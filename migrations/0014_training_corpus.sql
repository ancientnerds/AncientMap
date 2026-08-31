-- Training corpus: durable capture of what Theo reads and how it reasons.
--
-- Everything here is write-only from the pipeline's perspective — no runtime
-- code reads these tables for control flow. They exist so that a future
-- Ancient Nerds domain model can be trained on material the pipeline
-- currently throws away: source full texts (the LLM only ever sees a capped
-- snippet) and the intermediate reasoning of a research run (specialist
-- findings, synthesis, debate, curator passes).
--
-- Deliberately NO foreign keys to research_requests: a user deleting a paper
-- must not erase the run provenance, which is the whole point of the corpus.

-- One row per (source, content version). A source re-fetched later with
-- changed text gets a second row; identical text is a no-op via the PK.
CREATE TABLE IF NOT EXISTS theo_source_archive (
    source_id        TEXT NOT NULL,  -- sha256(_normalize_url(url))[:12], same id the CitationRegistry uses
    content_hash     TEXT NOT NULL,  -- sha256(full_text); '' marks a TDM-reservation row with no body
    url              TEXT NOT NULL,  -- first-seen original URL (display form)
    domain           TEXT NOT NULL DEFAULT '',
    title            TEXT NOT NULL DEFAULT '',
    -- Extracted page text, UNCAPPED (the LLM prompt cap does not apply here).
    -- NULL only on TDM-reservation rows.
    full_text        TEXT,
    -- gzipped original HTML, so the corpus can be re-extracted later with
    -- better tooling than the current regex tag-stripper. NULL when the text
    -- did not come from an HTML fetch.
    raw_html_gz      BYTEA,
    text_chars       INTEGER NOT NULL DEFAULT 0,
    -- http_status = 0 with content_type = 'adapter/snippet' means the text is
    -- the abstract the search adapter returned and no page was ever fetched.
    http_status      INTEGER NOT NULL DEFAULT 0,
    content_type     TEXT NOT NULL DEFAULT '',
    fetched_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- TRUE when this document was fetched for the corpus only and never
    -- reached an LLM prompt.
    archive_only     BOOLEAN NOT NULL DEFAULT FALSE,
    -- Provenance, modelled on source_records: licence travels with the row.
    source_api       TEXT NOT NULL DEFAULT '',
    doi              TEXT NOT NULL DEFAULT '',
    authors          JSONB,
    venue            TEXT NOT NULL DEFAULT '',
    reliability_tier INTEGER NOT NULL DEFAULT 0,
    -- '' = unresolved. docs/TRAINING_DATA_POLICY.md excludes unresolved rows
    -- from any training export by default.
    license          TEXT NOT NULL DEFAULT '',
    license_source   TEXT NOT NULL DEFAULT '',  -- 'adapter' | 'domain_map' | 'manual' | ''
    -- Machine-readable TDM reservation (§44b(3) UrhG) as found AT FETCH TIME.
    -- Not reconstructable afterwards, which is why it is stored per document.
    tdm_opt_out      BOOLEAN NOT NULL DEFAULT FALSE,
    tdm_signal       TEXT NOT NULL DEFAULT '',  -- 'robots_txt' | 'tdmrep' | 'meta_tag' | 'check_failed' | ''
    tdm_checked_at   TIMESTAMPTZ,
    PRIMARY KEY (source_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_theo_source_archive_fetched
    ON theo_source_archive (source_id, fetched_at DESC);

-- Which run saw which source, under which query, and whether the finished
-- paper ended up citing it. Query -> source -> cited is retrieval training
-- material; it survives a paper deletion on purpose.
CREATE TABLE IF NOT EXISTS theo_source_archive_runs (
    request_id   TEXT NOT NULL,  -- '' for standalone passes that have no request row
    source_id    TEXT NOT NULL,
    angle_id     TEXT NOT NULL DEFAULT '',
    search_query TEXT NOT NULL DEFAULT '',
    cited        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (request_id, source_id)
);

-- Intermediate reasoning. One row per terminal step of a run, plus curator
-- and miner passes (which carry request_id = NULL).
CREATE TABLE IF NOT EXISTS research_artifacts (
    id         BIGSERIAL PRIMARY KEY,
    request_id TEXT,
    kind       TEXT NOT NULL,
    ref        TEXT NOT NULL DEFAULT '',  -- angle id, date, or '' — scopes `kind`
    payload    JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_artifacts_request
    ON research_artifacts (request_id, kind);
CREATE INDEX IF NOT EXISTS idx_research_artifacts_kind
    ON research_artifacts (kind, created_at DESC);

-- Copy of thinking_log rows taken immediately before the 90/365-day prune
-- deletes them. The feed keeps its audited retention; the corpus keeps the
-- content.
CREATE TABLE IF NOT EXISTS thinking_log_archive (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    summary     TEXT NOT NULL,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Copy of a research_requests row taken before a user DELETE. Stored as a
-- whole-row jsonb dump rather than a twin table on purpose: research_requests
-- gains columns via boot-time ALTERs, and a twin with a fixed column list
-- would break the delete endpoint the next time that happens.
CREATE TABLE IF NOT EXISTS research_requests_archive (
    id          UUID PRIMARY KEY,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row         JSONB NOT NULL
);
