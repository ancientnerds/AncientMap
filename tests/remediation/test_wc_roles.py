"""Lane WC answers by role (owner decision D6, 2026-10-08): the check rounds and lane WN's write
round are the fact checker's (Sonnet, high), the verification rounds the web verifier's (Sonnet,
high), the judge the pilot judge's (Opus, xhigh), the adversarial second check of a standing defect
the adversarial role's (Opus, high). A brief takes its model, role and agent family from
`roles.ROLES`; an import accepts only a Claude answer given in the round's role; a chunk is judged
by a sample (`judge-export --sample N --seed S`) that never approves a plan.

The briefs' texts are pinned in `test_wc.py` and `test_wn.py`. No socket, no model, no database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import roles as RO  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from wc import cli as C  # noqa: E402
from wc import prompts as P  # noqa: E402
from wc import prompts_sonnet as P2  # noqa: E402

from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation import wn_fixtures as WX  # noqa: E402
from tests.remediation.test_wc import _judgement, _run  # noqa: E402
from tests.remediation.test_wc_verify import _answers, _checked, _hv, _rows  # noqa: E402
from tests.remediation.wc_fixtures import OH, M, wiki_cache  # noqa: E402,F401

#: A Phase-4 text the check keeps whole and one it keeps in part (`test_wc_list`).
SITE_KEPT = "2b000000-0000-4000-8000-00000000002b"
SITE_PART = "2a000000-0000-4000-8000-00000000002a"


def _no_braces_left(text: str) -> None:
    assert "{family}" not in text and "{model}" not in text and "{role}" not in text
    assert "{wiki_cache_note}" not in text and "{wiki_cache}" not in text


# ------------------------------------------------------------------------------ the briefs
def test_the_check_brief_is_the_fact_checkers_and_names_the_registry_model_and_role(
    tmp_path: Path,
) -> None:
    run, handoff = _run(tmp_path)
    text = C.brief(run, handoff, "wc-0002")
    entry = RO.role("fact_checker")
    assert (entry.model, entry.effort) == ("claude-sonnet-5-5", "high")
    assert "You are Sonnet checker wc-0002" in text
    assert f"--model {entry.model} --role fact_checker" in text
    assert "--answered-by sonnet-check-r1-wc-0002" in text
    _no_braces_left(text)
    assert "claude-opus-5-5" not in text and "<the model id" not in text


def test_every_brief_sends_the_agent_to_the_shared_wikipedia_cache_first(tmp_path: Path) -> None:
    run, handoff = _run(tmp_path)
    cache = C._shown(C.WIKI_CACHE)
    note = P.WIKI_CACHE_NOTE.format(wiki_cache=cache)
    run_v = _checked(tmp_path / "v")
    C.cmd_verify_export(run_v, _hv(tmp_path / "v"), batch_size=5)
    for text in (
        C.brief(run, handoff, "wc-0001"),
        C.verify_brief(run_v, _hv(tmp_path / "v"), "verify-0001"),
    ):
        assert note in text
        assert "the Wikipedia cache named below is the one exception" in text
        assert "A 403 or 429" not in text and "HTTP 403 or 429 is never a finding" in text
    assert cache.startswith(str(tmp_path)) or cache.endswith("wiki_cache")


def test_the_cache_the_briefs_name_is_the_one_the_fetcher_fills(monkeypatch) -> None:
    monkeypatch.undo()
    assert C.WIKI_CACHE == REPO / "output" / "remediation" / "final-2026-10-08" / "wiki_cache"
    assert C._shown(C.WIKI_CACHE) == "output/remediation/final-2026-10-08/wiki_cache"


def test_a_brief_refuses_to_send_an_agent_to_a_cache_that_is_not_there(
    tmp_path: Path,
    wiki_cache: Path,  # noqa: F811
) -> None:
    run, handoff = _run(tmp_path)
    (wiki_cache / "INDEX.jsonl").unlink()
    with pytest.raises(C.WcRunError, match="shared Wikipedia cache is missing"):
        C.brief(run, handoff, "wc-0001")


def test_the_verify_brief_is_the_web_verifiers_and_the_judge_brief_the_pilot_judges(
    tmp_path: Path,
) -> None:
    run = _checked(tmp_path)
    C.cmd_verify_export(run, _hv(tmp_path), batch_size=5)
    verify = C.verify_brief(run, _hv(tmp_path), "verify-0001")
    assert "You are Sonnet verifier verify-0001" in verify
    assert "--model claude-sonnet-5-5 --role web_verifier" in verify
    assert "--answered-by sonnet-wc-verify-0001" in verify
    _no_braces_left(verify)
    built = FX.build_run(tmp_path / "b", _rows(), _answers(), pilot=True, judged=False)[0]
    handoff = tmp_path / "b" / "handoff" / "judge"
    C.cmd_judge_export(built, handoff, batch_size=5)
    judge = C.judge_brief(built, handoff, "judge-0001")
    assert "You are Opus judge judge-0001" in judge
    assert "--model claude-opus-5-5 --role pilot_judge" in judge
    assert "--answered-by opus-wc-judge-judge-0001" in judge
    _no_braces_left(judge)
    assert RO.role("pilot_judge").effort == "xhigh"


def test_the_write_brief_of_lane_wn_is_the_fact_checkers_too(tmp_path: Path) -> None:
    """No writer role is registered: the web research that writes a sentence on a quote is the fact
    checker's (Sonnet, high)."""
    run = tmp_path / "wn"
    run.mkdir()
    C.cmd_read(run, runner=FX.ReadRunner([WX.wn_row(WX.SITE_N)]))
    handoff = tmp_path / "wn-w"
    C.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None, wn=True)
    text = C.brief(run, handoff, "wn-0001")
    assert "You are Sonnet writer wn-0001" in text
    assert (
        "--answered-by sonnet-write-wn-0001 --model claude-sonnet-5-5 --role fact_checker" in text
    )
    _no_braces_left(text)
    assert P.WIKI_CACHE_NOTE.format(wiki_cache=C._shown(C.WIKI_CACHE)) in text


