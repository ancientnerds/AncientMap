# SPDX-License-Identifier: AGPL-3.0-only
"""The site_shorts render ledger (migration 0021, plan 10.4): what each video was made from.

The render step writes one row per rendered file: the card text the narration read, the
Commons images on screen, the voice and the pipeline commit, tied to the file by its
sha256. Without it a published short is decoupled from the data it asserts - when a card
text changes, nobody can tell which video still carries the old claim.

The row is keyed by site id, not by the directory's slug: 16 curated sites share a name
(plan 10.6). Everything here reads what the render step itself wrote into the site
directory (site.json, selection.json, render/timeline.json, the mp4), so the same code
serves the live render and the backfill of renders made before the ledger existed
(scripts/backfill_site_shorts_ledger.py).

The status a row starts with is the site's scope decision (E4, migration 0020) at the time
of the write, read from unified_sites in the same transaction as the insert: a retired
site's render enters as 'withdrawn' with the scope reason, everything else as 'rendered'.
It is NOT guessed from the period: period_name is a coarse bucket that is often not the
site's date (T11, scripts/remediation/census/tests/t11_scope_window.py - museums, bucket
lower bounds, the inclusive 1500 AD boundary of the Americas), and the E4 decision is made
per site. A site retired after its render keeps its 'rendered' row: whoever publishes a
short has to check the site's scope at that moment.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.utils.public_sites import RETIRED

REPO = Path(__file__).resolve().parents[2]

#: The status vocabulary migration 0021 enforces.
STATUSES = ("rendered", "published", "withdrawn")


@dataclass(frozen=True)
class LedgerRow:
    site_id: str
    slug: str
    rendered_at: datetime
    card_text_at_render: str
    card_text_sha256: str
    image_ids: list[int]
    voice_id: str | None
    pipeline_commit: str | None
    video_sha256: str
    status: str
    status_reason: str | None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def used_image_ids(site_dir: Path) -> list[int]:
    """wiki_images ids of the stills the render put on screen, in order of appearance.

    The timeline names each still by its local path; selection.json maps that path to the
    image record. A still the selection does not know raises: the ledger must not guess
    which image a video shows.
    """
    timeline = json.loads((site_dir / "render" / "timeline.json").read_text(encoding="utf-8"))
    stills = json.loads((site_dir / "selection.json").read_text(encoding="utf-8"))["stills"]
    id_by_path = {still["local_path"]: int(still["id"]) for still in stills}
    on_screen = [seg["source"] for seg in timeline if seg["kind"] == "still"]
    missing = [path for path in on_screen if path not in id_by_path]
    if missing:
        raise LookupError(f"{site_dir.name}: timeline stills not in selection.json: {missing}")
    return list(dict.fromkeys(id_by_path[path] for path in on_screen))


_SCOPE_SQL = text(
    "SELECT scope_status, scope_reason FROM unified_sites WHERE id = CAST(:site_id AS uuid)"
)


def status_for(session: Session, site_id: str) -> tuple[str, str | None]:
    """(status, status_reason) a new render of this site starts with: its E4 decision now.

    A site that is gone from unified_sites raises - the row's foreign key would refuse it,
    and a render of a deleted site is a question for a human, not a ledger row.
    """
    row = session.execute(_SCOPE_SQL, {"site_id": site_id}).first()
    if row is None:
        raise LookupError(f"site {site_id} is not in unified_sites: nothing to ledger it under")
    if row.scope_status == RETIRED:
        reason = "site retired (E4)" + (f": {row.scope_reason}" if row.scope_reason else "")
        return "withdrawn", reason
    return "rendered", None


def row_for_render(
    site: dict,
    site_dir: Path,
    video: Path,
    *,
    voice_id: str | None,
    pipeline_commit: str | None,
    rendered_at: datetime,
    status: str,
    status_reason: str | None,
) -> LedgerRow:
    """The ledger row for one rendered video. rendered_at must carry a timezone.

    ``status``/``status_reason`` come from status_for() (the backfill adds its one reviewed
    per-site decision on top); the vocabulary and "withdrawn has a reason" are CHECKs of
    migration 0021.
    """
    if rendered_at.tzinfo is None:
        raise ValueError("rendered_at must be timezone-aware")
    card_text = site["card_text"]
    if not card_text:
        raise ValueError(f"{site['slug']}: a short without a card text has nothing to ledger")
    return LedgerRow(
        site_id=site["id"],
        slug=site["slug"],
        rendered_at=rendered_at,
        card_text_at_render=card_text,
        card_text_sha256=sha256_text(card_text),
        image_ids=used_image_ids(site_dir),
        voice_id=voice_id,
        pipeline_commit=pipeline_commit,
        video_sha256=sha256_file(video),
        status=status,
        status_reason=status_reason,
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed argv
        ["git", *args],  # noqa: S607 - git on PATH, as everywhere on the workstation
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def current_commit(repo: Path = REPO) -> str:
    """The commit the renderer runs from; '-dirty' when tracked files differ from it."""
    sha = _git(repo, "rev-parse", "HEAD")
    dirty = _git(repo, "status", "--porcelain", "--untracked-files=no")
    return f"{sha}-dirty" if dirty else sha


_INSERT = text("""
    INSERT INTO site_shorts (
        site_id, slug, rendered_at, card_text_at_render, card_text_sha256, image_ids,
        voice_id, pipeline_commit, video_sha256, status, status_reason
    ) VALUES (
        CAST(:site_id AS uuid), :slug, :rendered_at, :card_text_at_render, :card_text_sha256,
        CAST(:image_ids AS integer[]), :voice_id, :pipeline_commit, :video_sha256, :status,
        :status_reason
    )
    ON CONFLICT (video_sha256) DO NOTHING
""")


def record(session: Session, row: LedgerRow) -> bool:
    """Insert the row; False when this exact file is already in the ledger.

    The status vocabulary and the published/withdrawn invariants are CHECK constraints of
    migration 0021 - a violation raises from the database, not from here.
    """
    return session.execute(_INSERT, asdict(row)).rowcount == 1
