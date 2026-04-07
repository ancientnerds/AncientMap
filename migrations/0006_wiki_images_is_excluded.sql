-- Add is_excluded flag to wiki_images for soft-delete (prevents re-fetching by connectors)
ALTER TABLE wiki_images ADD COLUMN IF NOT EXISTS is_excluded BOOLEAN NOT NULL DEFAULT false;
