"""Unit tests for the image fetcher helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pipeline.lyra.image_fetcher import (
    ImageCandidate,
    deduplicate_candidates,
    select_top_per_connector,
)


def _make(url: str, source: str, title: str = "t") -> ImageCandidate:
    return ImageCandidate(
        url=url,
        source=source,
        title=title,
        description="",
        artist="",
        license="CC BY-SA 4.0",
        license_url="",
        thumbnail_url=url,
        metadata={},
    )


def test_deduplicate_candidates_by_url():
    cands = [
        _make("https://x/a.jpg", "wikimedia"),
        _make("https://x/a.jpg", "met_museum"),  # same URL, duplicate
        _make("https://x/b.jpg", "met_museum"),
    ]
    out = deduplicate_candidates(cands)
    assert len(out) == 2
    assert {c.url for c in out} == {"https://x/a.jpg", "https://x/b.jpg"}


def test_select_top_per_connector_caps_per_source():
    cands = [
        _make("https://x/1.jpg", "wikimedia"),
        _make("https://x/2.jpg", "wikimedia"),
        _make("https://x/3.jpg", "wikimedia"),  # over cap=2
        _make("https://y/1.jpg", "met_museum"),
    ]
    out = select_top_per_connector(cands, per_source=2)
    wiki = [c for c in out if c.source == "wikimedia"]
    assert len(wiki) == 2
    assert any(c.source == "met_museum" for c in out)
