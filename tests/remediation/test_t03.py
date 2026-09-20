"""Does T03 really catch the text years that contradict a site's period bucket?

The census reports "875 of 5,004 sites flagged" - a number that means nothing unless the
same code flags a contradiction when one is there and stays silent on the traps. These
tests feed `t03_years_in_text` synthetic sites carrying each defect and each
false-positive shape the check was built against, and assert both directions.

Deliberately not end-to-end: no snapshot, no network, no database. Each text below is a
real production shape (the site names in the comments are where it was measured), reduced
to the sentence that matters.
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

t03 = pytest.importorskip("census.tests.t03_years_in_text")


def _ctx(sites: list[dict], cards: dict[str, str] | None = None) -> SimpleNamespace:
    """The only part of Context T03 reads: `.sites` and the `card_stats` rows."""
    rows = {sid: [{"card_description": text}] for sid, text in (cards or {}).items()}
    return SimpleNamespace(
        sites=sites,
        snap=SimpleNamespace(by=lambda table: rows if table == "card_stats" else {}),
    )


def _site(sid: str, **over: Any) -> dict[str, Any]:
    base = {
        "id": sid,
        "source_id": "ancient_nerds",
        "name": f"Site {sid}",
        "period_start": None,
        "period_name": None,
        "description": "",
    }
    base.update(over)
    return base


def _flagged(site: dict, **kw: Any) -> list[M.Finding]:
    return t03.run(_ctx([site], **kw))


# ------------------------------------------------------------------ what is a claim
class TestExtraction:
    """A claim is a year that carries its own era - and a span is read as one claim."""

    @pytest.mark.parametrize(
        ("text", "intervals"),
        [
            ("Built 3500 BC.", [(-3500, -3500)]),
            ("occupied around 1500 BCE [1]", [(-1500, -1500)]),
            ("Torched in AD 500.", [(500, 500)]),
            ("founded by 500 AD", [(500, 500)]),
            ("dating to the 3rd millennium BC", [(-3000, -2001)]),
            ("from the 11th-millennium BC [1]", [(-11000, -10001)]),
        ],
    )
    def test_single_era_markers(self, text, intervals):
        got = [(m.lo, m.hi) for m in t03._claims(text)]
        assert got == intervals

    def test_range_across_the_era_boundary_is_one_span(self):
        """ "500 BC - 550 AD" (El Tintal) is one site phase, not two contradictions."""
        got = t03._claims("500 BC – 550 AD: El Tintal is a Maya site")
        assert [(m.lo, m.hi) for m in got] == [(-500, 550)]

    def test_range_with_the_marker_only_on_the_last_endpoint(self):
        """ "4300-3900 BC" - the bare 4300 must count backwards, not as 4300 AD."""
        got = t03._claims("Neolithic deposits dated 4300-3900 BC yielded decorated bowls")
        assert [(m.lo, m.hi) for m in got] == [(-4300, -3900)]

    def test_range_written_with_between_and_to(self):
        got = t03._claims("occupied from approximately 5000 BC to 2500 BC")
        assert [(m.lo, m.hi) for m in got] == [(-5000, -2500)]
        got = t03._claims("occupied 2500 to 2000 BC")
        assert [(m.lo, m.hi) for m in got] == [(-2500, -2000)]

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Excavations in 1963-1989 and c. 800 BC material came to light.", [("800 BC", -800)]),
            ("Restored in 1975 and c. 900 AD the church was rebuilt.", [("900 AD", 900)]),
            ("between 9100 and 8600 BCE", [("9100 and 8600 BCE", -9100)]),
            ("In 415 and 411 BC, citizens mustered here.", [("415 and 411 BC", -415)]),
        ],
    )
    def test_span_connectors_only_join_a_bare_endpoint(self, text, expected):
        """A filler word between a bare year and an ancient one means two statements."""
        assert [(m.raw, m.lo) for m in t03._claims(text)] == expected

    def test_citation_marker_is_not_a_span_endpoint(self):
        """A footnote number next to a year is not the other end of a range (§7.2)."""
        got = t03._claims("occupied from about 800 BC to AD 900 [1]. Kʼaxob is a Maya site")
        assert [(m.lo, m.hi) for m in got] == [(-800, 900)]

    def test_relative_age_and_before_present(self):
        got = t03._claims("used 1.2 million years ago")
        assert [(m.lo, m.hi) for m in got] == [(1950 - 1_200_000, 1950 - 1_200_000)]
        got = t03._claims("dated to 10,400 BP")
        assert [(m.lo, m.hi) for m in got] == [(1950 - 10_400, 1950 - 10_400)]

    def test_relative_age_governs_a_leading_endpoint(self):
        """ "14,800 and 10,500 years ago" (Winnemucca) - both endpoints, one age phrase."""
        got = t03._claims("dated to between 14,800 and 10,500 years ago")
        assert [(m.lo, m.hi) for m in got] == [(1950 - 14_800, 1950 - 10_500)]

    @pytest.mark.parametrize(
        "text",
        [
            "The hill was given away in 1985",  # Kit Hill
            "declared a Cultural Heritage of the Nation in November 2000",  # Hatunmarka
            "open since 1998, excavated in 1975, restored during the 19th century",
            "included 27,000 artifacts, 44,000 bones and 500,000 lithics",
            "spanning 4,000 years on one summit with a 19th-century chimney",
        ],
    )
    def test_modern_dates_without_an_era_are_not_claims(self, text):
        """The main trap: a bare year is a survey, a price or a count - never a period."""
        assert t03._claims(text) == []

    def test_modern_era_claims_are_dropped(self):
        assert t03._claims("The site was listed in AD 1985 and again in 1998 AD") == []

    def test_era_words_without_a_number_are_not_claims(self):
        """Eileithyia Cave's real dating reads like this; the check stays numeric."""
        assert t03._claims("used from the Neolithic to the Roman era") == []


