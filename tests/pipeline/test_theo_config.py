"""Tests for EFFORT_CONFIG and TierConfig in theo_config."""
import pytest

from api.services.theo_config import EFFORT_CONFIG, TierConfig


# ---------------------------------------------------------------------------
# Tier presence
# ---------------------------------------------------------------------------


def test_all_tiers_present():
    """EFFORT_CONFIG has all four expected effort tiers."""
    assert "brief" in EFFORT_CONFIG
    assert "paper" in EFFORT_CONFIG
    assert "thesis" in EFFORT_CONFIG
    assert "auto" in EFFORT_CONFIG


# ---------------------------------------------------------------------------
# brief tier
# ---------------------------------------------------------------------------


def test_brief_no_debate():
    """brief tier skips the debate stage (debate_rounds=0)."""
    assert EFFORT_CONFIG["brief"].debate_rounds == 0


def test_brief_single_specialist():
    """brief tier uses exactly one specialist."""
    assert EFFORT_CONFIG["brief"].specialists_count == 1


# ---------------------------------------------------------------------------
# thesis tier
# ---------------------------------------------------------------------------


def test_thesis_has_debate():
    """thesis tier runs two debate rounds."""
    assert EFFORT_CONFIG["thesis"].debate_rounds == 2


# ---------------------------------------------------------------------------
# auto tier
# ---------------------------------------------------------------------------


def test_auto_matches_paper():
    """auto tier has the same configuration values as paper tier."""
    auto = EFFORT_CONFIG["auto"]
    paper = EFFORT_CONFIG["paper"]

    assert auto.specialists_count == paper.specialists_count
    assert auto.max_search_queries == paper.max_search_queries
    assert auto.convergence_stage1 == paper.convergence_stage1
    assert auto.convergence_stage3 == paper.convergence_stage3
    assert auto.convergence_stage5 == paper.convergence_stage5
    assert auto.debate_rounds == paper.debate_rounds
    assert auto.devils_advocate == paper.devils_advocate
    assert auto.simplified_moderator == paper.simplified_moderator
    assert auto.max_tokens_per_call == paper.max_tokens_per_call
    assert auto.max_tokens_synthesis == paper.max_tokens_synthesis
