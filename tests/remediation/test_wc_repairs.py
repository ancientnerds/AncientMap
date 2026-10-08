"""The description repairs of the final repair (owner decisions D25b, D10 and D22 of 2026-10-08), on
lane WC's machinery:

* `defect-kept-sites` / the adversarial export / `defect-closure`: a reported claim that the check and
  the verifier both left standing is checked a second time by the adversarial role; its drop is
  written like every WC drop, its refutation is closed in the audit log;
* `minimax-sites`: the texts a MiniMax answer shaped and that still stand are asked again, by Claude,
  as a site-list run (a text lane WN wrote is asked again as `web`);
* the WN rerun's question names the site's English Wikipedia title and Wikidata item.

No socket, no model, no database.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from phase3.run import read_jsonl  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402
from wc import cli as C  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation import wn_fixtures as WX  # noqa: E402
from tests.remediation.test_wc_list import (  # noqa: E402
    SITE_ALL,
    SITE_NONE,
    SITE_P4,
    _defect_answers,
    _defect_lines,
    _p4_rows,
)
from tests.remediation.test_wc_verify import _answers, _rows  # noqa: E402
from tests.remediation.wc_fixtures import OH, wiki_cache  # noqa: E402,F401


@pytest.fixture(scope="module")
def built_defects(tmp_path_factory):
    """`test_wc_list`'s defect run: a Phase-4 text whose reported sentence is dropped (SITE_P4), one
    whose claim is tied to no sentence and that the check keeps whole (SITE_ALL: `defect-kept`), one
    whose reported sentence is kept and the rest dropped (SITE_NONE)."""
    root = tmp_path_factory.mktemp("wcd")
    run, plan = WX.build_list_run(
        root,
        _p4_rows(),
        [SITE_P4, SITE_ALL, SITE_NONE],
        _defect_answers(),
        name="wcl-defects",
        defect_lines=_defect_lines(M.text_sha256(WX.P4_TEXT)),
    )
    return root, run, plan


def _fresh_rows(plan: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows of a read made after `plan` was written: a planned site carries its new text."""
    written = {}
    for batch in read_jsonl(plan):
        for outcome in (WC4.WcOutcome.from_dict(o) for o in batch["outcomes"]):
            written[outcome.site_id] = outcome
    out = []
    for row in rows:
        outcome = written.get(row["id"])
        out.append(
            row
            if outcome is None
            else FX.row(row["id"], outcome.description, raw_data=outcome.raw_data, name=row["name"])
        )
    return out


def _read(tmp_path: Path, rows) -> Path:
    run = tmp_path / "runs" / "fresh"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=FX.ReadRunner(rows))
    return run


# ------------------------------------------------------------------------------ the standing claims
def test_the_standing_claims_of_a_built_run_become_the_list_of_the_adversarial_check(
    built_defects, tmp_path: Path
) -> None:
    root, source, plan = built_defects
    summary = json.loads((source / C.SUMMARY_FILE).read_text(encoding="utf-8"))
    assert set(summary["defects_kept"]) == {SITE_ALL, SITE_NONE}  # SITE_P4's claim was dropped
    run = _read(tmp_path, _fresh_rows(plan, _p4_rows()))
    out = tmp_path / "kept.txt"
    report = C.cmd_defect_kept_sites(run, [source], out)
    assert out.read_text(encoding="utf-8").split() == sorted([SITE_ALL, SITE_NONE])
    assert report["sites"] == 2 and report["skipped"] == {}
    claims = json.loads(out.with_name("kept.txt.report.json").read_text("utf-8"))["claims"]
    # a claim tied to no sentence stays tied to none; a tied one is found again in the live text
    (unmapped,) = claims[SITE_ALL]
    assert unmapped["sentence"] is None
    (mapped,) = claims[SITE_NONE]
    live = WC4.checked_sentences(_site_text(run, SITE_NONE))
    assert mapped["sentence"] == 1 and mapped["sentence_text"] == live[0]
    assert set(claims[SITE_NONE][0]) == set(C.DEFECT_CLAIM_KEYS)


