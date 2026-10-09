"""The agents' own quote check (`scripts/remediation/quote_check.py`): the lanes' machine check on one
page, run before an answer is recorded. The fetch runs against `httpx.MockTransport`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import quote_check as QC  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

URL = "https://en.wikipedia.org/wiki/Gough%27s_Cave"
PAGE = (
    "<html><body><p>In 1903 the remains of a human male were found. He is Britain's oldest complete "
    "human skeleton,<sup>[22]</sup> having been dated to the Mesolithic.</p></body></html>"
)


def _client(status: int = 200, body: str = PAGE) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, text=body, headers={"Content-Type": "text/html; charset=utf-8"}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def _check(tmp_path: Path, quote: str, **kw: object) -> dict[str, object]:
    return QC.self_check(
        URL, quote, kw.pop("client", None) or _client(), tmp_path / "pages", now=lambda: "t"
    )  # type: ignore[arg-type]


def test_a_quote_copied_from_the_cache_is_found_on_the_page_with_its_footnote(
    tmp_path: Path,
) -> None:
    result = _check(tmp_path, "oldest complete human skeleton, having been dated to the Mesolithic")
    assert result["ok"] is True and result["outcome"] == Q.FOUND


def test_a_quote_the_page_does_not_hold_says_where_the_page_differs(tmp_path: Path) -> None:
    result = _check(tmp_path, "oldest complete human skeleton, never having been dated")
    assert result["ok"] is False and result["outcome"] == Q.NOT_FOUND
    hint = result["hint"]
    assert isinstance(hint, dict)
    assert hint["quote_found_up_to"] == "oldest complete human skeleton, "
    assert hint["page_continues_with"].startswith("having been dated")
    assert hint["quote_continues_with"].startswith("never having")


def test_a_page_the_source_rule_refuses_is_not_fetched(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be called
        raise AssertionError("a refused source is never fetched")

    result = QC.self_check(
        "https://www.wikiwand.com/en/articles/Gough%27s_Cave",
        "oldest complete human skeleton",
        httpx.Client(transport=httpx.MockTransport(refuse)),
        tmp_path / "pages",
    )
    assert result["ok"] is False and str(result["outcome"]).startswith(QC.SOURCE_REFUSED)


def test_a_page_that_answered_an_error_status_is_a_failed_fetch(tmp_path: Path) -> None:
    result = _check(tmp_path, "oldest complete human skeleton", client=_client(403, "no"))
    assert result["ok"] is False and result["outcome"] == Q.FETCH_FAILED
    assert "403" in str(result["detail"])


def test_the_command_exits_one_for_a_quote_not_found_and_prints_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(Q, "http_client", lambda _agent: _client())
    quote_file = tmp_path / "q.txt"
    quote_file.write_text("oldest complete human skeleton, having been dated", encoding="utf-8")
    assert QC.main(["--url", URL, "--quote-file", str(quote_file)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert QC.main(["--url", URL, "--quote", "a sentence that is not on the page at all"]) == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == Q.NOT_FOUND


def test_an_empty_quote_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert QC.main(["--url", URL, "--quote", "  [22]  "]) == 2


# ------------------------------------------------------------------------------ one rendering
LIVE_FIXTURE = REPO / "tests" / "remediation" / "fixtures" / "quote_markers_live_2026-10-09.json"


def _live_library(tmp_path: Path) -> tuple[Q.Library, list[dict[str, str]]]:
    """The six real pages' paragraphs, kept as fetched pages (they carry `[n]` markers)."""
    cases = json.loads(LIVE_FIXTURE.read_text(encoding="utf-8"))
    for case in cases:
        Q.store_page(
            tmp_path / "pages",
            case["url"],
            status=200,
            final_url=case["url"],
            content_type="text/html; charset=utf-8",
            body=f"<html><body>{case['html']}</body></html>".encode(),
            error="",
            fetched_at="2026-10-09T00:00:00Z",
        )
    return Q.Library(tmp_path, tmp_path / "pages"), cases


class TestEveryLaneReadsTheLivePageAsTheCacheReadsIt:
    """The six quotes of the calibration were copied from the cache; each lane's own quote check
    finds them on the live paragraph, markers and all (all go through `Q.check_quote`)."""

    def test_the_teaser_verifiers_proof(self, tmp_path: Path) -> None:
        from teaser import answers as A
        from teaser import run as R

        library, cases = _live_library(tmp_path)
        for case in cases:
            judged = [A.Judged("a claim", "SUPPORTED", case["url"], case["quote"])]
            (proof,) = R.prove_claims("site", judged, library)
            assert proof["proven"] is True, case["page"]

    def test_the_identity_lanes_quote_check(self, tmp_path: Path) -> None:
        from identity import answers as IA

        library, cases = _live_library(tmp_path)
        for case in cases:
            ok, noted, reason = IA.check_quotes(
                [{"url": case["url"], "quote": case["quote"]}], "site", library
            )
            assert ok and not reason, (case["page"], noted)

    def test_the_acceptance_and_word_check_lanes_quote_check(self, tmp_path: Path) -> None:
        from acceptance import answers as AA

        library, cases = _live_library(tmp_path)
        for case in cases:
            result = AA.check_quotes("label", [AA.Quote(case["url"], case["quote"], None)], library)
            assert result.counted, (case["page"], result.reason)

    def test_no_lane_keeps_a_quote_matcher_of_its_own(self) -> None:
        """Every lane that checks a quote does it through `opus_audit/quotes`; the only other
        normalisers are the frozen Phase-3 metric and the coordinate matcher, neither a lane's check."""
        lanes = ("teaser", "wc", "fields", "identity", "acceptance", "image_roles", "served_image",
                 "mechanical", "l5", "phase4")  # fmt: skip
        own = []
        for lane in lanes:
            for path in sorted((REPO / "scripts" / "remediation" / lane).glob("*.py")):
                if path.name.startswith("mutation_sweep"):
                    continue
                text = path.read_text(encoding="utf-8")
                if "def normalise(" in text or "def normalize_quote(" in text:
                    own.append(path.name)
        assert own == []
