"""claim_support: the mechanical support-location and claim-hygiene rules.

Every literal in this file is copied from the audit of the 31 live papers in
``C:\\tmp\\papers\\<request_id>`` (``docs/reports/theo-paper-defects-2026-10-04.md``
is the catalogue), and the comment above each one names the paper and the
finding it reproduces. Nothing here reads ``C:\\tmp`` at run time: the suite has
to work on a clean machine.
"""

from __future__ import annotations

import dataclasses

import pytest

from pipeline.lyra.claim_support import (
    Located,
    SentenceDefect,
    claim_identifiers,
    claim_numbers,
    claim_site_codes,
    is_retraction_claim,
    locate_support,
    numbers_absent_from,
    sentence_defects,
)

# ---------------------------------------------------------------------------
# locate_support
# ---------------------------------------------------------------------------

# plasma-cosmology-and-the-electric-universe (02515a7a), ref01.txt, the
# first sentence of the paper. The audit verdict is "supported"; the source
# spells the title "Worlds in Collisions", so the title specific must land in
# Located.missing and not in the quote.
PLASMA_CLAIM = (
    "In 1950, Immanuel Velikovsky published *Worlds in Collision* — a book built "
    "around the claim that the planets had behaved catastrophically within recorded "
    "history."
)
PLASMA_SOURCE_SENTENCE = (
    "The idea that Venus is a relatively new body emanating from Jupiter was first "
    "suggested by Immanuel Velikovsky in his book Worlds in Collisions, published in "
    "1950. Velikovsky’s version is more elaborate and reliant on ancient myths than "
    "the version presented in this book."
)

# stargate-project-and-sri-remote-viewing-evidence (099ad920), report class B:
# "the $20 million figure appears in no source in the paper's evidence".
STARGATE_CLAIM = (
    "The program that grew out of those SRI experiments cycled through at least five "
    "codenames — SCANATE, SUN STREAK, GRILL FLAME, CENTER LANE, and finally STARGATE "
    "— and ultimately cost roughly $20 million across those twenty years, from 1975 to 1995."
)
# Every fetched reference text of that paper, keyed by file name as in evidence/.
# ref20 is the one file that mentions a twenty-million-dollar figure at all
# (Wikipedia text with "$20 million termination" in a scratch heading), and it
# is still not enough: it carries neither 1975 nor the codenames.
STARGATE_REFERENCE_TEXTS = {
    "ref01.txt": "But the idea that Venus is a relatively new body emanating from Jupiter "
    "was first suggested by Immanuel Velikovsky, and it is that SRI experiment which "
    "traced the operational origins of the later programme.",
    "ref02_ia.txt": "STAR GATE RECORDS DECLASSIFICATION. The records of the programme run "
    "from 1972 to 1995 and name the reviewing offices rather than the budget.",
    "ref05_ia.txt": "The Air Intelligence Review concluded that no remote viewing report "
    "ever provided actionable information for any intelligence operation.",
    "ref09.txt": "Project director from 1985 to 1995, the programme was wound up after the "
    "AIR review and moved to SAIC under Edwin C. May.",
    "ref11.txt": "Ingo Swann and Hal Puthoff began the joint remote viewing programme at "
    "the laboratories of Stanford Research International at Menlo Park, California.",
    "ref20.txt": (
        "### no actionable intelligence / $20 million termination\n"
        "[sg.txt chars 13380:14308]\n"
        "Based upon the collected findings, which recommended a higher level of critical "
        "research and tighter controls, the CIA terminated the 20 million dollar project, "
        "citing a lack of documented evidence that the program had any value to the "
        "intelligence community. Time magazine stated in 1995 three full-time psychics "
        "were still working on a $500,000-a-year budget out of Fort Meade, Maryland, "
        "which would soon close."
    ),
}
# The one sentence of ref20 that a claim of its own really is carried by: the
# positive control that keeps the None above from being vacuous.
STARGATE_CARRIED_CLAIM = (
    "Time magazine stated in 1995 three full-time psychics were still working on a "
    "$500,000-a-year budget out of Fort Meade."
)


