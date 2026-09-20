#!/bin/bash
# Gezielte Sicherung der kuratierten ancient_nerds-Daten vor dem DB-Audit.
# Nur lesend gegen die DB; schreibt ausschliesslich nach /var/www/ancientnerds/backups/.
set -euo pipefail

STAMP="2026-09-19_pre-audit"
DIR="/var/www/ancientnerds/backups/$STAMP"
mkdir -p "$DIR"

# Kein "docker exec -i": das Skript kommt selbst ueber stdin, ein -i wuerde den Rest verschlucken.
PSQL="docker exec ancient_nerds_db psql -U ancient_map -d ancient_map"

dump() {
  local name="$1" query="$2"
  $PSQL -c "COPY ($query) TO STDOUT WITH CSV HEADER" </dev/null | gzip -6 > "$DIR/$name.csv.gz"
  echo "$name: $(zcat "$DIR/$name.csv.gz" | wc -l) Zeilen (inkl. Kopf), $(du -h "$DIR/$name.csv.gz" | cut -f1)"
}

dump unified_sites \
  "SELECT * FROM unified_sites WHERE source_id = 'ancient_nerds'"
dump card_stats \
  "SELECT c.* FROM card_stats c JOIN unified_sites u ON u.id = c.site_id WHERE u.source_id = 'ancient_nerds'"
dump wiki_images \
  "SELECT w.* FROM wiki_images w JOIN unified_sites u ON u.id = w.site_id WHERE u.source_id = 'ancient_nerds'"
dump site_content_links \
  "SELECT l.* FROM site_content_links l JOIN unified_sites u ON u.id = l.site_id WHERE u.source_id = 'ancient_nerds'"
dump site_external_ids \
  "SELECT e.* FROM site_external_ids e JOIN unified_sites u ON u.id = e.site_id WHERE u.source_id = 'ancient_nerds'"
dump unified_site_names \
  "SELECT n.* FROM unified_site_names n JOIN unified_sites u ON u.id = n.site_id WHERE u.source_id = 'ancient_nerds'"

echo "---"
du -sh "$DIR"
ls -la "$DIR"
