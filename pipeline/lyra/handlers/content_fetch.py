"""Content fetch handler -- downloads actual web page content for sources.

Runs between audit and specialist so that specialists analyze full article
text instead of 200-char search snippets.  Replaces each source's snippet
with up to the per-run cap of extracted page text when the fetched content is
longer than what the source already has.

The same responses also feed the training corpus, which keeps the text
UNCAPPED (pipeline/lyra/training_corpus.py). Prompt and archive are two
consumers of one download: the cap below decides what the LLM sees and has no
effect on what is archived, and the archive has no effect on the prompt.
"""

import asyncio
import ipaddress
import logging
import re
import urllib.parse
from dataclasses import dataclass

import httpx

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import ContentFetched, SourcesAudited
from pipeline.lyra.training_corpus import (
    MAX_HTML_CHARS,
    DomainPolicy,
    already_archived,
    archive_documents,
    document_from_source,
    html_reserves_tdm,
    parse_robots,
    parse_tdmrep,
    reservation_for,
)

logger = logging.getLogger(__name__)

# Domains where fetching full content is pointless or blocked
_SKIP_DOMAINS = {"doi.org", "youtube.com", "youtu.be", "wikipedia.org"}

# Corpus equivalent. Wikipedia is deliberately absent: a Wikipedia page is
# pointless in a prompt (the model knows it) but is exactly the kind of
# licensed, well-edited long-form text a domain corpus wants. doi.org resolves
# to publisher landing pages behind paywalls, and YouTube watch pages carry no
# usable text -- their transcripts already live in news_videos.
_ARCHIVE_SKIP_DOMAINS = {"doi.org", "youtube.com", "youtu.be"}

# Fallback cap when settings are unavailable. The effective cap is
# resolved per-run from LyraSettings: source_max_content_chars (Anthropic) or
# minimax_source_max_content_chars (MiniMax — M3's 1M context lets specialists
# read full source text instead of 2K snippets).
_MAX_CONTENT_CHARS = 2000
_ALREADY_FETCHED_THRESHOLD = 500
_HTTP_TIMEOUT = 10.0

# Fetches run in waves of this size. Each wave opens its own AsyncClient per
# URL, so an unbounded gather over hundreds of archive candidates would mean
# hundreds of concurrent clients and every response body resident at once.
# The wave also bounds how much HTML is held before it is compressed away.
_FETCH_BATCH = 40


def _resolve_archive_settings() -> tuple[bool, int]:
    """(fetch sources the LLM path skips, cap on those extra fetches per angle)."""
    try:
        from pipeline.lyra.config import _get_settings

        settings = _get_settings()
        return settings.theo_archive_extra_fetch, settings.theo_archive_extra_fetch_cap
    except Exception:
        return False, 0


def _resolve_max_content_chars() -> int:
    """Per-run source-text cap, backend-aware (MiniMax gets the 1M-context cap)."""
    try:
        from pipeline.lyra.config import _get_settings

        settings = _get_settings()
        if settings.llm_backend == "minimax":
            return settings.minimax_source_max_content_chars
        return settings.source_max_content_chars
    except Exception:
        return _MAX_CONTENT_CHARS


