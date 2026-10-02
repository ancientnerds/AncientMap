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
import os
import subprocess
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


def _git(repo: Path, *argv: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *argv],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return done.stdout.strip()


@pytest.fixture(scope="module")
def _own_git_environment():
    """The pre-push hook runs the suite with GIT_DIR (and friends) exported; `git -C <throwaway>`
    then still acts on the pushed repository and the three commits below land in the real
    branch. Without these variables every git call here, the gate's included, uses `-C`."""
    patch = pytest.MonkeyPatch()
    for name in [n for n in os.environ if n.startswith("GIT_")]:
        patch.delenv(name)
    yield
    patch.undo()


@pytest.fixture(scope="module")
def lane_n_history(tmp_path_factory, _own_git_environment) -> dict[str, str]:
    """A throwaway repository with the three commits the gate reasons about: one before the change
    that puts lane N into the API's disclosure, the change, and one after. (The checkout the suite
    runs in may be shallow: CI clones with depth 1.)"""
    repo = tmp_path_factory.mktemp("history")
    _git(repo, "init", "-q")
    target = repo / G.LANE_N_FILE
    target.parent.mkdir(parents=True)
    commits = {}
    for name, text in (
        ("before", "LICENCE_LESS = frozenset({'L'})"),
        ("change", f"{G.LANE_N_MARK} = frozenset({{'L', 'N'}})"),
        ("after", f"{G.LANE_N_MARK} = frozenset({{'L', 'N'}})  # later edit"),
    ):
        target.write_text(text + chr(10), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", name)
        commits[name] = _git(repo, "rev-parse", "HEAD")
    return {"repo": str(repo), **commits}


@pytest.fixture(autouse=True)
def _history_of_the_gate(lane_n_history, monkeypatch) -> None:
    monkeypatch.setattr(G, "LANE_N_REPO", Path(lane_n_history["repo"]))


def _api_runs_the_lane_n_change(host: str) -> str:
    """The live API reports (`/` -> commit) a commit after the lane-N change."""
    return _git(Path(G.LANE_N_REPO), "rev-parse", "HEAD")


def _gate(argv, *, runner):
    """The gate with the API check answered as a deployed API would answer it: the real read is an
    ssh to the VPS."""
    return G.main(argv, runner=runner, api_commit=_api_runs_the_lane_n_change)


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
    assert _gate(_args(tmp_path, plan_path), runner=db) == 0
    out = capsys.readouterr().out
    assert "live description and raw_data: 3 of 3" in out and "pilot passed: " in out
    assert "rows planned: 6 | refused by rule: {}" in out
    assert _gate(_args(tmp_path, plan_path, "--rehearse"), runner=db) == 0
    assert not db.journal and db.sites[WX.SITE_N].description is None
    assert _gate(_args(tmp_path, plan_path, "--apply", "--step", "100"), runner=db) == 0
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


# ------------------------------------------------------------- one cell, two plans of the lane
def _cleared_then_written(tmp_path: Path, capsys, monkeypatch):
    """The WC pilot clears site C (its old text was dropped); the WN pilot, read afterwards, writes a
    text for it: the description and raw_data cells of C are written by two plans of lane WC."""
    from tests.remediation.test_phase4_wc_write import _answers as wc_answers
    from tests.remediation.test_phase4_wc_write import _db as wc_db
    from tests.remediation.test_phase4_wc_write import _rows as wc_rows

    wc_plan = FX.build_run(tmp_path / "wc", wc_rows(), wc_answers(), name="wc-pilot")[1]
    db = wc_db()
    base = ["--group", "WC", "--apply-root", str(tmp_path / "apply")]
    assert _gate([*base, "--wc-plan", str(wc_plan), "--apply", "--step", "100"], runner=db) == 0
    assert db.sites[FX.SITE_C].description is None and db.sites[FX.SITE_C].raw_data is None
    capsys.readouterr()
    accepted = _accept_output(
        tmp_path, capsys, monkeypatch, _production(db, tmp_path / "apply" / G.LANE_PLAN_FILE)
    )
    assert "RESULT: 0 deviation(s)" in accepted
    log = tmp_path / "accept-wc.log"
    log.write_text(accepted, encoding="utf-8")
    assert _gate([*base, "--accept", str(log)], runner=db) == 0
    after = [
        FX.row(sid, site.description, raw_data=site.raw_data, name=sid[:4])
        for sid, site in db.sites.items()
    ]
    wn_plan = WX.build_wn_run(
        tmp_path / "wn",
        after,
        {FX.SITE_C: WX.good(FX.SITE_C)},
        name="wn-pilot",
        first_batch=WC4.FIRST_BATCH + 1,
    )[1]
    return db, [*base, "--wc-plan", str(wc_plan), "--wc-plan", str(wn_plan)]


def test_a_wn_text_is_written_over_a_site_an_earlier_wc_plan_cleared(
    tmp_path, capsys, monkeypatch
) -> None:
    """The first WN writes hit this: the gate must plan the earlier clear (re-planned from what it
    was written from) and the new text as two chained rows per cell, write only the new one, and the
    lane's acceptance must chain them: a clear, then a text, 0 deviations - and still 0 once the
    new text is taken back."""
    db, args = _cleared_then_written(tmp_path, capsys, monkeypatch)
    capsys.readouterr()
    assert _gate(args, runner=db) == 0
    assert "pilot passed: " in capsys.readouterr().out
    assert _gate([*args, "--apply", "--step", "100"], runner=db) == 0
    out = capsys.readouterr().out
    assert "STEP COMPLETE: 1 site(s) written in 1 batch(es)" in out
    site = db.sites[FX.SITE_C]
    assert site.description and site.raw_data[M.PROVENANCE_KEY]["lane"] == "N"
    stamps = {(e["run_stamp"], e["column_name"]) for e in db.journal if e["row_pk"] == FX.SITE_C}
    assert len({stamp for stamp, _ in stamps}) == 2  # the clear's chunk and the WN chunk

    lane_plan = tmp_path / "apply" / G.LANE_PLAN_FILE
    rows = [r for r in lanes.read_jsonl(lane_plan) if r["site_id"] == FX.SITE_C]
    assert [r["column"] for r in rows].count("description") == 2  # two planned rows, one cell
    production = _production(db, lane_plan)
    output = _accept_output(tmp_path, capsys, monkeypatch, production, "--complete")
    assert "RESULT: 0 deviation(s)" in output
    assert "re-checked 4 written site(s) against their journal evidence" in output


def test_the_acceptance_of_a_chained_cell_still_counts_every_deviation(
    tmp_path, capsys, monkeypatch
) -> None:
    """A chain is no licence: a third write, a write between the two, a text another stamp changed
    after the lane, a reverted second write and two chunks claiming one text each stay what they
    were."""
    db, args = _cleared_then_written(tmp_path, capsys, monkeypatch)
    assert _gate([*args, "--apply", "--step", "100"], runner=db) == 0
    capsys.readouterr()
    lane_plan = tmp_path / "apply" / G.LANE_PLAN_FILE
    cell = ("unified_sites", "description", FX.SITE_C)

    def result(production, **extra):
        plan = lanes.read_jsonl(lane_plan)
        read = A.read_production(
            sorted({r["pk"] for r in plan}),
            stamp_like="phase4wc:%",
            columns=A.LANE_COLUMNS["p4wc"],
            run=production,
        )
        return A.accept4(
            planned=plan, lane_links=read.lane_links, chains=read.chains, live=read.live,
            present=read.present, columns=A.LANE_COLUMNS["p4wc"], complete=False,
            change_keys=read.change_keys, allowed=extra.get("allowed", ()),
        )  # fmt: skip

    base = _production(db, lane_plan)
    clean = result(base)
    assert clean.deviations == [] and cell in clean.carried
    assert len(clean.open_ids) == 9  # the WC pilot's 7 rows and the WN chunk's 2

    # another stamp wrote the text after the lane
    later = _production(db, lane_plan)
    last = max(
        (e for e in later.journal if e["column_name"] == "description"), key=lambda e: e["id"]
    )
    later.journal.append(
        {**last, "id": last["id"] + 1, "run_stamp": "other:1", "old_value": last["new_value"],
         "new_value": "Edited.", "change_key": "x"}
    )  # fmt: skip
    later.sites[FX.SITE_C]["description"] = "Edited."
    assert any(d.startswith("CHANGED LATER") for d in result(later).deviations)

    # a foreign write between the clear and the text: the chain is broken, not the lane's own
    between = _production(db, lane_plan)
    wn = [
        e for e in between.journal if e["row_pk"] == FX.SITE_C and ":p4wc-4002:" in e["run_stamp"]
    ]
    desc = next(e for e in wn if e["column_name"] == "description")
    at = desc["id"]
    for entry in between.journal:
        if entry["id"] >= at:
            entry["id"] += 1
    between.journal.append(
        {**desc, "id": at, "run_stamp": "other:2", "old_value": None, "new_value": "x",
         "change_key": "y"},
    )  # fmt: skip
    deviations = result(between).deviations
    assert any(d.startswith("CHANGED LATER") and "wrote between" in d for d in deviations)
    assert any(d.startswith("BROKEN CHAIN") for d in deviations)

    # the WN chunk not written (yet): the clear stands, the text is a later step - and a deviation
    # once the acceptance is --complete
    waiting = _production(db, lane_plan)
    waiting.journal = [e for e in waiting.journal if ":p4wc-4002:" not in e["run_stamp"]]
    waiting.sites[FX.SITE_C].update(description=None, raw_data=None)
    partial = result(waiting)
    assert partial.deviations == [] and partial.untouched == 2
    plan = lanes.read_jsonl(lane_plan)
    read = A.read_production(
        sorted({r["pk"] for r in plan}), stamp_like="phase4wc:%",
        columns=A.LANE_COLUMNS["p4wc"], run=waiting,
    )  # fmt: skip
    complete = A.accept4(
        planned=plan, lane_links=read.lane_links, chains=read.chains, live=read.live,
        present=read.present, columns=A.LANE_COLUMNS["p4wc"], complete=True,
        change_keys=read.change_keys, allowed=(),
    )  # fmt: skip
    assert sum(d.startswith("NOT WRITTEN") for d in complete.deviations) == 2

    # two chunks claiming one text (rows that do not chain) are still PLANNED TWICE
    twice = [dict(r) for r in plan]
    clear = next(r for r in plan if r["site_id"] == FX.SITE_C and r["column"] == "description")
    twice.append(dict(clear, change_key="z"))
    read = A.read_production(
        sorted({r["pk"] for r in twice}), stamp_like="phase4wc:%",
        columns=A.LANE_COLUMNS["p4wc"], run=base,
    )  # fmt: skip
    again = A.accept4(
        planned=twice, lane_links=read.lane_links, chains=read.chains, live=read.live,
        present=read.present, columns=A.LANE_COLUMNS["p4wc"], complete=False,
        change_keys=read.change_keys, allowed=(),
    )  # fmt: skip
    assert any(d.startswith("PLANNED TWICE") for d in again.deviations)


def test_taking_the_wn_text_back_leaves_the_clear_standing_and_the_acceptance_clean(
    tmp_path, capsys, monkeypatch
) -> None:
    """The way back of the second write of a cell: the reversal restores the cleared state, the
    clear's evidence is what the site is checked against, and the reverted chunk's rows are a plan
    not yet written - not a deviation, and a deviation once the acceptance is --complete."""
    db, args = _cleared_then_written(tmp_path, capsys, monkeypatch)
    assert _gate([*args, "--apply", "--step", "100"], runner=db) == 0
    capsys.readouterr()
    paths = [Path(args[i + 1]) for i, arg in enumerate(args) if arg == "--wc-plan"]
    batches, outcomes = W4.load_wc_plan(paths)
    later = batches[1]
    plan = W4.plan_wc(later, outcomes=outcomes, live=_live(db))
    chunk = W4.chunk_for(plan)
    assert chunk is not None and chunk.stamp == "phase4wc:p4wc-4002:chunk-0001"
    _keep_reversal(db, chunk)
    assert db.sites[FX.SITE_C].description is None and db.sites[FX.SITE_C].raw_data is None
    lane_plan = tmp_path / "apply" / G.LANE_PLAN_FILE
    output = _accept_output(tmp_path, capsys, monkeypatch, _production(db, lane_plan))
    assert "RESULT: 0 deviation(s)" in output
    assert "not yet written 2" in output  # the reverted chunk's two rows
    assert "re-checked 4 written site(s) against their journal evidence" in output


def _plan_of(batch_id: str, *rows: tuple[str, str, str | None, str | None]) -> W4.WritePlan4:
    plan = W4.WritePlan4(group=W4.Group.WC, batch_id=batch_id)
    for site_id, column, old, new in rows:
        plan.rows.append(
            W4.Row4(
                group=W4.Group.WC, site_id=site_id, site_name="s", table="unified_sites",
                pk_column="id", pk=site_id, column=column, old_value=old, new_value=new,
                test_id="t", evidence={}, change_key=f"{batch_id}:{column}:{old}:{new}",
            )
        )  # fmt: skip
    return plan


def test_two_plans_may_write_one_cell_only_as_a_chain() -> None:
    """A text written, then written again (a clear and the WN text; a list run over a written
    text): each row's old value is the one before it's new value. Two plans claiming the same old
    text - two identical clears, or two different rewrites of it - are not a chain."""
    s = "site-1"
    chained = [
        _plan_of("p4wc-4001", (s, "description", "old", None)),
        _plan_of("p4wc-4002", (s, "description", None, "new"), (s, "raw_data", None, "{}")),
        _plan_of("p4wc-4003", (s, "description", "new", "newer")),
    ]
    assert W4.wc_sites_planned_twice(chained) == {}
    identical = [
        _plan_of("p4wc-4001", (s, "description", "old", None)),
        _plan_of("p4wc-4002", (s, "description", "old", None)),
    ]
    assert W4.wc_sites_planned_twice(identical) == {s: ["p4wc-4001", "p4wc-4002"]}
    rewrites = [
        _plan_of("p4wc-4001", (s, "description", "old", "a")),
        _plan_of("p4wc-4002", (s, "description", "old", "b")),
    ]
    assert W4.wc_sites_planned_twice(rewrites) == {s: ["p4wc-4001", "p4wc-4002"]}
    broken_later = [
        _plan_of("p4wc-4001", (s, "description", "old", "a")),
        _plan_of("p4wc-4002", (s, "description", "a", "b")),
        _plan_of("p4wc-4003", (s, "description", "a", "c")),
    ]
    assert list(W4.wc_sites_planned_twice(broken_later)) == [s]


# ----------------------------------------------------------- the API must know lane N first
def test_the_gate_refuses_a_lane_n_write_until_the_live_api_carries_the_lane_n_change(
    plan_path: Path, tmp_path, capsys, lane_n_history
) -> None:
    """Without `NO_LICENCE_LANES` naming N, `description_disclosure` raises KeyError('licence') on
    every page of a written WN site. Order of the work: deploy, check the commit, then write - the
    gate holds it, in a dry run, a rehearsal and an apply alike, and nothing is rendered."""
    intro, before, after = (lane_n_history[k] for k in ("change", "before", "after"))
    assert G.lane_n_commit() == intro  # found in the history, not typed
    db = _db()
    for mode in ((), ("--rehearse",), ("--apply", "--step", "100")):
        capsys.readouterr()
        assert (
            G.main(_args(tmp_path, plan_path, *mode), runner=db, api_commit=lambda host: before)
            == 1
        )
        err = capsys.readouterr().err
        assert "does not contain" in err and "NO_LICENCE_LANES" in err and "Deploy first" in err
        assert not db.journal and db.sites[WX.SITE_N].description is None
    assert not (tmp_path / "apply").exists() or not list((tmp_path / "apply").glob("p4wc-*"))
    capsys.readouterr()
    assert G.main(_args(tmp_path, plan_path), runner=db, api_commit=lambda host: after) == 0
    out = capsys.readouterr().out
    assert f"lane N: the live API runs {after[:12]}, which contains {intro[:12]}" in out
    # a commit git cannot place is refused too, never read as "fine"
    assert G.main(_args(tmp_path, plan_path), runner=db, api_commit=lambda host: "0" * 40) == 1
    assert "cannot relate the live API's commit" in capsys.readouterr().err


def test_a_plan_without_lane_n_text_never_asks_the_api(tmp_path, capsys, monkeypatch) -> None:
    """A WC plan (a March text) is lane L's: the check is not asked, so no ssh is made for it."""
    from tests.remediation.test_phase4_wc_write import _answers as wc_answers
    from tests.remediation.test_phase4_wc_write import _db as wc_db
    from tests.remediation.test_phase4_wc_write import _rows as wc_rows

    wc_plan = FX.build_run(tmp_path / "wc", wc_rows(), wc_answers(), name="wc-pilot")[1]

    def never(host: str) -> str:
        raise AssertionError("the API was asked for a plan that writes no lane-N text")

    args = ["--group", "WC", "--wc-plan", str(wc_plan), "--apply-root", str(tmp_path / "apply")]
    assert G.main(args, runner=wc_db(), api_commit=never) == 0
