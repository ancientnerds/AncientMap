"""Configuration for Theodore Furcade — async archaeological research agent."""

from __future__ import annotations

import os

THEO_PARALLEL_SLOTS = 1

# Discord role ID that grants access to Theo Research Lab.
# Set THEO_RESEARCHER_ROLE_ID in .env to the role ID.
# If left empty, the researcher gate is disabled (403 for all users).
THEO_RESEARCHER_ROLE_ID = os.getenv("THEO_RESEARCHER_ROLE_ID", "")
RESULT_TTL_HOURS = 24
MAX_REQUESTS_PER_USER = 1

# Flat credit cost for a V2 convergence research run.
# Reserved up-front on submit, deducted on success, released on failure/cancel.
THEO_RESEARCH_COST = 600

# --- Quota watchdog (2026-06-28 plan, layer "active supervision") -----------
# 5h-rolling % thresholds for the quota watchdog tier classification.
# Above QUOTA_HEALTHY_PCT   => HEALTHY  (work proceeds, no warnings)
# Above QUOTA_DEGRADED_PCT  => DEGRADED (work proceeds, warning logged)
# Below or equal            => EXHAUSTED (limiter frozen, work paused)
# Set conservatively: a real Theo run burns ~3-5M tokens; below 5% the
# run will not finish without hitting a quota 429.
QUOTA_HEALTHY_PCT = 30
QUOTA_DEGRADED_PCT = 5

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
DEFERRED_MAX_AGE_HOURS = 6

# Optional kill-switch: set THEO_WATCHDOG_DISABLED=1 to disable the watchdog
# without code changes. Read in theo_quota_monitor.start_watchdog().
THEO_WATCHDOG_DISABLED = os.getenv("THEO_WATCHDOG_DISABLED", "") == "1"
