"""Unit tests for the multi-source search module (theo_sources.py).

All tests exercise pure logic — no real HTTP calls are made.
"""

import httpx
import pytest

from pipeline.lyra.config import LyraSettings
from pipeline.lyra.theo_sources import (
    BLOCKED_DOMAINS,
    SOURCE_GROUPS,
    MultiSourceSearch,
    NaraAdapter,
    RawSource,
    _is_blocked,
    _reconstruct_abstract,
)

# ---------------------------------------------------------------------------
# Blocked domain tests
# ---------------------------------------------------------------------------


def test_blocked_domains():
    """reddit.com, quora.com and facebook.com URLs are blocked."""
    assert _is_blocked("https://www.reddit.com/r/archaeology/comments/xyz")
    assert _is_blocked("https://quora.com/What-is-Gobekli-Tepe")
    assert _is_blocked("https://www.facebook.com/ancienthistory/posts/123")


def test_blocked_domain_subdomains():
    """Subdomains of blocked domains are also blocked."""
    assert _is_blocked("https://old.reddit.com/r/history")
    assert _is_blocked("https://m.facebook.com/page/123")


def test_allowed_domains():
    """Academic and reputable domains are NOT blocked."""
    assert not _is_blocked("https://www.academia.edu/123456/Some_Paper")
    assert not _is_blocked("https://www.researchgate.net/publication/123")
    assert not _is_blocked("https://www.jstor.org/stable/123456")


# ---------------------------------------------------------------------------
# RawSource defaults
# ---------------------------------------------------------------------------


def test_raw_source_defaults():
    """RawSource initialises optional fields to their documented defaults."""
    src = RawSource(url="https://example.com", title="Test Title", snippet="A snippet")
    assert src.doi == ""
    assert src.authors == []
    assert src.venue == ""
    assert src.date == ""
    assert src.citation_count == 0
    assert src.source_api == ""
    assert src.default_tier == 0


# ---------------------------------------------------------------------------
# SOURCE_GROUPS structure
# ---------------------------------------------------------------------------


def test_source_groups_defined():
    """SOURCE_GROUPS contains exactly the four expected keys."""
    assert "minimal" in SOURCE_GROUPS
    assert "standard" in SOURCE_GROUPS
    assert "full" in SOURCE_GROUPS
    assert "exhaustive" in SOURCE_GROUPS


def test_minimal_group_contents():
    """The 'minimal' group includes semantic_scholar and minimax."""
    assert "semantic_scholar" in SOURCE_GROUPS["minimal"]
    assert "minimax" in SOURCE_GROUPS["minimal"]


def test_exhaustive_group_has_all():
    """The 'exhaustive' group is the largest source group."""
    sizes = {name: len(adapters) for name, adapters in SOURCE_GROUPS.items()}
    assert sizes["exhaustive"] == max(sizes.values()), (
        f"exhaustive ({sizes['exhaustive']}) is not the largest group: {sizes}"
    )


# ---------------------------------------------------------------------------
# MultiSourceSearch initialisation
# ---------------------------------------------------------------------------


def test_multi_source_search_init():
    """MultiSourceSearch always registers semantic_scholar and wikipedia adapters."""
    settings = LyraSettings()
    searcher = MultiSourceSearch(settings)
    assert "semantic_scholar" in searcher._adapters
    assert "wikipedia" in searcher._adapters


# ---------------------------------------------------------------------------
# Abstract reconstruction helper
# ---------------------------------------------------------------------------


def test_openalex_abstract_reconstruction():
    """_reconstruct_abstract re-assembles words from an inverted index."""
    inverted = {
        "The": [0],
        "quick": [1],
        "brown": [2],
        "fox": [3],
    }
    result = _reconstruct_abstract(inverted)
    assert result == "The quick brown fox"


def test_openalex_abstract_reconstruction_empty():
    """_reconstruct_abstract returns empty string for an empty index."""
    assert _reconstruct_abstract({}) == ""


def test_openalex_abstract_reconstruction_repeated_word():
    """_reconstruct_abstract handles words that appear at multiple positions."""
    inverted = {
        "to": [0, 3],
        "be": [1, 4],
        "or": [2],
        "not": [5],
    }
    result = _reconstruct_abstract(inverted)
    assert result == "to be or to be not"


# ---------------------------------------------------------------------------
# NARA adapter (Catalog API v2 — declassified/archival primary sources)
# ---------------------------------------------------------------------------

_NARA_FIXTURE = {
    "body": {
        "hits": {
            "total": {"value": 2, "relation": "eq"},
            "hits": [
                {
                    "_id": "12345",
                    "_source": {
                        "record": {
                            "naId": 12345,
                            "title": "Memorandum on Project Stargate",
                            "scopeAndContentNote": "A" * 600,
                            "productionDates": [{"year": 1983, "logicalDate": "1983-05-01"}],
                            "levelOfDescription": "item",
                            "generalRecordsTypes": ["Textual Records"],
                        }
                    },
                },
                {
                    "_id": "67890",
                    "_source": {
                        "record": {
                            "naId": 67890,
                            "title": "Photographs of remote viewing test site",
                            "levelOfDescription": "fileUnit",
                            "generalRecordsTypes": ["Photographs and other Graphic Materials"],
                        }
                    },
                },
            ],
        }
    }
}


