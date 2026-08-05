"""
API routes for Theodore Furcade — async archaeological research agent.

Endpoints:
  POST   /theo/research             — Submit a new research request
  GET    /theo/research             — List user's requests (last 24h)
  GET    /theo/research/{id}        — Get single request with full report
  GET    /theo/research/{id}/stream — SSE stream for live progress
  DELETE /theo/research/{id}        — Delete a request (queued/completed/failed)
  POST   /theo/research/{id}/publish   — Publish to public library
  POST   /theo/research/{id}/unpublish — Remove from public library
  POST   /theo/research/{id}/generate-audio — Queue TTS audio generation
  GET    /theo/research/{id}/tts-status    — Check TTS status (authed)
  GET    /theo/public/{slug}/tts-status   — Check TTS status (public, for frontend)
  GET    /theo/public/{slug}        — Read a single public paper
  POST   /theo/check-duplicates     — Find similar public papers
  GET    /theo/me                   — User profile with fresh Discord roles
"""

import asyncio
import ipaddress
import json
import logging
import os
import re
import socket
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.services.jwt_auth import get_current_user, get_optional_user, require_researcher
from api.services.rate_limiter import RateLimiter, get_client_ip
from api.services.theo_config import (
    MAX_REQUESTS_PER_USER,
    THEO_RESEARCH_COST,
    THEO_RESEARCHER_ROLE_ID,
)
from api.services.theo_worker import get_live_events, release_reservation_in_session
from pipeline.database import DiscordUser, ResearchRequest, TtsRequest, get_session

DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "932330696956063765")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

logger = logging.getLogger(__name__)
router = APIRouter()
_theo_limiter = RateLimiter(max_requests=5, window_seconds=300, namespace="theo_research")


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RelevanceCheckRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=4000)


class ResearchSubmitRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=4000)
    force_include: list[str] = Field(default_factory=list)
    force_exclude: list[str] = Field(default_factory=list)
    video_ids: list[str] = Field(default_factory=list, max_length=5)
    web_urls: list[str] = Field(default_factory=list, max_length=10)
    disabled_adapters: list[str] = Field(default_factory=list)


class ResearchSubmitResponse(BaseModel):
    id: str
    status: str
    position: int
    estimated_minutes: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_uuid(request_id: str) -> None:
    """Validate that request_id is a valid UUID. Raises 404 if not."""
    try:
        uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Research request not found") from None


def _get_user_id(req: Request) -> str:
    """Get user identifier — Discord ID if logged in, IP otherwise."""
    user = get_optional_user(req)
    if user:
        return user.discord_id
    return get_client_ip(req)


class DuplicateCheckRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=4000)


def _estimate_minutes(queue_position: int) -> int:
    """Rough estimate based on queue position. V2 convergence runs vary widely."""
    return 30 * max(queue_position, 1)


def _make_slug(title: str) -> str:
    """Generate a URL-friendly slug from a paper title."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:250]


def _validate_web_urls(web_urls: list[str]) -> None:
    """SSRF gate for user-supplied web_urls (audit 2026-08-05).

    These URLs are fetched server-side by the research pipeline, so they
    must never be able to reach internal services. Each URL must parse as
    http(s) with a hostname, and EVERY address the hostname resolves to
    must be globally routable — private, loopback, link-local, and other
    reserved ranges (everything `ipaddress` does not consider global) are
    rejected. A hostname that does not resolve is rejected too: a URL we
    cannot resolve is a URL we cannot vouch for.

    Raises HTTP 422 naming the offending URL. Blocking DNS resolution —
    call via `asyncio.to_thread` from async routes.
    """
    for url in web_urls:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid web_url (must be http(s) with a hostname): {url}",
            )
        try:
            infos = socket.getaddrinfo(parsed.hostname, None)
        except socket.gaierror:
            raise HTTPException(
                status_code=422,
                detail=f"Unresolvable hostname in web_url: {url}",
            ) from None
        for info in infos:
            addr = ipaddress.ip_address(info[4][0])
            if not addr.is_global:
                raise HTTPException(
                    status_code=422,
                    detail=f"web_url resolves to a non-public address: {url}",
                )


async def _refresh_roles(user: DiscordUser) -> list[str]:
    """Refresh a user's Discord roles via bot API. Returns fresh roles list."""
    fresh_roles = user.roles or []
    if DISCORD_BOT_TOKEN and user.discord_id:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://discord.com/api/v10/guilds/{DISCORD_GUILD_ID}/members/{user.discord_id}",
                headers={"Authorization": f"Bot {DISCORD_BOT_TOKEN}"},
                timeout=5.0,
            )
        if resp.status_code == 200:
            fresh_roles = resp.json().get("roles", fresh_roles)
            with get_session() as session:
                db_user = session.query(DiscordUser).filter(DiscordUser.id == user.id).first()
                if db_user:
                    db_user.roles = fresh_roles
                    session.commit()
        else:
            logger.warning(
                "Discord role refresh failed for %s: %s",
                user.discord_id,
                resp.status_code,
            )
    return fresh_roles


# ---------------------------------------------------------------------------
# GET /theo/me — Current user's Theo profile with fresh roles
# ---------------------------------------------------------------------------


@router.get("/me")
async def theo_me(user: DiscordUser = Depends(get_current_user)):
    """Return the user's Theo profile and refresh their Discord roles from the bot."""
    fresh_roles = await _refresh_roles(user)

    avatar_url = None
    if user.avatar_hash:
        avatar_url = (
            f"https://cdn.discordapp.com/avatars/{user.discord_id}/{user.avatar_hash}.png?size=128"
        )

    return {
        "username": user.username,
        "discord_id": user.discord_id,
        "avatar_url": avatar_url,
        "has_researcher_role": bool(
            THEO_RESEARCHER_ROLE_ID and THEO_RESEARCHER_ROLE_ID in fresh_roles
        ),
    }


# ---------------------------------------------------------------------------
# POST /theo/check-relevance — Quick relevancy gate (no DB, no queue)
# ---------------------------------------------------------------------------


@router.post("/check-relevance")
async def check_relevance(body: RelevanceCheckRequest, req: Request):
    """Run the relevancy gate standalone — fast M2.7 call, ~2-3 seconds."""
    if not _theo_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")

    from pipeline.lyra.relevance_gate import check_relevance as gate_check

    rejection = await gate_check(body.question)
    if rejection:
        return {"relevant": False, "reason": rejection}
    return {"relevant": True, "reason": ""}


# ---------------------------------------------------------------------------
# GET /theo/adapters — Available source adapters for Sources stage
# ---------------------------------------------------------------------------