# ------------------------------------------------------------------------------ the imports
def _record(handoff: Path, answers: dict[str, str], *, by: str, model: str) -> None:
    FX.record_answers(handoff, answers, by=by, model=model)


def test_a_minimax_check_answer_is_never_imported(tmp_path: Path) -> None:
    run, handoff = tmp_path / "runs" / "wc-test", tmp_path / "handoff" / "wc-test-r1"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=FX.ReadRunner(_rows()))
    C.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None)
    _record(handoff, _answers(), by="opus-check", model=OH.MINIMAX_MODEL)
    with pytest.raises(C.WcRunError, match="answered by MiniMax.*never imported"):
        C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert not (run / "round-1" / "ANSWERS.jsonl").exists()


def test_a_minimax_verification_answer_is_never_imported_and_verify_void_is_the_way_back(
    tmp_path: Path,
) -> None:
    run = _checked(tmp_path)
    handoff = _hv(tmp_path)
    C.cmd_verify_export(run, handoff, batch_size=5)
    answers = {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    }
    _record(handoff, answers, by="opus-verify", model=OH.MINIMAX_MODEL)
    with pytest.raises(C.WcRunError, match="verify-void"):
        C.cmd_verify_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert not (run / "verify" / "round-1" / "VERIFIED.jsonl").exists()


def test_a_minimax_judge_answer_is_never_imported(tmp_path: Path) -> None:
    run = FX.build_run(tmp_path, _rows(), _answers(), pilot=True, judged=False)[0]
    handoff = tmp_path / "handoff" / "judge"
    C.cmd_judge_export(run, handoff, batch_size=5)
    answers = {
        site_id: json.dumps(
            {
                "site_id": site_id,
                "kept": [
                    {"k": k, "verdict": "SUPPORTED", "quotes": [], "note": "judged"}
                    for k in range(1, C._judge_counts(final)[0] + 1)
                ],
                "dropped": [
                    {"d": d, "verdict": "DROP_OK", "quotes": [], "note": "judged"}
                    for d in range(1, C._judge_counts(final)[1] + 1)
                ],
                "coherent": True,
                "note": "judged",
            }
        )
        for site_id, final in C._finals(run).items()
    }
    _record(handoff, answers, by="opus-judge", model=OH.MINIMAX_MODEL)
    with pytest.raises(C.WcRunError, match="never imported"):
        C.cmd_judge_import(run, handoff, client=FX.FakeClient(), pace=0.0)


