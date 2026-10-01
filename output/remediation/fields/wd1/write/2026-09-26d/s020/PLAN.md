# WD1 fields-wd1-2026-09-26d-s020: plan

Built 2026-09-29T15:46:29+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s020`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s020:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 226 |
| sites_written | 100 |
| refused | 28 |
| cells:period_name | 94 |
| cells:period_start | 94 |
| cells:site_type | 33 |
| cells:source_url | 5 |
| refused:coordinates-unresolved | 28 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Aboriginal Sites of New South Wales | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Aboriginal Sites of New South Wales | period_start | `-40000` | `NULL` | wd1-clear |
| Aboriginal Sites of New South Wales | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Acinipo | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Acinipo | period_start | `-500` | `NULL` | wd1-clear |
| Alyscamps | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Alyscamps | period_start | `1` | `NULL` | wd1-clear |
| Ancient Theatre of Thassos | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Ancient Theatre of Thassos | period_start | `-1500` | `-500` | wd1-replace |
| Ancient Theatre of Thassos | source_url | `https://diazoma.gr/en/theaters/ancient-theater-of-thassos/` | `https://el.wikipedia.org/wiki/%CE%91%CF%81%CF%87%CE%B1%CE%AF` | wd1-replace |
| Arc de Triomphe Septime Sévère | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Archaeological Park of Dion | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Archaeological Park of Dion | period_start | `-1500` | `NULL` | wd1-clear |
| Archaeological Park of Dion | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Arroyo el Concho | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Arroyo el Concho | period_start | `500` | `NULL` | wd1-clear |
| Arroyo el Concho | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Balanica | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Balanica | period_start | `-525000` | `NULL` | wd1-clear |
| Battlesbury Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Battlesbury Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Beltany Stone Circle | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Beltany Stone Circle | period_start | `-3000` | `-1400` | wd1-replace |
| Blackpatch | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Blackpatch | period_start | `-4500` | `NULL` | wd1-clear |
| Brent Knoll Camp | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Brent Knoll Camp | period_start | `-4500` | `NULL` | wd1-clear |
| Cade's Road | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Cade's Road | period_start | `1` | `NULL` | wd1-clear |
| Cardurnock | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Cardurnock | period_start | `1` | `NULL` | wd1-clear |
| Carn Liath - Broch | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Carn Liath - Broch | period_start | `-1500` | `NULL` | wd1-clear |
| Castle Dykes Henge | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Castle Dykes Henge | period_start | `-4500` | `NULL` | wd1-clear |
| Castro de Elviña | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Castro de Elviña | period_start | `-1000` | `-300` | wd1-replace |
| Cicerone Tower | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cicerone Tower | period_start | `-1500` | `NULL` | wd1-clear |
| Cicerone Tower | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Cicerone Tower | source_url | `https://artsupp.com/en/arpino/museums/torre-di-cicerone` | `https://www.triphobo.com/places/roccasecca-italy/cicerone-to` | wd1-replace |
| Clovelly Dykes | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Clovelly Dykes | period_start | `-1000` | `NULL` | wd1-clear |
| Cosgrove, Northamptonshire | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Cosgrove, Northamptonshire | period_start | `1` | `NULL` | wd1-clear |
| Cuddie Springs | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cuddie Springs | period_start | `-8000` | `NULL` | wd1-clear |
| Dimale | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Dimale | period_start | `-500` | `NULL` | wd1-clear |
| Dinies Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dinies Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Dolaucothi Gold Mines | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dolaucothi Gold Mines | period_start | `1` | `NULL` | wd1-clear |
| Dolebury Warren | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Dolebury Warren | period_start | `-3000` | `NULL` | wd1-clear |
| Ebbsfleet Valley | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ebbsfleet Valley | period_start | `-4500` | `NULL` | wd1-clear |
| Enkomi | source_url | `https://topostext.org/place/352339UEnk` | `https://en.wikipedia.org/wiki/Enkomi_(archaeological_site)` | wd1-replace |
| Falkner's Circle | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Falkner's Circle | period_start | `-2300` | `NULL` | wd1-clear |
| Ferrier of Tannerre-en-Puisaye | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ferrier of Tannerre-en-Puisaye | period_start | `-1500` | `NULL` | wd1-clear |
| Flowerdown Barrows | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Flowerdown Barrows | period_start | `-4500` | `NULL` | wd1-clear |
| Great Wymondley | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Great Wymondley | period_start | `1` | `NULL` | wd1-clear |
| Green Gully Archaeological Site | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Green Gully Archaeological Site | period_start | `-4500` | `NULL` | wd1-clear |
| Green Gully Archaeological Site | site_type | `Geological interest` | `Burial` | wd1-replace |
| Grotte de Gabillou | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Grotte de Gabillou | period_start | `-500` | `NULL` | wd1-clear |
| Għar il-Kbir | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Għar il-Kbir | period_start | `-3800` | `NULL` | wd1-clear |
| Hadrianopolis (Epirus) | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Hadrianopolis (Epirus) | period_start | `-500` | `NULL` | wd1-clear |
| Hane, Marquesas Islands | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Hane, Marquesas Islands | period_start | `500` | `NULL` | wd1-clear |
| Harhoog | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Harhoog | period_start | `-3000` | `NULL` | wd1-clear |
| Heidenmauer, Palatinate | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Heidenmauer, Palatinate | period_start | `-1500` | `-500` | wd1-replace |
| Huaca Casa Rosada | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Huaca Casa Rosada | period_start | `500` | `NULL` | wd1-clear |
| K'allapayuq Urqu | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| K'allapayuq Urqu | period_start | `1000` | `NULL` | wd1-clear |
| K'allapayuq Urqu | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| K'ipakhara | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| K'ipakhara | period_start | `1` | `NULL` | wd1-clear |
| K'ipakhara | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Kaya mezarları | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Kaya mezarları | period_start | `-400` | `NULL` | wd1-clear |
| Kaya mezarları | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Killarumiyuq | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Killarumiyuq | period_start | `1400` | `NULL` | wd1-clear |
| Kultepe-2 | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Kultepe-2 | period_start | `-4500` | `NULL` | wd1-clear |
| La Amelia | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| La Amelia | period_start | `500` | `NULL` | wd1-clear |
| La Amelia | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| La Chaire a Calvin | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| La Chaire a Calvin | period_start | `-13000` | `NULL` | wd1-clear |
| La Table de Jugurtha | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| La Table de Jugurtha | period_start | `1` | `-200` | wd1-replace |
| Langweiler - Archaeological Site | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Langweiler - Archaeological Site | period_start | `-5300` | `NULL` | wd1-clear |
| Langweiler - Archaeological Site | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Lappa, Crete | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Lappa, Crete | period_start | `-2000` | `NULL` | wd1-clear |
| Lavau Grave | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Lavau Grave | period_start | `-1500` | `-500` | wd1-replace |
| Lavau Grave | site_type | `Mound/tumulus` | `Tomb` | wd1-replace |
| Les Ruines | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Les Ruines | period_start | `-1500` | `NULL` | wd1-clear |
| Les Ruines | site_type | `Temple complex` | `City` | wd1-replace |
| Les Ruines | source_url | `https://www.easyvoyage.com/algerie/les-ruines-romaines-99` | `https://en.wikipedia.org/wiki/Tipasa` | wd1-replace |
| Lungkeng | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Lungkeng | period_start | `-4000` | `NULL` | wd1-clear |
| Lungkeng | site_type | `Archaeological site` | `NULL` | wd1-clear |
| Merri, Orne | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Merri, Orne | period_start | `-3000` | `NULL` | wd1-clear |
| Millka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Millka | period_start | `1000` | `NULL` | wd1-clear |
| Millka | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Mirq'imarka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Mirq'imarka | period_start | `1400` | `NULL` | wd1-clear |
| Mirq'imarka | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Museo Regional de Campeche | period_name | `1500+ AD` | `NULL` | wd1-derive-period-name |
| Museo Regional de Campeche | period_start | `1986` | `NULL` | wd1-clear |
| Museo Regional de Campeche | site_type | `Museum` | `NULL` | wd1-clear |
| Nakrang Tombs | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Nakrang Tombs | period_start | `-1000` | `NULL` | wd1-clear |
| Niumatou Site | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Niumatou Site | period_start | `-2000` | `NULL` | wd1-clear |
| Niumatou Site | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Olynthus | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Olynthus | period_start | `-3000` | `NULL` | wd1-clear |
| Overstone Anglo-Saxon Cemetery | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Overstone Anglo-Saxon Cemetery | period_start | `450` | `NULL` | wd1-clear |
| Palatki Heritage Site | period_name | `4500 - 3000 BC` | `1000 - 1500 AD` | wd1-derive-period-name |
| Palatki Heritage Site | period_start | `-4500` | `1100` | wd1-replace |
| Pannonian Limes | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Pannonian Limes | period_start | `-500` | `NULL` | wd1-clear |
| Pantelleria Vecchia Bank Megalith | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Pantelleria Vecchia Bank Megalith | period_start | `-8000` | `NULL` | wd1-clear |
| Pantelleria Vecchia Bank Megalith | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Paracas History Museum | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Paracas History Museum | period_start | `-800` | `NULL` | wd1-clear |
| Paracas History Museum | site_type | `Elongated skulls` | `Museum` | wd1-replace |
| Paso del Macho | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Paso del Macho | period_start | `-900` | `NULL` | wd1-clear |
| Perge Theatre | source_url | `http://www.tuerkei-antik.de/Theater/perge_en.htm` | `https://kitabe.org/en/antalya/perge-theatre` | wd1-replace |
| Perperikon | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Perperikon | period_start | `-3000` | `-5000` | wd1-replace |
| Pharaonic Tayma Inscription | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Pharaonic Tayma Inscription | period_start | `-500` | `-1192` | wd1-replace |
| Pheia, Elis | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Pheia, Elis | period_start | `-1500` | `NULL` | wd1-clear |
| Pinkuylluna | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Pinkuylluna | period_start | `1000` | `NULL` | wd1-clear |
| Piruro | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Piruro | period_start | `-3000` | `NULL` | wd1-clear |
| Piruro | site_type | `Temple complex` | `NULL` | wd1-clear |
| Pont Vell, Santa Eulària des Riu | period_name | `1 - 500 AD` | `1500+ AD` | wd1-derive-period-name |
| Pont Vell, Santa Eulària des Riu | period_start | `1` | `1701` | wd1-replace |
| Ponte de Gimonde | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ponte de Gimonde | period_start | `1` | `NULL` | wd1-clear |
| Porlock Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Porlock Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Punta de Chimino | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Punta de Chimino | period_start | `1` | `NULL` | wd1-clear |
| Punta de Chimino | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Rock Carvings in Central Norway | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Rock Carvings in Central Norway | period_start | `-6000` | `NULL` | wd1-clear |
| Rock City | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Rock City | period_start | `1` | `NULL` | wd1-clear |
| Rock City | site_type | `Geological interest` | `NULL` | wd1-clear |
| Roman Ruins of Creiro | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Ruins of Creiro | period_start | `1` | `NULL` | wd1-clear |
| Roman Villa of Quinta da Bolacha | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Villa of Quinta da Bolacha | period_start | `1` | `NULL` | wd1-clear |
| Roman Villa of Vale do Mouro | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Villa of Vale do Mouro | period_start | `1` | `NULL` | wd1-clear |
| Roman Villa of Vale do Mouro | site_type | `Residence/villa/farmhouse` | `NULL` | wd1-clear |
| San Clemente | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| San Clemente | period_start | `1` | `NULL` | wd1-clear |
| San Clemente | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Segesta | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Segesta | period_start | `-1500` | `NULL` | wd1-clear |
| Skopje Aqueduct | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Skopje Aqueduct | period_start | `1` | `NULL` | wd1-clear |
| Son Oleza | site_type | `Dolmen` | `City/town/settlement` | wd1-replace |
| Square Peristyle | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Tahai Ceremonial Complex | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Tahai Ceremonial Complex | period_start | `690` | `NULL` | wd1-clear |
| Tahai Ceremonial Complex | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Tarnowskie Góry | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Tarnowskie Góry | period_start | `-1500` | `NULL` | wd1-clear |
| Tas-Silġ | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Tas-Silġ | period_start | `-3000` | `-3150` | wd1-replace |
| Temple of Ptah, Sekhmet and Nefertom | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Temple of Ptah, Sekhmet and Nefertom | period_start | `-3000` | `NULL` | wd1-clear |
| Tenampua | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tenampua | period_start | `250` | `NULL` | wd1-clear |
| Tenampua | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| The Goatstones | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| The Goatstones | period_start | `-4500` | `NULL` | wd1-clear |
| Troullos | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Troullos | period_start | `-3000` | `NULL` | wd1-clear |
| Troullos | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Verziau of Gargantua | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Verziau of Gargantua | period_start | `-4500` | `NULL` | wd1-clear |
| Vrokastro | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Vrokastro | period_start | `-3000` | `NULL` | wd1-clear |
| Waman Pirqa | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Waman Pirqa | period_start | `1400` | `NULL` | wd1-clear |
| Waman Pirqa | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Warawtampu | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Wari Willka | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wari Willka | period_start | `1` | `NULL` | wd1-clear |
| Wasteberry Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wasteberry Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Ñusta Hispana | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Ñusta Hispana | period_start | `1450` | `NULL` | wd1-clear |
| Ñusta Hispana | site_type | `Rock art` | `NULL` | wd1-clear |
| Čurug | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Čurug | period_start | `-500` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Museo Regional de Campeche | lat | `coordinates-unresolved` | No source found gives a point for the Museo Regional de Campeche (Casa Teniente de Rey). |
| Perge Theatre | lat | `coordinates-unresolved` | No source found quotes coordinates for the theatre itself; Ancient Routes Türkiye gives only a rounded point for the cit |
| Lavau Grave | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent source with a point was found. |
| Arroyo el Concho | lat | `coordinates-unresolved` | Only the Megalithic Portal prints a point for Arroyo el Concho; no independent second source. |
| Overstone Anglo-Saxon Cemetery | lat | `coordinates-unresolved` | No source prints a point for the Overstone cemetery; Wikipedia gives none. |
| Square Peristyle | lat | `coordinates-unresolved` | Only Qualla gives a point (37.976, 23.724), which rounds Wikidata's; no independent source gives one. |
| Aboriginal Sites of New South Wales | lat | `coordinates-unresolved` | The entry is a collective of sites across New South Wales, not one place; no source gives a single point. |
| Rock City | lat | `coordinates-unresolved` | No source found quotes coordinates for a Rock City at this point. |
| Rock Carvings in Central Norway | lat | `coordinates-unresolved` | The entry names a region (Central Norway), not one site; no source gives a point for it. |
| Troullos | lat | `coordinates-unresolved` | No source gives a point for Troullos; the stored point cannot be confirmed. |
| Paso del Macho | lat | `coordinates-unresolved` | No source found gives a point for the Paso del Macho site in Yucatán; the Wikipedia hit is the Veracruz municipality. |
| Arc de Triomphe Septime Sévère | lat | `coordinates-unresolved` | No source found quotes coordinates for the arch of Septimius Severus at Dougga. |
| San Clemente | lat | `coordinates-unresolved` | No source gives a point for San Clemente; the stored point cannot be confirmed. |
| Pantelleria Vecchia Bank Megalith | lat | `coordinates-unresolved` | No source prints a point for the submerged block. |
| Nakrang Tombs | lat | `coordinates-unresolved` | No source found gives a point for the Nakrang tomb field. |
| Kaya mezarları | lat | `coordinates-unresolved` | No source found quotes coordinates for these rock tombs. |
| Pannonian Limes | lat | `coordinates-unresolved` | The Pannonian Limes is a 420 km frontier line; no source gives a single point for it, and the stored point lies far from |
| Les Ruines | lat | `coordinates-unresolved` | Only Wikipedia gives a point for Tipasa (36.59194 N 2.44944 E); no independent source with coordinates was found. |
| Cicerone Tower | lat | `coordinates-unresolved` | No source prints a point for the Cicerone Tower. |
| Ponte de Gimonde | lat | `coordinates-unresolved` | Only Wikipedia gives a point for the Ponte de Gimonde; no second independent source was found. |
| Paracas History Museum | lat | `coordinates-unresolved` | No source found gives a point for the Paracas History Museum. |
| Enkomi | lat | `coordinates-unresolved` | Only Wikipedia's article on the archaeological site gives a point (35.15972 N 33.88833 E); no independent second source  |
| Lungkeng | lat | `coordinates-unresolved` | No source found quotes coordinates for the Lungkeng site. |
| Punta de Chimino | lat | `coordinates-unresolved` | Only the Wikipedia family gives a point; Qualla's 16.432, -90.192 rounds it; no independent source confirms the stored p |
| Waman Pirqa | lat | `coordinates-unresolved` | No source found gives a point for Waman Pirqa. |
| Pharaonic Tayma Inscription | lat | `coordinates-unresolved` | No source found gives a point for the Pharaonic Tayma inscription. |
| K'ipakhara | lat | `coordinates-unresolved` | No source found gives a point for K'ipakhara. |
| Mirq'imarka | lat | `coordinates-unresolved` | No source found gives a point for Mirq'imarka. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s020-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s020 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
