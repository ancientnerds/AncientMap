# SPDX-License-Identifier: AGPL-3.0-only
"""Country-listing extras added 2026-08-09.

/sites/{country} selected site_type, period_name and the local hero webp
and then rendered none of them, so 218 Türkiye sites read as one
undifferentiated wall of name + blurb. These tests pin the grouping, the
hero, and the facts the head now derives from the real rows.
"""

from __future__ import annotations

import json

from pipeline import seo_pages


def _site(name: str, **over) -> dict:
    base = {
        "name": name,
        "path": f"/sites/turkiye/{name.lower()}-abc12345",
        "description": f"{name} is a place worth visiting.",
        "site_type": "Temple complex",
        "period_name": "500 BC - 1 AD",
        "period_start": -500,
        "thumbnail_url": "/data/images/wiki/abc12345/hero.webp",
    }
    base.update(over)
    return base


class TestTypeSections:
    def test_groups_by_type_largest_first(self):
        sections = seo_pages.type_sections(
            [
                _site("A", site_type="Theatre"),
                _site("B", site_type="Barrow"),
                _site("C", site_type="Barrow"),
            ]
        )
        assert [label for label, _ in sections] == ["Barrow", "Theatre"]
        assert [s["name"] for s in sections[0][1]] == ["B", "C"]

    def test_long_tail_merges_into_one_section(self):
        """England carries 30+ types; a section each would bury the list."""
        sites = [
            _site(f"S{i}", site_type=f"Type{i:02d}") for i in range(seo_pages.MAX_TYPE_SECTIONS + 5)
        ]
        sections = seo_pages.type_sections(sites)
        assert len(sections) == seo_pages.MAX_TYPE_SECTIONS + 1
        assert sections[-1][0] == seo_pages.OTHER_TYPES_LABEL
        assert len(sections[-1][1]) == 5

    def test_every_site_lands_in_exactly_one_section(self):
        sites = [_site(f"S{i}", site_type=f"Type{i % 20:02d}") for i in range(60)]
        placed = [s["name"] for _, group in seo_pages.type_sections(sites) for s in group]
        assert sorted(placed) == sorted(s["name"] for s in sites)

    def test_typeless_sites_go_to_other(self):
        sections = seo_pages.type_sections([_site("A", site_type=None)])
        assert sections == [(seo_pages.OTHER_TYPES_LABEL, [_site("A", site_type=None)])]


class TestCountryPageBody:
    def test_cards_carry_hero_type_and_period(self):
        body = seo_pages.country_sites_page("Türkiye", [_site("Nemrut")]).body
        assert '<img class="an-thumb" src="/data/images/wiki/abc12345/hero.webp"' in body
        assert 'loading="lazy"' in body  # 1053 England cards must not all fetch
        assert "Temple complex · 500 BC - 1 AD" in body

    def test_site_without_a_hero_renders_no_img(self):
        body = seo_pages.country_sites_page("Türkiye", [_site("Nemrut", thumbnail_url=None)]).body
        assert "an-thumb" not in body
        assert "Nemrut" in body

    def test_sections_get_anchors_and_a_chip_nav(self):
        body = seo_pages.country_sites_page(
            "Türkiye", [_site("A"), _site("B", site_type="Theatre")]
        ).body
        assert '<h2 id="temple-complex">Temple complex in Türkiye (1)</h2>' in body
        assert '<a class="an-chip" href="#theatre">' in body

    def test_single_section_gets_no_chip_nav(self):
        body = seo_pages.country_sites_page("Türkiye", [_site("A"), _site("B")]).body
        assert "an-chip" not in body

    def test_empty_country_renders(self):
        page = seo_pages.country_sites_page("Malta", [])
        assert "Archaeological Sites in Malta" in page.body
        assert "an-chip" not in page.body


class TestCountryPageHead:
    def test_description_names_the_real_types_and_span(self):
        head = seo_pages.country_sites_page(
            "Türkiye",
            [
                _site("A", site_type="Megalithic stones", period_start=-9000),
                _site("B", site_type="Megalithic stones", period_start=-500),
                _site("C", site_type="Theatre", period_start=1964),
            ],
        ).head
        assert "megalithic stones, theatre and more" in head
        assert "Spanning 9000 BC – 1964 AD" in head

    def test_span_collapses_when_all_sites_share_a_year(self):
        head = seo_pages.country_sites_page("Türkiye", [_site("A"), _site("B")]).head
        assert "Spanning 500 BC." in head

    def test_undated_sites_leave_the_span_out(self):
        head = seo_pages.country_sites_page(
            "Türkiye", [_site("A", period_start=None, period_name=None)]
        ).head
        assert "Spanning" not in head

    def test_og_image_uses_a_real_hero(self):
        head = seo_pages.country_sites_page(
            "Türkiye", [_site("A", thumbnail_url=None), _site("B")]
        ).head
        assert (
            'og:image" content="https://ancientnerds.com/data/images/wiki/abc12345/hero.webp"'
            in head
        )

    def test_og_image_falls_back_when_no_site_has_a_hero(self):
        head = seo_pages.country_sites_page("Türkiye", [_site("A", thumbnail_url=None)]).head
        assert "/landing/og-image.png" in head

    def test_schema_follows_the_rendered_order(self):
        head = seo_pages.country_sites_page(
            "Türkiye",
            [_site("Solo", site_type="Theatre"), _site("X"), _site("Y")],
        ).head
        # Temple complex (2) outranks Theatre (1), so X must come first.
        assert head.index('"position": 1, "name": "X"') < head.index('"name": "Solo"')


class TestRoutePayload:
    def test_interactive_view_gets_the_same_sections(self):
        """Lesson from the story pages: the React view must not be the poorer one."""
        page = seo_pages.country_sites_page(
            "Türkiye", [_site("A"), _site("B", site_type="Theatre")]
        )
        route = json.loads(page.route)
        assert route["type"] == "country"
        assert route["total"] == 2
        assert [s["label"] for s in route["sections"]] == ["Temple complex", "Theatre"]
        first = route["sections"][0]["sites"][0]
        assert first["siteType"] == "Temple complex"
        assert first["period"] == "500 BC - 1 AD"
        assert first["thumb"] == "/data/images/wiki/abc12345/hero.webp"
        assert route["sections"][0]["anchor"] == "temple-complex"

    def test_headline_breaking_names_cannot_escape_the_script_tag(self):
        route = seo_pages.country_sites_page("Türkiye", [_site("</script><b>x")]).route
        assert "</script>" not in route
        json.loads(route)

    def test_payload_blurb_is_cut_exactly_like_the_rendered_card(self):
        """The payload used a hard text[:200] slice, so the hydrated cards read
        "the city measured ap" while the crawler fragment ended cleanly."""
        long_desc = "Alexandria Troas was founded in 306 BC by Antigonus. " * 8
        page = seo_pages.country_sites_page("Türkiye", [_site("A", description=long_desc)])
        summary = json.loads(page.route)["sections"][0]["sites"][0]["summary"]
        assert summary.endswith("…")
        assert not summary.removesuffix("…").endswith(" ")
        assert f"<p>{summary}</p>" in page.body


class TestBlurb:
    def test_short_text_is_returned_whole(self):
        assert seo_pages.blurb("Short enough.") == "Short enough."

    def test_whitespace_is_collapsed(self):
        assert seo_pages.blurb("a\n\n  b") == "a b"

    def test_cut_lands_on_a_word_boundary(self):
        assert seo_pages.blurb("alpha beta gamma", limit=12) == "alpha beta…"

    def test_missing_text_is_empty(self):
        assert seo_pages.blurb(None) == ""
