-- Database Audit Fixes — Full audit of ancient_nerds (5,005 sites)
-- Generated 2026-02-14, updated 2026-02-15
-- Total: 556 fixes across 9 blocks
--   Blocks 1-7: 40 fixes (8 type, 28 period, 3 suspicious-date, 3 medium-confidence, 1 country)
--   Block 8: 128 fixes (raw_year field parsing → period_start/period_name)
--   Block 9: 259 fixes (web research → period_start/period_name)
--   42 sites flagged MANUAL (see end of file)
-- All sites are source_id = 'ancient_nerds'

BEGIN;

-- ============================================================
-- BLOCK 1: Type fixes (8 sites with unknown → correct type)
-- ============================================================

-- Acidava: Roman fort/settlement in Romania — Wikidata says Q839954 (archaeological site)
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '768e341f-d9fa-4a3c-a4bf-27d099d7f6da';

-- Archaeological Site of Plataea: ancient Greek city — Wikidata says Q515 (city)
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '23eac293-7958-4250-9f63-5b9fc8493cee';

-- Deva Victrix: Roman legionary fortress in Chester — Wikidata says Q519 (military installation)
UPDATE unified_sites SET site_type = 'Fortification'
WHERE id = '990741ec-f247-483a-8b8e-29f634e63f96';

-- Battle at the Harzhorn: 3rd century Roman–Germanic battlefield
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = 'aed60d2e-9dec-442b-a7bf-86647aca27b9';

-- Boleigh Fogou: Iron Age underground passage in Cornwall
UPDATE unified_sites SET site_type = 'Infrastructure'
WHERE id = '55231dfd-fc7a-4bdf-a490-7ee5de43e975';

-- Cartagena, Spain: ancient Carthaginian/Roman city
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '8a9ece01-983b-4bca-bb70-5f7d8f756781';

-- Apazzu: megalithic site in Corsica
UPDATE unified_sites SET site_type = 'Megalithic'
WHERE id = '01cdc8e2-56b7-4c9d-b6d0-68c290a65e55';

-- Cave of the Guanches: archaeological cave site in Tenerife
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = '4a87bc78-0813-4110-aa1e-3818326bee00';

-- ============================================================
-- BLOCK 2: Modern period fixes (28 sites with missing period)
-- All have raw_year indicating post-1500 construction/founding
-- ============================================================

-- Al-Ukhaydir (1531)
UPDATE unified_sites SET period_start = 1531, period_name = '1500+ AD'
WHERE id = '81b6f634-82df-4276-90a4-4ed1030cf4c7';

-- Attock Fort (1580)
UPDATE unified_sites SET period_start = 1580, period_name = '1500+ AD'
WHERE id = 'cf7e7df8-8987-4989-9fd5-d506d1844669';

-- Brean Down Fort (1864)
UPDATE unified_sites SET period_start = 1864, period_name = '1500+ AD'
WHERE id = '6724235d-289c-411b-9b85-ac18229a0212';

-- Delphi Archaeological Museum (1903)
UPDATE unified_sites SET period_start = 1903, period_name = '1500+ AD'
WHERE id = '660f8d4f-9fbd-43ea-8431-18c9327e81ea';

-- Forte da Graça (1763)
UPDATE unified_sites SET period_start = 1763, period_name = '1500+ AD'
WHERE id = '46bceb53-3c23-41a6-9659-b7a67035197a';

-- Grenoble Archaeological Museum (1846)
UPDATE unified_sites SET period_start = 1846, period_name = '1500+ AD'
WHERE id = '52bd1b99-5377-4a93-903d-cf99738b9926';

-- Jadar Museum (1984)
UPDATE unified_sites SET period_start = 1984, period_name = '1500+ AD'
WHERE id = 'e93e16aa-f555-4ad7-8ede-d8120fdf29a1';

-- Jaffa Gate (1538)
UPDATE unified_sites SET period_start = 1538, period_name = '1500+ AD'
WHERE id = 'c932b4f9-283e-4756-b9aa-cc5491aaddf8';

-- Jamrud Fort (1836)
UPDATE unified_sites SET period_start = 1836, period_name = '1500+ AD'
WHERE id = '8a42154e-7081-481f-ad77-49e7a02b2c98';

-- Kagoshima Castle (1601)
UPDATE unified_sites SET period_start = 1601, period_name = '1500+ AD'
WHERE id = '6791baaf-bb36-462b-a497-e704e23251ac';

-- Kharakhorum Museum (2007)
UPDATE unified_sites SET period_start = 2007, period_name = '1500+ AD'
WHERE id = 'ff1c4702-9115-43fc-b64f-15a9729bc6d9';

-- Koe Thaung Pagoda (1554)
UPDATE unified_sites SET period_start = 1554, period_name = '1500+ AD'
WHERE id = 'e514dc13-8bd1-443b-8137-94ff173d32b8';

-- Manora Fort (1797)
UPDATE unified_sites SET period_start = 1797, period_name = '1500+ AD'
WHERE id = '2dfb1bee-9ec5-4eb6-b8b7-cfedbcb09744';

-- Midford Castle (1775)
UPDATE unified_sites SET period_start = 1775, period_name = '1500+ AD'
WHERE id = '32429f3c-6e14-4015-900a-a9cd9fbb81eb';

-- Montjuïc Castle (1641)
UPDATE unified_sites SET period_start = 1641, period_name = '1500+ AD'
WHERE id = 'ed05c23a-973b-4d69-923c-b2e7b1b97305';

-- Museo Nacional de Antropología (1964)
UPDATE unified_sites SET period_start = 1964, period_name = '1500+ AD'
WHERE id = '7b061e76-f20f-447d-9650-c334492b86dc';

-- Naegi Castle (1532)
UPDATE unified_sites SET period_start = 1532, period_name = '1500+ AD'
WHERE id = '35e015d9-6ab6-4763-9873-0ff2560b9b91';

-- Naukot Fort (1810)
UPDATE unified_sites SET period_start = 1810, period_name = '1500+ AD'
WHERE id = 'bc10d0af-75ab-4c01-8b2c-a00327d0bb80';

-- Olsborg Castle (1502)
UPDATE unified_sites SET period_start = 1502, period_name = '1500+ AD'
WHERE id = 'f9ad013b-8208-4a02-8480-7c865c7577f6';

-- Osaka Castle (1583)
UPDATE unified_sites SET period_start = 1583, period_name = '1500+ AD'
WHERE id = 'a3fdb1d8-083b-4e8f-a170-5b98638d5b53';

-- Ostrowiec Świętokrzyski (1597)
UPDATE unified_sites SET period_start = 1597, period_name = '1500+ AD'
WHERE id = '1a3eff28-12e9-441c-9e4d-ae763e52b867';

-- Parque Museo La Venta (1958)
UPDATE unified_sites SET period_start = 1958, period_name = '1500+ AD'
WHERE id = 'fbd85388-fa8e-4136-be64-6ca2612effac';

-- Pfahlbaumuseum Unteruhldingen (1922)
UPDATE unified_sites SET period_start = 1922, period_name = '1500+ AD'
WHERE id = 'ef91e19e-db13-4475-b6a8-feb6f3298146';

-- The Salisbury Museum (1860)
UPDATE unified_sites SET period_start = 1860, period_name = '1500+ AD'
WHERE id = '18253743-256d-497f-be7b-6a7400d33593';

-- Tomb of Jahangir (1627)
UPDATE unified_sites SET period_start = 1627, period_name = '1500+ AD'
WHERE id = '50e5e380-1f89-4fa3-88de-e6ad35241316';

-- Xhamia e Plumbit (1733)
UPDATE unified_sites SET period_start = 1733, period_name = '1500+ AD'
WHERE id = 'e284429d-db64-478d-becd-20faf2a1b847';

-- Landguard Fort (1540)
UPDATE unified_sites SET period_start = 1540, period_name = '1500+ AD'
WHERE id = '39f7cab4-e0d9-4c15-a4a0-8fccd461ba3b';

-- Yenikale Ruins (1699) — also gets period fix
UPDATE unified_sites SET period_start = 1699, period_name = '1500+ AD'
WHERE id = 'd6d44645-a99b-4826-85b3-eb0123faadd2';

