# WD1 fields-wd1-2026-09-26d-s001: plan

Built 2026-09-29T15:28:36+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s001`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s001:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 215 |
| sites_written | 99 |
| refused | 22 |
| cells:period_name | 95 |
| cells:period_start | 95 |
| cells:site_type | 20 |
| cells:source_url | 5 |
| refused:coordinates-unresolved | 22 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Aedava | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Aedava | period_start | `-500` | `NULL` | wd1-clear |
| Alcimoennis | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Alcimoennis | period_start | `-1500` | `NULL` | wd1-clear |
| Althiburos | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Althiburos | period_start | `1` | `-1000` | wd1-replace |
| Ancient Kymissala | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ancient Kymissala | period_start | `-1500` | `NULL` | wd1-clear |
| Apazzu | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Apazzu | period_start | `-3300` | `NULL` | wd1-clear |
| Archaeological Park of Segóbriga | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Archaeological Park of Segóbriga | period_start | `1` | `NULL` | wd1-clear |
| Babel Lion | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Babel Lion | period_start | `-3000` | `NULL` | wd1-clear |
| Babylonian Theatre | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Babylonian Theatre | period_start | `-500` | `NULL` | wd1-clear |
| Babylonian Theatre | source_url | `https://www.livius.org/sources/content/the-babylon-theater-i` | `https://jcofarts.uobaghdad.edu.iq/index.php/jcofarts/article` | wd1-replace |
| Bathampton Down | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Bathampton Down | period_start | `-4500` | `NULL` | wd1-clear |
| Batán Grande | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Batán Grande | period_start | `500` | `NULL` | wd1-clear |
| Belsar's Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Belsar's Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Bonampak | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Bonampak | period_start | `500` | `NULL` | wd1-clear |
| Bradley Hill Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bradley Hill Fort | period_start | `-1000` | `NULL` | wd1-clear |
| Burley Wood | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Burley Wood | period_start | `-500` | `NULL` | wd1-clear |
| Burley Wood | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Castulo | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Castulo | period_start | `-1500` | `-3000` | wd1-replace |
| Cathedral and Churches of Echmiatsin and the Archaeological Site of Zvartnots | site_type | `Temple complex` | `Church/cathedral` | wd1-replace |
| Cathedral and Churches of Echmiatsin and the Archaeological Site of Zvartnots | source_url | `https://whc.unesco.org/en/list/1011/` | `https://worldheritageexplorer.org/sites/cathedral_and_church` | wd1-replace |
| Cave of Mayrières Supérieure | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cave of Mayrières Supérieure | period_start | `-13000` | `NULL` | wd1-clear |
| Cerna, Croatia | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cerna, Croatia | period_start | `-500` | `NULL` | wd1-clear |
| Chrisso, Phocis | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Chrisso, Phocis | period_start | `-2000` | `NULL` | wd1-clear |
| Coca, Segovia | period_name | `1 - 500 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Coca, Segovia | period_start | `1` | `-2500` | wd1-replace |
| Columbário Fenício | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Columbário Fenício | period_start | `-800` | `NULL` | wd1-clear |
| Columbário Fenício | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Cow Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cow Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Currachjaghju | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Currachjaghju | period_start | `-6000` | `NULL` | wd1-clear |
| Currachjaghju | site_type | `Settlement` | `NULL` | wd1-clear |
| Cuween Hill Chambered Cairn | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Cuween Hill Chambered Cairn | period_start | `-4500` | `-3000` | wd1-replace |
| Dausdava | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Dausdava | period_start | `-500` | `NULL` | wd1-clear |
| Derby Racecourse Roman Settlement | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Dere Street | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dere Street | period_start | `1` | `NULL` | wd1-clear |
| Devil's Humps, Stoughton | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Devil's Humps, Stoughton | period_start | `-4500` | `NULL` | wd1-clear |
| Dinedor Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dinedor Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Dobberworth | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Dobberworth | period_start | `-4500` | `NULL` | wd1-clear |
| Dumat al-Jandal Wall | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dumat al-Jandal Wall | period_start | `1` | `NULL` | wd1-clear |
| Eileithyia Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Eileithyia Cave | period_start | `-500` | `NULL` | wd1-clear |
| Foel Dduarth - Cairn to North-East of | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Foel Dduarth - Cairn to North-East of | period_start | `-5000` | `NULL` | wd1-clear |
| Foel Dduarth - Cairn to North-East of | site_type | `Cairn` | `NULL` | wd1-clear |
| Fort Abbas | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Fort Abbas | period_start | `-5000` | `NULL` | wd1-clear |
| Gaer Fawr, Llanilar | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Gaer Fawr, Llanilar | period_start | `-1500` | `NULL` | wd1-clear |
| Grimstock Hill Romano-British Settlement | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Grimstock Hill Romano-British Settlement | period_start | `1` | `NULL` | wd1-clear |
| Hampton Down Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Hampton Down Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Hartashen Megalithic Avenue | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Hartashen Megalithic Avenue | period_start | `-5000` | `NULL` | wd1-clear |
| Hathial | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Hathial | period_start | `-1500` | `-3000` | wd1-replace |
| Horvat Shema | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Horvat Shema | period_start | `1` | `NULL` | wd1-clear |
| Huayrapongo | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Huayrapongo | period_start | `-300` | `NULL` | wd1-clear |
| Justinianopolis (Epirus) | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Justinianopolis (Epirus) | period_start | `-500` | `NULL` | wd1-clear |
| Justinianopolis (Epirus) | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Kechries | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kechries | period_start | `-1500` | `NULL` | wd1-clear |
| Kingston Russell Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Kingston Russell Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Kudakkallu Parambu - Megalithic Burial Site | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Kudakkallu Parambu - Megalithic Burial Site | period_start | `-3000` | `NULL` | wd1-clear |
| Kudakkallu Parambu - Megalithic Burial Site | site_type | `Necropolis/tombs complex` | `Burial` | wd1-replace |
| Kyaneai Tarihi Sarnıç | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Kyaneai Tarihi Sarnıç | period_start | `-500` | `NULL` | wd1-clear |
| Kyaneai Tarihi Sarnıç | site_type | `Infrastructure` | `NULL` | wd1-clear |
| Labna | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Labna | period_start | `-200` | `NULL` | wd1-clear |
| Las Capellanías | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Las Capellanías | period_start | `-4000` | `NULL` | wd1-clear |
| Lescudjack Hill Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Lescudjack Hill Fort | period_start | `-1000` | `NULL` | wd1-clear |
| Llyn Fawr | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Llyn Fawr | period_start | `-2000` | `-650` | wd1-replace |
| Long Meg and Her Daughters | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Long Meg and Her Daughters | period_start | `-4000` | `NULL` | wd1-clear |
| Machaquila | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Machaquila | period_start | `500` | `NULL` | wd1-clear |
| Magasa, Crete | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Magasa, Crete | period_start | `-500` | `NULL` | wd1-clear |
| Medmenham | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Medmenham | period_start | `-500` | `NULL` | wd1-clear |
| Menhir du Camp de César | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Menhir du Camp de César | period_start | `1` | `NULL` | wd1-clear |
| Monte Lazzu | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Monte Lazzu | period_start | `-3500` | `NULL` | wd1-clear |
| Mérida Anthropological Museum | period_name | `1500+ AD` | `NULL` | wd1-derive-period-name |
| Mérida Anthropological Museum | period_start | `1959` | `NULL` | wd1-clear |
| Mérida Anthropological Museum | source_url | `https://sic.cultura.gob.mx/ficha.php?table=museo&table_id=41` | `https://lugares.inah.gob.mx/en/node/4258` | wd1-replace |
| Nicopolis ad Nestum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Nicopolis ad Nestum | period_start | `1` | `NULL` | wd1-clear |
| Ninamarca | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ninamarca | period_start | `1` | `NULL` | wd1-clear |
| Northwest Palace of Ashur-Nasir-Pal II | source_url | `https://www.britishmuseum.org/collection/galleries/assyria-n` | `https://www.learningsites.com/NWPalace/NWPalhome.php` | wd1-replace |
| Oinochori | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Oinochori | period_start | `-1500` | `NULL` | wd1-clear |
| Orolik | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Orolik | period_start | `-500` | `NULL` | wd1-clear |
| Oxkintok | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Oxkintok | period_start | `-1500` | `NULL` | wd1-clear |
| Pavlopetri | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Pavlopetri | period_start | `-4500` | `NULL` | wd1-clear |
| Pikestones | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Pikestones | period_start | `-4000` | `NULL` | wd1-clear |
| Pumawasi, Anta | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Pumawasi, Anta | period_start | `1400` | `NULL` | wd1-clear |
| Pumawasi, Anta | site_type | `Rock art` | `NULL` | wd1-clear |
| Punic Building, Żurrieq | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Punic Building, Żurrieq | period_start | `-500` | `NULL` | wd1-clear |
| Punic Building, Żurrieq | site_type | `Megalithic structures` | `Minaret/tower` | wd1-replace |
| Rag-i-Bibi | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Rag-i-Bibi | period_start | `1` | `NULL` | wd1-clear |
| Roman Bridge of Salamanca | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Roman Bridge of Salamanca | period_start | `-500` | `1` | wd1-replace |
| Roman Bridge, Saint-Thibéry | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Roman Bridge, Saint-Thibéry | period_start | `-500` | `NULL` | wd1-clear |
| Roman Vaults of Nuncio Viejo | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Vaults of Nuncio Viejo | period_start | `1` | `NULL` | wd1-clear |
| Roman Vaults of Nuncio Viejo | site_type | `Megalithic structures` | `Reservoir/aqueduct/canal` | wd1-replace |
| Roundton Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Roundton Hill | period_start | `-1500` | `NULL` | wd1-clear |
| Ruínas Romanas da Bobadela | source_url | `NULL` | `https://patrimonios.pt/en/bobadela/` | wd1-replace |
| Sidi Said | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Sidi Said | period_start | `1` | `NULL` | wd1-clear |
| Smythapark | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Smythapark | period_start | `-1000` | `NULL` | wd1-clear |
| Stannon Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Stannon Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Sura - Ancient Oracle | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Sura - Ancient Oracle | period_start | `1` | `-400` | wd1-replace |
| Sweetworthy | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Sweetworthy | period_start | `-3000` | `NULL` | wd1-clear |
| Sweetworthy | site_type | `Fortress/citadel` | `City/town/settlement` | wd1-replace |
| Tambo Viejo | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Tambo Viejo | period_start | `1000` | `NULL` | wd1-clear |
| Tell Maghzaliyah | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Tell Maghzaliyah | period_start | `-7000` | `NULL` | wd1-clear |
| Temple of Khonsuirdis | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Temple of Khonsuirdis | period_start | `-630` | `NULL` | wd1-clear |
| Temple of Khonsuirdis | site_type | `Temple complex` | `NULL` | wd1-clear |
| Tepeapulco Pyramid | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tepeapulco Pyramid | period_start | `-500` | `NULL` | wd1-clear |
| Tepeapulco Pyramid | site_type | `Pyramid complex` | `NULL` | wd1-clear |
| The Street, Derbyshire | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| The Street, Derbyshire | period_start | `1` | `NULL` | wd1-clear |
| The Street, Derbyshire | site_type | `Road/avenue/trackway` | `NULL` | wd1-clear |
| The Trundle | period_name | `1500 - 500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| The Trundle | period_start | `-1000` | `-4400` | wd1-replace |
| Three Brothers, Lancashire | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Three Brothers, Lancashire | period_start | `-4000` | `NULL` | wd1-clear |
| Tiverton, Devon | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Tiverton, Devon | period_start | `-2000` | `NULL` | wd1-clear |
| Tomba dei Giganti di Laccaneddu | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Tomba dei Giganti di Laccaneddu | period_start | `-3000` | `NULL` | wd1-clear |
| Tomba dei Giganti di Laccaneddu | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Toothill Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Toothill Fort | period_start | `-1000` | `NULL` | wd1-clear |
| Tregiffian Burial Chamber | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Tregiffian Burial Chamber | period_start | `-4500` | `NULL` | wd1-clear |
| Treryn Dinas | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Treryn Dinas | period_start | `-1000` | `NULL` | wd1-clear |
| Trialeti Petroglyphs | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Trialeti Petroglyphs | period_start | `-4500` | `NULL` | wd1-clear |
| Tulja Buddhist Caves | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tulja Buddhist Caves | period_start | `-500` | `NULL` | wd1-clear |
| Uch | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Uch | period_start | `-500` | `NULL` | wd1-clear |
| Wamanmarka, Lima | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wamanmarka, Lima | period_start | `1` | `NULL` | wd1-clear |
| Wamanmarka, Lima | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Westbury Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Westbury Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Xunantunich | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Xunantunich | period_start | `1` | `-600` | wd1-replace |
| Yanaque - Quilcamarca | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Yanaque - Quilcamarca | period_start | `1` | `NULL` | wd1-clear |
| Yanaque - Quilcamarca | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Yarrowbury | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Yarrowbury | period_start | `-1000` | `NULL` | wd1-clear |
| Yarrowbury | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Zona Arqueológica Chinkultic | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Zona Arqueológica Chinkultic | period_start | `1` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Menhir du Camp de César | lat | `coordinates-unresolved` | No two independent sources give a point for the menhir. |
| Horvat Shema | lat | `coordinates-unresolved` | Only the Wikipedia family (English and Hebrew) prints a point for Khirbet Shema; no independent second source. |
| Sura - Ancient Oracle | lat | `coordinates-unresolved` | No source found quotes coordinates for Sura; the Wikipedia hit is Harran. |
| Mérida Anthropological Museum | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point for the museum in the Palacio Cantón; no second independent source was found. |
| Zona Arqueológica Chinkultic | lat | `coordinates-unresolved` | Only Wikipedia gives a point for Chinkultic (0.02 km from the stored one); no second independent source was found. |
| Foel Dduarth - Cairn to North-East of | lat | `coordinates-unresolved` | Only the Megalithic Portal quotes a nearby point (0.18 km from the stored one), for a different feature; no second sourc |
| Roman Vaults of Nuncio Viejo | lat | `coordinates-unresolved` | Only Tripomatic quotes a point (0.02 km from the stored one); Wikipedia gives none, so no second independent source conf |
| Northwest Palace of Ashur-Nasir-Pal II | lat | `coordinates-unresolved` | No source prints a point for the Northwest Palace itself. |
| Kyaneai Tarihi Sarnıç | lat | `coordinates-unresolved` | No source found quotes coordinates for the historic cistern of Kyaneai. |
| The Street, Derbyshire | lat | `coordinates-unresolved` | No source prints a point for The Street; Wikipedia gives none. |
| Columbário Fenício | lat | `coordinates-unresolved` | No source found gives a point for the Columbário Fenício. |
| Babylonian Theatre | lat | `coordinates-unresolved` | No source prints a point for the theatre of Babylon. |
| Tomba dei Giganti di Laccaneddu | lat | `coordinates-unresolved` | Only World Heritage Guide prints a point, 1.3 km from the stored point; no second source confirms either. |
| Tepeapulco Pyramid | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point for the Tepeapulco pyramid; no second independent source was found. |
| Kudakkallu Parambu - Megalithic Burial Site | lat | `coordinates-unresolved` | Only a local listing page (Promallu) prints a point for Kudakkallu Parambu; Wikipedia gives none; no second source. |
| Temple of Khonsuirdis | lat | `coordinates-unresolved` | No source gives a point for the temple-tomb of Khonsuirdis. |
| Babel Lion | lat | `coordinates-unresolved` | Only the Arabic Wikipedia prints a point for the Lion of Babylon; no independent second source. |
| Ruínas Romanas da Bobadela | lat | `coordinates-unresolved` | Only Visit Região de Coimbra (via CVRDão) prints coordinates for the Bobadela ruins; no second independent source gives  |
| Archaeological Park of Segóbriga | lat | `coordinates-unresolved` | No source found gives a point for Segóbriga. |
| Dumat al-Jandal Wall | lat | `coordinates-unresolved` | Only Wikipedia gives a point for the Dumat al-Jandal wall; no second independent source was found. |
| Cathedral and Churches of Echmiatsin and the Archaeological Site of Zvartnots | lat | `coordinates-unresolved` | No two independent sources give a point for the serial World Heritage property. |
| Currachjaghju | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent source with a point was found. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s001-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s001 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
