"""The research behind the external-id repair's second wave: candidates for every wrong Wikidata link.

Input: the B1 name verdicts (`names.jsonl`) whose class is a wrong link (Q1 generic concept, Q2 shared
parent or sibling, Q3 no coordinate, Q4 more than 5 km away) and whose link the first repair wave did
not already replace. For each site, one at a time, read-only and cached:

* the English article whose title is the stored name (redirects followed and recorded), its item
  and its coordinates - the identity `external_ids.py` would have stored (qid_repair rule A);
* every Wikidata item within 1 km of the stored point (`list=geosearch` on wikidata.org), and the
  first ten `wbsearchentities` hits for the stored name - with their names, P31 classes and P625;
* for each candidate, whether the stored name is one of its names (`classify.name_identity`).

`suggest()` applies qid_repair's two rules with the stricter gate the remaining-work map asks for
(a replacement is worse than a known-bad anchor if it is wrong, because dedup trusts item ids):

* **A** - the stored name is an existing English article's exact title (not a redirect), and that
  article's item has a P625 within 1 km of the stored point;
* **B** - exactly one item within 1 km whose names include the stored name (N1/N2);
* otherwise **unresolved** - the row stays as it is.

The suggestion is a lead, not a decision: every wave-2 entry in `qid_repair.py` is read and written by
hand, with the evidence quoted from `qid_research.jsonl`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from census.fetch import Fetcher, chunked

from bcases import classify as C
from bcases import collect as K
from bcases import inputs

#: The radius of the neighbourhood search, and the gate a replacement must pass (metres).
RADIUS_M = 1000
SEARCH_LIMIT = 10


def enwiki_page(net: Fetcher, title: str) -> dict[str, Any]:
    """The English article named exactly `title`: resolved, with its item and coordinates."""
    return K.fetch_enwiki_coords(net, [title])[title]


def neighbours(net: Fetcher, lat: float, lon: float) -> list[str]:
    body = K.api_json(
        net,
        K.WIKIDATA_API,
        {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": str(RADIUS_M),
            "gslimit": "100",
            "format": "json",
        },
        ns="bcases_research",
    )
    hits = (body.get("query") or {}).get("geosearch")
    if hits is None:
        raise inputs.InputError(f"geosearch at {lat},{lon} answered without `geosearch`")
    return [str(h["title"]) for h in hits]


def search(net: Fetcher, name: str) -> list[str]:
    body = K.api_json(
        net,
        K.WIKIDATA_API,
        {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "limit": str(SEARCH_LIMIT),
            "format": "json",
        },
        ns="bcases_research",
    )
    hits = body.get("search")
    if hits is None:
        raise inputs.InputError(f"wbsearchentities {name!r} answered without `search`")
    return [str(h["id"]) for h in hits]


def entities(net: Fetcher, qids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Names, claims and English description of each candidate."""
    out: dict[str, dict[str, Any]] = {}
    for chunk in chunked(sorted(set(qids)), K.BATCH):
        for qid, entity in K._entities(
            net, chunk, props="labels|aliases|sitelinks|claims|descriptions"
        ).items():
            out[qid] = {
                "names": K.names_record(entity),
                "claims": K.claims_record(entity),
                "description": ((entity.get("descriptions") or {}).get("en") or {}).get("value"),
            }
    return out


def research(net: Fetcher, verdict: Mapping[str, Any], site: Mapping[str, Any]) -> dict[str, Any]:
    """Every candidate item for one wrong-link site, with the facts the two rules read."""
    lat, lon, name = float(site["lat"]), float(site["lon"]), str(site["name"])
    page = enwiki_page(net, name)
    found = [*neighbours(net, lat, lon), *search(net, name)]
    if page.get("wikibase_item"):
        found.append(str(page["wikibase_item"]))
    facts = entities(net, [q for q in dict.fromkeys(found) if q.startswith("Q")])
    classes = {q for f in facts.values() for q in f["claims"]["p31"]}
    labels = K.fetch_labels(net, classes) if classes else {}
    candidates = []
    for qid, fact in sorted(facts.items()):
        point = fact["claims"]["p625"]
        distance = None if point is None else C.km(lat, lon, point["lat"], point["lon"]) * 1000.0
        identity, match = C.name_identity(name, C.known_names(qid, {qid: fact["names"]}))
        candidates.append(
            {
                "qid": qid,
                "label": fact["names"]["labels"].get("en"),
                "description": fact["description"],
                "p31": [labels.get(q) or q for q in fact["claims"]["p31"]],
                "distance_m": None if distance is None else round(distance, 1),
                "identity": identity,
                "match": match,
                "enwiki": fact["claims"]["enwiki"],
            }
        )
    record = {
        "site_id": verdict["site_id"],
        "name": name,
        "class": verdict["class"],
        "old_qid": verdict["qid"],
        "old_label": verdict["en_label"],
        "stored_point": [lat, lon],
        "enwiki_page": page,
        "candidates": sorted(
            candidates,
            key=lambda c: (
                {"N1": 0, "N2": 1, "N3": 2, "none": 3}[c["identity"]],
                c["distance_m"] if c["distance_m"] is not None else 1e12,
            ),
        ),
    }
    record["suggestion"] = suggest(record)
    return record


def is_site_kind(candidate: Mapping[str, Any]) -> bool:
    """A candidate that can be a curated site: not a settlement, unit or natural feature that
    contains one (`classify.is_container_class`), and not a Wikimedia page (a list, a disambiguation)."""
    return not any(
        C.is_container_class(label) or label.startswith("Wikimedia") for label in candidate["p31"]
    )


def suggest(record: Mapping[str, Any]) -> dict[str, Any]:
    """qid_repair's rules A and B under the 1 km gate; anything else is unresolved.

    Rule A's position proof is the item's P625 or, where Wikidata's point is elsewhere, the article's
    own coordinates - the article is the identity rule A names, so its point is the one that has to
    agree with the stored point.
    """
    page = record["enwiki_page"]
    old = record["old_qid"]
    lat, lon = record["stored_point"]
    by_qid = {c["qid"]: c for c in record["candidates"]}
    item = page.get("wikibase_item")
    if item and item != old and not page.get("missing") and not page.get("redirected"):
        c = by_qid.get(item)
        article_m = (
            None if page.get("lat") is None else C.km(lat, lon, page["lat"], page["lon"]) * 1000.0
        )
        placed = (
            c is not None and c["distance_m"] is not None and c["distance_m"] <= RADIUS_M
        ) or (article_m is not None and article_m <= RADIUS_M)
        if c is not None and is_site_kind(c) and placed:
            return {"rule": "A", "qid": item, "title": page["title"]}
    near = [
        c
        for c in record["candidates"]
        if c["qid"] != old
        and c["identity"] in ("N1", "N2")
        and is_site_kind(c)
        and c["distance_m"] is not None
        and c["distance_m"] <= RADIUS_M
    ]
    if len(near) == 1:
        return {"rule": "B", "qid": near[0]["qid"], "title": near[0]["enwiki"]}
    return {
        "rule": "unresolved",
        "qid": None,
        "title": None,
        "near_matches": [c["qid"] for c in near],
    }
