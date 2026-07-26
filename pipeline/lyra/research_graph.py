"""Research knowledge graph — builder, persistence, and frontier topic engine.

The graph doubles as the permanent researcher's brain (2026-07-26 design):
`frontier` nodes are candidate topics, the worker feeder promotes the best
one to `researching`, a completed paper marks it `explored` and contributes
new frontier nodes from its unexplored rabbit holes.

Spec: docs/superpowers/specs/2026-07-26-permanent-researcher-design.md
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

_PUNCT_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_label(label: str) -> str:
    """Canonical form for node dedupe: lowercase, punctuation stripped,
    whitespace collapsed. Hyphens survive (Ein-Sof, Göbekli-Tepe)."""
    cleaned = _PUNCT_RE.sub(" ", label.lower())
    return _WS_RE.sub(" ", cleaned).strip()


def build_graph_from_state(state: Any, request_id: str) -> tuple[list[dict], list[dict]]:
    """Extract graph nodes + edges from a finished ResearchState.

    Pure function (no DB): returns node dicts keyed for upsert and edge dicts
    referencing nodes by ``(kind, norm_label)`` via ``src_norm``/``dst_norm``
    (both sides are created in the same batch, so label refs are resolvable).

    Emitted structure:
    - one ``paper`` node (explored) for the run
    - one ``topic`` node per angle topic (explored — it was researched)
    - one ``topic`` node per unexplored rabbit hole (frontier)
    - ``leads_to`` edges paper -> every topic it surfaced
    """
    paper_label = (getattr(state, "paper_title", "") or state.question).strip()
    paper_norm = normalize_label(paper_label)

    nodes: dict[tuple[str, str], dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}

    def add_node(label: str, kind: str, status: str, created_from: str) -> str:
        norm = normalize_label(label)
        key = (kind, norm)
        existing = nodes.get(key)
        if existing is None:
            nodes[key] = {
                "label": label.strip(),
                "norm_label": norm,
                "kind": kind,
                "status": status,
                "created_from": created_from,
                "request_id": request_id,
            }
        elif existing["status"] == "frontier" and status == "explored":
            # Explored always wins over frontier for the same label.
            existing["status"] = "explored"
        return norm

    def add_edge(src_norm: str, dst_norm: str, kind: str) -> None:
        key = (src_norm, dst_norm, kind)
        if key not in edges and src_norm != dst_norm:
            edges[key] = {"src_norm": src_norm, "dst_norm": dst_norm, "kind": kind}

    add_node(paper_label, "paper", "explored", "paper")

    # Angle topics were researched in this run — explored. Do this BEFORE
    # rabbit holes so a hole that spawned an angle resolves to explored.
    for angle in getattr(state, "angles", []):
        topic_norm = add_node(angle.topic, "topic", "explored", "paper")
        add_edge(paper_norm, topic_norm, "leads_to")

    # Unexplored rabbit holes become the new frontier.
    for angle in getattr(state, "angles", []):
        for hole in getattr(angle, "rabbit_holes", []) or []:
            hole_norm = add_node(hole, "topic", "frontier", "rabbit_hole")
            add_edge(paper_norm, hole_norm, "leads_to")

    return list(nodes.values()), list(edges.values())


def persist_graph(nodes: list[dict], edges: list[dict], session) -> None:
    """Upsert nodes and edges. Frontier never downgrades an explored node."""
    norm_to_id: dict[tuple[str, str], str] = {}
    for n in nodes:
        # NOTE: raw SQL bypasses the SQLAlchemy Python-side column defaults —
        # every NOT NULL column must be supplied explicitly here.
        row = session.execute(
            text("""
                INSERT INTO research_nodes
                    (id, label, norm_label, kind, status, created_from, source_signal,
                     paper_id, created_at, updated_at)
                VALUES
                    (:id, :label, :norm_label, :kind, :status, :created_from, 0,
                     CAST(NULLIF(:request_id, '') AS uuid), NOW(), NOW())
                ON CONFLICT (kind, norm_label) DO UPDATE SET
                    status = CASE
                        WHEN research_nodes.status = 'explored' THEN 'explored'
                        WHEN excluded.status = 'explored' THEN 'explored'
                        ELSE research_nodes.status
                    END,
                    updated_at = NOW()
                RETURNING id
            """),
            {
                "id": str(uuid.uuid4()),
                "label": n["label"][:500],
                "norm_label": n["norm_label"][:500],
                "kind": n["kind"],
                "status": n["status"],
                "created_from": n["created_from"],
                "request_id": n.get("request_id", ""),
            },
        ).fetchone()
        norm_to_id[(n["kind"], n["norm_label"])] = str(row.id)

    def node_id(norm: str) -> str | None:
        # Edges emitted by the builder reference paper/topic nodes only.
        return norm_to_id.get(("topic", norm)) or norm_to_id.get(("paper", norm))

    for e in edges:
        src, dst = node_id(e["src_norm"]), node_id(e["dst_norm"])
        if not src or not dst:
            continue
        session.execute(
            text("""
                INSERT INTO research_edges (id, src, dst, kind, weight, created_at)
                VALUES (:id, CAST(:src AS uuid), CAST(:dst AS uuid), :kind, 1.0, NOW())
                ON CONFLICT (src, dst, kind) DO NOTHING
            """),
            {"id": str(uuid.uuid4()), "src": src, "dst": dst, "kind": e["kind"]},
        )
    session.commit()


def persist_state_graph(state: Any, request_id: str) -> None:
    """Best-effort graph persistence at run end. A graph write failure must
    never fail the paper — log and move on (backfillable later)."""
    try:
        from pipeline.database import get_session

        nodes, edges = build_graph_from_state(state, request_id)
        with get_session() as session:
            persist_graph(nodes, edges, session)
        logger.info(
            "[GRAPH] Persisted %d nodes / %d edges for %s", len(nodes), len(edges), request_id
        )
    except Exception as exc:  # noqa: BLE001 — best-effort by design (see docstring)
        logger.error("[GRAPH] Persistence failed for %s: %s", request_id, exc)


def mark_node_explored(paper_request_id: str) -> None:
    """Flip the node that seeded this research request to explored."""
    try:
        from pipeline.database import get_session

        with get_session() as session:
            session.execute(
                text("""
                    UPDATE research_nodes
                    SET status = 'explored', updated_at = NOW()
                    WHERE paper_id = CAST(:rid AS uuid) AND status = 'researching'
                """),
                {"rid": paper_request_id},
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001 — best-effort by design
        logger.error("[GRAPH] mark_node_explored failed for %s: %s", paper_request_id, exc)


def pick_next_frontier_topic(session) -> dict | None:
    """Pick the highest-value frontier node and mark it researching.

    Score = source_signal + 0.5 * in-degree
            - 2.0 diversity penalty (children of papers explored in the last
              3 days — avoids researching the same cluster repeatedly)
            + 0.5 * random()  (the owner's "zufällig" component)
    """
    row = session.execute(
        text("""
            SELECT n.id::text AS id, n.label, n.kind, n.site_id::text AS site_id,
                   n.source_signal
                   + COALESCE(deg.cnt, 0) * 0.5
                   - CASE WHEN recent.hit IS NOT NULL THEN 2.0 ELSE 0 END
                   + random() * 0.5 AS score
            FROM research_nodes n
            LEFT JOIN (
                SELECT dst, COUNT(*) AS cnt FROM research_edges GROUP BY dst
            ) deg ON deg.dst = n.id
            LEFT JOIN (
                SELECT DISTINCT e.dst AS hit
                FROM research_edges e
                JOIN research_nodes p ON p.id = e.src AND p.kind = 'paper'
                WHERE p.updated_at > NOW() - INTERVAL '3 days'
            ) recent ON recent.hit = n.id
            WHERE n.status = 'frontier' AND n.kind IN ('topic', 'site')
            ORDER BY score DESC
            LIMIT 1
        """)
    ).fetchone()
    if not row:
        return None
    session.execute(
        text("""
            UPDATE research_nodes
            SET status = 'researching', updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
        """),
        {"id": row.id},
    )
    session.commit()
    return {"id": row.id, "label": row.label, "kind": row.kind, "site_id": row.site_id}


def question_for_node(node: dict) -> str:
    """Format a frontier node as a research question for the pipeline."""
    label = node["label"].strip()
    if node["kind"] == "site":
        return (
            f"What is known about {label}? Cover discovery history, dating, "
            f"interpretation controversies, and fringe theories."
        )
    if label.endswith("?"):
        return label
    return (
        f"What does the evidence say about {label}? Contrast mainstream "
        f"scholarship with fringe interpretations."
    )


def link_node_to_request(node_id: str, request_id: str, session) -> None:
    """Stamp the frontier node with the research_request it spawned."""
    session.execute(
        text("""
            UPDATE research_nodes
            SET paper_id = CAST(:rid AS uuid), updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
        """),
        {"id": node_id, "rid": request_id},
    )
    session.commit()
