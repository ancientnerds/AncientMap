# SPDX-License-Identifier: AGPL-3.0-only
"""Lane WC (the sentence check, owner decision O5 of 2026-09-26) needs no change of the API: a
checked March text keeps lane L's provenance with its hash moved to the trimmed text, so every
reader derives the existing AI footnote from it (`descriptionAi: generated`, no attribution line,
no licence claimed); an unmarked old text checked by the lane still claims nothing; a cleared site
(description NULL, raw_data NULL) is a page without a description and without a disclosure. The
raw_data values here are built by the lane's own code (`scripts/remediation/phase4/wc4.py`), not
typed by hand, so a change of the lane's output that the readers would render differently turns
this red.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from api.routes import sites as sr
from api.services import description_provenance as DP
from tests.fake_sql import RecordingSession

REMEDIATION = Path(__file__).resolve().parents[2] / "scripts" / "remediation"
if str(REMEDIATION) not in sys.path:
    sys.path.insert(0, str(REMEDIATION))

from phase4 import model4 as M  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402

SITE_ID = "4a5a324f-0000-4000-8000-000000000001"
MARCH = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]. They were built "
    "by giants in one night."
)
WIKI = "https://en.wikipedia.org/wiki/Tarxien_Temples"


def _site(raw_data: dict | None, *, snapshot: str = "The pre-March text.") -> M.PlanSite:
    return M.PlanSite(
        site_id=SITE_ID, name="Tarxien Temples", aliases=(), country="Malta",
        site_type="Temple complex", period_start=-3150, period_end=None, lat=35.8692,
        lon=14.5122, description=MARCH, description_sha256=M.text_sha256(MARCH),
        raw_data=raw_data, raw_data_sha256=None if raw_data is None else "a" * 64, card=None,
        card_sha256=None, source_url=WIKI, wikidata_qid=None, enwiki_title=None,
        in_snapshot=True, snapshot_description=snapshot, flags=frozenset(),
    )  # fmt: skip


def _checked(
    raw_data: dict | None, *, keep: bool, snapshot: str = "The pre-March text."
) -> tuple[str | None, dict | None]:
    """What the lane writes for this site: the first sentence kept on a quote, the second dropped
    - or both dropped (`keep=False`)."""
    site = _site(raw_data, snapshot=snapshot)
    first, second = WC4.checked_sentences(MARCH)
    decisions = [
        WC4.Decision(1, first, WC4.Verdict.KEEP, None, None)
        if keep
        else WC4.Decision(1, first, WC4.Verdict.DROP, None, WC4.DropReason.UNSUPPORTED),
        WC4.Decision(2, second, WC4.Verdict.DROP, None, WC4.DropReason.CONTRADICTED),
    ]
    quotes = {1: [WC4.Quote(WIKI, "Tarxien Temples - Wikipedia", "an archaeological complex")]}
    composed = WC4.compose(decisions, quotes if keep else {})
    check = (
        WC4.check_record(decisions, composed, quotes, run="wc-api", checked=MARCH) if keep else None
    )
    return composed.description, WC4.written_raw_data(site, composed, check)


def _legacy() -> dict:
    return {DP.PROVENANCE_KEY: M.LegacyProvenance(desc_sha256=M.text_sha256(MARCH)).to_dict()}


def test_a_checked_march_text_keeps_the_existing_ai_footnote_and_claims_no_licence():
    description, raw = _checked(_legacy(), keep=True)
    assert description == (
        "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]."
    )
    disclosure = DP.description_disclosure(DP.provenance_of(raw), description)
    assert disclosure == {
        "ai": "generated",
        "lane": "L",
        "aiSystem": M.LEGACY_AI_SYSTEM,
        "licence": None,
        "attribution": None,
    }
    assert DP.card_ai(DP.provenance_of(raw), None, "An old card.") is None


def test_the_site_api_serves_the_checked_text_with_its_new_citations_and_the_footnote():
    description, raw = _checked(_legacy(), keep=True)
    row = SimpleNamespace(
        id=SITE_ID, source_id="ancient_nerds", source_record_id="an-1", name="Tarxien Temples",
        lat=35.8692, lon=14.5122, site_type="Temple complex", period_start=-3150, period_end=None,
        period_name="3000 BC", country="Malta", description=description, thumbnail_url=None,
        source_url=None, raw_data=raw, scope_status=None, card_description=None,
        best_wiki_url=None, source_language=None,
    )  # fmt: skip
    resp = sr.get_site_detail(SITE_ID, db=RecordingSession({"WHERE us.id::text = :site_id": [row]}))
    assert resp["descriptionAi"] == "generated" and resp["descriptionAttribution"] is None
    assert resp["descriptionCitations"] == [
        {"n": 1, "url": WIKI, "title": "Tarxien Temples - Wikipedia", "domain": "en.wikipedia.org"}
    ]


def test_an_unclaimed_old_text_checked_by_the_lane_still_claims_nothing():
    """HUMAN_ONLY D7: the stored text is the pre-March one, so nothing proves its origin."""
    description, raw = _checked(None, keep=True, snapshot=MARCH)
    assert DP.provenance_of(raw) is None
    assert DP.description_disclosure(DP.provenance_of(raw), description) is None


def test_a_march_text_lane_l_never_marked_is_served_with_the_footnote_once_checked():
    """No marking stored (a P4 write a revert took back), but the text is not the pre-March one:
    the checked text carries lane L's marking, and every reader shows the AI footnote."""
    description, raw = _checked(None, keep=True)
    disclosure = DP.description_disclosure(DP.provenance_of(raw), description)
    assert disclosure is not None and (disclosure["ai"], disclosure["lane"]) == ("generated", "L")


def test_a_cleared_site_is_served_without_a_description_and_without_a_disclosure():
    description, raw = _checked(_legacy(), keep=False)
    assert (description, raw) == (None, None)
    row = SimpleNamespace(
        id=SITE_ID, source_id="ancient_nerds", source_record_id="an-1", name="Tarxien Temples",
        lat=35.8692, lon=14.5122, site_type="Temple complex", period_start=-3150, period_end=None,
        period_name="3000 BC", country="Malta", description=None, thumbnail_url=None,
        source_url=None, raw_data=None, scope_status=None, card_description=None,
        best_wiki_url=None, source_language=None,
    )  # fmt: skip
    resp = sr.get_site_detail(SITE_ID, db=RecordingSession({"WHERE us.id::text = :site_id": [row]}))
    assert resp["description"] is None
    assert "descriptionAi" not in resp and "descriptionCitations" not in resp
