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
* the residual predicates the read-backs print, and the output directory;
* `write_invariant` (2026-09-26, the L5 name lane): a residual that must count 0 over the planned
  sites once their rows are written, checked *inside* the transaction, write and reversal alike -
  for a value whose correctness is a relation between cells the lane writes together (a name and
  its match key), which no guard on the old values can see.

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
the scope vocabulary), so they are never copied, and the generated journal-row lists of
journal-reversal-3 (`reversal_3_list.py`) and of the wrong-both correction (`wrong_both_list.py`).
The card_stats lanes
live in `card_stats.py`, which imports the card generator: `resolve_lane` reaches them lazily, so
this module - and every lane that does not write card_stats - never imports the API package.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from prod_write import sql_literal  # noqa: F401 - the one quoting rule, re-exported for the lanes

from mechanical.reversal_3_list import JOURNAL_IDS as REVERSAL_3_JOURNAL_IDS
from mechanical.wrong_both_list import JOURNAL_IDS as WRONG_BOTH_JOURNAL_IDS
from pipeline.lyra.site_key import site_key_sql
from pipeline.normalizers.site_type import CANONICAL_TYPES
from pipeline.utils.public_sites import SCOPE_STATUSES
from pipeline.utils.text import PERIOD_BUCKETS

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*\Z")
#: The label is spliced into RAISE message literals: no quote (it would end the literal) and no `%`
#: (it would be read as a placeholder and consume an argument).
_LABEL = re.compile(r"^[A-Za-z0-9 _/-]+\Z")
_KEY_PREFIX = re.compile(r"^[a-z0-9-]+\Z")
#: A Postgres duration as `SET LOCAL ... = '<value>'` takes it: digits and a unit, nothing else.
_DURATION = re.compile(r"^[1-9][0-9]*(ms|s|min)\Z")


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
    write_invariant: Residual | None = None

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
        if self.write_invariant is not None and (
            not self.cells
            or not self.target.is_site
            or not _LABEL.match(self.write_invariant.metric)
        ):
            raise ValueError(
                f"{self.name}: a write invariant belongs to a cell lane on unified_sites (its "
                "probe corrupts one cell of two written together), and its metric - spliced "
                "into the statement - is plain words"
            )

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
    """Curated sites with a cell that still holds the value one of `journal_ids` wrote - what
    the reversal exists to remove, read in each column's own type; a site counts once, however
    many of its cells the list undoes. The comparison is built from the lane's
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
        "curated sites still holding a value this reversal list undoes",
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


def reversal_metrics(
    lane: Lane, journal_ids: Sequence[int], residual: Residual
) -> list[tuple[str, str]]:
    """The two counts every reversal lane reads back: the cells still holding a value the list
    undoes, and the listed journal rows a write other than this lane's has superseded since."""
    return [
        (
            residual.metric,
            f"FROM unified_sites WHERE source_id = 'ancient_nerds' AND {residual.predicate}",
        ),
        (
            "journal rows of this list that a later write superseded",
            "FROM remediation_change_log l WHERE l.id IN ("
            + ", ".join(str(i) for i in journal_ids)
            + ") AND EXISTS (SELECT 1 FROM remediation_change_log m WHERE m.table_name = "
            "l.table_name AND m.column_name = l.column_name AND m.row_pk = l.row_pk AND m.id > l.id "
            f"AND m.run_stamp <> {sql_literal(lane.run_stamp)})",
        ),
    ]


REVERSAL_1_READBACK = journal_readback(
    REVERSAL_1,
    [
        *reversal_metrics(REVERSAL_1, REVERSAL_1_JOURNAL_IDS, _REVERSAL_1_RESIDUAL),
        (
            "card_stats rows whose civilization differs from the site country",
            "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id "
            "WHERE u.source_id = 'ancient_nerds' AND cs.civilization IS DISTINCT FROM u.country",
        ),
    ],
)

