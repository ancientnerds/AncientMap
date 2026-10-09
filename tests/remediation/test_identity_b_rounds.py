"""The rounds engine of the identity questions (`scripts/remediation/identity/rounds.py`).

A toy stage stands in for the real ones: its question is a line of text, its answer a small JSON
object. What is tested is the engine - the export, the brief, the shape check, the role check at the
import, the decisions, the re-asks and the calibration gate - never a model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from identity import rounds as R  # noqa: E402

from tests.remediation.identity_b_fixtures import (  # noqa: E402
    NOW,
    FakeClient,
    answer_all,
    resolver_of,
)

PAGE = "https://example.org/page"


def render(ctx: dict[str, Any], earlier: str | None) -> str:
    return f"Question about {ctx['name']}." + ("" if earlier is None else f" Earlier: {earlier}")


def parse(text: str, ctx: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise R.AnswerError(f"not JSON: {exc}") from exc
    if set(data) != {"site_id", "ok"} or data["site_id"] != ctx["site_id"]:
        raise R.AnswerError("the answer is not {site_id, ok} of this question")
    return data


def decide(parsed: dict[str, Any], ctx: dict[str, Any], env: R.Env) -> R.Outcome:
    if parsed["ok"]:
        return R.Outcome(R.DECIDED, "", {"ok": True})
    return R.Outcome(R.HELD, "ok: the answer says no", {"ok": False})


SPEC = R.StageSpec(
    lane="toy",
    stage="toy-web",
    role="web_verifier",
    render=render,
    parse=parse,
    decide=decide,
    cited=lambda p, c: set(),
    titles=lambda p, c: set(),
    per_batch=1,
    guidance="Be careful.",
)
A_ID, B_ID = "aaaaaaaa-0000-4000-8000-000000000001", "bbbbbbbb-0000-4000-8000-000000000002"


def questions() -> list[R.Question]:
    return [
        R.Question(A_ID, {"site_id": A_ID, "name": "Alpha"}),
        R.Question(B_ID, {"site_id": B_ID, "name": "Beta"}),
    ]


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "toy" / "toy-web"


def run_import(out: Path, name: str = "r1") -> dict[str, Any]:
    return R.import_round(
        out, SPEC, name, http=FakeClient, resolver=resolver_of({}), now=lambda: NOW, pace=0
    )


class TestTheExport:
    def test_a_round_is_exported_with_its_contexts_and_recorded(
        self, out: Path, tmp_path: Path
    ) -> None:
        record = R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        assert record.name == "r1" and sorted(record.batches) == ["r1-b01", "r1-b02"]
        assert R.find_round(out, "r1") == record
        contexts = R.load_contexts(out)
        assert contexts[A_ID]["name"] == "Alpha" and set(contexts) == {A_ID, B_ID}
        prompt = (tmp_path / "h1" / "r1-b01" / "toy-web" / f"{A_ID}.prompt.txt").read_text("utf-8")
        assert prompt == "Question about Alpha."

    def test_a_used_directory_and_a_site_asked_twice_are_refused(
        self, out: Path, tmp_path: Path
    ) -> None:
        used = tmp_path / "used"
        used.mkdir()
        (used / "x").write_text("x", encoding="utf-8")
        with pytest.raises(R.RoundError, match="not empty"):
            R.export_round(out, SPEC, used, questions())
        with pytest.raises(R.RoundError, match="asked twice"):
            R.export_round(out, SPEC, tmp_path / "h", [questions()[0], questions()[0]])
        with pytest.raises(R.RoundError, match="nothing to export"):
            R.export_round(out, SPEC, tmp_path / "h", [])

    def test_batches_are_in_site_order_and_bounded(self) -> None:
        assert R.batches(["c", "a", "b"], "r1", 2) == {"r1-b01": ["a", "b"], "r1-b02": ["c"]}
        with pytest.raises(R.RoundError):
            R.batches(["a"], "r1", 0)

    def test_a_round_file_is_written_once(self, out: Path, tmp_path: Path) -> None:
        R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        with pytest.raises(R.RoundError, match="written once"):
            R._write_once(out / R.CONTEXTS_DIR / "r1.jsonl", "x")


class TestTheBriefAndTheShapeCheck:
    def test_the_brief_names_the_role_its_model_and_the_exact_commands(
        self, out: Path, tmp_path: Path
    ) -> None:
        R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        text = R.brief(out, SPEC, "r1", "r1-b01")
        assert "running as the role web_verifier" in text
        assert "--role web_verifier --model claude-sonnet-5-5" in text
        assert (
            f"--lane toy check-answer --stage toy-web --stage-dir {out.resolve().as_posix()} "
            "--round r1 --batch-id r1-b01"
        ) in text
        assert "Be careful." in text
        assert "read the site's Wikipedia text from that cache first" in text
        assert "a 403 or 429 is a refusal of the server, never a finding" in text
        with pytest.raises(R.RoundError, match="no batch"):
            R.brief(out, SPEC, "r1", "r9-b01")

    def test_check_answer_returns_the_shape_problem_or_none(
        self, out: Path, tmp_path: Path
    ) -> None:
        R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        ok = json.dumps({"site_id": A_ID, "ok": True})
        assert R.check_answer(out, SPEC, "r1", "r1-b01", A_ID, ok) is None
        assert "not JSON" in str(R.check_answer(out, SPEC, "r1", "r1-b01", A_ID, "nope"))
        with pytest.raises(R.RoundError, match="no question"):
            R.check_answer(out, SPEC, "r1", "r1-b02", A_ID, ok)


class TestTheImport:
    def test_decided_and_held_answers_are_merged_by_site(self, out: Path, tmp_path: Path) -> None:
        record = R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        answer_all(
            tmp_path / "h1",
            record,
            SPEC,
            {A_ID: {"site_id": A_ID, "ok": True}, B_ID: {"site_id": B_ID, "ok": False}},
        )
        summary = run_import(out)
        assert (summary["decided"], summary["held"]) == (1, 1)
        decisions = R.decisions_by_site(out)
        assert decisions[A_ID]["status"] == R.DECIDED and decisions[A_ID]["round"] == "r1"
        assert decisions[A_ID]["answered_by"] == "web_verifier:r1-b01"
        assert decisions[A_ID]["model"] == OH.SONNET_MODEL
        assert decisions[B_ID]["reason"] == "ok: the answer says no"
        assert R.held_sites(out) == {B_ID: "ok: the answer says no"}
        with pytest.raises(R.RoundError, match="imported already"):
            run_import(out)

    def test_a_shape_problem_holds_the_site_and_is_asked_again(
        self, out: Path, tmp_path: Path
    ) -> None:
        record = R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        answer_all(
            tmp_path / "h1", record, SPEC, {A_ID: {"site_id": A_ID, "ok": True}, B_ID: "not json"}
        )
        run_import(out)
        assert R.decisions_by_site(out)[B_ID]["reason"].startswith("shape: not JSON")
        held = R.reask_sites(out)
        again = R.export_round(
            out, SPEC, tmp_path / "h2", [questions()[1]], earlier=held, now=lambda: NOW
        )
        assert again.name == "r2" and again.sites == [B_ID]
        prompt = next((tmp_path / "h2").glob("*/toy-web/*.prompt.txt")).read_text("utf-8")
        assert prompt.endswith(
            "Earlier: shape: not JSON: Expecting value: line 1 column 1 (char 0)"
        )
        answer_all(tmp_path / "h2", again, SPEC, {B_ID: {"site_id": B_ID, "ok": True}})
        run_import(out, "r2")
        merged = R.decisions_by_site(out)
        assert merged[A_ID]["round"] == "r1" and merged[B_ID]["round"] == "r2"
        assert merged[B_ID]["status"] == R.DECIDED

    def test_an_unanswered_round_does_not_validate(self, out: Path, tmp_path: Path) -> None:
        R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        with pytest.raises(R.RoundError, match="does not validate"):
            run_import(out)

    def test_only_the_newest_round_is_imported_and_a_re_ask_waits_for_the_import(
        self, out: Path, tmp_path: Path
    ) -> None:
        record = R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        with pytest.raises(R.RoundError, match="exported but not imported"):
            R.reask_sites(out)
        answer_all(
            tmp_path / "h1",
            record,
            SPEC,
            {A_ID: {"site_id": A_ID, "ok": False}, B_ID: {"site_id": B_ID, "ok": False}},
        )
        run_import(out)
        for number in (2, 3):
            held = R.reask_sites(out)
            again = R.export_round(
                out, SPEC, tmp_path / f"h{number}", questions(), earlier=held, now=lambda: NOW
            )
            answer_all(
                tmp_path / f"h{number}",
                again,
                SPEC,
                {A_ID: {"site_id": A_ID, "ok": False}, B_ID: {"site_id": B_ID, "ok": False}},
            )
            run_import(out, f"r{number}")
        with pytest.raises(R.RoundError, match="3 rounds are out"):
            R.reask_sites(out)
        with pytest.raises(R.RoundError, match="not the newest"):
            run_import(out, "r1")

    def test_a_re_ask_asks_exactly_the_held_sites(self, out: Path, tmp_path: Path) -> None:
        record = R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        answer_all(
            tmp_path / "h1",
            record,
            SPEC,
            {A_ID: {"site_id": A_ID, "ok": True}, B_ID: {"site_id": B_ID, "ok": False}},
        )
        run_import(out)
        with pytest.raises(R.RoundError, match="exactly the held sites"):
            R.export_round(out, SPEC, tmp_path / "h2", questions(), earlier={B_ID: "x", A_ID: "y"})
        with pytest.raises(R.RoundError, match="round 1 re-asks nothing"):
            R.export_round(
                tmp_path / "other", SPEC, tmp_path / "h3", questions(), earlier={A_ID: "x"}
            )


class TestTheRoleCheck:
    """An answer is the stage's role's or it is not imported; nothing is written for a round whose
    answers are not (the model census of 2026-10-01 found 8,471 answers stamped Opus that Sonnet
    had written)."""

    def record_with(self, out: Path, tmp_path: Path, answered_by: str, model: str) -> R.Round:
        record = R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        for batch_id, sids in record.batches.items():
            for sid in sids:
                OH.write_answer(
                    tmp_path / "h1",
                    batch_id=batch_id,
                    stage=SPEC.stage,
                    label=sid,
                    text=json.dumps({"site_id": sid, "ok": True}),
                    answered_by=answered_by
                    if answered_by != "role"
                    else f"web_verifier:{batch_id}",
                    model=model,
                    now=lambda: NOW,
                )
        return record

    def test_an_answer_under_no_role_is_refused(self, out: Path, tmp_path: Path) -> None:
        self.record_with(out, tmp_path, "agent-1", OH.SONNET_MODEL)
        with pytest.raises(R.RoundError, match="recorded under no role"):
            run_import(out)
        assert not (out / R.ANSWERS_DIR).exists() and not (out / R.DECISIONS_FILE).exists()

    def test_an_answer_under_another_role_is_refused(self, out: Path, tmp_path: Path) -> None:
        self.record_with(out, tmp_path, "adversarial:r1", OH.OPUS_MODEL)
        with pytest.raises(R.RoundError, match="recorded under adversarial"):
            run_import(out)

    @pytest.mark.parametrize("stamp", [OH.OPUS_MODEL, OH.HAIKU_MODEL, OH.MINIMAX_MODEL])
    def test_an_answer_stamped_by_another_model_than_the_role_s_is_refused(
        self, out: Path, tmp_path: Path, stamp: str
    ) -> None:
        self.record_with(out, tmp_path, "role", stamp)
        with pytest.raises(R.RoundError, match="registered to claude-sonnet-5-5"):
            run_import(out)
        assert not (out / R.DECISIONS_FILE).exists()


class TestTheCalibrationGate:
    def seal(self, root: Path, calibration_id: str, role: str, **over: Any) -> None:
        seals = root / R.THRESHOLDS_FILE
        entry = {"role_sha256": RO.role_sha256(role), "calibration_id": calibration_id, **over}
        seals.parent.mkdir(parents=True, exist_ok=True)
        known = json.loads(seals.read_text("utf-8")) if seals.exists() else {}
        seals.write_text(json.dumps({**known, calibration_id: entry}), encoding="utf-8")

    def verdict(self, root: Path, calibration_id: str, **over: Any) -> None:
        body = {
            "calibration_id": calibration_id,
            "role": "web_verifier",
            "model": "claude-sonnet-5-5",
            "passed": True,
            "tier_move": None,
        }
        body.update(over)
        path = root / R.VERDICTS_DIR / f"{calibration_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body), encoding="utf-8")

    def test_a_passed_sealed_verdict_of_the_role_opens_the_gate(self, tmp_path: Path) -> None:
        self.seal(tmp_path, "c1", "web_verifier")
        self.verdict(tmp_path, "c1")
        assert R.require_calibration(tmp_path, "c1", "web_verifier")["passed"] is True

    def test_no_verdict_a_failed_verdict_and_another_role_close_it(self, tmp_path: Path) -> None:
        with pytest.raises(R.RoundError, match="has no verdict"):
            R.require_calibration(tmp_path, "c1", "web_verifier")
        self.seal(tmp_path, "c1", "web_verifier")
        self.verdict(tmp_path, "c1", passed=False, tier_move={"to": "claude-opus-5-5"})
        with pytest.raises(R.RoundError, match="did not pass"):
            R.require_calibration(tmp_path, "c1", "web_verifier")
        self.verdict(tmp_path, "c2")
        self.seal(tmp_path, "c2", "web_verifier")
        with pytest.raises(R.RoundError, match="measured role web_verifier, not adversarial"):
            R.require_calibration(tmp_path, "c2", "adversarial")

    def test_a_verdict_of_another_model_or_under_another_registry_entry_is_stale(
        self, tmp_path: Path
    ) -> None:
        self.seal(tmp_path, "c3", "web_verifier")
        self.verdict(tmp_path, "c3", model="claude-haiku-5-5")
        with pytest.raises(R.RoundError, match="calibrate again"):
            R.require_calibration(tmp_path, "c3", "web_verifier")
        self.seal(tmp_path, "c4", "web_verifier", role_sha256="0" * 64)
        self.verdict(tmp_path, "c4")
        with pytest.raises(R.RoundError, match="sealed under another registry entry"):
            R.require_calibration(tmp_path, "c4", "web_verifier")
        self.verdict(tmp_path, "c5")
        with pytest.raises(R.RoundError, match="sealed under another registry entry"):
            R.require_calibration(tmp_path, "c5", "web_verifier")


class TestTheEdges:
    def test_a_re_ask_before_any_round_is_refused(self, out: Path) -> None:
        with pytest.raises(R.RoundError, match="no round is exported yet"):
            R.reask_sites(out)

    def test_a_round_whose_stored_contexts_are_gone_cannot_be_checked(
        self, out: Path, tmp_path: Path
    ) -> None:
        R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        (out / R.CONTEXTS_DIR / "r1.jsonl").unlink()
        ok = json.dumps({"site_id": A_ID, "ok": True})
        with pytest.raises(R.RoundError, match="contexts were never stored"):
            R.check_answer(out, SPEC, "r1", "r1-b01", A_ID, ok)

    def test_a_fourth_round_is_never_exported(self, out: Path, tmp_path: Path) -> None:
        record = R.export_round(out, SPEC, tmp_path / "h1", questions(), now=lambda: NOW)
        no = {A_ID: {"site_id": A_ID, "ok": False}, B_ID: {"site_id": B_ID, "ok": False}}
        answer_all(tmp_path / "h1", record, SPEC, no)
        run_import(out)
        for number in (2, 3):
            again = R.export_round(
                out,
                SPEC,
                tmp_path / f"h{number}",
                questions(),
                earlier=R.held_sites(out),
                now=lambda: NOW,
            )
            answer_all(tmp_path / f"h{number}", again, SPEC, no)
            run_import(out, f"r{number}")
        with pytest.raises(R.RoundError, match="at most 3"):
            R.export_round(out, SPEC, tmp_path / "h4", questions(), earlier=R.held_sites(out))

    def test_a_title_the_resolver_does_not_answer_stops_the_import(
        self, out: Path, tmp_path: Path
    ) -> None:
        import dataclasses

        titled = dataclasses.replace(SPEC, titles=lambda p, c: {"Some Title"})
        record = R.export_round(out, titled, tmp_path / "h1", questions(), now=lambda: NOW)
        answer_all(
            tmp_path / "h1", record, titled,
            {A_ID: {"site_id": A_ID, "ok": True}, B_ID: {"site_id": B_ID, "ok": True}},
        )  # fmt: skip
        with pytest.raises(R.RoundError, match="1 title.s. came back unresolved"):
            R.import_round(
                out,
                titled,
                "r1",
                http=FakeClient,
                resolver=lambda wanted, client: {},
                now=lambda: NOW,
                pace=0,
            )
        assert not (out / R.DECISIONS_FILE).exists()


class TestTheAgreement:
    def decide_all(self, out: Path, tmp_path: Path, tag: str, verdicts: dict[str, bool]) -> None:
        record = R.export_round(
            out,
            SPEC,
            tmp_path / f"h-{tag}",
            [q for q in questions() if q.site_id in verdicts],
            now=lambda: NOW,
        )
        answer_all(
            tmp_path / f"h-{tag}",
            record,
            SPEC,
            {sid: {"site_id": sid, "ok": ok} for sid, ok in verdicts.items()},
        )
        run_import(out)

    def test_two_imports_of_the_same_questions_are_compared_by_site(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a", tmp_path / "b"
        self.decide_all(first, tmp_path, "a", {A_ID: True, B_ID: True})
        self.decide_all(second, tmp_path, "b", {A_ID: True})
        got = R.agreement(first, second)
        # the toy decision records no verdict: both sides read None, so they agree
        assert got == {
            "shared": 1,
            "agree": 1,
            "disagree": [],
            "only_first": [B_ID],
            "only_second": [],
        }

    def test_a_different_verdict_is_listed(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a", tmp_path / "b"
        for out, verdict in ((first, "KEEP"), (second, "RETARGET")):
            out.mkdir()
            R.write_jsonl(
                out / R.DECISIONS_FILE,
                [{"site_id": A_ID, "status": R.DECIDED, "data": {"verdict": verdict}}],
            )
        got = R.agreement(first, second)
        assert got["shared"] == 1 and got["agree"] == 0
        assert got["disagree"] == [{"site_id": A_ID, "first": "KEEP", "second": "RETARGET"}]
