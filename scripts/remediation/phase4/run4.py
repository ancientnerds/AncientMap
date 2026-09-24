"""The Phase-4 CLI: one subcommand per stage, each printing its own `STAGE_EXIT=` line.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, pipeline
"DRIVER" (`plan|sources|routes|select|assemble|verify|review|writeplan`). Work item WB-B4.

    run4.py plan      ...                         S0, forwarded to `plan4.main` (Track A)
    run4.py prepare   --batch-id p4-0001          copy the batch's plan line to its input.json
    run4.py sources   --batch-id p4-0001 --live   S1  `sources_stage.sources_batch` (Track A)
    run4.py routes    --batch-id p4-0001 --live   S1b `route_stage.routes_batch` (Track A)
    run4.py select    --batch-id p4-0001 --handoff-export|--handoff-import DIR   S3, S3R
    run4.py translate --batch-id p4-0001 --handoff-export|--handoff-import DIR   S3T
    run4.py assemble  --batch-id p4-0001          S4 (this track)
    run4.py verify    --batch-id p4-0001          S5  `verify4.verify_batch` (Track C)
    run4.py review    --batch-id p4-0001 --handoff-export|--handoff-import DIR   S6, re-verifying
    run4.py writeplan ...                         S7, forwarded to `write4.main` (Track D)
    run4.py holds                                 HOLDS4.jsonl: every batch's holds, once each

Every command reconfigures stdout and stderr to UTF-8 (page text and site names are not cp1252),
prints one JSON report (`indent=1`, so `mass_run.report_error` can read its top-level `error`) and
then `STAGE_EXIT=<n>`, and exits with `n`. The line is what the mass driver reads. A command that
dies before printing it has not finished, whatever its exit code says.

Nothing is bought without `--live`: `sources` and `routes` then only say what they would do.

**The model calls are answered through the Opus handoff** (owner order 2026-09-23: "no DeepSeek any
more - everything with Opus"; `scripts/remediation/opus_handoff.py`). `select`, `translate` and
`review` each run one round: `--handoff-export DIR` hands the stage's questions to DIR (the stage
itself runs, unchanged, over a scratch copy of the batch directory with a recording runner, so the
exported prompts are the import's by construction and nothing it writes survives), and - once Opus
agents answered and `opus_handoff.py validate --dir DIR` is clean - `--handoff-import DIR` runs the
stage on those answers. Without either, the command only says what it would ask. `translate` is its
own command because its questions are built from the selector's answers: S3 and S3R are one round,
S3T the next.

The other tracks' modules are imported when their command runs (`importlib`), so this driver loads
without them; a missing one fails loudly at that command.
"""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import run as R3  # noqa: E402
from phase3.run import InputError, read_jsonl  # noqa: E402

from phase4 import assemble as A  # noqa: E402
from phase4 import batch4 as B  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import restricted_stage as RS  # noqa: E402
from phase4 import review4 as RV  # noqa: E402
from phase4 import select_stage as SEL  # noqa: E402
from phase4 import translate_stage as TS  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
RUNNER_ROOT = REPO / "output" / "remediation" / "phase4_runner"
DEFAULT_PLAN = RUNNER_ROOT / "PLAN4.jsonl"
DEFAULT_LEDGER = RUNNER_ROOT / "LEDGER.jsonl"
HOLDS4_FILE = "HOLDS4.jsonl"
STAGE_EXIT = "STAGE_EXIT="
#: The plan's batch prefix (contracts, section 4: `assign_batches(prefix="p4")`).
BATCH_PREFIX = "p4-"
DEFAULT_FETCH_TIMEOUT = 40.0

Report = dict[str, Any]

#: The other tracks' modules, by the contract's names (docs/procedures/PHASE4_CONTRACTS.md).
PLAN4 = "phase4.plan4"
SOURCES_STAGE = "phase4.sources_stage"
ROUTE_STAGE = "phase4.route_stage"
VERIFY4 = "phase4.verify4"
WRITE4 = "phase4.write4"
#: The run-level commands another track owns: `run4 <command> <args>` is `<module>.main(<args>)`.
FORWARDED = {"plan": PLAN4, "writeplan": WRITE4}


def utf8_streams() -> None:
    """Every tool's first act (design, DRIVER): cp1252 must not kill a wave on a site name."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


def track(module: str) -> ModuleType:
    """Another track's module, imported when its command runs."""
    return importlib.import_module(module)


