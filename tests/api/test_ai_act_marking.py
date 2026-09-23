# SPDX-License-Identifier: AGPL-3.0-only
"""Art. 50 EU AI Act: machine-readable AI marking on content and site-description API schemas.

The content schemas (stories, journals, research) are AI-generated as a whole and say so by
default. A site description is marked by its own provenance (2026-09 remediation, design entry [6],
licensing_and_ai_act): `raw_data._description_provenance.ai` is the render key - 'selected' for
verbatim Wikipedia sentences an AI only chose and shortened (lanes W, S), 'generated' for text an
AI wrote (lanes T, R and the legacy lane L). The CC BY-SA 4.0 attribution is surfaced for the lanes
whose text adapts a Wikipedia article (W, S, T). One derivation serves /api/sites/{id}, the SSR
payload and the public v1 API, and it claims nothing for a text other than the one the provenance
hashes. Mutation cases: "p4 api" in `scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import copy
import hashlib
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.routes import sites as sr
from api.routes.news import NewsArticleResponse, NewsItemResponse
from api.schemas.public_v1 import (
    ArticleSummary,
    NewsItemPublic,
    ResearchPaperSummary,
    SiteDetailResponse,
)
from api.services import description_provenance as DP
from tests.fake_sql import RecordingSession


@pytest.mark.parametrize(
    ("schema", "expected_system"),
    [
        (NewsItemPublic, "lyra-news"),
        (NewsItemResponse, "lyra-news"),
        (ArticleSummary, "lyra-journal"),
        (NewsArticleResponse, "lyra-journal"),
        (ResearchPaperSummary, "theo-research"),
    ],
)
def test_content_schemas_carry_ai_marking(schema, expected_system):
    assert schema.model_fields["ai_generated"].default is True
    assert schema.model_fields["ai_system"].default == expected_system


# ── the site description's provenance ───────────────────────────────────────────────────────────

SITE_ID = "4a5a324f-0000-4000-8000-000000000001"
DESCRIPTION = "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]."
CARD = "The Tarxien Temples are an archaeological complex in Malta's south."
PERMALINK = "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=1234567"
AI_SYSTEM = "opencode-go/deepseek-v4.1-flash via Pi (an-sites-remediation-2026-09)"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
CHANGES = {"W": "sentences selected and shortened", "S": "sentences selected and shortened"}
CHANGES.update({"T": "translated", "R": "facts restated"})
AI = {"W": "selected", "S": "selected", "T": "generated", "R": "generated"}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _provenance(lane: str) -> dict[str, Any]:
    """The production_write shape; lane R cites a restricted page without a revision."""
    url = "https://example.org/hatunmarka" if lane == "R" else PERMALINK
    return {
        "v": 1,
        "run": "pilot-20260923",
        "lane": lane,
        "ai": AI[lane],
        "ai_system": AI_SYSTEM,
        "licence": "CC BY-SA 4.0",
        "attribution": {
            "title": "Tarxien Temples",
            "url": url,
            "licence_url": LICENCE_URL,
            "changes": CHANGES[lane],
        },
        "sources": [
            {
                "id": "R1" if lane == "R" else ("T.fr" if lane == "T" else "W"),
                "url": url,
                "revid": None if lane == "R" else 1234567,
                "rev_timestamp": None if lane == "R" else "2026-09-01T10:00:00Z",
                "text_sha256": "0" * 64,
                "licence": "restricted" if lane == "R" else "CC BY-SA 4.0",
            }
        ],
        "sentences": [{"n": 1, "src": "W", "start": 0, "end": 70, "drop": []}],
        "card": {"items": [{"sentence": 0, "drop": []}], "text_sha256": _sha(CARD)},
        "desc_sha256": _sha(DESCRIPTION),
    }


def _legacy() -> dict[str, Any]:
    return {
        "v": 1,
        "lane": "L",
        "ai": "generated",
        "ai_system": "2026-03 enrichment chain (LLM; model per site not recorded)",
        "basis": "description differs from pre-March snapshot d4526691 (plan section 15.3)",
        "desc_sha256": _sha(DESCRIPTION),
    }


@pytest.mark.parametrize("lane", ["W", "S"])
def test_selected_text_carries_the_attribution_line_and_no_ai_footnote_mark(lane):
    disclosure = DP.description_disclosure(_provenance(lane), DESCRIPTION)
    assert disclosure == {
        "ai": "selected",
        "lane": lane,
        "aiSystem": AI_SYSTEM,
        "licence": "CC BY-SA 4.0",
        "attribution": {
            "title": "Tarxien Temples",
            "url": PERMALINK,
            "licence": "CC BY-SA 4.0",
            "licenceUrl": LICENCE_URL,
            "changes": "sentences selected and shortened",
            "revisionDate": "2026-09-01",
        },
    }


def test_translated_text_is_generated_and_still_attributed():
    disclosure = DP.description_disclosure(_provenance("T"), DESCRIPTION)
    assert disclosure["ai"] == "generated"
    assert disclosure["attribution"]["changes"] == "translated"


def test_restated_text_is_generated_and_names_no_restricted_page():
    disclosure = DP.description_disclosure(_provenance("R"), DESCRIPTION)
    assert disclosure["ai"] == "generated" and disclosure["attribution"] is None


def test_legacy_text_is_generated_without_attribution_or_licence():
    disclosure = DP.description_disclosure(_legacy(), DESCRIPTION)
    assert disclosure == {
        "ai": "generated",
        "lane": "L",
        "aiSystem": "2026-03 enrichment chain (LLM; model per site not recorded)",
        "licence": None,
        "attribution": None,
    }


def test_no_provenance_no_disclosure():
    assert DP.description_disclosure(None, DESCRIPTION) is None
    assert DP.provenance_of({"description_citations": []}) is None
    assert DP.provenance_of(None) is None


@pytest.mark.parametrize("malformed", ['{"lane": "L", "ai": "generated"}', ["x"], 1])
def test_a_provenance_that_is_not_an_object_is_refused_not_ignored(malformed):
    """A present but malformed provenance (a double-encoded JSON string, a list) fails loudly on
    every reader, as `description_disclosure` does for an unknown mark - never a silent 'nothing to
    disclose' on one path and an exception on the other."""
    with pytest.raises(ValueError, match="is not a JSON object"):
        DP.provenance_of({DP.PROVENANCE_KEY: malformed})


