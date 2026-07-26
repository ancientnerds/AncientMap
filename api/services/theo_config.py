"""Configuration for Theodore Furcade — async archaeological research agent."""

from __future__ import annotations

import os

THEO_PARALLEL_SLOTS = 1

# Discord role ID that grants access to Theo Research Lab.
# Set THEO_RESEARCHER_ROLE_ID in .env to the role ID.
# If left empty, the researcher gate is disabled (403 for all users).
THEO_RESEARCHER_ROLE_ID = os.getenv("THEO_RESEARCHER_ROLE_ID", "")
MAX_REQUESTS_PER_USER = 1

# Flat credit cost for a V2 convergence research run.
# Reserved up-front on submit, deducted on success, released on failure/cancel.
THEO_RESEARCH_COST = 600

# --- Quota watchdog (2026-06-28 plan, layer "active supervision") -----------
# 5h-rolling % thresholds for the quota watchdog tier classification.
# Above QUOTA_HEALTHY_PCT   => HEALTHY   (full speed)
# Above QUOTA_THROTTLE_PCT  => DEGRADED  (work proceeds, warning logged)
# Above QUOTA_FREEZE_PCT    => THROTTLED (crawl: concurrency 1, 60s delay —
#                              a run at 80% usage can still finish its
#                              synthesis on the remaining tail)
# Below or equal            => EXHAUSTED (limiter frozen, work paused)
#
# 2026-07-06 v2 (user): at 80% used, don't freeze — throttle. The crawl
# lets refill outpace burn, so runs drift back OUT of the band instead of
# dying in it. Only the last 5% — the reserve that keeps everything else
# on this key alive — is a hard freeze.
QUOTA_HEALTHY_PCT = 30
QUOTA_THROTTLE_PCT = 20
QUOTA_FREEZE_PCT = 5

# Hysteresis: once EXHAUSTED, the tier only recovers when the 5h window is
# back at or above this %. Without it the watchdog would unfreeze at 21%,
# the run would burn back down to 20% within minutes, and the freeze/thaw
# flapping would make no forward progress ("pause until the quota actually
# resets", not "pause until barely above the line").
QUOTA_RESUME_PCT = 50

# --- Weekly wall (2026-07-19) ------------------------------------------------
# MiniMax enforces a second, calendar-week budget (resets Monday 00:00 UTC)
# as error 2056 — independent of the 5h window the ladder above tracks.
# When the weekly budget is empty, every call 429s while the 5h window sits
# at 100% precisely BECAUSE nothing can burn it: on 07-08..07-12 the probe
# read "HEALTHY 5h=100 weekly=0" for three days and the batch gate fed 17
# tasks into guaranteed failures. At or below this % the tier is EXHAUSTED
# regardless of the 5h value. No hysteresis — the weekly % only refills at
# the Monday reset, so there is no boundary to flap around.
QUOTA_WEEKLY_FREEZE_PCT = 5

# A batch run (is_batch=TRUE) may only START when the weekly budget still
# fits a whole paper: ~19%/paper observed on the ENTITÄT batch, plus margin.
# Below this floor a fresh multi-hour run would just park in the weekly wall
# mid-run. UI submissions bypass the batch gate entirely and are protected
# by the tier ladder alone.
THEO_BATCH_MIN_WEEKLY_PCT = 25

# How often the watchdog probes /v1/token_plan/remains. The probe is cached
# 60s server-side (minimax_shared.probe_minimax_quota), so 60s is a
# reasonable cadence — faster just hammers the endpoint without new data.
QUOTA_PROBE_INTERVAL_S = 60

# A research run deferred because of quota: re-claim after this delay.
# Old behaviour was a hard-coded 5 min regardless of quota health, which
# created a tight loop of "re-claim -> hit quota -> re-defer". The
# watchdog can override this via set_deferred_backoff_s() during EXHAUSTED
# to a longer value, but the default stays at 5 min for HEALTHY.
DEFERRED_RETRY_BACKOFF_S = 300

# If a run has been 'deferred' for longer than this, give up and mark it
# 'failed' so the queue does not grow forever. Operator should already have
# been notified by the Discord webhook when the EXHAUSTED transition fired.
# 24h (was 6h): with the 6h batch-pacing gate a deferred row may legitimately
# wait several pacing slots for its retry — 6h would reap it right at the
# first slot boundary, and a weekly-quota trough needs overnight to recover.
DEFERRED_MAX_AGE_HOURS = 24

# Optional kill-switch: set THEO_WATCHDOG_DISABLED=1 to disable the watchdog
# without code changes. Read in theo_quota_monitor.start_watchdog().
THEO_WATCHDOG_DISABLED = os.getenv("THEO_WATCHDOG_DISABLED", "") == "1"

# How long to wait between Theo task runs. The 5h rolling quota is shared
# with Lyra; running tasks back-to-back drains the window to 1% (observed
# 2026-06-29 — 6 failed tasks consumed 2.7M of the 9.7M budget, then a
# single watchdog freeze killed the next 46 queued tasks for hours).
# 30s is enough to let the probe catch up and surface a DEGRADED/EXHAUSTED
# signal before the next task starts hammering the API.
THEO_INTER_TASK_BACKOFF_S = 30

# --- Batch pacing (2026-07-04) ----------------------------------------------
# Batch tasks (research_requests.is_batch = TRUE) may START at most once per
# this interval, measured start-to-start against the most recent started_at of
# ANY task (a manual UI run also burns the shared quota, so it pushes the next
# batch slot back). UI submissions bypass the gate and start immediately.
# 6h start-to-start = max 4 batch tasks/day — a run takes 3-4h, so the shared
# 5h window recovers between starts instead of draining mid-batch.
THEO_MIN_TASK_INTERVAL_S = int(os.getenv("THEO_MIN_TASK_INTERVAL_S", str(6 * 3600)))
