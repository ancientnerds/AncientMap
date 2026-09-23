"""Does the period lane write exactly the bucket of `period_start` - and refuse everything else?

The planner and its lane are pure: rows in, verdicts out, with the pipeline's own
`categorize_period` and the frontend's `categorizePeriod` read from `sites.ts`. No database, no
network, no geo stack, so every test here runs in CI as well. Each refusal has a mutation case in
`mechanical/mutation_sweep.py`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import period_name as PN  # noqa: E402
from mechanical import plan as P  # noqa: E402

from pipeline.utils.text import PERIOD_BUCKETS, categorize_period  # noqa: E402

DELIVERED = REPO / "output" / "remediation" / "mechanical_period_name" / "PLAN.jsonl"
needs_plan = pytest.mark.skipif(not DELIVERED.exists(), reason=f"{DELIVERED} not built yet")

SITE = "17cf019a-0000-4000-8000-000000000001"


@pytest.fixture(scope="module")
def frontend() -> Any:
    return PN.frontend_rule(PN.SITES_TS.read_text(encoding="utf-8"))


def row(
    period_name: str | None = "1 - 500 AD",
    period_start: int | None = 1537,
    *,
    source_id: str = P.CURATED_SOURCE,
    name_journal: tuple[P.JournalLink, ...] = (),
    start_journal: tuple[P.JournalLink, ...] = (),
) -> PN.Row:
    """Damascus Gate's shape: phase 3 moved period_start 1 -> 1537, the label stayed."""
    return PN.Row(
        site_id=SITE,
        name="Damascus Gate",
        source_id=source_id,
        period_name=period_name,
        period_start=period_start,
        premise=None if period_start is None else str(period_start),
        name_journal=name_journal,
        start_journal=start_journal,
    )


def decide(frontend: Any, r: PN.Row, derive: Any = categorize_period) -> P.Verdict:
    return PN.classify_period(r, derive=derive, frontend=frontend)


PHASE3 = P.JournalLink(29001, "phase3:batch-0100:chunk-0001", "P3/period_start", "1", "1537")


class TestTheFrontendRule:
    @pytest.mark.parametrize(
        "year", [-1_400_000, -4501, -4500, -3000, -1500, -500, 0, 1, 499, 500, 1499, 1500, 1760]
    )
    def test_the_frontend_rule_is_read_and_agrees_with_the_pipeline(
        self, frontend: Any, year: int
    ) -> None:
        assert frontend(year) == categorize_period(year)

    def test_a_source_without_the_function_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="not defined"):
            PN.frontend_rule("export function somethingElse() {}\n")

    def test_a_function_without_comparisons_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="could not be read"):
            PN.frontend_rule("export function categorizePeriod(start) {\n  return 'x'\n}\n")


class TestClassifyPeriod:
    def test_a_label_left_behind_is_written_as_the_bucket(self, frontend: Any) -> None:
        verdict = decide(frontend, row(start_journal=(PHASE3,)))
        assert verdict.ok and verdict.new_value == "1500+ AD" and verdict.old_value == "1 - 500 AD"
        assert verdict.premise == "1537" and verdict.phase3
        sources = [e["source"] for e in verdict.evidence]
        assert "pipeline/utils/text.py:categorize_period" in sources
        assert "ancient-nerds-map/src/data/sites.ts:categorizePeriod" in sources
        assert "output/remediation/gold_standard/GOLD_STANDARD.md:79" in sources
        assert "remediation_change_log:29001" in sources

    def test_a_non_canonical_label_is_written_as_the_bucket(self, frontend: Any) -> None:
        """Bayer's Lake Mystery Walls: 1760, stored '> 1500 AD'."""
        verdict = decide(frontend, row("> 1500 AD", 1760))
        assert verdict.ok and verdict.new_value == "1500+ AD" and not verdict.phase3

    def test_the_deep_past_is_consistent(self, frontend: Any) -> None:
        """Atapuerca at -1,400,000 is '< 4500 BC'; before 2026-09-22 the pipeline said
        '1500+ AD' and this lane would have written that onto three sites."""
        verdict = decide(frontend, row("< 4500 BC", -1_400_000))
        assert not verdict.ok and verdict.reason == PN.CONSISTENT

    def test_a_label_that_is_already_the_bucket_is_consistent(self, frontend: Any) -> None:
        verdict = decide(frontend, row("1500+ AD", 1537))
        assert not verdict.ok and verdict.reason == PN.CONSISTENT

    def test_no_year_and_no_label_is_consistent(self, frontend: Any) -> None:
        verdict = decide(frontend, row(None, None))
        assert not verdict.ok and verdict.reason == PN.CONSISTENT

    def test_a_label_without_a_year_is_refused(self, frontend: Any) -> None:
        verdict = decide(frontend, row("1 - 500 AD", None))
        assert not verdict.ok and verdict.reason == "no-period-start"

    def test_a_year_without_a_label_is_refused(self, frontend: Any) -> None:
        verdict = decide(frontend, row(None, 1537))
        assert not verdict.ok and verdict.reason == "no-period-name"

    def test_two_implementations_that_disagree_refuse(self, frontend: Any) -> None:
        verdict = decide(frontend, row(), derive=lambda year: "1000 - 1500 AD")
        assert not verdict.ok and verdict.reason == "implementations-disagree"

    def test_a_row_of_another_source_is_refused(self, frontend: Any) -> None:
        verdict = decide(frontend, row(source_id="lyra"))
        assert not verdict.ok and verdict.reason == "row-not-in-curated-source"

    def test_a_period_start_written_around_the_journal_is_refused(self, frontend: Any) -> None:
        stale = P.JournalLink(29001, "phase3:x", "P3/period_start", "1", "1400")
        verdict = decide(frontend, row(start_journal=(stale,)))
        assert not verdict.ok and verdict.reason == "journal-disagrees"
        assert verdict.note.startswith("period_start:")

    def test_a_period_name_written_around_the_journal_is_refused(self, frontend: Any) -> None:
        stale = P.JournalLink(29002, "earlier-lane", "X", "500 - 1000 AD", "1000 - 1500 AD")
        verdict = decide(frontend, row(name_journal=(stale,)))
        assert not verdict.ok and verdict.reason == "journal-disagrees"
        assert verdict.note.startswith("period_name:")


