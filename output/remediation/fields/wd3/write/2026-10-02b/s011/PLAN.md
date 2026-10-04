# WD3 fields-wd3-2026-10-02b-s011: plan

Built 2026-10-04T12:55:12+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-02b_fields-wd3-s011`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-02b-s011:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 202 |
| sites_written | 99 |
| refused | 40 |
| cells:geom | 11 |
| cells:lat | 11 |
| cells:lon | 11 |
| cells:period_name | 73 |
| cells:period_start | 73 |
| cells:site_type | 21 |
| cells:source_url | 2 |
| refused:coordinates-unresolved | 17 |
| refused:country-changes | 1 |
| refused:field-unresolved | 22 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Acanceh | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Acanceh | period_start | `NULL` | `-350` | wd3-replace |
| Ackling Dyke | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Ackling Dyke | period_start | `NULL` | `55` | wd3-replace |
| Adam's Grave | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Adam's Grave | period_start | `NULL` | `-4000` | wd3-replace |
| Aetokremnos | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Aetokremnos | period_start | `NULL` | `-9825` | wd3-replace |
| Aetokremnos | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Akeman Street | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Akeman Street | period_start | `NULL` | `43` | wd3-replace |
| Alte Burg, Langenenslingen | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Alte Burg, Langenenslingen | period_start | `NULL` | `-700` | wd3-replace |
| Ancient Theatre of Makyneia | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Ancient Theatre of Makyneia | period_start | `NULL` | `-400` | wd3-replace |
| Anta de Agualva | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Anta de Agualva | period_start | `NULL` | `-4000` | wd3-replace |
| Arqueológico El Puente Park | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Arqueológico El Puente Park | period_start | `NULL` | `550` | wd3-replace |
| Arzachena Archaeological Park | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Aymestrey Burial | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Aymestrey Burial | period_start | `NULL` | `-2200` | wd3-replace |
| Azargoshnasp Fire Temple | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Azargoshnasp Fire Temple | period_start | `NULL` | `450` | wd3-replace |
| Ballymacdermott Court Tomb | geom | `0101000020E6100000B2D7C90B359E1AC02DFEA290DA2C4B40` | `SRID=4326;POINT(-6.370528 54.153889)` | wd3-point |
| Ballymacdermott Court Tomb | lat | `54.35042007406842` | `54.153889` | wd3-replace |
| Ballymacdermott Court Tomb | lon | `-6.6544992296166345` | `-6.370528` | wd3-replace |
| Beaumont Cut | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Beaumont Cut | period_start | `NULL` | `1832` | wd3-replace |
| Belören Kalesi | site_type | `NULL` | `Castle` | wd3-replace |
| Buckton Roman Fort | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Buckton Roman Fort | period_start | `NULL` | `80` | wd3-replace |
| Buri Burial Mound Field | geom | `0101000020E6100000B80D454800404940B46B5F7769263A40` | `SRID=4326;POINT(50.5031 26.1403)` | wd3-point |
| Buri Burial Mound Field | lat | `26.150046788021157` | `26.1403` | wd3-replace |
| Buri Burial Mound Field | lon | `50.50000861522443` | `50.5031` | wd3-replace |
| Calatia | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Calatia | period_start | `NULL` | `-800` | wd3-replace |
| Cannae | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Cannae | period_start | `NULL` | `-600` | wd3-replace |
| Carreg Coetan Arthur | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Carreg Coetan Arthur | period_start | `NULL` | `-3000` | wd3-replace |
| Chichakuri | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Dimini | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Dimini | period_start | `NULL` | `-4800` | wd3-replace |
| Dumat al-Jandal | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Dumat al-Jandal | period_start | `NULL` | `-1000` | wd3-replace |
| Foel Drygarn Hillfort | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Foel Drygarn Hillfort | period_start | `NULL` | `-1000` | wd3-replace |
| Fortifications of London | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Fortifications of London | period_start | `NULL` | `200` | wd3-replace |
| Galaxidi | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Galaxidi | period_start | `NULL` | `-300` | wd3-replace |
| Gallardet Dolmen | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Gallardet Dolmen | period_start | `NULL` | `-3500` | wd3-replace |
| Goloring | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Goloring | period_start | `NULL` | `-1200` | wd3-replace |
| Għar Dalam | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Għar Dalam | period_start | `NULL` | `-5200` | wd3-replace |
| Hammerum Burial Site | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Hammerum Burial Site | period_start | `NULL` | `200` | wd3-replace |
| Herxheim - Archaeological Site | geom | `0101000020E6100000B929F1DEAA7020409ABBDBD7CE924840` | `SRID=4326;POINT(8.1906469 49.1453309)` | wd3-point |
| Herxheim - Archaeological Site | lat | `49.14693735341207` | `49.1453309` | wd3-replace |
| Herxheim - Archaeological Site | lon | `8.220053641260948` | `8.1906469` | wd3-replace |
| Inka Wasi, Huancavelica | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Inka Wasi, Huancavelica | period_start | `NULL` | `1440` | wd3-replace |
| Kbor Klib | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Kbor Klib | period_start | `NULL` | `-200` | wd3-replace |
| Kemune (Zahiku) | geom | `0101000020E61000005D006B3469604540A15F0001C5624240` | `SRID=4326;POINT(42.73194 36.76861)` | wd3-point |
| Kemune (Zahiku) | lat | `36.77163708227386` | `36.76861` | wd3-replace |
| Kemune (Zahiku) | lon | `42.7532105944126` | `42.73194` | wd3-replace |
| Keno Daas Rock Carvings | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Keno Daas Rock Carvings | period_start | `NULL` | `601` | wd3-replace |
| Keno Daas Rock Carvings | site_type | `NULL` | `Rock relief/carving` | wd3-replace |
| Kertasi Temple | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Kertasi Temple | period_start | `NULL` | `1` | wd3-replace |
| Khao Sai On Archaeological Site | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Khao Sai On Archaeological Site | period_start | `NULL` | `-1000` | wd3-replace |
| Khao Sai On Archaeological Site | site_type | `NULL` | `Mine` | wd3-replace |
| Khichuqaqa | site_type | `NULL` | `Rock art` | wd3-replace |
| Kierikki | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Kierikki | period_start | `NULL` | `-5000` | wd3-replace |
| Komplek Megalith Tanjung Raja | source_url | `NULL` | `https://sisparnas.kemenpar.go.id/p/43025` | wd3-replace |
| Kʼatepan | site_type | `NULL` | `Temple complex` | wd3-replace |
| La Florida (Zacatecas) Shaft Tomb | site_type | `NULL` | `Tomb` | wd3-replace |
| Larisa, Argos | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Larisa, Argos | period_start | `NULL` | `-1300` | wd3-replace |
| Leptis Magna Museum | period_name | `NULL` | `1500+ AD` | wd3-derive-period-name |
| Leptis Magna Museum | period_start | `NULL` | `1986` | wd3-replace |
| Llaqta Qulluy, Tayacaja | site_type | `NULL` | `Archaeological site` | wd3-replace |
| London to Lewes Way | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| London to Lewes Way | period_start | `NULL` | `1` | wd3-replace |
| Lupanar of Pompeii | site_type | `NULL` | `Ruin` | wd3-replace |
| Macedonian Tomb of Elafochori | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Macedonian Tomb of Elafochori | period_start | `NULL` | `-400` | wd3-replace |
| Madera Caves | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Madera Caves | period_start | `NULL` | `1205` | wd3-replace |
| Makry Gialos | geom | `0101000020E6100000E6FEF60F76F7394032EA30008E884140` | `SRID=4326;POINT(25.9672 35.0377)` | wd3-point |
| Makry Gialos | lat | `35.06683351887149` | `35.0377` | wd3-replace |
| Makry Gialos | lon | `25.966645238687214` | `25.9672` | wd3-replace |
| Makry Gialos | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Makry Gialos | period_start | `NULL` | `-1500` | wd3-replace |
| Margarita Tomb | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Margarita Tomb | period_start | `NULL` | `440` | wd3-replace |
| Merano | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Merano | period_start | `NULL` | `-15` | wd3-replace |
| Midhowe Chambered Cairn | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Midhowe Chambered Cairn | period_start | `NULL` | `-3500` | wd3-replace |
| Misraħ Għar il-Kbir | site_type | `NULL` | `Road/avenue/trackway` | wd3-replace |
| Mnemata Site | site_type | `NULL` | `Cemetery` | wd3-replace |
| Mytilene | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Mytilene | period_start | `NULL` | `-1100` | wd3-replace |
| Nakhchivan Necropolises | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Nakhchivan Necropolises | period_start | `NULL` | `-1500` | wd3-replace |
| Nakhchivan Necropolises | site_type | `NULL` | `Necropolis` | wd3-replace |
| Nixtun-Ch’ich | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Nixtun-Ch’ich | period_start | `NULL` | `-1000` | wd3-replace |
| Niš | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Niš | period_start | `NULL` | `-300` | wd3-replace |
| Noh Kah | geom | `0101000020E6100000D9334C0E7B1456C0F49C004F7D7D3240` | `SRID=4326;POINT(-88.807831 18.110281)` | wd3-point |
| Noh Kah | lat | `18.490193307542498` | `18.110281` | wd3-replace |
| Noh Kah | lon | `-88.320010733048` | `-88.807831` | wd3-replace |
| Nordy Bank | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Nordy Bank | period_start | `NULL` | `-1000` | wd3-replace |
| Nyaung-gan | site_type | `NULL` | `Cemetery` | wd3-replace |
| Nîmes | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Nîmes | period_start | `NULL` | `-4000` | wd3-replace |
| Papeloze Kerk | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Papeloze Kerk | period_start | `NULL` | `-3300` | wd3-replace |
| Parque Arqueológico Zaculeu | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Parque Arqueológico Zaculeu | period_start | `NULL` | `250` | wd3-replace |
| Prassa | geom | `0101000020E6100000403F881D15303940D77973E862A84140` | `SRID=4326;POINT(25.191806 35.306889)` | wd3-point |
| Prassa | lat | `35.3155184329841` | `35.306889` | wd3-replace |
| Prassa | lon | `25.187822194827504` | `25.191806` | wd3-replace |
| Pukarani, Peru | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Pukarani, Peru | period_start | `NULL` | `1100` | wd3-replace |
| Pyramid of Djedkare-Isesi | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Pyramid of Djedkare-Isesi | period_start | `NULL` | `-2411` | wd3-replace |
| Quri Winchus | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Rock Carvings at Åsli | geom | `0101000020E61000006D082099093C3340A1C2F0CF684F5140` | `SRID=4326;POINT(19.017131 69.281089)` | wd3-point |
| Rock Carvings at Åsli | lat | `69.24077223312135` | `69.281089` | wd3-replace |
| Rock Carvings at Åsli | lon | `19.234521456070457` | `19.017131` | wd3-replace |
| Rodadero Slides | site_type | `NULL` | `Natural feature` | wd3-replace |
| San Estevan | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| San Estevan | period_start | `NULL` | `-800` | wd3-replace |
| Sanghao Cave | geom | `0101000020E61000009C14058FEAE25140D04ACAA93A074140` | `SRID=4326;POINT(72.183333 34.483333)` | wd3-point |
| Sanghao Cave | lat | `34.05647776010085` | `34.483333` | wd3-replace |
| Sanghao Cave | lon | `71.5455663251509` | `72.183333` | wd3-replace |
| Sanghao Cave | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Sanghao Cave | period_start | `NULL` | `-18000` | wd3-replace |
| Sayacmarca | site_type | `NULL` | `Archaeological site` | wd3-replace |
| Shillourokambos | geom | `0101000020E6100000652D1FF25294404057D6F065325F4140` | `SRID=4326;POINT(33.1563 34.76701)` | wd3-point |
| Shillourokambos | lat | `34.743725531193085` | `34.76701` | wd3-replace |
| Shillourokambos | lon | `33.15878130457239` | `33.1563` | wd3-replace |
| Sirkeli Höyüğü | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Sirkeli Höyüğü | period_start | `NULL` | `-5000` | wd3-replace |
| Sollentuna Socken | source_url | `NULL` | `https://en.wikipedia.org/wiki/Sollentuna_socken` | wd3-replace |
| St Catherine's Hill, Hampshire | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| St Catherine's Hill, Hampshire | period_start | `NULL` | `-600` | wd3-replace |
| Stenehed | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Stenehed | period_start | `NULL` | `400` | wd3-replace |
| Taputapuatea Marae | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Taputapuatea Marae | period_start | `NULL` | `1000` | wd3-replace |
| Teurnia | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Teurnia | period_start | `NULL` | `-1100` | wd3-replace |
| Thigibba Hammam Zouakra | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Thigibba Hammam Zouakra | period_start | `NULL` | `-300` | wd3-replace |
| Tienen Mithraeum | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Tienen Mithraeum | period_start | `NULL` | `201` | wd3-replace |
| Tivulaghju | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Tivulaghju | period_start | `NULL` | `-4500` | wd3-replace |
| Tomb of Aegisthus | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Tomb of Aegisthus | period_start | `NULL` | `-1510` | wd3-replace |
| Tomb of King Tongmyong | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Tomb of King Tongmyong | period_start | `NULL` | `427` | wd3-replace |
| Tomb of the Scene | site_type | `NULL` | `Tomb` | wd3-replace |
| Tregeseal East Stone Circle | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Tregeseal East Stone Circle | period_start | `NULL` | `-2500` | wd3-replace |
| Uxmal | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Uxmal | period_start | `NULL` | `501` | wd3-replace |
| Valley of the Caves, Chihuahua | geom | `0101000020E61000005DC6E8E19A0A5BC02E66756BCF8C3D40` | `SRID=4326;POINT(-108.321403 30.162578)` | wd3-point |
| Valley of the Caves, Chihuahua | lat | `29.550039974367046` | `30.162578` | wd3-replace |
| Valley of the Caves, Chihuahua | lon | `-108.16570327503128` | `-108.321403` | wd3-replace |
| Valley of the Caves, Chihuahua | period_name | `NULL` | `< 4500 BC` | wd3-derive-period-name |
| Valley of the Caves, Chihuahua | period_start | `NULL` | `-5500` | wd3-replace |
| Via Militaris | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Via Militaris | period_start | `NULL` | `1` | wd3-replace |
| Vilcashuamán | period_name | `NULL` | `1000 - 1500 AD` | wd3-derive-period-name |
| Vilcashuamán | period_start | `NULL` | `1400` | wd3-replace |
| Villa of Lucullus | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Villa of Lucullus | period_start | `NULL` | `-100` | wd3-replace |
| White Horse Stone | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| White Horse Stone | period_start | `NULL` | `-4000` | wd3-replace |
| Wila Wilani, Tacna | site_type | `NULL` | `Rock art` | wd3-replace |
| Wilsford Henge | period_name | `NULL` | `3000 - 1500 BC` | wd3-derive-period-name |
| Wilsford Henge | period_start | `NULL` | `-2600` | wd3-replace |
| Yarnbury Castle | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Yarnbury Castle | period_start | `NULL` | `-300` | wd3-replace |
| Zacpeten | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Zacpeten | period_start | `NULL` | `-1000` | wd3-replace |
| Zacpeten | site_type | `NULL` | `Settlement` | wd3-replace |
| Zona Arqueológica de Cholula | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Zona Arqueológica de Cholula | period_start | `NULL` | `-800` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Quri Winchus | period_start | `field-unresolved` | The English Wikipedia article says Quri Winchus holds remains of circular buildings of the Wanka period, but a period wo |
| Chichakuri | period_start | `field-unresolved` | English and Spanish Wikipedia and the MINCETUR inventory record (cod_Ficha=4758) place Chichakuri (Chichacori, Ollachea, |
| Margarita Tomb | lat | `coordinates-unresolved` | No page found prints a point for the Margarita Tomb itself; Wikipedia, Wikidata, Commons, Penn Museum, Florida Museum an |
| La Florida (Zacatecas) Shaft Tomb | lat | `coordinates-unresolved` | No readable page prints coordinates for this tomb; the Megalithic Portal page returns 403 to a plain GET. The INAH salva |
| La Florida (Zacatecas) Shaft Tomb | period_start | `field-unresolved` | The only article on this tomb gives 'two centuries before our era and 400 after Christ's' for the societies of the area  |
| Keno Daas Rock Carvings | lat | `coordinates-unresolved` | No readable page prints a coordinate pair for the Keno Daas carvings: the Wikipedia article carries a coord-missing noti |
| Prassa | period_start | `field-unresolved` | Prassa's sources (Wikipedia, minoancrete.com) date the houses only by Minoan phases (MM I to LM IA) without a year, cent |
| Rock Carvings at Åsli | period_start | `field-unresolved` | Askeladden gives only Stone Age (shoreline-dated, probable); Arild Hauge's text and Wikipedia say only hunting culture;  |
| Hammerum Burial Site | lat | `coordinates-unresolved` | The English Wikipedia article prints no coordinates, its Wikidata item (Q30588188) has no coordinate statement, and no r |
| Sollentuna Socken | period_start | `field-unresolved` | The sources date the parish's remains only by period words - Bronze Age chambered cairns, about 60 Iron Age burial sites |
| Sollentuna Socken | site_type | `field-unresolved` | The sources describe many kinds of remains at once (chambered cairns, around 60 burial sites, a tumulus, five hill forts |
| Belören Kalesi | lat | `coordinates-unresolved` | The Cultural Inventory record for Belören Kalesi, the only page I could read for this site, gives its name, type, status |
| Belören Kalesi | period_start | `field-unresolved` | The only dating I found for Belören Kalesi is Miras Haritası supposing a construction between the 5th and 1st centuries  |
| Kʼatepan | period_start | `field-unresolved` | Wikipedia only says the main temple is of a style typical of the Postclassic (c. 950-1539 AD) in the Guatemalan Highland |
| Komplek Megalith Tanjung Raja | lat | `coordinates-unresolved` | No readable page prints a point for the Tanjung Raja megalith complex in Gumay Ulu, Lahat; the national tourism register |
| Komplek Megalith Tanjung Raja | period_start | `field-unresolved` | No source found dates the Tanjung Raja megalith complex itself; pages on the Pasemah megaliths speak of the region in ge |
| Komplek Megalith Tanjung Raja | site_type | `field-unresolved` | The only page naming the site, the Sisparnas register entry 'Situs Megalit Tanjung Raja', gives just that Indonesian nam |
| Nakhchivan Necropolises | lat | `coordinates-unresolved` | No source prints a point for the Nakhchivan necropolises: the English and Azerbaijani Wikipedia articles give none, the  |
| Llaqta Qulluy, Tayacaja | lat | `coordinates-unresolved` | Wikipedia marks the coordinates as missing and Wikidata has no P625; no readable source found gives a point for Llaqta Q |
| Llaqta Qulluy, Tayacaja | period_start | `field-unresolved` | No readable source dates Llaqta Qulluy in Tayacaja; Wikipedia only gives the name's meaning. |
| Arzachena Archaeological Park | lat | `coordinates-unresolved` | The park is a group of eight sites (Li Muri, Li Lolghi, Albucciu, Moru, Malchittu, La Prisgiona, Coddu Vecchju and other |
| Arzachena Archaeological Park | period_start | `field-unresolved` | Italia.it dates the park's eight sites only as a span from the 5th to the 2nd millennium BC, which does not state a star |
| Rodadero Slides | period_start | `field-unresolved` | The Rodadero is a natural diorite outcrop; no readable source gives a date for the start of its use as a site (the Spani |
| Pukarani, Peru | lat | `coordinates-unresolved` | Only Wikipedia/Wikidata print a point (15 14 28 S 70 16 40 W), and they print it for the mountain; SRTM gives about 4,19 |
| Lupanar of Pompeii | period_start | `field-unresolved` | No readable source dates the construction of the Lupanar at VII.12.18-20; English, German, French, Italian Wikipedia, Po |
| Khichuqaqa | lat | `coordinates-unresolved` | English Wikipedia and Wikidata print no coordinates for Khichuqaqa (only Urubamba District, Cusco Region, on the slope o |
| Khichuqaqa | period_start | `field-unresolved` | No readable source gives a year, century or millennium for Khichuqaqa; Wikipedia only says it is an archaeological site  |
| Misraħ Għar il-Kbir | period_start | `field-unresolved` | Wikipedia says the age and purpose of the tracks are uncertain, with origins estimated from the Neolithic to Medieval ti |
| Via Militaris | lat | `coordinates-unresolved` | The Via Militaris is a road of 924 km from Singidunum to Constantinople; neither its English article nor the Wikidata it |
| Kastros | lat | `country-changes` | the new point lies in [], the site says Cyprus |
| Thigibba Hammam Zouakra | lat | `coordinates-unresolved` | No source I could read quotes a point for Thigibba at Hammam Zouakra: the French Wikipedia article leaves its latitude a |
| Khao Sai On Archaeological Site | lat | `coordinates-unresolved` | ISMEO/LoRAP's page gives the point of the Khao Sai On dioritic inselberg and, separately, points for the single excavati |
| Wila Wilani, Tacna | period_start | `field-unresolved` | No source states a year, century or millennium for the start of Wila Wilani (Tacna). The English article gives no date a |
| Mnemata Site | lat | `coordinates-unresolved` | No readable page prints a point for the Mnemata Site / Agios Georgios cemetery of Kition: Wikipedia and Wikidata carry n |
| Mnemata Site | period_start | `field-unresolved` | Wikipedia only says the site was a cemetery 'from the beginning of the Iron Age until the Roman times', a period word wi |
| Fortifications of London | lat | `coordinates-unresolved` | The Fortifications of London are a system of walls, gates and forts across the city; the Wikipedia article and its Wikid |
| Tomb of the Scene | period_start | `field-unresolved` | The sources about the Sahneh rock tombs give only period words (Median or Achaemenid; Persian Wikipedia's infobox gives  |
| Tomb of the Scene | source_url | `field-unresolved` | The only pages found about the rock tomb of Sahneh (Persian Wikipedia, visitiran.ir) never name it 'Tomb of the Scene',  |
| Nyaung-gan | lat | `coordinates-unresolved` | No readable source prints a coordinate pair for Nyaung-gan; Wikipedia carries no coordinates and Oakaie paper only says  |
| Nyaung-gan | period_start | `field-unresolved` | Wikipedia gives no date for Nyaung-gan itself (only Bronze Age); the literature gives only a range of estimates from the |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-02b_fields-wd3-s011-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-02b-s011 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
