# WD1 fields-wd1-2026-09-26d-s003: plan

Built 2026-09-29T15:30:43+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s003`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s003:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 215 |
| sites_written | 100 |
| refused | 20 |
| cells:geom | 1 |
| cells:lat | 1 |
| cells:lon | 1 |
| cells:period_name | 93 |
| cells:period_start | 92 |
| cells:site_type | 24 |
| cells:source_url | 3 |
| refused:coordinates-unresolved | 20 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Al-Dafi Site | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Al-Mnaykhrat | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Al-Mnaykhrat | period_start | `-1500` | `NULL` | wd1-clear |
| Al-Mnaykhrat | site_type | `Tomb` | `NULL` | wd1-clear |
| Amaru Marka Wasi | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Amaru Marka Wasi | period_start | `1000` | `NULL` | wd1-clear |
| Anundshög | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Anundshög | period_start | `1` | `500` | wd1-replace |
| Arrephorion | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Arrephorion | period_start | `-1000` | `-500` | wd1-replace |
| Balankanche Cave | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Balankanche Cave | period_start | `-1000` | `NULL` | wd1-clear |
| Bant's Carn | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Bant's Carn | period_start | `-3000` | `NULL` | wd1-clear |
| Bassianae | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Bassianae | period_start | `1` | `NULL` | wd1-clear |
| Bayston Hill | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Bayston Hill | period_start | `-500` | `NULL` | wd1-clear |
| Bizzicu Rossu | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Bizzicu Rossu | period_start | `-2000` | `NULL` | wd1-clear |
| Bizzicu Rossu | site_type | `Megalithic structures` | `Dolmen` | wd1-replace |
| Blythe Intaglios | period_name | `500 - 1000 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Blythe Intaglios | period_start | `550` | `-900` | wd1-replace |
| Broadsands Chambered Tomb | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Broadsands Chambered Tomb | period_start | `-4500` | `NULL` | wd1-clear |
| Burroughston Broch | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Burroughston Broch | period_start | `-1500` | `-200` | wd1-replace |
| Cales | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cales | period_start | `-500` | `NULL` | wd1-clear |
| Capler Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Capler Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Castallack Round | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castallack Round | period_start | `-1000` | `NULL` | wd1-clear |
| Castallack Round | site_type | `Earthwork` | `Settlement` | wd1-replace |
| Caus Castle | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Caus Castle | period_start | `-500` | `NULL` | wd1-clear |
| Cerje, Skopje | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Cerje, Skopje | period_start | `-4000` | `NULL` | wd1-clear |
| Cerje, Skopje | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Chalbury Hillfort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Chalbury Hillfort | period_start | `-1000` | `NULL` | wd1-clear |
| Chilworth Ring | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Chilworth Ring | period_start | `-1000` | `NULL` | wd1-clear |
| Cirque Romain de Vienne | site_type | `Pyramid complex` | `NULL` | wd1-clear |
| Clatworthy Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Clatworthy Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Cosquer Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cosquer Cave | period_start | `-500` | `NULL` | wd1-clear |
| Cossington, Kent | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Cossington, Kent | period_start | `-4500` | `NULL` | wd1-clear |
| Cossington, Kent | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Crug Hywel | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Crug Hywel | period_start | `-1500` | `NULL` | wd1-clear |
| Daepyeong | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Daepyeong | period_start | `-4500` | `NULL` | wd1-clear |
| Derinkuyu Underground City | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Derinkuyu Underground City | period_start | `1` | `NULL` | wd1-clear |
| Desfina | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Desfina | period_start | `-500` | `NULL` | wd1-clear |
| Devil's Lapful | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Devil's Lapful | period_start | `-4500` | `NULL` | wd1-clear |
| Dhank Caves | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dhank Caves | period_start | `1` | `NULL` | wd1-clear |
| Dohnsen, Siddernhausen - Dolmen | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Dohnsen, Siddernhausen - Dolmen | period_start | `-4500` | `NULL` | wd1-clear |
| Dolmen del prado de Lácara | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Dolmen del prado de Lácara | period_start | `-4000` | `NULL` | wd1-clear |
| Dolmen of Carapito I | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Dolmen of Carapito I | period_start | `-3000` | `NULL` | wd1-clear |
| Dun Beag Broch | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dun Beag Broch | period_start | `-1000` | `NULL` | wd1-clear |
| Dun Carloway | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dun Carloway | period_start | `1` | `NULL` | wd1-clear |
| East Myne | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| East Myne | period_start | `-3000` | `NULL` | wd1-clear |
| Eastern Biniac Naveta | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Eastern Biniac Naveta | period_start | `-3000` | `-1400` | wd1-replace |
| Edzna | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Edzna | period_start | `-500` | `-600` | wd1-replace |
| Etemenanki (Tower of Babel) | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Etemenanki (Tower of Babel) | period_start | `-3000` | `NULL` | wd1-clear |
| Filitosa | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Filitosa | period_start | `-4500` | `NULL` | wd1-clear |
| Filitosa | site_type | `Megalithic stones` | `Megalithic statues` | wd1-replace |
| Fir Clump Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Fir Clump Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Goldsborough, Scarborough | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Goldsborough, Scarborough | period_start | `1` | `NULL` | wd1-clear |
| Grabbist Hillfort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Grabbist Hillfort | period_start | `-1000` | `NULL` | wd1-clear |
| Gritulu | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Gritulu | period_start | `-6000` | `NULL` | wd1-clear |
| Grumentum | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Grumentum | period_start | `-1500` | `-300` | wd1-replace |
| Hatfield Neolithic Trackway | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Hatfield Neolithic Trackway | period_start | `-3000` | `NULL` | wd1-clear |
| Ingatambo | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ingatambo | period_start | `-1000` | `NULL` | wd1-clear |
| Inka Raqay, Ayacucho | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inka Raqay, Ayacucho | period_start | `1000` | `NULL` | wd1-clear |
| Inka Raqay, Ayacucho | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Izamal | period_name | `500 - 1000 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Izamal | period_start | `500` | `-700` | wd1-replace |
| Kaljaja, Balovac | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kaljaja, Balovac | period_start | `1` | `NULL` | wd1-clear |
| Kaljaja, Balovac | site_type | `Earthwork` | `NULL` | wd1-clear |
| Kenko, Puno | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kenko, Puno | period_start | `1` | `NULL` | wd1-clear |
| Kharrab Shams | site_type | `City/town/settlement` | `Church/cathedral` | wd1-replace |
| Khuntichi Vaat Hadsar Fort | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Khuntichi Vaat Hadsar Fort | period_start | `-100` | `NULL` | wd1-clear |
| King Arthur's Round Table | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| King Arthur's Round Table | period_start | `-4500` | `NULL` | wd1-clear |
| Kingsdown Camp | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Kingsdown Camp | period_start | `-3000` | `NULL` | wd1-clear |
| Kinniside Stone Circle | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Kinniside Stone Circle | period_start | `-3000` | `NULL` | wd1-clear |
| Kültəpə | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Kültəpə | period_start | `-500` | `NULL` | wd1-clear |
| La Draga | geom | `0101000020E610000069A47A4085210640CF09E96D4F0F4540` | `SRID=4326;POINT(2.758611 42.126667)` | wd1-point |
| La Draga | lat | `42.11961149100136` | `42.126667` | wd1-replace |
| La Draga | lon | `2.766367439024681` | `2.758611` | wd1-replace |
| Laüs | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Laüs | period_start | `-1500` | `NULL` | wd1-clear |
| Lee Wood | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Lee Wood | period_start | `-1000` | `NULL` | wd1-clear |
| Lee Wood | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Mahakali Caves | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Mahakali Caves | period_start | `-500` | `NULL` | wd1-clear |
| Mahkeme Ağacin Kültürel Jeositi | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Mahkeme Ağacin Kültürel Jeositi | period_start | `300` | `NULL` | wd1-clear |
| Mahkeme Ağacin Kültürel Jeositi | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Mahkeme Ağacin Kültürel Jeositi | source_url | `https://www.kizilcahamam.bel.tr/GezilecekYerDetayi/MAHKEMEAG` | `https://kizilcahamam.bel.tr/GezilecekYerDetayi/MAHKEMEAGACIN` | wd1-replace |
| Metropolis, Thessaly | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Metropolis, Thessaly | period_start | `-2000` | `NULL` | wd1-clear |
| Necropolises of Pydna | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Necropolises of Pydna | period_start | `-500` | `NULL` | wd1-clear |
| Necropolises of Pydna | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Newberry Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Newberry Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Newberry Castle | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Oppidum des Castels | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Oppidum des Castels | period_start | `-1500` | `-300` | wd1-replace |
| Pen y Gaer | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Pen y Gaer | period_start | `-4500` | `NULL` | wd1-clear |
| Pigi Athinas | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Pigi Athinas | period_start | `-7000` | `NULL` | wd1-clear |
| Pisarissos Antik Kenti | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Pisarissos Antik Kenti | period_start | `-500` | `NULL` | wd1-clear |
| Pisarissos Antik Kenti | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Pisarissos Antik Kenti | source_url | `https://blog.delphinhotel.com/article/23992-pisarissos-antik` | `https://www.alanya.bel.tr/S/867/Ruins` | wd1-replace |
| Pontes Fort | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pontes Fort | period_start | `1` | `NULL` | wd1-clear |
| Porth Hellick Down | site_type | `Cairn` | `Cemetery` | wd1-replace |
| Przywóz | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Przywóz | period_start | `1` | `NULL` | wd1-clear |
| Pumamarka, Urubamba | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Pumamarka, Urubamba | period_start | `1400` | `NULL` | wd1-clear |
| Pumamarka, Urubamba | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Pyrri | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pyrri | period_start | `1` | `NULL` | wd1-clear |
| Pyrri | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Quriwayrachina, Ayacucho | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Quriwayrachina, Ayacucho | period_start | `1000` | `NULL` | wd1-clear |
| Rhodiapolis Ancient City | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Rhodiapolis Ancient City | period_start | `-500` | `-800` | wd1-replace |
| Sagalassos Antoninler Çeşmesi | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Sagalassos Antoninler Çeşmesi | period_start | `1` | `NULL` | wd1-clear |
| Sagalassos Antoninler Çeşmesi | site_type | `Monument` | `NULL` | wd1-clear |
| Samicum | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Samicum | period_start | `-500` | `NULL` | wd1-clear |
| Sara Sara | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Sara Sara | period_start | `1` | `NULL` | wd1-clear |
| Seri Bahlol | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Seri Bahlol | period_start | `1` | `NULL` | wd1-clear |
| Shinewater | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Shinewater | period_start | `-3000` | `NULL` | wd1-clear |
| Showery Tor | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Showery Tor | period_start | `-4000` | `NULL` | wd1-clear |
| St. Paul's Catacombs | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| St. Paul's Catacombs | period_start | `1` | `NULL` | wd1-clear |
| Stadium at Nemea | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Stadium at Nemea | period_start | `-1500` | `-400` | wd1-replace |
| Stapari | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Stapari | period_start | `-5000` | `NULL` | wd1-clear |
| Swarn Bhandar | source_url | `NULL` | `https://en.wikipedia.org/wiki/Son_Bhandar_Caves` | wd1-replace |
| Templeborough | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Templeborough | period_start | `1` | `NULL` | wd1-clear |
| Teotenango | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Themistoclean Wall | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Three Brothers of Grugith | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Three Brothers of Grugith | period_start | `-4500` | `NULL` | wd1-clear |
| Three Brothers of Grugith | site_type | `Megalithic stones` | `Dolmen` | wd1-replace |
| Tomb of Eve | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tomb of Eve | period_start | `1` | `NULL` | wd1-clear |
| Tomba dei Giganti e Nuraghe Imbertighe | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Tomba dei Giganti e Nuraghe Imbertighe | period_start | `-3000` | `NULL` | wd1-clear |
| Tomba dei Giganti e Nuraghe Imbertighe | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Uskallaqta | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Uskallaqta | period_start | `1200` | `NULL` | wd1-clear |
| Uskallaqta | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Vela Spila Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Vela Spila Cave | period_start | `-21000` | `NULL` | wd1-clear |
| Vlajkovac | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Vlajkovac | period_start | `-4000` | `NULL` | wd1-clear |
| Voley Castle | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Voley Castle | period_start | `-2000` | `NULL` | wd1-clear |
| Waulud's Bank | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Waulud's Bank | period_start | `-3000` | `NULL` | wd1-clear |
| Woodbury Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Woodbury Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Xochicalco | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Xochicalco | period_start | `-200` | `NULL` | wd1-clear |
| Zennor Quoit | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Zennor Quoit | period_start | `-3000` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Pigi Athinas | lat | `coordinates-unresolved` | No source gives a point for Pigi Athinas; the stored point cannot be confirmed. |
| Bant's Carn | lat | `coordinates-unresolved` | Only Wikipedia gives a point for Bant's Carn; no independent source with coordinates was found. |
| Themistoclean Wall | lat | `coordinates-unresolved` | The Themistoclean Wall is a city wall several kilometres long; no source gives a single point for it. |
| Khuntichi Vaat Hadsar Fort | lat | `coordinates-unresolved` | Only the Wikipedia family's point for Hadsar fort as a whole is found, 0.5 km off; no source gives a point for the Khunt |
| Kenko, Puno | lat | `coordinates-unresolved` | No source found gives a point for Kenko in Puno. |
| Cirque Romain de Vienne | lat | `coordinates-unresolved` | No two independent sources give a point for the circus; the points found derive from Wikipedia and Wikidata. |
| Balankanche Cave | lat | `coordinates-unresolved` | Only the Wikipedia family prints a point for Balankanché; no independent second source. |
| Mahkeme Ağacin Kültürel Jeositi | lat | `coordinates-unresolved` | No source found quotes coordinates for the Mahkeme Ağacin geosite. |
| Kharrab Shams | lat | `coordinates-unresolved` | No source found quotes coordinates for Kharab Shams. |
| Pisarissos Antik Kenti | lat | `coordinates-unresolved` | Numistr's point lies 2.8 km from the stored one and no other source quotes coordinates. |
| Quriwayrachina, Ayacucho | lat | `coordinates-unresolved` | No source found gives a point for Quriwayrachina in Ayacucho. |
| Cerje, Skopje | lat | `coordinates-unresolved` | No source found gives a point for Cerje. |
| Al-Dafi Site | lat | `coordinates-unresolved` | No source found gives a point for the Al-Dafi site. |
| Hatfield Neolithic Trackway | lat | `coordinates-unresolved` | Wikipedia prints no point for the Lindholme/Hatfield trackway and the only other point found (Megalithic Portal, 53.5569 |
| Sagalassos Antoninler Çeşmesi | lat | `coordinates-unresolved` | No source found quotes coordinates for the Antonine fountain at Sagalassos. |
| Kaljaja, Balovac | lat | `coordinates-unresolved` | No source gives a point near the stored one; Serbian Wikipedia's point lies 11 km away. |
| Shinewater | lat | `coordinates-unresolved` | No source prints a point for the Shinewater settlement; Wikipedia gives none. |
| Cossington, Kent | lat | `coordinates-unresolved` | Wikipedia prints no point for Cossington and no other source gives one for the lost sarsen group, so no two sources can  |
| Pyrri | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates (the location is only believed to be near Komin) and no independent source g |
| Gritulu | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent source with a point was found. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s003-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s003 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
