"""Does T05 have teeth?

A check that reports zero findings is indistinguishable from a check that is broken, and
"every country is canonical" is only a result if the same code fires on a country value
that is not. These tests feed T05 synthetic sites carrying the defects the check exists to
find - one per defect class the snapshot actually contains - and assert that it fires,
without guessing a value where the project cannot prove one.

No snapshot, no network, no database: the site dicts are the minimum shape the check
reads (`id`, `country`), so a check that starts depending on a new column fails here
rather than silently reporting fewer findings.
"""

from __future__ import annotations

import importlib
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


def _ctx(sites: list[dict[str, Any]]) -> SimpleNamespace:
    """The only part of Context this check reads: `.sites`."""
    return SimpleNamespace(sites=sites)


def _site(sid: str, country: Any) -> dict[str, Any]:
    return {"id": sid, "source_id": "ancient_nerds", "name": f"Site {sid}", "country": country}


@pytest.fixture(scope="module")
def t05() -> Any:
    return importlib.import_module("census.tests.t05_country_values")


class TestT05CountryValues:
    """t05_country_values: a country value the project can read, under one spelling."""

    def test_canonical_country_produces_nothing(self, t05):
        assert t05.run(_ctx([_site("a", "Peru"), _site("b", "Türkiye")])) == []

    def test_deliberate_uk_design_is_not_a_defect(self, t05):
        """England/Wales/Scotland are project design (plan §4.3.2), not a broken value."""
        got = t05.run(_ctx([_site("a", "England"), _site("b", "Wales"), _site("c", "Scotland")]))
        assert got == []

    def test_territories_the_vocabularies_carry_are_not_flagged(self, t05):
        """Greenland and the Northern Mariana Islands are known to a vocabulary."""
        assert t05.run(_ctx([_site("a", "Greenland"), _site("b", "Northern Mariana Islands")])) == []

    def test_disambiguated_name_is_set_to_the_plain_country(self, t05):
        got = t05.run(_ctx([_site("a", "Georgia (country)")]))
        assert len(got) == 1
        f = got[0]
        assert f.proposal is M.Proposal.SET
        assert f.proposed_value == "Georgia"
        assert f.applicable, "the project's own mapping proves the country; no second source needed"
        assert f.severity is M.Severity.SEVERE, "the narrator reads the parenthetical aloud"
        assert f.evidence, "every finding must carry the source that supports it"
        assert f.test_id == "T05/disambiguated"

    def test_compound_label_is_set_to_its_country(self, t05):
        got = t05.run(_ctx([_site("a", "Chile, Easter Island")]))
        assert len(got) == 1
        f = got[0]
        assert (f.proposal, f.proposed_value) == (M.Proposal.SET, "Chile")
        assert f.applicable

    def test_sea_is_reviewed_never_guessed(self, t05):
        got = t05.run(_ctx([_site("a", "Baltic Sea")]))
        assert len(got) == 1
        f = got[0]
        assert f.proposal is M.Proposal.REVIEW
        assert f.proposed_value is None, "which coastal state owns the water is not decidable here"
        assert f.confidence is M.Confidence.UNVERIFIABLE
        assert not f.applicable

    def test_value_in_neither_vocabulary_is_reviewed(self, t05):
        got = t05.run(_ctx([_site("a", "Northern Ireland")]))
        assert len(got) == 1
        assert got[0].proposal is M.Proposal.REVIEW
        assert got[0].proposed_value is None

    def test_a_historical_entity_is_never_modernised(self, t05):
        """A site inside the Ottoman Empire may properly carry that name - no replacement."""
        got = t05.run(_ctx([_site("a", "Ottoman Empire"), _site("b", "USSR"), _site("c", "Persia")]))
        assert len(got) == 3
        for f in got:
            assert f.proposal is M.Proposal.REVIEW
            assert f.proposed_value is None
            assert not f.applicable

    def test_missing_country_is_a_finding_not_a_silent_pass(self, t05):
        for raw in (None, "", "   "):
            got = t05.run(_ctx([_site("a", raw)]))
            assert len(got) == 1, raw
            assert got[0].proposal is M.Proposal.REVIEW
            assert got[0].proposed_value is None

    def test_every_proposed_value_is_a_fixed_point_and_the_same_country(self, t05):
        """The guard that makes the advice durable: the project reads old and new as one
        country, and a re-run of this check would leave the repaired value alone."""
        codes, normalize = t05._vocabulary()
        sites = [
            _site("a", "Georgia (country)"),
            _site("b", "Chile, Easter Island"),
            _site("c", "Georgia (Country)"),
            _site("d", "georgia (country)"),
        ]
        proposed = 0
        for f in t05.run(_ctx(sites)):
            if f.proposal is not M.Proposal.SET:
                continue
            proposed += 1
            assert t05._iso(f.current_value, normalize) == t05._iso(f.proposed_value, normalize)
            assert t05._flag_code(f.proposed_value, codes) is not None
            assert t05._is_canonical(f.proposed_value, codes, normalize), (
                f"{f.proposed_value!r} would be flagged again on the next run"
            )
        assert proposed == len(sites)

    def test_findings_are_attributed_to_the_right_site(self, t05):
        got = t05.run(_ctx([_site("a", "Peru"), _site("b", "Baltic Sea")]))
        assert [f.site_id for f in got] == ["b"]
        assert got[0].field == "country"
        assert got[0].test_id.startswith("T05")
