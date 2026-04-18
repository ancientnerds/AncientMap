"""Tests for image diversity scoring."""

from __future__ import annotations

from pipeline.lyra.image_diversity import (
    compute_diversity,
    score_license_diversity,
    score_source_diversity,
)


def _emb(source: str = "wikimedia", license: str = "CC BY-SA 4.0") -> dict:
    return {"source": source, "license": license}


def test_source_diversity_empty():
    assert score_source_diversity([]) == 0.0


def test_source_diversity_all_unique():
    cases = [_emb("wikimedia"), _emb("met_museum"), _emb("loc")]
    assert score_source_diversity(cases) == 1.0


def test_source_diversity_partial():
    cases = [_emb("wikimedia"), _emb("wikimedia"), _emb("met_museum"), _emb("loc")]
    # 3 distinct / 4 total = 0.75
    assert score_source_diversity(cases) == 0.75


def test_source_diversity_all_same():
    cases = [_emb("wikimedia")] * 4
    assert score_source_diversity(cases) == 0.25


def test_license_diversity():
    cases = [
        _emb(license="CC0"),
        _emb(license="CC BY-SA 4.0"),
        _emb(license="Public Domain"),
    ]
    assert score_license_diversity(cases) == 1.0


def test_compute_diversity_returns_all_fields():
    cases = [
        _emb("wikimedia", "CC0"),
        _emb("met_museum", "CC0"),
        _emb("loc", "Public Domain"),
    ]
    d = compute_diversity(cases)
    assert d["total_embedded"] == 3
    assert d["source_count"] == 3
    assert d["license_count"] == 2
    assert d["source_diversity"] == 1.0
    assert d["license_diversity"] == round(2 / 3, 3)
    assert "wikimedia" in d["sources"]
    assert "met_museum" in d["sources"]
    assert "loc" in d["sources"]


def test_compute_diversity_empty():
    d = compute_diversity([])
    assert d["total_embedded"] == 0
    assert d["source_diversity"] == 0.0


def test_ignores_empty_source_values():
    cases = [_emb("wikimedia"), {"source": "", "license": "x"}, _emb("met_museum")]
    # Empty source is filtered — 2 sources / 2 usable = 1.0
    assert score_source_diversity(cases) == 1.0
