"""Tests for specialist selection and prompt building in theo_specialists."""
import pytest

from pipeline.lyra.theo_specialists import (
    SPECIALIST_POOL,
    Specialist,
    build_specialist_prompt,
    select_specialists,
)

# ---------------------------------------------------------------------------
# Pool integrity
# ---------------------------------------------------------------------------


def test_pool_has_27_specialists():
    """SPECIALIST_POOL contains exactly 27 specialists."""
    assert len(SPECIALIST_POOL) == 27


def test_all_ids_unique():
    """All specialist IDs in the pool are unique."""
    ids = [s.id for s in SPECIALIST_POOL]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# select_specialists — structural guarantees
# ---------------------------------------------------------------------------


def test_select_always_includes_historian():
    """ancient_historian is always included regardless of question content."""
    panel = select_specialists(
        domain_tags=["geology"],
        question="How does sediment erosion affect site preservation?",
        count=3,
    )
    ids = [s.id for s in panel]
    assert "ancient_historian" in ids


def test_select_returns_correct_count():
    """Requesting count=5 returns exactly 5 specialists."""
    panel = select_specialists(
        domain_tags=["archaeology"],
        question="Tell me about ancient Roman trade routes.",
        count=5,
    )
    assert len(panel) == 5


def test_select_count_exceeds_pool():
    """Requesting more specialists than the pool size returns at most pool size."""
    panel = select_specialists(
        domain_tags=[],
        question="general question",
        count=99,
    )
    assert len(panel) <= 27


# ---------------------------------------------------------------------------
# select_specialists — keyword and domain matching
# ---------------------------------------------------------------------------


def test_select_keyword_matching():
    """Question containing 'radiocarbon dating calibration' selects dating_specialist."""
    panel = select_specialists(
        domain_tags=[],
        question="What does radiocarbon dating calibration tell us about Bronze Age chronology?",
        count=5,
    )
    ids = [s.id for s in panel]
    assert "dating_specialist" in ids


def test_select_domain_matching():
    """domain_tags=['maritime', 'underwater'] selects underwater_archaeologist."""
    panel = select_specialists(
        domain_tags=["maritime", "underwater"],
        question="Describe a typical ancient harbour site.",
        count=5,
    )
    ids = [s.id for s in panel]
    assert "underwater_archaeologist" in ids


def test_select_fringe_keywords():
    """Fringe question selects alternative history and mythology specialists."""
    panel = select_specialists(
        domain_tags=["fringe", "mythology"],
        question="Did the Shining Ones from Sumerian texts arrive by UFO?",
        count=5,
    )
    ids = [s.id for s in panel]
    assert "alternative_history_researcher" in ids
    assert "comparative_mythologist" in ids


def test_force_include():
    """Force-included specialists appear regardless of keyword match."""
    panel = select_specialists(
        domain_tags=[],
        question="general archaeology question",
        count=3,
        force_include=["volcanologist", "paleoclimatologist"],
    )
    ids = [s.id for s in panel]
    assert "volcanologist" in ids
    assert "paleoclimatologist" in ids


def test_force_exclude():
    """Force-excluded specialists never appear, even if keyword matched."""
    panel = select_specialists(
        domain_tags=["dating"],
        question="radiocarbon dating calibration methods",
        count=5,
        force_exclude=["dating_specialist"],
    )
    ids = [s.id for s in panel]
    assert "dating_specialist" not in ids


def test_force_exclude_baseline():
    """Even the baseline generalist can be excluded."""
    panel = select_specialists(
        domain_tags=[],
        question="general question",
        count=3,
        force_exclude=["ancient_historian"],
    )
    ids = [s.id for s in panel]
    assert "ancient_historian" not in ids


# ---------------------------------------------------------------------------
# build_specialist_prompt
# ---------------------------------------------------------------------------


def test_build_specialist_prompt_returns_tuple():
    """build_specialist_prompt returns a 2-tuple of strings."""
    specialist = SPECIALIST_POOL[0]
    result = build_specialist_prompt(specialist, "What is stratigraphy?", "source context")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)


def test_build_specialist_prompt_contains_name():
    """System prompt contains the specialist's name."""
    specialist = SPECIALIST_POOL[0]
    system_prompt, _ = build_specialist_prompt(
        specialist, "What is stratigraphy?", "source context"
    )
    assert specialist.name in system_prompt


def test_build_specialist_prompt_json_instruction():
    """System prompt contains 'source_ids', instructing JSON output referencing sources."""
    specialist = SPECIALIST_POOL[0]
    system_prompt, _ = build_specialist_prompt(
        specialist, "What is stratigraphy?", "source context"
    )
    assert "source_ids" in system_prompt