def batch_dir_of(args: argparse.Namespace) -> Path:
    batch_id = args.batch_id
    if not batch_id.startswith(BATCH_PREFIX):
        raise InputError(f"{batch_id!r} is not a Phase-4 batch ({BATCH_PREFIX}NNNN)")
    path = Path(args.run_dir) / batch_id
    if not (path / M.INPUT_FILE).exists():
        raise InputError(f"{path}: no input.json; run `run4.py prepare` first")
    return path


#: A model stage as the handoff runs it: `(batch_dir, ledger, runner) -> exit code`.
ModelStage = Callable[[Path, Path, MS.ModelRunner], int]


def handed_off(
    batch_dir: Path, stages: Sequence[tuple[str, ModelStage]], directory: Path
) -> dict[str, Any]:
    """Export: the calls `stages` would make, their exact prompts handed to `directory`.

    The stages run for real and unchanged, one after the other, over a scratch copy of the batch
    directory - under its own run and batch names, which the stages read - with a scratch ledger and
    a `RecordingRunner` that answers every call with a text no stage's parser accepts. Every call is
    therefore captured with the prompt the import will send (an answer already on disk is reused and
    never recorded, as the import will reuse it), and nothing the stages write - holds, selections,
    answers, reports, ledger lines - survives the export.
    """
    recorder = MS.RecordingRunner()
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / B.run_name(batch_dir) / batch_dir.name
        shutil.copytree(batch_dir, copy)
        ledger = Path(scratch) / "LEDGER.jsonl"
        for name, stage in stages:
            if stage(copy, ledger, recorder) != 0:
                raise InputError(f"{batch_dir.name}: the export's run of {name} did not complete")
    counts = MS.export_calls(recorder.calls, directory=directory)
    return {
        "batch_id": batch_dir.name,
        "handoff_export": str(directory),
        "stages": [name for name, _ in stages],
        "calls": len(recorder.calls),
        "labels": [call.label for call in recorder.calls],
        **counts,
    }


def run_on_answers(
    batch_dir: Path, stages: Sequence[tuple[str, ModelStage, str]], *, ledger: Path, directory: Path
) -> tuple[int, Report]:
    """Import: `stages` on the Opus answers in `directory`; the first that cannot complete stops."""
    runner = MS.HandoffRunner(directory=directory)
    for name, stage, report in stages:
        code = stage(batch_dir, ledger, runner)
        if code != 0:
            return code, {
                "batch_id": batch_dir.name,
                "stage": name,
                "error": _stage_error(batch_dir, report),
            }
    return 0, {
        "batch_id": batch_dir.name,
        "handoff_import": str(directory),
        "stages": [name for name, _, _ in stages],
    }


# -------------------------------------------------------------------------------- the commands


def cmd_forward(module: str) -> Callable[[argparse.Namespace], tuple[int, Report]]:
    """`plan` and `writeplan` belong to Tracks A and D: their own `main(argv)` does the work and
    prints its own report; this driver adds only its exit line."""

    def command(args: argparse.Namespace) -> tuple[int, Report]:
        code = int(track(module).main(list(args.rest)))
        return code, {"command": args.command, "forwarded_to": module, "exit": code}

    return command


def plan_line_sites(row: Mapping[str, Any], where: str) -> list[M.PlanSite]:
    """The sites of one `PLAN4.jsonl` line, each read as a `PlanSite`; a line without a non-empty
    `sites` list is refused (`where` names the line). `prepare` and `mass4.read_plan4` read a line
    with this, before anything is written."""
    sites = row.get("sites")
    if not isinstance(sites, list) or not sites:
        raise InputError(f"{where}: {row.get('batch_id')!r} carries no sites")
    return [M.PlanSite.from_dict(site) for site in sites]


def cmd_prepare(args: argparse.Namespace) -> tuple[int, Report]:
    """Copy one plan line to `<run>/<batch>/input.json`, write-once, after reading every site."""
    plan = Path(args.plan)
    lines = [row for row in read_jsonl(plan) if row.get("batch_id") == args.batch_id]
    if len(lines) != 1:
        raise InputError(f"{plan}: {len(lines)} lines for {args.batch_id}, not one")
    batch = lines[0]
    plan_line_sites(batch, f"{plan} ({args.batch_id})")
    target = Path(args.run_dir) / args.batch_id / M.INPUT_FILE
    body = json.dumps(batch, ensure_ascii=False, sort_keys=True) + "\n"
    wrote = F.write_once(target, body.encode("utf-8"), source=f"{plan} ({args.batch_id})")
    B.read_batch(target.parent)
    return 0, {"batch_id": args.batch_id, "input": str(target), "wrote": wrote}


