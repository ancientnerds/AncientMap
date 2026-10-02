# WD1 fields-wd1-2026-09-26b-s001: plan

Built 2026-09-30T05:54:40+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s001`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s001:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 247 |
| sites_written | 100 |
| refused | 24 |
| cells:geom | 16 |
| cells:lat | 16 |
| cells:lon | 16 |
| cells:period_name | 56 |
| cells:period_start | 56 |
| cells:site_type | 49 |
| cells:source_url | 38 |
| refused:coordinates-unresolved | 24 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acropolis of Alatri | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Acropolis of Alatri | period_start | `-3000` | `-600` | wd1-replace |
| Acropolis of Alatri | source_url | `https://www3.astronomicalheritage.net/index.php/show-entity?` | `https://it.wikipedia.org/wiki/Acropoli_di_Alatri` | wd1-replace |
| Ad-Deir | source_url | `https://en.wikipedia.org/wiki/Ad_Deir` | `https://en.wikipedia.org/wiki/Ed-Deir,_Petra` | wd1-replace |
| Amfiteatar Salona | source_url | `https://en.wikipedia.org/wiki/Theatre` | `https://hr.wikipedia.org/wiki/Amfiteatar_u_Saloni` | wd1-replace |
| Ancient City of Argishtikhinili | source_url | `https://en.wikipedia.org/wiki/Argishtikhinili_(ancient_city)` | `https://en.wikipedia.org/wiki/Argi%C5%A1ti%E1%B8%ABinili` | wd1-replace |
| Ancient City of Troy | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Ancient City of Troy | period_start | `-500` | `-3000` | wd1-replace |
| Axus | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Axus | period_start | `-2000` | `NULL` | wd1-clear |
| Axus | source_url | `https://en.wikipedia.org/wiki/Axus` | `https://en.wikipedia.org/wiki/Axos` | wd1-replace |
| Ayawayq'u | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ayawayq'u | period_start | `1` | `NULL` | wd1-clear |
| Baalbek | site_type | `Megalithic structures` | `Temple complex` | wd1-replace |
| Baalbek | source_url | `https://en.wikipedia.org/wiki/Baalbek` | `https://de.wikipedia.org/wiki/Tempel_von_Baalbek` | wd1-replace |
| Balls Head Reserve | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Balls Head Reserve | period_start | `-4500` | `NULL` | wd1-clear |
| Belgrade Fortress | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Belgrade Fortress | period_start | `-500` | `1` | wd1-replace |
| Bhaja Caves | site_type | `Temple complex` | `Cave Structures` | wd1-replace |
| Boa Island | geom | `0101000020E6100000D84045B34F551FC08A41436B26424B40` | `SRID=4326;POINT(-7.869349 54.506088)` | wd1-point |
| Boa Island | lat | `54.51679745468125` | `54.506088` | wd1-replace |
| Boa Island | lon | `-7.83331184492291` | `-7.869349` | wd1-replace |
| Boa Island | period_name | `1500 - 500 BC` | `1 - 500 AD` | wd1-derive-period-name |
| Boa Island | period_start | `-1000` | `1` | wd1-replace |
| Boa Island | site_type | `Rock relief/carving` | `Sculptured stone` | wd1-replace |
| Boa Island | source_url | `https://en.wikipedia.org/wiki/Boa_Island` | `https://en.wikipedia.org/wiki/Boa_Island_figures` | wd1-replace |
| Bokerley Dyke | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Bokerley Dyke | period_start | `1` | `NULL` | wd1-clear |
| Bonstorf Barrows | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Bonstorf Barrows | period_start | `-3000` | `-1500` | wd1-replace |
| Broch of Gurness | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Burnt Fen | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Burnt Fen | period_start | `-8000` | `NULL` | wd1-clear |
| Burnt Fen | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Busskirch | geom | `0101000020E61000005C5272E1AEAA2140FFE71FAFE19D4740` | `SRID=4326;POINT(8.833528 47.217011)` | wd1-point |
| Busskirch | lat | `47.233449831561295` | `47.217011` | wd1-replace |
| Busskirch | lon | `8.833365483479774` | `8.833528` | wd1-replace |
| Butrint | site_type | `Temple complex` | `City` | wd1-replace |
| Bølareinen | geom | `0101000020E6100000FEF022920856274089689F3C8E045040` | `SRID=4326;POINT(11.9382 64.1459)` | wd1-point |
| Bølareinen | lat | `64.07118144576283` | `64.1459` | wd1-replace |
| Bølareinen | lon | `11.66803414036303` | `11.9382` | wd1-replace |
| Bølareinen | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Bølareinen | period_start | `-3000` | `-4000` | wd1-replace |
| Carnedd y Ddelw Cairn | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Carnedd y Ddelw Cairn | period_start | `-5000` | `NULL` | wd1-clear |
| Carnedd y Ddelw Cairn | source_url | `https://en.wikipedia.org/wiki/Carnedd_y_Ddelw` | `https://coflein.gov.uk/en/sites/303005` | wd1-replace |
| Carranque | geom | `0101000020E6100000C797F78FBE2C0FC0B302756EE2154440` | `SRID=4326;POINT(-3.955556 40.188889)` | wd1-point |
| Carranque | lat | `40.17097264016538` | `40.188889` | wd1-replace |
| Carranque | lon | `-3.896847843879161` | `-3.955556` | wd1-replace |
| Carranque | site_type | `Residence/villa/farmhouse` | `Villa` | wd1-replace |
| Carranque | source_url | `https://en.wikipedia.org/wiki/Carranque` | `https://es.wikipedia.org/wiki/Villa_romana_de_Carranque` | wd1-replace |
| Cave of Ardales | geom | `0101000020E6100000C6FA796BF66013C026CD83CD5F704240` | `SRID=4326;POINT(-4.828834 36.872802)` | wd1-point |
| Cave of Ardales | lat | `36.877923669201024` | `36.872802` | wd1-replace |
| Cave of Ardales | lon | `-4.844690017051738` | `-4.828834` | wd1-replace |
| Cave of Ardales | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Cave of Ardales | period_start | `1` | `NULL` | wd1-clear |
| Cave of Ardales | source_url | `https://en.wikipedia.org/wiki/Ardales` | `https://es.wikipedia.org/wiki/Cueva_de_Ardales` | wd1-replace |
| Cissbury Ring | site_type | `Mine/quarry` | `Fort` | wd1-replace |
| Cochapata | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Cochapata | period_start | `1400` | `NULL` | wd1-clear |
| Cochapata | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Condolden | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Condolden | period_start | `-4500` | `NULL` | wd1-clear |
| Condolden | source_url | `https://en.wikipedia.org/wiki/Condolden` | `https://www.megalithic.co.uk/article.php?sid=22301` | wd1-replace |
| Court Hill, Sussex | site_type | `Archaeological site` | `Earthwork` | wd1-replace |
| Deir el kalaa | source_url | `https://en.wikipedia.org/wiki/Beit_Mery` | `https://fr.wikipedia.org/wiki/Deir_el-Qalaa` | wd1-replace |
| Domus De Janas Torre Argentina | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Domus De Janas Torre Argentina | period_start | `-4500` | `NULL` | wd1-clear |
| Domus De Janas Torre Argentina | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Dubris | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Dubris | period_start | `-500` | `43` | wd1-replace |
| Eightercua Stone Row | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| El Tintal | geom | `0101000020E6100000A13902D2497B56C07AFE81A62BA83140` | `SRID=4326;POINT(-89.99583 17.57444)` | wd1-point |
| El Tintal | lat | `17.65691605256732` | `17.57444` | wd1-replace |
| El Tintal | lon | `-89.92638063638016` | `-89.99583` | wd1-replace |
| El Tintal | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| El Tintal | period_start | `-500` | `-600` | wd1-replace |
| Elaiussa Sebaste | site_type | `Temple complex` | `City` | wd1-replace |
| Engomi Ancient City Ruins | source_url | `https://en.wikipedia.org/wiki/Enkomi` | `https://en.wikipedia.org/wiki/Enkomi_(archaeological_site)` | wd1-replace |
| Gaer, Black Mountains | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Gaer, Black Mountains | period_start | `-1500` | `NULL` | wd1-clear |
| Gaer, Black Mountains | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Gaer, Black Mountains | source_url | `https://en.wikipedia.org/wiki/Gaer_(Black_Mountains)` | `https://coflein.gov.uk/en/sites/300043` | wd1-replace |
| Gene fornby | site_type | `Museum` | `Settlement` | wd1-replace |
| Glubochek | source_url | `https://en.wikipedia.org/wiki/Glubochek` | `NULL` | wd1-clear |
| Glösa | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Glösa | period_start | `-4500` | `NULL` | wd1-clear |
| Glösa | source_url | `https://en.wikipedia.org/wiki/Gl%C3%B6sa` | `https://www.megalithic.co.uk/article.php?sid=63073` | wd1-replace |
| Gonnus | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Gonnus | period_start | `-1000` | `NULL` | wd1-clear |
| Grotta di Santa Croce | geom | `0101000020E6100000A649A1D45781304071DBC88F219F4440` | `SRID=4326;POINT(16.469139 41.177056)` | wd1-point |
| Grotta di Santa Croce | lat | `41.24321172053795` | `41.177056` | wd1-replace |
| Grotta di Santa Croce | lon | `16.505246438385846` | `16.469139` | wd1-replace |
| Grotta di Santa Croce | period_name | `1 - 500 AD` | `< 4500 BC` | wd1-derive-period-name |
| Grotta di Santa Croce | period_start | `1` | `-150000` | wd1-replace |
| Halikan | geom | `0101000020E61000008C9306CA496130401B34C3AADA434740` | `SRID=4326;POINT(16.362 46.525)` | wd1-point |
| Halikan | lat | `46.530110688509204` | `46.525` | wd1-replace |
| Halikan | lon | `16.380032183270984` | `16.362` | wd1-replace |
| Hattusas | geom | `0101000020E610000058768F64DE4E41405198BC911C044440` | `SRID=4326;POINT(34.615278 40.019722)` | wd1-point |
| Hattusas | lat | `40.03212186535587` | `40.019722` | wd1-replace |
| Hattusas | lon | `34.616161890077535` | `34.615278` | wd1-replace |
| Hattusas | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Hattusas | period_start | `-3000` | `-6000` | wd1-replace |
| Hattusas | site_type | `City/town/settlement` | `City` | wd1-replace |
| Heroon of Trysa | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Idaean Cave | source_url | `https://en.wikipedia.org/wiki/Psychro_Cave` | `https://de.wikipedia.org/wiki/Id%C3%A4ische_Grotte` | wd1-replace |
| Inka Tampu, Vilcabamba | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inka Tampu, Vilcabamba | period_start | `1000` | `NULL` | wd1-clear |
| Intikancha, Puno | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Intikancha, Puno | period_start | `1` | `NULL` | wd1-clear |
| Intikancha, Puno | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Intikancha, Puno | source_url | `https://en.wikipedia.org/wiki/Intikancha_(Puno)` | `NULL` | wd1-clear |
| Jenny's Lantern | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Jenny's Lantern | source_url | `https://en.wikipedia.org/wiki/Jenny%27s_Lantern` | `https://keystothepast.info/search-records/results-of-search/` | wd1-replace |
| Juhor | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Juhor | period_start | `-500` | `NULL` | wd1-clear |
| Juhor | site_type | `Archaeological site` | `Fort` | wd1-replace |
| Juhor | source_url | `https://en.wikipedia.org/wiki/Juhor` | `NULL` | wd1-clear |
| Kadyanda | geom | `0101000020E610000018CA57F3E31D3D40A88B29D6D94F4240` | `SRID=4326;POINT(29.235998 36.717015)` | wd1-point |
| Kadyanda | lat | `36.623835344587235` | `36.717015` | wd1-replace |
| Kadyanda | lon | `29.116759499485937` | `29.235998` | wd1-replace |
| Kadyanda | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Kadyanda | period_start | `-1500` | `-500` | wd1-replace |
| Kadyanda | site_type | `Temple complex` | `City` | wd1-replace |
| Karnak Temple Complex | geom | `0101000020E6100000696BE41A06534040E0ACB84F81B63940` | `SRID=4326;POINT(32.6583 25.7183)` | wd1-point |
| Karnak Temple Complex | lat | `25.712910635554067` | `25.7183` | wd1-replace |
| Karnak Temple Complex | lon | `32.64862381127643` | `32.6583` | wd1-replace |
| Khotiv Hillfort | site_type | `Fortress/citadel` | `Fortification` | wd1-replace |
| King Lud's Entrenchments and The Drift | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| King Lud's Entrenchments and The Drift | period_start | `-4500` | `NULL` | wd1-clear |
| Kulubá | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Kulubá | period_start | `500` | `NULL` | wd1-clear |
| Lezhë District | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Lezhë District | period_start | `-500` | `-800` | wd1-replace |
| Lezhë District | site_type | `Megalithic stones` | `City` | wd1-replace |
| Lezhë District | source_url | `https://en.wikipedia.org/wiki/Lezh%C3%AB` | `NULL` | wd1-clear |
| Llanos de Moxos (archaeology) | site_type | `City/town/settlement` | `Earthwork` | wd1-replace |
| Louloudies | site_type | `Residence/villa/farmhouse` | `Fortification` | wd1-replace |
| M'Daourouch | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| M'Daourouch | period_start | `1` | `-300` | wd1-replace |
| M'Daourouch | site_type | `Megalithic stones` | `City` | wd1-replace |
| M'Daourouch | source_url | `https://en.wikipedia.org/wiki/M%27Daourouch` | `https://en.wikipedia.org/wiki/Madauros` | wd1-replace |
| Megalitikum Rindu Hati | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Megalitikum Rindu Hati | period_start | `-1500` | `NULL` | wd1-clear |
| Megalitikum Rindu Hati | site_type | `Megalithic statues` | `Sculptured stone` | wd1-replace |
| Megalitikum Rindu Hati | source_url | `https://kebudayaan-kemdikbud-go-id.translate.goog/bpcbjambi/` | `https://www.megalithic.co.uk/article.php?sid=63737` | wd1-replace |
| Menelaion | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Menelaion | period_start | `-3000` | `-1450` | wd1-replace |
| Menelaion | site_type | `City/town/settlement` | `Sanctuary` | wd1-replace |
| Merrivale, Devon | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Merrivale, Devon | period_start | `-4000` | `-2500` | wd1-replace |
| Merrivale, Devon | source_url | `https://en.wikipedia.org/wiki/Merrivale,_Devon` | `https://de.wikipedia.org/wiki/Merrivale` | wd1-replace |
| Mitla, Entrance to Tomb 1 | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Mitla, Entrance to Tomb 1 | period_start | `-1500` | `NULL` | wd1-clear |
| Mitla, Entrance to Tomb 1 | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Mochlos | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Mochlos | period_start | `-3100` | `-3000` | wd1-replace |
| Mochlos | source_url | `https://en.wikipedia.org/wiki/Mochlos` | `https://de.wikipedia.org/wiki/Mochlos_(Ausgrabungsst%C3%A4tt` | wd1-replace |
| Moylehid | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Moylehid | period_start | `-4000` | `NULL` | wd1-clear |
| Moylehid | source_url | `https://en.wikipedia.org/wiki/Moylehid` | `https://megalithicarchaeoastronomy.blogspot.com/p/moylehid.h` | wd1-replace |
| Mynydd Carningli | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Mynydd Illtud | geom | `0101000020E610000098E516DFA6EB0BC081B0F478CDF64940` | `SRID=4326;POINT(-3.4708 51.9417)` | wd1-point |
| Mynydd Illtud | lat | `51.928145522572784` | `51.9417` | wd1-replace |
| Mynydd Illtud | lon | `-3.490064375768906` | `-3.4708` | wd1-replace |
| Mynydd Illtud | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Mynydd Illtud | period_start | `-1500` | `NULL` | wd1-clear |
| Mynydd Illtud | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Nevado de Toluca | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Nevado de Toluca | period_start | `1` | `650` | wd1-replace |
| Ngarrabullgan | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Ngarrabullgan | period_start | `-500` | `NULL` | wd1-clear |
| Ngarrabullgan | site_type | `Cave Structures` | `Sacred site` | wd1-replace |
| Nim Li Punit | period_name | `500 - 1000 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Nim Li Punit | period_start | `500` | `150` | wd1-replace |
| Nine Maidens Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Nine Maidens Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Odigitria | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Odigitria | period_start | `-4000` | `-3000` | wd1-replace |
| Olympos Antique City | site_type | `Megalithic structures` | `City` | wd1-replace |
| Orongo | site_type | `Megalithic stones` | `Village` | wd1-replace |
| Paglicci Cave | geom | `0101000020E610000011E3232322222F4017188D0F5AD54440` | `SRID=4326;POINT(15.6152 41.654408)` | wd1-point |
| Paglicci Cave | lat | `41.666810935872654` | `41.654408` | wd1-replace |
| Paglicci Cave | lon | `15.56666669667314` | `15.6152` | wd1-replace |
| Papcastle | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Papcastle | source_url | `https://en.wikipedia.org/wiki/Papcastle` | `https://en.wikipedia.org/wiki/Derventio_(Papcastle)` | wd1-replace |
| Parc Cwm Long Cairn | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Parc Cwm Long Cairn | period_start | `-3000` | `-3900` | wd1-replace |
| Pen Dinas | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Pinnacle Hill | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Pinnacle Hill | period_start | `-4500` | `NULL` | wd1-clear |
| Poundbury Hill | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Poundbury Hill | period_start | `-500` | `-3000` | wd1-replace |
| Poundbury Hill | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Roman Temple Qsarnaba | site_type | `Temple complex` | `Temple` | wd1-replace |
| Roman Villa of Ammaia | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Roman Villa of Ammaia | period_start | `1` | `-100` | wd1-replace |
| Roman Villa of Ammaia | site_type | `Residence/villa/farmhouse` | `City` | wd1-replace |
| Salapia | geom | `0101000020E6100000BABB1004F3C12F400152379830BC4440` | `SRID=4326;POINT(15.99244 41.39704)` | wd1-point |
| Salapia | lat | `41.47023298932255` | `41.39704` | wd1-replace |
| Salapia | lon | `15.878807189028397` | `15.99244` | wd1-replace |
| Schöningen Spears | site_type | `Museum` | `Archaeological site` | wd1-replace |
| Schöningen Spears | source_url | `https://en.wikipedia.org/wiki/Sch%C3%B6ningen_spears` | `https://en.wikipedia.org/wiki/Sch%C3%B6ningen_site` | wd1-replace |
| Siga | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Siga | period_start | `1` | `-400` | wd1-replace |
| Siga | site_type | `Port` | `City` | wd1-replace |
| Soyuqbulaq, Agstafa | source_url | `https://en.wikipedia.org/wiki/Soyuqbulaq,_Agstafa` | `https://agtpipeline.digitalcollections-civiconnect.com/docum` | wd1-replace |
| Stenungsund | site_type | `Cemetery` | `Burial` | wd1-replace |
| Stenungsund | source_url | `https://en.wikipedia.org/wiki/Stenungsund` | `https://www.kringla.nu/kringla/objekt?referens=raa/lamning/7` | wd1-replace |
| Sushkivka | source_url | `https://en.wikipedia.org/wiki/Sushkivka` | `https://uk.wikipedia.org/wiki/%D0%A1%D1%83%D1%88%D0%BA%D1%96` | wd1-replace |
| Temple of Khnum- Esna | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Temple of Khnum- Esna | period_start | `-500` | `-1425` | wd1-replace |
| Temple of Khnum- Esna | site_type | `Temple complex` | `Temple` | wd1-replace |
| Temple of Khnum- Esna | source_url | `https://en.wikipedia.org/wiki/Khnum` | `https://en.wikipedia.org/wiki/Temple_of_Esna` | wd1-replace |
| Templo del Sol | source_url | `https://study.com/academy/lesson/temple-of-the-sun-at-machu-` | `https://es.wikipedia.org/wiki/Templo_del_Sol_(Ollantaytambo)` | wd1-replace |
| Tilurium | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tilurium | period_start | `-500` | `NULL` | wd1-clear |
| Tilurium | site_type | `City/town/settlement` | `Fortress` | wd1-replace |
| Tombeau de Tin Hinan | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Tombeau de Tin Hinan | source_url | `https://en.wikipedia.org/wiki/Tin_Hinan` | `https://en.wikipedia.org/wiki/Tin_Hinan_Tomb` | wd1-replace |
| Trebula Balliensis | geom | `0101000020E61000007139E3C7FB7F2C400AC7FC9F9E994440` | `SRID=4326;POINT(14.266013 41.228301)` | wd1-point |
| Trebula Balliensis | lat | `41.20015334932948` | `41.228301` | wd1-replace |
| Trebula Balliensis | lon | `14.249967810141898` | `14.266013` | wd1-replace |
| Vitcos | site_type | `City/town/settlement` | `Palace` | wd1-replace |
| Wadi as-Sail Burial Mound Field | geom | `0101000020E61000009834EBD8873E4940D9FC9556122A3A40` | `SRID=4326;POINT(50.51715 26.1247)` | wd1-point |
| Wadi as-Sail Burial Mound Field | lat | `26.164342319124305` | `26.1247` | wd1-replace |
| Wadi as-Sail Burial Mound Field | lon | `50.48852073177949` | `50.51715` | wd1-replace |
| Wadi as-Sail Burial Mound Field | source_url | `https://archiqoo.com/locations/wadi_sail_burials.php#:~:text` | `https://archiqoo.com/locations/wadi_sail_burials.php` | wd1-replace |
| Waithali | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Waithali | period_start | `1` | `501` | wd1-replace |
| Warahirka | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Warahirka | period_start | `1` | `NULL` | wd1-clear |
| Warahirka | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Wat'a, Cusco | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Wat'a, Cusco | period_start | `1400` | `NULL` | wd1-clear |
| Wicklewood Roman Temple | site_type | `Temple complex` | `Temple` | wd1-replace |
| Wolf Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Wolf Cave | period_start | `-130000` | `NULL` | wd1-clear |
| Wolf Cave | source_url | `https://en.wikipedia.org/wiki/Wolf_Cave` | `https://en.wikipedia.org/wiki/Susiluola_Cave` | wd1-replace |
| Öküzlü Ören Yeri | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Öküzlü Ören Yeri | period_start | `-500` | `NULL` | wd1-clear |
| Öküzlü Ören Yeri | site_type | `Temple complex` | `Settlement` | wd1-replace |
| Öküzlü Ören Yeri | source_url | `https://www.neredekal.com/okuzlu-oren-yeri-gezilecek-yer-det` | `https://en.wikipedia.org/wiki/%C3%96k%C3%BCzl%C3%BC` | wd1-replace |
| Ərəbyengicə | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ərəbyengicə | period_start | `-4000` | `NULL` | wd1-clear |
| Κourion Ancient Amphitheatre | source_url | `https://en.wikipedia.org/wiki/Theatre` | `https://ru.wikipedia.org/wiki/%D0%A2%D0%B5%D0%B0%D1%82%D1%80` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Burnt Fen | lat | `coordinates-unresolved` | Burnt Fen is a 6,940 ha drained fen with scattered Mesolithic findspots, not a single monument; only the Wikipedia/Wikid |
| Tombeau de Tin Hinan | lat | `coordinates-unresolved` | Only the Wikipedia family (en/fr Tin Hinan Tomb articles, Wikidata Q3531165) prints a point for the tomb itself (22°53′0 |
| Cochapata | lat | `coordinates-unresolved` | The stored point is the town of Quillabamba and the Wikidata/Wikipedia point is exactly the village of Huyro (OpenStreet |
| Soyuqbulaq, Agstafa | lat | `coordinates-unresolved` | The site is the Soyugbulaq kurgan cemetery, which the excavation report places '1km north of Soyugbulaq village' at a gr |
| Sushkivka | lat | `coordinates-unresolved` | The stored point 48.6835, 30.3489 is the centre of the village of Sushkivka (Wikidata and the Ukrainian village pages gi |
| M'Daourouch | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://vici.org/vici/51634/; quote not found: https://vici.org/vici/516 |
| Ərəbyengicə | lat | `coordinates-unresolved` | The ancient settlement lies at the southern edge of Ərəbyengicə village, about 200 m north of the Araz (Wikipedia; Azerb |
| Ayawayq'u | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point for Ayawayq'u (13°19′13″S 72°05′36″W, 1.1 km from the stored point); H |
| Megalitikum Rindu Hati | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point for the Rindu Hati statue group (3.961482S 103.410824E, GPS, 0.7 km from the st |
| Ngarrabullgan | lat | `coordinates-unresolved` | Ngarrabullgan is an 18 x 6.5 km tabletop mountain whose rock shelters (Ngarrabullgan Cave, Nonda Rock) are not published |
| Inka Tampu, Vilcabamba | lat | `coordinates-unresolved` | The site is the Inca wayrana/high-altitude shrine on the summit of Idmacoya (Inka Tampu) mountain north of Yupancca in V |
| Domus De Janas Torre Argentina | lat | `coordinates-unresolved` | The domus de janas lie by the Torre Argentina tower on the coast south of Bosa; nuraghi.net (from Nurnet NUR19616) print |
| Wat'a, Cusco | lat | `coordinates-unresolved` | English Wikipedia gives 13.34694 S 72.24556 W, matching the stored point. Wikidata's -13.3922, -72.2028 is a coarse valu |
| Stenungsund | lat | `coordinates-unresolved` | The burials found in 2006 lie in the grave-and-settlement area Norum 202:1 (Holm 1:1/1:5, Norum parish), which RAÄ's reg |
| Κourion Ancient Amphitheatre | lat | `coordinates-unresolved` | Only the Wikimedia family (Wikidata and the Russian Wikipedia article, in Russian notation) prints a point for the theat |
| Warahirka | lat | `coordinates-unresolved` | The stored point (-14.145, -71.459) lies in Pampamarca District of Canas Province, Cusco, which shares only its name wit |
| Moylehid | lat | `coordinates-unresolved` | The site is the Moylehid (Eagle's Knoll) passage-tomb cairn on Belmore Mountain, recorded only by Irish grid reference ( |
| Llanos de Moxos (archaeology) | lat | `coordinates-unresolved` | The site is the archaeological landscape of the Llanos de Moxos, earthworks spread over 110,000-200,000 km2 of the Beni  |
| Roman Temple Qsarnaba | lat | `coordinates-unresolved` | The Wikidata item's point (34.0875, 36.117778) belongs to Qasr el Banat near Chlifa, a different site that the English a |
| Schöningen Spears | lat | `coordinates-unresolved` | The find site (the spear pedestal Schöningen 13 II-4 in the lignite mine) lies at about 52.1335, 10.9893 per German Wiki |
| Öküzlü Ören Yeri | lat | `coordinates-unresolved` | Only the Wikipedia family prints a point for the Öküzlü ruins: English Wikipedia gives 36.56667°N 34.16111°E and German  |
| Papcastle | lat | `coordinates-unresolved` | The site is the Roman fort Derventio on the northern edge of Papcastle. Only Vici.org prints decimal coordinates for the |
| Intikancha, Puno | lat | `coordinates-unresolved` | The stored point is the summit of Intikancha mountain as Wikipedia and Wikidata give it; the only independent readable m |
| Glubochek | lat | `coordinates-unresolved` | The stored point (47.6026, 28.5064) lies in Moldova, far from the site, which is the Trypillia mega-settlement Hlybochok |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s001-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s001 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
