"""Batch fetch Wikidata claims for audit sites with Wikipedia URLs."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.normalizers.dates import extract_year_from_wikidata_time


UA = "AncientNerdsMap/1.0 (archaeological site database audit)"
HEADERS = {"User-Agent": UA}


def fetch_json(url: str) -> dict | None:
    """Fetch JSON from URL with User-Agent header."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  WARN: fetch failed for {url}: {e}", file=sys.stderr)
        return None


def extract_wiki_title(source_url: str) -> tuple[str, str] | None:
    """Extract (lang, title) from a Wikipedia URL.

    Handles mobile URLs (en.m.wikipedia.org), query params, and
    concatenated source_urls (space-separated — tries each in order).
    """
    if not source_url:
        return None
    # source_url may contain multiple URLs separated by spaces
    for url in source_url.split():
        m = re.search(r"https?://(\w+)(?:\.m)?\.wikipedia\.org/wiki/(.+?)(?:[#?].*)?$", url)
        if m:
            return m.group(1), urllib.parse.unquote(m.group(2))
    return None


def get_qid_from_wikipedia(lang: str, title: str) -> str | None:
    """Resolve Wikipedia article to Wikidata QID."""
    encoded = urllib.parse.quote(title, safe="")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    data = fetch_json(url)
    if data and "wikibase_item" in data:
        return data["wikibase_item"]
    return None


def fetch_wikidata_batch(qids: list[str]) -> dict:
    """Fetch multiple Wikidata entities in one call (max 50)."""
    ids_str = "|".join(qids)
    url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={ids_str}&format=json&props=claims|labels&languages=en"
    data = fetch_json(url)
    if data and "entities" in data:
        return data["entities"]
    return {}


def extract_year_from_time(time_str: str, precision: int) -> int | None:
    """Convert Wikidata time to year integer. Delegates to shared implementation."""
    return extract_year_from_wikidata_time(time_str, precision)


def extract_claims(entity: dict) -> dict:
    """Extract relevant claims from a Wikidata entity."""
    claims = entity.get("claims", {})
    result = {}

    # P625 - coordinates
    if "P625" in claims:
        val = claims["P625"][0]["mainsnak"].get("datavalue", {}).get("value", {})
        if val:
            result["lat"] = val.get("latitude")
            result["lon"] = val.get("longitude")

    # P17 - country (QID)
    if "P17" in claims:
        country_qids = []
        for c in claims["P17"]:
            dv = c["mainsnak"].get("datavalue", {}).get("value", {})
            if dv:
                country_qids.append(dv.get("id"))
        result["country_qids"] = country_qids

    # P31 - instance of (QIDs)
    if "P31" in claims:
        instance_qids = []
        for c in claims["P31"]:
            dv = c["mainsnak"].get("datavalue", {}).get("value", {})
            if dv:
                instance_qids.append(dv.get("id"))
        result["instance_qids"] = instance_qids

    # P571 - inception
    if "P571" in claims:
        for c in claims["P571"]:
            dv = c["mainsnak"].get("datavalue", {}).get("value", {})
            if dv:
                precision = dv.get("precision", 9)
                year = extract_year_from_time(dv.get("time", ""), precision)
                if year is not None:
                    result["inception_year"] = year
                    result["inception_precision"] = precision
                break

    # P580/P582 - start/end time
    for prop, key in [("P580", "start_year"), ("P582", "end_year")]:
        if prop in claims:
            dv = claims[prop][0]["mainsnak"].get("datavalue", {}).get("value", {})
            if dv:
                precision = dv.get("precision", 9)
                year = extract_year_from_time(dv.get("time", ""), precision)
                if year is not None:
                    result[key] = year

    # Label
    labels = entity.get("labels", {})
    if "en" in labels:
        result["en_label"] = labels["en"]["value"]

    return result


def main():
    # Read sites from stdin (pipe-delimited)
    sites = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        sites.append({
            "id": parts[0],
            "name": parts[1],
            "site_type": parts[2],
            "period_start": int(parts[3]) if parts[3] else None,
            "country": parts[4],
            "source_url": parts[5],
            "raw_year": parts[6],
            "tier": parts[7],
        })

    print(f"Loaded {len(sites)} sites", file=sys.stderr)

    # Step 1: Resolve Wikipedia URLs to QIDs
    wiki_sites = [s for s in sites if "wikipedia" in (s["source_url"] or "")]
    print(f"Resolving {len(wiki_sites)} Wikipedia URLs to QIDs...", file=sys.stderr)

    qid_map = {}  # site_id -> QID
    for i, site in enumerate(wiki_sites):
        parsed = extract_wiki_title(site["source_url"])
        if not parsed:
            print(f"  SKIP: can't parse URL for {site['name']}: {site['source_url']}", file=sys.stderr)
            continue
        lang, title = parsed
        qid = get_qid_from_wikipedia(lang, title)
        if qid:
            qid_map[site["id"]] = qid
        else:
            print(f"  WARN: no QID for {site['name']} ({lang}:{title})", file=sys.stderr)
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(wiki_sites)} resolved...", file=sys.stderr)
        time.sleep(0.15)  # rate limit

    print(f"Resolved {len(qid_map)} QIDs", file=sys.stderr)

    # Step 2: Batch fetch Wikidata entities
    all_qids = list(set(qid_map.values()))
    entities = {}
    for i in range(0, len(all_qids), 50):
        batch = all_qids[i:i+50]
        print(f"Fetching Wikidata batch {i//50 + 1} ({len(batch)} entities)...", file=sys.stderr)
        batch_entities = fetch_wikidata_batch(batch)
        entities.update(batch_entities)
        time.sleep(0.3)

    # Step 3: Resolve referenced QIDs (country, instance-of)
    ref_qids = set()
    for qid, entity in entities.items():
        claims = extract_claims(entity)
        for cq in claims.get("country_qids", []):
            ref_qids.add(cq)
        for iq in claims.get("instance_qids", []):
            ref_qids.add(iq)

    ref_labels = {}
    ref_qids_list = list(ref_qids)
    for i in range(0, len(ref_qids_list), 50):
        batch = ref_qids_list[i:i+50]
        print(f"Resolving {len(batch)} referenced QIDs...", file=sys.stderr)
        batch_data = fetch_wikidata_batch(batch)
        for rqid, rent in batch_data.items():
            labels = rent.get("labels", {})
            if "en" in labels:
                ref_labels[rqid] = labels["en"]["value"]
        time.sleep(0.3)

    # Step 4: Output results
    results = []
    for site in sites:
        qid = qid_map.get(site["id"])
        if not qid or qid not in entities:
            results.append({**site, "qid": qid, "wikidata": None})
            continue

        claims = extract_claims(entities[qid])
        # Resolve QID labels
        countries = [ref_labels.get(q, q) for q in claims.get("country_qids", [])]
        instances = [ref_labels.get(q, q) for q in claims.get("instance_qids", [])]
        claims["countries"] = countries
        claims["instances"] = instances
        results.append({**site, "qid": qid, "wikidata": claims})

    outpath = sys.argv[1] if len(sys.argv) > 1 else "audit_wikidata_results.json"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Done. {len(results)} results written to {outpath}.", file=sys.stderr)


if __name__ == "__main__":
    main()
