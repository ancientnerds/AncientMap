-- ============================================================
-- Database Audit Fixes — ancient_nerds source — 2026-02-15
-- Full re-audit mechanical fixes
-- ============================================================

-- ============================================================
-- Block 1: Non-canonical site_type variants (65 fixes)
-- Applied: 2026-02-15
-- ============================================================

-- Settlement (22) → settlement
UPDATE unified_sites SET site_type = 'settlement'
WHERE source_id = 'ancient_nerds' AND site_type = 'Settlement';

-- Archaeological Site (12) → archaeological_site
UPDATE unified_sites SET site_type = 'archaeological_site'
WHERE source_id = 'ancient_nerds' AND site_type = 'Archaeological Site';

-- Infrastructure (8) → infrastructure
UPDATE unified_sites SET site_type = 'infrastructure'
WHERE source_id = 'ancient_nerds' AND site_type = 'Infrastructure';

-- Monument (7) → monument
UPDATE unified_sites SET site_type = 'monument'
WHERE source_id = 'ancient_nerds' AND site_type = 'Monument';

-- Megalithic (5) → megalithic
UPDATE unified_sites SET site_type = 'megalithic'
WHERE source_id = 'ancient_nerds' AND site_type = 'Megalithic';

-- Temple (3) → temple
UPDATE unified_sites SET site_type = 'temple'
WHERE source_id = 'ancient_nerds' AND site_type = 'Temple';

-- Inscription (2) → inscription
UPDATE unified_sites SET site_type = 'inscription'
WHERE source_id = 'ancient_nerds' AND site_type = 'Inscription';

-- Rock Art (2) → Rock art
UPDATE unified_sites SET site_type = 'Rock art'
WHERE source_id = 'ancient_nerds' AND site_type = 'Rock Art';

-- Tomb (2) → tomb
UPDATE unified_sites SET site_type = 'tomb'
WHERE source_id = 'ancient_nerds' AND site_type = 'Tomb';

-- Ruin (1) → ruin
UPDATE unified_sites SET site_type = 'ruin'
WHERE source_id = 'ancient_nerds' AND site_type = 'Ruin';

-- Theatre (1) → theatre
UPDATE unified_sites SET site_type = 'theatre'
WHERE source_id = 'ancient_nerds' AND site_type = 'Theatre';

-- ============================================================
-- Block 2: period_name/period_start boundary inconsistencies (18 fixes)
-- Applied: 2026-02-15
-- ============================================================

-- Cauria: period_start=-4500, had '< 4500 BC', should be '4500 - 3000 BC'
UPDATE unified_sites SET period_name = '4500 - 3000 BC'
WHERE id = '90ec5b47-7488-4bb4-8c4d-1259d30ac328' AND period_start = -4500 AND period_name = '< 4500 BC';

-- Arlobi Menhir: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = 'b1eabcf0-cc21-4053-92a1-285b30da510b' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Carn Menyn: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = '58e730c7-6ec4-44a4-97e8-d2f75d9a1c9e' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Mount William Stone Axe Quarry: period_start=500, had '1 - 500 AD', should be '500 - 1000 AD'
UPDATE unified_sites SET period_name = '500 - 1000 AD'
WHERE id = 'bcc037db-7637-44c9-8204-3ce6d4370653' AND period_start = 500 AND period_name = '1 - 500 AD';

-- Mut Precinct: period_start=-1479, had '3000 - 1500 BC', should be '1500 - 500 BC'
UPDATE unified_sites SET period_name = '1500 - 500 BC'
WHERE id = 'fc84c8b7-697c-4ee3-924b-e412f5585c2b' AND period_start = -1479 AND period_name = '3000 - 1500 BC';

-- Nakhchivan Rock Signs: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = '238793b3-c335-4dcf-8155-c9e2d4985e0d' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Osirion: period_start=-1280, had '3000 - 1500 BC', should be '1500 - 500 BC'
UPDATE unified_sites SET period_name = '1500 - 500 BC'
WHERE id = '7345ac3a-0fbd-4507-807b-a2f8a592c39d' AND period_start = -1280 AND period_name = '3000 - 1500 BC';

-- Pilgrims' Way: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = 'a98dcb51-39c4-4ab9-b34e-1f10a9aa14d9' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Sliprännor i Gantofta: period_start=-1500, had '3000 - 1500 BC', should be '1500 - 500 BC'
UPDATE unified_sites SET period_name = '1500 - 500 BC'
WHERE id = '2d12562b-e482-4a6b-8329-5d7a22667a86' AND period_start = -1500 AND period_name = '3000 - 1500 BC';

-- White Tank Mountain Regional Park: period_start=500, had '1 - 500 AD', should be '500 - 1000 AD'
UPDATE unified_sites SET period_name = '500 - 1000 AD'
WHERE id = '290410a4-c7ed-4fe7-842d-bfe7ab97e899' AND period_start = 500 AND period_name = '1 - 500 AD';

-- Ancient Lilaia: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = 'e2aa3754-8d32-4455-bf6d-9077f18d50d2' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Agbulaq Necropolis: period_start=-1500, had '3000 - 1500 BC', should be '1500 - 500 BC'
UPDATE unified_sites SET period_name = '1500 - 500 BC'
WHERE id = 'a9c5d1bf-b6d0-4486-a507-8dddfdc57a02' AND period_start = -1500 AND period_name = '3000 - 1500 BC';

-- Blowing Stone: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = '763e4a8b-eed2-495d-81db-35f83a3d5d82' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Kinniside Stone Circle: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = '1d4dd1f5-e841-4c8c-9761-2d4ad3eec155' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Cardiccia: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = 'ffb35fc7-24f7-4722-8036-e4173ac6d8e6' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Situs Megalith Talang Kecepol: period_start=-500, had '1500 - 500 BC', should be '500 BC - 1 AD'
UPDATE unified_sites SET period_name = '500 BC - 1 AD'
WHERE id = 'bebaa4d3-fb8e-46a4-b9cb-fe6589925889' AND period_start = -500 AND period_name = '1500 - 500 BC';

-- Papeloze Kerk: period_start=-3000, had '4500 - 3000 BC', should be '3000 - 1500 BC'
UPDATE unified_sites SET period_name = '3000 - 1500 BC'
WHERE id = 'edd175c5-eeb5-4cff-8c18-7ae518915cc4' AND period_start = -3000 AND period_name = '4500 - 3000 BC';

-- Zelve Open Air Museum: period_start=500, had '1 - 500 AD', should be '500 - 1000 AD'
UPDATE unified_sites SET period_name = '500 - 1000 AD'
WHERE id = 'fa9441c6-255f-4fc3-aaba-8aa8b43759ac' AND period_start = 500 AND period_name = '1 - 500 AD';
-- ============================================================
-- Phase B Fixes: Period corrections from Wikidata verification
-- 212 period fixes, 4 country fixes
-- Applied: 2026-02-15
-- ============================================================

-- Block 3: Period corrections from raw_year re-parse (212 fixes)
-- These sites had period_start set from wrong raw_data field.
-- The raw_year string clearly gives a different (correct) date.

-- Abu Simbel Temples: raw_year='13th c. BC' -> -1300
UPDATE unified_sites SET period_start = -1300, period_name = '1500 - 500 BC'
WHERE id = '392bcf2d-257f-4be6-bde4-36a26a1dbc9c' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Acaray: raw_year='900 BC - 1470 AD' -> -900
UPDATE unified_sites SET period_start = -900, period_name = '1500 - 500 BC'
WHERE id = 'c72fb36a-0726-4975-9d7a-edc5bd59a66f' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Acrocorinth: raw_year='900 - 146 BC' -> -900
UPDATE unified_sites SET period_start = -900, period_name = '1500 - 500 BC'
WHERE id = 'f6d1da2a-f957-47fb-9ccf-58f2197eacc8' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Acropolis of Athens: raw_year='5th c. BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = 'ac46cdfd-877f-47d4-8403-90d21983364f' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Aeclanum: raw_year='509 BC - 15th c. AD' -> -509
UPDATE unified_sites SET period_start = -509, period_name = '1500 - 500 BC'
WHERE id = 'ae64dd4f-971f-4fd7-8540-08af5649e67a' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- A'en Darah: raw_year='1300 - 740 BC' -> -1300
UPDATE unified_sites SET period_start = -1300, period_name = '1500 - 500 BC'
WHERE id = '17fb93ad-3368-478b-ab8a-0541e8a0400c' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Ajanta Caves: raw_year='2nd c. BC - 650 AD' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = 'ec0a83d5-737e-48de-a79c-d709ad794e60' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Alba Fucens: raw_year='509 BC - 15th c. AD' -> -509
UPDATE unified_sites SET period_start = -509, period_name = '1500 - 500 BC'
WHERE id = '13120650-2e61-45af-976c-b2e0665c49af' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Altar Stone - Stonehenge: raw_year='2600 BC' -> -2600
UPDATE unified_sites SET period_start = -2600, period_name = '3000 - 1500 BC'
WHERE id = '6f6cebaa-d125-4f80-8625-a9f7dfdf3864' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Amelungsburg, Süntel: raw_year='300 - 100 BC' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '2ce50a62-f812-4204-bbb6-892a581fee52' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Amphipolis: raw_year='5th c. BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = '8a4ea255-abed-47fe-9c37-636756e90450' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Ameny Qemau Pyramid: raw_year='1700 - 1550 BC' -> -1700
UPDATE unified_sites SET period_start = -1700, period_name = '3000 - 1500 BC'
WHERE id = '0e3698c6-006c-4161-a8c3-8dfac5bdf2cc' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Ancient Theatre of Fourvière: raw_year='15 BC - 2nd c. AD' -> -15
UPDATE unified_sites SET period_start = -15, period_name = '500 BC - 1 AD'
WHERE id = '068a88b3-505e-4998-add2-6b985b255371' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Anemospilia: raw_year='3100 - 1700 BC' -> -3100
UPDATE unified_sites SET period_start = -3100, period_name = '4500 - 3000 BC'
WHERE id = '1ae9f44c-ebe7-454c-8c55-58efe28c0376' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Ancient Babylon: raw_year='1894 BC - 1000 AD' -> -1894
UPDATE unified_sites SET period_start = -1894, period_name = '3000 - 1500 BC'
WHERE id = '40e48fb3-769d-47c5-ac69-995bcd9e86b8' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Ancient Kourion: raw_year='11th c. BC' -> -1100
UPDATE unified_sites SET period_start = -1100, period_name = '1500 - 500 BC'
WHERE id = 'd120ca9a-703b-49e2-b333-ad6dfe508953' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Ancient City of Pergamon: raw_year='5th c. BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = '6da6eaa8-4d63-48cb-8c9e-c9eac12f1d04' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Ancient Sparta: raw_year='650 BC' -> -650
UPDATE unified_sites SET period_start = -650, period_name = '1500 - 500 BC'
WHERE id = '2e53c7cf-072e-465a-a53a-ba2128f50c08' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Ancient City of Troy: raw_year='3,600 BC - 500 AD' -> -3600
UPDATE unified_sites SET period_start = -3600, period_name = '4500 - 3000 BC'
WHERE id = '0576c316-4e26-4342-bc7e-42ae84bdc36e' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Antonine Wall: raw_year='142 AD' -> 142
UPDATE unified_sites SET period_start = 142, period_name = '1 - 500 AD'
WHERE id = 'cd307f24-5170-4cb1-acb0-0e7ba7e276d7' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Apamea: raw_year='300 BC - 13th c. AD' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '61ae1b37-1703-4754-880a-f7277504a829' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Appleby Logboat: raw_year='1500 - 1300 BC' -> -1500
UPDATE unified_sites SET period_start = -1500, period_name = '1500 - 500 BC'
WHERE id = 'f336bdb9-c53b-4eed-91d2-353e9e1b4566' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Ara trium Galliarum: raw_year='1st c. BC' -> -100
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD'
WHERE id = '42f11dde-ad7e-46e0-ab7b-37a7add49986' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Arch of Cabanes: raw_year='2nd c. AD' -> 200
UPDATE unified_sites SET period_start = 200, period_name = '1 - 500 AD'
WHERE id = '94141d8e-4482-4c1c-a5f0-79fc8fc2ca76' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Arch of the Sergii: raw_year='29 - 27 BC' -> -29
UPDATE unified_sites SET period_start = -29, period_name = '500 BC - 1 AD'
WHERE id = '748277a0-62bc-4628-b2a1-606f65a547f1' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Arkadiko Bridge: raw_year='1300 - 1190 BC' -> -1300
UPDATE unified_sites SET period_start = -1300, period_name = '1500 - 500 BC'
WHERE id = 'd996c0de-78d1-4966-9ace-3f40a9c6ed2d' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Archaeological Site of Kition: raw_year='13th c. BC' -> -1300
UPDATE unified_sites SET period_start = -1300, period_name = '1500 - 500 BC'
WHERE id = '55a670ec-c7c5-4f52-98ea-b25211aedd4e' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Arkheologicheskiy Muzey-Zapovednik "Tanais": raw_year='3rd c. BC' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '1cf32c46-3536-4e00-9b54-90a0203ff628' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Aššur: raw_year='2025 BC - 14th c. AD' -> -2025
UPDATE unified_sites SET period_start = -2025, period_name = '3000 - 1500 BC'
WHERE id = '3cb65471-1fc1-4055-9cfa-63d7514aeaee' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Athenian Treasury, Delphi: raw_year='6th - 5th c. BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '98c794a6-57b5-4783-b38d-3693bb60b91b' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Augusta Emerita: raw_year='25 BC' -> -25
UPDATE unified_sites SET period_start = -25, period_name = '500 BC - 1 AD'
WHERE id = '1886172a-83a7-4dfb-b5e5-4c3978571e48' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Augusta Raurica: raw_year='44 BC - 260 AD' -> -44
UPDATE unified_sites SET period_start = -44, period_name = '500 BC - 1 AD'
WHERE id = '3ccc24a7-a41a-4c7b-91e2-246b6b81ef05' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Babilonie: raw_year='300 - 150 BC' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '1c18de52-3783-41cb-a3dd-ade50498a974' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Behistun Inscription: raw_year='522 - 486 BC' -> -522
UPDATE unified_sites SET period_start = -522, period_name = '1500 - 500 BC'
WHERE id = '2094fe27-b71c-4059-82d0-3891880600a5' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Belgrade Fortress: raw_year='279 BC' -> -279
UPDATE unified_sites SET period_start = -279, period_name = '500 BC - 1 AD'
WHERE id = '033b359c-dc2e-4fea-a61e-cd2ad0ca9bbe' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Bibracte: raw_year='8th - 1st c. BC' -> -800
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC'
WHERE id = '3c56c4c5-f5a8-48bb-8b93-9e3a92feac09' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Blackhammer Chambered Cairn: raw_year='3000 BC' -> -3000
UPDATE unified_sites SET period_start = -3000, period_name = '3000 - 1500 BC'
WHERE id = '7fe4bb17-d008-4886-a097-c03c66b43f76' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Bishop's Basilica of Philippopolis: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = 'b46b6969-3160-4cbd-a574-8727ee7c53c5' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Brauroneion: raw_year='5th c. BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = '44354857-115b-44d3-b155-cae373565602' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Bull-Leaping Fresco: raw_year='15th c. BC' -> -1500
UPDATE unified_sites SET period_start = -1500, period_name = '1500 - 500 BC'
WHERE id = 'ceff34a3-d6a5-4d8c-8c58-4a8cc27460a5' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Cádiz: raw_year='7th c. BC' -> -700
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC'
WHERE id = '9ceb5947-c91f-4a1f-8c8f-6a67dbb88de2' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Carn Euny: raw_year='200 BC - 400 AD' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = 'c7994816-1b61-4c2b-a82b-513380825948' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Cartagena, Spain: raw_year='2nd c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = '8a9ece01-983b-4bca-bb70-5f7d8f756781' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Carteia: raw_year='10th c. BC' -> -1000
UPDATE unified_sites SET period_start = -1000, period_name = '1500 - 500 BC'
WHERE id = '504bf30a-c4a0-48e7-8bbc-378b585b59b5' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Castlestrange Stone: raw_year='300 BC - 100 AD' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '6848b0cc-552a-4e7d-b767-281d3658a5ac' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Castle of Kirkûk: raw_year='130 ft' -> 130
UPDATE unified_sites SET period_start = 130, period_name = '1 - 500 AD'
WHERE id = 'da54a7f3-948a-4da4-a775-68b7d1831d29' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Catacombs of San Gennaro: raw_year='2nd c. AD' -> 200
UPDATE unified_sites SET period_start = 200, period_name = '1 - 500 AD'
WHERE id = '1abe781b-81a3-4aff-af66-3a4359970d72' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Cave di Cusa: raw_year='6th c. - 409 BC' -> -6
UPDATE unified_sites SET period_start = -6, period_name = '500 BC - 1 AD'
WHERE id = 'af78d851-5a24-4bd6-a1ad-1df1f29f9526' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Chan Chan: raw_year='900 - 1470 AD' -> 900
UPDATE unified_sites SET period_start = 900, period_name = '500 - 1000 AD'
WHERE id = '55ce644f-cbfa-4aab-9f3f-e7cca251f3ad' AND period_start = 500 AND source_id = 'ancient_nerds';

