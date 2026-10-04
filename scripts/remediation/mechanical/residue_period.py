"""The owner's residue rung (2026-10-04): the label a curated site carries when nothing dates it.

`output/remediation/period_wave/residue_rule.json` (`decided_by: owner`) is the decision, written out
here because `output/` is a gitignored snapshot and a test that reads it would pass in this checkout
and fail in a clone:

* **applies to** a curated `ancient_nerds` site that carries no period after the sourced, structured
  and derived rungs have all been applied;
* **`period_name` = `Undated`, `period_start` = NULL**, marked unproven, origin in the journal
  `residue: no source, no Wikidata claim and no site_type implies a period`;
* **why**: the site gets a visible entry that states the period is not established, no year is
  invented, and the card takes no antiquity colour.

The rule is the *column's* rule, so it is stated once, in `lane.bucket_case()`: a curated row's label
is the bucket of its year, or `Undated` when it has no year. Every period lane checks it. The bucket
function itself does not learn it - `categorize_period(None)` is still `None` and the frontend's
`categorizePeriod(null)` still `Unknown`, because a row without a year is not a year.

## Two scopes, two waves

The rule has two halves, and they are two lanes so that a crash between them leaves no half-written
state and each run stamp covers exactly one decision:

* `undated` - the rows that carry **no year at all**: their label may only be *filled*, never
  overwritten (measured on production 2026-10-04 20:26: 103 rows, 83 live and 20 retired);
* `bucket` - the rows whose label **contradicts the year it sits on**: re-derived from
  `period_start` (measured the same minute: 1 row, Prambanan Temple, 850 with `1 - 500 AD`).

`period_name.py`'s own classifier is taught `Undated` so a later run of that lane does not list these
rows for review; the write is this lane's, because that lane's stamp was spent on 2026-09-22.

    residue_period.py --wave W --scope undated --write
    residue_period.py --wave W --scope bucket  --write
    apply.py --lane period-label-undated-W --emit ... --rehearse-rollback

`--write` reads production (read-only) and writes the lane's own directory: `PLAN.jsonl`,
`PLAN.md`, `SKIPPED.jsonl`, `ROLLBACK.sql`.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.lane import (  # noqa: E402
    _PERIOD_MISMATCH,
    LOCK_TIMEOUT,
    PERIOD_LABEL_LANE,
    PERIOD_LABEL_PREMISE,
    PERIOD_LABEL_TEST_ID,
    STATEMENT_TIMEOUT,
    Column,
    Lane,
    journal_readback,
    sql_literal,
)
from mechanical.period_name import frontend_rule  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    Plan,
    PlanError,
    Verdict,
    _now,
    psql_json_reader,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)
from pipeline.utils.text import PERIOD_BUCKETS, UNDATED, categorize_period  # noqa: E402

log = logging.getLogger("mechanical.residue_period")

SITES_TS = REPO / "ancient-nerds-map" / "src" / "data" / "sites.ts"
#: `undated` fills the label of a row that has no year; `bucket` re-derives a label that contradicts
#: one. Anything else is refused rather than guessed at.
SCOPES = ("undated", "bucket")
#: The row already carries the label this lane would write - the one state that is not a finding.
CONSISTENT = "consistent"
#: The row is another scope's work, or another lane's: named, listed, and not written here.
NOT_THIS_LANE = "not-this-lane"


def lane_of(scope: str, wave: str) -> Lane:
    """The lane `period-label-<scope>-<wave>`: a stamp, a test id, a table and a directory of its
    own, so no step of one scope can be mistaken for a step of the other."""
    name = f"period-label-{scope}-{wave}"
    match = PERIOD_LABEL_LANE.match(name)
    if match is None or match.group(1) != scope:
        raise ValueError(
            f"{scope!r} and {wave!r} are not a period-label lane name "
            f"(expected period-label-<{'|'.join(SCOPES)}>-<YYYY-MM-DD[a-z]>)"
        )
    return Lane(
        name=name,
        key_prefix=name,
        run_stamp=f"{wave}_period-label-{scope}",
        test_id=PERIOD_LABEL_TEST_ID,
        # The value is derived, not researched: the bucket of the site's own year, or the owner's
        # residue label. Two source families would be a claim about a source, and there is none.
        confidence="authoritative",
        label=f"period_name {scope}",
        plan_table=f"_period_label_{scope}_plan",
        out_dir_name=f"mechanical_period_label/{scope}/{wave}",
        post_commit_residual=_PERIOD_MISMATCH,
        rehearsal_residual=_PERIOD_MISMATCH,
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        cells=(
            Column(
                "period_name",
                "text",
                max_chars=100,
                allowed_new_values=(*(label for label, _lo, _hi in PERIOD_BUCKETS), UNDATED),
                # Only the residue scope fills: a label that is there is never overwritten by a row
                # that has no year (the other half of the rule is the `bucket` lane's write).
                fills_null=scope == "undated",
            ),
        ),
        premise_sql=PERIOD_LABEL_PREMISE,
    )


def readback(lane: Lane) -> str:
    """The read-only verification of a residue step, before and after its write."""
    return journal_readback(
        lane,
        [
            (
                _PERIOD_MISMATCH.metric,
                "FROM unified_sites WHERE source_id = 'ancient_nerds' "
                f"AND {_PERIOD_MISMATCH.predicate}",
            ),
            (
                "curated rows carrying the residue label",
                f"FROM unified_sites WHERE source_id = 'ancient_nerds' "
                f"AND period_name = {sql_literal(UNDATED)}",
            ),
            (
                "curated rows with the residue label and a year",
                f"FROM unified_sites WHERE source_id = 'ancient_nerds' "
                f"AND period_name = {sql_literal(UNDATED)} AND period_start IS NOT NULL",
            ),
        ],
    )


# --------------------------------------------------------------------------------- the candidates
@dataclass(frozen=True)
class Row:
    """One curated row: the label it carries and the year that label has to follow."""

    site_id: str
    name: str
    source_id: str
    period_name: str | None
    period_start: int | None
    premise: str | None


def row_sql(lane: Lane) -> str:
    return (
        "SELECT u.id::text AS id, u.name, u.source_id, u.period_name, u.period_start, "
        f"{lane.premise_sql} AS premise FROM unified_sites u "
        f"WHERE u.source_id = {sql_literal(CURATED_SOURCE)} ORDER BY u.id"
    )


def load_rows(reader: Callable[[str], list[dict[str, Any]]], lane: Lane) -> list[Row]:
    """Every curated row, read from production - read-only."""
    raw = reader(row_sql(lane))
    if not raw:
        raise PlanError("no curated row was read - refusing to plan against an empty set")
    return [
        Row(
            site_id=str(r["id"]),
            name=str(r["name"]),
            source_id=str(r["source_id"]),
            period_name=r["period_name"],
            period_start=None if r["period_start"] is None else int(r["period_start"]),
            premise=r["premise"],
        )
        for r in raw
    ]


# ------------------------------------------------------------------------------------ the decision
def classify(row: Row, *, scope: str, frontend: Callable[[int], str]) -> Verdict:
    """Decide one row. Every refusal carries its measured reason, and the premise of a write is the
    live year it was derived from (guard 5).

    `frontend` is the TypeScript `categorizePeriod` read out of `sites.ts`: two implementations of
    one rule, and a bucket they disagree about is a defect to fix, not a value to pick.
    """
    if scope not in SCOPES:
        raise PlanError(f"{scope!r} is not one of {SCOPES}")

    def verdict(ok: bool, reason: str, note: str, **kw: Any) -> Verdict:
        return Verdict(
            site_id=row.site_id,
            site_name=row.name,
            ok=ok,
            old_value=row.period_name,
            new_value=kw.get("new_value"),
            rule=kw.get("rule", ""),
            reason=reason,
            note=note,
            phase3=False,
            finding_test_id="live:unified_sites.period_name",
            evidence=kw.get("evidence", ()),
            premise=row.premise if ok else None,
            column="period_name" if ok else None,
        )

    if row.source_id != CURATED_SOURCE:
        return verdict(
            False,
            "row-not-in-curated-source",
            f"the row belongs to source_id={row.source_id!r}; this lane writes curated sites only",
        )

    if row.period_start is None:
        if row.period_name == UNDATED:
            return verdict(False, CONSISTENT, f"no year and the residue label {UNDATED!r}")
        if row.period_name:
            return verdict(
                False,
                "no-period-start",
                f"the row carries {row.period_name!r} but no year to derive it from; a label "
                f"without a year is a contradiction for a person, not a value to overwrite",
            )
        if scope != "undated":
            return verdict(
                False,
                NOT_THIS_LANE,
                "no year: the residue label is the `undated` lane's write, not this lane's",
            )
        return verdict(
            True,
            "",
            f"no source, no Wikidata claim and no site_type dates it: {UNDATED!r} with no year",
            new_value=UNDATED,
            rule="residue-label",
            evidence=(
                {
                    "source": "output/remediation/period_wave/residue_rule.json",
                    "url": "output/remediation/period_wave/residue_rule.json",
                    "quote": '"period_name": "Undated", "period_start": null, "marked_unproven": true',
                },
                {
                    "source": "pipeline/utils/text.py",
                    "url": "pipeline/utils/text.py",
                    "quote": f'UNDATED = "{UNDATED}"',
                },
            ),
        )

    bucket = categorize_period(row.period_start)
    if row.period_name == bucket:
        return verdict(False, CONSISTENT, f"{row.period_name!r} is the bucket of {row.period_start}")
    if frontend(row.period_start) != bucket:
        return verdict(
            False,
            "implementations-disagree",
            f"categorize_period({row.period_start}) is {bucket!r} and the frontend's "
            f"categorizePeriod is {frontend(row.period_start)!r}; the two implementations of one "
            "rule must agree before a value is written from either",
        )
    if scope != "bucket":
        return verdict(
            False,
            NOT_THIS_LANE,
            f"period_start {row.period_start}: the label {row.period_name!r} contradicts it, which is "
            "the `bucket` lane's write, not this lane's",
        )
    return verdict(
        True,
        "",
        f"period_start {row.period_start}: {row.period_name!r} -> {bucket!r}",
        new_value=bucket,
        rule="bucket-of-period-start",
        evidence=(
            {
                "source": "pipeline/utils/text.py",
                "url": "pipeline/utils/text.py",
                "quote": f"categorize_period({row.period_start}) = {bucket!r}",
            },
            {
                "source": "ancient-nerds-map/src/data/sites.ts",
                "url": "ancient-nerds-map/src/data/sites.ts",
                "quote": f"categorizePeriod({row.period_start}) = {bucket!r}",
            },
        ),
    )


def build_plan(lane: Lane, rows: Sequence[Row], *, frontend: Callable[[int], str]) -> Plan:
    """A pure function of its inputs: no database, no clock of its own."""
    scope = lane.name.split("-")[2]
    verdicts = [classify(row, scope=scope, frontend=frontend) for row in sorted(rows, key=lambda r: r.site_id)]
    changes = tuple(v for v in verdicts if v.ok)
    consistent = sum(1 for v in verdicts if not v.ok and v.reason == CONSISTENT)
    skipped = tuple(v for v in verdicts if not v.ok and v.reason != CONSISTENT)
    counters: Mapping[str, int] = {
        "rows": len(verdicts),
        "changes": len(changes),
        "consistent": consistent,
        "skipped": len(skipped),
        **{f"skip:{k}": n for k, n in sorted(Counter(s.reason for s in skipped).items())},
    }
    return Plan(changes=changes, skipped=skipped, built_at=_now(), counters=dict(counters), lane=lane)


# -------------------------------------------------------------------------------------- the output
def write_plan_md(plan: Plan, path: Path, *, scope: str) -> None:
    add = (lines := []).append
    add(f"# The residue rung: `period_name` {scope} - plan")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/residue_period.py`. Lane "
        f"`{plan.lane.name}`: run stamp `{plan.lane.run_stamp}`, journal test id "
        f"`{plan.lane.test_id}`, change keys `{plan.lane.key_prefix}:<site_id>`, premise "
        f"`{plan.lane.premise_sql}`."
    )
    add("")
    what = (
        "the rows that carry no year at all get the residue label, and only a NULL or empty label is "
        "written (the cell may be filled, never overwritten)"
        if scope == "undated"
        else "the rows whose label contradicts the year they sit on get the bucket of that year"
    )
    add(f"**{len(plan.changes)} row(s) will be written, {plan.counters['consistent']} already carry " f"this lane's label, {len(plan.skipped)} listed.** What this wave does: {what}.")
    add("")
    add("The rule is the owner's (`output/remediation/period_wave/residue_rule.json`, 2026-10-04):")
    add("")
    add("> a curated site that carries no period after the sourced, structured and derived rungs gets")
    add("> `period_name = \"Undated\"` and no year - a visible entry that states the period is not")
    add("> established, no year invented, and the card takes no antiquity colour.")
    add("")
    add("| stored period_name | written period_name | rows |")
    add("|---|---|---|")
    for (old, new), n in sorted(
        Counter((c.old_value, c.new_value) for c in plan.changes).items(), key=lambda kv: (-kv[1], kv[0])
    ):
        add(f"| `{old}` | `{new}` | {n} |")
    add("")
    add("## Every row")
    add("")
    add("| site | period_start | stored | written |")
    add("|---|---|---|---|")
    for c in sorted(plan.changes, key=lambda c: c.site_name):
        add(f"| {c.site_name} (`{c.site_id}`) | {c.premise} | `{c.old_value}` | `{c.new_value}` |")
    add("")
    if plan.skipped:
        add("## Not written by this wave")
        add("")
        add("| site | reason | note |")
        add("|---|---|---|")
        for s in plan.skipped:
            add(f"| {s.site_name} | `{s.reason}` | {s.note} |")
        add("")
    add("## What a reader must know afterwards")
    add("")
    add(
        "* The card generator reads `period_name` for `card_stats.mystery` and the rarity, so a "
        "card_stats wave follows this one (runbook 4.6 step 14); the `antiquity` stat reads "
        "`period_start` and is unchanged, because a row with no year already took its default."
    )
    add(
        "* The frontend labels a site with `period_name` and colours it from `period_start`, so "
        f"`{UNDATED}` shows as a grey badge with no antiquity colour - which is the rule's `why`."
    )
    add(
        "* Qdrant's change hash includes `period_name`; the next nightly sync picks these rows up."
    )
    add("")
    add("## Reproduce")
    add("")
    add("```bash")
    add(f"./.venv/Scripts/python.exe scripts/remediation/mechanical/residue_period.py --wave {plan.lane.run_stamp.split('_')[0]} --scope {scope} --write")
    add("./.venv/Scripts/python.exe -m pytest tests/remediation/test_residue_period.py -q -rs")
    add("```")
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------- the CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the owner's residue rung for period_name")
    ap.add_argument("--wave", required=True, help="a wave label, 2026-10-04 or 2026-10-04b")
    ap.add_argument("--scope", required=True, choices=SCOPES)
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--write",
        action="store_true",
        help="write PLAN.jsonl, PLAN.md, SKIPPED.jsonl, ROLLBACK.sql (reads prod, read-only)",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.write:
        ap.print_help()
        return 0
    lane = lane_of(args.scope, args.wave)
    # The frontend's own comparisons, read from its source: two implementations of one rule, and a
    # disagreement is a defect to fix, not a value to pick.
    frontend = frontend_rule(SITES_TS.read_text(encoding="utf-8"))
    plan = build_plan(lane, load_rows(psql_json_reader(), lane), frontend=frontend)
    # Guard 5 conditions the write on the live premise, so the value must follow from *that* input.
    # A residue label has no input to follow from; every other value must be the bucket of its own.
    for change in plan.changes:
        if change.new_value == UNDATED:
            continue
        shown = frontend(int(change.premise or ""))
        if shown != change.new_value:
            raise PlanError(
                f"{change.site_name} ({change.site_id}): the plan writes {change.new_value!r} for "
                f"period_start {change.premise}, and the frontend's own rule answers {shown!r} - "
                "refusing to emit a value the two implementations of the rule do not share"
            )
    out = args.out or (REPO / "output" / "remediation" / lane.out_dir_name)
    out.mkdir(parents=True, exist_ok=True)
    rows = write_plan_jsonl(plan, out / "PLAN.jsonl")
    skipped = write_skipped_jsonl(plan, out / "SKIPPED.jsonl")
    write_plan_md(plan, out / "PLAN.md", scope=args.scope)
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo.
    write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    log.info("PLAN.jsonl %d, SKIPPED.jsonl %d", rows, skipped)
    print(json.dumps(dict(plan.counters), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
