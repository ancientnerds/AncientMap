# WD1 fields-wd1-2026-09-26d-s012: plan

Built 2026-09-29T15:38:49+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s012`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s012:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 211 |
| sites_written | 100 |
| refused | 23 |
| cells:period_name | 91 |
| cells:period_start | 91 |
| cells:site_type | 26 |
| cells:source_url | 3 |
| refused:coordinates-unresolved | 23 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Achilleion, Thessaly | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Ancient City of Blanda | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Ancient City of Blanda | period_start | `-500` | `-600` | wd1-replace |
| Anta do Alto da Toupeira | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Anta do Alto da Toupeira | period_start | `-4000` | `NULL` | wd1-clear |
| Apodoulou | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Apodoulou | period_start | `-4000` | `-1950` | wd1-replace |
| Apodoulou | site_type | `Residence/villa/farmhouse` | `Settlement` | wd1-replace |
| Ashleys Copse | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ashleys Copse | period_start | `-1500` | `NULL` | wd1-clear |
| Ashleys Copse | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Ballinran Court Tomb | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ballinran Court Tomb | period_start | `-4000` | `NULL` | wd1-clear |
| Banoštor | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Banoštor | period_start | `-500` | `NULL` | wd1-clear |
| Bema | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bema | period_start | `-1500` | `NULL` | wd1-clear |
| Bema | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Berry Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Berry Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Bojjanna Konda | site_type | `Temple complex` | `Cave Structures` | wd1-replace |
| Cadbury Castle, Devon | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cadbury Castle, Devon | period_start | `-1000` | `NULL` | wd1-clear |
| Caer Bran | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Caer Bran | period_start | `-1500` | `-2000` | wd1-replace |
| Caer Bran | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Camboglanna | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Camboglanna | period_start | `1` | `NULL` | wd1-clear |
| Carfury Standing Stone | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Carfury Standing Stone | period_start | `1` | `NULL` | wd1-clear |
| Castle Head, Devon | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castle Head, Devon | period_start | `-1000` | `NULL` | wd1-clear |
| Castro of Castelo Velho | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Castro of Castelo Velho | period_start | `-4000` | `NULL` | wd1-clear |
| Catacombs of Malta | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Catacombs of Malta | period_start | `-300` | `201` | wd1-replace |
| Catacombs of Malta | site_type | `Temple complex` | `Burial` | wd1-replace |
| Cave of Los Aviones | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cave of Los Aviones | period_start | `-115000` | `NULL` | wd1-clear |
| Chelmsford | period_name | `4500 - 3000 BC` | `1 - 500 AD` | wd1-derive-period-name |
| Chelmsford | period_start | `-4500` | `60` | wd1-replace |
| Chitinamit | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Chitinamit | period_start | `1` | `NULL` | wd1-clear |
| Chitinamit | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Coffin Stone | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Coffin Stone | period_start | `-4500` | `NULL` | wd1-clear |
| Dağlı Kalesi | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dağlı Kalesi | period_start | `100` | `NULL` | wd1-clear |
| Dead Woman's Ditch | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Dead Woman's Ditch | period_start | `-5000` | `NULL` | wd1-clear |
| Deir el-Bahari | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Deir el-Bahari | period_start | `-500` | `-2061` | wd1-replace |
| Deir el-Bahari | site_type | `Necropolis/tombs complex` | `Temple complex` | wd1-replace |
| Dolmen de la Pastora | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Dolmen de la Pastora | period_start | `-4000` | `-3000` | wd1-replace |
| Dosariyah | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Fairy Toot | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Fairy Toot | period_start | `-4000` | `NULL` | wd1-clear |
| Gib Hill | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Gib Hill | period_start | `-8000` | `NULL` | wd1-clear |
| Grimsbury Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Grimsbury Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Hadži-Prodan's Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Hadži-Prodan's Cave | period_start | `-50000` | `NULL` | wd1-clear |
| Harrow Hill, West Sussex | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Harrow Hill, West Sussex | period_start | `-4500` | `NULL` | wd1-clear |
| Horse Pool Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Horse Pool Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Hoyo Negro Cenote | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Hoyo Negro Cenote | period_start | `-11000` | `NULL` | wd1-clear |
| Hualpayunca | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Hualpayunca | period_start | `1` | `NULL` | wd1-clear |
| Hundersingen | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Hundersingen | period_start | `-1500` | `NULL` | wd1-clear |
| Hybla Gereatis | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Hybla Gereatis | period_start | `-500` | `NULL` | wd1-clear |
| Inka Murata | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inka Murata | period_start | `1400` | `NULL` | wd1-clear |
| Inka Murata | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Iskanwaya | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Iskanwaya | period_start | `1` | `NULL` | wd1-clear |
| Izapa | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Izapa | period_start | `-500` | `-1500` | wd1-replace |
| Jajce Mithraeum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Jajce Mithraeum | period_start | `1` | `NULL` | wd1-clear |
| Kamennyy Gorod | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Karabel Kilisesi | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Karabel Kilisesi | period_start | `1` | `NULL` | wd1-clear |
| Karabel Kilisesi | site_type | `Church/cathedral` | `NULL` | wd1-clear |
| Katzenberg Hillfort | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Kavousi Vronda | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Kavousi Vronda | period_start | `-2000` | `NULL` | wd1-clear |
| Laqaya | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Laqaya | period_start | `1100` | `NULL` | wd1-clear |
| Laqaya | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Llamachayuq | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Llamachayuq | period_start | `1000` | `NULL` | wd1-clear |
| Lousonna | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Lousonna | period_start | `1` | `-15` | wd1-replace |
| Luoyang | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Luoyang | period_start | `-1046` | `NULL` | wd1-clear |
| Luoyang | source_url | `https://www.britannica.com/place/Luoyang` | `https://en.wikipedia.org/wiki/Luoyang` | wd1-replace |
| Machrie Moor Stone Circles | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Machrie Moor Stone Circles | period_start | `-3000` | `-3500` | wd1-replace |
| Mais, Bowness | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Mais, Bowness | period_start | `1` | `NULL` | wd1-clear |
| Moel Hiraddug | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Moel Hiraddug | period_start | `-1500` | `NULL` | wd1-clear |
| Monagrillo - Archaeological Site | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Mortuary Temple of Hawara | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Mortuary Temple of Hawara | period_start | `-3000` | `NULL` | wd1-clear |
| Mounsey Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Mounsey Castle | period_start | `-1500` | `NULL` | wd1-clear |
| Newgate | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Newgate | period_start | `1` | `NULL` | wd1-clear |
| Oldberry Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Oldberry Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Osmantəpə | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Osmantəpə | period_start | `-6000` | `NULL` | wd1-clear |
| Osmantəpə | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Pacatnamu | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Pacatnamu | period_start | `500` | `NULL` | wd1-clear |
| Pichvnari | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Pichvnari | period_start | `-2000` | `NULL` | wd1-clear |
| Pir Shah Jurio | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Pir Shah Jurio | period_start | `-4500` | `NULL` | wd1-clear |
| Preston Candover Long Barrow | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Preston Candover Long Barrow | period_start | `-5000` | `NULL` | wd1-clear |
| Puente de Alcántara | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Puente de Alcántara | period_start | `-500` | `201` | wd1-replace |
| Puig de sa Morisca Archaeological Park | site_type | `Museum` | `City/town/settlement` | wd1-replace |
| Pyramid G1-b | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Pyramid G1-b | period_start | `-3000` | `NULL` | wd1-clear |
| Quarley Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Quarley Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Qunchupata, Ayacucho | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Qunchupata, Ayacucho | period_start | `600` | `NULL` | wd1-clear |
| Qunchupata, Ayacucho | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Rudston Roman Villa | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Rudston Roman Villa | period_start | `1` | `NULL` | wd1-clear |
| Ruthergate | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ruthergate | period_start | `100` | `NULL` | wd1-clear |
| Salzofen Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Salzofen Cave | period_start | `-65000` | `NULL` | wd1-clear |
| Sanctuary of Artemis, Brauron | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Sanctuary of Artemis, Brauron | period_start | `-2000` | `-900` | wd1-replace |
| Saticula | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Saticula | period_start | `-500` | `NULL` | wd1-clear |
| Selinunte Archaeological Park | source_url | `NULL` | `https://www.sicilia.info/en/trapani/selinunte-archaeological` | wd1-replace |
| Shoulsbury Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Shoulsbury Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Sidyma | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Sidyma | period_start | `-500` | `NULL` | wd1-clear |
| Sidyma | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Sillustani | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Sillustani | period_start | `500` | `NULL` | wd1-clear |
| Siponto | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Siponto | period_start | `-500` | `NULL` | wd1-clear |
| Siraj-ji-Takri | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Siraj-ji-Takri | period_start | `-500` | `NULL` | wd1-clear |
| Small Down Knoll | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Small Down Knoll | period_start | `-4500` | `NULL` | wd1-clear |
| Sokhta Koh | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Sokhta Koh | period_start | `-3000` | `NULL` | wd1-clear |
| Stanwix | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Stanwix | period_start | `1` | `NULL` | wd1-clear |
| Stripple Stones | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Stripple Stones | period_start | `-4500` | `NULL` | wd1-clear |
| Sudha Gad Fort | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Sycurium | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Sycurium | period_start | `-1500` | `NULL` | wd1-clear |
| Taghlar Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Taghlar Cave | period_start | `-500` | `NULL` | wd1-clear |
| Tahtzibichen Labyrinth | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tahtzibichen Labyrinth | period_start | `100` | `NULL` | wd1-clear |
| Tahtzibichen Labyrinth | site_type | `Temple complex` | `NULL` | wd1-clear |
| Tampukancha | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Tampukancha | period_start | `1000` | `NULL` | wd1-clear |
| Tampukancha | site_type | `Temple complex` | `NULL` | wd1-clear |
| Taxila | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Taxila | period_start | `-3000` | `NULL` | wd1-clear |
| Temple of Athena Lindia | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Temple of Athena Lindia | period_start | `-500` | `-600` | wd1-replace |
| Tyberissos (Tubure) Kaya Mezarı | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Tyberissos (Tubure) Kaya Mezarı | period_start | `1` | `-400` | wd1-replace |
| Tyberissos (Tubure) Kaya Mezarı | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Tyberissos (Tubure) Kaya Mezarı | source_url | `https://www.arpaboyuyol.com/kekova-ucagiz-koyu-gezi-rehberi/` | `https://kulturenvanteri.com/en/yer/tyberissos-kaya-mezari/` | wd1-replace |
| Umm es-Sawan Ancient Basalt Quarry | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Umm es-Sawan Ancient Basalt Quarry | period_start | `-3000` | `NULL` | wd1-clear |
| Usnu, Huánuco | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Usnu, Huánuco | period_start | `1` | `NULL` | wd1-clear |
| Usnu, Huánuco | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Uzerliktapa | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Uzerliktapa | period_start | `-3000` | `NULL` | wd1-clear |
| Villa Boscoreale | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Villa Boscoreale | period_start | `1` | `-40` | wd1-replace |
| Waqutu | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Waqutu | period_start | `1400` | `NULL` | wd1-clear |
| West Lanyon Quoit | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| West Lanyon Quoit | period_start | `-4500` | `NULL` | wd1-clear |
| Willendorf in der Wachau | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Willendorf in der Wachau | period_start | `-500` | `NULL` | wd1-clear |
| Windmill Tump | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Windmill Tump | period_start | `-4500` | `NULL` | wd1-clear |
| Woodbury, Stoke Fleming | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Woodbury, Stoke Fleming | period_start | `-1000` | `NULL` | wd1-clear |
| Zapote Bobal | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Zapote Bobal | period_start | `500` | `NULL` | wd1-clear |
| Zapote Bobal | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Ġebel ġol-Baħar | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ġebel ġol-Baħar | period_start | `1` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Bojjanna Konda | lat | `coordinates-unresolved` | No source prints a point for Bojjannakonda; Wikipedia gives none. |
| Luoyang | lat | `coordinates-unresolved` | Only Wikipedia gives a point for Luoyang; no independent source with coordinates was found. |
| Osmantəpə | lat | `coordinates-unresolved` | Only Wikipedia gives a point for Osmantepe; no independent source with coordinates was found. |
| Sidyma | lat | `coordinates-unresolved` | No source found quotes coordinates for Sidyma; the Wikipedia hit is the district of Seydikemer. |
| Selinunte Archaeological Park | lat | `coordinates-unresolved` | Only Wikipedia's point for Selinunte is found, 1.1 km from the stored point; no second source gives a point for the park |
| Tyberissos (Tubure) Kaya Mezarı | lat | `coordinates-unresolved` | No source found quotes coordinates for the Tyberissos rock tomb. |
| Sillustani | lat | `coordinates-unresolved` | Only Spanish Wikipedia gives a point for Sillustani (0.03 km from the stored one); no second independent source was foun |
| Cave of Los Aviones | lat | `coordinates-unresolved` | Only Wikipedia (English and Spanish) and Wikidata, one source family, give a point for the cave; no second independent s |
| Puente de Alcántara | lat | `coordinates-unresolved` | Only Wikipedia (English and Spanish) and Wikidata, one source family, give a point; no independent second source quotes  |
| Siraj-ji-Takri | lat | `coordinates-unresolved` | No source found gives a point for Siraj-ji-Takri. |
| Bema | lat | `coordinates-unresolved` | The entry names only the generic "Bema" (Wikipedia's article on the orator's platform in general); no source identifies  |
| Ruthergate | lat | `coordinates-unresolved` | No source prints a point for Ruthergate; Wikipedia gives none. |
| Hoyo Negro Cenote | lat | `coordinates-unresolved` | No source found gives coordinates for the Hoyo Negro cave. |
| Tahtzibichen Labyrinth | lat | `coordinates-unresolved` | Only Megalithic Portal pages mention the Tahtzibichen labyrinth, and none gives its own point; no independent source was |
| Temple of Athena Lindia | lat | `coordinates-unresolved` | Only Wikidata gives a point for the temple; no independent source gives one. |
| Catacombs of Malta | lat | `coordinates-unresolved` | The entry is the catacombs of Malta in general; no source gives one point for them. |
| Karabel Kilisesi | lat | `coordinates-unresolved` | No source found quotes coordinates for Karabel Kilisesi. |
| Kamennyy Gorod | lat | `coordinates-unresolved` | No source found gives a point for Kamennyy Gorod. |
| Waqutu | lat | `coordinates-unresolved` | No source found gives a point for Waqutu. |
| Inka Murata | lat | `coordinates-unresolved` | The Wikipedia article prints no point and no independent source with coordinates was found. |
| Umm es-Sawan Ancient Basalt Quarry | lat | `coordinates-unresolved` | The only point found (MEDOMED) is 27 km away; no source gives the quarry's point. |
| Tampukancha | lat | `coordinates-unresolved` | No source found gives a point for Tampukancha. |
| Mortuary Temple of Hawara | lat | `coordinates-unresolved` | No source gives a point for the mortuary temple at Hawara; Wikipedia's search hit is the generic article on mortuary tem |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s012-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s012 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
