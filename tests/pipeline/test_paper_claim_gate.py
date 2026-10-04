"""The mechanical claim gate, against the findings of the 31-paper audit.

Every literal below is copied from a real paper in the audit's per-paper artefacts
(`C:\\tmp\\papers\\<request_id>\\live.md`, `audit.json`, `evidence/refNN.txt`), reduced to the
smallest stretch that carries the defect. The comment above each names the paper, the
request id and the audit finding it reproduces. Nothing here reads `C:\\tmp` at run time:
the suite is a pure function of its own literals, so it runs in CI with no artefacts.

Measured input (docs/reports/theo-paper-defects-2026-10-04.md): 2 105 findings over 31
papers, 602 of them supported as written. All 31 passed the production gate.

What these tests are for: every rule must fail on a real defect and stay silent on a real
supported claim. The second half is the harder half - a gate that refuses everything is
worth nothing - so the false-positive guard has the most assertions of anything here.
"""

from __future__ import annotations

import pytest

from pipeline.lyra.paper_claim_gate import (
    RULE_ORDER,
    check_paper,
    check_paragraph_markers,
    check_sentence_structure,
)

# ---------------------------------------------------------------------------
# Class A - the marker is on the wrong reference (384 misattributed)
# ---------------------------------------------------------------------------

# pineal-dmt-in-near-death-and-cross-cultural-mysticism
# (4486b29c-8773-4b49-ab74-f7832426e88e), report section A: "a scale claim sat on
# reference [11]; the sentence belonged to [38], the instrument paper, which was already
# cited elsewhere in the same paper". audit.json finding [28] gives the same sentence with
# the fix `... weaknesses[38].` - i.e. the auditor moved it off [11] onto [38].
# Reference [11] is Lawrence, Carhart-Harris, Griffiths and Timmermann (2022),
# "Phenomenology and content of the inhaled N, N-dimethyltryptamine experience",
# Scientific Reports - evidence/ref38.txt is the NDE-C scale record, and its abstract is
# what carries the 20-item scale, the 5-factor structure and the alpha.
PINEAL_SCALE = (
    "The Greyson NDE Scale remains the principal measurement instrument, though Martial "
    "and colleagues' 2020 Near-Death Experience Content (NDE-C) scale — a 20-item "
    "instrument with a 5-factor structure and Cronbach α = 0.85 — was developed to address "
    "its known weaknesses. [11]"
)
# evidence/ref11.txt, the Lawrence et al. DMT phenomenology paper.
PINEAL_LAWRENCE_2022 = (
    "Participants reported intense visual imagery, a greatly increased number and "
    "diversity of emotional impressions, and elevations in mood. Qualia were typically "
    "of a complex, 'geometrical' nature and predominantly hallucinogenic."
)
# evidence/ref38.txt as it was fetched: the Europe PMC record line, verbatim. The
# `"pubYear": "2020"` matters - the paragraph's date has to be somewhere in the source for
# the reference to carry the sentence at all, which is what makes the control below a real
# control and not a formality.
PINEAL_NDEC_2020 = (
    '{ "title": "The Near-Death Experience Content (NDE-C) scale: Development and '
    'psychometric validation.", "pmid": "33227590", "pmcid": null, '
    '"doi": "10.1016/j.concog.2020.103049", "pubYear": "2020", "authorString": "Martial C, '
    'Simon J, Puttaert N, Gosseries O, Charland-Verville V, Nyssen AS, Greyson B, Laureys '
    'S, Cassol H." } == ABSTRACT == As interest grows in near-death experiences (NDEs), it '
    "is increasingly important to accurately identify them to facilitate empirical "
    "research and reproducibility among assessors. We aimed (1) to reassess the "
    "psychometric properties of the NDE scale developed by Greyson (1983) and (2) to "
    "validate the Near-Death Experience Content (NDE-C) scale that quantifies NDEs in a "
    "more complete way. Internal consistency, construct and concurrent validity analyses "
    "were performed on the NDE scale. Based on those results and the most recent empirical "
    "evidence, we then developed a new 20-item scale. Internal consistency, explanatory and "
    "confirmatory factor, concurrent and discriminant validity analyses were conducted. "
    "Results revealed (1) a series of weaknesses in the NDE scale, (2) a 5-factor structure "
    "covering relevant dimensions and the very good psychometric properties of the NDE-C "
    "scale, including very good internal consistency (Cronbach α = 0.85) and concurrent "
    "validity (correlations above 0.76)."
)

# stargate-project-and-sri-remote-viewing-evidence
# (099ad920-2e52-4180-915c-c040d316f3d7), live.md prose 0, audit.json finding [0],
# verdict `misattributed`, fix kind `replace_claim`. The note: "It gives 1972 for when
# Swann proposed viewing Jupiter, not 1973, and never names the person who arranged the
# session." The paragraph is cited [1]; reference [1] is the CIAO test article.
STARGATE_SESSION = (
    "At 8:00 p.m. Central Standard Time on April 27, 1973, at the Stanford Research "
    "Institute in Menlo Park, California, an artist and author named Ingo Swann settled in "
    'for a remote-viewing session arranged by a mysterious "Mr. Sherman" and aimed his '
    "attention at Jupiter. [1]"
)
# evidence/ref01.txt.
STARGATE_REF01 = (
    "In 1972 Ingo Swann, working at the Stanford Research Institute, suggested carrying "
    "out an experiment to remote-view the planet Jupiter, an idea taken up by physicist "
    "Hal Puthoff and put the two of them to work on the boundary between the animate and "
    "inanimate."
)


# ---------------------------------------------------------------------------
# Class D - a reference that could not be read carries a marker (177 unverifiable)
# ---------------------------------------------------------------------------

