"""Unit tests for the multi-source search module (theo_sources.py).

All tests exercise pure logic — no real HTTP calls are made.
"""

import pytest

from pipeline.lyra.config import LyraSettings
from pipeline.lyra.theo_sources import (
    BLOCKED_DOMAINS,
    SOURCE_GROUPS,
    MultiSourceSearch,
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
