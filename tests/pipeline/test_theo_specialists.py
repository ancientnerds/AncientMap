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


def test_pool_has_18_specialists():
    """SPECIALIST_POOL contains exactly 18 specialists."""
    assert len(SPECIALIST_POOL) == 18


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
    """Requesting more specialists than the pool size returns at most 18."""
    panel = select_specialists(
        domain_tags=[],
        question="general question",
        count=99,
    )
    assert len(panel) <= 18


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
