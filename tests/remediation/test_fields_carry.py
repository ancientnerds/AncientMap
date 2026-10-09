"""Lane wd5, D19: the decisions of the refused points are carried into the run (`fields/carry.py`).

The 23 points the country guard refused already have a decision with a quote. The run does not ask
them again: it carries the decision and the write plan runs its (now tolerant) country check once
more. Offline: the waves and runs are temporary directories, the country check a function.
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

from fields import carry as CA  # noqa: E402
from fields import classify as C  # noqa: E402
from fields import handoff as HO  # noqa: E402
from fields import rule as R  # noqa: E402

COAST = "9d58f665-8cc3-4438-9dc5-99885deb90d0"
INLAND = "c070b6b0-3fd2-4d6c-acbe-105539188253"
ASKED_BEFORE = "73106998-2108-42c6-8b07-3a1c79783968"
STORED = "35.15098318594448, 32.81127348296412"
CLAUDE = "anthropic/claude-sonnet-5-5 (Claude Code agent)"
MINIMAX = "minimax/MiniMax-M3.1-Flash-Preview (MiniMax Code agent)"


def agrees(country: str, lat: float, lon: float) -> dict[str, Any]:
    return {"agrees": True, "polygon": [], "note": "coast, 0.4 km"}


def refuses(country: str, lat: float, lon: float) -> dict[str, Any]:
    return {"agrees": False, "polygon": ["Bosnia and Herzegovina"]}


def decision(site: str, verdict: str = "replace", **over: Any) -> dict[str, Any]:
    row = {
        "site_id": site,
        "name": "Mersinaki",
        "field": "coordinates",
        "status": "MISSING",
        "stored": STORED,
        "asked": 1,
        "decision": verdict,
        "value": "35.156834, 32.788315" if verdict == "replace" else None,
        "via": "counted",
        "round": 1,
        "counted_rounds": [1],
        "answered_by": "wd3-r1-b0004",
        "model": CLAUDE,
        "quotes": [
            {"source": "https://x.org/a", "quote": "35.156834, 32.788315", "outcome": "found"}
        ],  # fmt: skip
        "reasoning": "the register gives the point",
        "value_page": None,
    }
    row.update(over)
    return row


def line(site: str, *, asked: list[str] | None = None, stored: str = STORED) -> dict[str, Any]:
    return {
        "site_id": site,
        "name": "Mersinaki",
        "country": "Cyprus",
        "asked": ["coordinates"] if asked is None else asked,
        "fields": {"coordinates": {"stored": stored}},
        "open": {"coordinates": {"why": "unsourced-point"}},
    }


def refusal(path: Path, *sites: str, reason: str = "country-changes", column: str = "lat") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"site_id": s, "site_name": "x", "column": column, "reason": reason} for s in sites]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class World:
    """A fields directory with a WD3 run that decided, and its wave that refused."""

    def __init__(self, tmp_path: Path, decisions: list[dict[str, Any]], *sites: str) -> None:
        self.fields = tmp_path / "fields"
        self.run = self.fields / "wd5"
        self.decisions = decisions
        HO._write_jsonl(self.fields / "wd3" / "DECISIONS.jsonl", decisions)
        refusal(self.fields / "wd3" / "write" / "2026-10-04" / "s001" / "SKIPPED.jsonl", *sites)
        for lane in ("wd1", "wd4"):
            (self.fields / lane / "write").mkdir(parents=True)
        R.write_run(self.run, R.RECHECK)
        self.history = {(d["site_id"], d["field"]): d for d in decisions}

    def lines(self, *rows: dict[str, Any]) -> None:
        HO._write_jsonl(self.run / C.CLASSIFIED_FILE, rows)

    def carry(self, check: Any = agrees) -> dict[str, Any]:
        return CA.carry_points(
            self.run,
            history=self.history,
            fields_dir=self.fields,
            waves=[self.fields / lane / "write" for lane in CA.WAVE_LANES],
            country_check=check,
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    made = World(tmp_path, [decision(COAST)], COAST)
    made.lines(line(COAST))
    return made


class TestWhatIsCarried:
    def test_a_counted_replace_the_guard_refused_is_carried_with_its_origin(
        self, world: World
    ) -> None:
        meta = world.carry()
        assert meta["carried"] == 1 and meta["sites"] == [COAST] and meta["not_carried"] == {}
        [row] = CA.read_carried(world.run)
        assert row["via"] == "carried" and row["decision"] == "replace"
        assert row["value"] == "35.156834, 32.788315" and row["quotes"][0]["outcome"] == "found"
        assert row["origin"]["via"] == "counted" and row["origin"]["run"].endswith("fields/wd3")
        assert CA.carried_cells(world.run) == {(COAST, "coordinates")}

    def test_a_decision_a_minimax_model_made_is_asked_again(self, tmp_path: Path) -> None:
        world = World(tmp_path, [decision(COAST, model=MINIMAX)], COAST)
        world.lines(line(COAST))
        meta = world.carry()
        assert meta["carried"] == 0 and "MiniMax" in meta["not_carried"][COAST]
        assert CA.read_carried(world.run) == []

    @pytest.mark.parametrize(
        ("over", "said"),
        [
            ({"decision": "unresolved", "value": None}, "unresolved, not a replace"),
            ({"decision": "keep"}, "keep, not a replace"),
            ({"via": "exhausted"}, "came exhausted"),
            ({"stored": "1.0, 2.0"}, "was made about 1.0, 2.0"),
        ],
    )
    def test_only_a_counted_replace_about_the_stored_point_is_carried(
        self, tmp_path: Path, over: dict[str, Any], said: str
    ) -> None:
        world = World(tmp_path, [decision(COAST, **over)], COAST)
        world.lines(line(COAST))
        assert said in world.carry()["not_carried"][COAST]

    def test_a_refused_point_nobody_decided_since_is_asked(self, world: World) -> None:
        world.history.clear()
        assert world.carry()["not_carried"][COAST] == "no earlier decision"

    def test_a_point_the_guard_still_refuses_is_asked_not_carried(self, world: World) -> None:
        meta = world.carry(refuses)
        assert meta["carried"] == 0
        assert "Bosnia and Herzegovina" in meta["not_carried"][COAST]
        assert CA.carried_cells(world.run) == frozenset()

    def test_a_refused_point_the_run_does_not_ask_is_no_business_of_the_run(
        self, tmp_path: Path
    ) -> None:
        world = World(tmp_path, [decision(COAST), decision(INLAND)], COAST, INLAND)
        world.lines(line(COAST), line(INLAND, asked=["period_start"]))
        meta = world.carry()
        assert meta["sites"] == [COAST] and meta["refused_outside_this_run"] == [INLAND]

    def test_a_decision_that_was_not_refused_by_the_guard_is_not_carried(
        self, tmp_path: Path
    ) -> None:
        """Only the points the plans refused as `country-changes` - a replace that failed for
        another reason (a journal break, a start after the end) was not this lane's to carry."""
        world = World(tmp_path, [decision(COAST), decision(INLAND)], COAST)
        world.lines(line(COAST), line(INLAND))
        assert world.carry()["sites"] == [COAST]

    def test_another_refusal_of_the_plan_is_no_country_refusal(self, tmp_path: Path) -> None:
        world = World(tmp_path, [decision(COAST)])
        refusal(world.fields / "wd4" / "write" / "w" / "s001" / "SKIPPED.jsonl", COAST,
                reason="geom-not-point")  # fmt: skip
        refusal(world.fields / "wd4" / "write" / "w" / "s002" / "SKIPPED.jsonl", COAST,
                column="period_start")  # fmt: skip
        world.lines(line(COAST))
        assert world.carry()["carried"] == 0

    def test_the_latest_run_that_holds_the_decision_is_its_origin(self, tmp_path: Path) -> None:
        later = decision(COAST, answered_by="wd4-r0-b0001", round=0)
        world = World(tmp_path, [decision(COAST)], COAST)
        HO._write_jsonl(world.fields / "wd4" / "DECISIONS.jsonl", [later])
        world.history[(COAST, "coordinates")] = later
        world.lines(line(COAST))
        world.carry()
        assert CA.read_carried(world.run)[0]["origin"]["run"].endswith("fields/wd4")

    def test_a_decision_no_run_holds_has_no_origin_and_no_pages(self, tmp_path: Path) -> None:
        world = World(tmp_path, [decision(COAST)], COAST)
        world.history[(COAST, "coordinates")] = decision(COAST, answered_by="nobody")
        world.lines(line(COAST))
        with pytest.raises(CA.CarryError, match="no run under"):
            world.carry()
        assert not (world.run / CA.CARRIED_FILE).exists()


