# WD5 fields-wd5-2026-10-25p-s004: plan

Built 2026-10-25T07:53:19+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s004`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s004:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 10 |
| sites_written | 5 |
| refused | 110 |
| cells:period_name | 5 |
| cells:period_start | 5 |
| refused:coordinates-unresolved | 24 |
| refused:field-unresolved | 51 |
| refused:moved-since-classification | 35 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Ballochmyle Cup and Ring marks | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd5-derive-period-name |
| Ballochmyle Cup and Ring marks | period_start | `-10000` | `-4000` | wd5-replace |
| Bribir, Šibenik-Knin County | period_name | `1 - 500 AD` | `3000 - 1500 BC` | wd5-derive-period-name |
| Bribir, Šibenik-Knin County | period_start | `1` | `-2500` | wd5-replace |
| Carmona, Spain | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Carmona, Spain | period_start | `-800` | `-2550` | wd5-replace |
| Gudenus Cave | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd5-derive-period-name |
| Gudenus Cave | period_start | `-500` | `-68050` | wd5-replace |
| Puna Pau | period_name | `1 - 500 AD` | `1000 - 1500 AD` | wd5-derive-period-name |
| Puna Pau | period_start | `1` | `1250` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Naulette | period_start | `field-unresolved` | No readable page gives a quotable date or English period name for the Naulette finds: English Wikipedia says only that t |
| Dun Telve | period_start | `moved-since-classification` | decided about -400, holds -550 |
| Tlalpan | period_start | `field-unresolved` | The Spanish Wikipedia article on the historic centre of Tlalpan states that nothing is known of the exact date of its fo |
| Albanopolis | period_start | `field-unresolved` | No source dates the start of Albanopolis itself. English Wikipedia only says the city 'appears in the literature in 150  |
| Dinas Powys Hillfort | period_start | `field-unresolved` | Sources disagree about when Dinas Powys began. English Wikipedia (following Alcock 1963) gives the third or 2nd century  |
| Borkowo Megalithic Cemetery | period_start | `moved-since-classification` | decided about -800, holds -3000 |
| Lia Fáil | period_start | `field-unresolved` | English Wikipedia (Lia Fail, Hill of Tara), Heritage Ireland and irishmegaliths.org.uk give no date for the stone: Wikip |
| El Castillón | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0007): The excavators' page places the first stable occupation in the S |
| Grey Croft Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2900 |
| Honcopampa | period_start | `moved-since-classification` | decided about 1, holds 600 |
| Levänluhta | lat | `coordinates-unresolved` | no counted answer in 3 rounds: quote not found: https://fi.wikipedia.org/wiki/Lev%C3%A4nluhta; quote not found: https:// |
| Leper Stone | period_start | `field-unresolved` | No source dates the Leper Stone. Wikipedia only says it may have been set up as a menhir and derives the name from the m |
| Auquin Punta | lat | `coordinates-unresolved` | The Wikipedia/Wikidata point (9 32 21 S 76 44 14 W) coincides with the centroid of Jacas Grande District, not with the c |
| Auquin Punta | period_start | `field-unresolved` | The Turismo Peruano record (MINCETUR tourist inventory, https://www.turismoperuano.com/sitio-arqueologico-auquin-punta-h |
| Stina, Ukraine | lat | `coordinates-unresolved` | The stored point is the centre of the village of Stina (48 27 21 N, 28 25 04 E on English Wikipedia), not a settlement.  |
| Stina, Ukraine | period_start | `field-unresolved` | Frontiers (Chapman et al. 2019) calls Stina an 'isolated' megasite of Trypillia Phase CI but gives no calendar year for  |
| Boleigh Fogou | period_start | `field-unresolved` | Wikipedia says only that 'Iron Age pottery was found at the fogou'; the Cornwall Guide says the fogou is 'Thought to be  |
| Gavur Evi Anıtı | lat | `coordinates-unresolved` | Gavur Evi is a rock-cut tomb (yalı mezarı) in Değirmenözü neighbourhood, Manavgat (Antalya), per the Manavgat municipali |
| Gavur Evi Anıtı | period_start | `field-unresolved` | The Manavgat municipality page calls Gavur Evi a rock tomb among many rock-cut graves on the old Royal Road, but gives n |
| Intini Uyu Pata | lat | `coordinates-unresolved` | English Wikipedia carries no point; the Wikidata point (-16.2551, -69.0705) lies about 9 km from the stored one, near Yu |
| Intini Uyu Pata | period_start | `field-unresolved` | MINCETUR ficha 4790 assigns the temple to the Colla kingdom of the Lupaca society of the Aymara domain without any date, |
| Lighthouse of Leptis Magna | period_start | `moved-since-classification` | decided about -1500, holds 193 |
| Cappadocia | lat | `coordinates-unresolved` | The entry is named Cappadocia, which English Wikipedia and Wikidata Q217265 define as a historical region of Central Ana |
| Cappadocia | period_start | `field-unresolved` | A historical region has no construction, foundation or first-occupation date of its own; the sources date the Cappadocia |
| Shell Mound in Dongsam-dong, Busan | period_start | `moved-since-classification` | decided about -3500, holds -6050 |
| Chongam-ri Earthen Castle | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0029): The quote only reports one scholars' view (a 'view exists') that |
| The Lion Gate | lat | `coordinates-unresolved` | No readable page gives a point for the Lion Gate itself. The Unibo Butrint page, the whatsdavedoing guide and the Mindtr |
| The Lion Gate | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0001): The Wikipedia quote dates the acropolis outer wall as a whole (a |
| Grotta del Cavallo | period_start | `moved-since-classification` | decided about 1, holds -300000 |
| Lepreum | period_start | `moved-since-classification` | decided about -1500, holds -4000 |
| Cieza, Murcia | period_start | `moved-since-classification` | decided about -1500, holds -3000000 |
| Kinal | period_start | `field-unresolved` | English Wikipedia dates only the major occupational phase of Kinal to the Late Classic (c. AD 600-900) and an expansiona |
| Sutkagan Dor | period_start | `moved-since-classification` | decided about -800, holds -2600 |
| Brown Clee Hill | period_start | `moved-since-classification` | decided about -443800, holds -800 |
| Uqair Salt Mine Archaeological Site | lat | `coordinates-unresolved` | The English article and Wikidata item Q22690137 (no P625) give no point; the Arabic article and Nabataea.net page give n |
| Beacon Hill, Leicestershire | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0007): The Megalithic Portal says only 'believed to be of Late Bronze A |
| Bedd Arthur | period_start | `field-unresolved` | The sources do not agree and none dates Bedd Arthur itself: Wikipedia calls it only 'possibly Neolithic' and says the un |
| Pumamarka, San Sebastián | lat | `coordinates-unresolved` | The English article places the park only on the left side of the river Pumamarka in San Sebastian District; Wikidata Q15 |
| Biannus | period_start | `field-unresolved` | English Wikipedia says only that remains at Ano Viannos run from the Orientalizing period to Roman times, ToposText labe |
| House of the Knight | period_start | `field-unresolved` | No readable source dates the House of the Knight (Maison au Cavalier) at Volubilis: English and French Wikipedia give it |
| Su Kemeri | source_url | `moved-since-classification` | decided about 'https://www.wikidata.org/wiki/Q135582591', holds 'https://zenodo.org/records/14577067' |
| Carn Menyn | period_start | `field-unresolved` | Carn Menyn is a natural tor outcrop and no source dates a construction or foundation. The only start dates are for quarr |
| Carnfree | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Dizə, Sharur | period_start | `field-unresolved` | The article is about the present-day village and municipality of Dize, whose own beginning it does not date. It dates tw |
| Tregele | period_start | `field-unresolved` | Tregele is a small modern village in Llanbadrig community, north Anglesey (Wikipedia); the only ancient monument it ment |
| Breitenbach - Archaeological Site | period_start | `moved-since-classification` | decided about -500, holds -50000 |
| Grubstones | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Home Tombs | lat | `coordinates-unresolved` | The site is the Evkaya (Ev Kaya) rock tombs just south of Kastamonu city centre. The pages I could read as plain HTML (K |
| Mawk'allaqta, La Unión | lat | `coordinates-unresolved` | Wikidata Q15950057 has no P625 and neither the English nor the French article prints a point. The stored point is the on |
| Mawk'allaqta, La Unión | period_start | `field-unresolved` | The sources disagree on who founded the site. English and French Wikipedia say it was developed by the Wari culture (abo |
| Huiñao | period_start | `moved-since-classification` | decided about 1, holds 600 |
| Suessula | period_start | `moved-since-classification` | decided about -500, holds -900 |
| Annadorn Dolmen | period_start | `field-unresolved` | No reputable source dates Annadorn Dolmen. The Department for Communities page and its NISMR record (DOW 030:007), Engli |
| Mausoleum of Tangun | period_start | `field-unresolved` | The sources disagree on when this tomb began: North Korean historians claim about 3000 BCE from electron-spin-resonance  |
| Tapınak | period_start | `moved-since-classification` | decided about 1000, holds -323 |
| Tapınak | source_url | `moved-since-classification` | decided about None, holds 'https://kulturenvanteri.com/en/yer/phaselis-helenistik-tapinak/' |
| The Ridgeway | period_start | `field-unresolved` | Popular sources (Wikipedia, Historic UK, BBC Travel) say the Ridgeway has been used for about or at least 5,000 years, a |
| Camel Carving Site | lat | `coordinates-unresolved` | No readable page prints a point for the Camel Site: the English and Arabic Wikipedia articles, the Wikidata item (no P62 |
| Padderbury Top | period_start | `field-unresolved` | The English Wikipedia article on Padderbury Top (near Menheniot, Cornwall) calls it a hillfort and a 'defended settlemen |
| Walton Common | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Alverdiscott | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0006): The Iron Age enclosure and Roman camp is a scheduled monument in |
| Hatay Altınözü Yunushanı Gelinler Dağı Nekropolü | lat | `coordinates-unresolved` | The pages I read about the Yunushan Gelinler Dagi necropolis (Hurriyet Seyahat, the Altinozu district governor and educa |
| Hatay Altınözü Yunushanı Gelinler Dağı Nekropolü | period_start | `moved-since-classification` | decided about -800, holds 43 |
| Hoarstones | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Sa Cudia Cremada | period_start | `field-unresolved` | English Wikipedia says the remains belong to the Talaiotic culture of the Bronze and Iron Ages and gives no start year.  |
| Al Naslaa | period_start | `field-unresolved` | Al Naslaa is a wind-eroded sandstone landform; the English Wikipedia article gives no date, the Arabian Rock Art Heritag |
| Dmanisi | period_start | `moved-since-classification` | decided about -4500, holds -1798050 |
| Sacul | period_start | `field-unresolved` | Wikipedia (en and es) says only that Sacul's main period of occupation is the Late Classic and that its sculpted monumen |
| La Chapelle-aux-Saints | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0020): The 70 ka of the Prehistory of France page is contradicted by th |
| Gilwern Hill, Powys | period_start | `moved-since-classification` | decided about -4000, holds -2300 |
| Caer Drewyn | period_start | `moved-since-classification` | decided about -500, holds -800 |
| Black Mountain (Pima County, Arizona) | period_start | `field-unresolved` | English Wikipedia says only that the summit carries the ruins of an ancient Hohokam fortification (no date); the Tucson- |
| Medusa Mozaiği | lat | `coordinates-unresolved` | The mosaic is the Medusa floor of the Odeon of Kibyra (Hürriyet Daily News; English Wikipedia on Kibyra). The only point |
| GOLOGOÇ VİRANŞEHİR ŞANLIURFA TARİHİ KEMER | lat | `coordinates-unresolved` | The only page found about the Gologoc historic arch is a Yandex Maps business listing, a map directory (it files the arc |
| GOLOGOÇ VİRANŞEHİR ŞANLIURFA TARİHİ KEMER | period_start | `field-unresolved` | No reputable source about the Gologoc arch exists that I could find; the Yandex listing gives no age, period or architec |
| GOLOGOÇ VİRANŞEHİR ŞANLIURFA TARİHİ KEMER | source_url | `field-unresolved` | No Wikipedia article, Wikidata item or heritage register record for a Gologoc arch exists; the only page about it is a Y |
| Kanamarka | period_start | `field-unresolved` | English Wikipedia gives no date. Salazar et al. 2023 (Science Advances, PMC11318671) call it 'the rural Inca settlement  |
| Marsoulas Cave | period_start | `moved-since-classification` | decided about -500, holds -15050 |
| Ide, Devon | period_start | `field-unresolved` | Ide is a living village near Exeter. English Wikipedia, the Wikidata item (no inception statement), GENUKI, the Italian  |
| Chalai, Thessaly | period_start | `field-unresolved` | English Wikipedia (after Hansen & Nielsen) says only that remains of the Archaic and Classical periods have been found a |
| Markansaya | lat | `coordinates-unresolved` | Wikidata Q15950022 has no P625, and the English and Spanish Wikipedia articles carry no point (the Spanish page is in it |
| Hisar Hill | period_start | `moved-since-classification` | decided about -1350, holds -4000 |
| Brean Down | lat | `coordinates-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0008): The stored point already has sources: the Megalithic Portal hill |
| Brean Down | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0008): The quote dates only the hillfort's defences by a tourist site,  |
| Intiyuq K'uchu | period_start | `moved-since-classification` | decided about -10000, holds 1438 |
| Tunanmarca | site_type | `moved-since-classification` | decided about 'Archaeological site', holds 'City/town/settlement' |
| Lamay | lat | `coordinates-unresolved` | Lamay (the Central Complex of Dzibanche) is described by INAH and English Wikipedia only as one of the four groups of th |
| Lamay | period_start | `field-unresolved` | INAH says only that Lamay functioned for a short time, 'towards the end of the Classic' (lugares.inah.gob.mx/en/node/439 |
| Savaria Mithraeum | period_start | `field-unresolved` | English Wikipedia, the French article and the Hungarian press report of the 2008 excavation (Kronika/MTI) say only that  |
| Więckowy | lat | `coordinates-unresolved` | The stored point (54.0601, 18.3872) is the village of Wieckowy as English Wikipedia and Wikidata print it, not the regis |
| Dalj | period_start | `field-unresolved` | The sources for Dalj give no machine-readable start of the settlement itself. The Hrvatska enciklopedija says the villag |
| Goffers Knoll | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Mount Namsan Belt | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0039): The quote only says Namsan holds remains from the Silla period,  |
| Mellor Hill Fort | period_start | `moved-since-classification` | decided about -800, holds -500 |
| Frourio Hill | period_start | `field-unresolved` | English and Greek Wikipedia articles on Frourio Hill and the Ministry of Culture page (odysseus.culture.gr, obj_id 7044) |
| Pukara, Coporaque | lat | `coordinates-unresolved` | The English article only places the ruins on the left side of the road from Chivay to Coporaque and Wikidata Q17086526 h |
| Aglaureion | period_start | `field-unresolved` | No page dates the foundation of the Aglaureion cave sanctuary. English Wikipedia (Aglaureion; Cave Sanctuaries of the Ac |
| Qullqapampa | lat | `coordinates-unresolved` | Neither the English Wikipedia article nor Wikidata Q15950077 prints a coordinate; the tourism pages found place Qullqapa |
| Eddisbury Hill Fort | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0011): The 400 BC date is the 'developed' hillfort only: Pope et al. 20 |
| Aiadava | period_start | `field-unresolved` | No source dates the start of Aiadava. English, Romanian and Spanish Wikipedia (one source family) call it a Dacian town  |
| Temple of Hercules Gaditanus | lat | `coordinates-unresolved` | The English Wikipedia article prints no coordinates and says that LiDAR studies place the temple either under water in t |
| Cloaca, Capri | lat | `coordinates-unresolved` | The English, Norwegian, Italian and German Wikipedia pages print no coordinates for the Cloaca of Capri and Wikidata Q51 |
| Cloaca, Capri | period_start | `moved-since-classification` | decided about -500, holds 43 |
| Quesera (Cheeseboard) de Zonzamas | period_start | `field-unresolved` | No source dates the Quesera itself: ilanzarote.com calls its function an enigma and Spanish Wikipedia only lists it amon |
| Goodaver Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Parque Arqueológico do Solstício | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0003): The Pijama Surf page puts Rego Grande in the north of Ecuador an |
| Anku | lat | `coordinates-unresolved` | English Wikipedia's Anku point (9 21 S 76 35 W) lies about 15 km east of Tantamayo and the Wikidata/Spanish point about  |
| Anku | period_start | `field-unresolved` | Wikipedia and the Turismo Peruano record for Ango say only that the citadel was inhabited, excavated by Girault and Flor |
| Lake Mungo | period_start | `moved-since-classification` | decided about -500, holds -48050 |
| Saoba Stone Pillars | period_start | `moved-since-classification` | decided about -3000, holds -1050 |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s004-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s004 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
