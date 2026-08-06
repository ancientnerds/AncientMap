-- One-time cleanup, moved out of api/main.py startup (audit 2026-08-05):
-- the regexp UPDATE scanned all ~750K unified_sites rows on EVERY API boot
-- under a 30s statement_timeout — and was silently skipped forever when it
-- timed out. As a registry-tracked migration it runs exactly once, without
-- the startup timeout.

UPDATE unified_sites
SET description = regexp_replace(description, '\s*\[\d+\]', '', 'g')
WHERE description ~ '\[\d+\]'
  AND NOT jsonb_exists(COALESCE(raw_data, '{}'), 'description_citations');
