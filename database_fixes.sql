-- Database Audit Fixes — 100-site test batch
-- Generated 2026-02-14
-- Total: 40 fixes (8 type, 28 period, 3 suspicious-date, 3 medium-confidence, 1 country)
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

COMMIT;
