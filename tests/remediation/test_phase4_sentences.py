"""Does S2 number every sentence of a pinned text, offer exactly the spans the design names, and
never offer a span that carries a hedge, a negation or a restriction?

Work item WB-B2 (`scripts/remediation/phase4/sentences.py`). The mistakes worth a test are silent:
an offset one character off (the verifier would then compare the wrong slice), a sid that moves when
the pool is bounded, a span whose removal leaves `A, B` where `A B` was meant, an `according to` or
a `c.` offered for deletion, a reference section in the pool, a lane-S pool with a sentence about
the parent town. Each guard has a test that fails without it; the mutation cases are
`PHASE4_SELECT_MUTATIONS` in `scripts/remediation/phase3/mutation_sweep.py`. The texts are written
for the tests. Nothing here opens a socket or calls a model.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PHASE_PARENT = Path(__file__).resolve().parents[2] / "scripts" / "remediation"
if str(PHASE_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE_PARENT))

from phase4 import model4 as M  # noqa: E402
from phase4 import sentences as S  # noqa: E402
from phase4 import subject_gate as SG  # noqa: E402

from tests.remediation import p4_fixtures as X  # noqa: E402
from tests.remediation.p4_garble_cases import GARBLE_CASES  # noqa: E402
from tests.remediation.p4_span_cases import SPAN_CASES  # noqa: E402


def _one(text: str) -> M.Sentence:
    (sentence,) = S.split_source("W", text)
    return sentence


def _spans(text: str) -> dict[str, str]:
    """`span id -> the exact text of its range` for a one-sentence text."""
    return {span.id: text[span.start : span.end] for span in _one(text).spans}


# ------------------------------------------------------------------------------ numbering


def test_every_sentence_is_numbered_from_one_with_exact_offsets_and_its_section() -> None:
    sentences = S.split_source("W", X.ARTICLE)
    assert [s.index for s in sentences] == list(range(1, len(sentences) + 1))
    assert [s.sid for s in sentences][:3] == ["W1", "W2", "W3"]
    for sentence in sentences:
        piece = X.ARTICLE[sentence.start : sentence.end]
        assert piece == piece.strip() and piece
        assert "==" not in piece  # a heading line is never a sentence
    by_text = {X.ARTICLE[s.start : s.end]: s for s in sentences}
    assert by_text["The Stone Temple is a megalithic temple on the island of Gozo."].section is None
    assert by_text["A second shrine (the south shrine) was added later."].section == "History"


def test_a_circa_date_does_not_cut_a_sentence() -> None:
    texts = [X.ARTICLE[s.start : s.end] for s in S.split_source("W", X.ARTICLE)]
    assert (
        "The temple was built c. 2500 BC by a farming community, whose tombs lie nearby." in texts
    )


def test_a_sid_does_not_move_when_the_pool_is_bounded() -> None:
    sentences = S.split_source("W", X.ARTICLE)
    pool = S.candidate_pool(sentences, lane=M.Lane.W, names=["Stone Temple"], text=X.ARTICLE)
    assert {s.sid: s for s in sentences}["W10"] == {s.sid: s for s in pool}["W10"]


def test_a_non_selectable_source_is_refused() -> None:
    with pytest.raises(ValueError, match="not a selectable source"):
        S.split_source("R1", "A page sentence that is long enough to count.")


def test_another_language_source_gets_its_own_ids() -> None:
    sentences = S.split_source("T.fr", "Le temple est ancien et grand. Il fut fouille en 1911.")
    assert [s.sid for s in sentences] == ["T.fr1", "T.fr2"]


@pytest.mark.parametrize(
    ("source_id", "text"),
    [
        ("T.de", "Der Tempel wurde, was jedoch nicht belegt ist, von Bauern errichtet."),
        ("T.de", "Der Tempel wurde, vermutlich, von Bauern auf dem Hügel errichtet."),
        ("T.fr", "Le temple fut bâti par des paysans, ce qui n'est cependant pas prouvé."),
        ("T.es", "El templo fue construido, probablemente, por campesinos del valle."),
        ("T.it", "Il tempio fu costruito da contadini, ma questo non è dimostrato."),
    ],
)
def test_a_translated_source_offers_no_span(source_id: str, text: str) -> None:
    """The protected list is English: lane T selects whole sentences, so no foreign hedge can be
    dropped before the translator sees it."""
    (sentence,) = S.split_source(source_id, text)
    assert sentence.spans == ()
    assert S.split_source("W", text)[0].spans  # the same text in lane W would offer spans


@pytest.mark.parametrize(
    "heading",
    ["Einzelnachweise", "Literatur", "Weblinks", "Références", "Notes et références",
     "Bibliografía", "Enlaces externos", "Note", "Collegamenti esterni", "Referências",
     "Kaynakça", "Referències"],
)  # fmt: skip
def test_a_translated_sources_reference_section_is_never_in_the_pool(heading: str) -> None:
    text = (
        "Der Tempel steht auf einem Hügel über dem Fluss.\n"
        f"\n\n== {heading} ==\n\nDer Bericht über die Grabung erschien im Jahr 1911.\n"
    )
    pool = S.candidate_pool(S.split_source("T.de", text), lane=M.Lane.T, names=["X"], text=text)
    assert [S.sentence_text(text, s) for s in pool] == [
        "Der Tempel steht auf einem Hügel über dem Fluss."
    ]


# ---------------------------------------------------------------------------------- spans


def test_a_parenthesis_is_offered_with_the_space_in_front_of_it() -> None:
    text = "A second shrine (the south shrine) was added later."
    assert _spans(text) == {"p1": " (the south shrine)"}


def test_a_parenthesis_that_opens_the_sentence_takes_the_space_after_it() -> None:
    text = "(Built in stone) The shrine was added later on the hill."
    assert _spans(text)["p1"] == "(Built in stone) "


def test_a_paired_comma_insertion_takes_both_commas() -> None:
    text = "The temple, which stood on a low ridge, was used for a thousand years."
    spans = _spans(text)
    assert spans["a1"] == ", which stood on a low ridge,"
    span = next(s for s in _one(text).spans if s.id == "a1")
    assert text[: span.start] + text[span.end :] == "The temple was used for a thousand years."


def test_a_spaced_dash_pair_is_one_insertion() -> None:
    text = "The site lies 2 km south of the village – near the old road – on farmland."
    assert _spans(text) == {"a1": " – near the old road –"}


def _a_spans(text: str) -> set[str]:
    return {value for key, value in _spans(text).items() if key.startswith("a")}


def test_two_range_dashes_are_no_insertion() -> None:
    # Agri Bavnehøj W20: dropping "– 500 BC, 100 –" read "from 1800 150 burial mounds".
    text = "In the period from 1800 – 500 BC, 100 – 150 burial mounds were built every year."
    assert not any(span.startswith(" –") for span in _a_spans(text))
    assert _a_spans("The mound – fully 12 m across – stands on the ridge above the ford.") == {
        " – fully 12 m across –"
    }  # a number inside the insertion is no range: only a digit next to a dash is
    # a digit after the first dash, and a digit before it
    assert _a_spans("The mound – 12 m across – stands on the ridge above the ford.") == set()
    assert _a_spans("The wall was built in 1200 – of local stone – on the ridge above.") == set()


def test_a_dash_pair_holding_a_semicolon_is_no_insertion() -> None:
    # Varna Necropolis W32: "type 1 – elongated barrel-shaped; type 2 –" gave type 1 type 2's shape.
    text = "The beads are of four kinds: type 1 – long; type 2 – faceted; type 3 – short; type 4 – round."
    assert _a_spans(text) == set()
    # the same shape with no digit next to a dash: only the semicolon refuses it
    assert _a_spans("The beads are long – barrel-shaped; the pendants – round and flat.") == set()
    # a semicolon inside a parenthesis is not at the top level
    assert _a_spans("The corridor – lined with slabs (granite; basalt) – rises to its end.") == {
        " – lined with slabs (granite; basalt) –"
    }


def test_an_unspaced_dash_delimits_nothing() -> None:
    """A range carries the space before its first dash; an unspaced dash has none to carry, and a
    range from the letter before it would cut a word."""
    assert _a_spans("The temple—the largest of its kind—stood on the hill above.") == set()


def test_a_closing_parenthesis_before_its_opening_offers_nothing() -> None:
    assert _spans("In 1900, the shrine) was added (later, on the hill top.") == {}


def test_dashes_pair_in_order_and_an_odd_count_pairs_none() -> None:
    text = "The corridor – lined with limestone – rises gently – lined with granite – to its end."
    assert _a_spans(text) == {" – lined with limestone –", " – lined with granite –"}
    route = "The fort lay on the road from Boulogne – Cologne and Xanten – Aachen – Trier."
    assert _a_spans(route) == set()


@pytest.mark.parametrize(
    "text",
    [
        # a serial list's last link: the text after the second comma opens with "and"/"or"
        "The temples of Asclepius, Aphrodite, Apollo, and Artemis stood on the hill.",
        "The temple held statues of the goddess of the harvest, the god of the sea, and the god of war.",
        # a short item before a short tail that carries the coordinator
        "Finds from the ditch included pottery, coins, tools and bones from the pit.",
        # a run of short items that ends in a list link
        "It lies in the provinces of Nevsehir, Kayseri, Aksaray, Kirsehir, Sivas and Nigde.",
        # an asyndetic tail (Bela Palanka W11) and a place chain
        "The coins were minted under the rule of Constantine I, Theodosius I, Tiberius Nero.",
        "The hill fort lies near the village of Clovelly, Devon, England.",
        # a conjunct: the pair's own text opens with "and"/"or" (Sparta W58: dropping ", and other
        # objects collected in the local museum," gave "sculptures founded by Stamatakis")
        "The finds consisted of inscriptions, sculptures, and other objects kept in the local "
        "museum, founded in 1872.",
        "Visitors reach the site by boat, or by the coastal road, which was built in 1950.",
    ],
)
def test_a_comma_pair_inside_a_list_is_no_insertion(text: str) -> None:
    assert _a_spans(text) == set()


def test_an_insertion_beside_a_list_is_still_offered() -> None:
    text = "The temple, which stood on a low ridge, held statues of Ra and Isis."
    assert _a_spans(text) == {", which stood on a low ridge,"}
    # a short insertion before a long tail that carries a coordinator is no list link
    text = "The temple, now ruined, held statues of the gods of the river and of the sky."
    assert _a_spans(text) == {", now ruined,"}
    # the pair after it is a list link, not an insertion, so the shared comma refuses nothing
    text = "The finds, which were made in 1900, included pottery, coins, and tools."
    assert _a_spans(text) == {", which were made in 1900,"}


@pytest.mark.parametrize(
    "text",
    [
        # Agri Bavnehøj W11: dropping ", in Bavnehøj," read "The old Danish word, bavn means ..."
        "The old Danish word, bavn, in Bavnehøj, means a stack of wood placed on high ground.",
        # Babylon W1: ", within modern-day Hillah," beside ", Iraq,"
        "The city lay on the river in the south, within modern Hillah, Iraq, 85 km south "
        "of Baghdad.",
        # three insertion pairs in a row: each shares a comma with the next
        "The hall, a long room, of timber, with a hearth, stood on the hill above.",
        # the neighbour carries a protected token: it is refused, and it still refuses its partner
        "The old word, probably bavn, in the name, means a stack of wood on high ground.",
    ],
)
def test_two_comma_pairs_that_share_a_comma_offer_neither(text: str) -> None:
    """Which two of three commas enclose the insertion is not in the text (decision 2026-09-23):
    neither pair is offered, whichever one a reader would pick."""
    assert _a_spans(text) == set()


def test_a_leading_phrase_takes_its_comma_and_the_space_after_it() -> None:
    assert _spans("In 1900, the site was cleared of rubble by the governor.")["l1"] == "In 1900, "


@pytest.mark.parametrize(
    "text",
    [
        # the list's head and its first item (Babylon W204: dropping "Coins from the Parthian, "
        # read "Sasanian, and Arabic periods excavated in Babylon demonstrate ...")
        "The temples of Asclepius, Aphrodite, Apollo, and Artemis stood on the hill.",
        "Coins from the Parthian, Sasanian, and Arabic periods lie in the museum.",
        "Finds from the ditch included pottery, coins, tools and bones from the pit.",
        # the first of two conjuncts, with no second delimiter comma
        "The shrine was abandoned, and the temple was used as a barn.",
        "The stones came from the river, or they were cut on the hill above.",
    ],
)
def test_a_leading_phrase_that_opens_a_list_or_a_conjunct_is_not_offered(text: str) -> None:
    assert "l1" not in _spans(text)


def test_a_leading_phrase_of_seven_tokens_is_not_offered() -> None:
    text = "In the first year of the war, the site was cleared by the army."
    assert "l1" not in _spans(text)
    assert "l1" in _spans("In the first year of war, the site was cleared by the army.")


def test_the_last_comma_segment_stops_before_the_final_punctuation() -> None:
    text = "The temple was built by a farming community, whose tombs lie nearby."
    assert _spans(text) == {"t1": ", whose tombs lie nearby"}


def test_a_comma_inside_a_number_delimits_nothing() -> None:
    text = "The walls enclose 4,500 square metres of the hill top above the river."
    assert _spans(text) == {}


def test_a_comma_inside_a_parenthesis_delimits_nothing() -> None:
    text = "The shrine (rebuilt, twice) was added later on the hill top."
    assert _spans(text) == {"p1": " (rebuilt, twice)"}


def test_unbalanced_parentheses_offer_nothing() -> None:
    # A comma before the stray parenthesis would otherwise offer a leading phrase.
    assert _spans("In 1900, the shrine was added later (rebuilt twice.") == {}
    assert _spans("In 1900, the shrine) was added later on the hill top.") == {}


def test_a_sentence_without_final_punctuation_offers_nothing() -> None:
    text = "The shrine (rebuilt twice) was added later, on the hill top"
    assert _spans(text) == {}


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("The temple, probably built by farmers, was used for centuries.", "probably"),
        ("The temple was used for centuries, according to the excavators.", "according"),
        ("The temple was built (c. 2500 BC) by farmers on the ridge.", "c."),
        ("The shrine was added, but only in the second phase, to the temple.", "only"),
        ("The shrine was added later, as a part of the second phase.", "part of"),
        ("The shrine was added later, as the excavators suggested.", "suggest*"),
        ("The shrine was added later, though the date is unclear.", "though"),
        ("The shrine was not rebuilt, and the wall was never finished.", "not"),
    ],
)
def test_a_span_carrying_a_protected_token_is_never_offered(text: str, word: str) -> None:
    for span_text in _spans(text).values():
        assert not S.carries_protected_token(span_text), (word, span_text)
    assert S.carries_protected_token(text), word


@pytest.mark.parametrize(
    ("text", "word"),
    [
        # The shapes the review of WB-B2 found offered in the real pools (2026-09-23): dropping one
        # turns a hedged or negated claim into a plain assertion.
        ("Presumably, the dead were first laid down in the open on the hill.", "Presumably"),
        ("Apparently, the name of the village was taken from the stones.", "Apparently"),
        ("The cave yielded, arguably, the oldest bison bones in the region.", "arguably"),
        ("The town was, it seems, founded by settlers from the coast.", "seems"),
        ("The mound was built, it appears, by the first farmers of the valley.", "appears"),
        ("Supposedly, the stones were raised by giants on the hill.", "Supposedly"),
        ("Reputedly, the hermit lived in the cave above the river.", "Reputedly"),
        ("Evidently, the ditch was cut after the bank had been raised.", "Evidently"),
        ("The ridge, possible remains of a Roman fort, lies above the ford.", "possible"),
        ("The mound, probable site of a Bronze Age burial, lies on the ridge.", "probable"),
        ("The date of the mound is unknown, since the ditch was never dated.", "unknown"),
        ("The shrine was abandoned, as the deity venerated there cannot be named.", "cannot"),
        ("They don't have any drilled holes, which shows the talons were worn loose.", "don't"),
        ("They don’t have any drilled holes, which shows the talons were worn loose.", "don’t"),
        ("The bishopric was moved, and the see wasn't restored after the war.", "wasn't"),
        # pilot 2 (T3): a correction or contrast marker - House of the Faun's "(actually a satyr,
        # since the lower body is that of a man)" was offered and dropped
        ("The statue of a faun (actually a satyr) is what the house is named after.", "actually"),
        ("In fact, the ditch was cut after the bank had been raised.", "In fact"),
        ("In reality, the stones were set up by the farmers of the valley.", "In reality"),
        ("The shrine, instead of a temple, stood on the hill above the ford.", "instead"),
        ("The fort lay on the hill, rather than in the town.", "rather"),
        ("Whilst visiting the monument in 1666, the antiquary drew the stones.", "Whilst"),
        ("Nevertheless, the fort was held until the end of the war.", "Nevertheless"),
        ("Nonetheless, the fort was held until the end of the war.", "Nonetheless"),
        ("Contrary to a popular myth, the nose was not shot off by soldiers.", "Contrary"),
        ("Unlike the cemetery on the hill, the tomb held no pottery at all.", "Unlike"),
        ("The temple of Neptune (wrongly so named) stands on the plain.", "wrongly"),
        ("The ship (sometimes mistaken for a galley) lies in the harbour.", "mistaken"),
        ("The arch (sometimes erroneously written Bara) stands by the road.", "erroneously"),
        ("The mound, one incorrectly dated, lies beside the second ditch.", "incorrectly"),
        ("The ruin (which he misidentified as Ramah) lies on the hill.", "misidentified"),
        ("The statue (misattributed to Pheidias) stood in the temple.", "misattributed"),
        # every contracted negation, not a list of them
        ("The finds, which oughtn't be moved, lie in the museum of the town.", "oughtn't"),
        ("The shepherds, who daren't enter the cave, graze the slope below.", "daren't"),
        ("The mound, which won’t yield to the plough, rises above the field.", "won’t"),
    ],
)
def test_a_span_carrying_an_unlisted_hedge_or_a_contracted_negation_is_never_offered(
    text: str, word: str
) -> None:
    assert S.carries_protected_token(word), word
    for span_text in _spans(text).values():
        assert word not in span_text, (word, span_text)


def test_every_protected_group_is_honoured() -> None:
    for group, entries in M.PROTECTED_TOKENS.items():
        for entry in entries:
            if entry.endswith("*"):
                sample = entry.replace("*", "ed")
            elif entry.startswith("*"):
                sample = entry.replace("*", "ought")
            else:
                sample = entry
            assert S.carries_protected_token(f"x {sample} y"), (group, entry)
    assert not S.carries_protected_token("the ridge of the island")
    assert not S.carries_protected_token("etc. and so on")  # `c.` only as its own word


@pytest.mark.parametrize(("source_id", "text", "spans"), SPAN_CASES)
def test_the_span_cases_both_finders_share(source_id: str, text: str, spans: dict) -> None:
    """The fixture verify4's parity test runs its own finder over (PHASE4_CONTRACTS section 7)."""
    (sentence,) = S.split_source(source_id, text)
    assert {span.id: text[span.start : span.end] for span in sentence.spans} == spans


