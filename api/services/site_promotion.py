"""The one place a reviewed candidate becomes a unified_sites row.

Extracted from api/routes/radar.py::promote_to_db so the radar and the
proposals review share a single INSERT. One deliberate behaviour change
inside the move: name_normalized is written as the DB's own key
(pipeline.lyra.site_key) instead of Python normalize_name(), because the
orchestrator's maintenance pass rewrites it to exactly that on the next run
anyway — the old code wrote a key that was silently replaced.

Scope note: pipeline.lyra.site_identifier._promote_to_unified_sites is a
third, ORM-based insert path (auto-promotion) with its own dedup. Unifying
it is a separate ticket.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.lyra.site_key import site_key_sql


def insert_promoted_site(
    db: Session,
    *,
    name: str,
    lat: float,
    lon: float,
    site_type: str | None,
    period_start: int | None,
    period_end: int | None,
    period_name: str | None,
    country: str | None,
    description: str | None,
    thumbnail_url: str | None,
    source_url: str | None,
    source_id: str,
    source_record_id: str,
    edited_by: str,
) -> uuid.UUID:
    """Insert the site and its label row; returns the new site id.

    Does NOT commit — the caller owns the transaction so the audit update on
    the reviewed row lands atomically with the site.
    """
    new_site_id = uuid.uuid4()
    key = site_key_sql(":name")
    db.execute(
        text(f"""
        INSERT INTO unified_sites (
            id, source_id, source_record_id, name, name_normalized,
            lat, lon, geom,
            site_type, period_start, period_end, period_name,
            country, description, thumbnail_url, source_url,
            edited_by
        ) VALUES (
            :id, :source_id, :source_record_id, :name, {key},
            :lat, :lon, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
            :site_type, :period_start, :period_end, :period_name,
            :country, :description, :thumbnail_url, :source_url,
            :edited_by
        )
        """),
        {
            "id": new_site_id,
            "source_id": source_id,
            "source_record_id": source_record_id,
            "name": name,
            "lat": lat,
            "lon": lon,
            "site_type": site_type,
            "period_start": period_start,
            "period_end": period_end,
            "period_name": period_name,
            "country": country,
            "description": description,
            "thumbnail_url": thumbnail_url,
            "source_url": source_url,
            "edited_by": edited_by,
        },
    )
    db.execute(
        text(f"""
        INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
        VALUES (:site_id, :name, {key}, 'label')
        """),
        {"site_id": new_site_id, "name": name},
    )
    return new_site_id
