"""Source injectors — seed the research knowledge graph from live content.

Each injector turns an existing content stream into `frontier` nodes so the
permanent researcher's topic engine can pick them up:

- stories:  site names extracted from recent Lyra news items (signal = mentions)
- journal:  latest weekly digest titles
- sites:    high-rarity map sites (card_stats Epic/Legendary) without a paper
- radar:    Lyra auto-discovered sites by mention count

All writes dedupe on ``(kind, norm_label)`` — re-running injectors never
duplicates nodes. A collision accumulates ``source_signal`` and, since
2026-08-04, promotes a colliding ``reference`` node to ``frontier`` (the
2026-08 full-project ingest wrote 5,307 site nodes as ``reference``; without
this promotion an injected site never became researchable). It never
demotes or otherwise touches an already-frontier/researching/explored
node's status. `run_all_injectors()` is called hourly by the worker feeder
loop and must never raise.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from pipeline.lyra.research_graph import is_junk_label, normalize_label

logger = logging.getLogger(__name__)


def _insert_frontier(
    session,
    label: str,
    created_from: str,
    signal: float,
    kind: str = "topic",
    site_id: str | None = None,
) -> bool:
    """Upsert one frontier node; returns True when the node is new.

    Existing frontier/researching/explored nodes just accumulate signal — an
    explored topic getting fresh story mentions raises its neighbors' scores
    via edges without ever re-entering the frontier itself. A colliding
    ``reference`` node (the full-project ingest's default status, e.g. for
    site records) is the one status this DOES promote to ``frontier``:
    that promotion is the entire point of an injection signal landing on a
    structural-only node — it turns a reference into a research candidate.
    """
    label = (label or "").strip()
    if len(label) < 4 or is_junk_label(label):
        return False
    # Raw SQL bypasses SQLAlchemy Python-side defaults — supply all NOT NULL
    # columns explicitly.
    row = session.execute(
        text("""
            INSERT INTO research_nodes
                (id, label, norm_label, kind, status, created_from, source_signal,
                 site_id, created_at, updated_at)
            VALUES
                (gen_random_uuid(), :label, :norm_label, :kind, 'frontier', :created_from,
                 :signal, CAST(NULLIF(:site_id, '') AS uuid), NOW(), NOW())
            ON CONFLICT (kind, norm_label) DO UPDATE SET
                source_signal = research_nodes.source_signal + excluded.source_signal,
                status = CASE
                    WHEN research_nodes.status = 'reference' THEN 'frontier'
                    ELSE research_nodes.status
                END,
                site_id = COALESCE(research_nodes.site_id, excluded.site_id),
                updated_at = NOW()
            RETURNING (xmax = 0) AS is_new
        """),
        {
            "label": label[:500],
            "norm_label": normalize_label(label)[:500],
            "kind": kind,
            "created_from": created_from,
            "signal": signal,
            "site_id": site_id or "",
        },
    ).fetchone()
    return bool(row.is_new)


def inject_from_stories(session, days: int = 7) -> int:
    """Site names mentioned in recent news items; signal = mention count."""
    rows = session.execute(
        text("""
            SELECT site_name_extracted AS name, COUNT(*) AS mentions
            FROM news_items
            WHERE site_name_extracted IS NOT NULL
              AND created_at > NOW() - (:days * INTERVAL '1 day')
            GROUP BY site_name_extracted
            ORDER BY mentions DESC
            LIMIT 30
        """),
        {"days": days},
    ).fetchall()
    return sum(_insert_frontier(session, r.name, "story", float(r.mentions)) for r in rows)


def inject_from_journal(session) -> int:
    """Titles of the two most recent weekly digests."""
    rows = session.execute(
        text("""
            SELECT title FROM news_articles
            WHERE title IS NOT NULL
            ORDER BY published_at DESC NULLS LAST
            LIMIT 2
        """)
    ).fetchall()
    return sum(_insert_frontier(session, r.title, "journal", 1.0) for r in rows)


def inject_from_sites(session, limit: int = 20) -> int:
    """Epic/Legendary map sites — strongest product tie-in for papers."""
    rows = session.execute(
        text("""
            SELECT us.id::text AS site_id, us.name, cs.rarity_tier
            FROM card_stats cs
            JOIN unified_sites us ON us.id = cs.site_id
            WHERE cs.rarity_tier >= 4
            ORDER BY cs.total_power DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()
    return sum(
        _insert_frontier(
            session,
            r.name,
            "site",
            float(r.rarity_tier - 3),
            kind="site",
            site_id=r.site_id,
        )
        for r in rows
    )


def inject_from_radar(session, limit: int = 20) -> int:
    """Lyra auto-discovered sites, weighted by video mention count."""
    rows = session.execute(
        text("""
            SELECT COALESCE(corrected_name, name) AS name, mention_count
            FROM user_contributions
            WHERE source = 'lyra'
              AND enrichment_status IN ('enriched', 'promoted')
            ORDER BY mention_count DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()
    return sum(
        _insert_frontier(session, r.name, "story", min(float(r.mention_count), 5.0)) for r in rows
    )


def run_all_injectors() -> dict[str, int]:
    """Run every injector in one session. Never raises — the feeder loop
    must keep running even when one content table is empty or renamed."""
    counts: dict[str, int] = {}
    try:
        from pipeline.database import get_session

        with get_session() as session:
            counts["stories"] = inject_from_stories(session)
            counts["journal"] = inject_from_journal(session)
            counts["sites"] = inject_from_sites(session)
            counts["radar"] = inject_from_radar(session)
            session.commit()
        logger.info("[GRAPH] Injectors: %s new frontier nodes", counts)
    except Exception as exc:  # noqa: BLE001 — feeder loop must survive (see docstring)
        logger.error("[GRAPH] Injector run failed: %s", exc)
    return counts
