"""Curator agent — the permanent researcher's nightly thinking pass (spec §3).

One structured LLM call Mon–Thu night: update the world model from new
papers, curate miner candidates into `connection` frontier nodes with
targeted questions, formulate falsifiable hypotheses, judge completed
hypothesis runs. Best-effort: any failure degrades to today's behavior.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import text

from pipeline.lyra.research_graph import is_junk_label, normalize_label

logger = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_PASS = 5
MAX_HYPOTHESES_PER_PASS = 3

CURATOR_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "node_label": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["established", "contested", "refuted", "open"],
                    },
                    "confidence": {"type": "number"},
                    "external_source_count": {"type": "integer"},
                    "paper_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "status"],
            },
        },
        "connections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "question": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["label", "question"],
            },
        },
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "question": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["label", "question"],
            },
        },
        "hypothesis_outcomes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "node_label": {"type": "string"},
                    "outcome": {
                        "type": "string",
                        "enum": ["confirmed", "refuted", "inconclusive"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["node_label", "outcome"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["claim_updates", "connections", "hypotheses", "summary"],
}


def thinking_pass_due(now_utc: datetime, last_pass_at: datetime | None) -> bool:
    """Nightly Mon–Thu 02:00–05:00 UTC, at most once per 20h. Fri–Sun are
    research days (weekend batch gate) — the curator stays quiet."""
    if now_utc.weekday() > 3:
        return False
    if not (2 <= now_utc.hour < 5):
        return False
    return last_pass_at is None or (now_utc - last_pass_at) >= timedelta(hours=20)


def _insert_topic_node(session, label: str, kind: str, question: str, rationale: str) -> bool:
    if is_junk_label(label) or not question.strip():
        return False
    session.execute(
        text("""
            INSERT INTO research_nodes
                (id, label, norm_label, kind, status, created_from, source_signal,
                 question, created_at, updated_at)
            VALUES
                (:id, :label, :norm_label, :kind, 'frontier', 'curator', 2.0,
                 :question, NOW(), NOW())
            ON CONFLICT (kind, norm_label) DO NOTHING
        """),
        {
            "id": str(uuid.uuid4()),
            "label": label.strip()[:500],
            "norm_label": normalize_label(label)[:500],
            "kind": kind,
            "question": question.strip(),
        },
    )
    return True


def _link_connection_endpoints(session, conn_label: str) -> None:
    """A connection node 'A ↔ B' gets `connects` edges to A and B when those
    nodes exist — the Knowledge page draws the new line (spec data model).

    A label can exist as BOTH a topic and a site node (the miner's label
    bridge) — edges to both twins are deliberate: the connection anchors to
    every representation of its endpoint."""
    if "↔" not in conn_label:
        return
    conn_norm = normalize_label(conn_label)[:500]
    for part in conn_label.split("↔"):
        session.execute(
            text("""
                INSERT INTO research_edges (id, src, dst, kind, weight, created_at)
                SELECT CAST(:id AS uuid), c.id, t.id, 'connects', 1.0, NOW()
                FROM research_nodes c
                JOIN research_nodes t
                  ON t.norm_label = :part_norm AND t.kind != 'connection'
                WHERE c.kind = 'connection' AND c.norm_label = :conn_norm
                ON CONFLICT (src, dst, kind) DO NOTHING
            """),
            {
                "id": str(uuid.uuid4()),
                "conn_norm": conn_norm,
                "part_norm": normalize_label(part)[:500],
            },
        )


def _apply_curator_output(session, out: dict) -> dict:
    """Apply a validated curator output. Pure DB writes, no LLM. Returns
    counters for the thinking log. Refuted claims never reopen."""
    stats = {"claims": 0, "connections": 0, "hypotheses": 0, "outcomes": 0}

    for cu in out.get("claim_updates", []):
        claim_text = (cu.get("text") or "").strip()
        if not claim_text:
            continue
        norm = normalize_label(claim_text)[:500]
        existing = session.execute(
            text("SELECT status FROM knowledge_claims WHERE norm_text = :norm LIMIT 1"),
            {"norm": norm},
        ).fetchone()
        if existing and existing.status == "refuted":
            continue  # refuted is terminal (spec §1)
        paper_ids = json.dumps(cu.get("paper_ids") or [])
        if existing:
            session.execute(
                text("""
                    UPDATE knowledge_claims
                    SET status = :status, confidence = :conf,
                        external_source_count = :ext,
                        paper_ids = (SELECT COALESCE(jsonb_agg(DISTINCT e), '[]'::jsonb)
                                     FROM jsonb_array_elements(
                                          COALESCE(paper_ids, '[]'::jsonb)
                                          || CAST(:paper_ids AS jsonb)) e),
                        updated_at = NOW()
                    WHERE norm_text = :norm
                """),
                {
                    "status": cu["status"],
                    "conf": float(cu.get("confidence") or 0.5),
                    "ext": int(cu.get("external_source_count") or 0),
                    "paper_ids": paper_ids,
                    "norm": norm,
                },
            )
        else:
            session.execute(
                text("""
                    INSERT INTO knowledge_claims
                        (id, text, norm_text, node_id, status, confidence,
                         external_source_count, paper_ids, created_at, updated_at)
                    VALUES
                        (:id, :text, :norm,
                         (SELECT id FROM research_nodes
                          WHERE norm_label = :node_norm LIMIT 1),
                         :status, :conf, :ext, CAST(:paper_ids AS jsonb), NOW(), NOW())
                """),
                {
                    "id": str(uuid.uuid4()),
                    "text": claim_text,
                    "norm": norm,
                    "node_norm": normalize_label(cu.get("node_label") or "")[:500],
                    "status": cu["status"],
                    "conf": float(cu.get("confidence") or 0.5),
                    "ext": int(cu.get("external_source_count") or 0),
                    "paper_ids": paper_ids,
                },
            )
        stats["claims"] += 1

    for conn in out.get("connections", [])[:MAX_CONNECTIONS_PER_PASS]:
        label = conn.get("label") or ""
        if _insert_topic_node(
            session,
            label,
            "connection",
            conn.get("question") or "",
            conn.get("rationale") or "",
        ):
            _link_connection_endpoints(session, label)
            stats["connections"] += 1

    for hyp in out.get("hypotheses", [])[:MAX_HYPOTHESES_PER_PASS]:
        if _insert_topic_node(
            session,
            hyp.get("label") or "",
            "hypothesis",
            hyp.get("question") or "",
            hyp.get("rationale") or "",
        ):
            stats["hypotheses"] += 1

    for ho in out.get("hypothesis_outcomes", []):
        session.execute(
            text("""
                UPDATE research_nodes
                SET outcome = :outcome, updated_at = NOW()
                WHERE kind = 'hypothesis' AND norm_label = :norm
            """),
            {
                "outcome": ho["outcome"],
                "norm": normalize_label(ho.get("node_label") or "")[:500],
            },
        )
        stats["outcomes"] += 1

    session.commit()
    return stats


def _gather_inputs(session) -> dict:
    """Collect world model, new papers, miner candidates, open hypotheses."""
    last_pass = session.execute(
        text("SELECT MAX(created_at) AS ts FROM thinking_log WHERE kind = 'curator'")
    ).fetchone()
    since = last_pass.ts if last_pass and last_pass.ts else datetime(2020, 1, 1)

    claims = session.execute(
        text("""
            SELECT text, status, confidence FROM knowledge_claims
            ORDER BY updated_at DESC LIMIT 100
        """)
    ).fetchall()

    papers = session.execute(
        text("""
            SELECT id::text AS request_id, question, result_json FROM research_requests
            WHERE status = 'completed' AND is_batch = TRUE AND completed_at > :since
            ORDER BY completed_at DESC LIMIT 5
        """),
        {"since": since},
    ).fetchall()
    paper_excerpts = []
    for p in papers:
        report = (json.loads(p.result_json).get("report") or "") if p.result_json else ""
        # Head (framing) + tail (conclusions) of the report; middle is bulk.
        paper_excerpts.append(
            {
                "request_id": p.request_id,
                "question": p.question,
                "excerpt": report[:4000] + "\n...\n" + report[-3000:],
            }
        )

    open_hypotheses = session.execute(
        text("""
            SELECT n.label, n.question, rr.result_json
            FROM research_nodes n
            JOIN research_requests rr ON rr.id = n.paper_id AND rr.status = 'completed'
            WHERE n.kind = 'hypothesis' AND n.status = 'explored' AND n.outcome IS NULL
            LIMIT 5
        """)
    ).fetchall()
    hyp_inputs = [
        {
            "label": h.label,
            "question": h.question,
            "paper_tail": ((json.loads(h.result_json).get("report") or "")[-3000:])
            if h.result_json
            else "",
        }
        for h in open_hypotheses
    ]

    from pipeline.lyra.graph_miner import run_miner

    return {
        "claims": [dict(r._mapping) for r in claims],
        "papers": paper_excerpts,
        "candidates": run_miner(),
        "open_hypotheses": hyp_inputs,
    }


def run_curator_pass() -> None:
    """One nightly thinking pass. Best-effort — never raises."""
    try:
        from pathlib import Path

        from pipeline.database import get_session
        from pipeline.lyra.config import LyraSettings
        from pipeline.lyra.minimax_shared import structured_llm_call
        from pipeline.lyra.thinking_log import log_thinking

        settings = LyraSettings()
        with get_session() as session:
            inputs = _gather_inputs(session)

        system = (Path(__file__).parent / "prompts" / "curator_pass.txt").read_text(
            encoding="utf-8"
        )
        out = structured_llm_call(
            system=system,
            user_message=json.dumps(inputs, ensure_ascii=False, default=str)[:60000],
            schema=CURATOR_SCHEMA,
            max_tokens=4096,
            settings=settings,
            temperature=settings.temperature_verification,
        )
        if not out:
            logger.warning("[THINK] curator returned empty output — skipping apply")
            return

        with get_session() as session:
            stats = _apply_curator_output(session, out)

        summary = (
            f"Denkstunde: {stats['claims']} claims, {stats['connections']} connections, "
            f"{stats['hypotheses']} hypotheses, {stats['outcomes']} verdicts"
        )
        log_thinking("curator", summary, {**stats, "llm_summary": out.get("summary", "")})
        try:
            from api.services.notify import send_discord_webhook

            send_discord_webhook(
                {
                    "embeds": [
                        {
                            "title": "🧠 Theo Denkstunde",
                            "description": f"{summary}\n{out.get('summary', '')[:500]}",
                            "color": 0x3498DB,
                        }
                    ]
                }
            )
        except Exception:  # noqa: BLE001 — notification is best-effort
            pass
    except Exception as exc:  # noqa: BLE001 — thinking must never kill the feeder
        logger.error("[THINK] curator pass failed: %s", exc, exc_info=True)
