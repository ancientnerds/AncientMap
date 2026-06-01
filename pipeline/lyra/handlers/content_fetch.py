"""Content fetch handler -- downloads actual web page content for sources.

Runs between audit and specialist so that specialists analyze full article
text instead of 200-char search snippets.  Replaces each source's snippet
with up to 2000 chars of extracted page text when the fetched content is
longer than what the source already has.
"""

import asyncio
import ipaddress
import logging
import re
import urllib.parse

import httpx

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import ContentFetched, SourcesAudited

logger = logging.getLogger(__name__)

# Domains where fetching full content is pointless or blocked
_SKIP_DOMAINS = {"doi.org", "youtube.com", "youtu.be", "wikipedia.org"}

# Fallback cap when settings are unavailable. The effective cap is
# resolved per-run from LyraSettings: source_max_content_chars (Anthropic) or
# minimax_source_max_content_chars (MiniMax — M3's 1M context lets specialists
# read full source text instead of 2K snippets).
_MAX_CONTENT_CHARS = 2000
_ALREADY_FETCHED_THRESHOLD = 500
_HTTP_TIMEOUT = 10.0


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


class ContentFetchHandler(BaseHandler):
    """Fetches full page content for an angle's sources after audit."""

    def register(self):
        self.bus.on(SourcesAudited, self._on_sources_audited)

    async def _on_sources_audited(self, event: SourcesAudited):
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if not angle:
            await self.bus.emit(ContentFetched(angle_id=event.angle_id))
            return

        # Collect sources eligible for content fetch
        candidates: list[tuple[str, str]] = []
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
            candidates.append((sid, source.url))

        if not candidates:
            self.state.log(
                "content_fetch",
                f"Angle '{angle.topic}': no sources need content fetch",
            )
            await self.bus.emit(ContentFetched(angle_id=event.angle_id))
            return

        max_content_chars = _resolve_max_content_chars()

        self.emit_sse(
            {
                "type": "status",
                "content": f"Fetching content from {len(candidates)} sources for '{angle.topic}'...",
            }
        )

        async def _fetch_one(sid: str, url: str) -> tuple[str, str | None]:
            """Fetch a single URL and return (sid, extracted_text or None)."""
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
                            text = _extract_text_from_html(resp.text)
                            return sid, text[:max_content_chars] if text else None
            except Exception as exc:
                logger.debug("Content fetch failed for %s: %s", url, exc)
            return sid, None

        # Run all fetches in parallel (HTTP calls, not LLM -- no semaphore needed)
        tasks = [_fetch_one(sid, url) for sid, url in candidates]
        results = await asyncio.gather(*tasks)

        fetched = 0
        for sid, text in results:
            if not text:
                continue
            source = self.state.registry.get_reference(sid)
            if source and len(text) > len(source.snippet):
                source.snippet = text
                fetched += 1

        self.state.log(
            "content_fetch",
            f"Angle '{angle.topic}': fetched content for {fetched}/{len(candidates)} sources",
        )
        self.emit_sse(
            {
                "type": "status",
                "content": (
                    f"Fetched content for {fetched}/{len(candidates)} sources for '{angle.topic}'"
                ),
            }
        )

        await self.bus.emit(ContentFetched(angle_id=event.angle_id))
