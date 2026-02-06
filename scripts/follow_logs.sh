#!/bin/bash
# Continuously stream Docker container logs to ./logs/ (one file per container).
# File lock ensures only one instance runs at a time.
#
# Uses per-container tracking: when a container is rebuilt (new ID), the old
# follower is killed and a new one starts with --since to capture all logs.

LOGS_DIR="/var/www/ancientnerds/logs"
LOCK_FILE="$LOGS_DIR/.follow_logs.lock"
CONTAINERS="ancient_nerds_api ancient_nerds_lyra ancient_nerds_db ancient_nerds_redis ancient_nerds_qdrant ancient_nerds_searxng"

mkdir -p "$LOGS_DIR"

# Ensure only one instance runs
exec 200>"$LOCK_FILE"
flock -n 200 || exit 0

trap 'kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT

# Track container IDs and follower PIDs
declare -A KNOWN_IDS
declare -A FOLLOWER_PIDS

while true; do
    for container in $CONTAINERS; do
        if ! docker inspect "$container" >/dev/null 2>&1; then
            continue
        fi

        current_id=$(docker inspect --format '{{.Id}}' "$container" 2>/dev/null)
        prev_id="${KNOWN_IDS[$container]:-}"

        # Already following this exact container instance
        if [ "$prev_id" = "$current_id" ]; then
            # Check the follower is still alive
            pid="${FOLLOWER_PIDS[$container]:-}"
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                continue
            fi
            # Follower died — restart it below
        fi

        # Kill old follower if container was rebuilt
        old_pid="${FOLLOWER_PIDS[$container]:-}"
        if [ -n "$old_pid" ]; then
            kill "$old_pid" 2>/dev/null
        fi

        KNOWN_IDS[$container]="$current_id"

        # Capture ALL logs from this container instance
        started_at=$(docker inspect --format '{{.State.StartedAt}}' "$container" 2>/dev/null)
        docker logs -f --since "$started_at" "$container" >>"$LOGS_DIR/${container}.log" 2>&1 &
        FOLLOWER_PIDS[$container]=$!
    done

    # Poll every 10 seconds for container rebuilds
    sleep 10
done