# the-engineering-and-origins-of-the-baalbek-megaliths
# (29436601-239b-4139-a5a0-c9e34e32928f). The audit's verdict_counts are 14
# `unverifiable_fetch` and 12 `unverifiable_source` out of 58 findings - the largest
# share of any paper. live.md prose 6 carries [2] [6] [7] [8]; only reference 6 has a file
# in evidence/ (ref02, ref07 and ref08 do not). audit.json finding [4] records the
# assertion as `supported` "Ref 6, the one readable source in this paragraph" - which is
# exactly the blind spot: three of the four markers point at references nobody ever read.
BAALBEK_TRILITHON = (
    "The three megalithic blocks stacked above the courtyard of the Temple of Jupiter at "
    "Baalbek measure approximately 19 metres in length, 4.2 metres in height, and 3.6 "
    "metres in thickness. [2] [6] [7] [8]"
)
# evidence/ref06.txt, the Wikipedia `Baalbek Stones` lead, verbatim wikitext.
BAALBEK_REF06 = (
    "Each one of these stones is {{convert|19|m|ft}} long, {{convert|4.2|m|ft}} high, and "
    "{{convert|3.6|m|ft}} thick, and weighs around {{Convert|750–800|t|lbs}}."
)


# ---------------------------------------------------------------------------
# Class B - the claim is stronger than its source (858 unsupported)
# ---------------------------------------------------------------------------

# the-squatter-man-petroglyph-and-auroral-sky-mythology
# (27ec3538-258c-4960-9493-2bf6c0dc1a3b), audit.json finding [68], verdict `contradicted`,
# fix kind `replace_number`. fix.old "31 archaeological sites covering approximately 150
# square kilometers." / fix.new "31 archaeological sites covering over 50 square
# kilometers, within a 150 square kilometer area[7][8]." The two figures live in two
# different sources: the 31 sites over 50 km² is evidence/ref08.txt, the 150 km² area is
# evidence/ref07.txt.
SQUATTER_AREA = (
    "The Teymareh site contains over 21,000 petroglyphs spread across 31 archaeological "
    "sites covering approximately 150 square kilometers. [8]"
)
# evidence/ref08.txt - the 31 sites over 50 km². The 150 is not in it.
SQUATTER_REF08 = (
    "The placement of these Petroglyphs in 31 archaeological sites with an area of over 50 "
    "square kilometers has brought an unmatched museum in the heart of the region."
)
# evidence/ref07.txt - the 150 km² area, which is a different statement.
SQUATTER_REF07 = (
    "“Over 21,000 carvings have been identified within a 150 square kilometer area in "
    "Teymareh, Khomein,” Mashhadi further elaborated."
)


# ---------------------------------------------------------------------------
# Class C - an entity merged that the sources keep apart (site codes)
# ---------------------------------------------------------------------------

# mogollon-pithouse-sites-across-the-upper-gila
# (3b9ac686-1796-4ad4-92fa-2354c0cc21de), live.md block 1, cited [1]. Reference [1] is the
# Archaeology Southwest fact sheet (evidence/ref1.txt), which names the Mogollon
# Mountains, Flores Mogollón and Haury but nowhere gives a site code. The code appears in
# the paper's own references [2] and [4] - the Barkwill Love paper, "Rethinking 'Village'
# at Mogollon Village (LA 11568)" - which this paragraph does not cite. The audit's class-C
# finding is the same sentence family (findings [9], [10], [11], [15]-[17]: the LA 11568 /
# SU Site merge and "ten" for the source's "nine").
MOGOLLON_VILLAGE = (
    "In the summer of 1939, an archaeologist named Paul S. Martin and his colleague John "
    "B. Rinaldo pitched their field camp in the Gila National Forest of western New Mexico "
    "and began digging into a site the survey sheets called Mogollon Village — formally "
    "LA 11568. [1]"
)
# evidence/ref1.txt, the Archaeology Southwest fact sheet.
MOGOLLON_REF01 = (
    "The cultural tradition archaeologists call Mogollon (pronounced mug-e-own) is named "
    "after the Mogollon Mountains of New Mexico, which are named after Don Juan Ignacio "
    "Flores Mogollón, a Spanish Governor of New Mexico (1712-1715). Archaeologist Emil "
    "Haury was the first to describe the Mogollon archaeological culture as distinct from "
    "Hohokam and ancestral Pueblo groups."
)
# evidence/ref4.txt, the same paper on par.nsf.gov, whose title carries the code.
MOGOLLON_REF04 = (
    "REPORTS Rethinking “Village” at Mogollon Village (LA 11568): Formal Chronological "
    "Modeling of a Persistent Place. Lori Barkwill Love."
)


# ---------------------------------------------------------------------------
# Class E - a date or identifier copied from memory instead of from the record
# ---------------------------------------------------------------------------

# ufos-uap-and-the-modern-disclosure-debate (95fa3798-1678-40a4-ae2e-58595de93918),
# live.md block 30, cited [38] [39]. audit.json, fix kind `replace_date`: old "The 1997
# Sturrock Panel, convened at Stanford" / new "The 1998 Sturrock Panel report, convened at
# Stanford". Measured over the campaign's 24 `replace_date` findings: "1997" occurs
# nowhere in evidence/ref38.txt, which makes this the one date defect a containment check
# can decide. The others mostly cannot - see the false-negative test further down.
UFOS_STURROCK = (
    "The 1997 Sturrock Panel, convened at Stanford with funding from Laurance Rockefeller, "
    "found that some UAP cases have physical evidence worthy of study, but explicitly "
    "concluded it was not convinced that any of this evidence points to a violation of "
    "known natural laws or the involvement of an extraterrestrial intelligence. [38]"
)
# evidence/ref38.txt, the review's own account of the panel.
UFOS_REF38 = (
    "In the first independent review of UFO phenomena since 1970, a panel of scientists "
    "has concluded that some sightings are accompanied by physical evidence that deserves "
    "scientific study. But the panel was not convinced that any of this evidence points to "
    "a violation of known natural laws or the involvement of an extraterrestrial "
    "intelligence. The review was organized and directed by Peter Sturrock, professor of "
    "applied physics at Stanford University, and supported administratively by the Society "
    "for Scientific Exploration."
)

# stargate, audit.json finding [6], live.md paragraph 8, cited [6], verdict
# `misattributed`, fix kind `replace_date`. The note: "Every number in this sentence is
# correct against the source ... The year is not. The JSE record is Vol. 37 No. 3 (2023),
# and the paper says 2022 here and 2023 in paragraph 10 for the same study." Used as the
# measured limit of rule 3, not as a positive case.
STARGATE_YEAR_2022 = (
    "A 2022 systematic review and meta-analysis identified as the first meta-analysis of "
    "remote-viewing studies selected 36 studies with 40 effect sizes and returned an "
    "average effect size of 0.34. [6]"
)
# evidence/ref06.txt, the JSE record. Its own title reads "A 1974-2022 Systematic Review
# and Meta-Analysis", which is where the paper's 2022 also occurs.
STARGATE_JSE_RECORD = (
    "JSE Vol 37 No 3 (2023) record, published 2023-10-19. Vol. 37 No. 3 (2023) Remote "
    "Viewing: A 1974-2022 Systematic Review and Meta-Analysis. This is the first "
    "meta-analysis of all studies related to remote-viewing tasks conducted up to December "
    "2022. After applying our inclusion criteria, we selected 36 studies with a total of "
    "40 effect sizes, with an average effect size of 0.34."
)

