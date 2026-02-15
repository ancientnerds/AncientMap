"""Snapshot manifest endpoint for database version history."""

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

MANIFEST_PATH = Path("public/data/snapshots/manifest.json")


@router.get("/")
async def get_snapshots():
    """Return the snapshot manifest listing all available dated versions."""
    if not MANIFEST_PATH.exists():
        return {"snapshots": []}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)
