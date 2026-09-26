"""A link step's production commands: check, rehearse, probe-guards, apply, verify, rehearse-rollback.

A step (`plan.step_wave(n)`, `output/remediation/qid_repair/l5/step-NNN/`) is rendered by
`qid_repair.render_split(removals=True)`: `site_external_ids` rows by their full key, `source_url`
through `apply_remediation_change()`, each journalled in the same transaction, guards before and
invariants after (qid_repair's docstring, "Wave 4" and `render_split`). The commands, in order:

    check              read-only: the files are the plan's statements, byte for byte, and every
                       planned row still holds its old value
    rehearse           the write ending in ROLLBACK (`render_split(rehearsal=True)`); the journal
                       holds no row of the step's stamp afterwards
    probe-guards       one corrupted copy per guard, each rehearsed: psql must stop (exit 3) on the
                       guard's own RAISE and leave no journal row
    apply              the journal holds no row of the stamp yet; APPLY.sql; the outcome settled from
                       the journal, never by a retry; then verify
    verify             read-only: every row holds its new value, the journal holds exactly the plan's
                       change keys under the stamp
    rehearse-rollback  after the apply: ROLLBACK.sql ending in ROLLBACK, run on the landed rows

Exit codes as `mechanical/apply.py`'s: 0 OK, 1 REFUSED, 3 NOT COMMITTED, 4 COMMITTED (psql did not
finish cleanly, read-back confirmed), 5 OUTCOME UNKNOWN, 6 COMMITTED BUT NOT CONFIRMED, 7 a
rehearsal or a probe fell short.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import lanes  # noqa: E402 - the read-only psql seam of the qid_repair tool
import qid_repair as QR  # noqa: E402
from mechanical import apply as A  # noqa: E402
from prod_write import OutcomeUnknown, send  # noqa: E402

from l5 import plan as L5P  # noqa: E402

PREFIX = "source-url split: "
#: What each guard of `render_split` says after `source-url split: <count> ` - the probe is proven
#: only when psql's ERROR line carries its own guard's text.
SAYS = {
    "guard1": "site(s) are not curated sites",
    "guard2": "source_url value(s) no longer hold the planned old value",
    "guard3": "external-id row(s) no longer hold the planned old value",
    "guard5": "planned item(s) are carried by another curated site",
    "invariant4": "site(s) left without a link on an English Wikipedia source_url",
}
NEVER_STORED = "never stored (L5 probe)"

Send = Callable[[str], Any]
Read = Callable[[str], str]


class StepError(ValueError):
    """A step that must not be sent. Nothing was sent when this is raised."""


# ------------------------------------------------------------------------------ the offline check
def delivered(number: int) -> tuple[QR.Wave, list[QR.Change]]:
    """The step's plan, only if its APPLY.sql and ROLLBACK.sql are exactly what it renders."""
    wave = L5P.step_wave(number)
    rows = L5P.load_step(wave)
    rendered = L5P.statements(rows, wave)
    for name in ("APPLY.sql", "ROLLBACK.sql"):
        path = wave.out / name
        if not path.exists() or path.read_text(encoding="utf-8") != rendered[name]:
            raise StepError(f"{path} is not the statement its plan renders - edited or stale")
    return wave, rows


def journal_count(stamp: str, read: Read = lanes.psql) -> int:
    rows = lanes.json_rows(
        read(
            "SELECT to_jsonb(t)::text FROM (SELECT count(*)::int AS n FROM remediation_change_log "
            f"WHERE run_stamp = {lanes.sql_text(stamp)}) t;"
        )
    )
    return int(rows[0]["n"])


def deviations(rows: list[QR.Change], want: str, read: Read = lanes.psql) -> list[str]:
    """What production holds that differs from the plan's old (`want="old"`) or new values."""
    return QR.compare(rows, QR.read_rows(rows, run=read), want=want)


def journal_keys(stamp: str, read: Read = lanes.psql) -> set[str]:
    return {
        r["change_key"]
        for r in lanes.json_rows(
            read(
                "SELECT to_jsonb(t)::text FROM (SELECT change_key FROM remediation_change_log "
                f"WHERE run_stamp = {lanes.sql_text(stamp)}) t;"
            )
        )
    }


def verify(rows: list[QR.Change], wave: QR.Wave, read: Read = lanes.psql) -> list[str]:
    problems = deviations(rows, "new", read)
    keys = journal_keys(wave.run_stamp, read)
    if keys != {r.change_key for r in rows}:
        problems.append(
            f"the journal holds {len(keys)} key(s) under {wave.run_stamp}, the plan {len(rows)}"
        )
    return problems


