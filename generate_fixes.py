"""Generate SQL fixes from discrepancy analysis."""
import json
import re
import psycopg2

DB_CONN = "host=localhost port=5432 dbname=ancient_map user=ancient_map password=ancient_map_dev_password"

def categorize_period(year):
    if year is None: return None
    if year < -4500: return "< 4500 BC"
    if year < -3000: return "4500 - 3000 BC"
    if year < -1500: return "3000 - 1500 BC"
    if year < -500: return "1500 - 500 BC"
    if year < 1: return "500 BC - 1 AD"
    if year < 500: return "1 - 500 AD"
    if year < 1000: return "500 - 1000 AD"
    if year < 1500: return "1000 - 1500 AD"
    return "1500+ AD"

def parse_year_string(raw_year):
    if not raw_year: return None
    s = raw_year.strip()
    # "N,NNN BC" or "N BC"
    m = re.match(r'^([\d,]+)\s*BC', s, re.IGNORECASE)
    if m: return -int(m.group(1).replace(",", ""))
    # "Nth ml. BC"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s+ml\.?\s*BC', s, re.IGNORECASE)
    if m: return -int(m.group(1)) * 1000
    # "Nth c. BC"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s+c\.?\s*BC', s, re.IGNORECASE)
    if m: return -int(m.group(1)) * 100
    # "N BC - N AD" or "N - N BC"
    m = re.match(r'^([\d,]+)\s*BC\s*[-\u2013]', s, re.IGNORECASE)
    if m: return -int(m.group(1).replace(",", ""))
    # "N - N BC"
    m = re.match(r'^([\d,]+)\s*[-\u2013]\s*([\d,]+)\s*BC', s, re.IGNORECASE)
    if m: return -int(m.group(1).replace(",", ""))
    # "Nth - Nth ml. BC"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s*[-\u2013]\s*\d+(?:st|nd|rd|th)\s+ml\.?\s*BC', s, re.IGNORECASE)
    if m: return -int(m.group(1)) * 1000
    # "Nth - Nth c. BC"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s*[-\u2013]\s*\d+(?:st|nd|rd|th)\s+c\.?\s*BC', s, re.IGNORECASE)
    if m: return -int(m.group(1)) * 100
    # "N AD"
    m = re.match(r'^([\d,]+)\s*AD', s, re.IGNORECASE)
    if m: return int(m.group(1).replace(",", ""))
    # "Nth c. AD"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s+c\.?\s*AD', s, re.IGNORECASE)
    if m: return int(m.group(1)) * 100
    # "Nth ml. AD"
    m = re.match(r'^(\d+)(?:st|nd|rd|th)\s+ml\.?\s*AD', s, re.IGNORECASE)
    if m: return int(m.group(1)) * 1000
    # Bare "N BC" anywhere
    m = re.match(r'^([\d,]+)\s*BC', s, re.IGNORECASE)
    if m: return -int(m.group(1).replace(",", ""))
    # Plain number
    m = re.match(r'^([\d,]+)', s)
    if m:
        num = int(m.group(1).replace(",", ""))
        if "BC" in s.upper(): return -num
        return num
    return None

