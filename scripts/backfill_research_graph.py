"""Backfill the research knowledge graph from already-published papers.

One M3 structured call per published paper extracts topics, entities, and
open questions from the report; nodes + edges are upserted through the same
persistence path the live pipeline uses. Idempotent — rerunning only
accumulates, never duplicates (dedupe on (kind, norm_label)).

Run inside the api container after the graph tables exist:

  docker exec ancient_nerds_api python scripts/backfill_research_graph.py
"""

from __future__ import annotations

import json
import sys

from sqlalchemy import text

from pipeline.database import get_session
from pipeline.lyra.minimax_shared import structured_llm_call
from pipeline.lyra.research_graph import normalize_label, persist_graph

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "8-15 research topics the paper covers or touches",
        },
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "5-10 follow-up research questions the paper raises but does not answer",
        },
        "site_names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Archaeological sites discussed in the paper",
        },
    },
    "required": ["topics", "open_questions", "site_names"],
}

SYSTEM = (
    "You are building a research knowledge graph for an archaeology platform. "
    "Extract the requested structured data from the paper. Topics should be "
    "specific enough to research individually (not 'mythology' but 'Aztec Five "
    "Suns cosmology'). Open questions are follow-ups the paper explicitly or "
    "implicitly leaves unanswered."
)


def backfill_paper(row) -> tuple[int, int]:
    report = (row.report or "")[:60000]
    extracted = structured_llm_call(
        system=SYSTEM,
        user_message=f"Paper title: {row.title}\n\nPaper:\n{report}",
        schema=EXTRACTION_SCHEMA,
        max_tokens=4096,
        temperature=0.1,
    )

    paper_norm = normalize_label(row.title)
    nodes = [
        {
            "label": row.title,
            "norm_label": paper_norm,
            "kind": "paper",
            "status": "explored",
            "created_from": "backfill",
            "request_id": row.id,
        }
    ]
    edges = []
    for topic in extracted.get("topics", []):
        norm = normalize_label(topic)
        nodes.append(
            {
                "label": topic,
                "norm_label": norm,
                "kind": "topic",
                "status": "explored",
                "created_from": "backfill",
                "request_id": "",
            }
        )
        edges.append({"src_norm": paper_norm, "dst_norm": norm, "kind": "related"})
    for question in extracted.get("open_questions", []):
        norm = normalize_label(question)
        nodes.append(
            {
                "label": question,
                "norm_label": norm,
                "kind": "topic",
                "status": "frontier",
                "created_from": "backfill",
                "request_id": "",
            }
        )
        edges.append({"src_norm": paper_norm, "dst_norm": norm, "kind": "leads_to"})
    for site in extracted.get("site_names", []):
        norm = normalize_label(site)
        nodes.append(
            {
                "label": site,
                "norm_label": norm,
                "kind": "topic",
                "status": "frontier",
                "created_from": "backfill",
                "request_id": "",
            }
        )
        edges.append({"src_norm": paper_norm, "dst_norm": norm, "kind": "about_site"})

    with get_session() as session:
        persist_graph(nodes, edges, session)
    return len(nodes), len(edges)


def main() -> int:
    with get_session() as session:
        rows = session.execute(
            text("""
                SELECT id::text AS id,
                       result_json::jsonb->>'title' AS title,
                       COALESCE(result_json::jsonb->>'published_report',
                                result_json::jsonb->>'report') AS report
                FROM research_requests
                WHERE is_public = TRUE AND status = 'completed'
                ORDER BY published_at
            """)
        ).fetchall()

    print(f"Backfilling graph from {len(rows)} published papers...", flush=True)
    total_nodes = total_edges = 0
    for row in rows:
        if not row.title or not row.report:
            print(f"  SKIP {row.id}: missing title/report", flush=True)
            continue
        n, e = backfill_paper(row)
        total_nodes += n
        total_edges += e
        print(f"  {row.title[:60]}: {n} nodes, {e} edges", flush=True)

    with get_session() as session:
        counts = session.execute(
            text("SELECT status, COUNT(*) FROM research_nodes GROUP BY status")
        ).fetchall()
    print(json.dumps(dict(counts)), flush=True)
    print(f"Done: {total_nodes} nodes, {total_edges} edges processed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
