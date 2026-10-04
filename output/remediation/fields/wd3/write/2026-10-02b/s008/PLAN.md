# WD3 fields-wd3-2026-10-02b-s008: plan

Built 2026-10-04T12:49:26+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s008`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s008:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 200 |
| sites_written | 100 |
| refused | 40 |
| cells:geom | 9 |
| cells:lat | 9 |
| cells:lon | 9 |
| cells:period_name | 69 |
| cells:period_start | 69 |
| cells:site_type | 32 |
| cells:source_url | 3 |
| refused:coordinates-unresolved | 14 |
| refused:field-unresolved | 26 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acropolis of Athens | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Acropolis of Athens | period_start | `NULL` | `-4000` | wd3-replace |
| Al Sanea Tomb | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Al Sanea Tomb | period_start | `NULL` | `8` | wd3-replace |
| Alauna, Maryport | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Alauna, Maryport | period_start | `NULL` | `1` | wd3-replace |
| Alconétar Bridge | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Alconétar Bridge | period_start | `NULL` | `101` | wd3-replace |
| Amnisos | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Amnisos | period_start | `NULL` | `-1900` | wd3-replace |
| Ancon Archaeological Site | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Ancon Archaeological Site | period_start | `NULL` | `-8000` | wd3-replace |
| Anta do Paço da Vinha | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Anta do Paço da Vinha | period_start | `NULL` | `-3500` | wd3-replace |
| Aqueduc Romain | site_type | `NULL` | `Aqueduct` | wd3-replace |
| Ashdown Forest | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Axura Nekropolises | site_type | `NULL` | `Necropolis` | wd3-replace |
| Aylesbury | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Aylesbury | period_start | `NULL` | `-400` | wd3-replace |
| Balamkú | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Balamkú | period_start | `NULL` | `-300` | wd3-replace |
| Bejucal | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Ca n'Oliver Iberian Settlement and Museum | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Ca n'Oliver Iberian Settlement and Museum | period_start | `NULL` | `-700` | wd3-replace |
| Casteddu di Tappa | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Casteddu di Tappa | period_start | `NULL` | `-2200` | wd3-replace |
| Castell Cawr | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Castell Cawr | period_start | `NULL` | `-800` | wd3-replace |
| Castle Old Fort | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Castle Old Fort | period_start | `NULL` | `-500` | wd3-replace |
| Castra ad Montanesium | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Castra ad Montanesium | period_start | `NULL` | `1` | wd3-replace |
| Catacombs of Saint Gaudiosus | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Catacombs of Saint Gaudiosus | period_start | `NULL` | `301` | wd3-replace |
| Chacmultun | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Chacmultun | period_start | `NULL` | `300` | wd3-replace |
| Chalcatzingo | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Chalcatzingo | period_start | `NULL` | `-1500` | wd3-replace |
| Corbridge Lion | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Corbridge Lion | period_start | `NULL` | `101` | wd3-replace |
| Corick | site_type | `NULL` | `Stone circle` | wd3-replace |
| Cotzumalhuapa | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Cras -  Round Cairn to North of | site_type | `NULL` | `Cairn` | wd3-replace |
| Cras -  Round Cairn to North of | source_url | `NULL` | `https://cy.wikipedia.org/wiki/Carneddau_crynion_Cras_(Aber)` | wd3-replace |
| Danish Camp | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Danish Camp | period_start | `NULL` | `-400` | wd3-replace |
| Dolno Gradište | site_type | `NULL` | `Fortification` | wd3-replace |
| Drachenhöhle | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Drachenhöhle | period_start | `NULL` | `-65000` | wd3-replace |
| El Temblor | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| El Temblor | period_start | `NULL` | `600` | wd3-replace |
| El Temblor | site_type | `NULL` | `Settlement` | wd3-replace |
| El Zotz | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| El Zotz | period_start | `NULL` | `-400` | wd3-replace |
| El Zotz | site_type | `NULL` | `City` | wd3-replace |
| Ex voto of the Attalids, Delphi | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Ex voto of the Attalids, Delphi | period_start | `NULL` | `-241` | wd3-replace |
| Ex voto(s) of the Argives, Delphi | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Ex voto(s) of the Argives, Delphi | period_start | `NULL` | `-369` | wd3-replace |
| Ferrybridge Henge | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Ferrybridge Henge | period_start | `NULL` | `-3000` | wd3-replace |
| Frilford | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Frilford | period_start | `NULL` | `-350` | wd3-replace |
| Grapčeva Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Grapčeva Cave | period_start | `NULL` | `-6000` | wd3-replace |
| Haidara - Temple of Sun | site_type | `NULL` | `Funerary` | wd3-replace |
| Hengistbury Head | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Hengistbury Head | period_start | `NULL` | `-10000` | wd3-replace |
| Heroon at Nemea | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Heroon at Nemea | period_start | `NULL` | `-600` | wd3-replace |
| Inti Watana, Calca | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Inti Watana, Calca | period_start | `NULL` | `1440` | wd3-replace |
| Ixtutz | geom | `0101000020E61000002AD8B12CA15A56C06B21823EE1833040` | `SRID=4326;POINT(-89.47832 16.47296)` | wd3-point |
| Ixtutz | lat | `16.515155703325416` | `16.47296` | wd3-replace |
| Ixtutz | lon | `-89.41608731620423` | `-89.47832` | wd3-replace |
| Kalakača Archaeological Site, Beška | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Kalakača Archaeological Site, Beška | period_start | `NULL` | `-900` | wd3-replace |
| Karasis Kalesi | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Karasis Kalesi | period_start | `NULL` | `-200` | wd3-replace |
| Karasis Kalesi | site_type | `NULL` | `Castle` | wd3-replace |
| Kerbatch | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Kerbatch | period_start | `NULL` | `-300` | wd3-replace |
| Kirkby Thore | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Kirkby Thore | period_start | `NULL` | `69` | wd3-replace |
| Kutlug-Tepe | geom | `0101000020E61000004B85287A87B95040D8A938191E614240` | `SRID=4326;POINT(66.716667 37.083333)` | wd3-point |
| Kutlug-Tepe | lat | `36.758731033961965` | `37.083333` | wd3-replace |
| Kutlug-Tepe | lon | `66.89889387089822` | `66.716667` | wd3-replace |
| Kutlug-Tepe | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Kutlug-Tepe | period_start | `NULL` | `-1000` | wd3-replace |
| Kutlug-Tepe | site_type | `NULL` | `Fortification` | wd3-replace |
| La Chabola de la Hechicera | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| La Chabola de la Hechicera | period_start | `NULL` | `-2000` | wd3-replace |
| Lancken - Granitz Dolmens | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Lancken - Granitz Dolmens | period_start | `NULL` | `-3500` | wd3-replace |
| Lesche of the Knidians | site_type | `NULL` | `Monument` | wd3-replace |
| Mar Gerges Blue Yanouh | source_url | `NULL` | `https://en.wikipedia.org/wiki/Sanctuary_of_Yanouh` | wd3-replace |
| Marcahuamachuco | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Miseno | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Miseno | period_start | `NULL` | `-400` | wd3-replace |
| Mojeque | site_type | `NULL` | `Temple` | wd3-replace |
| Nina Kiru | site_type | `NULL` | `Tomb` | wd3-replace |
| Nitriansky Hrádok | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Nitriansky Hrádok | period_start | `NULL` | `-4800` | wd3-replace |
| Nordtor Hierapolis | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Nordtor Hierapolis | period_start | `NULL` | `82` | wd3-replace |
| Pajaral | geom | `0101000020E61000008017D454A57956C081E016A718E73040` | `SRID=4326;POINT(-90.44553 17.13015)` | wd3-point |
| Pajaral | lat | `16.902719920239637` | `17.13015` | wd3-replace |
| Pajaral | lon | `-89.90071602546777` | `-90.44553` | wd3-replace |
| Pajaral | site_type | `NULL` | `City` | wd3-replace |
| Pampas Gramalote | geom | `0101000020E610000055AA9C15BCDB53C006D1A56A9DCC1EC0` | `SRID=4326;POINT(-79.108124 -8.100001)` | wd3-point |
| Pampas Gramalote | lat | `-7.69981924664558` | `-8.100001` | wd3-replace |
| Pampas Gramalote | lon | `-79.43335476207115` | `-79.108124` | wd3-replace |
| Paradeisos Archaeological Site | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Paradeisos Archaeological Site | period_start | `NULL` | `-5000` | wd3-replace |
| Pautalia | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Pautalia | period_start | `NULL` | `-500` | wd3-replace |
| Petroglyph Provincial Park | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Petroglyph Provincial Park | period_start | `NULL` | `901` | wd3-replace |
| Petroglyphs of Arpa-Uzen | geom | `0101000020E61000004C1369D5C57E51402D0B74540C724540` | `SRID=4326;POINT(68.833333 43.833333)` | wd3-point |
| Petroglyphs of Arpa-Uzen | lat | `42.89100127855486` | `43.833333` | wd3-replace |
| Petroglyphs of Arpa-Uzen | lon | `69.98082480679767` | `68.833333` | wd3-replace |
| Petroglyphs of Arpa-Uzen | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Petroglyphs of Arpa-Uzen | period_start | `NULL` | `-2000` | wd3-replace |
| Pilgrims' Way | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Pilgrims' Way | period_start | `NULL` | `-600` | wd3-replace |
| Pisissarfik | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Pisissarfik | period_start | `NULL` | `1501` | wd3-replace |
| Port Way | geom | `0101000020E610000026E8CDEDD39DF1BFFBD5504633AD4940` | `SRID=4326;POINT(-1.63378 51.17003)` | wd3-point |
| Port Way | lat | `51.353127278776775` | `51.17003` | wd3-replace |
| Port Way | lon | `-1.1010321892959012` | `-1.63378` | wd3-replace |
| Qasr Naous Roman Temples | site_type | `NULL` | `Temple complex` | wd3-replace |
| Qulu Qulu | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Qulu Qulu | period_start | `NULL` | `1300` | wd3-replace |
| Qulu Qulu | site_type | `NULL` | `Funerary` | wd3-replace |
| Roman Road from Silchester to Bath | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Roman Road from Silchester to Bath | period_start | `NULL` | `1` | wd3-replace |
| Runayoc | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Sadarak | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Sadarak | period_start | `NULL` | `-4000` | wd3-replace |
| Sagaholm | geom | `0101000020E6100000EDB1FB5739342C403DF77F55EFB84C40` | `SRID=4326;POINT(14.172222 57.746389)` | wd3-point |
| Sagaholm | lat | `57.444803893550194` | `57.746389` | wd3-replace |
| Sagaholm | lon | `14.101999997591486` | `14.172222` | wd3-replace |
| Samothrace Temple Complex | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Samothrace Temple Complex | period_start | `NULL` | `-700` | wd3-replace |
| Shahhat | geom | `0101000020E6100000A1BA2D48CBDC354070DEECE322674040` | `SRID=4326;POINT(21.862222 32.827778)` | wd3-point |
| Shahhat | lat | `32.80575226846565` | `32.827778` | wd3-replace |
| Shahhat | lon | `21.86247683636123` | `21.862222` | wd3-replace |
| Snowden Crags | site_type | `NULL` | `Stone circle` | wd3-replace |
| Sofia | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Sofia | period_start | `NULL` | `-7000` | wd3-replace |
| Southwest Temple of the Ancient Agora of Athens | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Southwest Temple of the Ancient Agora of Athens | period_start | `NULL` | `1` | wd3-replace |
| Soğmatar | site_type | `NULL` | `Ruin` | wd3-replace |
| Spinsters' Rock | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Spinsters' Rock | period_start | `NULL` | `-3500` | wd3-replace |
| Tal-Barrani | site_type | `NULL` | `Necropolis/tombs complex` | wd3-replace |
| Tempio Nuragico a Pozzo di Irru | site_type | `NULL` | `Temple` | wd3-replace |
| Temple E, Selinus | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Temple E, Selinus | period_start | `NULL` | `-450` | wd3-replace |
| Termessos Kurucu'nun Evi | site_type | `NULL` | `Villa` | wd3-replace |
| Tombeau de Merlin | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Tombeau de Merlin | period_start | `NULL` | `-4000` | wd3-replace |
| Totternhoe Roman Villa | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Totternhoe Roman Villa | period_start | `NULL` | `301` | wd3-replace |
| Trebenna Antike Stadt | site_type | `NULL` | `City` | wd3-replace |
| Tres Islas | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Tres Islas | period_start | `NULL` | `-400` | wd3-replace |
| Tres Islas | site_type | `NULL` | `City` | wd3-replace |
| Tubuco | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Tubuco | period_start | `NULL` | `-1200` | wd3-replace |
| Tulum | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Tulum | period_start | `NULL` | `501` | wd3-replace |
| Uxbenka | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Uxbenka | period_start | `NULL` | `250` | wd3-replace |
| Uzun oba | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Uzun oba | period_start | `NULL` | `-5000` | wd3-replace |
| Uzun oba | site_type | `NULL` | `Settlement` | wd3-replace |
| Venado Beach | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Venado Beach | period_start | `NULL` | `550` | wd3-replace |
| Venta Belgarum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Venta Belgarum | period_start | `NULL` | `70` | wd3-replace |
| Via degli Inferi - Necropoli Banditaccia | source_url | `NULL` | `https://www.etruskey.it/en/itinerary/the-via-degli-inferi-an` | wd3-replace |
| Wajxaklajun | geom | `0101000020E6100000330EAEA473DE56C05FCD70081CA12E40` | `SRID=4326;POINT(-91.473953 15.828731)` | wd3-point |
| Wajxaklajun | lat | `15.314666999597362` | `15.828731` | wd3-replace |
| Wajxaklajun | lon | `-91.4758083057175` | `-91.473953` | wd3-replace |
| Wajxaklajun | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Wajxaklajun | period_start | `NULL` | `250` | wd3-replace |
| Wichqana | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Wichqana | period_start | `NULL` | `-1200` | wd3-replace |
| Wilcahuaín | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Wilcahuaín | period_start | `NULL` | `1100` | wd3-replace |
| Xerez Cromlech | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Xerez Cromlech | period_start | `NULL` | `-4000` | wd3-replace |
| Yanaca | site_type | `NULL` | `City/town/settlement` | wd3-replace |
| Yemshi Tepe | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Yemshi Tepe | period_start | `NULL` | `-500` | wd3-replace |
| Yemshi Tepe | site_type | `NULL` | `City/town/settlement` | wd3-replace |
| Ñawpallaqta, Lucanas | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Ħal Ġinwi Temple | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Ħal Ġinwi Temple | period_start | `NULL` | `-3600` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Soğmatar | period_start | `field-unresolved` | No source dates the start of Sogmatar as a site. English Wikipedia only reports that a series of Syriac inscriptions dat |
| Axura Nekropolises | lat | `coordinates-unresolved` | No page found prints a point for the Axura necropolises themselves: the Wikipedia articles (en, az, tr) and Wikidata car |
| Axura Nekropolises | period_start | `field-unresolved` | The Wikipedia article dates the three necropolises inconsistently (end of the Iron Age, the III-VIII centuries, the firs |
| Nordtor Hierapolis | lat | `coordinates-unresolved` | The cultural inventory page for the Hierapolis Frontinus gate describes the monument in prose and gives its date, but pr |
| Yanaca | period_start | `field-unresolved` | No source dates the start of Yanaca. The English article says it is extremely difficult to know when the first inhabitan |
| Port Way | period_start | `field-unresolved` | Wikipedia only says the road is often associated with the Roman Empire and may have predated the Roman occupation; no so |
| Aqueduc Romain | lat | `coordinates-unresolved` | No readable source prints a point for the Roman aqueduct of Constantine: its Wikidata item Q122114787 and Commons catego |
| Aqueduc Romain | period_start | `field-unresolved` | No readable source gives a year or century for the start of this aqueduct; Harba-DZ calls it only antique, Wikipedia onl |
| Trebenna Antike Stadt | period_start | `field-unresolved` | The article says the name is first mentioned on a milestone of 45/46 AD and the Antalya culture directorate states that  |
| Pajaral | period_start | `field-unresolved` | Sources only give period words (Early Classic stela, Classic kingdom of Hixwitz, 7th century eclipse by Zapote Bobal), n |
| Corick | period_start | `field-unresolved` | Wikipedia gives no date for the Corick stone circle and row; no readable source dates the site's start. |
| Via degli Inferi - Necropoli Banditaccia | lat | `coordinates-unresolved` | No readable page prints a point for the Via degli Inferi itself: Wikipedia has no article, Commons/Wikidata have no item |
| Via degli Inferi - Necropoli Banditaccia | period_start | `field-unresolved` | Readable pages only date tombs and road works along the road (tumuli from the 6th century BC on the main sepulchral road |
| Tubuco | lat | `coordinates-unresolved` | The site is Tabuco (Tubuco), the pre-Hispanic Tuxpan on the right bank of the Tuxpan river mouth, Veracruz; no readable  |
| Tubuco | site_type | `field-unresolved` | Spanish sources call Tabuco a small ceremonial centre and the first settlement of Tuxpan, but no readable source gives a |
| Tempio Nuragico a Pozzo di Irru | period_start | `field-unresolved` | The pages on the Irru complex (La Sardegna verso l'Unesco, Wikipedia on Nulvi, the list of Nuragic holy wells) describe  |
| Runayoc | lat | `coordinates-unresolved` | Neither Wikipedia (en, pt) nor its Wikidata item gives coordinates, and the Ministry of Culture resolution of 2025 only  |
| Runayoc | period_start | `field-unresolved` | Wikipedia and the MINCETUR inventory entry give no date for Runayoc; the resolution of 2025 concerns protection, not dat |
| Karasis Kalesi | lat | `coordinates-unresolved` | The German Wikipedia article on the Karasis fortress prints its coordinates only in German notation (37°33'8" N, 35°51'5 |
| Cras -  Round Cairn to North of | period_start | `field-unresolved` | The register and the Welsh article about this cairn place it after the end of the Stone Age and at the beginning of the  |
| Tal-Barrani | period_start | `field-unresolved` | English Wikipedia dates only the 16th-17th century documents about the estate and says the Punic tombs and Late Roman-By |
| Venado Beach | lat | `coordinates-unresolved` | Neither Wikipedia nor Wikidata gives a point for Venado Beach (Playa Venado, near the Venado River mouth, Pacific coast  |
| Ixtutz | period_start | `field-unresolved` | Wikipedia and the excavation reports (Chaluleu 2019, Reyes et al. 2019) date the first occupation only as Late Preclassi |
| Al Sanea Tomb | lat | `coordinates-unresolved` | No source I could read prints a point for the Al-Sanea tomb itself. The Arabic Wikipedia article that served as the stor |
| Nina Kiru | lat | `coordinates-unresolved` | No readable source prints a point for Nina Kiru/Ninaquero; Wikipedia and Wikidata give none, the MINCETUR record gives n |
| Nina Kiru | period_start | `field-unresolved` | MINCETUR assigns the mausoleum only to the Late Horizon (Inca) period, a period word without a year or century; no sourc |
| Dolno Gradište | period_start | `field-unresolved` | English and Macedonian Wikipedia and the E-Tour Guide page only give a period word (late antiquity) and the general impo |
| Bejucal | lat | `coordinates-unresolved` | The only printed points (Wikipedia/Wikidata 17.42, -89.67) lie about 38 km from the stored point and do not fit the arti |
| Bejucal | period_start | `field-unresolved` | Wikipedia dates the site to the second half of the 4th century AD, but the excavators (Garrison et al. 2016) place its e |
| Cotzumalhuapa | period_start | `field-unresolved` | The English Wikipedia article says the Cotzumalhuapa zone dates mainly to the Late Classic period, was occupied since th |
| Haidara - Temple of Sun | lat | `coordinates-unresolved` | No readable page prints a point for the Haidara monument at Qab Elias; the listed articles give none, and the only nearb |
| Haidara - Temple of Sun | period_start | `field-unresolved` | L'Orient Today only places Haidara in the Roman period (Roman religious and funerary purposes) without a year or century |
| Kerbatch | lat | `coordinates-unresolved` | The only point I can quote for Kerbatch is the French Wikipedia infobox coordinate 13° 45′ nord, 15° 06′ ouest, which li |
| Termessos Kurucu'nun Evi | period_start | `field-unresolved` | No source I read dates the Founder's House itself; the Roman type of the villa is a period description, not a year, cent |
| Termessos Kurucu'nun Evi | source_url | `field-unresolved` | No page about the Founder's House itself was found; the pages that name it, the ToposText gazetteer entry and the Turkis |
| Ashdown Forest | period_start | `field-unresolved` | The article dates the finds from the Mesolithic only as 11,000-7,000 BP, a BP range for a whole forest of sites of many  |
| Ñawpallaqta, Lucanas | period_start | `field-unresolved` | The English Wikipedia article only places the site on a mountain of the same name in the San Cristobal District, near Pu |
| Qasr Naous Roman Temples | lat | `coordinates-unresolved` | Livius, Wikipedia and the other readable pages print no point for the Qasr Naous temples; the Ain Akrine Wikipedia point |
| Qasr Naous Roman Temples | period_start | `field-unresolved` | Livius calls the two temples Roman and says only that the settlement north of them seems quite late; no readable source  |
| Snowden Crags | period_start | `field-unresolved` | Wikipedia only calls the site prehistoric and The Northern Antiquarian pages on the circle and the necropolis give no da |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s008-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s008 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
