"""Vector DB (Qdrant) sync status and reindex endpoints."""

import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api.services.jwt_auth import require_founder
from pipeline.database import DiscordUser, VectorSyncState, get_session

router = APIRouter()
logger = logging.getLogger(__name__)

# ─── Module-level reindex state ──────────────────────────────────────────────
_reindex_state: dict = {
    "running": False,
    "started_at": None,
    "collection": None,
    "last_completed_at": None,
    "last_duration_seconds": None,
    "last_result": None,
}

# Nightly scheduler state
_nightly_task: asyncio.Task | None = None
_next_run_utc: str | None = None

NIGHTLY_HOUR_UTC = 3  # 3:00 AM UTC


def _load_persisted_state():
    """Load last reindex state from the database (called once at startup)."""
    try:
        with get_session() as session:
            row = session.execute(
                text("SELECT last_completed_at, last_duration_seconds, last_result FROM vector_sync_state WHERE collection = 'all'")
            ).fetchone()
            if row and row.last_completed_at:
                _reindex_state["last_completed_at"] = row.last_completed_at.isoformat() + "Z" if row.last_completed_at.tzinfo is None else row.last_completed_at.isoformat()
                _reindex_state["last_duration_seconds"] = row.last_duration_seconds
                _reindex_state["last_result"] = row.last_result
                logger.info(f"[VECTOR-SYNC] Loaded persisted state: last run {_reindex_state['last_completed_at']}")
    except Exception as e:
        logger.warning(f"[VECTOR-SYNC] Could not load persisted state (table may not exist yet): {e}")


def _persist_state(collection: str):
    """Save reindex completion to the database."""
    try:
        with get_session() as session:
            session.execute(
                text("""
                    INSERT INTO vector_sync_state (collection, last_completed_at, last_duration_seconds, last_result)
                    VALUES (:col, :ts, :dur, :res)
                    ON CONFLICT (collection) DO UPDATE
                    SET last_completed_at = :ts, last_duration_seconds = :dur, last_result = :res
                """),
                {
                    "col": collection,
                    "ts": datetime.now(UTC),
                    "dur": _reindex_state["last_duration_seconds"],
                    "res": _reindex_state["last_result"],
                },
            )
            session.commit()
    except Exception as e:
        logger.warning(f"[VECTOR-SYNC] Failed to persist state: {e}")


# Load persisted state on module import (safe — get_session handles connection)
_load_persisted_state()


class ReindexRequest(BaseModel):
    collection: str | None = None  # "sites" | "news" | "transcripts" | "articles" | "empires" | None (all)
    rebuild: bool = False


# ─── GET /status ─────────────────────────────────────────────────────────────
@router.get("/status")
async def vector_sync_status():
    """Compare PostgreSQL row counts with Qdrant point counts."""
    # PG counts
    with get_session() as session:
        pg_sites = session.execute(
            text("SELECT COUNT(*) FROM unified_sites WHERE source_id = 'ancient_nerds'")
        ).scalar()
        pg_news = session.execute(
            text("SELECT COUNT(*) FROM news_items")
        ).scalar()
        pg_transcripts = session.execute(
            text("SELECT COUNT(*) FROM news_videos WHERE transcript_text IS NOT NULL AND status IN ('transcribed', 'summarized')")
        ).scalar()
        pg_articles = session.execute(
            text("SELECT COUNT(*) FROM news_articles")
        ).scalar()

    # Qdrant counts
    qdrant_available = True
    qdrant_sites = 0
    qdrant_news = 0
    qdrant_transcripts = 0
    qdrant_articles = 0
    qdrant_empires = 0
    try:
        from api.services.lyra_embeddings import get_qdrant_client

        client = get_qdrant_client()
        try:
            info = client.get_collection("sites")
            qdrant_sites = info.points_count
        except Exception:
            pass
        try:
            info = client.get_collection("news")
            qdrant_news = info.points_count
        except Exception:
            pass
        try:
            info = client.get_collection("transcripts")
            qdrant_transcripts = info.points_count
        except Exception:
            pass
        try:
            info = client.get_collection("articles")
            qdrant_articles = info.points_count
        except Exception:
            pass
        try:
            info = client.get_collection("empires")
            qdrant_empires = info.points_count
        except Exception:
            pass
    except Exception:
        qdrant_available = False

    # Empire boundary counts (static GeoJSON files, not in Qdrant)
    empire_count = 0
    boundary_count = 0
    try:
        meta_path = Path(__file__).resolve().parents[2] / "ancient-nerds-map" / "public" / "data" / "historical" / "metadata.json"
        meta = json.loads(meta_path.read_text())
        empire_count = meta.get("totalEmpires", 0)
        for region_empires in meta.get("empires", {}).values():
            for emp in region_empires:
                boundary_count += emp.get("yearCount", 0)
    except Exception:
        pass

    # Seshat polity count (source for empires Qdrant collection)
    seshat_polity_count = 0
    try:
        polities_path = Path(__file__).resolve().parents[2] / "ancient-nerds-map" / "src" / "data" / "seshat" / "polities.json"
        polities_data = json.loads(polities_path.read_text())
        seshat_polity_count = len(polities_data.get("polities", {}))
    except Exception:
        pass

    return {
        "qdrant_available": qdrant_available,
        "collections": {
            "sites": {
                "pg_count": pg_sites,
                "qdrant_count": qdrant_sites,
                "delta": pg_sites - qdrant_sites,
            },
            "news": {
                "pg_count": pg_news,
                "qdrant_count": qdrant_news,
                "delta": pg_news - qdrant_news,
            },
            "transcripts": {
                "pg_count": pg_transcripts,
                "qdrant_count": qdrant_transcripts,
                "delta": None,
                "note": "Qdrant count is chunks, PG count is videos — delta not comparable",
            },
            "articles": {
                "pg_count": pg_articles,
                "qdrant_count": qdrant_articles,
                "delta": None,
                "note": "Qdrant count is chunks, PG count is articles — delta not comparable",
            },
            "empires": {
                "pg_count": seshat_polity_count,
                "qdrant_count": qdrant_empires,
                "delta": seshat_polity_count - qdrant_empires,
            },
        },
        "empires": {
            "empire_count": empire_count,
            "boundary_count": boundary_count,
        },
        "reindex": {
            "running": _reindex_state["running"],
            "started_at": _reindex_state["started_at"],
            "collection": _reindex_state["collection"],
            "last_completed_at": _reindex_state["last_completed_at"],
            "last_duration_seconds": _reindex_state["last_duration_seconds"],
            "last_result": _reindex_state["last_result"],
        },
        "auto_reindex": {
            "enabled": _nightly_task is not None and not _nightly_task.done(),
            "next_run_utc": _next_run_utc,
        },
    }