#: The second reversal list (2026-09-23). 45 written phase-3 rows - 30 `site_type`, 15
#: `period_start` - that the first re-review decided to reverse
#: (`output/remediation/phase3_runner/REREVIEW_1.md`: one new reviewer call per row, the row kept
#: only on a clean clearance; `REREVIEW_1_FINAL.jsonl` with its hand read), and the 8 `period_name`
#: labels the period-name lane derived from 8 of those `period_start` values (30335-30536): with
#: the start restored, its label goes back to the bucket it names (`reversal.py`,
#: `mechanical_reversal_2/`).
REVERSAL_2_JOURNAL_IDS: tuple[int, ...] = (
    27752, 27924, 28004, 28092, 28325, 28597, 28607, 28621, 28627, 28632, 28663, 28670, 28675,
    28744, 28757, 28770, 28776, 28785, 28804, 28870, 28872, 28970, 28978, 28998, 29025, 29073,
    29082, 29136, 29176, 29246, 29272, 29275, 29285, 29326, 29410, 29436, 29497, 29552, 29563,
    29578, 29617, 29618, 29628, 29633, 29642,
    30335, 30386, 30405, 30441, 30451, 30454, 30512, 30536,
)  # fmt: skip
_REVERSAL_2_CELLS = (
    Column("site_type", "character varying", max_chars=100),
    Column("period_start", "integer"),
    Column("period_name", "character varying", max_chars=100),
)
_REVERSAL_2_RESIDUAL = reversal_residual(REVERSAL_2_JOURNAL_IDS, _REVERSAL_2_CELLS)

REVERSAL_2 = Lane(
    name="journal-reversal-2",
    key_prefix="journal-reversal-2",
    run_stamp="2026-09-23_mechanical-journal-reversal-2",
    test_id="P6/journal-reversal-2",
    confidence="authoritative",
    label="journal reversal",
    plan_table="_journal_reversal_2_plan",
    out_dir_name="mechanical_reversal_2",
    post_commit_residual=_REVERSAL_2_RESIDUAL,
    rehearsal_residual=_REVERSAL_2_RESIDUAL,
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
    cells=_REVERSAL_2_CELLS,
    reverses_journal=True,
)

REVERSAL_2_READBACK = journal_readback(
    REVERSAL_2,
    [
        *reversal_metrics(REVERSAL_2, REVERSAL_2_JOURNAL_IDS, _REVERSAL_2_RESIDUAL),
        (
            _PERIOD_MISMATCH.metric,
            f"FROM unified_sites WHERE source_id = 'ancient_nerds' AND {_PERIOD_MISMATCH.predicate}",
        ),
    ],
)

#: Each reversal lane and the journal rows it reverses - the list its `REASONS.json` must name.
REVERSAL_LISTS: dict[str, tuple[int, ...]] = {
    REVERSAL_1.name: REVERSAL_1_JOURNAL_IDS,
    REVERSAL_2.name: REVERSAL_2_JOURNAL_IDS,
}

LANES: dict[str, Lane] = {
    lane.name: lane
    for lane in (T05, UK_PARTS, PERIOD_NAME, SITE_TYPE_SHAPE, SCOPE, REVERSAL_1, REVERSAL_2)
}

#: The read-only verification per lane, except T05's: that one is `apply.VERIFY_SQL`, kept there
#: unchanged since the write it verified. A card_stats wave's is `card_stats.card_stats_readback`.
LANE_READBACKS: dict[str, str] = {
    UK_PARTS.name: UK_PARTS_READBACK,
    PERIOD_NAME.name: PERIOD_NAME_READBACK,
    SITE_TYPE_SHAPE.name: SITE_TYPE_SHAPE_READBACK,
    SCOPE.name: SCOPE_READBACK,
    REVERSAL_1.name: REVERSAL_1_READBACK,
    REVERSAL_2.name: REVERSAL_2_READBACK,
}

#: The third reversal list (2026-09-25): every write the Opus re-verification decided to revert (a
#: final revert, not superseded; `output/remediation/opus_audit/REVERSAL_3_INPUT.jsonl`), and the
#: `period_name` labels the period-name lane derived from those of its `period_start` values whose
#: restored start falls in another bucket. The journal ids are read from production by change_key
#: and generated into `reversal_3_list.py` by `reversal_opus.py --write`, together with
#: `mechanical_reversal_3/REASONS.json`; each audit row quotes the verdicts that decided it
#: (`opus:<change_key>`, `reversal.py`). Registered below the lists of the first two, which stay
#: as they were written.
_REVERSAL_3_CELLS = (
    Column("site_type", "character varying", max_chars=100),
    Column("period_start", "integer"),
    Column("period_name", "character varying", max_chars=100),
    Column("country", "character varying", max_chars=100),
)
_REVERSAL_3_RESIDUAL = reversal_residual(REVERSAL_3_JOURNAL_IDS, _REVERSAL_3_CELLS)

