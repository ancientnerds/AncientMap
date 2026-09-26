"""
Snapshot service for database version control.

Captures the pre-change state of unified_sites rows before batch edits
or uploads, enabling undo/restore operations.

Also creates file-based snapshots for the audit page version history.
"""

import logging
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern
from pipeline.database import affected_rows
from pipeline.static_exporter import write_file_snapshot

logger = logging.getLogger(__name__)

SNAPSHOTS_DIR = Path("public/data/snapshots")

# Source IDs that hold user-curated, editable site data. A "unified" snapshot
# covers exactly these; everything else (wikidata, osm, etc.) is reproducible
# from its scraper and not worth snapshotting per-row.
CURATED_SOURCES = ("ancient_nerds", "lyra", "ancient_nerds_community")

# Columns to capture in snapshots (everything except geom binary)
_SNAPSHOT_COLUMNS = [
    "id",
    "source_id",
    "source_record_id",
    "name",
    "name_normalized",
    "lat",
    "lon",
    "site_type",
    "period_start",
    "period_end",
    "period_name",
    "country",
    "description",
    "thumbnail_url",
    "source_url",
    "edited_by",
    "raw_data",
    "parent_site_id",
    "created_at",
    "updated_at",
    "scope_status",
    "scope_reason",
]


def create_snapshot(
    db: Session,
    site_ids: list[str],
    created_by: str,
    description: str,
    snapshot_type: str,
    source_id: str | None = None,
) -> str | None:
    """Capture current state of given sites. Returns snapshot_id or None if no rows.

    Uses INSERT...SELECT with jsonb_build_object so the JSONB is assembled
    server-side in one round-trip. ~0.2s for 5k rows vs ~210s for the prior
    executemany path that timed out behind nginx for any full-source snapshot.
    """
    if not site_ids:
        return None

    # Short-circuit if no matching sites exist (avoids inserting empty header).
    row_count = db.execute(
        text("SELECT COUNT(*) FROM unified_sites WHERE id::text = ANY(:ids)"),
        {"ids": site_ids},
    ).scalar()
    if not row_count:
        return None

    snapshot_id = str(uuid.uuid4())

    # Header first (FK target for snapshot_rows.snapshot_id).
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
            "row_count": row_count,
            "source_id": source_id,
        },
    )

    # Bulk-insert snapshot rows with JSONB built server-side — one round-trip,
    # vs the prior executemany that clocked ~210s for 5k rows and timed out
    # behind nginx.
    db.execute(
        text("""
            INSERT INTO snapshot_rows (snapshot_id, site_id, old_data)
            SELECT CAST(:snapshot_id AS uuid), id, jsonb_build_object(
                'id', id::text,
                'source_id', source_id,
                'source_record_id', source_record_id,
                'name', name,
                'name_normalized', name_normalized,
                'lat', lat,
                'lon', lon,
                'site_type', site_type,
                'period_start', period_start,
                'period_end', period_end,
                'period_name', period_name,
                'country', country,
                'description', description,
                'thumbnail_url', thumbnail_url,
                'source_url', source_url,
                'edited_by', edited_by,
                'raw_data', raw_data,
                'parent_site_id', parent_site_id::text,
                'created_at', created_at::text,
                'updated_at', updated_at::text,
                'scope_status', scope_status,
                'scope_reason', scope_reason
            )
            FROM unified_sites
            WHERE id::text = ANY(:ids)
        """),
        {"snapshot_id": snapshot_id, "ids": site_ids},
    )

    logger.info(f"Created snapshot {snapshot_id}: {row_count} rows ({description})")
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


def create_unified_snapshot(
    db: Session,
    created_by: str,
    description: str,
) -> dict:
    """Create a full snapshot covering every curated source at this moment.

    This is the single entry point used by user-facing snapshot actions
    (the "Create Snapshot" button, the pre-upload checkbox). It produces
    both a DB snapshot (for restore) and a file snapshot (for the audit
    page's date-pin feature), giving one logical "record of the sites
    database at this time" with two representations.

    Stored with snapshot_type='manual' and source_id=NULL so restore_snapshot
    treats it as a multi-source full restore. Returns
    {snapshot_id, row_count, file_snapshot_key}.
    """
    rows = db.execute(
        text("SELECT id::text FROM unified_sites WHERE source_id = ANY(:sources)"),
        {"sources": list(CURATED_SOURCES)},
    ).fetchall()
    if not rows:
        return {"snapshot_id": None, "row_count": 0, "file_snapshot_key": None}

    site_ids = [r.id for r in rows]
    snapshot_id = create_snapshot(
        db,
        site_ids=site_ids,
        created_by=created_by,
        description=description,
        snapshot_type="manual",
        source_id=None,  # NULL = unified / multi-source
    )

    # Also write the file-based snapshot so the audit page's date-pin UI
    # keeps working. Orphan files (DB commit fails but file is on disk) are
    # harmless — the manifest indexes them independently.
    file_key = export_file_snapshot(db)

    return {
        "snapshot_id": snapshot_id,
        "row_count": len(site_ids),
        "file_snapshot_key": file_key,
    }


