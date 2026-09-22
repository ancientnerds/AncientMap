"""Count what the reviewer pass produced, and list what it cleared on a writable field.

Written before the pass finished, so it reads half-written batches too: a `review.json` that does not
parse is counted and reported, never skipped in silence. The listing at the end is the thing the writer
will act on - one line per cleared finding on a field Phase 3 can actually write, with the stored value,
the proposal and the reviewer's own reason, so a human can read the first chunk rather than trust it.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the lane's paths

sys.path.insert(0, str(lanes.REPO / "scripts" / "remediation"))

from phase3 import discover_stage as DS  # noqa: E402  (the path has to exist first)
from phase3 import model as M  # noqa: E402

WRITABLE = ("site_type", "period_start", "country")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review-totals")
    parser.add_argument("--lane", default=lanes.MASS, help="which run's paths (lanes.py)")
    run = lanes.lane(parser.parse_args(argv).lane).run_dir
    totals: collections.Counter[str] = collections.Counter()
    per_field: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    cleared: list[tuple[str, str, str, str, str]] = []
    unreadable: list[str] = []
    reports = sorted(run.glob("*/review.json"))

    for report_path in reports:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            unreadable.append(report_path.parent.name)
            continue
        totals["batches"] += 1
        for key in ("calls", "refuted", "unresolved", "with_problems"):
            value = report.get(key)
            totals[key] += value if isinstance(value, int) else 0
        cost = report.get("cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            try:
                totals["cost_usd_micro"] += round(float(cost) * 1_000_000)
            except OverflowError:
                unreadable.append(f"{report_path.parent.name}: cost_usd too large for a float")
        for verdict in report.get("verdicts") or []:
            field = str(verdict.get("field") or "?")
            asked_value = verdict.get("asked")
            applies_value = verdict.get("applies")
            # Only a real JSON `true` counts as asked/cleared: `== True` would also accept 1, and the
            # difference between "not asked" and "asked and refuted" is what this whole report is for.
            asked = asked_value if isinstance(asked_value, bool) else False
            applies = applies_value if isinstance(applies_value, bool) else False
            per_field[field]["gestellt" if asked else "nicht gestellt"] += 1
            if not asked:
                continue
            per_field[field]["freigegeben" if applies else "widerlegt"] += 1
            totals["freigegeben" if applies else "widerlegt"] += 1
            site_id = str(verdict.get("site_id") or "")
            if not applies or field in M.REPORT_ONLY_FIELDS:
                continue
            answer = run / report_path.parent.name / "answers" / f"{site_id}%2F{field}.txt"
            proposed = "(keine Antwortdatei)"
            if answer.exists():
                parsed = DS.parse_answer(answer.read_text(encoding="utf-8"))
                proposed = parsed.proposed or "(kein Vorschlag)"
            detail = run / report_path.parent.name / "input.json"
            stored = "?"
            if detail.exists():
                try:
                    batch = json.loads(detail.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Named and counted, not swallowed: a report that aborts on one broken batch would
                    # lose the listing for all the others, so the row says the value is unknown and the
                    # summary names the batch.
                    unreadable.append(f"{report_path.parent.name}: input.json unlesbar")
                    batch = {}
                for site in batch.get("sites") or []:
                    if site.get("site_id") == site_id:
                        finding = DS.field_finding(site, field)
                        stored = str(finding.get("current_value"))
            cleared.append((site_id, field, stored, proposed, str(verdict.get("reason") or "")))

    print(f"Pruefberichte gelesen: {totals['batches']} von {len(reports)} (unlesbar: {unreadable})")
    print(
        f"Pruef-Aufrufe: {totals['calls']} | Prueferkosten: {totals['cost_usd_micro'] / 1e6:.4f} USD"
    )
    print(f"freigegeben: {totals['freigegeben']} | widerlegt: {totals['widerlegt']}")
    print(f"nicht entschieden: {totals['unresolved']} | mit Problemen: {totals['with_problems']}")
    print("\nje Feld:")
    for field in sorted(per_field):
        print(f"  {field:18} {dict(per_field[field].most_common())}")
    print(f"\nfreigegeben auf schreibbaren Feldern: {len(cleared)} (von {len(WRITABLE)} Feldern)")
    for site_id, field, stored, proposed, reason in cleared:
        print(
            f"\n--- {site_id} / {field}\n  alt: {stored[:160]}\n  neu: {proposed[:160]}\n  {reason[:400]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
