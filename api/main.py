"""
FastAPI Backend for Ancient Nerds Map.

High-performance API for serving 750K+ archaeological sites
with spatial clustering and viewport filtering.

Updated: BitNet LLM optimized for faster responses
"""

import logging
import os
import subprocess

from dotenv import load_dotenv

load_dotenv()

import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.cache import cache_get, cache_set, get_redis_client
from api.routes import (
    articles_html,
    auth,
    content,
    contributions,
    lyra,
    news,
    og,
    patreon,
    public_v1,
    radar,
    seo,
    sitemap,
    sites,
    snapshots,
    sources,
    streetview,
    vector_sync,
    wiki_images,
)
from pipeline.config import get_settings

logger = logging.getLogger(__name__)


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
        from pipeline.database import Base, engine
        Base.metadata.create_all(bind=engine)
        # Add columns that models define but create_all won't add to existing tables
        with engine.begin() as conn:
            from sqlalchemy import text as _text
            conn.execute(_text("ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS raw_data JSONB"))
            conn.execute(_text("ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS period_end INTEGER"))
        logger.info("[STARTUP] Database tables verified (includes discord_users, credit_grants, token_usage_logs)")
    except Exception as e:
        logger.warning(f"[STARTUP] Table creation check failed: {e}")

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
                    session.execute(sql_text("""
                        INSERT INTO unified_sites (
                            id, source_id, source_record_id, name, lat, lon,
                            site_type, country, description, source_url, edited_by
                        ) VALUES (
                            :id, 'ancient_nerds_community', :id, :name,
                            :lat, :lon, :site_type, :country, :description,
                            :source_url, 'user'
                        )
                    """), {
                        "id": cid,
                        "name": c.get("name", "Unknown"),
                        "lat": c.get("lat") or 0,
                        "lon": c.get("lon") or 0,
                        "site_type": c.get("site_type"),
                        "country": c.get("country"),
                        "description": c.get("description"),
                        "source_url": c.get("source_url"),
                    })
                    migrated += 1
                session.commit()
                if migrated:
                    logger.info(f"[STARTUP] Migrated {migrated} JSON contributions to unified_sites")
    except Exception as e:
        logger.warning(f"[STARTUP] Contribution migration failed (non-fatal): {e}")

    # Start Discord bot (if token is configured)
    try:
        bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
        if bot_token:
            import asyncio

            from api.services.discord_bot import start_bot
            asyncio.create_task(start_bot())
            logger.info("[STARTUP] Discord bot task created")
        else:
            logger.info("[STARTUP] DISCORD_BOT_TOKEN not set, skipping bot")
    except Exception as e:
        logger.warning(f"[STARTUP] Discord bot startup failed (non-fatal): {e}")

    get_redis_client()  # Initialize Redis connection

    # Pre-warm cache with default sites query (so first user gets instant response)
    try:
        cache_key = "sites:all:all:all:all:0:50000"
        if not cache_get(cache_key):
            logger.info("[STARTUP] Pre-warming sites cache...")
            start = time.time()

            from sqlalchemy import text

            from pipeline.database import get_session

            with get_session() as session:
                query = text("""
                    SELECT id::text, name, lat, lon, source_id, site_type,
                           period_start, thumbnail_url, country
                    FROM unified_sites
                    LIMIT 50000
                """)
                result = session.execute(query)
                sites = []
                for row in result:
                    site = {
                        "id": row.id, "n": row.name, "la": row.lat,
                        "lo": row.lon, "s": row.source_id, "t": row.site_type,
                        "p": row.period_start,
                    }
                    if row.thumbnail_url:
                        site["i"] = row.thumbnail_url
                    if row.country:
                        site["c"] = row.country
                    sites.append(site)

                response = {"count": len(sites), "sites": sites}
                cache_set(cache_key, response, ttl=1800)  # 30 minutes
                logger.info(f"[STARTUP] Pre-warmed cache with {len(sites)} sites in {(time.time()-start)*1000:.0f}ms")
        else:
            logger.info("[STARTUP] Sites cache already warm")
    except Exception as e:
        logger.warning(f"[STARTUP] Failed to pre-warm cache: {e}")

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
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log full error server-side; return generic message to clients."""
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}\n{''.join(tb)}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# CORS - allow frontend to connect (configured via API_CORS_ORIGINS env var)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# GZip compression for responses > 500 bytes (reduces JSON payload 3-5x)
app.add_middleware(GZipMiddleware, minimum_size=500)

# SEO: HTML pages for crawlers (no /api/ prefix — served via nginx proxy)
app.include_router(articles_html.router, tags=["articles-html"])
app.include_router(seo.router, tags=["seo"])

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sites.router, prefix="/api/sites", tags=["sites"])
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(og.router, prefix="/api/og", tags=["og"])
app.include_router(contributions.router, prefix="/api/contributions", tags=["contributions"])
app.include_router(lyra.router, prefix="/api/lyra", tags=["lyra"])
app.include_router(sitemap.router, prefix="/api/sitemap", tags=["sitemap"])
app.include_router(streetview.router, prefix="/api/streetview", tags=["streetview"])
app.include_router(content.router, prefix="/api/content", tags=["content"])
app.include_router(news.router, prefix="/api/news", tags=["news"])
app.include_router(radar.router, prefix="/api/radar", tags=["radar"])
app.include_router(public_v1.router, prefix="/api/v1", tags=["Public API"])
app.include_router(snapshots.router, prefix="/api/snapshots", tags=["snapshots"])
app.include_router(vector_sync.router, prefix="/api/vector-sync", tags=["vector-sync"])
app.include_router(wiki_images.router, prefix="/api/wiki-images", tags=["wiki-images"])
app.include_router(patreon.router, prefix="/api/patreon", tags=["patreon"])

# Serve wiki images as static files
_wiki_images_dir = Path("public/data/images/wiki")
_wiki_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/data/images/wiki", StaticFiles(directory=str(_wiki_images_dir)), name="wiki-images")

# Serve news screenshots as static files
_screenshots_dir = Path("public/data/news/screenshots")
_screenshots_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/news/screenshots", StaticFiles(directory=str(_screenshots_dir)), name="news-screenshots")


def _get_build_hash() -> str:
    """Get build hash from env var or git."""
    env_hash = os.environ.get("BUILD_HASH")
    if env_hash:
        return env_hash
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


BUILD_HASH = _get_build_hash()


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.0.0", "commit": BUILD_HASH, "service": "Ancient Nerds Map API"}


@app.get("/api/stats")
async def stats():
    """Get database statistics (cached for 5 minutes)."""
    # Try cache first
    cache_key = "api:stats"
    cached = cache_get(cache_key)
    if cached:
        return cached

    from sqlalchemy import text

    from pipeline.database import get_session

    with get_session() as session:
        # Total sites
        result = session.execute(text("SELECT COUNT(*) FROM unified_sites"))
        total_sites = result.scalar()

        # By source
        result = session.execute(text("""
            SELECT source_id, COUNT(*) as count
            FROM unified_sites
            GROUP BY source_id
            ORDER BY count DESC
        """))
        by_source = {row.source_id: row.count for row in result}

    response = {
        "total_sites": total_sites,
        "by_source": by_source,
    }

    # Cache for 5 minutes
    cache_set(cache_key, response, ttl=300)
    return response
