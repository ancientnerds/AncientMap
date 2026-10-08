-- 0029_unified_sites_spoken_name.sql
--
-- Add unified_sites.spoken_name: the short English form of a site's name that the narrator speaks
-- in a Short ("Machu Picchu, Peru."), owner decision D23 (2026-10-08). `name` stays the site's
-- name on its page; a name such as "Tiwanaku, Akapana (pyramid) 2" is read badly aloud.
--
-- NULL means "not set": pipeline/video/shorts_tts.spoken_name then speaks `name` as before. The
-- remediation lane `spoken-<wave>` fills it, wave by wave, each write journalled.
--
-- A plain column and not a raw_data key: four writers already share raw_data (provenance,
-- citations, check, card) and its lanes compare the whole jsonb.
--
-- LOCKING: ADD COLUMN of a nullable column without a default is a catalog change only (PostgreSQL
-- 16): no table rewrite, a momentary ACCESS EXCLUSIVE lock. The deploy runs it with lock_timeout.
-- Forward-only and idempotent: re-running the file changes nothing.

ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS spoken_name text NULL;

COMMENT ON COLUMN unified_sites.spoken_name IS
    'Short English name the narrator speaks in a Short (D23). NULL = not set, name is spoken. '
    'Written by the remediation lane spoken-<wave>; read by pipeline/video/shorts_export.';
