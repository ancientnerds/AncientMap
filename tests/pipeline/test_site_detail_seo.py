# SPDX-License-Identifier: AGPL-3.0-only
"""
Crawlable site detail pages (/sites/{country}/{slug}).

Regression cover for the 2026-08-07 finding: all ~5,000 site URLs were
parameter-based (/site.html?id={uuid}) and served one identical SPA shell
to normal user agents, with unique content revealed only to crawler user
agents. Google never fetched a single one of them. These tests assert the
replacement pages are unique, self-describing and correctly linked.
"""

import json
import re

import pytest

from pipeline.sites_html_renderer import (
    country_path,
    encode_path,
    render_site_detail_html,
    site_id_prefix_from_slug,
    site_path,
    site_slug,
)

SITE_A = {
    "id": "383a0107-b7f7-4431-a752-590f3c0a42b2",
    "name": "Aartswoud",
    "country": "Netherlands",
    "site_type": "City/town/settlement",
    "period_name": "3000 - 2500 BC",
    "period_start": -3000,
    "period_end": -2500,
    "description": "A Neolithic settlement.\nExcavations revealed post holes and hearths.",
    "lat": 52.7,
    "lon": 4.98,
    "source_url": "https://example.org/ref",
}

SITE_B = {
    "id": "74fe5dc2-1e2c-4dd6-b4ed-3cb376c9cd50",
    "name": "Burrough Hill",
    "country": "England",
    "site_type": "Fortress/citadel",
    "period_name": "1500 - 500 BC",
    "period_start": -1500,
    "period_end": -500,
    "description": "An Iron Age hillfort on an escarpment.",
    "lat": 52.73,
    "lon": -0.86,
    "source_url": None,
}

EMPTY_RELATED: dict = {
    "alt_names": [],
    "image": None,
    "news": [],
    "links": [],
    "parent": None,
    "siblings": [],
}

FULL_RELATED = {
    "alt_names": ["Aartswoud-Zuid", "Aartswoud"],
    "image": {
        "url": "/data/images/wiki/383a0107/hero.webp",
        "author": "J. Doe",
        "license": "CC BY-SA 4.0",
        "commons_url": "https://commons.wikimedia.org/wiki/File:X.jpg",
    },
    "news": [{"slug": "new-find-123", "headline": "New find at Aartswoud"}],
    "links": [
        {"title": "ToposText entry", "url": "https://topostext.org/x", "content_type": "text"}
    ],
    "parent": {"name": "Parent Complex", "slug": "parent-complex-aabbccdd"},
    "siblings": [{"name": "Opperdoes", "slug": "opperdoes-99887766"}],
}


def _tag(html: str, pattern: str) -> str:
    match = re.search(pattern, html, re.DOTALL)
    assert match, f"pattern not found: {pattern}"
    return match.group(1)


# --- Slugs -----------------------------------------------------------------


def test_slug_combines_name_and_id_prefix():
    assert site_slug("Aartswoud", "383a0107-b7f7-4431-a752-590f3c0a42b2") == "aartswoud-383a0107"


def test_slug_is_unique_for_duplicate_names():
    """16 curated sites share a name with another site — the suffix separates them."""
    a = site_slug("Tell Brak", "383a0107-b7f7-4431-a752-590f3c0a42b2")
    b = site_slug("Tell Brak", "74fe5dc2-1e2c-4dd6-b4ed-3cb376c9cd50")
    assert a != b


def test_slug_survives_a_name_that_slugifies_to_nothing():
    """A name of pure punctuation must not produce a leading-dash slug."""
    slug = site_slug("!!!", "383a0107-b7f7-4431-a752-590f3c0a42b2")
    assert slug == "383a0107"
    assert site_id_prefix_from_slug(slug) == "383a0107"


