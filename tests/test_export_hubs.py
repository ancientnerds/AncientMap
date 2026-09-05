"""scripts/export_hubs.py — the DB snapshot behind the homepage hub lists.

Pure-function tests: build_hubs_payload() turns country/paper rows into the
JSON the Vite build injects into index.html. Slugs must come from the same
helper the sitemap and the SSR pages use, papers must fall back to their
question when Theo stored no title, and the ordering is what the page shows.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "export_hubs", Path(__file__).resolve().parent.parent / "scripts" / "export_hubs.py"
)
export_hubs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(export_hubs)


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
        _row(
            slug="hard-stone",
            title="The Egyptian Hard-Stone Precision Debate",
            question="q1",
            published_at=None,
        ),
        _row(slug="untitled", title=None, question="What did Theo not name?", published_at=None),
    ]
    return export_hubs.build_hubs_payload(countries, papers)


def test_country_paths_use_the_shared_slug_helper(payload):
    from pipeline.sites_html_renderer import country_path

    by_name = {c["country"]: c for c in payload["countries"]}
    assert by_name["Türkiye"]["path"] == country_path("Türkiye") == "/sites/türkiye"
    assert by_name["Bosnia and Herzegovina"]["path"] == "/sites/bosnia-and-herzegovina"
    assert by_name["England"]["sites"] == 1053


def test_countries_keep_alphabetical_order_and_counts(payload):
    assert [c["country"] for c in payload["countries"]] == [
        "Bosnia and Herzegovina",
        "England",
        "Türkiye",
    ]


def test_papers_fall_back_to_the_question_as_title(payload):
    papers = {p["slug"]: p for p in payload["papers"]}
    assert papers["hard-stone"]["path"] == "/research/hard-stone"
    assert papers["hard-stone"]["title"] == "The Egyptian Hard-Stone Precision Debate"
    assert papers["untitled"]["title"] == "What did Theo not name?"


def test_payload_records_when_the_snapshot_was_taken(payload):
    assert payload["exported_at"].endswith("Z") or "+" in payload["exported_at"]
