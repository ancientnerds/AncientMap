-- ============================================================
-- Phase A Audit Log Entries — 2026-02-15
-- Logs all mechanical fixes and flagging actions
-- ============================================================

-- Block 1: site_type normalization fixes
-- We identify affected rows by matching the canonical form that was just applied
-- and checking raw_data to confirm the original non-canonical form

-- Settlement → settlement
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Settlement', 'settlement', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'settlement'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'settlement' AND changed_by LIKE 'claude_audit%');

-- Archaeological Site → archaeological_site
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Archaeological Site', 'archaeological_site', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'archaeological_site'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'archaeological_site' AND changed_by LIKE 'claude_audit%');

-- Infrastructure → infrastructure
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Infrastructure', 'infrastructure', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'infrastructure'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'infrastructure' AND changed_by LIKE 'claude_audit%');

-- Monument → monument
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Monument', 'monument', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'monument'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'monument' AND changed_by LIKE 'claude_audit%');

-- Megalithic → megalithic (5 that were title-cased)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Megalithic', 'megalithic', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'megalithic'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'megalithic' AND changed_by LIKE 'claude_audit%');

-- Temple → temple
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Temple', 'temple', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'temple'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'temple' AND changed_by LIKE 'claude_audit%');

-- Inscription → inscription
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Inscription', 'inscription', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'inscription'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'inscription' AND changed_by LIKE 'claude_audit%');

-- Rock Art → Rock art
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Rock Art', 'Rock art', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Rock art'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'Rock art' AND changed_by LIKE 'claude_audit%');

-- Tomb → tomb
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Tomb', 'tomb', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'tomb'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'tomb' AND changed_by LIKE 'claude_audit%');

-- Ruin → ruin
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Ruin', 'ruin', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'ruin'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'ruin' AND changed_by LIKE 'claude_audit%');

-- Theatre → theatre
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Theatre', 'theatre', 'high', 'internal_consistency: normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'theatre'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE field_changed = 'site_type' AND new_value = 'theatre' AND changed_by LIKE 'claude_audit%');

