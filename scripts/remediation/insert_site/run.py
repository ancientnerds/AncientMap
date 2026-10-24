"""D57 insert lane: the one command line (runbook docs/procedures/INSERT_SITES.md).

    PY=./.venv/Scripts/python.exe; I="$PY scripts/remediation/insert_site/run.py"
    R=d57-2026-10-24; H=output/remediation/handoff/insert-$R

    $I candidates --run $R --demand-dir <main checkout>/output/seo-audit-2026-10-08/scratch/demand
    $I research export       --run $R --handoff $H-r0
    $I research brief        --run $R --handoff $H-r0 --batch-id ins-r0-b001
    $I research check-answer --run $R --handoff $H-r0 --batch-id B --label QID --text-file F
    $PY scripts/remediation/opus_handoff.py validate --dir $H-r0
    $I research import       --run $R
    $I research export-reask --run $R --handoff $H-r1        (while REASK.json names fields)
    $I plan              --run $R --step 1      (read-only: PLAN.jsonl, PLAN.md, ROLLBACK.sql)
    $I emit              --run $R --step 1      (APPLY.sql)
    $I rehearse          --run $R --step 1
    $I probe-guards      --run $R --step 1
    $I apply             --run $R --step 1
    $I readback          --run $R --step 1
    $I rehearse-rollback --run $R --step 1
    $I accept            --run $R --step 1      (ACCEPTED.json, INSERTED_SITES.txt)
    $I status            --run $R

`--run` names a directory under `output/remediation/insert_site/` (or is a path). The read-only and
file steps print one JSON object and exit 0, or `REFUSED: <why>` and exit 1; the writer's steps
exit with the shared writers' codes (`writer.py`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import apply as MA  # noqa: E402
from prod_write import OutcomeUnknown  # noqa: E402

from insert_site import candidates as C  # noqa: E402
from insert_site import plan as P  # noqa: E402
from insert_site import research as RS  # noqa: E402
from insert_site import writer as W  # noqa: E402

WRITER_COMMANDS = ("emit", "rehearse", "probe-guards", "apply", "readback", "rehearse-rollback")
REFUSALS = (
    C.CandidateError,
    RS.ResearchError,
    P.InsertPlanError,
    W.WriterError,
    MA.PlanError,
    ValueError,
)


def run_dir(name: str) -> Path:
    path = Path(name)
    return path if path.is_absolute() or len(path.parts) > 1 else C.ROOT / name


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO / path


def _country_check():
    from fields.plan import _country_check as country_check  # the boundary file, loaded once

    return country_check()


def plan(run: Path, number: int) -> dict[str, Any]:
    step = P.plan_step(run, number, country_check=_country_check())
    target = P.step_dir(run, number)
    if step.inserts:
        W.render_checked(step)  # both statements render and lint before any file is written
    P.write_step(step, target)
    if step.inserts:
        W.write_rollback(step, target)
    refused: dict[str, int] = {}
    for r in step.refusals:
        refused[r.reason] = refused.get(r.reason, 0) + 1
    return {
        "step": str(target),
        "run_stamp": step.run_stamp,
        "sites": len(step.inserts),
        "refused": refused,
        "proposals_closed": sum(len(i.proposals) for i in step.inserts),
        "contributions_promoted": sum(len(i.contributions) for i in step.inserts),
        "journal_rows": sum(i.journal_rows for i in step.inserts),
        "digest": step.digest,
    }


def status(run: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"run": str(run)}
    if (run / C.CANDIDATES_FILE).exists():
        lines = C.read_candidates(run)
        out["candidates"] = {s: sum(1 for x in lines if x["status"] == s) for s in C.STATUSES}
    out["rounds"] = [
        {"round": r["round"], "questions": len(r["asked"]), "handoff": r["handoff"]}
        for r in RS.read_rounds(run)
    ]
    if (run / RS.REASK_FILE).exists():
        out["waiting"] = len(RS.waiting(run))
    target = P.step_dir(run, 1)
    out["step-001"] = {
        name: (target / name).exists()
        for name in (P.PLAN_FILE, W.ROLLBACK_FILE, W.APPLY_FILE, W.ACCEPTED_FILE)
    }
    return out


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(
        prog="insert_site/run.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cand = sub.add_parser("candidates", help="build the candidate list (Wikidata + read-only)")
    cand.add_argument("--run", required=True)
    cand.add_argument("--demand-dir", required=True, type=Path)
    research = sub.add_parser("research", help="the research handoff")
    rsub = research.add_subparsers(dest="stage", required=True)
    for name in ("export", "export-reask", "brief", "check-answer", "import"):
        cmd = rsub.add_parser(name)
        cmd.add_argument("--run", required=True)
        if name != "import":
            cmd.add_argument("--handoff", required=True, type=Path)
        if name in ("brief", "check-answer"):
            cmd.add_argument("--batch-id", required=True)
        if name == "check-answer":
            cmd.add_argument("--label", required=True)
            cmd.add_argument("--text-file", required=True, type=Path)
        if name == "export":
            cmd.add_argument("--batch-size", type=int, default=RS.BATCH_SIZE)
    for name in ("plan", *WRITER_COMMANDS, "accept"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run", required=True)
        cmd.add_argument("--step", required=True, type=int)
        if name == "readback":
            cmd.add_argument("--rollback", action="store_true", help="read back a committed undo")
    stat = sub.add_parser("status")
    stat.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    run = run_dir(args.run)
    try:
        if args.command == "candidates":
            result: Any = C.build(run, args.demand_dir)
        elif args.command == "research":
            result = _research(args, run)
            if isinstance(result, str):
                print(result)
                return 0
        elif args.command == "plan":
            result = plan(run, args.step)
        elif args.command == "status":
            result = status(run)
        elif args.command == "accept":
            result = W.accept(P.step_dir(run, args.step))
            print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
            return MA.EXIT_OK if result["accepted"] else MA.EXIT_COMMITTED_UNCONFIRMED
        else:
            return _writer(args.command, P.step_dir(run, args.step), args)
    except OutcomeUnknown as exc:
        print(f"OUTCOME UNKNOWN: {exc}", file=sys.stderr)
        return MA.EXIT_UNKNOWN
    except REFUSALS as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return MA.EXIT_REFUSED
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    if args.command == "research" and args.stage == "check-answer":
        return 0 if result["ok"] else 1
    return 0


def _research(args: argparse.Namespace, run: Path) -> Any:
    if args.stage == "export":
        return RS.export(run, _resolve(args.handoff), args.batch_size)
    if args.stage == "export-reask":
        return RS.export_reask(run, _resolve(args.handoff))
    if args.stage == "brief":
        return RS.brief(run, _resolve(args.handoff), args.batch_id)
    if args.stage == "check-answer":
        text = args.text_file.read_text(encoding="utf-8")
        return RS.check_answer(run, _resolve(args.handoff), args.batch_id, args.label, text)
    return RS.import_rounds(run)


def _writer(command: str, target: Path, args: argparse.Namespace) -> int:
    if command == "emit":
        print(json.dumps(W.emit(target), ensure_ascii=False, indent=1, sort_keys=True))
        return MA.EXIT_OK
    if command == "rehearse":
        return W.command_rehearse(target)
    if command == "probe-guards":
        return W.command_probe_guards(target)
    if command == "apply":
        return W.command_apply(target)
    if command == "readback":
        return W.command_readback(target, rollback=args.rollback)
    return W.command_rehearse_rollback(target)


if __name__ == "__main__":
    raise SystemExit(main())
