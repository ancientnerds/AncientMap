"""Lane WB, the write side: the two lanes of a step, their plan, the acceptance and the card file.

`mechanical/teaser.py` plans a run's outcomes as two cell lanes per step of at most 100 sites -
`teaser-prov-sNNN` (`unified_sites.raw_data`) and `teaser-card-sNNN` (`card_stats.card_description`,
the first lane that may clear its column). `mechanical/apply.py` writes them like every other lane.
DB-less: production is a fixture export, the SQL is asserted as rendered text. Each rule is asserted
by the refusal it produces (`mechanical/mutation_sweep.py "teaser:"`).
"""

from __future__ import annotations

import json
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
from mechanical import plan as MP  # noqa: E402
from mechanical import teaser as W  # noqa: E402
from phase4 import card_json as CJ  # noqa: E402

from pipeline.utils import card_provenance as CP  # noqa: E402
from tests.remediation import teaser_cases as T  # noqa: E402

PROV = W.teaser_lane(W.PROV, 1)
CARD = W.teaser_lane(W.CARD, 1)
P5_KEY = {"lane": "W", "desc_sha256": "0" * 64, "card": {"items": [], "text_sha256": "1" * 64}}


def outcome(site_id: str = T.SKARA, status: str = W.ACCEPTED, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "site_id": site_id,
        "name": T.NAMES[site_id],
        "desc_sha256": T.sha(T.DESCRIPTIONS.get(site_id) or ""),
        "status": status,
        "reason": None if status == W.ACCEPTED else "failed-after-two-rewrites",
        "card": T.GOOD.get(site_id) if status == W.ACCEPTED else None,
        "writer": {"stage": "write", "answered_by": "teaser-write-001", "answered_at": "t"}
        if status == W.ACCEPTED
        else None,
        "provenance": T.teaser(site_id) if status == W.ACCEPTED else None,
        "findings": [] if status == W.ACCEPTED else [{"card": "x", "reasons": ["Unsupported."]}],
        "attempts": 1 if status == W.ACCEPTED else 3,
    }
    base.update(over)
    return base


def live(site_id: str = T.SKARA, **over: Any) -> W.Live:
    raw = {"description_citations": [], "_description_provenance": P5_KEY}
    base = W.Live(
        site_id=site_id,
        name=T.NAMES[site_id],
        description=T.DESCRIPTIONS.get(site_id),
        scope_status=None,
        raw_data=json.dumps(raw, ensure_ascii=False),
        has_card_row=True,
        card=T.OLD_CARD,
    )
    return replace(base, **over)


# ------------------------------------------------------------------------------ the lanes
class TestTheLanes:
    def test_each_step_has_its_own_two_lanes(self) -> None:
        assert (PROV.name, PROV.run_stamp) == ("teaser-prov-s001", "wb-teaser-prov-s001")
        assert (CARD.name, CARD.run_stamp) == ("teaser-card-s001", "wb-teaser-card-s001")
        assert PROV.target is L.UNIFIED_SITES and CARD.target is L.CARD_STATS
        assert CARD.out_dir_name == "mechanical_teaser/s001/card"
        assert W.teaser_lane(W.CARD, 12).rollback_run_stamp == "wb-teaser-card-s012-rollback"
        with pytest.raises(ValueError, match="1-999"):
            W.teaser_lane(W.CARD, 1000)

    def test_only_the_card_column_is_cleared(self) -> None:
        (card,) = CARD.cells
        assert card.clears and card.fills_null and card.max_chars == 200
        (raw,) = PROV.cells
        assert not raw.clears and raw.fills_null

    def test_the_lanes_resolve_by_name_for_apply(self) -> None:
        assert L.resolve_lane("teaser-card-s007") == W.teaser_lane(W.CARD, 7)
        assert L.resolve_lane("teaser-prov-s007") == W.teaser_lane(W.PROV, 7)
        with pytest.raises(KeyError):
            L.resolve_lane("teaser-card-7")
        assert A.readback_for(CARD) == W.teaser_readback(CARD)
        assert "curated sites carrying a teaser provenance" in A.readback_for(CARD)

    def test_the_planner_reads_the_outcomes_in_the_run_cli_s_spelling(self) -> None:
        from teaser import run as R

        assert (W.RUNS, W.ACCEPTED, W.CLEARED) == (R.RUNS, R.ACCEPTED, R.CLEARED)
        assert W.lane_of("teaser-prov-s003") == W.teaser_lane(W.PROV, 3)

    def test_the_premises_are_the_description_and_the_provenance(self) -> None:
        assert PROV.premise_sql == L.ORPHAN_CITATIONS.premise_sql
        assert CARD.premise_sql.startswith(
            "coalesce(u.raw_data -> '_card_provenance' ->> 'text_sha256', '') || '|' || "
        )


