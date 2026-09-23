"""Phase 6 item 2: re-derive `unified_sites.period_name` from `period_start` - the period lane.

## The defect

The gold standard's rule for the column is `period_name == categorize_period(period_start)`
(`output/remediation/gold_standard/GOLD_STANDARD.md:79`). Phase 3 corrected 389 `period_start`
values and left 219 of their labels in another bucket; one more row (Bayer's Lake Mystery Walls,
1760) carries the non-canonical `> 1500 AD`. Measured read-only on production 2026-09-22: 220
curated rows disagree. The frontend labels a site with `period_name` but colours it and filters it
by `period_start` (`ancient-nerds-map/src/data/sites.ts`), so these rows show a label that
contradicts their own colour; the label also feeds `card_stats` and the Qdrant payload.

## How a row is decided (`classify_period`, first failure refuses)

1. curated rows only; 2. a row with no `period_start` has no bucket: consistent when its label is
   empty too, refused for review when it carries one (this lane never clears a column);
3. the bucket is the pipeline's own `categorize_period` - imported, never copied - and it must
   equal the frontend's `categorizePeriod`, read from `sites.ts` (two implementations of one rule;
   a disagreement is a defect to fix, not a value to pick); 4. a label that already is the bucket
   is consistent; 5. a row with no label to condition the write on is refused;
6. the journal of `period_name` and of `period_start` must both end at the live values - a value
   written around the journal is not one this lane will build on.

Every write carries its premise, the `period_start` it was derived from as the database prints it,
so the transaction refuses a row whose year changed after this plan (guard 5), and the lane owns
the nine bucket labels only (guard 4).

`--write` reads production (read-only) and writes `output/remediation/mechanical_period_name/`:
`PLAN.jsonl`, `PLAN.md`, `SKIPPED.jsonl`, `ROLLBACK.sql`. Re-run it after every later
`period_start` write. `apply.py --lane period-name` renders and runs the transaction.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.lane import PERIOD_NAME, sql_literal  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    _now,
    journal_break,
    load_journal,
    psql_json_reader,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)
from pipeline.utils.text import categorize_period  # noqa: E402

log = logging.getLogger("mechanical.period_name")

LANE = PERIOD_NAME
DEFAULT_OUT = REPO / "output" / "remediation" / LANE.out_dir_name
SITES_TS = REPO / "ancient-nerds-map" / "src" / "data" / "sites.ts"
CONSISTENT = "consistent"
RULE = (
    "output/remediation/gold_standard/GOLD_STANDARD.md:79",
    "| `period_name` | equals `categorize_period(period_start)` | inconsistent with `period_start` |",
)


# ---------------------------------------------------------------------- the frontend's rule
def frontend_rule(source: str) -> Callable[[int], str]:
    """`categorizePeriod` from `sites.ts`, as a function: its comparisons, read, not copied."""
    body = source.split("export function categorizePeriod", 1)
    if len(body) != 2:
        raise PlanError("categorizePeriod is not defined in sites.ts")
    text = body[1].split("\n}", 1)[0]
    steps = [
        (int(b), label) for b, label in re.findall(r"if \(start < (-?\d+)\) return '([^']+)'", text)
    ]
    last = re.search(r"\n\s+return '([^']+)'\s*$", text)
    if not steps or last is None:
        raise PlanError("categorizePeriod's comparisons could not be read from sites.ts")
    tail = last.group(1)

    def bucket(year: int) -> str:
        for bound, label in steps:
            if year < bound:
                return label
        return tail

    return bucket


# ------------------------------------------------------------------------------ the candidates
@dataclass(frozen=True)
class Row:
    """One curated row: the label, the year it should follow, and both fields' journals."""

    site_id: str
    name: str
    source_id: str
    period_name: str | None
    period_start: int | None
    premise: str | None
    name_journal: tuple[JournalLink, ...] = ()
    start_journal: tuple[JournalLink, ...] = ()


ROW_SQL = (
    "SELECT u.id::text AS id, u.name, u.source_id, u.period_name, u.period_start, "
    f"{LANE.premise_sql} AS premise FROM unified_sites u "
    f"WHERE u.source_id = {sql_literal(CURATED_SOURCE)} ORDER BY u.id"
)


