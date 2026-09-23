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

T05 is the country lane that was applied on 2026-09-21. Its rendering is pinned byte for byte in
`tests/remediation/test_mechanical.py` (sha256 of `APPLY.sql`/`ROLLBACK.sql` rendered from the
delivered plan), so it carries no fourth or fifth guard and no server bounds: `allowed_new_values=()`,
`premise_sql=None` and no timeouts render exactly the statement that was rehearsed and written.

A leaf module: it imports nothing from `plan.py` or `apply.py`, so both can import it. It does
import the pipeline's own vocabularies a lane owns (the period buckets, the canonical site types),
so they are never copied.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from pipeline.normalizers.site_type import CANONICAL_TYPES
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


@dataclass(frozen=True)
class Lane:
    """Everything `apply.py` needs to know about one mechanical write that is not in its rows."""

    name: str
    column: str
    max_chars: int
    key_prefix: str
    run_stamp: str
    test_id: str
    confidence: str
    label: str
    plan_table: str
    out_dir_name: str
    post_commit_residual: Residual
    rehearsal_residual: Residual
    allowed_new_values: tuple[str, ...] = ()
    premise_sql: str | None = None
    lock_timeout: str | None = None
    statement_timeout: str | None = None

    def __post_init__(self) -> None:
        """Every field that reaches SQL unquoted is checked here, once, instead of trusted."""
        if not _IDENTIFIER.match(self.column):
            raise ValueError(f"{self.column!r} is not a plain column name")
        if not _IDENTIFIER.match(self.plan_table) or not self.plan_table.startswith("_"):
            raise ValueError(f"{self.plan_table!r} is not a temp-table name of the form _name")
        if not _LABEL.match(self.label):
            raise ValueError(f"{self.label!r} cannot be spliced into a RAISE message")
        if not _KEY_PREFIX.match(self.key_prefix):
            raise ValueError(f"{self.key_prefix!r} is not a change_key prefix")
        if self.max_chars <= 0:
            raise ValueError(f"{self.name}: the column width must be positive")
        if not self.run_stamp or not self.test_id or not self.confidence:
            raise ValueError(
                f"{self.name}: a journal identity needs a stamp, a test id and a confidence"
            )
        for value in self.allowed_new_values:
            if not value or len(value) > self.max_chars:
                raise ValueError(f"{self.name}: {value!r} cannot be written into {self.column}")
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

    def change_key(self, site_id: str) -> str:
        """The journal's identity for one row's *write*.

        `change_key` names the exact transition, so the write and its reversal must not share one:
        `Georgia (country) -> Georgia` and `Georgia -> Georgia (country)` are two different
        transitions, and a single key for both makes them indistinguishable in
        `remediation_change_log` - the reversal would read as a duplicate of the write it undoes.
        """
        return f"{self.key_prefix}:{site_id}"

    def rollback_change_key(self, site_id: str) -> str:
        """The journal's identity for one row's *reversal*: G0's `-rollback` suffix, same shape."""
        return f"{self.key_prefix}-rollback:{site_id}"


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
    stamp, column = sql_literal(lane.run_stamp), sql_literal(lane.column)
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
            f"journal rows for this run outside unified_sites.{lane.column}",
            f"FROM remediation_change_log WHERE run_stamp = {stamp} "
            f"AND (table_name <> 'unified_sites' OR column_name <> {column})",
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

LANES: dict[str, Lane] = {lane.name: lane for lane in (T05, UK_PARTS, PERIOD_NAME, SITE_TYPE_SHAPE)}

#: The read-only verification per lane, except T05's: that one is `apply.VERIFY_SQL`, kept there
#: unchanged since the write it verified.
LANE_READBACKS: dict[str, str] = {
    UK_PARTS.name: UK_PARTS_READBACK,
    PERIOD_NAME.name: PERIOD_NAME_READBACK,
    SITE_TYPE_SHAPE.name: SITE_TYPE_SHAPE_READBACK,
}