# ------------------------------------------------------------------------------ the clear
def card_record(old: str | None, new: str | None, **over: Any) -> A.ChangeRecord:
    base = A.ChangeRecord(
        site_id=T.SKARA,
        site_name="Skara Brae",
        old_value=old,
        new_value=new,
        rule="teaser-card",
        condition="c",
        reason="r",
        evidence=({"source": "s", "quote": "q"},),
        premise="a|b|c",
        column="card_description",
    )
    return replace(base, **over)


class TestTheClear:
    def test_a_clear_and_its_reversal_are_valid_on_the_card_lane(self) -> None:
        A.validate_records([card_record(T.OLD_CARD, None)], lane=CARD)
        A.validate_records([card_record(None, T.OLD_CARD)], lane=CARD, rollback=True)

    def test_a_lane_that_does_not_clear_refuses_a_null(self) -> None:
        record = card_record("x", None, column="raw_data")
        with pytest.raises(MP.PlanError, match="never clears a column"):
            A.validate_records([record], lane=PROV)

    def test_null_to_null_is_never_a_change(self) -> None:
        with pytest.raises(MP.PlanError, match="NULL to NULL"):
            A.validate_records([card_record(None, None)], lane=CARD)

    def test_guard_2_lets_the_card_lane_write_null_and_nothing_else(self) -> None:
        sql = A.render_transaction([card_record(T.OLD_CARD, None)], site_ids=[T.SKARA], lane=CARD)
        guard2 = sql.split("scope guard 2")[1].split("scope guard 3")[0]
        assert "p.new_value IS NULL" not in guard2
        assert "p.new_value::character varying IS NOT DISTINCT FROM" in guard2
        assert "length(p.new_value) > 200" in guard2
        prov = A.render_transaction(
            [card_record("{}", '{"a": 1}', column="raw_data")], site_ids=[T.SKARA], lane=PROV
        )
        assert "p.new_value IS NULL" in prov.split("scope guard 2")[1].split("scope guard 3")[0]


