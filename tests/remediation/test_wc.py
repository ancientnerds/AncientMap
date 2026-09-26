"""Lane WC (owner decision O5, 2026-09-26): is a March description checked sentence by sentence,
kept only on machine-verified quotes, trimmed only by an exact cut, and cleared when nothing stays?

The deterministic core is `scripts/remediation/phase4/wc4.py`; the research side (read, export,
brief, check-answer, import, re-ask, build, the pilot's judge) is `scripts/remediation/wc/`. The
writer's group WC and its acceptance are tested in `test_phase4_wc_write.py`. The mutation cases are
`WC_MUTATIONS` in `scripts/remediation/phase3/mutation_sweep.py`. No socket, no model, no database.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import research_web  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402
from wc import answers as A  # noqa: E402
from wc import cli as C  # noqa: E402
from wc import prompts as P  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation.wc_fixtures import OH, WC4, M  # noqa: E402


# ------------------------------------------------------------------------------ the sentences
def test_the_question_asks_the_served_text_without_its_markers_in_phase4s_split() -> None:
    assert WC4.checked_sentences(FX.TEXT_A) == FX.SENTENCES_A
    assert WC4.strip_markers("A temple [1]. Built here.[1][2]") == "A temple. Built here."


def test_a_grouped_marker_left_after_the_plain_ones_is_not_asked() -> None:
    with pytest.raises(WC4.WcError, match="grouped or range"):
        WC4.checked_sentences("A temple [1, 2]. Built here [3].")


def test_a_text_without_a_sentence_is_not_asked() -> None:
    with pytest.raises(WC4.WcError, match="no sentence"):
        WC4.checked_sentences("   ")


@pytest.mark.parametrize(
    ("text", "sentences"),
    [
        # the population's own cases (2026-09-26): Duggleby Howe, Venado Beach, Frankenbury Camp,
        # Aetokremnos
        ("A round barrow. First excavated by Rev. Christopher Sykes in 1798.",
         ("A round barrow.", "First excavated by Rev. Christopher Sykes in 1798.")),
        ("Dug by Neville A. Harte, and Lt. Col. Montgomery. It is Gran Cocle.",
         ("Dug by Neville A. Harte, and Lt. Col. Montgomery.", "It is Gran Cocle.")),
        ("It is a scheduled ancient monument (no. 122). A hillfort.",
         ("It is a scheduled ancient monument (no. 122).", "A hillfort.")),
        ("It dates to c. 10,000 cal. BC. The name means eagle.",
         ("It dates to c. 10,000 cal. BC.", "The name means eagle.")),
    ],
)  # fmt: skip
def test_a_piece_the_splitter_ends_on_an_unknown_abbreviation_is_joined_to_the_next(
    text: str, sentences: tuple[str, ...]
) -> None:
    assert WC4.checked_sentences(text) == sentences


@pytest.mark.parametrize(
    ("sentence", "numbers", "marked"),
    [
        ("A temple in Malta.", (1,), "A temple in Malta [1]."),
        ("A temple in Malta.", (1, 2), "A temple in Malta [1] [2]."),
        ('It is called "the Monastery of the City."', (2,),
         'It is called "the Monastery of the City." [2]'),
        ("It is venerated as 'the Great God.'", (1, 3), "It is venerated as 'the Great God.' [1] [3]"),
        ("It is a gateway to resorts including Verbier", (1,),
         "It is a gateway to resorts including Verbier [1]."),
        ('It is called "the Gate"', (1,), 'It is called "the Gate" [1].'),
    ],
)  # fmt: skip
def test_a_marker_goes_before_the_final_mark_outside_a_quotation_or_brings_its_full_stop(
    sentence: str, numbers: tuple[int, ...], marked: str
) -> None:
    assert WC4.with_markers(sentence, numbers) == marked
    assert WC4.strip_markers(marked).rstrip(".") == sentence.rstrip(".")


# ------------------------------------------------------------------------------ the trim
SENTENCE = "They date to approximately 3150 BC, and they were built by giants."


def test_a_trim_removes_one_exact_piece_and_leaves_a_clean_sentence() -> None:
    assert WC4.trim(SENTENCE, ", and they were built by giants") == (
        "They date to approximately 3150 BC."
    )


def test_a_leading_piece_restores_the_capital() -> None:
    sentence = "In 1915, the temples were excavated by Themistocles Zammit."
    assert WC4.trim(sentence, "In 1915, ") == "The temples were excavated by Themistocles Zammit."


@pytest.mark.parametrize(
    ("remove", "message"),
    [
        ("and they were built by giants", "dangling punctuation"),
        ("built by giants", "space before punctuation"),
        (" giants.", "does not end with"),
        ("xyz", "occurs 0 times"),
        ("e", "occurs"),
        (SENTENCE, "whole sentence"),
        ("   ", "empty"),
        ("approximately ", "hedge, negation"),
    ],
)
def test_a_trim_that_is_not_exact_once_or_not_clean_is_refused(remove: str, message: str) -> None:
    with pytest.raises(WC4.WcError, match=message):
        WC4.trim(SENTENCE, remove)


def test_a_trim_that_leaves_a_double_space_is_refused() -> None:
    with pytest.raises(WC4.WcError, match="double space"):
        WC4.trim("The temple was built in 3000 BC by farmers.", "in 3000 BC")


def test_a_trimmed_sentence_under_25_characters_is_refused() -> None:
    with pytest.raises(WC4.WcError, match="under 25"):
        WC4.trim("A small temple stands in Tarxien, Malta.", " stands in Tarxien, Malta")


@pytest.mark.parametrize(
    ("sentence", "remove", "rest"),
    [
        ("Dating to the Late Neolithic period (c. 3000 BC), the mound is 37 metres wide.",
         " (c. 3000 BC)", "Dating to the Late Neolithic period, the mound is 37 metres wide."),
        ("The shelter, dated to approximately 10,000 BC, lies near Limassol in Cyprus.",
         ", dated to approximately 10,000 BC,", "The shelter lies near Limassol in Cyprus."),
        ("It was excavated by Sykes in 1798, but no records of his work remain.",
         ", but no records of his work remain", "It was excavated by Sykes in 1798."),
        ("The mound, probably a tomb, stands on the hill above the river.",
         ", probably a tomb,", "The mound stands on the hill above the river."),
        # a reporting hedge goes with the number it reports, inside the sentence
        ("The shelter, believed to date to about 10,000 BC, lies near Limassol in Cyprus.",
         ", believed to date to about 10,000 BC,", "The shelter lies near Limassol in Cyprus."),
        ("The mound, thought to have been raised in 3000 BC, stands on the hill.",
         ", thought to have been raised in 3000 BC,", "The mound stands on the hill."),
        ("The mound, reportedly raised in 3000 BC, stands on the hill above the river.",
         ", reportedly raised in 3000 BC,", "The mound stands on the hill above the river."),
        # a negation goes with the whole of its clause
        ("The mound, not a tomb, stands on the hill above the river.",
         ", not a tomb,", "The mound stands on the hill above the river."),
        # a negation that stays, in another clause than the piece
        ("The temple is not in Gozo, and it was built by giants in 3000 BC.",
         " by giants", "The temple is not in Gozo, and it was built in 3000 BC."),
    ],
)  # fmt: skip
def test_a_trim_may_cut_a_whole_clause_with_its_own_hedge(sentence, remove, rest) -> None:
    """The March texts' commonest invention is a hedged number: the clause goes with its hedge."""
    assert WC4.trim(sentence, remove) == rest


