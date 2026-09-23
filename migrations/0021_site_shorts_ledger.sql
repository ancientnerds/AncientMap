-- 0021_site_shorts_ledger.sql
--
-- The render ledger for site shorts (plan docs/procedures/SITES_DB_REMEDIATION_2026-09.md,
-- section 10.4): one row per rendered video, written by the render step
-- (pipeline/video/__main__.py -> pipeline/video/shorts_ledger.py).
--
-- WHY: "A published short is completely decoupled from the data state it asserts." The
-- render directory's site.json carries no timestamp, no hash and no data version, so once a
-- card text changes nobody can tell which video still speaks the old claim. The ledger keeps
-- the text the narration read (card_text_at_render + its sha256), the Commons images on
-- screen (image_ids = wiki_images.id, in order of appearance), the voice and the pipeline
-- commit, and ties them to exactly one file (video_sha256).
--
-- KEYED BY site_id, not by slugify(name): 16 curated sites share a name with another
-- (plan 10.6), and the shorts directory is named by the slug alone. slug is kept for
-- orientation only.
--
-- site_id is ON DELETE SET NULL, per the FK policy for unified_sites (api/main.py): a ledger
-- row outlives its site - that is when it matters most.
--
-- status:
--     rendered   the file exists; not uploaded
--     published  uploaded: youtube_id and published_at are set
--     withdrawn  must not be (or no longer be) published; status_reason says why
--                (e.g. the site left the E3 scope window, or its card text changed)
--
-- Forward-only and idempotent: CREATE ... IF NOT EXISTS only. A new, empty table - no lock on
-- any existing table except the brief SHARE ROW EXCLUSIVE the FK takes on unified_sites.

BEGIN;

CREATE TABLE IF NOT EXISTS site_shorts (
    id                   BIGSERIAL PRIMARY KEY,
    site_id              UUID REFERENCES unified_sites (id) ON DELETE SET NULL,
    slug                 TEXT        NOT NULL,
    rendered_at          TIMESTAMPTZ NOT NULL,
    card_text_at_render  TEXT        NOT NULL,
    card_text_sha256     TEXT        NOT NULL,
    image_ids            INTEGER[]   NOT NULL,
    voice_id             TEXT,
    pipeline_commit      TEXT,
    video_sha256         TEXT        NOT NULL,
    youtube_id           TEXT,
    published_at         TIMESTAMPTZ,
    status               TEXT        NOT NULL DEFAULT 'rendered',
    status_reason        TEXT,
    recorded_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT site_shorts_video_unique UNIQUE (video_sha256),
    CONSTRAINT site_shorts_status_vocab
        CHECK (status IN ('rendered', 'published', 'withdrawn')),
    CONSTRAINT site_shorts_sha256_shape
        CHECK (card_text_sha256 ~ '^[0-9a-f]{64}$' AND video_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT site_shorts_published_has_upload
        CHECK (status <> 'published' OR (youtube_id IS NOT NULL AND published_at IS NOT NULL)),
    CONSTRAINT site_shorts_withdrawn_has_reason
        CHECK (status <> 'withdrawn' OR status_reason IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_site_shorts_site ON site_shorts (site_id);

COMMENT ON TABLE site_shorts IS
    'One row per rendered site short: the card text, images, voice and commit it was made '
    'from, tied to one file by video_sha256 (plan 10.4). Written by the render step.';
COMMENT ON COLUMN site_shorts.image_ids IS
    'wiki_images.id of the stills on screen, in order of appearance.';

COMMIT;
