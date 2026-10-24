"""The site_type merge lane (`scripts/remediation/mechanical/site_type_merge.py`, owner decision D25).

DB-less: production is a fixture export, the statement is asserted as rendered text. Each refusal of
the map and of a row is asserted by the refusal it produces (`mechanical/mutation_sweep.py
"d25-merge:"`).
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

from fields import classify as FC  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import site_type_merge as M  # noqa: E402
from mechanical.plan import SNAPSHOT_KIND, JournalLink, PlanError  # noqa: E402

from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type  # noqa: E402

SITE = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
OTHER = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
WAVE = "2026-10-25"
DECISION = {"by": "orchestrator (claude-opus-5-5)", "at": "2026-10-25", "check": "adversarial"}


def map_text(**over: Any) -> str:
    data = json.loads(M.MAP_FILE.read_text(encoding="utf-8"))
    data.update(over)
    return json.dumps(data)


def undecided() -> M.MergeMap:
    """The delivered map with its decision taken away: what `wave` and `table` must refuse."""
    return M.parse_map(map_text(decision=None), "u" * 64)


def decided(**over: Any) -> M.MergeMap:
    return M.parse_map(map_text(decision=DECISION, **over), "d" * 64)


def live(site_type: str | None = "Settlement", **over: Any) -> M.Live:
    base: dict[str, Any] = {
        "site_id": SITE,
        "name": "Ancient Kourion",
        "source_id": "ancient_nerds",
        "scope_status": None,
        "site_type": site_type,
    }
    base.update(over)
    return M.Live(**base)


def link(
    id_: int, old: str | None, new: str | None, stamp: str = "phase3:batch-0001"
) -> JournalLink:
    return JournalLink(id_, stamp, "P3/site_type", old, new)


# ------------------------------------------------------------------------------ the map
class TestTheMap:
    def test_the_delivered_map_is_pinned_and_every_pair_holds(self) -> None:
        merge_map = M.load_map()
        groups = M.category_group()
        assert merge_map.sha256 == M.MAP_SHA256
        assert len(merge_map.merges) == 16
        for m in merge_map.merges.values():
            assert m.alias in CANONICAL_TYPES and m.target in CANONICAL_TYPES
            assert normalize_site_type(m.target) == m.target
            assert groups[m.alias] == groups[m.target]
            assert m.target not in merge_map.merges

    def test_the_delivered_map_is_decided(self) -> None:
        decision = M.load_map().decision
        assert decision is not None and "X14" in decision["by"]

    def test_an_edited_map_is_refused_until_its_pin_moves(self, tmp_path: Path) -> None:
        path = tmp_path / "map.json"
        path.write_text(map_text(decision=DECISION), encoding="utf-8")
        with pytest.raises(PlanError, match="is not the pinned map"):
            M.load_map(path)
        assert M.load_map(path, pin=M.sha256_file(path)).decision == DECISION

    def test_a_merge_never_crosses_a_category_group(self) -> None:
        bridge = {"target": "Gate/archway/bridge", "why": "a bridge"}
        with pytest.raises(PlanError, match="never crosses a category group"):
            M.parse_map(map_text(aliases={"Bridge": bridge}), "x")

    def test_a_target_must_be_a_canonical_fixed_point(self) -> None:
        with pytest.raises(PlanError, match="not a canonical type"):
            M.parse_map(map_text(aliases={"Town": {"target": "Townscape", "why": "w"}}), "x")
        # 'amphitheater' is a synonym the boot normaliser rewrites to 'Amphitheatre'
        with pytest.raises(PlanError, match="not a canonical type"):
            M.parse_map(map_text(aliases={"Stadium": {"target": "amphitheater", "why": "w"}}), "x")

    def test_an_alias_must_be_a_canonical_type(self) -> None:
        with pytest.raises(PlanError, match="no canonical type"):
            M.parse_map(map_text(aliases={"Townish": {"target": "Town", "why": "w"}}), "x")

    def test_a_target_is_never_an_alias_itself(self) -> None:
        chain = {
            "Town": {"target": "City/town/settlement", "why": "w"},
            "City/town/settlement": {"target": "City", "why": "w"},
        }
        with pytest.raises(PlanError, match="never an alias itself"):
            M.parse_map(map_text(aliases=chain), "x")
        with pytest.raises(PlanError, match="never an alias itself"):
            M.parse_map(map_text(aliases={"Town": {"target": "Town", "why": "w"}}), "x")

    def test_an_entry_names_its_target_and_why(self) -> None:
        with pytest.raises(PlanError, match="is not a map entry"):
            M.parse_map(map_text(aliases={"Town": {"target": "City/town/settlement"}}), "x")
        with pytest.raises(PlanError, match="is not a map entry"):
            M.parse_map(map_text(aliases={"Town": {"target": "City", "why": " "}}), "x")

    def test_the_map_holds_its_four_keys_and_merges_something(self) -> None:
        with pytest.raises(PlanError, match="holds the keys"):
            M.parse_map(map_text(extra=1), "x")
        with pytest.raises(PlanError, match="merges nothing"):
            M.parse_map(map_text(aliases={}), "x")

    def test_a_value_is_merged_or_kept_never_both(self) -> None:
        with pytest.raises(PlanError, match="merged and listed as not merged"):
            M.parse_map(map_text(not_merged={"Town": "kept"}), "x")

    def test_a_decision_names_who_when_and_the_check(self) -> None:
        with pytest.raises(PlanError, match="names no `by`, `at` and `check`"):
            M.parse_map(map_text(decision={"by": "x"}), "x")
        with pytest.raises(PlanError, match="names no `by`, `at` and `check`"):
            M.parse_map(map_text(decision={"by": "x", "at": "", "check": "c"}), "x")

    def test_the_p31_table_keeps_every_alias_until_the_merge_is_in_production(self) -> None:
        """Until the decided merge is applied and `table --write` moves the table with its pin,
        the pinned table still lists every alias, so a classify run reads the unmerged rows as
        before (the merge map is undecided today)."""
        merge_map = M.load_map()
        offered = {t for entry in FC.load_table().values() for t in entry.types}
        assert set(merge_map.merges) <= offered

    def test_an_unmerged_alias_row_classifies_as_before(self) -> None:
        """A `Settlement` site whose item is a 'human settlement' (a container class) holds its
        type: no identity doubt, the type confirmed - with the pinned table, not a merged one."""
        table = FC.load_table()
        who = FC.identity("Settlement", [table["Q486972"]])
        assert not who.doubt
        merged = FC.parse_table(M.merged_table(_table_text(), decided())[0])
        assert FC.identity("Settlement", [merged["Q486972"]]).doubt

    def test_the_group_lookup_is_the_card_game_s_own(self) -> None:
        from api.cardgame.constants import CATEGORY_GROUP

        assert dict(M.category_group()) == dict(CATEGORY_GROUP)


def _table_text() -> str:
    return FC.TABLE.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


class TestTheTable:
    def test_the_merged_table_offers_no_alias_and_keeps_the_rest(self) -> None:
        text, changed = M.merged_table(_table_text(), decided())
        merged, before = FC.parse_table(text), FC.parse_table(_table_text())
        aliases = set(decided().merges)
        assert changed > 0 and set(merged) == set(before)
        assert not {t for e in merged.values() for t in e.types} & aliases
        # City merges into the compound since the X14 decision; Village is kept
        assert merged["Q486972"].types == ("City/town/settlement", "Village")
        assert all(
            e.kind == before[q].kind and e.label == before[q].label for q, e in merged.items()
        )
        assert "without the site_type aliases" in json.loads(text)["about"]
        # written the table's own way (indent 1, UTF-8 unescaped), which the pinned file is too
        for t in (text, _table_text()):
            assert json.dumps(json.loads(t), indent=1, ensure_ascii=False) + "\n" == t

    def test_a_merged_table_is_not_merged_twice(self) -> None:
        text, _ = M.merged_table(_table_text(), decided())
        with pytest.raises(PlanError, match="merged already"):
            M.merged_table(text, decided())

    def test_an_undecided_map_moves_no_table(self) -> None:
        with pytest.raises(PlanError, match="map is undecided"):
            M.table(undecided(), read=reader([]))

    def test_the_table_waits_for_the_last_merge_wave(self, tmp_path: Path) -> None:
        path = tmp_path / "p31.json"
        path.write_text(_table_text(), encoding="utf-8", newline="\n")
        with pytest.raises(PlanError, match="1 curated row\\(s\\) still hold an alias"):
            M.table(decided(), read=reader([SITE]), path=path, write=True)
        assert path.read_text(encoding="utf-8") == _table_text()

    def test_the_table_is_written_with_the_sha_its_pin_moves_to(self, tmp_path: Path) -> None:
        path = tmp_path / "p31.json"
        path.write_text(_table_text(), encoding="utf-8", newline="\n")
        dry = M.table(decided(), read=reader([]), path=path)
        assert dry["written"] is False and path.read_text(encoding="utf-8") == _table_text()
        done = M.table(decided(), read=reader([]), path=path, write=True)
        assert done["table_sha256"] == dry["table_sha256"] == FC.table_sha256(path)
        assert done["table_sha256"] in done["next"]
        FC.load_table(path, pin=done["table_sha256"])


# ------------------------------------------------------------------------------ a row
class TestClassify:
    def test_an_alias_is_written_to_its_target(self) -> None:
        v = M.classify(SITE, live(), (link(1, "City", "Settlement"),), decided())
        assert v.ok and (v.old_value, v.new_value) == ("Settlement", "City/town/settlement")
        assert v.rule == "merge-alias" and v.phase3
        sources = [e["source"] for e in v.evidence]
        assert any("site_type_merge.json" in s for s in sources)
        assert "remediation_change_log:1" in sources

    def test_a_row_without_a_journal_is_the_imports_and_is_merged(self) -> None:
        v = M.classify(SITE, live("Theater"), (), decided())
        assert v.ok and v.new_value == "Theatre" and not v.phase3

    def test_a_retired_row_is_merged_too(self) -> None:
        v = M.classify(SITE, live("Cave", scope_status="retired"), (), decided())
        assert v.ok and v.new_value == "Cave Structures"

    def test_a_row_that_no_longer_holds_an_alias_is_listed(self) -> None:
        v = M.classify(SITE, live("Fortress/citadel"), (), decided())
        assert not v.ok and v.reason == "not-an-alias"
        assert not M.classify(SITE, live(None), (), decided()).ok

    def test_a_journal_that_does_not_end_at_the_live_value_is_refused(self) -> None:
        v = M.classify(SITE, live(), (link(1, "City", "Town"),), decided())
        assert not v.ok and v.reason == "journal-disagrees"
        broken = (link(1, "City", "Town"), link(2, "Village", "Settlement"))
        assert M.classify(SITE, live(), broken, decided()).reason == "journal-chain-broken"

    def test_a_row_of_another_source_is_refused(self) -> None:
        v = M.classify(SITE, live(source_id="lyra"), (), decided())
        assert not v.ok and v.reason == "row-not-in-curated-source"

    def test_a_site_that_is_gone_is_refused(self) -> None:
        v = M.classify(SITE, None, (), decided())
        assert not v.ok and v.reason == "site-gone"


# ------------------------------------------------------------------------------ the lanes
class TestTheLane:
    def test_a_step_is_a_lane_of_its_own(self) -> None:
        lane = M.merge_lane(WAVE, 2, M.load_map())
        assert lane.name == "site-type-merge-2026-10-25-s002" == lane.key_prefix
        assert lane.run_stamp == "2026-10-25_mechanical-site-type-merge-s002"
        assert lane.rollback_run_stamp == "2026-10-25_mechanical-site-type-merge-s002-rollback"
        assert lane.out_dir_name == "mechanical_site_type_merge/2026-10-25/s002"
        assert lane.column == "site_type" and lane.max_chars == 100 and not lane.cells
        assert lane.test_id == "D25/site-type-merge"
        assert lane.run_stamp != M.merge_lane(WAVE, 3, M.load_map()).run_stamp

    def test_the_lane_owns_the_map_s_targets_only(self) -> None:
        merge_map = M.load_map()
        lane = M.merge_lane(WAVE, 1, merge_map)
        assert lane.allowed_new_values == merge_map.targets
        assert not set(lane.allowed_new_values) & set(merge_map.merges)

    def test_the_name_resolves_through_the_registry_and_its_readback(self) -> None:
        lane = L.resolve_lane("site-type-merge-2026-10-25b-s001")
        assert lane == M.merge_lane("2026-10-25b", 1, M.load_map())
        readback = A.readback_for(lane)
        assert readback == M.readback(lane)
        assert f"'{lane.run_stamp}'" in readback
        assert lane.post_commit_residual.predicate in readback

    @pytest.mark.parametrize(
        "name",
        [
            "site-type-merge-2026-10-25",
            "site-type-merge-2026-10-25-s1",
            "site-type-merge-x-s001",
            "site-type-merges-2026-10-25-s001",
        ],
    )
    def test_a_malformed_name_is_no_lane(self, name: str) -> None:
        with pytest.raises(KeyError):
            L.resolve_lane(name)

    def test_the_statement_guards_the_alias_and_owns_the_targets(self) -> None:
        record = A.ChangeRecord(
            site_id=SITE,
            site_name="Ancient Kourion",
            old_value="Settlement",
            new_value="City/town/settlement",
            rule="merge-alias",
            condition="",
            reason="site-type-merge: x",
            evidence=({"source": "test", "quote": "x"},),
        )
        lane = M.merge_lane(WAVE, 1, M.load_map())
        sql = A.render_transaction([record], site_ids={SITE}, lane=lane)
        assert "scope guard 3" in sql and "scope guard 4" in sql
        assert f"'{lane.change_key(SITE)}'" in sql and "'D25/site-type-merge'" in sql
        with pytest.raises(PlanError, match="is not a value the site-type-merge"):
            A.validate_records(
                [A.ChangeRecord(**{**record.__dict__, "new_value": "Town"})], lane=lane
            )


# ------------------------------------------------------------------------------ the steps
def tagged(rows: dict[str, list[dict[str, Any]]]) -> str:
    lines = [json.dumps({"kind": kind, "row": r}) for kind, items in rows.items() for r in items]
    lines.append(
        json.dumps({"kind": SNAPSHOT_KIND, "row": {"exported_at": "2026-10-25 10:00:00+00"}})
    )
    return "\n".join(lines) + "\n"


def site_row(site: str = SITE, site_type: str = "Settlement", **over: Any) -> dict[str, Any]:
    base = {"site_id": site, "name": "Ancient Kourion", "source_id": "ancient_nerds",
            "scope_status": None, "site_type": site_type}  # fmt: skip
    return {**base, **over}


def reader(sites: list[str], rows: list[dict[str, Any]] | None = None, journal: list | None = None):  # type: ignore[no-untyped-def]
    def read(script: str) -> str:
        if "u.id::text AS site_id FROM unified_sites u WHERE" in script:
            return tagged({"site": [{"site_id": s} for s in sites]})
        return tagged(
            {"site": rows if rows is not None else [site_row()], "journal": journal or []}
        )

    return read


class TestTheWaveAndTheSteps:
    def test_an_undecided_map_plans_no_wave(self, tmp_path: Path) -> None:
        with pytest.raises(PlanError, match="the map is a proposal"):
            M.build_wave(WAVE, merge_map=undecided(), read=reader([SITE]), root=tmp_path)

    def test_the_wave_lists_the_alias_rows_in_steps_of_100(self, tmp_path: Path) -> None:
        sites = [f"00000000-0000-4000-8000-{n:012d}" for n in range(212)]
        merge_map = decided()
        result = M.build_wave(WAVE, merge_map=merge_map, read=reader(sites), root=tmp_path)
        assert result == {"wave": WAVE, "sites": 212, "steps": 3}
        record = M.read_wave(WAVE, tmp_path)
        assert [len(s) for s in record["steps"]] == [100, 100, 12]
        assert record["map_sha256"] == merge_map.sha256

    def test_a_wave_is_planned_once_and_an_edited_one_is_refused(self, tmp_path: Path) -> None:
        M.build_wave(WAVE, merge_map=decided(), read=reader([SITE]), root=tmp_path)
        with pytest.raises(PlanError, match="planned once"):
            M.build_wave(WAVE, merge_map=decided(), read=reader([SITE]), root=tmp_path)
        path = M.wave_dir(WAVE, tmp_path) / M.WAVE_FILE
        path.write_text(path.read_text(encoding="utf-8").replace('"sites": 1', '"sites": 2'))
        with pytest.raises(PlanError, match="not the pinned wave"):
            M.read_wave(WAVE, tmp_path)

    def test_a_wave_label_no_lane_resolves_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="wave label"):
            M.build_wave("tomorrow", merge_map=decided(), read=reader([SITE]), root=tmp_path)

    def test_a_step_is_planned_from_a_fresh_read_and_writes_its_files(self, tmp_path: Path) -> None:
        merge_map = decided()
        M.build_wave(WAVE, merge_map=merge_map, read=reader([SITE, OTHER]), root=tmp_path)
        rows = [site_row(), site_row(OTHER, "Fortress/citadel")]
        result = M.plan_step(WAVE, 1, merge_map=merge_map, read=reader([], rows), root=tmp_path)
        assert result["cells"] == 1 and result["skip:not-an-alias"] == 1
        assert result["merge:Settlement -> City/town/settlement"] == 1
        out = tmp_path / WAVE / "s001"
        plan = json.loads((out / "PLAN.jsonl").read_text(encoding="utf-8"))
        assert plan["column"] == "site_type" and plan["old_value"] == "Settlement"
        assert plan["change_key"] == f"site-type-merge-2026-10-25-s001:{SITE}"
        rollback = (out / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert "2026-10-25_mechanical-site-type-merge-s001-rollback" in rollback
        assert (out / "SKIPPED.jsonl").exists() and (out / "PLAN.md").exists()
        records = A.load_records(out / "PLAN.jsonl")
        A.validate_records(records, lane=M.merge_lane(WAVE, 1, merge_map))
        with pytest.raises(PlanError, match="exists"):
            M.plan_step(WAVE, 1, merge_map=merge_map, read=reader([], rows), root=tmp_path)

    def test_a_step_waits_for_the_one_before_it(self, tmp_path: Path) -> None:
        sites = [f"00000000-0000-4000-8000-{n:012d}" for n in range(101)]
        M.build_wave(WAVE, merge_map=decided(), read=reader(sites), root=tmp_path)
        with pytest.raises(PlanError, match="step 1 is not accepted"):
            M.plan_step(WAVE, 2, merge_map=decided(), read=reader([]), root=tmp_path)
        with pytest.raises(PlanError, match="steps 1..2"):
            M.plan_step(WAVE, 3, merge_map=decided(), read=reader([]), root=tmp_path)

    def test_a_step_is_never_planned_over_another_map(self, tmp_path: Path) -> None:
        M.build_wave(WAVE, merge_map=decided(), read=reader([SITE]), root=tmp_path)
        other = M.parse_map(map_text(decision=DECISION), "e" * 64)
        with pytest.raises(PlanError, match="plan a new wave"):
            M.plan_step(WAVE, 1, merge_map=other, read=reader([]), root=tmp_path)

    def test_a_step_holds_at_most_a_hundred_sites(self) -> None:
        many = [f"00000000-0000-4000-8000-{n:012d}" for n in range(101)]
        with pytest.raises(PlanError, match="at most 100"):
            M.build_step(WAVE, 1, many, {}, {}, decided(), built_at="t")

    def test_the_acceptance_reads_production_back_and_records_it_once(self, tmp_path: Path) -> None:
        merge_map = decided()
        M.build_wave(WAVE, merge_map=merge_map, read=reader([SITE]), root=tmp_path)
        M.plan_step(WAVE, 1, merge_map=merge_map, read=reader([]), root=tmp_path)
        lane = M.merge_lane(WAVE, 1, merge_map)
        written = {"row_pk": SITE, "run_stamp": lane.run_stamp, "old_value": "Settlement",
                   "new_value": "City/town/settlement"}  # fmt: skip
        after = reader([], [site_row(site_type="City/town/settlement")], [written])
        assert M.accept_step(WAVE, 1, merge_map=merge_map, read=after, root=tmp_path) == (0, [])
        assert (tmp_path / WAVE / "s001" / M.ACCEPTED_FILE).exists()
        stale = reader([], [site_row()], [written])
        code, found = M.accept_step(WAVE, 1, merge_map=merge_map, read=stale, root=tmp_path)
        assert code == 1 and "does not hold the planned value" in found[0]

    def test_the_acceptance_names_what_production_lacks(self) -> None:
        lane = M.merge_lane(WAVE, 1, decided())
        planned = [
            {"site_id": SITE, "old_value": "Settlement", "new_value": "City/town/settlement"}
        ]
        found = M.deviations(lane, planned, {SITE: live("City/town/settlement")}, [])
        assert any("0 journal row(s) for 1 planned" in f for f in found)
        assert any("journal row is not the plan's" in f for f in found)
        undone = [{"row_pk": SITE, "run_stamp": lane.rollback_run_stamp}]
        assert any(
            "rollback journal row" in f
            for f in M.deviations(lane, planned, {SITE: live("City/town/settlement")}, undone)
        )
        other = [{"row_pk": SITE, "run_stamp": lane.run_stamp, "old_value": "Town",
                  "new_value": "City/town/settlement"}]  # fmt: skip
        assert M.deviations(lane, planned, {SITE: live("City/town/settlement")}, other) == [
            f"{SITE}: the journal row is not the plan's"
        ]


class TestTheReport:
    def test_the_report_counts_the_aliases_and_the_refusals(self) -> None:
        def read(script: str) -> str:
            if "count(*) AS curated" in script:
                return tagged(
                    {
                        "count": [
                            {"site_type": "Settlement", "curated": 110, "retired": 1},
                            {"site_type": "City/town/settlement", "curated": 1141, "retired": 3},
                            {"site_type": "City", "curated": 92, "retired": 0},
                        ]
                    }
                )
            if "u.id::text AS site_id FROM unified_sites u WHERE" in script:
                return tagged({"site": [{"site_id": SITE}, {"site_id": OTHER}]})
            return tagged(
                {
                    "site": [site_row(), site_row(OTHER, "Town")],
                    "journal": [
                        {
                            "id": 4,
                            "row_pk": OTHER,
                            "run_stamp": "x",
                            "test_id": "t",
                            "old_value": "City",
                            "new_value": "Village",
                        }  # fmt: skip
                    ],
                }
            )

        result = M.report(M.load_map(), read=read)
        assert result["aliases"]["Settlement"] == {
            "target": "City/town/settlement",
            "group": "Settlements",
            "curated": 110,
            "retired": 1,
            "shown": 109,
        }
        # the decided map (X14) merges City too: 110 + 92 rows
        assert result["aliases"]["City"]["curated"] == 92
        assert result["rows"] == 202 and result["shown_rows"] == 201
        assert result["targets_before"]["City/town/settlement"] == 1141
        assert "City" not in result["not_merged"]
        assert result["refused"] == {"journal-disagrees": 1}
        assert result["decided"] is True
