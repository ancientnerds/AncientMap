# WD3 fields-wd3-2026-10-02b-s007: plan

Built 2026-10-04T12:48:27+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s007`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s007:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 206 |
| sites_written | 100 |
| refused | 37 |
| cells:geom | 9 |
| cells:lat | 9 |
| cells:lon | 9 |
| cells:period_name | 73 |
| cells:period_start | 73 |
| cells:site_type | 32 |
| cells:source_url | 1 |
| refused:coordinates-unresolved | 15 |
| refused:country-changes | 1 |
| refused:field-unresolved | 21 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acumincum | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Acumincum | period_start | `NULL` | `-300` | wd3-replace |
| Agri Bavnehøj | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Agri Bavnehøj | period_start | `NULL` | `-1800` | wd3-replace |
| Aigeira | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Aigeira | period_start | `NULL` | `-5500` | wd3-replace |
| Al Diwan | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Al Diwan | period_start | `NULL` | `1` | wd3-replace |
| Al Diwan | site_type | `NULL` | `Religious` | wd3-replace |
| Al Thumamah, Riyadh | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Al Thumamah, Riyadh | period_start | `NULL` | `-8000` | wd3-replace |
| Al Thumamah, Riyadh | site_type | `NULL` | `Settlement` | wd3-replace |
| America's Stonehenge | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| America's Stonehenge | period_start | `NULL` | `1801` | wd3-replace |
| Ancient City of Perrin | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Ancient City of Perrin | period_start | `NULL` | `433` | wd3-replace |
| Anta da Barrosa | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Anta da Barrosa | period_start | `NULL` | `-3000` | wd3-replace |
| Archaeological Site of Grand | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Archaeological Site of Grand | period_start | `NULL` | `1` | wd3-replace |
| Arroyo de Piedra | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Awkimarka, Apurímac | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Balberta | site_type | `NULL` | `City` | wd3-replace |
| Beacon Hill, Burghclere, Hampshire | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Beacon Hill, Burghclere, Hampshire | period_start | `NULL` | `-1000` | wd3-replace |
| Botley Stone | geom | `0101000020E6100000F55E88C74ED906C0AE1E8899C33F4A40` | `SRID=4326;POINT(-2.873522 52.501072)` | wd3-point |
| Botley Stone | lat | `52.49815673014142` | `52.501072` | wd3-replace |
| Botley Stone | lon | `-2.8561072910778145` | `-2.873522` | wd3-replace |
| Botley Stone | site_type | `NULL` | `Cairn` | wd3-replace |
| Cahors | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Cahors | period_start | `NULL` | `1` | wd3-replace |
| Campu di Bonu | site_type | `NULL` | `Tomb` | wd3-replace |
| Castell Nadolig | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Castell Nadolig | period_start | `NULL` | `-800` | wd3-replace |
| Cauria | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Cauria | period_start | `NULL` | `-5700` | wd3-replace |
| Cave 20 - Pandavleni Caves | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Cave 20 - Pandavleni Caves | period_start | `NULL` | `180` | wd3-replace |
| Ceccia | site_type | `NULL` | `Monument` | wd3-replace |
| Chakdara | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Chakdara | period_start | `NULL` | `-1000` | wd3-replace |
| Chakhil-i-Ghoundi Stupa | geom | `0101000020E61000009CE4CB25479D514042501A0122374140` | `SRID=4326;POINT(70.486831 34.369459)` | wd3-point |
| Chakhil-i-Ghoundi Stupa | lat | `34.43072522911872` | `34.369459` | wd3-replace |
| Chakhil-i-Ghoundi Stupa | lon | `70.45746750747134` | `70.486831` | wd3-replace |
| Chakhil-i-Ghoundi Stupa | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Chakhil-i-Ghoundi Stupa | period_start | `NULL` | `101` | wd3-replace |
| Chakhil-i-Ghoundi Stupa | site_type | `NULL` | `Monastery` | wd3-replace |
| Choquequirao Puquio | site_type | `NULL` | `Settlement` | wd3-replace |
| Chûn Quoit | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Chûn Quoit | period_start | `NULL` | `-2400` | wd3-replace |
| Clausentum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Clausentum | period_start | `NULL` | `1` | wd3-replace |
| Clava Cairns of Aviemore | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Clava Cairns of Aviemore | period_start | `NULL` | `-4000` | wd3-replace |
| Corfinium | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Corfinium | period_start | `NULL` | `-1000` | wd3-replace |
| Craig Ty-Isaf | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Craig Ty-Isaf | period_start | `NULL` | `-800` | wd3-replace |
| Dainzú | site_type | `NULL` | `Village` | wd3-replace |
| Djemila | geom | `0101000020E6100000287F9088971D1740E7A2BCEAA22A4240` | `SRID=4326;POINT(5.736669 36.320561)` | wd3-point |
| Djemila | lat | `36.333096830470645` | `36.320561` | wd3-replace |
| Djemila | lon | `5.778898366755847` | `5.736669` | wd3-replace |
| Eryx (Sicily) | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Eryx (Sicily) | period_start | `NULL` | `-1000` | wd3-replace |
| Fethiye Antik Tiyatrosu | site_type | `NULL` | `Theater` | wd3-replace |
| Fraubillen Cross | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Fraubillen Cross | period_start | `NULL` | `-3000` | wd3-replace |
| Gate of Zeus and Hera | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Gate of Zeus and Hera | period_start | `NULL` | `-600` | wd3-replace |
| Giza Eastern Cemetery | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Giza Eastern Cemetery | period_start | `NULL` | `-2589` | wd3-replace |
| Glastonbury Lake Village | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Glastonbury Lake Village | period_start | `NULL` | `-250` | wd3-replace |
| Goonhilly Downs - Dry Tree Menhir | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Goonhilly Downs - Dry Tree Menhir | period_start | `NULL` | `-1000` | wd3-replace |
| Govurqala, Shaki | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Govurqala, Shaki | period_start | `NULL` | `401` | wd3-replace |
| Granite Thrones of Judges of Axum | site_type | `NULL` | `Monument` | wd3-replace |
| Gumbat Stupa | site_type | `NULL` | `Monastery` | wd3-replace |
| Għar Għerduf Catacombs | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Għar Għerduf Catacombs | period_start | `NULL` | `201` | wd3-replace |
| Holmbury Hill | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Holmbury Hill | period_start | `NULL` | `-100` | wd3-replace |
| Icknield Way | geom | `0101000020E6100000E65140882C8507C082E235BBD65C4940` | `SRID=4326;POINT(-0.6034 51.8445)` | wd3-point |
| Icknield Way | lat | `50.72530307894796` | `51.8445` | wd3-replace |
| Icknield Way | lon | `-2.940026344740761` | `-0.6034` | wd3-replace |
| Iklaina | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Iklaina | period_start | `NULL` | `-1600` | wd3-replace |
| Inka Tampu, Huayopata | geom | `0101000020E61000007B9124A0A42352C0E21B8FA2BB032AC0` | `SRID=4326;POINT(-72.444707 -13.054399)` | wd3-point |
| Inka Tampu, Huayopata | lat | `-13.007290916413641` | `-13.054399` | wd3-replace |
| Inka Tampu, Huayopata | lon | `-72.55692294665452` | `-72.444707` | wd3-replace |
| Inka Tampu, Huayopata | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Inti Punku | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Inti Punku | period_start | `NULL` | `1470` | wd3-replace |
| Kaljaja, Teneš Do | site_type | `NULL` | `Fortress` | wd3-replace |
| Kamyana Mohyla | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Kamyana Mohyla | period_start | `NULL` | `-2000` | wd3-replace |
| Kanlı Divane Ören Yeri | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Kanlı Divane Ören Yeri | period_start | `NULL` | `-300` | wd3-replace |
| Kulachor | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Kulachor | period_start | `NULL` | `-300` | wd3-replace |
| La Graufesenque | site_type | `NULL` | `Village` | wd3-replace |
| Lascaux | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Lascaux | period_start | `NULL` | `-17000` | wd3-replace |
| Lebak Cibedug Temple | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Lebak Cibedug Temple | period_start | `NULL` | `-2500` | wd3-replace |
| Lebak Cibedug Temple | site_type | `NULL` | `Megalithic structures` | wd3-replace |
| Lisnadarragh Wedge Tomb | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Lisnadarragh Wedge Tomb | period_start | `NULL` | `-2500` | wd3-replace |
| Lissus, Crete | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Lissus, Crete | period_start | `NULL` | `-700` | wd3-replace |
| Little Kit's Coty House | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Little Kit's Coty House | period_start | `NULL` | `-4000` | wd3-replace |
| Little Woodbury | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Little Woodbury | period_start | `NULL` | `-400` | wd3-replace |
| Lohra Megalithic Tomb | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Lohra Megalithic Tomb | period_start | `NULL` | `-3000` | wd3-replace |
| Long Wood Enclosure | geom | `0101000020E61000006F253EC32AAA0BC04FCB1B2BAE954940` | `SRID=4326;POINT(-3.45803 51.1536)` | wd3-point |
| Long Wood Enclosure | lat | `51.16937769753587` | `51.1536` | wd3-replace |
| Long Wood Enclosure | lon | `-3.4580893758144877` | `-3.45803` | wd3-replace |
| Los Sapos Archeologico | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Los Sapos Archeologico | period_start | `NULL` | `601` | wd3-replace |
| Los Sapos Archeologico | site_type | `NULL` | `Rock relief/carving` | wd3-replace |
| Lot's Cave | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Lot's Cave | period_start | `NULL` | `-3300` | wd3-replace |
| Louisville | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Louisville | period_start | `NULL` | `-400` | wd3-replace |
| Louisville | source_url | `NULL` | `https://www.barpublishing.com/book/classic-maya-polychrome-s` | wd3-replace |
| Markiani | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Markiani | period_start | `NULL` | `-3200` | wd3-replace |
| Megalithic Walls of Altamura | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Megalithic Walls of Altamura | period_start | `NULL` | `-400` | wd3-replace |
| Menir da Cabeça do Rochedo | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Menir da Cabeça do Rochedo | period_start | `NULL` | `-2000` | wd3-replace |
| Mian Khan | site_type | `NULL` | `Village` | wd3-replace |
| Minar-i Chakri | geom | `0101000020E610000037F99EF3104E5140B8FCB538FB364140` | `SRID=4326;POINT(69.292694 34.419556)` | wd3-point |
| Minar-i Chakri | lat | `34.429541672573976` | `34.419556` | wd3-replace |
| Minar-i Chakri | lon | `69.21978464627033` | `69.292694` | wd3-replace |
| Museo de Sitio Wari | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Museo de Sitio Wari | period_start | `NULL` | `1996` | wd3-replace |
| Obelisk of Thutmose I | site_type | `NULL` | `Monument` | wd3-replace |
| Offham Hill | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Offham Hill | period_start | `NULL` | `-3500` | wd3-replace |
| Old Winchester Hill | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Old Winchester Hill | period_start | `NULL` | `-2100` | wd3-replace |
| Otrar | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Otrar | period_start | `NULL` | `1` | wd3-replace |
| Petrovka Settlement | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Petrovka Settlement | period_start | `NULL` | `-2000` | wd3-replace |
| Porte Taillée | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Porte Taillée | period_start | `NULL` | `101` | wd3-replace |
| Qalagah | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Qalagah | period_start | `NULL` | `1` | wd3-replace |
| Qohaito | geom | `0101000020E61000003F289037AFB643406BF60DC5DFC12D40` | `SRID=4326;POINT(39.42389 14.86611)` | wd3-point |
| Qohaito | lat | `14.878660352663436` | `14.86611` | wd3-replace |
| Qohaito | lon | `39.42722219981123` | `39.42389` | wd3-replace |
| Qohaito | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Qohaito | period_start | `NULL` | `-700` | wd3-replace |
| Qollmay | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Riesenstein, Wolfershausen | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Riesenstein, Wolfershausen | period_start | `NULL` | `-3000` | wd3-replace |
| Roman Aqueduct of Vieu | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Roman Aqueduct of Vieu | period_start | `NULL` | `150` | wd3-replace |
| Roman Remains under Alfonso X Street | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Roman Remains under Alfonso X Street | period_start | `NULL` | `1` | wd3-replace |
| Roman Ruins of Cerro da Vila | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Roman Ruins of Cerro da Vila | period_start | `NULL` | `-100` | wd3-replace |
| Selva di Malano | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Shap Stone Avenue | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Shap Stone Avenue | period_start | `NULL` | `-3200` | wd3-replace |
| Sirnikot | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Sirnikot | period_start | `NULL` | `401` | wd3-replace |
| Sirnikot | site_type | `NULL` | `Fort` | wd3-replace |
| Stobi | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Stobi | period_start | `NULL` | `-700` | wd3-replace |
| Tabasqueno | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Tabasqueno | period_start | `NULL` | `101` | wd3-replace |
| Talayotic Settlement of Torrellisar | geom | `0101000020E6100000C69BE2040B8D1040AD476178A5F94340` | `SRID=4326;POINT(4.1589 39.8904)` | wd3-point |
| Talayotic Settlement of Torrellisar | lat | `39.95036225080489` | `39.8904` | wd3-replace |
| Talayotic Settlement of Torrellisar | lon | `4.137737346964917` | `4.1589` | wd3-replace |
| Taliata | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Taliata | period_start | `NULL` | `1` | wd3-replace |
| Taliata | site_type | `NULL` | `Fort` | wd3-replace |
| Tayasal | site_type | `NULL` | `City` | wd3-replace |
| Teotihuacan - Tetitla | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Teotihuacan - Tetitla | period_start | `NULL` | `350` | wd3-replace |
| Teotihuacan - Tetitla | site_type | `NULL` | `Residence/villa/farmhouse` | wd3-replace |
| The Water Temple | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| The Water Temple | period_start | `NULL` | `101` | wd3-replace |
| Treasure of Osztrópataka | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Treasure of Osztrópataka | period_start | `NULL` | `201` | wd3-replace |
| Treasure of Osztrópataka | site_type | `NULL` | `Burial` | wd3-replace |
| Treasury of the Acanthians | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Treasury of the Acanthians | period_start | `NULL` | `-422` | wd3-replace |
| Twmbarlwm | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Twmbarlwm | period_start | `NULL` | `-500` | wd3-replace |
| Umm El Baragat- Tebtunis | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Umm El Baragat- Tebtunis | period_start | `NULL` | `-1800` | wd3-replace |
| Usqunta | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Utroba Cave | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Utroba Cave | period_start | `NULL` | `-480` | wd3-replace |
| Wanakawri, Huánuco | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Waqlamarka | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Waqlamarka | period_start | `NULL` | `1350` | wd3-replace |
| Waqlamarka | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Ñawpallaqta, Huanca Sancos | site_type | `NULL` | `Archaeological site` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Botley Stone | period_start | `field-unresolved` | Sources call it a Bronze Age ring cairn (period word only); no year, century or millennium is given. |
| Balberta | period_start | `field-unresolved` | Wikipedia says only that Balberta first appears to have been occupied in the Late Preclassic period and that its height  |
| Campu di Bonu | lat | `coordinates-unresolved` | No readable page prints a point for the Campu di Bonu cists; the stored point equals the centre of the commune of Bisinc |
| Long Wood Enclosure | period_start | `field-unresolved` | The enclosure is unexcavated; Wikipedia says only that it may have been an Iron Age hill fort, a period word with no yea |
| Granite Thrones of Judges of Axum | lat | `coordinates-unresolved` | No readable source prints a point for the granite thrones of Aksum; Wikipedia, Wikivoyage and OpenStreetMap-based pages  |
| Granite Thrones of Judges of Axum | period_start | `field-unresolved` | The sources only mention thrones bearing inscriptions of several Aksumite kings (Ousanas, Ezana, Kaleb, Wazeba) without  |
| Granite Thrones of Judges of Axum | source_url | `field-unresolved` | No page about the Thrones of the Judges themselves was found; the available pages (Wikipedia Aksum, Obelisk of Axum, tra |
| Sirnikot | lat | `coordinates-unresolved` | The only register point (DOAM 'Sirni Kot': 26.75, 68.336389) lies about 30 km east of the stored one and of OSM's Sirnik |
| Govurqala, Shaki | lat | `coordinates-unresolved` | No source prints a point for the Shaki Govurqala described by the English article (5th-14th-century walled settlement);  |
| Govurqala, Shaki | site_type | `field-unresolved` | The only description is 'populated place' and 'walled defense stand with round and square towers'; no source names a can |
| Al Diwan | lat | `coordinates-unresolved` | No source I could read prints a point for the al-Diwan chamber itself. The points on offer (English Wikipedia, Danish Wi |
| Talayotic Settlement of Torrellisar | period_start | `field-unresolved` | The Catalan article dates the site only by period words, 'des d'inicis de l'època talaiòtica ( bronze final ) fins al ta |
| Usqunta | period_start | `field-unresolved` | No source dates the start of Usqunta (Lucanas, Ayacucho). The English article and the heritage declaration of 2009/2011  |
| Choquequirao Puquio | period_start | `field-unresolved` | English and Spanish Wikipedia name Choquequirao Puquio (San Sebastian, Cusco; not the Vilcabamba Choquequirao) only as a |
| Treasure of Osztrópataka | lat | `coordinates-unresolved` | No source gives a point for the Osztrópataka burial itself. The English Wikipedia article on the treasure carries no coo |
| Roman Remains under Alfonso X Street | lat | `coordinates-unresolved` | No source I could read prints a point for the Roman remains under Alfonso X street. English Wikipedia describes the cham |
| Roman Remains under Alfonso X Street | site_type | `field-unresolved` | The sources I could read describe vaulted chambers that supplied water to the thermal baths, and the English article is  |
| Wanakawri, Huánuco | lat | `coordinates-unresolved` | The Wikidata item Q15950097 for Wanakawri, Huanuco carries no coordinate (P625) statement, and no article or register pa |
| Wanakawri, Huánuco | period_start | `field-unresolved` | No source dates the start of Wanakawri, Huanuco. The Wikidata item Q15950097 has no inception (P571) statement and no ar |
| Icknield Way | period_start | `field-unresolved` | English Wikipedia says the Way was in use 'at least as early as the Iron Age' and that its prehistoric origin has been q |
| Qollmay | period_start | `field-unresolved` | Wikipedia and the MINCETUR inventory date Qollmay only to the Inca Empire / Late Horizon Inca (a period word); the only  |
| Fethiye Antik Tiyatrosu | lat | `coordinates-unresolved` | No readable page prints a point for the ancient theatre of Fethiye itself; the only coordinates on the Telmessos article |
| Fethiye Antik Tiyatrosu | period_start | `field-unresolved` | Livius dates the theater only to "this age", the age of the Seleucid and Pergamene empires, without a year, century or m |
| Waqlamarka | lat | `coordinates-unresolved` | No source gives a point for Waqlamarka (Hacjlasmarca). The mincetur ficha 3723 for Zona Arqueologica de Huaclas Marca de |
| Ñawpallaqta, Huanca Sancos | lat | `coordinates-unresolved` | Neither the English Wikipedia article (its infobox has an empty coordinates field) nor the Wikidata item Q15950015 carri |
| Ñawpallaqta, Huanca Sancos | period_start | `field-unresolved` | The English Wikipedia article says only that the site is an archaeological site in the Carapo District and was declared  |
| Los Sapos Archeologico | lat | `coordinates-unresolved` | No readable page prints a point for Los Sapos in a form the check reads; only an OpenStreetMap-derived aggregator gives  |
| Awkimarka, Apurímac | period_start | `field-unresolved` | No source found dates Awkimarka in Apurímac (Pomacocha / Tumay Huaraca); Wikipedia gives no date and the Chanka literatu |
| Selva di Malano | lat | `coordinates-unresolved` | No readable page found prints a point for Selva di Malano; the Soriano nel Cimino ArteCitta page and Italian Wikipedia n |
| Selva di Malano | period_start | `field-unresolved` | The ArteCitta page gives only the period word 'Etruscan Roman period' for the villages, necropolis and rock monuments; n |
| Inka Tampu, Huayopata | period_start | `field-unresolved` | MINCETUR's record says only that the prehispanic settlement dates to the Late Intermediate Period (intermedio tardio), a |
| Arroyo de Piedra | period_start | `field-unresolved` | The only source with a year is the Spanish Wikipedia infobox (construction 600-900 AD), which contradicts its own text ( |
| Taliata | lat | `coordinates-unresolved` | Neither the English Taliata article (which carries Wikipedia's 'missing geocoordinate data' marker) nor the Wikidata ite |
| Kaljaja, Teneš Do | lat | `country-changes` | the new point lies in ['Kosovo'], the site says Serbia |
| Kaljaja, Teneš Do | period_start | `field-unresolved` | The Serbian infobox gives only 'Predrimsko doba', the pre-Drimic period, which is a period word and not a year, century  |
| Treasury of the Acanthians | lat | `coordinates-unresolved` | No readable page prints a point for the Treasury of the Acanthians itself: Wikidata Q22810172 has no coordinate, no Wiki |
| Treasury of the Acanthians | site_type | `field-unresolved` | The sources call the building a treasury in the sanctuary of Apollo at Delphi; no readable source names it a temple, mon |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s007-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s007 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
