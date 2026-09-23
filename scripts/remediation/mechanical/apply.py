"""Render, rehearse, apply and verify the mechanical repairs of one lane.

The plan (`PLAN.jsonl`) is what a lane's planner decided; this module is the only place that writes
anything, and it writes through one transaction:

* `--emit` writes `APPLY.sql` - generated, never hand-edited - and pins it to the plan: its first
  line is `-- plan sha256 <digest of PLAN.jsonl>`. It refuses unless `ROLLBACK.sql` exists and is
  the reversal of *this* plan, pinned the same way.
* `--rehearse` writes `REHEARSAL.sql` (the byte-identical statement with `COMMIT` replaced by
  `ROLLBACK`, plus read-backs) and runs it against production, so the guards are exercised on the
  real rows before anything is kept.
* `--probe-guards` runs deliberately corrupted copies the same way, to show that the guards can
  actually fail instead of asserting that they exist.
* `--apply` runs the read-only verification, applies, and runs it again. Before and after come
  from the database, not from this plan.
* `--verify` is read-only.

`--rehearse`, `--rehearse-rollback` and `--apply` never re-emit: they send the file on disk, and
only when it is still the statement its plan renders and its pin names the plan as it is now
(`[H] SECURITY 3 / BACKEND B7`). A plan changed after the emit, a hand edit, or a file from another
plan is refused.

After a psql timeout or a failed exit, `--apply` reads the journal for its run stamp. All rows
journalled means the transaction COMMITTED - a committed row cannot vanish. None journalled means
NOT COMMITTED only after psql's own exit 3: ON_ERROR_STOP stopped the script, so its session has
ended and an uncommitted transaction can never commit. After a client timeout or ssh's 255 the
server may still be running the script towards its COMMIT (measured 2026-09-23), so an empty journal
is an UNKNOWN outcome, reported with the queries to run before any retry. Once psql has exited 0
the write is in the database whatever its read-back says: a read-back that fails or disagrees is
reported as COMMITTED BUT NOT CONFIRMED, never as a refusal.

The exit codes the runbook reads: 0 OK, 1 REFUSED (nothing was sent), 3 NOT COMMITTED, 4 COMMITTED
(read-back confirmed, psql did not finish cleanly), 5 OUTCOME UNKNOWN, 6 COMMITTED BUT NOT CONFIRMED,
7 a guard probe did not see its own guard refuse.

`--lane` names the lane (`mechanical/lane.py`): the column, the journal identity and the values it
owns. It defaults to `t05`, the country lane applied on 2026-09-21, whose statement this module
still renders byte for byte (pinned in `tests/remediation/test_mechanical.py`).

`--rollback` is deliberately not a mode: `ROLLBACK.sql` exists and is generated, but reversing a
write is a decision, so running it is an explicit, reviewable `psql < ROLLBACK.sql`.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from prod_write import SSH_HOST, OutcomeUnknown, send  # noqa: E402

from mechanical.lane import LANE_READBACKS, LANES, T05, Lane  # noqa: E402
from mechanical.lane import sql_literal as _literal  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    ROLLBACK_RUN_STAMP,
    RUN_STAMP,
    TEST_ID,
    UUID_RE,
    PlanError,
    pinned,
    plan_sha256,
    psql_json_reader,
    render_rollback_sql,
    verify_pinned,
)

log = logging.getLogger("mechanical.apply")

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_NOT_COMMITTED = 3
EXIT_COMMITTED_UNCLEAN = 4
EXIT_UNKNOWN = 5
EXIT_COMMITTED_UNCONFIRMED = 6
EXIT_PROBE_FAILED = 7
COMMITTED = "COMMITTED"
NOT_COMMITTED = "NOT COMMITTED"

#: psql's exit status when ON_ERROR_STOP stopped the script at an error (psql(1), "Exit Status").
#: psql has then ended, and its session with it: a transaction that had not committed was aborted
#: and can never commit, so an empty journal is final. No other failure says that - a client
#: timeout, ssh's 255 or psql's 1 and 2 can leave the server session running the script.
PSQL_SCRIPT_ERROR = 3

#: What each in-transaction guard says when it refuses, after `<lane label>: <count> `. The renderer
#: writes these into the RAISE messages, and `--probe-guards` counts a probe as proven only when
#: psql's ERROR line carries its own guard's text: a probe refused by another guard (guard 4 also
#: refuses a too-long value, the column itself refuses 101 characters) proves nothing about its own.
#: Guard 1's second `%` is the curated source, a RAISE argument; guard 4's `{what}` is write/undo.
GUARD1_SAYS = "planned row(s) are not % sites"
GUARD2_SAYS = "planned row(s) are not writable changes"
GUARD3_SAYS = "planned row(s) no longer hold the planned old value"
GUARD4_SAYS = "planned row(s) {what} a value this lane does not own"
GUARD5_SAYS = "planned row(s) no longer hold the premise the plan derived its value from"


def lane_dir(lane: Lane) -> Path:
    """Where a lane's plan and statements live: `output/remediation/<out_dir_name>/`."""
    return REPO / "output" / "remediation" / lane.out_dir_name


DEFAULT_PLAN = lane_dir(T05) / "PLAN.jsonl"
DEFAULT_OUT = lane_dir(T05)


def change_key(site_id: str, lane: Lane = T05) -> str:
    """The journal's identity for one row's *write* (see `Lane.change_key`)."""
    return lane.change_key(site_id)


def rollback_change_key(site_id: str, lane: Lane = T05) -> str:
    """The journal's identity for one row's *reversal* (see `Lane.rollback_change_key`)."""
    return lane.rollback_change_key(site_id)


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
    #: The live input the value was derived from, as the database prints it (`Lane.premise_sql`).
    premise: str | None = None


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
            premise = payload.get("premise")
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
                    premise=None if premise is None else str(premise),
                )
            )
    if not records:
        raise PlanError(f"{path} holds no records")
    return records


