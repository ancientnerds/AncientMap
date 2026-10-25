# WD5 fields-wd5-2026-10-25p-s007: plan

Built 2026-10-25T07:56:14+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s007`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s007:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 4 |
| sites_written | 2 |
| refused | 114 |
| cells:period_name | 2 |
| cells:period_start | 2 |
| refused:coordinates-unresolved | 22 |
| refused:country-changes | 1 |
| refused:field-unresolved | 53 |
| refused:moved-since-classification | 38 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Castle Goff | period_name | `4500 - 3000 BC` | `1500 - 500 BC` | wd5-derive-period-name |
| Castle Goff | period_start | `-4000` | `-800` | wd5-replace |
| Wilcahuaín | period_name | `1000 - 1500 AD` | `500 - 1000 AD` | wd5-derive-period-name |
| Wilcahuaín | period_start | `1100` | `600` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Termessos Tiyatrosu | period_start | `moved-since-classification` | decided about 43, holds -200 |
| Gilching | lat | `coordinates-unresolved` | The entry stands for the prehistoric barrows of the municipality of Gilching, which the Zeitreise Gilching page places a |
| Gilching | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0022): The quoted sentence dates barrows in general (Hügelgräber wurden |
| Bruniquel Cave | period_start | `moved-since-classification` | decided about -500, holds -174550 |
| Bohonagh Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Ecclesall Woods | period_start | `field-unresolved` | The cup-and-ring rock is dated by Wikipedia and stone-circles.org.uk only to the late Neolithic or the Bronze Age, two a |
| Sar Ruins | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0046): The tourism page's 2nd-millennium BC date rests on equating Coma |
| Phthiotic Thebes | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0025): The only statement is one unreferenced sentence ('Evidence of hu |
| Naveta | lat | `coordinates-unresolved` | The item (Wikidata Q1234523, English article 'Naveta') is the type of Menorcan funerary chamber tomb, not one monument:  |
| Naveta | period_start | `field-unresolved` | A naveta here is a class of monuments: English Wikipedia dates the earlier proto-navetas to 1700-1300 BCE and the funera |
| Cuchi Machay | lat | `moved-since-classification` | decided about -12.121189584971145, -76.01222220434111, holds -12.026272, -75.958327 |
| Cuchi Machay | period_start | `moved-since-classification` | decided about -10000, holds -4000 |
| Waqlamarka | lat | `coordinates-unresolved` | The English article carries {{coord missing|Peru}} and Wikidata Q17104420 has no point; the readable MINCETUR inventory  |
| Ñawpallaqta, Huanca Sancos | lat | `coordinates-unresolved` | The English Wikipedia article and Wikidata item Q15950015 carry no coordinate; the stored point equals the Carapo Distri |
| Prosymna | period_start | `moved-since-classification` | decided about -800, holds -4000 |
| Am Forsthofweg | period_start | `field-unresolved` | English Wikipedia says no final statements can be made about the beginning or the end date of the small fort Am Forsthof |
| Kuhikugu | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0003): The quote dates the settling of the whole Upper Xingu by the Xin |
| Upuigma Rock Shelter | lat | `coordinates-unresolved` | The stored point (5.0860, -61.9569) equals the English Wikipedia point of the mountain Upuigma-tepui (5 05 10 N, 61 57 2 |
| Upuigma Rock Shelter | period_start | `field-unresolved` | The only dating on the stored source page (archaeology-world.com) says that similar rock art in Brazil has been dated to |
| Menir da Cabeça do Rochedo | period_start | `moved-since-classification` | decided about -2000, holds -4000 |
| Concordia - Remains of the Roman Temple of Augustus | lat | `coordinates-unresolved` | No readable source prints a point for the temple remains in Calle Holguin, Merida. The stored source (monumentalnet.org) |
| Awkimarka, Apurímac | period_start | `moved-since-classification` | decided about 1, holds 1200 |
| Thornbury, Herefordshire | period_start | `field-unresolved` | The Wikipedia article describes Thornbury as a village in Herefordshire with a population count and two nearby hill fort |
| Tan Hill, Wiltshire | period_start | `field-unresolved` | The stored source page (wiltshirewhitehorses.org.uk/tanhill.html) says only that a white horse or donkey figure once exi |
| Markapukyu | period_start | `field-unresolved` | The English and French Wikipedia articles give no date. The only dating found is the Mincetur-derived text on turismoper |
| Dinas Emrys | period_start | `field-unresolved` | The sources disagree about when Dinas Emrys (Beddgelert, Gwynedd) began: English Wikipedia's lead calls it an Iron Age h |
| Acumincum | period_start | `field-unresolved` | No quotable source dates the start of Acumincum/Gradina. English Wikipedia's 3rd century BC refers to 'the area' being i |
| Huamboy | lat | `coordinates-unresolved` | The stored point (-16.5710, -72.7151) and the Wikidata mountain point are the centre of Nicolas de Pierola District near |
| Huamboy | period_start | `field-unresolved` | The only dating source is the MINCETUR inventory text on turismoperuano.com, which assigns the complex 'desde el Periodo |
| Platt | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0002): German Wikipedia on Platt gives the earliest evidence as the Not |
| Arroyo de Piedra | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0025): The encyclopedia.com sentence says the Petexbatun centers Tamari |
| Anju Castle | lat | `coordinates-unresolved` | No page prints a point for the castle itself: English and Korean Wikipedia and the Wikidata item (Q25080767) carry none, |
| Anju Castle | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0029): The value -37 is the founding of the Goguryeo kingdom (the perio |
| Megalithic Wall, Gubbio | lat | `coordinates-unresolved` | The heracles-project page, Key to Umbria and Anne's Italy describe Gubbio's old town walls and gates in words and print  |
| Warratyi | period_start | `moved-since-classification` | decided about -500, holds -47050 |
| Colybrassus Antik Kenti | period_start | `moved-since-classification` | decided about 43, holds -323 |
| Teotihuacan - Tetitla | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0006): The student page's 350-550 C.E. is the Xolalpan-phase span of th |
| Ksaverove | lat | `coordinates-unresolved` | The stored point (49.1946, 31.5181) is the village of Ksaverove. The readable pages only list the Trypillia settlement:  |
| Ksaverove | period_start | `field-unresolved` | The only readable source on the settlement (trypillia.com, Videiko et al. 2011) assigns Ksaverove (about 100 ha) to Tryp |
| Dendra | period_start | `moved-since-classification` | decided about -3000, holds -4000 |
| Taliata | lat | `coordinates-unresolved` | The only source point is the Digital Atlas of the Roman Empire / Pleiades / Trismegistos point 44.443587, 22.144349, whi |
| Kaljaja, Teneš Do | lat | `country-changes` | the new point lies in ['Kosovo'], the site says Serbia |
| Kaljaja, Teneš Do | period_start | `field-unresolved` | The only datings found are Serbian: the SANU register 'Spomenici kulture u Srbiji' (record id 415) calls the period 'pre |
| Soğmatar | site_type | `moved-since-classification` | decided about 'Ruin', holds 'Sacred site' |
| Axura Nekropolises | lat | `coordinates-unresolved` | No page prints a point for the Axura necropolises themselves. The English, Azerbaijani and Turkish Wikipedia articles an |
| Axura Nekropolises | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0002): The English page is garbled; the Azerbaijani Wikipedia (from Bak |
| Els Munts - Roman Villa | lat | `moved-since-classification` | decided about 41.11655052794063, 1.2552670678094306, holds 41.135872, 1.385456 |
| Picken's Hole | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0015): The quoted 35,000 BP dates the faunal deposits (a hyena den), no |
| Yanaca | period_start | `field-unresolved` | The English Wikipedia article on Yanaca (Aymaraes Province, Apurímac) says that it is extremely difficult to know when t |
| Port Way | period_start | `field-unresolved` | No readable source dates the Port Way (Silchester to Old Sarum, Margary 4b). Wikipedia says only that the road is often  |
| Andle Stone | period_start | `field-unresolved` | English Wikipedia describes the Andle Stone only as a gritstone boulder with cup and ring marks and a memorial inscripti |
| Sydney Rock Engravings | lat | `coordinates-unresolved` | The entry is a regional group of roughly 2,000 Aboriginal engraving sites across the Sydney region (Ku-ring-gai Chase, S |
| Sydney Rock Engravings | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0001): The entry is a regional class of thousands of engravings that ca |
| Trebenna Antike Stadt | period_start | `field-unresolved` | No source dates the start of Trebenna and the sources disagree about its earliest phase: English Wikipedia and the Antal |
| Ishi no Hōden Megalith | period_start | `field-unresolved` | English Wikipedia calls the Ishi no Hoden 'of unknown age' and says the date it was carved, by whom and why remain unkno |
| Archaeological Site of La Ribera de Algaida | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0040): -4500 is the table's start of the Copper Age, but the site's own |
| Bone Cave, Tasmania | period_start | `moved-since-classification` | decided about -500, holds -27050 |
| Pajaral | period_start | `field-unresolved` | No independent source dates Pajaral's own start: English Wikipedia (and its es/it counterparts) only say that by the 7th |
| Corick | period_start | `field-unresolved` | The English Wikipedia article, Irish Megaliths (Derry page) and the Megalithic Portal pages for Corick Stone Circle (H77 |
| Ağbulaq Necropolis | lat | `coordinates-unresolved` | No page prints a point for the Ağbulaq necropolis: the English and Azerbaijani Wikipedia articles and the Wikidata item  |
| Ağbulaq Necropolis | period_start | `field-unresolved` | The English and Azerbaijani articles call it only an archaeological site 'of antiquity' (a broad class, not a date of th |
| Anta de Adrenunes | period_start | `field-unresolved` | No reliable source dates Anta de Adrenunes. English and Portuguese Wikipedia say no artefacts or burials were found and  |
| Cave of Bedmar | lat | `coordinates-unresolved` | No source prints a point for the Cueva de Bedmar: the English and Spanish Wikipedia articles carry no coordinates, Wikid |
| Moel Tŷ Uchaf | period_start | `moved-since-classification` | decided about -4000, holds -2300 |
| Heel Stone | period_start | `moved-since-classification` | decided about -4000, holds -3000 |
| Tumlehed Rock Painting | lat | `moved-since-classification` | decided about 57.733465010781245, 11.716677426446076, holds 57.731935, 11.740266 |
| Cerro Pátapo Ruins | period_start | `moved-since-classification` | decided about 1, holds 700 |
| Tempio Nuragico a Pozzo di Irru | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0005): The quote dates the frequentation of the whole Irru complex (nur |
| Stapeley Hill | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Runayoc | lat | `coordinates-unresolved` | No readable page prints a point for the Runayoc ruins (Huaytara, Huancavelica): the English article and Wikidata item Q2 |
| Runayoc | period_start | `field-unresolved` | The English article gives no date or period for Runayoc, and searches (Spanish and English, MINCETUR, Ministry of Cultur |
| Cras -  Round Cairn to North of | period_start | `moved-since-classification` | decided about -4000, holds -2300 |
| Tal-Barrani | period_start | `field-unresolved` | Tal-Barrani is an agricultural area (documented in the 16th and 17th centuries) that holds several separate burial remai |
| Nine Stones Close | period_start | `moved-since-classification` | decided about -4000, holds -2900 |
| Llanfechell | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0008): The quote names the 6th-century saint founder in a list of notab |
| Odessus | lat | `moved-since-classification` | decided about 43.216854323189835, 27.916709612096966, holds 43.200247, 27.91835 |
| Pilluchu | period_start | `field-unresolved` | No readable source dates Pilluchu (Pillucho, Vilcas Huaman, Ayacucho). Wikipedia in English gives only location and heig |
| Al-Rabba Roman and Byzantine Ruins | period_start | `field-unresolved` | The Princeton Encyclopedia of Classical Sites says Rabbathmoba/Areopolis was 'built on the site of the biblical town of  |
| Ixtutz | period_start | `moved-since-classification` | decided about 1, holds -400 |
| Nina Kiru | lat | `coordinates-unresolved` | Wikipedia and Wikidata (Q21044285, no P625) give no point; the Mincetur inventory record for the Sitio Arqueologico Nina |
| Nina Kiru | period_start | `moved-since-classification` | decided about -800, holds 1438 |
| Dokan-e-Davood | period_start | `moved-since-classification` | decided about -800, holds -400 |
| Quillarumi | period_start | `field-unresolved` | No readable source gives a date for the Quillarumi (Quilla Rumi) paintings: Wikipedia gives none, and the literature fou |
| Kosenivka | lat | `coordinates-unresolved` | English Wikipedia's Kosenivka article prints no coordinates, and the stored point (48.8313, 30.4319) is at the modern vi |
| Devil's Jumps, Treyford | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Broomfield Camp | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Wet Withens | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Dolno Gradište | period_start | `field-unresolved` | No readable source dates the start of Dolno Gradiste (Kocani). English and Macedonian Wikipedia (the latter files it as  |
| Trou de l'Abîme | period_start | `moved-since-classification` | decided about -500, holds -42550 |
| Tibradden Mountain | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Bejucal | lat | `coordinates-unresolved` | The only printed point for Bejucal is the Wikidata/English Wikipedia point 17.417, -89.667 (the French and Indonesian ar |
| Bejucal | period_start | `field-unresolved` | The sources disagree about the start: English Wikipedia dates the site to the second half of the 4th century AD (inscrip |
| Winsford, Somerset | lat | `coordinates-unresolved` | The stored point is the centre of Winsford village (Wikipedia and Wikidata give 51.0993, -3.5652 for the civil parish, 0 |
| Winsford, Somerset | period_start | `field-unresolved` | Wikipedia's Winsford article gives the village's Domesday entry (1085), 1219 and later dates and says the parish holds B |
| Intihuatana Archaeological Complex | period_start | `moved-since-classification` | decided about 43, holds 1438 |
| Nine Stones, Altarnun | period_start | `field-unresolved` | English Wikipedia on the Nine Stones (Altarnun stone circle, Bodmin Moor) gives no date or period, Cornwall's Bodmin Moo |
| Llamuqa | period_start | `field-unresolved` | Llamuqa (Llamocca/Llamoja, Cerro Apu Llamoja, 4,794 m, Huaynacotas, La Union, Arequipa) is described by English Wikipedi |
| Toledo, Spain | period_start | `field-unresolved` | No source I could read dates the start of the occupation of Toledo's own hill. The English article says only that Toledo |
| Haidara - Temple of Sun | lat | `coordinates-unresolved` | No readable page prints a point for the Haidara monument: LebanonUntravelled, Blog Baladi and L'Orient Today place it on |
| Baumann's Cave | period_start | `moved-since-classification` | decided about 1500, holds -3000000 |
| Kerbatch | period_start | `field-unresolved` | UNESCO's 3rd century BC to 16th century AD range (repeated in the French Wikipedia article on Kerbatch) is given for the |
| Gradište Archaeological Site, Iđoš | period_start | `moved-since-classification` | decided about -4000, holds -6000 |
| Dun Fiadhairt Broch | period_start | `moved-since-classification` | decided about 800, holds -800 |
| Ashdown Forest | period_start | `field-unresolved` | The entry is Ashdown Forest as a whole, which the English Wikipedia article 'Archaeology of Ashdown Forest' describes as |
| Boringdon Camp | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Cueva Antón | period_start | `moved-since-classification` | decided about 1, holds -300000 |
| La Chabola de la Hechicera | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0041): The quote's '5,000 years ago' is a round figure, but the peer-re |
| Highbury Hill, Clutton | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Somma Vesuviana | period_start | `field-unresolved` | The item is the town and comune of Somma Vesuviana. English Wikipedia gives its founding only through Strabo (a group of |
| Xerez Cromlech | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0007): The lead's 5th-or-4th-millennium hedge is contradicted inside th |
| Örenyeri | lat | `coordinates-unresolved` | The record's name Örenyeri is only the Turkish common noun for a ruin site and carries no source URL; no page, Wikidata  |
| Örenyeri | period_start | `field-unresolved` | No source identifies the site called Örenyeri, so none can date its start; the linked pages are about Göbekli Tepe, a di |
| Jubail Church | period_start | `field-unresolved` | The English Wikipedia article states that 'The date of the Jubail Church is contentious. Some sources place it in the fo |
| Blackdown Rings | period_start | `moved-since-classification` | decided about -4000, holds -800 |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s007-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s007 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
