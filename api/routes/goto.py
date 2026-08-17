# SPDX-License-Identifier: AGPL-3.0-only
"""Measurable Discord funnel redirect.

The Discord CTA sits on all ~7,400 indexed pages, but there was no way to
tell whether anyone clicks it — the site has no analytics, and counting
nginx log hits overstates clicks by ~3x (bots). This route makes the click
itself the measurement: every human-facing Discord link points at
``/goto/discord?src={surface}``, which logs one structured line and 302s to
the real invite.

Privacy: the log line carries ONLY the allowlisted source label and a
bot/human flag derived from the user agent. No IP, no referer, no cookie,
no free text — an unknown ``src`` is counted as ``unknown``, never echoed.

Read the numbers with scripts/funnel_report.py (docker logs of both API
containers).
"""

import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from pipeline.article_html_renderer import DISCORD_INVITE_URL

logger = logging.getLogger(__name__)

router = APIRouter()

#: Where a Discord link can live. Mirrored in
#: ancient-nerds-map/src/constants/brand.ts (DiscordCtaSource) — the sync
#: test in tests/api/test_goto_discord.py fails if the two lists drift.
ALLOWED_SOURCES = frozenset({"seo", "landing", "app", "account", "lyra", "disclaimer"})

#: UA substrings that mark automated clients. Deliberately broad: the point
#: is separating "a human clicked the CTA" from "a crawler followed the
#: link", not perfect bot taxonomy. Misclassified stragglers land in the
#: bot bucket, which only makes the human count conservative.
_BOT_UA_RE = re.compile(
    r"bot|crawl|spider|slurp|scrapy|curl|wget|python-requests|python-httpx|aiohttp"
    r"|headless|phantom|lighthouse|facebookexternalhit|whatsapp|telegram|preview"
    r"|go-http-client|okhttp|java/|libwww",
    re.IGNORECASE,
)


@router.get("/goto/discord")
async def goto_discord(request: Request, src: str | None = None) -> RedirectResponse:
    """302 to the Discord invite; log which surface sent the click.

    The redirect must never break: an unrecognized ``src`` still redirects,
    it is just logged as ``unknown`` (the raw value never reaches the log).
    Caching is disabled in nginx (Cache-Control: no-store on the location)
    so every click actually arrives here.
    """
    is_bot = int(bool(_BOT_UA_RE.search(request.headers.get("user-agent", ""))))
    label = src if src in ALLOWED_SOURCES else "unknown"
    logger.info("goto_discord src=%s bot=%d", label, is_bot)
    return RedirectResponse(DISCORD_INVITE_URL, status_code=302)
