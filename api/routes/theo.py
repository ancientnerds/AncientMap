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
  GET    /theo/public               — Browse public research papers
  GET    /theo/public/{slug}        — Read a single public paper
  POST   /theo/check-duplicates     — Find similar public papers
  GET    /theo/me                   — User profile with fresh Discord roles
"""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.services.jwt_auth import get_current_user, get_optional_user
from api.services.rate_limiter import RateLimiter, get_client_ip
from api.services.theo_config import (
    EFFORT_CONFIG,
    MAX_REQUESTS_PER_USER,
    THEO_CREDIT_COSTS,
    THEO_RESEARCHER_ROLE_ID,
)
from api.services.theo_worker import get_live_events
from pipeline.database import DiscordUser, get_session

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
    effort: str = Field(default="article")
    force_include: list[str] = Field(default_factory=list)
    force_exclude: list[str] = Field(default_factory=list)
    video_ids: list[str] = Field(default_factory=list, max_length=5)
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


def _estimate_minutes(effort: str, queue_position: int) -> int:
    """Rough estimate based on effort and queue position."""
    base = {"brief": 3, "note": 8, "article": 20, "review": 40, "thesis": 60}.get(effort, 20)
    return base * max(queue_position, 1)


def _make_slug(title: str) -> str:
    """Generate a URL-friendly slug from a paper title."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:250]


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
    _theo_limiter.check(get_client_ip(req))

    from pipeline.lyra.theo_pipeline import TheoPipeline

    pipeline = TheoPipeline()
    rejection = await pipeline._check_relevance(
        body.question,
        emit=lambda _: None,  # discard SSE events
    )
    if rejection:
        return {"relevant": False, "reason": rejection}
    return {"relevant": True, "reason": ""}


# ---------------------------------------------------------------------------
# POST /theo/enrich-prompt — Expand casual question into structured research prompt
# ---------------------------------------------------------------------------


class EnrichPromptRequest(BaseModel):
    question: str = Field(..., min_length=10, max_length=4000)
    effort: str = Field(default="article")


@router.post("/enrich-prompt")
async def enrich_prompt(body: EnrichPromptRequest, req: Request):
    """Expand a casual question into a structured research prompt."""
    _theo_limiter.check(get_client_ip(req))

    from pipeline.lyra.config import _get_settings
    from pipeline.lyra.minimax_shared import create_minimax_client, minimax_chat

    settings = _get_settings()
    client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)

    effort_label = {
        "brief": "a brief literature overview",
        "note": "a research note with 3 specialists",
        "article": "a journal article with 5 specialists and debate",
        "review": "a comprehensive literature review with 6 specialists",
        "thesis": "a thesis chapter with 8 specialists and multi-round debate",
    }.get(body.effort, "a research paper")

    system = (
        "You are a research prompt engineer for an archaeological research pipeline. "
        "Take the user's casual question and expand it into a clear, structured research prompt "
        "that will produce better academic results. The output is " + effort_label + ".\n\n"
        "Rules:\n"
        "- Preserve the user's original intent and scope\n"
        "- Add specificity: name time periods, regions, key concepts\n"
        "- Frame it as an investigation with clear angles to explore\n"
        "- Mention competing theories or debates if relevant\n"
        "- Keep it under 300 words\n"
        "- Write in third person ('This paper investigates...' not 'I want to know...')\n"
        "- Output ONLY the enriched prompt, no meta-commentary"
    )

    try:
        enriched = await asyncio.to_thread(
            minimax_chat, client, settings.minimax_model, system, body.question, 1024
        )
        client.close()
        return {"enriched": enriched.strip()}
    except Exception as exc:
        logger.warning("Prompt enrichment failed: %s", exc)
        client.close()
        return {"enriched": body.question}


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
        "adna_specialist",
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
async def submit_research(body: ResearchSubmitRequest, req: Request):
    """Submit a new research question for Theo to investigate."""
    _theo_limiter.check(get_client_ip(req))

    if body.effort not in EFFORT_CONFIG:
        raise HTTPException(status_code=400, detail=f"Invalid effort: {body.effort}")

    user_id = _get_user_id(req)
    credit_cost = THEO_CREDIT_COSTS.get(body.effort, 300)

    # Check user's active request count + credit balance
    with get_session() as session:
        count = session.execute(
            text("""
                SELECT COUNT(*) FROM research_requests
                WHERE user_id = :uid AND status IN ('queued', 'running')
            """),
            {"uid": user_id},
        ).scalar()

        if count >= MAX_REQUESTS_PER_USER:
            raise HTTPException(
                status_code=429,
                detail=f"Max {MAX_REQUESTS_PER_USER} concurrent requests per user",
            )

        # Credit check — deduct upfront (refund on failure/cancel)
        user_row = session.execute(
            text("SELECT credits, is_unlimited FROM discord_users WHERE discord_id = :uid"),
            {"uid": user_id},
        ).fetchone()

        if user_row and not user_row.is_unlimited:
            if user_row.credits < credit_cost:
                raise HTTPException(
                    status_code=402,
                    detail=f"Not enough credits. {body.effort.title()} costs {credit_cost} credits, you have {user_row.credits}.",
                )
            session.execute(
                text("UPDATE discord_users SET credits = credits - :cost WHERE discord_id = :uid"),
                {"uid": user_id, "cost": credit_cost},
            )

        # Build specialist options JSON (only if non-empty)
        spec_opts = None
        if body.force_include or body.force_exclude or body.video_ids or body.disabled_adapters:
            spec_opts = json.dumps(
                {
                    "force_include": body.force_include,
                    "force_exclude": body.force_exclude,
                    "video_ids": body.video_ids,
                    "disabled_adapters": body.disabled_adapters,
                }
            )

        # Insert new request
        request_id = str(uuid.uuid4())
        session.execute(
            text("""
                INSERT INTO research_requests
                    (id, user_id, question, effort, status, specialist_options, created_at)
                VALUES (:id, :uid, :q, :effort, 'queued', :spec_opts, NOW())
            """),
            {
                "id": request_id,
                "uid": user_id,
                "q": body.question,
                "effort": body.effort,
                "spec_opts": spec_opts,
            },
        )
        session.commit()

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
        estimated_minutes=_estimate_minutes(body.effort, position or 1),
    )


