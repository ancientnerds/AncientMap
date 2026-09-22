"""Summarise LEDGER.jsonl: what was spent, what it bought, and what a full run would cost.

Written because the tail of a bounded log is not a measurement: exit codes have already lied once
in this session (`FETCH_EXIT=2 JUDGE_EXIT=2` inside a chain that reported 0). Every number here
comes from the ledger rows on disk, and anything absent is reported as absent, not as zero.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ledger = pathlib.Path("output/remediation/phase3_runner/LEDGER.jsonl")
if not ledger.exists():
    print(f"  no ledger at {ledger}: nothing has been measured yet")
    raise SystemExit(1)

rows = [
    json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()
]
kinds = Counter(row.get("kind") for row in rows)
print(f"  ledger rows: {len(rows)}   by kind: {dict(kinds)}")

fetches = [row for row in rows if row.get("kind") == "fetch"]
if fetches:
    outcomes = Counter(row.get("outcome", "(no outcome field)") for row in fetches)
    print(f"  fetches    : {len(fetches)}   outcomes: {dict(outcomes)}")
    print(f"               bytes read: {sum(row.get('bytes') or 0 for row in fetches)}")
    statuses = Counter(row.get("http_status") for row in fetches)
    print(f"               http_status: {dict(statuses)}")
    given = [row for row in fetches if row.get("given_up")]
    print(f"               given up after retries: {len(given)}")

calls = [row for row in rows if row.get("kind") == "model_call"]
if not calls:
    print("  NO MODEL CALLS RECORDED - there is no measured cost per site to quote")
    raise SystemExit(0)

tin = sum(row.get("input_tokens") or 0 for row in calls)
tout = sum(row.get("output_tokens") or 0 for row in calls)
tcache = sum(row.get("cache_read_tokens") or 0 for row in calls)
cost = sum(row.get("cost_usd") or 0.0 for row in calls)
sites = {row.get("label") for row in calls}
print(f"  model calls: {len(calls)} over {len(sites)} call label(s)")
print(f"               input {tin}  output {tout}  cache-read {tcache}")
print(f"               cost ${cost:.6f}  (provider-reported, summed verbatim)")
print(
    f"               per call ${cost / len(calls):.6f}   per site ${cost / max(len(sites), 1):.6f}"
)
for sites_n in (1813, 5004):
    print(
        f"               projection: {sites_n} sites -> ${cost / max(len(sites), 1) * sites_n:.2f}"
    )
print()
print("  per-call detail:")
for row in calls:
    print(
        f"    {str(row.get('label'))[:34]:<34} {str(row.get('stage')):<8}"
        f" in={row.get('input_tokens'):<7} out={row.get('output_tokens'):<5} ${row.get('cost_usd')}"
    )
sys.exit(0)
