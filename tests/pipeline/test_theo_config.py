"""Tests for EFFORT_CONFIG and TierConfig in theo_config."""
import pytest

from api.services.theo_config import EFFORT_CONFIG, TierConfig

# ---------------------------------------------------------------------------
# Tier presence
# ---------------------------------------------------------------------------


def test_all_five_tiers_present():
    """EFFORT_CONFIG has all five expected effort tiers."""
    assert "brief" in EFFORT_CONFIG
    assert "note" in EFFORT_CONFIG
    assert "article" in EFFORT_CONFIG
    assert "review" in EFFORT_CONFIG
    assert "thesis" in EFFORT_CONFIG


def test_no_auto_tier():
    """The old 'auto' tier has been removed from EFFORT_CONFIG."""
    assert "auto" not in EFFORT_CONFIG


# ---------------------------------------------------------------------------
# brief tier
# ---------------------------------------------------------------------------


def test_brief_minimal_config():
    """brief tier uses one specialist, no debate, and minimal source APIs."""
    cfg = EFFORT_CONFIG["brief"]
    assert cfg.specialists_count == 1
    assert cfg.debate_rounds == 0
    assert cfg.source_apis == "minimal"


# ---------------------------------------------------------------------------
# note tier
# ---------------------------------------------------------------------------


def test_note_standard_config():
    """note tier uses three specialists and standard source APIs."""
    cfg = EFFORT_CONFIG["note"]
    assert cfg.specialists_count == 3
    assert cfg.source_apis == "standard"


# ---------------------------------------------------------------------------
# article tier
# ---------------------------------------------------------------------------


def test_article_standard_config():
    """article tier uses five specialists, devil's advocate, and standard source APIs."""
    cfg = EFFORT_CONFIG["article"]
    assert cfg.specialists_count == 5
    assert cfg.devils_advocate is True
    assert cfg.source_apis == "standard"


# ---------------------------------------------------------------------------
# review tier
# ---------------------------------------------------------------------------


def test_review_full_config():
    """review tier uses six specialists, one debate round, and full source APIs."""
    cfg = EFFORT_CONFIG["review"]
    assert cfg.specialists_count == 6
    assert cfg.debate_rounds == 1
    assert cfg.source_apis == "full"


# ---------------------------------------------------------------------------
# thesis tier
# ---------------------------------------------------------------------------


def test_thesis_exhaustive_config():
    """thesis tier uses eight specialists, two debate rounds, and exhaustive source APIs."""
    cfg = EFFORT_CONFIG["thesis"]
    assert cfg.specialists_count == 8
    assert cfg.debate_rounds == 2
    assert cfg.source_apis == "exhaustive"


# ---------------------------------------------------------------------------
# Cross-tier: source_apis field
# ---------------------------------------------------------------------------


def test_tier_config_has_source_apis():
    """Every tier in EFFORT_CONFIG has a non-empty source_apis field."""
    valid_groups = {"minimal", "standard", "full", "exhaustive"}
    for tier_name, cfg in EFFORT_CONFIG.items():
        assert cfg.source_apis in valid_groups, (
            f"Tier '{tier_name}' has source_apis={cfg.source_apis!r}, "
            f"expected one of {valid_groups}"
        )
