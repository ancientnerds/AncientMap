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
import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import write_gate4 as G  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase4 import plan4 as P4PLAN  # noqa: E402
from phase4 import revert4 as R  # noqa: E402

from tests.remediation import phase4_write_fixtures as FX  # noqa: E402
from tests.remediation import phase4_write_pins as PINS  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4, M, W  # noqa: E402

OPEN_WS = frozenset({M.Lane.W, M.Lane.S})


def _batch(tmp_path: Path, **kwargs):
    return W4.load_batch(FX.write_batch(tmp_path, **kwargs))


def _p4(batch, *, verify=None, open_lanes=OPEN_WS, audited=frozenset(), ledger=None, scope=None):
    return W4.plan_p4(
        batch,
        scope=FX.EVERY_SITE if scope is None else scope,
        open_lanes=open_lanes,
        audited=audited,
        verify=verify or FX.Verify(),
        ledger=FX.ledger_rows(FX.SITE_A, FX.SITE_B) if ledger is None else ledger,
    )


def _hold(site_id: str, reason: M.HoldReason, scope: M.HoldScope = M.HoldScope.SITE) -> M.Hold:
    return M.Hold(site_id=site_id, scope=scope, reason=reason, detail="the detail")


@pytest.fixture(autouse=True)
def _gate_plans_under_every_site(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gate's tests of steps, rounds and acceptances write fixture sites that no scope file
    lists; they plan under a scope of every site. The owner's scope rule is asked by its own tests
    below, which put a real scope file in place of the pinned one."""
    monkeypatch.setattr(G, "_defect_scope", lambda: FX.EVERY_SITE)


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
    assert call["witness"] == (None, None)  # this site's S1 pinned no Wikidata item


def test_the_verifier_is_shown_the_sites_pinned_wikidata_item(tmp_path: Path) -> None:
    """V6 accepts the English label of the site's pinned item (`src.D`) for a strong 'own'
    verdict: the plan hands the verifier exactly the meta and the bytes S1 stored."""
    batch_dir = FX.write_batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    raw = b'{"entities": {"Q1": {"id": "Q1", "labels": {"en": {"value": "The Temple"}}}}}'
    meta = {"id": "D", "sha256_raw": hashlib.sha256(raw).hexdigest()}
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    store.write(site_id=FX.SITE_A, feature=M.source_feature("D", "raw"), body=raw)
    store.write(
        site_id=FX.SITE_A,
        feature=M.source_feature("D", "meta"),
        body=json.dumps(meta).encode("utf-8"),
    )
    verify = FX.Verify()
    _p4(W4.load_batch(batch_dir), verify=verify)
    assert verify.calls[0]["witness"] == (meta, raw)


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


def test_every_answer_needs_the_prompt_it_answered(tmp_path: Path) -> None:
    """The journal records the exact prompt of every call: a reviewer answer whose prompt is not on
    disk is incomplete evidence, although `prompts/` holds the selector's."""
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    F = FX.F
    F.EvidenceStore(batch.root / "prompts").path_for(FX.SITE_A, M.REVIEW_FEATURE).unlink()
    plan = _p4(batch)
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_EVIDENCE
    assert "reviews/review has no prompt" in plan.refusals[0].detail


def test_every_answer_needs_its_ledger_line_and_every_call_its_answer(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    selector_only = [row for row in FX.ledger_rows(FX.SITE_A) if row["stage"] == "selector"]
    plan = _p4(batch, ledger=selector_only)
    assert not plan.rows and "reviews/review has no ledger line" in plan.refusals[0].detail
    extra = [*FX.ledger_rows(FX.SITE_A), {**selector_only[0], "label": f"{FX.SITE_A}/translate"}]
    plan = _p4(batch, ledger=extra)
    assert not plan.rows and "translate has no answer on disk" in plan.refusals[0].detail


def test_a_site_without_the_selectors_answer_is_refused(tmp_path: Path) -> None:
    """The design's p_evidence names the selector's answer (its sha256). A lane-W site whose every
    call is complete - answer, prompt and ledger line - but none of which is the selector's (a
    translation stands where the selection should be) is not written (decision D5)."""
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    for folder in ("answers", "prompts"):
        store = FX.F.EvidenceStore(batch.root / folder)
        store.path_for(FX.SITE_A, M.SELECT_FEATURE).unlink()
        store.write(site_id=FX.SITE_A, feature=M.TRANSLATE_FEATURE, body=b"T1: A sentence.\n")
    ledger = [
        {**row, "label": row["label"].replace(f"/{M.SELECT_FEATURE}", f"/{M.TRANSLATE_FEATURE}")}
        for row in FX.ledger_rows(FX.SITE_A)
    ]
    plan = _p4(batch, ledger=ledger)
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_EVIDENCE
    assert plan.refusals[0].detail == "no answers/select: this lane's site needs that call"


def _calls(*features: str) -> tuple[list[W4.ModelFile], list[str]]:
    """Complete calls: each with its answer (the reviewer's under reviews/), its prompt and its
    ledger label - so only a rule about which calls there are can object."""
    files: list[W4.ModelFile] = []
    for feature in features:
        folder = "reviews" if feature == M.REVIEW_FEATURE else "answers"
        files.append(W4.ModelFile(folder=folder, feature=feature, sha256="a" * 64))
        files.append(W4.ModelFile(folder="prompts", feature=feature, sha256="b" * 64))
    return files, [f"{FX.SITE_A}/{feature}" for feature in features]


@pytest.mark.parametrize(
    ("lane", "answers"),
    [
        (M.Lane.W, ["select"]),
        (M.Lane.S, ["select"]),
        (M.Lane.T, ["select", "translate"]),
        (M.Lane.R, ["restricted"]),
    ],
)
def test_each_lane_needs_its_own_calls_and_the_reviewers_by_name(lane, answers) -> None:
    """W, S and T select (T translates the selection too), R restates without a selector; every
    lane is reviewed. The names are the design's, not model4's, so a renamed constant goes red."""
    assert list(M.LANE_ANSWERS[lane]) == answers and M.REVIEW_FEATURE == "review"
    assert W4.evidence_problems(*_calls(*answers, "review"), lane=lane) == []
    for missing in [*answers, "review"]:
        kept = [feature for feature in [*answers, "review"] if feature != missing]
        folder = "reviews" if missing == "review" else "answers"
        assert W4.evidence_problems(*_calls(*kept), lane=lane) == [
            f"no {folder}/{missing}: this lane's site needs that call"
        ], missing


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
    assert evidence["ledger_labels"] == [f"{FX.SITE_A}/select", f"{FX.SITE_A}/review"]


def test_a_quote_never_reaches_public_raw_data(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    raw = _p4(batch).rows[1].new_value
    assert FX.TEXT[FX.S1[0] : FX.S1[1]] not in raw


def test_a_batch_where_a_site_reached_no_outcome_is_a_hole_not_a_refusal(tmp_path: Path) -> None:
    with pytest.raises(W4.PlanInputError, match="neither an assembly nor a site hold"):
        _batch(
            tmp_path, sites=[FX.plan_site(), FX.plan_site(FX.SITE_B)], assemblies=[FX.assembly()]
        )


@pytest.mark.parametrize("missing", [M.LANES_FILE, M.ASSEMBLY_FILE, M.HOLDS_FILE])
def test_a_batch_short_of_its_outcome_files_is_refused_by_name(tmp_path: Path, missing) -> None:
    """The D9 run's batch after its select export (2026-09-25): no `assembly.jsonl` until S4. The
    batch has reached no outcome - a hole, refused as one (`PlanInputError`, so the gate prints its
    `WRITE_EXIT=` line), not a `FileNotFoundError` that ends the gate without it."""
    batch_dir = FX.write_batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    (batch_dir / missing).unlink()
    with pytest.raises(W4.PlanInputError, match=f"no {missing}: the batch has not reached"):
        W4.load_batch(batch_dir)


def test_the_gate_refuses_a_run_whose_batch_is_not_assembled_yet_with_its_exit_line(
    tmp_path, monkeypatch, capsys
) -> None:
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    (tmp_path / "runs" / "pilot" / "p4-0001" / M.ASSEMBLY_FILE).unlink()
    assert G.main(_gate_args(tmp_path), runner=_db(GATE_SITE)) == 1
    captured = capsys.readouterr()
    assert "no assembly.jsonl: the batch has not reached" in captured.err
    assert captured.out.rstrip().endswith("WRITE_EXIT=1")
    assert not (tmp_path / "apply").exists()


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


OTHER_SITE = "9b0c1d2e-0000-4000-8000-000000000009"


def _legacy_row(**changes) -> W4.Row4:
    """A well-formed L row (legacy provenance over OLD_RAW), with `changes` made through make_row,
    so its change key is its own digest and only the tampered guard can refuse it."""
    legacy = M.LegacyProvenance(desc_sha256=M.text_sha256(FX.OLD_DESCRIPTION))
    fields = {
        "group": W4.Group.L,
        "site": FX.plan_site(),
        "column": "raw_data",
        "old_value": W4.raw_json(FX.OLD_RAW),
        "new_value": W4.raw_json(W4.legacy_raw_data(FX.OLD_RAW, legacy)),
        "test_id": W4.TEST_LEGACY,
        "evidence": {"group": "L"},
        **changes,
    }
    return W4.make_row(**fields)


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (lambda rows: [dataclasses.replace(rows[0], group=W4.Group.L), rows[1]], "a L row in a P4 plan"),
        (lambda rows: [rows[0], rows[0], rows[1]], "appears twice"),
        (lambda rows: [dataclasses.replace(r, site_id="not-a-uuid", pk="not-a-uuid") for r in rows], "is not a UUID"),
        (lambda rows: [dataclasses.replace(rows[0], pk_column="site_id"), rows[1]], "column's own table and key"),
        (lambda rows: [dataclasses.replace(rows[0], pk=OTHER_SITE), rows[1]], "is not the site id"),
        (lambda rows: [dataclasses.replace(rows[0], new_value=rows[0].old_value), rows[1]], "not a change"),
        (lambda rows: [dataclasses.replace(rows[0], new_value="   "), rows[1]], "an empty new value"),
        (lambda rows: [dataclasses.replace(rows[0], evidence={}), rows[1]], "without evidence"),
    ],
    ids=["group", "twice", "uuid", "table-key", "pk", "no-op", "empty", "evidence"],
)  # fmt: skip
def test_validate_rows_refuses_each_tampered_field(tmp_path: Path, tamper, message) -> None:
    """The plan-side mirror of the guards, one tampered field per case, each refused by its own
    guard (the message names which), never by a later one."""
    rows = _rows(tmp_path)
    W4.validate_rows(W4.Group.P4, rows)  # the untampered plan passes
    with pytest.raises(W.WriteRefused, match=message):
        W4.validate_rows(W4.Group.P4, tamper(rows))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"new_value": "[1]"}, "the new value is not a JSON object"),
        ({"old_value": "[1]"}, "the old value is not a JSON object"),
        (
            {
                "old_value": json.dumps(
                    W4.legacy_raw_data(
                        FX.OLD_RAW,
                        M.LegacyProvenance(desc_sha256=M.text_sha256(FX.OLD_DESCRIPTION)),
                    ),
                    indent=1,
                )
            },
            "the same JSON value",
        ),
        (
            {"new_value": W4.raw_json(W4.new_raw_data(FX.OLD_RAW, FX.assembly()))},
            "a L row writes full provenance",
        ),
    ],
    ids=["new-not-object", "old-not-object", "same-json", "full-provenance-in-L"],
)
def test_a_raw_data_row_is_refused_by_its_own_guard(changes, message) -> None:
    W4.validate_rows(W4.Group.L, [_legacy_row()])  # the untampered row passes
    with pytest.raises(W.WriteRefused, match=message):
        W4.validate_rows(W4.Group.L, [_legacy_row(**changes)])