@router.get("/adapters")
async def list_adapters():
    """Return available source adapters with their names and descriptions."""
    _icons = "/images/adapters"
    adapter_info: dict[str, dict[str, str]] = {
        "ancientnerds_db": {
            "label": "AncientNerds Database",
            "icon": "",
            "favicon": "",
            "group": "internal",
        },
        "ancientnerds_research": {
            "label": "Public Research Papers",
            "icon": "",
            "favicon": "",
            "group": "internal",
        },
        "youtube_transcripts": {
            "label": "YouTube Transcripts",
            "icon": "",
            "favicon": f"{_icons}/youtube.png",
            "group": "internal",
        },
        "semantic_scholar": {
            "label": "Semantic Scholar",
            "icon": "",
            "favicon": f"{_icons}/semantic-scholar.png",
            "group": "academic",
        },
        "openalex": {
            "label": "OpenAlex",
            "icon": "",
            "favicon": f"{_icons}/openalex.png",
            "group": "academic",
        },
        "crossref": {
            "label": "Crossref",
            "icon": "",
            "favicon": f"{_icons}/crossref.png",
            "group": "academic",
        },
        "core": {
            "label": "CORE",
            "icon": "",
            "favicon": f"{_icons}/core.png",
            "group": "academic",
        },
        "europeana": {
            "label": "Europeana",
            "icon": "",
            "favicon": f"{_icons}/europeana.png",
            "group": "heritage",
        },
        "smithsonian": {
            "label": "Smithsonian",
            "icon": "",
            "favicon": f"{_icons}/smithsonian.png",
            "group": "heritage",
        },
        # National Archives — declassified/archival U.S. government primary
        # sources (Catalog API v2, tier 1). Missing from this registry was a
        # kill-switch gap: the adapter ran in full/exhaustive searches with
        # no way to disable it from Stage 2's Source Adapter toggles.
        "nara": {
            "label": "National Archives",
            "icon": "",
            "favicon": f"{_icons}/nara.png",
            "group": "heritage",
        },
        "wikipedia": {
            "label": "Wikipedia",
            "icon": "",
            "favicon": f"{_icons}/wikipedia.png",
            "group": "web",
        },
        "internet_archive": {
            "label": "Internet Archive",
            "icon": "",
            "favicon": f"{_icons}/internet-archive.png",
            "group": "web",
        },
        "minimax": {
            "label": "Web Search",
            "icon": "",
            "favicon": f"{_icons}/minimax.png",
            "group": "web",
        },
    }
    return adapter_info


# ---------------------------------------------------------------------------
# GET /theo/specialists — Specialist pool for manual selection UI
# ---------------------------------------------------------------------------


@router.get("/specialists")
async def list_specialists():
    """Return the specialist pool for the frontend selection UI."""
    from pipeline.lyra.theo_specialists import SPECIALIST_POOL

    categories: dict[str, list[dict]] = {
        "Archaeological Core": [],
        "Interdisciplinary Science": [],
        "Fringe / Alternative": [],
    }
    science_ids = {
        "geologist",
        "paleoclimatologist",
        "ancient_dna_specialist",
        "archaeometallurgist",
        "volcanologist",
        "physicist",
        "archaeochemist",
        "paleoanthropologist",
        "structural_engineer",
        "historical_linguist",
        "architect",
    }
    fringe_ids = {
        "alternative_history_researcher",
        "comparative_mythologist",
        "esoteric_traditions_scholar",
        "anomalous_phenomena_analyst",
    }

    for s in SPECIALIST_POOL:
        entry = {
            "id": s.id,
            "name": s.name,
            "title": s.title,
            "domain": s.domain,
            "perspective": s.perspective[:120],
        }
        if s.id in fringe_ids:
            categories["Fringe / Alternative"].append(entry)
        elif s.id in science_ids:
            categories["Interdisciplinary Science"].append(entry)
        else:
            categories["Archaeological Core"].append(entry)

    return categories


# ---------------------------------------------------------------------------
# POST /theo/research — Submit new research request
# ---------------------------------------------------------------------------


@router.post("/research", response_model=ResearchSubmitResponse)
async def submit_research(
    body: ResearchSubmitRequest,
    req: Request,
    user: DiscordUser = Depends(get_current_user),
):
    """Submit a new research question for Theo to investigate."""
    if not _theo_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")

    # SSRF gate BEFORE any credit reservation — a rejected URL must not
    # leave a reservation behind. DNS resolution runs in a thread.
    if body.web_urls:
        await asyncio.to_thread(_validate_web_urls, body.web_urls)

    credit_cost = THEO_RESEARCH_COST

    # Check user's active request count + atomic credit reservation
    with get_session() as session:
        count = session.execute(
            text("""
                SELECT COUNT(*) FROM research_requests
                WHERE user_id = :uid AND status IN ('queued', 'running')
            """),
            {"uid": user.discord_id},
        ).scalar()

        if count >= MAX_REQUESTS_PER_USER:
            raise HTTPException(
                status_code=429,
                detail=f"Max {MAX_REQUESTS_PER_USER} concurrent requests per user",
            )

        # Atomic credit reservation — single UPDATE, no race condition
        result = session.execute(
            text("""
                UPDATE discord_users
                SET reserved_credits = reserved_credits + :cost
                WHERE discord_id = :uid
                  AND is_unlimited = FALSE
                  AND credits - reserved_credits >= :cost
                RETURNING credits - reserved_credits - :cost AS remaining
            """),
            {"uid": user.discord_id, "cost": credit_cost},
        )
        reserved = result.fetchone()
        if reserved is None:
            # Check if user is unlimited
            is_unlimited = session.execute(
                text("SELECT is_unlimited FROM discord_users WHERE discord_id = :uid"),
                {"uid": user.discord_id},
            ).scalar()
            if not is_unlimited:
                user_credits = (
                    session.execute(
                        text(
                            "SELECT credits - reserved_credits FROM discord_users WHERE discord_id = :uid"
                        ),
                        {"uid": user.discord_id},
                    ).scalar()
                    or 0
                )
                raise HTTPException(
                    status_code=402,
                    detail=f"Not enough credits. Research costs {credit_cost} credits, you have {user_credits} available.",
                )

        # Build specialist options JSON (only if non-empty)
        spec_opts = None
        if (
            body.force_include
            or body.force_exclude
            or body.video_ids
            or body.web_urls
            or body.disabled_adapters
        ):
            spec_opts = json.dumps(
                {
                    "force_include": body.force_include,
                    "force_exclude": body.force_exclude,
                    "video_ids": body.video_ids,
                    "web_urls": body.web_urls,
                    "disabled_adapters": body.disabled_adapters,
                }
            )

        # Insert new request. effort is a legacy V1 column still NOT NULL in
        # prod — always write 'research' so submits don't 500. The column can
        # be dropped once we migrate historical rows.
        request_id = str(uuid.uuid4())
        session.execute(
            text("""
                INSERT INTO research_requests
                    (id, user_id, question, effort, status, specialist_options, created_at)
                VALUES (:id, :uid, :q, 'research', 'queued', :spec_opts, NOW())
            """),
            {
                "id": request_id,
                "uid": user.discord_id,
                "q": body.question,
                "spec_opts": spec_opts,
            },
        )
        session.commit()

        # Award research submission achievements
        try:
            from api.cardgame.achievements import check_achievements

            check_achievements(session, user.id, "research_submit")
        except Exception:
            # Non-critical — achievements must never break the submission,
            # but the failure has to be visible in the logs.
            logger.warning("check_achievements failed", exc_info=True)

        # Get queue position
        position = session.execute(
            text("""
                SELECT COUNT(*) FROM research_requests
                WHERE status IN ('queued', 'running') AND created_at <= (
                    SELECT created_at FROM research_requests WHERE id = :id
                )
            """),
            {"id": request_id},
        ).scalar()

    return ResearchSubmitResponse(
        id=request_id,
        status="queued",
        position=position or 1,
        estimated_minutes=_estimate_minutes(position or 1),
    )


