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


**D17 (2026-10-08): the other routes.** The name search above is the last resort, not the first: a
site with a Wikidata item, a Wikipedia article or a sourced point has better questions to ask, and
`named_files` asks them first. In this order, each file kept once under the first route that names it,
each candidate carrying its `route` and `why`:

1. `p18`, `p373` - the item's image and the first dozen files of its Commons categories, through
   `served_image.vision.wanted_files` (the one reader of the claim);
2. `commonswiki` - the Commons category the item links as its `commonswiki` sitelink;
3. `sdc_p180` - Commons structured data: `haswbstatement:P180=<item>` (files that *say* they depict
   the item);
4. `enwiki_lead`, `enwiki_page` - the English article's lead image and its first dozen images;
5. `researched_category` - a Commons category the identity research found for the site;
6. `name`, `local_name` - the two searches and the category by name, for the site's name and for each
   local name the research found;
7. `geosearch` - files geotagged within 300 m of the site's point, nearest first, at most twenty - only
   for a point whose `_coord_provenance` is sourced (`population.py`; before the marker lane is
   written no point is, and the route says so in the site's notes).

The Wikidata item is the site's single one from `site_external_ids` (`population.py`); a site with two
has no item route and says so. Floor 800x300 (a run parameter), pace one request a second, at most two
sites at once. Files the site holds in its gallery - excluded rows too - and files an earlier pass
judged not to depict it are never offered again.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
for _path in (_ROOT, _ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from served_image import commons as CM  # noqa: E402
from served_image import vision as V  # noqa: E402

CANDIDATES = "CANDIDATES.jsonl"
SUMMARY = "CANDIDATE_SUMMARY.json"
REFUSALS = "CANDIDATE_REFUSALS.jsonl"

#: Candidates per site and per query. A category is small; a full-text search is not, and a site
#: whose name is a common word matches a whole municipality - twelve is enough to judge and small
#: enough that the model's picture budget (six per site) is not spent on the twelfth.
HITS_PER_QUERY = 12
#: Files one site keeps over all routes, in route order. The prefilter looks at sixty pictures to a
#: question, so a site that names more is capped - and says so (`SiteResult.capped`).
MAX_CANDIDATES = 60
#: The geotag route (D17): files within this radius of a **sourced** point, nearest first.
GEOSEARCH_RADIUS_M = 300
GEOSEARCH_LIMIT = 20
#: At most this many sites are searched at once; Commons is still asked one request a second.
MAX_WORKERS = 2

#: The routes, in the order they name files (a file named twice keeps the first, most precise route).
ROUTE_P18 = "p18"
ROUTE_P373 = "p373"
ROUTE_COMMONS_CATEGORY = "commonswiki"
ROUTE_SDC = "sdc_p180"
ROUTE_ENWIKI_LEAD = "enwiki_lead"
ROUTE_ENWIKI_PAGE = "enwiki_page"
ROUTE_RESEARCHED_CATEGORY = "researched_category"
ROUTE_NAME = "name"
ROUTE_LOCAL_NAME = "local_name"
ROUTE_GEOSEARCH = "geosearch"
ROUTES = (
    ROUTE_P18,
    ROUTE_P373,
    ROUTE_COMMONS_CATEGORY,
    ROUTE_SDC,
    ROUTE_ENWIKI_LEAD,
    ROUTE_ENWIKI_PAGE,
    ROUTE_RESEARCHED_CATEGORY,
    ROUTE_NAME,
    ROUTE_LOCAL_NAME,
    ROUTE_GEOSEARCH,
)

#: Why a file was dropped, by name - the four classes the search can produce.
NO_NAME = "no_name"
NO_CANDIDATE = "no_candidate"
ALL_TOO_SMALL = "all_too_small"
NOT_A_PICTURE = "not_a_picture"
EXCLUDED = "already_in_the_gallery"

#: An article image that is no photograph of the site: vector art, a sound, a video, an icon.
_NOT_FOR_PAGE = (".svg", ".ogg", ".oga", ".mp3", ".webm", ".ogv", ".wav", ".flac", ".pdf", ".djvu")


class SearchError(RuntimeError):
    """The search cannot answer for a site from what it was given. Never read as 'no candidate'."""


@dataclass
class SiteResult:
    """One site's search: the candidates, the reason it has none, and what the routes reported."""

    candidates: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    detail: str = ""
    #: What a route could not do for this site and why (a missing article, a Commons gallery page, a
    #: point that is not sourced) - named, so the report can count them.
    notes: list[str] = field(default_factory=list)
    #: Candidates beyond `MAX_CANDIDATES`, left out by name.
    capped: list[str] = field(default_factory=list)


def terms(name: str) -> list[tuple[str, str]]:
    """The `(query, why)` pairs of one site, in the order they are asked."""
    cleaned = " ".join(str(name or "").split())
    if not cleaned:
        return []
    return [
        (f"{cleaned} filetype:bitmap", f'a Commons picture search for "{cleaned}"'),
        (f'intitle:"{cleaned}" filetype:bitmap', f'a Commons file whose title is "{cleaned}"'),
    ]


class _StoreHarvest:
    """`vision.wanted_files` reads `harvest.entity(qid)`; the identity store (the 2026-09-26 harvest
    plus its delta) answers it, and an item neither root holds is an error, not an empty claim."""

    def __init__(self, entities: Any) -> None:
        self.entities = entities

    def entity(self, qid: str) -> Mapping[str, Any]:
        entity, _ = self.entities.get(qid)
        if entity is None:
            raise SearchError(
                f"item {qid} is in neither the harvest nor its delta - fetch it first "
                "(`candidate_search/run.py fetch-entities`)"
            )
        return entity


@dataclass(frozen=True)
class Named:
    """A file a route named: its title, the route and the reason, and a geotag's distance."""

    title: str
    route: str
    why: str
    distance_m: float | None = None


def _take(found: list[Named], seen: set[str], titles: Iterable[str], route: str, why: str) -> None:
    for title in titles:
        key = CM.canonical_file(title)
        if key not in seen:
            seen.add(key)
            found.append(Named(key, route, why))


def _names_of(site: Mapping[str, Any]) -> list[tuple[str, str]]:
    """`(name, route)` of every name the site is searched under: its own, then the researched local
    ones, each once (compared folded)."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    pairs = [(str(site.get("name") or ""), ROUTE_NAME)] + [
        (str(n), ROUTE_LOCAL_NAME) for n in site.get("local_names") or ()
    ]
    for name, route in pairs:
        cleaned = " ".join(name.split())
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            out.append((cleaned, route))
    return out


def named_files(
    commons: Any, site: Mapping[str, Any], entities: Any | None, notes: list[str]
) -> list[Named]:
    """Every file the routes name for one site, first route first, each file once."""
    found: list[Named] = []
    seen: set[str] = set()
    qid = site.get("qid")
    if qid and site.get("qid_conflict") is None and entities is None:
        raise SearchError(f"{site.get('site_id')}: the site has item {qid} but no entity store")
    if site.get("qid_conflict"):
        notes.append(f"two Wikidata items ({', '.join(site['qid_conflict'])}): no item route")
    elif qid:
        harvest = _StoreHarvest(entities)
        for title, why in V.wanted_files({"qid": qid}, harvest, commons):
            route = ROUTE_P18 if "(P18)" in why else ROUTE_P373
            _take(found, seen, [title], route, why)
        entity = harvest.entity(qid)
        link = ((entity.get("sitelinks") or {}).get("commonswiki") or {}).get("title")
        if link and link.startswith("Category:"):
            _take(
                found,
                seen,
                commons.members(link, HITS_PER_QUERY),
                ROUTE_COMMONS_CATEGORY,
                f'in the Commons category "{link[9:]}" the item links (commonswiki)',
            )
        elif link:
            notes.append(f"the commonswiki link {link!r} is a gallery page, not a category")
        _take(
            found,
            seen,
            commons.search(f"haswbstatement:P180={qid} filetype:bitmap", HITS_PER_QUERY),
            ROUTE_SDC,
            f"a Commons file whose structured data says it depicts {qid} (P180)",
        )
    title = site.get("enwiki_title")
    if site.get("enwiki_conflict"):
        notes.append(
            f"two Wikipedia titles ({', '.join(site['enwiki_conflict'])}): no article route"
        )
    elif title:
        article = commons.wikipedia_images(str(title))
        if article["missing"]:
            notes.append(f"the English article {title!r} does not exist")
        else:
            wiki_why = f'on the English Wikipedia article "{title}"'
            if article["lead"] and not article["lead"].lower().endswith(_NOT_FOR_PAGE):
                _take(
                    found,
                    seen,
                    [article["lead"]],
                    ROUTE_ENWIKI_LEAD,
                    f"the lead image of {wiki_why}",
                )
            page_files = [f for f in article["files"] if not f.lower().endswith(_NOT_FOR_PAGE)]
            _take(
                found, seen, page_files[:HITS_PER_QUERY], ROUTE_ENWIKI_PAGE, f"an image {wiki_why}"
            )
    category = site.get("commons_category")
    if category:
        _take(
            found,
            seen,
            commons.members(str(category), HITS_PER_QUERY),
            ROUTE_RESEARCHED_CATEGORY,
            f'in the Commons category "{category}", found by the identity research',
        )
    for name, route in _names_of(site):
        for query, why in terms(name):
            _take(found, seen, commons.search(query, HITS_PER_QUERY), route, why)
        _take(
            found,
            seen,
            commons.members(name, HITS_PER_QUERY),
            route,
            f'in the Commons category "{name}", the site\'s name'
            if route == ROUTE_NAME
            else f'in the Commons category "{name}", a local name of the site',
        )
    if site.get("coord_sourced"):
        for title_, distance in commons.geosearch(
            float(site["lat"]), float(site["lon"]), GEOSEARCH_RADIUS_M, GEOSEARCH_LIMIT
        ):
            if CM.canonical_file(title_) not in seen:
                seen.add(CM.canonical_file(title_))
                found.append(
                    Named(
                        CM.canonical_file(title_),
                        ROUTE_GEOSEARCH,
                        f"a Commons file geotagged within {GEOSEARCH_RADIUS_M} m of the site's "
                        "sourced point",
                        distance,
                    )
                )
    elif site.get("lat") is not None and "coord_sourced" in site:
        notes.append("geotag route skipped: the point is not sourced")
    return found


def site_candidates(
    commons: Any,
    site: Mapping[str, Any],
    *,
    floor: tuple[int, int],
    exclude: Iterable[str] = (),
    entities: Any | None = None,
) -> SiteResult:
    """One site's candidates over every route, and the reason it has none.

    A file is kept when it is a still picture (`picture_url` serves one), reaches the floor, and is
    not a file the site holds - in its gallery (`held_files`, excluded rows too), among `exclude` -
    or one an earlier pass judged not to depict it (`judged_not_depicts`). Candidates keep the route
    order; the first `MAX_CANDIDATES` are kept and the rest named in `capped`."""
    sid = str(site.get("site_id") or "")
    name = str(site.get("name") or "")
    if not name.strip():
        return SiteResult(reason=NO_NAME, detail=f"{sid}: the site has no name to search for")
    notes: list[str] = []
    known = {
        CM.canonical_file(f)
        for f in (
            *exclude,
            *(site.get("held_files") or ()),
            *(site.get("judged_not_depicts") or ()),
        )
    }
    titles = named_files(commons, site, entities, notes)
    if not titles:
        return SiteResult(
            reason=NO_CANDIDATE, detail=f"{sid}: Commons names no file for {name!r}", notes=notes
        )
    info = commons.imageinfo(n.title for n in titles)
    boxes = commons.sizes(n.title for n in titles)
    min_width, min_height = floor
    out: list[dict[str, Any]] = []
    too_small = 0
    for named in titles:
        entry = info.get(named.title) or {}
        width, height = boxes.get(named.title, (0, 0))
        if entry.get("status") != CM.OK:
            continue
        shown = CM.picture_url(entry)
        if shown is None:
            continue
        if named.title in known:
            continue
        if width < min_width or height < min_height:
            too_small += 1
            continue
        row = {
            "file": named.title,
            "why": named.why,
            "route": named.route,
            "picture_url": shown,
            "original_url": entry.get("url"),
            "width": width,
            "height": height,
        }
        if named.distance_m is not None:
            row["distance_m"] = round(named.distance_m, 1)
        out.append(row)
    if out:
        return SiteResult(
            candidates=out[:MAX_CANDIDATES],
            notes=notes,
            capped=[row["file"] for row in out[MAX_CANDIDATES:]],
        )
    if too_small:
        return SiteResult(
            reason=ALL_TOO_SMALL,
            detail=f"{sid}: {too_small} picture(s) of {name!r}, none reaches {min_width}x{min_height}",
            notes=notes,
        )
    return SiteResult(
        reason=NOT_A_PICTURE, detail=f"{sid}: no still picture of {name!r} on Commons", notes=notes
    )


def candidates(
    commons: Any,
    site: Mapping[str, Any],
    *,
    floor: tuple[int, int],
    exclude: Iterable[str] = (),
    entities: Any | None = None,
) -> tuple[list[dict[str, Any]], str, str]:
    """One site's candidates, and the reason it has none: `(candidates, refusal_reason,
    refusal_detail)`; the reason is `""` when candidates were found."""
    result = site_candidates(commons, site, floor=floor, exclude=exclude, entities=entities)
    return result.candidates, result.reason, result.detail


def run(
    out: Path,
    sites: Sequence[Mapping[str, Any]],
    commons: Any,
    *,
    floor: tuple[int, int],
    exclude: Iterable[str] = (),
    entities: Any | None = None,
    workers: int = 1,
) -> dict[str, Any]:
    """The whole population's candidates, and the refusals, written once into `out`.

    `workers` is the number of sites searched at once, 1 or 2 (`MAX_WORKERS`); Commons' pace is
    one request a second whatever the number (`served_image.commons.Commons._wait`)."""
    if not 1 <= workers <= MAX_WORKERS:
        raise SearchError(f"workers must be 1..{MAX_WORKERS}, not {workers}")
    excluded = list(exclude)

    def search(site: Mapping[str, Any]) -> SiteResult:
        return site_candidates(commons, site, floor=floor, exclude=excluded, entities=entities)

    if workers == 1:
        results = [search(site) for site in sites]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(search, sites))
    rows: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    notes: dict[str, list[str]] = {}
    for site, result in zip(sites, results, strict=True):
        sid = str(site.get("site_id") or "")
        if result.notes:
            notes[sid] = result.notes
        if result.reason:
            refusals.append(
                {
                    "site_id": sid,
                    "reason": result.reason,
                    "detail": result.detail,
                    "notes": result.notes,
                }
            )
            continue
        rows.append(
            {
                "site_id": sid,
                "name": str(site.get("name") or ""),
                "country": str(site.get("country") or ""),
                "floor": {"min_width": floor[0], "min_height": floor[1]},
                "candidates": result.candidates,
                "notes": result.notes,
                "capped": result.capped,
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
    by_route: dict[str, int] = {}
    for row in rows:
        for candidate in row["candidates"]:
            by_route[candidate["route"]] = by_route.get(candidate["route"], 0) + 1
    summary = {
        "sites": len(sites),
        "sites_with_candidates": len(rows),
        "candidates": sum(len(row["candidates"]) for row in rows),
        "candidates_by_route": {route: by_route[route] for route in ROUTES if route in by_route},
        "capped": sum(len(row["capped"]) for row in rows),
        "refused_sites": len(refusals),
        "refusals": {
            reason: sum(1 for r in refusals if r["reason"] == reason)
            for reason in sorted({r["reason"] for r in refusals})
        },
        "notes": {
            note: sum(1 for site_notes in notes.values() for n in site_notes if n == note)
            for note in sorted({n for site_notes in notes.values() for n in site_notes})
        },
        "floor": {"min_width": floor[0], "min_height": floor[1]},
        "hits_per_query": HITS_PER_QUERY,
    }
    (out / SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