def test_validate_rows_refuses_a_card_longer_than_the_column() -> None:
    long_card = W4.make_row(
        group=W4.Group.P5,
        site=FX.plan_site(),
        column="card_description",
        old_value=FX.OLD_CARD,
        new_value="A" * 201,
        test_id=W4.TEST_CARD,
        evidence={"x": 1},
    )
    with pytest.raises(W.WriteRefused, match="201 characters in varchar"):
        W4.validate_rows(W4.Group.P5, [long_card])


def test_a_chunk_has_at_most_its_groups_rows_and_a_1_based_round(tmp_path: Path) -> None:
    row = _legacy_row()
    W4.Chunk4(group=W4.Group.L, batch_id="p4l-0001", write_round=1, rows=(row,) * 100)
    with pytest.raises(W.WriteRefused, match="101 rows in one L chunk"):
        W4.Chunk4(group=W4.Group.L, batch_id="p4l-0001", write_round=1, rows=(row,) * 101)
    for bad in (0, -1, True):
        with pytest.raises(W.WriteRefused, match="1-based write round"):
            W4.Chunk4(group=W4.Group.L, batch_id="p4l-0001", write_round=bad, rows=(row,))


def _rewrite(path: Path, lines: list[str]) -> None:
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def _jsonl(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_load_batch_refuses_a_site_listed_twice(tmp_path: Path) -> None:
    batch_dir = FX.write_batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    raw = json.loads((batch_dir / M.INPUT_FILE).read_text(encoding="utf-8"))
    raw["sites"] = raw["sites"] * 2
    (batch_dir / M.INPUT_FILE).write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(W4.PlanInputError, match="a site is listed twice"):
        W4.load_batch(batch_dir)


@pytest.mark.parametrize(
    ("name", "edit", "message"),
    [
        (M.LANES_FILE, lambda lines: [*lines, lines[0].replace(FX.SITE_A, OTHER_SITE)], "lanes.jsonl names"),
        (M.LANES_FILE, lambda lines: [*lines, lines[0]], "lanes.jsonl names"),
        (M.LANES_FILE, lambda lines: lines[1:], "lanes.jsonl misses"),
        (M.ASSEMBLY_FILE, lambda lines: [*lines, lines[0].replace(FX.SITE_A, OTHER_SITE)], "assembly.jsonl names"),
        (M.ASSEMBLY_FILE, lambda lines: [*lines, lines[0]], "assembly.jsonl names"),
        (M.HOLDS_FILE, lambda lines: [*lines, json.dumps(_hold(OTHER_SITE, M.HoldReason.NO_SOURCE).to_dict())], "holds.jsonl names"),
    ],
    ids=["lane-foreign", "lane-twice", "lane-missing", "assembly-foreign", "assembly-twice", "hold-foreign"],
)  # fmt: skip
def test_load_batch_refuses_a_file_that_names_a_site_wrongly(tmp_path, name, edit, message) -> None:
    batch_dir = FX.write_batch(
        tmp_path,
        sites=[FX.plan_site(), FX.plan_site(FX.SITE_B)],
        assemblies=[FX.assembly(), FX.assembly(FX.SITE_B)],
    )
    W4.load_batch(batch_dir)  # the batch as written loads
    _rewrite(batch_dir / name, edit(_jsonl(batch_dir / name)))
    with pytest.raises(W4.PlanInputError, match=message):
        W4.load_batch(batch_dir)


def test_model_files_are_only_the_sites_own(tmp_path: Path) -> None:
    batch_dir = FX.write_batch(
        tmp_path,
        sites=[FX.plan_site(), FX.plan_site(FX.SITE_B)],
        assemblies=[FX.assembly(), FX.assembly(FX.SITE_B)],
    )
    files = W4.model_files(batch_dir, FX.SITE_A)
    assert [(entry.folder, entry.feature) for entry in files] == [
        ("answers", "select"),
        ("reviews", "review"),
        ("prompts", "review"),
        ("prompts", "select"),
    ]


def test_plan_writes_is_each_groups_own_planner_with_its_own_inputs(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    legacy = W4.plan_writes(batch, group=W4.Group.L, written=[FX.SITE_A])
    assert legacy.batch_id == "p4l-0003" and legacy.refusals[0].rule == W4.RULE_WRITTEN
    with pytest.raises(TypeError):
        W4.plan_writes(batch, group=W4.Group.L, written=[], open_lanes=OPEN_WS)
    with pytest.raises(TypeError):
        W4.plan_writes(batch, group=W4.Group.P5, scope=FX.EVERY_SITE, written={})  # card_findings


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


def test_the_allow_list_is_rendered_from_the_groups_rows(tmp_path: Path, p4_chunk) -> None:
    sql = W4.render_apply(p4_chunk)
    assert (
        "NOT IN (VALUES ('unified_sites', 'description', 'id', 'P4/description'), "
        "('unified_sites', 'raw_data', 'id', 'P4/raw_data'))"
    ) in sql
    batch = _batch(tmp_path / "p5", sites=[FX.plan_site()], assemblies=[FX.assembly()])
    cards = W4.plan_cards(
        batch, scope=FX.EVERY_SITE, written={FX.SITE_A: M.text_sha256(FX.CARD)}, card_findings={}
    )
    assert (
        "NOT IN (VALUES ('card_stats', 'card_description', 'site_id', 'P5/card'), "
        "('card_stats', 'card_description', 'site_id', 'P5/card-clear'))"
    ) in W4.render_apply(W4.chunk_for(cards))


def _between(sql: str, start: str, end: str) -> str:
    """The rendered text from `start` through `end`, with its line end."""
    first = sql.index(start)
    return sql[first : sql.index(end, first) + len(end)] + "\n"


def test_the_write_carries_exactly_the_reviewed_guards_and_invariants(p4_chunk) -> None:
    """Every guard, invariant and RAISE inside the transaction, byte for byte: the fake cannot run
    PL/pgSQL, so this pin is what fails when a predicate or a RAISE is removed
    (`phase4_write_pins`)."""
    sql = W4.render_apply(p4_chunk)
    assert _between(sql, "CREATE TEMP TABLE", ") ON COMMIT DROP;") == PINS.P4_PLAN_TABLE
    assert _between(sql, "DO $$", "END $$;") == PINS.P4_APPLY_BODY


def test_the_reversal_carries_exactly_the_reviewed_guards(p4_chunk) -> None:
    sql = W4.render_rollback(p4_chunk)
    assert _between(sql, "CREATE TEMP TABLE", ") ON COMMIT DROP;") == PINS.P4_PLAN_TABLE
    assert _between(sql, "DO $$", "END $$;") == PINS.P4_ROLLBACK_BODY


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


def _rendered(tmp_path: Path, chunk: W4.Chunk4) -> Path:
    out = tmp_path / "apply" / chunk.batch_id
    W4.write_plan_files(out, W4.WritePlan4(chunk.group, chunk.batch_id, list(chunk.rows)), chunk)
    return out


def test_a_write_the_read_back_disagrees_with_stops_the_run(tmp_path, p4_chunk) -> None:
    """A row moved right after the commit (a trigger, a boot import): the write is not taken as
    done, whatever the transaction said."""
    out = _rendered(tmp_path, p4_chunk)
    db = _db(FX.SITE_A)
    db.after_commit = lambda fake: setattr(fake.sites[FX.SITE_A], "description", "overwritten")
    with pytest.raises(W.ReadBackFailed, match="the read-back disagrees"):
        W4.apply_chunk(p4_chunk, out=out, rehearse=False, runner=db)


def test_a_journal_row_with_other_values_than_the_plan_fails_the_read_back(p4_chunk) -> None:
    db = _db(FX.SITE_A)
    db(W4.render_apply(p4_chunk), host="fake")
    assert W4.read_back(p4_chunk, expect_new=True, runner=db).ok
    db.journal[0]["new_value"] = "another text"
    back = W4.read_back(p4_chunk, expect_new=True, runner=db)
    assert not back.ok and any("the journal's new_value is" in m for m in back.mismatches)


def test_a_journal_row_under_the_stamp_that_the_plan_lacks_fails_the_read_back(p4_chunk) -> None:
    db = _db(FX.SITE_A)
    db(W4.render_apply(p4_chunk), host="fake")
    db.journal.append({**db.journal[0], "id": 99, "change_key": "phase4:" + "9" * 64})
    back = W4.read_back(p4_chunk, expect_new=True, runner=db)
    assert not back.ok and any("has 3 journal row(s), the plan 2" in m for m in back.mismatches)


def test_a_rehearsal_that_leaves_a_journal_row_stops_the_run(tmp_path, p4_chunk) -> None:
    out = _rendered(tmp_path, p4_chunk)
    db = _db(FX.SITE_A)
    db.leak_rolled_back_journal = True
    with pytest.raises(W.ReadBackFailed, match="the rehearsal left a trace"):
        W4.apply_chunk(p4_chunk, out=out, rehearse=True, runner=db)


def test_an_inverse_proof_that_keeps_its_reversal_stops_the_run(tmp_path, p4_chunk) -> None:
    """ROLLBACK.sql must end in ROLLBACK: one that commits moves the write back, and the read-back
    after it says so."""
    out = _rendered(tmp_path, p4_chunk)
    path = W4.chunk_dir(out, p4_chunk) / W4.ROLLBACK_FILE
    path.write_text(
        path.read_text(encoding="utf-8").replace("\nROLLBACK;\n", "\nCOMMIT;\n"), encoding="utf-8"
    )
    with pytest.raises(W.InverseFailed, match="did not leave the write as it was"):
        W4.apply_chunk(p4_chunk, out=out, rehearse=False, runner=_db(FX.SITE_A))


def test_reversal_journal_rows_that_survive_the_inverse_proof_stop_the_run(
    tmp_path, p4_chunk
) -> None:
    out = _rendered(tmp_path, p4_chunk)
    db = _db(FX.SITE_A)
    db.leak_rolled_back_journal = True
    with pytest.raises(W.InverseFailed, match="2 reversal journal row"):
        W4.apply_chunk(p4_chunk, out=out, rehearse=False, runner=db)


def test_a_site_outside_the_curated_source_is_blocked_before_anything_is_sent(
    tmp_path, p4_chunk
) -> None:
    out = _rendered(tmp_path, p4_chunk)
    db = _db(FX.SITE_A, source_id="wikidata")
    outcome = W4.apply_chunk(p4_chunk, out=out, rehearse=False, runner=db)
    assert not outcome.ok and "source_id is 'wikidata'" in outcome.blocked[0]
    assert not any("INSERT INTO" in sql for sql in db.sent) and not db.journal


def test_a_card_without_its_card_stats_row_is_blocked_before_anything_is_sent(tmp_path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    cards = W4.plan_cards(
        batch, scope=FX.EVERY_SITE, written={FX.SITE_A: M.text_sha256(FX.CARD)}, card_findings={}
    )
    chunk = W4.chunk_for(cards)
    out = _rendered(tmp_path, chunk)
    db = _db(FX.SITE_A, card_row=False)
    outcome = W4.apply_chunk(chunk, out=out, rehearse=False, runner=db)
    assert not outcome.ok and "no card_stats row" in outcome.blocked[0]
    assert not any("INSERT INTO" in sql for sql in db.sent)


def test_the_writer_tools_turn_their_streams_to_utf8_first(monkeypatch) -> None:
    calls: list[dict[str, str]] = []

    class Stream:
        def reconfigure(self, **kwargs: str) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(sys, "stdout", Stream())
    monkeypatch.setattr(sys, "stderr", Stream())
    W.utf8_streams()
    assert calls == [{"encoding": "utf-8", "errors": "replace"}] * 2


def test_every_exit_line_is_printed_on_utf8_streams(monkeypatch, capsys) -> None:
    seen: list[str] = []
    monkeypatch.setattr(W, "utf8_streams", lambda: seen.append("utf-8"))
    assert W4.exit_line("WRITE", lambda: 0) == 0
    assert seen == ["utf-8"] and capsys.readouterr().out == "WRITE_EXIT=0\n"


# ── the owner's defect scope: P4, L and P5 write no other site ──────────────────────────────────


def test_p4_refuses_a_site_outside_the_defect_scope_before_any_other_rule(tmp_path: Path) -> None:
    """Owner decision 2026-09-23: only the sites with proven text defects are written. A site
    outside the scope is refused under its own rule whatever else holds it (SITE_C is also held),
    and nothing of it is verified or read."""
    sites = [FX.plan_site(), FX.plan_site(FX.SITE_B), FX.plan_site(FX.SITE_C)]
    batch = _batch(
        tmp_path,
        sites=sites,
        assemblies=[FX.assembly(), FX.assembly(FX.SITE_B), FX.assembly(FX.SITE_C)],
        holds=[_hold(FX.SITE_C, M.HoldReason.V9)],
    )
    verify = FX.Verify()
    scope = FX.scope(FX.SITE_A)
    plan = _p4(
        batch,
        verify=verify,
        scope=scope,
        ledger=FX.ledger_rows(FX.SITE_A, FX.SITE_B, FX.SITE_C),
    )
    assert {row.site_id for row in plan.rows} == {FX.SITE_A}
    assert [(r.site_id, r.field, r.rule) for r in plan.refusals] == [
        (FX.SITE_B, "description", W4.RULE_OUT_OF_SCOPE),
        (FX.SITE_C, "description", W4.RULE_OUT_OF_SCOPE),
    ]
    assert scope.label in plan.refusals[0].detail
    assert "description and card stay as they are" in plan.refusals[0].detail
    assert [call["site"].site_id for call in verify.calls] == [FX.SITE_A]
    assert plan.refusals_by_rule() == {"outside-defect-scope": 2}


def test_p5_refuses_a_site_outside_the_defect_scope_even_a_card_clear(tmp_path: Path) -> None:
    """A written card and a card clear are both writes: neither happens outside the scope."""
    flagged = FX.plan_site(FX.SITE_B, flags=[M.SiteFlag.CLEARED_CARD_DEFECT])
    batch = _batch(
        tmp_path,
        sites=[FX.plan_site(), flagged],
        assemblies=[FX.assembly()],
        holds=[_hold(FX.SITE_B, M.HoldReason.NO_SOURCE)],
    )
    finding = {"refusal": {"rule": "report-only-field"}, "finder_answer": "WRONG"}
    plan = W4.plan_cards(
        batch,
        scope=FX.scope(),
        written={FX.SITE_A: M.text_sha256(FX.CARD)},
        card_findings={FX.SITE_B: [finding]},
    )
    assert not plan.rows
    assert [(r.site_id, r.field, r.rule) for r in plan.refusals] == [
        (FX.SITE_A, "card_description", W4.RULE_OUT_OF_SCOPE),
        (FX.SITE_B, "card_description", W4.RULE_OUT_OF_SCOPE),
    ]
    inside = W4.plan_cards(
        batch,
        scope=FX.scope(FX.SITE_A, FX.SITE_B),
        written={FX.SITE_A: M.text_sha256(FX.CARD)},
        card_findings={FX.SITE_B: [finding]},
    )
    assert [r.test_id for r in inside.rows] == ["P5/card", "P5/card-clear"]


def test_p4_and_p5_need_the_defect_scope_and_l_takes_none(tmp_path: Path) -> None:
    """No default: a P4 or P5 plan without the owner's scope is a TypeError, never a plan of every
    site. Lane L takes none (owner decision 2026-09-24): a scope handed to it is a TypeError too,
    never a filter of the March texts it marks."""
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    with pytest.raises(TypeError):
        W4.plan_writes(batch, group=W4.Group.L, scope=FX.EVERY_SITE, written=[])
    with pytest.raises(TypeError):
        W4.plan_writes(batch, group=W4.Group.P5, written={}, card_findings={})
    with pytest.raises(TypeError):
        W4.plan_p4(batch, open_lanes=OPEN_WS, audited=frozenset(), verify=FX.Verify(), ledger=[])


def _scope_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *site_ids: str) -> Path:
    """A real scope file of these sites, put in place of the pinned one (file and pin)."""
    payload: dict = {
        "version": G.S.SCOPE_VERSION,
        "decision": "a test",
        "inputs": {},
        "methods": {},
        "lists": dict.fromkeys(G.S.LISTS, 0),
        "unclaimed": {G.S.UNGROUNDED_CARD: {G.S.NOT_IN_SNAPSHOT: []}},
        "sites": [{"site_id": s, "lists": [G.S.CLEARED_CARD]} for s in sorted(site_ids)],
    }
    payload["lists"][G.S.CLEARED_CARD] = len(site_ids)
    payload["sites_sha256"] = G.S.sites_digest(payload["sites"])
    data = G.S.render_scope(payload)
    path = tmp_path / "SCOPE4.json"
    path.write_bytes(data)
    monkeypatch.setattr(G.S, "SCOPE_FILE", path)
    monkeypatch.setattr(G.S, "SCOPE_SHA256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(G, "_defect_scope", REAL_DEFECT_SCOPE)
    return path


#: The gate's own loader, kept before the autouse fixture replaces it for the other gate tests.
REAL_DEFECT_SCOPE = G._defect_scope


def test_the_gate_refuses_every_site_outside_the_pinned_scope_and_counts_it(
    tmp_path, monkeypatch, capsys
) -> None:
    """The gate plans under the pinned scope and no other - there is no flag - and the refusals are
    counted on the 'refused by rule' line like every other rule's."""
    _gate_run(tmp_path, 2)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    first, second = [f"{n:08x}-0000-4000-8000-00000000000{n}" for n in (1, 2)]
    _scope_file(monkeypatch, tmp_path, first)
    assert G.main(_gate_args(tmp_path), runner=_db(first, second)) == 0
    out = capsys.readouterr().out
    assert "rows planned: 2 | refused by rule: {'outside-defect-scope': 1}" in out
    assert "defect scope: SCOPE4.json v2 " in out  # the current version, read from the pinned file
    refused = (tmp_path / "apply" / "p4-0002" / W4.REFUSED_FILE).read_text(encoding="utf-8")
    assert json.loads(refused)["rule"] == "outside-defect-scope"


def test_a_site_outside_the_pinned_scope_is_marked_by_l_and_refused_by_p4_and_p5(
    tmp_path, monkeypatch, capsys
) -> None:
    """Both owner decisions on one site outside the pinned scope, through the gate: P4 and P5 write
    only the defect scope (2026-09-23, "Nur Defekt-Sites") and refuse it; lane L marks every
    March-AI text (2026-09-24, "Alle kennzeichnen") and plans its legacy provenance - it writes no
    text, only the marking."""
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    site = "00000001-0000-4000-8000-000000000001"
    _scope_file(monkeypatch, tmp_path, FX.SITE_A)
    refused = tmp_path / "ALL_REFUSED.jsonl"
    refused.write_text("", encoding="utf-8")
    planned = {}
    run = ["--run", "pilot", "--run-root", str(tmp_path / "runs")]
    for group, extra in (
        ("P4", [*run, "--open-lanes", "W,S"]),
        ("P5", [*run, "--phase3-refused", str(refused)]),
        ("L", ["--legacy-plan", str(_legacy_plan(tmp_path, FX.plan_site(site)))]),
    ):
        args = ["--group", group, "--apply-root", str(tmp_path / f"apply-{group}"), *extra]
        assert G.main(args, runner=_db(site)) == 0
        planned[group] = capsys.readouterr().out
    for group in ("P4", "P5"):
        assert "rows planned: 0 | refused by rule: {'outside-defect-scope': 1}" in planned[group]
    assert "rows planned: 1 | refused by rule: {}" in planned["L"]
    assert "outside-defect-scope" not in planned["L"]
    (row,) = W4.read_plan(tmp_path / "apply-L" / "p4l-1001", group=W4.Group.L)
    assert (row.site_id, row.test_id) == (site, W4.TEST_LEGACY)
    assert json.loads(row.new_value)[M.PROVENANCE_KEY]["ai"] == "generated"


# ── lane L: its own plan over the curated population (owner decision 2026-09-24) ───────────────


def _legacy_plan(tmp_path: Path, *sites: M.PlanSite) -> Path:
    """Lane L's own plan (`plan4.py legacy`) of exactly these sites, in their order."""
    path = tmp_path / "LEGACY4.jsonl"
    P4PLAN.write_legacy_plan(path, list(sites))
    return path


def _legacy_args(tmp_path: Path, plan: Path, *extra: str) -> list[str]:
    return ["--group", "L", "--legacy-plan", str(plan), "--apply-root", str(tmp_path / "apply"),
            *extra]  # fmt: skip


def _legacy_ids(count: int) -> list[str]:
    return [f"{n:08x}-0000-4000-8000-{n:012x}" for n in range(1, count + 1)]


def test_l_plans_the_curated_population_from_its_own_plan_and_counts_every_exclusion(
    tmp_path, capsys
) -> None:
    """Lane L's population is every curated site (`plan4.py legacy`), not a Phase-4 run's batches:
    a March text is marked, a site with live phase-4 provenance is excluded on production's word
    (read-only), and a text equal to d4526691 or a site the snapshot lacks is listed for HUMAN_ONLY
    D7 - each counted on its own."""
    marked, same, written, absent = _legacy_ids(4)
    plan = _legacy_plan(
        tmp_path,
        FX.plan_site(marked),
        FX.plan_site(same, description="Same.", snapshot="Same."),
        FX.plan_site(written),
        FX.plan_site(absent, description="Added in April.", snapshot=None, in_snapshot=False),
    )
    db = _db(marked, same, absent)
    db.sites[written] = FX.Site(raw_data={M.PROVENANCE_KEY: {"lane": "W", "card": None}})
    assert G.main(_legacy_args(tmp_path, plan), runner=db) == 0
    out = capsys.readouterr().out
    digest = hashlib.sha256(plan.read_bytes()).hexdigest()
    assert f"group L | legacy plan {plan} (sha256 {digest}) | " in out
    assert G.LEGACY_UNSCOPED in out
    assert "live phase-4 provenance: 1 of 4 planned sites (read-only)" in out
    assert (
        "rows planned: 1 | refused by rule: {'no-legacy-claim': 2, 'written-by-p4': 1} | "
        "unclaimed by reason (HUMAN_ONLY D7): {'not-in-snapshot': 1, 'same-as-snapshot': 1}"
    ) in out
    (row,) = W4.read_plan(tmp_path / "apply" / "p4l-1001", group=W4.Group.L)
    assert row.site_id == marked and row.old_value == W4.raw_json(FX.OLD_RAW)
    unclaimed = (tmp_path / "apply" / "p4l-1001" / W4.UNCLAIMED_FILE).read_text(encoding="utf-8")
    assert [json.loads(line)["site_id"] for line in unclaimed.splitlines()] == [same, absent]


def _legacy_acceptance(tmp_path: Path, *, journal_rows: int, planned: int) -> Path:
    """What `verify_writes4.py --lane p4l` prints for a clean step (its own lines, WB-C3)."""
    path = tmp_path / f"accept-l-{journal_rows}.log"
    path.write_text(
        f"lane p4l | stamps phase4l:p4l-% | planned rows {planned} | lane journal rows "
        f"{journal_rows} | carried {journal_rows} | not yet written {planned - journal_rows} | "
        "superseded 0\nRESULT: 0 deviation(s)\nACCEPT_EXIT=0\n",
        encoding="utf-8",
    )
    return path


def test_l_is_written_in_steps_of_its_own_plan_and_accepted_on_its_own_lane(
    tmp_path, capsys
) -> None:
    """The L plan's batches are written like every group's: one step of at most `--step` sites,
    then the acceptance - `verify_writes4.py --lane p4l`, which re-runs no verifier and reads no
    run, so the printed command names none - and only then the next step."""
    ids = _legacy_ids(16)
    plan = _legacy_plan(tmp_path, *[FX.plan_site(site_id) for site_id in ids])
    db = _db(*ids)
    assert G.main(_legacy_args(tmp_path, plan, "--apply", "--step", "15"), runner=db) == 0
    out = capsys.readouterr().out
    lane_plan = tmp_path / "apply" / G.LANE_PLAN_FILE
    done = out.split("STEP COMPLETE: ", 1)[1]
    assert done.startswith("15 site(s) written in 1 batch(es)")
    assert f"{G.VERIFY_TOOL} --lane p4l --plan {lane_plan} (0 deviations" in done
    assert "--run" not in done
    step = json.loads((tmp_path / "apply" / G.STEP_FILE).read_text(encoding="utf-8"))
    assert (step["lane"], step["stamps"]) == ("p4l", ["phase4l:p4l-1001:chunk-0001"])
    assert db.sites[ids[0]].raw_data[M.PROVENANCE_KEY]["lane"] == "L"
    assert M.PROVENANCE_KEY not in db.sites[ids[15]].raw_data
    assert G.main(_legacy_args(tmp_path, plan, "--apply", "--step", "15"), runner=db) == 1
    assert "has no acceptance" in capsys.readouterr().out
    accept = _legacy_acceptance(tmp_path, journal_rows=15, planned=16)
    back = ["--group", "L", "--apply-root", str(tmp_path / "apply"), "--accept", str(accept)]
    assert G.main(back, runner=db) == 0
    assert "ACCEPTED step 1" in capsys.readouterr().out
    assert G.main(_legacy_args(tmp_path, plan, "--apply", "--step", "15"), runner=db) == 0
    assert (tmp_path / "apply" / "p4l-1002" / "APPLIED.json").exists()
    assert db.sites[ids[15]].raw_data[M.PROVENANCE_KEY]["lane"] == "L"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--group", "L", "--run", "pilot"], "lane L plans the curated population"),
        (["--group", "L"], "--legacy-plan: lane L plans from"),
        (["--group", "P4", "--run", "pilot", "--legacy-plan", "x"], "only lane L plans from"),
        (["--group", "P5"], "--run: P4 and P5 plan a phase-4 run"),
    ],
)
def test_lane_l_plans_from_its_own_plan_and_p4_and_p5_from_a_run(
    tmp_path, capsys, args, message
) -> None:
    """One L population: a per-run L plan beside the curated one would put a site into two write
    batches of one lane. So L never takes a run, and P4 and P5 never take L's plan."""
    assert G.main([*args, "--apply-root", str(tmp_path / "apply")], runner=_db()) == 1
    assert message in capsys.readouterr().err
    assert not (tmp_path / "apply").exists()


def test_l_refuses_an_apply_root_holding_write_batches_of_another_l_plan(tmp_path, capsys) -> None:
    """The per-run L plans of before 2026-09-24 rendered `p4l-0001` .. for pilot 4's batches (dry,
    never written). The acceptance's lane plan is every `PLAN.jsonl` of the apply root, so such a
    batch would be judged as this plan's: the gate names it and plans nothing."""
    (site,) = _legacy_ids(1)
    plan = _legacy_plan(tmp_path, FX.plan_site(site))
    (tmp_path / "apply" / "p4l-0001").mkdir(parents=True)
    assert G.main(_legacy_args(tmp_path, plan), runner=_db(site)) == 1
    err = capsys.readouterr().err
    assert "['p4l-0001']" in err and "another L plan" in err
    assert not (tmp_path / "apply" / "p4l-1001").exists()


def test_l_plans_the_named_batches_of_its_plan_and_names_what_is_missing(tmp_path, capsys) -> None:
    """`--batch` names the L plan's own batches (the rehearsal of one step takes them so); a batch
    the plan lacks, and a plan file that is not there, end the run with a word, never a guess."""
    ids = _legacy_ids(16)
    plan = _legacy_plan(tmp_path, *[FX.plan_site(site_id) for site_id in ids])
    assert G.main(_legacy_args(tmp_path, plan, "--batch", "p4-1002"), runner=_db(*ids)) == 0
    assert "rows planned: 1 |" in capsys.readouterr().out
    assert sorted(path.name for path in (tmp_path / "apply").iterdir()) == ["p4l-1002"]
    assert G.main(_legacy_args(tmp_path, plan, "--batch", "p4-0036"), runner=_db(*ids)) == 1
    assert "no batch ['p4-0036']" in capsys.readouterr().err
    absent = tmp_path / "absent.jsonl"
    assert G.main(_legacy_args(tmp_path, absent), runner=_db(*ids)) == 1
    assert "no such L plan" in capsys.readouterr().err


def _rewritten(plan: Path, records: list[dict]) -> Path:
    plan.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return plan


def test_the_l_plan_is_read_strictly(tmp_path: Path) -> None:
    """A P4 plan (no `pass`) is not an L plan, and no site or batch id is listed twice."""
    first, second = _legacy_ids(2)
    plan = _legacy_plan(tmp_path, FX.plan_site(first))
    (record,) = [json.loads(line) for line in plan.read_text(encoding="utf-8").splitlines()]
    assert [b.batch_id for b in W4.load_legacy_plan(plan)] == ["p4-1001"]
    other = {**record, "sites": [FX.plan_site(second).to_dict()]}
    cases = [
        ([{k: v for k, v in record.items() if k != "pass"}], "not a lane-L plan batch"),
        ([record, {**record, "batch_id": "p4-1002", "ordinal": 1002}], "listed twice"),
        ([record, other], "batch p4-1001 twice"),
        ([{**record, "batch_id": "p4l-1001"}], "is not a plan batch id"),
    ]
    for records, message in cases:
        with pytest.raises(W4.PlanInputError, match=message):
            W4.load_legacy_plan(_rewritten(plan, records))


def test_a_re_plan_without_rows_drops_the_statements_an_earlier_dry_run_rendered(
    tmp_path, monkeypatch, capsys
) -> None:
    """A dry run renders a batch's statements; a later plan of that batch with no row (here: its
    site left the scope) must not leave them beside an empty PLAN.jsonl, where they would still
    write the old plan's rows by hand. A stopped batch keeps them: they are what was attempted."""
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    site = "00000001-0000-4000-8000-000000000001"
    statements = tmp_path / "apply" / "p4-0001" / W4.CHUNKS_DIR / "chunk-0001"
    assert G.main(_gate_args(tmp_path), runner=_db(site)) == 0
    assert (statements / W4.APPLY_FILE).exists()
    _scope_file(monkeypatch, tmp_path, "00000009-0000-4000-8000-000000000009")
    assert G.main(_gate_args(tmp_path), runner=_db(site)) == 0
    assert not statements.exists()
    assert (tmp_path / "apply" / "p4-0001" / W4.PLAN_FILE).read_text(encoding="utf-8") == ""

    monkeypatch.setattr(G, "_defect_scope", lambda: FX.EVERY_SITE)
    assert G.main(_gate_args(tmp_path), runner=_db(site)) == 0
    (tmp_path / "apply" / "p4-0001" / G.STOPPED_FILE).write_text("{}", encoding="utf-8")
    _scope_file(monkeypatch, tmp_path, "00000009-0000-4000-8000-000000000009")
    assert G.main(_gate_args(tmp_path), runner=_db(site)) == 0
    assert (statements / W4.APPLY_FILE).exists()


def test_a_reverted_rounds_record_survives_a_re_plan_without_rows(
    tmp_path, monkeypatch, capsys
) -> None:
    """Round 1 written, reverted and archived beside its statements (`chunks/chunk-0001/` with
    APPLIED.json and REVERTED.json); the site then leaves the scope. The re-plan has no row, and
    the reverted round's record - its statements included - stays exactly as it was."""
    db, out = _gate_written(tmp_path, monkeypatch)
    _revert_round(db, out, 1)
    assert G.main(_gate_args(tmp_path, "--round", "2"), runner=db) == 0  # re-opens, archives
    kept = out / W4.CHUNKS_DIR / "chunk-0001"
    before = {path.name: path.read_bytes() for path in kept.iterdir()}
    assert {G.APPLIED_FILE, G.REVERTED_FILE, W4.APPLY_FILE} <= set(before)
    _scope_file(monkeypatch, tmp_path, "00000009-0000-4000-8000-000000000009")
    capsys.readouterr()
    assert G.main(_gate_args(tmp_path), runner=db) == 0
    assert {path.name: path.read_bytes() for path in kept.iterdir()} == before


def test_the_gate_refuses_a_scope_file_that_is_not_the_pinned_one(
    tmp_path, monkeypatch, capsys
) -> None:
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    site = "00000001-0000-4000-8000-000000000001"
    path = _scope_file(monkeypatch, tmp_path, site)
    path.write_bytes(path.read_bytes() + b"\n")
    assert G.main(_gate_args(tmp_path), runner=_db(site)) == 1
    captured = capsys.readouterr()
    assert "is not the pinned scope" in captured.err
    assert captured.out.rstrip().endswith("WRITE_EXIT=1")
    assert not (tmp_path / "apply").exists()


# ── L and P5 ─────────────────────────────────────────────────────────────────────────────────────


def test_p5_writes_a_card_only_where_live_provenance_names_it(tmp_path: Path) -> None:
    batch = _batch(
        tmp_path,
        sites=[FX.plan_site(), FX.plan_site(FX.SITE_B), FX.plan_site(FX.SITE_C)],
        assemblies=[FX.assembly(), FX.assembly(FX.SITE_B), FX.assembly(FX.SITE_C)],
    )
    written = {FX.SITE_A: M.text_sha256(FX.CARD), FX.SITE_B: None}
    plan = W4.plan_cards(batch, scope=FX.EVERY_SITE, written=written, card_findings={})
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
    plan = W4.plan_cards(
        batch, scope=FX.EVERY_SITE, written={FX.SITE_A: None}, card_findings={FX.SITE_A: [finding]}
    )
    (row,) = plan.rows
    assert (row.test_id, row.old_value, row.new_value) == ("P5/card-clear", FX.OLD_CARD, None)
    assert row.evidence["phase3_findings"] == [finding]


@pytest.mark.parametrize("findings", [{}, {FX.SITE_A: []}], ids=["absent", "empty"])
def test_a_clear_without_its_phase3_finding_is_refused_loudly(tmp_path: Path, findings) -> None:
    flagged = FX.plan_site(flags=[M.SiteFlag.CLEARED_CARD_DEFECT])
    batch = _batch(tmp_path, sites=[flagged], holds=[_hold(FX.SITE_A, M.HoldReason.NO_SOURCE)])
    with pytest.raises(W4.PlanInputError, match="without its evidence"):
        W4.plan_cards(batch, scope=FX.EVERY_SITE, written={}, card_findings=findings)


def test_a_card_longer_than_the_column_is_refused(tmp_path: Path) -> None:
    long_card = "A" * 201
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly(card=long_card)])
    plan = W4.plan_cards(
        batch, scope=FX.EVERY_SITE, written={FX.SITE_A: M.text_sha256(long_card)}, card_findings={}
    )
    assert not plan.rows and plan.refusals[0].rule == W4.RULE_CARD_TOO_LONG