# ------------------------------------------------------------------------------ the decision
class TestTheDecision:
    def test_an_accepted_card_writes_its_provenance_and_the_card(self) -> None:
        prov, card = W.classify(outcome(), live(), {}, "wb-test")
        written = json.loads(prov.new_value)
        assert CP.validate(written["_card_provenance"]) == T.teaser(T.SKARA)
        assert written["_description_provenance"]["card"] is None
        assert written["description_citations"] == []
        assert prov.premise == T.sha(T.DESCRIPTIONS[T.SKARA])
        assert (card.old_value, card.new_value) == (T.OLD_CARD, T.GOOD[T.SKARA])
        text_sha = T.sha(T.GOOD[T.SKARA])
        desc_sha = T.sha(T.DESCRIPTIONS[T.SKARA])
        assert card.premise == f"{text_sha}|{desc_sha}|{desc_sha}"
        assert card.evidence[1]["quote"].startswith("the site's main facts [S1]")

    def test_a_cleared_card_removes_the_teaser_provenance_and_writes_null(self) -> None:
        raw = json.dumps({"_card_provenance": T.teaser(T.SKARA)}, ensure_ascii=False)
        prov, card = W.classify(outcome(status=W.CLEARED), live(raw_data=raw), {}, "wb-test")
        assert json.loads(prov.new_value) == {}
        assert card.new_value is None
        assert card.premise == f"||{T.sha(T.DESCRIPTIONS[T.SKARA])}"

    def test_a_clear_without_anything_to_remove_writes_only_the_card(self) -> None:
        prov, card = W.classify(outcome(status=W.CLEARED), live(raw_data=None), {}, "wb-test")
        assert prov is None and card.new_value is None

    def test_nothing_to_change_is_listed(self) -> None:
        decided = W.classify(
            outcome(status=W.CLEARED), live(raw_data=None, card=None), {}, "wb-test"
        )
        assert decided.reason == W.NOTHING_TO_CHANGE

    def test_a_null_raw_data_gets_an_object(self) -> None:
        prov, _card = W.classify(outcome(), live(raw_data=None), {}, "wb-test")
        assert prov.old_value is None
        assert set(json.loads(prov.new_value)) == {"_card_provenance"}

    @pytest.mark.parametrize(
        ("change", "reason"),
        [
            ({"description": "A description edited after the check."}, W.STALE_DESCRIPTION),
            ({"scope_status": "retired"}, W.SITE_RETIRED),
            ({"has_card_row": False}, W.NO_CARD_ROW),
            ({"raw_data": "[1, 2]"}, W.RAW_DATA_NOT_OBJECT),
            ({"raw_data": '{"a":1}'}, W.NOT_REPRINTED),
        ],
    )
    def test_a_site_that_changed_is_listed_not_written(self, change: dict, reason: str) -> None:
        assert W.classify(outcome(), live(**change), {}, "wb-test").reason == reason

    def test_a_site_the_export_did_not_return_is_listed(self) -> None:
        assert W.classify(outcome(), None, {}, "wb-test").reason == W.NOT_CURATED

    def test_a_cell_whose_journal_does_not_end_at_the_live_value_is_listed(self) -> None:
        link = MP.JournalLink(1, "phase5:p5-0001:chunk-0001", "P5/card", None, "Another card.")
        decided = W.classify(outcome(), live(), {(T.SKARA, "card_description"): [link]}, "r")
        assert decided.reason == "journal-disagrees"

    def test_the_raw_data_journal_is_compared_as_json(self) -> None:
        raw = live().raw_data
        reordered = json.dumps(dict(reversed(list(json.loads(raw).items()))))
        link = MP.JournalLink(1, "phase4l:p4l-0001:chunk-0001", "P4/l", None, reordered)
        decided = W.classify(outcome(), live(), {(T.SKARA, "raw_data"): [link]}, "r")
        assert not isinstance(decided, MP.Verdict)

    def test_a_step_writes_at_most_100_sites(self) -> None:
        many = [outcome(site_id=T.SKARA)] * 101
        with pytest.raises(MP.PlanError, match="at most 100"):
            W.build_step(1, "r", many, {}, {}, built_at="t")


# ------------------------------------------------------------------------------ plan and accept
def export_for(lives: list[W.Live], journal: list[dict] | None = None) -> str:
    return T.tagged(
        {
            "site": [
                {
                    "site_id": s.site_id,
                    "name": s.name,
                    "description": s.description,
                    "scope_status": s.scope_status,
                    "raw_data": s.raw_data,
                    "has_card_row": s.has_card_row,
                    "card": s.card,
                }
                for s in lives
            ],
            "journal": journal or [],
        }
    )


OUTCOMES = [outcome(T.SKARA), outcome(T.NEWGRANGE, status=W.CLEARED)]
LIVES = [live(T.SKARA), live(T.NEWGRANGE)]


def planned(tmp_path: Path) -> Path:
    root = tmp_path / "mechanical_teaser"
    W.plan_step("wb-test", 1, read=lambda _sql: export_for(LIVES), root=root, outcomes=OUTCOMES)
    return root


def closed(root: Path, step: int = 1, *, reverted: bool = False) -> None:
    """The closing record `accept` (written) or `close-reverted` (undone) leaves."""
    W._record_acceptance(step, root, {"reverted": reverted})


