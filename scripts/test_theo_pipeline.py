"""Test Theo pipeline end-to-end with live monitoring.

Usage:
    python scripts/test_theo_pipeline.py
    python scripts/test_theo_pipeline.py --effort note
    python scripts/test_theo_pipeline.py --question "What role did obsidian trade play?"
"""

import argparse
import asyncio
import json
import os
import sys
import time

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before any pipeline imports
load_dotenv()

from pipeline.lyra.theo_pipeline import TheoPipeline


def main():
    parser = argparse.ArgumentParser(description="Test Theo pipeline")
    parser.add_argument(
        "--question",
        default="What is the archaeological evidence for the construction techniques used at Sacsayhuaman in Peru?",
    )
    parser.add_argument("--effort", default="note", choices=["brief", "note", "article", "review", "thesis"])
    parser.add_argument("--output", default="scripts/test_theo_output.md")
    args = parser.parse_args()

    print(f"Question: {args.question}")
    print(f"Effort: {args.effort}")
    print(f"Output: {args.output}")
    print("=" * 60)

    events = []
    start = time.monotonic()

    def emit(event):
        elapsed = time.monotonic() - start
        event["_elapsed"] = round(elapsed, 1)
        events.append(event)

        # Print live status
        etype = event.get("type", "")
        if etype == "pipeline":
            stage = event.get("stage", "")
            status = event.get("status", "")
            dur = event.get("duration_ms")
            meta = event.get("meta", {})
            dur_str = f" ({dur}ms)" if dur else ""
            meta_str = f" {json.dumps(meta)}" if meta else ""
            print(f"[{elapsed:6.1f}s] PIPELINE {stage} -> {status}{dur_str}{meta_str}")
        elif etype == "status":
            content = event.get("content", "")
            print(f"[{elapsed:6.1f}s] STATUS: {content}")
        elif etype == "done":
            print(f"[{elapsed:6.1f}s] DONE: {event.get('status', '')}")

    async def run():
        pipeline = TheoPipeline()
        ctx = await pipeline.run(
            args.question,
            args.effort,
            emit,
            request_id="",  # empty = skip DB cancellation checks
        )
        return ctx

    print("\nStarting pipeline...\n")
    ctx = asyncio.run(run())
    total = time.monotonic() - start

    print(f"\n{'=' * 60}")
    print(f"Total time: {total:.1f}s")

    if ctx.error:
        print(f"ERROR: {ctx.error}")
        sys.exit(1)

    print(f"Paper title: {ctx.paper_title}")
    print(f"Paper length: {len(ctx.paper_text)} chars")
    print(f"Sources found: {len(ctx.registry.sources)}")
    print(f"References cited: {len(ctx.registry.reference_numbers)}")
    print(f"Specialists: {len(ctx.specialist_analyses)}")

    # Audit results
    audit = ctx.audit_result
    print(f"\nCitation audit:")
    print(f"  Passed: {audit.get('passed', False)}")
    print(f"  Total citations: {audit.get('total_citations', 0)}")
    print(f"  Uncited paragraphs: {audit.get('uncited_paragraphs', 0)}")
    print(f"  Invalid markers: {audit.get('invalid_markers', [])}")
    print(f"  Orphaned refs: {audit.get('orphaned_refs', [])}")

    # Quality score
    qs = ctx.quality_score
    if qs:
        print(f"\nQuality score: {qs.get('total', 0)}/100 ({qs.get('badge', '')})")
        dims = qs.get("dimensions", {})
        for k, v in dims.items():
            print(f"  {k}: {v}")
        failures = qs.get("failures", [])
        if failures:
            print(f"\nFailures:")
            for f in failures:
                print(f"  - {f}")
    else:
        print("\nQuality score: not computed (brief/note tier)")

    # Save output
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(ctx.paper_text)
    print(f"\nPaper saved to {args.output}")

    # Save events log
    events_path = args.output.replace(".md", "_events.json")
    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, default=str)
    print(f"Events log saved to {events_path}")


if __name__ == "__main__":
    main()
