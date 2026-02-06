"""
Shared admin PIN verification.

Used by: site editing, connector refresh, connector tests.
"""

import logging
import os

from fastapi import Request
from pydantic import BaseModel, Field

from api.services.turnstile import verify_turnstile

logger = logging.getLogger(__name__)

ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")


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
    """Extract client IP, respecting X-Forwarded-For for proxied requests."""
    ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
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

    if pin != ADMIN_PIN:
        logger.warning(f"Invalid admin PIN attempt from {ip}")
        return AdminPinResponse(
            verified=False,
            error="invalid_pin",
            message="Invalid PIN.",
        )

    return AdminPinResponse(verified=True, message="Admin access granted")
