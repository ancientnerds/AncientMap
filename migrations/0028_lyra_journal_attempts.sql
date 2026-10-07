-- 0028_lyra_journal_attempts.sql
--
-- The retry budget of the weekly journal, spent from the database.
--
-- WHY: on 2026-10-05 no journal appeared for the week of 2026-09-28. Three
-- attempts died in the LLM clustering step, the fourth was killed mid-cluster by
-- the 06:41 UTC deploy, and nothing retried: the attempt counter lived in
-- orchestrator.main's memory, so every deploy of that Monday (eight of them)
-- started a fresh "attempt 1/3", and should_generate_article() only opened on
-- Monday, so the Tuesday morning after the last crash was already too late.
--
-- One row per COVERED week — week_start is the Monday of the week the journal
-- writes about, not the Monday it runs on; the two differ by a week. The row is
-- written before the run starts, because a crashed attempt has already spent
-- quota. last_attempt_at spaces two attempts of the same week
-- (journal_attempts.RETRY_INTERVAL_S).
--
-- LOCKING: a new, empty table, no foreign keys, nothing to read — CREATE ... IF
-- NOT EXISTS only, so it takes no lock any running query cares about.
-- Forward-only and idempotent.

BEGIN;

CREATE TABLE IF NOT EXISTS lyra_journal_attempts (
    week_start      DATE        PRIMARY KEY,
    attempts        INTEGER     NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT lyra_journal_attempts_budget CHECK (attempts >= 0)
);

COMMENT ON TABLE lyra_journal_attempts IS
    'Attempts spent per covered week for the weekly journal. Written by '
    'pipeline.lyra.journal_attempts.claim_attempt() before each run, so a deploy '
    'cannot reset the budget and a crashed run still counts against it.';

COMMIT;