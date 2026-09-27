"""Tests for pipeline.lyra.coherence_pass."""

from pipeline.lyra.coherence_pass import (
    NumericClaim,
    check_title_terms_in_body,
    extract_numeric_claims,
    extract_title_terms,
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
