"""The owner's residue rung (2026-10-04): a curated site no source, no Wikidata claim and no
site_type dates carries the label `Undated` and no year - a visible entry that says the period is
not established, and never an invented year (`output/remediation/period_wave/residue_rule.json`,
`decided_by: owner`).

`residue_rule.json` lives in a gitignored snapshot, so what is decided here is written out: the
label is the word `Undated`, it is **not** a bucket (a year maps to a bucket, and this carries no
year - `categorize_period(None)` still answers `None`, and the frontend's `categorizePeriod(null)`
still answers `Unknown`), and the two scopes keep their work apart so each is one journalled wave:

* `undated` writes the residue label on the rows that have no year at all (103 measured on
  production 2026-10-04 20:26: 83 live, 20 retired);
* `bucket` re-derives a label that contradicts the year it sits on (1 measured: Prambanan Temple,
  850 with `1 - 500 AD`).

The rule lives in a lane of its own, never in the bucket function: `bucket_edge` and
`categorize_period` answer "which bucket is this year in", and a row without a year is not a year.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import lane as L  # noqa: E402
from mechanical import period_name as PN  # noqa: E402
from mechanical import residue_period as RP  # noqa: E402
from mechanical.plan import CURATED_SOURCE  # noqa: E402

from pipeline.utils.text import PERIOD_BUCKETS, UNDATED, categorize_period  # noqa: E402

WAVE = "2026-10-04"
PRAMBANAN = "21bd525e-fe10-40dd-96be-32d3c8d36d26"


@pytest.fixture(scope="module")
def frontend():
    """The frontend's own `categorizePeriod`, read from `sites.ts` - the same call the planner
    makes, so a test never asserts against a copy of the rule."""
    return PN.frontend_rule(PN.SITES_TS.read_text(encoding="utf-8"))


def row(**kw) -> RP.Row:
    base = {
        "site_id": "00000000-0000-4000-8000-000000000001",
        "name": "Site",
        "source_id": CURATED_SOURCE,
        "period_name": None,
        "period_start": None,
        "premise": None,
    }
    base.update(kw)
    return RP.Row(**base)


class TestTheResidueLabel:
    def test_it_is_the_owners_word_and_not_a_bucket(self) -> None:
        """`residue_rule.json`: `period_name: "Undated"`, marked unproven, no year invented."""
        assert UNDATED == "Undated"
        assert UNDATED not in {label for label, _lo, _hi in PERIOD_BUCKETS}

    def test_a_year_is_still_a_bucket_and_no_year_is_still_none(self) -> None:
        """The residue label is a lane value, not a bucket: the function that answers "which bucket
        is this year in" must not learn it, or every caller of `categorize_period` would start
        printing a label for rows that have no year."""
        assert categorize_period(850) == "500 - 1000 AD"
        assert categorize_period(None) is None


class TestTheLane:
    def test_each_scope_and_wave_is_a_lane_of_its_own(self) -> None:
        for scope in RP.SCOPES:
            lane = RP.lane_of(scope, WAVE)
            assert lane.name == f"period-label-{scope}-{WAVE}"
            assert lane.run_stamp == f"{WAVE}_period-label-{scope}"
            assert lane.plan_table == f"_period_label_{scope}_plan"
            assert lane.out_dir_name == f"mechanical_period_label/{scope}/{WAVE}"
            assert lane.key_prefix == lane.name
            assert lane.test_id == "period-label/residue"
            # one stamp per lane, and the label is authoritative for the owner, not two source
            # families (the value is derived, not researched)
            assert lane.confidence == "authoritative"

    def test_the_lane_owns_every_bucket_and_the_residue_label(self) -> None:
        """A cell lane carries its owned values on the cell, not on the lane: the lane field is
        for column lanes and stays empty here."""
        lane = RP.lane_of("undated", WAVE)
        assert lane.allowed_new_values == ()
        assert lane.cells[0].allowed_new_values == (
            *(label for label, _lo, _hi in PERIOD_BUCKETS),
            UNDATED,
        )

    def test_it_writes_one_column_and_only_fills_it(self) -> None:
        lane = RP.lane_of("undated", WAVE)
        assert [c.name for c in lane.cells] == ["period_name"]
        assert lane.cells[0].fills_null is True
        assert lane.cells[0].clears is False, "the lane never empties a column: Undated is a value"

    def test_a_wave_label_or_scope_it_does_not_own_is_refused(self) -> None:
        with pytest.raises(ValueError):
            RP.lane_of("undated", "not-a-wave")
        with pytest.raises(ValueError):
            RP.lane_of("sideways", WAVE)

    def test_apply_finds_the_lane_by_its_name(self) -> None:
        """`apply.py --lane period-label-undated-2026-10-04` has to reach this lane, or the wave
        cannot be run at all."""
        for scope in RP.SCOPES:
            lane = L.resolve_lane(f"period-label-{scope}-{WAVE}")
            assert lane == RP.lane_of(scope, WAVE)
            assert lane.run_stamp == f"{WAVE}_period-label-{scope}"
        with pytest.raises(KeyError):
            L.resolve_lane(f"period-label-sideways-{WAVE}")


class TestTheResidual:
    def test_a_yearless_row_is_expected_to_carry_the_residue_label(self) -> None:
        """The shared residual now states the owner's whole rule: the label is the bucket of the
        year, or the residue label when there is no year. A row with neither is a finding."""
        predicate = L.bucket_case("u.period_start")
        assert f"IS NULL THEN {UNDATED!r}" in predicate.replace('"', "'")


class TestTheReadback:
    def test_the_lane_reads_back_its_own_residue(self) -> None:
        """`apply.py --verify` and every apply print the lane's readback. Without a wiring here it
        would fall through to the card_stats one, and the wave's own claim - 0 rows left whose
        label is not the rule's - would never be asked."""
        from mechanical import apply as A

        for scope in RP.SCOPES:
            lane = RP.lane_of(scope, WAVE)
            readback = A.readback_for(lane)
            assert readback == RP.readback(lane), scope
            assert lane.run_stamp in readback
            assert L._PERIOD_MISMATCH.metric in readback
            assert "carrying the residue label" in readback

    def test_the_readback_separates_the_two_half_rules(self) -> None:
        """A row carrying `Undated` **with** a year is the one state that must never exist, so the
        readback counts it on its own rather than leaving it to the residual."""
        readback = RP.readback(RP.lane_of("undated", WAVE))
        assert "curated rows with the residue label and a year" in readback
        assert f"period_name = {UNDATED!r} AND period_start IS NOT NULL".replace('"', "'") in readback