@pytest.mark.parametrize(
    ("by", "model", "match"),
    [
        ("web_verifier:sonnet-check-r1", OH.SONNET_MODEL, "was given in role web_verifier"),
        ("pilot_judge:opus-check-r1", OH.OPUS_MODEL, "was given in role pilot_judge"),
        ("fact_checker:sonnet-check-r1", OH.OPUS_MODEL, "registered to claude-sonnet-5-5"),
    ],
)
def test_a_check_answer_given_in_another_role_or_under_another_stamp_is_refused(
    tmp_path: Path, by: str, model: str, match: str
) -> None:
    run, handoff = tmp_path / "runs" / "wc-test", tmp_path / "handoff" / "wc-test-r1"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=FX.ReadRunner(_rows()))
    C.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None)
    _record(handoff, _answers(), by=by, model=model)
    with pytest.raises(C.WcRunError, match=match):
        C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)


def test_an_answer_in_the_rounds_own_role_imports_and_so_does_a_legacy_unnamed_claude_answer(
    tmp_path: Path,
) -> None:
    run, handoff = tmp_path / "runs" / "wc-test", tmp_path / "handoff" / "wc-test-r1"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=FX.ReadRunner(_rows()))
    C.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None)
    answers = _answers()
    _record(
        handoff,
        {FX.SITE_A: answers[FX.SITE_A]},
        by="fact_checker:sonnet-check-r1",
        model=OH.SONNET_MODEL,
    )
    rest = {k: v for k, v in answers.items() if k != FX.SITE_A}
    _record(handoff, rest, by="opus-check", model=OH.OPUS_MODEL)  # recorded before the registry
    assert C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)["answers"] == 3
    rows = read_jsonl(run / "round-1" / "ANSWERS.jsonl")
    assert {r["answered_by"] for r in rows} >= {"fact_checker:sonnet-check-r1-wc-0001"}


# ------------------------------------------------------------------------------ the adversary
def _p4_rows() -> list[dict]:
    return [
        FX.row(SITE_KEPT, WX.P4_TEXT, raw_data=WX.p4_site_raw(), name="Tarxien Kept"),
        FX.row(SITE_PART, WX.P4_TEXT, raw_data=WX.p4_site_raw(), name="Tarxien Part"),
    ]


def _defect(site_id: str, sha: str, **change) -> dict:
    line = {
        "basis": "W", "candidates": [], "claim": "They date to 3150 BC", "desc_sha256": sha,
        "mapped_by": "m", "name": "x", "owner_lane": "WA", "proven": True,
        "quote": "The temples date from 2500 BC.", "quote_outcome": "found", "run": "wb-1",
        "sentence": 2, "sentence_text": WX.P4_SENTENCES[1], "site_id": site_id, "stage": "verify",
        "url": FX.WIKI, "verifier": "v",
    }  # fmt: skip
    return {**line, **change}


def _adversarial_export(tmp_path: Path, **change):
    run = tmp_path / "runs" / "adv"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=FX.ReadRunner(_p4_rows()))
    sha = M.text_sha256(WX.P4_TEXT)
    found = tmp_path / "d.jsonl"
    found.write_text(json.dumps(_defect(SITE_KEPT, sha)) + "\n", encoding="utf-8")
    listing = tmp_path / "list.txt"
    C.cmd_defect_sites(run, [found], listing)
    options = {
        "batch_size": 5, "exclude": None, "after": [], "pilot": None, "seed": None,
        "sites": listing, "defects": listing.with_name("list.txt.report.json"),
        "adversarial": True,
    }  # fmt: skip
    handoff = tmp_path / "handoff" / "adv-r1"
    return run, handoff, C.cmd_export(run, handoff, **{**options, **change})


def test_an_adversarial_run_asks_the_adversarial_question_and_is_answered_in_that_role(
    tmp_path: Path,
) -> None:
    run, handoff, summary = _adversarial_export(tmp_path)
    assert C.run_kind(run) == C.KIND_LIST and C.run_adversarial(run) is True
    assert json.loads((run / C.POPULATION_FILE).read_text("utf-8"))["adversarial"] is True
    (line,) = OH.manifest(handoff)
    prompt = (handoff / line["prompt_path"]).read_text(encoding="utf-8")
    assert prompt.startswith(P2.ADVERSARIAL_OPENING)
    assert "A LATER WEB CHECK REPORTED A CLAIM OF THIS DESCRIPTION CONTRADICTED" in prompt
    assert "THIS TEXT IS NOT TRIMMED" in prompt  # the Phase-4 rule is still there
    text = C.brief(run, handoff, "wc-0001")
    assert "You are Opus checker wc-0001" in text
    assert "--model claude-opus-5-5 --role adversarial" in text
    assert "--answered-by opus-check-r1-wc-0001" in text
    assert RO.role("adversarial").effort == "high"


