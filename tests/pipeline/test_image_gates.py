"""Unit tests for the metadata and vision relevance gates."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.image_gates import (
    metadata_gate_passes,
    parse_vlm_verdict,
)


def _cand(title="", desc="", artist="", url="https://x/y.jpg", source="wikimedia"):
    return ImageCandidate(
        url=url,
        source=source,
        title=title,
        description=desc,
        artist=artist,
        license="CC BY-SA 4.0",
        license_url="",
        thumbnail_url=url,
        metadata={},
    )


def test_metadata_gate_accepts_matching_keywords():
    c = _cand(title="Nebra sky disc", desc="Bronze Age astronomical disc")
    must_show = "The Nebra Sky Disc itself, bronze with gold celestial inlays"
    assert metadata_gate_passes(c, must_show) is True


def test_metadata_gate_rejects_unrelated():
    c = _cand(title="Great Pyramid of Giza at sunset", desc="Tourist photo")
    must_show = "The Nebra Sky Disc itself, bronze with gold celestial inlays"
    assert metadata_gate_passes(c, must_show) is False


def test_metadata_gate_rejects_empty_metadata():
    c = _cand(title="", desc="")
    assert metadata_gate_passes(c, "Anything") is False


def test_parse_vlm_verdict_accepts_well_formed():
    raw = (
        '{"shows_required_subject":"yes","specific_features_present":["disc"],'
        '"forbidden_elements_present":[],"image_quality":"good",'
        '"verdict":"accept","reason":"clear match"}'
    )
    v = parse_vlm_verdict(raw)
    assert v is not None
    assert v["verdict"] == "accept"


def test_parse_vlm_verdict_rejects_on_forbidden_present():
    raw = (
        '{"shows_required_subject":"yes","specific_features_present":["disc"],'
        '"forbidden_elements_present":["tourist"],"image_quality":"good",'
        '"verdict":"accept","reason":"?"}'
    )
    # Gate logic overrides verdict when forbidden_elements_present non-empty
    from pipeline.lyra.image_gates import verdict_is_accept

    v = parse_vlm_verdict(raw)
    assert verdict_is_accept(v) is False  # forbidden elements present


def test_parse_vlm_verdict_handles_garbage():
    assert parse_vlm_verdict("not json") is None
    assert parse_vlm_verdict("") is None
