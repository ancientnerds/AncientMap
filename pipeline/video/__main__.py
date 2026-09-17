"""CLI: build, audit and batch site shorts.

    python -m pipeline.video short --name "Machu Picchu" [--voice ID] [--steps …]
    python -m pipeline.video audit --name "Machu Picchu"
    python -m pipeline.video batch --limit 10            # plan only
    python -m pipeline.video batch --limit 10 --go       # run, guarded by MiniMax quota

Steps run in order export → images → select → tts → record → render; each reads
what the previous one wrote into `video-assets/shorts/<slug>/`. Only `export`
(and `batch`) need the database. `record` drives the Puppeteer recorder
(`npm run video:record`, headed Chrome, ~10 min) for the two globe clips.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from pipeline.article_html_renderer import slugify
from pipeline.database import get_session
from pipeline.lyra.minimax_shared import probe_minimax_quota
from pipeline.video import (
    shorts_audit,
    shorts_export,
    shorts_images,
    shorts_render,
    shorts_select,
    shorts_tts,
)

ALL_STEPS = ("export", "images", "select", "tts", "record", "render")
RECORDER_DIR = Path(__file__).resolve().parents[2] / "ancient-nerds-map"
RECORDER_API_TARGET = "https://ancientnerds.com"  # site dots + labels from prod, no local DB
RECORD_ATTEMPTS = 2  # the globe-ready poll times out now and then (DNS/proxy hiccup)


def _parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m pipeline.video")
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("short", help="build one site short")
    who = s.add_mutually_exclusive_group(required=True)
    who.add_argument("--site-id")
    who.add_argument("--name", help="exact site name; highest-rarity card wins")
    s.add_argument("--voice", default=shorts_tts.DEFAULT_VOICE)
    s.add_argument("--speed", type=float, default=shorts_tts.DEFAULT_SPEED)
    s.add_argument("--images", type=int, default=40, help="max images to download")
    s.add_argument(
        "--no-vlm",
        action="store_true",
        help="select by aspect + hash only (no MiniMax VLM judgement)",
    )
    s.add_argument("--steps", default=",".join(ALL_STEPS))

    a = sub.add_parser("audit", help="measure a rendered short and write audit.json")
    who_a = a.add_mutually_exclusive_group(required=True)
    who_a.add_argument("--site-id")
    who_a.add_argument("--name")

    b = sub.add_parser("batch", help="run many sites, guarded by the MiniMax quota")
    b.add_argument("--limit", type=int, default=10)
    b.add_argument("--tier-min", type=int, default=4, help="lowest rarity tier to include")
    b.add_argument("--go", action="store_true", help="actually run (default: print the plan)")
    b.add_argument("--min-5h", type=int, default=30, help="pause below this 5-hour %% remaining")
    b.add_argument(
        "--min-weekly", type=int, default=20, help="pause below this weekly %% remaining"
    )
    b.add_argument("--pause-min", type=int, default=30, help="minutes to wait when paused")
    b.add_argument("--voice", default=shorts_tts.DEFAULT_VOICE)
    b.add_argument("--speed", type=float, default=shorts_tts.DEFAULT_SPEED)

    sub.add_parser("report", help="aggregate every audit.json into a markdown report")
    return ap.parse_args(argv)


DB_ATTEMPTS = 3
DB_RETRY_WAIT_S = 15.0


def _site_dir_from_id_or_name(args: argparse.Namespace) -> tuple[dict, Path]:
    """Export from the database; a dropped SSH tunnel is retried a few times
    (the tunnel loop reconnects within seconds), anything else propagates."""
    from sqlalchemy.exc import OperationalError

    for attempt in range(1, DB_ATTEMPTS + 1):
        try:
            with get_session() as session:
                site_id = args.site_id or shorts_export.resolve_site_id(session, args.name)
                site = shorts_export.export_site(session, site_id)
            return site, shorts_export.site_dir(site)
        except OperationalError as exc:
            if attempt == DB_ATTEMPTS:
                raise
            logging.warning(
                "database unreachable (attempt %d/%d): %s",
                attempt,
                DB_ATTEMPTS,
                str(exc).splitlines()[0][:120],
            )
            time.sleep(DB_RETRY_WAIT_S)
    raise AssertionError("unreachable")


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


def _select(site: dict, site_dir: Path, use_vlm: bool) -> None:
    images = json.loads((site_dir / "images.json").read_text(encoding="utf-8"))
    cands = [
        shorts_select.Candidate(
            image=img,
            width=int(img["width"]),
            height=int(img["height"]),
            dhash=shorts_select.hash_image(Path(img["local_path"])),
        )
        for img in images
    ]
    if use_vlm:
        verdicts = shorts_select.judge_all(
            [Path(i["local_path"]) for i in images], site["name"], site["card_text"]
        )
        for cand, verdict in zip(cands, verdicts, strict=True):
            cand.verdict = verdict
    kept, rejected = shorts_select.select_stills(cands, require_verdict=use_vlm)
    selection = {
        "stills": [
            {**c.image, "verdict": c.verdict, "score": round(shorts_select.score(c), 2)}
            for c in kept
        ],
        "rejected": [{"filename": c.image["filename"], "reason": why} for c, why in rejected],
    }
    (site_dir / "selection.json").write_text(
        json.dumps(selection, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for c in kept:
        logging.info("keep  %5.2f %s", shorts_select.score(c), Path(c.image["local_path"]).name)
    for c, why in rejected:
        logging.info("drop  %-28s %s", why, Path(c.image["local_path"]).name)
    logging.info("%d stills selected, %d rejected", len(kept), len(rejected))


def record_clips(site_dir: Path) -> None:
    """Record the opening and return globe clips with the Puppeteer recorder."""
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found on PATH; the recorder needs Node")
    cmd = [
        npm,
        "run",
        "video:record",
        "--",
        "short-opening,short-return",
        "--portrait",
        "--fps",
        "60",
        "--input",
        (site_dir / "site.json").as_posix(),
        "--out",
        (site_dir / "clips").as_posix(),
    ]
    env = {**os.environ, "VITE_DEV_API_TARGET": RECORDER_API_TARGET}
    clips = [site_dir / "clips" / "short-opening.mp4", site_dir / "clips" / "short-return.mp4"]
    for attempt in range(1, RECORD_ATTEMPTS + 1):
        for clip in clips:
            clip.unlink(missing_ok=True)
        logging.info("recording clips (attempt %d/%d)…", attempt, RECORD_ATTEMPTS)
        proc = subprocess.run(cmd, cwd=RECORDER_DIR, env=env, capture_output=True, text=True)
        if all(c.exists() for c in clips):
            return
        tail = "\n".join(proc.stdout.splitlines()[-6:])
        logging.warning("recorder did not produce both clips (rc=%s):\n%s", proc.returncode, tail)
    raise RuntimeError(f"recording failed after {RECORD_ATTEMPTS} attempts for {site_dir.name}")


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

    if "select" in steps:
        _select(site, site_dir, use_vlm=not args.no_vlm)

    if "tts" in steps:
        shorts_tts.narrate(
            site["card_text"], site_dir / "narration.mp3", voice_id=args.voice, speed=args.speed
        )
        # The name is spoken on its own during the return flight; slower so it lands.
        # Its length decides how long the return flight is recorded (site-short.ts).
        site["name_audio_s"] = shorts_tts.narrate(
            site["name"], site_dir / "name.mp3", voice_id=args.voice, speed=args.speed - 0.07
        )
        shorts_export.write_site_json(site)

    if "record" in steps:
        record_clips(site_dir)

    if "render" in steps:
        selection = json.loads((site_dir / "selection.json").read_text(encoding="utf-8"))
        return shorts_render.render_short(site, selection["stills"], site_dir, voice_id=args.voice)
    return None


def quota_percentages() -> tuple[int, int]:
    """(5-hour remaining %, weekly remaining %) of the MiniMax 'general' plan."""
    q = probe_minimax_quota(force=True)
    general = next(
        (x for x in q.get("model_remains", []) if x.get("model_name") == "general"), None
    )
    if general is None:
        raise RuntimeError(f"MiniMax quota probe gave no 'general' model: {q}")
    return int(general["current_interval_remaining_percent"]), int(
        general["current_weekly_remaining_percent"]
    )


def batch_candidates(tier_min: int, limit: int) -> list[dict]:
    """Card-bearing sites of at least `tier_min`, best rarity first, that have no
    passing audit yet."""
    from sqlalchemy import text

    with get_session() as session:
        rows = (
            session.execute(
                text(
                    "SELECT s.id::text AS id, s.name FROM unified_sites s "
                    "JOIN card_stats c ON c.site_id = s.id "
                    "WHERE c.rarity_tier >= :tier AND c.card_description IS NOT NULL "
                    "ORDER BY c.rarity_score DESC NULLS LAST, s.name"
                ),
                {"tier": tier_min},
            )
            .mappings()
            .all()
        )
    out: list[dict] = []
    for row in rows:
        audit = shorts_export.ASSETS_ROOT / slugify(row["name"]) / "audit.json"
        if audit.exists() and json.loads(audit.read_text(encoding="utf-8")).get("ok"):
            continue
        out.append(dict(row))
        if len(out) >= limit:
            break
    return out


def run_batch(args: argparse.Namespace) -> int:
    plan = batch_candidates(args.tier_min, args.limit)
    five_h, weekly = quota_percentages()
    logging.info(
        "MiniMax quota: 5h %d %%, weekly %d %% (pause below %d / %d)",
        five_h,
        weekly,
        args.min_5h,
        args.min_weekly,
    )
    for i, site in enumerate(plan, 1):
        logging.info("%2d. %s", i, site["name"])
    if not args.go:
        logging.info("plan only (%d sites); add --go to run", len(plan))
        return 0
    failures = 0
    for site in plan:
        while True:
            five_h, weekly = quota_percentages()
            if five_h >= args.min_5h and weekly >= args.min_weekly:
                break
            logging.warning(
                "quota low (5h %d %%, weekly %d %%) — pausing %d min",
                five_h,
                weekly,
                args.pause_min,
            )
            time.sleep(args.pause_min * 60)
        site_args = argparse.Namespace(
            site_id=site["id"],
            name=None,
            voice=args.voice,
            speed=args.speed,
            images=40,
            no_vlm=False,
            steps=",".join(ALL_STEPS),
        )
        try:
            run_short(site_args)
            ok, _, _ = shorts_audit.audit_site(shorts_export.ASSETS_ROOT / slugify(site["name"]))
            failures += 0 if ok else 1
        except Exception:
            logging.exception("site failed: %s", site["name"])
            failures += 1
    logging.info("batch done: %d sites, %d failed/failed-audit", len(plan), failures)
    return 1 if failures else 0


def write_report() -> Path:
    """One markdown table over every audited site plus the rejection reasons."""
    rows: list[str] = []
    rejections: dict[str, int] = {}
    audited = sorted(shorts_export.ASSETS_ROOT.glob("*/audit.json"))
    for audit_path in audited:
        a = json.loads(audit_path.read_text(encoding="utf-8"))
        m = a["measurements"]
        failing = ", ".join(c["name"] for c in a["checks"] if not c["ok"]) or "-"
        rows.append(
            f"| {m['site']} | {'PASS' if a['ok'] else 'FAIL'} | {failing} | {m['duration']:.1f} s | "
            f"{m['stills_used']}/{m['stills_kept']} (-{m['stills_rejected']}) | {m['lufs']:.1f} | "
            f"{m['loop_seam']:.1f} | {m['opening_frames']}/{m['return_frames']} |"
        )
        sel_path = audit_path.parent / "selection.json"
        if sel_path.exists():
            for r in json.loads(sel_path.read_text(encoding="utf-8"))["rejected"]:
                key = r["reason"].split(" (")[0].split("=")[0]
                rejections[key] = rejections.get(key, 0) + 1
    lines = [
        f"# Site-Shorts QA report - {len(audited)} sites",
        "",
        "| Site | Audit | Failing checks | Length | Stills used/kept (rejected) | LUFS | Loop seam | Opening/return frames |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## Rejection reasons across all selections",
        "",
        *[f"- {k}: {v}" for k, v in sorted(rejections.items(), key=lambda kv: -kv[1])],
        "",
    ]
    out = shorts_export.ASSETS_ROOT / "AUDIT-REPORT.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse(sys.argv[1:] if argv is None else argv)
    if args.command == "short":
        out = run_short(args)
        if out:
            print(out)
        return 0
    if args.command == "audit":
        ok, _, _ = shorts_audit.audit_site(_exported_site_dir(args))
        return 0 if ok else 1
    if args.command == "report":
        write_report()
        return 0
    return run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