def load_rows(reader: Callable[[str], list[dict[str, Any]]]) -> list[Row]:
    """Every curated row with both journals, read from production - read-only."""
    raw = reader(ROW_SQL)
    if not raw:
        raise PlanError("no curated row was read - refusing to plan against an empty set")
    ids = [str(r["id"]) for r in raw]
    names = load_journal(reader, "period_name", ids)
    starts = load_journal(reader, "period_start", ids)
    return [
        Row(
            site_id=str(r["id"]),
            name=str(r["name"]),
            source_id=str(r["source_id"]),
            period_name=r["period_name"],
            period_start=None if r["period_start"] is None else int(r["period_start"]),
            premise=r["premise"],
            name_journal=names.get(str(r["id"]), ()),
            start_journal=starts.get(str(r["id"]), ()),
        )
        for r in raw
    ]


# ------------------------------------------------------------------------------ the decision
@dataclass(frozen=True)
class PeriodPlan:
    plan: Plan
    consistent: int
    counters: Mapping[str, int] = field(default_factory=dict)


def classify_period(
    row: Row, *, derive: Callable[[int | None], str | None], frontend: Callable[[int], str]
) -> Verdict:
    """Decide one row. Every check is named, and the first failure is the reason."""
    last_start = row.start_journal[-1] if row.start_journal else None
    phase3 = last_start is not None and last_start.run_stamp.startswith("phase3:")

    def verdict(
        ok: bool, reason: str, note: str, evidence: Sequence[dict[str, Any]] = (), **kw: Any
    ) -> Verdict:
        return Verdict(
            site_id=row.site_id,
            site_name=row.name,
            ok=ok,
            old_value=row.period_name,
            new_value=kw.get("new_value"),
            rule=kw.get("rule", ""),
            reason=reason,
            note=note,
            phase3=phase3,
            finding_test_id="live:unified_sites.period_name",
            evidence=tuple(evidence),
            premise=row.premise if ok else None,
        )

    if row.source_id != CURATED_SOURCE:
        return verdict(
            False,
            "row-not-in-curated-source",
            f"the row belongs to source_id={row.source_id!r}; this lane writes curated sites only",
        )
    if row.period_start is None:
        if row.period_name is None:
            return verdict(False, CONSISTENT, "no period_start and no period_name")
        return verdict(
            False,
            "no-period-start",
            f"the row carries {row.period_name!r} but no period_start to derive it from; this lane "
            "never clears the column",
        )
    bucket = derive(row.period_start)
    shown = frontend(row.period_start)
    if bucket != shown:
        return verdict(
            False,
            "implementations-disagree",
            f"categorize_period({row.period_start}) = {bucket!r} but the frontend's "
            f"categorizePeriod shows {shown!r} - one of the two implementations is wrong",
        )
    if bucket == row.period_name:
        return verdict(
            False, CONSISTENT, f"{row.period_name!r} is the bucket of {row.period_start}"
        )
    if not row.period_name:
        return verdict(
            False,
            "no-period-name",
            f"the row has period_start {row.period_start} but no period_name to condition the "
            "write on - hand review",
        )
    for field_name, links, live in (
        ("period_name", row.name_journal, row.period_name),
        ("period_start", row.start_journal, str(row.period_start)),
    ):
        broken = journal_break(links, live)
        if broken is not None:
            reason, note = broken
            return verdict(False, reason, f"{field_name}: {note}")

    evidence: list[dict[str, Any]] = [
        {
            "source": "pipeline/utils/text.py:categorize_period",
            "url": "pipeline/utils/text.py",
            "quote": f"categorize_period({row.period_start}) = {bucket!r}",
        },
        {
            "source": "ancient-nerds-map/src/data/sites.ts:categorizePeriod",
            "url": "ancient-nerds-map/src/data/sites.ts",
            "quote": f"categorizePeriod({row.period_start}) = {shown!r} (the globe's colour and filter)",
        },
        {
            "source": RULE[0],
            "url": "output/remediation/gold_standard/GOLD_STANDARD.md",
            "quote": RULE[1],
        },
    ]
    if last_start is not None:
        evidence.append(
            {
                "source": f"remediation_change_log:{last_start.id}",
                "url": "remediation_change_log",
                "quote": f"{last_start.run_stamp} ({last_start.test_id}): period_start "
                f"{last_start.old_value!r} -> {last_start.new_value!r} - the write that left the "
                "label behind",
            }
        )
    return verdict(
        True,
        "",
        f"period_start {row.period_start}: {row.period_name!r} -> {bucket!r}",
        evidence,
        new_value=bucket,
        rule="bucket-of-period-start",
    )


