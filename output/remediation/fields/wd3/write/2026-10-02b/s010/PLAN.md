# WD3 fields-wd3-2026-10-02b-s010: plan

Built 2026-10-04T12:52:38+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s010`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s010:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 198 |
| sites_written | 99 |
| refused | 29 |
| cells:geom | 6 |
| cells:lat | 6 |
| cells:lon | 6 |
| cells:period_name | 76 |
| cells:period_start | 76 |
| cells:site_type | 28 |
| refused:coordinates-unresolved | 12 |
| refused:field-unresolved | 16 |
| refused:not-a-curated-live-site | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acinipo | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Acinipo | period_start | `NULL` | `-45` | wd3-replace |
| Alcantarilla Dam | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Alcantarilla Dam | period_start | `NULL` | `-200` | wd3-replace |
| Allahdino | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Allahdino | period_start | `NULL` | `-2000` | wd3-replace |
| Ancaster, Lincolnshire | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Ancaster, Lincolnshire | period_start | `NULL` | `1` | wd3-replace |
| Arc de Triomphe Septime Sévère | site_type | `NULL` | `Monument` | wd3-replace |
| Archaeological Park of Dion | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Archaeological Park of Dion | period_start | `NULL` | `-500` | wd3-replace |
| Azykh Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Azykh Cave | period_start | `NULL` | `-700000` | wd3-replace |
| Baba-Dervish Settlement | geom | `0101000020E61000009F647922DEAE464073A79AE8F78B4440` | `SRID=4326;POINT(45.293892 41.073917)` | wd3-point |
| Baba-Dervish Settlement | lat | `41.09350307036848` | `41.073917` | wd3-replace |
| Baba-Dervish Settlement | lon | `45.36615401198764` | `45.293892` | wd3-replace |
| Ballowall Barrow | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Ballowall Barrow | period_start | `NULL` | `-3500` | wd3-replace |
| Ballyedmonduff Wedge Tomb | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Ballyedmonduff Wedge Tomb | period_start | `NULL` | `-1700` | wd3-replace |
| Beacon Ring | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Beacon Ring | period_start | `NULL` | `-400` | wd3-replace |
| Besshatyr Burial Ground | geom | `0101000020E6100000B28494C9BC9B5340C175A8B1AF2A4640` | `SRID=4326;POINT(78.21056 43.92278)` | wd3-point |
| Besshatyr Burial Ground | lat | `44.333486754661415` | `43.92278` | wd3-replace |
| Besshatyr Burial Ground | lon | `78.43339766982788` | `78.21056` | wd3-replace |
| Brauron | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Brauron | period_start | `NULL` | `-5000` | wd3-replace |
| Broch of Culswick | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Broch of Culswick | period_start | `NULL` | `-500` | wd3-replace |
| Cadbury Castle, Somerset | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Cadbury Castle, Somerset | period_start | `NULL` | `-3500` | wd3-replace |
| Cade's Road | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Cade's Road | period_start | `NULL` | `138` | wd3-replace |
| Carn Liath - Broch | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Carn Liath - Broch | period_start | `NULL` | `-100` | wd3-replace |
| Castro of Cidadelhe | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Castro of Cidadelhe | period_start | `NULL` | `-900` | wd3-replace |
| Caverna da Pedra Pintada | geom | `0101000020E610000001CADB1DBD154BC038E3727ADC5100C0` | `SRID=4326;POINT(-54.165 -2.058056)` | wd3-point |
| Caverna da Pedra Pintada | lat | `-2.03997131026372` | `-2.058056` | wd3-replace |
| Caverna da Pedra Pintada | lon | `-54.16983388168229` | `-54.165` | wd3-replace |
| Cerro De Trincheras | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Cerro De Trincheras | period_start | `NULL` | `1300` | wd3-replace |
| Cerro De Trincheras | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Cicerone Tower | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Cicerone Tower | period_start | `NULL` | `1001` | wd3-replace |
| Cicerone Tower | site_type | `NULL` | `Minaret/tower` | wd3-replace |
| Comagena | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Comagena | period_start | `NULL` | `81` | wd3-replace |
| Comer's Midden | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Comer's Midden | period_start | `NULL` | `1301` | wd3-replace |
| Comer's Midden | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Conjunto Arqueologico de Ñustahispana | site_type | `NULL` | `Rock relief/carving` | wd3-replace |
| Damb Sadat | geom | `0101000020E61000008C6CA26FFBBF50404E6A689D312F3E40` | `SRID=4326;POINT(66.95 30.05)` | wd3-point |
| Damb Sadat | lat | `30.184350812904363` | `30.05` | wd3-replace |
| Damb Sadat | lon | `66.99972143995018` | `66.95` | wd3-replace |
| Danbury, Essex | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Danbury, Essex | period_start | `NULL` | `-600` | wd3-replace |
| Devil's Highway - Roman Britain | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Devil's Highway - Roman Britain | period_start | `NULL` | `47` | wd3-replace |
| Dimale | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Dimale | period_start | `NULL` | `-500` | wd3-replace |
| Dolebury Warren | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Dolebury Warren | period_start | `NULL` | `-700` | wd3-replace |
| Doll Tor | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Doll Tor | period_start | `NULL` | `-2000` | wd3-replace |
| Duggleby Howe | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Duggleby Howe | period_start | `NULL` | `-3500` | wd3-replace |
| Dun Cuier | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Dun Cuier | period_start | `NULL` | `301` | wd3-replace |
| Fushan Archaeological Site | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Fushan Archaeological Site | period_start | `NULL` | `-1750` | wd3-replace |
| Fushan Archaeological Site | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Graves of Sainte-Colombe-sur-Seine | geom | `0101000020E61000008D730B5DED551340D756A44186B54740` | `SRID=4326;POINT(4.54978 47.87688)` | wd3-point |
| Graves of Sainte-Colombe-sur-Seine | lat | `47.41815968059898` | `47.87688` | wd3-replace |
| Graves of Sainte-Colombe-sur-Seine | lon | `4.833913282226502` | `4.54978` | wd3-replace |
| Great Dolmen of Dwasieden | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Great Dolmen of Dwasieden | period_start | `NULL` | `-3500` | wd3-replace |
| Hadrianopolis (Epirus) | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Hadrianopolis (Epirus) | period_start | `NULL` | `-425` | wd3-replace |
| Hane, Marquesas Islands | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Hane, Marquesas Islands | period_start | `NULL` | `900` | wd3-replace |
| Harhoog | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Harhoog | period_start | `NULL` | `-3000` | wd3-replace |
| Helsby Hill Fort | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Helsby Hill Fort | period_start | `NULL` | `-1250` | wd3-replace |
| Hunsbury Hill | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Hunsbury Hill | period_start | `NULL` | `-700` | wd3-replace |
| K'allapayuq Urqu | site_type | `NULL` | `Archaeological site` | wd3-replace |
| K'ipakhara | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Kelly Rounds | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Kelly Rounds | period_start | `NULL` | `-1100` | wd3-replace |
| Khortytsia | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Khortytsia | period_start | `NULL` | `-10000` | wd3-replace |
| Koviljkin grad | site_type | `NULL` | `Town` | wd3-replace |
| Kultepe-2 | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Kultepe-2 | period_start | `NULL` | `-3500` | wd3-replace |
| Kuntuyuq | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Kuntuyuq | period_start | `NULL` | `-6000` | wd3-replace |
| La Amelia | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| La Amelia | period_start | `NULL` | `600` | wd3-replace |
| Land of Tema | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Land of Tema | period_start | `NULL` | `-4000` | wd3-replace |
| Langweiler - Archaeological Site | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Langweiler - Archaeological Site | period_start | `NULL` | `-5300` | wd3-replace |
| Langweiler - Archaeological Site | site_type | `NULL` | `Settlement` | wd3-replace |
| Les Ruines | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Les Ruines | period_start | `NULL` | `-600` | wd3-replace |
| Lugbury Long Barrow | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Lugbury Long Barrow | period_start | `NULL` | `-3700` | wd3-replace |
| Lungkeng | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Lynford Quarry | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Lynford Quarry | period_start | `NULL` | `-58000` | wd3-replace |
| Maa Palaeokastro | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Maa Palaeokastro | period_start | `NULL` | `-1200` | wd3-replace |
| Merri, Orne | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Merri, Orne | period_start | `NULL` | `-3500` | wd3-replace |
| Metropolis Antik Kenti | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Metropolis Antik Kenti | period_start | `NULL` | `-1400` | wd3-replace |
| Miculla Petroglyphs | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Miculla Petroglyphs | period_start | `NULL` | `500` | wd3-replace |
| Nazca Lines | geom | `0101000020E61000008A5DDA2AF8C652C06629D48257782DC0` | `SRID=4326;POINT(-75.135 -14.6975)` | wd3-point |
| Nazca Lines | lat | `-14.735042656325003` | `-14.6975` | wd3-replace |
| Nazca Lines | lon | `-75.10889693569894` | `-75.135` | wd3-replace |
| Nebstone | site_type | `NULL` | `Rock art` | wd3-replace |
| Nether Denton | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Nether Denton | period_start | `NULL` | `81` | wd3-replace |
| Niumatou Site | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Noorpur Stupas | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Noorpur Stupas | period_start | `NULL` | `1` | wd3-replace |
| Noorpur Stupas | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Olynthus | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Olynthus | period_start | `NULL` | `-4000` | wd3-replace |
| Palma di Montechiaro | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Palma di Montechiaro | period_start | `NULL` | `1637` | wd3-replace |
| Pannonian Limes | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Pannonian Limes | period_start | `NULL` | `-31` | wd3-replace |
| Pinkuylluna | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Pinkuylluna | period_start | `NULL` | `1401` | wd3-replace |
| Piruro | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Piruro | period_start | `NULL` | `-3000` | wd3-replace |
| Piruro | site_type | `NULL` | `Fortress` | wd3-replace |
| Pozzo Sacro del Predio Canopoli | site_type | `NULL` | `Well` | wd3-replace |
| Punta de Chimino | site_type | `NULL` | `City` | wd3-replace |
| Ratae Corieltauvorum | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Ratae Corieltauvorum | period_start | `NULL` | `-200` | wd3-replace |
| Richmond Park | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Richmond Park | period_start | `NULL` | `1601` | wd3-replace |
| Rocha da Mina | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Rocha da Mina | period_start | `NULL` | `-50` | wd3-replace |
| Roman Ruins of Creiro | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Roman Ruins of Creiro | period_start | `NULL` | `-100` | wd3-replace |
| Roman Villa of Quinta da Bolacha | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Roman Villa of Quinta da Bolacha | period_start | `NULL` | `201` | wd3-replace |
| Roman Villa of Vale do Mouro | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Roman Villa of Vale do Mouro | period_start | `NULL` | `201` | wd3-replace |
| Roman Villa of Vale do Mouro | site_type | `NULL` | `Settlement` | wd3-replace |
| Roman Villa of Vilares | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Roman Villa of Vilares | period_start | `NULL` | `1` | wd3-replace |
| Ruins of Ténès | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Ruins of Ténès | period_start | `NULL` | `-800` | wd3-replace |
| San Clemente | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| San Clemente | period_start | `NULL` | `250` | wd3-replace |
| San Clemente | site_type | `NULL` | `City` | wd3-replace |
| Sialkot Fort | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Sialkot Fort | period_start | `NULL` | `101` | wd3-replace |
| Sirmium | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Sirmium | period_start | `NULL` | `-5000` | wd3-replace |
| Sitio Arqueológico Altar de Los Sacrificios | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Sitio Arqueológico Altar de Los Sacrificios | period_start | `NULL` | `-800` | wd3-replace |
| Tahai Ceremonial Complex | site_type | `NULL` | `Religious` | wd3-replace |
| Tamarindito | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Tamarindito | period_start | `NULL` | `400` | wd3-replace |
| Tamarindito | site_type | `NULL` | `City` | wd3-replace |
| Taqrachullu | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Tarnowskie Góry | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Tarnowskie Góry | period_start | `NULL` | `1490` | wd3-replace |
| Temple of Ptah, Sekhmet and Nefertom | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Temple of Ptah, Sekhmet and Nefertom | period_start | `NULL` | `-1800` | wd3-replace |
| Tenampua | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Tenampua | period_start | `NULL` | `750` | wd3-replace |
| Tenampua | site_type | `NULL` | `Fortress` | wd3-replace |
| Tipitarillo Yacata | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Tipitarillo Yacata | period_start | `NULL` | `300` | wd3-replace |
| Tipón | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Tipón | period_start | `NULL` | `-1000` | wd3-replace |
| Troullos | site_type | `NULL` | `Settlement` | wd3-replace |
| Viran Kapı | site_type | `NULL` | `Gate` | wd3-replace |
| Vrokastro | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Vrokastro | period_start | `NULL` | `-2160` | wd3-replace |
| Waman Pirqa | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Warawtampu | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Wari Willka | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Wari Willka | period_start | `NULL` | `-800` | wd3-replace |
| Wat's Dyke | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Wat's Dyke | period_start | `NULL` | `820` | wd3-replace |
| Wraxall Camp | site_type | `NULL` | `Settlement` | wd3-replace |
| Yerokambos | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Yerokambos | period_start | `NULL` | `-3300` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Tipitarillo Yacata | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point; no page with a quotable coordinate pair for the Tipitarillo yacata was found ( |
| Pozzo Sacro del Predio Canopoli | period_start | `field-unresolved` | Sources give period words only (Bronzo finale; fine Bronzo medio to età del Ferro) and Sardegna Turismo states the datin |
| Fushan Archaeological Site | lat | `coordinates-unresolved` | Neither the English nor the Chinese Wikipedia article on the Fushan site prints a coordinate pair for it, and its Wikida |
| Koviljkin grad | period_start | `field-unresolved` | No readable source dates the start of Koviljkin grad. English Wikipedia calls the ruins those of a Roman town and the Ge |
| Taqrachullu | period_start | `field-unresolved` | No source gives a start year for Taqrachullu; the English article names the site and its National Cultural Heritage stat |
| Wraxall Camp | period_start | `field-unresolved` | Wikipedia says only that Wraxall Camp (Failand, North Somerset) is an Iron Age settlement and that 1928 excavation found |
| Noorpur Stupas | lat | `coordinates-unresolved` | The only point found (Department of Archaeology and Museums record for the Naupura stupas, 35.8217, 74.2491) lies about  |
| Allahdino | lat | `coordinates-unresolved` | No readable source gives a point for Allahdino: the Pleiades record 398671587 prints no coordinates in its visible text  |
| Nebstone | period_start | `field-unresolved` | Wikipedia only says the cup and ring marked stones of Ilkley Moor are dated somewhere between 3500 and 2500 years old, a |
| Conjunto Arqueologico de Ñustahispana | period_start | `field-unresolved` | Wikipedia and the MINCETUR inventory record call the site Inca without a year, century or millennium for its start; the  |
| K'allapayuq Urqu | period_start | `field-unresolved` | Wikipedia calls it only a Chanka site; a culture name alone gives no year, and no source dates K'allapayuq Urqu. |
| La Amelia | site_type | `field-unresolved` | Sources call La Amelia only a Pre-Columbian Maya archaeological site / small Late Classic site / polity; none names a mo |
| Niumatou Site | period_start | `field-unresolved` | The English Wikipedia article dates the site only relatively: 'Civilizations in the area date to around 4,000 years ago  |
| Tahai Ceremonial Complex | period_start | `field-unresolved` | Wikipedia in English, Spanish and French, Ayres's University of Oregon page on the Tahai research, the World Monuments F |
| Troullos | lat | `coordinates-unresolved` | No readable source prints a point for Troullos itself: its Wikipedia article and Wikidata item carry no coordinate, and  |
| Troullos | period_start | `field-unresolved` | Wikipedia says the site was in use from Middle Minoan II until Late Minoan I, which is a period name without a year, cen |
| San Clemente | lat | `coordinates-unresolved` | Wikipedia, Wikidata and Blom's 1928 article give no point; the only point found is a coarse GeoNames/Mapcarta entry (17  |
| Ñusta Hispana | site | `not-a-curated-live-site` | source ancient_nerds, retired |
| Pannonian Limes | lat | `coordinates-unresolved` | The Pannonian Limes is a frontier line of several hundred kilometres along the Danube; Wikipedia and Wikidata give no po |
| Lungkeng | lat | `coordinates-unresolved` | The English Wikipedia article on Lungkeng prints no coordinate pair for the site, and its Wikidata item Q122820786 carri |
| Lungkeng | period_start | `field-unresolved` | The English Wikipedia article places Lungkeng in 'the pre-ceramic period, 5,000 to 6,000 years ago' and gives only a rad |
| Punta de Chimino | period_start | `field-unresolved` | Wikipedia says only that the site was first settled in the Middle Preclassic period, a period word without a year; no re |
| Waman Pirqa | lat | `coordinates-unresolved` | No source gives a point for Waman Pirqa that can be quoted. The English article has an empty coordinates field, the Wiki |
| Waman Pirqa | period_start | `field-unresolved` | No source dates the start of Waman Pirqa. The English article gives only its name gloss, its location near Antamarka and |
| K'ipakhara | lat | `coordinates-unresolved` | Wikipedia (en) lists K'ipakhara as missing geocoordinates and Wikidata has none; no readable source prints a point. |
| K'ipakhara | period_start | `field-unresolved` | No readable source dates K'ipakhara. |
| Devil's Highway - Roman Britain | lat | `coordinates-unresolved` | The Devil's Highway is a Roman road from London to Silchester; no readable source (English, German or Italian Wikipedia, |
| Lynford Quarry | lat | `coordinates-unresolved` | The stored point is Mundford village, about 2.5 km from the excavated site (NHER grid reference TL 8240 9484). The only  |
| Viran Kapı | period_start | `field-unresolved` | The Cultural Inventory record gives the monument's culture as Rome and no century, and the İzmir Bergama Museum text tha |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s010-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s010 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
