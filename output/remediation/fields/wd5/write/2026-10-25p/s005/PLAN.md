# WD5 fields-wd5-2026-10-25p-s005: plan

Built 2026-10-25T07:54:18+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s005`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s005:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 10 |
| sites_written | 5 |
| refused | 108 |
| cells:period_name | 5 |
| cells:period_start | 5 |
| refused:coordinates-unresolved | 21 |
| refused:field-unresolved | 60 |
| refused:moved-since-classification | 27 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Dağlı Kalesi | period_name | `1500 - 500 BC` | `500 BC - 1 AD` | wd5-derive-period-name |
| Dağlı Kalesi | period_start | `-800` | `-27` | wd5-replace |
| Jadranovo | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd5-derive-period-name |
| Jadranovo | period_start | `-500` | `-6500` | wd5-replace |
| Königsaue | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd5-derive-period-name |
| Königsaue | period_start | `-500` | `-78050` | wd5-replace |
| Palaikastro | period_name | `500 BC - 1 AD` | `3000 - 1500 BC` | wd5-derive-period-name |
| Palaikastro | period_start | `-500` | `-2900` | wd5-replace |
| Ponte de Rubiães | period_name | `1 - 500 AD` | `1000 - 1500 AD` | wd5-derive-period-name |
| Ponte de Rubiães | period_start | `101` | `1100` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Keilor Archaeological Site | period_start | `moved-since-classification` | decided about -500, holds -29050 |
| Minoan Modi | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0024): The ToposText quote only calls Modi a Minoan peak sanctuary and  |
| Çimdin Kalesi | lat | `coordinates-unresolved` | The Ministry's e-kitap page and the Kültür Envanteri record describe Çimdin Kale (Çemdin Kalesi) in Viranşehir, Şanlıurf |
| Çimdin Kalesi | period_start | `field-unresolved` | The sources disagree on when the castle began: Kültür Envanteri says Çimdin Kale (Eski Kale) was built by the Romans in  |
| Peregonivka | lat | `coordinates-unresolved` | The only printed point is the unreferenced coordinate statement of Wikidata Q18210819 (48 32 1.27 N, 30 23 0.26 E), whic |
| Peregonivka | period_start | `field-unresolved` | Kruts (trypillia.com, 2011) lists Peregonivka as a Trypillia settlement of about 100 ha in phase BII, but gives no date  |
| Teufelsstein, Haardt | period_start | `field-unresolved` | English and German Wikipedia describe the Teufelsstein as a carved monolith with a sacrifice bowl for its 'probably Celt |
| Quriwayrachina, Anta | lat | `coordinates-unresolved` | No readable page prints a point for the Qoriwayrachina terraces at Zurite (Anta): the English article and Wikidata item  |
| Quriwayrachina, Anta | period_start | `field-unresolved` | The English article gives no date or period for the Anta terraces; the only scholarly page found (a UNSAAC archaeology t |
| Miramar | lat | `coordinates-unresolved` | The entry has no Wikidata item, no Wikipedia article and no source_url. The linked pages (Atlas Obscura Quiahuiztlan, Mi |
| Miramar | period_start | `field-unresolved` | No source describing this site could be found, so none dates it; the stored 1000 is a band-edge made by a rule, and the  |
| Astale | period_start | `moved-since-classification` | decided about -500, holds 43 |
| Maltepe Tumulus | period_start | `field-unresolved` | The only dating found is scholarly: Pirson, Japp, Kelp and Nováček (2011, 'Der Tumulus auf dem İlyastepe und die pergame |
| Miyu Pampa | period_start | `field-unresolved` | The Turismo Peruano page that reproduces the Mincetur inventory description of the Sitio Arqueologico Miu Pampa (Jircan, |
| The Pipers, St Buryan | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Wat'a, Huánuco | period_start | `field-unresolved` | No source states a year for the start of Wat'a (Huata), Singa, Huamalíes. The English Wikipedia article gives no date or |
| Temple of Poseidon, Tainaron | period_start | `field-unresolved` | The Zenodo record for Tainaron (Pleiades-linked, citing C. Gardner's 2018 UBC dissertation) says 'Archaeological explora |
| Llamachayuq Qaqa | lat | `coordinates-unresolved` | English Wikipedia ('coord missing') and Wikidata Q17076901 print no point for Llamachayuq Qaqa (Llamachayoq Qaqa, Waqhan |
| Llamachayuq Qaqa | period_start | `moved-since-classification` | decided about -10000, holds 1438 |
| Clachtoll Broch | lat | `moved-since-classification` | decided about 58.205732597584536, -5.341416358179722, holds 58.195622, -5.342359 |
| Amaya, Burgos | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0007): The page separates cave visits (frecuentadas) from the Bell Beak |
| Bedd Taliesin | period_start | `moved-since-classification` | decided about -4000, holds -2000 |
| Ashwell, Hertfordshire | period_start | `field-unresolved` | The entry is the village and parish of Ashwell. English Wikipedia dates only separate things inside it: the nearby Arbur |
| Abbatija Tad-Dejr Hypogeal Complex | period_start | `field-unresolved` | No source dates the start of the complex: English Wikipedia says only that four larger complexes were added between the  |
| Wanakawri, Cusco | period_start | `field-unresolved` | The English article and the 2019 SAA abstract (tDAR) place Wanakawri/Huanacauri within the Inca Empire (ca. 1400-1533 CE |
| Tolmo de Minateda | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0042): The Castilla-La Mancha heritage sheet for the park dates the old |
| Lakhan-Jo-Daro | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0006): The quote only says the site was occupied during the Harappa Pha |
| Waruq | lat | `coordinates-unresolved` | The English article (Waruq / Huaroc, Chavinillo District, Yarowilca) has {{coord missing|Peru}}, the Spanish article Hua |
| Antik Barajı | period_start | `field-unresolved` | Reputable sources disagree on the date, so the start is disputed and none is taken. Lafli and Buora (Acta Classica Univ. |
| Swastika Stone | period_start | `field-unresolved` | English Wikipedia states that the Swastika Stone on Woodhouse Crag, Ilkley Moor, has not been verifiably dated: the acad |
| Medvednjak | lat | `moved-since-classification` | decided about 44.36653268734742, 20.956553640993786, holds 44.3976, 20.96142 |
| Lartos, Rhodes | lat | `coordinates-unresolved` | English Wikipedia says only that Lartos was an ancient village on the southeast coast of Rhodes and gives no point; its  |
| Lartos, Rhodes | period_start | `field-unresolved` | No page dates the start of the ancient village of Lartos. Wikipedia gives no date; German Wikipedia's Lardos article lis |
| Garden of the Fugitives, Pompeii | period_start | `field-unresolved` | The Wikipedia article only says the insula was largely converted to a vegetable garden and vineyard before the eruption  |
| Meydan Castle | period_start | `moved-since-classification` | decided about 1000, holds -312 |
| Brown Low | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Karabölücülü Harabeleri | period_start | `field-unresolved` | The Kultur Envanteri record of Karaböcülü Ören Yeri and its Wikidata item give no date or period, and I found no other p |
| Karabölücülü Harabeleri | site_type | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0045): The Kültür Envanteri record (Karaböcülü Ören Yeri, Çamlıbel, Sil |
| Karabölücülü Harabeleri | source_url | `field-unresolved` | The only page found is the Kultur Envanteri record 'Karaböcülü Ören Yeri', which spells the name differently from the en |
| Cave of Bacinete | period_start | `field-unresolved` | No source for the Cueva de Bacinete (Los Barrios, Cadiz) gives a year or a period the checker can read, and the sources  |
| Hatun Misapata | lat | `coordinates-unresolved` | English and Spanish Wikipedia place Hatun Misapata in Aucara District, Lucanas Province (Resolucion Viceministerial 459- |
| Little Meg | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Patara Antique Theatre | period_start | `moved-since-classification` | decided about 43, holds -323 |
| Ash Hole Cavern | period_start | `moved-since-classification` | decided about 1, holds -4000 |
| Phyle Cave | period_start | `field-unresolved` | English Wikipedia dates only a votive relief from the cave (mid-4th century BC to 1st century BC, 'various dates propose |
| Wendover | period_start | `field-unresolved` | Wikipedia, the VCH account and the town's own page give only documentary dates (a charter of 1214, a first market in 119 |
| Roman Milestones of Braga | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0035): The quote dates the road and its bridges (the first half of the  |
| Pirwayuq | lat | `coordinates-unresolved` | Wikidata P625 and Spanish Wikipedia print -12.9002, -75.7860, which is the village of Pirhuayoc in Vinac, Yauyos (Lima), |
| Pirwayuq | period_start | `field-unresolved` | No quotable date. The Spanish Wikipedia list of archaeological monuments of Huancavelica assigns 'Pirguayocc' (Laria) to |
| Crawley Edge Cairns | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Le Moustier | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0020): 56,000 BP is the oldest thermoluminescence date of only the uppe |
| Aulanko Castle | period_start | `field-unresolved` | English Wikipedia says it is not known when Aulanko Castle was built (only that it was demolished in the 13th century);  |
| Peñas de Cabrera | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0041): The Commons line 'rock art (Chalcolithic)' is a Wikidata label,  |
| Lindus | period_start | `moved-since-classification` | decided about -1500, holds -4000 |
| Bosporthennis | period_start | `field-unresolved` | Only the Wikipedia article is readable and it says the courtyard houses date 'from the Late Iron Age'; a search of the H |
| Achladia | lat | `moved-since-classification` | decided about 35.16680700239597, 26.050032182871053, holds 35.169212, 26.071848 |
| San Manuel Cenote | period_start | `field-unresolved` | The entry has no Wikidata item, no Wikipedia article and no linked pages. The only dating on record (pots possibly of 20 |
| Lapford | period_start | `field-unresolved` | The site is the village of Lapford. The only early date in its article concerns the Roman fort at nearby Bury Barton, a  |
| Khapia | period_start | `field-unresolved` | Khapia is a mountain (a possibly extinct volcano) that Wikipedia says was declared a prehispanic archaeological monument |
| Lismore Fields | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0014): The quote is a rounded 'first inhabitants 6,000 years ago' (not  |
| El Pedregal Archaeological Site | lat | `coordinates-unresolved` | Wikidata (Q63958892) and the English, Spanish and French articles print no point, and the Guanacaste conservation-area r |
| Blowing Stone | period_start | `field-unresolved` | The Blowing Stone is a perforated natural sarsen; Wikipedia and the Royal Berkshire History page give only a first recor |
| Wimble Toot | period_start | `field-unresolved` | Wikipedia on Wimble Toot (Babcary, Somerset) states 'The site is of an undetermined age' and offers two incompatible rea |
| Scorhill Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Colebrooke, Devon | period_start | `field-unresolved` | Colebrooke is a village; English Wikipedia says the supposed Roman fort or marching camp east of the village has no evid |
| Bow Hill, Sussex | period_start | `field-unresolved` | The stored point (50.8950, -0.8291) lies at the Bow Hill ridge top, about 500 m from the Devil's Humps (50.8931, -0.8364 |
| Zemun | period_start | `moved-since-classification` | decided about -300, holds -4000 |
| Kinđa | period_start | `field-unresolved` | The Kinda mound near Kikinda has never been excavated. English Wikipedia contradicts itself: it calls it a Copper Age ku |
| Ringmoor Stone Row and Cairn Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Foel Dduarth Enclosure | period_start | `field-unresolved` | The Heneb HER record GAT229 (Enclosure, Foel Dduarth, a Scheduled Monument) and the Cadw list type it only as prehistori |
| Giants' Graves | lat | `coordinates-unresolved` | The entry names the giants' tombs of Sardinia as a type with no Wikidata item and no stored source; the Italia.it page l |
| Little Sodbury | period_start | `field-unresolved` | The stored point is the village of Little Sodbury. The Victoria County History draft says evidence before the Iron Age i |
| Craddock Moor Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Mersinaki | lat | `moved-since-classification` | decided about 35.15098318594448, 32.81127348296412, holds 35.156834, 32.788315 |
| Mersinaki | period_start | `field-unresolved` | The sources only place the start loosely: the PHRC entry (phrc.it, citing Gjerstad et al. 1937, pp. 393-398) says the sa |
| Inkachaka | period_start | `moved-since-classification` | decided about 43, holds 1401 |
| Boundary Stones, Ukraine | period_start | `field-unresolved` | Only the Wikipedia family (en/uk/ru, one source) calls the alley of menhirs 'late Neolithic', with no excavation or abso |
| Scutchamer Knob | period_start | `field-unresolved` | Wikipedia and the Ridgeway National Trail page call the mound an early Iron Age round barrow, but the archaeologist Howa |
| Q'asa Pata | lat | `coordinates-unresolved` | The English Wikipedia article and Wikidata Q21044306 print no coordinate; no other readable source printing a point for  |
| Kusilluchayoc - El Templo de los Monos | period_start | `moved-since-classification` | decided about 43, holds 1401 |
| Yellowmead Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Corycus, Crete | lat | `coordinates-unresolved` | English Wikipedia and Wikidata (Q65077764, no P625) place the town only on the Corycus/Gramvousa peninsula in northweste |
| Corycus, Crete | period_start | `field-unresolved` | The only sources for the town are the mention by Ptolemy and a passage in Juvenal (English Wikipedia, citing Smith's Dic |
| Adullam Grove Nature Reserve | period_start | `field-unresolved` | The site is a nature reserve declared in 1994 that contains several separate ruins; English Wikipedia dates Horvat Midra |
| Kunturmarka, Pasco | lat | `coordinates-unresolved` | English Wikipedia (Kunturmarka, Pasco: Paucartambo District, Pasco Province; round buildings and chullpa tombs) and Wiki |
| Caves and Ice Age Art in the Swabian Jura | period_start | `moved-since-classification` | decided about -500, holds -41050 |
| Early Roman House | lat | `coordinates-unresolved` | English Wikipedia (Paphos Archaeological Park) names the Early Roman House only as one of the structures the Polish miss |
| Early Roman House | period_start | `field-unresolved` | No readable page dates the Early Roman House: English Wikipedia and the University of Warsaw news item only list it amon |
| Jabal al-ʿHayn | period_start | `field-unresolved` | The English Wikipedia article only calls the petroglyphs 'pre-historic' (a word the period vocabulary does not read from |
| Siponto | period_start | `field-unresolved` | No source dates the start of Siponto. English, German and Italian Wikipedia give only a Daunian foundation (legend of Di |
| Aghios Epiktitos Vrysi | lat | `moved-since-classification` | decided about 35.34050532036911, 33.319166696371134, holds 35.33148, 33.4266 |
| Zapote Bobal | period_start | `field-unresolved` | Sources disagree about what counts as the start: the FAMSI report by Fitzsimmons (Chronology: Late Classic, core occupie |
| Winnemucca Lake Petroglyphs | lat | `coordinates-unresolved` | The stored point is the centre of the dry Winnemucca Lake bed (enwiki 40°06'40"N 119°20'28"W), not the petroglyph site 2 |
| Coffin Stone | period_start | `field-unresolved` | English Wikipedia: archaeologists have argued the stone was part of a destroyed fourth-millennium BCE long barrow, but t |
| Serpent's Wall | lat | `coordinates-unresolved` | Serpent's Wall is a system of earthworks of about 1,000 remaining km across the middle Dnieper; the English, Ukrainian,  |
| Castro of Castelo Velho | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0034): The quoted page is about the medieval Castle of Alandroal in the |
| Saticula | period_start | `field-unresolved` | No source gives a start for Saticula. English Wikipedia names it a Caudini city attacked by Rome in 343 BC, which is an  |
| Yesemek Open Air Museum | lat | `moved-since-classification` | decided about 36.89306, 36.74444, holds 36.90461202109322, 36.745471619689944 |
| Mounsey Castle | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Tyberissos (Tubure) Kaya Mezarı | lat | `coordinates-unresolved` | The Kültür Envanteri record and Lycian Monuments describe the rock tomb as carved into an isolated bedrock outcrop in th |
| Usnu, Huánuco | period_start | `field-unresolved` | The only dating of this Usnu (Umari district, Pachitea province, Huanuco; 2,833 m, Panaococha) is the tourism inventory  |
| Caer Mote | period_start | `field-unresolved` | The article calls the earthwork enclosure 'The Battery' on St. John's Hill 'of undetermined age' and gives only a 1st-ce |
| Bema | lat | `coordinates-unresolved` | The entry 'Bema' is the generic term for an orator's platform (English Wikipedia's Bema article is about the term in Gre |
| Bema | period_start | `field-unresolved` | Bema is a generic architectural term, not one datable monument; English Wikipedia gives no date for any bema and the Pny |
| Banoštor | period_start | `field-unresolved` | No source dates the start of Banoštor (Bononia Malata). English Wikipedia's 279 BC is the Gallic invasion of the Balkans |
| Ruthergate | lat | `coordinates-unresolved` | The English Wikipedia article on Ruthergate (a disused old road near Guisborough) prints no coordinates and Wikidata Q73 |
| Llamachayuq | period_start | `field-unresolved` | The only source that dates Llamachayuq/Llamachayoq (San Jeronimo, Andahuaylas) is the MINCETUR inventory ficha 8212, whi |
| Hoyo Negro Cenote | lat | `coordinates-unresolved` | No readable page prints a point for the Hoyo Negro pit itself. English Wikipedia has no Hoyo Negro article; its Naia art |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s005-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s005 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
