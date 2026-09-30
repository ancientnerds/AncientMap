"""`python -m pipeline.studio episode ...`: one subcommand per video-studio step (spec 4)."""

from __future__ import annotations

import argparse
import json
import shlex
from typing import Any

from pipeline.studio import config, markers
from pipeline.studio.blocks import load_registry
from pipeline.studio.captures import record_captures
from pipeline.studio.episode import (
    episode_workspace,
    init_episode,
    load_all,
    load_case,
    load_episode,
    load_json,
    music_config,
    require_valid,
)
from pipeline.studio.errors import StudioError
from pipeline.studio.ledger_client import publish_remote
from pipeline.studio.package import build_package, check_title, package_thumbnail
from pipeline.studio.paper.publish import prepare_video, register_video
from pipeline.studio.paper.workspace import published_slug
from pipeline.studio.render import CANDIDATES, render_episode, render_thumbnail
from pipeline.studio.review import render_review
from pipeline.studio.timeline import build_timeline
from pipeline.studio.voice import voice_episode


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _music(choice: str, credit: str | None) -> dict[str, Any] | None:
    if choice == "none":
        return None
    if choice == "auto":
        from pipeline.video.__main__ import single_audio

        track = single_audio(config.video_assets() / "music")
        if track is None:
            raise StudioError(
                "video-assets/music holds no or several audio files: pass --music <file> or none"
            )
        choice = track.name
    if not (config.video_assets() / "music" / choice).is_file():
        raise StudioError(f"video-assets/music/{choice} does not exist")
    return music_config(choice, credit or "")


def paper_ref(request_id: str, slug: str | None) -> dict[str, str]:
    """{request_id, slug}: the slug a successful publish from this machine returned
    (publish_outcome.json, `published_slug`); otherwise the given --paper-slug."""
    published = published_slug(config.paper_dir(request_id) / "publish_outcome.json")
    if published is not None:
        if slug is not None and slug != published:
            raise StudioError(f"--paper-slug {slug!r} is not the published slug {published!r}")
        return {"request_id": request_id, "slug": published}
    if slug is None:
        raise StudioError(
            "--paper needs --paper-slug (the published /research/<slug>): the paper "
            "workspace records no successful publish"
        )
    return {"request_id": request_id, "slug": config.check_slug(slug)}


def cmd_init(args: argparse.Namespace) -> int:
    ws = episode_workspace(args.slug)
    paper = paper_ref(args.paper, args.paper_slug) if args.paper else None
    data = init_episode(
        ws,
        paper=paper,
        topic_type=args.topic,
        fmt=args.format,
        music=_music(args.music, args.music_credit),
    )
    _print({"workspace": str(ws.root), "episode": data})
    return 0


def cmd_markers_export(args: argparse.Namespace) -> int:
    ws = episode_workspace(args.slug)
    cf = load_case(ws, load_episode(ws), load_registry())
    _print(markers.export_markers(ws.root, cf))
    return 0


def cmd_markers_import(args: argparse.Namespace) -> int:
    _print(markers.import_markers(episode_workspace(args.slug).root))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    loaded = load_all(episode_workspace(args.slug))
    _print({"errors": loaded.report.errors, "deferred": loaded.report.deferred})
    return 0 if loaded.report.passed else 1


def cmd_review(args: argparse.Namespace) -> int:
    ws = episode_workspace(args.slug)
    loaded = load_all(ws)
    ws.review.write_text(
        render_review(loaded.script, loaded.casefile, loaded.words, loaded.report), encoding="utf-8"
    )
    _print({"review": str(ws.review), "errors": len(loaded.report.errors)})
    return 0


def cmd_voice(args: argparse.Namespace) -> int:
    ws = episode_workspace(args.slug)
    loaded = load_all(ws)
    require_valid(loaded, final=False)
    words = voice_episode(ws, loaded.script)
    after = load_all(ws)
    _print({"beats": len(words), "errors": after.report.errors, "deferred": after.report.deferred})
    return 0 if after.report.passed else 1


def cmd_capture(args: argparse.Namespace) -> int:
    ws = episode_workspace(args.slug)
    loaded = load_all(ws)
    require_valid(loaded, final=False)
    only = [c.strip() for c in args.only.split(",")] if args.only else None
    _print(sorted(record_captures(ws, loaded.script, only=only)))
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    t = build_timeline(episode_workspace(args.slug))
    _print({"durationInFrames": t["durationInFrames"], "scenes": len(t["scenes"])})
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    _print(render_episode(episode_workspace(args.slug)))
    return 0


def cmd_thumbnail(args: argparse.Namespace) -> int:
    _print(render_thumbnail(episode_workspace(args.slug), args.candidate, args.frame))
    return 0


def cmd_package(args: argparse.Namespace) -> int:
    _print(build_package(episode_workspace(args.slug)))
    return 0


