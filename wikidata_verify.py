"""
Batch Wikidata verification for ancient_nerds sites.
Resolves Wikipedia URLs → Wikidata QIDs → Fetches claims → Compares with DB.
Outputs SQL fixes and discrepancy report.
"""
import json
import re
import sys
import time
from urllib.parse import unquote, quote
import requests
import psycopg2

# --- Config ---
DB_CONN = "host=localhost port=5432 dbname=ancient_map user=ancient_map password=ancient_map_dev_password"
USER_AGENT = "AncientNerdsMap/1.0 (archaeological-sites-audit; contact@ancientnerds.com)"
BATCH_SIZE = 50
DELAY = 0.15  # seconds between API calls

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def extract_wiki_info(url):
    """Extract language and title from Wikipedia URL."""
    if not url:
        return None, None
    m = re.match(r'https?://([a-z]+)\.wikipedia\.org/wiki/(.+)', url)
    if m:
        return m.group(1), unquote(m.group(2))
    return None, None


def batch_resolve_qids(lang, titles):
    """Resolve Wikipedia titles to Wikidata QIDs using Wikipedia action API."""
    # titles is a list of (db_id, title) tuples
    title_map = {t: db_id for db_id, t in titles}
    title_str = "|".join(t for _, t in titles)

    try:
        resp = session.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": title_str,
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "format": "json",
                "redirects": "1",
            },
            timeout=30,
        )
        data = resp.json()
    except Exception as e:
        print(f"  ERROR resolving batch for {lang}: {e}", file=sys.stderr)
        return {}

    results = {}  # db_id -> QID

    # Handle redirects
    redirect_map = {}
    if "redirects" in data.get("query", {}):
        for r in data["query"]["redirects"]:
            redirect_map[r["to"]] = r["from"]

    # Handle normalized titles
    norm_map = {}
    if "normalized" in data.get("query", {}):
        for n in data["query"]["normalized"]:
            norm_map[n["to"]] = n["from"]

    pages = data.get("query", {}).get("pages", {})
    for page_id, page in pages.items():
        if int(page_id) < 0:
            continue  # Missing page
        qid = page.get("pageprops", {}).get("wikibase_item")
        if not qid:
            continue

        page_title = page.get("title", "")
        # Map back to original title
        original_title = page_title
        if page_title in redirect_map:
            original_title = redirect_map[page_title]
        if original_title in norm_map:
            original_title = norm_map[original_title]

        # Find the db_id for this title
        if original_title in title_map:
            results[title_map[original_title]] = qid
        else:
            # Try case-insensitive match
            for t, db_id in title_map.items():
                if t.replace("_", " ") == original_title.replace("_", " "):
                    results[db_id] = qid
                    break

    return results


def batch_fetch_wikidata(qids):
    """Fetch Wikidata claims for a batch of QIDs."""
    qid_str = "|".join(qids)
    try:
        resp = session.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbgetentities",
                "ids": qid_str,
                "format": "json",
                "props": "claims|labels",
                "languages": "en",
            },
            timeout=30,
        )
        return resp.json().get("entities", {})
    except Exception as e:
        print(f"  ERROR fetching Wikidata batch: {e}", file=sys.stderr)
        return {}


def extract_year_from_claim(claim):
    """Extract year from a Wikidata time claim."""
    try:
        snak = claim[0]["mainsnak"]
        if snak.get("snaktype") != "value":
            return None
        time_val = snak["datavalue"]["value"]["time"]
        precision = snak["datavalue"]["value"]["precision"]

        # Parse time string: +YYYY-MM-DDT00:00:00Z or -YYYY-MM-DDT00:00:00Z
        m = re.match(r'([+-])(\d+)-', time_val)
        if not m:
            return None
        sign = -1 if m.group(1) == "-" else 1
        year = int(m.group(2)) * sign

        return year, precision
    except (KeyError, IndexError, ValueError):
        return None


def extract_coord_from_claim(claim):
    """Extract lat/lon from P625 coordinate claim."""
    try:
        snak = claim[0]["mainsnak"]
        if snak.get("snaktype") != "value":
            return None
        val = snak["datavalue"]["value"]
        return val["latitude"], val["longitude"]
    except (KeyError, IndexError):
        return None


def extract_entity_id(claim):
    """Extract entity QID from a claim (for P17, P31)."""
    try:
        snak = claim[0]["mainsnak"]
        if snak.get("snaktype") != "value":
            return None
        return snak["datavalue"]["value"]["id"]
    except (KeyError, IndexError):
        return None


def resolve_entity_labels(qids_to_resolve):
    """Batch-resolve QIDs to English labels."""
    labels = {}
    for i in range(0, len(qids_to_resolve), BATCH_SIZE):
        batch = qids_to_resolve[i:i+BATCH_SIZE]
        qid_str = "|".join(batch)
        try:
            resp = session.get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action": "wbgetentities",
                    "ids": qid_str,
                    "format": "json",
                    "props": "labels",
                    "languages": "en",
                },
                timeout=30,
            )
            entities = resp.json().get("entities", {})
            for qid, entity in entities.items():
                label = entity.get("labels", {}).get("en", {}).get("value")
                if label:
                    labels[qid] = label
        except Exception as e:
            print(f"  ERROR resolving labels: {e}", file=sys.stderr)
        time.sleep(DELAY)
    return labels