def test_a_p5_card_is_written_and_its_hash_matches_the_live_provenance(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    p4 = _p4(batch)
    db = _db(FX.SITE_A)
    db(W4.render_apply(W4.chunk_for(p4)), host="fake")
    plan = W4.plan_cards(
        batch, scope=FX.EVERY_SITE, written={FX.SITE_A: M.text_sha256(FX.CARD)}, card_findings={}
    )
    chunk, out = _written(tmp_path, plan)
    outcome = W4.apply_chunk(chunk, out=out, rehearse=False, runner=db)
    assert outcome.ok and db.sites[FX.SITE_A].card == FX.CARD


def test_the_card_invariant_refuses_a_card_the_provenance_does_not_name(tmp_path: Path) -> None:
    batch = _batch(tmp_path, sites=[FX.plan_site()], assemblies=[FX.assembly()])
    db = _db(FX.SITE_A)
    db(W4.render_apply(W4.chunk_for(_p4(batch))), host="fake")
    db.sites[FX.SITE_A].raw_data[M.PROVENANCE_KEY]["card"]["text_sha256"] = "0" * 64
    plan = W4.plan_cards(
        batch, scope=FX.EVERY_SITE, written={FX.SITE_A: M.text_sha256(FX.CARD)}, card_findings={}
    )
    with pytest.raises(W.WriteRefused, match="invariant 4"):
        db(W4.render_apply(W4.chunk_for(plan)), host="fake")


# ── revert4 ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "pattern", ["phase3:%", "%", "phase4%", "phase4l-x:%", "country-canonical:%"]
)
def test_revert_refuses_every_family_but_the_three_phase45_ones(pattern: str) -> None:
    with pytest.raises(R.RevertRefused):
        R.render_revert(pattern)


