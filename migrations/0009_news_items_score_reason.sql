-- Store the LLM's editorial judgment for why a story got its significance score
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS score_reason TEXT;