# stargate, audit.json findings [12] and [15], cited [9]. Finding [12] is the AIR
# evaluation paragraph, cited [3] and reattributed to [9]; finding [15] is the Bem
# retraction sentence, also on [9]: "I could confirm neither claim from anything in the
# reference list", and the fix is "Bem's controversial 'Feeling the Future' paper was not
# retracted".
#
# Two spellings of the same paragraph, both real. The paper as it shipped prints the
# quotation de-hyphenated; the fetched text carries the PDF's line-break hyphen. The
# de-hyphenated form is the first constant below and is a defect in its own right; the
# hyphenated form is what the *source* reads, and pairing it with the Bem sentence is how
# rule 6 becomes reachable - a paragraph that locates and still claims a retraction.
STARGATE_AIR_DEHYPHENATED = (
    'The AIR evaluation concluded that "in no case had the information provided ever been '
    'used to guide intelligence operations" and that remote viewing had therefore "failed '
    'to produce actionable intelligence." [9]'
)
STARGATE_AIR_AND_RETRACTION = (
    'The AIR evaluation concluded that "in no case had the informa- tion provided ever been '
    'used to guide intelligence operations" and that remote viewing had therefore "failed to '
    'produce actionable intelligence." Daryl Bem\'s controversial "Feeling the Future" '
    "paper was retracted after a multi-site preregistered attempt at replication produced "
    "null results. [9]"
)
# evidence/ref09.txt, the AIR review's verdict, with the source's own line-break hyphen.
STARGATE_REF09 = (
    "Hyman agreed that “something beyond odd statistical hiccups is taking place,” but he "
    "added that “even if remote viewing is a real ability possessed by some individuals, "
    "its usefulness in intelligence gathering is questionable.” The AIR consultants "
    "ultimately sup- ported Hyman’s position, as they concluded that “in no case had the "
    "informa- tion provided ever been used to guide intelligence operations” and that "
    "remote viewing had therefore “failed to produce actionable intelligence.”"
)

# Class E, the identifier half: audit.json finding [28] of the same paper records a
# recovered source as "Mossbridge, Tressoldi and Utts (2012), Frontiers in Psychology,
# doi:10.3389/fpsyg.2012.00390", while the prose it replaced cited reference [17], a
# laboratory-history article that carries no DOI at all. Report section E: "an agent in
# this campaign twice wrote a wrong DOI and had to search by title to recover."
STARGATE_WRONG_DOI = (
    "The presentiment meta-analysis reported significant physiology-before-stimulus "
    "effects in advance, and the original paper itself flagged expectation bias. "
    "doi:10.3389/fpsyg.2012.00390 [17]"
)
STARGATE_REF17_PEAR = (
    "PEAR closed in February 2007, being incorporated into the International "
    "Consciousness Research Laboratories, and was criticised for lacking scientific "
    "rigor, poor methodology and misuse of statistics."
)


# ---------------------------------------------------------------------------
# The false-positive guard: a real `supported` finding must produce nothing
# ---------------------------------------------------------------------------

# the-engineering-and-origins-of-the-baalbek-megaliths, audit.json finding [25], verdict
# `supported`, cited [14], fix kind `null` (nothing changed). The source_quote the auditor
# recorded is reproduced verbatim as the source text, so the numbers 24 and 15 in the
# prose are in the source exactly as the source writes them. evidence/ref14.txt.
BAALBEK_HEROD = (
    "The masonry of the T-shaped podium is identical with that of Herod's terrace walls "
    "for the Temple in Jerusalem, indicating that Herod was involved in the erection of "
    "the Jupiter temple in Heliopolis, a role plausible only between 24 and 15 BC. [14]"
)
BAALBEK_REF14 = (
    "The masonry of the preserved T-shaped podium is identical with that of Herod’s "
    "terrace walls for the Temple in Jerusalem, indicating that Herod was involved in the "
    "erection of the Jupiter temple in Heliopolis. Paturel argues that Herod’s engagement "
    "in Baalbek is only plausible in the period between the deposition of Zenodoros and "
    "the foundation of the colonia, i.e., between 24 and 15 BC."
)


# ---------------------------------------------------------------------------
# The measurement trap: a picture is three stored paragraphs
# ---------------------------------------------------------------------------

# The shape of every paper in the audit: one prose paragraph, then a picture stored as
# three blocks - `![...](...)`, `*caption* [Source](url)`, and the next picture - then
# more prose, then `## References`. The report's measurement trap: "a naive paragraph
# count calls a 24-image paper 72 paragraphs and reports half the paper as uncited. Each
# picture is three stored paragraphs - ![...](...), *caption*, [Source](url) - and must
# be filtered out first."
# The image markdown, the alt-text QA flag and the paths are the real stored shapes
# (a Baalbek image path, and the `![gallery:<hash>|verified:yes|<title>]` flag the report
# names in section G).
BAALBEK_WITH_PICTURE = (
    "The Triton statue stood at the sanctuary's eastern end.\n\n"
    "![gallery:f5331e89|verified:yes|Temple of Jupiter, Baalbek, Lebanon]"
    "(/data/research-images/29436601-239b-4139-a5a0-c9e34e32928f/"
    "p0_Temple_of_Jupiter_at_Baalbek.jpg)\n\n"
    "*Temple of Jupiter, Baalbek, Lebanon. Photo: Nina Alchin.* "
    "[Source](https://commons.wikimedia.org/wiki/File:Temple_of_Jupiter,_Baalbek.jpg)\n\n"
    + BAALBEK_HEROD
    + "\n\n## References\n\n[14] A BMCR review of Adam (1977) — "
    "https://bmcr.brynmawr.edu/2011/02/review-of-adam-roman-building\n"
)