@pytest.mark.parametrize(
    ("sentence", "remove"),
    [
        # the review's probes of 2026-09-26: each passed every sentence check and read as new text
        ("The first temple on the hill was built c. 3000 BCE.", " c. 3000 BC"),
        ("The great mound was erected in the 3rd millennium BC by farmers.",
         " in the 3rd millennium B"),
        ("It is the largest megalithic tomb in northern Europe and a landmark.",
         " megalithic tomb in northern Europ"),
        ("The temple was built around 3500 BC by the farmers of the island.", "5"),
        ("The temple was built around 3500 BC by the farmers of the island.", "un"),
        # a number with its separators is one token too
        ("The temple was built around 3,500 BC by the farmers of the island.", ",500"),
        ("The temple was built around 3,500 BC by the farmers of the island.", "3,"),
        ("The capstone weighs about 2.5 tonnes and rests on three uprights.", ".5"),
        # a word joined by a hyphen or an apostrophe is one token as well
        ("The Hal-Saflieni Hypogeum is an underground complex in Paola.", " Hal-"),
        ("Zammit's excavations at the temples began in the year 1915.", "'s"),
    ],
)  # fmt: skip
def test_a_trim_never_cuts_inside_a_word_or_a_number(sentence: str, remove: str) -> None:
    """A piece copied one character short (` BC` of ` BCE`) or cut from inside a number leaves a
    token no source ever wrote (`builtE`, `300 BC`): its edges must fall between words."""
    with pytest.raises(WC4.WcError, match="cuts a word or number"):
        WC4.trim(sentence, remove)
    assert not WC4.cuts_token(sentence, 0) and not WC4.cuts_token(sentence, len(sentence))


@pytest.mark.parametrize(
    ("sentence", "remove"),
    [
        # the review's probes of 2026-09-26: a hedged claim that the trim would state as fact
        ("According to legend, the temple was built by giants in one night.",
         "According to legend, "),
        ("It is believed that the temple was built by the Phoenicians.", "It is believed that "),
        # the same frames elsewhere in the sentence, and the hedges V4's reporting words lack
        ("The temple was built, it is said, by giants in a single night.", ", it is said,"),
        ("It is likely that the temple was built by the Phoenicians.", "It is likely that "),
        ("The temple, according to Maltese folklore, was built by giants.",
         ", according to Maltese folklore,"),
        ("According to Maltese folklore, the temple was built by giants.",
         "According to Maltese folklore, "),
        ("The temple is said to be the oldest free-standing building in Malta.", " said to be"),
        # a reporting hedge that opens the sentence reports the rest, its number or not
        ("Legend dates it to 3000 BC, and giants built the temple in one night.",
         "Legend dates it to 3000 BC, and "),
        ("Believed to date to 3000 BC, the temple stands on a hill above the sea.",
         "Believed to date to 3000 BC, "),
        # a frame of the words V4 lacks: whether, as, think, consider
        ("It is uncertain whether the temple was built by the Phoenicians.",
         "It is uncertain whether "),
        ("As many scholars think, the temple was built by the Phoenicians.",
         "As many scholars think, "),
        ("It is considered the oldest free-standing building in all of Malta.",
         "It is considered "),
    ],
)  # fmt: skip
def test_a_hedge_frame_or_a_reporting_hedge_is_never_cut_off_its_claim(sentence, remove) -> None:
    with pytest.raises(WC4.WcError, match="hedge"):
        WC4.trim(sentence, remove)


@pytest.mark.parametrize(
    ("sentence", "remove"),
    [
        # the reporting word reports the rest, not a figure of its own clause
        ("The temple was, as Evans believed in 1920, built by giants in one night.",
         ", as Evans believed in 1920,"),
        ("The temple was built by giants, as was reported in 1990.", ", as was reported in 1990"),
        ("The temple, believed to be the oldest in Malta, stands on a hill.",
         ", believed to be the oldest in Malta,"),
        # a word that puts the whole sentence under a telling or into doubt, wherever it stands
        ("The temple, in Maltese tradition dated to 3000 BC, was built by giants.",
         ", in Maltese tradition dated to 3000 BC,"),
        ("The temple, whose date of 3000 BC is disputed, was built by the farmers.",
         ", whose date of 3000 BC is disputed,"),
        ("The temple was built by giants, a myth first recorded in 1850.",
         ", a myth first recorded in 1850"),
    ],
)  # fmt: skip
def test_a_reporting_or_doubting_word_goes_only_with_the_figure_it_reports(
    sentence, remove
) -> None:
    """A reporting word may go only as the inner clause of its own figure (`, believed to date to
    about 10,000 BC,`); a telling or a doubt of the whole sentence never goes."""
    with pytest.raises(WC4.WcError, match="hedge"):
        WC4.trim(sentence, remove)


@pytest.mark.parametrize(
    ("sentence", "remove"),
    [
        # the review's probes of 2026-09-26: a cut inside a negation's clause widens or inverts it
        ("The site is not a burial mound but a natural hill in the valley.", " a burial mound but"),
        ("The site was never excavated by Evans or anyone after him.", " by Evans or anyone after him"),
        ("No excavation has taken place at the site since the year 1920.", " since the year 1920"),
        # a negation that goes, while the rest of its clause stays
        ("The temple was not built by giants in the year 3000 BC.", " not built by giants"),
    ],
)  # fmt: skip
def test_a_trim_never_cuts_inside_the_clause_of_a_negation(sentence, remove) -> None:
    with pytest.raises(WC4.WcError, match="negation"):
        WC4.trim(sentence, remove)


@pytest.mark.parametrize(
    "remove", ["probably ", " not", "only ", "at least ", "approximately ", ", however,"]
)
def test_a_bare_hedge_negation_or_restriction_is_never_cut_off_its_claim(remove: str) -> None:
    sentence = "The mound, however, was probably not only at least approximately 37 metres wide in 3000 BC."
    assert WC4.bare_modifier(remove)
    with pytest.raises(WC4.WcError, match="only a hedge, negation"):
        WC4.trim(sentence, remove)


def test_a_trim_may_keep_a_stored_oddity_but_never_adds_one() -> None:
    """`is_complete_sentence` knows ASCII capitals only: a sentence that opens with `Ž` is no
    "complete sentence" before or after the trim, so the trim adds nothing and stands."""
    sentence = "Židovar is an archaeological site near Vršac, built by giants, in Serbia."
    assert WC4.trim(sentence, " built by giants,") == (
        "Židovar is an archaeological site near Vršac, in Serbia."
    )
    with pytest.raises(WC4.WcError, match="double space"):
        WC4.trim(sentence, "built by giants,")


def test_a_sentence_without_its_opening_still_keeps_its_end() -> None:
    """The review's probe of 2026-09-26: the opening and the end are asked apart, so a sentence
    that already lacks an ASCII capital cannot lose its final mark to a trim."""
    sentence = "Židovar is a hill fort on the bank of the Danube in Serbia."
    with pytest.raises(WC4.WcError, match="does not end with"):
        WC4.trim(sentence, " the bank of the Danube in Serbia.")


def test_a_piece_never_takes_the_end_of_a_sentence_stored_without_its_final_mark() -> None:
    """4 of the 15,133 sentences end without . ! or ? (2026-09-26): the stored end stays, so the
    trimmed sentence cannot end on a fragment the markers then close with a full stop."""
    sentence = "The site was built in 3000 BC by the farmers of the island"
    assert WC4.trim(sentence, " in 3000 BC") == "The site was built by the farmers of the island"
    with pytest.raises(WC4.WcError, match="final mark"):
        WC4.trim(sentence, " by the farmers of the island")


# ------------------------------------------------------------------------------ the decisions
def _d(n: int, sentence: str, verdict: str = "KEEP", remove=None, reason=None) -> WC4.Decision:
    return WC4.Decision(
        n=n,
        sentence=sentence,
        verdict=WC4.Verdict(verdict),
        remove=remove,
        reason=None if reason is None else WC4.DropReason(reason),
    )


def test_a_pronoun_sentence_goes_with_the_sentence_before_it_and_the_chain_follows() -> None:
    decisions = [
        _d(1, "The Tarxien Temples lie in Malta.", "DROP", reason="unsupported"),
        _d(2, "They date to approximately 3150 BC."),
        _d(3, "Its altar is decorated with spirals."),
        _d(4, "The complex was excavated in 1915."),
        _d(5, "It is a World Heritage Site."),
    ]
    out = WC4.follow_drops(decisions)
    assert [(d.verdict.value, d.reason) for d in out] == [
        ("DROP", WC4.DropReason.UNSUPPORTED),
        ("DROP", WC4.DropReason.LEANS),
        ("DROP", WC4.DropReason.LEANS),
        ("KEEP", None),
        ("KEEP", None),
    ]