# ─── POST /reindex ──────────────────────────────────────────────────────────
@router.post("/reindex")
async def vector_reindex(
    body: ReindexRequest,
    _user: DiscordUser = Depends(require_founder),
):
    """Trigger a background reindex of Qdrant collections (founders only)."""

    if _reindex_state["running"]:
        raise HTTPException(status_code=409, detail="Reindex already running")

    # Build CLI args
    cmd = [sys.executable, "scripts/build_lyra_index.py"]
    if body.collection:
        cmd += ["--collection", body.collection]
    if body.rebuild:
        cmd.append("--rebuild")

    _reindex_state["running"] = True
    _reindex_state["started_at"] = datetime.now(UTC).isoformat()
    _reindex_state["collection"] = body.collection or "all"

    asyncio.create_task(_run_reindex(cmd))

    return {"status": "started", "collection": body.collection or "all", "rebuild": body.rebuild}


async def _run_reindex(cmd: list[str]):
    """Run build_lyra_index.py as a subprocess and update state when done."""
    collection = _reindex_state["collection"] or "all"
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        duration = time.monotonic() - start
        _reindex_state["last_duration_seconds"] = round(duration)
        _reindex_state["last_completed_at"] = datetime.now(UTC).isoformat()
        _reindex_state["last_result"] = "success" if proc.returncode == 0 else f"failed (exit {proc.returncode})"
    except Exception as exc:
        _reindex_state["last_completed_at"] = datetime.now(UTC).isoformat()
        _reindex_state["last_duration_seconds"] = round(time.monotonic() - start)
        _reindex_state["last_result"] = f"error: {exc}"
    finally:
        _reindex_state["running"] = False
        _reindex_state["started_at"] = None
        _reindex_state["collection"] = None
        _persist_state(collection)


# ─── Nightly auto-reindex scheduler ─────────────────────────────────────────
def _seconds_until_next(hour_utc: int) -> float:
    """Seconds from now until the next occurrence of hour_utc:00 UTC."""
    now = datetime.now(UTC)
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def schedule_nightly_reindex():
    """Loop forever: sleep until 3:00 AM UTC, then trigger a full incremental reindex."""
    global _next_run_utc
    while True:
        wait = _seconds_until_next(NIGHTLY_HOUR_UTC)
        _next_run_utc = (datetime.now(UTC) + timedelta(seconds=wait)).isoformat()
        logger.info(f"[VECTOR-SYNC] Next nightly reindex at {_next_run_utc} ({wait / 3600:.1f}h from now)")
        await asyncio.sleep(wait)

        if _reindex_state["running"]:
            logger.info("[VECTOR-SYNC] Nightly reindex skipped — already running")
            continue

        logger.info("[VECTOR-SYNC] Starting nightly auto-reindex")
        cmd = [sys.executable, "scripts/build_lyra_index.py"]
        _reindex_state["running"] = True
        _reindex_state["started_at"] = datetime.now(UTC).isoformat()
        _reindex_state["collection"] = "all"
        await _run_reindex(cmd)


def start_nightly_scheduler():
    """Create the nightly scheduler task. Call from lifespan."""
    global _nightly_task
    _nightly_task = asyncio.create_task(schedule_nightly_reindex())
    logger.info("[VECTOR-SYNC] Nightly auto-reindex scheduler started")
