#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-only
#
# Retention for /var/www/ancientnerds/backups, split out of 00_backup_and_drill.sh so that
# its deletion behaviour can be tested against synthetic directories instead of being trusted.
#
# A backup that fills the disk is not a safeguard: this VPS has ~98 GB free and one dump is
# ~654 MB, so an unpruned daily run takes the database down in about five months. Conversely,
# a pruner with an off-by-one silently deletes the only restore point that matters - which is
# why this is a separate script with its own test (tests/remediation/test_prune_backups.py)
# rather than four lines buried in a 100-line backup script.
#
# Usage:  ./00_prune_backups.sh <stamp-to-keep> [keep-count]
#         KEEP=7 (default)          how many of the newest stamp dirs to retain
#         BACKUP_ROOT=/var/www/ancientnerds/backups   override for testing
#         DRY_RUN=1                 print what would be deleted, delete nothing
#
# Safety rules, all deliberate:
#   * Only directories whose name ends in "_remediation" are candidates. Hand-made restore
#     points (2026-09-19_pre-audit) and anything else in the directory are never touched.
#   * The stamp passed in is never deleted, even if it falls outside the newest KEEP - so a
#     clock skew or a repeated run cannot delete the dump that was just taken.
#   * Sorting is by mtime via stat, not by parsing `ls` output (SC2012).
#   * BACKUP_ROOT must be an absolute path that is not "/" - a bad variable must not turn
#     this into a recursive delete of something that was never a backup directory.

set -euo pipefail

STAMP="${1:-}"
KEEP="${2:-${KEEP:-7}}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/www/ancientnerds/backups}"
DRY_RUN="${DRY_RUN:-0}"

die() { echo "prune-backups: FATAL: $*" >&2; exit 1; }

case "$BACKUP_ROOT" in
  /*) : ;;
  *) die "BACKUP_ROOT must be an absolute path, got '$BACKUP_ROOT'" ;;
esac
[ "$BACKUP_ROOT" != "/" ] || die "BACKUP_ROOT must not be /"
[ -d "$BACKUP_ROOT" ] || die "BACKUP_ROOT '$BACKUP_ROOT' is not a directory"
case "$KEEP" in
  ''|*[!0-9]*) die "keep-count must be a non-negative integer, got '$KEEP'" ;;
esac

PRUNED=0
# Newest first by mtime, then skip the first KEEP entries; everything after that is deleted.
mapfile -t CANDIDATES < <(
  for d in "$BACKUP_ROOT"/*_remediation; do
    [ -d "$d" ] || continue
    printf '%s\t%s\n' "$(stat -c %Y "$d")" "$d"
  done | sort -rn | cut -f2-
)

KEPT=0
for d in "${CANDIDATES[@]:-}"; do
  [ -n "$d" ] || continue
  if [ "$KEPT" -lt "$KEEP" ]; then
    KEPT=$((KEPT + 1))
    continue
  fi
  # Never delete the stamp we were told to protect, wherever it sorts.
  if [ "$(basename "$d")" = "$STAMP" ]; then
    echo "prune-backups: keeping $STAMP regardless of age"
    continue
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo "prune-backups: would delete $(basename "$d")"
  else
    rm -rf "$d"
    echo "prune-backups: deleted $(basename "$d")"
  fi
  PRUNED=$((PRUNED + 1))
done

if [ "$DRY_RUN" = "1" ]; then
  echo "prune-backups: kept $KEPT, pruned $PRUNED (dry run - nothing was deleted)"
else
  # Deliberately explicit: an operator must never have to wonder whether a deletion really
  # happened. A bare "${DRY_RUN:+ (dry run)}" tested only whether the variable was SET, so it
  # printed "(dry run)" on real runs too (found 2026-09-20 on the VPS).
  echo "prune-backups: kept $KEPT, pruned $PRUNED (deleted)"
fi
