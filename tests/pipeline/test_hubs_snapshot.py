"""pipeline.static_exporter.build_hubs_payload — the homepage hub lists.

Pure-function tests for the payload the Vite build bakes into index.html.
Slugs must come from the same helper the sitemap and the SSR pages use,
papers must fall back to their question when Theo stored no title, and the
ordering is what the page shows.
"""

from types import SimpleNamespace

import pytest

from pipeline.sites_html_renderer import country_path
from pipeline.static_exporter import build_hubs_payload


def _row(**kw):
    return SimpleNamespace(**kw)


@pytest.fixture
def payload():
    countries = [
        _row(country="Türkiye", sites=218),
        _row(country="England", sites=1053),
        _row(country="Bosnia and Herzegovina", sites=12),
    ]
    papers = [
        _row(slug="hard-stone", title="The Egyptian Hard-Stone Precision Debate", question="q1"),
        _row(slug="untitled", title=None, question="What did Theo not name?"),
    ]
    return build_hubs_payload(countries, papers)


def test_country_paths_use_the_shared_slug_helper(payload):
    by_name = {c["country"]: c for c in payload["countries"]}
    assert by_name["Türkiye"]["path"] == country_path("Türkiye") == "/sites/türkiye"
    assert by_name["Bosnia and Herzegovina"]["path"] == "/sites/bosnia-and-herzegovina"
    assert by_name["England"]["sites"] == 1053


def test_countries_are_alphabetical(payload):
    assert [c["country"] for c in payload["countries"]] == [
        "Bosnia and Herzegovina",
        "England",
        "Türkiye",
    ]


def test_papers_keep_order_and_fall_back_to_the_question(payload):
    assert [p["slug"] for p in payload["papers"]] == ["hard-stone", "untitled"]
    assert payload["papers"][0]["path"] == "/research/hard-stone"
    assert payload["papers"][1]["title"] == "What did Theo not name?"


def test_payload_records_when_the_snapshot_was_taken(payload):
    assert payload["exported_at"].endswith("Z")
