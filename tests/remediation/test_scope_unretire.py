"""The label rule's SQL and the scope lane's un-retire (owner decisions D58 of 2026-10-24, D50 of 2026-10-19).

`mechanical.lane` renders the label rule (`pipeline/normalizers/dates.py`) into SQL; evaluated in
SQLite over every kind of row the rule distinguishes it must answer exactly what Python answers.
`mechanical/scope_unretire.py` plans the un-retire as a pure function of a read-only export, and
`identity_lanes.scope_unretire_lane` writes it with an invariant inside the transaction - both are
exercised here offline: the invariant's predicate runs in SQLite over the rows it must refuse and
the rows it must let through. Nothing here opens a socket or touches a database.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mechanical import apply as A  # noqa: E402
from mechanical import identity_lanes as IL  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical import scope_unretire as U  # noqa: E402
from phase4 import wc4  # noqa: E402

from pipeline.normalizers import dates as D  # noqa: E402

WAVE = "2026-10-24"
PRAMBANAN = "21bd525e-fe10-40dd-96be-32d3c8d36d26"
CHROBRY = "a26993c6-b562-4c28-a584-8de2c9312dad"
NIHA = "a451f6be-a506-41f6-9bf7-85d8c7c7ac8e"
OSAKA = "a3fdb1d8-083b-4e8f-a170-5b98638d5b53"
KHUSHUU = "71d8e2bc-7406-4c4a-b68d-2ff1b71800e8"
GROSS_RADEN = "9bbea428-26aa-4cb9-a9c8-d3f8f059972d"
OTHER_MUSEUM = "b0000000-0000-4000-8000-00000000000b"
NORSE = "c0000000-0000-4000-8000-00000000000c"
DUPLICATE = "d0000000-0000-4000-8000-00000000000d"
YONAGUNI = "01296632-a2a1-4610-a4a9-d0c3be77b788"
RICHAT = "84b456ff-0b44-4d75-92a4-5cbe22026b95"
SOURCE_A = {
    "url": "https://example.org/geology",
    "title": "Geology",
    "quote": "A natural formation.",
}
SOURCE_B = {
    "url": "https://example.net/claim",
    "title": "Claim",
    "quote": "Kimura claims a monument.",
}


# ------------------------------------------------------------------------------ the label SQL
def _rows() -> list[tuple[str | None, float | None, float]]:
    rows: list[tuple[str | None, float | None, float]] = [
        ("Poland", 51.56, 15.52),
        ("England", 54.53, -1.07),
        ("Türkiye", 37.18, 40.95),
        ("TR", 39.0, 35.0),
        ("Cyprus", 35.1, 33.4),
        ("Baltic Sea", 61.38, 18.45),
        ("Bavaria, Germany", 48.1, 11.6),
        ("Iceland", 64.1, -21.9),
        ("Russia", 58.72, 57.64),
        ("Russia", 43.07, 132.68),
        ("Russia", 56.8, 60.0),
        ("Russia", 66.0, -172.0),
        ("RU", 52.67, 88.53),
        ("Russia", None, 40.0),
        ("Spain", 28.1, -15.4),
        ("Spain", 40.4, -3.7),
        ("France", -21.12, 55.53),
        ("France", -16.84, -151.36),
        ("France", 4.9, -52.3),
        ("France", 48.85, 2.35),
        ("Cambodia", 13.45, 103.86),
        ("Indonesia", -7.75, 110.49),
        ("Lebanon", 33.58, 35.61),
        ("Syria", 33.25, 35.71),
        ("Greenland", 61.16, -45.43),
        ("Egypt", 28.56, 33.98),
        ("Iraq", 33.09, 44.58),
        ("Australia", -33.75, 143.08),
        ("Mexico", 20.0, -100.0),
        (None, 51.0, 15.0),
        (None, 20.0, -100.0),
        ("", 13.45, 103.86),
        ("Korea, South", 37.57, 126.98),
    ]
    for state, boxes in D.NON_EUROPEAN_PARTS.items():
        for lon_min, lat_min, lon_max, lat_max in boxes:
            rows += [(state, lat_min, lon_min), (state, lat_max, lon_max)]
            rows += [(state, lat_min - 0.5, lon_min + 0.1), (state, lat_max, lon_max + 0.5)]
    return rows


def _sites_db(rows: list[dict[str, Any]]) -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute(
        "CREATE TABLE unified_sites (id TEXT, source_id TEXT, name TEXT, site_type TEXT, "
        "country TEXT, lat REAL, lon REAL, period_start INT, period_end INT, scope_status TEXT, "
        "scope_reason TEXT, description TEXT)"
    )
    db.execute(
        "CREATE TABLE remediation_change_log (id INT, table_name TEXT, column_name TEXT, "
        "row_pk TEXT, new_value TEXT, evidence TEXT)"
    )
    for r in rows:
        db.execute(
            "INSERT INTO unified_sites VALUES (:id, 'ancient_nerds', :name, :site_type, :country, "
            ":lat, :lon, :period_start, :period_end, :scope_status, :scope_reason, :description)",
            {
                "name": "a site",
                "site_type": "Temple complex",
                "period_end": None,
                "scope_status": "in_scope",
                "scope_reason": None,
                "description": "A text.",
                **r,
            },
        )
    return db


class TestTheLabelWindowInSql:
    """The rendered SQL is the Python rule, row for row, in a real SQL engine."""

    def records(self) -> list[dict[str, Any]]:
        out = []
        n = 0
        for country, lat, lon in _rows():
            for year in (499, 500, 501, 975, 1500, 1501, None):
                for end in (None, 0):
                    n += 1
                    out.append(
                        {
                            "id": f"s{n}",
                            "country": country,
                            "lat": lat,
                            "lon": lon,
                            "period_start": year,
                            "period_end": end,
                        }
                    )
        return out

    def test_outside_label_window_is_passes_date_cutoff_negated(self) -> None:
        records = self.records()
        db = _sites_db(records)
        got = dict(db.execute(f"SELECT id, {L.outside_label_window('u.')} FROM unified_sites u"))
        want = {r["id"]: int(not D.passes_date_cutoff(r)) for r in records}
        assert got == want
        by = {(r["country"], r["lat"], r["lon"], r["period_start"]): r["id"] for r in records}
        assert got[by[("Poland", 51.56, 15.52, 975)]] == 1
        assert got[by[("Cambodia", 13.45, 103.86, 975)]] == 0
        assert got[by[("Türkiye", 37.18, 40.95, 975)]] == 1  # SQLite's lower agrees on this one
        assert got[by[("Russia", 43.07, 132.68, 975)]] == 0
        assert got[by[(None, 51.0, 15.0, 975)]] == 1  # no country: the Old World's 500 AD
        assert got[by[(None, 20.0, -100.0, 975)]] == 0  # the Americas need no country

    def test_label_borderline_sql_is_label_borderline(self) -> None:
        records = self.records()
        db = _sites_db(records)
        got = dict(db.execute(f"SELECT id, {L.label_borderline_sql('u.')} FROM unified_sites u"))
        want = {r["id"]: int(D.label_borderline(r)) for r in records}
        assert {k: bool(v) for k, v in got.items()} == {k: bool(v) for k, v in want.items()}
        assert sum(want.values()) > 0

    def test_in_medieval_old_world_sql_is_the_python_rule(self) -> None:
        records = self.records()
        db = _sites_db(records)
        got = dict(
            db.execute(f"SELECT id, {L.in_medieval_old_world_sql('u.')} FROM unified_sites u")
        )
        want = {r["id"]: D.in_medieval_old_world(r["country"], r["lat"], r["lon"]) for r in records}
        assert {k: bool(v) for k, v in got.items()} == want

    def test_the_sql_is_rendered_from_the_lists(self) -> None:
        sql = L.outside_label_window()
        assert f"THEN {D.LABEL_CUTOFF_MEDIEVAL_OLD_WORLD} " in sql
        assert f"ELSE {D.LABEL_CUTOFF_REST_OF_WORLD} END" in sql
        assert f"WHEN country IS NULL THEN {D.LABEL_CUTOFF_MEDIEVAL_OLD_WORLD} " in sql
        assert "'türkiye'" in sql and "'baltic sea'" in sql
        assert L.in_oceania_sql("u.") in L.outside_label_window("u.")
        assert L.outside_e3_window() != sql, "the delivered lanes keep the E3 text"

    def test_the_residual_is_the_label_window(self) -> None:
        assert L.UNDECIDED_OUTSIDE_LABEL_WINDOW.predicate == (
            f"{L.outside_label_window()} AND scope_status IS NULL"
        )


# ------------------------------------------------------------------------------ the lane
def cells(site_id: str, reason: str, *, old_reason: str = "E3: period_start 850 is past") -> list:
    base: dict[str, Any] = {
        "site_id": site_id,
        "site_name": "a site",
        "rule": "d58-label-rule",
        "condition": "x",
        "reason": "scope-unretire: x",
        "evidence": ({"source": "test", "quote": "x"},),
        "premise": "a site | Temple complex | 1 | 2 | Indonesia | 850 | NULL | md5",
    }
    return [
        A.ChangeRecord(**base, old_value="retired", new_value="in_scope", column="scope_status"),
        A.ChangeRecord(**base, old_value=old_reason, new_value=reason, column="scope_reason"),
    ]


class TestTheLane:
    lane = IL.scope_unretire_lane(WAVE)

    def test_its_identity_cells_and_premise(self) -> None:
        assert self.lane.name == f"scope-unretire-{WAVE}"
        assert self.lane.run_stamp == f"{WAVE}_mechanical-scope-unretire"
        assert self.lane.test_id == "D58/scope-unretire"
        assert self.lane.columns == ("scope_status", "scope_reason")
        status = self.lane.cell("scope_status")
        assert status.allowed_new_values == ("in_scope",) and not status.fills_null
        assert not self.lane.cell("scope_reason").fills_null
        assert self.lane.premise_sql.endswith(", md5(coalesce(u.description, '')))")
        assert self.lane.premise_sql.startswith(L.SCOPE_REVIEW_PREMISE_SQL.removesuffix(")"))
        assert self.lane.post_commit_residual is L.UNDECIDED_OUTSIDE_LABEL_WINDOW

    def test_resolve_lane_and_the_readback_reach_it(self) -> None:
        assert L.resolve_lane(f"scope-unretire-{WAVE}") == self.lane
        assert A.readback_for(self.lane) == IL.scope_unretire_readback(self.lane)
        for bad in ("scope-unretire-x", "scope-unretire-2026-10-24-1"):
            with pytest.raises((KeyError, ValueError)):
                L.resolve_lane(bad)
        with pytest.raises(ValueError, match="is not a wave label"):
            IL.scope_unretire_lane("tomorrow")

    def test_the_one_transition_is_a_guarded_un_retirement_and_its_rollback_retires(self) -> None:
        records = cells(PRAMBANAN, IL.D58_REASON_PREFIX + "x")
        A.validate_records(records, lane=self.lane)
        sql = A.render_transaction(records, site_ids={PRAMBANAN}, lane=self.lane)
        assert "guard 3" in sql and self.lane.site_invariants[0].predicate in sql
        assert self.lane.site_invariants[0].predicate == IL.unretire_violation_sql()
        undo = [
            A.ChangeRecord(**{**r.__dict__, "old_value": r.new_value, "new_value": r.old_value})
            for r in records
        ]
        A.validate_records(undo, lane=self.lane, rollback=True)

    def test_it_owns_no_other_status_and_never_fills_a_null(self) -> None:
        bad = cells(PRAMBANAN, "x")
        bad[0] = A.ChangeRecord(**{**bad[0].__dict__, "new_value": "retired", "old_value": None})
        with pytest.raises(MP.PlanError):
            A.validate_records(bad, lane=self.lane)
        pending = cells(PRAMBANAN, "x")
        pending[0] = A.ChangeRecord(**{**pending[0].__dict__, "new_value": "pending"})
        with pytest.raises(MP.PlanError, match="is not a value"):
            A.validate_records(pending, lane=self.lane)

    def test_the_invariant_has_its_probe(self) -> None:
        records = cells(PRAMBANAN, IL.D58_REASON_PREFIX + "x")
        foreign = {"id": "11111111-1111-1111-1111-111111111111", "name": "x", "premise": "p"}
        probes = {c[0] for c in A.probe_cases(records, self.lane, foreign)}
        assert "invariant-scope_reason" in probes and "guard5-premise" in probes

    def test_the_readback_counts_what_the_wave_moves(self) -> None:
        text = IL.scope_unretire_readback(self.lane)
        for metric in (
            "curated rows retired for their date inside the D58 window, not borderline",
            "curated rows retired for their date that are D58 borderline",
            "curated D50 sites shown",
            "curated D50 sites shown without a dispute-enriched description",
            "curated rows outside the D58 label window with no scope decision",
            "journal rows for this run that write a status other than in_scope",
            "curated rows with scope_status retired",
        ):
            assert metric in text, metric


# ------------------------------------------------------------------------------ the invariant
def _evidence(*, decision: str = wc4.EVIDENCE_DECISION_ENRICH, dispute: Any = "brief",
              classes: dict[str, str] | None = None) -> str:  # fmt: skip
    brief = {"site_id": YONAGUNI} if dispute == "brief" else dispute
    return json.dumps(
        {
            "decision": decision,
            wc4.ENRICH_EVIDENCE_KEY: {
                "dispute": brief,
                "classes": classes or {"4": wc4.DISPUTE_A, "5": wc4.DISPUTE_B},
            },
        }
    )


class TestTheInvariantInSql:
    """`unretire_violation_sql` over the written site: TRUE refuses the whole wave."""

    def violators(self, rows: list[dict[str, Any]], journal: list[tuple]) -> set[str]:
        db = _sites_db(rows)
        db.executemany(
            "INSERT INTO remediation_change_log VALUES (?, 'unified_sites', 'description', ?, ?, ?)",
            journal,
        )
        sql = f"SELECT u.id FROM unified_sites u WHERE {IL.unretire_violation_sql()}"
        return {row[0] for row in db.execute(sql)}

    def site(self, sid: str, reason: str, **over: Any) -> dict[str, Any]:
        return {"id": sid, "scope_reason": reason, "country": "Indonesia", "lat": -7.75,
                "lon": 110.49, "period_start": 850, **over}  # fmt: skip

    def test_a_label_un_retirement_inside_the_window_passes_and_every_other_fails(self) -> None:
        d58 = IL.D58_REASON_PREFIX + "rest of world ..."
        rows = [
            self.site(PRAMBANAN, d58),
            self.site(CHROBRY, d58, country="Poland", lat=51.56, lon=15.52, period_start=1000),
            self.site(OSAKA, d58, country="Japan", lat=34.7, lon=135.5, period_start=1583),
            self.site(NIHA, d58, country="Lebanon", lat=33.58, lon=35.61, period_start=975),
            self.site(RICHAT, d58, country="Mauritania", lat=21.1, lon=-11.4, period_start=None),
            self.site(DUPLICATE, "a reason that names no rule"),
            self.site(NORSE, "D58 label rule probe"),
        ]
        assert self.violators(rows, []) == {CHROBRY, OSAKA, NIHA, RICHAT, DUPLICATE, NORSE}

    def test_a_museum_un_retirement_needs_a_museum_outside_the_medieval_old_world(self) -> None:
        museum = IL.D58_MUSEUM_REASON_PREFIX + "its exhibits ..."
        rows = [
            self.site(KHUSHUU, museum, site_type="Museum", country="Mongolia", period_start=2008),
            self.site(
                GROSS_RADEN,
                museum,
                site_type="Museum",
                country="Germany",
                lat=53.7,
                lon=11.9,
                period_start=800,
            ),  # fmt: skip
            self.site(OTHER_MUSEUM, museum, site_type="Temple complex", country="Mongolia"),
            self.site(NORSE, museum, site_type="Museum", country=None),
        ]
        assert self.violators(rows, []) == {GROSS_RADEN, OTHER_MUSEUM, NORSE}

    def test_a_d50_site_passes_only_with_its_dispute_text(self) -> None:
        d50 = IL.D50_REASON_PREFIX + "shown as disputed ..."
        text = "A text with both positions."
        rows = [
            self.site(YONAGUNI, d50, description=text, country="Japan"),
            self.site(RICHAT, d50, description=text, country="Mauritania"),
            self.site(PRAMBANAN, d50, description=text),
        ]
        good = [(1, YONAGUNI, text, _evidence()), (2, PRAMBANAN, text, _evidence())]
        assert self.violators(rows, good) == {RICHAT, PRAMBANAN}, "no text; no D50 site"
        for broken in (
            (1, YONAGUNI, "An older text.", _evidence()),
            (1, YONAGUNI, text, _evidence(decision=wc4.EVIDENCE_DECISION)),
            (1, YONAGUNI, text, _evidence(dispute=None)),
            (1, YONAGUNI, text, _evidence(classes={"4": wc4.DISPUTE_A, "5": wc4.FACT})),
            (1, YONAGUNI, text, _evidence(classes={"4": wc4.DISPUTE_B})),
        ):
            assert YONAGUNI in self.violators(rows, [broken]), broken
        d58_on_d50 = [self.site(YONAGUNI, IL.D58_REASON_PREFIX + "x", country="Japan")]
        assert self.violators(d58_on_d50, []) == {YONAGUNI}

    def test_the_d50_readback_counts_a_shown_site_without_its_text(self) -> None:
        rows = [self.site(YONAGUNI, "x", description="t", country="Japan")]
        db = _sites_db(rows)
        sql = (
            "SELECT count(*) FROM unified_sites u WHERE u.source_id = 'ancient_nerds' AND "
            f"NOT {IL.dispute_enriched_sql('u')}"
        )
        assert db.execute(sql).fetchone() == (1,)
        db.execute(
            "INSERT INTO remediation_change_log VALUES (1, 'unified_sites', 'description', ?, 't', ?)",
            (YONAGUNI, _evidence()),
        )
        assert db.execute(sql).fetchone() == (0,)


# ------------------------------------------------------------------------------ the planner
def site_row(sid: str, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": sid, "name": "Prambanan Temple", "country": "Indonesia", "site_type": "Temple complex",
        "lat": -7.75, "lon": 110.49, "period_start": 850, "period_end": None,
        "scope_status": "retired",
        "scope_reason": "E3: period_start 850 is 350 years past the rest of world cutoff of 500 AD",
        "qids": [], "premise": f"premise-{sid[:8]}",
    }  # fmt: skip
    row.update(over)
    return row


def journal(sid: str, n: int, *, new: str = "retired", stamp: str = "2026-09-23_mechanical-scope-e4",
            old: str | None = None) -> dict[str, Any]:  # fmt: skip
    return {"id": n, "row_pk": sid, "old_value": old, "new_value": new, "run_stamp": stamp}


def brief(sid: str = YONAGUNI, **over: Any) -> dict[str, Any]:
    position = {"claim": "c", "holders": "geologists", "sources": [SOURCE_A]}
    record = {
        "site_id": sid, "name": "Yonaguni Monument", "desc_sha256": "a" * 64, "verdict": "dispute",
        "position_a": position, "position_b": {**position, "holders": "Kimura", "sources": [SOURCE_B]},
        "asserting": [], "note": "n", "researched_by": "field_researcher:ds-0001",
        "adjudicated_by": "adversarial:da-0001",
    }  # fmt: skip
    record.update(over)
    return record


def dispute_row(sid: str = YONAGUNI, n: int = 500, **over: Any) -> dict[str, Any]:
    row = {
        "id": n, "row_pk": sid, "run_stamp": "2026-10-30_wc-enrich-s001",
        "decision": wc4.EVIDENCE_DECISION_ENRICH, "dispute": brief(sid),
        "classes": {"3": wc4.DISPUTE_A, "4": wc4.DISPUTE_B},
    }  # fmt: skip
    row.update(over)
    return row


D50_REASON_NOW = "E3: not an archaeological site (natural_formation): a sandstone formation"


def export(sites: list[dict], rows: list[dict], disputes: list[dict] = ()) -> U.Export:
    return U.Export(tuple(sites), tuple(rows), tuple(disputes), "2026-10-24 08:00:00+00", "sha")


def build(ex: U.Export) -> MP.Plan:
    return U.build_plan(ex, built_at="t", lane=IL.scope_unretire_lane(WAVE))


def skipped(plan: MP.Plan) -> dict[str, str]:
    return {v.site_id: v.reason for v in plan.skipped}


class TestThePlanner:
    def test_a_date_retirement_the_label_rule_keeps_comes_back_with_its_reason(self) -> None:
        plan = build(export([site_row(PRAMBANAN)], [journal(PRAMBANAN, 42576)]))
        got = {c.column: c for c in plan.changes}
        assert (got["scope_status"].old_value, got["scope_status"].new_value) == (
            "retired",
            "in_scope",
        )
        assert got["scope_reason"].new_value == (
            "D58 label rule (owner, 2026-10-24): rest of world, period_start 850 lies inside its "
            "window through 1500 AD; the E3 retirement no longer holds"
        )
        assert got["scope_reason"].old_value == site_row(PRAMBANAN)["scope_reason"]
        assert got["scope_status"].premise == f"premise-{PRAMBANAN[:8]}"
        sources = [e["source"] for e in got["scope_reason"].evidence]
        assert sources == ["remediation_change_log:42576", "pipeline/normalizers/dates.py"]
        assert plan.counters["d58_date"] == 1 and plan.skipped == ()

    @pytest.mark.parametrize(
        ("over", "reason"),
        [
            ({"country": "Poland", "lat": 51.56, "lon": 15.52, "period_start": 1000},
             "outside-label-window"),
            ({"country": "Japan", "lat": 34.7, "lon": 135.5, "period_start": 1583},
             "outside-label-window"),
            ({"country": "Türkiye", "lat": 37.18, "lon": 40.95, "period_start": 750},
             "outside-label-window"),
            ({"country": "Lebanon", "lat": 33.58, "lon": 35.61, "period_start": 975},
             "label-borderline"),
            ({"country": "Canada", "lat": 51.6, "lon": -55.53, "period_start": 1000,
              "qids": ["Q189113"]}, "viking-subject"),
            ({"lon": None}, "label-rule-cannot-tell"),
            ({"period_start": None}, "label-rule-cannot-tell"),
            ({"country": None}, "outside-label-window"),  # an unplaced point keeps 500
        ],
    )  # fmt: skip
    def test_a_date_retirement_the_label_rule_does_not_keep_stays(
        self, over: dict[str, Any], reason: str
    ) -> None:
        plan = build(export([site_row(CHROBRY, **over)], [journal(CHROBRY, 1)]))
        assert plan.changes == () and skipped(plan) == {CHROBRY: reason}

    def test_only_a_journalled_retirement_is_taken_back(self) -> None:
        plan = build(export([site_row(PRAMBANAN)], []))
        assert skipped(plan) == {PRAMBANAN: "retirement-not-journalled"}
        moved = [journal(PRAMBANAN, 1), journal(PRAMBANAN, 2, new="in_scope", old="retired")]
        assert skipped(build(export([site_row(PRAMBANAN)], moved))) == {
            PRAMBANAN: "retirement-not-journalled"
        }
        again = [journal(PRAMBANAN, 1, new="in_scope"), journal(PRAMBANAN, 2)]
        assert build(export([site_row(PRAMBANAN)], again)).counters["d58_date"] == 1

    def test_a_retirement_no_decision_names_is_left_alone_and_not_listed(self) -> None:
        dup = site_row(DUPLICATE, scope_reason=f"duplicate_of:{PRAMBANAN}")
        nonsite = site_row(NORSE, scope_reason="E3: not an archaeological site (modern): a hotel")
        plan = build(export([dup, nonsite], [journal(DUPLICATE, 1), journal(NORSE, 2)]))
        assert plan.changes == () and plan.skipped == ()

    def test_a_pinned_museum_comes_back_outside_the_medieval_old_world_only(self) -> None:
        museum = site_row(
            KHUSHUU, name="Khushuu Tsaidam Museum", site_type="Museum", country="Mongolia",
            lat=47.57, lon=102.87, period_start=2008,
            scope_reason="E3 museum rule (plan section 8.2): Plan section 8.2: one of the 3 Museum "
            "rows that leave (Gokturk Orkhon stelae, 8th century).",
        )  # fmt: skip
        raden = site_row(
            GROSS_RADEN, site_type="Museum", country="Germany", lat=53.7, lon=11.9, period_start=800,
            scope_reason="E3 museum rule (plan section 8.2): ... (Slavic settlement and temple, "
            "9th/10th century). Phase 3 wrote period_start",
        )  # fmt: skip
        other = site_row(OTHER_MUSEUM, site_type="Museum", scope_reason="E3 museum rule: x")
        moved = {**museum, "scope_reason": "E3 museum rule: another reason"}
        plan = build(
            export([museum, raden, other], [journal(s, n) for n, s in enumerate(U.MUSEUM_EXHIBITS)]
                   + [journal(OTHER_MUSEUM, 9)])
        )  # fmt: skip
        reason = next(c.new_value for c in plan.changes if c.column == "scope_reason")
        assert reason == (
            "D58 label rule (owner, 2026-10-24), museum rule: its exhibits (Gokturk Orkhon stelae, "
            "8th century) lie in the rest of world, inside the window through 1500 AD; the E3 "
            "retirement no longer holds"
        )
        assert skipped(plan) == {
            GROSS_RADEN: "museum-exhibits-out",
            OTHER_MUSEUM: "museum-not-pinned",
        }
        assert skipped(build(export([moved], [journal(KHUSHUU, 1)]))) == {
            KHUSHUU: "museum-reason-moved"
        }
        unplaced = {**museum, "country": None}
        assert skipped(build(export([unplaced], [journal(KHUSHUU, 1)]))) == {
            KHUSHUU: "museum-exhibits-out"
        }
        retyped = {**museum, "site_type": "Temple complex"}
        assert skipped(build(export([retyped], [journal(KHUSHUU, 1)]))) == {
            KHUSHUU: "museum-type-moved"
        }

    def test_a_d50_site_waits_for_its_dispute_text(self) -> None:
        yonaguni = site_row(YONAGUNI, name="Yonaguni Monument", country="Japan", lat=24.4,
                            lon=123.0, period_start=None, scope_reason=D50_REASON_NOW)  # fmt: skip
        rows = [journal(YONAGUNI, 1, new="pending"), journal(YONAGUNI, 2, old="pending")]
        plan = build(export([yonaguni], rows))
        assert plan.changes == () and skipped(plan) == {YONAGUNI: "d50-no-dispute-text"}
        assert "no journal row wrote the description" in plan.skipped[0].note
        for row, says in (
            (dispute_row(decision=wc4.EVIDENCE_DECISION), "is no lane-E enrichment"),
            (dispute_row(dispute=None), "without a dispute brief"),
            (dispute_row(dispute=brief(verdict="unverified")), "is not 'dispute'"),
            (dispute_row(dispute=brief(RICHAT)), f"is of {RICHAT}"),
            (dispute_row(classes={"3": wc4.DISPUTE_A}), "appended no dispute_b"),
            (dispute_row(classes={"3": wc4.FACT}), "appended no dispute_a"),
        ):
            got = build(export([yonaguni], rows, [row]))
            assert got.changes == () and says in got.skipped[0].note, says

    def test_a_d50_site_with_its_dispute_text_comes_back_disputed(self) -> None:
        yonaguni = site_row(YONAGUNI, name="Yonaguni Monument", country="Japan", lat=24.4,
                            lon=123.0, period_start=None, scope_reason=D50_REASON_NOW)  # fmt: skip
        rows = [
            journal(YONAGUNI, 129629, old="pending", stamp="2026-09-30_mechanical-scope-review")
        ]
        stale = dispute_row(n=400, decision=wc4.EVIDENCE_DECISION)
        plan = build(export([yonaguni], rows, [stale, dispute_row(n=500)]))
        got = {c.column: c for c in plan.changes}
        assert got["scope_reason"].new_value == (
            "D50 disputed site (owner, 2026-10-19): shown as disputed; its description states the "
            "scholarly position and the claim, both sourced (remediation_change_log:500)"
        )
        urls = [e["url"] for e in got["scope_reason"].evidence]
        assert urls[2:] == [SOURCE_A["url"], SOURCE_B["url"]]
        assert plan.counters["d50_disputed"] == 1
        latest_bad = [dispute_row(n=500), dispute_row(n=600, dispute=None)]
        assert build(export([yonaguni], rows, latest_bad)).changes == (), "the latest row decides"

    def test_a_d50_site_retired_for_another_reason_is_not_its_lane_s(self) -> None:
        richat = site_row(RICHAT, scope_reason="E3: period_start 1200 is past")
        plan = build(export([richat], [journal(RICHAT, 1)], [dispute_row(RICHAT)]))
        assert skipped(plan) == {RICHAT: "d50-reason-moved"}

    def test_a_shown_site_in_the_export_stops_the_plan(self) -> None:
        with pytest.raises(U.UnretireError, match="not retired"):
            build(export([site_row(PRAMBANAN, scope_status=None)], []))

    def test_the_plan_s_records_are_the_lane_s_and_its_rollback_retires_again(
        self, tmp_path: Path
    ) -> None:
        plan = build(export([site_row(PRAMBANAN)], [journal(PRAMBANAN, 1)]))
        MP.write_plan_jsonl(plan, tmp_path / "PLAN.jsonl")
        MP.write_rollback_sql(plan, tmp_path / "ROLLBACK.sql", plan_path=tmp_path / "PLAN.jsonl")
        records = A.load_records(tmp_path / "PLAN.jsonl")
        A.validate_records(records, lane=plan.lane)
        rollback = (tmp_path / "ROLLBACK.sql").read_text("utf-8")
        assert f"{WAVE}_mechanical-scope-unretire-rollback" in rollback

    def test_a_wave_is_its_first_hundred_sites(self) -> None:
        sites, rows = [], []
        for i in range(101):
            sid = f"{i:08x}-0000-4000-8000-000000000000"
            sites.append(site_row(sid))
            rows.append(journal(sid, i + 1))
        wave = U.first_wave(build(export(sites, rows)))
        assert wave.counters["wave_sites"] == 100 and wave.counters["left_for_later_waves"] == 1
        assert len({c.site_id for c in wave.changes}) == 100


# ------------------------------------------------------------------------------ the waves
def _export_text(ex_sites: list[dict], rows: list[dict], disputes: list[dict] = ()) -> str:
    lines = [json.dumps({"kind": "site", "row": s}) for s in ex_sites]
    lines += [json.dumps({"kind": "journal", "row": r}) for r in rows]
    lines += [json.dumps({"kind": "dispute", "row": d}) for d in disputes]
    lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": "2026-10-24 08:00"}}))
    return "\n".join(lines) + "\n"


class TestTheWaves:
    def write_export(self, out: Path, text: str) -> None:
        path = U.export_path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def test_a_wave_writes_its_files_and_is_never_replaced_or_planned_twice(
        self, tmp_path: Path
    ) -> None:
        self.write_export(tmp_path, _export_text([site_row(PRAMBANAN)], [journal(PRAMBANAN, 1)]))
        result = U.write_wave(tmp_path, WAVE, built_at="t")
        assert result["sites"] == 1 and result["lane"] == f"scope-unretire-{WAVE}"
        for name in ("PLAN.jsonl", "SKIPPED.jsonl", "PLAN.md", "ROLLBACK.sql", "SOURCE.json"):
            assert (tmp_path / WAVE / name).is_file(), name
        assert "Prambanan Temple" in (tmp_path / WAVE / "PLAN.md").read_text("utf-8")
        with pytest.raises(U.UnretireError, match="was planned from this export"):
            U.write_wave(tmp_path, WAVE + "b", built_at="t")
        self.write_export(
            tmp_path, _export_text([site_row(PRAMBANAN, name="P")], [journal(PRAMBANAN, 1)])
        )
        with pytest.raises(U.UnretireError, match="holds a plan already"):
            U.write_wave(tmp_path, WAVE, built_at="t")

    def test_a_wave_with_nothing_to_write_is_refused_and_says_why(self, tmp_path: Path) -> None:
        chrobry = site_row(CHROBRY, country="Poland", lat=51.56, lon=15.52, period_start=1000)
        self.write_export(tmp_path, _export_text([chrobry], [journal(CHROBRY, 1)]))
        with pytest.raises(U.UnretireError, match="outside-label-window"):
            U.write_wave(tmp_path, WAVE, built_at="t")
        assert not (tmp_path / WAVE).exists()

    def test_a_missing_export_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(U.UnretireError, match="run `export` first"):
            U.write_wave(tmp_path, WAVE, built_at="t")

    def test_the_cli_refuses_a_label_that_is_no_wave(self, capsys: pytest.CaptureFixture) -> None:
        with pytest.raises(SystemExit):
            U.main(["write", "--wave", "soon"])
        assert "is not a wave label" in capsys.readouterr().err


class TestTheExport:
    def test_the_export_is_one_read_only_snapshot_of_the_retired_and_their_journal(self) -> None:
        script = MP.tagged_export_script(U.EXPORT_PARTS)
        assert "REPEATABLE READ READ ONLY" in script
        for verb in ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE"):
            assert verb not in script.upper().replace("UPDATED_AT", ""), verb
        assert "u.scope_status = 'retired'" in U.EXPORT_SITES_SQL
        assert f"{IL.SCOPE_UNRETIRE_PREMISE_SQL} AS premise" in U.EXPORT_SITES_SQL
        assert "e.kind = 'wikidata_qid'" in U.EXPORT_SITES_SQL
        assert "l.column_name = 'scope_status'" in U.EXPORT_JOURNAL_SQL
        assert "l.new_value = u.description" in U.EXPORT_DISPUTE_SQL
        for sid in L.D50_DISPUTED_SITES:
            assert f"'{sid}'" in U.EXPORT_DISPUTE_SQL

    def test_the_export_parses_into_its_three_parts(self) -> None:
        text = _export_text([site_row(PRAMBANAN)], [journal(PRAMBANAN, 1)], [dispute_row()])
        ex = U.parse_export(text)
        assert (len(ex.sites), len(ex.journal), len(ex.disputes)) == (1, 1, 1)
        assert ex.exported_at == "2026-10-24 08:00"

    def test_the_d50_sites_are_the_six_the_scope_review_retired(self) -> None:
        assert sorted(L.D50_DISPUTED_SITES.values()) == [
            "Baltic Sea Anomaly",
            "Bosnian Pyramid of Love",
            "Bosnian Pyramid of the Moon",
            "Bosnian Pyramid of the Sun",
            "Richat Structure",
            "Yonaguni Monument",
        ]
