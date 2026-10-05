"""The sentence-level evidence card: one entry per sentence, the paragraph's refs, a quote
located in a source text, and no change to the paper.

Every literal below is copied from the audited papers in `C:\\tmp\\papers` and named in a
comment; no test reads that directory at run time. The two papers are the baalbek paper
(`02515a7a-2097-409d-8288-1da5f2a72216`, `live.md` and the fetched `refNN.txt` texts), the
stargate paper (`099ad920-2e52-4180-915c-c040d316f3d7`) and the pineal-dmt and cargo-cults
papers (`4486b29c-8773-4b49-ab74-f7832426e88e`, `a00c4ee2-0162-4bfe-997f-72f7ac3457fc`,
both `corrected.md`, the text that shipped).
"""

from __future__ import annotations

import json

from pipeline.studio.paper.anchors import MARKER_RE
from pipeline.studio.paper.evidence_card import VERSION, SentenceSupport, build_evidence_card

# baalbek, live.md: the h2 and paragraphs 2 and 3 verbatim, with the real image block that
# sits between them - the three stored blocks (image, caption, [Source]) that a naive
# paragraph count reads as prose (the measurement trap of the defect report).
BAALBEK_REPORT = """## Alfvén's Plasma Universe and the Birkeland Current Legacy

For this body of work on magnetohydrodynamics, Alfvén received the 1970 Nobel Prize in Physics — the formal citation crediting him "for fundamental work and discoveries in magnetohydrodynamics with fruitful applications in different parts of plasma physics". [4] [5] [6] [7] [8] [9]

![Jupiter.Aurora.HST.UV](/data/research-images/02515a7a-2097-409d-8288-1da5f2a72216/p2_coronal_heating_TRACE_observat.jpg)

*Illustration: Jupiter.Aurora.HST.UV. Photo: NASA, ESA &amp; John T. Clarke (Univ. of Michigan) / Wikimedia Commons.*
[Source](https://commons.wikimedia.org/wiki/File:Jupiter.Aurora.HST.UV.jpg)

The story of field-aligned currents — what we now call Birkeland currents — runs through the same vein of vindication-by-instrument. Norwegian physicist Kristian Birkeland proposed in 1902–1903, on the basis of high-latitude expeditions and terrella experiments, that aurora and polar magnetic disturbances were caused by electric currents flowing along geomagnetic field lines into and away from the atmosphere. Sydney Chapman argued for decades that such currents could not cross the vacuum of space, and the paper in which Alfvén developed the theoretical framework in 1939 was rejected by the Journal of Geophysical Research because it disagreed with Chapman's theories. Chapman died in 1970. Four years later, satellite measurements confirmed the current systems he had rejected. [7] [8] [10]
"""

BAALBEK_SECTION = "Alfvén's Plasma Universe and the Birkeland Current Legacy"

# baalbek ref07.txt (the Lindau Mediatheque research profile, reference [7]), characters
# 5600-6200 of the fetched text. It carries the specifics of the paper's Birkeland sentence -
# "Kristian Birkeland" and "1902-1903" - so `locate_support` places that sentence here; in the
# whole ref07.txt the located quote starts at character 5708, at 108 of this excerpt.
BAALBEK_REF07 = (
    "cs of the space between the Sun and the Earth also began at this time, with a paper on "
    "the aurora borealis. The electrical nature of the aurora and the major role played by "
    "the Earth's magnetic field had already been established by the Norwegian physicist "
    "Kristian Birkeland, who first elucidated the nature of the aurora borealis during "
    "expeditions to high-latitude regions, organised in 1902-1903. He established a network "
    "of observatories to collect magnetic field data and at the beginning of the 20th century "
    "proposed that aurora and polar electric disturbances were caused by a system of curren"
)