def test_locate_support_finds_the_real_sentence_and_the_quote_is_verbatim():
    located = locate_support(PLASMA_CLAIM, PLASMA_SOURCE_SENTENCE)
    assert located is not None
    assert located.quote in PLASMA_SOURCE_SENTENCE
    assert PLASMA_SOURCE_SENTENCE[located.start : located.end] == located.quote
    assert "Immanuel Velikovsky in his book Worlds in Collisions, published in 1950" in located.quote
    assert "Immanuel Velikovsky" in located.matched
    assert "1950" in located.matched
    # The source's own spelling is "Collisions": the title is in the whole
    # source text nowhere on a word boundary, so it is missing, not matched.
    assert "Worlds in Collision" in located.missing


def test_locate_support_never_splices_two_sentences():
    # panspermia (aae36b9c), report class B: a quotation spliced out of two
    # sentences, verbatim in no contiguous stretch of its source. The source
    # below is three sentences and the claim names the first and the third.
    source = (
        "Life may have arrived from elsewhere in the galaxy. "
        "The panspermia hypothesis is old, and its directed variant is younger. "
        "No mechanism for directed transfer is agreed."
    )
    spliced = "Life may have arrived from elsewhere in the galaxy. No mechanism for directed transfer is agreed."
    assert spliced not in source

    claim = "Life may have arrived from elsewhere in the galaxy. No mechanism for directed transfer is agreed."
    # The claim has no specifics at all, so it can only be located by its own
    # text - and its own text is not a contiguous stretch of the source. No
    # window size can produce a quote, which is the point: a splice is not
    # evidence.
    assert locate_support(claim, source, window=2) is None
    assert locate_support(claim, source, window=3) is None
    # A contiguous claim about the same material is located, so the None above
    # is about the splice and not about the source.
    located = locate_support(
        "The panspermia hypothesis is old, and its directed variant is younger.", source
    )
    assert located is not None
    assert located.quote in source
    assert source[located.start : located.end] == located.quote
    assert located.quote.startswith("The panspermia hypothesis is old")


def test_locate_support_returns_none_for_the_stargate_twenty_million_claim():
    for name, text in STARGATE_REFERENCE_TEXTS.items():
        assert locate_support(STARGATE_CLAIM, text) is None, name
    # Its numbers are the reason: the figure, and the two dates that would have
    # to travel with it.
    assert claim_numbers(STARGATE_CLAIM) == ("20 million", "1975", "1995")
    # The figure itself does occur in one fetched file of that paper, in a
    # scratch Wikipedia extract that was not among its 18 references. What the
    # shipped claim adds on top of it - the twenty-year span - is in no
    # sentence there, which is why the claim is not located.
    ref20_sentence = (
        "Based upon the collected findings, which recommended a higher level of critical "
        "research and tighter controls, the CIA terminated the 20 million dollar project, "
        "citing a lack of documented evidence that the program had any value to the "
        "intelligence community."
    )
    assert numbers_absent_from(STARGATE_CLAIM, ref20_sentence) == ("1975", "1995")


def test_locate_support_locates_a_claim_the_same_source_really_carries():
    located = locate_support(STARGATE_CARRIED_CLAIM, STARGATE_REFERENCE_TEXTS["ref20.txt"])
    assert located is not None
    assert located.quote in STARGATE_REFERENCE_TEXTS["ref20.txt"]
    assert "three full-time psychics" in located.quote
    assert "1995" in located.matched


def test_locate_support_edge_cases():
    assert locate_support("", PLASMA_SOURCE_SENTENCE) is None
    assert locate_support(PLASMA_CLAIM, "") is None
    assert locate_support("   ", "   ") is None
    with pytest.raises(ValueError, match="window must be at least 1"):
        locate_support(PLASMA_CLAIM, PLASMA_SOURCE_SENTENCE, window=0)
    # No specifics at all: located only if the claim's own text is in the source.
    located = locate_support("Venus is a relatively new body.", PLASMA_SOURCE_SENTENCE)
    assert located is not None
    assert located.quote in PLASMA_SOURCE_SENTENCE
    assert located.matched == ()
    assert locate_support("Mars is a relatively new body.", PLASMA_SOURCE_SENTENCE) is None
    # Unicode text is handled end to end: the pineal-dmt paper's nirūpaṇa
    # sentence and the date it is judged on (report class E: the nirūpaṇa is
    # 1577 CE, and the paper had it wrong on the paṭala as well). Note that
    # extract_specifics' person pattern is ASCII-only, so a Devanagari or
    # transliterated name is not among the matched specifics.
    located = locate_support(
        "The nirūpaṇa is dated 1577 CE by Pūrṇānanda Yati.",
        "The Ṣaṭ-chakra-nirūpaṇa of Pūrṇānanda Yati, dated 1577 CE, describes the Ajna.",
    )
    assert located is not None
    assert "Pūrṇānanda Yati" in located.quote
    assert located.quote in (
        "The Ṣaṭ-chakra-nirūpaṇa of Pūrṇānanda Yati, dated 1577 CE, describes the Ajna."
    )
    assert "1577 CE" in located.matched
    assert located.missing == ()


