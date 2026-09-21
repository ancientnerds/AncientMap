"""Does the Phase-3 model stage read the settled usage, record the provider's own cost and refuse
every answer it could not measure?

Piece 3 has no database and no network, and it is the first piece that can spend money, so the
interesting mistakes are again not exceptions but a *silently wrong* number: a usage taken from a
partial `message_update`, an empty answer returned as a result, a cost recomputed from a price
table, a second ledger line that hides a charge, an argv that a shell would re-parse, or a
`--dry-run` that quietly starts a process. Each guard below has a test that fails when the guard
is removed; the mutation evidence is in `output/remediation/phase3_runner/PIECE3.md`.

Two captured transcripts are the fixtures, copied verbatim out of the gitignored
`output/remediation/logs/` so this suite does not depend on a scratch path:

* `fixtures/pi_probe_no_extensions.json` - the trace of **the argv this module builds**, `-ne`
  included (`input=437`, `cost.total=6.615e-05`). Every line is a JSON event.
* `fixtures/pi_probe2.json` - the earlier probe, taken **with extensions loaded** and with the
  two streams merged: its last line is the OSC 777 notifier of `~/.pi/agent/extensions/
  10-benachrichtigung.ts` followed by the `agent_settled` event. That is what dropping `-ne`
  buys, and the file is used here as the real, uncut input that must make the parser raise.

Nothing in this suite runs `pi`, opens a socket or touches the database.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model as M  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import run as R  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NO_EXTENSIONS = FIXTURES / "pi_probe_no_extensions.json"
MERGED_CAPTURE = FIXTURES / "pi_probe2.json"

#: The prompt of both probes, read out of the capture itself (not re-typed from the brief).
PROMPT = "Reply with exactly the word OK and nothing else."

#: The settled usage of `pi_probe_no_extensions.json`, verbatim.
REPORTED_INPUT = 437
REPORTED_OUTPUT = 1
REPORTED_TOTAL = 438
REPORTED_COST = 6.615e-05

NOTIFIER_PREFIX = "\x1b]777;"


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _answer() -> MS.ModelAnswer:
    """The fixture's settled answer, parsed - the numbers every scripted call replays."""
    return MS.parse_stream(_lines(NO_EXTENSIONS), source=str(NO_EXTENSIONS))


def _call(site_id: str = "site-1", stage: M.Stage = M.Stage.FINDER) -> MS.ModelCall:
    return MS.ModelCall(stage=stage, batch_id="batch-0001", site_id=site_id, prompt="a prompt")


def _site(site_id: str) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "name": f"Cave {site_id}",
        "findings": [
            {
                "test_id": "T05/country",
                "field": "country",
                "current_value": "Georgia (country)",
                "severity": "severe",
                "note": "the parenthetical is a disambiguation hint",
            }
        ],
    }


def _batch(count: int = 1) -> dict[str, Any]:
    return {
        "batch_id": "batch-0001",
        "ordinal": 1,
        "sites": [_site(f"site-{i}") for i in range(1, count + 1)],
    }


def _evidence_store(tmp_path: Path, count: int = 1) -> F.EvidenceStore:
    store = F.EvidenceStore(tmp_path / "evidence")
    for i in range(1, count + 1):
        path = store.path_for(f"site-{i}", "enwiki")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Cave {i} lies in the country Georgia.", encoding="utf-8")
    return store


class ScriptedRunner:
    """A fake runner: replays a captured answer and counts the calls. No process, no money."""

    def __init__(self, answer: MS.ModelAnswer | None = None) -> None:
        self.answer = answer if answer is not None else _answer()
        self.calls: list[MS.ModelCall] = []

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        self.calls.append(call)
        return self.answer


