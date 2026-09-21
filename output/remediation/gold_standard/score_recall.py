"""Score the discover pass against the gold standard: did it flag the field on the site?

The ground truth is `truth_fields.json` - the 24 errors the blinded human-style check found and the
census did not flag, each an exact (site, field) pair with the stored and the correct value. This script
asks one question of the run: **for each of those pairs, did the finder answer `WRONG`?**

Three denominators, because they mean different things and conflating them would flatter the result:

* ``ceiling_24``      - all 24 ground-truth entries, whatever the design can do.
* ``reachable``       - entries whose site was judged **and** whose field the pass asks about. This is
                        the design's own ceiling: it excludes the entries on sites the evidence bound
                        refused, and the entries in fields (`scope`) that no per-field value question can
                        reach because no column holds them.
* ``caught``          - of the reachable entries, the ones the finder answered `WRONG` for. **This is
                        recall.**

It also lists every `WRONG` the run produced that is *not* a ground-truth entry. Those are not
automatically false positives - the ground truth is the errors the blinded check could see, not every
error that exists - so they are printed with their one-sentence reason for a human to adjudicate rather
than counted.

Usage: ./.venv/Scripts/python.exe output/remediation/gold_standard/score_recall.py [RUN_DIR]
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter, defaultdict

REPO = pathlib.Path(__file__).resolve().parents[3]
TRUTH = REPO / "output" / "remediation" / "gold_standard" / "truth_fields.json"
DEFAULT_RUN = REPO / "output" / "remediation" / "phase3_runner" / "runs" / "gold"
OUT = REPO / "output" / "remediation" / "gold_standard" / "recall_result.json"

VERDICT = re.compile(r"VERDICT:\s*(CORRECT|WRONG|UNVERIFIABLE)")


def verdict_of(text: str) -> str | None:
    match = VERDICT.search(text)
    return match.group(1) if match else None


def reason_of(text: str) -> str:
    body = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return body[1] if len(body) > 1 else ""


def collect(
    run_dir: pathlib.Path,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str], set[str]]:
    """Every answered (site, field) -> verdict and reason, plus the sites the run judged."""
    verdicts: dict[tuple[str, str], str] = {}
    reasons: dict[tuple[str, str], str] = {}
    judged: set[str] = set()
    for batch in sorted(run_dir.glob("batch-*")):
        model = json.loads((batch / "model.json").read_text(encoding="utf-8"))
        for row in model["judgements"]:
            label = row["label"]
            site_id, _, field = label.partition("/")
            text = (batch / "answers" / f"{site_id}%2F{field}.txt").read_text(encoding="utf-8")
            verdicts[(site_id, field)] = verdict_of(text) or "MISSING"
            reasons[(site_id, field)] = reason_of(text)
            judged.add(site_id)
    return verdicts, reasons, judged


def main() -> int:
    run_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RUN
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    entries = truth["entries"]
    verdicts, reasons, judged = collect(run_dir)
    asked_fields = {field for _, field in verdicts}

    rows = []
    for entry in entries:
        key = (entry["site_id"], entry["field"])
        # `asked` means the pass really asked this exact question: a call was made and answered for
        # this (site, field). Membership in `fields_to_catch` is NOT enough - it holds `scope`, for
        # which no column exists and therefore no call is made, and counting those as reached would
        # inflate the denominator with questions that were never asked.
        asked = key in verdicts
        rows.append(
            {
                "site_name": entry["site_name"],
                "site_id": entry["site_id"],
                "field": entry["field"],
                "asked": asked,
                "verdict": verdicts.get(key, "NOT ASKED"),
                "caught": asked and verdicts.get(key) == "WRONG",
                "stored_value": entry["stored_value"],
                "correct_value": entry["correct_value"],
                "reason": reasons.get(key, ""),
            }
        )

    caught = [r for r in rows if r["caught"]]
    reachable = [r for r in rows if r["asked"]]
    unreachable = [r for r in rows if not r["asked"]]

    print(f"  run: {run_dir}")
    print(f"  judged sites: {len(judged)};  answered (site, field) pairs: {len(verdicts)}")
    print(f"  verdicts overall: {dict(Counter(verdicts.values()))}")
    print(f"\n  ceiling_24 = {len(rows)}   reachable = {len(reachable)}   caught = {len(caught)}")
    if reachable:
        print(
            f"  RECALL on the reachable set: {len(caught)}/{len(reachable)} = {len(caught) / len(reachable):.1%}"
        )
    print(
        f"  RECALL against all 24:       {len(caught)}/{len(rows)} = {len(caught) / len(rows):.1%}"
    )

    print("\n  --- the ground-truth entries, one line each ---")
    for r in sorted(rows, key=lambda r: (not r["caught"], r["site_name"], r["field"])):
        mark = "CAUGHT" if r["caught"] else ("not asked" if not r["asked"] else r["verdict"])
        print(
            f"    {mark:10s} {r['site_name'][:28]:30s} {r['field']:16s} stored={str(r['stored_value'])[:22]}"
        )

    print("\n  --- unreachable, with the reason ---")
    for r in unreachable:
        if r["site_id"] not in judged:
            why = "site refused by the evidence bound, so all five of its fields were never asked"
        elif r["field"] not in asked_fields:
            why = f"field '{r['field']}' has no column a per-field value question can read"
        else:
            why = "no call was made for this (site, field)"
        print(f"    {r['site_name'][:28]:30s} {r['field']:16s} -> {why}")

    caught_keys = {(r["site_id"], r["field"]) for r in caught}
    extra = [
        (key, verdict)
        for key, verdict in verdicts.items()
        if verdict == "WRONG" and key not in caught_keys
    ]
    print(
        f"\n  --- {len(extra)} WRONG verdicts that are NOT ground-truth entries (adjudicate by hand) ---"
    )
    for key, _ in sorted(extra):
        site_id, field = key
        name = next((r["site_name"] for r in rows if r["site_id"] == site_id), site_id[:8])
        print(f"    {name[:28]:30s} {field:16s} {reasons[key][:110]}")

    result = {
        "run_dir": str(run_dir),
        "question_commit": "round 1 = 6efec9a (verdict first); round 2 = 42fb917 (evidence statement first)",
        "judged_sites": len(judged),
        "answered_pairs": len(verdicts),
        "verdict_counts": dict(Counter(verdicts.values())),
        "ceiling_24": len(rows),
        "reachable": len(reachable),
        "caught": len(caught),
        "recall_on_reachable": (len(caught) / len(reachable)) if reachable else None,
        "recall_against_24": len(caught) / len(rows),
        "entries": rows,
        "wrong_not_in_ground_truth": [
            {"site_id": k[0], "field": k[1], "reason": reasons[k]} for k, _ in sorted(extra)
        ],
    }
    out = OUT.with_name(f"recall_result_{run_dir.name}.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n  wrote {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
