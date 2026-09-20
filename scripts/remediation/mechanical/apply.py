"""Render, rehearse, apply and verify the mechanical country repairs.

The plan (`PLAN.jsonl`) is what `plan.py` decided; this module is the only place that writes
anything, and it writes through one transaction:

* `--emit` writes `APPLY.sql` - generated, never hand-edited.
* `--rehearse` writes `REHEARSAL.sql` (the byte-identical statement with `COMMIT` replaced by
  `ROLLBACK`, plus read-backs) and runs it against production, so the guards are exercised on the
  real rows before anything is kept.
* `--probe-guards` runs deliberately corrupted copies the same way, to show that the guards can
  actually fail instead of asserting that they exist.
* `--apply` runs the read-only verification, applies, and runs it again. Before and after come
  from the database, not from this plan.
* `--verify` is read-only.

`--rollback` is deliberately not a mode: `ROLLBACK.sql` exists and is generated, but reversing a
write is a decision, so running it is an explicit, reviewable `psql < ROLLBACK.sql`.
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.plan import (  # noqa: E402
    CONFIDENCE,
    CURATED_SOURCE,
    ROLLBACK_RUN_STAMP,
    RUN_STAMP,
    TEST_ID,
    UUID_RE,
    PlanError,
)

log = logging.getLogger("mechanical.apply")

SSH_HOST = "ancientnerds"
PSQL = "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1"
#: psql is asked for unaligned rows only for the read-only metrics, where the output is parsed.
#: No `-F|`: ssh hands this command to the remote login shell, which reads a bare `|` as a pipe
#: (measured: `bash: -c: line 2: syntax error`). Unaligned output already separates on `|`.
PSQL_ROWS = PSQL + " -t -A"

DEFAULT_PLAN = REPO / "output/remediation/mechanical/PLAN.jsonl"
DEFAULT_OUT = REPO / "output/remediation/mechanical"

#: The country column is `character varying(100)` (measured: information_schema.columns,
#: 2026-09-21). A longer value is an error, never a truncation.
COUNTRY_COLUMN_CHARS = 100

#: Probes write nothing that survives: each one is a copy of the real statement with COMMIT
#: replaced by ROLLBACK and its own run stamp, so a survivor would be visible as a journal row.
PROBE_RUN_STAMP = f"{RUN_STAMP}-probe"


# --------------------------------------------------------------------------------- the records
@dataclass(frozen=True)
class ChangeRecord:
    """One row to write, exactly as `PLAN.jsonl` holds it."""

    site_id: str
    site_name: str
    old_value: str
    new_value: str
    rule: str
    condition: str
    reason: str
    evidence: tuple[dict[str, Any], ...] = ()
    phase3: bool = False


def load_records(path: Path) -> list[ChangeRecord]:
    if not path.exists():
        raise PlanError(f"{path} is missing - build the plan first (plan.py --write)")
    records: list[ChangeRecord] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            records.append(
                ChangeRecord(
                    site_id=str(payload["site_id"]),
                    site_name=str(payload["site_name"]),
                    old_value=str(payload["old_value"]),
                    new_value=str(payload["new_value"]),
                    rule=str(payload["rule"]),
                    condition=str(payload["condition"]),
                    reason=str(payload["reason"]),
                    evidence=tuple(payload.get("evidence") or ()),
                    phase3=bool(payload.get("phase3")),
                )
            )
    if not records:
        raise PlanError(f"{path} holds no records")
    return records


def validate_records(records: Sequence[ChangeRecord], *, source: str = CURATED_SOURCE) -> None:
    """The plan-side mirror of the transaction's guards. Pure, so a test can break each one.

    The database guards are the authority (`render_transaction`); this exists so a corrupted plan
    is refused *before* a statement is rendered as well as inside the transaction.
    """
    if not records:
        raise PlanError("refusing to validate an empty plan")
    if source != CURATED_SOURCE:
        raise PlanError(f"this lane writes {CURATED_SOURCE!r} only, not {source!r}")
    seen: set[str] = set()
    for r in records:
        if not UUID_RE.match(r.site_id):
            raise PlanError(f"{r.site_id!r} is not a UUID")
        if r.site_id in seen:
            raise PlanError(f"{r.site_id} appears twice - the plan is not a set of rows")
        seen.add(r.site_id)
        if not r.old_value:
            raise PlanError(f"{r.site_id}: no old value - a conditional write needs one")
        if not r.new_value:
            raise PlanError(f"{r.site_id}: no new value - this lane never clears the column")
        if r.new_value == r.old_value:
            raise PlanError(f"{r.site_id}: old and new are both {r.old_value!r} - not a change")
        if len(r.new_value) > COUNTRY_COLUMN_CHARS:
            raise PlanError(
                f"{r.site_id}: the new value is {len(r.new_value)} characters, "
                f"the column holds {COUNTRY_COLUMN_CHARS}"
            )
        if not r.reason or not r.evidence:
            raise PlanError(f"{r.site_id}: a write without a reason and evidence is not auditable")


# ---------------------------------------------------------------------------------- rendering
def _literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def render_transaction(
    records: Sequence[ChangeRecord],
    *,
    run_stamp: str = RUN_STAMP,
    site_ids: Iterable[str],
    source: str = CURATED_SOURCE,
    validate: bool = True,
) -> str:
    """One transaction that writes `records` and journals each row, or writes nothing.

    Every row goes through `apply_remediation_change()`, which does the conditional UPDATE and the
    journal INSERT in one statement and raises unless exactly one row matched the expected old
    value. `ON_ERROR_STOP` plus the explicit `COMMIT` at the end means a refusal anywhere rolls the
    whole plan back.

    `validate=False` is for `--probe-guards` only: the probes must reach the *database's* guards,
    so the plan-side mirror must not refuse them a line earlier.
    """
    records = list(records)
    if not records:
        raise PlanError("refusing to render a transaction with no rows")
    if validate:
        validate_records(records, source=source)
    sites = sorted({str(s) for s in site_ids})
    out: list[str] = []
    add = out.append
    add("-- Generated by scripts/remediation/mechanical/apply.py - do not edit by hand.")
    add(
        f"-- {len(records)} row(s) over {len(sites)} site(s); scope source_id = {_literal(source)};"
    )
    add(f"-- run stamp {_literal(run_stamp)}; journal test id {_literal(TEST_ID)}.")
    add(
        "-- Every UPDATE is conditioned on the old value the plan names; every change is journalled"
    )
    add("-- in the same transaction, so the audit trail cannot disagree with the data.")
    add("\\set ON_ERROR_STOP on")
    add("BEGIN;")
    add("")
    add("CREATE TEMP TABLE _country_plan (")
    add("    site_id     UUID PRIMARY KEY,")
    add("    old_value   TEXT NOT NULL,")
    add("    new_value   TEXT NOT NULL,")
    add("    change_key  TEXT NOT NULL,")
    add("    reason      TEXT NOT NULL,")
    add("    evidence    JSONB NOT NULL")
    add(") ON COMMIT DROP;")
    add("")
    add(
        "INSERT INTO _country_plan (site_id, old_value, new_value, change_key, reason, evidence) VALUES"
    )
    rows = []
    for r in sorted(records, key=lambda r: r.site_id):
        rows.append(
            "    ("
            f"{_literal(r.site_id)}::uuid, {_literal(r.old_value)}, {_literal(r.new_value)}, "
            f"{_literal(f'country-canonical:{r.site_id}')}, {_literal(r.reason)}, "
            f"{_literal(json.dumps(list(r.evidence), ensure_ascii=False))}::jsonb)"
        )
    add(",\n".join(rows) + ";")
    add("")
    add("DO $$")
    add("DECLARE")
    add("    bad      INTEGER;")
    add("    moved    INTEGER := 0;")
    add("    expected INTEGER;")
    add("    r        RECORD;")
    add("BEGIN")
    add("    SELECT count(*) INTO expected FROM _country_plan;")
    add("")
    add("    -- scope guard 1: every planned row is a curated site that still exists")
    add("    SELECT count(*) INTO bad")
    add("      FROM _country_plan p LEFT JOIN unified_sites u ON u.id = p.site_id")
    add(f"     WHERE u.id IS NULL OR u.source_id <> {_literal(source)};")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION 'country repair: % planned row(s) are not {source} sites', bad;")
    add("    END IF;")
    add("")
    add("    -- scope guard 2: the plan is a set of real changes, each one writable in the column")
    add("    SELECT count(*) INTO bad FROM _country_plan p")
    add("     WHERE p.old_value IS NULL OR p.new_value = '' OR p.new_value = p.old_value")
    add(f"        OR length(p.new_value) > {COUNTRY_COLUMN_CHARS};")
    add("    IF bad > 0 THEN")
    add("        RAISE EXCEPTION 'country repair: % planned row(s) are not writable changes', bad;")
    add("    END IF;")
    add("")
    add("    -- scope guard 3: every planned row still holds the old value the plan names")
    add("    SELECT count(*) INTO bad")
    add("      FROM _country_plan p JOIN unified_sites u ON u.id = p.site_id")
    add("     WHERE u.country IS DISTINCT FROM p.old_value;")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'country repair: % planned row(s) no longer hold the planned old "
        "value', bad;"
    )
    add("    END IF;")
    add("")
    add("    -- the only writer: the conditional UPDATE and its journal row commit together, and")
    add("    -- the function raises unless exactly one row matched")
    add("    FOR r IN SELECT * FROM _country_plan ORDER BY site_id LOOP")
    add("        moved := moved + apply_remediation_change(")
    add("            'unified_sites', 'country', 'id', r.site_id::text,")
    add("            r.old_value, r.new_value,")
    add(
        f"            {_literal(TEST_ID)}, {_literal(run_stamp)}, r.change_key, "
        f"{_literal(CONFIDENCE)}, r.evidence, r.site_id);"
    )
    add("    END LOOP;")
    add("")
    add("    IF moved <> expected THEN")
    add("        RAISE EXCEPTION 'country repair: % row(s) changed, % planned', moved, expected;")
    add("    END IF;")
    add("")
    add("    -- invariant 1: every planned row now holds the new value")
    add("    SELECT count(*) INTO bad")
    add("      FROM _country_plan p JOIN unified_sites u ON u.id = p.site_id")
    add("     WHERE u.country IS DISTINCT FROM p.new_value;")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'country repair: % planned row(s) do not hold the new value', bad;"
    )
    add("    END IF;")
    add("")
    add("    -- invariant 2: the journal and the data agree, row for row, in both directions")
    add("    SELECT count(*) INTO bad")
    add("      FROM _country_plan p LEFT JOIN remediation_change_log l")
    add("        ON l.row_pk = p.site_id::text AND l.table_name = 'unified_sites'")
    add("       AND l.column_name = 'country'")
    add(f"       AND l.run_stamp = {_literal(run_stamp)}")
    add("     WHERE l.id IS NULL")
    add("        OR l.new_value IS DISTINCT FROM p.new_value")
    add("        OR l.old_value IS DISTINCT FROM p.old_value;")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'country repair: % planned row(s) have no matching journal row', "
        "bad;"
    )
    add("    END IF;")
    add("")
    add("    SELECT count(*) INTO bad FROM remediation_change_log l")
    add("     WHERE l.run_stamp = " + _literal(run_stamp))
    add("       AND (l.table_name <> 'unified_sites' OR l.column_name <> 'country');")
    add("    IF bad > 0 THEN")
    add(
        "        RAISE EXCEPTION 'country repair: this run stamp journalled % row(s) outside "
        "unified_sites.country', bad;"
    )
    add("    END IF;")
    add("")
    add(
        "    RAISE NOTICE 'country repair: % row(s) changed and journalled over % curated site(s)',"
    )
    add("        moved, expected;")
    add("END $$;")
    add("")
    add("COMMIT;")
    add("")
    add(
        POST_COMMIT_READS.format(
            run_stamp=_literal(run_stamp), test_id=_literal(TEST_ID), source=_literal(source)
        )
    )
    return "\n".join(out)


POST_COMMIT_READS = """\
-- Post-commit read: the numbers the report quotes, from the database, not from the plan.
SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {run_stamp}
UNION ALL
SELECT 'journal rows for this test id', count(*)::text
  FROM remediation_change_log WHERE test_id = {test_id}
