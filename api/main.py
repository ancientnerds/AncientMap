"""
FastAPI Backend for Ancient Nerds Map.

High-performance API for serving 750K+ archaeological sites
with spatial clustering and viewport filtering.

Updated: BitNet LLM optimized for faster responses
"""

import logging
import mimetypes
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

from loguru import logger as _loguru_logger

_loguru_logger.disable("pipeline.connectors.registry")

from dotenv import load_dotenv

load_dotenv()

import asyncio
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from api.build_info import BUILD_HASH
from api.cache import cache_get, cache_set, get_redis_client
from api.cardgame.routes import router as cardgame_router
from api.routes import (
    app_gate,
    articles_html,
    auth,
    content,
    contributions,
    founders_stats,
    goto,
    interactions,
    landing_html,
    library,
    lyra,
    news,
    og,
    proposals,
    radar,
    research_html,
    sitemap,
    sites,
    sites_html,
    snapshots,
    sources,
    stats_access,
    streetview,
    theo,
    vector_sync,
    wiki_images,
)
from api.routes.public_v1 import create_public_api
from api.services.site_stats import get_site_stats
from api.ssr_client import SsrUnavailableError
from pipeline.config import get_settings

logger = logging.getLogger(__name__)

# Strong references to fire-and-forget startup tasks (Theo worker, Discord bot,
# cache warmers). The event loop keeps only weak references to tasks, so without
# this the daemons can be garbage-collected mid-run.
_background_tasks: set = set()


