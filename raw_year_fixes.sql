BEGIN;

-- Batch fix: parse raw_year values that were previously unparseable

-- Thor's Cave (raw: 9650 BC)
UPDATE unified_sites SET period_start = -9650, period_name = '< 4500 BC' WHERE id = 'c9ab63ba-44f8-4e52-aec1-2e305191abf6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c9ab63ba-44f8-4e52-aec1-2e305191abf6', 'Thor''s Cave', 'fix', 'period_start', NULL, '-9650', 'high', 'parsed from raw_year: 9650 BC', 'audit_v1_parse_fix');

-- Star Carr (raw: 9300 - 8480 BC)
UPDATE unified_sites SET period_start = -9300, period_name = '< 4500 BC' WHERE id = 'af010237-a119-4b7b-8a37-802f22d82708';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('af010237-a119-4b7b-8a37-802f22d82708', 'Star Carr', 'fix', 'period_start', NULL, '-9300', 'high', 'parsed from raw_year: 9300 - 8480 BC', 'audit_v1_parse_fix');

-- Caverna da Pedra Pintada (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = 'cf47a988-bf08-4482-93d3-2a051e83a2ff';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('cf47a988-bf08-4482-93d3-2a051e83a2ff', 'Caverna da Pedra Pintada', 'fix', 'period_start', NULL, '-9000', 'high', 'parsed from raw_year: 9000 BC', 'audit_v1_parse_fix');

-- Tarragal Caves (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = '218a4df9-1bc1-43ce-a054-1d964d7232a4';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('218a4df9-1bc1-43ce-a054-1d964d7232a4', 'Tarragal Caves', 'fix', 'period_start', NULL, '-9000', 'high', 'parsed from raw_year: 9000 BC', 'audit_v1_parse_fix');

-- Wurdi Youang Stone Arrangement (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = 'cf8b5d56-cbc8-4550-bd77-4dc259020bad';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('cf8b5d56-cbc8-4550-bd77-4dc259020bad', 'Wurdi Youang Stone Arrangement', 'fix', 'period_start', NULL, '-9000', 'high', 'parsed from raw_year: 9000 BC', 'audit_v1_parse_fix');

-- Ashdown Forest (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = 'b4a99c23-00b3-4eb5-80c0-c1569cb9a351';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b4a99c23-00b3-4eb5-80c0-c1569cb9a351', 'Ashdown Forest', 'fix', 'period_start', NULL, '-9000', 'high', 'parsed from raw_year: 9000 BC', 'audit_v1_parse_fix');

-- Le Mas-d'Azil (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = 'bddad876-e487-4c8c-a0ff-8b84b0dfbef4';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('bddad876-e487-4c8c-a0ff-8b84b0dfbef4', 'Le Mas-d''Azil', 'fix', 'period_start', NULL, '-9000', 'high', 'parsed from raw_year: 9000 BC', 'audit_v1_parse_fix');

-- Ancient Byblos (raw: 8800 - 5000 BC)
UPDATE unified_sites SET period_start = -8800, period_name = '< 4500 BC' WHERE id = '0f5bb5fa-e4a9-4e6e-ae02-48929ed84921';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0f5bb5fa-e4a9-4e6e-ae02-48929ed84921', 'Ancient Byblos', 'fix', 'period_start', NULL, '-8800', 'high', 'parsed from raw_year: 8800 - 5000 BC', 'audit_v1_parse_fix');

-- Asana, Peru (raw: 8500 BC)
UPDATE unified_sites SET period_start = -8500, period_name = '< 4500 BC' WHERE id = '3ac6b54d-0231-4b56-b1c0-b7fac461bbcc';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3ac6b54d-0231-4b56-b1c0-b7fac461bbcc', 'Asana, Peru', 'fix', 'period_start', NULL, '-8500', 'high', 'parsed from raw_year: 8500 BC', 'audit_v1_parse_fix');

-- Ancon Archaeological Site (raw: 8000 BC - 1530 AD)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'ac28b46b-542e-48b7-adf9-32da0efd74c1';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ac28b46b-542e-48b7-adf9-32da0efd74c1', 'Ancon Archaeological Site', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC - 1530 AD', 'audit_v1_parse_fix');

-- Blick Mead (raw: 8000 - 4000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '6ff3e4f1-8f21-410a-9c93-d4468c91a762';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6ff3e4f1-8f21-410a-9c93-d4468c91a762', 'Blick Mead', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 - 4000 BC', 'audit_v1_parse_fix');

-- Steppe Geoglyphs (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'f78f8d70-ca5f-4831-9475-e4369414c5b1';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f78f8d70-ca5f-4831-9475-e4369414c5b1', 'Steppe Geoglyphs', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Bidjigal Reserve (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '8fe4115a-617d-4cfc-ab35-272e8b2c1db2';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8fe4115a-617d-4cfc-ab35-272e8b2c1db2', 'Bidjigal Reserve', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Cuddie Springs (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'd6fabe8c-061f-4885-8e02-cc6276c6f23c';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d6fabe8c-061f-4885-8e02-cc6276c6f23c', 'Cuddie Springs', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Karta (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '2ff6f6ff-dada-465c-ad3b-6db67b57a31b';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2ff6f6ff-dada-465c-ad3b-6db67b57a31b', 'Karta', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Koongine Cave (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '3aa70cf2-d56b-4401-8a60-2cd12131827c';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3aa70cf2-d56b-4401-8a60-2cd12131827c', 'Koongine Cave', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Kastros (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'f0b20fa9-aab2-400d-bfa8-24af297bb993';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f0b20fa9-aab2-400d-bfa8-24af297bb993', 'Kastros', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Tenta, Cyprus (raw: 8000 - 5000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '6e8ac9be-7600-4248-921b-0477ca4a70dc';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6e8ac9be-7600-4248-921b-0477ca4a70dc', 'Tenta, Cyprus', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 - 5000 BC', 'audit_v1_parse_fix');

-- Warren Hill, Bournemouth (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'fdeca69b-4a68-455c-a865-044b37ccfd21';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fdeca69b-4a68-455c-a865-044b37ccfd21', 'Warren Hill, Bournemouth', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- European Archaeological Park of Bliesbruck-Reinheim (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '540037f8-f9af-4776-b2fa-b82b4e9a80f0';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('540037f8-f9af-4776-b2fa-b82b4e9a80f0', 'European Archaeological Park of Bliesbruck-Reinheim', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Pantelleria Vecchia Bank Megalith (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'daa1ea4b-c002-4552-a4ef-45d996c6cea6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('daa1ea4b-c002-4552-a4ef-45d996c6cea6', 'Pantelleria Vecchia Bank Megalith', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Għar Dalam (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'ebbad3eb-877c-4c7f-b6bf-66723f7b49e6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ebbad3eb-877c-4c7f-b6bf-66723f7b49e6', 'Għar Dalam', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Guitarrero Cave (raw: 8000 BC - 1000 AD)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'd1a6a883-779d-47eb-8496-78fbb360ddd6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d1a6a883-779d-47eb-8496-78fbb360ddd6', 'Guitarrero Cave', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC - 1000 AD', 'audit_v1_parse_fix');

-- Toquepala Caves (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '2b7bb7a9-4759-41bf-a703-8f4da42a1b5c';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2b7bb7a9-4759-41bf-a703-8f4da42a1b5c', 'Toquepala Caves', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Balanced Rock, North Salem (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '2fb4a171-fe52-40c9-8bcb-195cd068b55d';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2fb4a171-fe52-40c9-8bcb-195cd068b55d', 'Balanced Rock, North Salem', 'fix', 'period_start', NULL, '-8000', 'high', 'parsed from raw_year: 8000 BC', 'audit_v1_parse_fix');

-- Howick House (raw: 7600 BC)
UPDATE unified_sites SET period_start = -7600, period_name = '< 4500 BC' WHERE id = 'de97fdf7-80cc-425c-9c5b-b26b03310155';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('de97fdf7-80cc-425c-9c5b-b26b03310155', 'Howick House', 'fix', 'period_start', NULL, '-7600', 'high', 'parsed from raw_year: 7600 BC', 'audit_v1_parse_fix');

-- Combe-Capelle (raw: 7500 BC)
UPDATE unified_sites SET period_start = -7500, period_name = '< 4500 BC' WHERE id = 'ac76d3ef-82df-4fcc-8da4-f4fc7f59716e';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ac76d3ef-82df-4fcc-8da4-f4fc7f59716e', 'Combe-Capelle', 'fix', 'period_start', NULL, '-7500', 'high', 'parsed from raw_year: 7500 BC', 'audit_v1_parse_fix');

-- Mehrgarh (raw: 7000 - 2000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = '2eae8fd6-d3d4-4764-a8bd-2d3a8f88ebbe';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2eae8fd6-d3d4-4764-a8bd-2d3a8f88ebbe', 'Mehrgarh', 'fix', 'period_start', NULL, '-7000', 'high', 'parsed from raw_year: 7000 - 2000 BC', 'audit_v1_parse_fix');

-- Samsø (raw: 7000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = '49835383-20b8-44e0-9bf1-9e06cf2ecbb1';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('49835383-20b8-44e0-9bf1-9e06cf2ecbb1', 'Samsø', 'fix', 'period_start', NULL, '-7000', 'high', 'parsed from raw_year: 7000 BC', 'audit_v1_parse_fix');

-- Sassi di Matera (raw: 7000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = 'b0b461de-f74e-47b9-8b91-32c35b7c89c6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b0b461de-f74e-47b9-8b91-32c35b7c89c6', 'Sassi di Matera', 'fix', 'period_start', NULL, '-7000', 'high', 'parsed from raw_year: 7000 BC', 'audit_v1_parse_fix');

-- Bir Hima Rock Petroglyphs and Inscriptions (raw: 7000 - 1000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = 'b1135e25-0b17-4daf-ab6f-57b3cfb9a1fa';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b1135e25-0b17-4daf-ab6f-57b3cfb9a1fa', 'Bir Hima Rock Petroglyphs and Inscriptions', 'fix', 'period_start', NULL, '-7000', 'high', 'parsed from raw_year: 7000 - 1000 BC', 'audit_v1_parse_fix');

-- Jabal al-ʿHayn (raw: 7000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = '7ccaad38-8cfb-401e-a938-e2c792914b75';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('7ccaad38-8cfb-401e-a938-e2c792914b75', 'Jabal al-ʿHayn', 'fix', 'period_start', NULL, '-7000', 'high', 'parsed from raw_year: 7000 BC', 'audit_v1_parse_fix');

-- Cave del Valle, Cantabria (raw: 7000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = '69ef4043-f69f-4f87-b422-09eb53a72950';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('69ef4043-f69f-4f87-b422-09eb53a72950', 'Cave del Valle, Cantabria', 'fix', 'period_start', NULL, '-7000', 'high', 'parsed from raw_year: 7000 BC', 'audit_v1_parse_fix');

-- Atlit Yam (raw: 6900 - 6300 BC)
UPDATE unified_sites SET period_start = -6900, period_name = '< 4500 BC' WHERE id = 'cc240cba-a746-40f1-9045-b84efedf3e0d';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('cc240cba-a746-40f1-9045-b84efedf3e0d', 'Atlit Yam', 'fix', 'period_start', NULL, '-6900', 'high', 'parsed from raw_year: 6900 - 6300 BC', 'audit_v1_parse_fix');

-- Ancient Corinth (raw: 6500 - 146 BC)
UPDATE unified_sites SET period_start = -6500, period_name = '< 4500 BC' WHERE id = 'e2f8cf43-f499-4363-8fcb-af93e79ea756';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e2f8cf43-f499-4363-8fcb-af93e79ea756', 'Ancient Corinth', 'fix', 'period_start', NULL, '-6500', 'high', 'parsed from raw_year: 6500 - 146 BC', 'audit_v1_parse_fix');

-- Damjili Cave (raw: 6400 - 6000 BC)
UPDATE unified_sites SET period_start = -6400, period_name = '< 4500 BC' WHERE id = '15bc0443-6fb4-48df-a213-2d5095945d65';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('15bc0443-6fb4-48df-a213-2d5095945d65', 'Damjili Cave', 'fix', 'period_start', NULL, '-6400', 'high', 'parsed from raw_year: 6400 - 6000 BC', 'audit_v1_parse_fix');

-- Eston Nab (raw: 6000 - 700 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '277970ce-65f8-403a-8e20-dbcadac0f214';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('277970ce-65f8-403a-8e20-dbcadac0f214', 'Eston Nab', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 - 700 BC', 'audit_v1_parse_fix');

-- Gruta do Gentio (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = 'fab3989d-2c06-40cc-9d22-c7fb58e5e94f';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fab3989d-2c06-40cc-9d22-c7fb58e5e94f', 'Gruta do Gentio', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 BC', 'audit_v1_parse_fix');

-- Bouldnor Cliff (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = 'a9a32ee2-bd62-4fe4-8515-0ccdda65a7ee';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a9a32ee2-bd62-4fe4-8515-0ccdda65a7ee', 'Bouldnor Cliff', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 BC', 'audit_v1_parse_fix');

-- Castellane (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = 'dfd4d30e-1a29-4917-9626-787b823d7748';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('dfd4d30e-1a29-4917-9626-787b823d7748', 'Castellane', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 BC', 'audit_v1_parse_fix');

-- Yarim Tepe (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '9e17ecc2-7c59-4f03-bea4-8d32de261d3e';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9e17ecc2-7c59-4f03-bea4-8d32de261d3e', 'Yarim Tepe', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 BC', 'audit_v1_parse_fix');

-- Boca de Potrerillos (raw: 6000 - 2000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '69fb9773-3709-4e8e-8682-96c75f57dfc6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('69fb9773-3709-4e8e-8682-96c75f57dfc6', 'Boca de Potrerillos', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 - 2000 BC', 'audit_v1_parse_fix');

-- Tumba Madžari (raw: 6000 - 4300 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '5741eec1-d6ca-4a63-b0cb-f9a106a4acca';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5741eec1-d6ca-4a63-b0cb-f9a106a4acca', 'Tumba Madžari', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 - 4300 BC', 'audit_v1_parse_fix');

-- Rock Carvings in Central Norway (raw: 6000 BC - 300 AD)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = 'd928b37a-38d1-4c34-8e89-49703f92f313';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d928b37a-38d1-4c34-8e89-49703f92f313', 'Rock Carvings in Central Norway', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 BC - 300 AD', 'audit_v1_parse_fix');

-- Al Thumamah, Riyadh (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '9b3a51e8-25ee-4936-932a-af5e2fd48e01';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9b3a51e8-25ee-4936-932a-af5e2fd48e01', 'Al Thumamah, Riyadh', 'fix', 'period_start', NULL, '-6000', 'high', 'parsed from raw_year: 6000 BC', 'audit_v1_parse_fix');

-- Dispilio (raw: 5600 - 5000 BC)
UPDATE unified_sites SET period_start = -5600, period_name = '< 4500 BC' WHERE id = 'b11e591e-1f4c-4850-a7af-b5a13bc499cc';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b11e591e-1f4c-4850-a7af-b5a13bc499cc', 'Dispilio', 'fix', 'period_start', NULL, '-5600', 'high', 'parsed from raw_year: 5600 - 5000 BC', 'audit_v1_parse_fix');

-- Samarra (raw: 5500 - 3900 BC)
UPDATE unified_sites SET period_start = -5500, period_name = '< 4500 BC' WHERE id = '6d530908-adfd-44bf-b0dc-d4a02d2cdefb';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6d530908-adfd-44bf-b0dc-d4a02d2cdefb', 'Samarra', 'fix', 'period_start', NULL, '-5500', 'high', 'parsed from raw_year: 5500 - 3900 BC', 'audit_v1_parse_fix');

-- Qillqatani (raw: 5500 BC - 1472 AD)
UPDATE unified_sites SET period_start = -5500, period_name = '< 4500 BC' WHERE id = '29bbdfce-7b18-4530-b668-8a2fb289694b';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('29bbdfce-7b18-4530-b668-8a2fb289694b', 'Qillqatani', 'fix', 'period_start', NULL, '-5500', 'high', 'parsed from raw_year: 5500 BC - 1472 AD', 'audit_v1_parse_fix');

-- Pločnik - Archaeological Site (raw: 5500 - 4700 BC)
UPDATE unified_sites SET period_start = -5500, period_name = '< 4500 BC' WHERE id = '412a1f97-7dfd-4624-b6ec-2813217f39bf';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('412a1f97-7dfd-4624-b6ec-2813217f39bf', 'Pločnik - Archaeological Site', 'fix', 'period_start', NULL, '-5500', 'high', 'parsed from raw_year: 5500 - 4700 BC', 'audit_v1_parse_fix');

-- Settlements of the Cucuteni-Trypillia Culture (raw: 5500 - 2750 BC)
UPDATE unified_sites SET period_start = -5500, period_name = '< 4500 BC' WHERE id = '934ed584-2c13-46fc-bf38-eadd53b68d6f';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('934ed584-2c13-46fc-bf38-eadd53b68d6f', 'Settlements of the Cucuteni-Trypillia Culture', 'fix', 'period_start', NULL, '-5500', 'high', 'parsed from raw_year: 5500 - 2750 BC', 'audit_v1_parse_fix');

-- Eridu, Sumeria (raw: 5400 BC)
UPDATE unified_sites SET period_start = -5400, period_name = '< 4500 BC' WHERE id = '5cd47e05-c322-4510-b40f-c1f75072c147';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5cd47e05-c322-4510-b40f-c1f75072c147', 'Eridu, Sumeria', 'fix', 'period_start', NULL, '-5400', 'high', 'parsed from raw_year: 5400 BC', 'audit_v1_parse_fix');

-- Herxheim - Archaeological Site (raw: 5300 - 4950 BC)
UPDATE unified_sites SET period_start = -5300, period_name = '< 4500 BC' WHERE id = 'e6ec727e-8e27-4885-b2bb-a9aadd8f17c9';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e6ec727e-8e27-4885-b2bb-a9aadd8f17c9', 'Herxheim - Archaeological Site', 'fix', 'period_start', NULL, '-5300', 'high', 'parsed from raw_year: 5300 - 4950 BC', 'audit_v1_parse_fix');

-- Langweiler - Archaeological Site (raw: 5300 - 4900 BC)
UPDATE unified_sites SET period_start = -5300, period_name = '< 4500 BC' WHERE id = 'dde240ca-5969-4123-a842-e7e235f7566b';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('dde240ca-5969-4123-a842-e7e235f7566b', 'Langweiler - Archaeological Site', 'fix', 'period_start', NULL, '-5300', 'high', 'parsed from raw_year: 5300 - 4900 BC', 'audit_v1_parse_fix');

-- Saliagos (raw: 5000 - 4500 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '64fe03e2-33c3-4836-b012-b3e50917fcf6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('64fe03e2-33c3-4836-b012-b3e50917fcf6', 'Saliagos', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 - 4500 BC', 'audit_v1_parse_fix');

-- Sperris Quoit (raw: 5000 - 3000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '5bdfb4fe-496d-4c3a-9032-d5677201fca8';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5bdfb4fe-496d-4c3a-9032-d5677201fca8', 'Sperris Quoit', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 - 3000 BC', 'audit_v1_parse_fix');

-- Stepanivka (raw: 5000 - 4300 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'cd10aef4-26b6-477b-bc12-de3786c10594';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('cd10aef4-26b6-477b-bc12-de3786c10594', 'Stepanivka', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 - 4300 BC', 'audit_v1_parse_fix');

-- Alikomektepe (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '0d4830b5-92f1-4698-9aca-d32079f20e11';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0d4830b5-92f1-4698-9aca-d32079f20e11', 'Alikomektepe', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Tell Yunatsite (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '18f488c0-fce6-4ea4-b732-d23fe5759cd1';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('18f488c0-fce6-4ea4-b732-d23fe5759cd1', 'Tell Yunatsite', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Lismore Fields (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '75f2454d-5538-42ea-87b2-ba091dec3df6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('75f2454d-5538-42ea-87b2-ba091dec3df6', 'Lismore Fields', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Alignements de Kerzerho (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'bfc9d15b-70a1-44e7-ba2c-98195fb535df';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('bfc9d15b-70a1-44e7-ba2c-98195fb535df', 'Alignements de Kerzerho', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Grotte de Lombrives (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'e7623642-d009-4d1f-8f0e-fa03a89be90e';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e7623642-d009-4d1f-8f0e-fa03a89be90e', 'Grotte de Lombrives', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- La Noce de Pierres (raw: 5000 - 4000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '8b90f9f0-db52-4d17-a699-e70fc6e5c2ae';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8b90f9f0-db52-4d17-a699-e70fc6e5c2ae', 'La Noce de Pierres', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 - 4000 BC', 'audit_v1_parse_fix');

-- Le Grand-Pressigny (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '6c736688-98d7-4c57-bf53-1f4367950131';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6c736688-98d7-4c57-bf53-1f4367950131', 'Le Grand-Pressigny', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Mane Braz (raw: 5000 - 4000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'c1980a31-6a2b-4e83-ad99-8f36b6036ff2';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c1980a31-6a2b-4e83-ad99-8f36b6036ff2', 'Mane Braz', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 - 4000 BC', 'audit_v1_parse_fix');

-- Menhir de Champ-Dolent (raw: 5000 - 4000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'f634e2ff-366e-49f1-be74-ac930ba5bc02';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f634e2ff-366e-49f1-be74-ac930ba5bc02', 'Menhir de Champ-Dolent', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 - 4000 BC', 'audit_v1_parse_fix');

-- Saint-Michel Tumulus (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '29e8f8a9-119e-4cb7-8c24-c1ebd943cfe3';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('29e8f8a9-119e-4cb7-8c24-c1ebd943cfe3', 'Saint-Michel Tumulus', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Santa Verna (raw: 5000 - 3400 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'f8ccb519-328b-4b91-8c67-3416ee2aa788';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f8ccb519-328b-4b91-8c67-3416ee2aa788', 'Santa Verna', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 - 3400 BC', 'audit_v1_parse_fix');

-- Sheri Khan Tarakai (raw: 5000 - 2000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'c3b60256-57d1-4b74-80f0-1a2536795a20';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c3b60256-57d1-4b74-80f0-1a2536795a20', 'Sheri Khan Tarakai', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 - 2000 BC', 'audit_v1_parse_fix');

-- Menhir of Meada (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '521ade1a-0eaf-442b-973d-ccae9e9fbb35';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('521ade1a-0eaf-442b-973d-ccae9e9fbb35', 'Menhir of Meada', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Ekornavallen (raw: 5000 BC - 500 AD)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '480f44f7-ad94-4ea5-bad8-fde912fa692b';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('480f44f7-ad94-4ea5-bad8-fde912fa692b', 'Ekornavallen', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC - 500 AD', 'audit_v1_parse_fix');

-- Gärde (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '4235fa73-a58f-400b-a1f6-4998a8d2893f';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('4235fa73-a58f-400b-a1f6-4998a8d2893f', 'Gärde', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Maidanetske (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '9ad64db8-ba14-45f4-b565-7bf2c29db1f1';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9ad64db8-ba14-45f4-b565-7bf2c29db1f1', 'Maidanetske', 'fix', 'period_start', NULL, '-5000', 'high', 'parsed from raw_year: 5000 BC', 'audit_v1_parse_fix');

-- Goseck Circle (raw: 4900 - 4700 BC)
UPDATE unified_sites SET period_start = -4900, period_name = '< 4500 BC' WHERE id = '8862f0da-6584-4963-911f-a88c454dc321';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8862f0da-6584-4963-911f-a88c454dc321', 'Goseck Circle', 'fix', 'period_start', NULL, '-4900', 'high', 'parsed from raw_year: 4900 - 4700 BC', 'audit_v1_parse_fix');

-- Barnenez (raw: 4800 BC)
UPDATE unified_sites SET period_start = -4800, period_name = '< 4500 BC' WHERE id = '348770cd-a3a2-4b6e-83f7-bd5f5d699022';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('348770cd-a3a2-4b6e-83f7-bd5f5d699022', 'Barnenez', 'fix', 'period_start', NULL, '-4800', 'high', 'parsed from raw_year: 4800 BC', 'audit_v1_parse_fix');

-- Tumulus of Bougon (raw: 4800 BC)
UPDATE unified_sites SET period_start = -4800, period_name = '< 4500 BC' WHERE id = 'de449341-fecc-48c2-ab1d-0087ce60e174';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('de449341-fecc-48c2-ab1d-0087ce60e174', 'Tumulus of Bougon', 'fix', 'period_start', NULL, '-4800', 'high', 'parsed from raw_year: 4800 BC', 'audit_v1_parse_fix');

-- Solnitsata (raw: 4700 - 4200 BC)
UPDATE unified_sites SET period_start = -4700, period_name = '< 4500 BC' WHERE id = '4541e162-c69b-49d8-a4db-04e66089e8fd';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('4541e162-c69b-49d8-a4db-04e66089e8fd', 'Solnitsata', 'fix', 'period_start', NULL, '-4700', 'high', 'parsed from raw_year: 4700 - 4200 BC', 'audit_v1_parse_fix');

-- Locmariaquer Megaliths (raw: 4700 BC)
UPDATE unified_sites SET period_start = -4700, period_name = '< 4500 BC' WHERE id = '0cd58c95-e8da-453a-9ac4-ecaeeda843cc';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0cd58c95-e8da-453a-9ac4-ecaeeda843cc', 'Locmariaquer Megaliths', 'fix', 'period_start', NULL, '-4700', 'high', 'parsed from raw_year: 4700 BC', 'audit_v1_parse_fix');

-- Varna Necropolis (raw: 4600 - 4200 BC)
UPDATE unified_sites SET period_start = -4600, period_name = '< 4500 BC' WHERE id = 'fe6a7e02-39e4-46bf-abb9-b1862974f252';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fe6a7e02-39e4-46bf-abb9-b1862974f252', 'Varna Necropolis', 'fix', 'period_start', NULL, '-4600', 'high', 'parsed from raw_year: 4600 - 4200 BC', 'audit_v1_parse_fix');

-- Rock Carvings at Tennes (raw: 4600 - 2600 BC)
UPDATE unified_sites SET period_start = -4600, period_name = '< 4500 BC' WHERE id = 'a776d595-3309-45c7-9c7f-014181af2a84';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a776d595-3309-45c7-9c7f-014181af2a84', 'Rock Carvings at Tennes', 'fix', 'period_start', NULL, '-4600', 'high', 'parsed from raw_year: 4600 - 2600 BC', 'audit_v1_parse_fix');

-- Deriivka (raw: 4500 - 3500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '0bf5e631-0ee8-4b75-9c06-fd6d713cc42d';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0bf5e631-0ee8-4b75-9c06-fd6d713cc42d', 'Deriivka', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 3500 BC', 'audit_v1_parse_fix');

-- Ebbsfleet Valley (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'd9dc6883-3762-4abc-9dca-736e3292f527';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d9dc6883-3762-4abc-9dca-736e3292f527', 'Ebbsfleet Valley', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Hazleton Long Barrows (raw: 4500 - 2500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '9a941093-043f-4287-b188-aebddd81df62';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9a941093-043f-4287-b188-aebddd81df62', 'Hazleton Long Barrows', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 2500 BC', 'audit_v1_parse_fix');

-- King Lud's Entrenchments and The Drift (raw: 4500 - 2500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '0b8a8edd-8a60-4758-985c-bf354de4a985';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0b8a8edd-8a60-4758-985c-bf354de4a985', 'King Lud''s Entrenchments and The Drift', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 2500 BC', 'audit_v1_parse_fix');

-- Green Gully Archaeological Site (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'dac9b6e1-a54d-4b9a-b400-5fa295ba2040';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('dac9b6e1-a54d-4b9a-b400-5fa295ba2040', 'Green Gully Archaeological Site', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Kow Swamp Archaeological Site (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '06f6a014-f2c1-423a-8944-17c81374fd02';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('06f6a014-f2c1-423a-8944-17c81374fd02', 'Kow Swamp Archaeological Site', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Stenseby Passage Grave (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '2c621de8-bfe8-4f0f-96a9-01b3761ea97a';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2c621de8-bfe8-4f0f-96a9-01b3761ea97a', 'Stenseby Passage Grave', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Arbor Low (raw: 4500 - 1200 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'b3a11168-712b-445a-b453-c945be7900f3';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b3a11168-712b-445a-b453-c945be7900f3', 'Arbor Low', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 1200 BC', 'audit_v1_parse_fix');

-- Broadsands Chambered Tomb (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '186eeb54-e6a0-4370-87c6-fbcaae023a33';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('186eeb54-e6a0-4370-87c6-fbcaae023a33', 'Broadsands Chambered Tomb', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Cleeve Hill, Gloucestershire (raw: 4500 BC - 1st c. AD)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '6b926b71-b756-43c4-9bd8-f987641927da';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6b926b71-b756-43c4-9bd8-f987641927da', 'Cleeve Hill, Gloucestershire', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC - 1st c. AD', 'audit_v1_parse_fix');

-- Drizzlecombe (raw: 4500 - 1200 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'c82e8c63-783d-4d7b-aead-69052b6a04a2';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c82e8c63-783d-4d7b-aead-69052b6a04a2', 'Drizzlecombe', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 1200 BC', 'audit_v1_parse_fix');

-- Eggardon Hill (raw: 4500 - 2500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '3debd642-ff96-4840-bff2-9d8faced25cd';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3debd642-ff96-4840-bff2-9d8faced25cd', 'Eggardon Hill', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 2500 BC', 'audit_v1_parse_fix');

-- Great Tottington (raw: 4500 - 2500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'c221d864-3e29-4789-a581-f52f3c3cf096';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c221d864-3e29-4789-a581-f52f3c3cf096', 'Great Tottington', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 2500 BC', 'audit_v1_parse_fix');

-- Knowlton Circles (raw: 4500 - 2200 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '5a04c048-e207-42fe-9d26-b39a0217bf09';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5a04c048-e207-42fe-9d26-b39a0217bf09', 'Knowlton Circles', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 2200 BC', 'audit_v1_parse_fix');

-- Lanyon Quoit (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '4eba8602-4117-47ee-9c24-7e0ab06ef999';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('4eba8602-4117-47ee-9c24-7e0ab06ef999', 'Lanyon Quoit', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Carnac Stones (raw: 4500 - 3300 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'b539ba9e-5d7e-4ce8-a9ff-943ac3247297';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b539ba9e-5d7e-4ce8-a9ff-943ac3247297', 'Carnac Stones', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 3300 BC', 'audit_v1_parse_fix');

-- Craménil (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '683f96a1-3a51-40da-9d97-0d4971650334';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('683f96a1-3a51-40da-9d97-0d4971650334', 'Craménil', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Erdeven (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'c93f25d4-5aa3-46f9-a672-71a2000ce517';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c93f25d4-5aa3-46f9-a672-71a2000ce517', 'Erdeven', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Tombeau de Merlin (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'b27222dd-e77f-419d-9f1b-55bafcf61cc0';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b27222dd-e77f-419d-9f1b-55bafcf61cc0', 'Tombeau de Merlin', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Hohlenstein-Stadel (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'f0b786ae-17e0-4ce1-bfdc-c9184e5473a3';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f0b786ae-17e0-4ce1-bfdc-c9184e5473a3', 'Hohlenstein-Stadel', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Syberg (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '70762563-db82-43f3-ad30-bce5fde9c9bd';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('70762563-db82-43f3-ad30-bce5fde9c9bd', 'Syberg', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Rock Carvings at Åsli (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'e8235f8c-e30c-4c97-8297-639b2681d46b';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e8235f8c-e30c-4c97-8297-639b2681d46b', 'Rock Carvings at Åsli', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 BC', 'audit_v1_parse_fix');

-- Anta das Pedras Grandes (raw: 4500 - 2000 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '234afaf4-4030-41f9-aac6-6378d375d157';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('234afaf4-4030-41f9-aac6-6378d375d157', 'Anta das Pedras Grandes', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 2000 BC', 'audit_v1_parse_fix');

-- Medvednjak (raw: 4500 - 3500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '6eaec8c3-97e1-4e7b-b1d8-96b14c96a323';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6eaec8c3-97e1-4e7b-b1d8-96b14c96a323', 'Medvednjak', 'fix', 'period_start', NULL, '-4500', 'high', 'parsed from raw_year: 4500 - 3500 BC', 'audit_v1_parse_fix');

-- Lëkurësi Castle (raw: 1537 AD)
UPDATE unified_sites SET period_start = 1537, period_name = '1500+ AD' WHERE id = 'af9036d8-9a13-4107-b22d-b5c088006d91';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('af9036d8-9a13-4107-b22d-b5c088006d91', 'Lëkurësi Castle', 'fix', 'period_start', NULL, '1537', 'high', 'parsed from raw_year: 1537 AD', 'audit_v1_parse_fix');

-- Oudong (raw: 1601 - 1866 AD)
UPDATE unified_sites SET period_start = 1601, period_name = '1500+ AD' WHERE id = '37f08947-0576-48de-90ca-ef211b615619';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('37f08947-0576-48de-90ca-ef211b615619', 'Oudong', 'fix', 'period_start', NULL, '1601', 'high', 'parsed from raw_year: 1601 - 1866 AD', 'audit_v1_parse_fix');

-- Sheikhupura Fort (raw: 1607 AD)
UPDATE unified_sites SET period_start = 1607, period_name = '1500+ AD' WHERE id = 'b9f26550-7988-4a34-a3ff-7ef9cb69c838';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b9f26550-7988-4a34-a3ff-7ef9cb69c838', 'Sheikhupura Fort', 'fix', 'period_start', NULL, '1607', 'high', 'parsed from raw_year: 1607 AD', 'audit_v1_parse_fix');

-- Tomb of Ali Mardan Khan (raw: 1630 AD)
UPDATE unified_sites SET period_start = 1630, period_name = '1500+ AD' WHERE id = '58d46ab0-7fc9-4dfa-bf40-a5042d4a91be';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('58d46ab0-7fc9-4dfa-bf40-a5042d4a91be', 'Tomb of Ali Mardan Khan', 'fix', 'period_start', NULL, '1630', 'high', 'parsed from raw_year: 1630 AD', 'audit_v1_parse_fix');

-- Forte de Santa Luzia (raw: 1641 - 1648 AD)
UPDATE unified_sites SET period_start = 1641, period_name = '1500+ AD' WHERE id = '3ff2ae0e-9095-48ed-a45e-0d8c9f455527';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3ff2ae0e-9095-48ed-a45e-0d8c9f455527', 'Forte de Santa Luzia', 'fix', 'period_start', NULL, '1641', 'high', 'parsed from raw_year: 1641 - 1648 AD', 'audit_v1_parse_fix');

-- Sahasralinga (raw: 1678 - 1718 AD)
UPDATE unified_sites SET period_start = 1678, period_name = '1500+ AD' WHERE id = '075337ec-9108-431f-ae90-d5d0e795f23a';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('075337ec-9108-431f-ae90-d5d0e795f23a', 'Sahasralinga', 'fix', 'period_start', NULL, '1678', 'high', 'parsed from raw_year: 1678 - 1718 AD', 'audit_v1_parse_fix');

-- Ksar el Barka (raw: 1690 AD)
UPDATE unified_sites SET period_start = 1690, period_name = '1500+ AD' WHERE id = 'a5d9e9a7-9fd2-4a0f-a3ae-7dd78fba429b';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a5d9e9a7-9fd2-4a0f-a3ae-7dd78fba429b', 'Ksar el Barka', 'fix', 'period_start', NULL, '1690', 'high', 'parsed from raw_year: 1690 AD', 'audit_v1_parse_fix');

-- Shanqal Fort (raw: 1737 AD)
UPDATE unified_sites SET period_start = 1737, period_name = '1500+ AD' WHERE id = '9f823459-f4ce-43cc-a433-b1cdaf9f89ad';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9f823459-f4ce-43cc-a433-b1cdaf9f89ad', 'Shanqal Fort', 'fix', 'period_start', NULL, '1737', 'high', 'parsed from raw_year: 1737 AD', 'audit_v1_parse_fix');

-- Deir el kalaa (raw: 1748 AD)
UPDATE unified_sites SET period_start = 1748, period_name = '1500+ AD' WHERE id = '0e004ad3-7c38-4926-8bb7-86593ec4c4f7';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0e004ad3-7c38-4926-8bb7-86593ec4c4f7', 'Deir el kalaa', 'fix', 'period_start', NULL, '1748', 'high', 'parsed from raw_year: 1748 AD', 'audit_v1_parse_fix');

-- Sundarnarayan Temple (raw: 1756 AD)
UPDATE unified_sites SET period_start = 1756, period_name = '1500+ AD' WHERE id = '5067da0a-d681-4fe3-91e5-e2dc7c0656d7';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5067da0a-d681-4fe3-91e5-e2dc7c0656d7', 'Sundarnarayan Temple', 'fix', 'period_start', NULL, '1756', 'high', 'parsed from raw_year: 1756 AD', 'audit_v1_parse_fix');

-- Kot Diji Fort (raw: 1795 AD)
UPDATE unified_sites SET period_start = 1795, period_name = '1500+ AD' WHERE id = '98cb1e3f-2eab-4bd0-9cda-8bd61abcacb6';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('98cb1e3f-2eab-4bd0-9cda-8bd61abcacb6', 'Kot Diji Fort', 'fix', 'period_start', NULL, '1795', 'high', 'parsed from raw_year: 1795 AD', 'audit_v1_parse_fix');

-- Ali Masjid Fort (raw: 1837 AD)
UPDATE unified_sites SET period_start = 1837, period_name = '1500+ AD' WHERE id = '8c159d7f-d954-44fc-aab9-6b7841d68a35';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8c159d7f-d954-44fc-aab9-6b7841d68a35', 'Ali Masjid Fort', 'fix', 'period_start', NULL, '1837', 'high', 'parsed from raw_year: 1837 AD', 'audit_v1_parse_fix');

-- Krishnabai Mandir (raw: 1888 AD)
UPDATE unified_sites SET period_start = 1888, period_name = '1500+ AD' WHERE id = '826407f8-35ca-4423-bd85-5f53a3d95ea2';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('826407f8-35ca-4423-bd85-5f53a3d95ea2', 'Krishnabai Mandir', 'fix', 'period_start', NULL, '1888', 'high', 'parsed from raw_year: 1888 AD', 'audit_v1_parse_fix');

-- Museo de Antropologia de Xalapa (raw: 1937)
UPDATE unified_sites SET period_start = 1937, period_name = '1500+ AD' WHERE id = '761dfa49-30a6-4e09-a4c6-cb5294f3a98e';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('761dfa49-30a6-4e09-a4c6-cb5294f3a98e', 'Museo de Antropologia de Xalapa', 'fix', 'period_start', NULL, '1937', 'high', 'parsed from raw_year: 1937', 'audit_v1_parse_fix');

-- Charents Arch (raw: 1957 AD)
UPDATE unified_sites SET period_start = 1957, period_name = '1500+ AD' WHERE id = 'a9d840ac-4636-40bf-9570-682550967728';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a9d840ac-4636-40bf-9570-682550967728', 'Charents Arch', 'fix', 'period_start', NULL, '1957', 'high', 'parsed from raw_year: 1957 AD', 'audit_v1_parse_fix');

-- Mérida Anthropological Museum (raw: 1959)
UPDATE unified_sites SET period_start = 1959, period_name = '1500+ AD' WHERE id = '01c36727-31bd-45ae-9908-5c7043403cd2';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('01c36727-31bd-45ae-9908-5c7043403cd2', 'Mérida Anthropological Museum', 'fix', 'period_start', NULL, '1959', 'high', 'parsed from raw_year: 1959', 'audit_v1_parse_fix');

-- Shri Bhagwan Bahubali Monolithic Statue (raw: 1973 AD)
UPDATE unified_sites SET period_start = 1973, period_name = '1500+ AD' WHERE id = 'abfa8b60-ea29-4150-925f-87d4b1fe8092';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('abfa8b60-ea29-4150-925f-87d4b1fe8092', 'Shri Bhagwan Bahubali Monolithic Statue', 'fix', 'period_start', NULL, '1973', 'high', 'parsed from raw_year: 1973 AD', 'audit_v1_parse_fix');

-- Chacamarca Historic Sanctuary (raw: 1974 AD)
UPDATE unified_sites SET period_start = 1974, period_name = '1500+ AD' WHERE id = '160da9ec-9bc4-4893-8066-dd3afb41c5b2';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('160da9ec-9bc4-4893-8066-dd3afb41c5b2', 'Chacamarca Historic Sanctuary', 'fix', 'period_start', NULL, '1974', 'high', 'parsed from raw_year: 1974 AD', 'audit_v1_parse_fix');

-- Museo Regional de Antropologia Carlos Pellier (raw: 1980)
UPDATE unified_sites SET period_start = 1980, period_name = '1500+ AD' WHERE id = 'c1e49d01-2e46-4ecc-af7f-1fd39555fc8e';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c1e49d01-2e46-4ecc-af7f-1fd39555fc8e', 'Museo Regional de Antropologia Carlos Pellier', 'fix', 'period_start', NULL, '1980', 'high', 'parsed from raw_year: 1980', 'audit_v1_parse_fix');

-- Museo Regional de Campeche (raw: 1986)
UPDATE unified_sites SET period_start = 1986, period_name = '1500+ AD' WHERE id = 'd48eb704-d535-4be7-9695-868ee650cbb7';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d48eb704-d535-4be7-9695-868ee650cbb7', 'Museo Regional de Campeche', 'fix', 'period_start', NULL, '1986', 'high', 'parsed from raw_year: 1986', 'audit_v1_parse_fix');

-- Museo de la Arquitectura Maya (raw: 2005)
UPDATE unified_sites SET period_start = 2005, period_name = '1500+ AD' WHERE id = '9108b193-4370-4997-a271-7d20836efeed';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9108b193-4370-4997-a271-7d20836efeed', 'Museo de la Arquitectura Maya', 'fix', 'period_start', NULL, '2005', 'high', 'parsed from raw_year: 2005', 'audit_v1_parse_fix');

-- Khushuu Tsaidam Museum (raw: 2008 AD)
UPDATE unified_sites SET period_start = 2008, period_name = '1500+ AD' WHERE id = '71d8e2bc-7406-4c4a-b68d-2ff1b71800e8';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('71d8e2bc-7406-4c4a-b68d-2ff1b71800e8', 'Khushuu Tsaidam Museum', 'fix', 'period_start', NULL, '2008', 'high', 'parsed from raw_year: 2008 AD', 'audit_v1_parse_fix');

-- King Richard III Visitor Centre (raw: 2014 AD)
UPDATE unified_sites SET period_start = 2014, period_name = '1500+ AD' WHERE id = 'aa56465b-1a9e-45b2-abec-b50be3796d8f';
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('aa56465b-1a9e-45b2-abec-b50be3796d8f', 'King Richard III Visitor Centre', 'fix', 'period_start', NULL, '2014', 'high', 'parsed from raw_year: 2014 AD', 'audit_v1_parse_fix');

COMMIT;