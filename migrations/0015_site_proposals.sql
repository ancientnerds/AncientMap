-- Site proposer ("Prospector"): places named in our own content, checked
-- against the curated set, queued for a human decision.
-- Design: docs/superpowers/specs/2026-09-14-site-proposer-design.md
--
-- Nothing here alters an existing table's schema. Every FK into
-- unified_sites is SET NULL (standing rule); the two proposal-owned tables
-- cascade from site_proposals, which is re-derivable.
--
-- Index builds run CONCURRENTLY: the deploy runner executes this file with
-- lock_timeout=20s and statement_timeout=600s, and a plain CREATE INDEX on
-- the 1.76M-row name tables would hold a SHARE lock for the whole build.
-- psql -f runs each statement in its own transaction, which CONCURRENTLY
-- requires.

-- 1. Functional indexes for the spaceless name key. site_matcher's
--    _match_site_ids fallback ran `replace(name_normalized,' ','') = ...`
--    as a parallel seq scan: 587k rows removed per worker, ~125 ms per
--    lookup, twice per radar match (measured 2026-09-14).
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_usn_name_spaceless
    ON unified_site_names ((replace(name_normalized, ' ', '')));
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_name_spaceless
    ON unified_sites ((replace(name_normalized, ' ', '')));

-- 2. Partial indexes over the curated set (5,004 rows) so every rung of the
--    dedup ladder that targets ancient_nerds is an index hit, not a filter
--    over 1.76M rows.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_an_geom
    ON unified_sites USING gist (geom) WHERE source_id = 'ancient_nerds';
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_us_an_namekey
    ON unified_sites (name_normalized) WHERE source_id = 'ancient_nerds';

-- 3. Hard identifiers of curated sites: the enwiki title (after redirect
--    resolution) and the Wikidata QID. Populated by
--    pipeline.lyra.prospector.external_ids.refresh_site_external_ids.
--    Deliberately NOT unique on (kind, value): 115 curated rows share an
--    enwiki title with another curated row (pre-existing duplicates), so a
--    lookup returns a SET and a set of size > 1 is never decisive.
CREATE TABLE IF NOT EXISTS site_external_ids (
    site_id      UUID NOT NULL REFERENCES unified_sites(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ('wikidata_qid', 'enwiki_title')),
    value        TEXT NOT NULL,
    resolved_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (site_id, kind, value)
);
CREATE INDEX IF NOT EXISTS idx_sei_lookup ON site_external_ids (kind, value);

-- 4. Proposals. One row per real-world place, keyed on the hard identifier
--    when there is one and on (name key, country) when there is not — the
--    country scope stops two real "Glenwood"s collapsing into one card.
CREATE TABLE IF NOT EXISTS site_proposals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    name_key            TEXT NOT NULL,
    resolved_label      TEXT,
    wikidata_qid        TEXT,
    enwiki_title        TEXT,
    place_class         TEXT NOT NULL,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    geom                geometry(Point, 4326),
    coord_precision     DOUBLE PRECISION,
    location_rung       TEXT NOT NULL,
    country             TEXT,
    country_in_text     TEXT,
    site_type           TEXT,
    period_start        INT,
    period_end          INT,
    period_name         TEXT,
    period_phrase       TEXT,
    description         TEXT,
    thumbnail_url       TEXT,
    source_url          TEXT,
    wikipedia_url       TEXT,
    status              TEXT NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'needs_decision', 'have_it', 'approved',
                                          'merged', 'rejected', 'out_of_scope', 'not_a_place')),
    dedup_verdict       TEXT NOT NULL,
    dedup_trace         JSONB NOT NULL DEFAULT '[]'::jsonb,
    scope_verdict       TEXT NOT NULL,
    resolution_note     TEXT,
    resolution_path     TEXT,
    an_site_id          UUID REFERENCES unified_sites(id) ON DELETE SET NULL,
    external_site_id    UUID REFERENCES unified_sites(id) ON DELETE SET NULL,
    external_source_id  TEXT,
    contribution_id     UUID REFERENCES user_contributions(id) ON DELETE SET NULL,
    promoted_site_id    UUID REFERENCES unified_sites(id) ON DELETE SET NULL,
    merged_into_site_id UUID REFERENCES unified_sites(id) ON DELETE SET NULL,
    evidence_count      INT NOT NULL DEFAULT 0,
    corpus_kinds        TEXT NOT NULL DEFAULT '',
    reviewed_by         TEXT,
    reviewed_at         TIMESTAMPTZ,
    review_notes        TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sp_qid
    ON site_proposals (wikidata_qid) WHERE wikidata_qid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sp_enwiki
    ON site_proposals (enwiki_title) WHERE enwiki_title IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sp_namekey
    ON site_proposals (name_key, COALESCE(country, ''))
    WHERE wikidata_qid IS NULL AND enwiki_title IS NULL;
CREATE INDEX IF NOT EXISTS idx_sp_status_rank
    ON site_proposals (status, evidence_count DESC);
CREATE INDEX IF NOT EXISTS idx_sp_geom ON site_proposals USING gist (geom);

-- 5. Evidence: one row per verbatim sentence in our own content that names
--    the place. char offsets index the stored source text exactly, so the
--    review UI can deep-link to the sentence.
CREATE TABLE IF NOT EXISTS site_proposal_evidence (
    id            BIGSERIAL PRIMARY KEY,
    proposal_id   UUID NOT NULL REFERENCES site_proposals(id) ON DELETE CASCADE,
    corpus        TEXT NOT NULL CHECK (corpus IN ('paper', 'story', 'radar', 'entities_legacy')),
    source_table  TEXT NOT NULL,
    source_pk     TEXT NOT NULL,
    mentioned_as  TEXT NOT NULL,
    char_start    INT NOT NULL,
    char_end      INT NOT NULL,
    quote         TEXT NOT NULL,
    quote_start   INT NOT NULL,
    footnotes     INT[],
    locator       TEXT NOT NULL,
    extracted_by  TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_spe
    ON site_proposal_evidence (proposal_id, source_table, source_pk, char_start);
CREATE INDEX IF NOT EXISTS idx_spe_proposal ON site_proposal_evidence (proposal_id);

-- 6. Corpus-wide document frequency of name tokens, for the rare-shared-token
--    gate (G3): "great" appears in 1,959 site names and proves nothing;
--    "derinkuyu" appears in 6 and does. Refreshed by the same daily step that
--    maintains site_external_ids.
CREATE TABLE IF NOT EXISTS site_name_token_df (
    token     TEXT PRIMARY KEY,
    df        INT NOT NULL,
    built_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO site_name_token_df (token, df)
SELECT t, COUNT(*)
FROM unified_site_names, unnest(string_to_array(name_normalized, ' ')) AS t
WHERE t <> ''
GROUP BY t
ON CONFLICT (token) DO UPDATE SET df = EXCLUDED.df, built_at = NOW();
