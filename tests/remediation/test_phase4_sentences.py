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

from tests.remediation import p4_fixtures as X  # noqa: E402


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


def test_a_leading_phrase_takes_its_comma_and_the_space_after_it() -> None:
    assert _spans("In 1900, the site was cleared of rubble by the governor.")["l1"] == "In 1900, "


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


def test_every_protected_group_is_honoured() -> None:
    for group, entries in M.PROTECTED_TOKENS.items():
        for entry in entries:
            sample = entry.replace("*", "ed") if entry.endswith("*") else entry
            assert S.carries_protected_token(f"x {sample} y"), (group, entry)
    assert not S.carries_protected_token("the ridge of the island")
    assert not S.carries_protected_token("etc. and so on")  # `c.` only as its own word


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


def test_lanes_without_selection_have_no_pool() -> None:
    with pytest.raises(ValueError, match="selects no sentences"):
        S.candidate_pool((), lane=M.Lane.R, names=["X"], text="")
