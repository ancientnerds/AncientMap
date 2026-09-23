"""The card_stats lane recomputes the cards with the generator's own code - and proves it first.

`build_card_stats_plan` is a pure function of an export. The rows below are fabricated in the
export's own shape (`EXPORT_SITES_SQL`); the generator, the stats rules and the empire tagger are
the real ones unless a test injects a stand-in to isolate one rule. The production export is
gitignored bulk: the test that replays it skips with its reason when it is absent.
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

from mechanical import apply as A  # noqa: E402
from mechanical import card_stats as C  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402

from api.cardgame import generator  # noqa: E402

LANE = C.card_stats_lane(C.FIRST_WAVE)
EXPORT_DIR = A.lane_dir(LANE) / "export"
needs_export = pytest.mark.skipif(
    not (EXPORT_DIR / "export.jsonl").exists(),
    reason=f"{EXPORT_DIR} holds no production export (card_stats.py --export, gitignored bulk)",
)
ORDER = ("roman", "byzantine", "greek")
SITE_A = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
SITE_B = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"


def row(site_id: str = SITE_A, **over: Any) -> dict[str, Any]:
    """One exported curated row whose stored card is what the real generator computes for it."""
    base: dict[str, Any] = {
        "id": site_id,
        "name": "a site",
        "source_id": "ancient_nerds",
        "site_type": "Temple complex",
        "period_name": "3000 - 1500 BC",
        "period_start": -2500,
        "period_end": None,
        "description": "A temple.",
        "source_url": "https://en.wikipedia.org/wiki/X",
        "thumbnail_url": "/data/images/x.webp",
        "country": "Malta",
        "lat": 35.869,
        "lon": 14.512,
        "links": [["reference", "web_discovery"]],
        "wiki_images": 4,
        "likes": 0,
        "bookmarks": 0,
        "premise": f"premise-{site_id[:8]}",
        "has_card": True,
    }
    base.update(over)
    return base


def with_stored(rows: list[dict[str, Any]], **stored_over: Any) -> list[dict[str, Any]]:
    """The rows with `stored_*` set to what the real generator computes from them now."""
    computed = C.recompute(rows, ORDER)
    out = []
    for r in rows:
        stats = computed[r["id"]]
        stored = {
            f"stored_{c}": (C.cell_text(c, stats[c]) if c == "empires" else stats[c])
            for c in C.COLUMNS
        }
        stored.update(stored_over.get(r["id"], {}))
        out.append({**r, **stored})
    return out


def export(rows: list[dict[str, Any]], journal: tuple[dict[str, Any], ...] = ()) -> C.Export:
    return C.Export(
        sites=tuple(rows),
        journal=journal,
        empire_order=ORDER,
        exported_at="2026-09-23 00:00:00+00",
        sha256="0" * 64,
    )


def jrow(i: int, site: str, column: str, old: str, new: str, table: str = "unified_sites") -> dict:
    return {
        "id": i,
        "row_pk": site,
        "table_name": table,
        "column_name": column,
        "old_value": old,
        "new_value": new,
        "run_stamp": "phase3:batch-0001",
    }


class TestTheLane:
    def test_the_lane_owns_exactly_the_columns_the_generator_writes(self) -> None:
        stats = generator.site_card_stats(
            C.site_namespace(row()),
            combo_counts={},
            content=(0, 0, False),
            wiki_image_count=0,
            engagement=(0, 0),
        )
        assert set(C.COLUMNS) == set(stats), "a column the generator writes is a column we plan"

    def test_the_owned_values_are_the_generator_s_vocabulary(self) -> None:
        from api.cardgame.constants import GROUP_FORTIFICATION, RARITY_NAMES

        assert set(LANE.cell("category_group").allowed_new_values) == set(GROUP_FORTIFICATION)
        assert set(LANE.cell("rarity_tier").allowed_new_values) == {str(t) for t in RARITY_NAMES}

    def test_the_export_reads_the_premise_the_transaction_checks(self) -> None:
        assert f"{C.PREMISE_SQL} AS premise" in C.EXPORT_SITES_SQL
        assert LANE.premise_sql == C.PREMISE_SQL
        assert "READ ONLY" in C.export_script() and "\\set QUIET on" in C.export_script()

    def test_a_wave_is_a_lane_of_its_own(self) -> None:
        other = C.card_stats_lane("2026-09-24")
        assert other.run_stamp != LANE.run_stamp and other.out_dir_name != LANE.out_dir_name
        assert C.card_stats_readback(LANE) is C.card_stats_readback(LANE)


class TestTheExport:
    def test_a_line_of_another_kind_is_refused(self) -> None:
        text = '{"kind": "site", "row": {}}\n{"kind": "snapshot", "row": {"exported_at": "x"}}\n'
        with pytest.raises(P.PlanError, match="kind 'oops'"):
            C.parse_export(text + '{"kind": "oops", "row": {}}\n', ORDER)

    def test_an_export_without_its_snapshot_line_or_sites_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="one snapshot line"):
            C.parse_export('{"kind": "site", "row": {}}\n', ORDER)
        with pytest.raises(P.PlanError, match="no curated site"):
            C.parse_export('{"kind": "snapshot", "row": {"exported_at": "x"}}\n', ORDER)

    def test_an_export_without_an_empire_order_is_refused(self) -> None:
        text = '{"kind": "site", "row": {}}\n{"kind": "snapshot", "row": {"exported_at": "x"}}\n'
        with pytest.raises(P.PlanError, match="no empire order"):
            C.parse_export(text, ())


class TestTheModel:
    def test_a_row_without_a_description_is_not_recomputed(self) -> None:
        got = C.recompute([row(), row(SITE_B, description="")], ORDER)
        assert set(got) == {SITE_A}

    def test_mystery_counts_every_curated_row_with_a_description_or_not(self) -> None:
        seen: list[dict] = []

        def fake(site, *, combo_counts, content, wiki_image_count, engagement):  # noqa: ANN001
            seen.append(dict(combo_counts))
            return {"empires": []}

        C.recompute(
            [row(), row(SITE_B, description=None)],
            ORDER,
            generator=(fake, generator.content_stats),
        )
        assert seen == [{("Temple complex", "3000 - 1500 BC"): 2}]

    def test_the_empires_take_production_s_directory_order(self) -> None:
        def fake(site, *, combo_counts, content, wiki_image_count, engagement):  # noqa: ANN001
            return {"empires": ["greek", "roman"]}

        got = C.recompute([row()], ORDER, generator=(fake, generator.content_stats))
        assert got[SITE_A]["empires"] == ["roman", "greek"]

    def test_an_empire_production_does_not_list_is_refused(self) -> None:
        def fake(site, *, combo_counts, content, wiki_image_count, engagement):  # noqa: ANN001
            return {"empires": ["atlantis"]}

        with pytest.raises(P.PlanError, match="no place in production's order"):
            C.recompute([row()], ORDER, generator=(fake, generator.content_stats))

    def test_empires_are_spelled_the_way_the_database_prints_them(self) -> None:
        assert C.cell_text("empires", ["roman", "byzantine"]) == '["roman", "byzantine"]'
        assert C.cell_text("empires", ["Çatal"]) == '["Çatal"]'
        C.check_jsonb_spelling([{"id": SITE_A, "stored_empires": '["roman", "greek"]'}])
        with pytest.raises(P.PlanError, match="prints empires as"):
            C.check_jsonb_spelling([{"id": SITE_A, "stored_empires": '["roman","greek"]'}])

    def test_the_tagger_must_read_the_repository_s_boundaries(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from pipeline.historical_boundaries import tagger

        C.check_boundaries(sorted(tagger._get_empires()))
        with pytest.raises(P.PlanError, match="production does not list"):
            C.check_boundaries(["roman"])
        monkeypatch.setattr(tagger, "HISTORICAL_DIR", tmp_path)
        with pytest.raises(P.PlanError, match="run from the repository root"):
            C.check_boundaries(ORDER)


class TestTheCounterfactual:
    def test_journalled_inputs_are_put_back_newest_first(self) -> None:
        rows = [row(country="Pakistan", period_start=-1800)]
        journal = (
            jrow(1, SITE_A, "country", "Afghanistan", "India"),
            jrow(2, SITE_A, "country", "India", "Pakistan"),
            jrow(3, SITE_A, "period_start", "-3000", "-1800"),
            jrow(4, SITE_A, "scope_status", None, "retired"),
        )
        back, undone = C.counterfactual_sites(rows, journal)
        assert (back[0]["country"], back[0]["period_start"], undone) == ("Afghanistan", -3000, 3)

    def test_only_what_was_written_after_the_last_card_write_is_put_back(self) -> None:
        rows = [row(country="Pakistan")]
        journal = (
            jrow(1, SITE_A, "country", "Afghanistan", "India"),
            jrow(2, SITE_A, "mystery", "5", "6", table="card_stats"),
            jrow(3, SITE_A, "country", "India", "Pakistan"),
        )
        back, undone = C.counterfactual_sites(rows, journal)
        assert (back[0]["country"], undone) == ("India", 1)

    def test_a_model_that_reproduces_the_stored_cards_is_proven(self) -> None:
        rows = with_stored([row(), row(SITE_B, site_type="Fortress/citadel")])
        proof = C.prove_the_model(export(rows))
        assert proof["counterfactual_cells_differing"] == 0
        assert proof["counterfactual_cells_compared"] == 2 * len(C.COLUMNS)

    def test_a_model_that_does_not_reproduce_them_refuses_to_plan(self) -> None:
        rows = with_stored([row()], **{SITE_A: {"stored_mystery": 1}})
        with pytest.raises(P.PlanError, match="does not reproduce the stored card_stats"):
            C.build_card_stats_plan(export(rows), LANE, built_at="t")

    def test_a_journalled_write_explains_the_difference(self) -> None:
        before = with_stored([row(country="Afghanistan")])
        now = [{**before[0], "country": "Pakistan"}]
        journal = (jrow(1, SITE_A, "country", "Afghanistan", "Pakistan"),)
        result = C.build_card_stats_plan(export(now, journal), LANE, built_at="t")
        (change,) = result.plan.changes
        assert (change.column, change.old_value, change.new_value) == (
            "civilization",
            "Afghanistan",
            "Pakistan",
        )
        assert change.premise == now[0]["premise"]
        sources = [e["source"] for e in change.evidence]
        assert sources[0] == "api/cardgame/generator.py:site_card_stats"
        assert "remediation_change_log:1" in sources


class TestTheCells:
    def test_a_row_without_a_card_is_reported_not_inserted(self) -> None:
        # another (site_type, period_name) pair, so SITE_A's `mystery` share stays what it was
        rows = with_stored([row()])
        rows.append({**row(SITE_B, country="Chile", site_type="Cairn"), "has_card": False})
        rows[-1].update({f"stored_{c}": None for c in C.COLUMNS})
        result = C.build_card_stats_plan(export(rows), LANE, built_at="t")
        assert [(s.site_id, s.reason) for s in result.plan.skipped] == [
            (SITE_B, "no-card-stats-row")
        ]

    def test_a_cell_the_generator_would_clear_is_reported_not_written(self) -> None:
        """civilization copies country; a site without a country would get a NULL card column -
        this lane never clears a column, so that cell is a refusal with its reason."""
        rows = with_stored([row(country=None)], **{SITE_A: {"stored_civilization": "Malta"}})
        journal = (jrow(1, SITE_A, "country", "Malta", None),)
        result = C.build_card_stats_plan(export(rows, journal), LANE, built_at="t")
        assert not result.plan.changes
        assert [(s.column, s.reason) for s in result.plan.skipped] == [
            ("civilization", "new-value-null")
        ]

    def test_a_row_the_generator_skips_is_left_as_the_generator_leaves_it(self) -> None:
        rows = with_stored([row(), row(SITE_B)])
        rows[1]["description"] = ""
        result = C.build_card_stats_plan(export(rows), LANE, built_at="t")
        assert [(s.site_id, s.reason) for s in result.plan.skipped] == [(SITE_B, "no-description")]
        assert not result.plan.changes

    def test_the_plan_validates_renders_and_reverses_on_the_lane(self, tmp_path: Path) -> None:
        before = with_stored([row(country="Afghanistan", site_type="Settlement")])
        now = [{**before[0], "country": "Pakistan", "site_type": "Fortress/citadel"}]
        journal = (
            jrow(1, SITE_A, "country", "Afghanistan", "Pakistan"),
            jrow(2, SITE_A, "site_type", "Settlement", "Fortress/citadel"),
        )
        result = C.build_card_stats_plan(export(now, journal), LANE, built_at="t")
        columns = {c.column for c in result.plan.changes}
        assert {"civilization", "category_group", "fortification"} <= columns
        plan_path = tmp_path / "PLAN.jsonl"
        P.write_plan_jsonl(result.plan, plan_path)
        P.write_rollback_sql(result.plan, tmp_path / "ROLLBACK.sql", plan_path=plan_path)
        records = A.load_records(plan_path)
        A.validate_records(records, lane=LANE)
        A.emit(records, tmp_path, LANE, plan_path=plan_path)
        assert "'card_stats', r.column_name, 'site_id'" in (tmp_path / "APPLY.sql").read_text(
            encoding="utf-8"
        )
        assert result.tier_moves == {} or all(isinstance(k, tuple) for k in result.tier_moves)


class TestAWaveThatIsDone:
    def test_a_recomputed_database_plans_no_cell_and_leaves_no_statement(
        self, tmp_path: Path
    ) -> None:
        """The read-back of an applied wave: re-planned, it must find nothing to write - and a
        statement of an earlier plan must not be left behind to look like this plan's."""
        result = C.build_card_stats_plan(export(with_stored([row()])), LANE, built_at="t")
        assert not result.plan.changes and result.counters["cells"] == 0
        for stale in ("APPLY.sql", "ROLLBACK.sql"):
            (tmp_path / stale).write_text("-- an earlier plan's\n", encoding="utf-8")
        P.write_plan_jsonl(result.plan, tmp_path / "PLAN.jsonl")
        assert C.write_statements_or_none(result.plan, tmp_path) is False
        assert not (tmp_path / "APPLY.sql").exists() and not (tmp_path / "ROLLBACK.sql").exists()

    def test_a_plan_with_cells_gets_its_undo(self, tmp_path: Path) -> None:
        now = [{**with_stored([row(country="Malta")])[0], "country": "Gozo"}]
        journal = (jrow(1, SITE_A, "country", "Malta", "Gozo"),)
        result = C.build_card_stats_plan(export(now, journal), LANE, built_at="t")
        P.write_plan_jsonl(result.plan, tmp_path / "PLAN.jsonl")
        assert C.write_statements_or_none(result.plan, tmp_path) is True
        P.verify_pinned(
            tmp_path / "ROLLBACK.sql",
            plan_path=tmp_path / "PLAN.jsonl",
            expected=A.rollback_statement(A.load_records(tmp_path / "PLAN.jsonl"), LANE),
        )


