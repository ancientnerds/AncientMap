-- ============================================================
-- Phase C Fixes: Per-site research corrections
-- Applied: 2026-02-15
-- ============================================================

-- Block 5: Well-known site corrections from archaeological consensus

-- Gobekli Tepe: raw_year says "7th ml. BC" (-7000) but archaeological consensus
-- (UNESCO, Schmidt 2006, multiple peer-reviewed sources) places earliest construction
-- at ~9500 BC (10th millennium BC). Wikidata also gives -9999 (millennium precision).
UPDATE unified_sites SET period_start = -9500, period_name = '< 4500 BC'
WHERE id = (SELECT id FROM unified_sites WHERE name = 'Göbekli Tepe' AND source_id = 'ancient_nerds')
AND period_start = -7000;

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, 'Göbekli Tepe', 'fix', 'period_start', '-7000', '-9500', 'high',
'Phase C: UNESCO, Schmidt 2006, Wikidata Q207927. Archaeological consensus ~9500 BC. raw_year "7th ml. BC" is incorrect.',
'claude_audit_20260215'
FROM unified_sites WHERE name = 'Göbekli Tepe' AND source_id = 'ancient_nerds';

-- Block 6: Flag coord discrepancies for manual review
-- Per audit rules: do NOT auto-fix coordinates. Flag all 42 coord discrepancies.
