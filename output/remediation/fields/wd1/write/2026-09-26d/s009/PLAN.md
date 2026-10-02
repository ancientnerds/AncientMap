# WD1 fields-wd1-2026-09-26d-s009: plan

Built 2026-09-29T15:36:32+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s009`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s009:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 221 |
| sites_written | 100 |
| refused | 21 |
| cells:geom | 1 |
| cells:lat | 1 |
| cells:lon | 1 |
| cells:period_name | 92 |
| cells:period_start | 91 |
| cells:site_type | 30 |
| cells:source_url | 5 |
| refused:coordinates-unresolved | 21 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Aglaureion | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Aglaureion | period_start | `-500` | `NULL` | wd1-clear |
| Aguntum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Aguntum | period_start | `1` | `NULL` | wd1-clear |
| Al Naslaa | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Al Naslaa | period_start | `1` | `NULL` | wd1-clear |
| Alam Bridge Inscriptions | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Alam Bridge Inscriptions | period_start | `-500` | `NULL` | wd1-clear |
| Alverdiscott | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Alverdiscott | period_start | `-1000` | `NULL` | wd1-clear |
| Ancient Stadium of Nemea | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Ancient Stadium of Nemea | period_start | `-1500` | `-330` | wd1-replace |
| Ancient Stadium of Nemea | source_url | `https://nemeacenter.berkeley.edu/the-ancient-stadium/` | `https://en.wikipedia.org/wiki/Stadium_at_Nemea` | wd1-replace |
| Annadorn Dolmen | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Annadorn Dolmen | period_start | `-4000` | `NULL` | wd1-clear |
| Anta de Carcavelos | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Anta de Carcavelos | period_start | `-4000` | `NULL` | wd1-clear |
| Arbury Banks, Hertfordshire | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Arbury Banks, Hertfordshire | period_start | `-2000` | `NULL` | wd1-clear |
| Astuvansalmi Rock Paintings | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Astuvansalmi Rock Paintings | period_start | `-4500` | `-3000` | wd1-replace |
| Badshot Lea Long Barrow | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Badshot Lea Long Barrow | period_start | `-4000` | `NULL` | wd1-clear |
| Ballygroll Prehistoric Landscape | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ballygroll Prehistoric Landscape | period_start | `-4000` | `NULL` | wd1-clear |
| Barclodiad y Gawres | period_name | `< 4500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Barclodiad y Gawres | period_start | `-5000` | `-3000` | wd1-replace |
| Bela Palanka | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Bela Palanka | period_start | `-500` | `NULL` | wd1-clear |
| Berry Mound | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Berry Mound | period_start | `-500` | `NULL` | wd1-clear |
| Blacker's Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Blacker's Hill | period_start | `-1000` | `NULL` | wd1-clear |
| Breitenbach - Archaeological Site | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Breitenbach - Archaeological Site | period_start | `-5000` | `NULL` | wd1-clear |
| Breitenbach - Archaeological Site | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Caer Drewyn | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Caer Drewyn | period_start | `-500` | `NULL` | wd1-clear |
| Caer y Twr | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Caer y Twr | period_start | `1` | `NULL` | wd1-clear |
| Camel Carving Site | site_type | `Petroglyphs` | `Rock relief/carving` | wd1-replace |
| Cave of Niaux | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cave of Niaux | period_start | `-15000` | `NULL` | wd1-clear |
| Chalai, Thessaly | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Chalai, Thessaly | period_start | `-500` | `NULL` | wd1-clear |
| Cloghanmore | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Cloghanmore | period_start | `-4000` | `NULL` | wd1-clear |
| Cocev Kamen | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cocev Kamen | period_start | `-12000` | `NULL` | wd1-clear |
| Copán Ruins | period_name | `500 - 1000 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Copán Ruins | period_start | `500` | `-1000` | wd1-replace |
| Copán Ruins | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Daorson | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Daorson | period_start | `-500` | `-1700` | wd1-replace |
| Dmanisi | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Dmanisi | period_start | `-4500` | `NULL` | wd1-clear |
| Dowsborough Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dowsborough Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Dzibilchaltun | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Dzibilchaltun | period_start | `1` | `NULL` | wd1-clear |
| El Rey Zona Arqueologica | period_name | `1000 - 1500 AD` | `1 - 500 AD` | wd1-derive-period-name |
| El Rey Zona Arqueologica | period_start | `1000` | `101` | wd1-replace |
| El Rey Zona Arqueologica | site_type | `Temple complex` | `Settlement` | wd1-replace |
| Fonte Sacra Su Tempiesu | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Fonte Sacra Su Tempiesu | period_start | `-2000` | `NULL` | wd1-clear |
| Fonte Sacra Su Tempiesu | site_type | `Temple complex` | `Temple` | wd1-replace |
| Frourio Hill | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Frourio Hill | period_start | `-1000` | `NULL` | wd1-clear |
| GOLOGOÇ VİRANŞEHİR ŞANLIURFA TARİHİ KEMER | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| GOLOGOÇ VİRANŞEHİR ŞANLIURFA TARİHİ KEMER | period_start | `-4500` | `NULL` | wd1-clear |
| GOLOGOÇ VİRANŞEHİR ŞANLIURFA TARİHİ KEMER | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Gabarnmung Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Gabarnmung Cave | period_start | `-500` | `NULL` | wd1-clear |
| Gabarnmung Cave | site_type | `Cave Structures` | `Rock art` | wd1-replace |
| Gorzyczki, Silesian Voivodeship | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Gorzyczki, Silesian Voivodeship | period_start | `-4000` | `NULL` | wd1-clear |
| Grange Stone Circle | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Grange Stone Circle | period_start | `-2000` | `NULL` | wd1-clear |
| Grubstones | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Grubstones | period_start | `-4500` | `NULL` | wd1-clear |
| Hatay Altınözü Yunushanı Gelinler Dağı Nekropolü | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Hatay Altınözü Yunushanı Gelinler Dağı Nekropolü | period_start | `1` | `NULL` | wd1-clear |
| Hisar Hill | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Hisar Hill | period_start | `-4000` | `NULL` | wd1-clear |
| Hoarstones | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Hoarstones | period_start | `-4500` | `NULL` | wd1-clear |
| Home Tombs | source_url | `https://www.dogadatatil.com/evkaya-tombs-rock-tomb-houses-ka` | `NULL` | wd1-clear |
| Hotié de Viviane | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Hotié de Viviane | period_start | `-4500` | `NULL` | wd1-clear |
| House of Julia Felix, Pompeii | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| House of Julia Felix, Pompeii | period_start | `1` | `NULL` | wd1-clear |
| House of the Vettii, Pompeii | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| House of the Vettii, Pompeii | period_start | `1` | `NULL` | wd1-clear |
| Huandacareo | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Ide, Devon | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ide, Devon | period_start | `1` | `NULL` | wd1-clear |
| Inka Raqay | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inka Raqay | period_start | `1400` | `NULL` | wd1-clear |
| Inka Raqay | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Inka Wasi, Ayacucho | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inka Wasi, Ayacucho | period_start | `1000` | `NULL` | wd1-clear |
| Inka Wasi, Ayacucho | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Inkilltambo | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inkilltambo | period_start | `1000` | `NULL` | wd1-clear |
| Intiyuq K'uchu | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Intiyuq K'uchu | period_start | `1` | `NULL` | wd1-clear |
| Intiyuq K'uchu | site_type | `Rock art` | `NULL` | wd1-clear |
| Julliberrie's Grave | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Julliberrie's Grave | period_start | `-4000` | `NULL` | wd1-clear |
| Kanamarka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Kanamarka | period_start | `1000` | `NULL` | wd1-clear |
| Kanamarka | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Keal Cotes | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Keal Cotes | period_start | `-3000` | `NULL` | wd1-clear |
| Kotosh | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Kotosh | period_start | `-4500` | `-2000` | wd1-replace |
| Lamay | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Lamay | period_start | `1` | `NULL` | wd1-clear |
| Lamay | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Maria Reiche Museum | period_name | `1500+ AD` | `NULL` | wd1-derive-period-name |
| Maria Reiche Museum | period_start | `1994` | `NULL` | wd1-clear |
| Maria Reiche Museum | source_url | `https://www.atlasobscura.com/places/maria-reiche-museum` | `https://myperuguide.com/maria-reiche` | wd1-replace |
| Markansaya | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Markansaya | period_start | `1400` | `NULL` | wd1-clear |
| Markansaya | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Markušica | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Markušica | period_start | `-500` | `NULL` | wd1-clear |
| Marsoulas Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Marsoulas Cave | period_start | `-500` | `NULL` | wd1-clear |
| Mausoleum of Tangun | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Mausoleum of Tangun | period_start | `-3000` | `NULL` | wd1-clear |
| Mawk'allaqta, La Unión | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Mawk'allaqta, La Unión | period_start | `500` | `NULL` | wd1-clear |
| Mawk'allaqta, La Unión | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Mawk'allaqta, Sandia | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Mawk'allaqta, Sandia | period_start | `1400` | `NULL` | wd1-clear |
| Mawk'allaqta, Sandia | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Medusa Mozaiği | site_type | `Archaeological site` | `NULL` | wd1-clear |
| Mellor Hill Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Mellor Hill Fort | period_start | `-1500` | `NULL` | wd1-clear |
| Monte Grossu | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Monte Grossu | period_start | `-3000` | `NULL` | wd1-clear |
| Monte Grossu | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Monument of Prusias II | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Monument of Prusias II | period_start | `-500` | `NULL` | wd1-clear |
| Mortuary Temple of Seti I | site_type | `Temple complex` | `Temple` | wd1-replace |
| Oppidum de Verduron | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Oppidum de Verduron | period_start | `-1500` | `-300` | wd1-replace |
| Padderbury Top | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Padderbury Top | period_start | `-2000` | `NULL` | wd1-clear |
| Pañamarca | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Pañamarca | period_start | `1` | `550` | wd1-replace |
| Pañamarca | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Petuaria | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Petuaria | period_start | `1` | `NULL` | wd1-clear |
| Pont du Gard | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Pont sur la Laye | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Pont sur la Laye | period_start | `1` | `NULL` | wd1-clear |
| Posbury Hill Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Posbury Hill Fort | period_start | `-1000` | `NULL` | wd1-clear |
| Prehistoric Fortress Straževica (Dragaljevo) | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Prehistoric Fortress Straževica (Dragaljevo) | period_start | `-1500` | `NULL` | wd1-clear |
| Prehistoric Fortress Straževica (Dragaljevo) | site_type | `Fortress/citadel` | `NULL` | wd1-clear |
| Pukara, Coporaque | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Pukara, Coporaque | period_start | `1400` | `NULL` | wd1-clear |
| Pukara, Coporaque | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Qasr Chbib | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Qasr Chbib | period_start | `-1500` | `NULL` | wd1-clear |
| Qasr Chbib | site_type | `Temple complex` | `NULL` | wd1-clear |
| Qasr el-Sagha | geom | `0101000020E610000062F2BEA3C5D73E40E830033CF44E3D40` | `SRID=4326;POINT(30.677915 29.595145)` | wd1-point |
| Qasr el-Sagha | lat | `29.30841422155291` | `29.595145` | wd1-replace |
| Qasr el-Sagha | lon | `30.84285949146068` | `30.677915` | wd1-replace |
| Qasr el-Sagha | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Qasr el-Sagha | period_start | `-4500` | `-1900` | wd1-replace |
| Qasr el-Sagha | site_type | `Temple complex` | `Temple` | wd1-replace |
| Qullqapampa | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Qullqapampa | period_start | `1000` | `NULL` | wd1-clear |
| Qullqapampa | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Rock Carvings at Møllerstufossen | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Rock Carvings at Møllerstufossen | period_start | `-4000` | `NULL` | wd1-clear |
| Roman Tomb of Silistra | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Tomb of Silistra | period_start | `1` | `NULL` | wd1-clear |
| Roses, Girona | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Roses, Girona | period_start | `-1500` | `NULL` | wd1-clear |
| Sa Cudia Cremada | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Sa Cudia Cremada | period_start | `-2000` | `NULL` | wd1-clear |
| Sa Cudia Cremada | site_type | `Megalithic structures` | `City/town/settlement` | wd1-replace |
| Sacsayhuamán | site_type | `Megalithic structures` | `Fortress/citadel` | wd1-replace |
| Sacul | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Sacul | period_start | `500` | `NULL` | wd1-clear |
| Savaria Mithraeum | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Savaria Mithraeum | period_start | `1` | `NULL` | wd1-clear |
| Slwch Tump | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Slwch Tump | period_start | `-1500` | `NULL` | wd1-clear |
| Sperris Quoit | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Sperris Quoit | period_start | `-5000` | `-3500` | wd1-replace |
| Stadion Laodikeia | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Stadion Laodikeia | period_start | `-500` | `79` | wd1-replace |
| Stadion Laodikeia | source_url | `http://www.tuerkei-antik.de/Stadien/laodikeia_en.htm` | `https://dijital.link/stadion-laodikeia` | wd1-replace |
| Stobno, Lower Silesian Voivodeship | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Stobno, Lower Silesian Voivodeship | period_start | `-3000` | `NULL` | wd1-clear |
| Suessula | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Suessula | period_start | `-500` | `NULL` | wd1-clear |
| Tappoch Broch | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Tappoch Broch | period_start | `1` | `NULL` | wd1-clear |
| Tapınak | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tapınak | period_start | `-500` | `NULL` | wd1-clear |
| Tapınak | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Tayma | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Tayma | period_start | `-1500` | `NULL` | wd1-clear |
| Tedbury Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Tedbury Camp | period_start | `-1000` | `NULL` | wd1-clear |
| Temple of the Revelation of Amun | site_type | `Temple complex` | `Temple` | wd1-replace |
| Temple of the Revelation of Amun | source_url | `https://www.touregypt.net/featurestories/templeoforacle.htm` | `https://egyptunitedtours.com/temple-of-amun/` | wd1-replace |
| The Ridgeway | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| The Ridgeway | period_start | `-4500` | `NULL` | wd1-clear |
| Tregele | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Tregele | period_start | `-4000` | `NULL` | wd1-clear |
| Tunanmarca | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Veldwezelt-Hezerwater | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Veldwezelt-Hezerwater | period_start | `-50000` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Home Tombs | lat | `coordinates-unresolved` | No source found quotes coordinates for the Evkaya tombs. |
| Mawk'allaqta, La Unión | lat | `coordinates-unresolved` | No source found gives a point for Mawk'allaqta in La Unión. |
| Alam Bridge Inscriptions | lat | `coordinates-unresolved` | Only Wikipedia gives a point for the Alam Bridge inscriptions; no second independent source was found. |
| Tapınak | lat | `coordinates-unresolved` | No source found quotes coordinates for this temple. |
| Daorson | lat | `coordinates-unresolved` | Wikipedia prints no point and the Digital Atlas of the Roman Empire is 1.1 km from the stored point; no two independent  |
| Camel Carving Site | lat | `coordinates-unresolved` | No source found gives a point for the Camel Site. |
| Mortuary Temple of Seti I | lat | `coordinates-unresolved` | No source gives an independent point for the temple of Seti I at Qurna. |
| Hatay Altınözü Yunushanı Gelinler Dağı Nekropolü | lat | `coordinates-unresolved` | No source found quotes coordinates for the Gelinler Dağı necropolis. |
| Markušica | lat | `coordinates-unresolved` | Only Wikipedia gives an independent point; the travel aggregators repeat the Wikidata figures, so no second independent  |
| Maria Reiche Museum | lat | `coordinates-unresolved` | No source found gives a point for the Maria Reiche Museum. |
| Medusa Mozaiği | lat | `coordinates-unresolved` | No source found quotes coordinates for the Medusa mosaic at Kibyra. |
| GOLOGOÇ VİRANŞEHİR ŞANLIURFA TARİHİ KEMER | lat | `coordinates-unresolved` | No source found quotes coordinates for the arch. |
| Monument of Prusias II | lat | `coordinates-unresolved` | Only the Wikipedia family gives a point; the other points found (Apple Maps, Qualla) repeat Wikidata's, so no independen |
| Markansaya | lat | `coordinates-unresolved` | No source found gives a point for Markansaya. |
| Temple of the Revelation of Amun | lat | `coordinates-unresolved` | No two independent sources give a point for the oracle temple at Aghurmi. |
| Ballygroll Prehistoric Landscape | lat | `coordinates-unresolved` | Only Wikipedia gives a point that can be quoted; the Great Britain Guide prints its coordinates in a form that cannot be |
| Lamay | lat | `coordinates-unresolved` | Lamay is the Central Group of Dzibanché; no source gives a point for this group. |
| Stadion Laodikeia | lat | `coordinates-unresolved` | No source found quotes coordinates for the stadium of Laodikeia. |
| Mawk'allaqta, Sandia | lat | `coordinates-unresolved` | No source found gives a point for Mawk'allaqta in Sandia. |
| Pukara, Coporaque | lat | `coordinates-unresolved` | No source found gives a point for Pukara in Coporaque. |
| Qullqapampa | lat | `coordinates-unresolved` | No source found gives a point for Qullqapampa. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s009-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s009 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
