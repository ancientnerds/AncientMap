#!/usr/bin/env bash
# Rebuild the Theo worker as soon as it stops running a paper.
#
# WHY THIS EXISTS
# The deploy (.github/workflows/ci.yml) refuses to rebuild ancient_nerds_theo_worker
# while a research run is active — a paper costs 7-15h and ~9% of the weekly
# MiniMax budget, and a container recreate kills it (happened twice on
# 2026-08-07). The worker therefore keeps running the OLD image until some
# later deploy happens to catch it idle. When a fix must reach the worker
# without waiting for that coincidence, run this after the deploy: it waits
# for the run in flight to finish, then swaps the container in.
#
# ORDER MATTERS: build FIRST, swap second.
# `docker compose up -d --build` would build while the old worker keeps
# claiming — a build takes minutes, and a paper claimed in that window dies on
# the recreate. Building up front leaves only a seconds-wide gap between the
# idle check and the swap. Anything claimed inside that gap is reset to
# 'queued' by the worker's own startup recovery (theo_worker.py: "Recover
# orphaned requests left in 'running' state"), so at worst seconds of work
# are repeated -- never a 14h run.
#
# Usage (on the VPS, detached so an ssh drop can't kill it):
#   cd /var/www/ancientnerds
#   setsid nohup scripts/swap_theo_worker_when_idle.sh > /tmp/theo_swap.log 2>&1 &
#   tail -f /tmp/theo_swap.log
set -euo pipefail

POLL_SECONDS="${POLL_SECONDS:-60}"
MAX_WAIT_HOURS="${MAX_WAIT_HOURS:-20}"
COMPOSE_DIR="${COMPOSE_DIR:-/var/www/ancientnerds}"

cd "$COMPOSE_DIR"
deadline=$(( $(date +%s) + MAX_WAIT_HOURS * 3600 ))

# Same stamp the deploy uses. It sits AFTER the source COPY in the Dockerfile,
# so it busts no cache — it only makes the container report the build it runs.
export BUILD_HASH="$(git rev-parse --short HEAD)"

echo "[$(date -Is)] Building theo-worker image at $BUILD_HASH (old container keeps running)..."
docker compose build theo-worker
echo "[$(date -Is)] Build done. Waiting for the worker to go idle."

while :; do
    # Fail CLOSED: an unreadable count must never be treated as idle, or the
    # swap would kill the very run this script exists to protect.
    busy=$(docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -tAc \
        "SELECT COUNT(*) FROM research_requests WHERE status = 'running'" 2>/dev/null || echo "unknown")

    if [ "$busy" = "0" ]; then
        echo "[$(date -Is)] Worker idle — swapping container in."
        docker compose up -d --no-build theo-worker
        sleep 10
        docker ps --filter name=ancient_nerds_theo_worker \
                  --format 'table {{.Names}}\t{{.Status}}'
        echo "[$(date -Is)] Done. New code is live in the worker."
        exit 0
    fi

    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "[$(date -Is)] Gave up after ${MAX_WAIT_HOURS}h (running=$busy)." >&2
        echo "Worker still on the old image; the next idle deploy will pick it up." >&2
        exit 1
    fi

    echo "[$(date -Is)] running=$busy — waiting ${POLL_SECONDS}s"
    sleep "$POLL_SECONDS"
done
