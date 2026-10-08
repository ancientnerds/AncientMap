"""The identity package's write lanes (`mechanical/identity_lanes.py`) and their shared writers.

`scope-window-<wave>` (D20), `name-clean-<wave>` and `retarget-name-<wave>` (D23, D13) and
`spoken-<wave>` (D23) are cell lanes of `unified_sites`; the old name's alias is a chunk of the
shared writer. DB-less: the statements are asserted as rendered text and through the plan-side
mirror of the guards (`apply.validate_records`), the probes by their set.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from gallery_audit import chunk_writer as CW  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import identity_lanes as IL  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical.plan import PlanError  # noqa: E402

SITE_A = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
SITE_B = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
FOREIGN = {"id": "11111111-1111-1111-1111-111111111111", "name": "Somewhere", "premise": "p"}
PREMISE = "Aihole | Temple | 16.0 | 75.8 | India | 501 | NULL"


def cell(column: str, old: str | None, new: str | None, **over: Any) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": SITE_A,
        "site_name": "a site",
        "old_value": old,
        "new_value": new,
        "rule": "d20-window",
        "condition": "x",
        "reason": "scope-window: x",
        "evidence": ({"source": "test", "quote": "x"},),
        "premise": PREMISE,
        "column": column,
    }
    base.update(over)
    return A.ChangeRecord(**base)


def scope_cells(
    old_status: str | None, new_status: str, old_reason: str | None = None, **over: Any
):
    return [
        cell("scope_status", old_status, new_status, **over),
        cell(
            "scope_reason",
            old_reason,
            f"E3: period_start 1200 is past the cutoff; {new_status}",
            **over,
        ),
    ]


class TestTheRegistry:
    @pytest.mark.parametrize(
        "name",
        [
            "scope-window-2026-10-12",
            "scope-window-2026-10-12b",
            "name-clean-2026-10-12",
            "retarget-name-2026-10-12a",
            "spoken-2026-10-12",
        ],
    )
    def test_a_wave_name_resolves_to_its_lane_and_its_readback(self, name: str) -> None:
        lane = L.resolve_lane(name)
        wave = re.search(r"\d{4}-\d{2}-\d{2}[a-z]?$", name).group(0)  # type: ignore[union-attr]
        assert lane.name == name == lane.key_prefix
        assert A.readback_for(lane) == IL.readback(lane)
        assert lane.run_stamp.startswith(wave + "_mechanical-")

    @pytest.mark.parametrize(
        "name",
        [
            "scope-window-2026-10-12-s001",
            "scope-window-x",
            "name-clean-2026-10",
            "spoken-2026-10-12bb",
            "name-alias-2026-10-12",
            "retarget-name",
        ],
    )
    def test_another_family_or_a_malformed_wave_is_no_lane(self, name: str) -> None:
        with pytest.raises(KeyError):
            L.resolve_lane(name)

    def test_every_lane_has_a_stamp_a_table_and_a_directory_of_its_own(self) -> None:
        lanes = [
            IL.scope_window_lane("2026-10-12"),
            IL.name_lane("name-clean", "2026-10-12"),
            IL.name_lane("retarget-name", "2026-10-12"),
            IL.spoken_lane("2026-10-12"),
        ]
        for field in ("name", "run_stamp", "out_dir_name", "plan_table", "test_id", "label"):
            values = [getattr(lane, field) for lane in lanes]
            assert len(set(values)) == len(values), field
        assert (
            IL.scope_window_lane("2026-10-12").run_stamp
            != IL.scope_window_lane("2026-10-13").run_stamp
        )
        assert (
            IL.spoken_lane("2026-10-12").rollback_run_stamp
            == "2026-10-12_mechanical-spoken-rollback"
        )

    def test_a_bad_wave_label_is_refused_by_every_factory(self) -> None:
        for build in (
            IL.scope_window_lane,
            IL.spoken_lane,
            lambda w: IL.name_lane("name-clean", w),
            lambda w: IL.name_lane("retarget-name", w),
        ):
            with pytest.raises(ValueError, match="wave label"):
                build("2026-10-1")


class TestTheScopeWindowLane:
    lane = IL.scope_window_lane("2026-10-12")

    def test_it_writes_the_status_and_its_reason_and_owns_retired_and_in_scope(self) -> None:
        assert self.lane.columns == ("scope_status", "scope_reason")
        status = self.lane.cell("scope_status")
        assert status.allowed_new_values == ("retired", "in_scope") and status.fills_null
        assert self.lane.premise_sql == L.SCOPE_REVIEW_PREMISE_SQL
        assert self.lane.test_id == "D20/scope-window" and self.lane.confidence == "authoritative"

    @pytest.mark.parametrize(
        ("old", "new", "old_reason"),
        [
            (None, "retired", None),
            ("pending", "retired", "E3: no date, and no source places it outside the window"),
            ("in_scope", "retired", "E3 museum rule: exhibits ancient material"),
            (None, "in_scope", None),
            ("pending", "in_scope", "E3: no date"),
        ],
    )
    def test_each_transition_is_a_guarded_cell_pair(
        self, old: str | None, new: str, old_reason: str | None
    ) -> None:
        records = scope_cells(old, new, old_reason)
        A.validate_records(records, lane=self.lane)
        sql = A.render_transaction(records, site_ids={SITE_A}, lane=self.lane)
        assert "guard 3" in sql and "no longer hold the planned old value" in sql
        assert "WHEN 'scope_status' THEN p.new_value NOT IN ('retired', 'in_scope')" in sql
        undo = [
            cell("scope_status", new, old),
            cell("scope_reason", records[1].new_value, old_reason),
        ]
        A.validate_records(undo, lane=self.lane, rollback=True)

    def test_the_lane_owns_no_other_status(self) -> None:
        with pytest.raises(PlanError, match="is not a value the scope-window-2026-10-12 lane owns"):
            A.validate_records(scope_cells(None, "pending"), lane=self.lane)

    def test_a_transition_that_changes_nothing_is_no_change(self) -> None:
        with pytest.raises(PlanError, match="old and new are both"):
            A.validate_records([cell("scope_status", "retired", "retired")], lane=self.lane)

    @pytest.mark.parametrize("old", [None, "pending", "in_scope"])
    def test_the_probes_corrupt_the_old_value_the_premise_and_the_ownership(
        self, old: str | None
    ) -> None:
        records = scope_cells(old, "retired", None if old is None else "an earlier reason")
        suffixes = {c[0] for c in A.probe_cases(records, self.lane, FOREIGN)}
        assert {"guard4-not-owned", "guard5-premise", "guard2-foreign-column"} <= suffixes
        assert any(s.startswith("guard3") for s in suffixes), suffixes
        for _suffix, _name, mutated, _says in A.probe_cases(records, self.lane, FOREIGN):
            for r in mutated:
                if r.column in self.lane.columns:
                    for value in (r.old_value, r.new_value):
                        if value is not None:
                            A.typed_value(self.lane.cell(r.column), value)

    def test_the_readback_counts_the_window_the_dates_and_the_statuses(self) -> None:
        text = IL.scope_window_readback(self.lane)
        for metric in (
            "curated rows retired for their date",
            "curated rows retired as no archaeological site",
            "curated rows outside the E3 window (O7) with no scope decision",
            "curated rows with scope_status in_scope",
            "journal rows for this run that write a status outside retired and in_scope",
            "curated rows with a scope_status but no scope_reason",
        ):
            assert metric in text, metric
        assert "LIKE 'E3: period_start%'" in text


class TestTheNameLanes:
    @pytest.mark.parametrize("kind", ["name-clean", "retarget-name"])
    def test_a_name_lane_is_name_l5_s_cells_conditioned_on_the_external_ids(
        self, kind: str
    ) -> None:
        lane = IL.name_lane(kind, "2026-10-12")
        assert lane.cells == L.NAME_CELLS and lane.write_invariant is L._NAME_KEY_DIFFERS
        assert lane.premise_sql == L.NAME_FIX_PREMISE_SQL
        assert (
            lane.test_id
            == {"name-clean": "D23/name-clean", "retarget-name": "D13/retarget-name"}[kind]
        )

    def test_a_rename_moves_its_key_in_the_same_transaction_and_guards_the_premise(self) -> None:
        lane = IL.name_lane("retarget-name", "2026-10-12")
        premise = "enwiki_title=Kydonia, wikidata_qid=Q200"
        records = [
            cell("name", "Chania", "Kydonia", premise=premise),
            cell("name_normalized", "chania", "kydonia", premise=premise),
        ]
        A.validate_records(records, lane=lane)
        sql = A.render_transaction(records, site_ids={SITE_A}, lane=lane)
        assert "left(lower(unaccent(" in sql and "guard 5" in sql
        assert "enwiki_title=Kydonia, wikidata_qid=Q200" in sql
        assert "retarget-name-2026-10-12" in sql

    def test_the_readback_checks_the_keys_and_the_name_journal(self) -> None:
        text = IL.name_readback(IL.name_lane("name-clean", "2026-10-12"))
        assert "curated rows whose name_normalized is not the key of their name" in text
        assert "journal rows for this run whose key is not the key of the name it wrote" in text
        assert "visible curated rows sharing their name key" in text


class TestTheSpokenLane:
    lane = IL.spoken_lane("2026-10-12")

    def test_it_fills_a_null_column_on_the_premise_of_the_name(self) -> None:
        cell_ = self.lane.cell("spoken_name")
        assert cell_.fills_null and not cell_.clears and cell_.allowed_new_values == ()
        assert self.lane.premise_sql == "u.name" and self.lane.test_id == "D23/spoken-name"
        records = [cell("spoken_name", None, "Tarxien", premise="Tarxien Temples")]
        A.validate_records(records, lane=self.lane)
        undo = [cell("spoken_name", "Tarxien", None, premise="Tarxien Temples")]
        A.validate_records(undo, lane=self.lane, rollback=True)

    def test_a_blank_or_too_long_spoken_name_is_refused_in_the_transaction(self) -> None:
        sql = A.render_transaction(
            [cell("spoken_name", None, "Tarxien", premise="Tarxien Temples")],
            site_ids={SITE_A},
            lane=self.lane,
        )
        assert "blank or too long" in sql and f"> {IL.SPOKEN_MAX_CHARS}" in sql
        probes = {
            c[0]
            for c in A.probe_cases(
                [cell("spoken_name", None, "Tarxien", premise="Tarxien Temples")],
                self.lane,
                FOREIGN,
            )
        }
        assert "invariant-spoken_name" in probes

    def test_an_empty_spoken_name_is_not_a_value(self) -> None:
        with pytest.raises(PlanError, match="empty new value"):
            A.validate_records([cell("spoken_name", None, "")], lane=self.lane)

    def test_the_readback_names_the_overwrites_and_the_broken_names(self) -> None:
        text = IL.spoken_readback(self.lane)
        assert "journal rows for this run that overwrite a spoken_name" in text
        assert "curated rows whose spoken_name is blank or longer than the bound" in text


class TestTheAliasChunk:
    """The old name stays searchable: its `label` row becomes an `alias` row, nothing else."""

    def change(self, **over: Any) -> CW.Change:
        base: dict[str, Any] = {
            "table": "unified_site_names",
            "column": "name_type",
            "row_key": "321",
            "site_id": SITE_A,
            "old_value": "label",
            "new_value": "alias",
            "rule": "d13-retarget-name",
            "reason": "'Chania' stays searchable after the rename to 'Kydonia'",
            "evidence": [{"source": "https://en.wikipedia.org/wiki/Kydonia", "quote": "Kydonia"}],
        }
        base.update(over)
        return CW.Change(**base)

    def test_a_label_to_alias_change_is_a_valid_change(self) -> None:
        CW.validate_change(self.change())

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            ("alias", "label"),
            ("label", "wikidata_alias"),
            ("label", None),
            (None, "alias"),
            ("x", "y"),
        ],
    )
    def test_no_other_transition_of_the_column_is_written(
        self, old: str | None, new: str | None
    ) -> None:
        with pytest.raises(CW.ChunkError, match="label -> alias and nothing else"):
            CW.validate_change(self.change(old_value=old, new_value=new))

    def test_the_chunk_renders_with_the_name_row_guard_and_no_delete(self) -> None:
        from identity import name_write as NW

        chunk = CW.chunk_changes(NW.alias_lane("2026-10-12"), [self.change()])[0]
        sql = CW.render_statement(chunk)
        CW.lint_statement(sql)
        assert "guard 2b" in sql and "planned name row(s) do not belong to the site" in sql
        assert "name-alias-2026-10-12-001" in sql and "'unified_site_names'" in sql
        assert "guard 2c" not in sql, "no match key is written"
        CW.lint_statement(CW.render_statement(chunk, rollback=True))
