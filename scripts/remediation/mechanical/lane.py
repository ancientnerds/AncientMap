"""The mechanical lanes: one write path, several columns, each with its own journal identity.

`apply.py` renders, rehearses, probes and applies a plan through `apply_remediation_change()`, one
conditional UPDATE plus one journal row per planned row, all in one transaction. Nothing in that path
depends on *which* repair the plan is, except what a `Lane` names:

* the column it writes and that column's declared width (a longer value is an error, never a
  truncation - measured with `information_schema.columns` on production, 2026-09-22:
  `unified_sites.country`, `period_name` and `site_type` are all `character varying(100)`);
* the journal identity - run stamp, test id, confidence and the `change_key` prefix - so the read-back
  can count exactly this lane's rows and a reversal is a transition of its own;
* the values the lane owns (`allowed_new_values`): when it is non-empty the transaction carries a
  fourth scope guard, and the plan-side mirror a fourth check, refusing any planned value outside it;
* `premise_sql`, the live input the plan derived its value from. When it is set, every planned row
  carries that input as text and a fifth guard refuses the transaction if the row no longer holds it:
  a derived value is only right while what it was derived from is unchanged;
* `lock_timeout` and `statement_timeout`, the transaction's server-side bounds (2026-09-23). A
  client timeout or a dropped ssh channel does not stop the server: psql has the whole script on
  its stdin and runs it to the `COMMIT` after the client gave up (measured on the VPS: the remote
  psql ran the next statement 17 s after the client ssh was killed). Bounded on the server, a lock
  wait or a runaway statement raises inside the transaction instead - psql stops the script
  (exit 3) and nothing is kept, well inside the client's 900 s;
* the residual predicates the read-backs print, and the output directory.

## Two shapes: a column lane and a cell lane (2026-09-23)

A lane is a `(table, key column, value column, curated-scope predicate)`:

* **The target** (`Target`) is the table `apply_remediation_change()` writes and its key column.
  The plan's key is always a site id - `unified_sites.id`, or a table keyed by it
  (`card_stats.site_id`) - and the **curated-scope predicate** is the site's `source_id`, tested on
  `u`: the written row itself on `unified_sites`, the site the row belongs to on any other table.
* **A column lane** writes one `unified_sites` column (`column`, `max_chars`,
  `allowed_new_values`), and its records do not name it. The four lanes of 2026-09-21/22 are column
  lanes, and their statements are pinned by sha256 in `tests/remediation/test_mechanical.py`: the
  generalisation below renders them byte for byte as before.
* **A cell lane** (`cells`) writes several columns of one target in one transaction, and every
  record names its column: `card_stats` (the generator's twelve columns), `scope_status` with
  `scope_reason`, a list of journal rows to reverse. Each `Column` carries the type its planned
  text is compared in (`p.old_value::integer`), its width, the values it owns and whether its old
  value may be NULL (a column the lane *fills*, whose reversal restores the NULL).

T05 is the country lane that was applied on 2026-09-21. Its rendering is pinned byte for byte in
`tests/remediation/test_mechanical.py` (sha256 of `APPLY.sql`/`ROLLBACK.sql` rendered from the
delivered plan), so it carries no fourth or fifth guard and no server bounds: `allowed_new_values=()`,
`premise_sql=None` and no timeouts render exactly the statement that was rehearsed and written.

A leaf module: it imports nothing from `plan.py` or `apply.py`, so both can import it. It does
import the pipeline's own vocabularies a lane owns (the period buckets, the canonical site types,
the scope vocabulary), so they are never copied. The card_stats lanes
live in `card_stats.py`, which imports the card generator: `resolve_lane` reaches them lazily, so
this module - and every lane that does not write card_stats - never imports the API package.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from pipeline.normalizers.site_type import CANONICAL_TYPES
from pipeline.utils.public_sites import SCOPE_STATUSES
from pipeline.utils.text import PERIOD_BUCKETS

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
#: The label is spliced into RAISE message literals: no quote (it would end the literal) and no `%`
#: (it would be read as a placeholder and consume an argument).
_LABEL = re.compile(r"^[A-Za-z0-9 _/-]+$")
_KEY_PREFIX = re.compile(r"^[a-z0-9-]+$")
#: A Postgres duration as `SET LOCAL ... = '<value>'` takes it: digits and a unit, nothing else.
_DURATION = re.compile(r"^[1-9][0-9]*(ms|s|min)$")


def sql_literal(value: str | None) -> str:
    """A SQL string literal, quotes doubled; `None` is `NULL`. The one quoting rule of the lane."""
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class Residual:
    """A count the read-backs print: what the lane exists to remove, read from the database."""

    metric: str
    predicate: str


#: The tables a lane may write, each with its key column. Both keys are a site id, which is what
#: makes the curated-scope predicate (`u.source_id`) and the journal's `site_id_ref` one rule for
#: every lane. `apply_remediation_change()` allows four more tables; their keys are not site ids.
TARGET_KEYS = {"unified_sites": "id", "card_stats": "site_id"}

#: The types a cell's planned text is cast to before it is compared with the stored value - the
#: base types of the columns the cell lanes write (read from the catalog on production,
#: 2026-09-23). Spliced into SQL as `::<type>`, so the set is closed.
CELL_TYPES = frozenset({"integer", "jsonb", "text", "character varying"})


@dataclass(frozen=True)
class Target:
    """The table a lane writes, its key column, and the alias the rendered guards give the row.

    The plan's key is always a site id. The **curated-scope predicate** is that site's
    `source_id`, read on `u`: the written row itself when the target is `unified_sites`, the site
    the written row belongs to (`u.id = p.site_id`) on any other table.
    """

    table: str
    key_column: str
    alias: str

    def __post_init__(self) -> None:
        if TARGET_KEYS.get(self.table) != self.key_column:
            raise ValueError(
                f"{self.table}.{self.key_column} is not a target: a lane writes "
                + ", ".join(f"{t}.{k}" for t, k in sorted(TARGET_KEYS.items()))
            )
        if not _IDENTIFIER.match(self.alias) or (self.alias == "u") != self.is_site:
            raise ValueError(f"{self.alias!r}: `u` is the site, and only the site")

    @property
    def is_site(self) -> bool:
        """Whether the written row is the curated site itself."""
        return self.table == "unified_sites"


UNIFIED_SITES = Target("unified_sites", "id", "u")
CARD_STATS = Target("card_stats", "site_id", "t")


@dataclass(frozen=True)
class Column:
    """One column a cell lane writes, and how its planned text meets the stored value.

    `sql_type` is the base type the plan's text is cast to in every comparison
    (`t.mystery IS DISTINCT FROM p.old_value::integer`), so a comparison is made in the column's
    own type the way `apply_remediation_change()` makes it. `max_chars` is a declared width
    (`character varying(50)`), `None` for a type without one. `fills_null`: the stored value may be
    NULL - the lane fills an unassessed column (`scope_status`), and its reversal restores the NULL.
    """

    name: str
    sql_type: str
    max_chars: int | None = None
    allowed_new_values: tuple[str, ...] = ()
    fills_null: bool = False

    def __post_init__(self) -> None:
        if not _IDENTIFIER.match(self.name):
            raise ValueError(f"{self.name!r} is not a plain column name")
        if self.sql_type not in CELL_TYPES:
            raise ValueError(f"{self.name}: {self.sql_type!r} is not one of {sorted(CELL_TYPES)}")
        if self.max_chars is not None and self.max_chars <= 0:
            raise ValueError(f"{self.name}: the column width must be positive")
        for value in self.allowed_new_values:
            if not value or (self.max_chars is not None and len(value) > self.max_chars):
                raise ValueError(f"{self.name}: {value!r} cannot be written into {self.name}")

    def cast(self, expression: str) -> str:
        """`expression` compared in this column's type."""
        return f"{expression}::{self.sql_type}"