def test_an_unknown_ai_mark_is_refused():
    provenance = {**_provenance("W"), "ai": "handwritten"}
    with pytest.raises(ValueError, match="not one of"):
        DP.description_disclosure(provenance, DESCRIPTION)


def test_an_attribution_that_names_no_single_cited_source_is_refused():
    provenance = copy.deepcopy(_provenance("W"))
    provenance["attribution"]["url"] = "https://en.wikipedia.org/w/index.php?oldid=1"
    with pytest.raises(ValueError, match="names no single cited source"):
        DP.description_disclosure(provenance, DESCRIPTION)
    twice = copy.deepcopy(_provenance("W"))
    twice["sources"] = twice["sources"] * 2
    with pytest.raises(ValueError, match="names no single cited source"):
        DP.description_disclosure(twice, DESCRIPTION)


def test_a_description_edited_after_its_provenance_discloses_nothing():
    """The provenance hashes one text; an admin edit or a stale export is another text."""
    assert DP.description_disclosure(_provenance("W"), DESCRIPTION + " Edited.") is None


def test_a_card_is_marked_only_while_it_is_the_card_the_provenance_hashes():
    assert DP.card_ai(_provenance("W"), CARD) == "selected"
    assert DP.card_ai(_provenance("W"), CARD + "!") is None
    assert DP.card_ai(_legacy(), CARD) is None
    no_card = copy.deepcopy(_provenance("W"))
    no_card["card"] = None
    assert DP.card_ai(no_card, CARD) is None


def test_the_provenance_key_is_the_writers_own():
    remediation = Path(__file__).resolve().parents[2] / "scripts" / "remediation"
    if str(remediation) not in sys.path:
        sys.path.insert(0, str(remediation))
    from phase4 import model4

    assert model4.PROVENANCE_KEY == DP.PROVENANCE_KEY
    assert {lane.value for lane in model4.LANE_CHANGES} - {"R"} == DP.ATTRIBUTION_LANES
    assert {mark.value for mark in model4.AiMark} == DP.AI_MARKS