def cmd_sources(args: argparse.Namespace) -> tuple[int, Report]:
    """S1 through Track A's own live fetcher (`sources_stage.open_fetcher`: the 1 MiB client for
    the wiki hosts, the 60 KB one for every other, paced per host), reusing the Phase-3 mass run's
    `wikidata_entity` files."""
    batch_dir = batch_dir_of(args)
    if not args.live:
        return 0, {"batch_id": args.batch_id, "live": False, "bought": 0}
    sources = track(SOURCES_STAGE)
    with sources.open_fetcher(pacing_dir=Path(args.pacing_dir), timeout=args.timeout) as fetcher:
        code = sources.sources_batch(
            batch_dir,
            ledger=Path(args.ledger),
            fetcher=fetcher,
            now=datetime.now(UTC),
            phase3_run=Path(args.phase3_run),
        )
    return int(code), {"batch_id": args.batch_id, "live": True}


def cmd_routes(args: argparse.Namespace) -> tuple[int, Report]:
    """S1b through the same live fetcher and Track A's three search seams
    (`route_stage.open_search`: the searcher, the forced quota probe, the MiniMax host's pace).

    A run told `--max-searches 0` may send no search, so it opens no MiniMax client at all: it is
    handed `route_stage.no_search`, whose seams refuse (owner order 2026-09-23, "everything with
    Opus": the Phase-4 pilot sends no search, and its sites that need one are held
    `search-stopped`)."""
    batch_dir = batch_dir_of(args)
    if not args.live:
        return 0, {"batch_id": args.batch_id, "live": False, "bought": 0}
    sources = track(SOURCES_STAGE)
    routes = track(ROUTE_STAGE)
    pacing_dir = Path(args.pacing_dir)
    seams = (
        routes.no_search() if args.max_searches == 0 else routes.open_search(pacing_dir=pacing_dir)
    )
    with (
        sources.open_fetcher(pacing_dir=pacing_dir, timeout=args.timeout) as fetcher,
        seams as (searcher, probe, wait),
    ):
        code = routes.routes_batch(
            batch_dir,
            ledger=Path(args.ledger),
            fetcher=fetcher,
            searcher=searcher,
            max_searches=args.max_searches,
            now=datetime.now(UTC),
            probe=probe,
            wait=wait,
        )
    return int(code), {"batch_id": args.batch_id, "live": True, "max_searches": args.max_searches}


def _stage_error(batch_dir: Path, name: str) -> str | None:
    """The `error` a Track-B stage wrote into its report (`None` when it finished)."""
    report = json.loads((batch_dir / name).read_text(encoding="utf-8"))
    error = report.get("error")
    return error if isinstance(error, str) else None


def _select(batch_dir: Path, ledger: Path, runner: MS.ModelRunner) -> int:
    return SEL.select_batch(batch_dir, ledger=ledger, runner=runner)


def _restricted(batch_dir: Path, ledger: Path, runner: MS.ModelRunner) -> int:
    return RS.restricted_batch(batch_dir, ledger=ledger, runner=runner)


def _translate(batch_dir: Path, ledger: Path, runner: MS.ModelRunner) -> int:
    return TS.translate_batch(batch_dir, ledger=ledger, runner=runner)


def cmd_select(args: argparse.Namespace) -> tuple[int, Report]:
    """S3 for lanes W, S and T, then S3R for lane R: one handoff round, neither needs an answer."""
    batch_dir = batch_dir_of(args)
    stages = (
        ("select", _select, B.SELECT_REPORT),
        ("restricted", _restricted, B.RESTRICTED_REPORT),
    )
    if args.handoff_export:
        exported = [(name, stage) for name, stage, _ in stages]
        return 0, handed_off(batch_dir, exported, Path(args.handoff_export))
    if not args.handoff_import:
        return 0, preview_select(batch_dir)
    return run_on_answers(
        batch_dir, stages, ledger=Path(args.ledger), directory=Path(args.handoff_import)
    )


