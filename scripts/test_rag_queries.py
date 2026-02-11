#!/usr/bin/env python3
"""
Test harness for Lyra RAG retrieval quality.

Runs a graded set of queries (easy → hard) through the full hybrid search
pipeline (dense + BM25 + RRF + rerank) and prints what comes back from
both the sites and news collections.

Usage:
  python scripts/test_rag_queries.py
  python scripts/test_rag_queries.py --query "your custom query here"
  python scripts/test_rag_queries.py --index 3    # run only query #3
  python scripts/test_rag_queries.py --json        # append JSON metrics block
"""

import argparse
import json
import os
import statistics
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.lyra_tools import _hybrid_search

# ─── Test queries: easy → medium → hard → impossible ───────────────────────

QUERIES = [
    # ── EASY: Single-entity lookup (name match) ──
    {
        "level": "EASY",
        "query": "What does Machu Picchu mean?",
        "expect": "Should find Machu Picchu with its description",
        "collections": ["sites"],
    },
    {
        "level": "EASY",
        "query": "Tell me about Gobekli Tepe",
        "expect": "Should find Gobekli Tepe site + news about it",
        "collections": ["sites", "news"],
    },
    {
        "level": "EASY",
        "query": "Where is Stonehenge?",
        "expect": "Should find Stonehenge with country=England and coordinates",
        "collections": ["sites"],
    },

    # ── MEDIUM: Type + region filter (metadata match) ──
    {
        "level": "MEDIUM",
        "query": "Show me pyramids in Egypt",
        "expect": "Should return pyramid sites in Egypt (type + country filter)",
        "collections": ["sites"],
    },
    {
        "level": "MEDIUM",
        "query": "What megalithic sites are in France?",
        "expect": "Should return menhirs, dolmens, stone circles in France",
        "collections": ["sites"],
    },
    {
        "level": "MEDIUM",
        "query": "Roman fortresses in England",
        "expect": "Should return fortress/citadel sites with Roman-era period in England",
        "collections": ["sites"],
    },

    # ── HARD: Semantic reasoning across data ──
    {
        "level": "HARD",
        "query": "Ancient temples that are older than the Egyptian pyramids",
        "expect": "Should find pre-3000 BCE temples (Gobekli Tepe, Malta temples, etc.)",
        "collections": ["sites"],
    },
    {
        "level": "HARD",
        "query": "Sites in the Mediterranean that were part of the Roman Empire with fortifications",
        "expect": "Should find Roman-era fortresses in Greece, Italy, Turkey, etc.",
        "collections": ["sites"],
    },
    {
        "level": "HARD",
        "query": "Cave paintings and rock art in Europe",
        "expect": "Should find cave structures and petroglyphs across European countries",
        "collections": ["sites"],
    },

    # ── NEWS: Recent discoveries with timestamps ──
    {
        "level": "NEWS",
        "query": "Recent discoveries about Karahantepe",
        "expect": "Should find news items about Karahantepe with video timestamps",
        "collections": ["news"],
    },
    {
        "level": "NEWS",
        "query": "What new findings have been reported about water rituals at ancient sites?",
        "expect": "Should find Karahantepe water ritual news items",
        "collections": ["news"],
    },
    {
        "level": "NEWS",
        "query": "LiDAR archaeological discoveries",
        "expect": "Should find the LiDAR discovery news item from Alabama",
        "collections": ["news"],
    },

    # ── IMPOSSIBLE: Requires data we don't have ──
    {
        "level": "IMPOSSIBLE",
        "query": "Fortresses where human remains were found that are older than the site itself",
        "expect": "EXPECTED TO FAIL: requires find-level data we don't store",
        "collections": ["sites", "news"],
    },
    {
        "level": "IMPOSSIBLE",
        "query": "Sites where DNA analysis revealed unexpected population migration",
        "expect": "EXPECTED TO FAIL: requires excavation report data",
        "collections": ["sites", "news"],
    },
]

# ─── Colors for terminal output ────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"

LEVEL_COLORS = {
    "EASY": GREEN,
    "MEDIUM": YELLOW,
    "HARD": MAGENTA,
    "NEWS": CYAN,
    "IMPOSSIBLE": RED,
}


