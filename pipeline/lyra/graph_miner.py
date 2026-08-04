"""Structural connection mining on the research + project graph (spec §2).

Candidates come from DATA (graph topology, PostGIS geometry, world-model
status), never from Theo's own prose — that is the structural half of the
echo-chamber defense. The curator (LLM) ranks and turns the survivors into
frontier questions.

Redesigned 2026-08-04 after a prod-evidence review replayed the original
queries against the live graph (13,148 nodes / 21,583 edges) and found both
structural miners returned 0 rows, permanently:
- explored `topic` nodes only ever neighbor `paper` nodes, never
  culture/person/period/country/empire reference nodes;
- ALL `site` nodes are status='reference' — the injector upsert path never
  transitions a site node to 'explored';
- no explored node carries `site_id` (only `site` nodes do).

Fix: bridge an explored `topic` node to its structural `site` twin via a
shared `norm_label` (78 such cross-kind labels exist in prod). No new edges,
no status changes — the bridge is a join, not a graph mutation.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from pipeline.lyra.research_graph import normalize_label

logger = logging.getLogger(__name__)

# Per-miner quotas, applied BEFORE the global cap in merge_candidates(). The
# link miner is dense and sorts first; without a quota it would fill the
# whole cap and crowd out the thinner spatial/tension signals.
LINK_QUOTA = 7
SPATIAL_QUOTA = 5
TENSION_QUOTA = 3


def mine_link_prediction(session, limit: int = 20) -> list:
    """Explored topics sharing >=2 CONTENT neighbors (story/culture/person)
    via their bridged site twin, with no direct edge between the topics.

    country/period reference kinds are deliberately EXCLUDED from the shared-
    neighbor set: measured on prod, every same-country-same-epoch site pair
    ties at shared=2 (206,659 pairs) — country/period carry no discriminating
    signal here, only noise that would swamp the real candidates.

    GROUP BY topic ids (not labels): 78 duplicate labels exist across kinds
    in prod (the very bridge this query relies on), so grouping by label
    alone would collapse distinct topic pairs into one row.
    """
    return session.execute(
        text("""
            WITH bridged AS (
                SELECT n_topic.id AS topic_id, n_topic.label AS label, n_site.id AS site_node
                FROM research_nodes n_topic
                JOIN research_nodes n_site
                  ON n_site.kind = 'site' AND n_site.norm_label = n_topic.norm_label
                WHERE n_topic.status = 'explored' AND n_topic.kind = 'topic'
            ),
            neigh AS (
                SELECT src AS a, dst AS b FROM research_edges
                UNION
                SELECT dst AS a, src AS b FROM research_edges
            )
            SELECT b1.label AS a_label, b2.label AS b_label,
                   COUNT(DISTINCT x.b) AS shared,
                   ARRAY_AGG(DISTINCT rn.label) AS via
            FROM bridged b1
            JOIN neigh x ON x.a = b1.site_node
            JOIN bridged b2 ON b2.topic_id > b1.topic_id AND b2.site_node <> b1.site_node
            JOIN neigh y ON y.a = b2.site_node AND y.b = x.b
            JOIN research_nodes rn ON rn.id = x.b AND rn.kind IN ('story', 'culture', 'person')
            WHERE NOT EXISTS (
                SELECT 1 FROM neigh d WHERE d.a = b1.topic_id AND d.b = b2.topic_id
            )
            GROUP BY b1.topic_id, b2.topic_id, b1.label, b2.label
            HAVING COUNT(DISTINCT x.b) >= 2
            ORDER BY COUNT(DISTINCT x.b) DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()


def mine_spatial_cooccurrence(session, max_km: int = 200, limit: int = 20) -> list:
    """Explored topics whose bridged site twin is geographically close AND
    temporally overlapping to another explored topic's site twin, with no
    graph edge between the two topics.

    LEAST/GREATEST on the period bounds handles the 16 inverted
    period_start/period_end rows found in prod. The population here is only
    researched (explored) sites — tiny — so the doubled ST_DistanceSphere
    call (once in SELECT, once in WHERE) is irrelevant for cost.
    """
    return session.execute(
        text("""
            WITH researched_sites AS (
                SELECT n_topic.id AS topic_id, n_site.label AS label,
                       s.lat, s.lon,
                       LEAST(s.period_start, COALESCE(s.period_end, s.period_start)) AS p_lo,
                       GREATEST(s.period_start, COALESCE(s.period_end, s.period_start)) AS p_hi
                FROM research_nodes n_topic
                JOIN research_nodes n_site
                  ON n_site.kind = 'site' AND n_site.norm_label = n_topic.norm_label
                JOIN unified_sites s ON s.id = n_site.site_id
                WHERE n_topic.status = 'explored' AND n_topic.kind = 'topic'
                  AND s.period_start IS NOT NULL
            )
            SELECT a.label AS a_label, b.label AS b_label,
                   ROUND(ST_DistanceSphere(ST_MakePoint(a.lon, a.lat),
                                           ST_MakePoint(b.lon, b.lat)) / 1000) AS km
            FROM researched_sites a
            JOIN researched_sites b ON a.topic_id < b.topic_id
            WHERE ST_DistanceSphere(ST_MakePoint(a.lon, a.lat),
                                    ST_MakePoint(b.lon, b.lat)) < :max_m
              AND a.p_lo <= b.p_hi AND b.p_lo <= a.p_hi
              AND NOT EXISTS (
                  SELECT 1 FROM research_edges e
                  WHERE (e.src = a.topic_id AND e.dst = b.topic_id)
                     OR (e.src = b.topic_id AND e.dst = a.topic_id)
              )
            ORDER BY km ASC
            LIMIT :limit
        """),
        {"max_m": max_km * 1000, "limit": limit},
    ).fetchall()