UNION ALL
SELECT 'planned rows now holding the new value', count(*)::text
  FROM remediation_change_log l
 WHERE l.run_stamp = {run_stamp} AND l.table_name = 'unified_sites'
   AND l.column_name = 'country'
   AND EXISTS (SELECT 1 FROM unified_sites u
                WHERE u.id::text = l.row_pk AND u.country = l.new_value)
UNION ALL
SELECT 'curated rows still holding a parenthetical or comma country', count(*)::text
  FROM unified_sites
 WHERE source_id = {source} AND (country LIKE '%(%)%' OR country LIKE '%,%')
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source};
"""

REHEARSAL_READS = """\
-- after ROLLBACK: nothing may have changed
SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {run_stamp}
UNION ALL
SELECT 'curated rows still holding the old value', count(*)::text
  FROM unified_sites
 WHERE source_id = {source} AND (country LIKE '%(%' OR country LIKE '%,%')
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source}
UNION ALL
SELECT 'temp table _country_plan left behind', count(*)::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname = '_country_plan';
"""

VERIFY_SQL = f"""\
-- Read-only. The same file before and after the apply, so the two runs are comparable.
\\pset footer off
SELECT 'curated sites' AS metric, count(*)::text AS value
  FROM unified_sites WHERE source_id = 'ancient_nerds'
