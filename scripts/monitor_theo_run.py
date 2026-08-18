"""Poll a Theo research run via SSH, log progress, capture issues for post-mortem.

Runs until the research transitions to completed/failed/cancelled. Every poll:
- Records status, sites_found, tools_used, error_message
- Pulls the last 5 min of API logs via ssh, filters for warnings/errors/key markers
- Accumulates a deduped issue list in C:/tmp/theo_regen/<short_rid>_issues.json

When done, dumps the full result + a final issue summary.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REQUEST_ID = "4a873c4d-49c5-46ee-90ec-bbd49346f1c6"
SHORT = REQUEST_ID.split("-")[0]
# Prod tokens expire and must never live in the repo — grab a fresh one from
# the browser session (see memory: reference_theo_jwt_secret) and export it.
TOKEN = os.environ["THEO_JWT"]

OUT_DIR = Path("C:/tmp/theo_regen")
RESULT_PATH = OUT_DIR / f"{SHORT}.json"
PROGRESS_LOG = OUT_DIR / f"{SHORT}_progress.log"
ISSUES_PATH = OUT_DIR / f"{SHORT}_issues.json"

# Patterns we treat as noteworthy issues. Each entry is (category, regex).
# Anything matching the regex gets recorded with the timestamp + raw line.
ISSUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("llm_failure", re.compile(r"coherence_pass LLM failure")),
    ("llm_fallback", re.compile(r"MiniMax did not return tool_use block")),
    ("adapter_error", re.compile(r"search failed for .* 'section_text'")),
    ("rate_limit", re.compile(r"rate limited|status 429")),
    ("rate_limit_long", re.compile(r"backing off (?:[5-9]|[1-9][0-9])s")),  # >=5s
    ("error", re.compile(r"\bERROR\b")),
    ("traceback", re.compile(r"Traceback|raise [A-Z]")),
    ("hallucination_trigger", re.compile(r"hallucinat", re.IGNORECASE)),
    ("strip_legacy_refs", re.compile(r"Stripped LLM-emitted References")),
    ("strip_orphan", re.compile(r"Stripped \d+ orphan")),
    ("scrub_hex", re.compile(r"Scrubbed \d+ hex")),
    ("audit_failure", re.compile(r"audit_passed.*False|orphaned_refs.*[1-9]")),
    ("numeric_conflict", re.compile(r"numeric_conflict|high_numeric_conflicts")),
    ("contradiction_high", re.compile(r"high_contradictions.*[1-9]")),
    ("paper_step", re.compile(r"\bStep \d+(?:\.\d+)?(?:[a-z])?[: ]")),
    ("specialist_done", re.compile(r"specialist.*(?:completed|finished)")),
    ("write_section", re.compile(r"(?:section_writer|writing section)")),
    ("coherence_pass", re.compile(r"coherence_pass|run_coherence")),
    ("publish_ready", re.compile(r"publish|finalize_references")),
]


def ssh_run(cmd: str, timeout: int = 60) -> str:
    out = subprocess.run(
        ["ssh", "ancientnerds", cmd],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return out.stdout


def fetch_status() -> dict:
    cmd = (
        f'curl -s -H "Authorization: Bearer {TOKEN}" '
        f"http://localhost:8000/api/theo/research/{REQUEST_ID}"
    )
    return json.loads(ssh_run(cmd))


def fetch_recent_logs(since: str = "2m") -> str:
    return ssh_run(f"docker logs ancient_nerds_api --since {since} 2>&1")


def classify_line(line: str) -> str | None:
    for category, pattern in ISSUE_PATTERNS:
        if pattern.search(line):
            return category
    return None


def update_issues(seen: set[str], issues: dict[str, list[dict]], log_text: str) -> int:
    """Walk log lines, classify, add to issues dict. Returns count of new issues."""
    new = 0
    for raw_line in log_text.splitlines():
        # Strip the ANSI escape codes Loguru emits in container output
        line = re.sub(r"\x1b\[[\d;]*m", "", raw_line)
        category = classify_line(line)
        if not category:
            continue
        # Dedup key: category + the first 200 chars of the line (after timestamp)
        body = line.split("|", 4)[-1].strip() if "|" in line else line
        key = f"{category}|{body[:200]}"
        if key in seen:
            continue
        seen.add(key)
        issues.setdefault(category, []).append(
            {"time": datetime.now(UTC).isoformat(), "line": line[:500]}
        )
        new += 1
    return new


def write_progress(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Append to the progress log across restarts — don't lose history on
    # token refresh / network blip.

    # Resume from any existing issues file so a restart (e.g. token refresh)
    # doesn't lose the issue trail collected so far.
    issues: dict[str, list[dict]] = {}
    seen: set[str] = set()
    if ISSUES_PATH.exists():
        try:
            issues = json.loads(ISSUES_PATH.read_text(encoding="utf-8"))
            for category, items in issues.items():
                for item in items:
                    body = (
                        item["line"].split("|", 4)[-1].strip()
                        if "|" in item["line"]
                        else item["line"]
                    )
                    seen.add(f"{category}|{body[:200]}")
        except Exception:
            issues = {}
            seen = set()
    last_status = ""
    last_sites = -1
    poll_count = 0
    start = time.time()

    write_progress(f"monitor started for {REQUEST_ID}")

    while True:
        poll_count += 1
        try:
            data = fetch_status()
        except Exception as exc:
            write_progress(f"status fetch error: {exc}")
            time.sleep(30)
            continue

        status = data.get("status", "?")
        sites = data.get("sites_found", 0)
        elapsed = int(time.time() - start)

        if status != last_status or sites != last_sites:
            write_progress(
                f"status={status} sites={sites} tools={data.get('tools_used')} "
                f"duration_ms={data.get('duration_ms')} elapsed={elapsed}s"
            )
            last_status, last_sites = status, sites

        # Pull recent logs and harvest issues
        try:
            log_text = fetch_recent_logs(since="2m")
            n_new = update_issues(seen, issues, log_text)
            if n_new:
                write_progress(
                    f"+{n_new} new issue entries (total {sum(len(v) for v in issues.values())})"
                )
                ISSUES_PATH.write_text(
                    json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8"
                )
        except Exception as exc:
            write_progress(f"log fetch error: {exc}")

        if status in ("completed", "failed", "cancelled"):
            RESULT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            ISSUES_PATH.write_text(
                json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            write_progress(f"FINAL status={status} elapsed={elapsed}s")
            write_progress(f"result -> {RESULT_PATH}")
            write_progress(
                f"issues -> {ISSUES_PATH} ({sum(len(v) for v in issues.values())} total)"
            )
            # One last log harvest with a wider window for the final phase
            try:
                final_log = fetch_recent_logs(since="10m")
                update_issues(seen, issues, final_log)
                ISSUES_PATH.write_text(
                    json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except Exception:
                pass
            return 0 if status == "completed" else 2

        time.sleep(90)  # poll every 90s — enough granularity, easy on the API


if __name__ == "__main__":
    sys.exit(main())
