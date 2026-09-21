"""Does the mass-run driver walk a plan without losing evidence, money or its own guardrails?

Piece 7 is the thing that runs 334 batches unattended, so every way it can lie to itself is a test
here: a batch pronounced done on a truncated artefact, a ceiling that overshoots, a breaker that
never trips or one that trips on the wrong count, a progress file a human cannot read while the run
is going, and a dry run that quietly buys something. The dry run's test asserts on the **ledger**, not
on "nothing was raised".

The stages are never executed: `_StubRunner` stands in for `StageRunner` on the same contract
(`run_dir` plus `batch`), so no subprocess starts and no model is called. Each guard is additionally
proved able to fail by mutating `mass_run.py` and restoring it byte-identically - see
`output/remediation/phase3_runner/PIECE7.md`.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import mass_run as M  # noqa: E402
from phase3 import run as R  # noqa: E402

SITE = "31860bc4-476a-49bc-9f97-e25220063d19"
FIELDS = ("description", "period_start", "site_type", "country", "card_description")


def _plan(tmp_path: Path, batches: list[tuple[str, int]], *, sites: int = 1) -> Path:
    """A plan as `snapshot_plan` writes it: one line per batch, `{batch_id, ordinal, sites}`."""
    lines = [
        json.dumps(
            {
                "batch_id": batch_id,
                "ordinal": ordinal,
                "sites": [{"site_id": SITE} for _ in range(sites)],
            }
        )
        for batch_id, ordinal in batches
    ]
    path = tmp_path / "PLAN.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _ledger(tmp_path: Path, *, rows: list[dict[str, Any]] | None = None, torn: str = "") -> Path:
    path = tmp_path / "LEDGER.jsonl"
    text = "\n".join(json.dumps(row) for row in (rows or []))
    path.write_text((text + "\n" if text else "") + torn, encoding="utf-8")
    return path


def _model_call(cost: float) -> dict[str, Any]:
    return {"kind": "model_call", "cost_usd": cost, "batch_id": "batch-0001"}


def _artefacts(
    run_dir: Path,
    batch_id: str,
    *,
    calls: int = 1,
    wrote: bool = True,
    answers: bool = True,
    model_text: str | None = None,
) -> Path:
    """A batch on disk as the three stages leave it: input, fetch, model and the answer files."""
    root = run_dir / batch_id
    (root / "answers").mkdir(parents=True, exist_ok=True)
    (root / "input.json").write_text(json.dumps({"batch_id": batch_id}), encoding="utf-8")
    (root / "fetch.json").write_text(json.dumps({"batch_id": batch_id}), encoding="utf-8")
    judgements = [
        {"site_id": SITE, "field": FIELDS[index % len(FIELDS)], "wrote": wrote}
        for index in range(calls)
    ]
    (root / "model.json").write_text(
        model_text
        if model_text is not None
        else json.dumps({"totals": {"calls": calls}, "judgements": judgements}),
        encoding="utf-8",
    )
    if answers:
        for row in judgements:
            slug = M.F.EvidenceStore.slug(str(row["site_id"]), str(row["field"]))
            (root / "answers" / f"{slug}.txt").write_text("VERDICT: CORRECT\n", encoding="utf-8")
    return root


class _StubRunner:
    """The seam: no subprocess, same contract as `StageRunner`.

    `ledger` plus `calls_per_batch` make it buy like the real `judge` does. Without that the budgets
    could not be tested at all under ceilings that are measured *from the start of the run*: a stub
    that never spends never reaches a ceiling, and the test would pass for the wrong reason.
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        fail: set[str] | None = None,
        ledger: Path | None = None,
        calls_per_batch: int = 0,
        cost_per_call: float = 0.002,
    ) -> None:
        self.run_dir = run_dir
        self.fail = fail or set()
        self.ledger = ledger
        self.calls_per_batch = calls_per_batch
        self.cost_per_call = cost_per_call
        self.called: list[str] = []

    def batch(self, planned: M.PlannedBatch) -> tuple[bool, str]:
        self.called.append(planned.batch_id)
        if self.ledger is not None and self.calls_per_batch:
            with self.ledger.open("a", encoding="utf-8") as handle:
                for _ in range(self.calls_per_batch):
                    row = {
                        "kind": "model_call",
                        "cost_usd": self.cost_per_call,
                        "batch_id": planned.batch_id,
                    }
                    handle.write(json.dumps(row) + "\n")
        if planned.batch_id in self.fail:
            return False, f"{planned.batch_id}: judge exited 2"
        return True, "1 answers on disk"


