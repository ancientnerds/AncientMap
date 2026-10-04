"""The four studio checks, answered by `mcode exec` (pipeline/studio/mcode_checks.py).

These tests replace the node harness of the four Claude Code workflow scripts. A fake
`mcode.exec` plays the role of the model: it reads the two lines every prompt carries (the
answer file and the validator command), writes the scripted answer to the file the prompt
names and returns a run the way `mcode exec` does. Nothing here calls MiniMax.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import tests.pipeline.studio.episode_fixtures as ef
import tests.pipeline.studio.fixtures as fx
from pipeline.studio import handoff, mcode, mcode_checks
from pipeline.studio.errors import StudioError
from pipeline.studio.paper import claims, images
from pipeline.studio.paper.workspace import read_json, write_json
from tests import git_env

LIVE_QUOTE = "Roman engineers moved the largest blocks on sledges."
TDM_URL = "https://publisher.example/paywalled"
VENV_STUDIO = "./.venv/Scripts/python.exe -m pipeline.studio"


def _field(prompt: str, prefix: str, *, required: bool = True) -> str:
    for line in prompt.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    if required:
        raise AssertionError(f"the prompt has no {prefix!r} line:\n{prompt}")
    return ""


def _role(prompt: str) -> str:
    """Which run this prompt asks for. The verifier prompt mentions the skeptic, so the
    role is read from the first line, not from a word anywhere in it."""
    return "skeptic" if prompt.startswith("You are the adversarial skeptic") else "verifier"


class FakeMcode:
    """The model's side of one `mcode exec`: write the answer, return a run."""

    def __init__(self, answers: dict[tuple[str, str], dict[str, Any]]) -> None:
        self.answers = answers
        self.prompts: list[str] = []

    def __call__(self, prompt: str, *, cwd: Path, timeout: str = mcode.TIMEOUT) -> mcode.Run:
        self.prompts.append(prompt)
        role = _role(prompt)
        item = _field(prompt, "Task:", required=False) or _field(prompt, "Evidence item:").split(" ")[0]
        answer = self.answers.get((role, item), self.answers.get((role, "*")))
        if answer is not None:
            path = Path(_field(prompt, "Write your answer as one JSON object to this file:"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(answer), encoding="utf-8")
        run_id = f"run_{role}_{item}"
        result = {
            "type": "exec.result",
            "runId": run_id,
            "sessionId": "mvs_9d3d18599ba34b12a81cf4588ee799d0",
            "status": "succeeded",
            "output": "",
            "model": {"providerId": "minimax", "modelId": mcode.MODEL},
            "usage": {"inputTokens": 21001, "outputTokens": 40, "totalTokens": 21041},
            "durationMs": 10,
        }
        return mcode.Run(
            run_id=run_id,
            session_id=result["sessionId"],
            status="succeeded",
            model=mcode.MODEL,
            output="",
            duration_ms=10,
            input_tokens=21001,
            output_tokens=40,
            result=result,
        )

    def prompt_of(self, role: str, item: str) -> str:
        for prompt in self.prompts:
            if f"Task: {item}" in prompt and _role(prompt) == role:
                return prompt
        raise AssertionError(f"no {role} prompt for {item}")


def _install(monkeypatch, answers: dict[tuple[str, str], dict[str, Any]]) -> FakeMcode:
    fake = FakeMcode(answers)
    monkeypatch.setattr(mcode, "exec", fake)
    monkeypatch.setattr(mcode_checks.mcode, "exec", fake)
    monkeypatch.setattr(mcode, "weekly_stop", lambda: "")
    monkeypatch.setattr(mcode_checks.mcode, "weekly_stop", lambda: "")
    return fake


def _repo(tmp_path: Path) -> Path:
    """A git repository for the tracked-file guard: a clean tree with one tracked file.

    Every call runs with `env=git_env.own_env()`: the pre-push hook exports `GIT_DIR`, and
    it wins over `-C`, so without this the repository below is the branch being pushed
    (2026-10-03: the gate went red with 24 failures and the push was blocked).
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, env=git_env.own_env())
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True, env=git_env.own_env())
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a"],
        check=True,
        env=git_env.own_env(),
    )
    return repo


# --- claim check ------------------------------------------------------------------------------


def _tdm_workspace(tmp_path: Path):
    """The fixture paper with one paragraph that also cites the TDM-reserved S4."""
    draft = fx.build_draft().replace(
        "It is likely that Roman engineers moved the blocks [S:aaaaaaaaaaa1].",
        f"It is likely that Roman engineers moved the blocks [S:aaaaaaaaaaa1] [S:{fx.S4}].",
    )
    ws = fx.make_workspace(tmp_path, draft=draft)
    claims.export_claims(ws)
    rows = handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")
    return ws, next(r for r in rows if any(c["source_id"] == fx.S4 for c in r["cited"]))


def _supported(row) -> dict[str, Any]:
    return {
        "verdict": "supported",
        "quote": LIVE_QUOTE if row["kind"] != "coherence" else "",
        "quote_source_id": fx.S4 if row["kind"] != "coherence" else "",
        "explanation": "the source says so",
        "fix_suggestion": "",
    }


#: A verdict every claim task allows, coherence tasks included.
_unsupported = {
    "verdict": "unsupported",
    "quote": "",
    "quote_source_id": "",
    "explanation": "the source does not say it",
    "fix_suggestion": "name another source",
}


def _save_live(ws, body: str = LIVE_QUOTE, url: str = TDM_URL) -> None:
    path = ws.claims_dir / "live" / f"{fx.S4}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"URL: {url}\nFetched: 2026-10-03T12:00:00+00:00\n\n{body}\n", encoding="utf-8")


def test_a_supported_verdict_gets_its_own_independent_skeptic_run(tmp_path, monkeypatch):
    """O17/the plan: one run per task, and a `supported` answer a second run of its own -
    a fresh session, never the verifier's, so the skeptic cannot see the verifier's state
    beyond the answer it is asked to refute."""
    ws, row = _tdm_workspace(tmp_path)
    _save_live(ws)
    repo = _repo(tmp_path)
    fake = _install(
        monkeypatch,
        {
            ("verifier", "*"): {"verdict": "unsupported", "quote": "", "quote_source_id": "", "explanation": "the source does not say it", "fix_suggestion": "name another source"},
            ("verifier", row["task_id"]): _supported(row),
            ("skeptic", "*"): {"verdict": "supported", "explanation": "cannot refute", "fix_suggestion": ""},
        },
    )

    result = mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))

    assert result.answered == len(handoff.read_jsonl(ws.claims_dir / "tasks.jsonl"))
    (line,) = [r for r in handoff.read_jsonl(ws.claims_dir / "verdicts.jsonl") if r["task_id"] == row["task_id"]]
    assert line["verdict"] == "supported"
    assert f"{mcode.MODEL} (verifier, mcode exec, run_verifier_{row['task_id']}" in line["answered_by"]
    assert f"{mcode.MODEL} (skeptic, mcode exec, run_skeptic_" in line["skeptic_by"]
    assert line["answered_by"] != line["skeptic_by"]
    # the skeptic prompt names the verifier's answer and the files, not the session
    skeptic = fake.prompt_of("skeptic", row["task_id"])
    assert "Try hard to refute" in skeptic or "refute" in skeptic.lower()
    assert f"run_verifier_{row['task_id']}" not in skeptic


def test_every_stamp_can_be_checked_against_the_run_it_names(tmp_path, monkeypatch):
    """A stamp is only worth something if the run behind it can be read later.

    The plan asks for the real model and the real run id in `answered_by` / `skeptic_by`; on
    2026-10-03 all 55 stamps of the calibration named one, and none of the run ids was in the
    workspace - the answer file holds the verdict, not the `exec.result` the stamp is taken from.
    So the exec result is written beside the answer, per role.
    """
    ws, row = _tdm_workspace(tmp_path)
    _save_live(ws)
    repo = _repo(tmp_path)
    _install(
        monkeypatch,
        {
            ("verifier", row["task_id"]): _supported(row),
            ("skeptic", "*"): {"verdict": "supported", "explanation": "cannot refute", "fix_suggestion": ""},
        },
    )

    result = mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))

    (line,) = [r for r in handoff.read_jsonl(ws.claims_dir / "verdicts.jsonl") if r["task_id"] == row["task_id"]]
    assert result.answered >= 1
    for stamp, suffix in ((line["answered_by"], ""), (line["skeptic_by"], ".skeptic")):
        run_id = stamp.split("mcode exec, ")[1].split(",")[0]
        trace = ws.claims_dir / "mcode_runs" / f"{row['task_id']}{suffix}.exec.json"
        assert trace.is_file(), f"no exec result archived for {stamp}"
        evidence = json.loads(trace.read_text(encoding="utf-8"))
        assert evidence["runId"] == run_id
        assert evidence["model"]["modelId"] == mcode.MODEL
        assert evidence["type"] == "exec.result"


def test_a_refuting_skeptic_overrules_the_verdict_and_keeps_both_stamps(tmp_path, monkeypatch):
    ws, row = _tdm_workspace(tmp_path)
    _save_live(ws)
    repo = _repo(tmp_path)
    _install(
        monkeypatch,
        {
            ("verifier", "*"): {"verdict": "unsupported", "quote": "", "quote_source_id": "", "explanation": "the source does not say it", "fix_suggestion": "name another source"},
            ("verifier", row["task_id"]): _supported(row),
            ("skeptic", "*"): {
                "verdict": "unsupported",
                "explanation": "the source states a different number",
                "fix_suggestion": "cite the other source",
            },
        },
    )

    mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))

    (line,) = [r for r in handoff.read_jsonl(ws.claims_dir / "verdicts.jsonl") if r["task_id"] == row["task_id"]]
    assert line["verdict"] == "unsupported"
    assert line["quote"] == "" and line["quote_source_id"] == ""
    assert "the source says so" in line["explanation"]
    assert "the source states a different number" in line["explanation"]
    assert line["skeptic_by"] == ""
    assert "overruled by" in line["answered_by"]


def test_a_failed_live_read_leaves_only_source_missing_and_is_not_announced_as_saved(
    tmp_path, monkeypatch
):
    """Review of I3, kept: a source whose live read failed is never announced as saved, and
    the verifier of a task that cites it may answer nothing but source_missing."""
    ws, row = _tdm_workspace(tmp_path)
    repo = _repo(tmp_path)
    fake = _install(
        monkeypatch,
        {
            ("verifier", "*"): {"verdict": "source_missing", "quote": "", "quote_source_id": "", "explanation": "paywalled", "fix_suggestion": "drop it"},
        },
    )

    def failed(sid: str, url: str) -> str:
        return "HTTP 403 from " + url

    mcode_checks.answer_claims(ws, repo=repo, live_read=failed)

    prompt = fake.prompt_of("verifier", row["task_id"])
    assert "is saved in" not in prompt
    assert f"The live read of {fx.S4} failed (HTTP 403 from {TDM_URL})" in prompt
    assert "The only verdict you may give is therefore source_missing" in prompt


def test_a_saved_live_text_is_named_in_the_verifier_prompt_and_not_fetched_again(
    tmp_path, monkeypatch
):
    ws, row = _tdm_workspace(tmp_path)
    repo = _repo(tmp_path)
    fake = _install(
        monkeypatch,
        {("verifier", "*"): {"verdict": "source_missing", "quote": "", "quote_source_id": "", "explanation": "x", "fix_suggestion": ""}},
    )

    mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))

    prompt = fake.prompt_of("verifier", row["task_id"])
    assert f"the page text of {fx.S4} is saved in" in prompt
    assert "Do not fetch the page again" in prompt
    assert (ws.claims_dir / "live" / f"{fx.S4}.txt").is_file()


def test_an_answer_the_validator_refuses_is_not_appended_and_its_reason_is_named(
    tmp_path, monkeypatch
):
    """A quote that is not in the source is a wrong citation, whatever the model says."""
    ws, row = _tdm_workspace(tmp_path)
    _save_live(ws)
    repo = _repo(tmp_path)
    bad = _supported(row) | {"quote": "a sentence the source never printed"}
    _install(
        monkeypatch,
        {
            ("verifier", "*"): {"verdict": "unsupported", "quote": "", "quote_source_id": "", "explanation": "the source does not say it", "fix_suggestion": "name another source"},
            ("verifier", row["task_id"]): bad,
            ("skeptic", "*"): {"verdict": "supported", "explanation": "cannot refute", "fix_suggestion": ""},
        },
    )

    result = mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))

    assert row["task_id"] in [n["task_id"] for n in result.not_answered]
    reason = next(n["reason"] for n in result.not_answered if n["task_id"] == row["task_id"])
    assert f"quote does not occur verbatim in claims_check/live/{fx.S4}.txt" in reason
    assert all(r["task_id"] != row["task_id"] for r in handoff.read_jsonl(ws.claims_dir / "verdicts.jsonl"))


def test_a_claim_run_whose_repo_tree_changed_is_not_counted(tmp_path, monkeypatch):
    ws, row = _tdm_workspace(tmp_path)
    _save_live(ws)
    repo = _repo(tmp_path)

    class Dirty(FakeMcode):
        def __call__(self, prompt, *, cwd, timeout=mcode.TIMEOUT):
            run = super().__call__(prompt, cwd=cwd, timeout=timeout)
            (repo / "a.txt").write_text("an agent wrote here\n", encoding="utf-8")
            return run

    monkeypatch.setattr(mcode, "weekly_stop", lambda: "")
    monkeypatch.setattr(mcode_checks.mcode, "exec", Dirty({("verifier", "*"): {"verdict": "unsupported", "quote": "", "quote_source_id": "", "explanation": "the source does not say it", "fix_suggestion": "name another source"}}))

    with pytest.raises(StudioError, match="a run changed tracked files"):
        mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))


def test_a_claim_check_without_an_export_names_the_command_that_writes_it(tmp_path, monkeypatch):
    ws = fx.make_workspace(tmp_path)  # no claims.export_claims
    repo = _repo(tmp_path)
    _install(monkeypatch, {})

    with pytest.raises(StudioError, match=f"`{VENV_STUDIO} paper claims-export {fx.REQ}` first"):
        mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: "")


def test_the_claim_check_names_the_import_command_it_prepares(tmp_path, monkeypatch):
    ws, _ = _tdm_workspace(tmp_path)
    repo = _repo(tmp_path)
    _install(monkeypatch, {("verifier", "*"): {"verdict": "unsupported", "quote": "", "quote_source_id": "", "explanation": "the source does not say it", "fix_suggestion": "name another source"}})

    result = mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))

    assert result.next == f"{VENV_STUDIO} paper claims-import {fx.REQ}"


def test_an_unchanged_answer_file_is_left_alone_and_a_second_run_does_not_repeat_it(
    tmp_path, monkeypatch
):
    ws, row = _tdm_workspace(tmp_path)
    _save_live(ws)
    repo = _repo(tmp_path)
    fake = _install(monkeypatch, {("verifier", "*"): {"verdict": "unsupported", "quote": "", "quote_source_id": "", "explanation": "the source does not say it", "fix_suggestion": "name another source"}})

    mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))
    first = len(fake.prompts)
    mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: _save_live(ws))

    assert len(fake.prompts) == first  # every task already has a line in verdicts.jsonl
    assert result_lines(ws) == len(handoff.read_jsonl(ws.claims_dir / "tasks.jsonl"))


def result_lines(ws) -> int:
    return len(handoff.read_jsonl(ws.claims_dir / "verdicts.jsonl"))


# --- image check ------------------------------------------------------------------------------


def test_the_image_check_answers_pending_tasks_only(tmp_path, monkeypatch):
    ws = fx.make_workspace(tmp_path)
    write_json(ws.images_dir / "opportunities.json", fx.OPS)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    rows = handoff.read_jsonl(ws.images_dir / "tasks.jsonl")
    repo = _repo(tmp_path)
    fake = _install(monkeypatch, {("verifier", "*"): {"verdict": "meaningful", "depicts": "a megalith", "subject_box": [0.1, 0.1, 0.5, 0.5], "caption": "The block in the quarry"}})

    result = mcode_checks.answer_images(ws, repo=repo)

    assert result.answered == len(rows)
    lines = handoff.read_jsonl(ws.images_dir / "verdicts.jsonl")
    assert [r["task_id"] for r in lines] == [r["task_id"] for r in rows]
    assert f"{mcode.MODEL} (image check, mcode exec, run_verifier_{rows[0]['task_id']}" in lines[0]["answered_by"]
    assert len(fake.prompts) == len(rows)
    assert result.next == f"{VENV_STUDIO} paper images-import {fx.REQ}"


def test_a_subject_box_outside_the_picture_is_refused_and_named(tmp_path, monkeypatch):
    ws = fx.make_workspace(tmp_path)
    write_json(ws.images_dir / "opportunities.json", fx.OPS)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    assert (ws.images_dir / "tasks.jsonl").is_file()  # the export wrote the task the run answers
    repo = _repo(tmp_path)
    _install(monkeypatch, {("verifier", "*"): {"verdict": "meaningful", "depicts": "a megalith", "subject_box": [0.8, 0.8, 0.5, 0.5], "caption": "The block"}})

    result = mcode_checks.answer_images(ws, repo=repo)

    assert result.answered == 0
    assert not (ws.images_dir / "verdicts.jsonl").exists()
    assert "subject_box must be null or [x, y, w, h] fractions inside the image" in result.not_answered[0]["reason"]


def test_a_kept_picture_without_a_caption_is_refused(tmp_path, monkeypatch):
    ws = fx.make_workspace(tmp_path)
    write_json(ws.images_dir / "opportunities.json", fx.OPS)
    images.export_images(ws, search=fx.fake_search, download=fx.fake_download)
    repo = _repo(tmp_path)
    _install(monkeypatch, {("verifier", "*"): {"verdict": "weak", "depicts": "a megalith", "subject_box": None, "caption": "  "}})

    result = mcode_checks.answer_images(ws, repo=repo)

    assert "caption must be 1 to 120 characters" in result.not_answered[0]["reason"]


# --- marker check -----------------------------------------------------------------------------


def test_the_marker_check_answers_each_marker_and_names_the_import(tmp_path, monkeypatch):
    ep = tmp_path / "episodes" / "baalbek-c5"
    ef.write_casefile(ep)
    ef.write_media(ep)
    from pipeline.studio.casefile import from_dict

    markers_mod = __import__("pipeline.studio.markers", fromlist=["x"])
    markers_mod.export_markers(ep, from_dict(read_json(ep / "casefile.json", "a case file")))
    rows = handoff.read_jsonl(ep / markers_mod.CHECK_DIR / "tasks.jsonl")
    repo = _repo(tmp_path)
    fake = _install(monkeypatch, {("verifier", "*"): {"verdict": "hits", "explanation": "the box holds the person"}})

    result = mcode_checks.answer_markers(ep, repo=repo)

    assert result.answered == len(rows)
    (line,) = handoff.read_jsonl(ep / markers_mod.CHECK_DIR / "verdicts.jsonl")
    assert line["verdict"] == "hits"
    assert f"{mcode.MODEL} (marker check, mcode exec, run_verifier_{rows[0]['task_id']}" in line["answered_by"]
    assert len(fake.prompts) == len(rows)
    assert result.next == f"{VENV_STUDIO} episode markers-import baalbek-c5"


def test_the_marker_prompt_names_both_pictures_and_forbids_the_web(tmp_path, monkeypatch):
    ep = tmp_path / "episodes" / "baalbek-c5"
    ef.write_casefile(ep)
    ef.write_media(ep)
    from pipeline.studio.casefile import from_dict

    markers_mod = __import__("pipeline.studio.markers", fromlist=["x"])
    markers_mod.export_markers(ep, from_dict(read_json(ep / "casefile.json", "a case file")))
    row = handoff.read_jsonl(ep / markers_mod.CHECK_DIR / "tasks.jsonl")[0]
    repo = _repo(tmp_path)
    fake = _install(monkeypatch, {("verifier", "*"): {"verdict": "hits", "explanation": "ok"}})

    mcode_checks.answer_markers(ep, repo=repo)

    prompt = fake.prompts[0]
    assert row["crop_path"] in prompt and row["context_path"] in prompt
    assert "no web search" in prompt
    assert "must hit the right object" in prompt


# --- case-file verification -------------------------------------------------------------------


def test_the_case_file_check_writes_only_the_verification_of_checked_items(tmp_path, monkeypatch):
    ep = tmp_path / "episodes" / "baalbek-c5"
    ef.write_casefile(ep)
    ef.write_media(ep)
    ef.write_paper_workspace(tmp_path / "assets", evidence_ids=("ev-01",))
    before = read_json(ep / "casefile.json", "a case file")
    repo = _repo(tmp_path)
    _install(
        monkeypatch,
        {
            ("verifier", "e2"): {"status": "verified", "method": "web page", "explanation": "the quote is in the page"},
        },
    )

    result = mcode_checks.verify_casefile(ep, repo=repo, probe=lambda ep, item: {"route": "web page", "found": True})

    after = read_json(ep / "casefile.json", "a case file")
    assert result.answered == 1
    assert result.counts == {"verified": 1}
    (e2,) = [e for e in after["evidence"] if e["id"] == "e2"]
    assert e2["verification"]["status"] == "verified"
    assert e2["verification"]["method"] == "web page"
    assert e2["verification"]["by"].startswith(f"{mcode.MODEL} (case file check, mcode exec, run_verifier_e2")
    assert e2["verification"]["at"].endswith("+00:00")
    # nothing else moved
    assert {k: v for k, v in after.items() if k != "evidence"} == {
        k: v for k, v in before.items() if k != "evidence"
    }
    assert after["evidence"][0] == before["evidence"][0]  # e1 was already verified
    assert result.next == f"{VENV_STUDIO} episode check baalbek-c5"


def test_a_refuted_item_is_written_as_refuted_and_keeps_the_explanation(tmp_path, monkeypatch):
    ep = tmp_path / "episodes" / "baalbek-c5"
    ef.write_casefile(ep)
    ef.write_media(ep)
    ef.write_paper_workspace(tmp_path / "assets", evidence_ids=("ev-01",))
    repo = _repo(tmp_path)
    _install(monkeypatch, {("verifier", "e2"): {"status": "refuted", "method": "web page", "explanation": "the page says 900 tons"}})

    mcode_checks.verify_casefile(ep, repo=repo, probe=lambda ep, item: {"route": "web page", "found": False})

    (e2,) = [e for e in read_json(ep / "casefile.json", "a case file")["evidence"] if e["id"] == "e2"]
    assert e2["verification"]["status"] == "refuted"


def test_the_case_file_check_leaves_an_already_verified_item_alone(tmp_path, monkeypatch):
    ep = tmp_path / "episodes" / "baalbek-c5"
    ef.write_casefile(ep)
    ef.write_media(ep)
    ef.write_paper_workspace(tmp_path / "assets", evidence_ids=("ev-01",))
    repo = _repo(tmp_path)
    fake = _install(monkeypatch, {("verifier", "e2"): {"status": "verified", "method": "web page", "explanation": "the quote is in the page"}})

    result = mcode_checks.verify_casefile(ep, repo=repo, probe=lambda ep, item: {"route": "web page", "found": True})

    assert result.answered == 1  # e2 only
    assert len(fake.prompts) == 1


def test_an_item_the_model_did_not_finish_stays_unverified_and_is_named(tmp_path, monkeypatch):
    ep = tmp_path / "episodes" / "baalbek-c5"
    ef.write_casefile(ep)
    ef.write_media(ep)
    ef.write_paper_workspace(tmp_path / "assets", evidence_ids=("ev-01",))
    repo = _repo(tmp_path)
    _install(monkeypatch, {})  # the model writes no answer file

    result = mcode_checks.verify_casefile(ep, repo=repo, probe=lambda ep, item: {"route": "web page", "found": True})

    assert result.answered == 0
    (noted,) = result.not_answered
    assert noted["id"] == "e2"
    assert "no answer file" in noted["reason"]
    assert read_json(ep / "casefile.json", "a case file")["evidence"][1]["verification"]["status"] == "unverified"


# --- the quota stop and the CLI contract --------------------------------------------------------


STOP = "the weekly MiniMax plan has 4 % left (stop at 10 %, owner decision O20); the run resumes after the reset"


def test_a_weekly_quota_stop_stops_the_batch_before_the_first_run(tmp_path, monkeypatch):
    ws = fx.make_workspace(tmp_path)
    claims.export_claims(ws)
    repo = _repo(tmp_path)
    fake = _install(monkeypatch, {("verifier", "*"): _unsupported})
    monkeypatch.setattr(mcode, "weekly_stop", lambda: STOP)

    result = mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: "")

    assert fake.prompts == []
    assert result.stopped == STOP
    assert len(result.not_answered) == len(handoff.read_jsonl(ws.claims_dir / "tasks.jsonl"))
    assert not (ws.claims_dir / "verdicts.jsonl").exists()


def test_a_weekly_quota_that_runs_out_mid_batch_ends_the_pool(tmp_path, monkeypatch):
    """The first wave's two runs answer; the plan hits the line before the next one, and
    the rest of the tasks stay pending instead of being asked (owner decision O20)."""
    ws = fx.make_workspace(tmp_path)
    claims.export_claims(ws)
    repo = _repo(tmp_path)
    fake = _install(monkeypatch, {("verifier", "*"): _unsupported})
    seen: list[int] = []

    def weekly() -> str:
        seen.append(1)
        return "" if len(seen) <= 3 else STOP

    monkeypatch.setattr(mcode, "weekly_stop", weekly)

    result = mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: "")

    assert len(fake.prompts) == 2  # the first wave only
    assert result.answered == 2
    assert result.stopped == STOP
    assert len(result.not_answered) == len(handoff.read_jsonl(ws.claims_dir / "tasks.jsonl")) - 2


def test_a_stopped_batch_keeps_the_lines_of_the_waves_it_finished(tmp_path, monkeypatch):
    """A claim check runs for hours; a batch the quota stop ends must not lose them."""
    ws = fx.make_workspace(tmp_path)
    claims.export_claims(ws)
    repo = _repo(tmp_path)
    _install(monkeypatch, {("verifier", "*"): _unsupported})
    seen: list[int] = []

    def weekly() -> str:
        seen.append(1)
        return "" if len(seen) <= 3 else STOP

    monkeypatch.setattr(mcode, "weekly_stop", weekly)

    mcode_checks.answer_claims(ws, repo=repo, live_read=lambda sid, url: "")

    lines = handoff.read_jsonl(ws.claims_dir / "verdicts.jsonl")
    assert len(lines) == 2  # the first wave, banked before the stop
    assert all(r["verdict"] == "unsupported" for r in lines)

def test_the_validator_refuses_an_answer_file_that_is_not_json(tmp_path):
    path = tmp_path / "answer.json"
    path.write_text("I think the claim holds.", encoding="utf-8")
    ws, row = _tdm_workspace(tmp_path)
    problems = mcode_checks.validate_answer_file("claims", path, ws=ws, task_id=row["task_id"])
    assert problems and "not JSON" in problems[0]


def test_the_validator_accepts_a_complete_answer_file(tmp_path):
    ws, row = _tdm_workspace(tmp_path)
    _save_live(ws)
    path = tmp_path / "answer.json"
    path.write_text(json.dumps(_supported(row)), encoding="utf-8")
    assert mcode_checks.validate_answer_file("claims", path, ws=ws, task_id=row["task_id"]) == []