-- ============================================================
-- BLOCK 3: Suspicious date corrections (3 high-confidence)
-- ============================================================

-- Krapina Neanderthal Site: DB had museum year, actual site is ~130,000 BCE
UPDATE unified_sites SET period_start = -128000, period_name = '< 4500 BC'
WHERE id = 'c80bf1e4-215a-440d-9e2e-848c40348037';

-- Pont del Diable (Tarragona): Roman aqueduct, ~27 BC
UPDATE unified_sites SET period_start = -10, period_name = '500 BC - 1 AD'
WHERE id = '8dec4979-434b-46dd-9468-f829d6d1e713';

-- Overton Down: 1960s experimental archaeology earthwork
UPDATE unified_sites SET period_start = 1960, period_name = '1500+ AD'
WHERE id = '414416be-0a81-45f7-a572-216f39ee6a0d';

-- ============================================================
-- BLOCK 4: Medium confidence period fixes (3 sites)
-- ============================================================

-- Salapia: ancient Daunian/Roman settlement, ~900 BCE
UPDATE unified_sites SET period_start = -900, period_name = '1500 - 500 BC'
WHERE id = '0d141532-586a-4a6f-bfa0-78186786402e';

-- Blythe Intaglios: Native American geoglyphs, ~550 CE
UPDATE unified_sites SET period_start = 550, period_name = '500 - 1000 AD'
WHERE id = '1b69bb27-aebb-4675-8ee0-e9d6007a4cee';

-- Baumann's Cave: Paleolithic site, ~50,000 BCE
UPDATE unified_sites SET period_start = -50000, period_name = '< 4500 BC'
WHERE id = 'b3f7a897-e4b1-4c2f-b7fd-c91efd9523ae';

-- ============================================================
-- BLOCK 5: Country fix (1 site)
-- ============================================================

-- Yenikale: fortress in Kerch, Crimea — historically Ottoman, now Ukraine
UPDATE unified_sites SET country = 'Ukraine'
WHERE id = 'd6d44645-a99b-4826-85b3-eb0123faadd2';

-- ============================================================
-- BLOCK 6: Parse-failure fix (1 site)
-- ============================================================

-- Devil's Arrows: raw_year "3500 B C" failed to parse (space in "B C")
UPDATE unified_sites SET period_start = -3500, period_name = '4500 - 3000 BC'
WHERE name = 'Devil''s Arrows' AND source_id = 'ancient_nerds';

-- ============================================================
-- BLOCK 7: Type fixes — 64 unknown-type ancient_nerds sites
-- Full audit session 2026-02-14
-- ============================================================

-- === Tomb (2) ===
-- Agri Bavnehøj: Bronze Age burial mound in Denmark (raw_data: "Mound/tumulus")
UPDATE unified_sites SET site_type = 'Tomb'
WHERE id = '94776f9f-ea10-4b05-87bd-fd30c2cbdf6f';

-- Tivulaghju: Megalithic burial cists in Porto-Vecchio, Corsica
UPDATE unified_sites SET site_type = 'Tomb'
WHERE id = 'e3c407dd-513d-4344-8155-7bcc5db65b54';

-- === Megalithic (4) ===
-- Dolmen of Guadalperal: 4th millennium BC dolmen in Spain (raw_data: "Dolmen, Megalithic structures")
UPDATE unified_sites SET site_type = 'Megalithic'
WHERE id = 'adaf3933-e799-422f-92a4-29462e57df50';

-- Cardiccia: Largest dolmen in Corsica (5.6m long)
UPDATE unified_sites SET site_type = 'Megalithic'
WHERE id = 'ffb35fc7-24f7-4722-8036-e4173ac6d8e6';

-- Cauria: Menhir alignments (I Stantari, Renaghju) + Fontanaccia dolmen, Corsica
UPDATE unified_sites SET site_type = 'Megalithic'
WHERE id = '90ec5b47-7488-4bb4-8c4d-1259d30ac328';

-- Paddaghju (Palaghju): 258 standing stones, largest menhir collection in Mediterranean
UPDATE unified_sites SET site_type = 'Megalithic'
WHERE id = '4f5d500f-4c00-48a8-a048-6a3deb43f76a';

