#!/usr/bin/env python3
"""Minimal test: verify Mercury 2 accepts reasoning_effort parameter.

Usage:
    python scripts/test_mercury_reasoning.py

Requires LYRA_API_KEY env var (or in .env).
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("LYRA_API_KEY") or os.getenv("LYRA_ANTHROPIC_API_KEY")
base_url = os.getenv("LYRA_BASE_URL", "https://api.inceptionlabs.ai/v1")

if not api_key:
    print("ERROR: Set LYRA_API_KEY in .env or environment")
    sys.exit(1)

from openai import OpenAI

client = OpenAI(base_url=base_url, api_key=api_key, timeout=30.0)

EFFORTS = ["low", "medium", "high"]

for effort in EFFORTS:
    print(f"\n--- Testing reasoning_effort={effort!r} ---")
    try:
        resp = client.chat.completions.create(
            model="mercury-2",
            messages=[{"role": "user", "content": "What is 2+2? Reply in one word."}],
            max_tokens=64,
            reasoning_effort=effort,
        )
        text = resp.choices[0].message.content
        print(f"  OK: {text!r}")
    except Exception as e:
        print(f"  FAILED: {e}")
        print("  Trying extra_body fallback...")
        try:
            resp = client.chat.completions.create(
                model="mercury-2",
                messages=[{"role": "user", "content": "What is 2+2? Reply in one word."}],
                max_tokens=64,
                extra_body={"reasoning_effort": effort},
            )
            text = resp.choices[0].message.content
            print(f"  OK (via extra_body): {text!r}")
        except Exception as e2:
            print(f"  ALSO FAILED: {e2}")

print("\nDone.")
