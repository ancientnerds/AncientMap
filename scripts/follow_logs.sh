#!/bin/bash
# Continuously stream Docker container logs to ./logs/ (one file per container).
# File lock ensures only one instance runs at a time.
#
# Uses per-container tracking: when a container is rebuilt (new ID), the old
# follower is killed and a new one starts from that container's start, so no
# line is lost. When only the FOLLOWER died and the container is unchanged, the
# new one starts at --tail 0: replaying from the container's start appended the
# whole history again, every time. Measured 2026-09-19 on the Qdrant log: 26.6M
# lines, 500k of them unique — 98 % duplicates, 4.5 GB.
#
# Docker's own json logs are capped (docker-compose.yml: max-size 10m,
# max-file 3); these copies were not, so they grew without limit. MAX_BYTES
# now trims each file in place, which keeps the appending file descriptor
# valid — renaming it would leave the follower writing into the rotated file.

LOGS_DIR="/var/www/ancientnerds/logs"
LOCK_FILE="$LOGS_DIR/.follow_logs.lock"
#: Trim a log once it passes this, down to KEEP_BYTES of its tail.
MAX_BYTES=$((256 * 1024 * 1024))
KEEP_BYTES=$((64 * 1024 * 1024))
# Note: ancient_nerds_lyra excluded — it writes its own log file via
# RotatingFileHandler to /app/logs/ (same volume). Including it here
# would duplicate every line.
CONTAINERS="ancient_nerds_api ancient_nerds_db ancient_nerds_redis ancient_nerds_qdrant ancient_nerds_searxng"

mkdir -p "$LOGS_DIR"

# Ensure only one instance runs
exec 200>"$LOCK_FILE"
flock -n 200 || exit 0

trap 'kill $(jobs -p) 2>/dev/null; exit 0' SIGTERM SIGINT

# Track container IDs and follower PIDs
declare -A KNOWN_IDS
declare -A FOLLOWER_PIDS

# Keep the tail of any log that grew past MAX_BYTES. The rewrite goes through a
# temp file and back with `cat >`, which truncates the original in place: the
# follower's append handle keeps writing to the same inode.
trim_logs() {
    for container in $CONTAINERS; do
        local file="$LOGS_DIR/${container}.log"
        [ -f "$file" ] || continue
        local size
        size=$(stat -c %s "$file" 2>/dev/null) || continue
        [ "$size" -gt "$MAX_BYTES" ] || continue
        if tail -c "$KEEP_BYTES" "$file" >"$file.trim" 2>/dev/null; then
            cat "$file.trim" >"$file"
            echo "[follow_logs] trimmed ${container}.log from $size to $KEEP_BYTES bytes" >&2
        fi
        rm -f "$file.trim"
    done
}

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

        if [ "$prev_id" = "$current_id" ]; then
            # Same container, dead follower: everything up to here is already
            # in the file. Starting from the container's start would append it
            # all a second time.
            docker logs -f --tail 0 "$container" >>"$LOGS_DIR/${container}.log" 2>&1 &
        else
            # New container instance: capture it from its own start.
            KNOWN_IDS[$container]="$current_id"
            started_at=$(docker inspect --format '{{.State.StartedAt}}' "$container" 2>/dev/null)
            docker logs -f --since "$started_at" "$container" >>"$LOGS_DIR/${container}.log" 2>&1 &
        fi
        FOLLOWER_PIDS[$container]=$!
    done

    trim_logs

    # Poll every 10 seconds for container rebuilds
    sleep 10
done