def test_a_standing_claim_is_numbered_again_where_the_sentences_before_it_were_dropped(
    tmp_path: Path,
) -> None:
    """A text written since keeps the reported third sentence as its first: the claim must point at
    the sentence as it stands, or the adversary would settle another one."""
    site = "3a000000-0000-4000-8000-00000000003a"
    rows = [FX.row(site, WX.P4_TEXT, raw_data=WX.p4_site_raw(), name="Tarxien Third")]
    sha = M.text_sha256(WX.P4_TEXT)
    line = {
        "basis": "W", "candidates": [], "claim": "Zammit dug it in 1915", "desc_sha256": sha,
        "mapped_by": "m", "name": "x", "owner_lane": "WA", "proven": True,
        "quote": "Excavations were in 1920.", "quote_outcome": "found", "run": "wb-1",
        "sentence": 3, "sentence_text": WX.P4_SENTENCES[2], "site_id": site, "stage": "verify",
        "url": FX.WIKI, "verifier": "v",
    }  # fmt: skip
    answers = {site: FX.answer(site, [FX.drop(1), FX.drop(2), FX.keep(3, FX.Q_ZAMMIT)])}
    source, plan = WX.build_list_run(
        tmp_path / "src", rows, [site], answers, name="wcl-third", defect_lines=[line]
    )
    run = _read(tmp_path / "fresh", _fresh_rows(plan, rows))
    out = tmp_path / "kept.txt"
    assert C.cmd_defect_kept_sites(run, [source], out)["sites"] == 1
    (claim,) = json.loads(out.with_name("kept.txt.report.json").read_text("utf-8"))["claims"][site]
    assert claim["sentence"] == 1 and claim["sentence_text"] == WX.P4_SENTENCES[2].strip()
    assert len(WC4.checked_sentences(_site_text(run, site))) == 1


def _site_text(run: Path, site_id: str) -> str:
    return next(r for r in read_jsonl(run / C.ROWS_FILE) if r["id"] == site_id)["description"]


def test_a_site_that_changed_or_left_is_counted_and_not_checked_again(
    built_defects, tmp_path: Path
) -> None:
    _, source, plan = built_defects
    rows = _fresh_rows(plan, _p4_rows())
    moved = [
        FX.row(
            r["id"], "A text another lane wrote since stands here.", raw_data=None, name=r["name"]
        )
        if r["id"] == SITE_NONE
        else r
        for r in rows
    ]
    run = _read(tmp_path / "a", moved)
    report = C.cmd_defect_kept_sites(run, [source], tmp_path / "a" / "k.txt")
    assert report["sites"] == 1 and report["skipped"] == {"text-changed-since": 1}
    cleared = [
        FX.row(r["id"], None, raw_data=None, name=r["name"]) if r["id"] == SITE_ALL else r
        for r in rows
    ]
    run = _read(tmp_path / "b", cleared)
    report = C.cmd_defect_kept_sites(run, [source], tmp_path / "b" / "k.txt")
    assert report["sites"] == 1 and report["skipped"] == {"no-description": 1}
    retired = [
        FX.row(
            r["id"],
            r["description"],
            raw_data=r["raw_data"],
            scope_status="retired",
            name=r["name"],
        )
        if r["id"] == SITE_ALL
        else r
        for r in rows
    ]
    run = _read(tmp_path / "c", retired)
    assert C.cmd_defect_kept_sites(run, [source], tmp_path / "c" / "k.txt")["skipped"] == {
        "retired": 1
    }
    with pytest.raises(C.WcRunError, match="not a built site-list run"):
        plain = FX.build_run(tmp_path / "p", _rows(), _answers(), pilot=False)[0]
        C.cmd_defect_kept_sites(run, [plain], tmp_path / "p.txt")


def test_the_adversary_drops_one_standing_sentence_and_refutes_the_other(
    built_defects, tmp_path: Path
) -> None:
    """The whole second check: the list, the adversarial export, the answers in the adversarial
    role (Opus), the import, the verification and the build; then the closure for the audit log."""
    _, source, plan = built_defects
    run = _read(tmp_path, _fresh_rows(plan, _p4_rows()))
    out = tmp_path / "kept.txt"
    C.cmd_defect_kept_sites(run, [source], out)
    handoff = tmp_path / "handoff" / "adv-r1"
    C.cmd_export(
        run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None, sites=out,
        defects=out.with_name("kept.txt.report.json"), adversarial=True,
    )  # fmt: skip
    live = WC4.checked_sentences(_site_text(run, SITE_NONE))
    assert len(live) == 1
    answers = {
        SITE_ALL: FX.answer(
            SITE_ALL,
            [
                FX.keep(1, FX.Q_COMPLEX, note="the page does not contradict it"),
                FX.keep(2, FX.Q_DATE, note="the reported page says 2500 BC for the burial"),
                FX.keep(3, FX.Q_ZAMMIT),
            ],
        ),
        SITE_NONE: FX.answer(SITE_NONE, [FX.drop(1, "contradicted", FX.Q_DATE)]),
    }
    FX.record_answers(handoff, answers, by="adversarial:opus-check-r1", model=OH.OPUS_MODEL)
    C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    FX.verify_all(run, tmp_path / "handoff" / "adv-verify")
    summary = C.cmd_build(run, first_batch=4101)
    assert summary["not_planned"] == {"defect-kept": [SITE_ALL]}
    assert summary["defects_kept"].keys() == {SITE_ALL}  # SITE_NONE's claim is resolved by the drop

    record = C.cmd_defect_closure(run)
    assert [r["site_id"] for r in record["resolved"]] == [SITE_NONE]
    assert (
        record["resolved"][0]["reason"] == "contradicted" and record["resolved"][0]["sentence"] == 1
    )
    (refuted,) = record["refuted"]
    assert refuted["site_id"] == SITE_ALL and refuted["sentence"] is None
    assert refuted["claim"] == "They are not Maltese"
    assert [v["stage"] for v in refuted["verifiers"]] == ["verify"]
    text = C.closure_markdown(record)
    assert "1 claim(s) resolved by a drop, 1 refuted (defect line closed)" in text
    assert f"REFUTED Tarxien All ({SITE_ALL})" in text and "RESOLVED" in text
    with pytest.raises(C.WcRunError, match="a closure is written once"):
        C.cmd_defect_closure(run)


