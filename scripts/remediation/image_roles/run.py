"""The command line of the picture research (D17) and of the Claude image roles.

The steps, in order, for one candidate run directory `C` (`flow.py` explains each file):

    run.py population      --run-dir C [--sites FILE]            production read-only -> C/POPULATION.jsonl
    run.py fetch-entities  --run-dir C                           Wikidata -> the delta (items nobody holds)
    run.py identity-export --run-dir C --handoff H --mode verify|research [--found-nothing FILE]
    run.py brief | check-answer | import  --run-dir C --handoff H --stage identity-verify|identity-research
    run.py identity-apply  --run-dir C [--stage identity-verify ...]  -> C/POPULATION_2.jsonl
    run.py search          --run-dir C [--judged V ...] [--workers 2]  -> C/CANDIDATES.jsonl
    run.py pictures        --run-dir C                           renderings on disk -> C/PICTURES.jsonl
    run.py prefilter-export --run-dir C --handoff H              Haiku, 640 px, 60 to a question
    run.py brief | check-answer | import  ... --stage image-prefilter
    run.py depicts-export  --run-dir C --handoff H               Sonnet, 1280 px, by site
    run.py brief | check-answer | import  ... --stage image-depicts   (writes C/VERDICTS.jsonl)
    run.py recheck-export  --run-dir C --handoff H               Opus, round N (the next one)
    run.py brief | check-answer | import  ... --stage image-recheck [--round N]
    run.py write-targets   --run-dir C                           -> C/TARGETS.jsonl (confirmed picks)
    run.py prune-pictures  --run-dir C                           delete the pictures, keep their hashes

The MiniMax pool (D10, C4), with `C` the population's run directory and `OLD` the 2026-10-06 run:

    run.py pool            --run-dir C --old-run OLD             -> C/PICTURES.jsonl (pictures on disk)
    run.py pool-picks      --run-dir C --old-run OLD --out FILE  the old targets as picks
    run.py recheck-export  --run-dir C --handoff H --picks FILE  Opus re-checks the old targets
    run.py denied          --run-dir C --old-run OLD --served-run S
                                       the heroes MiniMax put on a page and Claude does not confirm
                                       -> S/OTHER_SITE_HEROES.jsonl, S/SITES.txt (served_image recheck)

`brief` prints one batch's agent instruction; `check-answer` checks an answer's shape; `import`
parses every answer into the stage's result file. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import research_web  # noqa: E402
import roles as RO  # noqa: E402
from candidate_search import judge_run as JR  # noqa: E402
from candidate_search import population as PP  # noqa: E402
from gallery_audit import persist_verdicts as pv  # noqa: E402
from identity import common as IC  # noqa: E402
from identity import entities as IE  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from phase3.run import InputError  # noqa: E402
from served_image import commons as CM  # noqa: E402
from served_image import recheck as RC  # noqa: E402
from served_image import state as ST  # noqa: E402

from image_roles import depicts as DP  # noqa: E402
from image_roles import flow as FL  # noqa: E402
from image_roles import hero_recheck as HR  # noqa: E402
from image_roles import identity as ID  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402
from image_roles.wiki_cache import WikiCache  # noqa: E402

STAGES = {
    ID.VERIFY_SPEC.name: ID.VERIFY_SPEC,
    ID.RESEARCH_SPEC.name: ID.RESEARCH_SPEC,
    PF.SPEC.name: PF.SPEC,
    DP.SPEC.name: DP.SPEC,
    HR.SPEC.name: HR.SPEC,
}
DEFAULT_WIKI_CACHE = IC.REPO / "output" / "remediation" / "final-2026-10-08" / "wiki_cache"


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def _spec(args: argparse.Namespace) -> SG.Spec:
    spec = STAGES[args.stage]
    return HR.spec_for_round(args.round) if args.stage == HR.SPEC.name and args.round else spec


def _entities(args: argparse.Namespace) -> IE.EntityStore:
    main = IC.main_checkout()
    return IE.EntityStore(
        args.harvest or IC.harvest_dir(main), args.delta or IE.delta_dir(IC.run_dir(main))
    )


def _cache(path: Path | None) -> WikiCache:
    return WikiCache(path or DEFAULT_WIKI_CACHE)


def _commons(run: Path) -> CM.Commons:
    return CM.Commons(run / "commons", research_web.client(), pace=CM.PACE_SECONDS)


def cmd_population(run: Path, sites: Path | None) -> dict[str, Any]:
    listed = None if sites is None else RC.read_sites(sites)
    return FL.write_population(run, pv.read_rows(PP.population_sql(listed)))


def cmd_fetch_entities(run: Path, args: argparse.Namespace) -> dict[str, Any]:
    qids = [s["qid"] for s in FL._population(run) if s.get("qid")]
    main = IC.main_checkout()
    return IE.fetch_delta(
        qids, args.harvest or IC.harvest_dir(main), args.delta or IE.delta_dir(IC.run_dir(main))
    )


def cmd_identity_export(run: Path, args: argparse.Namespace) -> dict[str, Any]:
    found = []
    if args.found_nothing:
        found = [r["site_id"] for r in FL._jsonl(args.found_nothing)]
    return FL.identity_export(
        run,
        args.handoff,
        args.mode,
        entities=_entities(args),
        cache=_cache(args.wiki_cache),
        found_nothing=found,
    )


def cmd_identity_apply(run: Path, stages: list[str]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for name in stages:
        results += SG.read_results(run, STAGES[name])
    return FL.identity_apply(run, results)


def cmd_search(run: Path, args: argparse.Namespace) -> dict[str, Any]:
    judged = FL.judged_not_depicts(args.judged or [])
    return FL.search(
        run,
        _commons(run),
        entities=_entities(args),
        floor=(args.min_width, args.min_height),
        workers=args.workers,
        judged=judged,
        limit=args.limit,
    )


def cmd_pictures(run: Path) -> dict[str, Any]:
    client = JR.PacedDownloads(research_web.client(), run / "commons")
    return FL.pictures(run, client)


def cmd_import(run: Path, args: argparse.Namespace) -> dict[str, Any]:
    spec = _spec(args)
    if spec.name == DP.SPEC.name:
        return FL.depicts_import(run, args.handoff)
    return SG.import_answers(run, args.handoff, spec)


def cmd_recheck_export(run: Path, args: argparse.Namespace) -> dict[str, Any]:
    picks = None if args.picks is None else FL._jsonl(args.picks)
    return FL.recheck_export(run, args.handoff, cache=_cache(args.wiki_cache), picks=picks)


def cmd_denied(run: Path, args: argparse.Namespace) -> dict[str, Any]:
    state = ST.load_read(args.served_run / "READ.json")
    heroes = FL.denied(run, args.old_run, state)
    return RC.write_derivation(args.served_run, heroes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands: dict[str, argparse.ArgumentParser] = {}
    for name in (
        "population",
        "fetch-entities",
        "identity-export",
        "identity-apply",
        "search",
        "pictures",
        "prefilter-export",
        "depicts-export",
        "recheck-export",
        "brief",
        "check-answer",
        "import",
        "write-targets",
        "prune-pictures",
        "pool",
        "pool-picks",
        "denied",
    ):
        commands[name] = sub.add_parser(name)
        commands[name].add_argument("--run-dir", required=True, type=Path)
    for name in ("fetch-entities", "identity-export", "search"):
        commands[name].add_argument("--harvest", type=Path, default=None)
        commands[name].add_argument("--delta", type=Path, default=None)
    commands["population"].add_argument("--sites", type=Path, default=None)
    commands["identity-export"].add_argument(
        "--mode", required=True, choices=("verify", "research")
    )
    commands["identity-export"].add_argument("--found-nothing", type=Path, default=None)
    commands["identity-apply"].add_argument(
        "--stage",
        action="append",
        choices=(ID.VERIFY_SPEC.name, ID.RESEARCH_SPEC.name),
        help="an identity stage whose answers are applied (repeat it)",
    )
    commands["search"].add_argument("--judged", type=Path, nargs="*", default=None)
    commands["search"].add_argument("--min-width", type=int, default=IH.OWNER_FLOOR_WIDTH)
    commands["search"].add_argument("--min-height", type=int, default=IH.OWNER_FLOOR_HEIGHT)
    commands["search"].add_argument("--workers", type=int, default=1)
    commands["search"].add_argument("--limit", type=int, default=None)
    commands["prefilter-export"].add_argument("--limit", type=int, default=None)
    commands["recheck-export"].add_argument("--picks", type=Path, default=None)
    for name in (
        "identity-export",
        "prefilter-export",
        "depicts-export",
        "recheck-export",
        "brief",
        "check-answer",
        "import",
    ):
        commands[name].add_argument("--handoff", required=True, type=Path)
    for name in ("identity-export", "depicts-export", "recheck-export"):
        commands[name].add_argument("--wiki-cache", type=Path, default=None)
    for name in ("brief", "check-answer", "import"):
        commands[name].add_argument("--stage", required=True, choices=sorted(STAGES))
        commands[name].add_argument("--round", type=int, default=None)
    for name in ("brief", "check-answer"):
        commands[name].add_argument("--batch-id", required=True)
    commands["check-answer"].add_argument("--label", required=True)
    commands["check-answer"].add_argument("--text-file", required=True, type=Path)
    for name in ("pool", "pool-picks", "denied"):
        commands[name].add_argument("--old-run", required=True, type=Path)
    commands["pool-picks"].add_argument("--out", required=True, type=Path)
    commands["denied"].add_argument("--served-run", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    args = build_parser().parse_args(argv)
    run, command = args.run_dir, args.command
    try:
        if command == "population":
            _print(cmd_population(run, args.sites))
        elif command == "fetch-entities":
            _print(cmd_fetch_entities(run, args))
        elif command == "identity-export":
            _print(cmd_identity_export(run, args))
        elif command == "identity-apply":
            if not args.stage:
                raise SG.StageError("name at least one --stage whose answers are applied")
            _print(cmd_identity_apply(run, args.stage))
        elif command == "search":
            _print(cmd_search(run, args))
        elif command == "pictures":
            _print(cmd_pictures(run))
        elif command == "prefilter-export":
            _print(FL.prefilter_export(run, args.handoff, limit=args.limit))
        elif command == "depicts-export":
            _print(FL.depicts_export(run, args.handoff, cache=_cache(args.wiki_cache)))
        elif command == "recheck-export":
            _print(cmd_recheck_export(run, args))
        elif command == "brief":
            print(SG.brief(run, args.handoff, _spec(args), args.batch_id))
        elif command == "check-answer":
            text = args.text_file.read_bytes().decode("utf-8")
            problem = SG.check_answer(
                run, args.handoff, _spec(args), args.batch_id, args.label, text
            )
            _print({"ok": problem is None, "problem": problem})
            return 0 if problem is None else 1
        elif command == "import":
            _print(cmd_import(run, args))
        elif command == "write-targets":
            _print(FL.write_targets(run))
        elif command == "prune-pictures":
            _print(FL.prune_pictures(run))
        elif command == "pool":
            _print(FL.pool(run, args.old_run))
        elif command == "pool-picks":
            picks = FL.pool_picks(run, args.old_run)
            ST.write_text_once(args.out, ST.jsonl_text(picks))
            _print({"picks": len(picks), "file": str(args.out)})
        else:
            _print(cmd_denied(run, args))
    except (ST.StateError, RO.RoleError, InputError, FileNotFoundError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