-- === Fortification (6) ===
-- Araghju (Castellu d'Araghju): Torrean fortified complex with cyclopean walls, Corsica
UPDATE unified_sites SET site_type = 'Fortification'
WHERE id = '576eeca0-250a-4d38-8524-aaf67bde36d6';

-- Ceccia: Torre de Ceccia — Torrean monument, Corsica
UPDATE unified_sites SET site_type = 'Fortification'
WHERE id = '9ffa8a42-7b0a-4cd3-8b4f-5cb16c916a97';

-- Oldbury Camp: Iron Age hillfort (raw_data: "Fortress/citadel, Earthwork")
UPDATE unified_sites SET site_type = 'Fortification'
WHERE id = 'a2b988c2-368a-44ac-a95b-32d73d74a116';

-- Belören Kalesi: Castle/fortification in Turkey
UPDATE unified_sites SET site_type = 'Fortification'
WHERE id = 'e8fea646-0b0c-466c-913a-9a99c7dd786d';

-- Dumat al-Jandal Wall: Ancient defensive wall in Saudi Arabia
UPDATE unified_sites SET site_type = 'Fortification'
WHERE id = '08886555-0ddd-40e1-bfe7-0322a41079ea';

-- Fectio: Roman fort (castellum) in Netherlands
UPDATE unified_sites SET site_type = 'Fortification'
WHERE id = 'f28a2d38-f5a9-49f2-83c8-53bb4c61cae4';

-- === Settlement (19) ===
-- Barton-le-Clay: Settlement (raw_data: "City/town/settlement, Fortress/citadel, Earthwork")
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '4e240612-152f-48a1-aee8-59dd9027a990';

-- Kirkby Thore: Roman settlement (raw_data: "City/town/settlement")
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = 'b3180c5d-77b8-4144-a69c-8503ce6c06f4';

-- Markiani: Fortified settlement on Amorgos (raw_data: "City/town/settlement, Fortress/citadel")
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '975e371e-6ada-4865-97f0-320c94ea8803';

-- Nichoria: Mycenaean settlement in Messenia (raw_data: multi-type, primary = settlement)
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '2d28d660-358d-4f4b-a99c-57d5b7395bc4';

-- Pozzuoli (Puteoli): Ancient Roman port city (raw_data: multi-type, primary = settlement)
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = 'da488c94-540b-4fdc-8d3a-0d5aba57b372';

-- Pucará, Puno: Pre-Inca settlement (raw_data: "City/town/settlement")
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = 'f921cb05-ab49-4bc9-b9a0-3dae48ee3e5a';

-- Roca Archaeological Site: Bronze Age settlement (raw_data: "City/town/settlement, Temple complex")
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = 'ee091b60-f72c-4e85-be61-baa970aa0630';

-- Teanum Apulum: Ancient Daunian/Roman city (raw_data: "City/town/settlement")
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = 'ce4058e7-7631-40ad-beb1-188e3cd27232';

-- Casteddu di Puzzonu: Late Bronze Age settlement, Corsica
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '86383b38-f1a1-4f04-9b7e-8a49c3495829';

-- Currachjaghju: Neolithic rock shelter habitation, Corsica (7th millennium BCE)
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '09b07712-628c-4c14-bf87-62c586f1ced3';

-- Monte Lazzu: Neolithic farming settlement, Corsica
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '000da27c-0797-4e58-a979-ae97b3d5016f';

-- Presa-Tusiu: Middle Neolithic settlement (5000-4000 BC), Corsica
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = 'cb688193-2ff5-4535-b1a7-af488587a451';

-- Pughjaredda: Late Neolithic settlement (4000-3000 BC), Corsica
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '2b3667ad-f83a-4514-8ef9-62231a454215';

-- Chaa Creek: Maya archaeological sites in Belize
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '89bdbe2c-a19b-484d-b6ef-2ed464b1311b';

-- Kraku Lu Jordan: Roman mining settlement in Serbia
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '3a5d5834-888a-458f-8a4b-66c709340688';

-- La Corona: Maya city in Guatemala
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '1010b3bf-a7d5-4e2c-9f70-8212a2cd1699';

-- Mamshit National Park (Mampsis): Nabataean city in Negev
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '94fd509a-71e9-4a1e-b235-4eb91b1cacca';

-- Shaduppum: Ancient Mesopotamian city (Tell Harmal)
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = 'f967e3c4-fc5b-4cd0-91d1-06030d51e31c';

-- Tell Maghzaliyah: Neolithic settlement in Iraq
UPDATE unified_sites SET site_type = 'Settlement'
WHERE id = '0608f0dc-4dd4-420e-ad27-ea59fe561212';

-- === Temple (2) ===
-- Kalapodi: Temple complex (raw_data: "Temple complex, City/town/settlement")
UPDATE unified_sites SET site_type = 'Temple'
WHERE id = 'cc5d001f-1ebf-44b8-a478-bfb78ec2d8d8';

-- Temple of Athena Pronaia: Temple at Delphi (raw_data: "Temple complex")
UPDATE unified_sites SET site_type = 'Temple'
WHERE id = '83822807-fe8c-4ca5-946e-17c5e7c5cf25';

-- === Theatre (1) ===
-- Babylonian Theatre: Theatre in ancient Babylon
UPDATE unified_sites SET site_type = 'Theatre'
WHERE id = '03f33939-7a7b-49f1-8ed1-99fb54897ae6';

-- === Infrastructure (7) ===
-- Antik Barajı: Roman dam at Orukaya, Turkey
UPDATE unified_sites SET site_type = 'Infrastructure'
WHERE id = '6e1bc7d5-624c-41c8-b69b-e64917ae5164';

-- Kyaneai Tarihi Sarnıç: Ancient cistern at Kyaneai, Turkey
UPDATE unified_sites SET site_type = 'Infrastructure'
WHERE id = '036346d9-313c-4fcd-9649-1aaba368e72e';

-- Great Bath: Mohenjo-daro bathing complex
UPDATE unified_sites SET site_type = 'Infrastructure'
WHERE id = '378fe0dc-2d2d-4d91-abcf-4955b7c45230';

-- Halliggye Fogou: Iron Age underground passage, Cornwall (same type as Boleigh Fogou)
UPDATE unified_sites SET site_type = 'Infrastructure'
WHERE id = '569f53de-6821-4597-b4f3-f695504b9d60';

-- Pendeen Vau: Iron Age fogou, Cornwall (same type as Boleigh Fogou)
UPDATE unified_sites SET site_type = 'Infrastructure'
WHERE id = 'bdd568d3-3a54-442a-9f8c-af7ac07bbaf0';

-- Lefke Gate: Roman gate in Iznik (Nicaea), Turkey
UPDATE unified_sites SET site_type = 'Infrastructure'
WHERE id = '5f745388-3793-459b-b55f-90dbb5bfed78';

-- Roman Nymphaeum Amman: Roman public fountain in Amman, Jordan
UPDATE unified_sites SET site_type = 'Infrastructure'
WHERE id = '67afbdc6-2f22-4678-88aa-df76baf9f7ea';

-- === Monument (7) ===
-- Tower of Hercules: Roman lighthouse in Spain (raw_data: "Minaret/tower")
UPDATE unified_sites SET site_type = 'Monument'
WHERE id = 'd36d9012-fba6-40fc-9f0d-ff865ef0f2a4';

-- Al Diwan: Nabataean rock-carved triclinium at Hegra
UPDATE unified_sites SET site_type = 'Monument'
WHERE id = '95af4ca2-80d9-4b18-81d9-05c8477213cb';

-- Bhagwan Bharat's Statue: Monumental Jain statue
UPDATE unified_sites SET site_type = 'Monument'
WHERE id = '59267588-ef6b-40b7-9990-c93b2b6d08f4';

-- Midas Monument (Yazilikaya): 7th c. BC Phrygian rock-cut facade
UPDATE unified_sites SET site_type = 'Monument'
WHERE id = '2ca81ca5-16b2-4bc5-ac27-d23549309bc8';

-- Mine Howe: Iron Age subterranean ritual structure, Orkney
UPDATE unified_sites SET site_type = 'Monument'
WHERE id = 'ba633252-4119-4f23-b1b7-6bfb3f86f2fc';

-- Sakafune-ishi Ruins: 7th century monumental stone structure, Nara, Japan
UPDATE unified_sites SET site_type = 'Monument'
WHERE id = 'fc029995-b6bb-4375-a5fa-9a0eb7d0fa85';

-- Library of Ashurbanipal: Famous ancient library in Nineveh
UPDATE unified_sites SET site_type = 'Monument'
WHERE id = 'bad314d6-47c3-457f-ab77-9600fe9b04d2';

-- === Inscription (2) ===
-- Cascajal Block: Oldest known Mesoamerican writing (Olmec)
UPDATE unified_sites SET site_type = 'Inscription'
WHERE id = '08f54fa9-0ca0-490c-82af-47fdd0a40e6b';

-- Lukyanus Kitabesi: Roman-period Greek inscription + horse-rider relief
UPDATE unified_sites SET site_type = 'Inscription'
WHERE id = '7de8d13e-49dd-42ca-a5cf-9e8fc614fbd7';

-- === Rock Art (2) ===
-- Ñusta Hispana: Inca rock relief/carving (raw_data: "Rock relief/carving")
UPDATE unified_sites SET site_type = 'Rock Art'
WHERE id = 'dafc7527-c6c8-45c3-8c7d-4813d20a4dcf';

-- Prehistoric Rock Art Sites in Côa Valley and Siega Verde (raw_data: "Rock art, Petroglyphs")
UPDATE unified_sites SET site_type = 'Rock Art'
WHERE id = '74ef6000-7bfa-4e7c-a745-b29b55f35030';

-- === Ruin (1) ===
-- Kobba Bent el Rey: Roman underground residential structure in Carthage
UPDATE unified_sites SET site_type = 'Ruin'
WHERE id = '3d790ba4-199b-4b94-b834-531db02eb066';

-- === Archaeological Site (10) ===
-- A Figa: Prehistoric site in Corsica (limited documentation)
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = 'fe4edbed-be84-4b80-b5de-62ab3e4c88ef';

-- al-Siq: Natural canyon entrance to Petra with carved niches and water channels
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = '22aa305a-3ecf-454e-a643-3e08dbbd2e14';

-- Gritulu: Prehistoric site in Corsica (limited documentation)
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = '20f1479a-f1f8-46ce-b3a3-05a71847097e';

-- Vasculaghju: Prehistoric site in Corsica (limited documentation)
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = 'db120341-8ea9-4841-9e41-6c9d9df171b3';

-- Juhor: Mountain in Serbia with Bronze Age finds
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = '17483f6c-6a12-4652-83e1-e0a2f6665429';

-- Llyn Cerrig Bach: Iron Age votive deposit lake, Wales
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = 'a42d9ff4-6d8d-4cb2-bb1d-64b1c66cb290';

-- Medusa Mozaiği: Roman mosaic in odeon of Kibyra
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = '5f22c11c-22a4-4776-9120-75b3b9e33687';

-- Fontes Tamarici: Roman springs described by Pliny the Elder
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = '59f8faa5-2f0f-4278-9c2c-97c4adaa55b7';

-- Veldwezelt-Hezerwater: Paleolithic open-air site in Belgium
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = '5b24d3c4-1382-434d-a177-e09fb0b8778d';

-- Lang Rongrien Rock Shelter: Paleolithic cave site, Thailand (raw_data: "Cave Structures")
UPDATE unified_sites SET site_type = 'Archaeological Site'
WHERE id = 'bc89e53c-a9e6-465e-9cc9-4a6f844b9589';

-- === FLAGGED: Mookambika Wildlife Sanctuary — NOT an archaeological site ===
-- This is a modern wildlife sanctuary in Karnataka, India. Should be reviewed for removal.
-- UPDATE unified_sites SET site_type = ??? WHERE id = '2133d54c-f352-4325-ae0c-dd532f9a65d3';

COMMIT;

-- ============================================================
-- BLOCK 8: Bulk raw_year → period_start parsing (128 sites)
-- These are ancient_nerds sites where raw_data->>'year' contains
-- parseable date strings but period_start was NULL.
-- Idempotent: safe to re-run on VPS.
-- Generated 2026-02-15
-- ============================================================

BEGIN;

-- Group 1a: Simple "XXXX BC" (e.g., "3000 BC" → -3000)
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', ' BC$', ''))::int,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', ' BC$', ''))::int < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' BC$', ''))::int < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' BC$', ''))::int < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' BC$', ''))::int < -500  THEN '1500 - 500 BC'
      ELSE '500 BC - 1 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND period_start IS NULL
  AND raw_data->>'year' ~ '^[0-9]+ BC$';

