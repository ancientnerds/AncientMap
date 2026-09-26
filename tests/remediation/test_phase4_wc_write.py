"""Lane WC's write (owner decision O5, 2026-09-26): the writer's group WC, the gate and the step's
acceptance - does a checked March text reach production only as the plan says, journalled, in steps,
and does the acceptance refuse anything else?

`phase4/write4.py` (group WC: `plan_wc`, `load_wc_plan`, the WC rules of `validate_rows`, guard 3's
clear tests and invariants 5-6), `output/remediation/tools/write_gate4.py --group WC --wc-plan` and
`output/remediation/tools/verify_writes4.py --lane p4wc`. The fake psql parses what it is sent
(`phase4_write_fixtures.FakeDb`), the fake production answers only read-only SELECTs
(`test_phase4_accept.FakeProduction`). The mutation cases are `WC_MUTATIONS`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import lanes  # noqa: E402
import verify_writes4 as A  # noqa: E402
import write_gate4 as G  # noqa: E402
from phase4 import revert4 as R  # noqa: E402

from tests.remediation import phase4_write_fixtures as PFX  # noqa: E402
from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4, M  # noqa: E402
from tests.remediation.test_phase4_accept import FakeProduction  # noqa: E402
from tests.remediation.test_phase4_write import _keep_reversal, _revert_set  # noqa: E402
from tests.remediation.wc_fixtures import WC4  # noqa: E402

UNCHANGED = "0e000000-0000-4000-8000-00000000000e"
TEXT_E = "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]."


def _rows() -> list[dict[str, Any]]:
    """A (lane L, trimmed), B (a March text without lane L's marking, kept: it gains the marking),
    C (lane L, cleared), E (kept byte for byte)."""
    text_b = "The Tarxien Temples are an archaeological complex in Tarxien, Malta."
    return [
        FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A, title_es="Templos")),
        FX.row(FX.SITE_B, text_b, raw_data=None, name="Tarxien B"),
        FX.row(FX.SITE_C, "Giants built it in one night. It glows at dusk.",
               raw_data=FX.legacy_raw("Giants built it in one night. It glows at dusk.")),
        FX.row(UNCHANGED, TEXT_E, raw_data={
            M.CITATIONS_KEY: [{"n": 1, "url": FX.WIKI, "title": "Tarxien Temples - Wikipedia",
                               "domain": "en.wikipedia.org", "claim": "old"}],
            M.PROVENANCE_KEY: M.LegacyProvenance(desc_sha256=M.text_sha256(TEXT_E)).to_dict(),
        }),
    ]  # fmt: skip


def _answers() -> dict[str, str]:
    return {
        FX.SITE_A: FX.answer(FX.SITE_A, [
            FX.keep(1, FX.Q_COMPLEX),
            FX.trimmed(2, ", and they were built by giants", FX.Q_DATE),
            FX.keep(3, FX.Q_ZAMMIT),
        ]),
        FX.SITE_B: FX.answer(FX.SITE_B, [FX.keep(1, FX.Q_COMPLEX)]),
        FX.SITE_C: FX.answer(FX.SITE_C, [FX.drop(1), FX.drop(2)]),
        UNCHANGED: FX.answer(UNCHANGED, [
            FX.keep(1, FX.quote(FX.WIKI, "The Tarxien Temples are an archaeological complex")),
        ]),
    }  # fmt: skip


def _plan(tmp_path: Path) -> Path:
    return FX.build_run(tmp_path, _rows(), _answers())[1]


def _db(rows=None) -> PFX.FakeDb:
    return PFX.FakeDb(
        {
            row["id"]: PFX.Site(description=row["description"], raw_data=row["raw_data"])
            for row in (rows or _rows())
        }
    )


def _loaded(tmp_path: Path):
    batches, outcomes = W4.load_wc_plan([_plan(tmp_path)])
    (batch,) = batches
    return batch, outcomes


def _live(db: PFX.FakeDb) -> dict[str, dict[str, Any]]:
    return {
        site_id: {"description": site.description, "raw_data": site.raw_data}
        for site_id, site in db.sites.items()
    }


# ------------------------------------------------------------------------------ the plan
def test_each_checked_site_becomes_its_rows_kept_cleared_or_raw_data_alone(tmp_path: Path) -> None:
    batch, outcomes = _loaded(tmp_path)
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db()))
    assert plan.batch_id == "p4wc-4001" and not plan.refusals
    rows = {(row.site_id, row.column): row for row in plan.rows}
    assert rows[(FX.SITE_A, "description")].test_id == W4.TEST_WC_DESCRIPTION
    assert rows[(FX.SITE_A, "raw_data")].test_id == W4.TEST_WC_RAW_DATA
    assert rows[(FX.SITE_C, "description")].new_value is None
    assert rows[(FX.SITE_C, "description")].test_id == W4.TEST_WC_DESCRIPTION_CLEAR
    assert rows[(FX.SITE_C, "raw_data")].new_value is None
    assert rows[(FX.SITE_C, "raw_data")].test_id == W4.TEST_WC_RAW_DATA_CLEAR
    assert (UNCHANGED, "description") not in rows
    assert rows[(UNCHANGED, "raw_data")].test_id == W4.TEST_WC_RAW_DATA
    new_a = json.loads(rows[(FX.SITE_A, "raw_data")].new_value)
    assert new_a["title_es"] == "Templos" and new_a[M.PROVENANCE_KEY]["lane"] == "L"
    assert json.loads(rows[(FX.SITE_B, "raw_data")].new_value)[M.PROVENANCE_KEY] == (
        M.LegacyProvenance(desc_sha256=M.text_sha256(TEXT_E)).to_dict()
    )
    assert all(row.change_key.startswith("phase4wc:") for row in plan.rows)
    assert rows[(FX.SITE_A, "raw_data")].evidence == outcomes[FX.SITE_A].evidence


def test_a_site_phase4_wrote_or_that_moved_since_its_check_is_refused_not_written(
    tmp_path: Path,
) -> None:
    batch, outcomes = _loaded(tmp_path)
    db = _db()
    db.sites[FX.SITE_A].raw_data = {M.PROVENANCE_KEY: {"lane": "W"}}
    db.sites[FX.SITE_B].description = "Someone edited this text."
    live = _live(db)
    del live[FX.SITE_C]
    plan = W4.plan_wc(batch, outcomes=outcomes, live=live)
    assert sorted((r.site_id, r.rule) for r in plan.refusals) == sorted(
        [
            (FX.SITE_A, W4.RULE_WRITTEN),
            (FX.SITE_B, W4.RULE_MOVED),
            (FX.SITE_C, W4.RULE_MOVED),
        ]
    )
    assert {row.site_id for row in plan.rows} == {UNCHANGED}


def test_an_outcome_for_another_text_than_the_plans_is_a_hole_not_a_refusal(
    tmp_path: Path,
) -> None:
    batch, outcomes = _loaded(tmp_path)
    evidence = {**outcomes[FX.SITE_A].evidence, "checked": "another text"}
    broken = {**outcomes, FX.SITE_A: WC4.WcOutcome(
        site_id=FX.SITE_A, description=outcomes[FX.SITE_A].description,
        raw_data=outcomes[FX.SITE_A].raw_data, evidence=evidence)}  # fmt: skip
    with pytest.raises(W4.PlanInputError, match="no outcome for the text it was checked with"):
        W4.plan_wc(batch, outcomes=broken, live=_live(_db()))


def _rows_of(tmp_path: Path) -> list[W4.Row4]:
    batch, outcomes = _loaded(tmp_path)
    return W4.plan_wc(batch, outcomes=outcomes, live=_live(_db())).rows


def _full_provenance() -> dict[str, Any]:
    """A lane-W provenance that parses and hashes site B's checked text (TEXT_E)."""
    provenance = PFX.assembly().provenance
    return dataclasses.replace(provenance, desc_sha256=M.text_sha256(TEXT_E)).to_dict()


def _unmarked(raw_json: str) -> str:
    """A raw_data value without its `_description_provenance`."""
    return json.dumps({k: v for k, v in json.loads(raw_json).items() if k != M.PROVENANCE_KEY})


def _remade(row: W4.Row4, **change: Any) -> W4.Row4:
    data = {**row.to_dict(), **change}
    data["change_key"] = W4.W.change_key(
        site_id=data["site_id"], table=data["table"], column=data["column"],
        old_value=data["old_value"], new_value=data["new_value"], test_id=data["test_id"],
        lane=W4.GROUP_FAMILY[W4.Group.WC],
    )  # fmt: skip
    return W4.Row4.from_dict(data)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rows: [r for r in rows if not (r.site_id == FX.SITE_A and r.column == "raw_data")],
         "site-atomic"),
        (lambda rows: [_remade(r, test_id=W4.TEST_WC_RAW_DATA_CLEAR)
                       if r.site_id == FX.SITE_A and r.column == "raw_data" else r for r in rows],
         "site-atomic"),
        (lambda rows: [_remade(r, new_value=None)
                       if r.site_id == FX.SITE_A and r.column == "raw_data" else r for r in rows],
         "only a card clear or a WC clear writes NULL"),
        (lambda rows: [_remade(r, new_value=json.dumps({**json.loads(r.new_value), "title_es": "x"}))
                       if r.site_id == FX.SITE_A and r.column == "raw_data" else r for r in rows],
         "changes keys outside"),
        (lambda rows: [_remade(r, new_value=r.new_value + " More.")
                       if r.site_id == FX.SITE_A and r.column == "description" else r for r in rows],
         "not the evidence's transition"),
        (lambda rows: [_remade(r, new_value=json.dumps({**json.loads(r.new_value),
                                                        M.PROVENANCE_KEY: {"lane": "W"}}))
                       if r.site_id == FX.SITE_B and r.column == "raw_data" else r for r in rows],
         "provenance|lane W"),
        # a full provenance that parses and hashes the very text: only the lane refuses it
        (lambda rows: [_remade(r, new_value=json.dumps({**json.loads(r.new_value),
                                                        M.PROVENANCE_KEY: _full_provenance()}))
                       if r.site_id == FX.SITE_B and r.column == "raw_data" else r for r in rows],
         "a lane-W provenance beside a checked text"),
        (lambda rows: [_remade(r, new_value=json.dumps({**json.loads(r.new_value),
                                                        M.CITATIONS_KEY: []}))
                       if r.site_id == FX.SITE_B and r.column == "raw_data" else r for r in rows],
         "disagree"),
        (lambda rows: [_remade(r, test_id=W4.TEST_CARD_CLEAR) if r.column == "description"
                       and r.site_id == FX.SITE_C else r for r in rows],
         "is not a WC row"),
        # a March text's AI footnote dropped: every invariant holds, its disclosure does not (the
        # review of 2026-09-26)
        (lambda rows: [_remade(r, new_value=_unmarked(r.new_value))
                       if r.site_id == FX.SITE_A and r.column == "raw_data" else r for r in rows],
         "AI disclosure"),
        # ... nor does an evidence that records the March text as unclaimed to excuse it
        (lambda rows: [_remade(r, new_value=_unmarked(r.new_value), evidence={
                           **r.evidence, "marking": {**r.evidence["marking"], "old": "unclaimed"}})
                       if r.site_id == FX.SITE_A and r.column == "raw_data" else r for r in rows],
         "recorded marking"),
    ],
)  # fmt: skip
def test_every_wc_plan_rule_refuses_a_broken_plan(tmp_path: Path, mutate, message) -> None:
    rows = _rows_of(tmp_path)
    W4.validate_rows(W4.Group.WC, rows)
    with pytest.raises((W4.W.WriteRefused, ValueError), match=message):
        W4.validate_rows(W4.Group.WC, mutate(rows))