UNION ALL
SELECT 'distinct country values (curated)', count(DISTINCT country)::text
  FROM unified_sites WHERE source_id = 'ancient_nerds'
UNION ALL
SELECT 'rows country = ''Georgia (country)''', count(*)::text
  FROM unified_sites WHERE source_id = 'ancient_nerds' AND country = 'Georgia (country)'
UNION ALL
SELECT 'rows country = ''Georgia''', count(*)::text
  FROM unified_sites WHERE source_id = 'ancient_nerds' AND country = 'Georgia'
UNION ALL
SELECT 'rows country = ''Chile, Easter Island''', count(*)::text
  FROM unified_sites WHERE source_id = 'ancient_nerds' AND country = 'Chile, Easter Island'
UNION ALL
SELECT 'rows country = ''Chile''', count(*)::text
  FROM unified_sites WHERE source_id = 'ancient_nerds' AND country = 'Chile'
UNION ALL
SELECT 'journal rows for this run stamp', count(*)::text
  FROM remediation_change_log WHERE run_stamp = '{RUN_STAMP}'
UNION ALL
SELECT 'journal rows for this test id', count(*)::text
  FROM remediation_change_log WHERE test_id = '{TEST_ID}'
UNION ALL
SELECT 'journal rows for the rollback stamp', count(*)::text
  FROM remediation_change_log WHERE run_stamp = '{ROLLBACK_RUN_STAMP}'
