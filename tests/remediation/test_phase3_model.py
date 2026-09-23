"""Does the Phase-3 model stage answer every call through the Opus handoff, record each answer
honestly as unmetered, and refuse every answer that is not the answer to exactly its question?

Owner order 2026-09-23: every judgement is answered by an Opus agent of the orchestrating session,
through files (`scripts/remediation/opus_handoff.py`). The interesting mistakes are again not
exceptions but a *silently wrong* record: an answer to another prompt read as this one's, a missing
answer turned into a named hole instead of a stop, a zero cost that claims a measurement, an export
that writes a ledger line or an answer, or a dry run that quietly exports. Each guard below has a
test that fails when the guard is removed, and a mutation case in
`scripts/remediation/phase3/mutation_sweep.py`.

Until 2026-09-23 the transport was a Pi process on `opencode-go/deepseek-v4.1-flash`; its tests and
the two captured Pi transcripts they read went with it (`output/remediation/phase3_runner/PIECE3.md`
keeps the measurements). Nothing in this suite calls a model, opens a socket or touches the database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

import opus_handoff as OH  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model as M  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import run as R  # noqa: E402


def _answer() -> MS.ModelAnswer:
    """The answer every scripted call replays: what the handoff returns, unmetered."""
    return MS.ModelAnswer(text="OK", usage=MS.Usage.unmetered())


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


def _assert_nothing_handed_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if anything exports a question or reads an answer. Used by the dry run."""

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError(f"a dry run must not touch the handoff: {args!r} {kwargs!r}")

    monkeypatch.setattr(OH, "export", refuse)
    monkeypatch.setattr(OH, "read_answer", refuse)


def _handoff_answers(directory: Path, text: str = "OK") -> int:
    """Answer every exported question of `directory` as an Opus agent would: through the helper."""
    lines = OH.manifest(directory)
    for line in lines:
        OH.write_answer(
            directory,
            batch_id=line["batch_id"],
            stage=line["stage"],
            label=line["label"],
            text=text,
            answered_by="test-agent",
            now=lambda: "2026-09-23T12:00:00+00:00",
        )
    return len(lines)


# ── the handoff runner: the answer to exactly this prompt, by Opus, or a stop ─────────────────


def test_the_runner_reads_the_opus_answer_to_exactly_this_prompt(tmp_path: Path) -> None:
    call = MS.ModelCall(
        stage=M.Stage.FINDER, batch_id="batch-0001", site_id="site-1", prompt="Ötzi? " * 10
    )
    assert MS.export_calls([call], directory=tmp_path) == {"exported": 1, "already": 0}
    assert MS.export_calls([call], directory=tmp_path) == {"exported": 0, "already": 1}
    _handoff_answers(tmp_path, text="VERDICT: CORRECT")

    answer = MS.HandoffRunner(directory=tmp_path).run(call)

    assert answer.text == "VERDICT: CORRECT"
    assert answer.usage == MS.Usage.unmetered()
    assert MS.MODEL == OH.OPUS_MODEL


def test_every_handoff_refusal_stops_the_batch_and_is_never_a_named_hole(tmp_path: Path) -> None:
    """A missing or stale answer is the orchestrator's to answer again, never a permanent hole.

    `UnreadableStream` would make the judge loop record a named failure and carry on (Phase 4 would
    append a hold); a plain `ModelCallFailed` stops the batch, so the question is asked again.
    """
    call = MS.ModelCall(stage=M.Stage.FINDER, batch_id="batch-0001", site_id="site-1", prompt="Q")
    runner = MS.HandoffRunner(directory=tmp_path)
    MS.export_calls([call], directory=tmp_path)

    with pytest.raises(MS.ModelCallFailed, match="no answer at") as missing:
        runner.run(call)
    assert not isinstance(missing.value, MS.UnreadableStream)

    _handoff_answers(tmp_path)
    changed = MS.ModelCall(
        stage=M.Stage.FINDER, batch_id="batch-0001", site_id="site-1", prompt="Q, asked today"
    )
    with pytest.raises(MS.ModelCallFailed, match="stale") as stale:
        runner.run(changed)
    assert not isinstance(stale.value, MS.UnreadableStream)


