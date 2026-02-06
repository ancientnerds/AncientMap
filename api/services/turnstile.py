"""
Shared Cloudflare Turnstile verification.

Single implementation used by all routes — no duplication.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET_KEY", "")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str, ip: str) -> bool:
    """
    Verify a Cloudflare Turnstile token.

    Fails closed: returns False if secret is missing or verification fails.
    """
    if not TURNSTILE_SECRET:
        logger.error("TURNSTILE_SECRET_KEY not configured — rejecting request")
        return False

    if not token or len(token) < 20:
        logger.warning(f"Invalid Turnstile token format from {ip}")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                TURNSTILE_VERIFY_URL,
                data={
                    "secret": TURNSTILE_SECRET,
                    "response": token,
                    "remoteip": ip,
                },
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success", False):
                    return True
                error_codes = result.get("error-codes", [])
                logger.warning(f"Turnstile verification failed for {ip}: {error_codes}")
                return False

            logger.error(f"Turnstile API returned status {response.status_code}")
            return False
    except httpx.TimeoutException:
        logger.error(f"Turnstile verification timed out for {ip}")
        return False
    except httpx.HTTPError as e:
        logger.error(f"Turnstile HTTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"Turnstile verification error: {e}")
        return False