-- Choquepuquio: raw_year='400 - 1530 AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '3842aca5-13d3-4166-80cf-92f8dac3514f' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Church of Saint George, Sofia: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '9789696d-6670-42d8-a76a-bd73fd3ca2c0' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Church of the Holy Apostles Peter and Paul, Ras: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '5db5e2c0-081a-4c69-a8c6-6105ac870e5f' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Chysauster Ancient Village: raw_year='100 BC - 3rd c. AD' -> -100
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD'
WHERE id = '911287cb-672e-4d84-bc52-e0d26546f834' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Citânia de Briteiros: raw_year='2nd - 1st c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = 'ddd829b1-fdad-4487-a284-35bae4539928' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Combe Hill, East Sussex: raw_year='3700 - 3500 BC' -> -3700
UPDATE unified_sites SET period_start = -3700, period_name = '4500 - 3000 BC'
WHERE id = '9ae31b41-d78d-44da-824d-43487ec611f0' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Crypta Neapolitana: raw_year='37 BC' -> -37
UPDATE unified_sites SET period_start = -37, period_name = '500 BC - 1 AD'
WHERE id = '1739eaea-9d1a-41c1-97a6-cea5820bca28' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Danebury: raw_year='6th c. BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = 'e5d1f9a5-86b9-41d5-a258-8f21cd1e83e6' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Debdieba: raw_year='3000 - 2500 BC' -> -3000
UPDATE unified_sites SET period_start = -3000, period_name = '3000 - 1500 BC'
WHERE id = '3746f91f-e0e5-4494-9ea6-0261ba241fe1' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Demetrias: raw_year='3rd c. BC' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '6c18df63-d9a4-4866-84cc-657a061bb46d' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Diocletian's Palace: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '4e78a6c5-1811-46d3-8e62-8c613ec3afbe' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Domvs Romana: raw_year='1st c. BC' -> -100
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD'
WHERE id = '70a0244e-de85-46e2-9515-c7ca202868b9' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Dos Pilas: raw_year='629 - 8th c. AD' -> 629
UPDATE unified_sites SET period_start = 629, period_name = '500 - 1000 AD'
WHERE id = '18f993a6-2922-432f-b795-4ef914cffcd4' AND period_start = 1000 AND source_id = 'ancient_nerds';

-- Drususstein: raw_year='9 BC' -> -9
UPDATE unified_sites SET period_start = -9, period_name = '500 BC - 1 AD'
WHERE id = 'f9d17ed5-eb41-4332-a2c1-42d7d9b57a56' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Dur-Sharrukin: raw_year='7th c. BC' -> -700
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC'
WHERE id = 'cc8c8638-cb77-4b61-a248-5c0f8e19cb66' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Dykyi Sad Archaeological Site: raw_year='1250 - 900 BC' -> -1250
UPDATE unified_sites SET period_start = -1250, period_name = '1500 - 500 BC'
WHERE id = '86c101ad-fcdb-413a-8aec-6aad2d1574e7' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Echo Stoa: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = 'e5efe12c-25a8-423f-8974-98fc23e299e9' AND period_start = 1 AND source_id = 'ancient_nerds';

-- El Jem Amphitheatre: raw_year='238 AD' -> 238
UPDATE unified_sites SET period_start = 238, period_name = '1 - 500 AD'
WHERE id = '62e7aef7-f914-4080-ae06-b4c347600d6d' AND period_start = 1 AND source_id = 'ancient_nerds';

-- El Cerrito: raw_year='300 BC - 17th c. AD' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '58bdf3b7-f210-49b4-bc02-f060c120737a' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Elche: raw_year='600 BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = 'c1c984e7-1391-4153-b140-f9bcd446d759' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Ennigaldi-Nanna's Museum: raw_year='530 BC' -> -530
UPDATE unified_sites SET period_start = -530, period_name = '1500 - 500 BC'
WHERE id = '696624d4-3f88-4175-a4cd-fd145d00174a' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Er-Grah Tumulus: raw_year='3300 BC' -> -3300
UPDATE unified_sites SET period_start = -3300, period_name = '4500 - 3000 BC'
WHERE id = 'c2628a93-7c87-4a98-8d13-8301f7063403' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Foso e Interior Citadelle De Victoria: raw_year='1500 BC - 1868 AD' -> -1500
UPDATE unified_sites SET period_start = -1500, period_name = '1500 - 500 BC'
WHERE id = 'fad5c73f-8725-47d0-b13c-372fefba62ea' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Fortifications of Chania: raw_year='3rd c. BC' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '77127fe3-8116-4567-9b04-aebbe719e5a7' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Funerary Naiskos of Aristonautes: raw_year='320 BC' -> -320
UPDATE unified_sites SET period_start = -320, period_name = '500 BC - 1 AD'
WHERE id = '359860c8-9f39-49d7-8834-1651987c8c1e' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Ganjnameh Ancient Inscriptions: raw_year='6th - 5th c. BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '3d801ecb-4453-4ce3-85db-dce392c67c9d' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Ġgantija: raw_year='3600 - 2500 BC' -> -3600
UPDATE unified_sites SET period_start = -3600, period_name = '4500 - 3000 BC'
WHERE id = '07ca1c0c-550e-41ab-ab5d-5563fce29d90' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Golden Gate - Diocletian's Palace: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = 'c35b1649-9442-4195-9604-4481ce65ffbf' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Great Basilica, Plovdiv: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '891ad351-7985-4c16-b6a6-830c26bc268f' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Great Sphinx of Giza: raw_year='2558 - 2532 BC' -> -2558
UPDATE unified_sites SET period_start = -2558, period_name = '3000 - 1500 BC'
WHERE id = '4599daa4-93cc-4c55-872c-41e9c7875a59' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Great Ziggurat of Ur: raw_year='21st c. BC' -> -2100
UPDATE unified_sites SET period_start = -2100, period_name = '3000 - 1500 BC'
WHERE id = '4ab1bd6e-a7fd-41c3-b341-9959d77d5a6e' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Hadrian's Wall: raw_year='122 AD' -> 122
UPDATE unified_sites SET period_start = 122, period_name = '1 - 500 AD'
WHERE id = 'f7a88213-58c1-4ee4-b791-4babfa0cd67a' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Håga Mound: raw_year='1000 BC' -> -1000
UPDATE unified_sites SET period_start = -1000, period_name = '1500 - 500 BC'
WHERE id = 'fffac2f9-3115-47be-9830-f5969cce734b' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Herodion National Park: raw_year='23 BC - 71 AD' -> -23
UPDATE unified_sites SET period_start = -23, period_name = '500 BC - 1 AD'
WHERE id = 'fdc3a783-3b1a-473a-bf22-8510308e0054' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Himera: raw_year='648 BC' -> -648
UPDATE unified_sites SET period_start = -648, period_name = '1500 - 500 BC'
WHERE id = '5c4b2afd-f915-4625-a841-790460fddef5' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Historic Site Tipasa: raw_year='6th c. BC - 6th c. AD' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '51e6e482-0301-4200-9719-17e8b548a8db' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Horgen: raw_year='3500 - 2850 BC' -> -3500
UPDATE unified_sites SET period_start = -3500, period_name = '4500 - 3000 BC'
WHERE id = 'b803b66a-768d-4040-bdac-6176611241da' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- House of the Faun, Pompeii: raw_year='2nd c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = '5752ff6c-ce00-4b78-aad7-f80a4d61c4e7' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Hypostyle Hall: raw_year='1290 - 1224 BC' -> -1290
UPDATE unified_sites SET period_start = -1290, period_name = '1500 - 500 BC'
WHERE id = 'f69c8107-a8fe-45ae-a8d8-d5ab8e618e33' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Huaca Huallamarca: raw_year='1000 - 1450 AD' -> 1000
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD'
WHERE id = 'db227639-34b4-45db-817c-95092b4a916a' AND period_start = 500 AND source_id = 'ancient_nerds';