def validate_records(
    records: Sequence[ChangeRecord],
    *,
    source: str = CURATED_SOURCE,
    lane: Lane = T05,
    rollback: bool = False,
) -> None:
    """The plan-side mirror of the transaction's guards. Pure, so a test can break each one.

    The database guards are the authority (`render_transaction`); this exists so a corrupted plan
    is refused *before* a statement is rendered as well as inside the transaction. For a reversal
    (`rollback=True`) the value the lane owns is the one being undone, so the owned-value check
    reads `old_value` instead of `new_value`.
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
        if len(r.new_value) > lane.max_chars:
            raise PlanError(
                f"{r.site_id}: the new value is {len(r.new_value)} characters, "
                f"the column holds {lane.max_chars}"
            )
        owned = r.old_value if rollback else r.new_value
        if lane.allowed_new_values and owned not in lane.allowed_new_values:
            raise PlanError(
                f"{r.site_id}: {owned!r} is not a value the {lane.name} lane owns "
                f"({', '.join(lane.allowed_new_values)})"
            )
        if lane.premise_sql is not None and r.premise is None:
            raise PlanError(
                f"{r.site_id}: the {lane.name} lane derives its value from {lane.premise_sql}, "
                "and the record carries no premise to condition the write on"
            )
        if lane.premise_sql is None and r.premise is not None:
            raise PlanError(
                f"{r.site_id}: the {lane.name} lane checks no premise, and a premise nobody "
                "checks is a false assurance"
            )
        if not r.reason or not r.evidence:
            raise PlanError(f"{r.site_id}: a write without a reason and evidence is not auditable")


# ---------------------------------------------------------------------------------- rendering
def render_transaction(
    records: Sequence[ChangeRecord],
    *,
    run_stamp: str | None = None,
    site_ids: Iterable[str],
    source: str = CURATED_SOURCE,
    validate: bool = True,
    rollback: bool = False,
    lane: Lane = T05,
) -> str:
    """One transaction that writes `records` and journals each row, or writes nothing.

    Every row goes through `apply_remediation_change()`, which does the conditional UPDATE and the
    journal INSERT in one statement and raises unless exactly one row matched the expected old
    value. `ON_ERROR_STOP` plus the explicit `COMMIT` at the end means a refusal anywhere rolls the
    whole plan back.

    `validate=False` is for `--probe-guards` only: the probes must reach the *database's* guards,
    so the plan-side mirror must not refuse them a line earlier.

    `rollback=True` renders the reversal, and with it the reversal's own `change_key` (see
    `rollback_change_key`): the two directions of one row are two transitions, not one. A missing
    `run_stamp` is the lane's own - the write's, or the reversal's.
    """
    records = list(records)
    if not records:
        raise PlanError("refusing to render a transaction with no rows")
    if validate:
        validate_records(records, source=source, lane=lane, rollback=rollback)
    if run_stamp is None:
        run_stamp = lane.rollback_run_stamp if rollback else lane.run_stamp
    key_of = lane.rollback_change_key if rollback else lane.change_key
    table, column, label = lane.plan_table, lane.column, lane.label
    premise = lane.premise_sql is not None
    sites = sorted({str(s) for s in site_ids})
    out: list[str] = []
    add = out.append
    add("-- Generated by scripts/remediation/mechanical/apply.py - do not edit by hand.")
    add(
        f"-- {len(records)} row(s) over {len(sites)} site(s); scope source_id = {_literal(source)};"
    )
    add(f"-- run stamp {_literal(run_stamp)}; journal test id {_literal(lane.test_id)}.")
    add(
        "-- Every UPDATE is conditioned on the old value the plan names; every change is journalled"
    )
    add("-- in the same transaction, so the audit trail cannot disagree with the data.")
    add("\\set ON_ERROR_STOP on")
    add("BEGIN;")
    add("")
    if lane.lock_timeout is not None or lane.statement_timeout is not None:
        add(
            "-- The server bounds this transaction itself: a lock wait or a runaway statement raises"
        )
        add(
            "-- here, psql stops the script (exit 3) and nothing is kept. A client that gives up does"
        )
        add("-- not stop the server - psql has the whole script on its stdin.")
        if lane.lock_timeout is not None:
            add(f"SET LOCAL lock_timeout = {_literal(lane.lock_timeout)};")
        if lane.statement_timeout is not None:
            add(f"SET LOCAL statement_timeout = {_literal(lane.statement_timeout)};")
        add("")
    add(f"CREATE TEMP TABLE {table} (")
    add("    site_id     UUID PRIMARY KEY,")
    add("    old_value   TEXT NOT NULL,")
    add("    new_value   TEXT NOT NULL,")
    add("    change_key  TEXT NOT NULL,")
    add("    reason      TEXT NOT NULL,")
    if premise:
        add("    premise     TEXT NOT NULL,")
    add("    evidence    JSONB NOT NULL")
    add(") ON COMMIT DROP;")
    add("")
    premise_column = " premise," if premise else ""
    add(
        f"INSERT INTO {table} (site_id, old_value, new_value, change_key, reason,{premise_column} "
        "evidence) VALUES"
    )
    rows = []
    for r in sorted(records, key=lambda r: r.site_id):
        premise_value = f"{_literal(r.premise)}, " if premise else ""
        rows.append(
            "    ("
            f"{_literal(r.site_id)}::uuid, {_literal(r.old_value)}, {_literal(r.new_value)}, "
            f"{_literal(key_of(r.site_id))}, {_literal(r.reason)}, {premise_value}"
            f"{_literal(json.dumps(list(r.evidence), ensure_ascii=False))}::jsonb)"
        )
    add(",\n".join(rows) + ";")
    add("")
    add("DO $$")
    add("DECLARE")
    add("    bad      INTEGER;")
    add("    moved    INTEGER := 0;")
    add(f"    expected INTEGER := {len(records)};")
    add("    r        RECORD;")
    add("BEGIN")
    add("    -- expected is the plan's own row count, rendered here, and not a second count of the")
    add("    -- temp table the loop below iterates: counting the same table twice would make the")
    add("    -- comparison after the loop a tautology. The instance that makes a short loop")
    add("    -- unreachable is apply_remediation_change, which raises unless exactly one row")
    add("    -- matched; this guard is what reports a loop that changed fewer rows than the plan.")
    add("")
    add("    -- scope guard 1: every planned row is a curated site that still exists")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {table} p LEFT JOIN unified_sites u ON u.id = p.site_id")
    add(f"     WHERE u.id IS NULL OR u.source_id <> {_literal(source)};")
    add("    IF bad > 0 THEN")
    add("        -- the source name is a RAISE argument, never part of the quoted message: a name")
    add("        -- spliced into the message text only parses while the name happens to contain no")
    add(
        "        -- quote, which is a property of today's value and not of this code. G0's guard is"
    )
    add("        -- the shape this one copies.")
    add(f"        RAISE EXCEPTION '{label}: % {GUARD1_SAYS}', bad, {_literal(source)};")
    add("    END IF;")
    add("")
    add("    -- scope guard 2: the plan is a set of real changes, each one writable in the column")
    add(f"    SELECT count(*) INTO bad FROM {table} p")
    add("     WHERE p.old_value IS NULL OR p.new_value = '' OR p.new_value = p.old_value")
    add(f"        OR length(p.new_value) > {lane.max_chars};")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION '{label}: % {GUARD2_SAYS}', bad;")
    add("    END IF;")
    add("")
    add("    -- scope guard 3: every planned row still holds the old value the plan names")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {table} p JOIN unified_sites u ON u.id = p.site_id")
    add(f"     WHERE u.{column} IS DISTINCT FROM p.old_value;")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION '{label}: % {GUARD3_SAYS}', bad;")
    add("    END IF;")
    add("")
    if lane.allowed_new_values:
        owned = "p.old_value" if rollback else "p.new_value"
        what = "undo" if rollback else "write"
        add(
            f"    -- scope guard 4: every planned row {what}s a value this lane owns "
            f"({'old' if rollback else 'new'} value)"
        )
        add(f"    SELECT count(*) INTO bad FROM {table} p")
        add(
            f"     WHERE {owned} NOT IN ("
            + ", ".join(_literal(v) for v in lane.allowed_new_values)
            + ");"
        )
        add("    IF bad > 0 THEN")
        add(f"        RAISE EXCEPTION '{label}: % {GUARD4_SAYS.format(what=what)}', bad;")
        add("    END IF;")
        add("")
    if premise:
        add(
            "    -- scope guard 5: every planned row still holds the input its value was derived from"
        )
        add("    SELECT count(*) INTO bad")
        add(f"      FROM {table} p JOIN unified_sites u ON u.id = p.site_id")
        add(f"     WHERE ({lane.premise_sql}) IS DISTINCT FROM p.premise;")
        add("    IF bad > 0 THEN")
        add(f"        RAISE EXCEPTION '{label}: % {GUARD5_SAYS}', bad;")
        add("    END IF;")
        add("")
    add("    -- the only writer: the conditional UPDATE and its journal row commit together, and")
    add("    -- the function raises unless exactly one row matched")
    add(f"    FOR r IN SELECT * FROM {table} ORDER BY site_id LOOP")
    add("        moved := moved + apply_remediation_change(")
    add(f"            'unified_sites', {_literal(column)}, 'id', r.site_id::text,")
    add("            r.old_value, r.new_value,")
    add(
        f"            {_literal(lane.test_id)}, {_literal(run_stamp)}, r.change_key, "
        f"{_literal(lane.confidence)}, r.evidence, r.site_id);"
    )
    add("    END LOOP;")
    add("")
    add("    IF moved <> expected THEN")
    add(f"        RAISE EXCEPTION '{label}: % row(s) changed, % planned', moved, expected;")
    add("    END IF;")
    add("")
    add("    -- invariant 1: every planned row now holds the new value")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {table} p JOIN unified_sites u ON u.id = p.site_id")
    add(f"     WHERE u.{column} IS DISTINCT FROM p.new_value;")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION '{label}: % planned row(s) do not hold the new value', bad;")
    add("    END IF;")
    add("")
    add("    -- invariant 2: the journal and the data agree, row for row, in both directions")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {table} p LEFT JOIN remediation_change_log l")
    add("        ON l.row_pk = p.site_id::text AND l.table_name = 'unified_sites'")
    add(f"       AND l.column_name = {_literal(column)}")
    add(f"       AND l.run_stamp = {_literal(run_stamp)}")
    add("     WHERE l.id IS NULL")
    add("        OR l.new_value IS DISTINCT FROM p.new_value")
    add("        OR l.old_value IS DISTINCT FROM p.old_value;")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION '{label}: % planned row(s) have no matching journal row', bad;")
    add("    END IF;")
    add("")
    add("    SELECT count(*) INTO bad FROM remediation_change_log l")
    add("     WHERE l.run_stamp = " + _literal(run_stamp))
    add(f"       AND (l.table_name <> 'unified_sites' OR l.column_name <> {_literal(column)});")
    add("    IF bad > 0 THEN")
    add(
        f"        RAISE EXCEPTION '{label}: this run stamp journalled % row(s) outside "
        f"unified_sites.{column}', bad;"
    )
    add("    END IF;")
    add("")
    add(f"    RAISE NOTICE '{label}: % row(s) changed and journalled over % curated site(s)',")
    add("        moved, expected;")
    add("END $$;")
    add("")
    add("COMMIT;")
    add("")
    add(post_commit_reads(lane, run_stamp=run_stamp, source=source))
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
   AND l.column_name = {column_literal}
   AND EXISTS (SELECT 1 FROM unified_sites u
                WHERE u.id::text = l.row_pk AND u.{column} = l.new_value)
UNION ALL
SELECT {residual_metric}, count(*)::text
  FROM unified_sites
 WHERE source_id = {source} AND {residual_predicate}
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source};
"""


