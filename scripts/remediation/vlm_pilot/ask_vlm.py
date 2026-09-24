"""Ask the reachable vision model the pipeline's own question, once per sampled image.

**Pilot history (2026-09-21).** Since the owner order of 2026-09-23 ("no DeepSeek any more -
everything with Opus") nothing that runs imports this module: the gallery audit's vision stage is
answered through the Opus handoff (`scripts/remediation/opus_handoff.py`), and the two pure helpers it
read from here (`EXPECTED_KINDS`, `extract_json`) live in `common.py`. The gateway transport below is
kept only as the record of how the pilot's 200 answers were bought; it is not to be run again.

Run:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
        scripts/remediation/vlm_pilot/ask_vlm.py            # all 200, 4 workers
    ... ask_vlm.py --limit 2 --out probe.jsonl              # a probe, 2 images

Out: `output/remediation/vlm_pilot/VLM.jsonl` (+ `.partial.jsonl` while running)
and the numbers for `COST.md` on stdout.

WHAT IS SENT
------------
* The prompt is `pipeline.video.shorts_select.VLM_PROMPT` **imported**, not
  copied, and filled exactly as `judge_all` fills it
  (`pipeline/video/shorts_select.py:271`): `site` = the site's name,
  `card_text` = `card_stats.card_description` - the same column
  `pipeline/video/shorts_export.py:230` turns into `card_text` for the shorts
  selector - and `title` = `vlm_pilot.common.image_title` equivalent, i.e.
  `wiki_images.title`. The kind enum is read *out of the prompt string* and
  checked against the six words the prompt prints, so the vocabulary cannot
  drift away from the question.
* The image is `shorts_select.vlm_bytes()` - the same RGB downscale to
  `VLM_MAX_SIDE` (1280) as JPEG quality `VLM_JPEG_QUALITY` (85) that the
  production call sends.
* Retry policy is the production one: `VLM_ATTEMPTS` (3) with
  `VLM_RETRY_WAIT_S` (8) between attempts.

TRANSPORT
---------
`http://`-free, `POST https://opencode.ai/zen/go/v1/chat/completions` (the gateway
proven reachable in `output/remediation/gallery_design/DESIGN.md` section 3), with
the `opencode-go` API key from `~/.pi/agent/auth.json`. The key is read at run time
from that file and is never printed and never written anywhere. The gateway
requires an `x-opencode-session` header; a uuid4 is generated per run and recorded
per row so a gateway log can be correlated.

WHAT IS RECORDED
----------------
One record per image, in `SAMPLE.jsonl` order: `image_id`, `tier`,
`sheet_index`, `http_status`, the **raw** response text, the parsed `kind`, the
raw `usage` object, `latency_ms`, `attempts`, `cost_usd` and the prompt that was
sent. `kind` is `null` - never `"other"` - when no verdict could be obtained, and
the record then carries an `error`. That distinction is the whole point: an empty
answer that reads as `other` is indistinguishable from a model that looked and
said "other", which is exactly the silent failure this audit exists to rule out.
The process exits 3 if any row has no verdict, after writing every row.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from common import (  # noqa: E402
    EXPECTED_KINDS,
    OUT_DIR,
    extract_json,
    read_jsonl,
    write_jsonl,
)

from pipeline.video.shorts_select import (  # noqa: E402
    VLM_ATTEMPTS,
    VLM_PROMPT,
    VLM_RETRY_WAIT_S,
    image_title,
    vlm_bytes,
)

GATEWAY_URL = "https://opencode.ai/zen/go/v1/chat/completions"
MODEL = "deepseek-v4-flash-vision-exp"
AUTH_FILE = Path.home() / ".pi" / "agent" / "auth.json"
AUTH_PROVIDER = "opencode-go"
#: The model reasons before it answers, and the reasoning is billed as output. Measured
#: on the first probe (2026-09-21): with 2,048 the reasoning consumed the whole budget on
#: 2 of 3 calls and the content came back empty with finish_reason=length; `minimax_vlm`,
#: whose transport this mirrors, sends no max_tokens at all.
MAX_TOKENS = 8192

#: The model's own registry prices, per 1M tokens (DESIGN.md section 3).
USD_PER_M_INPUT = 0.15
USD_PER_M_OUTPUT = 0.60
USD_PER_M_CACHE_READ = 0.003

#: The prompt prints its own enum; read it from there so the two cannot drift.
_ENUM_RE = re.compile(r'\{\{"kind":\s*"([^"]+)"((?:\s*\|\s*"[^"]+")*)')
_ENUM_MATCH = _ENUM_RE.search(VLM_PROMPT)
if _ENUM_MATCH is None:  # the question changed shape; refuse rather than guess
    raise SystemExit("REFUSING: VLM_PROMPT no longer prints a 'kind' enum")
PROMPT_KINDS = tuple(re.findall(r'"([^"]+)"', _ENUM_MATCH.group(0))[1:])


def load_api_key(auth_file: Path) -> str:
    """Read the opencode-go key. Never logged, never written to disk."""
    data = json.loads(auth_file.read_text(encoding="utf-8"))
    entry = data.get(AUTH_PROVIDER) or {}
    key = entry.get("key")
    if not key:
        raise SystemExit(f"no {AUTH_PROVIDER}.key in {auth_file}")
    return key


def prompt_for(row: dict[str, Any]) -> str:
    """The production prompt, filled the way `judge_all` fills it."""
    title = row.get("title") or Path(row["filename"]).stem
    return VLM_PROMPT.format(
        site=row["site_name"],
        card_text=row["card_text"],
        title=image_title({"title": title, "filename": row["filename"]}),
    )


def usage_cost(usage: dict[str, Any]) -> dict[str, Any]:
    """Cost of one call at the model's own prices, with the cached part split out."""
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    details = usage.get("prompt_tokens_details") or {}
    cached = int(
        details.get("cached_tokens")
        or usage.get("prompt_cache_hit_tokens")
        or usage.get("cache_read_input_tokens")
        or usage.get("cached_tokens")
        or 0
    )
    reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    fresh = max(prompt_tokens - cached, 0)
    cost = (
        fresh * USD_PER_M_INPUT
        + cached * USD_PER_M_CACHE_READ
        + completion_tokens * USD_PER_M_OUTPUT
    ) / 1_000_000
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached,
        "reasoning_tokens": reasoning,
        "cost_usd": round(cost, 8),
    }