def _assert_no_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if anything starts a Pi process. Used by every dry-run path."""

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(f"a dry run must not start a process: {args!r} {kwargs!r}")

    monkeypatch.setattr(MS.subprocess, "run", refuse)


# ── the settled usage and the provider's own cost ────────────────────────────────────────────


def test_usage_and_the_providers_cost_come_from_the_assistant_message_end() -> None:
    answer = _answer()

    assert answer.text == "OK"
    assert answer.usage.input_tokens == REPORTED_INPUT
    assert answer.usage.output_tokens == REPORTED_OUTPUT
    assert answer.usage.cache_read_tokens == 0
    assert answer.usage.cache_write_tokens == 0
    assert answer.usage.total_tokens == REPORTED_TOTAL
    assert answer.usage.cost_usd == REPORTED_COST
    # The provider's figure is recorded, not recomputed: a price table applied to the same input
    # count (0.15 USD/M, the model's own input price) would give 6.555e-05, not 6.615e-05.
    assert answer.usage.cost_usd != REPORTED_INPUT * 0.15e-6


def test_usage_is_read_from_message_end_and_not_from_a_partial_update() -> None:
    lines = _lines(NO_EXTENSIONS)
    # A partial event carrying a usage of its own must not be read as the settled one.
    partial = json.dumps(
        {
            "type": "message_update",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "O"}],
                "usage": {
                    "input": 999999,
                    "output": 999999,
                    "cacheRead": 999999,
                    "cacheWrite": 999999,
                    "totalTokens": 3999996,
                    "cost": {"total": 99.0},
                },
            },
        }
    )
    stream = lines[:3] + [partial] + lines[3:]

    answer = MS.parse_stream(stream, source="spliced fixture")

    assert answer.usage.input_tokens == REPORTED_INPUT
    assert answer.usage.cost_usd == REPORTED_COST


def test_a_missing_usage_block_raises() -> None:
    lines = []
    for line in _lines(NO_EXTENSIONS):
        event = json.loads(line)
        if event["type"] == "message_end" and event["message"].get("role") == "assistant":
            del event["message"]["usage"]
        lines.append(json.dumps(event, ensure_ascii=False))

    with pytest.raises(MS.ModelCallFailed, match="no usage block"):
        MS.parse_stream(lines, source="usage-less fixture")


def test_an_unparsable_line_raises_on_the_real_merged_capture() -> None:
    raw = _lines(MERGED_CAPTURE)

    # The capture is a real one, taken with extensions loaded and the streams merged: that line is
    # exactly what `-ne` removes (measured: the `-ne` capture has no such line).
    assert any(line.startswith(NOTIFIER_PREFIX) for line in raw)

    with pytest.raises(MS.ModelCallFailed, match="not JSON"):
        MS.parse_stream(raw, source=str(MERGED_CAPTURE))


def test_empty_assistant_text_raises() -> None:
    stream = [
        json.dumps(
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "   "}],
                    "usage": {
                        "input": 10,
                        "output": 0,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "totalTokens": 10,
                        "cost": {"total": 1e-05},
                    },
                },
            }
        )
    ]

    with pytest.raises(MS.ModelCallFailed, match="no text"):
        MS.parse_stream(stream, source="empty-answer stream")


def test_a_stream_without_a_settled_assistant_message_raises() -> None:
    stream = [
        json.dumps({"type": "session", "version": 3}),
        json.dumps({"type": "agent_start"}),
        json.dumps({"type": "message_end", "message": {"role": "system", "content": ""}}),
    ]

    with pytest.raises(MS.ModelCallFailed, match="nothing was measured"):
        MS.parse_stream(stream, source="headless stream")


# ── the process: argv, exit code, timeout ────────────────────────────────────────────────────


def test_the_argv_is_a_list_with_the_measured_flags_and_the_exact_model_id() -> None:
    argv = MS.pi_argv()

    assert isinstance(argv, list)
    assert all(isinstance(part, str) for part in argv)
    for flag in ("-p", "-ne", "-nt", "-nc", "--no-session"):
        assert flag in argv, flag
    assert argv[argv.index("--mode") + 1] == "json"
    assert argv[argv.index("--model") + 1] == "opencode-go/deepseek-v4.1-flash"
    assert argv[argv.index("--thinking") + 1] == "off"
    # Nothing was string-formatted into a command line: no flag element carries a space.
    assert [part for part in argv if " " in part] == []


def test_the_prompt_never_becomes_an_argv_element_and_arrives_on_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect that stopped the first live batch, pinned.

    Measured 2026-09-21: a real prompt (one site record plus its evidence) reached ~24,000
    characters. Passed as the last argv element it made `pi.cmd` exit 1 with `Die Befehlszeile ist
    zu lang.` - `pi.cmd` is a batch file, so Windows runs it through `cmd.exe`, whose command line
    stops near 8,191 characters. The prompt must travel on stdin, UTF-8 encoded, and the argv must
    stay far below that ceiling. This test fails if the prompt is put back into the argv list.
    """
    prompt = 'site "Ötzi" $(rm -rf /) && echo | done ' + "evidence " * 4_000
    assert len(prompt) > 20_000, "this test only means something with a prompt of the real size"
    seen: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen["argv"] = argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, NO_EXTENSIONS.read_bytes(), b"")

    monkeypatch.setattr(MS.subprocess, "run", fake_run)

    call = MS.ModelCall(
        stage=M.Stage.FINDER, batch_id="batch-0001", site_id="site-1", prompt=prompt
    )
    answer = MS.PiRunner(timeout=5.0).run(call)

    assert answer.usage.cost_usd == REPORTED_COST
    argv = seen["argv"]
    # 1. The prompt is not there, whole or in pieces.
    assert prompt not in argv
    assert [part for part in argv if "evidence" in part] == []
    # 2. The whole argv fits a Windows command line with room to spare.
    assert sum(len(part) for part in argv) < 200, sum(len(part) for part in argv)
    # 3. The child receives the prompt's exact bytes, and the non-ASCII site name survives.
    assert seen["input"] == prompt.encode("utf-8")
    assert "Ötzi" in seen["input"].decode("utf-8")


def test_the_runner_passes_the_argv_list_without_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen["argv"] = argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, NO_EXTENSIONS.read_bytes(), b"")

    monkeypatch.setattr(MS.subprocess, "run", fake_run)

    answer = MS.PiRunner(timeout=5.0).run(_call())

    assert answer.usage.cost_usd == REPORTED_COST
    assert isinstance(seen["argv"], list)
    assert seen["shell"] is False
    # The prompt is not in the argv; it goes to the child on stdin, UTF-8 encoded.
    assert seen["input"] == b"a prompt"
    assert "a prompt" not in seen["argv"]


def test_a_non_zero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        MS.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, b"", b"panicked"),
    )

    with pytest.raises(MS.ModelCallFailed, match="exited 1"):
        MS.PiRunner(timeout=5.0).run(_call())