def post_commit_reads(lane: Lane, *, run_stamp: str, source: str = CURATED_SOURCE) -> str:
    """`POST_COMMIT_READS` for one lane: its journal identity, its column, its residual."""
    return POST_COMMIT_READS.format(
        run_stamp=_literal(run_stamp),
        test_id=_literal(lane.test_id),
        source=_literal(source),
        column=lane.column,
        column_literal=_literal(lane.column),
        residual_metric=_literal(lane.post_commit_residual.metric),
        residual_predicate=lane.post_commit_residual.predicate,
    )


#: The post-write read-back as *numbers to be asserted*, not as text to be printed. Read with
#: `-t -A` so the values are parsed, and built from the plan's own rows so it cannot be satisfied by
#: a different 35 rows. `evidence/05_apply.txt` shows why this exists: the journal metric read 0 next
#: to `country = 'Georgia'` = 30, because `VERIFY_SQL` was not an f-string and every placeholder was
#: read as its literal self - and `--apply` printed that without asserting anything about it.
POST_WRITE_ASSERT_SQL = """\
WITH planned(site_id, new_value) AS (VALUES {values})
SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {run_stamp}
UNION ALL
SELECT 'planned rows now holding the planned new value', count(*)::text
  FROM planned p JOIN unified_sites u ON u.id = p.site_id
 WHERE u.{column} IS NOT DISTINCT FROM p.new_value
UNION ALL
SELECT 'planned rows with no journal row for this run stamp', count(*)::text
  FROM planned p LEFT JOIN remediation_change_log l
    ON l.row_pk = p.site_id::text AND l.table_name = 'unified_sites'
   AND l.column_name = {column_literal} AND l.run_stamp = {run_stamp}
 WHERE l.id IS NULL
UNION ALL
SELECT 'journal rows for this run outside unified_sites.{column}', count(*)::text
  FROM remediation_change_log
 WHERE run_stamp = {run_stamp}
   AND (table_name <> 'unified_sites' OR column_name <> {column_literal});
"""


