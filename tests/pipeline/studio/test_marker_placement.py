"""`normalize_marker_placement`: the one habit behind 113 of paper 1's findings.

Measured 2026-10-04 on the real workspace `95fa3798-1678-40a4-ae2e-58595de93918`
(90 references, all 90 with local source text): `paper check` reported 118 support
findings - 78 `located_sentence`, 38 `sentence_defect` (35 `no_clause_after_marker`,
3 `fragment_after_marker`), 1 `number_exact`, 1 `unsupported_specific`. 113 of them
came from one thing, the marker written *after* the full stop instead of before it.
The literal below is that paper's own paragraph.

The move has one answer, which is why it is code and not a writer instruction: a
marker that follows a full stop can only annotate the sentence before it, because
that is the only sentence a marker in that position could mean.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest

from pipeline.lyra.paper_claim_gate import check_sentence_structure
from pipeline.studio.paper.numbering import S_MARKER_RE, normalize_marker_placement

#: Workspace 95fa3798, "UFOs Over Nuclear Sites", as the writer left it: three
#: misplaced marker runs, one of them three markers long.
REAL_PARAGRAPH = (
    "The 1968 Condon Report, commissioned by the Air Force and conducted at the "
    "University of Colorado, concluded that further extensive study of UFOs probably "
    "could not be scientifically justified. [S:262eb541b9f7] The 1997 Sturrock Panel, "
    "convened at Stanford with funding from Laurance Rockefeller, found that some UAP "
    "cases have physical evidence worthy of study, but explicitly concluded it was "
    '"not convinced that any of this evidence points to a violation of known natural '
    'laws or the involvement of an extraterrestrial intelligence". In March 2024, '
    "AARO's Historical Record Report Vol. 1 found \"no verifiable evidence that any UAP "
    'sighting has represented extraterrestrial activity" and "no empirical evidence" '
    "for reverse-engineering programs. [S:e697b76fa2b9] [S:1db5e3da4879] "
    "[S:47aac844e468] A June 2025 Wall Street Journal investigation reported that AARO "
    "attributed the 1967 Malmstrom shutdown to a classified electromagnetic-pulse "
    "(EMP) test. [S:05687d661462] The 1997 Sturrock Panel found that some UAP cases."
)

#: The house form, the way the gate reads it: "[N]" and no run behind a full stop.
#: A run of one or more markers between a sentence end and the next word is the defect,
#: whether the markers are draft ids or numbers.
RUN_AFTER_STOP_RE = re.compile(r"[.!?…][ \t]+(?:\[[SN]:[^\]]+\][ \t]*)+(?=[^\s])")

#: What `number_draft`'s registry assigned to the five sources above.
NUMBER_OF = {
    "262eb541b9f7": "63",
    "e697b76fa2b9": "43",
    "1db5e3da4879": "64",
    "47aac844e468": "21",
    "05687d661462": "65",
}


def numbered(text: str) -> str:
    """`number_draft`'s second half, on a text whose first half is already done."""
    return re.sub(r"\[S:([0-9a-f]{12})\]", lambda m: f"[{NUMBER_OF[m.group(1)]}]", text)


def sentence_defect_kinds(report: str) -> list[str]:
    """The kinds the gate reports. The rule is `sentence_defect` for all of them, and
    the kind is the first word of the detail, so reading the rule alone tells nothing."""
    return [
        issue.detail.split(" ")[0]
        for issue in check_sentence_structure(report)
        if issue.rule == "sentence_defect"
    ]


def test_no_marker_run_stands_after_a_full_stop_any_more():
    """The whole contract: the defect is gone, and nothing but its place was touched.

    The marker multiset and the character count are the two invariants that make this a
    move and not an edit - a lost or doubled marker would show up in both.
    """
    assert RUN_AFTER_STOP_RE.search(REAL_PARAGRAPH), "the real paragraph is the fixture"

    out = normalize_marker_placement(REAL_PARAGRAPH)

    assert RUN_AFTER_STOP_RE.search(out) is None
    assert Counter(S_MARKER_RE.findall(out)) == Counter(S_MARKER_RE.findall(REAL_PARAGRAPH))
    assert len(out) == len(REAL_PARAGRAPH)