def main():
    conn = psycopg2.connect(DB_CONN)
    cur = conn.cursor()

    # Load wikidata results
    with open("wikidata_results.json") as f:
        data = json.load(f)

    period_disc = [d for d in data["discrepancies"] if d["field"] == "period_start"]
    country_disc = [d for d in data["discrepancies"] if d["field"] == "country"]

    # Get raw_data for period discrepancies
    site_ids = [d["id"] for d in period_disc]
    placeholders = ",".join(f"'{sid}'" for sid in site_ids)
    cur.execute(f"""
        SELECT id::text, name, period_start, raw_data->>'year' as raw_year
        FROM unified_sites WHERE id::text IN ({placeholders})
    """)
    raw_map = {row[0]: {"name": row[1], "period_start": row[2], "raw_year": row[3]} for row in cur.fetchall()}

    # Generate period fix SQL
    period_fixes = []
    for d in period_disc:
        sid = d["id"]
        db_val = int(d["db_value"])
        wd_val = int(d["wd_value"])
        raw = raw_map.get(sid, {})
        raw_year = raw.get("raw_year", "")
        name = raw.get("name", d["name"])

        parsed = parse_year_string(raw_year) if raw_year else None
        if parsed is None:
            continue

        db_diff = abs(db_val - parsed)
        if db_diff > max(100, abs(parsed) * 0.05 if parsed != 0 else 100):
            new_period_name = categorize_period(parsed)
            old_period_name = categorize_period(db_val)
            period_fixes.append({
                "id": sid,
                "name": name,
                "old_period_start": db_val,
                "new_period_start": parsed,
                "old_period_name": old_period_name,
                "new_period_name": new_period_name,
                "raw_year": raw_year,
                "evidence": f"raw_year='{raw_year}' -> parsed={parsed}"
            })

    # Country fixes
    country_fixes = [
        {"id": None, "name": "Achladia", "old": "Germany", "new": "Greece"},
        {"id": None, "name": "Ahuila Gencha Machay", "old": "Pakistan", "new": "Peru"},
        {"id": None, "name": "Aquae Helveticae", "old": "Sweden", "new": "Switzerland"},
        {"id": None, "name": "Tempio di Zeus, Selinunte", "old": "Greece", "new": "Italy"},
    ]
    # Resolve IDs
    for fix in country_fixes:
        for d in country_disc:
            if d["name"] == fix["name"]:
                fix["id"] = d["id"]
                break

    # Write SQL file
    with open("phase_b_fixes.sql", "w", encoding="utf-8") as f:
        f.write("-- ============================================================\n")
        f.write("-- Phase B Fixes: Period corrections from Wikidata verification\n")
        f.write(f"-- {len(period_fixes)} period fixes, {len(country_fixes)} country fixes\n")
        f.write("-- Applied: 2026-02-15\n")
        f.write("-- ============================================================\n\n")

        f.write(f"-- Block 3: Period corrections from raw_year re-parse ({len(period_fixes)} fixes)\n")
        f.write("-- These sites had period_start set from wrong raw_data field.\n")
        f.write("-- The raw_year string clearly gives a different (correct) date.\n\n")

        for fix in period_fixes:
            safe_name = fix["name"].replace("'", "''")
            f.write(f"-- {fix['name']}: raw_year='{fix['raw_year']}' -> {fix['new_period_start']}\n")
            f.write(f"UPDATE unified_sites SET period_start = {fix['new_period_start']}, "
                    f"period_name = '{fix['new_period_name']}'\n")
            f.write(f"WHERE id = '{fix['id']}' AND period_start = {fix['old_period_start']} "
                    f"AND source_id = 'ancient_nerds';\n\n")

        f.write("\n-- Block 4: Country corrections from Wikidata verification\n\n")
        for fix in country_fixes:
            if fix["id"]:
                safe_name = fix["name"].replace("'", "''")
                f.write(f"-- {fix['name']}: {fix['old']} -> {fix['new']}\n")
                f.write(f"UPDATE unified_sites SET country = '{fix['new']}'\n")
                f.write(f"WHERE id = '{fix['id']}' AND country = '{fix['old']}' "
                        f"AND source_id = 'ancient_nerds';\n\n")

        # Audit log entries
        f.write("\n-- Audit log entries for period fixes\n")
        for fix in period_fixes:
            safe_name = fix["name"].replace("'", "''")
            safe_evidence = fix["evidence"].replace("'", "''")
            f.write(f"INSERT INTO database_audit_log (site_id, site_name, action, field_changed, "
                    f"old_value, new_value, confidence, evidence_source, changed_by)\n")
            f.write(f"VALUES ('{fix['id']}', '{safe_name}', 'fix', 'period_start', "
                    f"'{fix['old_period_start']}', '{fix['new_period_start']}', 'high', "
                    f"'Phase B: {safe_evidence}', 'claude_audit_20260215');\n")

        f.write("\n-- Audit log entries for country fixes\n")
        for fix in country_fixes:
            if fix["id"]:
                safe_name = fix["name"].replace("'", "''")
                f.write(f"INSERT INTO database_audit_log (site_id, site_name, action, field_changed, "
                        f"old_value, new_value, confidence, evidence_source, changed_by)\n")
                f.write(f"VALUES ('{fix['id']}', '{safe_name}', 'fix', 'country', "
                        f"'{fix['old']}', '{fix['new']}', 'high', "
                        f"'Phase B: Wikidata P17 confirms correct country', 'claude_audit_20260215');\n")

    print(f"Generated {len(period_fixes)} period fixes and {len(country_fixes)} country fixes")
    print(f"Written to phase_b_fixes.sql")

    # Summary
    print(f"\nPeriod fixes by magnitude:")
    small = sum(1 for f in period_fixes if abs(f["new_period_start"] - f["old_period_start"]) < 500)
    medium = sum(1 for f in period_fixes if 500 <= abs(f["new_period_start"] - f["old_period_start"]) < 2000)
    large = sum(1 for f in period_fixes if abs(f["new_period_start"] - f["old_period_start"]) >= 2000)
    print(f"  Small (<500 yr): {small}")
    print(f"  Medium (500-2000 yr): {medium}")
    print(f"  Large (>2000 yr): {large}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
