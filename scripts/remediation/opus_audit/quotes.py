"""The machine quote check of the Opus re-verification (`output/remediation/opus_audit/RULES.md`).

RULES.md: "A verdict whose quotes cannot be found verbatim (whitespace-normalised) in the cited
evidence file or fetched page does not count; the row is judged again." This module is that check,
and nothing fuzzier.

**Normalisation** (`normalise`), applied to the quote and to the text alike: Unicode NFC, then every
maximal run of whitespace - the characters `str.isspace()` is true for, so a line break, a tab and a
no-break space too - becomes one U+0020, then both ends are stripped. Nothing else: case,
punctuation, quotation marks, dashes, ellipses, ligatures and citation markers are compared as they
are.

**A quote is found** when its normalised text is a substring of the normalised text of one of its
source's readings (`Source.texts`), and the reading that held it is recorded:

* an evidence file - a path relative to the repository that must be one of the row's own
  `evidence_files` (RULES.md: "an evidence file path from the row") - read as UTF-8 text "as
  served", and, when it is JSON (the finder's evidence is the raw API answer, cut at the fetch
  stage's byte cap for the largest pages), each string it holds, decoded ("json text field");
* a fetched page, by what it is: JSON (a MediaWiki `api.php` answer, a Wikidata entity) - the body
  as served and each decoded string; HTML - its visible text (`visible_text`: tags removed,
  entities unescaped, the content of `<script>`, `<style>`, `<template>` and `<title>` dropped, a
  block element's edges read as a line break and an inline element's as nothing); a PDF (by its
  `%PDF-` signature or its Content-Type) - the text `pdftotext -enc UTF-8` extracts; any other
  `text/*` (plain text, MediaWiki `action=raw`) - as served. Anything else is unreadable.

**A verdict counts** only when it has at least one quote and every quote is found.

URLs are fetched once each (`collect`), with the project's User-Agent, following redirects, and
kept under `pages/<sha256 of the URL>.body` (the raw bytes) beside `pages/<sha256>.json` (the URL,
status, final URL, Content-Type, time, size and sha256 of the body). A URL written with `&amp;` where
`&` was meant is the same URL: it is fetched and keyed as `&`, and the quote's record says so.
The project's own site is production: it is never fetched here, and it cannot vouch for itself.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from census.fetch import USER_AGENT  # noqa: E402 - the project's one User-Agent string

from pipeline.utils.http import is_public_http_url  # noqa: E402 - Lyra's own SSRF check

HEADERS = {"User-Agent": USER_AGENT}
#: Seconds between two requests to one host. A chosen courtesy, not a measured limit.
PACE_SECONDS = 1.0
#: The whole request, redirects included, may take this long before it is a failed fetch.
TIMEOUT_SECONDS = 60.0
#: Production. The audit does not touch it, and a page of the database under audit is no evidence.
PRODUCTION_HOSTS = frozenset({"ancientnerds.com", "www.ancientnerds.com"})

# the outcome of one quote
FOUND = "found"
NOT_FOUND = "not found"
EMPTY_QUOTE = "empty quote"
FILE_MISSING = "file missing"
NOT_ROW_FILE = "not an evidence file of this row"
FETCH_FAILED = "fetch failed"
NOT_FETCHED = "not fetched"
UNREADABLE = "unreadable content"
# the outcome of a verdict without a quote
NO_QUOTES = "no quotes"

AMP_NOTE = "&amp; read as &"


class AuditError(ValueError):
    """The audit's inputs are not what the rules need: the run stops and says which."""


# ------------------------------------------------------------------------------ the normaliser
def normalise(text: str) -> str:
    """NFC, then every whitespace run one space, then stripped - and nothing else."""
    return " ".join(unicodedata.normalize("NFC", text).split())


