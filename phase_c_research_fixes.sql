-- ============================================================
-- Phase C Research Fixes: Period dates from per-site research
-- Applied: 2026-02-15
-- ============================================================

-- HIGH confidence (1 site)

-- Blaskovina Archaeological Site: Roman municipium, 2nd-3rd century CE
-- Evidence: Serbian archaeological registry, Roman funerary monuments, Municipium Malvesatium
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD'
WHERE id = 'ea159045-9163-41c2-9026-71edd41683ec' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ea159045-9163-41c2-9026-71edd41683ec', 'Blaškovina Archaeological Site', 'fix', 'period_start', 'NULL', '100', 'high',
'Phase C research: Roman municipium (Municipium Malvesatium), 2nd-3rd c. CE funerary monuments. Serbian archaeological registry.',
'claude_audit_20260215');

-- MEDIUM confidence (7 sites)

-- Aya Muqu: Wari administrative context, Chipao District, Lucanas, Ayacucho
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD'
WHERE id = '134e6d5f-86de-4c3a-afc6-2959a360db15' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('134e6d5f-86de-4c3a-afc6-2959a360db15', 'Aya Muqu', 'fix', 'period_start', 'NULL', '600', 'medium',
'Phase C research: Wari administrative centers in Chipao District, Lucanas. Wari Empire 550-1000 CE. Cultural Heritage 2003.',
'claude_audit_20260215');

-- Bhagwan Bharat's Statue: Chandragiri, Shravanabelagola, earliest inscriptions 600 CE
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD'
WHERE id = '59267588-ef6b-40b7-9990-c93b2b6d08f4' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('59267588-ef6b-40b7-9990-c93b2b6d08f4', 'Bhagwan Bharat''s Statue', 'fix', 'period_start', 'NULL', '600', 'medium',
'Phase C research: Chandragiri hill, Shravanabelagola. Earliest inscriptions 600 CE. Bharata statue 600-900 CE range.',
'claude_audit_20260215');

-- Chipaw Marka: Same Wari context as Aya Muqu
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD'
WHERE id = 'c4446aa8-4d88-4d40-be5b-129bca6a68aa' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c4446aa8-4d88-4d40-be5b-129bca6a68aa', 'Chipaw Marka', 'fix', 'period_start', 'NULL', '600', 'medium',
'Phase C research: Chipao District, Lucanas, Wari context. Cultural Heritage 2003.',
'claude_audit_20260215');

-- Furby: Near Anundshog burial complex, radiocarbon 210-540 CE
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '6cc9e902-c82f-4b21-9f36-41c2b783cebc' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6cc9e902-c82f-4b21-9f36-41c2b783cebc', 'Furby', 'fix', 'period_start', 'NULL', '400', 'medium',
'Phase C research: Near Anundshog, largest tumulus in Sweden. Radiocarbon 210-540 CE. 12 burial mounds, 10 stone circles.',
'claude_audit_20260215');

-- Hatun Misapata: Lucanas Province, Sondondo Valley, Wari/Inca context
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD'
WHERE id = '706c0a4d-f0ba-4970-8744-176841caae61' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('706c0a4d-f0ba-4970-8744-176841caae61', 'Hatun Misapata', 'fix', 'period_start', 'NULL', '600', 'medium',
'Phase C research: Lucanas Province, Aucara District. Sondondo Valley Wari/Inca occupation. Cultural Heritage 2011.',
'claude_audit_20260215');

-- Jinkiori: Petroglyphs ~1500 years ago (500 CE), Wachiperi people
UPDATE unified_sites SET period_start = 500, period_name = '1 - 500 AD'
WHERE id = '39927155-7597-4da8-9e3f-8c02d3d7a6ac' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('39927155-7597-4da8-9e3f-8c02d3d7a6ac', 'Jinkiori', 'fix', 'period_start', 'NULL', '500', 'medium',
'Phase C research: Petroglyphs ~1500 years ago. Wachiperi people, Harakmbut group. EthnoCO 2016 expedition.',
'claude_audit_20260215');

-- Situs Megalit Tebing Tinggi: Pasemah megalithic culture, ~100 BCE
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD'
WHERE id = 'cf3b581a-c47f-41c6-9922-48c6e3b8d3a0' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('cf3b581a-c47f-41c6-9922-48c6e3b8d3a0', 'Situs Megalit Tebing Tinggi', 'fix', 'period_start', 'NULL', '-100', 'medium',
'Phase C research: Pasemah megalithic culture, South Sumatra. Dong Son-style bronze drums link to 2000-2500 years ago.',
'claude_audit_20260215');

-- LOW confidence (4 sites)

-- Beskardesler Kaya Mezarlari: Hellenistic period estimate
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = 'ee94fe5e-d975-4ed9-940d-16056532293e' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ee94fe5e-d975-4ed9-940d-16056532293e', 'Beşkardeşler Kaya Mezarları', 'fix', 'period_start', 'NULL', '-300', 'low',
'Phase C research: Rock tombs near Kardesler Village, Ulubey, Ordu. Turkish cultural portal: probably Hellenistic period (~300 BCE).',
'claude_audit_20260215');

-- Currachjaghju: Corsican Bronze Age settlement estimate
UPDATE unified_sites SET period_start = -1800, period_name = '3000 - 1500 BC'
WHERE id = '09b07712-628c-4c14-bf87-62c586f1ced3' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('09b07712-628c-4c14-bf87-62c586f1ced3', 'Currachjaghju', 'fix', 'period_start', 'NULL', '-1800', 'low',
'Phase C research: Corsican Bronze Age Torre culture settlement, ~1800-1300 BCE. Low confidence - site-specific dating not confirmed.',
'claude_audit_20260215');

-- Northern Avenue Petroglyph Site: Patayan tradition estimate ~700 CE
UPDATE unified_sites SET period_start = 700, period_name = '500 - 1000 AD'
WHERE id = 'fe9d2d34-c026-44cd-9883-86b23c96c962' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fe9d2d34-c026-44cd-9883-86b23c96c962', 'Northern Avenue Petroglyph Site', 'fix', 'period_start', 'NULL', '700', 'low',
'Phase C research: Kingman AZ, NRHP 1996. Patayan Rock Art Tradition ~700 CE. Geographic inference, actual date could be earlier.',
'claude_audit_20260215');

-- Waruq: Yaro/pre-Inca settlement ~1000 CE
UPDATE unified_sites SET period_start = 1000, period_name = '500 - 1000 AD'
WHERE id = '6dfdc2fb-802e-4193-b9c9-15684d50bea8' AND period_start IS NULL AND source_id = 'ancient_nerds';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6dfdc2fb-802e-4193-b9c9-15684d50bea8', 'Waruq', 'fix', 'period_start', 'NULL', '1000', 'low',
'Phase C research: Yarowilca Province, Yaro ethnic group pre-Inca settlement. Late Intermediate Period estimate. Very uncertain.',
'claude_audit_20260215');
