# SPDX-License-Identifier: AGPL-3.0-only
"""Auto-promote gate: score 100 + high AI confidence required, then the scope rule D58."""

from unittest.mock import MagicMock, patch

from pipeline.database import UserContribution
from pipeline.lyra.config import LyraSettings
from pipeline.lyra.site_identifier import _maybe_promote


def _contribution(score=100, confidence="high", lat=37.0, lon=38.0, **fields):
    c = UserContribution(name="Test Site", source="lyra")
    c.score = score
    c.lat = lat
    c.lon = lon
    for key, value in fields.items():
        setattr(c, key, value)
    c.enrichment_data = {"identification": {"confidence": confidence}}
    return c


def test_default_promotion_threshold_is_100():
    assert LyraSettings().min_score_for_promotion == 100


@patch("pipeline.lyra.site_identifier.label_scope")
def test_below_threshold_returns_early(mock_scope):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(score=99), "Test Site", settings)
    mock_scope.assert_not_called()


@patch("pipeline.lyra.site_identifier.label_scope")
def test_medium_confidence_returns_early(mock_scope):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(confidence="medium"), "Test Site", settings)
    mock_scope.assert_not_called()


@patch("pipeline.lyra.site_identifier.label_scope")
def test_missing_confidence_returns_early(mock_scope):
    session = MagicMock()
    settings = LyraSettings()
    contribution = _contribution()
    contribution.enrichment_data = {}
    _maybe_promote(session, contribution, "Test Site", settings)
    mock_scope.assert_not_called()


@patch("pipeline.lyra.site_identifier.label_scope", return_value="out_of_scope")
def test_high_confidence_and_score_100_proceeds_to_the_scope_rule(mock_scope):
    session = MagicMock()
    settings = LyraSettings()
    _maybe_promote(session, _contribution(wikidata_id="Q5"), "Test Site", settings)
    mock_scope.assert_called_once()
    assert mock_scope.call_args.args[1] == ("Q5",)


@patch("pipeline.lyra.site_identifier._promote_to_unified_sites")
@patch("pipeline.lyra.site_identifier._check_spatial_an_match", return_value=None)
@patch("pipeline.lyra.site_identifier.lookup_country", return_value=None)
class TestTheScopeRuleAtPromotion:
    """D58 at Lyra's auto-promotion: a borderline record waits for the founder, a Viking subject is
    out by its item, a non-European site of 500-1500 is promoted."""

    def promote(self, contribution):
        _maybe_promote(MagicMock(), contribution, "Test Site", LyraSettings())

    def test_a_crusader_castle_s_date_in_syria_waits_for_the_founder(
        self, _lookup, _match, promote
    ):
        c = _contribution(lat=34.76, lon=36.29, country="Syria", period_start=1142)
        self.promote(c)
        promote.assert_not_called()
        assert c.enrichment_status != "promoted"

    def test_a_norse_farm_in_greenland_waits_for_the_founder(self, _lookup, _match, promote):
        c = _contribution(lat=61.16, lon=-45.43, country="Greenland", period_start=1100)
        self.promote(c)
        promote.assert_not_called()

    def test_l_anse_aux_meadows_is_never_promoted(self, _lookup, _match, promote):
        c = _contribution(
            lat=51.60, lon=-55.53, country="Canada", period_start=1000, wikidata_id="Q189113"
        )
        self.promote(c)
        promote.assert_not_called()

    def test_a_site_of_europe_after_500_is_never_promoted(self, _lookup, _match, promote):
        c = _contribution(lat=51.56, lon=15.52, country="Poland", period_start=1000)
        self.promote(c)
        promote.assert_not_called()

    def test_prambanan_is_promoted(self, _lookup, _match, promote):
        promote.return_value = None
        c = _contribution(lat=-7.75, lon=110.49, country="Indonesia", period_start=850)
        self.promote(c)
        promote.assert_called_once()