class TestBuildPeriodPlan:
    def test_the_plan_is_a_partition_with_its_counters(self, frontend: Any) -> None:
        rows = [
            row(start_journal=(PHASE3,)),
            PN.Row(SITE.replace("0001", "0002"), "B", P.CURATED_SOURCE, "1500+ AD", 1537, "1537"),
            PN.Row(SITE.replace("0001", "0003"), "C", P.CURATED_SOURCE, "1 - 500 AD", None, None),
        ]
        result = PN.build_period_plan(
            rows, derive=categorize_period, frontend=frontend, built_at="2026-09-22T00:00:00+00:00"
        )
        assert len(result.plan.changes) == 1 and result.consistent == 1
        assert len(result.plan.skipped) == 1
        assert result.counters["skip:no-period-start"] == 1
        assert result.counters["changes_after_a_phase3_period_start"] == 1
        assert result.plan.lane is L.PERIOD_NAME


class TestTheLane:
    def test_the_lane_owns_exactly_the_nine_buckets(self) -> None:
        assert L.PERIOD_NAME.allowed_new_values == tuple(label for label, _, _ in PERIOD_BUCKETS)
        assert "> 1500 AD" not in L.PERIOD_NAME.allowed_new_values

    def test_the_sql_bucket_is_the_frontend_bucket(self, frontend: Any) -> None:
        case = L.bucket_case()
        steps = [
            (int(b), label)
            for b, label in re.findall(r"WHEN period_start < (-?\d+) THEN '([^']+)'", case)
        ]
        assert steps, case
        assert "WHEN period_start IS NULL THEN NULL" in case
        tail = re.search(r"ELSE '([^']+)' END", case).group(1)  # type: ignore[union-attr]

        def sql_bucket(year: int) -> str:
            for bound, label in steps:
                if year < bound:
                    return label
            return tail

        for year in (
            -1_400_000,
            -4501,
            -4500,
            -3000,
            -1501,
            -1500,
            -500,
            0,
            1,
            500,
            1000,
            1500,
            2014,
        ):
            assert sql_bucket(year) == frontend(year), year

    def test_the_statement_guards_the_buckets_and_the_year(self) -> None:
        record = A.ChangeRecord(
            site_id=SITE,
            site_name="Damascus Gate",
            old_value="1 - 500 AD",
            new_value="1500+ AD",
            rule="bucket-of-period-start",
            condition="",
            reason="period-name-bucket: x",
            evidence=({"source": "test", "quote": "x"},),
            premise="1537",
        )
        sql = A.render_transaction([record], site_ids={SITE}, lane=L.PERIOD_NAME)
        assert "'unified_sites', 'period_name', 'id', r.site_id::text," in sql
        assert "WHERE (u.period_start::text) IS DISTINCT FROM p.premise;" in sql
        assert "'< 4500 BC'" in sql and "'1500+ AD'" in sql and "scope guard 4" in sql
        assert f"'period-name-bucket:{SITE}'" in sql and "'P6/period-name-bucket'" in sql
        with pytest.raises(P.PlanError, match="is not a value the period-name lane owns"):
            A.validate_records(
                [A.ChangeRecord(**{**record.__dict__, "new_value": "> 1500 AD"})],
                lane=L.PERIOD_NAME,
            )

    def test_the_readback_names_the_period_run(self) -> None:
        readback = A.READBACKS[L.PERIOD_NAME.name]
        assert f"'{L.PERIOD_NAME.run_stamp}'" in readback
        assert "period_name IS DISTINCT FROM (CASE WHEN period_start IS NULL" in readback


@needs_plan
class TestTheDeliveredPlan:
    def test_220_rows_each_the_bucket_of_its_premise(self) -> None:
        records = A.load_records(DELIVERED)
        A.validate_records(records, lane=L.PERIOD_NAME)
        assert len(records) == 220
        for r in records:
            assert r.premise is not None
            assert r.new_value == categorize_period(int(r.premise)), r.site_name
            assert r.new_value != r.old_value
        assert sum(1 for r in records if r.phase3) == 219

    def test_every_record_names_the_rule_and_its_lane(self) -> None:
        for line in DELIVERED.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            assert payload["column"] == "period_name"
            assert payload["run_stamp"] == L.PERIOD_NAME.run_stamp
            assert payload["premise_sql"] == L.PERIOD_NAME.premise_sql
            sources = {e["source"] for e in payload["evidence"]}
            assert {"pipeline/utils/text.py:categorize_period", PN.RULE[0]} <= sources

    def test_the_rollback_reverses_every_row(self) -> None:
        records = A.load_records(DELIVERED)
        rollback = (DELIVERED.parent / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert f"'{L.PERIOD_NAME.rollback_run_stamp}'" in rollback
        body = rollback.split("INSERT INTO _period_name_plan", 1)[1].split("\n;\n", 1)[0]
        rows = [line for line in body.splitlines() if line.strip().startswith("('")]
        assert len(rows) == len(records)
        for r in records:
            (line,) = [x for x in rows if r.site_id in x]
            assert f"{P.sql_literal(r.new_value)}, {P.sql_literal(r.old_value)}" in line
