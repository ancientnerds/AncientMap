"""A/B harness: run one full Theo convergence pass and dump quality metrics.

Used to compare the M3 1M-context change (source-content cap) before/after.
The only difference between runs is the env var
``LYRA_MINIMAX_SOURCE_MAX_CONTENT_CHARS`` (e.g. 2000 baseline vs 40000 new) —
the harness itself is identical, so any quality delta is attributable to how
much source text the specialists read.

Run standalone (no research_requests row needed — request_id="" skips the DB
flush). Intended to run inside the api container on the VPS, e.g.:

  docker exec -e LYRA_LLM_BACKEND=minimax \
    -e LYRA_MINIMAX_SOURCE_MAX_CONTENT_CHARS=40000 \
    ancient_nerds_api python scripts/theo_ab_compare.py "QUESTION" new

Prints a single ``=== AB_RESULT === {json}`` line at the end for easy parsing.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time


def _maybe_shrink_config() -> None:
    """AB_SMALL=1 → patch the internally-built ResearchConfig down to a fast
    profile (fewer angles/specialists/rounds). The A/B stays valid because BOTH
    runs use the identical shrunk config; only the source-content cap differs.
    """
    if os.getenv("AB_SMALL") != "1":
        return
    import pipeline.lyra.convergence_orchestrator as co

    _orig = co.ResearchConfig

    def _small():
        c = _orig()
        c.max_angles = 3
        c.initial_specialist_count = 2
        c.min_specialists = 1
        c.max_specialists = 3
        c.max_search_rounds_per_angle = 2
        c.max_debate_rounds = 1
        c.queries_per_angle = 3
        c.source_apis = "minimal"
        return c

    co.ResearchConfig = _small


def _truncation_warnings(debug_log: list) -> int:
    """Count max_tokens / truncation markers in the run's debug log."""
    n = 0
    for entry in debug_log or []:
        blob = json.dumps(entry).lower()
        if "max_tokens" in blob or "truncat" in blob or "before finishing" in blob:
            n += 1
    return n


async def _run(question: str, label: str) -> dict:
    from pipeline.lyra.config import _get_settings

    _maybe_shrink_config()
    from pipeline.lyra.convergence_orchestrator import ConvergenceOrchestrator

    settings = _get_settings()
    cap = settings.minimax_source_max_content_chars
    backend = settings.llm_backend
    print(f"[ab:{label}] backend={backend} source_cap={cap} starting...", flush=True)

    counter = {"n": 0}
    t0 = time.monotonic()

    def emit(event: dict) -> None:
        counter["n"] += 1
        if counter["n"] % 25 == 0:
            mins = (time.monotonic() - t0) / 60.0
            print(
                f"[ab:{label}] {counter['n']} events, {mins:.1f}min, last={event.get('type')}",
                flush=True,
            )

    orch = ConvergenceOrchestrator()
    ctx = await orch.run(question, emit, request_id="")

    dur_min = (time.monotonic() - t0) / 60.0
    qs = ctx.quality_score or {}
    result = {
        "label": label,
        "question": question,
        "source_cap": cap,
        "backend": backend,
        "error": ctx.error or "",
        "duration_min": round(dur_min, 1),
        "total_tokens": ctx.total_tokens,
        "llm_calls": ctx.llm_call_count,
        "citation_sources": len(ctx.registry.sources) if hasattr(ctx, "registry") else 0,
        "specialists": len(getattr(ctx, "specialist_analyses", {}) or {}),
        "paper_chars": len(ctx.paper_text or ""),
        "paper_title": ctx.paper_title or "",
        "quality_score": qs.get("score"),
        "quality_badge": qs.get("badge"),
        "dimensions": qs.get("dimensions", {}),
        "truncation_warnings": _truncation_warnings(getattr(ctx, "debug_log", []) or []),
    }
    return result


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "What do we know about the purpose of Göbekli Tepe?"
    label = sys.argv[2] if len(sys.argv) > 2 else "run"
    try:
        result = asyncio.run(_run(question, label))
    except Exception as exc:  # noqa: BLE001 — surface any failure as a result
        import traceback

        result = {"label": label, "question": question, "error": f"{type(exc).__name__}: {exc}"}
        traceback.print_exc()
    print("=== AB_RESULT === " + json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
