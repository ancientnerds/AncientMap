"""Review API for prospector proposals (founders only).

GET  /api/proposals?status=review|new|needs_decision|have_it|...   ranked queue
GET  /api/proposals/{id}                                            one card
POST /api/proposals/{id}/approve   (PromoteOverrides body)  -> unified_sites, source_id='lyra'
POST /api/proposals/{id}/merge/{site_id}                    -> ONE alias row, status merged
POST /api/proposals/{id}/same-as/{other_id}                 -> two proposals are one place
POST /api/proposals/{id}/reject

Ranking is by (has coordinates, corpus diversity, evidence count), with a
prior machine verdict demoted to the end — and explicitly NOT by mention
frequency: the frequency head of the corpus is "giza plateau", "göbekli
tepe", "egypt", an anti-signal for finding sites we lack.

A proposal that came from the radar backlog carries `contribution_id`; every
human decision here is mirrored onto that user_contributions row so the
radar tab shrinks with the queue instead of showing the same card twice.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.cache import cache_delete_pattern
from api.routes.radar import (
    PromoteOverrides,
    _apply_overrides,
    _missing_core_fields,
    _require_uuid,
)
from api.services.jwt_auth import require_founder
from api.services.site_promotion import insert_promoted_site
from pipeline.database import DiscordUser, get_db
from pipeline.lyra.site_key import site_key_sql
from pipeline.utils.text import categorize_period

logger = logging.getLogger(__name__)
router = APIRouter()

STATUSES = (
    "new",
    "needs_decision",
    "have_it",
    "approved",
    "merged",
    "rejected",
    "out_of_scope",
    "not_a_place",
)

_ORDER = """
    ORDER BY (p.prior_verdict IS NOT NULL) ASC,
             (p.lat IS NOT NULL) DESC,
             array_length(string_to_array(NULLIF(p.corpus_kinds, ''), ','), 1) DESC NULLS LAST,
             p.evidence_count DESC, p.first_seen_at ASC
"""


def _row_to_item(session: Session, row) -> dict:
    ev = session.execute(
        text("""SELECT corpus, source_pk, mentioned_as, quote, locator, footnotes
                FROM site_proposal_evidence WHERE proposal_id = :id ORDER BY id"""),
        {"id": row.id},
    ).fetchall()
    return {
        "id": str(row.id),
        "name": row.name,
        "aliases": list(row.aliases or []),
        "status": row.status,
        "place_class": row.place_class,
        "resolved_label": row.resolved_label,
        "wikidata_qid": row.wikidata_qid,
        "enwiki_title": row.enwiki_title,
        "resolution_path": row.resolution_path,
        "resolution_note": row.resolution_note,
        "prior_verdict": row.prior_verdict,
        "contribution_id": str(row.contribution_id) if row.contribution_id else None,
        "lat": row.lat,
        "lon": row.lon,
        "coord_precision": row.coord_precision,
        "location_rung": row.location_rung,
        "country": row.country,
        "country_in_text": row.country_in_text,
        "site_type": row.site_type,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "period_name": row.period_name,
        "period_phrase": row.period_phrase,
        "description": row.description,
        "thumbnail_url": row.thumbnail_url,
        "wikipedia_url": row.wikipedia_url,
        "dedup_verdict": row.dedup_verdict,
        "dedup_trace": row.dedup_trace or [],
        "scope_verdict": row.scope_verdict,
        "an_site_id": str(row.an_site_id) if row.an_site_id else None,
        "external_site_id": str(row.external_site_id) if row.external_site_id else None,
        "external_source_id": row.external_source_id,
        "promoted_site_id": str(row.promoted_site_id) if row.promoted_site_id else None,
        "merged_into_site_id": str(row.merged_into_site_id) if row.merged_into_site_id else None,
        "evidence_count": row.evidence_count,
        "corpus_kinds": [k for k in (row.corpus_kinds or "").split(",") if k],
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "review_notes": row.review_notes,
        "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
        "missing_core_fields": _missing_core_fields(
            {
                "lat": row.lat,
                "lon": row.lon,
                "country": row.country,
                "site_type": row.site_type,
                "description": row.description,
            }
        ),
        "evidence": [
            {
                "corpus": e.corpus,
                "source_pk": e.source_pk,
                "mentioned_as": e.mentioned_as,
                "quote": e.quote,
                "locator": e.locator,
                "footnotes": e.footnotes or [],
            }
            for e in ev
        ],
    }


@router.get("")
@router.get("/")
def list_proposals(
    status: str = Query("review", pattern="^(" + "|".join(STATUSES) + "|review)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """`review` = new + needs_decision, the two statuses awaiting a human."""
    where = "p.status IN ('new', 'needs_decision')" if status == "review" else "p.status = :status"
    rows = db.execute(
        text(f"""SELECT COUNT(*) OVER() AS _total, p.* FROM site_proposals p
                 WHERE {where} AND p.place_class = 'site' {_ORDER} LIMIT :limit OFFSET :offset"""),
        {"status": status, "limit": limit, "offset": offset},
    ).fetchall()
    counts = db.execute(
        text(
            "SELECT status, COUNT(*) AS n FROM site_proposals WHERE place_class = 'site' GROUP BY status"
        )
    ).fetchall()
    return {
        "items": [_row_to_item(db, r) for r in rows],
        "total_count": rows[0]._total if rows else 0,
        "counts": {r.status: r.n for r in counts},
    }


@router.get("/{proposal_id}")
def get_proposal(
    proposal_id: str,
    _user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    return _row_to_item(db, _load(db, proposal_id))


def _load(db: Session, proposal_id: str):
    _require_uuid(proposal_id, 404, "Proposal not found")
    row = db.execute(
        text("SELECT * FROM site_proposals WHERE id = :id"), {"id": proposal_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return row


def _require_open(row) -> None:
    if row.status in ("approved", "merged"):
        raise HTTPException(status_code=409, detail=f"Already {row.status}")


def _stamp(db: Session, proposal_id: str, status: str, user: DiscordUser, **cols) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    db.execute(
        text(f"""UPDATE site_proposals
                 SET status = :status, reviewed_by = :by, reviewed_at = :at,
                     updated_at = NOW(){", " + sets if sets else ""}
                 WHERE id = :id"""),
        {
            "id": proposal_id,
            "status": status,
            "by": user.username,
            "at": datetime.now(UTC),
            **cols,
        },
    )


def _mirror_contribution(db: Session, row, *, enrichment_status: str, site_id=None) -> None:
    """Keep the radar's own row in step with the decision made here."""
    if not row.contribution_id:
        return
    db.execute(
        text("""UPDATE user_contributions
                SET enrichment_status = :st,
                    promoted_site_id = COALESCE(:site_id, promoted_site_id)
                WHERE id = :cid"""),
        {"st": enrichment_status, "site_id": site_id, "cid": row.contribution_id},
    )


