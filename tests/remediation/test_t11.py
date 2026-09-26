"""Does T11 actually have teeth, and does it reproduce the gate it exists for?

T11 decides scope from stored values only: `period_start` (with `period_end` preferred, as the
project's own function does), the region the coordinates fall in, and the project's cutoff
constants. These tests drive it two ways.

**A synthetic world** - five hand-built Natural Earth features handed to T02's real `_Atlas`
(a real STRtree, real `covers`) through the module's single geography seam - so the decision
logic is tested without the 4.9 MB cache and without a snapshot. The world contains everything
the logic branches on: the Americas, the rest of the world, a point in no polygon at all, one of
Natural Earth's own ocean features, and countries whose CONTINENT contradicts the project's
longitude window in both directions. The site coordinates and `period_start` values are the
measured ones from this repository's snapshot (Midford Castle, Ksar el Barka, Museo Campano,
Hane, Situs Megalit Tebing Tinggi, The Davidson Center), so the fixtures are real data rather
than invented points.

**The real snapshot**, skipped with a reason when it is absent: the module has to reproduce the
plan's §7 gate S12 (4,920 pass / 84 fail) and settle the plan's open 69-versus-84 question,
which is a claim about the data and cannot be made from synthetic sites.

Every test that calls `run()` fails when it is made to `return []`; the mutation proof, with the
fail count and the sha256 before and after, is in the task record.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from shapely.geometry import box

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402
from census.tests import t02_admin_country as t02  # noqa: E402

SNAPSHOT = REPO / "output" / "remediation" / "snapshot"
NE_SHAPEFILE = (
    REPO / "output" / "remediation" / "cache" / "naturalearth" / "ne_10m_admin_0_countries.shp"
)
CACHE = REPO / "output" / "remediation" / "cache"

#: Measured ids from the snapshot, so the real-data assertions name a site rather than a count:
#: the two gold-standard scope errors, and the one error of that class T11 cannot see.
MIDFORD_CASTLE = "32429f3c-6e14-4015-900a-a9cd9fbb81eb"
KSAR_EL_BARKA = "a5d9e9a7-9fd2-4a0f-a3ae-7dd78fba429b"
FONT_DELS_COMS = "58a2be59-ec1e-4667-96b9-3313ce406bc1"

needs_dataset = pytest.mark.skipif(
    not (SNAPSHOT.exists() and NE_SHAPEFILE.exists()),
    reason=f"snapshot and/or Natural Earth cache not present ({SNAPSHOT}, {NE_SHAPEFILE})",
)


@pytest.fixture(scope="module")
def t11() -> Any:
    return importlib.import_module("census.tests.t11_scope_window")


# ------------------------------------------------------------------------------- fixtures
def _site(
    sid: str,
    *,
    lat: float | None,
    lon: float | None,
    period_start: Any = 1,
    period_end: Any = None,
    period_name: Any = None,
    site_type: str = "Temple complex",
    name: str = "",
) -> dict[str, Any]:
    """One `unified_sites` row, in the shape the check reads."""
    return {
        "id": sid,
        "source_id": "ancient_nerds",
        "name": name or f"Site {sid}",
        "country": "Nowhere",
        "site_type": site_type,
        "lat": lat,
        "lon": lon,
        "period_start": period_start,
        "period_end": period_end,
        "period_name": period_name,
    }


def _ctx(sites: list[dict[str, Any]], cache: Path = CACHE) -> SimpleNamespace:
    """The parts of Context T11 reads: `.sites` and `.cache`."""
    return SimpleNamespace(sites=sites, cache=cache)


def _feature(admin: str, geometry: Any) -> Any:
    """One Natural Earth feature, built through T02's own constructor."""
    return t02._Feature(
        admin=admin,
        sovereign=admin,
        kind="Country",
        name_keys=(t02._fold(admin),),
        iso_codes=(),
        geom=geometry,
    )


