#!/usr/bin/env python3
"""Phase 2: Fetch Wikidata claims for matched sites.

Batch-fetches structured data from Wikidata for all reconciled QIDs.
Extracts inception dates, heritage designations, Commons images, sitelinks, etc.

Usage:
    python scripts/enrich_fetch_claims.py
"""

import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

_HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Properties to extract
PROPERTIES = {
    "P571": "inception",
    "P576": "dissolved",
    "P1435": "heritage",
    "P18": "commons_image",
    "P373": "commons_category",
    "P2596": "culture",
    "P149": "architectural_style",
    "P31": "instance_of",
    "P361": "part_of",
    "P1612": "pleiades_id",
    "P1566": "geonames_id",
}

# Heritage designation QIDs to human-readable labels
HERITAGE_LABELS = {
    "Q9259": "UNESCO World Heritage Site",
    "Q43113623": "UNESCO World Heritage Site (part)",
    "Q1459092": "National Historic Landmark",
    "Q15700834": "Scheduled Ancient Monument",
    "Q28737012": "national heritage site",
    "Q811165": "National monument",
    "Q51041800": "Monument historique",
}


def _parse_time_value(time_str: str) -> int | None:
    """Parse Wikidata time value to year integer."""
    if not time_str:
        return None
    # Format: +YYYY-MM-DDT00:00:00Z or -YYYY-MM-DDT00:00:00Z
    m = re.match(r"([+-])(\d+)-", time_str)
    if m:
        sign = -1 if m.group(1) == "-" else 1
        year = int(m.group(2))
        return sign * year
    return None


def _extract_string_value(claim: dict) -> str | None:
    """Extract a simple string value from a Wikidata claim."""
    mainsnak = claim.get("mainsnak", {})
    datavalue = mainsnak.get("datavalue", {})
    if datavalue.get("type") == "string":
        return datavalue.get("value")
    return None


def _extract_entity_id(claim: dict) -> str | None:
    """Extract entity ID (QID) from a wikibase-entityid claim."""
    mainsnak = claim.get("mainsnak", {})
    datavalue = mainsnak.get("datavalue", {})
    if datavalue.get("type") == "wikibase-entityid":
        return datavalue.get("value", {}).get("id")
    return None


def _extract_time_value(claim: dict) -> int | None:
    """Extract year from a time-valued claim."""
    mainsnak = claim.get("mainsnak", {})
    datavalue = mainsnak.get("datavalue", {})
    if datavalue.get("type") == "time":
        return _parse_time_value(datavalue.get("value", {}).get("time", ""))
    return None


def _resolve_heritage_label(qid: str) -> str:
    """Resolve a heritage designation QID to a human label."""
    return HERITAGE_LABELS.get(qid, qid)


def fetch_claims_batch(client: httpx.Client, qids: list[str]) -> dict[str, dict]:
    """Fetch claims for a batch of QIDs (max 50)."""
    resp = client.get(WIKIDATA_API, params={
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "claims|sitelinks",
        "format": "json",
    })
    if resp.status_code != 200:
        print(f"  wbgetentities returned {resp.status_code}", flush=True)
        return {}

    data = resp.json()
    entities = data.get("entities", {})
    results = {}

    for qid, entity in entities.items():
        if "missing" in entity:
            continue

        claims = entity.get("claims", {})
        sitelinks = entity.get("sitelinks", {})
        result: dict = {"qid": qid}

        # Extract each property
        for prop_id, field_name in PROPERTIES.items():
            prop_claims = claims.get(prop_id, [])
            if not prop_claims:
                continue

            claim = prop_claims[0]  # Take first claim

            if prop_id in ("P571", "P576"):
                # Time values -> year
                year = _extract_time_value(claim)
                if year is not None:
                    result[field_name] = year

            elif prop_id == "P1435":
                # Heritage designation -> resolve label
                heritage_qid = _extract_entity_id(claim)
                if heritage_qid:
                    result[field_name] = _resolve_heritage_label(heritage_qid)

            elif prop_id in ("P18", "P373"):
                # String values (filenames, category names)
                val = _extract_string_value(claim)
                if val:
                    result[field_name] = val

            elif prop_id in ("P2596", "P149", "P31", "P361"):
                # Entity references -> store QID (can resolve labels later)
                entity_id = _extract_entity_id(claim)
                if entity_id:
                    result[field_name] = entity_id

            elif prop_id in ("P1612", "P1566"):
                # External IDs (strings)
                val = _extract_string_value(claim)
                if val:
                    result[field_name] = val

        # Extract sitelinks (Wikipedia articles per language)
        if sitelinks:
            result["sitelinks"] = {}
            for wiki_key, link_data in sitelinks.items():
                if wiki_key.endswith("wiki") and wiki_key != "commonswiki":
                    lang = wiki_key[:-4]  # e.g. "enwiki" -> "en"
                    result["sitelinks"][lang] = link_data.get("title", "")

        results[qid] = result

    return results