def test_the_prompt_shows_the_exact_range() -> None:
    text = "The temple was built by a farming community, whose tombs lie nearby."
    (span,) = _one(text).spans
    assert S.span_text(text, span) == '", whose tombs lie nearby"'


def test_span_ids_count_per_kind_in_text_order() -> None:
    text = "In 1900, the temple (north) and the shrine (south), both of stone, were cleared."
    ids = [span.id for span in _one(text).spans]
    assert ids == sorted(ids, key=lambda i: next(s.start for s in _one(text).spans if s.id == i))
    assert {i for i in ids if i.startswith("p")} == {"p1", "p2"}


# ----------------------------------------------------------------------------------- pool


def test_the_pool_is_the_lead_and_the_first_six_of_each_section() -> None:
    lead = " ".join(f"The lead sentence number {i} is long enough." for i in range(1, 9))
    section = " ".join(f"The history sentence number {i} is long enough." for i in range(1, 10))
    text = f"{lead}\n\n\n== History ==\n\n{section}\n"
    pool = S.candidate_pool(S.split_source("W", text), lane=M.Lane.W, names=["X"], text=text)
    assert [s.section for s in pool].count(None) == 8
    assert [s.section for s in pool].count("History") == S.SENTENCES_PER_SECTION


def test_reference_sections_are_never_in_the_pool() -> None:
    sentences = S.split_source("W", X.ARTICLE)
    pool = S.candidate_pool(sentences, lane=M.Lane.W, names=["Stone Temple"], text=X.ARTICLE)
    assert "References" in {s.section for s in sentences}
    assert "References" not in {s.section for s in pool}


