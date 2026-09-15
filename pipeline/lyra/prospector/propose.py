"""Stage 4: write proposals + evidence.

One proposal per real-world place: keyed on the QID when there is one, the
enwiki title otherwise, and (name key, country) as the last resort — country
scoped so two real "Glenwood"s stay two cards, but tolerant of an UNKNOWN
country on either side so a card whose country was learned later does not
spawn a twin. Evidence rows are appended and deduplicated on (source,
char_start); `evidence_count` is DERIVED with count(*) on every touch, never
incremented (mention_count reached 34,061 against 2,464 real items that way).

A proposal a human has already decided (approved / merged / rejected) is
never re-opened by the pipeline; it only gains evidence. `aliases` is never
touched here — only a founder merging two proposals writes it.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text as sql

from pipeline.lyra.prospector.dedup import Verdict, gate_country
from pipeline.lyra.prospector.resolve import Resolution
from pipeline.lyra.site_key import site_key_sql
from pipeline.utils.text import categorize_period, clean_description

if TYPE_CHECKING:
    from pipeline.lyra.prospector.mentions import Mention
    from pipeline.lyra.prospector.pipeline import EvidenceRef

logger = logging.getLogger(__name__)

HUMAN_STATUSES = {"approved", "merged", "rejected"}


def derive_status(place_class: str, res: Resolution | None, verdict: Verdict | None) -> str:
    if place_class != "site":
        return "not_a_place"
    if res is not None and res.verdict in {"not_a_place", "area_not_point", "region", "off_earth"}:
        return "not_a_place"
    if res is not None and res.verdict == "resolved" and not res.in_scope:
        return "out_of_scope"
    if verdict is None:
        return "new"
    return {"have_it": "have_it", "needs_decision": "needs_decision"}.get(verdict.verdict, "new")


def paper_locator(slug: str, quote: str) -> str:
    """Deep link that lands on the sentence: /research/{slug}#:~:text=..."""
    fragment = urllib.parse.quote(quote[:40], safe="")
    return f"/research/{slug}#:~:text={fragment}"


def _name_key(session, name: str) -> str:
    return session.execute(sql(f"SELECT {site_key_sql(':raw')}"), {"raw": name}).scalar()


def _find_existing(session, *, qid, enwiki_title, name_key, country) -> uuid.UUID | None:
    if qid:
        row = session.execute(
            sql("SELECT id FROM site_proposals WHERE wikidata_qid = :q"), {"q": qid}
        ).fetchone()
        if row:
            return row.id
    if enwiki_title:
        row = session.execute(
            sql("SELECT id FROM site_proposals WHERE enwiki_title = :t"), {"t": enwiki_title}
        ).fetchone()
        if row:
            return row.id
    row = session.execute(
        sql("""SELECT id FROM site_proposals
               WHERE wikidata_qid IS NULL AND enwiki_title IS NULL
                 AND name_key = :k
                 AND (country IS NULL OR CAST(:c AS text) IS NULL OR country = :c)
               ORDER BY (country = :c) DESC NULLS LAST, first_seen_at
               LIMIT 1"""),
        {"k": name_key, "c": country},
    ).fetchone()
    return row.id if row else None


