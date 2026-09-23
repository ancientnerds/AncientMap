"""Does T02 (point-in-polygon) fire, and only when it should?

T02 reads two things: the site's `country` plus `lat`/`lon`, and Natural Earth's 10m
admin-0 polygons. These tests drive it with synthetic sites carrying a *known* relation to
the reference data - inside, just offshore, across the antimeridian, in another country -
and assert what a census row will say about each. The coordinates marked "measured" were
read out of this repository's own snapshot so the fixtures are real data, not invented
points; every expectation below was confirmed against the module before it was written
down.

They are deliberately not end-to-end: no snapshot load, no network. The reference dataset
has to be in the cache (one `--collect` run fetches it), so the class is skipped with a
reason when it is absent rather than silently passing.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402

CACHE = REPO / "output" / "remediation" / "cache"
NE_SHAPEFILE = CACHE / "naturalearth" / "ne_10m_admin_0_countries.shp"


def _ctx(sites: list[dict], cache: Path = CACHE) -> SimpleNamespace:
    """The parts of Context T02 reads: `.sites` and `.cache`."""
    return SimpleNamespace(
        sites=sites,
        cache=cache,
        snap=SimpleNamespace(rows=lambda *a, **k: [], by=lambda *a, **k: {}),
        site_ids=lambda: {str(s["id"]) for s in sites},
    )


def _site(sid: str, country: str, lat: float, lon: float, name: str = "") -> dict[str, Any]:
    return {
        "id": sid,
        "source_id": "ancient_nerds",
        "name": name or f"Site {sid}",
        "country": country,
        "lat": lat,
        "lon": lon,
    }


needs_dataset = pytest.mark.skipif(
    not NE_SHAPEFILE.exists(),
    reason=f"Natural Earth cache not present ({NE_SHAPEFILE}); run the census with --collect",
)


@needs_dataset
class TestT02AdminCountry:
    @pytest.fixture(scope="class")
    def t02(self) -> Any:
        import importlib

        return importlib.import_module("census.tests.t02_admin_country")

    # ------------------------------------------------------------------ it passes
    def test_inside_a_multi_part_country_produces_nothing(self, t02):
        """Hawaii is part 300-odd of 344 in one United States polygon."""
        got = t02.run(_ctx([_site("a", "USA", 19.6, -155.5)]))
        assert got == []

    def test_easter_island_is_chile(self, t02):
        """`Chile, Easter Island` must resolve Chile - and Chile's polygon carries the island."""
        got = t02.run(_ctx([_site("a", "Chile, Easter Island", -27.12, -109.35)]))
        assert got == []

    def test_england_resolves_through_the_projects_own_mapping(self, t02):
        """1,257 sites are England/Scotland/Wales - never countries in Natural Earth.

        Without the project's country->ISO mapping these would all report "unknown country
        string". Stonehenge is the fixture because the resolution path (not the coordinate)
        is what is under test.
        """
        got = t02.run(_ctx([_site("a", "England", 51.1789, -1.8262)]))
        assert got == []

    def test_a_coastal_site_within_tolerance_is_not_flagged(self, t02):
        """Measured: Heraion of Perachora lies 775 m outside Natural Earth's Greece polygon.

        Coastline generalisation and a 5-decimal coordinate can produce that on their own,
        which is what the 1 km tolerance is for.
        """
        got = t02.run(
            _ctx(
                [_site("a", "Greece", 38.02822459578033, 22.85252145416611, "Heraion of Perachora")]
            )
        )
        assert got == []

    def test_a_sovereign_claim_covers_its_territories(self, t02):
        """Nuuk is Greenland; `Denmark` is the sovereign and must not be accused.

        `France`/French Polynesia is the case this rule was measured on (Marquesas, 5,486 km
        from the French mainland); Nuuk is used here so the test does not depend on which
        dependency happens to be in the snapshot.
        """
        got = t02.run(_ctx([_site("a", "Denmark", 64.181, -51.694)]))
        assert got == []

    # ---------------------------------------------------------------- it fires
    def test_outside_by_more_than_one_kilometre_is_flagged(self, t02):
        """Measured: Ksar Lalla Fatma is 1.2 km outside Algeria, inside Tunisia."""
        got = t02.run(
            _ctx([_site("a", "Algeria", 36.84204635029945, 8.656110035152485, "Ksar Lalla Fatma")])
        )
        assert len(got) == 1
        finding = got[0]
        assert finding.test_id == "T02/outside-polygon"
        assert finding.field == "country"
        assert finding.severity is M.Severity.COSMETIC
        assert "1.2 km outside" in finding.note, finding.note
        assert "Tunisia" in finding.note, "the note must say where Natural Earth puts the point"
        assert finding.proposal is M.Proposal.REVIEW
        assert finding.proposed_value is None, "a guess is worse than a flag"
        assert finding.confidence is M.Confidence.UNVERIFIABLE
        assert not finding.applicable, "REVIEW is never auto-applicable"
        assert len(finding.evidence) >= 2

    def test_a_gross_mismatch_is_severe(self, t02):
        """Measured: a site claimed as Pakistan whose coordinates lie in Peru, 15,083 km away."""
        got = t02.run(_ctx([_site("a", "Pakistan", -9.399608434194468, -76.82616670438007)]))
        assert len(got) == 1
        assert got[0].severity is M.Severity.SEVERE
        assert "Peru" in got[0].note

    def test_antimeridian_is_measured_the_short_way(self, t02):
        """Fiji's polygon has parts on both sides of +/-180 (bounds -180.0 to 180.0).

        A single planar measurement of this point would report ~39,000 km; the wrapped one
        reports 42 km, which lands in the `moderate` band. The assertion is on the reported
        order of magnitude, so it fails if the wrap handling is ever removed.
        """
        got = t02.run(_ctx([_site("a", "Fiji", -17.0, -179.5)]))
        assert len(got) == 1
        assert got[0].severity is M.Severity.MODERATE
        km = float(got[0].note.split("lies ")[1].split(" km outside")[0])
        assert 10.0 < km < 200.0, f"{km} km is not the antimeridian-corrected distance"

    def test_unmatched_country_is_a_review_finding_not_a_guess(self, t02):
        """A sea is a real place and not an admin-0 feature - say so, do not force it.

        Rewritten 2026-09-22: the old example, `Northern Ireland` at 54.6/-5.9, now resolves to GB
        in the project's vocabulary (owner decision B9) and is tested below as a match. `Baltic
        Sea` at the snapshot's own point (61.377/18.448, the row T05 names) is still unmatched;
        the premise is asserted first, so a vocabulary that learns it fails here visibly.
        """
        assert t02._project_iso("Baltic Sea") is None
        got = t02.run(_ctx([_site("a", "Baltic Sea", 61.377, 18.448)]))
        assert len(got) == 1
        finding = got[0]
        assert finding.test_id == "T02/unmatched-country"
        assert finding.proposal is M.Proposal.REVIEW
        assert finding.proposed_value is None
        assert finding.confidence is M.Confidence.UNVERIFIABLE
        assert not finding.applicable
        assert finding.severity is M.Severity.COSMETIC
        assert "vocabulary" in finding.note

    def test_northern_ireland_resolves_to_the_united_kingdom(self, t02):
        """Belfast's point, claimed as `Northern Ireland`: GB in the project's vocabulary, inside
        Natural Earth's United Kingdom polygon, so no finding - the same as England/Wales/Scotland."""
        assert t02._project_iso("Northern Ireland") == "GB"
        assert t02.run(_ctx([_site("a", "Northern Ireland", 54.6, -5.9)])) == []
        atlas = t02._atlas(_ctx([]))
        claim = atlas.claim("Northern Ireland")
        assert claim is not None and claim.matched == ("United Kingdom",)

    def test_contested_ground_is_not_absorbed_by_the_sovereignty_rule(self, t02):
        """Herodion lies in Natural Earth's `Palestine`, whose SOVEREIGNT is `Israel`.

        Widening a claim onto contested ground would make a political ruling with a polygon;
        the point is 4.8 km outside Israel and belongs in the queue.
        """
        got = t02.run(
            _ctx(
                [
                    _site(
                        "a",
                        "Israel",
                        31.66577278948979,
                        35.241733093253366,
                        "Herodion National Park",
                    )
                ]
            )
        )
        assert len(got) == 1
        assert "Palestine" in got[0].note

    # ------------------------------------------------------------ contract details
    def test_severity_bands(self, t02):
        assert t02._severity(t02.TOLERANCE_M + 1) is M.Severity.COSMETIC
        assert t02._severity(t02.COSMETIC_MAX_M) is M.Severity.COSMETIC
        assert t02._severity(t02.COSMETIC_MAX_M + 1) is M.Severity.MODERATE
        assert t02._severity(t02.MODERATE_MAX_M) is M.Severity.MODERATE
        assert t02._severity(t02.MODERATE_MAX_M + 1) is M.Severity.SEVERE

    def test_applies_only_to_sites_with_a_country_and_a_point(self, t02):
        ctx = _ctx([])
        mine = _site("a", "Greece", 37.98, 23.72)
        assert t02.applies_to(mine, ctx)
        assert not t02.applies_to(_site("b", "", 37.98, 23.72), ctx)
        assert not t02.applies_to({"id": "c", "country": "Greece"}, ctx)
        assert not t02.applies_to({**mine, "lat": None}, ctx)
        assert t02.run(_ctx([_site("b", "", 37.98, 23.72)])) == [], "no country, no finding"

    def test_every_finding_is_evidenced_and_attributed_to_the_right_site(self, t02):
        sites = [
            _site("a", "Greece", 37.98, 23.72, "Athens, in Greece"),
            _site("b", "Pakistan", -9.399608434194468, -76.82616670438007),
            _site("c", "Baltic Sea", 55.0, 18.0),
        ]
        got = t02.run(_ctx(sites))
        assert {f.site_id for f in got} == {"b", "c"}
        for finding in got:
            assert finding.evidence, "every finding must carry the source that supports it"
            assert finding.test_id.startswith("T02")
            assert finding.dimension == "D3-LOCATION"
            assert finding.current_value is not None

    def test_a_missing_dataset_raises_instead_of_reporting_clean(self, t02, tmp_path):
        """The inversion this census exists to prevent: 'could not check' must never pass."""
        with pytest.raises(FileNotFoundError, match="missing"):
            t02.run(_ctx([_site("a", "Greece", 37.98, 23.72)], cache=tmp_path))