def typed_case(
    cells: Sequence[Column],
    value: str,
    *,
    alias: str,
    compare: str,
    column_expr: str,
    otherwise: str,
) -> str:
    """`CASE <column> WHEN 'c' THEN <alias>.c <compare> <value>::<type> ... ELSE <otherwise> END`.

    One comparison per cell, each in its column's own type, built from the cells themselves - the
    guards (`apply.cell_case`) and a reversal's residual (`reversal_residual`) alike, so a column
    added to a lane's cells is compared everywhere at once. CASE because only CASE fixes the
    evaluation order: in an `OR` of `(column = 'mystery' AND x::integer ...)` terms Postgres may
    cast a `category_group` text to integer first and raise.
    """
    whens = "".join(
        f"\n                WHEN {sql_literal(cell.name)} THEN {alias}.{cell.name} {compare} "
        f"{cell.cast(value)}"
        for cell in cells
    )
    return f"CASE {column_expr}{whens}\n                ELSE {otherwise} END"


def _check_column_lane(lane: Lane) -> None:
    """A column lane writes one `unified_sites` column named on the lane."""
    if not _IDENTIFIER.match(lane.column):
        raise ValueError(f"{lane.column!r} is not a plain column name")
    if lane.max_chars <= 0:
        raise ValueError(f"{lane.name}: the column width must be positive")
    for value in lane.allowed_new_values:
        if not value or len(value) > lane.max_chars:
            raise ValueError(f"{lane.name}: {value!r} cannot be written into {lane.column}")
    if not lane.target.is_site or lane.reverses_journal:
        raise ValueError(
            f"{lane.name}: a column lane writes one unified_sites column; another table or a "
            "journal reversal is a cell lane (`cells`)"
        )


