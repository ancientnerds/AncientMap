# WD5 fields-wd5-2026-10-25p-s002: plan

Built 2026-10-25T07:51:20+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25p_fields-wd5-s002`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25p-s002:<site>:<column>`.

| counter | value |
|---|---|
| sites | 100 |
| cells | 8 |
| sites_written | 4 |
| refused | 113 |
| cells:period_name | 4 |
| cells:period_start | 4 |
| refused:coordinates-unresolved | 22 |
| refused:field-unresolved | 55 |
| refused:moved-since-classification | 36 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Castle of Cola | period_name | `1000 - 1500 AD` | `3000 - 1500 BC` | wd5-derive-period-name |
| Castle of Cola | period_start | `1000` | `-2500` | wd5-replace |
| Kudaro | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd5-derive-period-name |
| Kudaro | period_start | `-500` | `-358050` | wd5-replace |
| Oppidum Steinsburg | period_name | `500 BC - 1 AD` | `1500 - 500 BC` | wd5-derive-period-name |
| Oppidum Steinsburg | period_start | `-500` | `-1200` | wd5-replace |
| Zar Cave | period_name | `500 BC - 1 AD` | `< 4500 BC` | wd5-derive-period-name |
| Zar Cave | period_start | `-500` | `-50000` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Stapari | period_start | `moved-since-classification` | decided about -3000, holds -4000 |
| Khuntichi Vaat Hadsar Fort | period_start | `field-unresolved` | The entry is the same Hadsar fort (Wikidata Q24951841). English Wikipedia says only 'it is believed that this fort was b |
| Kenko, Puno | lat | `coordinates-unresolved` | English Wikipedia, Wikidata (no P625, no other-language article) and the MINCETUR inventory record (ficha 5018) print no |
| Kenko, Puno | period_start | `moved-since-classification` | decided about 1, holds 1438 |
| Fir Clump Stone Circle | period_start | `field-unresolved` | English Wikipedia places the destroyed Fir Clump circle only in the general tradition of stone circle building (3300-900 |
| Mahkeme Ağacin Kültürel Jeositi | lat | `coordinates-unresolved` | The Kızılcahamam municipality pages for the geosite (and the district governorate, Turkish Wikipedia's article on the Ma |
| Pilares do Lena | period_start | `field-unresolved` | The Lena Pillars are a natural rock formation of early to middle Cambrian limestone, marlstone, dolomite and slate (Engl |
| Vescia | period_start | `field-unresolved` | English, Italian, Catalan and Swedish Wikipedia give only Vescia's role in the Latin War and its destruction (340 or 314 |
| Bayston Hill | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0007): The site is the village and civil parish of Bayston Hill (stored |
| Pisarissos Antik Kenti | lat | `moved-since-classification` | decided about 36.660868, 31.728062, holds 36.65641190502751, 31.75926440009959 |
| Pisarissos Antik Kenti | site_type | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0046): English Wikipedia's 'town' rests on the Barrington Atlas and is  |
| Tomba dei Giganti e Nuraghe Imbertighe | period_start | `field-unresolved` | Italian Wikipedia says only 'Il sepolcro può essere ascritto al Bronzo medio' (no year or century), a period word the qu |
| Iskuqucha | lat | `coordinates-unresolved` | English and Spanish Wikipedia place Iskuqucha (Izcucocha) in La Oroya District, Yauli Province, Junin, and Andina report |
| Çavuştepe | lat | `coordinates-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0046): The quote prints 38.352443N 43.459393E, not the stored 38.350257 |
| Pumamarka, Urubamba | period_start | `moved-since-classification` | decided about -800, holds 1000 |
| Al-Dafi Site | lat | `coordinates-unresolved` | No readable source prints a point for the Al-Dafi site: the English and Arabic Wikipedia articles carry no coordinates,  |
| Amaru Marka Wasi | period_start | `field-unresolved` | English and Spanish Wikipedia say only that the site was 'possibly the former residence of Amaru Yupanqui', eldest son o |
| Kinniside Stone Circle | period_start | `field-unresolved` | Kinniside is a 1925 reconstruction; Wikipedia gives no date, and stone-circles.org.uk, which calls it a typical Cumbrian |
| Dhank Caves | period_start | `field-unresolved` | The sources disagree across buckets: English Wikipedia and showcaves.com say the caves were carved in the 7th century AD |
| High Peak, Devon | period_start | `field-unresolved` | High Peak (Peak Hill, Sidmouth) is a multi-period site: Wikipedia names an eroded Iron Age hill fort but says only that  |
| Dun Carloway | period_start | `moved-since-classification` | decided about 1, holds -200 |
| Shinewater | lat | `coordinates-unresolved` | Neither the Wikipedia article nor the Wikidata item prints a point. The only sources that print coordinates for the sche |
| Shinewater | period_start | `moved-since-classification` | decided about -3000, holds -800 |
| Desfina | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0023): The Ministry page dates the fortified Mycenaean settlement on Ka |
| Bizzicu Rossu | period_start | `field-unresolved` | adversarial reject (round 1, adversarial:adv-r1-b0004): The 'Datazione' column of the Museo dei dolmen table is an archa |
| Dolmen of Carapito I | period_start | `field-unresolved` | Reputable sources disagree on the construction date of anta 1 do Carapito, so no single start year can be given. English |
| Cossington, Kent | lat | `coordinates-unresolved` | English Wikipedia prints no coordinates for Cossington, Kent and its Wikidata item has no P625; the Kent Archaeological  |
| Cossington, Kent | period_start | `field-unresolved` | Wikipedia says only that the lost sarsens are thought to possibly be the remains of a Neolithic chambered long barrow an |
| Gritulu | lat | `coordinates-unresolved` | The English and Corsican Wikipedia articles on Gritulu print no coordinates, Wikidata item Q5609729 holds no coordinate  |
| Torralba and Ambrona - Archaeological Site | period_start | `moved-since-classification` | decided about -500, holds -398050 |
| Cuatro Cienegas Footprints | lat | `coordinates-unresolved` | The site has no Wikidata item, Wikipedia article or stored source page. English and Spanish Wikipedia articles on Cuatro |
| Cuatro Cienegas Footprints | period_start | `field-unresolved` | No readable source describes the Cuatro Cienegas footprints or dates them: the Wikipedia articles on the town and basin  |
| Talapty Settlement | lat | `moved-since-classification` | decided about 44.80061056481539, 78.40493914096743, holds 44.821111, 78.363889 |
| Hadzhidimitrovo | lat | `coordinates-unresolved` | The Wikipedia article is tagged coord missing and the Wikidata item has no P625. The Yambol Regional Historical Museum p |
| Hadzhidimitrovo | period_start | `moved-since-classification` | decided about -500, holds -5230 |
| Day House Lane Stone Circle | period_start | `field-unresolved` | English Wikipedia dates the Day House Lane (Coate) Stone Circle near Swindon only through its class: stone circles were  |
| Traditional Arts Museum | lat | `coordinates-unresolved` | No readable page prints a point for the Palmyra museum of popular traditions (the khan north of the Temple of Bel, which |
| Nakhchivan Rock Signs | lat | `coordinates-unresolved` | No readable source gives a point for the rock signs themselves. English and Azerbaijani Wikipedia name only the place (A |
| Nakhchivan Rock Signs | period_start | `field-unresolved` | The English, Azerbaijani, German and Turkish articles describe three engraved rock signs found in 2016 at Agsal (circle, |
| Qilakitsoq | period_start | `field-unresolved` | No readable source dates the start of the Qilakitsoq settlement itself: the English Wikipedia article says its house rem |
| Rockbourne Roman Villa | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0016): The Trust sentence only says the history spans the Iron Age to t |
| Archaeological Site of Plataea | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0023): The quote only says Plataea existed from Mycenaean times, but th |
| T'uqu T'uquyuq | lat | `coordinates-unresolved` | No readable source prints a point for T'uqu T'uquyuq itself: its Wikipedia article and Wikidata item carry none, the MIN |
| T'uqu T'uquyuq | period_start | `moved-since-classification` | decided about -10000, holds 1438 |
| Te Pito Kura | period_start | `field-unresolved` | No readable source dates the building of Ahu Te Pito Kura. Imagina Rapa Nui, the Cs/Hr/Sr Wikipedias, Lonely Planet and  |
| Purunllacta, Cheto | period_start | `field-unresolved` | Only tourism pages (e.g. a travel agency page and a heritage-portal restatement) put the Cheto Purun Llacta 'around 1100 |
| Threestoneburn Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2900 |
| Al-Rabadha | period_start | `field-unresolved` | No source gives a year, century or named period for the start of Al-Rabadha. The King Saud University museum says it eme |
| Hatun Machay | period_start | `field-unresolved` | No readable source dates the start of Hatun Machay itself. Quechuandes (a tour operator) says its carvings and paintings |
| Brisworthy Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Wednesbury | period_start | `field-unresolved` | Wikipedia only says a ditch excavated in 2008 was interpreted as possibly part of the Iron Age hillfort 'long suspected  |
| Balnuaran of Clava | lat | `moved-since-classification` | decided about 57.477915335686546, -4.224785833093299, holds 57.473115, -4.073982 |
| Anakeion | period_start | `field-unresolved` | English, German and Greek Wikipedia and ToposText (period code CHR, location 'probably E of Acropolis') give no foundati |
| Taplow | period_start | `field-unresolved` | The Wikidata item and the stored source_url are the village and civil parish of Taplow, whose English Wikipedia article  |
| Romuald's Cave | period_start | `moved-since-classification` | decided about -500, holds -300000 |
| Guyaju Caves | period_start | `field-unresolved` | No source dates the start of the Guyaju Caves (Yanqing, Beijing). English and Chinese Wikipedia say the excavation was i |
| Knin | period_start | `moved-since-classification` | decided about -500, holds -4000 |
| Kyaneai Büyük Sarnıç | lat | `coordinates-unresolved` | Lycian Monuments, the stored antalyagezirehberi.net page, the Kolb survey reports (kulturvarliklari.gov.tr PDFs) and web |
| Kyaneai Büyük Sarnıç | period_start | `field-unresolved` | Sources date the city (earliest finds 6th century BCE; Hellenistic polis) but none dates this great cistern; the stored  |
| Berry Castle, Black Dog | period_start | `moved-since-classification` | decided about -4000, holds -800 |
| Muyu Urqu | period_start | `field-unresolved` | The readable sources place Muyu Urqu (Muyu Orqo, Cusco) in the Formative Period: the abstract of Zapata 1998 (Boletin de |
| Inti Watana, Ayacucho | period_start | `moved-since-classification` | decided about 1, holds 1438 |
| Caer Bach | period_start | `field-unresolved` | No source dates Caer Bach (Rowen, Conwy, SH 7443 7297). Wikipedia calls it a hillfort of indeterminate age and says no d |
| Massleberg 1 Rock Art | period_start | `moved-since-classification` | decided about -10000, holds -2500 |
| Gavur Kalesi | period_start | `moved-since-classification` | decided about -1700, holds -1350 |
| Hatunmarka | site_type | `moved-since-classification` | decided about 'Archaeological site', holds 'City/town/settlement' |
| Hemet Maze Stone | period_start | `field-unresolved` | English Wikipedia calls the Hemet Maze Stone only 'a prehistoric petroglyph' of the California Tradition and gives no da |
| Lagina | period_start | `field-unresolved` | Reputable sources disagree on when Lagina begins: the English Wikipedia article says both that the site was inhabited fr |
| Box Gully Archaeological Site | period_start | `moved-since-classification` | decided about -500, holds -30050 |
| Huichún | lat | `coordinates-unresolved` | English Wikipedia places Huichun only relative to Cochamarca and Obas ({{coord missing|Peru}}), Wikidata Q17104607 has n |
| Giridava | period_start | `field-unresolved` | The English Wikipedia stub only calls Giridava a Dacian town in Moesia in northern Bulgaria and gives no foundation or o |
| The Knave | period_start | `moved-since-classification` | decided about -200, holds -800 |
| Emblance Downs Stone Circles | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Teatro Romano | period_start | `field-unresolved` | English, Italian and French Wikipedia (one source family) date the Aosta theatre only to 'some decades after the foundat |
| Kitanaura Antik Kenti | period_start | `moved-since-classification` | decided about 1, holds -323 |
| Kudaro | lat | `moved-since-classification` | decided about 42.190763629610124, 43.438469873003335, holds 42.519722, 43.634167 |
| Yarrows Broch | period_start | `moved-since-classification` | decided about 800, holds -100 |
| Svileuva | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0039): Both pages date the Roman presence of Svileuva to the 1st to 4th |
| Taula | lat | `coordinates-unresolved` | The English Wikipedia article 'Taula' describes a type of stone monument found across Menorca (it lists some thirty taul |
| Taula | period_start | `field-unresolved` | The article dates the taulas as a class of monuments ('built by the Talaiotic culture between 500 BC and 300 BC'), and t |
| Ljuljaci | lat | `coordinates-unresolved` | The site is the group of prehistoric tumuli excavated by Srejovic near the village of Ljuljaci (Knic municipality). The  |
| Ljuljaci | period_start | `field-unresolved` | Reputable sources disagree on the Ljuljaci tumuli: English Wikipedia (Ljuljaci) calls them prehistoric Bronze Age tumuli |
| Deer Valley Petroglyph Preserve | period_start | `moved-since-classification` | decided about -10000, holds -3050 |
| Huaca Esmeralda | period_start | `field-unresolved` | Every page found says only that Huaca Esmeralda is Chimú and built in the culture's first stage (English and Spanish Wik |
| Nyons | period_start | `field-unresolved` | Nyons is a commune of the Drome whose English Wikipedia article gives no history or date. The French Wikipedia leaves it |
| Sliprännor i Gantofta | period_start | `field-unresolved` | The Gantofta grinding grooves (RAA Kvistofta 4:1, Helsingborg) are undated: English Wikipedia says there is as yet no ce |
| Yelland Stone Rows | period_start | `moved-since-classification` | decided about -4000, holds -2550 |
| Żukczyn | period_start | `moved-since-classification` | decided about -3000, holds -800 |
| Leaze Stone Circle | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Heelstone Ditch | period_start | `field-unresolved` | No readable source dates the Heelstone Ditch: Wikipedia's article, the Stonehenge article, English Heritage's pages and  |
| Clandon Barrow | period_start | `moved-since-classification` | decided about -4000, holds -2500 |
| Costa Beck | lat | `coordinates-unresolved` | The only printed point (Wikipedia and Wikidata 54.256, -0.794) is the river Costa Beck at its source at Keld Head, not t |
| Costa Beck | period_start | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0010): The Costa Beck quote only says Iron Age and Romano-British, but  |
| Redbourn | period_start | `field-unresolved` | Redbourn is a village; the only statements on its age (settled 'at least since Saxon times', recorded in Domesday 1086,  |
| Dragon Hill, Uffington | period_start | `field-unresolved` | No source dates the start of Dragon Hill. Wikipedia only says it 'has been suggested as some sort of Iron Age ritual sit |
| Round Loaf | period_start | `field-unresolved` | Wikipedia's 'Late Neolithic or Bronze Age' and '2400 - 1500 BC' come from the general scheduling text for the monument c |
| Karta | lat | `coordinates-unresolved` | Karta is the Aboriginal name of Kangaroo Island (English Wikipedia: 'Known as (Karta) Pintingga (Island of the Dead) by  |
| Karta | period_start | `field-unresolved` | The only dated statement about Karta/Kangaroo Island is that the island separated from the mainland around 10,000 years  |
| Wamanmarka, Chumbivilcas | lat | `coordinates-unresolved` | English Wikipedia's Wamanmarka has an empty coordinates field and Wikidata Q15950045 has no P625. The tourism-inventory  |
| Wamanmarka, Chumbivilcas | period_start | `field-unresolved` | The only readable description (tourism inventory record of the MINCETUR) says the site had Collao and Wari influence, ha |
| Munigua | period_start | `moved-since-classification` | decided about -700, holds -400 |
| Naupa Iglesia (Choquequilla) | period_start | `moved-since-classification` | decided about 500, holds 1438 |
| Sancreed Beacon | period_start | `moved-since-classification` | decided about -4500, holds -2500 |
| Huilai Monument Archaeology Park | site_type | `field-unresolved` | adversarial reject (round 0, adversarial:adv-r0-b0043): The same page and the Wikipedia article name the entity an archa |
| Satsurblia Cave | period_start | `moved-since-classification` | decided about -500, holds -23550 |
| Nausharo | site_type | `field-unresolved` | no counted answer in 3 rounds: quote not found: https://pmc.ncbi.nlm.nih.gov/articles/PMC7643715/; quote not found: http |
| Teotihuacan - Palace Atelelco | period_start | `field-unresolved` | The stored source page (UNAM Aragon) describes the Atetelco compound without a date, and the INAH and travel pages dated |
| Yuraq Mach'ay | period_start | `field-unresolved` | The English Wikipedia article (and Wikidata item) give no date for Yuraq Mach'ay in Pasco; searches for the MINCETUR inv |
| Aves Ditch | period_start | `moved-since-classification` | decided about -4000, holds -100 |
| Accua | lat | `coordinates-unresolved` | English Wikipedia says Accua's 'exact site is unknown' (only Livy mentions it, near Luceria); Pleiades place 446208 (Wik |
| Accua | period_start | `field-unresolved` | The only dated mention is Livy's report of Accua among the places recovered in 214 BCE, which is a historical attestatio |
| Likya Anıt Mezar | lat | `coordinates-unresolved` | The entry's name 'Likya Anıt Mezar' does not fix which Fethiye monument it means. The stored point (36.6231, 29.1137) li |
| Likya Anıt Mezar | source_url | `field-unresolved` | The stored Kültür Portalı page is about the Amintas rock tombs of Fethiye; since no page establishes that the entry 'Lik |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25p_fields-wd5-s002-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25p-s002 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
