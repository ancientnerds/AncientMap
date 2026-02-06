#!/bin/bash
# Continuously stream Docker container logs to ./logs/ (one file per container).
# File lock ensures only one instance runs at a time.
# Uses --since with container start time so logs aren't lost on rebuild.

LOGS_DIR="/var/www/ancientnerds/logs"
LOCK_FILE="$LOGS_DIR/.follow_logs.lock"
CONTAINERS="ancient_nerds_api ancient_nerds_lyra ancient_nerds_db ancient_nerds_redis ancient_nerds_qdrant ancient_nerds_searxng"

mkdir -p "$LOGS_DIR"

# Ensure only one instance runs
exec 200>"$LOCK_FILE"
flock -n 200 || exit 0

trap 'kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT

while true; do
    for container in $CONTAINERS; do
        if docker inspect "$container" >/dev/null 2>&1; then
            # Use --since with container start time to capture ALL logs from this
            # container instance. Fixes the gap where --tail 0 missed startup logs
            # emitted between container rebuild and this script re-attaching.
            started_at=$(docker inspect --format '{{.State.StartedAt}}' "$container" 2>/dev/null)
            docker logs -f --since "$started_at" "$container" >>"$LOGS_DIR/${container}.log" 2>&1 &
        fi
    done
    wait
    sleep 5
done