def _drive(
    tmp_path: Path,
    plan: Path,
    ledger: Path,
    *,
    jobs: int = 1,
    runner: _StubRunner | None = None,
    max_calls: int | None = None,
    max_usd: float | None = None,
    calls_per_batch: int = 0,
    cost_per_call: float = 0.002,
    failures_before_stop: int = M.DEFAULT_FAILURES_BEFORE_STOP,
    plan_digest: str | None = None,
    digest_of: Any = None,
) -> tuple[int, M.Progress, _StubRunner]:
    run_dir = tmp_path / "runs"
    plan_batches = M.read_plan(plan)
    runner = runner or _StubRunner(
        run_dir, ledger=ledger, calls_per_batch=calls_per_batch, cost_per_call=cost_per_call
    )
    progress = M.Progress(
        plan=str(plan), run_dir=str(run_dir), live=True, jobs=jobs, batches_total=len(plan_batches)
    )
    kwargs: dict[str, Any] = {}
    if digest_of is not None:
        kwargs["digest_of"] = digest_of
    code = M.run_mass(
        batches=plan_batches,
        runner=runner,
        budget=M.Budget(max_calls, max_usd),
        ledger=ledger,
        progress=progress,
        progress_path=tmp_path / "progress.json",
        failures_before_stop=failures_before_stop,
        jobs=jobs,
        plan_digest=plan_digest,
        **kwargs,
    )
    return code, progress, runner


# --- the dry run ---------------------------------------------------------------------------------


