#!/bin/bash
# Phase 1 input: pull a read-only snapshot of the curated corpus out of production.
#
# Produces output/remediation/snapshot/<table>.jsonl.gz plus MANIFEST.txt (row counts,
# sha256, production last_audited). Everything downstream (the ten deterministic tests)
# runs against THIS snapshot, never against the live database: it is reproducible, it
# does not keep 5,004 round trips against the VPS, and two runs are comparable.
#
# Strictly read-only. The only statements it sends are SELECTs.
#
# BUG FIXED 2026-09-20 - do not reintroduce `COPY (...) TO STDOUT` here.
#   The first version wrapped each query in COPY ... TO STDOUT, which applies COPY's
#   TEXT-format escaping on top of JSON that `row_to_json` had already escaped correctly.
#   A description containing a real `"` came back as `\"` from row_to_json, and COPY then
#   escaped the backslash into `\\"`. The file still had 5,004 lines and still matched its
#   own sha256, so the manifest looked perfect - but any JSON parser saw the `\\` as an
#   escaped backslash and the following `"` as the end of the string. Almost every row was
#   silently unparseable.
#   Letting psql print the row (`-A -t`, no COPY) emits the JSON verbatim. The validation
#   step at the end of this script exists so this can never pass unnoticed again.
#
# Usage:  ./01_export_snapshot.sh [outdir]
set -euo pipefail

OUT="${1:-output/remediation/snapshot}"
SSH_HOST="${SSH_HOST:-ancientnerds}"
PSQL="docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -q -t -A"

TABLES=(unified_sites card_stats wiki_images site_content_links site_external_ids unified_site_names)

mkdir -p "$OUT"
MAN="$OUT/MANIFEST.txt"

# One JSON object per line, filtered to the curated corpus so snapshot and backup
# describe the same rows. `row_to_json` keeps column names as-is, so a new column shows
# up here automatically.
declare -A Q=(
  [unified_sites]="SELECT row_to_json(t) FROM (SELECT * FROM unified_sites WHERE source_id='ancient_nerds') t"
  [card_stats]="SELECT row_to_json(t) FROM (SELECT c.* FROM card_stats c JOIN unified_sites u ON u.id=c.site_id WHERE u.source_id='ancient_nerds') t"
  [wiki_images]="SELECT row_to_json(t) FROM (SELECT w.* FROM wiki_images w JOIN unified_sites u ON u.id=w.site_id WHERE u.source_id='ancient_nerds') t"
  [site_content_links]="SELECT row_to_json(t) FROM (SELECT l.* FROM site_content_links l JOIN unified_sites u ON u.id=l.site_id WHERE u.source_id='ancient_nerds') t"
  [site_external_ids]="SELECT row_to_json(t) FROM (SELECT e.* FROM site_external_ids e JOIN unified_sites u ON u.id=e.site_id WHERE u.source_id='ancient_nerds') t"
  [unified_site_names]="SELECT row_to_json(t) FROM (SELECT n.* FROM unified_site_names n JOIN unified_sites u ON u.id=n.site_id WHERE u.source_id='ancient_nerds') t"
)

{
  echo "snapshot exported $(date -Is)  host=$SSH_HOST"
  echo "format: one JSON object per line, gzip"
  echo
  printf '%-24s %10s  %s\n' table lines sha256
} > "$MAN"

for t in "${TABLES[@]}"; do
  # SC2029 (client-side expansion) is intended: ${Q[$t]} is a local bash array and must
  # be expanded here, before the string ever reaches ssh. Do not "fix" that.
  # shellcheck disable=SC2029
  ssh "$SSH_HOST" "$PSQL -c \"${Q[$t]}\" | gzip -6" > "$OUT/$t.jsonl.gz"
  N=$(zcat "$OUT/$t.jsonl.gz" | wc -l)
  H=$(sha256sum "$OUT/$t.jsonl.gz" | cut -c1-16)
  printf '%-24s %10s  %s\n' "$t" "$N" "$H" >> "$MAN"
  echo "  $t: $N lines"
done

# Anchor: if the corpus changes under us, the census numbers stop being comparable.
# shellcheck disable=SC2029
LAST=$(ssh "$SSH_HOST" "$PSQL -c \"SELECT max(last_audited) FROM unified_sites WHERE source_id='ancient_nerds'\"" 2>/dev/null | tr -d '\r')
{
  echo
  echo "production max(last_audited) for ancient_nerds: $LAST"
} >> "$MAN"

# ------------------------------------------------------------------ validation
# A snapshot that cannot be parsed is worse than no snapshot: it looks like evidence.
# Parse EVERY line (not a sample) and fail the export on the first bad row.
echo "validating ..."
PY="${PY:-./.venv/Scripts/python.exe}"
[ -x "$PY" ] || PY=python3
"$PY" - "$OUT" "${TABLES[@]}" <<'PYEOF'
import gzip, json, sys
from pathlib import Path

out = Path(sys.argv[1])
bad = 0
for table in sys.argv[2:]:
    p = out / f"{table}.jsonl.gz"
    n = 0
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                if bad < 3:
                    print(f"  INVALID {table}:{lineno}: {exc}")
                    print(f"          {line[max(0, exc.colno - 60):exc.colno + 40]!r}")
                bad += 1
    print(f"  {table}: {n} rows parsed" if not bad else f"  {table}: {n} rows, errors seen")
if bad:
    sys.exit(f"FATAL: {bad} unparseable row(s) - the snapshot is not usable")
print("all rows parse as JSON")
PYEOF

echo "manifest: $MAN"
cat "$MAN"
