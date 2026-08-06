-- Idempotent credit-reservation release (audit 2026-08-05, P1-7).
-- Defer -> re-claim -> second defer/failure/stale-cleanup used to release the
-- same reservation repeatedly, draining reserved_credits held by OTHER
-- requests. The flag makes every release path exactly-once per request.

ALTER TABLE research_requests
    ADD COLUMN IF NOT EXISTS reservation_released BOOLEAN NOT NULL DEFAULT FALSE;

-- Terminal rows already had their release (or deduction); rows still in
-- flight (queued/running) hold a live reservation. Deferred rows released
-- at defer time, so they are marked released too.
UPDATE research_requests
SET reservation_released = TRUE
WHERE status IN ('completed', 'failed', 'cancelled', 'deferred');
