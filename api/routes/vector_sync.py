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
                text(
                    "SELECT last_completed_at, last_duration_seconds, last_result FROM vector_sync_state WHERE collection = 'all'"
                )
            ).fetchone()
            if row and row.last_completed_at:
                _reindex_state["last_completed_at"] = (
                    row.last_completed_at.isoformat() + "Z"
                    if row.last_completed_at.tzinfo is None
                    else row.last_completed_at.isoformat()
                )
                _reindex_state["last_duration_seconds"] = row.last_duration_seconds
                _reindex_state["last_result"] = row.last_result
                logger.info(
                    f"[VECTOR-SYNC] Loaded persisted state: last run {_reindex_state['last_completed_at']}"
                )
    except Exception as e:
        logger.warning(
            f"[VECTOR-SYNC] Could not load persisted state (table may not exist yet): {e}"
        )


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
    collection: str | None = (
        None  # "sites" | "news" | "transcripts" | "articles" | "empires" | "research" | None (all)
    )
    rebuild: bool = False
    backend: str | None = None  # "voyage" | "local" | None (both)


# ─── GET /status ─────────────────────────────────────────────────────────────
@router.get("/status")
async def vector_sync_status():
    """Compare PostgreSQL row counts with Qdrant point counts."""
    # PG counts
    with get_session() as session:
        pg_sites = session.execute(
            text("SELECT COUNT(*) FROM unified_sites WHERE source_id = 'ancient_nerds'")
        ).scalar()
        pg_news = session.execute(text("SELECT COUNT(*) FROM news_items")).scalar()
        pg_transcripts = session.execute(
            text("SELECT COUNT(*) FROM news_videos WHERE transcript_text IS NOT NULL")
        ).scalar()
        pg_articles = session.execute(text("SELECT COUNT(*) FROM news_articles")).scalar()
        pg_research = session.execute(
            text("SELECT COUNT(*) FROM research_requests WHERE is_public = TRUE")
        ).scalar()

    # Qdrant counts — both voyage and local collection sets
    qdrant_available = True
    qdrant_counts: dict[str, int] = {}
    _COLLECTION_NAMES = ["sites", "news", "transcripts", "articles", "empires", "research"]
    try:
        from api.services.lyra_embeddings import get_qdrant_client

        client = get_qdrant_client()
        for name in _COLLECTION_NAMES:
            for suffix in ("", "_local"):
                coll = f"{name}{suffix}"
                try:
                    info = client.get_collection(coll)
                    qdrant_counts[coll] = info.points_count
                except Exception:
                    qdrant_counts[coll] = 0
    except Exception:
        qdrant_available = False

    # Empire boundary counts (static GeoJSON files, not in Qdrant)
    empire_count = 0
    boundary_count = 0
    try:
        meta_path = (
            Path(__file__).resolve().parents[2] / "public" / "data" / "historical" / "metadata.json"
        )
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
        polities_path = (
            Path(__file__).resolve().parents[2]
            / "ancient-nerds-map"
            / "src"
            / "data"
            / "seshat"
            / "polities.json"
        )
        polities_data = json.loads(polities_path.read_text())
        seshat_polity_count = len(polities_data.get("polities", {}))
    except Exception:
        pass

    # Build collection status for both backends
    _pg_counts = {
        "sites": pg_sites,
        "news": pg_news,
        "transcripts": pg_transcripts,
        "articles": pg_articles,
        "empires": seshat_polity_count,
        "research": pg_research,
    }
    _no_delta = {
        "transcripts",
        "articles",
        "research",
    }  # chunk counts aren't comparable to PG counts

    collections_status = {}
    for name in _COLLECTION_NAMES:
        pg = _pg_counts[name]
        voyage_count = qdrant_counts.get(name, 0)
        local_count = qdrant_counts.get(f"{name}_local", 0)
        entry: dict = {
            "pg_count": pg,
            # Flat fields for frontend (voyage as primary)
            "qdrant_count": voyage_count,
            # Per-backend detail
            "voyage": {"qdrant_count": voyage_count},
            "local": {"qdrant_count": local_count},
        }
        if name in _no_delta:
            entry["note"] = "Qdrant count is chunks, PG count is source rows — delta not comparable"
            entry["delta"] = None
        else:
            entry["delta"] = pg - voyage_count
            entry["voyage"]["delta"] = pg - voyage_count
            entry["local"]["delta"] = pg - local_count
        collections_status[name] = entry

    return {
        "qdrant_available": qdrant_available,
        "collections": collections_status,
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
            "next_run_utc": _next_run_utc
            if (_nightly_task is not None and not _nightly_task.done())
            else None,
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

    # Build CLI args — run one or both backends
    backends = [body.backend] if body.backend else ["voyage"]
    cmds = []
    for be in backends:
        cmd = [sys.executable, "scripts/build_lyra_index.py", "--backend", be]
        if body.collection:
            cmd += ["--collection", body.collection]
        if body.rebuild:
            cmd.append("--rebuild")
        cmds.append(cmd)

    _reindex_state["running"] = True
    _reindex_state["started_at"] = datetime.now(UTC).isoformat()
    _reindex_state["collection"] = body.collection or "all"

    asyncio.create_task(_run_reindex_sequence(cmds))

    return {
        "status": "started",
        "collection": body.collection or "all",
        "rebuild": body.rebuild,
        "backends": backends,
    }


async def _run_reindex_sequence(cmds: list[list[str]]):
    """Run one or more build_lyra_index.py invocations sequentially."""
    collection = _reindex_state["collection"] or "all"
    start = time.monotonic()
    results = []
    try:
        for cmd in cmds:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                output = (stderr or stdout or b"").decode(errors="replace")[-500:]
                results.append(f"failed (exit {proc.returncode}): {output}")
            else:
                results.append("success")

        duration = time.monotonic() - start
        _reindex_state["last_duration_seconds"] = round(duration)
        _reindex_state["last_completed_at"] = datetime.now(UTC).isoformat()
        if all(r == "success" for r in results):
            _reindex_state["last_result"] = "success"
        else:
            _reindex_state["last_result"] = "; ".join(results)
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
        try:
            wait = _seconds_until_next(NIGHTLY_HOUR_UTC)
            _next_run_utc = (datetime.now(UTC) + timedelta(seconds=wait)).isoformat()
            logger.info(
                f"[VECTOR-SYNC] Next nightly reindex at {_next_run_utc} ({wait / 3600:.1f}h from now)"
            )
            await asyncio.sleep(wait)

            if _reindex_state["running"]:
                logger.info("[VECTOR-SYNC] Nightly reindex skipped — already running")
                continue

            logger.info("[VECTOR-SYNC] Starting nightly auto-reindex (voyage backend)")
            cmds = [
                [sys.executable, "scripts/build_lyra_index.py", "--backend", "voyage"],
            ]
            _reindex_state["running"] = True
            _reindex_state["started_at"] = datetime.now(UTC).isoformat()
            _reindex_state["collection"] = "all"
            await _run_reindex_sequence(cmds)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[VECTOR-SYNC] Nightly loop error: {e}")
            _reindex_state["running"] = False
            await asyncio.sleep(60)


def start_nightly_scheduler():
    """Create the nightly scheduler task. Call from lifespan."""
    global _nightly_task
    _nightly_task = asyncio.create_task(schedule_nightly_reindex())
    logger.info("[VECTOR-SYNC] Nightly auto-reindex scheduler started")
