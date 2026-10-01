# WD1 fields-wd1-2026-09-26b-s002: plan

Built 2026-09-30T05:55:23+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s002`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s002:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 279 |
| sites_written | 100 |
| refused | 20 |
| cells:geom | 24 |
| cells:lat | 24 |
| cells:lon | 24 |
| cells:period_name | 57 |
| cells:period_start | 56 |
| cells:site_type | 54 |
| cells:source_url | 40 |
| refused:coordinates-unresolved | 20 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acrópolis Aguateca | site_type | `City/town/settlement` | `City` | wd1-replace |
| Ahu Vinapu | site_type | `Megalithic stones` | `Megalithic structures` | wd1-replace |
| Alabanda Amfi Tiyatro Tarihi Alanı | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Alabanda Amfi Tiyatro Tarihi Alanı | period_start | `-1500` | `-200` | wd1-replace |
| Alabanda Amfi Tiyatro Tarihi Alanı | source_url | `https://en.wikipedia.org/wiki/Alabanda` | `https://kulturenvanteri.com/en/yer/alabanda-antik-tiyatrosu/` | wd1-replace |
| Aldersgate | site_type | `Gate/archway/bridge` | `Gate` | wd1-replace |
| Aldersgate | source_url | `https://en.wikipedia.org/wiki/Aldersgate` | `https://mapoflondon.uvic.ca/ALDE3.htm` | wd1-replace |
| Ancient Theatre of Megalopolis | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Ancient Theatre of Megalopolis | period_start | `1` | `-370` | wd1-replace |
| Ancient Theatre of Megalopolis | site_type | `Megalithic stones` | `Theatre` | wd1-replace |
| Ancient Theatre of Megalopolis | source_url | `https://en.wikipedia.org/wiki/Megalopolis,_Greece` | `https://es.wikipedia.org/wiki/Teatro_de_Megal%C3%B3polis` | wd1-replace |
| Anemospilia | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Anemospilia | period_start | `-4500` | `-1800` | wd1-replace |
| Archaeological Site of Ancient Thasos | source_url | `https://en.wikipedia.org/wiki/Thasos` | `https://fi.wikipedia.org/wiki/Thasos_(antiikin_kaupunki)` | wd1-replace |
| Archaeological Site of Eleusis | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Archaeological Site of Eleusis | source_url | `https://ancient-greece.org/images/ancient-sites/elefsina/ele` | `https://fr.wikipedia.org/wiki/Sanctuaire_d%27%C3%89leusis` | wd1-replace |
| Armazi | geom | `0101000020E610000006CA95A1545546401029457C87E84440` | `SRID=4326;POINT(44.72166 41.83763)` | wd1-point |
| Armazi | lat | `41.8166346872041` | `41.83763` | wd1-replace |
| Armazi | lon | `44.66664523900913` | `44.72166` | wd1-replace |
| Arminghall | geom | `0101000020E610000096A0A642BD2BF53F0C7DE6117C4B4A40` | `SRID=4326;POINT(1.30667 52.605571)` | wd1-point |
| Arminghall | lat | `52.58972381357498` | `52.605571` | wd1-replace |
| Arminghall | lon | `1.3231785396147067` | `1.30667` | wd1-replace |
| Arminghall | source_url | `https://en.wikipedia.org/wiki/Arminghall` | `https://de.wikipedia.org/wiki/Henge_von_Arminghall` | wd1-replace |
| Auquilohuagra | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Auquilohuagra | period_start | `1400` | `NULL` | wd1-clear |
| Auquilohuagra | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Babilonie | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Babilonie | period_start | `-500` | `NULL` | wd1-clear |
| Babilonie | site_type | `Fortress/citadel` | `Fortification` | wd1-replace |
| Barnenez | site_type | `Monument` | `Cairn` | wd1-replace |
| Bars-Hot | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Bars-Hot | period_start | `1` | `901` | wd1-replace |
| Bredon Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bredon Hill | period_start | `-1500` | `NULL` | wd1-clear |
| Bredon Hill | site_type | `Earthwork` | `Fort` | wd1-replace |
| Bredon Hill | source_url | `https://en.wikipedia.org/wiki/Bredon_Hill` | `https://www.megalithic.co.uk/article.php?sid=5111` | wd1-replace |
| Carl Wark | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Carl Wark | period_start | `-1500` | `NULL` | wd1-clear |
| Carl Wark | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Castro, Apulia | geom | `0101000020E610000034C0579E6A663240B16E6C9828024440` | `SRID=4326;POINT(18.425733 40.007022)` | wd1-point |
| Castro, Apulia | lat | `40.01686387342978` | `40.007022` | wd1-replace |
| Castro, Apulia | lon | `18.400064369605573` | `18.425733` | wd1-replace |
| Castro, Apulia | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Castro, Apulia | period_start | `-500` | `-800` | wd1-replace |
| Cave of Zeus, Naxos | period_name | `4500 - 3000 BC` | `< 4500 BC` | wd1-derive-period-name |
| Cave of Zeus, Naxos | period_start | `-4000` | `-5000` | wd1-replace |
| Chanquillo | site_type | `Fortress/citadel` | `Temple complex` | wd1-replace |
| Cheqollo | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Cheqollo | period_start | `1400` | `NULL` | wd1-clear |
| Cheqollo | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Chisbury | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| City of Enns | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| City of Enns | period_start | `1` | `-400` | wd1-replace |
| City of Enns | source_url | `https://en.wikipedia.org/wiki/History` | `https://en.wikipedia.org/wiki/Enns_(town)` | wd1-replace |
| Costa Beck | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Costa Beck | period_start | `1` | `NULL` | wd1-clear |
| Costa Beck | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Costa Beck | source_url | `https://en.wikipedia.org/wiki/Costa_Beck` | `NULL` | wd1-clear |
| Daidala | geom | `0101000020E610000054159955AEF63C4040943A401C5F4240` | `SRID=4326;POINT(28.976568 36.749409)` | wd1-point |
| Daidala | lat | `36.74304964886005` | `36.749409` | wd1-replace |
| Daidala | lon | `28.963597631334167` | `28.976568` | wd1-replace |
| Daidala | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Daidala | period_start | `-1000` | `-330` | wd1-replace |
| Deer Valley Petroglyph Preserve | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Deer Valley Petroglyph Preserve | period_start | `-4500` | `NULL` | wd1-clear |
| Duraz Temple | site_type | `Temple complex` | `Temple` | wd1-replace |
| Eflatun Pınar Hitit Anıtı | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Eflatun Pınar Hitit Anıtı | period_start | `-3000` | `-1300` | wd1-replace |
| Eflatun Pınar Hitit Anıtı | site_type | `Megalithic stones` | `Sacred site` | wd1-replace |
| Eston Nab | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Eston Nab | period_start | `-6000` | `NULL` | wd1-clear |
| Eston Nab | site_type | `Mound/tumulus` | `Fort` | wd1-replace |
| Gettlinge Grave Field | site_type | `Necropolis/tombs complex` | `Burial` | wd1-replace |
| Gettlinge Grave Field | source_url | `https://en.wikipedia.org/wiki/Gettlinge` | `https://sv.wikipedia.org/wiki/Gettlinge_gravf%C3%A4lt` | wd1-replace |
| Gran Saposoa | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Gran Saposoa | period_start | `1` | `601` | wd1-replace |
| Hellenistic-Roman Theatre | site_type | `Megalithic structures` | `Theatre` | wd1-replace |
| Hellenistic-Roman Theatre | source_url | `https://en.wikipedia.org/wiki/Theatre` | `https://www.sydney.edu.au/museum/our-research/paphos-theatre` | wd1-replace |
| Hemet Maze Stone | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Hemet Maze Stone | period_start | `-500` | `NULL` | wd1-clear |
| High Peak, Devon | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| High Peak, Devon | period_start | `-1000` | `NULL` | wd1-clear |
| High Peak, Devon | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| High Peak, Devon | source_url | `https://en.wikipedia.org/wiki/High_Peak,_Devon` | `https://www.megalithic.co.uk/article.php?sid=43929` | wd1-replace |
| Hillsborough, Devon | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Hillsborough, Devon | period_start | `-1000` | `-300` | wd1-replace |
| Hillsborough, Devon | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Hillsborough, Devon | source_url | `https://en.wikipedia.org/wiki/Hillsborough,_Devon` | `https://www.northdevoncoast-nl.org.uk/coastalheritage/hillsb` | wd1-replace |
| Holmul | geom | `0101000020E6100000163996E6E34E56C01E8738EBD84C3140` | `SRID=4326;POINT(-89.27306 17.31194)` | wd1-point |
| Holmul | lat | `17.300184918690427` | `17.31194` | wd1-replace |
| Holmul | lon | `-89.232659956648` | `-89.27306` | wd1-replace |
| Huari Archaeological Site | source_url | `https://en.wikipedia.org/wiki/Huari_(archaeological_site)` | `https://en.wikipedia.org/wiki/Wari_(archaeological_site)` | wd1-replace |
| Independence Fjord | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Ipf Mountain | site_type | `Fortress/citadel` | `Fortification` | wd1-replace |
| Iskuqucha | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Iskuqucha | period_start | `1400` | `NULL` | wd1-clear |
| Iskuqucha | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| KaʼKabish | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| KaʼKabish | period_start | `-500` | `-800` | wd1-replace |
| KaʼKabish | site_type | `Temple complex` | `City` | wd1-replace |
| Kephala | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Kephala | period_start | `-3000` | `-7000` | wd1-replace |
| Kephala | source_url | `https://en.wikipedia.org/wiki/Kephala` | `https://en.wikipedia.org/wiki/Knossos` | wd1-replace |
| Khoms | geom | `0101000020E610000087E6F67F13892C40E2026CA4B5534040` | `SRID=4326;POINT(14.29306 32.63833)` | wd1-point |
| Khoms | lat | `32.653980782260774` | `32.63833` | wd1-replace |
| Khoms | lon | `14.267726897134038` | `14.29306` | wd1-replace |
| Khoms | site_type | `Megalithic stones` | `City` | wd1-replace |
| Khoms | source_url | `https://en.wikipedia.org/wiki/Al-Khums` | `https://en.wikipedia.org/wiki/Leptis_Magna` | wd1-replace |
| Knin | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Knin | period_start | `-500` | `NULL` | wd1-clear |
| Ksar Lalla Fatma | source_url | `https://jazairhope-org.translate.goog/fr/ksar-lalla-fatma-ou` | `https://archiqoo.com/locations/ksar_lalla_fatma.php` | wd1-replace |
| Ligures Baebiani | geom | `0101000020E61000002BEFD5070A912D408A4F58BE18914440` | `SRID=4326;POINT(14.811051 41.319407)` | wd1-point |
| Ligures Baebiani | lat | `41.13356761276289` | `41.319407` | wd1-replace |
| Ligures Baebiani | lon | `14.783279652466794` | `14.811051` | wd1-replace |
| Ljuljaci | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ljuljaci | period_start | `-4000` | `NULL` | wd1-clear |
| Ljuljaci | source_url | `https://en.wikipedia.org/wiki/Ljuljaci` | `NULL` | wd1-clear |
| Madghacen | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Madghacen | source_url | `https://en.wikipedia.org/wiki/Madghacen` | `https://en.wikipedia.org/wiki/Medracen` | wd1-replace |
| Margus - City | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Margus - City | period_start | `-500` | `1` | wd1-replace |
| Margus - City | source_url | `https://en.wikipedia.org/wiki/Margus_(city)` | `https://en.wikipedia.org/wiki/Margum_(city)` | wd1-replace |
| Massinissa Mausoleum | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Massinissa Mausoleum | source_url | `https://en.wikipedia.org/wiki/Masinissa` | `https://fr.wikipedia.org/wiki/Souma%C3%A2_du_Khroub` | wd1-replace |
| Monte Adranone | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Monte Adranone | period_start | `-500` | `-600` | wd1-replace |
| Muyu Urqu | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Muyu Urqu | period_start | `1` | `NULL` | wd1-clear |
| Muyu Urqu | site_type | `City/town/settlement` | `Sacred site` | wd1-replace |
| Mynydd Maendy | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Mynydd Maendy | source_url | `https://en.wikipedia.org/wiki/Mynydd_Maendy` | `https://coflein.gov.uk/en/sites/301331` | wd1-replace |
| Naachtun | geom | `0101000020E61000001CBDEE57656F56C0127D4CB171CC3140` | `SRID=4326;POINT(-89.72847 17.79405)` | wd1-point |
| Naachtun | lat | `17.798609810995067` | `17.79405` | wd1-replace |
| Naachtun | lon | `-89.74056051554038` | `-89.72847` | wd1-replace |
| Natural Park Gradistea Muncelului - Cioclovina | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Natural Park Gradistea Muncelului - Cioclovina | period_start | `-100` | `NULL` | wd1-clear |
| Natural Park Gradistea Muncelului - Cioclovina | site_type | `Fortress/citadel` | `Natural feature` | wd1-replace |
| Neuchâtel | geom | `0101000020E61000000BD94AD9AABB1B4089A1BB0805804740` | `SRID=4326;POINT(6.930556 46.990278)` | wd1-point |
| Neuchâtel | lat | `47.00015362893743` | `46.990278` | wd1-replace |
| Neuchâtel | lon | `6.933268923943852` | `6.930556` | wd1-replace |
| Neuchâtel | period_name | `500 BC - 1 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Neuchâtel | period_start | `-500` | `1011` | wd1-replace |
| Nine Ladies Stone Circle | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Nine Ladies Stone Circle | period_start | `-4500` | `-2000` | wd1-replace |
| Numantia | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Numantia | period_start | `-500` | `-2500` | wd1-replace |
| Odysseus Palace | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Odysseus Palace | period_start | `-1500` | `NULL` | wd1-clear |
| Odysseus Palace | site_type | `Necropolis/tombs complex` | `Palace` | wd1-replace |
| Odysseus Palace | source_url | `https://ithaca.org.au/about-ithaca/odysseus-palace` | `https://el.wikipedia.org/wiki/%CE%91%CE%BD%CE%AC%CE%BA%CF%84` | wd1-replace |
| Oinoanda | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Oinoanda | period_start | `1` | `-200` | wd1-replace |
| Oinoanda | site_type | `Megalithic walls` | `City` | wd1-replace |
| Oushiko Shrine | source_url | `https://en.wikipedia.org/wiki/Ishi_no_H%C5%8Dden` | `https://www.city.takasago.lg.jp/soshikikarasagasu/citypromot` | wd1-replace |
| Parco Archeologico Antica Norba | site_type | `Megalithic stones` | `City/town/settlement` | wd1-replace |
| Parco Archeologico Antica Norba | source_url | `https://comune.norma.lt.it/contenuti/38972/antica-norba` | `https://en.wikipedia.org/wiki/Norba` | wd1-replace |
| Peñas de la Cerca | geom | `0101000020E6100000C8441EB019221AC0794DA467B00A4540` | `SRID=4326;POINT(-6.526643 42.064137)` | wd1-point |
| Peñas de la Cerca | lat | `42.0835084488162` | `42.064137` | wd1-replace |
| Peñas de la Cerca | lon | `-6.53330111679788` | `-6.526643` | wd1-replace |
| Peñas de la Cerca | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Peñas de la Cerca | period_start | `-1500` | `NULL` | wd1-clear |
| Pilares do Lena | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pilares do Lena | period_start | `1` | `NULL` | wd1-clear |
| Pistiros | geom | `0101000020E61000009CDDAC02E10B3840A6E67F70F2234540` | `SRID=4326;POINT(24.08927 42.243296)` | wd1-point |
| Pistiros | lat | `42.28083616490521` | `42.243296` | wd1-replace |
| Pistiros | lon | `24.046402136996775` | `24.08927` | wd1-replace |
| Pistiros | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Pistiros | period_start | `-1500` | `-500` | wd1-replace |
| Pistiros | site_type | `Megalithic stones` | `City/town/settlement` | wd1-replace |
| Polygonal Walls (Mura Poligonali) | source_url | `https://en.wikipedia.org/wiki/Amelia,_Umbria` | `https://www.turismoamelia.it/it/esplora-amelia/le-mura-polig` | wd1-replace |
| Poor Lot Barrow Cemetery | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Prebreza | geom | `0101000020E6100000DF30DB374833354050EE659EFAA84540` | `SRID=4326;POINT(21.2455 43.3411)` | wd1-point |
| Prebreza | lat | `43.32014827706428` | `43.3411` | wd1-replace |
| Prebreza | lon | `21.20032071210232` | `21.2455` | wd1-replace |
| Prison of Solomon | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Prison of Solomon | period_start | `-3000` | `-900` | wd1-replace |
| Prison of Solomon | site_type | `Cave Structures` | `Sanctuary` | wd1-replace |
| Pughjaredda | source_url | `https://en.wikipedia.org/wiki/Pughjaredda` | `https://en.wikipedia.org/wiki/Poghjaredda` | wd1-replace |
| Remesiana | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Remesiana | period_start | `1` | `NULL` | wd1-clear |
| Rocca San Felice | geom | `0101000020E610000016C456C65D552E4028DEE3A49E794440` | `SRID=4326;POINT(15.146238 40.974758)` | wd1-point |
| Rocca San Felice | lat | `40.95015393377645` | `40.974758` | wd1-replace |
| Rocca San Felice | lon | `15.166731069652126` | `15.146238` | wd1-replace |
| Rocca San Felice | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Rocca San Felice | source_url | `https://en.wikipedia.org/wiki/Mefitis` | `https://en.wikipedia.org/wiki/Ampsanctus` | wd1-replace |
| Roman Amphitheatre | site_type | `Megalithic structures` | `Amphitheatre` | wd1-replace |
| Roman Dam of Fonte Coberta | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Dam of Fonte Coberta | period_start | `1` | `NULL` | wd1-clear |
| Roman Kilns of El Rinconcillo, Algeciras | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Roman Kilns of El Rinconcillo, Algeciras | period_start | `1` | `-100` | wd1-replace |
| Roman Kilns of El Rinconcillo, Algeciras | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Roman Ruins of Tróia | site_type | `Ruin` | `Settlement` | wd1-replace |
| Roman Theatre, St Albans | geom | `0101000020E610000084E0D4276081D5BFBC510C31A8E04940` | `SRID=4326;POINT(-0.358312 51.754079)` | wd1-point |
| Roman Theatre, St Albans | lat | `51.7551328001168` | `51.754079` | wd1-replace |
| Roman Theatre, St Albans | lon | `-0.3360214604358662` | `-0.358312` | wd1-replace |
| Rubha an Dùnain Passage Grave | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Rubha an Dùnain Passage Grave | period_start | `-3000` | `NULL` | wd1-clear |
| Rubha an Dùnain Passage Grave | site_type | `City/town/settlement` | `Cairn` | wd1-replace |
| Rubha an Dùnain Passage Grave | source_url | `https://en.wikipedia.org/wiki/Rubha_an_D%C3%B9nain` | `https://her.highland.gov.uk/Monument/MHG4901` | wd1-replace |
| Satsurblia Cave | geom | `0101000020E6100000384AF9CCEC4C45408707774F4A304540` | `SRID=4326;POINT(42.606167 42.388111)` | wd1-point |
| Satsurblia Cave | lat | `42.37726777374251` | `42.388111` | wd1-replace |
| Satsurblia Cave | lon | `42.60097658321723` | `42.606167` | wd1-replace |
| Satsurblia Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Satsurblia Cave | period_start | `-500` | `NULL` | wd1-clear |
| Schanzenkopf - Schwedenschanze | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Schanzenkopf - Schwedenschanze | period_start | `-1500` | `NULL` | wd1-clear |
| Schanzenkopf - Schwedenschanze | site_type | `Earthwork` | `Fort` | wd1-replace |
| Schanzenkopf - Schwedenschanze | source_url | `https://en.wikipedia.org/wiki/Schanzenkopf_(Schwedenschanze)` | `https://www.alleburgen.de/bd.php?id=3126` | wd1-replace |
| Seuthopolis | site_type | `Underwater structures` | `City` | wd1-replace |
| Shaji-ki-Dheri | geom | `0101000020E61000004229811852E45140C8D8FE8EDE014140` | `SRID=4326;POINT(71.5918 33.9994)` | wd1-point |
| Shaji-ki-Dheri | lat | `34.014604448735156` | `33.9994` | wd1-replace |
| Shaji-ki-Dheri | lon | `71.5675107251491` | `71.5918` | wd1-replace |
| Shaji-ki-Dheri | site_type | `Temple complex` | `Monastery` | wd1-replace |
| Sigiriya - Peak | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Sigiriya - Peak | period_start | `-500` | `477` | wd1-replace |
| Svingerud Runestone | geom | `0101000020E61000007C36CAA4497E25400BA8582500F54D40` | `SRID=4326;POINT(10.229139 60.102694)` | wd1-point |
| Svingerud Runestone | lat | `59.914066952027575` | `60.102694` | wd1-replace |
| Svingerud Runestone | lon | `10.746655606922324` | `10.229139` | wd1-replace |
| Sybaris on the Traeis | site_type | `City/town/settlement` | `City` | wd1-replace |
| The Hwangnyongsa Belt | geom | `0101000020E61000001C11DDC83F276040F2EA5AE308E54140` | `SRID=4326;POINT(129.2328 35.837)` | wd1-point |
| The Hwangnyongsa Belt | lat | `35.78933374347061` | `35.837` | wd1-replace |
| The Hwangnyongsa Belt | lon | `129.2265362088882` | `129.2328` | wd1-replace |
| The Hwangnyongsa Belt | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| The Hwangnyongsa Belt | period_start | `1` | `553` | wd1-replace |
| The Hwangnyongsa Belt | source_url | `https://en.wikipedia.org/wiki/Gyeongju_Historic_Areas` | `https://en.wikipedia.org/wiki/Hwangnyongsa` | wd1-replace |
| The Sanseong Belt | geom | `0101000020E61000001C11DDC83F276040F2EA5AE308E54140` | `SRID=4326;POINT(129.2583 35.8417)` | wd1-point |
| The Sanseong Belt | lat | `35.78933374347061` | `35.8417` | wd1-replace |
| The Sanseong Belt | lon | `129.2265362088882` | `129.2583` | wd1-replace |
| The Sanseong Belt | source_url | `https://en.wikipedia.org/wiki/Gyeongju_Historic_Areas` | `https://en.wikipedia.org/wiki/Myeonghwalseong` | wd1-replace |
| The Wrekin | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| The Wrekin | source_url | `https://en.wikipedia.org/wiki/The_Wrekin` | `https://www.megalithic.co.uk/article.php?sid=4939` | wd1-replace |
| Tichit | period_name | `3000 - 1500 BC` | `1000 - 1500 AD` | wd1-derive-period-name |
| Tichit | period_start | `-2000` | `1101` | wd1-replace |
| Tichit | source_url | `https://en.wikipedia.org/wiki/Tichi` | `https://en.wikipedia.org/wiki/Tichit` | wd1-replace |
| Tikal | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Tikal | period_start | `1` | `-1000` | wd1-replace |
| Tikal | site_type | `Pyramid complex` | `City/town/settlement, Pyramid complex` | wd1-replace |
| Tikal | source_url | `https://en.wikipedia.org/wiki/Mundo_Perdido,_Tikal` | `https://en.wikipedia.org/wiki/Tikal` | wd1-replace |
| Tombs of the Kings | geom | `0101000020E61000006F836A19399B414086CC043093C83F40` | `SRID=4326;POINT(35.22919 31.78852)` | wd1-point |
| Tombs of the Kings | lat | `31.783495904132472` | `31.78852` | wd1-replace |
| Tombs of the Kings | lon | `35.21268003178454` | `35.22919` | wd1-replace |
| Torralba d'en Salort | site_type | `Megalithic structures` | `Village` | wd1-replace |
| Torralba d'en Salort | source_url | `https://www.illesbalears.travel/tourist-resource/en/menorca/` | `https://ca.wikipedia.org/wiki/Poblat_talai%C3%B2tic_de_Torra` | wd1-replace |
| Tournai-sur-Dive | geom | `0101000020E61000004F5B658312DFA73FCE5CA025FD674840` | `SRID=4326;POINT(0.0415 48.8009)` | wd1-point |
| Tournai-sur-Dive | lat | `48.812412932683955` | `48.8009` | wd1-replace |
| Tournai-sur-Dive | lon | `0.04662378171877057` | `0.0415` | wd1-replace |
| Tournai-sur-Dive | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Tournai-sur-Dive | period_start | `-4500` | `NULL` | wd1-clear |
| Tournai-sur-Dive | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Tournai-sur-Dive | source_url | `https://en.wikipedia.org/wiki/Tournai-sur-Dive` | `https://fr.wikipedia.org/wiki/Pierre_au_Bordeu` | wd1-replace |
| Upper Plym Valley | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Upper Plym Valley | period_start | `-5000` | `NULL` | wd1-clear |
| Upper Plym Valley | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Vescia | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Vescia | period_start | `-500` | `NULL` | wd1-clear |
| Villa Romana de Río Verde | geom | `0101000020E6100000C55389D6748813C06D33241128424240` | `SRID=4326;POINT(-4.94426 36.49577)` | wd1-point |
| Villa Romana de Río Verde | lat | `36.51684774654027` | `36.49577` | wd1-replace |
| Villa Romana de Río Verde | lon | `-4.8832582017248045` | `-4.94426` | wd1-replace |
| Villa Romana de Río Verde | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Villa Romana de Río Verde | period_start | `-500` | `1` | wd1-replace |
| Vindonissa | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Vindonissa | period_start | `1` | `-100` | wd1-replace |
| Vindonissa | site_type | `City/town/settlement` | `Fortress` | wd1-replace |
| White Tank Mountain Regional Park | geom | `0101000020E6100000356D6B5318235CC0319C5B5753CB4040` | `SRID=4326;POINT(-112.51282 33.58664)` | wd1-point |
| White Tank Mountain Regional Park | lat | `33.588480872851854` | `33.58664` | wd1-replace |
| White Tank Mountain Regional Park | lon | `-112.54835973254087` | `-112.51282` | wd1-replace |
| White Tank Mountain Regional Park | source_url | `https://en.wikipedia.org/wiki/White_Tank_Mountain_Regional_P` | `https://www.megalithic.co.uk/article.php?sid=14700` | wd1-replace |
| Wietrzychowice, Kuyavian-Pomeranian Voivodeship | geom | `0101000020E61000004F084BBC01DC324006C4A752AD344A40` | `SRID=4326;POINT(18.874376 52.409181)` | wd1-point |
| Wietrzychowice, Kuyavian-Pomeranian Voivodeship | lat | `52.41153939429937` | `52.409181` | wd1-replace |
| Wietrzychowice, Kuyavian-Pomeranian Voivodeship | lon | `18.859401481932135` | `18.874376` | wd1-replace |
| Wietrzychowice, Kuyavian-Pomeranian Voivodeship | site_type | `Mound/tumulus` | `Barrow` | wd1-replace |
| Wietrzychowice, Kuyavian-Pomeranian Voivodeship | source_url | `https://en.wikipedia.org/wiki/Wietrzychowice,_Kuyavian-Pomer` | `https://pl.wikipedia.org/wiki/Park_Kulturowy_Wietrzychowice` | wd1-replace |
| Yarrows Broch | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Yarrows Broch | period_start | `-500` | `NULL` | wd1-clear |
| Yarrows Broch | site_type | `Underwater structures` | `Minaret/tower` | wd1-replace |
| Yarrows Broch | source_url | `https://en.wikipedia.org/wiki/Iron_Age` | `https://nl.wikipedia.org/wiki/Broch_of_Yarrows` | wd1-replace |
| al-Siq | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| al-Siq | period_start | `1` | `-100` | wd1-replace |
| al-Siq | site_type | `Archaeological site` | `Natural feature` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Roman Dam of Fonte Coberta | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote fetch failed: https://imovel2.patrimoniocultural.gov.pt/detalhes.php?code=69739 (st |
| Cheqollo | lat | `coordinates-unresolved` | Spanish Wikipedia/Wikidata give -13.5704, -71.9957, 12.5 km from the stored point and about 6 km south of central Cusco, |
| Gran Saposoa | lat | `coordinates-unresolved` | Gran Saposoa is a cluster of ruins spread over some 1,000 ha along the Huabayacu valley; the only quotable points are En |
| Vescia | lat | `coordinates-unresolved` | The stored point (and the English Wikipedia coordinates) is the modern village of Vescia near Foligno in Umbria (GeoName |
| Upper Plym Valley | lat | `coordinates-unresolved` | The site is a 15.5 km2 archaeological landscape; only Wikipedia (and pages copying it, such as Wikishire and Archaeolist |
| Bars-Hot | lat | `coordinates-unresolved` | The stored point matches the English Wikipedia point (48°3′13″N 113°22′0″E, the pagoda on the east side of the walled ci |
| Iskuqucha | lat | `coordinates-unresolved` | Wikipedia and Andina place Iskuqucha (Izcucocha) in La Oroya District, Yauli, Junin; Andina adds that it was recorded in |
| Natural Park Gradistea Muncelului - Cioclovina | lat | `coordinates-unresolved` | The site is the Gradistea Muncelului-Cioclovina Natural Park, a 38,000 ha protected area; the park administration only g |
| Hellenistic-Roman Theatre | lat | `coordinates-unresolved` | Only Wikidata prints a point for the ancient theatre on Fabrica hill in Nea Paphos; the OpenStreetMap outline has no quo |
| Sybaris on the Traeis | lat | `coordinates-unresolved` | The stored point is the original Sybaris at Sibari (Parco del Cavallo), a different site; Wikipedia states the exact loc |
| Muyu Urqu | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point for Muyu Urqu (13°32′33″S 71°57′23″W, 22 m from the stored point); the |
| KaʼKabish | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family (and Mapcarta/GeoNames and Archaeolist, which repeat its exact figures) gives a point |
| Aldersgate | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote fetch failed: https://www.hmdb.org/m.asp?m=117103 (status 403); quote fetch failed: |
| Ksar Lalla Fatma | lat | `coordinates-unresolved` | No Wikipedia article, Wikidata item or register entry prints coordinates for Ksar Lalla Fatma (Oued Djenane, El Aioun, E |
| Pughjaredda | lat | `coordinates-unresolved` | The stored point is the war memorial in Sotta village (OSM memorial node at 41.5452, 9.1957), not the site. Lanfranchi a |
| Auquilohuagra | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point for Auquilohuagra (9°46′22″S 76°38′56″W, 1.6 km from the stored point) |
| Ljuljaci | lat | `coordinates-unresolved` | The site is the tumulus necropolis (Krcevine) near the village of Ljuljaci; the only printed coordinates (Wikipedia/Wiki |
| Mynydd Maendy | lat | `coordinates-unresolved` | The stored point (51.5701, -3.4700, also GeoNames' 51.565009, -3.472019 for the hill Mynydd Maendy) is the moorland summ |
| Costa Beck | lat | `coordinates-unresolved` | The stored point is the river's (near its source west of Pickering), while Kitson Clark (YAJ 30, 1931) places the excava |
| Independence Fjord | lat | `coordinates-unresolved` | The stored point is the middle of the 200 km long Independence Fjord itself (a body of water), as given by Wikipedia and |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s002-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s002 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
