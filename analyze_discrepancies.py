"""Analyze all Wikidata period discrepancies against raw_data."""
import json
import re
import psycopg2

DB_CONN = "host=localhost port=5432 dbname=ancient_map user=ancient_map password=ancient_map_dev_password"


def parse_year_string(raw_year):
    """Parse a raw_year string to extract the earliest year."""
    if not raw_year:
        return None

    s = raw_year.strip()

    # "N,NNN BC" or "N BC"
    m = re.match(r'^([\d,]+)\s*BC', s, re.IGNORECASE)
    if m:
        return -int(m.group(1).replace(",", ""))

    # "Nth ml. BC" (millennium)
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s+ml\.?\s*BC', s, re.IGNORECASE)
    if m:
        return -int(m.group(1)) * 1000

    # "Nth c. BC" (century)
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s+c\.?\s*BC', s, re.IGNORECASE)
    if m:
        return -int(m.group(1)) * 100

    # "N BC - N AD" or "N - N BC"
    m = re.match(r'^([\d,]+)\s*BC\s*[-\u2013]\s*([\d,]+)\s*(AD|BC)?', s, re.IGNORECASE)
    if m:
        return -int(m.group(1).replace(",", ""))

    # "N - N BC" (range within BC)
    m = re.match(r'^([\d,]+)\s*[-\u2013]\s*([\d,]+)\s*BC', s, re.IGNORECASE)
    if m:
        return -int(m.group(1).replace(",", ""))

    # "Nth - Nth ml. BC"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s*[-\u2013]\s*\d+(?:st|nd|rd|th)\s+ml\.?\s*BC', s, re.IGNORECASE)
    if m:
        return -int(m.group(1)) * 1000

    # "Nth - Nth c. BC"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s*[-\u2013]\s*\d+(?:st|nd|rd|th)\s+c\.?\s*BC', s, re.IGNORECASE)
    if m:
        return -int(m.group(1)) * 100

    # "N AD"
    m = re.match(r'^([\d,]+)\s*AD', s, re.IGNORECASE)
    if m:
        return int(m.group(1).replace(",", ""))

    # "Nth c. AD"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s+c\.?\s*AD', s, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 100

    # "Nth ml. AD"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s+ml\.?\s*AD', s, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 1000

    # Range: "N BC - Nth c. AD" or "N BC - N AD"
    m = re.match(r'^([\d,]+)\s*BC', s, re.IGNORECASE)
    if m:
        return -int(m.group(1).replace(",", ""))

    # Plain number at start
    m = re.match(r'^([\d,]+)', s)
    if m:
        num = int(m.group(1).replace(",", ""))
        # Check if "BC" appears anywhere later
        if "BC" in s.upper():
            return -num
        return num  # Assume AD if no BC

    return None