# ------------------------------------------------------------------------------ the readings
_JSON_STRING = re.compile(r'"((?:[^"\\]|\\.)*)(?:"|\Z)', re.DOTALL)
_PARTIAL_ESCAPE = re.compile(r"\\(?:u[0-9a-fA-F]{0,3})?\Z")
#: `strict=False` only lets a raw control character stand inside a string, as it was served.
_DECODER = json.JSONDecoder(strict=False)


def json_texts(text: str) -> list[str]:
    """Every string of a JSON text, decoded - up to the end of a text cut inside its last string.

    The fetch stage keeps at most its byte cap of a page, so the largest evidence files end inside
    a string; the strings before the cut are complete, and the last one is read to the cut.
    """
    out: list[str] = []
    for match in _JSON_STRING.finditer(text):
        body = _PARTIAL_ESCAPE.sub("", match.group(1))
        out.append(_DECODER.decode(f'"{body}"'))
    return out


def _is_json(text: str) -> bool:
    return text.lstrip()[:1] in ("{", "[")


#: Elements whose edges a browser renders as a line break. Every other element is inline.
BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "body", "br", "caption", "dd", "details",
        "dialog", "div", "dl", "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1",
        "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "html", "legend", "li", "main",
        "nav", "ol", "option", "p", "pre", "section", "summary", "table", "tbody", "td", "tfoot",
        "th", "thead", "tr", "ul",
    }
)  # fmt: skip
#: Elements whose content is not shown on the page.
HIDDEN_TAGS = frozenset({"script", "style", "template", "title"})


class _Visible(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in HIDDEN_TAGS:
            self.hidden += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in HIDDEN_TAGS:
            # a stray end tag closes nothing, as in a browser
            self.hidden -= 1 if self.hidden else 0
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def visible_text(html: str) -> str:
    parser = _Visible()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)


_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:\-]+)""", re.I)


def _charset(content_type: str, body: bytes, html: bool) -> str:
    """The HTTP header's charset, else (HTML) the document's own `<meta>`, else UTF-8."""
    for param in content_type.split(";")[1:]:
        name, _, value = param.strip().partition("=")
        if name.strip().lower() == "charset" and value.strip():
            return value.strip().strip("\"'")
    if html:
        match = _META_CHARSET.search(body[:4096])
        if match:
            return match.group(1).decode("ascii")
    return "utf-8"


class PdfUnreadable(ValueError):
    """The PDF reader could not read this body: the page is unreadable, the run goes on."""


def pdftotext(body: bytes) -> str:
    """The text `pdftotext -enc UTF-8` extracts - the one PDF reader of this check."""
    tool = shutil.which("pdftotext")
    if tool is None:
        raise AuditError("reading a PDF page needs pdftotext on PATH (poppler or xpdf)")
    with tempfile.TemporaryDirectory() as tmp:
        pdf, txt = Path(tmp) / "page.pdf", Path(tmp) / "page.txt"
        pdf.write_bytes(body)
        proc = subprocess.run(
            [tool, "-enc", "UTF-8", str(pdf), str(txt)], capture_output=True, timeout=300
        )
        if proc.returncode != 0 or not txt.exists():
            raise PdfUnreadable(f"pdftotext exit {proc.returncode}")
        return txt.read_text(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class Source:
    """What a cited source reads as - its normalised readings - or why it cannot be read."""

    texts: tuple[tuple[str, str], ...] = ()
    failure: str = ""
    detail: str = ""


def _readings(text: str) -> tuple[tuple[str, str], ...]:
    readings = [("as served", normalise(text))]
    if _is_json(text):
        readings += [("json text field", normalise(s)) for s in json_texts(text)]
    return tuple(readings)


def page_source(
    content_type: str, body: bytes, pdf_text: Callable[[bytes], str] = pdftotext
) -> Source:
    """A fetched body's readings, by what the body is (module docstring)."""
    media = content_type.split(";", 1)[0].strip().lower()
    if body.startswith(b"%PDF-") or media == "application/pdf":
        try:
            return Source((("pdf text", normalise(pdf_text(body))),))
        except PdfUnreadable as exc:
            return Source(failure=UNREADABLE, detail=f"application/pdf: {exc}")
    if media == "application/json" or media.endswith("+json"):
        return Source(_readings(body.decode("utf-8-sig", errors="replace")))
    html = media in ("text/html", "application/xhtml+xml")
    if not (html or media.startswith("text/")):
        return Source(failure=UNREADABLE, detail=media or "no Content-Type")
    charset = _charset(content_type, body, html)
    try:
        codecs.lookup(charset)
    except LookupError:
        return Source(failure=UNREADABLE, detail=f"unknown charset {charset!r}")
    text = body.decode(charset, errors="replace")
    if html:
        return Source((("visible text", normalise(visible_text(text))),))
    return Source(_readings(text))