# ------------------------------------------------------------------ what is a finding
class TestFindings:
    def test_description_that_contradicts_the_bucket_is_a_review_finding(self):
        site = _site(
            "a",
            period_start=-500,
            period_name="500 BC - 1 AD",
            description="The sanctuary was built in 4000 BC on the plain.",
        )
        got = _flagged(site)
        assert len(got) == 1
        f = got[0]
        assert f.test_id == "T03/all-outside"
        assert f.proposal is M.Proposal.REVIEW
        assert f.confidence is M.Confidence.UNVERIFIABLE
        assert f.proposed_value is None, "period_start is a sort key: T03 may not set one"
        assert not f.applicable, "REVIEW never carries a value that could be applied"
        assert f.field == "description"
        assert f.severity is M.Severity.MODERATE
        assert "4000 BC" in f.note

    def test_claim_attached_to_a_dating_verb_is_a_finding_on_its_own(self):
        """A site with an agreeing phase too, but its own dating placed elsewhere."""
        site = _site(
            "a",
            period_start=-1500,
            period_name="1500 - 500 BC",
            description="Occupied from 1200 BC. The Roman town was built in 100 AD.",
        )
        got = _flagged(site)
        assert [f.test_id for f in got] == ["T03/primary-outside"]

    def test_a_later_phase_without_a_dating_verb_is_not_a_finding(self):
        """Lerna: the description's own dating agrees, the later year is a structure."""
        site = _site(
            "a",
            period_start=-5000,
            period_name="< 4500 BC",
            description="A settlement inhabited from the Neolithic to the "
            "Mycenaean period (6th-1st millennium BC). Its most "
            "famous structure is the House of Tiles (c. 2500-2300 BC).",
        )
        assert _flagged(site) == []

    def test_a_text_that_also_states_the_declared_period_passes(self):
        site = _site(
            "a",
            period_start=-1500,
            period_name="1500 - 500 BC",
            description="Built in 1200 BC, rebuilt after the fire of 400 AD.",
        )
        assert _flagged(site) == []

    @pytest.mark.parametrize(
        ("start", "name", "year"),
        [
            (-4000, "4500 - 3000 BC", "around 3000 BC"),  # Menhir of Bulhoa
            (-1500, "1500 - 500 BC", "around 500 BC"),  # Stonea Camp
            (1, "1 - 500 AD", "Around 500 AD"),  # Margarita Tomb
        ],
    )
    def test_the_declared_edge_is_not_a_contradiction(self, start, name, year):
        """period_start sits on a bucket boundary on 75 % of the sites (§3.1, §4.3.1)."""
        site = _site(
            "a", period_start=start, period_name=name, description=f"The site dates to {year}."
        )
        assert _flagged(site) == []

    def test_card_contradiction_is_severe_and_reported_on_the_card_field(self):
        site = _site("a", period_start=-3000, period_name="3000 - 1500 BC")
        got = _flagged(site, cards={"a": "Founded around 300 BC on the Orontes."})
        assert len(got) == 1
        assert got[0].field == "card_description"
        assert got[0].severity is M.Severity.SEVERE  # §15.4: spoken in every short

    def test_a_card_that_repeats_the_description_raises_it_to_severe(self):
        site = _site(
            "a",
            period_start=-500,
            period_name="500 BC - 1 AD",
            description="The site was first built in 3000 BC.",
        )
        got = _flagged(site, cards={"a": "A megalith from around 2500 BC."})
        assert len(got) == 1, "one finding per site, the worse field is the one reported"
        assert got[0].field == "description"
        assert got[0].severity is M.Severity.SEVERE

    def test_site_without_a_period_is_not_applicable(self):
        """15 sites carry neither period_start nor a canonical period_name (§3.1)."""
        site = _site("a", description="A site the database dates nowhere.")
        assert t03.applies_to(site, _ctx([site])) is False
        assert _flagged(site) == []

    def test_non_canonical_period_name_does_not_decide_the_window(self):
        """Bayer's Lake > 1500 AD: period_name is not a bucket, period_start is."""
        site = _site(
            "a", period_start=None, period_name="> 1500 AD", description="Built in 3000 BC."
        )
        assert t03.applies_to(site, _ctx([site])) is False

    def test_deep_past_below_the_bucket_table_is_its_own_window(self):
        """Atapuerca at -1,400,000 must not be judged against the first bucket's floor."""
        site = _site(
            "a",
            period_start=-1_400_000,
            period_name="< 4500 BC",
            description="The cave was used 1.2 million years ago.",
        )
        assert _flagged(site) == []

    def test_period_name_widens_the_window_when_it_disagrees_with_period_start(self):
        site = _site(
            "a", period_start=1, period_name="1500 - 500 BC", description="Built around 800 BC."
        )
        assert _flagged(site) == []

    def test_evidence_quotes_the_text_and_the_declared_period(self):
        text = "The site was first built in 3000 BC, long before the declared bucket."
        site = _site("a", period_start=-500, period_name="500 BC - 1 AD", description=text)
        f = _flagged(site)[0]
        assert f.evidence[0].source == t03.TEXT_SOURCE["description"]
        assert f.evidence[0].quote in text
        assert {ev.source for ev in f.evidence} == {
            t03.TEXT_SOURCE["description"],
            "snapshot:unified_sites",
            "pipeline/utils/text.py:PERIOD_BUCKETS",
        }
        assert any("period_name" in ev.quote for ev in f.evidence)

    @pytest.mark.parametrize(
        ("start", "name", "text"),
        [
            (-500, "500 BC - 1 AD", "A settlement founded in the 2nd century AD."),
            (-1500, "1500 - 500 BC", "Founded around 400 BC on the Orontes."),
            (1, "1 - 500 AD", "The cave was used 15,000 BC and again in the 3rd century AD."),
        ],
    )
    def test_no_finding_ever_carries_a_value(self, start, name, text):
        """Every T03 finding is a question for Phase 3, never a proposed replacement."""
        site = _site("a", period_start=start, period_name=name, description=text)
        got = _flagged(site)
        assert got, "this text contradicts the declared bucket"
        for f in got:
            assert f.proposal is M.Proposal.REVIEW
            assert f.confidence is M.Confidence.UNVERIFIABLE
            assert f.proposed_value is None
            assert not f.applicable
