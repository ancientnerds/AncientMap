# SPDX-License-Identifier: AGPL-3.0-only
"""Backfill the site_shorts ledger (migration 0021) from the renders made before it existed.

    python scripts/backfill_site_shorts_ledger.py                 # plan: print the rows
    python scripts/backfill_site_shorts_ledger.py --apply         # insert them

Reads every video-assets/shorts/<slug>/ that holds a site.json and its <slug>.mp4 (16 on
2026-09-22; the workstation is the only place they exist) and builds each row with the
same code the render step now uses (pipeline/video/shorts_ledger.py): card text and site
id from site.json, the on-screen image ids from selection.json + render/timeline.json,
the voice from description.txt, rendered_at from the mp4's mtime. pipeline_commit stays
NULL: nobody recorded it.

The status is decided as for a live render - the site's scope decision in unified_sites
(shorts_ledger.status_for: retired -> withdrawn) - plus one reviewed per-site decision for
a render made before the scope rule reached the batch, WITHDRAWN_BEFORE_THE_LEDGER below.
No period heuristic: period_name is a coarse bucket that is often not the site's date (T11).

Both modes read DATABASE_URL (the workstation reaches production through
video-assets/prod-db.env, HUMAN_ONLY A6), because the plan shows exactly the statuses --apply
would insert. The plan only SELECTs the scope of each site. --apply inserts in the same
transaction that read the scope; a row whose video is already in the ledger is skipped
(ON CONFLICT (video_sha256) DO NOTHING), so a second run is a no-op.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.video import shorts_export, shorts_ledger  # noqa: E402

#: Renders made before the ledger whose site lies outside the E3 window without being
#: retired in unified_sites yet. One reviewed decision per site, from the remediation brief
#: (output/remediation/logs/remaining_map_2026-09-22.json, Phase 6 item 9: "Mark Tomb of
#: Jahangir (1627) out of scope"). A retirement in unified_sites takes precedence: its
#: reason is the E4 record.
WITHDRAWN_BEFORE_THE_LEDGER = {
    "50e5e380-1f89-4fa3-88de-e6ad35241316": (
        "out of scope: Tomb of Jahangir dates to 1627, past the E3 cutoff of 500 AD outside "
        "the Americas; rendered before the scope rule reached the batch"
    ),
}

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


def plan(root: Path, session: Session) -> list[shorts_ledger.LedgerRow]:
    """The ledger rows of every finished render under root; reads each site's scope."""
    rows = []
    for site, site_dir, video in rendered_dirs(root):
        status, reason = shorts_ledger.status_for(session, site["id"])
        if status == "rendered" and site["id"] in WITHDRAWN_BEFORE_THE_LEDGER:
            status, reason = "withdrawn", WITHDRAWN_BEFORE_THE_LEDGER[site["id"]]
        rows.append(
            shorts_ledger.row_for_render(
                site,
                site_dir,
                video,
                voice_id=voice_of(site_dir),
                pipeline_commit=None,
                rendered_at=datetime.fromtimestamp(video.stat().st_mtime, tz=UTC),
                status=status,
                status_reason=reason,
            )
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=shorts_export.ASSETS_ROOT)
    parser.add_argument("--apply", action="store_true", help="insert the rows (default: plan)")
    args = parser.parse_args(argv)

    from pipeline.database import get_session

    with get_session() as session:
        rows = plan(args.root, session)
        _print_plan(rows)
        if not args.apply:
            print("plan only; add --apply to insert")
            return 0
        inserted = sum(shorts_ledger.record(session, row) for row in rows)
    print(f"inserted {inserted}, already in the ledger {len(rows) - inserted}")
    return 0


def _print_plan(rows: list[shorts_ledger.LedgerRow]) -> None:
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


if __name__ == "__main__":
    raise SystemExit(main())
