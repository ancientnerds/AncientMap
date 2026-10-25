# WD5 fields-wd5-2026-10-25p-s009: plan

Built 2026-10-25T07:58:25+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s009`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s009:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 12 |
| sites_written | 6 |
| refused | 113 |
| cells:period_name | 6 |
| cells:period_start | 6 |
| refused:coordinates-unresolved | 25 |
| refused:field-unresolved | 54 |
| refused:moved-since-classification | 34 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Amazmaz | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd5-derive-period-name |
| Amazmaz | period_start | `-10000` | `-4000` | wd5-replace |
| Grotte de Lombrives | period_name | `< 4500 BC` | `4500 - 3000 BC` | wd5-derive-period-name |
| Grotte de Lombrives | period_start | `-4501` | `-4000` | wd5-replace |
| Metropolis Antik Kenti | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Metropolis Antik Kenti | period_start | `-1400` | `-3000` | wd5-replace |
| Phu Phra Bat Historical Park | period_name | `< 4500 BC` | `1500 - 500 BC` | wd5-derive-period-name |
| Phu Phra Bat Historical Park | period_start | `-10000` | `-1050` | wd5-replace |
| Ta' Kaċċatura | period_name | `1 - 500 AD` | `500 BC - 1 AD` | wd5-derive-period-name |
| Ta' Kaċċatura | period_start | `43` | `-200` | wd5-replace |
| The Ancient Tower of Thimonia | period_name | `500 - 1000 AD` | `1500 - 500 BC` | wd5-derive-period-name |
| The Ancient Tower of Thimonia | period_start | `800` | `-600` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Palazzo a Mare | period_start | `field-unresolved` | The stored 1000 (medieval) is wrong: every source calls Palazzo a Mare a Roman imperial villa. But no quotable page give |
| Gaya Tumuli | lat | `coordinates-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0007): The quote prints 35.237264, 128.873725 (unreferenced on Wikidata |
| Gran Pajatén | lat | `moved-since-classification` | decided about -7.648851125141207, -77.41795708905653, holds -7.654777, -77.401944 |
| Xtojil Cenote | period_start | `field-unresolved` | No readable page gives a start for Xtojil Cenote itself. Yucatan Magazine (on Xtogil, named by INAH) says only that the  |
| Lycia Rock Tombs | lat | `coordinates-unresolved` | 'Lycia Rock Tombs' names a class of monuments, not one site: the stored page (explorelycia.com) says the rock tombs lie  |
| Intipanawin | lat | `coordinates-unresolved` | The only printed point (English Wikipedia and Wikidata, -10.23636, -77.07311) belongs to the mountain item and lies at P |
| Intipanawin | period_start | `field-unresolved` | English Wikipedia describes the paintings (a sun's eye and llamas) without a date, and the Wikidata dates belong to the  |
| Jabal al-Baidain | lat | `coordinates-unresolved` | The English and Arabic Wikipedia articles (and their Wikidata item, which has no P625) place Jabal al-Baidain 13 km sout |
| Jabal al-Baidain | period_start | `field-unresolved` | The English and Arabic Wikipedia articles mention traces of ancient settlements, animal drawings and Thamudic (Badia-Tha |
| Castro de Porto de Baixo | lat | `moved-since-classification` | decided about 42.550165950738034, -9.033440591640034, holds 42.540331, -9.033867 |
| Tipón | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0033): The MINCETUR quote only says that history holds Tipon to have be |
| Allahdino | lat | `coordinates-unresolved` | English Wikipedia (Coord missing), the French, Tamil, Belarusian, Uzbek and Arabic articles and Wikidata Q4730348 carry  |
| Allahdino | period_start | `field-unresolved` | Wikipedia says only that the settlement was abandoned by c. 2000 BCE (an end date); Penn Museum's article dates the Hara |
| Cohaw | period_start | `moved-since-classification` | decided about -800, holds -4000 |
| Nebstone | period_start | `moved-since-classification` | decided about -10000, holds -2500 |
| Alcantarilla Dam | period_start | `moved-since-classification` | decided about -200, holds 1 |
| Cave of Gabrovnica | period_start | `field-unresolved` | The only dating of the Gabrovnica cave paintings is the museum-derived text, which English Wikipedia, Serbian Wikipedia, |
| Ingá Stone | period_start | `field-unresolved` | No reputable readable source dates the Inga Stone engravings. English and Portuguese Wikipedia give no date (English say |
| Neos Panteleimonas | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0005): Greek Wikipedia's article on Old Panteleimonas says the inhabita |
| Raw Dykes | period_start | `moved-since-classification` | decided about -4000, holds 43 |
| Conjunto Arqueologico de Ñustahispana | period_start | `moved-since-classification` | decided about -10000, holds 1438 |
| Museo Regional de Campeche | lat | `coordinates-unresolved` | The stored point (19.8249, -90.5688) is the Fuerte de San Miguel, whose Spanish Wikipedia article prints 19.8247151, -90 |
| Museo Regional de Campeche | period_start | `field-unresolved` | No source dates a 'Museo Regional de Campeche'. The only dated page, the stored travelbymexico entry, says the San Migue |
| Roman Villa of Vale do Mouro | site_type | `moved-since-classification` | decided about 'Settlement', holds 'Residence/villa/farmhouse' |
| Manika, Greece | lat | `moved-since-classification` | decided about 38.500193090465196, 23.999967810009217, holds 38.498, 23.626 |
| Skopje Aqueduct | period_start | `field-unresolved` | The sources disagree and none settles the start. English Wikipedia says the date is unclear and gives three theories (Ro |
| Flowerdown Barrows | period_start | `moved-since-classification` | decided about -4000, holds -2050 |
| Alyscamps | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0020): The quote only calls the Alyscamps Roman, so the table year 43 f |
| Wari Willka | period_start | `field-unresolved` | The sources disagree and none dates the start of the site itself. The MINCETUR inventory record (ficha 714, Santuario Ar |
| Arroyo el Concho | lat | `coordinates-unresolved` | The only page that describes Arroyo el Concho is the Megalithic Portal entry (sid=33419), which answers HTTP 403 to plai |
| Arroyo el Concho | period_start | `field-unresolved` | No readable page dates Arroyo el Concho: the Megalithic Portal entry is refused with HTTP 403, and neither Archaeology M |
| Kokkinokremmos | lat | `moved-since-classification` | decided about 34.91797895576575, 33.63324608667987, holds 34.9905, 33.7142 |
| Huaca Casa Rosada | period_start | `field-unresolved` | No source gives a year or a clean period for the start of Huaca Casa Rosada. The English Wikipedia article says its occu |
| Pheia, Elis | period_start | `moved-since-classification` | decided about -1500, holds -3200 |
| Overstone Anglo-Saxon Cemetery | lat | `coordinates-unresolved` | No page I could read prints a decimal or degree point for the Overstone Leys cemetery: the English Wikipedia article and |
| Overstone Anglo-Saxon Cemetery | period_start | `moved-since-classification` | decided about -800, holds 450 |
| Čurug | period_start | `field-unresolved` | No readable source dates the start of Curug as a site. Serbian Wikipedia says excavations around the village show people |
| Aboriginal Sites of New South Wales | lat | `coordinates-unresolved` | The item is a class of places, not one place: English Wikipedia opens 'Aboriginal sites of New South Wales consist of a  |
| Grotte de Gabillou | period_start | `moved-since-classification` | decided about -500, holds -3000000 |
| Menhirs of Sardinia | lat | `coordinates-unresolved` | The entry is the Brentoni menhirs near Villa Sant'Antonio as the stored source_url and point suggest, but the only page  |
| Menhirs of Sardinia | period_start | `field-unresolved` | The sources on Sardinian menhirs (indaginiemisteri.it) date the appearance of menhirs on the island to the second half o |
| La Chaire a Calvin | period_start | `moved-since-classification` | decided about -500, holds -13050 |
| Millka | period_start | `field-unresolved` | Only the English Wikipedia article (which cites Meddens and Vivanco 2002-2005, a PDF I could not read: Academia.edu answ |
| Rock Carvings in Central Norway | lat | `coordinates-unresolved` | The entry is the region of Central Norway (Trøndelag and parts of Nordland and Møre og Romsdal) with about 300 rock-art  |
| Rock Carvings in Central Norway | period_start | `field-unresolved` | The entry is a region of about 300 sites that English Wikipedia dates to two traditions, Stone Age (in Norway 8000-1800  |
| Lappa, Crete | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0004): ToposText's 'Hellenistic to Late Antique polis' is a classificat |
| Roman Ruins of Creiro | period_start | `moved-since-classification` | decided about -100, holds 51 |
| Ebbsfleet Valley | period_start | `field-unresolved` | Ebbsfleet Valley is a modern new town and redevelopment area; Wikipedia only lists finds of various ages in the wider ri |
| Paso del Macho | lat | `coordinates-unresolved` | Paso del Macho in the Bolonchen District of the eastern Puuc, Yucatan, is described by the Institute of Maya Studies tal |
| Paso del Macho | period_start | `moved-since-classification` | decided about -3000, holds -900 |
| Pozzuoli | lat | `moved-since-classification` | decided about 40.84455799856999, 14.093408398482643, holds 40.822643, 14.121911 |
| Temple of Dedun | period_start | `field-unresolved` | The site is the chapel of Dedwen at New Kalabsha (formerly inside the enclosure wall of the Kalabsha temple precinct). N |
| Green Gully Archaeological Site | period_start | `field-unresolved` | The site's dating exists but in no form the quote check reads. English Wikipedia says 'the site is dated to about 6500 y |
| Trevelgue Head | period_start | `moved-since-classification` | decided about -800, holds -10000 |
| Falkner's Circle | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0012): The quote dates the erection to the late third or early second m |
| Nakrang Tombs | lat | `coordinates-unresolved` | No source prints a point for the Nakrang (Lelang) tomb field. Korean Wikipedia (the stored source) gives none; English W |
| Nakrang Tombs | period_start | `field-unresolved` | No source dates the start of the tomb field as a whole. The Lelang Commandery was set up in 108 BCE, and Korean scholars |
| Vasculaghju | period_start | `field-unresolved` | The necropolis of Vasculaghju (Sotta, Corse-du-Sud: cists, dolmens, menhirs) has no readable page that dates it itself.  |
| Dinies Camp | period_start | `field-unresolved` | The article on Dinies Camp (Downhead, Somerset) calls it a univallate Iron Age hill fort enclosure, but its infobox says |
| Kaya mezarları | lat | `coordinates-unresolved` | 'Kaya mezarları' is a generic label (rock-cut tombs) with no Wikidata item or stored page; the Kultur Envanteri has many |
| Kaya mezarları | period_start | `field-unresolved` | The entry names no particular site and I found no page about rock tombs at the stored point, so nothing dates it; the st |
| Kaya mezarları | source_url | `field-unresolved` | No page is about these particular rock tombs: the name is generic and the linked pages describe rock tombs elsewhere (Ma |
| Castle Dykes Henge | period_start | `moved-since-classification` | decided about -3000, holds -800 |
| The Goatstones | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Porlock Stone Circle | period_start | `field-unresolved` | The Wikipedia article states that no evidence has been found that allows absolute dating of the monument's construction, |
| Pannonian Limes | lat | `coordinates-unresolved` | The Pannonian Limes is a roughly 420 km frontier line from Klosterneuburg to Singidunum. Its Wikidata item (Q471153) has |
| Pannonian Limes | period_start | `field-unresolved` | The sources disagree on when the Pannonian Limes began, so no start year can be quoted. The leads of English and German  |
| Tarnowskie Góry | period_start | `moved-since-classification` | decided about 1490, holds 1526 |
| The Poind and his Man | period_start | `moved-since-classification` | decided about -4000, holds -2900 |
| Warawtampu | site_type | `moved-since-classification` | decided about 'Archaeological site', holds 'City/town/settlement' |
| Ex voto of the Lacaedemonians | lat | `coordinates-unresolved` | Wikidata Q24913811 and the English and Greek Wikipedia articles on the Ex voto of the Lacaedemonians carry no coordinate |
| Ponte de Gimonde | period_start | `moved-since-classification` | decided about -27, holds 43 |
| Paracas History Museum | period_start | `field-unresolved` | The only source found that gives the museum's creation (11 December 2009, a museum directory at arqueologiadelperu.com)  |
| Verziau of Gargantua | period_start | `field-unresolved` | The menhir of Bois-les-Pargny (Aisne) is called Neolithic only in French: the Ministry of Culture's Merimee record PA001 |
| Lungkeng | lat | `coordinates-unresolved` | No readable page prints a point for the Lungkeng site on the Oluanpi peninsula: the English and Chinese Wikipedia articl |
| Lungkeng | period_start | `field-unresolved` | no counted answer in 3 rounds: quote not found: https://en.wikipedia.org/wiki/Lungkeng; quote not found: https://en.wiki |
| Post Track | lat | `moved-since-classification` | decided about 51.1959524781613, -2.960035675804092, holds 51.162434, -2.825022 |
| Waman Pirqa | lat | `coordinates-unresolved` | No page prints a point for the archaeological site Waman Pirqa: the English article (Lucanas Province, Carmen Salcedo Di |
| Pharaonic Tayma Inscription | lat | `coordinates-unresolved` | No readable page prints a point for the inscription itself: the English article and Wikidata give none and place it only |
| Stravomyti Cave | period_start | `moved-since-classification` | decided about -3000, holds -4000 |
| K'ipakhara | lat | `coordinates-unresolved` | English Wikipedia places K'ipakhara (Quepacara) south-east of Llata near the village of Milpo, Huamalies, Huanuco, but p |
| K'ipakhara | period_start | `field-unresolved` | Wikipedia says only that it is an archaeological site at about 3,600 m; the archived MINCETUR sheet it cites could not b |
| Chukimarka | period_start | `field-unresolved` | Chukimarka has no Wikipedia or Wikidata entry. The pages that name it (Mapcarta/OpenStreetMap, AllTrails and Wikiloc tra |
| Arbury Hill | period_start | `field-unresolved` | English Wikipedia says of the Iron Age fort on Arbury Hill that 'its date and origin are disputed'; the Northamptonshire |
| Mirq'imarka | lat | `coordinates-unresolved` | Wikipedia and Wikidata print no point; the Mincetur inventory sheet for the Sitio Arqueologico de Merkemarka (cod 5031,  |
| Castellane | period_start | `field-unresolved` | Castellane is a commune whose town stands at the foot of the Roc. English Wikipedia says only that Neolithic nomads pass |
| Aveline's Hole | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0007): The quote dates the Early Mesolithic cemetery use (around 8,300  |
| Uley | period_start | `field-unresolved` | The entry is the village and parish of Uley, Gloucestershire. Wikipedia, Visit Gloucestershire and the Uley Parish Counc |
| Roca dels Bous - Archaeological Site | period_start | `moved-since-classification` | decided about -500, holds -48050 |
| Amazmaz | lat | `coordinates-unresolved` | Every printed point (en/Wikidata 19.71667, -13.43333; Swedish 19.7233, -13.4325; French 19 07 N 13 41 W) is a point of t |
| La Grotte des Fées | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0020): The quote dates the Châtelperronian culture named after the cave |
| Ancient Lilaia | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0004): Both quotes date the 'area' or 'broader region' of Lilaea to the |
| Karpasia - Town | lat | `moved-since-classification` | decided about 35.59664186874294, 34.37808778289012, holds 35.62862, 34.37242 |
| Tirefour Castle | period_start | `moved-since-classification` | decided about 800, holds -800 |
| Tischofer Cave | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0001): The Wikipedias' 27,000-28,000 years for the bone points is an ol |
| Multan Fort | period_start | `field-unresolved` | The sources disagree and none gives a reliable start: English Wikipedia says only that the fort's walls were built by Mu |
| Madjedbebe | period_start | `moved-since-classification` | decided about -500, holds -63050 |
| Spy Cave | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0003): Both quotes date the Neanderthal fossils of 1886 (Spy 1 and 2),  |
| Navalia | lat | `coordinates-unresolved` | Navalia is known only as a name in Ptolemy's Geographia and its location is disputed: English/Dutch Wikipedia say it was |
| Navalia | period_start | `field-unresolved` | The only datable thing is that Ptolemy's Geographia (2nd century AD) mentions the name; that dates the mention, not the  |
| Grim's Ditch, Harrow | period_start | `moved-since-classification` | decided about -4000, holds 1 |
| The Ancient Tower of Thimonia | lat | `coordinates-unresolved` | The tower has no Wikipedia article or Wikidata item (the Wikidata item Thymonia, Q21406532, is the settlement). whichgre |
| Nysa Bridge | period_start | `field-unresolved` | English and German Wikipedia (and Grewe/Ozis 1994 behind them) date the Nysa Bridge only to 'late imperial times' from t |
| Chew Green | period_start | `moved-since-classification` | decided about -800, holds 43 |
| La Florida (Zacatecas) Shaft Tomb | lat | `coordinates-unresolved` | No readable page prints a point for this tomb. The INAH salvage excavation (reported by artdaily.cc) places it only unde |
| La Florida (Zacatecas) Shaft Tomb | period_start | `field-unresolved` | The only dating of this tomb is a reprint of an INAH release on artdaily.cc (served with an expired certificate): the to |
| Sallachy Broch | period_start | `field-unresolved` | The German Wikipedia article on the Broch von Sallachy (the stored source_url) describes the structure (outer diameter 1 |
| Prassa | period_start | `moved-since-classification` | decided about -4500, holds -2100 |
| Great and Little Kimble cum Marsh | period_start | `field-unresolved` | The stored site is the parish of Great and Little Kimble cum Marsh. Wikipedia dates only separate features in it (the Pu |
| Temple of Proserpina | period_start | `field-unresolved` | English Wikipedia says the date of construction is unknown; the Chrestion inscription records only a restoration under A |
| West Woods | period_start | `field-unresolved` | The entry is West Woods, a wood (Wikidata: part of the Marlborough Woodlands). Wikipedia says only that it has been visi |
| Rock Carvings at Åsli | period_start | `field-unresolved` | The Riksantikvaren-derived list of cultural monuments in Balsfjord files Åsli (Vasshalsen) only under 'Steinalder' (Ston |
| Mitrou | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0024): The Spanish Wikipedia 'about 2400 BC' is a stated occupation spa |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s009-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s009 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