def _check_cell_lane(lane: Lane) -> None:
    """A cell lane names its columns in `cells` and nothing in the column lane's fields."""
    if lane.column or lane.max_chars or lane.allowed_new_values:
        raise ValueError(
            f"{lane.name}: a cell lane names its columns in `cells`, not in `column`, "
            "`max_chars` or `allowed_new_values`"
        )
    names = [cell.name for cell in lane.cells]
    if len(set(names)) != len(names):
        raise ValueError(f"{lane.name}: a column appears twice in `cells`")


@dataclass(frozen=True)
class Lane:
    """Everything `apply.py` needs to know about one mechanical write that is not in its rows.

    A **column lane** sets `column`, `max_chars` and `allowed_new_values`; a **cell lane** sets
    `cells` instead (see the module docstring). `target` is the table written and its key;
    `reverses_journal` makes every planned cell the exact inverse of a named journal row.
    """

    name: str
    key_prefix: str
    run_stamp: str
    test_id: str
    confidence: str
    label: str
    plan_table: str
    out_dir_name: str
    post_commit_residual: Residual
    rehearsal_residual: Residual
    column: str = ""
    max_chars: int = 0
    allowed_new_values: tuple[str, ...] = ()
    premise_sql: str | None = None
    lock_timeout: str | None = None
    statement_timeout: str | None = None
    target: Target = UNIFIED_SITES
    cells: tuple[Column, ...] = ()
    reverses_journal: bool = False

    def __post_init__(self) -> None:
        """Every field that reaches SQL unquoted is checked here, once, instead of trusted."""
        if self.cells:
            _check_cell_lane(self)
        else:
            _check_column_lane(self)
        if not _IDENTIFIER.match(self.plan_table) or not self.plan_table.startswith("_"):
            raise ValueError(f"{self.plan_table!r} is not a temp-table name of the form _name")
        if not _LABEL.match(self.label):
            raise ValueError(f"{self.label!r} cannot be spliced into a RAISE message")
        if not _KEY_PREFIX.match(self.key_prefix):
            raise ValueError(f"{self.key_prefix!r} is not a change_key prefix")
        if not self.run_stamp or not self.test_id or not self.confidence:
            raise ValueError(
                f"{self.name}: a journal identity needs a stamp, a test id and a confidence"
            )
        for bound in (self.lock_timeout, self.statement_timeout):
            if bound is not None and not _DURATION.match(bound):
                raise ValueError(f"{self.name}: {bound!r} is not a duration like '10s'")

    @property
    def rollback_run_stamp(self) -> str:
        """The reversal's journal stamp: derived from the write's stamp, never equal to it."""
        return f"{self.run_stamp}-rollback"

    @property
    def probe_run_stamp(self) -> str:
        """Probes write nothing that survives; their own stamp makes a survivor visible."""
        return f"{self.run_stamp}-probe"

    @property
    def columns(self) -> tuple[str, ...]:
        """The columns this lane writes: its one column, or its cells' names."""
        return tuple(cell.name for cell in self.cells) if self.cells else (self.column,)

    def cell(self, column: str | None) -> Column:
        """The cell spec of `column` - refused unless this is a cell lane that owns it."""
        for cell in self.cells:
            if cell.name == column:
                return cell
        raise ValueError(f"{self.name}: {column!r} is not a column this lane writes")

    def _cell_suffix(self, column: str | None) -> str:
        """`:<column>` for a cell lane's key; nothing for a column lane, whose key is the site's.

        Whether a cell lane owns the column is not decided here but where it is enforced - the
        plan-side mirror and guard 2 - so a probe can render a cell in a column the lane does not
        own and show guard 2 refusing it.
        """
        if not self.cells:
            if column not in (None, self.column):
                raise ValueError(f"{self.name}: writes {self.column}, not {column!r}")
            return ""
        if column is None:
            raise ValueError(f"{self.name}: a cell lane's key names the cell's column")
        return f":{column}"

    def change_key(self, site_id: str, column: str | None = None) -> str:
        """The journal's identity for one row's *write* (one cell's, on a cell lane).

        `change_key` names the exact transition, so the write and its reversal must not share one:
        `Georgia (country) -> Georgia` and `Georgia -> Georgia (country)` are two different
        transitions, and a single key for both makes them indistinguishable in
        `remediation_change_log` - the reversal would read as a duplicate of the write it undoes.
        """
        return f"{self.key_prefix}:{site_id}" + self._cell_suffix(column)

    def rollback_change_key(self, site_id: str, column: str | None = None) -> str:
        """The journal's identity for one row's *reversal*: G0's `-rollback` suffix, same shape."""
        return f"{self.key_prefix}-rollback:{site_id}" + self._cell_suffix(column)