@pytest.mark.parametrize("pattern", ["phase5:%' OR '1'='1", "phase5:% ", "phase5:P5-%"])
def test_revert_refuses_a_pattern_outside_the_stamp_alphabet(pattern: str) -> None:
    with pytest.raises(R.RevertRefused, match="is not a run-stamp LIKE pattern"):
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
    assert "\nCOMMIT;\n" in sql and "\nROLLBACK;\n" in R.render_revert("phase5:%", rehearse=True)


def test_revert_refuses_rows_that_were_reverted_already() -> None:
    sql = R.render_revert("phase4:p4-0003:chunk-0001")
    assert "RAISE EXCEPTION 'revert: all % matched write(s) were reverted already', matched;" in sql


def test_revert4_carries_exactly_the_reviewed_guards() -> None:
    """Every guard, invariant and RAISE of the reversal, byte for byte (`phase4_write_pins`)."""
    sql = R.render_revert("phase5:%")
    assert sql[sql.index("BEGIN;") :] == PINS.P5_REVERT


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


# ── write rounds: a batch written again after a revert ──────────────────────────────────────────


def _revert_set(sql: str, entries: list[dict]) -> list[int]:
    """The journal ids the rendered reversal would revert: its own set query, evaluated."""
    query = sql.split("ids := ARRAY(", 1)[1].split("ORDER BY l.id);", 1)[0] + "ORDER BY l.id"
    return [row[0] for row in FX.journal_sqlite(entries).execute(query)]


