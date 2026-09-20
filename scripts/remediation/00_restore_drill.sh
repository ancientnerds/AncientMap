#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
#
# Restore drill: prove a pg_dump of the production database is actually restorable.
#
# Usage:  ./scripts/remediation/00_restore_drill.sh <stamp>
#
# Why this is its own script and not part of the backup run: an untested backup is a
# belief, not a safeguard, and the drill has to be re-runnable on demand - months later,
# against a dump taken by an older run, right before a risky migration.
#
# TWO FAILURES THAT COST RUNS ON 2026-09-20, both encoded here deliberately:
#
#   1. `docker exec` WITHOUT `-i` does not attach stdin to the container process at all.
#      Piping the dump in (`docker exec db pg_restore ... < dump`) therefore hands
#      pg_restore an EMPTY stdin, and it fails with the misleading
#          pg_restore: error: input file is too short (read 0, expected 5)
#      Because the drill only *warned* about pg_restore errors, it then compared row counts
#      against an empty scratch database - i.e. it reported on a database that was never
#      created. An untested backup is a belief; a backup tested this way is worse, because
#      it produces a green-looking report.
#
#   2. The obvious remedy - keep the dump on the HOST and let the host's pg_restore talk to
#      the published port (`pg_restore -h 127.0.0.1 -p 5432`) - DOES NOT WORK either:
#          pg_restore: error: connection to server at "127.0.0.1", port 5432 failed:
#          fe_sendauth: no password supplied
#      The container's pg_hba.conf ends with `host all all all scram-sha-256`, and a
#      connection arriving through Docker's port publication does NOT come from 127.0.0.1 -
#      it arrives from the Docker gateway (e.g. 172.17.0.1). So it misses the
#      `host all all 127.0.0.1/32 trust` line and is asked for a password. Inside the
#      container, `local all all trust` applies and no password is needed.
#
# THE METHOD THAT WORKS, and the only one this script uses: copy the dump INTO the container
# and run the container's own pg_restore with the dump as a FILE ARGUMENT. No stdin is
# involved in either direction, so failure 1 cannot recur, and no password is involved, so
# failure 2 cannot recur. Confirmed 2026-09-20: pg_restore exit=0, 654 MB restored in 1m37s,
# all row counts matching production.
#
# Version note: the container runs pg_restore 16.4, the host that took the dump runs 16.15.
# Both write and read the same PG16 archive format; the restore above proves the pairing
# works, so do not "fix" this by upgrading the container client.
#
# The dump copy needs ~625 MB inside the container; the drill removes it again on exit.
set -euo pipefail

STAMP="${1:-}"
[ -n "$STAMP" ] || { echo "usage: $0 <stamp>   (e.g. 2026-09-20_remediation)" >&2; exit 2; }

CTR=ancient_nerds_db
BASE="/var/www/ancientnerds/backups/$STAMP"
DUMP="$BASE/database_$STAMP.dump"
DRILL_DB="ancient_map_restore_drill_$$"
REPORT="$BASE/DRILL_REPORT.txt"
RESTORE_LOG="$BASE/DRILL_RESTORE.log"

TABLES=(unified_sites card_stats wiki_images site_content_links site_external_ids unified_site_names)

log() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "[$(date +%H:%M:%S)] FATAL: $*" >&2; exit 1; }

[ -f "$DUMP" ] || die "no dump at $DUMP"

# ---------------------------------------------------------- 1. is the archive readable?
# Independent of any database: if the file is truncated or not a pg_dump archive at all,
# say so here instead of discovering it through a confusing SQL error later.
log "1/4 reading the archive index ($(du -h "$DUMP" | cut -f1)) ..."
N_TOC=$(pg_restore --list "$DUMP" 2>"$RESTORE_LOG" | grep -c "TABLE DATA" || true)
[ "$N_TOC" -gt 0 ] || die "archive unreadable or has no table data - see $RESTORE_LOG"
log "    archive lists $N_TOC TABLE DATA entries"