REVERSAL_3 = Lane(
    name="journal-reversal-3",
    key_prefix="journal-reversal-3",
    run_stamp="2026-09-25_mechanical-journal-reversal-3",
    test_id="P6/journal-reversal-3",
    confidence="authoritative",
    label="journal reversal",
    plan_table="_journal_reversal_3_plan",
    out_dir_name="mechanical_reversal_3",
    post_commit_residual=_REVERSAL_3_RESIDUAL,
    rehearsal_residual=_REVERSAL_3_RESIDUAL,
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
    cells=_REVERSAL_3_CELLS,
    reverses_journal=True,
)

REVERSAL_3_READBACK = journal_readback(
    REVERSAL_3,
    [
        *reversal_metrics(REVERSAL_3, REVERSAL_3_JOURNAL_IDS, _REVERSAL_3_RESIDUAL),
        (
            _PERIOD_MISMATCH.metric,
            f"FROM unified_sites WHERE source_id = 'ancient_nerds' AND {_PERIOD_MISMATCH.predicate}",
        ),
        (
            "card_stats rows whose civilization differs from the site country",
            "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id "
            "WHERE u.source_id = 'ancient_nerds' AND cs.civilization IS DISTINCT FROM u.country",
        ),
    ],
)
REVERSAL_LISTS[REVERSAL_3.name] = REVERSAL_3_JOURNAL_IDS
LANES[REVERSAL_3.name] = REVERSAL_3
LANE_READBACKS[REVERSAL_3.name] = REVERSAL_3_READBACK

#: The wrong-both correction (2026-09-25): where the Opus re-verification reverted a write and its
#: judges named the right value (RULES.md rule 5: "wrong-both rows carry a proposed value ... It goes
#: to a later correction lane that writes only with a machine-verified verbatim quote"), that value
#: is written over the old value journal-reversal-3 restored - with the `period_name` label of a
#: `period_start` it moves to another bucket (`wrong_both.py`). The lane owns the canonical site
#: types and the bucket labels. Its list is the journal-reversal-3 rows whose restored value a
#: correction replaces, generated into `wrong_both_list.py` by `wrong_both.py --list`: the residual
#: is the curated sites still holding one of those restored values. It reverses no journal row and
#: derives from no premise: every cell is conditioned on its old value (guard 3). Registered below
#: the three reversal lists, which stay as they were written.
_WRONG_BOTH_CELLS = (
    Column(
        "site_type", "character varying", max_chars=100, allowed_new_values=tuple(CANONICAL_TYPES)
    ),
    Column("period_start", "integer"),
    Column(
        "period_name",
        "character varying",
        max_chars=100,
        allowed_new_values=tuple(label for label, _lo, _hi in PERIOD_BUCKETS),
    ),
    Column("country", "character varying", max_chars=100),
)
_WRONG_BOTH_RESIDUAL = Residual(
    "curated sites still holding a restored value a wrong-both correction replaces",
    reversal_residual(WRONG_BOTH_JOURNAL_IDS, _WRONG_BOTH_CELLS).predicate,
)

WRONG_BOTH = Lane(
    name="wrong-both",
    key_prefix="wrong-both",
    run_stamp="2026-09-25_mechanical-wrong-both",
    test_id="P6/wrong-both",
    confidence="authoritative",
    label="wrong-both correction",
    plan_table="_wrong_both_plan",
    out_dir_name="mechanical_wrong_both",
    post_commit_residual=_WRONG_BOTH_RESIDUAL,
    rehearsal_residual=_WRONG_BOTH_RESIDUAL,
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
    cells=_WRONG_BOTH_CELLS,
)

#: The period pair and the card country, read back as the reversal lanes read them.
_CURATED_ROWS = "FROM unified_sites WHERE source_id = 'ancient_nerds' AND "
_CARD_COUNTRY = (
    "card_stats rows whose civilization differs from the site country",
    "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id WHERE u.source_id = "
    "'ancient_nerds' AND cs.civilization IS DISTINCT FROM u.country",
)
WRONG_BOTH_READBACK = journal_readback(
    WRONG_BOTH,
    [
        *reversal_metrics(WRONG_BOTH, WRONG_BOTH_JOURNAL_IDS, _WRONG_BOTH_RESIDUAL),
        (_PERIOD_MISMATCH.metric, _CURATED_ROWS + _PERIOD_MISMATCH.predicate),
        _CARD_COUNTRY,
    ],
)
LANES[WRONG_BOTH.name] = WRONG_BOTH
LANE_READBACKS[WRONG_BOTH.name] = WRONG_BOTH_READBACK


