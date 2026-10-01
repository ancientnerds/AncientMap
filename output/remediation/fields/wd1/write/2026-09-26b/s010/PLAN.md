# WD1 fields-wd1-2026-09-26b-s010: plan

Built 2026-09-30T06:04:56+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s010`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s010:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 280 |
| sites_written | 96 |
| refused | 24 |
| cells:geom | 21 |
| cells:lat | 21 |
| cells:lon | 21 |
| cells:period_name | 60 |
| cells:period_start | 59 |
| cells:site_type | 55 |
| cells:source_url | 43 |
| refused:coordinates-unresolved | 20 |
| refused:country-changes | 4 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Akdam Dorik Mezar | source_url | `https://www.gidilmeli.com/Akdam-dor-kaya-gomutu-kas/11838/1` | `https://kulturenvanteri.com/en/yer/dor-kaya-mezari/` | wd1-replace |
| Altendorf Megalithic Tomb | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Amazmaz | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Amazmaz | period_start | `-500` | `NULL` | wd1-clear |
| Ancient Corinth | site_type | `Megalithic stones` | `City` | wd1-replace |
| Ancient Methone | period_name | `1500 - 500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Ancient Methone | period_start | `-1500` | `-4000` | wd1-replace |
| Ancient Methone | source_url | `https://en.wikipedia.org/wiki/Ancient_Methone` | `https://en.wikipedia.org/wiki/Methone_(Macedonia)` | wd1-replace |
| Arbury Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Arbury Hill | period_start | `-1500` | `NULL` | wd1-clear |
| Arbury Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Arbury Hill | source_url | `https://en.wikipedia.org/wiki/Arbury_Hill` | `https://her.northamptonshire.gov.uk/Monument/MNN329` | wd1-replace |
| Argos, Peloponnese | geom | `0101000020E6100000417EF7C376B736400A107D39F4CE4240` | `SRID=4326;POINT(22.72079 37.63091)` | wd1-point |
| Argos, Peloponnese | lat | `37.61682814222884` | `37.63091` | wd1-replace |
| Argos, Peloponnese | lon | `22.716655967639102` | `22.72079` | wd1-replace |
| Argos, Peloponnese | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Argos, Peloponnese | period_start | `-2000` | `-5000` | wd1-replace |
| Argos, Peloponnese | source_url | `https://en.wikipedia.org/wiki/History` | `https://en.wikipedia.org/wiki/Argos,_Peloponnese` | wd1-replace |
| Arvalem Caves | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Arvalem Caves | period_start | `1` | `501` | wd1-replace |
| Arvalem Caves | source_url | `https://en.wikipedia.org/wiki/Arvalem_Caves` | `https://www.livehistoryindia.com/story/amazing-india/arvalem` | wd1-replace |
| Aslanlı Mabet | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Aslanlı Mabet | source_url | `https://eskisehir.ktb.gov.tr/TR-157674/solonun-mezariaslanli` | `https://eskisehir.ktb.gov.tr/TR-336939/solonun-mezari---asla` | wd1-replace |
| Athena Tapınağı | site_type | `Temple complex` | `Temple` | wd1-replace |
| Athena Tapınağı | source_url | `https://www-canakkale--ayvacik-gov-tr.translate.goog/athena-` | `https://de.wikipedia.org/wiki/Athenatempel_(Assos)` | wd1-replace |
| Baba-Dervish Settlement | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Baba-Dervish Settlement | period_start | `-3000` | `-6000` | wd1-replace |
| Badbury Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Badbury Hill | source_url | `https://en.wikipedia.org/wiki/Badbury_Hill` | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord` | wd1-replace |
| Beacon Ring | geom | `0101000020E61000007BF45ECD938808C0010098AD37534A40` | `SRID=4326;POINT(-3.0878 52.6449)` | wd1-point |
| Beacon Ring | lat | `52.65013666078449` | `52.6449` | wd1-replace |
| Beacon Ring | lon | `-3.0666881603816` | `-3.0878` | wd1-replace |
| Beacon Ring | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Beacon Ring | period_start | `-1500` | `NULL` | wd1-clear |
| Beacon Ring | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Beacon Ring | source_url | `https://en.wikipedia.org/wiki/Long_Mountain_(Powys)` | `https://cy.wikipedia.org/wiki/Caer_Digoll` | wd1-replace |
| Blue Bell Hill | site_type | `Megalithic stones` | `Dolmen` | wd1-replace |
| Blue Bell Hill | source_url | `https://en.wikipedia.org/wiki/Blue_Bell_Hill` | `https://heritage.kent.gov.uk/Monument/MKE2504` | wd1-replace |
| Burghead Chambered Well | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Burghead Chambered Well | period_start | `-1000` | `NULL` | wd1-clear |
| Burghead Chambered Well | source_url | `https://en.wikipedia.org/wiki/Burghead` | `https://nl.wikipedia.org/wiki/Burghead_Well` | wd1-replace |
| Burledge Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Burledge Hill | period_start | `-1500` | `NULL` | wd1-clear |
| Carrock Fell | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Carrock Fell | period_start | `-1000` | `NULL` | wd1-clear |
| Carrock Fell | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Carrock Fell | source_url | `https://en.wikipedia.org/wiki/Carrock_Fell` | `https://www.megalithic.co.uk/article.php?sid=7481` | wd1-replace |
| Castle of Kirkûk | geom | `0101000020E6100000A76331FDAF3946403D639272FDD64140` | `SRID=4326;POINT(44.395833 35.469722)` | wd1-point |
| Castle of Kirkûk | lat | `35.679609605291695` | `35.469722` | wd1-replace |
| Castle of Kirkûk | lon | `44.4506832591208` | `44.395833` | wd1-replace |
| Castle of Kirkûk | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Castle of Kirkûk | period_start | `1` | `-884` | wd1-replace |
| Castro de A Cidá | geom | `0101000020E6100000373E2E23C6CA20C086A485BD8CAF4540` | `SRID=4326;POINT(-9.013628 42.561386)` | wd1-point |
| Castro de A Cidá | lat | `43.37148255372544` | `42.561386` | wd1-replace |
| Castro de A Cidá | lon | `-8.396042918581868` | `-9.013628` | wd1-replace |
| Castro de A Cidá | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Chapel Carn Brea | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Chapel Carn Brea | period_start | `-4500` | `-2500` | wd1-replace |
| Chapel Carn Brea | site_type | `Barrow` | `Cairn` | wd1-replace |
| Chapel Carn Brea | source_url | `https://en.wikipedia.org/wiki/Chapel_Carn_Brea` | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord` | wd1-replace |
| Chillerton Down | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Chillerton Down | period_start | `-1000` | `NULL` | wd1-clear |
| Chillerton Down | site_type | `Earthwork` | `Fort` | wd1-replace |
| Chillerton Down | source_url | `https://en.wikipedia.org/wiki/Chillerton_Down` | `https://www.megalithic.co.uk/article.php?sid=52806` | wd1-replace |
| Chukimarka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Chukimarka | period_start | `1000` | `NULL` | wd1-clear |
| Chukimarka | site_type | `Rock relief/carving` | `NULL` | wd1-clear |
| Chukimarka | source_url | `https://mapio.net/pic/p-842036/` | `https://www.openstreetmap.org/node/7154047486` | wd1-replace |
| Cocoraque Butte Archaeological District | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Cocoraque Butte Archaeological District | period_start | `1` | `NULL` | wd1-clear |
| Cocoraque Butte Archaeological District | source_url | `https://en.wikipedia.org/wiki/Cocoraque_Butte_Archaeological` | `https://npgallery.nps.gov/AssetDetail/NRIS/75000355` | wd1-replace |
| Cova Negra | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cova Negra | period_start | `-300000` | `NULL` | wd1-clear |
| Cumbemayo | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Cumbemayo | period_start | `-3000` | `-1500` | wd1-replace |
| Cumbemayo | site_type | `Petroglyphs` | `Aqueduct` | wd1-replace |
| Dilmun Burial Mounds - Aali Burial Mounds | source_url | `https://en.wikipedia.org/wiki/A%27ali` | `https://culture.gov.bh/en/visitingbahrain/CulturalTourism/De` | wd1-replace |
| Dinas Dinlle | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Dinas Dinlle | period_start | `-3000` | `NULL` | wd1-clear |
| Dinas Dinlle | source_url | `https://en.wikipedia.org/wiki/Hillfort` | `https://en.wikipedia.org/wiki/Dinas_Dinlle` | wd1-replace |
| Double Arches Pit | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Double Arches Pit | period_start | `-500` | `NULL` | wd1-clear |
| Er Lannic | source_url | `https://en.wikipedia.org/wiki/Er_Lannic` | `https://fr.wikipedia.org/wiki/Cromlech_d%27Er_Lannic` | wd1-replace |
| Farley Green, Surrey | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Farley Green, Surrey | period_start | `1` | `NULL` | wd1-clear |
| Farley Green, Surrey | site_type | `Temple complex` | `Temple` | wd1-replace |
| Farley Green, Surrey | source_url | `https://en.wikipedia.org/wiki/Farley_Green,_Surrey` | `https://www.roman-britain.co.uk/places/farley_heath/` | wd1-replace |
| Fiskerton Log Boat | geom | `0101000020E610000095067446A631E1BF3068CC68AF9D4A40` | `SRID=4326;POINT(-0.428455 53.230979)` | wd1-point |
| Fiskerton Log Boat | lat | `53.23191556912241` | `53.230979` | wd1-replace |
| Fiskerton Log Boat | lon | `-0.5373107315101203` | `-0.428455` | wd1-replace |
| Fiskerton Log Boat | site_type | `Museum` | `Religious` | wd1-replace |
| Fiskerton Log Boat | source_url | `https://en.wikipedia.org/wiki/Fiskerton_log_boat` | `https://heritage-explorer.lincolnshire.gov.uk/Monument/MLI52` | wd1-replace |
| Funerary Naiskos of Demetria and Pamphile | site_type | `Monument` | `Funerary` | wd1-replace |
| Gallo-Roman Villa of Orbe-Boscéaz | geom | `0101000020E6100000CEF3B0EF24221A40060F4509C15B4740` | `SRID=4326;POINT(6.537073 46.74432)` | wd1-point |
| Gallo-Roman Villa of Orbe-Boscéaz | lat | `46.71682849761969` | `46.74432` | wd1-replace |
| Gallo-Roman Villa of Orbe-Boscéaz | lon | `6.533344025779071` | `6.537073` | wd1-replace |
| Gallo-Roman Villa of Orbe-Boscéaz | site_type | `Residence/villa/farmhouse` | `Villa` | wd1-replace |
| Geißkopf, Central Black Forest | site_type | `Earthwork` | `Military` | wd1-replace |
| Glauberg | period_name | `1500 - 500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Glauberg | period_start | `-1000` | `-4500` | wd1-replace |
| Glauberg | site_type | `Fortress/citadel` | `Fortification` | wd1-replace |
| Heiligenberg, Heidelberg | site_type | `Fortress/citadel` | `Fortification` | wd1-replace |
| Helenistik Mabed | source_url | `https://www.gidilmeli.com/Helenistik-mabet-kas/11839/1` | `https://kulturenvanteri.com/en/yer/antiphellos-helenistik-ma` | wd1-replace |
| Hollybush Hill | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Hollybush Hill | period_start | `-1500` | `-470` | wd1-replace |
| Hollybush Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Hollybush Hill | source_url | `https://en.wikipedia.org/wiki/Hollybush_Hill` | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord` | wd1-replace |
| Kbor Klib | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Kbor Klib | period_start | `-167` | `NULL` | wd1-clear |
| Kbor Klib | source_url | `https://www.lonelyplanet.com/tunisia/central-tunisia-1331880` | `https://es.wikipedia.org/wiki/Kbor_klib` | wd1-replace |
| Khao Sam Kaeo | geom | `0101000020E610000022A2B36A84CB584087C6A09201FD2440` | `SRID=4326;POINT(99.18208 10.52725)` | wd1-point |
| Khao Sam Kaeo | lat | `10.494152624250331` | `10.52725` | wd1-replace |
| Khao Sam Kaeo | lon | `99.17995708029096` | `99.18208` | wd1-replace |
| King's Castle, Wells | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| King's Castle, Wells | period_start | `-1000` | `NULL` | wd1-clear |
| King's Castle, Wells | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Legananny Dolmen | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Legananny Dolmen | period_start | `-4500` | `-3000` | wd1-replace |
| Litton Cheney | geom | `0101000020E61000000B78D72F2F1605C0071FA84E675B4940` | `SRID=4326;POINT(-2.630017 50.723587)` | wd1-point |
| Litton Cheney | lat | `50.714090187158995` | `50.723587` | wd1-replace |
| Litton Cheney | lon | `-2.635832189334001` | `-2.630017` | wd1-replace |
| Litton Cheney | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Litton Cheney | period_start | `-4500` | `-2200` | wd1-replace |
| Litton Cheney | site_type | `Stone circle` | `Timber circle` | wd1-replace |
| Litton Cheney | source_url | `https://en.wikipedia.org/wiki/Litton_Cheney` | `https://heritage.dorsetcouncil.gov.uk/Monument/MDO1430` | wd1-replace |
| Maa Palaeokastro | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Maa Palaeokastro | period_start | `-3000` | `NULL` | wd1-clear |
| Maiden Castle, North Yorkshire | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Maiden Castle, North Yorkshire | period_start | `-1500` | `NULL` | wd1-clear |
| Maiden Castle, North Yorkshire | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Makra Stoa | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Makra Stoa | period_start | `-1500` | `NULL` | wd1-clear |
| Makra Stoa | site_type | `Megalithic structures` | `Archaeological site` | wd1-replace |
| Mam Tor | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Mam Tor | source_url | `https://en.wikipedia.org/wiki/Mam_Tor` | `https://her.derbyshire.gov.uk/Monument/MDR2223` | wd1-replace |
| Mamai-Hora | geom | `0101000020E610000030883C809C2E4140FD5E5B434AB84740` | `SRID=4326;POINT(34.274 47.434)` | wd1-point |
| Mamai-Hora | lat | `47.43976633035161` | `47.434` | wd1-replace |
| Mamai-Hora | lon | `34.36415102916396` | `34.274` | wd1-replace |
| Mamai-Hora | period_name | `4500 - 3000 BC` | `< 4500 BC` | wd1-derive-period-name |
| Mamai-Hora | period_start | `-4000` | `-5655` | wd1-replace |
| Mamai-Hora | site_type | `Mound/tumulus` | `Cemetery` | wd1-replace |
| Megalithic Plaza - Callacpuma Archaeological Site | source_url | `https://archaeologyworldnews.com/4750-year-old-megalithic-st` | `https://www.uwyo.edu/news/2024/02/uw-anthropologists-researc` | wd1-replace |
| Menhirs of Sardinia | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Menhirs of Sardinia | period_start | `-4000` | `NULL` | wd1-clear |
| Menhirs of Sardinia | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Menhirs of Sardinia | source_url | `https://m.megalithic.co.uk/article.php?sid=32552` | `https://www.megalithic.co.uk/article.php?sid=32552` | wd1-replace |
| Merano | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Merano | period_start | `-3000` | `NULL` | wd1-clear |
| Merano | site_type | `Megalithic stones` | `City` | wd1-replace |
| Meroë East (Main)Necropolis | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Meroë East (Main)Necropolis | period_start | `-800` | `-300` | wd1-replace |
| Meroë East (Main)Necropolis | source_url | `www.travelwithbrothers.com/sudan-the-royal-necropolis-of-mer` | `https://en.wikipedia.org/wiki/Pyramids_of_Mero%C3%AB` | wd1-replace |
| Milefortlet - Hadrians Wall | site_type | `Fortification` | `Fort` | wd1-replace |
| Milefortlet - Hadrians Wall | source_url | `NULL` | `https://en.wikipedia.org/wiki/Milecastle` | wd1-replace |
| Milton Keynes Hoard | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Mitrou | geom | `0101000020E6100000575CEF724A4637404A9666D1964C4340` | `SRID=4326;POINT(23.124344 38.636176)` | wd1-point |
| Mitrou | lat | `38.59835259923109` | `38.636176` | wd1-replace |
| Mitrou | lon | `23.274573501050636` | `23.124344` | wd1-replace |
| Mitrou | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Mitrou | period_start | `-5000` | `NULL` | wd1-clear |
| Nuragic Complex Romanzesu | period_name | `4500 - 3000 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Nuragic Complex Romanzesu | period_start | `-4500` | `-1500` | wd1-replace |
| Nuragic Complex Romanzesu | site_type | `City/town/settlement` | `Sanctuary` | wd1-replace |
| Nuragic Village of Tiscali | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Paraccra Archaeological Site | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Paraccra Archaeological Site | period_start | `1400` | `NULL` | wd1-clear |
| Paraccra Archaeological Site | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Persepolis | site_type | `Temple complex` | `Palace` | wd1-replace |
| Pirca Pirca, La Libertad | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Pirca Pirca, La Libertad | period_start | `-800` | `NULL` | wd1-clear |
| Pirca Pirca, La Libertad | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Positano | site_type | `Residence/villa/farmhouse` | `Villa` | wd1-replace |
| Positano | source_url | `https://en.wikipedia.org/wiki/Positano` | `https://it.wikipedia.org/wiki/Museo_archeologico_romano_Sant` | wd1-replace |
| Prassa | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Prassa | period_start | `-4500` | `NULL` | wd1-clear |
| Prassa | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Prince of the Lilies | geom | `0101000020E61000001FC8B7E51023394011EDCFE85BAB4140` | `SRID=4326;POINT(25.163373 35.297953)` | wd1-point |
| Prince of the Lilies | lat | `35.33874235298766` | `35.297953` | wd1-replace |
| Prince of the Lilies | lon | `25.13697658287867` | `25.163373` | wd1-replace |
| Prince of the Lilies | site_type | `Rock art` | `NULL` | wd1-clear |
| Pukarani, Peru | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pukarani, Peru | period_start | `1` | `NULL` | wd1-clear |
| Pukarani, Peru | site_type | `City/town/settlement` | `Fortress` | wd1-replace |
| Pukarani, Peru | source_url | `https://en.wikipedia.org/wiki/Pukarani_(Peru)` | `https://www.elizabetharkush.com/past-projects/pucarani` | wd1-replace |
| Putanges-le-Lac | geom | `0101000020E6100000C5EF1C3779BDCFBFCEC23BE7B0614840` | `SRID=4326;POINT(-0.361475 48.772792)` | wd1-point |
| Putanges-le-Lac | lat | `48.76321115892425` | `48.772792` | wd1-replace |
| Putanges-le-Lac | lon | `-0.24796977225366681` | `-0.361475` | wd1-replace |
| Putanges-le-Lac | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Putanges-le-Lac | period_start | `-4500` | `NULL` | wd1-clear |
| Putanges-le-Lac | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Putanges-le-Lac | source_url | `https://en.wikipedia.org/wiki/Putanges-le-Lac` | `https://fr.wikipedia.org/wiki/Droite_Pierre` | wd1-replace |
| Puy Foradado Dam | site_type | `Megalithic structures` | `Reservoir/aqueduct/canal` | wd1-replace |
| Pyre of Heracles | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Pyre of Heracles | period_start | `-500` | `-700` | wd1-replace |
| Ravenglass Roman Bath House | site_type | `Residence/villa/farmhouse` | `Bath` | wd1-replace |
| Regional Museum of Ancash | period_name | `500 BC - 1 AD` | `1500+ AD` | wd1-derive-period-name |
| Regional Museum of Ancash | period_start | `-500` | `1935` | wd1-replace |
| Regional Museum of Ancash | source_url | `https://www.lonelyplanet.com/peru/huaraz-and-the-cordilleras` | `https://es.wikipedia.org/wiki/Museo_Arqueol%C3%B3gico_de_%C3` | wd1-replace |
| Rehman Dheri | geom | `0101000020E6100000F6F38223A5B851400F2E100C34F23F40` | `SRID=4326;POINT(70.818333 31.996667)` | wd1-point |
| Rehman Dheri | lat | `31.946106676054168` | `31.996667` | wd1-replace |
| Rehman Dheri | lon | `70.88507926739098` | `70.818333` | wd1-replace |
| Roman Fish Salting Factory, Algeciras | site_type | `Ruin` | `Archaeological site` | wd1-replace |
| Sallachy Broch | geom | `0101000020E6100000FB1231A9B09911C084F487CB99024D40` | `SRID=4326;POINT(-4.45981 58.048288)` | wd1-point |
| Sallachy Broch | lat | `58.02031845224795` | `58.048288` | wd1-replace |
| Sallachy Broch | lon | `-4.400087970371483` | `-4.45981` | wd1-replace |
| Sallachy Broch | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Sallachy Broch | period_start | `-1500` | `NULL` | wd1-clear |
| Sallachy Broch | source_url | `https://en.wikipedia.org/wiki/Lairg` | `https://de.wikipedia.org/wiki/Broch_von_Sallachy` | wd1-replace |
| Sanghao Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Sanghao Cave | period_start | `-500` | `NULL` | wd1-clear |
| Sfireh Roman Temple | source_url | `www.wanderleb.com/blog/sfireh-temples` | `https://de.wikipedia.org/wiki/Hosn_Sfiri` | wd1-replace |
| Shengavit Settlement | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Shengavit Settlement | period_start | `-3500` | `-2900` | wd1-replace |
| Sialkot Fort | geom | `0101000020E6100000FA2B2FF534A352405191B44995424040` | `SRID=4326;POINT(74.5419 32.4939)` | wd1-point |
| Sialkot Fort | lat | `32.52018090550212` | `32.4939` | wd1-replace |
| Sialkot Fort | lon | `74.55010728460903` | `74.5419` | wd1-replace |
| Sialkot Fort | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Sialkot Fort | period_start | `1` | `NULL` | wd1-clear |
| Siega Verde | source_url | `https://en.wikipedia.org/wiki/Siega_Verde` | `https://es.wikipedia.org/wiki/Siega_Verde` | wd1-replace |
| Sollentuna Socken | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Sollentuna Socken | period_start | `-4500` | `NULL` | wd1-clear |
| Sollentuna Socken | site_type | `Mound/tumulus` | `NULL` | wd1-clear |
| Sollentuna Socken | source_url | `https://en.wikipedia.org/wiki/Sollentuna_socken` | `NULL` | wd1-clear |
| Storgosia | geom | `0101000020E610000011215F16E29D3840F09237B25AB54540` | `SRID=4326;POINT(24.628933 43.383008)` | wd1-point |
| Storgosia | lat | `43.41683032716344` | `43.383008` | wd1-replace |
| Storgosia | lon | `24.616731069779295` | `24.628933` | wd1-replace |
| Taksai Kurgans | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Taksai Kurgans | period_start | `-1500` | `-500` | wd1-replace |
| Temple of Dedun | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Temple of Dedun | period_start | `-3000` | `NULL` | wd1-clear |
| Temple of Dedun | site_type | `Temple complex` | `Temple` | wd1-replace |
| Temple of Dedun | source_url | `https://en.wikipedia.org/wiki/Dedun` | `https://www.megalithic.co.uk/article.php?sid=6336037` | wd1-replace |
| Templo de la Luna | source_url | `https://en.wikipedia.org/wiki/Temple_of_the_Moon_(Peru)` | `https://en.wikipedia.org/wiki/Amaru_Marka_Wasi` | wd1-replace |
| Teotihuacan | geom | `0101000020E610000043F262E4C8B758C02B29349841B03340` | `SRID=4326;POINT(-98.84389 19.6925)` | wd1-point |
| Teotihuacan | lat | `19.688500893339704` | `19.6925` | wd1-replace |
| Teotihuacan | lon | `-98.87163648283699` | `-98.84389` | wd1-replace |
| Teotihuacan | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Teotihuacan | site_type | `Pyramid complex` | `City/town/settlement, Pyramid complex` | wd1-replace |
| The Poind and his Man | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| The Poind and his Man | period_start | `-4500` | `NULL` | wd1-clear |
| The Wolseong Belt | geom | `0101000020E61000001C11DDC83F276040F2EA5AE308E54140` | `SRID=4326;POINT(129.223337 35.831314)` | wd1-point |
| The Wolseong Belt | lat | `35.78933374347061` | `35.831314` | wd1-replace |
| The Wolseong Belt | lon | `129.2265362088882` | `129.223337` | wd1-replace |
| The Wolseong Belt | site_type | `Fortress/citadel` | `Palace` | wd1-replace |
| The Wolseong Belt | source_url | `https://en.wikipedia.org/wiki/Gyeongju_Historic_Areas` | `https://en.wikipedia.org/wiki/Wolseong` | wd1-replace |
| Tiryns | period_name | `4500 - 3000 BC` | `< 4500 BC` | wd1-derive-period-name |
| Tiryns | period_start | `-4000` | `-5000` | wd1-replace |
| Tlos Ruins | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Tlos Ruins | period_start | `-2000` | `-5000` | wd1-replace |
| Tlos Ruins | site_type | `Megalithic stones` | `City` | wd1-replace |
| Trajan Arch | source_url | `www.historyhit.com/locations/trajan-arch-of-merida/` | `https://es.wikipedia.org/wiki/Arco_de_Trajano_(M%C3%A9rida)` | wd1-replace |
| Treasury of the Massaliots, Delphi | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Trevelgue Head | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Trevelgue Head | period_start | `-4000` | `NULL` | wd1-clear |
| Trevelgue Head | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Trojanov Grad | geom | `0101000020E61000009845E1E37D7E334003F83271354D4640` | `SRID=4326;POINT(19.52361 44.58833)` | wd1-point |
| Trojanov Grad | lat | `44.60319342602454` | `44.58833` | wd1-replace |
| Trojanov Grad | lon | `19.494108431337366` | `19.52361` | wd1-replace |
| Trojanov Grad | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Trojanov Grad | period_start | `1` | `-1000` | wd1-replace |
| Túcume | period_name | `500 - 1000 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Túcume | period_start | `500` | `1000` | wd1-replace |
| Vasculaghju | geom | `0101000020E6100000CE5097EAA45422407B9513C322464540` | `SRID=4326;POINT(9.165248 41.547637)` | wd1-point |
| Vasculaghju | lat | `42.54793585258718` | `41.547637` | wd1-replace |
| Vasculaghju | lon | `9.165320712062023` | `9.165248` | wd1-replace |
| Vasculaghju | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Vasculaghju | period_start | `-5000` | `NULL` | wd1-clear |
| Vasculaghju | site_type | `Archaeological site` | `Necropolis` | wd1-replace |
| Vasculaghju | source_url | `https://en.wikipedia.org/wiki/Vasculaghju` | `https://co.wikipedia.org/wiki/Vasculaghju` | wd1-replace |
| Wroxeter Stone | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Wroxeter Stone | period_start | `1` | `501` | wd1-replace |
| Yerokambos | geom | `0101000020E6100000CDBE5B79B91539400A5575BC98794140` | `SRID=4326;POINT(24.901333 34.936778)` | wd1-point |
| Yerokambos | lat | `34.94997363785849` | `34.936778` | wd1-replace |
| Yerokambos | lon | `25.0848613594997` | `24.901333` | wd1-replace |
| Yerokambos | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Yerokambos | period_start | `-4000` | `NULL` | wd1-clear |
| Yerokambos | site_type | `Cemetery` | `Tomb` | wd1-replace |
| Zaldapa | period_name | `1500 - 500 BC` | `1 - 500 AD` | wd1-derive-period-name |
| Zaldapa | period_start | `-800` | `301` | wd1-replace |
| Zaldapa | site_type | `Fortress/citadel` | `City` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Menhirs of Sardinia | lat | `coordinates-unresolved` | The entry's point and source are the Brentoni stone row of three menhirs near Villa Sant'Antonio; only the Megalithic Po |
| Baba-Dervish Settlement | lat | `coordinates-unresolved` | The stored point is the centre of Qazax town (41.0925, 45.3656 per Geodatos), not the site. The settlement lies on the l |
| Milefortlet - Hadrians Wall | lat | `coordinates-unresolved` | The entry is the whole class of milefortlets - the small forts that continued Hadrian's Wall down the Cumbrian coast fro |
| Pozzuoli | lat | `country-changes` | the new point lies in [], the site says Italy |
| Wroxeter Stone | lat | `coordinates-unresolved` | The stone was ploughed up in 1967 at the eastern defences of the Roman town (RIB 3145 gives only the grid reference SJ 5 |
| Pirca Pirca, La Libertad | lat | `coordinates-unresolved` | Only one source family prints a quotable point for the site: English Wikipedia/Wikidata give 7°02′40″S 77°45′36″W, which |
| Chukimarka | lat | `coordinates-unresolved` | Only the OpenStreetMap node 'Chukimarka' (historic=monument, -13.5038, -71.9640, about 170 m from the stored point) and  |
| Paraccra Archaeological Site | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point for Paraccra (15°27′32.4″S 71°27′47.5″W, 26 m from the stored point);  |
| Amazmaz | lat | `coordinates-unresolved` | The only published point (19.71667, -13.43333, printed by Wikipedia, Wikidata and Archaeolist) is GeoNames' point for th |
| Karpasia - Town | lat | `country-changes` | the new point lies in [], the site says Cyprus |
| Sanghao Cave | lat | `coordinates-unresolved` | The stored point (copied from English Wikipedia) lies in Peshawar, about 75 km from the cave: Dani's 1964 excavation rep |
| Megalithic Plaza - Callacpuma Archaeological Site | lat | `coordinates-unresolved` | Only the Megalithic Portal prints a point for the Callacpuma plaza (7.17284S 78.44123W, about 1.03 km from the stored po |
| Prassa | lat | `coordinates-unresolved` | Only Wikidata (35.3069, 25.1918) and pages copying it give a point for the Minoan houses at Prassa; OpenStreetMap, Pleia |
| Milton Keynes Hoard | lat | `coordinates-unresolved` | The hoard was found in a field at Monkston Park, Milton Keynes, but no source publishes the find spot's point: the Wikip |
| Helenistik Mabed | lat | `coordinates-unresolved` | The Hellenistic temple (Antiphellos Helenistik Mabet) in the centre of Kaş is placed about 50 m from the stored point by |
| Cocoraque Butte Archaeological District | lat | `coordinates-unresolved` | The NRHP lists the district as 'Address Restricted' and the Wikidata item of the district (Q16949635) has no coordinates |
| Merano | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://latitude.to/map/it/italy/cities/merano; quote not found: https:/ |
| Sollentuna Socken | lat | `coordinates-unresolved` | Sollentuna socken is a former parish of about 50 km² (English and Swedish Wikipedia), not one monument: it holds Bronze  |
| Double Arches Pit | lat | `coordinates-unresolved` | Wikipedia (51.953, -0.641) and Wikidata (51.953864, -0.638669) both put the pit within 0.2 km of the stored point, but t |
| Taksai Kurgans | lat | `coordinates-unresolved` | Only English Wikipedia gives a point for the kurgans (51.196575, 52.176884, 0.5 km from the stored point, and consistent |
| Crikvenica | lat | `country-changes` | the new point lies in [], the site says Croatia |
| Sfireh Roman Temple | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://vici.org/vici/27659/; quote not found: https://vici.org/vici/276 |
| Pukarani, Peru | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point (15°14′28″S 70°16′40″W, 20 m from the stored point); the OpenStreetMap |
| Flevum | lat | `country-changes` | the new point lies in ['Netherlands'], the site says Germany |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s010-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s010 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
