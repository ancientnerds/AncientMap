"""WC site-list runs (owner decision "Wikipedia/Wikidata reicht", 2026-10-01; runbook
`docs/procedures/SENTENCE_CHECK.md` section 11): the same check, verification, build and write over
exactly the listed curated sites - a March text, a Phase-4 text (WA's), a text a WC check kept before,
a text lane WN wrote - built from the `DESCRIPTION_DEFECTS.jsonl` of every WB run.

`wc/cli.py` (`export --sites`, `defect-sites`, the kinds), `wc/prompts_sonnet.py`, `phase4/wc4.py`
(`Marking.PHASE4`, `filtered_provenance`) and the writer's guards (moved-since-check, `--after`,
asked-again-later, invariant 6) - every existing population rule and guard of the plain runs is
`test_wc.py`'s and `test_phase4_wc_write.py`'s and stays as it was.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import write_gate4 as G  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402
from wc import answers as A  # noqa: E402
from wc import cli  # noqa: E402
from wc import prompts_sonnet as P2  # noqa: E402

from tests.remediation import phase4_write_fixtures as PFX  # noqa: E402
from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation import wn_fixtures as WX  # noqa: E402
from tests.remediation.phase4_write_fixtures import W4  # noqa: E402
from tests.remediation.test_phase4_wc_write import _accept_output, _production  # noqa: E402

SITE_P4 = "2a000000-0000-4000-8000-00000000002a"  #: a Phase-4 text; its sentence 2 is dropped
SITE_ALL = "2b000000-0000-4000-8000-00000000002b"  #: a Phase-4 text the check keeps whole
SITE_NONE = "2c000000-0000-4000-8000-00000000002c"  #: a Phase-4 text the check drops whole
SITE_MIS = "2d000000-0000-4000-8000-00000000002d"  #: a Phase-4 text whose provenance is 2 sentences
SITE_OUT = "2e000000-0000-4000-8000-00000000002e"  #: a curated site that is not in the list
SITE_RET = "2f000000-0000-4000-8000-00000000002f"  #: a retired site named by a list


def _p4_rows() -> list[dict[str, Any]]:
    short = WX.p4_site_raw()
    short[M.PROVENANCE_KEY] = {**short[M.PROVENANCE_KEY],
                               "sentences": short[M.PROVENANCE_KEY]["sentences"][:2]}  # fmt: skip
    return [
        FX.row(SITE_P4, WX.P4_TEXT, raw_data=WX.p4_site_raw(), name="Tarxien P4"),
        FX.row(SITE_ALL, WX.P4_TEXT, raw_data=WX.p4_site_raw(), name="Tarxien All"),
        FX.row(SITE_NONE, WX.P4_TEXT, raw_data=WX.p4_site_raw(), name="Tarxien None"),
        FX.row(SITE_MIS, WX.P4_TEXT, raw_data=short, name="Tarxien Mis"),
        FX.row(SITE_OUT, WX.P4_TEXT, raw_data=WX.p4_site_raw(), name="Tarxien Out"),
        FX.row(SITE_RET, WX.P4_TEXT, raw_data=WX.p4_site_raw(), scope_status="retired"),
    ]


def _p4_answers() -> dict[str, str]:
    dropped = FX.drop(2, "contradicted", FX.Q_DATE)
    return {
        SITE_P4: FX.answer(SITE_P4, [FX.keep(1, FX.Q_COMPLEX), dropped, FX.keep(3, FX.Q_ZAMMIT)]),
        SITE_ALL: FX.answer(
            SITE_ALL, [FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE), FX.keep(3, FX.Q_ZAMMIT)]
        ),  # fmt: skip
        SITE_NONE: FX.answer(SITE_NONE, [FX.drop(1), FX.drop(2), FX.drop(3)]),
    }


# ------------------------------------------------------------------------------ the population
def _pop(rows, *, kind=cli.KIND_LIST, only=None):
    return cli.population(rows, excluded=set(), earlier=set(), kind=kind, only=only)


def test_a_site_list_run_asks_exactly_the_listed_sites_and_each_text_under_its_marking() -> None:
    march = FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A))
    unclaimed = FX.row(FX.SITE_B, FX.TEXT_A, raw_data=None, snapshot=FX.TEXT_A)
    rows = [march, unclaimed, *_p4_rows()]
    listed = {FX.SITE_A, FX.SITE_B, SITE_P4, SITE_MIS, SITE_RET}
    asked, reasons = _pop(rows, only=listed)
    assert [(e["site_id"], e["marking"]) for e in asked] == [
        (FX.SITE_A, "L"), (FX.SITE_B, "unclaimed"), (SITE_P4, "phase4"),
    ]  # fmt: skip
    assert reasons == {"provenance-misaligned": [SITE_MIS], "retired": [SITE_RET]}
    assert all(e["site_id"] != SITE_OUT for e in asked)  # outside the list: not asked, not listed


def test_the_plain_runs_population_rules_are_what_they_were_for_the_same_rows() -> None:
    """Every existing rule of a plain run stays: a Phase-4 text and a text a check kept before are
    listed, never asked."""
    checked = FX.row(
        FX.SITE_C, FX.TEXT_A, raw_data={**FX.legacy_raw(FX.TEXT_A), WC4.CHECK_KEY: {"v": 2}}
    )
    asked, reasons = _pop([checked, *_p4_rows()], kind=cli.KIND_WC)
    assert asked == []
    assert reasons["phase4-text"] == [SITE_P4, SITE_ALL, SITE_NONE, SITE_MIS, SITE_OUT]
    assert reasons["checked-before"] == [FX.SITE_C]


def test_a_list_run_asks_a_text_a_check_kept_before_and_a_text_lane_wn_wrote(
    tmp_path: Path,
) -> None:
    kept = FX.build_run(
        tmp_path / "wc",
        [FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A))],
        {FX.SITE_A: FX.answer(FX.SITE_A, [FX.keep(1, FX.Q_COMPLEX), FX.drop(2), FX.drop(3)])},
    )[1]
    web = WX.build_wn_run(tmp_path / "wn", [WX.wn_row(WX.SITE_N)], {WX.SITE_N: WX.good(WX.SITE_N)})[
        1
    ]
    (checked,) = [WC4.WcOutcome.from_dict(o) for o in read_jsonl(kept)[0]["outcomes"]]
    (written,) = [WC4.WcOutcome.from_dict(o) for o in read_jsonl(web)[0]["outcomes"]]
    rows = [
        FX.row(FX.SITE_A, checked.description, raw_data=checked.raw_data),
        FX.row(WX.SITE_N, written.description, raw_data=written.raw_data),
    ]
    assert cli.population(rows, excluded=set(), earlier=set())[0] == []  # a plain run: neither
    asked, reasons = _pop(rows)
    assert not reasons
    assert [(e["site_id"], e["marking"]) for e in asked] == [(FX.SITE_A, "L"), (WX.SITE_N, "web")]


def test_a_provenance_that_does_not_hash_its_text_or_does_not_read_is_listed_not_asked() -> None:
    rows = _p4_rows()
    stale = json.loads(json.dumps(rows[0]["raw_data"]))
    stale[M.PROVENANCE_KEY]["desc_sha256"] = "a" * 64
    unreadable = json.loads(json.dumps(rows[0]["raw_data"]))
    unreadable[M.PROVENANCE_KEY] = {"lane": "W"}
    asked, reasons = _pop(
        [FX.row(FX.SITE_A, WX.P4_TEXT, raw_data=stale),
         FX.row(FX.SITE_B, WX.P4_TEXT, raw_data=unreadable)],
        only={FX.SITE_A, FX.SITE_B},
    )  # fmt: skip
    assert asked == []
    assert reasons == {"provenance-hash-differs": [FX.SITE_A], "provenance-unreadable": [FX.SITE_B]}


# ------------------------------------------------------------------------------ the export
def _read(tmp_path: Path, rows) -> Path:
    run = tmp_path / "runs" / "wcl"
    run.mkdir(parents=True)
    cli.cmd_read(run, runner=FX.ReadRunner(rows))
    return run


def _export(run: Path, tmp_path: Path, ids, **kw):
    listing = tmp_path / "list.txt"
    listing.write_text("".join(f"{i}\n" for i in ids) + "\n", encoding="utf-8")
    return cli.cmd_export(
        run, tmp_path / "h", batch_size=5, exclude=None, after=[], pilot=None, seed=None,
        sites=listing, **kw,
    )  # fmt: skip


def test_the_export_records_the_list_and_asks_the_listed_sites_only(tmp_path: Path) -> None:
    run = _read(tmp_path, _p4_rows())
    summary = _export(run, tmp_path, [SITE_P4, SITE_ALL])
    population = json.loads((run / cli.POPULATION_FILE).read_text(encoding="utf-8"))
    assert population["kind"] == "wc-list" and population["asked"] == 2
    assert population["list"]["sites"] == 2 and len(population["list"]["sha256"]) == 64
    assert population["by_marking"] == {"phase4": 2} and summary["questions"] == 2
    assert cli.run_kind(run) == "wc-list"
    assert [e["site_id"] for e in read_jsonl(run / cli.SITES_FILE)] == [SITE_P4, SITE_ALL]


def test_a_list_names_curated_sites_only_and_is_never_empty(tmp_path: Path) -> None:
    run = _read(tmp_path, _p4_rows())
    with pytest.raises(cli.WcRunError, match="no curated row of the read"):
        _export(run, tmp_path, [SITE_P4, FX.SITE_D])
    with pytest.raises(cli.WcRunError, match="an empty site list"):
        _export(run, tmp_path, [])
    with pytest.raises(cli.WcRunError, match="2f000000.*retired|nothing to ask"):
        _export(run, tmp_path, [SITE_RET])


def test_a_list_that_asks_nothing_stops_the_export(tmp_path: Path) -> None:
    run = _read(tmp_path, _p4_rows())
    with pytest.raises(cli.WcRunError, match="nothing to ask"):
        _export(run, tmp_path, [SITE_MIS])


def test_the_question_says_where_the_text_comes_from_and_a_phase4_text_is_not_trimmed(
    tmp_path: Path,
) -> None:
    run = _read(tmp_path, [FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A)),
                           *_p4_rows()])  # fmt: skip
    _export(run, tmp_path, [FX.SITE_A, SITE_P4])
    sites = cli.read_sites(run)
    march = cli.check_prompt(sites[FX.SITE_A], [1, 2, 3], {}, cli.KIND_LIST)
    p4 = cli.check_prompt(sites[SITE_P4], [1, 2, 3], {}, cli.KIND_LIST)
    assert P2.ORIGINS["L"] in march and "THIS TEXT IS NOT TRIMMED" not in march
    assert P2.ORIGINS["phase4"] in p4 and "THIS TEXT IS NOT TRIMMED" in p4
    assert "March 2026 by an AI enrichment chain and is shown" not in p4
    assert "KEEP_TRIMMED" in march and "answer KEEP or DROP for every sentence" in p4
    plain = cli.check_prompt(sites[FX.SITE_A], [1, 2, 3], {}, cli.KIND_WC)
    assert plain != march and "March 2026 by an AI enrichment chain and is shown" in plain


def test_a_phase4_text_is_never_trimmed_the_check_answer_refuses_a_cut(tmp_path: Path) -> None:
    run = _read(tmp_path, _p4_rows())
    _export(run, tmp_path, [SITE_P4])
    (record,) = cli.read_rounds(run)
    handoff = Path(record["handoff"])
    cut = FX.answer(SITE_P4, [FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE),
                              FX.trimmed(3, " in 1915", FX.Q_ZAMMIT)])  # fmt: skip
    clean, report = cli.check_answer(run, handoff, "wc-0001", SITE_P4, cut, fetch_pages=False)
    assert not clean and "S3: this text is not trimmed - answer KEEP" in report
    with pytest.raises(A.AnswerError, match="not trimmed"):
        A.parse_check(
            cut, site_id=SITE_P4, sentences=list(WX.P4_SENTENCES), asked=[1, 2, 3], trims=False
        )
    assert A.parse_check(cut, site_id=SITE_P4, sentences=list(WX.P4_SENTENCES), asked=[1, 2, 3])


def test_the_briefs_of_a_list_run_are_the_sonnet_ones_and_a_plain_run_keeps_its_own(
    tmp_path: Path,
) -> None:
    run = _read(tmp_path, _p4_rows())
    _export(run, tmp_path, [SITE_P4])
    (record,) = cli.read_rounds(run)
    brief = cli.brief(run, Path(record["handoff"]), "wc-0001")
    assert "Sonnet checker wc-0001" in brief and "--model claude-sonnet-5-5" in brief
    assert "--answered-by sonnet-check-r1-wc-0001" in brief and "claude-opus-5-5" not in brief


# ------------------------------------------------------------------------------ the build
@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("wcl")
    ids = [SITE_P4, SITE_ALL, SITE_NONE, SITE_MIS, SITE_RET]
    run, plan = WX.build_list_run(
        root, _p4_rows(), ids, _p4_answers(), pilot=True, name="wcl-pilot"
    )
    return root, run, plan


def _outcomes(plan: Path) -> dict[str, WC4.WcOutcome]:
    return {
        o["site_id"]: WC4.WcOutcome.from_dict(o)
        for batch in read_jsonl(plan)
        for o in batch["outcomes"]
    }


def test_a_phase4_text_keeps_its_kept_sentences_and_its_provenance_filtered_to_them(built) -> None:
    _, run, plan = built
    outcome = _outcomes(plan)[SITE_P4]
    assert outcome.description == (f"{WX.P4_SENTENCES[0][:-1]} [1]. {WX.P4_SENTENCES[2][:-1]} [2].")
    old = M.Provenance.from_dict(WX.p4_site_raw()[M.PROVENANCE_KEY])
    new = M.Provenance.from_dict(outcome.raw_data[M.PROVENANCE_KEY])
    assert new == dataclasses.replace(
        old, ai_system=M.AI_SYSTEM, sentences=(old.sentences[0], old.sentences[2]), card=None,
        desc_sha256=M.text_sha256(outcome.description),
    )  # fmt: skip
    assert (new.lane, new.ai, new.attribution, new.licence) == (
        M.Lane.W, M.AiMark.SELECTED, old.attribution, old.licence,
    )  # fmt: skip
    assert outcome.evidence["marking"]["old"] == "phase4"
    assert [s["verdict"] for s in outcome.evidence["sentences"]] == ["KEEP", "DROP", "KEEP"]
    assert WC4.wc_problems(outcome.description, outcome.raw_data, marking="phase4") == []
    assert WC4.wc_problems(outcome.description, outcome.raw_data)  # lane L's reading refuses it
    assert WC4.evidence_problems(outcome.evidence, outcome.description, outcome.raw_data) == []
    check = outcome.raw_data[WC4.CHECK_KEY]
    assert check["trimmed"] == 0 and check["kept"] == 2 and check["of"] == 3


def test_a_phase4_text_the_check_keeps_whole_is_not_written(built) -> None:
    _, run, plan = built
    assert SITE_ALL not in _outcomes(plan)
    summary = json.loads((run / cli.SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["kind"] == "wc-list"
    assert summary["not_planned"] == {"unchanged": [SITE_ALL]}
    finals = {f["site_id"]: f for f in read_jsonl(run / cli.FINAL_FILE)}
    assert finals[SITE_ALL]["planned"] is False and finals[SITE_ALL]["kept"] == 3
    assert finals[SITE_P4]["planned"] is True


def test_a_phase4_text_with_nothing_left_is_cleared_with_its_provenance_and_citations(
    built,
) -> None:
    _, run, plan = built
    cleared = _outcomes(plan)[SITE_NONE]
    assert cleared.description is None and cleared.raw_data is None
    assert WC4.wc_problems(None, None, marking="phase4") == []
    finals = {f["site_id"]: f for f in read_jsonl(run / cli.FINAL_FILE)}
    assert finals[SITE_NONE]["cleared"] is True and finals[SITE_NONE]["planned"] is True


def test_a_misaligned_provenance_and_a_retired_site_are_never_asked(built) -> None:
    _, run, _ = built
    population = json.loads((run / cli.POPULATION_FILE).read_text(encoding="utf-8"))
    assert population["listed"] == {"provenance-misaligned": [SITE_MIS], "retired": [SITE_RET]}
    assert population["asked"] == 3 and population["pilot"] == {"sites": 3, "seed": 1}


def test_the_verifier_and_the_judge_of_a_list_run_are_sonnet_agents(built) -> None:
    root, run, _ = built
    verify = next((root / "handoff" / "wcl-pilot-verify").glob("verify-0001"))
    assert verify.is_dir()
    handoff = root / "handoff" / "wcl-pilot-verify"
    brief = cli.verify_brief(run, handoff, "verify-0001")
    assert "Sonnet verifier verify-0001" in brief and "--answered-by sonnet-wc-verify-0001" in brief
    judge = cli.judge_brief(run, root / "handoff" / "wcl-pilot-judge", "judge-0001")
    assert "Sonnet judge judge-0001" in judge and "--model claude-sonnet-5-5" in judge
    assert "--answered-by sonnet-wc-judge-judge-0001" in judge
    result = json.loads((run / "judge" / "RESULT.json").read_text(encoding="utf-8"))
    assert result["passed"] is True


# ------------------------------------------------------------------------------ filtering
def _two_source_provenance() -> M.Provenance:
    base = PFX.assembly(card=None).provenance
    german = M.SourceRef(
        id="T.de", url="https://de.wikipedia.org/w/index.php?title=Tarxien&oldid=7", revid=7,
        rev_timestamp="2026-09-01T10:00:00Z", text_sha256=M.text_sha256("x"),
        licence=M.Licence.CC_BY_SA_4,
    )  # fmt: skip
    third = M.PublishedSentence(n=1, src="T.de", start=0, end=10, drop=())
    return dataclasses.replace(
        base, sources=(*base.sources, german), sentences=(*base.sentences, third)
    )


def test_filtering_a_provenance_follows_the_kept_sentences_and_their_sources() -> None:
    old = _two_source_provenance()
    kept = WC4.filtered_provenance(old, [1, 3], of=3, description="A new text.")
    assert [s.src for s in kept.sentences] == ["W", "T.de"] and len(kept.sources) == 2
    only_w = WC4.filtered_provenance(old, [1, 2], of=3, description="A new text.")
    assert [s.id for s in only_w.sources] == ["W"] and M.Provenance.from_dict(only_w.to_dict())
    assert only_w.card is None and only_w.ai_system == M.AI_SYSTEM
    assert only_w.desc_sha256 == M.text_sha256("A new text.")


def test_filtering_drops_the_card_of_sentences_that_changed() -> None:
    """The Phase-5 card key names sentences by index: once a sentence is dropped it names the wrong
    ones, and the card text itself is lane WB's to rewrite."""
    old = M.Provenance.from_dict(WX.p4_site_raw(card=True)[M.PROVENANCE_KEY])
    assert old.card is not None
    assert WC4.filtered_provenance(old, [1, 3], of=3, description="A new text.").card is None


