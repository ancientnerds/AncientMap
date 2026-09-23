"""Does the Phase-4/5 writer change exactly what the design allows, journalled, and nothing else?

`scripts/remediation/phase4/write4.py` (WB-D2) plans and renders the only Phase-4/5 changes to the
production database; `revert4.py` reverses them from the journal; `output/remediation/tools/
write_gate4.py` runs them in steps of 100 sites. The mistakes worth a test are the quiet ones:

* a site that is held, in a lane whose pilot has not passed, unaudited in lane T or R, or held by
  the verifier being written anyway;
* the verifier judging other bytes than the row writes (its `new_raw_data` must be the row's);
* a written description without its quotes in the journal, so the database alone could no longer
  re-verify it;
* half a P4 site (description without raw_data), a row outside its group's allow-list, a change key
  that is not the row's digest;
* a transaction without one of its guards or invariants, a statement run for another plan, a chunk
  written although a row moved or its stamp was used before, a rehearsal that leaves a trace;
* a reversal that touches phase 3, reverts a reversal, or reverts twice.

Each guard has a test that fails without it; the mutation cases are `PHASE4_WRITE_MUTATIONS` in
`scripts/remediation/phase3/mutation_sweep.py`. The one database seam is a fake psql that parses
what it is given (`phase4_write_fixtures.FakeDb`). Nothing here opens a socket or starts a process.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import write_gate4 as G  # noqa: E402
from phase4 import revert4 as R  # noqa: E402

from tests.remediation import phase4_write_fixtures as FX  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4, M, W  # noqa: E402

OPEN_WS = frozenset({M.Lane.W, M.Lane.S})


def _batch(tmp_path: Path, **kwargs):
    return W4.load_batch(FX.write_batch(tmp_path, **kwargs))


def _p4(batch, *, verify=None, open_lanes=OPEN_WS, audited=frozenset(), ledger=None):
    return W4.plan_p4(
        batch,
        open_lanes=open_lanes,
        audited=audited,
        verify=verify or FX.Verify(),
        ledger=FX.ledger_rows(FX.SITE_A, FX.SITE_B) if ledger is None else ledger,
    )


def _hold(site_id: str, reason: M.HoldReason, scope: M.HoldScope = M.HoldScope.SITE) -> M.Hold:
    return M.Hold(site_id=site_id, scope=scope, reason=reason, detail="the detail")


def _db(*site_ids: str, **fields) -> FX.FakeDb:
    return FX.FakeDb(
        {
            site_id: FX.Site(raw_data=json.loads(json.dumps(FX.OLD_RAW)), **fields)
            for site_id in site_ids
        }
    )


def _written(tmp_path: Path, plan: W4.WritePlan4, *, write_round: int = 1):
    chunk = W4.chunk_for(plan, write_round=write_round)
    out = tmp_path / "apply" / plan.batch_id
    W4.write_plan_files(out, plan, chunk)
    return chunk, out


# ── values ───────────────────────────────────────────────────────────────────────────────────────


def test_new_raw_data_replaces_the_citations_adds_the_provenance_and_keeps_the_rest() -> None:
    old = {"description_citations": [{"n": 1, "claim": "x"}], "title_es": "Templos"}
    new = W4.new_raw_data(old, FX.assembly())
    assert set(new) == {"description_citations", "title_es", M.PROVENANCE_KEY}
    assert new["title_es"] == "Templos"
    assert new["description_citations"] == [c.to_dict() for c in FX.assembly().citations]
    assert new[M.PROVENANCE_KEY] == FX.assembly().provenance.to_dict()
    assert old == {"description_citations": [{"n": 1, "claim": "x"}], "title_es": "Templos"}
    assert set(W4.new_raw_data(None, FX.assembly())) == {"description_citations", M.PROVENANCE_KEY}


def test_raw_data_is_serialised_with_sorted_keys_and_unescaped_text() -> None:
    assert W4.raw_json({"b": "Türkiye", "a": 1}) == '{"a": 1, "b": "Türkiye"}'


# ── P4: who is written ───────────────────────────────────────────────────────────────────────────


def test_a_clean_site_gets_its_description_and_raw_data_rows(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    plan = _p4(batch)
    assert plan.batch_id == "p4-0003" and not plan.refusals
    description, raw = plan.rows
    assert (description.column, description.test_id) == ("description", "P4/description")
    assert (description.old_value, description.new_value) == (FX.OLD_DESCRIPTION, FX.DESCRIPTION)
    assert (raw.column, raw.test_id) == ("raw_data", "P4/raw_data")
    assert json.loads(raw.old_value) == FX.OLD_RAW
    assert json.loads(raw.new_value) == W4.new_raw_data(FX.OLD_RAW, FX.assembly())
    assert description.change_key.startswith("phase4:") and raw.change_key.startswith("phase4:")


def test_a_site_on_a_hold_list_is_refused_not_written(tmp_path: Path) -> None:
    held = _hold(FX.SITE_B, M.HoldReason.V9)
    batch = _batch(
        tmp_path,
        sites=[FX.plan_site(), FX.plan_site(FX.SITE_B)],
        assemblies=[FX.assembly(), FX.assembly(FX.SITE_B)],
        holds=[held],
    )
    plan = _p4(batch)
    assert {row.site_id for row in plan.rows} == {FX.SITE_A}
    assert [(r.site_id, r.rule) for r in plan.refusals] == [(FX.SITE_B, W4.RULE_HELD)]
    assert "V9" in plan.refusals[0].detail


def test_a_held_card_writes_the_description_with_card_null(tmp_path: Path) -> None:
    card_hold = _hold(FX.SITE_A, M.HoldReason.AUDIT_NOT_CONTAINED, M.HoldScope.CARD)
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()], holds=[card_hold])
    verify = FX.Verify()
    plan = _p4(batch, verify=verify)
    raw = json.loads(plan.rows[1].new_value)
    assert raw[M.PROVENANCE_KEY]["card"] is None
    assert verify.calls[0]["assembly"].card is None  # the verifier judged what is written
    assert plan.rows[0].evidence["card_holds"][0]["reason"] == "audit-not-contained"


def test_a_lane_whose_pilot_has_not_passed_is_refused(tmp_path: Path) -> None:
    batch = _batch(
        tmp_path,
        sites=[FX.plan_site()],
        assemblies=[FX.assembly(lane=M.Lane.S)],
        lanes={FX.SITE_A: M.Lane.S},
    )
    plan = _p4(batch, open_lanes=frozenset({M.Lane.W}))
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_LANE_CLOSED


def test_lanes_t_and_r_are_written_only_after_the_independent_audit(tmp_path: Path) -> None:
    translated = dataclasses.replace(FX.assembly(), provenance=_t_provenance())
    batch = _batch(
        tmp_path,
        sites=[FX.plan_site()],
        assemblies=[translated],
        lanes={FX.SITE_A: M.Lane.T},
    )
    t_open = frozenset({M.Lane.W, M.Lane.T})
    assert _p4(batch, open_lanes=t_open).refusals[0].rule == W4.RULE_NOT_AUDITED


def _t_provenance() -> M.Provenance:
    base = FX.assembly().provenance
    return dataclasses.replace(
        base,
        lane=M.Lane.T,
        ai=M.AiMark.GENERATED,
        attribution=dataclasses.replace(base.attribution, changes=M.Changes.TRANSLATED),
    )


def test_the_verifier_is_shown_exactly_the_bytes_the_rows_write(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    verify = FX.Verify()
    plan = _p4(batch, verify=verify)
    call = verify.calls[0]
    assert call["new_raw_data"] == json.loads(plan.rows[1].new_value)
    assert call["quotes"] == [FX.TEXT[FX.S1[0] : FX.S1[1]], FX.TEXT[FX.S2[0] : FX.S2[1]]]
    assert call["texts"] == {"W": FX.TEXT}
    assert call["metas"]["W"] == FX.source_doc().to_dict()


def test_a_verifier_hold_refuses_the_site(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    verify = FX.Verify({FX.SITE_A: [_hold(FX.SITE_A, M.HoldReason.V4)]})
    plan = _p4(batch, verify=verify)
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_VERIFY
    assert "V4" in plan.refusals[0].detail


def test_a_site_without_its_prompts_on_disk_is_refused(tmp_path: Path) -> None:
    batch = _batch(
        tmp_path,
        sites=[FX.plan_site()],
        assemblies=[FX.assembly()],
        model_folders=("answers", "reviews"),
    )
    plan = _p4(batch)
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_EVIDENCE
    assert "prompts" in plan.refusals[0].detail


def test_a_site_whose_calls_are_not_in_the_ledger_is_refused(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    plan = _p4(batch, ledger=FX.ledger_rows(FX.SITE_A, batch="p4-0099"))
    assert not plan.rows and "ledger" in plan.refusals[0].detail


def test_the_journal_carries_every_published_sentences_quote(tmp_path: Path) -> None:
    """C3 re-verifies production against `sentences[i].quote`: the quote is the store's slice."""
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    evidence = _p4(batch).rows[0].evidence
    assert [s["quote"] for s in evidence["sentences"]] == [
        FX.TEXT[FX.S1[0] : FX.S1[1]],
        FX.TEXT[FX.S2[0] : FX.S2[1]],
    ]
    assert evidence["sentences"][0] == {
        "n": 1,
        "src": "W",
        "quote": FX.TEXT[FX.S1[0] : FX.S1[1]],
        "start": FX.S1[0],
        "end": FX.S1[1],
        "drop": [],
    }
    assert evidence["subject_gate"] == {"W": "own"}
    assert evidence["sources"][0]["revid"] == FX.REVID
    assert {f["folder"] for f in evidence["model_files"]} == set(W4.MODEL_FOLDERS)
    assert evidence["reviewer_lines"] == ["R1: KEEP", "R2: KEEP", "CARD: KEEP"]
    assert evidence["ledger_labels"] == [f"{FX.SITE_A}/selector", f"{FX.SITE_A}/reviewer"]


