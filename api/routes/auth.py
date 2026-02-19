"""
Discord OAuth2 authentication routes.

Endpoints:
- GET /auth/discord          → redirect to Discord OAuth
- GET /auth/discord/callback → handle OAuth callback, create JWT
- GET /auth/me               → get current user profile
- GET /auth/credits          → get credits balance + recent usage
- POST /auth/logout          → no-op (JWT is stateless, frontend clears token)
"""

import logging
import os
import secrets
from datetime import datetime, timezone
from math import ceil

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from api.services.jwt_auth import create_token, get_current_user
from api.services.rate_limiter import RateLimiter
from pipeline.database import CreditGrant, DiscordUser, TokenUsageLog, get_session

logger = logging.getLogger(__name__)

router = APIRouter()

# Discord OAuth config
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "932330696956063765")
OG_NERD_ROLE_ID = "972439407086944266"
OG_NERD_CREDIT_AMOUNT = 1000
FOUNDER_ROLE_ID = "933105341292486707"

# Simple in-memory CSRF state store (short-lived, cleared on restart is fine)
_oauth_states: dict[str, float] = {}
_OAUTH_STATE_CAP = 1000

# Rate limit on OAuth redirects: 5 per minute per IP
_oauth_limiter = RateLimiter(max_requests=5, window_seconds=60, namespace="oauth_redirect")


def _cleanup_states():
    """Remove expired CSRF states (older than 10 minutes)."""
    now = datetime.now(timezone.utc).timestamp()
    expired = [k for k, v in _oauth_states.items() if now - v > 600]
    for k in expired:
        del _oauth_states[k]


@router.get("/discord")
async def discord_oauth_redirect(req: Request):
    """Redirect user to Discord OAuth2 authorization page."""
    if not DISCORD_CLIENT_ID or not DISCORD_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Discord OAuth not configured")

    client_ip = req.client.host if req.client else "unknown"
    if not _oauth_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    _cleanup_states()

    if len(_oauth_states) >= _OAUTH_STATE_CAP:
        raise HTTPException(status_code=429, detail="Too many pending logins. Try again later.")

    state = secrets.token_urlsafe(32)
    _oauth_states[state] = datetime.now(timezone.utc).timestamp()

    from urllib.parse import urlencode
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds.members.read",
        "state": state,
        "prompt": "none",
    }
    url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(url=url)


@router.get("/discord/callback")
async def discord_oauth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Handle Discord OAuth2 callback."""
    if error:
        return RedirectResponse(url="/account.html?error=access_denied")

    if not code or not state:
        return RedirectResponse(url="/account.html?error=missing_params")

    # Validate CSRF state
    if state not in _oauth_states:
        return RedirectResponse(url="/account.html?error=invalid_state")
    del _oauth_states[state]

    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET or not DISCORD_REDIRECT_URI:
        return RedirectResponse(url="/account.html?error=not_configured")

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_resp = await client.post(
            "https://discord.com/api/v10/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            logger.error(f"Discord token exchange failed: {token_resp.status_code} {token_resp.text}")
            return RedirectResponse(url="/account.html?error=token_exchange_failed")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return RedirectResponse(url="/account.html?error=no_access_token")

        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # Fetch user info
        user_resp = await client.get("https://discord.com/api/v10/users/@me", headers=auth_headers)
        if user_resp.status_code != 200:
            logger.error(f"Discord user fetch failed: {user_resp.status_code}")
            return RedirectResponse(url="/account.html?error=user_fetch_failed")

        user_data = user_resp.json()
        discord_id = user_data["id"]
        username = user_data.get("global_name") or user_data.get("username", "Unknown")
        avatar_hash = user_data.get("avatar")

        # Fetch guild member info for roles
        roles: list[str] = []
        member_resp = await client.get(
            f"https://discord.com/api/v10/users/@me/guilds/{DISCORD_GUILD_ID}/member",
            headers=auth_headers,
        )
        if member_resp.status_code == 200:
            member_data = member_resp.json()
            roles = member_data.get("roles", [])
        else:
            logger.warning(f"Guild member fetch failed (user may not be in guild): {member_resp.status_code}")

    # Upsert user in database
    with get_session() as session:
        user = session.query(DiscordUser).filter(DiscordUser.discord_id == discord_id).first()
        if user:
            user.username = username
            user.avatar_hash = avatar_hash
            user.roles = roles
            user.last_login = datetime.now(timezone.utc)
        else:
            user = DiscordUser(
                discord_id=discord_id,
                username=username,
                avatar_hash=avatar_hash,
                roles=roles,
                credits=0,
            )
            session.add(user)
            session.flush()  # Get the user ID

        # Grant OG Nerd credits if they have the role and haven't received this grant
        if OG_NERD_ROLE_ID in roles:
            existing_grant = session.query(CreditGrant).filter(
                CreditGrant.user_id == user.id,
                CreditGrant.reason == "og_nerd_role",
            ).first()
            if not existing_grant:
                user.credits += OG_NERD_CREDIT_AMOUNT
                session.add(CreditGrant(
                    user_id=user.id,
                    amount=OG_NERD_CREDIT_AMOUNT,
                    reason="og_nerd_role",
                ))
                logger.info(f"Granted {OG_NERD_CREDIT_AMOUNT} credits to OG Nerd {username}")

        jwt_token = create_token(str(user.id), discord_id)

    response = RedirectResponse(url="/account.html")
    response.set_cookie(
        key="an_auth_token",
        value=jwt_token,
        max_age=120,  # Short-lived: frontend reads it immediately on load
        httponly=False,  # JS needs to read it
        samesite="lax",
        secure=True,
        path="/",
    )
    return response


@router.get("/me")
async def get_me(user: DiscordUser = Depends(get_current_user)):
    """Get current authenticated user profile."""
    avatar_url = None
    if user.avatar_hash:
        avatar_url = f"https://cdn.discordapp.com/avatars/{user.discord_id}/{user.avatar_hash}.png?size=128"

    roles = user.roles or []
    is_founder = FOUNDER_ROLE_ID in roles

    return {
        "id": str(user.id),
        "discord_id": user.discord_id,
        "username": user.username,
        "avatar_url": avatar_url,
        "roles": roles,
        "credits": -1 if is_founder else user.credits,
        "is_og_nerd": OG_NERD_ROLE_ID in roles,
        "is_founder": is_founder,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("/credits")
async def get_credits(user: DiscordUser = Depends(get_current_user)):
    """Get credits balance and recent usage history."""
    is_founder = FOUNDER_ROLE_ID in (user.roles or [])

    with get_session() as session:
        # Refresh credits from DB (in case it was deducted by another request)
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        credits = -1 if is_founder else (db_user.credits if db_user else user.credits)

        # Recent usage (last 20)
        usage = session.query(TokenUsageLog).filter(
            TokenUsageLog.user_id == user.id,
        ).order_by(TokenUsageLog.created_at.desc()).limit(20).all()

        usage_list = [
            {
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "voyage_tokens": u.voyage_tokens,
                "credits_used": u.credits_used,
                "created_at": u.created_at.isoformat(),
            }
            for u in usage
        ]

        # Total credits granted
        grants = session.query(CreditGrant).filter(
            CreditGrant.user_id == user.id,
        ).all()
        grants_list = [
            {
                "amount": g.amount,
                "reason": g.reason,
                "created_at": g.created_at.isoformat(),
            }
            for g in grants
        ]

    return {
        "credits": credits,
        "usage": usage_list,
        "grants": grants_list,
    }


@router.post("/logout")
async def logout():
    """No-op endpoint — JWT is stateless, frontend clears the token."""
    return {"ok": True}
