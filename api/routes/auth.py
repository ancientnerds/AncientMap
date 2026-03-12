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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.services.jwt_auth import FOUNDER_ROLE_ID, create_token, get_current_user, require_founder
from api.services.rate_limiter import RateLimiter, get_client_ip
from pipeline.database import CreditGrant, DiscordUser, TokenUsageLog, get_session

logger = logging.getLogger(__name__)

router = APIRouter()

# Discord OAuth config
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "932330696956063765")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
OG_NERD_ROLE_ID = "972439407086944266"

# Patreon tier role IDs (configured in Discord server)
PATRON_EXPLORER_ROLE_ID = "1083785196861657198"
PATRON_ARCHAEOLOGIST_ROLE_ID = "1083785565398380544"
PATRON_SCHOLAR_ROLE_ID = "1083785826586075278"

# One-time credit role IDs
TEAM_ROLE_ID = "933104896310378546"
RESEARCHER_ROLE_ID = "933105424264220815"
ADEPTUS_MAJOR_ROLE_ID = "1083087065010417775"
ADEPTUS_MINOR_ROLE_ID = "1083088517510484009"
INITIATE_ROLE_ID = "1083088899494129695"
ADEPT_ROLE_ID = "1083088426074640466"
NEOPHYTE_ROLE_ID = "1083088078379417630"
ANCIENT_NERDS_ROLE_ID = "968574705760100392"

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
}

CREDIT_ROLES[PATRON_EXPLORER_ROLE_ID] = {
    "name": "Patron Explorer",
    "type": "monthly",
    "amount": 5000,
    "cap_multiplier": 1,
    "reason": "monthly_patron_explorer",
}
CREDIT_ROLES[PATRON_ARCHAEOLOGIST_ROLE_ID] = {
    "name": "Patron Archaeologist",
    "type": "monthly",
    "amount": 15000,
    "cap_multiplier": 2,
    "reason": "monthly_patron_archaeologist",
}
CREDIT_ROLES[PATRON_SCHOLAR_ROLE_ID] = {
    "name": "Patron Scholar",
    "type": "monthly",
    "amount": 50000,
    "cap_multiplier": 3,
    "reason": "monthly_patron_scholar",
}

CREDIT_ROLES[TEAM_ROLE_ID] = {
    "name": "Team",
    "type": "one_time",
    "amount": 5000,
    "reason": "team_role",
}
CREDIT_ROLES[RESEARCHER_ROLE_ID] = {
    "name": "Researcher",
    "type": "one_time",
    "amount": 3000,
    "reason": "researcher_role",
}
CREDIT_ROLES[ADEPTUS_MAJOR_ROLE_ID] = {
    "name": "Adeptus Major",
    "type": "one_time",
    "amount": 2000,
    "reason": "adeptus_major_role",
}
CREDIT_ROLES[ADEPTUS_MINOR_ROLE_ID] = {
    "name": "Adeptus Minor",
    "type": "one_time",
    "amount": 1500,
    "reason": "adeptus_minor_role",
}
CREDIT_ROLES[INITIATE_ROLE_ID] = {
    "name": "Initiate",
    "type": "one_time",
    "amount": 1000,
    "reason": "initiate_role",
}
CREDIT_ROLES[ADEPT_ROLE_ID] = {
    "name": "Adept",
    "type": "one_time",
    "amount": 500,
    "reason": "adept_role",
}
CREDIT_ROLES[NEOPHYTE_ROLE_ID] = {
    "name": "Neophyte",
    "type": "one_time",
    "amount": 300,
    "reason": "neophyte_role",
}
CREDIT_ROLES[ANCIENT_NERDS_ROLE_ID] = {
    "name": "Ancient Nerds",
    "type": "one_time",
    "amount": 300,
    "reason": "ancient_nerds_role",
}