def _fake_nara_response(json_body: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://catalog.archives.gov/api/v2/records/search")
    return httpx.Response(status_code, json=json_body, request=request)


async def test_nara_adapter_parses_hits(monkeypatch):
    """NaraAdapter parses hits into RawSource: tier 1, NARA venue, /id/{naId} URL,
    scopeAndContentNote truncated to ~500 chars, first productionDates year as date.
    The second hit has neither scopeAndContentNote nor productionDates, exercising
    the levelOfDescription+generalRecordsTypes snippet fallback and empty date.
    """
    adapter = NaraAdapter("fake-key")
    monkeypatch.setattr(
        adapter._client, "request", lambda *a, **kw: _fake_nara_response(_NARA_FIXTURE)
    )

    results = await adapter.search("Stargate Project remote viewing", max_results=2)

    assert len(results) == 2

    first = results[0]
    assert first.url == "https://catalog.archives.gov/id/12345"
    assert first.title == "Memorandum on Project Stargate"
    assert first.snippet == "A" * 500
    assert first.date == "1983"
    assert first.venue == "U.S. National Archives"
    assert first.source_api == "nara"
    assert first.default_tier == 1

    second = results[1]
    assert second.url == "https://catalog.archives.gov/id/67890"
    assert second.title == "Photographs of remote viewing test site"
    assert second.snippet == "fileUnit, Photographs and other Graphic Materials"
    assert second.date == ""
    assert second.venue == "U.S. National Archives"
    assert second.default_tier == 1


async def test_nara_adapter_http_error_returns_empty(monkeypatch):
    """A failing HTTP call (e.g. bad key / 5xx) is swallowed — returns [], mirrors
    the try/except-around-_do pattern used by CORE/Europeana/Smithsonian.

    A persistent 500 makes _retry_request exhaust all 3 retries (real
    backoff: 1+2+4=7s) before giving up — monkeypatch time.sleep so this
    test doesn't actually burn 7 wall-clock seconds every run."""
    import pipeline.lyra.theo_sources as theo_sources_module

    monkeypatch.setattr(theo_sources_module.time, "sleep", lambda *_: None)

    adapter = NaraAdapter("fake-key")
    monkeypatch.setattr(
        adapter._client,
        "request",
        lambda *a, **kw: _fake_nara_response({}, status_code=500),
    )

    results = await adapter.search("Stargate Project", max_results=2)
    assert results == []


def test_nara_registered_with_key(monkeypatch):
    """NaraAdapter is registered in MultiSourceSearch._adapters when NARA_API_KEY is set."""
    monkeypatch.setenv("NARA_API_KEY", "fake-key")
    settings = LyraSettings()
    searcher = MultiSourceSearch(settings)
    assert "nara" in searcher._adapters
    assert isinstance(searcher._adapters["nara"], NaraAdapter)


def test_nara_absent_without_key(monkeypatch):
    """Without NARA_API_KEY set, the adapter is not registered at all."""
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    settings = LyraSettings()
    searcher = MultiSourceSearch(settings)
    assert "nara" not in searcher._adapters


def test_nara_in_full_exhaustive_not_minimal_not_standard():
    """nara is a source-group member of full/exhaustive only (2026-08-05 review:
    removed from 'standard' to keep the default group's ~240-calls/paper worst
    case off NARA's 10k/month quota — prod opts in explicitly via
    THEO_SOURCE_APIS=full)."""
    assert "nara" not in SOURCE_GROUPS["minimal"]
    assert "nara" not in SOURCE_GROUPS["standard"]
    assert "nara" in SOURCE_GROUPS["full"]
    assert "nara" in SOURCE_GROUPS["exhaustive"]


def test_nara_effective_selection_with_key(monkeypatch):
    """With the key set, nara is among the adapters actually selected for 'full'."""
    monkeypatch.setenv("NARA_API_KEY", "fake-key")
    settings = LyraSettings()
    searcher = MultiSourceSearch(settings)
    active_names = [n for n in SOURCE_GROUPS["full"] if n in searcher._adapters]
    assert "nara" in active_names


def test_nara_effective_selection_without_key(monkeypatch):
    """Without the key, nara is listed in the group but not actually selectable —
    MultiSourceSearch.search() filters wanted_names down to `name in self._adapters`."""
    monkeypatch.delenv("NARA_API_KEY", raising=False)
    settings = LyraSettings()
    searcher = MultiSourceSearch(settings)
    active_names = [n for n in SOURCE_GROUPS["full"] if n in searcher._adapters]
    assert "nara" not in active_names
