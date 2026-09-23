"""The card_stats lane recomputes the cards with the generator's own code - and proves it first.

`build_card_stats_plan` is a pure function of an export. The rows below are fabricated in the
export's own shape (`EXPORT_SITES_SQL`); the generator, the stats rules and the empire tagger are
the real ones unless a test injects a stand-in to isolate one rule. The production export is
gitignored bulk: the test that replays it skips with its reason when it is absent.
"""

from __future__ import annotations

import json
import subprocess
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

    def test_the_empire_order_is_production_s_listing_or_a_refusal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`ls -f` over ssh: a failed listing and an empty one are refusals, never an order."""
        answers: list[tuple[int, str]] = []

        def run(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
            assert args[0] == "ssh" and args[-3:] == ["ls", "-f", C.PRODUCTION_HISTORICAL]
            assert kw["capture_output"] and kw["check"] is False and kw["timeout"] > 0
            code, out = answers.pop(0)
            return subprocess.CompletedProcess(args, code, out, "ssh: connect failed")

        monkeypatch.setattr(C.subprocess, "run", run)
        answers.append((0, ".\nroman\n..\ngreek\n"))
        assert C.production_empire_order() == ["roman", "greek"]
        answers.append((255, ""))
        with pytest.raises(P.PlanError, match="failed: ssh: connect failed"):
            C.production_empire_order()
        answers.append((0, ".\n..\n"))
        with pytest.raises(P.PlanError, match="lists nothing on production"):
            C.production_empire_order()


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

    def test_a_tagger_that_finds_no_empire_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tagger tags nothing quietly when it finds no boundary; every card would lose its
        empires, and production's order would list them all."""
        from pipeline.historical_boundaries import tagger

        monkeypatch.setattr(tagger, "_get_empires", lambda: [])
        with pytest.raises(P.PlanError, match="found no empire"):
            C.check_boundaries(ORDER)


def no_bases(wave: str) -> dict[str, Any]:
    """The first wave reads no earlier wave's basis - a proof that asks for one is wrong."""
    raise AssertionError(f"the first wave's proof asked for the basis of {wave}")


class TestTheCounterfactual:
    def test_journalled_inputs_are_put_back_newest_first(self) -> None:
        rows = [row(country="Pakistan", period_start=-1800)]
        journal = (
            jrow(1, SITE_A, "country", "Afghanistan", "India"),
            jrow(2, SITE_A, "country", "India", "Pakistan"),
            jrow(3, SITE_A, "period_start", "-3000", "-1800"),
            jrow(4, SITE_A, "scope_status", None, "retired"),
        )
        back, undone = C.counterfactual_sites(rows, journal, C.first_wave_basis(rows))
        assert (back[0]["country"], back[0]["period_start"], undone) == ("Afghanistan", -3000, 3)

    def test_only_what_was_written_after_the_basis_horizon_is_put_back(self) -> None:
        rows = [row(country="Pakistan", likes=3)]
        journal = (
            jrow(1, SITE_A, "country", "Afghanistan", "India"),
            jrow(2, SITE_A, "mystery", "5", "6", table="card_stats"),
            jrow(3, SITE_A, "country", "India", "Pakistan"),
        )
        basis = C.Basis(
            "a test basis",
            since=2,
            journal_rows=2,
            unjournalled={SITE_A: {"links": [], "wiki_images": 1, "likes": 0, "bookmarks": 0}},
        )
        back, undone = C.counterfactual_sites(rows, journal, basis)
        assert (back[0]["country"], undone) == ("India", 1)
        assert (back[0]["links"], back[0]["wiki_images"], back[0]["likes"]) == ([], 1, 0)

    def test_a_model_that_reproduces_the_stored_cards_is_proven(self) -> None:
        rows = with_stored([row(), row(SITE_B, site_type="Fortress/citadel")])
        proof = C.prove_the_model(export(rows), bases=no_bases)
        assert proof.pointer is None and proof.basis.since == 0
        assert proof.counters["counterfactual_cells_differing"] == 0
        assert proof.counters["counterfactual_cells_compared"] == 2 * len(C.COLUMNS)

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


WAVE = C.FIRST_WAVE
NEXT = C.card_stats_lane("2026-09-24")
UNESCO = "A UNESCO World Heritage temple."