class TestThePlan:
    def test_a_step_writes_both_lanes_and_their_undo(self, tmp_path: Path) -> None:
        root = planned(tmp_path)
        for kind, cells in ((W.PROV, 2), (W.CARD, 2)):
            rows = A.load_records(root / "s001" / kind / "PLAN.jsonl")
            assert len(rows) == cells
            A.validate_records(rows, lane=W.teaser_lane(kind, 1))
            undo = (root / "s001" / kind / "ROLLBACK.sql").read_text(encoding="utf-8")
            assert undo.startswith("-- plan sha256 ")
            assert f"wb-teaser-{kind}-s001-rollback" in undo
        steps = W.read_steps(root)
        assert steps[0]["outcomes"] == sorted([T.SKARA, T.NEWGRANGE])

    def test_the_next_step_waits_for_the_acceptance_of_the_last(self, tmp_path: Path) -> None:
        root = planned(tmp_path)
        more = [outcome(T.STONEHENGE)]
        with pytest.raises(MP.PlanError, match="step 1 has no acceptance"):
            W.plan_step("wb-test", 2, read=lambda _: "", root=root, outcomes=[*OUTCOMES, *more])
        with pytest.raises(MP.PlanError, match="the next step is 2"):
            W.plan_step("wb-test", 3, read=lambda _: "", root=root, outcomes=more)

    def test_a_planned_site_is_not_planned_again(self) -> None:
        steps = [{"step": 1, "run": "wb-test", "outcomes": [T.SKARA]}]
        assert [o["site_id"] for o in W.next_outcomes("wb-test", OUTCOMES, steps)] == [T.NEWGRANGE]
        again = W.next_outcomes("wb-test", OUTCOMES, steps, frozenset({1}))
        assert [o["site_id"] for o in again] == sorted([T.SKARA, T.NEWGRANGE])


def written_state() -> tuple[list[W.Live], list[dict[str, Any]]]:
    """Production after both lanes of step 1 were applied as planned."""
    prov, card = W.classify(outcome(), live(), {}, "wb-test")
    skara = live(raw_data=prov.new_value, card=card.new_value)
    newgrange_prov, newgrange_card = W.classify(
        outcome(T.NEWGRANGE, status=W.CLEARED), live(T.NEWGRANGE), {}, "wb-test"
    )
    newgrange = live(T.NEWGRANGE, raw_data=newgrange_prov.new_value, card=None)
    journal = [
        {"row_pk": v.site_id, "column_name": v.column, "run_stamp": stamp,
         "old_value": v.old_value, "new_value": v.new_value}
        for v, stamp in (
            (prov, PROV.run_stamp), (card, CARD.run_stamp),
            (newgrange_prov, PROV.run_stamp), (newgrange_card, CARD.run_stamp),
        )
    ]  # fmt: skip
    return [skara, newgrange], journal


