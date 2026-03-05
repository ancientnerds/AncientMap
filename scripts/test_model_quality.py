"""Test Qwen3.5:2b quality with think=ON vs think=OFF.

Matches the pipeline's two-tier architecture:
  - trivial: think=false (greetings, meta, short reactions)
  - heavy:   think=true  (archaeology queries, tool calling)
"""

import sys
import io
import json
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen3.5:2b"

# System prompt (shortened version of Lyra's)
SYSTEM = """You are LYRA WHISKERBYTE, an archaeological AI agent for the Ancient Nerds Map project.
You help users explore archaeological sites, ancient civilizations, and discoveries.
Be concise, knowledgeable, and cite specific sites when possible.

## CRITICAL: No Hallucination
- NEVER list sites from general knowledge alone. Only mention specific sites from tool results.
- If asked about sites in a region, use the vector_search tool — do NOT guess.

## Off-Topic Handling
- You are an archaeology specialist. Politely decline non-archaeology requests.
- For cooking, coding, math, etc.: "I'm built for archaeology! I can help you
  explore ancient sites, civilizations, and discoveries. What would you like to know?"
- Exception: greetings and casual conversation are fine."""

# Tool definition for site search
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "vector_search",
            "description": "Search archaeological sites by semantic query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "collection": {
                        "type": "string",
                        "enum": ["sites", "news"],
                        "description": "Collection to search",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 5)",
                    },
                    "country": {
                        "type": "string",
                        "description": "Filter by country name",
                    },
                },
                "required": ["query"],
            },
        },
    }
]

# Test cases: each specifies which think mode to use
TESTS = [
    # --- Trivial tier (think=OFF) ---
    {
        "name": "Greeting (trivial)",
        "think": False,
        "messages": [{"role": "user", "content": "Hello Lyra!"}],
        "use_tools": False,
        "criteria": "Warm greeting, stay in character",
        "check": lambda r: len(r["content"]) > 20,
    },
    {
        "name": "Off-topic (trivial)",
        "think": False,
        "messages": [{"role": "user", "content": "How do you cook pasta?"}],
        "use_tools": False,
        "criteria": "Redirect to archaeology",
        "check": lambda r: any(
            kw in r["content"].lower()
            for kw in ("archaeol", "ancient", "built for", "specializ")
        ),
    },
    {
        "name": "Meta question (trivial)",
        "think": False,
        "messages": [{"role": "user", "content": "What can you do?"}],
        "use_tools": False,
        "criteria": "Describe capabilities, mention archaeology",
        "check": lambda r: len(r["content"]) > 30,
    },
    # --- Heavy tier (think=ON) ---
    {
        "name": "Site query Crete (heavy)",
        "think": True,
        "messages": [{"role": "user", "content": "What ancient sites can be found on the island of Crete?"}],
        "use_tools": True,
        "criteria": "Must call vector_search, not hallucinate",
        "check": lambda r: len(r["tool_calls"]) > 0,
    },
    {
        "name": "Search Egypt (heavy)",
        "think": True,
        "messages": [{"role": "user", "content": "Search for pyramid sites in Egypt"}],
        "use_tools": True,
        "criteria": "Must call vector_search with Egypt",
        "check": lambda r: any(
            tc["name"] == "vector_search" and "egypt" in json.dumps(tc["args"]).lower()
            for tc in r["tool_calls"]
        ),
    },
    {
        "name": "Civilizations (heavy)",
        "think": True,
        "messages": [{"role": "user", "content": "What's the difference between the Minoan and Mycenaean civilizations?"}],
        "use_tools": False,
        "criteria": "Explain key differences substantively",
        "check": lambda r: len(r["content"]) > 50,
    },
    {
        "name": "Trip to Turkey (heavy)",
        "think": True,
        "messages": [{"role": "user", "content": "I'm planning a trip to Turkey. What are the most important archaeological sites I should visit?"}],
        "use_tools": True,
        "criteria": "Must call vector_search for Turkey sites",
        "check": lambda r: len(r["tool_calls"]) > 0,
    },
]