def test_a_first_sentence_that_opens_with_a_pronoun_leans_on_nothing() -> None:
    (only,) = WC4.follow_drops([_d(1, "It is a temple complex in Malta.")])
    assert only.verdict is WC4.Verdict.KEEP


def _quotes() -> dict[int, list[WC4.Quote]]:
    return {
        1: [WC4.Quote(FX.WIKI, "Tarxien Temples - Wikipedia", "the quote one")],
        2: [
            WC4.Quote(FX.MUSEUM, "Tarxien", "the quote two"),
            WC4.Quote(FX.WIKI, "Tarxien Temples - Wikipedia", "the quote three"),
        ],
        3: [WC4.Quote(FX.WIKI, "Tarxien Temples - Wikipedia", "the quote four")],
    }


def _three() -> list[WC4.Decision]:
    return [
        _d(1, "The Tarxien Temples are in Malta."),
        _d(2, "They date to approximately 3150 BC, and they were built by giants.", "KEEP_TRIMMED",
           remove=", and they were built by giants"),
        _d(3, "The site was excavated in 1915."),
    ]  # fmt: skip


def test_the_text_marks_each_sentence_with_its_pages_numbered_by_first_appearance() -> None:
    composed = WC4.compose(_three(), _quotes())
    assert composed.description == (
        "The Tarxien Temples are in Malta [1]. They date to approximately 3150 BC [1] [2]. "
        "The site was excavated in 1915 [1]."
    )
    assert composed.citations == (
        {"n": 1, "url": FX.WIKI, "title": "Tarxien Temples - Wikipedia", "domain": "en.wikipedia.org"},
        {"n": 2, "url": FX.MUSEUM, "title": "Tarxien", "domain": "heritagemalta.mt"},
    )  # fmt: skip
    assert composed.cites == ((1,), (1, 2), (1,))


def test_two_quotes_of_one_page_give_one_marker() -> None:
    page = WC4.Quote(FX.WIKI, "Tarxien Temples - Wikipedia", "the quote one")
    again = WC4.Quote(FX.WIKI, "Tarxien Temples - Wikipedia", "the quote two")
    composed = WC4.compose([_d(1, "The Tarxien Temples are in Malta.")], {1: [page, again]})
    assert composed.description == "The Tarxien Temples are in Malta [1]."
    assert composed.cites == ((1,),) and len(composed.citations) == 1


def test_a_kept_sentence_without_a_verified_quote_is_a_contract_breach() -> None:
    with pytest.raises(WC4.WcError, match="without a verified quote"):
        WC4.compose(_three(), {1: _quotes()[1]})


def test_nothing_kept_composes_no_text_and_no_citation() -> None:
    decisions = [_d(1, "A temple.", "DROP", reason="contradicted")]
    composed = WC4.compose(decisions, {})
    assert (composed.description, composed.citations, composed.cites) == (None, (), ((),))


# ------------------------------------------------------------------------------ the record
def _outcome(site_row: dict, decisions=None, quotes=None):
    site = FX.plan_site(site_row)
    decisions = _three() if decisions is None else decisions
    quotes = _quotes() if quotes is None else quotes
    composed = WC4.compose(decisions, quotes)
    check = (
        None
        if composed.description is None
        else WC4.check_record(decisions, composed, quotes, run="wc-test", checked=site.description)
    )
    return site, composed, check, WC4.written_raw_data(site, composed, check)


def test_the_check_record_reads_back_strictly_and_counts_what_its_sentences_say() -> None:
    _, composed, check, _ = _outcome(
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A))
    )
    assert WC4.DescriptionCheck.from_dict(check.to_dict()) == check
    assert (check.kept, check.of, check.trimmed) == (3, 3, 1)
    assert check.checker == M.AI_SYSTEM
    assert check.desc_sha256 == M.text_sha256(composed.description)
    assert check.sentences[1].quote_sha256 == (
        M.text_sha256("the quote two"),
        M.text_sha256("the quote three"),
    )
    data = check.to_dict()
    for broken, message in (
        ({**data, "extra": 1}, "unknown"),
        ({**data, "kept": 2}, "is not what its sentences say"),
        ({**data, "checker": "someone"}, "is not"),
        ({**data, "desc_sha256": "x"}, "sha256"),
    ):
        with pytest.raises(ValueError, match=message):
            WC4.DescriptionCheck.from_dict(broken)


def test_a_record_never_describes_a_cleared_text() -> None:
    sentence = WC4.CheckedSentence(
        n=1, verdict=WC4.Verdict.DROP, reason=WC4.DropReason.UNSUPPORTED, cites=(), quote_sha256=()
    )
    with pytest.raises(ValueError, match="nothing kept is a clear"):
        WC4.DescriptionCheck(
            run="r", checker=M.AI_SYSTEM, checked_sha256="a" * 64, kept=0, of=1, trimmed=0,
            sentences=(sentence,), desc_sha256="b" * 64,
        )  # fmt: skip


def test_a_lane_l_text_keeps_its_ai_mark_with_the_hash_moved_and_every_other_key() -> None:
    raw = FX.legacy_raw(FX.TEXT_A, title_es="Templos")
    site, composed, check, new = _outcome(FX.row(FX.SITE_A, FX.TEXT_A, raw_data=raw))
    assert (
        new[M.PROVENANCE_KEY]
        == M.LegacyProvenance(desc_sha256=M.text_sha256(composed.description)).to_dict()
    )
    assert new[M.CITATIONS_KEY] == [dict(c) for c in composed.citations]
    assert new[WC4.CHECK_KEY] == check.to_dict()
    assert new["title_es"] == "Templos"
    assert WC4.wc_problems(composed.description, new) == []


@pytest.mark.parametrize(
    "site_row",
    [
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=None, snapshot=FX.TEXT_A),
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=None, in_snapshot=False),
    ],
    ids=["same-as-snapshot", "not-in-snapshot"],
)
def test_an_unclaimed_text_is_checked_and_still_claims_no_ai_origin(site_row) -> None:
    """HUMAN_ONLY D7: an old text nothing proves the March chain wrote gets no provenance - not
    even once it is trimmed, and so differs from the pre-March text."""
    site, composed, _, new = _outcome(site_row)
    assert WC4.old_marking(site) is WC4.Marking.UNCLAIMED
    assert M.PROVENANCE_KEY not in new and WC4.CHECK_KEY in new
    assert WC4.wc_problems(composed.description, new) == []


def test_a_march_text_lane_l_never_marked_gains_the_ai_mark_when_checked() -> None:
    """A text lane L's own rule claims (it differs from the pre-March snapshot) without a stored
    marking - a P4 write a revert took back restores the raw_data from before lane L - is published
    with lane L's marking, so the checked March text never goes out without the AI footnote."""
    site, composed, _, new = _outcome(FX.row(FX.SITE_A, FX.TEXT_A, raw_data=None))
    assert WC4.old_marking(site) is WC4.Marking.MARCH
    assert (
        new[M.PROVENANCE_KEY]
        == M.LegacyProvenance(desc_sha256=M.text_sha256(composed.description)).to_dict()
    )
    assert WC4.wc_problems(composed.description, new) == []


def test_a_kept_text_equal_to_the_pre_march_one_loses_the_march_claim() -> None:
    kept = "The Tarxien Temples are in Malta [1]."
    site_row = FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A), snapshot=kept)
    decisions = [_d(1, "The Tarxien Temples are in Malta."), _d(2, "Built by giants.", "DROP",
                 reason="unsupported")]  # fmt: skip
    _, composed, _, new = _outcome(site_row, decisions, {1: _quotes()[1]})
    assert composed.description == kept and M.PROVENANCE_KEY not in new


