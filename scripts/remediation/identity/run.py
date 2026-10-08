"""The identity package's command line: D13 re-targets, D20 scope window, D23 names.

Three lanes (`--lane`), each with question stages answered by Claude agents through
`opus_handoff.py` and a write chain run through the shared writers. Everything here reads the
discovery's files (`output/remediation/final-2026-10-08/identity/`, gitignored) and writes beside them;
nothing writes to production - the writes are `mechanical/apply.py --lane ...`, the link step's
`step` command and the chunk writer, each with the gates in the order emit, check, verify, rehearse,
probe-guards, apply, read-back, rehearse-rollback.

    PY=./.venv/Scripts/python.exe; I=scripts/remediation/identity; H=scripts/remediation/opus_handoff.py

    # a question stage (--lane retarget --stage retarget-web | retarget-recheck,
    #                   --lane scope-window --stage scope-window-web | scope-window-recheck,
    #                   --lane names --stage name-clean-web | name-clean-recheck | spoken-model)
    $PY $I/run.py --lane L --stage S export --handoff DIR [--pilot N | --sites-file F]
    $PY $I/run.py --lane L --stage S brief --round r1 --batch-id r1-b01       # the agent's brief
    $PY $I/run.py --lane L --stage S check-answer --round r1 --batch-id B --label SITE --text-file F
    $PY $H validate --dir DIR                        # every question answered, in shape, by the role
    $PY $I/run.py --lane L --stage S import --round r1 --calibration ID       # needs a passed verdict
    $PY $I/run.py --lane L --stage S export-reask --handoff DIR2              # the held sites, r2/r3
    $PY $I/run.py --lane L --stage S status

    # the result and the lists the other lanes read
    $PY $I/run.py --lane retarget result            # RESULT.jsonl, RETIRE_LIST, MERGE_LIST, OWNER_LIST
    $PY $I/run.py --lane scope-window result
    $PY $I/run.py --lane names --kind clean result

    # one wave: select, plan against a read-only live read, then the lane's own gates
    $PY $I/run.py --lane retarget wave --wave W [--limit 100]
    $PY $I/run.py --lane retarget plan-links --wave W        # the link step (links + source_url)
    $PY $I/run.py --lane retarget step check|rehearse|probe-guards|apply|verify|rehearse-rollback --wave W
    $PY $I/run.py --lane retarget plan-names --wave W        # after the link step landed
    $PY scripts/remediation/mechanical/apply.py --lane retarget-name-W --emit ...   # the name lane
    $PY scripts/remediation/gallery_audit/chunk_writer.py DIR/alias/chunk-001 --check ...  # the alias
    $PY $I/run.py --lane retarget verify --wave W            # read-only: plan = data, 0 deviations
    $PY $I/run.py --lane retarget chain-done --wave W --stage links --stamp STAMP
    $PY $I/run.py --lane retarget handoffs --wave W          # the lists for wd5, W/WN, images, card
    $PY $I/run.py --lane scope-window wave|plan|verify --wave W       # apply.py --lane scope-window-W
    $PY $I/run.py --lane names --kind clean|spoken wave|plan|verify --wave W
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(_HERE.parents[1]), str(REPO / "output" / "remediation" / "tools")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

import calibrate_claude as CC  # noqa: E402
import opus_handoff as OH  # noqa: E402
from gallery_audit import chunk_writer as CW  # noqa: E402
from l5.links import StepError  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical.identity_lanes import name_lane, spoken_lane  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from identity import (  # noqa: E402  # noqa: E402
    common,
    export,
    name_write,
    names_judge,
    plan_files,
    retarget,
    retarget_plan,
    scope_judge,
    verify,
    waves,
)
from identity import rounds as R  # noqa: E402
from identity.rounds import Question, StageSpec  # noqa: E402

Reader = Callable[[str], list[dict[str, Any]]]


@dataclass(frozen=True)
class StageDef:
    """A stage: its spec and the function that builds its population."""

    spec: StageSpec
    population: Callable[[], list[Question]]


class UsageError(ValueError):
    """The command cannot be taken as asked. Nothing was written."""


def _print(payload: Any) -> None:
    print(verify.dump(payload))


def read_only_reader() -> Reader:
    return MP.psql_json_reader(read_only=True)


# ------------------------------------------------------------------------------------ the stages
def stage_def(args: argparse.Namespace, run: Path) -> StageDef:
    """The stage `--lane/--stage` names, its population built from the discovery's files."""
    root = args.root
    lane, stage = args.lane, args.stage
    if (lane, stage) == (retarget.LANE, retarget.WEB):
        exported = export.load_export(run / common.EXPORT_FILE)
        return StageDef(
            retarget.web_spec(retarget.holders_of(exported)),
            lambda: retarget.web_questions(run, root=root),
        )
    if (lane, stage) == (retarget.LANE, retarget.RECHECK):
        spec = retarget.recheck_spec()
        web = R.stage_dir(run, retarget.web_spec({}))
        return StageDef(
            spec,
            lambda: retarget.recheck_questions(_asked(web), R.decisions_by_site(web)),
        )
    if (lane, stage) == (scope_judge.LANE, scope_judge.WEB):
        return StageDef(scope_judge.web_spec(), lambda: scope_judge.questions(run, root=root))
    if (lane, stage) == (scope_judge.LANE, scope_judge.RECHECK):
        web = R.stage_dir(run, scope_judge.web_spec())
        return StageDef(
            scope_judge.recheck_spec(),
            lambda: scope_judge.recheck_questions(_asked(web), R.decisions_by_site(web)),
        )
    if (lane, stage) == (names_judge.LANE, names_judge.CLEAN_WEB):
        return StageDef(
            names_judge.clean_spec(), lambda: names_judge.clean_questions(run, root=root)
        )
    if (lane, stage) == (names_judge.LANE, names_judge.CLEAN_RECHECK):
        web = R.stage_dir(run, names_judge.clean_spec())
        return StageDef(
            names_judge.recheck_spec(),
            lambda: names_judge.recheck_questions(
                _asked(web),
                R.decisions_by_site(web),
                names_judge.clean_questions(run, root=root, rule_made=True),
            ),
        )
    if (lane, stage) == (names_judge.LANE, names_judge.SPOKEN):
        return StageDef(
            names_judge.spoken_spec(), lambda: names_judge.spoken_questions(run, root=root)
        )
    raise UsageError(f"no stage {stage!r} in lane {lane!r}")


