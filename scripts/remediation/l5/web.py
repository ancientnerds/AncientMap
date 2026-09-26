"""L5's web identity and the two reads it makes: the cited pages, and the titles' resolution.

**The User-Agent.** The standing rule of the 2026-09-26 finish: no personal data in any web request,
User-Agent `AncientMapRemediation/1.0 (research)`. Measured 2026-09-26 from this machine: with
`httpx` (the client `opus_audit/quotes.collect` fetches with), `www.wikidata.org` and
`en.wikipedia.org` answer that bare string with HTTP 403 on all four URL shapes L5 reads
(`/w/api.php`, `Special:EntityData/<QID>.json`, `/wiki/<Title>`); with the project's public URL
added they answer 200 (curl and urllib pass the bare string - the refusal is Wikimedia's robot
policy judging the client). WD2 measured and chose the same (`research_web.py` on `wip/wd2`). A URL
of the project is no personal data, so L5 sends `USER_AGENT` below and nothing else that names
anyone.

**The titles.** Every article L5 keeps or writes is resolved the way `refresh_site_external_ids`
resolves a `source_url` title (`pipeline.lyra.prospector.wiki`): the same endpoint and parameters,
parsed by the same `_parse_query` - only the transport is L5's, for the User-Agent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

import httpx

from pipeline.lyra.prospector.wiki import BATCH, WIKIPEDIA_API, _parse_query

USER_AGENT = "AncientMapRemediation/1.0 (research; https://ancientnerds.com)"
TIMEOUT_SECONDS = 60.0

#: The query `resolve_titles` sends (pipeline.lyra.prospector.wiki), parameter for parameter.
QUERY = {
    "action": "query",
    "redirects": "1",
    "prop": "coordinates|pageprops",
    "ppprop": "wikibase_item|disambiguation",
    "format": "json",
    "formatversion": "2",
}

#: `(titles) -> {title: resolution}`, injected so the import is testable without the network.
Resolver = Callable[[list[str]], dict[str, dict[str, Any]]]


def client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=TIMEOUT_SECONDS
    )


def resolution(record: Any) -> dict[str, Any]:
    """A `TitleResolution` as the record L5 keeps (`TITLES.json`)."""
    return {
        "canonical_title": record.canonical_title,
        "qid": record.qid,
        "lat": record.lat,
        "lon": record.lon,
        "disambiguation": record.disambiguation,
        "redirected": record.redirected,
    }


def resolve_titles(titles: Iterable[str], http: httpx.Client) -> dict[str, dict[str, Any]]:
    """Every title resolved on English Wikipedia, 50 per request; a failed request raises."""
    unique = sorted({t for t in titles if t})
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(unique), BATCH):
        chunk = unique[start : start + BATCH]
        response = http.get(WIKIPEDIA_API, params={**QUERY, "titles": "|".join(chunk)})
        response.raise_for_status()
        query: Mapping[str, Any] = response.json()["query"]
        out.update({t: resolution(r) for t, r in _parse_query(chunk, dict(query)).items()})
    return out