class TestWhenItRuns:
    def test_only_a_wd5_run_carries(self, tmp_path: Path) -> None:
        world = World(tmp_path, [decision(COAST)], COAST)
        (world.run / R.RUN_FILE).unlink()
        R.write_run(world.run, R.ONE_FAMILY_PERIOD)
        world.lines(line(COAST))
        with pytest.raises(CA.CarryError, match="not a wd5 run"):
            world.carry()

    def test_a_run_that_was_asked_cannot_carry(self, world: World) -> None:
        (world.run / "ROUNDS.jsonl").write_text("{}\n", encoding="utf-8")
        with pytest.raises(CA.CarryError, match="carry before the export"):
            world.carry()

    def test_a_run_carries_once(self, world: World) -> None:
        world.carry()
        with pytest.raises(CA.CarryError, match="carries once"):
            world.carry()

    def test_a_run_without_a_classification_has_nothing_to_carry_into(self, tmp_path: Path) -> None:
        world = World(tmp_path, [decision(COAST)], COAST)
        with pytest.raises(CA.CarryError, match="build the population first"):
            world.carry()

    def test_a_lane_whose_waves_are_missing_is_refused_not_skipped(self, world: World) -> None:
        (world.fields / "wd4" / "write").rmdir()
        with pytest.raises(CA.CarryError, match="is not there"):
            world.carry()


class TestReadingWhatWasCarried:
    def test_a_run_that_carried_nothing_reads_empty(self, tmp_path: Path) -> None:
        assert CA.read_carried(tmp_path) == []
        assert CA.carried_cells(tmp_path) == frozenset()

    def test_an_edited_file_is_not_the_file_that_was_pinned(self, world: World) -> None:
        world.carry()
        path = world.run / CA.CARRIED_FILE
        path.write_text(path.read_text(encoding="utf-8").replace("35.156834", "1.0"),
                        encoding="utf-8")  # fmt: skip
        with pytest.raises(CA.CarryError, match="was edited"):
            CA.read_carried(world.run)

    def test_the_file_and_its_pin_come_together(self, world: World) -> None:
        world.carry()
        (world.run / CA.CARRIED_META).unlink()
        with pytest.raises(CA.CarryError, match="come together"):
            CA.read_carried(world.run)

    def test_the_pin_ignores_the_line_ending(self, world: World) -> None:
        world.carry()
        path = world.run / CA.CARRIED_FILE
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        assert len(CA.read_carried(world.run)) == 1