def test_filtering_refuses_what_it_cannot_keep_true() -> None:
    old = _two_source_provenance()
    with pytest.raises(WC4.WcError, match="cannot be matched one for one"):
        WC4.filtered_provenance(old, [1], of=4, description="x")
    with pytest.raises(WC4.WcError, match="nothing kept"):
        WC4.filtered_provenance(old, [], of=3, description="x")
    with pytest.raises(
        WC4.WcError, match="no kept sentence cites the source the attribution names"
    ):
        WC4.filtered_provenance(old, [3], of=3, description="x")


def test_a_phase4_text_is_never_trimmed_in_the_record_either() -> None:
    site = FX.plan_site(FX.row(SITE_P4, WX.P4_TEXT, raw_data=WX.p4_site_raw()))
    assert WC4.old_marking(site, listed=True) is WC4.Marking.PHASE4
    with pytest.raises(WC4.WcError, match="never trimmed"):
        WC4.provenance_after(site, "A new text.", kept=[1], of=3, trimmed=1, listed=True)
    with pytest.raises(WC4.WcError, match="wrote this text in Phase 4"):
        WC4.old_marking(site)  # a plain run asks none


def test_the_marking_of_a_site_without_a_description_and_of_a_rechecked_text() -> None:
    assert WC4.old_marking(FX.plan_site(WX.wn_row(WX.SITE_N))) is WC4.Marking.NONE
    assert WC4.old_marking(FX.plan_site(WX.wn_row(WX.SITE_N, "  "))) is WC4.Marking.NONE
    with pytest.raises(WC4.WcError, match="no description beside"):
        WC4.old_marking(FX.plan_site(WX.wn_row(WX.SITE_N, raw_data={WC4.CHECK_KEY: {}})))
    again = FX.plan_site(FX.row(FX.SITE_A, FX.TEXT_A, raw_data={**FX.legacy_raw(FX.TEXT_A),
                                                                  WC4.CHECK_KEY: {"v": 2}}))  # fmt: skip
    assert WC4.old_marking(again, listed=True) is WC4.Marking.L
    with pytest.raises(WC4.WcError, match="checked sentence by sentence before"):
        WC4.old_marking(again)


