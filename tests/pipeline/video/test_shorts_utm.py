# SPDX-License-Identifier: AGPL-3.0-only
"""Links in a Short's description and pinned comment carry UTM tags: YouTube
strips the referer on app clicks, so this is the only way Umami's UTM report
can attribute the visits — and utm_content tells the two links apart."""

from __future__ import annotations

from pipeline.video.shorts_render import build_comment, build_description, site_link

SITE = {
    "name": "Machu Picchu",
    "country": "Peru",
    "card_text": "A citadel.",
    "card_ai": None,
    "rarity_name": "Legendary",
    "rarity_tier": 5,
    "total_power": 33,
    "page_path": "/sites/peru/machu-picchu-abcd1234",
}


def test_site_link_is_absolute_and_tagged():
    assert site_link(SITE, "comment") == (
        "https://ancientnerds.com/sites/peru/machu-picchu-abcd1234"
        "?utm_source=youtube&utm_medium=short&utm_content=comment"
    )


def test_comment_and_description_use_distinct_placements():
    assert "utm_content=comment" in build_comment(SITE)
    description = build_description(SITE, [], voice_id="v")
    assert "utm_source=youtube&utm_medium=short&utm_content=description" in description
