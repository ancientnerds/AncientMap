"""Full-project graph ingestion — the structural layers of the knowledge graph.

Ingests the project's curated knowledge into `research_nodes`/`research_edges`
(spec: docs/superpowers/specs/2026-07-26-full-project-graph-design.md):

- sites:    ancient_nerds originals + radar discoveries
- periods:  12 canonical epochs (same bucketing as the public API)
- countries, empires (Seshat), cultures + persons (from Lyra's pre-extracted
  news entities, >= 2 mentions), stories, videos, channels, journals

Everything is SQL-only (zero LLM tokens), idempotent (upserts on
(kind, norm_label)), and uses status='reference' — the research frontier
picker only consumes status='frontier', so structural knowledge can never
flood the researcher's topic queue. Runs nightly from the worker feeder loop.
"""

from __future__ import annotations

import json
import logging
from collections import Counter

from sqlalchemy import text

from pipeline.lyra.research_graph import normalize_label

logger = logging.getLogger(__name__)

# Canonical epochs — labels match the public API period breakdown so the two
# surfaces never disagree.
_EPOCHS = [
    (-4500, "< 4500 BC"),
    (-3000, "4500 - 3000 BC"),
    (-1500, "3000 - 1500 BC"),
    (-500, "1500 - 500 BC"),
    (1, "500 BC - 1 AD"),
    (500, "1 - 500 AD"),
    (1000, "500 - 1000 AD"),
    (1500, "1000 - 1500 AD"),
]


def epoch_for_year(period_start: int | None) -> str | None:
    """Map a period_start year (negative = BC) to its canonical epoch label."""
    if period_start is None:
        return None
    for upper_bound, label in _EPOCHS:
        if period_start < upper_bound:
            return label
    return "1500+ AD"


def entity_mention_counts(entity_lists: list[list[str]]) -> Counter:
    """Count normalized mentions across stories; the ingest only creates
    person/culture nodes for names mentioned in >= 2 stories (one-off noise
    stays out of the graph)."""
    counts: Counter = Counter()
    for names in entity_lists:
        for name in {normalize_label(n) for n in names if n and len(n.strip()) >= 3}:
            counts[name] += 1
    return counts


class _GraphWriter:
    """Upsert helper with an in-memory (kind, norm_label) -> id map so edge
    creation never needs per-edge lookups."""

    def __init__(self, session):
        self.session = session
        self.node_ids: dict[tuple[str, str], str] = {}
        self.nodes_written = 0
        self.edges_written = 0

    def node(
        self,
        label: str,
        kind: str,
        *,
        status: str = "reference",
        created_from: str = "structure",
        site_id: str | None = None,
        signal: float = 0.0,
    ) -> str | None:
        label = (label or "").strip()
        if len(label) < 2:
            return None
        norm = normalize_label(label)[:500]
        key = (kind, norm)
        cached = self.node_ids.get(key)
        if cached:
            return cached
        row = self.session.execute(
            text("""
                INSERT INTO research_nodes
                    (id, label, norm_label, kind, status, created_from, source_signal,
                     site_id, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :label, :norm_label, :kind, :status, :created_from,
                     :signal, CAST(NULLIF(:site_id, '') AS uuid), NOW(), NOW())
                ON CONFLICT (kind, norm_label) DO UPDATE SET
                    -- keep the existing status (never downgrade frontier/explored),
                    -- refresh the site link when the ingest knows it
                    site_id = COALESCE(research_nodes.site_id, excluded.site_id),
                    updated_at = NOW()
                RETURNING id::text
            """),
            {
                "label": label[:500],
                "norm_label": norm,
                "kind": kind,
                "status": status,
                "created_from": created_from,
                "signal": signal,
                "site_id": site_id or "",
            },
        ).fetchone()
        self.node_ids[key] = row.id
        self.nodes_written += 1
        return row.id

    def edge(self, src: str | None, dst: str | None, kind: str) -> None:
        if not src or not dst or src == dst:
            return
        self.session.execute(
            text("""
                INSERT INTO research_edges (id, src, dst, kind, weight, created_at)
                VALUES (gen_random_uuid(), CAST(:src AS uuid), CAST(:dst AS uuid),
                        :kind, 1.0, NOW())
                ON CONFLICT (src, dst, kind) DO NOTHING
            """),
            {"src": src, "dst": dst, "kind": kind},
        )
        self.edges_written += 1


def _ingest_sites(w: _GraphWriter) -> None:
    """AN originals with period/country edges, plus radar discoveries."""
    rows = w.session.execute(
        text("""
            SELECT id::text AS site_id, name, country, period_start
            FROM unified_sites
            WHERE source_id = 'ancient_nerds' AND name IS NOT NULL
        """)
    ).fetchall()
    for r in rows:
        node = w.node(r.name, "site", created_from="structure", site_id=r.site_id)
        epoch = epoch_for_year(r.period_start)
        if epoch:
            w.edge(node, w.node(epoch, "period"), "dated_to")
        if r.country:
            w.edge(node, w.node(r.country, "country"), "located_in")

    radar = w.session.execute(
        text("""
            SELECT COALESCE(corrected_name, name) AS name, country
            FROM user_contributions
            WHERE source = 'lyra' AND enrichment_status IN ('enriched', 'promoted')
        """)
    ).fetchall()
    for r in radar:
        node = w.node(r.name, "site", created_from="radar")
        if r.country:
            w.edge(node, w.node(r.country, "country"), "located_in")


