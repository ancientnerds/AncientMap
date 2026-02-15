"""Snapshot manifest and data endpoints for database version history."""

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()

SNAPSHOTS_DIR = Path("public/data/snapshots")
MANIFEST_PATH = SNAPSHOTS_DIR / "manifest.json"


@router.get("/")
async def get_snapshots():
    """Return the snapshot manifest listing all available dated versions."""
    if not MANIFEST_PATH.exists():
        return {"snapshots": []}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


@router.get("/{date}.json")
async def get_snapshot_data(date: str):
    """Return a specific dated snapshot's site data."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(status_code=400, detail="Invalid date format")
    path = SNAPSHOTS_DIR / f"{date}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(json.load(f))
