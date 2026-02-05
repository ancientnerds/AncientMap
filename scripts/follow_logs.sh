#!/bin/bash
# Continuously stream Docker container logs to ./logs/ (one file per container).
# Loops forever — survives container restarts.

LOGS_DIR="/var/www/ancientnerds/logs"
CONTAINERS="ancient_nerds_api ancient_nerds_lyra ancient_nerds_db ancient_nerds_redis ancient_nerds_qdrant ancient_nerds_searxng"

mkdir -p "$LOGS_DIR"
trap 'kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT

while true; do
    for container in $CONTAINERS; do
        if docker inspect "$container" >/dev/null 2>&1; then
            docker logs -f --tail 100 "$container" >>"$LOGS_DIR/${container}.log" 2>&1 &
        fi
    done
    # Wait for any follower to die (container restart), then re-attach all
    wait -n 2>/dev/null || sleep 5
    # Kill remaining followers before re-attaching
    kill $(jobs -p) 2>/dev/null
    sleep 2
done