def bases_in(root: Path) -> Any:
    """The waves' `BASIS.json` files under `root`, read the way `read_basis_file` reads them."""

    def read(wave: str) -> dict[str, Any]:
        path = root / wave / C.BASIS_FILE
        if not path.exists():
            raise P.PlanError(f"{path} is missing")
        return json.loads(path.read_text(encoding="utf-8"))

    return read


def plan_wave(
    rows: list[dict[str, Any]], journal: tuple[dict, ...], root: Path, wave: str = WAVE
) -> C.CardStatsPlan:
    """Plan a wave and keep its `BASIS.json` the way `main --write` does."""
    ex = export(rows, journal)
    result = C.build_card_stats_plan(
        ex, C.card_stats_lane(wave), built_at="t", bases=bases_in(root)
    )
    C.write_basis_json(C.basis_record(result, ex, wave), root / wave / C.BASIS_FILE)
    return result


def cell_value(column: str, text: str | None) -> Any:
    """A planned cell's text as the export holds the stored value (jsonb stays text)."""
    if text is None or LANE.cell(column).sql_type != "integer":
        return text
    return int(text)


def applied(
    rows: list[dict[str, Any]],
    journal: tuple[dict, ...],
    result: C.CardStatsPlan,
    first_id: int,
    *,
    undo: bool = False,
) -> tuple[list[dict[str, Any]], tuple[dict, ...]]:
    """The export after `result`'s plan ran - every cell stored and journalled under the wave's
    stamp - and, with `undo`, after its ROLLBACK.sql ran too."""
    lane = result.plan.lane
    by_id = {r["id"]: dict(r) for r in rows}
    entries = list(journal)
    changes = list(result.plan.changes)
    for i, c in enumerate(changes):
        by_id[c.site_id][f"stored_{c.column}"] = cell_value(str(c.column), c.new_value)
        entries.append(
            {
                **jrow(
                    first_id + i, c.site_id, str(c.column), c.old_value, c.new_value, "card_stats"
                ),
                "run_stamp": lane.run_stamp,
            }
        )
    if undo:
        for i, c in enumerate(changes):
            by_id[c.site_id][f"stored_{c.column}"] = cell_value(str(c.column), c.old_value)
            entries.append(
                {
                    **jrow(
                        first_id + len(changes) + i,
                        c.site_id,
                        str(c.column),
                        c.new_value,
                        c.old_value,
                        "card_stats",
                    ),
                    "run_stamp": lane.rollback_run_stamp,
                }
            )
    return list(by_id.values()), tuple(entries)


