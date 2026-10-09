"""Row lanes (D14, 2026-10-08): a lane whose cells are rows of other tables.

`dup-merge-move-<wave>` moves a duplicate's images, content links and name row onto the survivor in one
transaction (`mechanical/rowlane.py`). The plan names each cell by `(table, row id, column)` and the
site it concerns, so the guards of a cell lane are stated per cell here. Each plan-side refusal has its
test; the invariants the transaction proves after the write are evaluated in SQLite (their SQL is
portable) on a state that satisfies them and on one state per way each can fail; every probe is held to
the refusal text the rendered statement raises; and the rendered statements are syntax-checked by
libpg_query when `pglast` is installed (it is in no requirements file: the check skips without it).
"""

from __future__ import annotations

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
from mechanical import plan as P  # noqa: E402
from mechanical import rowlane as R  # noqa: E402

from pipeline.utils.geo import haversine_distance  # noqa: E402

LOSER = "ae2ca7b1-89da-46cb-8924-f9d04dd5da2e"
SURVIVOR = "ce7db300-8777-425d-917a-2f6d9f325b58"
OTHER_LOSER = "3ebb514f-ac4a-4913-b54b-409bcc29eff4"
OTHER_SURVIVOR = "51daf6c9-25d3-4818-8857-0543f1203c57"
FOREIGN_SITE = "8db5555a-a9a3-417b-944c-6ec0c04de0db"
WAVE = "2026-10-10"
PAIRS = (L.MergePair(LOSER, SURVIVOR), L.MergePair(OTHER_LOSER, OTHER_SURVIVOR, 2500))
LANE = L.dup_merge_move_lane(WAVE, PAIRS)
EVIDENCE = ({"source": "test", "quote": "q"},)
PREMISE = "Banias | wikidata_qid=Q606295 | survivor Caesarea Philippi | wikidata_qid=Q606295"


def cell(
    table: str = "wiki_images",
    row_id: str = "11",
    column: str = "site_id",
    old: str | None = LOSER,
    new: str | None = SURVIVOR,
    *,
    site: str = LOSER,
    **over: Any,
) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": site,
        "site_name": "Banias",
        "old_value": old,
        "new_value": new,
        "rule": "d14-dup-merge-move",
        "condition": "id = 11",
        "reason": "the image moves to the survivor",
        "evidence": EVIDENCE,
        "premise": PREMISE,
        "column": column,
        "table": table,
        "row_id": row_id,
    }
    base.update(over)
    return A.ChangeRecord(**base)


def full_plan() -> list[A.ChangeRecord]:
    """An image (with a demoted hero), a content link and the name row of one loser."""
    return [
        cell("wiki_images", "11", "site_id"),
        cell("wiki_images", "11", "is_hero", "true", "false"),
        cell("site_content_links", "7", "site_id"),
        cell("unified_site_names", "5", "name_type", "label", "alias"),
        cell("unified_site_names", "5", "site_id"),
    ]


def render(records: list[A.ChangeRecord], **kw: Any) -> str:
    return A.render_transaction(records, site_ids={r.site_id for r in records}, lane=LANE, **kw)