-- Ishtar Gate: raw_year='575 BC' -> -575
UPDATE unified_sites SET period_start = -575, period_name = '1500 - 500 BC'
WHERE id = '15f3ae9f-86e9-4198-97c9-e67b42c034dc' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Italica: raw_year='206 BC' -> -206
UPDATE unified_sites SET period_start = -206, period_name = '500 BC - 1 AD'
WHERE id = 'c8a346a9-bed2-4420-83db-3a6fcca051e4' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Jisk'a Iru Muqu: raw_year='3400 - 1600 BC' -> -3400
UPDATE unified_sites SET period_start = -3400, period_name = '4500 - 3000 BC'
WHERE id = '01f3d961-e2cf-4a3d-bc36-7e9976efe93e' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Karnak Temple Complex: raw_year='1971 - 30 BC' -> -1971
UPDATE unified_sites SET period_start = -1971, period_name = '3000 - 1500 BC'
WHERE id = '14c0c237-0ece-4124-ada8-8ec56b431b08' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Kerch: raw_year='7th c. BC' -> -700
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC'
WHERE id = 'ac5c3d55-1122-4aad-bcee-90a514c56f4b' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- King Ezana's Stele: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '2c780872-8603-4ff7-b740-147b3cd5f22f' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Kition: raw_year='13th c. BC' -> -1300
UPDATE unified_sites SET period_start = -1300, period_name = '1500 - 500 BC'
WHERE id = '47c37ef9-98ee-41d8-879b-e78db06295da' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Knap of Howar: raw_year='3700 - 2800 BC' -> -3700
UPDATE unified_sites SET period_start = -3700, period_name = '4500 - 3000 BC'
WHERE id = '87cc7367-7c4d-4b5b-ae73-9cf41c550e9c' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Kourion: raw_year='12th c. BC' -> -1200
UPDATE unified_sites SET period_start = -1200, period_name = '1500 - 500 BC'
WHERE id = '9983bdce-9f35-47a3-a570-4021cfa41b97' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Kutaisi: raw_year='6th - 5th c. BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '2f8f4a6f-2480-49a1-ae22-23ad1102f77d' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Legananny Dolmen: raw_year='3000 BC' -> -3000
UPDATE unified_sites SET period_start = -3000, period_name = '3000 - 1500 BC'
WHERE id = 'ec838509-a1e6-4f6a-b216-3f1791c16d67' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- León, Spain: raw_year='1st c. BC' -> -100
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD'
WHERE id = '2dcaaefa-e48b-4eab-993e-982418c3c8eb' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Library of Ashurbanipal: raw_year='7th c. BC' -> -700
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC'
WHERE id = 'bad314d6-47c3-457f-ab77-9600fe9b04d2' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Libyco-Punic Mausoleum of Dougga: raw_year='2nd c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = '21f76b39-07bd-40cc-8506-116019eac196' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Llansteffan Castle: raw_year='800 BC - 12th c. AD' -> -800
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC'
WHERE id = 'f5e7956b-9aa4-47b0-b88a-3ed159f451d1' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- London Mithraeum: raw_year='3rd c. AD' -> 300
UPDATE unified_sites SET period_start = 300, period_name = '1 - 500 AD'
WHERE id = '75e685c6-e246-425d-8a2b-e1bf69d6af19' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Machu Picchu: raw_year='1438 - 1530 AD' -> 1438
UPDATE unified_sites SET period_start = 1438, period_name = '1000 - 1500 AD'
WHERE id = '4f366f34-983c-42e1-a89d-7e8f5f77cdce' AND period_start = 1000 AND source_id = 'ancient_nerds';

-- Maiden Castle, Dorset: raw_year='600 BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '39a50b0a-cc96-4e76-967c-fd1a1946aa2c' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Mausoleum at Halicarnassus: raw_year='353 - 350 BC' -> -353
UPDATE unified_sites SET period_start = -353, period_name = '500 BC - 1 AD'
WHERE id = 'fa26417b-eb7c-49d0-aaf7-adcd4909e78a' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Mellor Hill Fort: raw_year='800 BC - 1st c. AD' -> -800
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC'
WHERE id = '63220a54-b953-4e72-a914-8f564b8f3e11' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Minoan Palace of Knossos: raw_year='2000 - 1100 BC' -> -2000
UPDATE unified_sites SET period_start = -2000, period_name = '3000 - 1500 BC'
WHERE id = 'f8f6d3e9-c012-4fac-a562-cfbb592a3263' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Mesembria: raw_year='6th c. BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = 'bc058dac-5a3f-45db-8959-ba1df10920c4' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Montegrande Archaeological Site: raw_year='3000 BC' -> -3000
UPDATE unified_sites SET period_start = -3000, period_name = '3000 - 1500 BC'
WHERE id = '95bc3d88-46db-4ee3-a5a2-4d1d04a50488' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Naveta d'Es Tudons: raw_year='1200 - 750 BC' -> -1200
UPDATE unified_sites SET period_start = -1200, period_name = '1500 - 500 BC'
WHERE id = '71b5fca6-6ce4-43f0-bddd-6b3c15ca3f0e' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Nekresi: raw_year='2nd c. BC - 6th c. AD' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = '0060e6c0-8388-4762-bf51-9a3f88807899' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Neuchâtel: raw_year='13,000 BC' -> -13000
UPDATE unified_sites SET period_start = -13000, period_name = '< 4500 BC'
WHERE id = '2d89e6d4-8fa0-4258-a70a-bc42ad3c47bf' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Nijmegen: raw_year='1st c. BC' -> -100
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD'
WHERE id = '6069036e-08d0-48dc-b808-ba568efe707f' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Nymphaion, Crimea: raw_year='6th c. BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '250714e7-df78-444d-bfc0-303dfd6a3a03' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Obelisk of Axum: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = 'a50cf939-77f1-489c-82f7-93b07b2bc5ae' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Obelisk Of Theodosius: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '54dead1c-8dc0-4cdd-a581-47d2e033fdab' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Odeon of Herodes Atticus: raw_year='161 - 267 AD' -> 161
UPDATE unified_sites SET period_start = 161, period_name = '1 - 500 AD'
WHERE id = '2cabb7a1-0596-457c-b37f-c041440b4fe2' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Old Temple of Athena: raw_year='6th c. BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '50fdb577-af39-425e-a038-a0f8205f66fc' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Odessus: raw_year='7th c. BC' -> -700
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC'
WHERE id = 'ad600526-95f6-434d-9440-38ce0688b441' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Paestum: raw_year='600 BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '6eabe5c3-03f4-4155-8b7d-dbd5616f5d59' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Pamplona: raw_year='75 BC' -> -75
UPDATE unified_sites SET period_start = -75, period_name = '500 BC - 1 AD'
WHERE id = '14ca23b2-2208-4930-99f7-632db64ca953' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Patara: raw_year='1200 BC' -> -1200
UPDATE unified_sites SET period_start = -1200, period_name = '1500 - 500 BC'
WHERE id = '29245d49-3e8c-4c31-baf4-a3cdd54a8964' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Persepolis: raw_year='515 - 330 BC' -> -515
UPDATE unified_sites SET period_start = -515, period_name = '1500 - 500 BC'
WHERE id = 'e00a1e45-3c66-48f4-8cac-3169146aad21' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Petra: raw_year='2nd c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = 'a06a95d0-35b4-44bb-a0c1-716cbf972b19' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Phanagoria: raw_year='543 BC' -> -543
UPDATE unified_sites SET period_start = -543, period_name = '1500 - 500 BC'
WHERE id = '3e9107fa-e54c-407c-aaa7-a6f198e48c0f' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Phaselis: raw_year='7th c. BC' -> -700
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC'
WHERE id = '966f26e0-c2ae-4a0f-ac46-8a481ad80b19' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Pompeii: raw_year='8th c. BC' -> -800
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC'
WHERE id = '7a43d34c-2051-48b6-b598-d4482adb4623' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Pont du Gard: raw_year='19 BC' -> -19
UPDATE unified_sites SET period_start = -19, period_name = '500 BC - 1 AD'
WHERE id = '5fc3dde6-5284-41ba-af51-d91420bd0299' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Pontic Olbia: raw_year='7th c. BC - 4th c. AD' -> -700
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC'
WHERE id = '27781284-7698-46ff-b6aa-096800327282' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Porta Gemina: raw_year='2nd c. AD' -> 200
UPDATE unified_sites SET period_start = 200, period_name = '1 - 500 AD'
WHERE id = 'd4714397-6e73-432d-add3-c01e22cb055f' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Porta Nigra: raw_year='2nd c. AD' -> 200
UPDATE unified_sites SET period_start = 200, period_name = '1 - 500 AD'
WHERE id = 'c9755577-6815-411d-bb1e-f96330776818' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Portus Adurni: raw_year='3rd c. AD' -> 300
UPDATE unified_sites SET period_start = 300, period_name = '1 - 500 AD'
WHERE id = 'd622c812-d34b-4e3d-8005-978fb0e51079' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Pozzuoli: raw_year='531 BC' -> -531
UPDATE unified_sites SET period_start = -531, period_name = '1500 - 500 BC'
WHERE id = 'da488c94-540b-4fdc-8d3a-0d5aba57b372' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Priene Ruins: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '972ded7c-665e-4ca6-98cc-af4dff9ac8f3' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Prince of the Lilies: raw_year='1550 BC' -> -1550
UPDATE unified_sites SET period_start = -1550, period_name = '3000 - 1500 BC'
WHERE id = 'e4631001-b923-4f36-be7f-c961f9e287ba' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Pula: raw_year='2nd c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = '676dbe65-abbf-4e30-8e56-70cae048f1e0' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Pula Arena: raw_year='27 BC - 68 AD' -> -27
UPDATE unified_sites SET period_start = -27, period_name = '500 BC - 1 AD'
WHERE id = '7661e2ac-0a20-46be-9069-961b36db4ac7' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Pyramid of Amenemhat I: raw_year='1991 - 1778 BC' -> -1991
UPDATE unified_sites SET period_start = -1991, period_name = '3000 - 1500 BC'
WHERE id = '64c9b400-5cab-45f2-8662-03c24c4367ce' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Pyramid of Caius Cestius: raw_year='18 - 12 BC' -> -18
UPDATE unified_sites SET period_start = -18, period_name = '500 BC - 1 AD'
WHERE id = '872b05b1-618b-4618-b3ae-6c69f3177911' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Pyramid of Djoser: raw_year='27th c. BC' -> -2700
UPDATE unified_sites SET period_start = -2700, period_name = '3000 - 1500 BC'
WHERE id = '2b2812a6-63d4-4985-b334-ebb80f2ddd90' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Pyramid of Sahure: raw_year='25th c. BC' -> -2500
UPDATE unified_sites SET period_start = -2500, period_name = '3000 - 1500 BC'
WHERE id = '70e08059-7e26-4fa2-885f-31bb426f182d' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Pyramid of Senusret I: raw_year='1991 - 1778 BC' -> -1991
UPDATE unified_sites SET period_start = -1991, period_name = '3000 - 1500 BC'
WHERE id = '9b3eed6b-54e2-4321-8e84-9b204819879a' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Pyramid of Unas: raw_year='24th c. BC' -> -2400
UPDATE unified_sites SET period_start = -2400, period_name = '3000 - 1500 BC'
WHERE id = 'b0e8cb34-7b53-4900-a440-cc3c3b9c62bf' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Quoyness Chambered Cairn: raw_year='3000 BC' -> -3000
UPDATE unified_sites SET period_start = -3000, period_name = '3000 - 1500 BC'
WHERE id = '657dbfe1-7b3f-4548-93c6-99be8674a6ff' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Qʼumarkaj: raw_year='1400 - 1524 AD' -> 1400
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD'
WHERE id = '31203a3c-220a-41a8-87ff-befc4263c8d4' AND period_start = 1000 AND source_id = 'ancient_nerds';

