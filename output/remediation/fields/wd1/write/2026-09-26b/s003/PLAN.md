# WD1 fields-wd1-2026-09-26b-s003: plan

Built 2026-09-30T05:56:21+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s003`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s003:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 287 |
| sites_written | 100 |
| refused | 15 |
| cells:geom | 20 |
| cells:lat | 20 |
| cells:lon | 20 |
| cells:period_name | 62 |
| cells:period_start | 62 |
| cells:site_type | 55 |
| cells:source_url | 48 |
| refused:coordinates-unresolved | 15 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Agrour Amogjar | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Agrour Amogjar | period_start | `-500` | `NULL` | wd1-clear |
| Angkor Borei and Phnom Da | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Angkor Borei and Phnom Da | period_start | `-3000` | `-400` | wd1-replace |
| Angkor Borei and Phnom Da | site_type | `Temple complex` | `City` | wd1-replace |
| Appolonia Temple Ruins | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Appolonia Temple Ruins | period_start | `1` | `NULL` | wd1-clear |
| Appolonia Temple Ruins | source_url | `https://en.wikipedia.org/wiki/Apollonia_(Lycia)` | `NULL` | wd1-clear |
| Asklepion, Kos | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Asklepion, Kos | period_start | `-1500` | `-400` | wd1-replace |
| Asklepion, Kos | site_type | `Megalithic stones` | `Sanctuary` | wd1-replace |
| Asklepion, Kos | source_url | `https://en.wikipedia.org/wiki/Asclepieion` | `https://en.wikipedia.org/wiki/Temple_of_Asclepius,_Kos` | wd1-replace |
| Ayazini Kaya Church | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ayazini Kaya Church | period_start | `1` | `NULL` | wd1-clear |
| Ayazini Kaya Church | site_type | `Cave Structures` | `Church` | wd1-replace |
| Ayazini Kaya Church | source_url | `https://en.wikipedia.org/wiki/Ayazini,_%C4%B0hsaniye` | `https://www.afyondayiz.gov.tr/sayfa-ayazini-kilisesi/` | wd1-replace |
| Aššur | geom | `0101000020E61000000C4F6354CDA04540AC2D399C6CBC4140` | `SRID=4326;POINT(43.2625 35.456667)` | wd1-point |
| Aššur | lat | `35.47206452171244` | `35.456667` | wd1-replace |
| Aššur | lon | `43.2562661633402` | `43.2625` | wd1-replace |
| Beinan Cultural Park | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Beinan Cultural Park | period_start | `-4000` | `NULL` | wd1-clear |
| Beinan Cultural Park | source_url | `https://en.wikipedia.org/wiki/Beinan_Cultural_Park` | `https://en.wikipedia.org/wiki/Peinan_Site_Park` | wd1-replace |
| Berezan Island | source_url | `https://en.wikipedia.org/wiki/Berezan_Island` | `https://uk.wikipedia.org/wiki/%D0%91%D0%BE%D1%80%D0%B8%D1%81` | wd1-replace |
| Berry Head | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Berry Head | period_start | `-1000` | `NULL` | wd1-clear |
| Berry Head | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Berry Head | source_url | `https://en.wikipedia.org/wiki/Berry_Head` | `https://www.megalithic.co.uk/article.php?sid=62517` | wd1-replace |
| Bolt Tail | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Bolt Tail | period_start | `-1000` | `-300` | wd1-replace |
| Bolt Tail | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Bolt Tail | source_url | `https://en.wikipedia.org/wiki/Bolt_Tail` | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord` | wd1-replace |
| Bosnian Pyramid of the Sun | source_url | `https://en.wikipedia.org/wiki/Bosnian_pyramid_claims` | `https://en.wikipedia.org/wiki/Viso%C4%8Dica_(hill)` | wd1-replace |
| Breidden Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Breidden Hill | source_url | `https://en.wikipedia.org/wiki/Breidden_Hill` | `https://cy.wikipedia.org/wiki/Bryngaer_Breiddin` | wd1-replace |
| Brighstone | geom | `0101000020E610000088DC28679366F6BF70DC65EF71524940` | `SRID=4326;POINT(-1.40119 50.6553)` | wd1-point |
| Brighstone | lat | `50.64410202478109` | `50.6553` | wd1-replace |
| Brighstone | lon | `-1.4000429181740248` | `-1.40119` | wd1-replace |
| Brighstone | site_type | `Residence/villa/farmhouse` | `Villa` | wd1-replace |
| Brighstone | source_url | `https://en.wikipedia.org/wiki/Brighstone` | `https://www.wikidata.org/wiki/Q17648120` | wd1-replace |
| Brown Willy Cairns | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Brown Willy Cairns | period_start | `-3000` | `NULL` | wd1-clear |
| Brown Willy Cairns | source_url | `https://en.wikipedia.org/wiki/Brown_Willy` | `https://www.megalithic.co.uk/article.php?sid=35404` | wd1-replace |
| Burgstallkogel, Sulm Valley | site_type | `Mound/tumulus` | `Settlement` | wd1-replace |
| Burgstallkogel, Sulm Valley | source_url | `https://en.wikipedia.org/wiki/Burgstallkogel_(Sulm_valley)` | `https://en.wikipedia.org/wiki/Burgstallkogel` | wd1-replace |
| Burrington Combe | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Burrington Combe | period_start | `-4500` | `NULL` | wd1-clear |
| Carn Kenidjack | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Carn Kenidjack | period_start | `-5000` | `NULL` | wd1-clear |
| Carn Kenidjack | site_type | `Megalithic stones` | `Natural feature` | wd1-replace |
| Carrawburgh | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Castellum Onagrinum Archaeological Site, Begeč | geom | `0101000020E61000004F1E548A799F334075D8730B509E4640` | `SRID=4326;POINT(19.625824 45.226811)` | wd1-point |
| Castellum Onagrinum Archaeological Site, Begeč | lat | `45.236817771496966` | `45.226811` | wd1-replace |
| Castellum Onagrinum Archaeological Site, Begeč | lon | `19.62294830850288` | `19.625824` | wd1-replace |
| Castellum Onagrinum Archaeological Site, Begeč | source_url | `https://en.wikipedia.org/wiki/Archaeology` | `https://sr.wikipedia.org/wiki/%D0%9E%D0%BD%D0%B0%D0%B3%D1%80` | wd1-replace |
| Castle Hill, Torrington | period_name | `1500 - 500 BC` | `1000 - 1500 AD` | wd1-derive-period-name |
| Castle Hill, Torrington | period_start | `-1000` | `1139` | wd1-replace |
| Castle Hill, Torrington | site_type | `Fortress/citadel` | `Castle` | wd1-replace |
| Cave of the Guanches | geom | `0101000020E6100000FF89F4DC18B930C05CC794FB8B603C40` | `SRID=4326;POINT(-16.700256 28.383278)` | wd1-point |
| Cave of the Guanches | lat | `28.377135967085778` | `28.383278` | wd1-replace |
| Cave of the Guanches | lon | `-16.723035630895534` | `-16.700256` | wd1-replace |
| Cave of the Guanches | site_type | `Archaeological site` | `Cave` | wd1-replace |
| Cefn Bryn | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cefn Bryn | period_start | `-5000` | `NULL` | wd1-clear |
| Cefn Bryn | source_url | `https://en.wikipedia.org/wiki/Cefn_Bryn` | `https://cadwpublic-api.azurewebsites.net/reports/sam/FullRep` | wd1-replace |
| Cerro Quiac | site_type | `Temple complex` | `Fortress` | wd1-replace |
| Charax Spasinu | geom | `0101000020E6100000E7F8FE7B19C6474017E7FB460FE63E40` | `SRID=4326;POINT(47.578031 30.894692)` | wd1-point |
| Charax Spasinu | lat | `30.89867061281174` | `30.894692` | wd1-replace |
| Charax Spasinu | lon | `47.54765272092646` | `47.578031` | wd1-replace |
| Choquepuquio | geom | `0101000020E6100000A2ABFD4667EF51C0D0718CFADD462BC0` | `SRID=4326;POINT(-71.734088 -13.607518)` | wd1-point |
| Choquepuquio | lat | `-13.638412313121904` | `-13.607518` | wd1-replace |
| Choquepuquio | lon | `-71.7406785466433` | `-71.734088` | wd1-replace |
| Choquepuquio | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Choquepuquio | period_start | `1` | `-200` | wd1-replace |
| Cividade de Âncora | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Clayhanger, Devon | geom | `0101000020E6100000FF416BC944290BC00E990208CA7F4940` | `SRID=4326;POINT(-3.41492 50.9883)` | wd1-point |
| Clayhanger, Devon | lat | `50.998353005665294` | `50.9883` | wd1-replace |
| Clayhanger, Devon | lon | `-3.395150731645344` | `-3.41492` | wd1-replace |
| Clayhanger, Devon | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Clayhanger, Devon | period_start | `1` | `NULL` | wd1-clear |
| Clayhanger, Devon | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Clayhanger, Devon | source_url | `https://en.wikipedia.org/wiki/Clayhanger,_Devon` | `https://www.wikidata.org/wiki/Q17651192` | wd1-replace |
| Craig Rhiwarth | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Craig Rhiwarth | period_start | `-1500` | `NULL` | wd1-clear |
| Craig Rhiwarth | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Creech Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Creech Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Debdieba | site_type | `Megalithic structures` | `Temple` | wd1-replace |
| Delphi | site_type | `Megalithic stones` | `Sanctuary` | wd1-replace |
| Devil's Causeway | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Devil's Causeway | period_start | `1` | `NULL` | wd1-clear |
| Dolmen de Lácara | site_type | `Necropolis/tombs complex` | `Dolmen` | wd1-replace |
| Dolmen de Menga | site_type | `Mound/tumulus` | `Dolmen` | wd1-replace |
| Ebsbury | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ebsbury | period_start | `1` | `NULL` | wd1-clear |
| Ebsbury | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Eggardon Hill | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Eggardon Hill | period_start | `-4500` | `NULL` | wd1-clear |
| Eggardon Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Ekornavallen | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Ekornavallen | period_start | `-5000` | `-3300` | wd1-replace |
| Ekornavallen | site_type | `Cemetery` | `Burial` | wd1-replace |
| Epidaurus | geom | `0101000020E6100000EB38B84D121337407343414689CC4240` | `SRID=4326;POINT(23.1617 37.6331)` | wd1-point |
| Epidaurus | lat | `37.59793928324407` | `37.6331` | wd1-replace |
| Epidaurus | lon | `23.074498040653378` | `23.1617` | wd1-replace |
| Epidaurus | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Epidaurus | period_start | `-1500` | `-3000` | wd1-replace |
| Ermita de la Virgen del Pilar Dam | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ermita de la Virgen del Pilar Dam | period_start | `1` | `NULL` | wd1-clear |
| Ermita de la Virgen del Pilar Dam | site_type | `Megalithic structures` | `Reservoir/aqueduct/canal` | wd1-replace |
| Funerary Naiskos of Aristonautes | geom | `0101000020E61000003757F3E972BB37409EE5E062A3FE4240` | `SRID=4326;POINT(23.71861 37.97833)` | wd1-point |
| Funerary Naiskos of Aristonautes | lat | `37.98936115247055` | `37.97833` | wd1-replace |
| Funerary Naiskos of Aristonautes | lon | `23.732222196492526` | `23.71861` | wd1-replace |
| Great Ziggurat of Ur | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Great Ziggurat of Ur | period_start | `-500` | `-2100` | wd1-replace |
| Gärde | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Gärde | period_start | `-5000` | `NULL` | wd1-clear |
| Gärde | source_url | `https://en.wikipedia.org/wiki/G%C3%A4rde` | `https://fi.wikipedia.org/wiki/G%C3%A4rdenin_kalliopiirrokset` | wd1-replace |
| Habloville | geom | `0101000020E610000083867A177C89C5BFE8826FFFDA644840` | `SRID=4326;POINT(-0.1645 48.8064)` | wd1-point |
| Habloville | lat | `48.787933282326605` | `48.8064` | wd1-replace |
| Habloville | lon | `-0.16825820108811138` | `-0.1645` | wd1-replace |
| Habloville | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Habloville | period_start | `-4500` | `NULL` | wd1-clear |
| Habloville | site_type | `Megalithic stones` | `Dolmen` | wd1-replace |
| Habloville | source_url | `https://en.wikipedia.org/wiki/Habloville` | `https://fr.wikipedia.org/wiki/Pierre_des_Bignes` | wd1-replace |
| Hadnmauer | site_type | `Fortress` | `Wall` | wd1-replace |
| Haron (Charonian) Kabartmasi | source_url | `https://www.google.com.au/maps/place/HARON+(CHARON%C4%B0ON)+` | `https://kulturenvanteri.com/en/yer/haron-kabartmasi/` | wd1-replace |
| Hegra - Mada'in Salih | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Hegra - Mada'in Salih | period_start | `-100` | `-2000` | wd1-replace |
| Huánuco Pampa | period_name | `1 - 500 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Huánuco Pampa | period_start | `1` | `1460` | wd1-replace |
| Huánuco Pampa | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Ingapirca Archaeological Complex | period_name | `1000 - 1500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Ingapirca Archaeological Complex | period_start | `1000` | `500` | wd1-replace |
| Ingapirca Archaeological Complex | source_url | `https://www.ecuadorhop.com/inca-ruins-ecuador/` | `https://en.wikipedia.org/wiki/Ingapirca` | wd1-replace |
| Isla de Sacrificios | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Isla de Sacrificios | period_start | `1` | `NULL` | wd1-clear |
| Isla de Sacrificios | source_url | `https://en.wikipedia.org/wiki/Isla_de_Sacrificios` | `https://www.megalithic.co.uk/article.php?sid=31058` | wd1-replace |
| Jannusan Burial Mound Field | geom | `0101000020E61000009834EBD8873E4940D9FC9556122A3A40` | `SRID=4326;POINT(50.491583 26.22775)` | wd1-point |
| Jannusan Burial Mound Field | lat | `26.164342319124305` | `26.22775` | wd1-replace |
| Jannusan Burial Mound Field | lon | `50.48852073177949` | `50.491583` | wd1-replace |
| Jannusan Burial Mound Field | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Jannusan Burial Mound Field | period_start | `-3000` | `NULL` | wd1-clear |
| Jaw Hill | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Jaw Hill | period_start | `1` | `NULL` | wd1-clear |
| Jaw Hill | site_type | `Earthwork` | `NULL` | wd1-clear |
| Jaw Hill | source_url | `https://en.wikipedia.org/wiki/Jaw_Hill` | `NULL` | wd1-clear |
| Jinkiori | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Jinkiori | period_start | `-5000` | `NULL` | wd1-clear |
| Kamares, Crete | geom | `0101000020E61000008166466E27D23840765AEA7B7A934140` | `SRID=4326;POINT(24.827574 35.177318)` | wd1-point |
| Kamares, Crete | lat | `35.15217541640315` | `35.177318` | wd1-replace |
| Kamares, Crete | lon | `24.820914165675735` | `24.827574` | wd1-replace |
| Kamares, Crete | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Kamares, Crete | period_start | `-4000` | `-3000` | wd1-replace |
| Kamares, Crete | site_type | `Cave Structures` | `Cave` | wd1-replace |
| Kamares, Crete | source_url | `https://en.wikipedia.org/wiki/Kamares,_Crete` | `https://de.wikipedia.org/wiki/Kamares-H%C3%B6hle` | wd1-replace |
| Karahan Tepe | site_type | `Megalithic stones` | `Settlement` | wd1-replace |
| Kilmashogue | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Kilmashogue | period_start | `-4000` | `-2000` | wd1-replace |
| Kilmashogue | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Kilmashogue | source_url | `https://en.wikipedia.org/wiki/Kilmashogue` | `https://www.dublinmountains.ie/archaeology/archaeology/kilma` | wd1-replace |
| Kit Hill | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Kit Hill | period_start | `-4500` | `-3000` | wd1-replace |
| Kit Hill | site_type | `Fortification` | `Barrow` | wd1-replace |
| Kit Hill | source_url | `https://en.wikipedia.org/wiki/Kit_Hill` | `https://www.megalithic.co.uk/article.php?sid=61289` | wd1-replace |
| Kition | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Kition | period_start | `-3000` | `-1300` | wd1-replace |
| Kosmaj | geom | `0101000020E6100000326868C4CB903440767E41D89C3B4640` | `SRID=4326;POINT(20.499206 44.513415)` | wd1-point |
| Kosmaj | lat | `44.46572402189206` | `44.513415` | wd1-replace |
| Kosmaj | lon | `20.565609240999216` | `20.499206` | wd1-replace |
| Kosmaj | site_type | `Mine/quarry` | `Mine` | wd1-replace |
| Kosmaj | source_url | `https://en.wikipedia.org/wiki/Kosmaj` | `https://oxrep.classics.ox.ac.uk/popup.php?ste=2101` | wd1-replace |
| Kraku Lu Jordan | site_type | `Settlement` | `Fortification` | wd1-replace |
| Kuélap | period_name | `500 - 1000 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Kuélap | period_start | `500` | `401` | wd1-replace |
| Lower Swat Valley | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Lower Swat Valley | period_start | `-1500` | `NULL` | wd1-clear |
| Lower Swat Valley | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Lower Swat Valley | source_url | `https://en.wikipedia.org/wiki/Lower_Swat_Valley` | `https://ur.wikipedia.org/wiki/%D8%B2%DB%8C%D8%B1%DB%8C%DA%BA` | wd1-replace |
| Macellum of Naples | site_type | `City/town/settlement` | `Forum` | wd1-replace |
| Midea, Argolid | period_name | `4500 - 3000 BC` | `< 4500 BC` | wd1-derive-period-name |
| Midea, Argolid | period_start | `-4000` | `-4800` | wd1-replace |
| Monte Bubbonia | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Monte Bubbonia | period_start | `-1500` | `NULL` | wd1-clear |
| Museo Archeologico Nazionale e Zona Archeologica di Luni | site_type | `Museum` | `City` | wd1-replace |
| Museo Archeologico Nazionale e Zona Archeologica di Luni | source_url | `https://en.wikipedia.org/wiki/Luni` | `https://it.wikipedia.org/wiki/Luna_(colonia_romana)` | wd1-replace |
| Mycenaean Acropolis of Midea | period_name | `4500 - 3000 BC` | `< 4500 BC` | wd1-derive-period-name |
| Mycenaean Acropolis of Midea | period_start | `-4000` | `-5800` | wd1-replace |
| Nether Largie South Cairn, Kilmartin Glen | geom | `0101000020E610000067B3AE5DA4F215C06BE4D3E31D114C40` | `SRID=4326;POINT(-5.49514 56.124473)` | wd1-point |
| Nether Largie South Cairn, Kilmartin Glen | lat | `56.133724668944375` | `56.124473` | wd1-replace |
| Nether Largie South Cairn, Kilmartin Glen | lon | `-5.486955131328478` | `-5.49514` | wd1-replace |
| Nether Largie South Cairn, Kilmartin Glen | period_name | `500 BC - 1 AD` | `4500 - 3000 BC` | wd1-derive-period-name |
| Nether Largie South Cairn, Kilmartin Glen | period_start | `-500` | `-3700` | wd1-replace |
| Nether Largie South Cairn, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://de.wikipedia.org/wiki/Nether_Largie_South` | wd1-replace |
| Oddendale Stone Circle | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Oddendale Stone Circle | period_start | `-3000` | `NULL` | wd1-clear |
| Oddendale Stone Circle | source_url | `https://en.wikipedia.org/wiki/Oddendale` | `https://www.megalithic.co.uk/article.php?sid=329` | wd1-replace |
| Odeon Theatre | source_url | `https://en.wikipedia.org/wiki/Odeon_theater_(Amman)` | `https://en.wikipedia.org/wiki/Odeon_Theater_(Amman)` | wd1-replace |
| Palaestra at Delphi | site_type | `Megalithic structures` | `Archaeological site` | wd1-replace |
| Peterborough Petroglyphs | source_url | `https://en.wikipedia.org/wiki/Petroglyphs_Provincial_Park` | `https://www.pc.gc.ca/apps/dfhd/page_nhs_eng.aspx?id=487` | wd1-replace |
| Plain of Jars Site 3 | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Plain of Jars Site 3 | period_start | `-1240` | `NULL` | wd1-clear |
| Raddon Top | geom | `0101000020E61000000EEB0C3D76640CC05310F0F991674940` | `SRID=4326;POINT(-3.58414 50.816679)` | wd1-point |
| Raddon Top | lat | `50.809142343729626` | `50.816679` | wd1-replace |
| Raddon Top | lon | `-3.549053647000057` | `-3.58414` | wd1-replace |
| Raddon Top | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Raddon Top | period_start | `-1000` | `NULL` | wd1-clear |
| Raddon Top | source_url | `https://en.wikipedia.org/wiki/Raddon_Top` | `https://www.megalithic.co.uk/article.php?sid=7765` | wd1-replace |
| Ramesses III Temple | source_url | `https://en.wikipedia.org/wiki/Mortuary_Temple_of_Ramesses_II` | `https://digitalkarnak.ucsc.edu/Ramesses-III-Temple/` | wd1-replace |
| Riasc Monastic Settlement | site_type | `Megalithic stones` | `Monastery` | wd1-replace |
| Roulston Scar, Sutton Bank | geom | `0101000020E610000047DEBD573370F3BF4C4F9C547C1E4B40` | `SRID=4326;POINT(-1.2117 54.22682)` | wd1-point |
| Roulston Scar, Sutton Bank | lat | `54.23816926605522` | `54.22682` | wd1-replace |
| Roulston Scar, Sutton Bank | lon | `-1.2148927142533397` | `-1.2117` | wd1-replace |
| Roulston Scar, Sutton Bank | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Roulston Scar, Sutton Bank | period_start | `-500` | `NULL` | wd1-clear |
| Roulston Scar, Sutton Bank | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Roulston Scar, Sutton Bank | source_url | `https://en.wikipedia.org/wiki/Sutton_Bank` | `http://www.landscaperesearchcentre.org/html/Roulston2013/RS_` | wd1-replace |
| Saqqara Necropolis | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Saqqara Necropolis | period_start | `-3000` | `-3050` | wd1-replace |
| Scholes Coppice | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Scholes Coppice | period_start | `1` | `NULL` | wd1-clear |
| Scholes Coppice | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Scholes Coppice | source_url | `https://en.wikipedia.org/wiki/Scholes_Coppice` | `https://www.megalithic.co.uk/article.php?sid=5168` | wd1-replace |
| Site de Tiklat | site_type | `Megalithic stones` | `City/town/settlement` | wd1-replace |
| Site de Tiklat | source_url | `https://fr.wikipedia.org/wiki/Tubusuptu` | `https://en.wikipedia.org/wiki/Tubusuctu` | wd1-replace |
| Sklavokampos | geom | `0101000020E61000000529EA4134023940E543A3D8A5A54140` | `SRID=4326;POINT(24.958 35.2953)` | wd1-point |
| Sklavokampos | lat | `35.29412372562346` | `35.2953` | wd1-replace |
| Sklavokampos | lon | `25.008609885852838` | `24.958` | wd1-replace |
| Sklavokampos | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Sklavokampos | period_start | `-2000` | `-1500` | wd1-replace |
| Sklavokampos | site_type | `City/town/settlement` | `Villa` | wd1-replace |
| Spartia Temple | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Spartia Temple | period_start | `-1500` | `NULL` | wd1-clear |
| St Laurence School - Roman Villa | site_type | `Residence/villa/farmhouse` | `Villa` | wd1-replace |
| St Laurence School - Roman Villa | source_url | `https://en.wikipedia.org/wiki/St_Laurence_School` | `https://www.bradfordonavonmuseum.co.uk/archives/3686` | wd1-replace |
| Stadium at Olympia | site_type | `Megalithic structures` | `Stadium` | wd1-replace |
| Stane Street, Chichester | source_url | `https://en.wikipedia.org/wiki/Stane_Street_(Chichester)` | `https://en.wikipedia.org/wiki/Stane_Street` | wd1-replace |
| Susupillo | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Susupillo | period_start | `1` | `NULL` | wd1-clear |
| Susupillo | site_type | `City/town/settlement` | `Castle/palace` | wd1-replace |
| Susupillo | source_url | `https://en.wikipedia.org/wiki/Susupillo` | `https://www.megalithic.co.uk/article.php?sid=46153` | wd1-replace |
| Temple of Nabu | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Temple of Nabu | period_start | `1` | `-883` | wd1-replace |
| Temple of Nabu | site_type | `Temple complex` | `Temple` | wd1-replace |
| Temple of Nabu | source_url | `https://en.wikipedia.org/wiki/Temple_of_Nabu` | `https://archeologie.culture.gouv.fr/nimrud/fr/histoire-du-te` | wd1-replace |
| Temple of Thutmose III | source_url | `https://en.wikipedia.org/wiki/Temple_of_Thutmose_III` | `https://en.wikipedia.org/wiki/Festival_Hall_of_Thutmose_III` | wd1-replace |
| The Sanctuary & Temple of Apollo Hylates | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| The Sanctuary & Temple of Apollo Hylates | period_start | `-500` | `-800` | wd1-replace |
| The Sanctuary & Temple of Apollo Hylates | source_url | `https://en.wikipedia.org/wiki/Hylates` | `https://el.wikipedia.org/wiki/%CE%99%CE%B5%CF%81%CF%8C_%CF%8` | wd1-replace |
| The Tumuli Park Belt | geom | `0101000020E61000001C11DDC83F276040F2EA5AE308E54140` | `SRID=4326;POINT(129.212 35.838)` | wd1-point |
| The Tumuli Park Belt | lat | `35.78933374347061` | `35.838` | wd1-replace |
| The Tumuli Park Belt | lon | `129.2265362088882` | `129.212` | wd1-replace |
| The Tumuli Park Belt | source_url | `https://en.wikipedia.org/wiki/Gyeongju_Historic_Areas` | `https://en.wikipedia.org/wiki/Daereungwon` | wd1-replace |
| Tomb of the Birds | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Tomb of the Birds | period_start | `-3000` | `NULL` | wd1-clear |
| Tomb of the Birds | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Tomb of the Birds | source_url | `https://pocketsights.com/tours/place/Tomb-of-the-Birds-41831` | `https://giza.fas.harvard.edu/sites/4158/full/` | wd1-replace |
| Torre d'en Galmés | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Torre d'en Galmés | period_start | `-1500` | `-1700` | wd1-replace |
| Torre d'en Galmés | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Uxellodunum | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Uxellodunum | period_start | `-500` | `NULL` | wd1-clear |
| Uxellodunum | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Vrelo Šarkamen | geom | `0101000020E610000048E48B9999593640F9F1904905204640` | `SRID=4326;POINT(22.296264 44.261868)` | wd1-point |
| Vrelo Šarkamen | lat | `44.25016135766413` | `44.261868` | wd1-replace |
| Vrelo Šarkamen | lon | `22.349999996808293` | `22.296264` | wd1-replace |
| Vrelo Šarkamen | site_type | `Residence/villa/farmhouse` | `Palace` | wd1-replace |
| Vrelo Šarkamen | source_url | `https://en.wikipedia.org/wiki/%C5%A0arkamen` | `https://sr.wikipedia.org/wiki/%D0%A6%D0%B0%D1%80%D1%81%D0%BA` | wd1-replace |
| Wandlebury Hill | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Wandlebury Hill | period_start | `-1000` | `-400` | wd1-replace |
| Wandlebury Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Wandlebury Hill | source_url | `https://en.wikipedia.org/wiki/Wandlebury_Hill` | `https://en.wikipedia.org/wiki/Wandlebury_Hill_Fort` | wd1-replace |
| Watling Street | period_name | `3000 - 1500 BC` | `1 - 500 AD` | wd1-derive-period-name |
| Watling Street | period_start | `-3000` | `43` | wd1-replace |
| Xultun | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Xultun | period_start | `-1500` | `NULL` | wd1-clear |
| Y Garn Goch | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Y Garn Goch | period_start | `-1500` | `NULL` | wd1-clear |
| Y Garn Goch | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Y Garn Goch | source_url | `https://en.wikipedia.org/wiki/Y_Garn_Goch` | `https://cy.wikipedia.org/wiki/Bryngaerau_Garn_Goch` | wd1-replace |
| Yaxhá | geom | `0101000020E610000047336AB8AD5556C0752D48D6BB2D3140` | `SRID=4326;POINT(-89.4025 17.0775)` | wd1-point |
| Yaxhá | lat | `17.17864741575382` | `17.0775` | wd1-replace |
| Yaxhá | lon | `-89.33872804995654` | `-89.4025` | wd1-replace |
| Yaxhá | site_type | `Temple complex` | `City` | wd1-replace |
| Yaxhá | source_url | `https://en.wikipedia.org/wiki/Cultural_Triangle_Yaxha-Nakum-` | `https://en.wikipedia.org/wiki/Yaxha` | wd1-replace |
| Zominthos | site_type | `Residence/villa/farmhouse` | `Palace` | wd1-replace |
| Çatalat Viranşehir Antik Kent | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Çatalat Viranşehir Antik Kent | period_start | `1` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Debdieba | lat | `coordinates-unresolved` | The only published point for the buried temple is the Wikidata/Polish Wikipedia one (35°51'15"N 14°27'56"E, one source f |
| Creech Hill | lat | `coordinates-unresolved` | The site is the univallate hillfort at the northern end of Creech Hill, scheduled as 'Hillfort at Fox Covert, 550m north |
| Jinkiori | lat | `coordinates-unresolved` | The petroglyph rock stands on the right bank of the Queros River near Pillcopata, Kosnipata, at 825 m (Hostnig). The Wik |
| Ramesses III Temple | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://vici.org/vici/56224/; quote not found: https://vici.org/vici/562 |
| Tomb of the Birds | lat | `coordinates-unresolved` | The Tomb of the Birds is tomb NC 2 in the north cliff of Giza's far Western Cemetery. Only OpenStreetMap (shown through  |
| Jaw Hill | lat | `coordinates-unresolved` | The site is a cropmark enclosure (a possible Roman marching camp) on Jaw Hill near Kirkhamgate; the only point printed a |
| Lower Swat Valley | lat | `coordinates-unresolved` | The entry is a region, the archaeological landscape of the lower Swat valley between Chakdara and Saidu Sharif, not one  |
| Ayazini Kaya Church | lat | `coordinates-unresolved` | The church is Ayazini Kilisesi (Meryem Ana / Oyma Kilise) at the village entrance; the only printed points for it are th |
| Appolonia Temple Ruins | lat | `coordinates-unresolved` | The only source placing this structure ('Apollonia Yapı Kalıntısı', Kaş) is the Kültür Envanteri entry, whose point Wiki |
| Devil's Causeway | lat | `coordinates-unresolved` | The Devil's Causeway is an 89 km Roman road that leaves Dere Street near Portgate, north of Corbridge, and runs to Berwi |
| Watling Street | lat | `coordinates-unresolved` | Watling Street is a Roman road of several hundred kilometres from Dover and Richborough through London and St Albans to  |
| St Laurence School - Roman Villa | lat | `coordinates-unresolved` | Only the Wikimedia family gives a point for the villa: the Wikidata item 'Bradford-on-Avon Roman Villa' (NHLE 1493272) a |
| Çatalat Viranşehir Antik Kent | lat | `coordinates-unresolved` | The site is the Çatalat (Çatlar) ruins in the Tektek mountains, 16 km south-east of Soğmatar in Engelli (Küneftar) villa |
| Xultun | lat | `coordinates-unresolved` | Wikipedia (and Wikidata and GeoNames 3587680) give only the rounded 17°30′N 89°24′W, 2.6 km from the stored point; the o |
| Temple of Nabu | lat | `coordinates-unresolved` | The site is Ezida, the Nabu temple on the Nimrud acropolis. Vici.org places it at 36.097092, 43.330299, next to the stor |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s003-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s003 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