def test_a_hung_process_is_killed_and_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "survived.txt"
    code = f"import time,pathlib;time.sleep(6);pathlib.Path({marker.as_posix()!r}).write_text('x')"
    # A real child process: the flags are replaced by `-c <code>` so that sys.executable can be the
    # "pi" for this one call. Everything else - subprocess, timeout, kill - is the real path.
    monkeypatch.setattr(MS, "PI_FLAGS", ("-c", code))
    runner = MS.PiRunner(program=sys.executable, timeout=1.0)

    started = time.monotonic()
    with pytest.raises(MS.ModelCallFailed, match="did not answer within"):
        runner.run(_call())
    elapsed = time.monotonic() - started

    assert elapsed < 4.0, f"the timeout did not fire: {elapsed:.1f}s"
    time.sleep(2.5)  # the child would still be inside its sleep if it had survived
    assert not marker.exists(), "the timed-out process was not killed"


# ── the ledger: one measured line per call, with the reported cost ───────────────────────────


def test_exactly_one_ledger_line_per_call_records_tokens_and_the_reported_cost(
    tmp_path: Path,
) -> None:
    ledger = L.Ledger(tmp_path / "LEDGER.jsonl", clock=lambda: "2026-09-21T06:00:00+00:00")
    runner = ScriptedRunner()
    answers = F.EvidenceStore(tmp_path / "answers")

    report = MS.judge_batch(
        batch=_batch(2),
        runner=runner,
        store=_evidence_store(tmp_path, 2),
        answers=answers,
        ledger=ledger,
        stage=M.Stage.FINDER,
    )

    rows = [
        json.loads(line) for line in (tmp_path / "LEDGER.jsonl").read_text("utf-8").splitlines()
    ]
    assert len(rows) == len(runner.calls) == 2
    assert {row["kind"] for row in rows} == {"model_call"}
    assert {row["stage"] for row in rows} == {"finder"}
    assert [row["label"] for row in rows] == ["site-1/finder", "site-2/finder"]
    assert {row["model"] for row in rows} == {"opencode-go/deepseek-v4.1-flash"}
    for row in rows:
        assert row["input_tokens"] == REPORTED_INPUT
        assert row["output_tokens"] == REPORTED_OUTPUT
        assert row["cache_read_tokens"] == 0
        assert row["cache_write_tokens"] == 0
        # The provider's own figure, verbatim. Nothing here is a price applied to a token count.
        assert row["cost_usd"] == REPORTED_COST
    assert report.calls == 2
    assert report.input_tokens == 2 * REPORTED_INPUT
    assert report.cost_usd == 2 * REPORTED_COST
    assert answers.path_for("site-1", "finder").read_text(encoding="utf-8") == "OK"

    summary = L.summarise(tmp_path / "LEDGER.jsonl")
    assert summary.by_stage["finder"].model_calls == 2
    assert summary.by_stage["finder"].cost_usd == 2 * REPORTED_COST


def test_a_question_whose_answer_is_already_on_disk_is_not_asked_again(tmp_path: Path) -> None:
    """Existence is the record - and it has to hold *before* the call, where the money is spent.

    A re-run of a batch whose answers survive must not call the model twice: the second answer is
    paid for, and `EvidenceStore.write` refuses to overwrite the recorded one with different bytes,
    so the batch ends on an `EvidenceConflict` instead of a verdict. Measured on 2026-09-21: three
    consecutive mass-run batches (batch-0100/0118/0124) died exactly there and tripped the circuit
    breaker at 130 of 334 batches.
    """
    ledger_path = tmp_path / "LEDGER.jsonl"
    ledger = L.Ledger(ledger_path, clock=lambda: "2026-09-21T06:00:00+00:00")
    answers = F.EvidenceStore(tmp_path / "answers")
    recorded = answers.path_for("site-1", "finder")
    recorded.parent.mkdir(parents=True, exist_ok=True)
    recorded.write_text("the answer that was already recorded", encoding="utf-8")
    runner = ScriptedRunner()

    report = MS.judge_batch(
        batch=_batch(1),
        runner=runner,
        store=_evidence_store(tmp_path, 1),
        answers=answers,
        ledger=ledger,
        stage=M.Stage.FINDER,
    )

    # The model was not asked: no call, and therefore nothing in the ledger that says it was.
    assert runner.calls == []
    assert not ledger_path.exists() or ledger_path.read_text("utf-8") == ""
    # The recorded bytes are left exactly as they were, and the answer is the one on disk.
    assert recorded.read_text(encoding="utf-8") == "the answer that was already recorded"
    assert report.calls == 1
    assert report.cost_usd == 0.0
    assert report.input_tokens == 0
    judgement = report.judgements[0]
    assert judgement.wrote is False
    assert judgement.cost_usd == 0.0
    assert judgement.answer_chars == len("the answer that was already recorded")


def test_a_fetch_line_cannot_carry_a_model_cost() -> None:
    with pytest.raises(L.LedgerError, match="a fetch cannot carry cost_usd"):
        L.Entry(
            kind=L.LedgerKind.FETCH,
            stage=M.Stage.FINDER,
            batch_id="batch-0001",
            label="site-1/enwiki",
            url="https://en.wikipedia.org/wiki/X",
            http_status=200,
            bytes=10,
            outcome=L.FetchOutcome.OK,
            attempt=1,
            given_up=False,
            cost_usd=0.5,
        )