def get_user_tier(roles: list[str]) -> str:
    """Return the highest tier name for a user's roles.

    Priority: Patreon tiers first, then Discord-only tiers.
    """
    # Patreon tiers (highest first)
    if PATRON_SCHOLAR_ROLE_ID and PATRON_SCHOLAR_ROLE_ID in roles:
        return "scholar"
    if PATRON_ARCHAEOLOGIST_ROLE_ID and PATRON_ARCHAEOLOGIST_ROLE_ID in roles:
        return "archaeologist"
    if PATRON_EXPLORER_ROLE_ID and PATRON_EXPLORER_ROLE_ID in roles:
        return "explorer"
    # Discord-only tiers
    if FOUNDER_ROLE_ID in roles:
        return "founder"
    if TEAM_ROLE_ID in roles:
        return "team"
    if RESEARCHER_ROLE_ID in roles:
        return "researcher"
    if OG_NERD_ROLE_ID in roles:
        return "og_nerd"
    return "free"


# Simple in-memory CSRF state store (short-lived, cleared on restart is fine)
# Each value is (timestamp, return_to_path)
_oauth_states: dict[str, tuple[float, str]] = {}
_OAUTH_STATE_CAP = 1000

# Rate limit on OAuth redirects: 5 per minute per IP
_oauth_limiter = RateLimiter(max_requests=5, window_seconds=60, namespace="oauth_redirect")