# ---------------------------------------------------------- 2. empty scratch database
cleanup() {
  docker exec "$CTR" psql -U ancient_map -d postgres -q -c \
    "DROP DATABASE IF EXISTS $DRILL_DB" </dev/null >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "2/4 creating scratch database $DRILL_DB ..."
docker exec "$CTR" psql -U ancient_map -d postgres -q -c "DROP DATABASE IF EXISTS $DRILL_DB" </dev/null
docker exec "$CTR" psql -U ancient_map -d postgres -q -c "CREATE DATABASE $DRILL_DB" </dev/null

# ---------------------------------------------------------- 3. restore (container-side)
# docker cp, then pg_restore with the dump as its own file argument. See the two failure
# notes at the top of this file for why neither `docker exec -i ... < dump` nor a host-side
# pg_restore against 127.0.0.1 is used here.
log "3/4 copying the dump into the container and restoring into $DRILL_DB ..."
docker cp "$DUMP" "$CTR:/tmp/drill_$STAMP.dump" >/dev/null
DRILL_DUMP="/tmp/drill_$STAMP.dump"
# From here on the copy must be removed even if the restore fails, so register it now.
cleanup_inner() { docker exec "$CTR" rm -f "$DRILL_DUMP" >/dev/null 2>&1 || true; }
trap 'cleanup_inner; cleanup' EXIT
set +e
docker exec "$CTR" pg_restore -U ancient_map -d "$DRILL_DB" \
  --no-owner --no-acl "$DRILL_DUMP" > "$RESTORE_LOG" 2>&1
RC=$?
set -e
[ "$RC" -eq 0 ] || log "    pg_restore exit=$RC (see $RESTORE_LOG) - verifying row counts regardless"

# ---------------------------------------------------------- 4. did we actually get a schema?
# This is the guard the first version lacked: an "empty restore" must stop the run, not
# produce a nice-looking table of zeros.
MISSING=()
for t in "${TABLES[@]}"; do
  N=$(docker exec "$CTR" psql -U ancient_map -d "$DRILL_DB" -At -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_name='$t'" </dev/null) \
        || die "cannot query $DRILL_DB"
  [ "$N" = "1" ] || MISSING+=("$t")
done
[ "${#MISSING[@]}" -eq 0 ] || die "restore produced no schema for: ${MISSING[*]} - see $RESTORE_LOG"

log "4/4 comparing row counts ..."
{
  echo "restore drill  stamp=$STAMP  date=$(date -Is)  drill_db=$DRILL_DB"
  echo "dump bytes: $(stat -c%s "$DUMP")   archive TABLE DATA entries: $N_TOC   pg_restore exit=$RC"
  echo
  printf '%-28s %10s %10s %s\n' table source restored verdict
  FAIL=0
  for t in "${TABLES[@]}"; do
    SRC=$(docker exec "$CTR" psql -U ancient_map -d ancient_map -At -c "SELECT count(*) FROM $t" </dev/null)
    DST=$(docker exec "$CTR" psql -U ancient_map -d "$DRILL_DB" -At -c "SELECT count(*) FROM $t" </dev/null)
    V=OK; [ "$SRC" = "$DST" ] || { V="MISMATCH"; FAIL=1; }
    printf '%-28s %10s %10s %s\n' "$t" "$SRC" "$DST" "$V"
  done
  echo
  # pg_restore exit=1 can be normal when non-fatal ACL/owner warnings appear; a count
  # mismatch or a missing table is what actually matters, and the schema check in step 4
  # above already rejected a restore that produced nothing. Do not "fix" a non-zero exit
  # by suppressing it - look at $RESTORE_LOG and decide.
  if [ "$FAIL" -eq 0 ]; then
    echo "VERDICT: dump is restorable and matches production row-for-row."
  else
    echo "VERDICT: FAILED - do not proceed."
  fi
} | tee "$REPORT"

grep -q "VERDICT: dump is restorable" "$REPORT" || die "restore drill failed - see $REPORT"
log "drill PASSED - report: $REPORT"