class TestTheBasis:
    """What a later wave's proof stands on (`resolve_basis`). Before the basis existed, each of
    these made every later wave refuse to plan: a like, an undo, and a journalled write that
    landed between a wave's export and its apply (review of 2026-09-23, replayed on the real
    export: one like on Igel Column gave `2 cell(s) differ`)."""

    def test_a_like_after_a_wave_s_export_is_put_back(self, tmp_path: Path) -> None:
        before = with_stored([row(country="Afghanistan", description=UNESCO)])
        now = [{**before[0], "country": "Pakistan"}]
        journal = (jrow(1, SITE_A, "country", "Afghanistan", "Pakistan"),)
        rows, entries = applied(now, journal, plan_wave(now, journal, tmp_path), first_id=2)
        liked = [{**rows[0], "likes": 1}]
        result = C.build_card_stats_plan(
            export(liked, entries), NEXT, built_at="t", bases=bases_in(tmp_path)
        )
        assert result.proof.pointer == (WAVE, "after")
        assert ("legacy", "4", "5") in {
            (c.column, c.old_value, c.new_value) for c in result.plan.changes
        }

    def test_a_journalled_write_between_export_and_apply_is_put_back(self, tmp_path: Path) -> None:
        """Wave W exported at journal row 1; row 2 wrote a site W did not plan before W's apply.
        The next wave's proof puts row 2 back (it is past W's horizon) and plans its card."""
        before = with_stored([row(country="Afghanistan"), row(SITE_B, site_type="Cairn")])
        now = [{**before[0], "country": "Pakistan"}, before[1]]
        journal = (jrow(1, SITE_A, "country", "Afghanistan", "Pakistan"),)
        wave = plan_wave(now, journal, tmp_path)
        assert {c.site_id for c in wave.plan.changes} == {SITE_A}
        late = (*journal, jrow(2, SITE_B, "country", "Malta", "Gozo"))
        rows, entries = applied([now[0], {**now[1], "country": "Gozo"}], late, wave, first_id=3)
        result = C.build_card_stats_plan(
            export(rows, entries), NEXT, built_at="t", bases=bases_in(tmp_path)
        )
        assert [(c.site_id, c.column, c.new_value) for c in result.plan.changes] == [
            (SITE_B, "civilization", "Gozo")
        ]

    def test_after_a_wave_s_undo_the_proof_stands_on_what_that_wave_found(
        self, tmp_path: Path
    ) -> None:
        before = with_stored([row(country="Afghanistan")])
        now = [{**before[0], "country": "Pakistan"}]
        journal = (jrow(1, SITE_A, "country", "Afghanistan", "Pakistan"),)
        wave = plan_wave(now, journal, tmp_path)
        rows, entries = applied(now, journal, wave, first_id=2, undo=True)
        result = C.build_card_stats_plan(
            export(rows, entries), NEXT, built_at="t", bases=bases_in(tmp_path)
        )
        assert result.proof.pointer == (WAVE, "before") and result.proof.basis.since == 0
        assert [(c.column, c.old_value, c.new_value) for c in result.plan.changes] == [
            ("civilization", "Afghanistan", "Pakistan")
        ]

    def test_an_undo_of_a_later_wave_restores_the_earlier_wave_s_basis(
        self, tmp_path: Path
    ) -> None:
        """W1 applied; a like; W2 (proven on W1's export) applied and undone. The cards are W1's
        again, so the next proof stands on W1's export - the basis W2's own proof stood on."""
        before = with_stored([row(country="Afghanistan", description=UNESCO)])
        now = [{**before[0], "country": "Pakistan"}]
        journal = (jrow(1, SITE_A, "country", "Afghanistan", "Pakistan"),)
        rows, entries = applied(now, journal, plan_wave(now, journal, tmp_path), first_id=2)
        liked = [{**rows[0], "likes": 1}]
        second = plan_wave(liked, entries, tmp_path, wave="2026-09-24")
        assert second.proof.pointer == (WAVE, "after") and second.plan.changes
        rows, entries = applied(liked, entries, second, first_id=100, undo=True)
        result = C.build_card_stats_plan(
            export(rows, entries),
            C.card_stats_lane("2026-09-25"),
            built_at="t",
            bases=bases_in(tmp_path),
        )
        assert result.proof.pointer == ("2026-09-24", "before")
        assert result.proof.basis.since == max(j["id"] for j in journal)
        assert ("legacy", "4", "5") in {
            (c.column, c.old_value, c.new_value) for c in result.plan.changes
        }

    def test_a_cell_the_basis_wave_refused_is_not_compared(self, tmp_path: Path) -> None:
        """W could not clear `civilization` (the country went NULL), so that cell still holds the
        old country - not what W's export computes, and not a model error."""
        before = with_stored([row(country="Malta", site_type="Settlement")])
        now = [{**before[0], "country": None, "site_type": "Fortress/citadel"}]
        journal = (
            jrow(1, SITE_A, "country", "Malta", None),
            jrow(2, SITE_A, "site_type", "Settlement", "Fortress/citadel"),
        )
        wave = plan_wave(now, journal, tmp_path)
        assert [(s.column, s.reason) for s in wave.plan.skipped] == [
            ("civilization", "new-value-null")
        ]
        rows, entries = applied(now, journal, wave, first_id=3)
        result = C.build_card_stats_plan(
            export(rows, entries), NEXT, built_at="t", bases=bases_in(tmp_path)
        )
        assert not result.plan.changes
        assert result.proof.counters["counterfactual_cells_compared"] == len(C.COLUMNS) - 1

    def scenario(self, tmp_path: Path) -> tuple[list[dict], tuple[dict, ...], C.CardStatsPlan]:
        """Wave W applied: two journalled field writes, several card cells."""
        before = with_stored([row(country="Afghanistan", site_type="Settlement")])
        now = [{**before[0], "country": "Pakistan", "site_type": "Fortress/citadel"}]
        journal = (
            jrow(1, SITE_A, "country", "Afghanistan", "Pakistan"),
            jrow(2, SITE_A, "site_type", "Settlement", "Fortress/citadel"),
        )
        wave = plan_wave(now, journal, tmp_path)
        assert len(wave.plan.changes) > 1
        rows, entries = applied(now, journal, wave, first_id=3)
        return rows, entries, wave

    def test_a_basis_file_that_is_not_the_applied_plan_s_refuses(self, tmp_path: Path) -> None:
        rows, entries, _ = self.scenario(tmp_path)
        with pytest.raises(P.PlanError, match="that file is not the applied plan's"):
            C.build_card_stats_plan(
                export(rows, entries[:-1]), NEXT, built_at="t", bases=bases_in(tmp_path)
            )

    def test_an_undo_that_is_not_the_exact_inverse_refuses(self, tmp_path: Path) -> None:
        before = with_stored([row(country="Afghanistan", site_type="Settlement")])
        now = [{**before[0], "country": "Pakistan", "site_type": "Fortress/citadel"}]
        journal = (
            jrow(1, SITE_A, "country", "Afghanistan", "Pakistan"),
            jrow(2, SITE_A, "site_type", "Settlement", "Fortress/citadel"),
        )
        wave = plan_wave(now, journal, tmp_path)
        rows, entries = applied(now, journal, wave, first_id=3, undo=True)
        with pytest.raises(P.PlanError, match="not the exact inverse of its write"):
            C.build_card_stats_plan(
                export(rows, entries[:-1]), NEXT, built_at="t", bases=bases_in(tmp_path)
            )

    def test_a_card_stats_row_no_wave_wrote_refuses(self) -> None:
        rows = with_stored([row()])
        journal = (jrow(1, SITE_A, "mystery", "5", "6", table="card_stats"),)
        with pytest.raises(P.PlanError, match="no card_stats wave's write or undo"):
            C.build_card_stats_plan(export(rows, journal), NEXT, built_at="t", bases=no_bases)

    def test_the_write_and_the_undo_name_their_own_sides(self) -> None:
        for stamp, side in ((LANE.run_stamp, "after"), (LANE.rollback_run_stamp, "before")):
            entry = {**jrow(9, SITE_A, "mystery", "5", "6", table="card_stats"), "run_stamp": stamp}
            assert C.basis_pointer((jrow(1, SITE_A, "country", "a", "b"), entry)) == (WAVE, side)
        assert C.basis_pointer((jrow(1, SITE_A, "country", "a", "b"),)) is None

    def test_a_basis_of_another_wave_refuses(self, tmp_path: Path) -> None:
        rows, entries, _ = self.scenario(tmp_path)
        record = bases_in(tmp_path)(WAVE)
        with pytest.raises(P.PlanError, match="is wave 2026-09-22's"):
            C.build_card_stats_plan(
                export(rows, entries),
                NEXT,
                built_at="t",
                bases=lambda wave: {**record, "wave": "2026-09-22"},
            )

    def test_a_site_the_basis_does_not_know_refuses(self, tmp_path: Path) -> None:
        rows, entries, _ = self.scenario(tmp_path)
        added = with_stored([row(SITE_B, site_type="Cairn")])
        with pytest.raises(P.PlanError, match="the curated sites are not the basis's"):
            C.build_card_stats_plan(
                export([*rows, *added], entries), NEXT, built_at="t", bases=bases_in(tmp_path)
            )

    def test_a_row_committed_below_the_horizon_after_the_export_refuses(
        self, tmp_path: Path
    ) -> None:
        rows, entries, _ = self.scenario(tmp_path)
        late = {**jrow(0, SITE_A, "description", "A temple.", "A temple."), "id": 0}
        with pytest.raises(P.PlanError, match="a row committed below the horizon"):
            C.build_card_stats_plan(
                export(rows, (late, *entries)), NEXT, built_at="t", bases=bases_in(tmp_path)
            )

    def test_an_applied_wave_is_never_re_planned(self, tmp_path: Path) -> None:
        rows, entries, _ = self.scenario(tmp_path)
        with pytest.raises(P.PlanError, match="is applied, and re-planning it would overwrite"):
            C.build_card_stats_plan(
                export(rows, entries), LANE, built_at="t", bases=bases_in(tmp_path)
            )

    def test_a_missing_basis_file_refuses(self) -> None:
        with pytest.raises(P.PlanError, match="the basis of wave 2026-01-01 is what the proof"):
            C.read_basis_file("2026-01-01")

    def test_the_unjournalled_inputs_round_trip_as_a_multiset(self) -> None:
        inputs = {
            "links": [
                ["reference", "web_discovery"],
                ["model", "sketchfab"],
                ["reference", "web_discovery"],
            ],
            "wiki_images": 3,
            "likes": 1,
            "bookmarks": 2,
        }
        encoded = C.encode_unjournalled(inputs)
        assert encoded == [[["model", "sketchfab", 1], ["reference", "web_discovery", 2]], 3, 1, 2]
        back = C.decode_unjournalled(json.loads(json.dumps(encoded)))
        assert sorted(back["links"]) == sorted(inputs["links"])
        assert {k: back[k] for k in ("wiki_images", "likes", "bookmarks")} == {
            "wiki_images": 3,
            "likes": 1,
            "bookmarks": 2,
        }


