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
#
# Env vars:
#   DO_DRILL=1|0   default 1. 0 writes the dump + CSVs only (the nightly cron run).
#   KEEP=<n>       default 7.  how many of this script's stamp directories to retain.
#
# Exit codes: 0 = dump verified (and, when DO_DRILL=1, the drill passed), 1 = anything
# unverified. A non-zero exit from the nightly run means the safety net is gone - it is a
# real alert, not noise.
#
# Retention is built in and is not optional: a 654 MB dump per day fills the 98 GB of free
# space in about five months, and a full disk takes the DATABASE down, not just the backups.
# Only directories shaped "<date>_remediation" are ever pruned, so hand-made restore points
# such as 2026-09-19_pre-audit are safe from this script.

set -euo pipefail

STAMP="${1:-$(date +%Y-%m-%d)_remediation}"
# The backup root is overridable so the retention logic can be exercised against a synthetic
# directory tree (tests/remediation/test_prune_backups.py) instead of being trusted.
BACKUP_ROOT="${BACKUP_ROOT:-/var/www/ancientnerds/backups}"
# The nightly cron run sets DO_DRILL=0 because the drill costs ~2 min and 625 MB of container
# I/O; the weekly run keeps it at 1. Never leave the drill off permanently: it is the only
# thing that distinguishes a backup from a belief, so it must run at least once a week.
DO_DRILL="${DO_DRILL:-1}"
KEEP="${KEEP:-7}"
BASE="$BACKUP_ROOT/$STAMP"
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
# Guard before, not after: pg_dump needs room for a ~654 MB dump plus the CSVs on top of
# whatever is already there, and running out mid-dump leaves a truncated file that looks
# like a backup until someone tries to restore it.
FREE_KB=$(df -Pk "$BACKUP_ROOT" | awk 'NR==2{print $4}')
[ "$FREE_KB" -gt 5242880 ] || die "only $((FREE_KB/1024)) MB free on $BACKUP_ROOT - refusing to start"
log "stamp=$STAMP  dir=$BASE  free=$(df -h "$BACKUP_ROOT" | awk 'NR==2{print $4}')"

# ---------------------------------------------------------------- 1. full dump
log "1/4 full pg_dump (this is the restore point) ..."
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
log "2/4 targeted CSV dump of ${#Q[@]} tables ..."
# No `docker exec -i` here: if this script itself arrives over stdin, -i would eat the remainder.
for t in "${!Q[@]}"; do
  docker exec "$CTR" psql -U ancient_map -d ancient_map -c \
    "COPY (${Q[$t]}) TO STDOUT WITH CSV HEADER" </dev/null | gzip -6 > "$BASE/$t.csv.gz"
  # `wc -l` counts NEWLINES, not rows. A quoted CSV field may itself contain newlines, so this
  # number is slightly above the true row count. Measured 2026-09-20: unified_sites reported
  # 5,025 lines for 5,004 rows - exactly the 3,004... precisely: 5,004 rows + 1 header + 20
  # rows whose text contains a newline = 5,025. wiki_images is off by 1,221 for the same
  # reason. Useful as a "did this export change drastically" signal; useless as a row count, so
  # it is labelled as newlines and not as rows.
  log "    $t: $(du -h "$BASE/$t.csv.gz" | cut -f1) gz / $(zcat "$BASE/$t.csv.gz" | wc -l) newlines"
done

# ------------------------------------------------------------- 3. restore drill
# Delegate to the standalone drill script: it is deliberately re-runnable on its own, so the
# next person can re-verify this dump - or an older one - without taking a new one.
# The drill copies the dump into the container and runs the container's own pg_restore with
# the dump as a file argument. See the two failure notes at the top of 00_restore_drill.sh for
# why neither `docker exec -i ... < dump` nor a host-side pg_restore against 127.0.0.1 works.
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ "$DO_DRILL" = "1" ]; then
  log "3/4 restore drill -> $DRILL_DB ..."
  "$HERE/00_restore_drill.sh" "$STAMP" || die "restore drill failed - see $BASE/DRILL_REPORT.txt"
else
  log "3/4 restore drill SKIPPED (DO_DRILL=0). The dump is NOT verified by this run."
fi

# ------------------------------------------------------------------- 4. retention
# Delegated to 00_prune_backups.sh: it deletes directories, so its behaviour is tested rather
# than assumed (tests/remediation/test_prune_backups.py, plus a 20-case run on the VPS).
# It keeps the newest $KEEP "<date>_remediation" dirs and never touches anything else.
log "4/4 retention: keep the newest $KEEP '<date>_remediation' directories ..."
BACKUP_ROOT="$BACKUP_ROOT" KEEP="$KEEP" "$HERE/00_prune_backups.sh" "$STAMP" \
  || log "    retention reported a problem - continuing, the dump itself is intact"
log "    free now $(df -h "$BACKUP_ROOT" | awk 'NR==2{print $4}')"

log "done. dump=$BASE/database_$STAMP.dump  report=$BASE/DRILL_REPORT.txt"
