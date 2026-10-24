"""The calibration of lane E's writer (`enrich-writer`, `wc/enrich_calibration.py`): a leave-one-out
truth pool of texts that carry a sourced open question, sealed, prepared and compared through
`calibrate_claude.py`, and the verdict `enrich.require_writer_calibration` reads by code.

The text is a checked March text that ends on a sourced open question (a WC run end to end on the
fake pages); its open-question sentence is left out of the question, and the writer must find the
open matter again on a page of the host the sentence cited. No socket, no model, no database.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import calibrate_claude as CC  # noqa: E402
from phase3.run import read_jsonl  # noqa: E402
from phase4 import wc4 as WC4  # noqa: E402
from wc import cli as C  # noqa: E402
from wc import enrich as E  # noqa: E402
from wc import enrich_calibration as EC  # noqa: E402

from tests.remediation import enrich_fixtures as EF  # noqa: E402
from tests.remediation import wc_fixtures as FX  # noqa: E402
from tests.remediation.test_wc_repairs import _fresh_rows, _read  # noqa: E402
from tests.remediation.wc_fixtures import OH, wiki_cache  # noqa: E402,F401

SITE = "3a000000-0000-4000-8000-00000000003a"
OPEN = "Whether the alignment of the south temple served as a calendar remains unresolved."
TEXT = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta. "
    "They date to approximately 3150 BC. " + OPEN
)


@pytest.fixture
def checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh read holding a checked March text that ends on its sourced open question (the third
    sentence, citing the research page): the base lane E enriches."""
    for url, html in EF.PAGES.items():
        monkeypatch.setitem(FX.PAGES, url, html)
    rows = [FX.row(SITE, TEXT, raw_data=FX.legacy_raw(TEXT), name="Tarxien Temples")]
    answers = {
        SITE: FX.answer(
            SITE, [FX.keep(1, FX.Q_COMPLEX), FX.keep(2, FX.Q_DATE), FX.keep(3, EF.Q_HOOK)]
        )
    }
    _, plan = FX.build_run(tmp_path / "wc", rows, answers, name="wc-open")
    return _read(tmp_path, _fresh_rows(plan, rows))


