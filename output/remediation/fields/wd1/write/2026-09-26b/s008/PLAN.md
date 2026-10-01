# WD1 fields-wd1-2026-09-26b-s008: plan

Built 2026-09-30T06:02:45+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s008`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s008:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 281 |
| sites_written | 100 |
| refused | 27 |
| cells:geom | 23 |
| cells:lat | 23 |
| cells:lon | 23 |
| cells:period_name | 64 |
| cells:period_start | 64 |
| cells:site_type | 54 |
| cells:source_url | 30 |
| refused:coordinates-unresolved | 26 |
| refused:country-changes | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Al-Musawwarat as-Sufra | geom | `0101000020E6100000E10E96889F4740404DCC0BCE6E062F40` | `SRID=4326;POINT(33.32361 16.41583)` | wd1-point |
| Al-Musawwarat as-Sufra | lat | `15.512564124050323` | `16.41583` | wd1-replace |
| Al-Musawwarat as-Sufra | lon | `32.55955607726151` | `33.32361` | wd1-replace |
| Al-Rabba Roman and Byzantine Ruins | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Al-Rabba Roman and Byzantine Ruins | period_start | `1` | `NULL` | wd1-clear |
| Al-Rabba Roman and Byzantine Ruins | site_type | `Temple complex` | `City` | wd1-replace |
| Al-Rabba Roman and Byzantine Ruins | source_url | `https://en.wikipedia.org/wiki/Rabba` | `https://deadseaquake.info/EarthquakeCatalogOfTheDeadSea/Site` | wd1-replace |
| Alicante | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Alicante | period_start | `-1000` | `-231` | wd1-replace |
| Allar Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Allar Cave | period_start | `-500` | `NULL` | wd1-clear |
| Ancient Cassope | site_type | `Megalithic stones` | `City` | wd1-replace |
| Ancient City of Caulonia | site_type | `City/town/settlement` | `City` | wd1-replace |
| Araguina-Sennola | geom | `0101000020E6100000EB7526C4F762224028A9722BC0B14440` | `SRID=4326;POINT(9.1659 41.3922)` | wd1-point |
| Araguina-Sennola | lat | `41.38867705439253` | `41.3922` | wd1-replace |
| Araguina-Sennola | lon | `9.193296556181812` | `9.1659` | wd1-replace |
| Aziz Dheri | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Aziz Dheri | period_start | `-500` | `NULL` | wd1-clear |
| Aziz Dheri | site_type | `Mound/tumulus` | `Monastery` | wd1-replace |
| Battle at the Harzhorn | geom | `0101000020E61000006DDC53C93A222440B0985335A3EA4940` | `SRID=4326;POINT(10.104975 51.832383)` | wd1-point |
| Battle at the Harzhorn | lat | `51.833105722254345` | `51.832383` | wd1-replace |
| Battle at the Harzhorn | lon | `10.066854754912322` | `10.104975` | wd1-replace |
| Battle at the Harzhorn | site_type | `Archaeological site` | `Military` | wd1-replace |
| Battle at the Harzhorn | source_url | `https://en.wikipedia.org/wiki/Location` | `https://en.wikipedia.org/wiki/Battle_at_the_Harzhorn` | wd1-replace |
| Beglik Tash | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Beglik Tash | period_start | `-3000` | `-1400` | wd1-replace |
| Beglik Tash | site_type | `Monument` | `Sanctuary` | wd1-replace |
| Bejucal | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Bejucal | period_start | `1` | `NULL` | wd1-clear |
| Bejucal | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Belevi Mausoleum | site_type | `Megalithic stones` | `Tomb` | wd1-replace |
| Benther Berg | geom | `0101000020E6100000B1F8EA496D3B234083F316A7502B4A40` | `SRID=4326;POINT(9.639927 52.352423)` | wd1-point |
| Benther Berg | lat | `52.33839882488885` | `52.352423` | wd1-replace |
| Benther Berg | lon | `9.616068181927718` | `9.639927` | wd1-replace |
| Benther Berg | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Benther Berg | period_start | `-4500` | `-1600` | wd1-replace |
| Benther Berg | source_url | `https://en.wikipedia.org/wiki/Benther_Berg` | `https://www.megalithic.co.uk/article.php?sid=47761` | wd1-replace |
| Billingsgate Roman House and Baths | site_type | `Residence/villa/farmhouse` | `Bath` | wd1-replace |
| Bocchoris - City | geom | `0101000020E6100000E7B6EED8DDDD0740F58DED2EF2CE4340` | `SRID=4326;POINT(3.081389 39.912222)` | wd1-point |
| Bocchoris - City | lat | `39.61676584815351` | `39.912222` | wd1-replace |
| Bocchoris - City | lon | `2.9833332965707657` | `3.081389` | wd1-replace |
| Bryn Celli Ddu | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Bryn Celli Ddu | period_start | `-4000` | `-3000` | wd1-replace |
| Bryn Celli Ddu | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Carrigagulla | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Carrigagulla | period_start | `-4000` | `NULL` | wd1-clear |
| Castro de Sabroso | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Castro de Sabroso | period_start | `-1500` | `-500` | wd1-replace |
| Castro de Sabroso | site_type | `Fortress/citadel` | `Settlement` | wd1-replace |
| Castro de Sabroso | source_url | `https://de-m-wikipedia-org.translate.goog/wiki/Castro_de_Sab` | `https://pt.wikipedia.org/wiki/Cit%C3%A2nia_de_Sabroso` | wd1-replace |
| Chichén Viejo | site_type | `Temple complex` | `Residence/villa/farmhouse` | wd1-replace |
| Chichén Viejo | source_url | `www.cozumel4you.com/chichen-viejo/` | `https://www.inah.gob.mx/boletines/serie-inicial-un-grupo-res` | wd1-replace |
| Chryssolakkos | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Chryssolakkos | period_start | `-4500` | `-1800` | wd1-replace |
| Collor | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Collor | period_start | `1` | `NULL` | wd1-clear |
| Collor | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Column of Taharqa | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Column of Taharqa | source_url | `https://en.wikipedia.org/wiki/Precinct_of_Amun-Re` | `https://digitalkarnak.ucsc.edu/taharqo-kiosk/` | wd1-replace |
| Daschly | geom | `0101000020E61000003D05E7EDA181504010D5E8CBE17B4240` | `SRID=4326;POINT(66.400828 37.087708)` | wd1-point |
| Daschly | lat | `36.96782826298488` | `37.087708` | wd1-replace |
| Daschly | lon | `66.02550838051407` | `66.400828` | wd1-replace |
| Easter Island | geom | `0101000020E61000002C5FD9737C565BC082A84A803E1B3BC0` | `SRID=4326;POINT(-109.358333 -27.116667)` | wd1-point |
| Easter Island | lat | `-27.10642244169913` | `-27.116667` | wd1-replace |
| Easter Island | lon | `-109.35134597995483` | `-109.358333` | wd1-replace |
| El Kab | geom | `0101000020E61000008DDDF7E0A94C4040CED08C8662453940` | `SRID=4326;POINT(32.79778 25.11889)` | wd1-point |
| El Kab | lat | `25.27103463113672` | `25.11889` | wd1-replace |
| El Kab | lon | `32.59893428900532` | `32.79778` | wd1-replace |
| El Kab | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| El Kab | period_start | `-3000` | `-6400` | wd1-replace |
| El Kab | source_url | `https://en.wikipedia.org/wiki/El_Kab` | `https://en.wikipedia.org/wiki/Elkab` | wd1-replace |
| El Porvenir | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| El Porvenir | period_start | `1` | `NULL` | wd1-clear |
| Er-Grah Tumulus | site_type | `Necropolis/tombs complex` | `Mound/tumulus` | wd1-replace |
| Er-Grah Tumulus | source_url | `https://en.wikipedia.org/wiki/Locmariaquer_megaliths` | `https://fr.wikipedia.org/wiki/Tumulus_d%27Er_Grah` | wd1-replace |
| Faqra | geom | `0101000020E6100000F8335E45C8E741400C2ED23F2BFE4040` | `SRID=4326;POINT(35.807652 33.998375)` | wd1-point |
| Faqra | lat | `33.985694863917246` | `33.998375` | wd1-replace |
| Faqra | lon | `35.81079928493267` | `35.807652` | wd1-replace |
| Faqra | source_url | `https://en.wikipedia.org/wiki/Faqra` | `https://en.wikipedia.org/wiki/Qalaat_Faqra` | wd1-replace |
| Greenala Point Fort | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Greenala Point Fort | source_url | `https://en.wikipedia.org/wiki/Greenala_Point` | `https://coflein.gov.uk/en/sites/94956` | wd1-replace |
| Grotta di Cocceio | site_type | `Megalithic structures` | `Road` | wd1-replace |
| House of Dionysus | site_type | `Megalithic structures` | `Villa` | wd1-replace |
| House of Dionysus | source_url | `https://en.wikipedia.org/wiki/Paphos_Archaeological_Park` | `https://es.wikipedia.org/wiki/Casa_de_Dioniso_(Pafos)` | wd1-replace |
| Huapalcalco Pyramid | period_name | `500 - 1000 AD` | `< 4500 BC` | wd1-derive-period-name |
| Huapalcalco Pyramid | period_start | `500` | `-7000` | wd1-replace |
| Intihuatana Archaeological Complex | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Intihuatana Archaeological Complex | period_start | `1000` | `NULL` | wd1-clear |
| Intihuatana Archaeological Complex | site_type | `Polygonal masonry` | `Palace` | wd1-replace |
| Iolcus | geom | `0101000020E610000011CA1D6FBCFB3640E6D31CAF15B14340` | `SRID=4326;POINT(22.93332 39.363868)` | wd1-point |
| Iolcus | lat | `39.38347424419025` | `39.363868` | wd1-replace |
| Iolcus | lon | `22.983344025395187` | `22.93332` | wd1-replace |
| Iolcus | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Iolcus | period_start | `-1000` | `-3000` | wd1-replace |
| Isla Principal Topoxte | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Isla Principal Topoxte | period_start | `-500` | `-600` | wd1-replace |
| Ixtutz | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ixtutz | period_start | `1` | `NULL` | wd1-clear |
| Kaunos | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Kaunos | period_start | `-3000` | `-1000` | wd1-replace |
| Kaunos | site_type | `Temple complex` | `City` | wd1-replace |
| Kocherzhyntsi | source_url | `https://en.wikipedia.org/wiki/Kocherzhyntsi` | `http://tripillya.com/en/poselennya/kocherzhyntsi-2/` | wd1-replace |
| Kot Bala | geom | `0101000020E6100000CE28C794EE1E524045A5B505E4BD4040` | `SRID=4326;POINT(66.708333 25.4625)` | wd1-point |
| Kot Bala | lat | `33.483521188444264` | `25.4625` | wd1-replace |
| Kot Bala | lon | `72.48331183861885` | `66.708333` | wd1-replace |
| Kutlug-Tepe | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kutlug-Tepe | period_start | `-1000` | `NULL` | wd1-clear |
| Kutlug-Tepe | site_type | `Temple complex` | `NULL` | wd1-clear |
| Kyaneai Ören Yeri | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Kyaneai Ören Yeri | period_start | `-3000` | `-500` | wd1-replace |
| La Blanca | source_url | `https://en.wikipedia.org/wiki/La_Blanca` | `https://en.wikipedia.org/wiki/La_Blanca,_San_Marcos_(archaeo` | wd1-replace |
| La Milpa | site_type | `Pyramid complex` | `City` | wd1-replace |
| La Muerta | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| La Muerta | period_start | `1` | `NULL` | wd1-clear |
| La Muerta | site_type | `Temple complex` | `Settlement` | wd1-replace |
| Library of Ashurbanipal | site_type | `Monument` | `Palace` | wd1-replace |
| Madain Saleh | geom | `0101000020E61000008B90413282FA42405628EE4BA6CE3A40` | `SRID=4326;POINT(37.95278 26.79167)` | wd1-point |
| Madain Saleh | lat | `26.80722498478311` | `26.79167` | wd1-replace |
| Madain Saleh | lon | `37.95709827615163` | `37.95278` | wd1-replace |
| Madain Saleh | period_name | `1 - 500 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Madain Saleh | period_start | `1` | `-2000` | wd1-replace |
| Madain Saleh | source_url | `https://en.wikipedia.org/wiki/Hegra_(Mada%27in_Salih)` | `https://en.wikipedia.org/wiki/Hegra` | wd1-replace |
| Magura Cave | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd1-derive-period-name |
| Magura Cave | period_start | `-500` | `-8000` | wd1-replace |
| Mallkuamaya | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Mallkuamaya | period_start | `1` | `NULL` | wd1-clear |
| Mane Braz | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Mane Braz | period_start | `-5000` | `NULL` | wd1-clear |
| Mane Braz | site_type | `Mound/tumulus` | `Dolmen` | wd1-replace |
| Margery Hill | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Margery Hill | period_start | `-3000` | `NULL` | wd1-clear |
| Margery Hill | site_type | `Mound/tumulus` | `Cairn` | wd1-replace |
| Margery Hill | source_url | `https://en.wikipedia.org/wiki/Margery_Hill` | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord` | wd1-replace |
| Martinhoe | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Martinhoe | source_url | `https://en.wikipedia.org/wiki/Martinhoe` | `https://www.exmoorher.co.uk/Monument/MDE1020` | wd1-replace |
| Milecastles - Hadrian's Wall | site_type | `Fortification` | `Fort` | wd1-replace |
| Miłobądz, Pomeranian Voivodeship | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Miłobądz, Pomeranian Voivodeship | period_start | `-1500` | `NULL` | wd1-clear |
| Miłobądz, Pomeranian Voivodeship | source_url | `https://en.wikipedia.org/wiki/Mi%C5%82ob%C4%85dz,_Pomeranian` | `https://zabytek.pl/en/obiekty/g-292685` | wd1-replace |
| Moridunum, Axminster | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Mount Lykaion | geom | `0101000020E6100000B26D8AE598F9354070C1DB5681BA4240` | `SRID=4326;POINT(21.98855 37.44658)` | wd1-point |
| Mount Lykaion | lat | `37.45707212190871` | `37.44658` | wd1-replace |
| Mount Lykaion | lon | `21.97498926763155` | `21.98855` | wd1-replace |
| Mount Lykaion | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Mount Lykaion | source_url | `https://en.wikipedia.org/wiki/Mount_Lykaion` | `https://www.lykaionexcavation.org/site/` | wd1-replace |
| Mundigak | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Mundigak | period_start | `-5000` | `-4000` | wd1-replace |
| Myrtlebury | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Myrtlebury | period_start | `-1000` | `NULL` | wd1-clear |
| Myrtlebury | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Na Nova | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Na Nova | period_start | `-2000` | `NULL` | wd1-clear |
| Na Nova | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Nether Heyford | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Nether Heyford | period_start | `1` | `NULL` | wd1-clear |
| Nether Heyford | site_type | `Residence/villa/farmhouse` | `NULL` | wd1-clear |
| Nether Heyford | source_url | `https://en.wikipedia.org/wiki/Nether_Heyford` | `NULL` | wd1-clear |
| Nether Largie Standing Stones, Kilmartin Glen | geom | `0101000020E610000067B3AE5DA4F215C06BE4D3E31D114C40` | `SRID=4326;POINT(-5.495353 56.12168)` | wd1-point |
| Nether Largie Standing Stones, Kilmartin Glen | lat | `56.133724668944375` | `56.12168` | wd1-replace |
| Nether Largie Standing Stones, Kilmartin Glen | lon | `-5.486955131328478` | `-5.495353` | wd1-replace |
| Nether Largie Standing Stones, Kilmartin Glen | period_name | `4500 - 3000 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Nether Largie Standing Stones, Kilmartin Glen | period_start | `-4000` | `-1400` | wd1-replace |
| Nether Largie Standing Stones, Kilmartin Glen | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Nether Largie Standing Stones, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://nl.wikipedia.org/wiki/Nether_Largie_Standing_Stones` | wd1-replace |
| Odessus | source_url | `https://en.wikipedia.org/wiki/Odessos` | `https://bg.wikipedia.org/wiki/%D0%9E%D0%B4%D0%B5%D1%81%D0%BE` | wd1-replace |
| Pair-non-Pair Cave | geom | `0101000020E6100000E38586CE3AEEDEBF76597CDC25824640` | `SRID=4326;POINT(-0.50178 45.038978)` | wd1-point |
| Pair-non-Pair Cave | lat | `45.016780434339054` | `45.038978` | wd1-replace |
| Pair-non-Pair Cave | lon | `-0.48329038780693007` | `-0.50178` | wd1-replace |
| Pair-non-Pair Cave | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd1-derive-period-name |
| Pair-non-Pair Cave | period_start | `-500` | `-80000` | wd1-replace |
| Pampas Gramalote | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Pampas Gramalote | period_start | `-3000` | `-1500` | wd1-replace |
| Pampas Gramalote | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Pant-y-Saer Burial Chamber | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Pant-y-Saer Burial Chamber | period_start | `-5000` | `NULL` | wd1-clear |
| Pendeen Vau | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Pendeen Vau | period_start | `-1000` | `NULL` | wd1-clear |
| Pendeen Vau | site_type | `Infrastructure` | `Cave Structures` | wd1-replace |
| Petroglyph Provincial Park | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Petroglyph Provincial Park | period_start | `1000` | `NULL` | wd1-clear |
| Pilsdon Pen | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Pilsdon Pen | period_start | `-2000` | `NULL` | wd1-clear |
| Pilsdon Pen | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Pilsdon Pen | source_url | `https://en.wikipedia.org/wiki/Pilsdon_Pen` | `https://heritage.dorsetcouncil.gov.uk/Monument/MDO2018` | wd1-replace |
| Port Way | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Port Way | period_start | `1` | `NULL` | wd1-clear |
| Portico of the Aetolians | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Pseira | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Pseira | period_start | `-4000` | `NULL` | wd1-clear |
| Pseira | site_type | `City/town/settlement` | `Town` | wd1-replace |
| Qunchamarka | geom | `0101000020E610000058CAE8FC9D2152C0BD163D301C4F2AC0` | `SRID=4326;POINT(-72.515623 -13.226746)` | wd1-point |
| Qunchamarka | lat | `-13.154511935670024` | `-13.226746` | wd1-replace |
| Qunchamarka | lon | `-72.52526781781614` | `-72.515623` | wd1-replace |
| Qunchamarka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Qunchamarka | period_start | `1000` | `NULL` | wd1-clear |
| Rame Head | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Rame Head | period_start | `-1000` | `NULL` | wd1-clear |
| Rame Head | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Rame Head | source_url | `https://en.wikipedia.org/wiki/Rame_Head` | `https://www.megalithic.co.uk/article.php?sid=10079` | wd1-replace |
| Rio Amarillo | geom | `0101000020E6100000B763A836243256C0F2E2B0F3C9882D40` | `SRID=4326;POINT(-89.003056 14.889444)` | wd1-point |
| Rio Amarillo | lat | `14.76716577085742` | `14.889444` | wd1-replace |
| Rio Amarillo | lon | `-88.78346029705322` | `-89.003056` | wd1-replace |
| Rock Carvings at Tennes | geom | `0101000020E6100000DEBE60271F343340C0FF84CF81535140` | `SRID=4326;POINT(19.342778 69.310278)` | wd1-point |
| Rock Carvings at Tennes | lat | `69.30479801166712` | `69.310278` | wd1-replace |
| Rock Carvings at Tennes | lon | `19.20360036956742` | `19.342778` | wd1-replace |
| Roman Ruins of Casais Velhos | site_type | `City/town/settlement` | `Villa` | wd1-replace |
| Roman Villa of Chiragan | geom | `0101000020E61000000A1D10ABA72FF03F2DE0F86396994540` | `SRID=4326;POINT(1.014722 43.189444)` | wd1-point |
| Roman Villa of Chiragan | lat | `43.19990205433019` | `43.189444` | wd1-replace |
| Roman Villa of Chiragan | lon | `1.0116345102449622` | `1.014722` | wd1-replace |
| Roman Villa of Chiragan | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Roman Villa of Chiragan | period_start | `1` | `-100` | wd1-replace |
| Sagaholm | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Sagaholm | period_start | `-3000` | `-1500` | wd1-replace |
| Saldae (Béjaïa) | geom | `0101000020E6100000187F108EB13914407E281DB48D604240` | `SRID=4326;POINT(5.08433 36.75587)` | wd1-point |
| Saldae (Béjaïa) | lat | `36.754324449765576` | `36.75587` | wd1-replace |
| Saldae (Béjaïa) | lon | `5.0563413808411255` | `5.08433` | wd1-replace |
| Saldae (Béjaïa) | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Saldae (Béjaïa) | period_start | `1` | `-400` | wd1-replace |
| Schanzenkopf - Spessart | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Schanzenkopf - Spessart | period_start | `1` | `NULL` | wd1-clear |
| Schanzenkopf - Spessart | site_type | `Earthwork` | `Castle` | wd1-replace |
| Schanzenkopf - Spessart | source_url | `https://en.wikipedia.org/wiki/Schanzenkopf_(Spessart)` | `https://www.burgenwelt.org/deutschland/schanzenkopfbyab/obje` | wd1-replace |
| Ses Païsses | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Shipton Hill Settlement | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Shipton Hill Settlement | period_start | `-1500` | `NULL` | wd1-clear |
| Shipton Hill Settlement | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Situs Megalith Talang Kecepol | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Situs Megalith Talang Kecepol | period_start | `-1000` | `NULL` | wd1-clear |
| Situs Megalith Talang Kecepol | site_type | `Necropolis/tombs complex` | `Megalithic` | wd1-replace |
| Situs Megalith Talang Kecepol | source_url | `https://www.google.com.au/maps/place/Situs+Megalith+Talang+K` | `https://www.megalithic.co.uk/article.php?sid=63570` | wd1-replace |
| South Lodge Camp | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| South Lodge Camp | period_start | `-3000` | `-1250` | wd1-replace |
| South Lodge Camp | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Stapeley Hill | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Stapeley Hill | period_start | `-4500` | `NULL` | wd1-clear |
| Stapeley Hill | site_type | `Stone circle` | `Cairn` | wd1-replace |
| Stapeley Hill | source_url | `https://en.wikipedia.org/wiki/Stapeley_Hill` | `https://www.megalithic.co.uk/article.php?sid=10620` | wd1-replace |
| Stoa Poikile | site_type | `Megalithic stones` | `Monument` | wd1-replace |
| Taq Kasra | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Taq Kasra | period_start | `1` | `NULL` | wd1-clear |
| Teufelsrutsch | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Teufelsrutsch | period_start | `-1500` | `NULL` | wd1-clear |
| Teufelsrutsch | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Teufelsrutsch | source_url | `https://en.wikipedia.org/wiki/Teufelsrutsch` | `NULL` | wd1-clear |
| Tibradden Mountain | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Tibradden Mountain | period_start | `-4000` | `NULL` | wd1-clear |
| Tibradden Mountain | source_url | `https://en.wikipedia.org/wiki/Tibradden_Mountain` | `https://de.wikipedia.org/wiki/Tibradden_Cairn` | wd1-replace |
| Tiwanaku | site_type | `Temple complex` | `City` | wd1-replace |
| Toledo, Spain | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Toledo, Spain | period_start | `-1500` | `NULL` | wd1-clear |
| Tomb of Servilia | geom | `0101000020E6100000E59288D6748816C0835DD9A3BFBB4240` | `SRID=4326;POINT(-5.652263 37.467364)` | wd1-point |
| Tomb of Servilia | lat | `37.46678588975467` | `37.467364` | wd1-replace |
| Tomb of Servilia | lon | `-5.63325820168095` | `-5.652263` | wd1-replace |
| Torre del Greco | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Torre del Greco | period_start | `1` | `-100` | wd1-replace |
| Treasury of the Acanthians | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Treasury of the Acanthians | period_start | `-424` | `NULL` | wd1-clear |
| Treasury of the Acanthians | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Umm-Jidr Burial Mound Field | geom | `0101000020E61000009834EBD8873E4940D9FC9556122A3A40` | `SRID=4326;POINT(50.517308 26.016839)` | wd1-point |
| Umm-Jidr Burial Mound Field | lat | `26.164342319124305` | `26.016839` | wd1-replace |
| Umm-Jidr Burial Mound Field | lon | `50.48852073177949` | `50.517308` | wd1-replace |
| Villar de Domingo García | geom | `0101000020E61000009ABB3FA03E4402C024C9741CE51D4440` | `SRID=4326;POINT(-2.259444 40.183586)` | wd1-point |
| Villar de Domingo García | lat | `40.233554417633314` | `40.183586` | wd1-replace |
| Villar de Domingo García | lon | `-2.283322574562999` | `-2.259444` | wd1-replace |
| Villar de Domingo García | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Villar de Domingo García | period_start | `1` | `-100` | wd1-replace |
| Villar de Domingo García | source_url | `https://en.wikipedia.org/wiki/Villar_de_Domingo_Garc%C3%ADa` | `https://es.wikipedia.org/wiki/Villa_romana_de_Noheda` | wd1-replace |
| Virnamäki | period_name | `1500 - 500 BC` | `500 - 1000 AD` | wd1-derive-period-name |
| Virnamäki | period_start | `-1500` | `550` | wd1-replace |
| Virnamäki | site_type | `Monument` | `Cemetery` | wd1-replace |
| Wajxaklajun | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wajxaklajun | period_start | `1` | `NULL` | wd1-clear |
| Wajxaklajun | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Winsford, Somerset | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Winsford, Somerset | period_start | `-4500` | `NULL` | wd1-clear |
| Winsford, Somerset | site_type | `Barrow` | `NULL` | wd1-clear |
| Winsford, Somerset | source_url | `https://en.wikipedia.org/wiki/Winsford,_Somerset` | `NULL` | wd1-clear |
| Yagul | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Yagul | period_start | `-1500` | `-500` | wd1-replace |
| Yeronisos | period_name | `500 BC - 1 AD` | `4500 - 3000 BC` | wd1-derive-period-name |
| Yeronisos | period_start | `-500` | `-3800` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Treasury of the Acanthians | lat | `coordinates-unresolved` | No source prints a point for the Treasury of the Acanthians: Wikidata Q22810172 has no coordinate, ToposText has it only |
| Port Way | lat | `coordinates-unresolved` | Port Way is a 58 km linear Roman road from Silchester to Old Sarum; the stored point lies near its Silchester end in Pam |
| Taq Kasra | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote fetch failed: https://structurae.net/en/structures/taq-i-kisra (status 403); quote  |
| Pampas Gramalote | lat | `coordinates-unresolved` | Gramalote lies on the Pampa Gramalote in Huanchaco district near Trujillo; the stored point is at Puerto Malabrigo in th |
| Sagaholm | lat | `coordinates-unresolved` | The stored point copies English Wikipedia's 57.4447, 14.1020, which is 57°44′47″N 14°10′20″E misread as decimals and lie |
| Stapeley Hill | lat | `coordinates-unresolved` | The ancient site named after the hill is the Stapeley Hill (ring) cairn on the hill's saddle; only the Megalithic Portal |
| Odessus | lat | `country-changes` | the new point lies in [], the site says Bulgaria |
| Ixtutz | lat | `coordinates-unresolved` | The stored point is the town of Dolores (and its 'Parque Regional Municipal Ixtutz'), whereas Wikipedia, citing the Atla |
| Mallkuamaya | lat | `coordinates-unresolved` | The stored point is Puno city itself, while Wikipedia and MINCETUR place the chullpa site 15-18 km south-west of Puno on |
| Kutlug-Tepe | lat | `coordinates-unresolved` | The stored point (36.7587, 66.8989) is the city of Balkh, not the site; the only printed points are Wikipedia's coarse 3 |
| Bejucal | lat | `coordinates-unresolved` | The stored point lies about 16 km south-west of El Zotz, but Wikipedia places Bejucal 7 km north-east of El Zotz and 20  |
| Winsford, Somerset | lat | `coordinates-unresolved` | The stored point is the centre of Winsford village (Wikipedia and Wikidata give 51.0993, -3.5652 for the civil parish),  |
| La Blanca | lat | `coordinates-unresolved` | The site is La Blanca in San Marcos (the Middle Preclassic centre near Ocós); English Wikipedia/Wikidata put it at 14.59 |
| La Muerta | lat | `coordinates-unresolved` | No page prints coordinates for La Muerta: Wikidata has no P625, the English, Spanish, French and Italian articles and Co |
| Column of Taharqa | lat | `coordinates-unresolved` | Only OpenStreetMap's node 'Column of Taharqa' (25.7187615, 32.6572987) prints the column's point; the Wikidata item was  |
| Milecastles - Hadrian's Wall | lat | `coordinates-unresolved` | The entry is the whole class of Hadrian's Wall milecastles - 80 small forts spaced a Roman mile apart along the 117 km W |
| Wajxaklajun | lat | `coordinates-unresolved` | English Wikipedia places Wajxaklajun at 15°49′43.43″N 91°28′26.23″W beside San Mateo Ixtatán, about 57 km north of the s |
| Kocherzhyntsi | lat | `coordinates-unresolved` | No source prints a point for the Trypillia settlement itself: the reserve page and the Wikipedia-derived pages only say  |
| Nether Heyford | lat | `coordinates-unresolved` | The site is the Roman villa in Horestone meadow east of Nether Heyford (Northamptonshire HER 829/1). Only Vici.org print |
| Allar Cave | lat | `coordinates-unresolved` | All sources place the cave in Allar village on the left bank of the Vilesh (Yardymli district); Russian and Azerbaijani  |
| El Porvenir | lat | `coordinates-unresolved` | The stored point near Guatemala City is about 305 km from the site, which lies on the Guatemalan bank of the Usumacinta  |
| Chichén Viejo | lat | `coordinates-unresolved` | No two independent pages print a coordinate pair for Chichén Viejo (the Initial Series Group) as visible text. INAH's el |
| Situs Megalith Talang Kecepol | lat | `coordinates-unresolved` | Only the Megalithic Portal prints a point for the site (Pematang Bango Stone Grave, alternative name Talang Kecepol: 4.0 |
| Margery Hill | lat | `coordinates-unresolved` | The site is the scheduled round cairn 200 m west of the Margery Hill trig pillar (National Trust HER grid reference SK 1 |
| Miłobądz, Pomeranian Voivodeship | lat | `coordinates-unresolved` | The site is the Iron Age cemetery Miłobądz, site 3 (NID register 310/Archeol. of 1976). The stored point and the Wikidat |
| Teufelsrutsch | lat | `coordinates-unresolved` | The site is the Celtic ring wall (keltische Fliehburg) on the Ahrenberg just south of the Teufelsrutsch rock; OpenStreet |
| Roman Ruins of Casais Velhos | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote fetch failed: https://imovel2.patrimoniocultural.gov.pt/detalhes.php?code=74117 (st |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s008-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s008 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
