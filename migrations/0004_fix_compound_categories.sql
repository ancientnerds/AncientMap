BEGIN;
UPDATE unified_sites SET site_type = 'pyramid complex'
  WHERE id = '885ee465-142a-4368-a08c-66295e94cfab';
UPDATE unified_sites SET site_type = 'cave structures'
  WHERE id = '3aa70cf2-d56b-4401-8a60-2cd12131827c';
COMMIT;
