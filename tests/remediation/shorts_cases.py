"""Fixtures of contract shorts-v1: the eleven pilot sites of the card design (2026-10-08) with their
live descriptions and the sample card the design judge selected for each.

The descriptions are byte for byte what `output/remediation/state-2026-10-08/pilot_sites.json` holds
(a read-only SELECT of 2026-10-08, markers included), pinned here as fixtures: the live texts will be
repaired and enriched, and a test must not move with them. `live_card` is the card production held
that day. `card` is the design's sample (`teaser_design_digest.md`, "best samples"), changed only
where the shorts-v1 code refused a word (`only` and `Alpine` are not in the description of Vallee des
Merveilles); `anchors`, `reserve` and `hook_type` are what a writer would answer with it, and
`pool_images` the number of usable images (non-excluded, short side >= 900, aspect <= 2.0) the design
measured: six sites are Shorts-eligible, five are not.

A name here is the site's stored name; `aliases` are names the catalogue can store for it (the
description's own alternative names, and the spellings a search would use).
"""

from __future__ import annotations

from typing import Any

SAMPLES: tuple[dict[str, Any], ...] = (
    {
        "site_id": "37507863-e875-4192-a739-b06980f79e1b",
        "name": "Glaphyrae",
        "country": "Greece",
        "site_type": "City/town/settlement",
        "description": "Glaphyrae was a settlement in Magnesia, ancient Thessaly, Greece, mentioned "
        "by Homer in the Catalogue of Ships alongside Boebe and Iolcus [1] [2]. After "
        "this reference, the town does not appear in subsequent historical records [1] "
        "[2]. In the 19th century, William Martin Leake identified the site with "
        "Hellenic ruins on a hill above modern Glafira, between Boebe and Iolcus, an "
        "identification accepted by modern scholars [1] [2] [3]. At the time of "
        "Leake's visit, the entire circuit of the citadel on the hill summit remained "
        "visible [1] [2].",
        "live_card": "A town mentioned in Homer's Catalogue of Ships alongside Boebe and Iolcus. "
        "After Homer, its name vanishes entirely from the historical record.",
        "card": "Homer names this town in his Catalogue of Ships, and then the records fall silent. "
        "In the 19th century, the whole circuit of its citadel was still visible on a hill "
        "between Boebe and Iolcus.",
        "basis": ["S1", "S2", "S3", "S4"],
        "anchors": [],
        "reserve": ["reveal"],
        "hook_type": "person",
        "pool_images": 0,
        "aliases": [],
    },
    {
        "site_id": "5614b867-438c-4c38-9a43-e2d04abe6dc0",
        "name": "Vallée des Merveilles",
        "country": "France",
        "site_type": "Petroglyphs",
        "description": "The Vallée des Merveilles, also known in Italian as the Valle delle "
        "Meraviglie, is a part of the Mercantour National Park in southern France [1]. "
        "It holds the largest quantity of open-air Bronze Age petroglyphs in Europe, "
        "after Val Camonica in Italy [1]. The valley is located near the Italian "
        "border, in the rugged mountains of the Argentera massif within the Maritime "
        "Alps, between Saint-Martin-Vésubie and Tende [1]. The petroglyphs (rock "
        "engravings), located on stone outcrops within the valley, were first "
        "identified by British amateur archaeologist Clarence Bicknell in 1881 [1]. "
        "Between 1897 and 1902, Bicknell copied and catalogued more than 10,000 "
        "drawings [1]. Suns, stars and spirals are represented [1]. Some "
        "anthropomorphic figures have been found [1].",
        "live_card": "Bronze Age suns, stars and spirals are engraved on the stone outcrops of the "
        "Vallée des Merveilles, in the rugged Maritime Alps, where Clarence Bicknell "
        "catalogued more than 10,000 drawings.",
        "card": "Suns, stars and spirals are engraved on rock outcrops in a mountain valley. One "
        "place in Europe holds more open-air Bronze Age engravings, and an amateur copied "
        "over 10,000 drawings.",
        "basis": ["S2", "S5", "S6"],
        "anchors": ["rock outcrops", "open-air Bronze Age engravings"],
        "reserve": ["S4"],
        "hook_type": "object",
        "pool_images": 9,
        "aliases": [],
    },
    {
        "site_id": "22415177-5658-4973-ab15-ddad22663cde",
        "name": "Huaca del Sol",
        "country": "Peru",
        "site_type": "Pyramid complex",
        "description": "The Huaca del Sol is an adobe brick pyramid built by the Moche civilization "
        "(100 AD to 800 AD) on the northern coast of what is now Peru [1]. By 450 AD, "
        "eight different stages of construction had been completed on the Huaca del "
        "Sol [1]. Archeologists have estimated that the Huaca del Sol was composed of "
        "over 130 million adobe bricks and was the largest pre-Columbian adobe "
        "structure built in the Americas [1]. The Huaca del Sol was composed of four "
        "main levels [1]. During the Spanish occupation of Peru in the early 17th "
        "century, colonists redirected the waters of the Moche River to run past the "
        "base of the Huaca del Sol in order to facilitate the looting of gold "
        "artifacts from the temple [1].",
        "live_card": "Archaeologists estimate over 130 million adobe bricks went into the Huaca del "
        "Sol, a Moche pyramid. In the early 17th century, colonists turned the Moche "
        "River past its base to loot gold.",
        "card": "To help loot its gold, colonists made a river run past this Moche pyramid. By one "
        "estimate it took over 130 million adobe bricks: the largest adobe structure of the "
        "Americas before Columbus.",
        "basis": ["S3", "S5"],
        "anchors": ["Moche pyramid", "130 million adobe bricks"],
        "reserve": ["S2"],
        "hook_type": "act",
        "pool_images": 7,
        "aliases": [],
    },
    {
        "site_id": "6153e9bc-e4b8-468f-8328-878ba9ebd02f",
        "name": "Intiyuq K'uchu",
        "country": "Peru",
        "site_type": "Rock art",
        "description": "Intiyuq K'uchu (or Pintasqa Wayq'u) is an archaeological site in Peru with "
        "rock paintings [1]. It is located in the Cusco Region, Calca Province, Lamay "
        "District [1]. Intiyuq K'uchu is situated at a height of about 3,800 metres "
        "[1]. Inti means sun; -yuq is a suffix that denotes ownership; k'uchu means "
        '"corner" [1].',
        "live_card": "Rock paintings wait at Intiyuq K'uchu, about 3,800 metres up in the Lamay "
        "District of the Cusco Region, at a place whose name joins the words for sun and "
        "corner.",
        "card": "About 3,800 metres up, rock paintings mark a place with a name to decode. It starts "
        "with the word for sun, adds a suffix that means ownership, and ends with the word "
        "for corner.",
        "basis": ["S3", "S4"],
        "anchors": [],
        "reserve": ["reveal"],
        "hook_type": "number",
        "pool_images": 0,
        "aliases": ["Pintasqa Wayq'u"],
    },
    {
        "site_id": "5f9bc540-443e-41d6-93af-9c65dd28673b",
        "name": "Anta de Carcavelos",
        "country": "Portugal",
        "site_type": "Dolmen",
        "description": "The Anta de Carcavelos, located close to the village of Carcavelos near the "
        "town of Lousa in the municipality of Loures in the Lisbon District of "
        "Portugal, is a stone age dolmen or megalithic monument from the Chalcolithic "
        "period [1]. The Anta was a communal grave consisting of a sepulchral chamber "
        "with a polygonal shape [1]. The remains of the tomb consist of six cretaceous "
        "limestone slabs that originated in the area, which has several sizeable "
        "limestone outcrops [1]. Hastened as a result of looting at the site, the "
        "first excavations were carried out in 1986 and continued again from 1991-1994 "
        "[1]. From the studies carried out in 1994, many bones were collected, with "
        "over 80 adult males and females believed to have been buried there [1]. "
        "Various objects were also found such as flint arrowheads, smooth and "
        "decorated bell-shaped ceramics, dishes, cylindrical idols, and objects of "
        "adornment [1]. The evaluation of items found suggested a probable initial use "
        "of the dolmen as being in the last centuries of the 4th millennium BCE, with "
        "an intensification in its use between 3000 and 2600 BCE [1].",
        "live_card": "Six limestone slabs remain of the Anta de Carcavelos, a Chalcolithic communal "
        "grave. Over 80 adults are believed buried here, and flint arrowheads and "
        "cylindrical idols were found.",
        "card": "Over 80 men and women are believed to have been buried in one stone chamber. Looting "
        "hurried the first dig, and the finds include flint arrowheads, bell-shaped pottery "
        "and cylindrical idols.",
        "basis": ["S4", "S5", "S6"],
        "anchors": [],
        "reserve": ["S7"],
        "hook_type": "number",
        "pool_images": 1,
        "aliases": [],
    },
    {
        "site_id": "274ff0f7-d0f7-4f66-8c73-43cf53c895e9",
        "name": "Medinet Habu",
        "country": "Egypt",
        "site_type": "Temple complex",
        "description": "Medinet Habu is an archaeological locality situated near the foot of the "
        "Theban Hills on the West Bank of the River Nile opposite the modern city of "
        "Luxor, Egypt [1]. A Prussian expedition led by Karl Richard Lepsius worked in "
        "Thebes, mainly at Medinet Habu, from November 1844 until April 1845 [1]. The "
        "memorial temple of Ramesses III at Medinet Habu contains a minor list of "
        "pharaohs of the New Kingdom of Egypt [1]. The Coptic settlement at Medinet "
        "Habu was established as the final stage of a continuous process of occupation "
        "of the mortuary complex of Ramses III, which began in pharaonic times and "
        "continued into the Roman and late antique period [1].",
        "live_card": "Near the foot of the Theban Hills, across the Nile from Luxor, Medinet Habu "
        "keeps the temple of Ramesses III and its list of pharaohs, lived in from "
        "pharaonic times to a Coptic settlement.",
        "card": "From the pharaohs to the Romans, people kept living in this temple complex. It "
        "belonged to Ramesses the Third, holds a minor list of New Kingdom pharaohs, and "
        "ended as a Coptic settlement.",
        "basis": ["S3", "S4"],
        "anchors": ["temple complex", "list of New Kingdom pharaohs"],
        "reserve": ["S2"],
        "hook_type": "act",
        "pool_images": 8,
        "aliases": [],
    },
    {
        "site_id": "4f366f34-983c-42e1-a89d-7e8f5f77cdce",
        "name": "Machu Picchu",
        "country": "Peru",
        "site_type": "City/town/settlement",
        "description": "Machu Picchu is a 15th-century Inca citadel located in the Eastern Cordillera "
        "of southern Peru on a mountain ridge at 2,430 meters [1]. Studies of skeletal "
        "remains found at Machu Picchu show that most people who lived there were "
        "immigrants from diverse backgrounds [1]. Excavations documented approximately "
        "104 caves and rock shelters used as burial chambers around Machu Picchu, "
        "containing the remains of about 174 individuals, interpreted as largely "
        "belonging to yanaconas of diverse ethnic origins rather than the Inca elite "
        "[1]. Radiocarbon dating analyses have refined the site's chronology, "
        "indicating that Machu Picchu’s main construction and use fall in the early to "
        "mid 15th century, slightly earlier than some traditional documentary "
        "chronologies suggest [1]. The central buildings of Machu Picchu are built in "
        "classical Inca dry masonry, with large blocks precisely shaped through "
        "quarrying, stone-cutting, and stone-dressing, then fitted together without "
        "mortar [1]. Machu Picchu was connected to the Inca road system and "
        "long-distance trade, as shown by obsidian nodules found near the site’s "
        "entrance [1].",
        "live_card": "At 2,430 meters, about 104 caves and rock shelters around Machu Picchu held the "
        "remains of about 174 individuals, interpreted largely as yanaconas rather than "
        "the Inca elite.",
        "card": "Bones found here show that most people living in this Inca citadel were immigrants. "
        "Its central buildings are made of precisely shaped stone blocks, fitted together "
        "without mortar.",
        "basis": ["S2", "S5"],
        "anchors": ["Inca citadel", "precisely shaped stone blocks"],
        "reserve": ["S3"],
        "hook_type": "object",
        "pool_images": 14,
        "aliases": ["Machu Pichu"],
    },
    {
        "site_id": "d953e9b3-de33-4c7d-9357-bbc5d94d2a16",
        "name": "Göbekli Tepe",
        "country": "Türkiye",
        "site_type": "Megalithic structures",
        "description": "Göbekli Tepe is a Neolithic archaeological site in Upper Mesopotamia in "
        "modern-day Turkey [1]. Göbekli Tepe is near the village of Örencik in "
        "Şanliurfa Province in the Taş Tepeler, in the foothills of the Taurus "
        "Mountains [1]. Like most Pre-Pottery Neolithic sites in the Urfa region, "
        "Göbekli Tepe was built at a high point on the edge of the mountains, giving "
        "it a wide view over the plain beneath and good visibility from the plain [1]. "
        "Göbekli Tepe was built and occupied during the earliest part of the Southwest "
        "Asian Neolithic, known as the Pre-Pottery Neolithic (PPN, c.\u20099600–7000 "
        "BCE) [1]. The earliest phases at Göbekli Tepe have been dated to the PPNA; "
        "later phases to the PPNB [1]. Radiocarbon dating shows that the earliest "
        "exposed structures at Göbekli Tepe were built between 9500 and 9000 BCE, "
        "towards the end of the Pre-Pottery Neolithic A period [1]. Göbekli Tepe is "
        "littered with flint artifacts [1]. The stone pillars in the enclosures at "
        "Göbekli Tepe are T-shaped [1].",
        "live_card": "Göbekli Tepe, littered with flint, sets T-shaped stone pillars in its "
        "enclosures high on the edge of the Taurus foothills. Its earliest exposed "
        "structures rose between 9500 and 9000 BCE.",
        "card": "T-shaped stone pillars stand in enclosures on a high point above a plain. "
        "Radiocarbon dating shows its earliest exposed structures rose between 9500 and 9000 "
        "BCE.",
        "basis": ["S3", "S6", "S8"],
        "anchors": ["high point above a plain", "earliest exposed structures"],
        "reserve": ["S7"],
        "hook_type": "object",
        "pool_images": 12,
        "aliases": ["Gobekli Tepe", "Göbeklitepe"],
    },
    {
        "site_id": "0a82ea91-7f4e-4f1c-89c8-2e1115c1176c",
        "name": "Tregiffian Burial Chamber",
        "country": "England",
        "site_type": "Tomb",
        "description": "The Tregiffian Burial Chamber is a Neolithic or early Bronze Age chambered "
        "cairn located near Lamorna in west Cornwall, England [1] [2]. It is a rare "
        "type of passage grave known as an Entrance grave, featuring an entrance "
        "passage lined with stone slabs that leads into a central chamber [1] [3].",
        "live_card": "A rare entrance grave from ~4000 BC with a stone-lined passage leading to a "
        "central chamber. This tomb type is found almost exclusively in far western "
        "Cornwall and the Scilly Isles.",
        "card": "A passage lined with stone slabs leads into a central chamber for the dead. Built in "
        "the Neolithic or early Bronze Age, it is a rare kind of passage grave called an "
        "entrance grave.",
        "basis": ["S1", "S2"],
        "anchors": [],
        "reserve": None,
        "hook_type": "object",
        "pool_images": 5,
        "aliases": [],
    },
    {
        "site_id": "fead42ae-fdd5-48d1-bcc9-567c1c7873b8",
        "name": "Denbury Hill",
        "country": "England",
        "site_type": "Fortress/citadel",
        "description": "Denbury Hill (also known as Denbury Camp and Denbury Down) is the name of an "
        "Iron Age hill fort near the village of Denbury in Devon, England [1]. The "
        "fort is less than a kilometre south west of the village, occupying the entire "
        "hilltop of Denbury Down at 160 metres above sea level [1]. It is surrounded "
        "on the south and east sides by high embankments [1]. In the centre of the "
        "enclosure there are two large burial mounds [1].",
        "live_card": "Filling the entire hilltop of Denbury Down at 160 metres, the Iron Age hill "
        "fort of Denbury Hill has high embankments on its south and east sides and large "
        "burial mounds at its centre.",
        "card": "Two large burial mounds lie at the centre of an Iron Age hill fort. The fort fills "
        "an entire hilltop, 160 metres above sea level, and high banks rise along its south "
        "and east sides.",
        "basis": ["S1", "S2", "S3", "S4"],
        "anchors": [],
        "reserve": None,
        "hook_type": "object",
        "pool_images": 4,
        "aliases": ["Denbury Camp", "Denbury Down"],
    },
    {
        "site_id": "0ed41363-8709-42cc-a676-7cb76e3440bf",
        "name": "Mitla, Entrance to Tomb 1",
        "country": "Mexico",
        "site_type": "Tomb",
        "description": "Tomb 1 at Mitla is located within the Group of Columns, accessible via the "
        "patio in front of the northern building's staircase [1] [2] [3]. The tomb "
        "features a cruciform plan, roofed by massive monolithic stone lintels [3]. "
        "Its inner walls are decorated with the same geometric mosaic fretwork (greca "
        "friezes) found on the exterior buildings, with small polished stones fitted "
        'without mortar [3] [4]. The tomb also contains the famous "Column of Life" '
        "[1] [3].",
        "live_card": "The entrance to an ancient tomb at Mitla, the most sacred Zapotec burial site. "
        "Priests descended into underground chambers to inter rulers and communicate "
        "with the dead.",
        "card": "Massive stone lintels, each a single block, roof a tomb shaped like a cross. Its "
        "inner walls repeat the fretwork of the buildings outside, in small polished stones "
        "fitted without mortar.",
        "basis": ["S2", "S3"],
        "anchors": ["tomb shaped like a cross", "fretwork"],
        "reserve": ["S4"],
        "hook_type": "object",
        "pool_images": 6,
        "aliases": [],
    },
)