def test_a_run_stops_at_the_first_call_it_could_not_measure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A **transport** failure ends the batch; only an unreadable stream is a named hole.

    The seam is the exception class. `ModelCallFailed` says the call could not be *made* - a
    timeout, a non-zero exit, a process that would not start - and nothing after it may be trusted,
    so it propagates. `UnreadableStream` says these bytes hold no answer: the batch records the hole
    and buys the next call (the two tests below).
    """

    class FailingRunner:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
            raise MS.ModelCallFailed(f"{call.label}: pi exited 1; stderr tail: 'boom'")

    monkeypatch.setattr(MS, "PiRunner", FailingRunner)

    with pytest.raises(MS.ModelCallFailed, match="exited 1"):
        MS.judge_batch(
            batch=_batch(1),
            runner=FailingRunner(),
            store=_evidence_store(tmp_path, 1),
            answers=F.EvidenceStore(tmp_path / "answers"),
            ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
            stage=M.Stage.FINDER,
        )
    assert not (tmp_path / "LEDGER.jsonl").exists()


# ── an unreadable stream is a named hole, never the end of the batch ─────────────────────────


class HoleRunner:
    """A scripted runner whose one named site answers with an unreadable stream.

    It raises exactly what `PiRunner` raises once `parse_stream` has refused the bytes, so the loop
    under test cannot tell the scripted hole from the measured one. That loop is the whole point of
    the class: measured 2026-09-21, 4 of the mass run's 334 batches died on such a call and lost
    every answer they had already written (`output/remediation/logs/mass/batch-0143.judge.log`).
    """

    def __init__(self, hole: str = "site-2", **kwargs: Any) -> None:
        self.hole = hole
        self.kwargs = kwargs
        self.calls: list[MS.ModelCall] = []

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        self.calls.append(call)
        if call.site_id == self.hole:
            raise MS.UnreadableStream(
                f"{call.label} stdout:9 assistant message_end: the assistant message carries no "
                "text - an empty answer is not a result"
            )
        return _answer()


def test_an_unreadable_stream_is_a_named_failure_and_the_batch_carries_on(tmp_path: Path) -> None:
    """The defect the mass run measured, pinned: one hole, three calls, two answers, exit 0.

    The hole is recorded where a later reader looks - `site_id`, `field`, reason, no verdict - the
    calls after it are still bought, and the ledger carries one line per call that was measured.
    """
    runner = HoleRunner()
    ledger = L.Ledger(tmp_path / "LEDGER.jsonl")
    answers = F.EvidenceStore(tmp_path / "answers")

    report = MS.judge_batch(
        batch=_batch(3),
        runner=runner,
        store=_evidence_store(tmp_path, 3),
        answers=answers,
        ledger=ledger,
        stage=M.Stage.FINDER,
    )

    assert [call.site_id for call in runner.calls] == ["site-1", "site-2", "site-3"]
    assert [j.site_id for j in report.judgements] == ["site-1", "site-3"]
    assert report.calls == 3  # a failed call was a call
    assert report.cost_usd == 2 * REPORTED_COST  # ... and not an invented zero
    assert len(report.failures) == 1
    hole = report.failures[0]
    assert (hole.site_id, hole.field) == ("site-2", None)
    assert "carries no text" in hole.reason
    assert set(hole.to_dict()) == {"site_id", "field", "reason"}  # no verdict, no proposal
    stored = json.loads(report.to_json())
    assert stored["failures"] == [hole.to_dict()]
    assert stored["totals"]["calls"] == 3
    rows = [
        json.loads(line) for line in (tmp_path / "LEDGER.jsonl").read_text("utf-8").splitlines()
    ]
    assert [row["label"] for row in rows] == ["site-1/finder", "site-3/finder"]
    assert answers.path_for("site-1", "finder").exists()
    assert not answers.path_for("site-2", "finder").exists()


def test_a_named_failure_carries_a_site_a_field_and_a_reason_and_no_verdict() -> None:
    """`is_named_failure` is the shape check `mass_run.batch_state` settles a batch with.

    A record that grew a `verdict` or a `proposed` value is a finding the call never made, and a
    record that cannot be located is not one either. Refusing both is the whole reason the hole is
    written down instead of guessed at.
    """
    row: dict[str, Any] = {"site_id": "site-1", "field": "country", "reason": "no text"}

    assert MS.is_named_failure(row) is True
    assert MS.is_named_failure({**row, "field": None}) is True  # a per-site call has no field
    assert MS.is_named_failure({**row, "verdict": "WRONG"}) is False
    assert MS.is_named_failure({**row, "proposed": "Cave"}) is False
    assert MS.is_named_failure({k: v for k, v in row.items() if k != "field"}) is False
    assert MS.is_named_failure({"site_id": "", "field": "country", "reason": "no text"}) is False
    assert MS.is_named_failure({"site_id": "site-1", "field": "country", "reason": ""}) is False
    assert MS.is_named_failure(["site-1", "country", "no text"]) is False


def test_judge_live_records_an_unreadable_stream_as_a_hole_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2 stays for a call that could not be *made*; an unreadable stream ends as a hole.

    Measured 2026-09-21: batch-0143 died with exit 2 on one site's empty stream and the restart then
    hit the answers it had already written. Neither happens now - the batch finishes, `model.json`
    carries the hole, and the exit code says the batch is done.
    """
    monkeypatch.setattr(MS, "PiRunner", HoleRunner)
    run_dir = _prepared_run_dir(tmp_path, count=2)
    # The store the CLI builds sits next to input.json: <run_dir>/<batch_id>/evidence.
    _evidence_store(run_dir / "batch-0001", 2)
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        [
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            "batch-0001",
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["totals"]["calls"] == 2
    assert [j["site_id"] for j in payload["judgements"]] == ["site-1"]
    assert [f["site_id"] for f in payload["failures"]] == ["site-2"]
    assert "carries no text" in payload["failures"][0]["reason"]
    stored = json.loads((run_dir / "batch-0001" / "model.json").read_text(encoding="utf-8"))
    assert stored["failures"][0]["site_id"] == "site-2"
    assert stored["totals"]["calls"] == 2


# ── the prompt: bounded, one question per stage ──────────────────────────────────────────────


def test_the_finder_and_the_reviewer_ask_different_questions(tmp_path: Path) -> None:
    assert set(MS.STAGE_QUESTION) == {M.Stage.FINDER, M.Stage.REVIEWER}
    assert MS.FINDER_QUESTION != MS.REVIEWER_QUESTION

    store = _evidence_store(tmp_path, 1)
    finder = MS.prepare_call(
        batch_id="batch-0001", site=_site("site-1"), store=store, stage=M.Stage.FINDER
    )
    reviewer = MS.prepare_call(
        batch_id="batch-0001", site=_site("site-1"), store=store, stage=M.Stage.REVIEWER
    )

    assert MS.FINDER_QUESTION in finder.call.prompt
    assert MS.REVIEWER_QUESTION not in finder.call.prompt
    assert MS.REVIEWER_QUESTION in reviewer.call.prompt
    assert reviewer.call.label == "site-1/reviewer"
    # The site record and the fetched evidence both travel in the prompt.
    assert 'name="Cave site-1"' in finder.call.prompt
    assert "Cave 1 lies in the country Georgia." in finder.call.prompt


def test_a_call_refuses_evidence_that_is_not_on_disk(tmp_path: Path) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")

    with pytest.raises(MS.EvidenceUnusable, match="not on disk"):
        MS.prepare_call(
            batch_id="batch-0001", site=_site("site-1"), store=store, stage=M.Stage.FINDER
        )

    preview = MS.prepare_call(
        batch_id="batch-0001",
        site=_site("site-1"),
        store=store,
        stage=M.Stage.FINDER,
        allow_absent=True,
    )
    assert preview.excerpts[0].text is None
    assert "[absent:" in preview.call.prompt


def test_an_oversized_evidence_block_raises_instead_of_being_truncated(tmp_path: Path) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    path = store.path_for("site-1", "enwiki")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (MS.MAX_EVIDENCE_CHARS + 1), encoding="utf-8")

    with pytest.raises(MS.EvidenceUnusable, match="over the"):
        MS.prepare_call(
            batch_id="batch-0001", site=_site("site-1"), store=store, stage=M.Stage.FINDER
        )