def test_only_publishable_sentences_are_offered() -> None:
    long_one = "The temple " + "was very large and " * 30 + "old."
    text = f"Short one. The temple stands on the ridge above the sea. {long_one} and a fragment."
    sentences = S.split_source("W", text)
    pool = S.candidate_pool(sentences, lane=M.Lane.W, names=["X"], text=text)
    assert [S.sentence_text(text, s) for s in pool] == [
        "The temple stands on the ridge above the sea."
    ]


def test_a_sentence_cut_at_an_initial_is_never_in_the_pool() -> None:
    """Terminated and long enough, but `is_complete_sentence` refuses it: it ends on an initial."""
    cut = "The finds were first published in a report by the excavator Kevin C."
    text = f"The temple stands on the ridge above the sea.\n{cut}\n"
    sentences = S.split_source("W", text)
    assert cut in [S.sentence_text(text, s) for s in sentences]  # its own sentence
    pool = S.candidate_pool(sentences, lane=M.Lane.W, names=["X"], text=text)
    assert [S.sentence_text(text, s) for s in pool] == [
        "The temple stands on the ridge above the sea."
    ]


@pytest.mark.parametrize(("text", "garbled"), GARBLE_CASES)
def test_the_garble_cases_s2_judges_exactly(text: str, garbled: bool) -> None:
    """Pilot 2 (T5): the fixture V5's own check is held to as well (`p4_garble_cases`)."""
    assert S.garbled(text) is garbled


