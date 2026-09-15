"""Hard identifiers for the curated set: enwiki title + Wikidata QID.

4,632 of the 5,004 ancient_nerds rows carry an English-Wikipedia source_url
(0 carry a wikidata.org URL). Every title goes through the SAME
redirect-following batch call the candidates use (pipeline.lyra.prospector.
wiki.resolve_titles), which is what makes rung 0 of the dedup ladder
symmetric. Writes ONLY to site_external_ids — never to unified_site_names,
the table caption_garble poisoned.

Idempotent: re-running resolves only sites with no row yet unless
`only_missing=False`.
"""

from __future__ import annotations

import logging

from sqlalchemy import text as sql

from pipeline.lyra.prospector.wiki import enwiki_title_from_url, resolve_titles

logger = logging.getLogger(__name__)


def refresh_site_external_ids(session, *, only_missing: bool = True) -> dict[str, int]:
    """Resolve curated Wikipedia titles and upsert their canonical title + QID.

    Returns counts: sites considered, resolved (page exists), missing
    (no such page after redirects), rows written.
    """
    where = "source_id = 'ancient_nerds' AND source_url LIKE 'https://en.wikipedia.org/wiki/%'"
    if only_missing:
        where += " AND NOT EXISTS (SELECT 1 FROM site_external_ids e WHERE e.site_id = us.id)"
    rows = session.execute(
        sql(f"SELECT us.id::text AS id, us.source_url FROM unified_sites us WHERE {where}")
    ).fetchall()

    by_title: dict[str, list[str]] = {}
    for r in rows:
        title = enwiki_title_from_url(r.source_url)
        if title:
            by_title.setdefault(title, []).append(r.id)

    resolutions = resolve_titles(list(by_title))
    written = resolved = missing = 0
    for title, site_ids in by_title.items():
        res = resolutions.get(title)
        if res is None or not res.exists:
            missing += 1
            continue
        resolved += 1
        for site_id in site_ids:
            written += _upsert(session, site_id, "enwiki_title", res.canonical_title)
            if res.qid:
                written += _upsert(session, site_id, "wikidata_qid", res.qid)

    session.flush()
    counts = {
        "sites": len(rows),
        "titles": len(by_title),
        "resolved": resolved,
        "missing": missing,
        "rows_written": written,
    }
    logger.info("[PROSPECTOR] site_external_ids refresh: %s", counts)
    return counts


def _upsert(session, site_id: str, kind: str, value: str) -> int:
    res = session.execute(
        sql("""
        INSERT INTO site_external_ids (site_id, kind, value)
        VALUES (CAST(:site_id AS uuid), :kind, :value)
        ON CONFLICT DO NOTHING
        """),
        {"site_id": site_id, "kind": kind, "value": value},
    )
    return res.rowcount or 0


def refresh_token_df(session) -> int:
    """Rebuild site_name_token_df from unified_site_names (one pass)."""
    res = session.execute(
        sql("""
        INSERT INTO site_name_token_df (token, df)
        SELECT t, COUNT(*)
        FROM unified_site_names, unnest(string_to_array(name_normalized, ' ')) AS t
        WHERE t <> ''
        GROUP BY t
        ON CONFLICT (token) DO UPDATE SET df = EXCLUDED.df, built_at = NOW()
        """)
    )
    return res.rowcount or 0