def _cases(path: Path, *, sentence: int = 3) -> Path:
    path.write_text(
        json.dumps(
            {"site_id": SITE, "sentence": sentence, "confirmed_by": "a test", "note": "read"}
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_a_candidate_is_a_sourced_sentence_that_frames_something_as_open(
    checked: Path, tmp_path: Path
) -> None:
    out = tmp_path / "CANDIDATES.jsonl"
    assert EC.candidates(checked, out) == {"candidates": 1, "sites": 1}
    (line,) = read_jsonl(out)
    assert (line["sentence"], line["text"], line["urls"]) == (3, OPEN, [EF.RESEARCH])


def test_the_pool_asks_the_text_without_its_open_question_and_seals_the_hosts(
    checked: Path, tmp_path: Path
) -> None:
    out = tmp_path / "pool"
    summary = EC.build(checked, _cases(tmp_path / "cases.jsonl"), out)
    assert summary["cases"] == 1 and summary["questions"] == 1
    assert (
        "--comparison enrich-recovery" in summary["seal"] and "--threshold 0.7" in summary["seal"]
    )
    (entry,) = read_jsonl(out / "run" / C.SITES_FILE)
    assert entry["existing"] == [
        "The Tarxien Temples are an archaeological complex in Tarxien, Malta.",
        "They date to approximately 3150 BC.",
    ]
    base = WC4.Base.from_dict(entry["base"])
    assert OPEN not in base.text and [c["url"] for c in base.citations] == [FX.WIKI]
    truth = json.loads((out / EC.TRUTH_FILE).read_text(encoding="utf-8"))
    assert truth[SITE]["hosts"] == ["example.edu"] and truth[SITE]["removed"] == OPEN
    prompt = next((out / "handoff").rglob("*.prompt.txt")).read_text(encoding="utf-8")
    assert OPEN not in prompt and "open_question" in prompt
    with pytest.raises(EC.EnrichCalibrationError, match="frames nothing as open"):
        EC.build(checked, _cases(tmp_path / "c2.jsonl", sentence=2), tmp_path / "pool2")
    with pytest.raises(EC.EnrichCalibrationError, match="is built once"):
        EC.build(checked, _cases(tmp_path / "cases.jsonl"), out)


def _calibrate(
    checked: Path, tmp_path: Path, answer: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict]:
    """Seal, prepare, answer as the writer role, compare, verdict - the runbook's steps."""
    out = tmp_path / "pool"
    summary = EC.build(checked, _cases(tmp_path / "cases.jsonl"), out)
    root = tmp_path / "calibration"
    batches = sorted(C.round_of(out / "run", out / "handoff")["batches"])
    CC.seal(
        root,
        calibration_id=E.WRITER_CALIBRATION_ID,
        role=E.WRITER_ROLE,
        handoff=out / "handoff",
        batches=batches,
        threshold=E.WRITER_SEAL_MINIMUM,
        truth=out / EC.TRUTH_FILE,
        comparison=EC.COMPARISON,
    )
    prepared = CC.prepare(root, calibration_id=E.WRITER_CALIBRATION_ID, run=out / "run")
    copy = root / E.WRITER_CALIBRATION_ID
    brief = C.brief(Path(prepared["calibration_run"]), copy, batches[0])
    assert "enrich_writer" in brief and summary["cases"] == 1
    EF.record_enriched(copy, {SITE: answer})
    assert EC.main(["compare", "--root", str(root), "--id", E.WRITER_CALIBRATION_ID]) == 0
    verdict = CC.verdict(root, calibration_id=E.WRITER_CALIBRATION_ID, false_sources=0)
    return root, verdict


def test_a_writer_that_finds_the_open_question_again_passes_and_lane_e_may_be_approved(
    checked: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, verdict = _calibrate(checked, tmp_path, EF.good(SITE), monkeypatch)
    assert verdict["passed"] is True and verdict["agreement"] == 1.0 and verdict["units"] == 2
    assert len(E.require_writer_calibration(root)) == 64


def test_a_writer_that_finds_no_open_question_fails_and_lane_e_stays_closed(
    checked: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fact_only = EF.answer(SITE, EF.sentence("fact", EF.FACT, EF.Q_FACT))
    root, verdict = _calibrate(checked, tmp_path, fact_only, monkeypatch)
    assert verdict["passed"] is False and verdict["agreement"] == 0.0
    report = json.loads(
        (root / E.WRITER_CALIBRATION_ID / CC.COMPARISON_FILE).read_text(encoding="utf-8")
    )
    assert {(d["unit"], d["fresh"]) for d in report["disagreements"]} == {
        ("open_question", EC.ABSENT),
        ("source", EC.NO_SENTENCE),
    }
    assert report["disagreements"][0]["recorded_sources"] == [EF.RESEARCH]
    with pytest.raises(E.EnrichError, match="does not stand"):
        E.require_writer_calibration(root)


def test_the_comparison_counts_another_host_and_an_unreadable_answer() -> None:
    other = EF.answer(
        SITE,
        EF.sentence("open_question", EF.HOOK, FX.quote("https://elsewhere.org/x", "a quote", "X")),
    )
    assert EC.answer_units(other) == (EC.PRESENT, "elsewhere.org", ["https://elsewhere.org/x"])
    assert EC.answer_units("not json") is None
    assert EC.answer_units(json.dumps({"site_id": SITE})) is None


def test_leave_one_out_renumbers_what_stays_and_refuses_what_it_cannot_keep() -> None:
    a = "https://a.example/one"
    b = "https://b.example/two"
    base = WC4.Base(
        text="First sentence here [1]. Second one is it [2]. Third one again [1].",
        citations=(
            {"n": 1, "url": a, "title": "A", "domain": "a.example"},
            {"n": 2, "url": b, "title": "B", "domain": "b.example"},
        ),
    )
    left, removed, urls = EC.leave_one_out(base, 1)
    assert removed == "First sentence here." and urls == [a]
    assert left.text == "Second one is it [1]. Third one again [2]."
    assert [c["url"] for c in left.citations] == [b, a]
    with pytest.raises(EC.EnrichCalibrationError, match="sentence 4 of 3"):
        EC.leave_one_out(base, 4)


def test_an_unanswered_case_is_never_agreement_and_a_case_needs_its_confirmation(
    checked: Path, tmp_path: Path
) -> None:
    out = tmp_path / "pool"
    EC.build(checked, _cases(tmp_path / "cases.jsonl"), out)
    sealed = {"truth": str(out / EC.TRUTH_FILE), "role": E.WRITER_ROLE}
    report = EC.compare_recovery(sealed, {}, {}, out)
    assert report["unanswered"] == [SITE] and report["units"] == 0
    report = EC.compare_recovery(sealed, {}, {SITE: "not an answer"}, out)
    assert report["unanswered"] == [SITE]
    unconfirmed = tmp_path / "unconfirmed.jsonl"
    unconfirmed.write_text(
        json.dumps({"site_id": SITE, "sentence": 3, "confirmed_by": " ", "note": ""}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EC.EnrichCalibrationError, match="confirmed by someone"):
        EC.build(checked, unconfirmed, tmp_path / "pool3")
