# WD1 fields-wd1-2026-09-26d-s007: plan

Built 2026-09-29T15:34:55+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s007`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s007:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 206 |
| sites_written | 99 |
| refused | 23 |
| cells:period_name | 86 |
| cells:period_start | 86 |
| cells:site_type | 27 |
| cells:source_url | 7 |
| refused:coordinates-unresolved | 23 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Alabanda | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Alabanda | period_start | `-1500` | `NULL` | wd1-clear |
| Alogonia - Town | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Alogonia - Town | period_start | `-1000` | `NULL` | wd1-clear |
| Archaeological Dolmens of Antequera | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Archaeological Dolmens of Antequera | period_start | `-5000` | `-3800` | wd1-replace |
| Archaeological Dolmens of Antequera | source_url | `https://whc.unesco.org/en/list/1501/` | `https://en.wikipedia.org/wiki/Antequera_Dolmens_Site` | wd1-replace |
| Archaeological Ensemble of Tárraco | site_type | `Wall` | `NULL` | wd1-clear |
| Archaeological Site of Mycenae | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Archaeological Site of Mycenae | period_start | `-3000` | `-5000` | wd1-replace |
| Archaeological Site of Mycenae | site_type | `Megalithic walls` | `Citadel` | wd1-replace |
| Asclepieion of Pergamon | source_url | `http://www.my-favourite-planet.de/english/middle-east/turkey` | `https://turkisharchaeonews.net/site/asclepieion-pergamon` | wd1-replace |
| Awkimarka, Huánuco | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Awkimarka, Huánuco | period_start | `1400` | `NULL` | wd1-clear |
| Awkimarka, Huánuco | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Axlor | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Axlor | period_start | `-85000` | `NULL` | wd1-clear |
| Barbrook One | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Barbrook One | period_start | `-4500` | `-2000` | wd1-replace |
| Barton-le-Clay | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Barton-le-Clay | period_start | `-1000` | `NULL` | wd1-clear |
| Bejsebakke | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Bejsebakke | period_start | `-4500` | `NULL` | wd1-clear |
| Bincknoll Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bincknoll Castle | period_start | `-1500` | `NULL` | wd1-clear |
| Broadbury Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Broadbury Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Bucknowle Farm | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Bucknowle Farm | period_start | `1` | `NULL` | wd1-clear |
| Bury Camp | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Bury Camp | period_start | `-500` | `NULL` | wd1-clear |
| Caer Gwrtheyrn | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Caer Gwrtheyrn | period_start | `-1500` | `NULL` | wd1-clear |
| Castell Henllys | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castell Henllys | period_start | `-1500` | `NULL` | wd1-clear |
| Cave of Salemas | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cave of Salemas | period_start | `-500` | `NULL` | wd1-clear |
| Celemantia | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Celemantia | period_start | `1` | `NULL` | wd1-clear |
| Chuping Archaeological Site | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Chuping Archaeological Site | period_start | `-4000` | `NULL` | wd1-clear |
| Cuello | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Córdoba, Spain | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Córdoba, Spain | period_start | `-1500` | `NULL` | wd1-clear |
| Deepcar | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Deepcar | period_start | `-5000` | `NULL` | wd1-clear |
| Duloe Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Duloe Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| El Perú | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| El Perú | period_start | `-1500` | `-500` | wd1-replace |
| El Tortuguero | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| El Tortuguero | period_start | `500` | `NULL` | wd1-clear |
| Elborough Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Elborough Hill | period_start | `-1500` | `NULL` | wd1-clear |
| Etruscan Pyramid of Bomarzo | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Etruscan Pyramid of Bomarzo | period_start | `-1500` | `NULL` | wd1-clear |
| Etruscan Pyramid of Bomarzo | site_type | `Pyramid complex` | `NULL` | wd1-clear |
| Etruscan Pyramid of Bomarzo | source_url | `https://www.atlasobscura.com/places/etruscan-pyramid-bomarzo` | `https://www.thearchaeologist.org/blog/the-etruscan-pyramid-o` | wd1-replace |
| Frohnleiten | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Frohnleiten | period_start | `1` | `NULL` | wd1-clear |
| Funzie Girt | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Funzie Girt | period_start | `-2000` | `NULL` | wd1-clear |
| Glanum | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Glanum | period_start | `-1500` | `NULL` | wd1-clear |
| Goyet Caves | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Goyet Caves | period_start | `-35000` | `NULL` | wd1-clear |
| Grzybowa Góra | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Grzybowa Góra | period_start | `-11000` | `NULL` | wd1-clear |
| Hadda | site_type | `City/town/settlement` | `Monastery` | wd1-replace |
| Havránok | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Heraion at Foce del Sele | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Heraion at Foce del Sele | period_start | `-500` | `-600` | wd1-replace |
| Hob Hurst's House | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Hob Hurst's House | period_start | `-2000` | `NULL` | wd1-clear |
| Honanki Heritage Site | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Honanki Heritage Site | period_start | `-3000` | `-5000` | wd1-replace |
| House of Taga | period_name | `< 4500 BC` | `500 - 1000 AD` | wd1-derive-period-name |
| House of Taga | period_start | `-10000` | `900` | wd1-replace |
| Karabal Belören Demre Antalya | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Karabal Belören Demre Antalya | period_start | `500` | `NULL` | wd1-clear |
| Karabal Belören Demre Antalya | site_type | `Monastery` | `NULL` | wd1-clear |
| Karabal Belören Demre Antalya | source_url | `https://www.helpmecovid.com/tr/416126_karabal-beloren-demre-` | `NULL` | wd1-clear |
| Kintradwell Broch | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kintradwell Broch | period_start | `-1500` | `NULL` | wd1-clear |
| Kintradwell Broch | site_type | `Minaret/tower` | `NULL` | wd1-clear |
| Kinver Edge Hillfort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kinver Edge Hillfort | period_start | `-1500` | `NULL` | wd1-clear |
| Knook Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Knook Castle | period_start | `-1500` | `NULL` | wd1-clear |
| Ksar el Kaoua | site_type | `Castle/palace` | `Military` | wd1-replace |
| La Pintada | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| La Pintada | period_start | `500` | `NULL` | wd1-clear |
| Lake Bolac Stone Arrangement | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Lake Bolac Stone Arrangement | period_start | `-3000` | `NULL` | wd1-clear |
| Lauriacum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Lauriacum | period_start | `1` | `NULL` | wd1-clear |
| Limyra Antik Kenti | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Limyra Antik Kenti | period_start | `-1500` | `-500` | wd1-replace |
| Lindholm Høje | site_type | `City/town/settlement` | `Burial` | wd1-replace |
| Lopen Roman Mosaic | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Lopen Roman Mosaic | period_start | `1` | `NULL` | wd1-clear |
| Marcinków, Świętokrzyskie Voivodeship | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Marcinków, Świętokrzyskie Voivodeship | period_start | `-11000` | `NULL` | wd1-clear |
| Maumbury Rings | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Maumbury Rings | period_start | `-4500` | `-2500` | wd1-replace |
| Menosgada | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Menosgada | period_start | `-500` | `NULL` | wd1-clear |
| Molloko | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Molloko | period_start | `1` | `NULL` | wd1-clear |
| Montana | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Montana | period_start | `1` | `NULL` | wd1-clear |
| Mudgegonga Rock Shelter | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Mudgegonga Rock Shelter | period_start | `-3000` | `NULL` | wd1-clear |
| Mulri Hills | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Mulri Hills | period_start | `1` | `NULL` | wd1-clear |
| Mulri Hills | site_type | `Geological interest` | `NULL` | wd1-clear |
| Museum of the Royal Tombs of Aigai, Vergina | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Museum of the Royal Tombs of Aigai, Vergina | period_start | `-1100` | `NULL` | wd1-clear |
| Mycenae | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Mycenae | period_start | `-2000` | `-5000` | wd1-replace |
| Nine Maidens Stone Row | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Nine Maidens Stone Row | period_start | `-4000` | `NULL` | wd1-clear |
| Oldbury Rock Shelters | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Oldbury Rock Shelters | period_start | `-500` | `NULL` | wd1-clear |
| Ovçular Tepesi | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Ovçular Tepesi | period_start | `-5000` | `-4400` | wd1-replace |
| Pacbitun | site_type | `Pyramid complex` | `NULL` | wd1-clear |
| Parque Arqueológico Uaxactun | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Parque Arqueológico Uaxactun | source_url | `https://www.britannica.com/place/Uaxactun` | `https://en.wikipedia.org/wiki/Uaxactun` | wd1-replace |
| Pentre Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Pentre Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Petriana | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Petriana | period_start | `1` | `NULL` | wd1-clear |
| Pogradec Castle | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Pogradec Castle | period_start | `-1500` | `-500` | wd1-replace |
| Presaddfed Burial Chamber | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Presaddfed Burial Chamber | period_start | `-5000` | `-4000` | wd1-replace |
| Puente Romano, Mérida | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Puente Romano, Mérida | period_start | `1` | `-25` | wd1-replace |
| Qasr Sagha Temple | site_type | `Temple complex` | `Temple` | wd1-replace |
| Quillcay Machay | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Quillcay Machay | period_start | `-900` | `NULL` | wd1-clear |
| Quillcay Machay | site_type | `Rock art` | `NULL` | wd1-clear |
| Ražanj | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Ražanj | period_start | `-500` | `NULL` | wd1-clear |
| Remains of Roknia | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Remains of Roknia | period_start | `1` | `NULL` | wd1-clear |
| Remains of Roknia | site_type | `Megalithic stones` | `Necropolis` | wd1-replace |
| Remains of Roknia | source_url | `https://fr.wikipedia.org/wiki/Vestiges_de_Roknia` | `https://fr.wikipedia.org/wiki/N%C3%A9cropole_de_Roknia` | wd1-replace |
| Ringsbury Camp | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Ringsbury Camp | period_start | `-500` | `NULL` | wd1-clear |
| Roma Dönemi Agora Harabeleri | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Roma Dönemi Agora Harabeleri | period_start | `-500` | `NULL` | wd1-clear |
| Roma Dönemi Agora Harabeleri | site_type | `Forum` | `NULL` | wd1-clear |
| Roma Tiyatrosu | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roma Tiyatrosu | period_start | `150` | `NULL` | wd1-clear |
| Roma Tiyatrosu | site_type | `Theatre` | `NULL` | wd1-clear |
| Roman City of Deultum - Develtos | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Roman City of Deultum - Develtos | period_start | `-1500` | `NULL` | wd1-clear |
| Roman Column, York | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Roman Temple Temnin | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Temple Temnin | period_start | `1` | `NULL` | wd1-clear |
| Roman Temple Temnin | site_type | `Temple complex` | `NULL` | wd1-clear |
| Rouffignac Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Rouffignac Cave | period_start | `-11000` | `NULL` | wd1-clear |
| Samsø | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Samsø | period_start | `-7000` | `NULL` | wd1-clear |
| Saraakallio Rock Paintings | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Saraakallio Rock Paintings | period_start | `-4500` | `NULL` | wd1-clear |
| Sieben Steinhäuser | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Sieben Steinhäuser | period_start | `-4500` | `-3000` | wd1-replace |
| Stokeleigh Camp | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Stokeleigh Camp | period_start | `-500` | `NULL` | wd1-clear |
| Te Pito O Te Henua | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Te Pito O Te Henua | period_start | `1100` | `NULL` | wd1-clear |
| Te Pito O Te Henua | site_type | `Magnetic anomaly` | `NULL` | wd1-clear |
| Tempio di Zeus Olympios | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tempio di Zeus Olympios | period_start | `-500` | `NULL` | wd1-clear |
| Temple of Apollo, Melite | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Temple of Apollo, Melite | period_start | `1` | `NULL` | wd1-clear |
| Temple of Segesta | site_type | `Temple complex` | `Temple` | wd1-replace |
| Temple of Segesta | source_url | `https://study.com/academy/lesson/doric-temple-of-segesta-his` | `https://culturalheritageonline.com/places/temple-of-segesta-` | wd1-replace |
| The Long Lane, Derbyshire | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| The Long Lane, Derbyshire | period_start | `1` | `NULL` | wd1-clear |
| The Pipers | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| The Pipers | period_start | `-4000` | `NULL` | wd1-clear |
| Tomb of Funeral Beds - Necropolis of Banditaccia | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Tomb of Funeral Beds - Necropolis of Banditaccia | period_start | `-700` | `NULL` | wd1-clear |
| Tomb of Funeral Beds - Necropolis of Banditaccia | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Treva | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Treva | period_start | `1` | `NULL` | wd1-clear |
| Vathypetro | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Vathypetro | period_start | `-4500` | `-1580` | wd1-replace |
| Velika Humka | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Velika Humka | period_start | `-700` | `NULL` | wd1-clear |
| Villa of Theseus | site_type | `Megalithic structures` | `Residence/villa/farmhouse` | wd1-replace |
| Waraqu Urqu | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Waraqu Urqu | period_start | `1000` | `NULL` | wd1-clear |
| Waraqu Urqu | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Wilbury Hill Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wilbury Hill Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Wilca | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Wilca | period_start | `1000` | `NULL` | wd1-clear |
| Wilca | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Wraxall, Somerset | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wraxall, Somerset | period_start | `-1500` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Karabal Belören Demre Antalya | lat | `coordinates-unresolved` | No source found quotes coordinates for the site. |
| Waraqu Urqu | lat | `coordinates-unresolved` | Wikipedia's point lies 20 km from the stored one; no two sources agree on a point for Waraqu Urqu. |
| Roma Dönemi Agora Harabeleri | lat | `coordinates-unresolved` | No source found quotes coordinates for a Roman agora at this point. |
| Villa of Theseus | lat | `coordinates-unresolved` | No two independent sources give a point for the Villa of Theseus; Wikipedia's search hit is the whole city of Nea Paphos |
| Montana | lat | `coordinates-unresolved` | No source gives a point for Montana; the stored point cannot be confirmed. |
| Archaeological Dolmens of Antequera | lat | `coordinates-unresolved` | Wikipedia's point lies 0.17 km and Cultural Heritage Online's 0.9 km from the stored one, but the two lie over 1 km apar |
| Kintradwell Broch | lat | `coordinates-unresolved` | No source found gives a point near the stored one; the Megalithic Portal's point lies 4.75 km away. |
| Etruscan Pyramid of Bomarzo | lat | `coordinates-unresolved` | No source prints a point for the Bomarzo pyramid. |
| Temple of Apollo, Melite | lat | `coordinates-unresolved` | Only Wikipedia prints a point for the Temple of Apollo at Melite; no independent second source. |
| Remains of Roknia | lat | `coordinates-unresolved` | The Megalithic Portal point is 0.6 km from the stored point but French Wikipedia's point is 3.8 km away, so no two indep |
| The Long Lane, Derbyshire | lat | `coordinates-unresolved` | No source prints a point for the Long Lane Roman road; Wikipedia gives none. |
| Parque Arqueológico Uaxactun | lat | `coordinates-unresolved` | Only Wikipedia gives a point for Uaxactun; no independent source gives one. |
| Mulri Hills | lat | `coordinates-unresolved` | No source found gives a point for the Mulri Hills. |
| Limyra Antik Kenti | lat | `coordinates-unresolved` | No source found quotes coordinates for Limyra; the Wikipedia hit is Ani, another site. |
| Treva | lat | `coordinates-unresolved` | Treva is known only from Ptolemy and the Roman campaign accounts; no source fixes its location, so the stored point (cen |
| Ksar el Kaoua | lat | `coordinates-unresolved` | Only French Wikipedia prints a point (35 52 00 N, 1 07 00 E); no independent source with coordinates was found. |
| Roma Tiyatrosu | lat | `coordinates-unresolved` | No source found quotes coordinates for a Roman theatre at this point. |
| The Ancient Lycian Mezarı2 | lat | `coordinates-unresolved` | No source found quotes coordinates for this tomb group. |
| Honanki Heritage Site | lat | `coordinates-unresolved` | No source found quotes coordinates for Honanki. |
| Te Pito O Te Henua | lat | `coordinates-unresolved` | No source gives a point for Te Pito o te Henua. |
| Tomb of Funeral Beds - Necropolis of Banditaccia | lat | `coordinates-unresolved` | No source prints a point for this tomb. |
| Roman Temple Temnin | lat | `coordinates-unresolved` | Only Wikipedia's point for the village of Temnin el-Foka is found, 1.3 km off; no source gives a point for a temple. |
| Alogonia - Town | lat | `coordinates-unresolved` | The site of ancient Alagonia is uncertain: ToposText places it near Anatoliko (36.9556, 22.2612, low confidence), some 4 |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s007-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s007 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