def _world(t11: Any) -> Any:
    """A five-country world around T02's real atlas, and the only geography these tests need.

    Each box is placed where the branch it exercises sits in the real data:

    * `Europa` covers Midford Castle (51.35, -2.35) and Museo Campano (41.11, 14.21).
    * `Mexica` reaches east of -30 on purpose, so a point at lon -25 can be American to Natural
      Earth and not to the longitude window in the same run.
    * `Polynesia` covers the Marquesas pair (lon -139 / -151) and is Oceania: the region differs
      from the window, the verdict does not.
    * `Atlantis` covers lon -35 at the equator and is Africa: here the verdict differs too.
      (Until O7 of 2026-09-26 it was Oceania, whose cutoff was then 500 AD; since O7
      Oceania's cutoff is the Americas' 1500 AD and agrees with the window - the fixture
      keeps its purpose, a continent whose cutoff is not the window's, under Africa.)
    * `Mare` is one of Natural Earth's own sea features, which answer nothing about a region.

    shapely's `box` takes (minx, miny, maxx, maxy) - longitude first, then latitude.
    """
    features = [
        _feature("Europa", box(-10, 40, 30, 70)),
        _feature("Mexica", box(-120, 10, -20, 40)),
        _feature("Polynesia", box(-160, -25, -130, 0)),
        _feature("Atlantis", box(-40, -10, -31, 10)),
        _feature("Mare", box(-160, 20, -120, 40)),
    ]
    return t11._Geography(
        atlas=t02._Atlas(features),
        continents={
            "Europa": "Europe",
            "Mexica": "North America",
            "Polynesia": "Oceania",
            "Atlantis": "Africa",
            "Mare": "Seven seas (open ocean)",
        },
        retrieved_at=None,
    )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, t11: Any) -> Any:
    """Replace the module's geography seam, so no cache and no snapshot are needed."""
    geo = _world(t11)
    monkeypatch.setattr(t11, "_geography", lambda ctx: geo)
    return geo


def _kinds(findings: list[M.Finding]) -> list[str]:
    return [f.test_id for f in findings]


