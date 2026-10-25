# WD5 fields-wd5-2026-10-25p-s001: plan

Built 2026-10-25T07:50:24+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s001`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s001:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 8 |
| sites_written | 4 |
| refused | 111 |
| cells:period_name | 4 |
| cells:period_start | 4 |
| refused:coordinates-unresolved | 18 |
| refused:field-unresolved | 58 |
| refused:moved-since-classification | 35 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Dolmen del prado de Lácara | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Dolmen del prado de Lácara | period_start | `-4000` | `-3000` | wd5-replace |
| Kulubá | period_name | `500 - 1000 AD` | `500 BC - 1 AD` | wd5-derive-period-name |
| Kulubá | period_start | `500` | `-300` | wd5-replace |
| Lake Paliastomi | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd5-derive-period-name |
| Lake Paliastomi | period_start | `-1500` | `-400` | wd5-replace |
| Moylehid | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Moylehid | period_start | `-4000` | `-2900` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Menhir du Camp de César | period_start | `field-unresolved` | The French Wikipedia infobox gives only the period word Néolithique for the menhir, which this lane's period check does  |
| Gonnus | period_start | `moved-since-classification` | decided about -1500, holds -4000 |
| Tiverton, Devon | period_start | `field-unresolved` | Wikipedia gives Tiverton as a market town and mentions the Stone Age flint finds, the Iron Age hill fort Cranmore Castle |
| Burnt Fen | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0009): The quote dates archaeological finds somewhere in the Burnt Fen  |
| Dobberworth | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Pumawasi, Anta | period_start | `field-unresolved` | No quotable date. Rainer Hostnig's Rupestreweb article on Pumawasi (Chinchaypucyo, Anta, Cusco; rupestreweb.info/pintura |
| Aedava | period_start | `field-unresolved` | Aedava is known only from Procopius (De Aedificiis, 6th century AD), who says Justinian restored its damaged defences; E |
| Apazzu | period_start | `field-unresolved` | French Wikipedia's infobox (Menhirs d'Apazzu, Sartene) gives the period as 'Age du bronze' and German Wikipedia calls th |
| Llamayuq | lat | `coordinates-unresolved` | English Wikipedia ('coord missing') and Wikidata Q17076914 print no point for Llamayuq (Llamayoq 1-3, Calca, Wakan Wayq' |
| Llamayuq | period_start | `field-unresolved` | Hostnig (rupestreweb, Inca rock art of Cusco) lists Llamayoq 1-3 among paintings tied to late pre-Columbian tombs in the |
| Devil's Humps, Stoughton | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Foel Dduarth - Cairn to North-East of | period_start | `moved-since-classification` | decided about -4000, holds -2300 |
| Cochapata | lat | `coordinates-unresolved` | No readable page prints a point for the Cochapata (Qochapata) complex in Huayopata, La Convencion. English Wikipedia car |
| Roman Vaults of Nuncio Viejo | lat | `coordinates-unresolved` | English Wikipedia and its Wikidata item (Q30593106) carry no coordinates. The vaults are under Calle Nuncio Viejo 19 in  |
| Roman Vaults of Nuncio Viejo | period_start | `field-unresolved` | English Wikipedia says only that the walls and vaults are of Roman age. The one page that gives a date, toledo-virtual.c |
| Yanaque - Quilcamarca | period_start | `field-unresolved` | No source dates the start of the two settlements. The English Wikipedia article gives only location and structures. The  |
| Kyaneai Tarihi Sarnıç | lat | `coordinates-unresolved` | Lycian Monuments, the Kolb survey reports, the Sura church article and web searches treat Kyaneai as a whole city and pr |
| Kyaneai Tarihi Sarnıç | period_start | `field-unresolved` | Sources date the city of Kyaneai but none dates this cistern; the stored 1000 AD comes from a rule and from an import ro |
| Kyaneai Tarihi Sarnıç | source_url | `field-unresolved` | No page found is about this specific cistern; every candidate page concerns the city of Kyaneai or other Lycian sites. |
| Babylonian Theatre | period_start | `moved-since-classification` | decided about 43, holds -323 |
| Sushkivka | lat | `coordinates-unresolved` | The stored point (48.6835, 30.3489) is the centre of the village of Sushkivka (Wikidata Q4447541: 48 41 0 N, 30 20 56 E) |
| Grimstock Hill Romano-British Settlement | period_start | `moved-since-classification` | decided about -800, holds 43 |
| Cave of Mayrières Supérieure | period_start | `field-unresolved` | English Wikipedia calls the cave's bison paintings 15,000-year-old and French Wikipedia and the Merimee notice PA0012561 |
| Temple of Khonsuirdis | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0006): The same abstract says the monument is dated to the early Twenty |
| Dausdava | period_start | `field-unresolved` | The English Wikipedia stub says only that Dausdava was a Dacian town in Moesia between Nicopolis and Abritus and gives n |
| Justinianopolis (Epirus) | period_start | `moved-since-classification` | decided about -500, holds 501 |
| Ərəbyengicə | lat | `coordinates-unresolved` | The only published points (enwiki 39°28′31″N 44°57′00″E, Wikidata 39.4737, 44.9657) are the village's; the article place |
| Ərəbyengicə | period_start | `moved-since-classification` | decided about -500, holds -4000 |
| Ayawayq'u | period_start | `moved-since-classification` | decided about -10000, holds 1438 |
| Nine Maidens Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Megalitikum Rindu Hati | lat | `coordinates-unresolved` | The only page that prints a point for the Rindu Hati statue group is the Megalithic Portal (sid=63737), which answered 4 |
| Megalitikum Rindu Hati | period_start | `field-unresolved` | No readable page dates the Rindu Hati group itself; the Megalithic Portal page was unreadable (403), and Indonesian Wiki |
| Ninamarca | period_start | `field-unresolved` | The sources I found date the Ninamarca chullpas differently and none is academic: French Wikipedia (Lupaca, 13th-14th ce |
| Tilurium | period_start | `field-unresolved` | English and Croatian Wikipedia, Princeton Encyclopedia (Perseus), Visit Trilj and the Croatian heritage texts say the si |
| Oinochori | period_start | `field-unresolved` | English and Greek Wikipedia say only that ruins near the village are thought to be an ancient (Dorian or pre-Dorian) cit |
| Domus De Janas Torre Argentina | period_start | `field-unresolved` | The Wikipedia article gives 3400-2700 BC for the type of tomb in general, not for this site. The only page on this parti |
| Sweetworthy | period_start | `moved-since-classification` | decided about -3000, holds -800 |
| Hampton Down Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2050 |
| Three Brothers, Lancashire | period_start | `field-unresolved` | Wikipedia describes the Three Brothers (SD494734) only as three erratic boulders or standing stone hilltop altars survey |
| Dumat al-Jandal Wall | lat | `coordinates-unresolved` | Only the infobox of the English Wikipedia article prints a point (29.9444, 39.5035), and the article itself places the w |
| Dumat al-Jandal Wall | period_start | `field-unresolved` | The sources disagree: the English article (from the Saudi heritage authority) dates the wall to the 1st century CE, whil |
| Long Meg and Her Daughters | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0003): The two quotes only say 'late Neolithic or early Bronze Age' and |
| Glösa | period_start | `moved-since-classification` | decided about -3000, holds -4000 |
| Eileithyia Cave | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0023): The Bryn Mawr review is about the monograph on the Eileithyia ca |
| Medmenham | period_start | `field-unresolved` | The site is the village of Medmenham. Wikipedia, the Aston Rowant and Chilterns local-history page and the Historic Engl |
| Condolden | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Currachjaghju | lat | `coordinates-unresolved` | The English and Corsican Wikipedia articles on Currachjaghju print no coordinates, Wikidata item Q5194924 holds no coord |
| Kingston Russell Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Stannon Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2900 |
| Tregiffian Burial Chamber | period_start | `moved-since-classification` | decided about -800, holds -2900 |
| Tambo Viejo | period_start | `moved-since-classification` | decided about 1000, holds 130 |
| Sandy, Bedfordshire | period_start | `field-unresolved` | The site is the town of Sandy, whose occupation is documented only in loose bounds: Wikipedia has 'evidence for settleme |
| Cranon | period_start | `field-unresolved` | No source gives the start of Cranon (Crannon). English and German Wikipedia and the Princeton Encyclopedia entry (via To |
| Qaqapatan | period_start | `field-unresolved` | No reputable source dates the Qaqapatan rock paintings. Wikipedia gives only location and height; the Yarusyacan distric |
| Endebjerg | period_start | `field-unresolved` | Only English Wikipedia says Endebjerg (Samsø) was occupied 'since the Early Neolithic period', resting on Funnelbeaker f |
| Stenungsund | lat | `coordinates-unresolved` | The record stands for the RAA grave-and-settlement area Norum 202:1 (Holm 1:1, Norum parish), excavated and removed in 2 |
| Apolyanka | lat | `coordinates-unresolved` | The stored point is the village of Apolianka (uk.wikipedia village point 48.73333, 30.40583). The Trypillia settlement ( |
| Apolyanka | period_start | `field-unresolved` | Readable sources (Frontiers 2019, Springer 2024 on Cucuteni-Trypillia macrobotany) place Apolianka only as a Trypillia p |
| Rodhuish Common | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Beeley Moor | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0007): The site is Beeley Moor, an upland area (Wikidata: hill in the P |
| Balls Head Reserve | period_start | `field-unresolved` | English Wikipedia, the Heritage NSW record (which says only 'For many thousands of years this headland was used by the C |
| Carisbrook Stone Arrangement | period_start | `field-unresolved` | English Wikipedia dates the Carisbrook stone arrangement by no year, century or millennium (only the 1960s rediscovery a |
| İssium | period_start | `field-unresolved` | Only tourism and municipal pages date the Issium/Ision tower, and they disagree (4th century BC, 250-200 BC, 2nd century |
| Warahirka | lat | `coordinates-unresolved` | No readable page prints a point for Warahirka / Huarajirca (La Florida, Pampamarca District, Yarowilca Province, Huanuco |
| Warahirka | period_start | `field-unresolved` | The MINCETUR tourism-inventory record on turismoperuano.com (Sitio Arqueologico Huarajirca, Pampamarca, Yarowilca) says  |
| Lakkos | lat | `coordinates-unresolved` | The Spanish article places the Lakkos site only south of Mount Juktas near Karnari, with no coordinates. The English tit |
| Moylehid | lat | `coordinates-unresolved` | The only decimal points that can be quoted (Wikipedia and Wikidata for Moylehid, 54.32784, -7.77446) belong to the townl |
| Nea Roumata Archaeological Site | period_start | `moved-since-classification` | decided about -800, holds -3100 |
| Wolf Cave | period_start | `field-unresolved` | The sources disagree on whether the cave was inhabited at all. Excavators and tourism/museum pages estimate the finds at |
| Burra Ness Broch | period_start | `moved-since-classification` | decided about 800, holds -800 |
| Cloggs Cave | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0001): Wikipedia's 'around 17,000 years ago' is Flood's 1970s radiocarb |
| Ancient City of Selge | period_start | `field-unresolved` | No source dates Selge's start as a site. Turkish Archaeological News says the origins of the settlement 'still remain a  |
| Shovel Down | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Mawk'ataray | lat | `coordinates-unresolved` | Wikipedia (coord missing) and Wikidata give no point for Mawk'ataray; the Turismo Peruano page reproducing the Mincetur  |
| Mawk'ataray | period_start | `field-unresolved` | The only descriptive source (Turismo Peruano, reproducing the Mincetur inventory) says the remains are 'vestigios de ocu |
| Wiraqucha, Cusco | period_start | `field-unresolved` | The English Wikipedia article describes Wiraqucha (Cusco) as a mountain with a wak'a of two toad-shaped rocks and gives  |
| Bilbao | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0025): The Bilbao quote says only 'since the Preclassic', but the Cotzu |
| Ziari | period_start | `moved-since-classification` | decided about -500, holds -2600000 |
| Moel y Gaer, Rhosesmor | period_start | `moved-since-classification` | decided about -3000, holds -800 |
| Balksbury | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0007): Historic England's list entry 1018562 (Balksbury hillfort) dates |
| Condorcaga | period_start | `field-unresolved` | The English Wikipedia infobox names Chavin culture as builder of Condorcaga (Lajas, Chota, Cajamarca), but that is unref |
| Rempstone Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Nashtifan Windmills | period_start | `field-unresolved` | Tehran Times, Irantripedia and the stored untamediran page give only an estimated age of about 1,000 years (a custodian' |
| Carnedd y Ddelw Cairn | period_start | `moved-since-classification` | decided about -4000, holds -2300 |
| Welsh Road | lat | `coordinates-unresolved` | The Welsh Road is a drovers' route through the English Midlands from Brownhills to Buckingham; no source prints one poin |
| Welsh Road | period_start | `field-unresolved` | Wikipedia states 'The age of the route is not known' and only a probable pre-Roman origin is guessed from boundaries; th |
| Oppidum Uetliberg | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0042): The Uetliberg association page, written with the cantonal archae |
| Bokerley Dyke | period_start | `field-unresolved` | The Dorset HER (heritage.dorsetcouncil.gov.uk/Monument/MDO5932) says only that the dyke 'is thought to have originated i |
| Le Regourdou | period_start | `moved-since-classification` | decided about -500, holds -68050 |
| Korikos Antik Kenti | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0008): The only dating is a sentence that has Herodotus (died c. 425 BC |
| Coggabata | period_start | `moved-since-classification` | decided about -800, holds 43 |
| Brewer's Castle | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Intikancha, Puno | lat | `coordinates-unresolved` | The only readable points (English Wikipedia infobox, Wikidata) are the mountain's summit; the article says the archaeolo |
| Intikancha, Puno | period_start | `field-unresolved` | Wikipedia says only that the archaeological site was declared National Cultural Heritage, with no date; the Wikidata dat |
| Sara Sara | period_start | `field-unresolved` | Sara Sara is a Pleistocene volcano; the English article says it was worshipped 'in and before Inca time' and that its su |
| Pinnacle Hill | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Samicum | period_start | `moved-since-classification` | decided about -500, holds -2000 |
| Metropolis, Thessaly | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0005): The Pleiades string '750 BC - AD 300' is the Barrington Atlas at |
| Bant's Carn | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0002): The same English Heritage page that says Bronze Age tomb dates t |
| Uskallaqta | period_start | `field-unresolved` | No readable page dates Uskallaqta (Uskallacta, Juscallacta; Chivay, Caylloma, Arequipa): English Wikipedia and the Teran |
| Uskallaqta | site_type | `moved-since-classification` | decided about 'Necropolis/tombs complex', holds 'Archaeological site' |
| Juhor | period_start | `field-unresolved` | Veliki Vetren on Juhor is a multi-layer site (Eneolithic, Bronze Age, Iron Age with a Celtic/Scordiscan fort, Roman, med |
| Juhor | source_url | `moved-since-classification` | decided about 'https://en.wikipedia.org/wiki/Juhor', holds 'https://www.turistickiklub.com/sadrzaj/veliki-vetren' |
| Vlajkovac | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0007): The Neolithic date of the Vlajkovac circles is an amateur hypoth |
| Glubochek | lat | `coordinates-unresolved` | The stored point (47.6026, 28.5064) is in Moldova, nowhere near the Trypillia mega-settlement Hlybochok (Glubochek) in T |
| Inka Raqay, Ayacucho | period_start | `field-unresolved` | Spanish Wikipedia calls Incarracay (Inka Raqay, Allqu Willka, Iguain District, Huanta) a site 'perteneciente a la civili |
| Dun Beag Broch | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0037): The HES visitor page for Dun Beag gives a hedged date for this v |
| Showery Tor | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Roman Dam of Fonte Coberta | period_start | `moved-since-classification` | decided about -27, holds 43 |
| Castallack Round | period_start | `field-unresolved` | English Wikipedia dates only the class: rounds 'date from the late Iron Age to the early post-Roman period' and courtyar |
| Tomb of Eve | period_start | `field-unresolved` | The English Wikipedia article gives no date of construction; it quotes Pesce that the first writer to place Eve's tomb i |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s001-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s001 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
