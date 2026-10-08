"""D10 / D17 C4: the MiniMax-judged candidate pool, judged again by Claude from the pictures on disk.

The candidate run of 2026-10-06 (`candidates-2026-10-06`) was judged by `MiniMax-M3.1-Flash-Preview` -
5,739 verdicts - and its `depicts` picked 226 targets, of which 178 were written as heroes (192 first
heroes in all). Owner decision D10: a MiniMax answer is never ground truth; it is re-checked with
Claude and what fails is excluded or swapped through the journal. The pictures are still on disk (5,756
files, named by the sha256 of their rendering URL), so the re-judge costs no download:

* `pool_sites` hands the old run's candidates of the sites that still serve no picture to the
  prefilter and the depicts role, each candidate with its picture's `path`; a candidate whose picture
  is gone is named, never skipped;
* `target_picks` hands the 226 old targets to the adversarial re-check;
* `denied_heroes` names the heroes MiniMax's `depicts` put on a page and Claude does not confirm, in
  the shape the served-image recheck reads (`served_image.recheck`), so that the swap goes through
  the same journalled writer as the 47 of D15.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Collection, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from served_image import state as ST  # noqa: E402

from candidate_search import judge as CJ  # noqa: E402
from candidate_search import search as CS  # noqa: E402

#: The route a pool candidate carries: the old run found every one of them by the name search.
POOL_ROUTE = CS.ROUTE_NAME


class PoolError(ST.StateError):
    """The old run is not in the layout the re-judge reads, or a judgement is missing."""


def picture_path(old_run: Path, candidate: Mapping[str, Any]) -> Path:
    """Where `judge.download` kept a candidate's rendering: `pictures/<sha256(picture_url)[:32]>`."""
    url = str(candidate.get("picture_url") or "")
    return old_run / CJ.PICTURES / hashlib.sha256(url.encode()).hexdigest()[:32]


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise PoolError(f"{path} does not exist")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def pool_sites(
    old_run: Path, site_ids: Collection[str]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """`(sites, missing)`: the old run's candidates of the named sites, each with its `path` and the
    route of the old search; `missing` names the candidates whose picture is no longer on disk."""
    sites: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for site in _jsonl(old_run / CS.CANDIDATES):
        if str(site["site_id"]) not in site_ids:
            continue
        kept = []
        for candidate in site["candidates"]:
            path = picture_path(old_run, candidate)
            if not path.is_file():
                missing.append({"site_id": str(site["site_id"]), "file": str(candidate["file"])})
                continue
            kept.append({**candidate, "path": str(path), "route": POOL_ROUTE})
        if kept:
            sites.append({**site, "candidates": kept})
    return sites, missing


def target_picks(
    old_run: Path, population: Sequence[Mapping[str, Any]], site_ids: Collection[str] | None = None
) -> list[dict[str, Any]]:
    """The old run's targets as picks for the adversarial re-check: the site, the file, the old
    judge's note and stamp, the candidate's picture. A target whose candidate or picture is gone is
    refused by name."""
    by_site = {str(p["site_id"]): p for p in population}
    candidates = {str(s["site_id"]): s for s in _jsonl(old_run / CS.CANDIDATES)}
    verdicts = {
        (str(v["site_id"]), str(v["file"])): v
        for v in _jsonl(old_run / CJ.VERDICTS)
        if v.get("verdict") == CJ.DEPICTS
    }
    picks = []
    for target in _jsonl(old_run / CJ.TARGETS):
        site_id, file = str(target["site_id"]), str(target["commons_file"])
        if site_ids is not None and site_id not in site_ids:
            continue
        site = by_site.get(site_id)
        candidate = next(
            (c for c in candidates.get(site_id, {}).get("candidates", ()) if c["file"] == file),
            None,
        )
        verdict = verdicts.get((site_id, file))
        if site is None or candidate is None or verdict is None:
            raise PoolError(f"{site_id}: target {file!r} has no site, candidate or verdict")
        path = picture_path(old_run, candidate)
        if not path.is_file():
            raise PoolError(f"{site_id}: the picture of target {file!r} is gone ({path})")
        picks.append(
            {
                **site,
                "file": file,
                "path": str(path),
                "picture_url": candidate["picture_url"],
                "note": str(verdict.get("note") or "the old judge gave no note"),
                "answered_by": str(verdict.get("answered_by") or "the old judge"),
            }
        )
    return picks


def denied_pairs(
    old_verdicts: Sequence[Mapping[str, Any]],
    prefiltered: Sequence[Mapping[str, Any]],
    depicts_rows: Sequence[Mapping[str, Any]],
    rejected: Mapping[str, Collection[str]],
) -> list[dict[str, Any]]:
    """The `(site, file)` pairs MiniMax called `depicts` that Claude does not confirm.

    Claude's judgement of a pair is, in order: the prefilter dropped it (`survives` false) - denied,
    with the kind it saw; the depicts role called it something else - denied, with that verdict; the
    depicts role confirmed it but the adversarial re-check rejected it - denied. A pair Claude has not
    judged yet is an error: the denial list is made after the re-judge, never before."""
    pre = {(r["site_id"], r["file"]): r for r in prefiltered}
    dep = {(str(r["site_id"]), str(r["file"])): r for r in depicts_rows}
    out = []
    for old in old_verdicts:
        if old.get("verdict") != CJ.DEPICTS:
            continue
        key = (str(old["site_id"]), str(old["file"]))
        if key in pre and not pre[key]["survives"]:
            out.append(
                {
                    "site_id": key[0],
                    "file": key[1],
                    "verdict": f"not usable ({pre[key]['kind']})",
                    "shows": f"the prefilter saw a {pre[key]['kind']}",
                    "answered_by": pre[key]["answered_by"],
                }
            )
        elif key in dep:
            row = dep[key]
            if row["verdict"] != CJ.DEPICTS:
                out.append(
                    {
                        "site_id": key[0],
                        "file": key[1],
                        "verdict": row["verdict"],
                        "shows": row["note"],
                        "answered_by": row["answered_by"],
                    }
                )
            elif key[1] in rejected.get(key[0], ()):
                out.append(
                    {
                        "site_id": key[0],
                        "file": key[1],
                        "verdict": "rejected by the re-check",
                        "shows": row["note"],
                        "answered_by": row["answered_by"],
                    }
                )
        else:
            raise PoolError(
                f"{key[0]}: {key[1]!r} was called depicts by MiniMax and Claude has not judged it"
            )
    return out


def denied_heroes(state: ST.State, denied: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The denied pairs that are a **live hero** in the read, as `served_image.recheck` heroes
    (`image_id`, `site_id`, the earlier stage and verdict), in image-id order. A denied file the
    page does not serve is no matter for the writer: it is not a hero."""
    wanted = {(str(d["site_id"]), str(d["file"])): d for d in denied}
    out = []
    for sid in state.site_ids():
        for row in state.rows.get(sid, ()):
            file = ST.file_of_row(row)
            d = wanted.get((sid, file)) if file else None
            if d is not None and row.get("is_hero") and not row.get("is_excluded"):
                out.append(
                    {
                        "image_id": int(row["id"]),
                        "site_id": sid,
                        "stage": "image-depicts",
                        "verdict": d["verdict"],
                        "shows": d["shows"],
                        "basis": d["shows"],
                        "answered_by": d["answered_by"],
                    }
                )
    return sorted(out, key=lambda h: h["image_id"])