# ---------------------------------------------------------------------------------- the shape
class TestTheLaneShape:
    def test_the_row_cells_are_the_five_the_move_writes(self) -> None:
        assert [c.qualified for c in LANE.row_cells] == [
            "wiki_images.site_id",
            "wiki_images.is_hero",
            "site_content_links.site_id",
            "unified_site_names.site_id",
            "unified_site_names.name_type",
        ]
        assert LANE.columns == tuple(c.qualified for c in LANE.row_cells)

    def test_a_row_cell_names_a_row_keyed_table(self) -> None:
        with pytest.raises(ValueError, match="not a row-keyed table"):
            L.RowCell("unified_sites", L.Column("name", "text"))
        with pytest.raises(ValueError, match="not a row-keyed table"):
            L.RowCell("card_stats", L.Column("mystery", "integer"))

    def test_the_new_cell_types_are_closed_in(self) -> None:
        assert {"uuid", "boolean"} <= L.CELL_TYPES
        with pytest.raises(ValueError, match="is not one of"):
            L.Column("x", "money")

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"column": "country", "max_chars": 100}, "names its cells in `row_cells`"),
            ({"cells": L.PARENT_CELLS}, "names its cells in `row_cells`"),
            ({"write_invariant": L.Residual("curated rows", "true")}, "checks `row_invariants`"),
            ({"site_invariants": L.parent_invariants()}, "checks `row_invariants`"),
            ({"reverses_journal": True}, "checks `row_invariants`"),
            ({"target": L.CARD_STATS}, "curated-scope predicate reads unified_sites"),
            ({"row_cells": (*L.MOVE_CELLS, L.MOVE_CELLS[0])}, "appears twice"),
            ({"row_invariants": (*LANE.row_invariants, LANE.row_invariants[0])}, "share one probe"),
        ],
    )
    def test_a_row_lane_that_breaks_its_shape_is_refused(
        self, change: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            replace(LANE, **change)

    def test_row_invariants_belong_to_a_row_lane(self) -> None:
        with pytest.raises(ValueError, match="row invariants"):
            replace(L.SCOPE, row_invariants=LANE.row_invariants)

    @pytest.mark.parametrize(
        ("says", "bad_sql", "probe"),
        [
            ("it's wrong", "FROM {plan} q", "a-b"),
            ("fine", "FROM plan q", "a-b"),
            ("fine", "FROM {plan} q $$", "a-b"),
            ("fine", "FROM {plan} q", "Not A Probe"),
        ],
    )
    def test_a_row_invariant_is_spliced_safely(self, says: str, bad_sql: str, probe: str) -> None:
        with pytest.raises(ValueError):
            L.RowInvariant(says, bad_sql, probe)

    def test_the_cells_of_a_row_are_looked_up_by_table_and_column(self) -> None:
        assert LANE.row_cell("wiki_images", "is_hero").column.sql_type == "boolean"
        with pytest.raises(ValueError, match="not a cell this lane writes"):
            LANE.row_cell("wiki_images", "filename")
        with pytest.raises(ValueError, match="not a cell this lane writes"):
            LANE.row_cell("site_content_links", "is_hero")

    def test_the_change_key_names_the_cell_and_the_reversal_has_its_own(self) -> None:
        assert (
            LANE.row_change_key("wiki_images", "11", "site_id")
            == f"dup-merge-move-{WAVE}:wiki_images:11:site_id"
        )
        assert (
            LANE.row_rollback_change_key("wiki_images", "11", "site_id")
            == f"dup-merge-move-{WAVE}-rollback:wiki_images:11:site_id"
        )

    def test_where_a_row_lane_writes_is_every_qualified_column(self) -> None:
        assert L.written_where(LANE) == ", ".join(LANE.columns)
        outside = L.outside(LANE, "l.")
        assert outside.startswith("(l.table_name || '.' || l.column_name NOT IN (")
        assert "'wiki_images.site_id'" in outside and "'unified_site_names.name_type'" in outside


# ----------------------------------------------------------------------- the plan-side mirror
class TestThePlanSideMirror:
    def test_a_plan_of_the_five_cells_is_valid(self) -> None:
        A.validate_records(full_plan(), lane=LANE)

    def test_the_reversal_of_a_valid_plan_is_valid(self) -> None:
        A.validate_records(P.reversed_records(full_plan(), LANE), lane=LANE, rollback=True)

    @pytest.mark.parametrize(
        ("records", "message"),
        [
            ([], "empty plan"),
            ([cell(site="nope")], "is not a UUID"),
            ([cell(table=None)], "names its table, its row id and its column"),
            ([cell(row_id=None)], "names its table, its row id and its column"),
            ([cell(column=None)], "names its table, its row id and its column"),
            ([cell(row_id="0")], "is not a row id"),
            ([cell(row_id="07")], "is not a row id"),
            ([cell(row_id="x")], "is not a row id"),
            ([cell(column="filename")], "not a cell this lane writes"),
            ([cell(table="site_content_links", column="is_hero")], "not a cell this lane writes"),
            ([cell(), cell()], "appears twice"),
            ([cell(old="NOT-A-UUID")], "not a lower-case uuid"),
            ([cell(new=SURVIVOR.upper())], "not a lower-case uuid"),
            ([cell(column="is_hero", old="true", new="no")], "not how the database prints"),
            ([cell(old=SURVIVOR, new=SURVIVOR)], "old and new are both"),
            ([cell(old=None)], "not a column this lane fills"),
            ([cell(new=None)], "never clears a column"),
            (
                [cell("unified_site_names", "5", "name_type", "label", "nickname")],
                "not a value the",
            ),
            ([cell(column="is_hero", old="false", new="true")], "not a value the"),
            ([cell(premise=None)], "carries no premise"),
            ([cell(reason="")], "not auditable"),
            ([cell(evidence=())], "not auditable"),
            ([cell(journal_id=3)], "false assurance"),
            ([cell(), cell("site_content_links", "7", premise="another")], "two premises"),
        ],
    )
    def test_each_refusal(self, records: list[A.ChangeRecord], message: str) -> None:
        with pytest.raises(P.PlanError, match=message):
            A.validate_records(records, lane=LANE)

    def test_another_source_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="writes 'ancient_nerds' only"):
            A.validate_records(full_plan(), lane=LANE, source="geonames")

    def test_a_name_type_may_be_null_where_the_lane_fills_it(self) -> None:
        A.validate_records([cell("unified_site_names", "5", "name_type", None, "alias")], lane=LANE)

    def test_a_premise_nobody_checks_is_refused(self) -> None:
        bare = replace(LANE, premise_sql=None)
        with pytest.raises(P.PlanError, match="false assurance"):
            A.validate_records([cell()], lane=bare)