class TestTheAcceptance:
    def _accept(self, tmp_path: Path, lives: list[W.Live], journal: list[dict]) -> tuple:
        root = planned(tmp_path)
        run_dir = tmp_path / "runs" / "wb-test"
        run_dir.mkdir(parents=True)
        (run_dir / "OUTCOMES.jsonl").write_text(
            "".join(json.dumps(o) + "\n" for o in OUTCOMES), encoding="utf-8"
        )
        original = W.RUNS
        W.RUNS = tmp_path / "runs"
        try:
            code, found = W.accept_step(1, read=lambda _sql: export_for(lives, journal), root=root)
        finally:
            W.RUNS = original
        return code, found, root

    def test_the_written_step_is_accepted(self, tmp_path: Path) -> None:
        lives, journal = written_state()
        code, found, root = self._accept(tmp_path, lives, journal)
        assert (code, found) == (0, [])
        assert W.accepted(1, root)

    def test_an_acceptance_is_recorded_once(self, tmp_path: Path) -> None:
        lives, journal = written_state()
        _code, _found, root = self._accept(tmp_path, lives, journal)
        path = root / "ACCEPTED" / "step-001.json"
        path.write_text('{"step": 1, "reverted": false, "first": true}', encoding="utf-8")
        run_dir = tmp_path / "runs"
        original = W.RUNS
        W.RUNS = run_dir
        try:
            code, found = W.accept_step(1, read=lambda _sql: export_for(lives, journal), root=root)
        finally:
            W.RUNS = original
        assert (code, found) == (0, [])
        assert json.loads(path.read_text(encoding="utf-8"))["first"] is True

    def test_a_card_that_does_not_hold_is_a_deviation(self, tmp_path: Path) -> None:
        lives, journal = written_state()
        lives[0] = replace(lives[0], card="Another card.")
        code, found, root = self._accept(tmp_path, lives, journal)
        assert code == 1 and not W.accepted(1, root)
        assert any("does not hold the planned value" in line for line in found)
        assert any("not the accepted one" in line for line in found)

    def test_a_missing_journal_row_is_a_deviation(self, tmp_path: Path) -> None:
        lives, journal = written_state()
        _code, found, _root = self._accept(tmp_path, lives, journal[1:])
        assert any("journal row(s) for" in line for line in found)

    def test_a_rollback_row_is_a_deviation(self, tmp_path: Path) -> None:
        lives, journal = written_state()
        undo = {**journal[1], "run_stamp": CARD.rollback_run_stamp}
        _code, found, _root = self._accept(tmp_path, lives, [*journal, undo])
        assert any("rollback journal row" in line for line in found)

    def test_a_phase5_card_key_left_behind_is_a_deviation(self, tmp_path: Path) -> None:
        lives, journal = written_state()
        raw = json.loads(lives[0].raw_data)
        raw["_description_provenance"] = P5_KEY
        lives[0] = replace(lives[0], raw_data=json.dumps(raw, ensure_ascii=False))
        _code, found, _root = self._accept(tmp_path, lives, journal)
        assert any("still names a card" in line for line in found)

    def test_a_stale_provenance_is_a_deviation(self, tmp_path: Path) -> None:
        lives, journal = written_state()
        lives[0] = replace(lives[0], description="Edited since.")
        _code, found, _root = self._accept(tmp_path, lives, journal)
        assert any("stale" in line for line in found)


# ------------------------------------------------------------------------------ the undo
def undone_state() -> tuple[list[W.Live], list[dict[str, Any]]]:
    """Production after step 1 was written and both `ROLLBACK.sql` files ran: every cell holds its
    value from before the step again, each write followed by its inverse."""
    _lives, journal = written_state()
    undos = [
        {
            **row,
            "run_stamp": (PROV if row["column_name"] == "raw_data" else CARD).rollback_run_stamp,
            "old_value": row["new_value"],
            "new_value": row["old_value"],
        }
        for row in journal
    ]
    return list(LIVES), [*journal, *undos]


class TestTheUndo:
    def _close(self, tmp_path: Path, lives: list[W.Live], journal: list[dict]) -> tuple:
        root = planned(tmp_path)
        code, found = W.close_reverted(1, read=lambda _sql: export_for(lives, journal), root=root)
        return code, found, root

    def test_an_undone_step_is_closed_and_its_sites_are_planned_again(self, tmp_path: Path) -> None:
        lives, journal = undone_state()
        code, found, root = self._close(tmp_path, lives, journal)
        assert (code, found) == (0, [])
        assert W.accepted(1, root) and W.reverted(1, root)
        record = json.loads((root / "ACCEPTED" / "step-001.json").read_text(encoding="utf-8"))
        assert (record["reversed_cells"], record["unwritten_cells"]) == (4, 0)
        again = W.plan_step(
            "wb-test", 2, read=lambda _sql: export_for(LIVES), root=root, outcomes=OUTCOMES
        )
        assert again["outcomes"] == sorted([T.SKARA, T.NEWGRANGE])

    def test_a_step_never_applied_is_closed_the_same_way(self, tmp_path: Path) -> None:
        code, _found, root = self._close(tmp_path, list(LIVES), [])
        assert code == 0 and W.reverted(1, root)
        record = json.loads((root / "ACCEPTED" / "step-001.json").read_text(encoding="utf-8"))
        assert (record["reversed_cells"], record["unwritten_cells"]) == (0, 4)

    def test_a_write_still_standing_is_refused(self, tmp_path: Path) -> None:
        lives, journal = written_state()
        code, found, root = self._close(tmp_path, lives, journal)
        assert code == 1 and not W.accepted(1, root)
        assert any("does not hold its value from before the step" in line for line in found)
        assert any("1 write(s), 0 reversal(s)" in line for line in found)

    def test_a_reversal_that_is_not_the_inverse_is_refused(self, tmp_path: Path) -> None:
        lives, journal = undone_state()
        journal[-1] = {**journal[-1], "old_value": "Another card."}
        code, found, _root = self._close(tmp_path, lives, journal)
        assert code == 1 and any("not the write's inverse" in line for line in found)

    def test_a_step_is_closed_once(self, tmp_path: Path) -> None:
        lives, journal = undone_state()
        _code, _found, root = self._close(tmp_path, lives, journal)
        with pytest.raises(MP.PlanError, match="closed already"):
            W.close_reverted(1, read=lambda _sql: export_for(lives, journal), root=root)

    def test_the_card_file_names_written_steps_only(self, tmp_path: Path) -> None:
        root = planned(tmp_path)
        closed(root, reverted=True)
        with pytest.raises(MP.PlanError, match="was undone"):
            W.card_file(tmp_path / "unused.json", [1], run_sql=lambda _sql: "", root=root)