@pytest.mark.parametrize(
    "name",
    ["Aartswoud", "Tell Brak", "Çatalhöyük", "St. Mary's Abbey", "A-B-C"],
)
def test_slug_round_trips_to_the_id_prefix(name):
    slug = site_slug(name, "383a0107-b7f7-4431-a752-590f3c0a42b2")
    assert site_id_prefix_from_slug(slug) == "383a0107"


@pytest.mark.parametrize("bad", ["", "aartswoud", "aartswoud-zzzzzzzz", "aartswoud-383a010"])
def test_malformed_slugs_are_rejected(bad):
    assert site_id_prefix_from_slug(bad) is None


def test_slug_lookup_is_case_insensitive_on_the_suffix():
    assert site_id_prefix_from_slug("aartswoud-383A0107") == "383a0107"


# --- URL encoding ----------------------------------------------------------


def test_paths_are_unencoded_and_readable():
    """site_path/country_path return raw paths — encode_path does the escaping."""
    assert (
        site_path("Netherlands", "Aartswoud", "383a0107-b7f7-4431-a752-590f3c0a42b2")
        == "/sites/netherlands/aartswoud-383a0107"
    )
    assert country_path("Netherlands") == "/sites/netherlands"
    assert site_path("Türkiye", "Ayşepınar", "3ff78ce4-1111-2222-3333-4444") == (
        "/sites/türkiye/ayşepınar-3ff78ce4"
    )


def test_encode_path_percent_encodes_non_ascii():
    """478 site names, one country and ~100 news slugs carry non-ASCII."""
    encoded = encode_path(site_path("Türkiye", "Ayşepınar", "3ff78ce4-1111-2222-3333-4444"))
    assert encoded == "/sites/t%C3%BCrkiye/ay%C5%9Fep%C4%B1nar-3ff78ce4"
    assert encoded.isascii()
    assert encode_path("/news-archive/vráble-7637") == "/news-archive/vr%C3%A1ble-7637"


def test_encode_path_leaves_ascii_and_slashes_alone():
    assert encode_path("/sites/netherlands/aartswoud-383a0107") == (
        "/sites/netherlands/aartswoud-383a0107"
    )


def test_encoding_is_not_applied_twice():
    """Double-encoding would turn every '%' into '%25' and 404 the page."""
    once = encode_path(site_path("Türkiye", "Ayşepınar", "3ff78ce4-1111-2222-3333-4444"))
    assert "%25" not in once


def test_encoded_path_decodes_back_to_the_slug_the_route_matches_on():
    """Starlette hands the route a decoded path param — it must equal the slug."""
    from urllib.parse import unquote

    name, country = "Ayşepınar", "Türkiye"
    site_id = "3ff78ce4-1111-2222-3333-4444"
    encoded = encode_path(site_path(country, name, site_id))
    _, _, country_part, slug_part = encoded.split("/")
    assert unquote(slug_part) == site_slug(name, site_id)
    assert unquote(country_part) == "türkiye"
    assert site_id_prefix_from_slug(unquote(slug_part)) == "3ff78ce4"


# --- Page uniqueness (the actual regression) -------------------------------


def test_pages_are_unique_per_site():
    """The old shell gave every site the same title, h1 and description."""
    a = render_site_detail_html(SITE_A, EMPTY_RELATED)
    b = render_site_detail_html(SITE_B, EMPTY_RELATED)

    for pattern in (
        r"<title>(.*?)</title>",
        r"<h1>(.*?)</h1>",
        r'name="description" content="(.*?)"',
        r'rel="canonical" href="(.*?)"',
    ):
        assert _tag(a, pattern) != _tag(b, pattern), f"identical across sites: {pattern}"


def test_title_and_heading_carry_the_site_name():
    html = render_site_detail_html(SITE_A, EMPTY_RELATED)
    assert "Aartswoud" in _tag(html, r"<title>(.*?)</title>")
    assert "Netherlands" in _tag(html, r"<title>(.*?)</title>")
    assert _tag(html, r"<h1>(.*?)</h1>") == "Aartswoud"


