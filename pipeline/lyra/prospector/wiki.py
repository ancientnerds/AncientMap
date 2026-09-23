"""English-Wikipedia title resolution, batched, redirect-following.

One implementation serves both sides of the hard-identifier key: the curated
set's source_url titles (pipeline.lyra.prospector.external_ids) and the
candidates a paper or story names (pipeline.lyra.prospector.resolve). Pushing
BOTH through the same redirect resolution is what makes the key symmetric —
a curated row stored as /wiki/Sudama_Cave and a candidate named "Barabar
Caves" both land on "Barabar Caves" (verified live 2026-09-14).

Endpoint contract (verified live, formatversion=2):
  action=query&redirects=1&prop=coordinates|pageprops&ppprop=wikibase_item|disambiguation
returns `normalized` (underscore/encoding fixes), `redirects` (from→to
chains) and `pages` with `missing`, `invalid` (a title MediaWiki refuses,
with `invalidreason`), `pageprops.wikibase_item`, `pageprops.disambiguation`
and `coordinates[0].{lat,lon}` when present.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass

from pipeline.utils.http import fetch_with_retry

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
BATCH = 50  # API maximum for titles=


@dataclass(frozen=True)
class TitleResolution:
    """Where an input title ended up on English Wikipedia."""

    input_title: str
    canonical_title: str | None  # None when the page does not exist
    qid: str | None
    lat: float | None
    lon: float | None
    disambiguation: bool
    redirected: bool
    globe: str | None = None  # "earth" — anything else is an off-Earth feature

    @property
    def exists(self) -> bool:
        return self.canonical_title is not None


#: C0 controls and DEL - the set migration 0023 keeps out of unified_sites.source_url.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def enwiki_title_from_url(url: str | None) -> str | None:
    """'https://en.wikipedia.org/wiki/Sudama_Cave#Section' -> 'Sudama Cave'.

    A URL or a decoded title that carries a control character raises ValueError. Measured
    2026-09-23: 20 curated source_url values held two URLs joined by a newline, and Petra's became
    the "title" 'Petra\\nhttps://www.khanacademy.org/...' - no page can be named that way.
    """
    if not url:
        return None
    if _CONTROL_RE.search(url):
        raise ValueError(f"a URL with a control character names no page: {url!r}")
    prefix = "https://en.wikipedia.org/wiki/"
    if not url.startswith(prefix):
        return None
    tail = url[len(prefix) :].split("#", 1)[0].split("?", 1)[0]
    title = urllib.parse.unquote(tail).replace("_", " ").strip()
    if _CONTROL_RE.search(title):
        raise ValueError(f"{url!r} decodes to a title with a control character: {title!r}")
    return title or None


def resolve_titles(titles: list[str]) -> dict[str, TitleResolution]:
    """Resolve input titles to their canonical page, QID and coordinates.

    Returns a dict keyed by the INPUT title. Duplicates in `titles` are
    collapsed. Network failures raise (fetch_with_retry) — the caller decides
    whether a batch failure aborts the run; this function never returns a
    partial result dressed up as a full one.
    """
    unique = list(dict.fromkeys(t.strip() for t in titles if t and t.strip()))
    out: dict[str, TitleResolution] = {}
    for i in range(0, len(unique), BATCH):
        chunk = unique[i : i + BATCH]
        resp = fetch_with_retry(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "redirects": 1,
                "prop": "coordinates|pageprops",
                "ppprop": "wikibase_item|disambiguation",
                "titles": "|".join(chunk),
                "format": "json",
                "formatversion": 2,
            },
        )
        query = resp.json().get("query", {})
        out.update(_parse_query(chunk, query))
    return out


def _parse_query(chunk: list[str], query: dict) -> dict[str, TitleResolution]:
    # Chain: input -> normalized -> redirected (possibly several hops) -> page.
    normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
    redirects = {r["from"]: r["to"] for r in query.get("redirects", [])}
    pages = {p["title"]: p for p in query.get("pages", [])}

    result: dict[str, TitleResolution] = {}
    for title in chunk:
        current = normalized.get(title, title)
        redirected = False
        seen = set()
        while current in redirects and current not in seen:
            seen.add(current)
            current = redirects[current]
            redirected = True
        page = pages.get(current)
        # An `invalid` page is a title MediaWiki refuses (it answers with `invalidreason`, no
        # `missing`): no page exists under it. Taking its title as canonical is how Petra's
        # enwiki_title became 'Petra\nhttps://...' (measured live 2026-09-23).
        if page is None or page.get("missing") or page.get("invalid"):
            result[title] = TitleResolution(title, None, None, None, None, False, redirected)
            continue
        props = page.get("pageprops", {}) or {}
        coords = (page.get("coordinates") or [{}])[0]
        result[title] = TitleResolution(
            input_title=title,
            canonical_title=page["title"],
            qid=props.get("wikibase_item"),
            lat=coords.get("lat"),
            lon=coords.get("lon"),
            disambiguation="disambiguation" in props,
            redirected=redirected,
            globe=coords.get("globe"),
        )
    return result
