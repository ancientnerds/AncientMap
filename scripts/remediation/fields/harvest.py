"""The shared, read-only field harvest: what Wikidata and Wikipedia say about every curated site.

FINISH_PLAN_2026-09-26 workstream WD ("mechanical Wikidata/Wikipedia harvest -> per-field status").
Lane WD1 (coordinates, period, site type, source URL) and lane WD2 read these files; **the layout is
a contract between the two lanes and does not change**:

    <root>/SITES.jsonl            one line per curated site, sorted by id, exactly the keys
                                  site_id, name, country, lat, lon, qid (or null),
                                  enwiki_title (or null), source_url
    <root>/entities/<QID>.json    the raw `wbgetentities` entity of the site's item, as served
                                  (every property: claims, sitelinks, labels, descriptions, aliases)
    <root>/CLASSES.json           every class an item names in P31: English label and P279 parents
    <root>/enwiki/<QID>.json      the item's English article (its enwiki sitelink): the page's
                                  primary coordinates (`prop=coordinates`) and its own item
    <root>/urls/<site_id>.json    the stored source_url, asked once: a Wikipedia article resolved
                                  through that wiki's API (redirect, fragment, missing, its item),
                                  any other page by one GET (status, redirect chain, final URL,
                                  <title>), or why it was not asked
    <root>/HARVEST.json           when and how: the export's SQL and clock, the sample (if any),
                                  the User-Agent, and each fetch step's counts
    <root>/cache/                 the HTTP cache of the API answers (`census.fetch.Fetcher`)

**Where the site's item comes from.** Measured read-only on production 2026-09-26: the verified
Wikidata item of a curated site lives in `site_external_ids` (`kind = 'wikidata_qid'`, beside
`enwiki_title`): 4,633 of the 5,004 curated sites, one row each; 4,564 of the 4,926 not retired.
`card_stats.wikidata_qid` is NULL on every curated card (0 rows) and `raw_data` holds no item key
(its only keys are `_description_provenance` and `description_citations`). The rows are derived
from each site's `source_url` (`pipeline/lyra/prospector/external_ids.py`) and were repaired by the
external-id waves (`output/remediation/tools/qid_repair.py`, journalled 2026-09-22/23); the
other-language sitelink pilot failed its threshold and wrote nothing. So the export reads the item
from `site_external_ids` and nowhere else.

**Read-only, everywhere.** Production is asked one `SELECT` (`export`); the web is asked with GET
only, through httpx, with the User-Agent `USER_AGENT` - the project's public URL as its contact
(Wikimedia's User-Agent policy), no personal data. Wikimedia API answers go
through `census.fetch.Fetcher` (its cache, its retry and back-off) and `bcases.collect.api_json`
(an API error in a 200 raises; a transient one is asked again), one request at a time, `pace`
seconds apart. Other hosts are asked once each, `pace` seconds apart per host. **Resumable:** every
per-item and per-site file is written once and skipped on the next run (`--refetch-failed` asks the
failed source URLs again); a run that stops leaves only complete files behind (each file is written
to a temporary name and renamed).

A failed Wikimedia request raises and stops the run - nothing is recorded as absent that was not
answered as absent. A source page that cannot be read is recorded with its status or error: that is
the finding (`classify.py` reads a 404 as dead, a 403 as unverifiable by machine). A host behind bot
protection is not worked around: whc.unesco.org answers httpx with a Cloudflare challenge (403 "Just
a moment...", measured 2026-09-26) and is recorded as that 403, like Historic England's refusal.

**The agent, measured 2026-09-26 (httpx, this workstation).** Wikimedia answers an agent without a
contact (`AncientMapRemediation/1.0 (research)`) with `403 Please respect our robot policy` on the
API and on the article pages alike; `USER_AGENT`, which names the project's public site, gets 200
from en/de.wikipedia (API and pages) and www.wikidata.org. curl got 200 with both agents.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import random
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from bcases.collect import (  # noqa: E402 - the Wikimedia API seam, never copied
    WIKIDATA_API,
    api_json,
    fetch_enwiki_coords,
)
from census.fetch import Fetcher, chunked  # noqa: E402
from mechanical.plan import _claims, psql_json_reader  # noqa: E402
from phase4.route_stage import wikipedia_title  # noqa: E402 - `(lang, title)` of an article URL

from pipeline.lyra.prospector.wiki import CONTROL_RE  # noqa: E402 - migration 0023's control set
from pipeline.utils.http import is_public_http_url  # noqa: E402 - Lyra's own SSRF check

log = logging.getLogger("fields.harvest")

#: The only User-Agent the WD1 lane sends - the harvest and the quote check alike. The FINISH_PLAN
#: standing rule allows no personal data in any web request (no e-mail address, no name); Wikimedia's
#: User-Agent policy asks for a contact, so the agent names the project's public site.
USER_AGENT = "AncientMapRemediation/1.0 (https://ancientnerds.com; research)"
DEFAULT_ROOT = REPO / "output" / "remediation" / "fields" / "harvest"

SITES_FILE = "SITES.jsonl"
META_FILE = "HARVEST.json"
CLASSES_FILE = "CLASSES.json"
ENTITIES = "entities"
ENWIKI = "enwiki"
URLS = "urls"
CACHE = "cache"
#: The keys of a SITES.jsonl line, in this order - the contract WD2 reads.
SITE_KEYS = ("site_id", "name", "country", "lat", "lon", "qid", "enwiki_title", "source_url")
#: `wbgetentities` and the MediaWiki `titles=` accept at most 50 per request.
BATCH = 50
#: Seconds between two requests to one host - a chosen courtesy, not a measured limit.
PACE_SECONDS = 1.0
TIMEOUT_SECONDS = 60.0
#: How much of a page's <title> is kept.
TITLE_CHARS = 300
P_INSTANCE, P_SUBCLASS = "P31", "P279"

_QID = re.compile(r"Q[1-9][0-9]*\Z")
_TITLE = re.compile(rb"<title[^>]*>(.*?)</title\s*>", re.IGNORECASE | re.DOTALL)
#: Hosts whose URLs are not a source about a site: a search or map query, a machine translation
#: proxy of someone else's page. Recorded as `not-a-source`, never fetched.
NOT_A_SOURCE = re.compile(
    r"(?:^|\.)(?:google\.[a-z]{2,3}(?:\.[a-z]{2})?|bing\.com|duckduckgo\.com|translate\.goog)\Z"
)

# the kinds of a source_url record
URL_NONE = "none"
URL_WIKIPEDIA = "wikipedia"
URL_WEB = "web"
URL_NOT_A_SOURCE = "not-a-source"
URL_NOT_PUBLIC = "not-public"
URL_MALFORMED = "malformed"

EXPORT_SQL = """\
SELECT u.id::text AS site_id, u.name, u.country, u.lat, u.lon,
       (SELECT e.value FROM site_external_ids e
         WHERE e.site_id = u.id AND e.kind = 'wikidata_qid') AS qid,
       (SELECT e.value FROM site_external_ids e
         WHERE e.site_id = u.id AND e.kind = 'enwiki_title') AS enwiki_title,
       u.source_url, u.scope_status
  FROM unified_sites u
 WHERE u.source_id = 'ancient_nerds'
 ORDER BY u.id"""


class HarvestError(RuntimeError):
    """The harvest cannot go on from this state. Nothing half-written is left behind."""


def now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _write_json(path: Path, data: Any) -> None:
    """Written whole or not at all: a temporary name, then an atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------ the sites