# ------------------------------------------------------------------------------ the statement
class TestTheStatement:
    def test_one_transaction_with_its_guards_in_order(self) -> None:
        sql = render(full_plan())
        order = [
            "BEGIN;",
            "SET LOCAL lock_timeout = '10s';",
            f"CREATE TEMP TABLE {LANE.plan_table} (",
            "-- scope guard 1:",
            "-- scope guard 2:",
            "-- scope guard 3:",
            "-- scope guard 4:",
            "-- scope guard 5:",
            "FOR r IN SELECT * FROM",
            "-- invariant 1:",
            "-- invariant 2:",
            "-- row invariant:",
            "COMMIT;",
        ]
        positions = [sql.index(marker) for marker in order]
        assert positions == sorted(positions)
        assert (
            sql.count("\nCOMMIT;\n") == 1
            and "$$" not in sql.partition("DO $$")[2].partition("END $$;")[0]
        )

    def test_every_cell_goes_through_the_primitive_keyed_by_the_row_id(self) -> None:
        sql = render(full_plan())
        assert "apply_remediation_change(" in sql
        assert "r.table_name, r.column_name, 'id', r.row_id," in sql
        assert "r.change_key, 'two_source', r.evidence, r.site_id);" in sql
        assert "ORDER BY table_name, row_id::integer, column_name LOOP" in sql
        assert f"'dup-merge-move-{WAVE}:wiki_images:11:is_hero'" in sql
        assert f"'{WAVE}_mechanical-dup-merge-move'" in sql

    def test_guard_1_reads_the_site_and_the_owner_of_each_row_in_its_own_table(self) -> None:
        sql = render(full_plan())
        guard1 = sql.partition("-- scope guard 1:")[2].partition("-- scope guard 2:")[0]
        for table in ("wiki_images", "site_content_links", "unified_site_names"):
            assert (
                f"WHEN '{table}' THEN EXISTS (SELECT 1 FROM {table} t JOIN unified_sites o ON "
                "o.id = t.site_id WHERE t.id = p.row_id::integer AND o.source_id = "
                "'ancient_nerds')" in guard1
            )
        assert "u.id IS NULL OR u.source_id <> 'ancient_nerds'" in guard1

    def test_guard_3_reads_each_cell_in_its_column_s_own_type(self) -> None:
        sql = render(full_plan())
        guard3 = sql.partition("-- scope guard 3:")[2].partition("-- scope guard 4:")[0]
        assert (
            "WHEN 'wiki_images.site_id' THEN (SELECT t.site_id FROM wiki_images t WHERE t.id = p.row_id::integer) IS DISTINCT FROM p.old_value::uuid"
            in guard3
        )
        assert "p.old_value::boolean" in guard3
        assert "p.old_value::character varying" in guard3
        assert "ELSE true END" in guard3

    def test_guard_4_owns_the_alias_and_the_demotion_and_nothing_else(self) -> None:
        sql = render(full_plan())
        guard4 = sql.partition("-- scope guard 4:")[2].partition("-- scope guard 5:")[0]
        assert "WHEN 'wiki_images.is_hero' THEN p.new_value NOT IN ('false')" in guard4
        assert "WHEN 'unified_site_names.name_type' THEN p.new_value NOT IN ('alias')" in guard4
        assert "WHEN 'wiki_images.site_id'" not in guard4

    def test_guard_5_conditions_the_write_on_the_premise_once_per_site(self) -> None:
        sql = render(full_plan())
        guard5 = sql.partition("-- scope guard 5:")[2].partition("-- the only writer")[0]
        assert "(SELECT DISTINCT site_id, premise FROM _dup_merge_move_plan) p" in guard5
        assert "IS DISTINCT FROM p.premise" in guard5
        assert "CASE CAST(u.id AS text) WHEN '" + LOSER + "' THEN '" + SURVIVOR + "'" in guard5

    def test_the_journal_check_reads_the_site_the_cell_concerns(self) -> None:
        sql = render(full_plan())
        assert "OR l.site_id_ref IS DISTINCT FROM p.site_id;" in sql
        assert "this run stamp journalled % row(s) outside wiki_images.site_id" in sql

    def test_the_row_invariants_run_on_the_write_only(self) -> None:
        write = render(full_plan())
        undo = render(P.reversed_records(full_plan(), LANE), rollback=True)
        for invariant in LANE.row_invariants:
            assert f"RAISE EXCEPTION 'D14 duplicate move: % {invariant.says}', bad;" in write
            assert invariant.says not in undo
        assert write.count("-- row invariant:") == 5 and "-- row invariant:" not in undo

    def test_the_reversal_has_its_own_stamp_keys_and_ownership(self) -> None:
        undo = render(P.reversed_records(full_plan(), LANE), rollback=True)
        assert f"'{WAVE}_mechanical-dup-merge-move-rollback'" in undo
        assert f"'dup-merge-move-{WAVE}-rollback:wiki_images:11:site_id'" in undo
        guard4 = undo.partition("-- scope guard 4:")[2].partition("-- scope guard 5:")[0]
        assert "every planned cell undos a value this lane owns" in undo
        assert "THEN p.old_value NOT IN ('alias')" in guard4

    def test_probes_may_render_what_the_plan_side_mirror_refuses(self) -> None:
        corrupted = [cell(column="probe_foreign_column")]
        with pytest.raises(P.PlanError):
            render(corrupted)
        assert "'wiki_images.probe_foreign_column'" not in render(corrupted, validate=False)

    def test_the_statement_names_the_curated_scope_and_its_residual(self) -> None:
        sql = render(full_plan())
        assert "retired duplicates still holding an image or a content link" in sql
        assert "planned cells now holding the new value" in sql

    def test_an_empty_plan_is_not_rendered(self) -> None:
        with pytest.raises(P.PlanError, match="no rows"):
            render([])

    def test_a_value_that_would_end_the_do_block_is_refused(self) -> None:
        hostile = replace(cell(), reason="why $$ and more")
        # the reason is a quoted literal inside the INSERT, outside the DO block: harmless there
        assert "why $$ and more" in render([hostile])
        poisoned = replace(LANE, premise_sql="'x' || '$$'")
        with pytest.raises(P.PlanError, match="would end the DO block"):
            A.render_transaction([cell()], site_ids={LOSER}, lane=poisoned, validate=False)


