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
    source_id: str | None = None,
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
            INSERT INTO db_snapshots (id, created_by, description, snapshot_type, row_count, source_id)
            VALUES (:id, :created_by, :description, :snapshot_type, :row_count, :source_id)
        """),
        {
            "id": snapshot_id,
            "created_by": created_by,
            "description": description,
            "snapshot_type": snapshot_type,
            "row_count": len(rows),
            "source_id": source_id,
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


def create_manual_snapshot(
    db: Session,
    source_id: str,
    created_by: str,
    description: str,
) -> dict:
    """Create a manual snapshot of all sites in the given source.

    Returns {snapshot_id, row_count} or raises if no sites found.
    """
    # Get all site IDs for this source
    rows = db.execute(
        text("SELECT id::text FROM unified_sites WHERE source_id = :source_id"),
        {"source_id": source_id},
    ).fetchall()

    if not rows:
        return {"snapshot_id": None, "row_count": 0}

    site_ids = [r.id for r in rows]

    snapshot_id = create_snapshot(
        db,
        site_ids=site_ids,
        created_by=created_by,
        description=description,
        snapshot_type="manual",
        source_id=source_id,
    )

    return {"snapshot_id": snapshot_id, "row_count": len(site_ids)}


def restore_snapshot(db: Session, snapshot_id: str, restored_by: str = "system") -> dict:
    """Restore all rows from a snapshot.

    Creates a new snapshot of the current state first, so the restore
    itself is undoable. Returns {restored, undo_snapshot_id}.
    """
    # Get original snapshot's source_id so the undo snapshot inherits it
    orig_snap = db.execute(
        text("SELECT source_id, snapshot_type FROM db_snapshots WHERE id::text = :sid"),
        {"sid": snapshot_id},
    ).fetchone()

    snap_rows = db.execute(
        text("SELECT site_id::text, old_data FROM snapshot_rows WHERE snapshot_id::text = :sid"),
        {"sid": snapshot_id},
    ).fetchall()

    if not snap_rows:
        return {"restored": 0, "undo_snapshot_id": None}

    site_ids = [row.site_id for row in snap_rows]
    orig_source = orig_snap.source_id if orig_snap else None
    orig_type = orig_snap.snapshot_type if orig_snap else None

    # Snapshot current state BEFORE restoring, so the restore is undoable.
    # Skip if restoring an undo snapshot — prevents undo-of-undo chain clutter.
    undo_id = None
    if orig_type != "undo":
        undo_id = create_snapshot(
            db,
            site_ids=site_ids,
            created_by=restored_by,
            description="Before restore of snapshot (undo)",
            snapshot_type="undo",
            source_id=orig_source,
        )

    count = 0
    for row in snap_rows:
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
    logger.info(f"Restored snapshot {snapshot_id}: {count} rows (undo: {undo_id})")
    return {"restored": count, "undo_snapshot_id": undo_id}


_DIFF_FIELDS = [
    "name", "site_type", "period_start", "period_name",
    "country", "description", "source_url", "thumbnail_url",
]


def preview_snapshot(db: Session, snapshot_id: str) -> dict | None:
    """Return per-site diff: old_data (snapshot) vs current DB values.

    For each site in the snapshot, compares the stored old_data with the
    current unified_sites row and reports which fields differ.
    """
    # Fetch snapshot metadata
    snap_row = db.execute(
        text("""
            SELECT id::text, created_at, created_by, description, snapshot_type, row_count, source_id
            FROM db_snapshots WHERE id::text = :sid
        """),
        {"sid": snapshot_id},
    ).fetchone()
    if not snap_row:
        return None

    # Fetch all snapshot rows
    rows = db.execute(
        text("SELECT site_id::text, old_data FROM snapshot_rows WHERE snapshot_id::text = :sid"),
        {"sid": snapshot_id},
    ).fetchall()
    if not rows:
        return None

    site_ids = [r.site_id for r in rows]
    old_by_id = {r.site_id: r.old_data for r in rows}

    # Fetch current DB values for those sites
    current_rows = db.execute(
        text("""
            SELECT id::text, name, site_type, period_start, period_name,
                   country, description, source_url, thumbnail_url
            FROM unified_sites WHERE id::text = ANY(:ids)
        """),
        {"ids": site_ids},
    ).fetchall()
    current_by_id = {r.id: r for r in current_rows}

    sites = []
    for site_id in site_ids:
        old = old_by_id[site_id]
        cur = current_by_id.get(site_id)

        site_entry: dict = {
            "site_id": site_id,
            "name": old.get("name", "(unknown)"),
        }

        if not cur:
            # Site was deleted since snapshot — restoring would need an INSERT
            site_entry["status"] = "deleted"
            site_entry["fields"] = []
            sites.append(site_entry)
            continue

        changed = []
        for field in _DIFF_FIELDS:
            old_val = old.get(field)
            cur_val = getattr(cur, field, None)
            # Normalize for comparison
            old_str = str(old_val) if old_val is not None else ""
            cur_str = str(cur_val) if cur_val is not None else ""
            if old_str != cur_str:
                changed.append({
                    "field": field,
                    "current": cur_str or None,
                    "restore_to": old_str or None,
                })

        site_entry["status"] = "changed" if changed else "unchanged"
        site_entry["fields"] = changed
        sites.append(site_entry)

    return {
        "snapshot_id": snap_row.id,
        "created_at": snap_row.created_at.isoformat(),
        "created_by": snap_row.created_by,
        "description": snap_row.description,
        "snapshot_type": snap_row.snapshot_type,
        "row_count": snap_row.row_count,
        "source_id": snap_row.source_id,
        "sites": sites,
        "changed_count": sum(1 for s in sites if s["status"] == "changed"),
        "unchanged_count": sum(1 for s in sites if s["status"] == "unchanged"),
        "deleted_count": sum(1 for s in sites if s["status"] == "deleted"),
    }


def site_edit_history(db: Session, site_id: str, limit: int = 20) -> list[dict]:
    """Return the edit history for a single site from snapshot records.

    Each entry represents one change event: what the values were BEFORE
    that change was applied, plus the snapshot metadata (when, who, why).
    """
    rows = db.execute(
        text("""
            SELECT
                sr.old_data,
                ds.created_at,
                ds.created_by,
                ds.description,
                ds.snapshot_type
            FROM snapshot_rows sr
            JOIN db_snapshots ds ON ds.id = sr.snapshot_id
            WHERE sr.site_id::text = :site_id
            ORDER BY ds.created_at DESC
            LIMIT :limit
        """),
        {"site_id": site_id, "limit": limit},
    ).fetchall()

    if not rows:
        return []

    # Build history: each entry shows what changed (old_data[i] → old_data[i-1] or current)
    # The most recent snapshot's old_data shows values BEFORE the latest edit,
    # so we compare consecutive snapshots to reconstruct each change.
    # For the most recent entry, compare old_data vs current DB.
    current = db.execute(
        text("""
            SELECT name, site_type, period_start, period_name,
                   country, description, source_url, thumbnail_url
            FROM unified_sites WHERE id::text = :site_id
        """),
        {"site_id": site_id},
    ).fetchone()

    history = []
    for i, row in enumerate(rows):
        old = row.old_data
        # "after" is either the current DB (for most recent) or the old_data of the previous snapshot
        if i == 0 and current:
            after = {f: getattr(current, f, None) for f in _DIFF_FIELDS}
        elif i > 0:
            after = rows[i - 1].old_data
        else:
            after = {}

        changes = []
        for field in _DIFF_FIELDS:
            old_val = old.get(field)
            new_val = after.get(field) if isinstance(after, dict) else after.get(field, None) if hasattr(after, 'get') else None
            old_str = str(old_val) if old_val is not None else ""
            new_str = str(new_val) if new_val is not None else ""
            if old_str != new_str:
                changes.append({
                    "field": field,
                    "before": old_str or None,
                    "after": new_str or None,
                })

        history.append({
            "date": row.created_at.isoformat(),
            "by": row.created_by,
            "description": row.description,
            "type": row.snapshot_type,
            "changes": changes,
        })

    return history


def list_snapshots(db: Session, limit: int = 20, source_id: str | None = None) -> list[dict]:
    """List recent snapshots with metadata and affected site names.

    If source_id is given, only returns snapshots for that source.
    """
    if source_id:
        rows = db.execute(
            text("""
                SELECT id::text, created_at, created_by, description, snapshot_type, row_count, source_id
                FROM db_snapshots
                WHERE source_id = :source_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit, "source_id": source_id},
        ).fetchall()
    else:
        rows = db.execute(
            text("""
                SELECT id::text, created_at, created_by, description, snapshot_type, row_count, source_id
                FROM db_snapshots
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

    if not rows:
        return []

    snapshot_ids = [row.id for row in rows]

    # Fetch site names for all snapshots in one query
    site_rows = db.execute(
        text("""
            SELECT sr.snapshot_id::text, sr.old_data->>'name' AS site_name
            FROM snapshot_rows sr
            WHERE sr.snapshot_id::text = ANY(:ids)
            ORDER BY sr.old_data->>'name'
        """),
        {"ids": snapshot_ids},
    ).fetchall()

    sites_by_snap: dict[str, list[str]] = {}
    for sr in site_rows:
        sites_by_snap.setdefault(sr.snapshot_id, []).append(sr.site_name or "(unknown)")

    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
            "description": row.description,
            "snapshot_type": row.snapshot_type,
            "row_count": row.row_count,
            "source_id": row.source_id,
            "site_names": sites_by_snap.get(row.id, []),
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
