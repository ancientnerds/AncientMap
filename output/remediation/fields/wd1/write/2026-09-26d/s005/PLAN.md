# WD1 fields-wd1-2026-09-26d-s005: plan

Built 2026-09-29T15:32:39+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26d_fields-wd1-s005`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26d-s005:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 221 |
| sites_written | 100 |
| refused | 20 |
| cells:geom | 1 |
| cells:lat | 1 |
| cells:lon | 1 |
| cells:period_name | 92 |
| cells:period_start | 92 |
| cells:site_type | 29 |
| cells:source_url | 5 |
| refused:coordinates-unresolved | 20 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Accua | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Accua | period_start | `-500` | `NULL` | wd1-clear |
| Alepotrypa Cave | period_name | `4500 - 3000 BC` | `< 4500 BC` | wd1-derive-period-name |
| Alepotrypa Cave | period_start | `-4000` | `-6000` | wd1-replace |
| Argissa Magoula | geom | `0101000020E6100000B7E051DBEB323640AC424F9078CD4340` | `SRID=4326;POINT(22.34118 39.65986)` | wd1-point |
| Argissa Magoula | lat | `39.60524181242121` | `39.65986` | wd1-replace |
| Argissa Magoula | lon | `22.198911387910552` | `22.34118` | wd1-replace |
| Aslantepe Ruins | source_url | `https://www.inspirock.com/turkey/malatya/aslantepe-ruins-a11` | `https://www.kupi.com/en/explore/turkey/malatya/aslantepe-rui` | wd1-replace |
| Atella | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Atella | period_start | `-500` | `NULL` | wd1-clear |
| Atella | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Auga Punta | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Auga Punta | period_start | `1` | `NULL` | wd1-clear |
| Auga Punta | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Aves Ditch | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Aves Ditch | period_start | `-1500` | `NULL` | wd1-clear |
| Bada Valley Megaliths | period_name | `4500 - 3000 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Bada Valley Megaliths | period_start | `-4500` | `-1000` | wd1-replace |
| Balanced Rock, North Salem | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Balanced Rock, North Salem | period_start | `-8000` | `NULL` | wd1-clear |
| Balanced Rock, North Salem | source_url | `https://www.atlasobscura.com/places/balanced-rock` | `https://www.scenichudson.org/viewfinder/the-reasons-behind-t` | wd1-replace |
| Bartinney Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bartinney Castle | period_start | `-1500` | `NULL` | wd1-clear |
| Bartinney Castle | site_type | `City/town/settlement` | `Earthwork` | wd1-replace |
| Beenalaght | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Beenalaght | period_start | `-4500` | `NULL` | wd1-clear |
| Berry's Wood | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Berry's Wood | period_start | `-1000` | `NULL` | wd1-clear |
| Blackbury Camp | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Blackbury Camp | period_start | `-1000` | `-300` | wd1-replace |
| Box Gully Archaeological Site | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Box Gully Archaeological Site | period_start | `-500` | `NULL` | wd1-clear |
| Broch of Borwick | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Broch of Borwick | period_start | `1` | `-500` | wd1-replace |
| Bussock Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Bussock Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Capela de São Dinis | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Capela de São Dinis | period_start | `-4000` | `NULL` | wd1-clear |
| Carreg Samson | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Carreg Samson | period_start | `-4000` | `NULL` | wd1-clear |
| Castle of Cola | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Castle of Cola | period_start | `-2000` | `NULL` | wd1-clear |
| Cave of Maltravieso | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Cave of Maltravieso | period_start | `-66700` | `NULL` | wd1-clear |
| Chutixtiox | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Chutixtiox | period_start | `1200` | `NULL` | wd1-clear |
| City of David | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| City of David | period_start | `-3000` | `NULL` | wd1-clear |
| Clandon Barrow | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Clandon Barrow | period_start | `-4500` | `NULL` | wd1-clear |
| Clearbury Ring | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Clearbury Ring | period_start | `-1000` | `NULL` | wd1-clear |
| Cochabamba Archaeological Site | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Cochabamba Archaeological Site | period_start | `1000` | `NULL` | wd1-clear |
| Cochabamba Archaeological Site | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Crissa | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Crissa | period_start | `-2000` | `NULL` | wd1-clear |
| Deltaterrasserne | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Deltaterrasserne | period_start | `-3000` | `NULL` | wd1-clear |
| Deltaterrasserne | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Domica Cave | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Domica Cave | period_start | `-6000` | `NULL` | wd1-clear |
| Dragon Hill, Uffington | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Dragon Hill, Uffington | period_start | `-800` | `NULL` | wd1-clear |
| Edin's Hall Broch | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Edin's Hall Broch | period_start | `1` | `NULL` | wd1-clear |
| Emblance Downs Stone Circles | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Emblance Downs Stone Circles | period_start | `-4500` | `NULL` | wd1-clear |
| Flower's Barrow | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Flower's Barrow | period_start | `-1000` | `NULL` | wd1-clear |
| Fosbury Camp | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Fosbury Camp | period_start | `-1500` | `NULL` | wd1-clear |
| Giridava | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Giridava | period_start | `-500` | `NULL` | wd1-clear |
| Heelstone Ditch | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Heelstone Ditch | period_start | `-4000` | `NULL` | wd1-clear |
| Heelstone Ditch | site_type | `Earthwork` | `NULL` | wd1-clear |
| Huaca Esmeralda | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Huaca Esmeralda | period_start | `500` | `NULL` | wd1-clear |
| Huaca Esmeralda | site_type | `Castle/palace` | `NULL` | wd1-clear |
| Huichún | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Huichún | period_start | `1200` | `NULL` | wd1-clear |
| Huichún | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Huilai Monument Archaeology Park | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Huilai Monument Archaeology Park | period_start | `-2000` | `NULL` | wd1-clear |
| Huilai Monument Archaeology Park | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Ixkun Mayan Arqueológico Site | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Ixkun Mayan Arqueológico Site | period_start | `1` | `NULL` | wd1-clear |
| Kabah | period_name | `500 - 1000 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Kabah | period_start | `500` | `-400` | wd1-replace |
| Kanheri Caves | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kanheri Caves | period_start | `1` | `NULL` | wd1-clear |
| Karta | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Karta | period_start | `-8000` | `NULL` | wd1-clear |
| Karta | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Kitanaura Antik Kenti | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Kitanaura Antik Kenti | period_start | `1` | `NULL` | wd1-clear |
| Klimonas | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Kudaro | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Kudaro | period_start | `-38000` | `NULL` | wd1-clear |
| Kudaro | site_type | `Cave Structures` | `Cave` | wd1-replace |
| La Cobata | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| La Cobata | period_start | `1` | `-1000` | wd1-replace |
| Largin Castle | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Largin Castle | period_start | `-1000` | `NULL` | wd1-clear |
| Leaze Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Leaze Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Los Bañales | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Los Bañales | period_start | `-500` | `NULL` | wd1-clear |
| Machu Pitumarka | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Machu Pitumarka | period_start | `1400` | `NULL` | wd1-clear |
| Machu Pitumarka | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Mezine | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd1-derive-period-name |
| Mezine | period_start | `-500` | `-10000` | wd1-replace |
| Mezine | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Munigua | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Munigua | period_start | `1` | `NULL` | wd1-clear |
| Naupa Iglesia (Choquequilla) | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Naupa Iglesia (Choquequilla) | period_start | `500` | `NULL` | wd1-clear |
| Naupa Iglesia (Choquequilla) | site_type | `Megalithic stones` | `NULL` | wd1-clear |
| Nausharo | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Nemogram Stupa | site_type | `Temple complex` | `NULL` | wd1-clear |
| Nichoria | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Nichoria | period_start | `-2000` | `-3500` | wd1-replace |
| Notgrove Long Barrow | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Notgrove Long Barrow | period_start | `-3000` | `-3600` | wd1-replace |
| Nyons | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Nyons | period_start | `-1500` | `NULL` | wd1-clear |
| Oppidum Steinsburg | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Oppidum Steinsburg | period_start | `-500` | `NULL` | wd1-clear |
| Pellana | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Pellana | period_start | `-1500` | `-2500` | wd1-replace |
| Pertosa Caves | period_name | `1 - 500 AD` | `3000 - 1500 BC` | wd1-derive-period-name |
| Pertosa Caves | period_start | `1` | `-2000` | wd1-replace |
| Pirca Pirca, Lima | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Pirca Pirca, Lima | period_start | `1400` | `NULL` | wd1-clear |
| Pirca Pirca, Lima | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Portus Lemanis | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Portus Lemanis | period_start | `1` | `NULL` | wd1-clear |
| Pyramid of Hetepheres I | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Pyramid of Hetepheres I | period_start | `-2600` | `NULL` | wd1-clear |
| Pyramid of Hetepheres I | source_url | `https://www.marsaalamtours.org/en/the-pyramid-of-queen-hetep` | `https://en.wikipedia.org/wiki/Pyramid_G1-a` | wd1-replace |
| Rastrojón | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Redbourn | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Redbourn | period_start | `-1000` | `NULL` | wd1-clear |
| Roman Theatre of Arles | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd1-derive-period-name |
| Roman Theatre of Arles | period_start | `1` | `-40` | wd1-replace |
| Roman Theatre, Bregenz | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Roman Theatre, Bregenz | period_start | `1` | `NULL` | wd1-clear |
| Round Loaf | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Round Loaf | period_start | `-4500` | `NULL` | wd1-clear |
| Rozafa Castle | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Rozafa Castle | period_start | `-1500` | `-400` | wd1-replace |
| San Lázaro Roman Aqueduct | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| San Lázaro Roman Aqueduct | period_start | `-500` | `1` | wd1-replace |
| Sancreed Beacon | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Sancreed Beacon | period_start | `-4500` | `NULL` | wd1-clear |
| Santa Rita | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Santa Rita | period_start | `-3000` | `-1200` | wd1-replace |
| Scupi | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Scupi | period_start | `-500` | `NULL` | wd1-clear |
| Sechin Alto | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Sechin Alto | period_start | `-3000` | `NULL` | wd1-clear |
| Sechin Alto | site_type | `Pyramid complex` | `Mound/tumulus` | wd1-replace |
| Sikri Stupa | site_type | `Temple complex` | `NULL` | wd1-clear |
| Skorba Temples | period_name | `4500 - 3000 BC` | `< 4500 BC` | wd1-derive-period-name |
| Skorba Temples | period_start | `-4500` | `-4850` | wd1-replace |
| Sliprännor i Gantofta | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Sliprännor i Gantofta | period_start | `-1500` | `NULL` | wd1-clear |
| Smythe's Megalith | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Smythe's Megalith | period_start | `-4000` | `NULL` | wd1-clear |
| Smythe's Megalith | site_type | `Megalithic stones` | `Tomb` | wd1-replace |
| Stenseby Passage Grave | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Stenseby Passage Grave | period_start | `-4500` | `NULL` | wd1-clear |
| Sussex Greensand Way | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Sussex Greensand Way | period_start | `1` | `NULL` | wd1-clear |
| Svileuva | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Svileuva | period_start | `1` | `NULL` | wd1-clear |
| Tarawasi | site_type | `Temple complex` | `NULL` | wd1-clear |
| Tarmatambo | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Tarmatambo | period_start | `1200` | `NULL` | wd1-clear |
| Tarmatambo | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Taula | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Taula | period_start | `-1500` | `NULL` | wd1-clear |
| Teatro Romano | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Teatro Romano | period_start | `1` | `NULL` | wd1-clear |
| Temple of Augustus, Barcelona | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Temple of Augustus, Barcelona | period_start | `-3000` | `-100` | wd1-replace |
| Teotihuacan - Palace Atelelco | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Teotihuacan - Palace Atelelco | period_start | `450` | `NULL` | wd1-clear |
| Teotihuacan - Palace Atelelco | site_type | `Castle/palace` | `NULL` | wd1-clear |
| Teotihuacan - Palace Atelelco | source_url | `https://www.atlasobscura.com/places/palace-atetelco` | `https://www.aragon.unam.mx/teotihuacan/content/palacios/atet` | wd1-replace |
| The Bull Ring | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| The Bull Ring | period_start | `-4500` | `NULL` | wd1-clear |
| The Knave | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| The Knave | period_start | `-1500` | `NULL` | wd1-clear |
| Torre de Almofala | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Torre de Almofala | period_start | `100` | `NULL` | wd1-clear |
| Torre de Almofala | site_type | `Temple complex` | `Temple` | wd1-replace |
| Torre de Almofala | source_url | `NULL` | `https://www.e-cultura.pt/patrimonio_item/7505` | wd1-replace |
| Uragh Stone Circle | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Uragh Stone Circle | period_start | `-4500` | `NULL` | wd1-clear |
| Wamanmarka, Chumbivilcas | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Wamanmarka, Chumbivilcas | period_start | `1` | `NULL` | wd1-clear |
| Wamanmarka, Chumbivilcas | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Woodhouse Hill Fort | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Woodhouse Hill Fort | period_start | `-1000` | `NULL` | wd1-clear |
| Yelland Stone Rows | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Yelland Stone Rows | period_start | `-3000` | `NULL` | wd1-clear |
| Yuraq Mach'ay | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Yuraq Mach'ay | period_start | `1` | `NULL` | wd1-clear |
| Yuraq Mach'ay | site_type | `Rock art` | `NULL` | wd1-clear |
| Zar Cave | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Zar Cave | period_start | `-500` | `NULL` | wd1-clear |
| Ñawpallaqta, Fajardo | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Ñawpallaqta, Fajardo | period_start | `1400` | `NULL` | wd1-clear |
| Ñawpallaqta, Fajardo | site_type | `City/town/settlement` | `NULL` | wd1-clear |
| Żukczyn | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Żukczyn | period_start | `-3000` | `NULL` | wd1-clear |
| Žitorađa | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Žitorađa | period_start | `1` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Huichún | lat | `coordinates-unresolved` | No source found gives a point for Huichún. |
| Aslantepe Ruins | lat | `coordinates-unresolved` | No source found quotes coordinates for Arslantepe. |
| Kudaro | lat | `coordinates-unresolved` | No source (Wikipedia, Wikidata, the cave database) gives a point for Kudaro; the stored point cannot be confirmed. |
| Taula | lat | `coordinates-unresolved` | Taula is a type of monument found across Menorca; the stored point is a placeholder and no source gives one point for it |
| Stenseby Passage Grave | lat | `coordinates-unresolved` | Wikipedia's point is the hamlet of Stenseby and the Megalithic Portal points are 0.5-0.8 km away; no two independent sou |
| Rastrojón | lat | `coordinates-unresolved` | No source prints a point for Rastrojón; Wikipedia gives none. |
| La Cobata | lat | `coordinates-unresolved` | The stored point is the main plaza of Santiago Tuxtla, where the head now stands; no source gives a point for the find p |
| Balanced Rock, North Salem | lat | `coordinates-unresolved` | Only the Megalithic Portal quotes a point (0.11 km from the stored one); no independent second source confirms it. |
| Pyramid of Hetepheres I | lat | `coordinates-unresolved` | The pyramid of Hetepheres I is G1-a at Giza, about 21 km north of the stored point, but only Wikipedia gives its point;  |
| Temple of Augustus, Barcelona | lat | `coordinates-unresolved` | Only Wikidata (with the Wikipedia articles) gives a point; no independent second source quotes coordinates. |
| Karta | lat | `coordinates-unresolved` | Karta is the Aboriginal name of Kangaroo Island; no source gives a point for a site of that name. |
| Wamanmarka, Chumbivilcas | lat | `coordinates-unresolved` | No source found gives a point for Wamanmarka in Chumbivilcas. |
| Capela de São Dinis | lat | `coordinates-unresolved` | Only the Mora megalithism museum prints decimal coordinates for the anta; no second independent source gives a quotable  |
| Naupa Iglesia (Choquequilla) | lat | `coordinates-unresolved` | No source found gives a point for Naupa Iglesia; the Wikipedia hit (Temple of the Moon) lies 37.6 km away. |
| Chutixtiox | lat | `coordinates-unresolved` | Only Wikipedia gives a point for Chutixtiox; no independent source gives one. |
| Teotihuacan - Palace Atelelco | lat | `coordinates-unresolved` | No source found gives a point for the Atetelco compound. |
| Torre de Almofala | lat | `coordinates-unresolved` | No source found gives a point for the Torre de Almofala. |
| Rozafa Castle | lat | `coordinates-unresolved` | Only Wikipedia prints a point for Rozafa Castle; no independent source with coordinates was found. |
| Sikri Stupa | lat | `coordinates-unresolved` | The stored point is the Lahore Museum, where the stupa is displayed; no source gives a point for the find site at Sikri  |
| Accua | lat | `coordinates-unresolved` | No source prints a point for Accua; Wikipedia gives none. |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26d_fields-wd1-s005-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26d-s005 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