def upsert_proposal(
    session,
    *,
    name: str,
    place_class: str,
    res: Resolution | None,
    verdict: Verdict | None,
    country_in_text: str | None,
    period_phrase: str | None,
    contribution_id: str | None = None,
    prior_verdict: str | None = None,
) -> uuid.UUID:
    """Create or update the proposal for `name`. Returns its id."""
    country = gate_country(res.country if res else None, country_in_text)
    name_key = _name_key(session, name)
    resolved = res is not None and res.verdict == "resolved"
    qid = res.qid if resolved else None
    enwiki = res.canonical_title if resolved else None
    status = derive_status(place_class, res, verdict)

    ext = verdict.external if verdict else None
    lat = lon = None
    rung = "none"
    precision = None
    if resolved and res.has_point:
        lat, lon, precision = res.lat, res.lon, res.coord_precision
        rung = res.path if res.path == "contribution" else "wikidata_p625"
    elif ext and ext.get("enrich") and ext.get("lat") is not None:
        lat, lon, rung = ext["lat"], ext["lon"], f"external:{ext['source_id']}"

    site_type = (res.site_type if res else None) or (
        ext.get("site_type") if ext and ext.get("enrich") else None
    )
    period_start = res.period_start if res else None
    period_end = res.period_end if res else None
    period_name = categorize_period(period_start) if period_start is not None else None

    fields = {
        "name": name,
        "name_key": name_key,
        "resolved_label": res.label if res else None,
        "wikidata_qid": qid,
        "enwiki_title": enwiki,
        "place_class": place_class,
        "lat": lat,
        "lon": lon,
        "coord_precision": precision,
        "location_rung": rung,
        "country": country,
        "country_in_text": country_in_text,
        "site_type": site_type,
        "period_start": period_start,
        "period_end": period_end,
        "period_name": period_name,
        "period_phrase": period_phrase,
        "description": clean_description(res.description) if res else None,
        "thumbnail_url": res.thumbnail_url if res else None,
        "source_url": res.wikipedia_url if res else None,
        "wikipedia_url": res.wikipedia_url if res else None,
        "dedup_verdict": verdict.verdict if verdict else "not_run",
        "dedup_trace": json.dumps(
            verdict.trace if verdict else [], ensure_ascii=False, default=str
        ),
        "scope_verdict": "in_scope" if (res is None or res.in_scope) else "out_of_scope",
        "resolution_note": res.note if res else None,
        "resolution_path": res.path if res else None,
        "an_site_id": verdict.an_site_id if verdict else None,
        "external_site_id": ext["site_id"] if ext else None,
        "external_source_id": ext["source_id"] if ext else None,
        "prior_verdict": prior_verdict,
    }

    existing = _find_existing(
        session, qid=qid, enwiki_title=enwiki, name_key=name_key, country=country
    )
    if existing is None:
        pid = uuid.uuid4()
        cols = ", ".join([*fields, "contribution_id"])
        vals = ", ".join([*(_bind(k) for k in fields), ":contribution_id"])
        session.execute(
            sql(f"INSERT INTO site_proposals (id, status, {cols}) VALUES (:id, :status, {vals})"),
            {"id": pid, "status": status, "contribution_id": contribution_id, **fields},
        )
    else:
        pid = existing
        current = session.execute(
            sql("SELECT status FROM site_proposals WHERE id = :id"), {"id": pid}
        ).scalar()
        sets = ", ".join(f"{k} = {_bind(k)}" for k in fields)
        status_set = "" if current in HUMAN_STATUSES else ", status = :status"
        session.execute(
            sql(
                f"UPDATE site_proposals SET {sets}{status_set}, "
                f"contribution_id = COALESCE(contribution_id, :contribution_id), "
                f"updated_at = NOW() WHERE id = :id"
            ),
            {"id": pid, "status": status, "contribution_id": contribution_id, **fields},
        )
    session.execute(
        sql("""UPDATE site_proposals
               SET geom = CASE WHEN lat IS NOT NULL AND lon IS NOT NULL
                               THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326) END
               WHERE id = :id"""),
        {"id": pid},
    )
    return pid


def _bind(k: str) -> str:
    return "CAST(:dedup_trace AS jsonb)" if k == "dedup_trace" else f":{k}"


def add_evidence(session, proposal_id: uuid.UUID, items: list[tuple[Mention, EvidenceRef]]) -> int:
    """Append evidence rows (idempotent) and re-derive the counters."""
    added = 0
    for m, ref in items:
        res = session.execute(
            sql("""
            INSERT INTO site_proposal_evidence
                (proposal_id, corpus, source_table, source_pk, mentioned_as,
                 char_start, char_end, quote, quote_start, footnotes, locator, extracted_by)
            VALUES (:pid, :corpus, :table, :pk, :as, :s, :e, :quote, :qs, :fn, :loc, :by)
            ON CONFLICT DO NOTHING
            """),
            {
                "pid": proposal_id,
                "corpus": ref.corpus,
                "table": ref.source_table,
                "pk": ref.source_pk,
                "as": m.name,
                "s": m.char_start,
                "e": m.char_end,
                "quote": m.quote,
                "qs": m.quote_start,
                "fn": m.footnotes or None,
                "loc": ref.locator,
                "by": ref.extracted_by,
            },
        )
        added += res.rowcount or 0
    refresh_counters(session, proposal_id)
    return added


def refresh_counters(session, proposal_id: uuid.UUID) -> None:
    session.execute(
        sql("""
        UPDATE site_proposals p SET
            evidence_count = (SELECT COUNT(*) FROM site_proposal_evidence e WHERE e.proposal_id = p.id),
            corpus_kinds = (SELECT COALESCE(string_agg(DISTINCT e.corpus, ','), '')
                            FROM site_proposal_evidence e WHERE e.proposal_id = p.id)
        WHERE p.id = :id
        """),
        {"id": proposal_id},
    )