def test_the_api_boot_writes_no_description_citations():
    """The 10-site citation seed in api/main.py was a boot writer of raw_data the plan's section
    10.1 missed; it is gone (all 10 sites carried the key, read-only check 2026-09-23), so no
    container start can write the column the Phase-4 journal owns."""
    source = (Path(__file__).resolve().parents[2] / "api" / "main.py").read_text(encoding="utf-8")
    assert "description_citations}" not in source
    assert not re.search(r"UPDATE unified_sites\s+SET raw_data", source)


# ── the three readers ────────────────────────────────────────────────────────────────────────────


def _detail_row(raw_data, *, description=DESCRIPTION, card=CARD):
    return SimpleNamespace(
        id=SITE_ID,
        source_id="ancient_nerds",
        source_record_id="an-1",
        name="Tarxien Temples",
        lat=35.8692,
        lon=14.5122,
        site_type="Temple",
        period_start=-3150,
        period_end=None,
        period_name="3000 BC",
        country="Malta",
        description=description,
        thumbnail_url=None,
        source_url=None,
        raw_data=raw_data,
        scope_status=None,
        card_description=card,
        best_wiki_url=None,
        source_language=None,
    )


def test_the_site_api_surfaces_description_ai_and_attribution():
    raw = {"description_citations": [], DP.PROVENANCE_KEY: _provenance("W")}
    db = RecordingSession({"WHERE us.id::text = :site_id": [_detail_row(raw)]})
    resp = sr.get_site_detail(SITE_ID, db=db)
    assert resp["descriptionAi"] == "selected"
    assert resp["descriptionAttribution"]["url"] == PERMALINK
    assert resp["cardAi"] == "selected"


def test_the_site_api_says_nothing_without_provenance():
    db = RecordingSession({"WHERE us.id::text = :site_id": [_detail_row({"x": 1})]})
    resp = sr.get_site_detail(SITE_ID, db=db)
    assert "descriptionAi" not in resp and "descriptionAttribution" not in resp
    assert "cardAi" not in resp


def test_the_public_site_detail_schema_carries_the_description_marking():
    fields = SiteDetailResponse.model_fields
    assert fields["ai_generated"].default is False
    for name in ("description_ai", "description_ai_system", "description_license"):
        assert fields[name].default is None


def _public_client(row):
    from api.routes import public_v1

    app = public_v1.create_public_api()
    db = RecordingSession({"WHERE id::text = :site_id": [row]})
    app.dependency_overrides[public_v1.get_db] = lambda: db
    app.dependency_overrides[public_v1.rate_limit_dependency] = lambda: None
    return TestClient(app), db, public_v1


@pytest.mark.parametrize(
    ("provenance", "expected"),
    [
        (_provenance("W"), (False, "selected", AI_SYSTEM, "CC BY-SA 4.0")),
        (_provenance("R"), (True, "generated", AI_SYSTEM, "CC BY-SA 4.0")),
        (_legacy(), (True, "generated", _legacy()["ai_system"], None)),
        (None, (False, None, None, None)),
    ],
)
def test_the_public_api_marks_the_description_by_its_provenance(provenance, expected):
    row = SimpleNamespace(
        id=SITE_ID,
        name="Tarxien Temples",
        lat=35.8692,
        lon=14.5122,
        source_id="ancient_nerds",
        site_type="Temple",
        period_start=-3150,
        period_end=None,
        period_name=None,
        country="Malta",
        description=DESCRIPTION,
        source_url=None,
        thumbnail_url=None,
        scope_status=None,
        description_provenance=provenance,
    )
    client, db, public_v1 = _public_client(row)
    with (
        patch.object(public_v1, "cache_get", return_value=None),
        patch.object(public_v1, "cache_set"),
    ):
        body = client.get(f"/sites/{SITE_ID}").json()
    got = (
        body["ai_generated"],
        body["description_ai"],
        body["description_ai_system"],
        body["description_license"],
    )
    assert got == expected
    assert "raw_data -> '_description_provenance' AS description_provenance" in db.statement_with(
        "WHERE id::text = :site_id"
    )