# ----------------------------------------------------------------------------------- the lanes
#: The country lane applied on 2026-09-21 (35 rows, `mechanical/APPLIED.md`). The run stamp is
#: deliberately not the hero write's `2026-09-20_remediation`: the read-back counts journal rows by
#: run stamp, and a shared stamp would make "0 rows unaccounted" unprovable. The census emits
#: `T05/disambiguated` and `T05/compound`; this lane's transition is a decided write, and the finding
#: that named the row is recorded in every record's evidence - one test id for the whole run is what
#: makes the journal read-back unambiguous.
T05 = Lane(
    name="t05",
    column="country",
    max_chars=100,
    key_prefix="country-canonical",
    run_stamp="2026-09-21_mechanical-country",
    test_id="T05/country-canonical",
    confidence="authoritative",
    label="country repair",
    plan_table="_country_plan",
    out_dir_name="mechanical",
    post_commit_residual=Residual(
        "curated rows still holding a parenthetical or comma country",
        "(country LIKE '%(%)%' OR country LIKE '%,%')",
    ),
    rehearsal_residual=Residual(
        "curated rows still holding the old value",
        "(country LIKE '%(%' OR country LIKE '%,%')",
    ),
)

#: The server-side bounds of the lanes written after T05. A lane's statement changes a few hundred
#: rows through `apply_remediation_change` and finishes in well under a second; 10 s is a lock held
#: by another session (the API writing the same site), 120 s is a statement that has run away. Both
#: raise inside the transaction, so the script stops at psql exit 3 with nothing kept - the one
#: outcome `apply.py --apply` can settle as NOT COMMITTED from the journal alone.
LOCK_TIMEOUT = "10s"
STATEMENT_TIMEOUT = "120s"

#: The United Kingdom's parts, spelled by region (owner decision B9, 2026-09-21). The lane owns the
#: four Natural Earth geo units of the United Kingdom and nothing else, and every row's value is
#: derived from its own point: `premise_sql` is that point as the database prints it.
UK_PARTS = Lane(
    name="uk-parts",
    column="country",
    max_chars=100,
    key_prefix="country-uk-part",
    run_stamp="2026-09-22_mechanical-uk-parts",
    test_id="B9/uk-country-part",
    confidence="authoritative",
    label="UK country part",
    plan_table="_uk_part_plan",
    out_dir_name="mechanical_uk",
    post_commit_residual=Residual(
        "curated rows still spelled as the whole United Kingdom",
        "country IN ('United Kingdom', 'UK', 'Great Britain')",
    ),
    rehearsal_residual=Residual(
        "curated rows still spelled as the whole United Kingdom",
        "country IN ('United Kingdom', 'UK', 'Great Britain')",
    ),
    allowed_new_values=("England", "Northern Ireland", "Scotland", "Wales"),
    premise_sql="u.lat::text || ',' || u.lon::text",
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
)


# ------------------------------------------------------------------------------- the read-backs
def written_where(lane: Lane) -> str:
    """Where a lane's journal rows belong, in words: `unified_sites.country`, or a cell lane's
    `card_stats.(mystery, rarity_tier)`."""
    if not lane.cells:
        return f"unified_sites.{lane.column}"
    return f"{lane.target.table}.({', '.join(lane.columns)})"


def outside(lane: Lane, prefix: str = "") -> str:
    """SQL: a journal row (its columns prefixed with `prefix`) that is none of this lane's cells."""
    if not lane.cells:
        return (
            f"({prefix}table_name <> 'unified_sites' OR {prefix}column_name <> "
            f"{sql_literal(lane.column)})"
        )
    listed = ", ".join(sql_literal(column) for column in lane.columns)
    return (
        f"({prefix}table_name <> {sql_literal(lane.target.table)} OR {prefix}column_name "
        f"NOT IN ({listed}))"
    )


