"""
FastAPI Backend for Ancient Nerds Map.

High-performance API for serving 750K+ archaeological sites
with spatial clustering and viewport filtering.

Updated: BitNet LLM optimized for faster responses
"""

import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

from loguru import logger as _loguru_logger

_loguru_logger.disable("pipeline.connectors.registry")

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

from api.build_info import BUILD_HASH
from api.cache import cache_get, cache_set, get_redis_client
from api.cardgame.routes import router as cardgame_router
from api.routes import (
    articles_html,
    auth,
    content,
    contributions,
    interactions,
    lyra,
    news,
    og,
    patreon,
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
from api.routes.public_v1 import create_public_api
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
        import api.cardgame.models  # noqa: F401 — register Achievement/UserAchievement before create_all
        from pipeline.database import Base, engine

        Base.metadata.create_all(bind=engine)
        # Add columns that models define but create_all won't add to existing tables.
        # Note: unified_sites ALTERs live in pipeline/lyra/orchestrator.py migrations
        # to avoid lock contention when both containers start simultaneously.
        from sqlalchemy import text as _text

        _api_migrations = [
            """DO $$ BEGIN
                ALTER TABLE discord_users ADD CONSTRAINT credits_non_negative CHECK (credits >= 0);
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$""",
            "ALTER TABLE expedition_progress ADD COLUMN IF NOT EXISTS last_stage_played_at TIMESTAMP",
            "ALTER TABLE card_player_stats ADD COLUMN IF NOT EXISTS feature_flags JSONB DEFAULT '{}'",
            # Ensure unified_sites columns exist (normally added by orchestrator, but API needs them for /sites/all)
            "ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS edited_by VARCHAR(20) NOT NULL DEFAULT 'initial'",
            "ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
            "ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS last_audited TIMESTAMP",
            # Ensure card_stats enrichment columns exist (model defines them but create_all won't add to existing table)
            "ALTER TABLE card_stats ADD COLUMN IF NOT EXISTS confidence_score FLOAT",
            "ALTER TABLE card_stats ADD COLUMN IF NOT EXISTS source_language VARCHAR(10)",
            "ALTER TABLE card_stats ADD COLUMN IF NOT EXISTS best_wiki_url VARCHAR(500)",
            # Ensure db_snapshots has source_id column (added after initial table creation)
            "ALTER TABLE db_snapshots ADD COLUMN IF NOT EXISTS source_id VARCHAR(50)",
            # Strip orphaned [N] citation markers from sites lacking citation metadata
            "UPDATE unified_sites SET description = regexp_replace(description, '\\s*\\[\\d+\\]', '', 'g') WHERE description ~ '\\[\\d+\\]' AND NOT jsonb_exists(COALESCE(raw_data, '{}'), 'description_citations')",
        ]

        # Populate description_citations for 10 enriched sites (one-time prod data fix).
        # Uses parameterized queries to avoid SQLAlchemy parsing JSON colons as bind params.
        import json as _json

        _citation_seed = {
            "f6b8fa8a-775c-4ee3-babd-1723dc03ba86": [
                {
                    "n": 1,
                    "url": "https://grokipedia.com/page/Abri_de_la_Madeleine",
                    "title": "Abri de la Madeleine - Grokipedia",
                    "domain": "grokipedia.com",
                },
                {
                    "n": 2,
                    "url": "https://donsmaps.com/madeleine.html",
                    "title": "La Madeleine - a rock shelter in the Dordogne",
                    "domain": "donsmaps.com",
                },
                {
                    "n": 3,
                    "url": "https://www.artslookup.com/prehistoric/la-madeleine.html",
                    "title": "La Madeleine: Magdalenian culture Type-Site",
                    "domain": "artslookup.com",
                },
            ],
            "23cb48d4-7ca0-4105-a97e-f60f67537bc9": [
                {
                    "n": 1,
                    "url": "http://hillforts.arch.ox.ac.uk/records/EN3579.html",
                    "title": "Atlas of Hillforts: Abbotsbury Castle",
                    "domain": "hillforts.arch.ox.ac.uk",
                },
                {
                    "n": 2,
                    "url": "https://www.megalithic.co.uk/article.php?sid=4654",
                    "title": "Abbotsbury Castle Hillfort - The Megalithic Portal",
                    "domain": "megalithic.co.uk",
                },
                {
                    "n": 3,
                    "url": "https://www.digitaldigging.net/abbotsbury-castle-hillfort-dorset/",
                    "title": "Abbotsbury Castle Hillfort, Dorset - Digital Digging",
                    "domain": "digitaldigging.net",
                },
            ],
            "d7b8c0a6-0e25-4c12-b63e-1e7abd9af00f": [
                {
                    "n": 1,
                    "url": "https://www.environment.nsw.gov.au/topics/heritage/search-heritage-databases/aboriginal-heritage-information-management-system",
                    "title": "Aboriginal Heritage Information Management System - NSW Environment",
                    "domain": "environment.nsw.gov.au",
                },
                {
                    "n": 2,
                    "url": "https://www.aboriginalheritage.org/sites/identification/",
                    "title": "Identifying Aboriginal Sites - Aboriginal Heritage Office",
                    "domain": "aboriginalheritage.org",
                },
                {
                    "n": 3,
                    "url": "https://intarch.ac.uk/journal/issue52/8/index.html",
                    "title": "Traces in a Lost Landscape - Dyarubbin/Nepean River",
                    "domain": "intarch.ac.uk",
                },
            ],
            "6d3bc9c6-2672-49a9-9934-9f56e37c8fde": [
                {
                    "n": 1,
                    "url": "https://www.heritagegateway.org.uk/Gateway/Results_Single.aspx?uid=237986&resourceID=19191",
                    "title": "Heritage Gateway - Abingdon Causewayed Enclosure",
                    "domain": "heritagegateway.org.uk",
                },
                {
                    "n": 2,
                    "url": "https://archaeologydataservice.ac.uk/library/browse/issue.xhtml?recordId=1075392",
                    "title": "Settlement patterns in the Oxford region - CBA Research Report 44",
                    "domain": "archaeologydataservice.ac.uk",
                },
                {
                    "n": 3,
                    "url": "https://aaahsmap.abingdon.gov.uk/thought-category-period/neolithic/",
                    "title": "Neolithic - Abingdon Map",
                    "domain": "aaahsmap.abingdon.gov.uk",
                },
            ],
            "383a0107-b7f7-4431-a752-590f3c0a42b2": [
                {
                    "n": 1,
                    "url": "https://rijksmonumenten.nl/monument/531042/archeologie/aartswoud/",
                    "title": "Archeologie in Aartswoud - Rijksmonument 531042",
                    "domain": "rijksmonumenten.nl",
                },
                {
                    "n": 2,
                    "url": "https://en.wikipedia.org/wiki/Aartswoud",
                    "title": "Aartswoud - Wikipedia",
                    "domain": "en.wikipedia.org",
                },
            ],
            "74fe5dc2-1e2c-4dd6-b4ed-3cb376c9cd50": [
                {
                    "n": 1,
                    "url": "https://www.roman-britain.co.uk/places/aballava/",
                    "title": "Hadrian's Wall Fort - Burgh-by-Sands (Aballava) - Roman Britain",
                    "domain": "roman-britain.co.uk",
                },
                {
                    "n": 2,
                    "url": "https://www.cumbriacountyhistory.org.uk/first-recorded-african-community-britain-background-burgh-sands",
                    "title": "The first recorded African community in Britain - Cumbria County History Trust",
                    "domain": "cumbriacountyhistory.org.uk",
                },
            ],
            "6cf72484-5b8f-44b0-acfe-fd70ebfa5f26": [
                {
                    "n": 1,
                    "url": "https://heritagemalta.mt/explore/abbatija-tad-dejr/",
                    "title": "Abbatija tad-Dejr Catacombs - Heritage Malta",
                    "domain": "heritagemalta.mt",
                },
                {
                    "n": 2,
                    "url": "https://www.maltatina.com/abbatija-tad-dejr-rabat/",
                    "title": "Abbatija tad-Dejr, Rabat - Maltatina",
                    "domain": "maltatina.com",
                },
                {
                    "n": 3,
                    "url": "https://aroundus.com/p/8569297-abbatija-tad-dejr",
                    "title": "Abbatija Tad-Dejr - AroundUs",
                    "domain": "aroundus.com",
                },
            ],
            "8a091738-3689-48f4-8e8b-565a3197c5d5": [
                {
                    "n": 1,
                    "url": "https://www.andalucia.com/province/almeria/adra/history",
                    "title": "History | Adra | Andalucia.com",
                    "domain": "andalucia.com",
                },
                {
                    "n": 2,
                    "url": "https://liveinalmeria.com/en/adra-village/",
                    "title": "Adra Village - Live in Almeria",
                    "domain": "liveinalmeria.com",
                },
                {
                    "n": 3,
                    "url": "https://www.adra.es/en/web/guest/w/conocenos",
                    "title": "Conocenos - Adra Official Site",
                    "domain": "adra.es",
                },
            ],
            "2753c6bb-1b90-4d49-8e59-b037bf1df930": [
                {
                    "n": 1,
                    "url": "https://www.citedrive.com/en/discovery/geoarchaeological-and-microstratigraphic-view-of-a-neanderthal-settlement-at-rambla-de-ah%C3%ADllas-in-iberian-range-abrigo-de-la-quebrada-chelva-valenc/",
                    "title": "Geoarchaeological view of Abrigo de la Quebrada",
                    "domain": "citedrive.com",
                },
                {
                    "n": 2,
                    "url": "https://www.academia.edu/14960032/",
                    "title": "Neanderthal use of plants at Abrigo de la Quebrada",
                    "domain": "academia.edu",
                },
                {
                    "n": 3,
                    "url": "https://www.academia.edu/14960032/",
                    "title": "Neanderthal use of plants at Abrigo de la Quebrada",
                    "domain": "academia.edu",
                },
                {
                    "n": 4,
                    "url": "https://journals.ed.ac.uk/lithicstudies/article/view/783",
                    "title": "Middle Palaeolithic flint procurement in Central Mediterranean Iberia",
                    "domain": "journals.ed.ac.uk",
                },
            ],
            "09289d39-3f1e-4bac-b14b-931cb421d40d": [
                {
                    "n": 1,
                    "url": "http://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0006:entry%3Dabodiacum",
                    "title": "The Princeton Encyclopedia of Classical Sites: Abodiacum",
                    "domain": "perseus.tufts.edu",
                },
                {
                    "n": 2,
                    "url": "https://klavierzimmer.wordpress.com/2016/05/28/in-via-abodiacum/",
                    "title": "In via: Abodiacum - The Practice Room",
                    "domain": "klavierzimmer.wordpress.com",
                },
                {
                    "n": 3,
                    "url": "https://museen-in-bayern.de/en/museums/museum-details/museum-abodiacum",
                    "title": "Museum Abodiacum - Museen in Bayern",
                    "domain": "museen-in-bayern.de",
                },
            ],
        }
        _cite_sql = _text("""
            UPDATE unified_sites
            SET raw_data = jsonb_set(
                COALESCE(raw_data, cast('{}' as jsonb)),
                '{description_citations}',
                cast(:dc as jsonb)
            )
            WHERE id = :id
              AND NOT jsonb_exists(COALESCE(raw_data, cast('{}' as jsonb)), 'description_citations')
        """)
        # Run DDL migrations first (fast), then data fixes
        for _sql in _api_migrations:
            with engine.begin() as conn:
                conn.execute(_text("SET statement_timeout = '30s'"))
                conn.execute(_text(_sql))
        for _sid, _dc in _citation_seed.items():
            with engine.begin() as conn:
                conn.execute(_text("SET statement_timeout = '30s'"))
                conn.execute(_cite_sql, {"id": _sid, "dc": _json.dumps(_dc)})
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

    # Import card descriptions from JSON (idempotent — runs every startup)
    try:
        from pipeline.database import get_session

        desc_path = Path("public/data/card_descriptions.json")
        if desc_path.exists():
            import json as _json

            with open(desc_path, encoding="utf-8") as _f:
                _desc_data = _json.load(_f)
            descriptions = _desc_data.get("descriptions", {})
            if descriptions:
                from sqlalchemy import text as _t

                with get_session() as _s:
                    updated = 0
                    for _sid, _desc in descriptions.items():
                        r = _s.execute(
                            _t("""
                                INSERT INTO card_stats (site_id, card_description, antiquity, fortification,
                                    cultural_influence, mystery, legacy, total_power, rarity_score, rarity_tier, category_group)
                                VALUES (:id, :desc, 0, 0, 0, 0, 0, 0, 0, 0, 'unknown')
                                ON CONFLICT (site_id) DO UPDATE SET card_description = :desc
                                WHERE card_stats.card_description IS DISTINCT FROM :desc
                            """),
                            {"desc": _desc[:200], "id": _sid},
                        )
                        updated += r.rowcount
                    _s.commit()
                    if updated:
                        # Flush sites cache so fresh queries include cd
                        from api.cache import cache_delete_pattern as _cdp

                        _cdp("sites:*")
                        logger.info(
                            f"[STARTUP] Imported {updated} card descriptions (cache flushed)"
                        )
                    else:
                        logger.info(
                            f"[STARTUP] Card descriptions already up to date ({len(descriptions)} checked)"
                        )
    except Exception as e:
        logger.warning(f"[STARTUP] Card description import failed (non-fatal): {e}")

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

    # Start Discord bot (if token is configured)
    try:
        bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
        if bot_token:
            import asyncio

            from api.services.discord_bot import start_bot

            asyncio.create_task(start_bot())
            print("[STARTUP] Discord bot task created", flush=True)
        else:
            print("[STARTUP] DISCORD_BOT_TOKEN not set, skipping bot", flush=True)
    except Exception as e:
        print(f"[STARTUP] Discord bot startup failed (non-fatal): {e}", flush=True)

    # Start nightly vector reindex scheduler
    from api.routes.vector_sync import start_nightly_scheduler

    start_nightly_scheduler()

    get_redis_client()  # Initialize Redis connection

    # Pre-warm cache in background so the health endpoint responds immediately
    import asyncio

    async def _warm_cache():
        await asyncio.sleep(2)  # Let the server finish binding
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
                            "id": row.id,
                            "n": row.name,
                            "la": row.lat,
                            "lo": row.lon,
                            "s": row.source_id,
                            "t": row.site_type,
                            "p": row.period_start,
                        }
                        if row.thumbnail_url:
                            site["i"] = row.thumbnail_url
                        if row.country:
                            site["c"] = row.country
                        sites.append(site)

                    response = {"count": len(sites), "sites": sites}
                    cache_set(cache_key, response, ttl=1800)  # 30 minutes
                    logger.info(
                        f"[STARTUP] Pre-warmed cache with {len(sites)} sites in {(time.time() - start) * 1000:.0f}ms"
                    )
            else:
                logger.info("[STARTUP] Sites cache already warm")
        except Exception as e:
            logger.warning(f"[STARTUP] Failed to pre-warm cache: {e}")

    asyncio.create_task(_warm_cache())

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
app.mount("/api/v1", create_public_api())
app.include_router(snapshots.router, prefix="/api/snapshots", tags=["snapshots"])
app.include_router(vector_sync.router, prefix="/api/vector-sync", tags=["vector-sync"])
app.include_router(wiki_images.router, prefix="/api/wiki-images", tags=["wiki-images"])
app.include_router(patreon.router, prefix="/api/patreon", tags=["patreon"])
app.include_router(interactions.router, prefix="/api/interactions", tags=["interactions"])
app.include_router(cardgame_router, prefix="/api/cards", tags=["cards"])

# Serve wiki images as static files
_wiki_images_dir = Path("public/data/images/wiki")
_wiki_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/data/images/wiki", StaticFiles(directory=str(_wiki_images_dir)), name="wiki-images")

# Serve news screenshots as static files
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
        result = session.execute(
            text("""
            SELECT source_id, COUNT(*) as count
            FROM unified_sites
            GROUP BY source_id
            ORDER BY count DESC
        """)
        )
        by_source = {row.source_id: row.count for row in result}

    response = {
        "total_sites": total_sites,
        "by_source": by_source,
    }

    # Cache for 5 minutes
    cache_set(cache_key, response, ttl=300)
    return response