def _write_round(tmp_path: Path, plan: W4.WritePlan4, db: FX.FakeDb, write_round: int):
    chunk = W4.chunk_for(plan, write_round=write_round)
    out = tmp_path / "apply" / f"{plan.batch_id}-round-{write_round}"
    W4.write_plan_files(out, plan, chunk)
    return chunk, W4.apply_chunk(chunk, out=out, rehearse=False, runner=db)


def _keep_reversal(db: FX.FakeDb, chunk: W4.Chunk4) -> None:
    """What `revert4` journals for a chunk: every row written back, under the chunk's stamp and each
    row's key plus `-rollback` - the chunk's own inverse, committed."""
    db(W4.render_rollback(chunk).replace("\nROLLBACK;\n", "\nCOMMIT;\n"), host="fake")


@pytest.mark.parametrize("order", ["oldest-first", "newest-first"])
def test_a_batch_written_again_after_a_revert_reads_back_its_own_round(
    tmp_path: Path, p4_chunk, order: str
) -> None:
    """Round 2 of a batch journals the same change keys as the reverted round 1; its read-back
    reads its own stamp's rows, in whatever order the journal returns them."""
    plan = W4.WritePlan4(W4.Group.P4, p4_chunk.batch_id, list(p4_chunk.rows))
    db = FX.FakeDb(
        {FX.SITE_A: FX.Site(raw_data=json.loads(json.dumps(FX.OLD_RAW)))}, journal_order=order
    )
    first, outcome = _write_round(tmp_path, plan, db, 1)
    assert outcome.ok
    _keep_reversal(db, first)
    second, outcome = _write_round(tmp_path, plan, db, 2)
    assert [row.change_key for row in second.rows] == [row.change_key for row in first.rows]
    assert outcome.ok and outcome.read_back.ok and second.stamp.endswith(":chunk-0002")


def test_revert4_reverts_the_live_round_and_refuses_the_reverted_one(tmp_path, p4_chunk) -> None:
    """The reversal of a write is found by its key **and** its stamp plus `-rollback`: round 2's
    rows share their keys with round 1's reversal and are still live."""
    plan = W4.WritePlan4(W4.Group.P4, p4_chunk.batch_id, list(p4_chunk.rows))
    db = _db(FX.SITE_A)
    first, _ = _write_round(tmp_path, plan, db, 1)
    _keep_reversal(db, first)
    second, _ = _write_round(tmp_path, plan, db, 2)
    live = [e["id"] for e in db.journal if e["run_stamp"] == second.stamp]
    journal = list(db.journal)

    assert _revert_set(R.render_revert(second.stamp), journal) == live
    assert _revert_set(R.render_revert("phase4:%"), journal) == live  # the family, too
    assert _revert_set(R.render_revert(first.stamp), journal) == []  # refused: reverted already
    assert FX.reversal_reads(R.render_revert(second.stamp), journal) == {
        "journalled writes matched": 2,
        "reversals kept": 0,
    }
    assert FX.reversal_reads(R.render_revert(first.stamp), journal) == {
        "journalled writes matched": 2,
        "reversals kept": 2,
    }
    _keep_reversal(db, second)  # the revert of round 2 commits
    assert FX.reversal_reads(R.render_revert("phase4:%"), db.journal) == {
        "journalled writes matched": 4,
        "reversals kept": 4,
    }
    # the gate asks the same read on its own, and parses it strictly
    assert R.reversal_counts(first.stamp, runner=db, host="fake") == (2, 2)


# ── revert4 --site: one written site taken back (the mass run's mid-run audit, 2026-09-25) ──────


def _two_sites_written(tmp_path: Path) -> tuple[FX.FakeDb, W4.Chunk4]:
    """One chunk that wrote sites A and B (two rows each), committed."""
    batch = _batch(
        tmp_path,
        sites=[FX.plan_site(), FX.plan_site(FX.SITE_B)],
        assemblies=[FX.assembly(), FX.assembly(FX.SITE_B)],
    )
    db = _db(FX.SITE_A, FX.SITE_B)
    chunk, outcome = _write_round(tmp_path, _p4(batch), db, 1)
    assert outcome.ok and len(chunk.rows) == 4
    return db, chunk


def _keep_site_reversal(db: FX.FakeDb, chunk: W4.Chunk4, site_id: str) -> None:
    """What `revert4 --site` journals: the site's rows of the chunk written back, under the chunk's
    stamp and each row's key plus `-rollback`; the chunk's other sites untouched."""
    rows = tuple(row for row in chunk.rows if row.site_id == site_id)
    _keep_reversal(db, dataclasses.replace(chunk, rows=rows))


def test_a_site_revert_takes_back_only_that_sites_rows_of_the_matched_writes(tmp_path) -> None:
    db, chunk = _two_sites_written(tmp_path)
    journal = list(db.journal)
    of_b = [e["id"] for e in journal if e["site_id_ref"] == FX.SITE_B]
    assert len(of_b) == 2
    assert _revert_set(R.render_revert(chunk.stamp, site=FX.SITE_B), journal) == of_b
    assert _revert_set(R.render_revert("phase4:%", site=FX.SITE_B), journal) == of_b
    assert FX.reversal_reads(R.render_revert(chunk.stamp, site=FX.SITE_B), journal) == {
        "journalled writes matched": 2,
        "reversals kept": 0,
    }
    _keep_site_reversal(db, chunk, FX.SITE_B)  # the site's revert commits
    assert db.value(FX.SITE_B, "description") == FX.OLD_DESCRIPTION
    assert db.value(FX.SITE_A, "description") == FX.DESCRIPTION  # the chunk's other site stays
    assert _revert_set(R.render_revert(chunk.stamp, site=FX.SITE_B), db.journal) == []
    assert FX.reversal_reads(R.render_revert(chunk.stamp, site=FX.SITE_B), db.journal) == {
        "journalled writes matched": 2,
        "reversals kept": 2,
    }
    # the chunk as a whole: its other site is still revertable, the reverted one is skipped
    of_a = [e["id"] for e in journal if e["site_id_ref"] == FX.SITE_A]
    assert _revert_set(R.render_revert(chunk.stamp), db.journal) == of_a
    assert R.reversal_counts(chunk.stamp, runner=db, host="fake") == (4, 2)
    assert R.reversal_counts(chunk.stamp, site=FX.SITE_B, runner=db, host="fake") == (2, 2)
    assert R.reversal_counts(chunk.stamp, site=FX.SITE_A, runner=db, host="fake") == (2, 0)


def test_a_site_revert_keeps_every_guard_and_invariant_of_the_pattern_revert() -> None:
    """The site narrows the matched set - and so the set every guard, the loop and both invariants
    run over - and changes nothing else: without its one predicate, the statement is the pattern's
    own, byte for byte after the header line that names the site."""
    stamp = "phase4:p4-0036:chunk-0001"
    site = "70037a24-6487-4834-9b50-5242289009fe"
    narrowed = R.render_revert(stamp, site=site, rehearse=True)
    predicate = f" AND l.site_id_ref = '{site}'"
    assert narrowed.count(predicate) == 4  # the count, the set, and both lines of the read after
    plain = R.render_revert(stamp, rehearse=True)
    assert narrowed.replace(predicate, "").split("BEGIN;", 1)[1] == plain.split("BEGIN;", 1)[1]
    assert f"-- reverts every journalled write of site {site} whose run stamp is LIKE" in narrowed
    assert "\nROLLBACK;\n" in narrowed and "\nCOMMIT;\n" in R.render_revert(stamp, site=site)


@pytest.mark.parametrize(
    "site",
    [
        "Roman Bath, York",
        "70037A24-6487-4834-9B50-5242289009FE",
        "70037a2464874834 9b505242289009fe",
        "70037a24-6487-4834-9b50-5242289009fe' OR '1'='1",
        "",
    ],
)
def test_revert_refuses_a_site_that_is_not_a_site_id(site: str) -> None:
    with pytest.raises(R.RevertRefused, match="is not a site id"):
        R.render_revert("phase4:p4-0036:chunk-0001", site=site)


def test_the_revert_command_takes_one_site(capsys: pytest.CaptureFixture[str]) -> None:
    site = "70037a24-6487-4834-9b50-5242289009fe"
    assert R.main(["--stamp-like", "phase4:p4-0036:chunk-0001", "--site", site]) == 0
    out = capsys.readouterr().out
    assert f"AND l.site_id_ref = '{site}'" in out and out.rstrip().endswith("WRITE_EXIT=0")
    assert R.main(["--stamp-like", "phase4:p4-0036:chunk-0001", "--site", "York"]) == 1
    assert capsys.readouterr().out.rstrip().endswith("WRITE_EXIT=1")


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "journalled writes matched|2\n",
        "journalled writes matched|2\nrows|2\n",
        "journalled writes matched|2\njournalled writes matched|2\n",
        "journalled writes matched|2\nreversals kept|\n",
    ],
    ids=["empty", "one-metric", "another-metric", "twice", "no-count"],
)
def test_the_reversal_read_is_parsed_strictly(answer: str) -> None:
    """The gate re-opens a written round on this answer: anything but exactly the two metric lines
    is refused, never read as zero."""
    with pytest.raises(W.WriteRefused, match="the reversal read of"):
        R.reversal_counts("phase4:p4-0001:chunk-0001", runner=lambda sql, host: answer, host="h")


