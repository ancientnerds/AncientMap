-- 0024_site_search_trigram.sql
--
-- Trigram indexes for the site search (/api/sites/search, api/routes/sites.py search_sites).
--
-- WHY THIS FILE EXISTS
-- Every search matched the query as a substring of name_normalized over all 1.76M rows of
-- unified_sites: a parallel seq scan, measured 2026-09-25 on production at ~1.4 s per uncached
-- query. The search now also matches a query word by word ("the valley of kings, egypt" found
-- nothing, and was typed by visitors), which as a seq scan took 2.5-3.4 s. pg_trgm is installed;
-- a GIN index with gin_trgm_ops serves LIKE '%...%' and the word-start regex (~ '\m...') of both
-- the name and its spaceless form ("gobeklitepe" for "gobekli tepe").
--
-- name_normalized is maintained as left(lower(unaccent(name)), 500) (pipeline/lyra/site_key.py),
-- so the search compares against the column itself and needs no expression index for the
-- accents; the spaceless form mirrors idx_us_name_spaceless (0015).
--
-- LOCKING: CONCURRENTLY, as in 0015. The deploy runs this file with psql -f (each statement its
-- own transaction, which CONCURRENTLY requires), lock_timeout=20s and statement_timeout=600s.
-- A CONCURRENTLY build that fails leaves an INVALID index behind, which IF NOT EXISTS would then
-- skip forever; the file is only recorded as applied after it succeeded, so the DROP makes the
-- rerun build it again. Additive only: no row and no existing index changes.

DROP INDEX CONCURRENTLY IF EXISTS idx_us_name_trgm;
CREATE INDEX CONCURRENTLY idx_us_name_trgm
    ON unified_sites USING gin (name_normalized gin_trgm_ops);

DROP INDEX CONCURRENTLY IF EXISTS idx_us_name_spaceless_trgm;
CREATE INDEX CONCURRENTLY idx_us_name_spaceless_trgm
    ON unified_sites USING gin ((replace(name_normalized, ' ', '')) gin_trgm_ops);