class TestTheCells:
    def test_a_row_of_another_source_is_reported_not_written(self) -> None:
        """The export reads curated rows only; a row of another source in it is refused anyway,
        whatever its card would become."""
        before = with_stored([row(), row(SITE_B, site_type="Cairn", country="Chile")])
        now = [before[0], {**before[1], "country": "Peru", "source_id": "wikidata"}]
        journal = (jrow(1, SITE_B, "country", "Chile", "Peru"),)
        result = C.build_card_stats_plan(export(now, journal), LANE, built_at="t", bases=no_bases)
        assert not result.plan.changes
        assert [(s.site_id, s.reason) for s in result.plan.skipped] == [
            (SITE_B, "row-not-in-curated-source")
        ]

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
    proof = C.prove_the_model(export_, bases=no_bases)
    assert proof.pointer is None
    assert proof.counters["counterfactual_cells_differing"] == 0
    assert proof.counters["counterfactual_cells_compared"] == 12 * sum(
        1 for s in export_.sites if s["description"] and s["has_card"]
    )


@needs_export
def test_the_versioned_basis_is_the_export_s() -> None:
    """The committed `BASIS.json` of the first wave is what its export holds: its horizon, and
    every curated site's content links, images, likes and bookmarks."""
    export_ = C.load_export(EXPORT_DIR)
    record = C.read_basis_file(C.FIRST_WAVE)
    assert (record["wave"], record["export_sha256"]) == (C.FIRST_WAVE, export_.sha256)
    assert record["journal_max_id"] == max(int(j["id"]) for j in export_.journal)
    assert record["journal_rows"] == len(export_.journal) and record["proof_basis"] is None
    decoded = {sid: C.decode_unjournalled(v) for sid, v in record["unjournalled"].items()}
    for sid, inputs in C.unjournalled_of(export_.sites).items():
        assert sorted(map(tuple, decoded[sid]["links"])) == sorted(map(tuple, inputs["links"]))
        assert [decoded[sid][k] for k in C.UNJOURNALLED[1:]] == [
            inputs[k] for k in C.UNJOURNALLED[1:]
        ]
    assert set(decoded) == {s["id"] for s in export_.sites}


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


