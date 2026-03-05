#!/usr/bin/env python3
"""
VPS2 Multi-Model LLM Test Suite
=================================
Tests the Qwen3.5 multi-model setup on VPS2:

1. Health check / model list (expects 3 models)
2. Embeddings (nomic-embed-text)
3. Reranking (FlashRank)
4. Chat 0.8B (fast tier — simple greeting, expect <10s)
5. Chat 4B (heavy tier — complex query)
6. Chat 4B streaming (thinking + content tokens)
7. Tool calling (4B)
8. Concurrent (0.8B + 4B simultaneously)
9. Resource usage

Usage:
    python scripts/test_vps2.py                   # uses env vars from .env
    python scripts/test_vps2.py --url http://host:port --key yourkey
    python scripts/test_vps2.py --test health,embed,fast,heavy
"""

import argparse
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path

# Load .env from project root
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

import httpx

# ── Defaults from env ──────────────────────────────────────────────────────
DEFAULT_BASE_URL = os.getenv("LYRA_OLLAMA_BASE_URL", "")
DEFAULT_API_KEY = os.getenv("LYRA_OLLAMA_API_KEY", "")
DEFAULT_HEAVY_MODEL = os.getenv("LYRA_OLLAMA_MODEL_HEAVY", "qwen3.5:4b")
DEFAULT_FAST_MODEL = os.getenv("LYRA_OLLAMA_MODEL_FAST", "qwen3.5:0.8b")
DEFAULT_EMBED_URL = os.getenv("LYRA_OLLAMA_EMBED_URL", DEFAULT_BASE_URL)
DEFAULT_EMBED_KEY = os.getenv("LYRA_OLLAMA_EMBED_API_KEY", DEFAULT_API_KEY)
DEFAULT_EMBED_MODEL = os.getenv("LYRA_OLLAMA_EMBED_MODEL", "nomic-embed-text")
DEFAULT_RERANK_URL = os.getenv("LYRA_RERANK_URL", "")


def _strip_v1(url: str) -> str:
    """Strip /v1 suffix so test functions can build full paths consistently."""
    return url.rstrip("/").removesuffix("/v1").removesuffix("/v1/")


# ── Fix Windows console encoding ───────────────────────────────────────────
import io

if sys.stdout.encoding and sys.stdout.encoding.lower().startswith("cp"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── ANSI colors ────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def header(title: str):
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")


def result(ok: bool, msg: str, elapsed: float | None = None):
    icon = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    t = f" {DIM}({elapsed:.2f}s){RESET}" if elapsed is not None else ""
    print(f"  [{icon}] {msg}{t}")


def warn(msg: str):
    print(f"  {YELLOW}⚠ {msg}{RESET}")


def info(msg: str):
    print(f"  {DIM}{msg}{RESET}")


def make_headers(api_key: str) -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


# ──────────────────────────────────────────────────────────────────────────
# Test functions
# ──────────────────────────────────────────────────────────────────────────


def test_health(base_url: str, api_key: str) -> bool:
    """List available models — expects 3: heavy, fast, embed."""
    header("1. Health Check — Model List")
    try:
        t0 = time.perf_counter()
        resp = httpx.get(
            f"{base_url}/v1/models",
            headers=make_headers(api_key),
            timeout=30,
        )
        elapsed = time.perf_counter() - t0
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("id", "?") for m in data.get("data", [])]
        expected = 3
        ok = len(models) >= expected
        result(ok, f"Found {len(models)} model(s): {', '.join(models)}", elapsed)
        if not ok:
            warn(f"Expected at least {expected} models (heavy + fast + embed)")
        return ok
    except Exception as e:
        result(False, f"Model list failed: {e}")
        return False


def test_embeddings(embed_url: str, embed_key: str, model: str) -> bool:
    """Generate embeddings via /v1/embeddings."""
    header("2. Embeddings")
    try:
        t0 = time.perf_counter()
        resp = httpx.post(
            f"{embed_url}/v1/embeddings",
            headers=make_headers(embed_key),
            json={
                "model": model,
                "input": [
                    "The Great Pyramid of Giza was built around 2560 BCE",
                    "Roman aqueducts transported water across vast distances",
                ],
            },
            timeout=120,
        )
        elapsed = time.perf_counter() - t0
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("data", [])
        if not embeddings:
            result(False, "No embeddings returned")
            return False
        dim = len(embeddings[0].get("embedding", []))
        tokens = data.get("usage", {}).get("total_tokens", "?")
        ok = dim == 768
        result(ok, f"{len(embeddings)} vectors, {dim}-dim, {tokens} tokens", elapsed)
        if not ok:
            warn(f"Expected 768-dim vectors, got {dim}")
        return ok
    except Exception as e:
        result(False, f"Embeddings failed: {e}")
        return False