def test_a_quote_never_reaches_public_raw_data(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    raw = _p4(batch).rows[1].new_value
    assert FX.TEXT[FX.S1[0] : FX.S1[1]] not in raw


def test_a_batch_where_a_site_reached_no_outcome_is_a_hole_not_a_refusal(tmp_path: Path) -> None:
    with pytest.raises(W4.PlanInputError, match="neither an assembly nor a site hold"):
        _batch(
            tmp_path, sites=[FX.plan_site(), FX.plan_site(FX.SITE_B)], assemblies=[FX.assembly()]
        )


def test_a_site_assembled_in_another_lane_than_assigned_is_refused_loudly(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly(lane=M.Lane.S)])
    with pytest.raises(W4.PlanInputError, match="never changes lane"):
        _p4(batch)


def test_input_json_must_name_its_own_directory(tmp_path: Path) -> None:
    batch_dir = FX.write_batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    moved = batch_dir.rename(tmp_path / "p4-0004")
    with pytest.raises(W4.PlanInputError, match="names batch"):
        W4.load_batch(moved)


# ── validate_rows: the plan-side mirror of the guards ────────────────────────────────────────────


def _rows(tmp_path: Path) -> list[W4.Row4]:
    return _p4(_batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])).rows


def test_a_p4_site_is_written_description_and_raw_data_together(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    with pytest.raises(W.WriteRefused, match="site-atomic"):
        W4.validate_rows(W4.Group.P4, rows[:1])


def test_a_change_key_that_is_not_the_rows_phase4_digest_is_refused(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    phase3_key = dataclasses.replace(
        rows[0],
        change_key=W.change_key(
            site_id=FX.SITE_A,
            table="unified_sites",
            column="description",
            old_value=rows[0].old_value,
            new_value=rows[0].new_value,
            test_id="P4/description",
        ),
    )
    with pytest.raises(W.WriteRefused, match="digest"):
        W4.validate_rows(W4.Group.P4, [phase3_key, rows[1]])


def test_a_row_outside_its_groups_allow_list_is_refused(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    with pytest.raises(W.WriteRefused, match="not a L row"):
        W4.validate_rows(W4.Group.L, [dataclasses.replace(r, group=W4.Group.L) for r in rows[:1]])


def test_a_provenance_whose_hash_is_not_the_written_description_is_refused(tmp_path: Path) -> None:
    rows = _rows(tmp_path)
    other = W4.make_row(
        group=W4.Group.P4,
        site=FX.plan_site(),
        column="description",
        old_value=FX.OLD_DESCRIPTION,
        new_value="Another text [1].",
        test_id=W4.TEST_DESCRIPTION,
        evidence=rows[0].evidence,
    )
    with pytest.raises(W.WriteRefused, match="desc_sha256"):
        W4.validate_rows(W4.Group.P4, [other, rows[1]])


def test_only_a_card_clear_writes_null(tmp_path: Path) -> None:
    null_card = W4.make_row(
        group=W4.Group.P5,
        site=FX.plan_site(),
        column="card_description",
        old_value=FX.OLD_CARD,
        new_value=None,
        test_id=W4.TEST_CARD,
        evidence={"x": 1},
    )
    with pytest.raises(W.WriteRefused, match="only a card clear"):
        W4.validate_rows(W4.Group.P5, [null_card])


def test_plan_writes_is_each_groups_own_planner_with_its_own_inputs(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    legacy = W4.plan_writes(batch, group=W4.Group.L, written=[FX.SITE_A])
    assert legacy.batch_id == "p4l-0003" and legacy.refusals[0].rule == W4.RULE_WRITTEN
    with pytest.raises(TypeError):
        W4.plan_writes(batch, group=W4.Group.L, written=[], open_lanes=OPEN_WS)
    with pytest.raises(TypeError):
        W4.plan_writes(batch, group=W4.Group.P5, written={})  # card_findings is required


# ── chunks and stamps ────────────────────────────────────────────────────────────────────────────


def test_the_stamps_are_the_designs_three_families() -> None:
    for group, batch, stamp in (
        (W4.Group.P4, "p4-0003", "phase4:p4-0003:chunk-0001"),
        (W4.Group.L, "p4l-0003", "phase4l:p4l-0003:chunk-0001"),
        (W4.Group.P5, "p5-0003", "phase5:p5-0003:chunk-0001"),
    ):
        chunk = W4.Chunk4(group=group, batch_id=batch, write_round=1, rows=())
        assert chunk.stamp == stamp and chunk.rollback_stamp == stamp + "-rollback"
    assert W4.group_batch_id("p4-0003", W4.Group.L) == "p4l-0003"


def test_a_chunk_is_at_most_one_step_of_100_sites(tmp_path: Path) -> None:
    row = _rows(tmp_path)[0]
    many = tuple(
        dataclasses.replace(row, site_id=f"{n:08d}-0000-4000-8000-000000000000") for n in range(101)
    )
    with pytest.raises(W.WriteRefused, match="the step is 100"):
        W4.Chunk4(group=W4.Group.L, batch_id="p4l-0001", write_round=1, rows=many)


def test_a_batch_id_of_another_group_is_refused() -> None:
    with pytest.raises(W.WriteRefused, match="write batch id"):
        W4.Chunk4(group=W4.Group.P5, batch_id="p4-0003", write_round=1, rows=())


# ── the rendered transaction ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def p4_chunk(tmp_path: Path) -> W4.Chunk4:
    plan = _p4(_batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()]))
    return W4.chunk_for(plan)


def test_the_write_is_one_transaction_that_commits(p4_chunk: W4.Chunk4) -> None:
    sql = W4.render_apply(p4_chunk)
    assert sql.index("\\set ON_ERROR_STOP on") < sql.index("BEGIN;") < sql.index("COMMIT;")
    assert "ON COMMIT DROP" in sql and "ROLLBACK;" not in sql
    assert W.pinned_digest(sql) == p4_chunk.digest
    assert "'phase4:p4-0003:chunk-0001'" in sql


def test_the_old_value_guard_compares_every_target_in_its_own_type(p4_chunk: W4.Chunk4) -> None:
    sql = W4.render_apply(p4_chunk)
    guard = sql.split("-- guard 4:", 1)[1].split("FOR r IN", 1)[0]
    assert "u.description IS DISTINCT FROM p.old_value" in guard
    assert "u.raw_data IS DISTINCT FROM p.old_value::jsonb" in guard
    assert "c.card_description IS DISTINCT FROM p.old_value" in guard


def test_the_allow_list_is_rendered_from_the_groups_rows(p4_chunk: W4.Chunk4) -> None:
    sql = W4.render_apply(p4_chunk)
    assert (
        "NOT IN (VALUES ('unified_sites', 'description', 'id', 'P4/description'), "
        "('unified_sites', 'raw_data', 'id', 'P4/raw_data'))"
    ) in sql


def test_the_no_op_guard_compares_raw_data_as_jsonb(p4_chunk: W4.Chunk4) -> None:
    sql = W4.render_apply(p4_chunk)
    assert "p.new_value::jsonb IS NOT DISTINCT FROM p.old_value::jsonb" in sql


def test_both_sha256_invariants_are_inside_the_transaction(p4_chunk: W4.Chunk4) -> None:
    sql = W4.render_apply(p4_chunk)
    body = sql.split("COMMIT;")[0]
    assert (
        "(u.raw_data -> '_description_provenance' ->> 'desc_sha256')\n"
        "           IS DISTINCT FROM encode(sha256(convert_to(u.description, 'UTF8')), 'hex')"
    ) in body
    assert "encode(sha256(convert_to(c.card_description, 'UTF8')), 'hex')" in body
    assert "-> 'card' ->> 'text_sha256'" in body
    assert "WHERE p.column_name = 'card_description' AND p.new_value IS NOT NULL" in body


def test_the_journal_must_agree_with_the_plan_in_both_directions(p4_chunk: W4.Chunk4) -> None:
    sql = W4.render_apply(p4_chunk)
    assert "OR l.site_id_ref IS DISTINCT FROM p.site_id" in sql
    assert "IF journalled <> expected THEN" in sql


def test_the_rehearsal_is_the_write_ending_in_rollback(p4_chunk: W4.Chunk4) -> None:
    write, rehearse = W4.render_apply(p4_chunk), W4.render_apply(p4_chunk, rehearse=True)
    assert "\nROLLBACK;\n" in rehearse and "\nCOMMIT;\n" not in rehearse
    assert (
        write.split("DO $$", 1)[1].split("END $$;")[0]
        == rehearse.split("DO $$", 1)[1].split("END $$;")[0]
    )


def test_the_reversal_swaps_values_and_keys_and_is_rolled_back(p4_chunk: W4.Chunk4) -> None:
    sql = W4.render_rollback(p4_chunk)
    rows = list(FX._ROW.finditer(sql))
    assert [m["key"] for m in rows] == [r.change_key + "-rollback" for r in p4_chunk.rows]
    assert FX._literal(rows[0]["new"]) == p4_chunk.rows[0].old_value
    assert FX._literal(rows[0]["old"]) == p4_chunk.rows[0].new_value
    assert "\nROLLBACK;\n" in sql and "COMMIT;" not in sql.replace("ON COMMIT DROP", "")


# ── running a chunk against the fake psql ────────────────────────────────────────────────────────


def test_a_chunk_is_written_read_back_and_its_inverse_proven(tmp_path: Path, p4_chunk) -> None:
    out = tmp_path / "apply" / p4_chunk.batch_id
    W4.write_plan_files(
        out, W4.WritePlan4(W4.Group.P4, p4_chunk.batch_id, list(p4_chunk.rows)), p4_chunk
    )
    db = _db(FX.SITE_A)
    outcome = W4.apply_chunk(p4_chunk, out=out, rehearse=False, runner=db)
    assert outcome.ok and outcome.written == 2 and outcome.read_back.ok and outcome.inverse.ok
    assert db.sites[FX.SITE_A].description == FX.DESCRIPTION
    assert db.sites[FX.SITE_A].raw_data[M.PROVENANCE_KEY]["lane"] == "W"
    assert [entry["run_stamp"] for entry in db.journal] == ["phase4:p4-0003:chunk-0001"] * 2
    assert outcome.rollback_rows == 0
    reversals = [sql for sql in db.sent if "this file reverses run stamp" in sql]
    assert len(reversals) == 1 and "\nROLLBACK;\n" in reversals[0]  # the inverse proof ran


def test_a_moved_row_blocks_the_whole_chunk_and_nothing_is_sent(tmp_path: Path, p4_chunk) -> None:
    out = tmp_path / "apply" / p4_chunk.batch_id
    W4.write_plan_files(
        out, W4.WritePlan4(W4.Group.P4, p4_chunk.batch_id, list(p4_chunk.rows)), p4_chunk
    )
    db = _db(FX.SITE_A, description="Somebody edited this meanwhile.")
    outcome = W4.apply_chunk(p4_chunk, out=out, rehearse=False, runner=db)
    assert not outcome.ok and "no longer holds" in outcome.blocked[0]
    assert not any("INSERT INTO" in sql for sql in db.sent) and not db.journal


def test_a_stamp_that_already_journals_rows_blocks_the_chunk(tmp_path: Path, p4_chunk) -> None:
    out = tmp_path / "apply" / p4_chunk.batch_id
    W4.write_plan_files(
        out, W4.WritePlan4(W4.Group.P4, p4_chunk.batch_id, list(p4_chunk.rows)), p4_chunk
    )
    db = _db(FX.SITE_A)
    db.journal.append({"id": 1, "run_stamp": p4_chunk.stamp, "change_key": "x"})
    outcome = W4.apply_chunk(p4_chunk, out=out, rehearse=False, runner=db)
    assert not outcome.ok and "already journals" in outcome.blocked[-1]


def test_a_statement_pinned_to_another_plan_is_not_run(tmp_path: Path, p4_chunk) -> None:
    out = tmp_path / "apply" / p4_chunk.batch_id
    W4.write_plan_files(
        out, W4.WritePlan4(W4.Group.P4, p4_chunk.batch_id, list(p4_chunk.rows)), p4_chunk
    )
    apply_sql = W4.chunk_dir(out, p4_chunk) / W4.APPLY_FILE
    apply_sql.write_text(
        apply_sql.read_text(encoding="utf-8").replace(p4_chunk.digest, "0" * 64), encoding="utf-8"
    )
    with pytest.raises(W.WriteRefused, match="pinned to plan"):
        W4.apply_chunk(p4_chunk, out=out, rehearse=False, runner=_db(FX.SITE_A))


def test_the_rehearsal_changes_nothing_and_journals_nothing(tmp_path: Path, p4_chunk) -> None:
    out = tmp_path / "apply" / p4_chunk.batch_id
    W4.write_plan_files(
        out, W4.WritePlan4(W4.Group.P4, p4_chunk.batch_id, list(p4_chunk.rows)), p4_chunk
    )
    db = _db(FX.SITE_A)
    outcome = W4.apply_chunk(p4_chunk, out=out, rehearse=True, runner=db)
    assert outcome.ok and outcome.rehearsed and outcome.written == 0
    assert db.sites[FX.SITE_A].description == FX.OLD_DESCRIPTION and not db.journal
    assert any("\nROLLBACK;\n" in sql and "INSERT INTO" in sql for sql in db.sent)


def test_the_transaction_refuses_a_row_outside_its_allow_list(tmp_path: Path, p4_chunk) -> None:
    """Guard 2 in the statement itself, not only in `validate_rows`: a tampered row is refused."""
    sql = W4.render_apply(p4_chunk).replace("'P4/raw_data', '{", "'P4/card', '{", 1)
    db = _db(FX.SITE_A)
    with pytest.raises(W.WriteRefused, match="allow-list"):
        db(sql, host="fake")
    assert not db.journal


def test_the_transaction_refuses_a_site_that_is_not_curated(p4_chunk) -> None:
    db = _db(FX.SITE_A, source_id="wikidata")
    with pytest.raises(W.WriteRefused, match="guard 1"):
        db(W4.render_apply(p4_chunk), host="fake")


def test_the_read_back_catches_a_description_whose_hash_breaks_the_invariant(
    tmp_path, p4_chunk
) -> None:
    db = _db(FX.SITE_A)
    db(W4.render_apply(p4_chunk), host="fake")
    db.sites[FX.SITE_A].raw_data[M.PROVENANCE_KEY]["desc_sha256"] = "0" * 64
    back = W4.read_back(p4_chunk, expect_new=True, runner=db)
    assert not back.ok and any("desc_sha256" in m for m in back.mismatches)


# ── L and P5 ─────────────────────────────────────────────────────────────────────────────────────


def test_p5_writes_a_card_only_where_live_provenance_names_it(tmp_path: Path) -> None:
    batch = _batch(
        tmp_path,
        sites=[FX.plan_site(), FX.plan_site(FX.SITE_B), FX.plan_site(FX.SITE_C)],
        assemblies=[FX.assembly(), FX.assembly(FX.SITE_B), FX.assembly(FX.SITE_C)],
    )
    written = {FX.SITE_A: M.text_sha256(FX.CARD), FX.SITE_B: None}
    plan = W4.plan_cards(batch, written=written, card_findings={})
    assert [(r.site_id, r.test_id, r.new_value) for r in plan.rows] == [
        (FX.SITE_A, "P5/card", FX.CARD)
    ]
    assert plan.rows[0].change_key.startswith("phase5:")
    assert {r.site_id for r in plan.refusals} == {FX.SITE_B, FX.SITE_C}
    assert plan.rows[0].evidence["quotes"] == [FX.TEXT[FX.S2[0] : FX.S2[1]]]


def test_a_held_card_with_a_cleared_phase3_defect_is_cleared_with_its_finding(
    tmp_path: Path,
) -> None:
    flagged = FX.plan_site(flags=[M.SiteFlag.CLEARED_CARD_DEFECT])
    batch = _batch(
        tmp_path,
        sites=[flagged],
        assemblies=[FX.assembly()],
        holds=[_hold(FX.SITE_A, M.HoldReason.CARD_TOO_SHORT_AFTER_REVIEW, M.HoldScope.CARD)],
    )
    finding = {"refusal": {"rule": "report-only-field"}, "finder_answer": "WRONG"}
    plan = W4.plan_cards(batch, written={FX.SITE_A: None}, card_findings={FX.SITE_A: [finding]})
    (row,) = plan.rows
    assert (row.test_id, row.old_value, row.new_value) == ("P5/card-clear", FX.OLD_CARD, None)
    assert row.evidence["phase3_findings"] == [finding]


def test_a_clear_without_its_phase3_finding_is_refused_loudly(tmp_path: Path) -> None:
    flagged = FX.plan_site(flags=[M.SiteFlag.CLEARED_CARD_DEFECT])
    batch = _batch(tmp_path, sites=[flagged], holds=[_hold(FX.SITE_A, M.HoldReason.NO_SOURCE)])
    with pytest.raises(W4.PlanInputError, match="without its evidence"):
        W4.plan_cards(batch, written={}, card_findings={})


def test_a_card_longer_than_the_column_is_refused(tmp_path: Path) -> None:
    long_card = "A" * 201
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly(card=long_card)])
    plan = W4.plan_cards(batch, written={FX.SITE_A: M.text_sha256(long_card)}, card_findings={})
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_CARD_TOO_LONG


