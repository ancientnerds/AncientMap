"""Tests for pipeline.lyra.hallucination_gate."""
import pytest

from pipeline.lyra.hallucination_gate import (
    Specific,
    extract_specifics,
    verify_against_pack,
)
from pipeline.lyra.theo_citations import CitationRegistry


# ---------------------------------------------------------------------------
# Specific dataclass
# ---------------------------------------------------------------------------


def test_specific_dataclass():
    s = Specific(kind="person", text="Jane Doe", sentence="Jane Doe did X.")
    assert s.kind == "person"
    assert s.text == "Jane Doe"
    assert s.sentence == "Jane Doe did X."


# ---------------------------------------------------------------------------
# extract_specifics — smoke and kind-specific
# ---------------------------------------------------------------------------


def test_extract_specifics_empty():
    assert extract_specifics("") == []


def test_extract_specifics_returns_list():
    assert isinstance(extract_specifics("Hello world."), list)


def test_extract_persons():
    prose = "Dr. Paolo Debertolis measured the acoustics. The analyzer ran for 3 hours."
    specs = extract_specifics(prose)
    person_texts = [s.text for s in specs if s.kind == "person"]
    assert "Paolo Debertolis" in person_texts


def test_extract_persons_ignores_common_places():
    prose = "At Hal Saflieni Hypogeum in Malta, researchers measured resonance."
    specs = extract_specifics(prose)
    person_texts = [s.text for s in specs if s.kind == "person"]
    assert "Hal Saflieni" not in person_texts


def test_extract_dates():
    prose = "In 2007 researchers returned. The site dates to 3600 BCE."
    specs = extract_specifics(prose)
    date_texts = [s.text for s in specs if s.kind == "date"]
    assert "2007" in date_texts
    assert any("3600" in d and "BCE" in d.upper() for d in date_texts)


def test_extract_measurements():
    prose = "The chamber resonated at 70 Hz and 114 Hz. The stones weigh 150 tonnes."
    specs = extract_specifics(prose)
    m_texts = [s.text for s in specs if s.kind == "measurement"]
    assert any("70" in m and ("Hz" in m or "hz" in m) for m in m_texts)
    assert any("150" in m and "tonnes" in m.lower() for m in m_texts)


def test_extract_titles():
    prose = 'The book "Chariots of the Gods" sold millions.'
    specs = extract_specifics(prose)
    title_texts = [s.text for s in specs if s.kind == "title"]
    assert "Chariots of the Gods" in title_texts


def test_extract_long_quotes():
    prose = 'He said "the answer was lost in the sands of time forever ago" and left.'
    specs = extract_specifics(prose)
    quote_texts = [s.text for s in specs if s.kind == "quote"]
    assert any("sands of time forever ago" in q for q in quote_texts)


# ---------------------------------------------------------------------------
# verify_against_pack
# ---------------------------------------------------------------------------


def test_verify_flags_unsupported_specifics():
    registry = CitationRegistry()
    registry.register_source(
        "https://a.example/page",
        "Paolo Debertolis — Hal Saflieni acoustics study (2014)",
        "Paolo Debertolis measured 70 Hz and 114 Hz at Hal Saflieni in 2014.",
    )
    pack = "Paolo Debertolis measured 70 Hz resonance at Hal Saflieni."
    specs = [
        Specific(kind="person", text="Paolo Debertolis", sentence="X."),
        Specific(kind="person", text="David Kisheton", sentence="X."),
    ]
    unsupported = verify_against_pack(specs, pack, registry.sources, "")
    unsupported_texts = [u.text for u in unsupported]
    assert "David Kisheton" in unsupported_texts
    assert "Paolo Debertolis" not in unsupported_texts


def test_verify_normalizes_honorifics():
    """'Debertolis' in pack matches 'Dr. Paolo Debertolis' in prose."""
    registry = CitationRegistry()
    registry.register_source("https://a.example", "t", "Debertolis measured it.")
    pack = "Debertolis measured it."
    specs = [Specific(kind="person", text="Paolo Debertolis", sentence="X.")]
    unsupported = verify_against_pack(specs, pack, registry.sources, "")
    assert not unsupported


def test_verify_checks_original_question():
    """A specific mentioned only in the user question still counts as supported."""
    registry = CitationRegistry()
    specs = [Specific(kind="person", text="Hermes Trismegistus", sentence="X.")]
    unsupported = verify_against_pack(
        specs,
        pack="(empty)",
        sources=registry.sources,
        original_question="What about Hermes Trismegistus?",
    )
    assert not unsupported


def test_verify_checks_source_snippets():
    """A specific in a registered source's snippet counts as supported even if not in pack."""
    registry = CitationRegistry()
    registry.register_source(
        "https://a.example",
        "Some source",
        "Dr. Paolo Debertolis studied this.",
    )
    specs = [Specific(kind="person", text="Paolo Debertolis", sentence="X.")]
    unsupported = verify_against_pack(specs, pack="", sources=registry.sources, original_question="")
    assert not unsupported