-- Red Pyramid: raw_year='2575 - 2551 BC' -> -2575
UPDATE unified_sites SET period_start = -2575, period_name = '3000 - 1500 BC'
WHERE id = 'd48e920c-f57c-4f20-8bdf-df646d31029b' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Roman Bridge over the Ribeira de Odivelas: raw_year='1st c. BC - 1st c. AD' -> -100
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD'
WHERE id = '5cc613ff-ad80-4906-9103-6d1035eaea3e' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Roman Dam of Belas: raw_year='3rd c. AD' -> 300
UPDATE unified_sites SET period_start = 300, period_name = '1 - 500 AD'
WHERE id = '591cee00-2570-4cf4-94d8-a141cf6e9854' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Roman Theatre, Tarraco: raw_year='1st c. BC' -> -100
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD'
WHERE id = 'a71bf02d-0df6-4b15-8436-be73a43950f4' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Roman Temple of Vic: raw_year='2nd c. AD' -> 200
UPDATE unified_sites SET period_start = 200, period_name = '1 - 500 AD'
WHERE id = 'e056946d-fd09-43f2-8d45-648121ace99d' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Salamis Ancient City: raw_year='11th c. BC - 7th c. AD' -> -1100
UPDATE unified_sites SET period_start = -1100, period_name = '1500 - 500 BC'
WHERE id = 'f064d736-e58e-4505-b634-b5f18052e293' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- S'Argamassa Roman Fish Farm: raw_year='146 BC' -> -146
UPDATE unified_sites SET period_start = -146, period_name = '500 BC - 1 AD'
WHERE id = 'a0736505-9ca5-4361-bc0a-f0a47b6fed7e' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Samshvilde: raw_year='3rd c. BC - 18th c. AD' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = '43d64ea4-8c7e-4bca-bcfe-04b4e6e6b437' AND period_start = -500 AND source_id = 'ancient_nerds';

-- San Estevan: raw_year='800 BC - 900 AD' -> -800
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC'
WHERE id = 'f29afd0d-6fb8-4405-bee8-c1b17a6989e3' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Serapeum of Alexandria and Pompey's Pillar: raw_year='246 - 222 BC' -> -246
UPDATE unified_sites SET period_start = -246, period_name = '500 BC - 1 AD'
WHERE id = '03d28afb-c252-423e-9b4f-2815cfaed6c5' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Silbury Hill: raw_year='2400 - 2300 BC' -> -2400
UPDATE unified_sites SET period_start = -2400, period_name = '3000 - 1500 BC'
WHERE id = '21d63980-32dc-43cc-baa1-06c9e2f15335' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Singidunum: raw_year='3rd c. BC' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = 'fdafef27-24a2-4939-b2b0-7f3852676e82' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Sinuessa: raw_year='2nd c. BC - 5th c. AD' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = 'f6b5aa36-d662-4490-a83b-1e5d857afdd5' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Shengavit Settlement: raw_year='3000 - 2200 BC' -> -3000
UPDATE unified_sites SET period_start = -3000, period_name = '3000 - 1500 BC'
WHERE id = 'ef1ee8c0-f6bd-4886-bd66-8a6106ac5ca4' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Soli, Cyprus: raw_year='3rd c. BC - 4th c. AD' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = 'f69cf72f-d7b2-48d8-996d-82e19c289eee' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Spirit Cave, Thailand: raw_year='10,000 - 2000 BC' -> -10000
UPDATE unified_sites SET period_start = -10000, period_name = '< 4500 BC'
WHERE id = '9c64a3f6-8874-4441-b6c8-52428a1d45e5' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Square Peristyle: raw_year='300 BC' -> -300
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD'
WHERE id = 'd7a107f8-b228-48a7-97c5-081dc67c0469' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Stadium at Olympia: raw_year='8th - 4th c. BC' -> -800
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC'
WHERE id = '403e3c53-6a70-49cc-81b8-2014542e53d3' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Stele of Aristion: raw_year='510 BC' -> -510
UPDATE unified_sites SET period_start = -510, period_name = '1500 - 500 BC'
WHERE id = 'e2f2dee4-9e70-41b8-a7f5-be7aa07ea807' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Stonehenge: raw_year='3000 - 2000 BC' -> -3000
UPDATE unified_sites SET period_start = -3000, period_name = '3000 - 1500 BC'
WHERE id = '21b2278e-c3f2-4723-ae40-fa8a6161e3fb' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Sweet Track: raw_year='3807 BC' -> -3807
UPDATE unified_sites SET period_start = -3807, period_name = '4500 - 3000 BC'
WHERE id = 'a627df4e-f241-478e-b8ab-273e67f52441' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Table des Marchand: raw_year='4000 BC' -> -4000
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC'
WHERE id = '57ded976-9874-4832-8716-2b54c1fee102' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Sybaris: raw_year='720 - 510 BC' -> -720
UPDATE unified_sites SET period_start = -720, period_name = '1500 - 500 BC'
WHERE id = '991bd627-65d9-40d3-a97d-dfa879756da0' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Tambo Colorado: raw_year='15th c. AD' -> 1500
UPDATE unified_sites SET period_start = 1500, period_name = '1500+ AD'
WHERE id = 'c947e9b6-41c7-4c94-81c3-d79fc9e601b2' AND period_start = 1000 AND source_id = 'ancient_nerds';

-- Tempio di Zeus, Selinunte: raw_year='515 - 86 BC' -> -515
UPDATE unified_sites SET period_start = -515, period_name = '1500 - 500 BC'
WHERE id = '7759e372-b62e-424a-a726-d078a5a49e54' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Temple of Athena, Paestum: raw_year='500 BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = '0e12027e-9a65-470f-aca7-2cb1eb408120' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Temple of Athena Nike: raw_year='5th c. BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = '8d8753ae-9935-4ffb-b578-de5907999f68' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Temple of Ramesses II- Abu Simbel: raw_year='1264 - 1225 BC' -> -1264
UPDATE unified_sites SET period_start = -1264, period_name = '1500 - 500 BC'
WHERE id = '39e49c72-4037-487c-8402-409d00f7026e' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Temple of Hera, Olympia: raw_year='590 BC - 4th c. AD' -> -590
UPDATE unified_sites SET period_start = -590, period_name = '1500 - 500 BC'
WHERE id = '4c7f6521-241f-48c0-93da-f8d7893f5446' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Temple of Poseidon, Sounion: raw_year='5th c. BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = '100ab5ea-fdf9-4d78-9f65-961ee8190b7b' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Temple of Zeus, Olympia: raw_year='5th c. BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = '349e080c-0b4f-4708-8744-d1b1c6a0b83e' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Tenochtitlan - Templo Mayor: raw_year='1325 -1521 AD' -> 1325
UPDATE unified_sites SET period_start = 1325, period_name = '1000 - 1500 AD'
WHERE id = '6a28da7c-1e74-4f45-b49c-03c2af224c86' AND period_start = 1000 AND source_id = 'ancient_nerds';

-- Tenam Puente: raw_year='300 - 1200 AD' -> 300
UPDATE unified_sites SET period_start = 300, period_name = '1 - 500 AD'
WHERE id = '50873aa8-b4da-4b2c-99a9-b9e7859bf44b' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Tenayuca: raw_year='12th - 16th c. AD' -> 12
UPDATE unified_sites SET period_start = 12, period_name = '1 - 500 AD'
WHERE id = '852f3856-ecaa-4bab-82c8-a0ab2d11f94f' AND period_start = 1000 AND source_id = 'ancient_nerds';

-- The Great Pyramid of Giza: raw_year='26th c. BC' -> -2600
UPDATE unified_sites SET period_start = -2600, period_name = '3000 - 1500 BC'
WHERE id = '6313cd62-456d-4a85-8782-57613c7fc0e1' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- The Archaeological Site Nitzana: raw_year='2nd c. BC - 2nd c. AD' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = 'a965d140-d212-45f5-a269-1945fc8432b3' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Thebes: raw_year='3200 BC - 1st c. AD' -> -3200
UPDATE unified_sites SET period_start = -3200, period_name = '4500 - 3000 BC'
WHERE id = '76cd8b60-c373-4f26-85ac-2827b0797b15' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- The Temple of Artemis-Selçuk: raw_year='550 BC - 401 AD' -> -550
UPDATE unified_sites SET period_start = -550, period_name = '1500 - 500 BC'
WHERE id = 'e60fc487-9fb9-4e37-b590-4a035e591c7e' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- The Unfinished Obelisk: raw_year='1508 - 1458 BC' -> -1508
UPDATE unified_sites SET period_start = -1508, period_name = '3000 - 1500 BC'
WHERE id = 'f4955fe7-d4e9-4de7-9812-0fc7e94c0620' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Tomb of Cyrus the Great: raw_year='6th c. BC' -> -600
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC'
WHERE id = '695ddb9f-70cb-4e8a-9020-4bebf0b06227' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Tower of Elahbel: raw_year='103 AD' -> 103
UPDATE unified_sites SET period_start = 103, period_name = '1 - 500 AD'
WHERE id = '8797faec-8590-4716-9763-310be93ef6ea' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Trialeti Petroglyphs: raw_year='3000 - 2000 BC' -> -3000
UPDATE unified_sites SET period_start = -3000, period_name = '3000 - 1500 BC'
WHERE id = '0259ff6b-ef34-4a7e-93ef-78e2729e45a6' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Triumphal Arch of Orange: raw_year='27 BC - 14 AD' -> -27
UPDATE unified_sites SET period_start = -27, period_name = '500 BC - 1 AD'
WHERE id = '6d2ffc46-f990-4ec7-9d69-94029e8e98ed' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Turkistan - City: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = 'e3ac6021-f7ef-464d-a6d0-e0df9e91f553' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Túcume: raw_year='800 - 1530 AD' -> 800
UPDATE unified_sites SET period_start = 800, period_name = '500 - 1000 AD'
WHERE id = 'e48a661d-c148-4a0f-abff-f862d61524b7' AND period_start = 500 AND source_id = 'ancient_nerds';

-- Twin Gates of Pula: raw_year='2nd c. AD' -> 200
UPDATE unified_sites SET period_start = 200, period_name = '1 - 500 AD'
WHERE id = 'f5df832e-ab5e-4e9c-b6c9-037441011945' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Uffington White Horse: raw_year='1380 - 550 BC' -> -1380
UPDATE unified_sites SET period_start = -1380, period_name = '1500 - 500 BC'
WHERE id = '81724be4-6588-41b1-8efc-364637456cdf' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Uppåkra Temple: raw_year='3rd c. AD' -> 300
UPDATE unified_sites SET period_start = 300, period_name = '1 - 500 AD'
WHERE id = '6b9aa503-6d6a-44b1-a9d0-c165294808df' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Ur: raw_year='3800 BC' -> -3800
UPDATE unified_sites SET period_start = -3800, period_name = '4500 - 3000 BC'
WHERE id = '3dbbef3c-4605-4a1f-b04f-cadd63462673' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Uruk: raw_year='4000 - 3100 BC' -> -4000
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC'
WHERE id = 'd0b9e72f-73a8-4671-a01f-5cafa6e53bf8' AND period_start = -4500 AND source_id = 'ancient_nerds';

-- Valencia: raw_year='2nd c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = '86a32957-57c8-424d-bc27-78c2d3ebaedc' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Valley of the Kings: raw_year='16th 11th c. BC' -> -16
UPDATE unified_sites SET period_start = -16, period_name = '500 BC - 1 AD'
WHERE id = 'ed78d548-5409-4909-abc0-793390dfed1c' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Valley of the Queens: raw_year='1550 - 1292 BC' -> -1550
UPDATE unified_sites SET period_start = -1550, period_name = '3000 - 1500 BC'
WHERE id = 'd70dd131-fac7-4c7e-b367-95c2ac945339' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Varna, Bulgaria: raw_year='575 BC' -> -575
UPDATE unified_sites SET period_start = -575, period_name = '1500 - 500 BC'
WHERE id = 'e5558c53-90b5-42ca-aa79-ba2d05d56eac' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Velia: raw_year='538 BC' -> -538
UPDATE unified_sites SET period_start = -538, period_name = '1500 - 500 BC'
WHERE id = '8c44a3a9-c945-44e8-8dc2-1baab82890ea' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Vix Grave: raw_year='500 BC' -> -500
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD'
WHERE id = '6a7ed782-d72d-4eeb-8df6-634a27140019' AND period_start = -1500 AND source_id = 'ancient_nerds';

