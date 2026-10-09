"""Calibration teaser-2026-10-09b/c repair, 2026-10-10: what a contradiction is, a claim the sources
dispute, and the checker's qualifier step.

The web verifier falsely contradicted 7 of 20 recorded VERIFIED cards (Opus) and the adversarial
reviewer failed 12 of 25 clean cards: rounding, an overlapping range, a compatible estimate, a naming
convention and genuinely disputed claims were called contradictions. A reputable source that says
something incompatible is a contradiction; where reputable sources disagree among themselves the
claim is DISPUTED (a card that states it must hedge it or drop it); and a checker lists the
qualifiers of each claim's basis sentence and confirms each survives in the card.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import web_rules as WR  # noqa: E402
from teaser import answers as A  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import prompts_shorts as PS  # noqa: E402
from teaser import run as R  # noqa: E402
from teaser import shorts_v1 as SV  # noqa: E402

from tests.remediation import shorts_cases as S  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402

PAGE = "https://example.org/page"
QUOTE = "the earliest phase is dated to the seventh century"


def claim(verdict: str = "SUPPORTED", *, proven: bool = True, text: str = "c") -> dict[str, Any]:
    url = None if verdict == "UNVERIFIABLE" else PAGE
    quote = None if verdict == "UNVERIFIABLE" else QUOTE
    return {"claim": text, "verdict": verdict, "url": url, "quote": quote, "proven": proven}


def judge_text(*claims: dict[str, Any]) -> str:
    return T.judge_answer(*claims)


# ------------------------------------------------------------------------------ the web rule
class TestTheContradictionRule:
    @pytest.mark.parametrize(
        "needle",
        [
            "A CONTRADICTION is a reputable source",
            "excavation report",
            "heritage register",
            "peer-reviewed paper",
            "better-sourced Wikipedia article",
            "something INCOMPATIBLE",
            "These are NOT contradictions",
            "a rounding",
            "a range that overlaps",
            "another estimate",
            "naming convention",
            "the same fact in other words",
            "DISPUTED, not contradicted",
        ],
    )
    def test_the_verifier_rule_defines_a_contradiction(self, needle: str) -> None:
        assert needle in WR.VERIFIER_RULE

    def test_the_cache_stays_no_confirmation_and_the_politeness_stays(self) -> None:
        assert "NEVER independent confirmation" in WR.VERIFIER_RULE
        assert "no cap on requests" in WR.VERIFIER_RULE
        assert "An HTTP 403 or 429 is a throttle and NEVER a finding" in WR.VERIFIER_RULE

    def test_a_researcher_is_not_given_the_contradiction_rule(self) -> None:
        assert "CONTRADICTION" not in WR.RESEARCHER_RULE

    @pytest.mark.parametrize("role", sorted(WR.VERIFIER_ROLES))
    def test_every_verifying_role_reads_the_definition(self, role: str) -> None:
        assert WR.CONTRADICTION_RULE in WR.rule_for_role(role)

    def test_the_briefs_of_the_other_lanes_that_use_the_rule_carry_it(self) -> None:
        from wc import prompts as WC  # noqa: PLC0415 - the lanes import web_rules themselves

        assert WR.CONTRADICTION_RULE in WC.WIKI_CACHE_NOTE
        assert WR.CONTRADICTION_RULE not in WC.WIKI_CACHE_NOTE_WRITER

    def test_the_card_lane_briefs_carry_it(self) -> None:
        assert WR.CONTRADICTION_RULE in R._WEB_NOTE


# ------------------------------------------------------------------------------ the answer shape
class TestTheDisputedVerdict:
    def test_a_judge_may_dispute_a_claim_with_its_page_and_quote(self) -> None:
        judged = A.parse_judge(judge_text(T.judged_claim("DISPUTED", QUOTE, PAGE, "dated early")))
        assert [(j.verdict, j.url, j.quote) for j in judged] == [("DISPUTED", PAGE, QUOTE)]

    def test_a_disputed_claim_without_a_quote_is_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="quote"):
            A.parse_judge(judge_text(T.judged_claim("DISPUTED", None, PAGE)))

    def test_a_disputed_claim_without_a_page_is_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="url"):
            A.parse_judge(judge_text(T.judged_claim("DISPUTED", QUOTE, None)))

    def test_a_short_quote_proves_no_dispute(self) -> None:
        with pytest.raises(A.AnswerError, match="characters"):
            A.parse_judge(judge_text(T.judged_claim("DISPUTED", "seventh century", PAGE)))

    def test_the_answer_shape_names_the_verdict(self) -> None:
        assert "DISPUTED" in A.JUDGE_VERDICTS and "DISPUTED" in P.JUDGE_FORMAT

    def test_a_verdict_nobody_defined_is_still_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="verdict"):
            A.parse_judge(judge_text(T.judged_claim("MAYBE", QUOTE, PAGE)))


class TestTheVerification:
    def test_a_disputed_claim_is_not_verified(self) -> None:
        claims = [claim(), claim("DISPUTED"), claim()]
        assert R.card_verification(claims) == R.DISPUTED

    def test_a_disputed_claim_is_disputed_proven_or_not(self) -> None:
        assert R.card_verification([claim(), claim("DISPUTED", proven=False)]) == R.DISPUTED

    def test_a_contradiction_outranks_a_dispute(self) -> None:
        claims = [claim(), claim("DISPUTED"), claim("CONTRADICTED", proven=False)]
        assert R.card_verification(claims) == R.CONTRADICTED

    def test_a_dispute_outranks_an_unproven_central_claim(self) -> None:
        unproven = claim("UNVERIFIABLE", proven=False)
        assert R.card_verification([unproven, claim("DISPUTED")]) == R.DISPUTED
        assert R.card_verification([unproven, claim()]) == R.UNPROVEN

    def test_the_claims_are_told_apart(self) -> None:
        record = {
            "claims": [
                claim(text="ok"),
                claim("DISPUTED", text="disputed"),
                claim("CONTRADICTED", text="contradicted"),
                claim("UNVERIFIABLE", proven=False, text="unproven"),
            ]
        }
        assert [c["claim"] for c in R.disputed_claims(record)] == ["disputed"]
        assert [c["claim"] for c in R.contradicted_claims(record)] == ["contradicted"]
        assert [c["claim"] for c in R.unproven_claims(record)] == ["unproven"]

    def test_the_findings_say_hedge_or_drop(self) -> None:
        record = {"kind": "verify", "claims": [claim(text="dated early"), claim("DISPUTED")]}
        (finding,) = P.findings_of(record)
        assert "disputed" in finding and "hedge it or drop it" in finding and PAGE in finding
        assert PS.findings_of(record) == (finding,)


class TestTheRoute:
    """A disputed card goes to the one rewrite, like a contradicted one, and is cleared with its own
    reason when the second verification still disputes it."""

    CARD, REWRITTEN = "the first card", "the rewritten card"

    def records(self, first: str, second: str | None = None) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {
            "write": {"card": self.CARD, "problems": []},
            "check": {"card": self.CARD, "verdict": "PASS"},
            "verify": {"kind": "verify", "card": self.CARD, "verdict": first, "claims": []},
        }
        if second is not None:
            rows |= {
                "rewrite-v": {"card": self.REWRITTEN, "problems": []},
                "check-v": {"card": self.REWRITTEN, "verdict": "PASS"},
                "verify2": {
                    "kind": "verify",
                    "card": self.REWRITTEN,
                    "verdict": second,
                    "claims": [],
                },
            }
        stages = {stage: {} for stage in R.STAGES}
        for stage, row in rows.items():
            stages[stage]["site-1"] = {"site_id": "site-1", "stage": stage, **row}
        return stages

    def test_a_disputed_first_verification_is_due_a_rewrite(self) -> None:
        state = R.progress("site-1", self.records(R.DISPUTED))
        assert (state.status, state.stage) == (R.DUE, R.VERIFY_REWRITE)

    def test_a_card_still_disputed_after_the_rewrite_is_cleared_as_disputed(self) -> None:
        state = R.progress("site-1", self.records(R.DISPUTED, R.DISPUTED))
        assert (state.status, state.reason) == (R.CLEARED, R.DISPUTED_AFTER_VERIFY)

    def test_a_card_contradicted_after_the_rewrite_keeps_its_own_reason(self) -> None:
        state = R.progress("site-1", self.records(R.DISPUTED, R.CONTRADICTED))
        assert state.reason == R.CONTRADICTED_AFTER_VERIFY

    def test_a_hedged_rewrite_that_verifies_is_accepted(self) -> None:
        state = R.progress("site-1", self.records(R.DISPUTED, R.VERIFIED))
        assert state.status == R.ACCEPTED

    def test_the_pilot_judge_fails_a_card_with_a_disputed_claim(self) -> None:
        assert R.JudgeTally(claims=10, supported=10).passed
        assert not R.JudgeTally(claims=10, supported=9, disputed=1).passed


# ------------------------------------------------------------------------------ the prompts
SHORTS_SITE = SV.shorts_basis(
    site_id=S.SAMPLES[0]["site_id"],
    name=S.SAMPLES[0]["name"],
    country=S.SAMPLES[0]["country"],
    description=S.SAMPLES[0]["description"],
    alt_names=[],
    pool_images=0,
    image_titles=[],
)
V1_SITE = C.basis(
    site_id=T.SKARA,
    name=T.NAMES[T.SKARA],
    country=T.COUNTRIES[T.SKARA],
    description=T.DESCRIPTIONS[T.SKARA],
    alt_names=[],
)


class TestTheJudgePrompts:
    @pytest.mark.parametrize(
        "prompt",
        [
            P.judge_prompt("Skara Brae", "Scotland", "A card."),
            PS.judge_prompt("Glaphyrae", "Greece", "A card."),
        ],
    )
    def test_a_judge_is_told_what_is_no_contradiction(self, prompt: str) -> None:
        assert "SUPPORTED, CONTRADICTED, DISPUTED or" in prompt
        assert "Decide CONTRADICTED only when a reputable source" in prompt
        assert "NOT contradictions: a rounding, a range that overlaps" in prompt
        assert "decide DISPUTED, not CONTRADICTED" in prompt

    @pytest.mark.parametrize(
        "prompt",
        [
            P.judge_prompt("Skara Brae", "Scotland", "A card."),
            PS.judge_prompt("Glaphyrae", "Greece", "A card."),
        ],
    )
    def test_a_judge_is_told_a_hedged_claim_is_supported(self, prompt: str) -> None:
        assert "A claim the text already hedges" in prompt
        assert "is SUPPORTED when the sources really disagree" in prompt

    def test_the_adversary_is_told_what_is_no_finding(self) -> None:
        prompt = PS.adversarial_prompt(
            SHORTS_SITE,
            "A card.",
            {"claims": [{"claim": "x", "support": ["S1"]}]},
            {"claims": [claim()] and [{**claim(), "quote_outcome": "found"}]},
        )
        assert "that states something incompatible with the claim as the card words it" in prompt
        assert "no finding: a rounding, a range that overlaps" in prompt
        assert "never a doubt alone" in prompt


class TestTheVerifyRewritePrompts:
    contradicted = [claim("CONTRADICTED", text="built in 1850")]
    disputed = [claim("DISPUTED", text="dated to the fourth century")]

    @pytest.mark.parametrize(
        ("build", "site"),
        [(P.verify_rewrite_prompt, V1_SITE), (PS.verify_rewrite_prompt, SHORTS_SITE)],
    )
    def test_a_disputed_claim_is_shown_with_the_hedge_or_drop_rule(
        self, build: Any, site: Any
    ) -> None:
        prompt = build(site, "A card.", self.contradicted, [], self.disputed)
        assert "DISPUTED - reputable sources disagree with each other" in prompt
        assert "dated to the fourth century" in prompt
        assert "Do not state either side as a fact: hedge it" in prompt
        # a disputed claim is not a contradicted one: it has no `repeats` entry
        assert "dated to the fourth century" not in prompt.split("DISPUTED -")[0]

    @pytest.mark.parametrize(
        ("build", "site"),
        [(P.verify_rewrite_prompt, V1_SITE), (PS.verify_rewrite_prompt, SHORTS_SITE)],
    )
    def test_without_a_dispute_the_prompt_is_the_one_it_was(self, build: Any, site: Any) -> None:
        prompt = build(site, "A card.", self.contradicted, [])
        assert "DISPUTED" not in prompt and "hedge it" not in prompt
        assert prompt == build(site, "A card.", self.contradicted, [], [])


# ------------------------------------------------------------------------------ the qualifier step
class TestTheQualifierStep:
    @pytest.mark.parametrize(
        "prompt",
        [
            P.checker_prompt(V1_SITE, "A card."),
            PS.checker_prompt(SHORTS_SITE, "A card."),
        ],
    )
    def test_a_checker_compares_the_qualifiers_of_each_claim(self, prompt: str) -> None:
        assert "QUALIFIER STEP, for every claim" in prompt
        for word in ("qualifiers", "quantifiers", "hedges", "attributions", "time anchors"):
            assert word in prompt
        for example in (
            "'largely rebuilt' and the card says 'rebuilt'",
            "'many coins' and the card says 'the coins'",
            "'according to the saga, the broch was besieged'",
            "'originally stood 62 metres high' and the card says it 'stands 62 metres high'",
        ):
            assert example in prompt
        assert "support []" in prompt

    def test_the_step_comes_after_the_claims_are_mapped_and_before_the_tone(self) -> None:
        prompt = P.checker_prompt(V1_SITE, "A card.")
        assert (
            prompt.index("2. For each claim")
            < prompt.index("QUALIFIER STEP")
            < prompt.index("3. tone_ok")
        )
