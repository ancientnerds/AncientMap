#!/usr/bin/env bash
# Re-embed images for every public research paper, newest first, and stop
# before the MiniMax budget runs dry.
#
# WHY TWO QUOTA GATES
# The weekly budget is what Theo's Friday batch window competes for, but the
# 5-hour ROLLING window is what actually stops a backfill mid-paper: on
# 2026-08-31 the weekly still read 52% while the 5h window sat at 0% and the
# limiter froze in place with a six-hour wait cap, so the run slept instead of
# working. Both are checked before each paper; neither is checked during one,
# because abandoning a half-embedded paper wastes what it already spent.
#
# WHY IT IS NOT SAFE TO PUSH WHILE THIS RUNS
# The deploy skips rebuilding ancient_nerds_theo_worker only while a row in
# research_requests is 'running'. A backfill creates no such row, so the
# worker counts as idle, gets rebuilt, and takes this `docker exec` with it.
# If a deploy starts by accident, `gh run cancel <id>` still saves the run as
# long as the VPS HEAD has not moved yet.
#
# Usage (on the VPS, detached so an ssh drop can't kill it):
#   cd /var/www/ancientnerds
#   setsid nohup bash scripts/rework_paper_images.sh > /tmp/rework.log 2>&1 &
#   tail -f /tmp/rework_progress.log
#
# Re-running is safe and resumes where the budget stopped it: papers already
# reworked are simply done again, so pass SKIP_SLUGS to leave them alone.
set -uo pipefail

# Reserve for Theo: THEO_PAPER_COST_PCT says one research run costs ~25% of
# the weekly budget, and the batch window opens Friday.
MIN_WEEKLY=${MIN_WEEKLY:-35}
# Below this the limiter starts freezing between calls; a paper begun here
# would sleep more than it works. Waited out rather than stopped on.
MIN_5H=${MIN_5H:-25}
WAIT_STEP_S=${WAIT_STEP_S:-900}
MAX_WAIT_5H_S=${MAX_WAIT_5H_S:-28800}   # 8h — well past a full 5h window
SKIP_SLUGS="${SKIP_SLUGS:-}"
PROGRESS=${PROGRESS:-/tmp/rework_progress.log}
: > "$PROGRESS"

quota() {  # $1 = five_hour_remaining_percent | weekly_remaining_percent
    docker exec ancient_nerds_theo_worker python -c "
from pipeline.lyra.minimax_shared import probe_minimax_quota
print(int(probe_minimax_quota(force=True).get('$1') or -1))
" 2>/dev/null | tail -1
}

mapfile -t SLUGS < <(docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -tAc \
    "SELECT slug FROM research_requests
     WHERE is_public AND status='completed' AND slug IS NOT NULL
     ORDER BY published_at DESC" | tr -d '\r')

for slug in "${SLUGS[@]}"; do
    case " $SKIP_SLUGS " in *" $slug "*) continue;; esac

    w=$(quota weekly_remaining_percent)
    h=$(quota five_hour_remaining_percent)
    echo "[$(date -Is)] weekly=${w}% 5h=${h}% next=$slug" >> "$PROGRESS"

    # Fail CLOSED on an unreadable probe: -1 stops the run rather than
    # spending a budget we could not measure.
    if [ "${w:--1}" -lt "$MIN_WEEKLY" ] 2>/dev/null; then
        echo "[$(date -Is)] STOP: weekly ${w}% below the Theo reserve ${MIN_WEEKLY}%" >> "$PROGRESS"
        break
    fi
    # The 5h window is the one gate worth WAITING on: it is rolling, so it
    # refills by itself within hours, while the weekly budget only resets on
    # Monday. Stopping on it would end a run that just needed to sit still.
    waited=0
    while [ "${h:--1}" -lt "$MIN_5H" ] 2>/dev/null; do
        if [ "$waited" -ge "$MAX_WAIT_5H_S" ]; then
            echo "[$(date -Is)] STOP: 5h window still ${h}% after $((waited / 3600))h" >> "$PROGRESS"
            break 2
        fi
        echo "[$(date -Is)] 5h window ${h}% — waiting ${WAIT_STEP_S}s for it to refill" >> "$PROGRESS"
        sleep "$WAIT_STEP_S"
        waited=$((waited + WAIT_STEP_S))
        h=$(quota five_hour_remaining_percent)
    done

    log="/tmp/rework_${slug:0:40}.log"
    docker exec ancient_nerds_theo_worker python -m pipeline.lyra.backfill_probative_images \
        --slug "$slug" --replace --apply > "$log" 2>&1
    result=$(grep -aE "Images added|no images embedded|diverges from report" "$log" | tail -2 | tr '\n' ' ')
    echo "[$(date -Is)] DONE $slug :: ${result:-see $log}" >> "$PROGRESS"
done
echo "[$(date -Is)] RUN COMPLETE" >> "$PROGRESS"
