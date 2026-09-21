"""Measure the reviewer against the blinded gold standard.

Two questions, and they are not the same one:

* **Sensitivity** - of the blinded check's own errors whose field the finder proposed a correction
  for, how many did the reviewer leave standing? A refuted real error is the expensive mistake: the
  correction exists, the evidence supports it, and the reviewer throws it away.
* **Specificity** - of the findings the reviewer reviewed on fields the blinded check examined and
  called correct, how many did it refute? A confirmed wrong correction is the other expensive
  mistake: it would be written to the database.

The truth is `gold_standard/sites.json`. `errors_found` names the errors the blinded check found;
`verdicts` names the fields it examined, with its verdict. A field in **neither** list was not
examined - it is reported as `unexamined` and never counted as correct, because a field nobody
looked at is not evidence of anything.

Run it after a reviewer pass:
    ./.venv/Scripts/python.exe output/remediation/gold_standard/measure_reviewer.py <run-dir>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from phase3 import discover_stage as DS  # noqa: E402

GOLD = REPO / "output" / "remediation" / "gold_standard"
RUN = (
    Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "output/remediation/phase3_runner/runs/gold6"
)
RESULT = GOLD / f"reviewer_result_{RUN.name}.json"


def truth() -> tuple[set[tuple[str, str]], set[tuple[str, str]], set[tuple[str, str]]]:
    """`(errors, correct, unexamined)` as (site_id, field) pairs, from the blinded record."""
    sites = json.loads((GOLD / "sites.json").read_text(encoding="utf-8"))
    errors: set[tuple[str, str]] = set()
    correct: set[tuple[str, str]] = set()
    for record in sites["records"]:
        site_id = record["site_id"]
        for error in record["errors_found"]:
            # The blinded check writes a compound label when one error sits in two fields at once
            # ("period_start + description", "hero_image + gallery_images"), and one label that is not
            # a field at all ("source coverage"). Keying on the raw string silently loses the first
            # and invents a phantom key for the second. Measured 2026-09-21: 7 of the 24 missed
            # errors in `truth_fields.json` looked absent from `errors_found`, and three real error
            # fields (`590d3dff/description`, `9ed175c7/card_description`, `b6af84c5/description`)
            # were counted as `unexamined`. Splitting on "+" reconstructs exactly those 24.
            for part in str(error["field"]).split("+"):
                if part.strip():
                    errors.add((site_id, part.strip()))
        for verdict in record["verdicts"]:
            if verdict["verdict"] == "CORRECT":
                correct.add((site_id, verdict["field"]))
    known = {site_id for record in sites["records"] for site_id in [record["site_id"]]}
    correct -= errors
    unexamined = {
        (site_id, field)
        for site_id in known
        for field in DS.DISCOVER_FIELDS
        if (site_id, field) not in errors and (site_id, field) not in correct
    }
    return errors, correct, unexamined


def finder_answers() -> dict[tuple[str, str], DS.DiscoverAnswer]:
    """Every answer the finder bought for this run, parsed with the shipped parser."""
    answers: dict[tuple[str, str], DS.DiscoverAnswer] = {}
    for path in sorted(RUN.glob("batch-*/answers/*.txt")):
        site_id, _, field = path.stem.partition("%2F")
        answers[(site_id, field)] = DS.parse_answer(path.read_text(encoding="utf-8"))
    return answers


def reviewer_verdicts() -> dict[tuple[str, str], dict]:
    """Every verdict the reviewer wrote, keyed the same way as the answers."""
    verdicts: dict[tuple[str, str], dict] = {}
    for path in sorted(RUN.glob("batch-*/review.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        for verdict in report.get("verdicts", []):
            verdicts[(verdict["site_id"], verdict["field"])] = verdict
    return verdicts


def main() -> int:
    errors, correct, unexamined = truth()
    answers = finder_answers()
    verdicts = reviewer_verdicts()
    if not verdicts:
        print(f"no review.json under {RUN} - nothing measured")
        return 1

    # What the finder proposed, per (site, field): only a complete WRONG with a value is reviewable.
    proposed = {
        key: answer
        for key, answer in answers.items()
        if answer.verdict == "WRONG" and answer.proposed and not answer.problems
    }
    real_errors_with_a_finding = sorted(errors & set(proposed))
    unrefuted_errors = [
        k for k in real_errors_with_a_finding if verdicts.get(k, {}).get("applies") is True
    ]
    refuted_errors = [
        k for k in real_errors_with_a_finding if verdicts.get(k, {}).get("refuted") is True
    ]

    reviewed = {k: v for k, v in verdicts.items() if v.get("asked") is True}
    on_correct = {k: v for k, v in reviewed.items() if k in correct}
    on_unexamined = {k: v for k, v in reviewed.items() if k in unexamined}
    on_errors = {k: v for k, v in reviewed.items() if k in errors}
    refuted_correct = [k for k, v in on_correct.items() if v.get("refuted") is True]
    # The other direction, and the expensive one: a suspect finding (the blinded check called the
    # stored value correct, so the finding is the doubtful half) that the reviewer let through is a
    # write nobody has argued for. It is *not* called a false positive above, because on these
    # fields refuting the finding is the reviewer doing its job.
    upheld_correct = [k for k, v in on_correct.items() if v.get("applies") is True]
    unresolved = [k for k, v in reviewed.items() if v.get("refuted") is None]

    result = {
        "run": str(RUN),
        "answers": len(answers),
        "reviewed": len(reviewed),
        "truth_errors": len(errors),
        "real_errors_with_a_finding": len(real_errors_with_a_finding),
        "real_errors_left_standing": len(unrefuted_errors),
        "real_errors_refuted": len(refuted_errors),
        "reviewed_on_correct_fields": len(on_correct),
        "reviewed_on_correct_fields_refuted": len(refuted_correct),
        "reviewed_on_correct_fields_upheld": len(upheld_correct),
        "reviewed_on_unexamined_fields": len(on_unexamined),
        "reviewed_on_error_fields": len(on_errors),
        "unresolved": len(unresolved),
        "refuted_counts": dict(Counter(str(v.get("refuted")) for v in reviewed.values())),
        "real_errors_left_standing_list": [f"{s[:8]}%2F{f}" for s, f in unrefuted_errors],
        "real_errors_refuted_list": [f"{s[:8]}%2F{f}" for s, f in refuted_errors],
        "refuted_on_correct_list": [f"{s[:8]}%2F{f}" for s, f in refuted_correct],
        "upheld_on_correct_list": [f"{s[:8]}%2F{f}" for s, f in upheld_correct],
    }
    RESULT.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    print(f"run                          {RUN.name}")
    print(f"answers on disk              {result['answers']}")
    print(f"findings the reviewer asked  {result['reviewed']}")
    print(f"  refuted / not / unresolved {result['refuted_counts']}")
    print()
    print(f"blinded truth errors         {result['truth_errors']}")
    print(f"  the finder proposed one    {result['real_errors_with_a_finding']}")
    print(f"    left standing (applied)  {result['real_errors_left_standing']}")
    print(f"    refuted by the reviewer  {result['real_errors_refuted']}")
    print()
    print(f"reviewed, blinded-CORRECT    {result['reviewed_on_correct_fields']}")
    print(f"  rejected by the reviewer   {result['reviewed_on_correct_fields_refuted']}")
    print(f"  upheld, would be written   {result['reviewed_on_correct_fields_upheld']}")
    print(f"reviewed, blinded-unexamined {result['reviewed_on_unexamined_fields']}")
    print(f"reviewed, blinded-error      {result['reviewed_on_error_fields']}")
    print()
    print(f"written to {RESULT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