def cmd_translate(args: argparse.Namespace) -> tuple[int, Report]:
    """S3T for lane T: its own round, because its questions are built from the selector's answers."""
    batch_dir = batch_dir_of(args)
    if args.handoff_export:
        return 0, handed_off(batch_dir, [("translate", _translate)], Path(args.handoff_export))
    if not args.handoff_import:
        return 0, {"batch_id": args.batch_id, "live": False, "bought": 0}
    return run_on_answers(
        batch_dir,
        [("translate", _translate, B.TRANSLATE_REPORT)],
        ledger=Path(args.ledger),
        directory=Path(args.handoff_import),
    )


def preview_select(batch_dir: Path) -> Report:
    """What `select` would ask: the prompt size of every selecting site. Hands nothing off."""
    _, sites = B.read_batch(batch_dir)
    lanes = B.read_lanes(batch_dir, sites)
    held = B.site_held(B.read_holds(batch_dir))
    rows = []
    for site in sites:
        lane = lanes[site.site_id]
        if lane.lane not in SEL.SELECTING_LANES or site.site_id in held:
            continue
        source_id, meta, text, pool = SEL.site_pool(batch_dir, site, lane)
        prompt = SEL.site_selector_prompt(batch_dir, site, source_id, meta, pool, text).render()
        rows.append({"site_id": site.site_id, "pool": len(pool), "prompt_chars": len(prompt)})
    return {"batch_id": batch_dir.name, "live": False, "sites": rows}


def cmd_assemble(args: argparse.Namespace) -> tuple[int, Report]:
    batch_dir = batch_dir_of(args)
    code = A.assemble_batch(batch_dir)
    return code, {"batch_id": args.batch_id, "assembly": str(batch_dir / M.ASSEMBLY_FILE)}


def cmd_verify(args: argparse.Namespace) -> tuple[int, Report]:
    batch_dir = batch_dir_of(args)
    code = int(track(VERIFY4).verify_batch(batch_dir))
    return code, {"batch_id": args.batch_id}


def reverify_for(batch_dir: Path) -> RV.Reverify:
    """`verify4.verify_site` bound to this batch's evidence (the review's S5 again).

    `metas` are the raw `src.<id>.meta` objects, `texts` the pinned texts, `quotes` the store slice
    of every published sentence (`assemble.quotes_of`), and `new_raw_data` the writer's
    `write4.new_raw_data(old, assembly)` - the contract's own wiring.
    """
    verify4 = track(VERIFY4)
    write4 = track(WRITE4)

    def reverify(site: M.PlanSite, assembly: M.Assembly) -> tuple[M.Hold, ...]:
        ids = [source.id for source in assembly.provenance.sources]
        metas: Mapping[str, Mapping[str, Any]] = {
            source_id: B.read_meta(batch_dir, site.site_id, source_id) for source_id in ids
        }
        texts = {
            source_id: B.read_source(batch_dir, site.site_id, source_id)[1] for source_id in ids
        }
        return tuple(
            verify4.verify_site(
                site,
                assembly,
                metas=metas,
                texts=texts,
                quotes=A.quotes_of(assembly, texts),
                new_raw_data=write4.new_raw_data(site.raw_data, assembly),
            )
        )

    return reverify


def _review(batch_dir: Path, ledger: Path, runner: MS.ModelRunner) -> int:
    """S6 with the review's S5 bound to the directory it runs in (the scratch copy, on export)."""
    return RV.review_batch(
        batch_dir, ledger=ledger, runner=runner, reverify=reverify_for(batch_dir)
    )


def cmd_review(args: argparse.Namespace) -> tuple[int, Report]:
    batch_dir = batch_dir_of(args)
    if args.handoff_export:
        return 0, handed_off(batch_dir, [("review", _review)], Path(args.handoff_export))
    if not args.handoff_import:
        return 0, {"batch_id": args.batch_id, "live": False, "bought": 0}
    code = _review(
        batch_dir,
        Path(args.ledger),
        MS.HandoffRunner(directory=Path(args.handoff_import)),
    )
    report: Report = {"batch_id": args.batch_id, "handoff_import": args.handoff_import}
    if code != 0:
        report["error"] = _stage_error(batch_dir, B.REVIEW_REPORT)
    return code, report