def build_period_plan(
    rows: Sequence[Row],
    *,
    derive: Callable[[int | None], str | None],
    frontend: Callable[[int], str],
    built_at: str,
) -> PeriodPlan:
    """A pure function of its inputs: no database, no clock of its own."""
    verdicts = [
        classify_period(row, derive=derive, frontend=frontend)
        for row in sorted(rows, key=lambda r: r.site_id)
    ]
    changes = tuple(v for v in verdicts if v.ok)
    consistent = sum(1 for v in verdicts if not v.ok and v.reason == CONSISTENT)
    skipped = tuple(v for v in verdicts if not v.ok and v.reason != CONSISTENT)
    counters: dict[str, int] = {
        "rows": len(verdicts),
        "changes": len(changes),
        "consistent": consistent,
        "skipped": len(skipped),
        "changes_after_a_phase3_period_start": sum(1 for c in changes if c.phase3),
        **{f"skip:{k}": n for k, n in sorted(Counter(s.reason for s in skipped).items())},
    }
    plan = Plan(changes=changes, skipped=skipped, built_at=built_at, counters=counters, lane=LANE)
    return PeriodPlan(plan=plan, consistent=consistent, counters=counters)


# ------------------------------------------------------------------------------ the output
def write_plan_md(result: PeriodPlan, path: Path) -> None:
    plan = result.plan
    add = (lines := []).append
    add("# Phase 6 item 2 - period_name re-derived from period_start: plan")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/period_name.py`. Lane "
        f"`{LANE.name}`: run stamp `{LANE.run_stamp}`, journal test id `{LANE.test_id}`, change keys "
        f"`{LANE.key_prefix}:<site_id>`, premise `{LANE.premise_sql}`."
    )
    add("")
    add(
        f"**{len(plan.changes)} row(s) will be written, {result.consistent} already carry their "
        f"bucket, {len(plan.skipped)} refused.** {result.counters['changes_after_a_phase3_period_start']} "
        "of the written rows had their `period_start` corrected by phase 3; the journal row is named "
        "in each record's evidence."
    )
    add("")
    add("The rule is the gold standard's: " + RULE[1])
    add("")
    add("| stored period_name | written period_name | rows |")
    add("|---|---|---|")
    for (old, new), n in sorted(
        Counter((c.old_value, c.new_value) for c in plan.changes).items(),
        key=lambda kv: (-kv[1], kv[0]),
    ):
        add(f"| `{old}` | `{new}` | {n} |")
    add("")
    add("## Every row")
    add("")
    add("| site | period_start | stored | written | phase 3 |")
    add("|---|---|---|---|---|")
    for c in sorted(plan.changes, key=lambda c: c.site_name):
        add(
            f"| {c.site_name} (`{c.site_id}`) | {c.premise} | `{c.old_value}` | `{c.new_value}` | "
            f"{'yes' if c.phase3 else ''} |"
        )
    add("")
    if plan.skipped:
        add("## Refusals")
        add("")
        add("| site | reason | note |")
        add("|---|---|---|")
        for s in plan.skipped:
            add(f"| {s.site_name} | `{s.reason}` | {s.note} |")
        add("")
    add("## Residuals and consumers")
    add("")
    add(
        "* `card_stats.mystery` and the card rarity read `period_name` through the combo counts; "
        "they change only when the card generator runs (Phase 6 item 4, the owner's call)."
    )
    add(
        "* Qdrant's change hash includes `period_name`, so the next nightly sync picks these rows up; "
        "rows whose `period_start` changed but whose label did not stay stale there (Phase 6 item 6)."
    )
    add("* Re-run this planner after every later `period_start` write.")
    add("")
    add("## Reproduce")
    add("")
    add("```bash")
    add("./.venv/Scripts/python.exe scripts/remediation/mechanical/period_name.py --write")
    add(
        "./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_period_name.py -q -rs"
    )
    add("```")
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the period_name re-derivation (mechanical lane)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
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
    result = build_period_plan(
        load_rows(psql_json_reader()),
        derive=categorize_period,
        frontend=frontend_rule(SITES_TS.read_text(encoding="utf-8")),
        built_at=_now(),
    )
    args.out.mkdir(parents=True, exist_ok=True)
    rows = write_plan_jsonl(result.plan, args.out / "PLAN.jsonl")
    skipped = write_skipped_jsonl(result.plan, args.out / "SKIPPED.jsonl")
    write_plan_md(result, args.out / "PLAN.md")
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo.
    write_rollback_sql(result.plan, args.out / "ROLLBACK.sql", plan_path=args.out / "PLAN.jsonl")
    log.info("PLAN.jsonl %d, SKIPPED.jsonl %d, consistent %d", rows, skipped, result.consistent)
    print(json.dumps(dict(result.counters), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
