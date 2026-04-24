"""Tests for pipeline.lyra.coherence_pass."""
import pytest

from pipeline.lyra.coherence_pass import (
    CoherenceResult,
    Contradiction,
    check_title_terms_in_body,
    extract_title_terms,
    run_coherence_pass,
)


# ---------------------------------------------------------------------------
# extract_title_terms
# ---------------------------------------------------------------------------


def test_extract_title_terms_basic():
    terms = extract_title_terms("The Shining Ones: Sky Gods, Ancient Astronauts")
    assert "Shining Ones" in terms
    assert "Sky Gods" in terms
    assert "Ancient Astronauts" in terms


def test_extract_title_terms_drops_single_words():
    terms = extract_title_terms("Foo: Bar")
    # Each fragment is one non-filler word; min is 2 words → dropped
    assert "Foo" not in terms
    assert "Bar" not in terms


def test_extract_title_terms_drops_fillers():
    terms = extract_title_terms("Of the The")
    # After filler removal, zero content words → no phrases
    assert terms == []


def test_extract_title_terms_empty():
    assert extract_title_terms("") == []


# ---------------------------------------------------------------------------
# check_title_terms_in_body
# ---------------------------------------------------------------------------


def test_check_title_terms_case_insensitive():
    body = "This paper is about shining ones and how they reached earth."
    terms = ["Shining Ones", "Sky Gods"]
    result = check_title_terms_in_body(terms, body)
    assert result["Shining Ones"] is True
    assert result["Sky Gods"] is False


def test_check_title_terms_empty_terms():
    assert check_title_terms_in_body([], "any body") == {}


# ---------------------------------------------------------------------------
# run_coherence_pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_coherence_pass_parses_llm_output():
    """LLM returns valid JSON → result contains contradictions and term defs."""

    async def fake_llm(sys, usr, max_tok, settings, temp):
        return (
            '{"contradictions": [{"entity": "geopolymer", "stance_a": "no evidence",'
            ' "section_a": "S1", "stance_b": "material evidence", "section_b": "S2",'
            ' "severity": "high"}],'
            ' "title_terms": ["Shining Ones"],'
            ' "title_terms_defined_in_body": {"Shining Ones": true}}'
        )

    # Body does NOT contain "shining ones" so the local check must report False
    # regardless of what the LLM claims.
    body = "Nothing about the title concept appears here at all."
    result = await run_coherence_pass(
        "The Shining Ones: Sky Gods", body, fake_llm, settings=None
    )
    assert len(result.contradictions) == 1
    assert result.contradictions[0].entity == "geopolymer"
    assert result.contradictions[0].severity == "high"
    # Local check overrides LLM's "true" claim since body doesn't mention the term
    assert result.title_terms_defined_in_body["Shining Ones"] is False


@pytest.mark.asyncio
async def test_run_coherence_pass_handles_llm_failure():
    """LLM exception → empty contradictions, local title-check still works."""

    async def broken_llm(sys, usr, max_tok, settings, temp):
        raise RuntimeError("LLM is down")

    body = "This paper defines Shining Ones up front and uses the term throughout."
    result = await run_coherence_pass(
        "The Shining Ones: Sky Gods", body, broken_llm, settings=None
    )
    assert result.contradictions == []
    # Local title-term check still runs
    assert result.title_terms_defined_in_body["Shining Ones"] is True


@pytest.mark.asyncio
async def test_run_coherence_pass_handles_malformed_json():
    """Malformed JSON from LLM → graceful fallback to empty contradictions."""

    async def bad_llm(sys, usr, max_tok, settings, temp):
        return "not json"

    result = await run_coherence_pass(
        "Title Terms Here", "body", bad_llm, settings=None
    )
    assert result.contradictions == []


@pytest.mark.asyncio
async def test_run_coherence_pass_ignores_empty_entity_contradictions():
    """Contradictions without an entity are filtered out."""

    async def fake_llm(sys, usr, max_tok, settings, temp):
        return (
            '{"contradictions": ['
            '{"entity": "", "stance_a": "x", "section_a": "A", "stance_b": "y",'
            ' "section_b": "B", "severity": "low"},'
            '{"entity": "geopolymer", "stance_a": "x", "section_a": "A",'
            ' "stance_b": "y", "section_b": "B", "severity": "high"}'
            '], "title_terms": [], "title_terms_defined_in_body": {}}'
        )

    result = await run_coherence_pass(
        "Title Phrase Here", "body", fake_llm, settings=None
    )
    assert len(result.contradictions) == 1
    assert result.contradictions[0].entity == "geopolymer"
