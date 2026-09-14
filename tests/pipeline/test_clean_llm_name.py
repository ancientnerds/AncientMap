"""Tests for clean_llm_name — the guard on model-supplied site names.

The regression these guard against: the identification prompt returns
``"site_name": "null"`` as a JSON *string* when it cannot correct a name.
``if corrected_name:`` and SQL ``COALESCE`` both accept that, so on
2026-09-14 the production radar showed 47 cards titled "null" and 142 with a
blank title, and site_identifier trigram-searched the site database for the
literal word "null".
"""

import pytest

from pipeline.utils.text import clean_llm_name


@pytest.mark.parametrize(
    "placeholder",
    ["null", "NULL", "None", "n/a", "N/A", "na", "unknown", "Unknown", "undefined", "-", "--"],
)
def test_placeholders_become_none(placeholder):
    assert clean_llm_name(placeholder) is None


@pytest.mark.parametrize("blank", ["", "   ", "\n\t ", None])
def test_blank_becomes_none(blank):
    assert clean_llm_name(blank) is None


def test_placeholder_with_surrounding_whitespace_and_quotes():
    assert clean_llm_name('  "null" ') is None


def test_real_names_survive_unchanged():
    assert clean_llm_name("Göbekli Tepe") == "Göbekli Tepe"
    assert clean_llm_name("Ħal Saflieni Hypogeum") == "Ħal Saflieni Hypogeum"


def test_real_name_is_whitespace_normalised_and_unquoted():
    assert clean_llm_name('  "Valley of the   Kings"\n') == "Valley of the Kings"


def test_name_containing_a_placeholder_word_is_kept():
    # "Nan Madol" starts with "na" but is a real site; only exact matches drop.
    assert clean_llm_name("Nan Madol") == "Nan Madol"
    assert clean_llm_name("Unknown Iron Age settlement") == "Unknown Iron Age settlement"
