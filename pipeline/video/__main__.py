"""CLI: build one site short.

    python -m pipeline.video short --name "Machu Picchu" [--voice ID] [--images 8]
    python -m pipeline.video short --site-id <uuid> --steps tts,render

Steps run in order export → images → tts → render; each reads what the previous
one wrote into `video-assets/shorts/<slug>/`. The globe clips are recorded
separately (`npm run video:record -- site-short --portrait --input <site.json>
--out <dir>/clips`) and picked up by the render step when present.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from pipeline.article_html_renderer import slugify
from pipeline.database import get_session
from pipeline.video import shorts_export, shorts_images, shorts_render, shorts_tts

ALL_STEPS = ("export", "images", "tts", "render")


def _parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m pipeline.video")
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("short", help="build one site short")
    who = s.add_mutually_exclusive_group(required=True)
    who.add_argument("--site-id")
    who.add_argument("--name", help="exact site name; highest-rarity card wins")
    s.add_argument("--voice", default=shorts_tts.DEFAULT_VOICE)
    s.add_argument("--speed", type=float, default=shorts_tts.DEFAULT_SPEED)
    s.add_argument("--images", type=int, default=8, help="max images to download")
    s.add_argument("--steps", default=",".join(ALL_STEPS))
    return ap.parse_args(argv)


def _site_dir_from_id_or_name(args: argparse.Namespace) -> tuple[dict, Path]:
    with get_session() as session:
        site_id = args.site_id or shorts_export.resolve_site_id(session, args.name)
        site = shorts_export.export_site(session, site_id)
    return site, shorts_export.site_dir(site)


def _exported_site_dir(args: argparse.Namespace) -> Path:
    """Locate a previous export by name (slug) or by site id (scan site.json files)."""
    if args.name:
        site_dir = shorts_export.ASSETS_ROOT / slugify(args.name)
        if not (site_dir / "site.json").exists():
            raise SystemExit(
                f"no export for {args.name!r} at {site_dir}; run the export step first"
            )
        return site_dir
    for candidate in shorts_export.ASSETS_ROOT.glob("*/site.json"):
        if shorts_export.load_site_json(candidate)["id"] == args.site_id:
            return candidate.parent
    raise SystemExit(f"no export for site id {args.site_id}; run the export step first")


def run_short(args: argparse.Namespace) -> Path | None:
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    unknown = set(steps) - set(ALL_STEPS)
    if unknown:
        raise SystemExit(f"unknown steps: {sorted(unknown)}")

    if "export" in steps:
        site, site_dir = _site_dir_from_id_or_name(args)
        path = shorts_export.write_site_json(site)
        logging.info("exported %s → %s (%d images)", site["name"], path, len(site["images"]))
    else:
        # Later steps work offline from the exported site.json (no database).
        site_dir = _exported_site_dir(args)
        site = shorts_export.load_site_json(site_dir / "site.json")

    if "images" in steps:
        landed = asyncio.run(
            shorts_images.download_site_images(site, site_dir / "images", args.images)
        )
        (site_dir / "images.json").write_text(
            json.dumps(landed, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logging.info("%d/%d images on disk", len(landed), min(args.images, len(site["images"])))

    if "tts" in steps:
        shorts_tts.narrate(
            site["card_text"], site_dir / "narration.mp3", voice_id=args.voice, speed=args.speed
        )
        # The name is spoken on its own during the return flight; slower so it lands.
        shorts_tts.narrate(
            site["name"], site_dir / "name.mp3", voice_id=args.voice, speed=args.speed - 0.07
        )

    if "render" in steps:
        images = json.loads((site_dir / "images.json").read_text(encoding="utf-8"))
        return shorts_render.render_short(site, images, site_dir, voice_id=args.voice)
    return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse(sys.argv[1:] if argv is None else argv)
    if args.command == "short":
        out = run_short(args)
        if out:
            print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