def _is_safe_url(url: str) -> bool:
    """Block SSRF: reject internal IPs, non-HTTP schemes, metadata endpoints."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname or ""
        if hostname in ("169.254.169.254", "metadata.google.internal"):
            return False
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # hostname is a domain, not an IP
        return True
    except Exception:
        return False


def _extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML, strip tags."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass
class _Page:
    """One fetched page, before it is split into prompt text and archive row."""

    sid: str
    url: str
    text: str
    html: str
    status: int
    content_type: str


class ContentFetchHandler(BaseHandler):
    """Fetches full page content for an angle's sources after audit."""

    def register(self):
        self.bus.on(SourcesAudited, self._on_sources_audited)

    async def _on_sources_audited(self, event: SourcesAudited):
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if not angle:
            await self.bus.emit(ContentFetched(angle_id=event.angle_id))
            return

        # --- LLM path: unchanged rules, unchanged results -------------------
        llm_candidates: list[tuple[str, str]] = []
        for sid in angle.source_ids:
            source = self.state.registry.get_reference(sid)
            if not source:
                continue
            # Skip if already has substantial content
            if len(source.snippet) >= _ALREADY_FETCHED_THRESHOLD:
                continue
            # Skip domains where fetching is pointless
            if any(skip in source.url for skip in _SKIP_DOMAINS):
                continue
            if not _is_safe_url(source.url):
                continue
            llm_candidates.append((sid, source.url))

        # --- Corpus path: extra candidates plus reservation policies --------
        extra_candidates, policies = await self._plan_archive(angle, llm_candidates)

        if not llm_candidates and not extra_candidates:
            self.state.log(
                "content_fetch",
                f"Angle '{angle.topic}': no sources need content fetch",
            )
            await self.bus.emit(ContentFetched(angle_id=event.angle_id))
            return

        max_content_chars = _resolve_max_content_chars()
        llm_ids = {sid for sid, _ in llm_candidates}
        to_fetch = llm_candidates + extra_candidates

        self.emit_sse(
            {
                "type": "status",
                "content": f"Fetching content from {len(to_fetch)} sources for '{angle.topic}'...",
            }
        )

        fetched = 0
        archived = 0
        for start in range(0, len(to_fetch), _FETCH_BATCH):
            batch = to_fetch[start : start + _FETCH_BATCH]
            pages = await asyncio.gather(*[self._fetch_one(sid, url) for sid, url in batch])
            live = [page for page in pages if page is not None]

            for page in live:
                if page.sid not in llm_ids:
                    continue
                source = self.state.registry.get_reference(page.sid)
                capped = page.text[:max_content_chars]
                if source and len(capped) > len(source.snippet):
                    source.snippet = capped
                    fetched += 1

            archived += await self._archive_pages(live, llm_ids, policies)

        self.state.log(
            "content_fetch",
            f"Angle '{angle.topic}': fetched content for {fetched}/{len(llm_candidates)} sources, "
            f"archived {archived}/{len(to_fetch)} documents",
        )
        self.emit_sse(
            {
                "type": "status",
                "content": (
                    f"Fetched content for {fetched}/{len(llm_candidates)} sources "
                    f"for '{angle.topic}'"
                ),
            }
        )

        await self.bus.emit(ContentFetched(angle_id=event.angle_id))

    # -----------------------------------------------------------------------
    # Corpus planning + writing. Both are wrapped: the archive is a passenger
    # on this handler and must never be able to fail a research run. Failures
    # are loud in the log AND in the run's debug_log, never silent.
    # -----------------------------------------------------------------------

    async def _plan_archive(
        self, angle, llm_candidates: list[tuple[str, str]]
    ) -> tuple[list[tuple[str, str]], dict[str, DomainPolicy]]:
        """Return (extra fetches for the corpus only, reservation policy per domain)."""
        try:
            candidates: list[tuple[str, str]] = []
            for sid in angle.source_ids:
                source = self.state.registry.get_reference(sid)
                if not source:
                    continue
                if any(skip in source.url for skip in _ARCHIVE_SKIP_DOMAINS):
                    continue
                if not _is_safe_url(source.url):
                    continue
                candidates.append((sid, source.url))

            known = await asyncio.to_thread(already_archived, [sid for sid, _ in candidates])
            candidates = [(sid, url) for sid, url in candidates if sid not in known]

            policies = await self._domain_policies({self._domain_of(url) for _, url in candidates})

            extra_fetch, cap = _resolve_archive_settings()
            llm_ids = {sid for sid, _ in llm_candidates}
            extra: list[tuple[str, str]] = []
            if extra_fetch:
                for sid, url in candidates:
                    policy = policies.get(self._domain_of(url))
                    if sid in llm_ids or policy is None:
                        continue
                    if reservation_for(url, policy).opt_out:
                        continue
                    extra.append((sid, url))
                if len(extra) > cap:
                    self.state.log(
                        "archive",
                        f"Angle '{angle.topic}': archive fetch capped at {cap} "
                        f"({len(extra)} candidates)",
                    )
                    extra = extra[:cap]
            return extra, policies
        except Exception as exc:
            logger.error("[archive] planning failed for angle '%s': %s", angle.topic, exc)
            self.state.log("archive", f"ARCHIVE PLANNING FAILED: {exc}")
            return [], {}

    async def _archive_pages(
        self,
        pages: list[_Page],
        llm_ids: set[str],
        policies: dict[str, DomainPolicy],
    ) -> int:
        """Store fetched pages in the corpus. Returns rows written."""
        if not pages or not policies:
            return 0
        try:
            documents = []
            for page in pages:
                source = self.state.registry.get_reference(page.sid)
                policy = policies.get(self._domain_of(page.url))
                if source is None or policy is None:
                    continue
                verdict = reservation_for(page.url, policy)
                if not verdict.opt_out and html_reserves_tdm(page.html):
                    verdict.opt_out = True
                    verdict.signal = "meta_tag"
                documents.append(
                    document_from_source(
                        source,
                        full_text=page.text,
                        raw_html=page.html,
                        http_status=page.status,
                        content_type=page.content_type,
                        archive_only=page.sid not in llm_ids,
                        tdm_opt_out=verdict.opt_out,
                        tdm_signal=verdict.signal,
                    )
                )
            return await asyncio.to_thread(archive_documents, documents)
        except Exception as exc:
            logger.error("[archive] write failed: %s", exc)
            self.state.log("archive", f"ARCHIVE WRITE FAILED: {exc}")
            return 0

    async def _domain_policies(self, domains: set[str]) -> dict[str, DomainPolicy]:
        """Fetch robots.txt and tdmrep.json once per host."""
        hosts = sorted(d for d in domains if d)
        results = await asyncio.gather(*[self._domain_policy(host) for host in hosts])
        return dict(zip(hosts, results, strict=True))

    @staticmethod
    async def _domain_policy(domain: str) -> DomainPolicy:
        """Reservation signals published by one host.

        A host that answers neither document has reserved nothing, which is
        the normal case. A host we could not reach at all is recorded as
        `check_failed` on every document it produced — an unchecked row must
        never masquerade as a checked one.
        """
        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (research bot)"},
            ) as client:
                robots_resp, tdm_resp = await asyncio.gather(
                    client.get(f"https://{domain}/robots.txt"),
                    client.get(f"https://{domain}/.well-known/tdmrep.json"),
                )
            return DomainPolicy(
                robots=parse_robots(robots_resp.text) if robots_resp.status_code == 200 else None,
                reserved_paths=parse_tdmrep(tdm_resp.text) if tdm_resp.status_code == 200 else (),
            )
        except Exception as exc:
            logger.debug("[archive] reservation check failed for %s: %s", domain, exc)
            return DomainPolicy(check_error=str(exc)[:200])

    @staticmethod
    def _domain_of(url: str) -> str:
        return (urllib.parse.urlparse(url).hostname or "").removeprefix("www.")

    @staticmethod
    async def _fetch_one(sid: str, url: str) -> _Page | None:
        """Fetch a single URL. Returns None when it yields no usable text."""
        try:
            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (research bot)"},
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "html" in content_type or not content_type:
                        html = resp.text[:MAX_HTML_CHARS]
                        text = _extract_text_from_html(html)
                        if text:
                            return _Page(
                                sid=sid,
                                url=url,
                                text=text,
                                html=html,
                                status=resp.status_code,
                                content_type=content_type,
                            )
        except Exception as exc:
            logger.debug("Content fetch failed for %s: %s", url, exc)
        return None
