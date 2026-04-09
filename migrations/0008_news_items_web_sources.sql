-- Add web_sources column to news_items for storing verification reference links
ALTER TABLE news_items ADD COLUMN IF NOT EXISTS web_sources JSONB;
