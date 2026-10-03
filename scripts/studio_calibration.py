"""The claim check's calibration (owner decision O18, 2026-10-03).

Before a MiniMax verdict may gate a publish, the model has to agree with the verdicts that
were already accepted for the same tasks. This script measures that on the only paper the
studio has published, `95fa3798` (UFO/UAP, the one `theo_paper_publications` row), and it
never touches that paper's own workspace: it copies the workspace into
`<STUDIO_ASSETS>/calibration/<stamp>-<request id>/`, exports the claim tasks there, answers
the tasks whose ground truth exists, and compares.

**The reference is the recorded verdict of every `evidence.json` entry** - the verdict the
research run (MiniMax M3) stored for that claim, all 42 of them `supported`. It is *not* a
checked reference: no human or higher model audited it, so agreement with it measures
*consistency with the research run*, not truth. The report therefore names it as
`"reference": "MiniMax-M3, unchecked"` and every answer is re-checked at the source text.

Tasks are the 42 `evidence` ones; the `paragraph` and `coherence` tasks have no recorded
verdict anywhere, so they are not part of the measurement.

    ./.venv/Scripts/python.exe scripts/studio_calibration.py --request-id 95fa3798-...
    ./.venv/Scripts/python.exe scripts/studio_calibration.py --request-id 95fa3798-... --dry-run

Owner protocol for reading the result (2026-10-03, binding):

1. The script writes a `spot_check` worksheet: **every** deviation plus **10 randomly
   sampled agreements** (`SPOT_SEED` makes the sample reproducible), each with the answer's
   verbatim quote, the source it names and the text the quote has to occur in. Read every
   line of it at the source and write a verdict into `spot_check_verdicts.json`
   (`task_id` -> `"holds"` or `"refuted"` with one sentence why).
2. Pass = the worksheet is complete and every line holds, **and** >= 90 % agreement and 0
   false sources. A false source is an answer that quotes a source the task does not cite,
   or quotes text that is not in that source; the driver's own machine check refuses both
   before the line is written, so the count is taken from the accepted `verdicts.jsonl`.
3. The result goes to the owner before any publish uses a MiniMax verdict.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.studio import config, handoff, mcode_checks  # noqa: E402
from pipeline.studio.paper import claims  # noqa: E402
from pipeline.studio.paper.workspace import PaperWorkspace, read_json  # noqa: E402

AGREEMENT_PASS = 0.90
CALIBRATION_DIR = "calibration"
#: The reference the 42 recorded verdicts come from. Never called ground truth: nobody
#: audited them, so agreement with them is consistency, not truth.
REFERENCE = "MiniMax-M3, unchecked"
#: How many agreements of the spot check to sample, and the seed that makes it repeatable.
SPOT_AGREEMENTS = 10
SPOT_SEED = 20261003


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _recorded(ws: PaperWorkspace) -> dict[str, dict[str, Any]]:
    """The recorded verdict per evidence task, keyed by the task's `ref` (an `ev-NN` id)."""
    entries = read_json(ws.evidence, "the paper's evidence")
    return {e["id"]: e for e in entries}


def _copy(ws: PaperWorkspace, stamp: str) -> PaperWorkspace:
    target = config.studio_assets() / CALIBRATION_DIR / f"{stamp}-{ws.request_id}"
    if target.exists():
        raise SystemExit(f"{target} exists: pick a new stamp or delete that copy first")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ws.root, target, ignore=shutil.ignore_patterns("mcode_runs", "*.imported-*.jsonl"))
    return PaperWorkspace(target, ws.request_id)


def _only_evidence(ws: PaperWorkspace) -> list[str]:
    """Keep the evidence tasks pending; the other kinds have no recorded verdict."""
    rows = handoff.read_jsonl(ws.claims_dir / handoff.TASKS_FILE)
    evidence = [r for r in rows if r["kind"] == "evidence"]
    out = ws.claims_dir / handoff.PENDING_FILE
    out.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in evidence),
        encoding="utf-8",
        newline="",
    )
    return [r["task_id"] for r in evidence]


