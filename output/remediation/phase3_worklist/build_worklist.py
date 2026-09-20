"""Read-only builder for the Phase-3 worklist.

Consumes the ten census runs output/remediation/run_t01..run_t10 and produces:

* WORKLIST.jsonl - one record per site flagged by a FACTUAL check (T01/T02/T03/T05),
  deduplicated across checks, worst-first.
* _counts.json    - the arithmetic (per-test, intersection, union, dimension totals)
  so WORKLIST.md can quote measured numbers only.

It writes nothing outside output/remediation/phase3_worklist/. It never touches the
database or any source file.

Factual checks (an external claim about the world that a deterministic script cannot
conclusively settle): T01 (Wikidata name/country/coords), T02 (lat/lon vs country
polygon), T03 (text years vs period bucket), T05 (country value correctness).
Excluded as mechanical/structural: T04 (0 findings), T06 URL shape, T07 link
liveness, T08 citation markers, T09 Commons dimensions, T10 gallery tiers.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
REM = ROOT / "output" / "remediation"
OUT = Path(__file__).resolve().parent

#: test id -> run directory (run_t06_reverify is a duplicate of T06, not a 11th check)
RUNS: dict[str, str] = {f"T{i:02d}": f"run_t{i:02d}" for i in range(1, 11)}

FACTUAL = {"T01", "T02", "T03", "T05"}
MECHANICAL_EXCLUDED = {"T04", "T06", "T07", "T08", "T09", "T10"}

SEV_RANK = {"severe": 3, "moderate": 2, "cosmetic": 1, "": 0}


def load_findings(tid: str) -> list[dict]:
    path = REM / RUNS[tid] / "findings.jsonl"
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_sites() -> dict[str, dict]:
    sites: dict[str, dict] = {}
    with gzip.open(REM / "snapshot" / "unified_sites.jsonl.gz", "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                d = json.loads(line)
                sites[str(d["id"])] = d
    return sites


def main() -> None:
    sites = load_sites()

    per_test: dict[str, dict[str, list[dict]]] = {}
    test_site_sets: dict[str, set[str]] = {}
    integrity: list[str] = []

    for tid in RUNS:
        findings = load_findings(tid)
        by_site: dict[str, list[dict]] = defaultdict(list)
        for f in findings:
            by_site[f["site_id"]].append(f)
        per_test[tid] = by_site
        test_site_sets[tid] = set(by_site)
        census_rows = sum(
            1 for line in (REM / RUNS[tid] / "census.jsonl").open(encoding="utf-8") if line.strip()
        )
        integrity.append(f"{tid}: census_rows={census_rows} findings={len(findings)} sites={len(by_site)}")

    # --- union / intersection arithmetic over the factual tests ---
    factual_sets = {tid: test_site_sets[tid] for tid in sorted(FACTUAL)}
    union = set().union(*factual_sets.values())
    pairwise = {
        f"{a}&{b}": len(factual_sets[a] & factual_sets[b])
        for a, b in combinations(sorted(FACTUAL), 2)
    }
    triple = len(factual_sets["T01"] & factual_sets["T02"] & factual_sets["T03"])
    all_four = len(set.intersection(*factual_sets.values()))

    # --- merge per site ---
    records: list[dict[str, Any]] = []
    for sid in sorted(union):
        site = sites.get(sid, {})
        findings = []
        checks = []
        dims = set()
        for tid in sorted(FACTUAL):
            if sid not in per_test[tid]:
                continue
            checks.append(tid)
            for f in per_test[tid][sid]:
                dims.add(f.get("dimension", ""))
                findings.append(
                    {
                        "test_id": f["test_id"],
                        "dimension": f.get("dimension"),
                        "field": f.get("field"),
                        "severity": f.get("severity"),
                        "proposal": f.get("proposal"),
                        "confidence": f.get("confidence"),
                        "current_value": f.get("current_value"),
                        "proposed_value": f.get("proposed_value"),
                        "applicable": f.get("applicable"),
                        "note": f.get("note", ""),
                    }
                )
        applicable = [f for f in findings if f["applicable"]]
        needs_research = [f for f in findings if not f["applicable"]]
        records.append(
            {
                "site_id": sid,
                "name": site.get("name"),
                "checks": checks,
                "n_checks": len(checks),
                "dimensions": sorted(dims),
                "max_severity": max((f["severity"] or "" for f in findings), key=lambda s: SEV_RANK.get(s, 0)),
                "n_findings": len(findings),
                "phase3": bool(needs_research),  # no deterministic check can settle it
                "mechanically_settable": bool(applicable),
                "findings": findings,
            }
        )

    # worst-first: severe before moderate, more checks before fewer, name for stability
    records.sort(
        key=lambda r: (SEV_RANK[r["max_severity"]], r["n_checks"], r["n_findings"], r["name"] or ""),
        reverse=True,
    )

    phase3_records = [r for r in records if r["phase3"]]
    mechanical_records = [r for r in records if not r["phase3"] and r["mechanically_settable"]]

    # --- size the mechanical workstream too (for the plan's split) ---
    mech_all: dict[str, set[str]] = {}
    for tid in sorted(MECHANICAL_EXCLUDED):
        mech_all[tid] = set(per_test[tid])

    counts: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "integrity": integrity,
        "per_test_sites": {tid: len(test_site_sets[tid]) for tid in sorted(RUNS)},
        "per_test_findings": {tid: sum(len(v) for v in per_test[tid].values()) for tid in sorted(RUNS)},
        "factual_tests": sorted(FACTUAL),
        "excluded_mechanical_tests": sorted(MECHANICAL_EXCLUDED),
        "factual_union_sites": len(union),
        "phase3_sites": len(phase3_records),
        "mechanically_settable_sites": len(mechanical_records),
        "dimension_counts": Counter(
            f["dimension"] for r in records for f in r["findings"]
        ).most_common(),
        "severity_counts": Counter(r["max_severity"] for r in records).most_common(),
        "pairwise_factual_intersections": pairwise,
        "triple_T01_T02_T03": triple,
        "all_four_factual": all_four,
        "mechanical_excluded_sites": {tid: len(s) for tid, s in mech_all.items()},
        "mechanical_excluded_union": len(set().union(*mech_all.values())) if mech_all else 0,
    }

    out_jsonl = OUT / "WORKLIST.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

    (OUT / "_counts.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(counts, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
