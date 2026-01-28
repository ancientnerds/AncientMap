#!/bin/bash
# Daily backup of contributions.json - runs via cron at 3 AM

BACKUP_DIR="/var/www/ancientnerds/backups/contributions"
DATA_DIR="/var/www/ancientnerds.com/data"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

if [ -f "$DATA_DIR/contributions.json" ]; then
    cp "$DATA_DIR/contributions.json" "$BACKUP_DIR/contributions_${TIMESTAMP}.json"
    echo "[$(date)] ✓ Backed up contributions.json"

    # Keep only last 30 daily backups
    cd "$BACKUP_DIR"
    ls -t contributions_*.json 2>/dev/null | tail -n +31 | xargs -r rm
else
    echo "[$(date)] - No contributions.json found"
fi