# ---------------------------------------------------------------------------
# Class F - the six structural defects that shipped to live pages
# ---------------------------------------------------------------------------

# Report section F. Four of the six are quoted verbatim there; the two marker-shaped ones
# are given in the shape the report describes, because the audit artefacts no longer hold
# the broken text (the repair pass fixed them - the report's own point, since two of the
# six were introduced by the repair).
SEAM_CARGO_CULTS_FRAGMENT = (
    "Related British punitive expeditions killed nearly 100 Onge in a single incident, "
    "establishing a pattern of colonial violence that."
)
SEAM_CARGO_CULTS_FRAGMENT_2 = (
    "Both expeditions were turned back, an attack the people they."
)
SEAM_PHAETON_NO_STOP = (
    "The two bodies began their approach from a nearly aligned initial state [52] The "
    "evidence resolves the orbit."
)
SEAM_WATCHERS_COMMA = (
    "The two witnesses disagreed rather than consensus [11],."
)
SEAM_REINCARNATION_DOUBLE_STOP = (
    "The interval between the two reports was estimated at roughly 16 months.."
)
SEAM_PHAETON_MISSING_REF_LINE = (
    "The catalogue of the sixth through eleventh sessions runs from [50] to [55].\n\n"
    "## References\n\n[1] The first reference — https://example.org/one\n"
)
# pineal-dmt, the repair pass's own defect: a replacement sentence that swallowed its full
# stop, written as `...neurotransmitters[7].` with the marker glued to the word. A1's
# docstring records 95 of these in the corpus, 6 of them in this one paper.
SEAM_PINEAL_MARKER_SWALLOWED = (
    "The measure is comparable to known monoamine neurotransmitters[7]."
)


def _rules(issues) -> list[str]:
    return [issue.rule for issue in issues]


def _for_marker(issues, marker: str):
    return [issue for issue in issues if issue.marker == marker]


# ---------------------------------------------------------------------------
# Rule 1 - located_sentence
# ---------------------------------------------------------------------------


def test_a_scale_claim_on_eleven_yields_one_located_sentence_naming_eleven():
    """pineal, report section A: the scale claim sat on [11]; it belongs to [38].

    The marker is asked to carry its own sentence, and the paragraph-aggregate rule names
    every value of that sentence which no cited reference carries: "Greyson", "2020" and the
    full scale name. So the finding is now `unsupported_specific` rather than the coarser
    `located_sentence` - same defect, named value by value.
    """
    issues = check_paper(PINEAL_SCALE, {"11": PINEAL_LAWRENCE_2022, "38": PINEAL_NDEC_2020})
    located = [i for i in issues if i.rule in ("located_sentence", "unsupported_specific")]
    assert len(located) == 3, _rules(issues)
    assert {i.paragraph for i in located} == {0}
    assert "Greyson" in "".join(i.detail for i in located)
    assert all(i.rule != "unreadable_marker" for i in issues)


def test_the_audit_repair_moves_the_marker_to_the_reference_that_carries_it():
    """pineal: the audit's own fix for finding [28] is the sentence with [38] on it.

    The fix is `... weaknesses[38].` - the sentence and its reference change together, which
    is what class A is: a true sentence on the wrong reference. The gate cannot certify the
    repair, because `claim_support.locate_support` needs a second matched specific before it
    accepts a window; what it does certify is that the repair stopped being a support
    finding, which is the change the audit made.
    """
    repaired = PINEAL_SCALE.replace("[11]", "[38]")
    texts = {"11": PINEAL_LAWRENCE_2022, "38": PINEAL_NDEC_2020}
    before = _rules(check_paragraph_markers(PINEAL_SCALE, texts))
    after = _rules(check_paragraph_markers(repaired, texts))
    assert "unsupported_specific" in before
    assert after == []


def test_a_paragraph_its_source_really_carries_is_not_refused():
    """The control for the pineal test: a marker whose source carries the paragraph.

    The stargate AIR verdict, spelled the way reference 9 spells it, is the same shape of
    claim - a quotation on a marker - and the marker is honoured. Without this, the pineal
    test would pass for the wrong reason: a gate that refuses every paragraph is not a gate.
    """
    issues = check_paragraph_markers(
        STARGATE_AIR_DEHYPHENATED.replace("information", "informa- tion"), {"9": STARGATE_REF09}
    )
    assert not [i for i in issues if i.rule in ("located_sentence", "unreadable_marker")], [
        (i.rule, i.detail) for i in issues
    ]


def test_stargate_session_yields_a_located_sentence_naming_the_values_it_lacks():
    """stargate audit finding [0], verdict `misattributed`, fix kind `replace_claim`.

    The paragraph shares its SRI/Jupiter substance with reference 1, so the values that
    decide it are the session's: "It gives 1972 for when Swann proposed viewing Jupiter, not
    1973, and never names the person who arranged the session." The gate refuses the marker
    and names what the source carries none of, so the detail is actionable on its own.
    """
    issues = check_paragraph_markers(STARGATE_SESSION, {"1": STARGATE_REF01})
    located = [i for i in issues if i.rule in ("located_sentence", "unsupported_specific")]
    assert located, _rules(issues)
    detail = "".join(i.detail for i in located)
    assert "1973" in detail
    assert "in none of the texts" in detail or "carries none of" in detail


# ---------------------------------------------------------------------------
# Rule 2 - unreadable_marker
# ---------------------------------------------------------------------------


def test_a_marker_on_a_reference_with_no_text_is_unreadable_not_unsupported():
    """baalbek, class D: [2] and [7] have no file in evidence/ at all.

    The rule that matters here is which of the two rules fires. An unreadable reference is
    a dead link, and reporting it as a support failure would send a writer looking for a
    better source instead of fetching the one it already cites.
    """
    issues = check_paragraph_markers(
        BAALBEK_TRILITHON,
        {"2": "", "6": BAALBEK_REF06, "7": "   ", "8": BAALBEK_REF06},
    )
    for marker in ("[2]", "[7]"):
        found = _for_marker(issues, marker)
        assert found, f"{marker} produced no issue: {_rules(issues)}"
        assert all(issue.rule == "unreadable_marker" for issue in found), _rules(found)
        assert "no fetched text" in found[0].detail
    assert not [i for i in issues if i.rule == "located_sentence" and i.marker in ("[2]", "[7]")]


