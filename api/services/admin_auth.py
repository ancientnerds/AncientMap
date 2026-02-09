"""
Shared admin PIN verification.

Used by: site editing, connector refresh, connector tests.
"""

import logging
import os
import secrets

from fastapi import Request
from pydantic import BaseModel, Field

from api.services.turnstile import verify_turnstile

logger = logging.getLogger(__name__)

ADMIN_PIN = os.environ.get("ADMIN_PIN", "")
if not ADMIN_PIN:
    logger.warning("ADMIN_PIN not set — admin endpoints will reject all attempts")

# When behind a reverse proxy (nginx), trust X-Forwarded-For.
# Set TRUSTED_PROXY=1 in env when deployed behind nginx/Caddy.
_BEHIND_PROXY = os.environ.get("TRUSTED_PROXY", "").strip() in ("1", "true", "yes")


class AdminPinRequest(BaseModel):
    """Request body for any admin-PIN-gated action."""
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    turnstile_token: str = Field(..., description="Cloudflare Turnstile verification token")


class AdminPinResponse(BaseModel):
    """Response from admin PIN verification."""
    verified: bool
    error: str | None = None
    message: str | None = None
    cooldown_remaining: int | None = None


def get_client_ip(request: Request) -> str:
    """Extract client IP from the request.

    Only trusts X-Forwarded-For when TRUSTED_PROXY=1, and uses the
    rightmost entry (added by the reverse proxy closest to us).
    """
    ip = request.client.host if request.client else "unknown"
    if _BEHIND_PROXY:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Rightmost entry is the one added by our trusted proxy
            ip = forwarded.split(",")[-1].strip()
    return ip


async def verify_admin_pin(pin: str, turnstile_token: str, ip: str) -> AdminPinResponse:
    """
    Verify Turnstile + admin PIN.

    Returns AdminPinResponse — caller can add extra checks (rate limiting, etc.)
    before or after calling this.
    """
    if not await verify_turnstile(turnstile_token, ip):
        return AdminPinResponse(
            verified=False,
            error="captcha_failed",
            message="Verification failed. Please complete the captcha and try again.",
        )

    if not ADMIN_PIN:
        logger.warning(f"Admin PIN not configured — rejecting attempt from {ip}")
        return AdminPinResponse(
            verified=False,
            error="not_configured",
            message="Admin access is not configured.",
        )

    if not secrets.compare_digest(pin, ADMIN_PIN):
        logger.warning(f"Invalid admin PIN attempt from {ip}")
        return AdminPinResponse(
            verified=False,
            error="invalid_pin",
            message="Invalid PIN.",
        )

    return AdminPinResponse(verified=True, message="Admin access granted")
