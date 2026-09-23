"""Score a search-route pilot against the gold standard: by the sealed thresholds, and by the writer.

`output/remediation/phase3_runner/SEARCH_PILOT.md` fixed four pass thresholds before the first pilot's
first search. This reads a pilot's run directory and the gold standard, with the pipeline's own parser
and citation check, and reports each threshold's number and whether it holds:

1. no fabricated citation - an answer whose quoted text is not in the evidence the finder was shown
   (`discover_stage.finder_pages`: the fetched targets and the search snippets, which is what the
   finder's prompt carried; `discover_stage.source_problems` over them);
2. no harmful decision - a finder WRONG the reviewer did not refute, on a field the human called
   CORRECT;
3. agreement >= 90 % on the decided fields (finder CORRECT, or finder WRONG not refuted);
4. transport - every search stored or recorded as failed, the run not stopped.

The thresholds and their definitions stay as sealed. Since 2026-09-23 the writer applies three more
rules than it did when they were sealed - a `period_start` move inside the stored bucket, a search hit
whose fetched page does not carry the quote, a reviewer whose `WHY:` line names a failing half - so
**in addition** this reports what the writer itself would do with the pilot's batches
(`write_stage.load_plan`, the plan a `--apply` would be rendered from): the rows it would write, each
against the human verdict, and every rerun field it refuses with its rule. That is what would reach
production; the sealed block is what the pilot is passed or failed on. A batch the writer cannot plan
yet - its cited hits were never fetched (`hitpages.json` missing) - is named, never guessed.

Beside it, **what each rule costs** (`rule_cost`): each of the three switched off alone, then all
three, and the rows that appear - so a pilot's price in agreeing writes lost is measured rather than
asserted. On the first pilot: (a) alone refuses nothing, (b) alone refuses Ahu Tongariki
`period_start` (human WRONG), (c) alone refuses Lake Mungo and Cueva de los Murcielagos
`period_start` (both human WRONG); all three off is the writer before them, 5 rows - 3 agreeing, 1
unsupported (Lake Mungo `site_type`), 1 harmful (Aubrey Holes).

Read-only; no database, no network.

    ./.venv/Scripts/python.exe output/remediation/tools/score_search_pilot.py
    ./.venv/Scripts/python.exe output/remediation/tools/score_search_pilot.py \
        --run-dir output/remediation/phase3_runner/runs/search-gold2 --prefix srgdb \
        --progress output/remediation/logs/search_gold2/progress.json
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
for _root in (REPO, REPO / "scripts" / "remediation"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import review_stage as RS  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import write_stage as W  # noqa: E402

RUN = REPO / "output/remediation/phase3_runner/runs/search-gold"
GOLD = REPO / "output/remediation/gold_standard/sites.json"
PROGRESS = REPO / "output/remediation/logs/search_gold/progress.json"
PREFIX = "srgd"
AGREEMENT_FLOOR = 0.90


def gold_verdicts(path: Path) -> dict[tuple[str, str], str]:
    records = json.loads(path.read_text(encoding="utf-8"))["records"]
    return {
        (record["site_id"], verdict["field"]): str(verdict["verdict"]).upper()
        for record in records
        for verdict in record["verdicts"]
    }


def reviews(batch: Path) -> dict[tuple[str, str], dict]:
    data = json.loads((batch / "review.json").read_text(encoding="utf-8"))
    return {(v["site_id"], v["field"]): v for v in data["verdicts"]}


def batches_of(run: Path, prefix: str) -> list[Path]:
    """The pilot's batch directories, `<prefix>-NNNN`, in name order. None at all is refused."""
    found = sorted(path for path in run.glob(f"{prefix}-*") if path.is_dir())
    if not found:
        raise SystemExit(f"{run}: no {prefix}-NNNN batch directory")
    return found


