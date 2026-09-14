"""Tests for the _is_same_name gate on published-text rewriting.

Regression: site_matcher._correct_text_fields() used to rewrite a news item's
headline/summary/facts with the matched site's name on ANY match. Combined
with `caption_garble` aliases (which memoized a 0.35-threshold trigram guess
as an exact match), this put the wrong site into 206 published headlines --
e.g. the Chinese Neolithic site Jiahu was published as "Kahu-Jo-Darro", a site
in Pakistan. The gate below allows only spelling variants of the same name.
"""

from pipeline.lyra.site_matcher import _correct_text_fields, _is_same_name


class FakeItem:
    """Minimal stand-in for NewsItem — _correct_text_fields only touches these."""

    def __init__(self, extracted, headline, summary=None, post_text=None, facts=None):
        self.id = 1
        self.site_name_extracted = extracted
        self.headline = headline
        self.summary = summary
        self.post_text = post_text
        self.facts = facts


def test_different_places_do_not_match():
    assert not _is_same_name("Jiahu", "Kahu-Jo-Darro")
    assert not _is_same_name("Hampi", "Castle Hill, Hampshire")
    assert not _is_same_name("Denisova Cave", "Cave del Valle, Cantabria")
    assert not _is_same_name("Lake Van", "Glastonbury Lake Village")
    assert not _is_same_name("Great Zimbabwe", "Great Ziggurat of Ur")


def test_expansion_is_the_same_name():
    assert _is_same_name("Hawara", "Pyramid of Amenemhat III at Hawara")
    assert _is_same_name("Cahokia", "Cahokia Mounds State Historic Site")
    assert _is_same_name("Bada Valley megaliths", "Bada Valley Megaliths")


def test_transliteration_variant_is_the_same_name():
    assert _is_same_name("Goebekli Tepe", "Göbekli Tepe")
    assert _is_same_name("Catalhoyuk", "Çatalhöyük")
    assert _is_same_name("Phaistos", "Faistos")
    assert _is_same_name("Mohenjo Daro", "Mohenjo-daro")


def test_gate_is_deliberately_conservative():
    """Vowel-insertion variants fall outside normalize_transliteration's map.

    These are the SAME site, so the gate declines a rewrite it could have made.
    That is the intended trade: a missed correction leaves the text saying what
    the source said, which is never wrong. The site_id link still identifies it.
    """
    assert not _is_same_name("Osireion", "Osirion")
    assert not _is_same_name("Tell el-Hammam", "Tall el-Hammam")


def test_headline_is_left_alone_for_a_different_place():
    item = FakeItem(
        "Jiahu",
        "Jiahu: 9,000-year-old Chinese Neolithic site with multiple world firsts",
        facts=["Over 40 bone flutes were unearthed at Jiahu."],
    )
    _correct_text_fields(item, "Kahu-Jo-Darro")
    assert item.headline.startswith("Jiahu:")
    assert "Kahu-Jo-Darro" not in item.headline
    assert item.facts == ["Over 40 bone flutes were unearthed at Jiahu."]


def test_spelling_variant_is_still_corrected():
    item = FakeItem("Goebekli Tepe", "New dating for Goebekli Tepe enclosure D")
    _correct_text_fields(item, "Göbekli Tepe")
    assert item.headline == "New dating for Göbekli Tepe enclosure D"


def test_no_extracted_name_is_a_noop():
    item = FakeItem(None, "Unchanged headline")
    _correct_text_fields(item, "Some Site")
    assert item.headline == "Unchanged headline"
