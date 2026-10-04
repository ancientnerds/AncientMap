# WD3 fields-wd3-2026-10-02b-s002: plan

Built 2026-10-04T12:43:27+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s002`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s002:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 206 |
| sites_written | 100 |
| refused | 32 |
| cells:geom | 15 |
| cells:lat | 15 |
| cells:lon | 15 |
| cells:period_name | 67 |
| cells:period_start | 67 |
| cells:site_type | 27 |
| refused:coordinates-unresolved | 9 |
| refused:field-unresolved | 23 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Al-Dafi Site | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Al-Mnaykhrat | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Al-Mnaykhrat | period_start | `NULL` | `-600` | wd3-replace |
| Al-Mnaykhrat | site_type | `NULL` | `Tomb` | wd3-replace |
| Arch of Hadrian, Capua | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Arch of Hadrian, Capua | period_start | `NULL` | `50` | wd3-replace |
| Archaeological Site of Makronissos & Ancient Tombs | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Archaeological Site of Makronissos & Ancient Tombs | period_start | `NULL` | `-310` | wd3-replace |
| Babilonie | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Babilonie | period_start | `NULL` | `-800` | wd3-replace |
| Balankanche Cave | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Balankanche Cave | period_start | `NULL` | `-300` | wd3-replace |
| Barbury Castle | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Barbury Castle | period_start | `NULL` | `-700` | wd3-replace |
| Barranc de Gàfols | site_type | `NULL` | `Settlement` | wd3-replace |
| Barrow Clump | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Barrow Clump | period_start | `NULL` | `-2000` | wd3-replace |
| Bluestonehenge | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Bluestonehenge | period_start | `NULL` | `-3000` | wd3-replace |
| Broadsands Chambered Tomb | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Broadsands Chambered Tomb | period_start | `NULL` | `-4000` | wd3-replace |
| Burnt Mound in Fox Hollies Park | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Burnt Mound in Fox Hollies Park | period_start | `NULL` | `-1500` | wd3-replace |
| Cales | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Cales | period_start | `NULL` | `-800` | wd3-replace |
| Cerje, Skopje | geom | `0101000020E6100000BD0D69D1836E3540FEBDED0D86FF4440` | `SRID=4326;POINT(21.36222 41.9325)` | wd3-point |
| Cerje, Skopje | lat | `41.99627851589683` | `41.9325` | wd3-replace |
| Cerje, Skopje | lon | `21.431698883197658` | `21.36222` | wd3-replace |
| Cerje, Skopje | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Cerje, Skopje | period_start | `NULL` | `-6000` | wd3-replace |
| Cerje, Skopje | site_type | `NULL` | `Settlement` | wd3-replace |
| Cheqollo | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Cheqollo | period_start | `NULL` | `1400` | wd3-replace |
| Cheqollo | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Cirque Romain de Vienne | site_type | `NULL` | `Monument` | wd3-replace |
| Colcampata | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Colcampata | period_start | `NULL` | `1510` | wd3-replace |
| Coppa Nevigata | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Coppa Nevigata | period_start | `NULL` | `-6000` | wd3-replace |
| Cosquer Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Cosquer Cave | period_start | `NULL` | `-27000` | wd3-replace |
| Cossington, Kent | site_type | `NULL` | `Megalithic stones` | wd3-replace |
| Daepyeong | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Daepyeong | period_start | `NULL` | `-3500` | wd3-replace |
| Derinkuyu Underground City | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Derinkuyu Underground City | period_start | `NULL` | `-800` | wd3-replace |
| Diocletianopolis, Thrace | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Diocletianopolis, Thrace | period_start | `NULL` | `-6000` | wd3-replace |
| Dohnsen, Siddernhausen - Dolmen | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Dohnsen, Siddernhausen - Dolmen | period_start | `NULL` | `-3000` | wd3-replace |
| Dolmen of Carapito I | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Dolmen of Carapito I | period_start | `NULL` | `-2900` | wd3-replace |
| Dun Carloway | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Dun Carloway | period_start | `NULL` | `1` | wd3-replace |
| Elewijt Vicus | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Elewijt Vicus | period_start | `NULL` | `1` | wd3-replace |
| Eston Nab | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Eston Nab | period_start | `NULL` | `-700` | wd3-replace |
| Etemenanki (Tower of Babel) | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Etemenanki (Tower of Babel) | period_start | `NULL` | `-1500` | wd3-replace |
| Fengbitou Archaeological Site | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Filitosa | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Filitosa | period_start | `NULL` | `-3300` | wd3-replace |
| Gavur Kalesi | geom | `0101000020E61000008F33C011F2484040F2A85489CBC14340` | `SRID=4326;POINT(32.559135 39.531485)` | wd3-point |
| Gavur Kalesi | lat | `39.5140239394549` | `39.531485` | wd3-replace |
| Gavur Kalesi | lon | `32.569887369964924` | `32.559135` | wd3-replace |
| Gavur Kalesi | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Gavur Kalesi | period_start | `NULL` | `-1700` | wd3-replace |
| Goldsborough, Scarborough | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Goldsborough, Scarborough | period_start | `NULL` | `301` | wd3-replace |
| Govurqala, Nakhchivan | geom | `0101000020E6100000DA9BF889FDBF4640ED300260B0AA4340` | `SRID=4326;POINT(45.063611 39.376944)` | wd3-point |
| Govurqala, Nakhchivan | lat | `39.333507538862115` | `39.376944` | wd3-replace |
| Govurqala, Nakhchivan | lon | `45.499924894705785` | `45.063611` | wd3-replace |
| Hassle | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Hassle | period_start | `NULL` | `-600` | wd3-replace |
| Hatun Usnu | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Heidengraben | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Heidengraben | period_start | `NULL` | `-200` | wd3-replace |
| Huichún | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Ingatambo | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Ingatambo | period_start | `NULL` | `-2500` | wd3-replace |
| Inka Raqay, Ayacucho | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Isog | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Ixkun Mayan Arqueológico Site | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Ixkun Mayan Arqueológico Site | period_start | `NULL` | `-750` | wd3-replace |
| Judeir-jo-daro | geom | `0101000020E610000059193533916C504019C26AC501B93B40` | `SRID=4326;POINT(68.25 28.466667)` | wd3-point |
| Judeir-jo-daro | lat | `27.722683275760662` | `28.466667` | wd3-replace |
| Judeir-jo-daro | lon | `65.6963623064561` | `68.25` | wd3-replace |
| Judeir-jo-daro | site_type | `NULL` | `Settlement` | wd3-replace |
| Kaljaja, Balovac | site_type | `NULL` | `Fortification` | wd3-replace |
| KaʼKabish | geom | `0101000020E610000039F5E6F2A42456C021C7D722BD163240` | `SRID=4326;POINT(-88.72972 17.81611)` | wd3-point |
| KaʼKabish | lat | `18.08882348793043` | `17.81611` | wd3-replace |
| KaʼKabish | lon | `-88.57256767801745` | `-88.72972` | wd3-replace |
| King Arthur's Round Table | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| King Arthur's Round Table | period_start | `NULL` | `-2000` | wd3-replace |
| Kültəpə | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Kültəpə | period_start | `NULL` | `-6200` | wd3-replace |
| Lagina | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Lagina | period_start | `NULL` | `-400` | wd3-replace |
| Laüs | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Laüs | period_start | `NULL` | `-510` | wd3-replace |
| Lee Wood | site_type | `NULL` | `Fort` | wd3-replace |
| Llaqtapata | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Llaqtapata | period_start | `NULL` | `1401` | wd3-replace |
| Llaqtapata | site_type | `NULL` | `Religious` | wd3-replace |
| Los Naranjos Archaeological Park | site_type | `NULL` | `City` | wd3-replace |
| Mahakali Caves | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Mahakali Caves | period_start | `NULL` | `-100` | wd3-replace |
| Mahkeme Ağacin Kültürel Jeositi | site_type | `NULL` | `Cave` | wd3-replace |
| Marki Alonia | geom | `0101000020E61000003607172D0A9D4040A467E2B12A864140` | `SRID=4326;POINT(33.3252 35.0239)` | wd3-point |
| Marki Alonia | lat | `35.04817794375347` | `35.0239` | wd3-replace |
| Marki Alonia | lon | `33.226873050922606` | `33.3252` | wd3-replace |
| Metroon | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Metroon | period_start | `NULL` | `-500` | wd3-replace |
| Natural Park Gradistea Muncelului - Cioclovina | geom | `0101000020E6100000EEDC06D29A4537408CBCB406C3CE4640` | `SRID=4326;POINT(23.231 45.571)` | wd3-point |
| Natural Park Gradistea Muncelului - Cioclovina | lat | `45.61532672715211` | `45.571` | wd3-replace |
| Natural Park Gradistea Muncelului - Cioclovina | lon | `23.271893622088946` | `23.231` | wd3-replace |
| Necropolises of Pydna | site_type | `NULL` | `Necropolis` | wd3-replace |
| Odysseus Palace | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Odysseus Palace | period_start | `NULL` | `-1300` | wd3-replace |
| Peñas de la Cerca | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Peñas de la Cerca | period_start | `NULL` | `-700` | wd3-replace |
| Pirca Pirca, Lima | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Pirca Pirca, Lima | period_start | `NULL` | `600` | wd3-replace |
| Pisarissos Antik Kenti | geom | `0101000020E6100000DE71D7265FC23F402C66284E05544240` | `SRID=4326;POINT(31.728062 36.660868)` | wd3-point |
| Pisarissos Antik Kenti | lat | `36.65641190502751` | `36.660868` | wd3-replace |
| Pisarissos Antik Kenti | lon | `31.75926440009959` | `31.728062` | wd3-replace |
| Pisarissos Antik Kenti | site_type | `NULL` | `Town` | wd3-replace |
| Pontes Fort | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Pontes Fort | period_start | `NULL` | `103` | wd3-replace |
| Przywóz | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Przywóz | period_start | `NULL` | `101` | wd3-replace |
| Pughjaredda | geom | `0101000020E61000007B79F8A41B6422402A5F4880D9C54440` | `SRID=4326;POINT(9.199167 41.570833)` | wd3-point |
| Pughjaredda | lat | `41.5457001069429` | `41.570833` | wd3-replace |
| Pughjaredda | lon | `9.195523410159458` | `9.199167` | wd3-replace |
| Pumamarka, Urubamba | site_type | `NULL` | `Fortress` | wd3-replace |
| Puruchuco | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Puruchuco | period_start | `NULL` | `900` | wd3-replace |
| Pusilha | geom | `0101000020E610000042EBF6CF8C4F56C05FA92429D21A3040` | `SRID=4326;POINT(-89.194781 16.112939)` | wd3-point |
| Pusilha | lat | `16.104769298029506` | `16.112939` | wd3-replace |
| Pusilha | lon | `-89.24296950448209` | `-89.194781` | wd3-replace |
| Pyrri | site_type | `NULL` | `Settlement` | wd3-replace |
| Qhunqhu Wankani | site_type | `NULL` | `Temple complex` | wd3-replace |
| Qillqatani | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Qillqatani | period_start | `NULL` | `-7000` | wd3-replace |
| Quriwayrachina, La Convención | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Quriwayrachina, La Convención | period_start | `NULL` | `1201` | wd3-replace |
| Regensburg | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Regensburg | period_start | `NULL` | `179` | wd3-replace |
| Rock Carvings at Alta | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Rock Carvings at Alta | period_start | `NULL` | `-5000` | wd3-replace |
| Roman Dam of Fonte Coberta | geom | `0101000020E6100000E26C0FC57E5821C0F04042262D8D4240` | `SRID=4326;POINT(-8.690411 37.110358)` | wd3-point |
| Roman Dam of Fonte Coberta | lat | `37.10294035182039` | `37.110358` | wd3-replace |
| Roman Dam of Fonte Coberta | lon | `-8.672842176564192` | `-8.690411` | wd3-replace |
| Roman Villa of Freiria | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Roman Villa of Freiria | period_start | `NULL` | `-700` | wd3-replace |
| Ruins of Talamanca | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Ruins of Talamanca | period_start | `NULL` | `860` | wd3-replace |
| Sagalassos Antoninler Çeşmesi | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Sagalassos Antoninler Çeşmesi | period_start | `NULL` | `160` | wd3-replace |
| Sagalassos Antoninler Çeşmesi | site_type | `NULL` | `Monument` | wd3-replace |
| Schanzenkopf - Schwedenschanze | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Schanzenkopf - Schwedenschanze | period_start | `NULL` | `-800` | wd3-replace |
| Sechin Alto | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Sechin Alto | period_start | `NULL` | `-2000` | wd3-replace |
| Segura Bridge | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Segura Bridge | period_start | `NULL` | `101` | wd3-replace |
| Sembel | geom | `0101000020E61000004A9B3F1E6F764340B4D2DE1143A62E40` | `SRID=4326;POINT(38.888611 15.306944)` | wd3-point |
| Sembel | lat | `15.324730452013092` | `15.306944` | wd3-replace |
| Sembel | lon | `38.92526605706969` | `38.888611` | wd3-replace |
| Seri Bahlol | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Seri Bahlol | period_start | `NULL` | `1` | wd3-replace |
| Skotino Cave | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Skotino Cave | period_start | `NULL` | `-1900` | wd3-replace |
| T'uqu T'uquyuq | site_type | `NULL` | `Rock art` | wd3-replace |
| Te Pito Kura | site_type | `NULL` | `Megalithic statues` | wd3-replace |
| Tel Hazor National Park | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Tel Hazor National Park | period_start | `NULL` | `-3000` | wd3-replace |
| Templeborough | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Templeborough | period_start | `NULL` | `1` | wd3-replace |
| The Archaeological Site of Haidra | geom | `0101000020E6100000168FC0BA19E320401758E552AAC84140` | `SRID=4326;POINT(8.4597 35.5672)` | wd3-point |
| The Archaeological Site of Haidra | lat | `35.56769787023966` | `35.5672` | wd3-replace |
| The Archaeological Site of Haidra | lon | `8.443555675512055` | `8.4597` | wd3-replace |
| The Knave | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| The Knave | period_start | `NULL` | `-200` | wd3-replace |
| Traditional Arts Museum | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Traditional Arts Museum | period_start | `NULL` | `1992` | wd3-replace |
| Upper Plym Valley | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Upper Plym Valley | period_start | `NULL` | `-2300` | wd3-replace |
| Vela Spila Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Vela Spila Cave | period_start | `NULL` | `-20000` | wd3-replace |
| Veluška Tumba | geom | `0101000020E6100000D4995E053E5F35400CD25F4FC47F4440` | `SRID=4326;POINT(21.368667 40.931778)` | wd3-point |
| Veluška Tumba | lat | `40.99817840746627` | `40.931778` | wd3-replace |
| Veluška Tumba | lon | `21.372040114971085` | `21.368667` | wd3-replace |
| Vescia | geom | `0101000020E610000013233D167D772940CC39757EE27D4540` | `SRID=4326;POINT(13.92925 41.190661)` | wd3-point |
| Vescia | lat | `42.983474547614236` | `41.190661` | wd3-replace |
| Vescia | lon | `12.733376212084783` | `13.92925` | wd3-replace |
| Waulud's Bank | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Waulud's Bank | period_start | `NULL` | `-3000` | wd3-replace |
| Worlebury Camp | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Worlebury Camp | period_start | `NULL` | `-300` | wd3-replace |
| Xpuhil | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Xpuhil | period_start | `NULL` | `300` | wd3-replace |
| Yeavering | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Yeavering | period_start | `NULL` | `501` | wd3-replace |
| Ñawpallaqta, Fajardo | site_type | `NULL` | `Archaeological site` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Inka Raqay, Ayacucho | period_start | `field-unresolved` | Valdez & Valdez (BIFEA 2000) and Wikipedia place Incaraqay on the summit of Alkowillka (Allqu Willka) only as a site of  |
| Lee Wood | period_start | `field-unresolved` | Wikipedia calls Lee Wood an Iron Age enclosure or hill fort and mentions Neolithic ashes in a fireplace under its bank,  |
| Roman Dam of Fonte Coberta | period_start | `field-unresolved` | The Portuguese article, the national register and the Portal do Arqueologo date the dam only as romana / período romano, |
| Cheqollo | lat | `coordinates-unresolved` | The only printed coordinates are the Spanish Wikipedia/Wikidata point (-13.5704, -71.9957), which lies south-west of Cus |
| Mahkeme Ağacin Kültürel Jeositi | lat | `coordinates-unresolved` | The district page of Kizilcahamam.bel.tr describes the site only in words (village 18 km from the district centre, caves |
| Mahkeme Ağacin Kültürel Jeositi | period_start | `field-unresolved` | The same page only speculates that the residents of the caves 'were the first Christians that lived in hiding' and gives |
| Vescia | period_start | `field-unresolved` | The sources give only the city's role in the Latin/Samnite wars and its destruction (340 or 314 BC); none dates its foun |
| Pisarissos Antik Kenti | period_start | `field-unresolved` | No source gives a year or century for the founding of Pisarissos: English Wikipedia says only that it was 'inhabited dur |
| Natural Park Gradistea Muncelului - Cioclovina | period_start | `field-unresolved` | A natural park has no ancient start: the park's dates (1979, Law 5/2000) are its designation, and the Dacian fortresses  |
| Pumamarka, Urubamba | period_start | `field-unresolved` | The MINCETUR inventory record says only that occupation may go back to the Periodo Intermedio Tardio (Killke) and that t |
| Al-Dafi Site | lat | `coordinates-unresolved` | No source I could read prints a point for the Al-Dafi site itself: the English Wikipedia article carries an infobox map  |
| Kaljaja, Balovac | lat | `coordinates-unresolved` | The only point a source prints is Serbian Wikipedia's 42.8117, 21.2003, which lies about 11 km from the stored point and |
| Kaljaja, Balovac | period_start | `field-unresolved` | Neither the English nor the Serbian article dates the site: they describe the trapezoidal fortification, its cut stone a |
| Necropolises of Pydna | period_start | `field-unresolved` | English Wikipedia says only that the oldest tombs are from the Bronze Age (a period word) and that the oldest graves of  |
| Cossington, Kent | lat | `coordinates-unresolved` | No readable source prints a point for the lost Cossington sarsen group; Wikipedia gives none and the Megalithic Portal r |
| Cossington, Kent | period_start | `field-unresolved` | Wikipedia says only 'Neolithic' (a period word, and hedged as a possible long barrow); no source gives a year or century |
| Pyrri | lat | `coordinates-unresolved` | Wikipedia prints no coordinates (only 'near today's village of Komin'). Pleiades 197461 gives a 1:1M-scale DARMC point ( |
| Pyrri | period_start | `field-unresolved` | Wikipedia only calls it an ancient Roman settlement; Pleiades gives only the Roman/late-antique period range (30 BC - AD |
| Hatun Usnu | period_start | `field-unresolved` | No source found dates Hatun Usnu. |
| Traditional Arts Museum | lat | `coordinates-unresolved` | No readable source gives a point for this museum. The Arabic Wikipedia article on it carries no coordinate template, no  |
| Traditional Arts Museum | site_type | `field-unresolved` | The source that describes the site, the Arabic Wikipedia article, calls it a museum in Arabic (متحف) only, and no page I |
| Traditional Arts Museum | source_url | `field-unresolved` | The only page about this very museum that I could read is its Arabic Wikipedia article, which names the site in Arabic o |
| Judeir-jo-daro | period_start | `field-unresolved` | Sources say only that the site belongs to the Mature Harappan phase (a period word); the DOAM chronology 3500 BCE - 1800 |
| T'uqu T'uquyuq | lat | `coordinates-unresolved` | No readable source prints a point for T'uqu T'uquyuq: Wikipedia and Wikidata carry none, and the only point found (an Op |
| T'uqu T'uquyuq | period_start | `field-unresolved` | No source dates T'uqu T'uquyuq; only a travel page says the Saywa rock paintings are up to 4,000 years old, which is not |
| Te Pito Kura | period_start | `field-unresolved` | No readable source dates the start of the Te Pito Kura ahu itself; the only date found (Paro erected around 1620) dates  |
| Barranc de Gàfols | period_start | `field-unresolved` | The sources date the site's phases only as periods, not as a calendar year: the English Wikipedia infobox lists 'Periods |
| Isog | period_start | `field-unresolved` | Wikipedia (en, es) gives no date for Isog, only its location and the 1956-57 excavations; no source dates its start. |
| Pirca Pirca, Lima | site_type | `field-unresolved` | The MINCETUR record classes the site as Ciudadelas and describes dwellings, storehouses and ritual use, but no readable  |
| Huichún | lat | `coordinates-unresolved` | No readable source prints a point for Huichún: the English Wikipedia article and its Wikidata item carry no coordinates  |
| Huichún | period_start | `field-unresolved` | No source found gives a date for the start of Huichún; Wikipedia only gives its 2006 heritage declaration. |
| Ñawpallaqta, Fajardo | period_start | `field-unresolved` | The English Wikipedia article locates the site and explains the Quechua name ('ancient place') but gives no year, centur |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s002-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s002 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