def test_an_unmetered_answer_carries_zeros_and_says_so() -> None:
    usage = MS.Usage.unmetered()
    assert usage.metering == L.UNMETERED == "unmetered"
    assert (usage.input_tokens, usage.output_tokens, usage.total_tokens, usage.cost_usd) == (
        0,
        0,
        0,
        0.0,
    )


def test_an_unmetered_ledger_line_refuses_every_number_and_every_other_metering() -> None:
    """With no meter there is no number: an unmetered line that carries one invented it."""

    def line(**overrides: Any) -> L.Entry:
        fields: dict[str, Any] = {
            "kind": L.LedgerKind.MODEL_CALL,
            "stage": M.Stage.FINDER,
            "batch_id": "batch-0001",
            "label": "site-1/finder",
            "model": OH.OPUS_MODEL,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "metering": L.UNMETERED,
        }
        fields.update(overrides)
        return L.Entry(**fields)

    assert json.loads(line().to_json())["metering"] == "unmetered"
    for overrides in ({"input_tokens": 437}, {"cache_read_tokens": 3}, {"cost_usd": 6.6e-05}):
        with pytest.raises(L.LedgerError, match="unmetered call carries"):
            line(**overrides)
    with pytest.raises(L.LedgerError, match="unmetered call carries"):
        line(cost_usd=None)  # "not recorded" is not the declared 0 either
    with pytest.raises(L.LedgerError, match="is not 'unmetered'"):
        line(metering="subscription")
    # A provider-reported line keeps the exact shape every line had before: no key at all.
    assert "metering" not in json.loads(line(metering=None, input_tokens=5).to_json())


def test_a_fetch_line_cannot_carry_metering() -> None:
    with pytest.raises(L.LedgerError, match="a fetch cannot carry metering"):
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
            metering=L.UNMETERED,
        )


# ── the ledger: one line per call, naming Opus and saying it was not metered ─────────────────


def test_exactly_one_ledger_line_per_call_names_opus_and_is_unmetered(tmp_path: Path) -> None:
    ledger = L.Ledger(tmp_path / "LEDGER.jsonl", clock=lambda: "2026-09-23T06:00:00+00:00")
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
    assert {row["model"] for row in rows} == {"anthropic/claude-opus-5-5 (Claude Code agent)"}
    for row in rows:
        # Declared, not measured: the line says so, and every number on it is the declared zero.
        assert row["metering"] == "unmetered"
        assert (row["input_tokens"], row["output_tokens"], row["cost_usd"]) == (0, 0, 0.0)
    assert report.calls == 2
    assert report.cost_usd == 0.0
    assert answers.path_for("site-1", "finder").read_text(encoding="utf-8") == "OK"

    summary = L.summarise(tmp_path / "LEDGER.jsonl")
    assert summary.by_stage["finder"].model_calls == 2
    assert summary.by_stage["finder"].unmetered_calls == 2
    assert summary.total.unmetered_calls == 2


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
    """A call that could not be answered ends the batch; only an unreadable answer is a named hole.

    The seam is the exception class. `ModelCallFailed` says the call could not be *answered* - the
    handoff holds no answer for it, or one to another prompt - and nothing after it may be trusted,
    so it propagates. `UnreadableStream` says the answer that arrived holds none: the batch records
    the hole and buys the next call (the two tests below).
    """

    class FailingRunner:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
            raise MS.ModelCallFailed(f"{call.label}: no answer at <handoff> - export it first")

    with pytest.raises(MS.ModelCallFailed, match="no answer at"):
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

    No runner raises `UnreadableStream` since the Opus handoff (the handoff stops the batch
    instead), but the loops keep their contract for an answer that is not one: measured 2026-09-21,
    4 of the mass run's 334 batches died on such a call of the Pi transport and lost every answer
    they had already written (`output/remediation/logs/mass/batch-0143.judge.log`).
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
    monkeypatch.setattr(MS, "HandoffRunner", HoleRunner)
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
            "--handoff-import",
            str(tmp_path / "handoff"),
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


