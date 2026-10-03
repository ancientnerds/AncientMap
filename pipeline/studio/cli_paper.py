"""`python -m pipeline.studio paper ...`: one subcommand per paper-studio step (spec 3.2)."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.studio.errors import StudioError
from pipeline.studio.paper import bundle, claims, gates, images, numbering, publish, pull
from pipeline.studio.paper.workspace import read_json, workspace


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_list(_args: argparse.Namespace) -> int:
    print(pull.list_dossiers(), end="")
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    ws = pull.pull(args.request_id, args.dossier_from)
    _print({"workspace": str(ws.root), "brief": str(ws.brief)})
    return 0


def cmd_number(args: argparse.Namespace) -> int:
    built = numbering.number(workspace(args.request_id))
    _print({"sources": len(built.sources), "images": len(built.probative_images)})
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    result = gates.run_check(workspace(args.request_id))
    _print(
        {
            "passed": result["passed"],
            "failing": [g["name"] for g in result["gates"] if not g["passed"]],
            "report": str(workspace(args.request_id).check_report),
        }
    )
    return 0 if result["passed"] else 1


def cmd_claims_export(args: argparse.Namespace) -> int:
    _print(claims.export_claims(workspace(args.request_id)))
    return 0


def cmd_claims_import(args: argparse.Namespace) -> int:
    _print(claims.import_claims(workspace(args.request_id)))
    return 0


def cmd_images_export(args: argparse.Namespace) -> int:
    _print(images.export_images(workspace(args.request_id)))
    return 0


def cmd_images_import(args: argparse.Namespace) -> int:
    _print(images.import_images(workspace(args.request_id)))
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    ws = workspace(args.request_id)
    b = bundle.write_bundle(ws)
    _print({"bundle": str(ws.bundle), "images": bundle.upload_names(b["result"])})
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    ws = workspace(args.request_id)
    record = publish.publish(ws, dry_run=args.dry_run)
    applied = record["apply"]
    summary: dict[str, Any] = {"publish_outcome": str(ws.publish_outcome)}
    if applied is None:
        summary["dry_run"] = "passed"
    else:
        summary.update(
            slug=applied["slug"], url=applied["url"], side_effects=applied["side_effects"]
        )
    _print(summary)
    return 0


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise StudioError(f"--date {value!r} is not a calendar day (YYYY-MM-DD)") from exc


def _report_file(value: str) -> str:
    path = Path(value)
    if not path.is_file():
        raise StudioError(f"--report-file {value} does not exist")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise StudioError(f"--report-file {value} is not UTF-8: {exc}") from exc


def cmd_correct(args: argparse.Namespace) -> int:
    """Prints the apply outcome, whose `side_effects` carry the `paper_published` notice of a
    republish and of a `--report-file --rewrite` (owner decisions 18 and 21)."""
    on = _day(args.date) if args.date else None
    if args.entries and args.evidence_id:
        raise StudioError("--evidence-id goes with --text; an --entries file names its own")
    if args.entries:
        items = read_json(Path(args.entries), "a JSON list [{text, evidence_id?}]")
    else:
        items = [{"text": args.text}]
        if args.evidence_id:
            items[0]["evidence_id"] = args.evidence_id
    report = _report_file(args.report_file) if args.report_file else None
    record = publish.correct(
        workspace(args.request_id),
        publish.correction_entries(items, on),
        with_report=args.with_report,
        republish=args.republish,
        report=report,
        rewrite=args.rewrite,
    )
    _print(record["apply"])
    return 0


def cmd_register_video(args: argparse.Namespace) -> int:
    stamps = read_json(Path(args.timestamps), "a JSON object {ev-NN: seconds}")
    payload = publish.prepare_video(
        args.request_id,
        args.youtube_id,
        args.title,
        args.published_at,
        stamps,
        Path(args.poster) if args.poster else None,
    )
    _print(publish.register_video(payload, dry_run=False))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    paper = sub.add_parser("paper", help="the paper studio (pull, write, check, publish)")
    ps = paper.add_subparsers(dest="command", required=True)
    ps.add_parser("list", help="researched dossiers awaiting a write").set_defaults(func=cmd_list)
    p = ps.add_parser("pull", help="fetch the dossier and write brief.md")
    p.add_argument("request_id")
    p.add_argument(
        "--dossier-from",
        help="a fresh Theo run on this public paper's question: rewrite the paper from its "
        "dossier (the workspace, image paths and publish calls stay this paper's)",
    )
    p.set_defaults(func=cmd_pull)
    simple = [
        ("number", cmd_number, "[S:id] -> [N], References, images -> paper.md"),
        ("check", cmd_check, "run every gate; exit 1 when one fails"),
        ("claims-export", cmd_claims_export, "export the claim-check tasks"),
        ("claims-import", cmd_claims_import, "validate and accept claims_check/verdicts.jsonl"),
        ("images-export", cmd_images_export, "gather, download and export image-check tasks"),
        ("images-import", cmd_images_import, "select checked images and embed them"),
        ("bundle", cmd_bundle, "build bundle.json from a passing check"),
    ]
    for name, func, text in simple:
        p = ps.add_parser(name, help=text)
        p.add_argument("request_id")
        p.set_defaults(func=func)
    p = ps.add_parser("publish", help="upload images, dry-run, then apply")
    p.add_argument("request_id")
    p.add_argument("--dry-run", action="store_true", help="stop after theo_publish --dry-run")
    p.set_defaults(func=cmd_publish)
    p = ps.add_parser("correct", help="append corrections (optionally with a new text)")
    p.add_argument("request_id")
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--text", help="one correction entry")
    what.add_argument("--entries", help="JSON file [{text, evidence_id?}], one entry each")
    p.add_argument("--evidence-id", help="the evidence id --text retires or corrects")
    p.add_argument("--date", help="YYYY-MM-DD for every entry, default today (UTC)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--with-report", action="store_true", help="send the re-checked report and evidence"
    )
    mode.add_argument(
        "--republish", action="store_true", help="send the checked bundle.json result"
    )
    mode.add_argument(
        "--report-file", help="full markdown of a paper without a studio workspace check"
    )
    p.add_argument(
        "--rewrite",
        action="store_true",
        help="with --report-file: a full rewrite (the page shows the writer's disclosure line)",
    )
    p.set_defaults(func=cmd_correct)
    p = ps.add_parser("register-video", help="attach a YouTube video to the published paper")
    p.add_argument("request_id")
    p.add_argument("--youtube-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--published-at", required=True, help="ISO 8601 with timezone")
    p.add_argument("--timestamps", required=True, help="JSON file {ev-NN: seconds}")
    p.add_argument(
        "--poster",
        help="JPEG shown as the video's poster on the paper page: the thumbnail used on "
        "YouTube, <STUDIO_ASSETS>/episodes/<slug>/package/thumbnail_<K>.jpg",
    )
    p.set_defaults(func=cmd_register_video)