# ------------------------------------------------------------------------------ the card file
class TestTheCardFile:
    def _file(self, tmp_path: Path, cards: dict[str, str]) -> Path:
        path = tmp_path / "card_descriptions.json"
        path.write_text(CJ.canonical({CJ.TOP_KEY: cards}), encoding="utf-8", newline="\n")
        return path

    def _live(self, cards: dict[str, str | None]) -> Any:
        rows = "".join(
            json.dumps({"id": site, "card": card}) + "\n" for site, card in cards.items()
        )
        return lambda _sql: rows

    def test_the_file_follows_production_after_an_accepted_step(self, tmp_path: Path) -> None:
        root = planned(tmp_path)
        closed(root)
        path = self._file(tmp_path, {T.SKARA: T.OLD_CARD, T.NEWGRANGE: T.OLD_CARD})
        live_cards = {T.SKARA: T.GOOD[T.SKARA], T.NEWGRANGE: None}
        result = W.card_file(path, [1], run_sql=self._live(live_cards), root=root)
        assert (result["changed"], result["removed"]) == (1, 1)
        assert CJ.read_cards(path) == {T.SKARA: T.GOOD[T.SKARA]}

    def test_a_step_without_acceptance_is_refused(self, tmp_path: Path) -> None:
        root = planned(tmp_path)
        path = self._file(tmp_path, {})
        with pytest.raises(MP.PlanError, match="no acceptance"):
            W.card_file(path, [1], run_sql=self._live({}), root=root)

    def test_a_card_the_steps_did_not_write_is_refused(self, tmp_path: Path) -> None:
        root = planned(tmp_path)
        closed(root)
        path = self._file(tmp_path, {T.SKARA: T.OLD_CARD, T.NEWGRANGE: T.OLD_CARD, T.SACSAY: "a"})
        live_cards = {T.SKARA: T.GOOD[T.SKARA], T.NEWGRANGE: None, T.SACSAY: "b"}
        with pytest.raises(MP.PlanError, match="did not write"):
            W.card_file(path, [1], run_sql=self._live(live_cards), root=root)

    def test_a_planned_card_production_does_not_hold_is_refused(self, tmp_path: Path) -> None:
        root = planned(tmp_path)
        closed(root)
        path = self._file(tmp_path, {T.SKARA: T.OLD_CARD, T.NEWGRANGE: T.OLD_CARD})
        live_cards = {T.SKARA: T.OLD_CARD, T.NEWGRANGE: None}
        with pytest.raises(MP.PlanError, match="not in production"):
            W.card_file(path, [1], run_sql=self._live(live_cards), root=root)


class TestStale:
    def test_stale_and_moved_cards_are_counted(self) -> None:
        rows = [
            {"site_id": T.SKARA, "name": "Skara Brae", "stale": True, "card_moved": False},
            {"site_id": T.SACSAY, "name": "Sacsayhuamán", "stale": False, "card_moved": True},
        ]
        result = W.stale(read=lambda _sql: T.tagged({"site": rows}))
        assert (result["teasers"], result["stale"], result["card_moved"]) == (2, 1, 1)
