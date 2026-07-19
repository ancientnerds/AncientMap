# SPDX-License-Identifier: AGPL-3.0-only
"""Auto-promote gate: score 100 + high AI confidence required."""

from unittest.mock import MagicMock, patch

from pipeline.database import UserContribution
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.site_identifier import _maybe_promote


def _contribution(score=100, confidence="high", lat=37.0, lon=38.0):
    c = UserContribution(name="Test Site", source="lyra")
    c.score = score
    c.lat = lat
    c.lon = lon
    c.enrichment_data = {"identification": {"confidence": confidence}}
    return c


def test_default_promotion_threshold_is_100():
    assert LyraSettings().min_score_for_promotion == 100


@patch("pipeline.lyra.site_identifier.passes_date_cutoff")
def test_below_threshold_returns_early(mock_cutoff):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(score=99), "Test Site", settings)
    mock_cutoff.assert_not_called()


@patch("pipeline.lyra.site_identifier.passes_date_cutoff")
def test_medium_confidence_returns_early(mock_cutoff):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(confidence="medium"), "Test Site", settings)
    mock_cutoff.assert_not_called()


@patch("pipeline.lyra.site_identifier.passes_date_cutoff")
def test_missing_confidence_returns_early(mock_cutoff):
    session = MagicMock()
    settings = LyraSettings()
    contribution = _contribution()
    contribution.enrichment_data = {}
    _maybe_promote(session, contribution, "Test Site", settings)
    mock_cutoff.assert_not_called()


@patch("pipeline.lyra.site_identifier.passes_date_cutoff", return_value=False)
def test_high_confidence_and_score_100_proceeds_to_cutoff(mock_cutoff):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(), "Test Site", settings)
    mock_cutoff.assert_called_once()