def test_the_disclosure_a_written_text_needs_follows_its_old_marking() -> None:
    """The review of 2026-09-26: the AI footnote (EU AI Act) is required, not only checked when
    present. A kept March text carries lane L's provenance hashing it; a text that claims no March
    origin - unclaimed (D7), or kept as the pre-March text - and a cleared site carry none."""
    text = "The Tarxien Temples are in Malta [1]."
    legacy = {M.PROVENANCE_KEY: M.LegacyProvenance(desc_sha256=M.text_sha256(text)).to_dict()}
    march = WC4.marking_record(FX.plan_site(FX.row(FX.SITE_A, FX.TEXT_A,
                                                   raw_data=FX.legacy_raw(FX.TEXT_A))))  # fmt: skip
    assert march == {
        "old": "L", "in_snapshot": True, "snapshot_sha256": M.text_sha256("The pre-March text.")
    }  # fmt: skip
    assert WC4.disclosure_problems(march, text, legacy) == []
    (missing,) = WC4.disclosure_problems(march, text, {})
    assert "AI disclosure" in missing
    stale = {M.PROVENANCE_KEY: M.LegacyProvenance(desc_sha256=M.text_sha256("other")).to_dict()}
    assert WC4.disclosure_problems(march, text, stale)
    assert WC4.disclosure_problems({**march, "old": "march-unmarked"}, text, {})
    unclaimed = {**march, "old": "unclaimed"}
    assert WC4.disclosure_problems(unclaimed, text, {}) == []
    assert WC4.disclosure_problems(unclaimed, text, legacy)  # claims what nothing proves
    pre_march = {**march, "snapshot_sha256": M.text_sha256(text)}
    assert WC4.disclosure_problems(pre_march, text, {}) == []
    assert WC4.disclosure_problems(march, None, None) == []
    assert WC4.disclosure_problems(march, None, legacy)


def test_the_recorded_marking_is_the_one_the_checked_pair_carries() -> None:
    """The writer re-derives the old marking from the row's own old raw_data and the evidence's
    snapshot hash, so a recorded marking cannot excuse a missing footnote."""
    marked = FX.plan_site(FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A)))
    record = WC4.marking_record(marked)
    assert WC4.old_marking_problems(record, FX.TEXT_A, marked.raw_data) == []
    assert WC4.old_marking_problems({**record, "old": "unclaimed"}, FX.TEXT_A, marked.raw_data)
    assert WC4.old_marking_problems(record, FX.TEXT_A, None)
    unmarked = FX.plan_site(FX.row(FX.SITE_A, FX.TEXT_A, raw_data=None))
    assert WC4.marking_record(unmarked)["old"] == "march-unmarked"
    assert WC4.old_marking_problems(WC4.marking_record(unmarked), FX.TEXT_A, None) == []
    same = FX.plan_site(FX.row(FX.SITE_A, FX.TEXT_A, raw_data=None, snapshot=FX.TEXT_A))
    assert WC4.marking_record(same)["old"] == "unclaimed"
    assert WC4.old_marking_problems({**WC4.marking_record(same), "old": "march-unmarked"},
                                    FX.TEXT_A, None)  # fmt: skip


def test_a_cleared_site_keeps_no_wc_key_and_its_raw_data_is_null_when_nothing_is_left() -> None:
    dropped = [_d(1, "A temple.", "DROP", reason="unsupported")]
    _, composed, check, new = _outcome(
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A)), dropped, {}
    )
    assert (composed.description, check, new) == (None, None, None)
    _, _, _, kept_other = _outcome(
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A, title_es="x")), dropped, {}
    )
    assert kept_other == {"title_es": "x"}
    assert WC4.wc_problems(None, kept_other) == []


def test_a_text_phase4_wrote_or_wc_checked_before_is_not_wcs() -> None:
    site = FX.plan_site(FX.row(FX.SITE_A, FX.TEXT_A, raw_data={WC4.CHECK_KEY: {}}))
    with pytest.raises(WC4.WcError, match="checked sentence by sentence before"):
        WC4.old_marking(site)
    full = {M.PROVENANCE_KEY: {"lane": "W"}}
    with pytest.raises(ValueError):
        WC4.old_marking(FX.plan_site(FX.row(FX.SITE_A, FX.TEXT_A, raw_data=full)))


def _pair() -> tuple[str, dict]:
    _, composed, _, new = _outcome(FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A)))
    return composed.description, new


@pytest.mark.parametrize(
    ("break_it", "message"),
    [
        (lambda d, r: (d + " More.", r), "check record's desc_sha256"),
        (lambda d, r: (d, {**r, M.PROVENANCE_KEY: {**r[M.PROVENANCE_KEY], "desc_sha256": "a" * 64}}),
         "provenance's desc_sha256"),
        (lambda d, r: (d, {**r, M.CITATIONS_KEY: r[M.CITATIONS_KEY][:1]}), "disagree"),
        (lambda d, r: (d, {**r, M.CITATIONS_KEY: [{**r[M.CITATIONS_KEY][0], "domain": "x.org"},
                                                    r[M.CITATIONS_KEY][1]]}), "is not its host"),
        (lambda d, r: (d, {**r, M.CITATIONS_KEY: [{**c, "claim": "x"} for c in r[M.CITATIONS_KEY]]}),
         "carries"),
        (lambda d, r: (d, {k: v for k, v in r.items() if k != WC4.CHECK_KEY}), "does not read"),
        (lambda d, r: (None, r), "cleared description beside"),
    ],
)  # fmt: skip
def test_every_wc_invariant_goes_red_when_it_breaks(break_it, message) -> None:
    description, raw = _pair()
    assert WC4.wc_problems(description, raw) == []
    broken = break_it(description, raw)
    assert any(message in problem for problem in WC4.wc_problems(*broken))


def test_markers_that_do_not_run_from_1_by_first_use_break_d1() -> None:
    description, raw = _pair()
    swapped = description.replace("[1]", "[9]").replace("[2]", "[1]").replace("[9]", "[2]")
    problems = WC4.wc_problems(swapped, raw)
    assert any("not numbered 1..N" in p for p in problems)


# ------------------------------------------------------------------------------ the answers
def _parse(sentences, *, site_id=FX.SITE_A, asked=(1, 2, 3)):
    return A.parse_check(
        FX.answer(site_id, sentences), site_id=FX.SITE_A, sentences=FX.SENTENCES_A, asked=asked
    )


def test_an_answer_in_shape_is_read_sentence_by_sentence() -> None:
    parsed = _parse(
        [
            FX.keep(1, FX.Q_COMPLEX),
            FX.trimmed(2, ", and they were built by giants", FX.Q_DATE),
            FX.drop(3, "contradicted", FX.Q_ZAMMIT_WIKI),
        ]
    )
    assert [p.verdict.value for p in parsed] == ["KEEP", "KEEP_TRIMMED", "DROP"]
    assert parsed[2].reason is WC4.DropReason.CONTRADICTED