def journal_readback(lane: Lane, extra: Sequence[tuple[str, str]]) -> str:
    """The read-only verification of a lane, before and after its write: the same text both times.

    Every lane gets the journal metrics that make its write accountable - rows for its run stamp,
    test id and rollback stamp, and the three ways a row can land where it must not (another column,
    a non-curated row, another site's `site_id_ref`). `extra` is the lane's own measure of the data:
    `(metric, "FROM ... WHERE ...")` pairs, each counted.

    Ordered by metric, like T05's `VERIFY_SQL`: a `UNION ALL` has no order of its own (read on
    production 2026-09-22, the metrics came back scrambled), and the before and after runs of
    `--apply` must be comparable line by line.
    """
    stamp = sql_literal(lane.run_stamp)
    metrics: list[tuple[str, str]] = [
        ("curated sites", "FROM unified_sites WHERE source_id = 'ancient_nerds'"),
        *extra,
        (
            "journal rows for this run stamp",
            f"FROM remediation_change_log WHERE run_stamp = {stamp}",
        ),
        (
            "journal rows for this test id",
            f"FROM remediation_change_log WHERE test_id = {sql_literal(lane.test_id)}",
        ),
        (
            "journal rows for the rollback stamp",
            f"FROM remediation_change_log WHERE run_stamp = {sql_literal(lane.rollback_run_stamp)}",
        ),
        (
            f"journal rows for this run outside {written_where(lane)}",
            f"FROM remediation_change_log WHERE run_stamp = {stamp} AND {outside(lane)}",
        ),
        (
            "journal rows for this run on non-curated rows",
            "FROM remediation_change_log l LEFT JOIN unified_sites u ON u.id::text = l.row_pk "
            f"WHERE l.run_stamp = {stamp} AND (u.id IS NULL OR u.source_id <> 'ancient_nerds')",
        ),
        (
            "journal rows for this run with a site_id_ref of another site",
            f"FROM remediation_change_log WHERE run_stamp = {stamp} "
            "AND site_id_ref::text IS DISTINCT FROM row_pk",
        ),
    ]
    body = "\nUNION ALL\n".join(
        f"SELECT {sql_literal(metric)} AS metric, count(*)::text AS value\n  {source}"
        for metric, source in metrics
    )
    return (
        "-- Read-only. The same text before and after the apply.\n\\pset footer off\n"
        + body
        + "\nORDER BY 1;\n"
    )


def _country_rows(values: Sequence[str]) -> list[tuple[str, str]]:
    return [
        (
            f"rows country = {value!r}",
            "FROM unified_sites WHERE source_id = 'ancient_nerds' "
            f"AND country = {sql_literal(value)}",
        )
        for value in values
    ]


#: The UK lane's read-back (not named like apply.py's T05 statement on purpose: the mutation sweep
#: pins that one by its assignment text). The spellings are the British-Isles family measured on
#: 2026-09-22; card_stats.civilization is the named residual, as in T05.
UK_PARTS_READBACK = journal_readback(
    UK_PARTS,
    [
        *_country_rows(
            ("Ireland", "Northern Ireland", "United Kingdom", "England", "Scotland", "Wales")
        ),
        (
            "journal rows for this run with old value 'Ireland'",
            f"FROM remediation_change_log WHERE run_stamp = {sql_literal(UK_PARTS.run_stamp)} "
            "AND old_value = 'Ireland'",
        ),
        (
            "journal rows for this run with old value 'United Kingdom'",
            f"FROM remediation_change_log WHERE run_stamp = {sql_literal(UK_PARTS.run_stamp)} "
            "AND old_value = 'United Kingdom'",
        ),
        (
            "phase-3 country rows superseded by this run",
            "FROM remediation_change_log p WHERE p.run_stamp LIKE 'phase3:%' "
            "AND p.table_name = 'unified_sites' AND p.column_name = 'country' AND EXISTS ("
            "SELECT 1 FROM remediation_change_log l WHERE l.row_pk = p.row_pk "
            f"AND l.column_name = 'country' AND l.run_stamp = {sql_literal(UK_PARTS.run_stamp)} "
            "AND l.id > p.id)",
        ),
        (
            "card_stats rows whose civilization differs from the site country",
            "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id "
            "WHERE u.source_id = 'ancient_nerds' AND cs.civilization IS DISTINCT FROM u.country",
        ),
    ],
)


def bucket_case(column: str = "period_start") -> str:
    """`categorize_period` as a SQL expression, built from the table it walks (upper bounds only).

    The same rule as the pipeline function and the frontend's `categorizePeriod`: the first bucket
    is open below, the last open above, and no year means no bucket.
    """
    whens = " ".join(
        f"WHEN {column} < {hi} THEN {sql_literal(label)}" for label, _lo, hi in PERIOD_BUCKETS[:-1]
    )
    return f"(CASE WHEN {column} IS NULL THEN NULL {whens} ELSE {sql_literal(PERIOD_BUCKETS[-1][0])} END)"


_PERIOD_MISMATCH = Residual(
    "curated rows whose period_name is not the bucket of period_start",
    f"period_name IS DISTINCT FROM {bucket_case()}",
)

#: Phase 6 item 2 (2026-09-22): `period_name` re-derived from `period_start` wherever the two
#: disagree - the gold standard's own rule (`GOLD_STANDARD.md:79`: "equals
#: categorize_period(period_start)"). Phase 3 corrected 389 `period_start` values and left 219 of
#: their labels in another bucket. The lane owns the nine bucket labels and nothing else, and every
#: write is conditioned on the `period_start` it was derived from.
PERIOD_NAME = Lane(
    name="period-name",
    column="period_name",
    max_chars=100,
    key_prefix="period-name-bucket",
    run_stamp="2026-09-22_mechanical-period-name",
    test_id="P6/period-name-bucket",
    confidence="authoritative",
    label="period_name derivation",
    plan_table="_period_name_plan",
    out_dir_name="mechanical_period_name",
    post_commit_residual=_PERIOD_MISMATCH,
    rehearsal_residual=_PERIOD_MISMATCH,
    allowed_new_values=tuple(label for label, _lo, _hi in PERIOD_BUCKETS),
    premise_sql="u.period_start::text",
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
)