# ------------------------------------------------------------------------------ the writer
def _db(rows=None) -> PFX.FakeDb:
    return PFX.FakeDb(
        {
            r["id"]: PFX.Site(description=r["description"], raw_data=r["raw_data"])
            for r in (rows or _p4_rows())
        }  # fmt: skip
    )


def _live(db: PFX.FakeDb) -> dict[str, dict[str, Any]]:
    return {i: {"description": s.description, "raw_data": s.raw_data} for i, s in db.sites.items()}


def test_a_phase4_text_of_a_list_run_is_planned_not_refused_as_written_by_phase_4(built) -> None:
    _, _, plan = built
    (batch,), outcomes = W4.load_wc_plan([plan])
    result = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db()))
    assert not result.refusals
    rows = {(r.site_id, r.column): r for r in result.rows}
    assert {site for site, _ in rows} == {SITE_P4, SITE_NONE}
    assert rows[(SITE_NONE, "description")].test_id == W4.TEST_WC_DESCRIPTION_CLEAR
    assert rows[(SITE_P4, "description")].test_id == W4.TEST_WC_DESCRIPTION


def test_a_list_run_site_that_moved_since_its_check_is_refused(built) -> None:
    _, _, plan = built
    (batch,), outcomes = W4.load_wc_plan([plan])
    db = _db()
    db.sites[SITE_P4].description = "Someone edited this Phase-4 text."
    live = _live(db)
    del live[SITE_NONE]
    result = W4.plan_wc(batch, outcomes=outcomes, live=live)
    assert sorted((r.site_id, r.rule) for r in result.refusals) == sorted(
        [(SITE_P4, W4.RULE_MOVED), (SITE_NONE, W4.RULE_MOVED)]
    )
    assert not result.rows


