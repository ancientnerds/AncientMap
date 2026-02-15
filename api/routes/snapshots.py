"""Snapshot manifest and data endpoints for database version history."""

import json
import re
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter()

SNAPSHOTS_DIR = Path("public/data/snapshots")
MANIFEST_PATH = SNAPSHOTS_DIR / "manifest.json"

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


@lru_cache(maxsize=16)
def _compute_diff(from_date: str, to_date: str) -> dict:
    """Compare two snapshots and return structured diff. Cached by date pair."""
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

    return {
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
