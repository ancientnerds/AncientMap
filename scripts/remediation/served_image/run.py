"""The served-image lane's command line (WD2, O6). The runbook, with every gate and the undo, is
`docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md`; in order:

    run.py read           --run-dir R          production (read-only) -> R/READ.json
    run.py precheck       --run-dir R [--harvest H] [--subset | --sites FILE]
                                               P18/P373 against WD1's harvest -> R/PRECHECK.jsonl
                                               (written once: a new harvest is a new run dir;
                                               --sites: only the sites named, one id per line)
    run.py export-check   --run-dir R --handoff H-check [--population all|unconfirmed|recheck]
                                               [--sites FILE]
                                               every served image (default), 12 per batch;
                                               --sites: only those; recheck (D15): the richer
                                               prompt, needs --sites and R/CONTEXT.jsonl
    run.py brief          --run-dir R --handoff H-check --batch-id B [--role ROLE]
    run.py check-answer   --run-dir R --handoff H-check --batch-id B --label L --text-file F
    opus_handoff.py validate --dir H-check
    run.py import-check   --run-dir R [--role ROLE]
                                               -> R/CHECK.jsonl (--role: every answer must have
                                               been given in that role, D6)
    run.py export-replace --run-dir R --handoff H-replace [--claimed-only] [--sites FILE]
                                               every served image that does not depict its site
                                               (--claimed-only: only the sites that serve no image
                                               while their item claims a file - for a run that
                                               does not re-judge the served images; refused
                                               while a judged image failed)
    (brief, check-answer, validate as above)
    run.py import-replace --run-dir R          -> R/REPLACE.jsonl (only when export-replace
                                               reported questions > 0)
    run.py plan           --run-dir R          -> R/chunks/chunk-NNN (<= 100 sites each)
    chunk_writer.py R/chunks/chunk-NNN --check | --rehearse | --apply | --readback |
                                        --rehearse-rollback
    run.py accept         --run-dir R --chunk R/chunks/chunk-NNN
                                               read-only: every site of the chunk serves what the
                                               plan says; exit 0 only with 0 deviations
    run.py derive-sites   --run-dir R --verdicts-run V
                                               D15: the live heroes the run V judged other_site ->
                                               R/OTHER_SITE_HEROES.jsonl, R/SITES.txt
    run.py context        --run-dir R --import GEOJSON
                                               D15: the recheck's context per hero ->
                                               R/CONTEXT.jsonl (production read-only, Wikipedia)
    run.py no-image-report --run-dir R
                                               -> R/NO_IMAGE_REPORT.jsonl, R/NO_IMAGE_SUMMARY.json:
                                               every curated site that serves no image with the
                                               reason measured for it, and the counts that close
                                               over the read. Refused while a claiming site is
                                               not covered by the replace export.
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
import roles as RO  # noqa: E402
from gallery_audit.vision import Images  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from phase3.run import InputError, read_jsonl  # noqa: E402

from served_image import no_image_report as NR  # noqa: E402
from served_image import plan as PL  # noqa: E402
from served_image import recheck as RC  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image import vision as V  # noqa: E402
from served_image.commons import Commons  # noqa: E402
from served_image.precheck import (  # noqa: E402
    DEFAULT_HARVEST,
    PRECHECK_FILE,
    PRECHECK_SUMMARY,
    load_harvest,
    load_prechecks,
    run_precheck,
    write_prechecks,
)

READ = "READ.json"


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def commons_for(run: Path) -> Commons:
    return Commons(run / "commons", research_web.client())


def cmd_read(run: Path) -> dict[str, Any]:
    data = ST.read_production()
    digest = ST.write_read(run / READ, data)
    return {"sites": len(data["sites"]), "images": len(data["images"]), "sha256": digest}


def cmd_precheck(
    run: Path, harvest_root: Path, subset: bool, sites: Path | None = None
) -> dict[str, Any]:
    state = ST.load_read(run / READ)
    named = None if sites is None else RC.read_sites(sites)
    result = run_precheck(
        state, load_harvest(harvest_root), commons_for(run), subset=subset, sites=named
    )
    summary = {
        "read_sha256": state.sha256,
        "harvest": str(harvest_root),
        "subset": subset,
        "sites": named,
        "counts": result.counts(),
        "precheck_sha256": write_prechecks(run / PRECHECK_FILE, result),
    }
    ST.write_text_once(run / PRECHECK_SUMMARY, ST.json_text(summary))
    return summary


def pictures_for(run: Path) -> V.Pictures:
    return V.Pictures(Images(), commons_for(run))


def cmd_export_check(
    run: Path, handoff: Path, population: str, sites: Path | None = None
) -> dict[str, Any]:
    state = ST.load_read(run / READ)
    return V.export_check(
        run,
        handoff,
        state,
        load_prechecks(run / PRECHECK_FILE),
        pictures_for(run),
        population=population,
        sites=None if sites is None else RC.read_sites(sites),
        context=RC.load_context(run / RC.CONTEXT_FILE) if population == V.RECHECK else None,
    )


def cmd_export_replace(
    run: Path,
    handoff: Path,
    harvest_root: Path,
    claimed_only: bool = False,
    sites: Path | None = None,
) -> dict[str, Any]:
    state = ST.load_read(run / READ)
    summary = json.loads((run / PRECHECK_SUMMARY).read_text(encoding="utf-8"))
    same_harvest = Path(summary["harvest"]).resolve() == harvest_root.resolve()
    if summary["read_sha256"] != state.sha256 or not same_harvest:
        raise ST.StateError("the pre-check was run on another read or another harvest")
    return V.export_replace(
        run,
        handoff,
        state,
        load_prechecks(run / PRECHECK_FILE),
        load_harvest(harvest_root),
        pictures_for(run),
        claimed_only=claimed_only,
        sites=None if sites is None else RC.read_sites(sites),
    )


def cmd_derive_sites(run: Path, verdicts_run: Path) -> dict[str, Any]:
    state = ST.load_read(run / READ)
    heroes = RC.other_site_heroes(
        state, read_jsonl(verdicts_run / V.CHECK), read_jsonl(verdicts_run / V.REPLACE)
    )
    return RC.write_derivation(run, heroes)


def cmd_context(run: Path, source: Path) -> dict[str, Any]:
    state = ST.load_read(run / READ)
    heroes = read_jsonl(run / RC.HEROES_FILE)
    owner_links = IH.join_import(state, IH.read_import(source))
    records = RC.build_context(
        heroes,
        ST.CW.pv.read_rows(RC.context_sql([h["site_id"] for h in heroes])),
        owner_links,
        research_web.client(),
    )
    return {"records": len(records), "sha256": RC.write_context(run, records)}


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
        ("no-image-report", "every curated site that serves no image, with its measured reason"),
        ("derive-sites", "D15: the live heroes a served-image run judged other_site"),
        ("context", "D15: the recheck's context of each of those heroes"),
    ):
        commands[name] = sub.add_parser(name, help=helps)
        commands[name].add_argument("--run-dir", required=True, type=Path)
    for name in ("precheck", "export-replace", "no-image-report"):
        commands[name].add_argument("--harvest", type=Path, default=DEFAULT_HARVEST)
    commands["precheck"].add_argument(
        "--subset",
        action="store_true",
        help="a measured sample: the harvest's sites are the population",
    )
    for name in ("precheck", "export-check", "export-replace"):
        commands[name].add_argument(
            "--sites",
            type=Path,
            default=None,
            help="a file of site ids, one per line: only these sites (D15)",
        )
    for name in ("brief", "import-check", "import-replace"):
        commands[name].add_argument(
            "--role",
            default=None,
            help="a role of roles.ROLES (D6): the agents run as its model; an import refuses "
            "an answer not given in it",
        )
    commands["derive-sites"].add_argument("--verdicts-run", required=True, type=Path)
    commands["context"].add_argument(
        "--import", dest="source", required=True, type=Path, help="the 2025 import's GeoJSON"
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
    commands["export-replace"].add_argument(
        "--claimed-only",
        action="store_true",
        help="only the sites that serve no image while their Wikidata item claims a file: for a "
        "run that does not re-judge the served images. Refused while a judged image failed",
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
            _print(cmd_precheck(run, args.harvest, args.subset, args.sites))
        elif args.command == "export-check":
            _print(cmd_export_check(run, args.handoff, args.population, args.sites))
        elif args.command == "export-replace":
            _print(
                cmd_export_replace(run, args.handoff, args.harvest, args.claimed_only, args.sites)
            )
        elif args.command == "derive-sites":
            _print(cmd_derive_sites(run, args.verdicts_run))
        elif args.command == "context":
            _print(cmd_context(run, args.source))
        elif args.command == "brief":
            print(V.brief(run, args.handoff, args.batch_id, args.role))
        elif args.command == "check-answer":
            text = args.text_file.read_bytes().decode("utf-8")
            problem = V.check_answer(run, args.handoff, args.batch_id, args.label, text)
            _print({"ok": problem is None, "problem": problem})
            return 0 if problem is None else 1
        elif args.command == "import-check":
            _print(V.import_stage(run, V.STAGE_CHECK, args.role))
        elif args.command == "import-replace":
            _print(V.import_stage(run, V.STAGE_REPLACE, args.role))
        elif args.command == "plan":
            _print(PL.write_plan(run))
        elif args.command == "no-image-report":
            _print(NR.write_report(run, args.harvest, commons_for(run)))
        else:
            return cmd_accept(run, args.chunk)
    except (ST.StateError, OH.HandoffError, FileNotFoundError, InputError, RO.RoleError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