def test_a_dry_run_buys_nothing_and_leaves_the_ledger_exactly_as_it_was(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0002", 2)])
    ledger = _ledger(tmp_path, rows=[_model_call(0.001)])
    before = ledger.read_bytes()
    code = M.main(
        [
            "--plan",
            str(plan),
            "--run-dir",
            str(tmp_path / "runs"),
            "--ledger",
            str(ledger),
            "--log-dir",
            str(tmp_path / "logs"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "nothing was bought" in out
    assert "10 calls at 5 per site" in out  # two batches, one site each
    assert ledger.read_bytes() == before
    assert not (tmp_path / "logs" / "progress.json").exists()


def test_a_dry_run_writes_no_ledger_file_at_all(tmp_path: Path) -> None:
    """The other half of the same claim: nothing to leave unchanged, because nothing was written."""
    plan = _plan(tmp_path, [("batch-0001", 1)])
    ledger = tmp_path / "LEDGER.jsonl"
    assert (
        M.main(
            [
                "--plan",
                str(plan),
                "--run-dir",
                str(tmp_path / "runs"),
                "--ledger",
                str(ledger),
                "--log-dir",
                str(tmp_path / "logs"),
            ]
        )
        == 0
    )
    assert not ledger.exists()


# --- what counts as done -------------------------------------------------------------------------


def test_a_batch_whose_artefacts_parse_and_whose_answers_are_on_disk_is_done(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs"
    _artefacts(run_dir, "batch-0001", calls=3)
    state, reason = M.batch_state(run_dir, "batch-0001")
    assert state == M.DONE
    assert reason == "3 answers on disk"


def test_a_truncated_model_json_is_broken_and_never_done(tmp_path: Path) -> None:
    """Half a file is not evidence: a kill in the middle of writing must not read as success."""
    run_dir = tmp_path / "runs"
    _artefacts(run_dir, "batch-0001", model_text='{"totals": {"calls": 1}, "judge')
    state, reason = M.batch_state(run_dir, "batch-0001")
    assert state == M.BROKEN
    assert "does not parse" in reason


def test_a_written_judgement_without_its_answer_file_is_broken(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs"
    _artefacts(run_dir, "batch-0001", calls=2, answers=False)
    state, reason = M.batch_state(run_dir, "batch-0001")
    assert state == M.BROKEN
    assert "answer missing" in reason


def test_a_count_that_disagrees_with_the_judgements_is_broken(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs"
    _artefacts(
        run_dir,
        "batch-0001",
        model_text=json.dumps({"totals": {"calls": 7}, "judgements": [{"wrote": False}]}),
    )
    state, reason = M.batch_state(run_dir, "batch-0001")
    assert state == M.BROKEN
    assert "claims 7 calls but carries 1" in reason


def test_a_batch_without_input_or_without_fetch_is_not_mistaken_for_done(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs"
    root = _artefacts(run_dir, "batch-0001")
    (root / "fetch.json").unlink()
    assert M.batch_state(run_dir, "batch-0001")[0] == M.PARTIAL
    (root / "input.json").unlink()
    assert M.batch_state(run_dir, "batch-0001")[0] == M.ABSENT


def test_a_done_batch_is_skipped_and_the_unfinished_one_is_run(tmp_path: Path) -> None:
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0002", 2)])
    ledger = _ledger(tmp_path)
    _artefacts(tmp_path / "runs", "batch-0001", calls=2)
    code, progress, runner = _drive(tmp_path, plan, ledger)
    assert code == 0
    assert runner.called == ["batch-0002"]
    assert progress.batches_skipped == 1
    assert progress.batches_done == 1


# --- the budget ----------------------------------------------------------------------------------


def test_the_call_ceiling_stops_between_batches_and_names_what_was_not_reached(
    tmp_path: Path,
) -> None:
    """The ceiling is reached by *this run's* calls, so the stub has to buy like `judge` does."""
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0002", 2), ("batch-0003", 3)])
    ledger = _ledger(tmp_path)
    code, progress, runner = _drive(tmp_path, plan, ledger, max_calls=75, calls_per_batch=40)
    assert code == 1
    assert runner.called == ["batch-0001", "batch-0002"]
    assert progress.stopped is not None
    assert progress.stopped.startswith("call ceiling reached: 80 >= 75 calls this run")
    assert "the ledger holds 80" in progress.stopped
    assert progress.not_reached == ["batch-0003"]


def test_a_ceiling_means_this_run_and_not_the_ledgers_whole_history(tmp_path: Path) -> None:
    """The ledger is shared with the pilot and six recall rounds, so a ceiling must not count them.

    With an absolute reading, `--max-calls 75` against a ledger that already held 500 calls would
    stop before the first batch and quietly mean something other than what it says.
    """
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0002", 2)])
    ledger = _ledger(tmp_path, rows=[_model_call(0.002)] * 500)
    code, progress, runner = _drive(tmp_path, plan, ledger, max_calls=75, calls_per_batch=40)
    assert code == 0
    assert runner.called == ["batch-0001", "batch-0002"]
    assert progress.stopped is None
    assert M.Spend.from_ledger(ledger).calls == 580  # well past the ceiling, and still running


def test_the_dollar_ceiling_stops_the_run(tmp_path: Path) -> None:
    """Three batches at 20 calls of one cent each: 0, 0.20, then 0.40 against a 0.25 ceiling."""
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0002", 2), ("batch-0003", 3)])
    ledger = _ledger(tmp_path)
    code, progress, runner = _drive(
        tmp_path, plan, ledger, max_usd=0.25, calls_per_batch=20, cost_per_call=0.01
    )
    assert code == 1
    assert runner.called == ["batch-0001", "batch-0002"]
    assert progress.stopped is not None and "dollar ceiling" in progress.stopped
    assert progress.not_reached == ["batch-0003"]


def test_a_ceiling_that_is_not_reached_lets_the_batches_run(tmp_path: Path) -> None:
    """Seeded with 200 calls and 5 dollars of history, so a run that buys 40 more still passes."""
    plan = _plan(tmp_path, [("batch-0001", 1)])
    ledger = _ledger(tmp_path, rows=[_model_call(0.025)] * 200)
    code, progress, runner = _drive(
        tmp_path, plan, ledger, max_calls=100, max_usd=6.0, calls_per_batch=40
    )
    assert code == 0
    assert runner.called == ["batch-0001"]
    assert progress.stopped is None


# --- the circuit breaker -------------------------------------------------------------------------


def test_the_circuit_breaker_trips_after_the_configured_number_of_failures(tmp_path: Path) -> None:
    batches = [(f"batch-{number:04d}", number) for number in range(1, 7)]
    plan = _plan(tmp_path, batches)
    ledger = _ledger(tmp_path)
    runner = _StubRunner(tmp_path / "runs", fail={b[0] for b in batches})
    code, progress, runner = _drive(tmp_path, plan, ledger, runner=runner, failures_before_stop=3)
    assert code == 1
    assert runner.called == ["batch-0001", "batch-0002", "batch-0003"]
    assert progress.stopped is not None and "circuit breaker" in progress.stopped
    assert progress.not_reached == ["batch-0004", "batch-0005", "batch-0006"]
    assert len(progress.failed) == 3
    assert progress.failed["batch-0001"] == "batch-0001: judge exited 2"


def test_a_success_clears_the_failure_count(tmp_path: Path) -> None:
    """Otherwise the breaker is just a counter and one bad patch ends an otherwise healthy run."""
    batches = [(f"batch-{number:04d}", number) for number in range(1, 7)]
    plan = _plan(tmp_path, batches)
    ledger = _ledger(tmp_path)
    runner = _StubRunner(tmp_path / "runs", fail={"batch-0002", "batch-0003", "batch-0005"})
    code, progress, runner = _drive(tmp_path, plan, ledger, runner=runner, failures_before_stop=3)
    assert runner.called == [b[0] for b in batches]  # nothing was cut off
    assert code == 1  # failures happened, so the run reports them
    assert progress.batches_failed == 3
    assert progress.stopped is None


# --- one writer per tree -------------------------------------------------------------------------


def test_the_source_digest_guard_stops_a_run_whose_sources_changed(tmp_path: Path) -> None:
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0002", 2)])
    ledger = _ledger(tmp_path)
    code, progress, runner = _drive(
        tmp_path,
        plan,
        ledger,
        plan_digest="the digest read at the start",
        digest_of=lambda: "something else",
    )
    assert code == 1
    assert runner.called == []
    assert progress.stopped == "the phase-3 sources changed while the run was going"


def test_a_matching_digest_is_not_in_the_way(tmp_path: Path) -> None:
    plan = _plan(tmp_path, [("batch-0001", 1)])
    ledger = _ledger(tmp_path)
    code, progress, runner = _drive(
        tmp_path, plan, ledger, plan_digest="same", digest_of=lambda: "same"
    )
    assert code == 0
    assert runner.called == ["batch-0001"]


# --- the progress file ---------------------------------------------------------------------------


def test_the_progress_file_is_readable_at_any_time_and_carries_the_spend(tmp_path: Path) -> None:
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0002", 2)])
    ledger = _ledger(
        tmp_path, rows=[_model_call(0.01), _model_call(0.02), {"kind": "fetch", "cost_usd": None}]
    )
    _drive(tmp_path, plan, ledger)
    payload = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))
    assert payload["batches_total"] == 2
    assert payload["batches_done"] == 2
    assert payload["spend"]["calls"] == 2
    assert payload["spend"]["cost_usd"] == pytest.approx(0.03)
    assert payload["spend"]["fetch_lines"] == 1
    assert payload["in_flight"] == []
    assert payload["stopped"] is None


def test_the_progress_file_is_written_atomically_and_leaves_no_temp_behind(tmp_path: Path) -> None:
    progress = M.Progress(plan="p", run_dir="r", live=True, jobs=1, batches_total=1)
    progress.write(tmp_path / "progress.json")
    assert (tmp_path / "progress.json").exists()
    assert not (tmp_path / "progress.json.tmp").exists()


def test_a_crash_between_the_write_and_the_swap_leaves_the_previous_progress_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the temp file: a reader never sees half a progress report.

    Asserting "no `.tmp` is left behind" does not test that - a plain write satisfies it too. This
    one kills the machine between the write and the swap, and the old file has to survive whole.
    """
    path = tmp_path / "progress.json"
    M.Progress(plan="p", run_dir="r", live=True, jobs=1, batches_total=1).write(path)
    before = path.read_text(encoding="utf-8")

    def exploding_replace(src: Any, dst: Any) -> None:
        raise OSError("the machine died between the write and the swap")

    monkeypatch.setattr(M.os, "replace", exploding_replace)
    with pytest.raises(OSError):
        M.Progress(plan="p", run_dir="r", live=True, jobs=1, batches_total=2).write(path)
    assert path.read_text(encoding="utf-8") == before


# --- the stage runner ----------------------------------------------------------------------------


def test_the_stage_runner_asks_the_cli_and_logs_to_a_file_the_driver_owns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        seen.append(list(argv))
        kwargs["stdout"].write("stage output line\n")
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(M.subprocess, "run", fake_run)
    runner = M.StageRunner(
        plan=tmp_path / "PLAN.jsonl",
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=True,
        python=Path("python"),
        runner=Path("run.py"),
    )
    assert runner.call("fetch", "batch-0001") == 0
    argv = seen[0]
    assert argv[:3] == ["python", "run.py", "fetch"]
    assert ["--batch-id", "batch-0001"] == argv[5:7]
    assert "--live" in argv
    log = (tmp_path / "logs" / "batch-0001.fetch.log").read_text(encoding="utf-8")
    assert "run.py fetch" in log  # the argv is logged before the call, so a crash still leaves why
    assert "stage output line" in log


def test_the_dry_runner_does_not_pass_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = M.StageRunner(
        plan=tmp_path / "PLAN.jsonl",
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=False,
        python=Path("python"),
        runner=Path("run.py"),
    )
    assert "--live" not in runner.argv("fetch", "batch-0001")
    assert "--live" not in runner.argv("judge", "batch-0001")


def test_the_driver_tells_fetch_which_pace_directory_to_use(tmp_path: Path) -> None:
    """The pace is named here, not by `run.py`'s default, and both modules mean the same path.

    That default is empty on purpose: one `fetch` process has nobody to pace against, while a
    machine-wide default would let a test - or a second run - take a host's lock and hold a live run
    up. Concurrency is what the driver creates, so the driver is what has to name the pace.
    """
    runner = M.StageRunner(
        plan=tmp_path / "PLAN.jsonl",
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=True,
        python=Path("python"),
        runner=Path("run.py"),
    )
    argv = runner.argv("fetch", "batch-0001")
    assert argv[argv.index("--pacing-dir") + 1] == str(M.DEFAULT_PACING_DIR)
    assert "--pacing-dir" not in runner.argv("judge", "batch-0001")  # no sockets there
    assert M.DEFAULT_PACING_DIR == R.DEFAULT_PACING_DIR  # two modules, one path


def test_the_driver_can_be_told_not_to_pace(tmp_path: Path) -> None:
    runner = M.StageRunner(
        plan=tmp_path / "PLAN.jsonl",
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=True,
        pacing_dir=None,
        python=Path("python"),
        runner=Path("run.py"),
    )
    assert "--pacing-dir" not in runner.argv("fetch", "batch-0001")


def test_a_stage_that_runs_too_long_is_recorded_as_a_failure_rather_than_killing_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        raise M.subprocess.TimeoutExpired(cmd=argv, timeout=1.0)

    monkeypatch.setattr(M.subprocess, "run", fake_run)
    runner = M.StageRunner(
        plan=tmp_path / "PLAN.jsonl",
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=True,
        stage_timeout=1.0,
        python=Path("python"),
        runner=Path("run.py"),
    )
    assert runner.call("fetch", "batch-0001") == -9
    log = (tmp_path / "logs" / "batch-0001.fetch.log").read_text(encoding="utf-8")
    assert "exceeded 1s and was killed" in log


def test_a_batch_that_ends_incomplete_is_a_failure_even_though_every_stage_exited_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every stage returning 0 is a claim; the artefacts decide."""
    monkeypatch.setattr(
        M.subprocess,
        "run",
        lambda argv, **kwargs: types.SimpleNamespace(returncode=0),
    )
    runner = M.StageRunner(
        plan=tmp_path / "PLAN.jsonl",
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=True,
        python=Path("python"),
        runner=Path("run.py"),
    )
    ok, detail = runner.batch(M.PlannedBatch("batch-0001", 1, 1))
    assert not ok
    assert detail.startswith("after all three stages: absent")


# --- the plan and the ledger as input -------------------------------------------------------------


def test_a_plan_line_without_an_ordinal_is_refused_with_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "PLAN.jsonl"
    path.write_text(json.dumps({"batch_id": "batch-0001", "sites": [{"site_id": SITE}]}), "utf-8")
    with pytest.raises(M.PlanError) as excinfo:
        M.read_plan(path)
    assert "PLAN.jsonl:1" in str(excinfo.value)


def test_a_duplicate_batch_id_is_refused(tmp_path: Path) -> None:
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0001", 2)])
    with pytest.raises(M.PlanError):
        M.read_plan(plan)


def test_a_batch_with_no_sites_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "PLAN.jsonl"
    path.write_text(json.dumps({"batch_id": "batch-0001", "ordinal": 1, "sites": []}), "utf-8")
    with pytest.raises(M.PlanError):
        M.read_plan(path)


def test_an_unknown_batch_id_in_only_is_refused_rather_than_silently_ignored(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path, [("batch-0001", 1)])
    with pytest.raises(M.PlanError) as excinfo:
        M.main(
            [
                "--plan",
                str(plan),
                "--run-dir",
                str(tmp_path / "runs"),
                "--ledger",
                str(tmp_path / "L.jsonl"),
                "--log-dir",
                str(tmp_path / "logs"),
                "--only",
                "batch-0009",
            ]
        )
    assert "batch-0009" in str(excinfo.value)


def test_a_torn_trailing_ledger_line_is_named_while_an_inner_one_raises(tmp_path: Path) -> None:
    """A kill between write and flush is real; damage *inside* the file means a charge may be lost."""
    torn = _ledger(tmp_path, rows=[_model_call(0.01)], torn='{"kind": "model_ca')
    spend = M.Spend.from_ledger(torn)
    assert spend.calls == 1
    assert spend.torn_lines == 1
    damaged = tmp_path / "DAMAGED.jsonl"
    damaged.write_text('{"kind": "model_ca\n' + json.dumps(_model_call(0.01)) + "\n", "utf-8")
    with pytest.raises(M.LedgerDamage):
        M.Spend.from_ledger(damaged)


def test_the_ledger_of_a_run_that_never_started_is_not_an_error(tmp_path: Path) -> None:
    spend = M.Spend.from_ledger(tmp_path / "nothing.jsonl")
    assert spend.calls == 0
    assert spend.cost_usd == 0.0


def test_as_many_workers_are_used_as_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--jobs` is the one knob that makes 334 batches a night's work instead of a week's."""
    seen: list[int] = []
    real = M.ThreadPoolExecutor

    def factory(*, max_workers: int, **kwargs: Any) -> Any:
        seen.append(max_workers)
        return real(max_workers=max_workers, **kwargs)

    monkeypatch.setattr(M, "ThreadPoolExecutor", factory)
    plan = _plan(tmp_path, [("batch-0001", 1), ("batch-0002", 2), ("batch-0003", 3)])
    _drive(tmp_path, plan, _ledger(tmp_path), jobs=3)
    assert seen == [3]


def test_every_stage_argv_is_accepted_by_the_real_cli(tmp_path: Path) -> None:
    """The flags are checked against `run.py` itself, not against a memory of its flags.

    Stubbing `subprocess.run` proves the stub. On 2026-09-21 that stub let three defects through
    that would have stopped the very first live batch: `prepare` was sent `--ledger` and `--live`,
    neither of which it has - exit 2 on every batch - and it was never sent the plan at all.
    """
    plan = tmp_path / "PLAN.jsonl"
    plan.write_text("", encoding="utf-8")
    runner = M.StageRunner(
        plan=plan,
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=True,
        python=Path("python"),
        runner=Path("run.py"),
    )
    parser = R.build_parser()  # SystemExit(2) if a stage does not take what we send it
    for stage in ("prepare", "fetch", "judge"):
        parsed = parser.parse_args(runner.argv(stage, "batch-0001")[2:])
        assert parsed.run_dir == str(tmp_path / "runs")
    assert parser.parse_args(runner.argv("prepare", "batch-0001")[2:]).batch_id == ["batch-0001"]
    assert parser.parse_args(runner.argv("fetch", "batch-0001")[2:]).batch_id == "batch-0001"
    assert parser.parse_args(runner.argv("judge", "batch-0001")[2:]).batch_id == "batch-0001"


def test_prepare_is_given_the_plan_and_neither_the_ledger_nor_live(tmp_path: Path) -> None:
    """`prepare` without `--plan` is silent, not loud - and that is the dangerous one.

    It would prepare the default worklist batch under a batch id that exists in both plans, and the
    run would then fetch and judge those sites with nothing raising anywhere.
    """
    plan = tmp_path / "PLAN.jsonl"
    plan.write_text("", encoding="utf-8")
    runner = M.StageRunner(
        plan=plan,
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=True,
        python=Path("python"),
        runner=Path("run.py"),
    )
    argv = runner.argv("prepare", "batch-0001")
    prepared = R.build_parser().parse_args(argv[2:])
    assert Path(prepared.plan) == plan
    # `prepare` has no ledger and no `--live`; the proof is the namespace it parses into.
    assert not hasattr(prepared, "ledger")
    assert not hasattr(prepared, "live")
    assert "--ledger" not in argv
    assert "--live" not in argv