# ------------------------------------------------------------------------------ the page cache
def canonical_url(url: str) -> tuple[str, bool]:
    """The URL meant, and whether it was written with `&amp;` for `&` (that one escape only)."""
    if "&amp;" in url:
        return url.replace("&amp;", "&"), True
    return url, False


def url_key(url: str) -> str:
    return hashlib.sha256(canonical_url(url)[0].encode("utf-8")).hexdigest()


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def not_fetchable(url: str) -> str:
    """Why this URL is never fetched here, or "" when it may be."""
    host = (urlsplit(url).hostname or "").lower()
    if host in PRODUCTION_HOSTS:
        return f"{host} is production: the audit does not touch it"
    if not is_public_http_url(url):
        return "not a public http(s) URL"
    return ""


def store_page(
    pages: Path,
    url: str,
    *,
    status: int | None,
    final_url: str,
    content_type: str,
    body: bytes,
    error: str,
    fetched_at: str,
) -> None:
    """Keep one fetch: the raw body, then the record that names it (so a record means a body)."""
    pages.mkdir(parents=True, exist_ok=True)
    key = url_key(url)
    (pages / f"{key}.body").write_bytes(body)
    meta = {
        "url": canonical_url(url)[0],
        "status": status,
        "final_url": final_url,
        "content_type": content_type,
        "bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "error": error,
        "fetched_at": fetched_at,
    }
    (pages / f"{key}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def collect(
    urls: Iterable[str],
    pages: Path,
    client: httpx.Client,
    *,
    now: Callable[[], str],
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, int]:
    """Fetch every URL not yet kept, once; a failed fetch is kept too, with its status or error."""
    counts = {"fetched": 0, "cached": 0, "not fetched": 0}
    last: dict[str, float] = {}
    for url in sorted({canonical_url(u)[0] for u in urls}):
        if not_fetchable(url):
            counts["not fetched"] += 1
            continue
        if (pages / f"{url_key(url)}.json").exists():
            counts["cached"] += 1
            continue
        host = urlsplit(url).hostname or ""
        if host in last and last[host] + pace > time.monotonic():
            sleep(last[host] + pace - time.monotonic())
        last[host] = time.monotonic()
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            # the fetch failed: that is the record, and a quote on this page will not count
            store_page(
                pages,
                url,
                status=None,
                final_url="",
                content_type="",
                body=b"",
                error=f"{type(exc).__name__}: {exc}",
                fetched_at=now(),
            )
        else:
            store_page(
                pages,
                url,
                status=response.status_code,
                final_url=str(response.url),
                content_type=response.headers.get("Content-Type", ""),
                body=response.content,
                error="",
                fetched_at=now(),
            )
        counts["fetched"] += 1
    return counts


def page_index(urls: Iterable[str], pages: Path) -> list[dict[str, Any]]:
    """One line per cited URL (PAGES.jsonl): its fetch record, or why it was never fetched."""
    out: list[dict[str, Any]] = []
    for url in sorted({canonical_url(u)[0] for u in urls}):
        refused = not_fetchable(url)
        if refused:
            out.append({"url": url, "key": url_key(url), "not_fetched": refused})
            continue
        meta = json.loads((pages / f"{url_key(url)}.json").read_text(encoding="utf-8"))
        out.append(
            {"url": url, "key": url_key(url), **{k: v for k, v in meta.items() if k != "url"}}
        )
    return out


