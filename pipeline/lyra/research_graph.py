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


# Literal junk that LLM output / JSON serialization can leak into labels.
# 2026-07-31: a rabbit hole labeled "null" (source_signal 2220 via injector
# accumulation) topped the frontier and the feeder burned a research run on
# "What does the evidence say about null?". Every node-insert path and the
# frontier picker reject these.
# Compared post-normalize_label — "N/A" normalizes to "n a".
JUNK_LABELS = frozenset({"null", "none", "nan", "undefined", "unknown", "n/a", "n a", "na"})


def is_junk_label(label: str | None) -> bool:
    """True when a label must never become a graph node or research topic."""
    if not label:
        return True
    normalized = normalize_label(label)
    if not normalized:
        # Whitespace/punctuation-only labels normalize to "" — not in
        # JUNK_LABELS, so they slipped through before this check (M14,
        # 2026-08-05 review).
        return True
    return normalized in JUNK_LABELS


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
        if is_junk_label(label):
            return ""
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
        # Empty norm = junk label rejected by add_node — no node, no edge.
        if not src_norm or not dst_norm:
            return
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
        for kind in ("topic", "paper", "entity", "person"):
            found = norm_to_id.get((kind, norm))
            if found:
                return found
        return None

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


def reset_node_for_failed_request(paper_request_id: str) -> None:
    """Reset the node that seeded this research request back to frontier
    when its run dies without ever completing (failed/cancelled) — mirrors
    mark_node_explored's exact pattern for the terminal-failure case.

    Without this, a node stuck 'researching' from a dead run is a dead end:
    the miner's NOT EXISTS suppression treats the pair as already covered
    forever, and the curator's connection/hypothesis insert is a no-op
    (`ON CONFLICT (kind, norm_label) DO NOTHING`), so the label can never be
    requeued (Follow-up-Ticket 6, 2026-08-04 final review). Deliberately NOT
    called for 'deferred' runs — those retry and still hold a legitimate
    claim on the node; resetting them would let the feeder double-queue the
    same node while the deferred run is still pending."""
    try:
        from pipeline.database import get_session

        with get_session() as session:
            session.execute(
                text("""
                    UPDATE research_nodes
                    SET status = 'frontier', updated_at = NOW()
                    WHERE paper_id = CAST(:rid AS uuid) AND status = 'researching'
                """),
                {"rid": paper_request_id},
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001 — best-effort by design
        logger.error(
            "[GRAPH] reset_node_for_failed_request failed for %s: %s", paper_request_id, exc
        )


def allow_synthesis(recent_seed_kinds: list[str]) -> bool:
    """Max 1 of 3 recent batch runs may be synthesis (connection/hypothesis)
    — fresh external topics keep the majority (anti-echo, spec §4).

    A missing seed node (recent_batch_seed_kinds COALESCEs to 'topic' when a
    batch run has no matching connection/hypothesis research_nodes row —
    e.g. a manually queued or pre-thinking-layer run) deliberately reads as
    "not synthesis": it can never suppress a slot it didn't spend.

    Effective cadence is therefore 1-in-4, not 1-in-3: a synthesis run stays
    in the trailing window for the next three picks (itself plus the two
    after it, until a fourth run pushes it out), so it blocks the following
    three windows. Failed/claimed-but-not-completed runs still count here
    (this reads whatever landed in research_requests, not just successes) —
    both are accepted as conservative-by-design: undercounting synthesis
    slots is safe, overcounting them would erode the anti-echo quota.
    """
    return not any(k in ("connection", "hypothesis") for k in recent_seed_kinds)


def recent_batch_seed_kinds(session, limit: int = 3) -> list[str]:
    """Seed kinds of the most recent batch research_requests, most recent
    first — feeds allow_synthesis()'s anti-echo quota (spec §4). Graph-domain
    logic: it reasons about research_nodes, so it lives here rather than in
    the feeder."""
    return [
        r.kind
        for r in session.execute(
            text("""
                SELECT COALESCE(n.kind, 'topic') AS kind
                FROM research_requests rr
                LEFT JOIN research_nodes n
                  ON n.paper_id = rr.id
                 AND n.kind IN ('connection', 'hypothesis')
                WHERE rr.is_batch = TRUE
                ORDER BY rr.started_at DESC NULLS LAST
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()
    ]


def _pick_frontier(session, kinds: tuple[str, ...]) -> dict | None:
    """Pick the highest-value frontier node of the given kinds and mark it
    researching.

    Score = source_signal
            + kind weight (hypothesis 3.0, connection 2.0 — orders
              hypothesis above connection within the synthesis pool; it
              cannot make either compete against injector-accumulated
              source_signal on plain topic/site nodes, which is why
              pick_next_frontier_topic uses a dedicated slot instead of a
              shared ranking — see its docstring)
            + 0.5 * in-degree
            - 2.0 diversity penalty (children of papers explored in the last
              3 days — avoids researching the same cluster repeatedly)
            + age term: LEAST(days_old * 0.5, 3.0) — 0.5/day, capped at 3.0
              (bridges the hypothesis-vs-connection gap within a week). This
              is the REAL starvation fix (Follow-up-Ticket 4, corrected
              2026-08-05 review): the `n.created_at ASC` tiebreak added in
              the first pass was inert — `random() * 0.5` is part of the
              `score` column being sorted, and a float draw ties with
              another float draw ~never, so ORDER BY score DESC never
              actually reaches the tiebreak. Putting age INSIDE the score
              (rather than as an ORDER BY tiebreak on a column that's never
              tied) is what actually stops a newer node from permanently
              outscoring an older one via random() alone.
            + 0.5 * random()  (the owner's "zufällig" component)

    Tiebreak: n.created_at ASC (oldest first) — kept as a harmless second
    ORDER BY key in case two scores ever do land exactly equal (e.g. random()
    itself producing a duplicate float, astronomically unlikely but free to
    guard).
    """
    row = session.execute(
        text("""
            SELECT n.id::text AS id, n.label, n.kind, n.site_id::text AS site_id,
                   n.question,
                   n.source_signal
                   + CASE n.kind WHEN 'hypothesis' THEN 3.0
                                 WHEN 'connection' THEN 2.0
                                 ELSE 0 END
                   + COALESCE(deg.cnt, 0) * 0.5
                   - CASE WHEN recent.hit IS NOT NULL THEN 2.0 ELSE 0 END
                   + LEAST(EXTRACT(EPOCH FROM NOW() - n.created_at) / 86400.0 * 0.5, 3.0)
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
            WHERE n.status = 'frontier' AND n.kind = ANY(:kinds)
              -- junk-label insurance: a garbage node must never cost a
              -- multi-hour research run (see JUNK_LABELS, 2026-07-31)
              AND LOWER(TRIM(n.label)) NOT IN
                  ('null', 'none', 'nan', 'undefined', 'unknown', 'n/a', 'na', '')
              -- Failure cooldown (Follow-up-Ticket 5, final review): a node
              -- whose most recent run terminally failed/was cancelled and
              -- got reset to frontier (reset_node_for_failed_request) would
              -- otherwise be picked again immediately, bounding it to at
              -- most 1 attempt/day instead of hammering a doomed node in a
              -- tight reset->re-pick loop. Fresh nodes (paper_id IS NULL,
              -- never attempted) are unaffected — the NOT EXISTS is
              -- vacuously true when there's no matching research_requests
              -- row to join against.
              AND NOT EXISTS (
                  SELECT 1 FROM research_requests rr
                  WHERE rr.id = n.paper_id
                    AND rr.status IN ('failed', 'cancelled')
                    AND rr.completed_at > NOW() - INTERVAL '24 hours'
              )
            ORDER BY score DESC, n.created_at ASC
            LIMIT 1
        """),
        {"kinds": list(kinds)},
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
    return {
        "id": row.id,
        "label": row.label,
        "kind": row.kind,
        "site_id": row.site_id,
        "question": row.question,
    }


def pick_next_frontier_topic(session, include_synthesis: bool = True) -> dict | None:
    """Pick the next frontier node to research and mark it researching.

    When include_synthesis, curator-authored nodes (connection/hypothesis)
    get a dedicated slot: they are tried FIRST, ranked among themselves (the
    kind weights in _pick_frontier order hypothesis > connection within the
    pool); plain topic/site picking is untouched and serves as mandatory
    fallback — an empty synthesis pool must never idle the feeder.

    Rationale: additive weights can never beat injector-accumulated
    signals (measured on the live graph: frontier head source_signal 1180,
    growing ~+120/day via hourly injector accumulation, vs. a synthesis
    score ceiling of ~5.5 — a shared ranking put hypothesis nodes at
    rank #80 of 1132, never picked).
    """
    if include_synthesis:
        node = _pick_frontier(session, ("connection", "hypothesis"))
        if node:
            return node
    return _pick_frontier(session, ("topic", "site"))


def question_for_node(node: dict) -> str:
    """Format a frontier node as a research question for the pipeline.
    A curator-written question stored on the node always wins (spec §4)."""
    stored = (node.get("question") or "").strip()
    if stored:
        return stored
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
