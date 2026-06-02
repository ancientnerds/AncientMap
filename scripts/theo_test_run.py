"""Run a single full Theo convergence research pass and report the result.

Standalone (request_id="" skips the research_requests DB flush). Prints quality
metrics and writes the finished paper markdown to /tmp/theo_paper.md inside the
container. Used as an end-to-end smoke/showcase of the pipeline.

  docker exec ancient_nerds_api python scripts/theo_test_run.py "QUESTION"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time


def _maybe_shrink_config() -> None:
    """THEO_FAST=1 → bound the convergence to a fast profile (fewer angles/
    rounds) so a single run completes in ~15-20 min instead of 60+. Produces a
    real multi-angle paper, just shallower than the full 12-angle config."""
    if os.getenv("THEO_FAST") != "1":
        return
    import pipeline.lyra.convergence_orchestrator as co

    _orig = co.ResearchConfig

    def _small():
        c = _orig()
        # Fewer angles + a single debate round (debate is the slow part), but
        # keep per-angle search depth near default so coverage gates still pass.
        c.max_angles = 5
        c.initial_specialist_count = 3
        c.min_specialists = 2
        c.max_specialists = 5
        c.max_search_rounds_per_angle = 3
        c.max_debate_rounds = 1
        # saturation_threshold + queries_per_angle left at defaults (2, 5).
        return c

    co.ResearchConfig = _small


async def _run(question: str) -> None:
    _maybe_shrink_config()
    from pipeline.lyra.convergence_orchestrator import ConvergenceOrchestrator

    t0 = time.monotonic()
    counter = {"n": 0}

    def emit(event: dict) -> None:
        counter["n"] += 1
        if counter["n"] % 20 == 0:
            mins = (time.monotonic() - t0) / 60.0
            print(f"[theo] {counter['n']} events, {mins:.1f}min, last={event.get('type')}", flush=True)

    print(f"[theo] starting: {question}", flush=True)
    ctx = await ConvergenceOrchestrator().run(question, emit, request_id="")
    dur = (time.monotonic() - t0) / 60.0

    if ctx.error:
        print(f"=== THEO FAILED === {ctx.error}", flush=True)
        return

    qs = ctx.quality_score or {}
    paper = ctx.paper_text or ""
    with open("/tmp/theo_paper.md", "w", encoding="utf-8") as fh:  # noqa: S108 — container scratch path
        fh.write(f"# {ctx.paper_title}\n\n{paper}")

    summary = {
        "title": ctx.paper_title,
        "duration_min": round(dur, 1),
        "quality_score": qs.get("score"),
        "badge": qs.get("badge"),
        "dimensions": qs.get("dimensions", {}),
        "citation_sources": len(ctx.registry.sources) if hasattr(ctx, "registry") else 0,
        "specialists": len(getattr(ctx, "specialist_analyses", {}) or {}),
        "paper_chars": len(paper),
        "llm_calls": ctx.llm_call_count,
        "total_tokens": ctx.total_tokens,
    }
    print("=== THEO_SUMMARY === " + json.dumps(summary), flush=True)
    print("=== THEO DONE === paper written to /tmp/theo_paper.md", flush=True)


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "What do recent excavations and dating reveal about the purpose of Stonehenge?"
    asyncio.run(_run(question))


if __name__ == "__main__":
    main()