def test_a_wc_plan_is_read_strictly(tmp_path: Path) -> None:
    path = _plan(tmp_path)
    (record,) = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    cases = [
        ({**record, "pass": "phase4-legacy"}, "not a lane-WC plan batch"),
        ({**record, "batch_id": "p4wc-4001"}, "is not a plan batch id"),
        ({**record, "outcomes": record["outcomes"][::-1]}, "not the batch's sites"),
    ]
    for broken, message in cases:
        path.write_text(json.dumps(broken) + "\n", encoding="utf-8")
        with pytest.raises((W4.PlanInputError, ValueError), match=message):
            W4.load_wc_plan([path])
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(W4.PlanInputError, match="twice"):
        W4.load_wc_plan([path, path])


# ------------------------------------------------------------------------------ the statement
#: The WC parts of the rendered transaction, pinned: guard 3's clear tests and invariants 5-6.
WC_SQL_PINS = {
    "null_tests": "b9ac358501af4a6f50a803ac6d8f24565c5c1ebb85d4403bfdfc4975c8048ea3",
    "invariants": "db09b168b395b04dad3bffe326511f0bb239931a5f2914b0592493e5a1b6a73d",
}


def test_the_wc_statement_lets_only_its_clears_write_null_and_checks_its_own_invariants() -> None:
    measured = {
        "null_tests": hashlib.sha256(W4._null_tests_sql(W4.Group.WC).encode()).hexdigest(),
        "invariants": hashlib.sha256("\n".join(W4._wc_invariants("wc write")).encode()).hexdigest(),
    }
    assert measured == WC_SQL_PINS
    assert W4._null_tests_sql(W4.Group.P5) == "p.test_id <> 'P5/card-clear'"