def sealed(
    batches: list[Path], human: dict[tuple[str, str], str], progress: dict[str, Any]
) -> tuple[bool, list[str]]:
    """The four sealed thresholds, as `SEARCH_PILOT.md` defines them. Returns (passed, lines)."""
    rows = []
    fabricated = []
    unaccounted = 0
    for batch in batches:
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
                site_id=sid, site=site, store=store, hit_pages=False, failures=failures.get(sid, {})
            )
            shown = DS.finder_pages(excerpts)
            for field in SE.rerun_fields(site) or ():
                path = batch / "answers" / f"{sid}%2F{field}.txt"
                answer = DS.parse_answer(path.read_text(encoding="utf-8"))
                finder = str(answer.verdict).upper() if answer.verdict else "NONE"
                problems = DS.source_problems(answer, shown)
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

    decided = [r for r in rows if r["decided"]]
    agree = [r for r in decided if r["decided"] == r["human"]]
    harmful = [r for r in decided if r["decided"] == "WRONG" and r["human"] == "CORRECT"]
    agreement = len(agree) / len(decided) if decided else 0.0
    lines = [
        f"fields rerun: {len(rows)}  finder: {dict(collections.Counter(r['finder'] for r in rows))}",
        f"moved from UNVERIFIABLE to a decision: {len(decided)} of {len(rows)}",
        f"human verdicts of the rerun fields: {dict(collections.Counter(r['human'] for r in rows))}",
    ]
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
        lines.append(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
    for sid, field, problems in fabricated:
        lines.append(f"    fabricated: {sid} {field}: {problems}")
    for r in harmful:
        lines.append(f"    harmful: {r}")
    for r in decided:
        if r["decided"] != r["human"]:
            lines.append(f"    disagrees: {r}")
    passed = all(ok for _, ok, _ in checks)
    lines.append(f"PILOT RESULT: {'PASS' if passed else 'FAIL'}")
    return passed, lines


def writer_plans(
    batches: list[Path], human: dict[tuple[str, str], str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """`(written, refused, unplanned)`: every row `write_stage.load_plan` would write out of the
    pilot's batches, every rerun field it refuses with its rule, and every batch it cannot plan yet
    (its cited hits were never fetched), each row beside the human verdict of its field."""
    written: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    unplanned: list[str] = []
    for batch in batches:
        if (batch / MS.SEARCH_REPORT_NAME).exists() and not (batch / MS.HIT_REPORT_NAME).exists():
            unplanned.append(f"{batch.name}: no {MS.HIT_REPORT_NAME} (verify-hits has not run)")
            continue
        record = json.loads((batch / "input.json").read_text(encoding="utf-8"))
        asked = {
            (site["site_id"], field)
            for site in record["sites"]
            for field in SE.rerun_fields(site) or DS.DISCOVER_FIELDS
        }
        plan = W.load_plan(batch)
        for row in plan.rows:
            written.append(
                {
                    "batch": batch.name,
                    "site_id": row.site_id,
                    "field": row.column,
                    "old": row.old_value,
                    "new": row.new_value,
                    "human": human.get((row.site_id, row.column)),
                }
            )
        for refusal in plan.refusals:
            if (refusal.site_id, refusal.field) in asked:
                refused.append(
                    {
                        "batch": batch.name,
                        "site_id": refusal.site_id,
                        "field": refusal.field,
                        "rule": refusal.rule,
                        "human": human.get((refusal.site_id, refusal.field)),
                    }
                )
    return written, refused, unplanned


def writer_decision(batches: list[Path], human: dict[tuple[str, str], str]) -> list[str]:
    """What the writer would write out of each batch, row by row, and what it refuses and why.

    A row the writer would write means the pipeline says the stored value is WRONG and writes the
    new one: it agrees with a human WRONG, is **harmful** against a human CORRECT, and unsupported
    against a human UNVERIFIABLE. Every rerun field without a row is listed with the writer's rule.
    """
    written, refused, unplanned = writer_plans(batches, human)
    by_human = collections.Counter(str(row["human"]) for row in written)
    lines = [
        "WRITER DECISION (not sealed; what would reach production)",
        f"  rows the writer would write: {len(written)}  by human verdict: {dict(by_human)}",
        f"  harmful writes (human CORRECT): {by_human.get('CORRECT', 0)}",
        f"  agreeing writes (human WRONG): {by_human.get('WRONG', 0)} of {len(written)}",
        "  rerun fields refused, by rule: "
        + str(dict(sorted(collections.Counter(r["rule"] for r in refused).items()))),
    ]
    refused_wrong = [r for r in refused if r["human"] == "WRONG"]
    lines.append(f"  refused although the human says WRONG: {len(refused_wrong)}")
    for row in written:
        lines.append(f"    writes: {row}")
    for row in refused:
        if row["rule"] != W.RULE_NOT_RERUN:
            lines.append(f"    refuses: {row}")
    for reason in unplanned:
        lines.append(f"    NOT PLANNED: {reason}")
    lines.append(
        "WRITER RESULT: "
        + (
            "NOT AVAILABLE"
            if unplanned
            else f"{len(written)} row(s), {by_human.get('CORRECT', 0)} harmful"
        )  # fmt: skip
    )
    return lines


#: The writer's three rules of 2026-09-23, each by the one entry point that switches it off: the
#: period-bucket gate (`_same_bucket_refusal`), the hit-page check (`_hit_page_refusal`, with the
#: citation read on what the finder was shown, `finder_pages`, as before the rule), and the reviewer
#: contradiction hold (`failing_half`). The scorer replaces them inside `rules_off` only, to say what
#: each rule changes on its own; the writer has no switch and must not grow one.
RULE_SWITCHES: dict[str, tuple[tuple[Any, str, Any], ...]] = {
    "(a) period-bucket gate": ((W, "_same_bucket_refusal", lambda *args, **kwargs: None),),
    "(b) hit-page check": (
        (W, "_hit_page_refusal", lambda **kwargs: None),
        (DS, "pages_from_excerpts", DS.finder_pages),
    ),
    "(c) contradiction hold": ((RS, "failing_half", lambda reason: None),),
}


@contextlib.contextmanager
def rules_off(names: Iterable[str]) -> Iterator[None]:
    """The writer with the named `RULE_SWITCHES` switched off, for the length of the block."""
    with contextlib.ExitStack() as stack:
        for name in names:
            for target, attribute, replacement in RULE_SWITCHES[name]:
                stack.enter_context(mock.patch.object(target, attribute, replacement))
        yield


def _row_label(row: dict[str, Any]) -> str:
    return (
        f"{row['batch']} {row['site_id'][:8]} {row['field']} {row['old']!r} -> {row['new']!r} "
        f"(human {row['human']})"
    )


def rule_cost(batches: list[Path], human: dict[tuple[str, str], str]) -> list[str]:
    """What each of the writer's three 2026-09-23 rules changes on its own, measured, not asserted.

    Each rule is switched off alone, and then all three (the writer as it was before them). A row
    that appears only with one rule off is a write that rule alone refuses: against a human WRONG it
    is the rule's cost, against a human CORRECT a harmful write it stops, against UNVERIFIABLE an
    unsupported one. A row two rules refuse appears in neither single column - the two-rules-off
    line shows it. Added 2026-09-23 after the first pilot's cost was stated, not measured.
    """
    with rules_off(()):
        base = {_row_label(row) for row in writer_plans(batches, human)[0]}
    lines = ["WRITER RULE COST (each rule switched off alone; not sealed)"]
    lines.append(f"  all rules on: {len(base)} row(s)")
    names = list(RULE_SWITCHES)
    for off in [*([name] for name in names), names]:
        with rules_off(off):
            rows = writer_plans(batches, human)[0]
        extra = [row for row in rows if _row_label(row) not in base]
        counts = dict(sorted(collections.Counter(str(row["human"]) for row in extra).items()))
        label = "all three off (the writer before them)" if off == names else f"{off[0]} off"
        lines.append(f"  {label}: {len(extra)} more row(s), by human verdict {counts}")
        lines.extend(f"      {_row_label(row)}" for row in extra)
    return lines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="score-search-pilot")
    parser.add_argument("--run-dir", default=str(RUN), help="the pilot's run directory")
    parser.add_argument("--prefix", default=PREFIX, help="the pilot plan's batch-id prefix")
    parser.add_argument("--progress", default=str(PROGRESS), help="the mass driver's progress.json")
    parser.add_argument("--gold", default=str(GOLD), help="gold_standard/sites.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    human = gold_verdicts(Path(args.gold))
    batches = batches_of(Path(args.run_dir), args.prefix)
    progress = json.loads(Path(args.progress).read_text(encoding="utf-8"))
    passed, lines = sealed(batches, human, progress)
    for line in lines:
        print(line)
    decision = writer_decision(batches, human)
    for line in decision:
        print(line)
    if not decision[-1].endswith("NOT AVAILABLE"):
        for line in rule_cost(batches, human):
            print(line)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
