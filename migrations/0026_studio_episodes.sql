-- 0026_studio_episodes.sql
--
-- The render ledger for studio episodes (spec docs/superpowers/specs/
-- 2026-09-26-studio-and-claude-write-design.md, section 4.9): one row per rendered video,
-- written by `python -m pipeline.studio episode render` through
-- `docker exec -i ancient_nerds_api python -m pipeline.studio.ledger_cli --record`.
--
-- WHY: a published episode must stay traceable to what it asserts. The row keeps the sha256
-- of the case file and the script the video was rendered from, the voice, the pipeline commit
-- and the paper it belongs to, tied to exactly one file (video_sha256). Modelled on
-- site_shorts (0021): same status vocabulary and CHECKs.
--
-- paper_request_id is ON DELETE SET NULL: a ledger row outlives a deleted paper row.
--
-- renderer is the WebGL renderer string render.ts reported (spec 4.11: the proof that the
-- video was drawn on the NVIDIA RTX 3080, never the integrated AMD or software rendering).
--
-- status:
--     rendered   the file exists; not uploaded
--     published  uploaded: youtube_id and published_at are set (episode register-youtube)
--     withdrawn  must not be (or no longer be) published; status_reason says why
--
-- LOCKING: a new, empty table. The foreign key takes a brief SHARE ROW EXCLUSIVE lock on
-- research_requests (the deploy's lock_timeout of 20 s bounds the wait behind a worker
-- write). Forward-only and idempotent: CREATE ... IF NOT EXISTS only.

BEGIN;

CREATE TABLE IF NOT EXISTS studio_episodes (
    id                BIGSERIAL PRIMARY KEY,
    slug              TEXT          NOT NULL,
    paper_request_id  UUID REFERENCES research_requests (id) ON DELETE SET NULL,
    topic_type        TEXT          NOT NULL,
    casefile_sha256   TEXT          NOT NULL,
    script_sha256     TEXT          NOT NULL,
    voice_id          TEXT          NOT NULL,
    pipeline_commit   TEXT          NOT NULL,
    video_sha256      TEXT          NOT NULL,
    duration_s        NUMERIC(9, 3) NOT NULL,
    youtube_id        TEXT,
    status            TEXT          NOT NULL DEFAULT 'rendered',
    status_reason     TEXT,
    rendered_at       TIMESTAMPTZ   NOT NULL,
    renderer          TEXT          NOT NULL,
    published_at      TIMESTAMPTZ,
    recorded_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT studio_episodes_video_unique UNIQUE (video_sha256),
    CONSTRAINT studio_episodes_status_vocab
        CHECK (status IN ('rendered', 'published', 'withdrawn')),
    CONSTRAINT studio_episodes_topic_vocab
        CHECK (topic_type IN ('A', 'B', 'C', 'D')),
    CONSTRAINT studio_episodes_sha256_shape
        CHECK (casefile_sha256 ~ '^[0-9a-f]{64}$'
               AND script_sha256 ~ '^[0-9a-f]{64}$'
               AND video_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT studio_episodes_duration_positive CHECK (duration_s > 0),
    CONSTRAINT studio_episodes_published_has_upload
        CHECK (status <> 'published' OR (youtube_id IS NOT NULL AND published_at IS NOT NULL)),
    CONSTRAINT studio_episodes_withdrawn_has_reason
        CHECK (status <> 'withdrawn' OR status_reason IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_studio_episodes_paper ON studio_episodes (paper_request_id);
CREATE INDEX IF NOT EXISTS idx_studio_episodes_slug ON studio_episodes (slug);

COMMENT ON TABLE studio_episodes IS
    'One row per rendered studio episode: case file, script, voice and commit it was made '
    'from, tied to one file by video_sha256 (spec 4.9). Written by pipeline.studio.ledger_cli.';

COMMIT;