def test_a_reference_keyed_by_a_missing_entry_is_unreadable_too():
    """A marker on a number the caller knows nothing about is not silently supported.

    The gate cannot tell a reference that was never fetched from one the caller forgot to
    pass, so it refuses both. That is the documented behaviour: no fallback that turns an
    absent input into a pass.
    """
    issues = check_paragraph_markers(BAALBEK_TRILITHON, {"6": BAALBEK_REF06})
    for marker in ("[2]", "[7]", "[8]"):
        found = _for_marker(issues, marker)
        assert found and all(i.rule == "unreadable_marker" for i in found), (marker, _rules(issues))


# ---------------------------------------------------------------------------
# Rule 3 - number_exact, and where the squatter-man number is actually caught
# ---------------------------------------------------------------------------


def test_the_squatter_man_area_of_150_against_a_source_that_says_over_50():
    """squatter-man audit finding [68], verdict `contradicted`: the value must be named.

    31 sites over 50 km² in reference 8, 150 km² in the paper. A gate that says "a number
    is wrong" without saying which one cannot be acted on, so the assertion is on `150` in
    the detail.

    **The rule emitted is `located_sentence`, not `number_exact`, and that is A1's
    contract, not a choice here.** `claim_support.locate_support` accepts a window only
    when it carries *every* number, date and measurement of the claim, so a sentence whose
    number is sharpened does not locate at all - rule 1 refuses the marker first, and its
    detail names the values the source carries none of. `number_exact` is reachable only
    when a number is in the reference but not in the window that carries the sentence,
    which for the audited 31 is the 79 `contradicted` findings rather than the 858
    `unsupported` ones. The rule stays wired and its own test is below.
    """
    issues = check_paragraph_markers(SQUATTER_AREA, {"8": SQUATTER_REF08})
    located = [i for i in issues if i.rule in ("located_sentence", "unsupported_specific")]
    assert located, _rules(issues)
    assert "150" in "".join(i.detail for i in located)


def test_a_sharpened_number_never_reaches_number_exact_and_that_is_the_contract():
    """Rule 3 is wired, and `claim_support.locate_support` makes it unreachable.

    `locate_support` accepts a window only when it carries *every* number, date and
    measurement of the claim, so a sentence that sharpens a number does not locate at all
    and a sentence that does locate has all its numbers in the quote. `number_exact` can
    therefore never fire on a sharpened figure - the defect is reported by rule 1, which
    names the value, as the test above shows on the real squatter-man finding.

    This test pins that fact on the same real finding rather than on an invented paragraph,
    so the subsumption is visible in the suite instead of looking like a working rule.
    """
    issues = check_paragraph_markers(SQUATTER_AREA, {"8": SQUATTER_REF08})
    assert "number_exact" not in _rules(issues), _rules(issues)
    assert "unsupported_specific" in _rules(issues)


def test_the_same_number_on_the_reference_that_carries_it_is_not_an_issue():
    """The control: the paragraph's own figure is not reported when the quote carries it.

    The gate's answer is per marker, which is what lets it say *which* reference must
    carry the number - exactly the repair the audit applied
    ("...over 50 square kilometers, within a 150 square kilometer area[7][8]").
    """
    issues = check_paragraph_markers(SQUATTER_AREA.replace("[8]", "[7]"), {"7": SQUATTER_REF07})
    assert not [i for i in issues if "150" in i.detail and i.rule != "unsupported_specific"], [
        (i.rule, i.detail) for i in issues
    ]


# ---------------------------------------------------------------------------
# Rule 4 - site_code
# ---------------------------------------------------------------------------


def test_la_11568_in_prose_with_no_source_carrying_it():
    """mogollon, class C: the code is in the paper's references, not in the one it cites.

    The rule is that a site code is copied from the fetched record, never recalled, and
    this is the mechanical half of that: the string is either in a cited source or it is
    not. The semantic half - whether the source also equates Mogollon Village with the SU
    Site - is not decidable from strings and is out of scope, as the module says.
    """
    issues = check_paragraph_markers(MOGOLLON_VILLAGE, {"1": MOGOLLON_REF01})
    codes = [i for i in issues if i.rule == "site_code"]
    assert codes, _rules(issues)
    assert "LA 11568" in codes[0].detail


def test_the_same_code_on_the_reference_that_carries_it_is_not_an_issue():
    """The control: reference 4 is the paper whose title is "Mogollon Village (LA 11568)"."""
    issues = check_paragraph_markers(
        MOGOLLON_VILLAGE.replace("[1]", "[4]"), {"4": MOGOLLON_REF04}
    )
    assert "site_code" not in _rules(issues), _rules(issues)


# ---------------------------------------------------------------------------
# Rule 5 - identifier
# ---------------------------------------------------------------------------


def test_a_doi_in_the_prose_that_no_cited_source_carries():
    """stargate finding [28] / report section E: a DOI written from memory.

    The real case is a reference the audit could only recover by searching for its title
    after two DOIs had been written wrongly. What the gate can decide is the mechanical
    half: the identifier in the prose is in none of the texts the paragraph cites.
    """
    issues = check_paragraph_markers(STARGATE_WRONG_DOI, {"17": STARGATE_REF17_PEAR})
    identifiers = [i for i in issues if i.rule == "identifier"]
    assert identifiers, _rules(issues)
    assert "10.3389/fpsyg.2012.00390" in identifiers[0].detail


# ---------------------------------------------------------------------------
# Rule 6 - retraction
# ---------------------------------------------------------------------------


def test_a_quotation_the_source_does_not_hold_verbatim_is_not_located():
    """stargate audit finding [12], verdict `misattributed`: a de-hyphenated quotation.

    The paper prints the AIR verdict as one word, "in no case had the information provided";
    the fetched text has the line-break hyphen the PDF carries, "informa- tion". The
    quotation is presented as the source's words and it is not the source's words, so
    reference 9 does not carry the sentence and the marker is refused.
    """
    issues = check_paragraph_markers(STARGATE_AIR_DEHYPHENATED, {"9": STARGATE_REF09})
    located = [i for i in issues if i.rule == "located_sentence"]
    assert located, _rules(issues)
    assert located[0].marker == "[9]"


