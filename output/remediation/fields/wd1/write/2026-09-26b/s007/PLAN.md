# WD1 fields-wd1-2026-09-26b-s007: plan

Built 2026-09-30T06:01:15+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s007`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s007:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 255 |
| sites_written | 100 |
| refused | 25 |
| cells:geom | 21 |
| cells:lat | 21 |
| cells:lon | 21 |
| cells:period_name | 55 |
| cells:period_start | 55 |
| cells:site_type | 57 |
| cells:source_url | 25 |
| refused:coordinates-unresolved | 25 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acumincum | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Acumincum | period_start | `-500` | `NULL` | wd1-clear |
| Agri Bavnehøj | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Agri Bavnehøj | period_start | `-3000` | `NULL` | wd1-clear |
| Agri Bavnehøj | site_type | `Tomb` | `Barrow` | wd1-replace |
| Al-'Ula | geom | `0101000020E6100000F461946356F5424049D07111EB9D3A40` | `SRID=4326;POINT(37.92316 26.60853)` | wd1-point |
| Al-'Ula | lat | `26.616868105207946` | `26.60853` | wd1-replace |
| Al-'Ula | lon | `37.91669888253446` | `37.92316` | wd1-replace |
| Arch of Cabanes | geom | `0101000020E61000008EC839BF4E3BA73F4AD18641F8134440` | `SRID=4326;POINT(0.014722 40.165556)` | wd1-point |
| Arch of Cabanes | lat | `40.15601367075813` | `40.165556` | wd1-replace |
| Arch of Cabanes | lon | `0.045374356120093315` | `0.014722` | wd1-replace |
| Archaeological Area, Stymphalos | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Archaeological Area, Stymphalos | period_start | `-500` | `NULL` | wd1-clear |
| Archaeological Area, Stymphalos | site_type | `Temple complex` | `City` | wd1-replace |
| Athenian Treasury, Delphi | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Axum | geom | `0101000020E61000003FC4C193A15F4340C066A491FC452C40` | `SRID=4326;POINT(38.71861 14.13019)` | wd1-point |
| Axum | lat | `14.13669257289746` | `14.13019` | wd1-replace |
| Axum | lon | `38.74711844407329` | `38.71861` | wd1-replace |
| Axum | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Axum | period_start | `-500` | `1` | wd1-replace |
| Bahşeyiş Anıtı | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bahşeyiş Anıtı | period_start | `-550` | `NULL` | wd1-clear |
| Bahşeyiş Anıtı | source_url | `https://eskisehir.ktb.gov.tr/TR-157682/bahseyis-aniti-seyitg` | `https://eskisehir.ktb.gov.tr/TR-347125/bahseyis-aniti-seyitg` | wd1-replace |
| Basel-Münsterhügel | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Basel-Münsterhügel | period_start | `-500` | `-1000` | wd1-replace |
| Basel-Münsterhügel | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Beacon Hill, Burghclere, Hampshire | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Beacon Hill, Burghclere, Hampshire | period_start | `-1500` | `NULL` | wd1-clear |
| Beacon Hill, Burghclere, Hampshire | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Cave of Aurignac | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cave of Aurignac | period_start | `-500` | `NULL` | wd1-clear |
| Cetina | source_url | `https://en.wikipedia.org/wiki/Cetina` | `https://en.wikipedia.org/wiki/Cetina_culture` | wd1-replace |
| Chakdara | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Chakdara | period_start | `-3000` | `NULL` | wd1-clear |
| Chalkotheke | site_type | `Archaeological site` | `NULL` | wd1-clear |
| Chapel of Osiris | site_type | `Temple complex` | `Temple` | wd1-replace |
| Chapel of Osiris | source_url | `https://www.archaeology.org/issues/304-1807/from-the-trenche` | `https://digitalkarnak.ucsc.edu/Osiris-Heqa-Djet/` | wd1-replace |
| Cley Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cley Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Cley Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Cley Hill | source_url | `https://en.wikipedia.org/wiki/Cley_Hill` | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord` | wd1-replace |
| Cnidian Treasury | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Colima - Eastern Shaft Tomb | period_name | `1500 - 500 BC` | `1 - 500 AD` | wd1-derive-period-name |
| Colima - Eastern Shaft Tomb | period_start | `-1500` | `1` | wd1-replace |
| Colima - Eastern Shaft Tomb | site_type | `Cemetery` | `Tomb` | wd1-replace |
| Colima - Eastern Shaft Tomb | source_url | `https://en.wikipedia.org/wiki/Colima` | `https://www.megalithic.co.uk/article.php?sid=35244` | wd1-replace |
| Colybrassus Antik Kenti | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Colybrassus Antik Kenti | period_start | `-300` | `NULL` | wd1-clear |
| Coventina | site_type | `Rock relief/carving` | `Well` | wd1-replace |
| Coventina | source_url | `https://en.wikipedia.org/wiki/Coventina` | `https://keystothepast.info/search-records/results-of-search/` | wd1-replace |
| Demircili Anıt Mezarları | source_url | `https://www-kulturportali-gov-tr.translate.goog/turkiye/mers` | `https://kulturportali.gov.tr/turkiye/mersin/gezilecekyer/mbr` | wd1-replace |
| Dungur Palace (Queen of Sheba Palace) | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Dungur Palace (Queen of Sheba Palace) | period_start | `1` | `601` | wd1-replace |
| Ecclesall Woods | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Ecclesall Woods | period_start | `-3000` | `NULL` | wd1-clear |
| Ecclesall Woods | site_type | `Rock relief/carving` | `Rock art` | wd1-replace |
| Ecclesall Woods | source_url | `https://en.wikipedia.org/wiki/Ecclesall_Woods` | `https://www.megalithic.co.uk/article.php?sid=10278` | wd1-replace |
| El Caño Archaeological Park | geom | `0101000020E610000048321927472154C0407D6A03EACC2040` | `SRID=4326;POINT(-80.501056 8.394444)` | wd1-point |
| El Caño Archaeological Park | lat | `8.40022288012426` | `8.394444` | wd1-replace |
| El Caño Archaeological Park | lon | `-80.51996781788432` | `-80.501056` | wd1-replace |
| El Caño Archaeological Park | period_name | `500 BC - 1 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| El Caño Archaeological Park | period_start | `-100` | `700` | wd1-replace |
| El Pilar | geom | `0101000020E6100000C2557924ED4956C041E0F8B5DB413140` | `SRID=4326;POINT(-89.145167 17.255082)` | wd1-point |
| El Pilar | lat | `17.25725877119135` | `17.255082` | wd1-replace |
| El Pilar | lon | `-89.15509902810211` | `-89.145167` | wd1-replace |
| Esparragalejo Dam | site_type | `Megalithic structures` | `Reservoir/aqueduct/canal` | wd1-replace |
| Eva, Arcadia | geom | `0101000020E6100000B8C3105673AF364036C7F41242B54240` | `SRID=4326;POINT(22.6839 37.3786)` | wd1-point |
| Eva, Arcadia | lat | `37.41607891990718` | `37.3786` | wd1-replace |
| Eva, Arcadia | lon | `22.685353640644934` | `22.6839` | wd1-replace |
| Eva, Arcadia | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Eva, Arcadia | period_start | `-1000` | `NULL` | wd1-clear |
| Eva, Arcadia | source_url | `https://en.wikipedia.org/wiki/Eva,_Arcadia` | `https://en.wikipedia.org/wiki/Eva_(Cynuria)` | wd1-replace |
| Gamzigrad | site_type | `Castle/palace` | `Palace` | wd1-replace |
| Gilching | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Gilching | period_start | `-1500` | `NULL` | wd1-clear |
| Gilching | source_url | `https://en.wikipedia.org/wiki/Gilching` | `https://www.zeitreise-gilching.de/ortsgeschichte/bronzezeit/` | wd1-replace |
| Gochang, Hwasun and Ganghwa Dolmen Sites | geom | `0101000020E610000015E8C807CEAC5F40FCDA97797BB74140` | `SRID=4326;POINT(126.6523 35.4418)` | wd1-point |
| Gochang, Hwasun and Ganghwa Dolmen Sites | lat | `35.433455657146595` | `35.4418` | wd1-replace |
| Gochang, Hwasun and Ganghwa Dolmen Sites | lon | `126.70007509822638` | `126.6523` | wd1-replace |
| Gog Magog Hills | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Gog Magog Hills | period_start | `-4500` | `NULL` | wd1-clear |
| Gog Magog Hills | source_url | `https://en.wikipedia.org/wiki/History` | `https://en.wikipedia.org/wiki/Gog_Magog_Hills` | wd1-replace |
| Goonhilly Downs - Dry Tree Menhir | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Goonhilly Downs - Dry Tree Menhir | period_start | `-4500` | `NULL` | wd1-clear |
| Goonhilly Downs - Dry Tree Menhir | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Goonhilly Downs - Dry Tree Menhir | source_url | `https://en.wikipedia.org/wiki/Goonhilly_Downs` | `https://www.megalithic.co.uk/article.php?sid=7294` | wd1-replace |
| Hagia Photia | site_type | `Fortress/citadel` | `Fortification` | wd1-replace |
| Hazleton Long Barrows | geom | `0101000020E6100000F57EEF95772DFEBF349AC774D8ED4940` | `SRID=4326;POINT(-1.895383 51.86863)` | wd1-point |
| Hazleton Long Barrows | lat | `51.85816821809968` | `51.86863` | wd1-replace |
| Hazleton Long Barrows | lon | `-1.8861003739220312` | `-1.895383` | wd1-replace |
| Holm of Papa Chambered Cairn | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Holm of Papa Chambered Cairn | period_start | `-4500` | `NULL` | wd1-clear |
| Holm of Papa Chambered Cairn | source_url | `https://en.wikipedia.org/wiki/Holm_of_Papa` | `https://www.historicenvironment.scot/visit/all/holm-of-papa-` | wd1-replace |
| Holyhead Mountain Hut Circles | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Holyhead Mountain Hut Circles | period_start | `-2000` | `-500` | wd1-replace |
| Holyhead Mountain Hut Circles | site_type | `Residence/villa/farmhouse` | `Settlement` | wd1-replace |
| Huamboy | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Huamboy | period_start | `-200` | `NULL` | wd1-clear |
| Huamboy | site_type | `Necropolis/tombs complex` | `Cemetery` | wd1-replace |
| Huckhoe Settlement | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Hunter's Tor, Lustleigh Cleave | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Hunter's Tor, Lustleigh Cleave | period_start | `-1000` | `NULL` | wd1-clear |
| Hunter's Tor, Lustleigh Cleave | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Icknield Way | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Icknield Way | period_start | `-4000` | `NULL` | wd1-clear |
| Intihuatana, Urubamba | geom | `0101000020E6100000056627C239F251C0C513FEEC55232BC0` | `SRID=4326;POINT(-72.545683 -13.163075)` | wd1-point |
| Intihuatana, Urubamba | lat | `-13.569014936461722` | `-13.163075` | wd1-replace |
| Intihuatana, Urubamba | lon | `-71.78477529380332` | `-72.545683` | wd1-replace |
| Intihuatana, Urubamba | site_type | `Megalithic stones` | `Sculptured stone` | wd1-replace |
| Isca Dumnoniorum | site_type | `Fortress/citadel` | `Town` | wd1-replace |
| Karchaghbyur | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Karchaghbyur | period_start | `-500` | `NULL` | wd1-clear |
| Kourion | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Kourion | period_start | `-3000` | `-1050` | wd1-replace |
| Ksaverove | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ksaverove | period_start | `-4500` | `NULL` | wd1-clear |
| Ksaverove | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Ksaverove | source_url | `https://en.wikipedia.org/wiki/Ksaverove` | `NULL` | wd1-clear |
| La Ferté-en-Ouche | geom | `0101000020E61000003742D028765BE03F27C1CB3AAD6B4840` | `SRID=4326;POINT(0.497389 48.839567)` | wd1-point |
| La Ferté-en-Ouche | lat | `48.841224050035` | `48.839567` | wd1-replace |
| La Ferté-en-Ouche | lon | `0.5111647412432551` | `0.497389` | wd1-replace |
| La Ferté-en-Ouche | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| La Ferté-en-Ouche | period_start | `-4500` | `NULL` | wd1-clear |
| La Ferté-en-Ouche | site_type | `Megalithic stones` | `Dolmen` | wd1-replace |
| La Ferté-en-Ouche | source_url | `https://en.wikipedia.org/wiki/La_Fert%C3%A9-en-Ouche` | `https://fr.wikipedia.org/wiki/Pierre_Coupl%C3%A9e` | wd1-replace |
| La basilique Sainte-Crispine | site_type | `Temple complex` | `Church` | wd1-replace |
| Lalibela | period_name | `500 BC - 1 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Lalibela | period_start | `-500` | `1181` | wd1-replace |
| Lalibela | site_type | `Temple complex` | `Church` | wd1-replace |
| Lalibela | source_url | `https://en.wikipedia.org/wiki/Lalibela` | `https://en.wikipedia.org/wiki/Rock-Hewn_Churches,_Lalibela` | wd1-replace |
| Little Woodbury | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Little Woodbury | period_start | `-1500` | `NULL` | wd1-clear |
| Little Woodbury | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Llyn Cerrig Bach | site_type | `Archaeological site` | `Sacred site` | wd1-replace |
| Long Wood Enclosure | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Long Wood Enclosure | period_start | `-1500` | `NULL` | wd1-clear |
| Louisville | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Louisville | period_start | `-500` | `NULL` | wd1-clear |
| Louisville | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Louisville | source_url | `https://en.wikipedia.org/wiki/Louisville,_Belize` | `NULL` | wd1-clear |
| Macellum of Pozzuoli | site_type | `City/town/settlement` | `Monument` | wd1-replace |
| Magh Slécht | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Magh Slécht | period_start | `-4000` | `NULL` | wd1-clear |
| Magh Slécht | site_type | `Megalithic structures` | `Sacred site` | wd1-replace |
| Mamshit National Park | site_type | `Settlement` | `City` | wd1-replace |
| Manmodi Caves | geom | `0101000020E61000008B4DA984F67752407A742205A3343340` | `SRID=4326;POINT(73.8843 19.1859)` | wd1-point |
| Manmodi Caves | lat | `19.205612488662588` | `19.1859` | wd1-replace |
| Manmodi Caves | lon | `73.87442127736556` | `73.8843` | wd1-replace |
| Manmodi Caves | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Manmodi Caves | period_start | `-500` | `110` | wd1-replace |
| Menir da Cabeça do Rochedo | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Menir da Cabeça do Rochedo | period_start | `-4000` | `NULL` | wd1-clear |
| Minar-i Chakri | site_type | `Sculptured stone` | `Minaret/tower` | wd1-replace |
| Mormont | site_type | `Necropolis/tombs complex` | `Sanctuary` | wd1-replace |
| Mormont | source_url | `https://en.wikipedia.org/wiki/Mormont` | `https://fr.wikipedia.org/wiki/Mormont_(site_arch%C3%A9ologiq` | wd1-replace |
| Mount Thourion | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Mount Thourion | period_start | `-2000` | `-86` | wd1-replace |
| Mount Thourion | site_type | `Temple complex` | `Monument` | wd1-replace |
| Mughal Minar | geom | `0101000020E6100000D1EE1AEDC1935240DA9E36D6F6F54140` | `SRID=4326;POINT(74.339239 35.900795)` | wd1-point |
| Mughal Minar | lat | `35.92159536044137` | `35.900795` | wd1-replace |
| Mughal Minar | lon | `74.3087113154427` | `74.339239` | wd1-replace |
| Mughal Minar | period_name | `1 - 500 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Mughal Minar | period_start | `1` | `1320` | wd1-replace |
| Mughal Minar | site_type | `Temple complex` | `Minaret/tower` | wd1-replace |
| Myriv | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Naples Subterranean Structures | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Naples Subterranean Structures | period_start | `-1500` | `-300` | wd1-replace |
| Negrine | geom | `0101000020E6100000C616CD1BFD1B1E40A81CD1DA0E4C4140` | `SRID=4326;POINT(7.5205 34.4857)` | wd1-point |
| Negrine | lat | `34.59420333109421` | `34.4857` | wd1-replace |
| Negrine | lon | `7.527332720177304` | `7.5205` | wd1-replace |
| Negrine | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Negrine | period_start | `-500` | `104` | wd1-replace |
| Nesebar | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Nesebar | period_start | `-2000` | `-1000` | wd1-replace |
| North Bersted Man | site_type | `Museum` | `Burial` | wd1-replace |
| Obelisk of Axum | site_type | `Megalithic structures` | `Standing stone` | wd1-replace |
| Oldendorfer Totenstatt | site_type | `Mound/tumulus` | `Cemetery` | wd1-replace |
| Paos | geom | `0101000020E610000072781D3FBFFB354057C99D3DD1EC4240` | `SRID=4326;POINT(21.985 37.841)` | wd1-point |
| Paos | lat | `37.850135519069845` | `37.841` | wd1-replace |
| Paos | lon | `21.98338694066519` | `21.985` | wd1-replace |
| Parion | site_type | `Necropolis/tombs complex` | `City` | wd1-replace |
| Porte Noire | geom | `0101000020E61000001BAD13417514184006A75523BC9E4740` | `SRID=4326;POINT(6.0302 47.234131)` | wd1-point |
| Porte Noire | lat | `47.24011651689766` | `47.234131` | wd1-replace |
| Porte Noire | lon | `6.019978539300861` | `6.0302` | wd1-replace |
| Priene Ruins | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Priene Ruins | period_start | `1` | `-350` | wd1-replace |
| Priene Ruins | site_type | `Temple complex` | `City` | wd1-replace |
| Prinias | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Prinias | period_start | `-2000` | `-1200` | wd1-replace |
| Prinias | site_type | `Temple complex` | `Settlement` | wd1-replace |
| Prosymna | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Prosymna | period_start | `-4000` | `NULL` | wd1-clear |
| Puntay Urqu | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Puntay Urqu | period_start | `1400` | `NULL` | wd1-clear |
| Puntay Urqu | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Pyramid of Amenemhat III at Hawara | source_url | `https://en.wikipedia.org/wiki/Hawara` | `https://de.wikipedia.org/wiki/Hawara-Pyramide` | wd1-replace |
| Qalagah | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Qalagah | period_start | `1` | `NULL` | wd1-clear |
| Qohaito | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Qohaito | period_start | `1` | `NULL` | wd1-clear |
| Quispiguanca | geom | `0101000020E61000005B4AA06A200452C00601371C4F5C2AC0` | `SRID=4326;POINT(-72.112173 -13.301367)` | wd1-point |
| Quispiguanca | lat | `-13.180291063036304` | `-13.301367` | wd1-replace |
| Quispiguanca | lon | `-72.0644785466515` | `-72.112173` | wd1-replace |
| Quispiguanca | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Quispiguanca | period_start | `1000` | `NULL` | wd1-clear |
| Rapidum | geom | `0101000020E610000036ADCF8EDB770B405572E25213114240` | `SRID=4326;POINT(3.421825 36.136435)` | wd1-point |
| Rapidum | lat | `36.13340221459354` | `36.136435` | wd1-replace |
| Rapidum | lon | `3.4335242421272154` | `3.421825` | wd1-replace |
| Rapidum | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Rocha dos Namorados | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Rocha dos Namorados | period_start | `-4000` | `NULL` | wd1-clear |
| Ruins of Hippo (Hippo Regius) | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Ruins of Hippo (Hippo Regius) | period_start | `-3000` | `-500` | wd1-replace |
| Ruins of Hippo (Hippo Regius) | site_type | `Temple complex` | `City` | wd1-replace |
| Saar Temple | site_type | `Temple complex` | `Temple` | wd1-replace |
| Saar Temple | source_url | `https://en.wikipedia.org/wiki/Sar,_Bahrain` | `https://journals.uclpress.co.uk/ai/article/280/galley/12429/` | wd1-replace |
| San Bartolo | geom | `0101000020E61000005FD9419018DD56C016AE9B6DCC2A2E40` | `SRID=4326;POINT(-89.40389 17.54833)` | wd1-point |
| San Bartolo | lat | `15.083590913061055` | `17.54833` | wd1-replace |
| San Bartolo | lon | `-91.45462423735215` | `-89.40389` | wd1-replace |
| Shewaki Stupa | site_type | `Temple complex` | `Religious` | wd1-replace |
| Shewaki Stupa | source_url | `https://en.wikipedia.org/wiki/Shewaki` | `https://www.achco.org.af/project/Shewaki` | wd1-replace |
| Shukhuti Mosaic | site_type | `Residence/villa/farmhouse` | `Bath` | wd1-replace |
| Sidrón Cave | site_type | `Megalithic structures` | `Cave` | wd1-replace |
| Sotin | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Sotin | period_start | `-500` | `NULL` | wd1-clear |
| South Stoa I, Athens | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Tan Hill, Wiltshire | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Tan Hill, Wiltshire | period_start | `-1500` | `NULL` | wd1-clear |
| Tan Hill, Wiltshire | source_url | `https://en.wikipedia.org/wiki/Tan_Hill%2C_Wiltshire` | `https://www.wiltshirewhitehorses.org.uk/tanhill.html` | wd1-replace |
| Tegea | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Tegea | period_start | `-500` | `-1320` | wd1-replace |
| Temple of Amun | source_url | `https://en.wikipedia.org/wiki/Mortuary_temple` | `https://en.wikipedia.org/wiki/Precinct_of_Amun-Re` | wd1-replace |
| Teysheba | geom | `0101000020E61000001624842BD8BA4640B05FE5D481154440` | `SRID=4326;POINT(45.4953 40.1528)` | wd1-point |
| Teysheba | lat | `40.168024646758` | `40.1528` | wd1-replace |
| Teysheba | lon | `45.45972198440738` | `45.4953` | wd1-replace |
| The Giant Tumulus, Großmugl | geom | `0101000020E61000008029F8E3FD3F3040FF3C545326424840` | `SRID=4326;POINT(16.22312 48.48833)` | wd1-point |
| The Giant Tumulus, Großmugl | lat | `48.51679460156628` | `48.48833` | wd1-replace |
| The Giant Tumulus, Großmugl | lon | `16.24996781166692` | `16.22312` | wd1-replace |
| The Giant Tumulus, Großmugl | site_type | `Necropolis/tombs complex` | `Mound/tumulus` | wd1-replace |
| The Giant Tumulus, Großmugl | source_url | `https://en.wikipedia.org/wiki/Gro%C3%9Fmugl` | `https://de.wikipedia.org/wiki/Leeberg_(Gro%C3%9Fmugl)` | wd1-replace |
| The Gop | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| The Gop | period_start | `-5000` | `NULL` | wd1-clear |
| The Gop | site_type | `Fortress/citadel` | `Cairn` | wd1-replace |
| Troldkirken | site_type | `Necropolis/tombs complex` | `Barrow` | wd1-replace |
| Tønnesminde | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Vatin Circles | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Vatin Circles | period_start | `-5000` | `NULL` | wd1-clear |
| Vatin Circles | site_type | `Geoglyphs` | `Earthwork` | wd1-replace |
| Walbury Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Walbury Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Walbury Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Walbury Hill | source_url | `https://en.wikipedia.org/wiki/Walbury_Hill` | `https://www.megalithic.co.uk/article.php?sid=4529` | wd1-replace |
| Yarim Tepe | geom | `0101000020E6100000AB4EA37F012D4540CFC6A73058274240` | `SRID=4326;POINT(42.3675 36.32045)` | wd1-point |
| Yarim Tepe | lat | `36.307378847047964` | `36.32045` | wd1-replace |
| Yarim Tepe | lon | `42.351608233203784` | `42.3675` | wd1-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Long Wood Enclosure | lat | `coordinates-unresolved` | Only one source family prints the true point in a readable form: Wikidata gives 51°9'12.960"N, 3°27'28.908"W (NHLE-refer |
| Mormont | lat | `coordinates-unresolved` | Only the Wikipedia family (the French site article and its Wikidata item, 46°39'0"N 6°32'13"E) prints a point for the ar |
| Qohaito | lat | `coordinates-unresolved` | Only the Wikipedia family prints a point for the ruins (14.86611, 39.42389, about 1.4 km south of the stored point); Ple |
| Shewaki Stupa | lat | `coordinates-unresolved` | The stored point is the centre of Shewaki village, about 6 km west of the stupa. The stupa's own point is given only by  |
| Magh Slécht | lat | `coordinates-unresolved` | Magh Slécht is a historic plain of about 8 km2 in Templeport parish holding over 80 monuments; only Wikipedia and its Wi |
| Puntay Urqu | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point (13°45′59″S 73°48′08″W, 0.15 km from the stored point); the MINCETUR i |
| Naples Subterranean Structures | lat | `coordinates-unresolved` | The entry is the whole underground geothermal zone and tunnel network beneath Naples, running from Vesuvius through Pomp |
| Bahşeyiş Anıtı | lat | `coordinates-unresolved` | The only printed point for the Bahşeyiş monument is the Wikidata item Q134728456 (39°9'11.05"N, 30°34'30.68"E, about 70  |
| Icknield Way | lat | `coordinates-unresolved` | The Icknield Way is a braided trackway 'from Norfolk to Wiltshire' (Wikipedia); the stored point is Lyme Regis in Dorset |
| Tønnesminde | lat | `coordinates-unresolved` | Only the Wikipedia family (the English article's infobox, 55.81003389, 10.62370472, about 13 m from the stored point, an |
| Gilching | lat | `coordinates-unresolved` | The entry names the municipality of Gilching and its stored point is the town centre (the municipality's article coordin |
| Cetina | lat | `coordinates-unresolved` | The entry is the Early Bronze Age mound fields of the Cetina culture, which the sources place at several locations along |
| La basilique Sainte-Crispine | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://vici.org/vici/22810/; quote not found: https://vici.org/vici/228 |
| Cnidian Treasury | lat | `coordinates-unresolved` | Only Wikidata (38.481899, 22.50154, the same family as the Wikipedia article) prints a point for the Cnidian Treasury in |
| Prosymna | lat | `coordinates-unresolved` | Pleiades lists Prosymna as unlocated (Barrington Atlas 'unlocated'), ToposText gives 37.68, 22.78 only with 'Confidence: |
| Minar-i Chakri | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://vici.org/vici/90583/; quote not found: https://vici.org/vici/905 |
| Louisville | lat | `coordinates-unresolved` | Only Wikipedia gives a readable point (18°19′N 88°30′W, for the village, within 0.1 km of the stored point); the excavat |
| Colima - Eastern Shaft Tomb | lat | `coordinates-unresolved` | The site is the pre-Hispanic cemetery with a shaft tomb that INAH excavated in 2013 'al oriente de la ciudad de Colima'. |
| North Bersted Man | lat | `coordinates-unresolved` | The site is the 2008 warrior grave at Bersted Park, North Bersted near Bognor Regis; the stored point lies in Chichester |
| Shukhuti Mosaic | lat | `coordinates-unresolved` | The only coordinates published for the find site are English Wikipedia's and Wikidata's 42°05′N 42°05′E, which are the r |
| Tan Hill, Wiltshire | lat | `coordinates-unresolved` | The site is the lost Tan Hill white horse (the 'Tan Hill Donkey'), not the hill. Wiltshire White Horses and the Hillfigu |
| Huamboy | lat | `coordinates-unresolved` | The MINCETUR inventory record (as reproduced by turismoperuano.com) gives the complex as UTM 8 181 271 N / 763 804 E at  |
| Chapel of Osiris | lat | `coordinates-unresolved` | The stored point lies about 10 m from the Chapel of Osiris Heqadjet in East Karnak (Wikidata Q124824888 gives 25.71785,  |
| Karchaghbyur | lat | `coordinates-unresolved` | The Wikidata/Wikipedia point (40.16389, 45.57222) and GeoNames' points are the village of Karchaghbyur and its stream, n |
| Ksaverove | lat | `coordinates-unresolved` | No source prints a point for a Trypillia settlement at Ksaverove: the only pages that mention one are copies of an Engli |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s007-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s007 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
