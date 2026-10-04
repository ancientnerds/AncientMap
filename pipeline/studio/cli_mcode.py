"""`python -m pipeline.studio mcode ...`: the four checks on MiniMax Code (owner decision 2026-10-03).

    python -m pipeline.studio mcode claim-check     <request id> [--limit N]
    python -m pipeline.studio mcode image-check      <request id> [--limit N]
    python -m pipeline.studio mcode marker-check     <slug>       [--limit N]
    python -m pipeline.studio mcode casefile-verify  <slug>       [--limit N]
    python -m pipeline.studio mcode validate --check <check> --workspace <path> \\
        --answer <file> --task <id> [--stage <stage>]
    python -m pipeline.studio mcode probe

The four checks replace the Claude Code workflow scripts of the same names
(`.claude/workflows/theo-claim-check.js` and its three siblings); `validate` is the
command every run's prompt names, `probe` reports the CLI, the model and the weekly quota.

Exit codes: 0 every pending task was answered, 1 at least one was not (the reasons are in
the JSON), 2 a `StudioError`, 3 the weekly plan stop (owner decision O20) - the run
resumes after the reset and the pending tasks are exactly the ones still unanswered.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from pipeline.studio import config, mcode, mcode_checks
from pipeline.studio.errors import StudioError
from pipeline.studio.paper.workspace import PaperWorkspace, workspace


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _exit(result: mcode_checks.CheckResult) -> int:
    _print(result.as_dict())
    if result.stopped:
        return 3
    return 0 if not result.not_answered else 1


def cmd_claim_check(args: argparse.Namespace) -> int:
    return _exit(
        mcode_checks.answer_claims(workspace(args.request_id), repo=config.REPO, limit=args.limit)
    )


def cmd_image_check(args: argparse.Namespace) -> int:
    return _exit(
        mcode_checks.answer_images(workspace(args.request_id), repo=config.REPO, limit=args.limit)
    )


def cmd_marker_check(args: argparse.Namespace) -> int:
    slug = config.check_slug(args.slug)
    return _exit(
        mcode_checks.answer_markers(config.episode_dir(slug), repo=config.REPO, limit=args.limit)
    )


def cmd_casefile_verify(args: argparse.Namespace) -> int:
    slug = config.check_slug(args.slug)
    return _exit(
        mcode_checks.verify_casefile(config.episode_dir(slug), repo=config.REPO, limit=args.limit)
    )


def cmd_validate(args: argparse.Namespace) -> int:
    """`ACCEPTED` or `REJECTED: <every problem>`; exit 0 or 1.

    A run calls this until it prints ACCEPTED, so the message is the whole contract: it
    names what the answer file still lacks, and nothing else in the file is touched.
    """
    if args.check not in mcode_checks.CHECKS:
        raise StudioError(f"--check must be one of {list(mcode_checks.CHECKS)}")
    path = Path(args.workspace)
    if not path.is_dir():
        raise StudioError(f"{path} is not a directory")
    ws = PaperWorkspace(path, path.name) if args.check in ("claims", "images") else None
    problems = mcode_checks.validate_answer_file(
        args.check,
        Path(args.answer),
        task_id=args.task,
        ws=ws,
        ep_root=None if ws is not None else path,
        stage=args.stage or args.check,
    )
    if problems:
        print("REJECTED: " + "; ".join(problems))
        return 1
    print("ACCEPTED")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """What the checks will run on: the CLI, its version, the model, the weekly quota."""
    exe = mcode.exe()
    version = subprocess.run(  # noqa: S603 - a fixed argv
        [str(exe), "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    percent = mcode.weekly_remaining_percent()
    _print(
        {
            "exe": str(exe),
            "version": version,
            "model": mcode.MODEL,
            "effort": mcode.EFFORT,
            "weekly_remaining_percent": percent,
            "weekly_stop": mcode.WEEKLY_STOP_PERCENT,
            "quota_stopped": mcode.weekly_stop(),
            "concurrency": {"start": mcode.START_CONCURRENCY, "cap": mcode.MAX_CONCURRENCY},
            "repo": str(config.REPO),
            "tracked_changes": mcode.tree_state(config.REPO),
            "studio_assets": str(config.studio_assets()),
        }
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    area = sub.add_parser(
        "mcode", help="the four studio checks on MiniMax Code, plus validate and probe"
    )
    commands = area.add_subparsers(dest="command", required=True)
    for name, func, text, takes in [
        (
            "claim-check",
            cmd_claim_check,
            "answer claims_check/pending.jsonl (verifier + skeptic)",
            "request_id",
        ),
        ("image-check", cmd_image_check, "answer images/pending.jsonl", "request_id"),
        ("marker-check", cmd_marker_check, "answer markers_check/pending.jsonl", "slug"),
        ("casefile-verify", cmd_casefile_verify, "verify an episode's case-file evidence", "slug"),
    ]:
        p = commands.add_parser(name, help=text)
        p.add_argument(takes)
        p.add_argument("--limit", type=int, help="answer at most N pending tasks this run")
        p.set_defaults(func=func)
    p = commands.add_parser("validate", help="ACCEPTED or REJECTED for one answer file")
    p.add_argument("--check", required=True, choices=list(mcode_checks.CHECKS))
    p.add_argument("--stage", help="the run's own stage, `skeptic` for a claim task's second run")
    p.add_argument("--workspace", required=True, help="the paper or episode workspace path")
    p.add_argument("--answer", required=True, help="the answer file a run wrote")
    p.add_argument("--task", required=True, help="the task id the prompt names")
    p.set_defaults(func=cmd_validate)
    p = commands.add_parser("probe", help="the CLI, the model and the weekly quota")
    p.set_defaults(func=cmd_probe)