# ---------------------------------------------------------------------------
# claim_numbers / numbers_absent_from
# ---------------------------------------------------------------------------


def test_claim_numbers_normalizes_the_report_forms():
    assert claim_numbers("$20 million") == ("20 million",)
    assert claim_numbers("1650 tons") == ("1650 tons",)
    assert claim_numbers("150 km²") == ("150 km",)
    assert claim_numbers("40%") == ("40%",)
    assert claim_numbers("1,650") == ("1650",)
    assert claim_numbers("9") == ("9",)
    # Spelled out counts are out of scope, so they produce nothing.
    assert claim_numbers("nine dated structures") == ()
    assert claim_numbers("") == ()
    # Order is textual, duplicates collapsed, the currency name dropped.
    assert claim_numbers("$20 million, then $20 million more, in 1975") == (
        "20 million",
        "1975",
    )
    # A range keeps its unit on the last number, and both spellings agree.
    assert claim_numbers("700 to 950 km") == claim_numbers("700-950 km")
    assert claim_numbers("150 square kilometers") == ("150 km",)


def test_numbers_absent_from_catches_the_squatter_man_inflation():
    # the-squatter-man-petroglyph-and-auroral-sky-mythology (27ec3538), report
    # class B: 31 sites across "> 50 km²" published as 150 km². The sentence
    # below is ref07.txt verbatim; the claim is live.md verbatim.
    source_sentence = (
        "The placement of these petroglyphs at 31 archaeological sites covering over 50 "
        "square kilometers has created an unparalleled museum in the heart of the region."
    )
    shipped_claim = (
        "the Teymareh rock art site — which contains over 21,000 petroglyphs spread across 31 "
        "archaeological sites covering approximately 150 square kilometers."
    )
    absent = numbers_absent_from(shipped_claim, source_sentence)
    # The count of sites is in the source; the area the paper published is not.
    assert "31" in claim_numbers(shipped_claim)
    assert "31" not in absent
    assert "150 km" in absent
    assert "50 km" in claim_numbers(source_sentence)


def test_numbers_absent_from_keeps_the_equivalence_of_both_spellings():
    assert numbers_absent_from("150 km²", "over 50 square kilometers") == ("150 km",)
    assert numbers_absent_from("150 km²", "a 150 km² area") == ()


# ---------------------------------------------------------------------------
# claim_site_codes / claim_identifiers / is_retraction_claim
# ---------------------------------------------------------------------------


def test_claim_site_codes_finds_the_mogollon_codes():
    # mogollon-pithouse-sites-across-the-upper-gila (3b9ac686), report class C:
    # Mogollon Village (LA 11568) merged with the SU Site and its house count.
    assert "LA 11568" in claim_site_codes("Mogollon Village (LA 11568), also called the SU Site")
    assert claim_site_codes("Mogollon Village (LA 11568), also called the SU Site") == (
        "LA 11568",
        "SU Site",
    )
    # The Smithsonian accession of the same site's report, longest match first.
    assert claim_site_codes(
        'producing a Smithsonian report titled "MS 3304-a A Report on Excavations at Mogollon:1:15"'
    ) == ("MS 3304-a",)
    assert claim_site_codes("a site with no code at all") == ()
    assert claim_site_codes("") == ()


def test_claim_identifiers_finds_real_identifiers_from_the_papers():
    # plasma-cosmology (02515a7a) references.json, verbatim.
    assert "doi:10.1029/1999ja900500" in claim_identifiers(
        "10.1029/1999ja900500 — https://doi.org/10.1029/1999ja900500 (accessed 2026-09-11)"
    )
    # near-death-experience (b142912a) references.json, verbatim: a DOI that
    # ends at a full stop, and a PMID in a pubmed URL.
    identifiers = claim_identifiers(
        '[29] Lee W. Bailey (2001). A "little death". The Journal of near-death studies. '
        "DOI: 10.17514/jnds-2001-19-3-p139-159. (accessed 2026-08-14) "
        "https://pubmed.ncbi.nlm.nih.gov/11755611/"
    )
    assert identifiers == ("doi:10.17514/jnds-2001-19-3-p139-159", "pmid:11755611")
    # the-phaeton (23336ade) references.json, verbatim.
    assert "arxiv:1607.03963" in claim_identifiers(
        "Solar Obliquity Induced by Planet Nine — https://arxiv.org/abs/1607.03963"
    )
    assert claim_identifiers("a sentence with no identifier in it") == ()
    assert claim_identifiers("") == ()


