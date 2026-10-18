"""Lane wd5, the reader-gap run (`population.py build --stage wd5 --reask-cleared | --sites`).

The pilot of 2026-10-09 cleared three periods to `Undated` where the answer itself named a dated
value that the machine readers of that day could not read (a Hungarian century, a Ukrainian
millennium, an `Early Classic` the table did not hold). The run asks `period_start` of such empty
periods again and of the sites the orchestrator lists. Offline, like the lanes before it.
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
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import population as POP  # noqa: E402
from fields import rule as R  # noqa: E402

from tests.remediation import test_fields_plan as TP  # noqa: E402
from tests.remediation import test_fields_wd3 as TW  # noqa: E402
from tests.remediation.test_fields_classify import TABLE  # noqa: E402
from tests.remediation.test_fields_wd5 import (  # noqa: E402
    MINIMAX,
    SITE_ID,
    TestTheRecheckRun,
    five,
    made_of,
    made_row,
    wd5_decision,
    why,
)

CLAUDE = "anthropic/claude-opus-5-5 (Claude Code agent)"
HUNGARIAN = (
    "English Wikipedia dates only the fortification; Hungarian Wikipedia says the town was "
    "inhabited already in the 7th century BC ('már az i. e. 7. században is lakták a várost'), "
    "which the check does not read, so no start can be recorded."
)
NO_BLAME = "Wikipedia dates the fortification to the 5th century BC, not the start of the site."


def answer(reasoning: str = HUNGARIAN, *, decision: str = "unresolved", model: str | None = CLAUDE,
           via: str = "counted", quotes: list[dict[str, Any]] | None = None
           ) -> dict[str, Any]:  # fmt: skip
    return {"site_id": SITE_ID, "field": "period_start", "decision": decision, "model": model,
            "via": via, "reasoning": reasoning, "quotes": quotes or [], "value": None,
            "stored": None}  # fmt: skip


def gap(*rows: tuple[str, dict[str, Any]], row: dict[str, Any] | None = None,
        made: dict[Any, Any] | None = None, listed: str | None = None,
        detect: bool = True) -> tuple[dict[str, Any], str | None]:  # fmt: skip
    return POP.reader_gap_fields(
        TW.line_of(), row or TW.stored_row(period_start=None), list(rows), made or {},
        listed=listed, detect=detect,
    )  # fmt: skip


class TestWhatTheReadersReadToday:
    def test_an_age_before_the_present_is_a_bp_date(self) -> None:
        kind, what = POP.readable_date("charcoal from the hearth gave 12,000 BP") or ("", "")
        assert kind == "bp-age" and "10050" in what

    def test_a_century_in_another_language_is_a_dated_statement(self) -> None:
        kind, what = POP.readable_date(HUNGARIAN) or ("", "")
        assert kind == "dated-statement" and "century 7 BC" in what

    def test_a_period_the_table_holds_is_a_period_name(self) -> None:
        found = POP.readable_date("English Wikipedia says the site dates from the Early Classic")
        assert found is not None and found[0] == "period-name"

    def test_a_modern_year_and_a_late_one_state_no_start(self) -> None:
        assert POP.readable_date("surveyed in 1887, restored in 1998") is None
        assert POP.readable_date("the wall was built in 449 and rebuilt in 1200") is None
        assert POP.readable_date("the church was built in AD 1700") is None
        assert POP.readable_date("nothing here is dated") is None

    def test_the_quotes_of_an_answer_count_with_its_reasoning(self) -> None:
        said = answer("no start", quotes=[{"url": "u", "quote": "inhabited in the 7th century BC"}])
        assert "7th century BC" in POP._answer_text(said)


class TestWhichAnswersAreAReaderGap:
    def test_a_claude_unresolved_that_blames_a_reader_and_names_a_value_is(self) -> None:
        run, kind, what = POP.reader_gap_reading([("wd5-pilot", answer())]) or ("",) * 3
        assert (run, kind) == ("wd5-pilot", "dated-statement") and "BC" in what

    def test_a_date_in_an_answer_that_blames_no_reader_is_a_lead_the_agent_dropped(self) -> None:
        assert POP.reader_gap_reading([("wd5", answer(NO_BLAME))]) is None

    def test_a_blame_without_a_value_the_readers_read_is_not(self) -> None:
        assert POP.reader_gap_reading([("wd5", answer("the check cannot read Spanish"))]) is None

    def test_only_the_latest_answer_counts(self) -> None:
        later = answer("Wikipedia gives 5100 BC", decision="replace")
        assert POP.reader_gap_reading([("wd3", answer()), ("wd5", later)]) is None
        assert POP.reader_gap_reading([]) is None

    def test_an_adversarial_rejection_is_a_source_that_was_read(self) -> None:
        assert POP.reader_gap_reading([("wd5", answer(via="adversarial"))]) is None
        assert POP.reader_gap_reading([("wd5", answer(via="exhausted"))]) is None

    def test_a_minimax_answer_or_one_without_a_model_is_not_a_claude_answer(self) -> None:
        for model in (MINIMAX, None, "openai/gpt-5 (Codex agent)"):
            assert POP.reader_gap_reading([("wd4", answer(model=model))]) is None
        assert POP.reader_gap_reading([("wd5", answer(model=OH.SONNET_MODEL))]) is not None

    def test_a_keep_is_not_a_gap(self) -> None:
        assert POP.reader_gap_reading([("wd5", answer(decision="keep"))]) is None


class TestWhatAReaderGapRunAsks:
    def test_an_empty_period_of_a_reader_gap_is_asked_with_a_note_of_its_own(self) -> None:
        opened, skipped = gap(("wd5-pilot", answer()))
        assert skipped is None and list(opened) == ["period_start"]
        info = opened["period_start"]
        assert info["why"] == "reader-gap" == POP.WHY_READER_GAP
        assert info["reader_gap"] == "dated-statement" and info["wd1"] is None
        assert "wd5-pilot answered unresolved" in info["made"]
        assert "century 7 BC" in info["made"] and "readers of that day" in info["made"]

    def test_a_site_that_is_none_is_not_asked(self) -> None:
        assert gap(("wd5", answer(NO_BLAME))) == ({}, None)
        assert gap(("wd5", answer()), detect=False) == ({}, None)

    def test_a_period_stored_since_is_left_alone_and_counted(self) -> None:
        row = TW.stored_row(period_start=-700)
        assert gap(("wd5", answer()), row=row) == ({}, "not-empty")
        assert gap(row=row, listed="r") == ({}, "not-empty")

    def test_another_lanes_sourced_write_is_never_asked(self) -> None:
        sourced = made_of(made_row("period_start", None, confidence="two_source"))
        assert gap(("wd5", answer()), made=sourced) == ({}, "sourced")
        assert gap(made=sourced, listed="r") == ({}, "sourced")
        cleared = made_of(made_row("period_start", None, withdrawn=True))
        assert gap(("wd5", answer()), made=cleared)[1] is None  # wd5's own clear is not a source

    def test_a_listed_site_is_asked_with_the_orchestrators_reason(self) -> None:
        opened, skipped = gap(listed="a source states the 6th century BC in Polish")
        assert skipped is None
        assert opened["period_start"]["reader_gap"] == "listed"
        assert "Polish" in opened["period_start"]["made"]

    def test_the_question_names_the_reason_to_the_agent(self) -> None:
        assert set(HO.OPEN_TEXT) == set(POP.WHYS) and "reader-gap" in HO.OPEN_TEXT
        opened, _ = gap(("wd5-pilot", answer()))
        line = {**TW.line_of(), "open": opened}
        lines = HO._open_lines(line, "period_start")
        assert lines[0].startswith("Open because: the start is empty")
        assert "What stands: the period is empty" in lines[1]


class TestTheListedSites:
    def write(self, tmp_path: Path, *rows: Any) -> Path:
        path = tmp_path / "sites.jsonl"
        path.write_text("".join(f"{json.dumps(r)}\n" for r in rows), encoding="utf-8")
        return path

    def test_a_file_names_sites_with_reasons(self, tmp_path: Path) -> None:
        path = self.write(
            tmp_path, {"site_id": "a", "reason": " r1 "}, {"site_id": "b", "reason": "r2"}
        )
        assert POP.read_listed(path) == {"a": "r1", "b": "r2"}

    def test_a_malformed_file_is_refused_by_line(self, tmp_path: Path) -> None:
        with pytest.raises(POP.PopulationError, match="is missing"):
            POP.read_listed(tmp_path / "none.jsonl")
        with pytest.raises(POP.PopulationError, match="lists no site"):
            POP.read_listed(self.write(tmp_path))
        with pytest.raises(POP.PopulationError, match=r"sites.jsonl:1 is not"):
            POP.read_listed(self.write(tmp_path, {"site_id": "a"}))
        with pytest.raises(POP.PopulationError, match="comes with no reason"):
            POP.read_listed(self.write(tmp_path, {"site_id": "a", "reason": "  "}))
        with pytest.raises(POP.PopulationError, match="a is listed twice"):
            POP.read_listed(
                self.write(
                    tmp_path, {"site_id": "a", "reason": "x"}, {"site_id": "a", "reason": "y"}
                )
            )

    def test_a_listed_site_must_be_askable(self) -> None:
        empty = TW.stored_row(period_start=None)
        POP.check_listed({SITE_ID: "r"}, {SITE_ID: empty}, {})
        cases = (
            ({}, {}, "not a curated site"),
            ({SITE_ID: {**empty, "scope_status": "retired"}}, {}, "retired"),
            ({SITE_ID: TW.stored_row(period_start=-700)}, {}, "holds period_start -700 now"),
            ({SITE_ID: empty}, made_of(made_row("period_start", None, confidence="two_source")),
             "another lane's sourced write"),
        )  # fmt: skip
        for stored, made, message in cases:
            with pytest.raises(POP.PopulationError, match=message):
                POP.check_listed({SITE_ID: "r"}, stored, made)

    def test_every_offender_is_named(self) -> None:
        with pytest.raises(POP.PopulationError) as caught:
            POP.check_listed({"x": "r", "y": "r"}, {}, {})
        assert "x: not a curated" in str(caught.value) and "y: not a curated" in str(caught.value)


class TestTheAnswersTheRunReads:
    def test_the_answers_of_each_run_come_oldest_first(self, tmp_path: Path) -> None:
        first = {**TW.d("period_start", "unresolved"), "model": MINIMAX}
        wd1 = TW.wd1([first])
        for stage in POP.REASK_HISTORY_RUNS:
            rows = [answer(stage)] if stage in ("wd4", "wd5") else []
            HO._write_jsonl(tmp_path / stage / "DECISIONS.jsonl", rows)
        answers = POP.read_answers(wd1, tmp_path, POP.REASK_HISTORY_RUNS)[(SITE_ID, "period_start")]
        assert [run for run, _ in answers] == ["wd1", "wd4", "wd5"]
        assert POP.REASK_HISTORY_RUNS[-2:] == ("wd5-pilot", "wd5")

    def test_a_site_the_reader_gap_run_decided_is_never_asked_again(self, tmp_path: Path) -> None:
        assert POP.decided_by_reask(tmp_path) == frozenset()  # not answered yet
        HO._write_jsonl(
            tmp_path / POP.REASK_RUN / "DECISIONS.jsonl",
            [answer(), {**answer(), "field": "site_type", "site_id": "other"}],
        )
        assert POP.decided_by_reask(tmp_path) == frozenset({SITE_ID})


class TestTheRun:
    fixtures = TestTheRecheckRun()

    def prepare(self, tmp_path: Path, **stored: Any) -> tuple[Path, Path]:
        stored.setdefault("period_start", None)
        stored.setdefault("period_name", "Undated")
        return self.fixtures.prepare(tmp_path, [], **stored)

    def reask(self, detect: bool = True, listed: dict[str, str] | None = None,
              rows: list[tuple[str, dict[str, Any]]] | None = None,
              already: frozenset[str] = frozenset()) -> POP.Reask:  # fmt: skip
        rows = [("wd5-pilot", answer())] if rows is None else rows
        return POP.Reask({(SITE_ID, "period_start"): rows}, detect, listed or {}, already)

    def build(self, root: Path, out: Path, reask: POP.Reask, **kw: Any) -> dict[str, Any]:
        return POP.build(root, out, table=TABLE, wd1=TW.wd1([]), stage="wd5", history={},
                         reask=reask, **kw)  # fmt: skip

    def test_the_run_asks_period_start_of_the_reader_gap_and_records_why(
        self, tmp_path: Path
    ) -> None:
        root, out = self.prepare(tmp_path)
        counts = self.build(root, out, self.reask())
        line = json.loads((out / C.CLASSIFIED_FILE).read_text(encoding="utf-8"))
        assert line["asked"] == ["period_start"]
        assert line["open"]["period_start"]["why"] == "reader-gap"
        assert counts["population"]["why"] == {"period_start:reader-gap": 1}
        assert counts["reader_gap"] == {
            "asked": {"dated-statement": 1}, "skipped": {}, "detect": True, "listed": 0,
            "already_decided_sites": 0,
        }  # fmt: skip
        saved = json.loads((out / C.COUNTS_FILE).read_text(encoding="utf-8"))
        assert saved["reader_gap"]["asked"] == {"dated-statement": 1}
        run = json.loads((out / R.RUN_FILE).read_text(encoding="utf-8"))
        assert run["reask"]["detect"] is True and run["reask"]["reads"][-1] == "wd5"
        assert R.read_rule(out) is R.RECHECK

    def test_a_listed_site_is_asked_and_recorded(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path)
        counts = self.build(root, out, self.reask(False, {SITE_ID: "Polish source"}, []))
        assert counts["reader_gap"]["asked"] == {"listed": 1}
        run = json.loads((out / R.RUN_FILE).read_text(encoding="utf-8"))
        assert run["reask"]["listed"] == {SITE_ID: "Polish source"}

    def test_a_period_stored_since_is_not_asked_and_counted(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path, period_start=-700, period_name="1500 - 500 BC")
        counts = self.build(root, out, self.reask())
        assert counts["population"]["sites"] == 0
        assert counts["reader_gap"]["skipped"] == {"not-empty": 1}

    def test_a_site_a_reader_gap_run_decided_is_skipped_and_counted(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path)
        counts = self.build(root, out, self.reask(already=frozenset({SITE_ID})))
        assert counts["population"]["sites"] == 0
        assert counts["reader_gap"]["skipped"] == {"already-reasked": 1}
        assert counts["reader_gap"]["already_decided_sites"] == 1

    def test_a_listed_site_that_cannot_be_asked_refuses_before_anything_is_written(
        self, tmp_path: Path
    ) -> None:
        root, out = self.prepare(tmp_path, period_start=-700)
        with pytest.raises(POP.PopulationError, match="holds period_start -700 now"):
            self.build(root, out, self.reask(False, {SITE_ID: "r"}, []))
        assert not (out / R.RUN_FILE).exists()
        root, out = self.prepare(tmp_path / "again")
        with pytest.raises(POP.PopulationError, match="decided by wd5-reask already"):
            self.build(root, out, self.reask(False, {SITE_ID: "r"}, [], frozenset({SITE_ID})))
        assert not (out / R.RUN_FILE).exists()

    def test_a_reader_gap_run_is_one_run_of_the_recheck_rule(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path)
        with pytest.raises(POP.PopulationError, match="no pilot, no --without"):
            self.build(root, out, self.reask(), pilot=(1, 7))
        with pytest.raises(POP.PopulationError, match="no pilot, no --without"):
            self.build(root, out, self.reask(), without=tmp_path)
        with pytest.raises(POP.PopulationError, match="needs --reask-cleared or --sites"):
            self.build(root, out, self.reask(False, {}, []))
        with pytest.raises(POP.PopulationError, match="a stage wd5 run, not 'wd3'"):
            POP.build(root, out, table=TABLE, wd1=TW.wd1([]), stage="wd3", reask=self.reask())
        assert not (out / R.RUN_FILE).exists()

    def test_the_main_refuses_the_flags_of_another_stage(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            POP.main(["--out", str(tmp_path), "build", "--root", str(tmp_path), "--stage", "wd3",
                      "--reask-cleared"])  # fmt: skip

    def test_the_main_refuses_a_listed_site_file_that_is_missing(self, tmp_path: Path) -> None:
        root, out = self.prepare(tmp_path)
        argv = ["--out", str(out), "build", "--root", str(root), "--stage", "wd5",
                "--wd1-dir", str(tmp_path / "none"), "--sites", str(tmp_path / "none.jsonl")]  # fmt: skip
        assert POP.main(argv) == 1


class TestTheWritePlan:
    def test_a_found_start_fills_the_empty_period_with_its_label(self) -> None:
        row = TP.live(period_start=None, period_name="Undated")
        out = five([wd5_decision("period_start", "replace", "-700", None)], row,
                   open_={"period_start": why("reader-gap")}, kinds={"period_start": None})  # fmt: skip
        assert TP.written(out) == {
            "period_start": (None, "-700"),
            "period_name": ("Undated", "1500 - 500 BC"),
        }

    def test_a_period_written_since_by_another_lane_is_not_overwritten(self) -> None:
        row = TP.live(period_start=-3000)
        out = five([wd5_decision("period_start", "replace", "-700", None)], row,
                   open_={"period_start": why("reader-gap")}, kinds={"period_start": "sourced"})  # fmt: skip
        assert TP.written(out) == {}
        assert [v.reason for v in out] == ["moved-since-classification"]

    def test_an_unresolved_answer_withdraws_nothing(self) -> None:
        row = TP.live(period_start=None, period_name="Undated")
        out = five([wd5_decision("period_start", "unresolved", None, None)], row,
                   open_={"period_start": why("reader-gap")}, kinds={"period_start": None})  # fmt: skip
        assert TP.written(out) == {} and [v.reason for v in out] == ["field-unresolved"]
