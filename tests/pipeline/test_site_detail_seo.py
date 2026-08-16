# SPDX-License-Identifier: AGPL-3.0-only
"""
Slug and path contract for the crawlable site pages (/sites/{country}/{slug}).

Regression cover for the 2026-08-07 finding: all ~5,000 site URLs were
parameter-based (/site.html?id={uuid}) and Google never fetched a single
one of them. The page markup itself renders through React since the
react-ssr cutover — its assertions live in src/seo/__tests__/render.test.tsx
and meta.test.ts (Task 16). What stays Python, and what this file pins, is
the URL contract: slugs, paths and percent-encoding in
pipeline/sites_html_renderer.py, which routes and sitemap build on.
"""

import pytest

from pipeline.sites_html_renderer import (
    country_path,
    encode_path,
    site_id_prefix_from_slug,
    site_path,
    site_slug,
)

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