class TestTheSyntaxInPostgres:
    """libpg_query parses the rendered statements: a typo in the generated SQL is found here rather
    than in the rehearsal on production. Skipped without `pglast`, which is in no requirements file
    (`pip install pglast`)."""

    @pytest.fixture(autouse=True)
    def parser(self) -> Any:
        self.pglast = pytest.importorskip(
            "pglast", reason="pglast (libpg_query) is installed by hand"
        )
        return self.pglast

    def problems(self, sql: str) -> list[str]:
        import re

        pglast = self.pglast

        text = "\n".join(line for line in sql.splitlines() if not line.startswith("\\"))
        found = []
        match = re.search(r"DO \$\$\n(.*?)\nEND \$\$;", text, re.S)
        if match:
            body = "DECLARE\n" + match.group(1).split("DECLARE\n", 1)[1] + "\nEND"
            text = text.replace(match.group(0), "SELECT 1;")
            try:
                pglast.parse_plpgsql(
                    "CREATE FUNCTION f() RETURNS void LANGUAGE plpgsql AS $x$\n" + body + "\n$x$;"
                )
            except Exception as exc:  # noqa: BLE001 - any parser error is the finding
                found.append(f"plpgsql: {exc}")
            for stmt in re.findall(r"SELECT count\(\*\) INTO bad(.*?);\n", body, re.S):
                try:
                    pglast.parse_sql("SELECT count(*) " + stmt.strip() + ";")
                except Exception as exc:  # noqa: BLE001
                    found.append(f"select: {exc}: {stmt[:100]}")
        try:
            pglast.parse_sql(text)
        except Exception as exc:  # noqa: BLE001
            found.append(f"sql: {exc}")
        return found

    def test_the_move_statement_and_its_reversal_parse(self) -> None:
        assert self.problems(render(full_plan())) == []
        assert self.problems(render(P.reversed_records(full_plan(), LANE), rollback=True)) == []

    def test_the_retire_and_parent_lanes_parse(self) -> None:
        retire = L.dup_merge_retire_lane(WAVE, PAIRS)
        cells = [
            cell(column="scope_status", old=None, new="retired", table=None, row_id=None),
            cell(
                column="scope_reason",
                old=None,
                new=f"duplicate_of:{SURVIVOR}",
                table=None,
                row_id=None,
            ),
        ]
        assert self.problems(A.render_transaction(cells, site_ids={LOSER}, lane=retire)) == []
        parent = L.parent_lane(WAVE)
        child = [cell(column="parent_site_id", old=None, new=SURVIVOR, table=None, row_id=None)]
        assert self.problems(A.render_transaction(child, site_ids={LOSER}, lane=parent)) == []

    def test_the_read_backs_parse(self) -> None:
        for lane in (LANE, L.dup_merge_retire_lane(WAVE, PAIRS), L.parent_lane(WAVE)):
            text = A.readback_for(lane).replace("\\pset footer off", "")
            assert self.problems("BEGIN;\n" + text) == []

    def test_the_checker_finds_a_typo(self) -> None:
        assert self.problems(render(full_plan()).replace("END LOOP;", "END LOOPS;"))


# ------------------------------------------------------------------- the invariants in SQLite
def sqlite_world() -> sqlite3.Connection:
    """The tables the row invariants read, with PostGIS's two point functions and the name key's two
    (`unaccent` is the identity here, `left` the first characters)."""
    db = sqlite3.connect(":memory:")
    db.create_function("ST_MakePoint", 2, lambda lon, lat: f"{lon} {lat}")

    def sphere(a: str, b: str) -> float:
        (lon1, lat1), (lon2, lat2) = (map(float, p.split()) for p in (a, b))
        return 1000.0 * haversine_distance(lat1, lon1, lat2, lon2)

    db.create_function("ST_DistanceSphere", 2, sphere)
    db.create_function("unaccent", 1, lambda text: text)
    db.create_function("left", 2, lambda text, n: text[:n])
    db.executescript(
        """
        CREATE TABLE unified_sites (id TEXT PRIMARY KEY, name TEXT, source_id TEXT,
            scope_status TEXT, scope_reason TEXT, lat REAL, lon REAL);
        CREATE TABLE wiki_images (id INTEGER PRIMARY KEY, site_id TEXT, is_hero INTEGER,
            is_excluded INTEGER);
        CREATE TABLE unified_site_names (id INTEGER PRIMARY KEY, site_id TEXT, name TEXT,
            name_normalized TEXT, name_type TEXT);
        CREATE TABLE _dup_merge_move_plan (site_id TEXT, table_name TEXT, row_id TEXT,
            column_name TEXT, old_value TEXT, new_value TEXT);
        """
    )
    return db


def site(
    db: sqlite3.Connection, site_id: str, name: str, lat: float, lon: float, **over: Any
) -> None:
    row = {"source_id": "ancient_nerds", "scope_status": None, "scope_reason": None, **over}
    db.execute(
        "INSERT INTO unified_sites VALUES (?, ?, ?, ?, ?, ?, ?)",
        (site_id, name, row["source_id"], row["scope_status"], row["scope_reason"], lat, lon),
    )


