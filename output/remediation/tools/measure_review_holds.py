"""Measure two of the writer's rules of 2026-09-23 on the rows the mass lane already decided.

Read-only; nothing here writes a database or a plan. It answers, with the writer's own functions:

* **the reviewer contradiction hold** (`review_stage.failing_half`,
  `write_stage.RULE_REVIEW_CONTRADICTS`): of the mass lane's 72 hand-held rows, how many does the rule
  hold (its recall on the hand-read), and of the rows that were written and accepted, how many would
  it have held (the false-hold count by the hand-read's standard). Per phrase, and per phrase over
  every reviewer answer of the run by its `REFUTED:` value - the evidence the phrase set was derived
  from;
* **the period-bucket gate** (`write_stage.same_bucket`, `RULE_SAME_BUCKET`): how many written
  `period_start` rows moved inside the stored value's bucket - from the lane's pinned plan, and, given
  `--journal`, from the production journal itself.

Inputs are the mass lane's own files (`lanes.py`): its pinned plan (`ALL_ROWS.jsonl`, refused unless it
is the reviewed one), its hold list, its run directory, plus two read-only exports of production:

    --written-keys   one change_key per line: the journal's `phase3:batch-%` keys (WRITTEN_KEYS_SQL)
    --journal        the journal's period_start rows of the lane, one JSON object per line
                     (JOURNAL_PERIOD_START_SQL)

    ./.venv/Scripts/python.exe output/remediation/tools/measure_review_holds.py \
        --written-keys output/remediation/logs/search_lane/written_keys.txt --journal <export>
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys
from collections.abc import Iterable, Mapping
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - the lane's paths, the reviewed-plan pin and the writer (W)
from phase3 import review_stage as RS  # noqa: E402 - the phrase set, the one spelling of it

W = lanes.W

#: The two read-only exports, as they were taken on 2026-09-23 (`psql -t -A`, one line per row).
WRITTEN_KEYS_SQL = (
    "SELECT change_key FROM remediation_change_log WHERE run_stamp LIKE 'phase3:batch-%' "
    "ORDER BY change_key"
)
JOURNAL_PERIOD_START_SQL = (
    "SELECT to_jsonb(t)::text FROM (SELECT change_key, row_pk, old_value, new_value, run_stamp "
    "FROM remediation_change_log WHERE run_stamp LIKE 'phase3:batch-%' "
    "AND column_name = 'period_start' ORDER BY change_key) t"
)

HELD, WRITTEN, BOUNDARY = "held", "written", "boundary"


def classify(
    rows: Iterable[Mapping[str, Any]], *, holds: set[str], written: set[str]
) -> dict[str, list[Mapping[str, Any]]]:
    """The plan's rows as written, held by hand, or neither (stopped at the boundary check)."""
    groups: dict[str, list[Mapping[str, Any]]] = {HELD: [], WRITTEN: [], BOUNDARY: []}
    for row in rows:
        key = str(row["change_key"])
        if key in written and key in holds:
            raise SystemExit(f"{key} is both written and held: the two records disagree")
        groups[WRITTEN if key in written else HELD if key in holds else BOUNDARY].append(row)
    return groups


def phrase_counts(rows: Iterable[Mapping[str, Any]]) -> tuple[int, collections.Counter[str]]:
    """(rows the rule holds, rows per phrase). A row counts under the first phrase it carries."""
    held = 0
    per: collections.Counter[str] = collections.Counter()
    for row in rows:
        phrase = RS.failing_half(str(row["verdict"]["reason"]))
        if phrase is not None:
            held += 1
            per[phrase] += 1
    return held, per


def same_bucket_rows(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The `period_start` rows whose old and new value share a bucket (`write_stage.same_bucket`)."""
    return [
        row
        for row in rows
        if row.get("column", "period_start") == "period_start"
        and W.same_bucket(row["old_value"], str(row["new_value"])) is not None
    ]


def answers_by_verdict(run_dir: pathlib.Path) -> dict[str, collections.Counter[str]]:
    """Per phrase, the reviewer answers of the run that carry it, by their `REFUTED:` value."""
    per: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    names = {True: "YES", False: "NO", None: "other"}
    for path in sorted(run_dir.glob("*/reviews/*.txt")):
        answer = RS.parse_review(path.read_text(encoding="utf-8"))
        per["(all answers)"][names[answer.refuted]] += 1
        phrase = RS.failing_half(answer.reason)
        if phrase is not None:
            per[phrase][names[answer.refuted]] += 1
    return per


def build_parser() -> argparse.ArgumentParser:
    paths = lanes.lane(lanes.MASS)
    parser = argparse.ArgumentParser(prog="measure-review-holds")
    parser.add_argument("--rows", default=str(paths.rows))
    parser.add_argument("--holds", default=str(paths.holds))
    parser.add_argument("--run-dir", default=str(paths.run_dir))
    parser.add_argument("--written-keys", required=True, help=f"export of: {WRITTEN_KEYS_SQL}")
    parser.add_argument("--journal", default="", help=f"export of: {JOURNAL_PERIOD_START_SQL}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows_path = pathlib.Path(args.rows)
    rows = lanes.read_jsonl(rows_path)
    lanes.assert_reviewed_plan(lanes.MASS, rows, path=rows_path)
    holds = {str(row["change_key"]) for row in lanes.read_jsonl(pathlib.Path(args.holds))}
    keys = pathlib.Path(args.written_keys).read_text(encoding="utf-8").splitlines()
    written = {key.strip() for key in keys if key.strip()}
    groups = classify(rows, holds=holds, written=written)
    print(f"plan rows {len(rows)}: " + ", ".join(f"{k} {len(v)}" for k, v in groups.items()))

    print("\nreviewer contradiction hold (review_stage.failing_half):")
    held_by_rule = {}
    for name, members in groups.items():
        count, per = phrase_counts(members)
        held_by_rule[name] = count
        print(f"  {name}: {count} of {len(members)} held by the rule")
        for phrase, n in per.most_common():
            print(f"      {n:4d}  {phrase}")
    print(f"  recall on the hand holds: {held_by_rule[HELD]}/{len(groups[HELD])}")
    print(f"  false holds on written rows: {held_by_rule[WRITTEN]}/{len(groups[WRITTEN])}")

    print("\nreviewer answers of the run carrying each phrase, by REFUTED value:")
    for phrase, counts in answers_by_verdict(pathlib.Path(args.run_dir)).items():
        print(f"  {phrase:52s} {dict(sorted(counts.items()))}")

    print("\nperiod-bucket gate (write_stage.same_bucket):")
    for name, members in groups.items():
        period = [row for row in members if row["column"] == "period_start"]
        print(f"  {name}: {len(same_bucket_rows(period))} of {len(period)} period_start rows")
    either = sum(
        1
        for row in groups[HELD]
        if RS.failing_half(str(row["verdict"]["reason"])) is not None
        or (row["column"] == "period_start" and same_bucket_rows([row]))
    )
    print(f"  hand holds caught by the bucket gate or the contradiction hold: {either}")
    if args.journal:
        journal = lanes.read_jsonl(pathlib.Path(args.journal))
        print(
            f"  production journal: {len(same_bucket_rows(journal))} of {len(journal)} "
            "period_start rows inside the stored bucket"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
