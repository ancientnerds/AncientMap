-- Measure what a research run ACTUALLY costs on the MiniMax plan (2026-08-07).
--
-- research_requests.total_tokens comes from the API `usage` field and misses
-- the adaptive reasoning tokens MiniMax bills — measured gap: factor ~7.7
-- (49.6M counted vs 382M actually burned in the week of 2026-08-03). Quota
-- planning on that number is dangerous; the batch gate's THEO_PAPER_COST_PCT
-- had to be hand-calibrated instead.
--
-- These columns snapshot the plan's absolute weekly balance (probe field
-- `weekly_remains_time`, in tokens) at run start and run end, so the real
-- cost is a subtraction. Both nullable: a probe failure must never block a
-- run, and historical rows have no measurement.

ALTER TABLE research_requests
    ADD COLUMN IF NOT EXISTS plan_weekly_remains_start BIGINT,
    ADD COLUMN IF NOT EXISTS plan_weekly_remains_end   BIGINT,
    ADD COLUMN IF NOT EXISTS plan_week_start_ms        BIGINT;