# ------------------------------------------------------------ the orphan-citations lane (D1)
def marker_matches(text: str) -> str:
    """Every `[n]` of the text expression `text`, as the set-returning `regexp_matches`: a
    citation marker as the census and the acceptance's D1 read one (`t08_citation_markers.
    _MARKER_RE`). The census expands grouped and range forms first (`normalize_grouped_markers`);
    no curated description carries one (measured 2026-09-25, `citations.py`)."""
    return rf"regexp_matches(coalesce({text}, ''), '\[(\d+)\]', 'g')"


#: Every marker of a curated description, as rows of `m(g)`; on the data of 2026-09-25 this SQL
#: finds exactly the 78 sites the Python D1 finds.
_MARKERS_SQL = marker_matches("description")
#: Every `raw_data.description_citations` entry of the row, as rows of `e(entry)`; none where the
#: key is absent or not an array.
_ENTRIES_SQL = (
    "jsonb_array_elements(CASE WHEN jsonb_typeof(raw_data -> 'description_citations') = 'array' "
    "THEN raw_data -> 'description_citations' ELSE '[]'::jsonb END)"
)
_ENTRY_CITED = (
    "jsonb_typeof(e.entry -> 'n') = 'number' AND (e.entry ->> 'n')::numeric = m.g[1]::numeric"
)
#: D1's two halves on an unqualified `unified_sites` row: an entry no marker cites, a marker no
#: entry answers.
CITATIONS_UNCITED = (
    f"EXISTS (SELECT 1 FROM {_ENTRIES_SQL} AS e(entry) WHERE NOT EXISTS "
    f"(SELECT 1 FROM {_MARKERS_SQL} AS m(g) WHERE {_ENTRY_CITED}))"
)
CITATIONS_UNANSWERED = (
    f"EXISTS (SELECT 1 FROM {_MARKERS_SQL} AS m(g) WHERE NOT EXISTS "
    f"(SELECT 1 FROM {_ENTRIES_SQL} AS e(entry) WHERE {_ENTRY_CITED}))"
)
_D1_FAILS = Residual(
    "curated rows D1 fails on (a marker without an entry, or an entry no marker cites)",
    f"({CITATIONS_UNCITED} OR {CITATIONS_UNANSWERED})",
)

#: The acceptance's D1 (`acceptance/checks.py`) on the curated rows (2026-09-25): every `[N]` of the
#: description has an entry in `raw_data.description_citations`, and every entry is cited. The lane
#: removes the entries no marker cites - with the key where the text cites nothing - and writes
#: nothing else: not the description, not another `raw_data` key (`citations.py`). Its value is
#: derived from the description's markers, so each write is conditioned on the description it read,
#: as the sha256 `_description_provenance.desc_sha256` pins it.
ORPHAN_CITATIONS = Lane(
    name="orphan-citations",
    key_prefix="orphan-citations",
    run_stamp="2026-09-25_mechanical-orphan-citations",
    test_id="T08/orphan-citations",
    confidence="authoritative",
    label="orphan citation removal",
    plan_table="_orphan_citations_plan",
    out_dir_name="mechanical_citations",
    post_commit_residual=_D1_FAILS,
    rehearsal_residual=_D1_FAILS,
    premise_sql="encode(sha256(convert_to(coalesce(u.description, ''), 'UTF8')), 'hex')",
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
    cells=(Column("raw_data", "jsonb"),),
)