def assert_the_write_landed(
    records: Sequence[ChangeRecord], *, run_stamp: str | None = None, lane: Lane = T05
) -> dict[str, int]:
    """Read the landed state back and refuse unless it is the plan, row for row.

    Read-only, and run after the COMMIT: the journal is counted for this run stamp, every planned
    site is checked against the value the plan names for *that* site, and nothing may be journalled
    outside the lane's column. A mismatch raises, so `--apply` cannot report success over a
    read-back that disagrees with the plan it just wrote.
    """
    if not records:
        raise PlanError("refusing to check the read-back of an empty plan")
    stamp = lane.run_stamp if run_stamp is None else run_stamp
    values = ", ".join(f"({_literal(r.site_id)}::uuid, {_literal(r.new_value)})" for r in records)
    rows = read_rows(
        POST_WRITE_ASSERT_SQL.format(
            values=values,
            run_stamp=_literal(stamp),
            column=lane.column,
            column_literal=_literal(lane.column),
        )
    )
    got = {name.strip(): int(value) for name, value in rows}
    expected = len(records)
    checks = (
        (
            "journal rows for this run stamp",
            expected,
            f"the plan has {expected} row(s)",
        ),
        (
            "planned rows now holding the planned new value",
            expected,
            f"the plan names {expected} row(s)",
        ),
        (
            "planned rows with no journal row for this run stamp",
            0,
            "every planned row is journalled",
        ),
        (
            f"journal rows for this run outside unified_sites.{lane.column}",
            0,
            f"this run stamp journals unified_sites.{lane.column} only",
        ),
    )
    for name, want, why in checks:
        if got.get(name) != want:
            raise PlanError(
                f"the read-back after the write disagrees with the plan: {name} = "
                f"{got.get(name)}, expected {want} ({why})"
            )
    return got


REHEARSAL_READS = """\
-- after ROLLBACK: nothing may have changed
SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {run_stamp}
UNION ALL
SELECT {residual_metric}, count(*)::text
  FROM unified_sites
 WHERE source_id = {source} AND {residual_predicate}
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source}
UNION ALL
-- `{plan_table}` is a CREATE TEMP TABLE, so it lives in this session's `pg_temp_N` schema and
-- `nspname = 'public'` could never match it - the old form of this read was 0 whatever happened.
-- `to_regclass('pg_temp....')` resolves the current session's temp schema and is NULL when the
-- table is gone, so this reads 1 exactly when a leftover exists.
SELECT 'temp table {plan_table} left behind',
       (to_regclass('pg_temp.{plan_table}') IS NOT NULL)::int::text
"""


def rehearsal_reads(lane: Lane, *, run_stamp: str, source: str = CURATED_SOURCE) -> str:
    return REHEARSAL_READS.format(
        run_stamp=_literal(run_stamp),
        source=_literal(source),
        residual_metric=_literal(lane.rehearsal_residual.metric),
        residual_predicate=lane.rehearsal_residual.predicate,
        plan_table=lane.plan_table,
    )


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
 WHERE run_stamp = '{RUN_STAMP}' AND site_id_ref::text IS DISTINCT FROM row_pk
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

