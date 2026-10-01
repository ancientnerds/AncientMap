# WD1 fields-wd1-2026-09-26d-s011: plan

Built 2026-09-29T15:38:03+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s011`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s011:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 210 |
| sites_written | 98 |
| refused | 18 |
| cells:period_name | 91 |
| cells:period_start | 91 |
| cells:site_type | 25 |
| cells:source_url | 3 |
| refused:coordinates-unresolved | 18 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acidava | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Acidava | period_start | `1` | `NULL` | wd1-clear |
| Adullam Grove Nature Reserve | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Adullam Grove Nature Reserve | period_start | `-3000` | `NULL` | wd1-clear |
| Adullam Grove Nature Reserve | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Aequum Tuticum | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Aequum Tuticum | period_start | `-3000` | `NULL` | wd1-clear |
| Amiternum | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Amiternum | period_start | `-3000` | `NULL` | wd1-clear |
| Ancient City of Sillyon | period_name | `1 - 500 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Ancient City of Sillyon | period_start | `1` | `-2000` | wd1-replace |
| Asine | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Asine | period_start | `-1000` | `NULL` | wd1-clear |
| Bat's Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bat's Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Blagaj Fortress | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Blagaj Fortress | period_start | `1` | `NULL` | wd1-clear |
| Blowing Stone | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Blowing Stone | period_start | `-3000` | `NULL` | wd1-clear |
| Bosporthennis | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Bosporthennis | period_start | `-500` | `NULL` | wd1-clear |
| Burgh Walls Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Burgh Walls Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Castle Folds | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Castle Folds | period_start | `1` | `NULL` | wd1-clear |
| Castle Folds | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Castle Rings, Wiltshire | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castle Rings, Wiltshire | period_start | `-1500` | `NULL` | wd1-clear |
| Castles Camp | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Castles Camp | period_start | `-3000` | `NULL` | wd1-clear |
| Cenabum | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cenabum | period_start | `-500` | `NULL` | wd1-clear |
| Colebrooke, Devon | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Colebrooke, Devon | period_start | `1` | `NULL` | wd1-clear |
| Colonial Forum of Tarraco | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Colonial Forum of Tarraco | period_start | `1` | `-100` | wd1-replace |
| Corycus, Crete | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Corycus, Crete | period_start | `-2000` | `NULL` | wd1-clear |
| Craddock Moor Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Craddock Moor Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Cras  Round Cairn | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cras  Round Cairn | period_start | `-5000` | `NULL` | wd1-clear |
| Cras  Round Cairn | site_type | `Cairn` | `NULL` | wd1-clear |
| Crawley Edge Cairns | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Crawley Edge Cairns | period_start | `-3000` | `NULL` | wd1-clear |
| Dalton Parlours Roman Villa | site_type | `Residence/villa/farmhouse` | `Villa` | wd1-replace |
| Danubian Limes | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Danubian Limes | period_start | `1` | `NULL` | wd1-clear |
| Delos | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Delos | period_start | `-1500` | `-3000` | wd1-replace |
| Early Roman House | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Early Roman House | period_start | `1` | `NULL` | wd1-clear |
| Early Roman House | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| El Pedregal Archaeological Site | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| El Pedregal Archaeological Site | period_start | `1` | `-500` | wd1-replace |
| El Pedregal Archaeological Site | site_type | `Petroglyphs` | `Rock art` | wd1-replace |
| Foel Dduarth Enclosure | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Foel Dduarth Enclosure | period_start | `-5000` | `NULL` | wd1-clear |
| Foel Dduarth Enclosure | site_type | `Earthwork` | `NULL` | wd1-clear |
| Foel Dduarth Enclosure | source_url | `NULL` | `https://archwilio.org.uk/her/chi3/report/page.php?watprn=GAT` | wd1-replace |
| Giants' Graves | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Giants' Graves | period_start | `-1800` | `NULL` | wd1-clear |
| Giants' Graves | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Gudit Stelae Field | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Gudit Stelae Field | source_url | `NULL` | `https://www.findtourguide.com/destinations/ethiopia/aksum-31` | wd1-replace |
| Halae | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Halae | period_start | `-2000` | `NULL` | wd1-clear |
| Hatun Uchku | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Hatun Uchku | period_start | `1` | `NULL` | wd1-clear |
| Hatun Uchku | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Hembury | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Hembury | period_start | `-4500` | `NULL` | wd1-clear |
| Holkham Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Holkham Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Huntsham Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Huntsham Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Hypogeum of Torre del Ram | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Jadranovo | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Jadranovo | period_start | `-500` | `NULL` | wd1-clear |
| Keston Roman Villa | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Keston Roman Villa | period_start | `1` | `NULL` | wd1-clear |
| Khapia | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Khapia | period_start | `1` | `NULL` | wd1-clear |
| Kinđa | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Kinđa | period_start | `-500` | `NULL` | wd1-clear |
| Kirkdale Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Kirkdale Cave | period_start | `-121000` | `NULL` | wd1-clear |
| Koumasa | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Koumasa | period_start | `-4000` | `-3000` | wd1-replace |
| Kriemhildenstuhl | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kriemhildenstuhl | period_start | `1` | `NULL` | wd1-clear |
| Kul Farah Historical Site | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kul Farah Historical Site | period_start | `-1500` | `NULL` | wd1-clear |
| Kunturmarka, Pasco | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Kunturmarka, Pasco | period_start | `1400` | `NULL` | wd1-clear |
| Kunturmarka, Pasco | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Kusilluchayoc - El Templo de los Monos | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Kusilluchayoc - El Templo de los Monos | period_start | `1000` | `NULL` | wd1-clear |
| La Marche Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| La Marche Cave | period_start | `-500` | `NULL` | wd1-clear |
| Lapford | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Lapford | period_start | `1` | `NULL` | wd1-clear |
| Le Moustier | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Le Moustier | period_start | `-500` | `NULL` | wd1-clear |
| Lindus | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Lindus | period_start | `-1500` | `NULL` | wd1-clear |
| Lismore Fields | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Lismore Fields | period_start | `-5000` | `NULL` | wd1-clear |
| Lismore Fields | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Little Sodbury | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Little Sodbury | period_start | `-1000` | `NULL` | wd1-clear |
| Llwynda-Ddu Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Llwynda-Ddu Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Mockham Down | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Mockham Down | period_start | `-1000` | `NULL` | wd1-clear |
| Mockham Down | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Muyu Muyu | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Muyu Muyu | period_start | `1400` | `NULL` | wd1-clear |
| Muyu Muyu | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Necropoli Etrusca di Norchia | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Necropoli Etrusca di Norchia | period_start | `-500` | `NULL` | wd1-clear |
| Necropoli Etrusca di Norchia | site_type | `City/town/settlement` | `Necropolis` | wd1-replace |
| Necropoli Etrusca di Norchia | source_url | `https://www.passaggilenti.com/norchia-necropoli-etrusche/` | `https://lazioeventi.com/luoghi-da-visitare/necropoli-etrusca` | wd1-replace |
| Nuragic Complex of Sa Sedda e Sos Carros | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Nuragic Complex of Sa Sedda e Sos Carros | period_start | `-1000` | `NULL` | wd1-clear |
| Nuragic Complex of Sa Sedda e Sos Carros | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Oddendale | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Oddendale | period_start | `-2000` | `NULL` | wd1-clear |
| Olympe | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Olympe | period_start | `-400` | `NULL` | wd1-clear |
| Penycloddiau | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Penycloddiau | period_start | `-1500` | `NULL` | wd1-clear |
| Perthi-Duon Burial Chamber | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Perthi-Duon Burial Chamber | period_start | `-5000` | `NULL` | wd1-clear |
| Phyle Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Phyle Cave | period_start | `-500` | `NULL` | wd1-clear |
| Plainsfield Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Plainsfield Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Ponte de Rubiães | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ponte de Rubiães | period_start | `1` | `NULL` | wd1-clear |
| Puente Romano de la Alcantarilla | site_type | `Gate/archway/bridge` | `NULL` | wd1-clear |
| Punta de Estaca de Bares | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Punta de Estaca de Bares | period_start | `-2000` | `NULL` | wd1-clear |
| Pye Road | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pye Road | period_start | `1` | `NULL` | wd1-clear |
| Q'asa Pata | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Q'asa Pata | period_start | `1400` | `NULL` | wd1-clear |
| Q'asa Pata | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Ringmoor Stone Row and Cairn Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ringmoor Stone Row and Cairn Circle | period_start | `-4000` | `NULL` | wd1-clear |
| Roman Milestones of Braga | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Milestones of Braga | period_start | `1` | `NULL` | wd1-clear |
| Roman Milestones of Braga | site_type | `Inscription` | `NULL` | wd1-clear |
| San Manuel Cenote | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| San Manuel Cenote | period_start | `1` | `NULL` | wd1-clear |
| Scorhill Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Scorhill Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Scutchamer Knob | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Scutchamer Knob | period_start | `-1500` | `NULL` | wd1-clear |
| Sexi - Phoenician Colony | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Sexi - Phoenician Colony | period_start | `-500` | `-900` | wd1-replace |
| Shrub's Wood Long Barrow | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Shrub's Wood Long Barrow | period_start | `-4000` | `NULL` | wd1-clear |
| Stanborough | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Stanborough | period_start | `-1000` | `NULL` | wd1-clear |
| Station Stones - Stonehenge | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Station Stones - Stonehenge | period_start | `-3000` | `NULL` | wd1-clear |
| Sturminster Newton Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Sturminster Newton Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Sutton Walls Hill Fort | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Sutton Walls Hill Fort | period_start | `-1000` | `-300` | wd1-replace |
| The Larches, Monmouthshire | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| The Larches, Monmouthshire | period_start | `-1500` | `NULL` | wd1-clear |
| Tillya Tepe | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tillya Tepe | period_start | `-500` | `NULL` | wd1-clear |
| Tonina | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Tonina | period_start | `500` | `NULL` | wd1-clear |
| Tonina | site_type | `Pyramid complex` | `City/town/settlement` | wd1-replace |
| Trajan's Kiosk | site_type | `Temple complex` | `Temple` | wd1-replace |
| Tremeca | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Tremeca | period_start | `-4500` | `NULL` | wd1-clear |
| Tumshukayko | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Tumshukayko | period_start | `-3000` | `NULL` | wd1-clear |
| Tupu Inka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Tupu Inka | period_start | `1400` | `NULL` | wd1-clear |
| Tupu Inka | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Uthina Amphitheatre | site_type | `Megalithic stones` | `Amphitheatre` | wd1-replace |
| Valtos Leptokaryas | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Valtos Leptokaryas | period_start | `-1930` | `NULL` | wd1-clear |
| Verterae | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Verterae | period_start | `1` | `NULL` | wd1-clear |
| Vestiges of the Gallo-Roman Wall, Grenoble | site_type | `Fortress/citadel` | `Wall` | wd1-replace |
| Virosidum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Virosidum | period_start | `1` | `NULL` | wd1-clear |
| Vučedol | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Vučedol | period_start | `-4000` | `NULL` | wd1-clear |
| Welsh Way | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Welsh Way | period_start | `-1500` | `NULL` | wd1-clear |
| Wendover | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wendover | period_start | `-1000` | `NULL` | wd1-clear |
| Wimble Toot | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Wimble Toot | period_start | `-3000` | `NULL` | wd1-clear |
| Wincobank - Hill Fort | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Wincobank - Hill Fort | period_start | `-1500` | `-500` | wd1-replace |
| Woodbury Hill, Dorset | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Woodbury Hill, Dorset | period_start | `-2000` | `NULL` | wd1-clear |
| Yellowmead Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Yellowmead Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Zemun | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Zemun | period_start | `-500` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Roman Milestones of Braga | lat | `coordinates-unresolved` | No source found gives a point for the Roman milestones of Braga, which are spread over several parishes. |
| San Manuel Cenote | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point for the San Manuel cenote; no second independent source was found. |
| Necropoli Etrusca di Norchia | lat | `coordinates-unresolved` | Only Wikipedia prints a point for Norchia; no independent second source. |
| El Pedregal Archaeological Site | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent source with a point was found. |
| Foel Dduarth Enclosure | lat | `coordinates-unresolved` | Only the Megalithic Portal quotes a point (0.02 km from the stored one); no independent second source confirms it. |
| Roman Walls | lat | `coordinates-unresolved` | Only Ancient Travel prints a point for Aosta's Roman remains, 0.5 km off; no second source for the walls. |
| Vučedol | lat | `coordinates-unresolved` | Only Wikipedia gives a point for the site itself; the other point belongs to the Vucedol Culture Museum page, so no seco |
| Giants' Graves | lat | `coordinates-unresolved` | The entry is the Giants' graves of Sardinia as a type, spread across the island; no source gives one point. |
| Q'asa Pata | lat | `coordinates-unresolved` | No source found gives a point for Q'asa Pata in Ayacucho. |
| Corycus, Crete | lat | `coordinates-unresolved` | Corycus is known from Ptolemy only; no source gives a point for the ancient town, so the stored point cannot be confirme |
| Ancient City of Sillyon | lat | `coordinates-unresolved` | Only Turkish Archaeological News quotes a point, 4.3 km from the stored one; no second source confirms a point. |
| Puente Romano de la Alcantarilla | lat | `coordinates-unresolved` | No source found quotes coordinates for the Alcantarilla bridge; the Wikipedia hit is the Guadiana bridge, 1.9 km away. |
| Cras  Round Cairn | lat | `coordinates-unresolved` | No source found quotes coordinates for this cairn; the Wikipedia hit is a county list 5.4 km away. |
| Kunturmarka, Pasco | lat | `coordinates-unresolved` | No source found gives a point for Kunturmarka in Pasco. |
| Welsh Way | lat | `coordinates-unresolved` | No source prints a point for the Welsh Way, a long track-way. |
| Danubian Limes | lat | `coordinates-unresolved` | The Danubian Limes is a linear frontier; no source gives a point for it, so the stored point cannot be confirmed. |
| Gudit Stelae Field | lat | `coordinates-unresolved` | No two independent sources give a point for the Gudit Stelae Field. |
| Early Roman House | lat | `coordinates-unresolved` | No source identifies a site called the Early Roman House, so no point can be sourced. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s011-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s011 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