def test_the_first_misplaced_marker_lands_before_the_full_stop_it_followed():
    """A marker behind a full stop annotates the *following* sentence, which is how
    78 `located_sentence` findings arose: the gate asked the Condon source to carry
    the Sturrock sentence."""
    out = normalize_marker_placement(REAL_PARAGRAPH)
    assert "scientifically justified [S:262eb541b9f7]. The 1997 Sturrock Panel" in out


def test_a_three_marker_run_keeps_its_order_and_lands_as_one_run():
    out = normalize_marker_placement(REAL_PARAGRAPH)
    assert (
        "programs [S:e697b76fa2b9] [S:1db5e3da4879] [S:47aac844e468]. A June 2025" in out
    )


def test_the_gate_rule_that_fired_stops_firing():
    """The coupling that makes this worth having as code: three misplaced runs in,
    three `no_clause_after_marker` findings, and none out."""
    before = numbered(REAL_PARAGRAPH)
    after = numbered(normalize_marker_placement(REAL_PARAGRAPH))

    assert sentence_defect_kinds(before) == ["no_clause_after_marker"] * 3
    assert sentence_defect_kinds(after) == []


def test_a_marker_after_a_closing_quotation_mark_goes_outside_the_quote():
    """`...an extraterrestrial intelligence". [S:a] Next` - the marker belongs after the
    closing quote and before the full stop, not inside the quotation."""
    out = normalize_marker_placement('he concluded it was "a violation" [S:aaaabbbbcccc]. Next.')
    assert out == 'he concluded it was "a violation" [S:aaaabbbbcccc]. Next.'


def test_a_marker_that_opens_a_paragraph_is_left_where_the_writer_put_it():
    """There is no preceding sentence for it to belong to, and guessing one is the
    writer's decision - the support gate reports it as unreadable or unsupported."""
    draft = "[S:aaaabbbbcccc] The quarry is 1,000 metres long."
    assert normalize_marker_placement(draft) == draft


def test_a_marker_inside_a_sentence_is_not_touched():
    draft = "The block weighs 1,000 tons [S:aaaabbbbcccc], as the survey records."
    assert normalize_marker_placement(draft) == draft


def test_a_paragraph_below_a_heading_is_normalised_like_any_other():
    """A heading is not a sentence, so the run after its paragraph's first full stop is
    the ordinary case and the heading must not become the marker's host."""
    draft = "## The Quarry Blocks\n\nThe block weighs 1,000 tons. [S:aaaabbbbcccc] Next."
    assert normalize_marker_placement(draft) == (
        "## The Quarry Blocks\n\nThe block weighs 1,000 tons [S:aaaabbbbcccc]. Next."
    )


def test_a_run_of_several_markers_keeps_its_order():
    draft = "It concluded so [S:111111111111] [S:222222222222] [S:333333333333]. Next."
    assert normalize_marker_placement(draft) == (
        "It concluded so [S:111111111111] [S:222222222222] [S:333333333333]. Next."
    )


def test_a_bare_numeric_marker_is_not_this_functions_business():
    """draft_problems refuses bare [1] before numbering ever sees it, and a bare
    number in a stored report is not the writer's marker grammar."""
    assert normalize_marker_placement("It concluded so. [1] Next.") == "It concluded so. [1] Next."


@pytest.mark.parametrize("tail", ['"', "'", ")", "]", "»"])
def test_every_closing_character_a_marked_sentence_can_end_on(tail):
    draft = f'he wrote "a violation"{tail} [S:aaaabbbbcccc]. Next.'
    assert normalize_marker_placement(draft) == f'he wrote "a violation"{tail} [S:aaaabbbbcccc]. Next.'