@needs_export
def test_the_production_export_is_reproduced_cell_for_cell() -> None:
    """The counterfactual on the real export: with every journalled input put back, the generator's
    own code reproduces all 12 columns of every stored card (measured 2026-09-23: 60,048 cells)."""
    export_ = C.load_export(EXPORT_DIR)
    C.check_boundaries(export_.empire_order)
    proof = C.prove_the_model(export_)
    assert proof["counterfactual_cells_differing"] == 0
    assert proof["counterfactual_cells_compared"] == 12 * sum(
        1 for s in export_.sites if s["description"] and s["has_card"]
    )


@needs_export
def test_the_versioned_plan_md_is_the_export_s() -> None:
    export_ = C.load_export(EXPORT_DIR)
    text = (A.lane_dir(LANE) / "PLAN.md").read_text(encoding="utf-8")
    assert export_.sha256 in text


def test_the_empire_order_file_is_a_list_of_names(tmp_path: Path) -> None:
    (tmp_path / "export.jsonl").write_text(
        '{"kind": "site", "row": {}}\n{"kind": "snapshot", "row": {"exported_at": "x"}}\n',
        encoding="utf-8",
    )
    (tmp_path / "empire_order.json").write_text(json.dumps(list(ORDER)), encoding="utf-8")
    assert C.load_export(tmp_path).empire_order == ORDER
    (tmp_path / "empire_order.json").unlink()
    with pytest.raises(P.PlanError, match="run --export first"):
        C.load_export(tmp_path)


def test_the_resolved_lane_is_the_planner_s() -> None:
    assert L.resolve_lane(LANE.name) is LANE
