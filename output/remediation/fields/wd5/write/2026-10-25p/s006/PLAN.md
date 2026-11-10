# WD5 fields-wd5-2026-10-25p-s006: plan

Built 2026-10-25T07:55:18+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s006`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s006:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 10 |
| sites_written | 5 |
| refused | 106 |
| cells:period_name | 5 |
| cells:period_start | 5 |
| refused:coordinates-unresolved | 18 |
| refused:field-unresolved | 51 |
| refused:moved-since-classification | 37 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Archaeological Area, Stymphalos | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Archaeological Area, Stymphalos | period_start | `-800` | `-1750` | wd5-replace |
| Grakliani Hill | period_name | `1 - 500 AD` | `4500 - 3000 BC` | wd5-derive-period-name |
| Grakliani Hill | period_start | `43` | `-4500` | wd5-replace |
| Mên Scryfa | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Mên Scryfa | period_start | `-4000` | `-2500` | wd5-replace |
| Pintia | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd5-derive-period-name |
| Pintia | period_start | `-600` | `-500` | wd5-replace |
| Tulamba | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd5-derive-period-name |
| Tulamba | period_start | `-1500` | `-500` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Ballinran Court Tomb | period_start | `moved-since-classification` | decided about -800, holds -4000 |
| Dead Woman's Ditch | period_start | `field-unresolved` | The only source that dates Dead Woman's Ditch (Over Stowey, Quantock Hills, Somerset) at all is English Wikipedia, which |
| Gårdstånga | lat | `coordinates-unresolved` | The site is a single Bronze Age burial mound at Gardstanga, but the parish holds many registered mounds (and Swedish Wik |
| Gårdstånga | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Camboglanna | period_start | `field-unresolved` | English Wikipedia (Camboglanna) names only the 2nd- and 3rd-century garrisons and the 1934 excavation; roman-britain.co. |
| Preston Candover Long Barrow | period_start | `field-unresolved` | The English Wikipedia article calls the monument an unchambered long barrow but gives no date or period for it, and a pe |
| Karabel Kilisesi | period_start | `field-unresolved` | Karabel has two churches that the sources date differently (Kultur Envanteri gives the western church the 6th and 9th ce |
| Karabel Kilisesi | source_url | `field-unresolved` | The Kultur Envanteri has separate pages for Karabel Bati Asarcik Kilisesi and Karabel Dogu Asarcik Kilisesi; nothing say |
| Small Down Knoll | period_start | `moved-since-classification` | decided about -800, holds -2500 |
| Hybla Gereatis | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0027): The Digital Atlas of the Roman Empire 'temporal coverage' (-550  |
| Stripple Stones | period_start | `moved-since-classification` | decided about -4000, holds -2900 |
| Gazma Cave | lat | `coordinates-unresolved` | The only printed point (39°32′18″N 45°10′45″E, fr/ru/az/uk/pl Wikipedia, copied from Wikidata Q25536560 without a refere |
| Gazma Cave | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0003): The Polish Wikipedia 100-80 ka figure is contradicted by the pee |
| Dosariyah | site_type | `field-unresolved` | The English and German Wikipedia articles call Dosariyah an archaeological site and state that whether it was a permanen |
| Waqutu | lat | `coordinates-unresolved` | English Wikipedia's Waqutu has an empty coordinates field ({{coord missing|Peru}}) and Wikidata Q17104431 has no P625. T |
| Inka Murata | lat | `coordinates-unresolved` | English Wikipedia (flagged 'Bolivia articles missing geocoordinate data') and its Wikidata item Q17073756 carry no point |
| Umm es-Sawan Ancient Basalt Quarry | lat | `moved-since-classification` | decided about 29.71075495509649, 30.894883188062366, holds 29.711667, 30.883333 |
| Carfury Standing Stone | period_start | `field-unresolved` | English Wikipedia describes the 1957-58 Pool and Russell excavation (stone erected in an elliptical pit, little else fou |
| Hualpayunca | period_start | `moved-since-classification` | decided about 1, holds 1000 |
| Casteddu di Puzzonu | lat | `coordinates-unresolved` | No readable page prints a point for Casteddu di Puzzonu in Sartene: the English, French and Corsican Wikipedia stubs and |
| Anta do Alto da Toupeira | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0034): The quote says the dolmen 'dates back to the Chalcolithic', whic |
| Killa Mach'ay | lat | `coordinates-unresolved` | Only the Wikipedia/Wikidata family prints a point (es.wikipedia Quillamachay, Wikidata Q21044255: -12.86125, -74.581472, |
| Killa Mach'ay | period_start | `field-unresolved` | MINCETUR ficha 4281 and Wikipedia do not date the paintings. Ruiz Estrada's article (Arqueologia y Sociedad 13, 2000; Re |
| Lohum Jo Daro | period_start | `moved-since-classification` | decided about -4000, holds -2600 |
| Stairhaven | lat | `moved-since-classification` | decided about 54.8471858335266, -4.8696655689456225, holds 54.842845, -4.790692 |
| Hedum castellum | lat | `coordinates-unresolved` | The site's own location is not established: Bosnian Wikipedia (Hedum) says 'Za sada se još uvijek nije poznata tačna ubi |
| Hedum castellum | period_start | `field-unresolved` | Bosnian Wikipedia only says Hedum 'je postojao i u predrimsko vrijeme, u formi gradinskog naselja' (it also existed in p |
| Krzesin, Lubusz Voivodeship | period_start | `moved-since-classification` | decided about -4000, holds 500 |
| Abrigo do Lagar Velho | period_start | `moved-since-classification` | decided about -500, holds -50000 |
| Chaa Creek | lat | `coordinates-unresolved` | No readable page prints a point for the Chaa Creek Maya settlement (Stela, Plantain and Tunchilen groups, Cayo District, |
| Garakopaktapa | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0002): Azerbaijani Wikipedia and the Early Bronze Age monograph describ |
| Cierium | period_start | `moved-since-classification` | decided about -800, holds -1600 |
| Ayamachay | period_start | `moved-since-classification` | decided about -10000, holds 1438 |
| Kvitky | lat | `coordinates-unresolved` | The stored point (49.3136, 31.2341) lies at the village of Kvitky (uk.wikipedia village point 49.31583, 31.24583, about  |
| Kvitky | period_start | `field-unresolved` | The only readable scholarly page (trypillia.com, Videiko et al. 2011) assigns the Kvitky sites to Trypillia stage CI but |
| Cabezo Juré | lat | `coordinates-unresolved` | No readable source prints a point for the site itself. The English and Spanish Wikipedia articles carry no coordinate, W |
| Morgan's Hill Enclosure | period_start | `field-unresolved` | English Wikipedia says of Morgan's Hill Enclosure (Wiltshire) that the 1909 excavation found only medieval surface potte |
| Pylos | period_start | `field-unresolved` | The entry is the modern town of Pylos on Navarino Bay (current city built from 1829; Wikidata inception 1865). The Wikip |
| La Noce de Pierres | period_start | `field-unresolved` | The Brittany heritage inventory (bretania.bzh), Petit Fute, Cirkwi and the French Wikipedia infobox call the alignment o |
| Castle Crag | period_start | `field-unresolved` | Wikipedia's Castle Crag article is the mountain and says only that the summit is believed to have been an ancient hill f |
| Petroglyph Beach State Historic Park | period_start | `field-unresolved` | The Alaska State Parks page says only that the site itself is about 8000 years old; other pages say the carvings are est |
| Ex voto of the Tarentines | lat | `coordinates-unresolved` | Wikidata Q24913820 and the English and Greek Wikipedia articles on the Ex voto of the Tarentines carry no coordinates, a |
| Perge Sütunlu Cadde | period_start | `field-unresolved` | No reputable source dates the start of the colonnaded street itself. Princeton Encyclopedia (topostext), Turkish Archaeo |
| Roman Rig | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0016): The framework only calls an Iron Age origin (earlier or later) m |
| Yongin Wangsanli Jiseongmyo | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0040): The English article does call the tombs Bronze Age, but -2500 is |
| Batik Sehir Kekova | lat | `moved-since-classification` | decided about 36.197919601694004, 29.845612106746632, holds 36.177559, 29.858082 |
| Batik Sehir Kekova | period_start | `field-unresolved` | English Wikipedia, the Cornucopia guide and the Kultur Envanteri record only date the earthquake of the 2nd century AD t |
| Moel y Gest | period_start | `field-unresolved` | No readable source dates the Moel y Gest hillfort. Cadw's record CN059 (Moel y Gest Camp, Porthmadog) gives only the per |
| Trencrom Hill | period_start | `moved-since-classification` | decided about -800, holds -4000 |
| Villa of Torre de Palma | period_start | `moved-since-classification` | decided about 1, holds -700 |
| Besh Barmag Mountain | period_start | `field-unresolved` | Besh Barmag is a natural rock mountain and pilgrimage place. The English article dates only the tide marks (end of the l |
| Paphos | lat | `moved-since-classification` | decided about 34.76682531638928, 32.41674179819703, holds 34.76025, 32.40795 |
| Castle Close | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Humbleton Hill | period_start | `field-unresolved` | The English Wikipedia article is inconsistent about the earliest phase: the lead says 'an enclosed settlement of the Neo |
| Chactún | period_start | `field-unresolved` | No source gives a start for Chactun itself that can be quoted as a date. English Wikipedia's 600 to 900 AD is the Late C |
| Cova Foradà | period_start | `moved-since-classification` | decided about 1, holds -300000 |
| Great Serpent Mound | period_start | `field-unresolved` | The age of Serpent Mound is disputed in the peer-reviewed literature: Herrmann, Romain and colleagues (2014, defended in |
| Aughlish | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Kızlar Kalesi | period_start | `field-unresolved` | Sources disagree on the castle's date: English and Turkish Wikipedia say it can be dated to the 4th century (Late Roman) |
| Salou | period_start | `field-unresolved` | English Wikipedia says Salou was 'founded by the Greeks in the 6th century B.C.', but offers no archaeological basis. Ca |
| Bidjigal Reserve | period_start | `field-unresolved` | The only dating found is English Wikipedia's 'a midden dated to 10150 bp, which is the earliest human habitation site kn |
| Botley Stone | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| La Ferrassie | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0020): The quoted 74-68 ka is the date of the thin layer with the Neand |
| Dudsbury Camp | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Broch of West Burrafirth | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0007): The only dated statement for this broch is a 1st-century AD one  |
| Balberta | period_start | `moved-since-classification` | decided about 1, holds -400 |
| Withypool Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2350 |
| Roborough Castle | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Long Wood Enclosure | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Greater Ridgeway | lat | `coordinates-unresolved` | The Greater Ridgeway is a 362-mile long-distance footpath from Lyme Regis to Hunstanton, a combined route of four trails |
| Greater Ridgeway | period_start | `field-unresolved` | Wikipedia and the Great Chalk Way site describe the Greater Ridgeway as a modern combined walking and riding route that  |
| Granite Thrones of Judges of Axum | lat | `coordinates-unresolved` | The Thrones of the Judges are about 13 throne bases outside the Cathedral of Our Lady Mary of Zion in Aksum (habeshahist |
| Granite Thrones of Judges of Axum | period_start | `field-unresolved` | The sources read (habeshahistory.com on Maryam Tsion, Wikipedia Axum, archaeotravel.eu, EBSCO) name the thrones of the j |
| Typalia Antik Kenti | period_start | `moved-since-classification` | decided about -1500, holds -500 |
| Jasov Cave | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0007): The cited page itself dates the cave's finds from the Palaeolith |
| Settlements of the Cucuteni-Trypillia Culture | lat | `coordinates-unresolved` | The entry stands for the Wikipedia list of Cucuteni-Trypillia settlements, which covers many hundreds of sites across Uk |
| Kealkill Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Rocha dos Namorados | period_start | `field-unresolved` | The Rocha dos Namorados (Corval, Reguengos de Monsaraz) is a natural granite outcrop: English Wikipedia says there is no |
| Kamyana Mohyla | period_start | `moved-since-classification` | decided about -2000, holds -10000 |
| Carachupa | period_start | `field-unresolved` | The English and Spanish Wikipedia articles on Carachupa (Lonya Grande, Utcubamba, Amazonas) and the Maranon Waterkeeper  |
| Magh Slécht | period_start | `moved-since-classification` | decided about -10000, holds -4000 |
| Türkenfeld | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0022): English Wikipedia only says Neolithic, but German Wikipedia, whi |
| Eva, Arcadia | period_start | `field-unresolved` | The one dated account of the fortified town of Eua (Helleniko, Teichio ridge) is Balandier and Guintrand, BCH 143 (2019) |
| Aston Valley Barrow Cemetery | period_start | `moved-since-classification` | decided about -800, holds -2500 |
| Al Diwan | lat | `coordinates-unresolved` | No readable source prints a point for the al-Diwan chamber itself. Wikipedia and UNESCO give a point for the whole of He |
| Al Diwan | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0036): The Google quote only says sanctuaries of the area are 'from the |
| Ancient City of Perrin | period_start | `field-unresolved` | No source dates the start of the ancient city of Perrhe (Perre, Pirin). The stored 433 is the year of Andreas of Samosat |
| Grey Wethers | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Alarcos | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0040): The recorded quote does not state the start of the hill: it spea |
| Choquequirao Puquio | period_start | `field-unresolved` | The only statement of a period for Choquequirao Puquio (San Sebastian, Cusco) is the Inca culture field in the English W |
| Stalldown Barrow | period_start | `field-unresolved` | English Wikipedia calls Stalldown Barrow only 'a megalithic site' with a long stone row; the Dartmoor Site page says the |
| Apidima Cave | period_start | `moved-since-classification` | decided about -500, holds -208050 |
| Treasure of Osztrópataka | lat | `coordinates-unresolved` | No source prints a point for the burial itself. The English Wikipedia article and Wikidata Q18167176 carry no coordinate |
| Roman Remains under Alfonso X Street | lat | `coordinates-unresolved` | English Wikipedia and its Wikidata item (Q30593134) carry no coordinates. The Castilla-La Mancha tourism board page for  |
| Požun, Croatia | period_start | `field-unresolved` | Only the English Wikipedia article mentions anything ancient at Požun: a stone axe in the Ozalj Castle museum, called Ne |
| Wanakawri, Huánuco | lat | `coordinates-unresolved` | The English article (Wanakawri, Huanuco) and Wikidata Q15950097 print no point; the stored point is the centre of Chinch |
| Wanakawri, Huánuco | period_start | `field-unresolved` | Sources call Huanacaure an Inca site (Ministerio de Cultura Qhapaq Nan project report, tourism inventory) with an earlie |
| Longyou Grottoes | period_start | `field-unresolved` | English Wikipedia says outright that it is unknown when the Longyou caves were created: pots dated to 206 BC-23 AD were  |
| Bahşeyiş Anıtı | period_start | `moved-since-classification` | decided about 43, holds -550 |
| Ponter's Ball Dyke | period_start | `field-unresolved` | The Wikipedia article gives three incompatible origins for Ponter's Ball Dyke (a Celtic sanctuary 'probably 3rd century  |
| Icknield Way | period_start | `field-unresolved` | The Icknield Way is an ancient trackway whose age is disputed: the Wikipedia article says only that the route existed 'a |
| New Ditch | period_start | `field-unresolved` | English Wikipedia calls New Ditch (Butleigh Wood, Polden Hills, Somerset) a linear earthwork of possible Iron Age or Med |
| Buzbury Rings | period_start | `moved-since-classification` | decided about -800, holds -4000 |
| Sotin | period_start | `moved-since-classification` | decided about -500, holds -4500 |
| America's Stonehenge | period_start | `moved-since-classification` | decided about 1801, holds -2050 |
| Twmbarlwm | period_start | `moved-since-classification` | decided about -500, holds -800 |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s006-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s006 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
