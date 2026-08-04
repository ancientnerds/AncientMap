"""Structural connection mining on the research + project graph (spec §2).

Candidates come from DATA (graph topology, PostGIS geometry), never from
Theo's own prose — that is the structural half of the echo-chamber defense.
The curator (LLM) ranks and turns the survivors into frontier questions.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

_REFERENCE_KINDS = "('culture', 'person', 'period', 'country', 'empire')"


def mine_link_prediction(session, limit: int = 20) -> list:
    """Explored topic/site pairs sharing >=2 reference neighbors but no
    direct edge — the classic 'nobody drew this line yet' signal."""
    return session.execute(
        text(f"""
            WITH neigh AS (
                SELECT src AS a, dst AS b FROM research_edges
                UNION
                SELECT dst AS a, src AS b FROM research_edges
            )
            SELECT n1.label AS a_label, n2.label AS b_label,
                   COUNT(*) AS shared,
                   ARRAY_AGG(rn.label ORDER BY rn.label) AS via
            FROM neigh x
            JOIN neigh y ON y.b = x.b AND x.a < y.a
            JOIN research_nodes n1 ON n1.id = x.a
                 AND n1.status = 'explored' AND n1.kind IN ('topic', 'site')
            JOIN research_nodes n2 ON n2.id = y.a
                 AND n2.status = 'explored' AND n2.kind IN ('topic', 'site')
            JOIN research_nodes rn ON rn.id = x.b AND rn.kind IN {_REFERENCE_KINDS}
            WHERE NOT EXISTS (
                SELECT 1 FROM neigh d WHERE d.a = x.a AND d.b = y.a
            )
            GROUP BY n1.label, n2.label
            HAVING COUNT(*) >= 2
            ORDER BY COUNT(*) DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).fetchall()


def mine_spatial_cooccurrence(session, max_km: int = 200, limit: int = 20) -> list:
    """Explored sites that are geographically close AND temporally
    overlapping, with no graph edge between them."""
    return session.execute(
        text("""
            SELECT n1.label AS a_label, n2.label AS b_label,
                   ROUND(ST_DistanceSphere(
                       ST_MakePoint(s1.lon, s1.lat),
                       ST_MakePoint(s2.lon, s2.lat)) / 1000) AS km
            FROM research_nodes n1
            JOIN research_nodes n2 ON n1.id < n2.id
            JOIN unified_sites s1 ON s1.id = n1.site_id
            JOIN unified_sites s2 ON s2.id = n2.site_id
            WHERE n1.status = 'explored' AND n2.status = 'explored'
              AND ST_DistanceSphere(
                      ST_MakePoint(s1.lon, s1.lat),
                      ST_MakePoint(s2.lon, s2.lat)) < :max_m
              AND s1.period_start IS NOT NULL AND s2.period_start IS NOT NULL
              AND s1.period_start <= COALESCE(s2.period_end, s2.period_start)
              AND s2.period_start <= COALESCE(s1.period_end, s1.period_start)
              AND NOT EXISTS (
                  SELECT 1 FROM research_edges e
                  WHERE (e.src = n1.id AND e.dst = n2.id)
                     OR (e.src = n2.id AND e.dst = n1.id)
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


def merge_candidates(
    link_rows: list, spatial_rows: list, tension_rows: list | None = None, cap: int = 15
) -> list[dict]:
    """Pure merge: format, drop self-pairs, strongest first, cap."""
    out: list[dict] = []
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
    for r in tension_rows or []:
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
        candidates = merge_candidates(links, spatial, tensions)
        log_thinking(
            "miner",
            f"Miner: {len(candidates)} connection candidates "
            f"({len(links)} link, {len(spatial)} spatial, {len(tensions)} tension)",
            {"candidates": [c["label"] for c in candidates]},
        )
        return candidates
    except Exception as exc:  # noqa: BLE001 — thinking must never kill the feeder
        logger.error("[THINK] miner failed: %s", exc)
        return []