-- Group 1b: Range "XXXX - YYYY BC" (take earliest, e.g., "3000 - 2000 BC" → -3000)
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', ' - [0-9]+ BC$', ''))::int,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', ' - [0-9]+ BC$', ''))::int < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' - [0-9]+ BC$', ''))::int < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' - [0-9]+ BC$', ''))::int < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' - [0-9]+ BC$', ''))::int < -500  THEN '1500 - 500 BC'
      ELSE '500 BC - 1 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND period_start IS NULL
  AND raw_data->>'year' ~ '^[0-9]+ - [0-9]+ BC$';

-- Group 1c: Simple "XXXX AD" (e.g., "500 AD" → 500)
UPDATE unified_sites
SET period_start = (regexp_replace(raw_data->>'year', ' AD$', ''))::int,
    period_name = CASE
      WHEN (regexp_replace(raw_data->>'year', ' AD$', ''))::int < 1    THEN '500 BC - 1 AD'
      WHEN (regexp_replace(raw_data->>'year', ' AD$', ''))::int < 500  THEN '1 - 500 AD'
      WHEN (regexp_replace(raw_data->>'year', ' AD$', ''))::int < 1000 THEN '500 - 1000 AD'
      WHEN (regexp_replace(raw_data->>'year', ' AD$', ''))::int < 1500 THEN '1000 - 1500 AD'
      ELSE '1500+ AD'
    END
WHERE source_id = 'ancient_nerds'
  AND period_start IS NULL
  AND raw_data->>'year' ~ '^[0-9]+ AD$';

-- Group 1d: Range "XXXX - YYYY AD" (take earliest)
UPDATE unified_sites
SET period_start = (regexp_replace(raw_data->>'year', ' - [0-9]+ AD$', ''))::int,
    period_name = CASE
      WHEN (regexp_replace(raw_data->>'year', ' - [0-9]+ AD$', ''))::int < 1    THEN '500 BC - 1 AD'
      WHEN (regexp_replace(raw_data->>'year', ' - [0-9]+ AD$', ''))::int < 500  THEN '1 - 500 AD'
      WHEN (regexp_replace(raw_data->>'year', ' - [0-9]+ AD$', ''))::int < 1000 THEN '500 - 1000 AD'
      WHEN (regexp_replace(raw_data->>'year', ' - [0-9]+ AD$', ''))::int < 1500 THEN '1000 - 1500 AD'
      ELSE '1500+ AD'
    END
WHERE source_id = 'ancient_nerds'
  AND period_start IS NULL
  AND raw_data->>'year' ~ '^[0-9]+ - [0-9]+ AD$';

-- Group 1e: Bare 4-digit years (e.g., "1200" → 1200)
UPDATE unified_sites
SET period_start = (raw_data->>'year')::int,
    period_name = CASE
      WHEN (raw_data->>'year')::int < 1    THEN '500 BC - 1 AD'
      WHEN (raw_data->>'year')::int < 500  THEN '1 - 500 AD'
      WHEN (raw_data->>'year')::int < 1000 THEN '500 - 1000 AD'
      WHEN (raw_data->>'year')::int < 1500 THEN '1000 - 1500 AD'
      ELSE '1500+ AD'
    END
WHERE source_id = 'ancient_nerds'
  AND period_start IS NULL
  AND raw_data->>'year' ~ '^[0-9]{3,4}$';

-- Group 1f: Cross-era "XXXX BC - YYYY AD" (take earliest = -XXXX)
UPDATE unified_sites
SET period_start = -(regexp_replace(raw_data->>'year', ' BC - [0-9]+ AD$', ''))::int,
    period_name = CASE
      WHEN -(regexp_replace(raw_data->>'year', ' BC - [0-9]+ AD$', ''))::int < -4500 THEN '< 4500 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' BC - [0-9]+ AD$', ''))::int < -3000 THEN '4500 - 3000 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' BC - [0-9]+ AD$', ''))::int < -1500 THEN '3000 - 1500 BC'
      WHEN -(regexp_replace(raw_data->>'year', ' BC - [0-9]+ AD$', ''))::int < -500  THEN '1500 - 500 BC'
      ELSE '500 BC - 1 AD'
    END
WHERE source_id = 'ancient_nerds'
  AND period_start IS NULL
  AND raw_data->>'year' ~ '^[0-9]+ BC - [0-9]+ AD$';

-- Special: Magdalenian → -17000
UPDATE unified_sites
SET period_start = -17000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND period_start IS NULL
  AND raw_data->>'year' = 'Magdalenian';

-- Special: Cro-magnon → -40000
UPDATE unified_sites
SET period_start = -40000, period_name = '< 4500 BC'
WHERE source_id = 'ancient_nerds'
  AND period_start IS NULL
  AND raw_data->>'year' = 'Cro-magnon';

COMMIT;

-- ============================================================
-- BLOCK 9: Web-research period fixes (259 sites)
-- Source: Wikipedia/Wikidata/WebSearch per-site research
-- Applied: 2026-02-15
-- ============================================================

BEGIN;