def test_a_garbled_source_sentence_is_never_in_the_pool() -> None:
    """Bassae and Vindobala, pilot 2: complete, terminated and long enough, but each carries its
    source's garble - a full stop before a lowercase word, a preposition before a comma. The
    selector is never offered either, so V5 never has to hold the site for it."""
    bassae = (
        "Bassae lies at an elevation of 1,131 m above sea level on the slopes of Cotylion "
        "Mountain. near the village of Skliros, northeast of Figaleia."
    )
    vindobala = (
        "Vindobala was a Roman fort with the modern name, and in the hamlet of, Rudchester, "
        "Northumberland."
    )
    good = "The temple stands on the ridge above the sea."
    text = f"{good}\n{bassae}\n{vindobala}\n"
    sentences = S.split_source("W", text)
    assert {bassae, vindobala} <= {S.sentence_text(text, s) for s in sentences}
    pool = S.candidate_pool(sentences, lane=M.Lane.W, names=["X"], text=text)
    assert [S.sentence_text(text, s) for s in pool] == [good]


def test_the_pool_stops_at_120_sentences() -> None:
    text = " ".join(f"The lead sentence number {i} is long enough." for i in range(1, 200))
    pool = S.candidate_pool(S.split_source("W", text), lane=M.Lane.W, names=["X"], text=text)
    assert len(pool) == S.MAX_POOL_SENTENCES