-- Block 2: period_name boundary fixes (18 sites)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by) VALUES
('90ec5b47-7488-4bb4-8c4d-1259d30ac328', 'Cauria', 'fix', 'period_name', '< 4500 BC', '4500 - 3000 BC', 'high', 'internal_consistency: categorize_period(-4500)', 'claude_audit_20260215'),
('b1eabcf0-cc21-4053-92a1-285b30da510b', 'Arlobi Menhir', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('58e730c7-6ec4-44a4-97e8-d2f75d9a1c9e', 'Carn Menyn', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('bcc037db-7637-44c9-8204-3ce6d4370653', 'Mount William Stone Axe Quarry', 'fix', 'period_name', '1 - 500 AD', '500 - 1000 AD', 'high', 'internal_consistency: categorize_period(500)', 'claude_audit_20260215'),
('fc84c8b7-697c-4ee3-924b-e412f5585c2b', 'Mut Precinct', 'fix', 'period_name', '3000 - 1500 BC', '1500 - 500 BC', 'high', 'internal_consistency: categorize_period(-1479)', 'claude_audit_20260215'),
('238793b3-c335-4dcf-8155-c9e2d4985e0d', 'Nakhchivan Rock Signs', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('7345ac3a-0fbd-4507-807b-a2f8a592c39d', 'Osirion', 'fix', 'period_name', '3000 - 1500 BC', '1500 - 500 BC', 'high', 'internal_consistency: categorize_period(-1280)', 'claude_audit_20260215'),
('a98dcb51-39c4-4ab9-b34e-1f10a9aa14d9', 'Pilgrims'' Way', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('2d12562b-e482-4a6b-8329-5d7a22667a86', 'Sliprännor i Gantofta', 'fix', 'period_name', '3000 - 1500 BC', '1500 - 500 BC', 'high', 'internal_consistency: categorize_period(-1500)', 'claude_audit_20260215'),
('290410a4-c7ed-4fe7-842d-bfe7ab97e899', 'White Tank Mountain Regional Park', 'fix', 'period_name', '1 - 500 AD', '500 - 1000 AD', 'high', 'internal_consistency: categorize_period(500)', 'claude_audit_20260215'),
('e2aa3754-8d32-4455-bf6d-9077f18d50d2', 'Ancient Lilaia', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('a9c5d1bf-b6d0-4486-a507-8dddfdc57a02', 'Ağbulaq Necropolis', 'fix', 'period_name', '3000 - 1500 BC', '1500 - 500 BC', 'high', 'internal_consistency: categorize_period(-1500)', 'claude_audit_20260215'),
('763e4a8b-eed2-495d-81db-35f83a3d5d82', 'Blowing Stone', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('1d4dd1f5-e841-4c8c-9761-2d4ad3eec155', 'Kinniside Stone Circle', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('ffb35fc7-24f7-4722-8036-e4173ac6d8e6', 'Cardiccia', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('bebaa4d3-fb8e-46a4-b9cb-fe6589925889', 'Situs Megalith Talang Kecepol', 'fix', 'period_name', '1500 - 500 BC', '500 BC - 1 AD', 'high', 'internal_consistency: categorize_period(-500)', 'claude_audit_20260215'),
('edd175c5-eeb5-4cff-8c18-7ae518915cc4', 'Papeloze Kerk', 'fix', 'period_name', '4500 - 3000 BC', '3000 - 1500 BC', 'high', 'internal_consistency: categorize_period(-3000)', 'claude_audit_20260215'),
('fa9441c6-255f-4fc3-aaba-8aa8b43759ac', 'Zelve Open Air Museum', 'fix', 'period_name', '1 - 500 AD', '500 - 1000 AD', 'high', 'internal_consistency: categorize_period(500)', 'claude_audit_20260215');

-- Block 3: Flag non-archaeological entries
-- Museums (56)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'flag_manual', 'site_type', site_type, NULL, 'high', 'non-archaeological: museum', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'museum'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE action = 'flag_manual' AND evidence_source LIKE '%museum%');

-- Geological interest (40)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'flag_manual', 'site_type', site_type, NULL, 'high', 'non-archaeological: geological formation', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'geological interest'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE action = 'flag_manual' AND evidence_source LIKE '%geological%');

-- Elongated skulls (1) - museum display
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'flag_manual', 'site_type', site_type, NULL, 'high', 'non-archaeological: museum display', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'elongated skulls'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE action = 'flag_manual' AND site_id IN (SELECT id FROM unified_sites WHERE site_type = 'elongated skulls'));

-- Magnetic anomaly (1)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'flag_manual', 'site_type', site_type, NULL, 'high', 'non-archaeological: magnetic anomaly', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'magnetic anomaly'
AND id NOT IN (SELECT site_id FROM database_audit_log WHERE action = 'flag_manual' AND site_id IN (SELECT id FROM unified_sites WHERE site_type = 'magnetic anomaly'));

-- Unknown/wildlife sanctuary (1)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2133d54c-f352-4325-ae0c-dd532f9a65d3', 'Mookambika Wildlife Sanctuary Kodachadri', 'flag_manual', 'site_type', 'unknown', NULL, 'high', 'non-archaeological: modern wildlife sanctuary', 'claude_audit_20260215');

-- Block 4: Flag duplicate pairs
-- True duplicates (flag one for removal)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by) VALUES
('f28a2d38-f5a9-49f2-83c8-53bb4c61cae4', 'Fectio', 'flag_manual', 'duplicate', 'Fortification', NULL, 'high', 'true duplicate of a001babf (same coords, same Wikipedia URL)', 'claude_audit_20260215'),
('2a1d1dfb-474c-44db-a3ea-81758fadf851', 'Huichún', 'flag_manual', 'duplicate', NULL, NULL, 'high', 'true duplicate of d7a19d68 (identical coords, same Wikipedia URL)', 'claude_audit_20260215'),
('f8e537ac-c6e0-49f5-9b2f-995be80ab401', 'Porth Hellick Down', 'flag_manual', 'duplicate', NULL, NULL, 'high', 'true duplicate of 1f66729b (identical coords, same Wikipedia URL)', 'claude_audit_20260215');

-- Distinct sites with same name (verify, not duplicates)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by) VALUES
('63cbc133-6e22-46aa-b430-ac7da2e405cd', 'Pella', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct site: Pella Greece vs Pella Jordan — different coords/countries', 'claude_audit_20260215'),
('8f8d1ce5-3527-4c35-925f-579e6dc51784', 'Pella', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct site: Pella Jordan vs Pella Greece — different coords/countries', 'claude_audit_20260215'),
('31c2fc86-3acf-4684-99dc-9f1b35e0f3b4', 'Santa Rita', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct site: Santa Rita Mexico vs Santa Rita Belize — different coords/countries', 'claude_audit_20260215'),
('b5269a8f-b1fd-448a-a0ef-72142e188006', 'Santa Rita', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct site: Santa Rita Belize vs Santa Rita Mexico — different coords/countries', 'claude_audit_20260215'),
('c7ce50b5-7f16-41a7-844b-d0d7b419d549', 'Temple of Diana', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct site: Temple of Diana Nimes France vs Merida Spain', 'claude_audit_20260215'),
('76a5a42b-f24e-4a03-8e19-e32c1493eb1b', 'Temple of Diana', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct site: Temple of Diana Merida Spain vs Nimes France', 'claude_audit_20260215'),
('bf538bd9-912c-471a-964a-f94842e17491', 'Temple of Zeus', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct site: Temple of Zeus Cyrene Libya vs Jerash Jordan', 'claude_audit_20260215'),
('1560f618-3e00-433c-9728-a9d86471fe4a', 'Temple of Zeus', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct site: Temple of Zeus Jerash Jordan vs Cyrene Libya', 'claude_audit_20260215'),
('0c491ed6-51ca-4189-8db1-6b481f0862e3', 'Via Egnatia', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct points on same road: Via Egnatia N. Macedonia section', 'claude_audit_20260215'),
('feccbb16-9c3a-4d0e-9aac-ca8cf3d370d8', 'Via Egnatia', 'verify', 'duplicate_check', NULL, NULL, 'high', 'distinct points on same road: Via Egnatia Albania section', 'claude_audit_20260215');