def run_query(idx: int, test: dict) -> dict:
    """Run a single test query, print colored output, return metrics dict."""
    level = test["level"]
    query = test["query"]
    color = LEVEL_COLORS.get(level, RESET)

    print(f"\n{'='*80}")
    print(f"{BOLD}#{idx+1} [{color}{level}{RESET}{BOLD}] {query}{RESET}")
    print(f"{DIM}Expect: {test['expect']}{RESET}")
    print(f"{'─'*80}")

    metrics = {
        "index": idx + 1,
        "query": query,
        "level": level,
        "collections": {},
    }

    for collection in test["collections"]:
        t0 = time.time()
        results = _hybrid_search(query, collection=collection, limit=5)
        elapsed = (time.time() - t0) * 1000

        print(f"\n  {BOLD}{collection.upper()}{RESET} ({len(results)} results, {elapsed:.0f}ms):")

        scores = [r.get("relevance", 0) for r in results]
        top1_name = ""
        if results:
            top1_name = results[0].get("name") or results[0].get("headline", "???")

        metrics["collections"][collection] = {
            "elapsed_ms": round(elapsed, 1),
            "result_count": len(results),
            "top1_name": top1_name,
            "top1_score": scores[0] if scores else 0,
            "top5_avg_score": round(statistics.mean(scores), 3) if scores else 0,
            "top5_min_score": min(scores) if scores else 0,
        }

        if not results:
            print(f"    {DIM}(no results){RESET}")
            continue

        for i, item in enumerate(results):
            rel = item.get("relevance", 0)
            if rel >= 0.5:
                rel_color = GREEN
            elif rel >= 0.2:
                rel_color = YELLOW
            else:
                rel_color = RED

            name = item.get("name") or item.get("headline", "???")
            print(f"    {rel_color}{rel:.3f}{RESET}  {BOLD}{name}{RESET}")

            if item.get("site_type"):
                parts = []
                if item.get("site_type"):
                    parts.append(f"type={item['site_type']}")
                if item.get("period_name"):
                    parts.append(f"period={item['period_name']}")
                if item.get("country"):
                    parts.append(f"country={item['country']}")
                print(f"           {DIM}{' | '.join(parts)}{RESET}")

            desc = item.get("description") or item.get("summary") or ""
            if desc:
                snippet = desc[:120].replace("\n", " ")
                if len(desc) > 120:
                    snippet += "..."
                print(f"           {DIM}{snippet}{RESET}")

            if item.get("channel"):
                print(f"           {DIM}channel={item['channel']} | video={item.get('video_id','?')}{RESET}")

    return metrics


def _compute_summary(all_metrics: list[dict], total_time: float) -> dict:
    """Compute aggregate summary from all query metrics."""
    # Collect all individual search latencies (one per collection per query)
    all_latencies = []
    for m in all_metrics:
        for coll_data in m["collections"].values():
            all_latencies.append(coll_data["elapsed_ms"])

    # Skip the very first latency (cold start: model loading, connection init)
    warm_latencies = all_latencies[1:] if len(all_latencies) > 1 else all_latencies

    # Breakdown by level
    level_scores: dict[str, list[float]] = {}
    for m in all_metrics:
        level = m["level"]
        for coll_data in m["collections"].values():
            if coll_data["top1_score"] > 0:
                level_scores.setdefault(level, []).append(coll_data["top1_score"])

    level_summary = {}
    for level, scores in level_scores.items():
        level_summary[level] = {
            "avg_top1_score": round(statistics.mean(scores), 3),
            "query_count": len(scores),
        }

    sorted_warm = sorted(warm_latencies)
    p50_idx = int(len(sorted_warm) * 0.5)
    p95_idx = min(int(len(sorted_warm) * 0.95), len(sorted_warm) - 1)

    return {
        "total_queries": len(all_metrics),
        "total_search_calls": len(all_latencies),
        "total_time_s": round(total_time, 1),
        "avg_latency_ms": round(statistics.mean(warm_latencies), 1) if warm_latencies else 0,
        "median_latency_ms": round(statistics.median(warm_latencies), 1) if warm_latencies else 0,
        "p50_latency_ms": round(sorted_warm[p50_idx], 1) if sorted_warm else 0,
        "p95_latency_ms": round(sorted_warm[p95_idx], 1) if sorted_warm else 0,
        "cold_start_ms": round(all_latencies[0], 1) if all_latencies else 0,
        "by_level": level_summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Test Lyra RAG retrieval quality")
    parser.add_argument("--query", help="Run a custom query instead of the test set")
    parser.add_argument("--index", type=int, help="Run only test query at this index (1-based)")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Append a JSON metrics block after the colored output")
    args = parser.parse_args()

    if args.query:
        run_query(0, {
            "level": "CUSTOM",
            "query": args.query,
            "expect": "Custom query",
            "collections": ["sites", "news"],
        })
        return

    queries = QUERIES
    if args.index:
        if 1 <= args.index <= len(QUERIES):
            queries = [QUERIES[args.index - 1]]
        else:
            print(f"Index must be 1-{len(QUERIES)}")
            return

    print(f"{BOLD}Lyra RAG Retrieval Test — {len(queries)} queries{RESET}")
    print(f"{DIM}Pipeline: voyage-4 (dense) + BM25 (sparse) → RRF → rerank-2.5-lite{RESET}")

    all_metrics = []
    t_total = time.time()
    for i, test in enumerate(queries):
        idx = args.index - 1 if args.index else i
        metrics = run_query(idx, test)
        all_metrics.append(metrics)

    elapsed = time.time() - t_total
    print(f"\n{'='*80}")
    print(f"{BOLD}Done — {len(queries)} queries in {elapsed:.1f}s{RESET}")

    if args.json_output and all_metrics:
        summary = _compute_summary(all_metrics, elapsed)
        blob = {
            "queries": all_metrics,
            "summary": summary,
        }
        print(f"\n--- JSON ---")
        print(json.dumps(blob, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
