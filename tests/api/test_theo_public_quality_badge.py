# SPDX-License-Identifier: AGPL-3.0-only
"""GET /api/theo/public/{slug} publishes no M3 quality score (owner decision D86).

The endpoint hands a paper's stored result_json to the paper overlay. The old M3
judge's score and tier ("Platinum", "Gold", "Unverified" with x/100) stay stored -
a journalled paper's result_json changes only through theo_publish - but leave
the endpoint only as the studio's "Claim-checked" badge, and only where the
studio claim check ran.
"""

from __future__ import annotations

from api.routes.theo import public_result


def test_an_m3_score_leaves_the_payload():
    result = {
        "report": "text",
        "quality_score": {"badge": "Platinum", "score": 98, "passed": True, "meta": {}},
    }
    assert "quality_score" not in public_result(result)


def test_a_claim_checked_paper_keeps_only_its_badge():
    result = {
        "report": "text",
        "quality_score": {"badge": "Claim-checked", "score": 96, "passed": True, "meta": {}},
    }
    assert public_result(result)["quality_score"] == {"badge": "Claim-checked"}


def test_the_reviewed_publication_replaces_the_draft():
    result = {
        "report": "draft",
        "published_report": "reviewed",
        "hero_image": {"src": "/a.jpg"},
        "published_hero_image": {"src": "/b.jpg"},
    }
    out = public_result(result)
    assert out["report"] == "reviewed"
    assert out["hero_image"] == {"src": "/b.jpg"}
    assert result["report"] == "draft"  # the stored dict is not mutated
