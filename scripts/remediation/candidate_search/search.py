"""The candidate search: a site that serves no picture and carries no Wikidata item.

Owner decision 2026-10-06: build the search, let the model judge every candidate, and let the
INSERT lane write only what it confirmed.

**Why a new search at all.** `vision.wanted_files` reads the site's Wikidata item - its image (P18)
and the files of its Commons categories (P373) - and answers an empty list for a site that has no
item: **852 of the 1,081 sites that serve no picture at all carry no Wikidata id** (measured
2026-10-06), so there is no claim to read and the candidate set is empty before a single question
is asked. What such a site has is a **name**, and Commons' own search finds pictures for a name.

**What it finds, measured before this module was written** (25 sites of that class, the sample drawn
in the order the rest inventory holds them): 164 candidate pictures, **141 of them 800x300 or
larger**, and **13 of the 25 sites** carry at least one such candidate. The name-as-category route
was measured first and found empty: `members(<name>)` returned no still picture for 9 of 10 sites
(Cerna has a category, its two files are not pictures). It is kept because it is the one route that
can be right where the name is unique - a category is named after the site, a search matches words.

**A candidate is not a picture of the site.** The same sample returns a cat in Sidi Bou Said for the
site *Sidi Said* and a church in the Philippines for *Las Capellanías*. So nothing here decides that
a candidate depicts its site: `judge.py` asks the model that, per candidate, and only a `depicts`
verdict reaches the fetch and the INSERT lane. The search's own job is to hand over candidates worth
looking at and to refuse, by name, the sites for which it found none.

**The two questions per site**, both on Commons, both cached (`Commons.search`):

1. `search(f"{name} filetype:bitmap")` - the file namespace, bitmaps only. Without
   `filetype:bitmap` the same query answers scanned books: the five hits for *Monte Lazzu* are all
   PDFs from a library digitisation project, and a PDF is not a picture of a site.
2. `search(f'intitle:"{name}" filetype:bitmap")` - the title form, for the file whose name **is**
   the site's name. A name that carries a comma (*Wamanmarka, Lima*) or a qualifier (*Pumawasi,
   Anta*) matches nothing in this form; that is a fact about the site's name, and the site is then
   refused by name rather than searched for something that resembles it.

A candidate is kept when it is a still picture (`picture_url` serves one), reaches the floor of
this run, and is not a file the site's gallery already holds (`exclude`).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
for _path in (_ROOT, _ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from served_image import commons as CM  # noqa: E402

CANDIDATES = "CANDIDATES.jsonl"
SUMMARY = "CANDIDATE_SUMMARY.json"
REFUSALS = "CANDIDATE_REFUSALS.jsonl"

#: Candidates per site and per query. A category is small; a full-text search is not, and a site
#: whose name is a common word matches a whole municipality - twelve is enough to judge and small
#: enough that the model's picture budget (six per site) is not spent on the twelfth.
HITS_PER_QUERY = 12

#: Why a file was dropped, by name - the four classes the search can produce.
NO_NAME = "no_name"
NO_CANDIDATE = "no_candidate"
ALL_TOO_SMALL = "all_too_small"
NOT_A_PICTURE = "not_a_picture"
EXCLUDED = "already_in_the_gallery"


def terms(name: str) -> list[tuple[str, str]]:
    """The `(query, why)` pairs of one site, in the order they are asked."""
    cleaned = " ".join(str(name or "").split())
    if not cleaned:
        return []
    return [
        (f"{cleaned} filetype:bitmap", f'a Commons picture search for "{cleaned}"'),
        (f'intitle:"{cleaned}" filetype:bitmap', f'a Commons file whose title is "{cleaned}"'),
    ]


def _titles(commons: CM.Commons, name: str) -> list[tuple[str, str]]:
    """Every file the two queries answer, each with the query that named it, first query first."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def take(titles: Iterable[str], why: str) -> None:
        for title in titles:
            key = CM.canonical_file(title)
            if key not in seen:
                seen.add(key)
                found.append((key, why))

    for query, why in terms(name):
        take(commons.search(query, HITS_PER_QUERY), why)
    take(
        commons.members(name, HITS_PER_QUERY), f'in the Commons category "{name}", the site\'s name'
    )
    return found


def candidates(
    commons: CM.Commons,
    site: Mapping[str, Any],
    *,
    floor: tuple[int, int],
    exclude: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], str, str]:
    """One site's candidates, and the reason it has none.

    `(candidates, refusal_reason, refusal_detail)`; the reason is `""` when candidates were found.
    """
    sid = str(site.get("site_id") or "")
    name = str(site.get("name") or "")
    if not name.strip():
        return [], NO_NAME, f"{sid}: the site has no name to search for"
    known = {CM.canonical_file(f) for f in exclude}
    titles = _titles(commons, name)
    if not titles:
        return [], NO_CANDIDATE, f"{sid}: Commons names no file for {name!r}"
    info = commons.imageinfo(name for name, _ in titles)
    boxes = commons.sizes(name for name, _ in titles)
    min_width, min_height = floor
    out: list[dict[str, Any]] = []
    too_small = 0
    for title, why in titles:
        entry = info.get(title) or {}
        width, height = boxes.get(title, (0, 0))
        if entry.get("status") != CM.OK:
            continue
        shown = CM.picture_url(entry)
        if shown is None:
            continue
        if title in known:
            continue
        if width < min_width or height < min_height:
            too_small += 1
            continue
        out.append(
            {
                "file": title,
                "why": why,
                "picture_url": shown,
                "original_url": entry.get("url"),
                "width": width,
                "height": height,
            }
        )
    if out:
        return out, "", ""
    if too_small:
        return (
            [],
            ALL_TOO_SMALL,
            f"{sid}: {too_small} picture(s) of {name!r}, none reaches {min_width}x{min_height}",
        )
    return [], NOT_A_PICTURE, f"{sid}: no still picture of {name!r} on Commons"


def run(
    out: Path,
    sites: Sequence[Mapping[str, Any]],
    commons: CM.Commons,
    *,
    floor: tuple[int, int],
    exclude: Iterable[str] = (),
) -> dict[str, Any]:
    """The whole population's candidates, and the refusals, written once into `out`."""
    excluded = list(exclude)
    rows: list[dict[str, Any]] = []
    refusals: list[dict[str, str]] = []
    for site in sites:
        found, reason, detail = candidates(commons, site, floor=floor, exclude=excluded)
        if reason:
            refusals.append(
                {"site_id": str(site.get("site_id") or ""), "reason": reason, "detail": detail}
            )
            continue
        rows.append(
            {
                "site_id": str(site.get("site_id") or ""),
                "name": str(site.get("name") or ""),
                "country": str(site.get("country") or ""),
                "floor": {"min_width": floor[0], "min_height": floor[1]},
                "candidates": found,
            }
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / CANDIDATES).write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    (out / REFUSALS).write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in refusals),
        encoding="utf-8",
        newline="\n",
    )
    summary = {
        "sites": len(sites),
        "sites_with_candidates": len(rows),
        "candidates": sum(len(row["candidates"]) for row in rows),
        "refused_sites": len(refusals),
        "refusals": {
            reason: sum(1 for r in refusals if r["reason"] == reason)
            for reason in sorted({r["reason"] for r in refusals})
        },
        "floor": {"min_width": floor[0], "min_height": floor[1]},
        "hits_per_query": HITS_PER_QUERY,
    }
    (out / SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