UNION ALL
SELECT 'journal rows for this run outside unified_sites.country', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = '{RUN_STAMP}'
   AND (table_name <> 'unified_sites' OR column_name <> 'country')
UNION ALL
SELECT 'journal rows for this run on non-curated rows', count(*)::text
  FROM remediation_change_log l LEFT JOIN unified_sites u ON u.id::text = l.row_pk
 WHERE l.run_stamp = '{RUN_STAMP}'
   AND (u.id IS NULL OR u.source_id <> 'ancient_nerds')
UNION ALL
SELECT 'journal rows for this run with a site_id_ref of another site', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = '{RUN_STAMP}' AND site_id_ref::text <> row_pk
UNION ALL
SELECT 'distinct values for this run (should be 2)', count(DISTINCT new_value)::text
  FROM remediation_change_log WHERE run_stamp = '{RUN_STAMP}'
UNION ALL
SELECT 'curated rows whose country is a NULL or empty', count(*)::text
  FROM unified_sites WHERE source_id = 'ancient_nerds' AND (country IS NULL OR country = '')
UNION ALL
-- the residual this lane creates on purpose: card_stats.civilization still repeats the old value
SELECT 'card_stats rows whose civilization differs from the site country', count(*)::text
  FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id
 WHERE u.source_id = 'ancient_nerds' AND cs.civilization IS DISTINCT FROM u.country
