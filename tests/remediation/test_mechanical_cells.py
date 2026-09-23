"""Cell lanes: a lane as (table, key column, value column, curated-scope predicate).

The column lanes of 2026-09-21/22 are pinned byte for byte in `test_mechanical.py`
(`TestTheColumnLanesAreByteNeutral`). This file drives what the generalisation added: a lane that
writes several columns of `unified_sites` or of `card_stats` in one transaction, each cell compared
in its column's own type, NULL allowed only where the lane fills an empty column, and - for a
journal reversal - every cell tied to the journal row it undoes. Each guard is asserted by the
refusal it produces, so removing the guard turns its test red (the mechanical mutation sweep
proves that for each one).
"""

from __future__ import annotations

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

SITE_A = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
SITE_B = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
CARD = L.resolve_lane("card-stats-2026-09-23")


def cell(lane: L.Lane = L.SCOPE, **over: Any) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": SITE_A,
        "site_name": "a site",
        "old_value": None,
        "new_value": "retired",
        "rule": "e4-rule-a",
        "condition": "x",
        "reason": "scope-e4 (e4-rule-a): scope_status NULL -> 'retired'",
        "evidence": ({"source": "test", "quote": "x"},),
        "premise": "1837 | NULL | 34.0 | 71.2 | Fortress/citadel | Ali Masjid Fort",
        "column": "scope_status",
    }
    base.update(over)
    return A.ChangeRecord(**base)


def card_cell(**over: Any) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": SITE_A,
        "site_name": "a site",
        "old_value": "5",
        "new_value": "6",
        "rule": "generator-recompute",
        "condition": "x",
        "reason": "card-stats (generator-recompute): mystery 5 -> 6",
        "evidence": ({"source": "test", "quote": "x"},),
        "premise": "0123456789abcdef0123456789abcdef",
        "column": "mystery",
    }
    base.update(over)
    return A.ChangeRecord(**base)


def reversal_cell(**over: Any) -> A.ChangeRecord:
    base: dict[str, Any] = {
        "site_id": SITE_B,
        "site_name": "Ahin Posh Tape",
        "old_value": "Pakistan",
        "new_value": "Afghanistan",
        "rule": "journal-reversal",
        "condition": "x",
        "reason": "journal-reversal-1 (journal-reversal): undo",
        "evidence": ({"source": "test", "quote": "x"},),
        "column": "country",
        "journal_id": 28384,
    }
    base.update(over)
    return A.ChangeRecord(**base)


