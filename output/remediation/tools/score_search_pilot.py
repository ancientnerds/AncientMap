"""Score the search route's pilot against the gold standard, by the thresholds sealed beforehand.

`output/remediation/phase3_runner/SEARCH_PILOT.md` fixed four pass thresholds before the pilot's first
search. This reads the pilot's run directory and the gold standard, with the pipeline's own parser
and citation check, and reports each threshold's number and whether it holds:

1. no fabricated citation - an answer whose quoted text is not in the evidence it was shown
   (`discover_stage.source_problems`, the writer's RULE_CITATION check);
2. no harmful decision - a finder WRONG the reviewer did not refute, on a field the human called
   CORRECT;
3. agreement >= 90 % on the decided fields (finder CORRECT, or finder WRONG not refuted);
4. transport - every search stored or recorded as failed, the run not stopped.

Read-only; no database, no network.

    ./.venv/Scripts/python.exe output/remediation/tools/score_search_pilot.py
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402

RUN = REPO / "output/remediation/phase3_runner/runs/search-gold"
GOLD = REPO / "output/remediation/gold_standard/sites.json"
PROGRESS = REPO / "output/remediation/logs/search_gold/progress.json"
AGREEMENT_FLOOR = 0.90


def gold_verdicts() -> dict[tuple[str, str], str]:
    records = json.loads(GOLD.read_text(encoding="utf-8"))["records"]
    return {
        (record["site_id"], verdict["field"]): str(verdict["verdict"]).upper()
        for record in records
        for verdict in record["verdicts"]
    }


def reviews(batch: Path) -> dict[tuple[str, str], dict]:
    data = json.loads((batch / "review.json").read_text(encoding="utf-8"))
    return {(v["site_id"], v["field"]): v for v in data["verdicts"]}


def main() -> int:
    human = gold_verdicts()
    rows = []
    fabricated = []
    unaccounted = 0
    for batch in sorted(RUN.glob("srgd-*")):
        record = json.loads((batch / "input.json").read_text(encoding="utf-8"))
        failures = MS.read_fetch_failures(batch / "fetch.json")  # reads search.json too
        store = F.EvidenceStore(batch / "evidence")
        reviewed = reviews(batch)
        search = json.loads((batch / "search.json").read_text(encoding="utf-8"))
        if search.get("stopped") is not None:
            unaccounted += 1
        for site in search["sites"]:
            for outcome in site["outcomes"]:
                if not (outcome["stored"] or outcome["existing"] or outcome["failure"]):
                    unaccounted += 1
        for site in record["sites"]:
            sid = site["site_id"]
            excerpts = MS.evidence_excerpts(
                site_id=sid, site=site, store=store, failures=failures.get(sid, {})
            )
            pages = DS.pages_from_excerpts(excerpts)
            for field in SE.rerun_fields(site) or ():
                path = batch / "answers" / f"{sid}%2F{field}.txt"
                answer = DS.parse_answer(path.read_text(encoding="utf-8"))
                finder = str(answer.verdict).upper() if answer.verdict else "NONE"
                problems = DS.source_problems(answer, pages)
                if problems:
                    fabricated.append((sid, field, problems))
                review = reviewed.get((sid, field), {})
                refuted = review.get("refuted")
                if finder == "CORRECT":
                    decided = "CORRECT"
                elif finder == "WRONG" and refuted is False:
                    decided = "WRONG"
                else:
                    decided = None
                rows.append(
                    {
                        "batch": batch.name,
                        "site_id": sid,
                        "field": field,
                        "finder": finder,
                        "refuted": refuted,
                        "decided": decided,
                        "human": human.get((sid, field)),
                    }
                )

    progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    decided = [r for r in rows if r["decided"]]
    agree = [r for r in decided if r["decided"] == r["human"]]
    harmful = [r for r in decided if r["decided"] == "WRONG" and r["human"] == "CORRECT"]
    agreement = len(agree) / len(decided) if decided else 0.0

    print(
        f"fields rerun: {len(rows)}  finder: {dict(collections.Counter(r['finder'] for r in rows))}"
    )
    print(f"moved from UNVERIFIABLE to a decision: {len(decided)} of {len(rows)}")
    print(
        f"human verdicts of the rerun fields: {dict(collections.Counter(r['human'] for r in rows))}"
    )
    checks = [
        ("1 no fabricated citation", len(fabricated) == 0, f"{len(fabricated)} answer(s)"),
        ("2 no harmful decision", len(harmful) == 0, f"{len(harmful)} field(s)"),
        (
            "3 agreement >= 90 %",
            agreement >= AGREEMENT_FLOOR,
            f"{len(agree)}/{len(decided)} = {agreement:.1%}",
        ),
        (
            "4 transport",
            unaccounted == 0 and progress.get("stopped") is None and not progress.get("failed"),
            f"unaccounted slots {unaccounted}, stopped {progress.get('stopped')!r}, "
            f"failed {progress.get('failed')!r}",
        ),
    ]
    for name, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
    for sid, field, problems in fabricated:
        print(f"    fabricated: {sid} {field}: {problems}")
    for r in harmful:
        print(f"    harmful: {r}")
    for r in decided:
        if r["decided"] != r["human"]:
            print(f"    disagrees: {r}")
    passed = all(ok for _, ok, _ in checks)
    print("PILOT RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
