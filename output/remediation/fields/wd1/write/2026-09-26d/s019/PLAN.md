# WD1 fields-wd1-2026-09-26d-s019: plan

Built 2026-09-29T15:45:41+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s019`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s019:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 216 |
| sites_written | 100 |
| refused | 21 |
| cells:period_name | 94 |
| cells:period_start | 94 |
| cells:site_type | 25 |
| cells:source_url | 3 |
| refused:coordinates-unresolved | 21 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Aké (Yucatan) | period_name | `500 - 1000 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Aké (Yucatan) | period_start | `500` | `-200` | wd1-replace |
| Alcantarilla Dam | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Alcantarilla Dam | period_start | `-500` | `NULL` | wd1-clear |
| Ali Murad Mound | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ali Murad Mound | period_start | `-4500` | `NULL` | wd1-clear |
| Allahdino | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Allahdino | period_start | `-4500` | `NULL` | wd1-clear |
| Amphitheatre of Capua | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Amphitheatre of Capua | period_start | `1` | `NULL` | wd1-clear |
| Ballowall Barrow | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ballowall Barrow | period_start | `-4500` | `NULL` | wd1-clear |
| Begash | site_type | `Residence/villa/farmhouse` | `Settlement` | wd1-replace |
| Berry Castle, Huntshaw | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Berry Castle, Huntshaw | period_start | `-1000` | `NULL` | wd1-clear |
| Berry Castle, Huntshaw | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Blakey Topping Standing Stones | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Blakey Topping Standing Stones | period_start | `-4500` | `NULL` | wd1-clear |
| Boswens Menhir | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Boswens Menhir | period_start | `-4500` | `NULL` | wd1-clear |
| Brauron | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Brauron | period_start | `-500` | `NULL` | wd1-clear |
| Broch of Culswick | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Broch of Culswick | period_start | `-1500` | `NULL` | wd1-clear |
| Buarth-y-Gaer | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Buarth-y-Gaer | period_start | `-1500` | `NULL` | wd1-clear |
| Buarth-y-Gaer | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Bury Bank | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bury Bank | period_start | `-1500` | `NULL` | wd1-clear |
| Cadbury Castle, Somerset | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cadbury Castle, Somerset | period_start | `-1000` | `NULL` | wd1-clear |
| Capton | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Capton | period_start | `-1000` | `NULL` | wd1-clear |
| Castro de Sacóias | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castro de Sacóias | period_start | `-1000` | `NULL` | wd1-clear |
| Castro of Cidadelhe | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Castro of Cidadelhe | period_start | `-3000` | `NULL` | wd1-clear |
| Cave of Gabrovnica | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cave of Gabrovnica | period_start | `-1200` | `NULL` | wd1-clear |
| Caves of Arcy-sur-Cure | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Caves of Arcy-sur-Cure | period_start | `-28000` | `NULL` | wd1-clear |
| Caves of Monte Castillo | period_name | `1 - 500 AD` | `< 4500 BC` | wd1-derive-period-name |
| Caves of Monte Castillo | period_start | `1` | `-40800` | wd1-replace |
| Cerro De Trincheras | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Cerro De Trincheras | period_start | `1000` | `NULL` | wd1-clear |
| Cerro De Trincheras | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Chevdar | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Chevdar | period_start | `-8000` | `NULL` | wd1-clear |
| Chevdar | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Church Hill, West Sussex | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Church Hill, West Sussex | period_start | `-4500` | `NULL` | wd1-clear |
| Codford Circle | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Codford Circle | period_start | `-500` | `NULL` | wd1-clear |
| Colosso di Ramses II | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Colosso di Ramses II | period_start | `-1500` | `NULL` | wd1-clear |
| Colosso di Ramses II | site_type | `Megalithic statues` | `NULL` | wd1-clear |
| Colosso di Ramses II | source_url | `https://it.wikipedia.org/wiki/Colossi_di_Ramses_II` | `NULL` | wd1-clear |
| Comagena | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Comagena | period_start | `1` | `NULL` | wd1-clear |
| Comer's Midden | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Comer's Midden | period_start | `1000` | `NULL` | wd1-clear |
| Comer's Midden | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Conjunto Arqueologico de Ñustahispana | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Conjunto Arqueologico de Ñustahispana | period_start | `1000` | `NULL` | wd1-clear |
| Conjunto Arqueologico de Ñustahispana | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Cro-Magnon Rock Shelter | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cro-Magnon Rock Shelter | period_start | `-500` | `NULL` | wd1-clear |
| Cucuruzzu | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Cucuruzzu | period_start | `-1800` | `NULL` | wd1-clear |
| Cucuruzzu | site_type | `Megalithic structures` | `Fortress` | wd1-replace |
| Danbury, Essex | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Danbury, Essex | period_start | `-2000` | `NULL` | wd1-clear |
| Doctor's Gate | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Doctor's Gate | period_start | `1` | `NULL` | wd1-clear |
| Duggleby Howe | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Duggleby Howe | period_start | `-4500` | `NULL` | wd1-clear |
| Dzalisi | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Dzalisi | period_start | `1` | `-200` | wd1-replace |
| Earl Shilton | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Earl Shilton | period_start | `-500` | `NULL` | wd1-clear |
| Elyrus | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Elyrus | period_start | `-1500` | `NULL` | wd1-clear |
| Ermin Way | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ermin Way | period_start | `1` | `NULL` | wd1-clear |
| Eshkaft Salman | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Eshkaft Salman | period_start | `-3000` | `-1200` | wd1-replace |
| Finiq Archaeological Park | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Finiq Archaeological Park | period_start | `-1500` | `-500` | wd1-replace |
| Finiq Archaeological Park | source_url | `https://www.visitsaranda.net/see/phoenice-archaeological-par` | `https://en.wikipedia.org/wiki/Phoenice` | wd1-replace |
| Fortifications of Rhodes | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Fortifications of Rhodes | period_start | `-1500` | `-400` | wd1-replace |
| Fushan Archaeological Site | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Fushan Archaeological Site | period_start | `-3000` | `NULL` | wd1-clear |
| Fushan Archaeological Site | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Great Dolmen of Dwasieden | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Great Dolmen of Dwasieden | period_start | `-4500` | `NULL` | wd1-clear |
| Helsby Hill Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Helsby Hill Fort | period_start | `-1000` | `NULL` | wd1-clear |
| House of Aion | site_type | `Megalithic structures` | `Residence/villa/farmhouse` | wd1-replace |
| Inca Uyo | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inca Uyo | period_start | `1000` | `NULL` | wd1-clear |
| Inca Uyo | site_type | `Megalithic structures` | `Temple` | wd1-replace |
| Ingá Stone | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ingá Stone | period_start | `-4000` | `NULL` | wd1-clear |
| Ivington Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ivington Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Jacket's Field Long Barrow | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Jacket's Field Long Barrow | period_start | `-4000` | `NULL` | wd1-clear |
| Kelly Rounds | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Kelly Rounds | period_start | `-500` | `NULL` | wd1-clear |
| Koviljkin grad | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Koviljkin grad | period_start | `1` | `NULL` | wd1-clear |
| Koviljkin grad | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Kuntur Wasi | site_type | `Temple complex` | `NULL` | wd1-clear |
| Land of Tema | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Land of Tema | period_start | `-1500` | `NULL` | wd1-clear |
| Long Low, Wetton | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Long Low, Wetton | period_start | `-4500` | `NULL` | wd1-clear |
| Lycia Rock Tombs | source_url | `https://www.atlasobscura.com/places/lycian-rock-tombs` | `https://explorelycia.com/lycian-rock-tombs` | wd1-replace |
| Metropolis Antik Kenti | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Metropolis Antik Kenti | period_start | `-4500` | `NULL` | wd1-clear |
| Miculla Petroglyphs | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Miculla Petroglyphs | period_start | `1` | `NULL` | wd1-clear |
| Nargiztapa | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Nargiztapa | period_start | `-3000` | `NULL` | wd1-clear |
| Nargiztapa | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Nebstone | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Nebstone | period_start | `-3000` | `NULL` | wd1-clear |
| Nebstone | site_type | `Geological interest` | `NULL` | wd1-clear |
| Nefertari Temple | site_type | `Temple complex` | `Temple` | wd1-replace |
| Neos Panteleimonas | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Neos Panteleimonas | period_start | `-1000` | `NULL` | wd1-clear |
| Nether Denton | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Nether Denton | period_start | `1` | `NULL` | wd1-clear |
| Noorpur Stupas | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Noorpur Stupas | period_start | `-500` | `NULL` | wd1-clear |
| Noorpur Stupas | site_type | `Temple complex` | `NULL` | wd1-clear |
| Old Sarum | period_name | `4500 - 3000 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Old Sarum | period_start | `-4500` | `-400` | wd1-replace |
| Ollantaytambo | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Ollantaytambo | period_start | `1000` | `NULL` | wd1-clear |
| Painted Rock Petroglyph Site | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Painted Rock Petroglyph Site | period_start | `1` | `NULL` | wd1-clear |
| Palazzo a Mare | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Palazzo a Mare | period_start | `1` | `NULL` | wd1-clear |
| Palma di Montechiaro | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Palma di Montechiaro | period_start | `-1500` | `NULL` | wd1-clear |
| Panamá Viejo | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Panamá Viejo | period_start | `1000` | `NULL` | wd1-clear |
| Piscina Mirabilis | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Piscina Mirabilis | period_start | `-500` | `NULL` | wd1-clear |
| Pont Serme | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pont Serme | period_start | `1` | `NULL` | wd1-clear |
| Pozzo Sacro del Predio Canopoli | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Pozzo Sacro del Predio Canopoli | period_start | `-3000` | `NULL` | wd1-clear |
| Pozzo Sacro del Predio Canopoli | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Presa-Tusiu | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Presa-Tusiu | period_start | `-4000` | `NULL` | wd1-clear |
| Privlaka, Vukovar-Syrmia County | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Privlaka, Vukovar-Syrmia County | period_start | `-500` | `NULL` | wd1-clear |
| Quinkan Rock Art | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Quinkan Rock Art | period_start | `-25000` | `NULL` | wd1-clear |
| Ratae Corieltauvorum | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Ratae Corieltauvorum | period_start | `-200` | `NULL` | wd1-clear |
| Raw Dykes | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Raw Dykes | period_start | `1` | `NULL` | wd1-clear |
| Roman Thermae of Maximinus | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Roman Thermae of Maximinus | period_start | `-500` | `NULL` | wd1-clear |
| Roman Villa of Vilares | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Villa of Vilares | period_start | `1` | `NULL` | wd1-clear |
| Sanctuary of Asclepius, Epidaurus | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Sanctuary of Asclepius, Epidaurus | period_start | `-500` | `-600` | wd1-replace |
| Sirmium | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Sirmium | period_start | `-500` | `NULL` | wd1-clear |
| Sitio Arqueológico Altar de Los Sacrificios | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Sitio Arqueológico Altar de Los Sacrificios | period_start | `1` | `NULL` | wd1-clear |
| Skrzydłowo, Pomeranian Voivodeship | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Skrzydłowo, Pomeranian Voivodeship | period_start | `-1500` | `NULL` | wd1-clear |
| Stane Street, Colchester | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Stane Street, Colchester | period_start | `1` | `NULL` | wd1-clear |
| Talaja Caves | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Talaja Caves | period_start | `-500` | `NULL` | wd1-clear |
| Tamarindito | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tamarindito | period_start | `1` | `NULL` | wd1-clear |
| Tamarindito | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Taqrachullu | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Taqrachullu | period_start | `1` | `NULL` | wd1-clear |
| Taqrachullu | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Thor's Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Thor's Cave | period_start | `-9650` | `NULL` | wd1-clear |
| Thracian Tomb of Aleksandrovo | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Thracian Tomb of Aleksandrovo | period_start | `1` | `-400` | wd1-replace |
| Tipitarillo Yacata | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tipitarillo Yacata | period_start | `250` | `NULL` | wd1-clear |
| Tipón | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Tipón | period_start | `1000` | `NULL` | wd1-clear |
| Trethevy Quoit | site_type | `Megalithic structures` | `Dolmen` | wd1-replace |
| Uyu Uyu | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Uyu Uyu | period_start | `1200` | `NULL` | wd1-clear |
| Uyu Uyu | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Vindomora | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Vindomora | period_start | `1` | `NULL` | wd1-clear |
| Wat's Dyke | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wat's Dyke | period_start | `1` | `NULL` | wd1-clear |
| Whetstones Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Whetstones Stone Circle | period_start | `-4000` | `NULL` | wd1-clear |
| Wraxall Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wraxall Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Wraxall Camp | site_type | `Earthwork` | `NULL` | wd1-clear |
| Xtojil Cenote | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Xtojil Cenote | period_start | `250` | `NULL` | wd1-clear |
| Çatıören | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Çatıören | period_start | `-500` | `NULL` | wd1-clear |
| Çatıören | site_type | `Polygonal masonry` | `Archaeological site` | wd1-replace |
| Čertova pec | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Čertova pec | period_start | `-37000` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Amphitheatre of Capua | lat | `coordinates-unresolved` | Only Wikipedia prints a point for the amphitheatre of Capua; no independent second source. |
| Colosso di Ramses II | lat | `coordinates-unresolved` | No two independent sources give a point for this colossus. |
| Nefertari Temple | lat | `coordinates-unresolved` | No two independent sources give a point for the small temple at Abu Simbel. |
| Jacket's Field Long Barrow | lat | `coordinates-unresolved` | Wikipedia gives 51.209500, 0.909193 and the Megalithic Portal prints exactly the same figures to six decimals, so it app |
| Chevdar | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent source with a point was found. |
| Presa-Tusiu | lat | `coordinates-unresolved` | Neither Wikipedia nor Wikidata nor the excavation reports give a point for Presa-Tusiu; no source confirms the stored po |
| Tipitarillo Yacata | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point for the Tipitarillo yacata; no second independent source was found. |
| Privlaka, Vukovar-Syrmia County | lat | `coordinates-unresolved` | Only Wikipedia (English and Croatian, one family) gives a point for Privlaka; no independent source. |
| Aké (Yucatan) | lat | `coordinates-unresolved` | Only Mysteria prints a point for Aké; no independent second source. |
| Pozzo Sacro del Predio Canopoli | lat | `coordinates-unresolved` | No source prints a point for the holy well of Predio Canopoli. |
| Land of Tema | lat | `coordinates-unresolved` | Only Wikipedia gives a point for the Land of Tema; no second independent source was found. |
| Fushan Archaeological Site | lat | `coordinates-unresolved` | No source found quotes coordinates for the Fushan site. |
| Ali Murad Mound | lat | `coordinates-unresolved` | No source found gives a point for the Ali Murad mound. |
| Noorpur Stupas | lat | `coordinates-unresolved` | No source found gives a point for the Noorpur stupas. |
| Xtojil Cenote | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point for Xtojil; no second independent source was found. |
| Lycia Rock Tombs | lat | `coordinates-unresolved` | 'Lycia Rock Tombs' names the rock tombs spread across Lycia; no source gives one point for them. |
| Doctor's Gate | lat | `coordinates-unresolved` | Doctor's Gate is a Roman road running between Glossop and Brough-on-Noe; no source gives one point for it, so no two sou |
| House of Aion | lat | `coordinates-unresolved` | No two independent sources give a point for the House of Aion; Wikipedia's search hit is the whole city of Nea Paphos. |
| Allahdino | lat | `coordinates-unresolved` | No source found gives a point for Allahdino. |
| Finiq Archaeological Park | lat | `coordinates-unresolved` | Only Wikipedia prints a point for Phoenice (39.91333 N 20.05778 E); no independent source with coordinates was found. |
| Cerro De Trincheras | lat | `coordinates-unresolved` | Only Wikipedia's point for the modern town of Trincheras is found, 0.75 km off; no source gives a point for the hill sit |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s019-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s019 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