# ---------------------------------------------------------------------------
# GET /theo/research — List user's requests
# ---------------------------------------------------------------------------


@router.get("/research")
async def list_research(req: Request):
    """List the current user's research requests."""
    user_id = _get_user_id(req)

    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT id::text, question, status, sites_found, tools_used,
                       duration_ms, error_message, is_public, approved_by, created_at, completed_at
                FROM research_requests
                WHERE user_id = :uid
                ORDER BY created_at DESC
                -- 200, not 50: the ENTITÄT batch alone is 52 rows with
                -- created_at seconds apart — LIMIT 50 silently dropped the
                -- two OLDEST (= first-completed) papers from the UI.
                LIMIT 200
            """),
            {"uid": user_id},
        ).fetchall()

    return [
        {
            "id": r.id,
            "question": r.question,
            "status": r.status,
            "sites_found": r.sites_found,
            "tools_used": r.tools_used,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "is_public": r.is_public,
            "approved_by": r.approved_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /theo/research/quota — MiniMax Token Plan remaining (UI header)
# ---------------------------------------------------------------------------


@router.get("/research/quota")
async def get_quota():
    """MiniMax Token Plan remaining quota + limiter state. Public endpoint
    (no auth) so the theo.html UI header can show "Quota: 2.3M/9.7M tokens
    remaining" without forcing a login. The probe is cached 60s on the
    server side. See plan 2026-06-28-theo-rate-limit-defense.md Layer 2."""
    from pipeline.lyra.minimax_limiter import limiter
    from pipeline.lyra.minimax_shared import probe_minimax_quota

    # Sync httpx call (60s server-side cache) — run in a thread so a slow
    # MiniMax endpoint cannot block the event loop.
    quota = await asyncio.to_thread(probe_minimax_quota)
    return {
        "quota": quota,
        "limiter": limiter.stats,
    }


# ---------------------------------------------------------------------------
# GET /theo/research/health — watchdog tier + combined system state
# ---------------------------------------------------------------------------
# NOTE: this route MUST be declared before GET /research/{request_id} below.
# FastAPI matches in declaration order; if the parametric route came first
# it would catch "health" as a request_id and 422. Same trap as
# /research/quota above.


@router.get("/research/health")
async def get_health():
    """Quota watchdog tier + quota + limiter state in one shot.

    Public endpoint (no auth, no rate-limiter — same policy as
    /research/quota) so operator dashboards and the theo.html UI can
    surface "system is healthy / degraded / quota exhausted" without
    needing a login. The watchdog runs in the background on a 60s probe
    cycle; this endpoint just snapshots the latest state.

    Returns the tier that drives the poll-loop gate in theo_worker:
    - HEALTHY  (>30%): full speed ahead
    - DEGRADED (5-30%): work proceeds, log warning
    - EXHAUSTED (<=5%): limiter frozen, poll loop sleeping 60s
    - UNKNOWN: probe failed, watchdog has no opinion yet

    See plan 2026-06-28-theo-rate-limit-defense.md and the watchdog
    implementation in api/services/theo_quota_monitor.py.
    """
    from api.services.theo_quota_monitor import get_watchdog_state

    return get_watchdog_state()


# ---------------------------------------------------------------------------
# GET /theo/research/current — Public live view of the permanent researcher
# ---------------------------------------------------------------------------


@router.get("/research/current")
async def get_current_research():
    """What the permanent researcher is working on right now. Public — no
    auth (same policy as /research/health): the Theo page and the Knowledge
    section show live research to logged-out visitors. Never exposes report
    content — only the question and progress counters, which the running
    row flushes every ~30s.

    Registered BEFORE /research/{request_id} so the literal path wins.
    """
    from api.cache import cache_get, cache_set

    cache_key = "theo:current"
    cached = cache_get(cache_key)
    if cached:
        return cached

    with get_session() as session:
        running_row = session.execute(
            text("""
                SELECT question, started_at, sites_found, llm_calls, total_tokens
                FROM research_requests
                WHERE status = 'running' AND is_batch = TRUE
                ORDER BY started_at DESC
                LIMIT 1
            """)
        ).fetchone()
        queued_batch = (
            session.execute(
                text("""
                    SELECT COUNT(*) FROM research_requests
                    WHERE is_batch = TRUE AND status IN ('queued', 'deferred')
                """)
            ).scalar()
            or 0
        )
        last_pub = session.execute(
            text("""
                SELECT result_json::jsonb->>'title' AS title, slug
                FROM research_requests
                WHERE is_public = TRUE AND status = 'completed'
                ORDER BY published_at DESC
                LIMIT 1
            """)
        ).fetchone()

    running = None
    if running_row:
        elapsed_s = None
        if running_row.started_at:
            elapsed_s = int(
                (datetime.now(UTC) - running_row.started_at.replace(tzinfo=UTC)).total_seconds()
            )
        running = {
            "question": running_row.question,
            "started_at": running_row.started_at.isoformat() if running_row.started_at else None,
            "elapsed_s": elapsed_s,
            "sites_found": running_row.sites_found or 0,
            "llm_calls": running_row.llm_calls or 0,
            "total_tokens": running_row.total_tokens or 0,
        }

    response = {
        "running": running,
        "queued_batch": queued_batch,
        "last_published": {"title": last_pub.title, "slug": last_pub.slug} if last_pub else None,
    }
    cache_set(cache_key, response, ttl=30)
    return response


# ---------------------------------------------------------------------------
# GET /theo/research/{id} — Get full request with report
# ---------------------------------------------------------------------------


@router.get("/research/{request_id}")
async def get_research(request_id: str, req: Request):
    """Get a single research request including the full report."""
    _validate_uuid(request_id)
    user_id = _get_user_id(req)

    with get_session() as session:
        row = session.execute(
            text("""
                SELECT id::text, user_id, question, status, result_json,
                       pipeline_trace, debug_log, sites_found, tools_used, total_tokens,
                       llm_calls, duration_ms, error_message, created_at, completed_at
                FROM research_requests
                WHERE id = :id
            """),
            {"id": request_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Research request not found")
    if row.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your research request")

    try:
        result = json.loads(row.result_json) if row.result_json else None
    except (json.JSONDecodeError, TypeError):
        result = None

    return {
        "id": row.id,
        "question": row.question,
        "status": row.status,
        "result": result,
        "pipeline_trace": row.pipeline_trace,
        "sites_found": row.sites_found,
        "tools_used": row.tools_used,
        "total_tokens": row.total_tokens,
        "llm_calls": row.llm_calls or 0,
        "duration_ms": row.duration_ms,
        "error_message": row.error_message,
        "debug_log": row.debug_log,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


# ---------------------------------------------------------------------------
# GET /theo/research/{id}/blocks — Per-section approval block list
# ---------------------------------------------------------------------------


@router.get("/research/{request_id}/blocks")
async def get_research_blocks(
    request_id: str,
    user: DiscordUser = Depends(get_current_user),
):
    """Return the canonical per-section block list for the approval editor.

    Owner-only. Splits `result_json.report` into individually-reviewable
    blocks (paragraph, heading, list, blockquote, table, code, figure, mosaic,
    plus the hero image as a `hero` block). Each block comes back with its
    current approval state (pending / approved / rejected / edited) merged
    from `result_json.section_approvals.decisions`.

    The server is authoritative — the frontend renders the approval UI from
    this list rather than re-parsing client-side, so there's no split-brain
    risk between client and server on "what is a block."
    """
    from api.services.theo_blocks import build_block_list_response

    _validate_uuid(request_id)

    with get_session() as session:
        row = session.execute(
            text(
                "SELECT user_id, status, is_public, result_json "
                "FROM research_requests WHERE id = :id"
            ),
            {"id": request_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Research request not found")
    if row.user_id != user.discord_id:
        raise HTTPException(status_code=403, detail="Not your research request")
    if row.status != "completed":
        raise HTTPException(status_code=409, detail="Research must be completed")

    try:
        result = json.loads(row.result_json) if row.result_json else {}
    except (json.JSONDecodeError, TypeError):
        result = {}

    report = result.get("report") or ""
    if not report:
        return {"version": 0, "blocks": []}

    return build_block_list_response(
        report=report,
        section_approvals=result.get("section_approvals"),
        hero_image=result.get("hero_image"),
    )


# ---------------------------------------------------------------------------
# PATCH /theo/research/{id}/section — Approve / reject / edit one block
# ---------------------------------------------------------------------------


class SectionDecisionRequest(BaseModel):
    block_id: str = Field(..., min_length=1, max_length=64)
    state: str = Field(..., pattern="^(approved|rejected|edited)$")
    expected_version: int = Field(..., ge=0)
    content: str | None = Field(default=None, max_length=100000)


@router.patch("/research/{request_id}/section")
async def patch_research_section(
    request_id: str,
    body: SectionDecisionRequest,
    user: DiscordUser = Depends(get_current_user),
):
    """Record one block-level approval decision.

    Owner-only. Requires `status == completed` and `is_public == false`.
    Uses `expected_version` for optimistic concurrency — if two tabs try to
    decide on the same paper at the same time, the second one 409s and gets
    the fresh block list back on retry.

    `state == "edited"` is accepted syntactically but not yet implemented —
    the citation re-audit path lands in Slice 3.
    """
    from api.services.theo_blocks import (
        apply_block_edit,
        build_block_list_response,
        find_block_by_id,
        renumber_and_audit_report,
        split_paper_into_blocks,
        upsert_decision,
    )

    _validate_uuid(request_id)

    if body.state == "edited" and not body.content:
        raise HTTPException(
            status_code=422, detail="state=edited requires `content` in the request body"
        )

    with get_session() as session:
        row = session.execute(
            text(
                "SELECT user_id, status, is_public, result_json "
                "FROM research_requests WHERE id = :id"
            ),
            {"id": request_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Research request not found")
        if row.user_id != user.discord_id:
            raise HTTPException(status_code=403, detail="Not your research request")
        if row.status != "completed":
            raise HTTPException(status_code=409, detail="Research must be completed")
        if row.is_public:
            raise HTTPException(status_code=409, detail="Cannot edit a published paper")

        try:
            result = json.loads(row.result_json) if row.result_json else {}
        except (json.JSONDecodeError, TypeError):
            result = {}

        report = result.get("report") or ""
        if not report:
            raise HTTPException(status_code=409, detail="Paper has no report body")

        current_approvals = result.get("section_approvals") or {}
        current_version = int(current_approvals.get("version") or 0)
        if body.expected_version != current_version:
            raise HTTPException(
                status_code=409,
                detail=f"Stale version {body.expected_version}; current is {current_version}",
            )

        block_meta = find_block_by_id(report, result.get("hero_image"), body.block_id)
        if not block_meta:
            raise HTTPException(
                status_code=404,
                detail=f"Block '{body.block_id}' not found in current paper",
            )

        effective_report = report
        edited_content = None

        if body.state == "edited":
            if body.block_id == "hero":
                # Hero caption edit — rewrite result.hero_image.caption, don't
                # touch the report body. Hero block's content_hash stays "hero".
                hero = dict(result.get("hero_image") or {})
                hero["caption"] = body.content or ""
                result["hero_image"] = hero
                edited_content = body.content
            else:
                spliced = apply_block_edit(report, body.block_id, body.content or "")
                if spliced is None:
                    raise HTTPException(
                        status_code=404, detail="Block disappeared before edit could apply"
                    )
                effective_report, audit = renumber_and_audit_report(spliced)
                result["report"] = effective_report
                result["audit"] = audit
                result["edited_at"] = datetime.now(UTC).isoformat()
                edited_content = body.content

                # The renumber pipeline may have rewritten the block's citation
                # markers, giving it a new content_hash. Re-locate by position
                # so the decision carries forward with the post-audit hash.
                new_blocks = split_paper_into_blocks(effective_report)
                target_pos = block_meta["position"]
                relocated = next(
                    (
                        b
                        for b in new_blocks
                        if b.position["segment_idx"] == target_pos["segment_idx"]
                        and b.position["block_idx"] == target_pos["block_idx"]
                    ),
                    None,
                )
                if relocated:
                    block_meta = relocated.to_dict()

        new_approvals = upsert_decision(
            section_approvals=current_approvals,
            block_meta=block_meta,
            state=body.state,
            decided_by=user.username,
            decided_at=datetime.now(UTC).isoformat(),
            edited_content=edited_content,
        )
        result["section_approvals"] = new_approvals

        # Optimistic concurrency enforced IN the UPDATE (audit 2026-08-05):
        # the Python version check above is only a fast path — two
        # concurrent PATCHes could both pass it (TOCTOU). The WHERE clause
        # re-checks the STORED approvals version (absent = 0, matching the
        # Python-side default); rowcount 0 means another writer won.
        updated = session.execute(
            text("""
                UPDATE research_requests
                SET result_json = :result
                WHERE id = :id
                  AND COALESCE((result_json::jsonb->'section_approvals'->>'version')::int, 0)
                      = :expected_version
            """),
            {
                "id": request_id,
                "result": json.dumps(result),
                "expected_version": body.expected_version,
            },
        )
        if updated.rowcount == 0:
            fresh_version = session.execute(
                text(
                    "SELECT COALESCE((result_json::jsonb->'section_approvals'->>'version')::int, 0)"
                    " FROM research_requests WHERE id = :id"
                ),
                {"id": request_id},
            ).scalar()
            raise HTTPException(
                status_code=409,
                detail=f"Stale version {body.expected_version}; current is {fresh_version}",
            )
        session.commit()

    return build_block_list_response(
        report=effective_report,
        section_approvals=new_approvals,
        hero_image=result.get("hero_image"),
    )


# ---------------------------------------------------------------------------
# GET /theo/research/{id}/log — Download debug log
# ---------------------------------------------------------------------------


@router.get("/research/{request_id}/log")
async def get_research_log(request_id: str, req: Request, format: str = "json"):
    """Download the structured debug log for a research request."""
    _validate_uuid(request_id)
    user_id = _get_user_id(req)

    with get_session() as session:
        row = session.execute(
            text("SELECT user_id, debug_log, question FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Research request not found")
    if row.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your research request")

    debug_log = row.debug_log or []

    if format == "md":
        lines = ["# Research Debug Log\n", f"**Question:** {row.question[:200]}\n"]
        for entry in debug_log:
            ts = entry.get("ts", "")[:19]
            level = entry.get("level", "info").upper()
            stage = entry.get("stage", "")
            msg = entry.get("msg", "")
            icon = {"INFO": "o", "WARN": "!", "ERROR": "x"}.get(level, "o")
            lines.append(f"- `{ts}` [{stage}] ({icon}) {msg}")
            data = entry.get("data", {})
            if data:
                for k, v in data.items():
                    lines.append(f"  - {k}: `{v}`")
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse("\n".join(lines), media_type="text/markdown")

    return {"debug_log": debug_log}


# ---------------------------------------------------------------------------
# GET /theo/research/{id}/stream — SSE for live progress
# ---------------------------------------------------------------------------


@router.get("/research/{request_id}/stream")
async def stream_research(request_id: str, req: Request):
    """SSE stream for live progress updates while a request is processing."""
    _validate_uuid(request_id)
    user_id = _get_user_id(req)

    # Verify ownership
    with get_session() as session:
        row = session.execute(
            text("SELECT user_id, status FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your request")

    # If already completed, return a single done event
    if row.status in ("completed", "failed", "cancelled"):

        async def _done_gen():
            yield f"event: done\ndata: {json.dumps({'type': 'done', 'status': row.status})}\n\n"

        return StreamingResponse(
            _done_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def _stream_gen():
        """Stream live events, polling the event buffer."""
        cursor = 0
        idle_count = 0
        max_idle = 300  # 5 minutes of no events → close

        while idle_count < max_idle:
            events = get_live_events(request_id)
            if cursor < len(events):
                new_events = events[cursor:]
                for evt in new_events:
                    event_type = evt.get("type", "progress")
                    yield f"event: {event_type}\ndata: {json.dumps(evt)}\n\n"
                cursor = len(events)
                idle_count = 0

                # Close immediately on terminal event
                if new_events and new_events[-1].get("type") in ("done", "error"):
                    return
            else:
                idle_count += 1

            await asyncio.sleep(1)

        yield f"event: timeout\ndata: {json.dumps({'type': 'timeout'})}\n\n"

    return StreamingResponse(
        _stream_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# DELETE /theo/research/{id} — Delete/cancel a request
# ---------------------------------------------------------------------------


@router.delete("/research/{request_id}")
async def delete_research(request_id: str, req: Request):
    """Delete a research request. Queued → cancel. Completed/failed → delete. Running → error."""
    _validate_uuid(request_id)
    user_id = _get_user_id(req)

    with get_session() as session:
        row = session.execute(
            text("SELECT user_id, status, is_public FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if row.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not your request")

        if row.status in ("queued", "running"):
            # Cancel — pipeline checks for this between stages
            session.execute(
                text("UPDATE research_requests SET status = 'cancelled' WHERE id = :id"),
                {"id": request_id},
            )
            if row.status == "queued":
                # A queued row is never claimed by the worker, so no worker
                # path would ever release the credit reservation made at
                # submission — it would leak forever. Release it here, in
                # the SAME transaction as the status flip. Running rows are
                # released by the worker's cancelled-terminal path.
                release_reservation_in_session(session, row.user_id)
        else:
            # completed, failed, cancelled — actually delete
            session.execute(
                text("DELETE FROM research_requests WHERE id = :id"),
                {"id": request_id},
            )
        session.commit()

    # Clean up Qdrant if it was public
    if row.is_public:
        try:
            from pipeline.lyra.theo_research_index import delete_paper

            delete_paper(request_id)
        except Exception as exc:
            logger.warning("Qdrant cleanup failed for %s: %s", request_id, exc)

    # Clean up downloaded probative images for this paper
    try:
        import shutil
        from pathlib import Path

        images_dir = (
            Path(__file__).parent.parent.parent / "public" / "data" / "research-images" / request_id
        )
        if images_dir.exists() and images_dir.is_dir():
            shutil.rmtree(images_dir)
    except Exception as exc:
        logger.warning("Image cleanup failed for %s: %s", request_id, exc)

    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# POST /theo/research/{id}/approve — Human review approval
# ---------------------------------------------------------------------------


@router.post("/research/{request_id}/approve")
async def approve_research(
    request_id: str,
    user: DiscordUser = Depends(get_current_user),
):
    """Approve a research paper after human review.

    Stores approved_by (username) and approved_at (ISO timestamp)
    in result_json. Required before publishing.
    """
    _validate_uuid(request_id)

    with get_session() as session:
        row = session.execute(
            text("SELECT user_id, status, result_json FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if row.user_id != user.discord_id:
            raise HTTPException(status_code=403, detail="Not your request")
        if row.status != "completed":
            raise HTTPException(status_code=409, detail="Only completed research can be approved")

        try:
            result = json.loads(row.result_json) if row.result_json else {}
        except (json.JSONDecodeError, TypeError):
            result = {}

        result["approved_by"] = user.username
        result["approved_at"] = datetime.now(UTC).isoformat()

        session.execute(
            text("UPDATE research_requests SET result_json = :result WHERE id = :id"),
            {"id": request_id, "result": json.dumps(result)},
        )
        session.commit()

    return {
        "status": "approved",
        "approved_by": user.username,
        "approved_at": result["approved_at"],
    }


# ---------------------------------------------------------------------------
# POST /theo/research/{id}/publish — Publish to public library
# ---------------------------------------------------------------------------


@router.post("/research/{request_id}/publish")
async def publish_research(
    request_id: str,
    user: DiscordUser = Depends(get_current_user),
    dry_run: int = Query(default=0, ge=0, le=1),
    override: int = Query(default=0, ge=0, le=1),
    repair: int = Query(default=0, ge=0, le=1),
    x_theo_override_reason: str | None = Header(default=None, alias="X-Theo-Override-Reason"),
):
    """Publish a completed research paper to the public library.

    If `result_json.section_approvals` is present, every non-references block
    (plus the hero image when present) must have a decision — otherwise 409.
    The assembled paper skips rejected blocks, substitutes edited content for
    edited blocks, and leaves the References section verbatim.

    Legacy papers without section_approvals fall back to the single
    `approved_by` gate.

    Additionally gates on the judge's `quality_score.passed` — `?override=1`
    with a non-empty `X-Theo-Override-Reason` header bypasses this gate and
    logs the decision. Citation integrity is recomputed on the assembled
    artifact and is NOT override-able; `?repair=1` applies the deterministic
    citation repair before re-checking.

    `?dry_run=1` returns the would-be `published_report` / `published_hero_image`
    without writing, so the reviewer can diff before first publish.
    """
    from api.services.theo_blocks import compute_published_paper

    _validate_uuid(request_id)

    # Refresh roles from Discord and verify Researcher role
    fresh_roles = await _refresh_roles(user)
    if not THEO_RESEARCHER_ROLE_ID or THEO_RESEARCHER_ROLE_ID not in fresh_roles:
        raise HTTPException(status_code=403, detail="Researcher role required to publish")

    with get_session() as session:
        row = session.execute(
            text("""
                SELECT id::text, user_id, status, is_public, result_json, question
                FROM research_requests WHERE id = :id
            """),
            {"id": request_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if row.user_id != user.discord_id:
            raise HTTPException(status_code=403, detail="Not your request")
        if row.status != "completed":
            raise HTTPException(status_code=409, detail="Only completed research can be published")
        if row.is_public and not dry_run:
            raise HTTPException(status_code=409, detail="Already published")

        try:
            result = json.loads(row.result_json) if row.result_json else {}
        except (json.JSONDecodeError, TypeError):
            result = {}

        # Quality gate — the judge score is override-able; citation integrity
        # is NOT (it is recomputed on the artifact below, after assembly —
        # the stored audit can be stale and is informational only).
        quality_score = result.get("quality_score") or {}
        quality_passed = bool(quality_score.get("passed"))
        if not quality_passed:
            override_reason = (x_theo_override_reason or "").strip()
            if not (override and override_reason):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "quality_gate_failed",
                        "quality_passed": quality_passed,
                        "failing_metrics": ["quality_score.passed"],
                        "hint": (
                            "Pass ?override=1 with a non-empty X-Theo-Override-Reason "
                            "header to publish anyway."
                        ),
                    },
                )
            logger.warning(
                "Theo publish override: request_id=%s user=%s quality_passed=%s reason=%r",
                request_id,
                user.username,
                quality_passed,
                override_reason,
            )

        section_approvals = result.get("section_approvals")
        report = result.get("report") or ""
        hero_image = result.get("hero_image")

        # Publish gate.
        if section_approvals and section_approvals.get("decisions"):
            # Block-level workflow: every non-references block + hero must have a decision.
            assembled = compute_published_paper(report, hero_image, section_approvals)
            if assembled["pending_block_ids"]:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"{len(assembled['pending_block_ids'])} block(s) still pending "
                        "review; decide on every block before publishing"
                    ),
                )
        else:
            # Legacy workflow: single `approved_by` flag.
            if not result.get("approved_by"):
                raise HTTPException(
                    status_code=409,
                    detail="Paper must be reviewed and approved before publishing",
                )
            assembled = {
                "published_report": report,
                "published_block_ids": [],
                "published_hero_image": hero_image,
                "pending_block_ids": [],
            }

        # Citation-integrity gate — recomputed on the EXACT text being
        # published. Block-level rejections can orphan refs, and the stored
        # audit may predate later mutations. `?repair=1` applies the
        # deterministic repair (never fabricates or remaps a citation).
        from pipeline.lyra.theo_citations import repair_artifact, validate_paper_artifact

        publish_text = assembled["published_report"]
        artifact_report = validate_paper_artifact(publish_text)
        if not artifact_report["passed"] and repair:
            repaired_text, repaired_report = repair_artifact(publish_text)
            if repaired_report["passed"]:
                assembled["published_report"] = repaired_text
                artifact_report = repaired_report
        if not artifact_report["passed"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "citation_integrity_failed",
                    "issues": (artifact_report.get("issues") or [])[:10],
                    "hint": (
                        "Pass ?repair=1 to apply the deterministic citation repair, "
                        "or run scripts/repair_theo_citations.py. Override cannot "
                        "bypass this gate."
                    ),
                },
            )
        result["audit"] = artifact_report

        paper_title = result.get("title", row.question)
        slug = _make_slug(paper_title)
        existing = session.execute(
            text("SELECT id FROM research_requests WHERE slug = :slug AND id != :id"),
            {"slug": slug, "id": request_id},
        ).fetchone()
        if existing:
            slug = f"{slug}-{request_id[:8]}"

        if dry_run:
            return {
                "status": "dry_run",
                "slug": slug,
                "published_report": assembled["published_report"],
                "published_block_ids": assembled["published_block_ids"],
                "published_hero_image": assembled["published_hero_image"],
            }

        # Persist the assembled view alongside the original so legacy fallback
        # keeps working and edits can resume unchanged.
        result["published_report"] = assembled["published_report"]
        result["published_block_ids"] = assembled["published_block_ids"]
        result["published_hero_image"] = assembled["published_hero_image"]

        session.execute(
            text("""
                UPDATE research_requests
                SET is_public = TRUE,
                    published_at = NOW(),
                    published_by = :username,
                    slug = :slug,
                    result_json = :result
                WHERE id = :id
            """),
            {
                "id": request_id,
                "username": user.username,
                "slug": slug,
                "result": json.dumps(result),
            },
        )
        session.commit()

        try:
            from api.cardgame.achievements import check_achievements

            check_achievements(session, user.id, "research_publish")
        except Exception:
            # Non-critical — achievements must never break publishing.
            logger.warning("check_achievements failed", exc_info=True)

    # Index the assembled publication (not the raw report) so search results
    # don't return rejected content.
    paper_text = assembled["published_report"] or result.get("report", "")
    if paper_text:
        try:
            from pipeline.lyra.theo_research_index import index_paper

            indexed = index_paper(
                paper_id=request_id,
                paper_text=paper_text,
                paper_title=paper_title,
                paper_slug=slug,
                author_username=user.username,
                author_discord_id=user.discord_id,
                published_at=datetime.now(UTC).isoformat(),
            )
            logger.info("Published %s: %d sections indexed", request_id, indexed)
        except Exception as exc:
            logger.error("Qdrant indexing failed for %s: %s", request_id, exc)

    return {"status": "published", "slug": slug}


# ---------------------------------------------------------------------------
# POST /theo/research/{id}/unpublish — Remove from public library
# ---------------------------------------------------------------------------


@router.post("/research/{request_id}/unpublish")
async def unpublish_research(
    request_id: str,
    user: DiscordUser = Depends(get_current_user),
):
    """Remove a paper from the public library (keeps the private result)."""
    _validate_uuid(request_id)

    with get_session() as session:
        row = session.execute(
            text("SELECT user_id, is_public FROM research_requests WHERE id = :id"),
            {"id": request_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        if row.user_id != user.discord_id:
            raise HTTPException(status_code=403, detail="Not your request")
        if not row.is_public:
            raise HTTPException(status_code=409, detail="Not currently published")

        session.execute(
            text("""
                UPDATE research_requests
                SET is_public = FALSE, published_at = NULL, slug = NULL
                WHERE id = :id
            """),
            {"id": request_id},
        )
        session.commit()

    # Remove from Qdrant
    try:
        from pipeline.lyra.theo_research_index import delete_paper

        delete_paper(request_id)
    except Exception as exc:
        logger.warning("Qdrant cleanup on unpublish failed for %s: %s", request_id, exc)

    return {"status": "unpublished"}


# ---------------------------------------------------------------------------
# PATCH /theo/research/{id} — Edit report text (owner-only, not-public)
# ---------------------------------------------------------------------------


class EditReportRequest(BaseModel):
    report: str = Field(..., min_length=10, max_length=100000)


@router.patch("/research/{request_id}")
async def edit_research(
    request_id: str,
    body: EditReportRequest,
    user: DiscordUser = Depends(get_current_user),
):
    """Edit the report text of a completed research paper. Must be unpublished."""
    _validate_uuid(request_id)

    with get_session() as session:
        row = session.execute(
            text(
                "SELECT user_id, status, is_public, result_json "
                "FROM research_requests WHERE id = :id"
            ),
            {"id": request_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Research request not found")
        if row.user_id != user.discord_id:
            raise HTTPException(status_code=403, detail="Not your research request")
        if row.status != "completed":
            raise HTTPException(status_code=409, detail="Only completed research can be edited")
        if row.is_public:
            raise HTTPException(
                status_code=409, detail="Cannot edit a published paper — unpublish first"
            )
        # Load existing result, update report field
        try:
            result = json.loads(row.result_json) if row.result_json else {}
        except (json.JSONDecodeError, TypeError):
            result = {}

        from api.services.theo_blocks import renumber_and_audit_report

        rebuilt, audit = renumber_and_audit_report(body.report)
        result["report"] = rebuilt
        result["audit"] = audit
        result["edited_at"] = datetime.now(UTC).isoformat()

        session.execute(
            text("UPDATE research_requests SET result_json = :result WHERE id = :id"),
            {"id": request_id, "result": json.dumps(result)},
        )
        session.commit()

        # Award citation achievements if citations were added/edited
        if result.get("audit", {}).get("total_citations", 0) > 0:
            try:
                from api.cardgame.achievements import check_achievements

                check_achievements(session, user.id, "research_citation")
            except Exception:
                # Non-critical — achievements must never break the edit flow.
                logger.warning("check_achievements failed", exc_info=True)

    return {"status": "updated", "result": result}


# ---------------------------------------------------------------------------
# GET /theo/public — Browse public research papers
# ---------------------------------------------------------------------------


@router.get("/public")
async def list_public_research(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
):
    """List published research papers. No auth required."""
    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT r.id::text, r.question, r.slug, r.published_by, r.published_at,
                       r.sites_found, r.tools_used, r.duration_ms,
                       r.result_json::jsonb->>'title' AS paper_title,
                       r.result_json::jsonb->>'card_description' AS card_description,
                       r.result_json::jsonb->'hero_image'->>'src' AS hero_src,
                       u.discord_id AS author_discord_id,
                       u.avatar_hash AS author_avatar_hash
                FROM research_requests r
                LEFT JOIN discord_users u ON u.discord_id = r.user_id
                WHERE r.is_public = TRUE AND r.status = 'completed'
                ORDER BY r.published_at DESC
                OFFSET :offset LIMIT :limit
            """),
            {"offset": offset, "limit": limit},
        ).fetchall()

        total = session.execute(
            text(
                "SELECT COUNT(*) FROM research_requests WHERE is_public = TRUE AND status = 'completed'"
            )
        ).scalar()

    papers = []
    for r in rows:
        # Hero banner is picked from inline probative images at convergence time
        # (see pipeline.lyra.hero_picker). Older papers without a hero_image
        # entry surface as an empty cover_url — the card CSS handles that.
        cover_url = r.hero_src or ""
        author_avatar = None
        if r.author_avatar_hash and r.author_discord_id:
            author_avatar = (
                f"https://cdn.discordapp.com/avatars/"
                f"{r.author_discord_id}/{r.author_avatar_hash}.png?size=64"
            )

        papers.append(
            {
                "id": r.id,
                "title": r.paper_title or r.question,
                "question": r.question,
                "slug": r.slug,
                "published_by": r.published_by,
                "author_avatar": author_avatar,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "sites_found": r.sites_found,
                "duration_ms": r.duration_ms,
                "card_description": r.card_description or "",
                "cover_url": cover_url,
            }
        )

    return {"papers": papers, "total": total}