def _asked(stage_dir: Path) -> list[Question]:
    """The questions a stage asked, from its stored contexts (empty before round 1)."""
    if not R.load_rounds(stage_dir):
        return []
    return [Question(sid, ctx) for sid, ctx in sorted(R.load_contexts(stage_dir).items())]


def _pick(questions: list[Question], args: argparse.Namespace) -> list[Question]:
    if args.sites_file:
        wanted = [
            line.strip()
            for line in Path(args.sites_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        known = {q.site_id: q for q in questions}
        unknown = [s for s in wanted if s not in known]
        if unknown:
            raise UsageError(
                f"{len(unknown)} site(s) of {args.sites_file} are not in the population: {unknown[:3]}"
            )
        return [known[s] for s in wanted]
    if args.pilot:
        chosen = set(retarget.pilot_sites(questions, args.pilot))
        return [q for q in questions if q.site_id in chosen]
    return questions


def cmd_stage(args: argparse.Namespace, run: Path) -> int:
    definition = stage_def(args, run)
    spec = definition.spec
    out = R.stage_dir(run, spec)
    command = args.command
    if command == "export":
        if R.load_rounds(out):
            raise UsageError("round 1 is exported already - re-ask with export-reask")
        record = R.export_round(
            out, spec, Path(args.handoff).resolve(), _pick(definition.population(), args)
        )
    elif command == "export-reask":
        held = R.reask_sites(out)
        stored = R.load_contexts(out)
        record = R.export_round(
            out,
            spec,
            Path(args.handoff).resolve(),
            [Question(sid, stored[sid]) for sid in sorted(held)],
            earlier=held,
        )
    elif command == "brief":
        print(R.brief(out, spec, args.round, args.batch_id))
        return 0
    elif command == "check-answer":
        text = Path(args.text_file).read_bytes().decode("utf-8")
        problem = R.check_answer(out, spec, args.round, args.batch_id, args.label, text)
        _print({"ok": problem is None, "problem": problem})
        return 0 if problem is None else 1
    elif command == "import":
        verdict = R.require_calibration(Path(args.calibration_root), args.calibration, spec.role)
        summary = R.import_round(out, spec, args.round)
        _print(
            {**summary, "calibration": verdict["calibration_id"], "agreement": verdict["agreement"]}
        )
        return 0
    else:  # status
        decisions = R.load_decisions(out)
        _print(
            {
                "stage": spec.stage,
                "role": spec.role,
                "model": spec.model,
                "rounds": [r.name for r in R.load_rounds(out)],
                "decided": sum(d["status"] == R.DECIDED for d in decisions),
                "held": sum(d["status"] == R.HELD for d in decisions),
            }
        )
        return 0
    _print({"round": record.name, "sites": len(record.sites), "batches": len(record.batches)})
    return 0


# ------------------------------------------------------------------------------------ the results
def _now() -> str:
    return R.now_utc()


def _decisions(run: Path, spec: StageSpec) -> dict[str, dict[str, Any]]:
    return R.decisions_by_site(R.stage_dir(run, spec))


def cmd_retarget(args: argparse.Namespace, run: Path) -> int:
    web_dir = R.stage_dir(run, retarget.web_spec({}))
    web, second = _decisions(run, retarget.web_spec({})), _decisions(run, retarget.recheck_spec())
    command = args.command
    lane_dir = retarget_plan.lane_dir(run)
    if command == "result":
        asked = R.load_contexts(web_dir)
        final = retarget.final_state(web, second)
        common.write_jsonl(lane_dir / "RESULT.jsonl", final)
        retire, merge, owner = [], [], []
        for row in final:
            sid, ctx = row["site_id"], asked[row["site_id"]]
            data = web[sid]["data"] if row["verdict"] else None
            if row["state"] == retarget.FINAL_CONFIRMED and row["verdict"] == retarget.RETIRE:
                retire.append({"site_id": sid, "name": ctx["name"], "why": data["why"], "quotes": data["quotes"],
                               "ask": "the scope lane (scope_review): E3 not an archaeological site"})  # fmt: skip
            elif row["state"] == retarget.FINAL_CONFIRMED and row["verdict"] == retarget.MERGE:
                merge.append({"site_id": sid, "name": ctx["name"], "merge_with": data["merge_with"],
                              "why": data["why"], "quotes": data["quotes"], "ask": "D14: a duplicate"})  # fmt: skip
            elif row["state"] in (
                retarget.FINAL_REJECTED,
                retarget.FINAL_WAITING,
                retarget.FINAL_HELD,
            ):
                reason = (web.get(sid) or {}).get("reason", "")
                owner.append({"site_id": sid, "name": ctx["name"], "state": row["state"],
                              "verdict": row["verdict"], "reason": reason})  # fmt: skip
        common.write_jsonl(lane_dir / "RETIRE_LIST.jsonl", retire)
        common.write_jsonl(lane_dir / "MERGE_LIST.jsonl", merge)
        common.write_jsonl(lane_dir / "OWNER_LIST.jsonl", owner)
        states: dict[str, int] = {}
        for row in final:
            key = f"{row['verdict']}:{row['state']}"
            states[key] = states.get(key, 0) + 1
        _print({"asked": len(final), "by_verdict_and_state": dict(sorted(states.items())),
                "retire_list": len(retire), "merge_list": len(merge), "owner_list": len(owner)})  # fmt: skip
        return 0
    if command == "wave":
        _print(
            retarget_plan.select_wave(
                run,
                args.wave,
                retarget_plan.confirmed(web, second),
                limit=args.limit,
                built_at=_now(),
            )
        )
        return 0
    if command in ("chain-done", "chain-ready", "chain-status"):
        if command == "chain-done":
            done = retarget_plan.chain_done(
                run, args.wave, args.stage_name, args.stamp, args.sites or None
            )
            _print({"stage": args.stage_name, "sites": len(done)})
        elif command == "chain-ready":
            _print(retarget_plan.chain_ready(run, args.stage_name))
        else:
            _print(retarget_plan.chain_table(run))
        return 0
    wave_record = retarget_plan.load_wave(run, args.wave)
    ids = wave_record["sites"]
    every = retarget_plan.confirmed(web, second)
    decisions = {s: every[s] for s in ids}
    rechecks = {s: second[s] for s in ids}
    asked = R.load_contexts(web_dir)
    items = sorted({d["data"]["target"]["qid"]["value"] for d in decisions.values()})
    names = sorted({d["data"]["target"]["name"]["value"] for d in decisions.values()})
    if command == "step":
        commands = retarget_plan.link_commands(args.wave)
        return commands[args.step_command](args.step)
    reader = read_only_reader()
    if command == "plan-links":
        live = retarget_plan.read_live(ids, items, [], reader, names=False)
        plan = retarget_plan.build_links(decisions, rechecks, asked, live)
        out = retarget_plan.write_links(run, args.wave, plan)
        _print({"links": len(plan.links), "sites": len({c.site_id for c in plan.links}),
                "skipped": len(plan.skipped), "step": None if out is None else str(out)})  # fmt: skip
        return 0
    live = retarget_plan.read_live(ids, items, names, reader, names=True)
    if command == "plan-names":
        plan = retarget_plan.build_names(decisions, rechecks, live, args.wave)
        out = A.lane_dir(plan.lane)
        mech = name_write.write_name_plan(plan, _now(), out)
        chunks = name_write.write_alias_chunk(plan, args.wave, out / "alias")
        _print(
            {
                **mech.counters,
                "lane": plan.lane.name,
                "dir": str(out),
                "alias_chunks": [str(c) for c in chunks],
            }
        )
        return 0
    if command == "verify":
        skipped = _skipped_sites(run, args.wave)
        report = retarget_plan.verify_wave(decisions, asked, live, skipped)
        deviating = [r for r in report if r["deviations"]]
        _print({"sites": len(report), "landed": sum(r["state"] == "landed" for r in report),
                "skipped": sum(r["state"] == "skipped" for r in report),
                "deviations": len(deviating), "detail": deviating[:10]})  # fmt: skip
        return 0 if not deviating else 1
    if command == "handoffs":
        ready = [s for s in retarget_plan.chain_ready(run, "point_type") if s in decisions]
        if not ready:
            raise UsageError("no site of this wave has finished links, name and alias yet")
        records = retarget_plan.handoff_records(decisions, asked, ready, args.wave)
        _print(retarget_plan.write_handoffs(run, args.wave, records))
        return 0
    raise UsageError(f"no command {command!r} in lane retarget")


def _skipped_sites(run: Path, wave: str) -> dict[str, str]:
    """The sites a wave's plans left out, with why: the link plan's and the name plan's."""
    skipped: dict[str, str] = {}
    files = [retarget_plan.wave_dir(run, wave) / "LINKS_SKIPPED.jsonl"]
    name_skips = A.lane_dir(name_lane("retarget-name", wave)) / "SKIPPED.jsonl"
    for path in (*files, name_skips):
        if path.exists():
            for row in common.read_jsonl(path):
                skipped.setdefault(row["site_id"], f"{row['reason']}: {row['note']}")
    return skipped


def cmd_scope(args: argparse.Namespace, run: Path) -> int:
    web_spec = scope_judge.web_spec()
    web_dir = R.stage_dir(run, web_spec)
    web, second = _decisions(run, web_spec), _decisions(run, scope_judge.recheck_spec())
    lane_dir = run / scope_judge.LANE
    command = args.command
    final = scope_judge.final_state(web, second)
    if command == "result":
        asked = R.load_contexts(web_dir)
        common.write_jsonl(lane_dir / "RESULT.jsonl", final)
        owner = [
            {"site_id": r["site_id"], "name": asked[r["site_id"]]["name"], "state": r["state"],
             "verdict": r["verdict"], "reason": (web.get(r["site_id"]) or {}).get("reason", "")}
            for r in final if r["state"] in ("rejected", "held", "waiting-for-recheck")
        ]  # fmt: skip
        common.write_jsonl(lane_dir / "OWNER_LIST.jsonl", owner)
        counts: dict[str, int] = {}
        for r in final:
            key = f"{r['verdict']}:{r['state']}"
            counts[key] = counts.get(key, 0) + 1
        _print(
            {
                "asked": len(final),
                "by_verdict_and_state": dict(sorted(counts.items())),
                "owner_list": len(owner),
            }
        )
        return 0
    writable = {r["site_id"] for r in final if r["state"] in ("kept", "confirmed")}
    if command == "wave":
        _print(waves.select_wave(lane_dir, args.wave, writable, limit=args.limit, built_at=_now()))
        return 0
    ids = waves.load_wave(lane_dir, args.wave)["sites"]
    lane = scope_judge.scope_window_lane(args.wave)
    out = A.lane_dir(lane)
    if command == "plan":
        asked = R.load_contexts(web_dir)
        live = {str(r["site_id"]): r for r in read_only_reader()(scope_judge.live_sql(ids))}
        built = scope_judge.build({s: web[s] for s in ids}, second, asked, live, args.wave)
        mech = scope_judge.to_plan(built, _now())
        lines = [
            *plan_files.header_lines(mech, "D20 scope window", "scripts/remediation/identity/"),
            *[
                f"* **{c.site_name}** (`{c.site_id}`): {c.old_value!r} -> {c.new_value!r}"
                for c in built.changes
                if c.column == "scope_reason"
            ],
            *plan_files.skipped_lines(built.skipped),
            "",
        ]
        plan_files.write_cell_plan(mech, built.skipped, out, "\n".join(lines))
        wave_out = waves.wave_dir(lane_dir, args.wave)
        wave_out.mkdir(parents=True, exist_ok=True)
        common.write_jsonl(wave_out / scope_judge.PERIOD_WRONG_FILE, built.period_wrong)
        _print({**mech.counters, "lane": lane.name, "dir": str(out)})
        return 0
    if command == "verify":
        return _verify_cells(out)
    raise UsageError(f"no command {command!r} in lane scope-window")


def _verify_cells(out: Path) -> int:
    """The planned cells of a lane against production now (read-only): 0 deviations or exit 1."""
    cells = verify.planned_cells(out / "PLAN.jsonl")
    columns = sorted({c["column"] for c in cells})
    rows = read_only_reader()(verify.live_cells_sql([c["site_id"] for c in cells], columns))
    deviations = verify.cell_deviations(cells, {str(r["site_id"]): r for r in rows})
    report = verify.wave_report(deviations, len(cells))
    _print(report)
    return 0 if report["accepted"] else 1


def cmd_names(args: argparse.Namespace, run: Path) -> int:
    kind, command = args.kind, args.command
    if kind == "clean":
        web_spec = names_judge.clean_spec()
        lane_dir = run / names_judge.LANE / "clean"
        web_dir = R.stage_dir(run, web_spec)
        recheck_dir = R.stage_dir(run, names_judge.recheck_spec())
        web, second = R.decisions_by_site(web_dir), R.decisions_by_site(recheck_dir)
        rule_asked = {
            q.site_id: q.context
            for q in names_judge.clean_questions(run, root=args.root, rule_made=True)
        }
        final = names_judge.final_state(web, second, sorted(rule_asked))
        if command == "result":
            common.write_jsonl(lane_dir / "RESULT.jsonl", final)
            counts: dict[str, int] = {}
            for r in final:
                key = f"{r['source']}:{r['state']}"
                counts[key] = counts.get(key, 0) + 1
            _print({"asked": len(final), "by_source_and_state": dict(sorted(counts.items()))})
            return 0
        renames = names_judge.confirmed_renames({}, web, rule_asked, second)
        if command == "wave":
            _print(
                waves.select_wave(lane_dir, args.wave, renames, limit=args.limit, built_at=_now())
            )
            return 0
        ids = waves.load_wave(lane_dir, args.wave)["sites"]
        lane = name_lane("name-clean", args.wave)
        out = A.lane_dir(lane)
        if command == "plan":
            asked = {**R.load_contexts(web_dir), **rule_asked}
            picked = {s: renames[s] for s in ids}
            live = retarget_plan.read_live(
                ids,
                [],
                sorted({r["new_name"] for r in picked.values()}),
                read_only_reader(),
                names=True,
            )
            plan = names_judge.build_clean(
                picked, asked, live.sites, live.keys, live.key_holders, live.name_rows, args.wave
            )
            mech = name_write.write_name_plan(plan, _now(), out)
            chunks = name_write.write_alias_chunk(plan, args.wave, out / "alias")
            _print(
                {
                    **mech.counters,
                    "lane": lane.name,
                    "dir": str(out),
                    "alias_chunks": [str(c) for c in chunks],
                }
            )
            return 0
        if command == "verify":
            return _verify_cells(out)
    elif kind == "spoken":
        lane_dir = run / names_judge.LANE / "spoken"
        model = R.decisions_by_site(R.stage_dir(run, names_judge.spoken_spec()))
        rows = names_judge.spoken_rows(names_judge.rule_spoken(run), model)
        if command == "result":
            counts = dict(Counter(row["source"].split(":")[0] for row in rows.values()))
            none = sum(
                d["status"] == R.DECIDED and d["data"]["verdict"] == names_judge.NONE
                for d in model.values()
            )
            _print({"to_write": len(rows), "by_source": counts, "model_none": none,
                    "model_held": sum(d["status"] == R.HELD for d in model.values())})  # fmt: skip
            return 0
        if command == "wave":
            _print(waves.select_wave(lane_dir, args.wave, rows, limit=args.limit, built_at=_now()))
            return 0
        ids = waves.load_wave(lane_dir, args.wave)["sites"]
        lane = spoken_lane(args.wave)
        out = A.lane_dir(lane)
        if command == "plan":
            live = {
                str(r["site_id"]): r for r in read_only_reader()(names_judge.spoken_live_sql(ids))
            }
            plan = names_judge.build_spoken({s: rows[s] for s in ids}, live)
            mech = names_judge.spoken_plan(plan, args.wave, _now())
            lines = [
                *plan_files.header_lines(mech, "D23 spoken name", "scripts/remediation/identity/"),
                *[
                    f"* **{c.site_name}** (`{c.site_id}`): -> {c.new_value!r} ({c.note})"
                    for c in plan.changes
                ],
                *plan_files.skipped_lines(plan.skipped),
                "",
            ]
            plan_files.write_cell_plan(mech, plan.skipped, out, "\n".join(lines))
            _print({**mech.counters, "lane": lane.name, "dir": str(out)})
            return 0
        if command == "verify":
            return _verify_cells(out)
    raise UsageError(f"no command {command!r} for --kind {kind}")


# ------------------------------------------------------------------------------------ the parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--lane", required=True, choices=[retarget.LANE, scope_judge.LANE, names_judge.LANE]
    )
    parser.add_argument("--kind", choices=["clean", "spoken"], help="lane names: which write")
    parser.add_argument("--run-dir", type=Path, default=None, help="the discovery's directory")
    parser.add_argument(
        "--root", type=Path, default=None, help="the main checkout (the wiki cache)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def stage_command(name: str, help_: str) -> argparse.ArgumentParser:
        cmd = sub.add_parser(name, help=help_)
        cmd.add_argument("--stage", required=True)
        return cmd

    for name in ("export", "export-reask"):
        cmd = stage_command(name, "a round of questions into a new handoff directory")
        cmd.add_argument("--handoff", required=True, type=Path)
        if name == "export":
            cmd.add_argument("--pilot", type=int, default=0)
            cmd.add_argument("--sites-file", type=Path, default=None)
    for name in ("brief", "check-answer"):
        cmd = stage_command(name, "the agent's brief / the shape of one answer")
        cmd.add_argument("--round", required=True)
        cmd.add_argument("--batch-id", required=True)
    sub.choices["check-answer"].add_argument("--label", required=True)
    sub.choices["check-answer"].add_argument("--text-file", required=True, type=Path)
    importer = stage_command(
        "import", "fetch, quote-check, decide; needs a passed calibration verdict"
    )
    importer.add_argument("--round", required=True)
    importer.add_argument(
        "--calibration", required=True, help="the calibration id of the stage's role"
    )
    importer.add_argument("--calibration-root", type=Path, default=CC.CALIBRATION_ROOT)
    stage_command("status", "rounds and decisions of a stage")

    sub.add_parser("result", help="the stage results and the lists the other lanes read")
    for name in ("wave", "plan", "plan-links", "plan-names", "verify", "handoffs", "step"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--wave", required=True)
        if name == "wave":
            cmd.add_argument("--limit", type=int, default=waves.SITES_PER_WAVE)
    sub.choices["step"].add_argument(
        "step_command",
        choices=["check", "rehearse", "probe-guards", "apply", "verify", "rehearse-rollback"],
    )
    sub.choices["step"].add_argument("--step", type=int, default=retarget_plan.LINK_STEP)
    chain = sub.add_parser("chain-done", help="record that a stage landed for the wave's sites")
    chain.add_argument("--wave", required=True)
    chain.add_argument("--stage-name", required=True, choices=list(retarget_plan.CHAIN))
    chain.add_argument("--stamp", required=True)
    chain.add_argument("--sites", nargs="*", default=[])
    ready = sub.add_parser("chain-ready", help="the sites a stage may start on")
    ready.add_argument("--stage-name", required=True, choices=list(retarget_plan.CHAIN))
    sub.add_parser("chain-status", help="every site of every wave and where its chain stands")
    return parser


STAGE_COMMANDS = {"export", "export-reask", "brief", "check-answer", "import", "status"}


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    run = args.run_dir or common.run_dir()
    try:
        if args.command in STAGE_COMMANDS:
            return cmd_stage(args, run)
        if args.lane == retarget.LANE:
            return cmd_retarget(args, run)
        if args.lane == scope_judge.LANE:
            return cmd_scope(args, run)
        if not args.kind:
            raise UsageError("lane names needs --kind clean or --kind spoken")
        return cmd_names(args, run)
    except (
        UsageError,
        R.RoundError,
        waves.WaveError,
        OH.HandoffError,
        Q.AuditError,
        MP.PlanError,
        CW.ChunkError,
        StepError,
        common.IdentityError,
        CC.CalibrationError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
