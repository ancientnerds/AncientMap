"""Outbound notifications — currently just a Discord webhook sender.

Lives under pipeline/ because Dockerfile.lyra copies only that tree: the
orchestrator's alert and digest steps run inside the Lyra image, where
`api` does not exist. api/services/notify.py re-exports this function, so
every existing caller keeps its import path.

Fail-soft by design: a missing or failing webhook must never crash the
caller. The quota watchdog (theo_quota_monitor) calls
send_discord_webhook() on every state transition; if the URL is unset or
the call fails, the watchdog logs a warning and continues. No retry —
a missed alert is acceptable; tight loops are not.

Set DISCORD_WEBHOOK_URL in the API container's environment to enable.
Unset = silent no-op. The env-var name matches the convention used by
the discord bot token (api/services/discord_bot.py) and is documented
in .env.example if/when one is added.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def send_discord_webhook(payload: dict) -> bool:
    """POST `payload` to DISCORD_WEBHOOK_URL. Returns True on success, False
    otherwise. Never raises.

    Payload is sent as a JSON body. Discord accepts a number of shapes; the
    simplest is `{"content": "..."}` for plain text, or
    `{"embeds": [...]}` for rich embeds. We don't validate — the caller
    decides the shape.
    """
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        # Fail-soft: unconfigured webhook is a normal state, not an error.
        return False

    try:
        import httpx

        # Visitor text reaches this payload (feedback lines in the weekly
        # digest, error messages in the hourly alert). Without this, anyone
        # could type "@everyone" into a 404 page and ping the channel.
        resp = httpx.post(url, json={**payload, "allowed_mentions": {"parse": []}}, timeout=5.0)
        if resp.status_code >= 400:
            logger.warning(
                "[notify] Discord webhook returned %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        return True
    except Exception as exc:
        # Swallow ALL exceptions: a misconfigured webhook must never crash
        # the watchdog daemon. The error is logged for diagnostics.
        logger.warning("[notify] Discord webhook failed: %s", exc)
        return False


#: Discord rejects a message over 2000 characters; 1900 leaves room for the
#: trailer a caller may append. One implementation for the bot (api side) and
#: the weekly digest (Lyra side), which is why it lives here.
DISCORD_LIMIT = 1900


def split_message(message: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """Split at a paragraph, else a line, else a space, else hard."""
    if len(message) <= limit:
        return [message]
    chunks: list[str] = []
    rest = message
    while len(rest) > limit:
        window = rest[:limit]
        cut = window.rfind("\n\n")
        if cut <= 0:
            cut = window.rfind("\n")
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    if rest:
        chunks.append(rest)
    return chunks
