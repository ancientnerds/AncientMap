# WD1 fields-wd1-2026-09-26d-s014: plan

Built 2026-09-29T15:40:52+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s014`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s014:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 220 |
| sites_written | 100 |
| refused | 23 |
| cells:period_name | 95 |
| cells:period_start | 95 |
| cells:site_type | 25 |
| cells:source_url | 5 |
| refused:coordinates-unresolved | 23 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acropolis Museum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Acropolis Museum | period_start | `1` | `NULL` | wd1-clear |
| Aigeira | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Aigeira | period_start | `-5500` | `NULL` | wd1-clear |
| Al Diwan | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Al Diwan | period_start | `1` | `NULL` | wd1-clear |
| Al Diwan | site_type | `Monument` | `NULL` | wd1-clear |
| Al Thumamah, Riyadh | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Al Thumamah, Riyadh | period_start | `-6000` | `NULL` | wd1-clear |
| Al Thumamah, Riyadh | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Alarcos | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Alarcos | period_start | `-1500` | `NULL` | wd1-clear |
| America's Stonehenge | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| America's Stonehenge | period_start | `-3000` | `NULL` | wd1-clear |
| Ancient City of Jiaohe | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Ancient City of Jiaohe | period_start | `-3000` | `-200` | wd1-replace |
| Ancient City of Perrin | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ancient City of Perrin | period_start | `1` | `NULL` | wd1-clear |
| Anta da Barrosa | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Anta da Barrosa | period_start | `-4000` | `NULL` | wd1-clear |
| Apidima Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Apidima Cave | period_start | `-210000` | `NULL` | wd1-clear |
| Archaeological Site of Grand | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Archaeological Site of Grand | period_start | `1` | `NULL` | wd1-clear |
| Archaeological Site of Grand | site_type | `Megalithic structures` | `City` | wd1-replace |
| Aston Valley Barrow Cemetery | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Aston Valley Barrow Cemetery | period_start | `-4500` | `NULL` | wd1-clear |
| Barreira Megalithic Complex | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Barreira Megalithic Complex | period_start | `-4000` | `NULL` | wd1-clear |
| Black Ball Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Black Ball Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Bohonagh Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Bohonagh Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Bruniquel Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Bruniquel Cave | period_start | `-176500` | `NULL` | wd1-clear |
| Bullsdown Camp | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Bullsdown Camp | period_start | `-2000` | `NULL` | wd1-clear |
| Burrington Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Burrington Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Bury Ditches | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Bury Ditches | period_start | `-1500` | `-500` | wd1-replace |
| Buzbury Rings | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Buzbury Rings | period_start | `-1000` | `NULL` | wd1-clear |
| Cadson Bury | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Cadson Bury | period_start | `-1000` | `NULL` | wd1-clear |
| Cahors | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cahors | period_start | `-500` | `NULL` | wd1-clear |
| Capocorb Vell | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Capocorb Vell | period_start | `-2000` | `-1200` | wd1-replace |
| Carachupa | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Carachupa | period_start | `-2000` | `NULL` | wd1-clear |
| Castell Nadolig | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Castell Nadolig | period_start | `-1500` | `NULL` | wd1-clear |
| Cave of the Trois-Frères | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd1-derive-period-name |
| Cave of the Trois-Frères | period_start | `-500` | `-13000` | wd1-replace |
| Choquequirao Puquio | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Choquequirao Puquio | period_start | `1400` | `NULL` | wd1-clear |
| Choquequirao Puquio | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Chûn Castle | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Chûn Castle | period_start | `-1500` | `-400` | wd1-replace |
| Chûn Quoit | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Chûn Quoit | period_start | `-3000` | `NULL` | wd1-clear |
| Clausentum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Clausentum | period_start | `1` | `NULL` | wd1-clear |
| Clegyr Boia | period_name | `1500 - 500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Clegyr Boia | period_start | `-1500` | `-3800` | wd1-replace |
| Craig Ty-Isaf | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Craig Ty-Isaf | period_start | `-1500` | `NULL` | wd1-clear |
| Cuchi Machay | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cuchi Machay | period_start | `-7000` | `NULL` | wd1-clear |
| Cularo | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cularo | period_start | `-500` | `NULL` | wd1-clear |
| Devil's Dyke, Hertfordshire | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Devil's Dyke, Hertfordshire | period_start | `-1000` | `-100` | wd1-replace |
| Eryx (Sicily) | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Eryx (Sicily) | period_start | `-1500` | `NULL` | wd1-clear |
| Fethiye Antik Tiyatrosu | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Fethiye Antik Tiyatrosu | period_start | `-500` | `NULL` | wd1-clear |
| Fethiye Antik Tiyatrosu | site_type | `Theatre` | `NULL` | wd1-clear |
| Fethiye Antik Tiyatrosu | source_url | `http://www.tuerkei-antik.de/Theater/telmessos_en.htm` | `https://listeleo.com.tr/gezilecek-yerler/fethiye-antik-tiyat` | wd1-replace |
| Fraubillen Cross | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Fraubillen Cross | period_start | `-4500` | `NULL` | wd1-clear |
| Gate of Zeus and Hera | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Gate of Zeus and Hera | period_start | `-1500` | `NULL` | wd1-clear |
| Gate of Zeus and Hera | source_url | `https://www.tripadvisor.com/Attraction_Review-g776005-d14192` | `https://topostext.org/place/408247FZeu` | wd1-replace |
| Glastonbury Lake Village | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Glastonbury Lake Village | period_start | `-500` | `NULL` | wd1-clear |
| Glastonbury Lake Village | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Govurqala, Shaki | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Govurqala, Shaki | period_start | `1` | `NULL` | wd1-clear |
| Govurqala, Shaki | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Grakliani Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Grakliani Hill | period_start | `-1500` | `NULL` | wd1-clear |
| Grey Wethers | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Grey Wethers | period_start | `-4500` | `NULL` | wd1-clear |
| Holmbury Hill | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Holmbury Hill | period_start | `-500` | `NULL` | wd1-clear |
| Holmbury Hill | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Holne Chase Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Holne Chase Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Inti Punku | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Inti Punku | period_start | `1` | `NULL` | wd1-clear |
| Jasov Cave | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Jasov Cave | period_start | `-3000` | `NULL` | wd1-clear |
| Kamyana Mohyla | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Kamyana Mohyla | period_start | `-3000` | `NULL` | wd1-clear |
| Kanlı Divane Ören Yeri | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Kanlı Divane Ören Yeri | period_start | `-500` | `NULL` | wd1-clear |
| Kanlı Divane Ören Yeri | site_type | `Cave Structures` | `City/town/settlement` | wd1-replace |
| Kealkill Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Kealkill Stone Circle | period_start | `-4000` | `NULL` | wd1-clear |
| Kents Cavern | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Kents Cavern | period_start | `-500000` | `NULL` | wd1-clear |
| Knowle Hill Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Knowle Hill Castle | period_start | `-1000` | `NULL` | wd1-clear |
| La Sufricaya | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| La Sufricaya | period_start | `-500` | `350` | wd1-replace |
| La Sufricaya | site_type | `City/town/settlement` | `Palace` | wd1-replace |
| Lascaux | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Lascaux | period_start | `-22000` | `NULL` | wd1-clear |
| Lissus, Crete | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Lissus, Crete | period_start | `-1000` | `NULL` | wd1-clear |
| Longyou Grottoes | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Longyou Grottoes | period_start | `-500` | `NULL` | wd1-clear |
| Los Sapos Archeologico | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Los Sapos Archeologico | period_start | `-3000` | `NULL` | wd1-clear |
| Los Sapos Archeologico | site_type | `Sacred site` | `NULL` | wd1-clear |
| Lot's Cave | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Lot's Cave | period_start | `-3000` | `NULL` | wd1-clear |
| Lycaean Tomb | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Lycaean Tomb | source_url | `http://www.my-favourite-planet.de/english/europe/greece/dode` | `NULL` | wd1-clear |
| Maidanetske | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Maidanetske | period_start | `-5000` | `-3990` | wd1-replace |
| Markiani | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Markiani | period_start | `-4000` | `NULL` | wd1-clear |
| Megalithic Walls of Altamura | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Megalithic Walls of Altamura | period_start | `-500` | `NULL` | wd1-clear |
| Membury Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Membury Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Mian Khan | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Moel y Gaer, Llantysilio | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Moel y Gaer, Llantysilio | period_start | `-1500` | `NULL` | wd1-clear |
| Naveta | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Naveta | period_start | `-4500` | `NULL` | wd1-clear |
| Naveta | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| New Ditch | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| New Ditch | period_start | `-500` | `NULL` | wd1-clear |
| Obelisk of Thutmose I | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Obelisk of Thutmose I | source_url | `https://www.memphis.edu/egypt/resources/colortour/luxor5.php` | `https://digitalkarnak.ucsc.edu/obelisks-of-festival-hall-eas` | wd1-replace |
| Offham Hill | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Offham Hill | period_start | `-4000` | `NULL` | wd1-clear |
| Olympia, Greece | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Olympia, Greece | period_start | `-1500` | `-2300` | wd1-replace |
| Omphalos of Delphi | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Omphalos of Delphi | period_start | `-2000` | `NULL` | wd1-clear |
| Parco Archeologico Naturalistico di Santa Cristina | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Parco Archeologico Naturalistico di Santa Cristina | period_start | `-3000` | `-1200` | wd1-replace |
| Petrovka Settlement | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Petrovka Settlement | period_start | `-2000` | `NULL` | wd1-clear |
| Phthiotic Thebes | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Phthiotic Thebes | period_start | `-500` | `NULL` | wd1-clear |
| Pintia | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Pintia | period_start | `-500` | `NULL` | wd1-clear |
| Ponter's Ball Dyke | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Ponter's Ball Dyke | period_start | `-500` | `NULL` | wd1-clear |
| Požun, Croatia | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Požun, Croatia | period_start | `-1500` | `NULL` | wd1-clear |
| Qasr al-Sagha | site_type | `Temple complex` | `Temple` | wd1-replace |
| Qollmay | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Qollmay | period_start | `1000` | `NULL` | wd1-clear |
| Qollmay | site_type | `Cave Structures` | `NULL` | wd1-clear |
| Roman Remains under Alfonso X Street | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Remains under Alfonso X Street | period_start | `1` | `NULL` | wd1-clear |
| Roman Remains under Alfonso X Street | site_type | `Reservoir/aqueduct/canal` | `NULL` | wd1-clear |
| Roman Ruins of Djemila | site_type | `Temple complex` | `City` | wd1-replace |
| Roman Ruins of Djemila | source_url | `https://whc.unesco.org/en/list/191/` | `https://en.wikipedia.org/wiki/Dj%C3%A9mila` | wd1-replace |
| Ruborough Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Ruborough Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Sar Ruins | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Sar Ruins | period_start | `-1500` | `NULL` | wd1-clear |
| Shaftoe Crags Settlement | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Shaftoe Crags Settlement | period_start | `-1000` | `NULL` | wd1-clear |
| Sirnikot | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Sirnikot | period_start | `-1500` | `NULL` | wd1-clear |
| Sirnikot | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Stalldown Barrow | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Stalldown Barrow | period_start | `-4500` | `NULL` | wd1-clear |
| Stobi | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Stobi | period_start | `-500` | `NULL` | wd1-clear |
| Talayotic Settlement of Torrellisar | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Talayotic Settlement of Torrellisar | period_start | `-2000` | `NULL` | wd1-clear |
| Termessos Tiyatrosu | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Termessos Tiyatrosu | period_start | `-200` | `NULL` | wd1-clear |
| Tidbury Ring | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Tidbury Ring | period_start | `-1500` | `NULL` | wd1-clear |
| Tolvan Holed Stone | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Tolvan Holed Stone | period_start | `-4500` | `NULL` | wd1-clear |
| Treasure of Osztrópataka | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Treasure of Osztrópataka | period_start | `1` | `NULL` | wd1-clear |
| Treasure of Osztrópataka | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Twmbarlwm | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Twmbarlwm | period_start | `-1500` | `NULL` | wd1-clear |
| Türkenfeld | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Türkenfeld | period_start | `-3000` | `NULL` | wd1-clear |
| Usqunta | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Usqunta | period_start | `1400` | `NULL` | wd1-clear |
| Usqunta | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Utroba Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Utroba Cave | period_start | `-500` | `NULL` | wd1-clear |
| Wanakawri, Huánuco | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wanakawri, Huánuco | period_start | `1` | `NULL` | wd1-clear |
| Wanakawri, Huánuco | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Waqlamarka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Waqlamarka | period_start | `1200` | `NULL` | wd1-clear |
| Waqlamarka | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Willy Howe | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Willy Howe | period_start | `-3000` | `NULL` | wd1-clear |
| Ñawpallaqta, Huanca Sancos | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Ñawpallaqta, Huanca Sancos | period_start | `1400` | `NULL` | wd1-clear |
| Ñawpallaqta, Huanca Sancos | site_type | `City/town/settlement` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Sirnikot | lat | `coordinates-unresolved` | No source found gives a point for Sirnikot. |
| Parco Archeologico Naturalistico di Santa Cristina | lat | `coordinates-unresolved` | Only Mysteria prints a point for Santa Cristina; no independent second source. |
| Govurqala, Shaki | lat | `coordinates-unresolved` | Wikipedia notes that four archaeological sites share the name Govurqala and gives no point for this one; no source with  |
| Al Diwan | lat | `coordinates-unresolved` | Only Atlas Islamica gives a point for Al Diwan; no second independent source was found. |
| Talayotic Settlement of Torrellisar | lat | `coordinates-unresolved` | No source found quotes coordinates for Torrellisar. |
| Megalithic Walls of Altamura | lat | `coordinates-unresolved` | Only Wikipedia prints a point for the walls, 0.4 km off; no independent second source. |
| Mian Khan | lat | `coordinates-unresolved` | No source found gives a point for the Mian Khan excavation site. |
| Treasure of Osztrópataka | lat | `coordinates-unresolved` | No source found gives a point for the Osztrópataka burial. |
| Roman Remains under Alfonso X Street | lat | `coordinates-unresolved` | No source found quotes coordinates for the remains under Calle Alfonso X. |
| Gate of Zeus and Hera | lat | `coordinates-unresolved` | Only ToposText gives a point for the gate in its text (40.7756, 24.7090); no second quotable source gives one. |
| Požun, Croatia | lat | `coordinates-unresolved` | Only Wikipedia gives a point for Pozun; no independent source with coordinates was found. |
| Wanakawri, Huánuco | lat | `coordinates-unresolved` | No source found gives a point for Wanakawri in Huánuco. |
| Lycaean Tomb | lat | `coordinates-unresolved` | Only All Over Greece gives a point for the tomb (36.15099, 29.59526); no second source gives one. |
| La Sufricaya | lat | `coordinates-unresolved` | No source gives a point for La Sufricaya; the stored point cannot be confirmed. |
| Obelisk of Thutmose I | lat | `coordinates-unresolved` | No two independent sources give a point for the obelisk of Thutmose I. |
| Termessos Tiyatrosu | lat | `coordinates-unresolved` | No source found quotes coordinates for the theatre of Termessos. |
| Roman Ruins of Djemila | lat | `coordinates-unresolved` | Only Wikipedia gives a point (36.317 N 5.733 E); no independent source with coordinates was found. |
| Fethiye Antik Tiyatrosu | lat | `coordinates-unresolved` | No source found quotes coordinates for the Fethiye theatre. |
| Naveta | lat | `coordinates-unresolved` | Naveta is a type of Menorcan chamber tomb, not a single site; no source gives one point for it. |
| Cuchi Machay | lat | `coordinates-unresolved` | No source found gives a point for Cuchi Machay. |
| Waqlamarka | lat | `coordinates-unresolved` | No source found gives a point for Waqlamarka. |
| Ñawpallaqta, Huanca Sancos | lat | `coordinates-unresolved` | The only point found (HistoryData) lies 100 km from the stored one; no source gives a confirmed point. |
| Los Sapos Archeologico | lat | `coordinates-unresolved` | No source prints a point for Los Sapos. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s014-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s014 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
