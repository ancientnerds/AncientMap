# WD1 fields-wd1-2026-09-26d-s013: plan

Built 2026-09-29T15:39:54+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s013`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s013:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 203 |
| sites_written | 99 |
| refused | 21 |
| cells:period_name | 87 |
| cells:period_start | 87 |
| cells:site_type | 23 |
| cells:source_url | 6 |
| refused:coordinates-unresolved | 21 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Abrigo do Lagar Velho | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Abrigo do Lagar Velho | period_start | `-30000` | `NULL` | wd1-clear |
| Amphithéâtre Romain Cillium | site_type | `Amphitheatre` | `Theatre` | wd1-replace |
| Amphithéâtre Romain Cillium | source_url | `NULL` | `https://www.theatrum.de/900.html` | wd1-replace |
| Aughlish | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Aughlish | period_start | `-4000` | `NULL` | wd1-clear |
| Balberta | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Balberta | period_start | `1` | `NULL` | wd1-clear |
| Balberta | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Banwell Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Banwell Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Beckfoot | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Beckfoot | period_start | `1` | `NULL` | wd1-clear |
| Beech Bottom Dyke | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Beech Bottom Dyke | period_start | `1` | `NULL` | wd1-clear |
| Beech Bottom Dyke | site_type | `Earthwork` | `NULL` | wd1-clear |
| Beit el-Wali | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Beit el-Wali | period_start | `-1500` | `NULL` | wd1-clear |
| Berry Ring | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Berry Ring | period_start | `-1500` | `NULL` | wd1-clear |
| Bhimashankar Buddhist Caves | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Bhimashankar Buddhist Caves | period_start | `-500` | `NULL` | wd1-clear |
| Bhimashankar Buddhist Caves | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Bhimashankar Buddhist Caves | source_url | `https://kevinstandagephotography.wordpress.com/2017/03/18/bh` | `https://en.wikipedia.org/wiki/Manmodi_Caves` | wd1-replace |
| Bhutalinga Buddhist Caves | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Bhutalinga Buddhist Caves | period_start | `-500` | `NULL` | wd1-clear |
| Bhutalinga Buddhist Caves | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Bhutalinga Buddhist Caves | source_url | `https://kevinstandagephotography.wordpress.com/2017/03/17/bh` | `https://en.wikipedia.org/wiki/Manmodi_Caves` | wd1-replace |
| Bimaran | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Bimaran | period_start | `-500` | `NULL` | wd1-clear |
| Black Head, Cornwall | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Black Head, Cornwall | period_start | `-1000` | `NULL` | wd1-clear |
| Bocan Stone Circle | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Bocan Stone Circle | period_start | `-4500` | `-2500` | wd1-replace |
| Bosnian Pyramid of Love | site_type | `Geological interest` | `Natural feature` | wd1-replace |
| Botley Stone | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Botley Stone | period_start | `-4500` | `NULL` | wd1-clear |
| Botley Stone | site_type | `Mound/tumulus` | `NULL` | wd1-clear |
| Brittenburg | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Brittenburg | period_start | `-1500` | `NULL` | wd1-clear |
| Burfa Castle | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Burfa Castle | period_start | `1` | `NULL` | wd1-clear |
| Campu di Bonu | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Cantalloc Aqueducts | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Cantalloc Aqueducts | period_start | `1` | `NULL` | wd1-clear |
| Castle Close | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castle Close | period_start | `-1000` | `NULL` | wd1-clear |
| Castle Hill, Hampshire | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castle Hill, Hampshire | period_start | `-1000` | `NULL` | wd1-clear |
| Castle Knowe, Northumberland | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castle Knowe, Northumberland | period_start | `-1000` | `NULL` | wd1-clear |
| Castro of Vila Nova de São Pedro | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Castro of Vila Nova de São Pedro | period_start | `-3000` | `-3200` | wd1-replace |
| Cauria | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Cauria | period_start | `-4500` | `NULL` | wd1-clear |
| Cave 20 - Pandavleni Caves | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cave 20 - Pandavleni Caves | period_start | `-500` | `NULL` | wd1-clear |
| Cave 20 - Pandavleni Caves | source_url | `NULL` | `https://en.wikipedia.org/wiki/Nasik_Caves` | wd1-replace |
| Cave of Pego do Diabo | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cave of Pego do Diabo | period_start | `-35000` | `NULL` | wd1-clear |
| Chichester to Silchester Way | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Chichester to Silchester Way | period_start | `1` | `NULL` | wd1-clear |
| Chysauster Ancient Village | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Cierium | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Cierium | period_start | `-2000` | `NULL` | wd1-clear |
| Coneybury Henge | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Coneybury Henge | period_start | `-4500` | `NULL` | wd1-clear |
| Corfinium | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Corfinium | period_start | `-500` | `NULL` | wd1-clear |
| Cova Foradà | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cova Foradà | period_start | `-100000` | `NULL` | wd1-clear |
| Cueva de Bolomor | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cueva de Bolomor | period_start | `-350000` | `NULL` | wd1-clear |
| Dainzú | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Domus de Janas S'Incantu | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Domus de Janas S'Incantu | period_start | `-5000` | `NULL` | wd1-clear |
| Domus de Janas S'Incantu | source_url | `https://www.realsardinia.com/domus-de-janas/` | `https://www.preistoriainitalia.it/en/scheda/domus-de-janas-s` | wd1-replace |
| Dudsbury Camp | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Dudsbury Camp | period_start | `-2000` | `NULL` | wd1-clear |
| Dun Ardtreck | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Dun Ardtreck | period_start | `-500` | `NULL` | wd1-clear |
| Dun Ardtreck | site_type | `Fortification` | `NULL` | wd1-clear |
| Dungeon Hill | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Dungeon Hill | period_start | `-2000` | `NULL` | wd1-clear |
| Durrington Walls | site_type | `City/town/settlement` | `Henge` | wd1-replace |
| Garakopaktapa | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Garakopaktapa | period_start | `-3000` | `NULL` | wd1-clear |
| Garn Boduan | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Garn Boduan | period_start | `-3000` | `NULL` | wd1-clear |
| Gevninge | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Gevninge | period_start | `1` | `500` | wd1-replace |
| Goldbusch | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Goldbusch | period_start | `-4500` | `NULL` | wd1-clear |
| Granite Thrones of Judges of Axum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Granite Thrones of Judges of Axum | period_start | `1` | `NULL` | wd1-clear |
| Granite Thrones of Judges of Axum | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Granite Thrones of Judges of Axum | source_url | `https://www.metmuseum.org/essays/monumental-architecture-and` | `NULL` | wd1-clear |
| Greater Ridgeway | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Greater Ridgeway | period_start | `1` | `NULL` | wd1-clear |
| Greenway Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Greenway Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Gumbat Stupa | site_type | `Temple complex` | `NULL` | wd1-clear |
| Għar Għerduf Catacombs | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Għar Għerduf Catacombs | period_start | `1` | `NULL` | wd1-clear |
| Għar Għerduf Catacombs | site_type | `Cave Structures` | `Burial` | wd1-replace |
| Hadrianapolis Antik Kenti | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Hadrianapolis Antik Kenti | period_start | `1` | `NULL` | wd1-clear |
| Hod Hill | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Hod Hill | period_start | `-2000` | `-500` | wd1-replace |
| Kahu-Jo-Darro | site_type | `Temple complex` | `NULL` | wd1-clear |
| Kentisbury Down | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kentisbury Down | period_start | `-1000` | `NULL` | wd1-clear |
| Kentisbury Down | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| KirkBiza | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Krzesin, Lubusz Voivodeship | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Krzesin, Lubusz Voivodeship | period_start | `-4000` | `NULL` | wd1-clear |
| La Ferrassie | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| La Ferrassie | period_start | `-500` | `NULL` | wd1-clear |
| La Graufesenque | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Langdos | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Langdos | period_start | `-3000` | `-3950` | wd1-replace |
| Las Mercedes Archaeological Site | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Las Mercedes Archaeological Site | period_start | `-3000` | `-1500` | wd1-replace |
| Leben, Crete | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Leben, Crete | period_start | `-2000` | `NULL` | wd1-clear |
| Machu Colca | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Machu Colca | period_start | `1000` | `NULL` | wd1-clear |
| Membury Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Membury Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Mitchell's Fold Stone Circle | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Mitchell's Fold Stone Circle | period_start | `-4500` | `-2000` | wd1-replace |
| Moel y Gaer, Bodfari | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Moel y Gaer, Bodfari | period_start | `-1500` | `NULL` | wd1-clear |
| Morgan's Hill Enclosure | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Morgan's Hill Enclosure | period_start | `-3000` | `NULL` | wd1-clear |
| Mên Scryfa | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Mên Scryfa | period_start | `-4000` | `NULL` | wd1-clear |
| Obelisk of Hatshepsut | site_type | `Megalithic stones` | `Monument` | wd1-replace |
| Obzor | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Obzor | period_start | `-1000` | `NULL` | wd1-clear |
| Otrar | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Otrar | period_start | `1` | `NULL` | wd1-clear |
| Patara Meclis Binası | site_type | `Monument` | `NULL` | wd1-clear |
| Pech Merle | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd1-derive-period-name |
| Pech Merle | period_start | `-500` | `-25000` | wd1-replace |
| Pella | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Pella | period_start | `-7500` | `-4000` | wd1-replace |
| Perge Sütunlu Cadde | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Perge Sütunlu Cadde | period_start | `1` | `NULL` | wd1-clear |
| Perge Sütunlu Cadde | site_type | `Road` | `NULL` | wd1-clear |
| Petinesca | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Petinesca | period_start | `-500` | `NULL` | wd1-clear |
| Prestonbury Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Prestonbury Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Pylos | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Pylos | period_start | `-7000` | `NULL` | wd1-clear |
| Pythagoreion | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Pythagoreion | period_start | `-4000` | `NULL` | wd1-clear |
| Ratiaria | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Ratiaria | period_start | `-500` | `1` | wd1-replace |
| Rhodes Footbridge | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Rhodes Footbridge | period_start | `-500` | `NULL` | wd1-clear |
| Riesenstein, Wolfershausen | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Riesenstein, Wolfershausen | period_start | `-4500` | `NULL` | wd1-clear |
| Roborough Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Roborough Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Roman Aqueduct of Vieu | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Aqueduct of Vieu | period_start | `1` | `NULL` | wd1-clear |
| Roman Middlewich | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Middlewich | period_start | `1` | `NULL` | wd1-clear |
| Roman Rig | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Rig | period_start | `1` | `NULL` | wd1-clear |
| Roman Ruins of Cerro da Vila | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Ruins of Cerro da Vila | period_start | `1` | `NULL` | wd1-clear |
| Shap Stone Avenue | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Shap Stone Avenue | period_start | `-4500` | `NULL` | wd1-clear |
| Stairhaven | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Stairhaven | period_start | `-1500` | `NULL` | wd1-clear |
| Stairhaven | site_type | `Minaret/tower` | `NULL` | wd1-clear |
| Tabasqueno | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tabasqueno | period_start | `1` | `NULL` | wd1-clear |
| The Prison of Socrates | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| The Prison of Socrates | period_start | `-500` | `NULL` | wd1-clear |
| Trencrom Hill | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Trencrom Hill | period_start | `-4500` | `NULL` | wd1-clear |
| Tsitsamuri | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tsitsamuri | period_start | `-500` | `NULL` | wd1-clear |
| Tulamba | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Tulamba | period_start | `-1500` | `NULL` | wd1-clear |
| Typalia Antik Kenti | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Typalia Antik Kenti | period_start | `-1500` | `NULL` | wd1-clear |
| Tzintzuntzan | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Tzintzuntzan | period_start | `1000` | `NULL` | wd1-clear |
| Villa of Torre de Palma | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Villa of Torre de Palma | period_start | `1` | `NULL` | wd1-clear |
| Wadbury Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wadbury Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Winterbourne Bassett Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Winterbourne Bassett Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Withypool Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Withypool Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Yongin Wangsanli Jiseongmyo | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Yongin Wangsanli Jiseongmyo | period_start | `-4500` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Stairhaven | lat | `coordinates-unresolved` | No source gives a point for an ancient site at Stairhaven near the stored point; Stravaiging's point lies 5 km away. |
| Bhimashankar Buddhist Caves | lat | `coordinates-unresolved` | Only Wikipedia's point for the Manmodi complex as a whole is found, 0.5 km off; no source gives a point for the Bhimasha |
| Amphithéâtre Romain Cillium | lat | `coordinates-unresolved` | No source found quotes coordinates for the theatre of Cillium. |
| The Prison of Socrates | lat | `coordinates-unresolved` | No source gives a point for the rock-cut chambers on Philopappos Hill; the stored point cannot be confirmed. |
| Domus de Janas S'Incantu | lat | `coordinates-unresolved` | No source prints a point for the Domus de Janas S'Incantu. |
| Perge Sütunlu Cadde | lat | `coordinates-unresolved` | No source found quotes coordinates for the colonnaded street. |
| Yongin Wangsanli Jiseongmyo | lat | `coordinates-unresolved` | No source found gives a point for the Yongin Wangsanli dolmen. |
| Obelisk of Hatshepsut | lat | `coordinates-unresolved` | No two independent sources give a point for the obelisk. |
| Bosnian Pyramid of Love | lat | `coordinates-unresolved` | No source gives a point for the hill called the Pyramid of Love. |
| Roman Middlewich | lat | `coordinates-unresolved` | Only the DARMC gazetteer (Imperium) prints a point for Salinae; Wikipedia gives none; no second source. |
| Rhodes Footbridge | lat | `coordinates-unresolved` | Only Wikipedia gives a point for the footbridge; no independent source gives one. |
| Bhutalinga Buddhist Caves | lat | `coordinates-unresolved` | Only Wikipedia's point for the Manmodi complex as a whole is found, 0.6 km off; no source gives a point for the Bhutalin |
| Thermes Romains en Ruine-Roman Baths | lat | `coordinates-unresolved` | No source prints a point for the Roman baths of Beirut. |
| Botley Stone | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point for the Botley Stone (1.2 km from the stored point); no second independent sour |
| Cave 20 - Pandavleni Caves | lat | `coordinates-unresolved` | Only Wikipedia's point for the Nasik Caves complex as a whole is found; no source gives a point for Cave 20 itself. |
| Roman Aqueduct of Vieu | lat | `coordinates-unresolved` | Only the Wikipedia family (Wikidata, French Wikipedia) gives a point for the aqueduct; no independent source confirms th |
| Tabasqueno | lat | `coordinates-unresolved` | No source found gives a point for El Tabasqueño. |
| Campu di Bonu | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent source with a point was found. |
| Greater Ridgeway | lat | `coordinates-unresolved` | The Greater Ridgeway is a 362-mile long-distance route across England; no source gives one point for it, so no two sourc |
| Patara Meclis Binası | lat | `coordinates-unresolved` | No source found quotes coordinates for the Patara assembly building. |
| Granite Thrones of Judges of Axum | lat | `coordinates-unresolved` | No source gives a point for the granite thrones at Aksum. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s013-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s013 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