def _insert_alias(db: Session, site_id, name: str) -> None:
    db.execute(
        text(f"""
        INSERT INTO unified_site_names (site_id, name, name_normalized, name_type)
        SELECT :site_id, :name, {site_key_sql(":name")}, 'alias'
        WHERE NOT EXISTS (
            SELECT 1 FROM unified_site_names
            WHERE site_id = :site_id AND name_normalized = {site_key_sql(":name")}
        )
        """),
        {"site_id": site_id, "name": name},
    )


@router.post("/{proposal_id}/approve")
def approve_proposal(
    proposal_id: str,
    overrides: PromoteOverrides | None = None,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """Approve into unified_sites. source_id='lyra' per the owner's decision
    (2026-09-14: keep the radar tier as is for now). Founder-merged aliases
    become unified_site_names rows of type 'alias'."""
    row = _load(db, proposal_id)
    _require_open(row)
    item = dict(row._mapping)
    override_dict = overrides.model_dump(exclude_none=True) if overrides else {}
    effective = _apply_overrides(item, override_dict)
    missing = _missing_core_fields(effective)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"message": f"Missing core fields: {', '.join(missing)}", "missing": missing},
        )
    name = override_dict.get("name") or effective["name"]
    period_name = effective.get("period_name")
    if effective.get("period_start") is not None:
        period_name = categorize_period(effective["period_start"])
    site_id = insert_promoted_site(
        db,
        name=name,
        lat=effective["lat"],
        lon=effective["lon"],
        site_type=effective.get("site_type"),
        period_start=effective.get("period_start"),
        period_end=effective.get("period_end"),
        period_name=period_name,
        country=effective.get("country"),
        description=effective.get("description"),
        thumbnail_url=effective.get("thumbnail_url"),
        source_url=effective.get("wikipedia_url"),
        source_id="lyra",
        source_record_id=f"proposal-{proposal_id}",
        edited_by="proposal_approve",
    )
    for alias in row.aliases or []:
        _insert_alias(db, site_id, alias)
    if row.name != name:
        _insert_alias(db, site_id, row.name)
    _stamp(
        db,
        proposal_id,
        "approved",
        user,
        promoted_site_id=site_id,
        review_notes=json.dumps({"overrides": override_dict}) if override_dict else None,
    )
    _mirror_contribution(db, row, enrichment_status="promoted", site_id=site_id)
    db.commit()
    cache_delete_pattern("radar:*")
    cache_delete_pattern("sites:*")
    return {"success": True, "site_id": str(site_id)}


