"""Lane E's write (orchestrator decision X1, 2026-10-08): an enriched text reaches production only as the
plan says - the writer's group WC, the transaction's invariants 5 and 6 (the enrichment record instead
of the check record; lane E for a Phase-4 text), the gate (lane E needs the live API that names it) and
the step's acceptance - and the card lane reads the new text as a basis. Nothing here touches a
database: the fake psql parses what it is sent (`phase4_write_fixtures.FakeDb`). The mutation cases are
`ENRICH_MUTATIONS`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "output" / "remediation" / "tools", REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import verify_writes4 as V  # noqa: E402 - output/remediation/tools is on sys.path by the fixtures
import write_gate4 as G  # noqa: E402

from tests import git_env  # noqa: E402
from tests.remediation import enrich_fixtures as EF
from tests.remediation import phase4_write_fixtures as PFX
from tests.remediation import wc_fixtures as FX
from tests.remediation.phase4_write_fixtures import W4, M
from tests.remediation.test_phase4_wc_write import (
    _accept_output,
    _args,
    _production,
    _remade,
)
from tests.remediation.wc_fixtures import WC4


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict[str, Any]:
    return EF.built(tmp_path_factory.mktemp("enrich-write"))


def _db(built: dict[str, Any]) -> PFX.FakeDb:
    return PFX.FakeDb(
        {
            row["id"]: PFX.Site(description=row["description"], raw_data=row["raw_data"])
            for row in built["rows"]
        }
    )


def _live(db: PFX.FakeDb) -> dict[str, dict[str, Any]]:
    return {
        site_id: {"description": site.description, "raw_data": site.raw_data}
        for site_id, site in db.sites.items()
    }


def _plan(built: dict[str, Any], db: PFX.FakeDb | None = None) -> W4.WritePlan4:
    return W4.plan_wc(
        built["batch"],
        outcomes={built["batch"].batch_id: built["outcomes"]},
        live=_live(db or _db(built)),
    )


# ------------------------------------------------------------------------------ the plan
def test_each_enriched_site_becomes_its_description_row_and_its_raw_data_row(
    built: dict[str, Any],
) -> None:
    plan = _plan(built)
    assert plan.batch_id == "p4wc-4001" and not plan.refusals
    rows = {(row.site_id, row.column): row for row in plan.rows}
    assert {site for site, _ in rows} == {EF.SITE_W, EF.SITE_L, EF.SITE_N}  # not the unchanged site
    for site in (EF.SITE_W, EF.SITE_L, EF.SITE_N):
        outcome = built["outcomes"][site]
        description, raw = rows[(site, "description")], rows[(site, "raw_data")]
        assert (description.test_id, raw.test_id) == (W4.TEST_WC_DESCRIPTION, W4.TEST_WC_RAW_DATA)
        assert description.new_value == outcome.description
        assert description.old_value == outcome.evidence["checked"]  # the stored text, as it stands
        assert json.loads(raw.new_value) == outcome.raw_data
        assert raw.evidence == outcome.evidence
    assert all(row.change_key.startswith("phase4wc:") for row in plan.rows)


def test_a_site_that_moved_since_its_enrichment_was_asked_is_refused(built: dict[str, Any]) -> None:
    db = _db(built)
    db.sites[EF.SITE_W].description = "Someone edited this text."
    db.sites[EF.SITE_L].raw_data = {**db.sites[EF.SITE_L].raw_data, "title_es": "Templi"}
    plan = _plan(built, db)
    assert sorted((r.site_id, r.rule) for r in plan.refusals) == sorted(
        [(EF.SITE_W, W4.RULE_MOVED), (EF.SITE_L, W4.RULE_MOVED)]
    )
    assert {row.site_id for row in plan.rows} == {EF.SITE_N}


def test_a_written_enrichment_re_plans_to_the_rows_it_was_written_from(
    built: dict[str, Any],
) -> None:
    db = _db(built)
    chunk = W4.chunk_for(_plan(built, db))
    out = Path(built["root"]) / "apply-replan"
    W4.write_plan_files(out, _plan(built, db), chunk)
    assert W4.apply_chunk(chunk, out=out, rehearse=False, runner=db).ok
    again = _plan(built, db)  # the live pair is the outcome now: lane E is no "written by Phase 4"
    assert not again.refusals and len(again.rows) == len(chunk.rows)


def _rows(built: dict[str, Any]) -> list[W4.Row4]:
    return _plan(built).rows


def _edit_raw(rows: list[W4.Row4], site: str, change) -> list[W4.Row4]:
    out = []
    for row in rows:
        if row.site_id == site and row.column == "raw_data":
            raw = json.loads(row.new_value)
            change(raw)
            row = _remade(row, new_value=json.dumps(raw))
        out.append(row)
    return out


def _evidence_edited(rows: list[W4.Row4], site: str, change) -> list[W4.Row4]:
    out = []
    for row in rows:
        if row.site_id == site:
            evidence = json.loads(json.dumps(row.evidence))
            change(evidence)
            row = _remade(row, evidence=evidence)
        out.append(row)
    return out


def _lane_l_for(description: str) -> dict[str, Any]:
    return M.LegacyProvenance(desc_sha256=M.text_sha256(description)).to_dict()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rows, b: [r for r in rows if not (r.site_id == EF.SITE_W and r.column == "raw_data")],
         "site-atomic"),
        (lambda rows, b: [_remade(r, new_value=r.new_value + " More.")
                          if r.site_id == EF.SITE_W and r.column == "description" else r for r in rows],
         "not the evidence's transition"),
        (lambda rows, b: _edit_raw(rows, EF.SITE_W, lambda raw: raw.update(title_es="x")),
         "changes keys outside"),
        # the record that hashes the text is stale, or the check record of the base stands beside it
        (lambda rows, b: _edit_raw(rows, EF.SITE_W,
                                   lambda raw: raw[WC4.ENRICH_KEY].update(desc_sha256="a" * 64)),
         "desc_sha256 is not"),
        (lambda rows, b: _edit_raw(rows, EF.SITE_W,
                                   lambda raw: raw[WC4.ENRICH_KEY].update(verified_sha256="a" * 64)),
         "not the one its verifier confirmed|verified_sha256"),
        (lambda rows, b: _edit_raw(rows, EF.SITE_L,
                                   lambda raw: raw.update({WC4.CHECK_KEY: b["rows"][1]["raw_data"][WC4.CHECK_KEY]})),
         "check record beside"),
        # the provenance: not rehashed, of the wrong lane for the base, or its added list cut
        (lambda rows, b: _edit_raw(rows, EF.SITE_W,
                                   lambda raw: raw[M.PROVENANCE_KEY].update(desc_sha256="a" * 64)),
         "provenance's desc_sha256|AI disclosure"),
        (lambda rows, b: _edit_raw(rows, EF.SITE_W,
                                   lambda raw: raw.update({M.PROVENANCE_KEY: _lane_l_for(b["outcomes"][EF.SITE_W].description)})),
         "lane-L provenance|AI disclosure"),
        (lambda rows, b: _edit_raw(rows, EF.SITE_W,
                                   lambda raw: raw[M.PROVENANCE_KEY].update(added=raw[M.PROVENANCE_KEY]["added"][:1])),
         "old Phase-4 one with the appended sentences added"),
        (lambda rows, b: _edit_raw(rows, EF.SITE_L,
                                   lambda raw: raw.pop(M.PROVENANCE_KEY)),
         "carries its provenance|AI disclosure"),
        (lambda rows, b: _edit_raw(rows, EF.SITE_N,
                                   lambda raw: raw[M.PROVENANCE_KEY].update(desc_sha256="a" * 64)),
         "desc_sha256|AI disclosure"),
        # the evidence: its marking forged, its enrichment block missing, its verification broken
        (lambda rows, b: _evidence_edited(rows, EF.SITE_W,
                                          lambda e: e["marking"].update(old="unclaimed")),
         "recorded marking"),
        (lambda rows, b: _evidence_edited(rows, EF.SITE_W,
                                          lambda e: e.pop(WC4.ENRICH_EVIDENCE_KEY)),
         "does not read|compose"),
        (lambda rows, b: _evidence_edited(rows, EF.SITE_W,
                                          lambda e: e[WC4.VERIFICATION_KEY]["rounds"][0].update(answered_by="field_researcher:sonnet-enrich-we-0001")),
         "checked this site"),
        (lambda rows, b: _evidence_edited(rows, EF.SITE_W,
                                          lambda e: e[WC4.VERIFICATION_KEY]["rounds"][0].update(text_sha256="a" * 64)),
         "not what its rounds give|verified the text"),
    ],
)  # fmt: skip
def test_every_enrichment_plan_rule_refuses_a_broken_plan(
    built: dict[str, Any], mutate, message
) -> None:
    rows = _rows(built)
    W4.validate_rows(W4.Group.WC, rows)
    with pytest.raises((W4.W.WriteRefused, ValueError), match=message):
        W4.validate_rows(W4.Group.WC, mutate(rows, built))


# ------------------------------------------------------------------------------ the statement
def test_the_statement_reads_the_enrichment_record_and_maps_a_phase_4_text_to_lane_e(
    built: dict[str, Any],
) -> None:
    sql = W4.render_apply(W4.chunk_for(_plan(built)), rehearse=True)
    assert "'_description_enrichment' ELSE '_description_check'" in sql
    assert "THEN 'E'" in sql and "WHEN 'phase4' THEN CASE" in sql
    assert "'description_citations'" in sql  # the WC keys include the enrichment record
    assert "'_description_enrichment'" in "\n".join(W4._wc_invariants("wc write"))


def test_an_enriched_chunk_is_written_read_back_and_its_inverse_proven(
    built: dict[str, Any],
) -> None:
    db = _db(built)
    plan = _plan(built, db)
    chunk = W4.chunk_for(plan)
    out = Path(built["root"]) / "apply"
    W4.write_plan_files(out, plan, chunk)
    rehearsed = W4.apply_chunk(chunk, out=out, rehearse=True, runner=db)
    assert rehearsed.ok and not db.journal
    assert db.sites[EF.SITE_W].description == built["rows"][0]["description"]
    outcome = W4.apply_chunk(chunk, out=out, rehearse=False, runner=db)
    assert outcome.ok and outcome.written == len(plan.rows)
    for site_id, result in built["outcomes"].items():
        site = db.sites[site_id]
        assert (site.description, site.raw_data) == (result.description, result.raw_data)
        assert WC4.wc_problems(site.description, site.raw_data) == []
    assert {entry["run_stamp"] for entry in db.journal} == {"phase4wc:p4wc-4001:chunk-0001"}
    assert db.sites[EF.SITE_NONE].description == built["rows"][3]["description"]  # left as it was


@pytest.mark.parametrize("key", ["verified_sha256", "desc_sha256"])
def test_the_transaction_refuses_an_enrichment_record_that_names_another_text(
    built: dict[str, Any], key: str
) -> None:
    """Invariant 5 reads the enrichment record of a plan row whose evidence is an enrichment's: a
    rendered statement edited after its rendering is stopped in the database."""
    sql = W4.render_apply(W4.chunk_for(_plan(built)), rehearse=True)
    digest = built["outcomes"][EF.SITE_W].raw_data[WC4.ENRICH_KEY][key]
    marker = f'"{key}": "{digest}"'
    assert sql.count(marker) >= 1
    db = _db(built)
    edited = sql.replace(marker, f'"{key}": "' + "a" * 64 + '"')
    with pytest.raises(PFX.PsqlError, match="invariant 5"):
        db(edited, host="test")
    assert db.sites[EF.SITE_W].description == built["rows"][0]["description"] and not db.journal


def test_the_transaction_maps_a_phase_4_text_to_lane_e_and_no_other_lane(
    built: dict[str, Any],
) -> None:
    sql = W4.render_apply(W4.chunk_for(_plan(built)), rehearse=True)
    old_lane = '"lane": "E"'
    assert sql.count(old_lane) >= 1
    db = _db(built)
    with pytest.raises(PFX.PsqlError, match="invariant 6"):
        db(sql.replace(old_lane, '"lane": "W"'), host="test")
    assert not db.journal


# ------------------------------------------------------------------------------ the gate
@pytest.fixture(scope="module")
def api_history(tmp_path_factory) -> dict[str, str]:
    """A throwaway repository with the commits the gate reasons about: one before lane N's API change,
    lane N's, lane E's, and one after."""
    repo = tmp_path_factory.mktemp("api-history")

    def git(*argv: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *argv],
            capture_output=True, text=True, check=True, env=git_env.own_env(),
        )  # fmt: skip
        return done.stdout.strip()

    git("init", "-q")
    target = repo / G.LANE_N_FILE
    target.parent.mkdir(parents=True)
    commits: dict[str, str] = {}
    for name, text in (
        ("before", "LICENCE_LESS = frozenset({'L'})"),
        ("lane_n", f"{G.LANE_N_MARK} = frozenset({{'L', 'N'}})"),
        ("lane_e", f"{G.LANE_N_MARK} = frozenset({{'L', 'N'}})\n{G.LANE_E_MARK} = 'E'"),
        ("after", f"{G.LANE_N_MARK} = frozenset({{'L', 'N'}})\n{G.LANE_E_MARK} = 'E'\n# later"),
    ):
        target.write_text(text + "\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", name)
        commits[name] = git("rev-parse", "HEAD")
    return {"repo": str(repo), **commits}


@pytest.fixture
def _history(api_history, monkeypatch) -> None:
    monkeypatch.setattr(G, "LANE_N_REPO", Path(api_history["repo"]))


@pytest.fixture(scope="module")
def phase4_plan(tmp_path_factory) -> dict[str, Any]:
    """A plan with lane-E texts only (a Phase-4 text and a checked March text): no lane-N text."""
    root = tmp_path_factory.mktemp("lane-e-only")
    rows, answers = EF.standard_rows(root)
    keep = [EF.SITE_W, EF.SITE_L]
    run, plan = EF.build_enrich_run(
        root / "run", [r for r in rows if r["id"] in keep], answers, name="lane-e"
    )
    return {"plan": plan, "rows": [r for r in rows if r["id"] in keep], "root": root}


def _db_of(rows) -> PFX.FakeDb:
    return PFX.FakeDb(
        {r["id"]: PFX.Site(description=r["description"], raw_data=r["raw_data"]) for r in rows}
    )


def test_the_gate_refuses_a_lane_e_write_until_the_live_api_carries_the_lane_e_change(
    phase4_plan, tmp_path, capsys, api_history, _history
) -> None:
    """Without `ENRICHMENT_LANE` in `ATTRIBUTION_LANES` the page of an enriched Phase-4 text would show
    no attribution line for the Wikipedia sentences it still holds: order of the work - deploy, check
    the commit, then write - the gate holds it in a dry run, a rehearsal and an apply alike."""
    intro = api_history["lane_e"]
    assert G.lane_e_commit() == intro  # found in the history, not typed
    db = _db_of(phase4_plan["rows"])
    plan = phase4_plan["plan"]
    for live in (api_history["before"], api_history["lane_n"]):  # lane N's change is not lane E's
        for mode in ((), ("--rehearse",), ("--apply", "--step", "100")):
            capsys.readouterr()
            code = G.main(
                _args(tmp_path, plan, *mode), runner=db, api_commit=lambda host, c=live: c
            )
            err = capsys.readouterr().err
            assert code == 1 and "lane E: the live API runs" in err and "does not contain" in err
            assert "ENRICHMENT_LANE" in err and "Deploy first" in err
            assert (
                not db.journal
                and db.sites[EF.SITE_W].description == phase4_plan["rows"][0]["description"]
            )
    assert not list((tmp_path / "apply").glob("p4wc-*")) if (tmp_path / "apply").exists() else True
    capsys.readouterr()
    after = api_history["after"]
    assert G.main(_args(tmp_path, plan), runner=db, api_commit=lambda host: after) == 0
    out = capsys.readouterr().out
    assert f"lane E: the live API runs {after[:12]}, which contains {intro[:12]}" in out
    assert G.main(_args(tmp_path, plan), runner=db, api_commit=lambda host: "0" * 40) == 1
    assert "cannot relate the live API's commit" in capsys.readouterr().err


def test_a_plan_without_a_phase_4_enrichment_never_asks_the_api_about_lane_e(
    tmp_path, capsys, api_history, _history, built
) -> None:
    """A checked March text keeps lane L (the API knows it); only a W or S text that becomes lane E
    needs the API change. The lane-N text of the standard plan asks for lane N, not lane E."""
    root = tmp_path / "only-l"
    rows, answers = EF.standard_rows(root)
    keep = [r for r in rows if r["id"] == EF.SITE_L]
    _, plan = EF.build_enrich_run(root / "run", keep, answers, name="l-only")

    def never(host: str) -> str:
        raise AssertionError("the API was asked for a plan that writes no lane-E text")

    assert G.main(_args(tmp_path, plan), runner=_db_of(keep), api_commit=never) == 0
    # the standard plan holds a lane-N text too: the gate asks for lane N first and names it
    calls: list[str] = []
    code = G.main(
        _args(tmp_path / "b", built["plan"]), runner=_db(built),
        api_commit=lambda host: calls.append(host) or api_history["after"],
    )  # fmt: skip
    assert code == 0 and len(calls) == 2  # once for lane N, once for lane E
    out = capsys.readouterr().out
    assert "lane N: the live API runs" in out and "lane E: the live API runs" in out


# ------------------------------------------------------------------------------ the step's acceptance
def _written(tmp_path, built, api_history, monkeypatch, capsys) -> tuple[PFX.FakeDb, Any]:
    monkeypatch.setattr(G, "LANE_N_REPO", Path(api_history["repo"]))
    db = _db(built)
    code = G.main(
        _args(tmp_path, built["plan"], "--apply"),
        runner=db,
        api_commit=lambda host: api_history["after"],
    )
    assert code == 0
    capsys.readouterr()
    return db, _production(db, tmp_path / "apply" / G.LANE_PLAN_FILE)


def test_the_acceptance_re_derives_every_enriched_text_from_its_journal_evidence(
    built, tmp_path, capsys, monkeypatch, api_history
) -> None:
    db, production = _written(tmp_path, built, api_history, monkeypatch, capsys)
    output = _accept_output(tmp_path, capsys, monkeypatch, production)
    assert "RESULT: 0 deviation(s)" in output
    assert "re-checked 3 written site(s) against their journal evidence" in output
    assert "ACCEPT_EXIT=0" in output


def test_the_acceptance_refuses_an_enriched_text_that_is_not_what_the_evidence_composes(
    built, tmp_path, capsys, monkeypatch, api_history
) -> None:
    db, production = _written(tmp_path, built, api_history, monkeypatch, capsys)
    for entry in production.journal:
        if entry["row_pk"] == EF.SITE_W:
            evidence = json.loads(json.dumps(entry["evidence"]))
            evidence["sentences"][0]["sentence"] = (
                "Spiral reliefs decorate basalt slabs in the temples."
            )
            entry["evidence"] = evidence
    output = _accept_output(tmp_path, capsys, monkeypatch, production)
    assert (
        f"EVIDENCE {EF.SITE_W}: the description is not what the journal evidence composes" in output
    )
    assert "ACCEPT_EXIT=1" in output


def test_the_acceptance_holds_an_enriched_site_to_the_lanes_invariants(
    built, tmp_path, capsys, monkeypatch, api_history
) -> None:
    db, production = _written(tmp_path, built, api_history, monkeypatch, capsys)
    rows = production.sites
    stale = json.loads(json.dumps(rows[EF.SITE_L]["raw_data"]))
    stale[WC4.ENRICH_KEY]["desc_sha256"] = "a" * 64
    rows[EF.SITE_L]["raw_data"] = stale
    read = V.read_production(
        sorted(rows), stamp_like="phase4wc:%", columns=V.LANE_COLUMNS["p4wc"], run=production
    )
    carried = {("unified_sites", "raw_data", site) for site in rows}
    found = V.invariant_deviations(
        lane="p4wc", carried=carried, production=read,
        markings={s: o.evidence["marking"]["old"] for s, o in built["outcomes"].items()},
    )  # fmt: skip
    assert any(f"INVARIANT {EF.SITE_L}" in line and "desc_sha256 is not" in line for line in found)


# ------------------------------------------------------------------------------ the card basis
def test_the_card_lane_takes_an_enriched_text_as_a_basis_and_names_its_owner() -> None:
    from teaser import run as R

    text = "A text. It has more."
    digest = M.text_sha256(text)
    row = {"description": text, "lane": "E", "provenance_desc_sha256": digest,
           "check_desc_sha256": None}  # fmt: skip
    assert "E" in R.BASIS_LANES and R.basis_of(row) == "E"
    assert (
        R.basis_of({**row, "provenance_desc_sha256": "a" * 64}) is None
    )  # a stale hash is no basis
    # a checked March or lane-N text keeps its lane (no basis lane) and the enrichment record's hash
    # is the basis, as the check record's was: the query coalesces the two
    legacy = {**row, "lane": "L", "provenance_desc_sha256": digest, "check_desc_sha256": digest}
    assert R.basis_of(legacy) == R.SENTENCE_CHECKED
    assert "coalesce(u.raw_data -> '_description_enrichment' ->> 'desc_sha256'" in R.SITES_SQL
    assert R.ENRICH_KEY == WC4.ENRICH_KEY and R.OWNER_LANE["E"] == "WE"


def test_the_site_row_of_an_enriched_text_is_a_card_candidate(built: dict[str, Any]) -> None:
    from teaser import run as R

    outcome = built["outcomes"][EF.SITE_W]
    raw = outcome.raw_data
    row = {
        "site_id": EF.SITE_W, "name": "Tarxien", "country": "Malta", "description": outcome.description,
        "scope_status": None, "lane": raw[M.PROVENANCE_KEY]["lane"],
        "provenance_desc_sha256": raw[M.PROVENANCE_KEY]["desc_sha256"],
        "check_desc_sha256": raw[WC4.ENRICH_KEY]["desc_sha256"], "card_provenance": None,
        "has_card_row": True, "card": "An old card.", "alt_names": [],
    }  # fmt: skip
    assert R.classify(row) == (None, "")