def restore_snapshot(db: Session, snapshot_id: str, restored_by: str = "system") -> dict:
    """Restore a snapshot to become the current source state.

    UPSERTs every row from the snapshot back into unified_sites — so rows that
    were later deleted come back, and rows that were edited revert to snapshot
    values. For full-source snapshots (snapshot_type='manual') or sweeping
    bulk restores (snapshot_type='undo'), also deletes rows in the same source
    that weren't in the snapshot, so post-snapshot inserts are removed.

    The restore itself is undoable: snapshots the current state first (covering
    both the rows being replaced AND the rows being deleted).
    Returns {restored, deleted, undo_snapshot_id}.
    """
    orig_snap = db.execute(
        text("""
            SELECT source_id, snapshot_type FROM db_snapshots WHERE id::text = :sid
        """),
        {"sid": snapshot_id},
    ).fetchone()
    if orig_snap is None:
        return {"restored": 0, "deleted": 0, "undo_snapshot_id": None}

    snap_site_ids = [
        r.site_id
        for r in db.execute(
            text(
                "SELECT site_id::text AS site_id FROM snapshot_rows WHERE snapshot_id::text = :sid"
            ),
            {"sid": snapshot_id},
        ).fetchall()
    ]
    if not snap_site_ids:
        return {"restored": 0, "deleted": 0, "undo_snapshot_id": None}

    orig_source = orig_snap.source_id
    orig_type = orig_snap.snapshot_type
    # Full-source semantics: delete rows in source(s) that aren't in the
    # snapshot. Only safe for snapshots that captured the entire source
    # ('manual' type). A NULL source_id on a manual snapshot means the
    # snapshot is unified across every curated source. Partial 'upload' /
    # 'edit' snapshots only hold a subset, so applying the delete to them
    # would wipe every untouched site in the source.
    full_source_restore = orig_type == "manual"
    restore_sources: tuple[str, ...] | None
    if full_source_restore:
        restore_sources = (orig_source,) if orig_source else CURATED_SOURCES
    else:
        restore_sources = None

    # Capture current state BEFORE restoring so the restore itself is undoable.
    # Skip if restoring an undo — prevents undo-of-undo chains.
    undo_id = None
    if orig_type != "undo":
        undo_ids = list(snap_site_ids)
        if restore_sources:
            # Also capture rows currently in source(s) but not in snapshot —
            # they'll be deleted by this restore, so undo needs to re-insert
            # them.
            extras = db.execute(
                text("""
                    SELECT id::text AS id FROM unified_sites
                    WHERE source_id = ANY(:sources)
                      AND NOT (id::text = ANY(:existing))
                """),
                {"sources": list(restore_sources), "existing": snap_site_ids},
            ).fetchall()
            undo_ids.extend(r.id for r in extras)
        undo_id = create_snapshot(
            db,
            site_ids=undo_ids,
            created_by=restored_by,
            description="Before restore of snapshot (undo)",
            snapshot_type="undo",
            source_id=orig_source,
        )

    # UPSERT every row from the snapshot — INSERT re-creates rows that were
    # deleted after the snapshot; ON CONFLICT UPDATE reverts edited rows.
    upserted = db.execute(
        text("""
            INSERT INTO unified_sites (
                id, source_id, source_record_id, name, name_normalized,
                lat, lon, geom, site_type,
                period_start, period_end, period_name,
                country, description, thumbnail_url, source_url,
                edited_by, raw_data, parent_site_id,
                created_at, updated_at
            )
            SELECT
                (old_data->>'id')::uuid,
                old_data->>'source_id',
                old_data->>'source_record_id',
                old_data->>'name',
                old_data->>'name_normalized',
                (old_data->>'lat')::double precision,
                (old_data->>'lon')::double precision,
                ST_SetSRID(ST_MakePoint(
                    (old_data->>'lon')::double precision,
                    (old_data->>'lat')::double precision
                ), 4326),
                old_data->>'site_type',
                (old_data->>'period_start')::integer,
                (old_data->>'period_end')::integer,
                old_data->>'period_name',
                old_data->>'country',
                old_data->>'description',
                old_data->>'thumbnail_url',
                old_data->>'source_url',
                COALESCE(old_data->>'edited_by', 'initial'),
                old_data->'raw_data',
                NULLIF(old_data->>'parent_site_id', '')::uuid,
                COALESCE((old_data->>'created_at')::timestamp, NOW()),
                NOW()
            FROM snapshot_rows
            WHERE snapshot_id::text = :sid
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                name_normalized = EXCLUDED.name_normalized,
                lat = EXCLUDED.lat,
                lon = EXCLUDED.lon,
                geom = EXCLUDED.geom,
                site_type = EXCLUDED.site_type,
                period_start = EXCLUDED.period_start,
                period_end = EXCLUDED.period_end,
                period_name = EXCLUDED.period_name,
                country = EXCLUDED.country,
                description = EXCLUDED.description,
                thumbnail_url = EXCLUDED.thumbnail_url,
                source_url = EXCLUDED.source_url,
                edited_by = EXCLUDED.edited_by,
                -- raw_data holds description_citations: the [N] markers of the
                -- description. Restoring the description without restoring
                -- them leaves a row whose citations point at text that is no
                -- longer there (plan §10.3, 2026-09). Both branches therefore
                -- read the same snapshot value; a snapshot that predates
                -- raw_data clears the column instead of keeping the newer
                -- citations.
                raw_data = EXCLUDED.raw_data,
                updated_at = NOW()
        """),
        {"sid": snapshot_id},
    )
    restored = affected_rows(upserted)

    # The scope decision (E4, migration 0020) comes back only from a snapshot that
    # recorded it. A snapshot taken before 0020 has no scope key and knows nothing about
    # a later retirement - restoring NULL from it would un-retire the site without a
    # journal row. Such a row keeps its current scope; a re-created row starts at NULL.
    # A snapshot that did record it restores it like any other column, and the restore
    # preview lists the change (scope_status is a _DIFF_FIELD).
    db.execute(_RESTORE_SCOPE_SQL, {"sid": snapshot_id})

    deleted = 0
    if restore_sources:
        result = db.execute(
            text("""
                DELETE FROM unified_sites
                WHERE source_id = ANY(:sources)
                  AND NOT (id::text = ANY(:keep))
            """),
            {"sources": list(restore_sources), "keep": snap_site_ids},
        )
        deleted = affected_rows(result)

    db.commit()
    cache_delete_pattern("sites:*")
    cache_delete_pattern("radar:*")
    logger.info(
        f"Restored snapshot {snapshot_id}: {restored} upserts, {deleted} deletes (undo: {undo_id})"
    )
    return {"restored": restored, "deleted": deleted, "undo_snapshot_id": undo_id}