@pytest.mark.parametrize(
    ("sentences", "message"),
    [
        ([FX.keep(1, FX.Q_COMPLEX)], "covers sentences"),
        ([FX.keep(1), FX.keep(2, FX.Q_DATE), FX.keep(3, FX.Q_ZAMMIT)], "at least one quote"),
        ([FX.keep(1, FX.Q_COMPLEX), {**FX.keep(2, FX.Q_DATE), "remove": ", and"},
          FX.keep(3, FX.Q_ZAMMIT)], "removes nothing"),
        ([FX.keep(1, FX.Q_COMPLEX), FX.trimmed(2, "giants", FX.Q_DATE),
          FX.keep(3, FX.Q_ZAMMIT)], "space before punctuation"),
        ([FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE), FX.drop(3, "contradicted")],
         "contradicting quote"),
        ([FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE), FX.drop(3, "unsupported", FX.Q_ZAMMIT)],
         "contradicting quote"),
        ([FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE), FX.drop(3, "doubtful")], "reason"),
        ([FX.keep(1, FX.quote("https://ancientnerds.com/sites/x", "a quote of twenty chars")),
          FX.keep(2, FX.Q_DATE), FX.keep(3, FX.Q_ZAMMIT)], "own-site host"),
        ([FX.keep(1, FX.quote("https://grokipedia.com/page/Tarxien", "a quote of twenty chars")),
          FX.keep(2, FX.Q_DATE), FX.keep(3, FX.Q_ZAMMIT)], "ai-aggregator host"),
        ([FX.keep(1, FX.quote("https://www.wikiwand.com/en/Tarxien", "a quote of twenty chars")),
          FX.keep(2, FX.Q_DATE), FX.keep(3, FX.Q_ZAMMIT)], "wikimedia host"),
        ([FX.keep(1, FX.quote(FX.WIKI + "?utm_source=x", "a quote of twenty chars")),
          FX.keep(2, FX.Q_DATE), FX.keep(3, FX.Q_ZAMMIT)], "utm_"),
        ([FX.keep(1, FX.quote(FX.WIKI, "too short")), FX.keep(2, FX.Q_DATE),
          FX.keep(3, FX.Q_ZAMMIT)], "20-500"),
        ([FX.keep(1, FX.Q_COMPLEX, FX.Q_COMPLEX, FX.Q_COMPLEX, FX.Q_COMPLEX, FX.Q_COMPLEX),
          FX.keep(2, FX.Q_DATE), FX.keep(3, FX.Q_ZAMMIT)], "at most 4"),
        ([{**FX.keep(1, FX.Q_COMPLEX), "n": True}, FX.keep(2, FX.Q_DATE),
          FX.keep(3, FX.Q_ZAMMIT)], "as an integer"),
    ],
)  # fmt: skip
def test_an_answer_out_of_shape_is_refused_and_says_why(sentences, message) -> None:
    with pytest.raises(A.AnswerError, match=message):
        _parse(sentences)


def test_an_answer_about_another_site_is_refused() -> None:
    with pytest.raises(A.AnswerError, match="names site"):
        _parse([FX.keep(1, FX.Q_COMPLEX)], site_id=FX.SITE_B, asked=(1,))


def _library(tmp_path: Path, client: FX.FakeClient | None = None) -> Q.Library:
    pages = tmp_path / "pages"
    C.fetch(list(FX.PAGES), pages, client=client or FX.FakeClient(), pace=0.0)
    return Q.Library(Q.REPO, pages)


def test_a_quote_counts_only_when_code_finds_it_on_the_fetched_page(tmp_path: Path) -> None:
    library = _library(tmp_path)
    found, missing = A.quote_outcomes(
        FX.SITE_A,
        [WC4.Quote(**FX.Q_DATE), WC4.Quote(FX.WIKI, "t", "They date to about 5000 BC exactly.")],
        library,
        checked=FX.TEXT_A,
    )
    assert (found.verified, found.outcome) == (True, Q.FOUND)
    assert (missing.verified, missing.outcome) == (False, Q.NOT_FOUND)


def test_a_quote_on_a_copy_of_our_own_text_never_counts(tmp_path: Path) -> None:
    """The Phase-4 mirror rule on the checked text: a non-Wikipedia page that shares 25 words with
    the description proves nothing about it, even where the quote is found verbatim."""
    library = _library(tmp_path)
    (copied,) = A.quote_outcomes(
        FX.SITE_A,
        [WC4.Quote(FX.COPY, "copy", "The Tarxien Temples are an archaeological complex")],
        library,
        checked=FX.TEXT_A,
    )
    assert (copied.verified, copied.outcome) == (False, A.MIRROR)


def test_a_found_quote_whose_title_the_page_does_not_carry_does_not_count(tmp_path: Path) -> None:
    """The citation list publishes the title: one the page's text lacks (the tab title's suffix,
    an invented name) does not count; the heading, whitespace and case aside, does."""
    library = _library(tmp_path)
    text = "They date to approximately 3150 BC."
    outcomes = A.quote_outcomes(
        FX.SITE_A,
        [
            WC4.Quote(FX.WIKI, "Tarxien Temples - Wikipedia", text),
            WC4.Quote(FX.WIKI, "The Temples of Tarxien", text),
            WC4.Quote(FX.MUSEUM, "tarxien   TEMPLES", FX.Q_ZAMMIT["quote"]),
        ],
        library,
        checked=FX.TEXT_A,
    )
    assert [(o.verified, o.outcome) for o in outcomes] == [
        (False, A.TITLE_NOT_ON_PAGE),
        (False, A.TITLE_NOT_ON_PAGE),
        (True, Q.FOUND),
    ]


def test_the_fetcher_speaks_with_the_projects_user_agent_and_no_personal_data() -> None:
    client = A.Client()
    try:
        assert client.session.headers["User-Agent"] == research_web.USER_AGENT
    finally:
        client.close()
    assert "@" not in A.USER_AGENT


def test_a_host_that_refuses_the_connection_is_a_failed_fetch_not_a_crash(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    dead = "https://dead.example.org/page"
    C.fetch([dead], pages, client=FX.FakeClient(), pace=0.0)
    (refused,) = A.quote_outcomes(
        FX.SITE_A, [WC4.Quote(dead, "t", "a quote of twenty characters")],
        Q.Library(Q.REPO, pages), checked=FX.TEXT_A,
    )  # fmt: skip
    assert (refused.verified, refused.outcome) == (False, Q.FETCH_FAILED)
    assert "ConnectionError" in refused.detail


def test_a_failed_fetch_is_recorded_and_its_quote_does_not_count(tmp_path: Path) -> None:
    client = FX.FakeClient(status={FX.MUSEUM: 403})
    library = _library(tmp_path, client)
    (refused,) = A.quote_outcomes(FX.SITE_A, [WC4.Quote(**FX.Q_ZAMMIT)], library, checked=FX.TEXT_A)
    assert (refused.verified, refused.outcome) == (False, Q.FETCH_FAILED)


# ------------------------------------------------------------------------------ the frozen texts
#: The byte hashes of the frozen texts. A changed text makes every exported answer stale: re-pin
#: it here with the reason, and export a new round. CHECK_QUESTION re-pinned 2026-09-26 (the
#: review's fix round): rule 5 names the trim's new refusals - a cut inside a word or number,
#: the final mark, a telling or doubt of the sentence, a report of it, a negation's clause.
PINS = {
    "CHECK_QUESTION": "19dc88e3c078231e003eda41d22d82cf3e0c5fab17c50edfa54557763c0c81b9",
    "REASK_BLOCK": "e1c324db3e2571e70c42bf31f6d5594524014eec67ac0093b9afb0901c92960d",
    "CHECK_BRIEF": "5844ec9957fc97e651c2d1aead3edc08204e7a2eda981c0f02cfb1098d5291e5",
    "JUDGE_QUESTION": "6aba7d0af909bcfeb5a25766696404ecc0043ff1858bec231d247f00924d495d",
    "JUDGE_BRIEF": "69add49e539ba7df7ec4a2ed26d16fbb97c2f88d7f13c418fadf136a6db38a6a",
}


def test_the_questions_and_briefs_are_pinned_byte_for_byte() -> None:
    measured = {name: hashlib.sha256(getattr(P, name).encode("utf-8")).hexdigest() for name in PINS}
    assert measured == PINS


# ------------------------------------------------------------------------------ the run
class _Runner:
    """The read-only production seam: answers exactly `cli.WC_SQL`."""

    def __init__(self, rows):
        self.rows = rows
        self.sent: list[str] = []

    def __call__(self, sql: str, *, host: str) -> str:
        self.sent.append(sql)
        assert sql == C.WC_SQL
        return "".join(json.dumps(row) + "\n" for row in self.rows)


def _rows() -> list[dict]:
    text_b = "The Hypogeum lies in Paola. It was carved about 4000 BC."
    text_c = "Giants built it in one night. It glows at dusk."
    return [
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A)),
        FX.row(FX.SITE_B, text_b, raw_data=None, name="Hal Saflieni"),
        FX.row(FX.SITE_C, text_c, raw_data=FX.legacy_raw(text_c), name="Ggantija"),
        FX.row(FX.SITE_D, "Retired text.", raw_data=None, scope_status="retired", name="Gone"),
        FX.row(
            "0e000000-0000-4000-8000-00000000000e",
            "A Phase-4 text.",
            raw_data={M.PROVENANCE_KEY: {"lane": "W"}},
        ),
        FX.row("0f000000-0000-4000-8000-00000000000f", None, raw_data=None),
    ]


