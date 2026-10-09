"""D25: does a component site get its parent - and only a parent that is one?

`mechanical/parent.py` turns `PARENT_DECISIONS.jsonl` into waves (`CHILDREN.json`) and a wave into one
plan, lane `parent-<wave>`: per child one cell, `parent_site_id` NULL -> the parent. The pairs the plan
cannot carry are held back and listed; what the transaction proves again after the write - the parent
shows, lies in the child's country within 5 km, and the depth stays one - is evaluated here in SQLite
(the SQL is portable) with a state that satisfies it and one state per way each check can fail.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import parent as PA  # noqa: E402
from mechanical import plan as P  # noqa: E402

from pipeline.utils.geo import haversine_distance  # noqa: E402

WAVE = "2026-10-12"
CHILD = "e1e4e79c-a9c4-4169-8fde-371c0df79061"
PARENT = "9f5be838-53ab-48d8-9a1a-ac9597a87777"
OTHER = "5adaee62-3e90-4550-930c-6cd9039c223d"
GEONAMES = "8db5555a-a9a3-417b-944c-6ec0c04de0db"
RETIRED_SITE = "04d8ce82-4fa3-4e48-88b7-bb41b354260c"
NOW = "2026-10-12T00:00:00+00:00"
LANE = L.parent_lane(WAVE)
QUOTES = ({"source": "https://en.wikipedia.org/wiki/Pompeii", "quote": "part of Pompeii"},)


def child(c: str = CHILD, p: str = PARENT, **over: Any) -> PA.WaveChild:
    base: dict[str, Any] = {
        "child": c, "parent": p, "child_name": "Theatre Area of Pompeii",
        "parent_name": "Pompeii", "p361": True, "why": "it is part of", "quotes": QUOTES,
    }  # fmt: skip
    return PA.WaveChild(**{**base, **over})


def row(site: str, name: str, **over: Any) -> dict[str, Any]:
    base = {
        "id": site, "name": name, "country": "Italy", "source_id": "ancient_nerds",
        "scope_status": None, "scope_reason": None, "lat": 40.75, "lon": 14.48,
        "parent_site_id": None, "n_children": 0, "premise": f"{name} | Italy | 40.75, 14.48",
    }  # fmt: skip
    return {**base, **over}


def a_read(**over: Any) -> PA.Read:
    base = PA.Read(
        sites={CHILD: row(CHILD, "Theatre Area of Pompeii"), PARENT: row(PARENT, "Pompeii")},
        metres={CHILD: 120.0},
        stamps={},
        read_at="2026-10-12 10:00:00+00",
    )
    return replace(base, **over)


def plan_of(
    read: PA.Read | None = None,
    children: list[PA.WaveChild] | None = None,
    losers: set[str] | None = None,
):
    return PA.build(read or a_read(), children or [child()], LANE, losers or set(), NOW)


# --------------------------------------------------------------------------------- the waves
class TestTheWaves:
    def decision(self, c: str, p: str, status: str = "decided") -> dict[str, Any]:
        return {"child": c, "parent": p, "child_name": f"c-{c[:4]}", "parent_name": f"p-{p[:4]}",
                "p361": False, "status": status, "why": "w", "quotes": list(QUOTES)}  # fmt: skip

    def test_only_the_decided_children_are_in_a_wave(self) -> None:
        rows = [
            self.decision(CHILD, PARENT),
            self.decision(OTHER, PARENT, "conflict"),
            self.decision(GEONAMES, PARENT, "held"),
        ]
        assert [c.child for c in PA.decided_children(rows)] == [CHILD]

    def test_the_children_of_one_parent_stay_in_one_wave(self) -> None:
        kids = [
            child(f"00000000-0000-4000-8000-{n:012d}", p)
            for n, p in ((1, PARENT), (2, PARENT), (3, OTHER), (4, OTHER))
        ]
        waves = PA.split_waves(kids, max_children=3)
        assert [len(w) for w in waves] == [2, 2]
        assert [len(w) for w in PA.split_waves(kids, max_children=100)] == [4]
        with pytest.raises(P.PlanError, match="a wave holds 1"):
            PA.split_waves(kids, max_children=1)

    def test_the_wave_file_is_written_once_and_read_back(self, tmp_path: Path) -> None:
        PA.write_wave(WAVE, [child()], tmp_path)
        assert PA.load_wave(WAVE, tmp_path) == [child()]
        with pytest.raises(P.PlanError, match="planned once"):
            PA.write_wave(WAVE, [child()], tmp_path)

    def test_a_file_of_another_wave_or_none_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="run `waves` first"):
            PA.load_wave(WAVE, tmp_path)
        path = PA.write_wave(WAVE, [child()], tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**data, "wave": "2026-10-13"}), encoding="utf-8")
        with pytest.raises(P.PlanError, match="is the file of wave"):
            PA.load_wave(WAVE, tmp_path)

    def test_the_labels_are_the_date_then_letters(self) -> None:
        assert PA.wave_labels(WAVE, 2) == [WAVE, f"{WAVE}b"]
        with pytest.raises(ValueError, match="not a wave label"):
            PA.wave_labels("soon", 1)


# ------------------------------------------------------------------------------------ the plan
class TestThePlan:
    def test_a_child_gets_one_cell_with_its_parent(self) -> None:
        plan, held = plan_of()
        assert held == [] and plan.lane is LANE
        [v] = plan.changes
        assert (v.site_id, v.column, v.old_value, v.new_value) == (
            CHILD,
            "parent_site_id",
            None,
            PARENT,
        )
        assert v.premise == "Theatre Area of Pompeii | Italy | 40.75, 14.48"

    def test_the_evidence_cites_the_decision_the_quotes_and_the_facts(self) -> None:
        [v] = plan_of()[0].changes
        sources = [e["source"] for e in v.evidence]
        assert (
            sources[0] == "identity/parent_judge.py" and sources[-1] == "production:unified_sites"
        )
        assert v.evidence[1]["url"] == QUOTES[0]["source"]
        assert (
            "120.0 m apart" in v.evidence[-1]["quote"]
            and "P361 proves it: True" in v.evidence[-1]["quote"]
        )

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (
                lambda r: {"sites": {PARENT: r.sites[PARENT]}},
                "the child .* is not in unified_sites",
            ),
            (
                lambda r: {
                    "sites": {**r.sites, PARENT: row(PARENT, "Pompeii", source_id="geonames")}
                },
                "parent is not a curated site",
            ),
            (
                lambda r: {"sites": {**r.sites, PARENT: row(PARENT, "Pompei")}},
                "the decision names 'Pompeii'",
            ),
            (
                lambda r: {
                    "sites": {
                        **r.sites,
                        PARENT: row(PARENT, "Pompeii", scope_status="retired", scope_reason="x"),
                    }
                },
                "the parent is retired",
            ),
            (
                lambda r: {
                    "sites": {
                        **r.sites,
                        CHILD: row(
                            CHILD,
                            "Theatre Area of Pompeii",
                            scope_status="retired",
                            scope_reason="x",
                        ),
                    }
                },
                "the child is retired",
            ),
            (
                lambda r: {
                    "sites": {
                        **r.sites,
                        PARENT: row(PARENT, "Pompeii", scope_reason=f"duplicate_of:{OTHER}"),
                    }
                },
                "neither a child nor a parent",
            ),
            (
                lambda r: {
                    "sites": {
                        **r.sites,
                        CHILD: row(CHILD, "Theatre Area of Pompeii", parent_site_id=OTHER),
                    }
                },
                "names a parent already",
            ),
            (
                lambda r: {"sites": {**r.sites, PARENT: row(PARENT, "Pompeii", country="Greece")}},
                "another country",
            ),
            (lambda r: {"metres": {}}, "no distance"),
            (lambda r: {"metres": {CHILD: 5000.1}}, "at most 5000 m"),
            (
                lambda r: {
                    "sites": {**r.sites, PARENT: row(PARENT, "Pompeii", parent_site_id=OTHER)}
                },
                "depth one only",
            ),
            (
                lambda r: {
                    "sites": {**r.sites, CHILD: row(CHILD, "Theatre Area of Pompeii", n_children=2)}
                },
                "depth one only",
            ),
        ],
    )
    def test_each_check_holds_a_child_back_on_its_own(self, change, message: str) -> None:
        read = replace(a_read(), **change(a_read()))
        with pytest.raises(P.PlanError, match=message):
            plan_of(read)

    def test_5000_metres_is_the_limit_and_the_same_country_is_exact(self) -> None:
        plan_of(replace(a_read(), metres={CHILD: 5000.0}))

    def test_a_site_a_merge_retires_is_neither_child_nor_parent(self) -> None:
        for lost in (CHILD, PARENT):
            with pytest.raises(P.PlanError, match="neither a child nor a parent"):
                plan_of(losers={lost})

    def test_a_site_is_not_its_own_parent(self) -> None:
        with pytest.raises(P.PlanError, match="its own parent"):
            plan_of(
                children=[child(CHILD, CHILD, child_name="Pompeii", parent_name="Pompeii")],
                read=a_read(sites={CHILD: row(CHILD, "Pompeii")}, metres={CHILD: 0.0}),
            )

    def test_the_parent_of_a_child_in_the_wave_is_held_for_depth(self) -> None:
        read = a_read(
            sites={**a_read().sites, OTHER: row(OTHER, "Forum")},
            metres={CHILD: 100.0, PARENT: 100.0},
        )
        kids = [child(), child(PARENT, OTHER, child_name="Pompeii", parent_name="Forum")]
        with pytest.raises(P.PlanError, match="the parent is a child in this wave"):
            plan_of(read, kids)

    def test_a_held_child_is_listed_beside_the_planned_one(self) -> None:
        read = a_read(
            sites={**a_read().sites, OTHER: row(OTHER, "Forum", country="Greece")},
            metres={CHILD: 120.0, OTHER: 10.0},
        )
        kids = [child(), child(OTHER, PARENT, child_name="Forum")]
        plan, held = plan_of(read, kids)
        assert [v.site_id for v in plan.changes] == [CHILD]
        assert [(h["child"], h["reason"]) for h in held] == [
            (OTHER, "another country: 'Greece' / 'Italy'")
        ]

    def test_a_lane_that_has_written_is_not_planned_again(self) -> None:
        with pytest.raises(P.PlanError, match="never re-planned"):
            plan_of(a_read(stamps={LANE.run_stamp: 1}))

    def test_a_wave_with_nothing_left_is_refused_and_says_why(self) -> None:
        with pytest.raises(P.PlanError, match="nothing to plan") as excinfo:
            plan_of(a_read(metres={}))
        assert "no distance of the pair" in str(excinfo.value)

    def test_the_cell_renders_under_the_parent_lane(self) -> None:
        [v] = plan_of()[0].changes
        record = A.ChangeRecord(
            site_id=v.site_id,
            site_name=v.site_name,
            old_value=None,
            new_value=v.new_value,
            rule=v.rule,
            condition="c",
            reason="r",
            evidence=v.evidence,
            premise=v.premise,
            column="parent_site_id",
        )
        sql = A.render_transaction([record], site_ids={CHILD}, lane=LANE)
        assert sql.count("-- site invariant:") == 4 and "parent_site_id" in sql
        assert "D25 parent site" in sql


# ---------------------------------------------------------------------------- the invariants
def sqlite_world() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.create_function("ST_MakePoint", 2, lambda lon, lat: f"{lon} {lat}")

    def sphere(a: str, b: str) -> float:
        (lon1, lat1), (lon2, lat2) = (map(float, p.split()) for p in (a, b))
        return 1000.0 * haversine_distance(lat1, lon1, lat2, lon2)

    db.create_function("ST_DistanceSphere", 2, sphere)
    db.execute(
        "CREATE TABLE unified_sites (id TEXT PRIMARY KEY, name TEXT, source_id TEXT, scope_status TEXT, "
        "scope_reason TEXT, lat REAL, lon REAL, country TEXT, parent_site_id TEXT)"
    )
    return db


def put(
    db: sqlite3.Connection,
    site: str,
    *,
    lat: float = 40.75,
    lon: float = 14.48,
    country: str = "Italy",
    source: str = "ancient_nerds",
    status: str | None = None,
    parent: str | None = None,
) -> None:
    db.execute(
        "INSERT INTO unified_sites VALUES (?, 'n', ?, ?, NULL, ?, ?, ?, ?)",
        (site, source, status, lat, lon, country, parent),
    )


def broken(db: sqlite3.Connection, probe: str, child_id: str = CHILD) -> int:
    invariant = next(i for i in LANE.site_invariants if i.probe_name == probe)
    sql = f"SELECT {invariant.predicate} FROM unified_sites u WHERE u.id = ?"
    return int(db.execute(sql, (child_id,)).fetchone()[0])


def parented(**parent: Any) -> sqlite3.Connection:
    db = sqlite_world()
    put(db, PARENT, **parent)
    put(db, CHILD, parent=PARENT)
    return db


class TestTheInvariantsInSQL:
    def test_a_shown_curated_parent_of_the_country_within_5_km_breaks_none(self) -> None:
        db = parented()
        for invariant in LANE.site_invariants:
            assert broken(db, invariant.probe_name) == 0, invariant.says

    def test_the_four_invariants_and_their_probes(self) -> None:
        assert [i.probe_name for i in LANE.site_invariants] == [
            "parent-not-curated",
            "parent-retired",
            "parent-far",
            "parent-depth",
        ]
        assert all(i.probe_column == "parent_site_id" for i in LANE.site_invariants)
        assert LANE.site_invariants[3].probe_values == (L.PROBE_SELF,)

    def test_a_parent_that_is_no_curated_site_is_counted(self) -> None:
        assert broken(parented(source="geonames"), "parent-not-curated") == 1
        db = sqlite_world()
        put(db, CHILD, parent=OTHER)  # a parent that does not exist
        assert broken(db, "parent-not-curated") == 1

    def test_a_retired_parent_is_counted_and_a_pending_one_is_not(self) -> None:
        assert broken(parented(status="retired"), "parent-retired") == 1
        assert broken(parented(status="pending"), "parent-retired") == 0

    def test_another_country_is_counted_even_next_door(self) -> None:
        assert broken(parented(country="Greece"), "parent-far") == 1

    def test_5000_metres_is_the_limit(self) -> None:
        # one degree of latitude is 111.2 km: 0.0449 degrees is 4.99 km, 0.0451 degrees 5.01 km
        assert broken(parented(lat=40.75 + 0.0449), "parent-far") == 0
        assert broken(parented(lat=40.75 + 0.0451), "parent-far") == 1

    def test_the_far_check_leaves_a_retired_parent_to_its_own_check(self) -> None:
        assert broken(parented(status="retired", country="Greece"), "parent-far") == 0

    def test_a_site_that_is_its_own_parent_is_counted(self) -> None:
        db = sqlite_world()
        put(db, CHILD, parent=CHILD)
        assert broken(db, "parent-depth") == 1

    def test_a_parent_with_a_parent_is_counted(self) -> None:
        db = parented(parent=OTHER)
        put(db, OTHER)
        assert broken(db, "parent-depth") == 1

    def test_a_child_that_is_a_parent_is_counted(self) -> None:
        db = parented()
        put(db, OTHER, parent=CHILD)
        assert broken(db, "parent-depth") == 1

    def test_each_probe_value_trips_its_own_check_first(self) -> None:
        """The probes are disjoint where they can be: a value of one kind breaks no check before it."""
        db = sqlite_world()
        put(db, GEONAMES, source="geonames")
        put(db, RETIRED_SITE, status="retired", country="Türkiye", lat=36.0, lon=30.0)
        put(db, CHILD)
        kinds = {"parent-not-curated": GEONAMES, "parent-retired": RETIRED_SITE}
        for name, parent in kinds.items():
            db.execute("UPDATE unified_sites SET parent_site_id = ? WHERE id = ?", (parent, CHILD))
            order = [i.probe_name for i in LANE.site_invariants]
            fired = [n for n in order if broken(db, n)]
            assert fired[0] == name, (name, fired)
        db.execute("UPDATE unified_sites SET parent_site_id = ? WHERE id = ?", (CHILD, CHILD))
        assert [
            n for n in ("parent-not-curated", "parent-retired", "parent-far") if broken(db, n)
        ] == []


class TestTheProbes:
    RECORD = A.ChangeRecord(
        site_id=CHILD,
        site_name="c",
        old_value=None,
        new_value=PARENT,
        rule="r",
        condition="c",
        reason="r",
        evidence=({"source": "t", "quote": "q"},),
        premise="p",
        column="parent_site_id",
    )

    def cases(self) -> dict[str, Any]:
        foreign = {"id": GEONAMES, "name": "Chiapa", "premise": "x"}
        return {c[0]: c for c in A.probe_cases([self.RECORD], LANE, foreign)}

    def test_the_site_s_own_id_probes_the_depth_check(self) -> None:
        mutated = self.cases()["invariant-parent-depth"][2]
        assert mutated[0].new_value == CHILD

    def test_the_other_probes_name_a_row_of_their_kind(self) -> None:
        cases = self.cases()
        assert (
            cases["invariant-parent-not-curated"][2][0].new_value
            == "00000000-0000-0000-0000-000000000000"
        )
        assert (
            cases["invariant-parent-retired"][2][0].new_value
            == "04d8ce82-4fa3-4e48-88b7-bb41b354260c"
        )
        assert (
            cases["invariant-parent-far"][2][0].new_value == "30d3fb78-6b80-42f9-87f8-7616e63bec4f"
        )

    def test_a_guard_probe_exists_for_every_guard_a_cell_lane_renders(self) -> None:
        assert {
            "guard1-other-source",
            "guard2-no-op",
            "guard3-foreign-old-value",
            "guard5-premise",
        } <= set(self.cases())
        assert A.unprobed_invariants([self.RECORD], LANE) == []

    def test_a_site_invariant_probe_may_not_be_the_site_s_id_alone_unless_named(self) -> None:
        with pytest.raises(ValueError, match="needs its column and three values"):
            L.SiteInvariant("x", "true", "parent_site_id", ("a", "b"))
        L.SiteInvariant("x", "true", "parent_site_id", (L.PROBE_SELF,))

    def test_every_probe_names_a_refusal_the_statement_raises(self) -> None:
        for suffix, _name, mutated, expected in self.cases().values():
            sql = A.render_transaction(
                mutated,
                run_stamp=f"{LANE.probe_run_stamp}-{suffix}",
                site_ids={CHILD},
                validate=False,
                lane=LANE,
            )
            assert (
                f"RAISE EXCEPTION '{LANE.label}: % {expected.replace('ancient_nerds', '%')}'" in sql
            ), suffix


class TestTheReadBack:
    def test_the_read_back_counts_children_chains_and_distances(self) -> None:
        text = A.readback_for(LANE)
        for metric in (
            "curated sites that name a parent",
            "curated children whose parent is retired or not curated",
            "curated children in another country than their parent",
            "curated children further than 5000 m from their parent",
            "curated sites in a chain (a child that is a parent, or its own parent)",
        ):
            assert f"'{metric}'" in text, metric

    def test_the_residual_is_the_sites_that_name_a_parent(self) -> None:
        assert LANE.post_commit_residual.predicate == "parent_site_id IS NOT NULL"


class TestTheFiles:
    def test_the_read_is_one_read_only_snapshot_of_the_wave(self) -> None:
        parts = PA.read_parts([child()], LANE)
        assert [k for k, _ in parts] == ["site", "metres", "stamp"]
        script = P.tagged_export_script(parts)
        assert "READ ONLY" in script and LANE.premise_sql in dict(parts)["site"]
        for verb in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP", "ALTER"):
            assert verb not in script.upper().replace("ON_ERROR_STOP", "")

    def test_the_tagged_read_becomes_the_read(self) -> None:
        lines = [
            {"kind": "site", "row": row(CHILD, "Theatre Area of Pompeii")},
            {"kind": "metres", "row": {"child": CHILD, "metres": 120.0}},
            {"kind": "stamp", "row": {"run_stamp": LANE.run_stamp, "n": 0}},
            {"kind": "snapshot", "row": {"exported_at": "2026-10-12 10:00:00+00"}},
        ]
        read = PA.parse_read("\n".join(json.dumps(x) for x in lines), [child()], LANE)
        assert read.metres == {CHILD: 120.0} and read.stamps == {LANE.run_stamp: 0}

    def test_the_plan_files_are_the_lane_s(self, tmp_path: Path) -> None:
        plan, held = plan_of()
        PA.write_plan(plan, held, a_read(), tmp_path)
        directory = tmp_path / LANE.out_dir_name
        records = A.load_records(directory / "PLAN.jsonl")
        assert [(r.column, r.old_value, r.new_value) for r in records] == [
            ("parent_site_id", None, PARENT)
        ]
        assert (
            (directory / "ROLLBACK.sql").read_text(encoding="utf-8").startswith("-- plan sha256 ")
        )
        A.emit(records, directory, LANE, plan_path=directory / "PLAN.jsonl")
        assert "ROLLBACK.sql` sets each `parent_site_id` back to NULL" in (
            directory / "PLAN.md"
        ).read_text(encoding="utf-8")

    def test_the_merged_losers_are_read_from_the_duplicate_decisions(self, tmp_path: Path) -> None:
        from identity import common

        assert PA.merged_losers(tmp_path) == set()
        common.write_jsonl(
            tmp_path / "DUP_DECISIONS.jsonl", [{"merges": [{"site_id": CHILD}], "cluster_id": "c"}]
        )
        assert PA.merged_losers(tmp_path) == {CHILD}

    def test_the_waves_command_and_the_dry_plan_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from identity import common

        run = tmp_path / "run"
        run.mkdir()
        common.write_jsonl(
            run / "PARENT_DECISIONS.jsonl",
            [
                {
                    "child": CHILD,
                    "parent": PARENT,
                    "child_name": "c",
                    "parent_name": "p",
                    "p361": False,
                    "status": "decided",
                    "why": "w",
                    "quotes": [],
                }
            ],
        )
        monkeypatch.setattr(common, "run_dir", lambda root=None: run)
        assert PA.main(["--out", str(tmp_path / "out"), "waves", "--date", WAVE]) == 0
        assert json.loads(capsys.readouterr().out)[WAVE]["children"] == 1
        assert PA.main(["--out", str(tmp_path / "out"), "plan", "--wave", WAVE]) == 0
        assert "add --write" in capsys.readouterr().out
        assert PA.main(["--out", str(tmp_path / "out"), "plan", "--wave", "2026-10-13"]) == 1
        assert "REFUSED" in capsys.readouterr().err


from tests.remediation.test_mechanical import ProbeProduction  # noqa: E402


class TestTheProbeRun:
    RECORD = A.ChangeRecord(
        site_id=CHILD, site_name="c", old_value=None, new_value=PARENT, rule="r", condition="c",
        reason="r", evidence=({"source": "t", "quote": "q"},), premise="p", column="parent_site_id",
    )  # fmt: skip

    def test_every_guard_and_every_survivor_check_is_proven_when_its_own_text_refuses_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ProbeProduction(LANE, [self.RECORD], monkeypatch)
        assert A.cmd_probe_guards([self.RECORD], tmp_path, LANE) == 0
        assert capsys.readouterr().out.count("refused by its own guard=True") == 9

    def test_the_retire_lane_s_three_checks_are_proven_with_the_wave_s_limits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        retire = L.dup_merge_retire_lane(WAVE, [L.MergePair(CHILD, PARENT, 2500)])
        records = [
            A.ChangeRecord(site_id=CHILD, site_name="c", old_value=None, new_value=v, rule="r", condition="c", reason="r", evidence=({"source": "t", "quote": "q"},), premise="p", column=c)
            for c, v in (("scope_status", "retired"), ("scope_reason", f"duplicate_of:{PARENT}"))
        ]  # fmt: skip
        ProbeProduction(retire, records, monkeypatch)
        assert A.cmd_probe_guards(records, tmp_path, retire) == 0
        assert capsys.readouterr().out.count("refused by its own guard=True") == 9


class TestTheWavesCommandOnNothing:
    def test_the_waves_command_refuses_without_a_decided_child(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from identity import common

        run = tmp_path / "run"
        run.mkdir()
        common.write_jsonl(
            run / "PARENT_DECISIONS.jsonl",
            [
                {
                    "child": CHILD,
                    "parent": PARENT,
                    "child_name": "c",
                    "parent_name": "p",
                    "p361": False,
                    "status": "held",
                    "why": "w",
                    "quotes": [],
                }
            ],
        )
        monkeypatch.setattr(common, "run_dir", lambda root=None: run)
        assert PA.main(["--out", str(tmp_path / "out"), "waves", "--date", WAVE]) == 1
        assert "holds no decided child" in capsys.readouterr().err