def test_canonical_is_the_slug_url_not_the_parameter_url():
    html = render_site_detail_html(SITE_A, EMPTY_RELATED)
    canonical = _tag(html, r'rel="canonical" href="(.*?)"')
    assert canonical == "https://ancientnerds.com/sites/netherlands/aartswoud-383a0107"
    assert "site.html?id=" not in canonical


def test_meta_description_is_single_line_and_bounded():
    """A raw newline in the content attribute garbles the search snippet."""
    html = render_site_detail_html(SITE_A, EMPTY_RELATED)
    desc = _tag(html, r'name="description" content="(.*?)"')
    assert "\n" not in desc
    assert len(desc) <= 161
    assert desc.startswith("A Neolithic settlement.")


def test_description_body_is_rendered_in_full():
    """The meta description is truncated; the page body must not be."""
    html = render_site_detail_html(SITE_A, EMPTY_RELATED)
    assert "Excavations revealed post holes and hearths." in html


def test_site_without_country_fails_loudly():
    orphan = dict(SITE_A, country=None)
    with pytest.raises(ValueError, match="no country"):
        render_site_detail_html(orphan, EMPTY_RELATED)


# --- Structured data and escaping ------------------------------------------


def test_jsonld_is_valid_and_describes_a_place_with_breadcrumbs():
    html = render_site_detail_html(SITE_A, EMPTY_RELATED)
    block = _tag(html, r'<script type="application/ld\+json">(.*?)</script>')
    nodes = json.loads(block)

    types = {n["@type"] for n in nodes}
    assert types == {"Place", "BreadcrumbList"}

    place = next(n for n in nodes if n["@type"] == "Place")
    assert place["name"] == "Aartswoud"
    assert place["geo"]["latitude"] == 52.7
    assert place["address"]["addressCountry"] == "Netherlands"

    crumbs = next(n for n in nodes if n["@type"] == "BreadcrumbList")
    names = [c["name"] for c in crumbs["itemListElement"]]
    assert names == ["Home", "Sites", "Netherlands", "Aartswoud"]


def test_hostile_content_cannot_break_out_of_the_page_or_the_jsonld():
    hostile = dict(
        SITE_A,
        name="</script><script>alert(1)</script>",
        description='Quote " and <b>tag</b> & ampersand',
    )
    html = render_site_detail_html(hostile, EMPTY_RELATED)

    assert "<script>alert(1)</script>" not in html
    assert "<b>tag</b>" not in html
    # JSON-LD must still parse — an unescaped "</script>" would truncate it.
    json.loads(_tag(html, r'<script type="application/ld\+json">(.*?)</script>'))


# --- Internal linking ------------------------------------------------------


def test_related_content_becomes_internal_and_external_links():
    html = render_site_detail_html(SITE_A, FULL_RELATED)

    assert "/news-archive/new-find-123" in html
    assert "/sites/netherlands/opperdoes-99887766" in html
    assert "/sites/netherlands/parent-complex-aabbccdd" in html
    assert '/sites/netherlands"' in html
    assert "https://topostext.org/x" in html
    assert "Aartswoud-Zuid" in html


def test_hero_image_carries_its_attribution():
    html = render_site_detail_html(SITE_A, FULL_RELATED)
    assert "/data/images/wiki/383a0107/hero.webp" in html
    assert "J. Doe" in html
    assert "CC BY-SA 4.0" in html
    assert "commons.wikimedia.org" in html


def test_page_still_renders_without_any_related_content():
    html = render_site_detail_html(SITE_B, EMPTY_RELATED)
    assert "<h1>Burrough Hill</h1>" in html
    assert "Related resources" not in html
    assert "Archaeology news about" not in html


def test_page_links_to_the_interactive_globe():
    """The SPA view stays reachable — it is just no longer the canonical URL."""
    html = render_site_detail_html(SITE_A, EMPTY_RELATED)
    assert f"/site.html?id={SITE_A['id']}" in html