# ------------------------------------------------------------------ the decision itself
class TestT11ScopeWindow:
    def test_a_site_inside_the_window_produces_nothing(self, t11: Any, world: Any) -> None:
        """Europa, 500 BC, with Natural Earth and the longitude window agreeing."""
        assert t11.run(_ctx([_site("a", lat=51.35, lon=-2.35, period_start=-500)])) == []

    def test_a_site_past_the_cutoff_is_flagged(self, t11: Any, world: Any) -> None:
        """Midford Castle, measured: 1775 in Somerset, 1,275 years past the 500 AD cutoff."""
        got = t11.run(
            _ctx(
                [
                    _site(
                        MIDFORD_CASTLE,
                        lat=51.35064268125167,
                        lon=-2.3463889027884193,
                        period_start=1775,
                        period_name="1500+ AD",
                        site_type="Castle/palace",
                        name="Midford Castle",
                    )
                ]
            )
        )
        assert _kinds(got) == ["T11/out-of-window"]
        finding = got[0]
        assert finding.severity is M.Severity.SEVERE
        assert finding.field == "scope_status"
        assert finding.proposal is M.Proposal.REVIEW
        assert finding.proposed_value is None
        assert finding.applicable is False
        assert "1275 years past the rest of world cutoff" in finding.note
        assert "CONTINENT = Europe" in finding.evidence[2].quote

    def test_the_americas_window_is_1500_not_500(self, t11: Any, world: Any) -> None:
        """1200 AD in Mexico is in scope: the region changes the cutoff, not the arithmetic."""
        sites = [
            _site("mx", lat=20.0, lon=-100.0, period_start=1200),
            _site("es", lat=40.0, lon=-4.0, period_start=1200),
        ]
        got = t11.run(_ctx(sites))
        assert _kinds(got) == ["T11/out-of-window"]
        assert got[0].site_id == "es"  # same year, other region, other verdict

    def test_the_boundary_is_inclusive_on_both_sides(self, t11: Any, world: Any) -> None:
        """E3 says "through" 1500/500 AD, and the plan measured the trap at exactly 500."""
        sites = [
            _site("row-500", lat=40.0, lon=-4.0, period_start=500),
            _site("row-501", lat=40.0, lon=-4.0, period_start=501),
            _site("am-1500", lat=20.0, lon=-100.0, period_start=1500),
            _site("am-1501", lat=20.0, lon=-100.0, period_start=1501),
        ]
        got = t11.run(_ctx(sites))
        assert [f.site_id for f in got] == ["row-501", "am-1501"]

    def test_a_museum_past_the_cutoff_is_a_museum_question_not_a_verdict(
        self, t11: Any, world: Any
    ) -> None:
        """Museo Campano, measured: 1869 is the year the building opened, and E3 keeps it.

        The gold standard reviewed this very site and called the E3 museum rule correct
        (`GOLD_STANDARD.md:561`). A check that retired it would delete a site the owner's rule
        keeps, so the finding is moderate, unverifiable and carries the museum rule.
        """
        got = t11.run(
            _ctx(
                [
                    _site(
                        "museo",
                        lat=41.111076842523865,
                        lon=14.213266798496122,
                        period_start=1869,
                        period_name="1500+ AD",
                        site_type="Museum",
                        name="Museo Campano",
                    )
                ]
            )
        )
        assert _kinds(got) == ["T11/museum-past-cutoff"]
        assert got[0].severity is M.Severity.MODERATE
        assert got[0].confidence is M.Confidence.UNVERIFIABLE
        assert "exhibits ancient material" in got[0].note
        assert "is 1369 years past the rest of world cutoff" in got[0].note

    def test_a_site_without_a_date_is_flagged_not_passed(self, t11: Any, world: Any) -> None:
        """Situs Megalit Tebing Tinggi, measured: no period_start and no period_name.

        `passes_date_cutoff()` includes a dateless record ("No date = include"); a census row
        saying `pass` would certify this site clean on a comparison that never happened.
        """
        got = t11.run(
            _ctx(
                [
                    _site(
                        "noda",
                        lat=-4.092807250453572,
                        lon=103.34416960986482,
                        period_start=None,
                        period_name=None,
                        site_type="Megalithic stones",
                        name="Situs Megalit Tebing Tinggi",
                    )
                ]
            )
        )
        assert _kinds(got) == ["T11/undecidable-date"]
        assert got[0].severity is M.Severity.MODERATE
        assert "No date = include" in got[0].note

    def test_a_museum_without_a_date_is_undecidable_not_a_museum_finding(
        self, t11: Any, world: Any
    ) -> None:
        """The Davidson Center, measured: a museum with no period at all - two unknowns."""
        got = t11.run(
            _ctx(
                [
                    _site(
                        "davidson",
                        lat=31.77523597458017,
                        lon=35.234309850374565,
                        period_start=None,
                        site_type="Museum",
                        name="The Davidson Center",
                    )
                ]
            )
        )
        assert _kinds(got) == ["T11/undecidable-date"]

    def test_a_site_without_coordinates_is_flagged_not_passed(self, t11: Any, world: Any) -> None:
        """No point means no region, and no region means no cutoff - never a silent pass."""
        got = t11.run(_ctx([_site("nopoint", lat=None, lon=None, period_start=1700)]))
        assert _kinds(got) == ["T11/undecidable-location"]

    def test_a_period_start_that_is_not_a_year_is_flagged_not_crashed(
        self, t11: Any, world: Any
    ) -> None:
        got = t11.run(_ctx([_site("text", lat=40.0, lon=-4.0, period_start="1500 AD")]))
        assert _kinds(got) == ["T11/undecidable-date"]
        assert "not a year" in got[0].note

    def test_a_region_the_two_geographies_disagree_about_is_undecidable(
        self, t11: Any, world: Any
    ) -> None:
        """lon -35 is the Americas to the longitude window and Africa to Natural Earth.

        With 800 AD the two rules give opposite verdicts, so neither may be asserted.
        """
        got = t11.run(_ctx([_site("at", lat=0.0, lon=-35.0, period_start=800)]))
        assert _kinds(got) == ["T11/ambiguous-region"]
        assert got[0].confidence is M.Confidence.UNVERIFIABLE
        assert "opposite scope verdicts" in got[0].note

    def test_the_disagreement_flips_both_ways(self, t11: Any, world: Any) -> None:
        """lon -25 is the rest of the world to the window and North America to Natural Earth."""
        got = t11.run(_ctx([_site("mx", lat=20.0, lon=-25.0, period_start=800)]))
        assert _kinds(got) == ["T11/ambiguous-region"]

    def test_a_region_disagreement_without_a_verdict_flip_is_not_flagged(
        self, t11: Any, world: Any
    ) -> None:
        """Hane, Marquesas Islands, measured: Oceania by Natural Earth, Americas by longitude.

        500 AD is inside both windows, so the site is in scope under either rule and the
        disagreement changes nothing. This is the real snapshot's only region disagreement.
        """
        got = t11.run(
            _ctx(
                [
                    _site(
                        "hane",
                        lat=-8.922833012266825,
                        lon=-139.53497854671417,
                        period_start=500,
                    )
                ]
            )
        )
        assert got == []

    def test_a_point_in_no_polygon_is_decided_by_the_window_and_says_so(
        self, t11: Any, world: Any
    ) -> None:
        """Open water: Natural Earth has no second opinion, and the evidence records that."""
        got = t11.run(_ctx([_site("sea", lat=0.0, lon=-70.0, period_start=2010)]))
        assert _kinds(got) == ["T11/out-of-window"]
        assert "longitude window alone decided the region" in got[0].note
        assert "no feature (open water)" in got[0].evidence[2].quote

    def test_an_ocean_feature_is_not_a_continent(self, t11: Any, world: Any) -> None:
        """Natural Earth draws the seas as polygons; they must not answer a region question."""
        got = t11.run(_ctx([_site("pac", lat=30.0, lon=-150.0, period_start=2010)]))
        assert _kinds(got) == ["T11/out-of-window"]
        assert "CONTINENT = n/a" in got[0].evidence[2].quote
        assert "no continent" in got[0].note

    def test_nothing_is_auto_applicable(self, t11: Any, world: Any) -> None:
        """E4's column does not exist yet, and which side is wrong is a factual question."""
        sites = [
            _site("late", lat=40.0, lon=-4.0, period_start=1775, site_type="Castle/palace"),
            _site("mus", lat=41.1, lon=14.2, period_start=1869, site_type="Museum"),
            _site("noda", lat=-4.0, lon=103.3, period_start=None),
            _site("at", lat=0.0, lon=-35.0, period_start=800),
        ]
        got = t11.run(_ctx(sites))
        assert len(got) == 4
        assert {f.proposal for f in got} == {M.Proposal.REVIEW}
        assert {f.proposed_value for f in got} == {None}
        assert {f.field for f in got} == {"scope_status"}
        assert not any(f.applicable for f in got)

    def test_the_verdict_agrees_with_the_projects_own_scope_function(
        self, t11: Any, world: Any
    ) -> None:
        """Where the two can be compared, `passes_date_cutoff()` and T11 must not disagree."""
        from pipeline.normalizers.dates import passes_date_cutoff

        sites = [
            _site("a", lat=40.0, lon=-4.0, period_start=500),
            _site("b", lat=40.0, lon=-4.0, period_start=501),
            _site("c", lat=20.0, lon=-100.0, period_start=1500),
            _site("d", lat=20.0, lon=-100.0, period_start=1501),
            _site("e", lat=-4.0, lon=103.3, period_start=-3500),
            _site("f", lat=51.35, lon=-2.35, period_start=1775),
        ]
        flagged = {f.site_id for f in t11.run(_ctx(sites))}
        assert flagged == {s["id"] for s in sites if not passes_date_cutoff(s)}
        assert flagged == {"b", "d", "f"}

    def test_oceania_is_in_scope_through_1500_ad(self, t11: Any, world: Any) -> None:
        """O7 (owner, 2026-09-26): "Ozeanien wie Amerika". An Oceania row dated 1200 AD passes
        whether the longitude window holds it or not; 1501 AD is past the cutoff and the note
        names the region."""
        from pipeline.normalizers.dates import passes_date_cutoff

        sites = [
            {**_site("syd", lat=-33.87, lon=151.21, period_start=1200), "country": "Australia"},
            {**_site("late", lat=-33.87, lon=151.21, period_start=1501), "country": "Australia"},
            {**_site("noum", lat=-22.27, lon=166.45, period_start=1200), "country": "France"},
            {**_site("paris", lat=48.85, lon=2.35, period_start=1200), "country": "France"},
            {**_site("rapa", lat=-27.11, lon=-109.39, period_start=1200), "country": "Chile"},
        ]
        got = t11.run(_ctx(sites))
        assert {f.site_id for f in got} == {"late", "paris"}
        assert {f.site_id for f in got} == {s["id"] for s in sites if not passes_date_cutoff(s)}
        late = next(f for f in got if f.site_id == "late")
        assert "past the Oceania cutoff of 1500 AD" in late.note

    def test_the_marquesas_pair_now_agrees_in_region_too(self, t11: Any, world: Any) -> None:
        """Hane (stored as France, inside the window) is Oceania to both geographies since O7, so
        a date the Americas' window admits cannot come out ambiguous."""
        hane = {
            **_site("hane", lat=-8.92, lon=-139.53, period_start=1200),
            "country": "France",
        }
        assert t11.run(_ctx([hane])) == []


