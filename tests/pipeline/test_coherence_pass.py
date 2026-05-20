"""Tests for pipeline.lyra.coherence_pass."""

import pytest

from pipeline.lyra.coherence_pass import (
    CoherenceResult,
    Contradiction,
    NumericClaim,
    NumericConflict,
    check_title_terms_in_body,
    extract_numeric_claims,
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
    result = await run_coherence_pass("The Shining Ones: Sky Gods", body, fake_llm, settings=None)
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
    result = await run_coherence_pass("The Shining Ones: Sky Gods", body, broken_llm, settings=None)
    assert result.contradictions == []
    # Local title-term check still runs
    assert result.title_terms_defined_in_body["Shining Ones"] is True


@pytest.mark.asyncio
async def test_run_coherence_pass_handles_malformed_json():
    """Malformed JSON from LLM → graceful fallback to empty contradictions."""

    async def bad_llm(sys, usr, max_tok, settings, temp):
        return "not json"

    result = await run_coherence_pass("Title Terms Here", "body", bad_llm, settings=None)
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

    result = await run_coherence_pass("Title Phrase Here", "body", fake_llm, settings=None)
    assert len(result.contradictions) == 1
    assert result.contradictions[0].entity == "geopolymer"


# ---------------------------------------------------------------------------
# extract_numeric_claims
# ---------------------------------------------------------------------------


def test_extract_numeric_claims_finds_measurements_with_sections():
    body = (
        "# Title\n\n"
        "## Structure\n\n"
        "The Osiris Shaft descends approximately 25-30 m below the plateau surface.\n\n"
        "## Hydrogeology\n\n"
        "The shaft extends approximately 30-35 meters below the desert.\n"
        "Groundwater table sits at +15 m above sea level.\n"
    )
    claims = extract_numeric_claims(body)
    sections = {c.section for c in claims}
    assert "Structure" in sections
    assert "Hydrogeology" in sections
    structure_values = [c.value_text for c in claims if c.section == "Structure"]
    hydro_values = [c.value_text for c in claims if c.section == "Hydrogeology"]
    assert any("25-30" in v or "25 - 30" in v for v in structure_values)
    assert any("30-35" in v or "30 - 35" in v for v in hydro_values)
    assert any("15 m" in v for v in hydro_values)


def test_extract_numeric_claims_keeps_surrounding_sentence():
    body = "## S\n\nThe African Humid Period ended around 5000 cal yr BP.\n"
    claims = extract_numeric_claims(body)
    assert claims
    assert "African Humid Period" in claims[0].surrounding_sentence


def test_extract_numeric_claims_handles_no_headings():
    """Plain prose without ## headings is grouped under '(intro)'."""
    claims = extract_numeric_claims("The shaft is 30 m deep.")
    assert any(c.section == "(intro)" for c in claims)


def test_extract_numeric_claims_empty_body():
    assert extract_numeric_claims("") == []


def test_extract_numeric_claims_ignores_bare_numbers():
    """Numbers without a recognised unit (e.g. a section index '[1]') are skipped."""
    claims = extract_numeric_claims("## S\n\nReference [5] mentions site 7.")
    assert claims == []


# ---------------------------------------------------------------------------
# run_coherence_pass — numeric_conflicts wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_coherence_pass_parses_numeric_conflicts():
    """LLM returns numeric_conflicts in JSON → CoherenceResult exposes them."""

    async def fake_llm(sys, usr, max_tok, settings, temp):
        return (
            '{"contradictions": [], '
            '"title_terms": [], "title_terms_defined_in_body": {}, '
            '"numeric_conflicts": [{'
            '"entity": "Osiris Shaft depth", '
            '"section_a": "Structure", "value_a": "25-30 m", '
            '"section_b": "Hydrogeology", "value_b": "30-35 m", '
            '"suggested_resolution": "Use 30 m consistently or expose the range.",'
            ' "severity": "medium"}]}'
        )

    body = (
        "## Structure\n\nThe shaft descends 25-30 m.\n\n"
        "## Hydrogeology\n\nThe shaft is 30-35 m deep.\n"
    )
    result = await run_coherence_pass("Osiris Shaft", body, fake_llm, settings=None)
    assert len(result.numeric_conflicts) == 1
    nc = result.numeric_conflicts[0]
    assert nc.entity == "Osiris Shaft depth"
    assert nc.value_a == "25-30 m"
    assert nc.value_b == "30-35 m"
    assert nc.severity == "medium"
    # Pre-extracted claims also surface in the result for downstream debugging
    assert result.numeric_claims  # non-empty


@pytest.mark.asyncio
async def test_run_coherence_pass_filters_incomplete_numeric_conflicts():
    """Entries missing entity/value_a/value_b are dropped."""

    async def fake_llm(sys, usr, max_tok, settings, temp):
        return (
            '{"contradictions": [], '
            '"title_terms": [], "title_terms_defined_in_body": {}, '
            '"numeric_conflicts": ['
            '{"entity": "", "value_a": "1 m", "value_b": "2 m"},'
            '{"entity": "X", "value_a": "", "value_b": "2 m"},'
            '{"entity": "Real conflict", "section_a": "A", "value_a": "10 m",'
            ' "section_b": "B", "value_b": "100 m", "suggested_resolution": "Pick A.",'
            ' "severity": "high"}'
            "]}"
        )

    result = await run_coherence_pass(
        "Some Title", "## S\n\nThe value is 10 m.\n", fake_llm, settings=None
    )
    assert len(result.numeric_conflicts) == 1
    assert result.numeric_conflicts[0].entity == "Real conflict"


@pytest.mark.asyncio
async def test_run_coherence_pass_returns_empty_conflicts_on_llm_failure():
    """LLM exception → numeric_conflicts stays empty but numeric_claims still extracted."""

    async def broken_llm(sys, usr, max_tok, settings, temp):
        raise RuntimeError("LLM down")

    body = "## S\n\nThe shaft is 30 m deep.\n"
    result = await run_coherence_pass("Test", body, broken_llm, settings=None)
    assert result.numeric_conflicts == []
    assert any("30 m" in c.value_text for c in result.numeric_claims)
