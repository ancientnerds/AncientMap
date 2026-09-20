#!/bin/bash
# Phase 0 safeguard of the curated-sites remediation (docs/procedures/SITES_DB_REMEDIATION_2026-09.md).
#
# Runs ON THE VPS (inside /var/www/ancientnerds or anywhere; it only needs the .env and docker).
# Produces, in /var/www/ancientnerds/backups/<stamp>/:
#   1. database_<stamp>.dump      full custom-format pg_dump   (the real safety net)
#   2. <table>.csv.gz             CSV of the eight tables the audit may write to
#   3. DRILL_REPORT.txt           a TESTED restore: dump -> scratch DB -> row-count comparison
#
# The drill is the point of this script. An untested backup is not a backup.
#
# Usage:  ./00_backup_and_drill.sh [stamp]        (default stamp: <date>_remediation)
# Exit codes: 0 = dump + drill both verified, 1 = anything unverified.

set -euo pipefail

STAMP="${1:-$(date +%Y-%m-%d)_remediation}"
BASE="/var/www/ancientnerds/backups/$STAMP"
ENV_FILE="/var/www/ancientnerds/.env"
DRILL_DB="ancient_map_restore_drill_$$"
CTR="ancient_nerds_db"

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "FATAL: $*" >&2; exit 1; }

# ---------------------------------------------------------------- credentials
[ -f "$ENV_FILE" ] || die "no $ENV_FILE"
PGPASSWORD=$(grep -E "^POSTGRES_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
export PGPASSWORD
[ -n "$PGPASSWORD" ] || die "POSTGRES_PASSWORD empty in $ENV_FILE"
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=ancient_map

mkdir -p "$BASE"
log "stamp=$STAMP  dir=$BASE  free=$(df -h /var/www | awk 'NR==2{print $4}')"

# ---------------------------------------------------------------- 1. full dump
log "1/3 full pg_dump (this is the restore point) ..."
pg_dump -Fc -d ancient_map > "$BASE/database_$STAMP.dump"
DUMP_BYTES=$(stat -c %s "$BASE/database_$STAMP.dump")
[ "$DUMP_BYTES" -gt 100000000 ] || die "dump suspiciously small: $DUMP_BYTES bytes"
log "    dump: $DUMP_BYTES bytes"

# ------------------------------------------------------- 2. targeted CSV of the
# eight tables the remediation may write to. Faster to diff and to hand back to
# a human than a 1 GB custom dump.
declare -A Q=(
  [unified_sites]="SELECT * FROM unified_sites WHERE source_id='ancient_nerds'"
  [card_stats]="SELECT c.* FROM card_stats c JOIN unified_sites u ON u.id=c.site_id WHERE u.source_id='ancient_nerds'"
  [wiki_images]="SELECT w.* FROM wiki_images w JOIN unified_sites u ON u.id=w.site_id WHERE u.source_id='ancient_nerds'"
  [site_content_links]="SELECT l.* FROM site_content_links l JOIN unified_sites u ON u.id=l.site_id WHERE u.source_id='ancient_nerds'"
  [site_external_ids]="SELECT e.* FROM site_external_ids e JOIN unified_sites u ON u.id=e.site_id WHERE u.source_id='ancient_nerds'"
  [unified_site_names]="SELECT n.* FROM unified_site_names n JOIN unified_sites u ON u.id=n.site_id WHERE u.source_id='ancient_nerds'"
  [snapshot_rows]="SELECT * FROM snapshot_rows"
  [site_name_token_df]="SELECT * FROM site_name_token_df"
)
log "2/3 targeted CSV dump of ${#Q[@]} tables ..."
# No `docker exec -i` here: if this script itself arrives over stdin, -i would eat the remainder.
for t in "${!Q[@]}"; do
  docker exec "$CTR" psql -U ancient_map -d ancient_map -c \
    "COPY (${Q[$t]}) TO STDOUT WITH CSV HEADER" </dev/null | gzip -6 > "$BASE/$t.csv.gz"
  log "    $t: $(zcat "$BASE/$t.csv.gz" | wc -l) lines incl. header, $(du -h "$BASE/$t.csv.gz" | cut -f1)"
done

# ------------------------------------------------------------- 3. restore drill
# Delegate to the standalone drill script: it is deliberately re-runnable on its own,
# so the next person can re-verify this dump (or an older one) without taking a new one.
# The drill runs on the HOST's pg_restore against 127.0.0.1:5432 - see the pitfall note
# at the top of 00_restore_drill.sh for why piping the dump into `docker exec` silently
# restores an empty database.
log "3/3 restore drill -> $DRILL_DB ..."
HERE="$(cd "$(dirname "$0")" && pwd)"
"$HERE/00_restore_drill.sh" "$STAMP" || die "restore drill failed - see $BASE/DRILL_REPORT.txt"

log "done. dump=$BASE/database_$STAMP.dump  report=$BASE/DRILL_REPORT.txt"
