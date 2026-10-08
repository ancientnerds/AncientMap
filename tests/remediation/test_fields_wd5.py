"""Lane wd5 (`scripts/remediation/fields/`): the combined re-check of owner decisions D10, D12, D19.

One question per site asks the values no source stands behind - a period a rule made, a field a
MiniMax agent decided, a point nobody sourced - under the `recheck` rule: WD4's answer kinds, a
reader for dates in years before the present, and a write plan that replaces such a value (and only
such a value). Offline, like the lanes before it: production is a fake reader, the repository root
a temporary directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from fields import answers as A  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import plan as FP  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402
from mechanical import apply as MA  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical.plan import JournalLink, PlanError  # noqa: E402

from tests.remediation import test_fields_answers as TA  # noqa: E402
from tests.remediation import test_fields_plan as TP  # noqa: E402
from tests.remediation import test_fields_wd3 as TW  # noqa: E402
from tests.remediation.test_fields_classify import TABLE, TestTheRun  # noqa: E402

RE = R.RECHECK
SITE = TW.SITE
MINIMAX = "minimax/MiniMax-M3.1-Flash-Preview (MiniMax Code agent)"
RULE_NOTE = (
    "site_type 'Megalithic stones' lies in 'Neolithic'; the rule writes the epoch's beginning"
)


# ------------------------------------------------------------------------------ the rule
class TestTheRule:
    def test_the_recheck_rule_has_a_stage_of_its_own(self) -> None:
        assert (RE.name, RE.stage) == ("recheck", "wd5")
        assert R.BY_STAGE["wd5"] is RE and R.RULES["recheck"] is RE
        assert (RE.min_quotes, RE.min_families) == (1, 1)
        assert RE.forbidden_families == R.FORBIDDEN_FAMILIES
        assert RE.rests_on == R.ONE_FAMILY.rests_on

    def test_it_replaces_but_never_clears_by_answer(self) -> None:
        assert RE.recheck and not RE.fill_only and not RE.clearable
        assert RE.asks_open_fields and R.ONE_FAMILY.asks_open_fields
        assert not R.TWO_FAMILIES.asks_open_fields and not R.TWO_FAMILIES.recheck
        assert not R.ONE_FAMILY.recheck and not R.ONE_FAMILY_PERIOD.recheck

    def test_the_run_pins_the_rule(self, tmp_path: Path) -> None:
        R.write_run(tmp_path, RE, built_at="t")
        assert R.read_rule(tmp_path) is RE
        with pytest.raises(R.RuleError, match="pins rule 'recheck'"):
            R.write_run(tmp_path, R.ONE_FAMILY_PERIOD)
        (tmp_path / R.RUN_FILE).write_text('{"rule": "recheck", "stage": "wd4"}', encoding="utf-8")
        with pytest.raises(R.RuleError, match="stage 'wd4'"):
            R.read_rule(tmp_path)


# ------------------------------------------------------------------------------ the answers
def checked(field: str, answer: dict[str, Any], rule: R.Rule = RE, **stored: Any) -> Any:
    return A.check_shape(TA.text(**{field: answer}), [field], TA.line(**stored), rule)[field]


class TestTheAnswers:
    def test_a_period_word_is_an_answer_under_the_recheck_and_the_period_rule_only(self) -> None:
        answer = {**TA.block("replace", None, [(TA.WIKI, "an Iron Age hillfort")]),
                  A.PERIOD_KEY: "iron age"}  # fmt: skip
        assert checked("period_start", answer, period_start=None).value == "-800"
        assert (
            checked("period_start", answer, R.ONE_FAMILY_PERIOD, period_start=None).value == "-800"
        )
        assert "only" in checked("period_start", answer, R.ONE_FAMILY, period_start=None)

    def test_a_date_in_years_before_the_present_carries_a_replace(self) -> None:
        quotes = [(TA.WIKI, "the shelter was used about 40,000 years ago")]
        answer = checked("period_start", TA.block("replace", "-38050", quotes), period_start=None)
        assert answer.decision == "replace" and answer.value == "-38050"
        keep = checked("period_start", TA.block("keep", "-38050", quotes), period_start=-3000)
        assert "not in the stored value's bucket" in keep

    def test_a_clear_is_no_answer(self) -> None:
        assert "is not one of" in checked("period_start", TA.block("clear", None, []))
        assert checked("period_start", TA.block("unresolved", None, [])).decision == "unresolved"

    def test_one_quote_of_one_family_suffices_and_a_mirror_is_no_source(self) -> None:
        quotes = [(TA.WIKI, "built in 449 BC")]
        assert not isinstance(checked("period_start", TA.block("keep", "-449", quotes)), str)
        mirror = [("https://www.wikiwand.com/en/articles/Temple", "built in 449 BC")]
        assert "is no source" in checked("period_start", TA.block("keep", "-449", mirror))


# ------------------------------------------------------------------------------ the question
LINE = TW.wd3_line()


def wd5_line(why: str = "rule-made", made: str | None = None) -> dict[str, Any]:
    line = {**LINE, "open": {"period_start": {"why": why, "wd1": None, "made": made}}}
    line["fields"] = {**LINE["fields"], "period_start": {**LINE["fields"]["period_start"],
                                                         "stored": -4000}}  # fmt: skip
    return line


class TestTheQuestion:
    def test_it_shows_the_stored_value_why_it_is_asked_and_what_stands(self) -> None:
        line = wd5_line("rule-made", f"made by a rule, not found in a source: {RULE_NOTE}")
        prompt = HO.render_prompt(line, ["period_start"], None, RE)
        assert "lane wd5" in prompt
        assert "Stored value: -4000" in prompt
        assert "the stored start was made by a rule and found in no source" in prompt
        assert f"What stands: made by a rule, not found in a source: {RULE_NOTE}" in prompt
        assert "stored source_url" in prompt and "Hephaisteion - Pleiades" in prompt

    def test_every_reason_wd5_asks_for_has_its_words(self) -> None:
        for why in (POP.WHY_RULE_MADE, POP.WHY_MINIMAX, POP.WHY_UNSOURCED_POINT):
            assert why in HO.OPEN_TEXT
            prompt = HO.render_prompt(wd5_line(why), ["period_start"], None, RE)
            assert HO.OPEN_TEXT[why] in prompt

    def test_it_teaches_the_bp_reader_and_the_one_family_rule(self) -> None:
        rule = HO.FIELD_RULES_WD5["period_start"]
        assert "years before the present" in rule and "1950 minus" in rule
        assert '"12,000 cal BP"' in rule and '"45 ka"' in rule and "-4501" in rule
        assert "is not read" not in rule  # WD4's sentence that refused a BP date is gone
        assert "Undated" in rule and "MiniMax" in rule
        prompt = HO.render_prompt(wd5_line(), ["period_start"], None, RE)
        assert "One source suffices" in prompt and "Wikipedia mirrors" in prompt

    def test_the_other_rules_texts_are_untouched(self) -> None:
        assert "4,500 years ago" in HO.FIELD_RULES_WD4["period_start"]
        assert "4,500 years ago" in HO.FIELD_RULES_WD3["period_start"]
        assert HO.FIELD_RULES_WD5["coordinates"].startswith(HO.FIELD_RULES_WD4["coordinates"])
        assert "What unresolved does in this lane" in HO.FIELD_RULES_WD5["site_type"]
        assert HO.TEXTS[RE.name].answer_format == HO.ANSWER_FORMAT_WD4

    def test_the_original_import_claim_is_shown(self) -> None:
        claim = HO._original_claim(
            {"year": "800 BC", "period": "1 - 500 AD", "title": "T", "match": "url"}, RE
        )
        assert claim and 'Year "800 BC"' in claim[0]
        hint = {"year": "800 BC", "period": "1 - 500 AD", "title": "T", "match": "url"}
        assert HO._original_claim(hint, R.ONE_FAMILY) == []  # the older lane's prompt is pinned

    def test_the_brief_names_a_model_that_is_a_parameter(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        run.mkdir()
        R.write_run(run, RE)
        HO._write_jsonl(run / C.CLASSIFIED_FILE, [{**wd5_line(), "asked": ["period_start"]}])
        handoff = tmp_path / "handoff"
        HO.export(run, handoff)
        batch = next(iter(HO.read_rounds(run)[0]["batches"]))
        text = HO.brief(run, handoff, batch)
        assert "WD5 structured-field re-check" in text and "claude-sonnet-5-5" in text
        other = tmp_path / "handoff2"
        run2 = tmp_path / "run2"
        run2.mkdir()
        R.write_run(run2, RE)
        HO._write_jsonl(run2 / C.CLASSIFIED_FILE, [{**wd5_line(), "asked": ["period_start"]}])
        HO.export(run2, other, model="claude-opus-5-5")
        batch2 = next(iter(HO.read_rounds(run2)[0]["batches"]))
        assert "--model claude-opus-5-5" in HO.brief(run2, other, batch2)
        assert "claude-opus-5-5" in OH.ANSWER_MODELS


# ------------------------------------------------------------------------------ the lane
class TestTheLane:
    def test_wd5_is_a_lane_of_its_own(self) -> None:
        five, four = L.fields_lane("2026-10-09", 1, "wd5"), L.fields_lane("2026-10-09", 1, "wd4")
        assert five.name == "fields-wd5-2026-10-09-s001" and five.key_prefix == five.name
        assert five.run_stamp == "2026-10-09_fields-wd5-s001"
        assert five.test_id == "WD5/structured-fields" and five.label == "WD5 field correction"
        assert five.confidence == "one_source"
        assert five.out_dir_name == "fields/wd5/write/2026-10-09/s001"
        assert five.plan_table == "_fields_wd5_plan"
        for field in ("run_stamp", "out_dir_name", "plan_table", "test_id", "key_prefix", "label"):
            assert getattr(five, field) != getattr(four, field)
        assert five.site_invariants == four.site_invariants
        assert L.resolve_lane("fields-wd5-2026-10-09b-s012") == L.fields_lane(
            "2026-10-09b", 12, "wd5"
        )
        assert MA.readback_for(five) == L.fields_readback(five)

    def test_only_wd5_may_write_the_residue_label(self) -> None:
        def labels(stage: str) -> tuple[str, ...]:
            return L.fields_lane("2026-10-09", 1, stage).cell("period_name").allowed_new_values

        assert "Undated" in labels("wd5")
        for stage in ("wd1", "wd3", "wd4"):
            assert "Undated" not in labels(stage)
            assert labels("wd5")[:-1] == labels(stage)

    def test_a_cleared_start_with_the_undated_label_passes_the_plan_guards_of_wd5_only(
        self,
    ) -> None:
        records = [
            MA.ChangeRecord(
                site_id=TP.SITE, site_name="a site", old_value="-4000", new_value=None,
                rule="wd5-clear", condition="x", reason="fields-wd5 (wd5-clear)",
                evidence=({"source": "t", "quote": "x"},), column="period_start",
            ),
            MA.ChangeRecord(
                site_id=TP.SITE, site_name="a site", old_value="4500 - 3000 BC",
                new_value="Undated", rule="wd5-derive-period-name", condition="x",
                reason="fields-wd5 (wd5-derive-period-name)",
                evidence=({"source": "t", "quote": "x"},), column="period_name",
            ),
        ]  # fmt: skip
        MA.validate_records(records, lane=L.fields_lane("2026-10-09", 1, "wd5"))
        with pytest.raises(PlanError, match="Undated"):
            MA.validate_records(records, lane=L.fields_lane("2026-10-09", 1, "wd4"))

    def test_an_unknown_stage_is_no_lane(self) -> None:
        with pytest.raises(KeyError):
            L.resolve_lane("fields-wd6-2026-10-09-s001")


# ------------------------------------------------------------------------------ the population
SITE_ID = TW.SITE


def made_row(column: str, value: Any, *, rule: bool = False, minimax: bool = False,
             confidence: str = "one_source", note: str | None = None,
             withdrawn: bool = False) -> dict[str, Any]:  # fmt: skip
    return {"site_id": SITE_ID, "column_name": column, "run_stamp": "2026-10-04_fields-wd3-s001",
            "confidence": confidence, "new_value": None if value is None else str(value),
            "rule_made": rule, "minimax": minimax, "withdrawn": withdrawn,
            "note": note}  # fmt: skip


def made_of(*rows: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["site_id"], r["column_name"]): r for r in rows}


def decision(field: str, verdict: str, model: str | None = None, value: Any = None,
             stored: Any = None) -> dict[str, Any]:  # fmt: skip
    return {"site_id": SITE_ID, "field": field, "decision": verdict, "model": model,
            "value": value, "stored": stored, "reasoning": "r", "via": "counted",
            "run": "wd3"}  # fmt: skip


def history_of(*rows: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["site_id"], r["field"]): r for r in rows}


def recheck(row: dict[str, Any], history: dict[Any, Any], made: dict[Any, Any],
            **status: str) -> dict[str, str]:  # fmt: skip
    opened, _sourced = POP.recheck_fields(TW.line_of(**status), row, history, made, TW.wd1([], ()))
    return {field: info["why"] for field, info in opened.items()}


class TestTheKinds:
    def test_who_made_a_value_is_read_from_its_newest_journal_row(self) -> None:
        row = TW.stored_row(period_start=-4000)
        rule = made_of(made_row("period_start", -4000, rule=True, note=RULE_NOTE))
        assert POP.made_kinds(row, rule, SITE_ID)["period_start"] == "rule"
        minimax = made_of(made_row("period_start", -4000, minimax=True))
        assert POP.made_kinds(row, minimax, SITE_ID)["period_start"] == "minimax"
        sourced = made_of(made_row("period_start", -4000, confidence="two_source"))
        assert POP.made_kinds(row, sourced, SITE_ID)["period_start"] == "sourced"
        unsourced = made_of(made_row("period_start", -4000, confidence="opus-checked"))
        assert POP.made_kinds(row, unsourced, SITE_ID)["period_start"] is None

    def test_a_value_wd5_withdrew_is_sourced_by_nothing(self) -> None:
        """A cleared or restored cell is journalled at the lane's confidence, but its decision entry
        says `unresolved`: no source stands behind it, so no later build counts it as sourced."""
        row = TW.stored_row(period_start=-4000)
        withdrawn = made_of(made_row("period_start", -4000, withdrawn=True))
        assert POP.made_kinds(row, withdrawn, SITE_ID)["period_start"] is None
        cleared = made_of(made_row("period_start", None, withdrawn=True))
        assert (
            POP.made_kinds(TW.stored_row(period_start=None), cleared, SITE_ID)["period_start"]
            is None
        )
        assert "x ->> 'decision' = 'unresolved'" in POP.MADE_SQL

    def test_a_row_that_no_longer_ends_at_the_stored_value_claims_nothing(self) -> None:
        row = TW.stored_row(period_start=-3000)
        moved = made_of(made_row("period_start", -4000, rule=True))
        assert POP.made_kinds(row, moved, SITE_ID)["period_start"] is None
        assert (
            POP.made_kinds(TW.stored_row(period_start=None), moved, SITE_ID)["period_start"] is None
        )
        emptied = made_of(made_row("period_start", None, minimax=True))
        assert (
            POP.made_kinds(TW.stored_row(period_start=None), emptied, SITE_ID)["period_start"]
            == "minimax"
        )

    def test_a_point_is_compared_as_numbers_and_is_one_field(self) -> None:
        row = TW.stored_row(lat_text="37.9755", lon_text="23.72150")
        made = made_of(made_row("lat", "37.9755", minimax=True),
                       made_row("lon", "23.7215", confidence="two_source"))  # fmt: skip
        kinds = POP.made_kinds(row, made, SITE_ID)
        assert (kinds["lat"], kinds["lon"]) == ("minimax", "sourced")
        assert POP.field_kind(kinds, "coordinates") == "minimax"
        assert POP.field_kind({"lat": "sourced", "lon": None}, "coordinates") == "sourced"
        assert POP.field_kind({}, "coordinates") is None


class TestTheRecheckPopulation:
    def test_a_period_a_rule_made_is_asked_whoever_else_answered_it(self) -> None:
        made = made_of(made_row("period_start", -4000, rule=True, note=RULE_NOTE))
        row = TW.stored_row(period_start=-4000)
        assert recheck(row, {}, made) == {"period_start": "rule-made"}
        silent = history_of(decision("period_start", "unresolved", MINIMAX))
        assert recheck(row, silent, made) == {"period_start": "rule-made"}

    def test_the_question_says_what_the_rule_was(self) -> None:
        made = made_of(made_row("period_start", -4000, rule=True, note=RULE_NOTE))
        opened, _sourced = POP.recheck_fields(
            TW.line_of(), TW.stored_row(period_start=-4000), {}, made, TW.wd1([], ())
        )
        assert (
            opened["period_start"]["made"] == f"made by a rule, not found in a source: {RULE_NOTE}"
        )
        assert opened["period_start"]["wd1"] is None

    def test_a_field_a_minimax_agent_wrote_or_decided_is_asked(self) -> None:
        written = made_of(made_row("site_type", "Temple", minimax=True))
        assert recheck(TW.stored_row(site_type="Temple"), {}, written) == {
            "site_type": "minimax-answered"
        }
        for verdict in ("keep", "replace", "unresolved"):
            said = history_of(decision("source_url", verdict, MINIMAX))
            assert recheck(TW.stored_row(), said, {}) == {"source_url": "minimax-answered"}
        # an empty period a MiniMax agent could not date: its unresolved is no finding
        said = history_of(decision("period_start", "unresolved", MINIMAX))
        assert recheck(TW.stored_row(period_start=None), said, {}) == {
            "period_start": "minimax-answered"
        }

    def test_an_answer_of_another_model_is_not_asked_again(self) -> None:
        said = history_of(decision("site_type", "replace", OH.SONNET_MODEL),
                          decision("period_start", "unresolved", OH.SONNET_MODEL))  # fmt: skip
        assert recheck(TW.stored_row(), said, {}) == {}

    def test_another_lanes_sourced_write_is_never_asked_whatever_minimax_said(self) -> None:
        said = history_of(decision("period_start", "replace", MINIMAX),
                          decision("coordinates", "unresolved", MINIMAX))  # fmt: skip
        sourced = made_of(made_row("period_start", -449, confidence="authoritative"),
                          made_row("lat", "37.9755", confidence="two_source"))  # fmt: skip
        assert recheck(TW.stored_row(), said, sourced, coordinates=C.MISSING) == {}

    def test_a_point_nobody_sourced_is_asked_and_a_counted_keep_is_not(self) -> None:
        row = TW.stored_row()
        unresolved = history_of(decision("coordinates", "unresolved", OH.SONNET_MODEL))
        assert recheck(row, unresolved, {}) == {"coordinates": "unsourced-point"}
        held = history_of(decision("coordinates", "held", OH.SONNET_MODEL))
        assert recheck(row, held, {}) == {"coordinates": "unsourced-point"}
        # a better point a guard refused: the replace is decided, nothing wrote it
        refused = history_of(decision("coordinates", "replace", OH.SONNET_MODEL, "36.5, 34.1"))
        assert recheck(row, refused, {}) == {"coordinates": "unsourced-point"}
        kept = history_of(decision("coordinates", "keep", OH.SONNET_MODEL))
        assert recheck(row, kept, {}) == {}

    def test_a_site_no_pass_asked_is_read_by_the_machine_status(self) -> None:
        assert recheck(TW.stored_row(), {}, {}, coordinates=C.MISSING) == {
            "coordinates": "unsourced-point"
        }
        assert recheck(TW.stored_row(), {}, {}) == {}

    def test_a_minimax_point_is_minimax_answered_not_unsourced(self) -> None:
        written = made_of(made_row("lat", "37.9755", minimax=True))
        assert recheck(TW.stored_row(), {}, written) == {"coordinates": "minimax-answered"}

    def test_the_history_runs_wd1_then_wd3_then_wd4(self, tmp_path: Path) -> None:
        earlier = TW.wd1([{**TW.d("period_start", "keep"), "model": None}])
        for stage, verdict in (("wd3", "unresolved"), ("wd4", "replace")):
            HO._write_jsonl(
                tmp_path / stage / "DECISIONS.jsonl",
                [decision("period_start", verdict, MINIMAX), decision("site_type", "keep")],
            )
        history = POP.read_history(earlier, tmp_path)
        assert history[(SITE_ID, "period_start")]["decision"] == "replace"  # wd4 over wd3 over wd1
        assert history[(SITE_ID, "site_type")]["decision"] == "keep"


class TestTheRecheckRun:
    fixtures = TestTheRun()

    def prepare(
        self, tmp_path: Path, made: list[dict[str, Any]], **stored: Any
    ) -> tuple[Path, Path]:
        root, out = tmp_path / "h", tmp_path / "o"
        self.fixtures.write_harvest(root)
        self.fixtures.stored(out, **stored)
        HO._write_jsonl(out / POP.LINKS_FILE, [{"site_id": SITE_ID, "links": []}])
        HO._write_jsonl(out / POP.POINTS_FILE, [])
        HO._write_jsonl(out / POP.MADE_FILE, made)
        return root, out

    def test_a_wd5_run_asks_the_values_no_source_stands_behind(self, tmp_path: Path) -> None:
        root, out = self.prepare(
            tmp_path, [made_row("period_start", -4000, rule=True, note=RULE_NOTE)],
            period_start=-4000,
        )  # fmt: skip
        counts = POP.build(root, out, table=TABLE, wd1=TW.wd1([]), stage="wd5", history={})
        line = json.loads((out / C.CLASSIFIED_FILE).read_text(encoding="utf-8"))
        assert line["asked"] == ["period_start"]
        assert line["open"]["period_start"]["why"] == "rule-made"
        assert counts["population"]["why"] == {"period_start:rule-made": 1}
        assert R.read_rule(out) is RE

    def test_a_sourced_field_is_left_alone_and_counted(self, tmp_path: Path) -> None:
        root, out = self.prepare(
            tmp_path, [made_row("period_start", -4000, confidence="two_source"),
                       made_row("site_type", "Temple", minimax=True)],
            period_start=-4000, site_type="Temple",
        )  # fmt: skip
        counts = POP.build(root, out, table=TABLE, wd1=TW.wd1([]), stage="wd5", history={})
        assert counts["population"]["skipped_sourced"] == {"period_start": 1}
        assert counts["population"]["why"] == {"site_type:minimax-answered": 1}
        saved = json.loads((out / C.COUNTS_FILE).read_text(encoding="utf-8"))
        assert saved["population"]["skipped_sourced"] == {"period_start": 1}

    def test_a_wd5_run_needs_the_history_and_the_made_by_export(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, [], period_start=-4000)
        with pytest.raises(POP.PopulationError, match="no history"):
            POP.build(root, out, table=TABLE, wd1=TW.wd1([]), stage="wd5")
        (out / POP.MADE_FILE).unlink()
        with pytest.raises(POP.PopulationError, match="run `population.py export` first"):
            POP.build(root, out, table=TABLE, wd1=TW.wd1([]), stage="wd5", history={})

    def test_the_made_by_rows_are_refused_when_malformed(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, [{"site_id": SITE_ID}], period_start=-4000)
        with pytest.raises(POP.PopulationError, match="a row carries"):
            POP.build(root, out, table=TABLE, wd1=TW.wd1([]), stage="wd5", history={})

    def test_the_made_by_export_reads_one_row_per_column(self, tmp_path: Path) -> None:
        rows = [made_row("lat", "37.9755"), made_row("period_start", -4000, rule=True)]
        assert POP.export_made(tmp_path, reader=lambda sql: rows) == 2
        made = POP.read_made(tmp_path)
        assert made[(SITE_ID, "period_start")]["rule_made"] is True
        with pytest.raises(POP.PopulationError, match="made-by row carries"):
            POP.export_made(tmp_path, reader=lambda sql: [{"site_id": SITE_ID}])

    def test_the_step_read_names_the_steps_sites_only(self) -> None:
        sql = POP.made_sql([SITE_ID])
        assert f"c.row_pk IN ('{SITE_ID}')" in sql and "RULE" in sql and "minimax" in sql
        assert "c.row_pk IN" not in POP.MADE_SQL


# ------------------------------------------------------------------------------ the write plan
def five(decisions: list[dict[str, Any]], row: dict[str, Any] | None = None,
         open_: dict[str, Any] | None = None, kinds: dict[str, str | None] | None = None,
         journals: dict[str, Any] | None = None, **kw: Any) -> list[Any]:  # fmt: skip
    line = {"open": open_ if open_ is not None else {d["field"]: {"why": "x"} for d in decisions}}
    return FP.site_cells(
        row or TP.live(), line, {d["field"]: d for d in decisions}, journals or {},
        country_check=kw.pop("country_check", TP.AGREES), under=RE, kinds=kinds, **kw,
    )  # fmt: skip


def wd5_decision(field: str, verdict: str, value: Any, stored: Any,
                 model: str = OH.SONNET_MODEL) -> dict[str, Any]:  # fmt: skip
    return {**TP.decision(field, verdict, value, stored), "model": model}


def link(
    old: str | None, new: str | None, stamp: str = "2026-10-04_fields-wd3-s001", id_: int = 7
) -> JournalLink:
    return JournalLink(id_, stamp, "WD3/structured-fields", old, new)


def why(reason: str) -> dict[str, Any]:
    return {"why": reason, "wd1": None}


class TestWhatItReplaces:
    def test_a_start_a_rule_made_is_replaced_with_its_label(self) -> None:
        row = TP.live(period_start=-4000, period_name="4500 - 3000 BC")
        out = five([wd5_decision("period_start", "replace", "-2500", -4000)], row,
                   open_={"period_start": why("rule-made")}, kinds={"period_start": "rule"})  # fmt: skip
        assert TP.written(out) == {
            "period_start": ("-4000", "-2500"),
            "period_name": ("4500 - 3000 BC", "3000 - 1500 BC"),
        }
        assert {v.rule for v in out if v.ok} == {"wd5-replace", "wd5-derive-period-name"}
        assert out[0].finding_test_id == "WD5/period_start"
        for v in out:  # every cell shows who answered
            assert [e["model"] for e in v.evidence if "model" in e] == [OH.SONNET_MODEL]

    def test_a_sourced_value_is_never_replaced(self) -> None:
        for field, value, stored in (
            ("period_start", "-2500", -700), ("site_type", "Temple", "City"),
            ("source_url", "https://en.wikipedia.org/wiki/Other", "https://x.org/a"),
        ):  # fmt: skip
            row = TP.live(**{field: stored})
            for kind in ("sourced", "rule", "minimax"):
                reason = "unsourced-point" if kind == "rule" else "rule-made"
                if kind == "minimax":
                    reason = "rule-made"  # the reason names a rule, the journal says MiniMax
                out = five([wd5_decision(field, "replace", value, stored)], row,
                           open_={field: why(reason)}, kinds={field: kind})  # fmt: skip
                assert TP.written(out) == {}, (field, kind)
                assert [v.reason for v in out] == ["sourced-value"]
            # nothing says it was asked at all: a replace needs a reason
            out = five([wd5_decision(field, "replace", value, stored)], row, open_={},
                       kinds={field: None})  # fmt: skip
            assert [v.reason for v in out] == ["sourced-value"]
            # sourced by another lane after the question was asked
            out = five([wd5_decision(field, "replace", value, stored)], row,
                       open_={field: why("minimax-answered")}, kinds={field: "sourced"})  # fmt: skip
            assert [v.reason for v in out] == ["sourced-value"]

    def test_a_value_a_minimax_agent_wrote_or_left_is_replaced(self) -> None:
        for kind in ("minimax", None):
            out = five([wd5_decision("site_type", "replace", "Temple", "City")],
                       open_={"site_type": why("minimax-answered")}, kinds={"site_type": kind})  # fmt: skip
            assert TP.written(out) == {"site_type": ("City", "Temple")}

    def test_an_empty_field_is_filled_whatever_the_journal_says(self) -> None:
        row = TP.live(site_type=None)
        out = five([wd5_decision("site_type", "replace", "Temple", None)], row,
                   open_={"site_type": why("minimax-answered")}, kinds={"site_type": None})  # fmt: skip
        assert TP.written(out) == {"site_type": (None, "Temple")}

    def test_an_unsourced_point_is_replaced_and_moves_lat_lon_geom_together(self) -> None:
        out = five([wd5_decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")],
                   open_={"coordinates": why("unsourced-point")}, kinds={"lat": None, "lon": None})  # fmt: skip
        assert set(TP.written(out)) == {"lat", "lon", "geom"}
        assert {v.rule for v in out if v.ok} == {"wd5-replace", "wd5-point"}

    def test_a_sourced_point_is_never_replaced_and_a_better_point_is_still_guarded(self) -> None:
        out = five([wd5_decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")],
                   open_={"coordinates": why("unsourced-point")},
                   kinds={"lat": "sourced", "lon": "sourced"})  # fmt: skip
        assert TP.written(out) == {} and [v.reason for v in out] == ["sourced-value"]
        crossing = five([wd5_decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")],
                        open_={"coordinates": why("unsourced-point")}, kinds={},
                        country_check=TP.ELSEWHERE)  # fmt: skip
        assert crossing[0].reason == "country-changes"

    def test_a_keep_confirms_a_minimax_value_and_writes_nothing(self) -> None:
        keep = five([wd5_decision("site_type", "keep", "City", "City")],
                    open_={"site_type": why("minimax-answered")}, kinds={"site_type": "minimax"})  # fmt: skip
        assert keep == []

    def test_a_label_follows_only_a_start_the_step_writes(self) -> None:
        assert five([], TP.live(period_name="1 - 500 AD")) == []
        out = five([wd5_decision("site_type", "replace", "Temple", "City")],
                   TP.live(period_name="1 - 500 AD"),
                   open_={"site_type": why("minimax-answered")}, kinds={})  # fmt: skip
        assert set(TP.written(out)) == {"site_type"}

    def test_a_replace_never_starts_after_the_end(self) -> None:
        row = TP.live(period_start=-4000, period_end=-3500)
        out = five([wd5_decision("period_start", "replace", "-100", -4000)], row,
                   open_={"period_start": why("rule-made")}, kinds={"period_start": "rule"})  # fmt: skip
        assert [v.reason for v in out] == ["period-end-precedes-start"]

    def test_a_decision_about_a_value_the_row_no_longer_holds_is_refused(self) -> None:
        out = five(
            [wd5_decision("period_start", "replace", "-2500", -4000)],
            open_={"period_start": why("rule-made")},
            kinds={"period_start": "rule"},
        )
        assert [v.reason for v in out] == ["moved-since-classification"]


class TestWhatItWithdraws:
    def test_only_a_rule_made_start_clears_to_undated(self) -> None:
        row = TP.live(period_start=-4000, period_name="4500 - 3000 BC")
        out = five([wd5_decision("period_start", "unresolved", None, -4000)], row,
                   open_={"period_start": why("rule-made")}, kinds={"period_start": "rule"})  # fmt: skip
        assert TP.written(out) == {
            "period_start": ("-4000", None),
            "period_name": ("4500 - 3000 BC", "Undated"),
        }
        assert {v.rule for v in out if v.ok} == {"wd5-clear", "wd5-derive-period-name"}
        assert (
            "no year" in out[0].evidence[-1]["quote"] or "Undated" in out[0].evidence[-1]["quote"]
        )
        # a start nobody made by rule, or another lane sourced, or no journal row says: stays
        for kind in ("sourced", None):
            out = five([wd5_decision("period_start", "unresolved", None, -4000)], row,
                       open_={"period_start": why("minimax-answered")},
                       kinds={"period_start": kind})  # fmt: skip
            assert TP.written(out) == {} and [v.reason for v in out] == ["field-unresolved"]

    def test_a_label_that_is_undated_already_is_not_written_again(self) -> None:
        row = TP.live(period_start=-4000, period_name="Undated")
        out = five([wd5_decision("period_start", "unresolved", None, -4000)], row,
                   open_={"period_start": why("rule-made")}, kinds={"period_start": "rule"})  # fmt: skip
        assert set(TP.written(out)) == {"period_start"}

    def test_a_start_a_minimax_agent_wrote_is_restored_never_cleared_to_undated(self) -> None:
        row = TP.live(period_start=-1200, period_name="1500 - 500 BC")
        journals = {"period_start": [link("-2500", "-1200")]}
        out = five([wd5_decision("period_start", "unresolved", None, -1200)], row,
                   open_={"period_start": why("minimax-answered")},
                   kinds={"period_start": "minimax"}, journals=journals)  # fmt: skip
        assert TP.written(out) == {
            "period_start": ("-1200", "-2500"),
            "period_name": ("1500 - 500 BC", "3000 - 1500 BC"),
        }
        assert {v.rule for v in out if v.ok} == {"wd5-restore", "wd5-derive-period-name"}

    def test_a_start_a_minimax_agent_filled_goes_back_to_empty_and_undated(self) -> None:
        row = TP.live(period_start=-1200, period_name="1500 - 500 BC")
        journals = {"period_start": [link(None, "-1200")]}
        out = five([wd5_decision("period_start", "unresolved", None, -1200)], row,
                   open_={"period_start": why("minimax-answered")},
                   kinds={"period_start": "minimax"}, journals=journals)  # fmt: skip
        assert TP.written(out) == {
            "period_start": ("-1200", None),
            "period_name": ("1500 - 500 BC", "Undated"),
        }

    def test_a_type_or_url_a_minimax_agent_wrote_is_restored(self) -> None:
        for field, old, new in (("site_type", None, "Temple"), ("source_url", "https://x.org/a",
                                                                "https://en.wikipedia.org/wiki/Z")):  # fmt: skip
            row = TP.live(**{field: new})
            out = five([wd5_decision(field, "unresolved", None, new)], row,
                       open_={field: why("minimax-answered")}, kinds={field: "minimax"},
                       journals={field: [link(old, new)]})  # fmt: skip
            assert TP.written(out) == {field: (new, old)}
            assert out[0].rule == "wd5-restore"

    def test_a_point_a_minimax_agent_moved_is_restored_whole(self) -> None:
        row = TP.live(lat_text="36.5", lon_text="34.1", geom_text="NEWGEOM", geom_is_point=True)
        journals = {"lat": [link("35.1", "36.5")], "lon": [link("33.4", "34.1")],
                    "geom": [link("OLDGEOM", "NEWGEOM")]}  # fmt: skip
        out = five([wd5_decision("coordinates", "unresolved", None, "36.5, 34.1")], row,
                   open_={"coordinates": why("minimax-answered")},
                   kinds={"lat": "minimax", "lon": "minimax"}, journals=journals)  # fmt: skip
        assert TP.written(out) == {
            "lat": ("36.5", "35.1"),
            "lon": ("34.1", "33.4"),
            "geom": ("NEWGEOM", "SRID=4326;POINT(33.4 35.1)"),
        }
        assert {v.rule for v in out if v.ok} == {"wd5-restore", "wd5-point"}

    def test_a_point_one_coordinate_of_which_a_minimax_agent_moved_restores_that_one(self) -> None:
        row = TP.live(lat_text="36.5", lon_text="33.4", geom_text="NEWGEOM", geom_is_point=True)
        journals = {"lat": [link("35.1", "36.5")], "lon": [link(None, "33.4", "x", 3)],
                    "geom": [link("OLD", "NEWGEOM")]}  # fmt: skip
        out = five([wd5_decision("coordinates", "unresolved", None, "36.5, 33.4")], row,
                   open_={"coordinates": why("minimax-answered")},
                   kinds={"lat": "minimax", "lon": "sourced"}, journals=journals)  # fmt: skip
        assert TP.written(out)["lat"] == ("36.5", "35.1")
        assert "lon" not in TP.written(out)
        assert TP.written(out)["geom"][1] == "SRID=4326;POINT(33.4 35.1)"

    def test_a_point_nobody_wrote_stays_and_is_listed(self) -> None:
        for kinds in ({}, {"lat": "sourced", "lon": "sourced"}):
            out = five([wd5_decision("coordinates", "unresolved", None, "35.1, 33.4")],
                       open_={"coordinates": why("unsourced-point")}, kinds=kinds)  # fmt: skip
            assert TP.written(out) == {} and [v.reason for v in out] == ["coordinates-unresolved"]

    def test_a_restored_point_still_never_crosses_a_border(self) -> None:
        row = TP.live(lat_text="36.5", lon_text="34.1", geom_text="NEWGEOM", geom_is_point=True)
        journals = {"lat": [link("35.1", "36.5")], "lon": [link("33.4", "34.1")]}
        out = five([wd5_decision("coordinates", "unresolved", None, "36.5, 34.1")], row,
                   open_={"coordinates": why("minimax-answered")},
                   kinds={"lat": "minimax", "lon": "minimax"}, journals=journals,
                   country_check=TP.ELSEWHERE)  # fmt: skip
        assert TP.written(out) == {} and out[0].reason == "country-changes"

    def test_a_journal_that_does_not_end_at_the_live_value_refuses_the_restore(self) -> None:
        row = TP.live(period_start=-1200)
        journals = {"period_start": [link("-2500", "-999")]}  # the live value is not the last row's
        out = five([wd5_decision("period_start", "unresolved", None, -1200)], row,
                   open_={"period_start": why("minimax-answered")},
                   kinds={"period_start": "minimax"}, journals=journals)  # fmt: skip
        assert TP.written(out) == {}
        assert out[0].reason == "journal-disagrees"

    def test_an_unreadable_decision_withdraws_nothing(self) -> None:
        out = five([{**wd5_decision("period_start", "held", None, -4000)}],
                   TP.live(period_start=-4000), open_={"period_start": why("rule-made")},
                   kinds={"period_start": "rule"})  # fmt: skip
        assert [v.reason for v in out] == ["held-unreadable"]

    def test_the_other_rules_unresolved_stays_listed_even_for_a_minimax_value(self) -> None:
        out = FP.site_cells(
            TP.live(), {"open": {"site_type": {}}},
            {"site_type": TW.wd3_decision("site_type", "unresolved", None, "City")}, {},
            country_check=TP.AGREES, under=R.ONE_FAMILY, kinds={"site_type": "minimax"},
        )  # fmt: skip
        assert [v.reason for v in out] == ["field-unresolved"]


# ------------------------------------------------------------------------------ the wave and a step
class TestTheWaveAndTheStep:
    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setattr(FP, "REPO", tmp_path)
        monkeypatch.setattr(MA, "REPO", tmp_path)
        monkeypatch.setattr(HO, "REPO", tmp_path)
        run = tmp_path / "run"
        run.mkdir()
        R.write_run(run, RE)
        rows = []
        for site, why_ in ((TP.SITE, "rule-made"), (TP.OTHER, "minimax-answered")):
            rows.append({
                "site_id": site, "name": "Corycus", "asked": ["period_start"],
                "period_name": {"stored": "4500 - 3000 BC", "bucket_of_stored_start": "4500 - 3000 BC"},
                "open": {"period_start": {"why": why_, "wd1": None}},
            })  # fmt: skip
        (run / C.CLASSIFIED_FILE).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        HO._write_jsonl(run / HO.DECISIONS_FILE, [
            wd5_decision("period_start", "unresolved", None, -4000),
            {**wd5_decision("period_start", "unresolved", None, -4000), "site_id": TP.OTHER},
        ])  # fmt: skip
        HO._write_json(run / HO.REASK_FILE, {"after_round": 0, "fields": {}})
        return tmp_path

    @staticmethod
    def reader(sql: str) -> list[dict[str, Any]]:
        if "jsonb_array_elements" in sql:  # who made each value: only the first site's is a rule's
            return [made_row("period_start", -4000, rule=True) | {"site_id": TP.SITE}]
        if "remediation_change_log" in sql:
            return []
        return [TP.live(period_start=-4000, period_name="4500 - 3000 BC"),
                TP.live(site_id=TP.OTHER, period_start=-4000, period_name="4500 - 3000 BC")]  # fmt: skip

    def step(self) -> dict[str, Any]:
        return FP.build_step("2026-10-09a", 1, reader=self.reader, country_check=TP.AGREES,
                             frontend=lambda y: FP.categorize_period(y), stage="wd5")  # fmt: skip

    def test_the_wave_lives_under_wd5_and_takes_the_unresolved_it_may_withdraw(
        self, repo: Path
    ) -> None:
        result = FP.build_wave(repo / "run", "2026-10-09a")
        assert result == {"wave": "2026-10-09a", "sites": 2, "steps": 1, "held": 2}
        record = FP.read_wave("2026-10-09a", "wd5")
        assert record["rule"] == "recheck" and record["stage"] == "wd5"
        assert (
            FP.wave_dir("2026-10-09a", "wd5")
            == repo / "output/remediation/fields/wd5/write/2026-10-09a"
        )

    def test_an_unresolved_of_an_unsourced_point_is_no_wave_site(self, repo: Path) -> None:
        line = HO.read_classified(repo / "run")
        line[TP.SITE]["open"] = {"coordinates": {"why": "unsourced-point", "wd1": None}}
        (repo / "run" / C.CLASSIFIED_FILE).write_text(
            "".join(json.dumps(v) + "\n" for v in line.values()), encoding="utf-8"
        )
        HO._write_jsonl(repo / "run" / HO.DECISIONS_FILE, [
            wd5_decision("coordinates", "unresolved", None, "35.1, 33.4"),
        ])  # fmt: skip
        assert FP.build_wave(repo / "run", "2026-10-09a")["sites"] == 0

    def test_a_step_clears_the_rule_made_start_and_leaves_the_other_listed(
        self, repo: Path
    ) -> None:
        FP.build_wave(repo / "run", "2026-10-09a")
        result = self.step()
        assert result["cells"] == 2 and result["sites_written"] == 1
        assert result["refused:field-unresolved"] == 1
        out = FP.step_dir("2026-10-09a", 1, "wd5")
        records = MA.load_records(out / "PLAN.jsonl")
        assert [(r.column, r.old_value, r.new_value) for r in records] == [
            ("period_start", "-4000", None),
            ("period_name", "4500 - 3000 BC", "Undated"),
        ]
        assert out == repo / "output/remediation/fields/wd5/write/2026-10-09a/s001"
        undo = (out / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert "2026-10-09a_fields-wd5-s001-rollback" in undo
        sql = MA.render_transaction(
            records, site_ids={TP.SITE}, lane=L.fields_lane("2026-10-09a", 1, "wd5")
        )
        assert "WD5 field correction:" in sql and "'Undated'" in sql

    def test_a_wave_is_not_read_as_the_other_stage(self, repo: Path) -> None:
        FP.build_wave(repo / "run", "2026-10-09a")
        with pytest.raises(PlanError, match="was planned under recheck"):
            FP.wave_rule(FP.read_wave("2026-10-09a", "wd5"), "wd4")


# ------------------------------------------------------------------------------ the coast guard
import shapely  # noqa: E402
from bcases import classify as BC  # noqa: E402
from shapely.geometry import box  # noqa: E402


def atlas() -> tuple[list[str], list[Any], shapely.STRtree]:
    """Croatia and Bosnia share a land border at lon 18; Greece lies off to the south east; the
    island of Cyprus is drawn in two polygons and a base area; Scotland is far north."""
    names = ["Croatia", "Bosnia and Herzegovina", "Greece", "Cyprus", "Northern Cyprus",
             "Dhekelia Sovereign Base Area", "Republic of Serbia", "Kosovo", "United Kingdom"]  # fmt: skip
    geoms = [box(14, 42, 18, 46), box(18, 42, 20, 46), box(23, 36, 26, 39), box(32, 34.6, 33, 35.1),
             box(33, 35.1, 34, 35.7), box(33, 34.6, 34, 35.1), box(20, 43, 22, 45),
             box(20, 41, 22, 43), box(-8, 58, -5, 59)]  # fmt: skip
    return names, geoms, shapely.STRtree(geoms)


ATLAS = atlas()
#: One degree of latitude, in km, near 42 N (WGS84): the offsets below are chosen in these.
DEG_KM = 111.1


class TestTheCoastGuard:
    @staticmethod
    def moved(country: str, lat: float, lon: float, **kw: Any) -> dict[str, Any]:
        return BC.country_after_move(country, lat, lon, ATLAS, **kw)

    def test_a_point_in_the_sea_within_the_tolerance_counts_as_in_the_country(self) -> None:
        out = self.moved("Croatia", 42 - 1.0 / DEG_KM, 16.0)
        assert out["agrees"] and out["polygon"] == []
        assert out["note"].startswith("coast, 1.0") and out["note"].endswith(" km")

    def test_the_tolerance_is_2_5_km_and_no_more(self) -> None:
        assert BC.COAST_KM == 2.5
        assert self.moved("Croatia", 42 - 2.4 / DEG_KM, 16.0)["agrees"]
        refused = self.moved("Croatia", 42 - 2.6 / DEG_KM, 16.0)
        assert not refused["agrees"] and refused["note"] is None

    def test_the_tolerance_can_be_given_and_zero_is_the_plain_polygon_test(self) -> None:
        point = (42 - 3.0 / DEG_KM, 16.0)
        assert not self.moved("Croatia", *point)["agrees"]
        assert self.moved("Croatia", *point, tolerance_km=3.5)["agrees"]
        assert not self.moved("Croatia", 42 - 0.5 / DEG_KM, 16.0, tolerance_km=0)["agrees"]

    def test_a_point_inside_another_country_is_refused_however_near_the_stored_one_is(self) -> None:
        """Narona: 2.51 km inside Bosnia. The tolerance is for the sea; a land border is not
        crossed by it - the point lies in a polygon, so the polygon decides."""
        out = self.moved("Croatia", 44.0, 18.0 + 1.0 / (DEG_KM * 0.72))
        assert out["polygon"] == ["Bosnia and Herzegovina"] and not out["agrees"]

    def test_the_tolerance_needs_an_empty_polygon_query(self) -> None:
        near_greece_and_croatia = self.moved("Greece", 42 - 1.0 / DEG_KM, 16.0)
        assert not near_greece_and_croatia["agrees"]  # the sea off Croatia is not Greece's coast
        assert (
            self.moved("Greece", 37.0, 24.0)["agrees"]
            and self.moved("Greece", 37.0, 24.0)["note"] is None
        )

    def test_only_the_stored_countrys_coast_counts(self) -> None:
        # 1 km off Greece's coast: a Croatian row there is wrong, not on its coast
        assert not self.moved("Croatia", 36 - 1.0 / DEG_KM, 24.0)["agrees"]

    def test_the_distance_is_geodesic_not_degrees(self) -> None:
        """At 58 N a degree of longitude is 59 km, so 0.04 degrees west of Scotland's coast is
        2.36 km - within the tolerance - though 4.4 km as a distance in degrees times 111."""
        out = self.moved("Scotland", 58.5, -8.0 - 0.04)
        assert out["agrees"] and 2.2 < float(out["note"].split()[1]) < 2.5
        assert not self.moved("Scotland", 58.5, -8.0 - 0.06)["agrees"]

    def test_cyprus_is_one_island(self) -> None:
        for lat, lon, polygon in ((35.3, 33.5, "Northern Cyprus"), (34.8, 33.5, "Dhekelia Sovereign Base Area"),
                                  (34.8, 32.5, "Cyprus")):  # fmt: skip
            out = self.moved("Cyprus", lat, lon)
            assert out["agrees"] and out["polygon"] == [polygon]
        assert not self.moved("Greece", 35.3, 33.5)["agrees"]  # the equivalence is Cyprus's alone

    def test_a_sea_point_off_northern_cyprus_is_cyprus_s_coast(self) -> None:
        out = self.moved("Cyprus", 35.7 + 1.0 / DEG_KM, 33.5)
        assert out["agrees"] and out["note"].startswith("coast, 1.0")

    def test_kosovo_is_not_serbia_and_stays_refused(self) -> None:
        out = self.moved("Serbia", 42.0, 21.0)
        assert out["polygon"] == ["Kosovo"] and not out["agrees"]
        assert "kosovo" not in BC.POLITICAL_EQUIVALENTS.get("serbia", ())

    def test_crimea_keeps_ukraine_as_before(self) -> None:
        names, geoms = [*ATLAS[0], "Russia"], [*ATLAS[1], box(32, 44, 37, 47)]
        out = BC.country_after_move("Ukraine", 45.0, 34.0, (names, geoms, shapely.STRtree(geoms)))
        assert out["agrees"] and "B10" in out["note"]

    def test_a_cell_names_the_coast_it_was_let_through_on(self) -> None:
        check = lambda country, lat, lon: BC.country_after_move(country, lat, lon, ATLAS)  # noqa: E731
        sea = (42 - 1.0 / DEG_KM, 16.0)
        out = FP.site_cells(
            TP.live(country="Croatia"), {"open": {"coordinates": {}}},
            {"coordinates": wd5_decision("coordinates", "replace", f"{sea[0]}, {sea[1]}", "35.1, 33.4")},
            {}, country_check=check, under=R.ONE_FAMILY_PERIOD,
        )  # fmt: skip
        assert set(TP.written(out)) == {"lat", "lon", "geom"}
        assert "(coast, 1.0" in out[0].note
        beyond = (42 - 4.0 / DEG_KM, 16.0)
        out = FP.site_cells(
            TP.live(country="Croatia"), {"open": {"coordinates": {}}},
            {"coordinates": wd5_decision("coordinates", "replace", f"{beyond[0]}, {beyond[1]}", "35.1, 33.4")},
            {}, country_check=check, under=R.ONE_FAMILY_PERIOD,
        )  # fmt: skip
        assert out[0].reason == "country-changes" and "no country polygon" in out[0].note


# ------------------------------------------------------------------------------ the real boundaries
#: The refused better points of WD1 and WD3 (measured 2026-10-08 against `data/boundaries`): the 12
#: that lie within 2 km of their coast, Marco Gonzalez at 2.35 km, the Cyprus rows in the island's
#: other polygons - and the four that stay refused (X3).
REAL = (
    ("Paphos", "Cyprus", 34.76025, 32.40795, True, "coast, 0.35 km"),
    ("Clachtoll Broch", "Scotland", 58.195588, -5.342211, True, "coast, 0.89 km"),
    ("Marco Gonzalez", "Belize", 17.881998, -88.014887, True, "coast, 2.35 km"),
    ("Karpasia", "Cyprus", 35.62862, 34.37242, True, "coast, 1.62 km"),
    ("Kokkinokremmos", "Cyprus", 34.9905, 33.7142, True, None),  # Dhekelia base area
    ("Mersinaki", "Cyprus", 35.156834, 32.788315, True, None),  # Northern Cyprus
    ("Heracleion", "Egypt", 31.31278, 30.12889, False, None),  # 3.83 km out at sea
    ("Narona", "Croatia", 43.080406, 17.628031, False, None),  # inside Bosnia
    ("Kaljaja", "Serbia", 42.785454, 21.173462, False, None),  # Kosovo
    ("Flevum", "Germany", 52.451944, 4.669444, False, None),  # the Netherlands
)  # fmt: skip


class TestTheRealBoundaries:
    @pytest.fixture(scope="class")
    def real(self) -> Any:
        sys.path.insert(0, str(REPO / "output" / "remediation" / "tools"))
        import country_census as CC  # noqa: PLC0415

        return CC.load_countries()

    @pytest.mark.parametrize(("name", "country", "lat", "lon", "agrees", "note"), REAL)
    def test_the_refused_points_of_wd1_and_wd3(self, real: Any, name: str, country: str,
                                               lat: float, lon: float, agrees: bool,
                                               note: str | None) -> None:  # fmt: skip
        out = BC.country_after_move(country, lat, lon, real)
        assert out["agrees"] is agrees, name
        assert out["note"] == note, name


# ------------------------------------------------------------------------------ the owner list
from fields import owner_list as OL  # noqa: E402

S1, S2, S3, S4 = (f"00000000-0000-4000-8000-{n:012d}" for n in range(1, 5))


class TestTheOwnerList:
    """The 2026-10-08 defects of the list: a lane's own write was listed `refused` by the next
    wave of the same lane (1,252 cells), and a rule-made period was no state of its own."""

    @staticmethod
    def tree(tmp_path: Path, plan: list[dict[str, Any]], skipped: list[dict[str, Any]],
             decisions: list[dict[str, Any]], asked: dict[str, str],
             rule: R.Rule = R.ONE_FAMILY) -> tuple[Path, Path]:  # fmt: skip
        run, waves = tmp_path / rule.stage, tmp_path / rule.stage / "write"
        run.mkdir()
        R.write_run(run, rule)
        lines = [{"site_id": site, "name": f"Site {n}", "country": "Peru", "asked": [field],
                  "fields": {field: {"stored": None}}, "open": {field: {"why": "empty", "wd1": None}}}
                 for n, (site, field) in enumerate(asked.items())]  # fmt: skip
        HO._write_jsonl(run / C.CLASSIFIED_FILE, lines)
        HO._write_jsonl(run / "DECISIONS.jsonl", decisions)
        for name, rows in (("2026-10-02a", plan), ("2026-10-04", [])):
            wave = waves / name
            step = wave / "s001"
            step.mkdir(parents=True)
            HO._write_json(wave / "WAVE.json", {"run": OL._shown(run), "steps": [list(asked)]})
            (wave / "WAVE.sha256").write_text(TW.sha(wave / "WAVE.json") + "\n", encoding="utf-8")
            HO._write_jsonl(step / "PLAN.jsonl", rows)
            HO._write_jsonl(step / "SKIPPED.jsonl", skipped if name == "2026-10-04" else [])
            HO._write_json(step / "ACCEPTED.json", {"deviations": 0})
        return run, waves

    @staticmethod
    def plan_row(site: str, column: str, new: str, rule: str = "wd3-replace",
                 evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:  # fmt: skip
        return {"site_id": site, "column": column, "new_value": new, "rule": rule,
                "evidence": evidence or []}  # fmt: skip

    @staticmethod
    def decision(site: str, field: str, verdict: str) -> dict[str, Any]:
        return {"site_id": site, "field": field, "decision": verdict, "asked": 1,
                "reasoning": f"{verdict} reasoning", "via": "counted"}  # fmt: skip

    @staticmethod
    def moved(site: str, column: str, holds: str) -> dict[str, Any]:
        return {"site_id": site, "column": column, "reason": "moved-since-classification",
                "note": f"decided about None, holds {holds}"}  # fmt: skip

    def states(self, run: Path, waves: Path) -> dict[tuple[str, str], str]:
        return {(r["site_id"], r["field"]): r["state"] for r in OL.build([run], waves)["rows"]}

    def test_a_value_the_lane_wrote_and_a_later_wave_found_is_filled_not_refused(
        self, tmp_path: Path
    ) -> None:
        plan = [self.plan_row(S1, "period_start", "-4000"),
                self.plan_row(S2, "site_type", "Temple"),
                self.plan_row(S3, "lat", "36.5"), self.plan_row(S3, "lon", "34.1"),
                self.plan_row(S4, "source_url", "https://x.org/a")]  # fmt: skip
        skipped = [self.moved(S1, "period_start", "-4000"),
                   self.moved(S2, "site_type", "'Temple'"),
                   {**self.moved(S3, "lat", "36.5, 34.1")},
                   {**self.moved(S4, "source_url", "'https://elsewhere.org/'")}]  # fmt: skip
        decisions = [self.decision(S1, "period_start", "replace"), self.decision(S2, "site_type", "replace"),
                     self.decision(S3, "coordinates", "replace"), self.decision(S4, "source_url", "replace")]  # fmt: skip
        asked = {S1: "period_start", S2: "site_type", S3: "coordinates", S4: "source_url"}
        run, waves = self.tree(tmp_path, plan, skipped, decisions, asked)
        # S4's later wave found another value than the one written: a real refusal
        assert self.states(run, waves) == {(S4, "source_url"): "refused"}
        assert OL.build([run], waves)["counts"]["period_start"] == {"filled": 1}

    def test_a_refusal_before_any_write_stays_a_refusal(self, tmp_path: Path) -> None:
        run, waves = self.tree(
            tmp_path, [], [self.moved(S1, "period_start", "-4000")],
            [self.decision(S1, "period_start", "replace")], {S1: "period_start"},
        )  # fmt: skip
        assert self.states(run, waves) == {(S1, "period_start"): "refused"}

    def test_a_write_that_is_not_accepted_does_not_explain_a_refusal(self, tmp_path: Path) -> None:
        run, waves = self.tree(
            tmp_path, [self.plan_row(S1, "period_start", "-4000")],
            [self.moved(S1, "period_start", "-4000")],
            [self.decision(S1, "period_start", "replace")], {S1: "period_start"},
        )  # fmt: skip
        (waves / "2026-10-02a" / "s001" / "ACCEPTED.json").unlink()
        assert self.states(run, waves) == {(S1, "period_start"): "refused"}

    def test_a_start_a_rule_made_is_its_own_state_with_the_rules_reason(
        self, tmp_path: Path
    ) -> None:
        rule_evidence = [{"source": "WD3 decision (derived, round 0, rule:x)", "status": "RULE",
                          "reasoning": "site_type 'Megalithic stones' lies in 'Neolithic'"}]  # fmt: skip
        plan = [self.plan_row(S1, "period_start", "-4000", evidence=rule_evidence),
                self.plan_row(S1, "period_name", "4500 - 3000 BC", "wd3-derive-period-name"),
                self.plan_row(S2, "period_start", "-4000", evidence=rule_evidence)]  # fmt: skip
        # a site a rule dated has no decision of its own, or a model that found no source
        decisions = [self.decision(S2, "period_start", "unresolved")]
        run, waves = self.tree(
            tmp_path, plan, [], decisions, {S1: "period_start", S2: "period_start"}
        )
        result = OL.build([run], waves)
        assert self.states(run, waves) == {
            (S1, "period_start"): "rule",
            (S2, "period_start"): "rule",
        }
        assert result["counts"]["period_start"] == {"rule": 2}
        assert "lies in 'Neolithic'" in result["rows"][0]["reason"]
        assert OL.RULE in OL.LISTED
        assert "a start a rule made" in OL.render(result, [run])

    def test_a_rule_made_start_that_a_later_lane_kept_with_a_quote_is_sourced(self) -> None:
        cell = {"rule_made": True, "accepted": True, "rule": "wd4-replace", "written": True,
                "rule_note": "derived"}  # fmt: skip
        kept = {"decision": "keep", "reasoning": "the page dates it", "site_id": S1,
                "field": "period_start"}  # fmt: skip
        assert OL.state_of(kept, cell, True) == (OL.SOURCED, "the page dates it")
        for verdict in ("unresolved", "replace"):
            assert OL.state_of({**kept, "decision": verdict}, cell, True)[0] == OL.RULE, verdict
        assert OL.state_of(None, cell, True)[0] == OL.RULE

    def test_a_rule_row_is_not_a_filled_field(self, tmp_path: Path) -> None:
        evidence = [{"source": "s", "status": "RULE", "reasoning": "r"}]
        decisions = [self.decision(S1, "period_start", "replace")]
        run, waves = self.tree(tmp_path, [self.plan_row(S1, "period_start", "-4000", evidence=evidence)],
                               [], decisions, {S1: "period_start"})  # fmt: skip
        assert self.states(run, waves) == {(S1, "period_start"): "rule"}

    def test_a_wd5_run_has_a_list_and_a_withdrawn_value_is_listed_as_such(
        self, tmp_path: Path
    ) -> None:
        plan = [self.plan_row(S1, "period_start", "", "wd5-clear")]
        plan[0]["new_value"] = None
        decisions = [self.decision(S1, "period_start", "unresolved")]
        run, waves = self.tree(tmp_path, plan, [], decisions, {S1: "period_start"}, RE)
        rows = OL.build([run], waves)["rows"]
        assert [(r["state"], r["field"]) for r in rows] == [("unresolved", "period_start")]
        assert "withdrawn (wd5-clear)" in rows[0]["reason"]
        assert RE in OL.OWNED_RULES

    def test_a_rule_s_start_that_a_later_wave_replaced_is_no_longer_the_rules(
        self, tmp_path: Path
    ) -> None:
        evidence = [{"source": "s", "status": "RULE", "reasoning": "r"}]
        plan = [self.plan_row(S1, "period_start", "-4000", evidence=evidence)]
        run, waves = self.tree(tmp_path, plan, [], [self.decision(S1, "period_start", "replace")],
                               {S1: "period_start"})  # fmt: skip
        later = waves / "2026-10-04" / "s001"
        HO._write_jsonl(
            later / "PLAN.jsonl", [self.plan_row(S1, "period_start", "-2500", "wd3-replace")]
        )
        assert self.states(run, waves) == {}  # filled by the later write, not the rule's any more