# ---------------------------------------------------------------------------
# GET /theo/public/{slug} — Read a single public paper
# ---------------------------------------------------------------------------


@router.get("/public/{slug}")
async def get_public_research(slug: str):
    """Get a single public paper by slug. No auth required."""
    with get_session() as session:
        row = session.execute(
            text("""
                SELECT id::text, question, slug, published_by, published_at,
                       result_json, sites_found, tools_used, duration_ms
                FROM research_requests
                WHERE slug = :slug AND is_public = TRUE AND status = 'completed'
            """),
            {"slug": slug},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Paper not found")

    try:
        result = json.loads(row.result_json) if row.result_json else None
    except (json.JSONDecodeError, TypeError):
        result = None

    # Per-section approval workflow: swap in the assembled publication so the
    # public view renders the reviewed version (rejected blocks hidden, edited
    # content substituted) without the frontend having to know two fields.
    # Legacy papers without `published_report` are unaffected.
    if isinstance(result, dict):
        if result.get("published_report"):
            result = dict(result)
            result["report"] = result["published_report"]
            if "published_hero_image" in result:
                result["hero_image"] = result["published_hero_image"]

    return {
        "id": row.id,
        "question": row.question,
        "slug": row.slug,
        "published_by": row.published_by,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "result": result,
        "sites_found": row.sites_found,
        "tools_used": row.tools_used,
        "duration_ms": row.duration_ms,
    }


# ---------------------------------------------------------------------------
# POST /theo/check-duplicates — Find similar public papers
# ---------------------------------------------------------------------------


@router.post("/check-duplicates")
async def check_duplicates(body: DuplicateCheckRequest, req: Request):
    """Search for public papers similar to a research question."""
    if not _theo_limiter.check(get_client_ip(req)):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")

    try:
        from pipeline.lyra.theo_research_index import search_similar

        matches = search_similar(body.question, limit=5)
    except Exception as exc:
        logger.warning("Duplicate check failed: %s", exc)
        matches = []

    return {"matches": matches}


# ---------------------------------------------------------------------------
# TTS Audio Endpoints
# ---------------------------------------------------------------------------


@router.post("/research/{request_id}/generate-audio")
async def request_audio(
    request_id: str,
    user: DiscordUser = Depends(require_researcher),
):
    """Request TTS audio generation for a published research paper.

    Queues the request in the TtsRequest FIFO table. The orchestrator picks
    it up on the next cycle, generates audio paragraph by paragraph (stripping
    citations), and saves the MP3. Users can poll GET /research/{id}/tts-status
    for progress.
    """
    _validate_uuid(request_id)

    with get_session() as session:
        # Check paper exists, is public, and is completed
        paper = session.query(ResearchRequest).filter(ResearchRequest.id == request_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        if not paper.is_public:
            raise HTTPException(status_code=400, detail="Paper is not published")
        if paper.status != "completed":
            raise HTTPException(status_code=400, detail="Paper is not yet completed")

        # Check for duplicate pending request from same user
        existing = (
            session.query(TtsRequest)
            .filter(
                TtsRequest.paper_id == request_id,
                TtsRequest.user_id == str(user.id),
                TtsRequest.status.in_(["pending", "generating", "no_quota"]),
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409, detail="You already have a pending audio request for this paper"
            )

        # Create queue entry
        tts_req = TtsRequest(
            paper_id=request_id,
            user_id=str(user.id),
            status="pending",
        )
        session.add(tts_req)
        session.commit()

        # Queue position
        queue_position = (
            session.query(TtsRequest)
            .filter(
                TtsRequest.status.in_(["pending", "no_quota"]),
                TtsRequest.requested_at <= tts_req.requested_at,
            )
            .count()
        )

        return {
            "tts_request_id": str(tts_req.id),
            "status": "queued",
            "queue_position": queue_position,
            "message": "Audio generation queued. Check back at GET /theo/research/{id}/tts-status",
        }


@router.get("/research/{request_id}/tts-status")
async def get_tts_status_authed(
    request_id: str,
    user: DiscordUser = Depends(get_current_user),
):
    """Authenticated: check TTS status for a paper the current user requested."""
    _validate_uuid(request_id)

    with get_session() as session:
        tts_req = (
            session.query(TtsRequest)
            .filter(
                TtsRequest.paper_id == request_id,
                TtsRequest.user_id == str(user.id),
            )
            .order_by(TtsRequest.requested_at.desc())
            .first()
        )

        if not tts_req:
            raise HTTPException(status_code=404, detail="No audio request found for this paper")

        queue_position = None
        if tts_req.status in ("pending", "no_quota"):
            queue_position = (
                session.query(TtsRequest)
                .filter(
                    TtsRequest.status.in_(["pending", "no_quota"]),
                    TtsRequest.requested_at <= tts_req.requested_at,
                )
                .count()
            )

        return {
            "tts_request_id": str(tts_req.id),
            "status": tts_req.status,
            "audio_url": tts_req.audio_url,
            "chars_generated": tts_req.chars_generated,
            "queue_position": queue_position,
            "error_message": tts_req.error_message,
            "requested_at": tts_req.requested_at.isoformat() if tts_req.requested_at else None,
        }


@router.get("/public/{slug}/tts-status")
async def get_tts_status_public(slug: str):
    """Public: check TTS status for a paper by slug (no auth required).

    Used by the frontend to show the play button when audio is ready.
    Returns the most recent completed TtsRequest for the paper, if any.
    """
    with get_session() as session:
        paper = (
            session.query(ResearchRequest)
            .filter(
                ResearchRequest.slug == slug,
                ResearchRequest.is_public,
            )
            .first()
        )
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        tts_req = (
            session.query(TtsRequest)
            .filter(
                TtsRequest.paper_id == str(paper.id),
                TtsRequest.status == "done",
            )
            .order_by(TtsRequest.requested_at.desc())
            .first()
        )

        return {
            "has_audio": tts_req is not None,
            "audio_url": tts_req.audio_url if tts_req else None,
            "chars_generated": tts_req.chars_generated if tts_req else None,
            "status": tts_req.status if tts_req else None,
        }