def test_a_closure_is_for_an_adversarial_run_only(built_defects) -> None:
    _, source, _ = built_defects
    with pytest.raises(C.WcRunError, match="not an adversarial second check"):
        C.cmd_defect_closure(source)


# ------------------------------------------------------------------------------ the MiniMax texts
def _restamp(handoff: Path, model: str = OH.MINIMAX_MODEL) -> int:
    """Re-stamp every answer of a handoff as MiniMax's: the state of what 2026-10-03 to
    2026-10-07 recorded, which the import no longer takes."""
    count = 0
    for path in handoff.rglob("*.answer.json"):
        stored = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**stored, "model": model}), encoding="utf-8")
        count += 1
    return count


def test_the_texts_minimax_shaped_and_that_still_stand_are_the_recheck_list(
    tmp_path: Path,
) -> None:
    wc_root, wn_root = tmp_path / "wc", tmp_path / "wn"
    wc_run, wc_plan = FX.build_run(wc_root, _rows(), _answers(), pilot=False, name="wc-02")
    wn_run, wn_plan = WX.build_wn_run(
        wn_root, [WX.wn_row(WX.SITE_N)], {WX.SITE_N: WX.good(WX.SITE_N)}, pilot=False
    )
    # the verification of the WC run was MiniMax's, the check was Opus's; the WN run was MiniMax's whole
    assert _restamp(wc_root / "handoff" / "wc-02-verify") == 2
    assert _restamp(wn_root / "handoff" / "wn-test-w") == 1
    assert _restamp(wn_root / "handoff" / "wn-test-verify") == 1
    fresh = _fresh_rows(wc_plan, _rows()) + _fresh_rows(wn_plan, [WX.wn_row(WX.SITE_N)])
    run = _read(tmp_path, fresh)
    out = tmp_path / "minimax.txt"
    report = C.cmd_minimax_sites(run, [wc_run, wn_run], out)
    # site C kept nothing (never verified), so it was never MiniMax's; A and B and the WN site were
    assert out.read_text(encoding="utf-8").split() == sorted([FX.SITE_A, FX.SITE_B, WX.SITE_N])
    assert report["touched"] == 3 and report["sites"] == 3 and report["others"] == {}


@pytest.mark.parametrize(
    "reason",
    ["cleared", "rewritten-run", "rewritten-text", "retired", "not-a-curated-row"],
)
def test_a_minimax_text_that_is_gone_or_was_replaced_is_reported_and_not_asked_again(
    tmp_path: Path, reason: str
) -> None:
    root = tmp_path / "wc"
    run0, plan = FX.build_run(root, _rows(), _answers(), pilot=False, name="wc-02")
    _restamp(root / "handoff" / "wc-02-verify")
    by_id = {r["id"]: r for r in _fresh_rows(plan, _rows())}
    site = by_id[FX.SITE_B]
    check = site["raw_data"][WC4.CHECK_KEY]
    name = "Hal Saflieni"
    changed = {
        # no description now (lane WN's to write again)
        "cleared": FX.row(FX.SITE_B, None, raw_data=None, name=name),
        # another run's check record: another lane or run wrote the text since
        "rewritten-run": FX.row(
            FX.SITE_B,
            site["description"],
            raw_data={**site["raw_data"], WC4.CHECK_KEY: {**check, "run": "another-run"}},
            name=name,
        ),
        # the record names this run but not the text that stands
        "rewritten-text": FX.row(
            FX.SITE_B, site["description"] + " More.", raw_data=site["raw_data"], name=name
        ),
        "retired": FX.row(
            FX.SITE_B,
            site["description"],
            raw_data=site["raw_data"],
            scope_status="retired",
            name=name,
        ),
    }
    if reason == "not-a-curated-row":
        del by_id[FX.SITE_B]
    else:
        by_id[FX.SITE_B] = changed[reason]
    run = _read(tmp_path, list(by_id.values()))
    report = C.cmd_minimax_sites(run, [run0], tmp_path / "m.txt")
    wanted = "rewritten-since" if reason.startswith("rewritten") else reason
    assert report["touched"] == 2 and report["sites"] == 1  # A still holds the text
    assert report["others"] == {wanted: [FX.SITE_B]}
    assert (tmp_path / "m.txt").read_text(encoding="utf-8").split() == [FX.SITE_A]


