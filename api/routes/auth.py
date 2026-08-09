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
import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.services import jwt_auth
from api.services.jwt_auth import FOUNDER_ROLE_ID, create_token, get_current_user, require_founder
from api.services.lyra_tools import _escape_ilike
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

# MEE6 Monetize tier role IDs (configured in Discord server + MEE6 dashboard)
MEE6_EXPLORER_ROLE_ID = "1083785196861657198"
MEE6_PATHFINDER_ROLE_ID = "1083785565398380544"
MEE6_SCHOLAR_ROLE_ID = "1083785826586075278"

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

CREDIT_ROLES[MEE6_EXPLORER_ROLE_ID] = {
    "name": "Explorer",
    "type": "monthly",
    "amount": 5000,
    "cap_multiplier": 1,
    "reason": "monthly_patron_explorer",
}
CREDIT_ROLES[MEE6_PATHFINDER_ROLE_ID] = {
    "name": "Pathfinder",
    "type": "monthly",
    "amount": 15000,
    "cap_multiplier": 2,
    "reason": "monthly_patron_archaeologist",
}
CREDIT_ROLES[MEE6_SCHOLAR_ROLE_ID] = {
    "name": "Scholar",
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

    Priority: MEE6 Monetize tiers first, then Discord-only tiers.
    """
    # MEE6 Monetize tiers (highest first)
    if MEE6_SCHOLAR_ROLE_ID in roles:
        return "scholar"
    if MEE6_PATHFINDER_ROLE_ID in roles:
        return "pathfinder"
    if MEE6_EXPLORER_ROLE_ID in roles:
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


# OAuth state is signed with API_SECRET_KEY (HMAC via PyJWT) so it survives
# API restarts. Previously a process-local dict — every deploy wiped pending
# logins and users mid-flow saw "invalid_state". JWT also gives us a built-in
# expiry check via `exp`, so no cleanup task is needed.
_OAUTH_STATE_TTL_SECONDS = 600
_OAUTH_STATE_AUDIENCE = "oauth_state"
# Browser-binding nonce (audit 2026-08-05, M3): the state JWT alone is valid
# in ANY browser — an attacker could complete their own OAuth flow inside a
# victim's session (login CSRF). The redirect sets this cookie; the state
# carries only the SHA-256 of its value; the callback requires both to match.
_OAUTH_NONCE_COOKIE = "an_oauth_nonce"

# Rate limit on OAuth redirects: 15 per minute per IP. Was 5/min, but legitimate
# users retrying after a flaky first attempt routinely tripped it.
_oauth_limiter = RateLimiter(max_requests=15, window_seconds=60, namespace="oauth_redirect")

# Rate limit on OAuth callbacks: 15 per minute per IP (prevent token exchange abuse)
_callback_limiter = RateLimiter(max_requests=15, window_seconds=60, namespace="oauth_callback")

_ALLOWED_RETURN_PATHS = frozenset(
    {
        "/",
        "/account.html",
        "/news.html",
        "/game.html",
        "/index.html",
        "/theo.html",
        "/cards.html",
        "/globe.html",
        "/search.html",
        "/library.html",
        "/knowledge.html",
        "/sites/",
        "/news-archive/",
        "/research/",
        "/articles/",
    }
)

# The indexed pages live under generated paths (/sites/{country}/{slug},
# /news-archive/{slug}, …), so an exact allowlist cannot cover them. Five of
# six tested paths bounced the Discord returner to /account.html.
_ALLOWED_RETURN_PREFIXES = ("/sites/", "/news-archive/", "/research/", "/articles/")


def _is_allowed_return(return_to: object) -> bool:
    """Whether return_to is a safe same-origin path to redirect to.

    Explicit checks, not a sanitiser: anything not recognised is rejected.
    "//evil.com" and "/\\evil.com" are protocol-relative URLs that browsers
    resolve to a different origin, and CR/LF would split the Location header.
    """
    if not isinstance(return_to, str) or not return_to:
        return False
    if return_to in _ALLOWED_RETURN_PATHS:
        return True
    if not return_to.startswith("/") or return_to.startswith("//"):
        return False
    if "\\" in return_to or any(c in return_to for c in "\r\n\t"):
        return False
    lowered = return_to.lower()
    if "%0d" in lowered or "%0a" in lowered:
        return False
    return return_to.startswith(_ALLOWED_RETURN_PREFIXES)


def _create_oauth_state(return_to: str, nonce: str) -> str:
    """Create a signed CSRF state token bound to a browser nonce.

    Stateless — survives API restarts. The state embeds only the nonce's
    SHA-256; the raw nonce lives in an httpOnly cookie, so a state token is
    worthless outside the browser that started the flow.
    """
    if not jwt_auth.SECRET_KEY:
        raise RuntimeError("API_SECRET_KEY not set — cannot sign OAuth state")
    payload = {
        "aud": _OAUTH_STATE_AUDIENCE,
        "rt": return_to,
        "nh": hashlib.sha256(nonce.encode()).hexdigest(),
        "exp": datetime.now(UTC) + timedelta(seconds=_OAUTH_STATE_TTL_SECONDS),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, jwt_auth.SECRET_KEY, algorithm=jwt_auth.ALGORITHM)


def _consume_oauth_state(state: str, nonce_cookie: str | None) -> str | None:
    """Verify a signed state token + browser nonce, return return_to or None.

    Returns None for any failure (expired, tampered, wrong audience,
    return_to not in allowlist, missing/mismatched nonce cookie). A login
    link opened in a DIFFERENT browser than the one that started the flow
    has no nonce cookie and fails here by design — the user simply restarts
    the login. Callers redirect to /account.html?error=... on None.
    """
    if not state or not jwt_auth.SECRET_KEY:
        return None
    try:
        payload = jwt.decode(
            state,
            jwt_auth.SECRET_KEY,
            algorithms=[jwt_auth.ALGORITHM],
            audience=_OAUTH_STATE_AUDIENCE,
        )
    except jwt.PyJWTError:
        return None
    nonce_hash = payload.get("nh")
    if not isinstance(nonce_hash, str) or not nonce_cookie:
        return None
    if not hmac.compare_digest(nonce_hash, hashlib.sha256(nonce_cookie.encode()).hexdigest()):
        return None
    return_to = payload.get("rt")
    if not _is_allowed_return(return_to):
        return None
    return return_to


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


def resolve_monthly_grant_period(
    period: str, anchor: datetime, existing_created_at: list[datetime]
) -> str | None:
    """Decide the grant_period key for a calendar period, or None to skip.

    A grant row for this calendar month may exist from a PREVIOUS
    subscription cycle: cancel + rejoin in the same month resets the anchor,
    and until 2026-08-06 the old row silently swallowed the new cycle's
    grant — a paying rejoiner received nothing until the next calendar month
    (audit finding M4). Rows created before the current anchor belong to an
    earlier cycle; the new cycle's grant gets a ".N"-suffixed period so the
    (user_id, reason, grant_period) unique constraint stays intact and
    legacy rows keep their plain "YYYY-MM" keys.
    """
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    current_cycle = [
        c
        for c in existing_created_at
        if (c.replace(tzinfo=UTC) if c.tzinfo is None else c) >= anchor
    ]
    if current_cycle:
        return None  # this subscription cycle already got the period
    if not existing_created_at:
        return period
    return f"{period}.{len(existing_created_at)}"


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
                    nested = session.begin_nested()
                    session.add(
                        CreditGrant(
                            user_id=user.id,
                            amount=amount,
                            reason=reason,
                            grant_period="one_time",
                        )
                    )
                    session.flush()
                    nested.commit()
                except IntegrityError:
                    logger.info(f"Grant already exists for {user.username} ({reason})")
                    user.credits -= amount  # revert in-memory change
                    continue
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
                same_period = (
                    session.query(CreditGrant)
                    .filter(
                        CreditGrant.user_id == user.id,
                        CreditGrant.reason == reason,
                        CreditGrant.grant_period.like(f"{period}%"),
                    )
                    .all()
                )
                grant_period = resolve_monthly_grant_period(
                    period,
                    user.grant_anchor_date,
                    [g.created_at for g in same_period],
                )
                if grant_period is None:
                    continue

                effective = min(monthly_amount, max(0, max_balance - user.credits))
                if effective <= 0:
                    continue

                user.credits += effective
                try:
                    nested = session.begin_nested()
                    session.add(
                        CreditGrant(
                            user_id=user.id,
                            amount=effective,
                            reason=reason,
                            grant_period=grant_period,
                        )
                    )
                    session.flush()
                    nested.commit()
                except IntegrityError:
                    logger.info(
                        f"Monthly grant already exists for {user.username} "
                        f"({reason}, period={grant_period})"
                    )
                    user.credits -= effective  # revert in-memory change
                    continue
                logger.info(
                    f"Granted {effective} monthly credits to {user.username} "
                    f"({reason}, period={grant_period})"
                )


@router.get("/discord")
async def discord_oauth_redirect(req: Request, return_to: str | None = None):
    """Redirect user to Discord OAuth2 authorization page."""
    if not DISCORD_CLIENT_ID or not DISCORD_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Discord OAuth not configured")

    client_ip = get_client_ip(req)
    if not _oauth_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    # Allowlist return_to to prevent open redirect
    if not _is_allowed_return(return_to):
        return_to = "/account.html"

    nonce = secrets.token_urlsafe(32)
    state = _create_oauth_state(return_to, nonce)

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
    response = RedirectResponse(url=url)
    # samesite="lax" survives the top-level GET redirect back from Discord.
    response.set_cookie(
        key=_OAUTH_NONCE_COOKIE,
        value=nonce,
        max_age=_OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=True,
        path="/",
    )
    return response


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

    # Validate CSRF state + browser nonce. _consume_oauth_state returns None
    # for tampered, expired, unknown-return-to, or nonce-mismatched tokens.
    # The user sees one error code regardless of whether the state was
    # forged, stale, or opened in a different browser.
    return_to = _consume_oauth_state(state, req.cookies.get(_OAUTH_NONCE_COOKIE))
    if return_to is None:
        return RedirectResponse(url="/account.html?error=invalid_state")

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
                # Membership confirmed — take the roles from THIS response.
                # Until 2026-08-06 roles stayed [] here, wiping the stored
                # tier roles; the next login then saw them as "newly gained"
                # and reset grant_anchor_date (audit finding M4 side effect).
                roles = re_check.json().get("roles", [])

    # Upsert user in database
    try:
        with get_session() as session:
            user = (
                session.query(DiscordUser)
                .filter(DiscordUser.discord_id == discord_id)
                .with_for_update()
                .first()
            )
            if user:
                # Detect newly gained tier roles → reset anchor so no backdated credits
                old_roles = set(user.roles or [])
                new_roles = set(roles)
                tier_role_ids = {
                    MEE6_EXPLORER_ROLE_ID,
                    MEE6_PATHFINDER_ROLE_ID,
                    MEE6_SCHOLAR_ROLE_ID,
                }
                newly_gained_tier = (new_roles & tier_role_ids) - (old_roles & tier_role_ids)
                if newly_gained_tier:
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
    except Exception:
        logger.exception(f"Discord callback DB error for {discord_id} ({username})")
        return RedirectResponse(url="/account.html?error=server_error")

    response = RedirectResponse(url=return_to)
    response.set_cookie(
        key="an_auth_token",
        value=jwt_token,
        max_age=120,  # Short-lived: frontend reads it immediately on load
        httponly=False,  # nosemgrep: semgrep.python-cookie-httponly-false -- OAuth handoff cookie, 120s TTL, frontend must read it (CODE_AUDIT.md documented exception)
        samesite="lax",
        secure=True,
        path="/",
    )
    # Single-use: the nonce dies with the completed login, so a captured
    # callback URL cannot be replayed even in this browser.
    response.delete_cookie(_OAUTH_NONCE_COOKIE, path="/")
    return response


@router.get("/me")
async def get_me(user: DiscordUser = Depends(get_current_user)):
    """Get current authenticated user profile."""
    try:
        # Read credits from DB (grants are applied at login + webhook, not here).
        # Capture everything needed while the session is open — attribute access
        # after the with-block raises DetachedInstanceError.
        with get_session() as session:
            db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
            if db_user:
                credits = db_user.credits
                is_unlimited = db_user.is_unlimited
                grant_anchor_date = db_user.grant_anchor_date
            else:
                credits = user.credits
                is_unlimited = False
                grant_anchor_date = None

        avatar_url = None
        if user.avatar_hash:
            avatar_url = f"https://cdn.discordapp.com/avatars/{user.discord_id}/{user.avatar_hash}.png?size=128"

        roles = user.roles or []
        is_founder = FOUNDER_ROLE_ID in roles
        tier = get_user_tier(roles)

        # Next grant date for monthly tiers
        next_grant_date = None
        if tier in ("explorer", "pathfinder", "scholar") and grant_anchor_date:
            anchor = grant_anchor_date
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
                "web_search_requests": u.web_search_requests,
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

    @field_validator("amount")
    @classmethod
    def cap_amount(cls, v: int) -> int:
        return min(v, 10_000_000)


class BulkCreditRequest(BaseModel):
    role_id: str
    amount: int

    @field_validator("amount")
    @classmethod
    def cap_amount(cls, v: int) -> int:
        return min(v, 10_000_000)


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
            q_safe = _escape_ilike(q)
            query = query.filter(DiscordUser.username.ilike(f"%{q_safe}%", escape="\\"))
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

    try:
        target_user_id = uuid.UUID(body.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id") from None

    with get_session() as session:
        user = (
            session.query(DiscordUser)
            .filter(
                DiscordUser.id == target_user_id,
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
                    grant_period=str(int(datetime.now(UTC).timestamp())),
                )
            )
        elif body.action == "set":
            user.credits = body.amount
            session.add(
                CreditGrant(
                    user_id=user.id,
                    amount=body.amount,
                    reason="founder_grant",
                    grant_period=str(int(datetime.now(UTC).timestamp())),
                )
            )
        elif body.action == "add":
            user.credits += body.amount
            session.add(
                CreditGrant(
                    user_id=user.id,
                    amount=body.amount,
                    reason="founder_grant",
                    grant_period=str(int(datetime.now(UTC).timestamp())),
                )
            )
        elif body.action == "remove":
            # Ledger the ACTUAL delta, not the requested amount — the clamp
            # to 0 means removing 500 from a 300-credit balance deducts only
            # 300, and the ledger must reconcile with the balance
            # (audit 2026-08-05).
            old_credits = user.credits
            user.credits = max(0, user.credits - body.amount)
            session.add(
                CreditGrant(
                    user_id=user.id,
                    amount=user.credits - old_credits,
                    reason="founder_grant",
                    grant_period=str(int(datetime.now(UTC).timestamp())),
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
                    grant_period=str(int(datetime.now(UTC).timestamp())),
                )
            )

        session.flush()
        affected = len(users)

    return {"ok": True, "affected": affected}