# ── write_gate4 ──────────────────────────────────────────────────────────────────────────────────


def _gate_run(tmp_path: Path, sites: int) -> None:
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
    (run / M.LEDGER_FILE).write_text(
        "".join(
            json.dumps(row) + "\n"
            for number, site_id in enumerate(ids, start=1)
            for row in FX.ledger_rows(site_id, batch=f"p4-{number:04d}")
        ),
        encoding="utf-8",
    )


def _gate_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--group", "P4", "--run", "pilot", "--run-root", str(tmp_path / "runs"),
        "--apply-root", str(tmp_path / "apply"), "--open-lanes", "W,S",
        *extra,
    ]  # fmt: skip


def _acceptance(
    tmp_path: Path, *, journal_rows: int, name: str = "accept.log", **overrides
) -> Path:
    """What `verify_writes4.py --lane p4` prints for a clean step (its own lines, WB-C3)."""
    lines = {
        "head": f"lane p4 | stamps phase4:% | planned rows 6 | lane journal rows {journal_rows} | "
        f"carried {journal_rows} | not yet written 0 | superseded 0",
        "verified": "re-verified 2 written site(s) with V1-V15",
        "result": "RESULT: 0 deviation(s)",
        "exit": "ACCEPT_EXIT=0",
    }
    lines.update(overrides)
    path = tmp_path / name
    path.write_text("".join(f"{line}\n" for line in lines.values() if line), encoding="utf-8")
    return path


def test_the_gate_writes_one_step_and_stops_for_the_acceptance(
    tmp_path, monkeypatch, capsys
) -> None:
    _gate_run(tmp_path, 3)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    ids = [f"{n:08x}-0000-4000-8000-00000000000{n}" for n in range(1, 4)]
    db = _db(*ids)
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "2"), runner=db) == 0
    out = capsys.readouterr().out
    assert "STEP COMPLETE: 2 site(s)" in out and out.rstrip().endswith("WRITE_EXIT=0")
    applied = sorted(p.parent.name for p in (tmp_path / "apply").glob("*/APPLIED.json"))
    assert applied == ["p4-0001", "p4-0002"]
    step = json.loads((tmp_path / "apply" / G.STEP_FILE).read_text(encoding="utf-8"))
    assert step["stamps"] == ["phase4:p4-0001:chunk-0001", "phase4:p4-0002:chunk-0001"]
    plan_rows = (tmp_path / "apply" / G.LANE_PLAN_FILE).read_text(encoding="utf-8").splitlines()
    assert len(plan_rows) == 6  # every rendered batch's plan: the acceptance's --plan

    accept = _gate_args(tmp_path, "--accept", str(_acceptance(tmp_path, journal_rows=4)))
    assert G.main(accept, runner=db) == 0
    assert "ACCEPTED step 1" in capsys.readouterr().out
    assert not (tmp_path / "apply" / G.STEP_FILE).exists()
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "2"), runner=db) == 0
    assert (tmp_path / "apply" / "p4-0003" / "APPLIED.json").exists()


def test_the_gate_prints_the_acceptance_command_it_will_accept(
    tmp_path, monkeypatch, capsys
) -> None:
    """The step ends with the command to run: `verify_writes4.py` re-runs V1-V15 for lanes p4 and
    p5 and refuses to start without `--run` (wip/p4-verify, `accept_lane`), so the printed command
    names the lane, the lane plan and the run directory - copied as printed, it runs."""
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db("00000001-0000-4000-8000-000000000001")
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "1"), runner=db) == 0
    out = capsys.readouterr().out
    plan = tmp_path / "apply" / G.LANE_PLAN_FILE
    run = tmp_path / "runs" / "pilot"
    assert f"{G.VERIFY_TOOL} --lane p4 --plan {plan} --run {run} (0 deviations)" in out


def test_a_step_without_its_acceptance_blocks_the_next_step(tmp_path, monkeypatch, capsys) -> None:
    """The owner's "after every hundred, a check, and only then continue" is a precondition: a
    driver that calls the gate in a loop writes one step and no more."""
    _gate_run(tmp_path, 3)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db(*[f"{n:08x}-0000-4000-8000-00000000000{n}" for n in range(1, 4)])
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "1"), runner=db) == 0
    sent = len(db.sent)
    capsys.readouterr()
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "1"), runner=db) == 1
    out = capsys.readouterr().out
    assert "has no acceptance" in out and out.rstrip().endswith("WRITE_EXIT=1")
    assert len(db.sent) == sent  # nothing was sent, not even a preflight
    assert sorted(p.parent.name for p in (tmp_path / "apply").glob("*/APPLIED.json")) == ["p4-0001"]


def _gate_run_of(tmp_path: Path, *, batches: int, sites: int) -> list[str]:
    """A run of `batches` plan batches of `sites` sites each (the design's batches of 15)."""
    run = tmp_path / "runs" / "pilot"
    ids: list[str] = []
    ledger_rows: list[dict] = []
    for number in range(1, batches + 1):
        batch = [
            f"{number:04x}{n:04x}-0000-4000-8000-{number * 100 + n:012x}" for n in range(sites)
        ]
        FX.write_batch(
            run,
            sites=[FX.plan_site(site_id) for site_id in batch],
            assemblies=[FX.assembly(site_id) for site_id in batch],
            batch_id=f"p4-{number:04d}",
        )
        ledger_rows.extend(FX.ledger_rows(*batch, batch=f"p4-{number:04d}"))
        ids.extend(batch)
    (run / M.LEDGER_FILE).write_text(
        "".join(json.dumps(row) + "\n" for row in ledger_rows), encoding="utf-8"
    )
    return ids


def test_the_gate_reads_only_the_ledger_of_its_own_run(tmp_path, monkeypatch, capsys) -> None:
    """Pilots reuse the batch ids `p4-0001` .. (pilot 2's open item, 2026-09-24): pilot 1 asked the
    same site in the same batch id, in its own run directory. The P4 plan of pilot 2 reads pilot
    2's ledger (`<run>/LEDGER.jsonl`, `model4.LEDGER_FILE`) and nothing else, so no label of pilot
    1's calls - here a second select and review, and a translate - appears in its evidence; the
    runner root's shared ledger, which both pilots wrote before, is not read at all."""
    site_id = GATE_SITE
    pilot1 = FX.ledger_rows(site_id, batch="p4-0001") * 2 + [
        {**FX.ledger_rows(site_id, batch="p4-0001")[0], "label": f"{site_id}/translate"}
    ]
    pilot2 = FX.ledger_rows(site_id, batch="p4-0001")
    for run, rows in (("pilot1", pilot1), ("pilot2", pilot2)):
        run_dir = tmp_path / "runs" / run
        FX.write_batch(
            run_dir,
            sites=[FX.plan_site(site_id)],
            assemblies=[FX.assembly(site_id)],
            batch_id="p4-0001",
        )
        (run_dir / M.LEDGER_FILE).write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
    (tmp_path / "runs" / M.LEDGER_FILE).write_text(
        "".join(json.dumps(row) + "\n" for row in [*pilot1, *pilot2]), encoding="utf-8"
    )
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    args = [
        "--group", "P4", "--run", "pilot2", "--run-root", str(tmp_path / "runs"),
        "--apply-root", str(tmp_path / "apply"), "--open-lanes", "W,S",
    ]  # fmt: skip
    assert G.main(args, runner=_db(site_id)) == 0
    assert "refused by rule: {}" in capsys.readouterr().out
    rows = W4.read_plan(tmp_path / "apply" / "p4-0001", group=W4.Group.P4)
    assert rows
    for row in rows:
        assert row.evidence["ledger_labels"] == [f"{site_id}/select", f"{site_id}/review"]


def test_a_third_run_is_written_into_the_apply_root_two_runs_wrote(
    tmp_path, monkeypatch, capsys
) -> None:
    """The D9 run (owner order 2026-09-25) writes into the P4 apply root pilot 4 and the mass run
    wrote. Its batch id is its own (`plan4.LIST_PLAN_FIRST_BATCH`, p4-0901), so the gate renders it
    beside theirs and leaves their record byte for byte, asks its step's acceptance like any other,
    and the lane plan the acceptance reads carries every run's rows."""
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    batches = {"pilot4": "p4-0001", "mass": "p4-0010", "d9": "p4-0901"}
    sites = {run: f"{n:08x}-0000-4000-8000-{n:012x}" for n, run in enumerate(batches, start=1)}
    for run, batch_id in batches.items():
        run_dir = tmp_path / "runs" / run
        site_id = sites[run]
        FX.write_batch(
            run_dir,
            sites=[FX.plan_site(site_id)],
            assemblies=[FX.assembly(site_id)],
            batch_id=batch_id,
        )
        (run_dir / M.LEDGER_FILE).write_text(
            "".join(json.dumps(r) + "\n" for r in FX.ledger_rows(site_id, batch=batch_id)),
            encoding="utf-8",
        )
    db = _db(*sites.values())
    apply = tmp_path / "apply"

    def gate(run: str, *extra: str) -> int:
        args = ["--group", "P4", "--run", run, "--run-root", str(tmp_path / "runs"),
                "--apply-root", str(apply), "--open-lanes", "W,S", *extra]  # fmt: skip
        return G.main(args, runner=db)

    for step, run in enumerate(("pilot4", "mass"), start=1):
        assert gate(run, "--apply", "--step", "100") == 0
        accepted = _acceptance(tmp_path, journal_rows=2 * step, name=f"accept-{step}.log")
        assert gate(run, "--accept", str(accepted)) == 0
    before = {
        path: path.read_bytes()
        for path in apply.rglob("*")
        if path.is_file() and path.name != G.LANE_PLAN_FILE
    }
    capsys.readouterr()

    assert gate("d9") == 0
    assert "rows planned: 2 | refused by rule: {}" in capsys.readouterr().out
    assert gate("d9", "--apply", "--step", "100") == 0

    assert "STEP COMPLETE: 1 site(s) written in 1 batch(es)" in capsys.readouterr().out
    step = json.loads((apply / G.STEP_FILE).read_text(encoding="utf-8"))
    assert step["stamps"] == ["phase4:p4-0901:chunk-0001"]
    assert {path: path.read_bytes() for path in before} == before
    lane_plan = (apply / G.LANE_PLAN_FILE).read_text(encoding="utf-8").splitlines()
    assert sorted(json.loads(line)["site_id"] for line in lane_plan) == sorted(
        2 * [*sites.values()]
    )
    accepted = _acceptance(tmp_path, journal_rows=6, name="accept-3.log")
    assert gate("d9", "--accept", str(accepted)) == 0
    assert len(list((apply / G.ACCEPTED_DIR).glob("step-*.json"))) == 3


def test_a_step_of_100_sites_never_writes_more_than_100(tmp_path, monkeypatch, capsys) -> None:
    """Batches of 15: the step stops before the batch that would carry it past 100 - 90 sites, not
    105 (design: CHUNK = ONE STEP = 100 SITES)."""
    ids = _gate_run_of(tmp_path, batches=8, sites=15)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db(*ids)
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "100"), runner=db) == 0
    assert "STEP COMPLETE: 90 site(s) written in 6 batch(es)" in capsys.readouterr().out
    written = {entry["site_id_ref"] for entry in db.journal}
    assert len(written) == 90


def test_a_batch_larger_than_the_step_is_refused(tmp_path, monkeypatch, capsys) -> None:
    ids = _gate_run_of(tmp_path, batches=1, sites=3)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db(*ids)
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "2"), runner=db) == 1
    assert "3 sites in one batch; the step is 2" in capsys.readouterr().out and not db.journal


