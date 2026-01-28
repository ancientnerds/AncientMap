#!/bin/bash
# Restore script for AncientMap VPS

BACKUP_DIR="/var/www/ancientnerds/backups"
DATA_DIR="/var/www/ancientnerds.com/data"

# Load database password from environment
if [ -f /var/www/ancientnerds/.env ]; then
    source /var/www/ancientnerds/.env
fi
export PGPASSWORD="${POSTGRES_PASSWORD:?Error: POSTGRES_PASSWORD not set. Source .env file first.}"

if [ -z "$1" ]; then
    echo "Usage: ./vps_restore.sh <timestamp>"
    echo ""
    echo "Available backups:"
    ls -la "$BACKUP_DIR"/*.dump 2>/dev/null | awk '{print $NF}' | sed 's/.*database_//' | sed 's/.dump//'
    exit 1
fi

TIMESTAMP=$1

echo "=== Restoring from backup: $TIMESTAMP ==="

# 1. Restore contributions.json
if [ -f "$BACKUP_DIR/contributions_${TIMESTAMP}.json" ]; then
    cp "$BACKUP_DIR/contributions_${TIMESTAMP}.json" "$DATA_DIR/contributions.json"
    echo "✓ contributions.json restored"
fi

# 2. Restore database
if [ -f "$BACKUP_DIR/database_${TIMESTAMP}.dump" ]; then
    echo "Restoring database (this may take a moment)..."
    pg_restore -U ancient_map -h localhost -p 5432 -d ancient_map -c "$BACKUP_DIR/database_${TIMESTAMP}.dump"
    echo "✓ Database restored"
fi

echo "=== Restore complete ==="