# ------------------------------------------------------------------------- the contract
class TestT11Contract:
    def test_it_declares_the_census_contract(self, t11: Any) -> None:
        assert t11.TEST_ID == "T11"
        assert t11.DIMENSION == "SCOPE"
        assert callable(t11.run)
        assert "Oceania" in t11.NAME  # O7: Americas and Oceania through 1500 AD

    def test_what_it_quotes_from_dates_py_stands_in_dates_py(self, t11: Any, world: Any) -> None:
        """A finding quotes the project's scope function as its evidence: every quote of
        `pipeline/normalizers/dates.py` must stand in that file as it is now, and cite no line
        number (O7 moved the lines once already). Code quotes join lines with "; "."""
        dates = (REPO / "pipeline" / "normalizers" / "dates.py").read_text(encoding="utf-8")
        source = " ".join(dates.split())
        findings = t11.run(
            _ctx(
                [
                    _site("noda", lat=10.0, lon=10.0, period_start=None),
                    _site("nopoint", lat=None, lon=None, period_start=1700),
                ]
            )
        )
        quoted = [
            e for f in findings for e in f.evidence if "pipeline/normalizers/dates.py" in e.source
        ]
        assert {f.test_id for f in findings} == {"T11/undecidable-date", "T11/undecidable-location"}
        assert len(quoted) >= 3
        for evidence in quoted:
            assert ":" not in evidence.source.split("dates.py", 1)[1].split(" ", 1)[0]
            for fragment in evidence.quote.split("; "):
                assert " ".join(fragment.split()) in source, fragment
        for finding in findings:
            assert "dates.py:" not in finding.note

    def test_the_cutoffs_are_the_projects_own_constants(self, t11: Any) -> None:
        """Re-typing 1500/500 here would let the census drift from the loader silently."""
        from pipeline.normalizers.dates import (
            AMERICAS_LON_MAX,
            AMERICAS_LON_MIN,
            DATE_CUTOFF_AMERICAS,
            DATE_CUTOFF_OCEANIA,
            DATE_CUTOFF_REST_OF_WORLD,
            e3_region,
            passes_date_cutoff,
        )

        rule = t11._scope_rule()
        assert (rule.americas_lon_min, rule.americas_lon_max) == (
            AMERICAS_LON_MIN,
            AMERICAS_LON_MAX,
        )
        assert rule.cutoffs[rule.americas] == DATE_CUTOFF_AMERICAS == 1500
        assert rule.cutoffs[rule.oceania] == DATE_CUTOFF_OCEANIA == 1500
        assert rule.cutoffs[rule.rest_of_world] == DATE_CUTOFF_REST_OF_WORLD == 500
        assert rule.passes is passes_date_cutoff
        assert rule.region_of is e3_region

    def test_the_region_rule_is_the_projects_own(self, t11: Any) -> None:
        """Rewritten for O7 (2026-09-26): `region` took a longitude and knew two regions; it now
        takes the row, because Oceania is decided by the row's country. The longitude window's
        edges are asserted as before, and the Oceania cases are added."""
        rule = t11._scope_rule()

        def row(lon: float, country: str = "Nowhere", lat: float = 0.0) -> dict[str, Any]:
            return {"lon": lon, "lat": lat, "country": country}

        assert rule.region(row(-170.0)) == ("Americas", 1500)
        assert rule.region(row(-30.0)) == ("Americas", 1500)
        assert rule.region(row(-29.99)) == ("rest of world", 500)
        assert rule.region(row(0.0)) == ("rest of world", 500)
        assert rule.region(row(144.81)) == ("rest of world", 500)
        # House of Taga, Tinian (measured on production 2026-09-26)
        assert rule.region(row(145.62, "Northern Mariana Islands", 14.97)) == ("Oceania", 1500)
        # Ahu Akivi, stored as Chile: Oceania, not the Americas, though the window holds it
        assert rule.region(row(-109.39, "Chile", -27.11)) == ("Oceania", 1500)
        assert rule.region(row(-70.65, "Chile", -33.45)) == ("Americas", 1500)
        with pytest.raises(AssertionError, match="without a longitude"):
            rule.region({"lon": None, "lat": None, "country": "Australia"})

    def test_natural_earth_s_oceania_answers_the_americas_cutoff(self, t11: Any) -> None:
        """O7: the second geography must not call an Oceania point a 500 AD region, or every
        Oceania site dated 501-1500 would come out ambiguous."""
        rule = t11._scope_rule()
        assert rule.continent_cutoff("Oceania") == 1500
        assert rule.continent_cutoff("North America") == 1500
        assert rule.continent_cutoff("South America") == 1500
        assert rule.continent_cutoff("Asia") == 500
        assert rule.continent_cutoff("Europe") == 500
        assert rule.continent_cutoff("Africa") == 500

    def test_it_never_touches_the_network(self, t11: Any) -> None:
        """Scope is a pure function of stored values: a `collect()` here would be a defect."""
        assert not hasattr(t11, "collect")

    def test_a_missing_dataset_raises_instead_of_reporting_nothing(
        self, t11: Any, tmp_path: Path
    ) -> None:
        """ "Could not check" must never become "checked and clean"."""
        with pytest.raises(FileNotFoundError, match="missing"):
            t11.run(_ctx([_site("a", lat=51.0, lon=0.0, period_start=1775)], cache=tmp_path))

    def test_the_region_vocabulary_is_the_one_the_module_uses(self, t11: Any) -> None:
        assert t11.AMERICAS_CONTINENTS == {"North America", "South America"}
        assert "Seven seas (open ocean)" in t11.NO_REGION_CONTINENTS
        assert t11.FIELD == "scope_status"


