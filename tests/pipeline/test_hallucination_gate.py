"""Tests for pipeline.lyra.hallucination_gate."""

import pytest

from pipeline.lyra.hallucination_gate import (
    Specific,
    delete_sentences_with_specifics,
    extract_specifics,
    repair_prose,
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


def test_extract_person_honorific_single_word():
    """ "Dr. Kisheton" is extracted even though "Dr." breaks the 2-word run.

    The baseline PERSON_RE requires two capitalized words in a row, so a
    period-terminated honorific followed by a single surname slips through.
    The honorific extractor closes that gap.
    """
    prose = "Dr. Kisheton measured the chamber."
    specs = extract_specifics(prose)
    person_texts = {s.text for s in specs if s.kind == "person"}
    assert "Kisheton" in person_texts


def test_extract_person_multi_word_run_catches_honorific():
    """ "Professor Smith" matches PERSON_RE as a 2-word run; single-word
    fallback should not also emit "Smith" separately."""
    prose = "Professor Smith confirmed the reading."
    specs = extract_specifics(prose)
    person_texts = {s.text for s in specs if s.kind == "person"}
    # The full run is extracted; not re-emitted as last-name-only
    assert "Professor Smith" in person_texts
    assert "Smith" not in person_texts


def test_extract_person_honorific_without_period():
    """ "Dr Singh" (no period after honorific) matches the 2-word PERSON_RE."""
    prose = "Dr Singh reported the finding."
    specs = extract_specifics(prose)
    person_texts = {s.text for s in specs if s.kind == "person"}
    assert "Dr Singh" in person_texts


def test_extract_institutions():
    """Named institutions like 'Institute of Cosmic Studies' extracted."""
    prose = (
        "The Stanford Research Institute published the finding. "
        "Later, the University of Cambridge confirmed it. "
        "The Society for Archaeoastronomy disagreed."
    )
    specs = extract_specifics(prose)
    inst_texts = {s.text for s in specs if s.kind == "institution"}
    assert any("Stanford Research Institute" in t for t in inst_texts)
    assert any("University of Cambridge" in t for t in inst_texts)
    assert any("Society" in t for t in inst_texts)


def test_extract_institution_does_not_double_count_persons():
    """A Title-Case run that's a person shouldn't also emit as institution."""
    prose = "Johns Hopkins published the study."
    specs = extract_specifics(prose)
    # "Johns Hopkins" is emitted as person (2 Cap words). The institution
    # regex requires Institute/University/etc. after — not present here, so
    # we expect ONLY a person extraction, not an institution one.
    kinds = {s.kind for s in specs}
    assert "person" in kinds
    assert "institution" not in kinds


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
    unsupported = verify_against_pack(
        specs, pack="", sources=registry.sources, original_question=""
    )
    assert not unsupported


# ---------------------------------------------------------------------------
# delete_sentences_with_specifics
# ---------------------------------------------------------------------------


def test_delete_sentences_with_specifics_removes_offenders():
    prose = "Kisheton measured the room. The pattern exists. Debertolis confirmed this."
    unsupported = [Specific(kind="person", text="Kisheton", sentence="Kisheton measured the room.")]
    result = delete_sentences_with_specifics(prose, unsupported)
    assert "Kisheton" not in result
    assert "The pattern exists" in result
    assert "Debertolis confirmed this" in result


def test_delete_sentences_with_specifics_empty_list_is_noop():
    prose = "Some prose here. More prose."
    assert delete_sentences_with_specifics(prose, []) == prose


# ---------------------------------------------------------------------------
# repair_prose
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_prose_no_retries_when_clean():
    """If there are no unsupported specifics, return immediately with zero retries."""

    async def fake_llm(*a, **k):
        raise AssertionError("llm should not be called")

    prose = "Clean prose."
    result, remaining, retries = await repair_prose(
        prose, [], pack="", sources={}, original_question="", llm_call=fake_llm, settings=None
    )
    assert result == prose
    assert remaining == []
    assert retries == 0


@pytest.mark.asyncio
async def test_repair_prose_succeeds_on_first_retry():
    """LLM returns clean prose on first attempt; no sentences deleted."""
    registry = CitationRegistry()
    registry.register_source("https://a", "a", "Debertolis measured it.")
    pack = "Debertolis measured it."

    async def fake_llm(system, user, max_tokens, settings, temperature):
        return "Debertolis measured it."

    unsupported = [Specific(kind="person", text="Kisheton", sentence="Kisheton did it.")]
    result, remaining, retries = await repair_prose(
        "Kisheton did it.",
        unsupported,
        pack=pack,
        sources=registry.sources,
        original_question="",
        llm_call=fake_llm,
        settings=None,
    )
    assert "Kisheton" not in result
    assert remaining == []
    assert retries == 1


@pytest.mark.asyncio
async def test_repair_prose_falls_back_to_deletion_after_retries():
    """If LLM keeps returning bad prose, fall through to mechanical deletion."""

    async def stubborn_llm(system, user, max_tokens, settings, temperature):
        # LLM returns the same bad prose each retry — never clean
        return "David Kisheton did it. More prose here."

    unsupported = [
        Specific(kind="person", text="David Kisheton", sentence="David Kisheton did it.")
    ]
    result, remaining, retries = await repair_prose(
        "David Kisheton did it. More prose here.",
        unsupported,
        pack="",
        sources={},
        original_question="",
        llm_call=stubborn_llm,
        settings=None,
        max_retries=2,
    )
    # After 2 retries + mechanical delete, the Kisheton sentence is gone
    assert "Kisheton" not in result
    assert "More prose here" in result
    assert retries == 2


@pytest.mark.asyncio
async def test_repair_prose_llm_exception_falls_through():
    """If the LLM raises, fall through to mechanical deletion gracefully."""

    async def failing_llm(*a, **k):
        raise RuntimeError("LLM is down")

    unsupported = [Specific(kind="person", text="Kisheton", sentence="Kisheton did it.")]
    result, remaining, retries = await repair_prose(
        "Kisheton did it. Keep this sentence.",
        unsupported,
        pack="",
        sources={},
        original_question="",
        llm_call=failing_llm,
        settings=None,
    )
    assert "Kisheton" not in result
    assert "Keep this sentence" in result
    # We attempted one retry before the exception propagated out of the loop
    assert retries >= 1