def aggregate_holds(run_dir: Path) -> list[M.Hold]:
    """Every batch's holds, in batch order, each distinct line once: `HOLDS4.jsonl`.

    A site counts in its latest batch only: `mass4` re-queues a site held `revision-too-fresh` into
    a later batch (`REQUEUE4.jsonl`), and the holds of the batch it left are no longer its state.
    """
    batch_dirs = sorted(p for p in run_dir.iterdir() if p.is_dir())
    sites_of = {path.name: {site.site_id for site in B.read_batch(path)[1]} for path in batch_dirs}
    latest = {site_id: name for name, site_ids in sites_of.items() for site_id in site_ids}
    seen: set[str] = set()
    out: list[M.Hold] = []
    for batch_dir in batch_dirs:
        for hold in B.read_holds(batch_dir):
            if hold.site_id not in sites_of[batch_dir.name]:
                raise InputError(f"{batch_dir}: a hold for {hold.site_id}, not a site of the batch")
            line = hold.to_json()
            if latest[hold.site_id] == batch_dir.name and line not in seen:
                seen.add(line)
                out.append(hold)
    return out


def cmd_holds(args: argparse.Namespace) -> tuple[int, Report]:
    run_dir = Path(args.run_dir)
    holds = aggregate_holds(run_dir)
    B.write_text_atomic(run_dir / HOLDS4_FILE, M.dump_jsonl(holds))
    by_reason: dict[str, int] = {}
    for hold in holds:
        by_reason[hold.reason.value] = by_reason.get(hold.reason.value, 0) + 1
    return 0, {"holds": len(holds), "by_reason": by_reason, "out": str(run_dir / HOLDS4_FILE)}


# ---------------------------------------------------------------------------------- the parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phase4-run", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    for name, module in FORWARDED.items():
        # Every argument after the command name is the owning module's own (`main` collects them).
        sub.add_parser(name, help=f"forwarded to {module}.main").set_defaults(
            func=cmd_forward(module)
        )

    def batch_command(name: str, func: Callable[..., tuple[int, Report]], *, live: bool) -> Any:
        command = sub.add_parser(name)
        command.add_argument("--run-dir", required=True)
        command.add_argument("--batch-id", required=True)
        command.add_argument("--ledger", default=str(DEFAULT_LEDGER))
        if live:
            command.add_argument("--live", action="store_true", help="buy; without it, only say")
        command.set_defaults(func=func)
        return command

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--run-dir", required=True)
    prepare.add_argument("--batch-id", required=True)
    prepare.add_argument("--plan", default=str(DEFAULT_PLAN))
    prepare.set_defaults(func=cmd_prepare)

    for name, func in (("sources", cmd_sources), ("routes", cmd_routes)):
        command = batch_command(name, func, live=True)
        command.add_argument("--pacing-dir", default=str(R3.DEFAULT_PACING_DIR))
        command.add_argument("--timeout", type=float, default=DEFAULT_FETCH_TIMEOUT)
        if name == "sources":
            command.add_argument(
                "--phase3-run",
                default=str(R3.DEFAULT_SOURCE_RUN_DIR),
                help="the Phase-3 mass run whose wikidata_entity files S1 reuses",
            )
        if name == "routes":
            command.add_argument("--max-searches", type=int, required=True)
    for name, func in (
        ("select", cmd_select),
        ("translate", cmd_translate),
        ("review", cmd_review),
    ):
        # The model stages buy nothing themselves: one handoff half, or a preview (`opus_handoff`).
        half = batch_command(name, func, live=False).add_mutually_exclusive_group()
        half.add_argument("--handoff-export", metavar="DIR", default=None)
        half.add_argument("--handoff-import", metavar="DIR", default=None)
    batch_command("assemble", cmd_assemble, live=False)
    batch_command("verify", cmd_verify, live=False)

    holds = sub.add_parser("holds")
    holds.add_argument("--run-dir", required=True)
    holds.set_defaults(func=cmd_holds)
    return parser


def main(argv: list[str] | None = None) -> int:
    utf8_streams()
    parser = build_parser()
    args, rest = parser.parse_known_args(argv)
    if args.command in FORWARDED:
        args.rest = rest
    elif rest:
        parser.error(f"unrecognized arguments: {' '.join(rest)}")
    code, report = args.func(args)
    print(
        json.dumps(
            {"command": args.command, **report}, ensure_ascii=False, indent=1, sort_keys=True
        )
    )
    print(f"{STAGE_EXIT}{code}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
