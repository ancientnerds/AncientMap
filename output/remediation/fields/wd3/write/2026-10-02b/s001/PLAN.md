# WD3 fields-wd3-2026-10-02b-s001: plan

Built 2026-10-04T12:40:35+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s001`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s001:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 202 |
| sites_written | 100 |
| refused | 32 |
| cells:geom | 7 |
| cells:lat | 7 |
| cells:lon | 7 |
| cells:period_name | 75 |
| cells:period_start | 75 |
| cells:site_type | 27 |
| cells:source_url | 4 |
| refused:coordinates-unresolved | 9 |
| refused:field-unresolved | 23 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Alampra | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Alampra | period_start | `NULL` | `-1900` | wd3-replace |
| Alcimoennis | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Alcimoennis | period_start | `NULL` | `-200` | wd3-replace |
| Alikomektepe | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Alikomektepe | period_start | `NULL` | `-5000` | wd3-replace |
| Alikomektepe | site_type | `NULL` | `Settlement` | wd3-replace |
| Almsworthy Common | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Almsworthy Common | period_start | `NULL` | `-2350` | wd3-replace |
| Ancient City of Selge | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Ancient City of Selge | period_start | `NULL` | `-1300` | wd3-replace |
| Ancient City of Telmessos | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Ancient City of Telmessos | period_start | `NULL` | `-500` | wd3-replace |
| Ancient Kymissala | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Ancient Kymissala | period_start | `NULL` | `-700` | wd3-replace |
| Araltobe Kurgan | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Araltobe Kurgan | period_start | `NULL` | `-300` | wd3-replace |
| Archaeological Park of Segóbriga | geom | `0101000020E6100000AB03D281366E06C06ACFFC94BDF54340` | `SRID=4326;POINT(-2.81053 39.88591)` | wd3-point |
| Archaeological Park of Segóbriga | lat | `39.91984808296441` | `39.88591` | wd3-replace |
| Archaeological Park of Segóbriga | lon | `-2.8038149015632903` | `-2.81053` | wd3-replace |
| Archaeological Park of Segóbriga | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Archaeological Park of Segóbriga | period_start | `NULL` | `-500` | wd3-replace |
| Archaeological Site of Olympia | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Archaeological Site of Olympia | period_start | `NULL` | `-2000` | wd3-replace |
| Aya Muqu | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Ayawayq'u | geom | `0101000020E6100000070840DF4F0552C0447E137E9AA42AC0` | `SRID=4326;POINT(-72.09333 -13.32028)` | wd3-point |
| Ayawayq'u | lat | `-13.321491184119743` | `-13.32028` | wd3-replace |
| Ayawayq'u | lon | `-72.08300000432074` | `-72.09333` | wd3-replace |
| Babel Lion | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Babel Lion | period_start | `NULL` | `-605` | wd3-replace |
| Babylonian Theatre | geom | `0101000020E610000022B74868ED3946408CC2F39F8B4F4040` | `SRID=4326;POINT(44.429667 32.541667)` | wd3-point |
| Babylonian Theatre | lat | `32.621448511145985` | `32.541667` | wd3-replace |
| Babylonian Theatre | lon | `44.45255759764247` | `44.429667` | wd3-replace |
| Bassianae | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Bassianae | period_start | `NULL` | `1` | wd3-replace |
| Batán Grande | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Batán Grande | period_start | `NULL` | `701` | wd3-replace |
| Bilbao | site_type | `NULL` | `Urban` | wd3-replace |
| Bonampak | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Bonampak | period_start | `NULL` | `300` | wd3-replace |
| Burley Wood | site_type | `NULL` | `Fort` | wd3-replace |
| Carisbrook Stone Arrangement | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Castell Caer Seion | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Castell Caer Seion | period_start | `NULL` | `-600` | wd3-replace |
| Castle Naze | geom | `0101000020E61000003455CD0CCBE6FEBF2FB22FBF1AA44A40` | `SRID=4326;POINT(-1.92102 53.3027)` | wd3-point |
| Castle Naze | lat | `53.28206624821575` | `53.3027` | wd3-replace |
| Castle Naze | lon | `-1.9313459873277` | `-1.92102` | wd3-replace |
| Cave of Pedra Furada | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Cave of Pedra Furada | period_start | `NULL` | `-3095` | wd3-replace |
| Centro Arqueológico de Chinchero | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Centro Arqueológico de Chinchero | period_start | `NULL` | `1480` | wd3-replace |
| Centro Arqueológico de Chinchero | site_type | `NULL` | `Palace` | wd3-replace |
| Conchalito | site_type | `NULL` | `Funerary` | wd3-replace |
| Condorcaga | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Currachjaghju | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Densuș Church | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Densuș Church | period_start | `NULL` | `1250` | wd3-replace |
| Dolmen de Bagneux | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Dolmen de Bagneux | period_start | `NULL` | `-3000` | wd3-replace |
| Dolmen del prado de Lácara | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Dolmen del prado de Lácara | period_start | `NULL` | `-4000` | wd3-replace |
| Dumat al-Jandal Wall | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Dumat al-Jandal Wall | period_start | `NULL` | `1` | wd3-replace |
| Emilianus - Stollen | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Emilianus - Stollen | period_start | `NULL` | `101` | wd3-replace |
| Foel Dduarth - Cairn to North-East of | site_type | `NULL` | `Cairn` | wd3-replace |
| Foel Dduarth - Cairn to North-East of | source_url | `NULL` | `https://cy.wikipedia.org/wiki/Carnedd_gron_Foel_Dduarth` | wd3-replace |
| Gaer, Black Mountains | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Gaer, Black Mountains | period_start | `NULL` | `-450` | wd3-replace |
| Glösa | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Glösa | period_start | `NULL` | `-3000` | wd3-replace |
| Gough's Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Gough's Cave | period_start | `NULL` | `-12750` | wd3-replace |
| Guellayhuasin | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Guellayhuasin | period_start | `NULL` | `1200` | wd3-replace |
| Hellenistic House | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Hellenistic House | period_start | `NULL` | `-400` | wd3-replace |
| Hollingbury Castle | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Hollingbury Castle | period_start | `NULL` | `-600` | wd3-replace |
| Horvat Shema | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Horvat Shema | period_start | `NULL` | `180` | wd3-replace |
| Hov Dås | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Hov Dås | period_start | `NULL` | `-3950` | wd3-replace |
| Hunnum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Hunnum | period_start | `NULL` | `122` | wd3-replace |
| Intikancha, Puno | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Intikancha, Puno | source_url | `NULL` | `https://en.wikipedia.org/wiki/Intikancha_(Puno)` | wd3-replace |
| Juhor | source_url | `NULL` | `https://en.wikipedia.org/wiki/Juhor` | wd3-replace |
| Justinianopolis (Epirus) | site_type | `NULL` | `Town` | wd3-replace |
| Krimisa | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Krimisa | period_start | `NULL` | `-700` | wd3-replace |
| Kudakkallu Parambu - Megalithic Burial Site | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Kudakkallu Parambu - Megalithic Burial Site | period_start | `NULL` | `-2000` | wd3-replace |
| La Corona | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| La Corona | period_start | `NULL` | `250` | wd3-replace |
| La Roche-aux-Fées | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| La Roche-aux-Fées | period_start | `NULL` | `-3000` | wd3-replace |
| Labna | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Labna | period_start | `NULL` | `200` | wd3-replace |
| Las Capellanías | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Las Capellanías | period_start | `NULL` | `-2700` | wd3-replace |
| Los Pinchudos | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Los Pinchudos | period_start | `NULL` | `1470` | wd3-replace |
| Machaquila | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Machaquila | period_start | `NULL` | `701` | wd3-replace |
| Mitla, Entrance to Tomb 1 | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Mitla, Entrance to Tomb 1 | period_start | `NULL` | `100` | wd3-replace |
| Moel y Gaer, Rhosesmor | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Moel y Gaer, Rhosesmor | period_start | `NULL` | `-3000` | wd3-replace |
| Monte Lazzu | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Monte Lazzu | period_start | `NULL` | `-4000` | wd3-replace |
| Mortuary Temple of Amenhotep III | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Mortuary Temple of Amenhotep III | period_start | `NULL` | `-1352` | wd3-replace |
| Mérida Anthropological Museum | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Mérida Anthropological Museum | period_start | `NULL` | `1904` | wd3-replace |
| Nagara (Ancient city) | geom | `0101000020E610000070F4AFEF5C9D514017C6E33F0B374140` | `SRID=4326;POINT(70.397583 34.446552)` | wd3-point |
| Nagara (Ancient city) | lat | `34.43003080961005` | `34.446552` | wd3-replace |
| Nagara (Ancient city) | lon | `70.45879738028611` | `70.397583` | wd3-replace |
| Nashtifan Windmills | site_type | `NULL` | `Heritage site` | wd3-replace |
| Nicopolis ad Nestum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Nicopolis ad Nestum | period_start | `NULL` | `106` | wd3-replace |
| Oppidum Uetliberg | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Oppidum Uetliberg | period_start | `NULL` | `-4000` | wd3-replace |
| Oxkintok | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Oxkintok | period_start | `NULL` | `-600` | wd3-replace |
| Pavlopetri | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Pavlopetri | period_start | `NULL` | `-3500` | wd3-replace |
| Periano Ghundai | geom | `0101000020E6100000A463A2F3B45C5140C12F83038F573F40` | `SRID=4326;POINT(69.383333 31.366667)` | wd3-point |
| Periano Ghundai | lat | `31.342025966194118` | `31.366667` | wd3-replace |
| Periano Ghundai | lon | `69.44854441507647` | `69.383333` | wd3-replace |
| Pigi Athinas | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Pigi Athinas | period_start | `NULL` | `-7000` | wd3-replace |
| Portfield Hillfort | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Portfield Hillfort | period_start | `NULL` | `-1000` | wd3-replace |
| Pumawasi, Anta | site_type | `NULL` | `Rock art` | wd3-replace |
| Punic Building, Żurrieq | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Punic Building, Żurrieq | period_start | `NULL` | `-600` | wd3-replace |
| Pyramid of Khentkaus II | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Pyramid of Khentkaus II | period_start | `NULL` | `-2460` | wd3-replace |
| Qaqapatan | site_type | `NULL` | `Rock art` | wd3-replace |
| Rag-i-Bibi | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Rag-i-Bibi | period_start | `NULL` | `201` | wd3-replace |
| Roman Bridge, Saint-Thibéry | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Roman Bridge, Saint-Thibéry | period_start | `NULL` | `-27` | wd3-replace |
| Rudston Monolith | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Rudston Monolith | period_start | `NULL` | `-3500` | wd3-replace |
| San Claudio | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| San Claudio | period_start | `NULL` | `-200` | wd3-replace |
| San Claudio | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Sidi Said | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Sidi Said | period_start | `NULL` | `101` | wd3-replace |
| St. Paul's Catacombs | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| St. Paul's Catacombs | period_start | `NULL` | `-400` | wd3-replace |
| Tell Maghzaliyah | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Tell Maghzaliyah | period_start | `NULL` | `-6500` | wd3-replace |
| Temple of Aphrodite, Ancient Cassope | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Temple of Aphrodite, Ancient Cassope | period_start | `NULL` | `-400` | wd3-replace |
| Temple of Apollo Patroos | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Temple of Apollo Patroos | period_start | `NULL` | `-550` | wd3-replace |
| Temple of Khonsuirdis | site_type | `NULL` | `Temple` | wd3-replace |
| Temple of Khonsuirdis | source_url | `NULL` | `https://experts.arizona.edu/en/publications/the-twenty-fifth` | wd3-replace |
| Tepeapulco Pyramid | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Tepeapulco Pyramid | period_start | `NULL` | `-100` | wd3-replace |
| Tepeapulco Pyramid | site_type | `NULL` | `Pyramid complex` | wd3-replace |
| The Street, Derbyshire | site_type | `NULL` | `Road` | wd3-replace |
| Tomb of Macridy Bey | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Tomb of Macridy Bey | period_start | `NULL` | `-300` | wd3-replace |
| Tomb of Macridy Bey | site_type | `NULL` | `Tomb` | wd3-replace |
| Tomba dei Giganti di Laccaneddu | geom | `0101000020E6100000005F629487E22040AAA88BE9F5424440` | `SRID=4326;POINT(8.43808 40.5117)` | wd3-point |
| Tomba dei Giganti di Laccaneddu | lat | `40.52312964743881` | `40.5117` | wd3-replace |
| Tomba dei Giganti di Laccaneddu | lon | `8.442440640457335` | `8.43808` | wd3-replace |
| Tomba dei Giganti di Laccaneddu | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Tomba dei Giganti di Laccaneddu | period_start | `NULL` | `-1800` | wd3-replace |
| Tomba dei Giganti di Laccaneddu | site_type | `NULL` | `Tomb` | wd3-replace |
| Tulja Buddhist Caves | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Tulja Buddhist Caves | period_start | `NULL` | `-50` | wd3-replace |
| Uchkus Inkañan | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Uchkus Inkañan | period_start | `NULL` | `-1200` | wd3-replace |
| Uchkus Inkañan | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Uskallaqta | site_type | `NULL` | `Necropolis/tombs complex` | wd3-replace |
| Vardarski Rid | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Vardarski Rid | period_start | `NULL` | `-1300` | wd3-replace |
| Villaggio Bizantino | site_type | `NULL` | `Village` | wd3-replace |
| Wamanmarka, Lima | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Wamanmarka, Lima | period_start | `NULL` | `900` | wd3-replace |
| Wamanmarka, Lima | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Washingborough | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Washingborough | period_start | `NULL` | `-1000` | wd3-replace |
| Wayna Tawqaray | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Wayna Tawqaray | period_start | `NULL` | `1400` | wd3-replace |
| Wotanstein, Hesse | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Wotanstein, Hesse | period_start | `NULL` | `-300` | wd3-replace |
| Xochicalco | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Xochicalco | period_start | `NULL` | `-200` | wd3-replace |
| Yanaque - Quilcamarca | site_type | `NULL` | `Village` | wd3-replace |
| Zennor Quoit | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Zennor Quoit | period_start | `NULL` | `-2500` | wd3-replace |
| Zona Arqueológica Chinkultic | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Zona Arqueológica Chinkultic | period_start | `NULL` | `-50` | wd3-replace |
| Züschen - Megalithic Tomb | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Züschen - Megalithic Tomb | period_start | `NULL` | `-4000` | wd3-replace |
| İssium | site_type | `NULL` | `Castle` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Pumawasi, Anta | period_start | `field-unresolved` | Wikipedia says only that the cave has pre-Columbian rock-art and was a burial ground; the Hostnig article that describes |
| Foel Dduarth - Cairn to North-East of | period_start | `field-unresolved` | The Welsh article dates the monument only to the end of the Neolithic and the start of the Bronze Age, and the scheduled |
| Yanaque - Quilcamarca | period_start | `field-unresolved` | No source dates Yanaque - Quilcamarca. The English article calls the two places legendary villages on the mountain Yanaq |
| The Street, Derbyshire | lat | `coordinates-unresolved` | No source found prints a point for The Street: Wikipedia and Wikidata give none, the Derbyshire HER gives only OS grid r |
| The Street, Derbyshire | period_start | `field-unresolved` | The Derbyshire HER gives only the period band 'Roman - 43 AD to 409 AD' and Wikipedia no construction year; the years fo |
| Babylonian Theatre | period_start | `field-unresolved` | German Wikipedia says the founding date of the theatre is not transmitted ('Das Gründungsdatum des Theaters ist nicht üb |
| Temple of Khonsuirdis | period_start | `field-unresolved` | The University of Arizona abstract only says the monument has a 'revised early Twenty-Fifth Dynasty dating', a dynasty n |
| Burley Wood | period_start | `field-unresolved` | Wikipedia calls Burley Wood (north of Lydford, Devon) an Iron Age hill fort, a period word without a year or century; th |
| Justinianopolis (Epirus) | period_start | `field-unresolved` | English Wikipedia says only that Justinian I repaired and moved the settlement, with no century or year; the Epirus (Rom |
| Ayawayq'u | period_start | `field-unresolved` | No source gives a year, century or millennium for the start of Ayawayq'u; the paintings are only classed as late or Inca |
| Currachjaghju | lat | `coordinates-unresolved` | The English and Corsican Wikipedia articles and the Wikidata item print no coordinates for Currachjaghju (Curacchiaghju, |
| Currachjaghju | period_start | `field-unresolved` | Only class-wide ranges (the Corsican Neolithic, 6000-3000 BC) and period words (Early Neolithic, Prenéolithique) were fo |
| Hellenistic House | lat | `coordinates-unresolved` | No readable page prints a point for the so-called Hellenistic House of Nea Paphos; Wikidata has no item for it and the e |
| Qaqapatan | period_start | `field-unresolved` | Neither the English Wikipedia article nor the MINCETUR-based Turismo Peruano record gives any year, century or period fo |
| Conchalito | lat | `coordinates-unresolved` | The Spanish Wikipedia article on the El Conchalito archaeological site (La Paz, Baja California Sur) prints no coordinat |
| Castle Naze | period_start | `field-unresolved` | Wikipedia, Historic England and Peak District Online give only the period word Iron Age or the class range of promontory |
| Guellayhuasin | site_type | `field-unresolved` | Only the MINCETUR record (in Spanish) calls it a ciudadela subterranea; Wikipedia says only archaeological site, so no E |
| Carisbrook Stone Arrangement | period_start | `field-unresolved` | Wikipedia and the Victorian fact sheet give no year, century or millennium for the Carisbrook arrangement's construction |
| İssium | lat | `coordinates-unresolved` | The stored Kültür Envanteri page for Issium Kalesi gives only the name, region and status, and no coordinate pair; Nomin |
| İssium | period_start | `field-unresolved` | The Kültür Envanteri entry for Issium Kalesi names no period, century or year, and no other readable source I found date |
| Nagara (Ancient city) | period_start | `field-unresolved` | No readable source gives a founding or first-occupation date for Nagara; Wikipedia's only date (2nd century CE creations |
| Bilbao | period_start | `field-unresolved` | Wikipedia says only that Bilbao was occupied since the Preclassic and that its main occupation was Late Classic (c. AD 6 |
| San Claudio | lat | `coordinates-unresolved` | German Wikipedia gives only a rounded point (17 19 N, 91 9 W) about 2 km from the stored point, too coarse to confirm or |
| Condorcaga | period_start | `field-unresolved` | The sources found give only period words: Spanish Wikipedia and the Cajamarca regional tourism page call it Chavin-influ |
| Aya Muqu | period_start | `field-unresolved` | No source found dates Aya Muqu; Wikipedia (English, Spanish, French) only gives its heritage declaration in 2003 and its |
| Nashtifan Windmills | period_start | `field-unresolved` | No source of record dates the windmills' start: the sources give only 'about 1,000 years old', a Safavid style label or  |
| Los Pinchudos | lat | `coordinates-unresolved` | No readable page prints a point for Los Pinchudos: the English, Spanish and Russian Wikipedia articles and the Wikidata  |
| Intikancha, Puno | lat | `coordinates-unresolved` | The only readable points (English Wikipedia, Wikidata) are labelled as the mountain's summit; the archaeological site is |
| Intikancha, Puno | period_start | `field-unresolved` | English and Spanish Wikipedia only say the archaeological site was declared National Cultural Heritage and give no date; |
| Pigi Athinas | lat | `coordinates-unresolved` | The English and German Wikipedia articles and the Wikidata item for Pigi Athinas carry no coordinates, and no other read |
| Uskallaqta | period_start | `field-unresolved` | The English article of the item gives no year, century or millennium for Uskallaqta and the Wikidata item states no ince |
| Juhor | period_start | `field-unresolved` | The article dates only individual finds, 'Findings from the 3rd century BC in Veliki Vetren', and places the settlement  |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s001-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s001 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