@pytest.mark.parametrize(
    ("overrides", "journal_rows", "problem"),
    [
        ({"exit": "ACCEPT_EXIT=1"}, 2, "does not end in ACCEPT_EXIT=0"),
        ({"result": "RESULT: 1 deviation(s)"}, 2, "does not say"),
        ({"head": ""}, 2, "0 lane line(s)"),
        (
            {
                "head": "lane p5 | stamps phase5:% | planned rows 1 | lane journal rows 2 | carried 2"
            },
            2,
            "the step is lane p4",
        ),
        (
            {
                "head": "lane p4 | stamps phase4:p4-0009:% | planned rows 1 | lane journal rows 2 | x"
            },
            2,
            "do not cover",
        ),
        ({}, 1, "it was run before this step"),
    ],
)
def test_an_acceptance_that_does_not_accept_this_step_is_refused(
    tmp_path, monkeypatch, capsys, overrides, journal_rows, problem
) -> None:
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db("00000001-0000-4000-8000-000000000001")
    assert G.main(_gate_args(tmp_path, "--apply"), runner=db) == 0
    capsys.readouterr()
    output = _acceptance(tmp_path, journal_rows=journal_rows, **overrides)
    assert G.main(_gate_args(tmp_path, "--accept", str(output)), runner=db) == 1
    assert problem in capsys.readouterr().out
    assert (tmp_path / "apply" / G.STEP_FILE).exists()


def test_one_acceptance_output_never_accepts_two_steps(tmp_path, monkeypatch, capsys) -> None:
    _gate_run(tmp_path, 2)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db(*[f"{n:08x}-0000-4000-8000-00000000000{n}" for n in range(1, 3)])
    output = _acceptance(tmp_path, journal_rows=4)
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "1"), runner=db) == 0
    assert G.main(_gate_args(tmp_path, "--accept", str(output)), runner=db) == 0
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "1"), runner=db) == 0
    capsys.readouterr()
    assert G.main(_gate_args(tmp_path, "--accept", str(output)), runner=db) == 1
    assert "an earlier step was accepted on this very output" in capsys.readouterr().out


def test_like_matches_is_sql_like() -> None:
    assert G.like_matches("phase4:%", "phase4:p4-0001:chunk-0001")
    assert G.like_matches("phase4:p4-000_:%", "phase4:p4-0001:chunk-0001")
    assert not G.like_matches("phase4:%", "phase4l:p4l-0001:chunk-0001")
    assert not G.like_matches("phase4.p4%", "phase4:p4-0001")  # a dot is a dot


def test_the_dry_run_sends_nothing(tmp_path, monkeypatch, capsys) -> None:
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db("00000001-0000-4000-8000-000000000001")
    assert G.main(_gate_args(tmp_path), runner=db) == 0
    assert db.sent == [] and "dry run, nothing is sent" in capsys.readouterr().out
    assert (tmp_path / "apply" / "p4-0001" / "chunks" / "chunk-0001" / "APPLY.sql").exists()


def test_a_blocked_batch_stops_the_run_and_is_refused_until_read(
    tmp_path, monkeypatch, capsys
) -> None:
    _gate_run(tmp_path, 2)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    first = "00000001-0000-4000-8000-000000000001"
    db = _db(first, "00000002-0000-4000-8000-000000000002")
    db.sites[first].description = "moved"
    assert G.main(_gate_args(tmp_path, "--apply"), runner=db) == 1
    assert (tmp_path / "apply" / "p4-0001" / "STOPPED.json").exists()
    assert not (tmp_path / "apply" / "p4-0002" / "APPLIED.json").exists()
    db.sites[first].description = FX.OLD_DESCRIPTION
    assert G.main(_gate_args(tmp_path, "--apply"), runner=db) == 1
    assert "stopped in an earlier run" in capsys.readouterr().out


def test_a_written_batch_keeps_the_plan_it_was_written_from(tmp_path, monkeypatch) -> None:
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db("00000001-0000-4000-8000-000000000001")
    assert G.main(_gate_args(tmp_path, "--apply"), runner=db) == 0
    monkeypatch.setattr(
        G, "_verifier", lambda: FX.Verify({"00000001-0000-4000-8000-000000000001": [
            _hold("00000001-0000-4000-8000-000000000001", M.HoldReason.V9)]})
    )  # fmt: skip
    assert G.main(_gate_args(tmp_path), runner=db) == 1


# ── write rounds through the gate: a reverted batch is written again as its next round ─────────

GATE_SITE = "00000001-0000-4000-8000-000000000001"
ROUND_1 = "phase4:p4-0001:chunk-0001"
ROUND_2 = "phase4:p4-0001:chunk-0002"


def _revert_round(db: FX.FakeDb, out: Path, write_round: int = 1) -> None:
    """What `revert4` journals for one written round of a batch: the round's own ROLLBACK.sql,
    committed - every row written back under the round's stamp and key plus `-rollback`."""
    chunk = out / W4.CHUNKS_DIR / f"chunk-{write_round:04d}"
    sql = (chunk / W4.ROLLBACK_FILE).read_text(encoding="utf-8")
    db(sql.replace("\nROLLBACK;\n", "\nCOMMIT;\n"), host="fake")


def _gate_written(tmp_path: Path, monkeypatch, *, accept: bool = True):
    """One batch of one site written through the gate as round 1 (and its step accepted)."""
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db(GATE_SITE)
    assert G.main(_gate_args(tmp_path, "--apply"), runner=db) == 0
    if accept:
        output = _acceptance(tmp_path, journal_rows=2, name="round-1.log")
        assert G.main(_gate_args(tmp_path, "--accept", str(output)), runner=db) == 0
    return db, tmp_path / "apply" / "p4-0001"


