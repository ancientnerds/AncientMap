BEGIN;

-- Batch fix: parse raw_year values that were previously unparseable

-- Thor's Cave (raw: 9650 BC)
UPDATE unified_sites SET period_start = -9650, period_name = '< 4500 BC' WHERE id = 'c9ab63ba-44f8-4e52-aec1-2e305191abf6';

-- Star Carr (raw: 9300 - 8480 BC)
UPDATE unified_sites SET period_start = -9300, period_name = '< 4500 BC' WHERE id = 'af010237-a119-4b7b-8a37-802f22d82708';

-- Caverna da Pedra Pintada (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = 'cf47a988-bf08-4482-93d3-2a051e83a2ff';

-- Tarragal Caves (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = '218a4df9-1bc1-43ce-a054-1d964d7232a4';

-- Wurdi Youang Stone Arrangement (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = 'cf8b5d56-cbc8-4550-bd77-4dc259020bad';

-- Ashdown Forest (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = 'b4a99c23-00b3-4eb5-80c0-c1569cb9a351';

-- Le Mas-d'Azil (raw: 9000 BC)
UPDATE unified_sites SET period_start = -9000, period_name = '< 4500 BC' WHERE id = 'bddad876-e487-4c8c-a0ff-8b84b0dfbef4';

-- Ancient Byblos (raw: 8800 - 5000 BC)
UPDATE unified_sites SET period_start = -8800, period_name = '< 4500 BC' WHERE id = '0f5bb5fa-e4a9-4e6e-ae02-48929ed84921';

-- Asana, Peru (raw: 8500 BC)
UPDATE unified_sites SET period_start = -8500, period_name = '< 4500 BC' WHERE id = '3ac6b54d-0231-4b56-b1c0-b7fac461bbcc';

-- Ancon Archaeological Site (raw: 8000 BC - 1530 AD)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'ac28b46b-542e-48b7-adf9-32da0efd74c1';

-- Blick Mead (raw: 8000 - 4000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '6ff3e4f1-8f21-410a-9c93-d4468c91a762';

-- Steppe Geoglyphs (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'f78f8d70-ca5f-4831-9475-e4369414c5b1';

-- Bidjigal Reserve (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '8fe4115a-617d-4cfc-ab35-272e8b2c1db2';

-- Cuddie Springs (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'd6fabe8c-061f-4885-8e02-cc6276c6f23c';

-- Karta (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '2ff6f6ff-dada-465c-ad3b-6db67b57a31b';

-- Koongine Cave (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '3aa70cf2-d56b-4401-8a60-2cd12131827c';

-- Kastros (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'f0b20fa9-aab2-400d-bfa8-24af297bb993';

-- Tenta, Cyprus (raw: 8000 - 5000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '6e8ac9be-7600-4248-921b-0477ca4a70dc';

-- Warren Hill, Bournemouth (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'fdeca69b-4a68-455c-a865-044b37ccfd21';

-- European Archaeological Park of Bliesbruck-Reinheim (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '540037f8-f9af-4776-b2fa-b82b4e9a80f0';

-- Pantelleria Vecchia Bank Megalith (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'daa1ea4b-c002-4552-a4ef-45d996c6cea6';

-- Għar Dalam (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'ebbad3eb-877c-4c7f-b6bf-66723f7b49e6';

-- Guitarrero Cave (raw: 8000 BC - 1000 AD)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = 'd1a6a883-779d-47eb-8496-78fbb360ddd6';

-- Toquepala Caves (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '2b7bb7a9-4759-41bf-a703-8f4da42a1b5c';

-- Balanced Rock, North Salem (raw: 8000 BC)
UPDATE unified_sites SET period_start = -8000, period_name = '< 4500 BC' WHERE id = '2fb4a171-fe52-40c9-8bcb-195cd068b55d';

-- Howick House (raw: 7600 BC)
UPDATE unified_sites SET period_start = -7600, period_name = '< 4500 BC' WHERE id = 'de97fdf7-80cc-425c-9c5b-b26b03310155';

-- Combe-Capelle (raw: 7500 BC)
UPDATE unified_sites SET period_start = -7500, period_name = '< 4500 BC' WHERE id = 'ac76d3ef-82df-4fcc-8da4-f4fc7f59716e';

-- Mehrgarh (raw: 7000 - 2000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = '2eae8fd6-d3d4-4764-a8bd-2d3a8f88ebbe';

-- Samsø (raw: 7000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = '49835383-20b8-44e0-9bf1-9e06cf2ecbb1';

-- Sassi di Matera (raw: 7000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = 'b0b461de-f74e-47b9-8b91-32c35b7c89c6';

-- Bir Hima Rock Petroglyphs and Inscriptions (raw: 7000 - 1000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = 'b1135e25-0b17-4daf-ab6f-57b3cfb9a1fa';

-- Jabal al-ʿHayn (raw: 7000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = '7ccaad38-8cfb-401e-a938-e2c792914b75';

-- Cave del Valle, Cantabria (raw: 7000 BC)
UPDATE unified_sites SET period_start = -7000, period_name = '< 4500 BC' WHERE id = '69ef4043-f69f-4f87-b422-09eb53a72950';

-- Atlit Yam (raw: 6900 - 6300 BC)
UPDATE unified_sites SET period_start = -6900, period_name = '< 4500 BC' WHERE id = 'cc240cba-a746-40f1-9045-b84efedf3e0d';

-- Ancient Corinth (raw: 6500 - 146 BC)
UPDATE unified_sites SET period_start = -6500, period_name = '< 4500 BC' WHERE id = 'e2f8cf43-f499-4363-8fcb-af93e79ea756';

-- Damjili Cave (raw: 6400 - 6000 BC)
UPDATE unified_sites SET period_start = -6400, period_name = '< 4500 BC' WHERE id = '15bc0443-6fb4-48df-a213-2d5095945d65';

-- Eston Nab (raw: 6000 - 700 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '277970ce-65f8-403a-8e20-dbcadac0f214';

-- Gruta do Gentio (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = 'fab3989d-2c06-40cc-9d22-c7fb58e5e94f';

-- Bouldnor Cliff (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = 'a9a32ee2-bd62-4fe4-8515-0ccdda65a7ee';

-- Castellane (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = 'dfd4d30e-1a29-4917-9626-787b823d7748';

-- Yarim Tepe (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '9e17ecc2-7c59-4f03-bea4-8d32de261d3e';

-- Boca de Potrerillos (raw: 6000 - 2000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '69fb9773-3709-4e8e-8682-96c75f57dfc6';

-- Tumba Madžari (raw: 6000 - 4300 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '5741eec1-d6ca-4a63-b0cb-f9a106a4acca';

-- Rock Carvings in Central Norway (raw: 6000 BC - 300 AD)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = 'd928b37a-38d1-4c34-8e89-49703f92f313';

-- Al Thumamah, Riyadh (raw: 6000 BC)
UPDATE unified_sites SET period_start = -6000, period_name = '< 4500 BC' WHERE id = '9b3a51e8-25ee-4936-932a-af5e2fd48e01';

-- Dispilio (raw: 5600 - 5000 BC)
UPDATE unified_sites SET period_start = -5600, period_name = '< 4500 BC' WHERE id = 'b11e591e-1f4c-4850-a7af-b5a13bc499cc';

-- Samarra (raw: 5500 - 3900 BC)
UPDATE unified_sites SET period_start = -5500, period_name = '< 4500 BC' WHERE id = '6d530908-adfd-44bf-b0dc-d4a02d2cdefb';

-- Qillqatani (raw: 5500 BC - 1472 AD)
UPDATE unified_sites SET period_start = -5500, period_name = '< 4500 BC' WHERE id = '29bbdfce-7b18-4530-b668-8a2fb289694b';

-- Pločnik - Archaeological Site (raw: 5500 - 4700 BC)
UPDATE unified_sites SET period_start = -5500, period_name = '< 4500 BC' WHERE id = '412a1f97-7dfd-4624-b6ec-2813217f39bf';

-- Settlements of the Cucuteni-Trypillia Culture (raw: 5500 - 2750 BC)
UPDATE unified_sites SET period_start = -5500, period_name = '< 4500 BC' WHERE id = '934ed584-2c13-46fc-bf38-eadd53b68d6f';

-- Eridu, Sumeria (raw: 5400 BC)
UPDATE unified_sites SET period_start = -5400, period_name = '< 4500 BC' WHERE id = '5cd47e05-c322-4510-b40f-c1f75072c147';

-- Herxheim - Archaeological Site (raw: 5300 - 4950 BC)
UPDATE unified_sites SET period_start = -5300, period_name = '< 4500 BC' WHERE id = 'e6ec727e-8e27-4885-b2bb-a9aadd8f17c9';

-- Langweiler - Archaeological Site (raw: 5300 - 4900 BC)
UPDATE unified_sites SET period_start = -5300, period_name = '< 4500 BC' WHERE id = 'dde240ca-5969-4123-a842-e7e235f7566b';

-- Saliagos (raw: 5000 - 4500 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '64fe03e2-33c3-4836-b012-b3e50917fcf6';

-- Sperris Quoit (raw: 5000 - 3000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '5bdfb4fe-496d-4c3a-9032-d5677201fca8';

-- Stepanivka (raw: 5000 - 4300 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'cd10aef4-26b6-477b-bc12-de3786c10594';

-- Alikomektepe (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '0d4830b5-92f1-4698-9aca-d32079f20e11';

-- Tell Yunatsite (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '18f488c0-fce6-4ea4-b732-d23fe5759cd1';

-- Lismore Fields (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '75f2454d-5538-42ea-87b2-ba091dec3df6';

-- Alignements de Kerzerho (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'bfc9d15b-70a1-44e7-ba2c-98195fb535df';

-- Grotte de Lombrives (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'e7623642-d009-4d1f-8f0e-fa03a89be90e';

-- La Noce de Pierres (raw: 5000 - 4000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '8b90f9f0-db52-4d17-a699-e70fc6e5c2ae';

-- Le Grand-Pressigny (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '6c736688-98d7-4c57-bf53-1f4367950131';

-- Mane Braz (raw: 5000 - 4000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'c1980a31-6a2b-4e83-ad99-8f36b6036ff2';

-- Menhir de Champ-Dolent (raw: 5000 - 4000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'f634e2ff-366e-49f1-be74-ac930ba5bc02';

-- Saint-Michel Tumulus (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '29e8f8a9-119e-4cb7-8c24-c1ebd943cfe3';

-- Santa Verna (raw: 5000 - 3400 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'f8ccb519-328b-4b91-8c67-3416ee2aa788';

-- Sheri Khan Tarakai (raw: 5000 - 2000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = 'c3b60256-57d1-4b74-80f0-1a2536795a20';

-- Menhir of Meada (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '521ade1a-0eaf-442b-973d-ccae9e9fbb35';

-- Ekornavallen (raw: 5000 BC - 500 AD)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '480f44f7-ad94-4ea5-bad8-fde912fa692b';

-- Gärde (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '4235fa73-a58f-400b-a1f6-4998a8d2893f';

-- Maidanetske (raw: 5000 BC)
UPDATE unified_sites SET period_start = -5000, period_name = '< 4500 BC' WHERE id = '9ad64db8-ba14-45f4-b565-7bf2c29db1f1';

-- Goseck Circle (raw: 4900 - 4700 BC)
UPDATE unified_sites SET period_start = -4900, period_name = '< 4500 BC' WHERE id = '8862f0da-6584-4963-911f-a88c454dc321';

-- Barnenez (raw: 4800 BC)
UPDATE unified_sites SET period_start = -4800, period_name = '< 4500 BC' WHERE id = '348770cd-a3a2-4b6e-83f7-bd5f5d699022';

-- Tumulus of Bougon (raw: 4800 BC)
UPDATE unified_sites SET period_start = -4800, period_name = '< 4500 BC' WHERE id = 'de449341-fecc-48c2-ab1d-0087ce60e174';

-- Solnitsata (raw: 4700 - 4200 BC)
UPDATE unified_sites SET period_start = -4700, period_name = '< 4500 BC' WHERE id = '4541e162-c69b-49d8-a4db-04e66089e8fd';

-- Locmariaquer Megaliths (raw: 4700 BC)
UPDATE unified_sites SET period_start = -4700, period_name = '< 4500 BC' WHERE id = '0cd58c95-e8da-453a-9ac4-ecaeeda843cc';

-- Varna Necropolis (raw: 4600 - 4200 BC)
UPDATE unified_sites SET period_start = -4600, period_name = '< 4500 BC' WHERE id = 'fe6a7e02-39e4-46bf-abb9-b1862974f252';

-- Rock Carvings at Tennes (raw: 4600 - 2600 BC)
UPDATE unified_sites SET period_start = -4600, period_name = '< 4500 BC' WHERE id = 'a776d595-3309-45c7-9c7f-014181af2a84';

-- Deriivka (raw: 4500 - 3500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '0bf5e631-0ee8-4b75-9c06-fd6d713cc42d';

-- Ebbsfleet Valley (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'd9dc6883-3762-4abc-9dca-736e3292f527';

-- Hazleton Long Barrows (raw: 4500 - 2500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '9a941093-043f-4287-b188-aebddd81df62';

-- King Lud's Entrenchments and The Drift (raw: 4500 - 2500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '0b8a8edd-8a60-4758-985c-bf354de4a985';

-- Green Gully Archaeological Site (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'dac9b6e1-a54d-4b9a-b400-5fa295ba2040';

-- Kow Swamp Archaeological Site (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '06f6a014-f2c1-423a-8944-17c81374fd02';

-- Stenseby Passage Grave (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '2c621de8-bfe8-4f0f-96a9-01b3761ea97a';

-- Arbor Low (raw: 4500 - 1200 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'b3a11168-712b-445a-b453-c945be7900f3';

-- Broadsands Chambered Tomb (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '186eeb54-e6a0-4370-87c6-fbcaae023a33';

-- Cleeve Hill, Gloucestershire (raw: 4500 BC - 1st c. AD)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '6b926b71-b756-43c4-9bd8-f987641927da';

-- Drizzlecombe (raw: 4500 - 1200 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'c82e8c63-783d-4d7b-aead-69052b6a04a2';

-- Eggardon Hill (raw: 4500 - 2500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '3debd642-ff96-4840-bff2-9d8faced25cd';

-- Great Tottington (raw: 4500 - 2500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'c221d864-3e29-4789-a581-f52f3c3cf096';

-- Knowlton Circles (raw: 4500 - 2200 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '5a04c048-e207-42fe-9d26-b39a0217bf09';

-- Lanyon Quoit (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '4eba8602-4117-47ee-9c24-7e0ab06ef999';

-- Carnac Stones (raw: 4500 - 3300 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'b539ba9e-5d7e-4ce8-a9ff-943ac3247297';

-- Craménil (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '683f96a1-3a51-40da-9d97-0d4971650334';

-- Erdeven (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'c93f25d4-5aa3-46f9-a672-71a2000ce517';

-- Tombeau de Merlin (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'b27222dd-e77f-419d-9f1b-55bafcf61cc0';

-- Hohlenstein-Stadel (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'f0b786ae-17e0-4ce1-bfdc-c9184e5473a3';

-- Syberg (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '70762563-db82-43f3-ad30-bce5fde9c9bd';

-- Rock Carvings at Åsli (raw: 4500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = 'e8235f8c-e30c-4c97-8297-639b2681d46b';

-- Anta das Pedras Grandes (raw: 4500 - 2000 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '234afaf4-4030-41f9-aac6-6378d375d157';

-- Medvednjak (raw: 4500 - 3500 BC)
UPDATE unified_sites SET period_start = -4500, period_name = '4500 - 3000 BC' WHERE id = '6eaec8c3-97e1-4e7b-b1d8-96b14c96a323';

-- Lëkurësi Castle (raw: 1537 AD)
UPDATE unified_sites SET period_start = 1537, period_name = '1500+ AD' WHERE id = 'af9036d8-9a13-4107-b22d-b5c088006d91';

-- Oudong (raw: 1601 - 1866 AD)
UPDATE unified_sites SET period_start = 1601, period_name = '1500+ AD' WHERE id = '37f08947-0576-48de-90ca-ef211b615619';

-- Sheikhupura Fort (raw: 1607 AD)
UPDATE unified_sites SET period_start = 1607, period_name = '1500+ AD' WHERE id = 'b9f26550-7988-4a34-a3ff-7ef9cb69c838';

-- Tomb of Ali Mardan Khan (raw: 1630 AD)
UPDATE unified_sites SET period_start = 1630, period_name = '1500+ AD' WHERE id = '58d46ab0-7fc9-4dfa-bf40-a5042d4a91be';

-- Forte de Santa Luzia (raw: 1641 - 1648 AD)
UPDATE unified_sites SET period_start = 1641, period_name = '1500+ AD' WHERE id = '3ff2ae0e-9095-48ed-a45e-0d8c9f455527';

-- Sahasralinga (raw: 1678 - 1718 AD)
UPDATE unified_sites SET period_start = 1678, period_name = '1500+ AD' WHERE id = '075337ec-9108-431f-ae90-d5d0e795f23a';

-- Ksar el Barka (raw: 1690 AD)
UPDATE unified_sites SET period_start = 1690, period_name = '1500+ AD' WHERE id = 'a5d9e9a7-9fd2-4a0f-a3ae-7dd78fba429b';

-- Shanqal Fort (raw: 1737 AD)
UPDATE unified_sites SET period_start = 1737, period_name = '1500+ AD' WHERE id = '9f823459-f4ce-43cc-a433-b1cdaf9f89ad';

-- Deir el kalaa (raw: 1748 AD)
UPDATE unified_sites SET period_start = 1748, period_name = '1500+ AD' WHERE id = '0e004ad3-7c38-4926-8bb7-86593ec4c4f7';

-- Sundarnarayan Temple (raw: 1756 AD)
UPDATE unified_sites SET period_start = 1756, period_name = '1500+ AD' WHERE id = '5067da0a-d681-4fe3-91e5-e2dc7c0656d7';

-- Kot Diji Fort (raw: 1795 AD)
UPDATE unified_sites SET period_start = 1795, period_name = '1500+ AD' WHERE id = '98cb1e3f-2eab-4bd0-9cda-8bd61abcacb6';

-- Ali Masjid Fort (raw: 1837 AD)
UPDATE unified_sites SET period_start = 1837, period_name = '1500+ AD' WHERE id = '8c159d7f-d954-44fc-aab9-6b7841d68a35';

-- Krishnabai Mandir (raw: 1888 AD)
UPDATE unified_sites SET period_start = 1888, period_name = '1500+ AD' WHERE id = '826407f8-35ca-4423-bd85-5f53a3d95ea2';

-- Museo de Antropologia de Xalapa (raw: 1937)
UPDATE unified_sites SET period_start = 1937, period_name = '1500+ AD' WHERE id = '761dfa49-30a6-4e09-a4c6-cb5294f3a98e';

-- Charents Arch (raw: 1957 AD)
UPDATE unified_sites SET period_start = 1957, period_name = '1500+ AD' WHERE id = 'a9d840ac-4636-40bf-9570-682550967728';

-- Mérida Anthropological Museum (raw: 1959)
UPDATE unified_sites SET period_start = 1959, period_name = '1500+ AD' WHERE id = '01c36727-31bd-45ae-9908-5c7043403cd2';

-- Shri Bhagwan Bahubali Monolithic Statue (raw: 1973 AD)
UPDATE unified_sites SET period_start = 1973, period_name = '1500+ AD' WHERE id = 'abfa8b60-ea29-4150-925f-87d4b1fe8092';

-- Chacamarca Historic Sanctuary (raw: 1974 AD)
UPDATE unified_sites SET period_start = 1974, period_name = '1500+ AD' WHERE id = '160da9ec-9bc4-4893-8066-dd3afb41c5b2';

-- Museo Regional de Antropologia Carlos Pellier (raw: 1980)
UPDATE unified_sites SET period_start = 1980, period_name = '1500+ AD' WHERE id = 'c1e49d01-2e46-4ecc-af7f-1fd39555fc8e';

-- Museo Regional de Campeche (raw: 1986)
UPDATE unified_sites SET period_start = 1986, period_name = '1500+ AD' WHERE id = 'd48eb704-d535-4be7-9695-868ee650cbb7';

-- Museo de la Arquitectura Maya (raw: 2005)
UPDATE unified_sites SET period_start = 2005, period_name = '1500+ AD' WHERE id = '9108b193-4370-4997-a271-7d20836efeed';

-- Khushuu Tsaidam Museum (raw: 2008 AD)
UPDATE unified_sites SET period_start = 2008, period_name = '1500+ AD' WHERE id = '71d8e2bc-7406-4c4a-b68d-2ff1b71800e8';

-- King Richard III Visitor Centre (raw: 2014 AD)
UPDATE unified_sites SET period_start = 2014, period_name = '1500+ AD' WHERE id = 'aa56465b-1a9e-45b2-abec-b50be3796d8f';

COMMIT;