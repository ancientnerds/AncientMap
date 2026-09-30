# WD1 fields-wd1-2026-09-26c-s001: plan

Built 2026-09-26T19:53:36+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26c_fields-wd1-s001`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26c-s001:<site>:<column>`.

| counter | value |
|---|---|
| sites | 46 |
| cells | 89 |
| sites_written | 46 |
| refused | 9 |
| cells:period_name | 39 |
| cells:period_start | 38 |
| cells:site_type | 10 |
| cells:source_url | 2 |
| refused:coordinates-unresolved | 8 |
| refused:country-changes | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Alderman's Barrow | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Alderman's Barrow | period_start | `-4500` | `-2500` | wd1-replace |
| Ales Stenar | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Ales Stenar | period_start | `1` | `600` | wd1-replace |
| Amos Antik Kenti | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Amos Antik Kenti | period_start | `-500` | `-1000` | wd1-replace |
| Ancient City of Laodicea | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd1-derive-period-name |
| Ancient City of Laodicea | period_start | `-500` | `-5500` | wd1-replace |
| Broch of West Burrafirth | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Broch of West Burrafirth | period_start | `-1000` | `NULL` | wd1-clear |
| Cancuén | period_name | `500 - 1000 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Cancuén | period_start | `500` | `300` | wd1-replace |
| Colcampata | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Colcampata | period_start | `1000` | `NULL` | wd1-clear |
| Dabarkot | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Dabarkot | period_start | `-5000` | `-3500` | wd1-replace |
| Dabarkot | site_type | `Mound/tumulus` | `Settlement` | wd1-replace |
| Dankirke | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Dolmens of Sardinia | site_type | `Necropolis/tombs complex` | `Dolmen` | wd1-replace |
| Dolmens of Sardinia | source_url | `https://virtualarchaeology.sardegnacultura.it/index.php/en/a` | `https://journals.ed.ac.uk/lithicstudies/article/view/1943` | wd1-replace |
| Eleusis | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Eleusis | period_start | `-1500` | `-2000` | wd1-replace |
| Eleusis | source_url | `https://www.britannica.com/place/Eleusis-ancient-city-Greece` | `https://fr.wikipedia.org/wiki/Sanctuaire_d%27%C3%89leusis` | wd1-replace |
| Gate of the Sun | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Gate of the Sun | period_start | `1` | `NULL` | wd1-clear |
| Gough's Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Gough's Cave | period_start | `-500` | `NULL` | wd1-clear |
| Gruta do Gentio | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Gruta do Gentio | period_start | `-6000` | `NULL` | wd1-clear |
| Harrow Way | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Harrow Way | period_start | `-1500` | `NULL` | wd1-clear |
| Henmore Brook | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Henmore Brook | period_start | `-5000` | `NULL` | wd1-clear |
| Jordbro Grave Field | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Jordbro Grave Field | period_start | `-1500` | `NULL` | wd1-clear |
| Kastros | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Kow Swamp Archaeological Site | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Kow Swamp Archaeological Site | period_start | `-11000` | `NULL` | wd1-clear |
| Lactodurum | site_type | `City/town/settlement` | `Town` | wd1-replace |
| Llamayuq | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Llamayuq | period_start | `1` | `NULL` | wd1-clear |
| Mongchontoseong Earthen Fortification | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Mongchontoseong Earthen Fortification | period_start | `-100` | `201` | wd1-replace |
| Moral-Reforma | period_name | `500 - 1000 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Moral-Reforma | period_start | `500` | `-300` | wd1-replace |
| Must Farm Bronze Age Settlement | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| New Guinea II Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| New Guinea II Cave | period_start | `-500` | `NULL` | wd1-clear |
| Olmeto | period_name | `4500 - 3000 BC` | `1000 - 1500 AD` | wd1-derive-period-name |
| Olmeto | period_start | `-4000` | `1329` | wd1-replace |
| Ourense | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Ourense | period_start | `-500` | `1` | wd1-replace |
| Passau | period_name | `1 - 500 AD` | `< 4500 BC` | wd1-derive-period-name |
| Passau | period_start | `1` | `-4900` | wd1-replace |
| Pedra das Cabras | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Pedra das Cabras | period_start | `-4000` | `-2200` | wd1-replace |
| Pucará, Puno | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Pucará, Puno | period_start | `-3000` | `-1400` | wd1-replace |
| Robin Hood's Butts | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Robin Hood's Butts | period_start | `-4500` | `NULL` | wd1-clear |
| Roman Bridge, Trier | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Roman Bridge, Trier | period_start | `1` | `-17` | wd1-replace |
| Roman Emperors Route | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Roman Emperors Route | period_start | `-500` | `NULL` | wd1-clear |
| Roman Emperors Route | site_type | `Road/avenue/trackway` | `NULL` | wd1-clear |
| Ruinas Romanas de Mérida | site_type | `Temple complex` | `City` | wd1-replace |
| Sagunto | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Saoba Stone Pillars | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Saoba Stone Pillars | period_start | `-1000` | `NULL` | wd1-clear |
| Saoba Stone Pillars | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Simanya Cave | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Simanya Cave | period_start | `1` | `NULL` | wd1-clear |
| Slapton Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Slapton Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Stravomyti Cave | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Stravomyti Cave | period_start | `-4000` | `NULL` | wd1-clear |
| Tayata | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Temple of Antas, Fluminimaggiore | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Temple of Antas, Fluminimaggiore | period_start | `-3000` | `-900` | wd1-replace |
| Templos de Tarxien | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Templos de Tarxien | period_start | `-3000` | `-3600` | wd1-replace |
| Tripiti - Archaeological Site | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Tripiti - Archaeological Site | period_start | `-4500` | `-3000` | wd1-replace |
| Tŷ Newydd Burial Chamber | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Tŷ Newydd Burial Chamber | period_start | `-5000` | `NULL` | wd1-clear |
| West Woods | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| West Woods | period_start | `-4500` | `NULL` | wd1-clear |
| Ziari | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Ziari | period_start | `-3000` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Llamayuq | lat | `coordinates-unresolved` | Neither the English Wikipedia article nor its Wikidata item (which has no P625) gives coordinates, and Hostnig's field r |
| Dabarkot | lat | `coordinates-unresolved` | Pakistan's Department of Archaeology and Museums gives Daber Kot at 30.083333, 68.683333 (about 40 km from the stored po |
| Dolmens of Sardinia | lat | `coordinates-unresolved` | The entry is the collective group of the more than 200 dolmens scattered over central-northern Sardinia (Luras, Mores, M |
| Harrow Way | lat | `coordinates-unresolved` | The Harrow Way is a linear prehistoric trackway said to run from Seaton in Devon to Dover in Kent (its western section e |
| Eleusis | lat | `country-changes` | the new point lies in [], the site says Greece |
| Tayata | lat | `coordinates-unresolved` | Only the Megalithic Portal gives a point for the Tayata site (17.35 N, 97.57 W, flagged as scaled from a bad map), and t |
| Kastros | lat | `coordinates-unresolved` | The Neolithic settlement lies on the south flank of Cape Apostolos Andreas, about 4 km north of the monastery, so the st |
| Gruta do Gentio | lat | `coordinates-unresolved` | The two sources that give a point disagree by about 4 km: the 2024 Frontiers in Microbiology paper (after Dias et al. 19 |
| Roman Emperors Route | lat | `coordinates-unresolved` | The Roman Emperors Route is a modern tourism and archaeology project, a 600 km route linking separate Roman sites across |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26c_fields-wd1-s001-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26c-s001 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
