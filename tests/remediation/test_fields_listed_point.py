"""Lane wd5, the listed-point run (`population.py build --stage wd5 --sites FILE --point`).

Follow-up 1 of the close-out of 2026-10-24: Sybaris on the Traeis holds the point of Sybaris, and
no command asked one named site's coordinates again (`--sites` built a `period_start` question
only). The run asks the stored point of each listed site and nothing else; these tests pin what it
adds to a wd5 run: the reason the question names, which listed points are refused, the run's
record and what the write plan does with its answers. Offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.remediation import test_fields_plan as TP
from tests.remediation import test_fields_wd3 as TW
from tests.remediation import test_fields_wd5_reask as TR
from tests.remediation.test_fields_wd5 import SITE_ID, five, made_of, made_row, wd5_decision, why
from tests.remediation.test_fields_wd5_reask import HO, POP, R

REASON = "the record holds the point of Sybaris; the city lay on the Trionto, about 25 km away"
POINT = "35.1, 33.4"


def said(decision: str, run: str = "wd5", reasoning: str = "no source gives a point") -> Any:
    return run, {"site_id": SITE_ID, "field": "coordinates", "decision": decision,
                 "reasoning": reasoning}  # fmt: skip


def answers(*rows: Any) -> dict[tuple[str, str], list[Any]]:
    return {(SITE_ID, "coordinates"): list(rows)}


class TestTheQuestion:
    def test_a_listed_point_is_asked_under_its_own_reason(self) -> None:
        opened = POP.listed_point_fields([], listed=REASON)
        assert list(opened) == ["coordinates"]
        cell = opened["coordinates"]
        assert cell["why"] == "listed-point" == POP.WHY_LISTED_POINT
        assert cell["reader_gap"] == "listed-point" and cell["wd1"] is None
        assert cell["made"] == f"the orchestrator named this site's stored point for a second look: {REASON}"  # fmt: skip

    def test_the_latest_answer_about_the_point_is_shown_as_a_lead(self) -> None:
        rows = [said("unresolved", "wd3", "older"), said("unresolved", "wd5", "x" * 900)]
        made = POP.listed_point_fields(rows, listed=REASON)["coordinates"]["made"]
        assert f"{REASON}. The pass of wd5 answered unresolved: " in made
        assert made.endswith("x" * POP.READER_GAP_SHOWN_CHARS) and "older" not in made

    def test_a_site_the_list_does_not_name_is_not_asked(self) -> None:
        assert POP.listed_point_fields([said("unresolved")], listed=None) == {}

    def test_the_question_names_the_reason_to_the_agent(self) -> None:
        assert set(HO.OPEN_TEXT) == set(POP.WHYS) and POP.WHY_LISTED_POINT in HO.OPEN_TEXT
        line = TW.wd3_line(asked=["coordinates"])
        line["open"] = POP.listed_point_fields([], listed=REASON)
        lines = HO._open_lines(line, "coordinates")
        assert lines[0].startswith("Open because: the stored point is asked once more")
        assert lines[1].startswith("What stands: the orchestrator named this site's stored point")
        prompt = HO.render_prompt(line, ["coordinates"], rule=R.RECHECK)
        assert REASON in prompt and "### coordinates" in prompt and "### period_start" not in prompt


class TestTheListedPoints:
    def test_a_point_no_source_stands_behind_may_be_asked_again(self) -> None:
        stored = {SITE_ID: TW.stored_row()}
        POP.check_listed_points({SITE_ID: "r"}, stored, {}, {})
        POP.check_listed_points({SITE_ID: "r"}, stored, {}, answers(said("unresolved")))
        # a keep an older pass gave and a later one did not: the latest answer decides
        POP.check_listed_points(
            {SITE_ID: "r"}, stored, {}, answers(said("keep", "wd3"), said("unresolved"))
        )
        # a point a MiniMax agent wrote is no sourced one
        minimax = made_of(made_row("lat", "37.9755", minimax=True, confidence="two_source"))
        POP.check_listed_points({SITE_ID: "r"}, stored, minimax, {})

    def test_a_listed_point_must_be_askable(self) -> None:
        row = TW.stored_row()
        sourced = made_of(made_row("lat", "37.9755", confidence="two_source"))
        cases = (
            ({}, {}, {}, "not a curated site"),
            ({SITE_ID: {**row, "scope_status": "retired"}}, {}, {}, "retired"),
            ({SITE_ID: row}, sourced, {}, "another lane's sourced write"),
            ({SITE_ID: row}, {}, answers(said("unresolved", "wd3"), said("keep")),
             "the pass of wd5 kept its point on a quoted source"),
        )  # fmt: skip
        for stored, made, told, message in cases:
            with pytest.raises(POP.PopulationError, match=message):
                POP.check_listed_points({SITE_ID: "r"}, stored, made, told)

    def test_every_offender_is_named(self) -> None:
        with pytest.raises(POP.PopulationError) as caught:
            POP.check_listed_points({"x": "r", "y": "r"}, {}, {}, {})
        assert "x: not a curated" in str(caught.value) and "y: not a curated" in str(caught.value)
        assert str(caught.value).startswith("the listed point(s) cannot be asked again: ")


class TestTheRun:
    fixtures = TR.TestTheRun()

    def reask(self, **kw: object) -> POP.Reask:
        base: dict[str, object] = {"answers": {}, "detect": False, "listed": {SITE_ID: REASON},
                                   "already": frozenset(), "why": POP.WHY_LISTED_POINT}  # fmt: skip
        return POP.Reask(**{**base, **kw})  # type: ignore[arg-type]

    def test_the_run_asks_the_point_of_the_listed_site_and_nothing_else(
        self, tmp_path: Path
    ) -> None:
        root, out = self.fixtures.prepare(tmp_path)  # its period is empty too: not asked here
        counts = self.fixtures.build(root, out, self.reask(answers=answers(said("unresolved"))))
        line = json.loads((out / "CLASSIFIED.jsonl").read_text(encoding="utf-8"))
        assert line["asked"] == ["coordinates"]
        assert line["open"]["coordinates"]["why"] == "listed-point"
        assert "The pass of wd5 answered unresolved" in line["open"]["coordinates"]["made"]
        assert counts["population"]["why"] == {"coordinates:listed-point": 1}
        assert counts["reader_gap"]["asked"] == {"listed-point": 1}
        run = json.loads((out / R.RUN_FILE).read_text(encoding="utf-8"))
        assert run["reask"]["why"] == "listed-point" and run["reask"]["listed"] == {SITE_ID: REASON}
        assert R.read_rule(out) is R.RECHECK and not HO.is_d99_run(out)

    def test_a_site_the_list_does_not_name_is_not_in_the_run(self, tmp_path: Path) -> None:
        root, out = self.fixtures.prepare(tmp_path)
        other = "00000000-0000-4000-8000-000000000001"
        with pytest.raises(POP.PopulationError, match=f"{other}: not a curated site"):
            self.fixtures.build(root, out, self.reask(listed={other: "r"}))
        assert not (out / R.RUN_FILE).exists()

    def test_a_listed_point_a_source_stands_behind_refuses_before_anything_is_written(
        self, tmp_path: Path
    ) -> None:
        root, out = self.fixtures.prepare(tmp_path)
        with pytest.raises(POP.PopulationError, match="kept its point on a quoted source"):
            self.fixtures.build(root, out, self.reask(answers=answers(said("keep"))))
        assert not (out / R.RUN_FILE).exists()

    def test_a_listed_point_run_neither_detects_nor_skips(self, tmp_path: Path) -> None:
        root, out = self.fixtures.prepare(tmp_path)
        with pytest.raises(POP.PopulationError, match="the points of its listed sites only"):
            self.fixtures.build(root, out, self.reask(detect=True))
        with pytest.raises(POP.PopulationError, match="the points of its listed sites only"):
            self.fixtures.build(root, out, self.reask(already=frozenset({"x"})))
        assert not (out / R.RUN_FILE).exists()

    def test_the_main_refuses_point_without_its_flags(self, tmp_path: Path) -> None:
        home = tmp_path / POP.POINT_RUNS / "2026-11-11"
        base = ["--out", str(home), "build", "--root", str(tmp_path), "--point"]
        for extra in (["--stage", "wd5"], ["--stage", "wd3", "--sites", "x"],
                      ["--stage", "wd5", "--sites", "x", "--reask-cleared"],
                      ["--stage", "wd5", "--sites", "x", "--d99"]):  # fmt: skip
            with pytest.raises(SystemExit):
                POP.main(base + extra)

    def test_the_main_builds_a_listed_point_run_only_where_the_owner_list_reads_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        flags = ["build", "--root", str(tmp_path), "--stage", "wd5", "--point", "--sites",
                 str(tmp_path / "none.jsonl"), "--wd1-dir", str(tmp_path / "none")]  # fmt: skip
        with pytest.raises(SystemExit):
            POP.main(["--out", str(tmp_path / "elsewhere" / "2026-11-11"), *flags])
        assert f"<fields>/{POP.POINT_RUNS}/<label>" in capsys.readouterr().err
        # in its home the flags pass, and the missing list is the build's own refusal
        assert POP.main(["--out", str(tmp_path / POP.POINT_RUNS / "2026-11-11"), *flags]) == 1
        assert "none.jsonl is missing" in capsys.readouterr().err


class TestTheWritePlan:
    OPEN = {"coordinates": why("listed-point")}

    def test_a_sourced_point_replaces_the_listed_one(self) -> None:
        out = five([wd5_decision("coordinates", "replace", "36.5, 34.1", POINT)],
                   open_=self.OPEN, kinds={"lat": None, "lon": None})  # fmt: skip
        assert set(TP.written(out)) == {"lat", "lon", "geom"}
        assert TP.written(out)["lat"] == ("35.1", "36.5")

    def test_a_point_another_lane_sourced_since_is_not_replaced(self) -> None:
        out = five([wd5_decision("coordinates", "replace", "36.5, 34.1", POINT)],
                   open_=self.OPEN, kinds={"lat": "sourced", "lon": "sourced"})  # fmt: skip
        assert TP.written(out) == {} and [v.reason for v in out] == ["sourced-value"]

    def test_an_unresolved_answer_leaves_the_point(self) -> None:
        out = five([wd5_decision("coordinates", "unresolved", None, POINT)],
                   open_=self.OPEN, kinds={"lat": None, "lon": None})  # fmt: skip
        assert TP.written(out) == {} and [v.reason for v in out] == ["coordinates-unresolved"]