def test_judge_without_a_handoff_renders_the_prompt_and_hands_off_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _assert_nothing_handed_off(monkeypatch)
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
    assert payload["model"] == "anthropic/claude-opus-5-5 (Claude Code agent)"
    site = payload["sites"][0]
    assert "argv" not in site  # there is no process to show any more
    assert site["prompt_chars"] == len(site["prompt"])
    assert MS.FINDER_QUESTION in site["prompt"]
    # The preview shows the missing evidence instead of hiding it, and nothing was written.
    assert site["evidence"][0]["present"] is False
    assert not ledger.exists()
    assert not (run_dir / "batch-0001" / "answers").exists()


def _judge_argv(run_dir: Path, ledger: Path, *extra: str) -> list[str]:
    return [
        "judge",
        "--run-dir",
        str(run_dir),
        "--batch-id",
        "batch-0001",
        "--ledger",
        str(ledger),
        *extra,
    ]


def test_an_export_hands_off_exactly_the_calls_the_import_asks_and_writes_nothing_else(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Export, answer, import through the real CLI: every call answered, nothing written early.

    The export runs the judge itself with a recording runner, so the questions handed off are the
    import's by construction; the import then finds an answer for every call it makes. The export
    writes no ledger line, no answer and no `model.json`: those are the import's, from the answers.
    """
    run_dir = _prepared_run_dir(tmp_path, count=2)
    _evidence_store(run_dir / "batch-0001", 2)
    ledger = tmp_path / "LEDGER.jsonl"
    handoff = tmp_path / "handoff"

    assert R.main(_judge_argv(run_dir, ledger, "--handoff-export", str(handoff))) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["labels"] == ["site-1/finder", "site-2/finder"]
    assert exported["exported"] == 2 and "error" not in exported
    assert not ledger.exists()
    assert not (run_dir / "batch-0001" / "answers").exists()
    assert not (run_dir / "batch-0001" / "model.json").exists()
    assert [line["prompt_sha256"] for line in OH.manifest(handoff)] == [
        OH.prompt_sha256(item.call.prompt)
        for item in MS.prepare_batch(
            batch=_batch(2),
            store=F.EvidenceStore(run_dir / "batch-0001" / "evidence"),
            stage=M.Stage.FINDER,
        )
    ]
    assert R.main(_judge_argv(run_dir, ledger, "--handoff-import", str(handoff))) == 2
    assert "no answer at" in json.loads(capsys.readouterr().out)["error"]

    assert _handoff_answers(handoff, text="VERDICT: CORRECT") == 2
    assert OH.validate(handoff).ok
    assert R.main(_judge_argv(run_dir, ledger, "--handoff-import", str(handoff))) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["totals"]["calls"] == 2
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert [(row["label"], row["metering"]) for row in rows] == [
        ("site-1/finder", "unmetered"),
        ("site-2/finder", "unmetered"),
    ]
    # A second export after the import has nothing left to ask: the answers are on disk.
    assert R.main(_judge_argv(run_dir, ledger, "--handoff-export", str(handoff))) == 0
    assert json.loads(capsys.readouterr().out)["calls"] == 0


def test_export_and_import_are_one_or_the_other(tmp_path: Path) -> None:
    run_dir = _prepared_run_dir(tmp_path)
    with pytest.raises(SystemExit):
        R.main(
            _judge_argv(
                run_dir,
                tmp_path / "LEDGER.jsonl",
                "--handoff-export",
                str(tmp_path / "a"),
                "--handoff-import",
                str(tmp_path / "b"),
            )
        )
    with pytest.raises(SystemExit):
        R.main(_judge_argv(run_dir, tmp_path / "LEDGER.jsonl", "--live"))


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

    monkeypatch.setattr(MS, "HandoffRunner", CountingRunner)
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
            "--handoff-import",
            str(tmp_path / "handoff"),
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
            raise MS.ModelCallFailed(f"{call.label}: no answer at <handoff> - export it first")

    monkeypatch.setattr(MS, "HandoffRunner", FailingRunner)
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
            "--handoff-import",
            str(tmp_path / "handoff"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["live"] is True
    assert "no answer at" in payload["error"]
    assert not ledger.exists()
    assert not (run_dir / "batch-0001" / "model.json").exists()
