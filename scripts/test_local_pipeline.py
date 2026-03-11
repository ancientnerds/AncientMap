"""Test Lyra chat pipeline against local Ollama."""

import sys
import io

# Fix Windows console encoding for emoji
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import httpx
import jwt
import datetime
import time

API_BASE = "http://localhost:8000/api/lyra"
SECRET = "4f8927dba790534df560a10c3fbafb4bf837a0794c0551b838fe4be801455a2f"

# Generate test JWT
token = jwt.encode(
    {
        "sub": "test_user_123",
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
        "iat": datetime.datetime.now(datetime.UTC),
    },
    SECRET,
    algorithm="HS256",
)

HEADERS = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_chat(message: str, label: str):
    """Send a chat request and stream the SSE response."""
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"Message: {message}")
    print(f"{'='*60}")

    start = time.time()
    body = {"message": message, "backend": "local"}

    try:
        with httpx.stream(
            "POST",
            f"{API_BASE}/chat",
            json=body,
            headers=HEADERS,
            timeout=120.0,
        ) as resp:
            if resp.status_code != 200:
                print(f"ERROR: HTTP {resp.status_code}")
                print(resp.read().decode())
                return False

            first_token_time = None
            token_count = 0
            full_response = ""

            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break

                import json

                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue

                ev_type = ev.get("type", "")

                if ev_type == "token":
                    if first_token_time is None:
                        first_token_time = time.time()
                    token_count += 1
                    content = ev.get("content", "")
                    full_response += content
                    print(content, end="", flush=True)
                elif ev_type == "thinking":
                    content = ev.get("content", "")
                    print(f"[think] {content}", end="", flush=True)
                elif ev_type == "pipeline":
                    stage = ev.get("stage", "")
                    meta = ev.get("meta") or {}
                    if stage == "pipeline_init":
                        tier = meta.get("tier", "?")
                        cls = meta.get("classification", "")
                        print(f"\n  [pipeline] {stage}: tier={tier} ({cls})")
                    else:
                        detail = ev.get("detail", "")
                        print(f"\n  [pipeline] {stage}: {detail}")
                elif ev_type == "sites":
                    sites = ev.get("sites", [])
                    print(f"\n  [sites] {len(sites)} sites retrieved")
                elif ev_type == "error":
                    print(f"\n  [ERROR] {ev.get('message', '')}")
                    return False
                elif ev_type == "done":
                    model = ev.get("model", "")
                    tier = ev.get("tier", "")
                    print(f"\n  [done] model={model}, tier={tier}")

            elapsed = time.time() - start
            ttft = (first_token_time - start) if first_token_time else None

            print(f"\n\n--- Results ---")
            print(f"Total time: {elapsed:.1f}s")
            if ttft:
                print(f"Time to first token: {ttft:.1f}s")
            print(f"Tokens: {token_count}")
            if token_count > 0 and elapsed > 0:
                print(f"Tokens/sec: {token_count / elapsed:.1f}")
            print(f"Response length: {len(full_response)} chars")
            return True

    except httpx.ReadTimeout:
        elapsed = time.time() - start
        print(f"\nTIMEOUT after {elapsed:.1f}s")
        return False
    except Exception as e:
        print(f"\nEXCEPTION: {e}")
        return False


if __name__ == "__main__":
    results = {}

    # Test 1: Simple greeting -> should route to 0.8B fast tier
    results["fast_greeting"] = test_chat("Hello Lyra!", "Fast tier (0.8B) - Greeting")

    # Test 2: Complex query -> should route to 4B heavy tier
    results["heavy_query"] = test_chat(
        "What ancient sites can be found on the island of Crete?",
        "Heavy tier (4B) - Complex archaeology query",
    )

    # Summary
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    if all(results.values()):
        print("\nAll tests passed!")
        sys.exit(0)
    else:
        print("\nSome tests FAILED!")
        sys.exit(1)