def _run(tmp_path: Path, rows=None, **export) -> tuple[Path, Path]:
    run, handoff = tmp_path / "runs" / "wc-test", tmp_path / "handoff" / "wc-test-r1"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=_Runner(_rows() if rows is None else rows))
    options = {"batch_size": 2, "exclude": None, "after": [], "pilot": None, "seed": None}
    C.cmd_export(run, handoff, **{**options, **export})
    return run, handoff


def test_the_read_is_phase4s_plan_read_with_the_scope_status_and_nothing_written(
    tmp_path: Path,
) -> None:
    assert C.WC_SQL.replace("u.scope_status, ", "", 1) == C.plan4.PLAN_SQL
    run = tmp_path / "run"
    run.mkdir()
    record = C.cmd_read(run, runner=_Runner(_rows()))
    assert record["rows"] == 6
    assert record["sha256"] == hashlib.sha256((run / C.ROWS_FILE).read_bytes()).hexdigest()


def test_the_population_is_every_march_text_that_stays_and_lists_the_rest(tmp_path: Path) -> None:
    run, handoff = _run(tmp_path)
    population = json.loads((run / C.POPULATION_FILE).read_text(encoding="utf-8"))
    assert population["population"] == 3
    assert population["by_marking"] == {"L": 2, "march-unmarked": 1}
    assert population["listed_counts"] == {"no-description": 1, "phase4-text": 1, "retired": 1}
    sites = C.read_sites(run)
    assert list(sites) == [FX.SITE_A, FX.SITE_B, FX.SITE_C]
    assert sites[FX.SITE_A]["sentences"] == list(FX.SENTENCES_A)
    lines = OH.manifest(handoff)
    assert [(line["batch_id"], line["label"]) for line in lines] == [
        ("wc-0001", FX.SITE_A), ("wc-0001", FX.SITE_B), ("wc-0002", FX.SITE_C)
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ({WC4.CHECK_KEY: {"v": 1}}, "checked-before"),
        ({M.PROVENANCE_KEY: {"lane": "L"}}, "provenance-unreadable"),
        ({M.PROVENANCE_KEY: M.LegacyProvenance(desc_sha256="a" * 64).to_dict()},
         "provenance-hash-differs"),
    ],
)  # fmt: skip
def test_a_text_the_lane_cannot_check_as_it_stands_is_listed(tmp_path, raw, reason) -> None:
    run, _ = _run(tmp_path, rows=[FX.row(FX.SITE_A, FX.TEXT_A, raw_data=raw),
                                  FX.row(FX.SITE_B, "A second text stands here.")])  # fmt: skip
    listed = json.loads((run / C.POPULATION_FILE).read_text(encoding="utf-8"))["listed"]
    assert listed == {reason: [FX.SITE_A]}


def test_a_chunk_asks_the_first_sites_and_the_next_chunk_goes_on_after_it(tmp_path: Path) -> None:
    first, _ = _run(tmp_path / "one", limit=2)
    assert list(C.read_sites(first)) == [FX.SITE_A, FX.SITE_B]
    record = json.loads((first / C.POPULATION_FILE).read_text(encoding="utf-8"))
    assert (record["population"], record["asked"], record["limit"]) == (3, 2, 2)
    second, _ = _run(tmp_path / "two", limit=2, after=[first])
    assert list(C.read_sites(second)) == [FX.SITE_C]
    with pytest.raises(C.WcRunError, match="population is empty"):
        _run(tmp_path / "three", after=[first, second])
    for bad in ({"limit": 0}, {"limit": 2, "pilot": 1, "seed": 7}):
        with pytest.raises(C.WcRunError, match="--limit"):
            _run(tmp_path / f"bad-{len(bad)}", **bad)


def test_excluded_and_earlier_sites_are_listed_not_asked(tmp_path: Path) -> None:
    earlier, _ = _run(tmp_path / "one", limit=1)
    exclude = tmp_path / "exclude.txt"
    exclude.write_text(FX.SITE_B + "\n", encoding="utf-8")
    run, _ = _run(tmp_path / "two", exclude=exclude, after=[earlier])
    listed = json.loads((run / C.POPULATION_FILE).read_text(encoding="utf-8"))["listed"]
    assert listed["excluded"] == [FX.SITE_B]
    assert listed["earlier-run"] == [FX.SITE_A]
    assert list(C.read_sites(run)) == [FX.SITE_C]


@pytest.mark.parametrize(
    "line",
    ["zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz", FX.SITE_B.upper(), FX.SITE_B.replace("-", "")],
)
def test_an_exclude_file_takes_canonical_site_ids_only(tmp_path: Path, line: str) -> None:
    """The id check is `revert4.check_site` (a lowercase, hyphenated UUID), not a look-alike."""
    exclude = tmp_path / "exclude.txt"
    exclude.write_text(f"{FX.SITE_A}\n\n{line}\n", encoding="utf-8")
    with pytest.raises(C.WcRunError, match=r"exclude\.txt:3: .* is not a site id"):
        _run(tmp_path, exclude=exclude)


def test_the_pilot_is_a_seeded_draw_of_the_population(tmp_path: Path) -> None:
    first, _ = _run(tmp_path / "one", pilot=2, seed=7)
    again, _ = _run(tmp_path / "two", pilot=2, seed=7)
    assert list(C.read_sites(first)) == list(C.read_sites(again))
    assert len(C.read_sites(first)) == 2
    with pytest.raises(C.WcRunError, match="go together"):
        _run(tmp_path / "three", pilot=2)


def test_the_question_shows_the_site_its_sentences_and_asks_every_one(tmp_path: Path) -> None:
    run, handoff = _run(tmp_path)
    (line,) = [line for line in OH.manifest(handoff) if line["label"] == FX.SITE_A]
    prompt = (handoff / line["prompt_path"]).read_text(encoding="utf-8")
    assert "coordinates: 35.86920, 14.51220" in prompt
    assert "S2: They date to approximately 3150 BC, and they were built by giants." in prompt
    assert "[1]" not in prompt.split("THE SENTENCES", 1)[1].split("DECIDE", 1)[0]
    assert "for each of the sentences S1, S2, S3" in prompt
    assert f'"site_id": "{FX.SITE_A}"' in prompt


def test_the_brief_names_the_batchs_own_scratch_and_the_commands(tmp_path: Path) -> None:
    run, handoff = _run(tmp_path)
    text = C.brief(run, handoff, "wc-0002")
    assert "1 question(s)" in text and "wc-test-r1-scratch/wc-0002/<label>.json" in text
    assert "wc/cli.py check-answer" in text and "--answered-by opus-check-r1-wc-0002" in text
    with pytest.raises(C.WcRunError, match="no batch"):
        C.brief(run, handoff, "wc-0009")


def _answers_round_1() -> dict[str, str]:
    return {
        FX.SITE_A: FX.answer(FX.SITE_A, [
            FX.keep(1, FX.Q_COMPLEX),
            FX.trimmed(2, ", and they were built by giants", FX.Q_DATE),
            FX.keep(3, FX.quote(FX.MUSEUM, "Zammit dug at Tarxien in the year 1915.")),
        ]),
        FX.SITE_B: FX.answer(FX.SITE_B, [
            FX.drop(1, "unsupported"),
            FX.keep(2, FX.Q_DATE),
        ]),
        FX.SITE_C: FX.answer(FX.SITE_C, [FX.drop(1), FX.drop(2)]),
    }  # fmt: skip


