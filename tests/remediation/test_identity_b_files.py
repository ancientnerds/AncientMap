"""The files and reads the identity writes share: plan files, waves, the live-cell check, the reader.

DB-less: the reader's session is captured instead of sent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from identity import common, plan_files, verify, waves  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import identity_lanes as IL  # noqa: E402
from mechanical import plan as MP  # noqa: E402

SITE = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
OTHER = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"


def verdicts(old: str | None = None, new: str = "Tarxien") -> list[MP.Verdict]:
    return [
        MP.Verdict(
            site_id=SITE, site_name="Tarxien Temples", ok=True, old_value=old, new_value=new,
            rule="d23-spoken-name", reason="", note="n", phase3=False, finding_test_id="D23/spoken-name",
            evidence=({"source": "rule", "url": "names", "quote": "q"},), premise="Tarxien Temples",
            column="spoken_name",
        )
    ]  # fmt: skip


def plan(changes: list[MP.Verdict]) -> MP.Plan:
    return MP.Plan(
        tuple(changes),
        (),
        built_at="t",
        counters={"sites": len(changes)},
        lane=IL.spoken_lane("2026-10-12"),
    )


class TestThePlanFiles:
    def test_a_plan_with_cells_writes_the_four_files(self, tmp_path: Path) -> None:
        wrote = plan_files.write_cell_plan(
            plan(verdicts()),
            [{"site_id": OTHER, "name": "x", "reason": "r", "note": "n"}],
            tmp_path,
            "# md\n",
        )
        assert wrote is True
        assert {p.name for p in tmp_path.iterdir()} == {
            "PLAN.jsonl",
            "SKIPPED.jsonl",
            "PLAN.md",
            "ROLLBACK.sql",
        }
        assert json.loads((tmp_path / "SKIPPED.jsonl").read_text("utf-8"))["site_id"] == OTHER
        assert (tmp_path / "ROLLBACK.sql").read_text("utf-8").startswith("-- plan sha256 ")

    def test_a_plan_that_writes_nothing_removes_an_earlier_unemitted_plan(
        self, tmp_path: Path
    ) -> None:
        plan_files.write_cell_plan(plan(verdicts()), [], tmp_path, "a")
        assert (
            plan_files.write_cell_plan(
                plan([]),
                [{"site_id": SITE, "name": "x", "reason": "gone", "note": "n"}],
                tmp_path,
                "b",
            )
            is False
        )
        assert {p.name for p in tmp_path.iterdir()} == {"SKIPPED.jsonl", "PLAN.md"}

    def test_a_plan_whose_statement_was_emitted_is_never_planned_again(
        self, tmp_path: Path
    ) -> None:
        plan_files.write_cell_plan(plan(verdicts()), [], tmp_path, "a")
        (tmp_path / "APPLY.sql").write_text("-- emitted", encoding="utf-8")
        with pytest.raises(MP.PlanError, match="is not planned again"):
            plan_files.write_cell_plan(plan(verdicts(new="Other")), [], tmp_path, "b")
        assert (tmp_path / "PLAN.jsonl").read_text("utf-8").count("Tarxien") >= 1

    def test_the_header_and_the_skips_read_well(self) -> None:
        mech = plan(verdicts())
        head = "\n".join(plan_files.header_lines(mech, "D23 spoken name", "identity/"))
        assert "# D23 spoken name (spoken-2026-10-12) - planned, not applied" in head
        assert (
            "journal test id `D23/spoken-name`, premise `u.name`" in head and '"sites": 1' in head
        )
        assert plan_files.skipped_lines([]) == []
        assert (
            plan_files.skipped_lines([{"site_id": "s", "name": "n", "reason": "r", "note": "x"}])[
                -1
            ]
            == "* `s` n: r - x"
        )


class TestTheWaves:
    def test_a_wave_is_selected_once_and_a_site_is_in_one_wave_only(self, tmp_path: Path) -> None:
        first = waves.select_wave(tmp_path, "w1", {"b", "a", "c"}, limit=2, built_at="t")
        assert first["sites"] == ["a", "b"] and waves.planned_sites(tmp_path) == {"a", "b"}
        second = waves.select_wave(tmp_path, "w2", ["a", "b", "c"], limit=100, built_at="t")
        assert second["sites"] == ["c"]
        assert [w["wave"] for w in waves.all_waves(tmp_path)] == ["w1", "w2"]
        with pytest.raises(waves.WaveError, match="selected once"):
            waves.select_wave(tmp_path, "w1", {"d"}, limit=1, built_at="t")
        with pytest.raises(waves.WaveError, match="no site is left"):
            waves.select_wave(tmp_path, "w3", {"a", "b", "c"}, limit=1, built_at="t")

    @pytest.mark.parametrize("limit", [0, -1, 101])
    def test_a_wave_holds_one_to_a_hundred_sites(self, tmp_path: Path, limit: int) -> None:
        with pytest.raises(waves.WaveError, match="1..100"):
            waves.select_wave(tmp_path, "w", {"a"}, limit=limit, built_at="t")

    def test_a_wave_that_was_never_selected_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(waves.WaveError, match="select the wave first"):
            waves.load_wave(tmp_path, "w")


class TestTheLiveCellCheck:
    cells = [
        {"site_id": SITE, "column": "scope_status", "old_value": None, "new_value": "retired"},
        {"site_id": SITE, "column": "scope_reason", "old_value": None, "new_value": "E3: x"},
    ]

    def test_the_read_asks_only_the_planned_columns_of_the_planned_sites(self) -> None:
        sql = verify.live_cells_sql([SITE, SITE], ["scope_status", "scope_reason", "scope_status"])
        assert sql.count("::uuid") == 1 and "u.scope_status::text AS scope_status" in sql
        assert sql.count("AS scope_status") == 1 and sql.lstrip().upper().startswith("SELECT")
        with pytest.raises(common.IdentityError, match="not a column name"):
            verify.live_cells_sql([SITE], ["name; DROP TABLE x"])

    def test_every_cell_must_hold_its_new_value_and_a_gone_row_is_a_deviation(self) -> None:
        live = {SITE: {"scope_status": "retired", "scope_reason": "E3: x"}}
        assert verify.cell_deviations(self.cells, live) == []
        wrong = {SITE: {"scope_status": "pending", "scope_reason": "E3: x"}}
        (dev,) = verify.cell_deviations(self.cells, wrong)
        assert "scope_status: holds 'pending', the plan wrote 'retired'" in dev
        assert verify.cell_deviations(self.cells, {}) == [f"{SITE}: the row is gone"] * 2

    def test_a_wave_is_accepted_only_with_cells_and_no_deviation(self) -> None:
        assert verify.wave_report([], 2)["accepted"] is True
        assert verify.wave_report([], 0)["accepted"] is False
        assert verify.wave_report(["x"] * 30, 4)["detail"] == ["x"] * 20
        assert verify.wave_report(["x"], 4)["accepted"] is False

    def test_the_planned_cells_are_read_from_a_plan_file(self, tmp_path: Path) -> None:
        MP.write_plan_jsonl(plan(verdicts()), tmp_path / "PLAN.jsonl")
        assert verify.planned_cells(tmp_path / "PLAN.jsonl") == [
            {"site_id": SITE, "column": "spoken_name", "old_value": None, "new_value": "Tarxien"}
        ]


class TestTheReadOnlyReader:
    def sent(self, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> list[str]:
        sql_sent: list[str] = []

        def fake(sql: str, *, rows: bool = False, **_: Any) -> subprocess.CompletedProcess[str]:
            sql_sent.append(sql)
            return subprocess.CompletedProcess([], 0, '{"a": 1}\n', "")

        monkeypatch.setattr(A, "run_psql", fake)
        assert MP.psql_json_reader(**kw)("SELECT 1 AS a") == [{"a": 1}]
        return sql_sent

    def test_a_read_only_reader_opens_the_session_read_only_and_quiet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (sql,) = self.sent(monkeypatch, read_only=True)
        assert sql.startswith("\\set QUIET on\nSET default_transaction_read_only = on;\n")
        assert sql.endswith("SELECT row_to_json(t) FROM (SELECT 1 AS a) t")

    def test_the_default_reader_sends_what_it_always_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (sql,) = self.sent(monkeypatch)
        assert sql == "SELECT row_to_json(t) FROM (SELECT 1 AS a) t"
