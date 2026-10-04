# WD3 fields-wd3-2026-10-02b-s003: plan

Built 2026-10-04T12:44:28+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s003`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s003:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 206 |
| sites_written | 100 |
| refused | 28 |
| cells:geom | 8 |
| cells:lat | 8 |
| cells:lon | 8 |
| cells:period_name | 74 |
| cells:period_start | 74 |
| cells:site_type | 33 |
| cells:source_url | 1 |
| refused:coordinates-unresolved | 11 |
| refused:field-unresolved | 17 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Aartswoud | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Aartswoud | period_start | `NULL` | `-2500` | wd3-replace |
| Acatitlan | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Acatitlan | period_start | `NULL` | `1101` | wd3-replace |
| Agios Vasileios, Laconia | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Agios Vasileios, Laconia | period_start | `NULL` | `-3200` | wd3-replace |
| Archaeological Site of Xcalumkín | geom | `0101000020E61000000DC65522E26F56C07D0C17C544013440` | `SRID=4326;POINT(-90.010194 20.172139)` | wd3-point |
| Archaeological Site of Xcalumkín | lat | `20.004955595137734` | `20.172139` | wd3-replace |
| Archaeological Site of Xcalumkín | lon | `-89.74817713142711` | `-90.010194` | wd3-replace |
| Archaeological Site of Xcalumkín | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Archaeological Site of Xcalumkín | period_start | `NULL` | `-300` | wd3-replace |
| Archaeological Site of Xcalumkín | site_type | `NULL` | `City` | wd3-replace |
| Ariconium | site_type | `NULL` | `Town` | wd3-replace |
| Asana, Peru | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Asana, Peru | period_start | `NULL` | `-9000` | wd3-replace |
| Asana, Peru | site_type | `NULL` | `Settlement` | wd3-replace |
| Atella | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Atella | period_start | `NULL` | `-500` | wd3-replace |
| Atella | site_type | `NULL` | `City` | wd3-replace |
| Auquilohuagra | geom | `0101000020E610000002ECB8C8762A53C05102A205A28A23C0` | `SRID=4326;POINT(-76.648972 -9.772694)` | wd3-point |
| Auquilohuagra | lat | `-9.77076737978601` | `-9.772694` | wd3-replace |
| Auquilohuagra | lon | `-76.66350000437527` | `-76.648972` | wd3-replace |
| Auquilohuagra | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Awkimarka, Huánuco | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Ayşepınar | site_type | `NULL` | `Tomb` | wd3-replace |
| Bejsebakke | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Bejsebakke | period_start | `NULL` | `-2400` | wd3-replace |
| Bewcastle Roman Fort | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Bewcastle Roman Fort | period_start | `NULL` | `124` | wd3-replace |
| Brantingham Roman Villa | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Brantingham Roman Villa | period_start | `NULL` | `101` | wd3-replace |
| Bredon Hill | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Bredon Hill | period_start | `NULL` | `-300` | wd3-replace |
| Bucknowle Farm | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Bucknowle Farm | period_start | `NULL` | `1` | wd3-replace |
| Buddhist Caves of Khapra Kodiya | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Buddhist Caves of Khapra Kodiya | period_start | `NULL` | `-300` | wd3-replace |
| Bussock Camp | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Bussock Camp | period_start | `NULL` | `-600` | wd3-replace |
| Capela de São Dinis | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Capela de São Dinis | period_start | `NULL` | `-4000` | wd3-replace |
| Caska, Croatia | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Caska, Croatia | period_start | `NULL` | `-100` | wd3-replace |
| Cefn Carnedd | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Cefn Carnedd | period_start | `NULL` | `-800` | wd3-replace |
| Chutixtiox | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Chutixtiox | period_start | `NULL` | `1200` | wd3-replace |
| City of David | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| City of David | period_start | `NULL` | `-4000` | wd3-replace |
| Cochabamba Archaeological Site | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Cochabamba Archaeological Site | period_start | `NULL` | `1350` | wd3-replace |
| Cochabamba Archaeological Site | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Comalcalco | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Comalcalco | period_start | `NULL` | `-800` | wd3-replace |
| Creech Hill | geom | `0101000020E6100000164512A3CEC603C01349F80D288F4940` | `SRID=4326;POINT(-2.47845 51.1282)` | wd3-point |
| Creech Hill | lat | `51.118409868462685` | `51.1282` | wd3-replace |
| Creech Hill | lon | `-2.47207381629472` | `-2.47845` | wd3-replace |
| Debdieba | geom | `0101000020E61000007A9EA66E6EFA2C40C492FDA411EE4140` | `SRID=4326;POINT(14.465556 35.854167)` | wd3-point |
| Debdieba | lat | `35.85991346723088` | `35.854167` | wd3-replace |
| Debdieba | lon | `14.48912378105091` | `14.465556` | wd3-replace |
| Devil's Causeway | geom | `0101000020E61000002174B8C5B42200C0E778F53CD17C4B40` | `SRID=4326;POINT(-1.809 55.308)` | wd3-point |
| Devil's Causeway | lat | `54.97513544069243` | `55.308` | wd3-replace |
| Devil's Causeway | lon | `-2.016946358386591` | `-1.809` | wd3-replace |
| Dion, Pieria | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Dion, Pieria | period_start | `NULL` | `-600` | wd3-replace |
| Dolbury | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Dolbury | period_start | `NULL` | `-600` | wd3-replace |
| Domica Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Domica Cave | period_start | `NULL` | `-35000` | wd3-replace |
| Dun Ringill | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Dun Ringill | period_start | `NULL` | `-1000` | wd3-replace |
| Edin's Hall Broch | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Edin's Hall Broch | period_start | `NULL` | `101` | wd3-replace |
| El Tigre (Campeche) | site_type | `NULL` | `City` | wd3-replace |
| Ermita de la Virgen del Pilar Dam | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Ermita de la Virgen del Pilar Dam | period_start | `NULL` | `1` | wd3-replace |
| Featherwood Roman Camps | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Featherwood Roman Camps | period_start | `NULL` | `1` | wd3-replace |
| Glanum | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Glanum | period_start | `NULL` | `-600` | wd3-replace |
| Goward Dolmen | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Goward Dolmen | period_start | `NULL` | `-2500` | wd3-replace |
| Hadrian's Wall Path | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Hadrian's Wall Path | period_start | `NULL` | `2003` | wd3-replace |
| Hascombe Hill | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Hascombe Hill | period_start | `NULL` | `-100` | wd3-replace |
| Heaning Wood Bone Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Heaning Wood Bone Cave | period_start | `NULL` | `-9290` | wd3-replace |
| Hisarya, Bulgaria | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Hisarya, Bulgaria | period_start | `NULL` | `-6000` | wd3-replace |
| Hob Hurst's House | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Hob Hurst's House | period_start | `NULL` | `-1000` | wd3-replace |
| Horom Citadel | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Horom Citadel | period_start | `NULL` | `-4000` | wd3-replace |
| Huaca Esmeralda | site_type | `NULL` | `Temple` | wd3-replace |
| Huilai Monument Archaeology Park | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Huntersquoy Chambered Cairn | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Huntersquoy Chambered Cairn | period_start | `NULL` | `-3000` | wd3-replace |
| Iulia Constantia Zilil | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Iulia Constantia Zilil | period_start | `NULL` | `-400` | wd3-replace |
| Ixtonton | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Ixtonton | period_start | `NULL` | `-400` | wd3-replace |
| Kanheri Caves | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Kanheri Caves | period_start | `NULL` | `-100` | wd3-replace |
| Knocknakilla | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Knocknakilla | period_start | `NULL` | `-1600` | wd3-replace |
| La Centinela | site_type | `NULL` | `Pyramid complex` | wd3-replace |
| La Joyanca | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| La Joyanca | period_start | `NULL` | `-200` | wd3-replace |
| La strada Romana delle Gallie ed il suo arco | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| La strada Romana delle Gallie ed il suo arco | period_start | `NULL` | `-31` | wd3-replace |
| La strada Romana delle Gallie ed il suo arco | site_type | `NULL` | `Road` | wd3-replace |
| Las Flores | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Las Flores | period_start | `NULL` | `1000` | wd3-replace |
| Las Flores | site_type | `NULL` | `City` | wd3-replace |
| Lentas | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Lentas | period_start | `NULL` | `-3000` | wd3-replace |
| Licata | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Licata | period_start | `NULL` | `-700` | wd3-replace |
| Likya Anıt Mezar | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Likya Anıt Mezar | period_start | `NULL` | `-400` | wd3-replace |
| Likya Anıt Mezar | site_type | `NULL` | `Tomb` | wd3-replace |
| Likya Anıt Mezar | source_url | `NULL` | `https://www.kulturportali.gov.tr/turkiye/mugla/gezilecekyer/` | wd3-replace |
| Llaqta Qulluy, Conayca | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Los Bañales | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Los Bañales | period_start | `NULL` | `-400` | wd3-replace |
| Maray Qalla | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Maray Qalla | period_start | `NULL` | `1450` | wd3-replace |
| Mayapan | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Mayapan | period_start | `NULL` | `1020` | wd3-replace |
| Megaliths in Mecklenburg-Vorpommern | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Megaliths in Mecklenburg-Vorpommern | period_start | `NULL` | `-3500` | wd3-replace |
| Molloko | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Molloko | period_start | `NULL` | `1300` | wd3-replace |
| Montana | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Montana | period_start | `NULL` | `400` | wd3-replace |
| Munigua | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Munigua | period_start | `NULL` | `-700` | wd3-replace |
| Mynydd Maendy | geom | `0101000020E6100000265388BC89C20BC066674E79F9C84940` | `SRID=4326;POINT(-3.5086 51.6486)` | wd3-point |
| Mynydd Maendy | lat | `51.57011333778682` | `51.6486` | wd3-replace |
| Mynydd Maendy | lon | `-3.4699892739394214` | `-3.5086` | wd3-replace |
| Naupa Iglesia (Choquequilla) | site_type | `NULL` | `Cave` | wd3-replace |
| Nausharo | site_type | `NULL` | `City` | wd3-replace |
| Nemogram Stupa | site_type | `NULL` | `Monastery` | wd3-replace |
| Pomeroy Wood | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Pomeroy Wood | period_start | `NULL` | `60` | wd3-replace |
| Pomeroy Wood | site_type | `NULL` | `Fort` | wd3-replace |
| Prehistoric Rock-Art Site of Pala Pinta | geom | `0101000020E6100000E2E09F7674E61DC02BAF085D5CA34440` | `SRID=4326;POINT(-7.394484 41.308844)` | wd3-point |
| Prehistoric Rock-Art Site of Pala Pinta | lat | `41.27625620769535` | `41.308844` | wd3-replace |
| Prehistoric Rock-Art Site of Pala Pinta | lon | `-7.475053647525984` | `-7.394484` | wd3-replace |
| Purepecha Digs | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Purepecha Digs | period_start | `NULL` | `-2570` | wd3-replace |
| Purepecha Digs | site_type | `NULL` | `Settlement` | wd3-replace |
| Purépecha Proto Urban Site | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Purépecha Proto Urban Site | period_start | `NULL` | `1000` | wd3-replace |
| Purépecha Proto Urban Site | site_type | `NULL` | `Settlement` | wd3-replace |
| Pyramid G1-d | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Pyramid G1-d | period_start | `NULL` | `-2600` | wd3-replace |
| Pyramid of Hetepheres I | geom | `0101000020E6100000EB76978B9A353F404AD1DE44EBC93D40` | `SRID=4326;POINT(31.136261 29.978836)` | wd3-point |
| Pyramid of Hetepheres I | lat | `29.788746170424282` | `29.978836` | wd3-replace |
| Pyramid of Hetepheres I | lon | `31.20938942382683` | `31.136261` | wd3-replace |
| Rastrojón | site_type | `NULL` | `Residence/villa/farmhouse` | wd3-replace |
| Roman City of Deultum - Develtos | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Roman City of Deultum - Develtos | period_start | `NULL` | `-700` | wd3-replace |
| Rouffignac Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Rouffignac Cave | period_start | `NULL` | `-11000` | wd3-replace |
| Roulston Scar, Sutton Bank | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Roulston Scar, Sutton Bank | period_start | `NULL` | `-900` | wd3-replace |
| San Jose de Moro | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| San Jose de Moro | period_start | `NULL` | `400` | wd3-replace |
| Scupi | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Scupi | period_start | `NULL` | `-1200` | wd3-replace |
| Smythe's Megalith | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Smythe's Megalith | period_start | `NULL` | `-4000` | wd3-replace |
| Stari Slankamen | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Stari Slankamen | period_start | `NULL` | `-300` | wd3-replace |
| Stenseby Passage Grave | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Stenseby Passage Grave | period_start | `NULL` | `-3500` | wd3-replace |
| Stokeleigh Camp | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Stokeleigh Camp | period_start | `NULL` | `-300` | wd3-replace |
| Tampu Mach'ay, Huancavelica | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Tanqa Tanqa | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Tanqa Tanqa | period_start | `NULL` | `1200` | wd3-replace |
| Tanqa Tanqa | site_type | `NULL` | `Settlement` | wd3-replace |
| Tarawasi | site_type | `NULL` | `Palace` | wd3-replace |
| Tarmatambo | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Tempio di Zeus Olympios | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Tempio di Zeus Olympios | period_start | `NULL` | `-480` | wd3-replace |
| Temple of Isis, Pompeii | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Temple of Isis, Pompeii | period_start | `NULL` | `-200` | wd3-replace |
| Teotihuacan - Palace Atelelco | site_type | `NULL` | `Palace` | wd3-replace |
| Teteles de Santo Nombre | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Teteles de Santo Nombre | period_start | `NULL` | `-400` | wd3-replace |
| Teteles de Santo Nombre | site_type | `NULL` | `Settlement` | wd3-replace |
| Wamanmarka, Chumbivilcas | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Waraqu Urqu | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Whitsbury Castle | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Whitsbury Castle | period_start | `NULL` | `-600` | wd3-replace |
| Xnaheb | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Xnaheb | period_start | `NULL` | `700` | wd3-replace |
| Xnaheb | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Xələc, Nakhchivan | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Xələc, Nakhchivan | period_start | `NULL` | `-4000` | wd3-replace |
| Yuraq Mach'ay | site_type | `NULL` | `Rock art` | wd3-replace |
| Žitorađa | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Žitorađa | period_start | `NULL` | `301` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Auquilohuagra | period_start | `field-unresolved` | No source found gives a year, century or millennium for the start of Auquilohuagra; Wikipedia calls it only an archaeolo |
| Huaca Esmeralda | period_start | `field-unresolved` | Wikipedia says only 'first stage of development' of the Chimu culture; the only readable-to-me dated claims (a Chimu-per |
| Pyramid of Hetepheres I | period_start | `field-unresolved` | The Wikipedia articles only say the pyramid was built in the Fourth Dynasty; no readable source dates this pyramid's con |
| Wamanmarka, Chumbivilcas | lat | `coordinates-unresolved` | No quotable source gives the site's own point in the required form. The English article has an empty coordinates field a |
| Wamanmarka, Chumbivilcas | period_start | `field-unresolved` | No source dates the start of Wamanmarka. The national heritage register record describes a pre-Inca citadel with influen |
| Naupa Iglesia (Choquequilla) | period_start | `field-unresolved` | The sources found give only period words (Inca Late Horizon, earlier Wari presence) or speculation, no year or century f |
| Huilai Monument Archaeology Park | period_start | `field-unresolved` | The English Wikipedia article on the Huilai site gives no date at all, and the Chinese article dates it only relatively: |
| Teotihuacan - Palace Atelelco | period_start | `field-unresolved` | Sources date only the murals (Xolalpan phase c. 450-650 AD on Wikipedia; roughly 350-650 CE on Yucatan Magazine) or Teot |
| Yuraq Mach'ay | period_start | `field-unresolved` | The English Wikipedia article describes Yuraq Mach'ay only as an archaeological site with rock paintings at 3,991 m on t |
| Tarmatambo | period_start | `field-unresolved` | No source dates the start of Tarmatambo; the English article gives only its National Cultural Heritage designation, and  |
| Purepecha Digs | lat | `coordinates-unresolved` | The only source, the Megalithic Portal entry, says its location is approximate and actually cites the peak of the Paricu |
| Megaliths in Mecklenburg-Vorpommern | lat | `coordinates-unresolved` | The entry covers the megaliths of a whole German state; no source gives a single point for it, and the English article p |
| Creech Hill | period_start | `field-unresolved` | The Somerset HER and Wikipedia give only 'Early Iron Age' or the generic hill-fort statement ('roughly the start of the  |
| La Joyanca | lat | `coordinates-unresolved` | English and Spanish Wikipedia and Wikidata print no point for La Joyanca, and none of the excavation or project pages (C |
| Tampu Mach'ay, Huancavelica | lat | `coordinates-unresolved` | No readable source gives a point for Tampu Mach'ay in Acostambo, Huancavelica; Wikipedia and Wikidata carry none, and th |
| Tampu Mach'ay, Huancavelica | period_start | `field-unresolved` | No source dates Tampu Mach'ay in Huancavelica. |
| Purépecha Proto Urban Site | lat | `coordinates-unresolved` | No source prints a point for this site: the discoverer withheld the precise location for fear of looting, and the Megali |
| Llaqta Qulluy, Conayca | lat | `coordinates-unresolved` | Wikipedia marks the coordinates as missing and Wikidata has no P625; no readable source found gives a point for Llaqta Q |
| Llaqta Qulluy, Conayca | period_start | `field-unresolved` | No readable source dates Llaqta Qulluy in Conayca; Wikipedia only gives the name's meaning. |
| Ariconium | period_start | `field-unresolved` | Wikipedia says only that the site existed before the Roman era and was abandoned perhaps shortly after 360; the Princeto |
| Teteles de Santo Nombre | lat | `coordinates-unresolved` | A SciELO article prints 18 37 40 N y 97 42 59 W for the site, but the connecting word makes the quote unreadable as a po |
| Ayşepınar | lat | `coordinates-unresolved` | The Cultural Inventory record for the Ayşepınar rock tombs, which is the only register page I could read, prints no coor |
| Ayşepınar | period_start | `field-unresolved` | The Cultural Inventory dates the Ayşepınar rock tombs only to the Hellenistic-Roman period, a period word, and mentions  |
| Devil's Causeway | period_start | `field-unresolved` | No readable page dates the construction of the Devil's Causeway to a year, century or millennium: English Wikipedia only |
| Waraqu Urqu | lat | `coordinates-unresolved` | The English Wikipedia article prints no coordinate for Waraqu Urqu itself; its only point, 13°07'13"S 73°49'57"W, is exp |
| Waraqu Urqu | period_start | `field-unresolved` | No source I could read dates the start of Waraqu Urqu: the article names only the Chanka culture as its period, a period |
| Montana | lat | `coordinates-unresolved` | The English and Spanish Wikipedia articles on Montana (Escuintla, Guatemala) print no coordinates and the Wikidata item  |
| Awkimarka, Huánuco | period_start | `field-unresolved` | No source found dates Awkimarka/Auquimarca in Tomay Kichwa District, Ambo Province, Huánuco; Wikipedia gives no date and |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s003-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s003 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
