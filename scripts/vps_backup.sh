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
# theo_source_archive holds the training corpus: large, append-only, and only
# reproducible by re-crawling the web. Its DATA is excluded here so that ten
# daily dumps do not carry ten copies of it — the table definition stays in
# the dump, so a restore still yields a working schema. The corpus gets its
# own, less frequent dump below.
pg_dump -U ancient_map -h localhost -p 5432 -Fc \
    --exclude-table-data='public.theo_source_archive' \
    ancient_map > "$BACKUP_DIR/database_${TIMESTAMP}.dump"
if [ $? -eq 0 ]; then
    echo "✓ Database backed up"
else
    echo "✗ Database backup FAILED"
    exit 1
fi

# 2b. Training corpus — weekly, keep 2. It grows slowly and never changes
# retroactively, so a daily copy would dominate the backup directory without
# improving what we could actually recover.
LATEST_CORPUS=$(ls -t "$BACKUP_DIR"/corpus_*.dump 2>/dev/null | head -1)
if [ -z "$LATEST_CORPUS" ] || [ -n "$(find "$LATEST_CORPUS" -mtime +6 2>/dev/null)" ]; then
    pg_dump -U ancient_map -h localhost -p 5432 -Fc \
        -t 'public.theo_source_archive' \
        ancient_map > "$BACKUP_DIR/corpus_${TIMESTAMP}.dump"
    echo "✓ Training corpus backed up"
else
    echo "- Training corpus dump still fresh (weekly cadence)"
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
ls -t corpus_*.dump 2>/dev/null | tail -n +3 | xargs -r rm

echo "=== Backup complete ==="
