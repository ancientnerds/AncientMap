"""Everything the owner-case classifier needs from outside this machine - fetched once, cached.

Two kinds of source, both read-only:

* **Production** (`export`): one `SELECT` over the 5,004 curated rows through the project's own ssh +
  psql seam (`mechanical.plan.psql_json_reader`), with each row's Wikidata item and English title from
  `site_external_ids`, its image and content-link counts, and `lat`/`lon`/`geom` as the database prints
  them - the old values a coordinate write is conditioned on.
* **Wikidata and Wikipedia**, through `census.fetch.Fetcher`: the project's `USER_AGENT` (never a
  personal address), its HTTP cache, its retry and back-off. Every batch is a deterministic slice of a
  sorted id list, so a re-run is answered from the cache.

What is fetched, and why:

| file | request | used for |
| --- | --- | --- |
| `wd_names.json` | `wbgetentities` labels/aliases/sitelinks, every linked item | B1 names, duplicates |
| `p31_labels.json` | `wbgetentities` English labels of every P31 class named | container / linear classes |
| `wd_claims.json` | `wbgetentities` claims+sitelinks of the coordinate cases' items | P625 with its references, P189/P195/P276 (museum objects), the enwiki sitelink |
| `enwiki_coords.json` | en.wikipedia `prop=coordinates|pageprops` | the second coordinate witness |

**OpenStreetMap is not a witness in this run.** Overpass (`overpass-api.de`, the endpoint the phase-3
fetch stage uses) answered five queries from this workstation on 2026-09-23 and then reset every
further connection (`WinError 10054` on six attempts, `curl` exit 35 on `/api/status`) - the reset
the remaining-work map already recorded. Asking it from the production VPS would use a production
machine for something other than a read-only `SELECT`, which this action does not do. So the
coordinate witnesses are Wikidata `P625` and the English article, and the independence rule is
strict about those two (`classify.independent`).

A failed request raises (`FetchError`); nothing is recorded as "absent" that was not answered as absent.
A Wikimedia API error in a 200 answer is an error too: a transient one ("too busy", `maxlag`) is asked
again, bounded, with the cache bypassed; any other raises.
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from census.fetch import USER_AGENT, Fetcher, chunked

from bcases import inputs

log = logging.getLogger("bcases.collect")

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
ENWIKI_API = "https://en.wikipedia.org/w/api.php"
#: `wbgetentities` and `prop=coordinates` accept at most 50 ids/titles per request.
BATCH = 50
#: API error codes that mean "ask again later", not "no": the server's own load signals.
TRANSIENT_ERRORS = frozenset({"cirrussearch-too-busy-error", "maxlag", "ratelimited"})
#: How often a transient error is asked again, and the pause before each new ask (seconds).
TRANSIENT_ATTEMPTS = 4
TRANSIENT_PAUSE = 10.0

#: The claims the coordinate witnesses read: the point, and what makes an item a museum-held object.
P_COORD, P_FOUND_AT, P_COLLECTION, P_LOCATION, P_INSTANCE = "P625", "P189", "P195", "P276", "P31"
#: Reference properties that say where a P625 value came from.
P_IMPORTED_FROM, P_STATED_IN, P_IMPORT_URL, P_REF_URL = "P143", "P248", "P4656", "P854"

EXPORT_SQL = """\
SELECT u.id::text AS id, u.name, u.lat, u.lon, u.lat::text AS lat_text, u.lon::text AS lon_text,
       u.geom::text AS geom_text, u.country, u.site_type, u.source_url, u.period_start,
       u.parent_site_id::text AS parent_site_id, u.description, u.created_at::text AS created_at,
       u.scope_status,
       (SELECT e.value FROM site_external_ids e
         WHERE e.site_id = u.id AND e.kind = 'wikidata_qid') AS qid,
       (SELECT e.value FROM site_external_ids e
         WHERE e.site_id = u.id AND e.kind = 'enwiki_title') AS enwiki,
       (SELECT count(*) FROM site_external_ids e WHERE e.site_id = u.id) AS n_ext,
       (SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS n_img,
       (SELECT count(*) FROM site_content_links l WHERE l.site_id = u.id) AS n_links
  FROM unified_sites u
 WHERE u.source_id = 'ancient_nerds'
 ORDER BY u.id"""

#: The curated set's size on 2026-09-23 (read-only count). The export refuses any other number: a
#: partial answer must not become a partial classification.
CURATED_SITES = 5004


def now() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat()


def meta(**extra: Any) -> dict[str, Any]:
    return {"fetched_at": now(), "user_agent": USER_AGENT, **extra}


# ------------------------------------------------------------------------------- production
def export(cache: Path, *, reader: Callable[[str], list[dict[str, Any]]]) -> int:
    """The curated rows, read-only. A site with two items of one kind makes the subquery raise."""
    rows = reader(EXPORT_SQL)
    if len(rows) != CURATED_SITES:
        raise inputs.InputError(
            f"the export returned {len(rows)} curated rows, not {CURATED_SITES}"
        )
    records = {str(row["id"]): row for row in rows}
    inputs.write_cache(
        cache / inputs.EXPORT_FILE, records, {"exported_at": now(), "sql": EXPORT_SQL}
    )
    return len(records)


# ------------------------------------------------------------------------------ the Wikimedia API
def api_json(
    net: Fetcher,
    url: str,
    params: Mapping[str, str],
    *,
    ns: str,
    pause: float = TRANSIENT_PAUSE,
) -> dict[str, Any]:
    """One Wikimedia API answer as JSON. An API error raises; a transient one is asked again first.

    `Fetcher` caches every 2xx answer, and the API reports "too busy" inside a 200 - so the new ask
    bypasses the cache (`force`), or the cached refusal would be read back forever.
    """
    for attempt in range(TRANSIENT_ATTEMPTS):
        payload = net.get_json(url, params=dict(params), ns=ns, force=attempt > 0)
        body = payload.get("json")
        if not isinstance(body, dict):
            raise inputs.InputError(f"{url} answered {dict(params)} with no JSON object")
        error = body.get("error")
        if error is None:
            return body
        if error.get("code") not in TRANSIENT_ERRORS:
            raise inputs.InputError(f"{url} refused {dict(params)}: {error}")
        log.warning("%s: %s - asking again in %.0f s", url, error.get("code"), pause)
        time.sleep(pause)
    raise inputs.InputError(f"{url} stayed busy for {TRANSIENT_ATTEMPTS} asks: {dict(params)}")


def _entities(net: Fetcher, ids: Sequence[str], **params: str) -> dict[str, Any]:
    body = api_json(
        net,
        WIKIDATA_API,
        {"action": "wbgetentities", "ids": "|".join(ids), "format": "json", **params},
        ns="bcases_wikidata",
    )
    entities = body.get("entities")
    if not isinstance(entities, dict):
        raise inputs.InputError(f"wbgetentities answered {ids[:3]}... without an `entities` map")
    absent = [q for q in ids if q not in entities]
    if absent:
        raise inputs.InputError(f"wbgetentities did not answer for {absent[:3]}")
    return entities


def names_record(entity: Mapping[str, Any]) -> dict[str, Any]:
    """Labels, aliases and wiki sitelinks (not Commons) of one entity - its names in every language."""
    return {
        "labels": {k: v["value"] for k, v in (entity.get("labels") or {}).items()},
        "aliases": {k: [a["value"] for a in v] for k, v in (entity.get("aliases") or {}).items()},
        "sitelinks": {
            k: v["title"]
            for k, v in (entity.get("sitelinks") or {}).items()
            if k.endswith("wiki") and k != "commonswiki"
        },
        "missing": "missing" in entity,
    }


def fetch_names(net: Fetcher, qids: Iterable[str]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for chunk in chunked(sorted(set(qids)), BATCH):
        for qid, entity in _entities(net, chunk, props="labels|aliases|sitelinks").items():
            records[qid] = names_record(entity)
    return records


def fetch_labels(net: Fetcher, qids: Iterable[str]) -> dict[str, str | None]:
    records: dict[str, str | None] = {}
    for chunk in chunked(sorted(set(qids)), BATCH):
        for qid, entity in _entities(net, chunk, props="labels", languages="en").items():
            records[qid] = ((entity.get("labels") or {}).get("en") or {}).get("value")
    return records


def _statements(entity: Mapping[str, Any], prop: str) -> list[Mapping[str, Any]]:
    """Non-deprecated statements of `prop`, in Wikidata's order."""
    return [s for s in (entity.get("claims") or {}).get(prop, []) if s.get("rank") != "deprecated"]


def _item_values(entity: Mapping[str, Any], prop: str) -> list[str]:
    out: list[str] = []
    for statement in _statements(entity, prop):
        value = ((statement.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            out.append(str(value["id"]))
    return out


def _reference_values(statement: Mapping[str, Any]) -> dict[str, list[str]]:
    """Where a statement says it came from: P143/P248 items and P4656/P854 URLs, over all references."""
    found: dict[str, list[str]] = {}
    for reference in statement.get("references") or ():
        for prop, snaks in (reference.get("snaks") or {}).items():
            if prop not in (P_IMPORTED_FROM, P_STATED_IN, P_IMPORT_URL, P_REF_URL):
                continue
            for snak in snaks:
                value = (snak.get("datavalue") or {}).get("value")
                text = value.get("id") if isinstance(value, dict) else value
                if text:
                    found.setdefault(prop, []).append(str(text))
    return found


def claims_record(entity: Mapping[str, Any]) -> dict[str, Any]:
    """The coordinate-witness view of one entity: its first non-deprecated P625 with precision, globe
    and references, the museum properties, P31 and its English article."""
    point = None
    coordinates = _statements(entity, P_COORD)
    if coordinates:
        value = ((coordinates[0].get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        if value.get("latitude") is not None:
            point = {
                "lat": float(value["latitude"]),
                "lon": float(value["longitude"]),
                "precision": value.get("precision"),
                "globe": str(value.get("globe") or "").rsplit("/", 1)[-1] or None,
                "references": _reference_values(coordinates[0]),
                "statements": len(coordinates),
            }
    return {
        "missing": "missing" in entity,
        "en_label": ((entity.get("labels") or {}).get("en") or {}).get("value"),
        "p625": point,
        "p31": _item_values(entity, P_INSTANCE),
        "p189": _item_values(entity, P_FOUND_AT),
        "p195": _item_values(entity, P_COLLECTION),
        "p276": _item_values(entity, P_LOCATION),
        "enwiki": ((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title"),
    }


def fetch_claims(net: Fetcher, qids: Iterable[str]) -> dict[str, Any]:
    """Claims of `qids`, then of every find-spot and holding place they name (one hop)."""
    records: dict[str, Any] = {}
    todo = sorted(set(qids))
    for _hop in range(2):
        for chunk in chunked([q for q in todo if q not in records], BATCH):
            for qid, entity in _entities(
                net, chunk, props="claims|sitelinks|labels", languages="en", sitefilter="enwiki"
            ).items():
                records[qid] = claims_record(entity)
        todo = sorted(
            {q for r in records.values() for p in ("p189", "p195", "p276") for q in r[p]}
            - set(records)
        )
    return records


# -------------------------------------------------------------------------------- wikipedia
def fetch_enwiki_coords(net: Fetcher, titles: Iterable[str]) -> dict[str, Any]:
    """Primary coordinates and the item of each English article, keyed by the title asked for.

    Redirects are followed and recorded: a title that is a redirect names another article, and the
    classifier decides whether that article is the item's.
    """
    records: dict[str, Any] = {}
    for chunk in chunked(sorted(set(titles)), BATCH):
        body = api_json(
            net,
            ENWIKI_API,
            {
                "action": "query",
                "prop": "coordinates|pageprops",
                "titles": "|".join(chunk),
                "coprimary": "primary",
                # `colimit` defaults to 10 per request: without it, 40 of 50 pages come back
                # without coordinates and a `continue` - measured 2026-09-23, 131 of 614 pages.
                "colimit": "max",
                "ppprop": "wikibase_item",
                "redirects": "1",
                "format": "json",
                "formatversion": "2",
            },
            ns="bcases_enwiki",
        )
        if "continue" in body:
            raise inputs.InputError(
                f"en.wikipedia answered {chunk[:3]}... in part (`continue`): {body['continue']}"
            )
        query = body.get("query")
        if not isinstance(query, dict):
            raise inputs.InputError(f"en.wikipedia answered {chunk[:3]}... without a `query`")
        hop = {n["from"]: n["to"] for n in query.get("normalized") or ()}
        redirect = {r["from"]: r["to"] for r in query.get("redirects") or ()}
        pages = {p["title"]: p for p in query.get("pages") or ()}
        for title in chunk:
            normal = hop.get(title, title)
            final = redirect.get(normal, normal)
            page = pages.get(final)
            if page is None:
                raise inputs.InputError(f"en.wikipedia did not answer for {title!r}")
            coords = page.get("coordinates") or []
            records[title] = {
                "title": final,
                "redirected": final != normal,
                "missing": bool(page.get("missing")),
                "wikibase_item": (page.get("pageprops") or {}).get("wikibase_item"),
                "lat": coords[0]["lat"] if coords else None,
                "lon": coords[0]["lon"] if coords else None,
                "globe": coords[0].get("globe") if coords else None,
            }
    return records