def http_client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT_SECONDS)


# ------------------------------------------------------------------------------ the check
@dataclass(frozen=True)
class QuoteResult:
    source: str
    quote: str
    outcome: str
    detail: str


@dataclass(frozen=True)
class VerdictCheck:
    """Whether a verdict counts, each quote's outcome, and the first failure's outcome."""

    counted: bool
    quotes: tuple[QuoteResult, ...]
    reason: str


class Library:
    """The sources verdicts cite: the repository's evidence files and the kept pages, read once."""

    def __init__(
        self, repo: Path, pages: Path, pdf_text: Callable[[bytes], str] = pdftotext
    ) -> None:
        self.repo = repo
        self.pages = pages
        self.pdf_text = pdf_text
        self._cache: dict[str, Source] = {}

    def file(self, rel: str) -> Source:
        if rel not in self._cache:
            path = self.repo / rel
            if not path.is_file():
                self._cache[rel] = Source(failure=FILE_MISSING, detail=rel)
            else:
                self._cache[rel] = Source(_readings(path.read_bytes().decode("utf-8")))
        return self._cache[rel]

    def url(self, url: str) -> Source:
        canonical = canonical_url(url)[0]
        if canonical not in self._cache:
            self._cache[canonical] = self._page(canonical)
        return self._cache[canonical]

    def _page(self, url: str) -> Source:
        refused = not_fetchable(url)
        if refused:
            return Source(failure=NOT_FETCHED, detail=refused)
        key = url_key(url)
        meta_path = self.pages / f"{key}.json"
        if not meta_path.exists():
            raise AuditError(f"{url} was not collected - run `run.py fetch` first")
        meta: Mapping[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta["status"] is None:
            return Source(failure=FETCH_FAILED, detail=str(meta["error"]))
        if not 200 <= int(meta["status"]) < 300:
            return Source(failure=FETCH_FAILED, detail=f"status {meta['status']}")
        body = (self.pages / f"{key}.body").read_bytes()
        if hashlib.sha256(body).hexdigest() != meta["body_sha256"]:
            raise AuditError(f"{key}.body is not the body its record names")
        return page_source(str(meta["content_type"]), body, self.pdf_text)


def check_quote(quote: Mapping[str, Any], row: Mapping[str, Any], library: Library) -> QuoteResult:
    source, text = quote["source"], quote["quote"]
    if not isinstance(source, str) or not isinstance(text, str):
        raise AuditError(f"{row['change_key']}: a quote needs a source and a text: {quote!r}")
    notes: list[str] = []
    if is_url(source):
        if canonical_url(source)[1]:
            notes.append(AMP_NOTE)
        read = library.url(source)
    elif source not in row["evidence_files"]:
        return QuoteResult(source, text, NOT_ROW_FILE, "")
    else:
        read = library.file(source)
    if read.failure:
        return QuoteResult(source, text, read.failure, "; ".join([read.detail, *notes]))
    wanted = normalise(text)
    if not wanted:
        return QuoteResult(source, text, EMPTY_QUOTE, "")
    for reading, haystack in read.texts:
        if wanted in haystack:
            return QuoteResult(source, text, FOUND, "; ".join([reading, *notes]))
    return QuoteResult(source, text, NOT_FOUND, "; ".join(notes))


def check_verdict(
    verdict: Mapping[str, Any], row: Mapping[str, Any], library: Library
) -> VerdictCheck:
    results = tuple(check_quote(q, row, library) for q in verdict["quotes"])
    if not results:
        return VerdictCheck(False, (), NO_QUOTES)
    failed = [r.outcome for r in results if r.outcome != FOUND]
    return VerdictCheck(not failed, results, failed[0] if failed else "")
