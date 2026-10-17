-- 0030_source_meta_ancient_nerds_cc_by.sql
--
-- The curated Ancient Nerds site records are CC BY 4.0 (owner decision 2026-10-11), as terms.html,
-- LICENSE and the disclaimer already state. source_meta still said CC BY-SA 4.0, and
-- `UnifiedLoader._init_source_meta` never updates the licence of an existing row, so the
-- static exporter kept publishing the old licence in sources.json.
--
-- Site descriptions with a Wikipedia source line stay CC BY-SA 4.0; they carry their own licence
-- per site (raw_data._description_provenance) and are not covered by this row.
--
-- Forward-only and idempotent: re-running the file changes nothing.

UPDATE source_meta
SET license = 'CC BY 4.0', attribution = 'Ancient Nerds (ancientnerds.com)'
WHERE id = 'ancient_nerds';
