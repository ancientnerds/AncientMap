"""Theo batch runner for the ENTITÄT 54-prompt set.

Submits every theo_prompts/T*.txt to the Theo API one at a time, polls
until completion, and writes each report to a local reports/ dir. Resume-
safe — skips slugs whose <slug>.md already exists or whose request_id is
tracked in the progress file as done.

Reads the JWT from $THEO_TOKEN env var, falls back to ~/.theo_token.
NEVER log the token. NEVER commit the env file.

Usage on VPS:
    THEO_TOKEN=$(cat ~/.theo_token) \\
    python3 scripts/theo_queue_runner.py \\
        --prompts /var/www/ancientnerds/../FantasyAdventure/docs/entitaet/research/theo_prompts \\
        --out /var/www/ancientnerds/../FantasyAdventure/docs/entitaet/research/reports \\
        --api http://localhost:8000 \\
        --poll 60 \\
        --max-parallel 1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

DEFAULT_API = os.getenv("THEO_API", "http://localhost:8000/api")
DEFAULT_POLL = int(os.getenv("THEO_POLL", "60"))
PROGRESS_FILE = "theo_queue_progress.json"


def _load_token() -> str:
    token = os.getenv("THEO_TOKEN", "").strip()
    if token:
        return token
    p = Path.home() / ".theo_token"
    if p.exists():
        token = p.read_text(encoding="utf-8").strip()
        if token:
            return token
    print("FATAL: no THEO_TOKEN env var and no ~/.theo_token", file=sys.stderr)
    sys.exit(2)


def _http(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _http_with_retry(
    method: str, url: str, token: str, body: dict | None = None, *, max_attempts: int = 5
) -> dict:
    """Retry on 429/502/503/connection-error with linear backoff."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    last_err = None
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                method=method,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 502, 503, 504) and attempt < max_attempts - 1:
                wait = 5 * (attempt + 1)
                print(
                    f"  [http {e.code}] retry {attempt + 1}/{max_attempts - 1} in {wait}s",
                    flush=True,
                )
                time.sleep(wait)
                continue
            body_text = ""
            try:
                body_text = e.read().decode("utf-8")[:200]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {e.code} {method} {url}: {body_text}") from e
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last_err = e
            if attempt < max_attempts - 1:
                wait = 5 * (attempt + 1)
                print(
                    f"  [conn {e!r}] retry {attempt + 1}/{max_attempts - 1} in {wait}s", flush=True
                )
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"unreachable: {last_err!r}")


def _slug_from_filename(p: Path) -> str:
    # T01_polygonal-masonry.txt -> polygonal-masonry
    stem = p.stem  # "T01_polygonal-masonry"
    return re.sub(r"^T\d+_", "", stem)