ORDER BY 1;
"""

ROLLBACK_REHEARSAL_READS = """\
-- after ROLLBACK of the reversal: the reversal must leave nothing behind either
SELECT 'journal rows for the rollback stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {rollback_stamp}
UNION ALL
SELECT 'planned rows still holding the written value', count(*)::text
  FROM unified_sites WHERE id IN ({ids}) AND country IN ('Georgia', 'Chile')
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source}
UNION ALL
SELECT 'temp table _country_plan left behind', count(*)::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relname = '_country_plan';
"""

PRIMITIVE_CHECK_SQL = """\
-- Which body of apply_remediation_change is deployed? (migrations/0017 and 0018)
SELECT p.proname || '(' || coalesce(array_to_string(p.proargtypes::regtype[], ', '), '') || ')'
       AS signature
  FROM pg_proc p WHERE p.proname = 'apply_remediation_change';
SELECT pg_get_functiondef(p.oid) LIKE '%$1::%s WHERE%' AS casts_value_to_column_type,
       pg_get_functiondef(p.oid) LIKE '%IS NOT DISTINCT FROM $3::%s%' AS casts_old_value,
       pg_get_functiondef(p.oid) LIKE '%stored a different value%' AS rereads_stored_value
  FROM pg_proc p WHERE p.proname = 'apply_remediation_change';
