"""
Snapshot service for database version control.

Captures the pre-change state of unified_sites rows before batch edits
or uploads, enabling undo/restore operations.

Also creates file-based snapshots for the audit page version history.
"""

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern

logger = logging.getLogger(__name__)

SNAPSHOTS_DIR = Path("public/data/snapshots")

# Columns to capture in snapshots (everything except geom binary)
_SNAPSHOT_COLUMNS = [
    "id", "source_id", "source_record_id", "name", "name_normalized",
    "lat", "lon", "site_type", "period_start", "period_end", "period_name",
    "country", "description", "thumbnail_url", "source_url", "edited_by",
    "raw_data", "parent_site_id", "created_at", "updated_at",
]


def create_snapshot(
    db: Session,
    site_ids: list[str],
    created_by: str,
    description: str,
    snapshot_type: str,
) -> str | None:
    """Capture current state of given sites. Returns snapshot_id or None if no rows."""
    if not site_ids:
        return None

    # Fetch current state of all affected rows
    cols = ", ".join(f"{c}::text" if c in ("id", "parent_site_id") else c for c in _SNAPSHOT_COLUMNS)
    rows = db.execute(
        text(f"SELECT {cols} FROM unified_sites WHERE id::text = ANY(:ids)"),
        {"ids": site_ids},
    ).fetchall()

    if not rows:
        return None

    snapshot_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO db_snapshots (id, created_by, description, snapshot_type, row_count)
            VALUES (:id, :created_by, :description, :snapshot_type, :row_count)
        """),
        {
            "id": snapshot_id,
            "created_by": created_by,
            "description": description,
            "snapshot_type": snapshot_type,
            "row_count": len(rows),
        },
    )

    for row in rows:
        row_dict = {}
        for col in _SNAPSHOT_COLUMNS:
            val = getattr(row, col, None)
            if val is not None:
                row_dict[col] = str(val) if isinstance(val, (uuid.UUID,)) else val
            else:
                row_dict[col] = None
        # Handle datetime serialization
        for dt_col in ("created_at", "updated_at"):
            if row_dict.get(dt_col) is not None:
                row_dict[dt_col] = str(row_dict[dt_col])

        db.execute(
            text("""
                INSERT INTO snapshot_rows (snapshot_id, site_id, old_data)
                VALUES (:snapshot_id, :site_id, CAST(:old_data AS jsonb))
            """),
            {
                "snapshot_id": snapshot_id,
                "site_id": row_dict["id"],
                "old_data": __import__("json").dumps(row_dict),
            },
        )

    logger.info(f"Created snapshot {snapshot_id}: {len(rows)} rows ({description})")
    return snapshot_id


def restore_snapshot(db: Session, snapshot_id: str) -> int:
    """Restore all rows from a snapshot. Returns count of restored rows."""
    snapshot_rows = db.execute(
        text("SELECT site_id::text, old_data FROM snapshot_rows WHERE snapshot_id::text = :sid"),
        {"sid": snapshot_id},
    ).fetchall()

    if not snapshot_rows:
        return 0

    count = 0
    for row in snapshot_rows:
        data = row.old_data
        db.execute(
            text("""
                UPDATE unified_sites SET
                    name = :name,
                    name_normalized = :name_normalized,
                    lat = :lat,
                    lon = :lon,
                    geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                    site_type = :site_type,
                    period_start = :period_start,
                    period_end = :period_end,
                    period_name = :period_name,
                    country = :country,
                    description = :description,
                    thumbnail_url = :thumbnail_url,
                    source_url = :source_url,
                    edited_by = :edited_by,
                    updated_at = NOW()
                WHERE id::text = :site_id
            """),
            {
                "site_id": data["id"],
                "name": data.get("name"),
                "name_normalized": data.get("name_normalized"),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
                "site_type": data.get("site_type"),
                "period_start": data.get("period_start"),
                "period_end": data.get("period_end"),
                "period_name": data.get("period_name"),
                "country": data.get("country"),
                "description": data.get("description"),
                "thumbnail_url": data.get("thumbnail_url"),
                "source_url": data.get("source_url"),
                "edited_by": data.get("edited_by", "initial"),
            },
        )
        count += 1

    db.commit()
    cache_delete_pattern("sites:*")
    cache_delete_pattern("radar:*")
    logger.info(f"Restored snapshot {snapshot_id}: {count} rows")
    return count


def list_snapshots(db: Session, limit: int = 20) -> list[dict]:
    """List recent snapshots with metadata."""
    rows = db.execute(
        text("""
            SELECT id::text, created_at, created_by, description, snapshot_type, row_count
            FROM db_snapshots
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()

    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
            "description": row.description,
            "snapshot_type": row.snapshot_type,
            "row_count": row.row_count,
        }
        for row in rows
    ]


def export_file_snapshot(db: Session) -> str:
    """Export current DB state as a dated snapshot file for the audit page.

    Queries all audit-source sites, writes a JSON file to public/data/snapshots/,
    and updates the manifest. Returns the snapshot date key.
    """
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    snapshot_key = now.strftime("%Y-%m-%d_%H%M%S")

    result = db.execute(text("""
        SELECT
            id, name, lat, lon, source_id, site_type,
            period_start, period_end, period_name, country,
            description, thumbnail_url, source_url, edited_by,
            created_at
        FROM unified_sites
        WHERE source_id IN ('ancient_nerds', 'lyra', 'ancient_nerds_community')
        ORDER BY source_id, name
    """))

    sites = []
    source_counts: dict[str, int] = defaultdict(int)

    for row in result:
        site: dict[str, object] = {
            "id": str(row.id),
            "n": row.name[:100] if row.name else "",
            "la": round(row.lat, 5),
            "lo": round(row.lon, 5),
            "s": row.source_id,
        }
        if row.site_type:
            site["t"] = row.site_type
        if row.period_start is not None:
            site["p"] = row.period_start
        if row.period_name:
            site["pn"] = row.period_name
        if row.country:
            site["c"] = row.country
        if row.description:
            site["d"] = row.description[:500]
        if row.thumbnail_url:
            site["i"] = row.thumbnail_url
        if row.source_url:
            site["u"] = row.source_url
        if row.edited_by and row.edited_by != "initial":
            site["eb"] = row.edited_by
        if row.created_at:
            site["ea"] = row.created_at.isoformat()

        sites.append(site)
        source_counts[row.source_id] += 1

    snapshot_data = {
        "snapshot_date": now.isoformat(),
        "sites": sites,
        "count": len(sites),
        "by_source": dict(source_counts),
    }

    snapshot_file = f"{snapshot_key}.json"
    with open(SNAPSHOTS_DIR / snapshot_file, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, separators=(",", ":"))

    # Update manifest
    manifest_path = SNAPSHOTS_DIR / "manifest.json"
    manifest: dict = {"snapshots": []}
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

    snapshots = manifest["snapshots"]
    snapshots.append({
        "date": snapshot_key,
        "file": snapshot_file,
        "sites": len(sites),
        "by_source": dict(source_counts),
    })
    snapshots.sort(key=lambda s: s["date"], reverse=True)
    manifest["snapshots"] = snapshots

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"File snapshot {snapshot_key}: {len(sites)} sites")
    return snapshot_key