# Rate limit on OAuth callbacks: 10 per minute per IP (prevent token exchange abuse)
_callback_limiter = RateLimiter(max_requests=10, window_seconds=60, namespace="oauth_callback")


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
    Safe to call repeatedly — idempotent via app-level check + row lock on DiscordUser.
    """
    roles = user.roles or []
    now = datetime.now(UTC)

    # Find the highest monthly tier the user holds (skip lower ones to prevent double grants)
    monthly_roles_present = [
        (rid, cfg) for rid, cfg in CREDIT_ROLES.items() if rid in roles and cfg["type"] == "monthly"
    ]
    highest_monthly_role = (
        max(monthly_roles_present, key=lambda x: x[1]["amount"])[0]
        if monthly_roles_present
        else None
    )

    for role_id, config in CREDIT_ROLES.items():
        if role_id not in roles:
            continue

        role_type = config["type"]
        reason = config["reason"]

        if role_type == "one_time":
            # Use sentinel "one_time" instead of NULL so the DB unique constraint
            # (user_id, reason, grant_period) can prevent duplicate grants.
            # PostgreSQL treats NULL != NULL in unique constraints.
            existing = (
                session.query(CreditGrant)
                .filter(
                    CreditGrant.user_id == user.id,
                    CreditGrant.reason == reason,
                    CreditGrant.grant_period == "one_time",
                )
                .first()
            )
            if not existing:
                amount = config["amount"]
                user.credits += amount
                try:
                    session.add(
                        CreditGrant(
                            user_id=user.id,
                            amount=amount,
                            reason=reason,
                            grant_period="one_time",
                        )
                    )
                    session.flush()
                except IntegrityError:
                    logger.info(f"Grant already exists for {user.username} ({reason})")
                    session.rollback()
                    return
                logger.info(f"Granted {amount} credits to {user.username} ({reason})")

        elif role_type == "monthly":
            if role_id != highest_monthly_role:
                continue

            if user.grant_anchor_date is None:
                user.grant_anchor_date = now

            monthly_amount = config["amount"]
            cap_multiplier = config.get("cap_multiplier", 3)
            max_balance = monthly_amount * cap_multiplier

            for period in get_eligible_periods(user.grant_anchor_date, now):
                existing = (
                    session.query(CreditGrant)
                    .filter(
                        CreditGrant.user_id == user.id,
                        CreditGrant.reason == reason,
                        CreditGrant.grant_period == period,
                    )
                    .first()
                )
                if existing:
                    continue

                effective = min(monthly_amount, max(0, max_balance - user.credits))
                if effective <= 0:
                    continue

                user.credits += effective
                try:
                    session.add(
                        CreditGrant(
                            user_id=user.id,
                            amount=effective,
                            reason=reason,
                            grant_period=period,
                        )
                    )
                    session.flush()
                except IntegrityError:
                    logger.info(
                        f"Monthly grant already exists for {user.username} ({reason}, period={period})"
                    )
                    session.rollback()
                    return
                logger.info(
                    f"Granted {effective} monthly credits to {user.username} ({reason}, period={period})"
                )


def _cleanup_states():
    """Remove expired CSRF states (older than 10 minutes)."""
    now = datetime.now(UTC).timestamp()
    expired = [k for k, v in _oauth_states.items() if now - v[0] > 600]
    for k in expired:
        del _oauth_states[k]


@router.get("/discord")
async def discord_oauth_redirect(req: Request, return_to: str | None = None):
    """Redirect user to Discord OAuth2 authorization page."""
    if not DISCORD_CLIENT_ID or not DISCORD_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Discord OAuth not configured")

    client_ip = get_client_ip(req)
    if not _oauth_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    _cleanup_states()

    if len(_oauth_states) >= _OAUTH_STATE_CAP:
        raise HTTPException(status_code=429, detail="Too many pending logins. Try again later.")

    # Sanitize return_to: must be a relative path, no open redirect
    if (
        not return_to
        or not return_to.startswith("/")
        or return_to.startswith("//")
        or return_to.startswith("/\\")
    ):
        return_to = "/account.html"

    state = secrets.token_urlsafe(32)
    _oauth_states[state] = (datetime.now(UTC).timestamp(), return_to)

    from urllib.parse import urlencode

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds.members.read guilds.join",
        "state": state,
        "prompt": "consent",
    }
    url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(url=url)


@router.get("/discord/callback")
async def discord_oauth_callback(
    req: Request, code: str | None = None, state: str | None = None, error: str | None = None
):
    """Handle Discord OAuth2 callback."""
    client_ip = get_client_ip(req)
    if not _callback_limiter.check(client_ip):
        return RedirectResponse(url="/account.html?error=rate_limited")

    if error:
        return RedirectResponse(url="/account.html?error=access_denied")

    if not code or not state:
        return RedirectResponse(url="/account.html?error=missing_params")

    # Validate CSRF state (must exist and be less than 10 minutes old)
    state_entry = _oauth_states.pop(state, None)
    if state_entry is None:
        return RedirectResponse(url="/account.html?error=invalid_state")
    state_ts, return_to = state_entry
    if datetime.now(UTC).timestamp() - state_ts > 600:
        return RedirectResponse(url="/account.html?error=expired_state")

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
            logger.error(
                f"Discord token exchange failed: {token_resp.status_code} {token_resp.text}"
            )
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
            # Not in guild — attempt auto-join via bot token
            if DISCORD_BOT_TOKEN:
                join_resp = await client.put(
                    f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/members/{discord_id}",
                    headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
                    json={"access_token": access_token},
                )
                if join_resp.status_code in (201, 204):
                    logger.info(f"Auto-joined user {username} ({discord_id}) to guild")
                    # Re-fetch member info to get roles
                    member_resp2 = await client.get(
                        f"https://discord.com/api/v10/users/@me/guilds/{DISCORD_GUILD_ID}/member",
                        headers=auth_headers,
                    )
                    if member_resp2.status_code == 200:
                        roles = member_resp2.json().get("roles", [])
                else:
                    logger.warning(f"Auto-join failed for {discord_id}: {join_resp.status_code}")

            # If still not in guild after auto-join attempt, gate login
            if not roles:
                re_check = await client.get(
                    f"https://discord.com/api/v10/users/@me/guilds/{DISCORD_GUILD_ID}/member",
                    headers=auth_headers,
                )
                if re_check.status_code != 200:
                    return RedirectResponse(url="/account.html?error=not_in_guild")

    # Upsert user in database
    with get_session() as session:
        user = (
            session.query(DiscordUser)
            .filter(DiscordUser.discord_id == discord_id)
            .with_for_update()
            .first()
        )
        if user:
            # Detect newly gained patron roles → reset anchor so no backdated credits
            old_roles = set(user.roles or [])
            new_roles = set(roles)
            patron_role_ids = {
                PATRON_EXPLORER_ROLE_ID,
                PATRON_ARCHAEOLOGIST_ROLE_ID,
                PATRON_SCHOLAR_ROLE_ID,
            }
            newly_gained_patron = (new_roles & patron_role_ids) - (old_roles & patron_role_ids)
            if newly_gained_patron:
                user.grant_anchor_date = datetime.now(UTC)

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

        # Check login achievement
        from api.cardgame.achievements import check_achievements

        check_achievements(session, user.id, "login")

        jwt_token = create_token(str(user.id), discord_id)

    response = RedirectResponse(url=return_to)
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
    try:
        # Read credits from DB (grants are applied at login + webhook, not here)
        with get_session() as session:
            db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
            if db_user:
                credits = db_user.credits
                is_unlimited = db_user.is_unlimited
            else:
                credits = user.credits
                is_unlimited = False

        avatar_url = None
        if user.avatar_hash:
            avatar_url = f"https://cdn.discordapp.com/avatars/{user.discord_id}/{user.avatar_hash}.png?size=128"

        roles = user.roles or []
        is_founder = FOUNDER_ROLE_ID in roles
        tier = get_user_tier(roles)

        # Next grant date for monthly tiers
        next_grant_date = None
        if (
            tier in ("explorer", "archaeologist", "scholar")
            and db_user
            and db_user.grant_anchor_date
        ):
            from datetime import timedelta

            anchor = db_user.grant_anchor_date
            now = datetime.now(UTC)
            # Find next anniversary of anchor day
            y, m = now.year, now.month
            anchor_day = anchor.day
            due_day = _clamp_day(y, m, anchor_day)
            next_due = datetime(y, m, due_day, tzinfo=UTC)
            if next_due <= now:
                if m == 12:
                    y += 1
                    m = 1
                else:
                    m += 1
                due_day = _clamp_day(y, m, anchor_day)
                next_due = datetime(y, m, due_day, tzinfo=UTC)
            next_grant_date = next_due.isoformat()

        return {
            "id": str(user.id),
            "discord_id": user.discord_id,
            "username": user.username,
            "avatar_url": avatar_url,
            "roles": roles,
            "credits": credits,
            "is_unlimited": is_unlimited,
            "is_og_nerd": OG_NERD_ROLE_ID in roles,
            "is_founder": is_founder,
            "tier": tier,
            "next_grant_date": next_grant_date,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    except Exception:
        logger.exception("/me failed")
        raise


@router.get("/credits")
async def get_credits(user: DiscordUser = Depends(get_current_user)):
    """Get credits balance and recent usage history."""
    with get_session() as session:
        # Refresh credits from DB (in case it was deducted by another request)
        db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
        credits = db_user.credits if db_user else user.credits
        is_unlimited = db_user.is_unlimited if db_user else False

        # Recent usage (last 20)
        usage = (
            session.query(TokenUsageLog)
            .filter(
                TokenUsageLog.user_id == user.id,
            )
            .order_by(TokenUsageLog.created_at.desc())
            .limit(20)
            .all()
        )

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
        grants = (
            session.query(CreditGrant)
            .filter(
                CreditGrant.user_id == user.id,
            )
            .all()
        )
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
        "is_unlimited": is_unlimited,
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
    action: str  # "set", "add", or "remove"
    amount: int

    @property
    def validated_amount(self) -> int:
        if self.amount < 0:
            raise ValueError("amount must be non-negative")
        return min(self.amount, 10_000_000)


class BulkCreditRequest(BaseModel):
    role_id: str
    amount: int


@router.get("/admin/users")
async def admin_list_users(
    _founder: DiscordUser = Depends(require_founder),
    q: str = Query(default="", max_length=100),
    role: str = Query(default="", max_length=500),
):
    """List users for admin panel. Optional search by username and/or role filter."""
    with get_session() as session:
        query = session.query(DiscordUser)
        if q:
            query = query.filter(DiscordUser.username.ilike(f"%{q}%"))
        if role:
            role_ids = [r.strip() for r in role.split(",") if r.strip()]
            if role_ids:
                from sqlalchemy import cast
                from sqlalchemy.dialects.postgresql import ARRAY, TEXT

                query = query.filter(DiscordUser.roles.op("?|")(cast(role_ids, ARRAY(TEXT))))
        users = query.order_by(DiscordUser.last_login.desc()).limit(100).all()

        return {
            "users": [
                {
                    "id": str(u.id),
                    "username": u.username,
                    "avatar_url": (
                        f"https://cdn.discordapp.com/avatars/{u.discord_id}/{u.avatar_hash}.png?size=64"
                        if u.avatar_hash
                        else None
                    ),
                    "credits": u.credits,
                    "is_unlimited": u.is_unlimited,
                    "is_founder": FOUNDER_ROLE_ID in (u.roles or []),
                    "is_og_nerd": OG_NERD_ROLE_ID in (u.roles or []),
                    "roles": u.roles or [],
                    "last_login": u.last_login.isoformat() if u.last_login else None,
                    "grant_anchor_date": u.grant_anchor_date.isoformat()
                    if u.grant_anchor_date
                    else None,
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
        raise HTTPException(
            status_code=400, detail="action must be 'set', 'add', 'remove', or 'set_unlimited'"
        )
    if body.action in ("set", "add", "remove") and body.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be non-negative")

    with get_session() as session:
        user = (
            session.query(DiscordUser)
            .filter(
                DiscordUser.id == uuid.UUID(body.user_id),
            )
            .with_for_update()
            .first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if body.action == "set_unlimited":
            user.is_unlimited = body.amount != 0
            session.add(
                CreditGrant(
                    user_id=user.id,
                    amount=0,
                    reason="unlimited_set" if user.is_unlimited else "unlimited_removed",
                )
            )
        elif body.action == "set":
            user.credits = body.amount
            session.add(
                CreditGrant(
                    user_id=user.id,
                    amount=body.amount,
                    reason="founder_grant",
                )
            )
        elif body.action == "add":
            user.credits += body.amount
            session.add(
                CreditGrant(
                    user_id=user.id,
                    amount=body.amount,
                    reason="founder_grant",
                )
            )
        elif body.action == "remove":
            user.credits = max(0, user.credits - body.amount)
            session.add(
                CreditGrant(
                    user_id=user.id,
                    amount=-body.amount,
                    reason="founder_grant",
                )
            )

        session.flush()
        new_credits = user.credits
        is_unlimited = user.is_unlimited

    return {"ok": True, "new_credits": new_credits, "is_unlimited": is_unlimited}


@router.get("/admin/users/count-by-role")
async def admin_count_by_role(
    role_id: str = Query(..., max_length=50),
    _founder: DiscordUser = Depends(require_founder),
):
    """Count users that have a specific role. Used for bulk grant preview."""
    with get_session() as session:
        count = (
            session.query(DiscordUser)
            .filter(
                DiscordUser.roles.op("?")(role_id),
            )
            .count()
        )
    return {"count": count}


@router.post("/admin/credits/bulk")
async def admin_bulk_credits(
    body: BulkCreditRequest,
    _founder: DiscordUser = Depends(require_founder),
):
    """Add credits to all users with a specific role."""
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    with get_session() as session:
        users = (
            session.query(DiscordUser)
            .filter(
                DiscordUser.roles.op("?")(body.role_id),
            )
            .with_for_update()
            .all()
        )

        for u in users:
            u.credits += body.amount
            session.add(
                CreditGrant(
                    user_id=u.id,
                    amount=body.amount,
                    reason="bulk_role_grant",
                )
            )

        session.flush()
        affected = len(users)

    return {"ok": True, "affected": affected}
