"""Does the reviewer refute findings without inventing anything, and does it leave alone what it
cannot act on?

Piece 6a of the Phase-3 runner. The discover pass asks the finder's question and nothing else, so its
precision is the pipeline's precision - and the census measured a 60 % false-negative rate. The
reviewer asks the second, differently-worded question, and the pilot measured it refuting 61 % of the
findings it looked at.

The mistakes that matter here are the quiet ones:

* a refutation that cites a page the run never fetched, or quotes a sentence that is not in the page
  we stored - the same fabricated-citation defect as the finder's, and the reason `claim_problems` is
  shared rather than re-written;
* treating `UNRESOLVED` as "not refuted": the three-state value is the stage's whole point, and
  collapsing it would let a finding nobody could confirm be written to the database;
* reviewing a finding that proposes no change, which spends a call to produce an inapplicable verdict
  and hides that the finding was never about a value;
* a field the finder never answered disappearing silently, so an empty reviewer report looks the same
  as a batch that was never judged;
* paying twice for the same question on a second pass.

Each guard below has a test that fails when the guard is removed; the mutation evidence (the
mutation, the failing assertion and the restored file's sha256) is in
`output/remediation/phase3_runner/PIECE6A.md`. Nothing in this file opens a socket or starts a
process: every runner here is scripted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import review_stage as RS  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402

NO_EXTENSIONS = Path(__file__).resolve().parent / "fixtures" / "pi_probe_no_extensions.json"
PAGE_TEXT = "Cave text xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
#: A URL key for the parse-only tests, which bring their own `pages` mapping. The batch-level tests
#: must not use it: they derive the URL the run really fetched (`_page_url`), because a citation
#: naming a URL nobody asked for is the very defect those tests are about.
CITED_URL = "https://en.wikipedia.org/w/api.php?action=query&titles=Cave%201&format=json"


# ── helpers ──────────────────────────────────────────────────────────────────────────────────


def _usage() -> Any:
    """The captured settled usage, so every scripted call carries real numbers."""
    lines = NO_EXTENSIONS.read_text(encoding="utf-8").splitlines()
    return MS.parse_stream(lines, source=str(NO_EXTENSIONS)).usage


def _site(site_id: str = "site-1", *, name: str = "Cave 1") -> dict[str, Any]:
    actual = dict.fromkeys(SP.DISCOVER_FIELDS, "a value")
    return {
        "findings": [SP.finding_row(field, actual[field]) for field in SP.DISCOVER_FIELDS],
        "name": name,
        "site_id": site_id,
    }


def _batch(*sites: dict[str, Any]) -> dict[str, Any]:
    return {"batch_id": "batch-0001", "ordinal": 1, "sites": list(sites)}


def _evidence_store(root: Path, *sites: str) -> F.EvidenceStore:
    """An evidence store holding exactly the page the finder and the reviewer both read."""
    store = F.EvidenceStore(root)
    for site_id in sites:
        path = store.path_for(site_id, F.FEATURE_ENWIKI)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PAGE_TEXT, encoding="utf-8")
    return store


def _page_url(site: dict[str, Any]) -> str:
    """The enwiki URL the run actually asks for this site's page - derived from the code, never
    guessed: a citation naming a URL nobody asked for is exactly what these tests are about."""
    return next(t.url for t in F.targets_for_site(site) if t.feature == F.FEATURE_ENWIKI)


def _source(site: dict[str, Any], *, quote: str = "Cave text") -> str:
    return f'SOURCE: {_page_url(site)} - "{quote}"'


def _finder_answer(
    site: dict[str, Any],
    *,
    verdict: str = "WRONG",
    proposed: str | None = "Cave",
    with_source: bool = True,
    quote: str = "Cave text",
) -> str:
    """A finder's answer that parses without a single problem - the only kind that is reviewed."""
    lines = ["The page calls it a cave.", f"VERDICT: {verdict}"]
    if proposed is not None:
        lines.append(f"PROPOSED: {proposed}")
    if with_source:
        lines.append(_source(site, quote=quote))
    return "\n".join(lines) + "\n"


