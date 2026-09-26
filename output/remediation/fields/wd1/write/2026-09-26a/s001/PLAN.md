# WD1 fields-wd1-2026-09-26a-s001: plan

Built 2026-09-26T20:06:54+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26a_fields-wd1-s001`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26a-s001:<site>:<column>`.

| counter | value |
|---|---|
| sites | 65 |
| cells | 158 |
| sites_written | 63 |
| refused | 16 |
| cells:geom | 12 |
| cells:lat | 12 |
| cells:lon | 12 |
| cells:period_name | 37 |
| cells:period_start | 37 |
| cells:site_type | 27 |
| cells:source_url | 21 |
| refused:coordinates-unresolved | 15 |
| refused:country-changes | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Adulis | geom | `0101000020E61000007036A06F76D843406AE750F8408C2E40` | `SRID=4326;POINT(39.6606 15.2636)` | wd1-point |
| Adulis | lat | `15.273933181644413` | `15.2636` | wd1-replace |
| Adulis | lon | `39.69111438105472` | `39.6606` | wd1-replace |
| Adulis | site_type | `Temple complex` | `City` | wd1-replace |
| Amelungsburg, Süntel | site_type | `Earthwork` | `Fortification` | wd1-replace |
| Amsa-dong | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Amsa-dong | period_start | `-3000` | `-4000` | wd1-replace |
| Ancient Roman Theatre | site_type | `Amphitheatre` | `Theatre` | wd1-replace |
| Ancient Roman Theatre | source_url | `https://ask-aladdin.com/egypt-sites/greco-roman-monuments/ro` | `https://ar.wikipedia.org/wiki/%D8%A7%D9%84%D9%85%D8%B3%D8%B1` | wd1-replace |
| Apolyanka | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Apolyanka | period_start | `-4500` | `NULL` | wd1-clear |
| Apolyanka | source_url | `https://en.wikipedia.org/wiki/Apolyanka` | `NULL` | wd1-clear |
| Aquae Calidae, Bulgaria | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Aquae Calidae, Bulgaria | period_start | `1` | `-500` | wd1-replace |
| Aquae Calidae, Bulgaria | site_type | `Bath` | `City/town/settlement` | wd1-replace |
| Archaeological Site of Tamassos | geom | `0101000020E61000005A6C7E32699F40400506303EC4864140` | `SRID=4326;POINT(33.242186 35.028422)` | wd1-point |
| Archaeological Site of Tamassos | lat | `35.05286385865114` | `35.028422` | wd1-replace |
| Archaeological Site of Tamassos | lon | `33.245397865038015` | `33.242186` | wd1-replace |
| Bahrain’s Dilmun Burial Mounds - Janabiyah Burial Field | source_url | `https://en.wikipedia.org/wiki/Janabiyah` | `https://archiqoo.com/locations/janabiyah_burials.php` | wd1-replace |
| Beeley Moor | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Beeley Moor | period_start | `-4500` | `NULL` | wd1-clear |
| Beeley Moor | source_url | `https://en.wikipedia.org/wiki/Beeley_Moor` | `https://her.derbyshire.gov.uk/Monument/MDR10069` | wd1-replace |
| Boleigh Fogou | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Boleigh Fogou | period_start | `-1000` | `NULL` | wd1-clear |
| Boleigh Fogou | site_type | `Infrastructure` | `Cave Structures` | wd1-replace |
| Brean Down | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Brean Down | period_start | `-1000` | `NULL` | wd1-clear |
| Brean Down | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Brean Down | source_url | `https://en.wikipedia.org/wiki/Brean_Down` | `https://www.megalithic.co.uk/article.php?sid=25260` | wd1-replace |
| Burrough Hill | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Burrough Hill | period_start | `-1000` | `-500` | wd1-replace |
| Caer Caradoc | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Caer Caradoc | period_start | `-1500` | `NULL` | wd1-clear |
| Caer Caradoc | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Caer Caradoc | source_url | `https://en.wikipedia.org/wiki/Caer_Caradoc` | `https://www.megalithic.co.uk/article.php?sid=4931` | wd1-replace |
| Castle Crag | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castle Crag | period_start | `-1000` | `NULL` | wd1-clear |
| Castle Crag | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Castle Crag | source_url | `https://en.wikipedia.org/wiki/Castle_Crag` | `https://www.megalithic.co.uk/article.php?sid=13326` | wd1-replace |
| Caves and Ice Age Art in the Swabian Jura | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Caves and Ice Age Art in the Swabian Jura | period_start | `-500` | `NULL` | wd1-clear |
| Cup and Ring marks, Kilmartin Glen | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Cup and Ring marks, Kilmartin Glen | period_start | `-500` | `-3000` | wd1-replace |
| Cup and Ring marks, Kilmartin Glen | source_url | `https://en.wikipedia.org/wiki/Kilmartin_Glen` | `https://www.kilmartin.org/why-excavate-rock-art` | wd1-replace |
| Dodman Point | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dodman Point | period_start | `-1000` | `NULL` | wd1-clear |
| Dodman Point | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Dodman Point | source_url | `https://en.wikipedia.org/wiki/Dodman_Point` | `https://www.megalithic.co.uk/article.php?sid=1167621741` | wd1-replace |
| Dur-Kurigalzu (Ziggurat at Aqar Quf) | geom | `0101000020E6100000645CF417C7194640E0FC6607A6AE4040` | `SRID=4326;POINT(44.20222 33.35361)` | wd1-point |
| Dur-Kurigalzu (Ziggurat at Aqar Quf) | lat | `33.364441800391205` | `33.35361` | wd1-replace |
| Dur-Kurigalzu (Ziggurat at Aqar Quf) | lon | `44.201388353649946` | `44.20222` | wd1-replace |
| Dur-Kurigalzu (Ziggurat at Aqar Quf) | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Dur-Kurigalzu (Ziggurat at Aqar Quf) | period_start | `-3000` | `-1400` | wd1-replace |
| El Baúl | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| El Baúl | period_start | `-1500` | `NULL` | wd1-clear |
| Govurqala, Nakhchivan | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Govurqala, Nakhchivan | period_start | `-500` | `-3000` | wd1-replace |
| Halos, Delphi | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Halos, Delphi | period_start | `-500` | `NULL` | wd1-clear |
| Halos, Delphi | site_type | `Megalithic structures` | `Sacred site` | wd1-replace |
| Harold's Stones, Trellech | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Harold's Stones, Trellech | period_start | `-4500` | `-2300` | wd1-replace |
| Harold's Stones, Trellech | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Harold's Stones, Trellech | source_url | `https://en.wikipedia.org/wiki/Trellech` | `https://de.wikipedia.org/wiki/Harold%E2%80%99s_Stones` | wd1-replace |
| Haughey's Fort | geom | `0101000020E6100000EC67F3BB3F091BC006C5FCD32B2C4B40` | `SRID=4326;POINT(-6.716488 54.349479)` | wd1-point |
| Haughey's Fort | lat | `54.3450875267245` | `54.349479` | wd1-replace |
| Haughey's Fort | lon | `-6.759032189112968` | `-6.716488` | wd1-replace |
| Helgö | source_url | `https://en.wikipedia.org/wiki/Helg%C3%B6` | `https://www.megalithic.co.uk/article.php?sid=63813` | wd1-replace |
| Hengistbury Head | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Hengistbury Head | period_start | `-3000` | `NULL` | wd1-clear |
| Hierapolis | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Hierapolis | period_start | `-500` | `NULL` | wd1-clear |
| Hound Tor | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Hound Tor | period_start | `-1000` | `-1700` | wd1-replace |
| Hound Tor | source_url | `https://en.wikipedia.org/wiki/Hound_Tor` | `https://en.wikipedia.org/wiki/Hundatorra` | wd1-replace |
| Hypostyle Hall | site_type | `Megalithic structures` | `Temple` | wd1-replace |
| Kutaisi | geom | `0101000020E6100000008492779D594540D228C2FFFF1F4540` | `SRID=4326;POINT(42.7001 42.2698)` | wd1-point |
| Kutaisi | lat | `42.24999997120325` | `42.2698` | wd1-replace |
| Kutaisi | lon | `42.700118013897736` | `42.7001` | wd1-replace |
| Lagentium | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Laguna de las Momias | site_type | `Cave Structures` | `Necropolis/tombs complex` | wd1-replace |
| Lamanai Archaeological Reserve | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Lamanai Archaeological Reserve | period_start | `-3000` | `-1500` | wd1-replace |
| Lewesdon Hill | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Lewesdon Hill | period_start | `-2000` | `NULL` | wd1-clear |
| Lewesdon Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Lewesdon Hill | source_url | `https://en.wikipedia.org/wiki/Lewesdon_Hill` | `https://heritage.dorsetcouncil.gov.uk/Monument/MDO532` | wd1-replace |
| Llanfihangel Din Sylwy | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Llanfihangel Din Sylwy | period_start | `-1000` | `-500` | wd1-replace |
| Llanfihangel Din Sylwy | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Llanfihangel Din Sylwy | source_url | `https://en.wikipedia.org/wiki/Llanfihangel_Din_Sylwy` | `https://en.wikipedia.org/wiki/Bwrdd_Arthur` | wd1-replace |
| Lynford Quarry | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Lynford Quarry | period_start | `-500` | `NULL` | wd1-clear |
| Lyrbe | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Lyrbe | period_start | `1` | `-400` | wd1-replace |
| Lyrbe | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Macellum of Pompeii | site_type | `City/town/settlement` | `Forum` | wd1-replace |
| Niedertiefenbach - Megalithic Tomb | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Nine Stones, Winterbourne Abbas | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Nine Stones, Winterbourne Abbas | period_start | `-4500` | `NULL` | wd1-clear |
| Obelisk of Ark | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Obelisk of Ark | period_start | `-500` | `301` | wd1-replace |
| Pagar Alam | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pagar Alam | period_start | `100` | `NULL` | wd1-clear |
| Peregonivka | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Peregonivka | period_start | `-4500` | `NULL` | wd1-clear |
| Peregonivka | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Peregonivka | source_url | `https://en.wikipedia.org/wiki/Peregonivka` | `NULL` | wd1-clear |
| Poggioreale, Naples | geom | `0101000020E6100000E0EB6975BF992C4093483210FF6E4440` | `SRID=4326;POINT(14.283356 40.867639)` | wd1-point |
| Poggioreale, Naples | lat | `40.867158913185584` | `40.867639` | wd1-replace |
| Poggioreale, Naples | lon | `14.30028883855806` | `14.283356` | wd1-replace |
| Poggioreale, Naples | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Poggioreale, Naples | period_start | `-1500` | `-500` | wd1-replace |
| Poggioreale, Naples | source_url | `https://en.wikipedia.org/wiki/Poggioreale_(Naples)` | `https://www.roadtvitalia.it/cava-greca-poggioreale-stata-dan` | wd1-replace |
| Praetorium Agrippinae | site_type | `Fortification` | `Fort` | wd1-replace |
| Ranigat | site_type | `City/town/settlement` | `Monastery` | wd1-replace |
| Rispebjerg | geom | `0101000020E6100000810471DBC0A82D40E8B45FCDCF934B40` | `SRID=4326;POINT(15.011062 55.026589)` | wd1-point |
| Rispebjerg | lat | `55.15477912114312` | `55.026589` | wd1-replace |
| Rispebjerg | lon | `14.829596383615582` | `15.011062` | wd1-replace |
| Satellite Pyramid (to Bent Pyramid) | source_url | `https://en.wikipedia.org/wiki/Bent_Pyramid` | `https://it.wikipedia.org/wiki/Piramide_satellite_meridionale` | wd1-replace |
| Sicyonian Treasury | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Stabiae | source_url | `https://en.wikipedia.org/wiki/Temples_(band)` | `https://en.wikipedia.org/wiki/Stabiae` | wd1-replace |
| Suburban Baths, Pompeii | site_type | `Megalithic structures` | `Bath` | wd1-replace |
| Sun Temple of Niuserre (Abu Ghorab) | source_url | `https://en.wikipedia.org/wiki/Egyptian_sun_temple` | `https://de.wikipedia.org/wiki/Sonnenheiligtum_des_Niuserre` | wd1-replace |
| Tel Hermal Fort | geom | `0101000020E6100000EA7654E6A63B46405778B8A99AA94040` | `SRID=4326;POINT(44.467065 33.309483)` | wd1-point |
| Tel Hermal Fort | lat | `33.32503243930176` | `33.309483` | wd1-replace |
| Tel Hermal Fort | lon | `44.4660308754372` | `44.467065` | wd1-replace |
| Tel Hermal Fort | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Tel Hermal Fort | period_start | `-4500` | `-3000` | wd1-replace |
| Tel Hermal Fort | site_type | `Fortress/citadel` | `City/town/settlement` | wd1-replace |
| Temple of Hatra | geom | `0101000020E6100000861F45D8475D454009AB1A55C2D04140` | `SRID=4326;POINT(42.71833 35.58806)` | wd1-point |
| Temple of Hatra | lat | `35.630930555364166` | `35.58806` | wd1-replace |
| Temple of Hatra | lon | `42.72875502944139` | `42.71833` | wd1-replace |
| Thibilis | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Thibilis | period_start | `1` | `NULL` | wd1-clear |
| Thracian Tomb, Shushmanets | geom | `0101000020E610000073251687E46139402C1C34A554584540` | `SRID=4326;POINT(25.348682 42.706968)` | wd1-point |
| Thracian Tomb, Shushmanets | lat | `42.69008317036091` | `42.706968` | wd1-replace |
| Thracian Tomb, Shushmanets | lon | `25.38239330568963` | `25.348682` | wd1-replace |
| Tsagaan Salaa Rock Paintings | geom | `0101000020E61000009BF3CFA0C42E5640CEB152CF273F4840` | `SRID=4326;POINT(88.3954 49.334)` | wd1-point |
| Tsagaan Salaa Rock Paintings | lat | `48.49340240037746` | `49.334` | wd1-replace |
| Tsagaan Salaa Rock Paintings | lon | `88.73075123126766` | `88.3954` | wd1-replace |
| Tsagaan Salaa Rock Paintings | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Tsagaan Salaa Rock Paintings | period_start | `-11000` | `NULL` | wd1-clear |
| Tyre World Heritage Site - Necropolis | geom | `0101000020E61000006AFF90B25D994140BE791B2191A24040` | `SRID=4326;POINT(35.20972 33.27222)` | wd1-point |
| Tyre World Heritage Site - Necropolis | lat | `33.27005399552898` | `33.27222` | wd1-replace |
| Tyre World Heritage Site - Necropolis | lon | `35.198171921538986` | `35.20972` | wd1-replace |
| Urpish | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Urpish | period_start | `1` | `NULL` | wd1-clear |
| Urpish | site_type | `Megalithic structures` | `Fortress/citadel` | wd1-replace |
| Valley of the Thracian Rulers | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Valley of the Thracian Rulers | period_start | `-2000` | `-500` | wd1-replace |
| Wet Withens | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Wet Withens | period_start | `-4500` | `NULL` | wd1-clear |
| Wet Withens | site_type | `Henge` | `Stone circle` | wd1-replace |
| White Sheet Hill | source_url | `https://en.wikipedia.org/wiki/White_Sheet_Hill` | `https://www.megalithic.co.uk/article.php?sid=5105` | wd1-replace |
| Winnemucca Lake Petroglyphs | source_url | `https://en.wikipedia.org/wiki/Winnemucca_Lake` | `https://www.usgs.gov/publications/dating-north-americas-olde` | wd1-replace |
| Wiraqucha Pirqa | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wiraqucha Pirqa | period_start | `1` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Apolyanka | lat | `coordinates-unresolved` | The stored point is the OpenStreetMap node of Apolianka village itself (48.7361, 30.4043); the Trypillia site lies on th |
| Govurqala, Nakhchivan | lat | `coordinates-unresolved` | The site is the Bronze Age Govurqala by Shahtakhti (Kangarli district), 35 km north-west of Nakhchivan on the left bank  |
| Pagar Alam | lat | `coordinates-unresolved` | Pagar Alam is a modern city whose Pasemah megaliths 'surround the town on all sides' (Tegur Wangi, Tanjung Aro, Belumai, |
| Brean Down | lat | `coordinates-unresolved` | The site is the small Iron Age hillfort, which the Somerset HER (record 10115, 'At the E end of Brean Down', ST 298 588) |
| Laguna de las Momias | lat | `coordinates-unresolved` | Only Wikipedia (English -6.85, -77.70 and Spanish -6.8506, -77.6931, one source family) prints a point in a readable for |
| Peregonivka | lat | `coordinates-unresolved` | The stored point equals the Wikidata item Q18210819 (48.5337, 30.3834, carried over from a deleted Wikipedia stub), whic |
| Valley of the Thracian Rulers | lat | `coordinates-unresolved` | The site is a valley-wide Thracian necropolis of some 1,500 tumuli, not one monument, and the sources place it at unrela |
| Winnemucca Lake Petroglyphs | lat | `coordinates-unresolved` | The stored point is the centre of the dry Winnemucca Lake bed (Wikipedia/Wikidata of the lake), while the petroglyph sit |
| Bahrain’s Dilmun Burial Mounds - Janabiyah Burial Field | lat | `coordinates-unresolved` | The Janabiyah Burial Mound Field (World Heritage component 1542-021) is given a point only by its Wikidata item Q6595405 |
| Els Munts - Roman Villa | lat | `country-changes` | the new point lies in [], the site says Spain |
| Halos, Delphi | lat | `coordinates-unresolved` | Only Wikidata (and the Wikipedia-derived mirrors of it) print a point for the Halos; the Historical Marker Database page |
| Helgö | lat | `coordinates-unresolved` | The site is the Iron Age trading and workshop settlement on Helgö, which Swedish Wikipedia places on the north-eastern p |
| Cup and Ring marks, Kilmartin Glen | lat | `coordinates-unresolved` | The entry is the collective cup-and-ring rock art of Kilmartin Glen, spread over separate panels (Achnabreck about 56.06 |
| Lynford Quarry | lat | `coordinates-unresolved` | The excavated Middle Palaeolithic site lies at NHER grid reference TL 8240 9484, which the Megalithic Portal gives as 52 |
| Urpish | lat | `coordinates-unresolved` | The stored point equals English Wikipedia's minute-rounded 9°17′S 76°44′W and is about 1.1 km from the site: the Peruvia |
| Wiraqucha Pirqa | lat | `coordinates-unresolved` | Only the English Wikipedia family (and its copies such as Archaeolist) gives the stored point (13.5307 S, 75.3456 W). Wi |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26a_fields-wd1-s001-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26a-s001 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
