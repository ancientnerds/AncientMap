-- ============================================================
-- Comprehensive site_type normalization — ancient_nerds source
-- Fixes ALL non-canonical variants to their canonical form
-- Applied: 2026-02-15
-- ============================================================

-- Already-applied fixes from initial pass (these are now canonical):
-- Settlement (22) → settlement  [DONE]
-- Archaeological Site (12) → archaeological_site  [DONE]
-- Infrastructure (8) → infrastructure  [DONE]
-- Monument (7) → monument  [DONE]
-- Megalithic (5) → megalithic  [DONE]
-- Temple (3) → temple  [DONE]
-- Inscription (2) → inscription  [DONE]
-- Rock Art (2) → Rock art  [DONE]
-- Tomb (2) → tomb  [DONE]
-- Ruin (1) → ruin  [DONE]
-- Theatre (1) → theatre  [DONE]

-- Compound types stored in wrong case:
UPDATE unified_sites SET site_type = 'Barrow' WHERE source_id = 'ancient_nerds' AND site_type = 'barrow';
UPDATE unified_sites SET site_type = 'Cairn' WHERE source_id = 'ancient_nerds' AND site_type = 'cairn';
UPDATE unified_sites SET site_type = 'Castle/palace' WHERE source_id = 'ancient_nerds' AND site_type = 'castle/palace';
UPDATE unified_sites SET site_type = 'Cave Structures' WHERE source_id = 'ancient_nerds' AND site_type = 'cave structures';
UPDATE unified_sites SET site_type = 'Cave Structures, Rock art' WHERE source_id = 'ancient_nerds' AND site_type = 'cave structures, rock art';
UPDATE unified_sites SET site_type = 'Church/cathedral' WHERE source_id = 'ancient_nerds' AND site_type = 'church/cathedral';
UPDATE unified_sites SET site_type = 'City/town/settlement' WHERE source_id = 'ancient_nerds' AND site_type = 'city/town/settlement';
UPDATE unified_sites SET site_type = 'City/town/settlement, Pyramid complex' WHERE source_id = 'ancient_nerds' AND site_type = 'city/town/settlement, pyramid complex';
UPDATE unified_sites SET site_type = 'Dolmen' WHERE source_id = 'ancient_nerds' AND site_type = 'dolmen';
UPDATE unified_sites SET site_type = 'Earthwork' WHERE source_id = 'ancient_nerds' AND site_type = 'earthwork';
UPDATE unified_sites SET site_type = 'Elongated skulls' WHERE source_id = 'ancient_nerds' AND site_type = 'elongated skulls';
UPDATE unified_sites SET site_type = 'Fortress/citadel' WHERE source_id = 'ancient_nerds' AND site_type = 'fortress/citadel';
UPDATE unified_sites SET site_type = 'Gate/archway/bridge' WHERE source_id = 'ancient_nerds' AND site_type = 'gate/archway/bridge';
UPDATE unified_sites SET site_type = 'Geoglyphs' WHERE source_id = 'ancient_nerds' AND site_type = 'geoglyphs';
UPDATE unified_sites SET site_type = 'Geological interest' WHERE source_id = 'ancient_nerds' AND site_type = 'geological interest';
UPDATE unified_sites SET site_type = 'Henge' WHERE source_id = 'ancient_nerds' AND site_type = 'henge';
UPDATE unified_sites SET site_type = 'Magnetic anomaly' WHERE source_id = 'ancient_nerds' AND site_type = 'magnetic anomaly';
UPDATE unified_sites SET site_type = 'Megalithic statues' WHERE source_id = 'ancient_nerds' AND site_type = 'megalithic statues';
UPDATE unified_sites SET site_type = 'Megalithic stones' WHERE source_id = 'ancient_nerds' AND site_type = 'megalithic stones';
UPDATE unified_sites SET site_type = 'Megalithic structures' WHERE source_id = 'ancient_nerds' AND site_type = 'megalithic structures';
UPDATE unified_sites SET site_type = 'Megalithic walls' WHERE source_id = 'ancient_nerds' AND site_type = 'megalithic walls';
UPDATE unified_sites SET site_type = 'Minaret/tower' WHERE source_id = 'ancient_nerds' AND site_type = 'minaret/tower';
UPDATE unified_sites SET site_type = 'Mine/quarry' WHERE source_id = 'ancient_nerds' AND site_type = 'mine/quarry';
UPDATE unified_sites SET site_type = 'Mound/tumulus' WHERE source_id = 'ancient_nerds' AND site_type = 'mound/tumulus';
UPDATE unified_sites SET site_type = 'Museum' WHERE source_id = 'ancient_nerds' AND site_type = 'museum';
UPDATE unified_sites SET site_type = 'Necropolis/tombs complex' WHERE source_id = 'ancient_nerds' AND site_type = 'necropolis/tombs complex';
UPDATE unified_sites SET site_type = 'Petroglyphs' WHERE source_id = 'ancient_nerds' AND site_type = 'petroglyphs';
UPDATE unified_sites SET site_type = 'Polygonal masonry' WHERE source_id = 'ancient_nerds' AND site_type = 'polygonal masonry';
UPDATE unified_sites SET site_type = 'Pyramid complex' WHERE source_id = 'ancient_nerds' AND site_type = 'pyramid complex';
UPDATE unified_sites SET site_type = 'Reservoir/aqueduct/canal' WHERE source_id = 'ancient_nerds' AND site_type = 'reservoir/aqueduct/canal';
UPDATE unified_sites SET site_type = 'Residence/villa/farmhouse' WHERE source_id = 'ancient_nerds' AND site_type = 'residence/villa/farmhouse';
UPDATE unified_sites SET site_type = 'Road/avenue/trackway' WHERE source_id = 'ancient_nerds' AND site_type = 'road/avenue/trackway';
UPDATE unified_sites SET site_type = 'Rock art' WHERE source_id = 'ancient_nerds' AND site_type = 'rock art';
UPDATE unified_sites SET site_type = 'Rock relief/carving' WHERE source_id = 'ancient_nerds' AND site_type = 'rock relief/carving';
UPDATE unified_sites SET site_type = 'Sculptured stone' WHERE source_id = 'ancient_nerds' AND site_type = 'sculptured stone';
UPDATE unified_sites SET site_type = 'Stone circle' WHERE source_id = 'ancient_nerds' AND site_type = 'stone circle';
UPDATE unified_sites SET site_type = 'Stone cross' WHERE source_id = 'ancient_nerds' AND site_type = 'stone cross';
UPDATE unified_sites SET site_type = 'Temple complex' WHERE source_id = 'ancient_nerds' AND site_type = 'temple complex';
UPDATE unified_sites SET site_type = 'Timber circle' WHERE source_id = 'ancient_nerds' AND site_type = 'timber circle';
UPDATE unified_sites SET site_type = 'Underwater structures' WHERE source_id = 'ancient_nerds' AND site_type = 'underwater structures';
UPDATE unified_sites SET site_type = 'Well' WHERE source_id = 'ancient_nerds' AND site_type = 'well';