PERIOD_NAME_READBACK = journal_readback(
    PERIOD_NAME,
    [
        (
            _PERIOD_MISMATCH.metric,
            f"FROM unified_sites WHERE source_id = 'ancient_nerds' AND {_PERIOD_MISMATCH.predicate}",
        ),
        (
            "curated rows with period_name '> 1500 AD'",
            "FROM unified_sites WHERE source_id = 'ancient_nerds' AND period_name = '> 1500 AD'",
        ),
        (
            "curated rows with a period_name but no period_start",
            "FROM unified_sites WHERE source_id = 'ancient_nerds' "
            "AND period_start IS NULL AND period_name IS NOT NULL",
        ),
        (
            "journal rows for this run whose value is not the row's bucket",
            "FROM remediation_change_log l JOIN unified_sites u ON u.id::text = l.row_pk "
            f"WHERE l.run_stamp = {sql_literal(PERIOD_NAME.run_stamp)} "
            f"AND l.new_value IS DISTINCT FROM {bucket_case('u.period_start')}",
        ),
    ],
)

#: What a `site_type` value that is *not a site type* looks like, measured on the phase-3 writes of
#: 2026-09-21/22: a lowercase snake_case marker a program emitted (`suspect_modern`, twice) and the
#: model's own statement that no type fits (`Grave (burial site) — not representable`). No canonical
#: type matches either (pinned by a test), so the shape alone cannot misread a real type.
NOT_A_TYPE_MARKER = r"^[a-z0-9]+(_[a-z0-9]+)+$"
NOT_A_TYPE_PHRASE = "not representable"

_NOT_A_TYPE = Residual(
    "curated rows whose site_type is a marker token or a model refusal",
    f"(site_type ~ {sql_literal(NOT_A_TYPE_MARKER)} "
    f"OR site_type ILIKE {sql_literal('%' + NOT_A_TYPE_PHRASE + '%')})",
)

#: Phase 6 item 1 (2026-09-22): phase 3 wrote three values into `site_type` that are not site types
#: and are live in page titles. The lane restores the value each of those writes replaced - the
#: journal's `old_value` - and owns the canonical types only (`pipeline/normalizers/site_type.py`).
SITE_TYPE_SHAPE = Lane(
    name="site-type-shape",
    column="site_type",
    max_chars=100,
    key_prefix="site-type-shape",
    run_stamp="2026-09-22_mechanical-site-type-shape",
    test_id="P6/site-type-shape",
    confidence="authoritative",
    label="site_type shape repair",
    plan_table="_site_type_plan",
    out_dir_name="mechanical_site_type",
    post_commit_residual=_NOT_A_TYPE,
    rehearsal_residual=_NOT_A_TYPE,
    allowed_new_values=tuple(CANONICAL_TYPES),
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
)

SITE_TYPE_SHAPE_READBACK = journal_readback(
    SITE_TYPE_SHAPE,
    [
        (
            _NOT_A_TYPE.metric,
            f"FROM unified_sites WHERE source_id = 'ancient_nerds' AND {_NOT_A_TYPE.predicate}",
        ),
        (
            "curated rows whose site_type is outside the canonical list",
            "FROM unified_sites WHERE source_id = 'ancient_nerds' AND (site_type IS NULL OR "
            "site_type NOT IN (" + ", ".join(sql_literal(t) for t in CANONICAL_TYPES) + "))",
        ),
        (
            "journal rows for this run whose value is not canonical",
            f"FROM remediation_change_log WHERE run_stamp = {sql_literal(SITE_TYPE_SHAPE.run_stamp)} "
            "AND new_value NOT IN (" + ", ".join(sql_literal(t) for t in CANONICAL_TYPES) + ")",
        ),
    ],
)


