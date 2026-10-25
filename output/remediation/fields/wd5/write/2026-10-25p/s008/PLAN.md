# WD5 fields-wd5-2026-10-25p-s008: plan

Built 2026-10-25T07:57:30+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s008`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s008:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 10 |
| sites_written | 5 |
| refused | 106 |
| cells:period_name | 5 |
| cells:period_start | 5 |
| refused:coordinates-unresolved | 17 |
| refused:field-unresolved | 54 |
| refused:moved-since-classification | 35 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Derbyshire Portway | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Derbyshire Portway | period_start | `-4500` | `-2500` | wd5-replace |
| Jordbro Grave Field | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd5-derive-period-name |
| Jordbro Grave Field | period_start | `-800` | `-500` | wd5-replace |
| Osiris Shaft | period_name | `1500 - 500 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Osiris Shaft | period_start | `-800` | `-2686` | wd5-replace |
| Swinside | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Swinside | period_start | `-4000` | `-2900` | wd5-replace |
| Wooston Castle | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd5-derive-period-name |
| Wooston Castle | period_start | `-800` | `-200` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Snowden Crags | period_start | `field-unresolved` | English Wikipedia calls Snowden Crags only 'prehistoric', and the Northern Antiquarian pages it cites (Snowden Crags Cir |
| Derbyshire Portway | lat | `coordinates-unresolved` | The Derbyshire Portway is a trackway of over 40 miles from Mam Tor to the Hemlock Stone; neither its English Wikipedia a |
| Schanzenkopf - Spessart | period_start | `field-unresolved` | No source gives a year, and the sources disagree on the age of the Schanzenkopf ring wall near Alzenau-Wasserlos: Englis |
| Waqrapukara | period_start | `field-unresolved` | No reliable source dates the foundation of Waqrapukara. BBC Travel quotes archaeologist Oscar Montufar that Canchis cera |
| Ahuila Gencha Machay | period_start | `field-unresolved` | English Wikipedia gives no date. The MINCETUR-derived Turismo Peruano record says only that the two painted scenes date  |
| Rock Carvings at Eidefoss | period_start | `field-unresolved` | The sources disagree and none dates the two moose carvings of Eidefoss (Fossen, Nord-Fron) themselves: the Norwegian Wik |
| Dulan Site | period_start | `moved-since-classification` | decided about -3000, holds -1050 |
| Thibilis | period_start | `field-unresolved` | No readable source dates the start of Thibilis. English Wikipedia calls it 'a Roman and Byzantine era town' and dates on |
| Na Nova | period_start | `moved-since-classification` | decided about -3000, holds -800 |
| Carrigagulla | period_start | `field-unresolved` | The English Wikipedia article on Carrigagulla (megalithic complex 2.9 km north-east of Ballinagree, Co. Cork: an axial s |
| Pant-y-Saer Burial Chamber | period_start | `moved-since-classification` | decided about -3000, holds -3500 |
| Niederstotzingen | period_start | `field-unresolved` | The site is the town of Niederstotzingen. English and German Wikipedia date only other things: ivory carvings dated to 3 |
| Halos, Delphi | period_start | `field-unresolved` | English, Italian and Greek Wikipedia and the Delphi marker on hmdb.org describe the Halos (a round open area for the Sep |
| Kocherzhyntsi | lat | `coordinates-unresolved` | The stored point (48.6966, 30.1358) matches the centre of the village Kocherzhyntsi (uk.wikipedia village point 48.69556 |
| Nether Heyford | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0003): The site is the village and civil parish of Nether Heyford, whos |
| Titiqaqa, Cusco | lat | `coordinates-unresolved` | Titiqaqa (Teteqaqa, Teteq'aq'a), the archaeological site of Cusco District in the north-east of the city (listed by the  |
| Vottovaara | period_start | `field-unresolved` | The English and Russian Wikipedia articles on Vottovaara give no date for the stone groups: Shakhnovich and Manyukhin re |
| Puqin Kancha | lat | `coordinates-unresolved` | The English Wikipedia article and the Wikidata item (Q18345872) carry no coordinate, the Commons category carries none,  |
| Rillaton Barrow | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Lang Rongrien Rock Shelter | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0008): The excavator's own paper (Anderson 1997, Geoarchaeology 12) dat |
| Glassonby | period_start | `field-unresolved` | The stored site is the village and civil parish of Glassonby, whose own history in Wikipedia is medieval and later; the  |
| Stockdorf | period_start | `field-unresolved` | Stockdorf is a village (district of Gauting). The only ancient datings on any page concern a barrow cemetery in the Ange |
| El Porvenir | period_start | `field-unresolved` | English Wikipedia on El Porvenir (Maya site), read in full, gives no date or period at all (it only calls it a ruined ci |
| Kutikina Cave | period_start | `moved-since-classification` | decided about -500, holds -18050 |
| Pendeen Vau | period_start | `moved-since-classification` | decided about -500, holds -800 |
| Eretria, Thessaly | period_start | `moved-since-classification` | decided about -3000, holds -750 |
| Cranmore Castle | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Devil's Lair | period_start | `moved-since-classification` | decided about -500, holds -46050 |
| Kozarnika, Dimovo Municipality | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0004): The quote dates the earliest use to 1.6-1.4 million BP (about -1 |
| Borough Hill Roman Villa | period_start | `moved-since-classification` | decided about -2500, holds 43 |
| Llaqta Qulluy, Vilca | lat | `coordinates-unresolved` | Wikidata Q21044271 has no P625 and the English article is a stub (declared Patrimonio Cultural, no point, no height, no  |
| Norton Camp | period_start | `moved-since-classification` | decided about -800, holds -2000 |
| Rock Art of the Iberian Mediterranean Basin | lat | `coordinates-unresolved` | The property is a serial World Heritage site of some 727 shelters spread over six autonomous communities from the Pyrene |
| Woburn Sands | period_start | `field-unresolved` | Woburn Sands is a town that grew from the hamlet of Hogsty End (Quaker meeting house c. 1675, turnpike 1727, earliest ma |
| Caves of Poço Velho | period_start | `moved-since-classification` | decided about -4000, holds -3000000 |
| Prokuplje | period_start | `field-unresolved` | No source dates the start of the town of Prokuplje itself. English and Serbian Wikipedia put the Neolithic/Vinca and Cop |
| Eartham Pit, Boxgrove | period_start | `moved-since-classification` | decided about -500, holds -478050 |
| Obadiah's Barrow | period_start | `field-unresolved` | No page I could read dates this barrow on Gugh. The English Wikipedia article contradicts itself: its lead calls it a 'N |
| Mane Braz | period_start | `field-unresolved` | The English Wikipedia article on Mane Braz (the Mane Braz dolmens near Erdeven, Morbihan) gives no date; the London Trav |
| Elche | period_start | `field-unresolved` | The -500 (5th century BC) is the foundation of the Iberian city of Helike/Ilici, which the English Wikipedia places at t |
| Eleusis | lat | `moved-since-classification` | decided about 38.0886659372907, 23.53682494352389, holds 38.0411, 23.538 |
| Great Tottington | period_start | `field-unresolved` | Wikipedia says only that the sarsens at Great Tottington (a moated manor farm near Maidstone) may be remains of a Neolit |
| Teufelsrutsch | lat | `coordinates-unresolved` | The site is the Celtic refuge fort on the Ahrenberg south of the Teufelsrutsch rock near Wendelsheim (German Wikipedia:  |
| Teufelsrutsch | period_start | `field-unresolved` | English Wikipedia says only that remains of a Celtic stronghold were found nearby, and German Wikipedia that remains of  |
| Giant's Grave, Cumbria | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Hodson Stone Circle | lat | `coordinates-unresolved` | The Hodson circle is destroyed or only 'thought to have been present'. Neither the English Wikipedia article nor Wikidat |
| Hodson Stone Circle | period_start | `field-unresolved` | The article dates the lost Hodson circle only by the class span of stone-circle building (3300-900 BCE, Late Neolithic a |
| Tsona Cave | period_start | `moved-since-classification` | decided about -500, holds -348050 |
| Bruach An Druimein, Kimartin Glen | lat | `moved-since-classification` | decided about 56.13375456249825, -5.486998046671952, holds 56.117602, -5.507935 |
| Bruach An Druimein, Kimartin Glen | period_start | `field-unresolved` | The excavation report (SHAIR 27) dates the main phase of occupation to the later first millennium BC (early Iron Age) an |
| Aufina | period_start | `field-unresolved` | English Wikipedia (from Smith's 1854-57 dictionary) only says Pliny lists the Aufinates among the Vestini and that it wa |
| Petrovaradin | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0038): The only support for 19,000 BC is the Wikipedia fortress article |
| Medicine Wheel/Medicine Mountain National Historic Landmark | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0047): The Wyoming encyclopedia quote dates charcoal from 'nearby arche |
| Mihailovac | lat | `coordinates-unresolved` | English Wikipedia says only that Mihailovac is an archaeological site and settlement near Vrsac; neither the article nor |
| Vicus Maracitanus-Ksar Toual | period_start | `field-unresolved` | No source dates the start of the site. The Princeton Encyclopedia of Classical Sites (as quoted on English Wikipedia) ca |
| Llaqta Qulluy, Acoria | lat | `coordinates-unresolved` | English Wikipedia (a stub: Huancavelica Region, Huancavelica Province, Acoria District) and Wikidata Q21044269 print no  |
| Trendle Ring | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Micheldever Wood | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Castlenalacht Stone Row | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Shihsanhang Museum of Archaeology | period_start | `moved-since-classification` | decided about 1998, holds -50 |
| Scladina | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0001): The 130,000 BP figure is the 1992 luminescence age of 130 +/- 20 |
| Yunus Sütunu | period_start | `field-unresolved` | No source dates the Yunus Sütunu (Pillar of Jonah) itself: Turkish Wikipedia only cites Xenophon's account of Cyrus pass |
| Rock Shelter of Solhapa | lat | `moved-since-classification` | decided about 41.47317682403635, -6.356957087993126, holds 41.456667, -6.336667 |
| Rock Shelter of Solhapa | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0035): The quote (from the DGPC record, code 74941) dates only the engr |
| Pusuquy Pata | lat | `coordinates-unresolved` | No source prints a point for Pusuquy Pata. Wikipedia and Wikidata give none; the excavation paper by Valdez, Valdez and  |
| Pusuquy Pata | period_start | `moved-since-classification` | decided about -800, holds 600 |
| T'akaq | lat | `coordinates-unresolved` | The only printed points (English and Spanish Wikipedia, Wikidata Q16901073) are those of the mountain T'akaq, not of the |
| T'akaq | period_start | `field-unresolved` | The English and Spanish articles describe a mountain with an archaeological site and give no date. A Huanuco Rumbos tour |
| Nettleton, Wiltshire | period_start | `field-unresolved` | The item and stored point are the village and civil parish of Nettleton, Wiltshire. English Wikipedia dates nothing abou |
| Drizzlecombe | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Tebay | period_start | `field-unresolved` | Wikipedia, the Cumbria County History Trust township summary and the Old Cumbria Gazetteer describe Tebay as a township  |
| Virgil's Tomb | period_start | `field-unresolved` | The pages call the monument only a 'Roman burial vault' / 'columbarium of the Roman period' (English, French, Italian Wi |
| Fournou Korifi | lat | `moved-since-classification` | decided about 35.007058153179614, 25.5900678098488, holds 35.0067, 25.6093 |
| Combs Ditch | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Thor's Cave | period_start | `field-unresolved` | The only readable page is the Wikipedia article (and its Russian and Ukrainian translations), which says the finds sugge |
| Uyu Uyu | site_type | `moved-since-classification` | decided about 'Fortress', holds 'City/town/settlement' |
| Čertova pec | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0039): The same page says the earliest finds are Mousterian (Middle Pal |
| Roman Thermae of Maximinus | period_start | `moved-since-classification` | decided about -100, holds 1 |
| Skarżysko-Kamienna | lat | `coordinates-unresolved` | English Wikipedia prints 51°7′N 20°55′E for the city (type:city, rounded to the arcminute) while Wikidata P625 and Polis |
| Cro-Magnon Rock Shelter | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0020): The only date (27,680 +/- 270 BP, Beta-157439) is an uncalibrate |
| Boswens Menhir | period_start | `field-unresolved` | Wikipedia's Boswens Menhir article, the Cornwall Guide page and the Ancient Penwith menhir page describe the stone, its  |
| Chevdar | lat | `moved-since-classification` | decided about 42.61680089201004, 25.400107285080768, holds 42.653333, 24.051604 |
| Chevdar | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0004): The quote only says 'early Neolithic' and the researcher applied |
| Roman Villa of Vilares | period_start | `moved-since-classification` | decided about 1, holds -300 |
| Privlaka, Vukovar-Syrmia County | lat | `coordinates-unresolved` | English and Croatian Wikipedia print only the village centre of Privlaka (45°11′40″N 18°50′16″E, the same as Wikidata P6 |
| Privlaka, Vukovar-Syrmia County | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0005): The quote dates the Sopot culture (and the article's own infobox |
| Borough Hill | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0008): The same HER page states the hillforts are Iron Age and lists a  |
| Pozzo Sacro del Predio Canopoli | period_start | `field-unresolved` | The sources disagree on the date and none gives one start. Sardegna Turismo (Regione Sardegna, sardegnaturismo.it/it/esp |
| Elyrus | period_start | `field-unresolved` | English, Greek, German and Spanish Wikipedia and ToposText (Hellenistic to Late Antique polis) date Elyros only by its f |
| Earl Shilton | period_start | `field-unresolved` | No source dates the start of Earl Shilton as a settlement. Wikipedia, GENUKI and the Hinckley Times give only the Roman  |
| Fushan Archaeological Site | lat | `coordinates-unresolved` | No readable page prints a point for the Fushan archaeological site (Fushan Village, Beinan, Taitung): the English and Ch |
| Thebes, Greece | period_start | `moved-since-classification` | decided about -500, holds -4000 |
| Taqrachullu | period_start | `moved-since-classification` | decided about 1, holds 700 |
| Dun Cuier | period_start | `moved-since-classification` | decided about 301, holds -200 |
| Inca Uyo | period_start | `field-unresolved` | No reputable source dates the start of Inca Uyo. The English Wikipedia article says only that the site was 'important in |
| Situs Megalit Tebing Tinggi | lat | `coordinates-unresolved` | The stored source (Media Lampung article) describes the Tebing Tinggi site without coordinates; the Megalithic Portal pa |
| Situs Megalit Tebing Tinggi | period_start | `field-unresolved` | The Media Lampung article calls Tebing Tinggi a prehistoric Pasemah megalithic site without any year, century or period  |
| Wurdi Youang Stone Arrangement | period_start | `field-unresolved` | The English article says 'The purpose, use, and age of the arrangement are not known' and that 'the precise age of the a |
| Painted Rock Petroglyph Site | period_start | `field-unresolved` | English Wikipedia says only that the site holds Hohokam-style petroglyphs and 'petroglyphs of Archaic origin' in the are |
| Kinichná | period_start | `moved-since-classification` | decided about 1, holds -400 |
| Ali Murad Mound | lat | `coordinates-unresolved` | No readable source prints a point for the Ali Murad mound: English Wikipedia and the Sindh Directorate General of Antiqu |
| Ali Murad Mound | period_start | `moved-since-classification` | decided about -4000, holds -2600 |
| Whetstones Stone Circle | period_start | `field-unresolved` | The Whetstones circle (Church Stoke, Powys) was destroyed around 1860-1870 and was never excavated or dated. Wikipedia g |
| Trink Hill | period_start | `field-unresolved` | English Wikipedia on Trink Hill (Nancledra, Cornwall) says only that a round barrow exists at the summit, with no date;  |
| Blakey Topping Standing Stones | period_start | `field-unresolved` | No readable source dates these standing stones: English Wikipedia, stone-circles.org.uk and the Northern Antiquarian des |
| Codford Circle | period_start | `field-unresolved` | English Wikipedia calls Codford Circle a Neolithic hill top enclosure or possible hillfort in its lead but states in the |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s008-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s008 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
