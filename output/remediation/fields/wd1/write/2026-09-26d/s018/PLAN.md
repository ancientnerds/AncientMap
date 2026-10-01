# WD1 fields-wd1-2026-09-26d-s018: plan

Built 2026-09-29T15:44:45+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s018`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s018:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 213 |
| sites_written | 100 |
| refused | 18 |
| cells:geom | 1 |
| cells:lat | 1 |
| cells:lon | 1 |
| cells:period_name | 96 |
| cells:period_start | 96 |
| cells:site_type | 17 |
| cells:source_url | 1 |
| refused:coordinates-unresolved | 18 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Afrodit Tapınağı | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Afrodit Tapınağı | period_start | `-500` | `-600` | wd1-replace |
| Afrodit Tapınağı | source_url | `https://whc.unesco.org/en/list/1519/` | `https://en.wikipedia.org/wiki/Sanctuary_of_Aphrodite_Aphrodi` | wd1-replace |
| Alignements de Kerzerho | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Alignements de Kerzerho | period_start | `-5000` | `NULL` | wd1-clear |
| Ambresbury Banks | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ambresbury Banks | period_start | `-1500` | `NULL` | wd1-clear |
| Apollonia | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Apollonia | period_start | `-1500` | `-500` | wd1-replace |
| Archaeological Area Santu Pedrù | geom | `0101000020E6100000C2DFAAFF4FCC204020429E6654524440` | `SRID=4326;POINT(8.402948 40.623527)` | wd1-point |
| Archaeological Area Santu Pedrù | lat | `40.6432007096048` | `40.623527` | wd1-replace |
| Archaeological Area Santu Pedrù | lon | `8.399047841652536` | `8.402948` | wd1-replace |
| Area Archaeological Sa Mandra 'e Sa Giua | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Area Archaeological Sa Mandra 'e Sa Giua | period_start | `-3000` | `NULL` | wd1-clear |
| Area Archaeological Sa Mandra 'e Sa Giua | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Aufina | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Aufina | period_start | `-500` | `NULL` | wd1-clear |
| Autun | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Autun | period_start | `-500` | `NULL` | wd1-clear |
| Balcon de Montezuma | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Balcon de Montezuma | period_start | `1` | `NULL` | wd1-clear |
| Boskednan Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Boskednan Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Bruach An Druimein, Kimartin Glen | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Bruach An Druimein, Kimartin Glen | period_start | `-4000` | `NULL` | wd1-clear |
| Bruach An Druimein, Kimartin Glen | site_type | `Cemetery` | `NULL` | wd1-clear |
| Burridge Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Burridge Fort | period_start | `-1000` | `NULL` | wd1-clear |
| Burridge Fort | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Burry Holms | period_name | `1500 - 500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Burry Holms | period_start | `-1500` | `-10000` | wd1-replace |
| Buzeyir Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Buzeyir Cave | period_start | `-70000` | `NULL` | wd1-clear |
| Caer Euni | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Caer Euni | period_start | `-1500` | `NULL` | wd1-clear |
| Cambria Farm | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Cambria Farm | period_start | `-3000` | `NULL` | wd1-clear |
| Caracol Natural Monument Reservation | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Caracol Natural Monument Reservation | period_start | `1` | `-1200` | wd1-replace |
| Carn Euny | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Castlenalacht Stone Row | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Castlenalacht Stone Row | period_start | `-2000` | `NULL` | wd1-clear |
| Cerro Sechín | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Cerro Sechín | period_start | `-3000` | `NULL` | wd1-clear |
| Chipaw Marka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Chipaw Marka | period_start | `1000` | `NULL` | wd1-clear |
| Chipaw Marka | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Chiripa Archaeological site | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Chiripa Archaeological site | period_start | `-1500` | `NULL` | wd1-clear |
| Chisenbury Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Chisenbury Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Chongbang Fortress | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Chongbang Fortress | period_start | `1` | `NULL` | wd1-clear |
| Citânia de Santa Luzia | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Citânia de Santa Luzia | period_start | `-3000` | `NULL` | wd1-clear |
| Combs Ditch | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Combs Ditch | period_start | `-500` | `NULL` | wd1-clear |
| Compsa | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Compsa | period_start | `-500` | `NULL` | wd1-clear |
| Drizzlecombe | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Drizzlecombe | period_start | `-4500` | `NULL` | wd1-clear |
| Dundon Hill Hillfort | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Dundon Hill Hillfort | period_start | `-2000` | `NULL` | wd1-clear |
| Eartham Pit, Boxgrove | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Eartham Pit, Boxgrove | period_start | `-480000` | `NULL` | wd1-clear |
| El Cedral | site_type | `Temple complex` | `NULL` | wd1-clear |
| El Tepozteco | site_type | `Temple complex` | `Temple` | wd1-replace |
| Elche | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Elche | period_start | `-1500` | `NULL` | wd1-clear |
| Escoural Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Escoural Cave | period_start | `-50000` | `NULL` | wd1-clear |
| Fen Causeway | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Fen Causeway | period_start | `1` | `NULL` | wd1-clear |
| Giant's Grave, Cumbria | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Giant's Grave, Cumbria | period_start | `-4500` | `NULL` | wd1-clear |
| Giecz | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Giecz | period_start | `1` | `801` | wd1-replace |
| Grasburg, Rottleberode | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Grasburg, Rottleberode | period_start | `-2000` | `NULL` | wd1-clear |
| Great Tottington | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Great Tottington | period_start | `-4500` | `NULL` | wd1-clear |
| Great Tottington | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Hodson Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Hodson Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Igeum-dong | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Igeum-dong | period_start | `-1500` | `NULL` | wd1-clear |
| Igeum-dong | site_type | `Cemetery` | `NULL` | wd1-clear |
| Kahta Castle | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Kahta Castle | period_start | `1` | `-200` | wd1-replace |
| Kahta Castle | site_type | `Fortress/citadel` | `Castle` | wd1-replace |
| Kale-Krševica | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Kale-Krševica | period_start | `-500` | `-1300` | wd1-replace |
| King's Quoit | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| King's Quoit | period_start | `-5000` | `NULL` | wd1-clear |
| Kings Weston Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kings Weston Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Knoll Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Knoll Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Les Combarelles | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Les Combarelles | period_start | `-11680` | `NULL` | wd1-clear |
| Lindos | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Lindos | period_start | `-1000` | `NULL` | wd1-clear |
| Llaqta Qulluy, Acoria | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Llaqta Qulluy, Acoria | period_start | `1400` | `NULL` | wd1-clear |
| Llaqta Qulluy, Acoria | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Machu Pirqa | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Machu Pirqa | period_start | `500` | `NULL` | wd1-clear |
| Machu Pirqa | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Maen Llia | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Maen Llia | period_start | `-4000` | `NULL` | wd1-clear |
| Maes Knoll | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Maes Knoll | period_start | `-500` | `NULL` | wd1-clear |
| Maison Carré | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Maison Carré | period_start | `1` | `NULL` | wd1-clear |
| Malia, Crete | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Malia, Crete | period_start | `-2000` | `NULL` | wd1-clear |
| Mayburgh Henge | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Mayburgh Henge | period_start | `-4500` | `NULL` | wd1-clear |
| Medicine Wheel/Medicine Mountain National Historic Landmark | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Medicine Wheel/Medicine Mountain National Historic Landmark | period_start | `1200` | `NULL` | wd1-clear |
| Mihailovac | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Mihailovac | period_start | `-500` | `NULL` | wd1-clear |
| Mihailovac | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Moel y Gaer, Llanbedr | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Moel y Gaer, Llanbedr | period_start | `-1500` | `NULL` | wd1-clear |
| Mulinuyuq | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Mulinuyuq | period_start | `1400` | `NULL` | wd1-clear |
| Mycenaean Cemetery of Voudeni | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Mycenaean Cemetery of Voudeni | period_start | `-3000` | `-1500` | wd1-replace |
| Neolithic Flint Mines of Spiennes | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Neolithic Flint Mines of Spiennes | period_start | `-5000` | `-4300` | wd1-replace |
| Nettleton, Wiltshire | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Nettleton, Wiltshire | period_start | `-4500` | `NULL` | wd1-clear |
| Obadiah's Barrow | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Obadiah's Barrow | period_start | `-3000` | `NULL` | wd1-clear |
| Osiris Shaft | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Osiris Shaft | period_start | `-1550` | `NULL` | wd1-clear |
| Osiris Shaft | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Partiscum (Castra) | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Partiscum (Castra) | period_start | `1` | `NULL` | wd1-clear |
| Petrovaradin | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Petrovaradin | period_start | `-500` | `NULL` | wd1-clear |
| Pikimachay | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Pikimachay | period_start | `-500` | `NULL` | wd1-clear |
| Pocklington Iron Age Burial Ground | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Pocklington Iron Age Burial Ground | period_start | `-500` | `NULL` | wd1-clear |
| Poston Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Poston Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Prokuplje | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Prokuplje | period_start | `-6000` | `NULL` | wd1-clear |
| Pusuquy Pata | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pusuquy Pata | period_start | `1` | `NULL` | wd1-clear |
| Pusuquy Pata | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Qurimarka, Apurímac | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Qurimarka, Apurímac | period_start | `1400` | `NULL` | wd1-clear |
| Ras il-Wardija | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Ras il-Wardija | period_start | `-3000` | `-1500` | wd1-replace |
| Roman Bridge of Mina, Relizane | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Bridge of Mina, Relizane | period_start | `1` | `NULL` | wd1-clear |
| Route of Megalithic Culture | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Route of Megalithic Culture | period_start | `-4000` | `NULL` | wd1-clear |
| San Pawl Milqi | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| San Pawl Milqi | period_start | `-500` | `NULL` | wd1-clear |
| Scladina | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Scladina | period_start | `-127000` | `NULL` | wd1-clear |
| Segsbury Camp | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Segsbury Camp | period_start | `-500` | `-600` | wd1-replace |
| Shearplace Hill Enclosure | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Shearplace Hill Enclosure | period_start | `-3000` | `NULL` | wd1-clear |
| Shihsanhang Museum of Archaeology | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Shihsanhang Museum of Archaeology | period_start | `1` | `NULL` | wd1-clear |
| Swinside | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Swinside | period_start | `-4500` | `NULL` | wd1-clear |
| Tebay | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tebay | period_start | `1` | `NULL` | wd1-clear |
| Templebryan Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Templebryan Stone Circle | period_start | `-4000` | `NULL` | wd1-clear |
| The Hurlers Stone Circles | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| The Hurlers Stone Circles | period_start | `-4000` | `NULL` | wd1-clear |
| Thickthorn Down Long Barrows | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Thickthorn Down Long Barrows | period_start | `-4500` | `NULL` | wd1-clear |
| Tomb of Queen Khentkawes I | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Tomb of Queen Khentkawes I | period_start | `-3000` | `NULL` | wd1-clear |
| Tomb of Ramhai | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tomb of Ramhai | period_start | `-500` | `NULL` | wd1-clear |
| Tomb of Ramhai | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Trendle Ring | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Trendle Ring | period_start | `-2000` | `NULL` | wd1-clear |
| Tsona Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tsona Cave | period_start | `-500` | `NULL` | wd1-clear |
| Tsutskhvati Cave Natural Monument | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tsutskhvati Cave Natural Monument | period_start | `-500` | `NULL` | wd1-clear |
| Tune Stone | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tune Stone | period_start | `1` | `NULL` | wd1-clear |
| Tunley Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Tunley Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Ventanillas de Otuzco | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Ventanillas de Otuzco | period_start | `-1500` | `-300` | wd1-replace |
| Virgil's Tomb | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Virgil's Tomb | period_start | `-500` | `NULL` | wd1-clear |
| Vlochos Archaeological Site | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Vlochos Archaeological Site | period_start | `-1000` | `NULL` | wd1-clear |
| Woodhenge | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Woodhenge | period_start | `-4500` | `-2500` | wd1-replace |
| Wooston Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wooston Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Xihuatoxtla | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Xihuatoxtla | period_start | `-8700` | `NULL` | wd1-clear |
| Yunus Sütunu | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Yunus Sütunu | period_start | `-1500` | `NULL` | wd1-clear |
| Yunus Sütunu | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Židovar | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Židovar | period_start | `-4000` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Kahta Castle | lat | `coordinates-unresolved` | Only Apple Maps quotes a point (0.24 km from the stored one); no independent second source confirms it. |
| Afrodit Tapınağı | lat | `coordinates-unresolved` | No source found quotes coordinates for the Temple of Aphrodite at Aphrodisias. |
| El Cedral | lat | `coordinates-unresolved` | The only other points found lie 10-13 km away; no source confirms the stored point. |
| Roman Bridge of Mina, Relizane | lat | `coordinates-unresolved` | No source with coordinates for the Roman bridge of Mina was found. |
| Great Tottington | lat | `coordinates-unresolved` | Wikipedia prints no point for Great Tottington and no other source gives one, so no two sources can be quoted. |
| Hodson Stone Circle | lat | `coordinates-unresolved` | The Hodson Stone Circle is destroyed and Wikipedia prints no point for it; no source gives its coordinates, so no two so |
| Xihuatoxtla | lat | `coordinates-unresolved` | No source found gives a point for the Xihuatoxtla shelter. |
| Bruach An Druimein, Kimartin Glen | lat | `coordinates-unresolved` | No source found gives a point for Bruach an Druimein. |
| Route of Megalithic Culture | lat | `coordinates-unresolved` | The Route of Megalithic Culture is a 330 km holiday route; no source gives a single point for it, so the stored point ca |
| Mihailovac | lat | `coordinates-unresolved` | No source gives a point for Mihailovac near Vršac; the Digital Atlas point lies 128 km away at another Mihailovac. |
| Area Archaeological Sa Mandra 'e Sa Giua | lat | `coordinates-unresolved` | No source prints a point for Sa Mandra 'e Sa Giua. |
| Osiris Shaft | lat | `coordinates-unresolved` | No two independent sources give a point for the Osiris Shaft. |
| Llaqta Qulluy, Acoria | lat | `coordinates-unresolved` | No source found gives a point for Llaqta Qulluy in Acoria. |
| Yunus Sütunu | lat | `coordinates-unresolved` | No source found quotes coordinates for the Yunus Sütunu. |
| Qurimarka, Apurímac | lat | `coordinates-unresolved` | No source found gives a point for Qurimarka in Apurímac. |
| Pusuquy Pata | lat | `coordinates-unresolved` | No source found gives a point for Pusuquy Pata. |
| Mulinuyuq | lat | `coordinates-unresolved` | No source found gives a point for Mulinuyuq. |
| Tomb of Ramhai | lat | `coordinates-unresolved` | No source gives a point for the Tomb of Ramhai. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s018-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s018 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
