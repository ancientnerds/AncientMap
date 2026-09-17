# SPDX-License-Identifier: AGPL-3.0-only
"""stats.ancientnerds.com — founder-only access to the Umami dashboard, via Discord.

Umami has no Discord login, so nginx asks this module before it proxies a
single byte on the stats host (`auth_request`). The flow:

1. The browser opens stats.ancientnerds.com. nginx sub-requests
   GET /api/auth/stats-gate with the visitor's cookies. Without a valid
   ``an_stats`` cookie the gate answers 401 and nginx serves
   GET /api/auth/stats-login — the entry page below.
2. "Continue with Discord" starts the ordinary OAuth flow on the main host
   (/api/auth/discord?return_to=/api/auth/stats-handoff), which ends with the
   120 s handoff cookie ``an_auth_token`` (auth.py, discord_callback).
3. GET /api/auth/stats-handoff reads that cookie, looks the user up, requires
   the Founder role (jwt_auth.FOUNDER_ROLE_ID) and mints ``an_stats``: a
   signed HS256 token with scope "stats", twelve hours, for
   Domain=.ancientnerds.com, HttpOnly, Secure, SameSite=Lax. Then it
   redirects to https://stats.ancientnerds.com/. No Founder role → 403 page.
4. nginx lets the request through to Umami. Umami's own login (with its
   optional 2FA) stays as the second lock; the browser remembers it.

Who gets in is therefore exactly the set of Discord accounts carrying the
Founder role — managed on the Discord server, not in this code.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from html import escape
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from api.services import jwt_auth
from pipeline.database import DiscordUser, get_session

logger = logging.getLogger(__name__)
router = APIRouter()

STATS_HOST = "stats.ancientnerds.com"
COOKIE_NAME = "an_stats"
COOKIE_DOMAIN = ".ancientnerds.com"
SESSION_HOURS = 12
HANDOFF_PATH = "/api/auth/stats-handoff"
LOGIN_PATH = "/api/auth/stats-login"
#: Fonts come from the main host: the stats host proxies everything else to Umami.
_FONTS_CSS = "https://ancientnerds.com/fonts/fonts.css"


def mint_stats_token(discord_id: str, username: str, now: datetime | None = None) -> str:
    """The ``an_stats`` value: same key and algorithm as the user JWT, but its
    own scope, so a normal login token can never open the dashboard."""
    if not jwt_auth.SECRET_KEY:
        raise RuntimeError("API_SECRET_KEY not set — refusing to sign tokens with empty secret")
    now = now or datetime.now(UTC)
    payload = {
        "sub": discord_id,
        "name": username,
        "scope": "stats",
        "iat": now,
        "exp": now + timedelta(hours=SESSION_HOURS),
    }
    return jwt.encode(payload, jwt_auth.SECRET_KEY, algorithm=jwt_auth.ALGORITHM)


def stats_session(request: Request) -> dict | None:
    """Payload of a valid ``an_stats`` cookie, else None (missing, expired,
    wrong signature, or a token of another scope)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt_auth.decode_token(token)
    except Exception:
        return None
    return payload if payload.get("scope") == "stats" else None


@router.get("/stats-gate")
async def stats_gate(request: Request) -> Response:
    """nginx auth_request target: 204 lets the request through, 401 does not."""
    if stats_session(request):
        return Response(status_code=204)
    return Response(status_code=401)


@router.get("/stats-login")
async def stats_login(request: Request) -> HTMLResponse:
    """The entry page nginx serves for an unauthenticated stats visitor."""
    denied = request.query_params.get("denied") == "1"
    return HTMLResponse(content=gate_html(denied=denied), status_code=403 if denied else 200)


@router.get("/stats-handoff")
async def stats_handoff(request: Request) -> Response:
    """After the Discord login: turn the 120 s handoff cookie into the stats session."""
    token = request.cookies.get("an_auth_token")
    if not token:
        return RedirectResponse(url=f"/api/auth/discord?return_to={quote(HANDOFF_PATH, safe='')}")
    try:
        payload = jwt_auth.decode_token(token)
    except Exception:
        return RedirectResponse(url=f"/api/auth/discord?return_to={quote(HANDOFF_PATH, safe='')}")
    discord_id = payload.get("sub")
    if not discord_id:
        return RedirectResponse(url=f"/api/auth/discord?return_to={quote(HANDOFF_PATH, safe='')}")

    with get_session() as session:
        user = session.query(DiscordUser).filter(DiscordUser.discord_id == discord_id).first()
        roles = list(user.roles or []) if user else []
        username = user.username if user else ""

    if jwt_auth.FOUNDER_ROLE_ID not in roles:
        logger.warning("stats access denied for discord_id=%s (no Founder role)", discord_id)
        return HTMLResponse(content=gate_html(denied=True), status_code=403)

    response = RedirectResponse(url=f"https://{STATS_HOST}/", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=mint_stats_token(discord_id, username),
        max_age=SESSION_HOURS * 3600,
        domain=COOKIE_DOMAIN,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    logger.info("stats session issued for %s", username)
    return response


@router.get("/stats-logout")
async def stats_logout() -> Response:
    response = RedirectResponse(url=f"https://{STATS_HOST}{LOGIN_PATH}", status_code=302)
    response.delete_cookie(COOKIE_NAME, domain=COOKIE_DOMAIN, path="/")
    return response


_DISCORD_SVG = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.3 4.4A19.8 19.8 0 0 0 15.4 3l-.2.4a18 18 '
    "0 0 1 4.5 2.3 15 15 0 0 0-15.4 0A18 18 0 0 1 8.8 3.4L8.6 3a19.8 19.8 0 0 0-4.9 1.4C.6 9.1-.3 13.7.2 "
    "18.2a19.9 19.9 0 0 0 6 3l1.3-2a12.6 12.6 0 0 1-2-1l.5-.4a14.2 14.2 0 0 0 12 0l.5.4a12.6 12.6 0 0 1-2 "
    "1l1.3 2a19.9 19.9 0 0 0 6-3c.6-5.2-.9-9.8-3.5-13.8ZM8.5 15.4c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 "
    "2.2 1.1 2.1 2.4c0 1.3-.9 2.4-2.1 2.4Zm7 0c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.1 2.4c0 "
    '1.3-.9 2.4-2.1 2.4Z"/></svg>'
)