#: Restores the scope columns from the snapshot rows that recorded them (the key is
#: present from migration 0020 on). restore-all-uploads (api/routes/sites.py) applies the
#: same rule inside its single UPDATE, with a CASE on the key.
_RESTORE_SCOPE_SQL = text("""
    UPDATE unified_sites us SET
        scope_status = sr.old_data->>'scope_status',
        scope_reason = sr.old_data->>'scope_reason'
    FROM snapshot_rows sr
    WHERE sr.snapshot_id::text = :sid
      AND us.id = sr.site_id
      AND sr.old_data ? 'scope_status'
""")


_DIFF_FIELDS = [
    "name",
    "site_type",
    "period_start",
    "period_name",
    "country",
    "description",
    "source_url",
    "thumbnail_url",
    # A restore can un-retire a site; the preview has to say so.
    "scope_status",
]


def _compared_fields(*states: dict) -> list[str]:
    """The _DIFF_FIELDS these recorded states can be compared on.

    scope_status only when every state recorded it. A snapshot row taken before migration
    0020 has no scope key: it says nothing about the scope, and the restore leaves the
    current scope alone for it (_RESTORE_SCOPE_SQL, restore-all-uploads). Reading the
    missing key as NULL would make the preview announce an un-retirement the restore never
    performs, and the edit history credit a later retirement to an unrelated edit.
    """
    return [
        field
        for field in _DIFF_FIELDS
        if field != "scope_status" or all("scope_status" in state for state in states)
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
                   country, description, source_url, thumbnail_url, scope_status
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
        for field in _compared_fields(old):
            old_val = old.get(field)
            cur_val = getattr(cur, field, None)
            # Normalize for comparison
            old_str = str(old_val) if old_val is not None else ""
            cur_str = str(cur_val) if cur_val is not None else ""
            if old_str != cur_str:
                changed.append(
                    {
                        "field": field,
                        "current": cur_str or None,
                        "restore_to": old_str or None,
                    }
                )

        site_entry["status"] = "changed" if changed else "unchanged"
        site_entry["fields"] = changed
        sites.append(site_entry)

    return {
        "snapshot_id": snap_row.id,
        "created_at": snap_row.created_at.isoformat() + "+00:00",
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
                   country, description, source_url, thumbnail_url, scope_status
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
        for field in _compared_fields(old, after):
            old_val = old.get(field)
            new_val = after.get(field)
            old_str = str(old_val) if old_val is not None else ""
            new_str = str(new_val) if new_val is not None else ""
            if old_str != new_str:
                changes.append(
                    {
                        "field": field,
                        "before": old_str or None,
                        "after": new_str or None,
                    }
                )

        history.append(
            {
                "date": row.created_at.isoformat() + "+00:00",
                "by": row.created_by,
                "description": row.description,
                "type": row.snapshot_type,
                "changes": changes,
            }
        )

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
            "created_at": row.created_at.isoformat() + "+00:00",
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
    """Write a dated snapshot file of the curated sites for the audit page.

    One writer for public/data/snapshots/: pipeline.static_exporter.write_file_snapshot
    (the static export writes its snapshot through the same function). Returns the key.
    """
    return write_file_snapshot(db, SNAPSHOTS_DIR)