def test_is_retraction_claim():
    # stargate (099ad920), report class E: this retraction did not exist, and
    # was refuted through Crossref, OpenAlex and Europe PMC.
    assert is_retraction_claim(
        'Daryl Bem\'s controversial "Feeling the Future" paper was retracted after a '
        "multi-site preregistered attempt at replication produced null results."
    )
    # The corrected sentence is the same kind of claim about the record, so it
    # is flagged too: the check that decides it is the same one.
    assert is_retraction_claim(
        'Bem\'s controversial "Feeling the Future" paper was not retracted, but a large '
        "scale replication attempt reported no evidence for it."
    )
    # mogollon (3b9ac686) ref12.txt, verbatim: an ordinary sentence.
    assert not is_retraction_claim(
        "In 1941, we cleaned out eight more houses and recovered approximately 18,000 sherds "
        "and 750 stone and bone tools."
    )
    # "withdrawn" of money is not a claim about a work.
    assert not is_retraction_claim("The fund was withdrawn in 1995.")
    assert not is_retraction_claim("")
    assert not is_retraction_claim("The article was heavily revised.")


# ---------------------------------------------------------------------------
# sentence_defects
# ---------------------------------------------------------------------------

# The six defects the report's class F table records as shipped. The two
# marked "report" are quoted from the table's "what the reader saw" column; the
# other four are verbatim from the paper files, because the repair pass has
# since rewritten some of them and the audit kept the defect, not the string.
SHIPPED_DEFECTS = {
    # cargo-cults (a00c4ee2), report class F row 1: a sentence cut mid-clause.
    "ends_on_function_word": "Related British punitive expeditions killed nearly 100 Onge in a "
    "single incident, establishing a pattern of colonial violence that.",
    # the-phaeton (23336ade), report class F row 2: no full stop at the marker.
    "no_terminator": "A planet of the kind Batygin and Brown modelled can also generate the "
    "Sun's six-degree obliquity, and the specific pole position of the Sun's spin axis, from a "
    "nearly aligned initial state [52] The evidence resolves to this: the TNO clustering "
    "signature is contested.",
    # near-death-experience (b142912a) references.json, verbatim: a doubled stop.
    "double_stop": '[29] Lee W. Bailey (2001). A "little death": The near-death experience and '
    "Tibetan delogs.. The Journal of near-death studies.",
    # the-watchers-nephilim (64da0eaf), report class F row 3: a comma before the stop.
    "comma_before_stop": "Susan Milbrath's reading of the Sun Stone is one specialist's "
    "interpretation rather than consensus [11],.",
    # the-phaeton (23336ade) corrected.md, verbatim: the stored form of the
    # same defect, a marker run that ends a sentence and carries no clause.
    "no_clause_after_marker": "A planet of the kind Batygin and Brown modelled can also generate "
    "the Sun's six-degree obliquity, and the specific pole position of the Sun's spin axis, from "
    "a nearly aligned initial state. [52] The evidence resolves to this: the TNO clustering "
    "signature is contested.",
    # pineal-gland-dmt (4486b29c) corrected.md, verbatim: six of these in that
    # one paper, all written by the repair pass that swallowed the full stop.
    "fragment_after_marker": "Dean et al. put a number to it: the rat brain is capable of "
    "synthesizing and releasing DMT at concentrations comparable to known monoamine "
    "neurotransmitters[7].",
}


@pytest.mark.parametrize("kind", sorted(SHIPPED_DEFECTS))
def test_sentence_defects_finds_each_shipped_structural_defect(kind):
    found = sentence_defects(SHIPPED_DEFECTS[kind])
    assert [defect.kind for defect in found] == [kind]
    assert found[0].offset == SHIPPED_DEFECTS[kind].index(found[0].text)