# The same paper's sentences of paragraph 3. The paper paraphrases: neither shares a long run
# of words with the source, which is why the card records a quote and not a verdict.
BIRKELAND_SENTENCE = (
    "Norwegian physicist Kristian Birkeland proposed in 1902–1903, on the basis of "
    "high-latitude expeditions and terrella experiments, that aurora and polar magnetic "
    "disturbances were caused by electric currents flowing along geomagnetic field lines "
    "into and away from the atmosphere."
)
CHAPMAN_SENTENCE = (
    "Sydney Chapman argued for decades that such currents could not cross the vacuum of space, "
    "and the paper in which Alfvén developed the theoretical framework in 1939 was rejected by "
    "the Journal of Geophysical Research because it disagreed with Chapman's theories."
)

# baalbek ref01.txt (the universeofparticles.com page, reference [1]), its fetch header and
# its first paragraphs, verbatim. The excerpt stops before the Birkeland paragraph, which
# holds a no-break space (U+00A0) in "the late 19 th<U+00A0>century" - a real character a
# card has to index by, not by byte. No word of UNSUPPORTED_SENTENCE occurs here, not even
# as a run of two, and `locate_support` returns None for it against the whole ref01.txt as
# well (measured 2026-10-04): that sentence is the audit's class A, a true-sounding sentence
# hung on a source that does not carry it.
BAALBEK_REF01 = """SOURCE: https://www.universeofparticles.com/the-electric-universe/
HTTP: 200
CHARS: 4271

Skip to content

Universe of Particles

Open mobile menu Close mobile menu

The Electric Universe

In the physics laid out in this book, gravity takes a side-role to electricity. Gravity is due to a tiny imbalance in the electrical force. It’s of little importance in monumental events, such as those described in the chapters above.

Gravity is only a significant force when there’s electric stability . It’s therefore a mistake to assume that what we see in the universe is primarily due to gravity."""
# baalbek, live.md paragraph 0: three sentences, one paragraph-level marker.
BAALBEK_HOOK_PARAGRAPH = (
    "In 1950, Immanuel Velikovsky published *Worlds in Collision* — a book built around the "
    "claim that the planets had behaved catastrophically within recorded history. Astronomers "
    "demolished its orbital mechanics, but the book refused burial. Twenty-two years later, the "
    'small journal *Pensée* ran Ralph Juergens\'s paper "The Electric Sun," arguing that our '
    "star runs on external galactic current rather than internal fusion — and in the Electric "
    "Universe literature, Juergens stands as the explicitly named bridge between Velikovsky and "
    "the modern movement of Wallace Thornhill and David Talbott. [1]"
)
UNSUPPORTED_SENTENCE = "Astronomers demolished its orbital mechanics, but the book refused burial."

# stargate, live.md paragraphs 0 and 2 verbatim, the first placed before an h2 so the card
# sees it as the hook. Every audited paper opens with its title as an h1 or an h2, so no
# shipped paper has a hook paragraph; the shape is the one `numbering.compose` leaves when a
# draft starts with prose.
STARGATE_REPORT = """At 8:00 p.m. Central Standard Time on April 27, 1973, at the Stanford Research Institute in Menlo Park, California, an artist and author named Ingo Swann settled in for a remote-viewing session arranged by a mysterious "Mr. Sherman" and aimed his attention at Jupiter. What he described over the next hour startled the physicists watching over him: a ring encircling the gas giant, so unexpected that Swann himself wondered whether he had accidentally drifted to Saturn. NASA's Pioneer 10 flyby subsequently confirmed that Jupiter did, in fact, have rings, and the episode has been cited in parapsychology literature ever since as a successful case of pre-confirmation anomalous cognition. [1]

## Findings

The U.S. government–sponsored psi research effort now generically referred to as the Stargate Project emerged in 1972 under the Defense Intelligence Agency, with the program's laboratory component contracted to Stanford Research Institute (SRI) and its operational component eventually moved to Fort Meade, Maryland. The SRI remote-viewing research was led by physicists Hal Puthoff and Russell Targ working with 'gifted subjects' including Pat Price and Ingo Swann. Start and end dates are reported inconsistently across sources as 1975–1995 or 1977–1995, with earlier DIA assessment activity dating to 1972. [3]
"""

