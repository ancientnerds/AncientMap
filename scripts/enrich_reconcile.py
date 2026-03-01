#!/usr/bin/env python3
"""Phase 1: Wikidata Entity Reconciliation.

Matches archaeological sites to Wikidata Q-items using three strategies:
1. Extract QIDs from existing source_url (regex, 0 API calls)
2. W3C Reconciliation API (wikidata.reconci.link) for unmatched sites
3. SPARQL geo-search fallback with fuzzy name matching

Usage:
    python scripts/enrich_reconcile.py
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.database import engine
from sqlalchemy import text

# Reuse regex patterns from wikimedia_resolver
_QID_RE = re.compile(r"wikidata\.org/(?:entity|wiki)/(Q\d+)")
_WIKI_ARTICLE_RE = re.compile(r"(\w+)\.wikipedia\.org/wiki/(.+?)(?:#.*)?$")

_HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
RECONCILIATION_API = "https://wikidata.reconci.link/en/api"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _extract_qid_from_url(url: str) -> str | None:
    """Extract QID from a Wikidata entity URL."""
    m = _QID_RE.search(url)
    return m.group(1) if m else None


def _extract_article_from_url(url: str) -> tuple[str, str] | None:
    """Extract (lang, article_title) from a Wikipedia URL."""
    m = _WIKI_ARTICLE_RE.search(url)
    if m:
        return m.group(1), unquote(m.group(2)).replace("_", " ")
    return None


def _extract_fragment_from_url(url: str) -> str | None:
    """Extract meaningful fragment text from a Wikipedia URL.

    E.g. 'https://en.wikipedia.org/wiki/Giza_pyramid_complex#Osiris_Shaft'
    returns 'Osiris Shaft'.
    """
    m = re.search(r"wikipedia\.org/wiki/.+?#(.+)$", url)
    if m:
        frag = unquote(m.group(1)).replace("_", " ").strip()
        if frag:
            return frag
    return None


def _resolve_article_to_qid(client: httpx.Client, lang: str, title: str) -> str | None:
    """Resolve a Wikipedia article title to a Wikidata QID via API."""
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    resp = client.get(api_url, params={
        "action": "query",
        "titles": title,
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "format": "json",
    })
    if resp.status_code != 200:
        return None
    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        qid = page.get("pageprops", {}).get("wikibase_item")
        if qid:
            return qid
    return None


def strategy_url_extract(allowed_site_ids: set[str] | None = None) -> dict[str, dict]:
    """Strategy 1: Extract QIDs from source_url in the database."""
    matches = {}
    with engine.connect() as conn:
        id_filter = ""
        params = {}
        if allowed_site_ids is not None:
            id_placeholders = ", ".join(f":sid_{i}" for i in range(len(allowed_site_ids)))
            for i, sid in enumerate(allowed_site_ids):
                params[f"sid_{i}"] = sid
            id_filter = f"AND id::text IN ({id_placeholders})"

        rows = conn.execute(text(f"""
            SELECT id::text AS site_id, source_url, name
            FROM unified_sites
            WHERE source_id = 'ancient_nerds'
              AND source_url IS NOT NULL
              AND source_url != ''
              {id_filter}
        """), params).fetchall()

    _PRIORITY_LANGS = ["en", "de", "fr", "it", "es", "ar"]

    client = httpx.Client(headers=_HEADERS, timeout=30.0, follow_redirects=True)
    try:
        for row in rows:
            site_id = row.site_id
            url = row.source_url

            # Try direct QID extraction
            qid = _extract_qid_from_url(url)
            if qid:
                matches[site_id] = {"qid": qid, "method": "url_qid", "confidence": 1.0}
                continue

            # Try Wikipedia article -> QID
            article_info = _extract_article_from_url(url)
            base_qid = None
            lang = None
            if article_info:
                lang, title = article_info
                base_qid = _resolve_article_to_qid(client, lang, title)
                if base_qid:
                    matches[site_id] = {"qid": base_qid, "method": "url_wiki", "confidence": 0.95}

            # Fragment-aware resolution: if URL has a fragment, try it as a standalone article
            fragment = _extract_fragment_from_url(url)
            if fragment:
                # Build language priority list: source URL lang first, then priority langs
                try_langs = []
                if lang:
                    try_langs.append(lang)
                for tl in _PRIORITY_LANGS:
                    if tl not in try_langs:
                        try_langs.append(tl)

                if base_qid:
                    # Base article resolved — look for a more specific dedicated article
                    for tl in try_langs:
                        frag_qid = _resolve_article_to_qid(client, tl, fragment)
                        if frag_qid and frag_qid != base_qid:
                            matches[site_id] = {"qid": frag_qid, "method": "url_wiki_fragment", "confidence": 0.9}
                            break
                else:
                    # Base article didn't resolve — try fragment directly
                    for tl in try_langs:
                        frag_qid = _resolve_article_to_qid(client, tl, fragment)
                        if frag_qid:
                            matches[site_id] = {"qid": frag_qid, "method": "url_wiki_fragment", "confidence": 0.85}
                            break

                # If fragment didn't resolve, try the site's own name
                if site_id not in matches:
                    site_name = row.name
                    if site_name and site_name != fragment:
                        for tl in try_langs:
                            name_qid = _resolve_article_to_qid(client, tl, site_name)
                            if name_qid:
                                matches[site_id] = {"qid": name_qid, "method": "url_name_fallback", "confidence": 0.85}
                                break
    finally:
        client.close()

    return matches


def strategy_reconciliation(sites: list[dict], already_matched: set[str]) -> dict[str, dict]:
    """Strategy 2: W3C Reconciliation API for unmatched sites."""
    unmatched = [s for s in sites if s["site_id"] not in already_matched]
    if not unmatched:
        return {}

    matches = {}
    client = httpx.Client(headers=_HEADERS, timeout=60.0)

    # Process in batches of 25
    batch_size = 25
    for batch_start in range(0, len(unmatched), batch_size):
        batch = unmatched[batch_start:batch_start + batch_size]

        queries = {}
        for i, site in enumerate(batch):
            q = {"query": site["name"]}
            # Add coordinate properties for better matching
            if site.get("lat") and site.get("lon"):
                q["properties"] = [
                    {"pid": "P625", "v": f"{site['lat']}/{site['lon']}"}
                ]
            queries[f"q{i}"] = q

        try:
            resp = client.post(
                RECONCILIATION_API,
                data={"queries": json.dumps(queries)},
            )
            if resp.status_code != 200:
                print(f"  Reconciliation API returned {resp.status_code} for batch {batch_start}", flush=True)
                time.sleep(2)
                continue

            results = resp.json()
            for i, site in enumerate(batch):
                key = f"q{i}"
                candidates = results.get(key, {}).get("result", [])
                if candidates and candidates[0].get("score", 0) > 50:
                    best = candidates[0]
                    matches[site["site_id"]] = {
                        "qid": best["id"],
                        "method": "reconciliation",
                        "confidence": round(min(best["score"] / 100, 1.0), 2),
                    }
        except Exception as e:
            print(f"  Reconciliation error at batch {batch_start}: {e}", flush=True)

        # Rate limit
        time.sleep(1)

        if (batch_start + batch_size) % 100 == 0:
            print(f"  Reconciliation: processed {batch_start + batch_size}/{len(unmatched)}", flush=True)

    client.close()
    return matches


def strategy_sparql_geo(sites: list[dict], already_matched: set[str]) -> dict[str, dict]:
    """Strategy 3: SPARQL geo-search fallback."""
    unmatched = [s for s in sites if s["site_id"] not in already_matched
                 and s.get("lat") and s.get("lon")]
    if not unmatched:
        return {}

    matches = {}
    client = httpx.Client(headers={**_HEADERS, "Accept": "application/sparql-results+json"}, timeout=60.0)

    # Process one at a time (SPARQL geo queries are expensive)
    for i, site in enumerate(unmatched):
        name = site["name"].replace('"', '\\"')
        lat = site["lat"]
        lon = site["lon"]

        query = f"""
        SELECT ?item ?itemLabel ?dist WHERE {{
          SERVICE wikibase:around {{
            ?item wdt:P625 ?loc .
            bd:serviceParam wikibase:center "Point({lon} {lat})"^^geo:wktLiteral .
            bd:serviceParam wikibase:radius "10" .
            bd:serviceParam wikibase:distance ?dist .
          }}
          ?item wdt:P31/wdt:P279* wd:Q839954 .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
        }}
        ORDER BY ?dist
        LIMIT 5
        """

        try:
            resp = client.get(WIKIDATA_SPARQL, params={"query": query, "format": "json"})
            if resp.status_code != 200:
                time.sleep(3)
                continue

            results = resp.json().get("results", {}).get("bindings", [])
            if not results:
                continue

            # Fuzzy name match among results
            name_lower = name.lower()
            best_match = None
            for r in results:
                label = r.get("itemLabel", {}).get("value", "").lower()
                if name_lower in label or label in name_lower:
                    best_match = r
                    break

            # If no fuzzy match, take closest if within 2km
            if not best_match and results:
                dist = float(results[0].get("dist", {}).get("value", 999))
                if dist < 2:
                    best_match = results[0]

            if best_match:
                qid = best_match["item"]["value"].split("/")[-1]
                matches[site["site_id"]] = {
                    "qid": qid,
                    "method": "sparql_geo",
                    "confidence": 0.7,
                }

        except Exception as e:
            print(f"  SPARQL error for {site['name']}: {e}", flush=True)

        # Heavy rate limiting for SPARQL
        time.sleep(2)

        if (i + 1) % 50 == 0:
            print(f"  SPARQL geo: processed {i + 1}/{len(unmatched)}", flush=True)

    client.close()
    return matches


def main() -> None:
    parser = argparse.ArgumentParser(description="Wikidata Entity Reconciliation")
    parser.add_argument(
        "--site-ids-file",
        default=None,
        help="JSON file with list of site IDs to filter (for --limit mode)",
    )
    args = parser.parse_args()

    allowed_site_ids = None
    if args.site_ids_file:
        with open(args.site_ids_file, encoding="utf-8") as f:
            allowed_site_ids = set(json.load(f))
        print(f"[RECONCILE] Filtering to {len(allowed_site_ids)} site IDs", flush=True)

    card_sites_path = OUTPUT_DIR / "card_sites.json"
    if not card_sites_path.exists():
        print(f"Error: {card_sites_path} not found. Run: python scripts/export_card_sites.py")
        sys.exit(1)

    with open(card_sites_path, encoding="utf-8") as f:
        sites = json.load(f)

    # Load coordinates from DB for all sites
    site_coords = {}
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id::text AS site_id, lat, lon
            FROM unified_sites
            WHERE source_id = 'ancient_nerds'
        """)).fetchall()
    for row in rows:
        site_coords[row.site_id] = (row.lat, row.lon)

    # Enrich site list with coords
    for site in sites:
        coords = site_coords.get(site["site_id"])
        if coords:
            site["lat"], site["lon"] = coords

    total = len(sites)
    print(f"[RECONCILE] Starting reconciliation for {total} sites", flush=True)

    # Strategy 1: URL extraction
    print("\n[RECONCILE] Strategy 1: Extracting QIDs from source URLs...", flush=True)
    url_matches = strategy_url_extract(allowed_site_ids=allowed_site_ids)
    print(f"  Matched {len(url_matches)} sites from URLs", flush=True)

    matched_ids = set(url_matches.keys())
    all_matches = dict(url_matches)

    # Strategy 2: Reconciliation API
    print(f"\n[RECONCILE] Strategy 2: Reconciliation API for {total - len(matched_ids)} remaining sites...", flush=True)
    recon_matches = strategy_reconciliation(sites, matched_ids)
    print(f"  Matched {len(recon_matches)} sites via reconciliation", flush=True)
    matched_ids.update(recon_matches.keys())
    all_matches.update(recon_matches)

    # Strategy 3: SPARQL geo-search
    remaining = total - len(matched_ids)
    print(f"\n[RECONCILE] Strategy 3: SPARQL geo-search for {remaining} remaining sites...", flush=True)
    sparql_matches = strategy_sparql_geo(sites, matched_ids)
    print(f"  Matched {len(sparql_matches)} sites via SPARQL geo", flush=True)
    all_matches.update(sparql_matches)

    # Stats
    stats = {
        "url": len(url_matches),
        "reconciliation": len(recon_matches),
        "sparql": len(sparql_matches),
        "unmatched": total - len(all_matches),
    }

    output = {
        "matches": all_matches,
        "stats": stats,
        "total_sites": total,
    }

    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "enrichment_qids.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[RECONCILE] Results saved to {output_path}", flush=True)
    print(f"  Total matched: {len(all_matches)} / {total} ({len(all_matches)/total*100:.1f}%)", flush=True)
    for method, count in stats.items():
        print(f"    {method}: {count}", flush=True)


if __name__ == "__main__":
    main()