def test_a_claude_answered_run_has_no_minimax_text(tmp_path: Path) -> None:
    root = tmp_path / "wc"
    run0, plan = FX.build_run(root, _rows(), _answers(), pilot=False, name="wc-03")
    run = _read(tmp_path, _fresh_rows(plan, _rows()))
    report = C.cmd_minimax_sites(run, [run0], tmp_path / "m.txt")
    assert (report["touched"], report["sites"]) == (0, 0)


# ------------------------------------------------------------------------------ the WN rerun
def test_the_wn_question_names_the_sites_english_wikipedia_title_and_wikidata_item(
    tmp_path: Path,
) -> None:
    """D22: a site that is empty is asked again with what identifies its Wikipedia article."""
    run = tmp_path / "wn"
    run.mkdir()
    C.cmd_read(run, runner=FX.ReadRunner([WX.wn_row(WX.SITE_N)]))
    handoff = tmp_path / "wn-w"
    C.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None, wn=True)
    (line,) = OH.manifest(handoff)
    prompt = (handoff / line["prompt_path"]).read_text(encoding="utf-8")
    assert "Wikidata item: Q1195938" in prompt
    assert "English Wikipedia title: Tarxien Temples" in prompt


def test_the_sites_a_wc_check_cleared_are_in_the_wn_rerun_and_a_stale_key_is_not(
    tmp_path: Path,
) -> None:
    """A cleared site holds no WC key (the check cleared its record with its text), so lane WN asks
    it; a description-less site that still carries one is a broken state of another lane."""
    cleared = FX.row(FX.SITE_A, None, raw_data=None)
    never = FX.row(FX.SITE_B, "   ", raw_data=None)
    stale = FX.row(FX.SITE_C, None, raw_data={WC4.CHECK_KEY: {"v": 2}})
    has_text = FX.row(FX.SITE_D, "A text stands here.", raw_data=None)
    asked, listed = C.population(
        [cleared, never, stale, has_text], excluded=set(), earlier=set(), kind=C.KIND_WN
    )
    assert [e["site_id"] for e in asked] == [FX.SITE_A, FX.SITE_B]
    assert listed == {"stale-keys": [FX.SITE_C], "has-description": [FX.SITE_D]}


def test_a_run_is_read_against_the_tree_it_was_recorded_in(tmp_path: Path) -> None:
    """The WN pilot lives in another worktree than the mass runs: `<tree>/output/remediation/wc_runner/
    runs/<name>` records its handoffs relative to its own tree, any other run against the default."""
    tree = tmp_path / "other-tree"
    run = tree / "output" / "remediation" / "wc_runner" / "runs" / "wn-x"
    run.mkdir(parents=True)
    default = tmp_path / "default"
    assert C._tree_of(run, default) == tree.resolve()
    assert C._tree_of(tmp_path / "runs" / "wc-x", default) == default


def test_a_round_whose_handoff_is_missing_stops_the_recheck_list(tmp_path: Path) -> None:
    """A list built without a round's answers would leave out the texts they shaped, silently."""
    root = tmp_path / "wc"
    run0, plan = FX.build_run(root, _rows(), _answers(), pilot=False, name="wc-02")
    _restamp(root / "handoff" / "wc-02-verify")
    run = _read(tmp_path, _fresh_rows(plan, _rows()))
    shutil.rmtree(root / "handoff" / "wc-02-verify")
    with pytest.raises(C.WcRunError, match="one of its rounds is not there"):
        C.cmd_minimax_sites(run, [run0], tmp_path / "m.txt")