def test_sentence_defects_reports_the_fragment_not_just_the_kind():
    text = SHIPPED_DEFECTS["fragment_after_marker"]
    defects = sentence_defects(text)
    assert defects[0].text == "[7]"
    assert text[defects[0].offset : defects[0].offset + len(defects[0].text)] == "[7]"
    # The marker's left neighbour is the swallowed full stop's place: the word
    # "neurotransmitters" runs straight into it.
    assert text[defects[0].offset - 1] == "s"
    assert isinstance(defects[0], SentenceDefect)


def test_sentence_defects_finds_nothing_in_a_clean_paragraph():
    # plasma-cosmology (02515a7a) live.md, verbatim, first paragraph of the
    # paper: clean prose with a marker-free sentence run.
    clean = (
        "In 1950, Immanuel Velikovsky published *Worlds in Collision* — a book built around the "
        "claim that the planets had behaved catastrophically within recorded history. Astronomers "
        "demolished its orbital mechanics, but the book refused burial. Twenty-two years later, "
        "Ralph Juergens proposed an electric model for the Sun, arguing that our star runs on "
        "external galactic current rather than internal fusion."
    )
    assert sentence_defects(clean) == ()


def test_sentence_defects_skips_headings_images_and_captions():
    # plasma-cosmology (02515a7a) live.md, verbatim: a caption, its credit line
    # and an image block, none of them prose.
    block = (
        "## Alfvén's Plasma Universe\n"
        "\n"
        "![Jupiter.Aurora.HST.UV](/data/research-images/x.jpg)\n"
        "\n"
        "*Illustration: Jupiter's aurora. Photo: D. Desai / NOIRLab / NSF / AURA / STScI.*\n"
        "\n"
        "[Source](https://noirlab.edu/public/images/noirlab2017-000a/)"
    )
    assert sentence_defects(block) == ()


def test_sentence_defects_does_not_fire_on_the_accepted_marker_shapes():
    # The project's citation unit: a marker run at the end of a paragraph, a
    # marker before the final full stop, and a mid-clause citation.
    accepted = (
        "The dispute was finally settled in 1974, four years after Chapman's death, when Earth "
        "satellites measured downflowing currents for the first time [2, 3] [4].\n"
        "\n"
        "Alfvén was born in 1908 in Norrköping, Sweden [7].\n"
        "\n"
        "The site sits on the San Francisco River near Glenwood in the Reserve area [9] [10]."
    )
    assert sentence_defects(accepted) == ()


def test_sentence_defects_keeps_an_ellipsis_and_a_url_out_of_scope():
    # "..." is three stops, not two; the ADS bibcode in the URL is a
    # bibliographic fact, not prose (plasma-cosmology references.json).
    text = (
        "The ages run 900 B.C. to A.D. 750, and the spread is... unchanged. Worlds in Collision "
        "— https://adsabs.harvard.edu/full/1950PA.....58..278P (accessed 2026-09-11)"
    )
    assert sentence_defects(text) == ()
    assert sentence_defects("") == ()


def test_sentence_defects_handles_unicode_prose():
    # pineal-gland-dmt (4486b29c) live.md, verbatim, and the watchers paper's
    # Radcliffe-Brown *Jurua* (report class C, a spirit given to the wrong group).
    clean = (
        "The Ṣaṭ-chakra-nirūpaṇa system — codified in the 15th–16th century CE and elaborated "
        "across the Yoga Upanishads — does not invoke any anatomical structure called the pineal "
        "gland; that linkage is a later development."
    )
    assert sentence_defects(clean) == ()
    assert sentence_defects(
        "Radcliffe-Brown recorded the sea-spirit of the North Andaman group under the name Jurua, "
        "while the Aka-Bea of the South Andaman knew it as Juruwin."
    ) == ()
    found = sentence_defects(
        "The nirūpaṇa describes the Ajna as a two-petalled lotus inscribed in silver-white, and "
        "the seed syllables mark the union of opposites at the meeting point of the Ida, Pingala, "
        "and Sushumna nadis, as the."
    )
    assert [defect.kind for defect in found] == ["ends_on_function_word"]
    assert found[0].text == "the."


# ---------------------------------------------------------------------------
# The dataclasses are the published interface
# ---------------------------------------------------------------------------


def test_located_is_frozen_and_carries_its_offsets():
    located = locate_support(PLASMA_CLAIM, PLASMA_SOURCE_SENTENCE)
    assert isinstance(located, Located)
    with pytest.raises(dataclasses.FrozenInstanceError):
        located.quote = "something else"  # type: ignore[misc]