def run_test(test: dict) -> dict:
    """Run a single test using Ollama native /api/chat."""
    messages = [{"role": "system", "content": SYSTEM}] + test["messages"]

    body: dict = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "think": test["think"],
        "options": {"num_predict": 4096, "temperature": 0.7},
    }
    if test["use_tools"]:
        body["tools"] = TOOLS

    start = time.time()
    thinking_text = ""
    content_text = ""
    tool_calls: list[dict] = []
    first_token: float | None = None
    prompt_tokens = 0
    completion_tokens = 0

    try:
        with httpx.stream(
            "POST",
            f"{OLLAMA_URL}/api/chat",
            json=body,
            timeout=120.0,
        ) as resp:
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = chunk.get("message", {})

                thinking = msg.get("thinking", "")
                if thinking:
                    thinking_text += thinking
                    if first_token is None:
                        first_token = time.time()

                content = msg.get("content", "")
                if content:
                    content_text += content
                    if first_token is None:
                        first_token = time.time()

                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        fn = tc.get("function", {})
                        tool_calls.append({
                            "name": fn.get("name", ""),
                            "args": fn.get("arguments", {}),
                        })

                if chunk.get("done"):
                    prompt_tokens = chunk.get("prompt_eval_count", 0) or 0
                    completion_tokens = chunk.get("eval_count", 0) or 0

        elapsed = time.time() - start
        ttft = (first_token - start) if first_token else elapsed

        return {
            "success": True,
            "thinking": thinking_text,
            "content": content_text,
            "tool_calls": tool_calls,
            "elapsed": elapsed,
            "ttft": ttft,
            "tokens": prompt_tokens + completion_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tok_per_sec": completion_tokens / elapsed if elapsed > 0 else 0,
            "think_enabled": test["think"],
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "elapsed": time.time() - start,
        }


def main():
    print(f"Model: {MODEL}")
    print(f"Ollama: {OLLAMA_URL}")
    print("=" * 80)

    results: list[dict] = []

    for test in TESTS:
        think_label = "think=ON" if test["think"] else "think=OFF"
        tier = "HEAVY" if test["think"] else "TRIVIAL"
        print(f"\n{'='*80}")
        print(f"TEST: {test['name']} [{tier}] ({think_label})")
        print(f"Criteria: {test['criteria']}")
        print("-" * 80)

        result = run_test(test)
        result["test_name"] = test["name"]
        result["tier"] = tier
        results.append(result)

        if not result["success"]:
            print(f"  ERROR: {result.get('error', 'unknown')}")
            continue

        print(
            f"  Time: {result['elapsed']:.1f}s | TTFT: {result['ttft']:.1f}s"
            f" | Tok/s: {result['tok_per_sec']:.1f}"
            f" | Tokens: {result['prompt_tokens']}+{result['completion_tokens']}"
        )

        if result["thinking"]:
            think_preview = result["thinking"][:200].replace("\n", " ")
            print(f"  Thinking: {think_preview}...")

        if result["tool_calls"]:
            for tc in result["tool_calls"]:
                print(f"  Tool: {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})")

        if result["content"]:
            content_preview = result["content"][:300].replace("\n", " ")
            print(f"  Response: {content_preview}")
            if len(result["content"]) > 300:
                print(f"  ... ({len(result['content'])} chars total)")

        passed = test["check"](result)
        print(f"  Quality: {'PASS' if passed else 'FAIL'}")

    # Summary
    print(f"\n\n{'='*80}")
    print("SUMMARY")
    print("=" * 80)
    header = f"{'Test':<30} {'Tier':<8} {'Think':>5} {'Time':>6} {'TTFT':>6} {'Tok/s':>6} {'Tools':>5} {'Resp':>6} {'Quality':>7}"
    print(header)
    print("-" * 80)

    trivial_pass = trivial_total = heavy_pass = heavy_total = 0
    trivial_time = heavy_time = 0.0

    for i, test in enumerate(TESTS):
        r = results[i]
        if not r["success"]:
            print(f"{test['name']:<30} {'ERR':<8}")
            continue
        tools = len(r.get("tool_calls", []))
        resp_len = len(r.get("content", ""))
        passed = test["check"](r)
        think = "ON" if r["think_enabled"] else "OFF"
        tier = r["tier"]

        if tier == "TRIVIAL":
            trivial_total += 1
            trivial_time += r["elapsed"]
            if passed:
                trivial_pass += 1
        else:
            heavy_total += 1
            heavy_time += r["elapsed"]
            if passed:
                heavy_pass += 1

        print(
            f"{test['name']:<30} {tier:<8} {think:>5}"
            f" {r['elapsed']:>5.1f}s {r['ttft']:>5.1f}s"
            f" {r['tok_per_sec']:>5.1f}"
            f" {tools:>5} {resp_len:>6}"
            f" {'PASS' if passed else 'FAIL':>7}"
        )

    print("-" * 80)
    if trivial_total:
        print(f"  TRIVIAL (think=OFF): {trivial_pass}/{trivial_total} passed | avg {trivial_time/trivial_total:.1f}s")
    if heavy_total:
        print(f"  HEAVY   (think=ON):  {heavy_pass}/{heavy_total} passed | avg {heavy_time/heavy_total:.1f}s")
    total_pass = trivial_pass + heavy_pass
    total_total = trivial_total + heavy_total
    print(f"  OVERALL: {total_pass}/{total_total} passed")


if __name__ == "__main__":
    main()