def test_a_retraction_claim_whose_located_quote_lacks_the_word():
    """stargate audit finding [15], class E: a retraction that does not exist.

    Two real stargate sentences, cited on reference 9: the AIR evaluation verdict, spelled
    the way the fetched text spells it so the marker locates, and the Bem retraction claim,
    which ref09 does not make - the audit's note reads "It contains no Wiseman, no Milton,
    no 'Experiment One', no 'Feeling the Future' and no Daryl Bem." A retraction is a claim
    about the bibliographic record, and the record in front of the reader does not say it.

    The rule is reachable only in this shape. Rule 6 needs a paragraph that locates *and*
    asserts a retraction; a retraction claim on a paragraph nothing carries is rule 1's
    business, and the audited stargate paragraph is in that second class.
    """
    issues = check_paragraph_markers(STARGATE_AIR_AND_RETRACTION, {"9": STARGATE_REF09})
    assert "located_sentence" not in _rules(issues), _rules(issues)
    retractions = [i for i in issues if i.rule == "retraction"]
    assert retractions, _rules(issues)
    assert retractions[0].marker == "[9]"
    assert "retract" in retractions[0].detail.lower()


def test_a_retraction_the_source_states_is_not_an_issue():
    """The control: the same sentence, with a source that does use the word, is supported."""
    reported = (
        "The Feeling the Future paper was retracted in 2011 after a multi-site "
        "preregistered replication attempt reported null results. [9]"
    )
    source = (
        "The Feeling the Future paper was retracted in 2011 after a large-scale "
        "preregistered replication attempt reported null results; the retraction notice "
        "remains on the journal record."
    )
    issues = check_paragraph_markers(reported, {"9": source})
    assert "retraction" not in _rules(issues), _rules(issues)


# ---------------------------------------------------------------------------
# Rules 1 and 5: a year in the prose that its source does not carry
# ---------------------------------------------------------------------------


def test_a_year_in_the_prose_that_its_source_does_not_carry_reports_the_year():
    """ufos audit finding, fix kind `replace_date`: 1997 where the record is 1998.

    **The rule asserted is the one that names the year in its detail**, which is now
    `unsupported_specific` (the marker's own sentence does not locate, and the value is
    named). Not `identifier`: that rule covers a DOI, an ISBN or a PMID, and a year is none
    of those, so `claim_identifiers` cannot return it. And not `number_exact`: `locate_support`
    requires a window to carry every date and number of the claim, so a claim with a wrong
    year in it does not locate at all - which is the same mechanism as the squatter number,
    and the detail names the value so the year is still the actionable part of the report.
    """
    issues = check_paragraph_markers(UFOS_STURROCK, {"38": UFOS_REF38})
    assert "identifier" not in _rules(issues), _rules(issues)
    located = [
        i for i in issues if i.rule in ("located_sentence", "unsupported_specific")
    ]
    assert located, _rules(issues)
    assert "1997" in "".join(i.detail for i in located)


def test_the_audit_repair_is_not_yet_decidable_either():
    """ufos: even the corrected year is not in the fetched text, so rule 1 still fires.

    The audit's fix is 1998 and the fetched reference 38 contains neither 1997 nor 1998 - it
    is the review's own narrative, undated. So the repair cannot be certified from the
    fetched text alone, which is the honest state of this finding: the year is in the
    bibliographic record, and the record is a different artefact from the source text.
    """
    fixed = UFOS_STURROCK.replace("The 1997 Sturrock Panel", "The 1998 Sturrock Panel")
    assert "1998" not in UFOS_REF38
    issues = check_paragraph_markers(fixed, {"38": UFOS_REF38})
    assert "identifier" not in _rules(issues), _rules(issues)


def test_a_wrong_year_that_the_source_also_contains_is_not_reported():
    """stargate finding [6], a measured false negative of the rules above.

    The paper says 2022 where the record's own year is 2023, which is a real defect the
    audit fixed with `replace_date`. Neither rule 3 nor rule 1 sees it: reference 6's title
    is "A 1974-2022 Systematic Review and Meta-Analysis", so the paper's 2022 *is* in the
    source, legitimately, and a containment test cannot tell that occurrence from the wrong
    one. `identifier` cannot see it either - a year is not a DOI, an ISBN or a PMID.

    Measured over the campaign's 24 `replace_date` findings, this is the common shape, not
    the exception: the wrong year usually occurs somewhere in the fetched text. The
    `ufos` panel above is the one the containment check can decide. Catching the rest needs
    a date-aware comparison against the record's own year field, not a numeric one.

    The class-E coverage that does work mechanically is the DOI test above: the same failure
    mode - an identifier recalled instead of copied - with a decidable string.
    """
    issues = check_paragraph_markers(STARGATE_YEAR_2022, {"6": STARGATE_JSE_RECORD})
    assert "identifier" not in _rules(issues), _rules(issues)
    assert not [i for i in issues if "2022" in i.detail], [
        (i.rule, i.detail) for i in issues
    ]


# ---------------------------------------------------------------------------
# Rule 7 - sentence_defect
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "text", "seam"),
    [
        (
            "cargo-cults, sentence cut mid-clause (report section F, first of two)",
            SEAM_CARGO_CULTS_FRAGMENT,
            "a pattern of colonial violence that.",
        ),
        (
            "phaeton, no full stop after a marker",
            SEAM_PHAETON_NO_STOP,
            "initial state [52] The",
        ),
        (
            "watchers-nephilim, comma left in front of the full stop",
            SEAM_WATCHERS_COMMA,
            "consensus [11],.",
        ),
        (
            "reincarnation, doubled full stop",
            SEAM_REINCARNATION_DOUBLE_STOP,
            "roughly 16 months..",
        ),
        (
            "pineal-dmt, a replacement that swallowed its full stop",
            SEAM_PINEAL_MARKER_SWALLOWED,
            "neurotransmitters[7].",
        ),
    ],
)
def test_each_shipped_structural_defect_is_reported(label, text, seam):
    """Report section F: the four text seams it quotes verbatim, one fixture each.

    The assertion is on the rule id and on the defect's own text appearing in the detail,
    not on `claim_support`'s kind vocabulary - the kind names are A1's to choose, and this
    side of the contract is that a defect is reported and that the reader can see it.

    The report's class-F table lists six. Two are not in this list, each for a reason the
    tests below state: the orphan-reference defect belongs to `validate_paper_artifact`,
    and the second cargo-cults fragment is a gap in `claim_support`'s word list.
    """
    issues = check_sentence_structure(text)
    defects = [i for i in issues if i.rule == "sentence_defect"]
    assert defects, f"{label}: no sentence_defect, got {_rules(issues)}"
    assert any(seam in issue.detail for issue in defects), (
        f"{label}: no defect quotes {seam!r}; "
        + " | ".join(issue.detail for issue in defects)
    )


