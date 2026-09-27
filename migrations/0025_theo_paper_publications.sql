-- 0025_theo_paper_publications.sql
--
-- The journal of every write the Claude publish path makes to a Theo paper
-- (spec docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md,
-- sections 2.6-2.9). pipeline/lyra/theo_publishing.py inserts one row per
-- publish, correction and video registration, in the same transaction as the
-- research_requests UPDATE; the IndexNow and Qdrant side effects that run after
-- the commit are recorded afterwards in side_effects.
--
-- WHY: research_requests is outside apply_remediation_change's allow-list
-- (migration 0022), so without this table a published or corrected paper leaves
-- no record of who wrote it, which input bundle it came from and which gates it
-- passed.
--
-- request_id is ON DELETE SET NULL: a journal row outlives its paper (DELETE
-- /api/theo/research/{id} archives and deletes the row).
--
-- The second statement indexes research_artifacts for the dossier reads
-- (latest row per request and kind).
--
-- LOCKING: a new, empty table; the FK takes a brief SHARE ROW EXCLUSIVE lock on
-- research_requests. The index build takes a SHARE lock on research_artifacts
-- (a few hundred rows). Forward-only and idempotent (IF NOT EXISTS everywhere).

BEGIN;

CREATE TABLE IF NOT EXISTS theo_paper_publications (
    id            BIGSERIAL PRIMARY KEY,
    request_id    UUID REFERENCES research_requests (id) ON DELETE SET NULL,
    action        TEXT        NOT NULL,
    slug          TEXT,
    writer        JSONB       NOT NULL,
    bundle_sha256 CHAR(64)    NOT NULL,
    gates         JSONB       NOT NULL,
    side_effects  JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT theo_paper_publications_action_vocab
        CHECK (action IN ('publish', 'correct', 'register_video')),
    CONSTRAINT theo_paper_publications_sha256_shape
        CHECK (bundle_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_theo_paper_publications_request
    ON theo_paper_publications (request_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_research_artifacts_request_kind_created
    ON research_artifacts (request_id, kind, created_at DESC);

COMMENT ON TABLE theo_paper_publications IS
    'One row per write of the Claude publish path (publish, correct, register_video): '
    'writer, input bundle hash, gate results and post-commit side effects '
    '(pipeline/lyra/theo_publishing.py).';

COMMIT;