-- BATCH 1 (48 fixes)
UPDATE unified_sites SET period_start = -40000, period_name = '< 4500 BC' WHERE id = 'd7b8c0a6-0e25-4c12-b63e-1e7abd9af00f';
UPDATE unified_sites SET period_start = -2487, period_name = '3000 - 1500 BC' WHERE id = 'f6f190b6-7c0b-4cf5-8ceb-cf9ec567997d';
UPDATE unified_sites SET period_start = -3300, period_name = '4500 - 3000 BC' WHERE id = 'fe4edbed-be84-4b80-b5de-62ab3e4c88ef';
UPDATE unified_sites SET period_start = -1500, period_name = '3000 - 1500 BC' WHERE id = 'a9c5d1bf-b6d0-4486-a507-8dddfdc57a02';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '24695f34-5605-4cdd-965f-fd646c1ed044';
UPDATE unified_sites SET period_start = -3300, period_name = '4500 - 3000 BC' WHERE id = '01cdc8e2-56b7-4c9d-b6d0-68c290a65e55';
UPDATE unified_sites SET period_start = -1800, period_name = '3000 - 1500 BC' WHERE id = '576eeca0-250a-4d38-8524-aaf67bde36d6';
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = 'af25c5ad-8050-456e-94bd-c8f6e5fa1715';
UPDATE unified_sites SET period_start = -1400000, period_name = '< 4500 BC' WHERE id = 'a80e7611-46f8-4fd6-a74b-0b5e29defa6e';
UPDATE unified_sites SET period_start = -3000, period_name = '4500 - 3000 BC' WHERE id = 'b1eabcf0-cc21-4053-92a1-285b30da510b';
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC' WHERE id = 'e5948e02-efb2-4c4e-b3e6-8295aa3cdcac';
UPDATE unified_sites SET period_start = -1400000, period_name = '< 4500 BC' WHERE id = '5f10ac9c-682b-41cf-9eeb-7c2825b0ea4d';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '2c1c70ac-91df-4577-ac77-3bedd6c521ee';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '53b027b5-8d22-4339-a218-41dcb158a4e6';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '454ecea0-4c69-48a1-8fb3-5e96b53f683c';
UPDATE unified_sites SET period_start = -85000, period_name = '< 4500 BC' WHERE id = '44cc38c9-b726-4bff-8f59-c547b69d6dab';
UPDATE unified_sites SET period_start = -1000, period_name = '1500 - 500 BC' WHERE id = '8a68279e-6456-48ab-9543-7c33376fac42';
UPDATE unified_sites SET period_start = -550, period_name = '1500 - 500 BC' WHERE id = '9ac59d75-ae27-4515-8430-32ba6a23669e';
UPDATE unified_sites SET period_start = -525000, period_name = '< 4500 BC' WHERE id = 'da2f5fea-80b2-4c88-a5d1-738c054512b5';
UPDATE unified_sites SET period_start = -1000, period_name = '1500 - 500 BC' WHERE id = '1a9242d4-250f-4ffb-8dad-dae849c10798';
UPDATE unified_sites SET period_start = -1400000, period_name = '< 4500 BC' WHERE id = '3f888db6-1b30-44c7-b2f6-3effec34f650';
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC' WHERE id = '5ea4b4c5-9a5d-492d-aa71-5458b78d07a0';
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD' WHERE id = '23576019-c749-4ee9-95b1-cdae21f5ff06';
UPDATE unified_sites SET period_start = -2000, period_name = '3000 - 1500 BC' WHERE id = '1f3c04f4-4025-4779-9968-6aa298127478';
UPDATE unified_sites SET period_start = -3000, period_name = '4500 - 3000 BC' WHERE id = '763e4a8b-eed2-495d-81db-35f83a3d5d82';
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD' WHERE id = '916b8b05-0c42-4af3-b05e-9be842a23c5b';
UPDATE unified_sites SET period_start = 200, period_name = '1 - 500 AD' WHERE id = '74af1ed2-4221-4e13-8a96-e63631d01cc7';
UPDATE unified_sites SET period_start = -5600, period_name = '< 4500 BC' WHERE id = '5bf42cbd-5082-43a3-b064-91ca60423e51';
UPDATE unified_sites SET period_start = -3000, period_name = '4500 - 3000 BC' WHERE id = 'ffb35fc7-24f7-4722-8036-e4173ac6d8e6';
UPDATE unified_sites SET period_start = -3000, period_name = '4500 - 3000 BC' WHERE id = '58e730c7-6ec4-44a4-97e8-d2f75d9a1c9e';
UPDATE unified_sites SET period_start = -2000, period_name = '3000 - 1500 BC' WHERE id = '86383b38-f1a1-4f04-9b7e-8a49c3495829';
UPDATE unified_sites SET period_start = -132, period_name = '500 BC - 1 AD' WHERE id = '76d31c3a-0d8f-4b12-9b6d-41321e40af50';
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD' WHERE id = '83af1077-fe87-4b2e-ad58-e84628b9a4d6';
UPDATE unified_sites SET period_start = -4500, period_name = '< 4500 BC' WHERE id = '90ec5b47-7488-4bb4-8c4d-1259d30ac328';
UPDATE unified_sites SET period_start = -36000, period_name = '< 4500 BC' WHERE id = '255da98c-7cdf-46b3-878e-7eb55df2d8c2';
UPDATE unified_sites SET period_start = -37000, period_name = '< 4500 BC' WHERE id = '70c0458f-b0a0-458e-9755-6b9e39153342';
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '704e228b-e4e7-4097-bd71-819f72fb8a0a';
UPDATE unified_sites SET period_start = -100000, period_name = '< 4500 BC' WHERE id = 'aa90c7b3-4a88-4ea9-9ef2-4db7e5bba024';
UPDATE unified_sites SET period_start = -18000, period_name = '< 4500 BC' WHERE id = 'b96aa592-779d-4d93-a16f-7b09496b1139';
UPDATE unified_sites SET period_start = -40800, period_name = '< 4500 BC' WHERE id = 'd73a1955-ec4f-42cd-b6f3-f0b203ff8eee';
UPDATE unified_sites SET period_start = -150000, period_name = '< 4500 BC' WHERE id = 'f6daed37-710f-4512-a494-bb4ecddd4d2c';
UPDATE unified_sites SET period_start = -64800, period_name = '< 4500 BC' WHERE id = '29440d54-9b26-4f92-9f0c-b7573373d12c';
UPDATE unified_sites SET period_start = -115000, period_name = '< 4500 BC' WHERE id = '81666db8-d2a8-4557-8986-376a02bf40b2';
UPDATE unified_sites SET period_start = -66700, period_name = '< 4500 BC' WHERE id = '32a2b3eb-c4c3-4574-bbf5-30a4d7a68dfc';
UPDATE unified_sites SET period_start = -13000, period_name = '< 4500 BC' WHERE id = '043054e2-55c8-4b1a-8ad1-3f9092f0efea';
UPDATE unified_sites SET period_start = -35000, period_name = '< 4500 BC' WHERE id = '87abc0f0-0a56-420f-94ce-ada2998bbd0d';
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC' WHERE id = '4a87bc78-0813-4110-aa1e-3818326bee00';
UPDATE unified_sites SET period_start = -40800, period_name = '< 4500 BC' WHERE id = 'c8bc4dc3-af79-4cbd-b8cf-dd69df5b4ad6';
UPDATE unified_sites SET period_start = -28000, period_name = '< 4500 BC' WHERE id = 'cf7d3acb-1b74-484d-8084-6c7297b23ec0';
UPDATE unified_sites SET period_start = -200, period_name = '500 BC - 1 AD' WHERE id = '89bdbe2c-a19b-484d-b6ef-2ed464b1311b';

