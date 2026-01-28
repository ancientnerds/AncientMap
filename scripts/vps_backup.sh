#!/bin/bash
# Backup script for AncientMap VPS - run before deployments or unified_loader
#
# SECURITY: Database credentials are loaded from .env file or ~/.pgpass
# Never hardcode passwords in scripts!

set -e

BACKUP_DIR="/var/www/ancientnerds/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATA_DIR="/var/www/ancientnerds.com/data"
ENV_FILE="/var/www/ancientnerds/.env"

# Load database password from .env file (secure method)
if [ -f "$ENV_FILE" ]; then
    # Extract POSTGRES_PASSWORD from .env file
    export PGPASSWORD=$(grep -E "^POSTGRES_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -z "$PGPASSWORD" ]; then
        echo "ERROR: POSTGRES_PASSWORD not found in $ENV_FILE"
        exit 1
    fi
else
    # Fall back to .pgpass file (PostgreSQL standard)
    if [ ! -f ~/.pgpass ]; then
        echo "ERROR: No .env file found and no ~/.pgpass configured"
        echo "Please create $ENV_FILE with POSTGRES_PASSWORD or configure ~/.pgpass"
        exit 1
    fi
    echo "Using ~/.pgpass for authentication"
fi

mkdir -p "$BACKUP_DIR"

echo "=== AncientMap Backup - $TIMESTAMP ==="

# 1. Backup contributions.json
if [ -f "$DATA_DIR/contributions.json" ]; then
    cp "$DATA_DIR/contributions.json" "$BACKUP_DIR/contributions_${TIMESTAMP}.json"
    echo "✓ contributions.json backed up"
else
    echo "- No contributions.json found (OK if new install)"
fi

# 2. Backup database
pg_dump -U ancient_map -h localhost -p 5432 -Fc ancient_map > "$BACKUP_DIR/database_${TIMESTAMP}.dump"
if [ $? -eq 0 ]; then
    echo "✓ Database backed up"
else
    echo "✗ Database backup FAILED"
    exit 1
fi

# 3. Show backup sizes
echo ""
echo "Backups created:"
ls -lh "$BACKUP_DIR"/*_${TIMESTAMP}*

# 4. Cleanup old backups (keep last 10)
echo ""
echo "Cleaning up old backups (keeping last 10)..."
cd "$BACKUP_DIR"
ls -t contributions_*.json 2>/dev/null | tail -n +11 | xargs -r rm
ls -t database_*.dump 2>/dev/null | tail -n +11 | xargs -r rm

echo "=== Backup complete ==="
