# WD1 fields-wd1-2026-09-26b-s005: plan

Built 2026-09-30T05:58:39+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s005`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s005:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 258 |
| sites_written | 99 |
| refused | 22 |
| cells:geom | 24 |
| cells:lat | 24 |
| cells:lon | 24 |
| cells:period_name | 46 |
| cells:period_start | 46 |
| cells:site_type | 65 |
| cells:source_url | 29 |
| refused:coordinates-unresolved | 20 |
| refused:country-changes | 1 |
| refused:held-unreadable | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Aballava | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Ahin Posh Tape | geom | `0101000020E6100000C4D638F621BD5140BCBD056681D54040` | `SRID=4326;POINT(70.451 34.406)` | wd1-point |
| Ahin Posh Tape | lat | `33.66801142959909` | `34.406` | wd1-replace |
| Ahin Posh Tape | lon | `70.95519786406209` | `70.451` | wd1-replace |
| Ahin Posh Tape | site_type | `Temple complex` | `Monastery` | wd1-replace |
| Akkale | site_type | `Ruin` | `Settlement` | wd1-replace |
| Al Hajar Burial Mound Field | geom | `0101000020E61000009834EBD8873E4940D9FC9556122A3A40` | `SRID=4326;POINT(50.514947 26.216683)` | wd1-point |
| Al Hajar Burial Mound Field | lat | `26.164342319124305` | `26.216683` | wd1-replace |
| Al Hajar Burial Mound Field | lon | `50.48852073177949` | `50.514947` | wd1-replace |
| Alexandria Arachosia - Old Kandahar | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Alexandria Arachosia - Old Kandahar | period_start | `-500` | `-1000` | wd1-replace |
| Alexandria Arachosia - Old Kandahar | site_type | `Fortress/citadel` | `City` | wd1-replace |
| Altar of Athena Polias | site_type | `Megalithic structures` | `Sacred site` | wd1-replace |
| Anku | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Anku | period_start | `1` | `NULL` | wd1-clear |
| Anku | site_type | `City/town/settlement` | `Citadel` | wd1-replace |
| Archaeological Site of Pnyx | site_type | `Megalithic stones` | `Archaeological site` | wd1-replace |
| Armeni - Archaeological Site | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Armeni - Archaeological Site | period_start | `-2000` | `-1400` | wd1-replace |
| Armeni - Archaeological Site | source_url | `https://en.wikipedia.org/wiki/Armeni_(archaeological_site)` | `https://en.wikipedia.org/wiki/Armenoi_(archaeological_site)` | wd1-replace |
| Arsemia Ören Yeri | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Arsemia Ören Yeri | period_start | `1` | `-300` | wd1-replace |
| Arsemia Ören Yeri | site_type | `Temple complex` | `City` | wd1-replace |
| Astale | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Astale | period_start | `-500` | `NULL` | wd1-clear |
| Aubrey Holes - Stonehenge | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Aubrey Holes - Stonehenge | period_start | `-4500` | `-3000` | wd1-replace |
| Aubrey Holes - Stonehenge | site_type | `Timber circle` | `Cemetery` | wd1-replace |
| Aulanko Castle | geom | `0101000020E6100000CCDF9360C772384041CC9FFDD2824E40` | `SRID=4326;POINT(24.47056 61.02264)` | wd1-point |
| Aulanko Castle | lat | `61.02206392576819` | `61.02264` | wd1-replace |
| Aulanko Castle | lon | `24.448354755498983` | `24.47056` | wd1-replace |
| Aulanko Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Aulanko Castle | period_start | `-1500` | `NULL` | wd1-clear |
| Bardal Rock Carvings | geom | `0101000020E61000002006A59C1370274000021591B8035040` | `SRID=4326;POINT(11.391063 64.044804)` | wd1-point |
| Bardal Rock Carvings | lat | `64.05814005900902` | `64.044804` | wd1-replace |
| Bardal Rock Carvings | lon | `11.7188996268697` | `11.391063` | wd1-replace |
| Boca de Potrerillos | site_type | `Rock art` | `Petroglyphs` | wd1-replace |
| Bow Hill, Sussex | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Bow Hill, Sussex | period_start | `-4500` | `NULL` | wd1-clear |
| Bow Hill, Sussex | site_type | `Mound/tumulus` | `Barrow` | wd1-replace |
| Bow Hill, Sussex | source_url | `https://en.wikipedia.org/wiki/Bow_Hill,_Sussex` | `https://en.wikipedia.org/wiki/Bow_Hill,_West_Sussex` | wd1-replace |
| Brean Down Fort | period_name | `1500 - 500 BC` | `1500+ AD` | wd1-derive-period-name |
| Brean Down Fort | period_start | `-1500` | `1864` | wd1-replace |
| Bryn Eryr | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bryn Eryr | period_start | `-1500` | `NULL` | wd1-clear |
| Bryn Eryr | site_type | `Residence/villa/farmhouse` | `Settlement` | wd1-replace |
| Burnham Beeches | geom | `0101000020E6100000CF93D040152AE4BF62D20B9203C84940` | `SRID=4326;POINT(-0.635376 51.552888)` | wd1-point |
| Burnham Beeches | lat | `51.56260896279561` | `51.552888` | wd1-replace |
| Burnham Beeches | lon | `-0.630137087432212` | `-0.635376` | wd1-replace |
| Burnham Beeches | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Burnham Beeches | period_start | `-1000` | `NULL` | wd1-clear |
| Burnham Beeches | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Burnham Beeches | source_url | `https://en.wikipedia.org/wiki/Burnham_Beeches` | `https://heritageportal.buckinghamshire.gov.uk/Monument/MBC46` | wd1-replace |
| Büyük Hamam | source_url | `https://en.wikipedia.org/wiki/Phaselis` | `https://kulturenvanteri.com/yer/phaselis-buyuk-hamam/` | wd1-replace |
| Castle Of Urfa | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Castle Of Urfa | period_start | `-132` | `201` | wd1-replace |
| Castle Of Urfa | site_type | `Fortress/citadel` | `Castle` | wd1-replace |
| Castro of Monte Castelo | geom | `0101000020E6100000F0BD45F48D4221C00AC7FC9F9E994440` | `SRID=4326;POINT(-8.678481 41.200405)` | wd1-point |
| Castro of Monte Castelo | lat | `41.20015334932948` | `41.200405` | wd1-replace |
| Castro of Monte Castelo | lon | `-8.6299892745146` | `-8.678481` | wd1-replace |
| Chichén Itzá | site_type | `Pyramid complex` | `City/town/settlement, Pyramid complex` | wd1-replace |
| Cleeve Hill, Gloucestershire | geom | `0101000020E6100000D23377A45B0E00C02FD0C8ADC6F54940` | `SRID=4326;POINT(-2.0233 51.92775)` | wd1-point |
| Cleeve Hill, Gloucestershire | lat | `51.92012569718678` | `51.92775` | wd1-replace |
| Cleeve Hill, Gloucestershire | lon | `-2.007010731590051` | `-2.0233` | wd1-replace |
| Cleeve Hill, Gloucestershire | period_name | `4500 - 3000 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Cleeve Hill, Gloucestershire | period_start | `-4500` | `-700` | wd1-replace |
| Cleeve Hill, Gloucestershire | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Cleeve Hill, Gloucestershire | source_url | `https://en.wikipedia.org/wiki/Cleeve_Hill,_Gloucestershire` | `https://www.megalithic.co.uk/article.php?sid=4693` | wd1-replace |
| Coldrum Long Barrow | site_type | `Megalithic stones` | `Barrow` | wd1-replace |
| Craménil | geom | `0101000020E61000001CCDC26A0820D8BF6AAE0BB9615F4840` | `SRID=4326;POINT(-0.3597 48.7559)` | wd1-point |
| Craménil | lat | `48.74516976423622` | `48.7559` | wd1-replace |
| Craménil | lon | `-0.3769551317775084` | `-0.3597` | wd1-replace |
| Craménil | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Craménil | period_start | `-4500` | `NULL` | wd1-clear |
| Craménil | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Craménil | source_url | `https://en.wikipedia.org/wiki/Cram%C3%A9nil` | `https://fr.wikipedia.org/wiki/Affiloir_de_Gargantua` | wd1-replace |
| Crantit Chambered Cairn | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Crantit Chambered Cairn | period_start | `-3000` | `NULL` | wd1-clear |
| Crantit Chambered Cairn | source_url | `https://en.wikipedia.org/wiki/History` | `https://de.wikipedia.org/wiki/Crantit_Cairn` | wd1-replace |
| Cusichaca River | geom | `0101000020E6100000DB847F9BAE0752C005370DF0D09E2AC0` | `SRID=4326;POINT(-72.43 -13.22611)` | wd1-point |
| Cusichaca River | lat | `-13.310187818158292` | `-13.22611` | wd1-replace |
| Cusichaca River | lon | `-72.12003219082855` | `-72.43` | wd1-replace |
| Cusichaca River | period_name | `1000 - 1500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Cusichaca River | period_start | `1000` | `-700` | wd1-replace |
| Delphinion | source_url | `https://en.wikipedia.org/wiki/Delphinion` | `https://es.wikipedia.org/wiki/Delfinio_de_Mileto` | wd1-replace |
| Demetrias | geom | `0101000020E61000006CD2F4122DE93640F9B98A528BAC4340` | `SRID=4326;POINT(22.9243 39.3434)` | wd1-point |
| Demetrias | lat | `39.34800178312066` | `39.3434` | wd1-replace |
| Demetrias | lon | `22.910844025393473` | `22.9243` | wd1-replace |
| Demre | geom | `0101000020E6100000DEE9FE26C0FC3D40312F136E9B1F4240` | `SRID=4326;POINT(29.984238 36.25869)` | wd1-point |
| Demre | lat | `36.24693084656463` | `36.25869` | wd1-replace |
| Demre | lon | `29.987307011828186` | `29.984238` | wd1-replace |
| Demre | source_url | `https://en.wikipedia.org/wiki/Demre` | `https://www.kulturportali.gov.tr/portal/demre-nekropolu` | wd1-replace |
| Dharmarajika Stupa | geom | `0101000020E6100000BBBF1AFEEA31524075D5CF2574DD4040` | `SRID=4326;POINT(72.842119 33.744544)` | wd1-point |
| Dharmarajika Stupa | lat | `33.730107046586376` | `33.744544` | wd1-replace |
| Dharmarajika Stupa | lon | `72.77996780979349` | `72.842119` | wd1-replace |
| Dharmarajika Stupa | site_type | `Temple complex` | `Monastery` | wd1-replace |
| Earthen Fortification, Pungnap-dong | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Earthen Fortification, Pungnap-dong | period_start | `-18` | `201` | wd1-replace |
| Earthen Fortification, Pungnap-dong | source_url | `https://en.wikipedia.org/wiki/Pungnaptoseong` | `https://en.wikipedia.org/wiki/P%27ungnapt%27os%C5%8Fng` | wd1-replace |
| Elephanta Caves | site_type | `Temple complex` | `Cave Structures` | wd1-replace |
| Fin Cop | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Furby | period_name | `500 - 1000 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Furby | period_start | `500` | `1200` | wd1-replace |
| Furby | site_type | `Mound/tumulus` | `Church` | wd1-replace |
| Furby | source_url | `https://en.wikipedia.org/wiki/Furby,_Sweden` | `https://kulturarvvastmanland.se/databas/plats/vasteras/furby` | wd1-replace |
| Großmugl | geom | `0101000020E61000006D4FF34BFF3F3040BCB507DC25424840` | `SRID=4326;POINT(16.22312 48.48833)` | wd1-point |
| Großmugl | lat | `48.51678038002453` | `48.48833` | wd1-replace |
| Großmugl | lon | `16.24998926820938` | `16.22312` | wd1-replace |
| Großmugl | source_url | `https://en.wikipedia.org/wiki/Gro%C3%9Fmugl` | `https://de.wikipedia.org/wiki/Leeberg_(Gro%C3%9Fmugl)` | wd1-replace |
| Gymnasium, Delphi | site_type | `Megalithic structures` | `Bath` | wd1-replace |
| Gyrton, Thessaly | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Gyrton, Thessaly | period_start | `-2000` | `NULL` | wd1-clear |
| Hatun Misapata | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Hatun Misapata | period_start | `600` | `NULL` | wd1-clear |
| Hatun Misapata | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Heidetrank Oppidum | site_type | `Fortress/citadel` | `Settlement` | wd1-replace |
| Huillca Raccay | geom | `0101000020E610000019896647D61052C0CA35A6ECAF832AC0` | `SRID=4326;POINT(-72.423484 -13.235413)` | wd1-point |
| Huillca Raccay | lat | `-13.257201571740456` | `-13.235413` | wd1-replace |
| Huillca Raccay | lon | `-72.26307854665028` | `-72.423484` | wd1-replace |
| Huillca Raccay | period_name | `1000 - 1500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Huillca Raccay | period_start | `1400` | `-600` | wd1-replace |
| Inkachaka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inkachaka | period_start | `1400` | `NULL` | wd1-clear |
| Inkachaka | site_type | `City/town/settlement` | `Bridge` | wd1-replace |
| Jach'a Phasa | period_name | `1 - 500 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Jach'a Phasa | period_start | `1` | `1323` | wd1-replace |
| Kalaureia | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Kalaureia | source_url | `https://en.wikipedia.org/wiki/Kalaureia` | `https://de.wikipedia.org/wiki/Poseidon-Heiligtum_von_Kalaure` | wd1-replace |
| Katalymata ton Plakoton | period_name | `1500 - 500 BC` | `500 - 1000 AD` | wd1-derive-period-name |
| Katalymata ton Plakoton | period_start | `-1000` | `617` | wd1-replace |
| Katalymata ton Plakoton | site_type | `Temple complex` | `Church` | wd1-replace |
| Khoit Tsenkher Cave Rock Art | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Khoit Tsenkher Cave Rock Art | period_start | `-20000` | `NULL` | wd1-clear |
| La Parisienne - Fresco | geom | `0101000020E6100000E9C7B79911233940984826345EAB4140` | `SRID=4326;POINT(25.16306 35.29806)` | wd1-point |
| La Parisienne - Fresco | lat | `35.33881236905398` | `35.29806` | wd1-replace |
| La Parisienne - Fresco | lon | `25.136987311714538` | `25.16306` | wd1-replace |
| La Parisienne - Fresco | site_type | `Rock art` | `NULL` | wd1-clear |
| Le Grand-Pressigny | period_name | `< 4500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Le Grand-Pressigny | period_start | `-5000` | `-2800` | wd1-replace |
| Le Grand-Pressigny | source_url | `https://en.wikipedia.org/wiki/Le_Grand-Pressigny` | `https://de.wikipedia.org/wiki/Feuersteinmine_Le_Grand-Pressi` | wd1-replace |
| Lees Hall Roman Camp | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Lees Hall Roman Camp | period_start | `1` | `NULL` | wd1-clear |
| Lees Hall Roman Camp | site_type | `Archaeological site` | `Military` | wd1-replace |
| Little Meg | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Little Meg | period_start | `-2500` | `NULL` | wd1-clear |
| Little Meg | site_type | `Stone circle` | `Cairn` | wd1-replace |
| Lydney Park | site_type | `City/town/settlement` | `Temple complex` | wd1-replace |
| Megarian Treasury, Delphi | site_type | `Megalithic structures` | `Temple` | wd1-replace |
| Megarian Treasury, Olympia | site_type | `Megalithic structures` | `Temple` | wd1-replace |
| Mersinaki | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Mersinaki | period_start | `-1500` | `NULL` | wd1-clear |
| Mersinaki | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Meydan Castle | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Meydan Castle | period_start | `-500` | `NULL` | wd1-clear |
| Midsummer Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Midsummer Hill | source_url | `https://en.wikipedia.org/wiki/Midsummer_Hill` | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord` | wd1-replace |
| Mitla | period_name | `1000 - 1500 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Mitla | period_start | `1000` | `200` | wd1-replace |
| Miyu Pampa | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Miyu Pampa | period_start | `1` | `NULL` | wd1-clear |
| Miyu Pampa | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Mount Juktas | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Mount Juktas | source_url | `https://en.wikipedia.org/wiki/Mount_Juktas` | `http://www.minoancrete.com/juktas.htm` | wd1-replace |
| Mount Namsan Belt | geom | `0101000020E61000001C11DDC83F276040F2EA5AE308E54140` | `SRID=4326;POINT(129.225556 35.768056)` | wd1-point |
| Mount Namsan Belt | lat | `35.78933374347061` | `35.768056` | wd1-replace |
| Mount Namsan Belt | lon | `129.2265362088882` | `129.225556` | wd1-replace |
| Mount Namsan Belt | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Mount Namsan Belt | period_start | `1` | `NULL` | wd1-clear |
| Mount Namsan Belt | site_type | `Rock relief/carving` | `Sacred site` | wd1-replace |
| Mount Namsan Belt | source_url | `https://en.wikipedia.org/wiki/Gyeongju_Historic_Areas` | `https://en.wikipedia.org/wiki/Namsan_(Gyeongju)` | wd1-replace |
| Murujuga | site_type | `Rock art` | `Petroglyphs` | wd1-replace |
| Murujuga | source_url | `https://en.wikipedia.org/wiki/Murujuga` | `https://en.wikipedia.org/wiki/Burrup_Peninsula` | wd1-replace |
| Oricum Archaeological Park | site_type | `Megalithic stones` | `City` | wd1-replace |
| Osirion | site_type | `Megalithic structures` | `Funerary` | wd1-replace |
| Parque Arqueológico do Solstício | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Parque Arqueológico do Solstício | period_start | `1` | `NULL` | wd1-clear |
| Parque Arqueológico do Solstício | site_type | `Megalithic stones` | `Stone circle` | wd1-replace |
| Peppercombe Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Peppercombe Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Peppercombe Castle | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Peppercombe Castle | source_url | `https://en.wikipedia.org/wiki/Peppercombe` | `https://www.megalithic.co.uk/article.php?sid=7764` | wd1-replace |
| Peñas de Cabrera | geom | `0101000020E61000009799EA4806B811C0729AA8E683724240` | `SRID=4326;POINT(-4.387961 36.895085)` | wd1-point |
| Peñas de Cabrera | lat | `36.894650299383` | `36.895085` | wd1-replace |
| Peñas de Cabrera | lon | `-4.429711474722715` | `-4.387961` | wd1-replace |
| Peñas de Cabrera | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Peñas de Cabrera | period_start | `-4000` | `NULL` | wd1-clear |
| Peñas de Cabrera | site_type | `Cave Structures` | `Rock art` | wd1-replace |
| Philippopolis, Thrace | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Philippopolis, Thrace | period_start | `1` | `-342` | wd1-replace |
| Philippopolis, Thrace | source_url | `https://en.wikipedia.org/wiki/Philippopolis_(Thrace)` | `https://bg.wikipedia.org/wiki/%D0%A4%D0%B8%D0%BB%D0%B8%D0%BF` | wd1-replace |
| Phylaki | site_type | `Cemetery` | `Tomb` | wd1-replace |
| Pirwayuq | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pirwayuq | period_start | `1` | `NULL` | wd1-clear |
| Pirwayuq | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Pyramid of Neferhetepes | source_url | `https://en.wikipedia.org/wiki/Pyramid_of_Userkaf` | `https://de.wikipedia.org/wiki/Neferhetepes-Pyramide` | wd1-replace |
| Qhapaq Kancha | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Qhapaq Kancha | period_start | `1000` | `NULL` | wd1-clear |
| Qhapaq Kancha | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Rocks of Saskatchewan | source_url | `http://ryanwunsch.com/mystery-rocks-saskatchewan/` | `https://bluejayjournal.ca/index.php/bluejay/article/view/538` | wd1-replace |
| Roman Bath, York | site_type | `Residence/villa/farmhouse` | `Bath` | wd1-replace |
| Roman City Ruins of Salona | site_type | `Megalithic stones` | `City` | wd1-replace |
| Roman Nymphaeum Amman | site_type | `Infrastructure` | `Monument` | wd1-replace |
| Rudna Glava | geom | `0101000020E61000004B91D7FBA911364024E15D226A2B4640` | `SRID=4326;POINT(22.087591 44.339494)` | wd1-point |
| Rudna Glava | lat | `44.33917646011312` | `44.339494` | wd1-replace |
| Rudna Glava | lon | `22.068999996308133` | `22.087591` | wd1-replace |
| Saliagos | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Santuário Arqueológico de Ollantaytambo | source_url | `https://www.machupicchuterra.com/br/cusco/ollantaytambo/siti` | `https://www.machupicchuterra.com/br/cusco/urubamba/sitio-arq` | wd1-replace |
| Santuário Rupestre de Panóias | site_type | `Cave Structures` | `Sanctuary` | wd1-replace |
| Sitio Arqueológico Yarumela El Chircal | geom | `0101000020E61000001B4DB858EBE855C0B053D5698CDB2C40` | `SRID=4326;POINT(-87.6476 14.3636)` | wd1-point |
| Sitio Arqueológico Yarumela El Chircal | lat | `14.428805644312746` | `14.3636` | wd1-replace |
| Sitio Arqueológico Yarumela El Chircal | lon | `-87.63936441419757` | `-87.6476` | wd1-replace |
| Solokha Kurgan | geom | `0101000020E6100000F56729B5751741403D1876DA59B54740` | `SRID=4326;POINT(34.339 47.326)` | wd1-point |
| Solokha Kurgan | lat | `47.41680460707037` | `47.326` | wd1-replace |
| Solokha Kurgan | lon | `34.18327965280324` | `34.339` | wd1-replace |
| Stoa of Eumenes | site_type | `Ruin` | `Monument` | wd1-replace |
| Stoa of Zeus | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Stone Spheres of Costa Rica | geom | `0101000020E6100000A7B104B4000055C012AB57771E002440` | `SRID=4326;POINT(-83.4775 8.91139)` | wd1-point |
| Stone Spheres of Costa Rica | lat | `10.000232438518228` | `8.91139` | wd1-replace |
| Stone Spheres of Costa Rica | lon | `-84.00004291971582` | `-83.4775` | wd1-replace |
| Stone Spheres of Costa Rica | site_type | `Rock relief/carving` | `Sculptured stone` | wd1-replace |
| Syberg | period_name | `4500 - 3000 BC` | `500 - 1000 AD` | wd1-derive-period-name |
| Syberg | period_start | `-4500` | `700` | wd1-replace |
| Syberg | site_type | `City/town/settlement` | `Castle` | wd1-replace |
| Syberg | source_url | `https://en.wikipedia.org/wiki/Syberg` | `https://en.wikipedia.org/wiki/Sigiburg` | wd1-replace |
| Tašmajdan Park | site_type | `City/town/settlement` | `Quarry` | wd1-replace |
| Tempio di Zeus, Selinunte | site_type | `Temple complex` | `Temple` | wd1-replace |
| Tempio di Zeus, Selinunte | source_url | `https://en.wikipedia.org/wiki/Selinunte` | `https://it.wikipedia.org/wiki/Tempio_G_di_Selinunte` | wd1-replace |
| Temple of Poseidon, Tainaron | geom | `0101000020E61000007AD95E07987B3640CB7A927D4C314240` | `SRID=4326;POINT(22.4867 36.4018)` | wd1-point |
| Temple of Poseidon, Tainaron | lat | `36.3851468053086` | `36.4018` | wd1-replace |
| Temple of Poseidon, Tainaron | lon | `22.482788525253888` | `22.4867` | wd1-replace |
| Temple of Poseidon, Tainaron | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Temple of Poseidon, Tainaron | period_start | `-1500` | `NULL` | wd1-clear |
| The Acropolis of Ancient Thasos | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| The Acropolis of Ancient Thasos | period_start | `-500` | `-600` | wd1-replace |
| The Black Pyramid- Pyramid of Amenemhat III (Dahshur) | source_url | `https://en.wikipedia.org/wiki/Pyramid_of_Amenemhat_III_(Dahs` | `https://en.wikipedia.org/wiki/Black_Pyramid` | wd1-replace |
| The Roman Bridge (Elguentra) | site_type | `Megalithic structures` | `Bridge` | wd1-replace |
| The Roman Bridge (Elguentra) | source_url | `https://en.wikipedia.org/wiki/El_Kantara` | `https://ar.wikipedia.org/wiki/%D8%AC%D8%B3%D8%B1_%D8%A7%D9%8` | wd1-replace |
| Tours Amphitheatre | site_type | `Megalithic structures` | `Amphitheatre` | wd1-replace |
| Trajan's Forum | geom | `0101000020E61000002F5BD313719D2140035882C284FF4340` | `SRID=4326;POINT(12.48587 41.89542)` | wd1-point |
| Trajan's Forum | lat | `39.99623900761073` | `41.89542` | wd1-replace |
| Trajan's Forum | lon | `8.807503337431255` | `12.48587` | wd1-replace |
| Wanakawri, Cusco | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Wanakawri, Cusco | period_start | `1000` | `NULL` | wd1-clear |
| Wanakawri, Cusco | site_type | `Monument` | `Sacred site` | wd1-replace |
| Waraqayuq | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Waraqayuq | period_start | `1` | `NULL` | wd1-clear |
| Waraqayuq | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Wat'a, Huánuco | geom | `0101000020E610000013685E6EB93253C08E37F8C4F5BB22C0` | `SRID=4326;POINT(-76.809532 -9.357669)` | wd1-point |
| Wat'a, Huánuco | lat | `-9.367109446811607` | `-9.357669` | wd1-replace |
| Wat'a, Huánuco | lon | `-76.7925678178729` | `-76.809532` | wd1-replace |
| Wat'a, Huánuco | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wat'a, Huánuco | period_start | `1` | `NULL` | wd1-clear |
| Worlebury Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Worlebury Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Worlebury Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Worlebury Hill | source_url | `https://en.wikipedia.org/wiki/Worlebury_Hill` | `https://en.wikipedia.org/wiki/Worlebury_Camp` | wd1-replace |
| Şuayb Antik Şehri | site_type | `Megalithic stones` | `Settlement` | wd1-replace |
| Şuayb Antik Şehri | source_url | `https://www-sanliurfa-bel-tr.translate.goog/icerik/236/625/s` | `https://www.urfakulturatlasi.com.tr/envanter/detay/suayip-an` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Jach'a Phasa | lat | `coordinates-unresolved` | Only English Wikipedia prints a point for the site (17°23′47″S 68°48′13″W, 0.09 km from the stored point), and its own f |
| Peppercombe Castle | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://thegreatbritainguide.com/place/peppercombe-castle/; quote not fo |
| Anku | lat | `coordinates-unresolved` | The stored point sits at Tantamayo town, the reference point of the whole Tantamayo complex; enwiki (-9.350, -76.583, co |
| The Roman Bridge (Elguentra) | lat | `coordinates-unresolved` | The Arabic Wikipedia article on the bridge (and its Wikidata item) gives 35°14′01″N 5°42′06″E, which matches the OpenStr |
| Delphinion | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://vici.org/vici/18190/; quote not found: https://vici.org/vici/181 |
| Miyu Pampa | lat | `coordinates-unresolved` | The sources place Miu Pampa about 500 m from Jircán, the capital of Jircán district, at 3,434 m; the stored point (taken |
| Furby | lat | `coordinates-unresolved` | Furby's remaining site is its church ruin (RAÄ Västerås 502:1); only the Wikimedia family (Wikidata Q29886222, 59°38'22. |
| Roman Bath, York | period_start | `held-unreadable` | no counted answer in 3 rounds: quote fetch failed: https://www.britainexpress.com/cities/york/Roman_Bathhouse.htm (statu |
| Hatun Misapata | lat | `coordinates-unresolved` | Wikipedia places Hatun Misapata in Aucara District (per the 2011 heritage resolution), but its only printed point (es.wi |
| Qhapaq Kancha | lat | `coordinates-unresolved` | The stored point lies in the village of Coya, not on the summit site: the MINCETUR inventory gives the ruins as UTM 19 L |
| Waraqayuq | lat | `coordinates-unresolved` | The stored point is the summit of Waraqayuq mountain. English Wikipedia, citing the INC 2001 inventory, puts the archaeo |
| Crantit Chambered Cairn | lat | `coordinates-unresolved` | Only the Wikimedia family (Wikidata Q1138920 and the German article Crantit Cairn, 58.972577, -2.975777, matching Canmor |
| Pirwayuq | lat | `coordinates-unresolved` | The stored point is the centroid of Laria District (OpenStreetMap boundary), not the site, and Wikidata's P625 points at |
| Murujuga | lat | `coordinates-unresolved` | Murujuga is a cultural landscape covering the whole Burrup Peninsula and Dampier Archipelago; the sources give scattered |
| Achladia | lat | `country-changes` | the new point lies in ['Greece'], the site says Germany |
| Rocks of Saskatchewan | lat | `coordinates-unresolved` | The Mystery Rocks (the Rock Pile) lie on private land south of Fort Walsh in the Cypress Hills; the 1998 Saskatchewan In |
| Gyrton, Thessaly | lat | `coordinates-unresolved` | The site of Gyrton is disputed. The stored point is the Barrington Atlas/DARE location at Mourlari near Evangelismos (DA |
| Pyramid of Neferhetepes | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family gives a point for this queen's pyramid (Wikidata 29.87275, 31.2186; de.wikipedia 29°  |
| Megarian Treasury, Delphi | lat | `coordinates-unresolved` | The only point found for the Megarian Treasury is OpenStreetMap's outline 'Θησαυρός Μεγαρέων' (way 145690063, centre 38. |
| Bryn Eryr | lat | `coordinates-unresolved` | Cadw's scheduling record AN100 and the Heneb HER (PRN 401) place the Bryn Eryr enclosure at OS grid SH 5406 7566 (E 2540 |
| Mersinaki | lat | `coordinates-unresolved` | The only point found for the Mersinaki sanctuary is 35.156834, 32.788315 on the PHRC inscription database page, repeated |
| Inkachaka | lat | `coordinates-unresolved` | Only the Wikipedia family (enwiki 17°14′18″S 65°48′44″W, eswiki and Wikidata about 17°14′15″S 65°49′01″W, both within 0. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s005-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s005 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