# ------------------------------------------------------------------------ the scope lane (E4)
def outside_e3_window(prefix: str = "") -> str:
    """SQL: the row's date lies past the E3 cutoff of its region - `passes_date_cutoff()` negated.

    Built from the project's own rule and constants (`pipeline/normalizers/dates.py`), never
    re-typed: the date is `period_end or period_start` (Python's `or`, so a 0 `period_end` falls
    through too), the region is the longitude window, and a row without a date or a longitude is
    never outside (the function includes it). `prefix` qualifies the columns (`u.`).
    """
    from pipeline.normalizers.dates import (
        AMERICAS_LON_MAX,
        AMERICAS_LON_MIN,
        DATE_CUTOFF_AMERICAS,
        DATE_CUTOFF_REST_OF_WORLD,
    )

    p = prefix
    date = (
        f"(CASE WHEN {p}period_end IS NOT NULL AND {p}period_end <> 0 THEN {p}period_end "
        f"ELSE {p}period_start END)"
    )
    cutoff = (
        f"(CASE WHEN {p}lon BETWEEN {AMERICAS_LON_MIN} AND {AMERICAS_LON_MAX} "
        f"THEN {DATE_CUTOFF_AMERICAS} ELSE {DATE_CUTOFF_REST_OF_WORLD} END)"
    )
    return f"({p}lon IS NOT NULL AND {date} > {cutoff})"


_UNDECIDED_OUT_OF_WINDOW = Residual(
    "curated rows outside the E3 window with no scope decision",
    f"{outside_e3_window()} AND scope_status IS NULL",
)

#: E4 (owner decision 2026-09-19, migration 0020): flag an out-of-scope site AND hide it
#: platform-wide - never DELETE it. The lane fills `scope_status` and `scope_reason`, both NULL on
#: every curated row until now (read on production 2026-09-23), in one transaction, so no site is
#: ever retired without its reason. Every decision rests on the row's date, place, type and name,
#: and a reviewed one on a quote of its description (`scope.py`), and is conditioned on them: the
#: premise is those inputs as the database prints it, the description as its md5. A duplicate's
#: ranking against its survivor is not in it - the survivor is not a planned row (`scope.py`).
SCOPE = Lane(
    name="scope-e4",
    key_prefix="scope-e4",
    run_stamp="2026-09-23_mechanical-scope-e4",
    test_id="E4/scope-status",
    confidence="authoritative",
    label="E4 scope decision",
    plan_table="_scope_plan",
    out_dir_name="mechanical_scope",
    post_commit_residual=_UNDECIDED_OUT_OF_WINDOW,
    rehearsal_residual=_UNDECIDED_OUT_OF_WINDOW,
    premise_sql=(
        "concat_ws(' | ', coalesce(u.period_start::text, 'NULL'), "
        "coalesce(u.period_end::text, 'NULL'), u.lat::text, u.lon::text, "
        "coalesce(u.site_type, 'NULL'), u.name, md5(coalesce(u.description, '')))"
    ),
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
    cells=(
        Column("scope_status", "text", allowed_new_values=SCOPE_STATUSES, fills_null=True),
        Column("scope_reason", "text", fills_null=True),
    ),
)

SCOPE_READBACK = journal_readback(
    SCOPE,
    [
        *(
            (
                f"curated rows with scope_status {status}",
                "FROM unified_sites WHERE source_id = 'ancient_nerds' AND "
                + (
                    "scope_status IS NULL"
                    if status == "NULL"
                    else f"scope_status = {sql_literal(status)}"
                ),
            )
            for status in ("NULL", *SCOPE_STATUSES)
        ),
        (
            _UNDECIDED_OUT_OF_WINDOW.metric,
            "FROM unified_sites WHERE source_id = 'ancient_nerds' AND "
            + _UNDECIDED_OUT_OF_WINDOW.predicate,
        ),
        (
            "curated rows without a date and no scope decision",
            "FROM unified_sites WHERE source_id = 'ancient_nerds' AND period_start IS NULL "
            "AND period_end IS NULL AND scope_status IS NULL",
        ),
        (
            "curated rows retired as a duplicate",
            "FROM unified_sites WHERE source_id = 'ancient_nerds' AND scope_status = 'retired' "
            "AND scope_reason LIKE 'duplicate_of:%'",
        ),
        (
            "curated rows with a scope_status but no scope_reason",
            "FROM unified_sites WHERE source_id = 'ancient_nerds' AND scope_status IS NOT NULL "
            "AND (scope_reason IS NULL OR scope_reason = '')",
        ),
        (
            "retired duplicates whose survivor is retired or not curated",
            "FROM unified_sites d WHERE d.source_id = 'ancient_nerds' AND d.scope_status = "
            "'retired' AND d.scope_reason LIKE 'duplicate_of:%' AND NOT EXISTS (SELECT 1 FROM "
            "unified_sites s WHERE s.id::text = substring(d.scope_reason from 14 for 36) AND "
            "s.source_id = 'ancient_nerds' AND s.scope_status IS DISTINCT FROM 'retired')",
        ),
    ],
)