def main():
    print("Connecting to database...")
    conn = psycopg2.connect(DB_CONN)
    cur = conn.cursor()

    # Get all ancient_nerds sites with Wikipedia URLs
    cur.execute("""
        SELECT id, name, source_url, period_start, site_type, country, lat, lon
        FROM unified_sites
        WHERE source_id = 'ancient_nerds'
          AND source_url LIKE '%wikipedia.org%'
        ORDER BY
            CASE WHEN period_start IS NULL THEN 0 ELSE 1 END,
            name
    """)
    sites = cur.fetchall()
    print(f"Found {len(sites)} sites with Wikipedia URLs")

    # Group by language
    lang_groups = {}
    site_map = {}  # id -> site data
    for row in sites:
        site_id, name, source_url, period_start, site_type, country, lat, lon = row
        lang, title = extract_wiki_info(source_url)
        if not lang or not title:
            continue
        site_map[str(site_id)] = {
            "name": name,
            "url": source_url,
            "period_start": period_start,
            "site_type": site_type,
            "country": country,
            "lat": lat,
            "lon": lon,
        }
        if lang not in lang_groups:
            lang_groups[lang] = []
        lang_groups[lang].append((str(site_id), title))

    print(f"Language distribution: {', '.join(f'{k}={len(v)}' for k, v in sorted(lang_groups.items(), key=lambda x: -len(x[1])))}")

    # Phase 1: Resolve Wikipedia → QID
    print("\n=== Phase 1: Resolving Wikipedia URLs -> Wikidata QIDs ===")
    qid_map = {}  # db_id -> QID
    total_resolved = 0

    for lang, entries in sorted(lang_groups.items(), key=lambda x: -len(x[1])):
        print(f"  Resolving {len(entries)} {lang}.wikipedia.org titles...")
        for i in range(0, len(entries), BATCH_SIZE):
            batch = entries[i:i+BATCH_SIZE]
            results = batch_resolve_qids(lang, batch)
            qid_map.update(results)
            total_resolved += len(results)
            time.sleep(DELAY)
        print(f"    Resolved: {sum(1 for e in entries if e[0] in qid_map)}/{len(entries)}")

    print(f"\nTotal QIDs resolved: {total_resolved}/{len(site_map)}")

    # Phase 2: Batch fetch Wikidata claims
    print("\n=== Phase 2: Fetching Wikidata claims ===")
    all_qids = list(set(qid_map.values()))
    wikidata_claims = {}  # QID -> claims dict
    qids_to_resolve = set()  # QIDs referenced by P17/P31 that need label resolution

    for i in range(0, len(all_qids), BATCH_SIZE):
        batch = all_qids[i:i+BATCH_SIZE]
        print(f"  Fetching claims batch {i//BATCH_SIZE + 1}/{(len(all_qids) + BATCH_SIZE - 1)//BATCH_SIZE}...")
        entities = batch_fetch_wikidata(batch)

        for qid, entity in entities.items():
            claims = entity.get("claims", {})
            parsed = {}

            # P571 inception / P580 start time
            for prop in ["P571", "P580"]:
                if prop in claims:
                    year_info = extract_year_from_claim(claims[prop])
                    if year_info:
                        parsed["inception_year"] = year_info[0]
                        parsed["inception_precision"] = year_info[1]
                        break

            # P625 coordinates
            if "P625" in claims:
                coords = extract_coord_from_claim(claims["P625"])
                if coords:
                    parsed["lat"] = coords[0]
                    parsed["lon"] = coords[1]

            # P17 country (QID)
            if "P17" in claims:
                country_qid = extract_entity_id(claims["P17"])
                if country_qid:
                    parsed["country_qid"] = country_qid
                    qids_to_resolve.add(country_qid)

            # P31 instance of (QID)
            if "P31" in claims:
                type_qid = extract_entity_id(claims["P31"])
                if type_qid:
                    parsed["type_qid"] = type_qid
                    qids_to_resolve.add(type_qid)

            # P18 image
            if "P18" in claims:
                try:
                    img = claims["P18"][0]["mainsnak"]["datavalue"]["value"]
                    parsed["image"] = img
                except (KeyError, IndexError):
                    pass

            wikidata_claims[qid] = parsed

        time.sleep(DELAY)

    print(f"Fetched claims for {len(wikidata_claims)} entities")

    # Phase 3: Resolve entity labels (countries, types)
    print(f"\n=== Phase 3: Resolving {len(qids_to_resolve)} entity labels ===")
    entity_labels = resolve_entity_labels(list(qids_to_resolve))
    print(f"Resolved {len(entity_labels)} labels")

    # Phase 4: Compare and classify
    print("\n=== Phase 4: Comparing Wikidata vs DB ===")

    fixes = []
    discrepancies = []
    verified = []
    missing_period_found = []

    for db_id, qid in qid_map.items():
        site = site_map[db_id]
        wd = wikidata_claims.get(qid, {})

        if not wd:
            continue

        # Check period
        if "inception_year" in wd:
            wd_year = wd["inception_year"]
            wd_precision = wd["inception_precision"]
            db_period = site["period_start"]

            if db_period is None and wd_year <= 1500:
                missing_period_found.append({
                    "id": db_id,
                    "name": site["name"],
                    "wd_year": wd_year,
                    "wd_precision": wd_precision,
                    "qid": qid,
                })
            elif db_period is not None:
                # Check if they roughly agree
                if abs(db_period - wd_year) <= max(100, abs(db_period) * 0.1):
                    verified.append((db_id, site["name"], "period_start", str(db_period), str(wd_year), qid))
                elif wd_year > 1500 and db_period <= 1500:
                    # Wikidata has modern date, DB has ancient — likely discovery date
                    verified.append((db_id, site["name"], "period_start", str(db_period), f"REJECTED:{wd_year}(likely discovery date)", qid))
                else:
                    discrepancies.append({
                        "id": db_id,
                        "name": site["name"],
                        "field": "period_start",
                        "db_value": str(db_period),
                        "wd_value": str(wd_year),
                        "wd_precision": wd_precision,
                        "qid": qid,
                    })

        # Check country
        if "country_qid" in wd:
            wd_country = entity_labels.get(wd["country_qid"], "")
            db_country = site["country"] or ""
            if wd_country and db_country:
                # Normalize for comparison
                wd_norm = wd_country.lower().strip()
                db_norm = db_country.lower().strip()
                # Handle common mismatches
                country_aliases = {
                    "united kingdom": ["england", "scotland", "wales", "northern ireland"],
                    "people's republic of china": ["china"],
                    "republic of ireland": ["ireland"],
                }
                match = (wd_norm == db_norm or
                        wd_norm in db_norm or db_norm in wd_norm or
                        any(db_norm in aliases for k, aliases in country_aliases.items() if wd_norm == k) or
                        any(wd_norm in aliases for k, aliases in country_aliases.items() if db_norm == k))

                if not match:
                    discrepancies.append({
                        "id": db_id,
                        "name": site["name"],
                        "field": "country",
                        "db_value": db_country,
                        "wd_value": wd_country,
                        "qid": qid,
                    })

        # Check coords
        if "lat" in wd and "lon" in wd:
            db_lat = site["lat"]
            db_lon = site["lon"]
            if db_lat and db_lon:
                lat_diff = abs(db_lat - wd["lat"])
                lon_diff = abs(db_lon - wd["lon"])
                if lat_diff > 0.5 or lon_diff > 0.5:
                    discrepancies.append({
                        "id": db_id,
                        "name": site["name"],
                        "field": "coords",
                        "db_value": f"({db_lat:.4f}, {db_lon:.4f})",
                        "wd_value": f"({wd['lat']:.4f}, {wd['lon']:.4f})",
                        "qid": qid,
                    })

    # Output results
    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Sites with Wikipedia URLs: {len(site_map)}")
    print(f"QIDs resolved: {len(qid_map)}")
    print(f"Claims fetched: {len(wikidata_claims)}")
    print(f"Verified (period matches): {len(verified)}")
    print(f"Discrepancies found: {len(discrepancies)}")
    print(f"Missing period with Wikidata date: {len(missing_period_found)}")

    # Missing period details
    if missing_period_found:
        print(f"\n--- Missing period_start — Wikidata has dates ---")
        for item in missing_period_found:
            precision_labels = {6: "millennium", 7: "century", 8: "decade", 9: "year"}
            p = precision_labels.get(item["wd_precision"], f"p{item['wd_precision']}")
            print(f"  {item['name']}: wd_year={item['wd_year']} ({p}) [{item['qid']}]")

    # Discrepancies by field
    disc_by_field = {}
    for d in discrepancies:
        field = d["field"]
        if field not in disc_by_field:
            disc_by_field[field] = []
        disc_by_field[field].append(d)

    for field, items in sorted(disc_by_field.items()):
        print(f"\n--- {field} discrepancies ({len(items)}) ---")
        for d in items[:30]:  # First 30
            print(f"  {d['name']}: DB={d['db_value']} WD={d['wd_value']} [{d.get('qid', '')}]")
        if len(items) > 30:
            print(f"  ... and {len(items) - 30} more")

    # Write discrepancies to JSON for further processing
    output = {
        "summary": {
            "total_wikipedia": len(site_map),
            "qids_resolved": len(qid_map),
            "verified": len(verified),
            "discrepancies": len(discrepancies),
            "missing_period_found": len(missing_period_found),
        },
        "missing_period": missing_period_found,
        "discrepancies": discrepancies,
        "verified_count": len(verified),
    }

    with open("wikidata_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results written to wikidata_results.json")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
