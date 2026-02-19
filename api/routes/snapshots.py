"""Snapshot manifest and data endpoints for database version history."""

import json
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern
from api.services.jwt_auth import require_founder
from pipeline.database import DiscordUser, get_db

router = APIRouter()

SNAPSHOTS_DIR = Path("public/data/snapshots")
MANIFEST_PATH = SNAPSHOTS_DIR / "manifest.json"

# Valid source IDs for pinning
VALID_SOURCES = {"ancient_nerds", "lyra", "ancient_nerds_community"}

# Compact key → display name for diff comparison
FIELD_MAP = {
    "n": "Name",
    "t": "Type",
    "pn": "Period",
    "p": "Period Start",
    "c": "Country",
    "d": "Description",
    "u": "Source URL",
    "i": "Image URL",
    "la": "Latitude",
    "lo": "Longitude",
    "eb": "Edited By",
}

# Fields to skip in comparison (metadata, not content)
SKIP_FIELDS = {"id", "s", "ea"}

# In-memory pins cache (shared with sites.py via getter)
_pins_cache: dict[str, str | None] | None = None
_pins_cache_ts: float = 0
_PINS_CACHE_TTL = 60  # seconds


def get_active_pins(db: Session) -> dict[str, str | None]:
    """Return active pins as {source_id: snapshot_date}. Cached 60s."""
    global _pins_cache, _pins_cache_ts
    now = time.time()
    if _pins_cache is not None and now - _pins_cache_ts < _PINS_CACHE_TTL:
        return _pins_cache
    rows = db.execute(text(
        "SELECT source_id, snapshot_date FROM source_version_pins"
    )).fetchall()
    _pins_cache = {r.source_id: r.snapshot_date for r in rows}
    _pins_cache_ts = now
    return _pins_cache


def clear_pins_cache():
    """Clear the in-memory pins cache (called after pin changes)."""
    global _pins_cache, _pins_cache_ts
    _pins_cache = None
    _pins_cache_ts = 0


@router.get("/")
async def get_snapshots():
    """Return the snapshot manifest listing all available dated versions."""
    if not MANIFEST_PATH.exists():
        return {"snapshots": []}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def _resolve_date(date_key: str) -> str:
    """Resolve 'latest' to the most recent snapshot date, or validate the key."""
    if date_key == "latest":
        if not MANIFEST_PATH.exists():
            raise HTTPException(status_code=400, detail="No snapshot manifest found")
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
        entries = manifest.get("snapshots", [])
        if not entries:
            raise HTTPException(status_code=400, detail="No snapshots available")
        return entries[0]["date"]
    if not re.match(r"^\d{4}-\d{2}-\d{2}(_\d{6})?$", date_key):
        raise HTTPException(status_code=400, detail=f"Invalid date format: {date_key}")
    return date_key


def _load_snapshot(date: str) -> list[dict]:
    """Load a snapshot's sites array from disk."""
    path = SNAPSHOTS_DIR / f"{date}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {date}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("sites", [])


_diff_cache: dict[tuple[str, str], dict] = {}


def _compute_diff(from_date: str, to_date: str) -> dict:
    """Compare two snapshots and return structured diff. Cached by date pair (exceptions not cached)."""
    cache_key = (from_date, to_date)
    if cache_key in _diff_cache:
        return _diff_cache[cache_key]
    from_sites = _load_snapshot(from_date)
    to_sites = _load_snapshot(to_date)

    from_map = {s["id"]: s for s in from_sites}
    to_map = {s["id"]: s for s in to_sites}

    from_ids = set(from_map.keys())
    to_ids = set(to_map.keys())

    added_ids = to_ids - from_ids
    removed_ids = from_ids - to_ids
    common_ids = from_ids & to_ids

    added = [to_map[sid] for sid in added_ids]
    removed = [from_map[sid] for sid in removed_ids]

    changed = []
    field_counts: dict[str, int] = {}

    for sid in common_ids:
        old = from_map[sid]
        new = to_map[sid]
        fields = {}
        for key, display in FIELD_MAP.items():
            old_val = str(old.get(key, "")) if old.get(key) is not None else ""
            new_val = str(new.get(key, "")) if new.get(key) is not None else ""
            if old_val != new_val:
                fields[display] = {"from": old_val, "to": new_val}
                field_counts[display] = field_counts.get(display, 0) + 1
        if fields:
            changed.append({
                "id": sid,
                "n": new.get("n", old.get("n", "")),
                "fields": fields,
            })

    # Sort: changed by name, added/removed by name
    changed.sort(key=lambda x: x["n"].lower())
    added.sort(key=lambda x: x.get("n", "").lower())
    removed.sort(key=lambda x: x.get("n", "").lower())

    result = {
        "from_date": from_date,
        "to_date": to_date,
        "from_count": len(from_sites),
        "to_count": len(to_sites),
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "fields": field_counts,
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }
    # Evict oldest if cache is full
    if len(_diff_cache) >= 16:
        _diff_cache.pop(next(iter(_diff_cache)))
    _diff_cache[cache_key] = result
    return result


@router.get("/diff")
async def get_snapshot_diff(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
):
    """Compare two snapshots and return added/removed/changed sites."""
    resolved_from = _resolve_date(from_date)
    resolved_to = _resolve_date(to_date)

    if resolved_from == resolved_to:
        raise HTTPException(
            status_code=400, detail="Cannot diff a snapshot against itself"
        )

    result = _compute_diff(resolved_from, resolved_to)
    return JSONResponse(result)


# =============================================================================
# Version Pins (per-source snapshot pinning for public globe)
# =============================================================================


class PinRequest(BaseModel):
    snapshot_date: str | None = None


@router.get("/pins")
async def get_pins(db: Session = Depends(get_db)):
    """Return active version pins per source."""
    pins = get_active_pins(db)
    result = {}
    for source_id, snap_date in pins.items():
        if snap_date is not None:
            result[source_id] = {"snapshot_date": snap_date}
    return {"pins": result}


@router.put("/pins/{source_id}")
async def set_pin(
    source_id: str,
    body: PinRequest,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """Pin or unpin a source to a specific snapshot version (founders only)."""
    edited_by = user.username

    if source_id not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source_id}")

    snap_date = body.snapshot_date

    # If pinning, validate the snapshot file exists
    if snap_date is not None:
        path = SNAPSHOTS_DIR / f"{snap_date}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Snapshot not found: {snap_date}")

    # Upsert
    if snap_date is None:
        # Unpin: delete the row
        db.execute(text(
            "DELETE FROM source_version_pins WHERE source_id = :sid"
        ), {"sid": source_id})
    else:
        db.execute(text("""
            INSERT INTO source_version_pins (source_id, snapshot_date, pinned_at, pinned_by)
            VALUES (:sid, :snap, NOW(), :by)
            ON CONFLICT (source_id) DO UPDATE SET
                snapshot_date = EXCLUDED.snapshot_date,
                pinned_at = EXCLUDED.pinned_at,
                pinned_by = EXCLUDED.pinned_by
        """), {"sid": source_id, "snap": snap_date, "by": edited_by})

    db.commit()

    # Clear caches
    clear_pins_cache()
    cache_delete_pattern("sites:*")

    return {"success": True, "source_id": source_id, "snapshot_date": snap_date}


@router.get("/{date}.json")
async def get_snapshot_data(date: str):
    """Return a specific dated snapshot's site data."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}(_\d{6})?$", date):
        raise HTTPException(status_code=400, detail="Invalid date format")
    path = SNAPSHOTS_DIR / f"{date}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))