# ------------------------------------------------------------------------------ the probes
def probe_cases(
    rows: Sequence[QR.Change], live: Mapping[str, Any]
) -> list[tuple[str, list[QR.Change]]]:
    """One corrupted copy of the step per guard it renders, named by the guard.

    `live` is read from production by the caller: `foreign` (a site id of another source),
    `shared` (an item another curated site carries) and `links` (the first site's stored
    external-id rows, `[(kind, value)]`). Pure.
    """
    ext = [r for r in rows if r.table == QR.TABLE]
    urls = [r for r in rows if r.table == QR.SITES_TABLE]
    first = rows[0]
    cases: list[tuple[str, list[QR.Change]]] = [
        ("guard1", [replace(first, site_id=str(live["foreign"])), *rows[1:]]),
    ]
    if ext:
        i = rows.index(ext[0])
        cases.append(
            ("guard3", [*rows[:i], replace(ext[0], old_value=NEVER_STORED), *rows[i + 1 :]])
        )
    if urls:
        i = rows.index(urls[0])
        cases.append(
            ("guard2", [*rows[:i], replace(urls[0], old_value=NEVER_STORED), *rows[i + 1 :]])
        )
    replaced = [r for r in ext if r.kind == "wikidata_qid" and r.new_value is not None]
    if replaced:
        i = rows.index(replaced[0])
        cases.append(
            (
                "guard5",
                [*rows[:i], replace(replaced[0], new_value=str(live["shared"])), *rows[i + 1 :]],
            )
        )
    # the first site loses both links and keeps its English Wikipedia source_url
    sid = first.site_id
    removal = [
        replace(
            first,
            table=QR.TABLE,
            kind=kind,
            old_value=value,
            new_value=None,
            change_key=f"probe:{kind}",
        )
        for kind, value in live["links"]
    ]
    cases.append(("invariant4", [r for r in rows if r.site_id != sid] + removal))
    return cases


def probe_live(rows: Sequence[QR.Change], read: Read = lanes.psql) -> dict[str, Any]:
    """What the probes need from production (read-only): a foreign site, a shared item, and the
    first planned site's stored links - the state its invariant-4 probe removes."""
    foreign = lanes.json_rows(
        read(
            "SELECT to_jsonb(t)::text FROM (SELECT id::text AS id FROM unified_sites "
            f"WHERE source_id <> {lanes.sql_text(QR.CURATED)} LIMIT 1) t;"
        )
    )
    shared = lanes.json_rows(
        read(
            "SELECT to_jsonb(t)::text FROM (SELECT e.value FROM site_external_ids e JOIN "
            "unified_sites u ON u.id = e.site_id WHERE e.kind = 'wikidata_qid' AND "
            f"u.source_id = {lanes.sql_text(QR.CURATED)} AND e.site_id NOT IN ("
            + ", ".join(f"{lanes.sql_text(r.site_id)}::uuid" for r in rows)
            + ") ORDER BY e.value LIMIT 1) t;"
        )
    )
    first = rows[0].site_id
    links = lanes.json_rows(
        read(
            "SELECT to_jsonb(t)::text FROM (SELECT kind, value FROM site_external_ids "
            f"WHERE site_id = {lanes.sql_text(first)}::uuid ORDER BY kind) t;"
        )
    )
    if not foreign or not shared or not links:
        raise StepError("production gave no foreign site, shared item or stored link to probe with")
    return {
        "foreign": foreign[0]["id"],
        "shared": shared[0]["value"],
        "links": [(r["kind"], r["value"]) for r in links],
    }


def refused_by(guard: str, output: str) -> bool:
    own = re.compile(re.escape(PREFIX) + r"\d+ " + re.escape(SAYS[guard]))
    return any("ERROR:" in line and own.search(line) for line in output.splitlines())


# ------------------------------------------------------------------------------ the commands
def cmd_check(number: int, read: Read = lanes.psql) -> int:
    wave, rows = delivered(number)
    problems = deviations(rows, "old", read)
    for problem in problems:
        print(f"  DEVIATION {problem}")
    print(f"check {wave.out.name}: {len(rows)} row(s), {len(problems)} deviation(s)")
    return A.EXIT_OK if not problems else A.EXIT_REFUSED


def _rehearsed(proc: Any, stamp: str, read: Read) -> tuple[bool, int]:
    ok = proc.returncode == 0 and "ROLLBACK" in proc.stdout and "COMMIT" not in proc.stdout
    return ok, journal_count(stamp, read)


def cmd_rehearse(number: int, sender: Send = send, read: Read = lanes.psql) -> int:
    wave, rows = delivered(number)
    sql = QR.render_split(rows, reversal=False, rehearsal=True, wave=wave, removals=True)
    proc = sender(sql)
    print(proc.stdout)
    ok, left = _rehearsed(proc, wave.run_stamp, read)
    if not ok or left:
        print(proc.stderr, file=sys.stderr)
        print(f"REHEARSAL FAILED: psql exit {proc.returncode}, {left} journal row(s) left")
        return A.EXIT_PROBE_FAILED
    print(f"REHEARSAL OK: {wave.out.name}, {len(rows)} row(s), rolled back")
    return A.EXIT_OK


