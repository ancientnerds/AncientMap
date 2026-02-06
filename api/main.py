"""
FastAPI Backend for Ancient Nerds Map.

High-performance API for serving 800K+ archaeological sites
with spatial clustering and viewport filtering.

Updated: BitNet LLM optimized for faster responses
"""

import logging
import os
import subprocess

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from api.cache import cache_get, cache_set, get_redis_client
from api.routes import (
    ai,
    content,
    contributions,
    discoveries,
    news,
    og,
    sitemap,
    sites,
    sources,
    streetview,
)
from pipeline.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    import time

    # Startup: warm up database connection pool and Redis
    logger.info("Starting Ancient Nerds Map API...")
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


app = FastAPI(
    title="Ancient Nerds Map API",
    description="High-performance API for 800K+ archaeological sites",
    version="1.0.0",
    lifespan=lifespan,
)

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

# Include routers
app.include_router(sites.router, prefix="/api/sites", tags=["sites"])
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(og.router, prefix="/api/og", tags=["og"])
app.include_router(contributions.router, prefix="/api/contributions", tags=["contributions"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(sitemap.router, prefix="/api/sitemap", tags=["sitemap"])
app.include_router(streetview.router, prefix="/api/streetview", tags=["streetview"])
app.include_router(content.router, prefix="/api/content", tags=["content"])
app.include_router(news.router, prefix="/api/news", tags=["news"])
app.include_router(discoveries.router, prefix="/api/discoveries", tags=["discoveries"])

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