def plan(db: sqlite3.Connection, *cells: tuple[str, str, str, str, str, str]) -> None:
    """Plan rows `(site, table, row id, column, old, new)`."""
    db.executemany("INSERT INTO _dup_merge_move_plan VALUES (?, ?, ?, ?, ?, ?)", list(cells))


def bad(db: sqlite3.Connection, probe: str) -> int:
    invariant = next(i for i in LANE.row_invariants if i.probe == probe)
    sql = "SELECT count(*) " + invariant.bad_sql.replace("{plan}", LANE.plan_table)
    return int(db.execute(sql).fetchone()[0])


BANIAS = (33.2486, 35.6944)
CAESAREA_NEAR = (33.2472, 35.6939)  # about 160 m
TIKAL = (17.2220, -89.6237)


def world(
    *, survivor_at: tuple[float, float] = CAESAREA_NEAR, **survivor: Any
) -> sqlite3.Connection:
    db = sqlite_world()
    site(db, LOSER, "Banias", *BANIAS)
    site(db, SURVIVOR, "Caesarea Philippi", *survivor_at, **survivor)
    plan(db, (LOSER, "wiki_images", "11", "site_id", LOSER, SURVIVOR))
    return db


class TestTheInvariantsInSQL:
    def test_a_move_onto_the_named_near_curated_survivor_breaks_none(self) -> None:
        db = world()
        db.execute("UPDATE wiki_images SET site_id = ?", (SURVIVOR,))
        db.execute("INSERT INTO wiki_images VALUES (11, ?, 0, 0)", (SURVIVOR,))
        db.execute(
            "INSERT INTO unified_site_names VALUES (5, ?, 'Banias', 'banias', 'alias')", (SURVIVOR,)
        )
        for invariant in LANE.row_invariants:
            assert bad(db, invariant.probe) == 0, invariant.says

    def test_a_destination_that_is_no_curated_site_is_counted(self) -> None:
        assert bad(world(source_id="geonames"), "dest-curated") == 1
        assert bad(world(), "dest-curated") == 0
        db = world()
        db.execute("UPDATE _dup_merge_move_plan SET new_value = ?", (FOREIGN_SITE,))
        assert bad(db, "dest-curated") == 1

    def test_a_destination_that_is_retired_is_counted(self) -> None:
        assert bad(world(scope_status="retired", scope_reason="x"), "dest-shown") == 1
        assert bad(world(scope_status="pending", scope_reason="x"), "dest-shown") == 0
        assert bad(world(), "dest-shown") == 0

    def test_a_destination_other_than_the_named_survivor_is_counted(self) -> None:
        db = world()
        site(db, OTHER_SURVIVOR, "Amathus", *CAESAREA_NEAR)
        db.execute("UPDATE _dup_merge_move_plan SET new_value = ?", (OTHER_SURVIVOR,))
        assert bad(db, "dest-named-near") == 1

    def test_a_site_the_lane_names_no_pair_for_is_counted(self) -> None:
        db = world()
        db.execute("UPDATE _dup_merge_move_plan SET site_id = ?", (FOREIGN_SITE,))
        site(db, FOREIGN_SITE, "Elsewhere", *BANIAS)
        assert bad(db, "dest-named-near") == 1

    def test_the_default_limit_is_two_thousand_metres(self) -> None:
        # Banias to Tikal is thousands of kilometres; 1.9 km north of Banias is inside, 2.1 km outside
        inside = world(survivor_at=(BANIAS[0] + 0.0171, BANIAS[1]))
        outside = world(survivor_at=(BANIAS[0] + 0.0189, BANIAS[1]))
        assert bad(inside, "dest-named-near") == 0
        assert bad(outside, "dest-named-near") == 1

    def test_a_pair_with_its_own_limit_may_lie_further_and_the_others_may_not(self) -> None:
        db = sqlite_world()
        site(db, OTHER_LOSER, "Ancient Amathunta", 34.7125, 33.1419)
        site(db, OTHER_SURVIVOR, "Amathus", 34.7125 + 0.0189, 33.1419)  # 2.1 km: inside 2,500 m
        plan(db, (OTHER_LOSER, "wiki_images", "20", "site_id", OTHER_LOSER, OTHER_SURVIVOR))
        assert bad(db, "dest-named-near") == 0
        far = replace(
            LANE, row_invariants=L.move_invariants([L.MergePair(OTHER_LOSER, OTHER_SURVIVOR)])
        )
        invariant = next(i for i in far.row_invariants if i.probe == "dest-named-near")
        sql = "SELECT count(*) " + invariant.bad_sql.replace("{plan}", LANE.plan_table)
        assert db.execute(sql).fetchone()[0] == 1

    def test_two_live_heroes_on_a_touched_site_are_counted_and_an_excluded_one_is_not(self) -> None:
        db = world()
        db.executemany(
            "INSERT INTO wiki_images VALUES (?, ?, ?, ?)",
            [(1, SURVIVOR, 1, 0), (2, SURVIVOR, 1, 0)],
        )
        assert bad(db, "hero-cell") == 1
        db.execute("UPDATE wiki_images SET is_excluded = 1 WHERE id = 2")
        assert bad(db, "hero-cell") == 0
        db.execute("UPDATE wiki_images SET is_excluded = NULL, is_hero = NULL WHERE id = 2")
        assert bad(db, "hero-cell") == 0

    def test_the_loser_is_a_touched_site_too(self) -> None:
        db = world()
        db.executemany("INSERT INTO wiki_images VALUES (?, ?, 1, 0)", [(1, LOSER), (2, LOSER)])
        assert bad(db, "hero-cell") == 1

    def test_a_loser_whose_name_is_not_a_name_of_its_survivor_is_counted(self) -> None:
        db = world()
        assert bad(db, "alias-cells") == 1
        db.execute(
            "INSERT INTO unified_site_names VALUES (5, ?, 'Banias', 'banias', 'alias')", (SURVIVOR,)
        )
        assert bad(db, "alias-cells") == 0

    def test_the_alias_is_compared_by_the_loser_s_name_key(self) -> None:
        db = world()
        db.execute(
            "INSERT INTO unified_site_names VALUES (5, ?, 'Paneas', 'paneas', 'alias')", (SURVIVOR,)
        )
        assert bad(db, "alias-cells") == 1