def test_a_later_plan_takes_over_a_site_it_asks_again_and_after_leaves_the_earlier_ones(
    built, tmp_path: Path
) -> None:
    _, run, first = built
    ids = [SITE_P4, SITE_ALL]
    # the second run reads the same production: both claim SITE_P4 unless `--after` names the first
    second_run, second = WX.build_list_run(
        tmp_path, _p4_rows(), ids, _p4_answers(), name="wcl-second", first_batch=4002
    )
    (b1, b2), outcomes = W4.load_wc_plan([first, second])
    taken = W4.plan_wc(b1, outcomes=outcomes, live=_live(_db()))
    assert (SITE_P4, W4.RULE_TAKEN_OVER) in {(r.site_id, r.rule) for r in taken.refusals}
    assert SITE_P4 in {r.site_id for r in W4.plan_wc(b2, outcomes=outcomes, live=_live(_db())).rows}
    both = W4.wc_sites_planned_twice(
        [W4.plan_wc(b, outcomes=outcomes, live=_live(_db())) for b in (b1, b2)]
    )
    assert both == {}  # one site, one batch
    # `--after`: a chunk that names the first run asks none of its sites again
    third = tmp_path / "runs" / "wcl-third"
    third.mkdir(parents=True)
    cli.cmd_read(third, runner=FX.ReadRunner(_p4_rows()))
    listing = tmp_path / "third.txt"
    listing.write_text(f"{SITE_P4}\n{SITE_ALL}\n{SITE_NONE}\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="nothing to ask"):
        cli.cmd_export(
            third, tmp_path / "h3", batch_size=5, exclude=None, after=[run], pilot=None,
            seed=None, sites=listing,
        )  # fmt: skip
    listing.write_text(f"{SITE_P4}\n{SITE_OUT}\n", encoding="utf-8")
    cli.cmd_export(
        third, tmp_path / "h4", batch_size=5, exclude=None, after=[run], pilot=None, seed=None,
        sites=listing,
    )  # fmt: skip
    population = json.loads((third / cli.POPULATION_FILE).read_text(encoding="utf-8"))
    assert population["listed"] == {"earlier-run": [SITE_P4]} and population["asked"] == 1
    assert second_run.name == "wcl-second"


def test_the_plan_refuses_a_phase4_provenance_that_is_not_the_old_one_filtered(built) -> None:
    _, _, plan = built
    (batch,), outcomes = W4.load_wc_plan([plan])
    rows = W4.plan_wc(batch, outcomes=outcomes, live=_live(_db())).rows
    W4.validate_rows(W4.Group.WC, rows)

    def edited(change) -> list[W4.Row4]:
        out = []
        for row in rows:
            if row.site_id == SITE_P4 and row.column == "raw_data":
                raw = json.loads(row.new_value)
                change(raw[M.PROVENANCE_KEY])
                row = _remake(row, json.dumps(raw))
            out.append(row)
        return out

    old = M.Provenance.from_dict(WX.p4_site_raw()[M.PROVENANCE_KEY]).to_dict()
    for change, message in (
        (lambda p: p.update(sentences=old["sentences"]), "published sentences|filtered"),
        (
            lambda p: p.update(
                card={"items": [{"sentence": 0, "drop": []}], "text_sha256": "b" * 64}
            ),
            "filtered",
        ),
        (lambda p: p.update(ai_system=M.AI_SYSTEM_OPUS), "filtered"),
    ):
        with pytest.raises((W4.W.WriteRefused, ValueError), match=message):
            W4.validate_rows(W4.Group.WC, edited(change))


def _remake(row: W4.Row4, new_value: str) -> W4.Row4:
    data = {**row.to_dict(), "new_value": new_value}
    data["change_key"] = W4.W.change_key(
        site_id=data["site_id"], table=data["table"], column=data["column"],
        old_value=data["old_value"], new_value=data["new_value"], test_id=data["test_id"],
        lane=W4.GROUP_FAMILY[W4.Group.WC],
    )  # fmt: skip
    return W4.Row4.from_dict(data)


def test_a_list_plan_is_written_accepted_and_every_site_holds_the_invariants(
    built, tmp_path, capsys, monkeypatch
) -> None:
    _, _, plan = built
    db = _db()
    args = ["--group", "WC", "--wc-plan", str(plan), "--apply-root", str(tmp_path / "apply")]
    assert G.main(args, runner=db) == 0
    assert G.main([*args, "--rehearse"], runner=db) == 0
    assert not db.journal
    assert G.main([*args, "--apply", "--step", "100"], runner=db) == 0
    p4 = db.sites[SITE_P4]
    assert (
        p4.raw_data[M.PROVENANCE_KEY]["lane"] == "W"
        and len(p4.raw_data[M.PROVENANCE_KEY]["sentences"]) == 2
    )
    assert db.sites[SITE_NONE].description is None and db.sites[SITE_NONE].raw_data is None
    assert db.sites[SITE_ALL].description == WX.P4_TEXT  # kept whole: not written
    capsys.readouterr()
    production = _production(db, tmp_path / "apply" / G.LANE_PLAN_FILE)
    output = _accept_output(tmp_path, capsys, monkeypatch, production)
    assert "RESULT: 0 deviation(s)" in output
    # a card the filtered provenance dropped is no longer claimed: put a stale one back and the
    # evidence re-check names it
    stale = production.sites[SITE_P4]["raw_data"][M.PROVENANCE_KEY]
    production.sites[SITE_P4]["raw_data"][M.PROVENANCE_KEY] = {
        **stale, "card": {"items": [{"sentence": 0, "drop": []}], "text_sha256": "b" * 64}
    }  # fmt: skip
    refused = _accept_output(tmp_path, capsys, monkeypatch, production)
    assert f"EVIDENCE {SITE_P4}: the provenance still names a card" in refused
    # ... and the provenance lists one published sentence per kept sentence, not the old three
    production.sites[SITE_P4]["raw_data"][M.PROVENANCE_KEY] = {
        **stale, "sentences": WX.p4_site_raw()[M.PROVENANCE_KEY]["sentences"]
    }  # fmt: skip
    refused = _accept_output(tmp_path, capsys, monkeypatch, production)
    assert f"EVIDENCE {SITE_P4}: the provenance lists 3 published sentences, the evidence kept 2" in (
        refused
    )  # fmt: skip


def test_a_trimmed_phase4_text_is_refused_by_the_writers_plan_rules(built) -> None:
    """The record says KEEP_TRIMMED for a Phase-4 text: no filtered provenance can follow a cut."""
    _, _, plan = built
    (batch,), outcomes = W4.load_wc_plan([plan])
    outcome = outcomes[batch.batch_id][SITE_P4]
    evidence = json.loads(json.dumps(outcome.evidence))
    evidence["sentences"][0]["verdict"] = "KEEP_TRIMMED"
    evidence["sentences"][0]["remove"] = " in Tarxien, Malta"
    problems = W4._phase4_problems("phase4", evidence, outcome.description, WX.p4_site_raw(),
                                   outcome.raw_data)  # fmt: skip
    assert problems == ["a Phase-4 text is only kept or dropped by sentence, never trimmed"]
    assert (
        W4._phase4_problems("L", evidence, outcome.description, None, None) == []
    )  # not its marking


def test_the_in_database_invariant_expects_the_old_lane_for_a_phase4_text(built) -> None:
    _, _, plan = built
    (batch,), outcomes = W4.load_wc_plan([plan])
    chunk = W4.chunk_for(W4.plan_wc(batch, outcomes=outcomes, live=_live(_db())))
    sql = W4.render_apply(chunk, rehearse=True)
    db = _db()
    assert db(sql, host="test") == "NOTICE\n"  # the filtered provenance keeps lane W
    assert db.sites[SITE_P4].description == WX.P4_TEXT and not db.journal  # rolled back
    # the rendered statement edited after its rendering: the written provenance names lane S, the
    # old Phase-4 provenance (the plan row's old value) was lane W - invariant 6 refuses it
    marker = f"'{SITE_P4}'::uuid, 'unified_sites', 'raw_data'"
    (line,) = [
        row
        for row in sql.splitlines()
        if row.lstrip().startswith(f"('{SITE_P4}'::uuid, 'unified_sites', 'raw_data'")
    ]
    at = line.rfind('"lane": "W"')
    assert marker in line and at > 0
    edited = sql.replace(line, line[:at] + '"lane": "S"' + line[at + len('"lane": "W"') :])
    with pytest.raises(PFX.PsqlError, match="invariant 6"):
        db(edited, host="test")
    assert db.sites[SITE_P4].description == WX.P4_TEXT and not db.journal


# ------------------------------------------------------------------------------ the pilot gate
def test_a_list_run_is_in_the_wc_class_and_needs_the_wc_pilot(built, tmp_path: Path) -> None:
    _, _, plan = built
    wc_pilot = FX.build_run(
        tmp_path / "c",
        [FX.row(FX.SITE_A, FX.TEXT_A, raw_data=FX.legacy_raw(FX.TEXT_A))],
        {FX.SITE_A: FX.answer(FX.SITE_A, [FX.keep(1, FX.Q_COMPLEX), FX.drop(2), FX.drop(3)])},
        name="wc-pilot",
    )[1]
    _, chunk = WX.build_list_run(tmp_path / "d", _p4_rows(), [SITE_P4], _p4_answers(), name="wcl-chunk",
                                 first_batch=4003)  # fmt: skip
    assert len(cli.pilot_approval([wc_pilot, chunk])) == 1  # the WC pilot approves a list chunk
    with pytest.raises(cli.WcRunError, match="the first WC plan named is the pilot's"):
        cli.pilot_approval([chunk])
    # a list run that is itself a pilot (`--pilot`) and passed its judge approves later chunks
    assert len(cli.pilot_approval([plan, chunk])) == 1


# ------------------------------------------------------------------------------ the defects
def _defect(site_id: str, sha: str, **kw) -> dict[str, Any]:
    line = {
        "basis": "W", "candidates": ["S2"], "claim": "They date to 3150 BC", "desc_sha256": sha,
        "mapped_by": "teaser-rewrite-v-001", "name": "Tarxien P4", "owner_lane": "WA",
        "proven": True, "quote": "The temples date from 2500 BC.", "quote_outcome": "found",
        "run": "wb-ws-2026-09-27-01", "sentence": 2, "sentence_text": WX.P4_SENTENCES[1],
        "site_id": site_id, "stage": "verify", "url": FX.WIKI, "verifier": "teaser-verify-001",
    }  # fmt: skip
    return {**line, **kw}


def test_the_site_list_is_built_from_the_defects_that_still_describe_the_served_text(
    tmp_path: Path,
) -> None:
    rows = _p4_rows()
    run = _read(tmp_path, rows)
    sha = M.text_sha256(WX.P4_TEXT)
    defects = tmp_path / "wb-01" / "DESCRIPTION_DEFECTS.jsonl"
    defects.parent.mkdir()
    more = tmp_path / "wb-02" / "DESCRIPTION_DEFECTS.jsonl"
    more.parent.mkdir()
    lines = [
        _defect(SITE_P4, sha),
        _defect(SITE_P4, sha, claim="another claim", stage="verify2", sentence=None),
        _defect(SITE_ALL, "c" * 64),  # the text changed since: not the defective one
        _defect(SITE_NONE, sha, proven=False, quote_outcome="fetch failed"),
        _defect(SITE_RET, sha),
        _defect("30000000-0000-4000-8000-000000000030", sha),  # not a curated row
    ]
    defects.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    more.write_text(
        json.dumps(_defect(SITE_ALL, sha, owner_lane="WC", basis="WC")) + "\n", encoding="utf-8"
    )
    out = tmp_path / "list.txt"
    report = cli.cmd_defect_sites(run, [defects, more], out)
    assert out.read_text(encoding="utf-8").split() == sorted([SITE_P4, SITE_NONE, SITE_ALL])
    assert report["lines"] == 7 and report["sites"] == 3
    assert report["skipped"] == {"not-a-curated-row": 1, "retired": 1, "text-changed-since": 1}
    assert report["by_owner_lane"] == {"WA": 2, "WC": 1}
    saved = json.loads(out.with_name("list.txt.report.json").read_text(encoding="utf-8"))
    assert [c["claim"] for c in saved["claims"][SITE_P4]] == [
        "They date to 3150 BC",
        "another claim",
    ]
    proven = cli.cmd_defect_sites(run, [defects, more], tmp_path / "proven.txt", proven_only=True)
    assert proven["sites"] == 2 and proven["skipped"]["unproven"] == 1
    # the list drives a run: export --sites asks exactly these
    cli.cmd_export(
        run, tmp_path / "h", batch_size=5, exclude=None, after=[], pilot=None, seed=None, sites=out
    )
    assert [e["site_id"] for e in read_jsonl(run / cli.SITES_FILE)] == sorted(
        [SITE_P4, SITE_NONE, SITE_ALL]
    )


def test_a_line_that_is_no_defect_or_names_no_site_stops_the_command(tmp_path: Path) -> None:
    run = _read(tmp_path, _p4_rows())
    bad = tmp_path / "d.jsonl"
    bad.write_text(json.dumps({"site_id": SITE_P4}) + "\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="not a DESCRIPTION_DEFECTS line"):
        cli.cmd_defect_sites(run, [bad], tmp_path / "o.txt")
    bad.write_text(json.dumps(_defect("not-a-uuid", "a" * 64)) + "\n", encoding="utf-8")
    with pytest.raises(cli.WcRunError, match="d.jsonl:1"):
        cli.cmd_defect_sites(run, [bad], tmp_path / "o.txt")


def test_the_command_line_has_the_new_options() -> None:
    parser = cli.build_parser()
    export = parser.parse_args(
        ["export", "--run-dir", "r", "--handoff", "h", "--sites", "f.txt", "--wn"]
    )
    assert (export.sites, export.wn) == (Path("f.txt"), True)
    defects = parser.parse_args(
        ["defect-sites", "--run-dir", "r", "--defects", "a", "--defects", "b", "--out", "o",
         "--proven-only"]
    )  # fmt: skip
    assert defects.defects == [Path("a"), Path("b")] and defects.proven_only
    plain = parser.parse_args(["export", "--run-dir", "r", "--handoff", "h"])
    assert plain.sites is None and plain.wn is False