class TestTheClassifier:
    def test_a_row_without_a_year_gets_the_residue_label(self, frontend) -> None:
        v = RP.classify(row(), scope="undated", frontend=frontend)
        assert v.ok and v.new_value == UNDATED
        assert v.old_value in (None, "")

    def test_a_row_with_the_residue_label_already_is_left_alone(self, frontend) -> None:
        v = RP.classify(row(period_name=UNDATED), scope="undated", frontend=frontend)
        assert not v.ok and v.reason == RP.CONSISTENT

    def test_a_yearless_row_carrying_another_label_is_refused_for_review(self, frontend) -> None:
        """A label with no year to derive it from is not this lane's to overwrite - it is a
        contradiction a person resolves."""
        v = RP.classify(row(period_name="1 - 500 AD"), scope="undated", frontend=frontend)
        assert not v.ok and v.reason == "no-period-start"

    def test_the_residue_scope_never_derives_a_bucket(self, frontend) -> None:
        """The 103 rows and the one mismatched label are two waves, so a crash between them leaves
        no half-written state and each stamp covers one rule."""
        v = RP.classify(row(period_start=850, period_name="1 - 500 AD"), scope="undated", frontend=frontend)
        assert not v.ok and v.reason == RP.NOT_THIS_LANE

    def test_the_bucket_scope_repairs_a_label_that_contradicts_its_year(self, frontend) -> None:
        v = RP.classify(
            row(site_id=PRAMBANAN, name="Prambanan Temple", period_start=850, period_name="1 - 500 AD"),
            scope="bucket",
            frontend=frontend,
        )
        assert v.ok and v.new_value == "500 - 1000 AD"
        assert v.old_value == "1 - 500 AD"

    def test_a_correct_row_is_consistent_in_both_scopes(self, frontend) -> None:
        for scope in RP.SCOPES:
            v = RP.classify(row(period_start=850, period_name="500 - 1000 AD"), scope=scope, frontend=frontend)
            assert not v.ok and v.reason == RP.CONSISTENT, scope

    def test_the_bucket_scope_does_not_write_the_residue_label(self, frontend) -> None:
        v = RP.classify(row(), scope="bucket", frontend=frontend)
        assert not v.ok and v.reason == RP.NOT_THIS_LANE

    def test_a_row_of_another_source_is_refused(self, frontend) -> None:
        v = RP.classify(row(source_id="pleiades"), scope="undated", frontend=frontend)
        assert not v.ok and v.reason == "row-not-in-curated-source"

    def test_a_scope_it_does_not_own_is_refused(self, frontend) -> None:
        with pytest.raises(RP.PlanError):
            RP.classify(row(), scope="sideways", frontend=frontend)

    def test_two_implementations_that_disagree_refuse_the_write(self, frontend) -> None:
        """One rule has two implementations, and a value is never picked between them."""
        v = RP.classify(row(period_start=850, period_name="1 - 500 AD"), scope="bucket", frontend=lambda y: "1 - 500 AD")
        assert not v.ok and v.reason == "implementations-disagree"

    def test_the_written_value_carries_the_premise_the_lane_conditions_on(self, frontend) -> None:
        v = RP.classify(row(premise="850"), scope="undated", frontend=frontend)
        assert v.premise == "850", "guard 5 needs the live input the value was derived from"


class TestThePlan:
    def _reader(self, rows: list[dict]):
        def read(sql: str) -> list[dict]:
            return rows if "FROM unified_sites" in sql else []

        return read

    def test_the_plan_carries_the_rows_it_writes_and_lists_the_rest(self, frontend) -> None:
        rows = [
            {"id": "00000000-0000-4000-8000-000000000001", "name": "No year", "source_id": "ancient_nerds",
             "period_name": None, "period_start": None, "premise": None},
            {"id": PRAMBANAN, "name": "Prambanan Temple", "source_id": "ancient_nerds",
             "period_name": "1 - 500 AD", "period_start": 850, "premise": "850"},
        ]
        lane = RP.lane_of("undated", WAVE)
        plan = RP.build_plan(lane, RP.load_rows(self._reader(rows), lane), frontend=frontend)
        assert [c.site_id for c in plan.changes] == ["00000000-0000-4000-8000-000000000001"]
        assert plan.changes[0].new_value == UNDATED
        assert [s.reason for s in plan.skipped] == [RP.NOT_THIS_LANE]
        assert plan.counters["changes"] == 1
        assert plan.counters["rows"] == 2
        assert plan.counters[f"skip:{RP.NOT_THIS_LANE}"] == 1

    def test_an_empty_read_refuses_to_plan(self) -> None:
        with pytest.raises(RP.PlanError):
            RP.load_rows(self._reader([]), RP.lane_of("undated", WAVE))