def _answer_file(store: F.EvidenceStore, site_id: str, field: str, text: str) -> Path:
    path = store.path_for(site_id, field)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ScriptedRunner:
    """A fake runner: counts calls, answers with a fixed text, never starts a process."""

    def __init__(
        self, text: str = "REFUTED: NO\nWHY: the page says exactly what the record says\n"
    ):
        self.text = text
        self.calls: list[MS.ModelCall] = []
        self.usage = _usage()

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:
        self.calls.append(call)
        return MS.ModelAnswer(text=self.text, usage=self.usage)


class ExplodingRunner:
    """A runner that fails the test if anything is bought - the only proof a call was skipped."""

    def run(self, call: MS.ModelCall) -> MS.ModelAnswer:  # pragma: no cover - must not run
        raise AssertionError(f"a call was bought for {call.label} although the answer was on disk")


def _by_field(verdicts: list[RS.ReviewVerdict], field: str) -> RS.ReviewVerdict:
    """One field's verdict. Selecting by field keeps these tests independent of report order."""
    hits = [v for v in verdicts if v.field == field]
    assert len(hits) == 1, f"{len(hits)} verdicts for {field!r}"
    return hits[0]


def _ledger(tmp_path: Path) -> L.Ledger:
    return L.Ledger(tmp_path / "LEDGER.jsonl")


# ── the answer's shape ───────────────────────────────────────────────────────────────────────


def test_a_refutation_without_a_source_is_a_problem() -> None:
    answer = RS.parse_review("REFUTED: YES\nWHY: the page is about another cave\n")
    assert answer.refuted is True
    assert any("no `SOURCE:` page" in p for p in answer.problems), answer.problems
    assert not answer.complete


def test_a_refutation_that_cites_a_page_the_run_never_fetched_is_a_problem() -> None:
    text = (
        "REFUTED: YES\nWHY: the page is about another cave\n"
        'SOURCE: https://example.org/never-fetched - "the other cave"\n'
    )
    answer = RS.parse_review(text)
    pages = {CITED_URL: PAGE_TEXT}
    problems = answer.problems + DS.claim_problems(answer.sources, pages)
    assert any("was not fetched by this run" in p for p in problems), problems


def test_a_refutation_whose_quote_is_not_in_the_page_the_run_stored_is_a_problem() -> None:
    text = (
        "REFUTED: YES\nWHY: the page says otherwise\n"
        f'SOURCE: {CITED_URL} - "a sentence that is not in the stored page"\n'
    )
    answer = RS.parse_review(text)
    problems = answer.problems + DS.claim_problems(answer.sources, {CITED_URL: PAGE_TEXT})
    assert any("quote does not occur" in p for p in problems), problems


def test_an_honest_refutation_has_no_problems() -> None:
    text = f'REFUTED: YES\nWHY: the page is about another cave\nSOURCE: {CITED_URL} - "Cave text"\n'
    answer = RS.parse_review(text)
    assert answer.problems == ()
    assert answer.refuted is True
    assert answer.reason.startswith("the page is about another cave")
    assert DS.claim_problems(answer.sources, {CITED_URL: PAGE_TEXT}) == ()


def test_unresolved_is_neither_refuted_nor_not_refuted() -> None:
    """The three-state value: `UNRESOLVED` must not be readable as `refuted = False`."""
    answer = RS.parse_review("REFUTED: UNRESOLVED\nWHY: the page does not settle it\n")
    assert answer.problems == ()
    assert answer.refuted is None
    verdict = RS.ReviewVerdict(
        site_id="site-1", field="description", refuted=answer.refuted, reason=answer.reason
    )
    assert verdict.asked
    assert verdict.refuted is None
    assert not verdict.applies, "an unresolved finding must not be applied"


