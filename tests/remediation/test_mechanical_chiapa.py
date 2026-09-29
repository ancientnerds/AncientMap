"""HUMAN_ONLY Nr. 7: does the Chiapa pair get exactly the hide and the rename - and nothing else?

`mechanical/chiapa.py` plans two lanes from one read-only read: `chiapa-hide` (the empty row
"Chiapa de Corzo" retired as `duplicate_of:<the Zoque row>`) and `chiapa-name` (the Zoque row renamed
"Chiapa de Corzo", its key computed by Postgres). Each plan-side check refuses on its own here; the
guards the transactions carry - the empty-row premise, the three survivor checks, the rename's
premise that waits for the hide - are evaluated in SQLite where their SQL is portable, and their
probes are counted. The delivered-plan tests read `output/remediation/mechanical_chiapa/` only.
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

from l5.population import PINNED_NAMES  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import chiapa as C  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402

from pipeline.utils.geo import haversine_distance  # noqa: E402
from tests.remediation.test_mechanical import FOREIGN, ProbeProduction  # noqa: E402

HIDDEN = "24aa135d-4714-47f5-96c0-d58f0bc04b6f"
KEPT = "ed186ea9-9ed1-415d-828b-97d9f21401d2"
REASON = f"duplicate_of:{KEPT}"
CREATED = "2026-03-04 21:07:57.660461"
#: The stored points, read from production 2026-09-29 (read-only): 7.4 m apart.
HIDDEN_POINT = (16.702978402703742, -93.00403619076117)
KEPT_POINT = (16.703005507354554, -93.00410000425359)
DELIVERED = REPO / "output" / "remediation" / "mechanical_chiapa"
needs_plan = pytest.mark.skipif(
    not (DELIVERED / "hide" / "PLAN.jsonl").exists(), reason=f"{DELIVERED} not built yet"
)


def hidden_row(**over: Any) -> dict[str, Any]:
    row = {
        "id": HIDDEN, "name": "Chiapa de Corzo", "name_normalized": "chiapa de corzo",
        "source_id": "ancient_nerds", "scope_status": None, "scope_reason": None,
        "lat": HIDDEN_POINT[0], "lon": HIDDEN_POINT[1], "created_at": CREATED, "links": 0,
        "images": 0, "citations": 0, "ext": None, "hide_premise": L.EMPTY_ROW_PREMISE,
        "name_premise": L.duplicates_retired_onto([]),
    }  # fmt: skip
    return {**row, **over}


def kept_row(**over: Any) -> dict[str, Any]:
    row = {
        "id": KEPT, "name": "Zoque Culture Archaeological Zone",
        "name_normalized": "zoque culture archaeological zone", "source_id": "ancient_nerds",
        "scope_status": None, "scope_reason": None, "lat": KEPT_POINT[0], "lon": KEPT_POINT[1],
        "created_at": CREATED, "links": 3, "images": 20, "citations": 0,
        "ext": "enwiki_title=Chiapa de Corzo (Mesoamerican site), wikidata_qid=Q4384315",
        "hide_premise": "content links 3, images 20",
        "name_premise": L.duplicates_retired_onto([]),
    }  # fmt: skip
    return {**row, **over}


def a_read(**over: Any) -> C.Read:
    base = C.Read(
        sites={HIDDEN: hidden_row(), KEPT: kept_row()},
        metres=7.43465614,
        key="chiapa de corzo",
        holders=({"id": HIDDEN, "name": "Chiapa de Corzo", "scope_status": None},),
        journal={},
        stamps={},
        read_at="2026-09-29 15:46:18.899089+00",
    )
    return replace(base, **over)


def with_site(site_id: str, row: dict[str, Any] | None) -> C.Read:
    sites = {HIDDEN: hidden_row(), KEPT: kept_row()}
    if row is None:
        del sites[site_id]
    else:
        sites[site_id] = row
    return a_read(sites=sites)


NOW = "2026-09-29T00:00:00+00:00"


# ------------------------------------------------------------------------------ the plan
class TestThePlan:
    def test_the_hide_and_the_rename_as_decided(self) -> None:
        hide, rename = C.build(a_read(), NOW)
        assert hide.lane is L.CHIAPA_HIDE and rename.lane is L.CHIAPA_NAME
        assert [(v.site_id, v.column, v.old_value, v.new_value) for v in hide.changes] == [
            (HIDDEN, "scope_status", None, "retired"),
            (HIDDEN, "scope_reason", None, REASON),
        ]
        assert [(v.site_id, v.column, v.old_value, v.new_value) for v in rename.changes] == [
            (KEPT, "name", "Zoque Culture Archaeological Zone", "Chiapa de Corzo"),
            (KEPT, "name_normalized", "zoque culture archaeological zone", "chiapa de corzo"),
        ]
        assert {v.premise for v in hide.changes} == {"content links 0, images 0"}
        assert {v.premise for v in rename.changes} == {
            f"duplicates retired onto it: 1, highest id {HIDDEN}"
        }

    def test_the_evidence_cites_the_owner_decision_and_the_wikidata_label(self) -> None:
        hide, rename = C.build(a_read(), NOW)
        for plan in (hide, rename):
            sources = [e["source"] for v in plan.changes for e in v.evidence]
            assert "output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md" in sources
            assert "production:unified_sites" in sources
        label = [e for v in rename.changes for e in v.evidence if e["source"].startswith("wiki")]
        assert label and "en label = 'Chiapa de Corzo'" in label[0]["quote"]
        assert "7.4 m apart" in hide.changes[0].evidence[1]["quote"]
        assert "survivor_rank" in hide.changes[0].evidence[2]["url"]

    def test_the_pair_is_l5_s_pinned_rename(self) -> None:
        pinned = PINNED_NAMES[KEPT]
        assert (C.HIDDEN, C.HIDDEN_REASON) == pinned.hidden_first == (HIDDEN, REASON)
        assert C.HIDDEN_REASON == f"{L.DUPLICATE_PREFIX}{KEPT}"
        assert (pinned.old, pinned.new) == ("Zoque Culture Archaeological Zone", "Chiapa de Corzo")

    @pytest.mark.parametrize(
        ("read", "message"),
        [
            (lambda: with_site(HIDDEN, None), "row to hide .* is not in unified_sites"),
            (lambda: with_site(HIDDEN, hidden_row(source_id="geonames")), "not a curated site"),
            (lambda: with_site(HIDDEN, hidden_row(name="Chiapa")), "the decision hides"),
            (
                lambda: with_site(HIDDEN, hidden_row(scope_status="pending", scope_reason="x")),
                "already has a scope decision",
            ),
            (
                lambda: with_site(HIDDEN, hidden_row(scope_reason="x")),
                "already has a scope decision",
            ),
            (
                lambda: with_site(HIDDEN, hidden_row(hide_premise="content links 1, images 0")),
                "an empty row",
            ),
            (
                lambda: with_site(HIDDEN, hidden_row(hide_premise="content links 0, images 2")),
                "an empty row",
            ),
            (
                lambda: a_read(
                    journal={
                        (HIDDEN, "scope_status"): (
                            P.JournalLink(9, "2026-09-25_x", "t", None, "retired"),
                        )
                    }
                ),
                "journal-disagrees",
            ),
            (lambda: with_site(KEPT, None), "kept row .* is not in unified_sites"),
            (lambda: with_site(KEPT, kept_row(source_id="wikidata")), "not a curated site"),
            (
                lambda: with_site(KEPT, kept_row(scope_status="retired", scope_reason="x")),
                "the kept row is retired",
            ),
            (lambda: a_read(metres=100.5), "one site is at most 100 m"),
            (
                lambda: with_site(KEPT, kept_row(created_at="2026-03-05 00:00:00")),
                "survivor rule keeps the empty row",
            ),
            (lambda: with_site(KEPT, kept_row(name="Zoque")), "the rename replaces"),
            (lambda: with_site(KEPT, kept_row(name_normalized=None)), "the rename replaces"),
            (
                lambda: a_read(
                    journal={
                        (KEPT, "name"): (P.JournalLink(9, "2026-09-26_x", "t", "Zoque", "Z"),)
                    }
                ),
                "journal-disagrees",
            ),
            (
                lambda: with_site(
                    KEPT, kept_row(name_premise=L.duplicates_retired_onto(["0" * 8]))
                ),
                "a row is retired onto the kept row already",
            ),
            (
                lambda: a_read(
                    holders=(
                        {"id": HIDDEN, "name": "Chiapa de Corzo", "scope_status": None},
                        {"id": "1" * 8, "name": "Chiapa de Corzo", "scope_status": "pending"},
                    )
                ),
                "two visible rows would be called",
            ),
            (
                lambda: a_read(stamps={L.CHIAPA_HIDE.run_stamp: 2}),
                "a lane that has written is never re-planned",
            ),
        ],
        ids=[
            "hidden-gone", "hidden-not-curated", "hidden-renamed", "hidden-decided",
            "hidden-reason-only", "hidden-has-a-link", "hidden-has-images", "hidden-journal",
            "kept-gone", "kept-not-curated", "kept-retired", "too-far", "survivor-rule",
            "kept-renamed", "kept-without-key", "kept-journal", "retired-onto-kept",
            "another-visible-holder", "stamp-written",
        ],
    )  # fmt: skip
    def test_each_check_refuses_on_its_own(self, read: Any, message: str) -> None:
        with pytest.raises(P.PlanError, match=message):
            C.build(read(), NOW)

    def test_a_retired_holder_of_the_name_is_no_obstacle(self) -> None:
        holders = (
            {"id": HIDDEN, "name": "Chiapa de Corzo", "scope_status": None},
            {"id": "1" * 8, "name": "Chiapa de Corzo", "scope_status": "retired"},
        )
        _hide, rename = C.build(a_read(holders=holders), NOW)
        assert rename.changes[0].new_value == "Chiapa de Corzo"

    def test_a_journal_that_ends_at_the_live_value_is_no_obstacle(self) -> None:
        journal = {
            (KEPT, "name"): (P.JournalLink(9, "2026-03-04_x", "t", "Zoque", C.RENAME.old),),
        }
        hide, _rename = C.build(a_read(journal=journal), NOW)
        assert len(hide.changes) == 2


class TestTheRead:
    def test_one_read_only_snapshot_of_exactly_the_pair(self) -> None:
        script = P.tagged_export_script(C.read_parts())
        assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" in script
        assert f"u.id IN ('{HIDDEN}', '{KEPT}')" in script
        assert L.EMPTY_ROW_PREMISE_SQL in script and L.DUPLICATES_RETIRED_ONTO_SQL in script
        assert "left(lower(unaccent('Chiapa de Corzo')), 500)" in script
        for stamp in (L.CHIAPA_HIDE.run_stamp, L.CHIAPA_NAME.rollback_run_stamp):
            assert f"'{stamp}'" in script

    def test_the_tagged_lines_become_the_read(self) -> None:
        lines = [
            {"kind": "site", "row": hidden_row()},
            {"kind": "site", "row": kept_row()},
            {"kind": "pair", "row": {"metres": 7.43465614}},
            {"kind": "key", "row": {"name": "Chiapa de Corzo", "key": "chiapa de corzo"}},
            {"kind": "holder", "row": {"id": HIDDEN, "name": "x", "scope_status": None}},
            {
                "kind": "journal",
                "row": {
                    "id": 5,
                    "row_pk": KEPT,
                    "column_name": "name",
                    "run_stamp": "s",
                    "test_id": "t",
                    "old_value": "a",
                    "new_value": C.RENAME.old,
                },
            },  # fmt: skip
            {"kind": "stamp", "row": {"run_stamp": L.CHIAPA_NAME.run_stamp, "n": 0}},
            {"kind": "snapshot", "row": {"exported_at": "2026-09-29 15:46:18+00"}},
        ]
        read = C.parse_read("".join(json.dumps(line) + "\n" for line in lines))
        assert set(read.sites) == {HIDDEN, KEPT} and read.key == "chiapa de corzo"
        assert read.journal[(KEPT, "name")][0].new_value == C.RENAME.old
        assert read.read_at == "2026-09-29 15:46:18+00"
        hide, _rename = C.build(read, NOW)
        assert hide.changes[0].premise == L.EMPTY_ROW_PREMISE
        twice = "".join(json.dumps(line) + "\n" for line in [lines[2], *lines])
        with pytest.raises(P.PlanError, match="once"):
            C.parse_read(twice)

    def test_both_lanes_files_are_the_mechanical_lanes(self, tmp_path: Path) -> None:
        hide, rename = C.build(a_read(), NOW)
        C.write_plans(hide, rename, a_read(), tmp_path)
        for plan in (hide, rename):
            directory = tmp_path / plan.lane.out_dir_name
            records = A.load_records(directory / "PLAN.jsonl")
            A.validate_records(records, lane=plan.lane)
            assert A.emit(records, directory, plan.lane, plan_path=directory / "PLAN.jsonl") == 2
            P.verify_pinned(
                directory / "ROLLBACK.sql",
                plan_path=directory / "PLAN.jsonl",
                expected=A.rollback_statement(records, plan.lane),
            )
        page = (tmp_path / "mechanical_chiapa" / "hide" / "PLAN.md").read_text(encoding="utf-8")
        assert "Runs first" in page and "| scope_status | NULL | `retired` |" in page
        page = (tmp_path / "mechanical_chiapa" / "name" / "PLAN.md").read_text(encoding="utf-8")
        assert "Runs second" in page and "rename's `ROLLBACK.sql` first" in page


# ------------------------------------------------------------------------ the guards in SQL
def sqlite_sites() -> sqlite3.Connection:
    """The three tables the guards read, with PostGIS's two point functions: a point is its text,
    the sphere distance the haversine one (PostGIS's sphere and this radius differ by 0.0001 %)."""
    db = sqlite3.connect(":memory:")
    db.create_function("ST_MakePoint", 2, lambda lon, lat: f"{lon} {lat}")

    def sphere(a: str, b: str) -> float:
        (lon1, lat1), (lon2, lat2) = (map(float, p.split()) for p in (a, b))
        return 1000.0 * haversine_distance(lat1, lon1, lat2, lon2)

    db.create_function("ST_DistanceSphere", 2, sphere)
    db.execute(
        "CREATE TABLE unified_sites (id TEXT PRIMARY KEY, source_id TEXT, scope_status TEXT, "
        "scope_reason TEXT, lat REAL, lon REAL)"
    )
    db.execute("CREATE TABLE site_content_links (site_id TEXT)")
    db.execute("CREATE TABLE wiki_images (site_id TEXT)")
    return db


def add(db: sqlite3.Connection, site: str, *, source: str = "ancient_nerds", status: Any = None,
        reason: Any = None, point: tuple[float, float] = KEPT_POINT) -> None:  # fmt: skip
    db.execute(
        "INSERT INTO unified_sites VALUES (?, ?, ?, ?, ?, ?)",
        (site, source, status, reason, *point),
    )


def one(db: sqlite3.Connection, expression: str, site: str) -> Any:
    """`expression` evaluated on the row `u` = `site`."""
    query = f"SELECT {expression} FROM unified_sites u WHERE u.id = ?"
    return db.execute(query, (site,)).fetchone()[0]


class TestTheGuardsInSQL:
    def test_the_empty_row_premise_counts_links_and_images(self) -> None:
        db = sqlite_sites()
        add(db, HIDDEN, point=HIDDEN_POINT)
        assert one(db, L.EMPTY_ROW_PREMISE_SQL, HIDDEN) == L.EMPTY_ROW_PREMISE
        db.execute("INSERT INTO site_content_links VALUES (?)", (HIDDEN,))
        assert one(db, L.EMPTY_ROW_PREMISE_SQL, HIDDEN) == "content links 1, images 0"
        db.executemany("INSERT INTO wiki_images VALUES (?)", [(HIDDEN,), (HIDDEN,), (KEPT,)])
        assert one(db, L.EMPTY_ROW_PREMISE_SQL, HIDDEN) == "content links 1, images 2"

    def test_the_rename_premise_is_the_hide_it_waits_for(self) -> None:
        """Before the hide the kept row reads 0 and the rename is refused; after it, exactly the
        planned premise. Only a curated row retired with exactly the kept row's reason counts."""
        db = sqlite_sites()
        add(db, KEPT)
        add(db, HIDDEN, point=HIDDEN_POINT)
        planned = L.duplicates_retired_onto([HIDDEN])
        assert one(db, L.DUPLICATES_RETIRED_ONTO_SQL, KEPT) == L.duplicates_retired_onto([])
        for status, reason, source in (
            ("pending", REASON, "ancient_nerds"),
            ("retired", f"duplicate_of:{KEPT[:-1]}0", "ancient_nerds"),
            ("retired", REASON, "geonames"),
        ):
            db.execute(
                "UPDATE unified_sites SET scope_status = ?, scope_reason = ?, source_id = ? "
                "WHERE id = ?",
                (status, reason, source, HIDDEN),
            )
            assert one(db, L.DUPLICATES_RETIRED_ONTO_SQL, KEPT) != planned, (status, reason)
        db.execute(
            "UPDATE unified_sites SET scope_status = 'retired', scope_reason = ?, "
            "source_id = 'ancient_nerds' WHERE id = ?",
            (REASON, HIDDEN),
        )
        assert one(db, L.DUPLICATES_RETIRED_ONTO_SQL, KEPT) == planned
        second = "ffffffff-0000-0000-0000-000000000000"
        add(db, second, status="retired", reason=REASON)
        got = one(db, L.DUPLICATES_RETIRED_ONTO_SQL, KEPT)
        assert got == L.duplicates_retired_onto([HIDDEN, second]) and got != planned

    @pytest.mark.parametrize(
        ("survivor", "fires"),
        [
            ({"source": "ancient_nerds"}, None),
            ({"source": "geonames"}, "survivor-not-curated"),
            ({"absent": True}, "survivor-not-curated"),
            ({"reason": "E3: no survivor named"}, "survivor-not-curated"),
            ({"status": "retired"}, "survivor-retired"),
            ({"status": "pending"}, None),
            ({"point": (HIDDEN_POINT[0] + 0.00089, HIDDEN_POINT[1])}, None),
            ({"point": (HIDDEN_POINT[0] + 0.00091, HIDDEN_POINT[1])}, "survivor-far"),
            ({"point": (17.0, -93.0), "status": "retired"}, "survivor-retired"),
        ],
        ids=[
            "near-visible", "not-curated", "no-such-row", "no-duplicate-reason", "retired",
            "pending-is-visible", "99-m", "101-m", "far-and-retired",
        ],
    )  # fmt: skip
    def test_each_survivor_check_fires_for_its_kind_alone(
        self, survivor: dict[str, Any], fires: str | None
    ) -> None:
        """The three checks are disjoint: a survivor that fails fails exactly one, so each probe
        is refused by its own; a visible curated survivor within 100 m fails none."""
        db = sqlite_sites()
        if not survivor.get("absent"):
            add(db, KEPT, source=survivor.get("source", "ancient_nerds"),
                status=survivor.get("status"), point=survivor.get("point", KEPT_POINT))  # fmt: skip
        add(db, HIDDEN, status="retired", reason=survivor.get("reason", REASON), point=HIDDEN_POINT)
        fired = [
            invariant.probe_name
            for invariant in L.DUPLICATE_SURVIVOR_INVARIANTS
            if one(db, f"({invariant.predicate})", HIDDEN)
        ]
        assert fired == ([] if fires is None else [fires])

    def test_the_two_edge_points_lie_either_side_of_100_m(self) -> None:
        """The 99-m and 101-m survivors above, measured: 0.00089 and 0.00091 degrees of latitude."""
        near, far = ((HIDDEN_POINT[0] + d, HIDDEN_POINT[1]) for d in (0.00089, 0.00091))
        assert 98 < 1000 * haversine_distance(*HIDDEN_POINT, *near) < 100
        assert 100 < 1000 * haversine_distance(*HIDDEN_POINT, *far) < 102


# ------------------------------------------------------------------------------ the lanes
PROBES_OF_THE_HIDE = {
    "guard1-other-source",
    "guard2-no-op",
    "guard2-foreign-column",
    "guard3-foreign-old-value",
    "guard4-not-owned",
    "guard5-premise",
    "invariant-survivor-not-curated",
    "invariant-survivor-retired",
    "invariant-survivor-far",
}


def lane_records(directory: Path, which: int) -> list[A.ChangeRecord]:
    """The records of the hide (0) or the rename (1), written and read back as apply.py reads them."""
    plan = C.build(a_read(), NOW)[which]
    P.write_plan_jsonl(plan, directory / "PLAN.jsonl")
    return A.load_records(directory / "PLAN.jsonl")


class TestTheLanes:
    def test_the_lanes_are_registered_with_their_own_directories(self) -> None:
        assert L.resolve_lane("chiapa-hide") is L.CHIAPA_HIDE
        assert L.resolve_lane("chiapa-name") is L.CHIAPA_NAME
        assert A.lane_dir(L.CHIAPA_HIDE) == DELIVERED / "hide"
        assert A.lane_dir(L.CHIAPA_NAME) == DELIVERED / "name"
        assert A.readback_for(L.CHIAPA_HIDE) is L.CHIAPA_HIDE_READBACK

    def test_the_hide_writes_retired_and_nothing_else(self, tmp_path: Path) -> None:
        assert L.CHIAPA_HIDE.cell("scope_status").allowed_new_values == ("retired",)
        records = lane_records(tmp_path, 0)
        A.validate_records(records, lane=L.CHIAPA_HIDE)
        with pytest.raises(P.PlanError, match="not a value the chiapa-hide lane owns"):
            A.validate_records(
                [replace(records[0], new_value="in_scope"), records[1]], lane=L.CHIAPA_HIDE
            )

    def test_the_survivor_checks_run_after_the_write_and_only_on_it(self, tmp_path: Path) -> None:
        records = lane_records(tmp_path, 0)
        write = A.apply_statement(records, L.CHIAPA_HIDE)
        loop = write.index("END LOOP;")
        for invariant in L.DUPLICATE_SURVIVOR_INVARIANTS:
            at = write.index(f"RAISE EXCEPTION 'Nr 7 duplicate hide: % {invariant.says}', bad;")
            assert at > loop
        assert f"WHERE ({L.EMPTY_ROW_PREMISE_SQL}) IS DISTINCT FROM p.premise;" in write
        undo = A.rollback_statement(records, L.CHIAPA_HIDE)
        assert "site invariant" not in undo
        assert f"WHERE ({L.EMPTY_ROW_PREMISE_SQL}) IS DISTINCT FROM p.premise;" in undo

    def test_the_rename_waits_for_the_hide_both_ways(self, tmp_path: Path) -> None:
        records = lane_records(tmp_path, 1)
        for sql in (
            A.apply_statement(records, L.CHIAPA_NAME),
            A.rollback_statement(records, L.CHIAPA_NAME),
        ):
            assert f"WHERE ({L.DUPLICATES_RETIRED_ONTO_SQL}) IS DISTINCT FROM p.premise;" in sql
            assert f"'duplicates retired onto it: 1, highest id {HIDDEN}'" in sql
            assert "invariant 3, the lane's own" in sql

    def test_every_guard_of_the_hide_has_its_probe(self, tmp_path: Path) -> None:
        cases = {c[0]: c for c in A.probe_cases(lane_records(tmp_path, 0), L.CHIAPA_HIDE, FOREIGN)}
        assert set(cases) == PROBES_OF_THE_HIDE
        for invariant in L.DUPLICATE_SURVIVOR_INVARIANTS:
            _suffix, _name, mutated, says = cases[invariant.probe_suffix]
            assert says == invariant.says
            assert [r.new_value for r in mutated if r.column == "scope_reason"] == [
                invariant.probe_values[0]
            ]

    def test_every_guard_of_the_rename_has_its_probe(self, tmp_path: Path) -> None:
        cases = {c[0] for c in A.probe_cases(lane_records(tmp_path, 1), L.CHIAPA_NAME, FOREIGN)}
        assert cases == {
            "guard1-other-source", "guard2-no-op", "guard2-foreign-column", "guard2-too-long",
            "guard3-foreign-old-value", "guard5-premise", "invariant-lane",
        }  # fmt: skip

    def test_the_probes_pass_when_each_is_refused_by_its_own_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        records = lane_records(tmp_path, 0)
        ProbeProduction(L.CHIAPA_HIDE, records, monkeypatch)
        assert A.cmd_probe_guards(records, tmp_path, L.CHIAPA_HIDE) == 0
        out = capsys.readouterr().out
        assert out.count("refused by its own guard=True") == len(PROBES_OF_THE_HIDE)

    def test_two_invariants_probing_one_column_are_named_apart(self) -> None:
        first, second, _third = L.DUPLICATE_SURVIVOR_INVARIANTS
        unnamed = (replace(first, probe_name=""), replace(second, probe_name=""))
        with pytest.raises(ValueError, match="share one probe name"):
            replace(L.CHIAPA_HIDE, site_invariants=unnamed)
        with pytest.raises(ValueError, match="not a probe name"):
            replace(first, probe_name="Survivor Far")

    def test_the_read_backs_count_what_the_lanes_move(self) -> None:
        hide = L.CHIAPA_HIDE_READBACK
        assert "curated rows retired as a duplicate'" in hide
        assert "retired duplicates whose survivor is retired or not curated" in hide
        assert f"'{L.CHIAPA_HIDE.run_stamp}'" in hide
        name = L.CHIAPA_NAME_READBACK
        assert (
            "visible curated rows sharing their name key with another visible curated row" in name
        )
        assert f"'{L.CHIAPA_NAME.run_stamp}'" in name and f"'{L.NAME_L5.run_stamp}'" not in name


# ------------------------------------------------------------------------ the delivered plans
@needs_plan
class TestTheDeliveredPlans:
    def test_the_hide_is_two_cells_of_the_empty_row(self) -> None:
        records = A.load_records(DELIVERED / "hide" / "PLAN.jsonl")
        assert [(r.site_id, r.column, r.old_value, r.new_value, r.premise) for r in records] == [
            (HIDDEN, "scope_status", None, "retired", L.EMPTY_ROW_PREMISE),
            (HIDDEN, "scope_reason", None, REASON, L.EMPTY_ROW_PREMISE),
        ]

    def test_the_rename_is_two_cells_of_the_kept_row_and_waits_for_the_hide(self) -> None:
        records = A.load_records(DELIVERED / "name" / "PLAN.jsonl")
        waits = L.duplicates_retired_onto([HIDDEN])
        assert [(r.site_id, r.column, r.new_value, r.premise) for r in records] == [
            (KEPT, "name", "Chiapa de Corzo", waits),
            (KEPT, "name_normalized", "chiapa de corzo", waits),
        ]

    def test_the_read_is_the_one_the_plans_rest_on(self) -> None:
        read = C.parse_read((DELIVERED / "READ.jsonl").read_text(encoding="utf-8"))
        hide, rename = C.build(read, NOW)
        for plan in (hide, rename):
            delivered = A.load_records(A.lane_dir(plan.lane) / "PLAN.jsonl")
            assert [(r.column, r.new_value, r.premise) for r in delivered] == [
                (v.column, v.new_value, v.premise) for v in plan.changes
            ]
