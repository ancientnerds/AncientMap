-- ============================================================
-- Audit log for ALL site_type normalizations
-- Bulk insert: one entry per site, grouped by old→new mapping
-- ============================================================

-- Initial 65 fixes (non-canonical variants → canonical)
-- Settlement (22) → settlement
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Settlement', 'settlement', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'settlement';

-- Archaeological Site (12) → archaeological_site
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Archaeological Site', 'archaeological_site', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'archaeological_site';

-- Infrastructure (8) → infrastructure
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Infrastructure', 'infrastructure', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'infrastructure';

-- Monument (7 of 36) → monument  (29 were already canonical)
-- We can't distinguish which 7 were Monument vs monument, so log all 36
-- with a note that 29 were already canonical (verify action for those)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'verify', 'site_type', 'monument', 'monument', 'high', 'normalize_site_type(): already canonical', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'monument';

-- Megalithic (5 of 6) → megalithic  (1 was already canonical)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'verify', 'site_type', 'megalithic', 'megalithic', 'high', 'normalize_site_type(): already canonical or fixed', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'megalithic';

-- Temple (3) → temple
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Temple', 'temple', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'temple';

-- Inscription (2) → inscription
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Inscription', 'inscription', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'inscription';

-- Rock Art (2) → Rock art  (65 were rock art → Rock art, logged separately below)
-- Can't distinguish old 'Rock Art' from old 'rock art' in current data — all are 'Rock art' now
-- Log all 67 as verify since we can't tell which were which
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'verify', 'site_type', NULL, 'Rock art', 'high', 'normalize_site_type(): normalized from rock art/Rock Art', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Rock art';

-- Tomb (2) → tomb
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Tomb', 'tomb', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'tomb';

-- Ruin (1) → ruin
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'Ruin', 'ruin', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'ruin';

-- Theatre (1 of 28) → theatre  (27 were already canonical)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'verify', 'site_type', 'theatre', 'theatre', 'high', 'normalize_site_type(): already canonical or fixed', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'theatre';

-- Compound type case normalizations (all lowercase → canonical title case)
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'barrow', 'Barrow', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Barrow';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'cairn', 'Cairn', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Cairn';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'castle/palace', 'Castle/palace', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Castle/palace';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'cave structures', 'Cave Structures', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Cave Structures';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'cave structures, rock art', 'Cave Structures, Rock art', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Cave Structures, Rock art';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'church/cathedral', 'Church/cathedral', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Church/cathedral';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'city/town/settlement', 'City/town/settlement', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'City/town/settlement';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'city/town/settlement, pyramid complex', 'City/town/settlement, Pyramid complex', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'City/town/settlement, Pyramid complex';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'dolmen', 'Dolmen', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Dolmen';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'earthwork', 'Earthwork', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Earthwork';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'fortress/citadel', 'Fortress/citadel', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Fortress/citadel';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'gate/archway/bridge', 'Gate/archway/bridge', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Gate/archway/bridge';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'geoglyphs', 'Geoglyphs', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Geoglyphs';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'geological interest', 'Geological interest', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Geological interest';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'henge', 'Henge', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Henge';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'magnetic anomaly', 'Magnetic anomaly', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Magnetic anomaly';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'megalithic statues', 'Megalithic statues', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Megalithic statues';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'megalithic stones', 'Megalithic stones', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Megalithic stones';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'megalithic structures', 'Megalithic structures', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Megalithic structures';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'megalithic walls', 'Megalithic walls', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Megalithic walls';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'minaret/tower', 'Minaret/tower', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Minaret/tower';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'mine/quarry', 'Mine/quarry', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Mine/quarry';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'mound/tumulus', 'Mound/tumulus', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Mound/tumulus';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'museum', 'Museum', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Museum';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'necropolis/tombs complex', 'Necropolis/tombs complex', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Necropolis/tombs complex';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'petroglyphs', 'Petroglyphs', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Petroglyphs';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'polygonal masonry', 'Polygonal masonry', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Polygonal masonry';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'pyramid complex', 'Pyramid complex', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Pyramid complex';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'reservoir/aqueduct/canal', 'Reservoir/aqueduct/canal', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Reservoir/aqueduct/canal';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'residence/villa/farmhouse', 'Residence/villa/farmhouse', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Residence/villa/farmhouse';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'road/avenue/trackway', 'Road/avenue/trackway', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Road/avenue/trackway';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'rock relief/carving', 'Rock relief/carving', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Rock relief/carving';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'sculptured stone', 'Sculptured stone', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Sculptured stone';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'stone circle', 'Stone circle', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Stone circle';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'stone cross', 'Stone cross', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Stone cross';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'temple complex', 'Temple complex', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Temple complex';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'timber circle', 'Timber circle', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Timber circle';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'underwater structures', 'Underwater structures', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Underwater structures';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'elongated skulls', 'Elongated skulls', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Elongated skulls';

INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
SELECT id, name, 'fix', 'site_type', 'well', 'Well', 'high', 'normalize_site_type()', 'claude_audit_20260215'
FROM unified_sites WHERE source_id = 'ancient_nerds' AND site_type = 'Well';