#: The read-only verification per lane. T05's is `VERIFY_SQL` above, unchanged since the write it
#: verified (its sha256 is pinned in the tests); the later lanes' texts live in `lane.py`.
READBACKS: dict[str, str] = {T05.name: VERIFY_SQL, **LANE_READBACKS}

ROLLBACK_REHEARSAL_READS = """\
-- after ROLLBACK of the reversal: the reversal must leave nothing behind either
WITH planned(site_id, written) AS (VALUES {values})
SELECT 'journal rows for the rollback stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {rollback_stamp}
UNION ALL
SELECT 'planned rows still holding the written value', count(*)::text
  FROM planned p JOIN unified_sites u ON u.id = p.site_id
 WHERE u.{column} IS NOT DISTINCT FROM p.written
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source}
UNION ALL
SELECT 'temp table {plan_table} left behind',
       (to_regclass('pg_temp.{plan_table}') IS NOT NULL)::int::text
"""


def rollback_rehearsal_reads(records: Sequence[ChangeRecord], lane: Lane = T05) -> str:
    """The reads after a rehearsed reversal, per planned row and the value *that* row was given."""
    values = ", ".join(f"({_literal(r.site_id)}::uuid, {_literal(r.new_value)})" for r in records)
    return ROLLBACK_REHEARSAL_READS.format(
        values=values,
        rollback_stamp=_literal(lane.rollback_run_stamp),
        source=_literal(CURATED_SOURCE),
        column=lane.column,
        plan_table=lane.plan_table,
    )


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


def rehearse(
    sql: str,
    *,
    run_stamp: str | None = None,
    source: str = CURATED_SOURCE,
    lane: Lane = T05,
) -> str:
    """The same statement with `COMMIT` swapped for `ROLLBACK`, plus reads of what must not change.

    The point is to run the identical text - the same guards, the same calls - against
    production without keeping any of it, so a broken guard is found before it is committing.
    """
    head, sep, _ = sql.partition("\nCOMMIT;\n")
    if not sep:
        raise PlanError("the emitted statement has no COMMIT - refusing to rehearse it")
    stamp = lane.run_stamp if run_stamp is None else run_stamp
    return head + "\nROLLBACK;\n" + rehearsal_reads(lane, run_stamp=stamp, source=source)