def test_a_p5_card_is_written_and_its_hash_matches_the_live_provenance(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    p4 = _p4(batch)
    db = _db(FX.SITE_A)
    db(W4.render_apply(W4.chunk_for(p4)), host="fake")
    plan = W4.plan_cards(batch, written={FX.SITE_A: M.text_sha256(FX.CARD)}, card_findings={})
    chunk, out = _written(tmp_path, plan)
    outcome = W4.apply_chunk(chunk, out=out, rehearse=False, runner=db)
    assert outcome.ok and db.sites[FX.SITE_A].card == FX.CARD


def test_the_card_invariant_refuses_a_card_the_provenance_does_not_name(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    db = _db(FX.SITE_A)
    db(W4.render_apply(W4.chunk_for(_p4(batch))), host="fake")
    db.sites[FX.SITE_A].raw_data[M.PROVENANCE_KEY]["card"]["text_sha256"] = "0" * 64
    plan = W4.plan_cards(batch, written={FX.SITE_A: M.text_sha256(FX.CARD)}, card_findings={})
    with pytest.raises(W.WriteRefused, match="invariant 4"):
        db(W4.render_apply(W4.chunk_for(plan)), host="fake")


# ── revert4 ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pattern", ["phase3:%", "%", "phase4%", "phase4l-x:%", "country-canonical:%"]
)
def test_revert_refuses_every_family_but_the_three_phase45_ones(pattern: str) -> None:
    with pytest.raises(R.RevertRefused):
        R.render_revert(pattern)


def test_revert_refuses_a_pattern_that_names_reversals() -> None:
    with pytest.raises(R.RevertRefused, match="reversals"):
        R.render_revert("phase5:p5-0001:chunk-0001-rollback")


def test_revert_reads_the_journal_newest_first_and_writes_each_row_back_conditionally() -> None:
    sql = R.render_revert("phase5:%")
    assert "run_stamp LIKE 'phase5:%' AND l.run_stamp NOT LIKE '%-rollback'" in sql
    assert "ORDER BY l.id DESC LOOP" in sql
    assert "r.new_value, r.old_value, r.test_id," in sql  # written value is the conditional old
    assert (
        "CASE r.table_name WHEN 'card_stats' THEN 'site_id' WHEN 'unified_sites' THEN 'id' END"
        in sql
    )
    assert "r.run_stamp || '-rollback', r.change_key || '-rollback'" in sql
    assert sql.rstrip().split("\n")[-1].startswith("                WHERE k.change_key")
    assert "\nCOMMIT;\n" in sql and "\nROLLBACK;\n" in R.render_revert("phase5:%", rehearse=True)


def test_revert_refuses_rows_that_were_reverted_already() -> None:
    sql = R.render_revert("phase4:p4-0003:chunk-0001")
    assert "RAISE EXCEPTION 'revert: % row(s) were reverted already', bad;" in sql


def test_revert_touches_only_the_three_written_columns_of_curated_sites() -> None:
    sql = R.render_revert("phase4l:%")
    assert (
        "NOT IN (VALUES ('unified_sites', 'description'), ('unified_sites', 'raw_data'), "
        "('card_stats', 'card_description'))"
    ) in sql
    assert "u.source_id <> 'ancient_nerds'" in sql


def test_revert_prints_its_own_exit_line(capsys: pytest.CaptureFixture[str]) -> None:
    assert R.main(["--stamp-like", "phase3:%"]) == 1
    assert capsys.readouterr().out.rstrip().endswith("WRITE_EXIT=1")


# ── write_gate4 ──────────────────────────────────────────────────────────────────────────────────


def _gate_run(tmp_path: Path, sites: int) -> Path:
    """A run with one batch per site, so the step boundary falls between batches."""
    run = tmp_path / "runs" / "pilot"
    ids = [f"{n:08x}-0000-4000-8000-00000000000{n}" for n in range(1, sites + 1)]
    for number, site_id in enumerate(ids, start=1):
        FX.write_batch(
            run,
            sites=[FX.plan_site(site_id)],
            assemblies=[FX.assembly(site_id)],
            batch_id=f"p4-{number:04d}",
        )
    ledger = tmp_path / "LEDGER.jsonl"
    ledger.write_text(
        "".join(
            json.dumps(row) + "\n"
            for number, site_id in enumerate(ids, start=1)
            for row in FX.ledger_rows(site_id, batch=f"p4-{number:04d}")
        ),
        encoding="utf-8",
    )
    return ledger


def _gate_args(tmp_path: Path, ledger: Path, *extra: str) -> list[str]:
    return [
        "--group", "P4", "--run", "pilot", "--run-root", str(tmp_path / "runs"),
        "--apply-root", str(tmp_path / "apply"), "--open-lanes", "W,S", "--ledger", str(ledger),
        *extra,
    ]  # fmt: skip


def test_the_gate_writes_one_step_and_stops_for_the_acceptance(
    tmp_path, monkeypatch, capsys
) -> None:
    ledger = _gate_run(tmp_path, 3)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    ids = [f"{n:08x}-0000-4000-8000-00000000000{n}" for n in range(1, 4)]
    db = _db(*ids)
    assert G.main(_gate_args(tmp_path, ledger, "--apply", "--step", "2"), runner=db) == 0
    out = capsys.readouterr().out
    assert "STEP COMPLETE: 2 site(s)" in out and out.rstrip().endswith("WRITE_EXIT=0")
    applied = sorted(p.parent.name for p in (tmp_path / "apply").glob("*/APPLIED.json"))
    assert applied == ["p4-0001", "p4-0002"]
    assert G.main(_gate_args(tmp_path, ledger, "--apply", "--step", "2"), runner=db) == 0
    assert (tmp_path / "apply" / "p4-0003" / "APPLIED.json").exists()


def test_the_dry_run_sends_nothing(tmp_path, monkeypatch, capsys) -> None:
    ledger = _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db("00000001-0000-4000-8000-000000000001")
    assert G.main(_gate_args(tmp_path, ledger), runner=db) == 0
    assert db.sent == [] and "dry run, nothing is sent" in capsys.readouterr().out
    assert (tmp_path / "apply" / "p4-0001" / "chunks" / "chunk-0001" / "APPLY.sql").exists()


def test_a_blocked_batch_stops_the_run_and_is_refused_until_read(
    tmp_path, monkeypatch, capsys
) -> None:
    ledger = _gate_run(tmp_path, 2)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    first = "00000001-0000-4000-8000-000000000001"
    db = _db(first, "00000002-0000-4000-8000-000000000002")
    db.sites[first].description = "moved"
    assert G.main(_gate_args(tmp_path, ledger, "--apply"), runner=db) == 1
    assert (tmp_path / "apply" / "p4-0001" / "STOPPED.json").exists()
    assert not (tmp_path / "apply" / "p4-0002" / "APPLIED.json").exists()
    db.sites[first].description = FX.OLD_DESCRIPTION
    assert G.main(_gate_args(tmp_path, ledger, "--apply"), runner=db) == 1
    assert "stopped in an earlier run" in capsys.readouterr().out


def test_a_written_batch_keeps_the_plan_it_was_written_from(tmp_path, monkeypatch) -> None:
    ledger = _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db("00000001-0000-4000-8000-000000000001")
    assert G.main(_gate_args(tmp_path, ledger, "--apply"), runner=db) == 0
    monkeypatch.setattr(
        G, "_verifier", lambda: FX.Verify({"00000001-0000-4000-8000-000000000001": [
            _hold("00000001-0000-4000-8000-000000000001", M.HoldReason.V9)]})
    )  # fmt: skip
    assert G.main(_gate_args(tmp_path, ledger), runner=db) == 1


def test_written_sites_counts_only_full_provenance(tmp_path: Path) -> None:
    rows = [
        {"id": FX.SITE_A, "lane": "W", "card": "a" * 64},
        {"id": FX.SITE_B, "lane": "L", "card": None},
        {"id": FX.SITE_C, "lane": None, "card": None},
    ]
    answer = "".join(json.dumps(row) + "\n" for row in rows)
    found = G.written_sites([FX.SITE_A, FX.SITE_B, FX.SITE_C], run=lambda sql: answer)
    assert found == {FX.SITE_A: "a" * 64}


def test_the_open_lanes_name_only_lanes_that_publish() -> None:
    assert G.open_lanes("W, S") == frozenset({M.Lane.W, M.Lane.S})
    with pytest.raises(SystemExit, match="publishes nothing"):
        G.open_lanes("W,0")
