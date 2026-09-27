"""Archive completion: the full text of every source a moderated claim cites (spec 2.3).

Runs inside the DossierHandler after the moderator, on the VPS. During the run
content_fetch fetched only sources whose adapter snippet was short, and never
Wikipedia, doi.org or YouTube, so about half of the sources behind moderated
claims had no more than an abstract archived. The Claude writer checks every
claim against archived text, so this step fetches what is missing:

* Wikipedia through its REST HTML endpoint (/api/rest_v1/page/html/<title>);
* doi.org by following the redirect to the publisher's landing page;
* PDFs through pypdf, HTML through pipeline.utils.text.extract_text_from_html;
* YouTube as the transcript news_videos holds (what the transcript adapter cites).

TDM reservations are honoured as content_fetch honours them: the row is stored
without its body and the source counts as tdm_reserved. Only this automatic
completion skips such a source (the EU TDM opt-out covers automated full-text
fetching): the paper cites it like any source, and the local claim check
reads it live (owner decision 16, spec 3.5). The step is bounded in
time and concurrency (THEO_ARCHIVE_COMPLETION_MAX_S, at most
MAX_ARCHIVE_COMPLETION_S; THEO_ARCHIVE_COMPLETION_CONCURRENCY), and every
per-source failure is recorded in the manifest, never dropped.
"""

from __future__ import annotations

import asyncio
import io
import os
import time
import urllib.parse
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx
from sqlalchemy import text

from pipeline.lyra.dossier_manifest import moderated_source_ids
from pipeline.lyra.handlers.content_fetch import domain_of, fetch_domain_policy
from pipeline.lyra.theo_publishing import YOUTUBE_ID_RE
from pipeline.lyra.training_corpus import (
    MAX_HTML_CHARS,
    SNIPPET_CONTENT_TYPE,
    DomainPolicy,
    archive_documents,
    best_archive_rows,
    classify_archive_row,
    document_from_source,
    html_reserves_tdm,
    record_run_links,
    reservation_for,
)
from pipeline.utils.http import DEFAULT_HEADERS, is_public_http_url
from pipeline.utils.text import extract_text_from_html

TRANSCRIPT_CONTENT_TYPE = "youtube/transcript"
_HTTP_TIMEOUT_S = 20.0
_MAX_PDF_BYTES = 30_000_000
_TRANSCRIPT_SQL = text("SELECT transcript_text FROM news_videos WHERE id = :id")
_TIME_BUDGET_REASON = "archive completion time budget exhausted"

#: Upper bound of THEO_ARCHIVE_COMPLETION_MAX_S. Archive completion makes no LLM
#: call, so the worker's stall guard sees a frozen progress signature for its
#: whole duration; it must stay below theo_worker._STALL_GRACE_SECONDS (2700 s),
#: or the guard kills a finished run during completion and it ends failed.
MAX_ARCHIVE_COMPLETION_S = 2400.0


class ArchiveFetchError(Exception):
    """One source could not be archived; the reason goes into the manifest."""


@dataclass
class ArchiveStats:
    """The manifest's `archive` section (contract C1)."""

    cited_sources: int = 0
    full_text: int = 0
    abstract_only: int = 0
    missing: int = 0
    tdm_reserved: int = 0
    failures: list[dict] = field(default_factory=list)
    duration_s: float = 0.0
    timed_out: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FetchedDocument:
    """Text of one fetched document plus what the archive row needs."""

    text: str
    html: str
    status: int
    content_type: str
    final_url: str


@dataclass
class _Completed:
    document: Any  # training_corpus.ArchiveDocument
    status: str  # full_text | tdm_reserved


