"""Does the B9 UK lane write the United Kingdom's parts by region - and refuse everything else?

The planner decides from Natural Earth's admin-0 map units, the two project vocabularies and an
independent Wikidata witness. Each refusal below has a test that fails when its check is removed
(`mechanical/mutation_sweep.py` removes them one by one). The points are real: production rows
(read-only, 2026-09-22) or places whose unit is not in doubt, and the few constructed ones are
*computed* against the dataset rather than typed in.

The real-data tests need the map-units cache (`uk_parts.py --collect`, gitignored) and skip with
their reason without it, as T02 and T05 do. Every decision guard is also decided on a schematic map
of lon/lat boxes (`TestClassifyUkOnASchematicMap`, added 2026-09-23), which needs only the geo stack
the CI `tests` job installs (geopandas, pyproj, shapely - `.github/workflows/ci.yml`), so the
decision is tested in CI and in a fresh clone too; the mutation sweep names those tests. The
delivered-plan tests read `output/remediation/mechanical_uk/PLAN.jsonl` only.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402
from mechanical import uk_parts as U  # noqa: E402

MAP_UNITS = (
    REPO
    / "output"
    / "remediation"
    / "cache"
    / "naturalearth_map_units"
    / "ne_10m_admin_0_map_units.shp"
)
DELIVERED = REPO / "output" / "remediation" / "mechanical_uk" / "PLAN.jsonl"

needs_units = pytest.mark.skipif(
    not MAP_UNITS.exists(),
    reason=f"Natural Earth map units not present ({MAP_UNITS}); run uk_parts.py --collect",
)
needs_plan = pytest.mark.skipif(not DELIVERED.exists(), reason=f"{DELIVERED} not built yet")

#: Real points: production rows (Boa Island, Giant's Ring, Eartham Pit, Ballinran, Wat's Dyke) and
#: places whose unit is not in doubt (Newgrange, Douglas, Stonehenge).
BOA = (54.5168, -7.8333)
GIANTS_RING = (54.54040225496907, -5.950000002593157)
EARTHAM = (50.870115074722, -0.6900000028171179)
BALLINRAN = (54.0737558594383, -6.1755663314580955)  # 109 m offshore of NI, 2.29 km from IE
WATS_DYKE = (52.98682814109494, -3.028568187345812)  # stored England, lies in Wales
NEWGRANGE = (53.6947, -6.4755)
DOUGLAS = (54.1523, -4.4861)
STONEHENGE = (51.1789, -1.8262)

UK = {"Q145": {"label": "United Kingdom", "p297": "GB"}, "Q27": {"label": "Ireland", "p297": "IE"}}
QID = "Q887472"
SITE_ID = "037e3715-f5f7-4345-8216-8aa26f404009"


@pytest.fixture(scope="module")
def units() -> Any:
    if not MAP_UNITS.exists():
        pytest.skip(f"Natural Earth map units not present ({MAP_UNITS}); run uk_parts.py --collect")
    return U.load_units(MAP_UNITS)


@pytest.fixture(scope="module")
def vocabulary() -> tuple[dict[str, str], Any]:
    return P._vocabulary()


def entity(
    *,
    p17: list[dict[str, Any]] | None = None,
    p131: list[str] | None = None,
    units_reached: list[str] | None = None,
    point: tuple[float, float] | None = BOA,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "p17": [{"id": "Q145", "rank": "normal", "start": None, "end": None}]
        if p17 is None
        else p17,
        "p131": ["Q1"] if p131 is None else p131,
        "p625": None if point is None else list(point),
        "p131_units": ["Q26"] if units_reached is None else units_reached,
        "enwiki": "Some Tomb",
        "categories": categories,
        "fetched_at": "2026-09-22T00:00:00+00:00",
    }


def candidate(
    stored: str = "Ireland",
    point: tuple[float, float] | None = BOA,
    *,
    source_id: str = P.CURATED_SOURCE,
    qids: tuple[str, ...] = (QID,),
    journal: tuple[P.JournalLink, ...] = (),
    name: str = "Boa Island",
) -> U.Candidate:
    return U.Candidate(
        site=P.Site(
            site_id=SITE_ID,
            name=name,
            country=stored,
            lat=None if point is None else point[0],
            lon=None if point is None else point[1],
            source_id=source_id,
        ),
        premise=None if point is None else f"{point[0]},{point[1]}",
        qids=qids,
        journal=journal,
    )


def decide(
    units: Any,
    vocabulary: tuple[dict[str, str], Any],
    cand: U.Candidate | None = None,
    witness: dict[str, Any] | None = None,
    *,
    codes: dict[str, str] | None = None,
    normalize: Any = None,
) -> P.Verdict:
    real_codes, real_normalize = vocabulary
    return U.classify_uk(
        cand or candidate(),
        units=units,
        codes=real_codes if codes is None else codes,
        normalize=real_normalize if normalize is None else normalize,
        witnesses={QID: entity() if witness is None else witness},
        countries=UK,
        retrieved_at="2026-09-22T21:40:07+00:00",
    )


def moved_towards(units: Any, start: tuple[float, float], end: tuple[float, float], **want: float):
    """The point on start->end whose distance to `unit` is `metres`, by bisection (computed)."""
    unit, metres = str(want["unit"]), float(want["metres"])
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lat, lon = (start[0] + mid * (end[0] - start[0]), start[1] + mid * (end[1] - start[1]))
        if (units.distance_m(unit, lat, lon) > metres) == bool(want.get("away", False)):
            hi = mid
        else:
            lo = mid
    return (start[0] + lo * (end[0] - start[0]), start[1] + lo * (end[1] - start[1]))


# ------------------------------------------------------------------------------- the geo units
@needs_units
class TestTheMapUnits:
    def test_the_unit_is_the_geounit_and_not_the_short_name(self, units: Any) -> None:
        assert "Northern Ireland" in units.units and "N. Ireland" not in units.units
        assert {"England", "Scotland", "Wales", "Northern Ireland", "Ireland"} <= set(units.units)
        assert units.units["Northern Ireland"].sovereign == "United Kingdom"

    def test_duplicate_unit_names_are_refused(self, units: Any) -> None:
        wales = units.units["Wales"]
        with pytest.raises(P.PlanError, match="unique GEOUNIT"):
            U.MapUnits([wales, wales])

    def test_an_offshore_point_takes_the_only_unit_within_tolerance(self, units: Any) -> None:
        where = units.locate(*BALLINRAN)
        assert where.unit == "Northern Ireland" and not where.inside
        assert 100 < where.metres < 120

    def test_open_water_5_km_out_is_undecided(self, units: Any) -> None:
        at_sea = moved_towards(
            units, GIANTS_RING, (54.87, -5.60), unit="Northern Ireland", metres=5000, away=True
        )
        assert 4900 < units.distance_m("Northern Ireland", *at_sea) < 5100
        assert units.locate(*at_sea).unit is None


# -------------------------------------------------------------------------------- the decision
@needs_units
class TestClassifyUk:
    def test_an_ireland_row_in_northern_ireland_is_written_as_northern_ireland(
        self, units: Any, vocabulary: Any
    ) -> None:
        verdict = decide(units, vocabulary)
        assert verdict.ok and verdict.new_value == "Northern Ireland"
        assert verdict.rule == "geo-unit" and verdict.premise == f"{BOA[0]},{BOA[1]}"
        sources = [e["source"] for e in verdict.evidence]
        assert any(s.startswith("naturalearth:ne_10m_admin_0_map_units") for s in sources)
        assert any(s.startswith("pipeline/utils/country_lookup.py") for s in sources)
        assert any(s.startswith("ancient-nerds-map/") for s in sources)
        assert any(s == f"wikidata:{QID}:P625" for s in sources)
        assert any(s.startswith("output/remediation/HANDOVER.md") for s in sources)
        assert U.witness_kinds(verdict) == ["P17", "P131*"]

    def test_the_value_is_the_unit_and_not_a_constant(self, units: Any, vocabulary: Any) -> None:
        eartham = decide(
            units,
            vocabulary,
            candidate("United Kingdom", EARTHAM, name="Eartham Pit"),
            entity(point=EARTHAM, units_reached=["Q21"]),
        )
        assert eartham.ok and eartham.new_value == "England"
        giants = decide(
            units,
            vocabulary,
            candidate("United Kingdom", GIANTS_RING),
            entity(point=GIANTS_RING, units_reached=[]),
        )
        assert giants.ok and giants.new_value == "Northern Ireland"

    def test_an_ireland_row_in_the_republic_is_consistent_and_not_written(
        self, units: Any, vocabulary: Any
    ) -> None:
        verdict = decide(units, vocabulary, candidate("Ireland", NEWGRANGE))
        assert not verdict.ok and verdict.reason == U.CONSISTENT

    def test_a_united_kingdom_row_in_the_republic_is_a_contradiction(
        self, units: Any, vocabulary: Any
    ) -> None:
        verdict = decide(units, vocabulary, candidate("United Kingdom", NEWGRANGE))
        assert not verdict.ok and verdict.reason == "geography-contradicts"

    def test_a_crown_dependency_is_not_a_uk_part(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(units, vocabulary, candidate("United Kingdom", DOUGLAS))
        assert not verdict.ok and verdict.reason == "not-a-uk-part"
        assert "Isle of Man" in verdict.note

    def test_a_region_that_is_already_spelled_out_is_never_touched(
        self, units: Any, vocabulary: Any
    ) -> None:
        """Wat's Dyke says England and lies in Wales: a coordinate question, not this lane's."""
        verdict = decide(units, vocabulary, candidate("England", WATS_DYKE, name="Wat's Dyke"))
        assert not verdict.ok and verdict.reason == "out-of-scope"

    def test_a_row_of_another_source_is_refused(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(units, vocabulary, candidate(source_id="lyra"))
        assert not verdict.ok and verdict.reason == "row-not-in-curated-source"

    def test_a_row_without_a_point_is_refused(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(units, vocabulary, candidate(point=None))
        assert not verdict.ok and verdict.reason == "no-point"

    def test_an_ireland_row_300_m_from_the_border_is_ambiguous(
        self, units: Any, vocabulary: Any
    ) -> None:
        near_border = moved_towards(
            units, (54.80, -7.35), (54.85, -7.55), unit="Ireland", metres=300
        )
        assert units.locate(*near_border).unit == "Northern Ireland"
        assert 250 < units.distance_m("Ireland", *near_border) < 350
        verdict = decide(
            units, vocabulary, candidate("Ireland", near_border), entity(point=near_border)
        )
        assert not verdict.ok and verdict.reason == "border-ambiguous"

    def test_an_offshore_row_is_written_by_the_unit_within_tolerance(
        self, units: Any, vocabulary: Any
    ) -> None:
        verdict = decide(
            units,
            vocabulary,
            candidate("United Kingdom", BALLINRAN),
            entity(point=BALLINRAN, units_reached=[]),
        )
        assert verdict.ok and verdict.new_value == "Northern Ireland"
        assert verdict.rule == "geo-unit-within-tolerance"

    def test_a_point_at_sea_is_undecided(self, units: Any, vocabulary: Any) -> None:
        at_sea = moved_towards(
            units, GIANTS_RING, (54.87, -5.60), unit="Northern Ireland", metres=5000, away=True
        )
        verdict = decide(units, vocabulary, candidate("United Kingdom", at_sea))
        assert not verdict.ok and verdict.reason == "geography-undecided"

    def test_without_the_vocabulary_change_every_northern_irish_row_is_refused(
        self, units: Any, vocabulary: Any
    ) -> None:
        codes, _ = vocabulary
        without = {k: v for k, v in codes.items() if k != "Northern Ireland"}
        verdict = decide(units, vocabulary, codes=without)
        assert not verdict.ok and verdict.reason == "not-a-country-code"

    def test_an_unexpected_iso_transition_is_refused(self, units: Any, vocabulary: Any) -> None:
        _, normalize = vocabulary
        verdict = decide(
            units,
            vocabulary,
            normalize=lambda v: "FR" if v == "Ireland" else normalize(v),
        )
        assert not verdict.ok and verdict.reason == "iso-transition-unexpected"

    def test_a_value_the_census_would_flag_again_is_refused(
        self, units: Any, vocabulary: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(U, "_is_canonical", lambda *a, **k: False)
        verdict = decide(units, vocabulary)
        assert not verdict.ok and verdict.reason == "not-a-fixed-point"

    def test_a_preferred_p17_of_ireland_contradicts(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(
            units,
            vocabulary,
            witness=entity(p17=[{"id": "Q27", "rank": "preferred", "start": None, "end": None}]),
        )
        assert not verdict.ok and verdict.reason == "wikidata-contradicts"
        assert "IE" in verdict.note

    def test_a_p131_chain_to_england_contradicts_a_northern_irish_point(
        self, units: Any, vocabulary: Any
    ) -> None:
        verdict = decide(units, vocabulary, witness=entity(units_reached=["Q26", "Q21"]))
        assert not verdict.ok and verdict.reason == "wikidata-contradicts"
        assert "Q21" in verdict.note

    def test_a_p131_chain_to_ireland_contradicts(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(units, vocabulary, witness=entity(units_reached=["Q27"]))
        assert not verdict.ok and verdict.reason == "wikidata-contradicts"

    def test_an_entity_point_in_another_unit_is_refused(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(units, vocabulary, witness=entity(point=STONEHENGE))
        assert not verdict.ok and verdict.reason == "wikidata-point-elsewhere"
        assert "England" in verdict.note

    def test_an_entity_point_1_9_km_away_in_the_same_unit_is_fine(
        self, units: Any, vocabulary: Any
    ) -> None:
        """Aghanaglack's shape: same unit, not the same 1000 m."""
        from census.tests.t02_admin_country import GEOD

        further = moved_towards(units, BOA, (54.60, -7.60), unit="Ireland", metres=4800, away=True)
        apart = GEOD.inv(BOA[1], BOA[0], further[1], further[0])[2]
        assert apart > 1000, "the entity point must be further than T02's 1000 m for this test"
        verdict = decide(units, vocabulary, witness=entity(point=further))
        assert verdict.ok

    def test_an_entity_without_a_point_is_refused(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(units, vocabulary, witness=entity(point=None))
        assert not verdict.ok and verdict.reason == "wikidata-point-missing"

    def test_an_ireland_row_without_a_positive_witness_is_refused(
        self, units: Any, vocabulary: Any
    ) -> None:
        verdict = decide(units, vocabulary, witness=entity(p17=[], units_reached=[]))
        assert not verdict.ok and verdict.reason == "no-external-witness"

    def test_a_united_kingdom_row_without_a_witness_records_the_gap(
        self, units: Any, vocabulary: Any
    ) -> None:
        verdict = decide(
            units,
            vocabulary,
            candidate("United Kingdom", GIANTS_RING),
            entity(p17=[], p131=[], units_reached=[], point=GIANTS_RING),
        )
        assert verdict.ok and "gap" in verdict.note and U.witness_kinds(verdict) == []

    @pytest.mark.parametrize(
        ("category", "ok"),
        [
            ("Category:Megalithic monuments in Northern Ireland", True),
            ("Category:Archaeological sites in County Donegal", False),
            ("Category:Stone circles in Ireland", False),
        ],
    )
    def test_a_category_counts_only_when_it_names_the_unit(
        self, units: Any, vocabulary: Any, category: str, ok: bool
    ) -> None:
        """Annaghmare's shape: no P17, no P131, only P625 and its article's categories."""
        verdict = decide(
            units,
            vocabulary,
            witness=entity(p17=[], p131=[], units_reached=[], categories=[category]),
        )
        assert verdict.ok is ok
        if ok:
            assert U.witness_kinds(verdict) == ["enwiki category"]
        else:
            assert verdict.reason == "no-external-witness"

    def test_a_category_naming_the_republic_contradicts(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(
            units,
            vocabulary,
            witness=entity(
                p17=[],
                p131=[],
                units_reached=[],
                categories=[
                    "Category:Megalithic monuments in Northern Ireland",
                    "Category:Megalithic monuments in the Republic of Ireland",
                ],
            ),
        )
        assert not verdict.ok and verdict.reason == "category-contradicts"

    def test_a_category_is_no_witness_for_an_entity_that_states_p131(
        self, units: Any, vocabulary: Any
    ) -> None:
        """A townland P131 that stops short of Q26 is a statement; a category does not replace it."""
        verdict = decide(
            units,
            vocabulary,
            witness=entity(
                p17=[],
                p131=["Q7830001"],
                units_reached=[],
                categories=["Category:Megalithic monuments in Northern Ireland"],
            ),
        )
        assert not verdict.ok and verdict.reason == "no-external-witness"

    def test_a_site_needs_exactly_one_entity(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(units, vocabulary, candidate(qids=("Q1", "Q2")))
        assert not verdict.ok and verdict.reason == "no-single-wikidata-entity"
        verdict = decide(units, vocabulary, candidate(qids=()))
        assert not verdict.ok and verdict.reason == "no-single-wikidata-entity"

    def test_an_entity_missing_from_the_cache_is_refused(self, units: Any, vocabulary: Any) -> None:
        verdict = decide(units, vocabulary, candidate(qids=("Q999",)))
        assert not verdict.ok and verdict.reason == "witness-not-collected"

    def test_a_phase3_write_is_superseded_and_named(self, units: Any, vocabulary: Any) -> None:
        link = P.JournalLink(
            28001, "phase3:batch-0148:chunk-0001", "P3/country", "Ireland", "United Kingdom"
        )
        verdict = decide(
            units,
            vocabulary,
            candidate("United Kingdom", GIANTS_RING, journal=(link,)),
            entity(point=GIANTS_RING, units_reached=[]),
        )
        assert verdict.ok and verdict.phase3
        assert any(e["source"] == "remediation_change_log:28001" for e in verdict.evidence)

    def test_a_journal_that_disagrees_with_the_row_is_refused(
        self, units: Any, vocabulary: Any
    ) -> None:
        link = P.JournalLink(
            28001, "phase3:batch-0148:chunk-0001", "P3/country", "Ireland", "Wales"
        )
        verdict = decide(
            units, vocabulary, candidate("United Kingdom", GIANTS_RING, journal=(link,))
        )
        assert not verdict.ok and verdict.reason == "journal-disagrees"

    def test_a_broken_journal_chain_is_refused(self, units: Any, vocabulary: Any) -> None:
        first = P.JournalLink(1, "phase3:a", "P3/country", "Ireland", "United Kingdom")
        second = P.JournalLink(2, "phase3:b", "P3/country", "Wales", "United Kingdom")
        verdict = decide(
            units, vocabulary, candidate("United Kingdom", GIANTS_RING, journal=(first, second))
        )
        assert not verdict.ok and verdict.reason == "journal-chain-broken"


@needs_units
class TestBuildUkPlan:
    def test_the_plan_is_a_partition_with_its_counters(self, units: Any, vocabulary: Any) -> None:
        codes, normalize = vocabulary
        cands = [
            candidate(),
            replace(
                candidate("Ireland", NEWGRANGE),
                site=replace(
                    candidate("Ireland", NEWGRANGE).site,
                    site_id="1" * 8 + "-1111-1111-1111-" + "1" * 12,
                ),
            ),
            replace(
                candidate("United Kingdom", DOUGLAS),
                site=replace(
                    candidate("United Kingdom", DOUGLAS).site,
                    site_id="2" * 8 + "-2222-2222-2222-" + "2" * 12,
                ),
            ),
        ]
        uk = U.build_uk_plan(
            cands,
            units=units,
            codes=codes,
            normalize=normalize,
            witnesses={QID: entity()},
            countries=UK,
            retrieved_at=None,
            built_at="2026-09-22T00:00:00+00:00",
        )
        written = {v.site_id for v in uk.plan.changes}
        same = {v.site_id for v in uk.consistent}
        refused = {v.site_id for v in uk.plan.skipped}
        assert len(written) == len(same) == len(refused) == 1
        assert written.isdisjoint(same) and written.isdisjoint(refused) and same.isdisjoint(refused)
        assert uk.counters["changes"] == 1 and uk.counters["consistent"] == 1
        assert uk.counters["skip:not-a-uk-part"] == 1
        assert uk.counters["transition:Ireland -> Northern Ireland"] == 1
        assert uk.plan.lane is L.UK_PARTS and uk.plan.run_stamp == L.UK_PARTS.run_stamp


# ------------------------------------------- the decision, on a map drawn for the test
def schematic_units() -> U.MapUnits:
    """A schematic British Isles in lon/lat boxes. Every guard of `classify_uk` is decided on it
    below, so the decision is tested where the Natural Earth cache is absent - CI and a fresh
    clone, where the real-data classes above skip. Borders: Ireland | Northern Ireland at 8 W,
    England | Wales at 3 W; the Isle of Man and Scotland stand apart. Northern Ireland has a bay
    open to the east (6.2 W to the sea, 54.3 to 54.7 N), so a point at sea can lie inside the
    unit's envelope - where `locate`'s index finds the unit and only the measured 1000 m decides,
    as on a real coastline. Distances come from T02's geodesic rule, as on the real polygons."""
    from shapely.geometry import box

    bay = box(-6.2, 54.3, -5.4, 54.7)
    return U.MapUnits(
        [
            U.Unit("Ireland", "Ireland", box(-10.0, 51.5, -8.0, 55.5)),
            U.Unit(
                "Northern Ireland", "United Kingdom", box(-8.0, 54.0, -5.5, 55.3).difference(bay)
            ),
            U.Unit("England", "United Kingdom", box(-3.0, 50.0, 1.5, 55.0)),
            U.Unit("Wales", "United Kingdom", box(-5.0, 51.5, -3.0, 53.4)),
            U.Unit("Scotland", "United Kingdom", box(-6.0, 55.5, -2.0, 58.5)),
            U.Unit("Isle of Man", "Isle of Man", box(-4.8, 54.05, -4.3, 54.4)),
        ]
    )


#: Points on the schematic map, each well inside its box.
S_NI = (54.5, -6.8)
S_NI_NORTH = (54.6, -6.8)  # 11 km from S_NI, same unit
S_IRELAND = (53.0, -9.0)
S_ENGLAND = (52.0, -1.0)
S_MAN = (54.2, -4.5)


@pytest.fixture(scope="module")
def schematic() -> U.MapUnits:
    return schematic_units()


def ni_entity(**over: Any) -> dict[str, Any]:
    return entity(**{"point": S_NI_NORTH, **over})


class TestClassifyUkOnASchematicMap:
    """The decision guards of `classify_uk`, one test each, on geometry built for them."""

    def test_schematic_one_covering_unit_decides(self, schematic: Any, vocabulary: Any) -> None:
        verdict = decide(schematic, vocabulary, candidate("Ireland", S_NI), ni_entity())
        assert verdict.ok and verdict.new_value == "Northern Ireland"
        assert verdict.rule == "geo-unit" and verdict.premise == f"{S_NI[0]},{S_NI[1]}"
        assert U.witness_kinds(verdict) == ["P17", "P131*"]

    def test_schematic_the_value_is_the_unit(self, schematic: Any, vocabulary: Any) -> None:
        england = decide(
            schematic,
            vocabulary,
            candidate("United Kingdom", S_ENGLAND),
            entity(point=S_ENGLAND, units_reached=["Q21"]),
        )
        assert england.ok and england.new_value == "England"

    def test_schematic_an_ireland_row_in_the_republic_is_consistent(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(schematic, vocabulary, candidate("Ireland", S_IRELAND))
        assert not verdict.ok and verdict.reason == U.CONSISTENT

    def test_schematic_a_united_kingdom_row_in_the_republic_contradicts(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(schematic, vocabulary, candidate("United Kingdom", S_IRELAND))
        assert not verdict.ok and verdict.reason == "geography-contradicts"

    def test_schematic_a_crown_dependency_is_not_a_uk_part(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(schematic, vocabulary, candidate("United Kingdom", S_MAN))
        assert not verdict.ok and verdict.reason == "not-a-uk-part"
        assert "Isle of Man" in verdict.note

    def test_schematic_a_region_already_spelled_out_is_out_of_scope(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(schematic, vocabulary, candidate("England", S_ENGLAND))
        assert not verdict.ok and verdict.reason == "out-of-scope"

    def test_schematic_a_row_of_another_source_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(schematic, vocabulary, candidate(point=S_NI, source_id="lyra"))
        assert not verdict.ok and verdict.reason == "row-not-in-curated-source"

    def test_schematic_a_row_without_a_point_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(schematic, vocabulary, candidate(point=None))
        assert not verdict.ok and verdict.reason == "no-point"

    def test_schematic_an_ireland_row_300_m_from_the_border_is_ambiguous(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        near = moved_towards(schematic, S_NI, (54.5, -8.5), unit="Ireland", metres=300)
        assert schematic.locate(*near).unit == "Northern Ireland"
        assert 250 < schematic.distance_m("Ireland", *near) < 350
        verdict = decide(schematic, vocabulary, candidate("Ireland", near), ni_entity())
        assert not verdict.ok and verdict.reason == "border-ambiguous"

    def test_schematic_an_offshore_row_takes_the_only_unit_within_tolerance(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        offshore = moved_towards(
            schematic, S_NI, (54.5, -5.0), unit="Northern Ireland", metres=500, away=True
        )
        where = schematic.locate(*offshore)
        assert where.unit == "Northern Ireland" and not where.inside and 400 < where.metres <= 500
        verdict = decide(
            schematic,
            vocabulary,
            candidate("United Kingdom", offshore),
            ni_entity(units_reached=[]),
        )
        assert verdict.ok and verdict.rule == "geo-unit-within-tolerance"

    def test_schematic_a_point_5_km_at_sea_is_undecided(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        at_sea = moved_towards(
            schematic, S_NI, (54.5, -5.0), unit="Northern Ireland", metres=5000, away=True
        )
        from shapely.geometry import Point

        assert 4900 < schematic.distance_m("Northern Ireland", *at_sea) <= 5000
        envelope = schematic.units["Northern Ireland"].geom.envelope
        assert envelope.contains(Point(at_sea[1], at_sea[0])), "in the bay, not beyond the map"
        verdict = decide(schematic, vocabulary, candidate("United Kingdom", at_sea))
        assert not verdict.ok and verdict.reason == "geography-undecided"

    def test_two_units_within_tolerance_are_undecided(self) -> None:
        from shapely.geometry import box

        west = U.Unit("West", "X", box(0.0, 0.0, 1.0, 1.0))
        east = U.Unit("East", "X", box(1.01, 0.0, 2.0, 1.0))
        where = U.MapUnits([west, east]).locate(0.5, 1.005)
        assert where.unit is None and "2 units within 1000 m" in where.note

    def test_schematic_the_unit_is_the_geounit_and_not_the_short_name(self, tmp_path: Path) -> None:
        """Natural Earth's `NAME` reads `N. Ireland`; the lane writes `GEOUNIT`. A shapefile with
        the dataset's three columns, written here, is read the way the cached one is."""
        import geopandas as gpd
        from shapely.geometry import box

        frame = gpd.GeoDataFrame(
            {
                "GEOUNIT": ["Northern Ireland", "Ireland"],
                "NAME": ["N. Ireland", "Ireland"],
                "SOVEREIGNT": ["United Kingdom", "Ireland"],
            },
            geometry=[box(-8.0, 54.0, -5.5, 55.3), box(-10.0, 51.5, -8.0, 55.5)],
            crs="EPSG:4326",
        )
        path = tmp_path / "units.shp"
        frame.to_file(path)
        units = U.load_units(path)
        assert set(units.units) == {"Northern Ireland", "Ireland"}
        assert units.units["Northern Ireland"].sovereign == "United Kingdom"
        assert units.locate(*S_NI).unit == "Northern Ireland"

    def test_schematic_duplicate_unit_names_are_refused(self, schematic: Any) -> None:
        wales = schematic.units["Wales"]
        with pytest.raises(P.PlanError, match="unique GEOUNIT"):
            U.MapUnits([wales, wales])

    def test_schematic_without_the_vocabulary_change_northern_ireland_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        codes, _ = vocabulary
        without = {k: v for k, v in codes.items() if k != "Northern Ireland"}
        verdict = decide(
            schematic, vocabulary, candidate("Ireland", S_NI), ni_entity(), codes=without
        )
        assert not verdict.ok and verdict.reason == "not-a-country-code"

    def test_schematic_an_unexpected_iso_transition_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        _, normalize = vocabulary
        verdict = decide(
            schematic,
            vocabulary,
            candidate("Ireland", S_NI),
            ni_entity(),
            normalize=lambda v: "FR" if v == "Ireland" else normalize(v),
        )
        assert not verdict.ok and verdict.reason == "iso-transition-unexpected"

    def test_schematic_a_value_the_census_would_flag_again_is_refused(
        self, schematic: Any, vocabulary: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(U, "_is_canonical", lambda *a, **k: False)
        verdict = decide(schematic, vocabulary, candidate("Ireland", S_NI), ni_entity())
        assert not verdict.ok and verdict.reason == "not-a-fixed-point"

    def test_schematic_a_site_needs_exactly_one_entity(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        for qids in (("Q1", "Q2"), ()):
            verdict = decide(schematic, vocabulary, candidate("Ireland", S_NI, qids=qids))
            assert not verdict.ok and verdict.reason == "no-single-wikidata-entity"

    def test_schematic_an_entity_missing_from_the_cache_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(schematic, vocabulary, candidate("Ireland", S_NI, qids=("Q999",)))
        assert not verdict.ok and verdict.reason == "witness-not-collected"

    def test_schematic_an_entity_without_a_point_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(schematic, vocabulary, candidate("Ireland", S_NI), ni_entity(point=None))
        assert not verdict.ok and verdict.reason == "wikidata-point-missing"

    def test_schematic_an_entity_point_in_another_unit_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(
            schematic, vocabulary, candidate("Ireland", S_NI), ni_entity(point=S_ENGLAND)
        )
        assert not verdict.ok and verdict.reason == "wikidata-point-elsewhere"
        assert "England" in verdict.note

    def test_schematic_a_preferred_p17_of_ireland_contradicts(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        p17 = [{"id": "Q27", "rank": "preferred", "start": None, "end": None}]
        verdict = decide(schematic, vocabulary, candidate("Ireland", S_NI), ni_entity(p17=p17))
        assert not verdict.ok and verdict.reason == "wikidata-contradicts" and "IE" in verdict.note

    def test_schematic_a_p131_chain_to_another_unit_contradicts(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        for reached in (["Q26", "Q21"], ["Q27"]):
            verdict = decide(
                schematic,
                vocabulary,
                candidate("Ireland", S_NI),
                ni_entity(units_reached=reached),
            )
            assert not verdict.ok and verdict.reason == "wikidata-contradicts"

    def test_schematic_an_ireland_row_without_a_positive_witness_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(
            schematic,
            vocabulary,
            candidate("Ireland", S_NI),
            ni_entity(p17=[], units_reached=[]),
        )
        assert not verdict.ok and verdict.reason == "no-external-witness"

    def test_schematic_a_united_kingdom_row_without_a_witness_records_the_gap(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(
            schematic,
            vocabulary,
            candidate("United Kingdom", S_NI),
            ni_entity(p17=[], p131=[], units_reached=[]),
        )
        assert verdict.ok and "gap" in verdict.note and U.witness_kinds(verdict) == []

    @pytest.mark.parametrize(
        ("category", "ok"),
        [
            ("Category:Megalithic monuments in Northern Ireland", True),
            ("Category:Archaeological sites in County Donegal", False),
            ("Category:Stone circles in Ireland", False),
        ],
    )
    def test_schematic_a_category_counts_only_when_it_names_the_unit(
        self, schematic: Any, vocabulary: Any, category: str, ok: bool
    ) -> None:
        verdict = decide(
            schematic,
            vocabulary,
            candidate("Ireland", S_NI),
            ni_entity(p17=[], p131=[], units_reached=[], categories=[category]),
        )
        assert verdict.ok is ok
        if ok:
            assert U.witness_kinds(verdict) == ["enwiki category"]
        else:
            assert verdict.reason == "no-external-witness"

    def test_schematic_a_category_naming_the_republic_contradicts(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        categories = [
            "Category:Megalithic monuments in Northern Ireland",
            "Category:Megalithic monuments in the Republic of Ireland",
        ]
        verdict = decide(
            schematic,
            vocabulary,
            candidate("Ireland", S_NI),
            ni_entity(p17=[], p131=[], units_reached=[], categories=categories),
        )
        assert not verdict.ok and verdict.reason == "category-contradicts"

    def test_schematic_a_category_is_no_witness_for_an_entity_that_states_p131(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        verdict = decide(
            schematic,
            vocabulary,
            candidate("Ireland", S_NI),
            ni_entity(
                p17=[],
                p131=["Q7830001"],
                units_reached=[],
                categories=["Category:Megalithic monuments in Northern Ireland"],
            ),
        )
        assert not verdict.ok and verdict.reason == "no-external-witness"

    def test_schematic_a_phase3_write_is_superseded_and_named(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        link = P.JournalLink(
            28001, "phase3:batch-0148:chunk-0001", "P3/country", "Ireland", "United Kingdom"
        )
        verdict = decide(
            schematic,
            vocabulary,
            candidate("United Kingdom", S_NI, journal=(link,)),
            ni_entity(units_reached=[]),
        )
        assert verdict.ok and verdict.phase3
        assert any(e["source"] == "remediation_change_log:28001" for e in verdict.evidence)

    def test_schematic_a_journal_that_disagrees_or_breaks_is_refused(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        wales = P.JournalLink(1, "phase3:a", "P3/country", "Ireland", "Wales")
        verdict = decide(schematic, vocabulary, candidate("United Kingdom", S_NI, journal=(wales,)))
        assert not verdict.ok and verdict.reason == "journal-disagrees"
        first = P.JournalLink(1, "phase3:a", "P3/country", "Ireland", "United Kingdom")
        second = P.JournalLink(2, "phase3:b", "P3/country", "Wales", "United Kingdom")
        verdict = decide(
            schematic,
            vocabulary,
            candidate("United Kingdom", S_NI, journal=(first, second)),
        )
        assert not verdict.ok and verdict.reason == "journal-chain-broken"

    def test_schematic_the_plan_is_a_partition_with_its_counters(
        self, schematic: Any, vocabulary: Any
    ) -> None:
        codes, normalize = vocabulary

        def at(stored: str, point: tuple[float, float], digit: str) -> U.Candidate:
            base = candidate(stored, point)
            sid = f"{digit * 8}-{digit * 4}-{digit * 4}-{digit * 4}-{digit * 12}"
            return replace(base, site=replace(base.site, site_id=sid))

        uk = U.build_uk_plan(
            [
                at("Ireland", S_NI, "1"),
                at("Ireland", S_IRELAND, "2"),
                at("United Kingdom", S_MAN, "3"),
            ],
            units=schematic,
            codes=codes,
            normalize=normalize,
            witnesses={QID: ni_entity()},
            countries=UK,
            retrieved_at=None,
            built_at="2026-09-23T00:00:00+00:00",
        )
        assert [v.new_value for v in uk.plan.changes] == ["Northern Ireland"]
        assert [v.reason for v in uk.consistent] == [U.CONSISTENT]
        assert [v.reason for v in uk.plan.skipped] == ["not-a-uk-part"]
        assert uk.counters["transition:Ireland -> Northern Ireland"] == 1
        assert uk.plan.lane is L.UK_PARTS


class TestTheCollectionQuery:
    def test_the_sparql_asks_for_the_five_units_and_only_those(self) -> None:
        query = U.sparql_units_query(["Q2", "Q1", "Q2"])
        assert "VALUES ?item { wd:Q1 wd:Q2 }" in query
        assert "VALUES ?unit { wd:Q21 wd:Q22 wd:Q25 wd:Q26 wd:Q27 }" in query
        assert "wdt:P131*" in query

    def test_the_candidate_query_reads_the_lane_s_premise(self) -> None:
        assert L.UK_PARTS.premise_sql in U.CANDIDATE_SQL
        assert "u.country IN ('Ireland', 'United Kingdom')" in U.CANDIDATE_SQL
        assert "u.source_id = 'ancient_nerds'" in U.CANDIDATE_SQL

    def test_a_non_uuid_is_never_interpolated(self) -> None:
        with pytest.raises(P.PlanError, match="not a UUID"):
            P.sql_ids(["x'; DROP TABLE unified_sites; --"])


# ------------------------------------------------------------------------- the delivered plan
@needs_plan
class TestTheDeliveredPlan:
    def test_23_rows_of_the_agreed_shape(self) -> None:
        records = A.load_records(DELIVERED)
        A.validate_records(records, lane=L.UK_PARTS)
        assert len(records) == 23
        assert {r.new_value for r in records} == {"Northern Ireland", "England"}
        assert {r.old_value for r in records} == {"Ireland", "United Kingdom"}
        pairs = [(r.old_value, r.new_value) for r in records]
        assert pairs.count(("Ireland", "Northern Ireland")) == 17
        assert pairs.count(("United Kingdom", "Northern Ireland")) == 5
        assert pairs.count(("United Kingdom", "England")) == 1
        assert sum(1 for r in records if r.phase3) == 5

    def test_every_ireland_row_carries_a_positive_external_witness(self) -> None:
        for line in DELIVERED.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            assert payload["run_stamp"] == L.UK_PARTS.run_stamp
            assert payload["change_key"] == f"country-uk-part:{payload['site_id']}"
            assert payload["premise"] and payload["premise_sql"] == L.UK_PARTS.premise_sql
            sources = [e["source"] for e in payload["evidence"]]
            assert any(s.startswith("naturalearth:ne_10m_admin_0_map_units") for s in sources)
            assert any(s.endswith(":P625") for s in sources)
            if payload["old_value"] == "Ireland":
                assert any(
                    ":P17 -> " in s or ":P131* -> " in s or s.startswith("enwiki:") for s in sources
                ), payload["site_name"]

    def test_the_rollback_reverses_every_row(self) -> None:
        records = A.load_records(DELIVERED)
        rollback = (DELIVERED.parent / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert f"'{L.UK_PARTS.rollback_run_stamp}'" in rollback
        for r in records:
            assert f"'country-uk-part-rollback:{r.site_id}'" in rollback
        body = rollback.split("INSERT INTO _uk_part_plan", 1)[1].split("\n;\n", 1)[0]
        rows = [line for line in body.splitlines() if line.strip().startswith("('")]
        assert len(rows) == len(records)
        for r in records:
            (row,) = [line for line in rows if r.site_id in line]
            assert f"'{r.new_value}', '{r.old_value}'" in row, "old and new swapped"