# ------------------------------------------------------------------------------ the lane shape
class TestTheLaneShape:
    def test_a_target_must_be_keyed_by_a_site_id(self) -> None:
        with pytest.raises(ValueError, match="is not a target"):
            L.Target("wiki_images", "id", "w")
        with pytest.raises(ValueError, match="is not a target"):
            L.Target("card_stats", "id", "t")

    def test_u_is_the_site_and_only_the_site(self) -> None:
        with pytest.raises(ValueError, match="`u` is the site"):
            L.Target("card_stats", "site_id", "u")
        with pytest.raises(ValueError, match="`u` is the site"):
            L.Target("unified_sites", "id", "t")

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("name", "mystery; DROP", "not a plain column name"),
            ("sql_type", "integer; --", "is not one of"),
            ("max_chars", 0, "must be positive"),
            ("allowed_new_values", ("",), "cannot be written"),
        ],
    )
    def test_a_column_that_would_splice_something_unsafe_is_refused(
        self, field: str, value: Any, message: str
    ) -> None:
        with pytest.raises(ValueError, match=message):
            replace(L.Column("mystery", "integer"), **{field: value})

    def test_a_cell_lane_names_its_columns_only_in_cells(self) -> None:
        with pytest.raises(ValueError, match="names its columns in `cells`"):
            replace(L.SCOPE, column="scope_status")
        with pytest.raises(ValueError, match="appears twice"):
            replace(L.SCOPE, cells=(L.SCOPE.cells[0], L.SCOPE.cells[0]))

    def test_a_column_lane_writes_unified_sites_and_reverses_nothing(self) -> None:
        with pytest.raises(ValueError, match="is a cell lane"):
            replace(L.UK_PARTS, target=L.CARD_STATS)
        with pytest.raises(ValueError, match="is a cell lane"):
            replace(L.UK_PARTS, reverses_journal=True)

    def test_a_cell_key_names_its_column_and_a_reversal_its_suffix(self) -> None:
        assert L.SCOPE.change_key(SITE_A, "scope_status") == f"scope-e4:{SITE_A}:scope_status"
        assert L.SCOPE.rollback_change_key(SITE_A, "scope_reason") == (
            f"scope-e4-rollback:{SITE_A}:scope_reason"
        )
        with pytest.raises(ValueError, match="names the cell's column"):
            L.SCOPE.change_key(SITE_A)
        assert L.UK_PARTS.change_key(SITE_A, "country") == f"country-uk-part:{SITE_A}"
        with pytest.raises(ValueError, match="writes country"):
            L.UK_PARTS.change_key(SITE_A, "site_type")

    def test_a_card_stats_wave_resolves_and_nothing_else_does(self) -> None:
        assert CARD.target is L.CARD_STATS and CARD.run_stamp == "2026-09-23_mechanical-card-stats"
        assert L.resolve_lane("card-stats-2026-09-24b").run_stamp == (
            "2026-09-24b_mechanical-card-stats"
        )
        for bad in ("card-stats-", "card-stats-w1", "card-stats-2026-09-23; x"):
            with pytest.raises(KeyError):
                L.resolve_lane(bad)

    def test_the_outside_predicate_lists_every_owned_column(self) -> None:
        assert L.outside(L.SCOPE, "l.") == (
            "(l.table_name <> 'unified_sites' OR l.column_name NOT IN ('scope_status', "
            "'scope_reason'))"
        )
        assert L.written_where(CARD).startswith("card_stats.(antiquity, ")
        assert L.outside(L.T05) == "(table_name <> 'unified_sites' OR column_name <> 'country')"


