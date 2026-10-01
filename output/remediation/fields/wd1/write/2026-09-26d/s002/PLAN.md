# WD1 fields-wd1-2026-09-26d-s002: plan

Built 2026-09-29T15:29:44+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s002`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s002:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 222 |
| sites_written | 100 |
| refused | 25 |
| cells:period_name | 94 |
| cells:period_start | 94 |
| cells:site_type | 28 |
| cells:source_url | 6 |
| refused:coordinates-unresolved | 25 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Abritus | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Abritus | period_start | `1` | `-500` | wd1-replace |
| Aigai Ancient City | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Aigai Ancient City | period_start | `-500` | `-800` | wd1-replace |
| Alampra | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Alampra | period_start | `-3000` | `NULL` | wd1-clear |
| Alikomektepe | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Alikomektepe | period_start | `-5000` | `NULL` | wd1-clear |
| Alikomektepe | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Almsworthy Common | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Almsworthy Common | period_start | `-4500` | `NULL` | wd1-clear |
| Ancient City of Selge | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Ancient City of Selge | period_start | `-3000` | `NULL` | wd1-clear |
| Ancient City of Telmessos | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ancient City of Telmessos | period_start | `-1500` | `NULL` | wd1-clear |
| Araltobe Kurgan | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Araltobe Kurgan | period_start | `-500` | `NULL` | wd1-clear |
| Archaeological Site of Olympia | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Archaeological Site of Olympia | period_start | `-4500` | `NULL` | wd1-clear |
| Archaeological Site of Olympia | source_url | `https://whc.unesco.org/en/list/517/` | `https://en.wikipedia.org/wiki/Olympia,_Greece` | wd1-replace |
| Aya Muqu | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Aya Muqu | period_start | `800` | `NULL` | wd1-clear |
| Aya Muqu | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Backwell Hillfort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Backwell Hillfort | period_start | `-1000` | `NULL` | wd1-clear |
| Balksbury | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Balksbury | period_start | `-3000` | `NULL` | wd1-clear |
| Baqirha | site_type | `Megalithic stones` | `City/town/settlement` | wd1-replace |
| Berth Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Berth Hill | period_start | `-1500` | `NULL` | wd1-clear |
| Bilbao | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Bilbao | period_start | `500` | `NULL` | wd1-clear |
| Bilbao | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Bosnian Pyramid of the Moon | site_type | `Geological interest` | `Natural feature` | wd1-replace |
| Brewer's Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Brewer's Castle | period_start | `-1500` | `NULL` | wd1-clear |
| Burra Ness Broch | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Burra Ness Broch | period_start | `-1500` | `NULL` | wd1-clear |
| Carisbrook Stone Arrangement | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Carisbrook Stone Arrangement | period_start | `1` | `NULL` | wd1-clear |
| Carisbrook Stone Arrangement | site_type | `Stone circle` | `NULL` | wd1-clear |
| Castell Caer Seion | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Castell Caer Seion | period_start | `-500` | `NULL` | wd1-clear |
| Castle Naze | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castle Naze | period_start | `-1000` | `NULL` | wd1-clear |
| Castle Naze | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Cave of Pedra Furada | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Cave of Pedra Furada | period_start | `-4000` | `NULL` | wd1-clear |
| Centro Arqueológico de Chinchero | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Centro Arqueológico de Chinchero | period_start | `1000` | `NULL` | wd1-clear |
| Centro Arqueológico de Chinchero | site_type | `Polygonal masonry` | `NULL` | wd1-clear |
| Chacamarca Historic Sanctuary | period_name | `1500+ AD` | `NULL` | wd1-derive-period-name |
| Chacamarca Historic Sanctuary | period_start | `1974` | `NULL` | wd1-clear |
| Chersonesus | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Chersonesus | period_start | `-1500` | `-422` | wd1-replace |
| Cloggs Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cloggs Cave | period_start | `-17000` | `NULL` | wd1-clear |
| Coggabata | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Coggabata | period_start | `1` | `NULL` | wd1-clear |
| Conchalito | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Conchalito | period_start | `-1500` | `-2300` | wd1-replace |
| Conchalito | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Condorcaga | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Condorcaga | period_start | `-1500` | `NULL` | wd1-clear |
| Condorcaga | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Cranon | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Cranon | period_start | `-2000` | `NULL` | wd1-clear |
| Curdon Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Curdon Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Dedoplis Mindori | site_type | `City/town/settlement` | `Temple complex` | wd1-replace |
| Densuș Church | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Densuș Church | period_start | `1` | `NULL` | wd1-clear |
| Dolmen de Bagneux | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Dolmen de Bagneux | period_start | `-3000` | `NULL` | wd1-clear |
| Emilianus - Stollen | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Emilianus - Stollen | period_start | `1` | `NULL` | wd1-clear |
| Endebjerg | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Endebjerg | period_start | `-4500` | `NULL` | wd1-clear |
| Guellayhuasin | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Guellayhuasin | period_start | `1` | `NULL` | wd1-clear |
| Guellayhuasin | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Hellenistic House | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Hellenistic House | period_start | `-500` | `NULL` | wd1-clear |
| Hellenistic House | site_type | `Megalithic structures` | `Residence/villa/farmhouse` | wd1-replace |
| Hochob | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Hochob | period_start | `500` | `NULL` | wd1-clear |
| Hollingbury Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Hollingbury Castle | period_start | `-1500` | `NULL` | wd1-clear |
| Hov Dås | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Hov Dås | period_start | `-4500` | `NULL` | wd1-clear |
| Hunnum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Hunnum | period_start | `1` | `NULL` | wd1-clear |
| Jordan Hill Roman Temple | site_type | `Temple complex` | `Temple` | wd1-replace |
| Kenko | source_url | `https://www.machupicchu.org/ruins/kenko.htm` | `https://en.wikipedia.org/wiki/Qenko` | wd1-replace |
| Knockmaree Dolmen | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Knockmaree Dolmen | period_start | `-4500` | `-3000` | wd1-replace |
| Kommos, Crete | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Kommos, Crete | period_start | `-4500` | `-2000` | wd1-replace |
| Korikos Antik Kenti | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Korikos Antik Kenti | period_start | `-500` | `NULL` | wd1-clear |
| Korikos Antik Kenti | source_url | `https://whc.unesco.org/en/tentativelists/5909/` | `https://turkiyeturizmansiklopedisi.com/korikos-orenyeri` | wd1-replace |
| Krimisa | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Krimisa | period_start | `-1500` | `NULL` | wd1-clear |
| La Corona | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| La Corona | period_start | `500` | `NULL` | wd1-clear |
| La Corona | site_type | `Settlement` | `City` | wd1-replace |
| La Roche-aux-Fées | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| La Roche-aux-Fées | period_start | `-4500` | `NULL` | wd1-clear |
| Lake Paliastomi | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Lake Paliastomi | period_start | `-1500` | `NULL` | wd1-clear |
| Lakkos | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Lakkos | period_start | `-4500` | `NULL` | wd1-clear |
| Lakkos | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Lakkos | source_url | `https://es.wikipedia.org/wiki/Lakkos` | `NULL` | wd1-clear |
| Las Cogotas | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Las Cogotas | period_start | `-2000` | `-1200` | wd1-replace |
| Le Regourdou | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Le Regourdou | period_start | `-68000` | `NULL` | wd1-clear |
| Los Pinchudos | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Los Pinchudos | period_start | `500` | `NULL` | wd1-clear |
| Mawk'ataray | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Mawk'ataray | period_start | `1000` | `NULL` | wd1-clear |
| Mawk'ataray | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Mixco Viejo | period_name | `500 - 1000 AD` | `1000 - 1500 AD` | wd1-derive-period-name |
| Mixco Viejo | period_start | `500` | `1101` | wd1-replace |
| Moel y Gaer, Rhosesmor | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Moel y Gaer, Rhosesmor | period_start | `-1500` | `NULL` | wd1-clear |
| Mortuary Temple of Amenhotep III | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Mortuary Temple of Amenhotep III | period_start | `-3000` | `NULL` | wd1-clear |
| Nagara (Ancient city) | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Nagara (Ancient city) | period_start | `1` | `NULL` | wd1-clear |
| Nashtifan Windmills | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Nashtifan Windmills | period_start | `500` | `NULL` | wd1-clear |
| Nashtifan Windmills | site_type | `Infrastructure` | `NULL` | wd1-clear |
| Nashtifan Windmills | source_url | `https://www.atlasobscura.com/places/nashtifan-windmills` | `https://untamediran.com/nashtifan-windmills` | wd1-replace |
| Nea Roumata Archaeological Site | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Nea Roumata Archaeological Site | period_start | `-3000` | `NULL` | wd1-clear |
| Nea Roumata Archaeological Site | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Oppidum Uetliberg | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Oppidum Uetliberg | period_start | `-500` | `NULL` | wd1-clear |
| Paradise Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Paradise Cave | period_start | `-60000` | `NULL` | wd1-clear |
| Perborough Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Perborough Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Poblat de Son Catlar | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Poblat de Son Catlar | period_start | `-3000` | `NULL` | wd1-clear |
| Poblat de Son Catlar | site_type | `Megalithic structures` | `City/town/settlement` | wd1-replace |
| Portfield Hillfort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Portfield Hillfort | period_start | `-1000` | `NULL` | wd1-clear |
| Praileaitz Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Praileaitz Cave | period_start | `-13500` | `NULL` | wd1-clear |
| Puka Urqu, Ayacucho | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Puka Urqu, Ayacucho | period_start | `1` | `NULL` | wd1-clear |
| Puka Urqu, Ayacucho | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Pyramid of Khentkaus II | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Pyramid of Khentkaus II | period_start | `-3000` | `NULL` | wd1-clear |
| Pyramid of Pepi II | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Pyramid of Pepi II | period_start | `-500` | `-2278` | wd1-replace |
| Qaqapatan | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Qaqapatan | period_start | `1` | `NULL` | wd1-clear |
| Qaqapatan | site_type | `Rock art` | `NULL` | wd1-clear |
| Rempstone Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Rempstone Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Rodhuish Common | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Rodhuish Common | period_start | `-1000` | `NULL` | wd1-clear |
| Roman Bridge of Catribana | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Bridge of Catribana | period_start | `1` | `NULL` | wd1-clear |
| Roman Temple-Deir El Aachaiyer | site_type | `Temple complex` | `Temple` | wd1-replace |
| Roman Temple-Deir El Aachaiyer | source_url | `https://www.megalithic.co.uk/article.php?sid=18023` | `https://wanderleb.com/wanderblog/deir-el-aachaiyer-temple` | wd1-replace |
| Rudston Monolith | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Rudston Monolith | period_start | `-4000` | `NULL` | wd1-clear |
| Rykeneld Street | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Rykeneld Street | period_start | `1` | `NULL` | wd1-clear |
| San Claudio | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| San Claudio | period_start | `-500` | `NULL` | wd1-clear |
| San Claudio | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Sandy, Bedfordshire | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Sandy, Bedfordshire | period_start | `-1000` | `NULL` | wd1-clear |
| Shovel Down | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Shovel Down | period_start | `-4500` | `NULL` | wd1-clear |
| Smedmore Hill Settlement | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Smedmore Hill Settlement | period_start | `-1500` | `NULL` | wd1-clear |
| South Street Barrow | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| South Street Barrow | period_start | `-4500` | `NULL` | wd1-clear |
| Stanton Drew Stone Circles | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Stanton Drew Stone Circles | period_start | `-4500` | `-3000` | wd1-replace |
| Stantonbury Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Stantonbury Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Temple of Aphrodite, Ancient Cassope | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Temple of Aphrodite, Ancient Cassope | period_start | `-500` | `NULL` | wd1-clear |
| Temple of Apollo Patroos | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Temple of Apollo Patroos | period_start | `-1500` | `NULL` | wd1-clear |
| The Frith | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| The Frith | period_start | `-1000` | `NULL` | wd1-clear |
| Tomb of Macridy Bey | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tomb of Macridy Bey | period_start | `-500` | `NULL` | wd1-clear |
| Tomb of Macridy Bey | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Uchkus Inkañan | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Uchkus Inkañan | period_start | `-1200` | `NULL` | wd1-clear |
| Uchkus Inkañan | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Vardarski Rid | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Vardarski Rid | period_start | `-500` | `NULL` | wd1-clear |
| Villaggio Bizantino | period_name | `3000 - 1500 BC` | `500 - 1000 AD` | wd1-derive-period-name |
| Villaggio Bizantino | period_start | `-3000` | `550` | wd1-replace |
| Villaggio Bizantino | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Washingborough | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Washingborough | period_start | `-1500` | `NULL` | wd1-clear |
| Wayna Tawqaray | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wayna Tawqaray | period_start | `1` | `NULL` | wd1-clear |
| Welsh Road | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Welsh Road | period_start | `-500` | `NULL` | wd1-clear |
| West Wycombe | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| West Wycombe | period_start | `-1500` | `-500` | wd1-replace |
| Wiraqucha, Cusco | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wiraqucha, Cusco | period_start | `1` | `NULL` | wd1-clear |
| Wotanstein, Hesse | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Wotanstein, Hesse | period_start | `-500` | `NULL` | wd1-clear |
| Züschen - Megalithic Tomb | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Züschen - Megalithic Tomb | period_start | `-4000` | `NULL` | wd1-clear |
| İssium | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| İssium | period_start | `1` | `NULL` | wd1-clear |
| İssium | site_type | `Fortress/citadel` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Kenko | lat | `coordinates-unresolved` | Wikipedia's point lies 0.3 km from the stored one but Megalithic Builders' 1.04 km away; no two independent sources agre |
| Hellenistic House | lat | `coordinates-unresolved` | No source gives a point for the Hellenistic House in Nea Paphos. |
| Roman Temple-Deir El Aachaiyer | lat | `coordinates-unresolved` | No source prints a point for the temple of Deir El Aachaiyer. |
| Centro Arqueológico de Chinchero | lat | `coordinates-unresolved` | PilgrimMap's point lies 3.4 km from the stored one; no two sources give a point for the Chinchero archaeological centre. |
| Conchalito | lat | `coordinates-unresolved` | No source prints a point for El Conchalito. |
| Castle Naze | lat | `coordinates-unresolved` | Wikipedia gives a point only for Combs Moss as a whole, not for the fort at its northern tip, and The Great Britain Guid |
| Pyramid of Khentkaus II | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and only Tripomatic gives a point; no two independent sources. |
| Archaeological Site of Olympia | lat | `coordinates-unresolved` | Only Wikipedia gives a point for the sanctuary; the other pages show no coordinates in their text. |
| Kommos, Crete | lat | `coordinates-unresolved` | Only the Wikipedia family gives an independent point; ToposText's Amyklaion point (35.013, 24.761) matches Wikidata's ro |
| İssium | lat | `coordinates-unresolved` | No source found quotes coordinates for the Issium fortress. |
| Lakkos | lat | `coordinates-unresolved` | No source gives a point for Lakkos; Spanish Wikipedia places it south of Mount Juktas near Karnari but gives no coordina |
| Rykeneld Street | lat | `coordinates-unresolved` | No source prints a point for Rykeneld Street; a road has no single point in the sources. |
| Nea Roumata Archaeological Site | lat | `coordinates-unresolved` | No source gives a point for the tomb at Nea Roumata; the stored point cannot be confirmed. |
| Dedoplis Mindori | lat | `coordinates-unresolved` | Only the Wikipedia family gives a point (Wikipedia, Wikidata and historydata's copy); about.ge shows no coordinates in i |
| Nagara (Ancient city) | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent page with the city's point was found. |
| Bosnian Pyramid of the Moon | lat | `coordinates-unresolved` | No two independent sources give a point for the hill called the Pyramid of the Moon. |
| Poblat de Son Catlar | lat | `coordinates-unresolved` | Only Spanish Wikipedia and a page copying it (Hispanopedia) give a point; no independent second source quotes coordinate |
| Villaggio Bizantino | lat | `coordinates-unresolved` | No source prints a point for the Byzantine village of Canalotto. |
| Mawk'ataray | lat | `coordinates-unresolved` | No source found gives a point for Mawk'ataray. |
| San Claudio | lat | `coordinates-unresolved` | No source found gives a point for San Claudio. |
| Nashtifan Windmills | lat | `coordinates-unresolved` | Only Wikipedia's point for the town of Nashtifan is found, 0.6 km off; no source gives a point for the windmills. |
| Welsh Road | lat | `coordinates-unresolved` | No source prints a point for the Welsh Road, a drovers' route. |
| Pyramid of Pepi II | lat | `coordinates-unresolved` | Only Wikipedia gives a point for the pyramid; no independent source with coordinates was found. |
| Korikos Antik Kenti | lat | `coordinates-unresolved` | No source found quotes coordinates for Korykos. |
| Los Pinchudos | lat | `coordinates-unresolved` | No source found gives a point for Los Pinchudos. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s002-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s002 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