def _read_question(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def _load_progress(progress_path: Path) -> dict:
    if progress_path.exists():
        try:
            return json.loads(progress_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"done": {}, "failed": {}, "in_flight": {}}


def _save_progress(progress_path: Path, prog: dict) -> None:
    progress_path.write_text(json.dumps(prog, indent=2, ensure_ascii=False), encoding="utf-8")


def _submit(api: str, token: str, question: str) -> str:
    resp = _http_with_retry("POST", f"{api}/theo/research", token, {"question": question})
    return resp["id"]


def _poll(api: str, token: str, request_id: str, slug: str, poll_sec: int) -> dict:
    """Poll until status is terminal. Returns the final result dict."""
    terminal = {"completed", "failed", "cancelled", "expired"}
    last_status = None
    t0 = time.monotonic()
    while True:
        row = _http_with_retry("GET", f"{api}/theo/research/{request_id}", token)
        status = row.get("status")
        elapsed = int(time.monotonic() - t0)
        if status != last_status:
            mins = elapsed // 60
            secs = elapsed % 60
            print(f"  [{slug}] {status} ({mins}m{secs}s)", flush=True)
            last_status = status
        if status in terminal:
            return row
        time.sleep(poll_sec)


def _extract_paper(row: dict) -> tuple[str, str, dict]:
    result = row.get("result") or {}
    title = result.get("title") or ""
    paper = result.get("paper") or result.get("paper_text") or ""
    qs = result.get("quality_score") or {}
    return title, paper, qs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", required=True, help="dir of T*.txt prompt files")
    ap.add_argument("--out", required=True, help="dir to write <slug>.md + .json")
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--poll", type=int, default=DEFAULT_POLL)
    ap.add_argument("--max-parallel", type=int, default=1)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--only", default="", help="comma-separated slugs to restrict to")
    ap.add_argument("--skip-slugs", default="", help="comma-separated slugs to skip")
    ap.add_argument("--progress", default=PROGRESS_FILE)
    args = ap.parse_args()

    prompts_dir = Path(args.prompts)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = Path(args.progress)
    if not progress_path.is_absolute():
        progress_path = out_dir / progress_path

    token = _load_token()

    prog = _load_progress(progress_path)
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    skip = {s.strip() for s in args.skip_slugs.split(",") if s.strip()}

    # Build queue: sorted T-files, exclude done/already-on-disk
    files = sorted(prompts_dir.glob("T*.txt"))
    todo: list[tuple[Path, str]] = []
    for f in files:
        slug = _slug_from_filename(f)
        if only and slug not in only:
            continue
        if skip and slug in skip:
            continue
        if (out_dir / f"{slug}.md").exists():
            print(f"[skip] {slug}: .md already on disk", flush=True)
            continue
        if slug in prog["done"]:
            print(f"[skip] {slug}: in progress.json done", flush=True)
            continue
        todo.append((f, slug))

    print(f"[queue] {len(todo)} prompts to process out of {len(files)} total", flush=True)
    print(f"[queue] api={args.api} poll={args.poll}s out={out_dir}", flush=True)

    for f, slug in todo:
        question = _read_question(f)
        if len(question) < 10:
            print(f"[skip] {slug}: question too short ({len(question)} chars)", flush=True)
            continue
        if len(question) > 4000:
            print(
                f"[warn] {slug}: question {len(question)} chars — will be truncated by API",
                flush=True,
            )

        print(f"\n=== {slug} === ({len(question)} chars)", flush=True)
        # Submit (with retries on transient)
        request_id = None
        for attempt in range(args.max_retries):
            try:
                request_id = _submit(args.api, token, question)
                break
            except Exception as e:
                print(
                    f"  [submit] attempt {attempt + 1}/{args.max_retries} failed: {e!r}", flush=True
                )
                if attempt < args.max_retries - 1:
                    time.sleep(30 * (attempt + 1))
        if not request_id:
            prog["failed"][slug] = {"reason": "submit_failed"}
            _save_progress(progress_path, prog)
            continue

        prog["in_flight"][slug] = request_id
        _save_progress(progress_path, prog)
        print(f"  submitted: {request_id}", flush=True)

        # Poll
        try:
            row = _poll(args.api, token, request_id, slug, args.poll)
        except Exception as e:
            print(f"  [poll] {slug}: {e!r}", flush=True)
            prog["failed"][slug] = {"request_id": request_id, "reason": f"poll_failed: {e!r}"}
            prog["in_flight"].pop(slug, None)
            _save_progress(progress_path, prog)
            continue

        title, paper, qs = _extract_paper(row)
        score = qs.get("score")
        badge = qs.get("badge")
        status = row.get("status")
        paper_chars = len(paper)

        # Persist
        (out_dir / f"{slug}.md").write_text(f"# {title or slug}\n\n{paper}\n", encoding="utf-8")
        meta = {
            "slug": slug,
            "request_id": request_id,
            "title": title,
            "status": status,
            "quality_score": score,
            "badge": badge,
            "paper_chars": paper_chars,
            "llm_calls": row.get("llm_calls"),
            "total_tokens": row.get("total_tokens"),
            "sites_found": row.get("sites_found"),
            "duration_ms": row.get("duration_ms"),
            "error_message": row.get("error_message"),
            "submitted_at": row.get("created_at"),
            "completed_at": row.get("completed_at"),
            "audit_gate_failures": (
                qs.get("audit_gate_failures") if isinstance(qs, dict) else None
            ),
        }
        (out_dir / f"{slug}.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        if status == "completed":
            prog["done"][slug] = {"request_id": request_id, "score": score, "badge": badge}
            verdict = (
                "TOP"
                if (isinstance(score, int) and score >= 90)
                else "OK"
                if (isinstance(score, int) and score >= 70 and paper_chars >= 4000)
                else "FLAG"
            )
            print(f"  DONE {slug}: q={score} {badge} {paper_chars}ch verdict={verdict}", flush=True)
        else:
            prog["failed"][slug] = {
                "request_id": request_id,
                "reason": row.get("error_message") or status,
            }
            print(f"  FAILED {slug}: status={status} err={row.get('error_message')}", flush=True)

        prog["in_flight"].pop(slug, None)
        _save_progress(progress_path, prog)

    # Summary
    done = prog["done"]
    failed = prog["failed"]
    print(
        f"\n[summary] {len(done)} done, {len(failed)} failed out of {len(todo)} processed",
        flush=True,
    )
    for slug, info in done.items():
        print(f"  OK  {slug}: q={info.get('score')} {info.get('badge')}", flush=True)
    for slug, info in failed.items():
        print(f"  FAIL {slug}: {info.get('reason')}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