def test_a_wc_chunk_renders_its_invariants_in_place_of_invariant_3(tmp_path: Path) -> None:
    batch, outcomes = _loaded(tmp_path)
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db()))
    sql = W4.render_apply(W4.chunk_for(plan))
    assert "p.test_id NOT IN ('WC/description-clear', 'WC/raw_data-clear')" in sql
    assert "-- invariant 5 (WC)" in sql and "-- invariant 6 (WC)" in sql
    assert "-- invariant 3 (P4, L)" not in sql
    assert "run stamp 'phase4wc:p4wc-4001:chunk-0001'" in sql


def test_a_wc_chunk_is_written_read_back_and_its_inverse_proven(tmp_path: Path) -> None:
    batch, outcomes = _loaded(tmp_path)
    db = _db()
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(db))
    chunk = W4.chunk_for(plan)
    out = tmp_path / "apply" / plan.batch_id
    W4.write_plan_files(out, plan, chunk)
    rehearsed = W4.apply_chunk(chunk, out=out, rehearse=True, runner=db)
    assert rehearsed.ok and db.sites[FX.SITE_A].description == FX.TEXT_A and not db.journal
    outcome = W4.apply_chunk(chunk, out=out, rehearse=False, runner=db)
    assert outcome.ok and outcome.written == len(plan.rows)
    for site_id, result in outcomes.items():
        site = db.sites[site_id]
        assert (site.description, site.raw_data) == (result.description, result.raw_data)
        assert WC4.wc_problems(site.description, site.raw_data) == []
    assert {entry["run_stamp"] for entry in db.journal} == {"phase4wc:p4wc-4001:chunk-0001"}