def cmd_probe_guards(number: int, sender: Send = send, read: Read = lanes.psql) -> int:
    wave, rows = delivered(number)
    failures = 0
    for guard, mutated in probe_cases(rows, probe_live(rows, read)):
        probe = replace(wave, run_stamp=f"{wave.run_stamp}-probe-{guard}")
        sql = QR.render_split(mutated, reversal=False, rehearsal=True, wave=probe, removals=True)
        proc = sender(sql)
        output = proc.stdout + proc.stderr
        own = proc.returncode == A.PSQL_SCRIPT_ERROR and refused_by(guard, output)
        left = journal_count(probe.run_stamp, read)
        print(f"[{guard}] psql exit={proc.returncode} refused by its own guard={own}, {left} left")
        if not own or left:
            failures += 1
            print(f"   !! expected exit {A.PSQL_SCRIPT_ERROR} with '{PREFIX}<n> {SAYS[guard]}'")
    return A.EXIT_OK if failures == 0 else A.EXIT_PROBE_FAILED


def _settle(rows: list[QR.Change], wave: QR.Wave, what: str, ended: bool, read: Read) -> int:
    """After a timeout or a failed exit: the journal says what happened; nothing is retried."""
    count = journal_count(wave.run_stamp, read)
    if count == 0 and ended:
        print(f"NOT COMMITTED: {what}; the journal holds 0 rows for {wave.run_stamp!r}")
        return A.EXIT_NOT_COMMITTED
    if count != len(rows):
        print(
            f"OUTCOME UNKNOWN: {what}; the journal holds {count} of {len(rows)} rows. Wait until "
            f"no session of this write is open ({A.OPEN_SESSIONS_SQL}), then count again."
        )
        return A.EXIT_UNKNOWN
    problems = verify(rows, wave, read)
    if problems:
        print("COMMITTED BUT NOT CONFIRMED: " + "; ".join(problems))
        return A.EXIT_COMMITTED_UNCONFIRMED
    print(f"COMMITTED: {what}, but the read-back matches the plan")
    return A.EXIT_COMMITTED_UNCLEAN


def cmd_apply(number: int, sender: Send = send, read: Read = lanes.psql) -> int:
    wave, rows = delivered(number)
    already = journal_count(wave.run_stamp, read)
    if already:
        raise StepError(
            f"run stamp {wave.run_stamp!r} already journals {already} row(s): never apply twice - "
            "run verify"
        )
    problems = deviations(rows, "old", read)
    if problems:
        raise StepError(
            f"{len(problems)} planned row(s) no longer hold their old value: {problems[:3]}"
        )
    try:
        proc = sender((wave.out / "APPLY.sql").read_text(encoding="utf-8"))
    except OutcomeUnknown as exc:
        return _settle(rows, wave, f"psql timed out ({exc})", False, read)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return _settle(
            rows,
            wave,
            f"psql exited {proc.returncode}",
            proc.returncode == A.PSQL_SCRIPT_ERROR,
            read,
        )
    problems = verify(rows, wave, read)
    if problems:
        print("COMMITTED BUT NOT CONFIRMED: " + "; ".join(problems))
        return A.EXIT_COMMITTED_UNCONFIRMED
    print(f"APPLY OK: {wave.out.name}, {len(rows)} row(s), plan = journal = data")
    return A.EXIT_OK


def cmd_verify(number: int, read: Read = lanes.psql) -> int:
    wave, rows = delivered(number)
    problems = verify(rows, wave, read)
    for problem in problems:
        print(f"  DEVIATION {problem}")
    print(f"verify {wave.out.name}: {len(rows)} row(s), {len(problems)} deviation(s)")
    return A.EXIT_OK if not problems else A.EXIT_COMMITTED_UNCONFIRMED


def cmd_rehearse_rollback(number: int, sender: Send = send, read: Read = lanes.psql) -> int:
    wave, rows = delivered(number)
    if verify(rows, wave, read):
        raise StepError(
            f"{wave.out.name} has not landed as planned - rehearse its undo after the apply"
        )
    sql = QR.render_split(rows, reversal=True, rehearsal=True, wave=wave, removals=True)
    proc = sender(sql)
    print(proc.stdout)
    ok, left = _rehearsed(proc, wave.rollback_stamp, read)
    if not ok or left or verify(rows, wave, read):
        print(proc.stderr, file=sys.stderr)
        print(f"ROLLBACK REHEARSAL FAILED: psql exit {proc.returncode}, {left} row(s) kept")
        return A.EXIT_PROBE_FAILED
    print(f"ROLLBACK REHEARSAL OK: {wave.out.name}, the undo ran on the landed rows, rolled back")
    return A.EXIT_OK


COMMANDS: dict[str, Callable[[int], int]] = {
    "check": cmd_check,
    "rehearse": cmd_rehearse,
    "probe-guards": cmd_probe_guards,
    "apply": cmd_apply,
    "verify": cmd_verify,
    "rehearse-rollback": cmd_rehearse_rollback,
}