# pineal-dmt, corrected.md paragraph 18 verbatim: multi-byte transliteration throughout
# (Ṣaṭ-chakra-nirūpaṇa, Pūrṇānanda, Śrītattvacintāmaṣī), em dashes, and a marker written
# without a space (cerebellum[42]).
PINEAL_REPORT = """## The Eye of Horus, Ajna Chakra, and the Cross-Cultural Third Eye

The canonical textual description comes from the Ṣaṭ-chakra-nirūpaṇa, a section of Pūrṇānanda Yati's Śrītattvacintāmaṣī, composed in 1577 CE and translated by John Woodroffe in 1919 as The Serpent Power. That predates any Western glandular identification of the gland: Woodroffe's 1919 edition of the text places the Ajna frontally in the space between the eyebrows and, at the back, with the pineal gland, the pituitary body and the top of the cerebellum[42]. Buddhist and Taoist traditions register analogous but independent concepts — the "Eye of Wisdom" or "Divine Eye" in Buddhism, linked to the doctrine of emptiness, and the "upper dantian" between the eyebrows in Taoism, a focus of meditation and qi cultivation — none of which originally couple the metaphor to a glandular location. [26]
"""
PINEAL_SENTENCES = [
    "The canonical textual description comes from the Ṣaṭ-chakra-nirūpaṇa, a section of "
    "Pūrṇānanda Yati's Śrītattvacintāmaṣī, composed in 1577 CE and translated by John "
    "Woodroffe in 1919 as The Serpent Power.",
    "That predates any Western glandular identification of the gland: Woodroffe's 1919 edition "
    "of the text places the Ajna frontally in the space between the eyebrows and, at the back, "
    "with the pineal gland, the pituitary body and the top of the cerebellum.",
    'Buddhist and Taoist traditions register analogous but independent concepts — the "Eye of '
    'Wisdom" or "Divine Eye" in Buddhism, linked to the doctrine of emptiness, and the '
    '"upper dantian" between the eyebrows in Taoism, a focus of meditation and qi cultivation '
    "— none of which originally couple the metaphor to a glandular location.",
]

# cargo-cults, corrected.md paragraph 26, the sentence the audit caught merging the North
# Andaman Jurua with the South Andaman Juruwin (class C).
JURUA_SENTENCE = (
    "Radcliffe-Brown's 1906 study of the Andamanese records the sea-spirits directly: in the "
    "North Andaman they are called Jurua, and among the Aka-Bea of the South Andaman Juruwin — "
    "'the name not of a single individual but of a class of supernatural beings of which there "
    "is an indefinite number' — which devour those 'drowned or buried at sea' and attack people "
    "found fishing"
)


def has_run(sentence: str, text: str, words: int = 2) -> bool:
    """True when `words` consecutive words of `sentence` occur in `text` (case-insensitive).

    The premise of the two fixtures below, kept in the test so a re-typed literal that stops
    matching its source text fails here instead of quietly changing what the card is asked.
    """
    parts = sentence.split()
    return any(
        " ".join(parts[i : i + words]).lower() in text.lower()
        for i in range(len(parts) - words + 1)
    )


def sentences_of(card: dict, index: int = 0) -> list[dict]:
    return card["paragraphs"][index]["sentences"]


def test_one_entry_per_sentence_in_reading_order_with_its_section():
    card = build_evidence_card(BAALBEK_REPORT, {})
    assert card["version"] == VERSION
    assert [(p["index"], p["section"]) for p in card["paragraphs"]] == [
        (0, BAALBEK_SECTION),
        (1, BAALBEK_SECTION),
    ]
    assert [s["sentence"] for s in sentences_of(card, 0)] == [
        "For this body of work on magnetohydrodynamics, Alfvén received the 1970 Nobel Prize "
        'in Physics — the formal citation crediting him "for fundamental work and discoveries '
        "in magnetohydrodynamics with fruitful applications in different parts of plasma "
        'physics".'
    ]
    assert [s["sentence"] for s in sentences_of(card, 1)] == [
        "The story of field-aligned currents — what we now call Birkeland currents — runs "
        "through the same vein of vindication-by-instrument.",
        BIRKELAND_SENTENCE,
        CHAPMAN_SENTENCE,
        "Chapman died in 1970.",
        "Four years later, satellite measurements confirmed the current systems he had rejected.",
    ]
    # every entry names its own paragraph, and the offsets point back into the report
    for para in card["paragraphs"]:
        for row in para["sentences"]:
            assert row["paragraph"] == para["index"]
            assert row["section"] == BAALBEK_SECTION
            assert BAALBEK_REPORT[row["offset"] :].startswith(row["sentence"][:40])