def test_the_evidence_bound_is_above_every_site_the_recall_fixture_measured() -> None:
    """The bound was raised from 32,000 to 64,000 because it refused 2 of the fixture's 24 sites whole.

    The figures are the fixture's own (`output/remediation/gold_standard/`): the combined evidence of
    the Pyramid of Caius Cestius is 49,952 characters and of Priene Ruins 37,339, and at 32,000 both
    sites lost all five fields - including the fields whose decisive sentence sits inside the part
    that would have fitted. The assertion is a **floor**, not the value, so the number may be raised
    again without touching this test while it may not be lowered past the measurement.
    """
    assert MS.MAX_EVIDENCE_CHARS >= 49_952  # Pyramid of Caius Cestius, the fixture's largest site


def test_the_prompt_says_which_census_finding_it_is_about(tmp_path: Path) -> None:
    prepared = MS.prepare_call(
        batch_id="batch-0001",
        site=_site("site-1"),
        store=_evidence_store(tmp_path, 1),
        stage=M.Stage.FINDER,
    )

    assert 'test_id="T05/country"' in prepared.call.prompt
    assert 'field="country"' in prepared.call.prompt
    assert "Georgia (country)" in prepared.call.prompt
    assert prepared.call.prompt.startswith("<question>")
    assert prepared.call.prompt.rstrip().endswith("</evidence>")
    assert "<failed_targets>" not in prepared.call.prompt  # nothing failed for this site


# ── piece 4: partial evidence, and the site no evidence reached ──────────────────────────────


def _latlon_site(site_id: str) -> dict[str, Any]:
    """A site whose findings buy **two** targets: `enwiki` and `overpass_named`."""
    return {
        "site_id": site_id,
        "name": f"Cave {site_id}",
        "findings": [
            {
                "test_id": "T01/coords",
                "field": "lat/lon",
                "current_value": [42.3772, 42.6010],
                "severity": "moderate",
                "note": "Wikidata says the stored point is 1.2 km east",
            }
        ],
    }