#: D4 of the acceptance in SQL, on an unqualified `unified_sites` row: the row carries a
#: `_description_provenance` whose `desc_sha256` is not the sha256 of its description.
PROVENANCE_HASH_DIFFERS = (
    "raw_data ? '_description_provenance' AND "
    "encode(sha256(convert_to(coalesce(description, ''), 'UTF8')), 'hex') "
    "IS DISTINCT FROM raw_data -> '_description_provenance' ->> 'desc_sha256'"
)
#: A `raw_data` journal row `l` whose new citation array holds an entry its old one did not.
_ENTRY_ADDED = (
    "EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(l.new_value::jsonb -> "
    "'description_citations', '[]'::jsonb)) AS x(entry) WHERE NOT coalesce("
    "l.old_value::jsonb -> 'description_citations', '[]'::jsonb) @> "
    "jsonb_build_array(x.entry))"
)
#: The read-back rows both citation lanes print: D1's two halves and D4, over the curated rows.
_CITATION_STATE = (
    (
        "curated rows with a description_citations entry no marker cites",
        _CURATED_ROWS + CITATIONS_UNCITED,
    ),
    (
        "curated rows with a marker no description_citations entry answers",
        _CURATED_ROWS + CITATIONS_UNANSWERED,
    ),
)
_D4_FAILS = (
    "curated rows whose description is not the one its provenance hashes",
    _CURATED_ROWS + PROVENANCE_HASH_DIFFERS,
)

_ORPHAN_STAMP = sql_literal(ORPHAN_CITATIONS.run_stamp)
ORPHAN_CITATIONS_READBACK = journal_readback(
    ORPHAN_CITATIONS,
    [
        (_D1_FAILS.metric, _CURATED_ROWS + _D1_FAILS.predicate),
        *_CITATION_STATE,
        (
            "curated rows carrying description_citations",
            _CURATED_ROWS + "raw_data ? 'description_citations'",
        ),
        _D4_FAILS,
        (
            "journal rows for this run that changed a raw_data key other than "
            "description_citations",
            f"FROM remediation_change_log WHERE run_stamp = {_ORPHAN_STAMP} AND "
            "(old_value::jsonb - 'description_citations') IS DISTINCT FROM "
            "(new_value::jsonb - 'description_citations')",
        ),
        (
            "journal rows for this run that added a citation entry",
            f"FROM remediation_change_log l WHERE l.run_stamp = {_ORPHAN_STAMP} AND "
            + _ENTRY_ADDED,
        ),
    ],
)
LANES[ORPHAN_CITATIONS.name] = ORPHAN_CITATIONS
LANE_READBACKS[ORPHAN_CITATIONS.name] = ORPHAN_CITATIONS_READBACK

# ------------------------------------------------------------ the dangling-markers lane (D9)
#: The markers of D9 (2026-09-25): a `[N]` of the description with no citation entry. The
#: orphan-citations lane listed these sites for a human; the owner's order of 2026-09-25 takes D9's
#: option (b) for the ones Phase 4 held - the marker points to no source, so it leaves the text and
#: the claims stay, under lane L's marking that the text is AI-generated (`dangling_markers.py`).
#: The lane writes two cells of one site in one transaction: the description without its dangling
#: markers, and `raw_data` with `_description_provenance.desc_sha256` moved to the new text (D4) -
#: plus, where the removal leaves an entry no marker cites, without that entry (D1, the
#: orphan-citations rule). The premise is the legacy provenance less the hash it moves: guard 5
#: refuses a site whose text is no longer lane L's, and holds for the write and its reversal alike.
DANGLING_MARKERS = Lane(
    name="dangling-markers",
    key_prefix="dangling-markers",
    run_stamp="2026-09-25_mechanical-dangling-markers",
    test_id="T08/dangling-markers",
    confidence="authoritative",
    label="dangling marker removal",
    plan_table="_dangling_markers_plan",
    out_dir_name="mechanical_dangling_markers",
    post_commit_residual=_D1_FAILS,
    rehearsal_residual=_D1_FAILS,
    premise_sql=(
        "coalesce((u.raw_data -> '_description_provenance') - 'desc_sha256', 'null'::jsonb)::text"
    ),
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
    cells=(Column("description", "text"), Column("raw_data", "jsonb")),
)

_DANGLING_STAMP = sql_literal(DANGLING_MARKERS.run_stamp)
_DANGLING_ROWS = f"FROM remediation_change_log l WHERE l.run_stamp = {_DANGLING_STAMP} AND "
#: A description as the markers' surroundings: every marker and every whitespace taken out.
_PROSE = r"regexp_replace(regexp_replace(coalesce({}, ''), '\[\d+\]', '', 'g'), '\s', '', 'g')"


def _raw_data_rows(predicate: str) -> str:
    """This run's `raw_data` rows meeting `predicate` - behind a CASE, because the lane's
    description rows are not JSON and a WHERE does not fix the order its casts run in."""
    return _DANGLING_ROWS + f"CASE WHEN l.column_name = 'raw_data' THEN {predicate} ELSE false END"


