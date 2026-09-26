"""The served-image lane's command line (WD2, O6). The runbook, with every gate and the undo, is
`docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md`; in order:

    run.py read           --run-dir R          production (read-only) -> R/READ.json
    run.py precheck       --run-dir R [--harvest H] [--subset]
                                               P18/P373 against WD1's harvest -> R/PRECHECK.jsonl
    run.py export-check   --run-dir R --handoff H-check [--population all|unconfirmed]
                                               every served image (default), 12 per batch
    run.py brief          --run-dir R --handoff H-check --batch-id B
    run.py check-answer   --run-dir R --handoff H-check --batch-id B --label L --text-file F
    opus_handoff.py validate --dir H-check
    run.py import-check   --run-dir R          -> R/CHECK.jsonl
    run.py export-replace --run-dir R --handoff H-replace
                                               every served image that does not depict its site
    (brief, check-answer, validate as above)
    run.py import-replace --run-dir R          -> R/REPLACE.jsonl
    run.py plan           --run-dir R          -> R/chunks/chunk-NNN (<= 100 sites each)
    chunk_writer.py R/chunks/chunk-NNN --check | --rehearse | --apply | --readback |
                                        --rehearse-rollback
    run.py accept         --run-dir R --chunk R/chunks/chunk-NNN
                                               read-only: every site of the chunk serves what the
                                               plan says; exit 0 only with 0 deviations
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import opus_handoff as OH  # noqa: E402
import research_web  # noqa: E402
from gallery_audit.vision import Images  # noqa: E402

from served_image import plan as PL  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image import vision as V  # noqa: E402
from served_image.commons import Commons  # noqa: E402
from served_image.precheck import (  # noqa: E402
    DEFAULT_HARVEST,
    load_harvest,
    load_prechecks,
    run_precheck,
    write_prechecks,
)

READ = "READ.json"
PRECHECK = "PRECHECK.jsonl"
PRECHECK_SUMMARY = "PRECHECK.json"


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def commons_for(run: Path) -> Commons:
    return Commons(run / "commons", research_web.client())


def cmd_read(run: Path) -> dict[str, Any]:
    data = ST.read_production()
    digest = ST.write_read(run / READ, data)
    return {"sites": len(data["sites"]), "images": len(data["images"]), "sha256": digest}


def cmd_precheck(run: Path, harvest_root: Path, subset: bool) -> dict[str, Any]:
    state = ST.load_read(run / READ)
    result = run_precheck(state, load_harvest(harvest_root), commons_for(run), subset=subset)
    write_prechecks(run / PRECHECK, result)
    summary = {
        "read_sha256": state.sha256,
        "harvest": str(harvest_root),
        "subset": subset,
        "counts": result.counts(),
        "precheck_sha256": ST.file_sha256(run / PRECHECK),
    }
    (run / PRECHECK_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def pictures_for(run: Path) -> V.Pictures:
    return V.Pictures(Images(), commons_for(run))


def cmd_export_check(run: Path, handoff: Path, population: str) -> dict[str, Any]:
    state = ST.load_read(run / READ)
    return V.export_check(
        run,
        handoff,
        state,
        load_prechecks(run / PRECHECK),
        pictures_for(run),
        population=population,
    )


def cmd_export_replace(run: Path, handoff: Path, harvest_root: Path) -> dict[str, Any]:
    state = ST.load_read(run / READ)
    summary = json.loads((run / PRECHECK_SUMMARY).read_text(encoding="utf-8"))
    same_harvest = Path(summary["harvest"]).resolve() == harvest_root.resolve()
    if summary["read_sha256"] != state.sha256 or not same_harvest:
        raise ST.StateError("the pre-check was run on another read or another harvest")
    return V.export_replace(
        run,
        handoff,
        state,
        load_prechecks(run / PRECHECK),
        load_harvest(harvest_root),
        pictures_for(run),
    )


def cmd_accept(run: Path, chunk: Path) -> int:
    result = PL.accept(run, chunk)
    _print(result)
    return 0 if not result["deviations"] else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands: dict[str, argparse.ArgumentParser] = {}
    for name, helps in (
        ("read", "read production (read-only) into READ.json"),
        ("precheck", "the P18/P373 pre-check against WD1's harvest"),
        ("export-check", "the served images into a new handoff, 12 per batch"),
        ("export-replace", "every image the check did not call depicts, with its candidates"),
        ("brief", "the instruction of one batch's Opus agent"),
        ("check-answer", "the shape of one answer text, before it is recorded"),
        ("import-check", "parse every check answer into CHECK.jsonl"),
        ("import-replace", "parse every replacement answer into REPLACE.jsonl"),
        ("plan", "the decisions as chunks of the shared image writer"),
        ("accept", "read-only: a written chunk's sites serve what the plan says"),
    ):
        commands[name] = sub.add_parser(name, help=helps)
        commands[name].add_argument("--run-dir", required=True, type=Path)
    for name in ("precheck", "export-replace"):
        commands[name].add_argument("--harvest", type=Path, default=DEFAULT_HARVEST)
    commands["precheck"].add_argument(
        "--subset",
        action="store_true",
        help="a measured sample: the harvest's sites are the population",
    )
    for name in ("export-check", "export-replace", "brief", "check-answer"):
        commands[name].add_argument("--handoff", required=True, type=Path)
    commands["export-check"].add_argument(
        "--population",
        choices=V.POPULATIONS,
        default=V.ALL,
        help="all (default): every served image; unconfirmed: only what the pre-check could not "
        "confirm - measured unsafe, see the module docstring of vision.py",
    )
    for name in ("brief", "check-answer"):
        commands[name].add_argument("--batch-id", required=True)
    commands["check-answer"].add_argument("--label", required=True)
    commands["check-answer"].add_argument("--text-file", required=True, type=Path)
    commands["accept"].add_argument("--chunk", required=True, type=Path)
    args = parser.parse_args(argv)
    run = args.run_dir
    try:
        if args.command == "read":
            _print(cmd_read(run))
        elif args.command == "precheck":
            _print(cmd_precheck(run, args.harvest, args.subset))
        elif args.command == "export-check":
            _print(cmd_export_check(run, args.handoff, args.population))
        elif args.command == "export-replace":
            _print(cmd_export_replace(run, args.handoff, args.harvest))
        elif args.command == "brief":
            print(V.brief(run, args.handoff, args.batch_id))
        elif args.command == "check-answer":
            text = args.text_file.read_bytes().decode("utf-8")
            problem = V.check_answer(run, args.handoff, args.batch_id, args.label, text)
            _print({"ok": problem is None, "problem": problem})
            return 0 if problem is None else 1
        elif args.command == "import-check":
            _print(V.import_stage(run, V.STAGE_CHECK))
        elif args.command == "import-replace":
            _print(V.import_stage(run, V.STAGE_REPLACE))
        elif args.command == "plan":
            _print(PL.write_plan(run))
        else:
            return cmd_accept(run, args.chunk)
    except (ST.StateError, OH.HandoffError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