OVERPASS_FAILURE = "no response: GET https://overpass-api.de/api/interpreter: ReadTimeout (3 request(s) recorded, the last one given up; no evidence on disk)"


def _enwiki_only_store(tmp_path: Path, site_id: str = "site-1") -> F.EvidenceStore:
    store = F.EvidenceStore(tmp_path / "evidence")
    path = store.path_for(site_id, F.FEATURE_ENWIKI)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Cave site-1 lies in Georgia.", encoding="utf-8")
    return store


def test_a_partially_failed_site_still_gets_a_call_and_the_prompt_names_the_failure(
    tmp_path: Path,
) -> None:
    """The wiki evidence did answer the coordinate question, so the dead Overpass is not fatal.

    This is the case the first live batch could not reach: the enwiki file for that site was on
    disk (4,356 bytes, http_status 200) while the Overpass request had timed out.
    """
    prepared = MS.prepare_call(
        batch_id="batch-0001",
        site=_latlon_site("site-1"),
        store=_enwiki_only_store(tmp_path),
        stage=M.Stage.FINDER,
        failures={F.FEATURE_OVERPASS_NAMED: OVERPASS_FAILURE},
    )

    prompt = prepared.call.prompt
    assert MS.PARTIAL_EVIDENCE_NOTE in prompt
    assert "<failed_targets>" in prompt
    assert 'feature="overpass_named"' in prompt
    assert "ReadTimeout" in prompt
    assert 'status="failed"' in prompt
    assert MS.FAILED_TARGET_MARKER in prompt
    # The evidence that *did* arrive is still there, and it is the only one called present.
    assert "Cave site-1 lies in Georgia." in prompt
    assert prompt.count('status="present"') == 1
    assert [e.failure is None for e in prepared.excerpts] == [True, False]
    assert prepared.excerpts[1].text is None

    # And the call is made: a failed second opinion is not a reason to skip a site.
    runner = ScriptedRunner()
    report = MS.judge_batch(
        batch={"batch_id": "batch-0001", "sites": [_latlon_site("site-1")]},
        runner=runner,
        store=_enwiki_only_store(tmp_path),
        answers=F.EvidenceStore(tmp_path / "answers"),
        ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
        stage=M.Stage.FINDER,
        failures={"site-1": {F.FEATURE_OVERPASS_NAMED: OVERPASS_FAILURE}},
    )
    assert len(runner.calls) == 1
    assert report.calls == 1
    assert report.skipped == []
    assert MS.PARTIAL_EVIDENCE_NOTE in runner.calls[0].prompt


def test_a_site_no_evidence_reached_is_recorded_unverifiable_without_a_model_call(
    tmp_path: Path,
) -> None:
    """No evidence at all: no call (that would buy a guess), but a recorded verdict with a reason."""
    runner = ScriptedRunner()
    ledger = L.Ledger(tmp_path / "LEDGER.jsonl")

    report = MS.judge_batch(
        batch={"batch_id": "batch-0001", "sites": [_latlon_site("site-1")]},
        runner=runner,
        store=F.EvidenceStore(tmp_path / "empty-evidence"),
        answers=F.EvidenceStore(tmp_path / "answers"),
        ledger=ledger,
        stage=M.Stage.FINDER,
        failures={
            "site-1": {
                F.FEATURE_ENWIKI: OVERPASS_FAILURE,
                F.FEATURE_OVERPASS_NAMED: OVERPASS_FAILURE,
            }
        },
    )

    assert runner.calls == []  # no process, no money
    assert report.calls == 0
    assert len(report.skipped) == 1
    skipped = report.skipped[0]
    assert skipped.site_id == "site-1"
    assert F.FEATURE_ENWIKI in skipped.reason  # every failed target is named, with its reason
    assert F.FEATURE_OVERPASS_NAMED in skipped.reason
    assert "ReadTimeout" in skipped.reason
    assert len(skipped.findings) == 1  # one per census finding of the site
    finding = skipped.findings[0]
    assert finding.verdict is M.Verdict.UNVERIFIABLE
    assert finding.defect is False  # derived from the verdict: it is not a clean bill of health
    assert finding.test_id == "T01/coords"
    assert finding.note == skipped.reason
    # Recorded, not silently empty: in the report, and nothing in the ledger (no call was made).
    payload = json.loads(report.to_json())
    assert payload["totals"]["calls"] == 0
    assert payload["totals"]["unverifiable_findings"] == 1
    assert payload["skipped"][0]["findings"][0]["defect"] is False
    assert payload["skipped"][0]["findings"][0]["verdict"] == "unverifiable"
    assert not ledger.path.exists()


def test_a_site_that_buys_no_target_is_recorded_unverifiable_as_such(tmp_path: Path) -> None:
    """All-T02 findings buy no fetch (decision 12), so there is nothing a call could judge."""
    site = {
        "site_id": "site-1",
        "name": "Cave site-1",
        "findings": [
            {
                "test_id": "T02/outside-polygon",
                "field": "country",
                "current_value": "Ireland",
                "severity": "cosmetic",
            }
        ],
    }
    runner = ScriptedRunner()

    report = MS.judge_batch(
        batch={"batch_id": "batch-0001", "sites": [site]},
        runner=runner,
        store=F.EvidenceStore(tmp_path / "evidence"),
        answers=F.EvidenceStore(tmp_path / "answers"),
        ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
        stage=M.Stage.FINDER,
    )

    assert runner.calls == []
    assert "buy no evidence target" in report.skipped[0].reason
    assert report.skipped[0].findings[0].verdict is M.Verdict.UNVERIFIABLE