"""


def rehearse(sql: str, *, run_stamp: str = RUN_STAMP, source: str = CURATED_SOURCE) -> str:
    """The same statement with `COMMIT` swapped for `ROLLBACK`, plus reads of what must not change.

    The point is to run the identical text - the same guards, the same 35 calls - against
    production without keeping any of it, so a broken guard is found before it is committing.
    """
    head, sep, _ = sql.partition("\nCOMMIT;\n")
    if not sep:
        raise PlanError("the emitted statement has no COMMIT - refusing to rehearse it")
    return (
        head
        + "\nROLLBACK;\n"
        + REHEARSAL_READS.format(run_stamp=_literal(run_stamp), source=_literal(source))
    )


# --------------------------------------------------------------------------------- transport
def run_psql(
    sql: str, *, host: str = SSH_HOST, timeout: int = 900, rows: bool = False, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Send `sql` to production the way this project does it: ssh, then psql in the container."""
    proc = subprocess.run(
        shlex.split(f"ssh {host} {PSQL_ROWS if rows else PSQL}"),
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise PlanError(f"psql exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}".strip())
    return proc


def read_rows(sql: str) -> list[list[str]]:
    proc = run_psql(sql, rows=True)
    return [line.split("|") for line in proc.stdout.splitlines() if line.strip()]


def _hub_rows() -> list[tuple[str, str, int]]:
    """(country, slug, rows) for every curated country - the hub shape, from the database.

    The slug function is the pipeline's own, which the hub route imports
    (`api/routes/sites_html.py:25`) and matches rows with: `/sites/{slug}` 404s once no row's
    `country` slugs to it, and only redirects a *case variant* of a slug that still matches.
    """
    from pipeline.sites_html_renderer import country_slug

    rows = read_rows(
        "SELECT country, count(*) FROM unified_sites "
        "WHERE source_id = 'ancient_nerds' GROUP BY country ORDER BY country"
    )
    return [(country, country_slug(country), int(count)) for country, count in rows]


def verify_interests(records: Sequence[ChangeRecord]) -> str:
    """The hub-slug table for the values this plan touches - measured, not asserted."""
    wanted = {r.old_value for r in records} | {r.new_value for r in records}
    rows = [row for row in _hub_rows() if row[0] in wanted]
    width = max((len(c) for c, _, _ in rows), default=1)
    lines = ["country value".ljust(width) + "  slug                     rows"]
    lines += [
        f"{country.ljust(width)}  {slug.ljust(23)} {count:>4}" for country, slug, count in rows
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------------------- the commands
def emit(records: Sequence[ChangeRecord], out: Path) -> int:
    validate_records(records)
    apply_path = out / "APPLY.sql"
    rollback_path = out / "ROLLBACK.sql"
    if not rollback_path.exists():
        raise PlanError(
            f"{rollback_path} does not exist - the rollback is written before the apply, never after"
        )
    sql = render_transaction(records, run_stamp=RUN_STAMP, site_ids={r.site_id for r in records})
    apply_path.parent.mkdir(parents=True, exist_ok=True)
    apply_path.write_text(sql, encoding="utf-8", newline="\n")
    log.info(
        "wrote %s (%d rows); ROLLBACK.sql is %s than APPLY.sql: %s",
        apply_path,
        len(records),
        "older" if rollback_path.stat().st_mtime <= apply_path.stat().st_mtime else "NEWER",
        f"{rollback_path.stat().st_mtime} vs {apply_path.stat().st_mtime}",
    )
    return len(records)


def cmd_rehearse(records: Sequence[ChangeRecord], out: Path) -> str:
    sql = (out / "APPLY.sql").read_text(encoding="utf-8")
    script = rehearse(sql)
    head = sql.partition("\nCOMMIT;\n")[0]
    if not script.startswith(head):
        raise PlanError("the rehearsal is not the byte-identical statement up to COMMIT")
    path = out / "REHEARSAL.sql"
    path.write_text(script, encoding="utf-8", newline="\n")
    log.info("wrote %s (COMMIT -> ROLLBACK)", path)
    proc = run_psql(script)
    print(proc.stdout)
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr)
    return proc.stdout


def cmd_rehearse_rollback(records: Sequence[ChangeRecord], out: Path) -> str:
    """Run `ROLLBACK.sql` with `COMMIT` swapped for `ROLLBACK`.

    The reversal starts from the state the write left behind, so this needs no apply first: it is
    the byte-identical rollback file, and its guards and journal are exercised against the real
    rows. Nothing is kept - the reads show the rows still holding the written value afterwards.
    """
    path = out / "ROLLBACK.sql"
    if not path.exists():
        raise PlanError(f"{path} does not exist - there is no reversal to rehearse")
    sql = path.read_text(encoding="utf-8")
    head, sep, _ = sql.partition("\nCOMMIT;\n")
    if not sep:
        raise PlanError("ROLLBACK.sql has no COMMIT - refusing to rehearse it")
    ids = ", ".join(_literal(str(r.site_id)) + "::uuid" for r in records)
    script = (
        head
        + "\nROLLBACK;\n"
        + ROLLBACK_REHEARSAL_READS.format(
            rollback_stamp=_literal(ROLLBACK_RUN_STAMP), source=_literal(CURATED_SOURCE), ids=ids
        )
    )
    target = out / "REHEARSAL_ROLLBACK.sql"
    target.write_text(script, encoding="utf-8", newline="\n")
    log.info("wrote %s (the reversal, COMMIT -> ROLLBACK)", target)
    proc = run_psql(script)
    print(proc.stdout)
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr)
    return proc.stdout


def cmd_apply(records: Sequence[ChangeRecord], out: Path) -> str:
    print("=== before ===")
    print(run_psql(VERIFY_SQL).stdout)
    print(verify_interests(records))
    sql = (out / "APPLY.sql").read_text(encoding="utf-8")
    proc = run_psql(sql)
    print("=== the write ===")
    print(proc.stdout)
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr)
    print("=== after ===")
    print(run_psql(VERIFY_SQL).stdout)
    print(verify_interests(records))
    return proc.stdout