def register_youtube(
    slug: str, youtube_id: str, title: str, published_at: str, poster: int
) -> dict[str, Any]:
    """Record a manual upload: the paper registration proven first, then the ledger, then the
    paper.

    `poster` is the thumbnail candidate K used on YouTube (or the A/B winner, owner question
    Q2): package/thumbnail_<K>.jpg becomes the paper page's video poster (owner decision 13).
    The ledger write cannot be repeated (a published row is no longer 'rendered'), so the paper
    registration is proven before it (publish.prepare_video): a dry run without the poster (an
    evidence id the paper does not carry, or a video it already has, stops here with nothing
    written or uploaded), the verified upload of the thumbnail as video_<youtube_id>.jpg, a dry
    run with it. When the apply then fails, the ledger is already written: the error names the
    `paper register-video` command that finishes the registration (its first dry run refuses
    a registration that did commit). An episode without a paper writes only the ledger.
    """
    from pipeline.video.shorts_ledger import sha256_file

    ws = episode_workspace(slug)
    ledger = load_json(ws.render_dir / "ledger.json", "run `episode render` first")
    video = ws.package_dir / f"{slug}.mp4"
    if not video.exists() or sha256_file(video) != ledger["row"]["video_sha256"]:
        raise StudioError("package/<slug>.mp4 is not the file the ledger recorded; re-package")
    if poster not in CANDIDATES:
        raise StudioError(f"--poster must be one of {list(CANDIDATES)}")
    thumb = ws.package_dir / package_thumbnail(poster)
    if not thumb.is_file():
        raise StudioError(f"package/{thumb.name} does not exist: run `episode package`")
    episode = load_json(ws.config, "")
    payload = None
    stamps_path = ws.package_dir / "evidence_timestamps.json"
    if episode["paper"] is not None:
        stamps = load_json(stamps_path, "run `episode package` first")
        request_id = episode["paper"]["request_id"]
        payload = prepare_video(
            request_id, youtube_id, check_title(title), published_at, stamps, thumb
        )
    out: dict[str, Any] = {
        "ledger": publish_remote(ledger["row"]["video_sha256"], youtube_id, published_at)
    }
    if payload is not None:
        try:
            out["paper"] = register_video(payload, dry_run=False)
        except StudioError as exc:
            finish = shlex.join(
                [
                    "python",
                    "-m",
                    "pipeline.studio",
                    "paper",
                    "register-video",
                    payload["request_id"],
                    "--youtube-id",
                    youtube_id,
                    "--title",
                    title,
                    "--published-at",
                    published_at,
                    "--timestamps",
                    stamps_path.as_posix(),
                    "--poster",
                    thumb.as_posix(),
                ]
            )
            raise type(exc)(f"{exc}; the ledger is written; finish with: {finish}") from exc
    return out


def cmd_register_youtube(args: argparse.Namespace) -> int:
    _print(register_youtube(args.slug, args.youtube_id, args.title, args.published_at, args.poster))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    ep = sub.add_parser("episode", help="the video studio (case file to upload package)")
    es = ep.add_subparsers(dest="command", required=True)
    p = es.add_parser("init", help="create the episode workspace and episode.json")
    p.add_argument("slug")
    p.add_argument("--paper", help="research request id of the paper")
    p.add_argument(
        "--paper-slug",
        help="the paper's public slug (read from publish_outcome.json when it exists)",
    )
    p.add_argument("--topic", required=True, choices=["A", "B", "C", "D"])
    p.add_argument("--format", default="full", choices=["full", "slice"])
    p.add_argument("--music", default="auto", help="auto | none | <file in video-assets/music>")
    p.add_argument("--music-credit", help="credit line for the description")
    p.set_defaults(func=cmd_init)
    simple = [
        ("markers-export", cmd_markers_export, "export the crop check of every marker"),
        ("markers-import", cmd_markers_import, "accept markers_check/verdicts.jsonl"),
        ("check", cmd_check, "validate case file and script; exit 1 on errors"),
        ("review", cmd_review, "write review.html (the owner's script table)"),
        ("voice", cmd_voice, "narrate every beat and time every word"),
        ("timeline", cmd_timeline, "compile timeline.json"),
        ("render", cmd_render, "lint, render, stills, normalise, audit and ledger"),
        ("package", cmd_package, "write the upload package"),
    ]
    for name, func, text in simple:
        p = es.add_parser(name, help=text)
        p.add_argument("slug")
        p.set_defaults(func=func)
    p = es.add_parser("capture", help="record the captures the script declares")
    p.add_argument("slug")
    p.add_argument("--only", help="comma-separated capture ids")
    p.set_defaults(func=cmd_capture)
    p = es.add_parser("thumbnail", help="re-render one thumbnail candidate from another frame")
    p.add_argument("slug")
    p.add_argument("--candidate", required=True, type=int, choices=list(CANDIDATES))
    p.add_argument("--frame", required=True, type=int, help="a frame before any verdict cue")
    p.set_defaults(func=cmd_thumbnail)
    p = es.add_parser("register-youtube", help="record a manual upload in ledger and paper")
    p.add_argument("slug")
    p.add_argument("--youtube-id", required=True)
    p.add_argument("--title", required=True, help="the title the video was uploaded with")
    p.add_argument("--published-at", required=True, help="ISO 8601 with timezone")
    p.add_argument(
        "--poster",
        required=True,
        type=int,
        choices=list(CANDIDATES),
        help="the thumbnail candidate used on YouTube: the paper page's video poster",
    )
    p.set_defaults(func=cmd_register_youtube)
