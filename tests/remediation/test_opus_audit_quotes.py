"""The machine quote check of the Opus re-verification (`scripts/remediation/opus_audit/quotes.py`).

RULES.md: "A verdict whose quotes cannot be found verbatim (whitespace-normalised) in the cited
evidence file or fetched page does not count; the row is judged again." Every test here builds its
own evidence files and page cache under `tmp_path`; the fetch runs against `httpx.MockTransport`,
so nothing opens a socket.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from opus_audit import quotes as Q  # noqa: E402

NOW = "2026-09-24T12:00:00+00:00"
EVIDENCE = "runs/batch-0001/evidence/site-1%2Fenwiki.txt"
ES_URL = "https://es.wikipedia.org/wiki/Tarmatambo"
API_URL = "https://en.wikipedia.org/w/api.php?action=query&prop=extracts&titles=Aguada&format=json"


def _row(*evidence: str) -> dict[str, object]:
    return {"change_key": "phase3:k1", "evidence_files": list(evidence or (EVIDENCE,))}


def _verdict(*quotes: tuple[str, str]) -> dict[str, object]:
    return {
        "change_key": "phase3:k1",
        "verdict": "revert",
        "right_value": None,
        "reason": "r",
        "quotes": [{"source": s, "quote": q} for s, q in quotes],
    }


def _evidence(root: Path, text: str, rel: str = EVIDENCE) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _page(root: Path, url: str, body: bytes | str, **meta: object) -> None:
    Q.store_page(
        root / "pages",
        url,
        status=meta.get("status", 200),  # type: ignore[arg-type]
        final_url=url,
        content_type=str(meta.get("content_type", "text/html; charset=utf-8")),
        body=body.encode("utf-8") if isinstance(body, str) else body,
        error=str(meta.get("error", "")),
        fetched_at=NOW,
    )


def _library(root: Path, **kwargs: object) -> Q.Library:
    return Q.Library(root, root / "pages", **kwargs)  # type: ignore[arg-type]


def _check(root: Path, *quotes: tuple[str, str], row: dict[str, object] | None = None, **kw):
    return Q.check_verdict(_verdict(*quotes), row or _row(), _library(root, **kw))


# ------------------------------------------------------------------------------ the normaliser
def test_whitespace_runs_become_one_space_and_the_ends_are_stripped() -> None:
    assert Q.normalise("  built\n\tfrom  around 1000 BC \r\n") == "built from around 1000 BC"


def test_a_decomposed_letter_equals_its_composed_form() -> None:
    decomposed, composed = "Aguada Fénix", "Aguada Fénix"
    assert decomposed != composed
    assert Q.normalise(decomposed) == Q.normalise(composed) == composed


def test_nothing_but_whitespace_and_nfc_is_normalised() -> None:
    """Case, quotation marks, dashes and ellipses are compared as they are - nothing fuzzier."""
    for quote, text in [
        ("Built from", "built from"),
        ("the “temple”", 'the "temple"'),
        ("1000–1500", "1000-1500"),
        ("from around…", "from around..."),
        ("ﬁre", "fire"),
    ]:
        assert Q.normalise(quote) != Q.normalise(text)


# ------------------------------------------------------------------------------ evidence files
def test_a_quote_is_found_in_the_decoded_text_of_a_json_evidence_file(tmp_path: Path) -> None:
    _evidence(
        tmp_path, '{"query":{"pages":{"1":{"extract":"Aguada F\\u00e9nix is a\\nlarge site."}}}}'
    )
    check = _check(tmp_path, (EVIDENCE, "Aguada Fénix is a large site."))
    assert check.counted
    assert check.quotes[0].outcome == Q.FOUND
    assert check.quotes[0].detail == "json text field"


def test_a_quote_is_found_in_the_raw_text_of_an_evidence_file(tmp_path: Path) -> None:
    _evidence(tmp_path, '{"descriptions":{"en":{"language":"en","value":"city of Sicily"}}}')
    check = _check(tmp_path, (EVIDENCE, '"value":"city of Sicily"'))
    assert check.counted
    assert check.quotes[0].detail == "as served"


def test_a_truncated_json_evidence_file_is_read_to_its_cut(tmp_path: Path) -> None:
    """The fetch stage cuts a page at its byte cap: the JSON then ends inside its last string."""
    _evidence(
        tmp_path, '{"query":{"pages":{"1":{"title":"Dougga","extract":"Thugga la rom\\u00e1na, 200'
    )
    assert _check(tmp_path, (EVIDENCE, "Thugga la romána, 200")).counted


def test_a_plain_text_evidence_file_is_read_as_it_is(tmp_path: Path) -> None:
    _evidence(
        tmp_path, "Wikidata item Q5690, read through the Wikidata Query Service: inception 1000"
    )
    assert _check(tmp_path, (EVIDENCE, "read through the Wikidata Query Service")).counted


def test_a_file_that_is_not_one_of_the_rows_evidence_files_does_not_count(tmp_path: Path) -> None:
    """Measured 2026-09-24: a pass-2 verdict on Tarmatambo quoted the Shetland site's evidence."""
    other = "runs/batch-0052/evidence/other-site%2Fenwiki.txt"
    _evidence(tmp_path, "when Neolithic farmers first came to Shetland", other)
    check = _check(tmp_path, (other, "when Neolithic farmers first came to Shetland"))
    assert not check.counted
    assert check.quotes[0].outcome == Q.NOT_ROW_FILE


