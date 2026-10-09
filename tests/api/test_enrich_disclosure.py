# SPDX-License-Identifier: AGPL-3.0-only
"""Lane E (a W or S text that the enrichment lane added AI-written, web-sourced sentences to, orchestrator
decision X1 of 2026-10-08) writes `raw_data._description_provenance` of lane E
(`model4.EnrichedProvenance`): the AI wrote part of the words (`ai: generated`) and the text still adapts
the pinned Wikipedia revision, so the CC BY-SA attribution line stays, with a change note that says the
text was extended. Every reader - `/api/sites/{id}`, the SSR payload and the public v1 API - derives it
through `api/services/description_provenance`; this holds that derivation to the writer's own record,
built by the lane's code (`scripts/remediation/phase4/wc4.py`), not typed by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.routes import sites as sr
from api.services import description_provenance as DP
from tests.fake_sql import RecordingSession

REMEDIATION = Path(__file__).resolve().parents[2] / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

from phase4 import model4 as M  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402

SITE_ID = "4a5a324f-0000-4000-8000-0000000000bb"
BASE = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]. "
    "They date to approximately 3150 BC [1]. "
    "The site was excavated by Themistocles Zammit in 1915 [1]."
)
PERMALINK = "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567"
RESEARCH = "https://www.example.edu/malta/tarxien-research"
NEW = "Spiral reliefs decorate limestone slabs inside the temples."


def _record() -> tuple[str, dict]:
    """The text and `raw_data` of an enriched W text, built by the lane's own code."""
    from tests.remediation import wn_fixtures as WX

    raw = WX.p4_site_raw(BASE)
    base = WC4.Base(text=BASE, citations=tuple(raw[M.CITATIONS_KEY]))
    composed = WC4.compose(
        [WC4.Decision(1, NEW, WC4.Verdict.KEEP, None, None)],
        {1: [WC4.Quote(url=RESEARCH, title="Tarxien Research", quote="q" * 30)]},
        base=base,
    )
    provenance = WC4.enriched_provenance(
        raw, composed, base=base, ai_system=M.AI_SYSTEM_CLAUDE, marking=WC4.Marking.PHASE4
    )
    new = {**raw, M.CITATIONS_KEY: list(composed.citations), M.PROVENANCE_KEY: provenance.to_dict()}
    return composed.description, new


def test_lane_e_is_a_lane_whose_text_names_its_wikipedia_source():
    assert "E" in DP.ATTRIBUTION_LANES and DP.ENRICHMENT_LANE == M.Lane.E.value
    assert "E" not in DP.NO_LICENCE_LANES  # it keeps the licence of the pinned revision


def test_an_enriched_text_is_served_with_the_ai_footnote_and_the_attribution_line():
    text, raw = _record()
    disclosure = DP.description_disclosure(DP.provenance_of(raw), text)
    source = raw[M.PROVENANCE_KEY]["sources"][0]
    assert disclosure == {
        "ai": "generated",
        "lane": "E",
        "aiSystem": M.AI_SYSTEM,  # the pinned text named MiniMax: both writes stay named
        "licence": "CC BY-SA 4.0",
        "attribution": {
            "title": "Tarxien Temples",
            "url": source["url"],
            "licence": "CC BY-SA 4.0",
            "licenceUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "changes": "sentences selected, shortened and extended",
            "revisionDate": "2026-09-01",
        },
    }


def test_the_disclosure_is_a_statement_about_one_text_a_changed_description_claims_nothing():
    text, raw = _record()
    assert DP.description_disclosure(DP.provenance_of(raw), text + " Edited.") is None


def test_a_lane_e_record_without_its_attribution_source_fails_loudly_on_every_reader():
    text, raw = _record()
    provenance = {**raw[M.PROVENANCE_KEY], "sources": []}
    with pytest.raises(ValueError, match="no single cited source"):
        DP.description_disclosure(provenance, text)


def test_lane_e_has_no_card_key_so_a_phase_5_card_is_never_claimed_for_it():
    text, raw = _record()
    provenance = DP.provenance_of(raw)
    assert provenance["card"] is None
    assert DP.card_ai(provenance, None, "A card text.") is None


def test_the_site_api_serves_an_enriched_text_with_its_citations_and_the_attribution():
    text, raw = _record()
    row = SimpleNamespace(
        id=SITE_ID, source_id="ancient_nerds", source_record_id="an-1", name="Tarxien Temples",
        lat=35.8692, lon=14.5122, site_type="Temple complex", period_start=-3150, period_end=None,
        period_name="3000 BC", country="Malta", description=text, thumbnail_url=None,
        source_url=None, raw_data=raw, scope_status=None, card_description="An old card.",
        best_wiki_url=None, source_language=None,
    )  # fmt: skip
    resp = sr.get_site_detail(SITE_ID, db=RecordingSession({"WHERE us.id::text = :site_id": [row]}))
    assert resp["descriptionAi"] == "generated"
    assert resp["descriptionAttribution"]["changes"] == "sentences selected, shortened and extended"
    assert resp["descriptionAttribution"]["title"] == "Tarxien Temples"
    assert [c["n"] for c in resp["descriptionCitations"]] == [1, 2]
    assert resp["descriptionCitations"][1]["url"] == RESEARCH