@router.post("/{proposal_id}/merge/{site_id}")
def merge_proposal(
    proposal_id: str,
    site_id: str,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """The candidate IS an existing site: record the name(s) as aliases.

    This and `same-as` are the only paths by which a candidate name ever
    enters unified_site_names, and both are explicit human decisions.
    """
    row = _load(db, proposal_id)
    _require_open(row)
    _require_uuid(site_id, 422, "Invalid site_id")
    site = db.execute(
        text("SELECT id, name FROM unified_sites WHERE id = :sid"), {"sid": site_id}
    ).fetchone()
    if not site:
        raise HTTPException(status_code=404, detail="Target site not found")
    for alias in [row.name, *(row.aliases or [])]:
        _insert_alias(db, site_id, alias)
    _stamp(db, proposal_id, "merged", user, merged_into_site_id=site_id)
    _mirror_contribution(db, row, enrichment_status="matched")
    db.commit()
    cache_delete_pattern("radar:*")
    return {"success": True, "site_id": site_id, "site_name": site.name}


@router.post("/{proposal_id}/same-as/{other_id}")
def same_as(
    proposal_id: str,
    other_id: str,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    """Two proposals name one place ("SU Site" is "Mogollon Village").

    `other` folds into `proposal`: its evidence moves over, its name and
    aliases become aliases here, and it is closed as merged. The pipeline
    never writes aliases; only this decision does.
    """
    if proposal_id == other_id:
        raise HTTPException(status_code=422, detail="A proposal cannot be merged into itself")
    row = _load(db, proposal_id)
    other = _load(db, other_id)
    _require_open(row)
    _require_open(other)
    db.execute(
        text("""
        INSERT INTO site_proposal_evidence
            (proposal_id, corpus, source_table, source_pk, mentioned_as, char_start, char_end,
             quote, quote_start, footnotes, locator, extracted_by)
        SELECT :keep, corpus, source_table, source_pk, mentioned_as, char_start, char_end,
               quote, quote_start, footnotes, locator, extracted_by
        FROM site_proposal_evidence WHERE proposal_id = :gone
        ON CONFLICT DO NOTHING
        """),
        {"keep": proposal_id, "gone": other_id},
    )
    db.execute(
        text("DELETE FROM site_proposal_evidence WHERE proposal_id = :gone"), {"gone": other_id}
    )
    new_aliases = [n for n in [other.name, *(other.aliases or [])] if n != row.name]
    db.execute(
        text("""
        UPDATE site_proposals p SET
            aliases = ARRAY(SELECT DISTINCT unnest(p.aliases || CAST(:new AS text[]))),
            contribution_id = COALESCE(p.contribution_id, :cid),
            evidence_count = (SELECT COUNT(*) FROM site_proposal_evidence e WHERE e.proposal_id = p.id),
            corpus_kinds = (SELECT COALESCE(string_agg(DISTINCT e.corpus, ','), '')
                            FROM site_proposal_evidence e WHERE e.proposal_id = p.id),
            updated_at = NOW()
        WHERE p.id = :keep
        """),
        {"keep": proposal_id, "new": new_aliases, "cid": other.contribution_id},
    )
    _stamp(
        db,
        other_id,
        "merged",
        user,
        review_notes=json.dumps({"merged_into_proposal": proposal_id}),
        evidence_count=0,
        corpus_kinds="",
    )
    _mirror_contribution(db, other, enrichment_status="matched")
    db.commit()
    return {"success": True, "aliases": new_aliases}


class RejectBody(BaseModel):
    note: str | None = None


@router.post("/{proposal_id}/reject")
def reject_proposal(
    proposal_id: str,
    body: RejectBody | None = None,
    user: DiscordUser = Depends(require_founder),
    db: Session = Depends(get_db),
):
    row = _load(db, proposal_id)
    _require_open(row)
    _stamp(db, proposal_id, "rejected", user, review_notes=(body.note if body else None))
    # 'dismissed', not 'rejected': the radar pipeline re-processes 'rejected'
    # rows and would resurrect the card (see radar.py::dismiss_contribution).
    _mirror_contribution(db, row, enrichment_status="dismissed")
    db.commit()
    cache_delete_pattern("radar:*")
    return {"success": True}