def test_a_not_refuted_verdict_that_carries_a_source_is_a_problem() -> None:
    text = (
        "REFUTED: NO\nWHY: the page says exactly what the record says\n"
        f'SOURCE: {CITED_URL} - "Cave text"\n'
    )
    answer = RS.parse_review(text)
    assert any("belongs to `REFUTED: YES`" in p for p in answer.problems), answer.problems


def test_a_review_without_a_refuted_line_is_a_problem() -> None:
    answer = RS.parse_review("WHY: I looked at it\n")
    assert answer.refuted is None
    assert any("0 `REFUTED:` line(s)" in p for p in answer.problems), answer.problems


def test_a_refuted_line_with_a_value_outside_the_vocabulary_is_a_problem() -> None:
    answer = RS.parse_review("REFUTED: MAYBE\nWHY: unclear\n")
    assert answer.refuted is None
    assert any("is not one of YES, NO, UNRESOLVED" in p for p in answer.problems), answer.problems


def test_two_refuted_lines_are_a_problem() -> None:
    answer = RS.parse_review("REFUTED: YES\nREFUTED: NO\nWHY: both\n")
    assert any("2 `REFUTED:` line(s)" in p for p in answer.problems), answer.problems


def test_a_review_without_a_why_line_is_a_problem() -> None:
    answer = RS.parse_review("REFUTED: NO\n")
    assert any("no `WHY:` sentence" in p for p in answer.problems), answer.problems


# ── what gets reviewed at all ────────────────────────────────────────────────────────────────


def test_only_a_complete_wrong_finding_is_asked_about(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    _answer_file(
        answers,
        "site-1",
        "period_start",
        _finder_answer(site, verdict="CORRECT", proposed=None, with_source=False),
    )
    _answer_file(answers, "site-1", "site_type", _finder_answer(site, proposed=None))

    plan = RS.plan_batch(batch=_batch(site), answers=answers, store=store)

    assert [item.call.field for item in plan.calls] == ["description"], plan.calls
    reasons = {v.field: v.unreviewable or "" for v in plan.unreviewable}
    assert len(reasons) == 4, reasons
    assert "proposes no change" in reasons["period_start"], reasons
    assert "not usable as it stands" in reasons["site_type"], reasons
    assert "a `WRONG` verdict with no `PROPOSED:` value" in reasons["site_type"], reasons


def test_a_field_the_finder_never_answered_is_recorded_not_silently_skipped(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")

    plan = RS.plan_batch(batch=_batch(site), answers=answers, store=store)

    assert plan.calls == []
    assert len(plan.unreviewable) == len(SP.DISCOVER_FIELDS)
    for verdict in plan.unreviewable:
        assert not verdict.asked
        assert "is not on disk" in (verdict.unreviewable or ""), verdict
        assert verdict.refuted is None


def test_a_site_whose_findings_all_propose_nothing_buys_no_call(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    for field in SP.DISCOVER_FIELDS:
        _answer_file(
            answers,
            "site-1",
            field,
            _finder_answer(site, verdict="UNVERIFIABLE", proposed=None, with_source=False),
        )
    runner = ScriptedRunner()

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=runner,
        store=store,
        answers=answers,
        reviews=F.EvidenceStore(tmp_path / "reviews"),
        ledger=_ledger(tmp_path),
    )

    assert runner.calls == []
    assert report.calls == 0
    assert report.cost_usd == 0.0
    assert len(report.verdicts) == len(SP.DISCOVER_FIELDS)
    assert all(v.unreviewable for v in report.verdicts)


# ── the prompt ───────────────────────────────────────────────────────────────────────────────


def test_the_prompt_carries_the_finders_answer_verbatim_and_the_same_page(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    finder_text = _finder_answer(site)
    _answer_file(answers, "site-1", "description", finder_text)

    plan = RS.plan_batch(batch=_batch(site), answers=answers, store=store)

    assert len(plan.calls) == 1
    prompt = plan.calls[0].call.prompt
    assert finder_text.strip() in prompt, "the finding must travel verbatim, not re-rendered"
    assert "a value" in prompt, "the stored value the finder judged must be in the prompt too"
    assert PAGE_TEXT in prompt, "the reviewer reads the same page the finder read"
    assert MS.REVIEWER_QUESTION in prompt
    assert plan.calls[0].call.stage.value == "reviewer"
    assert plan.calls[0].call.field == "description"


def test_the_reviewer_question_asks_for_the_verdict_line_the_parser_wants(tmp_path: Path) -> None:
    """The reviewer's question was never measured before it was asked twelve times, and it never
    asked for the line the parser reads.

    In the round-6 gold run every one of the 12 answers came back with no `REFUTED:` line at all -
    the model wrote `**VERDICT: none refuted**` in a shape of its own - so all 12 were read as
    `UNRESOLVED`, `applies` was false everywhere, and the write path would have had nothing to
    apply. The finder's frozen question spells its answer shape out; this one now does too, and the
    shape is taken from the parser's own vocabulary so that a drift on either side fails here.
    """
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))

    prompt = RS.plan_batch(batch=_batch(site), answers=answers, store=store).calls[0].call.prompt

    assert f"REFUTED: {' | '.join(RS.REFUTED_VALUES)}" in prompt
    assert "WHY:" in prompt


def test_the_reviewer_question_forbids_refuting_from_the_referees_own_knowledge(
    tmp_path: Path,
) -> None:
    """The finder may not uphold a stored value with its own knowledge; the reviewer may not kill a
    finding with its own knowledge either.

    A refutation removes a correction from the write path, so a reviewer that refutes from memory
    rather than from a page this run fetched throws away the corrections the evidence supports.
    """
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))

    prompt = RS.plan_batch(batch=_batch(site), answers=answers, store=store).calls[0].call.prompt

    assert "may not refute a finding" in prompt