def test_a_missing_evidence_file_does_not_count(tmp_path: Path) -> None:
    check = _check(tmp_path, (EVIDENCE, "anything"))
    assert not check.counted
    assert check.quotes[0].outcome == Q.FILE_MISSING


def test_a_quote_that_is_not_in_the_file_does_not_count(tmp_path: Path) -> None:
    _evidence(tmp_path, '{"extract":"built from around 1000 BC to 800 BC"}')
    check = _check(tmp_path, (EVIDENCE, "built from around 1200 BC"))
    assert not check.counted
    assert check.quotes[0].outcome == Q.NOT_FOUND


def test_an_empty_quote_is_never_found(tmp_path: Path) -> None:
    _evidence(tmp_path, '{"extract":"built from around 1000 BC"}')
    check = _check(tmp_path, (EVIDENCE, " \n "))
    assert not check.counted
    assert check.quotes[0].outcome == Q.EMPTY_QUOTE


# ------------------------------------------------------------------------------ the verdict
def test_a_verdict_counts_only_when_every_quote_is_found(tmp_path: Path) -> None:
    _evidence(tmp_path, '{"extract":"built from around 1000 BC"}')
    both = _check(tmp_path, (EVIDENCE, "built from"), (EVIDENCE, "around 1000 BC"))
    one = _check(tmp_path, (EVIDENCE, "built from"), (EVIDENCE, "around 900 BC"))
    assert both.counted and not one.counted
    assert [q.outcome for q in one.quotes] == [Q.FOUND, Q.NOT_FOUND]
    assert one.reason == Q.NOT_FOUND


def test_a_verdict_without_a_quote_does_not_count(tmp_path: Path) -> None:
    check = _check(tmp_path)
    assert not check.counted
    assert check.reason == Q.NO_QUOTES


# ------------------------------------------------------------------------------ fetched pages
def test_html_is_compared_against_its_visible_text(tmp_path: Path) -> None:
    html = (
        "<html><head><title>T</title><style>.x{}</style></head><body>"
        "<p>Tarmatambo es un sitio <b>arqueol&oacute;gico</b> correspondiente a una antigua "
        "<a href='/llacta'>llacta</a> inca&#46;</p><div>Rango medio</div>"
        "<script>var hidden = 'only in a script';</script></body></html>"
    )
    _page(tmp_path, ES_URL, html)
    found = "es un sitio arqueológico correspondiente a una antigua llacta inca."
    assert _check(tmp_path, (ES_URL, found)).counted
    # a block element's edge reads as a line break, so its words do not run together
    assert _check(tmp_path, (ES_URL, "inca. Rango medio")).counted
    assert not _check(tmp_path, (ES_URL, "inca.Rango medio")).counted
    # the markup and a script's text are not visible text
    assert not _check(tmp_path, (ES_URL, "<b>arqueol")).counted
    assert not _check(tmp_path, (ES_URL, "only in a script")).counted


def test_an_html_page_is_decoded_by_its_declared_charset(tmp_path: Path) -> None:
    body = "<p>Sitio arqueológico de Pucará</p>".encode("latin-1")
    _page(tmp_path, ES_URL, body, content_type="text/html; charset=ISO-8859-1")
    assert _check(tmp_path, (ES_URL, "Sitio arqueológico de Pucará")).counted


