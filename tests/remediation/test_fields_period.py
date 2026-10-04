"""Lane WD4 (`scripts/remediation/fields/`): a named period is a value (owner decision 2026-10-04).

Measured on 2026-10-04 in `output/remediation/fields/wd3/DECISIONS.jsonl`: of the 2,113 sites WD3
asked for a `period_start`, 1,338 came back `unresolved` with `value: null`, `value_page: null` and
`quotes: []` - and 792 of those name a period in their own `reasoning` (iron age 366, roman 243,
bronze age 192, neolithic 171, prehistoric 43), 677 of them one a table can turn into years. The
research was done and the answer was thrown away, because WD3's question forbade a period word and
`answers._check_period` could only read a year. WD4 asks the same question, accepts a period word,
and derives the year from one shared table (`pipeline/periods.py`), so exactly one place holds it.
WD1 and WD3 keep their own text and their own checks.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from fields import answers as A  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import rule as R  # noqa: E402
from pipeline import periods as P  # noqa: E402

from tests.remediation import test_fields_answers as TA  # noqa: E402
from tests.remediation import test_fields_wd3 as TW  # noqa: E402

WIKI, REGISTER = TA.WIKI, TA.REGISTER
PERIOD = R.ONE_FAMILY_PERIOD
#: The sentence the 792 dropped answers were made of, with a date in it, and without one
IRON = [(WIKI, "an Iron Age hillfort, occupied from c. 800 BC")]
PERIOD_ONLY = [(WIKI, "an Iron Age hillfort")]


def period_answer(
    name: Any = "iron age",
    quotes: list[tuple[str, str]] | None = None,
    decision: str = "replace",
    value: Any = None,
) -> dict[str, Any]:
    block = TA.block(decision, value, IRON if quotes is None else quotes,
                     reasoning="the page calls it an Iron Age hillfort")
    if name is not None:
        block[A.PERIOD_KEY] = name
    return block


def checked(answer: dict[str, Any], rule: R.Rule = PERIOD, **stored: Any) -> Any:
    """One period_start answer, checked under `rule` (the default: the period run)."""
    return A.check_shape(TA.text(period_start=answer), ["period_start"],
                         TA.line(**stored), rule)["period_start"]


# ------------------------------------------------------------------------------ the rule
class TestTheRule:
    def test_the_period_run_has_a_stage_of_its_own(self) -> None:
        assert PERIOD.name == "one-family-period" and PERIOD.stage == "wd4"
        assert R.BY_STAGE["wd4"] is PERIOD and "one-family-period" in R.RULES

    def test_it_is_wd3_s_rule_with_its_own_stage(self) -> None:
        # one quote from one source, the same refused families, fills and never clears
        assert (PERIOD.min_quotes, PERIOD.min_families) == (1, 1)
        assert PERIOD.forbidden_families == R.FORBIDDEN_FAMILIES
        assert PERIOD.fill_only and not PERIOD.clearable
        assert PERIOD.rests_on == R.ONE_FAMILY.rests_on

    def test_the_two_finished_stages_are_untouched(self) -> None:
        assert (R.TWO_FAMILIES.name, R.TWO_FAMILIES.stage) == ("two-families", "wd1")
        assert (R.ONE_FAMILY.name, R.ONE_FAMILY.stage) == ("one-family", "wd3")
        assert (R.TWO_FAMILIES.min_quotes, R.TWO_FAMILIES.min_families) == (2, 2)
        assert R.TWO_FAMILIES.clearable and not R.TWO_FAMILIES.fill_only
        assert R.ONE_FAMILY.min_quotes == 1 and not R.ONE_FAMILY.clearable
        assert R.DEFAULT is R.TWO_FAMILIES
        assert sorted(R.RULES) == ["one-family", "one-family-period", "two-families"]

    def test_the_run_pins_its_own_rule(self, tmp_path: Path) -> None:
        R.write_run(tmp_path, PERIOD, built_at="t")
        assert R.read_rule(tmp_path) is PERIOD
        with pytest.raises(R.RuleError, match="pins rule 'one-family-period'"):
            R.write_run(tmp_path, R.ONE_FAMILY)
        (tmp_path / R.RUN_FILE).write_text(
            '{"rule": "one-family-period", "stage": "wd3"}', encoding="utf-8"
        )
        with pytest.raises(R.RuleError, match="stage 'wd3'"):
            R.read_rule(tmp_path)


# ------------------------------------------------------------------------------ the shape
class TestTheAnswerShape:
    def test_a_period_word_answer_carries_the_name_and_gets_the_table_year(self) -> None:
        answer = checked(period_answer(), period_start=None)
        assert answer.decision == "replace" and answer.value == "-800"
        assert answer.period_name == "iron age"

    def test_the_year_comes_from_the_table_and_not_from_the_agent(self) -> None:
        quotes = {
            "neolithic": [(WIKI, "a Neolithic causeway enclosure")],
            "Victorian": [(WIKI, "built in the Victorian era")],
            "the Prehistory": [(WIKI, "a site of the Prehistory")],
        }
        for name, said in quotes.items():
            answer = checked(period_answer(name, said), period_start=None)
            assert answer.value == str(P.start_year(name)), name

    def test_an_invented_year_for_a_period_word_is_refused(self) -> None:
        # the table is the authority: one year for one name, so an agent's own is never read
        problem = checked(period_answer(value="-750"), period_start=None)
        assert "the year comes from the vocabulary" in problem
        assert "iron age" in problem and "-800" in problem

    def test_an_unknown_period_name_is_refused_by_name_and_by_size(self) -> None:
        problem = checked(period_answer("Klingon Age"), period_start=None)
        assert "Klingon Age" in problem and f"the {len(P.PERIODS)} names" in problem

    def test_a_name_is_a_trimmed_non_empty_string(self) -> None:
        for bad in ("   ", "", 42, ["iron age"]):
            assert "trimmed, non-empty string" in checked(period_answer(bad), period_start=None)

    def test_the_name_is_period_start_s_key_only(self) -> None:
        answer = A.parse(
            TA.text(site_type={**TA.block("keep", "Temple", IRON), A.PERIOD_KEY: "iron age"}),
            ["site_type"],
            R.ONE_FAMILY,
        )["site_type"]
        assert "period_start's own" in answer

    def test_unresolved_carries_no_name_and_no_quote(self) -> None:
        assert checked(TA.block("unresolved", None, [])).decision == "unresolved"
        named = TA.block("unresolved", None, []) | {A.PERIOD_KEY: "iron age"}
        assert "carries no value and no quote" in checked(named)

    def test_another_optional_key_is_still_refused(self) -> None:
        answer = {**TA.block("keep", "-449", IRON), "period": "iron age"}
        assert "not ['decision'" in checked(answer)

    def test_a_period_word_is_no_answer_under_the_two_finished_stages(self) -> None:
        two = [(WIKI, IRON[0][1]), (REGISTER, "an Iron Age fort")]
        for rule in (R.TWO_FAMILIES, R.ONE_FAMILY):
            problem = checked(period_answer(quotes=two), rule, period_start=None)
            assert "period_start's own" in problem and PERIOD.name in problem, rule.name


# ------------------------------------------------------------------------------ the checks
class TestThePeriodChecks:
    def test_a_quote_that_names_the_period_is_a_dating_quote(self) -> None:
        # "an Iron Age hillfort" carries no digit and no century word: `dated` refuses it, and it
        # is the one sentence shape the dropped 792 answers were made of
        assert not A.dated("an Iron Age hillfort")
        assert checked(period_answer(quotes=PERIOD_ONLY), period_start=None).decision == "replace"

    def test_every_quote_must_date_and_one_must_name_the_period(self) -> None:
        undated = [(REGISTER, "a stone fort on the moor")]
        assert "names no period and carries no date" in checked(
            period_answer(quotes=undated), period_start=None
        )
        other = [(WIKI, "a Bronze Age round barrow")]
        assert "names no period and carries no date" in checked(
            period_answer(quotes=other), period_start=None
        )
        # dated, and about another period: a date is not the period the answer names
        named_elsewhere = [(WIKI, "built in 800 BC"), (REGISTER, "a fort of the 2nd century")]
        assert "no quote names iron age" in checked(
            period_answer(quotes=named_elsewhere), period_start=None
        )
        # one quote names it, the others only have to carry a date
        both = [(WIKI, "an Iron Age hillfort"), (REGISTER, "a fort of the 2nd century")]
        assert checked(period_answer(quotes=both), period_start=None).decision == "replace"

    def test_the_bucket_comparison_runs_on_the_derived_year(self) -> None:
        # the stored value is -449, the Iron Age's -800 is in another bucket
        assert "that is replace" in checked(period_answer(decision="keep"))
        assert checked(period_answer(decision="replace")).decision == "replace"
        kept = checked(period_answer(decision="keep"), period_start=-700)
        assert kept.decision == "keep" and kept.value == "-800"
        assert "that is keep" in checked(period_answer(), period_start=-800)
        assert checked(period_answer(), period_start=None).decision == "replace"

    def test_a_period_word_answer_without_a_quote_rests_on_nothing(self) -> None:
        assert "at least one quote" in checked(period_answer(quotes=[]), period_start=None)

    def test_a_refused_family_is_still_no_source(self) -> None:
        quotes = [("https://www.wikiwand.com/en/articles/X", "an Iron Age hillfort")]
        assert "is no source" in checked(period_answer(quotes=quotes), period_start=None)


# ------------------------------------------------------------------------------ year answers
class TestYearAnswersAreUnchanged:
    def test_a_year_answer_is_read_under_every_rule_alike(self) -> None:
        answer = TA.block("keep", "-449", [(WIKI, "built in 449 BC"), (REGISTER, "5th century BC")])
        for rule in (R.TWO_FAMILIES, R.ONE_FAMILY, PERIOD):
            assert checked(answer, rule).decision == "keep"

    def test_the_year_checks_still_refuse_what_they_refused(self) -> None:
        undated = [(WIKI, "a Doric temple")]
        assert "carries no date" in checked(TA.block("keep", "-449", undated))
        loose = [(WIKI, "The site covers 12 hectares.")]
        assert "no quote states" in checked(TA.block("keep", "-449", loose))
        assert "is not an integer year" in checked(TA.block("keep", "c. 449 BC", undated))
        assert "not a year a site can start in" in checked(TA.block("replace", "3000", undated))

    def test_under_the_period_run_a_year_answer_resting_on_a_period_word_is_named(self) -> None:
        # the one thing wd4 adds to the year branch: a refusal that says what to send instead,
        # so that no period-word answer is dropped a second time
        problem = checked(TA.block("replace", "-800", PERIOD_ONLY), period_start=None)
        assert f"answer with {A.PERIOD_KEY}" in problem and "iron age" in problem
        # under wd1 and wd3 the same answer keeps the plain refusal, without the hint
        plain = checked(TA.block("replace", "-800", PERIOD_ONLY), R.ONE_FAMILY, period_start=None)
        assert plain == f"period_start: the quote on {WIKI} carries no date"

    def test_a_quoted_year_answers_as_before_under_the_period_run(self) -> None:
        answer = checked(TA.block("replace", "-800", [(WIKI, "occupied from c. 800 BC")]),
                         period_start=None)
        assert answer.decision == "replace" and answer.period_name is None


# ------------------------------------------------------------------------------ the question
#: One row of the measured hint file, `output/remediation/period_wave/original_periods.jsonl`:
#: what the site's own article carried when the dataset was imported (2025-12-18).
HINT = {
    "site_id": TW.A_ID,
    "name": "Temple of Hephaestus",
    "source_url": WIKI,
    "match": "url",
    "title": "Temple of Hephaestus",
    "year": "800 BC",
    "period": "1 - 500 AD",
    "category": "Temple",
}
HINT_KEYS = frozenset(HINT)


class TestTheQuestion:
    LINE = TW.wd3_line()

    @pytest.fixture
    def run(self, tmp_path: Path) -> Path:
        run = tmp_path / "run"
        run.mkdir()
        R.write_run(run, PERIOD)
        HO._write_jsonl(run / HO.C.CLASSIFIED_FILE, [self.LINE])
        return run

    def test_the_period_rule_text_names_the_answer_kind(self) -> None:
        rule = HO.FIELD_RULES_WD4["period_start"]
        assert A.PERIOD_KEY in rule
        assert "Iron Age hillfort" in rule
        # the year rule is not relaxed by it
        assert "itself" in rule and "4,500 years ago" in rule
        assert HO.FIELD_RULES_WD4["coordinates"] == HO.FIELD_RULES_WD3["coordinates"]
        assert HO.FIELD_RULES_WD4["site_type"] == HO.FIELD_RULES_WD3["site_type"]
        assert HO.FIELD_RULES_WD4["source_url"] == HO.FIELD_RULES_WD3["source_url"]

    def test_the_two_finished_rule_texts_still_forbid_a_period_word(self) -> None:
        # WD3's text is where the sentence stands; WD1's never had it, and neither names the key
        assert "a period word alone" in HO.FIELD_RULES_WD3["period_start"]
        for text in (HO.FIELD_RULES["period_start"], HO.FIELD_RULES_WD3["period_start"]):
            assert A.PERIOD_KEY not in text

    def test_the_answer_format_of_the_period_run_names_the_key(self) -> None:
        assert A.PERIOD_KEY in HO.ANSWER_FORMAT_WD4
        assert A.PERIOD_KEY not in HO.ANSWER_FORMAT_WD3
        assert A.PERIOD_KEY not in HO.ANSWER_FORMAT

    def test_the_prompt_of_the_period_run_says_it(self) -> None:
        prompt = HO.render_prompt(self.LINE, ["period_start"], None, PERIOD)
        assert "lane WD4" in prompt and A.PERIOD_KEY in prompt
        assert "a period word alone" not in prompt

    def test_the_prompt_of_wd3_is_unchanged(self) -> None:
        prompt = HO.render_prompt(self.LINE, ["period_start"], None, R.ONE_FAMILY)
        assert A.PERIOD_KEY not in prompt and "a period word alone" in prompt
        assert prompt == HO.render_prompt(self.LINE, ["period_start"], None, R.ONE_FAMILY)
        assert "lane WD3" in prompt and "lane WD4" not in prompt

    def test_batches_and_the_brief_follow_the_period_run(self, run: Path, tmp_path: Path) -> None:
        handoff = tmp_path / "h"
        HO.export(run, handoff)
        manifest = HO.OH.manifest(handoff)
        assert [m["batch_id"] for m in manifest] == ["wd4-r0-b0001"]
        prompt = (handoff / manifest[0]["prompt_path"]).read_text(encoding="utf-8")
        assert A.PERIOD_KEY in prompt and "lane WD4" in prompt
        text = HO.brief(run, handoff, "wd4-r0-b0001")
        assert "of the WD4 structured-field fill" in text and "--stage wd4" in text
        assert "--model claude-sonnet-5-5" in text
        assert text == HO.brief(run, handoff, "wd4-r0-b0001")

    def test_check_answer_reads_a_period_word(self, run: Path, tmp_path: Path) -> None:
        handoff = tmp_path / "h"
        HO.export(run, handoff)
        args = (run, handoff, "wd4-r0-b0001", self.LINE["site_id"])
        assert HO.check_answer(*args, TA.text(period_start=period_answer())) == {
            "ok": True,
            "problems": {},
        }
        invented = period_answer(value="-750")
        problem = HO.check_answer(*args, TA.text(period_start=invented))["problems"]["period_start"]
        assert "vocabulary" in problem

    def test_every_rule_has_its_own_texts_and_brief(self) -> None:
        assert set(HO.TEXTS) == set(R.RULES)
        assert set(HO.BRIEF_PARTS) == set(R.RULES)
        assert HO.TEXTS[PERIOD.name].field_rules is HO.FIELD_RULES_WD4
        assert HO.TEXTS[R.ONE_FAMILY.name].field_rules is HO.FIELD_RULES_WD3
        assert HO.TEXTS[R.TWO_FAMILIES.name].field_rules is HO.FIELD_RULES
        assert HO.BRIEF_PARTS[PERIOD.name]["lane"] == "WD4"
        assert HO.BRIEF_PARTS[R.ONE_FAMILY.name]["lane"] == "WD3"
        assert HO.BRIEF_PARTS[R.TWO_FAMILIES.name]["lane"] == "WD1"


class TestTheOriginalImportHint:
    """The claim the site's own article carried on 2025-12-18, shown to the agent and read by
    nothing: measured 2026-10-04, the nine-band `Period` agrees with the curated `period_start` in
    70.6 % of the 2,775 sites that have both and the `Year` in 20.9 %, and none of 1,544 Years lands
    inside the stored [period_start, period_end] span - a claim to confirm or contradict, never a
    value to copy."""

    LINE = TW.wd3_line()

    @pytest.fixture
    def run(self, tmp_path: Path) -> Path:
        run = tmp_path / "run"
        run.mkdir()
        R.write_run(run, PERIOD)
        HO._write_jsonl(run / HO.C.CLASSIFIED_FILE, [self.LINE])
        HO._write_jsonl(run / HO.HINTS_FILE, [HINT])
        return run

    def test_a_run_reads_its_own_hint_rows(self, run: Path) -> None:
        assert HO.read_hints(run) == {HINT["site_id"]: HINT}

    def test_a_run_without_the_file_has_no_hints(self, tmp_path: Path) -> None:
        assert HO.read_hints(tmp_path) == {}

    def test_a_malformed_hint_row_is_refused(self, run: Path) -> None:
        HO._write_jsonl(run / HO.HINTS_FILE, [{**HINT, "year": None}])
        with pytest.raises(HO.HandoffStepError, match="carries"):
            HO.read_hints(run)
        HO._write_jsonl(run / HO.HINTS_FILE, [{k: v for k, v in HINT.items() if k != "match"}])
        with pytest.raises(HO.HandoffStepError, match="not \\['category'"):
            HO.read_hints(run)

    def test_the_period_run_is_told_what_the_import_carried(self) -> None:
        prompt = HO.render_prompt(self.LINE, ["period_start"], None, PERIOD, hint=HINT)
        assert "2025-12-18" in prompt
        assert HINT["year"] in prompt and HINT["period"] in prompt
        assert "confirm or contradict" in prompt
        # the claim belongs to the period field, not to the type
        typed = TW.wd3_line(TW.B_ID, ["site_type"])
        other = HO.render_prompt(
            typed, ["site_type"], None, PERIOD, hint={**HINT, "site_id": TW.B_ID}
        )
        assert HINT["year"] not in other

    def test_the_two_older_runs_are_asked_the_same_question(self) -> None:
        for rule in (R.TWO_FAMILIES, R.ONE_FAMILY):
            assert HO.render_prompt(self.LINE, ["period_start"], None, rule, hint=HINT) == HO.render_prompt(  # fmt: skip
                self.LINE, ["period_start"], None, rule
            )

    def test_a_hint_with_nothing_in_it_changes_no_question(self) -> None:
        empty = {**HINT, "year": "", "period": ""}
        assert HO.render_prompt(self.LINE, ["period_start"], None, PERIOD, hint=empty) == (
            HO.render_prompt(self.LINE, ["period_start"], None, PERIOD)
        )
        assert HO.render_prompt(self.LINE, ["period_start"], None, PERIOD, hint=None) == (
            HO.render_prompt(self.LINE, ["period_start"], None, PERIOD)
        )

    def test_an_answer_that_only_repeats_the_hint_is_refused(self) -> None:
        # the checker reads nothing of the hint: no quote, no answer - and the hint's own Period
        # band is not a period name at all, so it cannot even be sent as one
        bare_year = TA.block("replace", "-800", [], reasoning="as the import says")
        assert "rests on" in checked(bare_year, PERIOD, period_start=None)
        bare_band = TA.block("replace", None, [], reasoning="as the import says")
        bare_band[A.PERIOD_KEY] = HINT["period"]
        assert "vocabulary knows" in checked(bare_band, PERIOD, period_start=None)
        assert A.PERIOD_KEY not in HO.FIELD_RULES_WD4["coordinates"]
