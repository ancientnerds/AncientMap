"""Row lanes: the transaction of a lane whose cells are rows of other tables (D14, 2026-10-08).

A cell lane (`lane.py`) writes columns of one row per site - `unified_sites`, or `card_stats` keyed by
the site. Merging a duplicate writes rows that carry an id of their own and belong to a site only
through `site_id`: the loser's images and content links move to the survivor, its name row becomes an
alias there. `apply_remediation_change()` takes such a row by `(table, column, key column, key)`, so
the primitive is the same; what differs is the plan - each cell names `(table, row id, column)` and,
beside it, the **site it concerns** - and every guard that a cell lane states as a join on the site
(`u.id = p.site_id`) is stated here per cell with a scalar subquery on the row:

* the **plan's `site_id`** is the site the cell concerns (the loser). It is the journal's
  `site_id_ref`, the curated-scope check and the premise's row - never the row's key;
* **guard 1** - the site is a curated one, and so is the owner of the row the cell names (`site_id`
  of the row), at the time of the write: the row of the loser while it moves, the survivor's while
  it is moved back;
* **guards 2-5** are the cell lane's (`apply.writable_whens` is the one rule of guard 2), the stored
  value of a cell read as `(SELECT t.<column> FROM <table> t WHERE t.id = p.row_id::integer)` and
  compared in the column's own type;
* **row invariants** (`Lane.row_invariants`) count violations over the whole plan after the loop;
  they run on the write only, a reversal restores a state the invariant may never have held.

Everything else - the journal identity, the server bounds, the pin of `APPLY.sql` to its plan, the
rehearsal, the read-back by identity - is `apply.py`'s, which dispatches here for a lane with
`row_cells`. Nothing is added that the cell lane does not already do: this module only says where the
row is.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import apply as A  # noqa: E402
from mechanical.lane import TARGET_KEYS, Lane, outside, written_where  # noqa: E402
from mechanical.lane import sql_literal as _literal  # noqa: E402
from mechanical.plan import CURATED_SOURCE, UUID_RE, PlanError, psql_json_reader  # noqa: E402

#: A row id is the table's serial: a plain positive integer, spelled as the database prints it.
ROW_ID_RE = re.compile(r"^[1-9][0-9]*\Z")
#: The `WHERE`-ready selector of a plan row's cell: what `Lane.row_cells` is looked up by.
SELECTOR = "p.table_name || '.' || p.column_name"


def key_column(lane: Lane) -> str:
    """The one key column of the tables the lane writes (`id` for all three row-keyed tables)."""
    keys = {TARGET_KEYS[cell.table] for cell in lane.row_cells}
    if len(keys) != 1:
        raise PlanError(f"{lane.name}: its tables are keyed by {sorted(keys)}, not one column")
    return keys.pop()


def stored(table: str, column: str, key: str) -> str:
    """SQL: the stored value of one cell - NULL when the row is gone, which no planned value matches."""
    return f"(SELECT t.{column} FROM {table} t WHERE t.id = {key}::integer)"


def typed_row_case(
    lane: Lane,
    value: str,
    *,
    selector: str = SELECTOR,
    key: str = "p.row_id",
    compare: str = "IS DISTINCT FROM",
    otherwise: str = "true",
) -> str:
    """`CASE <table.column> WHEN 'wiki_images.site_id' THEN (stored cell) <compare> <value>::uuid ...`.

    One comparison per cell of the lane, each in its column's own type; CASE because only CASE fixes
    the order the casts are evaluated in (`lane.typed_case`'s reason, kept)."""
    whens = "".join(
        f"\n                WHEN {_literal(cell.qualified)} THEN "
        f"{stored(cell.table, cell.column.name, key)} {compare} {cell.column.cast(value)}"
        for cell in lane.row_cells
    )
    return f"CASE {selector}{whens}\n                ELSE {otherwise} END"


# --------------------------------------------------------------------------------- the records
def validate_records(
    records: Sequence[A.ChangeRecord],
    *,
    source: str = CURATED_SOURCE,
    lane: Lane,
    rollback: bool = False,
) -> None:
    """The plan-side mirror of the row lane's guards. Pure, so a test can break each one."""
    if not records:
        raise PlanError("refusing to validate an empty plan")
    if source != CURATED_SOURCE:
        raise PlanError(f"this lane writes {CURATED_SOURCE!r} only, not {source!r}")
    seen: set[str] = set()
    premises: dict[str, str | None] = {}
    for r in records:
        if not UUID_RE.match(r.site_id):
            raise PlanError(f"{r.site_id!r} is not a UUID")
        if r.table is None or r.row_id is None or r.column is None:
            raise PlanError(
                f"{r.site_id}: a row lane's record names its table, its row id and its column"
            )
        if not ROW_ID_RE.match(r.row_id):
            raise PlanError(f"{r.site_id}: {r.row_id!r} is not a row id")
        try:
            cell = lane.row_cell(r.table, r.column)
        except ValueError as exc:
            raise PlanError(f"{r.site_id}: {exc}") from exc
        key = f"{r.table}/{r.row_id}/{r.column}"
        if key in seen:
            raise PlanError(f"{key} appears twice - the plan is not a set of cells")
        seen.add(key)
        A._validate_value(r, cell.column, lane.name, rollback=rollback)
        if premises.setdefault(r.site_id, r.premise) != r.premise:
            raise PlanError(
                f"{r.site_id}: two premises for one site - every cell of a site is derived from "
                "the same input"
            )
        if r.journal_id is not None:
            raise PlanError(
                f"{r.site_id}: a journal id this statement does not check is a false assurance"
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


def reversed_records(records: Sequence[Any], lane: Lane) -> list[A.ChangeRecord]:
    """The reversal of a row lane's cells: old and new swapped, in reverse order, the row kept."""
    return [
        A.ChangeRecord(
            site_id=r.site_id,
            site_name=r.site_name,
            old_value=r.new_value,
            new_value=r.old_value,
            rule=f"rollback-{r.rule}",
            condition=f"{key_column(lane)} = {r.row_id} AND {r.column} IS NOT DISTINCT FROM "
            f"{_literal(r.new_value)}",
            reason=f"rollback of {lane.key_prefix}: {r.table}.{r.column} of row {r.row_id} "
            f"{r.old_value!r} restored for {r.site_name}",
            evidence=tuple(r.evidence),
            phase3=r.phase3,
            premise=r.premise,
            column=r.column,
            table=r.table,
            row_id=r.row_id,
        )
        for r in reversed(list(records))
    ]


def _ordered(records: Iterable[A.ChangeRecord]) -> list[A.ChangeRecord]:
    return sorted(records, key=lambda r: (str(r.table), int(str(r.row_id)), str(r.column)))


# ----------------------------------------------------------------------------------- rendering
def render_transaction(
    records: Sequence[A.ChangeRecord],
    *,
    run_stamp: str | None = None,
    site_ids: Iterable[str],
    source: str = CURATED_SOURCE,
    validate: bool = True,
    rollback: bool = False,
    lane: Lane,
) -> str:
    """One transaction that writes `records` and journals each cell, or writes nothing.

    The same transaction as a cell lane's (`apply.render_transaction`), cell by cell:
    `validate=False` is for `--probe-guards` only, `rollback=True` renders the reversal with its own
    change keys and its own stamp, and the row invariants run on the write alone.
    """
    records = list(records)
    if not records:
        raise PlanError("refusing to render a transaction with no rows")
    if validate:
        validate_records(records, source=source, lane=lane, rollback=rollback)
    if run_stamp is None:
        run_stamp = lane.rollback_run_stamp if rollback else lane.run_stamp
    key_of = lane.row_rollback_change_key if rollback else lane.row_change_key
    table, label = lane.plan_table, lane.label
    premise = lane.premise_sql is not None
    pk = key_column(lane)
    sites = sorted({str(s) for s in site_ids})
    out: list[str] = []
    add = out.append
    add("-- Generated by scripts/remediation/mechanical/apply.py - do not edit by hand.")
    add(
        f"-- {len(records)} cell(s) of rows in {written_where(lane)} over {len(sites)} site(s); "
        f"scope source_id = {_literal(source)};"
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
    add("    site_id     UUID NOT NULL,")
    add("    table_name  TEXT NOT NULL,")
    add("    row_id      TEXT NOT NULL,")
    add("    column_name TEXT NOT NULL,")
    add("    old_value   TEXT,")
    add("    new_value   TEXT,")
    add("    change_key  TEXT NOT NULL,")
    add("    reason      TEXT NOT NULL,")
    if premise:
        add("    premise     TEXT NOT NULL,")
    add("    evidence    JSONB NOT NULL,")
    add("    PRIMARY KEY (table_name, row_id, column_name)")
    add(") ON COMMIT DROP;")
    add("")
    premise_column = " premise," if premise else ""
    add(
        f"INSERT INTO {table} (site_id, table_name, row_id, column_name, old_value, new_value, "
        f"change_key, reason,{premise_column} evidence) VALUES"
    )
    rows = []
    for r in _ordered(records):
        premise_value = f"{_literal(r.premise)}, " if premise else ""
        rows.append(
            "    ("
            f"{_literal(r.site_id)}::uuid, {_literal(r.table)}, {_literal(r.row_id)}, "
            f"{_literal(r.column)}, {_literal(r.old_value)}, {_literal(r.new_value)}, "
            f"{_literal(key_of(str(r.table), str(r.row_id), str(r.column)))}, "
            f"{_literal(r.reason)}, {premise_value}"
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
    add(
        "    -- expected is the plan's own cell count, rendered here, and not a second count of the"
    )
    add(
        "    -- temp table the loop below iterates (a tautology otherwise); apply_remediation_change"
    )
    add(
        "    -- raises unless exactly one row matched, this guard reports a loop that changed fewer."
    )
    add("")
    owned = " ".join(
        f"WHEN {_literal(cell.table)} THEN EXISTS (SELECT 1 FROM {cell.table} t JOIN unified_sites o "
        f"ON o.id = t.site_id WHERE t.{pk} = p.row_id::integer AND o.source_id = {_literal(source)})"
        for cell in {c.table: c for c in lane.row_cells}.values()
    )
    add(
        "    -- scope guard 1: every planned cell concerns a curated site, and the row it names exists"
    )
    add("    -- and belongs to a curated site now")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {table} p LEFT JOIN unified_sites u ON u.id = p.site_id")
    add(f"     WHERE u.id IS NULL OR u.source_id <> {_literal(source)}")
    add(f"        OR NOT (CASE p.table_name {owned} ELSE false END);")
    add("    IF bad > 0 THEN")
    add("        -- the source name is a RAISE argument, never part of the quoted message")
    add(f"        RAISE EXCEPTION '{label}: % {A.GUARD1_SAYS}', bad, {_literal(source)};")
    add("    END IF;")
    add("")
    add("    -- scope guard 2: the plan is a set of real changes, each one writable in its column")
    add(f"    SELECT count(*) INTO bad FROM {table} p")
    whens = A.writable_whens(
        [(cell.qualified, cell.column) for cell in lane.row_cells], rollback=rollback
    )
    add(
        f"     WHERE p.new_value = '' OR CASE {SELECTOR}"
        + "".join(whens)
        + "\n                ELSE true END;"
    )
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION '{label}: % {A.GUARD2_SAYS}', bad;")
    add("    END IF;")
    add("")
    add("    -- scope guard 3: every planned cell still holds the old value the plan names")
    add(f"    SELECT count(*) INTO bad FROM {table} p")
    add(f"     WHERE {typed_row_case(lane, 'p.old_value')};")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION '{label}: % {A.GUARD3_SAYS}', bad;")
    add("    END IF;")
    add("")
    owned_cells = [cell for cell in lane.row_cells if cell.column.allowed_new_values]
    if owned_cells:
        lane_side = "p.old_value" if rollback else "p.new_value"
        what = "undo" if rollback else "write"
        add(
            f"    -- scope guard 4: every planned cell {what}s a value this lane owns "
            f"({'old' if rollback else 'new'} value)"
        )
        guard4 = "".join(
            f"\n                WHEN {_literal(cell.qualified)} THEN {lane_side} NOT IN ("
            + ", ".join(_literal(v) for v in cell.column.allowed_new_values)
            + ")"
            for cell in owned_cells
        )
        add(f"    SELECT count(*) INTO bad FROM {table} p")
        add(f"     WHERE CASE {SELECTOR}{guard4}\n                ELSE false END;")
        add("    IF bad > 0 THEN")
        add(f"        RAISE EXCEPTION '{label}: % {A.GUARD4_SAYS.format(what=what)}', bad;")
        add("    END IF;")
        add("")
    if premise:
        add(
            "    -- scope guard 5: every planned site still holds the input its value was derived from"
        )
        add("    SELECT count(*) INTO bad")
        add(
            f"      FROM (SELECT DISTINCT site_id, premise FROM {table}) p "
            "JOIN unified_sites u ON u.id = p.site_id"
        )
        add(f"     WHERE ({lane.premise_sql}) IS DISTINCT FROM p.premise;")
        add("    IF bad > 0 THEN")
        add(f"        RAISE EXCEPTION '{label}: % {A.GUARD5_SAYS}', bad;")
        add("    END IF;")
        add("")
    add("    -- the only writer: the conditional UPDATE and its journal row commit together, and")
    add("    -- the function raises unless exactly one row matched")
    add(
        f"    FOR r IN SELECT * FROM {table} ORDER BY table_name, row_id::integer, column_name LOOP"
    )
    add("        moved := moved + apply_remediation_change(")
    add(f"            r.table_name, r.column_name, {_literal(pk)}, r.row_id,")
    add("            r.old_value, r.new_value,")
    add(
        f"            {_literal(lane.test_id)}, {_literal(run_stamp)}, r.change_key, "
        f"{_literal(lane.confidence)}, r.evidence, r.site_id);"
    )
    add("    END LOOP;")
    add("")
    add("    IF moved <> expected THEN")
    add(f"        RAISE EXCEPTION '{label}: % cell(s) changed, % planned', moved, expected;")
    add("    END IF;")
    add("")
    add("    -- invariant 1: every planned cell now holds the new value")
    add(f"    SELECT count(*) INTO bad FROM {table} p")
    add(f"     WHERE {typed_row_case(lane, 'p.new_value')};")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION '{label}: % planned cell(s) do not hold the new value', bad;")
    add("    END IF;")
    add("")
    add("    -- invariant 2: the journal and the data agree, cell for cell, in both directions")
    add("    SELECT count(*) INTO bad")
    add(f"      FROM {table} p LEFT JOIN remediation_change_log l")
    add("        ON l.row_pk = p.row_id AND l.table_name = p.table_name")
    add("       AND l.column_name = p.column_name")
    add(f"       AND l.run_stamp = {_literal(run_stamp)}")
    add("     WHERE l.id IS NULL")
    add("        OR l.new_value IS DISTINCT FROM p.new_value")
    add("        OR l.old_value IS DISTINCT FROM p.old_value")
    add("        OR l.site_id_ref IS DISTINCT FROM p.site_id;")
    add("    IF bad > 0 THEN")
    add(f"        RAISE EXCEPTION '{label}: % planned cell(s) have no matching journal row', bad;")
    add("    END IF;")
    add("")
    add("    SELECT count(*) INTO bad FROM remediation_change_log l")
    add("     WHERE l.run_stamp = " + _literal(run_stamp))
    add(f"       AND {outside(lane, 'l.')};")
    add("    IF bad > 0 THEN")
    add(
        f"        RAISE EXCEPTION '{label}: this run stamp journalled % row(s) outside "
        f"{written_where(lane)}', bad;"
    )
    add("    END IF;")
    add("")
    for invariant in () if rollback else lane.row_invariants:
        add(f"    -- row invariant: the plan may not leave this - {invariant.says}")
        add("    SELECT count(*) INTO bad")
        add(f"      {invariant.bad_sql.replace('{plan}', table)};")
        add("    IF bad > 0 THEN")
        add(f"        RAISE EXCEPTION '{label}: % {invariant.says}', bad;")
        add("    END IF;")
        add("")
    add(
        f"    RAISE NOTICE '{label}: % of % planned cell(s) changed and journalled over "
        f"{len(sites)} curated site(s)',"
    )
    add("        moved, expected;")
    add("END $$;")
    block = "\n".join(out).partition("\nDO $$\n")[2].rpartition("\nEND $$;")[0]
    if "$$" in block:
        raise PlanError(f"{lane.name}: a value spliced into the statement would end the DO block")
    add("")
    add("COMMIT;")
    add("")
    add(post_commit_reads(lane, run_stamp=run_stamp, source=source))
    return "\n".join(out)


# ----------------------------------------------------------------------------- the read-backs
POST_COMMIT_READS = """\
-- Post-commit read: the numbers the report quotes, from the database, not from the plan.
SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {run_stamp}
UNION ALL
SELECT 'journal rows for this test id', count(*)::text
  FROM remediation_change_log WHERE test_id = {test_id}
UNION ALL
SELECT 'planned cells now holding the new value', count(*)::text
  FROM remediation_change_log p
 WHERE p.run_stamp = {run_stamp}
   AND ({holds})
UNION ALL
SELECT {residual_metric}, count(*)::text
  FROM unified_sites
 WHERE source_id = {source} AND {residual_predicate}
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source};
"""


def _journal_selector() -> str:
    return "p.table_name || '.' || p.column_name"


def post_commit_reads(lane: Lane, *, run_stamp: str, source: str = CURATED_SOURCE) -> str:
    """The row lane's `POST_COMMIT_READS`: the journal rows of its stamp and the cells now holding
    what they wrote (read through the journal, which names each cell by table, column and row)."""
    holds = typed_row_case(
        lane,
        "p.new_value",
        key="p.row_pk",
        compare="IS NOT DISTINCT FROM",
        otherwise="false",
    )
    return POST_COMMIT_READS.format(
        run_stamp=_literal(run_stamp),
        test_id=_literal(lane.test_id),
        source=_literal(source),
        holds=holds,
        residual_metric=_literal(lane.post_commit_residual.metric),
        residual_predicate=lane.post_commit_residual.predicate,
    )


def _planned_values(records: Sequence[A.ChangeRecord], value: str) -> tuple[str, str]:
    """`(columns, VALUES rows)` naming each planned cell with `value`: what a read-back compares
    the database against, cell for cell."""
    rows = ", ".join(
        f"({_literal(r.table)}, {_literal(r.row_id)}, {_literal(r.column)}, "
        f"{_literal(r.new_value)})"
        for r in records
    )
    return f"table_name, row_id, column_name, {value}", rows


ASSERT_SQL = """\
WITH planned({planned}) AS (VALUES {values})
SELECT 'journal rows for this run stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {run_stamp}
UNION ALL
SELECT 'planned cells now holding the planned new value', count(*)::text
  FROM planned p
 WHERE {holds}
UNION ALL
SELECT 'planned cells with no journal row for this run stamp', count(*)::text
  FROM planned p LEFT JOIN remediation_change_log l
    ON l.row_pk = p.row_id AND l.table_name = p.table_name
   AND l.column_name = p.column_name AND l.run_stamp = {run_stamp}
 WHERE l.id IS NULL
UNION ALL
SELECT 'journal rows for this run outside {where}', count(*)::text
  FROM remediation_change_log l
 WHERE l.run_stamp = {run_stamp}
   AND {outside};
"""


def assert_the_write_landed(
    records: Sequence[A.ChangeRecord], *, run_stamp: str | None = None, lane: Lane
) -> dict[str, int]:
    """Read the landed state back and refuse unless it is the plan, cell for cell (read-only)."""
    if not records:
        raise PlanError("refusing to check the read-back of an empty plan")
    stamp = lane.run_stamp if run_stamp is None else run_stamp
    planned, values = _planned_values(records, "new_value")
    rows = A.read_rows(
        ASSERT_SQL.format(
            planned=planned,
            values=values,
            run_stamp=_literal(stamp),
            holds=typed_row_case(
                lane, "p.new_value", compare="IS NOT DISTINCT FROM", otherwise="false"
            ),
            where=written_where(lane),
            outside=outside(lane, "l."),
        )
    )
    got = {name.strip(): int(value) for name, value in rows}
    expected = len(records)
    checks = (
        ("journal rows for this run stamp", expected, f"the plan has {expected} cell(s)"),
        (
            "planned cells now holding the planned new value",
            expected,
            f"the plan names {expected} cell(s)",
        ),
        (
            "planned cells with no journal row for this run stamp",
            0,
            "every planned cell is journalled",
        ),
        (
            f"journal rows for this run outside {written_where(lane)}",
            0,
            f"this run stamp journals {written_where(lane)} only",
        ),
    )
    for name, want, why in checks:
        if got.get(name) != want:
            raise PlanError(
                f"the read-back after the write disagrees with the plan: {name} = "
                f"{got.get(name)}, expected {want} ({why})"
            )
    return got


ROLLBACK_REHEARSAL_READS = """\
-- after ROLLBACK of the reversal: the reversal must leave nothing behind either
WITH planned({planned}) AS (VALUES {values})
SELECT 'journal rows for the rollback stamp' AS metric, count(*)::text AS value
  FROM remediation_change_log WHERE run_stamp = {rollback_stamp}
UNION ALL
SELECT 'planned cells still holding the written value', count(*)::text
  FROM planned p
 WHERE {holds}
UNION ALL
SELECT 'curated sites', count(*)::text
  FROM unified_sites WHERE source_id = {source}
UNION ALL
SELECT 'temp table {plan_table} left behind',
       (to_regclass('pg_temp.{plan_table}') IS NOT NULL)::int::text
"""


def rollback_rehearsal_reads(records: Sequence[A.ChangeRecord], lane: Lane) -> str:
    """The reads after a rehearsed reversal, per planned cell and the value *that* cell was given."""
    planned, values = _planned_values(records, "written")
    return ROLLBACK_REHEARSAL_READS.format(
        planned=planned,
        values=values,
        rollback_stamp=_literal(lane.rollback_run_stamp),
        source=_literal(CURATED_SOURCE),
        holds=typed_row_case(lane, "p.written", compare="IS NOT DISTINCT FROM", otherwise="false"),
        plan_table=lane.plan_table,
    )


def verify_interests(records: Sequence[A.ChangeRecord], lane: Lane) -> str:
    """What the plan touches, measured - the images, links and names of every site it names, as the
    database holds them now (the sites a cell leaves and the sites it reaches)."""
    sites = {r.site_id for r in records}
    sites |= {
        str(v) for r in records if r.column == "site_id" for v in (r.old_value, r.new_value) if v
    }
    listed = ", ".join(_literal(s) for s in sorted(sites))
    rows = psql_json_reader()(
        "SELECT u.id::text AS site_id, u.name, "
        "(SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS images, "
        "(SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id AND w.is_hero IS TRUE "
        "AND w.is_excluded IS NOT TRUE) AS heroes, "
        "(SELECT count(*) FROM site_content_links c WHERE c.site_id = u.id) AS links, "
        "(SELECT count(*) FROM unified_site_names n WHERE n.site_id = u.id) AS names "
        f"FROM unified_sites u WHERE u.id::text IN ({listed}) ORDER BY u.name, u.id"
    )
    lines = ["images heroes links names  site"]
    lines += [
        f"{int(row['images']):>6} {int(row['heroes']):>6} {int(row['links']):>5} "
        f"{int(row['names']):>5}  {row['name']} ({row['site_id']})"
        for row in rows
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------- probes
ProbeResult = list[A.ChangeRecord] | None


def flipped(value: str | None, sql_type: str) -> str:
    """A value the cell does not hold: the other boolean, else the type's never-stored value."""
    if sql_type == "boolean":
        return "false" if value == "true" else "true"
    return A.NEVER_STORED[sql_type]


def _site_cells(records: Sequence[A.ChangeRecord]) -> dict[str, list[int]]:
    """The indices of the `site_id` cells (the moves) of each site the plan names."""
    out: dict[str, list[int]] = {}
    for index, r in enumerate(records):
        if r.column == "site_id":
            out.setdefault(r.site_id, []).append(index)
    return out


def redirect(records: Sequence[A.ChangeRecord], destination: str) -> ProbeResult:
    """Every move of the first site that has one and neither leaves nor reaches `destination`,
    sent to `destination` instead (a move that already points there would be a no-op, which guard 2
    refuses before the destination guard is asked - the retired probe row is itself a loser)."""
    moves = _site_cells(records)
    movable = [
        site
        for site in sorted(moves)
        if all(destination not in (records[i].old_value, records[i].new_value) for i in moves[site])
    ]
    if not movable:
        return None
    mutated = list(records)
    for index in moves[movable[0]]:
        mutated[index] = replace(mutated[index], new_value=destination)
    return mutated


#: A production row each destination probe sends a move to. Read 2026-10-01 (`lane.py`): a GeoNames
#: row, a retired duplicate, and a curated site 364 km or more from any loser.
GEONAMES_ROW = "8db5555a-a9a3-417b-944c-6ec0c04de0db"
RETIRED_ROW = "04d8ce82-4fa3-4e48-88b7-bb41b354260c"
FAR_ROW = "30d3fb78-6b80-42f9-87f8-7616e63bec4f"


def drop_first(records: Sequence[A.ChangeRecord], column: str, table: str | None) -> ProbeResult:
    """The plan without its first cell of `column` (of `table` when named)."""
    index = next(
        (
            i
            for i, r in enumerate(records)
            if r.column == column and (table is None or r.table == table)
        ),
        None,
    )
    if index is None or len(records) == 1:
        return None
    return [r for i, r in enumerate(records) if i != index]


def drop_hero_cell(records: Sequence[A.ChangeRecord], lane: Lane) -> ProbeResult:
    """A moved hero left a hero: without the cell that demotes it, the survivor has two."""
    return drop_first(records, "is_hero", "wiki_images")


def drop_alias_cells(records: Sequence[A.ChangeRecord], lane: Lane) -> ProbeResult:
    """The loser's name row left on the loser: its survivor never gets the alias."""
    site = next((r.site_id for r in records if r.table == "unified_site_names"), None)
    if site is None:
        return None
    kept = [r for r in records if not (r.site_id == site and r.table == "unified_site_names")]
    return kept or None


PROBES: Mapping[str, Any] = {
    "dest-curated": lambda records, lane: redirect(records, GEONAMES_ROW),
    "dest-shown": lambda records, lane: redirect(records, RETIRED_ROW),
    "dest-named-near": lambda records, lane: redirect(records, FAR_ROW),
    "hero-cell": drop_hero_cell,
    "alias-cells": drop_alias_cells,
}


def probe_cases(
    records: Sequence[A.ChangeRecord], lane: Lane, foreign: Mapping[str, Any]
) -> list[tuple[str, str, list[A.ChangeRecord], str]]:
    """One corrupted copy of the plan per in-transaction guard, each expected to be refused by its
    own guard (`apply.refusal`). `foreign` is a row of another source: `{table, row_id, site_id,
    name}` and, for a lane with a premise, `premise` (read by `foreign_row`)."""
    # A boolean has two values: flipping the old value of a cell that goes true -> false is a no-op
    # that guard 2 refuses first, so the probes corrupt the first cell of any other type.
    start = next(
        (
            i
            for i, r in enumerate(records)
            if lane.row_cell(r.table, r.column).column.sql_type != "boolean"
        ),
        0,
    )
    first = records[start]
    cell = lane.row_cell(first.table, first.column)

    def corrupt(index: int, **change: Any) -> list[A.ChangeRecord]:
        mutated = list(records)
        mutated[index] = replace(records[index], **change)
        return mutated

    probes: list[tuple[str, str, list[A.ChangeRecord], str]] = [
        (
            "guard3-foreign-old-value",
            "guard 3 - a planned old value the cell does not hold",
            corrupt(start, old_value=flipped(first.old_value, cell.column.sql_type)),
            A.refusal(A.GUARD3_SAYS),
        ),
        (
            "guard2-no-op",
            "guard 2 - a planned cell that is not a change",
            corrupt(start, new_value=first.old_value),
            A.refusal(A.GUARD2_SAYS),
        ),
        (
            "guard2-foreign-column",
            "guard 2 - a cell in a column the lane does not own",
            corrupt(start, column="probe_foreign_column"),
            A.refusal(A.GUARD2_SAYS),
        ),
    ]
    wide = next(
        (
            i
            for i, r in enumerate(records)
            if lane.row_cell(r.table, r.column).column.max_chars is not None
        ),
        None,
    )
    if wide is not None:
        width = lane.row_cell(records[wide].table, records[wide].column).column.max_chars or 0
        probes.append(
            (
                "guard2-too-long",
                "guard 2 - a value longer than its column",
                corrupt(wide, new_value="X" * (width + 1)),
                A.refusal(A.GUARD2_SAYS),
            )
        )
    probes.append(
        (
            "guard1-other-source",
            f"guard 1 - a {first.table} row of a site outside source_id = 'ancient_nerds'",
            corrupt(
                start,
                site_id=str(foreign["site_id"]),
                site_name=str(foreign["name"]),
                table=str(foreign["table"]),
                row_id=str(foreign["row_id"]),
                condition=f"id = {foreign['row_id']}",
                reason="probe: a row of another source, which must be refused",
                evidence=({"source": "probe", "quote": "corrupted copy"},),
                premise=None if lane.premise_sql is None else str(foreign["premise"]),
            ),
            A.refusal(A.GUARD1_SAYS),
        )
    )
    owned = next(
        (
            i
            for i, r in enumerate(records)
            if lane.row_cell(r.table, r.column).column.allowed_new_values
            and lane.row_cell(r.table, r.column).column.sql_type != "boolean"
        ),
        None,
    )
    if owned is not None:
        owned_type = lane.row_cell(records[owned].table, records[owned].column).column.sql_type
        probes.append(
            (
                "guard4-not-owned",
                "guard 4 - a planned value the lane does not own",
                corrupt(owned, new_value=A.NOT_OWNED[owned_type]),
                A.refusal(A.GUARD4_SAYS.format(what="write")),
            )
        )
    if lane.premise_sql is not None:
        probes.append(
            (
                "guard5-premise",
                "guard 5 - a site whose premise has changed since the plan",
                corrupt(start, premise="a premise the row never had"),
                A.refusal(A.GUARD5_SAYS),
            )
        )
    for invariant in lane.row_invariants:
        mutated = PROBES[invariant.probe](records, lane)
        if mutated is not None:
            probes.append(
                (
                    f"invariant-{invariant.probe}",
                    f"row invariant - {invariant.says}",
                    mutated,
                    A.refusal(invariant.says),
                )
            )
    return probes


def unprobed_invariants(records: Sequence[A.ChangeRecord], lane: Lane) -> list[str]:
    """The row invariants this plan cannot probe: it holds no cell the probe could corrupt."""
    return [i.says for i in lane.row_invariants if PROBES[i.probe](records, lane) is None]


def foreign_row(lane: Lane, table: str) -> dict[str, Any]:
    """A row of `table` that belongs to a site outside the curated source (read-only), with its
    site's name and - for a lane with a premise - the premise the database prints for that site."""
    premise = f", {lane.premise_sql} AS premise" if lane.premise_sql is not None else ""
    rows = psql_json_reader()(
        f"SELECT '{table}' AS \"table\", t.id::text AS row_id, u.id::text AS site_id, u.name"
        f"{premise} FROM {table} t JOIN unified_sites u ON u.id = t.site_id "
        f"WHERE u.source_id <> {_literal(CURATED_SOURCE)} LIMIT 1"
    )
    if not rows:
        raise PlanError(f"no {table} row of a non-curated site to probe the source guard with")
    return rows[0]


# ------------------------------------------------------------------------------------ the plan
def plan_record(change: Any, plan: Any) -> dict[str, Any]:
    """One `PLAN.jsonl` line of a row lane: the cell (`row_table`, `row_id`, `column`), the site it
    concerns, the lane's journal identity and the evidence. `plan.plan_record` dispatches here."""
    lane = plan.lane
    if change.table is None or change.row_id is None or change.column is None:
        raise PlanError(f"{change.site_id}: a row lane's change names its table, row and column")
    lane.row_cell(change.table, change.column)
    if not ROW_ID_RE.match(change.row_id):
        raise PlanError(f"{change.site_id}: {change.row_id!r} is not a row id")
    record: dict[str, Any] = {
        "site_id": change.site_id,
        "site_name": change.site_name,
        "row_table": change.table,
        "row_id": change.row_id,
        "column": change.column,
        "key_column": key_column(lane),
        "old_value": change.old_value,
        "new_value": change.new_value,
        "rule": change.rule,
        "condition": f"{key_column(lane)} = {change.row_id} AND {change.column} IS NOT DISTINCT "
        f"FROM {_literal(change.old_value)}",
        "reason": f"{lane.key_prefix} ({change.rule}): {change.note}",
        "change_key": lane.row_change_key(change.table, change.row_id, change.column),
        "test_id": plan.test_id,
        "run_stamp": plan.run_stamp,
        "confidence": lane.confidence,
        "source_id": plan.source_id,
        "phase3": change.phase3,
        "finding_test_id": change.finding_test_id,
        "evidence": list(change.evidence),
    }
    if lane.premise_sql is not None:
        if change.premise is None:
            raise PlanError(f"{change.site_id}: the {lane.name} lane needs the site's premise")
        record["premise"] = change.premise
    return record