def test_a_paragraph_citing_several_refs_gives_each_sentence_all_of_them():
    card = build_evidence_card(BAALBEK_REPORT, {})
    # the real paragraph writes its six markers as a run after the final full stop
    assert sentences_of(card, 0)[0]["refs"] == ["4", "5", "6", "7", "8", "9"]
    assert {tuple(s["refs"]) for s in sentences_of(card, 1)} == {("7", "8", "10")}


def test_a_marker_run_after_the_last_full_stop_is_not_a_sentence():
    """Every audited paragraph writes its markers as a run after the last full stop, and the
    sentence splitter cuts that run off as a piece of its own: 32 such pieces in the baalbek
    paper alone, one per paragraph. A piece that is nothing but a marker carries no claim, so
    it is no entry - the markers are in `refs`, nothing is lost and `unlocated` stays readable.
    """
    card = build_evidence_card(BAALBEK_REPORT, {})
    # "…different parts of plasma physics". [4] [5] [6] [7] [8] [9] is one sentence
    assert len(sentences_of(card, 0)) == 1
    assert sentences_of(card, 0)[0]["sentence"].endswith('different parts of plasma physics".')
    assert sentences_of(card, 0)[0]["refs"] == ["4", "5", "6", "7", "8", "9"]
    # "…the current systems he had rejected. [7] [8] [10]" is five sentences, not eight
    assert len(sentences_of(card, 1)) == 5
    assert all(row["sentence"] for row in sentences_of(card, 0) + sentences_of(card, 1))


def test_the_located_quote_is_a_contiguous_span_of_the_source_text():
    # the premise of the fixture, in the source text itself: the specifics the locator needs
    assert "Kristian Birkeland" in BAALBEK_REF07
    assert "organised in 1902-1903" in BAALBEK_REF07
    card = build_evidence_card(BAALBEK_REPORT, {"7": BAALBEK_REF07})
    row = sentences_of(card, 1)[1]
    assert row["sentence"] == BIRKELAND_SENTENCE
    assert row["quote_source"] == "7"  # the first of [7] [8] [10] whose text carries it
    assert row["quote"] in BAALBEK_REF07
    assert (
        BAALBEK_REF07[row["quote_start"] : row["quote_start"] + len(row["quote"])] == (row["quote"])
    )
    # a quote is a stretch of the source a reader can re-read, so it names what it supports
    assert "Kristian Birkeland" in row["quote"]
    assert "1902-1903" in row["quote"]


def test_a_sentence_no_cited_source_carries_is_unlocated_with_its_refs_named():
    report = BAALBEK_HOOK_PARAGRAPH + "\n"
    assert not has_run(UNSUPPORTED_SENTENCE, BAALBEK_REF01)
    card = build_evidence_card(report, {"1": BAALBEK_REF01})
    assert {
        "paragraph": 0,
        "sentence": UNSUPPORTED_SENTENCE,
        "refs": ["1"],
    } in card["unlocated"]
    row = next(s for s in sentences_of(card) if s["sentence"] == UNSUPPORTED_SENTENCE)
    assert row["quote"] == ""
    assert row["quote_source"] == ""
    assert row["quote_start"] == -1
    assert row["refs"] == ["1"]
    assert UNSUPPORTED_SENTENCE in [s["sentence"] for s in sentences_of(card)]


