"""Acceptance of the import-hero wave: three questions per planned site, asked of production.

The wave's own `--readback` proves that a statement ran. This proves that the *page* came out the
way the owner asked: it serves the file the 2025 import links, its thumbnail names the row that
file lives in, and exactly one live row holds the hero flag. It reads; it writes nothing but its
own result file.

The read it works on is not the plan's. `read.read_production()` again, after the last chunk, is
the only read that can settle the question - a plan's old values describe what production looked
like before, not what it looks like now.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from served_image import state as ST


@dataclass(frozen=True)
class WaveResult:
    """What the read shows for the wave's sites, and every site it refuses by name."""

    sites: int
    served_the_import: int
    thumbnail_follows: int
    one_hero: int
    problems: list[str]

    @property
    def ok(self) -> bool:
        """True when every planned site answers all three questions as the lane's rules say."""
        return not self.problems

    def as_json(self) -> dict[str, Any]:
        return {
            "sites": self.sites,
            "served_the_import": self.served_the_import,
            "thumbnail_follows": self.thumbnail_follows,
            "one_hero": self.one_hero,
            "problems": self.problems,
            "ok": self.ok,
        }


def thumbnail_of(site_id: str, filename: str) -> str:
    """The thumbnail URL that names this row's local file - what rule ih4 leaves behind."""
    return f"/data/images/wiki/{site_id[:8]}/{filename}"


def live_heroes(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The rows a gallery actually shows with the hero flag."""
    return [row for row in rows if row.get("is_hero") and not row.get("is_excluded")]


def check_wave(
    state: ST.State,
    claims: Mapping[str, Mapping[str, Any]],
    site_ids: Sequence[str],
) -> WaveResult:
    """The three questions, per site of `site_ids`.

    `claims` is the lane's own join (`plan.join_import`), because it is the join that recorded
    which image the wave moved a site to; a site whose claim holds no image never entered a chunk
    and is not asked about here.
    """
    served_the_import = 0
    thumbnail_follows = 0
    one_hero = 0
    problems: list[str] = []
    for sid in site_ids:
        site = state.sites.get(sid)
        if site is None:
            problems.append(f"{sid}: not in the read any more")
            continue
        rows = state.rows.get(sid, ())
        heroes = live_heroes(rows)
        claim = claims.get(sid, {})
        wanted_file = ST.file_of_url(str(claim.get("image") or "")) or "no Commons file"
        served = ST.served_of(site, rows)
        if served.kind == ST.NONE or served.file != wanted_file:
            problems.append(
                f"{sid} ({site.get('name')!r}): serves {served.file!r}, "
                f"the 2025 import links {wanted_file!r}"
            )
        else:
            served_the_import += 1
        if len(heroes) == 1:
            one_hero += 1
            wanted = thumbnail_of(sid, str(heroes[0]["filename"]))
            if site.get("thumbnail_url") == wanted:
                thumbnail_follows += 1
            else:
                problems.append(
                    f"{sid} ({site.get('name')!r}): thumbnail {site.get('thumbnail_url')!r} "
                    f"does not name the served row {wanted!r}"
                )
        else:
            problems.append(
                f"{sid} ({site.get('name')!r}): {len(heroes)} live hero row(s), expected one"
            )
    return WaveResult(
        sites=len(site_ids),
        served_the_import=served_the_import,
        thumbnail_follows=thumbnail_follows,
        one_hero=one_hero,
        problems=problems,
    )


def wave_site_ids(run_dir: Path, chunk_glob: str = "chunk-0*") -> list[str]:
    """Every site id the run's chunks name, in first-seen order, from their PLAN.jsonl.

    The acceptance asks about the sites the wave *wrote*, which is what the chunks recorded - not
    the sites the plan considered, and certainly not the sites it refused.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for chunk in sorted(Path(run_dir).glob(chunk_glob)):
        for line in open(chunk / "PLAN.jsonl", encoding="utf-8"):
            if not line.strip():
                continue
            sid = str(json.loads(line)["site_id"])
            if sid not in seen:
                seen.add(sid)
                ids.append(sid)
    return ids