# ------------------------------------------------------------------------------------- probes
FOREIGN = {
    "table": "wiki_images",
    "row_id": "99",
    "site_id": FOREIGN_SITE,
    "name": "Chiapa",
    "premise": "Chiapa | | survivor ",
}


class TestTheProbes:
    def cases(self, records: list[A.ChangeRecord] | None = None) -> dict[str, Any]:
        return {c[0]: c for c in A.probe_cases(records or full_plan(), LANE, FOREIGN)}

    def test_every_guard_and_every_invariant_has_its_probe(self) -> None:
        assert list(self.cases()) == [
            "guard3-foreign-old-value",
            "guard2-no-op",
            "guard2-foreign-column",
            "guard2-too-long",
            "guard1-other-source",
            "guard4-not-owned",
            "guard5-premise",
            "invariant-dest-curated",
            "invariant-dest-shown",
            "invariant-dest-named-near",
            "invariant-hero-cell",
            "invariant-alias-cells",
        ]
        assert A.unprobed_invariants(full_plan(), LANE) == []

    def test_every_probe_names_a_refusal_its_statement_raises(self) -> None:
        for suffix, _name, mutated, expected in self.cases().values():
            sql = A.render_transaction(
                mutated, run_stamp=f"{LANE.probe_run_stamp}-{suffix}",
                site_ids={r.site_id for r in mutated}, validate=False, lane=LANE,
            )  # fmt: skip
            says = expected.replace("ancient_nerds", "%")  # guard 1 names its source as an argument
            assert f"RAISE EXCEPTION '{LANE.label}: % {says}'" in sql, suffix

    def test_a_boolean_first_cell_is_not_the_one_corrupted(self) -> None:
        records = [cell("wiki_images", "11", "is_hero", "true", "false"), *full_plan()[2:]]
        old = self.cases(records)["guard3-foreign-old-value"][2]
        assert old[0].old_value == "true" and old[1].old_value != "label"
        assert old[1].old_value == "00000000-0000-4000-8000-0000000d1e5e"

    def test_the_destination_probes_send_the_loser_s_moves_to_a_row_of_their_kind(self) -> None:
        for suffix, destination in (
            ("dest-curated", R.GEONAMES_ROW),
            ("dest-shown", R.RETIRED_ROW),
            ("dest-named-near", R.FAR_ROW),
        ):
            mutated = self.cases()[f"invariant-{suffix}"][2]
            moves = [r for r in mutated if r.column == "site_id"]
            assert moves and {r.new_value for r in moves} == {destination}
            assert [r for r in mutated if r.column != "site_id"] == [
                r for r in full_plan() if r.column != "site_id"
            ]

    def test_the_hero_probe_drops_the_demotion_and_the_alias_probe_the_name_row(self) -> None:
        hero = self.cases()["invariant-hero-cell"][2]
        assert len(hero) == 4 and not [r for r in hero if r.column == "is_hero"]
        alias = self.cases()["invariant-alias-cells"][2]
        assert [r.table for r in alias] == ["wiki_images", "wiki_images", "site_content_links"]

    def test_a_plan_without_the_cells_a_probe_needs_names_the_invariants_it_cannot_probe(
        self,
    ) -> None:
        records = [cell("site_content_links", "7", "site_id")]
        suffixes = list(self.cases(records))
        assert "invariant-dest-curated" in suffixes and "invariant-hero-cell" not in suffixes
        assert A.unprobed_invariants(records, LANE) == [
            i.says for i in LANE.row_invariants if i.probe in ("hero-cell", "alias-cells")
        ]
        assert (
            A.unprobed_invariants(
                [cell("unified_site_names", "5", "name_type", "label", "alias")], LANE
            )
            != []
        )

    def test_a_single_cell_plan_cannot_drop_its_only_cell(self) -> None:
        assert (
            R.drop_first([cell("wiki_images", "11", "is_hero", "true", "false")], "is_hero", None)
            is None
        )

    def test_the_foreign_row_replaces_the_first_non_boolean_cell(self) -> None:
        mutated = self.cases()["guard1-other-source"][2]
        assert (mutated[0].site_id, mutated[0].row_id, mutated[0].table) == (
            FOREIGN_SITE,
            "99",
            "wiki_images",
        )
        assert mutated[0].premise == FOREIGN["premise"] and mutated[1:] == full_plan()[1:]