def test_a_plain_list_run_does_not_ask_the_adversarial_question(tmp_path: Path) -> None:
    run, handoff, _ = _adversarial_export(tmp_path / "a")
    plain_run, plain_handoff, _ = _adversarial_export(tmp_path / "p", adversarial=False)
    (line,) = OH.manifest(plain_handoff)
    prompt = (plain_handoff / line["prompt_path"]).read_text(encoding="utf-8")
    assert P2.ADVERSARIAL_OPENING not in prompt and prompt.startswith("You check one site")
    assert C.run_adversarial(plain_run) is False and "--role fact_checker" in C.brief(
        plain_run, plain_handoff, "wc-0001"
    )


def test_the_adversarial_export_needs_a_report_and_is_no_pilot_and_no_wn_run(
    tmp_path: Path,
) -> None:
    with pytest.raises(C.WcRunError, match="goes with --defects"):
        _adversarial_export(tmp_path / "a", defects=None)
    with pytest.raises(C.WcRunError, match="no --wn, no --pilot"):
        _adversarial_export(tmp_path / "b", pilot=1, seed=3)
    with pytest.raises(C.WcRunError, match="no --wn, no --pilot"):
        _adversarial_export(tmp_path / "c", wn=True)


@pytest.mark.parametrize(
    ("by", "model", "match"),
    [
        ("opus-check-r1", OH.OPUS_MODEL, "names no role"),
        ("fact_checker:sonnet-check-r1", OH.SONNET_MODEL, "was given in role fact_checker"),
        ("adversarial:opus-check-r1", OH.SONNET_MODEL, "registered to claude-opus-5-5"),
    ],
)
def test_only_the_adversarial_role_answers_an_adversarial_check(
    tmp_path: Path, by: str, model: str, match: str
) -> None:
    run, handoff, _ = _adversarial_export(tmp_path)
    answer = FX.answer(SITE_KEPT, [FX.keep(1, FX.Q_COMPLEX), FX.drop(2), FX.keep(3, FX.Q_ZAMMIT)])
    _record(handoff, {SITE_KEPT: answer}, by=by, model=model)
    with pytest.raises(C.WcRunError, match=match):
        C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)


# ------------------------------------------------------------------------------ the sampled judge
def _chunk(tmp_path: Path) -> Path:
    return FX.build_run(tmp_path, _rows(), _answers(), pilot=False)[0]


def _judge_answers(run: Path) -> dict[str, str]:
    answers = {}
    for site_id, final in C._finals(run).items():
        kept, dropped = C._judge_counts(final)
        answers[site_id] = json.dumps(
            {
                "site_id": site_id,
                "kept": [
                    {"k": k, "verdict": "SUPPORTED", "quotes": [], "note": "judged"}
                    for k in range(1, kept + 1)
                ],
                "dropped": [
                    {"d": d, "verdict": "DROP_OK", "quotes": [], "note": "judged"}
                    for d in range(1, dropped + 1)
                ],
                "coherent": True,
                "note": "judged",
            }
        )
    return answers


def test_a_chunk_is_judged_by_a_seeded_sample_and_the_result_records_the_draw(
    tmp_path: Path,
) -> None:
    run = _chunk(tmp_path)
    first = C.cmd_judge_export(run, tmp_path / "j1", batch_size=5, sample=2, seed=11)
    assert first["questions"] == 2 and first["sample"] == {"sites": 2, "seed": 11, "of": 3}
    record = json.loads((run / "judge" / "ROUND.json").read_text(encoding="utf-8"))
    asked = sorted(label for labels in record["batches"].values() for label in labels)
    assert len(asked) == 2 and record["sample"] == first["sample"]
    again = tmp_path / "again"
    shutil_copy = FX.build_run(again, _rows(), _answers(), pilot=False)[0]
    C.cmd_judge_export(shutil_copy, again / "j", batch_size=5, sample=2, seed=11)
    other = json.loads((shutil_copy / "judge" / "ROUND.json").read_text(encoding="utf-8"))
    assert sorted(l for ls in other["batches"].values() for l in ls) == asked  # the seed decides
    FX.record_answers(
        tmp_path / "j1",
        {label: answer for label, answer in _judge_answers(run).items() if label in asked},
        by="opus-judge",
    )
    result = C.cmd_judge_import(run, tmp_path / "j1", client=FX.FakeClient(), pace=0.0)
    assert result["passed"] is True and result["sample"] == record["sample"]
    assert result["measured"]["sites"] == 2


