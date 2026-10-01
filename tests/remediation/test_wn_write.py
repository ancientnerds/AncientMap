"""Lane WN's write (owner decision "Neu aus Webquellen", 2026-10-01): a description written for a
site that had none reaches production through the same journalled WC writer group - the premise is an
empty old value, NULL or blank, which the plan, the transaction's guards, the read-back, the
acceptance and the way back must all hold explicitly.

`phase4/write4.py` (`plan_wc` with an empty old value, `load_wc_plan`, invariant 6's lane by the
recorded marking), `output/remediation/tools/write_gate4.py --group WC`, `verify_writes4.py --lane
p4wc` and `revert4.py`. The fake psql parses what it is sent (`phase4_write_fixtures.FakeDb`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import verify_writes4 as A  # noqa: E402
import write_gate4 as G  # noqa: E402
from phase4 import revert4 as R  # noqa: E402

from tests.remediation import phase4_write_fixtures as PFX  # noqa: E402
from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation import wn_fixtures as WX  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4, M  # noqa: E402
from tests.remediation.test_phase4_accept import FakeProduction  # noqa: E402
from tests.remediation.test_phase4_wc_write import (  # noqa: E402
    _accept_output,
    _production,
    _remade,
)
from tests.remediation.test_phase4_write import _keep_reversal, _revert_set  # noqa: E402
from tests.remediation.wc_fixtures import WC4  # noqa: E402


def _rows() -> list[dict[str, Any]]:
    """N (NULL description, NULL raw_data), BLANK (a blank description and a raw_data of its own),
    EMPTY (the agent found nothing: never written), BAD (one written sentence lost its quote)."""
    return [
        WX.wn_row(WX.SITE_N),
        WX.wn_row(WX.SITE_BLANK, "  ", raw_data={"title_es": "Templos"}),
        WX.wn_row(WX.SITE_EMPTY),
        WX.wn_row(WX.SITE_BAD),
    ]


def _answers() -> dict[str, str]:
    q_nowhere = FX.quote(
        FX.WIKI, "The temples were raised by a lost people in a later age of giants."
    )
    return {
        WX.SITE_N: WX.good(WX.SITE_N),
        WX.SITE_BLANK: WX.good(WX.SITE_BLANK),
        WX.SITE_EMPTY: WX.nothing(WX.SITE_EMPTY),
        WX.SITE_BAD: WX.written(
            WX.SITE_BAD,
            WX.sentence(WX.W1, WX.Q_W1),
            WX.sentence(WX.W2, WX.Q_W2),
            WX.sentence("The monuments were raised by a lost people in a later age.", q_nowhere),
        ),
    }


@pytest.fixture(scope="module")
def plan_path(tmp_path_factory) -> Path:
    return WX.build_wn_run(tmp_path_factory.mktemp("wnw"), _rows(), _answers(), name="wn-pilot")[1]


def _db(rows=None) -> PFX.FakeDb:
    return PFX.FakeDb(
        {
            row["id"]: PFX.Site(description=row["description"], raw_data=row["raw_data"])
            for row in (rows or _rows())
        }
    )


def _live(db: PFX.FakeDb) -> dict[str, dict[str, Any]]:
    return {
        site_id: {"description": site.description, "raw_data": site.raw_data}
        for site_id, site in db.sites.items()
    }


def _loaded(path: Path):
    batches, outcomes = W4.load_wc_plan([path])
    (batch,) = batches
    return batch, outcomes


# ------------------------------------------------------------------------------ the plan
def test_a_written_description_is_planned_over_an_empty_old_value(plan_path: Path) -> None:
    batch, outcomes = _loaded(plan_path)
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db()))
    assert not plan.refusals
    rows = {(row.site_id, row.column): row for row in plan.rows}
    assert {site for site, _ in rows} == {WX.SITE_N, WX.SITE_BLANK, WX.SITE_BAD}
    n_description, n_raw = rows[(WX.SITE_N, "description")], rows[(WX.SITE_N, "raw_data")]
    assert (n_description.old_value, n_raw.old_value) == (None, None)
    assert (n_description.test_id, n_raw.test_id) == (W4.TEST_WC_DESCRIPTION, W4.TEST_WC_RAW_DATA)
    assert n_description.new_value == outcomes[batch.batch_id][WX.SITE_N].description
    blank = rows[(WX.SITE_BLANK, "description")]
    assert blank.old_value == "  " and blank.new_value is not None
    blank_raw = json.loads(rows[(WX.SITE_BLANK, "raw_data")].new_value)
    assert blank_raw["title_es"] == "Templos"  # every key outside WC's three stays
    assert blank_raw[M.PROVENANCE_KEY]["lane"] == "N"
    assert n_description.evidence["marking"]["old"] == "none"
    assert n_description.evidence["checked"] is None and blank.evidence["checked"] == "  "


def test_a_site_that_got_a_description_since_its_write_round_is_never_overwritten(
    plan_path: Path,
) -> None:
    """The premise of lane WN is an empty site: a text that arrived since (a WC write, a hand edit)
    makes the pair `moved-since-check`, refused before anything is rendered; so does a raw_data that
    moved, and a site that vanished."""
    batch, outcomes = _loaded(plan_path)
    db = _db()
    db.sites[WX.SITE_N].description = "A text somebody wrote meanwhile."
    db.sites[WX.SITE_BLANK].raw_data = {"title_es": "Templos", "title_mt": "Tempji"}
    live = _live(db)
    del live[WX.SITE_BAD]
    plan = W4.plan_wc(batch, outcomes=outcomes, live=live)
    assert sorted((r.site_id, r.rule) for r in plan.refusals) == sorted(
        [(s, W4.RULE_MOVED) for s in (WX.SITE_N, WX.SITE_BLANK, WX.SITE_BAD)]
    )
    assert not plan.rows


def test_blank_and_null_are_two_old_values_and_the_plan_holds_the_one_it_was_asked_with(
    plan_path: Path,
) -> None:
    """NULL and a blank string are not the same stored value: the evidence's `checked` and the row's
    old value are what the read found, and a site read as NULL that now holds a blank string (or
    the other way round) is no longer the checked pair."""
    batch, outcomes = _loaded(plan_path)
    db = _db()
    db.sites[WX.SITE_N].description = "  "
    db.sites[WX.SITE_BLANK].description = None
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(db))
    assert sorted(r.site_id for r in plan.refusals) == sorted([WX.SITE_N, WX.SITE_BLANK])
    assert {row.site_id for row in plan.rows} == {WX.SITE_BAD}


def test_the_plan_loader_refuses_an_outcome_that_leaves_a_wn_site_empty(
    plan_path: Path, tmp_path: Path
) -> None:
    """Lane WN writes only the sites that got a text: an empty outcome is no write (NULL over NULL
    is no change), and a plan that carries one is refused whole."""
    (record,) = [json.loads(line) for line in plan_path.read_text(encoding="utf-8").splitlines()]
    cleared = json.loads(json.dumps(record))
    cleared["outcomes"][0]["description"] = None
    cleared["outcomes"][0]["evidence"]["description"] = None
    cleared["outcomes"][0]["raw_data"] = None
    path = tmp_path / "WC4.jsonl"
    path.write_text(json.dumps(cleared) + "\n", encoding="utf-8")
    with pytest.raises(W4.PlanInputError, match="had no description and has none"):
        W4.load_wc_plan([path])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        # lane L's provenance on a text lane WN wrote, hashing the very text
        (lambda r, raw: {**raw, M.PROVENANCE_KEY: M.LegacyProvenance(
            desc_sha256=M.text_sha256(r.new_value)).to_dict()}, "lane-L provenance|AI disclosure"),
        # no provenance at all: the AI mark is required, not only checked where present
        (lambda r, raw: {k: v for k, v in raw.items() if k != M.PROVENANCE_KEY}, "AI disclosure"),
        # lane N's provenance of another text
        (lambda r, raw: {**raw, M.PROVENANCE_KEY: M.WebProvenance(desc_sha256="a" * 64).to_dict()},
         "provenance's desc_sha256|AI disclosure"),
    ],
)  # fmt: skip
def test_the_plan_requires_lane_ns_provenance_on_every_written_wn_text(
    plan_path: Path, mutate, message: str
) -> None:
    batch, outcomes = _loaded(plan_path)
    rows = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db())).rows
    W4.validate_rows(W4.Group.WC, rows)
    description = next(r for r in rows if r.site_id == WX.SITE_N and r.column == "description")
    broken = [
        _remade(r, new_value=json.dumps(mutate(description, json.loads(r.new_value))))
        if r.site_id == WX.SITE_N and r.column == "raw_data"
        else r
        for r in rows
    ]
    with pytest.raises((W4.W.WriteRefused, ValueError), match=message):
        W4.validate_rows(W4.Group.WC, broken)


def test_the_plan_refuses_an_evidence_that_records_another_marking_than_the_pair_carries(
    plan_path: Path,
) -> None:
    """A site with no description is `none`; recorded as a March text it would escape the lane-N
    provenance it needs (and claim a March origin nothing proves)."""
    batch, outcomes = _loaded(plan_path)
    rows = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db())).rows
    edited = [
        _remade(r, evidence={**r.evidence, "marking": {**r.evidence["marking"], "old": "L"}})
        if r.site_id == WX.SITE_N
        else r
        for r in rows
    ]
    with pytest.raises(W4.W.WriteRefused, match="recorded marking"):
        W4.validate_rows(W4.Group.WC, edited)


# ------------------------------------------------------------------------------ the statement
def test_the_wn_chunk_renders_guard_4_for_a_null_and_a_blank_old_value(plan_path: Path) -> None:
    batch, outcomes = _loaded(plan_path)
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db()))
    sql = W4.render_apply(W4.chunk_for(plan))
    assert "IS DISTINCT FROM" in sql and "unlike `=`, it is true for a NULL old value" in sql
    assert (
        f"'{WX.SITE_N}'::uuid, 'unified_sites', 'description', 'id', '{WX.SITE_N}', NULL, '" in sql
    )
    assert (
        f"'{WX.SITE_BLANK}'::uuid, 'unified_sites', 'description', 'id', '{WX.SITE_BLANK}', '  ', '"
        in sql
    )
    assert "WHEN 'none' THEN 'N' WHEN 'web' THEN 'N'" in sql
    assert "p.old_value::jsonb" in sql and "-- invariant 6 (WC)" in sql


def test_the_transaction_holds_the_lane_the_marking_calls_for(plan_path: Path) -> None:
    """Invariant 6 inside the transaction: a lane-WN text carries lane N's provenance. The plan
    refuses a wrong one first; here the rendered statement is edited after its rendering."""
    batch, outcomes = _loaded(plan_path)
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db()))
    sql = W4.render_apply(W4.chunk_for(plan), rehearse=True)
    db = _db()
    assert db(sql, host="test") == "NOTICE\n"  # the rehearsal, rolled back
    assert db.sites[WX.SITE_N].description is None and not db.journal
    as_march = sql.replace('"lane": "N"', '"lane": "L"')
    assert as_march != sql
    with pytest.raises(PFX.PsqlError, match="invariant 6"):
        db(as_march, host="test")
    assert db.sites[WX.SITE_N].description is None and not db.journal


# ------------------------------------------------------------------------------ the gate
def _args(tmp_path: Path, plan: Path, *extra: str) -> list[str]:
    return ["--group", "WC", "--wc-plan", str(plan), "--apply-root", str(tmp_path / "apply"),
            *extra]  # fmt: skip


def test_a_wn_plan_is_planned_written_in_a_step_accepted_and_taken_back(
    plan_path: Path, tmp_path, capsys, monkeypatch
) -> None:
    db = _db()
    assert G.main(_args(tmp_path, plan_path), runner=db) == 0
    out = capsys.readouterr().out
    assert "live description and raw_data: 3 of 3" in out and "pilot passed: " in out
    assert "rows planned: 6 | refused by rule: {}" in out
    assert G.main(_args(tmp_path, plan_path, "--rehearse"), runner=db) == 0
    assert not db.journal and db.sites[WX.SITE_N].description is None
    assert G.main(_args(tmp_path, plan_path, "--apply", "--step", "100"), runner=db) == 0
    assert "STEP COMPLETE: 3 site(s) written in 1 batch(es)" in capsys.readouterr().out
    written = {sid: db.sites[sid] for sid in (WX.SITE_N, WX.SITE_BLANK, WX.SITE_BAD)}
    assert all(site.description for site in written.values())
    assert db.sites[WX.SITE_EMPTY].description is None  # the agent found nothing: nothing written
    for site in written.values():
        assert WC4.wc_problems(site.description, site.raw_data, marking="none") == []
        assert site.raw_data[M.PROVENANCE_KEY]["lane"] == "N"
    assert db.sites[WX.SITE_BLANK].raw_data["title_es"] == "Templos"

    lane_plan = tmp_path / "apply" / G.LANE_PLAN_FILE
    production = _production(db, lane_plan)
    output = _accept_output(tmp_path, capsys, monkeypatch, production)
    assert "RESULT: 0 deviation(s)" in output
    assert "re-checked 3 written site(s) against their journal evidence" in output

    # the acceptance holds each written text to lane N's provenance by its recorded marking
    production.sites[WX.SITE_N]["raw_data"] = {
        **production.sites[WX.SITE_N]["raw_data"],
        M.PROVENANCE_KEY: M.LegacyProvenance(
            desc_sha256=M.text_sha256(production.sites[WX.SITE_N]["description"])
        ).to_dict(),
    }
    refused = _accept_output(tmp_path, capsys, monkeypatch, production)
    assert f"INVARIANT {WX.SITE_N}: a lane-L provenance beside a checked text" in refused
    assert f"EVIDENCE {WX.SITE_N}: the AI disclosure is not the WebProvenance" in refused
    assert "ACCEPT_EXIT=1" in refused


def test_revert4_takes_a_written_wn_chunk_back_to_the_empty_old_values(
    plan_path: Path, tmp_path
) -> None:
    """The undo is the journal: the reversal writes NULL (and the blank string) back, byte for
    byte - the descriptions leave again, the raw_data of the blank site is what it was."""
    batch, outcomes = _loaded(plan_path)
    db = _db()
    plan = W4.plan_wc(batch, outcomes=outcomes, live=_live(db))
    chunk = W4.chunk_for(plan)
    out = tmp_path / "apply" / plan.batch_id
    W4.write_plan_files(out, plan, chunk)
    assert W4.apply_chunk(chunk, out=out, rehearse=False, runner=db).ok
    journal = list(db.journal)
    assert _revert_set(R.render_revert("phase4wc:%"), journal) == [e["id"] for e in journal]
    one = [e["id"] for e in journal if e["site_id_ref"] == WX.SITE_N]
    assert (
        len(one) == 2 and _revert_set(R.render_revert(chunk.stamp, site=WX.SITE_N), journal) == one
    )
    _keep_reversal(db, chunk)
    for row in _rows():
        site = db.sites[row["id"]]
        assert (site.description, site.raw_data) == (row["description"], row["raw_data"])
    assert db.sites[WX.SITE_N].description is None and db.sites[WX.SITE_BLANK].description == "  "


def test_the_read_back_holds_a_wn_site_to_lane_ns_invariants(plan_path: Path) -> None:
    batch, outcomes = _loaded(plan_path)
    rows = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db())).rows
    of_n = [row for row in rows if row.site_id == WX.SITE_N]
    stored = {
        "id": WX.SITE_N,
        "description": next(r for r in of_n if r.column == "description").new_value,
        "raw_data": json.loads(next(r for r in of_n if r.column == "raw_data").new_value),
    }
    assert W4.invariant_problems(stored, of_n) == []
    stored["raw_data"][M.PROVENANCE_KEY] = M.LegacyProvenance(
        desc_sha256=M.text_sha256(stored["description"])
    ).to_dict()
    assert any("lane-L provenance" in p for p in W4.invariant_problems(stored, of_n))


def test_the_acceptance_markings_come_from_the_last_wc_evidence_of_each_site() -> None:
    rows = [
        {"id": 1, "row_pk": "a", "evidence": {"marking": {"old": "L"}}},
        {"id": 5, "row_pk": "a", "evidence": {"marking": {"old": "none"}}},
        {"id": 3, "row_pk": "b", "evidence": {"marking": {"old": "phase4"}}},
    ]
    assert A.wc_markings(rows) == {"a": "none", "b": "phase4"}
    assert A.wc_markings([]) == {}


def test_the_production_double_is_the_one_the_existing_wc_tests_use() -> None:
    assert FakeProduction is not None  # the acceptance's read-only production seam