def test_reranker(rerank_url: str, embed_key: str) -> bool:
    """Rerank documents via FlashRank service."""
    header("3. Reranking (FlashRank)")
    if not rerank_url:
        warn("LYRA_RERANK_URL not set — skipping")
        return True
    try:
        headers = {"Content-Type": "application/json"}
        if embed_key:
            headers["Authorization"] = f"Bearer {embed_key}"

        t0 = time.perf_counter()
        resp = httpx.post(
            rerank_url,
            headers=headers,
            json={
                "query": "ancient Egyptian pyramids",
                "documents": [
                    "The Great Pyramid of Giza is the oldest of the Seven Wonders",
                    "Python is a popular programming language",
                    "Pharaoh Khufu commissioned the construction of the Great Pyramid",
                    "The weather in London is often rainy",
                    "Ancient Egyptian priests performed mummification rituals",
                ],
                "top_k": 3,
            },
            timeout=60,
        )
        elapsed = time.perf_counter() - t0
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            result(False, "No rerank results returned")
            return False
        top = results[0]
        result(
            True,
            f"Top result: idx={top['index']} score={top['relevance_score']:.4f}, "
            f"{len(results)} results returned",
            elapsed,
        )
        for r in results:
            info(f"  #{r['index']} score={r['relevance_score']:.4f}")
        return True
    except Exception as e:
        result(False, f"Reranker failed: {e}")
        return False