def test_a_mediawiki_api_answer_is_compared_against_its_json_text_fields(tmp_path: Path) -> None:
    body = json.dumps({"query": {"pages": {"1": {"extract": "Aguada Fénix is a\nlarge site"}}}})
    assert "\\u00e9" in body  # served escaped, as the API serves it
    _page(tmp_path, API_URL, body, content_type="application/json; charset=utf-8")
    check = _check(tmp_path, (API_URL, "Aguada Fénix is a large site"))
    assert check.counted
    assert check.quotes[0].detail == "json text field"


def test_a_pdf_is_compared_against_the_text_the_extractor_reads(tmp_path: Path) -> None:
    url = "https://example.org/report.pdf"
    _page(tmp_path, url, b"%PDF-1.4 binary", content_type="application/octet-stream")
    seen: list[bytes] = []

    def extractor(body: bytes) -> str:
        seen.append(body)
        return "Construido por la cultura\nCanchis"

    check = _check(tmp_path, (url, "Construido por la cultura Canchis"), pdf_text=extractor)
    assert check.counted
    assert seen == [b"%PDF-1.4 binary"]


def test_a_pdf_the_extractor_cannot_read_is_unreadable_and_the_check_goes_on(
    tmp_path: Path,
) -> None:
    url = "https://example.org/report.pdf"
    _page(tmp_path, url, b"%PDF-1.4 damaged", content_type="application/pdf")

    def extractor(body: bytes) -> str:
        raise Q.PdfUnreadable("pdftotext exit 1")

    check = _check(tmp_path, (url, "anything"), pdf_text=extractor)
    assert check.quotes[0].outcome == Q.UNREADABLE
    assert check.quotes[0].detail == "application/pdf: pdftotext exit 1"


def test_a_page_of_another_content_type_is_unreadable(tmp_path: Path) -> None:
    url = "https://example.org/photo.jpg"
    _page(tmp_path, url, b"\xff\xd8\xff", content_type="image/jpeg")
    check = _check(tmp_path, (url, "anything"))
    assert not check.counted
    assert check.quotes[0].outcome == Q.UNREADABLE
    assert "image/jpeg" in check.quotes[0].detail


def test_a_page_that_answered_with_an_error_status_does_not_count(tmp_path: Path) -> None:
    _page(tmp_path, ES_URL, "<p>Tarmatambo es un sitio</p>", status=404)
    check = _check(tmp_path, (ES_URL, "Tarmatambo es un sitio"))
    assert not check.counted
    assert check.quotes[0].outcome == Q.FETCH_FAILED
    assert check.quotes[0].detail == "status 404"


def test_a_page_that_could_not_be_fetched_names_the_error(tmp_path: Path) -> None:
    _page(tmp_path, ES_URL, b"", status=None, error="ConnectTimeout: timed out")
    check = _check(tmp_path, (ES_URL, "Tarmatambo"))
    assert check.quotes[0].outcome == Q.FETCH_FAILED
    assert check.quotes[0].detail == "ConnectTimeout: timed out"


def test_a_url_that_was_never_collected_stops_the_check(tmp_path: Path) -> None:
    with pytest.raises(Q.AuditError, match="not collected"):
        _check(tmp_path, (ES_URL, "Tarmatambo"))


def test_a_kept_body_that_is_not_the_one_its_record_names_stops_the_check(tmp_path: Path) -> None:
    _page(tmp_path, ES_URL, "<p>Tarmatambo es un sitio</p>")
    (tmp_path / "pages" / f"{Q.url_key(ES_URL)}.body").write_bytes(b"<p>Tarmatambo es otro</p>")
    with pytest.raises(Q.AuditError, match="not the body its record names"):
        _check(tmp_path, (ES_URL, "Tarmatambo es otro"))


def test_the_projects_own_site_is_never_fetched_and_never_counts(tmp_path: Path) -> None:
    """ancientnerds.com is production: the audit does not touch it, and it cannot vouch for itself."""
    url = "https://ancientnerds.com/api/sites/b5627c73"
    check = _check(tmp_path, (url, '"type":"Minaret/tower"'))
    assert check.quotes[0].outcome == Q.NOT_FETCHED


