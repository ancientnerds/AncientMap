#!/bin/bash
# Continuously stream Docker container logs to ./logs/ (one file per container).
# Managed by systemd: ancientnerds-logs.service

LOGS_DIR="/var/www/ancientnerds/logs"
mkdir -p "$LOGS_DIR"

trap 'kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT

for container in ancient_nerds_api ancient_nerds_lyra ancient_nerds_db ancient_nerds_redis ancient_nerds_qdrant ancient_nerds_searxng; do
    # Only follow containers that exist
    if docker inspect "$container" >/dev/null 2>&1; then
        docker logs -f --tail 1000 "$container" >>"$LOGS_DIR/${container}.log" 2>&1 &
    fi
done

wait
