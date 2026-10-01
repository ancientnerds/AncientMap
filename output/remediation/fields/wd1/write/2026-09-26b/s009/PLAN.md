# WD1 fields-wd1-2026-09-26b-s009: plan

Built 2026-09-30T06:03:49+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s009`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s009:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 264 |
| sites_written | 98 |
| refused | 25 |
| cells:geom | 21 |
| cells:lat | 21 |
| cells:lon | 21 |
| cells:period_name | 56 |
| cells:period_start | 56 |
| cells:site_type | 55 |
| cells:source_url | 34 |
| refused:coordinates-unresolved | 21 |
| refused:country-changes | 4 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Abu Salabikh | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Abu Salabikh | period_start | `-3000` | `-3900` | wd1-replace |
| Acontisma | geom | `0101000020E6100000976D4B161F87384041CDF344D37C4440` | `SRID=4326;POINT(24.527672 40.965324)` | wd1-point |
| Acontisma | lat | `40.97519742874511` | `40.965324` | wd1-replace |
| Acontisma | lon | `24.527818101325092` | `24.527672` | wd1-replace |
| Alcalá de Henares | geom | `0101000020E6100000E001EE93F4EE0AC0F391D4BEBF3B4440` | `SRID=4326;POINT(-3.364305 40.481815)` | wd1-point |
| Alcalá de Henares | lat | `40.46678910617256` | `40.481815` | wd1-replace |
| Alcalá de Henares | lon | `-3.366677432728679` | `-3.364305` | wd1-replace |
| Allt yr Esgair | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Allt yr Esgair | period_start | `-1500` | `NULL` | wd1-clear |
| Allt yr Esgair | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Allt yr Esgair | source_url | `https://en.wikipedia.org/wiki/Allt_yr_Esgair` | `https://coflein.gov.uk/en/sites/92158` | wd1-replace |
| Ancient Eleon | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Ancient Eleon | period_start | `-1500` | `-1700` | wd1-replace |
| Ancient Eleon | site_type | `Polygonal masonry` | `Settlement` | wd1-replace |
| Anim Synagogue | site_type | `Temple complex` | `Religious` | wd1-replace |
| Archaeological site Puma Punku | site_type | `Megalithic stones` | `Temple` | wd1-replace |
| Argentovaria | geom | `0101000020E61000001D6B0556E02C1E400099F7DB58054840` | `SRID=4326;POINT(7.5386 48.0601)` | wd1-point |
| Argentovaria | lat | `48.041774269006055` | `48.0601` | wd1-replace |
| Argentovaria | lon | `7.543824524002756` | `7.5386` | wd1-replace |
| Ashley, Northamptonshire | source_url | `https://en.wikipedia.org/wiki/Ashley,_Northamptonshire` | `https://her.northamptonshire.gov.uk/Monument/MNN1608` | wd1-replace |
| Avdat National Park | site_type | `Temple complex` | `City` | wd1-replace |
| Aynuna | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Aynuna | period_start | `1` | `-100` | wd1-replace |
| Bakka Roman Temple | source_url | `https://en.wikipedia.org/wiki/Bakka,_Lebanon` | `https://archiqoo.com/locations/bakka_temple.php` | wd1-replace |
| Baltic Sea Anomaly | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Baltic Sea Anomaly | period_start | `1` | `NULL` | wd1-clear |
| Baltic Sea Anomaly | site_type | `Underwater structures` | `Natural feature` | wd1-replace |
| Ban Chiang | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Ban Chiang | period_start | `-3000` | `-1500` | wd1-replace |
| Borough Hill | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Borough Hill | period_start | `-3000` | `NULL` | wd1-clear |
| Borough Hill | site_type | `Barrow` | `Fort` | wd1-replace |
| Borough Hill | source_url | `https://en.wikipedia.org/wiki/Borough_Hill` | `https://her.northamptonshire.gov.uk/Monument/MNN3603` | wd1-replace |
| Bull-Leaping Fresco | geom | `0101000020E61000008BC8B77D0F23394011EDCFE85BAB4140` | `SRID=4326;POINT(25.16306 35.29806)` | wd1-point |
| Bull-Leaping Fresco | lat | `35.33874235298766` | `35.29806` | wd1-replace |
| Bull-Leaping Fresco | lon | `25.136955125206935` | `25.16306` | wd1-replace |
| Bull-Leaping Fresco | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Bull-Leaping Fresco | period_start | `-3000` | `-1450` | wd1-replace |
| Bull-Leaping Fresco | site_type | `Rock relief/carving` | `NULL` | wd1-clear |
| Caesarea Philippi | site_type | `Temple complex` | `City` | wd1-replace |
| Camulodunum | site_type | `City/town/settlement` | `City` | wd1-replace |
| Careyeros Hill | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Careyeros Hill | period_start | `-500` | `NULL` | wd1-clear |
| Careyeros Hill | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Careyeros Hill | source_url | `https://www.megalithic.co.uk/article.php?sid=18241` | `https://www.megalithic.co.uk/Careyeros-Hill-18241` | wd1-replace |
| Castle Hill, Huddersfield | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Castle Hill, Huddersfield | period_start | `-1500` | `-2000` | wd1-replace |
| Castle Hill, Huddersfield | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Castro de Achadizo | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Castro of Santa Trega | geom | `0101000020E6100000B4BC5EF018C021C0EEBAFF8D97F34440` | `SRID=4326;POINT(-8.8698 41.8927)` | wd1-point |
| Castro of Santa Trega | lat | `41.90306258189035` | `41.8927` | wd1-replace |
| Castro of Santa Trega | lon | `-8.875190269054976` | `-8.8698` | wd1-replace |
| Castro of Santa Trega | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Cohaw | geom | `0101000020E6100000373B60C32A331CC0F1DDC172CE0C4B40` | `SRID=4326;POINT(-7.018076 54.057253)` | wd1-point |
| Cohaw | lat | `54.100050301229096` | `54.057253` | wd1-replace |
| Cohaw | lon | `-7.049967816112988` | `-7.018076` | wd1-replace |
| Cohaw | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Cohaw | period_start | `-4000` | `NULL` | wd1-clear |
| Didyma | site_type | `Megalithic stones` | `Sanctuary` | wd1-replace |
| Dun Cuier | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dun Cuier | period_start | `1` | `NULL` | wd1-clear |
| Dun Cuier | source_url | `https://en.wikipedia.org/wiki/Iron_Age` | `https://de.wikipedia.org/wiki/Dun_Cuier` | wd1-replace |
| Eastern Gate of Philippopolis | site_type | `Gate/archway/bridge` | `Gate` | wd1-replace |
| El Argar | geom | `0101000020E6100000927DAC5B29F7F8BF22F1829773E14240` | `SRID=4326;POINT(-1.91146 37.24868)` | wd1-point |
| El Argar | lat | `37.76134008306168` | `37.24868` | wd1-replace |
| El Argar | lon | `-1.560342176533457` | `-1.91146` | wd1-replace |
| Erdeven | geom | `0101000020E6100000ABF935BA225509C0B3C3459E14D14740` | `SRID=4326;POINT(-3.1481 47.6347)` | wd1-point |
| Erdeven | lat | `47.63344171911685` | `47.6347` | wd1-replace |
| Erdeven | lon | `-3.1665701434823936` | `-3.1481` | wd1-replace |
| Erdeven | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Erdeven | period_start | `-4500` | `NULL` | wd1-clear |
| Erdeven | source_url | `https://en.wikipedia.org/wiki/Erdeven` | `https://en.wikipedia.org/wiki/Kerz%C3%A9rho` | wd1-replace |
| Fa'ahia | period_name | `500 - 1000 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Fa'ahia | period_start | `500` | `1050` | wd1-replace |
| Fa'ahia | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Fa'ahia | source_url | `https://en.wikipedia.org/wiki/Fa%27ahia` | `https://en.wikipedia.org/wiki/Fa%CA%BBahia` | wd1-replace |
| Feddersen Wierde | geom | `0101000020E610000080AD74B7C02A21404F996F3167C64A40` | `SRID=4326;POINT(8.55 53.661111)` | wd1-point |
| Feddersen Wierde | lat | `53.55002420376933` | `53.661111` | wd1-replace |
| Feddersen Wierde | lon | `8.583501561158073` | `8.55` | wd1-replace |
| Feddersen Wierde | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Feddersen Wierde | period_start | `1` | `-100` | wd1-replace |
| Feddersen Wierde | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Flag Fen | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Flag Fen | period_start | `-3000` | `-1365` | wd1-replace |
| Fournou Korifi | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Fournou Korifi | period_start | `-4500` | `-2600` | wd1-replace |
| Fournou Korifi | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Glebe Cairn, Kilmartin Glen | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Glebe Cairn, Kilmartin Glen | period_start | `-4000` | `-1700` | wd1-replace |
| Glebe Cairn, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://nl.wikipedia.org/wiki/Glebe_Cairn` | wd1-replace |
| Golem Grad | site_type | `Church/cathedral` | `Settlement` | wd1-replace |
| Golem Grad | source_url | `https://en.wikipedia.org/wiki/Golem_Grad` | `https://mk.wikipedia.org/wiki/%D0%93%D0%BE%D0%BB%D0%B5%D0%BC` | wd1-replace |
| Gran Pajatén | period_name | `500 - 1000 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Gran Pajatén | period_start | `500` | `-200` | wd1-replace |
| Gulluk Mountain Termessos National Park | geom | `0101000020E6100000BCC3983DEB833E40906392E5DE814240` | `SRID=4326;POINT(30.464722 36.9825)` | wd1-point |
| Gulluk Mountain Termessos National Park | lat | `37.01461476943871` | `36.9825` | wd1-replace |
| Gulluk Mountain Termessos National Park | lon | `30.515308236881296` | `30.464722` | wd1-replace |
| Gulluk Mountain Termessos National Park | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Gulluk Mountain Termessos National Park | period_start | `-700` | `-333` | wd1-replace |
| Gulluk Mountain Termessos National Park | source_url | `https://en.wikipedia.org/wiki/Mount_G%C3%BCll%C3%BCk-Termess` | `https://en.wikipedia.org/wiki/Termessos` | wd1-replace |
| Gyeongju Historic Areas | site_type | `Temple complex` | `Heritage site` | wd1-replace |
| Ham Hill, Somerset | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Ham Hill, Somerset | period_start | `-500` | `-800` | wd1-replace |
| Ham Hill, Somerset | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Ham Hill, Somerset | source_url | `https://en.wikipedia.org/wiki/Ham_Hill,_Somerset` | `https://en.wikipedia.org/wiki/Ham_Hill_Hillfort` | wd1-replace |
| Intipanawin | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Intipanawin | period_start | `1` | `NULL` | wd1-clear |
| Jabal al-Baidain | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Jabal al-Baidain | period_start | `-1500` | `NULL` | wd1-clear |
| Jabal al-Baidain | site_type | `Petroglyphs` | `Archaeological site` | wd1-replace |
| Jerwan | site_type | `City/town/settlement` | `Aqueduct` | wd1-replace |
| Kalapodi | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Kalapodi | period_start | `-2000` | `-1400` | wd1-replace |
| Kalapodi | site_type | `Temple` | `Sanctuary` | wd1-replace |
| Kalapodi | source_url | `https://en.wikipedia.org/wiki/Kalapodi` | `https://www.dainst.org/en/research/projects/kalapodi-ein-pho` | wd1-replace |
| Kilclooney More | site_type | `Megalithic structures` | `Dolmen` | wd1-replace |
| Kilclooney More | source_url | `https://en.wikipedia.org/wiki/Kilclooney_More` | `https://de.wikipedia.org/wiki/Kilclooney_More_1` | wd1-replace |
| Killerton | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Killerton | source_url | `https://en.wikipedia.org/wiki/Killerton` | `https://en.wikipedia.org/wiki/Dolbury` | wd1-replace |
| Kinichná | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kinichná | period_start | `1` | `NULL` | wd1-clear |
| Kinichná | source_url | `https://lugares.inah.gob.mx/es/zonas-arqueologicas/zonas/179` | `https://es.wikipedia.org/wiki/Kinichn%C3%A1` | wd1-replace |
| Kokkinokremmos | source_url | `https://en.wikipedia.org/wiki/Kokkinokremmos` | `https://en.wikipedia.org/wiki/Pyla-Kokkinokremos` | wd1-replace |
| Kovachevsko kale | site_type | `City/town/settlement` | `Fortress` | wd1-replace |
| Krapina Neanderthal Site | site_type | `Archaeological site` | `Cave` | wd1-replace |
| Kuntuyuq | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kuntuyuq | period_start | `300` | `NULL` | wd1-clear |
| Ladle Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ladle Hill | period_start | `-1500` | `NULL` | wd1-clear |
| Ladle Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Lagartero | source_url | `https://lugares.inah.gob.mx/en/zonas-arqueologicas/zonas/168` | `https://en.wikipedia.org/wiki/El_Lagartero` | wd1-replace |
| Langdale Axe Industry | geom | `0101000020E6100000FEE0F0EEFB8208C0DB78D7903A394B40` | `SRID=4326;POINT(-3.121304 54.454977)` | wd1-point |
| Langdale Axe Industry | lat | `54.44709978600596` | `54.454977` | wd1-replace |
| Langdale Axe Industry | lon | `-3.063957087255516` | `-3.121304` | wd1-replace |
| Lapa de Gargantáns | geom | `0101000020E61000008AC8B5699C1921C030A931946B464540` | `SRID=4326;POINT(-8.583055 42.569722)` | wd1-point |
| Lapa de Gargantáns | lat | `42.55015804695938` | `42.569722` | wd1-replace |
| Lapa de Gargantáns | lon | `-8.550021460953094` | `-8.583055` | wd1-replace |
| Las Bóvedas - Thermae | geom | `0101000020E6100000C74671620BF613C08C1112423E3E4240` | `SRID=4326;POINT(-4.993653 36.468053)` | wd1-point |
| Las Bóvedas - Thermae | lat | `36.48627496607068` | `36.468053` | wd1-replace |
| Las Bóvedas - Thermae | lon | `-4.9902778035772775` | `-4.993653` | wd1-replace |
| Lygourio | geom | `0101000020E61000003D39EA3B89083740EE106117D2CC4240` | `SRID=4326;POINT(23.03611 37.61444)` | wd1-point |
| Lygourio | lat | `37.60016147841985` | `37.61444` | wd1-replace |
| Lygourio | lon | `23.033344025310033` | `23.03611` | wd1-replace |
| Lygourio | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Lygourio | period_start | `-500` | `NULL` | wd1-clear |
| Markahirka | site_type | `Rock art` | `Necropolis/tombs complex` | wd1-replace |
| Meydancık Castle | geom | `0101000020E610000065A80C5AFCB64040E10027016E244240` | `SRID=4326;POINT(33.43975 36.27284)` | wd1-point |
| Meydancık Castle | lat | `36.28460707096543` | `36.27284` | wd1-replace |
| Meydancık Castle | lon | `33.4295761644178` | `33.43975` | wd1-replace |
| Micheldever Wood | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Micheldever Wood | period_start | `-3000` | `NULL` | wd1-clear |
| Nazca Lines | source_url | `https://www.history.com/topics/south-america/nazca-lines` | `https://en.wikipedia.org/wiki/Nazca_lines` | wd1-replace |
| Nebi Samuel National Park | site_type | `Temple complex` | `Tomb` | wd1-replace |
| Nekromanteion of Acheron | site_type | `Necropolis/tombs complex` | `Sanctuary` | wd1-replace |
| Nether Largie Mid Cairn, Kilmartin Glen | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Nether Largie Mid Cairn, Kilmartin Glen | period_start | `-4000` | `-2000` | wd1-replace |
| Nether Largie Mid Cairn, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://www.historicenvironment.scot/visit/all/kilmartin-gle` | wd1-replace |
| Nubian Pyramids | geom | `0101000020E610000051FED2757DDD4040D7CAAF5FF5EE3040` | `SRID=4326;POINT(33.74861 16.9375)` | wd1-point |
| Nubian Pyramids | lat | `16.93343160669141` | `16.9375` | wd1-replace |
| Nubian Pyramids | lon | `33.73039124300397` | `33.74861` | wd1-replace |
| Nubian Pyramids | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Nubian Pyramids | period_start | `-500` | `-751` | wd1-replace |
| Old Horom | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Old Horom | period_start | `-3000` | `NULL` | wd1-clear |
| Old Horom | source_url | `https://en.wikipedia.org/wiki/Horom,_Armenia` | `https://en.wikipedia.org/wiki/Horom_Citadel` | wd1-replace |
| Pallanum - Mura Megalitiche (Paladine) di Pallanum | source_url | `https://en.wikipedia.org/wiki/Pallanum` | `https://it.wikipedia.org/wiki/Pallanum` | wd1-replace |
| Phu Phra Bat Historical Park | geom | `0101000020E610000025F0DDB1CF9759407238D6FC71B73140` | `SRID=4326;POINT(102.356278 17.731056)` | wd1-point |
| Phu Phra Bat Historical Park | lat | `17.71658306341164` | `17.731056` | wd1-replace |
| Phu Phra Bat Historical Park | lon | `102.37205168412818` | `102.356278` | wd1-replace |
| Phu Phra Bat Historical Park | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Phu Phra Bat Historical Park | period_start | `-4500` | `NULL` | wd1-clear |
| Porta Nord Acropoli | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Porta Nord Acropoli | period_start | `-1500` | `-409` | wd1-replace |
| Porta Nord Acropoli | site_type | `Temple complex` | `Gate` | wd1-replace |
| Porta Nord Acropoli | source_url | `https://en.wikipedia.org/wiki/Selinunte` | `https://www.selinunte.net/le_fortificazioni.htm` | wd1-replace |
| Pukara, Vilcas Huamán | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Pukara, Vilcas Huamán | period_start | `1000` | `NULL` | wd1-clear |
| Pukara, Vilcas Huamán | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Pyongyang Castle | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Pyongyang Castle | period_start | `1` | `552` | wd1-replace |
| Pyongyang Castle | site_type | `Castle/palace` | `Fortress` | wd1-replace |
| Quiahuiztlan | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Quiahuiztlan | period_start | `1` | `800` | wd1-replace |
| Quiahuiztlan | site_type | `Necropolis/tombs complex` | `City/town/settlement` | wd1-replace |
| Ri Cruin Cairn, Kilmartin Glen | geom | `0101000020E610000067B3AE5DA4F215C06BE4D3E31D114C40` | `SRID=4326;POINT(-5.499583 56.117083)` | wd1-point |
| Ri Cruin Cairn, Kilmartin Glen | lat | `56.133724668944375` | `56.117083` | wd1-replace |
| Ri Cruin Cairn, Kilmartin Glen | lon | `-5.486955131328478` | `-5.499583` | wd1-replace |
| Ri Cruin Cairn, Kilmartin Glen | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Ri Cruin Cairn, Kilmartin Glen | period_start | `-500` | `-2200` | wd1-replace |
| Ri Cruin Cairn, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://fr.wikipedia.org/wiki/Cairn_de_Ri_Cruin` | wd1-replace |
| Richmond Park | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Richmond Park | period_start | `-1500` | `NULL` | wd1-clear |
| Rocha da Mina | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Rocha da Mina | period_start | `-500` | `NULL` | wd1-clear |
| Rocha da Mina | site_type | `Megalithic structures` | `Sanctuary` | wd1-replace |
| Rocha da Mina | source_url | `www.megalithic.co.uk/article.php?sid=37238` | `https://arqueologia.patrimoniocultural.pt/index.php?sid=siti` | wd1-replace |
| Rock Shelter of Solhapa | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Rock Shelter of Solhapa | period_start | `-4000` | `NULL` | wd1-clear |
| Rock Shelter of Solhapa | site_type | `Rock relief/carving` | `Rock art` | wd1-replace |
| Ruins of Ténès | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ruins of Ténès | period_start | `-1500` | `NULL` | wd1-clear |
| Ruins of Ténès | site_type | `Necropolis/tombs complex` | `City` | wd1-replace |
| Ruins of Ténès | source_url | `https://en.wikipedia.org/wiki/T%C3%A9n%C3%A8s` | `https://en.wikipedia.org/wiki/Cartennae` | wd1-replace |
| Salamgarh | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Salamgarh | period_start | `-500` | `NULL` | wd1-clear |
| Salamgarh | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Situs Megalit Tebing Tinggi | source_url | `https://kebudayaan-kemdikbud-go-id.translate.goog/bpcbjambi/` | `https://medialampung.disway.id/seni-dan-budaya/read/699757/s` | wd1-replace |
| Slate Hill Settlement | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Slate Hill Settlement | period_start | `-1000` | `NULL` | wd1-clear |
| Slate Hill Settlement | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Stanwick Iron Age Fortifications | site_type | `City/town/settlement` | `Fortification` | wd1-replace |
| Stoa of the Athenians | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Stoa of the Athenians | period_start | `-1500` | `-478` | wd1-replace |
| Stoa of the Athenians | site_type | `Polygonal masonry` | `Monument` | wd1-replace |
| Stockland Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Stockland Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Stockland Castle | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Stone Circles at Odry | site_type | `Megalithic stones` | `Stone circle` | wd1-replace |
| Stone Circles at Odry | source_url | `https://www3.astronomicalheritage.net/index.php/show-entity?` | `https://pl.wikipedia.org/wiki/Odry_(cmentarzysko)` | wd1-replace |
| T'akaq | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| T'akaq | period_start | `1` | `NULL` | wd1-clear |
| T'akaq | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Tauriana | geom | `0101000020E6100000E83915CB31B32F400E064672F42E4340` | `SRID=4326;POINT(15.86624 38.39415)` | wd1-point |
| Tauriana | lat | `38.36683491152881` | `38.39415` | wd1-replace |
| Tauriana | lon | `15.84998926767453` | `15.86624` | wd1-replace |
| Tayma Stones | geom | `0101000020E610000048691EFECEAF02406916E2213F6E4840` | `SRID=4326;POINT(38.54389 27.62972)` | wd1-point |
| Tayma Stones | lat | `48.861301646608645` | `27.62972` | wd1-replace |
| Tayma Stones | lon | `2.335844025900915` | `38.54389` | wd1-replace |
| Tayma Stones | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Tayma Stones | period_start | `-1500` | `-500` | wd1-replace |
| Tayma Stones | site_type | `Rock relief/carving` | `Inscription` | wd1-replace |
| Teanum Apulum | geom | `0101000020E6100000092757B64FD52D40E5DE91366DE64440` | `SRID=4326;POINT(15.241689 41.7637)` | wd1-point |
| Teanum Apulum | lat | `41.80020792124359` | `41.7637` | wd1-replace |
| Teanum Apulum | lon | `14.916623781336527` | `15.241689` | wd1-replace |
| Teanum Apulum | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Teanum Apulum | period_start | `-500` | `-900` | wd1-replace |
| The Linear Cemetery, Kilmartin Glen | period_name | `500 BC - 1 AD` | `4500 - 3000 BC` | wd1-derive-period-name |
| The Linear Cemetery, Kilmartin Glen | period_start | `-500` | `-3700` | wd1-replace |
| The Linear Cemetery, Kilmartin Glen | site_type | `Cairn` | `Cemetery` | wd1-replace |
| The Linear Cemetery, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://www.mysteriousbritain.co.uk/ancient-sites/kilmartin-` | wd1-replace |
| Theban Treasury, Delphi | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Thebes, Greece | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Thebes, Greece | period_start | `-4000` | `NULL` | wd1-clear |
| Throne of Queen Sheba - Barran Temple | source_url | `https://en.wikipedia.org/wiki/Barran_Temple` | `https://en.wikipedia.org/wiki/Bar%27an_Temple` | wd1-replace |
| Théâtre Romain Khmissa (Ancient Thubursicum, Roman Theatre) | site_type | `Megalithic stones` | `Theatre` | wd1-replace |
| Théâtre Romain Khmissa (Ancient Thubursicum, Roman Theatre) | source_url | `https://en.wikipedia.org/wiki/Thubursicum` | `https://theatrum.de/thubursicumnumidarum.html` | wd1-replace |
| Timpone della Motta | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Timpone della Motta | period_start | `-3000` | `-1500` | wd1-replace |
| Timpone della Motta | site_type | `City/town/settlement` | `Sanctuary` | wd1-replace |
| Trink Hill | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Trink Hill | period_start | `-3000` | `NULL` | wd1-clear |
| Trink Hill | source_url | `https://en.wikipedia.org/wiki/Trink_Hill` | `https://www.megalithic.co.uk/article.php?sid=20224` | wd1-replace |
| Vicus Maracitanus-Ksar Toual | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Vicus Maracitanus-Ksar Toual | period_start | `1` | `NULL` | wd1-clear |
| Wind Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wind Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Wind Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Wind Hill | source_url | `https://en.wikipedia.org/wiki/Wind_Hill` | `https://www.exmoorher.co.uk/Monument/MDE1236` | wd1-replace |
| Witham Shield | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Wurdi Youang Stone Arrangement | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Wurdi Youang Stone Arrangement | period_start | `-9000` | `NULL` | wd1-clear |
| Ναός Σωτήρου Διός | site_type | `City/town/settlement` | `Sanctuary` | wd1-replace |
| Ναός Σωτήρου Διός | source_url | `https://en.wikipedia.org/wiki/Megalopolis,_Greece` | `https://topostext.org/place/374221SZSo` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Vicus Maracitanus-Ksar Toual | lat | `coordinates-unresolved` | English Wikipedia places the ruins at 36° 01′ 04″ N, 9° 13′ 47″ E (the stored point), while the Digital Atlas of the Rom |
| Careyeros Hill | lat | `coordinates-unresolved` | Only C. Michael Hogan's Megalithic Portal entry gives a point for Careyeros Hill (20.783278N 105.522008W, matching the s |
| Bakka Roman Temple | lat | `coordinates-unresolved` | Aliquot (Presses de l'Ifpo) and middleeast.com place the temple inside Bakka village, at the top of the village near the |
| Witham Shield | lat | `coordinates-unresolved` | The shield was dredged from the River Witham 'in the vicinity of Washingborough and Fiskerton'; the Lincolnshire HER fin |
| Rock Shelter of Solhapa | lat | `coordinates-unresolved` | Both the stored point (about 2.5 km off) and the Wikidata point (in Duas Igrejas village) are wrong: the shelter lies ab |
| T'akaq | lat | `coordinates-unresolved` | The only published coordinates (Wikipedia/Wikidata, and an OpenStreetMap peak node tagged with the same Wikidata item) a |
| Theban Treasury, Delphi | lat | `coordinates-unresolved` | Only one source family prints a quotable point for the Theban Treasury: Wikidata Q22675693 (38°28'53.422"N, 22°30'4.540" |
| Ashley, Northamptonshire | lat | `coordinates-unresolved` | The site is the Iron Age settlement and Roman villa north of the village near the River Welland, which RCHME and the Nor |
| Baltic Sea Anomaly | lat | `coordinates-unresolved` | Ocean X never published the anomaly's position (esovitae.com: 'Ocean X Team has not published precise coordinates'), Wik |
| Fournou Korifi | lat | `country-changes` | the new point lies in [], the site says Greece |
| Aynuna | lat | `coordinates-unresolved` | The Wikidata point (28.094444, 35.200278) is the GeoNames point of the modern village of 'Aynunah, not the ruins. Pleiad |
| Abu Salabikh | lat | `coordinates-unresolved` | The stored point lies in fields about 13.5 km east of the tell. Pleiades (OSM and CIGS locations), the German, Dutch and |
| Richmond Park | lat | `coordinates-unresolved` | The entry names only the park; the stored point (about TQ 2054 7377) lies on no recorded barrow, and the park's recorded |
| Markahirka | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point for the site (9°22′14.65″S 77°7′47.50″W, 26 m from the stored point);  |
| Situs Megalit Tebing Tinggi | lat | `coordinates-unresolved` | The site lies in dusun Tebing Tinggi, Kelurahan Lubuk Buntak, Kecamatan Dempo Selatan, Pagar Alam (Kumparan), and the st |
| Nazca Lines | lat | `coordinates-unresolved` | The Nazca lines cover some 450 km2 and the sources that print a point disagree by kilometres: Wikipedia gives 14°41′51″S |
| Wurdi Youang Stone Arrangement | lat | `coordinates-unresolved` | Only Wikipedia (citing the UNESCO astronomical-heritage portal) gives a point for the arrangement, 37°52′30″S 144°27′28″ |
| Kuntuyuq | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point for Kuntuyuq (-10.54944, -76.35917, 0.1 km from the stored point); MIN |
| Gran Pajatén | lat | `coordinates-unresolved` | Only English Wikipedia (7°38'56"S 77°25'05"W, which the stored point copies) gives a quotable point; OpenStreetMap (via  |
| Pukara, Vilcas Huamán | lat | `coordinates-unresolved` | Neither Wikipedia nor Wikidata gives a point, and the MINCETUR inventory only places the ruins on Cerro Pucará near Anta |
| Intipanawin | lat | `coordinates-unresolved` | The rock shelter lies about an hour's walk from the village of Pacllon (MINCETUR inventory via turismoperuano), but no s |
| Jabal al-Baidain | lat | `coordinates-unresolved` | Wikipedia and Sabq place Jabal al-Baidain 13 km south-west of Dawadmi in Riyadh Region. The stored point (31.28, 36.29)  |
| Castro de Porto de Baixo | lat | `country-changes` | the new point lies in [], the site says Spain |
| Manika, Greece | lat | `country-changes` | the new point lies in [], the site says Greece |
| Kokkinokremmos | lat | `country-changes` | the new point lies in ['Dhekelia Sovereign Base Area'], the site says Cyprus |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s009-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s009 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