def cmd_probe_guards(records: Sequence[ChangeRecord], out: Path) -> int:
    """Corrupt one copy per guard and show, on production, that the guard refuses.

    Each probe runs inside `BEGIN ... ROLLBACK` with its own run stamp. It writes nothing: the
    guards fire before the loop, and the failed statement aborts the transaction. The journal is
    read back afterwards to show that no probe left a row behind.
    """
    probes: list[tuple[str, str, list[ChangeRecord]]] = []

    corrupted_old = list(records)
    corrupted_old[0] = replace(corrupted_old[0], old_value="A country that was never there")
    probes.append(
        (
            "guard3-foreign-old-value",
            "guard 3 - a planned old value the row does not hold",
            corrupted_old,
        )
    )

    noop = list(records)
    noop[0] = replace(noop[0], new_value=noop[0].old_value)
    probes.append(("guard2-no-op", "guard 2 - a planned row that is not a change", noop))

    too_long = list(records)
    too_long[0] = replace(too_long[0], new_value="X" * 101)
    probes.append(("guard2-too-long", "guard 2 - a value longer than the column", too_long))

    foreign = read_rows(
        "SELECT id, name, coalesce(country, 'NULL') FROM unified_sites "
        "WHERE source_id <> 'ancient_nerds' AND country IS NOT NULL AND country <> '' "
        "AND source_id = 'canmore_scotland' LIMIT 1"
    )
    if not foreign:
        raise PlanError("no non-curated row to probe the source guard with")
    fid, fname, fcountry = foreign[0]
    other_source = list(records)
    other_source[0] = ChangeRecord(
        site_id=fid,
        site_name=fname,
        old_value=fcountry,
        new_value="Georgia",
        rule="probe",
        condition=f"id = {fid}",
        reason="probe: a row of another source, which must be refused",
        evidence=({"source": "probe", "quote": "corrupted copy"},),
    )
    probes.append(
        ("guard1-other-source", "guard 1 - a row outside source_id = 'ancient_nerds'", other_source)
    )

    failures = 0
    for suffix, name, mutated in probes:
        stamp = f"{PROBE_RUN_STAMP}-{suffix}"
        sql = render_transaction(
            mutated, run_stamp=stamp, site_ids={r.site_id for r in mutated}, validate=False
        )
        script = rehearse(sql, run_stamp=stamp, source=CURATED_SOURCE)
        proc = run_psql(script, check=False)
        raised = "ERROR" in proc.stdout or "ERROR" in proc.stderr
        print(f"[{name}] psql exit={proc.returncode} raised={raised}")
        for line in (proc.stdout + proc.stderr).splitlines():
            if "ERROR" in line or "country repair:" in line:
                print("   " + line.strip())
        left = read_rows(f"SELECT count(*) FROM remediation_change_log WHERE run_stamp = '{stamp}'")
        print(f"   journal rows left by this probe: {left[0][0] if left else '?'}")
        if not raised:
            failures += 1
            print(f"   !! the guard did NOT fire for {name} - this is a broken guard")
    return failures


# ------------------------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply the mechanical country-repair plan")
    ap.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--emit", action="store_true", help="write APPLY.sql only (no database)")
    ap.add_argument(
        "--rehearse",
        action="store_true",
        help="run APPLY.sql with COMMIT replaced by ROLLBACK, then report",
    )
    ap.add_argument(
        "--rehearse-rollback",
        action="store_true",
        help="run ROLLBACK.sql with COMMIT replaced by ROLLBACK, then report",
    )
    ap.add_argument(
        "--apply", action="store_true", help="verify, send APPLY.sql to production, verify again"
    )
    ap.add_argument("--verify", action="store_true", help="run the read-only verification")
    ap.add_argument(
        "--interests",
        action="store_true",
        help="read-only: the hub slug and row count of every value this plan touches",
    )
    ap.add_argument(
        "--probe-guards",
        action="store_true",
        help="run corrupted copies of the statement and show each guard refusing",
    )
    ap.add_argument(
        "--check-primitive",
        action="store_true",
        help="report which body of apply_remediation_change is deployed",
    )
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.check_primitive:
        print(run_psql(PRIMITIVE_CHECK_SQL).stdout)
        return 0
    if args.verify:
        print(run_psql(VERIFY_SQL).stdout)
        return 0

    records = load_records(args.plan)
    validate_records(records)

    if args.interests:
        print(verify_interests(records))
        return 0
    if args.probe_guards:
        return cmd_probe_guards(records, args.out)
    if args.emit or args.apply or args.rehearse or args.rehearse_rollback:
        emit(records, args.out)
    if args.rehearse:
        cmd_rehearse(records, args.out)
    if args.rehearse_rollback:
        cmd_rehearse_rollback(records, args.out)
    if args.apply:
        cmd_apply(records, args.out)
    if not any((args.emit, args.apply, args.rehearse, args.rehearse_rollback)):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