def test_the_read_back_holds_a_wc_site_to_the_lanes_invariants(tmp_path: Path) -> None:
    rows = _rows_of(tmp_path)
    by_site = [row for row in rows if row.site_id == FX.SITE_A]
    stored = {
        "id": FX.SITE_A,
        "description": by_site[0].new_value,
        "raw_data": json.loads(by_site[1].new_value),
    }
    assert W4.invariant_problems(stored, by_site) == []
    stored["description"] += " Edited."
    assert any("desc_sha256" in p for p in W4.invariant_problems(stored, by_site))


# ------------------------------------------------------------------------------ the gate
def _args(tmp_path: Path, plan: Path, *extra: str) -> list[str]:
    return ["--group", "WC", "--wc-plan", str(plan), "--apply-root", str(tmp_path / "apply"),
            *extra]  # fmt: skip


def _production(db: PFX.FakeDb, lane_plan: Path) -> FakeProduction:
    """What production holds after the fake psql's writes, as the acceptance reads it: the
    journal with each row's evidence (from the lane plan the rows were written from)."""
    evidence = {row["change_key"]: row["evidence"] for row in lanes.read_jsonl(lane_plan)}
    journal = [
        {**{k: entry[k] for k in ("id", "table_name", "column_name", "row_pk", "old_value",
                                  "new_value", "run_stamp", "change_key")},
         "evidence": evidence.get(entry["change_key"].removesuffix("-rollback"))}
        for entry in db.journal
    ]  # fmt: skip
    return FakeProduction(
        journal=journal,
        sites={
            site_id: {
                "description": site.description,
                "raw_data": site.raw_data,
                "card_description": site.card,
                "has_card_row": site.card_row,
            }
            for site_id, site in db.sites.items()
        },
    )


