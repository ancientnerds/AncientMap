"""Lane WB, the handoff side: the card contract, the answer shapes, the prompts and the run.

Everything here is DB-less and model-less: production is a fixture export, the Opus agents are
answers written through `opus_handoff.write_answer`, the brand fonts are `phase4_cases`'
`fake_card_fit`, the web is an `httpx.MockTransport`. Each rule is asserted by the refusal it
produces, so removing it turns its test red (`mechanical/mutation_sweep.py "teaser:"`).
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from teaser import answers as A  # noqa: E402
from teaser import contract as C  # noqa: E402
from teaser import prompts as P  # noqa: E402
from teaser import run as R  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402


def basis(site_id: str = T.SKARA, alt_names: list[str] | None = None) -> C.Basis:
    return C.basis(
        site_id=site_id,
        name=T.NAMES[site_id],
        country=T.COUNTRIES[site_id],
        description=T.DESCRIPTIONS[site_id],
        alt_names=alt_names or [],
    )


# ------------------------------------------------------------------------------ the fact basis
class TestTheFactBasis:
    def test_sentences_are_numbered_without_their_markers(self) -> None:
        sentences = C.description_sentences(T.DESCRIPTIONS[T.SKARA])
        assert [s.id for s in sentences] == ["S1", "S2", "S3", "S4", "S5", "S6"]
        assert sentences[0].text.endswith("Mainland, Orkney.")
        assert not any("[" in s.text for s in sentences)

    def test_a_circa_date_does_not_end_a_sentence(self) -> None:
        sentences = C.description_sentences("It was built c. 3000 BC by farmers [2, 3]. It fell.")
        assert [s.text for s in sentences] == ["It was built c. 3000 BC by farmers.", "It fell."]

    def test_each_line_is_split_on_its_own(self) -> None:
        sentences = C.description_sentences("A mound.\n\nA ditch [4-6]. A bank.")
        assert [s.text for s in sentences] == ["A mound.", "A ditch.", "A bank."]

    def test_a_site_without_a_description_has_no_basis(self) -> None:
        with pytest.raises(ValueError, match="no published description"):
            C.basis(site_id=T.EMPTY, name="X", country="Y", description="  ", alt_names=[])


class TestTheNameForms:
    def test_a_bracketed_disambiguator_is_no_form(self) -> None:
        forms = C.name_forms("Eryx (Sicily)", [], "Eryx was a city in Sicily.")
        assert forms == ("Eryx (Sicily)", "Eryx")

    def test_a_bracket_in_the_middle_is_taken_out(self) -> None:
        forms = C.name_forms("Quesera (Cheeseboard) de Zonzamas", [], "text")
        assert "Quesera de Zonzamas" in forms

    def test_the_part_before_the_first_comma_is_a_form(self) -> None:
        assert "Gaer Hillfort" in C.name_forms("Gaer Hillfort, Trellech", [], "text")

    def test_slash_and_dash_parts_are_forms_and_a_leading_the_goes(self) -> None:
        forms = C.name_forms("The Black Pyramid- Pyramid of Amenemhat III (Dahshur)", [], "text")
        assert {"The Black Pyramid", "Black Pyramid", "Pyramid of Amenemhat III"} <= set(forms)
        slash = C.name_forms("Medicine Wheel/Medicine Mountain National Historic Landmark", [], "t")
        assert "Medicine Wheel" in slash

    def test_an_alias_counts_only_where_the_description_uses_it(self) -> None:
        site = T.DESCRIPTIONS[T.SACSAY]
        assert "Saksaywaman" in C.name_forms("Sacsayhuamán", ["Saksaywaman"], site)
        assert "Sacsahuaman" not in C.name_forms("Sacsayhuamán", ["Sacsahuaman"], site)

    def test_a_short_derived_form_is_dropped_but_a_short_name_stays(self) -> None:
        assert C.name_forms("Ur", [], "Ur was a city.") == ("Ur",)
        assert "Ab" not in C.name_forms("Ab, Somewhere Long", [], "text")


# ------------------------------------------------------------------------------ the mechanical checks
def problems(card: str, site_id: str = T.SKARA, fit: Any = T.fit) -> list[str]:
    return C.problems(C.final_card(card), basis(site_id), fit=fit)


def padded(card: str) -> str:
    """`card` grown past the floor with words that claim nothing."""
    while len(card) < C.MIN_CHARS:
        card = card[:-1] + ", and more stone walls."
    return card


class TestTheMechanicalChecks:
    @pytest.mark.parametrize("site_id", [T.SKARA, T.NEWGRANGE, T.STONEHENGE, T.SACSAY])
    def test_the_good_cards_pass(self, site_id: str) -> None:
        assert problems(T.GOOD[site_id], site_id) == []

    def test_the_length_is_160_to_190_characters(self) -> None:
        assert any(p.startswith("length") for p in problems("Skara Brae lies on Orkney."))
        too_long = T.GOOD[T.SKARA][:-1] + ", beside the Bay of Skaill on the west coast of Orkney."
        assert len(too_long) > C.MAX_CHARS
        assert any(p.startswith("length") for p in problems(too_long))

    def test_the_length_is_measured_after_the_spoken_edit(self) -> None:
        assert C.final_card("Built c. 3180 BC.") == "Built circa 3180 BC."

    def test_layout_and_ending(self) -> None:
        good = T.GOOD[T.SKARA]
        assert any(p.startswith("layout") for p in problems(good.replace(", a ", ",  a ")))
        assert any(p.startswith("layout") for p in problems(" " + good[1:]))
        assert any(p.startswith("ending") for p in problems(good[:-1] + ","))
        assert any(p.startswith("ending") for p in problems(good[:-1] + "!"))
        assert not any(p.startswith("ending") for p in problems(good[:-1] + "?"))

    def test_at_most_two_sentences(self) -> None:
        card = "Skara Brae lies on Orkney. A storm found it. It was lived in from roughly 3180 BC."
        assert any(p.startswith("sentences") for p in problems(padded(card)))

    def test_at_most_one_short_question(self) -> None:
        two = T.GOOD[T.SKARA][:120] + "? Who? Why?"
        assert any(p.startswith("questions") for p in problems(two))
        long_q = (
            "Skara Brae lies on Orkney, stone houses in the sand dunes. What did the people who "
            "lived in them from roughly 3180 BC to around 2500 BC see from their doors at dawn?"
        )
        assert C.MIN_CHARS <= len(long_q) <= C.MAX_CHARS
        assert any(p.startswith("question:") for p in problems(long_q))

    @pytest.mark.parametrize(
        "bad", ["(", "[1]", "🗿", "²", "©", "!", "#", "*", "→", "×", "+", "=", "~", "|", "±"]
    )
    def test_brackets_markers_emojis_and_symbols_are_refused(self, bad: str) -> None:
        card = T.GOOD[T.SKARA].replace("Neolithic", f"Neolithic{bad}")
        assert any(p.startswith("characters") for p in problems(card))

    def test_a_zero_width_joiner_is_refused(self) -> None:
        card = T.GOOD[T.SKARA].replace("Neolithic", "Neo" + chr(0x200D) + "lithic")
        assert any(p.startswith("characters") for p in problems(card))

    def test_a_bare_circa_is_refused(self) -> None:
        card = T.GOOD[T.SKARA].replace("lived in from", "c. the end, lived in from")
        assert any(p.startswith("circa") for p in problems(card))

    def test_every_numeral_is_grounded_in_the_description(self) -> None:
        computed = T.GOOD[T.SKARA].replace("3180 BC to around 2500 BC", "5,000 years ago, 2500 BC")
        found = problems(computed)
        assert any(p.startswith("numbers not in the description: 5000") for p in found)
        assert problems(T.GOOD[T.SKARA].replace("3180", "3,180")) == []

    def test_a_numeral_of_the_name_is_grounded(self) -> None:
        site = C.basis(
            site_id=T.SKARA, name="Mound 72", country="X", description="A mound.", alt_names=[]
        )
        card = padded("Mound 72 rises from the fields, a mound of earth and stone.")
        assert not any(p.startswith("numbers") for p in C.problems(card, site, fit=T.fit))

    def test_the_card_names_the_site(self) -> None:
        card = T.GOOD[T.SKARA].replace("Skara Brae", "this village")
        assert any(p.startswith("name") for p in problems(card))
        accented = T.GOOD[T.SACSAY].replace("Sacsayhuamán", "Sacsayhuaman")
        assert problems(accented, T.SACSAY) == []

    def test_the_shorts_font_and_frame(self) -> None:
        def missing(name: str, card: str) -> Any:
            return dataclasses.replace(T.fit(name, card), missing=("ʿ",))

        def wide(name: str, card: str) -> Any:
            return dataclasses.replace(T.fit(name, card), px=C.V.MAX_CAPTION_PX + 1, widest="X")

        assert any(p.startswith("font") for p in problems(T.GOOD[T.SKARA], fit=missing))
        assert any(p.startswith("caption") for p in problems(T.GOOD[T.SKARA], fit=wide))


class TestTheExamples:
    @pytest.mark.parametrize("example", P.EXAMPLES, ids=lambda e: e.site)
    def test_every_example_passes_the_contract_on_its_site_s_description(self, example) -> None:
        site_id = T.SITE_OF[example.site]
        assert (T.COUNTRIES[site_id], T.GOOD[site_id]) == (example.country, example.card)
        assert C.problems(example.card, basis(site_id), fit=T.fit) == []

    @pytest.mark.parametrize("example", P.EXAMPLES, ids=lambda e: e.site)
    def test_an_example_shows_its_description_s_own_sentences_by_id(self, example) -> None:
        numbered = {s.id: s.text for s in basis(T.SITE_OF[example.site]).sentences}
        assert all(numbered[sid] == text for sid, text in example.sentences)

    @pytest.mark.parametrize("example", P.EXAMPLES, ids=lambda e: e.site)
    def test_every_claim_of_an_example_names_a_sentence_it_shows(self, example) -> None:
        own = {sid for sid, _text in example.sentences}
        assert all(ids and set(ids) <= own for _claim, ids in example.claims)


# ------------------------------------------------------------------------------ the answer shapes
class TestTheWriterAnswer:
    def test_a_card_and_its_basis(self) -> None:
        written = A.parse_writer(T.writer_answer("Built c. 3180 BC.", ["S3"]), basis())
        assert written.card == "Built circa 3180 BC." and written.basis == ("S3",)

    @pytest.mark.parametrize(
        ("text", "why"),
        [
            ("```json\n{}\n```", "one JSON object"),
            ('{"card": "x"}', "exactly"),
            ('{"card": "x", "basis": ["S1"], "note": 1}', "exactly"),
            ('{"card": " ", "basis": ["S1"]}', "card is not"),
            ('{"card": "x", "basis": []}', "no sentence"),
            ('{"card": "x", "basis": ["S99"]}', "not sentence ids"),
            ('{"card": "x", "basis": ["S1", "S1"]}', "twice"),
        ],
    )
    def test_anything_else_is_refused(self, text: str, why: str) -> None:
        with pytest.raises(A.AnswerError, match=why):
            A.parse_writer(text, basis())


class TestTheCheckerAnswer:
    def test_a_pass(self) -> None:
        checked = A.parse_checker(T.checker_answer(), basis())
        assert checked.verdict == A.PASSED and checked.claims == (
            ("the site's main facts", ("S1",)),
        )

    def test_a_pass_with_an_unsupported_claim_is_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="unsupported claim"):
            A.parse_checker(T.checker_answer(claims=[("the oldest", [])]), basis())

    @pytest.mark.parametrize("flag", ["tone_ok", "this_site"])
    def test_a_pass_with_a_broken_rule_is_refused(self, flag: str) -> None:
        with pytest.raises(A.AnswerError, match="tone_ok or this_site"):
            A.parse_checker(T.checker_answer(**{flag: False}), basis())

    def test_a_pass_with_a_reason_is_refused(self) -> None:
        with pytest.raises(A.AnswerError, match="PASS with a reason"):
            A.parse_checker(T.checker_answer(reasons=["too flat"]), basis())

    def test_a_fail_needs_a_reason(self) -> None:
        with pytest.raises(A.AnswerError, match="FAIL without a reason"):
            A.parse_checker(T.checker_answer(verdict="FAIL"), basis())
        failed = A.parse_checker(
            T.checker_answer(verdict="FAIL", claims=[("the oldest", [])], reasons=["No."]), basis()
        )
        assert failed.verdict == A.FAILED

    @pytest.mark.parametrize(
        ("change", "why"),
        [
            ({"claims": []}, "non-empty list"),
            ({"claims": [{"claim": "x", "support": ["S9"]}]}, "not sentence ids"),
            ({"verdict": "MAYBE"}, "PASS or FAIL"),
            ({"tone_ok": "yes"}, "true or false"),
            ({"reasons": "none"}, "not a list"),
        ],
    )
    def test_anything_else_is_refused(self, change: dict[str, Any], why: str) -> None:
        data = {**json.loads(T.checker_answer()), **change}
        with pytest.raises(A.AnswerError, match=why):
            A.parse_checker(json.dumps(data), basis())


class TestTheJudgeAnswer:
    QUOTE = "occupied from roughly 3180 BC to around 2500 BC"

    def _answer(self, **over: Any) -> str:
        claim = {
            "claim": "c",
            "verdict": "SUPPORTED",
            "url": "https://x.org/a",
            "quote": self.QUOTE,
        }
        return json.dumps({"claims": [{**claim, **over}]})

    def test_a_supported_and_an_unverifiable_claim(self) -> None:
        assert A.parse_judge(self._answer())[0].url == "https://x.org/a"
        judged = A.parse_judge(self._answer(verdict="UNVERIFIABLE", url=None, quote=None))
        assert judged[0].verdict == "UNVERIFIABLE"

    @pytest.mark.parametrize(
        ("over", "why"),
        [
            ({"verdict": "UNVERIFIABLE"}, "carries no url"),
            ({"quote": None}, "quote is not"),
            ({"quote": "short"}, "at least 20"),
            ({"url": "ftp://x"}, "http"),
            ({"verdict": "TRUE"}, "one of"),
        ],
    )
    def test_anything_else_is_refused(self, over: dict[str, Any], why: str) -> None:
        with pytest.raises(A.AnswerError, match=why):
            A.parse_judge(self._answer(**over))


# ------------------------------------------------------------------------------ the prompts
class TestThePrompts:
    def test_the_writer_sees_the_sentences_the_forms_the_rules_and_the_examples(self) -> None:
        prompt = P.writer_prompt(basis())
        assert "S3 The site was occupied from roughly 3180 BC" in prompt
        assert "NAME FORMS (the card must contain one of these, exactly): Skara Brae" in prompt
        assert "160-190 characters" in prompt and "Storm" not in prompt.split("THE RULES")[0]
        assert all(example.card in prompt for example in P.EXAMPLES)
        assert '{"card": "<the card>", "basis": ["S1", "S3"]}' in prompt

    def test_the_rewriter_sees_every_earlier_card_and_why(self) -> None:
        prompt = P.rewrite_prompt(basis(), [P.Finding("An old card.", ("No sentence says X.",))])
        assert "Card 1 (12 characters): An old card." in prompt
        assert "- No sentence says X." in prompt

    def test_the_checker_sees_the_card_and_the_sentences_but_no_writer(self) -> None:
        prompt = P.checker_prompt(basis(), T.GOOD[T.SKARA])
        assert T.GOOD[T.SKARA] in prompt and "S6 The buildings follow" in prompt
        assert '"verdict": "PASS"' in prompt and "basis" not in prompt

    def test_the_judge_sees_only_the_card(self) -> None:
        prompt = P.judge_prompt("Skara Brae", "Scotland", T.GOOD[T.SKARA])
        assert T.GOOD[T.SKARA] in prompt and "Bay of Skaill" not in prompt
        assert "ancientnerds.com" in prompt and "403" in prompt

    def test_the_findings_of_a_check_name_every_unsupported_claim(self) -> None:
        record = {
            "kind": "check",
            "claims": [
                {"claim": "the oldest", "support": []},
                {"claim": "on Orkney", "support": ["S1"]},
            ],
            "tone_ok": False,
            "this_site": True,
            "reasons": ["Too flat."],
        }
        findings = P.findings_of(record)
        assert findings[0] == "No sentence of the description supports the claim: the oldest"
        assert len(findings) == 3 and findings[-1] == "Too flat."


# ------------------------------------------------------------------------------ select
class TestTheSelection:
    def test_who_is_a_candidate(self) -> None:
        reasons = {r["site_id"]: R.classify(r)[0] for r in T.production_rows()}
        assert reasons == {
            T.SKARA: None,
            T.NEWGRANGE: None,
            T.STONEHENGE: None,
            T.SACSAY: None,
            T.MARCH: R.NOT_FINAL,
            T.EMPTY: R.NO_DESCRIPTION,
            T.RETIRED_SITE: R.RETIRED,
        }

    def test_a_description_its_provenance_does_not_hash_is_not_final(self) -> None:
        assert R.classify(T.row(T.SKARA, provenance_desc_sha256="0" * 64))[0] == R.NOT_FINAL

    @pytest.mark.parametrize("lane", ["L", None])
    def test_a_sentence_checked_text_is_a_basis_while_its_check_hashes_it(self, lane) -> None:
        digest = T.sha(T.DESCRIPTIONS[T.MARCH])
        checked = T.row(T.MARCH, lane=lane, check_desc_sha256=digest)
        assert R.classify(checked) == (None, "")
        assert R.basis_of(checked) == R.SENTENCE_CHECKED
        moved = T.row(T.MARCH, lane=lane, check_desc_sha256="0" * 64)
        assert R.classify(moved)[0] == R.NOT_FINAL

    def test_a_phase4_lane_is_named_before_a_sentence_check(self) -> None:
        digest = T.sha(T.DESCRIPTIONS[T.SKARA])
        assert R.basis_of(T.row(T.SKARA, check_desc_sha256=digest)) == "W"
        stale_w = T.row(T.SKARA, provenance_desc_sha256="0" * 64, check_desc_sha256=digest)
        assert R.basis_of(stale_w) == R.SENTENCE_CHECKED

    def test_the_run_records_each_candidate_s_basis(self, tmp_path: Path) -> None:
        checked = T.row(T.MARCH, lane="L", check_desc_sha256=T.sha(T.DESCRIPTIONS[T.MARCH]))
        rows = [checked if r["site_id"] == T.MARCH else r for r in T.production_rows()]
        run = make_run(tmp_path, rows)
        record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        assert record["basis"] == {"W": 4, "WC": 1}
        sites = {s["site_id"]: s["basis"] for s in R.read_jsonl(run / "SITES.jsonl")}
        assert sites[T.MARCH] == "WC"

    def test_a_site_without_a_card_row_is_listed(self) -> None:
        assert R.classify(T.row(T.SKARA, has_card_row=False))[0] == R.NO_CARD_ROW

    def test_a_live_teaser_is_current_and_a_stale_one_a_candidate(self) -> None:
        live = T.row(T.SKARA, card=T.GOOD[T.SKARA], card_provenance=T.teaser(T.SKARA))
        assert R.classify(live)[0] == R.CURRENT
        stale = T.row(
            T.SKARA, card=T.GOOD[T.SKARA], card_provenance=T.teaser(T.SKARA, description="old")
        )
        assert R.classify(stale)[0] is None

    def test_a_site_asked_before_is_asked_again_only_after_its_description_moved(self) -> None:
        rows = T.production_rows()
        asked = {T.SKARA: T.sha(T.DESCRIPTIONS[T.SKARA]), T.NEWGRANGE: T.sha("an older text")}
        chosen = R.select_rows(rows, earlier=asked, sites=None, pilot=None)
        assert [s["site_id"] for s in chosen.sites] == sorted([T.NEWGRANGE, T.STONEHENGE, T.SACSAY])
        assert {r["site_id"]: r["reason"] for r in chosen.listed}[T.SKARA] == R.ASKED_BEFORE

    def test_a_pilot_is_a_seeded_draw(self) -> None:
        rows = T.production_rows()
        first = R.select_rows(rows, earlier={}, sites=None, pilot=(2, 7))
        again = R.select_rows(rows, earlier={}, sites=None, pilot=(2, 7))
        assert [s["site_id"] for s in first.sites] == [s["site_id"] for s in again.sites]
        assert len(first.sites) == 2
        assert sum(r["reason"] == R.NOT_DRAWN for r in first.listed) == 2
        with pytest.raises(R.RunError, match="a pilot of 9"):
            R.select_rows(rows, earlier={}, sites=None, pilot=(9, 7))

    def test_a_sites_file_restricts_and_names_only_curated_sites(self) -> None:
        rows = T.production_rows()
        chosen = R.select_rows(rows, earlier={}, sites={T.SKARA}, pilot=None)
        assert [s["site_id"] for s in chosen.sites] == [T.SKARA]
        with pytest.raises(R.RunError, match="no curated site"):
            R.select_rows(rows, earlier={}, sites={"f" * 8}, pilot=None)


# ------------------------------------------------------------------------------ the run
def make_run(tmp_path: Path, rows: list[dict[str, Any]] | None = None) -> Path:
    run = tmp_path / "runs" / "wb-test"
    export = T.tagged({"site": rows if rows is not None else T.production_rows()})

    def read(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(export, encoding="utf-8", newline="\n")

    R.select(run, read=read, sites_file=None, pilot=None, exclude=[])
    return run


def answer_all(run: Path, stage: str, handoff: Path, answers: dict[str, str], by: str = "") -> None:
    record = R._round(run, stage)
    assert record is not None
    for batch_id, members in record["batches"].items():
        for site_id in members:
            OH.write_answer(
                handoff,
                batch_id=batch_id,
                stage=stage,
                label=site_id,
                text=answers[site_id],
                answered_by=by or R.agent_name(batch_id),
            )


def step(run: Path, tmp_path: Path, stage: str, answers: dict[str, str], by: str = "") -> dict:
    handoff = tmp_path / f"handoff-{stage}"
    exported = R.export_stage(run, stage, handoff)
    if exported["questions"]:
        answer_all(run, stage, handoff, answers, by)
        return R.import_stage(run, stage, fit=T.fit)
    return exported


GOOD_WRITES = {site: T.writer_answer(card) for site, card in T.GOOD.items()}
PASSES = dict.fromkeys(T.GOOD, T.checker_answer())


class TestTheRun:
    def test_select_fixes_the_candidates_once(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        record = json.loads((run / "RUN.json").read_text(encoding="utf-8"))
        assert record["sites"] == 4
        assert record["listed"] == {"no-description": 1, "not-final": 1, "retired": 1}
        with pytest.raises(R.RunError, match="selected already"):
            make_run(tmp_path)

    def test_a_changed_sites_file_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        path = run / "SITES.jsonl"
        path.write_text(path.read_text(encoding="utf-8").replace("Orkney", "Shetland"), "utf-8")
        with pytest.raises(R.RunError, match="not the file RUN.json pins"):
            R.bases(run)

    def test_all_accepted_in_the_first_round(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        assert step(run, tmp_path, "write", GOOD_WRITES)["mechanical_failures"] == 0
        assert step(run, tmp_path, "check", PASSES)["verdicts"] == {"PASS": 4}
        assert step(run, tmp_path, "rewrite1", {})["questions"] == 0
        R.outcomes(run)
        rows = R.read_outcomes(run)
        accepted = [r for r in rows if r["status"] == R.ACCEPTED]
        assert len(accepted) == 4
        for row in accepted:
            provenance = CP.validate(row["provenance"])
            assert CP.describes(provenance, T.GOOD[row["site_id"]])
            assert provenance["desc_sha256"] == T.sha(T.DESCRIPTIONS[row["site_id"]])
            assert provenance["check"]["by"].startswith("teaser-check-")
        cleared = [r for r in rows if r["status"] == R.CLEARED]
        assert [(r["site_id"], r["reason"]) for r in cleared] == [(T.EMPTY, R.NO_DESCRIPTION)]

    def test_a_blank_description_clears_the_card_on_the_text_as_it_was_read(
        self, tmp_path: Path
    ) -> None:
        rows = [
            T.row(T.EMPTY, description="  ", lane=None, provenance_desc_sha256=None)
            if r["site_id"] == T.EMPTY
            else r
            for r in T.production_rows()
        ]
        run = make_run(tmp_path, rows)
        step(run, tmp_path, "write", GOOD_WRITES)
        step(run, tmp_path, "check", PASSES)
        R.outcomes(run)
        empty = next(r for r in R.read_outcomes(run) if r["site_id"] == T.EMPTY)
        assert (empty["status"], empty["reason"]) == (R.CLEARED, R.NO_DESCRIPTION)
        assert empty["desc_sha256"] == T.sha("  ")

    def test_a_card_that_fails_goes_to_a_rewrite_with_its_findings(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        writes = {**GOOD_WRITES, T.SKARA: T.writer_answer("Skara Brae lies on Orkney.")}
        assert step(run, tmp_path, "write", writes)["mechanical_failures"] == 1
        checks = {
            **PASSES,
            T.NEWGRANGE: T.checker_answer(
                "FAIL", [("the oldest tomb", [])], ["No sentence says it is the oldest."]
            ),
        }
        step(run, tmp_path, "check", checks)
        R.export_stage(run, "rewrite1", tmp_path / "handoff-rewrite1")
        prompts = {
            line["label"]: (tmp_path / "handoff-rewrite1" / line["prompt_path"]).read_text("utf-8")
            for line in OH.manifest(tmp_path / "handoff-rewrite1")
        }
        assert set(prompts) == {T.SKARA, T.NEWGRANGE}
        assert "length: 26 characters" in prompts[T.SKARA]
        assert (
            "No sentence of the description supports the claim: the oldest tomb"
            in prompts[T.NEWGRANGE]
        )
        assert R.status(run)["states"] == {"accepted": 2, "due rewrite1": 2}

    def test_two_failed_rewrites_clear_the_card(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        bad = T.writer_answer("Skara Brae lies on Orkney.")
        step(run, tmp_path, "write", {**GOOD_WRITES, T.SKARA: bad})
        step(run, tmp_path, "check", PASSES)
        step(run, tmp_path, "rewrite1", {T.SKARA: bad})
        assert step(run, tmp_path, "check1", {})["questions"] == 0
        step(run, tmp_path, "rewrite2", {T.SKARA: T.writer_answer(T.GOOD[T.SKARA])})
        fail = T.checker_answer("FAIL", [("x", [])], ["Unsupported."])
        step(run, tmp_path, "check2", {T.SKARA: fail})
        R.outcomes(run)
        skara = next(r for r in R.read_outcomes(run) if r["site_id"] == T.SKARA)
        assert skara["status"] == R.CLEARED and skara["reason"] == "failed-after-two-rewrites"
        assert skara["attempts"] == 3 and skara["provenance"] is None

    def test_an_earlier_stage_must_be_imported_before_the_next_is_asked(
        self, tmp_path: Path
    ) -> None:
        run = make_run(tmp_path)
        R.export_stage(run, "write", tmp_path / "h-write")
        with pytest.raises(R.RunError, match="wait for their import"):
            R.export_stage(run, "check", tmp_path / "h-check")
        with pytest.raises(R.RunError, match="exported already"):
            R.export_stage(run, "write", tmp_path / "h-write-2")

    def test_a_checker_that_wrote_the_card_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES)
        with pytest.raises(R.RunError, match="wrote or checked this site before"):
            step(run, tmp_path, "check", PASSES, by="teaser-write-001")

    def test_a_malformed_answer_is_refused_at_import(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        with pytest.raises(R.RunError, match="malformed answer"):
            step(run, tmp_path, "write", {**GOOD_WRITES, T.SKARA: '{"card": "x"}'})

    def test_an_answer_to_another_prompt_is_refused(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        answer_all(run, "write", handoff, GOOD_WRITES)
        line = next(line for line in OH.manifest(handoff) if line["label"] == T.SKARA)
        prompt = handoff / line["prompt_path"]
        prompt.write_text(prompt.read_text("utf-8") + " ", encoding="utf-8")
        with pytest.raises(R.RunError, match="validated"):
            R.import_stage(run, "write", fit=T.fit)

    def test_a_question_the_run_would_now_ask_differently_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The prompts changed between export and import (a rule edited mid-round): the import
        rebuilds each question and refuses the answers to the old one."""
        run = make_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        answer_all(run, "write", handoff, GOOD_WRITES)
        monkeypatch.setattr(P, "RULES", (*P.RULES, "A rule added after the export."))
        with pytest.raises(R.RunError, match="not this question's"):
            R.import_stage(run, "write", fit=T.fit)

    def test_an_import_is_the_same_when_run_again(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES)
        first = (run / "STAGE-write.jsonl").read_bytes()
        step(run, tmp_path, "check", PASSES)
        R.import_stage(run, "write", fit=T.fit)
        assert (run / "STAGE-write.jsonl").read_bytes() == first

    def test_outcomes_wait_for_every_site(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        step(run, tmp_path, "write", GOOD_WRITES)
        with pytest.raises(R.RunError, match="still due"):
            R.outcomes(run)

    def test_check_answer_shows_the_writer_the_problems(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        batch = next(iter(R._round(run, "write")["batches"]))
        bad = R.check_answer(
            run, handoff, batch, T.SKARA, T.writer_answer("Skara Brae."), fit=T.fit
        )
        assert not bad["ok"] and bad["problems"][0].startswith("length")
        good = R.check_answer(run, handoff, batch, T.SKARA, GOOD_WRITES[T.SKARA], fit=T.fit)
        assert good["ok"] and good["length"] == len(T.GOOD[T.SKARA])
        shape = R.check_answer(run, handoff, batch, T.SKARA, "{}", fit=T.fit)
        assert not shape["ok"]
        with pytest.raises(R.RunError, match="no question"):
            R.check_answer(run, handoff, batch, T.MARCH, "{}", fit=T.fit)

    def test_the_brief_names_the_batch_its_scratch_and_its_agent(self, tmp_path: Path) -> None:
        run = make_run(tmp_path)
        handoff = tmp_path / "handoff-write"
        R.export_stage(run, "write", handoff)
        text = R.brief(run, handoff, "write-001")
        assert "Opus writer write-001" in text and "--answered-by teaser-write-001" in text
        assert "handoff-write-scratch/write-001/<label>.json" in text
        assert "no web research" in text
        assert 'Skip every question whose "answer_path"' in text
        with pytest.raises(R.RunError, match="no batch"):
            R.brief(run, handoff, "write-009")


# ------------------------------------------------------------------------------ the pilot judge
PAGE = "https://example.org/skara-brae"
PAGE_TEXT = b"<html><body><p>The site was occupied from roughly 3180 BC to around 2500 BC.</p></body></html>"


def judge_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == PAGE:
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=PAGE_TEXT)
        return httpx.Response(404, content=b"no")

    return httpx.Client(transport=httpx.MockTransport(handler))


def judged(
    verdict: str = "SUPPORTED", quote: str = "occupied from roughly 3180 BC to around 2500 BC"
) -> str:
    claims = [
        {"claim": "lived in from roughly 3180 BC", "verdict": verdict, "url": PAGE, "quote": quote}
    ]
    return json.dumps({"claims": claims})


class TestThePilotJudge:
    def _accepted_run(self, tmp_path: Path) -> Path:
        run = make_run(tmp_path, [T.row(T.SKARA)])
        step(run, tmp_path, "write", {T.SKARA: GOOD_WRITES[T.SKARA]})
        step(run, tmp_path, "check", {T.SKARA: PASSES[T.SKARA]})
        R.outcomes(run)
        return run

    def _judge(self, run: Path, tmp_path: Path, text: str, by: str = "") -> dict[str, Any]:
        handoff = tmp_path / "handoff-judge"
        R.export_judge(run, handoff)
        OH.write_answer(
            handoff, batch_id="judge-001", stage=R.JUDGE_STAGE, label=T.SKARA, text=text,
            answered_by=by or "teaser-judge-001",
        )  # fmt: skip
        return R.import_judge(run, client=judge_client(), pace=0)

    def test_a_quoted_support_passes(self, tmp_path: Path) -> None:
        result = self._judge(self._accepted_run(tmp_path), tmp_path, judged())
        assert result["pilot"] == "PASS" and result["supported"] == 1

    def test_a_proven_contradiction_fails_the_pilot(self, tmp_path: Path) -> None:
        result = self._judge(self._accepted_run(tmp_path), tmp_path, judged("CONTRADICTED"))
        assert result["pilot"] == "FAIL" and result["wrong_cards"] == [T.SKARA]

    def test_a_quote_the_page_does_not_hold_proves_nothing(self, tmp_path: Path) -> None:
        text = judged(quote="occupied from roughly 4000 BC to around 2500 BC")
        result = self._judge(self._accepted_run(tmp_path), tmp_path, text)
        assert result["unproven"] == 1 and result["pilot"] == "FAIL"

    def test_a_judge_who_worked_on_the_card_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(R.RunError, match="worked on this card"):
            self._judge(self._accepted_run(tmp_path), tmp_path, judged(), by="teaser-check-001")

    def test_the_import_asks_the_web_without_personal_data(self) -> None:
        with R.judge_client() as client:
            agent = client.headers["User-Agent"]
        assert agent == "AncientMapRemediation/1.0 (research)" and "@" not in agent
