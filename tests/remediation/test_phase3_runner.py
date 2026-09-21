"""Does the Phase-3 skeleton fire, refuse, and stay offline?

Piece 1 of the runner has no database and no network, so the interesting mistakes are not
exceptions but a *silently wrong* artefact: a plan that is not reproducible, a verdict kind
that cannot be emitted, a "no write" verdict carrying a write, a text field that gets a `set`
the next API boot reverts, a ledger line that overwrites the one before it, or a batch that
crashes and is reported as clean. Each guard below has a test that fails when the guard is
removed - the mutation evidence is in `output/remediation/phase3_runner/PIECE1.md`.

The plan and batch-arithmetic tests read the *real* worklist
(`output/remediation/phase3_worklist/WORKLIST.jsonl`), so a change in its shape fails here
instead of in the paid run.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import ledger as L  # noqa: E402
from phase3 import model as M  # noqa: E402
from phase3 import run as R  # noqa: E402

WORKLIST = REPO / "output" / "remediation" / "phase3_worklist" / "WORKLIST.jsonl"
PHASE3_MODULES = (M, L, R)


def _evidence() -> M.Evidence:
    return M.Evidence(source="enwiki", url="https://en.wikipedia.org/wiki/X", quote="...", retrieved_at="2026-09-21T00:00:00+00:00")


def _finding(**over: object) -> M.Finding:
    base: dict[str, object] = {
        "site_id": "31860bc4-476a-49bc-9f97-e25220063d19",
        "field": "period_start",
        "verdict": M.Verdict.DEFECT,
        "severity": M.Severity.SEVERE,
        "test_id": "P3/period",
    }
    base.update(over)
    return M.Finding(**base)  # type: ignore[arg-type]


# ── model: the three verdict kinds ───────────────────────────────────────────────────────────


def test_all_three_verdict_kinds_are_expressible() -> None:
    defect = _finding(proposal=M.Proposal.SET, proposed_value=-2000, evidence=[_evidence()], confidence=M.Confidence.TWO_SOURCE)
    odd_but_right = _finding(
        verdict=M.Verdict.TRUE_BUT_NO_CORRECTION,
        severity=M.Severity.MODERATE,
        current_value="5th century AD (card terminus)",
        proposal=M.Proposal.REVIEW,
        note="the card's only dated claim is the terminus (plan §4.3 pattern 7)",
    )
    cannot_settle = _finding(
        verdict=M.Verdict.UNVERIFIABLE,
        severity=M.Severity.MODERATE,
        proposal=M.Proposal.REVIEW,
        confidence=M.Confidence.UNVERIFIABLE,
        note="neither source carries a coordinate",
    )

    assert [f.verdict.value for f in (defect, odd_but_right, cannot_settle)] == [
        "defect",
        "true_but_no_correction",
        "unverifiable",
    ]
    # The required boolean both briefs ask for, derived from the verdict so the two cannot disagree.
    assert [f.defect for f in (defect, odd_but_right, cannot_settle)] == [True, False, False]
    payload = json.loads(odd_but_right.to_json())
    assert payload["defect"] is False
    assert payload["verdict"] == "true_but_no_correction"


@pytest.mark.parametrize(
    "verdict", [M.Verdict.TRUE_BUT_NO_CORRECTION, M.Verdict.UNVERIFIABLE]
)
def test_a_no_write_verdict_cannot_carry_a_write(verdict: M.Verdict) -> None:
    # Everything else about the record is a valid write, so the verdict is the only guard left.
    with pytest.raises(ValueError, match="no write"):
        _finding(
            verdict=verdict,
            proposal=M.Proposal.SET,
            proposed_value=-2000,
            evidence=[_evidence()],
            confidence=M.Confidence.TWO_SOURCE,
        )


def test_a_no_write_verdict_cannot_smuggle_a_proposed_value() -> None:
    with pytest.raises(ValueError, match="must not carry a proposed_value"):
        _finding(
            verdict=M.Verdict.TRUE_BUT_NO_CORRECTION,
            proposal=M.Proposal.REVIEW,
            proposed_value=-2000,
        )


def test_an_invented_verdict_value_is_refused() -> None:
    with pytest.raises(ValueError, match="not one of"):
        _finding(verdict="correct")


def test_a_defect_cannot_be_recorded_as_nothing_to_see() -> None:
    with pytest.raises(ValueError, match="cannot carry proposal=none"):
        _finding(proposal=M.Proposal.NONE)


@pytest.mark.parametrize("field", sorted(M.REPORT_ONLY_FIELDS))
def test_text_fields_are_report_only(field: str) -> None:
    with pytest.raises(ValueError, match="report-only"):
        _finding(field=field, proposal=M.Proposal.SET, proposed_value="a new sentence", evidence=[_evidence()])


def test_a_proposed_write_needs_evidence() -> None:
    with pytest.raises(ValueError, match="needs evidence"):
        _finding(proposal=M.Proposal.SET, proposed_value=-2000, evidence=[])


def test_unverifiable_confidence_cannot_carry_a_write() -> None:
    with pytest.raises(ValueError, match="unverifiable cannot carry"):
        _finding(
            proposal=M.Proposal.SET,
            proposed_value=-2000,
            evidence=[_evidence()],
            confidence=M.Confidence.UNVERIFIABLE,
        )


def test_site_type_must_be_a_fixed_point_of_the_boot_normalizer() -> None:
    # Premise measured against the producer itself: "temple" is rewritten on every container start.
    assert M.site_type_fixed_point("temple") is False
    assert M.site_type_fixed_point("Temple") is True

    with pytest.raises(ValueError, match="not a site_type fixed point"):
        _finding(
            field="site_type",
            proposal=M.Proposal.SET,
            proposed_value="temple",
            evidence=[_evidence()],
            confidence=M.Confidence.AUTHORITATIVE,
        )
    surviving = _finding(
        field="site_type",
        proposal=M.Proposal.SET,
        proposed_value="Temple",
        evidence=[_evidence()],
        confidence=M.Confidence.AUTHORITATIVE,
    )
    assert surviving.proposed_value == "Temple"


def test_a_stage_result_refuses_findings_from_outside_its_batch() -> None:
    with pytest.raises(ValueError, match="not in this batch"):
        M.StageResult(
            stage=M.Stage.FINDER,
            batch_id="batch-0001",
            site_ids=["a"],
            findings=[_finding(site_id="b")],
        )


def test_a_crashed_stage_must_name_its_error() -> None:
    with pytest.raises(ValueError, match="needs the error"):
        M.StageResult(stage=M.Stage.FINDER, batch_id="batch-0001", site_ids=["a"], status=M.StageStatus.ERROR)
    with pytest.raises(ValueError, match="cannot carry an error"):
        M.StageResult(
            stage=M.Stage.FINDER,
            batch_id="batch-0001",
            site_ids=["a"],
            status=M.StageStatus.COMPLETE,
            error="should not be here",
        )


def test_a_stage_result_round_trips_its_findings() -> None:
    result = M.StageResult(
        stage=M.Stage.REVIEWER,
        batch_id="batch-0001",
        site_ids=["a"],
        findings=[_finding(site_id="a")],
    )
    payload = json.loads(result.to_json())
    assert payload["stage"] == "reviewer"
    assert payload["status"] == "complete"
    assert payload["findings"][0]["defect"] is True


# ── ledger: measured, append-only, crash-safe ───────────────────────────────────────────────


def _call(label: str = "P3/finder") -> L.Entry:
    return L.Entry(
        kind=L.LedgerKind.MODEL_CALL,
        stage=M.Stage.FINDER,
        batch_id="batch-0001",
        label=label,
        model="deepseek-v4.1-flash",
        input_tokens=1000,
        output_tokens=200,
        cache_read_tokens=800,
    )


def _fetch(at: str) -> L.Entry:
    return L.Entry(
        kind=L.LedgerKind.FETCH,
        stage=M.Stage.REVIEWER,
        batch_id="batch-0001",
        label="Satsurblia/enwiki",
        at=at,
        url="https://en.wikipedia.org/wiki/Satsurblia_Cave",
        http_status=200,
        bytes=4096,
    )


def test_appending_is_additive_and_leaves_no_half_line(tmp_path: Path) -> None:
    path = tmp_path / "LEDGER.jsonl"
    ledger = L.Ledger(path, clock=lambda: "2026-09-21T00:00:00+00:00")

    first = ledger.append(_call())
    ledger.append(_fetch("2026-09-21T00:01:00+00:00"))

    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw
    assert len(raw.decode("utf-8").splitlines()) == 2  # the second append did not overwrite the first
    assert first.at == "2026-09-21T00:00:00+00:00"  # stamped by the ledger's own clock
    assert json.loads(raw.decode("utf-8").splitlines()[0])["kind"] == "model_call"


def test_summarise_totals_by_stage(tmp_path: Path) -> None:
    path = tmp_path / "LEDGER.jsonl"
    ledger = L.Ledger(path, clock=lambda: "2026-09-21T00:02:00+00:00")
    ledger.append(_call())
    ledger.append(_fetch("2026-09-21T00:00:30+00:00"))

    summary = L.summarise(path)
    assert sorted(summary.by_stage) == ["finder", "reviewer"]
    assert summary.lines == 2
    finder = summary.by_stage["finder"]
    assert (finder.model_calls, finder.input_tokens, finder.output_tokens, finder.total_tokens) == (1, 1000, 200, 1200)
    assert finder.cache_read_tokens == 800
    reviewer = summary.by_stage["reviewer"]
    assert (reviewer.fetches, reviewer.fetch_bytes, reviewer.model_calls) == (1, 4096, 0)
    assert reviewer.first_at == "2026-09-21T00:00:30+00:00"
    assert summary.total.model_calls == 1 and summary.total.fetch_bytes == 4096


def test_a_model_call_without_token_counts_is_refused() -> None:
    with pytest.raises(L.LedgerError, match="never estimated"):
        L.Entry(kind=L.LedgerKind.MODEL_CALL, stage=M.Stage.FINDER, batch_id="b", label="x", model="m", input_tokens=None, output_tokens=1)
    with pytest.raises(L.LedgerError, match="never estimated"):
        L.Entry(kind=L.LedgerKind.MODEL_CALL, stage=M.Stage.FINDER, batch_id="b", label="x", model="m", input_tokens=1, output_tokens=None)


def test_a_fetch_without_an_observed_status_is_refused() -> None:
    with pytest.raises(L.LedgerError, match="raises in the fetcher"):
        L.Entry(kind=L.LedgerKind.FETCH, stage=M.Stage.FINDER, batch_id="b", label="x", url="https://example.org", bytes=10)
    with pytest.raises(L.LedgerError, match="a fetch cannot carry"):
        L.Entry(kind=L.LedgerKind.FETCH, stage=M.Stage.FINDER, batch_id="b", label="x", url="https://example.org", http_status=200, bytes=10, input_tokens=5)


def test_a_model_call_cannot_carry_fetch_fields() -> None:
    entry = _call()
    with pytest.raises(L.LedgerError, match="cannot carry"):
        L.Entry(**{**entry.__dict__, "url": "https://example.org"})  # type: ignore[arg-type]


def test_summarise_of_a_missing_ledger_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nothing has been measured"):
        L.summarise(tmp_path / "absent.jsonl")


def test_a_truncated_ledger_line_raises(tmp_path: Path) -> None:
    path = tmp_path / "LEDGER.jsonl"
    # A line that is not JSON at all: a total over it would be a guess.
    path.write_text('{"kind": "model_call", "stage": "finder"}\nnot json\n', encoding="utf-8", newline="\n")
    with pytest.raises(L.LedgerError, match="not JSON"):
        L.summarise(path)
    # A line without its newline: the append was interrupted mid-write.
    path.write_text('{"kind": "model_call", "stage": "finder"}', encoding="utf-8", newline="\n")
    with pytest.raises(L.LedgerError, match="does not end in a newline"):
        L.summarise(path)
    # An empty line is not a measurement either.
    path.write_text('\n', encoding="utf-8", newline="\n")
    with pytest.raises(L.LedgerError, match="empty line"):
        L.summarise(path)


# ── run: deterministic plan, offline ────────────────────────────────────────────────────────


def test_plan_of_the_real_worklist_is_byte_identical_across_runs(tmp_path: Path) -> None:
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    assert R.main(["plan", "--worklist", str(WORKLIST), "--out", str(first)]) == 0
    assert R.main(["plan", "--worklist", str(WORKLIST), "--out", str(second)]) == 0

    one, two = first.read_bytes(), second.read_bytes()
    digest = lambda blob: hashlib.sha256(blob).hexdigest()  # noqa: E731
    assert one == two
    assert digest(one) == digest(two)
    assert one.count(b"\n") == 121  # ceil(1813 / 15), one line per batch
    assert b"\r\n" not in one  # newline pinned to LF
    # No timestamp anywhere: the artefact must not depend on when it was produced.
    assert not re.search(rb'"(at|ts|timestamp|generated_at|date)"', one)


def test_plan_has_the_ratified_batch_arithmetic(tmp_path: Path) -> None:
    out = tmp_path / "plan.jsonl"
    R.main(["plan", "--worklist", str(WORKLIST), "--out", str(out)])

    lines = out.read_text(encoding="utf-8").splitlines()
    batches = [json.loads(line) for line in lines]
    assert [b["batch_id"] for b in batches[:2]] == ["batch-0001", "batch-0002"]
    assert [len(b["sites"]) for b in batches[:2]] == [15, 15]
    assert len(batches[-1]["sites"]) == 13
    assert sum(len(b["sites"]) for b in batches) == 1813

    # The worklist's own order (worst first) is preserved, not re-sorted.
    records = R.read_jsonl(WORKLIST)
    phase3 = [r for r in records if r["phase3"] is True]
    assert [s["site_id"] for s in batches[0]["sites"]] == [r["site_id"] for r in phase3[:15]]
    assert [s["site_id"] for s in batches[-1]["sites"]] == [r["site_id"] for r in phase3[-13:]]


def test_plan_refuses_a_record_it_cannot_place(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"site_id": "a", "phase3": true}\n{"site_id": "b"}\n', encoding="utf-8", newline="\n")
    with pytest.raises(R.InputError, match="carries no `phase3` flag"):
        R.main(["plan", "--worklist", str(bad), "--out", str(tmp_path / "out.jsonl")])

    no_id = tmp_path / "no_id.jsonl"
    no_id.write_text('{"phase3": true}\n', encoding="utf-8", newline="\n")
    with pytest.raises(R.InputError, match="carries no `site_id`"):
        R.main(["plan", "--worklist", str(no_id), "--out", str(tmp_path / "out2.jsonl")])


def test_plan_refuses_a_batch_size_below_one(tmp_path: Path) -> None:
    with pytest.raises(R.InputError, match="batch size must be >= 1"):
        R.main(["plan", "--worklist", str(WORKLIST), "--out", str(tmp_path / "out.jsonl"), "--batch-size", "0"])


def _tiny_plan(tmp_path: Path) -> Path:
    plan = tmp_path / "plan.jsonl"
    plan.write_text(
        '{"batch_id": "batch-0001", "ordinal": 1, "sites": [{"site_id": "a"}]}\n'
        '{"batch_id": "batch-0002", "ordinal": 2, "sites": [{"site_id": "b"}]}\n',
        encoding="utf-8",
        newline="\n",
    )
    return plan


def test_prepare_writes_one_input_file_per_batch(tmp_path: Path) -> None:
    plan = _tiny_plan(tmp_path)
    run_dir = tmp_path / "runs"
    assert R.main(["prepare", "--plan", str(plan), "--run-dir", str(run_dir)]) == 0
    first = run_dir / "batch-0001" / "input.json"
    assert json.loads(first.read_text(encoding="utf-8"))["sites"] == [{"site_id": "a"}]

    # Selecting one batch rewrites only that one and cannot invent a batch id.
    R.main(["prepare", "--plan", str(plan), "--run-dir", str(run_dir), "--batch-id", "batch-0002"])
    with pytest.raises(R.InputError, match="not in the plan"):
        R.main(["prepare", "--plan", str(plan), "--run-dir", str(run_dir), "--batch-id", "batch-0009"])


def test_status_reports_what_is_on_disk(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan = _tiny_plan(tmp_path)
    run_dir = tmp_path / "runs"
    with pytest.raises(FileNotFoundError, match="nothing has been prepared"):
        R.main(["status", "--run-dir", str(run_dir), "--plan", str(plan)])

    R.main(["prepare", "--plan", str(plan), "--run-dir", str(run_dir)])
    ledger = tmp_path / "LEDGER.jsonl"
    L.Ledger(ledger, clock=lambda: "2026-09-21T00:00:00+00:00").append(_call())
    capsys.readouterr()
    assert R.main(["status", "--run-dir", str(run_dir), "--plan", str(plan), "--ledger", str(ledger)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["planned_batches"] == 2
    assert payload["planned_sites"] == 2
    assert payload["batches_with_input"] == ["batch-0001", "batch-0002"]
    assert payload["batches_with_result"] == []
    assert payload["ledger"]["stages"]["finder"]["model_calls"] == 1


def test_the_skeleton_touches_no_network_and_no_model_client() -> None:
    banned = re.compile(r"\b(httpx|requests|urllib|socket|aiohttp|openai|anthropic|subprocess)\b")
    for module in PHASE3_MODULES:
        source = Path(module.__file__).read_text(encoding="utf-8")
        hits = sorted(set(banned.findall(source)))
        assert hits == [], f"{Path(module.__file__).name} reaches outside the process: {hits}"