def _ingest_empires(w: _GraphWriter) -> None:
    """Seshat polities. Uses the api-side loader (this module only ever runs
    inside the api container's worker — the lyra container never calls it)."""
    from api.routes.public_v1 import _POLITIES

    for pid, p in _POLITIES.items():
        node = w.node(p.get("name", pid), "empire", created_from="structure")
        epoch = epoch_for_year(p.get("startYear"))
        if epoch:
            w.edge(node, w.node(epoch, "period"), "dated_to")


def _ingest_content(w: _GraphWriter) -> None:
    """Stories, videos, channels, journals + person/culture entities."""
    channels = w.session.execute(
        text("SELECT id, name FROM news_channels WHERE enabled = true")
    ).fetchall()
    channel_nodes = {c.id: w.node(c.name, "channel", created_from="structure") for c in channels}

    videos = w.session.execute(
        text("SELECT id, title, channel_id FROM news_videos WHERE title IS NOT NULL")
    ).fetchall()
    video_nodes: dict[str, str | None] = {}
    for v in videos:
        node = w.node(v.title, "video", created_from="story")
        video_nodes[v.id] = node
        w.edge(node, channel_nodes.get(v.channel_id), "on_channel")

    # Site nodes by unified_sites id — for the direct story->site FK edges.
    site_by_id = {
        r.site_id: r.id
        for r in w.session.execute(
            text("""
                SELECT id::text AS id, site_id::text AS site_id
                FROM research_nodes WHERE kind = 'site' AND site_id IS NOT NULL
            """)
        ).fetchall()
    }

    stories = w.session.execute(
        text("""
            SELECT id, headline, site_id::text AS site_id, video_id, entities
            FROM news_items WHERE headline IS NOT NULL
        """)
    ).fetchall()

    # Pass 1: mention counts across all stories (>=2 gate for person/culture).
    people_lists: list[list[str]] = []
    culture_lists: list[list[str]] = []
    parsed: dict[int, dict] = {}
    for s in stories:
        ents = s.entities if isinstance(s.entities, dict) else {}
        if isinstance(s.entities, str):
            try:
                ents = json.loads(s.entities)
            except (json.JSONDecodeError, TypeError):
                ents = {}
        parsed[s.id] = ents
        people_lists.append(ents.get("people") or [])
        culture_lists.append(ents.get("cultures") or [])
    people_ok = {n for n, c in entity_mention_counts(people_lists).items() if c >= 2}
    cultures_ok = {n for n, c in entity_mention_counts(culture_lists).items() if c >= 2}

    for s in stories:
        node = w.node(s.headline, "story", created_from="story")
        if s.site_id and s.site_id in site_by_id:
            w.edge(node, site_by_id[s.site_id], "mentions")
        if s.video_id in video_nodes:
            w.edge(node, video_nodes[s.video_id], "from_video")
        ents = parsed.get(s.id, {})
        for person in ents.get("people") or []:
            if normalize_label(person) in people_ok:
                w.edge(node, w.node(person, "person", created_from="story"), "mentions")
        for culture in ents.get("cultures") or []:
            if normalize_label(culture) in cultures_ok:
                w.edge(node, w.node(culture, "culture", created_from="story"), "mentions")
        # Entity-extracted site names that match an existing site/topic node —
        # unmatched names are skipped on purpose (no junk nodes).
        for site_name in ents.get("sites") or []:
            key = ("site", normalize_label(site_name)[:500])
            if key in w.node_ids:
                w.edge(node, w.node_ids[key], "mentions")

    journals = w.session.execute(
        text("SELECT title, video_ids FROM news_articles WHERE title IS NOT NULL")
    ).fetchall()
    for j in journals:
        node = w.node(j.title, "journal", created_from="journal")
        for vid in j.video_ids or []:
            w.edge(node, video_nodes.get(vid), "covers")


def run_full_ingest() -> dict[str, int]:
    """Run the complete structural ingestion. Never raises — the worker
    feeder loop must survive any single failure; each layer commits
    separately so a late failure keeps earlier layers."""
    stats: dict[str, int] = {}
    try:
        from pipeline.database import get_session

        with get_session() as session:
            w = _GraphWriter(session)
            for name, fn in (
                ("sites", _ingest_sites),
                ("empires", _ingest_empires),
                ("content", _ingest_content),
            ):
                try:
                    fn(w)
                    session.commit()
                    stats[name] = w.nodes_written
                except Exception as exc:  # noqa: BLE001 — per-layer isolation
                    session.rollback()
                    logger.error("[GRAPH] Full ingest layer %r failed: %s", name, exc)
            stats["nodes_total"] = w.nodes_written
            stats["edges_total"] = w.edges_written
        logger.info("[GRAPH] Full ingest done: %s", stats)
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.error("[GRAPH] Full ingest failed: %s", exc)
    return stats
