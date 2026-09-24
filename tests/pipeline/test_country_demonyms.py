"""The country -> demonym table (`country_lookup.ISO_TO_DEMONYMS`) the Phase-4 card rule reads.

Phase 4's pilot 2 (2026-09-24) published two cards that name a country through its demonym - "a
Danish hill" (Agri Bavnehøj) and "the first Greek site" (Bassae) - because V10 checked country names
only, although the design's card rule is "no country value, alias or demonym (country_lookup
vocabulary plus a demonym table)". The table lives beside `NAME_TO_ISO`, so the verifier and the
selector's rule text read the same data. These tests hold the table to the vocabulary it serves:
every country code `NAME_TO_ISO` knows has its demonyms, and nothing else is in it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pipeline.utils.country_lookup import ISO_TO_DEMONYMS, NAME_TO_ISO

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