def test_an_amp_escaped_url_is_the_same_url_and_says_so(tmp_path: Path) -> None:
    escaped = API_URL.replace("&", "&amp;")
    assert Q.url_key(escaped) == Q.url_key(API_URL)
    _page(tmp_path, API_URL, json.dumps({"extract": "large site"}), content_type="application/json")
    check = _check(tmp_path, (escaped, "large site"))
    assert check.counted
    assert "&amp; read as &" in check.quotes[0].detail


# ------------------------------------------------------------------------------ the fetch
def test_every_url_is_fetched_once_and_its_raw_bytes_kept(tmp_path: Path) -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        assert request.headers["User-Agent"] == Q.USER_AGENT
        if "missing" in str(request.url):
            return httpx.Response(404, content=b"gone", headers={"Content-Type": "text/plain"})
        return httpx.Response(200, content=b"<p>page</p>", headers={"Content-Type": "text/html"})

    pages = tmp_path / "pages"
    urls = [ES_URL, "https://example.org/missing", API_URL, API_URL.replace("&", "&amp;")]
    with httpx.Client(transport=httpx.MockTransport(handler), headers=Q.HEADERS) as client:
        first = Q.collect(urls, pages, client, now=lambda: NOW, sleep=lambda _s: None)
        again = Q.collect(urls, pages, client, now=lambda: NOW, sleep=lambda _s: None)
    assert len(asked) == 3  # the &amp; form is the same URL; the second run fetches nothing
    assert first == {"fetched": 3, "cached": 0, "not fetched": 0}
    assert again == {"fetched": 0, "cached": 3, "not fetched": 0}
    key = Q.url_key(ES_URL)
    assert (pages / f"{key}.body").read_bytes() == b"<p>page</p>"
    meta = json.loads((pages / f"{key}.json").read_text(encoding="utf-8"))
    assert meta["url"] == ES_URL and meta["status"] == 200 and meta["fetched_at"] == NOW
    missing = json.loads((pages / f"{Q.url_key('https://example.org/missing')}.json").read_text())
    assert missing["status"] == 404


def test_a_second_request_to_one_host_waits_and_another_host_does_not(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x", headers={"Content-Type": "text/plain"})

    waits: list[float] = []
    urls = ["https://a.example/1", "https://b.example/1", "https://a.example/2"]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        Q.collect(urls, tmp_path / "pages", client, now=lambda: NOW, sleep=waits.append, pace=30)
    assert len(waits) == 1 and 0 < waits[0] <= 30


def test_the_page_index_names_every_cited_url_its_status_and_its_bytes(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<p>x</p>", headers={"Content-Type": "text/html"})

    urls = [ES_URL, "https://ancientnerds.com/api/sites/x", API_URL.replace("&", "&amp;")]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        Q.collect(urls, tmp_path / "pages", client, now=lambda: NOW, sleep=lambda _s: None)
    index = Q.page_index(urls, tmp_path / "pages")
    assert [x["url"] for x in index] == sorted([ES_URL, API_URL, urls[1]])
    fetched = {x["url"]: x for x in index}
    assert fetched[ES_URL]["status"] == 200 and fetched[ES_URL]["key"] == Q.url_key(ES_URL)
    assert fetched[ES_URL]["body_sha256"] == Q.hashlib.sha256(b"<p>x</p>").hexdigest()
    assert (
        fetched[urls[1]]["not_fetched"]
        == "ancientnerds.com is production: the audit does not touch it"
    )


def test_a_fetch_that_fails_is_recorded_with_its_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        Q.collect([ES_URL], tmp_path / "pages", client, now=lambda: NOW, sleep=lambda _s: None)
    meta = json.loads((tmp_path / "pages" / f"{Q.url_key(ES_URL)}.json").read_text())
    assert meta["status"] is None
    assert meta["error"] == "ConnectTimeout: timed out"


def test_the_projects_own_site_and_private_addresses_are_not_fetched(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"fetched {request.url}")

    urls = ["https://ancientnerds.com/api/sites/x", "http://127.0.0.1/admin"]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        counts = Q.collect(urls, tmp_path / "pages", client, now=lambda: NOW, sleep=lambda _s: None)
    assert counts == {"fetched": 0, "cached": 0, "not fetched": 2}