# ---------------------------------------------------------------------------
# GET /theo/research — List user's requests
# ---------------------------------------------------------------------------


@router.get("/research")
async def list_research(req: Request):
    """List the current user's research requests (last 24h, not expired)."""
    user_id = _get_user_id(req)

    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT id::text, question, effort, status, sites_found, tools_used,
                       duration_ms, error_message, is_public, created_at, completed_at
                FROM research_requests
                WHERE user_id = :uid
                  AND (is_public = TRUE OR expires_at IS NULL OR expires_at > NOW())
                  AND (is_public = TRUE OR created_at > NOW() - INTERVAL '24 hours')
                ORDER BY created_at DESC
                LIMIT 50
            """),
            {"uid": user_id},
        ).fetchall()

    return [
        {
            "id": r.id,
            "question": r.question,
            "effort": r.effort,
            "status": r.status,
            "sites_found": r.sites_found,
            "tools_used": r.tools_used,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "is_public": r.is_public,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in rows
    ]


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
                SELECT id::text, user_id, question, effort, status, result_json,
                       pipeline_trace, sites_found, tools_used, total_tokens,
                       duration_ms, error_message, created_at, completed_at, expires_at
                FROM research_requests
                WHERE id = :id
            """),
            {"id": request_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Research request not found")
    if row.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your research request")
    if row.expires_at and row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Research report expired")

    try:
        result = json.loads(row.result_json) if row.result_json else None
    except (json.JSONDecodeError, TypeError):
        result = None

    return {
        "id": row.id,
        "question": row.question,
        "effort": row.effort,
        "status": row.status,
        "result": result,
        "pipeline_trace": row.pipeline_trace,
        "sites_found": row.sites_found,
        "tools_used": row.tools_used,
        "total_tokens": row.total_tokens,
        "duration_ms": row.duration_ms,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


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
        import asyncio

        cursor = 0
        idle_count = 0
        max_idle = 300  # 5 minutes of no events → close

        while idle_count < max_idle:
            events = get_live_events(request_id)
            if cursor < len(events):
                for evt in events[cursor:]:
                    event_type = evt.get("type", "progress")
                    yield f"event: {event_type}\ndata: {json.dumps(evt)}\n\n"
                cursor = len(events)
                idle_count = 0

                # Check if we've reached a terminal event
                if any(e.get("type") in ("done", "error") for e in events[cursor - 1 :]):
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

    # Clean up generated images
    try:
        from pipeline.lyra.theo_images import delete_paper_images

        delete_paper_images(request_id)
    except Exception as exc:
        logger.warning("Image cleanup failed for %s: %s", request_id, exc)

    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# POST /theo/research/{id}/publish — Publish to public library
# ---------------------------------------------------------------------------


@router.post("/research/{request_id}/publish")
async def publish_research(
    request_id: str,
    user: DiscordUser = Depends(get_current_user),
):
    """Publish a completed research paper to the public library."""
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
        if row.is_public:
            raise HTTPException(status_code=409, detail="Already published")

        # Parse result to get paper title for slug
        try:
            result = json.loads(row.result_json) if row.result_json else {}
        except (json.JSONDecodeError, TypeError):
            result = {}

        paper_title = result.get("title", row.question)
        slug = _make_slug(paper_title)

        # Ensure slug uniqueness by appending short ID if needed
        existing = session.execute(
            text("SELECT id FROM research_requests WHERE slug = :slug AND id != :id"),
            {"slug": slug, "id": request_id},
        ).fetchone()
        if existing:
            slug = f"{slug}-{request_id[:8]}"

        session.execute(
            text("""
                UPDATE research_requests
                SET is_public = TRUE,
                    published_at = NOW(),
                    published_by = :username,
                    slug = :slug,
                    expires_at = NULL
                WHERE id = :id
            """),
            {"id": request_id, "username": user.username, "slug": slug},
        )
        session.commit()

    # Index in Qdrant
    paper_text = result.get("report", "")
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
                effort=row.status,
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
                SELECT r.id::text, r.question, r.effort, r.slug, r.published_by, r.published_at,
                       r.sites_found, r.tools_used, r.duration_ms,
                       r.result_json::jsonb->>'title' AS paper_title,
                       r.result_json::jsonb->>'card_description' AS card_description,
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
        cover_url = f"/data/research-images/{r.id}/cover.png"
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
                "effort": r.effort,
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
                SELECT id::text, question, effort, slug, published_by, published_at,
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

    return {
        "id": row.id,
        "question": row.question,
        "effort": row.effort,
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
    _theo_limiter.check(get_client_ip(req))

    try:
        from pipeline.lyra.theo_research_index import search_similar

        matches = search_similar(body.question, limit=5)
    except Exception as exc:
        logger.warning("Duplicate check failed: %s", exc)
        matches = []

    return {"matches": matches}
