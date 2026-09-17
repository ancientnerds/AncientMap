# SPDX-License-Identifier: AGPL-3.0-only
"""Links the Discord bot posts: canonical where the slug is known, and always
tagged for Umami's UTM report — Discord apps open links without a referer,
so without the tag every one of these visits counts as "direct"."""

from __future__ import annotations

from api.services import discord_bot as bot


def test_site_link_is_canonical_and_tagged_when_name_and_country_are_known():
    url = bot.site_link("9c8b7a65-4321-4cba-8000-111122223333", "Göbekli Tepe", "Türkiye")
    assert url == (
        "https://ancientnerds.com/sites/t%C3%BCrkiye/g%C3%B6bekli-tepe-9c8b7a65"
        "?utm_source=discord&utm_medium=bot"
    )


def test_site_link_falls_back_to_the_id_url_with_the_tag():
    url = bot.site_link("9c8b7a65-4321-4cba-8000-111122223333")
    assert url == (
        "https://ancientnerds.com/site.html?id=9c8b7a65-4321-4cba-8000-111122223333"
        "&utm_source=discord&utm_medium=bot"
    )


def test_inline_site_markers_become_tagged_links_without_previews():
    text = bot._clean_for_discord("See [Giza](site:abc-123) and [x](flag:EG).")
    assert (
        text
        == "See [Giza](<https://ancientnerds.com/site.html?id=abc-123&utm_source=discord&utm_medium=bot>) and x."
    )


def test_sites_embed_uses_canonical_links():
    embed = bot._build_sites_embed(
        [
            {"id": "9c8b7a65-4321-4cba-8000-111122223333", "name": "Göbekli Tepe", "country": "Türkiye", "period_name": "Neolithic"},
            {"id": "", "name": "Nameless"},
        ]
    )
    assert "https://ancientnerds.com/sites/t%C3%BCrkiye/g%C3%B6bekli-tepe-9c8b7a65?utm_source=discord&utm_medium=bot" in embed.description
    assert "(Neolithic, Türkiye)" in embed.description
    assert "**Nameless**" in embed.description
