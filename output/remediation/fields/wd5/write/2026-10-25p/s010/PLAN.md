# WD5 fields-wd5-2026-10-25p-s010: plan

Built 2026-10-25T07:59:26+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s010`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s010:<site>:<column>`.

| counter | value |
|---|---|
| sites | 92 |
| cells | 6 |
| sites_written | 3 |
| refused | 112 |
| cells:period_name | 3 |
| cells:period_start | 3 |
| refused:coordinates-unresolved | 21 |
| refused:country-changes | 1 |
| refused:field-unresolved | 53 |
| refused:moved-since-classification | 37 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Arzachena Archaeological Park | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd5-derive-period-name |
| Arzachena Archaeological Park | period_start | `-500` | `-5000` | wd5-replace |
| Las Labradas | period_name | `< 4500 BC` | `500 - 1000 AD` | wd5-derive-period-name |
| Las Labradas | period_start | `-10000` | `750` | wd5-replace |
| The Warbanks | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| The Warbanks | period_start | `-4000` | `-2500` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Cocoraque Butte Archaeological District | lat | `coordinates-unresolved` | No readable page prints the district's own point. The NRHP lists Cocoraque Butte Archaeological District (75000355) with |
| Cocoraque Butte Archaeological District | period_start | `field-unresolved` | English Wikipedia (and a bikepacking page that repeats it) gives the petroglyphs as '1150 to 2000 years old' with no her |
| Sollentuna Socken | lat | `coordinates-unresolved` | The record stands for Sollentuna socken, a former parish of about 49.5 km2 (English Wikipedia), not for one monument; th |
| Sollentuna Socken | period_start | `field-unresolved` | English Wikipedia only says that the parish holds Bronze Age cairns, around 60 burial sites and five hill forts from the |
| Sollentuna Socken | source_url | `field-unresolved` | The stored English article is about the administrative parish (socken), a region, not about one ancient site; no page ab |
| Double Arches Pit | period_start | `moved-since-classification` | decided about -500, holds 43 |
| Pollena Trocchia | period_start | `field-unresolved` | The item is the modern comune of Pollena Trocchia, made in 1811 from two villages. English Wikipedia gives their origin  |
| Belören Kalesi | period_start | `field-unresolved` | Kultur Envanteri gives the type only and no date. The only page that dates the castle (Miras Haritasi, a 5th to 1st cent |
| Kʼatepan | period_start | `moved-since-classification` | decided about 43, holds 950 |
| Crikvenica | lat | `moved-since-classification` | decided about 45.18352232373571, 14.700032182860244, holds 45.173733, 14.692356 |
| Blaškovina Archaeological Site | lat | `coordinates-unresolved` | The Blaškovina necropolis lies 'in the eastern part of the village of Visibaba, on a terrace above the Zapadna Morava' ( |
| Tombs of Malta | lat | `coordinates-unresolved` | The item is a list of prehistoric tombs scattered across the Maltese islands (Bingemma, Xemxija, Kercem, Xaghra and othe |
| Tombs of Malta | period_start | `field-unresolved` | The entry is a series of unrelated tombs from different periods; the only date the article gives is the generic word pre |
| Wade's Causeway | period_start | `field-unresolved` | Wikipedia says its origins, age and purpose have not been reliably established (excavated and dated Roman in the mid-20t |
| Fernacre | period_start | `field-unresolved` | English Wikipedia says only that the dating of the sites is uncertain and that Fernacre has been suggested to be Neolith |
| Witzna | lat | `coordinates-unresolved` | English and Spanish Wikipedia and Wikidata Q8028659 print no point for Witzna; the Archaeology magazine, Science Breaker |
| Witzna | period_start | `field-unresolved` | Wikipedia says only that significant occupancy is dated to the Classic period; the Archaeology magazine, Science Breaker |
| Bindon Hill | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Sigwells | period_start | `moved-since-classification` | decided about -4500, holds -2500 |
| Żejtun Roman Villa | period_start | `field-unresolved` | The sources give incompatible starts for a multi-period site: the University of Malta page and Wikipedia note only a roc |
| Farley Green, Surrey | period_start | `field-unresolved` | The readable pages only give an upper bound (Wikipedia: the Romano-Celtic temple was in use some time before the end of  |
| Llaqta Qulluy, Tayacaja | lat | `coordinates-unresolved` | Wikidata Q21044267 has no P625 and the English article prints no point, only the 3,960 m height and the community Llaqta |
| Arzachena Archaeological Park | lat | `coordinates-unresolved` | Italia.it describes the park as a group of eight sites (Li Muri, Albucciu, Moru, Malchittu, Li Lolghi, La Prisgiona, Cod |
| Rodadero Slides | lat | `coordinates-unresolved` | No readable page prints a point for the Rodadero (Suchuna) outcrop itself: the site has no Wikidata item or Wikipedia ar |
| Gurnard's Head | period_start | `moved-since-classification` | decided about -800, holds -200 |
| Caisteal Grugaig | period_start | `moved-since-classification` | decided about -2000, holds -800 |
| Carrock Fell | period_start | `field-unresolved` | English Wikipedia (about the fell) calls the summit enclosure an Iron Age hill fort 'believed to have been built by the  |
| Cova Negra | period_start | `moved-since-classification` | decided about 1, holds -4501 |
| Flevum | lat | `country-changes` | the new point lies in ['Netherlands'], the site says Germany |
| Tomb of Darius II | period_start | `moved-since-classification` | decided about -550, holds -423 |
| Lupanar of Pompeii | period_start | `field-unresolved` | The English, German, Italian and French Wikipedia articles, the Pompeii Archaeological Park page and Pompeii in Pictures |
| Carreg Coetan Arthur | period_start | `moved-since-classification` | decided about -3000, holds -3650 |
| Vindija Cave | period_start | `field-unresolved` | No readable page dates the start of Vindija Cave's occupation. English Wikipedia says Neanderthals used it 40,000 years  |
| Khichuqaqa | lat | `coordinates-unresolved` | English Wikipedia and Wikidata print no point for Khichuqaqa (K'echuqaqa); Hostnig's descriptions (rupestreweb.info, TRA |
| Khichuqaqa | period_start | `moved-since-classification` | decided about -10000, holds 1438 |
| Misraħ Għar il-Kbir | period_start | `field-unresolved` | Sources disagree and none gives a firm start: English Wikipedia says the ruts date no later than c.700 BC with several e |
| Misraħ Għar il-Kbir | site_type | `field-unresolved` | The readable sources (English and German Wikipedia, Spoken Past, Ancient Origins) call the site a network of cart ruts o |
| Via Militaris | lat | `coordinates-unresolved` | The Via Militaris is a 924 km road from Singidunum to Constantinople; neither its Wikidata item Q1231059 nor any Wikiped |
| Ardgroom | period_start | `field-unresolved` | Monumental Ireland's page for the Ardgroom Stone Circle (Ardgroom Outward, Co. Cork, SMR CO102-006001) and Curious Irela |
| Kastros | lat | `moved-since-classification` | decided about 35.53869568390137, 34.27675771835874, holds 35.69442, 34.5859 |
| Salina Catacombs | period_start | `field-unresolved` | No readable source dates the start of these catacombs: English Wikipedia speaks only of the community that lived there i |
| Otišić | period_start | `field-unresolved` | The English, Croatian and Serbian Wikipedia articles only say the village area has finds 'from the Stone Age and Roman E |
| Khao Sai On Archaeological Site | lat | `moved-since-classification` | decided about 14.800804534275574, 100.651292336184, holds 14.784464, 100.729939 |
| Khao Sai On Archaeological Site | period_start | `moved-since-classification` | decided about -1000, holds -300 |
| Ħal Resqun Catacombs | period_start | `field-unresolved` | The Archaeological Society Malta article (Camilleri and Gingell Littlejohn) and English Wikipedia both say that Zammit's |
| The Warbanks | lat | `moved-since-classification` | decided about 52.13151063405994, 0.7184658119142862, holds 52.146994, 0.75499 |
| Surčin | period_start | `field-unresolved` | No source dates the start of Surcin. English Wikipedia only lists that settlements existed in the Stone Age, Neolithic,  |
| Karakabaklı | period_start | `field-unresolved` | The sources disagree about when Karakabaklı began and none is an excavation or register record that settles it: the Engl |
| Urpish | lat | `moved-since-classification` | decided about -9.283089759415377, -76.73330111787394, holds -9.276667, -76.725581 |
| Urpish | period_start | `field-unresolved` | The only dating found is a period word with no year: the Peruvian tourism inventory description of the Sitio Arqueologic |
| Glantane East | period_start | `field-unresolved` | English Wikipedia, irishmegaliths.org.uk (Cork) and megalithics.com describe the wedge tomb, two stone circles and align |
| Mawk'allaqta, Espinar | period_start | `field-unresolved` | The English article gives no date. The Mincetur-derived page on turismoperuano.com (Zona Arqueologica de Maukallaqta, Cu |
| Stone of the Guanches | lat | `coordinates-unresolved` | Neither the English, Spanish nor French Wikipedia article on the Stone of the Guanches prints coordinates, and Wikidata  |
| Stone of the Guanches | period_start | `field-unresolved` | No source dates the engraved stone itself. Wikipedia only calls it a stone associated with the mummification practices o |
| Road Castle | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Nakovanj | period_start | `moved-since-classification` | decided about -1500, holds -6000 |
| Yellowberries Copse | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0004): The article gives only 'late Bronze Age or early Iron Age' (an u |
| Dumat al-Jandal | period_start | `field-unresolved` | The only source for a 10th century BC start is the English Wikipedia article (and its French copy), which is not indepen |
| Dighton Rock | period_start | `field-unresolved` | English Wikipedia calls the carvings 'of ancient and uncertain origin' and gives only the first record (Danforth's 1680  |
| Risovača Cave | lat | `moved-since-classification` | decided about 44.30014586334488, 20.56643181215441, holds 44.303308, 20.581952 |
| Risovača Cave | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0039): The value -300000 is the start of the whole Middle Palaeolithic, |
| Abri de la Madeleine | period_start | `moved-since-classification` | decided about -500, holds -50000 |
| Tikra | lat | `coordinates-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0032): The Spanish Wikipedia point is not the site: it prints the site  |
| Tikra | period_start | `moved-since-classification` | decided about -800, holds 1100 |
| Cave Sanctuaries of the Acropolis of Athens | period_start | `field-unresolved` | The site is a group of several cave shrines (Apollo, Zeus, Pan, Aphrodite and Eros, Aglauros and others) on the Acropoli |
| Orchomenus, Arcadia | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0024): The quote only says Orchomenus originated as a prehistoric settl |
| Tomb of the Scene | period_start | `field-unresolved` | No source names a 'Tomb of the Scene'; the name is probably the English rendering of the Persian gurdakhmeh-ye Sahneh (S |
| Nyaung-gan | lat | `moved-since-classification` | decided about 21.613916605662713, 95.40172617853912, holds 22.4, 95.066667 |
| Louisenlund, Bornholm | period_start | `field-unresolved` | The Danish Nature Agency's page for Louisenlund (udinaturen.dk) states 'Der har aldrig været foretaget større undersøgel |
| Xyniae | period_start | `field-unresolved` | No readable page dates the founding or first occupation of Xyniae: the English, French, Spanish and Bulgarian Wikipedia  |
| Pyramids of Queens | lat | `coordinates-unresolved` | The entry 'Pyramids of Queens' names no king: Khufu's queens' pyramids (G1-a to G1-c, Wikipedia points about 29.978, 31. |
| Pyramids of Queens | period_start | `moved-since-classification` | decided about 1000, holds -2613 |
| Craigs Dolmen | period_start | `moved-since-classification` | decided about -800, holds -4000 |
| New Guinea II Cave | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0002): The article's own dating line gives 21,900 +900/-800 BP for the  |
| Carnedd y Saeson and Neighbouring Cairns North-West of Foel Dduarth | period_start | `field-unresolved` | Coflein (NPRN 93599) and the Wikipedia list of scheduled monuments give this cairnfield only the period 'Prehistoric', a |
| Klaraki | lat | `coordinates-unresolved` | No readable source prints a point for the Klaraki hill: Wikipedia and Wikidata (Q85774673, enwiki sitelink only, no P625 |
| Klaraki | period_start | `field-unresolved` | Wikipedia's Klaraki article gives no date; the Sparta city wall is dated in general to the late 4th-3rd century BC, but  |
| Chimei Lithic Workshops | lat | `coordinates-unresolved` | No readable page prints a point for the Chimei lithic workshops: the English and Chinese Wikipedia articles and Wikidata |
| Chimei Lithic Workshops | period_start | `moved-since-classification` | decided about -500, holds -2550 |
| Wiraqucha Pirqa | lat | `moved-since-classification` | decided about -13.530460072481059, -75.34557854664526, holds -13.543305, -75.379422 |
| Wiraqucha Pirqa | period_start | `field-unresolved` | The English Wikipedia article and huancavelica.com call Wiraqucha Pirqa only a pre-Hispanic walled citadel or town (14 t |
| Roman Aqueducts of Toledo | lat | `coordinates-unresolved` | The Roman aqueducts of Toledo are a water system from the Alcantarilla dam at Mazarambroz to the Tagus gorge at Toledo,  |
| Kunturmarka, Ayacucho | lat | `coordinates-unresolved` | English Wikipedia and its Wikidata item print no point. The Alteritas 2021 study of Condormarca (AA.HH. Condormarca, Hua |
| Enclosed Hut Circle Settlement - South-East of Bod Silin | period_start | `moved-since-classification` | decided about -500, holds -800 |
| Gartnanoul | period_start | `field-unresolved` | Read the English and German Wikipedia articles, Heritage Ireland, Megalithic Ireland and irishmegaliths.org.uk: none giv |
| Simanya Cave | period_start | `moved-since-classification` | decided about 1, holds -47050 |
| Lesingey Round | period_start | `field-unresolved` | Wikipedia dates only rounds as a class (late Iron Age to early post-Roman), not this site; the Gatehouse Gazetteer quote |
| Zafarraya | period_start | `moved-since-classification` | decided about -500, holds -48050 |
| Saba in Ancient Sites | lat | `coordinates-unresolved` | No source names an ancient site 'Saba' at the stored point near Kaş (Bayındır, Antalya). The ancient places near it are  |
| Saba in Ancient Sites | period_start | `field-unresolved` | No source about an ancient site 'Saba' at this point was found; the attached pages are about Hierapolis, a different sit |
| Saba in Ancient Sites | source_url | `field-unresolved` | No page about a site called Saba at the stored point near Kaş was found; the attached pages concern Hierapolis at Pamukk |
| Kukuli, Arequipa | lat | `moved-since-classification` | decided about -15.776224465203656, -73.93380000427342, holds -15.855889, -73.311403 |
| El Mirón Cave | period_start | `field-unresolved` | Spanish and French Wikipedia say El Mirón holds remains continuously from the present back to the Mousterian, and the es |
| Federsee | period_start | `moved-since-classification` | decided about -500, holds -11000 |
| Marayniyoq | lat | `moved-since-classification` | decided about -13.056959603986634, -74.21613563131027, holds -13.01, -74.205 |
| A Figa | lat | `coordinates-unresolved` | Corsican Wikipedia has only a one-sentence stub placing A Figa in the commune of Sartene and prints no point; the fr.wik |
| A Figa | period_start | `field-unresolved` | No page found dates A Figa: the Corsican stub says only that it is an archaeological site in Sartene. English Wikipedia' |
| Hadsar Fort | period_start | `field-unresolved` | English Wikipedia says only 'it is believed that this fort was built in the Satavahana Era' and German Wikipedia that th |
| Mut Castle | period_start | `field-unresolved` | The Turkish Ministry of Culture's Kulturportali says 'Mut Kalesi'nin ilk insa tarihi bilinmemektedir' (the first constru |
| Calcaria | period_start | `field-unresolved` | English Wikipedia says only that the Romans founded the settlement and that its nature is uncertain; roman-britain.co.uk |
| Northern Avenue Petroglyph Site | lat | `coordinates-unresolved` | English Wikipedia states that the National Register does not disclose the location and that a local petroglyph club plac |
| Northern Avenue Petroglyph Site | period_start | `field-unresolved` | The only register record, NPGallery NRIS 96001054, lists periods of significance as a run of contiguous generic bins (10 |
| Nitovikla | lat | `moved-since-classification` | decided about 35.49431516999355, 34.28308778288577, holds 35.487183, 34.29055 |
| Roman Aqueduct of Paris | lat | `moved-since-classification` | decided about 48.857049131693, 2.3523636316693914, holds 48.799444, 2.332778 |
| Foel Chwern | period_start | `moved-since-classification` | decided about -4000, holds -2300 |
| Roman Emperors Route | lat | `coordinates-unresolved` | The Roman Emperors Route (Itinerarium Romanum Serbiae) is, per English Wikipedia, 'a tourism and archaeology project in  |
| Roman Emperors Route | period_start | `field-unresolved` | The Roman Emperors Route is a present-day tourism and archaeology project, not an ancient site with a construction or fi |
| Kanichi | period_start | `field-unresolved` | Wikipedia says only that the complex was influenced by the Wari and Chanka cultures, with no date. MINCETUR's inventory  |
| Pumaq Hirka | period_start | `field-unresolved` | No quotable date. The Spanish Wikipedia article on the same site (Castillo Pumaj Jirca) gives its epoch as 'Intermedio T |
| Cardiccia | period_start | `field-unresolved` | The sources disagree on when Cardiccia (Sartene) starts. Wikipedia's Prehistory of Corsica lists it among Middle Neolith |
| Leskernick Hill | period_start | `moved-since-classification` | decided about -4500, holds -2500 |
| Five Marys | period_start | `moved-since-classification` | decided about -4000, holds -2500 |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s010-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s010 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