def ask_once(client: httpx.Client, session: str, prompt: str, jpeg: bytes) -> dict[str, Any]:
    """One HTTP call. Returns status/raw/usage; never raises for an HTTP error."""
    started = time.monotonic()
    response = client.post(
        GATEWAY_URL,
        headers={"x-opencode-session": session},
        json={
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64,"
                                + base64.b64encode(jpeg).decode("ascii")
                            },
                        },
                    ],
                }
            ],
        },
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    raw = response.text
    usage: dict[str, Any] = {}
    content = ""
    finish_reason = None
    if response.status_code == 200:
        body = response.json()
        usage = body.get("usage") or {}
        choices = body.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""
            finish_reason = choices[0].get("finish_reason")
    return {
        "http_status": response.status_code,
        "latency_ms": latency_ms,
        "raw_response": raw if response.status_code != 200 else content,
        "finish_reason": finish_reason,
        "body_text": raw if response.status_code == 200 else raw[:500],
        "usage": usage,
    }


def judge(client: httpx.Client, session: str, row: dict[str, Any]) -> dict[str, Any]:
    """One image: up to VLM_ATTEMPTS calls, then either a kind or a recorded error."""
    prompt = prompt_for(row)
    jpeg = vlm_bytes(Path(row["local_file_path"]))
    record: dict[str, Any] = {
        "image_id": row["image_id"],
        "tier": row["tier"],
        "sheet_index": row["sheet_index"],
        "site_id": row["site_id"],
        "site_name": row["site_name"],
        "filename": row["filename"],
        "title": row.get("title"),
        "model": MODEL,
        "session_id": session,
        "prompt": prompt,
        "jpeg_bytes": len(jpeg),
        "kind": None,
        "kind_raw": None,
        "verdict": None,
        "raw_response": None,
        "finish_reason": None,
        "error": None,
        "attempts": 0,
        "http_status": None,
        "latency_ms": None,
        "usage": {},
        "cost_usd": 0.0,
    }
    attempts_detail: list[dict[str, Any]] = []
    for attempt in range(1, VLM_ATTEMPTS + 1):
        record["attempts"] = attempt
        try:
            call = ask_once(client, session, prompt, jpeg)
        except Exception as exc:  # transport failure is data, not a crash
            attempts_detail.append(
                {"attempt": attempt, "transport_error": f"{type(exc).__name__}: {exc}"}
            )
            record["error"] = f"transport: {type(exc).__name__}: {exc}"[:400]
            if attempt < VLM_ATTEMPTS:
                time.sleep(VLM_RETRY_WAIT_S)
            continue

        record["http_status"] = call["http_status"]
        record["latency_ms"] = call["latency_ms"]
        record["usage"] = call["usage"]
        record["raw_response"] = call["raw_response"]
        record["finish_reason"] = call["finish_reason"]
        attempts_detail.append(
            {
                "attempt": attempt,
                "http_status": call["http_status"],
                "latency_ms": call["latency_ms"],
                "finish_reason": call["finish_reason"],
                "usage": call["usage"],
            }
        )
        if call["http_status"] != 200:
            record["error"] = f"http {call['http_status']}: {call['body_text'][:200]}"
            if attempt < VLM_ATTEMPTS:
                time.sleep(VLM_RETRY_WAIT_S)
            continue

        parsed = extract_json(call["raw_response"])
        if parsed is None:
            record["error"] = (
                f"unparsable JSON in response (finish_reason={call['finish_reason']}, "
                f"{len(call['raw_response'] or '')} chars)"
            )
            if attempt < VLM_ATTEMPTS:
                time.sleep(VLM_RETRY_WAIT_S)
            continue

        kind = parsed.get("kind")
        record["verdict"] = parsed
        record["kind_raw"] = kind
        if kind in PROMPT_KINDS:
            record["kind"] = kind
            record["error"] = None
        elif kind is None:
            record["error"] = "response carries no 'kind' field"
        else:
            record["error"] = f"'kind' out of vocabulary: {kind!r}"
        break

    costs = [usage_cost(a["usage"]) for a in attempts_detail if a.get("usage")]
    record["cost_usd"] = round(sum(c["cost_usd"] for c in costs), 8)
    record["usage_totals"] = {
        "prompt_tokens": sum(c["prompt_tokens"] for c in costs),
        "completion_tokens": sum(c["completion_tokens"] for c in costs),
        "cached_tokens": sum(c["cached_tokens"] for c in costs),
        "reasoning_tokens": sum(c["reasoning_tokens"] for c in costs),
    }
    record["attempts_detail"] = attempts_detail
    if record["kind"] is None and not record["error"]:
        record["error"] = "no verdict after all attempts, and no error recorded (bug)"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=0, help="only the first N sampled images")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--out",
        default="VLM.jsonl",
        help="file name inside output/remediation/vlm_pilot (a probe writes its own)",
    )
    args = parser.parse_args()

    if PROMPT_KINDS != EXPECTED_KINDS:
        raise SystemExit(
            f"REFUSING: the prompt's kind enum changed: {PROMPT_KINDS} != {EXPECTED_KINDS}"
        )
    rows = list(read_jsonl(OUT_DIR / "SAMPLE.jsonl"))
    if args.limit:
        rows = rows[: args.limit]
    key = load_api_key(AUTH_FILE)
    session = str(uuid.uuid4())
    out_path = OUT_DIR / args.out
    partial_path = OUT_DIR / (Path(args.out).stem + ".partial.jsonl")

    print(f"model={MODEL} url={GATEWAY_URL} images={len(rows)} workers={args.workers}")
    print(f"kind enum from the prompt itself: {PROMPT_KINDS}")
    print(f"session={session} out={out_path}")

    lock = threading.Lock()
    results: dict[int, dict[str, Any]] = {}
    done = 0
    failed = 0
    spent = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0
    wall_start = time.monotonic()

    with httpx.Client(
        timeout=180.0,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    ) as client:

        def work(row: dict[str, Any]) -> None:
            nonlocal done, failed, spent, prompt_tokens, completion_tokens, cached_tokens
            record = judge(client, session, row)
            with lock:
                results[row["image_id"]] = record
                done += 1
                spent += record["cost_usd"]
                totals = record["usage_totals"]
                prompt_tokens += totals["prompt_tokens"]
                completion_tokens += totals["completion_tokens"]
                cached_tokens += totals["cached_tokens"]
                if record["kind"] is None:
                    failed += 1
                elapsed = time.monotonic() - wall_start
                print(
                    f"[{done}/{len(rows)}] kind={record['kind']!s:20} "
                    f"http={record['http_status']} {record['latency_ms']}ms "
                    f"spent=${spent:.5f} tokens in/out/cache={prompt_tokens}/{completion_tokens}/"
                    f"{cached_tokens} failed={failed} elapsed={elapsed:.0f}s",
                    flush=True,
                )
                if done % 10 == 0:
                    print(
                        f"    running cost: ${spent:.5f} for {done} images "
                        f"({prompt_tokens} in, {completion_tokens} out, {cached_tokens} cached)",
                        flush=True,
                    )
                with open(partial_path, "a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(work, rows))

    ordered = [results[row["image_id"]] for row in rows]
    write_jsonl(out_path, ordered)
    partial_path.unlink(missing_ok=True)

    total_cost = sum(r["cost_usd"] for r in ordered)
    parsed = sum(1 for r in ordered if r["kind"] is not None)
    kinds: dict[str, int] = {}
    for record in ordered:
        if record["kind"] is not None:
            kinds[record["kind"]] = kinds.get(record["kind"], 0) + 1
        else:
            kinds["<no verdict>"] = kinds.get("<no verdict>", 0) + 1
    print("\n=== summary ===")
    print(f"images            : {len(ordered)}")
    print(f"verdicts parsed   : {parsed}")
    print(f"no verdict        : {len(ordered) - parsed}")
    print(f"kind distribution : {kinds}")
    print(
        f"tokens            : in {prompt_tokens} (cached {cached_tokens}), out {completion_tokens}"
    )
    print(
        f"cost at 0.15/0.60/0.003 per 1M : ${total_cost:.5f} "
        f"(in ${(prompt_tokens - cached_tokens) * USD_PER_M_INPUT / 1e6:.5f}, "
        f"cache ${cached_tokens * USD_PER_M_CACHE_READ / 1e6:.5f}, "
        f"out ${completion_tokens * USD_PER_M_OUTPUT / 1e6:.5f})"
    )
    print(f"wall clock        : {time.monotonic() - wall_start:.0f}s")
    if failed:
        print(
            f"\nFAILED ROWS ({failed}) - kind is null, an error is recorded, never a fake 'other':"
        )
        for record in ordered:
            if record["kind"] is None:
                print(
                    f"  image {record['image_id']} http={record['http_status']}: {record['error']}"
                )
        print(f"\nwrote {out_path} (exit 3: at least one image has no verdict)")
        return 3
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