def test_the_reviewers_prompt_is_bounded_like_the_finders(tmp_path: Path) -> None:
    site = _site()
    store = F.EvidenceStore(tmp_path / "evidence")
    path = store.path_for("site-1", F.FEATURE_ENWIKI)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * (MS.MAX_EVIDENCE_CHARS + 10), encoding="utf-8")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))

    with pytest.raises(MS.EvidenceOverBound):
        RS.plan_batch(batch=_batch(site), answers=answers, store=store)


# ── the judge ────────────────────────────────────────────────────────────────────────────────


def test_a_review_already_on_disk_is_read_and_not_bought_again(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    reviews = F.EvidenceStore(tmp_path / "reviews")
    _answer_file(reviews, "site-1", "description", "REFUTED: NO\nWHY: already answered once\n")

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=ExplodingRunner(),
        store=store,
        answers=answers,
        reviews=reviews,
        ledger=_ledger(tmp_path),
    )

    assert report.calls == 0
    assert report.resumed == 1
    assert report.cost_usd == 0.0
    verdict = _by_field(report.verdicts, "description")
    assert verdict.reason == "already answered once"
    assert verdict.applies


def test_a_live_review_is_bought_once_written_once_and_counted(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    reviews = F.EvidenceStore(tmp_path / "reviews")
    runner = ScriptedRunner()
    ledger = _ledger(tmp_path)
    before = ledger.path.read_text(encoding="utf-8") if ledger.path.exists() else ""

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=runner,
        store=store,
        answers=answers,
        reviews=reviews,
        ledger=ledger,
    )

    assert len(runner.calls) == 1
    assert report.calls == 1
    assert report.resumed == 0
    assert report.cost_usd == pytest.approx(runner.usage.cost_usd)
    assert (
        reviews.path_for("site-1", "description")
        .read_text(encoding="utf-8")
        .startswith("REFUTED: NO")
    )
    after = ledger.path.read_text(encoding="utf-8")
    assert after != before and "reviewer" in after, "the purchased call belongs in the ledger"
    assert _by_field(report.verdicts, "description").applies


