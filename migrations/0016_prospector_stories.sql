-- Prospector increment 2: stories as the steady-state source, the radar
-- backlog absorbed into the same queue, aliases decided by humans.
--
-- Additive only. Nothing here alters an existing column.

-- Which news items the story extractor has already read. Set for every item
-- it processes, mentions or not, so an item naming no place is not re-read
-- every week.
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS prospected_at TIMESTAMPTZ;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_items_unprospected
    ON news_items (id) WHERE prospected_at IS NULL;

-- Other names for the same place, recorded ONLY when a founder merges two
-- proposals ("SU Site" is "Mogollon Village"). Written to unified_site_names
-- as name_type='alias' on approve — the second of the two paths by which a
-- candidate name may ever enter that table, both human decisions.
ALTER TABLE site_proposals ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}';

-- A prior MACHINE verdict on the same name (the radar's LLM rejected a
-- proposed match, for example). Demotes rank and prints a badge; it never
-- hides a card, because 271 of the radar's 273 rejections were LLM calls,
-- not the founder.
ALTER TABLE site_proposals ADD COLUMN IF NOT EXISTS prior_verdict TEXT;