DANGLING_MARKERS_READBACK = journal_readback(
    DANGLING_MARKERS,
    [
        (_D1_FAILS.metric, _CURATED_ROWS + _D1_FAILS.predicate),
        *_CITATION_STATE,
        _D4_FAILS,
        (
            "journal rows for this run whose description differs in more than markers and "
            "whitespace",
            _DANGLING_ROWS
            + "l.column_name = 'description' AND "
            + _PROSE.format("l.old_value")
            + " IS DISTINCT FROM "
            + _PROSE.format("l.new_value"),
        ),
        (
            "journal rows for this run whose description gained a marker",
            _DANGLING_ROWS
            + "l.column_name = 'description' AND EXISTS (SELECT 1 FROM "
            + f"{marker_matches('l.new_value')} AS m(g) WHERE NOT EXISTS (SELECT 1 FROM "
            + f"{marker_matches('l.old_value')} AS o(g) WHERE o.g = m.g))",
        ),
        (
            "journal rows for this run whose raw_data changed more than the citations and the hash",
            _raw_data_rows(
                "((l.old_value::jsonb - 'description_citations') #- "
                "'{_description_provenance,desc_sha256}') IS DISTINCT FROM "
                "((l.new_value::jsonb - 'description_citations') #- "
                "'{_description_provenance,desc_sha256}')"
            ),
        ),
        (
            "journal rows for this run whose citation array gained an entry",
            _raw_data_rows(_ENTRY_ADDED),
        ),
        (
            "journal rows for this run whose provenance hash is not the description it wrote",
            _raw_data_rows(
                "NOT EXISTS (SELECT 1 FROM remediation_change_log d WHERE d.run_stamp = "
                "l.run_stamp AND d.row_pk = l.row_pk AND d.column_name = 'description' AND "
                "encode(sha256(convert_to(d.new_value, 'UTF8')), 'hex') = "
                "l.new_value::jsonb -> '_description_provenance' ->> 'desc_sha256')"
            ),
        ),
        (
            "journal rows for this run whose provenance is not lane L",
            _raw_data_rows(
                "(l.new_value::jsonb -> '_description_provenance' ->> 'lane') IS DISTINCT FROM 'L'"
            ),
        ),
    ],
)
LANES[DANGLING_MARKERS.name] = DANGLING_MARKERS
LANE_READBACKS[DANGLING_MARKERS.name] = DANGLING_MARKERS_READBACK

# ------------------------------------------------------------------ the B2 country lane (WE)
#: HUMAN_ONLY B2-L, decided 2026-09-26 under the owner's O9 ("nach meiner Empfehlung entscheiden",
#: `output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`): the two curated rows whose country the
#: B2 classifier found wrong and no lane wrote. `(site id, name, stored value, decided value)`.
#: Achladia lies with its item's P625 on Crete (P17 Greece); Delphinion lies in Miletus, 20 m from
#: its item's P625. The dataset spells Türkiye (218 curated rows, 0 `Turkey`, read 2026-09-26).
COUNTRY_B2_DECISIONS: tuple[tuple[str, str, str, str], ...] = (
    ("74145e9b-76a6-48de-a902-08ecb2f1f7bb", "Achladia", "Germany", "Greece"),
    ("6aa4c8de-3794-42fe-b68e-6b6ab77bd8ed", "Delphinion", "Greece", "Türkiye"),
)
_B2_WRONG = Residual(
    "curated rows still holding a country the B2 decision replaces",
    "("
    + " OR ".join(
        f"(id = {sql_literal(site)}::uuid AND country = {sql_literal(old)})"
        for site, _name, old, _new in COUNTRY_B2_DECISIONS
    )
    + ")",
)

