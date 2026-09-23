"""Does the Phase-4 driver wire every stage to the contract's function, print the line the mass run
reads, reuse Phase 3's guards, and draw audit samples nobody can steer?

Work item WB-B4 (`phase4/run4.py`, `phase4/mass4.py`, `phase4/audit4.py`). Track A's stages are
merged: their batch functions are replaced by stand-ins bound to the real signatures (a call the
real function refuses raises here too), and their live fetcher is the real one. The modules not
merged yet (`verify4`, `write4`, `plan4` for `plan`) are recording fakes put into `sys.modules`. No
socket, process, model or database is touched (`subprocess.run` is made to raise wherever a spawn
would be a bug).
"""

from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import json
import subprocess
import sys
import threading
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

PHASE_PARENT = Path(__file__).resolve().parents[2] / "scripts" / "remediation"
if str(PHASE_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import mass_run as MR  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import run as R3  # noqa: E402
from phase4 import assemble as A  # noqa: E402
from phase4 import audit4 as AU  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import mass4 as M4  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import review4 as RV  # noqa: E402
from phase4 import route_stage as RS  # noqa: E402
from phase4 import run4 as R4  # noqa: E402
from phase4 import select_stage as SEL  # noqa: E402
from phase4 import sources_stage as S1  # noqa: E402

from tests.remediation import p4_fixtures as X  # noqa: E402

SELECT = "DESC: W1\nDESC: W2\nDESC: W5 -a1\nDESC: W6 -p1\nCARD: W2\n"


def _script(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    """The one real process this suite starts: `run4.py` itself, isolated (`-I`), never a model."""
    return subprocess.run(argv, cwd=cwd, capture_output=True, timeout=60, check=False)


def _fake(monkeypatch: pytest.MonkeyPatch, name: str, **functions: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in functions.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict, str]:
    code = R4.main(argv)
    out = capsys.readouterr().out
    lines = out.rstrip("\n").split("\n")
    assert lines[-1] == f"STAGE_EXIT={code}"
    return code, json.loads("\n".join(lines[:-1])), out


def _plan(tmp_path: Path, sites: list[M.PlanSite], batch: str = "p4-0001") -> Path:
    plan = tmp_path / "PLAN4.jsonl"
    row = {"batch_id": batch, "ordinal": 1, "sites": [site.to_dict() for site in sites]}
    plan.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return plan


# ------------------------------------------------------------------------------------ run4


def test_prepare_copies_the_plan_line_write_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(tmp_path, [X.plan_site("site-1")])
    run_dir = tmp_path / "runs" / "pilot"
    argv = ["prepare", "--run-dir", str(run_dir), "--batch-id", "p4-0001", "--plan", str(plan)]
    code, report, _ = _run(capsys, argv)
    assert code == 0 and report["wrote"] is True
    assert B.read_batch(run_dir / "p4-0001")[1][0].site_id == "site-1"
    assert _run(capsys, argv)[1]["wrote"] is False  # the same bytes again: nothing written
    _plan(tmp_path, [X.plan_site("site-2")])
    with pytest.raises(F.EvidenceConflict):
        R4.main(argv)


def test_prepare_refuses_a_malformed_plan_site(tmp_path: Path) -> None:
    broken = {**X.plan_site().to_dict(), "lat": True}
    plan = tmp_path / "PLAN4.jsonl"
    plan.write_text(json.dumps({"batch_id": "p4-0001", "ordinal": 1, "sites": [broken]}) + "\n")
    with pytest.raises(ValueError, match="lat"):
        R4.main(
            ["prepare", "--run-dir", str(tmp_path), "--batch-id", "p4-0001", "--plan", str(plan)]
        )
    assert not (tmp_path / "p4-0001" / M.INPUT_FILE).exists()  # refused before anything is written


def test_a_batch_command_refuses_a_foreign_or_unprepared_batch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a Phase-4 batch"):
        R4.main(["assemble", "--run-dir", str(tmp_path), "--batch-id", "batch-0001"])
    with pytest.raises(ValueError, match="no input.json"):
        R4.main(["assemble", "--run-dir", str(tmp_path), "--batch-id", "p4-0001"])


def test_the_streams_are_utf8_before_anything_is_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    R4.utf8_streams()
    print("Göbekli Tepe – Ṭūr ʿAbdīn")
    stream.flush()
    assert raw.getvalue().decode("utf-8").startswith("Göbekli Tepe – Ṭūr ʿAbdīn")


class _Closing:
    """A fetcher or searcher stand-in that records its close."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False
        self.endpoint = "https://search.example/v1"

    def get(self, url: str) -> F.FetchedPage:
        raise AssertionError(f"{self.name} was asked for {url}; no socket in a test")

    def close(self) -> None:
        self.closed = True


def _prepared(tmp_path: Path) -> Path:
    return X.make_batch(tmp_path, [X.w_site("site-1")])


def _bound(real: Callable[..., Any], seen: dict[str, Any], result: Any) -> Callable[..., Any]:
    """A stand-in for a Track-A function that refuses what the real one refuses (contract rule 4):
    every call is bound to the real signature first, so a missing, extra or renamed keyword raises
    here as it would there. The bound arguments are recorded."""
    signature = inspect.signature(real)

    def stand_in(*args: Any, **kwargs: Any) -> Any:
        seen.update(signature.bind(*args, **kwargs).arguments)
        return result

    return stand_in


def test_sources_hands_track_a_its_own_live_fetcher_and_the_phase3_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fetcher is Track A's real `open_fetcher` (nothing about it is replaced here): the
    host-capped, paced client the stage expects, built and closed by the driver."""
    batch_dir = _prepared(tmp_path)
    seen: dict[str, Any] = {}
    monkeypatch.setattr(S1, "sources_batch", _bound(S1.sources_batch, seen, 3))
    argv = ["sources", "--run-dir", str(batch_dir.parent), "--batch-id", "p4-0001"]
    assert _run(capsys, [*argv, "--ledger", str(tmp_path / "L.jsonl")])[0] == 0  # no --live
    assert seen == {}
    live = [*argv, "--live", "--pacing-dir", str(tmp_path / "pace")]
    code, _, _ = _run(capsys, [*live, "--phase3-run", str(tmp_path / "mass")])
    assert code == 3  # the stage's own code is the exit line
    assert seen["batch_dir"] == batch_dir and seen["phase3_run"] == tmp_path / "mass"
    assert isinstance(seen["fetcher"], F.PacedFetcher)
    assert isinstance(seen["fetcher"]._inner, S1.HostCappedFetcher)
    assert seen["now"].tzinfo is not None
    _run(capsys, live)
    assert seen["phase3_run"] == R3.DEFAULT_SOURCE_RUN_DIR  # the Phase-3 mass run


def test_routes_gets_the_live_fetcher_the_search_seams_and_its_search_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = _prepared(tmp_path)
    search = _Closing("search")
    seams = (search, lambda: {"quota": "probe"}, lambda: None)
    opened: dict[str, Any] = {}
    signature = inspect.signature(RS.open_search)

    @contextlib.contextmanager
    def open_search(*args: Any, **kwargs: Any) -> Iterator[tuple[Any, Any, Any]]:
        opened.update(signature.bind(*args, **kwargs).arguments)
        yield seams
        search.close()

    seen: dict[str, Any] = {}
    monkeypatch.setattr(RS, "open_search", open_search)
    monkeypatch.setattr(RS, "routes_batch", _bound(RS.routes_batch, seen, 0))
    argv = ["routes", "--run-dir", str(batch_dir.parent), "--batch-id", "p4-0001", "--live"]
    code, report, _ = _run(capsys, [*argv, "--max-searches", "7", "--pacing-dir", str(tmp_path)])
    assert code == 0 and report["max_searches"] == 7
    assert opened == {"pacing_dir": tmp_path}
    assert (seen["searcher"], seen["probe"], seen["wait"]) == seams
    assert seen["max_searches"] == 7 and seen["now"].tzinfo is not None
    assert isinstance(seen["fetcher"], F.PacedFetcher)
    assert isinstance(seen["fetcher"]._inner, S1.HostCappedFetcher)
    assert search.closed


def test_verify_is_track_cs_batch_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = _prepared(tmp_path)
    calls: list[Path] = []
    _fake(monkeypatch, R4.VERIFY4, verify_batch=lambda path: calls.append(path) or 1)
    code, _, _ = _run(
        capsys, ["verify", "--run-dir", str(batch_dir.parent), "--batch-id", "p4-0001"]
    )
    assert code == 1 and calls == [batch_dir]


def test_plan_and_writeplan_forward_their_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    got: dict[str, list[str]] = {}
    _fake(monkeypatch, R4.PLAN4, main=lambda argv: got.setdefault("plan", argv) and 0)
    _fake(monkeypatch, R4.WRITE4, main=lambda argv: got.setdefault("write", argv) and 5)
    assert _run(capsys, ["plan", "--out", "x.jsonl"])[0] == 0
    assert _run(capsys, ["writeplan", "--run-dir", "r"])[0] == 5
    assert got == {"plan": ["--out", "x.jsonl"], "write": ["--run-dir", "r"]}


def test_select_runs_the_three_model_stages_and_a_dry_run_buys_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = _prepared(tmp_path)
    ledger = tmp_path / "L.jsonl"
    argv = ["select", "--run-dir", str(batch_dir.parent), "--batch-id", "p4-0001"]
    code, report, _ = _run(capsys, [*argv, "--ledger", str(ledger)])
    assert code == 0 and report["live"] is False and report["sites"][0]["prompt_chars"] > 0
    assert not ledger.exists()
    runner = X.ScriptedRunner({("site-1", "select"): SELECT})
    monkeypatch.setattr(R4, "pi_runner", lambda timeout: runner)
    code, report, _ = _run(capsys, [*argv, "--ledger", str(ledger), "--live"])
    assert code == 0 and report["stages"] == ["select", "translate", "restricted"]
    for name in (B.SELECTIONS_FILE, B.TRANSLATIONS_FILE, B.RESTATEMENTS_FILE):
        assert (batch_dir / name).exists(), name
    assert len(X.ledger_lines(ledger)) == 1


def test_a_select_that_could_not_call_names_the_error_for_the_spawn_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = _prepared(tmp_path)
    failed = MS.ModelCallFailed("site-1/select: 'pi.cmd' could not be started: [WinError 2]")
    monkeypatch.setattr(
        R4, "pi_runner", lambda timeout: X.ScriptedRunner({("site-1", "select"): failed})
    )
    argv = ["select", "--run-dir", str(batch_dir.parent), "--batch-id", "p4-0001", "--live"]
    code, report, out = _run(capsys, [*argv, "--ledger", str(tmp_path / "L.jsonl")])
    assert code == 2 and report["stage"] == "select"
    assert MR.spawn_failure(code, out)  # mass_run's own reader finds the error


def _selected_batch(tmp_path: Path, site_id: str = "site-1", batch: str = "p4-0001") -> Path:
    batch_dir = X.make_batch(
        tmp_path,
        [X.w_site(site_id, raw_data={"description_citations": [], "k": 1})],
        batch=batch,
    )
    SEL.select_batch(
        batch_dir,
        ledger=tmp_path / "L.jsonl",
        runner=X.ScriptedRunner({(site_id, "select"): SELECT}),
    )
    B.write_records(batch_dir / B.TRANSLATIONS_FILE, [])
    B.write_records(batch_dir / B.RESTATEMENTS_FILE, [])
    assert A.assemble_batch(batch_dir) == 0
    return batch_dir


def test_review_re_verifies_through_verify_site_with_the_contracts_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = _selected_batch(tmp_path)
    seen: list[dict[str, Any]] = []

    def verify_site(site: M.PlanSite, assembly: M.Assembly, **kw: Any) -> tuple[M.Hold, ...]:
        seen.append({"site": site, "assembly": assembly, **kw})
        return ()

    def new_raw_data(old: dict | None, assembly: M.Assembly) -> dict:
        return {**(old or {}), "made_by": "write4"}

    _fake(monkeypatch, R4.VERIFY4, verify_site=verify_site)
    _fake(monkeypatch, R4.WRITE4, new_raw_data=new_raw_data)
    answer = "R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: KEEP\nCARD: KEEP"
    monkeypatch.setattr(
        R4, "pi_runner", lambda timeout: X.ScriptedRunner({("site-1", "review"): answer})
    )
    argv = ["review", "--run-dir", str(batch_dir.parent), "--batch-id", "p4-0001", "--live"]
    code, _, _ = _run(capsys, [*argv, "--ledger", str(tmp_path / "L.jsonl")])
    assert code == 0
    (call,) = seen
    assert set(call) == {"site", "assembly", "metas", "texts", "quotes", "new_raw_data"}
    assert call["metas"]["W"] == json.loads(X.wiki_doc("W", X.ARTICLE).to_json())
    assert call["texts"] == {"W": X.ARTICLE}
    assert call["quotes"] == A.quotes_of(call["assembly"], {"W": X.ARTICLE})
    assert call["new_raw_data"] == {"description_citations": [], "k": 1, "made_by": "write4"}


def test_holds4_is_every_batch_hold_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = tmp_path / "runs" / "pilot"
    one = M.Hold(site_id="a", scope=M.HoldScope.SITE, reason=M.HoldReason.NO_SOURCE, detail="x")
    two = M.Hold(site_id="b", scope=M.HoldScope.CARD, reason=M.HoldReason.V10, detail="y")
    for batch, holds in (("p4-0001", [one, two]), ("p4-0002", [one])):
        (run_dir / batch).mkdir(parents=True)
        B.append_holds(run_dir / batch, holds)
    code, report, _ = _run(capsys, ["holds", "--run-dir", str(run_dir)])
    assert code == 0 and report["holds"] == 2
    assert M.load_jsonl(run_dir / R4.HOLDS4_FILE, M.Hold) == [one, two]


# ----------------------------------------------------------------------------------- mass4


def test_read_plan4_refuses_what_is_not_a_phase4_plan(tmp_path: Path) -> None:
    good = _plan(tmp_path, [X.plan_site("s1"), X.plan_site("s2")])
    (planned,) = M4.read_plan4(good)
    assert (planned.batch_id, planned.sites) == ("p4-0001", 2)
    for broken, match in (
        ({"batch_id": "batch-0001", "ordinal": 1, "sites": [X.plan_site().to_dict()]}, "Phase-4"),
        ({"batch_id": "p4-0001", "ordinal": True, "sites": [X.plan_site().to_dict()]}, "ordinal"),
        ({"batch_id": "p4-0001", "ordinal": 1, "sites": []}, "no sites"),
        (
            {"batch_id": "p4-0001", "ordinal": 1, "sites": [X.plan_site().to_dict()] * 2},
            "planned twice",
        ),
    ):
        good.write_text(json.dumps(broken) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=match):
            M4.read_plan4(good)


def test_the_exit_line_is_the_last_one_printed() -> None:
    assert M4.stage_exit('{\n "error": null\n}\nSTAGE_EXIT=0\n') == 0
    assert M4.stage_exit("STAGE_EXIT=0\nretry\nSTAGE_EXIT=2\n") == 2
    assert M4.stage_exit("Traceback (most recent call last):\nKeyError\n") is None
    assert M4.stage_exit("xSTAGE_EXIT=0\n") is None
    # A child's text-mode stdout on Windows ends its lines in \r\n; the line is still read.
    assert M4.stage_exit('{\r\n "error": null\r\n}\r\nSTAGE_EXIT=4\r\n') == 4


def test_run4_runs_as_a_script_from_any_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "pilot"
    run_dir.mkdir(parents=True)
    done = _script(
        [sys.executable, "-I", str(M4.RUN4), "holds", "--run-dir", str(run_dir)], cwd=tmp_path
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode("utf-8").splitlines()[-1] == "STAGE_EXIT=0"


def _runner(
    tmp_path: Path, *, live: bool = True, ledger: Path | None = None
) -> M4.Phase4StageRunner:
    return M4.Phase4StageRunner(
        plan=tmp_path / "PLAN4.jsonl",
        run_dir=tmp_path / "runs" / "pilot",
        ledger=ledger or tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=live,
        budget=MR.Budget(max_usd=15.0, max_searches=700),
        pacing_dir=tmp_path / "pace",
        python=Path(sys.executable),
    )


def test_every_stage_argv_is_accepted_by_the_real_run4_parser(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    parser = R4.build_parser()
    for stage in M4.STAGES4:
        argv = runner.argv(stage, "p4-0001")
        assert argv[:3] == [sys.executable, str(M4.RUN4), stage]
        args = parser.parse_args(argv[2:])
        assert args.command == stage
        assert ("--live" in argv) == (stage in M4.LIVE_STAGES)
        assert ("--pacing-dir" in argv) == (stage in M4.PACED_STAGES)
    assert runner.argv("routes", "p4-0001")[-2:] == ["--max-searches", "700"]
    assert "--live" not in _runner(tmp_path, live=False).argv("select", "p4-0001")


def test_the_search_allowance_counts_this_runs_searches_only(tmp_path: Path) -> None:
    ledger = tmp_path / "L.jsonl"
    line = {
        "kind": "fetch", "stage": "finder", "batch_id": "p4-0001",
        "label": "s/minimax_search.name", "url": "https://x", "outcome": "ok",
    }  # fmt: skip
    ledger.write_text(json.dumps(line) + "\n", encoding="utf-8")
    runner = _runner(tmp_path, ledger=ledger)  # one search before this run: not counted
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line) + "\n" + json.dumps(line) + "\n")
    assert runner.searches_left() == 698


def test_parallel_routes_stages_never_share_one_search_allowance(tmp_path: Path) -> None:
    """With `--jobs 2` two batches run at once. The allowance a routes stage is told is what is
    left when it starts; two routes stages that started together would each be told the whole
    remainder and could spend it twice. They take turns: the second is told what the first left."""
    ledger = tmp_path / "L.jsonl"
    runner = M4.Phase4StageRunner(
        plan=tmp_path / "PLAN4.jsonl",
        run_dir=tmp_path / "runs" / "pilot",
        ledger=ledger,
        log_dir=tmp_path / "logs",
        live=True,
        budget=MR.Budget(max_usd=15.0, max_searches=10),
        pacing_dir=None,
        python=Path(sys.executable),
    )
    first_in_routes = threading.Event()
    second_in_routes = threading.Event()
    told: dict[str, int] = {}
    line = {
        "kind": "fetch", "stage": "finder", "batch_id": "p4-0001",
        "label": "s/minimax_search.name", "url": "https://x", "outcome": "ok",
    }  # fmt: skip

    def call(stage: str, batch_id: str) -> int:
        log = runner.log_dir / f"{batch_id}.{stage}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        if stage == "routes":
            argv = runner.argv(stage, batch_id)
            allowance = int(argv[argv.index("--max-searches") + 1])
            told[batch_id] = allowance
            if batch_id == "p4-0001":
                first_in_routes.set()
                second_in_routes.wait(timeout=1.0)  # the other batch's routes, if it can start
            else:
                second_in_routes.set()
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write("".join(json.dumps(line) + "\n" for _ in range(allowance)))
        with log.open("a", encoding="utf-8") as handle:
            handle.write("STAGE_EXIT=0\n")
        return 0

    runner.call = call  # type: ignore[method-assign]
    first = threading.Thread(
        target=runner.batch, args=(MR.PlannedBatch(batch_id="p4-0001", ordinal=1, sites=1),)
    )
    first.start()
    assert first_in_routes.wait(timeout=5.0)
    runner.batch(MR.PlannedBatch(batch_id="p4-0002", ordinal=2, sites=1))
    first.join(timeout=5.0)
    assert told == {"p4-0001": 10, "p4-0002": 0}
    assert MR.Spend.from_ledger(ledger).searches == 10


def _stub_calls(runner: M4.Phase4StageRunner, outputs: dict[str, tuple[int, str]]) -> list[str]:
    """Replace the process spawn: each stage appends its scripted output to its own log."""
    called: list[str] = []

    def call(stage: str, batch_id: str) -> int:
        called.append(stage)
        code, text = outputs.get(stage, (0, "STAGE_EXIT=0\n"))
        log = runner.log_dir / f"{batch_id}.{stage}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(text)
        return code

    runner.call = call  # type: ignore[method-assign]
    return called


def test_a_non_zero_exit_line_stops_the_run_whatever_the_process_said(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    called = _stub_calls(runner, {"select": (0, '{\n "error": "pi died"\n}\nSTAGE_EXIT=2\n')})
    ok, detail = runner.batch(MR.PlannedBatch(batch_id="p4-0001", ordinal=1, sites=1))
    assert not ok and "select STAGE_EXIT=2" in detail
    assert called == ["prepare", "sources", "routes", "select"]
    assert runner.stop_reason is not None and "pi died" in runner.stop_reason


def test_a_stage_without_an_exit_line_fails_the_batch_for_the_circuit_breaker(
    tmp_path: Path,
) -> None:
    runner = _runner(tmp_path)
    _stub_calls(runner, {"sources": (0, "Traceback (most recent call last):\n")})
    ok, detail = runner.batch(MR.PlannedBatch(batch_id="p4-0001", ordinal=1, sites=1))
    assert not ok and "printed no STAGE_EXIT= line" in detail
    assert runner.stop_reason is None


def test_a_zero_exit_line_goes_on_even_when_the_process_code_is_not_zero(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    called = _stub_calls(runner, {"sources": (1, "STAGE_EXIT=0\n")})
    ok, detail = runner.batch(MR.PlannedBatch(batch_id="p4-0001", ordinal=1, sites=1))
    assert called == list(M4.STAGES4)
    assert not ok and detail.startswith("after every stage")  # nothing was really written


def _reviewed(tmp_path: Path, site_id: str = "site-1", batch: str = "p4-0001") -> Path:
    batch_dir = _selected_batch(tmp_path, site_id, batch)
    answer = "R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: KEEP\nCARD: KEEP"
    RV.review_batch(
        batch_dir,
        ledger=tmp_path / "L.jsonl",
        runner=X.ScriptedRunner({(site_id, "review"): answer}),
        reverify=lambda site, assembly: (),
    )
    return batch_dir


def test_done_is_a_finished_review_over_the_assembly_on_disk(tmp_path: Path) -> None:
    batch_dir = _selected_batch(tmp_path)
    run_dir = batch_dir.parent
    assert M4.batch_done(run_dir, "p4-0001") == (False, "no review4.json")
    batch_dir = _reviewed(tmp_path / "again")
    run_dir = batch_dir.parent
    assert M4.batch_done(run_dir, "p4-0001")[0]
    assembly = batch_dir / M.ASSEMBLY_FILE
    assembly.write_bytes(assembly.read_bytes() + b"")
    A.assemble_batch(batch_dir)  # the same bytes: still done
    assert M4.batch_done(run_dir, "p4-0001")[0]
    assembly.write_text("", encoding="utf-8")
    assert M4.batch_done(run_dir, "p4-0001") == (
        False,
        "assembly.jsonl is not the one the review wrote",
    )


def test_a_done_batch_starts_no_stage(tmp_path: Path) -> None:
    batch_dir = _reviewed(tmp_path)
    runner = _runner(tmp_path)
    runner.run_dir = batch_dir.parent
    called = _stub_calls(runner, {})
    ok, detail = runner.batch(MR.PlannedBatch(batch_id="p4-0001", ordinal=1, sites=1))
    assert ok and detail.startswith("already done") and called == []


def _args(tmp_path: Path, plan: Path, *extra: str) -> argparse.Namespace:
    return M4.build_parser().parse_args(
        ["--plan", str(plan), "--run-dir", str(tmp_path / "runs" / "pilot"),
         "--ledger", str(tmp_path / "L.jsonl"), "--log-dir", str(tmp_path / "logs"), *extra]
    )  # fmt: skip


def test_the_live_run_is_mass_runs_loop_with_phase4s_digest_and_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(tmp_path, [X.plan_site("site-1")])
    (tmp_path / "runs" / "pilot").mkdir(parents=True)
    seen: dict[str, Any] = {}

    def run_mass(**kw: Any) -> int:
        seen.update(kw)
        return 0

    monkeypatch.setattr(MR, "run_mass", run_mass)
    assert M4.drive(_args(tmp_path, plan, "--live")) == 0
    assert seen["plan_digest"] == MR.package_digest(root=M4.PHASE4_DIR)
    assert seen["plan_digest"] != MR.package_digest()
    assert seen["digest_of"]() == seen["plan_digest"]
    assert (seen["budget"].max_usd, seen["budget"].max_searches) == (15.0, 700)
    assert isinstance(seen["runner"], M4.Phase4StageRunner)
    assert seen["stop_of"]() is None
    assert (tmp_path / "runs" / "pilot" / R4.HOLDS4_FILE).exists()


def test_a_dry_run_starts_nothing_and_writes_no_ledger_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan(tmp_path, [X.plan_site("site-1")])

    def no_spawn(*args: Any, **kw: Any) -> None:
        raise AssertionError("a dry run started a process")

    monkeypatch.setattr(MR.subprocess, "run", no_spawn)
    assert M4.drive(_args(tmp_path, plan)) == 0
    assert not (tmp_path / "L.jsonl").exists()


# ----------------------------------------------------------------------------------- audit4


def test_a_draw_is_seeded_sorted_and_never_takes_an_excluded_id() -> None:
    ids = [f"site-{i:03d}" for i in range(200)]
    first = AU.draw_sample(ids, seed=20260922, count=10, exclude={"site-005"})
    assert first == AU.draw_sample(
        list(reversed(ids)), seed=20260922, count=10, exclude={"site-005"}
    )
    assert first == sorted(first) and len(first) == 10 and "site-005" not in first
    assert first != AU.draw_sample(ids, seed=1, count=10, exclude=set())
    assert AU.draw_sample(ids, seed=1, count=3, exclude=set(ids[3:])) == ids[:3]


def test_a_stratum_smaller_than_the_count_is_taken_whole() -> None:
    assert AU.draw_sample(["b", "a", "b"], seed=7, count=5, exclude={"c"}) == ["a", "b"]
    with pytest.raises(ValueError, match="no sample"):
        AU.draw_sample(["a"], seed=7, count=0, exclude=set())


def test_the_sheet_shows_every_sentence_beside_its_passage_and_never_the_reviewer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = _selected_batch(tmp_path)
    answer = "R1: KEEP\nR2: KEEP\nR3: KEEP\nR4: DROP SECRET REVIEWER NOTE\nCARD: KEEP"
    RV.review_batch(
        batch_dir,
        ledger=tmp_path / "L.jsonl",
        runner=X.ScriptedRunner({("site-1", "review"): answer}),
        reverify=lambda site, assembly: (),
    )
    ids = tmp_path / "ids.txt"
    ids.write_text("site-1\n", encoding="utf-8")
    out = tmp_path / "sheet.md"
    code = AU.main(
        ["sheet", "--run-dir", str(batch_dir.parent), "--site-ids", str(ids), "--out", str(out)]
    )
    assert code == 0 and capsys.readouterr().out.rstrip().endswith("STAGE_EXIT=0")
    sheet = out.read_text(encoding="utf-8")
    assert "SECRET REVIEWER NOTE" not in sheet and "DROP" not in sheet
    assert sheet.count("- verdict: SUPPORTED | UNSUPPORTED | WRONG_SITE") == 3
    assert "- passage: The temple was built c. 2500 BC by a farming community" in sheet
    assert "- verdict: CONTAINED | NOT_CONTAINED" in sheet
    assert "[1] Wikipedia: Stone Temple - " + X.PERMALINK in sheet


def _ids_file(path: Path, *ids: str) -> str:
    path.write_text("".join(f"{site_id}\n" for site_id in ids), encoding="utf-8")
    return str(path)


def test_the_draw_command_prints_the_sample(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    batch_dir = _reviewed(tmp_path)
    written = _ids_file(tmp_path / "written.txt", "site-1")
    argv = ["draw", "--run-dir", str(batch_dir.parent), "--seed", "3", "--count", "5"]
    assert AU.main([*argv, "--written", written]) == 0
    assert capsys.readouterr().out.split() == ["site-1", "STAGE_EXIT=0"]


def test_only_a_finished_review_counts_and_a_later_site_hold_takes_a_site_out(
    tmp_path: Path,
) -> None:
    """The auditor judges reviewed text: a batch whose review never finished, and a site a later
    stage held after it, are not in the population the samples are drawn from."""
    run_dir = _reviewed(tmp_path, "site-1", "p4-0001").parent
    _selected_batch(tmp_path, "site-2", "p4-0002")  # assembled, never reviewed
    third = _reviewed(tmp_path, "site-3", "p4-0003")
    assert M4.batch_done(run_dir, "p4-0002") == (False, "no review4.json")
    assert set(AU.reviewed_sites(run_dir)) == {"site-1", "site-3"}
    B.append_holds(
        third,
        [
            M.Hold(
                site_id="site-3",
                scope=M.HoldScope.SITE,
                reason=M.HoldReason.LANE_R_CLOSED,
                detail="held after the review",
            )
        ],
    )
    assert set(AU.reviewed_sites(run_dir)) == {"site-1"}


def test_a_draw_is_taken_from_the_written_sites_and_refuses_one_never_reviewed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = _reviewed(tmp_path, "site-1", "p4-0001").parent
    _reviewed(tmp_path, "site-3", "p4-0003")
    _selected_batch(tmp_path, "site-2", "p4-0002")
    argv = ["draw", "--run-dir", str(run_dir), "--seed", "3", "--count", "5"]
    with pytest.raises(SystemExit):  # the written set is not optional
        AU.main(argv)
    capsys.readouterr()
    assert AU.main([*argv, "--written", _ids_file(tmp_path / "w1.txt", "site-3")]) == 0
    assert capsys.readouterr().out.split() == ["site-3", "STAGE_EXIT=0"]  # site-1: not written
    with pytest.raises(ValueError, match="site-2"):
        AU.main([*argv, "--written", _ids_file(tmp_path / "w2.txt", "site-1", "site-2")])
    excluded = _ids_file(tmp_path / "ex.txt", "site-2")
    assert AU.main([*argv, "--written", str(tmp_path / "w2.txt"), "--exclude", excluded]) == 0
    assert capsys.readouterr().out.split() == ["site-1", "STAGE_EXIT=0"]


def test_a_site_assembled_in_two_batches_and_an_unknown_sheet_id_are_refused(
    tmp_path: Path,
) -> None:
    run_dir = _reviewed(tmp_path, "site-1", "p4-0001").parent
    with pytest.raises(ValueError, match="not reviewed in this run"):
        AU.main(
            ["sheet", "--run-dir", str(run_dir), "--site-ids",
             _ids_file(tmp_path / "ids.txt", "site-9"), "--out", str(tmp_path / "s.md")]
        )  # fmt: skip
    _reviewed(tmp_path / "other", "site-1", "p4-0002")
    (run_dir / "p4-0002").mkdir()
    for path in (tmp_path / "other" / "runs" / "pilot" / "p4-0002").iterdir():
        if path.is_file():
            (run_dir / "p4-0002" / path.name).write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="site-1 is assembled in two batches"):
        AU.reviewed_sites(run_dir)