def test_a_missing_evidence_file_with_no_recorded_failure_still_raises(tmp_path: Path) -> None:
    """The guard that fired correctly stays exactly as it was: nothing recorded, nothing judged."""
    with pytest.raises(MS.EvidenceUnusable, match="records no failure"):
        MS.prepare_call(
            batch_id="batch-0001",
            site=_latlon_site("site-1"),
            store=_enwiki_only_store(tmp_path),
            stage=M.Stage.FINDER,
        )
    # And a failure recorded for a *different* target does not excuse the missing one either.
    with pytest.raises(MS.EvidenceUnusable, match="records no failure"):
        MS.prepare_call(
            batch_id="batch-0001",
            site=_latlon_site("site-1"),
            store=F.EvidenceStore(tmp_path / "nothing"),
            stage=M.Stage.FINDER,
            failures={F.FEATURE_ENWIKI: OVERPASS_FAILURE},
        )
    # Through the stage as well: the batch stops rather than judging what is not on disk.
    with pytest.raises(MS.EvidenceUnusable, match="not on disk"):
        MS.judge_batch(
            batch={"batch_id": "batch-0001", "sites": [_latlon_site("site-1")]},
            runner=ScriptedRunner(),
            store=_enwiki_only_store(tmp_path),
            answers=F.EvidenceStore(tmp_path / "answers"),
            ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
            stage=M.Stage.FINDER,
        )


def test_read_fetch_failures_reads_what_the_fetch_stage_wrote(tmp_path: Path) -> None:
    """The round trip that makes the judge's "explained failure" a record, not a belief."""
    site = _site_record_for_report()
    report = F.BatchFetchReport(batch_id="batch-0001", stage=M.Stage.FINDER)
    outcome = F.SiteEvidence(site_id=site["site_id"])
    outcome.outcomes.append(
        F.TargetOutcome(
            feature=F.FEATURE_ENWIKI,
            url="https://en.wikipedia.org/w/api.php?data=x",
            bought_by="T01/coords lat/lon",
            attempts=[
                F.FetchAttempt(1, L.FetchOutcome.OK, 200, 4356, None),
            ],
            stored=True,
        )
    )
    outcome.outcomes.append(
        F.TargetOutcome(
            feature=F.FEATURE_OVERPASS_NAMED,
            url=site["targets"][1]["url"],
            bought_by="T01/coords lat/lon",
            attempts=[
                F.FetchAttempt(1, L.FetchOutcome.TRANSPORT_FAILURE, None, 0, "ReadTimeout"),
                F.FetchAttempt(2, L.FetchOutcome.TRANSPORT_FAILURE, None, 0, "ReadTimeout"),
                F.FetchAttempt(3, L.FetchOutcome.TRANSPORT_FAILURE, None, 0, "ReadTimeout"),
            ],
        )
    )
    report.sites.append(outcome)
    path = tmp_path / "fetch.json"
    F.write_report(path, report)

    assert MS.read_fetch_failures(path) == report.failures_by_site()
    assert MS.read_fetch_failures(path) == {
        site["site_id"]: {F.FEATURE_OVERPASS_NAMED: outcome.outcomes[1].failure}
    }
    # A batch that was never fetched live explains nothing, and says so by explaining nothing.
    assert MS.read_fetch_failures(tmp_path / "absent.json") == {}
    # An unreadable report is not an empty one.
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    with pytest.raises(R.InputError, match="not JSON"):
        MS.read_fetch_failures(broken)
    shape = tmp_path / "shape.json"
    shape.write_text(json.dumps({"sites": [{"site_id": "s"}]}), encoding="utf-8")
    with pytest.raises(R.InputError, match="no `outcomes` list"):
        MS.read_fetch_failures(shape)


class _ProbeDownFetcher:
    """`overpass-api.de` resets, everything else answers. The seam, so no socket is opened."""

    def get(self, url: str) -> F.FetchedPage:
        if urlsplit(url).hostname == "overpass-api.de":
            raise F.TransportFailure(f"GET {url}: ConnectError: connection reset by peer")
        return F.FetchedPage(
            status=200, final_url=url, body=b'{"query": {"pages": {}}}', truncated=False
        )


