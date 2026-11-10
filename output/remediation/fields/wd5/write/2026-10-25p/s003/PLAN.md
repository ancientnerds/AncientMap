# WD5 fields-wd5-2026-10-25p-s003: plan

Built 2026-10-25T07:52:22+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s003`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s003:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 12 |
| sites_written | 6 |
| refused | 112 |
| cells:period_name | 6 |
| cells:period_start | 6 |
| refused:coordinates-unresolved | 21 |
| refused:country-changes | 1 |
| refused:field-unresolved | 63 |
| refused:moved-since-classification | 27 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Ayşepınar | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd5-derive-period-name |
| Ayşepınar | period_start | `-800` | `-323` | wd5-replace |
| Goyet Caves | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd5-derive-period-name |
| Goyet Caves | period_start | `-500` | `-118050` | wd5-replace |
| Longstone of Minchinhampton | period_name | `4500 - 3000 BC` | `3000 - 1500 BC` | wd5-derive-period-name |
| Longstone of Minchinhampton | period_start | `-4000` | `-1600` | wd5-replace |
| Padah-Lin Caves | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd5-derive-period-name |
| Padah-Lin Caves | period_start | `-500` | `-23050` | wd5-replace |
| Rumicolca | period_name | `1 - 500 AD` | `500 - 1000 AD` | wd5-derive-period-name |
| Rumicolca | period_start | `43` | `600` | wd5-replace |
| Tongobriga | period_name | `1 - 500 AD` | `1500 - 500 BC` | wd5-derive-period-name |
| Tongobriga | period_start | `1` | `-800` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Ponton Heath Barrow Cemetery | period_start | `moved-since-classification` | decided about -4000, holds -2000 |
| Brown Willy Cairns | period_start | `field-unresolved` | Wikipedia says the Brown Willy summit cairn has never been excavated; the 2162-1746 cal BC dates belong to nine other Bo |
| Naviforme | lat | `coordinates-unresolved` | Q4885086 and the English article 'Naviforme' describe a building type, the boat-shaped prehistoric house of the Balearic |
| Monte Bubbonia | period_start | `field-unresolved` | No source gives one agreed start in years for Monte Bubbonia. English Wikipedia says only that the ruins of the summit t |
| Gerrards Cross | period_start | `field-unresolved` | The stored site is the town of Gerrards Cross; its Wikipedia article gives no date for the start of the town, and only m |
| Isla de Sacrificios | period_start | `field-unresolved` | No readable source dates the start of the site on the Isla de Sacrificios. English Wikipedia only gives the 1518 Spanish |
| Carn Kenidjack | period_start | `field-unresolved` | English Wikipedia calls Carn Kenidjack a hill covered in megaliths and dates nothing; the Cornish Ancient Sites Protecti |
| El Baúl | period_start | `field-unresolved` | No page gives a start for El Baul that the others do not contradict. English Wikipedia says only that it was occupied du |
| Roman Dam of Pego da Moura | period_start | `moved-since-classification` | decided about -27, holds 1 |
| Camlet Way | lat | `coordinates-unresolved` | Camlet Way is a linear Roman road running between Colchester and Silchester via St Albans (English, German and Italian W |
| Camlet Way | period_start | `field-unresolved` | English, German and Italian Wikipedia call Camlet Way a Roman road without any date for its construction; the English He |
| Spartia Temple | period_start | `field-unresolved` | English Wikipedia and a 2007 press report (Kathimerini text reposted on a blog) call the Spartia sanctuary of Herakles n |
| Blue Man-i'-th'-Moss | period_start | `field-unresolved` | The only dating statement found is Wikipedia's 'believed to have been standing since pre-Roman times', which names no ye |
| Blewbury | period_start | `field-unresolved` | The entry is the village and parish of Blewbury; the dated remains (Blewburton Hill hill fort, begun in the sixth or fif |
| Jinkiori | lat | `coordinates-unresolved` | English and Spanish Wikipedia print -12.9606, -71.3477 for Jinkiori/Hinkiori, but that point is the same as the nearby Q |
| Jinkiori | period_start | `field-unresolved` | English and Spanish Wikipedia attribute the engravings to an Amazonian origin, possibly ancestors of the Huachipaeri, wi |
| Cursus Barrows | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Huntersquoy Chambered Cairn | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0037): The HES scheduling record gives a hedged date for this very cair |
| Tampu Mach'ay, Huancavelica | lat | `coordinates-unresolved` | Tampu Mach'ay (Tambomachay), a cave site 300 m from the main plaza of Acostambo, Huancavelica: Wikipedia and Wikidata ca |
| Tampu Mach'ay, Huancavelica | period_start | `field-unresolved` | The only description (DIRCETUR Huancavelica inventory sheet, 2009) says the caves hold looted human remains and that Tam |
| Purépecha Proto Urban Site | lat | `coordinates-unresolved` | The Los Angeles Times report on this unnamed proto-urban centre of the Purepecha at Lake Patzcuaro says the discoverer ' |
| Purépecha Proto Urban Site | site_type | `moved-since-classification` | decided about 'Settlement', holds 'City/town/settlement' |
| Sarvaš | period_start | `moved-since-classification` | decided about -500, holds -6200 |
| Llaqta Qulluy, Conayca | lat | `coordinates-unresolved` | Wikidata Q21044270 has no P625 and the English article is categorised as missing coordinates; the Mincetur-derived page  |
| Llaqta Qulluy, Conayca | period_start | `field-unresolved` | The English article (a stub) gives no date, culture or period; the Mincetur-derived turismoperuano.com page describes on |
| Sunningdale Barrow | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Burial Ground of Cherneliv-Ruskyi | period_start | `field-unresolved` | The en/uk/pl Wikipedia articles (one source) say only that it is a burial ground of the Chernyakhov culture investigated |
| Arna, Greece | period_start | `field-unresolved` | English Wikipedia (Arna, Greece) and Hellenica World describe a modern village on Mount Taygetus; the only dated item is |
| Beinan Cultural Park | period_start | `moved-since-classification` | decided about -500, holds -3050 |
| Tomb of the Birds | period_start | `field-unresolved` | The Tomb of the Birds is NC 2, one of three North Cliff rock-cut tombs of Reisner's numbering (Andrew Collins's page say |
| Xnaheb | site_type | `field-unresolved` | no counted answer in 3 rounds: quote not found: https://en.wikipedia.org/wiki/Xnaheb; quote not found: https://en.wikipe |
| Ariconium | period_start | `moved-since-classification` | decided about -800, holds -100 |
| Dun Troddan | period_start | `moved-since-classification` | decided about -4000, holds -550 |
| Asseria | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0004): A tour-operator blog says the oldest remains date to the 5th cen |
| Jaw Hill | lat | `coordinates-unresolved` | The only printed point is the one of the Wikipedia article and Wikidata item Jaw Hill, which is the hill (53.7057, -1.55 |
| Jaw Hill | period_start | `field-unresolved` | The only text about the site is the Wikipedia stub, which says the enclosure 'was thought to be a possible Roman marchin |
| Kobba Bent el Rey | lat | `coordinates-unresolved` | Read and found no printed point for Kobba Bent el Rey itself: the French and Arabic Wikipedia articles and their Wikidat |
| Ganjnameh Ancient Inscriptions | period_start | `moved-since-classification` | decided about -10000, holds -550 |
| Burrington Combe | period_start | `moved-since-classification` | decided about -4500, holds -50000 |
| Scholes Coppice | period_start | `field-unresolved` | The Wikipedia article is about the woodland and only says the most significant site there 'is thought to be an Iron Age  |
| Lower Swat Valley | lat | `coordinates-unresolved` | The entry is the whole lower Swat valley, a region (the Urdu Wikipedia source_url describes a historical area); it is no |
| Lower Swat Valley | period_start | `field-unresolved` | A region of many sites has no single start. English Wikipedia's Swat Valley article dates only the Gandhara grave cultur |
| Agrour Amogjar | period_start | `field-unresolved` | The Wikidata item is a mountain, and the paintings of the Agrour Amogjar shelters belong to eight stylistic groups from  |
| Buddhist Caves of Khapra Kodiya | period_start | `field-unresolved` | The sources disagree across the BC/AD line for this very cave: English Wikipedia and its Junagadh group article give the |
| Ermita de la Virgen del Pilar Dam | period_start | `moved-since-classification` | decided about 1, holds -100 |
| Muntham Court Romano-British Site | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0014): Scholarly sources date the Muntham Court settlement earlier than |
| Robin Hood's Butts | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Ayazini Kaya Church | period_start | `field-unresolved` | The sources disagree across buckets: Kultur Envanteri (Meryem Ana Kilisesi, Ayazini, also called Oyma Kilise) says the c |
| Appolonia Temple Ruins | period_start | `field-unresolved` | Kultur Envanteri types the structure only as '?, Temple' with no date, and the Princeton Encyclopedia entry for Apolloni |
| Palencia | period_start | `field-unresolved` | English and Spanish Wikipedia only give the Roman conquest (2nd century BC) and say the city's historical origins remain |
| Foxholes, Hertford | period_start | `moved-since-classification` | decided about 1, holds -2500 |
| Plain of Jars Site 3 | period_start | `field-unresolved` | No source dates Site 3 (Hai Hin Lat Khai) itself. UNESCO dates the 15-component serial property (Site 3 is one component |
| Ayşepınar | lat | `moved-since-classification` | decided about 38.21917623289961, 35.62750736219417, holds 38.2289, 35.615481 |
| Nine Maidens Stone Row | period_start | `moved-since-classification` | decided about -4000, holds -2900 |
| Karabal Belören Demre Antalya | lat | `coordinates-unresolved` | No readable heritage register, Wikipedia or Wikidata entry exists for a site 'Karabal Belören' in Demre; the Kultur Enva |
| Karabal Belören Demre Antalya | period_start | `field-unresolved` | No source describes or dates a site called Karabal Belören in Demre; the database's own import article (a church in Ando |
| Waraqu Urqu | lat | `coordinates-unresolved` | The English article's infobox has no coordinates; its only point (13°07′13″S 73°49′57″W) is stated for the mountain Wana |
| Roma Dönemi Agora Harabeleri | lat | `coordinates-unresolved` | The agora in Ayaş (Erdemli) is the Roman agora of Elaiussa Sebaste, which lies next to the theatre; no readable page pri |
| Roma Dönemi Agora Harabeleri | period_start | `moved-since-classification` | decided about 1000, holds 101 |
| Roma Dönemi Agora Harabeleri | source_url | `field-unresolved` | The entry is the map-directory name 'Roma Dönemi Agora Harabeleri' (Yandex Maps, Ayaş Mah., Kızılbağ Cad.), i.e. the Rom |
| Wraxall, Somerset | period_start | `field-unresolved` | Wraxall, Somerset is a village; Wikipedia, BAFHS and the Historic England deserted-settlement record describe a Saxon-er |
| Oddendale Stone Circle | period_start | `field-unresolved` | The concentric stone circle at about NY 592129 (Historic England 1011513) has only an antiquarian opening (Rev. J. Simps |
| Deepcar | period_start | `moved-since-classification` | decided about -500, holds -10000 |
| Kintradwell Broch | lat | `moved-since-classification` | decided about 58.010147753244, -3.8500107312077168, holds 58.048774, -3.815623 |
| Kintradwell Broch | period_start | `field-unresolved` | No source dates this broch itself. The Highland HER record (MHG9777) gives only the generic band 'Early Iron Age to Earl |
| Funzie Girt | period_start | `field-unresolved` | No source gives a start year or one period for Funzie Girt: the English Wikipedia says the date is unknown with Mesolith |
| El Tortuguero | period_start | `field-unresolved` | No readable source states a year, century or founding period for the start of El Tortuguero. English Wikipedia and the G |
| The Pipers | period_start | `field-unresolved` | Wikipedia (The Pipers, The Hurlers) gives the Minions Pipers no date; stone-circles.org.uk says it is 'debatable whether |
| Etruscan Pyramid of Bomarzo | period_start | `field-unresolved` | No reliable source dates the pyramid. The castellotorrealfina.it page says 'its dating, like its true nature, remains sh |
| Çatalat Viranşehir Antik Kent | lat | `coordinates-unresolved` | The site is the Çatalat (Çatlar) ruins in the Tektek mountains; the linked Wikidata item and English Wikipedia article ( |
| Çatalat Viranşehir Antik Kent | period_start | `field-unresolved` | The English Wikipedia article and the linked pages (Livius, Britannica) concern the town of Viranşehir/Constantina (Cons |
| Remains of Roknia | lat | `coordinates-unresolved` | Every readable page that prints a point (German, English and French Wikipedia, Wikimedia Commons, Archaeolist) gives the |
| Remains of Roknia | period_start | `field-unresolved` | No readable page gives the necropolis a year, century or English period word of its own. German Wikipedia says almost al |
| Roman Walls of Córdoba | lat | `moved-since-classification` | decided about 37.892469, -4.768655, holds 37.86688688608024, -4.766602330498061 |
| Lauriacum | period_start | `field-unresolved` | The sources disagree on when Lauriacum began, so the start is disputed and no single date can be given. German Wikipedia |
| Cave of Salemas | period_start | `moved-since-classification` | decided about -500, holds -4501 |
| Bincknoll Castle | period_start | `field-unresolved` | Sources conflict on whether the earthwork is Iron Age at all: English Wikipedia says the Iron Age origin is currently un |
| Mulri Hills | lat | `coordinates-unresolved` | English Wikipedia places the Mulri Hills only 'in Gulshan Town, Karachi' (no coordinates, coord-missing) and in front of |
| Mulri Hills | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0029): The page names a Late Palaeolithic and a Mesolithic phase, but - |
| Treva | lat | `coordinates-unresolved` | Treva is known only from Ptolemy's Geographia and from Roman campaign accounts; its location is contested: English Wikip |
| Treva | period_start | `field-unresolved` | English Wikipedia describes only a hypothesised Roman marching camp and vicus around 4 BC to 5 AD campaigns, with 'no ar |
| Chuping Archaeological Site | period_start | `moved-since-classification` | decided about -10000, holds -800 |
| Lake Bolac Stone Arrangement | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0002): The ABC quote is only a lower bound ('more than 1,500 years ago' |
| Oldbury Rock Shelters | period_start | `moved-since-classification` | decided about -500, holds -48050 |
| Alabanda | period_start | `field-unresolved` | No source gives a reliable start for Alabanda. Livius says the town 'was founded in the fourth century BCE', but other s |
| Clayhanger, Devon | period_start | `moved-since-classification` | decided about -800, holds 43 |
| Marcinków, Świętokrzyskie Voivodeship | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0034): The quote dates the Rydno reserve as a whole (several hundred ty |
| Roma Tiyatrosu | period_start | `field-unresolved` | No readable source dates the theatre of Anavarza itself. The Ministry-linked Turkish Museums page only lists the theatre |
| Roma Tiyatrosu | source_url | `field-unresolved` | The only pages about the theatre itself (the Kültür Envanteri record 'Anazarbos Antik Tiyatrosu' and the Wikidata item ' |
| Ražanj | period_start | `field-unresolved` | No source dates the start of Razanj. English Wikipedia gives only the Roman name Cametas and a 1929-1941 note; Serbian W |
| The Ancient Lycian Mezarı2 | lat | `coordinates-unresolved` | The entry 'The Ancient Lycian Mezari2' has no source page of its own and names no particular tomb; its stored point lies |
| Quillcay Machay | period_start | `field-unresolved` | No source dates Quillcay Machay: Wikipedia gives only its heritage declaration; the tourism record calls the art 'chavin |
| Broadbury Castle | period_start | `field-unresolved` | Wikipedia reports that Historic England reads Broadbury Castle as a Roman marching camp but that firm evidence for this  |
| Te Pito O Te Henua | period_start | `field-unresolved` | Te Pito O Te Henua is the name of a smooth, roughly spherical basalt boulder (about 75 cm, Wikidata Q118977915, de.wikip |
| La Pintada | period_start | `field-unresolved` | The stored -10000 (rule value for rock art) has no source; the Sonoran rock art of La Pintada is not dated that early by |
| Barton-le-Clay | period_start | `field-unresolved` | Barton-le-Clay is a village; Wikipedia says only that it has existed since at least 1066 (a lower bound, not a start), t |
| Alogonia - Town | period_start | `field-unresolved` | English Wikipedia (Alagonia, Alogonia (town)) and ToposText describe an ancient town of Laconia/Messenia known from Paus |
| El Oso, Ávila | period_start | `field-unresolved` | The only date for this statue is the unreferenced inception '5. century BCE' (end '2. century BCE') on the Wikidata item |
| Jivdhan Fort | period_start | `field-unresolved` | Sources disagree and none is reliable for the start: English Wikipedia says the fort 'originated during the Satavahana e |
| Narona | lat | `country-changes` | the new point lies in ['Bosnia and Herzegovina'], the site says Croatia |
| Sisira Well | lat | `coordinates-unresolved` | No readable page prints a point for the well: the English and Arabic Wikipedia articles and Wikidata give none and place |
| Sisira Well | period_start | `field-unresolved` | The English and Arabic Wikipedia articles say only that this type of rock-cut irrigation system was known in the Nabatae |
| Chawaytiri | period_start | `moved-since-classification` | decided about -10000, holds 1438 |
| Ancient Pydna | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0022): The quote puts the first habitation at the END of the Late Bronz |
| Trapeza, Crete | period_start | `moved-since-classification` | decided about -500, holds -4000 |
| Llactan | period_start | `field-unresolved` | The Spanish Wikipedia article on Llactan (also called Anguyo Alto, La Peca District, Bagua, Amazonas) states 'Todavia no |
| Siscia | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0005): The 4th century BC marks the Celtic oppidum phase only; the Arch |
| Qurimarka, Cusco | lat | `coordinates-unresolved` | No readable page prints a point for Qurimarka (Qorimarka) on the Rayanniyoq river, Ollantaytambo District: the English a |
| Belbury Castle | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Wamanilla | lat | `coordinates-unresolved` | The English Wikipedia infobox for Wamanilla has an empty coordinates field, Wikidata Q20085597 has no P625 and no other- |
| Quishuar Archaeological Site | lat | `coordinates-unresolved` | The English Wikipedia article places Quishuar only in the south of Yanama District and prints no coordinate; Wikidata Q1 |
| Swanborough Tump | period_start | `field-unresolved` | No source dates Swanborough Tump: English Wikipedia says only that it has been considered a Bronze Age bowl barrow while |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s003-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s003 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
