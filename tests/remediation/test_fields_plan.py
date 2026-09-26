"""WD1's write plan (`scripts/remediation/fields/plan.py`): decisions into journalled steps.

`site_cells` is pure; the wave, the step and the acceptance run on files in a temporary repository
root and a fake production reader. What is pinned: a replaced point moves lat, lon and geom together
and never across a border; a cleared start clears its label; a label follows its start everywhere;
a decision about a value the row no longer holds is refused; a step is planned only after the one
before it is accepted, and accepted only with 0 deviations.
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

from fields import handoff as HO  # noqa: E402
from fields import plan as FP  # noqa: E402
from mechanical import apply as MA  # noqa: E402
from mechanical.plan import JournalLink, PlanError  # noqa: E402

SITE = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
OTHER = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
AGREES = lambda country, lat, lon: {"agrees": True, "polygon": [country]}  # noqa: E731
ELSEWHERE = lambda country, lat, lon: {"agrees": False, "polygon": ["Turkey"]}  # noqa: E731
QUOTES = [{"source": "https://a.example", "quote": "q", "outcome": "found", "detail": ""}]


def live(**over: Any) -> dict[str, Any]:
    base = {
        "site_id": SITE,
        "name": "Corycus",
        "source_id": "ancient_nerds",
        "scope_status": None,
        "country": "Cyprus",
        "lat_text": "35.1",
        "lon_text": "33.4",
        "geom_text": "0101000020E6100000",
        "geom_is_point": True,
        "period_start": -700,
        "period_end": None,
        "period_name": "1500 - 500 BC",
        "site_type": "City",
        "source_url": "https://en.wikipedia.org/wiki/Corycus",
    }
    base.update(over)
    return base


def decision(field: str, verdict: str, value: Any, stored: Any) -> dict[str, Any]:
    return {
        "site_id": SITE,
        "field": field,
        "decision": verdict,
        "value": value,
        "stored": stored,
        "status": "CONFLICT",
        "via": "counted",
        "round": 0,
        "answered_by": "wd1-r0-b0001",
        "quotes": QUOTES if verdict in ("keep", "replace") else [],
        "reasoning": "sources",
    }


def cells(decisions: list[dict[str, Any]], row: dict[str, Any] | None = None,
          journals: dict[str, Any] | None = None, **kw: Any) -> list[Any]:  # fmt: skip
    return FP.site_cells(
        row or live(),
        {},
        {d["field"]: d for d in decisions},
        journals or {},
        country_check=kw.pop("country_check", AGREES),
        **kw,
    )


def written(verdicts: list[Any]) -> dict[str, tuple[Any, Any]]:
    return {v.column: (v.old_value, v.new_value) for v in verdicts if v.ok}


class TestSiteCells:
    def test_a_replaced_point_moves_lat_lon_and_geom_together(self) -> None:
        out = cells([decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")])
        assert written(out) == {
            "lat": ("35.1", "36.5"),
            "lon": ("33.4", "34.1"),
            "geom": ("0101000020E6100000", "SRID=4326;POINT(34.1 36.5)"),
        }

    def test_a_point_that_crosses_a_border_is_held(self) -> None:
        out = cells([decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")],
                    country_check=ELSEWHERE)  # fmt: skip
        assert written(out) == {} and out[0].reason == "country-changes"

    def test_an_unresolved_point_is_held_and_a_kept_one_untouched(self) -> None:
        held = cells([decision("coordinates", "unresolved", None, "35.1, 33.4")])
        assert [v.reason for v in held] == ["coordinates-unresolved"]
        assert cells([decision("coordinates", "keep", "35.1, 33.4", "35.1, 33.4")]) == []

    def test_a_geom_that_is_not_the_point_is_refused_and_a_null_one_filled(self) -> None:
        out = cells([decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")],
                    row=live(geom_is_point=False))  # fmt: skip
        assert out[0].reason == "geom-not-point"
        filled = cells([decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")],
                       row=live(geom_text=None, geom_is_point=False))  # fmt: skip
        assert written(filled)["geom"] == (None, "SRID=4326;POINT(34.1 36.5)")

    def test_a_replaced_start_takes_its_label_along(self) -> None:
        out = cells([decision("period_start", "replace", "-2500", -700)])
        assert written(out) == {
            "period_start": ("-700", "-2500"),
            "period_name": ("1500 - 500 BC", "3000 - 1500 BC"),
        }

    def test_a_cleared_start_clears_its_label(self) -> None:
        out = cells([decision("period_start", "clear", None, -700)])
        assert written(out) == {
            "period_start": ("-700", None),
            "period_name": ("1500 - 500 BC", None),
        }

    def test_a_label_follows_an_unchanged_start(self) -> None:
        out = cells([], row=live(period_name="1 - 500 AD"))
        assert written(out) == {"period_name": ("1 - 500 AD", "1500 - 500 BC")}

    def test_a_start_after_the_end_is_refused(self) -> None:
        out = cells([decision("period_start", "replace", "100", -700)], row=live(period_end=-100))
        assert out[0].reason == "period-end-precedes-start" and written(out) == {}

    def test_a_zero_end_is_no_end(self) -> None:
        # the codebase reads a site's date as `period_end or period_start` (mechanical/lane.py),
        # so a period_end of 0 is no end and refuses no start
        out = cells([decision("period_start", "replace", "100", -700)], row=live(period_end=0))
        assert written(out)["period_start"] == ("-700", "100") and not [v for v in out if not v.ok]

    def test_a_decision_about_another_value_is_refused(self) -> None:
        out = cells([decision("site_type", "replace", "Temple", "Town")])
        assert out[0].reason == "moved-since-classification"
        moved = cells([decision("coordinates", "replace", "36.5, 34.1", "35.0, 33.4")])
        assert moved[0].reason == "moved-since-classification"

    def test_type_and_url_are_replaced_or_cleared(self) -> None:
        out = cells([
            decision("site_type", "replace", "Temple", "City"),
            decision("source_url", "clear", None, "https://en.wikipedia.org/wiki/Corycus"),
        ])  # fmt: skip
        assert written(out) == {
            "site_type": ("City", "Temple"),
            "source_url": ("https://en.wikipedia.org/wiki/Corycus", None),
        }
        assert {v.rule for v in out} == {"wd1-replace", "wd1-clear"}

    def test_a_field_written_around_the_journal_is_refused(self) -> None:
        journals = {"site_type": (JournalLink(9, "x", "t", "Fort", "Town"),)}
        out = cells([decision("site_type", "replace", "Temple", "City")], journals=journals)
        assert out[0].reason == "journal-disagrees"
        start = {"period_start": (JournalLink(9, "x", "t", "-600", "-650"),)}
        refused = cells([decision("period_start", "replace", "-2500", -700)], journals=start)
        assert [v.reason for v in refused] == ["journal-disagrees", "period-start-journal"]

    def test_a_coordinate_journal_is_read_as_numbers(self) -> None:
        journals = {"lat": (JournalLink(9, "x", "t", "35.0", "35.10"),)}
        out = cells(
            [decision("coordinates", "replace", "36.5, 34.1", "35.1, 33.4")], journals=journals
        )
        assert "lat" in written(out)

    def test_two_implementations_of_the_bucket_must_agree(self) -> None:
        out = cells([decision("period_start", "replace", "-2500", -700)], frontend=lambda y: "?")
        assert out[-1].reason == "implementations-disagree"

    def test_a_retired_site_gets_no_cell(self) -> None:
        out = cells(
            [decision("site_type", "replace", "Temple", "City")], row=live(scope_status="retired")
        )
        assert [v.reason for v in out] == ["not-a-curated-live-site"]


# ------------------------------------------------------------------------------ wave and step
@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository root of our own: the wave and step directories land under it."""
    monkeypatch.setattr(FP, "REPO", tmp_path)
    monkeypatch.setattr(MA, "REPO", tmp_path)
    monkeypatch.setattr(HO, "REPO", tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    line = {
        "site_id": SITE,
        "name": "Corycus",
        "period_name": {"stored": "1500 - 500 BC", "bucket_of_stored_start": "1500 - 500 BC"},
        "asked": ["site_type"],
    }
    quiet = {**line, "site_id": OTHER, "asked": []}
    (run / "CLASSIFIED.jsonl").write_text(
        json.dumps(line) + "\n" + json.dumps(quiet) + "\n", encoding="utf-8"
    )
    (run / HO.DECISIONS_FILE).write_text(
        json.dumps(decision("site_type", "replace", "Temple", "City")) + "\n", encoding="utf-8"
    )
    HO._write_json(run / HO.REASK_FILE, {"after_round": 0, "fields": {}})
    return tmp_path


def reader(sql: str) -> list[dict[str, Any]]:
    if "remediation_change_log" in sql:
        return []
    return [live()]


def step(wave: str = "2026-09-27", number: int = 1) -> dict[str, Any]:
    return FP.build_step(
        wave,
        number,
        reader=reader,
        country_check=AGREES,
        frontend=lambda y: FP.categorize_period(y),
    )


class TestWaveAndStep:
    def test_the_wave_takes_the_sites_with_a_write(self, repo: Path) -> None:
        result = FP.build_wave(repo / "run", "2026-09-27")
        assert result == {"wave": "2026-09-27", "sites": 1, "steps": 1}
        with pytest.raises(PlanError, match="planned once"):
            FP.build_wave(repo / "run", "2026-09-27")

    def test_a_wave_waits_for_every_re_ask(self, repo: Path) -> None:
        HO._write_json(
            repo / "run" / HO.REASK_FILE, {"after_round": 0, "fields": {SITE: ["site_type"]}}
        )
        with pytest.raises(PlanError, match="still wait for a re-ask"):
            FP.build_wave(repo / "run", "2026-09-27")

    def test_a_step_writes_its_plan_and_its_undo(self, repo: Path) -> None:
        FP.build_wave(repo / "run", "2026-09-27")
        result = step()
        assert result["cells"] == 1 and result["cells:site_type"] == 1
        out = FP.step_dir("2026-09-27", 1)
        records = MA.load_records(out / "PLAN.jsonl")
        assert [(r.column, r.old_value, r.new_value) for r in records] == [
            ("site_type", "City", "Temple")
        ]
        assert (out / "ROLLBACK.sql").read_text(encoding="utf-8").startswith("-- plan sha256 ")
        assert "2026-09-27_fields-wd1-s001-rollback" in (out / "ROLLBACK.sql").read_text(
            encoding="utf-8"
        )

    def test_a_step_waits_for_the_one_before_it(self, repo: Path) -> None:
        FP.build_wave(repo / "run", "2026-09-27")
        wave = FP.read_wave("2026-09-27")
        wave["steps"].append([OTHER])
        HO._write_json(FP.wave_dir("2026-09-27") / FP.WAVE_FILE, wave)
        with pytest.raises(PlanError, match="step 1 is not accepted"):
            step(number=2)

    def test_changed_decisions_are_refused(self, repo: Path) -> None:
        FP.build_wave(repo / "run", "2026-09-27")
        (repo / "run" / HO.DECISIONS_FILE).write_text("", encoding="utf-8")
        with pytest.raises(PlanError, match="not the one the wave was built from"):
            step()


class TestTheAcceptance:
    def emitted(self, repo: Path) -> tuple[Any, list[MA.ChangeRecord]]:
        FP.build_wave(repo / "run", "2026-09-27")
        step()
        lane = FP.fields_lane("2026-09-27", 1)
        out = FP.step_dir("2026-09-27", 1)
        records = MA.load_records(out / "PLAN.jsonl")
        MA.emit(records, out, lane, plan_path=out / "PLAN.jsonl")
        return lane, records

    def test_a_clean_read_back_is_accepted_once(self, repo: Path) -> None:
        self.emitted(repo)
        counts = [
            ["planned cells holding their new value", "1"],
            ["journal rows for the stamp", "1"],
            ["journal rows matching a planned cell exactly", "1"],
            ["journal rows of another stamp on a planned cell since", "0"],
            ["planned sites breaking: x", "0"],
        ]
        result = FP.accept("2026-09-27", 1, read_rows=lambda sql: counts)
        assert result["deviations"] == 0
        with pytest.raises(PlanError, match="accepted once"):
            FP.accept("2026-09-27", 1, read_rows=lambda sql: counts)

    def test_any_deviation_refuses_the_step(self, repo: Path) -> None:
        self.emitted(repo)
        counts = [
            ["planned cells holding their new value", "0"],
            ["journal rows for the stamp", "1"],
            ["journal rows matching a planned cell exactly", "1"],
            ["journal rows of another stamp on a planned cell since", "1"],
        ]
        with pytest.raises(PlanError, match="2 deviation"):
            FP.accept("2026-09-27", 1, read_rows=lambda sql: counts)
        assert not (FP.step_dir("2026-09-27", 1) / FP.ACCEPTED_FILE).exists()

    def test_the_acceptance_reads_every_cell_typed_and_every_invariant(self, repo: Path) -> None:
        lane, records = self.emitted(repo)
        sql = FP.accept_sql(lane, records)
        assert (
            "WHEN 'site_type' THEN u.site_type IS NOT DISTINCT FROM p.new_value::character varying"
            in sql
        )
        assert sql.count("planned sites breaking: ") == 2
        assert "FROM planned q WHERE q.site_id = p.site_id" in sql