def test_the_pool_stops_at_24000_characters() -> None:
    body = "The lead sentence is long enough to count and it goes on " + "and on " * 45 + "here."
    text = " ".join([body] * 100)
    pool = S.candidate_pool(S.split_source("W", text), lane=M.Lane.W, names=["X"], text=text)
    assert sum(s.end - s.start for s in pool) <= S.MAX_POOL_CHARS
    assert sum(s.end - s.start for s in pool) + len(body) > S.MAX_POOL_CHARS


def test_lane_s_offers_only_name_bearing_sentences_or_their_section() -> None:
    text = (
        "The town of Gozo has a market and a harbour. The Old Shrine lies west of the town.\n"
        "\n\n== Old Shrine ==\n\nIts walls were built of limestone blocks.\n"
    )
    pool = S.candidate_pool(
        S.split_source("W", text), lane=M.Lane.S, names=["old shrine"], text=text
    )
    assert [S.sentence_text(text, s) for s in pool] == [
        "The Old Shrine lies west of the town.",
        "Its walls were built of limestone blocks.",
    ]


def test_a_name_match_is_whole_words_and_ignores_accents() -> None:
    assert S.names_in("The Göbekli Tepe mound lies here.", ["Gobekli Tepe"])
    assert not S.names_in("The Kilmartinglen stones.", ["Kilmartin"])


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("The Chichen Itza complex lies in the north of the peninsula.", "Chichén-Itzá"),
        ("The St Kilda cleits are stone storage huts on the island.", "St. Kilda"),
        ("The Chichén-Itzá ball court is the largest of its kind.", "Chichen Itza"),
    ],
)
def test_a_name_matches_by_the_one_phase4_fold(text: str, name: str) -> None:
    """Lane S keeps the sentences that name the site; the subject gate accepted the article by the
    same name with `subject_gate.fold` (punctuation a space). A second fold that keeps the hyphen or
    the full stop would find no sentence and hold the site as no-source (the review's R6)."""
    assert S.names_in(text, [name])
    assert S.names_in(text, [name]) == (f" {SG.fold(name)} " in f" {SG.fold(text)} ")


def test_lanes_without_selection_have_no_pool() -> None:
    with pytest.raises(ValueError, match="selects no sentences"):
        S.candidate_pool((), lane=M.Lane.R, names=["X"], text="")