def _stamp_of(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["run_stamp"]


def test_a_reverted_batch_is_written_again_as_round_2(tmp_path, monkeypatch, capsys) -> None:
    """The documented recovery - write, revert (`revert4`), `--apply --round 2` - writes chunk-0002.
    The gate re-opens the batch on production's word that round 1 is reverted, and keeps round 1's
    record beside its statements; it never answers 'no open batch' over a reverted batch."""
    db, out = _gate_written(tmp_path, monkeypatch)
    _revert_round(db, out, 1)
    capsys.readouterr()
    assert G.main(_gate_args(tmp_path, "--apply", "--round", "2"), runner=db) == 0
    assert "STEP COMPLETE: 1 site(s) written in 1 batch(es)" in capsys.readouterr().out
    assert [entry["run_stamp"] for entry in db.journal].count(ROUND_2) == 2
    assert _stamp_of(out / G.APPLIED_FILE) == ROUND_2
    kept = out / W4.CHUNKS_DIR / "chunk-0001"
    assert _stamp_of(kept / G.APPLIED_FILE) == ROUND_1
    proof = json.loads((kept / G.REVERTED_FILE).read_text(encoding="utf-8"))
    assert (proof["run_stamp"], proof["write_round"], proof["reversals_kept"]) == (ROUND_1, 1, 2)
    step = json.loads((tmp_path / "apply" / G.STEP_FILE).read_text(encoding="utf-8"))
    assert step["stamps"] == [ROUND_2]


def _drop_reversal_of_one_row(db: FX.FakeDb) -> None:
    db.journal.remove(next(e for e in db.journal if e["run_stamp"] == ROUND_1 + "-rollback"))


def _drop_round_1(db: FX.FakeDb) -> None:
    db.journal[:] = [e for e in db.journal if not e["run_stamp"].startswith(ROUND_1)]


@pytest.mark.parametrize(
    ("revert", "damage"),
    [(False, None), (True, _drop_reversal_of_one_row), (True, _drop_round_1)],
    ids=["round-1-live", "half-reverted", "never-journalled"],
)
def test_a_batch_is_re_opened_only_when_production_holds_its_reversal(
    tmp_path, monkeypatch, capsys, revert, damage
) -> None:
    """Round 2 needs every row of round 1's stamp journalled, as many as round 1 wrote, each with its
    own reversal kept. Without that proof the record stays, nothing is rendered and nothing written."""
    db, out = _gate_written(tmp_path, monkeypatch)
    if revert:
        _revert_round(db, out, 1)
    if damage is not None:
        damage(db)
    journal = list(db.journal)
    capsys.readouterr()
    assert G.main(_gate_args(tmp_path, "--apply", "--round", "2"), runner=db) == 1
    captured = capsys.readouterr()
    assert "round 1 is not reverted in production" in captured.err
    assert captured.out.rstrip().endswith("WRITE_EXIT=1")
    assert _stamp_of(out / G.APPLIED_FILE) == ROUND_1
    assert not (out / W4.CHUNKS_DIR / "chunk-0002").exists()
    assert db.journal == journal


def _reopened(tmp_path: Path, monkeypatch):
    """Round 1 written, reverted, and the batch re-opened for round 2 by a dry run."""
    db, out = _gate_written(tmp_path, monkeypatch)
    _revert_round(db, out, 1)
    assert G.main(_gate_args(tmp_path, "--round", "2"), runner=db) == 0
    assert not (out / G.APPLIED_FILE).exists()
    return db, out


@pytest.mark.parametrize(
    ("state", "write_round", "problem"),
    [
        ("reverted", "3", "was written in round 1; --round 3 re-writes a batch whose round 2"),
        ("never-written", "2", "its next write is round 1, not --round 2"),
        ("re-opened", "1", "its next write is round 2, not --round 1"),
    ],
)
def test_a_round_the_batch_cannot_take_is_refused_loudly(
    tmp_path, monkeypatch, capsys, state, write_round, problem
) -> None:
    """A write round follows the batch's reverted rounds one by one: round 3 needs a reverted
    round 2, a batch never written starts at round 1, and a re-opened batch never writes round 1's
    stamp again (its statements are the reverted round's record)."""
    if state == "reverted":
        db, out = _gate_written(tmp_path, monkeypatch)
        _revert_round(db, out, 1)
    elif state == "never-written":
        _gate_run(tmp_path, 1)
        monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
        db, out = _db(GATE_SITE), tmp_path / "apply" / "p4-0001"
    else:
        db, out = _reopened(tmp_path, monkeypatch)
    journal = list(db.journal)
    capsys.readouterr()
    args = _gate_args(tmp_path, "--apply", "--round", write_round)
    assert G.main(args, runner=db) == 1
    assert problem in capsys.readouterr().err
    assert db.journal == journal and not (out / G.STOPPED_FILE).exists()
    if state == "re-opened":  # round 1's statements stay the reverted round's record
        assert _stamp_of(out / W4.CHUNKS_DIR / "chunk-0001" / G.APPLIED_FILE) == ROUND_1
    else:
        assert not (out / W4.CHUNKS_DIR / f"chunk-{int(write_round):04d}").exists()


def test_a_reverted_step_is_closed_on_its_reversal_and_written_again(
    tmp_path, monkeypatch, capsys
) -> None:
    """A step whose acceptance was red and that `revert4` took back can never be accepted: every
    link it wrote now has a later one. `--close-reverted` records it as closed on production's word
    that every row of every stamp is reverted, and its batches are then written as round 2. Until
    then the batch is frozen: `--round 2` does not re-open a batch of the pending step."""
    db, out = _gate_written(tmp_path, monkeypatch, accept=False)
    _revert_round(db, out, 1)
    capsys.readouterr()
    assert G.main(_gate_args(tmp_path, "--apply", "--round", "2"), runner=db) == 1
    assert "belongs to the written step that awaits its acceptance" in capsys.readouterr().err
    assert _stamp_of(out / G.APPLIED_FILE) == ROUND_1

    assert G.main(_gate_args(tmp_path, "--close-reverted"), runner=db) == 0
    assert "CLOSED step 1 by its reversal: 1 site(s) in 1 batch(es)" in capsys.readouterr().out
    assert not (tmp_path / "apply" / G.STEP_FILE).exists()
    assert not (tmp_path / "apply" / G.ACCEPTED_DIR).exists()  # closed, never accepted
    closed = json.loads(
        (tmp_path / "apply" / G.CLOSED_DIR / "step-0001.json").read_text(encoding="utf-8")
    )
    assert closed["stamps"] == [ROUND_1] and closed["proofs"][0]["reversals_kept"] == 2
    assert _stamp_of(out / W4.CHUNKS_DIR / "chunk-0001" / G.APPLIED_FILE) == ROUND_1

    assert G.main(_gate_args(tmp_path, "--apply", "--round", "2"), runner=db) == 0
    assert [entry["run_stamp"] for entry in db.journal].count(ROUND_2) == 2


def test_a_step_whose_rows_are_live_is_not_closed(tmp_path, monkeypatch, capsys) -> None:
    db, out = _gate_written(tmp_path, monkeypatch, accept=False)
    capsys.readouterr()
    assert G.main(_gate_args(tmp_path, "--close-reverted"), runner=db) == 1
    assert "round 1 is not reverted in production" in capsys.readouterr().err
    assert (tmp_path / "apply" / G.STEP_FILE).exists()
    assert _stamp_of(out / G.APPLIED_FILE) == ROUND_1
    assert not (tmp_path / "apply" / G.CLOSED_DIR).exists()


@pytest.mark.parametrize(
    ("stamps", "journal_rows", "accepted"),
    [
        ("phase4:%", 2, False),  # read after the revert, before round 2: round 1's rows only
        ("phase4:%", 4, True),  # every round's rows (a reversal is not a lane row)
        ("phase4:%:chunk-0002", 2, True),  # a narrowed pattern reads the rounds it covers
    ],
)
def test_the_acceptance_must_have_read_every_round_its_stamps_cover(
    tmp_path, monkeypatch, capsys, stamps, journal_rows, accepted
) -> None:
    """'Read at least the rows written so far' counts every written round - the reverted one's
    record is kept, not dropped - under the stamps the output read. Counting only the live rounds
    would let an output taken after the revert, before round 2, accept round 2."""
    db, out = _gate_written(tmp_path, monkeypatch)
    _revert_round(db, out, 1)
    assert G.main(_gate_args(tmp_path, "--apply", "--round", "2"), runner=db) == 0
    head = (
        f"lane p4 | stamps {stamps} | planned rows 2 | lane journal rows {journal_rows} | "
        f"carried 2 | not yet written 0 | superseded 0"
    )
    output = _acceptance(tmp_path, journal_rows=journal_rows, name="round-2.log", head=head)
    capsys.readouterr()
    code = G.main(_gate_args(tmp_path, "--accept", str(output)), runner=db)
    printed = capsys.readouterr().out
    assert code == (0 if accepted else 1)
    assert ("it was run before this step" in printed) is not accepted


def test_the_unclaimed_sites_are_counted_by_reason(tmp_path: Path) -> None:
    """HUMAN_ONLY D7 lists them by reason: a text equal to the pre-March one and a site the snapshot
    does not have are two counts, never one sum."""
    no_claim = W4.legacy4.NoClaim
    plan = W4.WritePlan4(
        W4.Group.L,
        "p4l-0001",
        unclaimed=[
            W4.legacy4.Unclaimed(FX.SITE_A, "A", no_claim.SAME_AS_SNAPSHOT),
            W4.legacy4.Unclaimed(FX.SITE_B, "B", no_claim.NOT_IN_SNAPSHOT),
            W4.legacy4.Unclaimed(FX.SITE_C, "C", no_claim.NOT_IN_SNAPSHOT),
        ],
    )
    planned = [G.Planned(out=tmp_path, plan=plan, chunk=None)]
    assert G.unclaimed_by_reason(planned) == {"not-in-snapshot": 2, "same-as-snapshot": 1}


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


def test_p4_is_never_planned_without_an_open_lane(tmp_path, monkeypatch, capsys) -> None:
    _gate_run(tmp_path, 1)
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    args = _gate_args(tmp_path)
    args[args.index("--open-lanes") + 1] = ""
    assert G.main(args, runner=_db()) == 1
    assert "P4 writes only lanes whose pilot passed" in capsys.readouterr().err
    assert not (tmp_path / "apply").exists()


def test_a_step_of_no_site_is_refused(tmp_path, monkeypatch, capsys) -> None:
    _gate_run(tmp_path, 1)
    assert G.main(_gate_args(tmp_path, "--apply", "--step", "0"), runner=_db()) == 1
    assert "at least one site per step" in capsys.readouterr().err


def test_the_audited_list_is_site_ids_only(tmp_path: Path) -> None:
    audited = tmp_path / "audited.txt"
    audited.write_text(f"{FX.SITE_A}\n\n{FX.SITE_B}\n", encoding="utf-8")
    assert G.read_audited(audited) == frozenset({FX.SITE_A, FX.SITE_B})
    audited.write_text(f"{FX.SITE_A}\nTarxien Temples\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"audited.txt:2: 'Tarxien Temples' is not a site id"):
        G.read_audited(audited)


def test_a_card_clear_is_evidenced_only_by_a_cleared_card_finding(tmp_path: Path) -> None:
    """The 709: Phase-3 refusals under `report-only-field` for `card_description`, each with the
    finder's answer and the reviewer's verdict. Another field, or another rule, is not a card
    finding."""
    run_dir = tmp_path / "runs" / "mass"
    batch = run_dir / "batch-0001"
    FX.F.EvidenceStore(batch / "answers").write(
        site_id=FX.SITE_A, feature="card_description", body=b"WRONG: the card names another site"
    )
    verdict = {"site_id": FX.SITE_A, "field": "card_description", "verdict": "NOT_REFUTED"}
    other = {"site_id": FX.SITE_A, "field": "country", "verdict": "NOT_REFUTED"}
    (batch / "review.json").write_text(json.dumps({"verdicts": [verdict, other]}), encoding="utf-8")
    card = {"batch_id": "batch-0001", "site_id": FX.SITE_A, "field": "card_description"}
    refused = tmp_path / "ALL_REFUSED.jsonl"
    refused.write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in (
                {**card, "rule": G.PHASE3_REPORT_ONLY},
                {**card, "field": "country", "rule": G.PHASE3_REPORT_ONLY},
                {**card, "site_id": FX.SITE_B, "rule": "reviewer-did-not-clear"},
            )
        ),
        encoding="utf-8",
    )
    findings = G.phase3_card_findings(refused, run_dir)
    assert findings == {
        FX.SITE_A: [
            {
                "refusal": {**card, "rule": G.PHASE3_REPORT_ONLY},
                "finder_answer": "WRONG: the card names another site",
                "reviewer": verdict,
            }
        ]
    }


# ── one written site taken back: the batch's re-plan leaves it out (mid-run audit, 2026-09-25) ──

GATE_B = "00000002-0000-4000-8000-000000000002"


def _gate_two_sites_written(tmp_path: Path, monkeypatch) -> tuple[FX.FakeDb, Path, Path]:
    """One batch of two sites written through the gate as round 1, its step accepted."""
    run = tmp_path / "runs" / "pilot"
    batch_dir = FX.write_batch(
        run,
        sites=[FX.plan_site(GATE_SITE), FX.plan_site(GATE_B)],
        assemblies=[FX.assembly(GATE_SITE), FX.assembly(GATE_B)],
        batch_id="p4-0001",
    )
    (run / M.LEDGER_FILE).write_text(
        "".join(json.dumps(r) + "\n" for r in FX.ledger_rows(GATE_SITE, GATE_B, batch="p4-0001")),
        encoding="utf-8",
    )
    monkeypatch.setattr(G, "_verifier", lambda: FX.Verify())
    db = _db(GATE_SITE, GATE_B)
    assert G.main(_gate_args(tmp_path, "--apply"), runner=db) == 0
    output = _acceptance(tmp_path, journal_rows=4, name="round-1.log")
    assert G.main(_gate_args(tmp_path, "--accept", str(output)), runner=db) == 0
    return db, batch_dir, tmp_path / "apply" / "p4-0001"


def _revert_site(db: FX.FakeDb, out: Path, site_id: str) -> None:
    """What `revert4 --stamp-like <round 1> --site <site>` journals: the site's rows of round 1
    written back under the round's stamp and each key plus `-rollback`, committed."""
    rows = [row for row in W4.read_plan(out, group=W4.Group.P4) if row.site_id == site_id]
    chunk = W4.chunk_for(W4.WritePlan4(W4.Group.P4, "p4-0001", rows))
    db(W4.render_rollback(chunk).replace("\nROLLBACK;\n", "\nCOMMIT;\n"), host="fake")


def _audit_hold(batch_dir: Path, site_id: str) -> None:
    hold = M.Hold(
        site_id=site_id,
        scope=M.HoldScope.SITE,
        reason=M.HoldReason.AUDIT_WRONG_SITE,
        detail="MIDRUN_AUDIT_VERDICTS.json: sentence 1 WRONG_SITE",
    )
    with (batch_dir / M.HOLDS_FILE).open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(hold.to_json() + "\n")


def test_a_written_batch_is_re_planned_without_a_held_site_once_its_rows_are_reverted(
    tmp_path, monkeypatch, capsys
) -> None:
    """A site the audit held after its batch was written is planned by no one again; the batch's
    re-plan leaves it out. The gate accepts that re-plan only on production's word, read-only, that
    every row round 1 wrote for the site has its own reversal kept (`revert4 --site`): what is live
    of the batch is then exactly the re-plan. The batch keeps the plan it was written from - its
    `PLAN.jsonl` and `APPLIED.json` - and nothing is written."""
    db, batch_dir, out = _gate_two_sites_written(tmp_path, monkeypatch)
    plan_bytes = (out / W4.PLAN_FILE).read_bytes()
    applied_bytes = (out / G.APPLIED_FILE).read_bytes()
    _audit_hold(batch_dir, GATE_B)
    capsys.readouterr()

    assert G.main(_gate_args(tmp_path), runner=db) == 1  # held, but its rows are still live
    captured = capsys.readouterr()
    assert f"revert4.py --stamp-like '{ROUND_1}' --site {GATE_B}" in captured.err
    assert captured.out.rstrip().endswith("WRITE_EXIT=1")

    _revert_site(db, out, GATE_B)
    journal = list(db.journal)
    assert G.main(_gate_args(tmp_path), runner=db) == 0
    printed = capsys.readouterr().out
    assert f"p4-0001: {GATE_B} left out of the re-plan" in printed
    assert "its 2 row(s) of round 1 have their own reversal kept" in printed
    assert "rows planned: 2 |" in printed and "open batches: 0" in printed
    assert (out / W4.PLAN_FILE).read_bytes() == plan_bytes
    assert (out / G.APPLIED_FILE).read_bytes() == applied_bytes
    assert G.main(_gate_args(tmp_path, "--apply"), runner=db) == 0
    assert "done: no open batch left to write" in capsys.readouterr().out
    assert db.journal == journal


def test_a_written_batch_is_never_re_planned_to_other_rows(tmp_path, monkeypatch, capsys) -> None:
    """Only a left-out site whose rows are reverted is accepted: a re-plan that changes a written
    row - here site A's text - is refused, reverted rows of another site or not."""
    db, batch_dir, out = _gate_two_sites_written(tmp_path, monkeypatch)
    _audit_hold(batch_dir, GATE_B)
    _revert_site(db, out, GATE_B)
    assemblies = [FX.assembly(GATE_SITE, description=FX.DESCRIPTION.replace("1915", "1916"))]
    (batch_dir / M.ASSEMBLY_FILE).write_text(
        M.dump_jsonl([*assemblies, FX.assembly(GATE_B)]), encoding="utf-8"
    )
    capsys.readouterr()
    assert G.main(_gate_args(tmp_path), runner=db) == 1
    assert "this batch was written from another plan" in capsys.readouterr().err
