"""Theo smoke test — single short run on the VPS, no DB flush.

Bypasses the API auth + DB-flush layer by passing request_id="". Runs
inside the API container (which has the full pipeline deps) via:
    cat scripts/smoke_theo_host.py | ssh ancientnerds \
        'docker exec -i ancient_nerds_api python -'

Reports the quality score, badge, paper length, llm_calls, total_tokens,
and a short progress trail. Non-zero exit if quality < 70 or paper < 4k chars.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Force shallow ResearchConfig so this finishes in ~15-20 min on the VPS.
os.environ["THEO_FAST"] = "1"

QUESTION = (
    "What evidence is there for and against the hypothesis that the Younger "
    "Dryas cooling event (~12,900 years ago) was triggered by a cosmic impact, "
    "and how do the most recent scientific papers (2020-2025) weigh in?"
)


async def main() -> int:
    # Match the host-script logic: shrink the config when THEO_FAST=1.
    import pipeline.lyra.convergence_orchestrator as co

    _orig = co.ResearchConfig

    def _small():
        c = _orig()
        c.max_angles = 5
        c.initial_specialist_count = 3
        c.min_specialists = 2
        c.max_specialists = 5
        c.max_search_rounds_per_angle = 3
        c.max_debate_rounds = 1
        return c

    co.ResearchConfig = _small

    from pipeline.lyra.convergence_orchestrator import ConvergenceOrchestrator

    t0 = time.monotonic()
    counter = {"n": 0}

    def emit(event: dict) -> None:
        counter["n"] += 1
        if counter["n"] % 25 == 0:
            mins = (time.monotonic() - t0) / 60.0
            print(
                f"[smoke] {counter['n']} events, {mins:.1f}min, last={event.get('type')}",
                flush=True,
            )

    print(f"[smoke] START: {QUESTION[:80]}...", flush=True)
    ctx = await ConvergenceOrchestrator().run(QUESTION, emit, request_id="")
    dur_min = round((time.monotonic() - t0) / 60.0, 1)

    if ctx.error:
        print(f"[smoke] FAILED: {ctx.error}", flush=True)
        return 2

    qs = ctx.quality_score or {}
    paper = ctx.paper_text or ""
    sources_count = 0
    try:
        sources_count = len(ctx.registry.sources)
    except Exception:
        pass

    summary = {
        "duration_min": dur_min,
        "quality_score": qs.get("score"),
        "badge": qs.get("badge"),
        "dimensions": qs.get("dimensions", {}),
        "paper_chars": len(paper),
        "llm_calls": getattr(ctx, "llm_call_count", None),
        "total_tokens": getattr(ctx, "total_tokens", None),
        "sources_count": sources_count,
        "title": ctx.paper_title or "",
        "events": counter["n"],
        "passed_gate": qs.get("audit_gate_failures", {}).get("passed"),
    }
    print("[smoke] RESULT:", flush=True)
    print(json.dumps(summary, indent=2, default=str), flush=True)

    score = qs.get("score") or 0
    if score < 70:
        print(f"[smoke] FAIL: quality {score} < 70", flush=True)
        return 3
    if len(paper) < 4000:
        print(f"[smoke] FAIL: paper {len(paper)} chars < 4000", flush=True)
        return 4
    print(f"[smoke] OK in {dur_min}min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
