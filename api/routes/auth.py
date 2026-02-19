"""
Discord OAuth2 authentication routes.

Endpoints:
- GET /auth/discord          → redirect to Discord OAuth
- GET /auth/discord/callback → handle OAuth callback, create JWT
- GET /auth/me               → get current user profile
- GET /auth/credits          → get credits balance + recent usage
- POST /auth/logout          → no-op (JWT is stateless, frontend clears token)
"""

import calendar
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime
from math import ceil

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.services.jwt_auth import FOUNDER_ROLE_ID, create_token, get_current_user, require_founder
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

# --- Role-based credit configuration ---
# Each Discord role that grants credits is defined here.
# Types: "one_time" = single grant, "monthly" = recurring
# Note: "unlimited" is now a per-user flag (is_unlimited), toggled by admins.
CREDIT_ROLES: dict[str, dict] = {
    OG_NERD_ROLE_ID: {
        "name": "OG Nerd",
        "type": "one_time",
        "amount": 1000,
        "reason": "og_nerd_role",
    },
    # Patreon tiers — add role IDs once they're configured in Discord:
    # "ROLE_ID": {
    #     "name": "Patron Bronze",
    #     "type": "monthly",
    #     "amount": 100,
    #     "cap_multiplier": 3,
    #     "reason": "monthly_patron_bronze",
    # },
}

# Simple in-memory CSRF state store (short-lived, cleared on restart is fine)
_oauth_states: dict[str, float] = {}
_OAUTH_STATE_CAP = 1000

# Rate limit on OAuth redirects: 5 per minute per IP
_oauth_limiter = RateLimiter(max_requests=5, window_seconds=60, namespace="oauth_redirect")


def _clamp_day(year: int, month: int, day: int) -> int:
    """Clamp a day to the max days in a given month (e.g. 31 in Feb → 28)."""
    return min(day, calendar.monthrange(year, month)[1])


def get_eligible_periods(anchor: datetime, now: datetime) -> list[str]:
    """Return period strings ("YYYY-MM") from anchor to now where the anniversary day has passed.

    Limited to the last 3 entries (accumulation window).
    """
    periods: list[str] = []
    anchor_day = anchor.day
    y, m = anchor.year, anchor.month

    while True:
        due_day = _clamp_day(y, m, anchor_day)
        due_date = datetime(y, m, due_day, tzinfo=UTC)
        if due_date > now:
            break
        periods.append(f"{y:04d}-{m:02d}")
        # Advance one month
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1

    # Cap to last 3 periods (accumulation window)
    return periods[-3:]


def process_credit_grants(session: Session, user: DiscordUser) -> None:
    """Evaluate and apply credit grants for all roles the user has.

    Handles one-time, monthly (with cap), and unlimited role types.
    Safe to call repeatedly — idempotent via unique constraint.
    """
    roles = user.roles or []
    now = datetime.now(UTC)

    for role_id, config in CREDIT_ROLES.items():
        if role_id not in roles:
            continue

        role_type = config["type"]
        reason = config["reason"]

        if role_type == "one_time":
            existing = session.query(CreditGrant).filter(
                CreditGrant.user_id == user.id,
                CreditGrant.reason == reason,
                CreditGrant.grant_period.is_(None),
            ).first()
            if not existing:
                amount = config["amount"]
                user.credits += amount
                session.add(CreditGrant(
                    user_id=user.id,
                    amount=amount,
                    reason=reason,
                    grant_period=None,
                ))
                logger.info(f"Granted {amount} credits to {user.username} ({reason})")

        elif role_type == "monthly":
            if user.grant_anchor_date is None:
                user.grant_anchor_date = now

            monthly_amount = config["amount"]
            cap_multiplier = config.get("cap_multiplier", 3)
            max_balance = monthly_amount * cap_multiplier

            for period in get_eligible_periods(user.grant_anchor_date, now):
                existing = session.query(CreditGrant).filter(
                    CreditGrant.user_id == user.id,
                    CreditGrant.reason == reason,
                    CreditGrant.grant_period == period,
                ).first()
                if existing:
                    continue

                effective = min(monthly_amount, max(0, max_balance - user.credits))
                if effective <= 0:
                    continue

                user.credits += effective
                session.add(CreditGrant(
                    user_id=user.id,
                    amount=effective,
                    reason=reason,
                    grant_period=period,
                ))
                logger.info(f"Granted {effective} monthly credits to {user.username} ({reason}, period={period})")

    session.flush()