#: The country lane of the B2 decision (`country_b2.py`). A column lane like the UK lane: it owns
#: exactly the decided values, and every row carries its point as the premise - the decision rests
#: on where the row lies, so a row whose point moved after the plan is refused (guard 5).
COUNTRY_B2 = Lane(
    name="country-b2",
    column="country",
    max_chars=100,
    key_prefix="country-b2",
    run_stamp="2026-09-26_mechanical-country-b2",
    test_id="B2/country",
    confidence="authoritative",
    label="B2 country repair",
    plan_table="_country_b2_plan",
    out_dir_name="mechanical_country_b2",
    post_commit_residual=_B2_WRONG,
    rehearsal_residual=_B2_WRONG,
    allowed_new_values=tuple(sorted({new for _site, _name, _old, new in COUNTRY_B2_DECISIONS})),
    premise_sql="u.lat::text || ',' || u.lon::text",
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
)
COUNTRY_B2_READBACK = journal_readback(
    COUNTRY_B2,
    [
        (_B2_WRONG.metric, _CURATED_ROWS + _B2_WRONG.predicate),
        *_country_rows(("Germany", "Greece", "Türkiye")),
        _CARD_COUNTRY,
    ],
)
LANES[COUNTRY_B2.name] = COUNTRY_B2
LANE_READBACKS[COUNTRY_B2.name] = COUNTRY_B2_READBACK

# ------------------------------------------------------------------ the L5 name lane (WE)
#: A curated row whose match key is not the key Postgres derives from its name: the name lane's
#: residual, 0 before (read 2026-09-26) and after - the lane writes each name and its key together.
_NAME_KEY_DIFFERS = Residual(
    "curated rows whose name_normalized is not the key of their name",
    f"name_normalized IS DISTINCT FROM {site_key_sql('name')}",
)

#: HUMAN_ONLY B1-N and Nr. 7, decided 2026-09-26 under O9: L5's name pass renames a curated site
#: only to a sourced name of that very site - an Opus reading whose quote the machine found
#: (`scripts/remediation/l5/`) - and "Zoque Culture Archaeological Zone" to "Chiapa de Corzo", the
#: English label of its item Q4384315. `name` is NOT NULL and `varchar(500)`; its match key moves
#: with it in the same transaction, as the key Postgres computed from the new name when the plan
#: was read (FIELD_CONTRACT 2.2: write `left(lower(unaccent(name)), 500)`, never a Python key); the
#: transaction itself refuses to commit a planned site whose key is not its name's key
#: (`write_invariant`), the rename and its reversal alike.
NAME_L5 = Lane(
    name="name-l5",
    key_prefix="name-l5",
    run_stamp="2026-09-26_mechanical-name-l5",
    test_id="B1/name-l5",
    confidence="authoritative",
    label="L5 name repair",
    plan_table="_name_l5_plan",
    out_dir_name="mechanical_name_l5",
    post_commit_residual=_NAME_KEY_DIFFERS,
    rehearsal_residual=_NAME_KEY_DIFFERS,
    lock_timeout=LOCK_TIMEOUT,
    statement_timeout=STATEMENT_TIMEOUT,
    cells=(
        Column("name", "character varying", max_chars=500),
        Column("name_normalized", "character varying", max_chars=500),
    ),
    write_invariant=_NAME_KEY_DIFFERS,
)
_NAME_STAMP = sql_literal(NAME_L5.run_stamp)
NAME_L5_READBACK = journal_readback(
    NAME_L5,
    [
        (_NAME_KEY_DIFFERS.metric, _CURATED_ROWS + _NAME_KEY_DIFFERS.predicate),
        (
            "journal rows for this run whose key is not the key of the name it wrote",
            f"FROM remediation_change_log l WHERE l.run_stamp = {_NAME_STAMP} AND "
            "l.column_name = 'name_normalized' AND NOT EXISTS (SELECT 1 FROM "
            f"remediation_change_log n WHERE n.run_stamp = {_NAME_STAMP} AND n.row_pk = l.row_pk "
            f"AND n.column_name = 'name' AND {site_key_sql('n.new_value')} = l.new_value)",
        ),
        (
            "journal rows for this run naming a site whose name and key did not move together",
            f"FROM remediation_change_log l WHERE l.run_stamp = {_NAME_STAMP} AND (SELECT "
            f"count(*) FROM remediation_change_log m WHERE m.run_stamp = {_NAME_STAMP} AND "
            "m.row_pk = l.row_pk) <> 2",
        ),
    ],
)
LANES[NAME_L5.name] = NAME_L5
LANE_READBACKS[NAME_L5.name] = NAME_L5_READBACK

#: A card_stats recompute is re-run after every later write wave, each wave a lane of its own
#: (`card-stats-2026-09-23`, `card-stats-2026-09-24b`): its own run stamp, so "never apply a stamp
#: twice" still holds, and its own directory.
CARD_STATS_LANE = re.compile(r"^card-stats-(\d{4}-\d{2}-\d{2}[a-z]?)\Z")


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
