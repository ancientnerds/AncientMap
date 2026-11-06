"""Owner decision D99 (2026-11-06): the undated shown sites, asked by a Claude researcher.

The lane is a wd5 run (`population.py build --stage wd5 --sites FILE --d99`); these tests pin what
D99 adds to it: the reason the question names, the run's record, the seeded draw of the pilot and
the source printer the agent reads first. Offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fields import d99 as D99  # noqa: E402  (sys.path set by the imports above)

from tests.remediation import test_fields_wd3 as TW
from tests.remediation import test_fields_wd5_reask as TR
from tests.remediation.test_fields_wd5 import SITE_ID, made_of, made_row
from tests.remediation.test_fields_wd5_reask import HO, POP, R


class TestTheQuestion:
    def test_a_d99_site_is_asked_under_its_own_reason(self) -> None:
        opened, skipped = POP.reader_gap_fields(
            TW.line_of(), TW.stored_row(period_start=None), [], {},
            listed="D99 pilot, stratum peru", detect=False, listed_why=POP.WHY_D99,
        )  # fmt: skip
        assert skipped is None
        cell = opened["period_start"]
        assert cell["why"] == "d99-undated" and cell["reader_gap"] == "d99"
        assert "owner decision D99" in cell["made"] and "stratum peru" in cell["made"]
        lines = HO._open_lines({**TW.line_of(), "open": opened}, "period_start")
        assert lines[0].startswith("Open because: the start is empty (Undated). Owner decision D99")
        assert "d99.py sources --label" in lines[0]

    def test_the_question_names_the_extractors_mistakes(self) -> None:
        text = HO.OPEN_TEXT[POP.WHY_D99]
        for mistake in ("AD 43", "Wari Willka", "hedged pair", "collective entity", "upper bound",
                        "no dating stated", "discovered, excavated"):  # fmt: skip
            assert mistake in text

    def test_a_sourced_site_is_still_refused(self) -> None:
        sourced = made_of(made_row("period_start", None, confidence="two_source"))
        assert POP.reader_gap_fields(
            TW.line_of(), TW.stored_row(period_start=None), [], sourced,
            listed="r", detect=False, listed_why=POP.WHY_D99,
        ) == ({}, "sourced")  # fmt: skip

    def test_an_unknown_reason_is_refused(self) -> None:
        with pytest.raises(POP.PopulationError, match="is asked as"):
            POP.reader_gap_fields(TW.line_of(), TW.stored_row(period_start=None), [], {},
                                  listed="r", detect=False, listed_why="empty")  # fmt: skip


class TestTheRun:
    fixtures = TR.TestTheRun()

    def reask(self, **kw: object) -> POP.Reask:
        base: dict[str, object] = {"answers": {}, "detect": False, "listed": {SITE_ID: "D99 pilot"},
                                   "already": frozenset(), "why": POP.WHY_D99}  # fmt: skip
        return POP.Reask(**{**base, **kw})  # type: ignore[arg-type]

    def test_the_run_asks_the_listed_site_and_records_d99(self, tmp_path: Path) -> None:
        root, out = self.fixtures.prepare(tmp_path)
        counts = self.fixtures.build(root, out, self.reask())
        line = json.loads((out / "CLASSIFIED.jsonl").read_text(encoding="utf-8"))
        assert line["asked"] == ["period_start"]
        assert line["open"]["period_start"]["why"] == "d99-undated"
        assert counts["reader_gap"]["asked"] == {"d99": 1}
        run = json.loads((out / R.RUN_FILE).read_text(encoding="utf-8"))
        assert run["reask"]["why"] == "d99-undated" and R.read_rule(out) is R.RECHECK

    def test_a_d99_run_neither_detects_nor_skips(self, tmp_path: Path) -> None:
        root, out = self.fixtures.prepare(tmp_path)
        with pytest.raises(POP.PopulationError, match="asks its listed sites only"):
            self.fixtures.build(root, out, self.reask(detect=True))
        with pytest.raises(POP.PopulationError, match="asks its listed sites only"):
            self.fixtures.build(root, out, self.reask(already=frozenset({"x"})))
        assert not (out / R.RUN_FILE).exists()

    def test_the_main_refuses_d99_without_its_flags(self, tmp_path: Path) -> None:
        base = ["--out", str(tmp_path), "build", "--root", str(tmp_path), "--d99"]
        for extra in (["--stage", "wd5"], ["--stage", "wd3", "--sites", "x"],
                      ["--stage", "wd5", "--sites", "x", "--reask-cleared"]):  # fmt: skip
            with pytest.raises(SystemExit):
                POP.main(base + extra)


class TestTheDraw:
    def sites(self) -> tuple[list[str], dict[str, str | None], frozenset[str]]:
        countries: dict[str, str | None] = {}
        for i in range(12):
            countries[f"pe{i:02d}"] = "Peru"
            countries[f"en{i:02d}"] = "England"
            countries[f"gr{i:02d}"] = "Greece" if i % 2 else "Türkiye"
            countries[f"ot{i:02d}"] = "Spain"
            countries[f"cf{i:02d}"] = "Peru"
        conflicts = frozenset(f"cf{i:02d}" for i in range(12))
        return sorted(countries), countries, conflicts

    def test_the_draw_is_stratified_seeded_and_disjoint(self) -> None:
        undated, countries, conflicts = self.sites()
        rows = D99.draw(undated, countries, conflicts, 7)
        assert rows == D99.draw(list(reversed(undated)), countries, conflicts, 7)
        assert len(rows) == 50 and len({r["site_id"] for r in rows}) == 50
        by: dict[str, list[str]] = {}
        for r in rows:
            by.setdefault(r["reason"].split("stratum ")[1].split(":")[0], []).append(r["site_id"])
        assert {k: len(v) for k, v in by.items()} == {s: 10 for s, _ in D99.STRATA}
        assert all(s.startswith("cf") for s in by["conflict"])  # a conflict in Peru is a conflict
        assert all(s.startswith("pe") for s in by["peru"])
        assert D99.draw(undated, countries, conflicts, 8) != rows

    def test_a_small_stratum_and_a_site_without_a_row_are_refused(self) -> None:
        undated, countries, conflicts = self.sites()
        few = [s for s in undated if not s.startswith("pe") or s < "pe02"]
        with pytest.raises(D99.D99Error, match="stratum peru holds 2"):
            D99.draw(few, countries, conflicts, 7)
        with pytest.raises(D99.D99Error, match="no harvest row"):
            D99.draw([*undated, "zz"], countries, conflicts, 7)

    def test_conflicts_are_the_rejected_period_cells(self) -> None:
        rows = [{"site_id": "a", "field": "period_start", "state": "reject"},
                {"site_id": "b", "field": "period_start", "state": "unclear"},
                {"site_id": "c", "field": "coordinates", "state": "reject"}]  # fmt: skip
        assert D99.conflict_sites(rows) == frozenset({"a"})


class TestTheSources:
    def test_wikidata_leads_name_the_dates_and_the_period_labels(self) -> None:
        when = {"time": "-0500-00-00T00:00:00Z", "precision": 7}
        entity = {"claims": {
            "P571": [{"mainsnak": {"datavalue": {"value": when}}}],
            "P2348": [{"mainsnak": {"datavalue": {"value": {"id": "Q11764"}}}}],
            "P793": [{"mainsnak": {"datavalue": {"value": {"id": "Q385378"}}},
                      "qualifiers": {"P585": [{"datavalue": {"value": {
                          "time": "+0100-00-00T00:00:00Z"}}}]}}],
        }}  # fmt: skip
        lines = D99.wikidata_leads(entity, {"Q11764": {"label": "Bronze Age"}})
        assert lines == [
            "  - P571: -0500-00-00T00:00:00Z (precision 7)",
            "  - P2348: Q11764 (Bronze Age)",
            "  - P793: Q385378 [P585 +0100-00-00T00:00:00Z]",
        ]

    def test_an_article_url_is_the_live_address(self) -> None:
        assert D99.article_url("hr", "Sisak (grad)") == "https://hr.wikipedia.org/wiki/Sisak_(grad)"


class TestTheBrief:
    def test_a_d99_run_is_told_its_start_is_empty_and_not_the_recheck_warning(
        self, tmp_path: Path
    ) -> None:
        run = tmp_path / "run"
        run.mkdir()
        (run / R.RUN_FILE).write_text(
            json.dumps({"reask": {"why": "d99-undated"}}), encoding="utf-8"
        )
        assert HO.is_d99_run(run)
        (run / R.RUN_FILE).write_text(json.dumps({"reask": {"detect": True}}), encoding="utf-8")
        assert not HO.is_d99_run(run)
        recheck = HO.BRIEF_PARTS[R.RECHECK.name]["evidence"]
        assert HO.D99_REPLACED_EVIDENCE in recheck  # the swap has its text to replace
        swapped = HO._swap(recheck, HO.D99_REPLACED_EVIDENCE, HO.D99_EVIDENCE)
        assert "NEVER independent confirmation" not in swapped
        assert "d99.py sources" in swapped and "throttle" in swapped
