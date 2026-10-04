# WD3 fields-wd3-2026-10-02b-s004: plan

Built 2026-10-04T12:45:28+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s004`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s004:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 197 |
| sites_written | 98 |
| refused | 30 |
| cells:geom | 8 |
| cells:lat | 8 |
| cells:lon | 8 |
| cells:period_name | 73 |
| cells:period_start | 73 |
| cells:site_type | 25 |
| cells:source_url | 2 |
| refused:coordinates-unresolved | 11 |
| refused:country-changes | 2 |
| refused:field-unresolved | 17 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Aguntum | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Aguntum | period_start | `NULL` | `-50` | wd3-replace |
| Alabanda | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Alabanda | period_start | `NULL` | `-400` | wd3-replace |
| Alam Bridge Inscriptions | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Alam Bridge Inscriptions | period_start | `NULL` | `301` | wd3-replace |
| Alogonia - Town | geom | `0101000020E61000008400F3BB3FDC3540C66CA1007A944240` | `SRID=4326;POINT(22.2612 36.9556)` | wd3-point |
| Alogonia - Town | lat | `37.159973219700575` | `36.9556` | wd3-replace |
| Alogonia - Town | lon | `21.860347506357826` | `22.2612` | wd3-replace |
| Aqua Augusta, Naples | geom | `0101000020E6100000DF10E3C7FB7F2C409AB36E0CB16A4440` | `SRID=4326;POINT(14.0803 40.7953)` | wd3-point |
| Aqua Augusta, Naples | lat | `40.833528093389035` | `40.7953` | wd3-replace |
| Aqua Augusta, Naples | lon | `14.249967810123449` | `14.0803` | wd3-replace |
| Araghju | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Araghju | period_start | `NULL` | `-2000` | wd3-replace |
| Arbury Banks, Hertfordshire | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Arbury Banks, Hertfordshire | period_start | `NULL` | `-1000` | wd3-replace |
| Archaeological Ensemble of Tárraco | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Archaeological Site, Argos | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Archaeological Site, Argos | period_start | `NULL` | `-3000` | wd3-replace |
| Atzompa | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Atzompa | period_start | `NULL` | `650` | wd3-replace |
| Atzompa | site_type | `NULL` | `City/town/settlement` | wd3-replace |
| Badshot Lea Long Barrow | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Badshot Lea Long Barrow | period_start | `NULL` | `-4000` | wd3-replace |
| Bava Pyare Caves | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Bava Pyare Caves | period_start | `NULL` | `-200` | wd3-replace |
| Bury Camp | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Bury Camp | period_start | `NULL` | `-350` | wd3-replace |
| Caer Drewyn | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Caer Drewyn | period_start | `NULL` | `-500` | wd3-replace |
| Cape St. Athanasius Ancient Settlement | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Cape St. Athanasius Ancient Settlement | period_start | `NULL` | `-600` | wd3-replace |
| Carmona, Spain | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Carmona, Spain | period_start | `NULL` | `-800` | wd3-replace |
| Carn Menyn | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Carn Menyn | period_start | `NULL` | `-6000` | wd3-replace |
| Castell Henllys | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Castell Henllys | period_start | `NULL` | `-500` | wd3-replace |
| Cefn Bryn | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Cefn Bryn | period_start | `NULL` | `-2300` | wd3-replace |
| Celemantia | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Celemantia | period_start | `NULL` | `1` | wd3-replace |
| Chacchoben | geom | `0101000020E61000003E613B18200A56C08E32C594C7073340` | `SRID=4326;POINT(-88.232381 19.000817)` | wd3-point |
| Chacchoben | lat | `19.03038911642448` | `19.000817` | wd3-replace |
| Chacchoben | lon | `-88.1582089023477` | `-88.232381` | wd3-replace |
| Chawaytiri | site_type | `NULL` | `Rock art` | wd3-replace |
| City of Alesia | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| City of Alesia | period_start | `NULL` | `-200` | wd3-replace |
| Colha | geom | `0101000020E61000009D086E02B82356C0281A92A7C7133240` | `SRID=4326;POINT(-88.36654 17.95572)` | wd3-point |
| Colha | lat | `18.077265237016178` | `17.95572` | wd3-replace |
| Colha | lon | `-88.55810604806398` | `-88.36654` | wd3-replace |
| Coom Wedge Tomb | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Coom Wedge Tomb | period_start | `NULL` | `-2500` | wd3-replace |
| Craig Rhiwarth | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Craig Rhiwarth | period_start | `NULL` | `-800` | wd3-replace |
| Cras - Ring Cairn to North of | site_type | `NULL` | `Cairn` | wd3-replace |
| Cras - Ring Cairn to North of | source_url | `NULL` | `https://cy.wikipedia.org/wiki/Cras_(carnedd_i%27r_Gorllewin)` | wd3-replace |
| Craterus' ex voto | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Craterus' ex voto | period_start | `NULL` | `-320` | wd3-replace |
| Craterus' ex voto | site_type | `NULL` | `Monument` | wd3-replace |
| Córdoba, Spain | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Córdoba, Spain | period_start | `NULL` | `-800` | wd3-replace |
| Dinas Powys Hillfort | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Dinas Powys Hillfort | period_start | `NULL` | `-300` | wd3-replace |
| Duloe Stone Circle | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Duloe Stone Circle | period_start | `NULL` | `-2000` | wd3-replace |
| Dun Telve | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Dun Telve | period_start | `NULL` | `-400` | wd3-replace |
| Dzibilchaltun | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Dzibilchaltun | period_start | `NULL` | `-900` | wd3-replace |
| El Castillón | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| El Castillón | period_start | `NULL` | `401` | wd3-replace |
| El Oso, Ávila | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| El Oso, Ávila | period_start | `NULL` | `-500` | wd3-replace |
| Etruscan Pyramid of Bomarzo | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Etruscan Pyramid of Bomarzo | period_start | `NULL` | `-700` | wd3-replace |
| Etruscan Pyramid of Bomarzo | site_type | `NULL` | `Monument` | wd3-replace |
| Frohnleiten | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Frohnleiten | period_start | `NULL` | `1280` | wd3-replace |
| Gabarnmung Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Gabarnmung Cave | period_start | `NULL` | `-45180` | wd3-replace |
| Goosehill Camp | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Goosehill Camp | period_start | `NULL` | `-700` | wd3-replace |
| Grange Stone Circle | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Grange Stone Circle | period_start | `NULL` | `-3000` | wd3-replace |
| Grenoble Archaeological Museum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Grenoble Archaeological Museum | period_start | `NULL` | `301` | wd3-replace |
| Helorus | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Helorus | period_start | `NULL` | `-800` | wd3-replace |
| Hierapolis | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Hierapolis | period_start | `NULL` | `-700` | wd3-replace |
| Hotié de Viviane | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Hotié de Viviane | period_start | `NULL` | `-3355` | wd3-replace |
| Huaca Huantinamarca | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Huaca Huantinamarca | period_start | `NULL` | `1401` | wd3-replace |
| Huaca Huantinamarca | site_type | `NULL` | `Pyramid complex` | wd3-replace |
| Incahuasi, Lima | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Incahuasi, Lima | period_start | `NULL` | `1450` | wd3-replace |
| Incahuasi, Lima | site_type | `NULL` | `Urban` | wd3-replace |
| Inka Tunuwiri | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Inka Tunuwiri | period_start | `NULL` | `-500` | wd3-replace |
| Inkilltambo | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Inkilltambo | period_start | `NULL` | `1420` | wd3-replace |
| Julliberrie's Grave | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Julliberrie's Grave | period_start | `NULL` | `-4000` | wd3-replace |
| Kasserine | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Kasserine | period_start | `NULL` | `101` | wd3-replace |
| Kempraten | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Kempraten | period_start | `NULL` | `1` | wd3-replace |
| Kinal | site_type | `NULL` | `City` | wd3-replace |
| King John's Hill | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| King John's Hill | period_start | `NULL` | `-100` | wd3-replace |
| Lauriacum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Lauriacum | period_start | `NULL` | `200` | wd3-replace |
| Lavatrae | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Lavatrae | period_start | `NULL` | `70` | wd3-replace |
| Lefkaritis Tomb | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Lefkaritis Tomb | period_start | `NULL` | `-800` | wd3-replace |
| Llactan | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Lopen Roman Mosaic | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Lopen Roman Mosaic | period_start | `NULL` | `360` | wd3-replace |
| Mawk'allaqta, La Unión | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Menosgada | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Menosgada | period_start | `NULL` | `-600` | wd3-replace |
| Military Way - Hadrian's Wall | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Military Way - Hadrian's Wall | period_start | `NULL` | `162` | wd3-replace |
| Mullu Q'awa | site_type | `NULL` | `Settlement` | wd3-replace |
| Mulri Hills | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Nimrod Fortress | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Nimrod Fortress | period_start | `NULL` | `-332` | wd3-replace |
| Nymphaeum (Illyria) | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Nymphaeum (Illyria) | period_start | `NULL` | `-500` | wd3-replace |
| Pacbitun | site_type | `NULL` | `City/town/settlement, Pyramid complex` | wd3-replace |
| Parque Arqueológico Uaxactun | site_type | `NULL` | `City` | wd3-replace |
| Petriana | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Petriana | period_start | `NULL` | `122` | wd3-replace |
| Pillkukayna | geom | `0101000020E6100000EA0C1468444B51C0FD9E91E1C90430C0` | `SRID=4326;POINT(-69.14425 -16.048639)` | wd3-point |
| Pillkukayna | lat | `-16.01870546155168` | `-16.048639` | wd3-replace |
| Pillkukayna | lon | `-69.17605020483066` | `-69.14425` | wd3-replace |
| Pillkukayna | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Pillkukayna | period_start | `NULL` | `1471` | wd3-replace |
| Pont sur la Laye | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Pont sur la Laye | period_start | `NULL` | `1101` | wd3-replace |
| Pumamarka, San Sebastián | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Quillcay Machay | site_type | `NULL` | `Rock art` | wd3-replace |
| Quishuar Archaeological Site | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Rano Raraku | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Rano Raraku | period_start | `NULL` | `1200` | wd3-replace |
| Ringsbury Camp | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Ringsbury Camp | period_start | `NULL` | `-50` | wd3-replace |
| Roma Tiyatrosu | site_type | `NULL` | `Theatre` | wd3-replace |
| Roman Temple Temnin | site_type | `NULL` | `Sanctuary` | wd3-replace |
| Roman Walls of Córdoba | geom | `0101000020E6100000311B8A33001113C0E0854426F6EE4240` | `SRID=4326;POINT(-4.768655 37.892469)` | wd3-point |
| Roman Walls of Córdoba | lat | `37.86688688608024` | `37.892469` | wd3-replace |
| Roman Walls of Córdoba | lon | `-4.766602330498061` | `-4.768655` | wd3-replace |
| Rough Tor | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Rough Tor | period_start | `NULL` | `-4000` | wd3-replace |
| Saraakallio Rock Paintings | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Saraakallio Rock Paintings | period_start | `NULL` | `-5000` | wd3-replace |
| Shell Mound in Dongsam-dong, Busan | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Shell Mound in Dongsam-dong, Busan | period_start | `NULL` | `-3500` | wd3-replace |
| Shypyntsi | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Shypyntsi | period_start | `NULL` | `-5000` | wd3-replace |
| Sitio Sierra | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Sitio Sierra | period_start | `NULL` | `-300` | wd3-replace |
| Sitio Sierra | site_type | `NULL` | `Village` | wd3-replace |
| Su Kemeri | site_type | `NULL` | `Aqueduct` | wd3-replace |
| Su Kemeri | source_url | `NULL` | `https://www.wikidata.org/wiki/Q135582591` | wd3-replace |
| Te Pito O Te Henua | site_type | `NULL` | `Magnetic anomaly` | wd3-replace |
| Temple of Apollo, Melite | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Temple of Apollo, Melite | period_start | `NULL` | `101` | wd3-replace |
| The Bulwarks, Porthkerry | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| The Bulwarks, Porthkerry | period_start | `NULL` | `-200` | wd3-replace |
| Tomb of Funeral Beds - Necropolis of Banditaccia | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Tomb of Funeral Beds - Necropolis of Banditaccia | period_start | `NULL` | `-550` | wd3-replace |
| Tomb of Funeral Beds - Necropolis of Banditaccia | site_type | `NULL` | `Tomb` | wd3-replace |
| Tongobriga | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Tongobriga | period_start | `NULL` | `1` | wd3-replace |
| Trippet Stones | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Trippet Stones | period_start | `NULL` | `-1700` | wd3-replace |
| Uçan ağıl | geom | `0101000020E6100000FF77283979B746403AFE0E6138934340` | `SRID=4326;POINT(45.508 39.291)` | wd3-point |
| Uçan ağıl | lat | `39.15015805465778` | `39.291` | wd3-replace |
| Uçan ağıl | lon | `45.43338694072735` | `45.508` | wd3-replace |
| Vaphio | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Vaphio | period_start | `NULL` | `-1600` | wd3-replace |
| Vertillum | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Vertillum | period_start | `NULL` | `-150` | wd3-replace |
| Warham Camp | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Warham Camp | period_start | `NULL` | `-200` | wd3-replace |
| Welbeck Hill | geom | `0101000020E610000058E6DBCC97F3C8BF61BD8ACA08C64A40` | `SRID=4326;POINT(-0.166799 53.519505)` | wd3-point |
| Welbeck Hill | lat | `53.547143285507225` | `53.519505` | wd3-replace |
| Welbeck Hill | lon | `-0.19493386748199515` | `-0.166799` | wd3-replace |
| Welshbury Hill | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Welshbury Hill | period_start | `NULL` | `-1600` | wd3-replace |
| Wilbury Hill Camp | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Wilbury Hill Camp | period_start | `NULL` | `-700` | wd3-replace |
| Wilca | site_type | `NULL` | `Archaeological site` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Wilca | period_start | `field-unresolved` | No source gives a construction or first-occupation date for Wilca. The English article is a one-sentence stub with no da |
| Mulri Hills | lat | `coordinates-unresolved` | Wikipedia gives no coordinates for the Mulri Hills (a coord-missing notice) and places them only in Gulshan Town, Karach |
| Mulri Hills | period_start | `field-unresolved` | Wikipedia names only the periods (Late Palaeolithic and Mesolithic) of the flint scatters found on the Mulri Hills; a pe |
| Roma Tiyatrosu | lat | `coordinates-unresolved` | No source prints a point for the Anavarza theatre itself. Wikidata Q29002435 gives 37°14'38.400"N, 35°53'42.000"E = 37.2 |
| Roma Tiyatrosu | period_start | `field-unresolved` | No source that states the value dates this theatre's start. English Wikipedia names the monument but gives no year for i |
| Roma Tiyatrosu | source_url | `field-unresolved` | No page was found that documents this theatre as a site of its own: the English Wikipedia article, the Turkish Museums p |
| Marco Gonzalez Archaeological Reserve | lat | `country-changes` | the new point lies in [], the site says Belize |
| Quillcay Machay | period_start | `field-unresolved` | English and Spanish Wikipedia describe the Quillcay Machay paintings only as having later Chavinoid influence, with no y |
| Te Pito O Te Henua | period_start | `field-unresolved` | The stone is a natural basalt boulder; German Wikipedia and Czech Wikipedia give only the legend that Hotu Matu'a brough |
| Roman Temple Temnin | lat | `coordinates-unresolved` | The only point for the Temnin el-Fawqa sanctuary (the nymphaeum of Ain el-Jobb) is Vici's pin, and its own annotation sa |
| Roman Temple Temnin | period_start | `field-unresolved` | No page found dates the Temnin el-Fawqa sanctuary or nymphaeum; the Wikipedia and Vici pages give only 'Roman' without a |
| Alogonia - Town | period_start | `field-unresolved` | Wikipedia only calls Alagonia an ancient town of Messenia taken from Pausanias; Pleiades and ToposText give only the att |
| Craterus' ex voto | lat | `coordinates-unresolved` | No readable source prints a point for the Craterus monument itself; the Wikipedia article and its Commons category give  |
| Chawaytiri | period_start | `field-unresolved` | English and Spanish Wikipedia describe the Chawaytiri rock paintings without any date; the one page that says Inca era ( |
| Llactan | period_start | `field-unresolved` | Spanish Wikipedia states the culture and period of Llactan have not yet been determined; no source found dates it. |
| Quishuar Archaeological Site | lat | `coordinates-unresolved` | Neither the English Wikipedia article nor its Wikidata item prints a point for Quishuar (the article is listed as missin |
| Quishuar Archaeological Site | period_start | `field-unresolved` | The MINCETUR inventory says the Yanama ruins including Quishuar are pre-Inca but that their history is unknown for lack  |
| Sitio Sierra | lat | `coordinates-unresolved` | Wikipedia and Wikidata give no point for Sitio Sierra; the Smithsonian STRI page gives only a grid reference (5379800E-9 |
| Military Way - Hadrian's Wall | lat | `coordinates-unresolved` | The Military Way is a long linear road along Hadrian's Wall; neither Wikipedia nor its Wikidata item gives a coordinate, |
| Mullu Q'awa | period_start | `field-unresolved` | The Ministerio de Cultura associates the site only with the Late Intermediate and Late Horizon periods and Wikipedia say |
| Lefkaritis Tomb | lat | `coordinates-unresolved` | No readable page prints a point for the Lefkaritis Tomb: Wikipedia and Wikidata carry none, the Hadjisavvas papers only  |
| Cras - Ring Cairn to North of | period_start | `field-unresolved` | The Welsh article about the ring cairn says it was raised in the Iron Age 'mae'n debyg' (probably) and the scheduled mon |
| Kinal | period_start | `field-unresolved` | Wikipedia dates only the major occupational phase to the Late Classic (c.600-900 AD) and a building program to the 8th c |
| The Lost City of Heracleion | lat | `country-changes` | the new point lies in [], the site says Egypt |
| Pumamarka, San Sebastián | lat | `coordinates-unresolved` | Wikipedia and Wikidata give no point for Pumamarka in San Sebastian; the stored point lies outside the bounding box of t |
| Pumamarka, San Sebastián | period_start | `field-unresolved` | The Cusco culture directorate and municipal pages call it a pre-Hispanic religious centre with Inca elements but give no |
| Su Kemeri | period_start | `field-unresolved` | The Wikidata item for the Phaselis Aqueduct records only its type, country, administrative location, conservation state  |
| Nymphaeum (Illyria) | lat | `coordinates-unresolved` | The English and Albanian Wikipedia articles print no coordinates; the Digital Atlas of the Roman Empire point is 1.7 km  |
| Mawk'allaqta, La Unión | lat | `coordinates-unresolved` | Neither the English nor the French Wikipedia article for Mawk'allaqta (La Union, Puyca) prints a point, the Mincetur rec |
| Mawk'allaqta, La Unión | period_start | `field-unresolved` | Wikipedia gives only 'about 500CE to 1000CE' as the span of the Wari culture that developed the site, a period range for |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s004-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s004 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