#: Two more clean variants for five of the sites: a writer answers three variants that differ in
#: their first three words, so an end-to-end run needs them (the sample card is the first).
EXTRA_VARIANTS: dict[str, list[dict[str, Any]]] = {
    "Machu Picchu": [
        {
            "card": "Obsidian nodules near its entrance reveal a citadel tied to "
            "long-distance trade. Its central buildings use large blocks, "
            "precisely shaped and fitted together without mortar.",
            "basis": ["S5", "S6"],
            "anchors": ["long-distance trade", "large blocks, precisely shaped"],
            "reserve": ["S2"],
            "hook_type": "object",
        },
        {
            "card": "About 174 people lay in the caves and rock shelters around this "
            "mountain ridge. Inca masons fitted the central buildings of this "
            "citadel together without mortar.",
            "basis": ["S3", "S5"],
            "anchors": ["mountain ridge", "central buildings"],
            "reserve": ["S4"],
            "hook_type": "number",
        },
    ],
    "Huaca del Sol": [
        {
            "card": "Eight stages of construction had been completed by 450 AD on this "
            "adobe pyramid. Over 130 million bricks went into it, and "
            "colonists later diverted a river past its base.",
            "basis": ["S1", "S2", "S3", "S5"],
            "anchors": ["adobe pyramid", "a river past its base"],
            "reserve": ["S4"],
            "hook_type": "number",
        },
        {
            "card": "A river was turned from its course so colonists could loot gold "
            "from a temple. The Moche built that temple, an adobe pyramid of "
            "four main levels, long before the Spanish came.",
            "basis": ["S1", "S4", "S5"],
            "anchors": ["from a temple", "adobe pyramid"],
            "reserve": ["S2"],
            "hook_type": "act",
        },
    ],
    "Glaphyrae": [
        {
            "card": "Boebe and Iolcus share a line with it in Homer's Catalogue of Ships. "
            "Later records never mention it again, but in the 19th century William "
            "Martin Leake found its ruins on a hill.",
            "basis": ["S1", "S2", "S3"],
            "anchors": [],
            "reserve": ["reveal"],
            "hook_type": "person",
        },
        {
            "card": "A whole citadel circuit still showed on a hill summit in the 19th "
            "century. Homer had listed the town in his Catalogue of Ships, yet no "
            "later record mentions it.",
            "basis": ["S1", "S2", "S3", "S4"],
            "anchors": [],
            "reserve": ["reveal"],
            "hook_type": "object",
        },
    ],
    "Tregiffian Burial Chamber": [
        {
            "card": "Stone slabs line a passage into a central chamber of "
            "an entrance grave. This rare kind of passage grave "
            "stands in the Neolithic or early Bronze Age, near "
            "Lamorna in west Cornwall.",
            "basis": ["S1", "S2"],
            "anchors": [],
            "reserve": None,
            "hook_type": "object",
        },
        {
            "card": "Archaeologists place this chambered cairn in the "
            "Neolithic or early Bronze Age. Its entrance passage, "
            "lined with stone slabs, leads into a single central "
            "chamber in west Cornwall.",
            "basis": ["S1", "S2"],
            "anchors": [],
            "reserve": None,
            "hook_type": "object",
        },
    ],
    "Denbury Hill": [
        {
            "card": "High banks wrap the south and east sides of a hilltop 160 metres "
            "above sea level. Inside the enclosure, two large burial mounds "
            "mark the centre of an Iron Age hill fort.",
            "basis": ["S1", "S2", "S3", "S4"],
            "anchors": [],
            "reserve": None,
            "hook_type": "object",
        },
        {
            "card": "Just below the village, an entire hilltop was turned into an Iron "
            "Age fort. Its south and east sides are ringed by high embankments, "
            "and two large burial mounds sit at the centre.",
            "basis": ["S1", "S2", "S3", "S4"],
            "anchors": [],
            "reserve": None,
            "hook_type": "act",
        },
    ],
}

BY_NAME: dict[str, dict[str, Any]] = {sample["name"]: sample for sample in SAMPLES}
ELIGIBLE = tuple(s["name"] for s in SAMPLES if s["pool_images"] >= 6)