def test_a_whole_judge_records_no_sample(tmp_path: Path) -> None:
    run = _chunk(tmp_path)
    summary = C.cmd_judge_export(run, tmp_path / "j", batch_size=5)
    assert summary["questions"] == 3 and summary["sample"] is None
    FX.record_answers(tmp_path / "j", _judge_answers(run), by="opus-judge")
    assert "sample" not in C.cmd_judge_import(run, tmp_path / "j", client=FX.FakeClient(), pace=0.0)


@pytest.mark.parametrize(
    ("kw", "match"),
    [
        ({"sample": 2}, "go together"),
        ({"seed": 2}, "go together"),
        ({"sample": 4, "seed": 1}, "a sample of 4 from 3 judgeable"),
        ({"sample": 0, "seed": 1}, "a sample of 0 from 3 judgeable"),
    ],
)
def test_a_sample_needs_its_seed_and_fits_the_chunk(tmp_path: Path, kw: dict, match: str) -> None:
    with pytest.raises(C.WcRunError, match=match):
        C.cmd_judge_export(_chunk(tmp_path), tmp_path / "j", batch_size=5, **kw)


def test_a_pilot_is_judged_whole_and_a_sampled_verdict_approves_no_plan(tmp_path: Path) -> None:
    run, plan = FX.build_run(tmp_path, _rows(), _answers(), pilot=True, judged=False)
    with pytest.raises(C.WcRunError, match="a pilot is judged whole"):
        C.cmd_judge_export(run, tmp_path / "j", batch_size=5, sample=2, seed=1)
    assert not (run / "judge" / "ROUND.json").exists()
    # a judged pilot whose result was marked as a sample (by hand) approves nothing
    FX.judge_all(run, tmp_path / "jw")
    result_path = run / "judge" / "RESULT.json"
    assert C.pilot_approval([plan])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result_path.write_text(json.dumps({**result, "sample": {"sites": 1}}), encoding="utf-8")
    with pytest.raises(C.WcRunError, match="a sampled verdict approves no plan"):
        C.pilot_approval([plan])


def _list_chunk(root: Path) -> Path:
    keeps_all = FX.answer(
        SITE_KEPT, [FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE), FX.keep(3, FX.Q_ZAMMIT)]
    )
    drops = FX.answer(SITE_PART, [FX.keep(1, FX.Q_COMPLEX), FX.drop(2), FX.drop(3)])
    return WX.build_list_run(
        root, _p4_rows(), [SITE_KEPT, SITE_PART], {SITE_KEPT: keeps_all, SITE_PART: drops},
        name="wcl-sample",
    )[0]  # fmt: skip


def test_a_sample_leaves_out_the_sites_a_list_run_does_not_write(tmp_path: Path) -> None:
    """A Phase-4 text whose check keeps every sentence is `unchanged` or `defect-kept`: nothing of
    it is written, so nothing of it is judged."""
    run = _list_chunk(tmp_path / "a")
    finals = C._finals(run)
    assert finals[SITE_KEPT]["planned"] is False and finals[SITE_PART]["planned"] is True
    summary = C.cmd_judge_export(run, tmp_path / "j", batch_size=5, sample=1, seed=1)
    assert summary["sample"]["of"] == 1
    (line,) = OH.manifest(tmp_path / "j")
    assert line["label"] == SITE_PART
    with pytest.raises(C.WcRunError, match="a sample of 2 from 1 judgeable"):
        C.cmd_judge_export(
            _list_chunk(tmp_path / "b"), tmp_path / "j2", batch_size=5, sample=2, seed=1
        )


def test_a_sampled_judge_of_a_wn_chunk_owes_no_pilot_minimum(tmp_path: Path) -> None:
    rows = [WX.wn_row(WX.SITE_N), WX.wn_row("1b000000-0000-4000-8000-00000000000b")]
    other = "1b000000-0000-4000-8000-00000000000b"
    run, _ = WX.build_wn_run(
        tmp_path,
        rows,
        {WX.SITE_N: WX.good(WX.SITE_N), other: WX.good(other)},
        pilot=False,
    )
    summary = C.cmd_judge_export(run, tmp_path / "j", batch_size=5, sample=1, seed=1)
    assert summary["questions"] == 1
    FX.record_answers(tmp_path / "j", {k: v for k, v in _judge_answers(run).items()
                                       if k in {line["label"] for line in OH.manifest(tmp_path / "j")}},
                      by="opus-judge")  # fmt: skip
    result = C.cmd_judge_import(run, tmp_path / "j", client=FX.FakeClient(), pace=0.0)
    assert result["passed"] is True and "minimum" not in result["measured"]


