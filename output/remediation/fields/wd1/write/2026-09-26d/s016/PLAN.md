# WD1 fields-wd1-2026-09-26d-s016: plan

Built 2026-09-29T15:42:34+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s016`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s016:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 223 |
| sites_written | 99 |
| refused | 19 |
| cells:period_name | 94 |
| cells:period_start | 94 |
| cells:site_type | 29 |
| cells:source_url | 6 |
| refused:coordinates-unresolved | 19 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acropolis of Athens | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Acropolis of Athens | period_start | `-1500` | `NULL` | wd1-clear |
| Al Sanea Tomb | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Al Sanea Tomb | period_start | `1` | `NULL` | wd1-clear |
| Al Sanea Tomb | source_url | `https://www.safarway.com/en/property/al-sanea-tomb` | `https://ar.wikipedia.org/wiki/%D9%82%D8%B5%D8%B1_%D8%A7%D9%8` | wd1-replace |
| Alauna, Maryport | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Alauna, Maryport | period_start | `1` | `NULL` | wd1-clear |
| Alconétar Bridge | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Alconétar Bridge | period_start | `1` | `NULL` | wd1-clear |
| Ancon Archaeological Site | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Ancon Archaeological Site | period_start | `-8000` | `NULL` | wd1-clear |
| Ancon Archaeological Site | site_type | `City/town/settlement` | `Necropolis` | wd1-replace |
| Anta do Paço da Vinha | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Anta do Paço da Vinha | period_start | `-4000` | `NULL` | wd1-clear |
| Arlobi Menhir | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Arlobi Menhir | period_start | `-3000` | `NULL` | wd1-clear |
| Ashdown Forest | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Ashdown Forest | period_start | `-9000` | `NULL` | wd1-clear |
| Ashdown Forest | site_type | `Barrow` | `NULL` | wd1-clear |
| Baho Dheri | site_type | `Temple complex` | `NULL` | wd1-clear |
| Balamkú | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Balamkú | period_start | `-300` | `NULL` | wd1-clear |
| Ballynoe Stone Circle | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Ballynoe Stone Circle | period_start | `-4000` | `-3000` | wd1-replace |
| Banbury Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Banbury Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Baumann's Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Baumann's Cave | period_start | `-50000` | `NULL` | wd1-clear |
| Bet She'arim National Park | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Bet She'arim National Park | period_start | `1` | `NULL` | wd1-clear |
| Bet She'arim National Park | site_type | `Cave Structures` | `Necropolis` | wd1-replace |
| Bet She'arim National Park | source_url | `https://whc.unesco.org/en/list/1471/` | `https://en.wikipedia.org/wiki/Beit_She%27arim_necropolis` | wd1-replace |
| Boringdon Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Boringdon Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Brandon Camp | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Brandon Camp | period_start | `-500` | `NULL` | wd1-clear |
| Braughing - Roman Town | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Braughing - Roman Town | period_start | `-500` | `NULL` | wd1-clear |
| Broomfield Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Broomfield Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Bwrdd Arthur | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bwrdd Arthur | period_start | `-1500` | `NULL` | wd1-clear |
| Ca n'Oliver Iberian Settlement and Museum | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ca n'Oliver Iberian Settlement and Museum | period_start | `-1500` | `NULL` | wd1-clear |
| Caral-Supe | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Caral-Supe | period_start | `-4500` | `-3000` | wd1-replace |
| Casteddu di Tappa | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Casteddu di Tappa | period_start | `-4500` | `NULL` | wd1-clear |
| Casteddu di Tappa | site_type | `Megalithic stones` | `Fortress` | wd1-replace |
| Castell Cawr | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castell Cawr | period_start | `-1500` | `NULL` | wd1-clear |
| Castle Old Fort | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Castle Old Fort | period_start | `-500` | `NULL` | wd1-clear |
| Castra ad Montanesium | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Castra ad Montanesium | period_start | `1` | `NULL` | wd1-clear |
| Catacombs of Saint Gaudiosus | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Catacombs of Saint Gaudiosus | period_start | `1` | `NULL` | wd1-clear |
| Cerro Pátapo Ruins | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Cerro Pátapo Ruins | period_start | `1` | `NULL` | wd1-clear |
| Chacmultun | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Chacmultun | period_start | `-500` | `NULL` | wd1-clear |
| Combe-Capelle | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Combe-Capelle | period_start | `-7500` | `NULL` | wd1-clear |
| Coney's Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Coney's Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Cotzumalhuapa | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cotzumalhuapa | period_start | `-1500` | `NULL` | wd1-clear |
| Cotzumalhuapa | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Cras -  Round Cairn to North of | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cras -  Round Cairn to North of | period_start | `-5000` | `NULL` | wd1-clear |
| Cras -  Round Cairn to North of | site_type | `Cairn` | `NULL` | wd1-clear |
| Danish Camp | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Danish Camp | period_start | `-400` | `NULL` | wd1-clear |
| Danish Camp | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Devil's Jumps, Treyford | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Devil's Jumps, Treyford | period_start | `-4500` | `NULL` | wd1-clear |
| Dewerstone | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dewerstone | period_start | `-1000` | `NULL` | wd1-clear |
| Dewerstone | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Dinghurst Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dinghurst Fort | period_start | `-1000` | `NULL` | wd1-clear |
| Dokan-e-Davood | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dokan-e-Davood | period_start | `-1500` | `NULL` | wd1-clear |
| Dokan-e-Davood | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Dokan-e-Davood | source_url | `https://www.cais-soas.com/CAIS/Archaeology/Hakhamaneshian/do` | `https://en.wikipedia.org/wiki/Dukkan-e_Daud` | wd1-replace |
| Dolno Gradište | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dolno Gradište | period_start | `1` | `NULL` | wd1-clear |
| Dolno Gradište | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Duddo Five Stones | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Duddo Five Stones | period_start | `-4500` | `-2000` | wd1-replace |
| Dun Fiadhairt Broch | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dun Fiadhairt Broch | period_start | `1` | `NULL` | wd1-clear |
| El Temblor | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| El Temblor | period_start | `500` | `NULL` | wd1-clear |
| El Temblor | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Ex voto(s) of the Argives, Delphi | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Ex voto(s) of the Argives, Delphi | period_start | `-500` | `NULL` | wd1-clear |
| Ferrybridge Henge | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ferrybridge Henge | period_start | `-4500` | `NULL` | wd1-clear |
| Frilford | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Frilford | period_start | `-500` | `NULL` | wd1-clear |
| Gradište Archaeological Site, Iđoš | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Gradište Archaeological Site, Iđoš | period_start | `-5000` | `NULL` | wd1-clear |
| Grapčeva Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Grapčeva Cave | period_start | `-7000` | `NULL` | wd1-clear |
| Haidara - Temple of Sun | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Haidara - Temple of Sun | period_start | `100` | `NULL` | wd1-clear |
| Haidara - Temple of Sun | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Henblas Burial Chamber | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Henblas Burial Chamber | period_start | `-5000` | `NULL` | wd1-clear |
| Huaca del Dragón | period_name | `500 - 1000 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Huaca del Dragón | period_start | `900` | `1001` | wd1-replace |
| Huaca del Dragón | site_type | `Temple complex` | `Temple` | wd1-replace |
| Karasis Kalesi | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Karasis Kalesi | period_start | `-500` | `NULL` | wd1-clear |
| Karasis Kalesi | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Kerbatch | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Kerbatch | period_start | `-500` | `NULL` | wd1-clear |
| Kirkby Thore | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kirkby Thore | period_start | `1` | `NULL` | wd1-clear |
| Lancken - Granitz Dolmens | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Lancken - Granitz Dolmens | period_start | `-4500` | `NULL` | wd1-clear |
| Lesche of the Knidians | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Llamuqa | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Llamuqa | period_start | `1` | `NULL` | wd1-clear |
| Llanfechell | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Llanfechell | period_start | `-4000` | `NULL` | wd1-clear |
| Marcahuamachuco | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Mawk'allaqta, Paruro | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Mawk'allaqta, Paruro | period_start | `1400` | `NULL` | wd1-clear |
| Mawk'allaqta, Paruro | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Milber Down | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Milber Down | period_start | `-1000` | `NULL` | wd1-clear |
| Miseno | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Miseno | period_start | `-500` | `NULL` | wd1-clear |
| Moel Arthur | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Moel Arthur | period_start | `-1500` | `NULL` | wd1-clear |
| Mojeque | site_type | `Temple complex` | `NULL` | wd1-clear |
| Nina Kiru | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Nina Kiru | period_start | `1000` | `NULL` | wd1-clear |
| Nina Kiru | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Nine Stones Close | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Nine Stones Close | period_start | `-4500` | `NULL` | wd1-clear |
| Nine Stones, Altarnun | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Nine Stones, Altarnun | period_start | `-4500` | `NULL` | wd1-clear |
| Nitriansky Hrádok | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Nitriansky Hrádok | period_start | `-5000` | `NULL` | wd1-clear |
| Norsebury Ring | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Norsebury Ring | period_start | `-1000` | `NULL` | wd1-clear |
| Oakley Down Barrow Cemetery | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Oakley Down Barrow Cemetery | period_start | `-3000` | `NULL` | wd1-clear |
| Oakmere Hill Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Oakmere Hill Fort | period_start | `-1000` | `NULL` | wd1-clear |
| Paradeisos Archaeological Site | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Paradeisos Archaeological Site | period_start | `-6000` | `NULL` | wd1-clear |
| Pautalia | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pautalia | period_start | `1` | `NULL` | wd1-clear |
| Pilluchu | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pilluchu | period_start | `1` | `NULL` | wd1-clear |
| Pilluchu | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Pisissarfik | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Pisissarfik | period_start | `1000` | `NULL` | wd1-clear |
| Pod | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Pod | period_start | `-3000` | `NULL` | wd1-clear |
| Pod | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Quillarumi | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Quillarumi | period_start | `1` | `NULL` | wd1-clear |
| Roman Road from Silchester to Bath | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Road from Silchester to Bath | period_start | `1` | `NULL` | wd1-clear |
| Rujum Al-Hiri | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Rujum Al-Hiri | period_start | `-4500` | `-3000` | wd1-replace |
| Rumiwasi | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Rumiwasi | period_start | `1400` | `NULL` | wd1-clear |
| Runayoc | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Runayoc | period_start | `1` | `NULL` | wd1-clear |
| Runayoc | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Samothrace Temple Complex | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Samothrace Temple Complex | period_start | `-1500` | `NULL` | wd1-clear |
| Shahhat | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Shahhat | source_url | `https://libyaobserver.ly/culture/ancient-city-shahat-cyrene` | `https://plizio.com/en/libya/ly-ja/shahhat/` | wd1-replace |
| Sofia | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Sofia | period_start | `-500` | `NULL` | wd1-clear |
| Southwest Temple of the Ancient Agora of Athens | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Southwest Temple of the Ancient Agora of Athens | period_start | `1` | `NULL` | wd1-clear |
| Spinsters' Rock | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Spinsters' Rock | period_start | `-4500` | `NULL` | wd1-clear |
| Tal-Barrani | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tal-Barrani | period_start | `1` | `NULL` | wd1-clear |
| Tal-Barrani | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Tempio Nuragico a Pozzo di Irru | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Tempio Nuragico a Pozzo di Irru | period_start | `-3000` | `NULL` | wd1-clear |
| Tempio Nuragico a Pozzo di Irru | site_type | `Temple complex` | `NULL` | wd1-clear |
| Tempio Nuragico a Pozzo di Irru | source_url | `NULL` | `https://sardegnaversounesco.org/il-tempio-nuragico-a-pozzo-d` | wd1-replace |
| Temple E, Selinus | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Temple E, Selinus | period_start | `-1500` | `NULL` | wd1-clear |
| Temple of Apollo, Pompeii | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Temple of Apollo, Pompeii | period_start | `-500` | `-600` | wd1-replace |
| Termessos Kurucu'nun Evi | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Termessos Kurucu'nun Evi | period_start | `-500` | `NULL` | wd1-clear |
| Termessos Kurucu'nun Evi | site_type | `Residence/villa/farmhouse` | `NULL` | wd1-clear |
| Termessos Kurucu'nun Evi | source_url | `https://www.alamy.com/stock-photo-ruins-of-the-founders-hous` | `NULL` | wd1-clear |
| Tombeau de Merlin | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Tombeau de Merlin | period_start | `-4500` | `NULL` | wd1-clear |
| Torberry Hill | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Torberry Hill | period_start | `-1500` | `-500` | wd1-replace |
| Trou de l'Abîme | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Trou de l'Abîme | period_start | `-50000` | `NULL` | wd1-clear |
| Venado Beach | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Venado Beach | period_start | `1` | `NULL` | wd1-clear |
| Venta Belgarum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Venta Belgarum | period_start | `1` | `NULL` | wd1-clear |
| Vespasian's Camp | period_name | `1500 - 500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Vespasian's Camp | period_start | `-1500` | `-6250` | wd1-replace |
| Warbstow Bury | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Warbstow Bury | period_start | `-1000` | `NULL` | wd1-clear |
| Warbstow Bury | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Wichqana | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wichqana | period_start | `-1500` | `NULL` | wd1-clear |
| Yemshi Tepe | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Yemshi Tepe | period_start | `1` | `NULL` | wd1-clear |
| Yemshi Tepe | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Ħal Ġinwi Temple | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ħal Ġinwi Temple | period_start | `-4500` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Tempio Nuragico a Pozzo di Irru | lat | `coordinates-unresolved` | No source prints a point for the Irru holy well. |
| Runayoc | lat | `coordinates-unresolved` | No source found gives a point for Runayoc. |
| Ex voto(s) of the Argives, Delphi | lat | `coordinates-unresolved` | No source gives a point for the Argive offerings at Delphi; the stored point cannot be confirmed. |
| Karasis Kalesi | lat | `coordinates-unresolved` | No source found quotes coordinates for Karasis. |
| Cras -  Round Cairn to North of | lat | `coordinates-unresolved` | No source found quotes coordinates for this cairn. |
| Venado Beach | lat | `coordinates-unresolved` | No source found gives a point for Venado Beach. |
| Western Walls of Thessalonica | lat | `coordinates-unresolved` | No source gives a point for the western section of the walls; Cultural Heritage Online's point for the whole circuit lie |
| Pautalia | lat | `coordinates-unresolved` | Wikipedia prints no point and the only other point (Ancient Bulgaria) is 0.6 km off; no two independent sources agree. |
| Al Sanea Tomb | lat | `coordinates-unresolved` | No source found gives a point for the Al Sanea tomb; Wikipedia's point for Al-Ula lies 18.6 km away. |
| Nina Kiru | lat | `coordinates-unresolved` | No source found gives a point for Nina Kiru. |
| Dokan-e-Davood | lat | `coordinates-unresolved` | No source prints a point for Dokan-e-Davood. |
| Baho Dheri | lat | `coordinates-unresolved` | No source found gives a point for Baho Dheri. |
| Bet She'arim National Park | lat | `coordinates-unresolved` | Only Wikipedia prints a point for the Beit She'arim necropolis; no independent second source. |
| Anta do Paço da Vinha | lat | `coordinates-unresolved` | Portuguese Wikipedia gives a point about 0.1 km from the stored one, but no second independent source prints coordinates |
| Shahhat | lat | `coordinates-unresolved` | The only points found are for the modern town of Shahhat, about 2 km away; no source gives a point for the stored site. |
| Haidara - Temple of Sun | lat | `coordinates-unresolved` | No source prints a point for the Haidara monument. |
| Kerbatch | lat | `coordinates-unresolved` | Only Mysteria gives a point at the stored location (Plizio's lies 3.8 km away); no second independent source agrees. |
| Termessos Kurucu'nun Evi | lat | `coordinates-unresolved` | No source found quotes coordinates for the Founder's House. |
| Ashdown Forest | lat | `coordinates-unresolved` | Ashdown Forest is a large area with more than 570 sites; no source gives a single point for this entry. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s016-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s016 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