# --------------------------------------------------------------------------------- transport
def run_psql(
    sql: str, *, host: str = SSH_HOST, timeout: int = 900, rows: bool = False, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Send `sql` to production the way this project does it (`prod_write.send`).

    A timeout raises `OutcomeUnknown` (the COMMIT may or may not have reached the database); a
    non-zero exit raises `PlanError` unless `check=False`, when the caller reads the journal.
    """
    proc = send(sql, host=host, timeout=timeout, rows=rows)
    if check and proc.returncode != 0:
        raise PlanError(f"psql exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}".strip())
    return proc


def read_rows(sql: str) -> list[list[str]]:
    proc = run_psql(sql, rows=True)
    return [line.split("|") for line in proc.stdout.splitlines() if line.strip()]


def journal_count(run_stamp: str) -> int:
    """How many journal rows a run stamp holds - the one question a lost COMMIT is answered by."""
    rows = read_rows(
        f"SELECT count(*) FROM remediation_change_log WHERE run_stamp = {_literal(run_stamp)}"
    )
    if len(rows) != 1 or len(rows[0]) != 1:
        raise PlanError(f"the journal count for {run_stamp!r} came back as {rows!r}")
    return int(rows[0][0])


#: Every session still inside a transaction, other than the one asking. A psql session that ran a
#: lane's script and has not ended shows here until its transaction commits or aborts.
OPEN_SESSIONS_SQL = (
    "SELECT pid, state, now() - xact_start AS open_for, left(query, 60) AS query "
    "FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND xact_start IS NOT NULL "
    "AND application_name = 'psql';"
)


def commit_state(records: Sequence[ChangeRecord], lane: Lane = T05, *, session_ended: bool) -> str:
    """Did the lane's one transaction commit? Read from the journal, never assumed.

    The transaction journals every planned row or none. All of them under the run stamp means it
    COMMITTED: a committed row cannot vanish. None means it did NOT only when `session_ended` - psql
    stopped the script itself (`PSQL_SCRIPT_ERROR`), so the transaction was aborted with its
    session. After a client timeout or a dropped channel the server can still be running the script
    towards its COMMIT, and other sessions cannot see its uncommitted journal rows, so an empty
    journal is not yet an answer. Anything else - a partial journal, a journal that cannot be read -
    is an unknown outcome too, each reported with the queries to run before any retry.
    """
    query = (
        f"SELECT count(*) FROM remediation_change_log WHERE run_stamp = {_literal(lane.run_stamp)};"
    )
    try:
        count = journal_count(lane.run_stamp)
    except (OutcomeUnknown, PlanError) as exc:
        raise OutcomeUnknown(
            f"the journal could not be read either ({exc}). Before any retry run: {query} - the "
            f"write landed only if it reads {len(records)}, and nothing was written if it reads 0"
        ) from exc
    if count == len(records):
        return COMMITTED
    if count == 0 and session_ended:
        return NOT_COMMITTED
    if count == 0:
        raise OutcomeUnknown(
            f"the journal holds 0 rows for {lane.run_stamp!r} so far, but psql did not end the "
            "script itself, and the server may still be running it towards its COMMIT. Before any "
            f"retry: wait until {OPEN_SESSIONS_SQL} lists no session of this write, then run: "
            f"{query} - the write landed only if it reads {len(records)}, and nothing was written "
            "if it reads 0"
        )
    raise OutcomeUnknown(
        f"the journal holds {count} of {len(records)} rows for {lane.run_stamp!r}; one transaction "
        "cannot leave that behind - stop and find out what else wrote under this stamp"
    )


def confirm_committed(records: Sequence[ChangeRecord], lane: Lane, what: str) -> int | None:
    """Read a committed write back: `None` when it is the plan, row for row, else the exit code.

    The write is in the database by the time this runs, so a read-back that fails or disagrees is
    reported as exactly that - COMMITTED BUT NOT CONFIRMED - and never as a refusal, which would
    read as "nothing was sent". `--apply` refuses this run stamp from now on either way.
    """
    try:
        landed = assert_the_write_landed(records, lane=lane)
    except (OutcomeUnknown, PlanError) as exc:
        return committed_unconfirmed(lane, what, exc)
    for name, value in landed.items():
        print(f"  {name}: {value}")
    return None


def committed_unconfirmed(lane: Lane, what: str, exc: Exception) -> int:
    print(
        f"COMMITTED BUT NOT CONFIRMED: {what}; the write is in the database, but its read-back "
        f"did not confirm the plan: {exc}. Run --verify before anything else; --apply refuses "
        f"{lane.run_stamp!r} from now on."
    )
    return EXIT_COMMITTED_UNCONFIRMED


def settle(records: Sequence[ChangeRecord], lane: Lane, what: str, *, session_ended: bool) -> int:
    """After a timeout or a failed psql exit: say from the journal what actually happened."""
    state = commit_state(records, lane, session_ended=session_ended)
    if state == NOT_COMMITTED:
        print(
            f"NOT COMMITTED: {what}, and the journal holds 0 rows for {lane.run_stamp!r} - "
            "nothing was written."
        )
        return EXIT_NOT_COMMITTED
    print(
        f"COMMITTED: {what}, but the journal holds all {len(records)} rows for "
        f"{lane.run_stamp!r} - the transaction committed. Reading it back:"
    )
    unconfirmed = confirm_committed(records, lane, what)
    if unconfirmed is not None:
        return unconfirmed
    print(
        "APPLY LANDED: the read-back matches the plan, row for row; psql did not finish cleanly, "
        "so its own post-commit output is missing - run --verify for the full read-back."
    )
    return EXIT_COMMITTED_UNCLEAN


def _value_rows(lane: Lane) -> list[tuple[str, str, int]]:
    """(value, slug, rows) for every curated value of the lane's column, from the database.

    For the country column the slug is the hub's: the slug function is the pipeline's own, which
    the hub route imports (`api/routes/sites_html.py:25`) and matches rows with - `/sites/{slug}`
    404s once no row's `country` slugs to it, and only redirects a *case variant* of a slug that
    still matches. Other columns have no hub page, so their slug is `-`.
    """
    from pipeline.sites_html_renderer import country_slug

    rows = read_rows(
        f"SELECT {lane.column}, count(*) FROM unified_sites "
        f"WHERE source_id = 'ancient_nerds' GROUP BY {lane.column} ORDER BY {lane.column}"
    )
    return [
        (value, country_slug(value) if lane.column == "country" else "-", int(count))
        for value, count in rows
    ]


def verify_interests(records: Sequence[ChangeRecord], lane: Lane = T05) -> str:
    """The value table (and hub slug) for the values this plan touches - measured, not asserted."""
    wanted = {r.old_value for r in records} | {r.new_value for r in records}
    rows = [row for row in _value_rows(lane) if row[0] in wanted]
    width = max((len(c) for c, _, _ in rows), default=1)
    lines = [f"{lane.column} value".ljust(width) + "  slug                     rows"]
    lines += [f"{value.ljust(width)}  {slug.ljust(23)} {count:>4}" for value, slug, count in rows]
    return "\n".join(lines)


# ------------------------------------------------------------------------------- the commands
def apply_statement(records: Sequence[ChangeRecord], lane: Lane) -> str:
    """The write this plan renders - what `APPLY.sql` must hold below its pin."""
    return render_transaction(
        records, run_stamp=lane.run_stamp, site_ids={r.site_id for r in records}, lane=lane
    )


def rollback_statement(records: Sequence[ChangeRecord], lane: Lane) -> str:
    """The reversal this plan renders - what `ROLLBACK.sql` must hold below its pin."""
    return render_rollback_sql(records, site_ids={r.site_id for r in records}, lane=lane)


def emit(records: Sequence[ChangeRecord], out: Path, lane: Lane = T05, *, plan_path: Path) -> int:
    validate_records(records, lane=lane)
    apply_path = out / "APPLY.sql"
    rollback_path = out / "ROLLBACK.sql"
    if not rollback_path.exists():
        raise PlanError(
            f"{rollback_path} does not exist - the rollback is written before the apply, never after"
        )
    # The undo on disk must be the reversal of *this* plan, unedited: an undo pinned to another
    # plan would be kept next to an apply it does not reverse.
    verify_pinned(rollback_path, plan_path=plan_path, expected=rollback_statement(records, lane))
    apply_path.parent.mkdir(parents=True, exist_ok=True)
    apply_path.write_text(
        pinned(apply_statement(records, lane), plan_sha256(plan_path)),
        encoding="utf-8",
        newline="\n",
    )
    log.info(
        "wrote %s (%d rows); ROLLBACK.sql is %s than APPLY.sql: %s",
        apply_path,
        len(records),
        "older" if rollback_path.stat().st_mtime <= apply_path.stat().st_mtime else "NEWER",
        f"{rollback_path.stat().st_mtime} vs {apply_path.stat().st_mtime}",
    )
    return len(records)


def cmd_rehearse(
    records: Sequence[ChangeRecord], out: Path, lane: Lane = T05, *, plan_path: Path
) -> str:
    sql = verify_pinned(
        out / "APPLY.sql", plan_path=plan_path, expected=apply_statement(records, lane)
    )
    script = rehearse(sql, lane=lane)
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


def cmd_rehearse_rollback(
    records: Sequence[ChangeRecord], out: Path, lane: Lane = T05, *, plan_path: Path
) -> str:
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
    verify_pinned(path, plan_path=plan_path, expected=rollback_statement(records, lane))
    script = head + "\nROLLBACK;\n" + rollback_rehearsal_reads(records, lane)
    target = out / "REHEARSAL_ROLLBACK.sql"
    target.write_text(script, encoding="utf-8", newline="\n")
    log.info("wrote %s (the reversal, COMMIT -> ROLLBACK)", target)
    proc = run_psql(script)
    print(proc.stdout)
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr)
    return proc.stdout


def cmd_apply(
    records: Sequence[ChangeRecord], out: Path, lane: Lane = T05, *, plan_path: Path
) -> int:
    """Send the pinned `APPLY.sql` - only if it is still this plan's - and prove what happened.

    Returns an exit code: `EXIT_OK`; after a timeout or a failed psql exit the journal's answer
    (`EXIT_NOT_COMMITTED`, `EXIT_COMMITTED_UNCLEAN`); after a COMMIT whose read-back fails or
    disagrees `EXIT_COMMITTED_UNCONFIRMED`. An outcome the journal cannot settle raises
    `OutcomeUnknown`. Only a refusal *before* the write raises `PlanError`.
    """
    sql = verify_pinned(
        out / "APPLY.sql", plan_path=plan_path, expected=apply_statement(records, lane)
    )
    already = journal_count(lane.run_stamp)
    if already:
        raise PlanError(
            f"run stamp {lane.run_stamp!r} already journals {already} row(s): this write has "
            "landed, or something else wrote under its stamp - run --verify; never apply twice"
        )
    readback = READBACKS[lane.name]
    print("=== before ===")
    print(run_psql(readback).stdout)
    print(verify_interests(records, lane))
    try:
        proc = run_psql(sql, check=False)
    except OutcomeUnknown as exc:
        return settle(records, lane, f"psql timed out ({exc})", session_ended=False)
    print("=== the write ===")
    print(proc.stdout)
    if proc.stderr.strip():
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        return settle(
            records,
            lane,
            f"psql exited {proc.returncode}",
            session_ended=proc.returncode == PSQL_SCRIPT_ERROR,
        )
    # psql exited 0 with ON_ERROR_STOP after the explicit COMMIT: the write is in the database, and
    # nothing that fails from here on may be reported as a refusal.
    what = "psql exited 0 after the COMMIT"
    print("=== after ===")
    try:
        print(run_psql(readback).stdout)
        print(verify_interests(records, lane))
    except (OutcomeUnknown, PlanError) as exc:
        return committed_unconfirmed(lane, what, exc)
    # Printed above, asserted here: a read-back that disagrees with the plan is no success.
    unconfirmed = confirm_committed(records, lane, what)
    if unconfirmed is not None:
        return unconfirmed
    print("APPLY OK: the read-back matches the plan, row for row")
    return EXIT_OK


def refusal(says: str) -> str:
    """What a guard says after `<label>: <count> ` in psql's ERROR line (guard 1 names the source)."""
    return says.replace("%", CURATED_SOURCE)


def refused_by_its_guard(lane: Lane, says: str, errors: Sequence[str]) -> bool:
    """Whether one of psql's ERROR lines is the lane's refusal `<label>: <count> <says>`."""
    own = re.compile(re.escape(f"{lane.label}: ") + r"\d+ " + re.escape(says))
    return any(own.search(line) for line in errors)


def probe_cases(
    records: Sequence[ChangeRecord], lane: Lane, foreign: Mapping[str, Any]
) -> list[tuple[str, str, list[ChangeRecord], str]]:
    """One corrupted copy of the plan per in-transaction guard, each expected to be refused.

    Every probe corrupts exactly one row and names the refusal its own guard prints (`refusal`):
    the probe is proven only when that text is in psql's ERROR line, so a probe that a later guard,
    the primitive or the column type refuses instead is reported, not counted.

    `foreign` is a row of another source (`id`, `name`, `value` and, for a lane with a premise,
    `premise`), read from production by the caller. Pure, so a test can check that every guard the
    lane renders has its probe.
    """
    first = records[0]
    probes: list[tuple[str, str, list[ChangeRecord], str]] = []

    corrupted_old = list(records)
    corrupted_old[0] = replace(first, old_value="A country that was never there")
    probes.append(
        (
            "guard3-foreign-old-value",
            "guard 3 - a planned old value the row does not hold",
            corrupted_old,
            refusal(GUARD3_SAYS),
        )
    )

    noop = list(records)
    noop[0] = replace(first, new_value=first.old_value)
    probes.append(
        (
            "guard2-no-op",
            "guard 2 - a planned row that is not a change",
            noop,
            refusal(GUARD2_SAYS),
        )
    )

    too_long = list(records)
    too_long[0] = replace(first, new_value="X" * (lane.max_chars + 1))
    probes.append(
        (
            "guard2-too-long",
            "guard 2 - a value longer than the column",
            too_long,
            refusal(GUARD2_SAYS),
        )
    )

    other_source = list(records)
    other_source[0] = ChangeRecord(
        site_id=str(foreign["id"]),
        site_name=str(foreign["name"]),
        old_value=str(foreign["value"]),
        new_value=first.new_value,
        rule="probe",
        condition=f"id = {foreign['id']}",
        reason="probe: a row of another source, which must be refused",
        evidence=({"source": "probe", "quote": "corrupted copy"},),
        premise=None if lane.premise_sql is None else str(foreign["premise"]),
    )
    probes.append(
        (
            "guard1-other-source",
            "guard 1 - a row outside source_id = 'ancient_nerds'",
            other_source,
            refusal(GUARD1_SAYS),
        )
    )

    if lane.allowed_new_values:
        not_owned = list(records)
        not_owned[0] = replace(first, new_value="A value this lane does not own")
        probes.append(
            (
                "guard4-not-owned",
                "guard 4 - a planned value the lane does not own",
                not_owned,
                refusal(GUARD4_SAYS.format(what="write")),
            )
        )

    if lane.premise_sql is not None:
        moved = list(records)
        moved[0] = replace(first, premise="a premise the row never had")
        probes.append(
            (
                "guard5-premise",
                "guard 5 - a row whose premise has changed since the plan",
                moved,
                refusal(GUARD5_SAYS),
            )
        )
    return probes


def cmd_probe_guards(records: Sequence[ChangeRecord], out: Path, lane: Lane = T05) -> int:
    """Corrupt one copy per guard and show, on production, that *that* guard refuses.

    Each probe runs inside `BEGIN ... ROLLBACK` with its own run stamp. It writes nothing: the
    guards fire before the loop, and the failed statement aborts the transaction. A probe counts
    only when psql stopped the script (`PSQL_SCRIPT_ERROR`) with an ERROR line carrying its own
    guard's refusal, and the journal holds no row for its stamp afterwards. Returns the number of
    probes that fell short.
    """
    # Read as JSON: a name may contain the `|` unaligned psql separates fields on.
    premise = f", {lane.premise_sql} AS premise" if lane.premise_sql is not None else ""
    foreign = psql_json_reader()(
        f"SELECT u.id::text AS id, u.name, u.{lane.column}::text AS value{premise} "
        f"FROM unified_sites u WHERE u.source_id <> 'ancient_nerds' "
        f"AND u.{lane.column} IS NOT NULL AND u.{lane.column} <> '' LIMIT 1"
    )
    if not foreign:
        raise PlanError("no non-curated row to probe the source guard with")

    failures = 0
    for suffix, name, mutated, expected in probe_cases(records, lane, foreign[0]):
        stamp = f"{lane.probe_run_stamp}-{suffix}"
        sql = render_transaction(
            mutated,
            run_stamp=stamp,
            site_ids={r.site_id for r in mutated},
            validate=False,
            lane=lane,
        )
        script = rehearse(sql, run_stamp=stamp, source=CURATED_SOURCE, lane=lane)
        proc = run_psql(script, check=False)
        errors = [line.strip() for line in (proc.stdout + proc.stderr).splitlines()]
        errors = [line for line in errors if "ERROR:" in line]
        own = proc.returncode == PSQL_SCRIPT_ERROR and refused_by_its_guard(lane, expected, errors)
        print(f"[{name}] psql exit={proc.returncode} refused by its own guard={own}")
        for line in errors:
            print("   " + line)
        left = journal_count(stamp)
        print(f"   journal rows left by this probe: {left}")
        if not own:
            failures += 1
            print(
                f"   !! {name}: expected psql exit {PSQL_SCRIPT_ERROR} with an ERROR saying "
                f"'{lane.label}: <n> {expected}' - the guard did not refuse this probe itself"
            )
        if left:
            failures += 1
            print(f"   !! {name}: the probe left {left} journal row(s) behind")
    return failures


# ------------------------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply one mechanical lane's plan")
    ap.add_argument(
        "--lane",
        choices=sorted(LANES),
        default=T05.name,
        help="the lane (column, journal identity, owned values); default t05",
    )
    ap.add_argument("--plan", type=Path, help="default: the lane's PLAN.jsonl")
    ap.add_argument("--out", type=Path, help="default: the lane's output directory")
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
        help="read-only: the row count (and hub slug) of every value this plan touches",
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
    lane = LANES[args.lane]
    out = args.out if args.out is not None else lane_dir(lane)
    plan = args.plan if args.plan is not None else out / "PLAN.jsonl"

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        return run(args, lane=lane, out=out, plan=plan, usage=ap.print_help)
    except OutcomeUnknown as exc:
        print(f"OUTCOME UNKNOWN: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN
    except PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED


def run(args: argparse.Namespace, *, lane: Lane, out: Path, plan: Path, usage: Any) -> int:
    """The commands in their fixed order. Only `--emit` writes `APPLY.sql`; every command that
    sends a file sends the one on disk, after proving it is still its plan's."""
    if args.check_primitive:
        print(run_psql(PRIMITIVE_CHECK_SQL).stdout)
        return EXIT_OK
    if args.verify:
        print(run_psql(READBACKS[lane.name]).stdout)
        return EXIT_OK

    records = load_records(plan)
    validate_records(records, lane=lane)

    if args.interests:
        print(verify_interests(records, lane))
        return EXIT_OK
    if args.probe_guards:
        # The number of failed probes is not an exit code: 3 of them would read as NOT COMMITTED.
        return EXIT_PROBE_FAILED if cmd_probe_guards(records, out, lane) else EXIT_OK
    if args.emit:
        emit(records, out, lane, plan_path=plan)
    if args.rehearse:
        cmd_rehearse(records, out, lane, plan_path=plan)
    if args.rehearse_rollback:
        cmd_rehearse_rollback(records, out, lane, plan_path=plan)
    if args.apply:
        return cmd_apply(records, out, lane, plan_path=plan)
    if not any((args.emit, args.rehearse, args.rehearse_rollback)):
        usage()
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