def main() -> None:
    qids_path = OUTPUT_DIR / "enrichment_qids.json"
    if not qids_path.exists():
        print(f"Error: {qids_path} not found. Run: python scripts/enrich_reconcile.py")
        sys.exit(1)

    with open(qids_path, encoding="utf-8") as f:
        qids_data = json.load(f)

    matches = qids_data.get("matches", {})
    if not matches:
        print("No matched QIDs found.")
        sys.exit(1)

    # Build QID -> site_id mapping
    qid_to_sites: dict[str, list[str]] = {}
    for site_id, match_info in matches.items():
        qid = match_info["qid"]
        qid_to_sites.setdefault(qid, []).append(site_id)

    unique_qids = list(qid_to_sites.keys())
    total = len(unique_qids)
    print(f"[CLAIMS] Fetching claims for {total} unique QIDs ({len(matches)} sites)", flush=True)

    client = httpx.Client(headers=_HEADERS, timeout=60.0)
    all_claims: dict[str, dict] = {}

    # Batch fetch (50 QIDs per request)
    batch_size = 50
    for batch_start in range(0, total, batch_size):
        batch = unique_qids[batch_start:batch_start + batch_size]
        batch_results = fetch_claims_batch(client, batch)
        all_claims.update(batch_results)

        if (batch_start + batch_size) % 200 == 0 or batch_start + batch_size >= total:
            print(f"  Fetched {min(batch_start + batch_size, total)}/{total} QIDs...", flush=True)

        # Rate limit
        time.sleep(0.5)

    client.close()

    # Map back to site_ids
    site_claims: dict[str, dict] = {}
    for qid, claim_data in all_claims.items():
        for site_id in qid_to_sites.get(qid, []):
            site_claims[site_id] = claim_data

    # Stats
    has_inception = sum(1 for c in site_claims.values() if "inception" in c)
    has_heritage = sum(1 for c in site_claims.values() if "heritage" in c)
    has_image = sum(1 for c in site_claims.values() if "commons_image" in c)
    has_sitelinks = sum(1 for c in site_claims.values() if c.get("sitelinks"))

    output = {
        "claims": site_claims,
        "stats": {
            "total_sites": len(site_claims),
            "has_inception": has_inception,
            "has_heritage": has_heritage,
            "has_commons_image": has_image,
            "has_sitelinks": has_sitelinks,
        },
    }

    output_path = OUTPUT_DIR / "enrichment_claims.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[CLAIMS] Results saved to {output_path}", flush=True)
    print(f"  Sites with claims: {len(site_claims)}", flush=True)
    print(f"  With inception date: {has_inception}", flush=True)
    print(f"  With heritage designation: {has_heritage}", flush=True)
    print(f"  With Commons image: {has_image}", flush=True)
    print(f"  With Wikipedia sitelinks: {has_sitelinks}", flush=True)


if __name__ == "__main__":
    main()