# ------------------------------------------------------------------------------ the read-backs
class TestTheReadBacks:
    def test_the_assert_reads_the_journal_and_the_cells_row_for_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []

        def rows(sql: str) -> list[list[str]]:
            seen.append(sql)
            return [
                ["journal rows for this run stamp", "5"],
                ["planned cells now holding the planned new value", "5"],
                ["planned cells with no journal row for this run stamp", "0"],
                [f"journal rows for this run outside {L.written_where(LANE)}", "0"],
            ]

        monkeypatch.setattr(A, "read_rows", rows)
        got = A.assert_the_write_landed(full_plan(), lane=LANE)
        assert got["journal rows for this run stamp"] == 5
        assert "('wiki_images', '11', 'site_id', 'ce7db300" in seen[0]
        assert (
            "WHEN 'wiki_images.site_id' THEN (SELECT t.site_id FROM wiki_images t WHERE t.id = p.row_id::integer) IS NOT DISTINCT FROM p.new_value::uuid"
            in seen[0]
        )

    @pytest.mark.parametrize(
        ("metric", "wrong"),
        [
            ("journal rows for this run stamp", "4"),
            ("planned cells now holding the planned new value", "4"),
            ("planned cells with no journal row for this run stamp", "1"),
            (f"journal rows for this run outside {L.written_where(LANE)}", "1"),
        ],
    )
    def test_a_read_back_that_disagrees_with_the_plan_raises(
        self, monkeypatch: pytest.MonkeyPatch, metric: str, wrong: str
    ) -> None:
        good = {
            "journal rows for this run stamp": "5",
            "planned cells now holding the planned new value": "5",
            "planned cells with no journal row for this run stamp": "0",
            f"journal rows for this run outside {L.written_where(LANE)}": "0",
        }
        monkeypatch.setattr(
            A, "read_rows", lambda sql: [[k, wrong if k == metric else v] for k, v in good.items()]
        )
        with pytest.raises(P.PlanError, match="disagrees with the plan"):
            A.assert_the_write_landed(full_plan(), lane=LANE)

    def test_the_rollback_rehearsal_asks_for_the_written_values(self) -> None:
        sql = A.rollback_rehearsal_reads(full_plan(), LANE)
        assert "WITH planned(table_name, row_id, column_name, written)" in sql
        assert "p.written::uuid" in sql and "temp table _dup_merge_move_plan left behind" in sql

    def test_the_move_read_back_counts_what_must_not_change(self) -> None:
        text = A.readback_for(LANE)
        for metric in (
            "wiki_images rows of curated sites",
            "site_content_links rows of curated sites",
            "unified_site_names rows of curated sites",
            "curated sites with more than one live hero",
            "retired duplicates still holding an image or a content link",
            "retired duplicates whose name is not among the names of their survivor",
            "journal rows for this run on non-curated sites",
            "journal rows for this run with no site_id_ref",
        ):
            assert f"'{metric}'" in text, metric
        assert "site_id_ref of another site" not in text

    def test_the_post_commit_reads_hold_the_row_lane_s_journal_identity(self) -> None:
        sql = A.post_commit_reads(LANE, run_stamp=LANE.run_stamp)
        assert "planned cells now holding the new value" in sql and "p.row_pk::integer" in sql

    def test_the_cell_lane_read_back_is_what_it_was(self) -> None:
        text = A.readback_for(L.SCOPE)
        assert "journal rows for this run with a site_id_ref of another site" in text
        assert "journal rows for this run on non-curated rows" in text