# ------------------------------------------------------------------------------ the plan side
class TestThePlanSideMirror:
    def test_a_fill_may_start_from_null_but_never_end_in_it(self) -> None:
        A.validate_records([cell()], lane=L.SCOPE)
        with pytest.raises(P.PlanError, match="never clears a column"):
            A.validate_records([cell(new_value=None, old_value="retired")], lane=L.SCOPE)

    def test_a_column_the_lane_does_not_fill_is_never_null(self) -> None:
        with pytest.raises(P.PlanError, match="is not a column this lane fills"):
            A.validate_records([card_cell(old_value=None)], lane=CARD)

    def test_the_reversal_of_a_fill_restores_the_null(self) -> None:
        undo = cell(old_value="retired", new_value=None)
        A.validate_records([undo], lane=L.SCOPE, rollback=True)
        with pytest.raises(P.PlanError, match="undoes a NULL"):
            A.validate_records([cell()], lane=L.SCOPE, rollback=True)

    def test_a_cell_must_name_a_column_the_lane_owns(self) -> None:
        with pytest.raises(P.PlanError, match="is not a column this lane writes"):
            A.validate_records([card_cell(column="name")], lane=CARD)
        with pytest.raises(P.PlanError, match="is not a column this lane writes"):
            A.validate_records([card_cell(column=None)], lane=CARD)

    def test_a_column_lane_record_may_not_name_another_column(self) -> None:
        record = replace(
            cell(),
            column="site_type",
            old_value="Ireland",
            new_value="Northern Ireland",
            premise="54.5,-7.8",
        )
        with pytest.raises(P.PlanError, match="writes country, not site_type"):
            A.validate_records([record], lane=L.UK_PARTS)

    def test_the_same_cell_twice_is_refused_but_two_cells_of_a_site_are_not(self) -> None:
        A.validate_records([card_cell(), card_cell(column="total_power")], lane=CARD)
        with pytest.raises(P.PlanError, match="appears twice"):
            A.validate_records([card_cell(), card_cell()], lane=CARD)

    @pytest.mark.parametrize(
        ("over", "message"),
        [
            ({"new_value": "06"}, "is not how the database prints 6"),
            ({"new_value": "six"}, "is not an integer"),
            ({"column": "empires", "old_value": "[]", "new_value": "[roman"}, "is not JSON"),
            ({"column": "empires", "old_value": '["a"]', "new_value": '[ "a" ]'}, "old and new"),
            ({"new_value": "5"}, "old and new"),
            ({"column": "category_group", "old_value": "Other", "new_value": "X" * 51}, "holds 50"),
            ({"new_value": ""}, "an empty new value"),
        ],
    )
    def test_every_cell_is_checked_in_its_column_s_type(
        self, over: dict[str, Any], message: str
    ) -> None:
        with pytest.raises(P.PlanError, match=message):
            A.validate_records([card_cell(**over)], lane=CARD)

    def test_an_owned_column_refuses_a_value_the_lane_does_not_own(self) -> None:
        with pytest.raises(P.PlanError, match="does not own|is not a value"):
            A.validate_records(
                [card_cell(column="rarity_tier", old_value="2", new_value="9")], lane=CARD
            )
        with pytest.raises(P.PlanError, match="is not a value the scope-e4 lane owns"):
            A.validate_records([cell(new_value="hidden")], lane=L.SCOPE)
        undo = cell(old_value="hidden", new_value=None)
        with pytest.raises(P.PlanError, match="'hidden' is not a value"):
            A.validate_records([undo], lane=L.SCOPE, rollback=True)

    def test_every_cell_of_a_site_carries_the_same_premise(self) -> None:
        with pytest.raises(P.PlanError, match="two premises for one site"):
            A.validate_records(
                [card_cell(), card_cell(column="total_power", premise="another")], lane=CARD
            )

    def test_a_reversal_names_its_journal_row_and_only_a_reversal_does(self) -> None:
        A.validate_records([reversal_cell()], lane=L.REVERSAL_1)
        with pytest.raises(P.PlanError, match="reverses journal rows, and the record names none"):
            A.validate_records([reversal_cell(journal_id=None)], lane=L.REVERSAL_1)
        with pytest.raises(P.PlanError, match="journal id this statement does not check"):
            A.validate_records([card_cell(journal_id=7)], lane=CARD)
        undo = reversal_cell(old_value="Afghanistan", new_value="Pakistan")
        with pytest.raises(P.PlanError, match="journal id this statement does not check"):
            A.validate_records([undo], lane=L.REVERSAL_1, rollback=True)


# ------------------------------------------------------------------------------ the statement
def rendered(lane: L.Lane, records: list[A.ChangeRecord], **kw: Any) -> str:
    return A.render_transaction(records, site_ids={r.site_id for r in records}, lane=lane, **kw)