def site_line(row: Mapping[str, Any]) -> dict[str, Any]:
    """One SITES.jsonl line from an export row: exactly `SITE_KEYS`, the item checked."""
    qid = row["qid"]
    if qid is not None and not _QID.match(str(qid)):
        raise HarvestError(f"{row['site_id']}: {qid!r} is not a Wikidata item id")
    return {
        "site_id": str(row["site_id"]),
        "name": str(row["name"]),
        "country": row["country"],
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "qid": None if qid is None else str(qid),
        "enwiki_title": row["enwiki_title"],
        "source_url": row["source_url"],
    }


def choose_sample(rows: Sequence[Mapping[str, Any]], size: int, seed: int) -> list[str]:
    """`size` ids drawn from the sites that are not retired, reproducibly (`random.Random(seed)`
    over the sorted ids)."""
    pool = sorted(str(r["site_id"]) for r in rows if r["scope_status"] != "retired")
    if size > len(pool):
        raise HarvestError(f"a sample of {size} from {len(pool)} sites that are not retired")
    return sorted(random.Random(seed).sample(pool, size))  # noqa: S311 - a seeded draw, not a key


def export(
    root: Path,
    *,
    reader: Callable[[str], list[dict[str, Any]]],
    sample: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """SITES.jsonl from one read-only SELECT: every curated site, or a reproducible sample of the
    ones not retired. HARVEST.json records the SQL, the clock and the sample."""
    rows = reader(EXPORT_SQL)
    if not rows:
        raise HarvestError("the export returned no curated site - refusing an empty harvest")
    exported_at = now()
    chosen = None if sample is None else set(choose_sample(rows, sample, int(seed or 0)))
    lines = [site_line(r) for r in rows if chosen is None or str(r["site_id"]) in chosen]
    lines.sort(key=lambda line: line["site_id"])
    root.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    tmp = root / (SITES_FILE + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(root / SITES_FILE)
    meta = {
        "exported_at": exported_at,
        "sql": EXPORT_SQL,
        "user_agent": USER_AGENT,
        "population": {
            "curated": len(rows),
            "retired": sum(1 for r in rows if r["scope_status"] == "retired"),
            "with_qid": sum(1 for r in rows if r["qid"] is not None),
        },
        "sample": None if sample is None else {"size": sample, "seed": seed},
        "sites": len(lines),
        "steps": {},
    }
    _write_json(root / META_FILE, meta)
    return {"sites": len(lines), **meta["population"]}


def read_sites(root: Path) -> list[dict[str, Any]]:
    """SITES.jsonl, each line checked to carry exactly the contract's keys."""
    path = root / SITES_FILE
    if not path.exists():
        raise HarvestError(f"{path} is missing - run `harvest.py export` first")
    out = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = json.loads(raw)
        if tuple(line) != SITE_KEYS:
            raise HarvestError(f"{path}:{number} carries {list(line)}, not {list(SITE_KEYS)}")
        out.append(line)
    return out


def _record_step(root: Path, step: str, counts: Mapping[str, Any]) -> None:
    meta = _read_json(root / META_FILE)
    meta["steps"][step] = {"finished_at": now(), **counts}
    _write_json(root / META_FILE, meta)


# ------------------------------------------------------------------------------ the items
def entity_path(root: Path, qid: str) -> Path:
    if not _QID.match(qid):
        raise HarvestError(f"{qid!r} is not a Wikidata item id")
    return root / ENTITIES / f"{qid}.json"


def load_entity(root: Path, qid: str) -> dict[str, Any]:
    """The entity harvested for `qid`; a missing file raises (harvest it first)."""
    path = entity_path(root, qid)
    if not path.exists():
        raise HarvestError(f"{path} is missing - run `harvest.py fetch` first")
    return _read_json(path)


def _answered(asked: Sequence[str], entities: Mapping[str, Any]) -> dict[str, Any]:
    """The entity for each asked id. A merged item is answered under the id it redirects to, with
    `redirects.from` naming the asked one; an id answered by neither raises."""
    out: dict[str, Any] = {}
    by_origin = {
        str(e["redirects"]["from"]): e
        for e in entities.values()
        if isinstance(e, dict) and isinstance(e.get("redirects"), dict)
    }
    for qid in asked:
        entity = entities.get(qid) or by_origin.get(qid)
        if not isinstance(entity, dict):
            raise HarvestError(f"wbgetentities did not answer for {qid}")
        out[qid] = entity
    return out


def fetch_entities(
    net: Fetcher,
    root: Path,
    qids: Iterable[str],
    *,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, int]:
    """Every item not yet harvested, 50 per request, each written to its own file as served."""
    wanted = sorted(set(qids))
    todo = [q for q in wanted if not entity_path(root, q).exists()]
    for number, chunk in enumerate(chunked(todo, BATCH)):
        if number:
            sleep(pace)
        body = api_json(
            net,
            WIKIDATA_API,
            {"action": "wbgetentities", "ids": "|".join(chunk), "format": "json"},
            ns="fields_wikidata",
        )
        entities = body.get("entities")
        if not isinstance(entities, dict):
            raise HarvestError(f"wbgetentities answered {chunk[:3]}... without an `entities` map")
        for qid, entity in _answered(chunk, entities).items():
            _write_json(entity_path(root, qid), entity)
        log.info("entities: %d of %d", min((number + 1) * BATCH, len(todo)), len(todo))
    return {"items": len(wanted), "fetched": len(todo), "cached": len(wanted) - len(todo)}


def item_ids(entity: Mapping[str, Any], prop: str) -> list[str]:
    """The items named by the non-deprecated statements of `prop`, in Wikidata's order."""
    out: list[str] = []
    for statement in _claims(entity, prop):
        value = ((statement.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            out.append(str(value["id"]))
    return out


def fetch_classes(
    net: Fetcher,
    root: Path,
    qids: Iterable[str],
    *,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, int]:
    """English label and P279 parents of every class the harvested items name in P31."""
    path = root / CLASSES_FILE
    known: dict[str, Any] = _read_json(path) if path.exists() else {}
    classes = sorted(
        {c for q in set(qids) for c in item_ids(load_entity(root, q), P_INSTANCE)} - set(known)
    )
    for number, chunk in enumerate(chunked(classes, BATCH)):
        if number:
            sleep(pace)
        body = api_json(
            net,
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(chunk),
                "props": "labels|claims",
                "languages": "en",
                "format": "json",
            },
            ns="fields_wikidata_classes",
        )
        for qid, entity in _answered(chunk, body.get("entities") or {}).items():
            known[qid] = {
                "label": ((entity.get("labels") or {}).get("en") or {}).get("value"),
                "p279": item_ids(entity, P_SUBCLASS),
            }
    _write_json(path, known)
    return {"classes": len(known), "fetched": len(classes)}


# ------------------------------------------------------------------------------ the articles
def enwiki_path(root: Path, qid: str) -> Path:
    return root / ENWIKI / f"{entity_path(root, qid).stem}.json"


def enwiki_sitelink(entity: Mapping[str, Any]) -> str | None:
    return ((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title")


def fetch_enwiki(
    net: Fetcher,
    root: Path,
    qids: Iterable[str],
    *,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, int]:
    """The primary coordinates of each item's English article (`bcases.collect.
    fetch_enwiki_coords`: redirects followed and recorded), one file per item that has one."""
    titles: dict[str, str] = {}
    for qid in sorted(set(qids)):
        title = enwiki_sitelink(load_entity(root, qid))
        if title is not None and not enwiki_path(root, qid).exists():
            titles[qid] = title
    by_title: dict[str, list[str]] = {}
    for qid, title in titles.items():
        by_title.setdefault(title, []).append(qid)
    for number, chunk in enumerate(chunked(sorted(by_title), BATCH)):
        if number:
            sleep(pace)
        for title, record in fetch_enwiki_coords(net, chunk).items():
            for qid in by_title[title]:
                _write_json(
                    enwiki_path(root, qid),
                    {"qid": qid, "sitelink": title, "fetched_at": now(), **record},
                )
    return {"articles": len(titles)}


def load_enwiki(root: Path, qid: str) -> dict[str, Any] | None:
    """The item's article record, or None when the item has no English article."""
    path = enwiki_path(root, qid)
    return _read_json(path) if path.exists() else None


# ------------------------------------------------------------------------------ the source URLs
def url_path(root: Path, site_id: str) -> Path:
    return root / URLS / f"{site_id}.json"


def load_url(root: Path, site: Mapping[str, Any]) -> dict[str, Any]:
    """The record of the site's source_url - refused when it records another URL than the site's
    SITES.jsonl line holds (an export taken after the fetch): fetch again first."""
    path = url_path(root, str(site["site_id"]))
    if not path.exists():
        raise HarvestError(f"{path} is missing - run `harvest.py fetch` first")
    record = _read_json(path)
    if record["source_url"] != site["source_url"]:
        raise HarvestError(
            f"{path} records {record['source_url']!r}, the site holds {site['source_url']!r} - "
            "run `harvest.py fetch` again"
        )
    return record


def url_kind(url: str | None) -> str:
    """How a stored source_url is asked: not at all (`none`, `malformed`, `not-public`,
    `not-a-source`), through its wiki's API (`wikipedia`), or with one GET (`web`)."""
    if url is None or not url.strip():
        return URL_NONE
    if CONTROL_RE.search(url) or urlsplit(url).scheme not in ("http", "https"):
        return URL_MALFORMED
    host = (urlsplit(url).hostname or "").lower()
    if NOT_A_SOURCE.search(host):
        return URL_NOT_A_SOURCE
    if not is_public_http_url(url):
        return URL_NOT_PUBLIC
    if wikipedia_title(url) is not None:
        return URL_WIKIPEDIA
    return URL_WEB


def resolve_wiki_titles(net: Fetcher, lang: str, titles: Sequence[str]) -> dict[str, Any]:
    """Each title of one Wikipedia, resolved: its redirect (and the section it points into), a
    missing or invalid page, the item of the page it ends at."""
    body = api_json(
        net,
        f"https://{lang}.wikipedia.org/w/api.php",
        {
            "action": "query",
            "prop": "pageprops",
            "ppprop": "wikibase_item|disambiguation",
            "titles": "|".join(titles),
            "redirects": "1",
            "format": "json",
            "formatversion": "2",
        },
        ns=f"fields_{lang}wiki",
    )
    query = body.get("query")
    if not isinstance(query, dict):
        raise HarvestError(f"{lang}.wikipedia answered {list(titles)[:3]}... without a `query`")
    hop = {n["from"]: n["to"] for n in query.get("normalized") or ()}
    redirects = {r["from"]: r for r in query.get("redirects") or ()}
    pages = {p["title"]: p for p in query.get("pages") or ()}
    out: dict[str, Any] = {}
    for title in titles:
        normal = hop.get(title, title)
        redirect = redirects.get(normal)
        final = redirect["to"] if redirect else normal
        page = pages.get(final)
        if page is None:
            raise HarvestError(f"{lang}.wikipedia did not answer for {title!r}")
        out[title] = {
            "lang": lang,
            "title": title,
            "resolved_title": final,
            "redirected": redirect is not None,
            "fragment": (redirect or {}).get("tofragment"),
            "missing": bool(page.get("missing")),
            "invalid": bool(page.get("invalid")),
            "wikibase_item": (page.get("pageprops") or {}).get("wikibase_item"),
            "disambiguation": "disambiguation" in (page.get("pageprops") or {}),
        }
    return out


def page_title(body: bytes, encoding: str | None) -> str | None:
    """The page's <title>, unescaped and with its whitespace collapsed, or None."""
    match = _TITLE.search(body)
    if match is None:
        return None
    text = match.group(1).decode(encoding or "utf-8", errors="replace")
    return " ".join(html.unescape(text).split())[:TITLE_CHARS] or None


def get_page(client: httpx.Client, url: str) -> dict[str, Any]:
    """One GET, redirects followed: the status, every hop, the final URL, the <title>. A failed
    request is recorded with its error - that is the finding, not a reason to stop."""
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        return {"status": None, "error": f"{type(exc).__name__}: {exc}", "hops": []}
    hops = [str(r.url) for r in response.history]
    content_type = response.headers.get("Content-Type", "")
    title = None
    if "html" in content_type.lower():
        title = page_title(response.content, response.encoding)
    return {
        "status": response.status_code,
        "final_url": str(response.url),
        "hops": hops,
        "content_type": content_type,
        "page_title": title,
        "error": None,
    }


def fetch_urls(
    net: Fetcher,
    client: httpx.Client,
    root: Path,
    sites: Sequence[Mapping[str, Any]],
    *,
    refetch_failed: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    pace: float = PACE_SECONDS,
) -> dict[str, int]:
    """One record per site's stored source_url (`url_kind`); every record written once - and
    asked again when the site's source_url is no longer the one it records (an export taken after
    a write, e.g. after the link wave L5)."""

    def due(site: Mapping[str, Any]) -> bool:
        path = url_path(root, str(site["site_id"]))
        if not path.exists():
            return True
        record = _read_json(path)
        if record["source_url"] != site["source_url"]:
            return True
        failed = record.get("error") or (record.get("status") or 0) >= 500
        return bool(refetch_failed and record["kind"] == URL_WEB and failed)

    todo = [s for s in sites if due(s)]
    kinds = Counter()
    wiki: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    last: dict[str, float] = {}
    for site in todo:
        url = site["source_url"]
        kind = url_kind(url)
        kinds[kind] += 1
        base = {"site_id": site["site_id"], "source_url": url, "kind": kind}
        if kind == URL_WIKIPEDIA:
            lang, title = wikipedia_title(url) or ("", "")
            wiki.setdefault(lang, {}).setdefault(title, []).append(site)
            continue
        if kind != URL_WEB:
            _write_json(url_path(root, site["site_id"]), {**base, "fetched_at": now()})
            continue
        host = urlsplit(url).hostname or ""
        if host in last and last[host] + pace > clock():
            sleep(last[host] + pace - clock())
        last[host] = clock()
        record = {**base, **get_page(client, url), "fetched_at": now()}
        _write_json(url_path(root, site["site_id"]), record)
    for number, (lang, by_title) in enumerate(sorted(wiki.items())):
        for part, chunk in enumerate(chunked(sorted(by_title), BATCH)):
            if number or part:
                sleep(pace)
            for title, resolved in resolve_wiki_titles(net, lang, chunk).items():
                for site in by_title[title]:
                    url = site["source_url"]
                    record = {
                        "site_id": site["site_id"],
                        "source_url": url,
                        "kind": URL_WIKIPEDIA,
                        "url_fragment": urlsplit(url).fragment or None,
                        **resolved,
                        "fetched_at": now(),
                    }
                    _write_json(url_path(root, site["site_id"]), record)
    return {"asked": len(todo), **dict(sorted(kinds.items()))}


# ------------------------------------------------------------------------------ the dating sources
# D70 (2026-11-05, `dating.py`): what the dating extractor reads beyond the files above, fetched for
# the sites it is run on (`fetch-dating --sites FILE`) and kept in two directories of their own - the
# contract's files keep their layout:
#
#     <root>/wikitext/<lang>/<revid>.json   the wikitext of a cached article at the revision the
#                                           Wikipedia cache read (`fields/wiki.py`), 50 revisions per
#                                           request; keyed by the revision, the one thing the cache's
#                                           page and the fetch share
#     <root>/wikis/<lang>/<QID>.json        the plain-text extract of the item's article in each
#                                           readable language (`READ_LANGS`), one per request
#     <root>/ITEM_LABELS.json               the English label of every item a P2348 (time period)
#                                           or P793 (significant event) claim names
#
# Wikimedia throttles this office IP from four parallel clients on (2026-10-07): every step here is
# serial, `pace` >= 1 s apart, and refused below that.
WIKITEXT = "wikitext"
WIKIS = "wikis"
ITEM_LABELS_FILE = "ITEM_LABELS.json"
#: The Wikipedias the extractor reads besides English: the languages `dates.py` reads.
READ_LANGS = (
    "de", "fr", "es", "it", "pt", "nl", "pl", "ru", "uk", "cs", "sk", "sl", "hr", "sr", "sh", "bs",
    "mk", "bg", "hu", "el", "tr", "ro", "ca", "sv", "da", "no", "fi", "id",
)  # fmt: skip
LABEL_PROPS = ("P2348", "P793")
MIN_DATING_PACE = 1.0
#: Hosts a cited page is not read from as tier 4: their own tiers read them (Wikipedia, Wikidata,
#: Commons) or they are no source at all (`rule.FORBIDDEN_FAMILIES`).
_OWN_TIER_HOSTS = re.compile(r"(?:^|\.)(?:wikipedia\.org|wikidata\.org|wikimedia\.org)\Z")


def _paced(pace: float) -> None:
    if pace < MIN_DATING_PACE:
        raise HarvestError(f"pace {pace}: Wikimedia is asked at most once a second (serially)")


def wikitext_path(root: Path, lang: str, revid: Any) -> Path:
    if not re.fullmatch(r"[a-z-]{2,12}", lang) or not re.fullmatch(r"\d+", str(revid)):
        raise HarvestError(f"{lang!r}/{revid!r} is no Wikipedia language and revision")
    return root / WIKITEXT / lang / f"{revid}.json"


def load_wikitext(root: Path, lang: str, revid: Any) -> str | None:
    """The wikitext of a cached revision - None when Wikipedia answered it as gone (a deleted or
    suppressed revision); a revision never asked raises (`fetch-dating` first)."""
    path = wikitext_path(root, lang, revid)
    if not path.exists():
        raise HarvestError(f"{path} is missing - run `harvest.py fetch-dating` first")
    record = _read_json(path)
    return None if record.get("missing") else str(record["wikitext"])


def fetch_wikitext(
    net: Fetcher,
    root: Path,
    pages: Iterable[tuple[str, Any]],
    *,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, int]:
    """The wikitext of each `(lang, revid)` not yet on disk, 50 revisions per request
    (`prop=revisions&revids=a|b|..&rvslots=main`); a revision answered as bad is recorded missing."""
    _paced(pace)
    todo: dict[str, list[str]] = {}
    for lang, revid in sorted({(str(lang), str(revid)) for lang, revid in pages}):
        if not wikitext_path(root, lang, revid).exists():
            todo.setdefault(lang, []).append(revid)
    asked = 0
    for lang, revids in sorted(todo.items()):
        for chunk in chunked(revids, BATCH):
            if asked:
                sleep(pace)
            asked += 1
            body = api_json(
                net,
                f"https://{lang}.wikipedia.org/w/api.php",
                {
                    "action": "query",
                    "prop": "revisions",
                    "revids": "|".join(chunk),
                    "rvprop": "ids|content",
                    "rvslots": "main",
                    "format": "json",
                    "formatversion": "2",
                },
                ns=f"fields_{lang}wiki_wikitext",
            )
            query = body.get("query") or {}
            found: dict[str, dict[str, Any]] = {}
            for page in query.get("pages") or ():
                for revision in page.get("revisions") or ():
                    content = ((revision.get("slots") or {}).get("main") or {}).get("content")
                    found[str(revision["revid"])] = {
                        "lang": lang,
                        "revid": int(revision["revid"]),
                        "title": page.get("title"),
                        "wikitext": content,
                        "missing": content is None,
                    }
            bad = {str(b.get("revid")) for b in query.get("badrevids", {}).values()} if isinstance(
                query.get("badrevids"), dict) else set()  # fmt: skip
            for revid in chunk:
                if revid in found:
                    record = found[revid]
                elif revid in bad:
                    record = {"lang": lang, "revid": int(revid), "missing": True}
                else:
                    raise HarvestError(f"{lang}.wikipedia did not answer for revision {revid}")
                _write_json(wikitext_path(root, lang, revid), {**record, "fetched_at": now()})
    return {"revisions": sum(len(v) for v in todo.values()), "requests": asked}


def fetch_item_labels(
    net: Fetcher,
    root: Path,
    qids: Iterable[str],
    *,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, int]:
    """The English label of every item the harvested items name in `LABEL_PROPS` (ITEM_LABELS.json)."""
    _paced(pace)
    path = root / ITEM_LABELS_FILE
    known: dict[str, Any] = _read_json(path) if path.exists() else {}
    wanted = sorted(
        {i for q in set(qids) for prop in LABEL_PROPS for i in item_ids(load_entity(root, q), prop)}
        - set(known)
    )
    for number, chunk in enumerate(chunked(wanted, BATCH)):
        if number:
            sleep(pace)
        body = api_json(
            net,
            WIKIDATA_API,
            {"action": "wbgetentities", "ids": "|".join(chunk), "props": "labels",
             "languages": "en", "format": "json"},  # fmt: skip
            ns="fields_wikidata_item_labels",
        )
        for qid, entity in _answered(chunk, body.get("entities") or {}).items():
            known[qid] = {"label": ((entity.get("labels") or {}).get("en") or {}).get("value")}
    _write_json(path, known)
    return {"items": len(known), "fetched": len(wanted)}


def wikis_path(root: Path, lang: str, qid: str) -> Path:
    if lang not in READ_LANGS:
        raise HarvestError(f"{lang!r} is not a language the dating extractor reads")
    return root / WIKIS / lang / f"{entity_path(root, qid).stem}.json"


def read_sitelinks(entity: Mapping[str, Any]) -> list[tuple[str, str]]:
    """`(lang, title)` of the item's articles in `READ_LANGS`, in that order."""
    links = entity.get("sitelinks") or {}
    out = []
    for lang in READ_LANGS:
        title = (links.get(f"{lang}wiki") or {}).get("title")
        if title:
            out.append((lang, str(title)))
    return out


def load_wikis(
    root: Path, qid: str, entity: Mapping[str, Any], *, skip: frozenset[str] = frozenset()
) -> list[tuple[str, dict[str, Any]]]:
    """The item's other-language articles as fetched, in `READ_LANGS` order, but the languages in
    `skip` (the Wikipedia cache holds them); a sitelink never fetched raises (`fetch-dating` first)."""
    out = []
    for lang, _title in read_sitelinks(entity):
        if lang in skip:
            continue
        path = wikis_path(root, lang, qid)
        if not path.exists():
            raise HarvestError(f"{path} is missing - run `harvest.py fetch-dating` first")
        out.append((lang, _read_json(path)))
    return out


def fetch_wikis(
    net: Fetcher,
    root: Path,
    qids: Iterable[str],
    *,
    skip: Mapping[str, frozenset[str]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, int]:
    """The plain-text extract (sections as `== Heading ==` lines) and the latest revision of each
    item's article in `READ_LANGS`, one request per article, serially. `skip[qid]` names the
    languages the Wikipedia cache already holds for the item's site."""
    _paced(pace)
    skip = skip or {}
    asked = 0
    for qid in sorted(set(qids)):
        for lang, title in read_sitelinks(load_entity(root, qid)):
            path = wikis_path(root, lang, qid)
            if path.exists() or lang in skip.get(qid, frozenset()):
                continue
            if asked:
                sleep(pace)
            asked += 1
            body = api_json(
                net,
                f"https://{lang}.wikipedia.org/w/api.php",
                {"action": "query", "prop": "extracts|info", "explaintext": "1",
                 "exsectionformat": "wiki", "titles": title, "redirects": "1", "format": "json",
                 "formatversion": "2"},  # fmt: skip
                ns=f"fields_{lang}wiki_extract",
            )
            pages = (body.get("query") or {}).get("pages") or []
            if len(pages) != 1:
                raise HarvestError(f"{lang}.wikipedia answered {title!r} with {len(pages)} pages")
            page = pages[0]
            _write_json(
                path,
                {
                    "qid": qid,
                    "lang": lang,
                    "sitelink": title,
                    "title": page.get("title"),
                    "revid": page.get("lastrevid"),
                    "missing": bool(page.get("missing")) or page.get("extract") is None,
                    "text": page.get("extract"),
                    "fetched_at": now(),
                },
            )
    return {"requests": asked}


def cited_page_refs(fields_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Tier 4 of the extractor: per site, the non-Wikipedia pages the answers of the field runs under
    `fields_dir` cited (their DECISIONS.jsonl quotes, the adversarial re-check's too) whose fetch is
    kept (PAGES.jsonl and `pages/` of any run, status 200). A page of a forbidden family
    (`rule.FORBIDDEN_FAMILIES`) or of Wikipedia, Wikidata or Commons is never one. Each ref names
    its body; `page_text` reads it."""
    from fields import answers as A
    from fields import rule as R

    stored: dict[str, dict[str, Any]] = {}
    for index in sorted(fields_dir.glob("*/PAGES.jsonl")) + sorted(fields_dir.glob("*/*/PAGES.jsonl")):
        for raw in index.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            meta = json.loads(raw)
            body = index.parent / "pages" / f"{meta['key']}.body"
            if meta.get("status") == 200 and body.exists() and meta["url"] not in stored:
                stored[meta["url"]] = {
                    "url": meta["url"],
                    "body": body,
                    "content_type": meta.get("content_type") or "",
                    "fetched_at": meta.get("fetched_at"),
                }
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for decisions in sorted(fields_dir.glob("*/DECISIONS.jsonl")):
        for raw in decisions.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            quotes = list(row.get("quotes") or ())
            adversarial = row.get("adversarial")
            if isinstance(adversarial, dict):
                quotes += list(adversarial.get("quotes") or ())
                # a rejected cell keeps the researcher's answer, quotes and all, in `original`
                original = adversarial.get("original")
                if isinstance(original, dict):
                    quotes += list(original.get("quotes") or ())
            for quote in quotes:
                url = str(quote.get("source") or "").replace("&amp;", "&")
                host = (urlsplit(url).hostname or "").lower()
                if url not in stored or _OWN_TIER_HOSTS.search(host):
                    continue
                if A.family_of(url, R.EXTRACT) in R.FORBIDDEN_FAMILIES:
                    continue
                out.setdefault(str(row["site_id"]), {})[url] = stored[url]
    return {site: [refs[u] for u in sorted(refs)] for site, refs in out.items()}


def page_text(ref: Mapping[str, Any]) -> str | None:
    """A cited page's text as the quote check reads it (`opus_audit/quotes.page_source`: HTML as its
    visible text, a PDF through pdftotext), or None when it cannot be read."""
    from opus_audit import quotes as Q

    source = Q.page_source(str(ref["content_type"]), Path(ref["body"]).read_bytes())
    if source.failure or not source.texts:
        return None
    return source.texts[0][1]


def read_site_ids(path: Path) -> list[str]:
    """`--sites FILE`: JSON lines that carry a `site_id` (the run's UNDATED.jsonl, a gold's
    GOLD.jsonl and DEV.jsonl)."""
    if not path.exists():
        raise HarvestError(f"{path} is missing")
    ids = [str(json.loads(raw)["site_id"]) for raw in path.read_text(encoding="utf-8").splitlines()
           if raw.strip()]  # fmt: skip
    if not ids:
        raise HarvestError(f"{path} names no site")
    return sorted(set(ids))


def fetch_dating(
    root: Path,
    *,
    net: Fetcher,
    site_ids: Sequence[str],
    wiki_cache: Any,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, Any]:
    """The dating extractor's sources for `site_ids` (the harvest's entities fetched before):
    the item labels, the wikitext of each cached article's revision, the other-language extracts.
    Each step resumable and recorded in HARVEST.json."""
    _paced(pace)
    by_id = {s["site_id"]: s for s in read_sites(root)}
    unknown = sorted(set(site_ids) - set(by_id))
    if unknown:
        raise HarvestError(f"{len(unknown)} site(s) are not in {root / SITES_FILE}: {unknown[:3]}")
    qids = sorted({by_id[s]["qid"] for s in site_ids if by_id[s]["qid"]})
    pages = [(str(p["lang"]), p["revid"]) for s in site_ids for p in wiki_cache.pages(s)
             if not p.get("missing") and p.get("revid")]  # fmt: skip
    cached: dict[str, set[str]] = {}
    for s in site_ids:
        if by_id[s]["qid"]:
            cached.setdefault(by_id[s]["qid"], set()).update(str(p["lang"]) for p in wiki_cache.pages(s))
    result: dict[str, Any] = {}
    for step, work in (
        ("item_labels", lambda: fetch_item_labels(net, root, qids, sleep=sleep, pace=pace)),
        ("wikitext", lambda: fetch_wikitext(net, root, pages, sleep=sleep, pace=pace)),
        ("wikis", lambda: fetch_wikis(net, root, qids, sleep=sleep, pace=pace,
                                      skip={q: frozenset(v) for q, v in cached.items()})),
    ):  # fmt: skip
        result[step] = work()
        _record_step(root, f"dating_{step}", {**result[step], "sites": len(site_ids)})
        log.info("%s: %s", step, result[step])
    return result


# ------------------------------------------------------------------------------ the run
def open_fetcher(root: Path) -> Fetcher:
    """The Wikimedia API client: the census Fetcher, with this harvest's cache and agent."""
    return Fetcher(root / CACHE, workers=1, timeout=TIMEOUT_SECONDS, user_agent=USER_AGENT)


def open_client() -> httpx.Client:
    """The client for the stored source pages and the quoted pages: this lane's agent, redirects
    followed."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=TIMEOUT_SECONDS
    )


def fetch(
    root: Path,
    *,
    net: Fetcher,
    client: httpx.Client,
    refetch_failed: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    pace: float = PACE_SECONDS,
) -> dict[str, Any]:
    """Every step in order - items, their classes, their articles, the source URLs - each
    resumable and each recorded in HARVEST.json when it finishes."""
    sites = read_sites(root)
    qids = sorted({s["qid"] for s in sites if s["qid"] is not None})
    result: dict[str, Any] = {}
    for step, run in (
        ("entities", lambda: fetch_entities(net, root, qids, sleep=sleep, pace=pace)),
        ("classes", lambda: fetch_classes(net, root, qids, sleep=sleep, pace=pace)),
        ("enwiki", lambda: fetch_enwiki(net, root, qids, sleep=sleep, pace=pace)),
        (
            "urls",
            lambda: fetch_urls(
                net, client, root, sites, refetch_failed=refetch_failed, sleep=sleep, pace=pace
            ),
        ),
    ):
        result[step] = run()
        _record_step(root, step, result[step])
        log.info("%s: %s", step, result[step])
    return result


def status(root: Path) -> dict[str, Any]:
    """Coverage of the harvest as it stands - read from the files only."""
    sites = read_sites(root)
    with_qid = [s for s in sites if s["qid"] is not None]
    entities = [s for s in with_qid if entity_path(root, s["qid"]).exists()]
    articles = [s for s in entities if enwiki_sitelink(load_entity(root, s["qid"])) is not None]

    def url_state(site: Mapping[str, Any]) -> str:
        path = url_path(root, site["site_id"])
        if not path.exists():
            return "-"
        record = _read_json(path)
        return record["kind"] if record["source_url"] == site["source_url"] else "stale"

    urls = Counter(url_state(s) for s in sites)
    return {
        "sites": len(sites),
        "with_qid": len(with_qid),
        "entities_harvested": len(entities),
        "with_enwiki_sitelink": len(articles),
        "enwiki_records": sum(1 for s in articles if enwiki_path(root, s["qid"]).exists()),
        "url_records": dict(sorted(urls.items())),
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="SITES.jsonl from production (one read-only SELECT)")
    exp.add_argument("--sample", type=int, help="a reproducible sample of sites not retired")
    exp.add_argument("--seed", type=int, default=0)
    run = sub.add_parser("fetch", help="items, classes, articles, source URLs (resumable)")
    run.add_argument("--refetch-failed", action="store_true")
    run.add_argument("--pace", type=float, default=PACE_SECONDS)
    dating = sub.add_parser(
        "fetch-dating",
        help="D70: the dating extractor's sources for the listed sites - item labels, the "
        "wikitext of each cached revision, the other-language extracts (serial, resumable)",
    )
    dating.add_argument("--sites", type=Path, nargs="+", required=True,
                        help="JSON-lines files with a site_id per line (UNDATED, GOLD, DEV, HARD)")  # fmt: skip
    dating.add_argument("--pace", type=float, default=PACE_SECONDS)
    sub.add_parser("status", help="coverage, from the files only")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        if args.command == "export":
            if args.sample is None and args.seed:
                parser.error("--seed draws a sample: give --sample too")
            result = export(
                args.root, reader=psql_json_reader(), sample=args.sample, seed=args.seed
            )
        elif args.command == "fetch":
            with open_fetcher(args.root) as net, open_client() as client:
                result = fetch(
                    args.root,
                    net=net,
                    client=client,
                    refetch_failed=args.refetch_failed,
                    pace=args.pace,
                )
        elif args.command == "fetch-dating":
            from fields import wiki as W

            site_ids = sorted({s for path in args.sites for s in read_site_ids(path)})
            with open_fetcher(args.root) as net:
                result = fetch_dating(
                    args.root, net=net, site_ids=site_ids, wiki_cache=W.WikiCache(), pace=args.pace
                )
        else:
            result = status(args.root)
    except HarvestError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