def main():
    with open("wikidata_results.json") as f:
        data = json.load(f)

    period_disc = [d for d in data["discrepancies"] if d["field"] == "period_start"]
    country_disc = [d for d in data["discrepancies"] if d["field"] == "country"]
    coord_disc = [d for d in data["discrepancies"] if d["field"] == "coords"]

    conn = psycopg2.connect(DB_CONN)
    cur = conn.cursor()

    # Get raw_data for all discrepancy sites
    site_ids = [d["id"] for d in period_disc]
    if not site_ids:
        print("No period discrepancies to analyze")
        return

    placeholders = ",".join(f"'{sid}'" for sid in site_ids)
    cur.execute(f"""
        SELECT id::text, name, period_start, raw_data->>'year' as raw_year
        FROM unified_sites WHERE id::text IN ({placeholders})
    """)
    raw_map = {row[0]: {"name": row[1], "period_start": row[2], "raw_year": row[3]} for row in cur.fetchall()}

    # Classify each discrepancy
    fixes = []         # DB wrong, can fix from raw_year
    wd_confirms = []   # WD agrees with raw_year (DB was parsed wrong)
    db_correct = []    # DB matches raw_year, WD is different
    ambiguous = []     # Can't determine

    for d in period_disc:
        sid = d["id"]
        db_val = int(d["db_value"])
        wd_val = int(d["wd_value"])
        raw = raw_map.get(sid, {})
        raw_year = raw.get("raw_year", "")
        name = d["name"]

        parsed = parse_year_string(raw_year) if raw_year else None

        if parsed is not None:
            db_diff = abs(db_val - parsed)
            wd_diff = abs(wd_val - parsed)

            if db_diff <= max(100, abs(parsed) * 0.05):
                # DB matches raw_year
                db_correct.append({
                    "name": name, "id": sid,
                    "db": db_val, "wd": wd_val, "parsed": parsed,
                    "raw_year": raw_year,
                })
            elif wd_diff < db_diff and db_diff > 200:
                # WD is closer to raw_year than DB
                wd_confirms.append({
                    "name": name, "id": sid,
                    "db": db_val, "wd": wd_val, "parsed": parsed,
                    "raw_year": raw_year,
                })
            elif db_diff > 200:
                # DB is far from raw_year, propose fix to parsed value
                fixes.append({
                    "name": name, "id": sid,
                    "db": db_val, "wd": wd_val, "parsed": parsed,
                    "raw_year": raw_year,
                })
            else:
                ambiguous.append({
                    "name": name, "id": sid,
                    "db": db_val, "wd": wd_val, "parsed": parsed,
                    "raw_year": raw_year,
                })
        else:
            ambiguous.append({
                "name": name, "id": sid,
                "db": db_val, "wd": wd_val, "parsed": None,
                "raw_year": raw_year,
            })

    print("=" * 70)
    print(f"PERIOD DISCREPANCY ANALYSIS (total: {len(period_disc)})")
    print("=" * 70)
    print(f"  DB correct (matches raw_year): {len(db_correct)}")
    print(f"  DB wrong, fixable from raw_year: {len(fixes)}")
    print(f"  WD confirms raw_year (DB parsed wrong): {len(wd_confirms)}")
    print(f"  Ambiguous (needs manual review): {len(ambiguous)}")

    print(f"\n--- DB wrong, fixable from raw_year ({len(fixes)}) ---")
    for f in fixes:
        print(f"  {f['name'][:40]:<42} DB={f['db']:>8} parsed={f['parsed']:>8} raw={f['raw_year']!r}")

    print(f"\n--- WD confirms raw_year ({len(wd_confirms)}) ---")
    for f in wd_confirms:
        print(f"  {f['name'][:40]:<42} DB={f['db']:>8} WD={f['wd']:>8} parsed={f['parsed']:>8} raw={f['raw_year']!r}")

    print(f"\n--- Ambiguous ({len(ambiguous)}) ---")
    for f in ambiguous[:20]:
        print(f"  {f['name'][:40]:<42} DB={f['db']:>8} WD={f['wd']:>8} parsed={str(f['parsed']):>8} raw={f['raw_year']!r}")
    if len(ambiguous) > 20:
        print(f"  ... and {len(ambiguous) - 20} more")

    # Write fixes to JSON
    output = {
        "fixes": fixes,
        "wd_confirms": wd_confirms,
        "db_correct": db_correct,
        "ambiguous": ambiguous,
        "country_disc": country_disc,
        "coord_disc": coord_disc,
    }
    with open("discrepancy_analysis.json", "w") as f_out:
        json.dump(output, f_out, indent=2, ensure_ascii=False)
    print(f"\nAnalysis written to discrepancy_analysis.json")

    # Generate country fix SQL for genuine errors
    genuine_country_fixes = []
    country_fixes_map = {
        "Achladia": ("Germany", "Greece"),
        "Ahuila Gencha Machay": ("Pakistan", "Peru"),
        "Aquae Helveticae": ("Sweden", "Switzerland"),
        "Tempio di Zeus, Selinunte": ("Greece", "Italy"),
    }
    for d in country_disc:
        if d["name"] in country_fixes_map:
            old, new = country_fixes_map[d["name"]]
            if d["db_value"] == old:
                genuine_country_fixes.append({
                    "id": d["id"],
                    "name": d["name"],
                    "old": old,
                    "new": new,
                })

    print(f"\n--- Genuine country fixes ({len(genuine_country_fixes)}) ---")
    for f in genuine_country_fixes:
        print(f"  {f['name']}: {f['old']} -> {f['new']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
