# SPDX-License-Identifier: AGPL-3.0-only
"""Backfill the site_shorts ledger (migration 0021) from the renders made before it existed.

    python scripts/backfill_site_shorts_ledger.py                 # plan: print the rows
    python scripts/backfill_site_shorts_ledger.py --apply         # insert them

Reads every video-assets/shorts/<slug>/ that holds a site.json and its <slug>.mp4 (16 on
2026-09-22; the workstation is the only place they exist) and builds each row with the
same code the render step now uses (pipeline/video/shorts_ledger.py): card text and site
id from site.json, the on-screen image ids from selection.json + render/timeline.json,
the voice from description.txt, rendered_at from the mp4's mtime. pipeline_commit stays
NULL: nobody recorded it. A render of a site outside the E3 window (Tomb of Jahangir,
1627, period "1500+ AD") is entered as withdrawn with its reason.

--apply writes through DATABASE_URL (the workstation reaches production through
video-assets/prod-db.env, HUMAN_ONLY A6) in one transaction; a row whose video is already
in the ledger is skipped (ON CONFLICT (video_sha256) DO NOTHING), so a second run is a
no-op. Without --apply nothing touches a database.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.video import shorts_export, shorts_ledger  # noqa: E402

_VOICE = re.compile(r"Narration: AI-generated voice \(MiniMax [^,]+, ([^)]+)\)\.")


def voice_of(site_dir: Path) -> str:
    """The voice render_short wrote into description.txt."""
    match = _VOICE.search((site_dir / "description.txt").read_text(encoding="utf-8"))
    if match is None:
        raise LookupError(f"{site_dir.name}: no narration voice in description.txt")
    return match.group(1)


def rendered_dirs(root: Path) -> list[tuple[dict, Path, Path]]:
    """(site, site_dir, video) for every directory with a site.json and its final mp4."""
    found = []
    for site_json in sorted(root.glob("*/site.json")):
        site = shorts_export.load_site_json(site_json)
        video = site_json.parent / f"{site['slug']}.mp4"
        if video.exists():
            found.append((site, site_json.parent, video))
    return found


def plan(root: Path) -> list[shorts_ledger.LedgerRow]:
    rows = []
    for site, site_dir, video in rendered_dirs(root):
        rows.append(
            shorts_ledger.row_for_render(
                site,
                site_dir,
                video,
                voice_id=voice_of(site_dir),
                pipeline_commit=None,
                rendered_at=datetime.fromtimestamp(video.stat().st_mtime, tz=UTC),
            )
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=shorts_export.ASSETS_ROOT)
    parser.add_argument("--apply", action="store_true", help="insert the rows (default: plan)")
    args = parser.parse_args(argv)

    rows = plan(args.root)
    for row in rows:
        print(
            json.dumps(
                {
                    "slug": row.slug,
                    "site_id": row.site_id,
                    "rendered_at": row.rendered_at.isoformat(),
                    "images": len(row.image_ids),
                    "voice": row.voice_id,
                    "status": row.status,
                    "reason": row.status_reason,
                    "video_sha256": row.video_sha256[:12],
                },
                ensure_ascii=False,
            )
        )
    print(f"{len(rows)} render(s)")
    if not args.apply:
        print("plan only; add --apply to insert")
        return 0

    from pipeline.database import get_session

    with get_session() as session:
        inserted = sum(shorts_ledger.record(session, row) for row in rows)
    print(f"inserted {inserted}, already in the ledger {len(rows) - inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