class TestTheCellStatement:
    def test_the_plan_is_a_set_of_cells(self) -> None:
        sql = rendered(CARD, [card_cell()])
        assert "    column_name TEXT NOT NULL," in sql
        assert "    PRIMARY KEY (site_id, column_name)" in sql
        assert "    site_id     UUID PRIMARY KEY," not in sql
        assert (
            f"('{SITE_A}'::uuid, 'mystery', '5', '6', 'card-stats-2026-09-23:{SITE_A}:mystery',"
            in sql
        )

    def test_scope_guard_1_needs_the_card_stats_row_and_a_curated_site(self) -> None:
        sql = rendered(CARD, [card_cell()])
        assert "LEFT JOIN card_stats t ON t.site_id = p.site_id" in sql
        assert "LEFT JOIN unified_sites u ON u.id = p.site_id" in sql
        assert "WHERE t.site_id IS NULL OR u.id IS NULL OR u.source_id <> 'ancient_nerds';" in sql

    def test_every_comparison_is_made_in_the_column_s_type(self) -> None:
        sql = rendered(CARD, [card_cell()])
        assert "WHEN 'mystery' THEN t.mystery IS DISTINCT FROM p.old_value::integer" in sql
        assert "WHEN 'empires' THEN t.empires IS DISTINCT FROM p.new_value::jsonb" in sql
        assert (
            "WHEN 'mystery' THEN p.new_value::integer IS NOT DISTINCT FROM p.old_value::integer"
            in sql
        )
        # a cell in a column the lane does not own counts as refused (guard 2), as not holding its
        # old value (guard 3) and as not holding its new value (invariant 1)
        for block in ("scope guard 2", "scope guard 3", "invariant 1"):
            section = sql.split(f"-- {block}", 1)[1].split("IF bad > 0", 1)[0]
            assert section.rstrip().endswith("ELSE true END;"), block
        assert "OR length(p.new_value) > 50\n" in sql and "OR length(p.new_value) > 100\n" in sql

    def test_guard_2_allows_null_only_on_the_side_the_lane_fills(self) -> None:
        write = rendered(L.SCOPE, [cell()])
        assert (
            "WHEN 'scope_status' THEN p.new_value::text IS NOT DISTINCT FROM p.old_value::text "
            "OR p.new_value IS NULL\n"
        ) in write
        undo = rendered(L.SCOPE, [cell(old_value="retired", new_value=None)], rollback=True)
        assert (
            "WHEN 'scope_status' THEN p.new_value::text IS NOT DISTINCT FROM p.old_value::text "
            "OR p.old_value IS NULL\n"
        ) in undo
        card = rendered(CARD, [card_cell()])
        assert "OR p.new_value IS NULL OR p.old_value IS NULL" in card

    def test_guard_4_covers_the_owned_columns_only(self) -> None:
        sql = rendered(CARD, [card_cell()])
        assert "WHEN 'rarity_tier' THEN p.new_value NOT IN ('1', '2', '3', '4', '5')" in sql
        assert "WHEN 'category_group' THEN p.new_value NOT IN ('Burial & Death'," in sql
        assert "WHEN 'mystery' THEN p.new_value NOT IN" not in sql
        undo = rendered(L.SCOPE, [cell(old_value="retired", new_value=None)], rollback=True)
        assert "WHEN 'scope_status' THEN p.old_value NOT IN" in undo

    def test_guard_5_reads_each_site_s_premise_once(self) -> None:
        sql = rendered(
            CARD, [card_cell(), card_cell(column="total_power", old_value="1", new_value="2")]
        )
        assert "FROM (SELECT DISTINCT site_id, premise FROM _card_stats_plan) p" in sql

    def test_guard_6_is_rendered_for_a_reversal_s_write_only(self) -> None:
        write = rendered(L.REVERSAL_1, [reversal_cell()])
        assert "scope guard 6" in write and "    journal_id  BIGINT NOT NULL," in write
        assert "WHERE l.id = p.journal_id AND l.table_name = 'unified_sites'" in write
        assert "l.id > p.journal_id" in write
        assert f"'{SITE_B}'::uuid, 'country', 'Pakistan', 'Afghanistan'" in write
        assert ", 28384, '[" in write
        undo = P.render_rollback_sql([reversal_cell()], site_ids={SITE_B}, lane=L.REVERSAL_1)
        assert "scope guard 6" not in undo and "journal_id" not in undo
        assert "scope guard 6" not in rendered(CARD, [card_cell()])

    def test_the_writer_names_the_target_and_each_cell_s_column(self) -> None:
        sql = rendered(CARD, [card_cell()])
        assert "'card_stats', r.column_name, 'site_id', r.site_id::text," in sql
        assert "ORDER BY site_id, column_name LOOP" in sql
        assert "ON l.row_pk = p.site_id::text AND l.table_name = 'card_stats'" in sql
        assert "       AND l.column_name = p.column_name" in sql

    def test_the_notice_counts_cells_against_the_plan(self) -> None:
        sql = rendered(
            CARD, [card_cell(), card_cell(column="total_power", old_value="1", new_value="2")]
        )
        assert "% of % planned cell(s) changed and journalled over 1 curated site(s)'," in sql

    def test_the_read_backs_compare_each_cell_in_its_type(self) -> None:
        post = A.post_commit_reads(CARD, run_stamp="x")
        assert "WHEN 'mystery' THEN t.mystery IS NOT DISTINCT FROM l.new_value::integer" in post
        assert "l.column_name IN ('antiquity'," in post
        # a journal row of another column holds nothing: it must not count as landed
        assert "ELSE false END)" in post
        reads = A.rollback_rehearsal_reads([card_cell()], CARD)
        assert f"('{SITE_A}'::uuid, 'mystery', '6')" in reads
        assert "WHEN 'mystery' THEN t.mystery IS NOT DISTINCT FROM p.written::integer" in reads
        assert "ELSE false END\n" in reads

    def test_the_probes_read_another_source_s_site_without_a_column(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cell lane's guard-1 probe needs only a site of another source (and its premise): the
        cells keep their own values, so no column of the foreign row is read."""
        sent: list[str] = []

        def reader() -> Any:
            def read(sql: str) -> list[dict[str, Any]]:
                sent.append(sql)
                raise P.PlanError("stop")

            return read

        monkeypatch.setattr(A, "psql_json_reader", reader)
        with pytest.raises(P.PlanError, match="stop"):
            A.cmd_probe_guards([card_cell()], Path("."), CARD)
        assert sent == [
            f"SELECT u.id::text AS id, u.name, {CARD.premise_sql} AS premise "
            "FROM unified_sites u WHERE u.source_id <> 'ancient_nerds' LIMIT 1"
        ]


# ------------------------------------------------------------------------------ the reversal
class TestTheReversalOfACellPlan:
    def test_the_undo_restores_null_where_the_lane_filled_it(self) -> None:
        (undo,) = P.reversed_records([cell()], L.SCOPE)
        assert (undo.old_value, undo.new_value, undo.column) == ("retired", None, "scope_status")
        assert undo.reason.startswith("rollback of scope-e4: scope_status None restored")

    def test_the_undo_of_a_reversal_names_no_journal_row(self) -> None:
        (undo,) = P.reversed_records([reversal_cell()], L.REVERSAL_1)
        assert undo.journal_id is None and (undo.old_value, undo.new_value) == (
            "Afghanistan",
            "Pakistan",
        )

    def test_a_plan_record_names_its_table_key_and_cell(self) -> None:
        verdict = P.Verdict(
            site_id=SITE_A,
            site_name="a site",
            ok=True,
            old_value="5",
            new_value="6",
            rule="generator-recompute",
            reason="",
            note="mystery 5 -> 6",
            phase3=False,
            finding_test_id="live:card_stats",
            evidence=({"source": "t", "quote": "x"},),
            premise="p",
            column="mystery",
        )
        record = P.plan_record(verdict, P.Plan(changes=(verdict,), skipped=(), lane=CARD))
        assert (record["table"], record["column"], record["key_column"]) == (
            "card_stats",
            "mystery",
            "site_id",
        )
        assert record["change_key"] == f"card-stats-2026-09-23:{SITE_A}:mystery"
        assert "premise_sql" not in record and record["premise"] == "p"
        with pytest.raises(ValueError, match="is not a column this lane writes"):
            P.plan_record(replace(verdict, column="name"), P.Plan((verdict,), (), lane=CARD))

    def test_a_reversal_record_carries_its_journal_row(self) -> None:
        verdict = P.Verdict(
            site_id=SITE_B,
            site_name="x",
            ok=True,
            old_value="Pakistan",
            new_value="Afghanistan",
            rule="journal-reversal",
            reason="",
            note="n",
            phase3=True,
            finding_test_id="journal:28384",
            evidence=({"source": "t", "quote": "x"},),
            column="country",
            journal_id=28384,
        )
        plan = P.Plan(changes=(verdict,), skipped=(), lane=L.REVERSAL_1)
        assert P.plan_record(verdict, plan)["journal_id"] == 28384
        with pytest.raises(P.PlanError, match="needs the journal row it undoes"):
            P.plan_record(replace(verdict, journal_id=None), plan)


# ------------------------------------------------------------------------------ the probes
FOREIGN = {"id": "11111111-1111-1111-1111-111111111111", "name": "Somewhere", "premise": "p"}


class TestTheCellProbes:
    @pytest.mark.parametrize("which", ["card", "scope", "reversal"])
    def test_each_corrupted_value_is_valid_in_its_column_s_type(self, which: str) -> None:
        """A probe value the column's cast refuses would stop at `invalid input syntax for type
        integer` - psql's refusal, not its guard's - and the probe would prove nothing."""
        lane, records = {
            "card": (
                CARD,
                [
                    card_cell(column="rarity_tier", old_value="2", new_value="3"),
                    card_cell(column="category_group", old_value="Other", new_value="Monuments"),
                    card_cell(column="empires", old_value="[]", new_value='["roman"]'),
                ],
            ),
            "scope": (L.SCOPE, [cell(), cell(column="scope_reason", new_value="E3")]),
            "reversal": (
                L.REVERSAL_1,
                [
                    reversal_cell(),
                    reversal_cell(
                        column="period_start",
                        old_value="-2500",
                        new_value="-3000",
                        site_id=SITE_A,
                        journal_id=28018,
                    ),
                ],
            ),
        }[which]
        for _suffix, _, mutated, _ in A.probe_cases(records, lane, FOREIGN):
            for r in mutated:
                if r.column not in lane.columns:
                    continue
                for value in (r.old_value, r.new_value):
                    if value is not None:
                        A.typed_value(lane.cell(r.column), value)

    def test_the_probes_match_the_guards_each_lane_renders(self) -> None:
        card = {
            c[0]
            for c in A.probe_cases(
                [card_cell(column="rarity_tier", old_value="2", new_value="3")], CARD, FOREIGN
            )
        }
        assert {"guard4-not-owned", "guard5-premise", "guard2-foreign-column"} <= card
        assert "guard6-journal-row" not in card
        reversal = {c[0] for c in A.probe_cases([reversal_cell()], L.REVERSAL_1, FOREIGN)}
        assert "guard6-journal-row" in reversal and "guard2-too-long" in reversal
        assert "guard5-premise" not in reversal and "guard4-not-owned" not in reversal
        scope = {c[0] for c in A.probe_cases([cell()], L.SCOPE, FOREIGN)}
        assert "guard2-too-long" not in scope, "neither scope column has a width"

    def test_the_foreign_column_probe_names_a_column_the_lane_does_not_own(self) -> None:
        (_, _, mutated, says) = next(
            c
            for c in A.probe_cases([card_cell()], CARD, FOREIGN)
            if c[0] == "guard2-foreign-column"
        )
        assert mutated[0].column not in CARD.columns and says == A.refusal(A.GUARD2_SAYS)

    def test_the_other_source_probe_keeps_the_cell_and_swaps_the_site(self) -> None:
        (_, _, mutated, _) = next(
            c for c in A.probe_cases([card_cell()], CARD, FOREIGN) if c[0] == "guard1-other-source"
        )
        assert mutated[0].site_id == FOREIGN["id"] and mutated[0].column == "mystery"
        assert mutated[0].premise == "p"
