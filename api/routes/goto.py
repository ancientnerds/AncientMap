# SPDX-License-Identifier: AGPL-3.0-only
"""Measurable Discord funnel redirect.

The Discord CTA sits on all ~7,400 indexed pages, but there was no way to
tell whether anyone clicks it — the site has no analytics, and counting
nginx log hits overstates clicks by ~3x (bots). This route makes the click
itself the measurement: every human-facing Discord link points at
``/goto/discord?src={surface}``, which logs one structured line and 302s to
the real invite.

Privacy: the log line carries ONLY the allowlisted source label, a
bot/human flag derived from the user agent, and the moment of the click in
UTC. No IP, no referer, no cookie, no free text — an unknown ``src`` is
counted as ``unknown``, never echoed.

Read the numbers with scripts/funnel_report.py (docker logs of both API
containers).
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from pipeline.article_html_renderer import DISCORD_INVITE_URL
from pipeline.referral_log import BOT_UA_RE

logger = logging.getLogger(__name__)

router = APIRouter()

#: Where a Discord link can live. Mirrored in
#: ancient-nerds-map/src/constants/brand.ts (DiscordCtaSource) — the sync
#: test in tests/api/test_goto_discord.py fails if the two lists drift.
ALLOWED_SOURCES = frozenset({"seo", "landing", "app", "account", "lyra", "disclaimer"})


@router.get("/goto/discord")
async def goto_discord(request: Request, src: str | None = None) -> RedirectResponse:
    """302 to the Discord invite; log which surface sent the click.

    The redirect must never break: an unrecognized ``src`` still redirects,
    it is just logged as ``unknown`` (the raw value never reaches the log).
    Caching is disabled in nginx (Cache-Control: no-store on the location)
    so every click actually arrives here.
    """
    is_bot = int(bool(BOT_UA_RE.search(request.headers.get("user-agent", ""))))
    label = src if src in ALLOWED_SOURCES else "unknown"
    # The stamp is part of the message, not of the log format: api/main.py
    # formats every line as "LEVEL | logger | message" with no asctime, so
    # until 2026-09-19 this line read "goto_discord src=seo bot=1" and could
    # not be placed in time at all — `docker logs --since` was the only
    # window, and the mounted ancient_nerds_api.log had none. Explicit UTC so
    # the stamp does not depend on the container's timezone, whole seconds
    # because a click needs no millisecond.
    clicked_at = datetime.now(UTC).isoformat(timespec="seconds")
    logger.info("goto_discord src=%s bot=%d at=%s", label, is_bot, clicked_at)
    return RedirectResponse(DISCORD_INVITE_URL, status_code=302)