def _accept_output(tmp_path, capsys, monkeypatch, production: FakeProduction) -> str:
    monkeypatch.setattr(A.lanes, "psql", lambda sql, host: production(sql))
    lane_plan = tmp_path / "apply" / G.LANE_PLAN_FILE
    code = A.main(["--lane", "p4wc", "--plan", str(lane_plan)])
    out = capsys.readouterr().out
    assert out.strip().endswith(f"ACCEPT_EXIT={code}")
    return out


def test_wc_is_planned_written_in_a_step_and_accepted_on_its_own_lane(
    tmp_path, capsys, monkeypatch
) -> None:
    plan = _plan(tmp_path)
    db = _db()
    assert G.main(_args(tmp_path, plan), runner=db) == 0
    out = capsys.readouterr().out
    assert G.WC_UNSCOPED in out and "live description and raw_data: 4 of 4" in out
    assert "rows planned: 7 | refused by rule: {}" in out and "dry run, nothing is sent" in out
    assert G.main(_args(tmp_path, plan, "--rehearse"), runner=db) == 0
    assert not db.journal and db.sites[FX.SITE_A].description == FX.TEXT_A
    assert G.main(_args(tmp_path, plan, "--apply", "--step", "100"), runner=db) == 0
    out = capsys.readouterr().out
    assert "STEP COMPLETE: 4 site(s) written in 1 batch(es)" in out
    assert f"{G.VERIFY_TOOL} --lane p4wc --plan" in out and "--run" not in out.split("STEP")[-1]
    step = json.loads((tmp_path / "apply" / G.STEP_FILE).read_text(encoding="utf-8"))
    assert (step["lane"], step["stamps"]) == ("p4wc", ["phase4wc:p4wc-4001:chunk-0001"])
    assert db.sites[FX.SITE_C].description is None and db.sites[FX.SITE_C].raw_data is None

    lane_plan = tmp_path / "apply" / G.LANE_PLAN_FILE
    output = _accept_output(tmp_path, capsys, monkeypatch, _production(db, lane_plan))
    assert "RESULT: 0 deviation(s)" in output
    assert "re-checked 4 written site(s) against their journal evidence" in output
    log = tmp_path / "accept-1.log"
    log.write_text(output, encoding="utf-8")
    assert G.main(["--group", "WC", "--apply-root", str(tmp_path / "apply"),
                   "--accept", str(log)], runner=db) == 0  # fmt: skip
    assert "ACCEPTED step 1" in capsys.readouterr().out
    assert G.main(_args(tmp_path, plan, "--apply"), runner=db) == 0
    assert "done: no open batch left to write" in capsys.readouterr().out


def test_the_acceptance_refuses_a_text_that_is_not_what_the_evidence_composes(
    tmp_path, capsys, monkeypatch
) -> None:
    plan = _plan(tmp_path)
    db = _db()
    assert G.main(_args(tmp_path, plan, "--apply"), runner=db) == 0
    capsys.readouterr()
    production = _production(db, tmp_path / "apply" / G.LANE_PLAN_FILE)
    for entry in production.journal:
        if entry["row_pk"] == FX.SITE_A:
            sentences = entry["evidence"]["sentences"]
            entry["evidence"] = {
                **entry["evidence"],
                "sentences": [
                    {**sentences[0], "sentence": "The Tarxien Temples are in Gozo."},
                    *sentences[1:],
                ],
            }
    output = _accept_output(tmp_path, capsys, monkeypatch, production)
    assert f"EVIDENCE {FX.SITE_A}: the description is not what the journal evidence composes" in (
        output
    )  # fmt: skip
    assert "ACCEPT_EXIT=1" in output