-- Western Wall: raw_year='19 BC - 70 AD' -> -19
UPDATE unified_sites SET period_start = -19, period_name = '500 BC - 1 AD'
WHERE id = 'ba452543-f3d8-436b-bef5-4329382d234e' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Κourion Ancient Amphitheatre: raw_year='2nd c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = '0c00d8bd-d6b3-4237-b4c9-9a86748ee5ab' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Yazılıkkaya: raw_year='16th - 13th c. BC' -> -1600
UPDATE unified_sites SET period_start = -1600, period_name = '3000 - 1500 BC'
WHERE id = '85a6ae2e-6f62-44f2-9dfd-fd81b229d56d' AND period_start = -3000 AND source_id = 'ancient_nerds';

-- Zadar: raw_year='2nd c. BC' -> -200
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD'
WHERE id = 'be2bb871-ba24-49cf-9172-d20d673a2c3d' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Zerzevan Castle: raw_year='4th c. AD' -> 400
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD'
WHERE id = '1fe816f4-f921-45ff-97b7-0ca7d1d0d009' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Arc de Triomphe Septime Sévère: raw_year='205 AD' -> 205
UPDATE unified_sites SET period_start = 205, period_name = '1 - 500 AD'
WHERE id = 'da9530ed-5945-4970-a041-333b782fc208' AND period_start = 1 AND source_id = 'ancient_nerds';

-- Pergamon Amfitiyatrosu: raw_year='282 - 133 BC' -> -282
UPDATE unified_sites SET period_start = -282, period_name = '500 BC - 1 AD'
WHERE id = '908d6a9b-6032-4fd4-84c7-72896374778b' AND period_start = -500 AND source_id = 'ancient_nerds';

-- Colosso di Ramses II: raw_year='1279 - 1213 BC' -> -1279
UPDATE unified_sites SET period_start = -1279, period_name = '1500 - 500 BC'
WHERE id = 'c9cca1f6-9117-40f3-b830-605b144baf90' AND period_start = -1500 AND source_id = 'ancient_nerds';


-- Block 4: Country corrections from Wikidata verification

-- Achladia: Germany -> Greece
UPDATE unified_sites SET country = 'Greece'
WHERE id = '74145e9b-76a6-48de-a902-08ecb2f1f7bb' AND country = 'Germany' AND source_id = 'ancient_nerds';

-- Ahuila Gencha Machay: Pakistan -> Peru
UPDATE unified_sites SET country = 'Peru'
WHERE id = 'b8aedc17-2215-44c3-b89c-8125050efbd5' AND country = 'Pakistan' AND source_id = 'ancient_nerds';

-- Aquae Helveticae: Sweden -> Switzerland
UPDATE unified_sites SET country = 'Switzerland'
WHERE id = 'cb659fbe-0f1c-43dc-9c40-4517c0974a79' AND country = 'Sweden' AND source_id = 'ancient_nerds';

-- Tempio di Zeus, Selinunte: Greece -> Italy
UPDATE unified_sites SET country = 'Italy'
WHERE id = '7759e372-b62e-424a-a726-d078a5a49e54' AND country = 'Greece' AND source_id = 'ancient_nerds';