def spot_check(ws: PaperWorkspace, rows: dict[str, dict[str, Any]], lines: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The worksheet the owner protocol reads at the source text.

    Every deviation plus `SPOT_AGREEMENTS` random agreements, each with the answer's own
    quote, the source it names, the file the quote has to occur in and the context around
    it - so a reader can judge the line without re-running anything.
    """
    dossier = claims.load_dossier(ws)
    pairs = []
    for task_id, row in rows.items():
        if row["kind"] != "evidence":
            continue
        line = lines.get(task_id)
        if line is None:
            continue
        pairs.append((task_id, row, line))
    deviations = [(t, r, l) for t, r, l in pairs if l["verdict"] != "supported"]
    agreements = [(t, r, l) for t, r, l in pairs if l["verdict"] == "supported"]
    # A repeatable sample of the agreements, not a secret: S311 does not apply.
    sampled = random.Random(SPOT_SEED).sample(  # noqa: S311
        agreements, min(SPOT_AGREEMENTS, len(agreements))
    )

    def line_of(task_id: str, row: dict[str, Any], answer: dict[str, Any], why: str) -> dict[str, Any]:
        sid = answer.get("quote_source_id") or ""
        text = claims.live_text(ws, dossier.sources[sid]) if sid and sid in dossier.sources else ""
        quote = answer.get("quote") or ""
        at = text.find(quote) if quote and text else -1
        return {
            "task_id": task_id,
            "ref": row["ref"],
            "why": why,
            "claim": row["claim"],
            "answer_verdict": answer["verdict"],
            "quote": quote,
            "quote_source_id": sid,
            "quote_occurs_in_text": at >= 0,
            "context": text[max(0, at - 200) : at + len(quote) + 200] if at >= 0 else "",
            "fix_suggestion": answer.get("fix_suggestion", ""),
            "verdict": "",
        }

    return {
        "reference": REFERENCE,
        "protocol": (
            "read every line at the source text, then write "
            "spot_check_verdicts.json = {task_id: 'holds' | 'refuted: <why>'}"
        ),
        "deviations": [line_of(t, r, l, "deviation: the answer is not supported") for t, r, l in deviations],
        "sampled_agreements": [
            line_of(t, r, l, f"random agreement (seed {SPOT_SEED})") for t, r, l in sampled
        ],
    }


def with_verdicts(worksheet: dict[str, Any], path: Path) -> dict[str, Any]:
    """The worksheet plus the owner's verdicts, and whether every line was judged."""
    if not path.is_file():
        worksheet["verdicts"] = None
        worksheet["all_judged"] = False
        return worksheet
    given = json.loads(path.read_text(encoding="utf-8"))
    lines = worksheet["deviations"] + worksheet["sampled_agreements"]
    for line in lines:
        line["verdict"] = given.get(line["task_id"], "")
    judged = [line for line in lines if line["verdict"].strip()]
    worksheet["verdicts"] = given
    worksheet["judged"] = len(judged)
    worksheet["of"] = len(lines)
    worksheet["all_judged"] = len(judged) == len(lines)
    worksheet["refuted"] = [
        line["task_id"] for line in lines if not line["verdict"].strip().lower().startswith("holds")
    ]
    return worksheet


def compare(ws: PaperWorkspace, recorded: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The measurement: agreement with the recorded verdicts, and the false sources."""
    rows = {r["task_id"]: r for r in handoff.read_jsonl(ws.claims_dir / handoff.TASKS_FILE)}
    lines = {
        r["task_id"]: r for r in handoff.read_jsonl(ws.claims_dir / handoff.VERDICTS_FILE)
    }
    pairs: list[dict[str, Any]] = []
    false_sources: list[str] = []
    for task_id, row in sorted(rows.items()):
        if row["kind"] != "evidence":
            continue
        was = recorded.get(row["ref"], {}).get("verdict")
        now = lines.get(task_id, {}).get("verdict")
        pairs.append({"ref": row["ref"], "task_id": task_id, "recorded": was, "answered": now})
        if now != "supported" or was != "supported":
            continue
        line = lines[task_id]
        cited = {c["source_id"] for c in row["cited"]}
        if line["quote_source_id"] not in cited:
            false_sources.append(f"{row['ref']}: quote names {line['quote_source_id']!r}, not cited")
    answered = [p for p in pairs if p["answered"] is not None]
    agree = [p for p in answered if p["recorded"] == p["answered"]]
    share = len(agree) / len(answered) if answered else 0.0
    return {
        "tasks": len(pairs),
        "answered": len(answered),
        "agreement": round(share, 4),
        "agreement_pass": share >= AGREEMENT_PASS,
        "recorded_verdicts": dict(Counter(p["recorded"] for p in pairs)),
        "answered_verdicts": dict(Counter(p["answered"] for p in answered)),
        "false_sources": false_sources,
        "differences": [p for p in pairs if p["recorded"] != p["answered"]],
        "overruled_by_skeptic": sum(
            1 for line in lines.values() if "overruled by" in line.get("answered_by", "")
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--request-id", required=True, help="a published paper with a studio workspace")
    ap.add_argument("--dry-run", action="store_true", help="print what would be run and stop")
    ap.add_argument(
        "--resume",
        help="an existing calibration copy to carry on in; a task its verdicts.jsonl already "
        "holds is not answered again, so an interrupted run keeps its answers",
    )
    args = ap.parse_args(argv)

    source = config.paper_dir(args.request_id)
    if not source.is_dir():
        raise SystemExit(f"{source} does not exist: no studio workspace for that request")
    if args.dry_run:
        print(
            json.dumps(
                {
                    "workspace": str(source),
                    "recorded_evidence_verdicts": len(read_json(PaperWorkspace(source, args.request_id).evidence, "evidence")),
                    "copy_target": str(
                        config.studio_assets() / CALIBRATION_DIR / f"<stamp>-{args.request_id}"
                    ),
                    "model": mcode_checks.mcode.MODEL,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    stamp = _stamp()
    if args.resume:
        copy_root = Path(args.resume)
        if not copy_root.is_dir():
            raise SystemExit(f"{copy_root} does not exist: nothing to resume")
        stamp = copy_root.name.split("-", 1)[0]
        ws = PaperWorkspace(copy_root, args.request_id)
    else:
        ws = _copy(PaperWorkspace(source, args.request_id), stamp)
    recorded = _recorded(PaperWorkspace(source, args.request_id))
    claims.export_claims(ws)
    wanted = _only_evidence(ws)
    print(f"calibration copy: {ws.root}", flush=True)
    print(f"re-answering {len(wanted)} evidence tasks on {mcode_checks.mcode.MODEL}", flush=True)

    result = mcode_checks.answer_claims(ws, repo=config.REPO)
    rows = {r["task_id"]: r for r in handoff.read_jsonl(ws.claims_dir / handoff.TASKS_FILE)}
    lines = {r["task_id"]: r for r in handoff.read_jsonl(ws.claims_dir / handoff.VERDICTS_FILE)}
    report = {
        "stamp": stamp,
        "request_id": args.request_id,
        "model": mcode_checks.mcode.MODEL,
        "reference": REFERENCE,
        "source_workspace": str(source),
        "copy": str(ws.root),
        "check": result.as_dict(),
    }
    report["measurement"] = compare(ws, recorded)
    report["spot_check"] = with_verdicts(
        spot_check(ws, rows, lines), ws.root / "spot_check_verdicts.json"
    )
    measured = report["measurement"]
    report["passed"] = bool(
        measured["agreement_pass"]
        and not measured["false_sources"]
        and report["spot_check"].get("all_judged")
        and not report["spot_check"].get("refuted")
    )
    out = ws.root / "calibration_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
    print(json.dumps(measured, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "spot_check": {
                    "reference": REFERENCE,
                    "deviations": len(report["spot_check"]["deviations"]),
                    "sampled_agreements": len(report["spot_check"]["sampled_agreements"]),
                    "judged": report["spot_check"].get("judged", 0),
                    "all_judged": report["spot_check"].get("all_judged"),
                    "refuted": report["spot_check"].get("refuted"),
                },
                "passed": report["passed"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"report: {out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
