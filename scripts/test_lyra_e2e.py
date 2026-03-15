#!/usr/bin/env python3
"""End-to-end local test for the Lyra pipeline.

Runs the full agent stream locally and prints every event.
Requires: local Docker DB + Qdrant, .env with API keys.

Usage:
    python scripts/test_lyra_e2e.py "any tunnels beneath Sacsayhuaman?"
    python scripts/test_lyra_e2e.py --debug "Sacsayhuaman tunnels youtube"
    python scripts/test_lyra_e2e.py --json "query"   # Structured JSON output
"""

import asyncio
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


async def run_test(query: str, debug: bool = False, json_output: bool = False):
    from api.services.lyra_agent import run_agent_stream

    if not json_output:
        print(f"\n{'='*70}")
        print(f"QUERY: {query}")
        print(f"{'='*70}\n")

    t0 = time.monotonic()
    events = []

    from api.services.lyra_router import RequestContext, set_request_context, route_request

    # Use the real router so LYRA_LLM_BACKEND env var is respected
    backend = os.getenv("LYRA_LLM_BACKEND", "mercury")
    ctx = route_request(backend, query)
    set_request_context(ctx)

    async for event in run_agent_stream(
        message=query,
        context_type="global",
        context_id=None,
        context_year=None,
        history=[],
        ctx=ctx,
    ):
        events.append(event)
        etype = event.get("type", "?")

        if not json_output:
            if etype == "pipeline":
                stage = event.get("stage", "?")
                status = event.get("status", "?")
                ms = event.get("duration_ms")
                meta = event.get("meta", {})
                ms_str = f" ({ms}ms)" if ms is not None else ""
                meta_str = f" | {json.dumps(meta, default=str)[:200]}" if meta else ""
                print(f"  [{stage}] {status}{ms_str}{meta_str}")

            elif etype == "diffusion":
                content = event.get("content", "")
                print(f"\n  === LLM RESPONSE ({len(content)} chars) ===")
                print(f"  {content[:500]}")
                if len(content) > 500:
                    print(f"  ... ({len(content) - 500} more chars)")
                print("  === END RESPONSE ===\n")

            elif etype == "status":
                print(f"  [status] {event.get('content', '')}")

            elif etype == "sites":
                sites = event.get("sites", [])
                print(f"  [sites] {len(sites)} sites for map")
                if debug:
                    for s in sites[:3]:
                        print(f"    - {s.get('name')} ({s.get('country')})")

            elif etype == "news":
                news = event.get("news", [])
                print(f"  [news] {len(news)} news items")
                for n in news[:5]:
                    print(f"    - {n.get('headline')} ({n.get('channel', '?')})")
                    if n.get("video_id"):
                        print(f"      video: {n['video_id']}, ts: {n.get('timestamp_seconds')}")

            elif etype == "done":
                meta = event.get("metadata", {})
                tokens = meta.get("tokens", {})
                print(f"\n  [DONE] {meta.get('tool_calls', 0)} tools, "
                      f"{meta.get('sites_found', 0)} sites, "
                      f"LLM: {tokens.get('input', 0)+tokens.get('output', 0)} tok, "
                      f"Embed: {tokens.get('voyage', 0)} tok")

            elif etype == "thinking":
                if debug:
                    print(f"  [thinking] {event.get('content', '')[:100]}")

            elif etype == "error":
                print(f"  [ERROR] {event.get('error', '?')}")

    elapsed = time.monotonic() - t0

    # JSON output mode — structured result for scripting
    if json_output:
        diffusion_events = [e for e in events if e.get("type") == "diffusion"]
        news_events = [e for e in events if e.get("type") == "news"]
        site_events = [e for e in events if e.get("type") == "sites"]
        done_events = [e for e in events if e.get("type") == "done"]
        result = {
            "query": query,
            "content": diffusion_events[-1].get("content", "") if diffusion_events else "",
            "sites": [s for ev in site_events for s in ev.get("sites", [])],
            "news": [n for ev in news_events for n in ev.get("news", [])],
            "metadata": done_events[-1].get("metadata", {}) if done_events else {},
            "elapsed_s": round(elapsed, 1),
            "event_count": len(events),
            "error": next((e.get("error") for e in events if e.get("type") == "error"), None),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return

    print(f"\n  Total time: {elapsed:.1f}s")
    print(f"  Total events: {len(events)}")

    # Show the final response content
    diffusion_events = [e for e in events if e.get("type") == "diffusion"]
    if diffusion_events:
        final = diffusion_events[-1].get("content", "")
        print(f"\n{'='*70}")
        print("FINAL ANSWER:")
        print(f"{'='*70}")
        print(final)
    else:
        print("\n  WARNING: No diffusion events — no text was emitted!")

    # Show what news was found
    news_events = [e for e in events if e.get("type") == "news"]
    if news_events:
        print(f"\n{'='*70}")
        print("NEWS IN SIDEBAR:")
        print(f"{'='*70}")
        for ne in news_events:
            for n in ne.get("news", []):
                vid = n.get("video_id", "")
                ts = n.get("timestamp_seconds", "")
                print(f"  - {n.get('headline')} [{n.get('channel')}]")
                if vid:
                    print(f"    https://youtube.com/watch?v={vid}" + (f"&t={ts}s" if ts else ""))


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="any tunnels beneath Sacsayhuaman? can you check youtube?")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--json", action="store_true", help="Output structured JSON (for scripting)")
    args = parser.parse_args()

    asyncio.run(run_test(args.query, debug=args.debug, json_output=args.json))


if __name__ == "__main__":
    main()
