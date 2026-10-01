# WD1 fields-wd1-2026-09-26b-s011: plan

Built 2026-09-30T06:06:01+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-09-26b_fields-wd1-s011`, test id `WD1/structured-fields`, change keys `fields-wd1-2026-09-26b-s011:<site>:<column>`.

| counter | value |
|---|---|
| sites | 56 |
| cells | 165 |
| sites_written | 56 |
| refused | 10 |
| cells:geom | 16 |
| cells:lat | 16 |
| cells:lon | 16 |
| cells:period_name | 37 |
| cells:period_start | 37 |
| cells:site_type | 30 |
| cells:source_url | 13 |
| refused:coordinates-unresolved | 9 |
| refused:held-unreadable | 1 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| A Figa | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| A Figa | period_start | `-3300` | `NULL` | wd1-clear |
| A Figa | site_type | `Archaeological site` | `NULL` | wd1-clear |
| A Figa | source_url | `https://en.wikipedia.org/wiki/A_Figa` | `NULL` | wd1-clear |
| Abusir | geom | `0101000020E6100000950DA75630383F404198AFE9F9E43D40` | `SRID=4326;POINT(31.203611 29.896111)` | wd1-point |
| Abusir | lat | `29.894438367242632` | `29.896111` | wd1-replace |
| Abusir | lon | `31.21948758676952` | `31.203611` | wd1-replace |
| Aihole | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Aihole | period_start | `1` | `501` | wd1-replace |
| Ain Hirsha Roman Temple | source_url | `https://en.wikipedia.org/wiki/Ain_Harcha` | `https://riunet.upv.es/entities/publication/5cd1c125-94e8-4e3` | wd1-replace |
| Antequera Dolmens Site | period_name | `3000 - 1500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Antequera Dolmens Site | period_start | `-3000` | `-3800` | wd1-replace |
| Appleby Logboat | site_type | `Museum` | `NULL` | wd1-clear |
| Ardgroom | geom | `0101000020E61000005B1BF62BA7C923C02A3E1FCBB4DE4940` | `SRID=4326;POINT(-9.87003 51.73598)` | wd1-point |
| Ardgroom | lat | `51.739892378096854` | `51.73598` | wd1-replace |
| Ardgroom | lon | `-9.89385354403719` | `-9.87003` | wd1-replace |
| Ardgroom | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Ardgroom | period_start | `-4500` | `NULL` | wd1-clear |
| Ardgroom | site_type | `Megalithic stones` | `Stone circle` | wd1-replace |
| Ardgroom | source_url | `https://en.wikipedia.org/wiki/Ardgroom` | `https://www.megalithic.co.uk/article.php?sid=628` | wd1-replace |
| Baltalı Kapı | period_name | `500 BC - 1 AD` | `1 - 500 AD` | wd1-derive-period-name |
| Baltalı Kapı | period_start | `-500` | `101` | wd1-replace |
| Baltalı Kapı | source_url | `https://www-milas-gov-tr.translate.goog/baltali-kapii?_x_tr_` | `https://tr.wikipedia.org/wiki/Baltal%C4%B1_Kap%C4%B1` | wd1-replace |
| Bassae | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Björkö, Ekerö | geom | `0101000020E6100000E14A09F75D8F31405D5ABC6297A94D40` | `SRID=4326;POINT(17.54528 59.33611)` | wd1-point |
| Björkö, Ekerö | lat | `59.32493242451594` | `59.33611` | wd1-replace |
| Björkö, Ekerö | lon | `17.56002754189365` | `17.54528` | wd1-replace |
| Björkö, Ekerö | period_name | `3000 - 1500 BC` | `500 - 1000 AD` | wd1-derive-period-name |
| Björkö, Ekerö | period_start | `-3000` | `750` | wd1-replace |
| Björkö, Ekerö | site_type | `Mound/tumulus` | `Town` | wd1-replace |
| Björkö, Ekerö | source_url | `https://en.wikipedia.org/wiki/Bj%C3%B6rk%C3%B6_(Eker%C3%B6)` | `https://en.wikipedia.org/wiki/Birka` | wd1-replace |
| Cardiccia | geom | `0101000020E610000039182E3AD1F2214033B5DF4A98CF4440` | `SRID=4326;POINT(8.9407 41.5577)` | wd1-point |
| Cardiccia | lat | `41.62183509753449` | `41.5577` | wd1-replace |
| Cardiccia | lon | `8.97425252735785` | `8.9407` | wd1-replace |
| Cardiccia | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Cardiccia | period_start | `-3000` | `NULL` | wd1-clear |
| Cardiccia | site_type | `Megalithic` | `Dolmen` | wd1-replace |
| Castro de Borneiro | site_type | `City/town/settlement` | `Settlement` | wd1-replace |
| Caunos Tombs of The Kings | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Caunos Tombs of The Kings | period_start | `-1500` | `-400` | wd1-replace |
| Caunos Tombs of The Kings | source_url | `https://en.wikipedia.org/wiki/Kaunos` | `https://kulturenvanteri.com/yer/kaunos-kaya-mezarlari/` | wd1-replace |
| Clare, Suffolk | period_name | `4500 - 3000 BC` | `1000 - 1500 AD` | wd1-derive-period-name |
| Clare, Suffolk | period_start | `-4500` | `1045` | wd1-replace |
| Clare, Suffolk | source_url | `https://en.wikipedia.org/wiki/History` | `https://en.wikipedia.org/wiki/Clare,_Suffolk` | wd1-replace |
| Craigs Dolmen | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Craigs Dolmen | period_start | `-4000` | `NULL` | wd1-clear |
| Craigs Dolmen | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Dighton Rock | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Dighton Rock | period_start | `1000` | `NULL` | wd1-clear |
| Dreros | site_type | `Archaeological site` | `City` | wd1-replace |
| Hammarah Temple | site_type | `Temple complex` | `Temple` | wd1-replace |
| Hammarah Temple | source_url | `https://www.wanderleb.com/blog/hammara-temple` | `NULL` | wd1-clear |
| Heuneburg | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Heuneburg | period_start | `-1500` | `-1600` | wd1-replace |
| Hexton | geom | `0101000020E6100000C45D0FA18B29D9BFB021AE47FFFA4940` | `SRID=4326;POINT(-0.402214 51.953141)` | wd1-point |
| Hexton | lat | `51.960915527367774` | `51.953141` | wd1-replace |
| Hexton | lon | `-0.3931607315875818` | `-0.402214` | wd1-replace |
| Hexton | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Hexton | source_url | `https://en.wikipedia.org/wiki/Hexton` | `https://northhertsmuseum.org/archaeology-tuesdays-ravensburg` | wd1-replace |
| Huéscar | geom | `0101000020E610000067D14340174404C0B18EDF906AE64240` | `SRID=4326;POINT(-2.539444 37.809444)` | wd1-point |
| Huéscar | lat | `37.80012713352097` | `37.809444` | wd1-replace |
| Huéscar | lon | `-2.533247472829476` | `-2.539444` | wd1-replace |
| Huéscar | period_name | `1500 - 500 BC` | `1000 - 1500 AD` | wd1-derive-period-name |
| Huéscar | period_start | `-1000` | `1201` | wd1-replace |
| Inkapintay | geom | `0101000020E6100000D380EEECD91052C071A65B3907842AC0` | `SRID=4326;POINT(-72.250139 -13.258472)` | wd1-point |
| Inkapintay | lat | `-13.257867615163578` | `-13.258472` | wd1-replace |
| Inkapintay | lon | `-72.26330111781435` | `-72.250139` | wd1-replace |
| Inkapintay | period_name | `1000 - 1500 AD` | `NULL` | wd1-derive-period-name |
| Inkapintay | period_start | `1000` | `NULL` | wd1-clear |
| Kharakhorum Museum | geom | `0101000020E61000006840C29BB4B65940A879667980994740` | `SRID=4326;POINT(102.83928 47.195307)` | wd1-point |
| Kharakhorum Museum | lat | `47.19923322204278` | `47.195307` | wd1-replace |
| Kharakhorum Museum | lon | `102.85477346391565` | `102.83928` | wd1-replace |
| Krasnyi Yar, Kazakhstan | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd1-derive-period-name |
| Krasnyi Yar, Kazakhstan | period_start | `-5000` | `-3700` | wd1-replace |
| Krasnyi Yar, Kazakhstan | site_type | `City/town/settlement` | `Village` | wd1-replace |
| Leskernick Hill | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| Leskernick Hill | period_start | `-4500` | `NULL` | wd1-clear |
| Leskernick Hill | site_type | `Stone circle` | `Settlement` | wd1-replace |
| Leskernick Hill | source_url | `https://en.wikipedia.org/wiki/Leskernick_Hill` | `https://www.megalithic.co.uk/article.php?sid=22135` | wd1-replace |
| Llansteffan Castle | period_name | `3000 - 1500 BC` | `1000 - 1500 AD` | wd1-derive-period-name |
| Llansteffan Castle | period_start | `-3000` | `1101` | wd1-replace |
| Louisenlund, Bornholm | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Louisenlund, Bornholm | period_start | `-1500` | `NULL` | wd1-clear |
| Louisenlund, Bornholm | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Maleme | geom | `0101000020E610000066CE7FDEF7D83740A48E582FDEC24140` | `SRID=4326;POINT(23.8327 35.5236)` | wd1-point |
| Maleme | lat | `35.522405546418014` | `35.5236` | wd1-replace |
| Maleme | lon | `23.847532182886788` | `23.8327` | wd1-replace |
| Maleme | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Maleme | period_start | `-3000` | `-1300` | wd1-replace |
| Maleme | site_type | `Necropolis/tombs complex` | `Tomb` | wd1-replace |
| Maleme | source_url | `https://en.wikipedia.org/wiki/Maleme` | `http://odysseus.culture.gr/h/2/gh251.jsp?obj_id=15961` | wd1-replace |
| Marayniyoq | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd1-derive-period-name |
| Marayniyoq | period_start | `1` | `700` | wd1-replace |
| Marayniyoq | site_type | `City/town/settlement` | `Archaeological site` | wd1-replace |
| Mes Aynak | geom | `0101000020E61000003B367801805751403BC10F8439334140` | `SRID=4326;POINT(69.3001 34.2715)` | wd1-point |
| Mes Aynak | lat | `34.40019274491575` | `34.2715` | wd1-replace |
| Mes Aynak | lon | `69.36718785037458` | `69.3001` | wd1-replace |
| Mes Aynak | period_name | `3000 - 1500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Mes Aynak | period_start | `-3000` | `-100` | wd1-replace |
| Mes Aynak | site_type | `Temple complex` | `Monastery` | wd1-replace |
| Minoan Palace of Knossos | site_type | `Megalithic stones` | `Palace` | wd1-replace |
| Orchomenus, Boeotia | geom | `0101000020E6100000169A1D23BDFB36402053048BE23D4340` | `SRID=4326;POINT(22.9641 38.4956)` | wd1-point |
| Orchomenus, Boeotia | lat | `38.483476044761346` | `38.4956` | wd1-replace |
| Orchomenus, Boeotia | lon | `22.98335475418761` | `22.9641` | wd1-replace |
| Orchomenus, Boeotia | period_name | `3000 - 1500 BC` | `NULL` | wd1-derive-period-name |
| Orchomenus, Boeotia | period_start | `-3000` | `NULL` | wd1-clear |
| Overton Hill | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Overton Hill | period_start | `-1500` | `-2500` | wd1-replace |
| Overton Hill | site_type | `Road/avenue/trackway` | `Barrow` | wd1-replace |
| Overton Hill | source_url | `https://en.wikipedia.org/wiki/Overton_Hill` | `http://www.stone-circles.org.uk/stone/overtonbarrows.htm` | wd1-replace |
| Pešturina | geom | `0101000020E61000004E7058526BE63540C7F84CB159954540` | `SRID=4326;POINT(22.046221 43.293931)` | wd1-point |
| Pešturina | lat | `43.16679970034016` | `43.293931` | wd1-replace |
| Pešturina | lon | `21.900075098601796` | `22.046221` | wd1-replace |
| Pešturina | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Pešturina | period_start | `-111000` | `NULL` | wd1-clear |
| Pikillaqta | site_type | `Temple complex` | `City/town/settlement` | wd1-replace |
| Saguaro National Park | period_name | `1 - 500 AD` | `1500+ AD` | wd1-derive-period-name |
| Saguaro National Park | period_start | `1` | `1933` | wd1-replace |
| Saguaro National Park | site_type | `Petroglyphs` | `Natural feature` | wd1-replace |
| Salamis Ancient City | period_name | `3000 - 1500 BC` | `1500 - 500 BC` | wd1-derive-period-name |
| Salamis Ancient City | period_start | `-3000` | `-1100` | wd1-replace |
| San Estevan | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| San Estevan | period_start | `-1500` | `NULL` | wd1-clear |
| Shaduppum | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd1-derive-period-name |
| Shaduppum | period_start | `-4500` | `-3000` | wd1-replace |
| Shahbaz Garhi | geom | `0101000020E610000047E49F433D0A52402C9EA5172D1E4140` | `SRID=4326;POINT(72.16525 34.224194)` | wd1-point |
| Shahbaz Garhi | lat | `34.23575110995111` | `34.224194` | wd1-replace |
| Shahbaz Garhi | lon | `72.15998926748681` | `72.16525` | wd1-replace |
| Shahbaz Garhi | site_type | `Rock relief/carving` | `Inscription` | wd1-replace |
| Shrine of Hercules Curinus | site_type | `Temple complex` | `Sanctuary` | wd1-replace |
| Sinuessa | geom | `0101000020E6100000C63E7FD3A7B42B40FFC37C1221924440` | `SRID=4326;POINT(13.847624 41.153942)` | wd1-point |
| Sinuessa | lat | `41.14163428394385` | `41.153942` | wd1-replace |
| Sinuessa | lon | `13.852842911990034` | `13.847624` | wd1-replace |
| Smyrna Agora Ancient City | site_type | `Archaeological site` | `Forum` | wd1-replace |
| Soli, Cyprus | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Soli, Cyprus | period_start | `-500` | `-1100` | wd1-replace |
| Surčin | period_name | `1 - 500 AD` | `NULL` | wd1-derive-period-name |
| Surčin | period_start | `1` | `NULL` | wd1-clear |
| Taputapuatea Marae | period_name | `500 - 1000 AD` | `NULL` | wd1-derive-period-name |
| Taputapuatea Marae | period_start | `500` | `NULL` | wd1-clear |
| The Longstone, Mottistone | period_name | `4500 - 3000 BC` | `NULL` | wd1-derive-period-name |
| The Longstone, Mottistone | period_start | `-4500` | `NULL` | wd1-clear |
| The Longstone, Mottistone | site_type | `Megalithic stones` | `Standing stone` | wd1-replace |
| Thirty-nine (39) Bridge Street, Chester | site_type | `Residence/villa/farmhouse` | `Bath` | wd1-replace |
| Tievebulliagh | source_url | `https://en.wikipedia.org/wiki/Tievebulliagh` | `https://www.megalithic.co.uk/article.php?sid=6333459` | wd1-replace |
| Tikra | period_name | `500 BC - 1 AD` | `NULL` | wd1-derive-period-name |
| Tikra | period_start | `-250` | `NULL` | wd1-clear |
| Tikra | site_type | `Necropolis/tombs complex` | `Burial` | wd1-replace |
| Treasury of Cyrene | site_type | `Megalithic structures` | `Monument` | wd1-replace |
| Twin Gates of Pula | site_type | `Megalithic stones` | `Gate` | wd1-replace |
| Yaxuna | period_name | `500 - 1000 AD` | `1500 - 500 BC` | wd1-derive-period-name |
| Yaxuna | period_start | `500` | `-800` | wd1-replace |
| Yeavering Bell | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd1-derive-period-name |
| Yeavering Bell | period_start | `-1500` | `-300` | wd1-replace |
| Yeavering Bell | site_type | `Fortress/citadel` | `Fort` | wd1-replace |
| Yellowberries Copse | geom | `0101000020E6100000A36D2A17C49F0EC0EFE163E79F344940` | `SRID=4326;POINT(-3.842037 50.412796)` | wd1-point |
| Yellowberries Copse | lat | `50.4111298787792` | `50.412796` | wd1-replace |
| Yellowberries Copse | lon | `-3.82801073168021` | `-3.842037` | wd1-replace |
| Yellowberries Copse | period_name | `1500 - 500 BC` | `NULL` | wd1-derive-period-name |
| Yellowberries Copse | period_start | `-1000` | `NULL` | wd1-clear |
| Zafarraya | geom | `0101000020E61000000AF38886888810C0118A22CAC07B4240` | `SRID=4326;POINT(-4.127058 36.950732)` | wd1-point |
| Zafarraya | lat | `36.966820971360114` | `36.950732` | wd1-replace |
| Zafarraya | lon | `-4.1333333035552275` | `-4.127058` | wd1-replace |
| Zafarraya | period_name | `< 4500 BC` | `NULL` | wd1-derive-period-name |
| Zafarraya | period_start | `-28000` | `NULL` | wd1-clear |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Hammarah Temple | lat | `coordinates-unresolved` | Aliquot's Ifpo catalogue places Qasr Hammara on the southern slope of a valley about 3 km north-east of the modern villa |
| Hammarah Temple | period_start | `held-unreadable` | no counted answer in 3 rounds: quote fetch failed: https://today.lorientlejour.com/article/1537764/between-paganism-and- |
| Appleby Logboat | lat | `coordinates-unresolved` | The stored point is North Lincolnshire Museum in Scunthorpe, which keeps the logboat, not the place of the find. The boa |
| Tikra | lat | `coordinates-unresolved` | English Wikipedia gives 10.05139 S 76.61944 W (the stored point), but Spanish Wikipedia and Wikidata, which count as the |
| Shaduppum | lat | `coordinates-unresolved` | English Wikipedia gives Tell Harmal at 33°18′34″N 44°28′01″E, next to the stored point, and Wikidata's point is a coarse |
| Ain Hirsha Roman Temple | lat | `coordinates-unresolved` | Wikidata places the temple at 33.4535234, 35.7904376 (0.03 km from the stored point) and Pleiades' place record for the  |
| Krasnyi Yar, Kazakhstan | lat | `coordinates-unresolved` | The sources disagree by kilometres: German Wikipedia/Wikidata give 53.33994, 69.11968 (the stored point), English Wikipe |
| Marayniyoq | lat | `coordinates-unresolved` | The sources place Marayniyoq on Vega Pampa about 4 km north of Wari (-13.0606, -74.1989); the stored point lies 2 km wes |
| A Figa | lat | `coordinates-unresolved` | The only trace of an archaeological site 'A Figa' is a one-sentence, unreferenced Corsican Wikipedia stub (co.wikipedia. |
| Treasury of Cyrene | lat | `coordinates-unresolved` | Only one source family prints a point for the Treasury of Cyrene: Wikidata Q22810178 (38.482535, 22.502622, 0.13 km from |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-09-26b_fields-wd1-s011-rollback`; rehearse it with `apply.py --lane fields-wd1-2026-09-26b-s011 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