def test_check_answer_says_what_fails_and_what_text_the_answer_leaves(tmp_path: Path) -> None:
    run, handoff = _run(tmp_path)
    clean, report = C.check_answer(
        run, handoff, "wc-0001", FX.SITE_A, _answers_round_1()[FX.SITE_A],
        client=FX.FakeClient(), pace=0.0,
    )  # fmt: skip
    assert not clean
    assert "S1 KEEP: counts" in report and "S3 KEEP: DOES NOT COUNT" in report
    assert (
        "the text this answer leaves: The Tarxien Temples are an archaeological complex" in report
    )
    assert (handoff / "wc-0001" / "pages").is_dir()
    ok, _ = C.check_answer(
        run, handoff, "wc-0001", FX.SITE_A,
        FX.answer(FX.SITE_A, [FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE),
                              FX.keep(3, FX.Q_ZAMMIT)]),
        client=FX.FakeClient(), pace=0.0,
    )  # fmt: skip
    assert ok
    shape, report = C.check_answer(run, handoff, "wc-0001", FX.SITE_A, "{}", fetch_pages=False)
    assert not shape and report.startswith("NOT IN SHAPE")


def _import(run: Path, handoff: Path, answers: dict[str, str], **client) -> dict:
    FX.record_answers(handoff, answers)
    return C.cmd_import(run, handoff, client=FX.FakeClient(**client), pace=0.0)


def test_a_round_is_imported_only_when_every_answer_validates(tmp_path: Path) -> None:
    run, handoff = _run(tmp_path)
    FX.record_answers(handoff, {FX.SITE_A: _answers_round_1()[FX.SITE_A]})
    with pytest.raises(C.WcRunError, match="2 missing"):
        C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)


def test_a_sentence_whose_quote_fails_is_reasked_once_then_dropped(tmp_path: Path) -> None:
    run, handoff = _run(tmp_path)
    summary = _import(run, handoff, _answers_round_1())
    assert summary["to_reask"] == 1 and summary["sites_to_reask"] == 1
    reask = json.loads((run / "round-1" / "REASK.json").read_text(encoding="utf-8"))
    assert list(reask) == [FX.SITE_A] and list(reask[FX.SITE_A]) == ["3"]
    with pytest.raises(C.WcRunError, match="re-ask it first|export-reask"):
        C.cmd_build(run, first_batch=4001)

    second = tmp_path / "handoff" / "wc-test-r2"
    C.cmd_export_reask(run, second, batch_size=5)
    (line,) = OH.manifest(second)
    prompt = (second / line["prompt_path"]).read_text(encoding="utf-8")
    assert "RE-ASK" in prompt and "S3: the quote on " + FX.MUSEUM in prompt
    assert "for each of the sentences S3" in prompt
    _import(run, second, {FX.SITE_A: FX.answer(FX.SITE_A, [FX.keep(3, FX.Q_ZAMMIT)])})
    with pytest.raises(C.WcRunError, match="once"):
        C.cmd_export_reask(run, tmp_path / "handoff" / "wc-test-r3", batch_size=5)

    summary = C.cmd_build(run, first_batch=4001)
    assert summary["sites"] == 3 and summary["cleared"] == 2
    finals = C._finals(run)
    assert finals[FX.SITE_A]["description"] == (
        "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]. "
        "They date to approximately 3150 BC [1]. "
        "The site was excavated by Themistocles Zammit in 1915 [2]."
    )
    # site B: its first sentence dropped, and the second leans on it ("It was carved ...")
    assert finals[FX.SITE_B]["cleared"] is True
    assert [d["reason"] for d in finals[FX.SITE_B]["decisions"]] == [
        "unsupported", "leans-on-dropped"
    ]  # fmt: skip
    assert finals[FX.SITE_C]["cleared"] is True


def test_a_sentence_still_failing_after_the_reask_round_is_dropped_unverified(
    tmp_path: Path,
) -> None:
    """The museum refuses the import's fetch in round 1; a page is fetched once per run, so the
    re-ask's quote on it fails too, and the sentence is dropped as unverified."""
    run, handoff = _run(tmp_path)
    _import(run, handoff, _answers_round_1(), status={FX.MUSEUM: 403})
    second = tmp_path / "handoff" / "wc-test-r2"
    C.cmd_export_reask(run, second, batch_size=5)
    (line,) = OH.manifest(second)
    assert "status 403" in (second / line["prompt_path"]).read_text(encoding="utf-8")
    _import(run, second, {FX.SITE_A: FX.answer(FX.SITE_A, [FX.keep(3, FX.Q_ZAMMIT)])})
    C.cmd_build(run, first_batch=4001)
    decisions = C._finals(run)[FX.SITE_A]["decisions"]
    assert (decisions[2]["verdict"], decisions[2]["reason"]) == ("DROP", "unverified")


def test_the_import_counts_only_pages_it_fetched_itself(tmp_path: Path) -> None:
    """A page the batch agent's `check-answer` stored (or one written into that store by hand)
    is never the import's evidence: the import fetches into the run's own store."""
    run, handoff = _run(tmp_path)
    forged = FX.FakeClient(pages={**FX.PAGES, FX.MUSEUM: FX.PAGES[FX.MUSEUM].replace(
        "Excavations at Tarxien", "Zammit dug at Tarxien in the year 1915. Excavations at Tarxien")})  # fmt: skip
    clean, _ = C.check_answer(
        run, handoff, "wc-0001", FX.SITE_A, _answers_round_1()[FX.SITE_A], client=forged, pace=0.0
    )
    assert clean  # the agent's store holds the forged page
    summary = _import(run, handoff, _answers_round_1())
    assert summary["to_reask"] == 1  # the import's own fetch does not carry the quote
    assert (run / C.PAGES_DIR).is_dir()
    assert not (handoff / "wc-0002" / "pages").exists()


def test_an_answer_out_of_shape_at_import_is_reasked_whole(tmp_path: Path) -> None:
    run, handoff = _run(tmp_path)
    answers = {**_answers_round_1(), FX.SITE_C: FX.answer(FX.SITE_C, [FX.drop(1)])}
    summary = _import(run, handoff, answers)
    assert summary["not_in_shape"] == 1
    reask = json.loads((run / "round-1" / "REASK.json").read_text(encoding="utf-8"))
    assert sorted(reask[FX.SITE_C]) == ["1", "2"]


def test_a_changed_question_is_never_imported(tmp_path: Path, monkeypatch) -> None:
    run, handoff = _run(tmp_path)
    FX.record_answers(handoff, _answers_round_1())
    monkeypatch.setattr(C.P, "CHECK_QUESTION", C.P.CHECK_QUESTION.replace("RULES", "RULES:"))
    with pytest.raises(C.WcRunError, match="not this question's"):
        C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)


def _built(tmp_path: Path) -> Path:
    run, handoff = _run(tmp_path)
    answers = _answers_round_1()
    answers[FX.SITE_A] = FX.answer(FX.SITE_A, [
        FX.keep(1, FX.Q_COMPLEX),
        FX.trimmed(2, ", and they were built by giants", FX.Q_DATE),
        FX.keep(3, FX.Q_ZAMMIT, FX.Q_ZAMMIT_WIKI),
    ])  # fmt: skip
    _import(run, handoff, answers)
    C.cmd_build(run, first_batch=4001)
    return run


