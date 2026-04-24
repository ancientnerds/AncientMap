"""Tests for pipeline.lyra.canonical_coverage."""
import pytest

from pipeline.lyra.canonical_coverage import (
    extract_user_subquestions,
    find_coverage_gaps,
)


# ---------------------------------------------------------------------------
# extract_user_subquestions
# ---------------------------------------------------------------------------


def test_extract_subquestions_basic():
    q = "What if the Shining Ones were aliens? Could they have manipulated matter?"
    subs = extract_user_subquestions(q)
    assert any("shining ones" in s.lower() for s in subs)
    assert any("manipulated matter" in s.lower() for s in subs)


def test_extract_subquestions_handles_whatif_without_qmark():
    q = "What if aliens built the pyramids."
    subs = extract_user_subquestions(q)
    # "What if" trigger should catch it even without a question mark
    assert any("aliens built" in s.lower() for s in subs)


def test_extract_subquestions_empty_input():
    assert extract_user_subquestions("") == []


def test_extract_subquestions_no_questions():
    q = "This is a declarative statement. Nothing to extract here."
    assert extract_user_subquestions(q) == []


def test_extract_subquestions_preserves_whole_sentence():
    q = "Could they have skills like manipulating matter via quantum mechanics?"
    subs = extract_user_subquestions(q)
    assert len(subs) == 1
    assert "quantum mechanics" in subs[0]


# ---------------------------------------------------------------------------
# find_coverage_gaps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_gaps_returns_missing_subtopics():
    """Mock LLM: first call returns canonical list, second returns gaps."""
    responses = iter(
        [
            '{"canonical_subtopics": ["Giza", "Watchers", "Puma Punku"]}',
            '{"missing_subtopics": ["Watchers"]}',
        ]
    )

    async def fake_llm(sys, usr, max_tok, settings, temp):
        return next(responses)

    gaps = await find_coverage_gaps(
        question="Ancient aliens",
        proposed_angle_topics=["Giza pyramid construction", "Puma Punku precision"],
        llm_call=fake_llm,
        settings=None,
    )
    assert gaps == ["Watchers"]


@pytest.mark.asyncio
async def test_find_gaps_filters_fabricated_subtopics():
    """LLM's gap list must not include anything not in the canonical list."""
    responses = iter(
        [
            '{"canonical_subtopics": ["A", "B"]}',
            '{"missing_subtopics": ["A", "X-made-up"]}',
        ]
    )

    async def fake_llm(sys, usr, max_tok, settings, temp):
        return next(responses)

    gaps = await find_coverage_gaps(
        question="q",
        proposed_angle_topics=[],
        llm_call=fake_llm,
        settings=None,
    )
    assert gaps == ["A"]


@pytest.mark.asyncio
async def test_find_gaps_handles_llm_failure_gracefully():
    """If enumeration fails, return empty list — don't block decomposition."""

    async def broken_llm(sys, usr, max_tok, settings, temp):
        raise RuntimeError("LLM down")

    gaps = await find_coverage_gaps(
        question="q", proposed_angle_topics=[], llm_call=broken_llm, settings=None
    )
    assert gaps == []


@pytest.mark.asyncio
async def test_find_gaps_handles_malformed_json_gracefully():
    async def malformed_llm(sys, usr, max_tok, settings, temp):
        return "not json at all"

    gaps = await find_coverage_gaps(
        question="q", proposed_angle_topics=[], llm_call=malformed_llm, settings=None
    )
    assert gaps == []


@pytest.mark.asyncio
async def test_find_gaps_empty_canonical_list_returns_empty():
    responses = iter(
        [
            '{"canonical_subtopics": []}',
        ]
    )

    async def fake_llm(sys, usr, max_tok, settings, temp):
        return next(responses)

    gaps = await find_coverage_gaps(
        question="q", proposed_angle_topics=[], llm_call=fake_llm, settings=None
    )
    assert gaps == []