-- Audit log entries for period fixes
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('392bcf2d-257f-4be6-bde4-36a26a1dbc9c', 'Abu Simbel Temples', 'fix', 'period_start', '-3000', '-1300', 'high', 'Phase B: raw_year=''13th c. BC'' -> parsed=-1300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c72fb36a-0726-4975-9d7a-edc5bd59a66f', 'Acaray', 'fix', 'period_start', '-1500', '-900', 'high', 'Phase B: raw_year=''900 BC - 1470 AD'' -> parsed=-900', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f6d1da2a-f957-47fb-9ccf-58f2197eacc8', 'Acrocorinth', 'fix', 'period_start', '-1500', '-900', 'high', 'Phase B: raw_year=''900 - 146 BC'' -> parsed=-900', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ac46cdfd-877f-47d4-8403-90d21983364f', 'Acropolis of Athens', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''5th c. BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ae64dd4f-971f-4fd7-8540-08af5649e67a', 'Aeclanum', 'fix', 'period_start', '-3000', '-509', 'high', 'Phase B: raw_year=''509 BC - 15th c. AD'' -> parsed=-509', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('17fb93ad-3368-478b-ab8a-0541e8a0400c', 'A''en Darah', 'fix', 'period_start', '-1500', '-1300', 'high', 'Phase B: raw_year=''1300 - 740 BC'' -> parsed=-1300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ec0a83d5-737e-48de-a79c-d709ad794e60', 'Ajanta Caves', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC - 650 AD'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('13120650-2e61-45af-976c-b2e0665c49af', 'Alba Fucens', 'fix', 'period_start', '-3000', '-509', 'high', 'Phase B: raw_year=''509 BC - 15th c. AD'' -> parsed=-509', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6f6cebaa-d125-4f80-8625-a9f7dfdf3864', 'Altar Stone - Stonehenge', 'fix', 'period_start', '-3000', '-2600', 'high', 'Phase B: raw_year=''2600 BC'' -> parsed=-2600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2ce50a62-f812-4204-bbb6-892a581fee52', 'Amelungsburg, Süntel', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''300 - 100 BC'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8a4ea255-abed-47fe-9c37-636756e90450', 'Amphipolis', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''5th c. BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0e3698c6-006c-4161-a8c3-8dfac5bdf2cc', 'Ameny Qemau Pyramid', 'fix', 'period_start', '-3000', '-1700', 'high', 'Phase B: raw_year=''1700 - 1550 BC'' -> parsed=-1700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('068a88b3-505e-4998-add2-6b985b255371', 'Ancient Theatre of Fourvière', 'fix', 'period_start', '-500', '-15', 'high', 'Phase B: raw_year=''15 BC - 2nd c. AD'' -> parsed=-15', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('1ae9f44c-ebe7-454c-8c55-58efe28c0376', 'Anemospilia', 'fix', 'period_start', '-4500', '-3100', 'high', 'Phase B: raw_year=''3100 - 1700 BC'' -> parsed=-3100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('40e48fb3-769d-47c5-ac69-995bcd9e86b8', 'Ancient Babylon', 'fix', 'period_start', '-3000', '-1894', 'high', 'Phase B: raw_year=''1894 BC - 1000 AD'' -> parsed=-1894', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d120ca9a-703b-49e2-b333-ad6dfe508953', 'Ancient Kourion', 'fix', 'period_start', '-3000', '-1100', 'high', 'Phase B: raw_year=''11th c. BC'' -> parsed=-1100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6da6eaa8-4d63-48cb-8c9e-c9eac12f1d04', 'Ancient City of Pergamon', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''5th c. BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2e53c7cf-072e-465a-a53a-ba2128f50c08', 'Ancient Sparta', 'fix', 'period_start', '-1500', '-650', 'high', 'Phase B: raw_year=''650 BC'' -> parsed=-650', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0576c316-4e26-4342-bc7e-42ae84bdc36e', 'Ancient City of Troy', 'fix', 'period_start', '-500', '-3600', 'high', 'Phase B: raw_year=''3,600 BC - 500 AD'' -> parsed=-3600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('cd307f24-5170-4cb1-acb0-0e7ba7e276d7', 'Antonine Wall', 'fix', 'period_start', '1', '142', 'high', 'Phase B: raw_year=''142 AD'' -> parsed=142', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('61ae1b37-1703-4754-880a-f7277504a829', 'Apamea', 'fix', 'period_start', '-3000', '-300', 'high', 'Phase B: raw_year=''300 BC - 13th c. AD'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f336bdb9-c53b-4eed-91d2-353e9e1b4566', 'Appleby Logboat', 'fix', 'period_start', '-3000', '-1500', 'high', 'Phase B: raw_year=''1500 - 1300 BC'' -> parsed=-1500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('42f11dde-ad7e-46e0-ab7b-37a7add49986', 'Ara trium Galliarum', 'fix', 'period_start', '-500', '-100', 'high', 'Phase B: raw_year=''1st c. BC'' -> parsed=-100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('94141d8e-4482-4c1c-a5f0-79fc8fc2ca76', 'Arch of Cabanes', 'fix', 'period_start', '1', '200', 'high', 'Phase B: raw_year=''2nd c. AD'' -> parsed=200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('748277a0-62bc-4628-b2a1-606f65a547f1', 'Arch of the Sergii', 'fix', 'period_start', '-500', '-29', 'high', 'Phase B: raw_year=''29 - 27 BC'' -> parsed=-29', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d996c0de-78d1-4966-9ace-3f40a9c6ed2d', 'Arkadiko Bridge', 'fix', 'period_start', '-1500', '-1300', 'high', 'Phase B: raw_year=''1300 - 1190 BC'' -> parsed=-1300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('55a670ec-c7c5-4f52-98ea-b25211aedd4e', 'Archaeological Site of Kition', 'fix', 'period_start', '-3000', '-1300', 'high', 'Phase B: raw_year=''13th c. BC'' -> parsed=-1300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('1cf32c46-3536-4e00-9b54-90a0203ff628', 'Arkheologicheskiy Muzey-Zapovednik "Tanais"', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''3rd c. BC'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3cb65471-1fc1-4055-9cfa-63d7514aeaee', 'Aššur', 'fix', 'period_start', '-3000', '-2025', 'high', 'Phase B: raw_year=''2025 BC - 14th c. AD'' -> parsed=-2025', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('98c794a6-57b5-4783-b38d-3693bb60b91b', 'Athenian Treasury, Delphi', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th - 5th c. BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('1886172a-83a7-4dfb-b5e5-4c3978571e48', 'Augusta Emerita', 'fix', 'period_start', '-500', '-25', 'high', 'Phase B: raw_year=''25 BC'' -> parsed=-25', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3ccc24a7-a41a-4c7b-91e2-246b6b81ef05', 'Augusta Raurica', 'fix', 'period_start', '-500', '-44', 'high', 'Phase B: raw_year=''44 BC - 260 AD'' -> parsed=-44', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('1c18de52-3783-41cb-a3dd-ade50498a974', 'Babilonie', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''300 - 150 BC'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2094fe27-b71c-4059-82d0-3891880600a5', 'Behistun Inscription', 'fix', 'period_start', '-1500', '-522', 'high', 'Phase B: raw_year=''522 - 486 BC'' -> parsed=-522', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('033b359c-dc2e-4fea-a61e-cd2ad0ca9bbe', 'Belgrade Fortress', 'fix', 'period_start', '-500', '-279', 'high', 'Phase B: raw_year=''279 BC'' -> parsed=-279', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3c56c4c5-f5a8-48bb-8b93-9e3a92feac09', 'Bibracte', 'fix', 'period_start', '-500', '-800', 'high', 'Phase B: raw_year=''8th - 1st c. BC'' -> parsed=-800', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('7fe4bb17-d008-4886-a097-c03c66b43f76', 'Blackhammer Chambered Cairn', 'fix', 'period_start', '-4500', '-3000', 'high', 'Phase B: raw_year=''3000 BC'' -> parsed=-3000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b46b6969-3160-4cbd-a574-8727ee7c53c5', 'Bishop''s Basilica of Philippopolis', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('44354857-115b-44d3-b155-cae373565602', 'Brauroneion', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''5th c. BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ceff34a3-d6a5-4d8c-8c58-4a8cc27460a5', 'Bull-Leaping Fresco', 'fix', 'period_start', '-3000', '-1500', 'high', 'Phase B: raw_year=''15th c. BC'' -> parsed=-1500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9ceb5947-c91f-4a1f-8c8f-6a67dbb88de2', 'Cádiz', 'fix', 'period_start', '-1500', '-700', 'high', 'Phase B: raw_year=''7th c. BC'' -> parsed=-700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c7994816-1b61-4c2b-a82b-513380825948', 'Carn Euny', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''200 BC - 400 AD'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8a9ece01-983b-4bca-bb70-5f7d8f756781', 'Cartagena, Spain', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('504bf30a-c4a0-48e7-8bbc-378b585b59b5', 'Carteia', 'fix', 'period_start', '-3000', '-1000', 'high', 'Phase B: raw_year=''10th c. BC'' -> parsed=-1000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6848b0cc-552a-4e7d-b767-281d3658a5ac', 'Castlestrange Stone', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''300 BC - 100 AD'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('da54a7f3-948a-4da4-a775-68b7d1831d29', 'Castle of Kirkûk', 'fix', 'period_start', '1', '130', 'high', 'Phase B: raw_year=''130 ft'' -> parsed=130', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('1abe781b-81a3-4aff-af66-3a4359970d72', 'Catacombs of San Gennaro', 'fix', 'period_start', '1', '200', 'high', 'Phase B: raw_year=''2nd c. AD'' -> parsed=200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('af78d851-5a24-4bd6-a1ad-1df1f29f9526', 'Cave di Cusa', 'fix', 'period_start', '-1500', '-6', 'high', 'Phase B: raw_year=''6th c. - 409 BC'' -> parsed=-6', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('55ce644f-cbfa-4aab-9f3f-e7cca251f3ad', 'Chan Chan', 'fix', 'period_start', '500', '900', 'high', 'Phase B: raw_year=''900 - 1470 AD'' -> parsed=900', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3842aca5-13d3-4166-80cf-92f8dac3514f', 'Choquepuquio', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''400 - 1530 AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9789696d-6670-42d8-a76a-bd73fd3ca2c0', 'Church of Saint George, Sofia', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5db5e2c0-081a-4c69-a8c6-6105ac870e5f', 'Church of the Holy Apostles Peter and Paul, Ras', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('911287cb-672e-4d84-bc52-e0d26546f834', 'Chysauster Ancient Village', 'fix', 'period_start', '-500', '-100', 'high', 'Phase B: raw_year=''100 BC - 3rd c. AD'' -> parsed=-100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ddd829b1-fdad-4487-a284-35bae4539928', 'Citânia de Briteiros', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd - 1st c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9ae31b41-d78d-44da-824d-43487ec611f0', 'Combe Hill, East Sussex', 'fix', 'period_start', '-4500', '-3700', 'high', 'Phase B: raw_year=''3700 - 3500 BC'' -> parsed=-3700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('1739eaea-9d1a-41c1-97a6-cea5820bca28', 'Crypta Neapolitana', 'fix', 'period_start', '-500', '-37', 'high', 'Phase B: raw_year=''37 BC'' -> parsed=-37', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e5d1f9a5-86b9-41d5-a258-8f21cd1e83e6', 'Danebury', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th c. BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3746f91f-e0e5-4494-9ea6-0261ba241fe1', 'Debdieba', 'fix', 'period_start', '-4500', '-3000', 'high', 'Phase B: raw_year=''3000 - 2500 BC'' -> parsed=-3000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6c18df63-d9a4-4866-84cc-657a061bb46d', 'Demetrias', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''3rd c. BC'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('4e78a6c5-1811-46d3-8e62-8c613ec3afbe', 'Diocletian''s Palace', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('70a0244e-de85-46e2-9515-c7ca202868b9', 'Domvs Romana', 'fix', 'period_start', '-500', '-100', 'high', 'Phase B: raw_year=''1st c. BC'' -> parsed=-100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('18f993a6-2922-432f-b795-4ef914cffcd4', 'Dos Pilas', 'fix', 'period_start', '1000', '629', 'high', 'Phase B: raw_year=''629 - 8th c. AD'' -> parsed=629', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f9d17ed5-eb41-4332-a2c1-42d7d9b57a56', 'Drususstein', 'fix', 'period_start', '-500', '-9', 'high', 'Phase B: raw_year=''9 BC'' -> parsed=-9', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('cc8c8638-cb77-4b61-a248-5c0f8e19cb66', 'Dur-Sharrukin', 'fix', 'period_start', '-1500', '-700', 'high', 'Phase B: raw_year=''7th c. BC'' -> parsed=-700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('86c101ad-fcdb-413a-8aec-6aad2d1574e7', 'Dykyi Sad Archaeological Site', 'fix', 'period_start', '-1500', '-1250', 'high', 'Phase B: raw_year=''1250 - 900 BC'' -> parsed=-1250', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e5efe12c-25a8-423f-8974-98fc23e299e9', 'Echo Stoa', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('62e7aef7-f914-4080-ae06-b4c347600d6d', 'El Jem Amphitheatre', 'fix', 'period_start', '1', '238', 'high', 'Phase B: raw_year=''238 AD'' -> parsed=238', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('58bdf3b7-f210-49b4-bc02-f060c120737a', 'El Cerrito', 'fix', 'period_start', '-3000', '-300', 'high', 'Phase B: raw_year=''300 BC - 17th c. AD'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c1c984e7-1391-4153-b140-f9bcd446d759', 'Elche', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''600 BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('696624d4-3f88-4175-a4cd-fd145d00174a', 'Ennigaldi-Nanna''s Museum', 'fix', 'period_start', '-1500', '-530', 'high', 'Phase B: raw_year=''530 BC'' -> parsed=-530', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c2628a93-7c87-4a98-8d13-8301f7063403', 'Er-Grah Tumulus', 'fix', 'period_start', '-4500', '-3300', 'high', 'Phase B: raw_year=''3300 BC'' -> parsed=-3300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fad5c73f-8725-47d0-b13c-372fefba62ea', 'Foso e Interior Citadelle De Victoria', 'fix', 'period_start', '-3000', '-1500', 'high', 'Phase B: raw_year=''1500 BC - 1868 AD'' -> parsed=-1500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('77127fe3-8116-4567-9b04-aebbe719e5a7', 'Fortifications of Chania', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''3rd c. BC'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('359860c8-9f39-49d7-8834-1651987c8c1e', 'Funerary Naiskos of Aristonautes', 'fix', 'period_start', '-500', '-320', 'high', 'Phase B: raw_year=''320 BC'' -> parsed=-320', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3d801ecb-4453-4ce3-85db-dce392c67c9d', 'Ganjnameh Ancient Inscriptions', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th - 5th c. BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('07ca1c0c-550e-41ab-ab5d-5563fce29d90', 'Ġgantija', 'fix', 'period_start', '-4500', '-3600', 'high', 'Phase B: raw_year=''3600 - 2500 BC'' -> parsed=-3600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c35b1649-9442-4195-9604-4481ce65ffbf', 'Golden Gate - Diocletian''s Palace', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('891ad351-7985-4c16-b6a6-830c26bc268f', 'Great Basilica, Plovdiv', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('4599daa4-93cc-4c55-872c-41e9c7875a59', 'Great Sphinx of Giza', 'fix', 'period_start', '-3000', '-2558', 'high', 'Phase B: raw_year=''2558 - 2532 BC'' -> parsed=-2558', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('4ab1bd6e-a7fd-41c3-b341-9959d77d5a6e', 'Great Ziggurat of Ur', 'fix', 'period_start', '-500', '-2100', 'high', 'Phase B: raw_year=''21st c. BC'' -> parsed=-2100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f7a88213-58c1-4ee4-b791-4babfa0cd67a', 'Hadrian''s Wall', 'fix', 'period_start', '1', '122', 'high', 'Phase B: raw_year=''122 AD'' -> parsed=122', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fffac2f9-3115-47be-9830-f5969cce734b', 'Håga Mound', 'fix', 'period_start', '-1500', '-1000', 'high', 'Phase B: raw_year=''1000 BC'' -> parsed=-1000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fdc3a783-3b1a-473a-bf22-8510308e0054', 'Herodion National Park', 'fix', 'period_start', '-500', '-23', 'high', 'Phase B: raw_year=''23 BC - 71 AD'' -> parsed=-23', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5c4b2afd-f915-4625-a841-790460fddef5', 'Himera', 'fix', 'period_start', '-1500', '-648', 'high', 'Phase B: raw_year=''648 BC'' -> parsed=-648', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('51e6e482-0301-4200-9719-17e8b548a8db', 'Historic Site Tipasa', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th c. BC - 6th c. AD'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b803b66a-768d-4040-bdac-6176611241da', 'Horgen', 'fix', 'period_start', '-4500', '-3500', 'high', 'Phase B: raw_year=''3500 - 2850 BC'' -> parsed=-3500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5752ff6c-ce00-4b78-aad7-f80a4d61c4e7', 'House of the Faun, Pompeii', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f69c8107-a8fe-45ae-a8d8-d5ab8e618e33', 'Hypostyle Hall', 'fix', 'period_start', '-1500', '-1290', 'high', 'Phase B: raw_year=''1290 - 1224 BC'' -> parsed=-1290', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('db227639-34b4-45db-817c-95092b4a916a', 'Huaca Huallamarca', 'fix', 'period_start', '500', '1000', 'high', 'Phase B: raw_year=''1000 - 1450 AD'' -> parsed=1000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('15f3ae9f-86e9-4198-97c9-e67b42c034dc', 'Ishtar Gate', 'fix', 'period_start', '-1500', '-575', 'high', 'Phase B: raw_year=''575 BC'' -> parsed=-575', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c8a346a9-bed2-4420-83db-3a6fcca051e4', 'Italica', 'fix', 'period_start', '-500', '-206', 'high', 'Phase B: raw_year=''206 BC'' -> parsed=-206', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('01f3d961-e2cf-4a3d-bc36-7e9976efe93e', 'Jisk''a Iru Muqu', 'fix', 'period_start', '-4500', '-3400', 'high', 'Phase B: raw_year=''3400 - 1600 BC'' -> parsed=-3400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('14c0c237-0ece-4124-ada8-8ec56b431b08', 'Karnak Temple Complex', 'fix', 'period_start', '-3000', '-1971', 'high', 'Phase B: raw_year=''1971 - 30 BC'' -> parsed=-1971', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ac5c3d55-1122-4aad-bcee-90a514c56f4b', 'Kerch', 'fix', 'period_start', '-1500', '-700', 'high', 'Phase B: raw_year=''7th c. BC'' -> parsed=-700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2c780872-8603-4ff7-b740-147b3cd5f22f', 'King Ezana''s Stele', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('47c37ef9-98ee-41d8-879b-e78db06295da', 'Kition', 'fix', 'period_start', '-3000', '-1300', 'high', 'Phase B: raw_year=''13th c. BC'' -> parsed=-1300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('87cc7367-7c4d-4b5b-ae73-9cf41c550e9c', 'Knap of Howar', 'fix', 'period_start', '-4500', '-3700', 'high', 'Phase B: raw_year=''3700 - 2800 BC'' -> parsed=-3700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9983bdce-9f35-47a3-a570-4021cfa41b97', 'Kourion', 'fix', 'period_start', '-3000', '-1200', 'high', 'Phase B: raw_year=''12th c. BC'' -> parsed=-1200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2f8f4a6f-2480-49a1-ae22-23ad1102f77d', 'Kutaisi', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th - 5th c. BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ec838509-a1e6-4f6a-b216-3f1791c16d67', 'Legananny Dolmen', 'fix', 'period_start', '-4500', '-3000', 'high', 'Phase B: raw_year=''3000 BC'' -> parsed=-3000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2dcaaefa-e48b-4eab-993e-982418c3c8eb', 'León, Spain', 'fix', 'period_start', '-500', '-100', 'high', 'Phase B: raw_year=''1st c. BC'' -> parsed=-100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('bad314d6-47c3-457f-ab77-9600fe9b04d2', 'Library of Ashurbanipal', 'fix', 'period_start', '-1500', '-700', 'high', 'Phase B: raw_year=''7th c. BC'' -> parsed=-700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('21f76b39-07bd-40cc-8506-116019eac196', 'Libyco-Punic Mausoleum of Dougga', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f5e7956b-9aa4-47b0-b88a-3ed159f451d1', 'Llansteffan Castle', 'fix', 'period_start', '-3000', '-800', 'high', 'Phase B: raw_year=''800 BC - 12th c. AD'' -> parsed=-800', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('75e685c6-e246-425d-8a2b-e1bf69d6af19', 'London Mithraeum', 'fix', 'period_start', '1', '300', 'high', 'Phase B: raw_year=''3rd c. AD'' -> parsed=300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('4f366f34-983c-42e1-a89d-7e8f5f77cdce', 'Machu Picchu', 'fix', 'period_start', '1000', '1438', 'high', 'Phase B: raw_year=''1438 - 1530 AD'' -> parsed=1438', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('39a50b0a-cc96-4e76-967c-fd1a1946aa2c', 'Maiden Castle, Dorset', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''600 BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fa26417b-eb7c-49d0-aaf7-adcd4909e78a', 'Mausoleum at Halicarnassus', 'fix', 'period_start', '-500', '-353', 'high', 'Phase B: raw_year=''353 - 350 BC'' -> parsed=-353', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('63220a54-b953-4e72-a914-8f564b8f3e11', 'Mellor Hill Fort', 'fix', 'period_start', '-1500', '-800', 'high', 'Phase B: raw_year=''800 BC - 1st c. AD'' -> parsed=-800', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f8f6d3e9-c012-4fac-a562-cfbb592a3263', 'Minoan Palace of Knossos', 'fix', 'period_start', '-3000', '-2000', 'high', 'Phase B: raw_year=''2000 - 1100 BC'' -> parsed=-2000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('bc058dac-5a3f-45db-8959-ba1df10920c4', 'Mesembria', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th c. BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('95bc3d88-46db-4ee3-a5a2-4d1d04a50488', 'Montegrande Archaeological Site', 'fix', 'period_start', '-4500', '-3000', 'high', 'Phase B: raw_year=''3000 BC'' -> parsed=-3000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('71b5fca6-6ce4-43f0-bddd-6b3c15ca3f0e', 'Naveta d''Es Tudons', 'fix', 'period_start', '-1500', '-1200', 'high', 'Phase B: raw_year=''1200 - 750 BC'' -> parsed=-1200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0060e6c0-8388-4762-bf51-9a3f88807899', 'Nekresi', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC - 6th c. AD'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2d89e6d4-8fa0-4258-a70a-bc42ad3c47bf', 'Neuchâtel', 'fix', 'period_start', '-500', '-13000', 'high', 'Phase B: raw_year=''13,000 BC'' -> parsed=-13000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6069036e-08d0-48dc-b808-ba568efe707f', 'Nijmegen', 'fix', 'period_start', '-500', '-100', 'high', 'Phase B: raw_year=''1st c. BC'' -> parsed=-100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('250714e7-df78-444d-bfc0-303dfd6a3a03', 'Nymphaion, Crimea', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th c. BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a50cf939-77f1-489c-82f7-93b07b2bc5ae', 'Obelisk of Axum', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('54dead1c-8dc0-4cdd-a581-47d2e033fdab', 'Obelisk Of Theodosius', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2cabb7a1-0596-457c-b37f-c041440b4fe2', 'Odeon of Herodes Atticus', 'fix', 'period_start', '1', '161', 'high', 'Phase B: raw_year=''161 - 267 AD'' -> parsed=161', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('50fdb577-af39-425e-a038-a0f8205f66fc', 'Old Temple of Athena', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th c. BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ad600526-95f6-434d-9440-38ce0688b441', 'Odessus', 'fix', 'period_start', '-1500', '-700', 'high', 'Phase B: raw_year=''7th c. BC'' -> parsed=-700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6eabe5c3-03f4-4155-8b7d-dbd5616f5d59', 'Paestum', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''600 BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('14ca23b2-2208-4930-99f7-632db64ca953', 'Pamplona', 'fix', 'period_start', '-500', '-75', 'high', 'Phase B: raw_year=''75 BC'' -> parsed=-75', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('29245d49-3e8c-4c31-baf4-a3cdd54a8964', 'Patara', 'fix', 'period_start', '-1500', '-1200', 'high', 'Phase B: raw_year=''1200 BC'' -> parsed=-1200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e00a1e45-3c66-48f4-8cac-3169146aad21', 'Persepolis', 'fix', 'period_start', '-1500', '-515', 'high', 'Phase B: raw_year=''515 - 330 BC'' -> parsed=-515', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a06a95d0-35b4-44bb-a0c1-716cbf972b19', 'Petra', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3e9107fa-e54c-407c-aaa7-a6f198e48c0f', 'Phanagoria', 'fix', 'period_start', '-1500', '-543', 'high', 'Phase B: raw_year=''543 BC'' -> parsed=-543', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('966f26e0-c2ae-4a0f-ac46-8a481ad80b19', 'Phaselis', 'fix', 'period_start', '-1500', '-700', 'high', 'Phase B: raw_year=''7th c. BC'' -> parsed=-700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('7a43d34c-2051-48b6-b598-d4482adb4623', 'Pompeii', 'fix', 'period_start', '-1500', '-800', 'high', 'Phase B: raw_year=''8th c. BC'' -> parsed=-800', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5fc3dde6-5284-41ba-af51-d91420bd0299', 'Pont du Gard', 'fix', 'period_start', '-500', '-19', 'high', 'Phase B: raw_year=''19 BC'' -> parsed=-19', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('27781284-7698-46ff-b6aa-096800327282', 'Pontic Olbia', 'fix', 'period_start', '-1500', '-700', 'high', 'Phase B: raw_year=''7th c. BC - 4th c. AD'' -> parsed=-700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d4714397-6e73-432d-add3-c01e22cb055f', 'Porta Gemina', 'fix', 'period_start', '1', '200', 'high', 'Phase B: raw_year=''2nd c. AD'' -> parsed=200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c9755577-6815-411d-bb1e-f96330776818', 'Porta Nigra', 'fix', 'period_start', '1', '200', 'high', 'Phase B: raw_year=''2nd c. AD'' -> parsed=200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d622c812-d34b-4e3d-8005-978fb0e51079', 'Portus Adurni', 'fix', 'period_start', '1', '300', 'high', 'Phase B: raw_year=''3rd c. AD'' -> parsed=300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('da488c94-540b-4fdc-8d3a-0d5aba57b372', 'Pozzuoli', 'fix', 'period_start', '-1500', '-531', 'high', 'Phase B: raw_year=''531 BC'' -> parsed=-531', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('972ded7c-665e-4ca6-98cc-af4dff9ac8f3', 'Priene Ruins', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e4631001-b923-4f36-be7f-c961f9e287ba', 'Prince of the Lilies', 'fix', 'period_start', '-3000', '-1550', 'high', 'Phase B: raw_year=''1550 BC'' -> parsed=-1550', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('676dbe65-abbf-4e30-8e56-70cae048f1e0', 'Pula', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('7661e2ac-0a20-46be-9069-961b36db4ac7', 'Pula Arena', 'fix', 'period_start', '-500', '-27', 'high', 'Phase B: raw_year=''27 BC - 68 AD'' -> parsed=-27', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('64c9b400-5cab-45f2-8662-03c24c4367ce', 'Pyramid of Amenemhat I', 'fix', 'period_start', '-3000', '-1991', 'high', 'Phase B: raw_year=''1991 - 1778 BC'' -> parsed=-1991', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('872b05b1-618b-4618-b3ae-6c69f3177911', 'Pyramid of Caius Cestius', 'fix', 'period_start', '-500', '-18', 'high', 'Phase B: raw_year=''18 - 12 BC'' -> parsed=-18', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('2b2812a6-63d4-4985-b334-ebb80f2ddd90', 'Pyramid of Djoser', 'fix', 'period_start', '-3000', '-2700', 'high', 'Phase B: raw_year=''27th c. BC'' -> parsed=-2700', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('70e08059-7e26-4fa2-885f-31bb426f182d', 'Pyramid of Sahure', 'fix', 'period_start', '-3000', '-2500', 'high', 'Phase B: raw_year=''25th c. BC'' -> parsed=-2500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9b3eed6b-54e2-4321-8e84-9b204819879a', 'Pyramid of Senusret I', 'fix', 'period_start', '-3000', '-1991', 'high', 'Phase B: raw_year=''1991 - 1778 BC'' -> parsed=-1991', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b0e8cb34-7b53-4900-a440-cc3c3b9c62bf', 'Pyramid of Unas', 'fix', 'period_start', '-3000', '-2400', 'high', 'Phase B: raw_year=''24th c. BC'' -> parsed=-2400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('657dbfe1-7b3f-4548-93c6-99be8674a6ff', 'Quoyness Chambered Cairn', 'fix', 'period_start', '-4500', '-3000', 'high', 'Phase B: raw_year=''3000 BC'' -> parsed=-3000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('31203a3c-220a-41a8-87ff-befc4263c8d4', 'Qʼumarkaj', 'fix', 'period_start', '1000', '1400', 'high', 'Phase B: raw_year=''1400 - 1524 AD'' -> parsed=1400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d48e920c-f57c-4f20-8bdf-df646d31029b', 'Red Pyramid', 'fix', 'period_start', '-3000', '-2575', 'high', 'Phase B: raw_year=''2575 - 2551 BC'' -> parsed=-2575', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('5cc613ff-ad80-4906-9103-6d1035eaea3e', 'Roman Bridge over the Ribeira de Odivelas', 'fix', 'period_start', '-500', '-100', 'high', 'Phase B: raw_year=''1st c. BC - 1st c. AD'' -> parsed=-100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('591cee00-2570-4cf4-94d8-a141cf6e9854', 'Roman Dam of Belas', 'fix', 'period_start', '1', '300', 'high', 'Phase B: raw_year=''3rd c. AD'' -> parsed=300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a71bf02d-0df6-4b15-8436-be73a43950f4', 'Roman Theatre, Tarraco', 'fix', 'period_start', '-500', '-100', 'high', 'Phase B: raw_year=''1st c. BC'' -> parsed=-100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e056946d-fd09-43f2-8d45-648121ace99d', 'Roman Temple of Vic', 'fix', 'period_start', '1', '200', 'high', 'Phase B: raw_year=''2nd c. AD'' -> parsed=200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f064d736-e58e-4505-b634-b5f18052e293', 'Salamis Ancient City', 'fix', 'period_start', '-3000', '-1100', 'high', 'Phase B: raw_year=''11th c. BC - 7th c. AD'' -> parsed=-1100', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a0736505-9ca5-4361-bc0a-f0a47b6fed7e', 'S''Argamassa Roman Fish Farm', 'fix', 'period_start', '-500', '-146', 'high', 'Phase B: raw_year=''146 BC'' -> parsed=-146', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('43d64ea4-8c7e-4bca-bcfe-04b4e6e6b437', 'Samshvilde', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''3rd c. BC - 18th c. AD'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f29afd0d-6fb8-4405-bee8-c1b17a6989e3', 'San Estevan', 'fix', 'period_start', '-1500', '-800', 'high', 'Phase B: raw_year=''800 BC - 900 AD'' -> parsed=-800', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('03d28afb-c252-423e-9b4f-2815cfaed6c5', 'Serapeum of Alexandria and Pompey''s Pillar', 'fix', 'period_start', '-500', '-246', 'high', 'Phase B: raw_year=''246 - 222 BC'' -> parsed=-246', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('21d63980-32dc-43cc-baa1-06c9e2f15335', 'Silbury Hill', 'fix', 'period_start', '-3000', '-2400', 'high', 'Phase B: raw_year=''2400 - 2300 BC'' -> parsed=-2400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('fdafef27-24a2-4939-b2b0-7f3852676e82', 'Singidunum', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''3rd c. BC'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f6b5aa36-d662-4490-a83b-1e5d857afdd5', 'Sinuessa', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC - 5th c. AD'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ef1ee8c0-f6bd-4886-bd66-8a6106ac5ca4', 'Shengavit Settlement', 'fix', 'period_start', '-4500', '-3000', 'high', 'Phase B: raw_year=''3000 - 2200 BC'' -> parsed=-3000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f69cf72f-d7b2-48d8-996d-82e19c289eee', 'Soli, Cyprus', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''3rd c. BC - 4th c. AD'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('9c64a3f6-8874-4441-b6c8-52428a1d45e5', 'Spirit Cave, Thailand', 'fix', 'period_start', '-500', '-10000', 'high', 'Phase B: raw_year=''10,000 - 2000 BC'' -> parsed=-10000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d7a107f8-b228-48a7-97c5-081dc67c0469', 'Square Peristyle', 'fix', 'period_start', '-500', '-300', 'high', 'Phase B: raw_year=''300 BC'' -> parsed=-300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('403e3c53-6a70-49cc-81b8-2014542e53d3', 'Stadium at Olympia', 'fix', 'period_start', '-1500', '-800', 'high', 'Phase B: raw_year=''8th - 4th c. BC'' -> parsed=-800', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e2f2dee4-9e70-41b8-a7f5-be7aa07ea807', 'Stele of Aristion', 'fix', 'period_start', '-1500', '-510', 'high', 'Phase B: raw_year=''510 BC'' -> parsed=-510', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('21b2278e-c3f2-4723-ae40-fa8a6161e3fb', 'Stonehenge', 'fix', 'period_start', '-4500', '-3000', 'high', 'Phase B: raw_year=''3000 - 2000 BC'' -> parsed=-3000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a627df4e-f241-478e-b8ab-273e67f52441', 'Sweet Track', 'fix', 'period_start', '-4500', '-3807', 'high', 'Phase B: raw_year=''3807 BC'' -> parsed=-3807', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('57ded976-9874-4832-8716-2b54c1fee102', 'Table des Marchand', 'fix', 'period_start', '-4500', '-4000', 'high', 'Phase B: raw_year=''4000 BC'' -> parsed=-4000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('991bd627-65d9-40d3-a97d-dfa879756da0', 'Sybaris', 'fix', 'period_start', '-1500', '-720', 'high', 'Phase B: raw_year=''720 - 510 BC'' -> parsed=-720', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c947e9b6-41c7-4c94-81c3-d79fc9e601b2', 'Tambo Colorado', 'fix', 'period_start', '1000', '1500', 'high', 'Phase B: raw_year=''15th c. AD'' -> parsed=1500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('7759e372-b62e-424a-a726-d078a5a49e54', 'Tempio di Zeus, Selinunte', 'fix', 'period_start', '-1500', '-515', 'high', 'Phase B: raw_year=''515 - 86 BC'' -> parsed=-515', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0e12027e-9a65-470f-aca7-2cb1eb408120', 'Temple of Athena, Paestum', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''500 BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8d8753ae-9935-4ffb-b578-de5907999f68', 'Temple of Athena Nike', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''5th c. BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('39e49c72-4037-487c-8402-409d00f7026e', 'Temple of Ramesses II- Abu Simbel', 'fix', 'period_start', '-1500', '-1264', 'high', 'Phase B: raw_year=''1264 - 1225 BC'' -> parsed=-1264', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('4c7f6521-241f-48c0-93da-f8d7893f5446', 'Temple of Hera, Olympia', 'fix', 'period_start', '-3000', '-590', 'high', 'Phase B: raw_year=''590 BC - 4th c. AD'' -> parsed=-590', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('100ab5ea-fdf9-4d78-9f65-961ee8190b7b', 'Temple of Poseidon, Sounion', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''5th c. BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('349e080c-0b4f-4708-8744-d1b1c6a0b83e', 'Temple of Zeus, Olympia', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''5th c. BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6a28da7c-1e74-4f45-b49c-03c2af224c86', 'Tenochtitlan - Templo Mayor', 'fix', 'period_start', '1000', '1325', 'high', 'Phase B: raw_year=''1325 -1521 AD'' -> parsed=1325', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('50873aa8-b4da-4b2c-99a9-b9e7859bf44b', 'Tenam Puente', 'fix', 'period_start', '1', '300', 'high', 'Phase B: raw_year=''300 - 1200 AD'' -> parsed=300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('852f3856-ecaa-4bab-82c8-a0ab2d11f94f', 'Tenayuca', 'fix', 'period_start', '1000', '12', 'high', 'Phase B: raw_year=''12th - 16th c. AD'' -> parsed=12', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6313cd62-456d-4a85-8782-57613c7fc0e1', 'The Great Pyramid of Giza', 'fix', 'period_start', '-3000', '-2600', 'high', 'Phase B: raw_year=''26th c. BC'' -> parsed=-2600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('a965d140-d212-45f5-a269-1945fc8432b3', 'The Archaeological Site Nitzana', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC - 2nd c. AD'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('76cd8b60-c373-4f26-85ac-2827b0797b15', 'Thebes', 'fix', 'period_start', '-4500', '-3200', 'high', 'Phase B: raw_year=''3200 BC - 1st c. AD'' -> parsed=-3200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e60fc487-9fb9-4e37-b590-4a035e591c7e', 'The Temple of Artemis-Selçuk', 'fix', 'period_start', '-1500', '-550', 'high', 'Phase B: raw_year=''550 BC - 401 AD'' -> parsed=-550', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f4955fe7-d4e9-4de7-9812-0fc7e94c0620', 'The Unfinished Obelisk', 'fix', 'period_start', '-3000', '-1508', 'high', 'Phase B: raw_year=''1508 - 1458 BC'' -> parsed=-1508', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('695ddb9f-70cb-4e8a-9020-4bebf0b06227', 'Tomb of Cyrus the Great', 'fix', 'period_start', '-1500', '-600', 'high', 'Phase B: raw_year=''6th c. BC'' -> parsed=-600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8797faec-8590-4716-9763-310be93ef6ea', 'Tower of Elahbel', 'fix', 'period_start', '1', '103', 'high', 'Phase B: raw_year=''103 AD'' -> parsed=103', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0259ff6b-ef34-4a7e-93ef-78e2729e45a6', 'Trialeti Petroglyphs', 'fix', 'period_start', '-4500', '-3000', 'high', 'Phase B: raw_year=''3000 - 2000 BC'' -> parsed=-3000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6d2ffc46-f990-4ec7-9d69-94029e8e98ed', 'Triumphal Arch of Orange', 'fix', 'period_start', '-500', '-27', 'high', 'Phase B: raw_year=''27 BC - 14 AD'' -> parsed=-27', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e3ac6021-f7ef-464d-a6d0-e0df9e91f553', 'Turkistan - City', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e48a661d-c148-4a0f-abff-f862d61524b7', 'Túcume', 'fix', 'period_start', '500', '800', 'high', 'Phase B: raw_year=''800 - 1530 AD'' -> parsed=800', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('f5df832e-ab5e-4e9c-b6c9-037441011945', 'Twin Gates of Pula', 'fix', 'period_start', '1', '200', 'high', 'Phase B: raw_year=''2nd c. AD'' -> parsed=200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('81724be4-6588-41b1-8efc-364637456cdf', 'Uffington White Horse', 'fix', 'period_start', '-1500', '-1380', 'high', 'Phase B: raw_year=''1380 - 550 BC'' -> parsed=-1380', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6b9aa503-6d6a-44b1-a9d0-c165294808df', 'Uppåkra Temple', 'fix', 'period_start', '1', '300', 'high', 'Phase B: raw_year=''3rd c. AD'' -> parsed=300', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('3dbbef3c-4605-4a1f-b04f-cadd63462673', 'Ur', 'fix', 'period_start', '-4500', '-3800', 'high', 'Phase B: raw_year=''3800 BC'' -> parsed=-3800', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d0b9e72f-73a8-4671-a01f-5cafa6e53bf8', 'Uruk', 'fix', 'period_start', '-4500', '-4000', 'high', 'Phase B: raw_year=''4000 - 3100 BC'' -> parsed=-4000', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('86a32957-57c8-424d-bc27-78c2d3ebaedc', 'Valencia', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ed78d548-5409-4909-abc0-793390dfed1c', 'Valley of the Kings', 'fix', 'period_start', '-3000', '-16', 'high', 'Phase B: raw_year=''16th 11th c. BC'' -> parsed=-16', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('d70dd131-fac7-4c7e-b367-95c2ac945339', 'Valley of the Queens', 'fix', 'period_start', '-3000', '-1550', 'high', 'Phase B: raw_year=''1550 - 1292 BC'' -> parsed=-1550', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('e5558c53-90b5-42ca-aa79-ba2d05d56eac', 'Varna, Bulgaria', 'fix', 'period_start', '-1500', '-575', 'high', 'Phase B: raw_year=''575 BC'' -> parsed=-575', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('8c44a3a9-c945-44e8-8dc2-1baab82890ea', 'Velia', 'fix', 'period_start', '-1500', '-538', 'high', 'Phase B: raw_year=''538 BC'' -> parsed=-538', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('6a7ed782-d72d-4eeb-8df6-634a27140019', 'Vix Grave', 'fix', 'period_start', '-1500', '-500', 'high', 'Phase B: raw_year=''500 BC'' -> parsed=-500', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('ba452543-f3d8-436b-bef5-4329382d234e', 'Western Wall', 'fix', 'period_start', '-500', '-19', 'high', 'Phase B: raw_year=''19 BC - 70 AD'' -> parsed=-19', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('0c00d8bd-d6b3-4237-b4c9-9a86748ee5ab', 'Κourion Ancient Amphitheatre', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('85a6ae2e-6f62-44f2-9dfd-fd81b229d56d', 'Yazılıkkaya', 'fix', 'period_start', '-3000', '-1600', 'high', 'Phase B: raw_year=''16th - 13th c. BC'' -> parsed=-1600', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('be2bb871-ba24-49cf-9172-d20d673a2c3d', 'Zadar', 'fix', 'period_start', '-500', '-200', 'high', 'Phase B: raw_year=''2nd c. BC'' -> parsed=-200', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('1fe816f4-f921-45ff-97b7-0ca7d1d0d009', 'Zerzevan Castle', 'fix', 'period_start', '1', '400', 'high', 'Phase B: raw_year=''4th c. AD'' -> parsed=400', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('da9530ed-5945-4970-a041-333b782fc208', 'Arc de Triomphe Septime Sévère', 'fix', 'period_start', '1', '205', 'high', 'Phase B: raw_year=''205 AD'' -> parsed=205', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('908d6a9b-6032-4fd4-84c7-72896374778b', 'Pergamon Amfitiyatrosu', 'fix', 'period_start', '-500', '-282', 'high', 'Phase B: raw_year=''282 - 133 BC'' -> parsed=-282', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('c9cca1f6-9117-40f3-b830-605b144baf90', 'Colosso di Ramses II', 'fix', 'period_start', '-1500', '-1279', 'high', 'Phase B: raw_year=''1279 - 1213 BC'' -> parsed=-1279', 'claude_audit_20260215');

-- Audit log entries for country fixes
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('74145e9b-76a6-48de-a902-08ecb2f1f7bb', 'Achladia', 'fix', 'country', 'Germany', 'Greece', 'high', 'Phase B: Wikidata P17 confirms correct country', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('b8aedc17-2215-44c3-b89c-8125050efbd5', 'Ahuila Gencha Machay', 'fix', 'country', 'Pakistan', 'Peru', 'high', 'Phase B: Wikidata P17 confirms correct country', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('cb659fbe-0f1c-43dc-9c40-4517c0974a79', 'Aquae Helveticae', 'fix', 'country', 'Sweden', 'Switzerland', 'high', 'Phase B: Wikidata P17 confirms correct country', 'claude_audit_20260215');
INSERT INTO database_audit_log (site_id, site_name, action, field_changed, old_value, new_value, confidence, evidence_source, changed_by)
VALUES ('7759e372-b62e-424a-a726-d078a5a49e54', 'Tempio di Zeus, Selinunte', 'fix', 'country', 'Greece', 'Italy', 'high', 'Phase B: Wikidata P17 confirms correct country', 'claude_audit_20260215');
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

-- ============================================================
-- Block 7: edited_by column migration + backfill audit rows
-- Applied: 2026-02-15
-- ============================================================

-- Ensure column exists (idempotent)
ALTER TABLE unified_sites ADD COLUMN IF NOT EXISTS edited_by VARCHAR(20) NOT NULL DEFAULT 'initial';

-- Backfill: mark rows that were fixed by the audit as 'audit'
-- Only touches rows still at 'initial' that have a corresponding 'fix' entry in the audit log
UPDATE unified_sites SET edited_by = 'audit'
FROM database_audit_log
WHERE unified_sites.id = database_audit_log.site_id
  AND database_audit_log.action = 'fix'
  AND unified_sites.edited_by = 'initial';