-- BATCH 2 (53 fixes)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '4faa104c-1f92-4968-aa85-ec1450813997';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '1941620d-0f59-46a3-9e13-d10e9c05cdfa';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = 'e59377f7-18eb-459e-adc4-b9c40274ddfa';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '9845a5a2-4ecc-412f-8455-7e156e0cbb16';
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD' WHERE id = 'a26993c6-b562-4c28-a584-8de2c9312dad';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '0286a741-77f2-4148-8e62-487041920281';
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC' WHERE id = '03ebb1eb-834c-46f9-a038-9231d40f8072';
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD' WHERE id = 'a511e195-58d5-40e8-af84-baa83518f5e8';
UPDATE unified_sites SET period_start = -8550, period_name = '< 4500 BC' WHERE id = '217b6292-d8ee-403b-a8ad-236304ac481d';
UPDATE unified_sites SET period_start = -1800, period_name = '3000 - 1500 BC' WHERE id = 'c9901c19-39a0-4b8f-baa5-448f3891ab39';
UPDATE unified_sites SET period_start = -350000, period_name = '< 4500 BC' WHERE id = '8e4f5b3f-25dd-471f-96e4-4398f89754bd';
UPDATE unified_sites SET period_start = -13000, period_name = '< 4500 BC' WHERE id = 'e3af20a8-86db-43d5-9562-909cfbdf3bbd';
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'a8c2a8e8-d03c-4037-ab82-8c246b2d6e29';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = '82ab3246-cd82-4453-bd84-4668d3640ad1';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = '92424ead-7e63-40d3-8796-76f8ef82ae86';
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD' WHERE id = 'f6825042-70ed-4d70-8e17-42575be53b67';
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '253204e7-0000-4ca2-aa8b-80d9b51c0685';
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC' WHERE id = '2f93c277-9023-4fbd-9b56-dc2c4f18c1f6';
UPDATE unified_sites SET period_start = 1850, period_name = '1500+ AD' WHERE id = '5f8ce412-3bb0-4aa3-aff3-cd1d825273a6';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = 'baf13030-1578-4edc-a351-ca627828a326';
UPDATE unified_sites SET period_start = -3500, period_name = '4500 - 3000 BC' WHERE id = '5f478ce8-5cb2-4a8f-bd80-95f64bae677a';
UPDATE unified_sites SET period_start = -60000, period_name = '< 4500 BC' WHERE id = 'f4931c71-9e14-4bdc-ad9d-88bf763b6985';
UPDATE unified_sites SET period_start = 43, period_name = '1 - 500 AD' WHERE id = 'ba3cbac4-815f-4e9c-85d7-4118d4e23499';
UPDATE unified_sites SET period_start = 5, period_name = '1 - 500 AD' WHERE id = 'f28a2d38-f5a9-49f2-83c8-53bb4c61cae4';
UPDATE unified_sites SET period_start = -3500, period_name = '4500 - 3000 BC' WHERE id = '58a2be59-ec1e-4667-96b9-3313ce406bc1';
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '008ecaa5-ce9b-484d-9eb8-0f27659bc91d';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = '559a729a-01e4-4161-bdc6-730494fb785b';
UPDATE unified_sites SET period_start = -3800, period_name = '4500 - 3000 BC' WHERE id = 'dd6ec46e-813f-458a-a881-a5673ea8b839';
UPDATE unified_sites SET period_start = -1800, period_name = '3000 - 1500 BC' WHERE id = '78123025-5f8c-433a-9623-a60ea4105600';
UPDATE unified_sites SET period_start = 700, period_name = '500 - 1000 AD' WHERE id = 'f91d645f-29ad-439d-83eb-fdf0531d93cc';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = '5e30b705-2163-47c0-bd65-3316be1806c9';
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'b4357b01-a483-4b2b-b667-68e0a6e6f500';
UPDATE unified_sites SET period_start = -11000, period_name = '< 4500 BC' WHERE id = '4598fdbb-4025-4bb3-955f-cdd68dae05ba';
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC' WHERE id = 'c88af005-464d-4b81-857b-d94db6b3e45a';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = '8a66f7db-94df-45d9-919f-760b966192be';
UPDATE unified_sites SET period_start = -50000, period_name = '< 4500 BC' WHERE id = '833d2de9-5bc4-425d-b5a5-111d742c8f0d';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = 'b3ebbc47-7624-4ef9-9f6f-bc03eab227f5';
UPDATE unified_sites SET period_start = 1, period_name = '1 - 500 AD' WHERE id = '9977d351-4c1a-465f-8928-f84c3a67248f';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '2968fd35-9b61-4dfb-bb1b-cc4489827fd6';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '21d9af3d-9d4e-4df0-beb1-268486146a61';
UPDATE unified_sites SET period_start = -400, period_name = '500 BC - 1 AD' WHERE id = '88b99e63-3075-4fef-9d90-91a8c1f7e62b';
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD' WHERE id = '296ed0f4-1ad0-4929-b019-196c80e547be';
UPDATE unified_sites SET period_start = -11000, period_name = '< 4500 BC' WHERE id = '82c9fb95-c776-4450-bb5c-93a70fdcb056';
UPDATE unified_sites SET period_start = 900, period_name = '500 - 1000 AD' WHERE id = 'b0b4e4d6-ef79-4b2d-ad6b-62532b5ba54d';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'ff4dc88e-bebe-4b88-90d3-6697bffc9107';
UPDATE unified_sites SET period_start = 1600, period_name = '1500+ AD' WHERE id = 'a3b55317-bae1-42b5-9c64-477749bdc2d5';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '7e23ac5b-3d28-4004-842a-6d3514ddd5ed';
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD' WHERE id = '04f2ddf1-3539-41e4-bea2-e0f1f9fa0476';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '2a1d1dfb-474c-44db-a3ea-81758fadf851';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = 'd7a19d68-d432-45d4-bd3d-55430b25ed04';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '66ca3d59-0402-4261-97cb-c5e5be3faac7';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = '9adffc6f-a7ef-4809-96db-60b43fe3bf33';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = 'd3afcf00-2741-44b9-b1de-db4cadb77e65';

-- BATCH 3 (53 fixes)
UPDATE unified_sites SET period_start = -1000, period_name = '1500 - 500 BC' WHERE id = '1dea486d-6a81-4b61-ac89-bca807ad78ab';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '791b7bc8-8015-4715-ae40-50452a4c6fb5';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '8590c435-e895-4d7e-9b06-d0f2027c04d7';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '5d0819e0-a352-4ea1-9d64-067da2e428f9';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '54bbe431-e520-498c-8413-4bbc23eb4947';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'aa24106a-9784-4f51-81a8-1f6b0c6dbab9';
UPDATE unified_sites SET period_start = 500, period_name = '500 - 1000 AD' WHERE id = 'a938f9bc-4f40-497d-8f2f-2ab44a0a2d1c';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '1be6202f-f47a-40f8-8b07-9fe22cc95000';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '28402a1d-9e31-4818-9790-783de876cecd';
UPDATE unified_sites SET period_start = 500, period_name = '500 - 1000 AD' WHERE id = 'a6d480fd-bb81-4339-bb85-59c7e8bf8d63';
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD' WHERE id = 'd4ead0d9-4f61-4021-a84d-da1b667f002d';
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD' WHERE id = '9b5751dd-d54e-4e8a-b4c0-7b4dc2a863c7';
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD' WHERE id = '5fe20684-2090-41cf-8154-c2a50a0b9602';
UPDATE unified_sites SET period_start = -400, period_name = '500 BC - 1 AD' WHERE id = '40acede4-eb32-4515-9ca4-b44145280678';
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD' WHERE id = 'f294fd21-7428-4c73-9810-dae8ff8ee546';
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC' WHERE id = '2297e801-c762-4bb9-9e88-102c65e301a1';
UPDATE unified_sites SET period_start = -400, period_name = '500 BC - 1 AD' WHERE id = 'db4c2f3e-2f4a-4dc6-bf01-23f109fe1837';
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD' WHERE id = 'e6f95365-5042-4815-9275-e0e5f295c8e6';
UPDATE unified_sites SET period_start = -500000, period_name = '< 4500 BC' WHERE id = '931ddb0f-7236-4315-ac59-8cc677dd5aa7';
UPDATE unified_sites SET period_start = -20000, period_name = '< 4500 BC' WHERE id = '6e1f996c-be31-4337-bd80-7a94b03a3d05';
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD' WHERE id = '1a76bfc9-7056-4848-ac12-d24016a923bb';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '69aaac26-9f4a-47da-beb4-d31ef8d4301f';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'ddc0a0bf-1313-499a-8ec6-77839727afe1';
UPDATE unified_sites SET period_start = -3000, period_name = '4500 - 3000 BC' WHERE id = '1d4dd1f5-e841-4c8c-9761-2d4ad3eec155';
UPDATE unified_sites SET period_start = -1000, period_name = '1500 - 500 BC' WHERE id = 'e9eacdcd-80e7-4101-aa88-b942ec755f5c';
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD' WHERE id = '53fd5500-0ce2-4bd0-a3d3-8ec069605e3e';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = '88c417e9-5131-401f-8187-1da8cc344b0f';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'fc514046-4f2c-42b1-a3f6-ca88404d2e18';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'facb2c7f-777a-4eb0-8036-731853847f07';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '7bcdeff1-fd34-4c0d-a32e-d8f812e64a73';
UPDATE unified_sites SET period_start = -400000, period_name = '< 4500 BC' WHERE id = '4dc7086c-f261-4f38-85f2-10a20eeda1bc';
UPDATE unified_sites SET period_start = 1100, period_name = '1000 - 1500 AD' WHERE id = '7cfb8a17-e0c7-4062-be2a-f79777dacf94';
UPDATE unified_sites SET period_start = -2500, period_name = '3000 - 1500 BC' WHERE id = 'a09044a9-4ff3-4df3-be04-72a953b67429';
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD' WHERE id = '82b9ba8e-bc9a-405a-afe2-fcb210a5d278';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'c54e678e-8662-42cd-8875-fc387cc19fad';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'ec64fd4c-0fa2-4932-9a75-6756b90aed5b';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'bee72fdb-a761-4a79-90ee-9e98d1d5ad75';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '2fe3e1da-dcae-4014-a4d9-8b3132952546';
UPDATE unified_sites SET period_start = 300, period_name = '1 - 500 AD' WHERE id = '1ac10af9-1ace-4be6-8e02-88dacc77b6c6';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '3dd6b568-007f-4a95-877b-12324e031893';
UPDATE unified_sites SET period_start = -11000, period_name = '< 4500 BC' WHERE id = '4a59d4e4-c3b6-40bf-9153-302dd1f52595';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'cd2e38bd-c70e-4813-8ccd-0a567ab6a7ca';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '6098d612-4f78-437a-87cb-739b74f254a4';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '69fb2e9b-8dda-4cfa-b5de-63ce3015c978';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'b4d35f13-0f0e-479e-84a1-e388dda01d4d';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '63b855c8-c281-42d8-87ea-58aeeec070ef';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = 'c3c19561-b4fc-48a8-9fd4-187fdc27f42b';
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD' WHERE id = 'a4d1130a-68fb-4acd-8b77-5088ace9a377';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'df891fda-0a06-48a3-a265-97c9b3138d23';
UPDATE unified_sites SET period_start = -3500, period_name = '4500 - 3000 BC' WHERE id = '000da27c-0797-4e58-a979-ae97b3d5016f';
UPDATE unified_sites SET period_start = 698, period_name = '500 - 1000 AD' WHERE id = '97b3cd09-f833-48ca-8273-8b76767fc245';
UPDATE unified_sites SET period_start = 500, period_name = '1 - 500 AD' WHERE id = 'bcc037db-7637-44c9-8204-3ce6d4370653';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'c8855169-8cd1-40ae-9f2a-cfc8be715d8b';

