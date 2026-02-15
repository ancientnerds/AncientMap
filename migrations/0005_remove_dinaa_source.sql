-- Remove DINAA source entirely (no longer used)
DELETE FROM unified_sites WHERE source_id = 'dinaa';
DELETE FROM source_meta WHERE id = 'dinaa';