def test_the_acceptance_holds_a_written_site_to_the_wc_invariants(tmp_path, monkeypatch) -> None:
    plan = _plan(tmp_path)
    db = _db()
    assert G.main(_args(tmp_path, plan, "--apply"), runner=db) == 0
    production = _production(db, tmp_path / "apply" / G.LANE_PLAN_FILE)
    rows = production.sites
    rows[FX.SITE_B]["raw_data"] = {**rows[FX.SITE_B]["raw_data"], M.CITATIONS_KEY: []}
    read = A.read_production(
        sorted(rows), stamp_like="phase4wc:%", columns=A.LANE_COLUMNS["p4wc"], run=production
    )
    carried = {("unified_sites", "raw_data", site) for site in rows}
    found = A.invariant_deviations(lane="p4wc", carried=carried, production=read)
    assert any(f"INVARIANT {FX.SITE_B}" in line and "disagree" in line for line in found)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--group", "WC", "--run", "pilot"], "lane WC plans from its own plans"),
        (["--group", "WC"], "--wc-plan: lane WC plans from"),
        (["--group", "L", "--wc-plan", "x"], "only lane WC plans from it"),
    ],
)
def test_wc_plans_from_its_own_plans_only(tmp_path, capsys, args, message) -> None:
    assert G.main([*args, "--apply-root", str(tmp_path / "apply")], runner=_db()) == 1
    assert message in capsys.readouterr().err


def test_wc_refuses_an_apply_root_holding_batches_of_a_plan_not_named(tmp_path, capsys) -> None:
    plan = _plan(tmp_path)
    (tmp_path / "apply" / "p4wc-4999").mkdir(parents=True)
    assert G.main(_args(tmp_path, plan), runner=_db()) == 1
    err = capsys.readouterr().err
    assert "['p4wc-4999']" in err and "not named here" in err


def test_a_site_that_moved_is_refused_at_the_plan_and_the_rest_is_written(tmp_path, capsys) -> None:
    plan = _plan(tmp_path)
    db = _db()
    db.sites[FX.SITE_B].description = "Edited since the check."
    assert G.main(_args(tmp_path, plan, "--apply"), runner=db) == 0
    out = capsys.readouterr().out
    assert "refused by rule: {'moved-since-check': 1}" in out
    assert db.sites[FX.SITE_B].description == "Edited since the check."
    assert db.sites[FX.SITE_C].description is None


# ------------------------------------------------------------------------------ the registry
def test_the_wc_lane_is_registered_from_the_writers_own_table() -> None:
    lane = lanes.lane("p4wc")
    assert (lane.family, lane.stamp_like) == ("phase4wc", "phase4wc:p4wc-%")
    assert lane.apply_root.name == "_write_apply_p4wc"
    assert R.check_pattern("phase4wc:%") == "phase4wc:%"
    assert "phase4wc:" in R.FAMILIES


# ------------------------------------------------------------------------------ the way back
def test_revert4_takes_a_written_wc_chunk_back_the_cleared_site_included(tmp_path: Path) -> None:
    """The undo of a WC step is `revert4.py --stamp-like 'phase4wc:...'` (or `--site <id>` for one
    site): its set query takes exactly the step's journalled rows, and the reversal it journals puts
    every site back to the text and raw_data it was checked with - a cleared site's NULLs too."""
    batch, outcomes = _loaded(tmp_path)
    db = _db()
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(db))
    chunk = W4.chunk_for(plan)
    out = tmp_path / "apply" / plan.batch_id
    W4.write_plan_files(out, plan, chunk)
    assert W4.apply_chunk(chunk, out=out, rehearse=False, runner=db).ok
    assert db.sites[FX.SITE_C].description is None and db.sites[FX.SITE_C].raw_data is None
    journal = list(db.journal)
    assert _revert_set(R.render_revert("phase4wc:%"), journal) == [e["id"] for e in journal]
    of_c = [e["id"] for e in journal if e["site_id_ref"] == FX.SITE_C]
    assert len(of_c) == 2
    assert _revert_set(R.render_revert(chunk.stamp, site=FX.SITE_C), journal) == of_c
    _keep_reversal(db, chunk)
    for row in _rows():
        site = db.sites[row["id"]]
        assert (site.description, site.raw_data) == (row["description"], row["raw_data"])
    assert _revert_set(R.render_revert("phase4wc:%"), db.journal) == []
