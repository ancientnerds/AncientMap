# SPDX-License-Identifier: AGPL-3.0-only
"""The INSERT lane's writer: the shared writer's five steps, for a statement that creates a row.

`gallery_audit/chunk_writer.py` cannot apply this lane, and that is why the 476 `no_target_row`
sites of the read `import-hero-2026-10-06-006` had no row for the owner's picture: its
`lint_statement` refuses an INSERT and `apply_remediation_change()` (migrations 0017/0018/0022) is a
conditional UPDATE whose journal row it writes in the same statement. This module is the same five
commands over `import_hero/insert.py`'s chunks:

```bash
$PY scripts/remediation/import_hero/insert_writer.py $R/chunk-001 --check               # offline
$PY scripts/remediation/import_hero/insert_writer.py $R/chunk-001 --rehearse            # rolled back
$PY scripts/remediation/import_hero/insert_writer.py $R/chunk-001 --apply               # the one write
$PY scripts/remediation/import_hero/insert_writer.py $R/chunk-001 --readback            # plan = journal = data
$PY scripts/remediation/import_hero/insert_writer.py $R/chunk-001 --rehearse-rollback   # rolled back
```

The exit codes are the shared writer's, because the procedure that reads them is the same one: 0 ok,
1 refused (nothing sent), 3 the write did not commit, 4 committed but the read-back differs, 5 the
outcome is unknown (a timeout - read the journal, never retry), 6 committed and unconfirmed, 7 a
rehearsal did not roll back.

**The read-back is three-way and by identity, not by counts**: every planned row must have its
journal rows (plan -> journal), every journal row must belong to a planned column of the row it
names (journal -> plan), and the data must hold the values both of them claim. A count alone would
pass a journal that recorded the text `r.filename` instead of the file's name.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT / "scripts" / "remediation", ROOT / "scripts" / "remediation" / "gallery_audit"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import persist_verdicts as pv  # noqa: E402
from mechanical.apply import OPEN_SESSIONS_SQL, PSQL_SCRIPT_ERROR  # noqa: E402
from persist_verdicts import OutcomeUnknown  # noqa: E402

from import_hero import insert as IN  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_NOT_COMMITTED = 3
EXIT_COMMITTED_UNCLEAN = 4
EXIT_UNKNOWN = 5
EXIT_COMMITTED_UNCONFIRMED = 6
EXIT_REHEARSAL_FAILED = 7

READBACK_LABEL = IN.READBACK_LABEL
PIN_RE = re.compile(r"(?m)^-- pin: ([0-9a-f]{64})\s*$")


class InsertChunkError(pv.PersistError):
    """A chunk that must not be written, sent or trusted. Nothing was sent when this is raised."""


# ------------------------------------------------------------------------------ the delivered files
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_chunk(directory: Path) -> IN.InsertChunk:
    """The chunk the directory holds, rebuilt from its own records. Offline."""
    header = json.loads(_read(directory / "CHUNK.json"))
    rows = [
        IN.Insert.from_json(json.loads(line))
        for line in _read(directory / "INSERT.jsonl").splitlines()
        if line.strip()
    ]
    if header["rows"] != len(rows) or header["sites"] != len(rows):
        raise InsertChunkError(
            f"{directory / 'CHUNK.json'} claims {header['rows']} row(s), the file holds {len(rows)}"
        )
    chunk = IN.InsertChunk(
        stamp=header["run_id"],
        number=int(header["chunk"]),
        inserts=rows,
        # The floor this chunk serves, as its plan recorded it: the writer rebuilds the chunk and
        # re-renders its statement to compare against the file, so a rebuild at the lane's own floor
        # would refuse the very file the plan wrote (measured 2026-10-07, wave
        # `insert-2026-10-07-010`). A chunk written before the floor was recorded in `CHUNK.json`
        # served the lane's own floor, so the absent key means exactly that and nothing else.
        floor=(
            int(header.get("min_width", IN.HERO_MIN_WIDTH)),
            int(header.get("min_height", IN.HERO_MIN_HEIGHT)),
        ),
    )
    if chunk.run_stamp != f"{header['run_id']}-{int(header['chunk']):03d}":
        raise InsertChunkError(f"{directory}: the run stamp {chunk.run_stamp!r} is not numbered")
    if header["digest"] != chunk.digest:
        raise InsertChunkError(
            f"{directory} is not the plan it claims: digest {header['digest'][:12]}… against "
            f"{chunk.digest[:12]}…"
        )
    return chunk


def check_delivered(directory: Path) -> IN.InsertChunk:
    """The files on disk are exactly what the plan renders, or nothing is sent. Offline."""
    chunk = load_chunk(directory)
    for name, kind in (("APPLY.sql", "apply"), ("ROLLBACK.sql", "rollback")):
        path = directory / name
        if not path.is_file():
            raise InsertChunkError(f"{path} does not exist")
        text = _read(path)
        pin = PIN_RE.search(text)
        if pin is None or pin.group(1) != chunk.digest:
            raise InsertChunkError(
                f"{path} is not pinned to this plan (plan sha256 {chunk.digest})"
            )
        rendered = (
            IN.render_apply(chunk.inserts, chunk.run_stamp, digest=chunk.digest, floor=chunk.floor)
            if kind == "apply"
            else IN.render_rollback(chunk.inserts, chunk.run_stamp, digest=chunk.digest)
        )
        if text != rendered:
            raise InsertChunkError(
                f"{path} is not the statement its plan renders - edited or stale; refusing to send"
            )
        IN.lint_statement(text, kind=kind)
    return chunk


# ------------------------------------------------------------------------------------- production
def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def journal_rows(run_stamp: str) -> list[dict[str, Any]]:
    return pv.read_rows(
        "SELECT row_to_json(t) FROM (SELECT site_id_ref::text AS site_id, table_name, column_name,"
        " row_pk, old_value, new_value, change_key, confidence, test_id FROM remediation_change_log"
        f" WHERE run_stamp = {_literal(run_stamp)} ORDER BY id) t;"
    )


def journal_count(run_stamp: str) -> int:
    rows = pv.read_rows(
        "SELECT row_to_json(t) FROM (SELECT count(*)::int AS n FROM remediation_change_log"
        f" WHERE run_stamp = {_literal(run_stamp)}) t;"
    )
    if len(rows) != 1:
        raise InsertChunkError(f"the journal count for {run_stamp!r} came back as {rows!r}")
    return int(rows[0]["n"])


def _planned_count(chunk: IN.InsertChunk) -> int:
    return sum(row.journal_rows for row in chunk.inserts)


def read_rows_in_production(chunk: IN.InsertChunk) -> dict[str, dict[str, Any]]:
    """What the database holds for this chunk's rows: one entry per planned site, or a reason."""
    pairs = ", ".join(
        f"({_literal(row.site_id)}::uuid, {_literal(row.values['original_url'])})"
        for row in chunk.inserts
    )
    columns = ", ".join(f"w.{column}::text AS {column}" for column in IN.INSERT_COLUMNS)
    rows = pv.read_rows(
        "SELECT row_to_json(t) FROM (SELECT w.id::text AS row_id, w.site_id::text AS site_id,"
        f" {columns}, w.is_hero::text AS is_hero, w.is_excluded::text AS is_excluded,"
        " w.is_lead::text AS is_lead, w.source_type, w.sort_order::text AS sort_order"
        " FROM wiki_images w"
        f" JOIN (VALUES {pairs}) AS p(sid, url) ON w.site_id = p.sid AND w.original_url = p.url) t;"
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        site_id = str(row["site_id"])
        if site_id in out:
            raise InsertChunkError(f"site {site_id} holds the planned file twice")
        out[site_id] = row
    return out


def _thumbnails(chunk: IN.InsertChunk) -> dict[str, str | None]:
    ids = ", ".join(_literal(row.site_id) for row in chunk.inserts)
    rows = pv.read_rows(
        "SELECT row_to_json(t) FROM (SELECT id::text AS site_id, thumbnail_url FROM unified_sites"
        f" WHERE id IN ({ids})) t;"
    )
    return {str(row["site_id"]): row["thumbnail_url"] for row in rows}


def readback(chunk: IN.InsertChunk) -> list[str]:
    """Every difference between the plan, the journal and the data. Empty means confirmed."""
    problems: list[str] = []
    data = read_rows_in_production(chunk)
    thumbs = _thumbnails(chunk)
    journal = journal_rows(chunk.run_stamp)
    by_site: dict[str, list[dict[str, Any]]] = {}
    for row in journal:
        by_site.setdefault(str(row["site_id"]), []).append(row)

    for planned in chunk.inserts:
        site = planned.site_id
        held = data.get(site)
        if held is None:
            problems.append(f"{site}: no wiki_images row holds {planned.values['original_url']!r}")
            continue
        # data holds what the plan wrote
        for column in IN.INSERT_COLUMNS:
            if held.get(column) != planned.values[column]:
                problems.append(
                    f"{site}: {column} is {held.get(column)!r}, the plan wrote "
                    f"{planned.values[column]!r}"
                )
        if held.get("is_hero") != "true" or held.get("is_excluded") != "false":
            problems.append(
                f"{site}: the inserted row is_hero={held.get('is_hero')!r}, "
                f"is_excluded={held.get('is_excluded')!r}"
            )
        if held.get("is_lead") != "false" or held.get("source_type") != IN.SOURCE_TYPE:
            problems.append(
                f"{site}: the inserted row carries is_lead={held.get('is_lead')!r}, "
                f"source_type={held.get('source_type')!r}"
            )
        if thumbs.get(site) != planned.new_thumbnail:
            problems.append(
                f"{site}: thumbnail_url is {thumbs.get(site)!r}, the plan wrote "
                f"{planned.new_thumbnail!r}"
            )
        if planned.demoted_id:
            demoted = pv.read_rows(
                "SELECT row_to_json(t) FROM (SELECT is_hero::text AS is_hero FROM wiki_images"
                f" WHERE id = {int(planned.demoted_id)} AND site_id = {_literal(site)}::uuid) t;"
            )
            if not demoted or demoted[0]["is_hero"] != "false":
                problems.append(f"{site}: row {planned.demoted_id} still holds the hero flag")
        # the journal carries exactly this row's writes, with the values the row holds
        rows = by_site.get(site, [])
        if len(rows) != planned.journal_rows:
            problems.append(
                f"{site}: the journal holds {len(rows)} row(s), the plan writes "
                f"{planned.journal_rows}"
            )
        seen = {(str(row["table_name"]), str(row["column_name"])) for row in rows}
        for column in IN.JOURNAL_COLUMNS:
            if ("wiki_images", column) not in seen:
                problems.append(f"{site}: the journal carries no row for the written {column}")
        if planned.demoted_id and ("wiki_images", "is_hero") not in seen:
            problems.append(f"{site}: the journal carries no row for the demotion")
        if planned.thumbnail_changes and ("unified_sites", "thumbnail_url") not in seen:
            problems.append(f"{site}: the journal carries no row for the thumbnail")
        for row in rows:
            if (
                str(row["row_pk"]) != str(held["row_id"])
                and str(row["table_name"]) == "wiki_images"
            ):
                if not (planned.demoted_id and str(row["row_pk"]) == planned.demoted_id):
                    problems.append(
                        f"{site}: a journal row names row {row['row_pk']}, not the inserted "
                        f"{held['row_id']}"
                    )
            if row["test_id"] != IN.LANE_TEST_ID or row["confidence"] != IN.LANE_CONFIDENCE:
                problems.append(
                    f"{site}: a journal row carries test_id={row['test_id']!r}, "
                    f"confidence={row['confidence']!r}"
                )
            column = str(row["column_name"])
            if column in IN.JOURNAL_COLUMNS and str(row["new_value"]) != str(held.get(column)):
                problems.append(
                    f"{site}: the journal says {column} is {row['new_value']!r}, the row holds "
                    f"{held.get(column)!r}"
                )
    # nothing else: every journal row of this stamp belongs to a site of this chunk
    planned_sites = {row.site_id for row in chunk.inserts}
    extra = sorted(set(by_site) - planned_sites)
    if extra:
        problems.append(f"{len(extra)} site(s) outside the chunk carry this stamp: {extra[:5]}")
    return problems


# --------------------------------------------------------------------------------------- commands
def _ran_as_rehearsal(proc_stdout: str) -> bool:
    return (
        READBACK_LABEL in proc_stdout and "ROLLBACK" in proc_stdout and "COMMIT" not in proc_stdout
    )


def _unknown(chunk: IN.InsertChunk, detail: str) -> OutcomeUnknown:
    query = (
        "SELECT count(*) FROM remediation_change_log WHERE run_stamp = "
        f"{_literal(chunk.run_stamp)};"
    )
    return OutcomeUnknown(
        f"{detail} Before any retry: wait until {OPEN_SESSIONS_SQL} lists no session of this write, "
        f"then run: {query} - the chunk landed only if it reads {_planned_count(chunk)}, and "
        "nothing was written if it reads 0."
    )


def settle(chunk: IN.InsertChunk, what: str, *, session_ended: bool) -> int:
    """After a timeout or a failed psql exit: say from the journal what happened, never retry.

    All planned rows journalled means the transaction COMMITTED - a committed row cannot vanish.
    None means NOT COMMITTED only when psql itself stopped the script (its exit 3): its session is
    gone and an uncommitted transaction with it. After a timeout the server may still be running
    the script towards its COMMIT, so an empty journal is UNKNOWN.
    """
    expected = _planned_count(chunk)
    try:
        count = journal_count(chunk.run_stamp)
    except (OutcomeUnknown, pv.PersistError) as exc:
        raise _unknown(chunk, f"{what}; the journal could not be read either ({exc}).") from exc
    if count == 0 and session_ended:
        print(f"NOT COMMITTED: {what}; the journal holds 0 rows for {chunk.run_stamp!r}.")
        return EXIT_NOT_COMMITTED
    if count == 0:
        raise _unknown(chunk, f"{what}; the journal holds 0 rows so far.")
    if count != expected:
        raise _unknown(
            chunk,
            f"{what}; the journal holds {count} of {expected} rows - one transaction cannot "
            "leave that behind.",
        )
    print(f"COMMITTED: {what}, but the journal holds all {count} rows. Reading it back:")
    problems = readback(chunk)
    if problems:
        return _unconfirmed(problems)
    print("APPLY LANDED: the read-back matches the plan both ways; psql did not finish cleanly.")
    return EXIT_COMMITTED_UNCLEAN


def _unconfirmed(problems: list[str]) -> int:
    print("COMMITTED BUT NOT CONFIRMED: the write is in the database, but its read-back differs:")
    for problem in problems:
        print(f"  {problem}")
    return EXIT_COMMITTED_UNCONFIRMED


def command_rehearse(directory: Path) -> int:
    """APPLY.sql with its one COMMIT swapped for ROLLBACK: every guard runs, nothing is kept."""
    chunk = check_delivered(directory)
    proc = pv.run_psql(pv.rehearsal_of(_read(directory / "APPLY.sql")), check=False)
    print(proc.stdout)
    if proc.returncode != 0 or not _ran_as_rehearsal(proc.stdout):
        print(proc.stderr, file=sys.stderr)
        print(f"REHEARSAL FAILED: psql exit {proc.returncode}")
        return EXIT_REHEARSAL_FAILED
    left = journal_count(chunk.run_stamp)
    if left != 0:
        print(f"REHEARSAL FAILED: {left} journal row(s) of {chunk.run_stamp!r} survived it")
        return EXIT_REHEARSAL_FAILED
    print(f"REHEARSAL OK: chunk {chunk.number:03d}, {len(chunk.inserts)} row(s), rolled back")
    return EXIT_OK


def command_rehearse_rollback(directory: Path) -> int:
    """ROLLBACK.sql with COMMIT -> ROLLBACK, against the state the landed write left behind."""
    chunk = check_delivered(directory)
    proc = pv.run_psql(pv.rehearsal_of(_read(directory / "ROLLBACK.sql")), check=False)
    print(proc.stdout)
    if proc.returncode != 0 or not _ran_as_rehearsal(proc.stdout):
        print(proc.stderr, file=sys.stderr)
        print(f"ROLLBACK REHEARSAL FAILED: psql exit {proc.returncode}")
        return EXIT_REHEARSAL_FAILED
    problems = readback(chunk)
    if problems:
        print(f"ROLLBACK REHEARSAL FAILED: {len(problems)} difference(s) after the rehearsal:")
        for problem in problems[:20]:
            print(f"  {problem}")
        return EXIT_REHEARSAL_FAILED
    print("ROLLBACK REHEARSAL OK: the reversal ran on the landed rows and was rolled back")
    return EXIT_OK


def command_apply(directory: Path) -> int:
    chunk = check_delivered(directory)
    already = journal_count(chunk.run_stamp)
    if already:
        raise InsertChunkError(
            f"run stamp {chunk.run_stamp!r} already journals {already} row(s): this chunk has "
            "landed, or something else wrote under its stamp - run --readback; never apply twice"
        )
    try:
        proc = pv.run_psql(_read(directory / "APPLY.sql"), check=False)
    except OutcomeUnknown as exc:
        return settle(chunk, f"psql timed out ({exc})", session_ended=False)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return settle(
            chunk,
            f"psql exited {proc.returncode}",
            session_ended=proc.returncode == PSQL_SCRIPT_ERROR,
        )
    try:
        problems = readback(chunk)
    except (OutcomeUnknown, pv.PersistError) as exc:
        return _unconfirmed([f"the read-back could not run: {exc}"])
    if problems:
        return _unconfirmed(problems)
    print(
        f"APPLY OK: chunk {chunk.number:03d}, {len(chunk.inserts)} row(s); the read-back "
        "matches plan and journal both ways"
    )
    return EXIT_OK


def command_readback(directory: Path) -> int:
    chunk = check_delivered(directory)
    problems = readback(chunk)
    if problems:
        print("READBACK FAILED:")
        for problem in problems:
            print(f"  {problem}")
        return EXIT_COMMITTED_UNCONFIRMED
    print(
        f"READBACK OK: {len(chunk.inserts)} row(s), plan = journal = data "
        f"({_planned_count(chunk)} journal rows)"
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(
        prog="import_hero/insert_writer.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("chunk", type=Path, help="an emitted chunk directory")
    group = parser.add_mutually_exclusive_group(required=True)
    for flag in ("check", "rehearse", "apply", "readback", "rehearse-rollback"):
        group.add_argument(f"--{flag}", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check:
            chunk = check_delivered(args.chunk)
            print(
                f"CHECK OK: {args.chunk} is the plan's, {len(chunk.inserts)} row(s), "
                f"stamp {chunk.run_stamp!r}"
            )
            return EXIT_OK
        if args.rehearse:
            return command_rehearse(args.chunk)
        if args.apply:
            return command_apply(args.chunk)
        if args.readback:
            return command_readback(args.chunk)
        return command_rehearse_rollback(args.chunk)
    except OutcomeUnknown as exc:
        print(f"OUTCOME UNKNOWN: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN
    except pv.PersistError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