def mine_contested_claims(session, limit: int = 10) -> list:
    """World-model tensions: contested claims are re-research candidates —
    the third miner source from spec §2 (conflict detector, claims level)."""
    return session.execute(
        text("""
            SELECT c.text AS claim_text, n.label AS node_label
            FROM knowledge_claims c
            LEFT JOIN research_nodes n ON n.id = c.node_id
            WHERE c.status = 'contested'
            ORDER BY c.confidence DESC, c.updated_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()


def _pair_norm_keys(label: str) -> tuple[str, str]:
    """Both normalized orderings of a 'A ↔ B' pair label, for cross-miner
    dedup and suppression against already-promoted connection nodes."""
    if "↔" not in label:
        norm = normalize_label(label)
        return norm, norm
    a, b = (p.strip() for p in label.split("↔", 1))
    return normalize_label(f"{a} ↔ {b}"), normalize_label(f"{b} ↔ {a}")


def _link_candidates(link_rows: list) -> list[dict]:
    out = []
    for r in sorted(link_rows, key=lambda r: -r.shared):
        if r.a_label == r.b_label:
            continue
        out.append(
            {
                "label": f"{r.a_label} ↔ {r.b_label}",
                "miner": "link",
                "evidence": (
                    f"{r.shared} shared reference neighbors "
                    f"({', '.join(list(r.via)[:4])}), no direct link researched"
                ),
            }
        )
    return out


def _spatial_candidates(spatial_rows: list) -> list[dict]:
    out = []
    for r in spatial_rows:
        if r.a_label == r.b_label:
            continue
        out.append(
            {
                "label": f"{r.a_label} ↔ {r.b_label}",
                "miner": "spatial",
                "evidence": f"{int(r.km)} km apart, overlapping periods, no researched link",
            }
        )
    return out


def _tension_candidates(tension_rows: list) -> list[dict]:
    out = []
    for r in tension_rows:
        label = (r.node_label or r.claim_text[:80]).strip()
        if not label:
            continue
        out.append(
            {
                "label": label,
                "miner": "tension",
                "evidence": f"world model marks this contested: {r.claim_text[:200]}",
            }
        )
    return out


def merge_candidates(
    link_rows: list,
    spatial_rows: list,
    tension_rows: list | None = None,
    cap: int = 15,
    existing_connection_norms: frozenset = frozenset(),
) -> list[dict]:
    """Pure merge: format, drop self-pairs, quota per miner, cross-miner
    dedup, suppress already-promoted connections, strongest first, cap."""
    link_c = _link_candidates(link_rows)[:LINK_QUOTA]
    spatial_c = _spatial_candidates(spatial_rows)[:SPATIAL_QUOTA]
    tension_c = _tension_candidates(tension_rows or [])[:TENSION_QUOTA]

    out: list[dict] = []
    seen_pair_norms: set[str] = set()

    for c in link_c + spatial_c:
        fwd, rev = _pair_norm_keys(c["label"])
        if fwd in existing_connection_norms or rev in existing_connection_norms:
            continue
        if fwd in seen_pair_norms or rev in seen_pair_norms:
            continue
        seen_pair_norms.add(fwd)
        out.append(c)

    for c in tension_c:
        if normalize_label(c["label"]) in existing_connection_norms:
            continue
        out.append(c)

    return out[:cap]


def run_miner() -> list[dict]:
    """Collect candidates from all miners. Best-effort (injector pattern)."""
    try:
        from pipeline.database import get_session
        from pipeline.lyra.thinking_log import log_thinking

        with get_session() as session:
            links = mine_link_prediction(session)
            spatial = mine_spatial_cooccurrence(session)
            tensions = mine_contested_claims(session)
            existing_connection_norms = {
                row.norm_label
                for row in session.execute(
                    text("SELECT norm_label FROM research_nodes WHERE kind = 'connection'")
                ).fetchall()
            }
        candidates = merge_candidates(
            links, spatial, tensions, existing_connection_norms=existing_connection_norms
        )
        log_thinking(
            "miner",
            f"Miner: {len(candidates)} connection candidates "
            f"({len(links)} link, {len(spatial)} spatial, {len(tensions)} tension)",
            {"candidates": [c["label"] for c in candidates]},
        )
        return candidates
    except Exception as exc:  # noqa: BLE001 — thinking must never kill the feeder
        logger.error("[THINK] miner failed: %s", exc, exc_info=True)
        return []
