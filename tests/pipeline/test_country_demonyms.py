"""The country -> demonym table (`country_lookup.ISO_TO_DEMONYMS`) the Phase-4 card rule reads.

Phase 4's pilot 2 (2026-09-24) published two cards that name a country through its demonym - "a
Danish hill" (Agri Bavnehøj) and "the first Greek site" (Bassae) - because V10 checked country names
only, although the design's card rule is "no country value, alias or demonym (country_lookup
vocabulary plus a demonym table)". The table lives beside `NAME_TO_ISO`, so the verifier and the
selector's rule text read the same data. These tests hold the table to the vocabulary it serves:
every country code `NAME_TO_ISO` knows has its demonyms, and nothing else is in it.

The owner's decision of 2026-09-24 (the final design, entry [6], wins: "Cultural adjectives such as
Roman, Egyptian or Maya are allowed") splits the card's words in two: the ancient-culture adjectives
a card may carry even where the same word is a modern nationality (`ANCIENT_CULTURE_ADJECTIVES`), and
the modern-nationality demonyms V10 holds (`MODERN_NATIONALITY_DEMONYMS`, the table without them).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pipeline.utils.country_lookup import (
    ANCIENT_CULTURE_ADJECTIVES,
    ISO_TO_DEMONYMS,
    MODERN_NATIONALITY_DEMONYMS,
    NAME_TO_ISO,
)

REPO = Path(__file__).resolve().parents[2]


def test_every_country_of_the_vocabulary_has_its_demonyms_and_nothing_else() -> None:
    assert set(ISO_TO_DEMONYMS) == set(NAME_TO_ISO.values())
    for iso, demonyms in ISO_TO_DEMONYMS.items():
        assert demonyms, iso
        assert len(set(demonyms)) == len(demonyms), iso


def test_every_demonym_is_written_as_a_proper_noun_and_is_no_country_name() -> None:
    """A demonym is matched as written (a capital first letter); a country name that doubles as
    its adjective (`New Zealand`) is already `NAME_TO_ISO`'s and is not repeated here."""
    for iso, demonyms in ISO_TO_DEMONYMS.items():
        for demonym in demonyms:
            assert demonym == demonym.strip() and demonym[0].isupper(), (iso, demonym)
            assert demonym.lower() not in NAME_TO_ISO, (iso, demonym)


@pytest.mark.parametrize(
    ("iso", "demonym"),
    [
        ("GR", "Greek"),
        ("DK", "Danish"),
        ("EG", "Egyptian"),
        ("IT", "Italian"),
        ("ES", "Spanish"),
        ("FR", "French"),
        ("GB", "English"),
        ("GB", "Scottish"),
        ("GB", "Welsh"),
        ("GB", "British"),
        ("IE", "Irish"),
        ("TR", "Turkish"),
        ("PE", "Peruvian"),
        ("MX", "Mexican"),
        ("MT", "Maltese"),
        ("US", "American"),
        ("NL", "Dutch"),
        ("CH", "Swiss"),
    ],
)
def test_the_modern_country_adjectives_are_in_the_table(iso: str, demonym: str) -> None:
    assert demonym in ISO_TO_DEMONYMS[iso]


def _retired_style_rule() -> dict[str, list[str]]:
    """`scripts/verify_descriptions.py`'s `DEMONYM_MAP`: the card style rule the design calls "the
    existing style rule" (retired as a gate on 2026-09-23, still on disk)."""
    path = REPO / "scripts" / "verify_descriptions.py"
    spec = importlib.util.spec_from_file_location("verify_descriptions_retired", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DEMONYM_MAP


#: The retired map's words that are no modern country adjective or people noun: ethnonyms and
#: historic names (Khmer, Magyar, Persian, Mongol, Arabian) and place names (`myanmar`, `easter
#: island` are `NAME_TO_ISO` names, blocked as countries already).
NOT_A_DEMONYM = frozenset(
    {"khmer", "magyar", "persian", "mongol", "arabian", "myanmar", "easter island"}
)


def test_the_table_keeps_every_demonym_of_the_retired_card_style_rule() -> None:
    kept = {demonym.lower() for demonyms in ISO_TO_DEMONYMS.values() for demonym in demonyms}
    for country, words in _retired_style_rule().items():
        iso = NAME_TO_ISO.get(country.lower()) or NAME_TO_ISO.get(country.split(",")[0].lower())
        if iso is None:
            continue  # a country the vocabulary does not know (the Northern Mariana Islands)
        for word in words:
            if word not in NOT_A_DEMONYM:
                assert word in kept, (country, word)


# ------------------------------------------------ the owner's split (2026-09-24, design entry [6])

#: The design's own examples ("Cultural adjectives such as Roman, Egyptian or Maya are allowed") and
#: the ancient cultures the owner's decision names, each allowed in a card.
OWNERS_CULTURES = (
    "Roman", "Greek", "Egyptian", "Maya", "Mayan", "Inca", "Aztec", "Olmec", "Toltec", "Zapotec",
    "Mixtec", "Moche", "Nazca", "Etruscan", "Celtic", "Gallic", "Iberian", "Phoenician", "Punic",
    "Carthaginian", "Persian", "Assyrian", "Babylonian", "Sumerian", "Akkadian", "Hittite",
    "Minoan", "Mycenaean", "Nabataean", "Thracian", "Dacian", "Scythian", "Norse", "Viking",
    "Anglo-Saxon", "Pictish", "Khmer", "Nubian", "Kushite", "Byzantine", "Hellenistic",
    "Mesopotamian",
)  # fmt: skip


def test_the_owners_ancient_cultures_are_allowed() -> None:
    for word in OWNERS_CULTURES:
        assert word in ANCIENT_CULTURE_ADJECTIVES, word


def test_every_ancient_culture_word_is_written_as_a_proper_noun_and_is_no_country_name() -> None:
    for word in ANCIENT_CULTURE_ADJECTIVES:
        assert word == word.strip() and word[0].isupper(), word
        assert word.lower() not in NAME_TO_ISO, word


def test_the_held_demonyms_are_the_table_without_the_ancient_cultures() -> None:
    """(b) is derived, never written twice: every demonym of the table that is no ancient culture's
    word, and nothing else - so a word of (a) is never held, whatever the table carries."""
    table = {demonym for demonyms in ISO_TO_DEMONYMS.values() for demonym in demonyms}
    assert MODERN_NATIONALITY_DEMONYMS == table - ANCIENT_CULTURE_ADJECTIVES
    assert not MODERN_NATIONALITY_DEMONYMS & ANCIENT_CULTURE_ADJECTIVES


@pytest.mark.parametrize(
    "word",
    ["Danish", "Spanish", "French", "Italian", "Turkish", "Mexican", "Peruvian", "British",
     "English", "Maltese", "Dane", "Spaniard", "Irish", "Scottish", "Welsh", "Cypriot"],
)  # fmt: skip
def test_a_modern_nationality_is_held(word: str) -> None:
    assert word in MODERN_NATIONALITY_DEMONYMS


@pytest.mark.parametrize("word", ["Greek", "Hellenic", "Hellene", "Egyptian", "Macedonian"])
def test_an_ancient_culture_that_is_also_a_modern_demonym_is_not_held(word: str) -> None:
    """The words where the split matters: the table carries them (GR, EG, MK) and (a) takes them."""
    assert any(word in demonyms for demonyms in ISO_TO_DEMONYMS.values()), word
    assert word in ANCIENT_CULTURE_ADJECTIVES and word not in MODERN_NATIONALITY_DEMONYMS