def archive_completion_limits() -> tuple[float, int]:
    """(THEO_ARCHIVE_COMPLETION_MAX_S, THEO_ARCHIVE_COMPLETION_CONCURRENCY), defaults 1800 s and 4."""
    max_seconds = float(os.getenv("THEO_ARCHIVE_COMPLETION_MAX_S", "1800"))
    concurrency = int(os.getenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", "4"))
    if not 1 <= max_seconds <= MAX_ARCHIVE_COMPLETION_S:
        raise ValueError(
            f"THEO_ARCHIVE_COMPLETION_MAX_S must be between 1 and {MAX_ARCHIVE_COMPLETION_S:.0f} s "
            f"(the worker's stall guard fires after 2700 s without progress), got {max_seconds}"
        )
    if concurrency < 1:
        raise ValueError(
            f"THEO_ARCHIVE_COMPLETION_CONCURRENCY must be at least 1, got {concurrency}"
        )
    return max_seconds, concurrency


def youtube_video_id(url: str) -> str | None:
    """The 11-character video id of a youtu.be / youtube.com URL, else None."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = ""
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            candidate = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            candidate = parsed.path.split("/")[2]
    return candidate if YOUTUBE_ID_RE.fullmatch(candidate) else None


def resolve_fetch_url(url: str) -> tuple[str, str]:
    """(kind, URL to fetch): kind is 'wikipedia', 'youtube' or 'web'.

    Wikipedia articles go through the REST HTML endpoint (article HTML without
    skin or navigation). doi.org stays 'web': the client follows the redirect
    to the publisher.
    """
    if youtube_video_id(url):
        return "youtube", url
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    is_wikipedia = host == "wikipedia.org" or host.endswith(".wikipedia.org")
    if is_wikipedia and parsed.path.startswith("/wiki/") and len(parsed.path) > len("/wiki/"):
        title = parsed.path[len("/wiki/") :]
        return "wikipedia", f"https://{host}/api/rest_v1/page/html/{title}"
    return "web", url


def pdf_text(data: bytes) -> str:
    """Text of a PDF (pypdf, imported here: API image only)."""
    from pypdf import PdfReader

    if len(data) > _MAX_PDF_BYTES:
        raise ArchiveFetchError(f"PDF larger than {_MAX_PDF_BYTES} bytes")
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 — pypdf parses untrusted bytes and raises many types; recorded per source
        raise ArchiveFetchError(f"unreadable PDF: {type(exc).__name__}: {exc}") from exc
    body = "\n".join(page.strip() for page in pages if page.strip())
    if not body:
        raise ArchiveFetchError("PDF carries no extractable text (scanned image?)")
    return body


async def fetch_document(client: httpx.AsyncClient, url: str) -> FetchedDocument:
    """Fetch one URL and extract its text (HTML or PDF). Raises ArchiveFetchError."""
    resp = await client.get(url)
    final_url = str(resp.url)
    if resp.status_code != 200:
        raise ArchiveFetchError(f"HTTP {resp.status_code} from {final_url}")
    content_type = resp.headers.get("content-type", "")
    lowered = content_type.lower()
    if "pdf" in lowered or urllib.parse.urlparse(final_url).path.lower().endswith(".pdf"):
        return FetchedDocument(
            text=pdf_text(resp.content),
            html="",
            status=resp.status_code,
            content_type=content_type or "application/pdf",
            final_url=final_url,
        )
    if "html" in lowered or not content_type:
        html = resp.text[:MAX_HTML_CHARS]
        body = extract_text_from_html(html)
        if not body:
            raise ArchiveFetchError(f"page yielded no text: {final_url}")
        return FetchedDocument(
            text=body,
            html=html,
            status=resp.status_code,
            content_type=content_type,
            final_url=final_url,
        )
    raise ArchiveFetchError(f"unsupported content type {content_type!r} from {final_url}")


def load_transcript(video_id: str) -> str:
    """The transcript news_videos holds for a YouTube video, '' when it has none."""
    from pipeline.database import get_session

    with get_session() as session:
        row = session.execute(_TRANSCRIPT_SQL, {"id": video_id}).fetchone()
    if row is None or not row.transcript_text:
        return ""
    return row.transcript_text


def _client() -> httpx.AsyncClient:
    """One client for the whole step: follows redirects (doi.org), 20 s per request.

    The User-Agent names the project, as Wikimedia's API policy asks of API clients.
    """
    return httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT_S,
        follow_redirects=True,
        headers={
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
        },
    )


async def _policy(cache: dict[str, asyncio.Task], host: str) -> DomainPolicy:
    """One reservation lookup per host, shared by concurrent fetches."""
    if host not in cache:
        cache[host] = asyncio.create_task(fetch_domain_policy(host))
    return await asyncio.shield(cache[host])


async def _complete_one(
    client: httpx.AsyncClient, source: Any, policy_cache: dict[str, asyncio.Task]
) -> _Completed:
    kind, fetch_url = resolve_fetch_url(source.url)
    if kind == "youtube":
        video_id = youtube_video_id(source.url)
        transcript = await asyncio.to_thread(load_transcript, video_id)
        if not transcript:
            raise ArchiveFetchError(f"no transcript for YouTube video {video_id} in news_videos")
        document = document_from_source(
            source, full_text=transcript, content_type=TRANSCRIPT_CONTENT_TYPE, archive_only=True
        )
        return _Completed(document, "full_text")
    if not is_public_http_url(fetch_url):
        raise ArchiveFetchError(f"not a public http(s) URL: {fetch_url}")
    page = await fetch_document(client, fetch_url)
    # Wikipedia is fetched through /api/, which robots.txt closes to crawlers; the
    # reservation question is about the article, so it is asked of the /wiki/ URL.
    policy_url = source.url if kind == "wikipedia" else page.final_url
    verdict = reservation_for(policy_url, await _policy(policy_cache, domain_of(policy_url)))
    if not verdict.opt_out and page.html and html_reserves_tdm(page.html):
        verdict.opt_out, verdict.signal = True, "meta_tag"
    document = document_from_source(
        source,
        full_text=page.text,
        raw_html=page.html,
        http_status=page.status,
        content_type=page.content_type,
        archive_only=True,
        tdm_opt_out=verdict.opt_out,
        tdm_signal=verdict.signal,
    )
    return _Completed(document, "tdm_reserved" if verdict.opt_out else "full_text")


async def _fetch_all(
    pending: list, *, max_seconds: float, concurrency: int
) -> tuple[dict[str, _Completed], dict[str, str], bool]:
    """Fetch every pending source: (completed by id, failure reason by id, timed out)."""
    if not pending:
        return {}, {}, False
    gate = asyncio.Semaphore(concurrency)
    policy_cache: dict[str, asyncio.Task] = {}
    async with _client() as client:

        async def run(source: Any) -> _Completed:
            async with gate:
                return await _complete_one(client, source, policy_cache)

        tasks = {source.id: asyncio.create_task(run(source)) for source in pending}
        _done, still_running = await asyncio.wait(tasks.values(), timeout=max(max_seconds, 0.0))
        for task in still_running:
            task.cancel()
        await asyncio.gather(*still_running, return_exceptions=True)
        for task in policy_cache.values():
            task.cancel()
        await asyncio.gather(*policy_cache.values(), return_exceptions=True)

    completed: dict[str, _Completed] = {}
    reasons: dict[str, str] = {}
    for source_id, task in tasks.items():
        if task in still_running:
            reasons[source_id] = _TIME_BUDGET_REASON
            continue
        exc = task.exception()
        if exc is None:
            completed[source_id] = task.result()
        elif isinstance(exc, ArchiveFetchError):
            reasons[source_id] = str(exc)
        elif isinstance(exc, httpx.HTTPError):
            reasons[source_id] = f"{type(exc).__name__}: {exc}"
        else:
            raise exc
    return completed, reasons, bool(still_running)


async def complete_archive(
    request_id: str,
    registry: Any,
    moderated: dict,
    angles: list,
    *,
    max_seconds: float,
    concurrency: int,
) -> ArchiveStats:
    """Archive the full text of every source the moderated claims cite; return the coverage.

    Every cited source ends in exactly one class: full_text, tdm_reserved,
    abstract_only (only an adapter abstract exists; archived here when it was
    not yet) or missing. Every cited source in the registry is linked to the run
    with cited=true (theo_source_archive_runs), meaning "cited by a moderated claim".
    """
    started = time.monotonic()
    targets = moderated_source_ids(moderated)
    stats = ArchiveStats(cited_sources=len(targets))
    known = await asyncio.to_thread(best_archive_rows, targets, with_text=False)

    status: dict[str, str] = {}
    failures: dict[str, dict] = {}
    pending: list = []
    for source_id in targets:
        source = registry.get_reference(source_id)
        if source is None:
            status[source_id] = "missing"
            failures[source_id] = {
                "source_id": source_id,
                "url": "",
                "reason": "source id is not in the citation registry",
            }
            continue
        current = classify_archive_row(known.get(source_id))
        if current in ("full_text", "tdm_reserved"):
            status[source_id] = current
        else:
            pending.append(source)

    completed, reasons, timed_out = await _fetch_all(
        pending, max_seconds=max_seconds - (time.monotonic() - started), concurrency=concurrency
    )

    documents = []
    for source in pending:
        if source.id in completed:
            documents.append(completed[source.id].document)
            status[source.id] = completed[source.id].status
            continue
        failures[source.id] = {
            "source_id": source.id,
            "url": source.url,
            "reason": reasons[source.id],
        }
        if classify_archive_row(known.get(source.id)) == "abstract_only":
            status[source.id] = "abstract_only"
        elif source.snippet:
            documents.append(
                document_from_source(
                    source, full_text=source.snippet, content_type=SNIPPET_CONTENT_TYPE
                )
            )
            status[source.id] = "abstract_only"
        else:
            status[source.id] = "missing"
    await asyncio.to_thread(archive_documents, documents)

    angle_of: dict[str, str] = {}
    for angle in angles:
        for source_id in angle.source_ids:
            angle_of.setdefault(source_id, angle.id)
    links = []
    for source_id in targets:
        source = registry.get_reference(source_id)
        if source is None:
            continue
        links.append(
            {
                "source_id": source_id,
                "angle_id": angle_of.get(source_id, ""),
                "search_query": source.search_query[:2000],
                "cited": True,
            }
        )
    await asyncio.to_thread(record_run_links, request_id, links)

    tally = Counter(status.values())
    stats.full_text = tally["full_text"]
    stats.abstract_only = tally["abstract_only"]
    stats.missing = tally["missing"]
    stats.tdm_reserved = tally["tdm_reserved"]
    stats.failures = [failures[source_id] for source_id in targets if source_id in failures]
    stats.timed_out = timed_out
    stats.duration_s = round(time.monotonic() - started, 1)
    return stats
