# WD3 fields-wd3-2026-10-01a-s001: plan

Built 2026-10-01T18:10:09+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-01a_fields-wd3-s001`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-01a-s001:<site>:<column>`.

| counter | value |
|---|---|
| sites | 41 |
| cells | 79 |
| sites_written | 41 |
| refused | 21 |
| cells:geom | 4 |
| cells:lat | 4 |
| cells:lon | 4 |
| cells:period_name | 25 |
| cells:period_start | 25 |
| cells:site_type | 16 |
| cells:source_url | 1 |
| refused:coordinates-unresolved | 8 |
| refused:field-unresolved | 13 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Abu Salabikh | geom | `0101000020E61000003734CA5E7C994640B6B33F76A01F4040` | `SRID=4326;POINT(45.054167 32.253056)` | wd3-point |
| Abu Salabikh | lat | `32.24708440885972` | `32.253056` | wd3-replace |
| Abu Salabikh | lon | `45.199107979519276` | `45.054167` | wd3-replace |
| Ancient City of Sillyon | geom | `0101000020E61000005519747E74FA3E40EA801278DC834240` | `SRID=4326;POINT(30.9897 36.9925)` | wd3-point |
| Ancient City of Sillyon | lat | `37.03016568091864` | `36.9925` | wd3-replace |
| Ancient City of Sillyon | lon | `30.978340056747886` | `30.9897` | wd3-replace |
| Ashleys Copse | site_type | `NULL` | `Fort` | wd3-replace |
| Auga Punta | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Bartinney Castle | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Bartinney Castle | period_start | `NULL` | `-1800` | wd3-replace |
| Beacon Castle | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Beacon Castle | period_start | `NULL` | `-100` | wd3-replace |
| Berry Mound | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Berry Mound | period_start | `NULL` | `-200` | wd3-replace |
| Bilbilis | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Bilbilis | period_start | `NULL` | `-27` | wd3-replace |
| Carahunge Prehistoric Monument | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Carahunge Prehistoric Monument | period_start | `NULL` | `-2000` | wd3-replace |
| Cloghanmore | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Cloghanmore | period_start | `NULL` | `-2500` | wd3-replace |
| Cochapata | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Cosgrove, Northamptonshire | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Cosgrove, Northamptonshire | period_start | `NULL` | `100` | wd3-replace |
| Deltaterrasserne | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Deltaterrasserne | period_start | `NULL` | `-2050` | wd3-replace |
| Deltaterrasserne | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Dere Street | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Dere Street | period_start | `NULL` | `79` | wd3-replace |
| Giants' Graves | site_type | `NULL` | `Tomb` | wd3-replace |
| Hatfield Neolithic Trackway | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Hatfield Neolithic Trackway | period_start | `NULL` | `-2900` | wd3-replace |
| Hochob | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Hochob | period_start | `NULL` | `300` | wd3-replace |
| Honanki Heritage Site | geom | `0101000020E610000086FB696315E25BC07A863EC891754140` | `SRID=4326;POINT(-111.93448 34.93679)` | wd3-point |
| Honanki Heritage Site | lat | `34.918511419801646` | `34.93679` | wd3-replace |
| Honanki Heritage Site | lon | `-111.53255544042449` | `-111.93448` | wd3-replace |
| Huandacareo | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Inka Raqay | site_type | `NULL` | `Ruin` | wd3-replace |
| Konjic Mithraeum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Konjic Mithraeum | period_start | `NULL` | `301` | wd3-replace |
| Lakkos | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Lakkos | source_url | `NULL` | `https://es.wikipedia.org/wiki/Lakkos` | wd3-replace |
| Lindos | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Lindos | period_start | `NULL` | `-1000` | wd3-replace |
| Little St Bernard Pass | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Little St Bernard Pass | period_start | `NULL` | `-3000` | wd3-replace |
| Machu Pitumarka | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Machu Pitumarka | period_start | `NULL` | `1401` | wd3-replace |
| Machu Pitumarka | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Marpa, Peru | site_type | `NULL` | `Town` | wd3-replace |
| Megalithic Wall, Gubbio | site_type | `NULL` | `Wall` | wd3-replace |
| Nargiztapa | site_type | `NULL` | `Settlement` | wd3-replace |
| Ollantaytambo | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Ollantaytambo | period_start | `NULL` | `1401` | wd3-replace |
| Panamá Viejo | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Panamá Viejo | period_start | `NULL` | `1519` | wd3-replace |
| Petinesca | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Petinesca | period_start | `NULL` | `-200` | wd3-replace |
| Pod | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Pod | period_start | `NULL` | `-2500` | wd3-replace |
| Pod | site_type | `NULL` | `Fort` | wd3-replace |
| Puka Urqu, Ayacucho | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Pukara, Víctor Fajardo | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Route of Megalithic Culture | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Route of Megalithic Culture | period_start | `NULL` | `-3500` | wd3-replace |
| Schalkholz Passage Grave | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Schalkholz Passage Grave | period_start | `NULL` | `-3500` | wd3-replace |
| Taq Kasra | geom | `0101000020E61000007F26F515BA494640272BAA7571924040` | `SRID=4326;POINT(44.580833 33.093611)` | wd3-point |
| Taq Kasra | lat | `33.144087513055915` | `33.093611` | wd3-replace |
| Taq Kasra | lon | `44.57599138708337` | `44.580833` | wd3-replace |
| Taq Kasra | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Taq Kasra | period_start | `NULL` | `501` | wd3-replace |
| Uqair Salt Mine Archaeological Site | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Verterae | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Verterae | period_start | `NULL` | `79` | wd3-replace |
| Virosidum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Virosidum | period_start | `NULL` | `90` | wd3-replace |
| Xaman-Ha | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Xaman-Ha | period_start | `NULL` | `1200` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Cochapata | lat | `coordinates-unresolved` | The only printed point (Wikipedia/Wikidata, -13.0069, -72.5541) is the village of Huyro, about 22 km from the stored poi |
| Cochapata | period_start | `field-unresolved` | Wikipedia gives Cochapata only as an Inca archaeological site in Huayopata; a culture word alone gives no year or centur |
| Lakkos | lat | `coordinates-unresolved` | No page gives coordinates for Lakkos: Spanish Wikipedia is in the category of articles without coordinates, the Wikidata |
| Lakkos | period_start | `field-unresolved` | Spanish Wikipedia names only the period (Late Minoan III, IIIB or IIIC) for the finds, which is a period word and gives  |
| Puka Urqu, Ayacucho | period_start | `field-unresolved` | The Wikipedia article and the listing found give only the name's meaning, elevation and location of Puka Urqu (Lucanas P |
| Hatfield Neolithic Trackway | lat | `coordinates-unresolved` | Historic England's scheduling entry gives only an OS grid reference (SE7060407233, about 12 km south of the stored point |
| Auga Punta | period_start | `field-unresolved` | Wikipedia (en, es) and the MINCETUR tourism listing give only the location and elevation of Auga Punta; no source found  |
| Uqair Salt Mine Archaeological Site | lat | `coordinates-unresolved` | English Wikipedia carries no coordinates and says the site lies about 25 km northwest of Uqair city, while the stored po |
| Uqair Salt Mine Archaeological Site | period_start | `field-unresolved` | Wikipedia says only that the site dates back to the Hellenistic period, a period word without a year, century or millenn |
| Inka Raqay | period_start | `field-unresolved` | Only travel sites say the Inca installation was built between 1460 and 1470 (their pages are bot-blocked or lack the sen |
| Marpa, Peru | period_start | `field-unresolved` | The only date on the Wikipedia page is the Wari culture's 500-900 AD span in the highlands, which is not a date for Marp |
| Giants' Graves | lat | `coordinates-unresolved` | The entry is the Sardinian giants' graves as a type found throughout the island (about 800); no source gives one point f |
| Giants' Graves | period_start | `field-unresolved` | Sources date the class of monuments only by the Bronze Age or a broad range; no source dates the start of this entry as  |
| Giants' Graves | source_url | `field-unresolved` | The entry is a class of tombs, not one site; the Wikipedia article treats the type and no page about a single site of th |
| Ashleys Copse | period_start | `field-unresolved` | English Wikipedia only calls Ashley's Copse an Iron Age hillfort, a period word without a year or century; the Historic  |
| Megalithic Wall, Gubbio | lat | `coordinates-unresolved` | No source found prints a point for a megalithic wall at Gubbio; the Gubbio town point does not witness the stored point. |
| Megalithic Wall, Gubbio | period_start | `field-unresolved` | The Heracles page dates the medieval circuit (built within 1302), and the pre-Roman city is dated, but no source dates t |
| Route of Megalithic Culture | lat | `coordinates-unresolved` | The Route of Megalithic Culture is a 310 km tourist route; German Wikipedia prints a coordinate only as the route's star |
| Nargiztapa | period_start | `field-unresolved` | Wikipedia gives only the period words 'Bronze Age' (and Middle Bronze Age by analogy with Uzarliktapa) for Nargiztapa; a |
| Xaman-Ha | lat | `coordinates-unresolved` | The only point printed for Structure C-1 is in an unparsed d-minutes-seconds form on the Mayan Ruins Website, and no oth |
| Pukara, Víctor Fajardo | period_start | `field-unresolved` | The English Wikipedia article and Wikidata give no date for Pukara in Sarhua District, Victor Fajardo Province; no other |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-01a_fields-wd3-s001-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-01a-s001 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