-- BATCH 4 (52 fixes)
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '54e2461b-5a65-4da6-9e73-10b14a813736';
UPDATE unified_sites SET period_start = -177, period_name = '500 BC - 1 AD' WHERE id = '3f9bdb7e-9739-47db-b323-1935cf6ea8d6';
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD' WHERE id = 'a457cbdf-37c9-4b06-b59c-fdfecc8ba582';
UPDATE unified_sites SET period_start = -1479, period_name = '3000 - 1500 BC' WHERE id = 'fc84c8b7-697c-4ee3-924b-e412f5585c2b';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '7a339d92-507c-43e2-8eef-ff924f8c4231';
UPDATE unified_sites SET period_start = -3000, period_name = '4500 - 3000 BC' WHERE id = '238793b3-c335-4dcf-8155-c9e2d4985e0d';
UPDATE unified_sites SET period_start = -100, period_name = '500 BC - 1 AD' WHERE id = '1c573084-c7d7-4072-84c3-30adc4b6c521';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '2a7e3b61-6a76-4f1a-8c4a-e0d895a129a5';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '9f5cf21d-173d-4387-bbf7-ac5b06ee134b';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'b54d2d6a-d3d4-442e-9cf4-1ddd1bf1073e';
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD' WHERE id = 'afb20664-90a8-4e20-bc76-d6c524f5ede0';
UPDATE unified_sites SET period_start = 1450, period_name = '1000 - 1500 AD' WHERE id = 'dafc7527-c6c8-45c3-8c7d-4813d20a4dcf';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = 'd2bfe5ff-6e7a-46ad-b9ae-69723cb08563';
UPDATE unified_sites SET period_start = 1500, period_name = '1500+ AD' WHERE id = '0db1078f-012b-42ef-a9b4-e5e482c92767';
UPDATE unified_sites SET period_start = -1280, period_name = '3000 - 1500 BC' WHERE id = '7345ac3a-0fbd-4507-807b-a2f8a592c39d';
UPDATE unified_sites SET period_start = 500, period_name = '500 - 1000 AD' WHERE id = '2051a8ae-6ce5-4a33-bfa6-997ed2479750';
UPDATE unified_sites SET period_start = -2000, period_name = '3000 - 1500 BC' WHERE id = '4f5d500f-4c00-48a8-a048-6a3deb43f76a';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = '30cf4488-c74c-42d8-8e21-a017ca0bf921';
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD' WHERE id = 'cb8cc790-ac27-4f13-afb0-b12a3cf4e6db';
UPDATE unified_sites SET period_start = -190, period_name = '500 BC - 1 AD' WHERE id = 'c365e1f8-e4bb-43f0-9c46-58497b709fae';
UPDATE unified_sites SET period_start = -3000, period_name = '4500 - 3000 BC' WHERE id = 'edd175c5-eeb5-4cff-8c18-7ae518915cc4';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'e1c3365d-f89e-468e-a928-8e5db1210844';
UPDATE unified_sites SET period_start = -7500, period_name = '< 4500 BC' WHERE id = '8f8d1ce5-3527-4c35-925f-579e6dc51784';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = '73be8eb3-140a-4646-8bfa-e7ec9d78c38c';
UPDATE unified_sites SET period_start = -111000, period_name = '< 4500 BC' WHERE id = 'f7f2dac5-0f0a-4cbd-8ac0-c2f1f42311ca';
UPDATE unified_sites SET period_start = -3000, period_name = '4500 - 3000 BC' WHERE id = 'a98dcb51-39c4-4ab9-b34e-1f10a9aa14d9';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '5b4a848a-90b8-432e-9016-d931607218cd';
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD' WHERE id = '5025eee3-28ea-46d6-b2c3-dbb1f38a24d6';
UPDATE unified_sites SET period_start = -800, period_name = '1500 - 500 BC' WHERE id = 'db9e04a9-afe5-4541-8ae4-0d7c5b14facc';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '29efc463-cdf8-4dd6-849b-ff378c87a2de';
UPDATE unified_sites SET period_start = -1240, period_name = '1500 - 500 BC' WHERE id = '3f7e973f-f972-4677-9d02-6ae0b6942fcd';
UPDATE unified_sites SET period_start = -500, period_name = '500 BC - 1 AD' WHERE id = '34272ded-e2dd-47ab-b771-f3fc4a68b1bb';
UPDATE unified_sites SET period_start = -13500, period_name = '< 4500 BC' WHERE id = '0ae727b3-6355-47ad-9c47-2c5f01a3bc20';
UPDATE unified_sites SET period_start = -1500, period_name = '1500 - 500 BC' WHERE id = '5c8779da-b96e-44a7-b460-fa391205e10d';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = 'cb688193-2ff5-4535-b1a7-af488587a451';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = '2b3667ad-f83a-4514-8ef9-62231a454215';
UPDATE unified_sites SET period_start = -1300, period_name = '1500 - 500 BC' WHERE id = '7df3ac64-8a51-4a51-aeb0-7b99c1e9c196';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '64137ead-762b-4621-a59c-5c7395ef4826';
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD' WHERE id = 'd1fd88e8-1e77-4bc2-859e-d72632d37500';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '58486903-37c4-4aa4-866f-f7f8d66205ac';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '1cf08f5b-a8a8-4e06-a586-17ae6d0cf153';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '018c0c9d-c85f-4ed9-86eb-8cf350ec83e7';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '99328522-518c-40cd-94a1-b541906c3f00';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'bc13a236-675e-46b4-8cb1-b5e86d9fbd97';
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD' WHERE id = 'ba2e3e1a-f3d0-4c41-9508-946ceced696a';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '7959bac1-48f2-4648-b9fa-7b23847cd894';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = '29924a49-a6ce-430e-a5f7-a048a20d7dca';
UPDATE unified_sites SET period_start = 400, period_name = '1 - 500 AD' WHERE id = '64ad25a0-6088-470f-a0f0-368159ceb43e';
UPDATE unified_sites SET period_start = -900, period_name = '1500 - 500 BC' WHERE id = '4cab063f-a1a1-4e24-a46a-d609f2f87f53';
UPDATE unified_sites SET period_start = -25000, period_name = '< 4500 BC' WHERE id = 'c9a49774-6211-499c-b80c-9dbeec95b47c';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '517e41aa-be07-4b3b-9b44-1a6a77de304e';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = 'b5974adf-ab54-406e-99a4-e7c29c6ca5ba';