def test_a_wave_label_nothing_could_apply_is_refused(capsys: pytest.CaptureFixture) -> None:
    """`apply.py --lane card-stats-w2` refuses the name, so `--wave w2` must not write a plan
    under it."""
    with pytest.raises(ValueError, match="is not a wave label"):
        C.card_stats_lane("w2")
    with pytest.raises(SystemExit) as info:
        C.main(["--wave", "w2", "--write"])
    assert info.value.code == 2 and "is not a wave label" in capsys.readouterr().err
    assert C.card_stats_lane("2026-09-24b").name == "card-stats-2026-09-24b"


def test_main_writes_the_wave_s_basis_next_to_its_plan(tmp_path: Path) -> None:
    """`--write` keeps the basis the next wave's proof reads; a plan of 0 cells keeps it too."""
    from pipeline.historical_boundaries import tagger

    rows = with_stored([row(), row(SITE_B, site_type="Cairn")])
    lines = [json.dumps({"kind": "site", "row": r}) for r in rows]
    lines.append(json.dumps({"kind": "snapshot", "row": {"exported_at": "2026-09-24 00:00+00"}}))
    (tmp_path / "export").mkdir()
    (tmp_path / "export" / "export.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    order = [*ORDER, *sorted(set(tagger._get_empires()) - set(ORDER))]
    (tmp_path / "export" / "empire_order.json").write_text(json.dumps(order), encoding="utf-8")
    assert C.main(["--wave", "2026-09-24", "--out", str(tmp_path), "--write"]) == 0
    record = json.loads((tmp_path / C.BASIS_FILE).read_text(encoding="utf-8"))
    assert (record["wave"], record["cells"], record["proof_basis"]) == ("2026-09-24", 0, None)
    assert set(record["unjournalled"]) == {SITE_A, SITE_B}
    assert not (tmp_path / "ROLLBACK.sql").exists()