def test_a_target_on_an_unreachable_host_reaches_the_prompt_as_not_attempted(
    tmp_path: Path,
) -> None:
    """Piece 4b, end to end: the probe's decision must reach `<failed_targets>`, and say which of
    the two facts it is. A target nobody asked because its host was silent is *not* a target that
    was asked and failed, and a prompt that blurred the two would let the model read silence as
    absence of a defect.
    """
    store = F.EvidenceStore(tmp_path / "evidence")
    site = _latlon_site("site-1")
    report = F.collect_batch(
        batch={"batch_id": "batch-0001", "sites": [site]},
        fetcher=_ProbeDownFetcher(),
        store=store,
        ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
        stage=M.Stage.FINDER,
    )
    path = tmp_path / "fetch.json"
    F.write_report(path, report)

    failures = MS.read_fetch_failures(path)
    assert set(failures["site-1"]) == {F.FEATURE_OVERPASS_NAMED}
    prepared = MS.prepare_call(
        batch_id="batch-0001",
        site=site,
        store=store,
        stage=M.Stage.FINDER,
        failures=failures["site-1"],
    )

    prompt = prepared.call.prompt
    assert "<failed_targets>" in prompt
    assert 'feature="overpass_named"' in prompt
    assert "not attempted" in prompt  # the fact: this target was never asked
    assert "host probe" in prompt  # ... because the host did not answer the run's probe
    assert "ConnectError" in prompt  # the probe's own reason, not an attempt's status
    assert "0 request(s) recorded" in prompt
    # A target that *was* asked and failed says the other sentence; this prompt must not carry it.
    assert "the last one given up" not in prompt
    assert MS.FAILED_TARGET_MARKER in prompt
    # The evidence that did arrive is still there, and it is the only one called present.
    assert prompt.count('status="present"') == 1
    assert [e.failure is None for e in prepared.excerpts] == [True, False]


def _site_record_for_report() -> dict[str, Any]:
    site = _latlon_site("31860bc4-476a-49bc-9f97-e25220063d19")
    site["targets"] = [{"feature": t.feature, "url": t.url} for t in F.targets_for_site(site)]
    return site


# ── the CLI: dry run by default ──────────────────────────────────────────────────────────────


def _prepared_run_dir(tmp_path: Path, count: int = 1) -> Path:
    run_dir = tmp_path / "runs"
    batch_dir = run_dir / "batch-0001"
    batch_dir.mkdir(parents=True)
    (batch_dir / "input.json").write_text(
        json.dumps(_batch(count), ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    return run_dir


def test_judge_without_live_renders_the_argv_and_the_prompt_and_starts_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _assert_no_process(monkeypatch)
    run_dir = _prepared_run_dir(tmp_path)
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        [
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            "batch-0001",
            "--ledger",
            str(ledger),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["live"] is False
    assert payload["calls"] == 1
    assert payload["model"] == "opencode-go/deepseek-v4.1-flash"
    site = payload["sites"][0]
    # The preview shows the argv the runner would use, and the prompt **separately**: the prompt is
    # never an argv element (it travels on stdin - the module docstring records the measurement).
    assert site["prompt"] not in site["argv"]
    assert site["argv"][1:] == list(MS.PI_FLAGS) + [
        "--model",
        "opencode-go/deepseek-v4.1-flash",
        "--thinking",
        "off",
    ]
    assert site["prompt_chars"] == len(site["prompt"])
    assert MS.FINDER_QUESTION in site["prompt"]
    # The preview shows the missing evidence instead of hiding it, and nothing was written.
    assert site["evidence"][0]["present"] is False
    assert not ledger.exists()
    assert not (run_dir / "batch-0001" / "answers").exists()


def test_judge_live_records_unverifiable_findings_for_a_site_with_no_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole live path, with the fetch report naming what failed: recorded, not surfacing as 2."""
    started: list[str] = []

    class CountingRunner:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
            started.append(call.site_id)
            return _answer()

    monkeypatch.setattr(MS, "PiRunner", CountingRunner)
    run_dir = _prepared_run_dir(tmp_path)
    batch_dir = run_dir / "batch-0001"
    (batch_dir / "fetch.json").write_text(
        json.dumps(
            {
                "batch_id": "batch-0001",
                "sites": [
                    {
                        "site_id": "site-1",
                        "outcomes": [
                            {
                                "feature": "enwiki",
                                "url": "https://en.wikipedia.org/w/api.php?data=x",
                                "failure": "no response: GET ...: ReadTimeout (3 request(s) recorded)",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        [
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            "batch-0001",
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert started == []  # no model call: there was nothing for a model to read
    assert payload["totals"]["calls"] == 0
    assert payload["totals"]["unverifiable_findings"] == 1
    assert payload["skipped"][0]["site_id"] == "site-1"
    assert "ReadTimeout" in payload["skipped"][0]["reason"]
    stored = json.loads((batch_dir / "model.json").read_text(encoding="utf-8"))
    assert stored["skipped"][0]["findings"][0]["verdict"] == "unverifiable"
    assert stored["skipped"][0]["findings"][0]["field"] == "country"
    assert not ledger.exists()  # no call, no measurement, so no line claiming one


def test_judge_live_reports_a_call_it_could_not_measure_with_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FailingRunner:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
            raise MS.ModelCallFailed(f"{call.label}: pi exited 1; stderr tail: 'boom'")

    monkeypatch.setattr(MS, "PiRunner", FailingRunner)
    run_dir = _prepared_run_dir(tmp_path)
    # The store the CLI builds sits next to input.json: <run_dir>/<batch_id>/evidence.
    _evidence_store(run_dir / "batch-0001", 1)
    ledger = tmp_path / "LEDGER.jsonl"

    rc = R.main(
        [
            "judge",
            "--run-dir",
            str(run_dir),
            "--batch-id",
            "batch-0001",
            "--ledger",
            str(ledger),
            "--live",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["live"] is True
    assert "pi exited 1" in payload["error"]
    assert not ledger.exists()
    assert not (run_dir / "batch-0001" / "model.json").exists()