def test_the_second_cargo_cults_fragment_is_a_gap_in_claim_support_not_here():
    """The report's other cargo-cults seam, "attack the people they." - measured, not caught.

    The report quotes two cargo-cults fragments among the six that shipped; the first ends
    on "that" and is reported, the second ends on "they" and is not. `sentence_defects`
    matches the sentence's last word against a closed list, and that list has the
    prepositions, the conjunctions and the articles but not the pronouns - `they`, `them`,
    `it`, `this` and `those` all miss. This is `pipeline/lyra/claim_support.py`, work
    package A1's file, so the gate forwards what it is given; the test pins the gap so it
    is visible in this repository's own suite rather than assumed away.
    """
    issues = check_sentence_structure(SEAM_CARGO_CULTS_FRAGMENT_2)
    assert issues == [], [(i.rule, i.detail) for i in issues]


def test_the_orphan_reference_defect_is_already_the_artifact_gates():
    """phaeton, the sixth class-F defect, is `validate_paper_artifact`'s `orphaned_refs`.

    Measured against the production gate: it answers `passed: False` with "[50] cited in
    text but not in the rendered References list". The report's class-F table lists this
    among the defects the gate does not see; that half of the table is wrong, and the
    sentence check is the wrong place to put the rule.
    """
    from pipeline.lyra.theo_citations import validate_paper_artifact

    verdict = validate_paper_artifact(SEAM_PHAETON_MISSING_REF_LINE)
    assert verdict["passed"] is False
    assert any("[50] cited in text but not in the rendered References list" in i
               for i in verdict["issues"]), verdict["issues"]


def test_a_clean_paragraph_has_no_structural_defect():
    """The control for the seven above."""
    assert check_sentence_structure(BAALBEK_HEROD) == []


def test_the_marker_of_a_seam_is_carried_on_the_issue():
    """A defect about a marker names that marker, so a writer can find it in the text."""
    issues = check_sentence_structure(SEAM_PHAETON_NO_STOP)
    assert [i.marker for i in issues] == ["[52]"], [(i.rule, i.marker) for i in issues]


# ---------------------------------------------------------------------------
# Rule 1's boundary: verifiable content or nothing
# ---------------------------------------------------------------------------

# The studio fixture's padding sentence, verbatim from
# tests/pipeline/studio/fixtures.py: repeated to reach the 5,000-word floor, and carrying a
# marker. It is here because it is what a marker on a claim-free sentence does: nothing.
# It is not a class-A finding and must never become one.
PADDING_SENTENCE = (
    "The block rests where the workers left it and the stone still shows the marks of the "
    "tools that cut it from the hill. [1]"
)
# The archive text the studio fixture cites it on. It carries none of the sentence's
# particulars, because the sentence has none.
PADDING_SOURCE = (
    "The trilithon was quarried at the quarry to the south of the sanctuary and dragged "
    "into place on rollers. The soffits of the podium carry no tooling marks."
)


def test_a_sentence_with_no_verifiable_content_is_not_a_citation_failure():
    """A marker on a sentence that asserts nothing checkable is undecidable, not wrong.

    `locate_support` needs two matched specifics before it accepts a window, so it returns
    `None` for a sentence with no specifics at all. That `None` means "nothing to decide",
    and the gate must not turn it into a class-A finding: the defect would be padding, which
    the word count and the writer own, and a gate that fires on padding is a gate whose
    output stops being read.
    """
    issues = check_paragraph_markers(PADDING_SENTENCE, {"1": PADDING_SOURCE})
    assert "located_sentence" not in _rules(issues), _rules(issues)


def test_one_number_the_source_lacks_makes_the_same_shape_a_finding():
    """The other side of the boundary: a single number the source does not carry.

    Same marker, same reference, same sentence shape - the difference is the one number.
    That is the whole distinction: whether the sentence holds something a fetched text could
    have carried and did not.
    """
    with_number = (
        "The trilithon was quarried 900 metres from the sanctuary and dragged into place on "
        "rollers. [1]"
    )
    issues = check_paragraph_markers(with_number, {"1": PADDING_SOURCE})
    located = [i for i in issues if i.rule in ("located_sentence", "unsupported_specific")]
    assert located, _rules(issues)
    assert "900" in "".join(i.detail for i in located)


def test_a_padding_paragraph_on_an_unreadable_reference_is_still_reported():
    """Rule 2 is about the reference, not the sentence, so padding does not excuse it.

    "This reference could not be read" stays true whatever the paragraph says, and the
    report's rule is that a reference nobody fetched may not carry a marker at all.
    """
    issues = check_paragraph_markers(PADDING_SENTENCE, {"1": ""})
    unreadable = [i for i in issues if i.rule == "unreadable_marker"]
    assert unreadable, _rules(issues)
    assert unreadable[0].marker == "[1]"


def test_a_quotation_counts_as_verifiable_content():
    """A quotation is checkable content: the source either holds those words or it does not.

    This is the stargate de-hyphenation case - a sentence whose only specific is a
    quotation, and the fetched text's line-break hyphen is enough to make the marker a
    finding rather than padding.
    """
    assert check_paragraph_markers(PADDING_SENTENCE, {"1": PADDING_SOURCE}) == []
    assert "located_sentence" in _rules(
        check_paragraph_markers(STARGATE_AIR_DEHYPHENATED, {"9": STARGATE_REF09})
    )


# ---------------------------------------------------------------------------
# The false-positive guard
# ---------------------------------------------------------------------------


def test_a_supported_paragraph_with_its_source_reports_nothing():
    """baalbek finding [25], verdict `supported`, no fix - the audit changed nothing here.

    This is the most important test in the file. The gate refuses 1 503 of 2 105 audited
    claims; a gate that refuses a claim the auditor left alone has no value, because a
    writer would stop reading its output. The source text here is the audit's own
    `source_quote` for the finding, so every number in the prose is in the source exactly
    as the source writes it, and the paragraph carries exactly one readable marker.
    """
    issues = check_paragraph_markers(BAALBEK_HEROD, {"14": BAALBEK_REF14})
    assert issues == [], [(i.rule, i.detail) for i in issues]