# ------------------------------------------------------------------ the journal-reversal lanes
def reversal_residual(journal_ids: Sequence[int], cells: Sequence[Column]) -> Residual:
    """Curated cells that still hold the value one of `journal_ids` wrote - what the reversal
    exists to remove, read in each column's own type. The comparison is built from the lane's
    `cells` (`typed_case`): a journal row of a column the lane does not write reads as false."""
    listed = ", ".join(str(int(i)) for i in journal_ids)
    holds = typed_case(
        cells,
        "l.new_value",
        alias="unified_sites",
        compare="IS NOT DISTINCT FROM",
        column_expr="l.column_name",
        otherwise="false",
    )
    return Residual(
        "curated cells still holding a value this reversal list undoes",
        "EXISTS (SELECT 1 FROM remediation_change_log l WHERE l.id IN ("
        + listed
        + ") AND l.table_name = 'unified_sites' AND l.row_pk = unified_sites.id::text AND "
        + holds
        + ")",
    )


#: The first reversal list (2026-09-23), each a phase-3 write read-only verified wrong or not a
#: correction (`reversal.py`, `mechanical_reversal_1/PLAN.md`): 28384 Ahin Posh Tape country
#: Afghanistan -> Pakistan; 28018 Stanydale Temple and 28638 Agri Bavnehøj period_start -3000 ->
#: -2500 / -1800, values the gold standard had judged CORRECT.
REVERSAL_1_JOURNAL_IDS: tuple[int, ...] = (28018, 28384, 28638)
_REVERSAL_1_CELLS = (
    Column("country", "character varying", max_chars=100),
    Column("period_start", "integer"),
)
_REVERSAL_1_RESIDUAL = reversal_residual(REVERSAL_1_JOURNAL_IDS, _REVERSAL_1_CELLS)

REVERSAL_1 = Lane(
    name="journal-reversal-1",
    key_prefix="journal-reversal-1",
    run_stamp="2026-09-23_mechanical-journal-reversal-1",
    test_id="P6/journal-reversal",
    confidence="authoritative",
    label="journal reversal",
    plan_table="_journal_reversal_plan",
    out_dir_name="mechanical_reversal_1",
    post_commit_residual=_REVERSAL_1_RESIDUAL,
    rehearsal_residual=_REVERSAL_1_RESIDUAL,
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
    cells=_REVERSAL_1_CELLS,
    reverses_journal=True,
)

REVERSAL_1_READBACK = journal_readback(
    REVERSAL_1,
    [
        (
            _REVERSAL_1_RESIDUAL.metric,
            f"FROM unified_sites WHERE source_id = 'ancient_nerds' AND {_REVERSAL_1_RESIDUAL.predicate}",
        ),
        (
            "journal rows of this list that a later write superseded",
            "FROM remediation_change_log l WHERE l.id IN ("
            + ", ".join(str(i) for i in REVERSAL_1_JOURNAL_IDS)
            + ") AND EXISTS (SELECT 1 FROM remediation_change_log m WHERE m.table_name = "
            "l.table_name AND m.column_name = l.column_name AND m.row_pk = l.row_pk AND m.id > l.id "
            f"AND m.run_stamp <> {sql_literal(REVERSAL_1.run_stamp)})",
        ),
        (
            "card_stats rows whose civilization differs from the site country",
            "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id "
            "WHERE u.source_id = 'ancient_nerds' AND cs.civilization IS DISTINCT FROM u.country",
        ),
    ],
)

LANES: dict[str, Lane] = {
    lane.name: lane for lane in (T05, UK_PARTS, PERIOD_NAME, SITE_TYPE_SHAPE, SCOPE, REVERSAL_1)
}

#: The read-only verification per lane, except T05's: that one is `apply.VERIFY_SQL`, kept there
#: unchanged since the write it verified. A card_stats wave's is `card_stats.card_stats_readback`.
LANE_READBACKS: dict[str, str] = {
    UK_PARTS.name: UK_PARTS_READBACK,
    PERIOD_NAME.name: PERIOD_NAME_READBACK,
    SITE_TYPE_SHAPE.name: SITE_TYPE_SHAPE_READBACK,
    SCOPE.name: SCOPE_READBACK,
    REVERSAL_1.name: REVERSAL_1_READBACK,
}

#: A card_stats recompute is re-run after every later write wave, each wave a lane of its own
#: (`card-stats-2026-09-23`, `card-stats-2026-09-24b`): its own run stamp, so "never apply a stamp
#: twice" still holds, and its own directory.
CARD_STATS_LANE = re.compile(r"^card-stats-(\d{4}-\d{2}-\d{2}[a-z]?)$")


def resolve_lane(name: str) -> Lane:
    """The lane called `name`: a registered one, or a card_stats wave. `KeyError` otherwise.

    The card_stats lanes are built by `card_stats.card_stats_lane`, imported here and only here:
    their owned values are the card generator's own, and importing the API package is not a cost
    every other lane should pay.
    """
    if name in LANES:
        return LANES[name]
    match = CARD_STATS_LANE.match(name)
    if match is None:
        raise KeyError(name)
    from mechanical.card_stats import card_stats_lane

    return card_stats_lane(match.group(1))