def _create_background_task(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    import time

    # Startup: verify critical configuration
    from api.services.jwt_auth import verify_secret_key

    verify_secret_key()

    # Startup: ensure new tables exist + warm up connections
    logger.info("Starting Ancient Nerds Map API...")
    try:
        import api.cardgame.models  # noqa: F401 — register Achievement/UserAchievement before create_all
        from pipeline.database import Base, engine

        Base.metadata.create_all(bind=engine)
        from api.boot_schema import run_api_boot_schema

        # The 10-site description_citations seed that stood here (a boot writer the plan's
        # section 10.1 missed) was removed 2026-09-23 (Phase 4, WB-D4): a read-only check that
        # day found all 10 sites carrying the key, so it could only ever have fired against a
        # row a journalled write had just emptied - and the Phase-4 writer never empties it (V12).

        # Run DDL migrations first (fast), then data fixes. The DDL adds what models
        # define but create_all won't add to existing tables; each step asks the
        # catalog first and takes its table lock only when its object is missing
        # (api/boot_schema.py). Each step runs in its own transaction with
        # lock_timeout=5s, so one that does need a lock fails fast on contention
        # (e.g. Lyra orchestrator holding locks on unified_sites) instead of
        # blocking for minutes and racing the health check.
        run_api_boot_schema(engine)
        logger.info(
            "[STARTUP] Database tables verified (includes discord_users, credit_grants, token_usage_logs)"
        )

        # Seed achievement definitions (idempotent upsert)
        from pipeline.database import get_session as _get_session

        with _get_session() as _session:
            from api.cardgame.achievements import seed_achievements

            count = seed_achievements(_session)
            logger.info(f"[STARTUP] Seeded {count} achievement definitions")
    except Exception as e:
        logger.error(f"[STARTUP] Table creation/migration failed: {e}")
        raise

    # Import card descriptions from JSON (idempotent — runs every startup). The
    # file is the authoritative copy of the field and this import is how a
    # committed file reaches an existing row; what it reports when it discards a
    # database value lives in api/services/card_descriptions.py (plan §10.1).
    try:
        from api.services.card_descriptions import (
            import_card_descriptions,
            load_card_descriptions,
        )
        from pipeline.database import get_session

        descriptions = load_card_descriptions()
        if descriptions:
            with get_session() as _s:
                imported = import_card_descriptions(_s, descriptions)
                _s.commit()
                if imported["imported"]:
                    # Flush sites cache so fresh queries include cd
                    from api.cache import cache_delete_pattern as _cdp

                    _cdp("sites:*")
                    logger.info(
                        f"[STARTUP] Imported {imported['imported']} card descriptions (cache flushed)"
                    )
                else:
                    logger.info(
                        f"[STARTUP] Card descriptions already up to date ({imported['checked']} checked)"
                    )
    except Exception as e:
        logger.warning(f"[STARTUP] Card description import failed (non-fatal): {e}")

    # The description import above inserts zeroed placeholder rows (rarity_tier=0)
    # so a description has a row to live on. Every card query filters on
    # rarity_tier, so until the stats are computed those are cards nobody can draw.
    # Off the critical path: on a fresh DB this is thousands of sites (~90s) and
    # would race the startup health check.
    async def _backfill_card_stats() -> None:
        from api.cardgame.generator import backfill_placeholder_stats

        try:
            filled = await asyncio.to_thread(backfill_placeholder_stats)
            if filled:
                logger.info(f"[STARTUP] Computed card stats for {filled} placeholder rows")
        except Exception as e:
            logger.warning(f"[STARTUP] Card stat backfill failed (non-fatal): {e}")

    _create_background_task(_backfill_card_stats())

    # Migrate any existing JSON contributions into unified_sites
    try:
        from api.routes.contributions import load_contributions
        from pipeline.database import get_session

        contributions = load_contributions()
        if contributions:
            with get_session() as session:
                from sqlalchemy import text as sql_text

                migrated = 0
                for c in contributions:
                    cid = c.get("id")
                    if not cid:
                        continue
                    # Skip if already in DB
                    exists = session.execute(
                        sql_text("SELECT 1 FROM unified_sites WHERE id = :id"),
                        {"id": cid},
                    ).fetchone()
                    if exists:
                        continue
                    session.execute(
                        sql_text("""
                        INSERT INTO unified_sites (
                            id, source_id, source_record_id, name, lat, lon,
                            site_type, country, description, source_url, edited_by
                        ) VALUES (
                            :id, 'ancient_nerds_community', :id, :name,
                            :lat, :lon, :site_type, :country, :description,
                            :source_url, 'user'
                        )
                    """),
                        {
                            "id": cid,
                            "name": c.get("name", "Unknown"),
                            "lat": c.get("lat") or 0,
                            "lon": c.get("lon") or 0,
                            "site_type": c.get("site_type"),
                            "country": c.get("country"),
                            "description": c.get("description"),
                            "source_url": c.get("source_url"),
                        },
                    )
                    migrated += 1
                session.commit()
                if migrated:
                    logger.info(
                        f"[STARTUP] Migrated {migrated} JSON contributions to unified_sites"
                    )
    except Exception as e:
        logger.warning(f"[STARTUP] Contribution migration failed (non-fatal): {e}")

    # Start Theo research worker — unless a dedicated worker container owns it.
    # THEO_WORKER_EXTERNAL=1 is set on the api service in docker-compose so a
    # deploy can rebuild the API without killing a 15h research run (the run
    # lives in the theo_worker container, which the deploy skips while busy).
    if os.environ.get("THEO_WORKER_EXTERNAL") == "1":
        logger.info("[STARTUP] Theo worker runs in its own container — not started here")
    else:
        try:
            from api.services.theo_worker import start_worker as _start_theo

            _create_background_task(_start_theo())
            logger.info("[STARTUP] Theo research worker task created")
        except Exception as e:
            logger.warning(f"[STARTUP] Theo worker startup failed (non-fatal): {e}")

    # Start Discord bot (if token is configured)
    try:
        bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
        if bot_token:
            from api.services.discord_bot import start_bot

            _create_background_task(start_bot())
            print("[STARTUP] Discord bot task created", flush=True)
        else:
            print("[STARTUP] DISCORD_BOT_TOKEN not set, skipping bot", flush=True)
    except Exception as e:
        print(f"[STARTUP] Discord bot startup failed (non-fatal): {e}", flush=True)

    # Start nightly vector reindex scheduler
    from api.routes.vector_sync import start_nightly_scheduler

    start_nightly_scheduler()

    get_redis_client()  # Initialize Redis connection

    # Warm up connector status cache in the background (non-blocking), so the
    # health endpoint responds immediately. (A sites pre-warm used to live here: it
    # wrote 50,000 rows under "sites:all:all:all:all:0:50000", a key /api/sites/all
    # has never read - removed 2026-09-22.)
    async def _warm_connector_cache():
        await asyncio.sleep(2)  # Let server finish binding
        try:
            from pipeline.connectors.registry import ConnectorRegistry

            await ConnectorRegistry.check_all_status(timeout=10.0, include_tests=False)
            logger.info("[STARTUP] Connector cache warmed")
        except Exception as e:
            logger.warning(f"[STARTUP] Connector cache warm-up failed (non-fatal): {e}")

    _create_background_task(_warm_connector_cache())

    yield
    # Shutdown
    logger.info("Shutting down...")
    try:
        from api.services.discord_bot import stop_bot

        await stop_bot()
    except Exception as e:
        logger.warning(f"Discord bot shutdown error: {e}")


app = FastAPI(
    title="Ancient Nerds Map API",
    description="High-performance API for 750K+ archaeological sites",
    version="1.1.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log full error server-side; return generic message to clients."""
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}\n{''.join(tb)}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.exception_handler(SsrUnavailableError)
async def ssr_unavailable_handler(request: Request, exc: SsrUnavailableError) -> Response:
    """The SSR sidecar is a hard dependency — its outage is a gateway error, not a 500."""
    logger.error(f"SSR service unavailable on {request.method} {request.url.path}: {exc}")
    return Response(status_code=502, content="Renderer unavailable", media_type="text/plain")


# CORS - allow frontend to connect (configured via API_CORS_ORIGINS env var)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


# Security response headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # DENY: nothing frames these pages — the homepage portals are screenshots
    # (PagePortal.tsx), the iframe version of 2026-09-10 is gone.
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# GZip compression for responses > 500 bytes (reduces JSON payload 3-5x)
app.add_middleware(GZipMiddleware, minimum_size=500)

# SEO: HTML pages for crawlers (no /api/ prefix — served via nginx proxy)
app.include_router(articles_html.router, tags=["articles-html"])
app.include_router(research_html.router, tags=["research-html"])
app.include_router(sites_html.router, tags=["sites-html"])
app.include_router(landing_html.router, tags=["landing-html"])
# Funnel measurement: /goto/discord logs the click and 302s to the invite
# (no /api/ prefix — nginx proxies the exact path)
app.include_router(goto.router, tags=["goto"])

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(stats_access.router, prefix="/api/auth", tags=["stats-access"])
app.include_router(founders_stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(sites.router, prefix="/api/sites", tags=["sites"])
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(app_gate.router, prefix="/api/app", tags=["app"])
app.include_router(og.router, prefix="/api/og", tags=["og"])
app.include_router(contributions.router, prefix="/api/contributions", tags=["contributions"])
app.include_router(lyra.router, prefix="/api/lyra", tags=["lyra"])
app.include_router(sitemap.router, prefix="/api/sitemap", tags=["sitemap"])
app.include_router(streetview.router, prefix="/api/streetview", tags=["streetview"])
app.include_router(content.router, prefix="/api/content", tags=["content"])
app.include_router(news.router, prefix="/api/news", tags=["news"])
app.include_router(radar.router, prefix="/api/radar", tags=["radar"])
app.include_router(proposals.router, prefix="/api/proposals", tags=["proposals"])
app.mount("/api/v1", create_public_api())
app.include_router(snapshots.router, prefix="/api/snapshots", tags=["snapshots"])
app.include_router(vector_sync.router, prefix="/api/vector-sync", tags=["vector-sync"])
app.include_router(wiki_images.router, prefix="/api/wiki-images", tags=["wiki-images"])

app.include_router(interactions.router, prefix="/api/interactions", tags=["interactions"])
app.include_router(library.router, prefix="/api/library", tags=["library"])
app.include_router(cardgame_router, prefix="/api/cards", tags=["cards"])
app.include_router(theo.router, prefix="/api/theo", tags=["theo"])

# Python's mimetypes table has no webp entry on this base image, so StaticFiles
# labelled every hero as application/octet-stream. Verified in the container:
# mimetypes.guess_type("a.webp") -> (None, None). Must run before the mounts.
mimetypes.add_type("image/webp", ".webp")

# Serve wiki images as static files
_wiki_images_dir = Path("public/data/images/wiki")
_wiki_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/data/images/wiki", StaticFiles(directory=str(_wiki_images_dir)), name="wiki-images")

# LEGACY mount — new screenshot URLs use /data/news/screenshots/ (nginx serves
# public/data/news/ directly; robots.txt disallows /api/). This mount stays
# because /api/news/screenshots/ og:image URLs are cached at Google/Discord.
_screenshots_dir = Path("public/data/news/screenshots")
_screenshots_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/api/news/screenshots", StaticFiles(directory=str(_screenshots_dir)), name="news-screenshots"
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "commit": BUILD_HASH,
        "service": "Ancient Nerds Map API",
    }


@app.get("/api/stats")
async def stats():
    """Get database statistics (cached for 5 minutes)."""
    return get_site_stats()