def test_a_ref_the_caller_holds_no_text_for_leaves_its_sentences_unlocated():
    """The audit's class D: a reference nobody could fetch may still carry a marker."""
    report = BAALBEK_REPORT[BAALBEK_REPORT.index("The story of") :]
    card = build_evidence_card(report, {"07": BAALBEK_REF07})  # the key is "7", not "07"
    assert card["counts"]["sentences"] == 5
    assert card["counts"]["located"] == 0
    assert card["counts"]["unlocated"] == 5
    assert {tuple(u["refs"]) for u in card["unlocated"]} == {("7", "8", "10")}
    # and the same text under the marker's own number does locate the sentence
    located = build_evidence_card(report, {"7": BAALBEK_REF07})
    row = sentences_of(located, 0)[1]
    assert row["sentence"] == BIRKELAND_SENTENCE
    assert row["quote_source"] == "7"
    assert (
        BAALBEK_REF07[row["quote_start"] : row["quote_start"] + len(row["quote"])] == row["quote"]
    )


def test_counts_are_internally_consistent():
    card = build_evidence_card(BAALBEK_REPORT, {"1": BAALBEK_REF01, "7": BAALBEK_REF07})
    counts = card["counts"]
    assert counts["sentences"] == sum(len(p["sentences"]) for p in card["paragraphs"]) == 6
    assert counts["located"] + counts["unlocated"] == counts["with_refs"]
    assert counts["with_refs"] + counts["sentences_without_refs"] == counts["sentences"]
    assert counts["unlocated"] == len(card["unlocated"])
    assert set(counts) == {
        "sentences",
        "with_refs",
        "located",
        "unlocated",
        "sentences_without_refs",
    }
    assert counts["sentences_without_refs"] == 0
    for row in card["unlocated"]:
        para = card["paragraphs"][row["paragraph"]]
        assert row["refs"] == sentences_of(card, row["paragraph"])[0]["refs"]
        assert row["sentence"] in [s["sentence"] for s in para["sentences"]]
        assert para["section"] == BAALBEK_SECTION


def test_building_the_card_leaves_the_report_byte_identical():
    before = BAALBEK_REPORT.encode("utf-8")
    card = build_evidence_card(BAALBEK_REPORT, {"1": BAALBEK_REF01, "7": BAALBEK_REF07})
    assert BAALBEK_REPORT.encode("utf-8") == before
    # the card is a plain result_json value, and it adds no marker of its own
    assert json.loads(json.dumps(card, ensure_ascii=False)) == card
    assert MARKER_RE.search(BAALBEK_REPORT)
    for para in card["paragraphs"]:
        for row in para["sentences"]:
            assert MARKER_RE.search(row["sentence"]) is None


def test_image_blocks_captions_and_source_lines_produce_no_entries():
    assert len(BAALBEK_REPORT.split("\n\n")) == 5  # h2, paragraph, image, caption, paragraph
    card = build_evidence_card(BAALBEK_REPORT, {"1": BAALBEK_REF01, "7": BAALBEK_REF07})
    assert len(card["paragraphs"]) == 2
    recorded = " ".join(row["sentence"] for para in card["paragraphs"] for row in para["sentences"])
    for stored in ("Illustration", "Jupiter.Aurora", "Wikimedia Commons", "Univ. of Michigan"):
        assert stored in BAALBEK_REPORT
        assert stored not in recorded
    assert all(
        BAALBEK_REPORT[row["offset"]] != "!"
        for para in card["paragraphs"]
        for row in para["sentences"]
    )


def test_a_hook_paragraph_before_the_first_h2_has_no_section():
    card = build_evidence_card(STARGATE_REPORT, {})
    assert [(p["index"], p["section"]) for p in card["paragraphs"]] == [(0, ""), (1, "Findings")]
    assert [s["section"] for s in sentences_of(card, 0)] == [""] * 3
    assert len(sentences_of(card, 0)) == 3
    assert len(sentences_of(card, 1)) == 3
    assert sentences_of(card, 0)[0]["sentence"].startswith("At 8:00 p.m. Central Standard Time")
    assert STARGATE_REPORT[sentences_of(card, 0)[1]["offset"] :].startswith("What he described")