# ------------------------------------------------------------------------------ the plan files
class TestThePlanRecord:
    def verdict(self, **over: Any) -> P.Verdict:
        base: dict[str, Any] = {
            "site_id": LOSER, "site_name": "Banias", "ok": True, "old_value": LOSER,
            "new_value": SURVIVOR, "rule": "d14-dup-merge-move", "reason": "", "note": "n",
            "phase3": False, "finding_test_id": LANE.test_id, "evidence": EVIDENCE,
            "premise": PREMISE, "column": "site_id", "table": "wiki_images", "row_id": "11",
        }  # fmt: skip
        return P.Verdict(**{**base, **over})

    def test_the_line_names_the_row_the_cell_and_the_lane(self) -> None:
        plan = P.Plan(changes=(self.verdict(),), skipped=(), lane=LANE)
        record = P.plan_record(plan.changes[0], plan)
        assert (record["row_table"], record["row_id"], record["column"]) == (
            "wiki_images",
            "11",
            "site_id",
        )
        assert record["change_key"] == f"dup-merge-move-{WAVE}:wiki_images:11:site_id"
        assert record["premise"] == PREMISE and "premise_sql" not in record
        assert record["site_id"] == LOSER and record["run_stamp"] == LANE.run_stamp

    def test_a_change_without_its_row_is_refused(self) -> None:
        plan = P.Plan(changes=(self.verdict(row_id=None),), skipped=(), lane=LANE)
        with pytest.raises(P.PlanError, match="names its table, row and column"):
            P.plan_record(plan.changes[0], plan)

    def test_a_change_without_its_premise_is_refused(self) -> None:
        plan = P.Plan(changes=(self.verdict(premise=None),), skipped=(), lane=LANE)
        with pytest.raises(P.PlanError, match="needs the site's premise"):
            P.plan_record(plan.changes[0], plan)

    def test_the_plan_file_loads_back_into_the_records_it_came_from(self, tmp_path: Path) -> None:
        plan = P.Plan(
            changes=tuple(self.verdict(row_id=str(i)) for i in (11, 12)), skipped=(), lane=LANE
        )
        path = tmp_path / "PLAN.jsonl"
        P.write_plan_jsonl(plan, path)
        loaded = A.load_records(path)
        assert [(r.table, r.row_id, r.column, r.site_id) for r in loaded] == [
            ("wiki_images", "11", "site_id", LOSER),
            ("wiki_images", "12", "site_id", LOSER),
        ]
        sql = A.apply_statement(loaded, LANE)
        assert A.rollback_statement(loaded, LANE) != sql and "rollback" in A.rollback_statement(
            loaded, LANE
        )

    def test_the_apply_and_the_rollback_are_pinned_to_the_plan(self, tmp_path: Path) -> None:
        plan = P.Plan(changes=(self.verdict(),), skipped=(), lane=LANE)
        path = tmp_path / "PLAN.jsonl"
        P.write_plan_jsonl(plan, path)
        P.write_rollback_sql(plan, tmp_path / "ROLLBACK.sql", plan_path=path)
        records = A.load_records(path)
        assert A.emit(records, tmp_path, LANE, plan_path=path) == 1
        text = (tmp_path / "APPLY.sql").read_text(encoding="utf-8")
        assert text.startswith("-- plan sha256 ") and "dup-merge-move-" + WAVE in text


# ------------------------------------------------------------------------------ the probe run
from tests.remediation.test_mechanical import ProbeProduction  # noqa: E402


class TestTheProbeRun:
    """`--probe-guards` against a production that refuses every probe the way its guard says."""

    def production(self, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> ProbeProduction:
        monkeypatch.setattr(R, "psql_json_reader", lambda: lambda sql: [FOREIGN])
        return ProbeProduction(LANE, full_plan(), monkeypatch, foreign=FOREIGN, **kw)

    def test_every_probe_is_proven_when_its_own_guard_refuses_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.production(monkeypatch)
        assert A.cmd_probe_guards(full_plan(), tmp_path, LANE) == 0
        out = capsys.readouterr().out
        assert out.count("refused by its own guard=True") == 12 and "not probed" not in out

    def test_a_probe_another_guard_refuses_is_a_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        wrong = (A.PSQL_SCRIPT_ERROR, f"ERROR:  {LANE.label}: 1 {A.GUARD2_SAYS}")
        self.production(monkeypatch, answers={"invariant-hero-cell": wrong})
        assert A.cmd_probe_guards(full_plan(), tmp_path, LANE) == 1
        out = capsys.readouterr().out
        assert "!! row invariant - touched site(s) end with more than one live hero" in out
        assert "the guard did not refuse this probe itself" in out

    def test_a_probe_that_leaves_a_journal_row_is_a_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.production(monkeypatch, left={"invariant-alias-cells": 1})
        assert A.cmd_probe_guards(full_plan(), tmp_path, LANE) == 1

    def test_a_plan_that_cannot_carry_a_probe_says_so_and_still_proves_the_rest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        records = full_plan()[2:4]  # a content link and a name_type cell: no hero, no names move
        monkeypatch.setattr(
            R, "psql_json_reader", lambda: lambda sql: [{**FOREIGN, "table": "site_content_links"}]
        )
        ProbeProduction(
            LANE, records, monkeypatch, foreign={**FOREIGN, "table": "site_content_links"}
        )
        assert A.cmd_probe_guards(records, tmp_path, LANE) == 0
        assert "not probed: the plan writes no cell it could corrupt" in capsys.readouterr().out

    def test_the_foreign_row_is_read_from_the_first_cell_s_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[str] = []
        monkeypatch.setattr(
            R, "psql_json_reader", lambda: lambda sql: asked.append(sql) or [FOREIGN]
        )
        assert R.foreign_row(LANE, "site_content_links") == FOREIGN
        assert "FROM site_content_links t JOIN unified_sites u ON u.id = t.site_id" in asked[0]
        assert "u.source_id <> 'ancient_nerds'" in asked[0] and LANE.premise_sql in asked[0]

    def test_no_foreign_row_is_a_refusal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(R, "psql_json_reader", lambda: lambda sql: [])
        with pytest.raises(P.PlanError, match="no site_content_links row of a non-curated site"):
            R.foreign_row(LANE, "site_content_links")

    def test_the_interests_list_what_the_plan_touches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[str] = []

        def reader(sql: str) -> list[dict[str, Any]]:
            asked.append(sql)
            return [
                {
                    "site_id": LOSER,
                    "name": "Banias",
                    "images": 3,
                    "heroes": 1,
                    "links": 2,
                    "names": 1,
                }
            ]

        monkeypatch.setattr(R, "psql_json_reader", lambda: reader)
        text = A.verify_interests(full_plan(), LANE)
        assert text.splitlines()[0] == "images heroes links names  site"
        assert "Banias (" + LOSER + ")" in text
        assert LOSER in asked[0] and SURVIVOR in asked[0]
