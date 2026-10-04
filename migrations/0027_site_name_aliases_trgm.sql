-- 0027_site_name_aliases_trgm.sql
--
-- Trigram index over the multilingual names of a site (unified_site_names), for
-- the alias arm of /api/sites/search (api/routes/sites.py search_sites).
--
-- WHY THIS FILE EXISTS
-- A visitor who types a site in their own language ("Machu Picchu" as マチュ・ピチュ,
-- Μάτσου Πίτσου or माचू पिच्चू) found nothing: the search matched
-- unified_sites.name_normalized, the country and the word tier, and never the
-- other names the site carries in unified_site_names. Wikidata has a label in
-- 140 languages for that one site; the row for it existed, the query could not
-- see it.
--
-- The index is PARTIAL, over `name_type <> 'label'`, on purpose:
--   * the `label` rows (1,760,723 of them, one per site) are a mirror of
--     unified_sites.name, which the search already matches with a better rank.
--     Including them would put a 1.76M-row subset into a subquery that can only
--     return what the outer arms return anyway.
--   * the aliases are the part a search cannot get any other way, and they are
--     small: 94 rows before the backfill of 2026-10-04, ~100k after it. A
--     partial GIN index over that subset is a fraction of the size of a full
--     one and is what keeps the alias subquery an index scan.
--
-- name_normalized here is written with the same canonical expression that fills
-- the site column, left(lower(unaccent(name)), 500) (pipeline/lyra/site_key.py,
-- enforced in _store_wikidata_aliases), so the search's canonical binds match it
-- without any expression index for the accents.
--
-- LOCKING: CONCURRENTLY, as in 0024. The deploy runs this file with psql -f
-- (each statement its own transaction, which CONCURRENTLY requires),
-- lock_timeout=20s and statement_timeout=600s. A CONCURRENTLY build that fails
-- leaves an INVALID index behind, which IF NOT EXISTS would then skip forever;
-- the file is only recorded as applied after it succeeded, so the DROP makes a
-- rerun build it again. Additive only: no row and no existing index changes.

DROP INDEX CONCURRENTLY IF EXISTS idx_usn_alias_trgm;
CREATE INDEX CONCURRENTLY idx_usn_alias_trgm
    ON unified_site_names USING gin (name_normalized gin_trgm_ops)
    WHERE name_type <> 'label';