def test_an_empty_report_a_report_of_headings_and_a_paragraph_with_no_refs():
    empty = build_evidence_card("", {})
    assert empty == {
        "version": VERSION,
        "paragraphs": [],
        "counts": {
            "sentences": 0,
            "with_refs": 0,
            "located": 0,
            "unlocated": 0,
            "sentences_without_refs": 0,
        },
        "unlocated": [],
    }
    headings = build_evidence_card("## Findings\n\n## References\n", {"1": BAALBEK_REF01})
    assert headings["paragraphs"] == []
    assert headings["counts"]["sentences"] == 0

    # the baalbek hook on its own: three sentences, no marker anywhere
    only_hook = build_evidence_card(BAALBEK_HOOK_PARAGRAPH.replace(" [1]", ""), {})
    assert only_hook["counts"] == {
        "sentences": 3,
        "with_refs": 0,
        "located": 0,
        "unlocated": 0,
        "sentences_without_refs": 3,
    }
    assert only_hook["unlocated"] == []
    assert only_hook["paragraphs"][0]["section"] == ""


def test_offsets_stay_correct_across_multi_byte_characters():
    card = build_evidence_card(PINEAL_REPORT, {})
    rows = sentences_of(card)
    assert [r["sentence"] for r in rows] == PINEAL_SENTENCES
    # the raw second sentence carries its marker on the word, between "cerebellum" and the
    # full stop, so the offset points at the sentence as the report writes it
    raw = [PINEAL_SENTENCES[0], PINEAL_SENTENCES[1][:-1] + "[42].", PINEAL_SENTENCES[2]]
    assert [r["offset"] for r in rows] == [PINEAL_REPORT.index(s) for s in raw]
    assert PINEAL_REPORT[rows[1]["offset"] :].startswith(raw[1])
    # the marker written without a space before it is gone from the sentence, and in `refs`
    assert rows[1]["sentence"].endswith("the top of the cerebellum.")
    assert rows[0]["refs"] == rows[1]["refs"] == ["42", "26"]

    # the same rule across a second paper, in a paragraph after another one
    report = f"{JURUA_SENTENCE} [34]\n\n{JURUA_SENTENCE} [34]\n"
    twin = build_evidence_card(report, {})
    assert [r["offset"] for r in sentences_of(twin, 0)] == [0]
    assert [r["offset"] for r in sentences_of(twin, 1)] == [report.index(JURUA_SENTENCE, 1)]
    assert sentences_of(twin, 1)[0]["sentence"] == JURUA_SENTENCE
    # the two identical paragraphs keep their own offsets and their own refs
    assert [r["refs"] for r in sentences_of(twin, 0)] == [["34"]]
    assert [r["refs"] for r in sentences_of(twin, 1)] == [["34"]]


def test_a_sentence_points_at_the_claim_task_that_judged_it():
    rows = sentences_of(build_evidence_card(BAALBEK_REPORT, {"7": BAALBEK_REF07}), 1)
    # a claim task id is "<kind>-<12 hex>" (studio.handoff.Task.task_id)
    card = build_evidence_card(
        BAALBEK_REPORT,
        {"7": BAALBEK_REF07},
        claim_task_ids={BIRKELAND_SENTENCE: "paragraph-1a2b3c4d5e6f"},
    )
    assert sentences_of(card, 1)[1]["claim_task_id"] == "paragraph-1a2b3c4d5e6f"
    assert {r["claim_task_id"] for r in sentences_of(card, 1)} == {
        "",
        "paragraph-1a2b3c4d5e6f",
    }
    assert {r["claim_task_id"] for r in rows} == {""}


def test_an_entry_holds_exactly_the_dataclass_fields():
    card = build_evidence_card(BAALBEK_REPORT, {})
    fields = list(SentenceSupport.__dataclass_fields__)
    for para in card["paragraphs"]:
        assert set(para) == {"index", "section", "sentences"}
        for row in para["sentences"]:
            assert list(row) == fields