def test_the_command_line_takes_the_new_options() -> None:
    parser = C.build_parser()
    judge = parser.parse_args(
        ["judge-export", "--run-dir", "r", "--handoff", "h", "--sample", "55", "--seed", "9"]
    )
    assert (judge.sample, judge.seed) == (55, 9)
    export = parser.parse_args(
        [
            "export",
            "--run-dir",
            "r",
            "--handoff",
            "h",
            "--sites",
            "f",
            "--defects",
            "d",
            "--adversarial",
        ]
    )
    assert export.adversarial is True
    assert parser.parse_args(["export", "--run-dir", "r", "--handoff", "h"]).adversarial is False


# ------------------------------------------------------------------------------ the role is named
NEW = "2026-10-09T09:00:00+00:00"  # after the registry (2026-10-08)


def _check_round(tmp_path: Path) -> tuple[Path, Path]:
    run, handoff = tmp_path / "runs" / "wc-test", tmp_path / "handoff" / "wc-test-r1"
    run.mkdir(parents=True)
    C.cmd_read(run, runner=FX.ReadRunner(_rows()))
    C.cmd_export(run, handoff, batch_size=5, exclude=None, after=[], pilot=None, seed=None)
    return run, handoff


@pytest.mark.parametrize("model", [OH.HAIKU_MODEL, OH.SONNET_MODEL, OH.OPUS_MODEL])
def test_an_answer_given_now_names_the_rounds_role_whatever_its_model(
    tmp_path: Path, model: str
) -> None:
    """Without `--role` a Haiku answer could enter any round: the stamp was never compared."""
    run, handoff = _check_round(tmp_path)
    FX.record_answers(handoff, _answers(), by="anyname-wc", model=model, at=NEW)
    with pytest.raises(C.WcRunError, match="names no role.*answer --role fact_checker"):
        C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert not (run / "round-1" / "ANSWERS.jsonl").exists()


def test_the_verification_and_the_judge_name_their_role_from_the_registry_day_on(
    tmp_path: Path,
) -> None:
    run = _checked(tmp_path)
    handoff = _hv(tmp_path)
    C.cmd_verify_export(run, handoff, batch_size=5)
    answers = {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    }
    FX.record_answers(handoff, answers, by="anyname", model=OH.HAIKU_MODEL, at=NEW)
    with pytest.raises(C.WcRunError, match="names no role.*answer --role web_verifier"):
        C.cmd_verify_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    pilot = FX.build_run(tmp_path / "j", _rows(), _answers(), pilot=True, judged=False)[0]
    judge = tmp_path / "handoff" / "judge"
    C.cmd_judge_export(pilot, judge, batch_size=5)
    FX.record_answers(judge, _judge_answers(pilot), by="anyname", model=OH.SONNET_MODEL, at=NEW)
    with pytest.raises(C.WcRunError, match="names no role.*answer --role pilot_judge"):
        C.cmd_judge_import(pilot, judge, client=FX.FakeClient(), pace=0.0)


# ------------------------------------------------------------------------ one agent, one role
def test_one_agent_cannot_check_and_then_verify_the_same_site_under_two_role_prefixes(
    tmp_path: Path,
) -> None:
    run, handoff = _check_round(tmp_path)
    FX.record_answers(handoff, _answers(), by="fact_checker:agent-7", model=OH.SONNET_MODEL, at=NEW)
    C.cmd_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    verify = tmp_path / "handoff" / "wc-test-verify"
    C.cmd_verify_export(run, verify, batch_size=5)
    answers = {
        FX.SITE_A: FX.verification(FX.SITE_A, ["SUPPORTED"] * 3),
        FX.SITE_B: FX.verification(FX.SITE_B, ["SUPPORTED"] * 2),
    }
    FX.record_answers(verify, answers, by="web_verifier:agent-7", model=OH.SONNET_MODEL, at=NEW)
    # the checkers are fact_checker:agent-7-wc-0001; this verifier is the same agent in another role
    for line in OH.manifest(verify):
        path = verify / line["answer_path"]
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["answered_by"] = "web_verifier:agent-7-wc-0001"
        path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(C.WcRunError, match="checked or verified this site before"):
        C.cmd_verify_import(run, verify, client=FX.FakeClient(), pace=0.0)
    assert not (run / "verify" / "round-1" / "VERIFIED.jsonl").exists()


