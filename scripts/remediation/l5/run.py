"""L5, the journalled link and name pass (HUMAN_ONLY B1-L, B1-N, Nr. 7) - the command line.

The runbook is `docs/procedures/SITES_DB_REMEDIATION_2026-09.md`, section "WE lanes". In order:

    run.py population                       read-only: who is asked, and the read the questions
                                            are built from (POPULATION.jsonl, COUNTS.json,
                                            export/READ.json)
    run.py export --handoff DIR             round 1: every asked site, batches of --per-batch
    run.py brief --round R --batch-id B     the instruction of the Opus agent of one batch
    run.py check-answer --round R --batch-id B --label SITE --text-file F
                                            the shape of one answer, before it is recorded
    opus_handoff.py validate --dir DIR      every question answered, in shape, by Opus
    run.py import --round R                 fetch, quote-check, resolve, decide; DECISIONS.jsonl
    run.py export-reask --handoff DIR2      a new round for the held sites, each with its reason
    run.py plan                             read-only live read; the link steps and the name lane
    run.py step COMMAND --step N            check | rehearse | probe-guards | apply | verify |
                                            rehearse-rollback, per link step (`links.py`)
    apply.py --lane name-l5 --emit ...      the name lane, like every mechanical lane

Nothing here writes to production except `step apply` (and the name lane's `--apply`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import opus_handoff as OH  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical.lane import NAME_L5  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from l5 import handoff as H  # noqa: E402
from l5 import links  # noqa: E402
from l5 import plan as L5P  # noqa: E402
from l5 import population as POP  # noqa: E402
from l5.decide import DECIDED  # noqa: E402

OUT = POP.OUT


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def cmd_population() -> dict[str, Any]:
    rounds = H.load_rounds(OUT)
    if rounds:
        raise H.HandoffError(
            f"round {rounds[0].name} was exported from the read of {rounds[0].read_at}: every "
            "question is rebuilt from that read on import, so a new read would orphan them"
        )
    population = POP.members(POP.load_names())
    read = POP.read_production(population, MP.psql_json_reader())
    return POP.write(OUT, population, read)


def cmd_plan() -> dict[str, Any]:
    decisions = [d for d in H.load_decisions(OUT) if d["status"] == DECIDED]
    read = POP.load_read(OUT)
    live = L5P.read_live(decisions, POP.PINNED_NAMES, MP.psql_json_reader())
    built = L5P.build(decisions, read["sites"], live)
    steps = L5P.steps(built.links)
    for number, rows in enumerate(steps, start=1):
        L5P.write_step(L5P.step_wave(number), rows)
    if built.names:
        L5P.write_names(L5P.name_plan(built, H.now_utc()), A.lane_dir(NAME_L5))
    H.write_jsonl(OUT / "SKIPPED.jsonl", built.skipped)
    counts = built.counts()
    (OUT / "PLAN_COUNTS.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {**counts, "steps": [L5P.step_wave(n).out.name for n in range(1, len(steps) + 1)]}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("population", help="read-only: the population and the question read")
    for name in ("export", "export-reask"):
        cmd = sub.add_parser(name, help="a round of questions into a new handoff directory")
        cmd.add_argument("--handoff", required=True, type=Path)
        cmd.add_argument("--per-batch", type=int, default=H.PER_BATCH)
    for name in ("brief", "check-answer"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--round", required=True)
        cmd.add_argument("--batch-id", required=True)
    sub.choices["check-answer"].add_argument("--label", required=True)
    sub.choices["check-answer"].add_argument("--text-file", required=True, type=Path)
    sub.add_parser("import").add_argument("--round", required=True)
    sub.add_parser("plan", help="read-only live read; the link steps and the name lane")
    step = sub.add_parser("step", help="a link step's production command")
    step.add_argument("step_command", choices=sorted(links.COMMANDS))
    step.add_argument("--step", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "population":
            _print(cmd_population())
        elif args.command == "export":
            if H.load_rounds(OUT):
                raise H.HandoffError("round 1 is exported already - re-ask with export-reask")
            record = H.export_round(
                OUT,
                H.resolve_path(args.handoff),
                H.first_round_sites(OUT),
                per_batch=args.per_batch,
            )
            _print(
                {"round": record.name, "sites": len(record.sites), "batches": len(record.batches)}
            )
        elif args.command == "export-reask":
            held = H.held_sites(OUT)
            record = H.export_round(
                OUT,
                H.resolve_path(args.handoff),
                sorted(held),
                earlier=held,
                per_batch=args.per_batch,
            )
            _print(
                {"round": record.name, "sites": len(record.sites), "batches": len(record.batches)}
            )
        elif args.command == "brief":
            print(H.brief(OUT, args.round, args.batch_id))
        elif args.command == "check-answer":
            text = H.resolve_path(args.text_file).read_bytes().decode("utf-8")
            problem = H.check_answer(OUT, args.round, args.batch_id, args.label, text)
            _print({"ok": problem is None, "problem": problem})
            return 0 if problem is None else 1
        elif args.command == "import":
            _print(H.import_round(OUT, args.round))
        elif args.command == "plan":
            _print(cmd_plan())
        else:
            return links.COMMANDS[args.step_command](args.step)
    except (
        H.HandoffError,
        OH.HandoffError,
        Q.AuditError,
        MP.PlanError,
        links.StepError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