def gate_html(denied: bool = False) -> str:
    """Mobile-first NERV entry page: wordmark, one action, one status line."""
    login_href = escape(f"/api/auth/discord?return_to={quote(HANDOFF_PATH, safe='')}")
    if denied:
        title = "No Founder role"
        heading = escape(title)
        lead = "This Discord account has no Founder role on the Ancient Nerds server."
        action = f'<a class="btn" href="{login_href}">{_DISCORD_SVG}Try another account</a>'
        status = '<span class="dot dot-red"></span>Access denied'
    else:
        title = "Stats"
        heading = "Site <span>Stats</span>"
        lead = "Visitors, journeys, events. Cookieless, self-hosted, founders only."
        action = f'<a class="btn" href="{login_href}">{_DISCORD_SVG}Continue with Discord</a>'
        status = '<span class="dot"></span>Umami · live'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{escape(title)} · Ancient Nerds</title>
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="https://ancientnerds.com/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{_FONTS_CSS}">
<style>
  :root {{ --red: #bb0a0a; --red-bright: #ff2a2a; --green: #00cc66; --ink: #060604; --paper: #e8e8e0; --muted: #888880; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{
    background: var(--ink); color: var(--paper);
    font-family: 'Inter', system-ui, sans-serif;
    display: grid; place-items: center;
    padding: max(24px, env(safe-area-inset-top)) 20px max(24px, env(safe-area-inset-bottom));
    background-image:
      linear-gradient(rgba(0,204,102,0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(0,204,102,0.06) 1px, transparent 1px);
    background-size: 32px 32px;
  }}
  main {{ width: 100%; max-width: 420px; }}
  .mark {{
    font-family: 'Orbitron', 'Inter', sans-serif; font-weight: 700; letter-spacing: 0.18em;
    font-size: 0.8rem; color: var(--green); text-transform: uppercase; margin-bottom: 28px;
  }}
  .mark b {{ color: var(--paper); font-weight: 700; }}
  h1 {{
    font-family: 'Saira Extra Condensed', 'Orbitron', sans-serif; font-weight: 700;
    font-size: clamp(3.2rem, 18vw, 5.4rem); line-height: 0.9; letter-spacing: 0.02em;
    text-transform: uppercase; color: var(--paper); margin-bottom: 18px;
  }}
  h1 span {{ color: var(--red-bright); }}
  p {{ color: var(--muted); font-size: 1rem; line-height: 1.55; margin-bottom: 32px; max-width: 34ch; }}
  .btn {{
    display: flex; align-items: center; justify-content: center; gap: 12px;
    width: 100%; min-height: 56px; padding: 0 20px;
    background: #000; color: var(--red-bright); text-decoration: none;
    border: 2px solid var(--red); border-radius: 4px;
    font-family: 'JetBrains Mono', monospace; font-size: 0.95rem; font-weight: 500;
    letter-spacing: 0.08em; text-transform: uppercase;
    transition: background 0.15s, color 0.15s;
  }}
  .btn:hover, .btn:focus-visible {{ background: var(--red); color: #000; outline: none; }}
  .btn:active {{ transform: translateY(1px); }}
  .btn svg {{ width: 22px; height: 22px; flex: none; fill: currentColor; }}
  .status {{
    margin-top: 24px; display: flex; align-items: center; gap: 10px;
    font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--muted);
  }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 12px var(--green); animation: pulse 2s ease-in-out infinite; }}
  .dot-red {{ background: var(--red-bright); box-shadow: 0 0 12px var(--red-bright); animation: none; }}
  @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
  footer {{ margin-top: 48px; font-size: 0.75rem; color: var(--muted); }}
  footer a {{ color: var(--green); text-decoration: none; }}
  footer a:hover {{ color: var(--paper); }}
  @media (min-width: 640px) {{ main {{ max-width: 480px; }} .btn {{ width: auto; min-width: 300px; }} }}
  @media (prefers-reduced-motion: reduce) {{ .dot {{ animation: none; }} .btn {{ transition: none; }} }}
</style>
</head>
<body>
<main>
  <div class="mark"><b>Ancient Nerds</b> · Analytics</div>
  <h1>{heading}</h1>
  <p>{escape(lead)}</p>
  {action}
  <div class="status">{status}</div>
  <footer><a href="https://ancientnerds.com/">ancientnerds.com</a> · <a href="https://ancientnerds.com/privacy.html">Privacy</a></footer>
</main>
</body>
</html>"""
