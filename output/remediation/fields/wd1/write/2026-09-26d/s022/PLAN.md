# WD1 fields-wd1-2026-09-26d-s022: plan

Built 2026-09-29T15:48:18+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s022`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s022:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 219 |
| sites_written | 99 |
| refused | 24 |
| cells:period_name | 95 |
| cells:period_start | 95 |
| cells:site_type | 24 |
| cells:source_url | 5 |
| refused:coordinates-unresolved | 23 |
| refused:held-unreadable | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Ackling Dyke | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ackling Dyke | period_start | `1` | `NULL` | wd1-clear |
| Akeman Street | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Akeman Street | period_start | `1` | `NULL` | wd1-clear |
| Alte Burg, Langenenslingen | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Alte Burg, Langenenslingen | period_start | `-1500` | `NULL` | wd1-clear |
| Ancient Theatre of Makyneia | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Ancient Theatre of Makyneia | period_start | `-500` | `NULL` | wd1-clear |
| Ancient Theatre of Makyneia | source_url | `https://diazoma.gr/en/theaters/theatre-of-macynia/` | `https://el.wikipedia.org/wiki/%CE%91%CF%81%CF%87%CE%B1%CE%AF` | wd1-replace |
| Anta de Agualva | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Anta de Agualva | period_start | `-4000` | `NULL` | wd1-clear |
| Antas da Valeira | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Antas da Valeira | period_start | `-4000` | `NULL` | wd1-clear |
| Archaeological site Makthar | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Arqueológico El Puente Park | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Arqueológico El Puente Park | period_start | `500` | `NULL` | wd1-clear |
| Arzachena Archaeological Park | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Arzachena Archaeological Park | period_start | `-4000` | `NULL` | wd1-clear |
| Arzachena Archaeological Park | site_type | `Megalithic structures` | `NULL` | wd1-clear |
| Arzachena Archaeological Park | source_url | `https://strictlysardinia.com/archeological-sites-in-sardinia` | `https://www.italia.it/en/sardinia/arzachena-archaeological-p` | wd1-replace |
| Aymestrey Burial | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Aymestrey Burial | period_start | `-4500` | `NULL` | wd1-clear |
| Aymestrey Burial | site_type | `Museum` | `Burial` | wd1-replace |
| Barpa Langass | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Barpa Langass | period_start | `-4500` | `-3000` | wd1-replace |
| Beaumont Cut | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Beaumont Cut | period_start | `1` | `NULL` | wd1-clear |
| Belas Knap | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Belas Knap | period_start | `-4500` | `-3000` | wd1-replace |
| Beşkardeşler Kaya Mezarları | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Beşkardeşler Kaya Mezarları | period_start | `1` | `NULL` | wd1-clear |
| Beşkardeşler Kaya Mezarları | site_type | `Tomb` | `NULL` | wd1-clear |
| Beşkardeşler Kaya Mezarları | source_url | `NULL` | `https://kirikhan.bel.tr/kirikhan/tanitim/gorulecek-yerler/be` | wd1-replace |
| Bindon Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bindon Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Brampton, Norfolk | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Brampton, Norfolk | period_start | `1` | `NULL` | wd1-clear |
| Buckton Roman Fort | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Buckton Roman Fort | period_start | `1` | `NULL` | wd1-clear |
| Cannae | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Cannae | period_start | `-500` | `NULL` | wd1-clear |
| Carreg Coetan Arthur | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Carreg Coetan Arthur | period_start | `-4000` | `NULL` | wd1-clear |
| Creswell Crags | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Creswell Crags | period_start | `-500` | `NULL` | wd1-clear |
| Derventio Brigantum | site_type | `City/town/settlement` | `Fort` | wd1-replace |
| Desborough Castle | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Desborough Castle | period_start | `-2000` | `NULL` | wd1-clear |
| Dimini | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Dimini | period_start | `-5000` | `NULL` | wd1-clear |
| Dog Hole Cave | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dog Hole Cave | period_start | `1` | `NULL` | wd1-clear |
| Durovernum Cantiacorum | site_type | `City/town/settlement` | `Town` | wd1-replace |
| El Salt | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| El Salt | period_start | `-60000` | `NULL` | wd1-clear |
| El Salt | site_type | `Cave Structures` | `Archaeological site` | wd1-replace |
| Fernacre | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Fernacre | period_start | `-4500` | `NULL` | wd1-clear |
| Figsbury Ring | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Figsbury Ring | period_start | `-4500` | `-3000` | wd1-replace |
| Fortifications of London | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Fortifications of London | period_start | `1` | `NULL` | wd1-clear |
| Galaxidi | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Galaxidi | period_start | `-1500` | `NULL` | wd1-clear |
| Glantane East | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Glantane East | period_start | `-4500` | `NULL` | wd1-clear |
| Goloring | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Goloring | period_start | `-1500` | `NULL` | wd1-clear |
| Grutas de Loltún | period_name | `3000 - 1500 BC` | `< 4500 BC` | wd1-derive-period-name |
| Grutas de Loltún | period_start | `-3000` | `-9000` | wd1-replace |
| Gurnard's Head | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Gurnard's Head | period_start | `-1000` | `NULL` | wd1-clear |
| Għar Dalam | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Għar Dalam | period_start | `-8000` | `NULL` | wd1-clear |
| Halwell Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Halwell Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Hartberg Megalithic Tomb | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Hartberg Megalithic Tomb | period_start | `-4500` | `-3000` | wd1-replace |
| Hohlenstein-Stadel | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Hohlenstein-Stadel | period_start | `-4500` | `NULL` | wd1-clear |
| Inka Wasi, Huancavelica | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inka Wasi, Huancavelica | period_start | `1000` | `NULL` | wd1-clear |
| Kamenica Tumulus | period_name | `4500 - 3000 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Kamenica Tumulus | period_start | `-4500` | `-1300` | wd1-replace |
| Kamenica Tumulus | site_type | `Necropolis/tombs complex` | `Mound/tumulus` | wd1-replace |
| Karakabaklı | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Karakabaklı | period_start | `-300` | `NULL` | wd1-clear |
| Kelsborrow Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Kelsborrow Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Khao Sai On Archaeological Site | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Khao Sai On Archaeological Site | period_start | `-1000` | `NULL` | wd1-clear |
| Khao Sai On Archaeological Site | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Khichuqaqa | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Khichuqaqa | period_start | `1` | `NULL` | wd1-clear |
| Khichuqaqa | site_type | `Rock art` | `NULL` | wd1-clear |
| Kierikki | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Kierikki | period_start | `-4500` | `NULL` | wd1-clear |
| Kierikki | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Knockmany Passage Tomb | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Knockmany Passage Tomb | period_start | `-4500` | `-3000` | wd1-replace |
| Konjic Mithraeum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Konjic Mithraeum | period_start | `1` | `NULL` | wd1-clear |
| Las Labradas | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Las Labradas | period_start | `500` | `NULL` | wd1-clear |
| Las Sepulturas | period_name | `500 - 1000 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Las Sepulturas | period_start | `500` | `-1400` | wd1-replace |
| Llaqta Qulluy, Tayacaja | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Llaqta Qulluy, Tayacaja | period_start | `1400` | `NULL` | wd1-clear |
| Llaqta Qulluy, Tayacaja | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Lupanar of Pompeii | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Lupanar of Pompeii | period_start | `-500` | `NULL` | wd1-clear |
| Lupanar of Pompeii | site_type | `Residence/villa/farmhouse` | `NULL` | wd1-clear |
| Makry Gialos | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Makry Gialos | period_start | `-1500` | `NULL` | wd1-clear |
| Mawk'allaqta, Espinar | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Mawk'allaqta, Espinar | period_start | `1` | `NULL` | wd1-clear |
| Misraħ Għar il-Kbir | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Misraħ Għar il-Kbir | period_start | `-1500` | `NULL` | wd1-clear |
| Misraħ Għar il-Kbir | site_type | `Road/avenue/trackway` | `NULL` | wd1-clear |
| Mnemata Site | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Mnemata Site | period_start | `-1500` | `NULL` | wd1-clear |
| Mnemata Site | site_type | `Cemetery` | `NULL` | wd1-clear |
| Musbury Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Musbury Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Mytilene | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Mytilene | period_start | `-3000` | `NULL` | wd1-clear |
| Nakhchivan Necropolises | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Nakhchivan Necropolises | period_start | `-2000` | `NULL` | wd1-clear |
| Nakhchivan Necropolises | site_type | `Necropolis/tombs complex` | `NULL` | wd1-clear |
| Nakovanj | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Nakovanj | period_start | `-1500` | `NULL` | wd1-clear |
| Niš | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Niš | period_start | `-500` | `NULL` | wd1-clear |
| Nordy Bank | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Nordy Bank | period_start | `-1500` | `NULL` | wd1-clear |
| Nîmes | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Nîmes | period_start | `-4500` | `NULL` | wd1-clear |
| Otišić | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Otišić | period_start | `1` | `NULL` | wd1-clear |
| Papeloze Kerk | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Papeloze Kerk | period_start | `-3000` | `NULL` | wd1-clear |
| Parque Arqueológico Zaculeu | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Parque Arqueológico Zaculeu | period_start | `1` | `NULL` | wd1-clear |
| Psychro Cave | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Psychro Cave | period_start | `-4000` | `-2800` | wd1-replace |
| Road Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Road Castle | period_start | `-1500` | `NULL` | wd1-clear |
| Rodadero Slides | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Rodadero Slides | period_start | `1100` | `NULL` | wd1-clear |
| Rodadero Slides | site_type | `Geological interest` | `NULL` | wd1-clear |
| Rodadero Slides | source_url | `https://www.atlasobscura.com/places/rodadero-slides` | `https://charismaticplanet.com/rodadero-slides-cusco-peru/` | wd1-replace |
| Salina Catacombs | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Salina Catacombs | period_start | `1` | `NULL` | wd1-clear |
| Sayacmarca | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Schalkholz Passage Grave | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Schalkholz Passage Grave | period_start | `-4500` | `NULL` | wd1-clear |
| Seaton Down | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Seaton Down | period_start | `-1000` | `NULL` | wd1-clear |
| Seaton Down | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Sigwells | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Sigwells | period_start | `-4500` | `NULL` | wd1-clear |
| Sirkeli Höyüğü | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Sirkeli Höyüğü | period_start | `-5000` | `NULL` | wd1-clear |
| Stenehed | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Stenehed | period_start | `-1500` | `NULL` | wd1-clear |
| Stone of the Guanches | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Stone of the Guanches | period_start | `-1000` | `NULL` | wd1-clear |
| Temple of Apollo | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Temple of Apollo | period_start | `-500` | `-700` | wd1-replace |
| Temple of Apollo | site_type | `Megalithic structures` | `Temple` | wd1-replace |
| Teurnia | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Teurnia | period_start | `-500` | `NULL` | wd1-clear |
| The Unfinished Obelisk | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| The Unfinished Obelisk | period_start | `-3000` | `-1473` | wd1-replace |
| The Warbanks | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| The Warbanks | period_start | `-4500` | `NULL` | wd1-clear |
| Thigibba Hammam Zouakra | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Thigibba Hammam Zouakra | period_start | `-300` | `NULL` | wd1-clear |
| Tipu | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tipu | period_start | `-300` | `NULL` | wd1-clear |
| Tomb of Darius II | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tomb of Darius II | period_start | `-423` | `NULL` | wd1-clear |
| Tregeseal East Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Tregeseal East Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Usnu Muqu | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Usnu Muqu | period_start | `1400` | `NULL` | wd1-clear |
| Uxmal | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Uxmal | period_start | `500` | `NULL` | wd1-clear |
| Via Militaris | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Via Militaris | period_start | `1` | `NULL` | wd1-clear |
| Vilcashuamán | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Vilcashuamán | period_start | `1000` | `NULL` | wd1-clear |
| Vindija Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Vindija Cave | period_start | `-41000` | `NULL` | wd1-clear |
| Whelpley Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Whelpley Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Wila Wilani, Tacna | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Wila Wilani, Tacna | period_start | `-7000` | `NULL` | wd1-clear |
| Wila Wilani, Tacna | site_type | `Rock art` | `NULL` | wd1-clear |
| Witzna | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Witzna | period_start | `1` | `NULL` | wd1-clear |
| Woodbury Hill, Worcestershire | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Woodbury Hill, Worcestershire | period_start | `-1500` | `NULL` | wd1-clear |
| Wysin | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Wysin | period_start | `-1500` | `NULL` | wd1-clear |
| Zakros | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Zakros | period_start | `-4000` | `-1900` | wd1-replace |
| Zakros | site_type | `Castle/palace` | `Palace` | wd1-replace |
| Zenobia Cham Palace Hotel | period_name | `1 - 500 AD` | `1500+ AD` | wd1-derive-period-name |
| Zenobia Cham Palace Hotel | period_start | `1` | `1920` | wd1-replace |
| Zenobia Cham Palace Hotel | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Zenobia Cham Palace Hotel | source_url | `NULL` | `http://www.cometosyria.com/en/hotels-in-syria/Hotels+in+Palm` | wd1-replace |
| Zona Arqueológica de Cholula | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Zona Arqueológica de Cholula | period_start | `-1500` | `NULL` | wd1-clear |
| Ħal Resqun Catacombs | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ħal Resqun Catacombs | period_start | `1` | `NULL` | wd1-clear |
| Ħal Resqun Catacombs | site_type | `Necropolis/tombs complex` | `Burial` | wd1-replace |
| Żejtun Roman Villa | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Żejtun Roman Villa | period_start | `-500` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Alte Burg, Langenenslingen | lat | `coordinates-unresolved` | Only Wikipedia and Wikidata give a point; the research project and the commune pages show no coordinates. |
| Witzna | lat | `coordinates-unresolved` | No source prints a point for Witzna; Wikipedia gives none. |
| Nakhchivan Necropolises | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent source with a point was found. |
| Żejtun Roman Villa | lat | `coordinates-unresolved` | Only Wikipedia prints a point for the Żejtun villa; no independent second source. |
| Llaqta Qulluy, Tayacaja | lat | `coordinates-unresolved` | No source found gives a point for Llaqta Qulluy in Tayacaja. |
| Arzachena Archaeological Park | lat | `coordinates-unresolved` | The park is a group of sites spread over several places; no source gives one point for it. |
| Rodadero Slides | lat | `coordinates-unresolved` | No source found gives a point for the Rodadero slides. |
| Makry Gialos | lat | `coordinates-unresolved` | No source gives a point for the villa; the stored point cannot be confirmed. |
| Papeloze Kerk | lat | `coordinates-unresolved` | Only Wikipedia (and Wikidata, the same family) give a point for D49, 0.03 km from the stored one; no second independent  |
| Tomb of Darius II | lat | `coordinates-unresolved` | Only the Wikipedia family (Persian article) prints a point for the tomb; no independent second source. |
| Beşkardeşler Kaya Mezarları | lat | `coordinates-unresolved` | No source found quotes coordinates for the Beşkardeşler rock tombs. |
| Khichuqaqa | lat | `coordinates-unresolved` | No source found gives a point for Khichuqaqa. |
| Via Militaris | lat | `coordinates-unresolved` | The Via Militaris is a long Roman road; no source gives a point for it at the stored location. |
| Thigibba Hammam Zouakra | lat | `coordinates-unresolved` | No source found quotes coordinates for Thigibba at Hammam Zouakra; Mysteria's point is for Thigibba Bure, 64 km away. |
| Las Labradas | lat | `coordinates-unresolved` | Only Wikidata gives a point for Las Labradas; no second independent source was found. |
| Zenobia Cham Palace Hotel | lat | `coordinates-unresolved` | No source found quotes coordinates for the hotel. |
| Khao Sai On Archaeological Site | lat | `coordinates-unresolved` | ISMEO's point for the Khao Sai On hill lies 5.4 km from the stored one and Wikipedia gives none; no two sources give one |
| The Warbanks | lat | `coordinates-unresolved` | No source prints a point for the Warbanks; Wikipedia gives none. |
| Mawk'allaqta, Espinar | site_type | `held-unreadable` | no counted answer in 3 rounds: quote fetch failed: https://www.chullostravelperu.com/blog/en/maukallaqta-in-espinar-ande |
| Stone of the Guanches | lat | `coordinates-unresolved` | No source found quotes coordinates for the Stone of the Guanches. |
| Mnemata Site | lat | `coordinates-unresolved` | The Wikipedia article prints no coordinates and no independent source with a point was found. |
| Las Sepulturas | lat | `coordinates-unresolved` | No source prints a point for Las Sepulturas. |
| Temple of Apollo | lat | `coordinates-unresolved` | No source found quotes coordinates for the Temple of Apollo at Didyma; the Wikipedia hit is a biography. |
| Fortifications of London | lat | `coordinates-unresolved` | The fortifications of London are a system of walls, gates and forts spread over the city; no source gives one point for  |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s022-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s022 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