def test_the_report_counts_what_the_verdicts_say(tmp_path: Path) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    reviews = F.EvidenceStore(tmp_path / "reviews")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    _answer_file(answers, "site-1", "period_start", _finder_answer(site))
    _answer_file(answers, "site-1", "site_type", _finder_answer(site))
    _answer_file(answers, "site-1", "country", _finder_answer(site))
    _answer_file(
        answers,
        "site-1",
        "card_description",
        _finder_answer(site, verdict="CORRECT", proposed=None, with_source=False),
    )
    _answer_file(reviews, "site-1", "description", "REFUTED: NO\nWHY: it holds\n")
    _answer_file(
        reviews,
        "site-1",
        "period_start",
        "REFUTED: YES\nWHY: another period\n" + _source(site) + "\n",
    )
    _answer_file(
        reviews, "site-1", "site_type", "REFUTED: UNRESOLVED\nWHY: the page does not settle it\n"
    )
    _answer_file(
        reviews,
        "site-1",
        "country",
        "REFUTED: YES\nWHY: cites a page nobody fetched\n"
        + 'SOURCE: https://example.org/x - "a sentence"\n',
    )

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=ExplodingRunner(),
        store=store,
        answers=answers,
        reviews=reviews,
        ledger=_ledger(tmp_path),
    )
    payload = report.to_dict()

    assert payload["calls"] == 0 and payload["resumed"] == 4
    assert payload["applies"] == 1, payload
    # Two reviewers said YES; one of them cited a page nobody fetched, so it does not apply. The
    # counters report what was said, `applies` reports what a writer may act on - keeping those two
    # apart is the reason both exist.
    assert payload["refuted"] == 2, payload
    assert payload["unresolved"] == 1, payload
    assert payload["unreviewable"] == 1, payload
    assert payload["with_problems"] == 1, payload
    assert sum(1 for v in report.verdicts if v.applies) == 1
    assert not _by_field(report.verdicts, "country").applies
    assert _by_field(report.verdicts, "country").refuted is True
    # And the report reads in the plan's field order, not in the order the fields were judged.
    assert [v.field for v in report.verdicts] == list(SP.DISCOVER_FIELDS)


def test_the_reviewer_writes_its_own_report_and_leaves_the_finders_model_json_alone(
    tmp_path: Path,
) -> None:
    site = _site()
    store = _evidence_store(tmp_path / "evidence", "site-1")
    answers = F.EvidenceStore(tmp_path / "answers")
    _answer_file(answers, "site-1", "description", _finder_answer(site))
    finder_report = tmp_path / "batch-0001" / "model.json"
    finder_report.parent.mkdir(parents=True, exist_ok=True)
    finder_report.write_text('{"stage": "finder", "totals": {"calls": 5}}\n', encoding="utf-8")
    before = finder_report.read_bytes()

    report = RS.judge_review_batch(
        batch=_batch(site),
        runner=ScriptedRunner(),
        store=store,
        answers=answers,
        reviews=F.EvidenceStore(tmp_path / "batch-0001" / "reviews"),
        ledger=_ledger(tmp_path),
    )
    RS.write_report(tmp_path / "batch-0001" / "review.json", report)

    written = json.loads((tmp_path / "batch-0001" / "review.json").read_text(encoding="utf-8"))
    assert written["stage"] == "reviewer"
    assert written["verdicts"][0]["field"] == "description"
    assert finder_report.read_bytes() == before, (
        "the reviewer must not overwrite the finder's record"
    )


def test_an_unreviewable_verdict_never_applies(tmp_path: Path) -> None:
    """A finding nobody was asked about must not reach a writer as if it had been confirmed."""
    verdict = RS.ReviewVerdict(
        site_id="site-1",
        field="description",
        refuted=None,
        reason="the finder's verdict is 'CORRECT'",
        unreviewable="the finder's verdict is 'CORRECT'",
    )
    assert not verdict.asked
    assert not verdict.applies
    assert verdict.to_dict()["applies"] is False
    assert verdict.to_dict()["asked"] is False
