# SPDX-License-Identifier: AGPL-3.0-only
"""Lane WN (a description written from web pages for a site that had none, owner decision of
2026-10-01) writes `raw_data._description_provenance` of lane N (`model4.WebProvenance`): the AI
wrote the words (`ai: generated`), no licence, no attribution line and no card key. Every reader -
`/api/sites/{id}`, the SSR payload and the public v1 API - derives it through
`api/services/description_provenance`; this holds that derivation to the writer's own record, built
by the lane's code (`scripts/remediation/phase4/model4.py`), not typed by hand.
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

SITE_ID = "4a5a324f-0000-4000-8000-0000000000aa"
TEXT = "The Tarxien Temples form a complex in Malta [1]."
WIKI = "https://en.wikipedia.org/wiki/Tarxien_Temples"


def _raw(text: str = TEXT) -> dict:
    return {
        "description_citations": [
            {"n": 1, "url": WIKI, "title": "Tarxien Temples", "domain": "en.wikipedia.org"}
        ],
        DP.PROVENANCE_KEY: M.WebProvenance(desc_sha256=M.text_sha256(text)).to_dict(),
    }


def test_a_lane_n_text_is_served_with_the_ai_footnote_and_claims_no_licence_or_attribution():
    disclosure = DP.description_disclosure(DP.provenance_of(_raw()), TEXT)
    assert disclosure == {
        "ai": "generated",
        "lane": "N",
        "aiSystem": M.AI_SYSTEM,
        "licence": None,
        "attribution": None,
    }


def test_a_lane_n_provenance_has_no_card_key_and_never_reads_as_a_card_claim():
    """`card_ai` reads the Phase-5 card key of a full provenance; a lane-N record has none, and the
    card of such a site is lane WB's (`_card_provenance`) - never an AttributeError or a KeyError."""
    provenance = DP.provenance_of(_raw())
    assert "card" not in provenance
    assert DP.card_ai(provenance, None, "A card text.") is None
    assert DP.card_ai(provenance, None, None) is None


def test_the_disclosure_is_a_statement_about_one_text_a_changed_description_claims_nothing():
    assert DP.description_disclosure(DP.provenance_of(_raw()), TEXT + " Edited.") is None


def test_the_site_api_serves_a_lane_n_text_with_its_citations_and_the_footnote():
    row = SimpleNamespace(
        id=SITE_ID, source_id="ancient_nerds", source_record_id="an-1", name="Tarxien Temples",
        lat=35.8692, lon=14.5122, site_type="Temple complex", period_start=-3150, period_end=None,
        period_name="3000 BC", country="Malta", description=TEXT, thumbnail_url=None,
        source_url=None, raw_data=_raw(), scope_status=None, card_description="An old card.",
        best_wiki_url=None, source_language=None,
    )  # fmt: skip
    resp = sr.get_site_detail(SITE_ID, db=RecordingSession({"WHERE us.id::text = :site_id": [row]}))
    assert resp["descriptionAi"] == "generated" and resp["descriptionAttribution"] is None
    assert resp["descriptionCitations"] == [
        {"n": 1, "url": WIKI, "title": "Tarxien Temples", "domain": "en.wikipedia.org"}
    ]


def test_the_writer_and_the_reader_agree_on_the_provenance_key_and_the_marks():
    assert DP.PROVENANCE_KEY == M.PROVENANCE_KEY
    assert DP.NO_LICENCE_LANES == {M.Lane.L.value, M.Lane.N.value}
    assert M.AiMark.GENERATED.value in DP.AI_MARKS


def test_an_unknown_ai_mark_still_fails_on_every_reader_alike():
    provenance = {**M.WebProvenance(desc_sha256=M.text_sha256(TEXT)).to_dict(), "ai": "wrote"}
    with pytest.raises(ValueError, match="not one of"):
        DP.description_disclosure(provenance, TEXT)