-- BATCH 5 (53 fixes)
UPDATE unified_sites SET period_start = 600, period_name = '500 - 1000 AD' WHERE id = '80fa4dec-a12f-4604-b92e-bfa32b2e0ef6';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'c6fa5dc5-1eda-405f-97d2-9338392a8054';
UPDATE unified_sites SET period_start = 1250, period_name = '1000 - 1500 AD' WHERE id = '56c3e7d6-250a-457d-9c42-7d37ef47af3c';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = '940444fb-1897-4c1f-bdc2-30e967df95c8';
UPDATE unified_sites SET period_start = 1438, period_name = '1000 - 1500 AD' WHERE id = 'ece7f01a-17bf-4b09-afc9-8368b323a88b';
UPDATE unified_sites SET period_start = 150, period_name = '1 - 500 AD' WHERE id = '4b8583a1-da7c-4bf9-a702-05298be4227c';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = '22362770-e393-48d3-812d-34c7e772cf4c';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'b3d487a0-2f8b-4eb0-b6b8-7560377ebe9f';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '10fc71fe-5305-497e-8642-4219e822223a';
UPDATE unified_sites SET period_start = 100, period_name = '1 - 500 AD' WHERE id = '82a98ba6-5bd5-4a0c-8170-5ac93df1a89b';
UPDATE unified_sites SET period_start = 655, period_name = '500 - 1000 AD' WHERE id = 'fc029995-b6bb-4375-a5fa-9a0eb7d0fa85';
UPDATE unified_sites SET period_start = -12000, period_name = '< 4500 BC' WHERE id = 'f1dc14c0-5f0b-4bf1-a7ee-cecfb00514a5';
UPDATE unified_sites SET period_start = -47000, period_name = '< 4500 BC' WHERE id = 'a4ac2a6f-0159-447e-a6d2-7300fbc986ef';
UPDATE unified_sites SET period_start = -48000, period_name = '< 4500 BC' WHERE id = '801f9478-d27d-4c58-919b-2e14a07ca1a4';
UPDATE unified_sites SET period_start = -500, period_name = '1500 - 500 BC' WHERE id = 'bebaa4d3-fb8e-46a4-b9cb-fe6589925889';
UPDATE unified_sites SET period_start = -11000, period_name = '< 4500 BC' WHERE id = 'cb1b00bc-0495-43d9-8a69-c54aa3fb93b4';
UPDATE unified_sites SET period_start = -1500, period_name = '3000 - 1500 BC' WHERE id = '2d12562b-e482-4a6b-8329-5d7a22667a86';
UPDATE unified_sites SET period_start = 373, period_name = '1 - 500 AD' WHERE id = '58c0a320-200d-42ce-9477-2148736e6a65';
UPDATE unified_sites SET period_start = 690, period_name = '500 - 1000 AD' WHERE id = 'd972a5b7-866c-48d6-af54-d9ac91f00b0b';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '3a75476c-410d-4a37-9858-b0733fc6965d';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '33e2399e-fd68-4aab-bf79-c5695a6c0bf0';
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD' WHERE id = 'f0ca6709-214b-4f96-9ddc-069990a45034';
UPDATE unified_sites SET period_start = -250, period_name = '500 BC - 1 AD' WHERE id = 'f7a58094-985b-4f4c-ad0e-c7d8b4c5c2f4';
UPDATE unified_sites SET period_start = -300, period_name = '500 BC - 1 AD' WHERE id = 'f42a2997-d354-48b1-99b5-1a38cef7d01c';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'bb312418-3990-4a2a-86a3-5f3bc9c1c7b2';
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'e3c407dd-513d-4344-8155-7bcc5db65b54';
UPDATE unified_sites SET period_start = -4100, period_name = '4500 - 3000 BC' WHERE id = 'ea25fd7b-6bae-4a45-8a75-60ef783a9230';
UPDATE unified_sites SET period_start = -2000, period_name = '3000 - 1500 BC' WHERE id = '3845e670-6a97-47b6-b6c4-2387e7465523';
UPDATE unified_sites SET period_start = -2100, period_name = '3000 - 1500 BC' WHERE id = '56f3ec0c-0610-4701-8a4e-727b7d3a2512';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '622658a7-db08-4b38-8c80-023702db4a8f';
UPDATE unified_sites SET period_start = -500000, period_name = '< 4500 BC' WHERE id = '58dd6a0b-4c70-4eee-824f-a270800ef886';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '723dad90-4cd2-42ca-a8d1-9cf8fe11f1f0';
UPDATE unified_sites SET period_start = -600, period_name = '1500 - 500 BC' WHERE id = '7a0fa7b4-88fb-49d0-bfd7-9ebe9c5109d8';
UPDATE unified_sites SET period_start = -1200, period_name = '1500 - 500 BC' WHERE id = '14e9a488-b7a0-4205-aed8-a02d5ded87b5';
UPDATE unified_sites SET period_start = 1300, period_name = '1000 - 1500 AD' WHERE id = 'eaac27c7-d027-442a-ae0d-49d9e27dfb69';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '173c03f1-90d6-41d4-93d3-2bded70d2489';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'f057c595-7ea4-42ce-bf5d-734fad5a1e47';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '97e6920e-fb90-41d1-9e6c-38a76029e782';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = 'ca826aa3-d4f8-4ca3-ba60-5fc434bcaf96';
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'db120341-8ea9-4841-9e41-6c9d9df171b3';
UPDATE unified_sites SET period_start = -700, period_name = '1500 - 500 BC' WHERE id = '46be23ba-b785-4a9f-bcd7-c98b01ff445f';
UPDATE unified_sites SET period_start = 50, period_name = '1 - 500 AD' WHERE id = '297e5e17-96b1-4df9-88ac-638b1231a654';
UPDATE unified_sites SET period_start = -4000, period_name = '4500 - 3000 BC' WHERE id = 'bbae3db6-eb55-418c-9478-babfe5e087d2';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '5169991f-862a-451b-b76f-9a49a8bc5f8b';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = 'ddbaa0c7-7d30-45fa-ab80-71b0d49d8dec';
UPDATE unified_sites SET period_start = 1200, period_name = '1000 - 1500 AD' WHERE id = '9effdfa3-4808-45e7-be9a-578a870e1899';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '84e58c4d-9c61-4454-b165-041371c9b2c1';
UPDATE unified_sites SET period_start = 1400, period_name = '1000 - 1500 AD' WHERE id = '0a6e70ea-022a-4035-a866-0e54efff533d';
UPDATE unified_sites SET period_start = 1650, period_name = '1500+ AD' WHERE id = 'c54a5e46-c856-46be-b638-62d6fda1c8e5';
UPDATE unified_sites SET period_start = 500, period_name = '1 - 500 AD' WHERE id = '290410a4-c7ed-4fe7-842d-bfe7ab97e899';
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = 'f3a9d429-16b9-4ecd-97de-26319d3552ea';
UPDATE unified_sites SET period_start = 1000, period_name = '1000 - 1500 AD' WHERE id = '47396b3b-88aa-4d18-a7ac-8bec4154c19d';
UPDATE unified_sites SET period_start = 500, period_name = '1 - 500 AD' WHERE id = 'fa9441c6-255f-4fc3-aaba-8aa8b43759ac';

COMMIT;

-- ============================================================
-- MANUAL FIXES REQUIRED (42 sites — period_start still NULL)
-- These need human judgment: museums, geological features,
-- pseudoarchaeology, or insufficient archaeological data.
-- ============================================================
-- Museums (7): Ephesus Archaeological Museum, Leptis Magna Museum,
--   Maria Reiche Museum, Museo Campano, Museum of the Royal Tombs of Aigai,
--   Paracas History Museum, The Davidson Center
-- Geological/pseudoarchaeology (5): Bosnian Pyramid of Love/Moon/Sun,
--   Rocks of Saskatchewan, Singing Stones of Brittany, Popping Stone
-- Disputed/undatable (1): Yonaguni Monument
-- Cave structures (no clear date): Ayşepinar, Beşkardeşler Kaya Mezarlari,
--   Kirkdale Cave, Paradise Cave, Parque Nacional de Shorsky,
--   Temple of Lemminkäinen
-- Peruvian sites (insufficient data): Aya Muqu, Carachupa, Chipaw Marka,
--   Cuchi Machay, Hatun Misapata, Jinkiori, Kukuli, Kuntuyuq, Waruq
-- Other: Belören Kalesi, Bhagwan Bharat's Statue, Blaškovina,
--   Çem Kalesi, Currachjaghju, Furby, GOLOGOÇ VİRANŞEHİR,
--   Gritulu, Kamennyy Gorod, Mookambika Wildlife Sanctuary,
--   Northern Avenue Petroglyph Site, Prebreza,
--   Situs Megalit Tebing Tinggi