def test_a_judge_who_is_a_checker_under_another_role_prefix_is_not_independent(
    tmp_path: Path,
) -> None:
    run = FX.build_run(tmp_path, _rows(), _answers(), pilot=True, judged=False)[0]
    handoff = tmp_path / "handoff" / "judge"
    C.cmd_judge_export(run, handoff, batch_size=5)
    # the checkers answered as `opus-check-wc-0001` (recorded before the registry)
    FX.record_answers(handoff, _judge_answers(run), by="pilot_judge:x", model=OH.OPUS_MODEL, at=NEW)
    for line in OH.manifest(handoff):
        path = handoff / line["answer_path"]
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["answered_by"] = "pilot_judge:opus-check-wc-0001"
        path.write_text(json.dumps(stored), encoding="utf-8")
    result = C.cmd_judge_import(run, handoff, client=FX.FakeClient(), pace=0.0)
    assert result["measured"]["independent"] == 0
    assert any("judged by a checker or verifier of the run" in f for f in result["failures"])


# ------------------------------------------------------- a chunk is written after its sampled judge
def _approved_chunk(tmp_path: Path) -> tuple[Path, Path, Path]:
    pilot = FX.build_run(tmp_path / "p", _rows(), _answers(), pilot=True)[1]
    run, plan = FX.build_run(tmp_path / "c", _rows(), _answers(), pilot=False)
    return pilot, run, plan


def _sample_answers(run: Path, handoff: Path, *, wrong: bool) -> dict[str, str]:
    record = json.loads((run / "judge" / "ROUND.json").read_text(encoding="utf-8"))
    asked = {label for labels in record["batches"].values() for label in labels}
    answers = {label: a for label, a in _judge_answers(run).items() if label in asked}
    if wrong:
        counts = {label: C._judge_counts(C._finals(run)[label]) for label in sorted(asked)}
        label = next(label for label, (kept, _) in counts.items() if kept)
        kept, dropped = counts[label]
        answers[label] = _judgement(
            label, ["SUPPORTED"] * (kept - 1) + ["WRONG"], ["DROP_OK"] * dropped
        )
    return answers


def test_a_chunk_whose_sampled_judge_is_unanswered_failed_or_for_another_plan_is_not_written(
    tmp_path: Path,
) -> None:
    pilot, run, plan = _approved_chunk(tmp_path)
    assert len(C.pilot_approval([pilot, plan])) == 1  # no judge round: the sample is the operator's
    handoff = tmp_path / "handoff" / "sample"
    C.cmd_judge_export(run, handoff, batch_size=5, sample=2, seed=3)
    with pytest.raises(C.WcRunError, match="exported and not imported"):
        C.pilot_approval([pilot, plan])
    FX.record_answers(handoff, _sample_answers(run, handoff, wrong=True), by="opus-judge")
    assert C.cmd_judge_import(run, handoff, client=FX.FakeClient(), pace=0.0)["passed"] is False
    with pytest.raises(C.WcRunError, match="sampled judge did not pass"):
        C.pilot_approval([pilot, plan])


def test_a_chunk_whose_sampled_judge_passed_on_this_plan_is_written_and_only_this_plan(
    tmp_path: Path,
) -> None:
    pilot, run, plan = _approved_chunk(tmp_path)
    handoff = tmp_path / "handoff" / "sample"
    C.cmd_judge_export(run, handoff, batch_size=5, sample=2, seed=3)
    FX.record_answers(handoff, _sample_answers(run, handoff, wrong=False), by="opus-judge")
    assert C.cmd_judge_import(run, handoff, client=FX.FakeClient(), pace=0.0)["passed"] is True
    assert len(C.pilot_approval([pilot, plan])) == 1
    result_path = run / "judge" / "RESULT.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result_path.write_text(json.dumps({**result, "plan_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(C.WcRunError, match="not the plan the sampled judge judged"):
        C.pilot_approval([pilot, plan])
