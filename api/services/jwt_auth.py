"""
JWT authentication for Discord OAuth users.

Uses PyJWT with HS256 signing via API_SECRET_KEY.
"""

import logging
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request

from pipeline.database import DiscordUser, get_session

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("API_SECRET_KEY", "")
ALGORITHM = "HS256"
TOKEN_EXPIRY_DAYS = 7
FOUNDER_ROLE_ID = "933105341292486707"


def verify_secret_key() -> None:
    """Verify API_SECRET_KEY is set. Call during app startup to fail fast."""
    if not SECRET_KEY:
        raise RuntimeError(
            "API_SECRET_KEY environment variable is not set. "
            "The API cannot start without a signing key for JWT tokens."
        )


def create_token(user_id: str, discord_id: str) -> str:
    """Create a signed JWT for an authenticated user."""
    if not SECRET_KEY:
        raise RuntimeError("API_SECRET_KEY not set — refusing to sign tokens with empty secret")
    payload = {
        "sub": discord_id,
        "user_id": user_id,
        "exp": datetime.now(UTC) + timedelta(days=TOKEN_EXPIRY_DAYS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    if not SECRET_KEY:
        raise HTTPException(status_code=503, detail="Auth not configured")
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(status_code=401, detail="Token expired") from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err


def _extract_bearer(request: Request) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_current_user(request: Request) -> DiscordUser:
    """FastAPI dependency: require authenticated user. Raises 401 if not."""
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = _decode_token(token)
    discord_id = payload.get("sub")
    if not discord_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    with get_session() as session:
        user = session.query(DiscordUser).filter(DiscordUser.discord_id == discord_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        # Detach from session so it's usable outside the context manager
        session.expunge(user)
        return user


def get_optional_user(request: Request) -> DiscordUser | None:
    """FastAPI dependency: return user if authenticated, None otherwise."""
    token = _extract_bearer(request)
    if not token:
        return None

    try:
        payload = _decode_token(token)
    except HTTPException:
        return None

    discord_id = payload.get("sub")
    if not discord_id:
        return None

    with get_session() as session:
        user = session.query(DiscordUser).filter(DiscordUser.discord_id == discord_id).first()
        if user:
            session.expunge(user)
        return user


async def require_founder(user: DiscordUser = Depends(get_current_user)) -> DiscordUser:
    """Dependency that requires the user to have the Founder role."""
    if FOUNDER_ROLE_ID not in (user.roles or []):
        raise HTTPException(status_code=403, detail="Founders only")
    return user