# --------------------------------------------------------------------- against the snapshot
@needs_dataset
class TestT11OnTheSnapshot:
    """The claims that are about the data: S12, and the plan's open 69-versus-84 question."""

    @pytest.fixture(scope="class")
    def snapshot(self) -> Any:
        from census.snapshot import Snapshot

        return Snapshot(str(SNAPSHOT))

    @pytest.fixture(scope="class")
    def findings(self, t11: Any, snapshot: Any) -> list[M.Finding]:
        return t11.run(_ctx(snapshot.sites))

    def test_it_reproduces_the_plans_gate_s12(
        self, findings: list[M.Finding], snapshot: Any
    ) -> None:
        """§7 S12: 4,920 pass / 84 fail. T11 must land on exactly those two numbers."""
        assert len(snapshot.sites) == 5004
        assert len(findings) == 84  # one finding per flagged site, no site flagged twice
        assert len({f.site_id for f in findings}) == 84
        assert len(snapshot.sites) - 84 == 4920

    def test_the_69_versus_84_question_is_the_15_sites_without_a_date(
        self, findings: list[M.Finding]
    ) -> None:
        """§8.1's SQL gives 69; S12 reports 84. The difference is the dateless rows, not a rule.

        The assessment's own S12 line (`output/audit_inventory/_wf2_result.json`) says it
        verbatim: "4.920 pass / 84 fail (69 ausserhalb, 15 ohne period_start)".
        """
        late = [f for f in findings if f.test_id in ("T11/out-of-window", "T11/museum-past-cutoff")]
        dateless = [f for f in findings if f.test_id == "T11/undecidable-date"]
        assert (len(late), len(dateless)) == (69, 15)
        assert len(late) + len(dateless) == 84
        assert {f.test_id for f in findings} == {
            "T11/out-of-window",
            "T11/museum-past-cutoff",
            "T11/undecidable-date",
        }

    def test_the_museum_rule_splits_the_69_as_the_plan_says(
        self, findings: list[M.Finding]
    ) -> None:
        """§8.1: "18 carry `site_type = 'Museum'` where period_start is the founding year"."""
        museums = [f for f in findings if f.test_id == "T11/museum-past-cutoff"]
        assert len(museums) == 18
        assert all("exhibits ancient material" in f.note for f in museums)
        assert len([f for f in findings if f.test_id == "T11/out-of-window"]) == 51

    def test_both_gold_standard_scope_errors_are_caught(self, findings: list[M.Finding]) -> None:
        """The blinded sample's E3 errors (`GOLD_STANDARD.md:239` and `:285`)."""
        flagged = {f.site_id for f in findings}
        assert MIDFORD_CASTLE in flagged
        assert KSAR_EL_BARKA in flagged

    def test_the_fabricated_date_it_cannot_see_is_named_not_claimed(
        self, findings: list[M.Finding]
    ) -> None:
        """Font dels Coms (`GOLD_STANDARD.md:883`) passes: -3500 is inside the window.

        The third blinded E3 error is invisible to any check on stored dates - it is wrong
        *because* period_start is fabricated - and this test pins that blind spot, so nobody
        reads T11's pass rows as "all E3 errors found".
        """
        assert FONT_DELS_COMS not in {f.site_id for f in findings}
