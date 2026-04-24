"""Fire a research request at the live API and tail progress via SSE.

Usage:
    python scripts/trigger_test_research.py

Uses the Bitvise tunnel at localhost:18000 and the AUTH_TOKEN env var
(or the hard-coded fallback for this sprint). Prints the new request_id,
then streams status events until the run completes.

On completion, writes the full result payload to
C:/tmp/theo_regen/<request_id>.json so the audit step can reuse it
without re-hitting the API.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import httpx

API_BASE = os.environ.get("THEO_API_BASE", "http://127.0.0.1:18000")
AUTH_TOKEN = os.environ.get(
    "AUTH_TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDIwMDAxMTI3NTYwNjQyNjAiLCJ1c2VyX2lkIjoiMjZlMDYzMWItNjY0Yy00NTg4LTk0M2EtMDk1NjE2YWFjODhiIiwiZXhwIjoxNzc3MjM1NDk3LCJpYXQiOjE3NzY2MzA2OTd9.VvY82-5MQyZ89FlabzhRL7l0zGmKCKIkhfYD0Hz4hw4",
)

SHINING_ONES_QUESTION = (
    "I was always pondering about the Legends of the so called Shining Ones. "
    "What if these were beings from other planets coming to earth, interacting "
    "with early humans, giving them knowledge which results in stories about "
    "ancient egypt gods or Hermes Trismegistus or others like Quetzalcoatle that "
    "came from the skies? What if these beings are so enhanced that we cannot "
    "comprehend it. Could they have skills like manipulating matter via quantum "
    "mechanics to form ancient unexplainable structures like megalithic walls "
    "and polygonal masonry? Please investigate and try to connect the dots on "
    "what you can find! Make sure look left and right and not be contained to "
    "my specific question to connect the dots!"
)

OUT_DIR = pathlib.Path(r"C:/tmp/theo_regen")


def submit(question: str) -> str:
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    resp = httpx.post(
        f"{API_BASE}/api/theo/research",
        headers=headers,
        json={"question": question},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    rid = data["id"]
    print(f"Submitted: {rid} status={data.get('status')} position={data.get('position')}")
    return rid


def poll_until_done(request_id: str) -> dict:
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    last_status = ""
    while True:
        resp = httpx.get(
            f"{API_BASE}/api/theo/research/{request_id}",
            headers=headers,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "?")
        sites = data.get("sites_found", 0)
        if status != last_status:
            print(f"[{time.strftime('%H:%M:%S')}] status={status} sites={sites}")
            last_status = status
        if status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(30)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rid = submit(SHINING_ONES_QUESTION)

    start = time.time()
    data = poll_until_done(rid)
    elapsed = int(time.time() - start)
    print(f"\nRun finished in {elapsed}s with status={data.get('status')}")

    out_path = OUT_DIR / f"{rid}.json"
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Saved result: {out_path}")
    return 0 if data.get("status") == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