def _cleanup_states():
    """Remove expired CSRF states (older than 10 minutes)."""
    now = datetime.now(UTC).timestamp()
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
    _oauth_states[state] = datetime.now(UTC).timestamp()

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
            user.last_login = datetime.now(UTC)
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

        # Evaluate and apply credit grants for all roles
        process_credit_grants(session, user)

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
    # Process any pending credit grants (monthly accumulation, etc.)
    with get_session() as session:
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        if db_user:
            process_credit_grants(session, db_user)
            credits = db_user.credits
        else:
            credits = user.credits

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
        "credits": credits,
        "is_unlimited": db_user.is_unlimited if db_user else False,
        "is_og_nerd": OG_NERD_ROLE_ID in roles,
        "is_founder": is_founder,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("/credits")
async def get_credits(user: DiscordUser = Depends(get_current_user)):
    """Get credits balance and recent usage history."""
    with get_session() as session:
        # Refresh credits from DB (in case it was deducted by another request)
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        credits = db_user.credits if db_user else user.credits

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
                "grant_period": g.grant_period,
                "created_at": g.created_at.isoformat(),
            }
            for g in grants
        ]

    return {
        "credits": credits,
        "is_unlimited": db_user.is_unlimited if db_user else False,
        "usage": usage_list,
        "grants": grants_list,
    }


@router.post("/logout")
async def logout():
    """No-op endpoint — JWT is stateless, frontend clears the token."""
    return {"ok": True}


# --- Founder Admin ---


class CreditAdjustRequest(BaseModel):
    user_id: str
    action: str  # "set" or "add"
    amount: int


@router.get("/admin/users")
async def admin_list_users(
    _founder: DiscordUser = Depends(require_founder),
    q: str = Query(default="", max_length=100),
):
    """List users for admin panel. Optional search by username."""
    with get_session() as session:
        query = session.query(DiscordUser)
        if q:
            query = query.filter(DiscordUser.username.ilike(f"%{q}%"))
        users = query.order_by(DiscordUser.last_login.desc()).limit(100).all()

        return {
            "users": [
                {
                    "id": str(u.id),
                    "username": u.username,
                    "avatar_url": (
                        f"https://cdn.discordapp.com/avatars/{u.discord_id}/{u.avatar_hash}.png?size=64"
                        if u.avatar_hash else None
                    ),
                    "credits": u.credits,
                    "is_unlimited": u.is_unlimited,
                    "is_founder": FOUNDER_ROLE_ID in (u.roles or []),
                    "is_og_nerd": OG_NERD_ROLE_ID in (u.roles or []),
                    "last_login": u.last_login.isoformat() if u.last_login else None,
                    "grant_anchor_date": u.grant_anchor_date.isoformat() if u.grant_anchor_date else None,
                }
                for u in users
            ]
        }


@router.post("/admin/credits")
async def admin_adjust_credits(
    body: CreditAdjustRequest,
    _founder: DiscordUser = Depends(require_founder),
):
    """Set, add, remove credits, or toggle unlimited for a user."""
    if body.action not in ("set", "add", "remove", "set_unlimited"):
        raise HTTPException(status_code=400, detail="action must be 'set', 'add', 'remove', or 'set_unlimited'")

    with get_session() as session:
        user = session.query(DiscordUser).filter(
            DiscordUser.id == uuid.UUID(body.user_id),
        ).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if body.action == "set_unlimited":
            user.is_unlimited = body.amount != 0
            session.add(CreditGrant(
                user_id=user.id,
                amount=0,
                reason="unlimited_set" if user.is_unlimited else "unlimited_removed",
            ))
        elif body.action == "set":
            user.credits = body.amount
            session.add(CreditGrant(
                user_id=user.id,
                amount=body.amount,
                reason="founder_grant",
            ))
        elif body.action == "add":
            user.credits += body.amount
            session.add(CreditGrant(
                user_id=user.id,
                amount=body.amount,
                reason="founder_grant",
            ))
        elif body.action == "remove":
            user.credits = max(0, user.credits - body.amount)
            session.add(CreditGrant(
                user_id=user.id,
                amount=-body.amount,
                reason="founder_grant",
            ))

        session.flush()
        new_credits = user.credits
        is_unlimited = user.is_unlimited

    return {"ok": True, "new_credits": new_credits, "is_unlimited": is_unlimited}