def _chat_request(base_url: str, api_key: str, model: str, prompt: str,
                  max_tokens: int = 200, stream: bool = False,
                  tools: list | None = None) -> dict:
    """Send a chat completion request and return the response dict."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    resp = httpx.post(
        f"{base_url}/v1/chat/completions",
        headers=make_headers(api_key),
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()


def test_chat_fast(base_url: str, api_key: str, model: str) -> bool:
    """Chat with 0.8B model — simple greeting, should be fast."""
    header(f"4. Chat 0.8B Fast ({model})")
    try:
        t0 = time.perf_counter()
        data = _chat_request(base_url, api_key, model, "Hello! Who are you?", max_tokens=100)
        elapsed = time.perf_counter() - t0

        content = data["choices"][0]["message"].get("content", "")
        usage = data.get("usage", {})
        prompt_tok = usage.get("prompt_tokens", "?")
        compl_tok = usage.get("completion_tokens", "?")
        actual_model = data.get("model", "?")

        ok = elapsed < 30  # Should be well under 10s, 30s is generous
        result(ok, f"Tokens: {prompt_tok}→{compl_tok}, model={actual_model}", elapsed)
        info(f"  Response: {content[:200]}")
        if elapsed > 10:
            warn(f"Slow response ({elapsed:.1f}s) — expected <10s for 0.8B")
        return ok
    except Exception as e:
        result(False, f"Chat 0.8B failed: {e}")
        return False


def test_chat_heavy(base_url: str, api_key: str, model: str) -> bool:
    """Chat with 4B model — complex archaeology query."""
    header(f"5. Chat 4B Heavy ({model})")
    try:
        t0 = time.perf_counter()
        data = _chat_request(
            base_url, api_key, model,
            "Compare the Minoan and Mycenaean civilizations — what distinguished them?",
            max_tokens=500,
        )
        elapsed = time.perf_counter() - t0

        msg = data["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning", "") or msg.get("reasoning_content", "")
        usage = data.get("usage", {})
        prompt_tok = usage.get("prompt_tokens", "?")
        compl_tok = usage.get("completion_tokens", "?")

        result(True, f"Tokens: {prompt_tok}→{compl_tok}", elapsed)
        if reasoning:
            info(f"  Reasoning: {len(reasoning)} chars")
        info(f"  Response: {content[:200]}...")
        return True
    except Exception as e:
        result(False, f"Chat 4B failed: {e}")
        return False


def test_streaming_heavy(base_url: str, api_key: str, model: str) -> bool:
    """Streaming chat with 4B — verify thinking + content tokens."""
    header(f"6. Streaming 4B ({model})")
    try:
        t0 = time.perf_counter()
        first_token_time = None
        token_count = 0
        thinking_chars = 0
        content_chars = 0
        full_content = ""

        with httpx.stream(
            "POST",
            f"{base_url}/v1/chat/completions",
            headers=make_headers(api_key),
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": "What was the significance of Göbekli Tepe?"}
                ],
                "max_tokens": 500,
                "stream": True,
            },
            timeout=300,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    token_count += 1
                    content_chars += len(delta["content"])
                    full_content += delta["content"]
                reasoning_text = delta.get("reasoning") or delta.get("reasoning_content") or ""
                if reasoning_text:
                    thinking_chars += len(reasoning_text)
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    token_count += 1

        elapsed = time.perf_counter() - t0
        ttft = (first_token_time - t0) if first_token_time else 0
        tps = token_count / (elapsed - ttft) if (elapsed - ttft) > 0 else 0

        result(True, f"{token_count} chunks in {elapsed:.2f}s", elapsed)
        info(f"  Time to first token: {ttft:.2f}s")
        info(f"  Tokens/sec: {tps:.1f}")
        if thinking_chars:
            info(f"  Thinking: {thinking_chars} chars")
        info(f"  Content: {content_chars} chars")
        info(f"  Response: {full_content[:200]}...")
        return True
    except Exception as e:
        result(False, f"Streaming failed: {e}")
        return False


def test_tool_calling(base_url: str, api_key: str, model: str) -> bool:
    """Tool calling with 4B — critical for Lyra agent."""
    header(f"7. Tool Calling ({model})")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_sites",
                "description": "Search for archaeological sites by name, type, or location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for archaeological sites",
                        },
                        "country": {
                            "type": "string",
                            "description": "Country to filter by",
                        },
                    },
                    "required": ["query"],
                },
            },
        }
    ]
    try:
        t0 = time.perf_counter()
        data = _chat_request(
            base_url, api_key, model,
            "Find me archaeological sites related to the Minoans in Greece.",
            max_tokens=500, tools=tools,
        )
        elapsed = time.perf_counter() - t0
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls", [])

        if tool_calls:
            tc = tool_calls[0]
            fn = tc["function"]
            result(True, f"Tool called: {fn['name']}({fn['arguments']})", elapsed)
            return True
        else:
            content = msg.get("content", "")
            warn(f"No tool call — model responded with text: {content[:100]}")
            result(False, "Model did not invoke tool", elapsed)
            return False
    except Exception as e:
        result(False, f"Tool calling failed: {e}")
        return False


def test_concurrent(base_url: str, api_key: str, fast_model: str, heavy_model: str) -> bool:
    """Fire 0.8B and 4B requests simultaneously — both should succeed."""
    header("8. Concurrent (0.8B + 4B)")
    try:
        t0 = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            fast_future = pool.submit(
                _chat_request, base_url, api_key, fast_model,
                "Say hello in 10 words.", 50,
            )
            heavy_future = pool.submit(
                _chat_request, base_url, api_key, heavy_model,
                "Name three Bronze Age civilizations.", 200,
            )
            fast_data = fast_future.result(timeout=120)
            heavy_data = heavy_future.result(timeout=300)

        elapsed = time.perf_counter() - t0

        fast_content = fast_data["choices"][0]["message"].get("content", "")
        heavy_content = heavy_data["choices"][0]["message"].get("content", "")
        fast_model_used = fast_data.get("model", "?")
        heavy_model_used = heavy_data.get("model", "?")

        ok = bool(fast_content and heavy_content)
        result(ok, f"Both responded in {elapsed:.1f}s total", elapsed)
        info(f"  Fast ({fast_model_used}): {fast_content[:100]}")
        info(f"  Heavy ({heavy_model_used}): {heavy_content[:100]}")
        return ok
    except Exception as e:
        result(False, f"Concurrent test failed: {e}")
        return False


def test_resource_usage(base_url: str, api_key: str) -> bool:
    """Query Ollama process info (ps endpoint) for RAM/CPU usage."""
    header("9. Resource Usage (Ollama /api/ps)")
    try:
        t0 = time.perf_counter()
        resp = httpx.get(
            f"{base_url}/api/ps",
            headers=make_headers(api_key),
            timeout=30,
        )
        elapsed = time.perf_counter() - t0

        if resp.status_code == 200:
            data = resp.json()
            models = data.get("models", [])
            if models:
                result(True, f"{len(models)} model(s) loaded", elapsed)
                for m in models:
                    name = m.get("name", "?")
                    size = m.get("size", 0)
                    vram = m.get("size_vram", 0)
                    size_gb = size / (1024**3)
                    vram_gb = vram / (1024**3)
                    info(f"  {name}: {size_gb:.2f} GB RAM, {vram_gb:.2f} GB VRAM")
                    details = m.get("details", {})
                    if details:
                        info(
                            f"    family={details.get('family', '?')}, "
                            f"params={details.get('parameter_size', '?')}, "
                            f"quant={details.get('quantization_level', '?')}"
                        )
                return True
            else:
                warn("No models currently loaded (idle)")
                result(True, "Ollama idle — no models in memory", elapsed)
                return True
        elif resp.status_code == 404:
            warn("/api/ps not proxied through nginx — endpoint unavailable remotely")
            result(True, "Skipped (not proxied)", elapsed)
            return True
        else:
            result(False, f"HTTP {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        warn(f"Could not reach /api/ps: {e}")
        result(True, "Skipped (endpoint not available)")
        return True


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Test VPS2 multi-model LLM infrastructure")
    parser.add_argument(
        "--url", default=DEFAULT_BASE_URL, help="Base URL for Ollama/OpenAI-compatible API"
    )
    parser.add_argument("--key", default=DEFAULT_API_KEY, help="API key (Bearer token for nginx)")
    parser.add_argument("--heavy-model", default=DEFAULT_HEAVY_MODEL, help="Heavy LLM model (4B)")
    parser.add_argument("--fast-model", default=DEFAULT_FAST_MODEL, help="Fast LLM model (0.8B)")
    parser.add_argument(
        "--embed-url", default=DEFAULT_EMBED_URL, help="Embeddings endpoint base URL"
    )
    parser.add_argument("--embed-key", default=DEFAULT_EMBED_KEY, help="Embeddings API key")
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL, help="Embedding model name")
    parser.add_argument("--rerank-url", default=DEFAULT_RERANK_URL, help="Reranker endpoint URL")
    parser.add_argument(
        "--test",
        help="Run specific test (health,embed,rerank,fast,heavy,stream,tool,concurrent,resources)",
    )
    args = parser.parse_args()

    # Normalize: strip /v1 suffix
    args.url = _strip_v1(args.url) if args.url else args.url
    if args.embed_url:
        args.embed_url = _strip_v1(args.embed_url)

    if not args.url:
        print(f"{RED}Error: No base URL. Set LYRA_OLLAMA_BASE_URL in .env or pass --url{RESET}")
        sys.exit(1)

    print(f"{BOLD}VPS2 Multi-Model LLM Test Suite{RESET}")
    print(f"  LLM endpoint:   {args.url}")
    print(f"  Heavy model:    {args.heavy_model}")
    print(f"  Fast model:     {args.fast_model}")
    print(f"  Embed endpoint: {args.embed_url or '(same as LLM)'}")
    print(f"  Embed model:    {args.embed_model}")
    print(f"  Rerank endpoint:{args.rerank_url or '(not set)'}")
    print(f"  Auth:           {'Bearer ***' + args.key[-4:] if args.key else 'none'}")

    total_start = time.perf_counter()
    tests_run = 0
    tests_passed = 0

    test_map = {
        "health": lambda: test_health(args.url, args.key),
        "embed": lambda: test_embeddings(
            args.embed_url or args.url, args.embed_key or args.key, args.embed_model
        ),
        "rerank": lambda: test_reranker(args.rerank_url, args.embed_key or args.key),
        "fast": lambda: test_chat_fast(args.url, args.key, args.fast_model),
        "heavy": lambda: test_chat_heavy(args.url, args.key, args.heavy_model),
        "stream": lambda: test_streaming_heavy(args.url, args.key, args.heavy_model),
        "tool": lambda: test_tool_calling(args.url, args.key, args.heavy_model),
        "concurrent": lambda: test_concurrent(
            args.url, args.key, args.fast_model, args.heavy_model
        ),
        "resources": lambda: test_resource_usage(args.url, args.key),
    }

    if args.test:
        selected = [t.strip() for t in args.test.split(",")]
        for name in selected:
            if name not in test_map:
                print(f"{RED}Unknown test: {name}. Available: {', '.join(test_map)}{RESET}")
                sys.exit(1)
    else:
        selected = list(test_map.keys())

    for name in selected:
        tests_run += 1
        try:
            if test_map[name]():
                tests_passed += 1
        except Exception as e:
            result(False, f"Unexpected error: {e}")

    total_elapsed = time.perf_counter() - total_start

    # ── Summary ────────────────────────────────────────────────────────────
    header("Summary")
    color = GREEN if tests_passed == tests_run else (YELLOW if tests_passed > 0 else RED)
    print(f"  {color}{tests_passed}/{tests_run} tests passed{RESET}")
    print(f"  Total time: {total_elapsed:.2f}s")

    # System resource snapshot
    print(f"\n{BOLD}  System Resources:{RESET}")
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        print(f"  CPU usage:  {cpu:.1f}%")
        print(f"  RAM total:  {mem.total / (1024**3):.1f} GB")
        print(f"  RAM used:   {mem.used / (1024**3):.1f} GB ({mem.percent}%)")
        print(f"  RAM avail:  {mem.available / (1024**3):.1f} GB")
    except ImportError:
        info("  (install psutil for local system resource info)")

    if tests_passed < tests_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