def test_the_gate_plan_holds_every_outcome_with_its_evidence_and_the_invariants(
    tmp_path: Path,
) -> None:
    run = _built(tmp_path)
    (record,) = [json.loads(line) for line in (run / C.PLAN_FILE).read_text("utf-8").splitlines()]
    assert (record["batch_id"], record["pass"]) == ("p4-4001", WC4.PLAN_MARK)
    assert [s["site_id"] for s in record["sites"]] == [FX.SITE_A, FX.SITE_B, FX.SITE_C]
    for data in record["outcomes"]:
        outcome = WC4.WcOutcome.from_dict(data)
        assert WC4.wc_problems(outcome.description, outcome.raw_data) == []
        assert WC4.evidence_problems(outcome.evidence, outcome.description, outcome.raw_data) == []
    a = WC4.WcOutcome.from_dict(record["outcomes"][0])
    assert a.description.endswith("in 1915 [1] [2].")  # the museum is [2], quoted first
    evidence = a.evidence
    assert evidence["checked"] == FX.TEXT_A and evidence["checker"] == M.AI_SYSTEM
    assert evidence["kept"] == 3 and evidence["of"] == 3
    assert evidence["sentences"][2]["quotes"][0]["verified"] is True
    assert evidence["answers"][0]["answered_by"] == "opus-check-wc-0001"
    with pytest.raises(C.WcRunError, match="starts at 4001"):
        C.cmd_build(run, first_batch=901)


def test_the_evidence_recheck_goes_red_on_a_moved_text(tmp_path: Path) -> None:
    run = _built(tmp_path)
    outcome = WC4.WcOutcome.from_dict(
        json.loads((run / C.PLAN_FILE).read_text("utf-8").splitlines()[0])["outcomes"][0]
    )
    moved = outcome.description.replace("Malta", "Gozo")
    assert "the description is not what the journal evidence composes" in (
        WC4.evidence_problems(outcome.evidence, moved, outcome.raw_data)
    )
    other = {**outcome.raw_data, WC4.CHECK_KEY: {**outcome.raw_data[WC4.CHECK_KEY], "run": "x"}}
    assert WC4.evidence_problems(outcome.evidence, outcome.description, other)
    # a March text that lost its AI footnote holds every invariant, and the evidence says so
    assert outcome.evidence["marking"]["old"] == "L"
    unmarked = {k: v for k, v in outcome.raw_data.items() if k != M.PROVENANCE_KEY}
    assert WC4.wc_problems(outcome.description, unmarked) == []
    assert any(
        "AI disclosure" in problem
        for problem in WC4.evidence_problems(outcome.evidence, outcome.description, unmarked)
    )


# ------------------------------------------------------------------------------ the judge
def _judge_run(tmp_path: Path) -> tuple[Path, Path]:
    run = _built(tmp_path)
    handoff = tmp_path / "handoff" / "wc-test-judge"
    C.cmd_judge_export(run, handoff, batch_size=5)
    return run, handoff


def _judgement(site_id: str, kept: list[str], dropped: list[str], coherent: bool = True) -> str:
    return json.dumps({
        "site_id": site_id,
        "kept": [{"k": k, "verdict": v, "quotes": [Q_DATE_J] if v == "WRONG" else [],
                  "note": "judged"} for k, v in enumerate(kept, start=1)],
        "dropped": [{"d": d, "verdict": v, "quotes": [], "note": "judged"}
                    for d, v in enumerate(dropped, start=1)],
        "coherent": coherent,
        "note": "judged",
    })  # fmt: skip


Q_DATE_J = {"url": FX.WIKI, "quote": "They date to approximately 3150 BC."}


def _judge(run: Path, handoff: Path, answers: dict[str, str], by: str = "opus-judge") -> dict:
    FX.record_answers(handoff, answers, by=by)
    return C.cmd_judge_import(run, handoff, client=FX.FakeClient(), pace=0.0)


def test_the_pilot_judge_sees_the_kept_text_with_its_quotes_and_the_drops(tmp_path: Path) -> None:
    run, handoff = _judge_run(tmp_path)
    lines = {line["label"]: line for line in OH.manifest(handoff)}
    prompt = (handoff / lines[FX.SITE_A]["prompt_path"]).read_text(encoding="utf-8")
    assert "K2: They date to approximately 3150 BC." in prompt
    assert (
        '    trimmed from: "They date to approximately 3150 BC, and they were built by giants."'
        in (prompt)
    )
    assert f'    quote: "They date to approximately 3150 BC." - {FX.WIKI}' in prompt
    assert "(3 kept, 0 dropped)" in prompt
    prompt_c = (handoff / lines[FX.SITE_C]["prompt_path"]).read_text(encoding="utf-8")
    assert "(none - the description is cleared)" in prompt_c
    assert "--answered-by opus-wc-judge-judge-0001" in C.judge_brief(run, handoff, "judge-0001")


def test_the_pilot_passes_only_below_every_threshold(tmp_path: Path) -> None:
    run, handoff = _judge_run(tmp_path)
    good = {
        FX.SITE_A: _judgement(FX.SITE_A, ["SUPPORTED"] * 3, []),
        FX.SITE_B: _judgement(FX.SITE_B, [], ["DROP_OK", "DROP_OK"]),
        FX.SITE_C: _judgement(FX.SITE_C, [], ["DROP_OK", "DROP_OK"]),
    }
    result = _judge(run, handoff, good)
    assert result["passed"] and result["measured"]["kept_sentences"] == 3


@pytest.mark.parametrize(
    ("kept", "coherent", "failure"),
    [
        (["SUPPORTED", "WRONG", "SUPPORTED"], True, "WRONG with a found quote"),
        (["SUPPORTED", "UNSUPPORTED", "SUPPORTED"], True, "UNSUPPORTED, above 5 %"),
        (["SUPPORTED"] * 3, False, "incoherent"),
    ],
)
def test_a_wrong_an_unsupported_share_or_an_incoherent_text_fails_the_pilot(
    tmp_path, kept, coherent, failure
) -> None:
    run, handoff = _judge_run(tmp_path)
    answers = {
        FX.SITE_A: _judgement(FX.SITE_A, kept, [], coherent),
        FX.SITE_B: _judgement(FX.SITE_B, [], ["DROP_OK", "DROP_OK"]),
        FX.SITE_C: _judgement(FX.SITE_C, [], ["DROP_OK", "DROP_OK"]),
    }
    result = _judge(run, handoff, answers)
    assert not result["passed"] and any(failure in f for f in result["failures"])


def test_a_judge_who_checked_the_site_is_not_independent(tmp_path: Path) -> None:
    run, handoff = _judge_run(tmp_path)
    answers = {
        label: _judgement(label, ["SUPPORTED"] * 3, []) if label == FX.SITE_A
        else _judgement(label, [], ["DROP_OK", "DROP_OK"])
        for label in (FX.SITE_A, FX.SITE_B, FX.SITE_C)
    }  # fmt: skip
    # the checkers answered as opus-check-wc-0001/-0002; this judge reuses that name
    FX.record_answers(handoff, answers, by="opus-check")
    for line in OH.manifest(handoff):
        stored = json.loads((handoff / line["answer_path"]).read_text(encoding="utf-8"))
        stored["answered_by"] = "opus-check-wc-0001"
        (handoff / line["answer_path"]).write_text(json.dumps(stored), encoding="utf-8")
    result = C.cmd_judge_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert not result["passed"]
    assert any("judged by one of their checkers" in f for f in result["failures"])


def test_judge_check_answer_reads_the_shape_only(tmp_path: Path) -> None:
    run, handoff = _judge_run(tmp_path)
    assert C.judge_check_answer(run, handoff, "judge-0001", FX.SITE_A,
                                _judgement(FX.SITE_A, ["SUPPORTED"] * 3, [])) is None  # fmt: skip
    problem = C.judge_check_answer(
        run, handoff, "judge-0001", FX.SITE_A,
        _judgement(FX.SITE_A, ["SUPPORTED"] * 2, []),
    )  # fmt: skip
    assert "kept covers" in problem


def test_the_command_line_prints_its_own_exit_line(tmp_path: Path, capsys) -> None:
    code = C.main(["brief", "--run-dir", str(tmp_path / "none"), "--handoff", str(tmp_path),
                   "--batch-id", "wc-0001"])  # fmt: skip
    out = capsys.readouterr()
    assert code == 1 and out.out.strip().endswith("WC_EXIT=1") and "REFUSED" in out.err


def test_the_decision_record_stays_a_plain_dataclass() -> None:
    decision = _d(1, "A temple in Malta stands here.")
    assert dataclasses.asdict(decision)["verdict"] == "KEEP"