def test_the_supported_paragraph_adds_no_marker_issue_through_check_paper():
    """The same paragraph through the full gate: nothing but a structural defect, if any.

    `check_paper` adds rule 7, whose vocabulary belongs to `claim_support`; the assertion
    is that rules 1-6 and 8 add nothing on top.
    """
    issues = check_paper(BAALBEK_HEROD, {"14": BAALBEK_REF14})
    assert [i for i in issues if i.rule != "sentence_defect"] == [], [
        (i.rule, i.detail) for i in issues
    ]


# ---------------------------------------------------------------------------
# The paragraph walk
# ---------------------------------------------------------------------------


def test_a_picture_is_not_reported_as_prose():
    """The report's measurement trap, reproduced.

    A naive block count calls this two pictures' worth of stored text three prose
    paragraphs each and then reports half the paper as uncited. `report_paragraphs` is the
    walk the publish gate already uses, so the image line, the italic caption and the
    `[Source](url)` trailer are out of scope before any rule runs - and the prose after the
    picture keeps its index, which is what an issue's `paragraph` must mean.
    """
    from pipeline.lyra.theo_publishing import report_paragraphs

    paragraphs = report_paragraphs(BAALBEK_WITH_PICTURE)
    assert len(paragraphs) == 2, [p[:60] for p in paragraphs]
    assert paragraphs[1] == BAALBEK_HEROD

    issues = check_paper(BAALBEK_WITH_PICTURE, {"14": BAALBEK_REF14})
    assert [i for i in issues if i.rule != "sentence_defect"] == [], [
        (i.rule, i.detail) for i in issues
    ]


def test_the_reference_lines_are_not_prose_either():
    """`[14] A BMCR review of Adam (1977) — https://...` is a bibliography line, not prose.

    If it counted, the gate would check the reference list's own text against the reference
    list and report every bibliographic fact as unsupported.
    """
    from pipeline.lyra.theo_publishing import report_paragraphs

    paragraphs = report_paragraphs(BAALBEK_WITH_PICTURE)
    assert not any(p.startswith("[14] A BMCR") for p in paragraphs)


def test_a_paragraph_with_no_marker_is_left_to_the_artifact_gate():
    """Uncited prose is `validate_paper_artifact`'s `uncited_paragraphs`, not this gate's.

    With no cited source there is nothing to trace a claim against, and checking anyway
    would report every proper noun in the paragraph as unsupported - a second, noisier copy
    of a defect another gate already reports by name.
    """
    report = "The Triton statue stood at the sanctuary's eastern end."
    assert check_paragraph_markers(report, {"14": BAALBEK_REF14}) == []


# ---------------------------------------------------------------------------
# The key types and the reporting order
# ---------------------------------------------------------------------------


def test_source_texts_accepts_string_and_int_keys():
    """A report's markers are strings and the studio's registry is keyed by int.

    The pineal scale claim marked [12], the claim it really is, carried with the same text
    under an int key, must produce the same result as the string key.
    """
    as_string = check_paragraph_markers(
        PINEAL_SCALE.replace("[11]", "[12]"), {"12": PINEAL_LAWRENCE_2022}
    )
    as_int = check_paragraph_markers(
        PINEAL_SCALE.replace("[11]", "[12]"), {12: PINEAL_LAWRENCE_2022}
    )
    assert as_string == as_int
    assert [i.rule for i in as_int] == ["unsupported_specific"] * 3


def test_mixed_string_and_int_keys_resolve_to_the_same_reference():
    """A registry that mixes both is one registry, not two half-empty ones.

    The two unreadable references are keyed by int and the readable one by string, so a
    gate that normalised only one of the two would report [2] and [7] as located.
    """
    mixed = check_paragraph_markers(
        BAALBEK_TRILITHON, {2: "", "6": BAALBEK_REF06, 7: "   ", "8": BAALBEK_REF06}
    )
    assert [i.marker for i in mixed if i.rule == "unreadable_marker"] == ["[2]", "[7]"]


def test_issues_are_reported_in_rule_order():
    """The order the rules are documented in is the order a reader gets them in."""
    report = (
        BAALBEK_TRILITHON
        + "\n\n"
        + MOGOLLON_VILLAGE
        + "\n\n"
        + "The interval was estimated at roughly 16 months..\n"
    )
    issues = check_paper(
        report,
        {
            "1": MOGOLLON_REF01,
            "6": BAALBEK_REF06,
            "7": SQUATTER_REF08,
            "8": SQUATTER_REF07,
        },
    )
    ranks = [RULE_ORDER.index(issue.rule) for issue in issues]
    assert ranks == sorted(ranks), [issue.rule for issue in issues]
    assert len(ranks) > 1, "the fixture must trip more than one rule to mean anything"


def test_paragraph_indices_are_report_paragraph_indices():
    """An issue's `paragraph` is the index a writer uses to find the paragraph.

    It is the same index space the evidence anchors and the studio's `anchors.paragraphs`
    use, so an issue needs no second walk of the paper to be acted on. The mogollon
    paragraph is index 0 and the clean one index 1; only the first produces an issue, and
    it carries 0.
    """
    from pipeline.lyra.theo_publishing import report_paragraphs

    two = MOGOLLON_VILLAGE + "\n\n" + BAALBEK_HEROD
    assert len(report_paragraphs(two)) == 2
    found = check_paragraph_markers(two, {"1": MOGOLLON_REF01, "14": BAALBEK_REF14})
    assert {i.paragraph for i in found} == {0}, [(i.rule, i.paragraph) for i in found]


def test_check_paper_is_the_two_checks_merged():
    """`check_paper` is `check_paragraph_markers` + `check_sentence_structure`, in rule order."""
    report = SEAM_REINCARNATION_DOUBLE_STOP + " " + BAALBEK_TRILITHON
    texts = {"2": "", "6": BAALBEK_REF06, "7": "   ", "8": BAALBEK_REF06}
    markers = check_paragraph_markers(report, texts)
    structure = check_sentence_structure(report)
    assert set(check_paper(report, texts)) == set(markers) | set(structure)
