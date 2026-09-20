"""Emit PILOT.jsonl — one record per (site, field) for the five-site Phase 3 pilot.

Every evidence entry names a fetch by its `label` in fetch_log.jsonl; url and
retrieved_at are read from that log so the two can never drift apart.  Quotes are
verbatim excerpts of the saved body under evidence/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
LOG = HERE / "fetch_log.jsonl"

_missing: set[str] = set()


def ev(label: str, source: str, quote: str) -> dict:
    """One evidence item, resolved against the fetch log."""
    for line in LOG.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["label"] == label:
            return {
                "source": source,
                "url": row["url"],
                "quote": quote,
                "retrieved_at": row["at"],
                "fetch_log_label": label,
                "http_status": row["http"],
            }
    _missing.add(label)
    raise KeyError(f"{label} not in fetch_log.jsonl")


WD_SATS = ev(
    "Satsurblia/wikidata",
    "Wikidata Q28220554",
    "P625 = Point(42.388111, 42.606167) with precision 0.01216; P17 = Q230",
)
EN_SATS = ev(
    "Satsurblia/enwiki",
    "Wikipedia 'Satsurblia Cave'",
    "paleoanthropological site ... 1.2 km from Kumistavi ... 287 meters above sea level; occupied ~25,500-24,400 BP",
)
KA_SATS = ev(
    "Satsurblia/kawiki",
    "Georgian Wikipedia 'საწურბლიას მღვიმე'",
    "საწურბლიას მღვიმე — კარსტული მღვიმე საქართველოში, წყალტუბოს მუნიციპალიტეტში, სოფელ ყუმისთავთან. ... სიგრძე 125–130 მ. ფსკერის ფართობი 1950 მ², მოცულობა 8100 მ³ (no coordinates in the page; gives the elevation as 270 m where enwiki and showcaves say 287 m)",
)
PLOS = ev(
    "Satsurblia/plos_article",
    "Pinhasi et al., PLOS ONE 10(10):e111271 (2014)",
    "The layer is dated to 25,535-24,408 cal. BP (95.4% confidence interval)",
)
SHOWCAVES = ev(
    "Satsurblia/showcaves",
    "showcaves.com",
    "Location: Village Kumistavi, Tskaltubo Municipality. (42.387795, 42.606163) ... L=130 m, A=287 m asl.",
)
GEONAMES_SATS = ev(
    "Satsurblia/geonames",
    "GeoNames search 'Satsurblia'",
    "Satsurblia Cave -> Lat/Lng 42.3772 / 42.6009",
)
OSM_SATS = ev(
    "Satsurblia/osm_bbox",
    "OpenStreetMap API map bbox (raw geometry)",
    "node 'საწურბლიას მღვიმე' (name:en Satsurblia Cave, natural=cave_entrance) at 42.39647,42.58902; way 'პრომეთეს მღვიმე' (Prometheus Cave Visitors Center & Tickets) centroid 42.37685,42.60074; node 'Prometheus Cave Exit' 42.37659,42.60095",
)
NATPARK = ev(
    "Satsurblia/nationalparks",
    "nationalparks.ge (Agency of Protected Areas)",
    "Satsurblia Cave Natural Monument ... Location: Tskaltubo Municipal[ity]",
)
TTS = (
    "pipeline/video/shorts_tts.py:21-23 — specific_place(country) returns the text after the "
    "last comma, so 'Georgia (country)' is spoken in full"
)

WD_PET = ev(
    "Petroglyph/wikidata",
    "Wikidata Q7178910",
    "P625 = Point(58.301061, -134.413121); P17 = Q30 (USA)",
)
EN_PET = ev(
    "Petroglyph/enwiki",
    "Wikipedia 'Petroglyph Beach State Historic Park'",
    "Located on the shore of Wrangell, Alaska barely a mile out of town, it became a State Historic Park in 2000. At least 40 petroglyphs have been found to date. The site itself is about 8000 years old.",
)
WIKITEXT_PET = ev(
    "Petroglyph/enwiki_wikitext",
    "Wikipedia wikitext of the same page",
    "{{Coord|58.301061|-134.413121}}",
)
ASP_PET = ev(
    "Petroglyph/ak_state_parks_wrang",
    "Alaska DNR, Division of Parks & Outdoor Recreation",
    "Petroglyph Beach in Wrangell has the highest concentration of petroglyphs in the southeast region of Alaska. The beach is a little over a mile out of town, and became a State Historic Park in 2000. At least 40 petroglyphs have been found in the area. The site itself is about 8000 years old. ... Address: Grave Street, Wrangell. Driving Directions: 1 mile from the ferry terminal.",
)
OSM_PET = ev(
    "Petroglyph/osm_bbox",
    "OpenStreetMap API map bbox (raw geometry)",
    "Grave Street ways in Wrangell: centroids 56.48134/-132.39086, 56.48283/-132.38953, 56.48286/-132.39254 (the stored point 56.48287/-132.39350 is on Grave Street)",
)
OVERPASS_PET_FEAT = ev(
    "Petroglyph/overpass_stored_features",
    "Overpass API, named features within 600 m of the stored point",
    "Grave Street, Graves Street, Third Avenue, 4th Avenue, 5th Avenue, Stough's Trailer Court Road - Wrangell street grid, no other named feature",
)
OVERPASS_JUNEAU = ev(
    "Petroglyph/overpass_juneau",
    "Overpass API around the Wikidata point",
    "place node 'Juneau' at 58.3019613,-134.4196751, 0.4 km from the Wikidata/Wikipedia coordinate",
)
GEONAMES_PET = ev(
    "Petroglyph/geonames_search",
    "GeoNames search 'Petroglyph Beach' (US)",
    "Petroglyph Beach State Historic Park -> 58.3011 / -134.4131, i.e. the same point as Wikipedia (derived, not independent)",
)

WD_PAN = ev(
    "Pannonian/wikidata",
    "Wikidata Q471153",
    "en label 'Pannonian Limes', description 'Roman fortified frontier'; P17 = Q40 (Austria); NO P625",
)
EN_PAN = ev(
    "Pannonian/enwiki_danubian",
    "Wikipedia 'Pannonian Limes' / 'Danubian Limes'",
    "section of the Roman Danubian frontier across Austria, Slovakia, Hungary, Croatia and Serbia",
)
HR_PAN = ev(
    "Pannonian/hrwiki_panonski",
    "Croatian Wikipedia 'Panonski limes'",
    "sjeverni dio dunavskog limesa; 420 km ... od Klosterneuburga u današnjoj Austriji do Beograda (Singidunum)",
)
LIMESCRO = ev(
    "Pannonian/limescroatia_unesco",
    "Archaeological Museum Osijek, limescroatia.eu",
    "Lokaliteti: Osječko-baranjska županija Batina, Zmajevac, Kneževi Vinogradi, Lug, Kopačevo, Bilje, Osijek - Donji grad, Dalj ... Vukovarsko-srijemska županija Sotin, Ilok",
)
DANUBE = ev(
    "Pannonian/overpass_danube",
    "Overpass API, Danube geometry within 120 km of the stored point",
    "nearest way 'Дунав' 82.7 km away (44.7437, 20.9918)",
)
OVER_PAN_PT = ev(
    "Pannonian/overpass_stored_point2",
    "Overpass API around the stored point",
    "nearest place node: village Јабучје 43.99911,20.99020, ~1 km",
)

WD_KAR = ev(
    "Karpasia/wikidata",
    "Wikidata Q1734309",
    "P625 = Point(35.61994444, 34.35175); P17 = Q229 (Cyprus); P31 = Q486972 human settlement, Q15661340 ancient city, Q148837 polis; P1584 = Pleiades 707526",
)
EN_KAR = ev(
    "Karpasia/enwiki",
    "Wikipedia 'Karpasia (town)'",
    "ancient Cypriot town on the northern Karpas peninsula, 3 km from modern Rizokarpaso; founded (by tradition) by the Phoenician king Pygmalion of Tyre; image caption 'Ayios Philon Church, situated at the site of Karpasia'",
)
WIKITEXT_KAR = ev(
    "Karpasia/enwiki_wikitext",
    "Wikipedia wikitext of the same page",
    "{{coord|35|35|47|N|34|22|41|E}} = 35.59639, 34.37806 — the stored point",
)
PLEIADES = ev(
    "Karpasia/pleiades_707526",
    "Pleiades 707526 (Karpasia)",
    "DARMC representative point 35.626206/34.369934; types settlement, port; Roman, Hellenistic, Classical, Archaic periods",
)
PRINCETON = ev(
    "Karpasia/perseus_princeton",
    "Princeton Encyclopedia of Classical Sites (Perseus)",
    "entry title: 'KARPASIA (Haghios Philon) Cyprus'",
)
OVERPASS_KAR = ev(
    "Karpasia/overpass_site",
    "Overpass API, 'Philon' features within 6 km",
    "node 2649148733 'Ayios Philon Roman harbor' (historic=archaeological_site) at 35.63473,34.39794, 4.60 km from the stored point",
)
WD_ZENO = ev(
    "Karpasia/wd_zeno",
    "Wikidata Q171303 (Zeno of Citium)",
    "P19 (place of birth) = Q1743884; P27 (citizenship) = Q1743884; P569 = -0334",
)
WD_KITION = ev(
    "Karpasia/wd_kition_label",
    "Wikidata Q1743884",
    "en label 'Kition', description 'ancient Phoenician city and kingdom in Cyprus'",
)
DDG_KAR = ev(
    "Karpasia/britannica_zeno",
    "britannica.com (BLOCKED, 403 - recorded as untried evidence)",
    "Cloudflare challenge page, no content; the Zeno/Kition claim rests on Wikidata P19/P27 and the Kition label fetched separately",
)
SEP_KAR = ev(
    "Karpasia/sep_zeno",
    "plato.stanford.edu/entries/zeno-citium/ (unusable: 380 bytes, JS shell)",
    "380 bytes of a JS shell - the encyclopaedia entry never arrived, so it is recorded as a failed probe, not as evidence",
)
IEP_KAR = ev(
    "Karpasia/iep_zeno",
    "iep.utm.edu/zeno/ (unusable: serves an unrelated article)",
    "HTTP 200 but the page is 'liar_paradox | Internet Encyclopedia of Philosophy'; the words Citium, Kition, Cyprus and Larnaca do not occur in its 24,973 bytes",
)

WD_DID = ev(
    "Didnauri/wikidata",
    "Wikidata Q26001314",
    "P625 = Point(41.43, 46.1953) with precision 2.78e-06",
)
EN_DID = ev(
    "Didnauri/enwiki",
    "Wikipedia 'Didnauri'",
    "Late Bronze Age/Early Iron Age settlement on the Shiraki Plain, Dedoplistsqaro municipality, discovered 2014; dated to the 12th-9th centuries BC by the Georgian team; '1.5 km defensive wall'; National Agency: largest ancient settlement in the South Caucasus",
)
WIKITEXT_DID = ev(
    "Didnauri/enwiki_wikitext",
    "Wikipedia wikitext of the same page",
    "infobox coord 41°24'53\"N 46°13'23\"E = 41.414722, 46.223056 — the stored point",
)
OSM_DID_NE = ev(
    "Didnauri/osm_bbox_nw",
    "OpenStreetMap API map bbox NW of the stored point",
    "way 1352023455 name 'დიდნაურის ნაქალაქარი' wikidata=Q26001314, place=isolated_dwelling, landuse=farmyard, centroid 41.421537,46.209003",
)
OSM_DID_SE = ev(
    "Didnauri/osm_bbox_se",
    "OpenStreetMap API map bbox SE of the stored point",
    "way 1193836494 name 'დიდნაურის ნაქალაქარი' wikidata=Q26001314, historic=archaeological_site, archaeological_site=settlement, ruins=fort, historic:period=iron-age, place=locality; bbox lat 41.41159-41.41729, lon 46.21381-46.23019; centroid 41.415504,46.219961; the stored point lies inside",
)
MAPCARTA = ev(
    "Didnauri/mapcarta",
    "mapcarta.com (OSM/GeoNames mirror)",
    "Didnauri ... Latitude 41.41444° or 41°24'52\" north",
)
DDG_DID = ev(
    "Didnauri/ddg_georgian",
    "DuckDuckGo lite search (Georgian query)",
    "hit list: ka.wikipedia 'დიდნაურის ნაქალაქარი', dtda.ge, ambebi.ge, 1tv.ge - no source with a coordinate of its own",
)

S = "severe"
M = "moderate"

RECORDS: list[dict] = [
    # ---------------------------------------------------------------- Satsurblia
    {
        "site_id": "31860bc4-476a-49bc-9f97-e25220063d19",
        "site_name": "Satsurblia Cave",
        "census_findings": [
            {
                "test_id": "T01/coords",
                "field": "lat/lon",
                "proposal": "review",
                "severity": M,
                "note": "Wikidata P625 is 1.28 km from the stored point (review threshold 1000 m)",
            },
            {
                "test_id": "T03/all-outside",
                "field": "card_description",
                "proposal": "review",
                "severity": S,
                "note": "card_description dates the site to 23,500 BC (< 4500 BC), but the declared period is 500 BC - 1 AD",
            },
            {
                "test_id": "T05/disambiguated",
                "field": "country",
                "proposal": "set",
                "severity": S,
                "note": "the parenthetical is a disambiguation hint, and the narrator reads 'Georgia (country)' aloud",
            },
        ],
        "outcomes": [
            {
                "field": "name",
                "current_value": "Satsurblia Cave",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/name",
            },
            {
                "field": "country",
                "current_value": "Georgia (country)",
                "outcome": "WRONG",
                "proposal": "set",
                "proposed_value": "Georgia",
                "confidence": "authoritative",
                "severity": S,
                "t1": "P3/country",
            },
            {
                "field": "lat/lon",
                "current_value": [42.37726777374251, 42.60097658321723],
                "outcome": "UNVERIFIABLE",
                "proposal": "review",
                "proposed_value": None,
                "confidence": "unverifiable",
                "severity": M,
                "t1": "P3/coords",
            },
            {
                "field": "period_start",
                "current_value": -500,
                "outcome": "WRONG",
                "proposal": "set",
                "proposed_value": -23500,
                "confidence": "two_source",
                "severity": S,
                "t1": "P3/period",
            },
            {
                "field": "period_name",
                "current_value": "500 BC - 1 AD",
                "outcome": "WRONG",
                "proposal": "set",
                "proposed_value": "< 4500 BC",
                "confidence": "authoritative",
                "severity": S,
                "t1": "P3/period",
            },
            {
                "field": "site_type",
                "current_value": "Cave Structures",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/site_type",
            },
            {
                "field": "description",
                "current_value": "Satsurblia Cave Natural Monument is a paleoanthropological site located 1.2 km from Kumistavi village in Georgia's Imereti region, situated 287 meters above sea level [1]. This karst cave was first excavated in 1976 by archaeologist A. N. Kalandadze [1]. During the Medieval period, the cave served as a refuge [1].",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/description",
            },
            {
                "field": "card_description",
                "current_value": "A Paleolithic cave first occupied around 23,500 BC. In the Middle Ages it was reused — ancient humans and medieval people sheltered in the same cavern.",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/card_description",
            },
        ],
    },
    # ---------------------------------------------------------------- Petroglyph
    {
        "site_id": "8c39badd-8113-4a71-a041-21d68f47bf58",
        "site_name": "Petroglyph Beach State Historic Park",
        "census_findings": [
            {
                "test_id": "T01/coords",
                "field": "lat/lon",
                "proposal": "review",
                "severity": S,
                "note": "Wikidata P625 is 235.60 km from the stored point",
            },
            {
                "test_id": "T02/outside-polygon",
                "field": "country",
                "proposal": "review",
                "severity": "cosmetic",
                "note": "point lies 1.1 km outside the United States of America polygon; Natural Earth places it in no country polygon (open water)",
            },
            {
                "test_id": "T05/spelling-split",
                "field": "country",
                "proposal": "review",
                "severity": M,
                "note": "abbreviation of a country the snapshot also spells 'United States' (1 site)",
            },
        ],
        "outcomes": [
            {
                "field": "name",
                "current_value": "Petroglyph Beach State Historic Park",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/name",
            },
            {
                "field": "country",
                "current_value": "USA",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/country",
            },
            {
                "field": "lat/lon",
                "current_value": [56.482869678860816, -132.3935035238634],
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/coords",
            },
            {
                "field": "period_start",
                "current_value": -5000,
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/period",
            },
            {
                "field": "period_name",
                "current_value": "< 4500 BC",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/period",
            },
            {
                "field": "site_type",
                "current_value": "Petroglyphs",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/site_type",
            },
            {
                "field": "description",
                "current_value": "Petroglyph Beach State Historic Park is an archaeological site on the shore of Wrangell, Alaska, featuring the highest concentration of Native American petroglyphs in southeastern Alaska [1]. Located less than a mile from downtown Wrangell, the site contains at least 40 carved images on boulders and bedrock outcrops [1]. The beach and surrounding area date to approximately 8,000 years ago, making it one of the oldest archaeological sites in the region [1]. The site was established as a State Historic Park in 2000 to protect these irreplaceable cultural artifacts [1].",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/description",
            },
            {
                "field": "card_description",
                "current_value": "An Alaskan beach with the highest concentration of petroglyphs in the southeast region. The site is about 8,000 years old, with at least 40 carvings found on boulders and bedrock.",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "authoritative",
                "severity": "none",
                "t1": "P3/card_description",
            },
        ],
    },
    # ---------------------------------------------------------------- Pannonian
    {
        "site_id": "db85cd62-288f-4142-9cad-f15532e4fe26",
        "site_name": "Pannonian Limes",
        "census_findings": [
            {
                "test_id": "T01/country",
                "field": "country",
                "proposal": "review",
                "severity": M,
                "note": "stored country normalises to 'HR', Wikidata P17 to ['AT']",
            },
            {
                "test_id": "T02/outside-polygon",
                "field": "country",
                "proposal": "review",
                "severity": M,
                "note": "point lies 182.2 km outside the Croatia polygon; Natural Earth places it in Republic of Serbia",
            },
            {
                "test_id": "T03/all-outside",
                "field": "card_description",
                "proposal": "review",
                "severity": S,
                "note": "card_description dates the site to 5th century AD (1 - 500 AD), but the declared period is 500 BC - 1 AD",
            },
        ],
        "outcomes": [
            {
                "field": "name",
                "current_value": "Pannonian Limes",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/name",
            },
            {
                "field": "country",
                "current_value": "Croatia",
                "outcome": "WRONG",
                "proposal": "review",
                "proposed_value": None,
                "confidence": "two_source",
                "severity": M,
                "t1": "P3/country",
                "note": "no single correct value: the frontier runs through Austria, Slovakia, Hungary, Croatia and Serbia; the field cannot hold it",
            },
            {
                "field": "lat/lon",
                "current_value": [44.00010030082549, 20.999924894773976],
                "outcome": "WRONG",
                "proposal": "review",
                "proposed_value": None,
                "confidence": "two_source",
                "severity": M,
                "t1": "P3/coords",
                "note": "new defect, not named by the census: the nearest Danube geometry is 82.7 km away, and the limes is the Danube line",
            },
            {
                "field": "period_start",
                "current_value": -500,
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/period",
            },
            {
                "field": "period_name",
                "current_value": "500 BC - 1 AD",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/period",
            },
            {
                "field": "site_type",
                "current_value": "Fortress/citadel",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/site_type",
            },
            {
                "field": "description",
                "current_value": "The Pannonian Limes in Croatia is a segment of the Roman Danubian frontier stretching approximately 420 km from Austria to Serbia[1]. Built along the Danube River, this line of forts and watchtowers protected the Pannonian provinces from northern barbarian invasions from the reign of Augustus (31 BC–AD 14) until the early 5th century[1]. In certain areas, Roman defenses extended across the river into hostile Barbaricum territory[1].",
                "outcome": "WRONG",
                "proposal": "review",
                "proposed_value": None,
                "confidence": "two_source",
                "severity": M,
                "t1": "P3/description",
                "note": "new defect: the sentence scopes a multinational frontier to Croatia and contradicts itself; the fix is a Phase-5 text rewrite, not a SQL update",
            },
            {
                "field": "card_description",
                "current_value": "A 420 km stretch of Roman frontier fortifications along the Danube, defended from the time of Augustus to the 5th century AD. Forts lined the river at regular intervals.",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/card_description",
            },
        ],
    },
    # ---------------------------------------------------------------- Karpasia
    {
        "site_id": "e2dbb087-8f25-4726-967a-e1054d4be16c",
        "site_name": "Karpasia - Town",
        "census_findings": [
            {
                "test_id": "T01/coords",
                "field": "lat/lon",
                "proposal": "review",
                "severity": M,
                "note": "Wikidata P625 is 3.52 km from the stored point",
            },
            {
                "test_id": "T02/outside-polygon",
                "field": "country",
                "proposal": "review",
                "severity": M,
                "note": "point lies 68.1 km outside the Cyprus polygon; Natural Earth places it in Northern Cyprus",
            },
            {
                "test_id": "T03/all-outside",
                "field": "card_description",
                "proposal": "review",
                "severity": S,
                "note": "card_description dates the site to 334 BC (500 BC - 1 AD), but the declared period is 1500 - 500 BC",
            },
        ],
        "outcomes": [
            {
                "field": "name",
                "current_value": "Karpasia - Town",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/name",
                "note": "'Name - Qualifier' is a house pattern measured on 97 of 5,004 sites",
            },
            {
                "field": "country",
                "current_value": "Cyprus",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/country",
            },
            {
                "field": "lat/lon",
                "current_value": [35.59664186874294, 34.37808778289012],
                "outcome": "WRONG",
                "proposal": "review",
                "proposed_value": None,
                "confidence": "two_source",
                "severity": M,
                "t1": "P3/coords",
                "note": "the stored point is modern Rizokarpaso; the ancient site is at Ayios Philon, 3.4-4.6 km away per three sources that disagree with each other",
            },
            {
                "field": "period_start",
                "current_value": -1500,
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/period",
            },
            {
                "field": "period_name",
                "current_value": "1500 - 500 BC",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/period",
            },
            {
                "field": "site_type",
                "current_value": "City/town/settlement",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/site_type",
            },
            {
                "field": "description",
                "current_value": "Karpasia (also Karpasion) was an ancient Cypriot city on the northern Karpas Peninsula, located 3 km from modern Rizokarpaso [1]. According to tradition, it was founded by the Phoenician king Pygmalion of Tyre [1]. The city possessed a harbor whose ancient moles remain visible today [1].",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/description",
            },
            {
                "field": "card_description",
                "current_value": "An ancient Greek city-kingdom founded by Phoenicians. Its most famous resident, Zeno of Citium (born c. 334 BC), founded Stoic philosophy.",
                "outcome": "WRONG",
                "proposal": "review",
                "proposed_value": None,
                "confidence": "authoritative",
                "severity": S,
                "t1": "P3/card_description",
                "note": "new defect, not named by the census: Wikidata P19/P27 place Zeno of Citium in Kition, 102 km away in a straight line; the fix is a Phase-5 card rewrite",
            },
        ],
    },
    # ---------------------------------------------------------------- Didnauri
    {
        "site_id": "593de422-8bfc-4101-8e13-3db406830e60",
        "site_name": "Didnauri",
        "census_findings": [
            {
                "test_id": "T01/coords",
                "field": "lat/lon",
                "proposal": "review",
                "severity": M,
                "note": "Wikidata P625 is 2.86 km from the stored point",
            },
            {
                "test_id": "T03/all-outside",
                "field": "card_description",
                "proposal": "review",
                "severity": S,
                "note": "card_description dates the site to 12th-9th century BC (1500 - 500 BC), but the declared period is 3000 - 1500 BC",
            },
            {
                "test_id": "T05/disambiguated",
                "field": "country",
                "proposal": "set",
                "severity": S,
                "note": "the narrator reads 'Georgia (country)' aloud",
            },
        ],
        "outcomes": [
            {
                "field": "name",
                "current_value": "Didnauri",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/name",
            },
            {
                "field": "country",
                "current_value": "Georgia (country)",
                "outcome": "WRONG",
                "proposal": "set",
                "proposed_value": "Georgia",
                "confidence": "authoritative",
                "severity": S,
                "t1": "P3/country",
            },
            {
                "field": "lat/lon",
                "current_value": [41.414698033306436, 46.222808833435394],
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/coords",
            },
            {
                "field": "period_start",
                "current_value": -3000,
                "outcome": "WRONG",
                "proposal": "set",
                "proposed_value": -1500,
                "confidence": "two_source",
                "severity": S,
                "t1": "P3/period",
            },
            {
                "field": "period_name",
                "current_value": "3000 - 1500 BC",
                "outcome": "WRONG",
                "proposal": "set",
                "proposed_value": "1500 - 500 BC",
                "confidence": "two_source",
                "severity": S,
                "t1": "P3/period",
            },
            {
                "field": "site_type",
                "current_value": "City/town/settlement",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/site_type",
            },
            {
                "field": "description",
                "current_value": "Didnauri is a Late Bronze Age/Early Iron Age settlement on the Shiraki Plain in Dedoplistsqaro municipality, southeastern Georgia. It is considered the largest ancient settlement ever unearthed in the South Caucasus. The site is inscribed on Georgia's list of Immovable Monuments of Cultural Heritage [1].",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/description",
            },
            {
                "field": "card_description",
                "current_value": "Spread across the Shiraki Plain, this 12th–9th century BC site is described by national heritage authorities as the largest ancient settlement found in the South Caucasus.",
                "outcome": "CORRECT",
                "proposal": "none",
                "confidence": "two_source",
                "severity": "none",
                "t1": "P3/card_description",
            },
        ],
    },
]


def local(source: str, quote: str) -> dict:
    """Evidence from this repository (a file:line claim), not an HTTP fetch."""
    return {
        "source": source,
        "url": source,
        "quote": quote,
        "retrieved_at": "2026-09-20",
        "fetch_log_label": None,
        "http_status": None,
    }


TTS_EV = local(
    "pipeline/video/shorts_tts.py:21-23",
    "specific_place(country) returns the text after the last comma, so 'Georgia (country)' "
    "is spoken in full",
)

# Evidence per field: keyed by (site_id, field); each entry is (evidence item, why it counts).
EvidenceList = list[tuple[dict[str, Any], str]]
E: dict[tuple[str, str], EvidenceList] = {
    ("31860bc4-476a-49bc-9f97-e25220063d19", "name"): [
        (EN_SATS, "article title 'Satsurblia Cave'"),
        (WD_SATS, "Wikidata en label 'Satsurblia Cave'"),
    ],
    ("31860bc4-476a-49bc-9f97-e25220063d19", "country"): [
        (WD_SATS, "P17 = Q230 Georgia"),
        (KA_SATS, "Georgian article: წყალტუბოს მუნიციპალიტეტი (Georgia)"),
        (TTS_EV, "the spoken line"),
    ],
    ("31860bc4-476a-49bc-9f97-e25220063d19", "lat/lon"): [
        (WD_SATS, "the census's P625, with its own precision 0.01216 deg = 1.35 km"),
        (SHOWCAVES, "42.387795, 42.606163"),
        (GEONAMES_SATS, "42.3772, 42.6009 = the stored value"),
        (
            OSM_SATS,
            "a named 'Satsurblia Cave' cave entrance 2.35 km away, and the stored point 50 m from the Prometheus Cave ticket centre",
        ),
        (NATPARK, "location: Tskaltubo Municipality, no coordinates published"),
    ],
    ("31860bc4-476a-49bc-9f97-e25220063d19", "period_start"): [
        (PLOS, "25,535-24,408 cal. BP"),
        (EN_SATS, "occupied ~25,500-24,400 BP"),
        (
            local(
                "pipeline/utils/text.py:255",
                "categorize_period(-23500) == '< 4500 BC' (run against pipeline/utils/text.py:255)",
            ),
            "categorize_period(-23500) == '< 4500 BC' (run against pipeline/utils/text.py:255)",
        ),
    ],
    ("31860bc4-476a-49bc-9f97-e25220063d19", "period_name"): [
        (PLOS, "25,535-24,408 cal. BP"),
        (
            local("pipeline/utils/text.py:255", "categorize_period(-23500) == '< 4500 BC'"),
            "categorize_period(-23500) == '< 4500 BC'",
        ),
    ],
    ("31860bc4-476a-49bc-9f97-e25220063d19", "site_type"): [
        (WD_SATS, "P31 = cave + archaeological site"),
        (EN_SATS, "paleoanthropological site"),
        (
            local(
                "pipeline/normalizers/site_type.py:186",
                "normalize_site_type('Cave Structures') == 'Cave Structures' (fixed point)",
            ),
            "normalize_site_type('Cave Structures') == 'Cave Structures' (fixed point)",
        ),
    ],
    ("31860bc4-476a-49bc-9f97-e25220063d19", "description"): [
        (EN_SATS, "1.2 km from Kumistavi, 287 m above sea level"),
        (SHOWCAVES, "287 m asl.; excavations 1976 by A. N. Kalandadze; medieval use"),
        (
            KA_SATS,
            "the Georgian article says 270 m for the same cave - majority holds, noted not used",
        ),
    ],
    ("31860bc4-476a-49bc-9f97-e25220063d19", "card_description"): [
        (PLOS, "25,535-24,408 cal. BP"),
        (EN_SATS, "medieval refuge; Palaeolithic occupation"),
    ],
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "name"): [
        (EN_PET, "article title 'Petroglyph Beach State Historic Park'"),
        (
            ASP_PET,
            "the agency calls the unit 'Petroglyph State Historic Site' - a designation difference, not a factual error",
        ),
    ],
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "country"): [
        (ASP_PET, "in Wrangell, Alaska"),
        (WD_PET, "P17 = Q30 USA"),
        (OVERPASS_PET_FEAT, "the stored point is on the Wrangell street grid, not open water"),
    ],
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "lat/lon"): [
        (ASP_PET, "Address: Grave Street, Wrangell; 1 mile from the ferry terminal"),
        (OSM_PET, "Grave Street at the stored point, in Wrangell"),
        (OVERPASS_JUNEAU, "the Wikidata/Wikipedia point is the Juneau place node"),
        (WIKITEXT_PET, "the article's own coord is the same Juneau point"),
    ],
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "period_start"): [
        (ASP_PET, "The site itself is about 8000 years old"),
        (EN_PET, "about 8000 years old"),
    ],
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "period_name"): [
        (ASP_PET, "about 8000 years old"),
        (EN_PET, "about 8000 years old"),
    ],
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "site_type"): [
        (EN_PET, "petroglyphs on boulders and bedrock"),
        (ASP_PET, "highest concentration of petroglyphs"),
        (
            local(
                "pipeline/normalizers/site_type.py:186",
                "normalize_site_type('Petroglyphs') is a fixed point",
            ),
            "normalize_site_type('Petroglyphs') is a fixed point",
        ),
    ],
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "description"): [
        (
            ASP_PET,
            "highest concentration ... became a State Historic Park in 2000. At least 40 petroglyphs",
        ),
        (EN_PET, "same sentences - i.e. the article derives from the agency page"),
    ],
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "card_description"): [
        (ASP_PET, "highest concentration ... about 8000 years old. At least 40 petroglyphs")
    ],
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "name"): [
        (WD_PAN, "Wikidata en label 'Pannonian Limes'"),
        (HR_PAN, "Croatian Wikipedia titles the same frontier 'Panonski limes'"),
    ],
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "country"): [
        (EN_PAN, "across Austria, Slovakia, Hungary, Croatia and Serbia"),
        (HR_PAN, "od Klosterneuburga u današnjoj Austriji do Beograda"),
        (WD_PAN, "P17 = Q40 Austria (a third answer again)"),
        (LIMESCRO, "the Croatian section is Batina ... Ilok"),
        (OVER_PAN_PT, "the stored coordinate is in Serbia"),
    ],
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "lat/lon"): [
        (DANUBE, "nearest Danube geometry 82.7 km away"),
        (HR_PAN, "the limes follows the Danube"),
        (EN_PAN, "420 km from Austria to Serbia"),
        (OVER_PAN_PT, "the stored point is a Serbian village"),
    ],
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "period_start"): [
        (HR_PAN, "car August od 14. pr. Kr. do 31. godine"),
        (EN_PAN, "from the reign of Augustus (31 BC-AD 14) to the early 5th century"),
        (
            local("pipeline/utils/text.py:255", "categorize_period(-500) == '500 BC - 1 AD'"),
            "categorize_period(-500) == '500 BC - 1 AD'",
        ),
    ],
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "period_name"): [
        (HR_PAN, "Augustus 14 BC - AD 31"),
        (
            local("pipeline/utils/text.py:255", "the inception lies inside the declared bucket"),
            "the inception lies inside the declared bucket",
        ),
    ],
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "site_type"): [
        (EN_PAN, "line of forts and watchtowers"),
        (
            local(
                "pipeline/normalizers/site_type.py:186",
                "normalize_site_type('Fortress/citadel') is a fixed point",
            ),
            "normalize_site_type('Fortress/citadel') is a fixed point",
        ),
    ],
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "description"): [
        (EN_PAN, "multinational frontier"),
        (HR_PAN, "420 km, Klosterneuburg to Belgrade"),
        (OVER_PAN_PT, "the stored coordinate is in Serbia, not Croatia"),
    ],
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "card_description"): [
        (HR_PAN, "420 km ... od Klosterneuburga ... do Beograda"),
        (EN_PAN, "Augustus to the early 5th century"),
    ],
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "name"): [
        (EN_KAR, "article title 'Karpasia (town)'"),
        (
            {
                "source": "local measurement, output/remediation/snapshot/unified_sites.jsonl.gz",
                "url": "output/remediation/snapshot/unified_sites.jsonl.gz",
                "quote": "97 of 5,004 site names use the pattern 'Name - Qualifier' (e.g. 'Akrotiri - Prehistoric City', 'Armeni - Archaeological Site')",
                "retrieved_at": "2026-09-20",
                "fetch_log_label": None,
                "http_status": None,
            },
            "house pattern, not an artifact",
        ),
    ],
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "country"): [
        (WD_KAR, "P17 = Q229 Cyprus"),
        (PLEIADES, "Cyprus"),
        (EN_KAR, "northern Karpas Peninsula"),
    ],
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "lat/lon"): [
        (WIKITEXT_KAR, "the stored value is the article's own coordinate"),
        (PRINCETON, "KARPASIA (Haghios Philon) Cyprus - the ancient site is at Ayios Philon"),
        (WD_KAR, "P625 = 35.61994444, 34.35175"),
        (PLEIADES, "DARMC 35.626206/34.369934"),
        (OVERPASS_KAR, "OSM 'Ayios Philon Roman harbor' 35.63473/34.39794, 4.60 km away"),
        (EN_KAR, "the record's own source says the ancient city was 3 km from modern Rizokarpaso"),
    ],
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "period_start"): [
        (EN_KAR, "founded (by tradition) by Pygmalion of Tyre"),
        (PLEIADES, "Archaic period, 750-550 BC"),
        (
            local(
                "pipeline/utils/text.py:255",
                "categorize_period(-1500) == '1500 - 500 BC'; 750 BC falls in the same bucket",
            ),
            "categorize_period(-1500) == '1500 - 500 BC'; 750 BC falls in the same bucket",
        ),
    ],
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "period_name"): [
        (PLEIADES, "settlement and port, Archaic to Roman"),
        (local("pipeline/utils/text.py:255", "same bucket"), "same bucket"),
    ],
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "site_type"): [
        (PLEIADES, "types: settlement, port"),
        (WD_KAR, "P31 human settlement / ancient city / polis"),
        (
            local(
                "pipeline/normalizers/site_type.py:186",
                "normalize_site_type('City/town/settlement') is a fixed point",
            ),
            "normalize_site_type('City/town/settlement') is a fixed point",
        ),
    ],
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "description"): [
        (EN_KAR, "3 km from modern Rizokarpaso; founded by Pygmalion; harbour with visible moles"),
        (PRINCETON, "KARPASIA (Haghios Philon), Cyprus"),
    ],
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "card_description"): [
        (WD_ZENO, "Zeno of Citium: P19 = P27 = Q1743884"),
        (WD_KITION, "Q1743884 = Kition, 'ancient Phoenician city and kingdom in Cyprus'"),
    ],
    ("593de422-8bfc-4101-8e13-3db406830e60", "name"): [
        (EN_DID, "article title 'Didnauri'"),
        (OSM_DID_SE, "name:en Didnauri"),
    ],
    ("593de422-8bfc-4101-8e13-3db406830e60", "country"): [
        (EN_DID, "Dedoplistsqaro municipality, Georgia"),
        (DDG_DID, "Georgian sources"),
        (
            local("pipeline/video/shorts_tts.py:21-23", "the spoken line (shorts_tts.py:21-23)"),
            "the spoken line (shorts_tts.py:21-23)",
        ),
    ],
    ("593de422-8bfc-4101-8e13-3db406830e60", "lat/lon"): [
        (
            OSM_DID_SE,
            "way tagged wikidata=Q26001314 contains the stored point (41.41159-41.41729, 46.21381-46.23019)",
        ),
        (OSM_DID_NE, "the second way with the same tags"),
        (WIKITEXT_DID, "infobox coord = the stored point"),
        (WD_DID, "P625 2.86 km away, precision 2.78e-06"),
        (MAPCARTA, "41.41444"),
    ],
    ("593de422-8bfc-4101-8e13-3db406830e60", "period_start"): [
        (EN_DID, "12th-9th centuries BC"),
        (OSM_DID_SE, "historic:period=iron-age"),
        (
            local(
                "pipeline/utils/text.py:255",
                "categorize_period(-1500) == '1500 - 500 BC'; 648 of 987 sites in that bucket use -1500",
            ),
            "the bucket label of the proposed -1500",
        ),
    ],
    ("593de422-8bfc-4101-8e13-3db406830e60", "period_name"): [
        (EN_DID, "12th-9th centuries BC"),
        (OSM_DID_SE, "historic:period=iron-age"),
    ],
    ("593de422-8bfc-4101-8e13-3db406830e60", "site_type"): [
        (OSM_DID_SE, "archaeological_site=settlement"),
        (EN_DID, "settlement"),
        (
            local(
                "pipeline/normalizers/site_type.py:186",
                "normalize_site_type('City/town/settlement') is a fixed point",
            ),
            "normalize_site_type('City/town/settlement') is a fixed point",
        ),
    ],
    ("593de422-8bfc-4101-8e13-3db406830e60", "description"): [
        (
            EN_DID,
            "Late Bronze Age/Early Iron Age settlement on the Shiraki Plain, Dedoplistsqaro municipality",
        ),
        (OSM_DID_SE, "historic:period=iron-age on the mapped settlement"),
    ],
    ("593de422-8bfc-4101-8e13-3db406830e60", "card_description"): [
        (
            EN_DID,
            "dated to the 12th-9th centuries BC; largest ancient settlement in the South Caucasus per the National Agency",
        ),
        (OSM_DID_SE, "iron-age tag on the settlement mapped with the same Wikidata item"),
    ],
}

REVIEW: dict[tuple[str, str], dict] = {
    ("31860bc4-476a-49bc-9f97-e25220063d19", "country"): {
        "verdict": "confirmed",
        "note": "mechanism reproduced at shorts_tts.py:21-23; Wikidata P17 = Q230; 27 sites spell it 'Georgia (country)' against 3 'Georgia'",
    },
    ("31860bc4-476a-49bc-9f97-e25220063d19", "lat/lon"): {
        "verdict": "unresolved",
        "note": "own sources: showcaves.com 42.387795/42.606163, GeoNames 42.3772/42.6009 (= the stored value), OSM node 'აწურბლიას მღვიმე' 42.39647/42.58902. Three candidates, none authoritative enough; the stored pin sits on the Prometheus Cave visitor complex. Goes to a human.",
        "refutation_evidence": [SHOWCAVES, GEONAMES_SATS, OSM_SATS],
    },
    ("31860bc4-476a-49bc-9f97-e25220063d19", "period_start"): {
        "verdict": "not_refuted",
        "note": "peer-reviewed dating (PLOS ONE 2014) reproduced independently; categorize_period run at source",
        "refutation_evidence": [PLOS],
    },
    ("31860bc4-476a-49bc-9f97-e25220063d19", "period_name"): {
        "verdict": "not_refuted",
        "note": "same evidence",
        "refutation_evidence": [PLOS],
    },
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "lat/lon"): {
        "verdict": "refuted",
        "note": "the census lead rested on Wikidata/Wikipedia; the official Alaska State Parks page gives the Wrangell address 'Grave Street' and OSM has the stored point on Grave Street, while the Wikidata point is the Juneau place node 0.4 km away. The stored value survives.",
        "refutation_evidence": [ASP_PET, OSM_PET, OVERPASS_JUNEAU],
    },
    ("8c39badd-8113-4a71-a041-21d68f47bf58", "country"): {
        "verdict": "refuted",
        "note": "two census findings on one field: T02 (open water, 1.1 km) is a Natural Earth coastline artifact on Wrangell Island; T05 is a spelling/consistency decision, not a factual error",
        "refutation_evidence": [ASP_PET, OVERPASS_PET_FEAT],
    },
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "country"): {
        "verdict": "confirmed_as_inconsistency",
        "note": "the field cannot be Croatia and cannot be Austria either; needs a human scope decision",
        "refutation_evidence": [HR_PAN, LIMESCRO],
    },
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "lat/lon"): {
        "verdict": "found_not_named",
        "note": "not a census lead: Wikidata has no P625 for Q471153. Own measurement: the Danube is 82.7 km away (Overpass).",
        "refutation_evidence": [DANUBE, OVER_PAN_PT],
    },
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "period_start"): {
        "verdict": "refuted",
        "note": "the card's only dated claim is the terminus; the Augustan inception lies inside the declared bucket",
        "refutation_evidence": [HR_PAN, EN_PAN],
    },
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "period_name"): {
        "verdict": "refuted",
        "note": "same",
        "refutation_evidence": [HR_PAN],
    },
    ("db85cd62-288f-4142-9cad-f15532e4fe26", "description"): {
        "verdict": "found_not_named",
        "note": "self-contradicting scope claim; Phase-5 text route",
        "refutation_evidence": [EN_PAN, HR_PAN],
    },
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "lat/lon"): {
        "verdict": "not_refuted",
        "note": "three independent sources put the ancient site at Ayios Philon 3.4-4.6 km away, and the record's own description says 3 km from the modern town; the candidates disagree, so proposal=review",
        "refutation_evidence": [PLEIADES, OVERPASS_KAR, WIKITEXT_KAR],
    },
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "country"): {
        "verdict": "refuted",
        "note": "Natural Earth draws the de-facto border; Wikidata P17 = Cyprus; ENRICHMENT_AUDIT anti-pattern 7",
        "refutation_evidence": [WD_KAR, PLEIADES],
    },
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "period_start"): {
        "verdict": "refuted",
        "note": "the flagged 334 BC is Zeno's birth year, not a date of the site; the site's foundation (7th century BC) is inside the declared bucket",
        "refutation_evidence": [PLEIADES, WD_ZENO],
    },
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "period_name"): {
        "verdict": "refuted",
        "note": "same",
        "refutation_evidence": [PLEIADES],
    },
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "card_description"): {
        "verdict": "found_not_named",
        "note": "Zeno of Citium was born in Kition per Wikidata P19/P27 (Q1743884, label fetched separately)",
        "refutation_evidence": [WD_ZENO, WD_KITION],
    },
    ("593de422-8bfc-4101-8e13-3db406830e60", "country"): {
        "verdict": "confirmed",
        "note": "same mechanism as Satsurblia",
        "refutation_evidence": [TTS_EV],
    },
    ("593de422-8bfc-4101-8e13-3db406830e60", "lat/lon"): {
        "verdict": "refuted",
        "note": "OSM ways tagged with the same Wikidata item contain the stored point; Wikidata's pin is off the mapped site",
        "refutation_evidence": [OSM_DID_SE, OSM_DID_NE],
    },
    ("593de422-8bfc-4101-8e13-3db406830e60", "period_start"): {
        "verdict": "not_refuted",
        "note": "OSM's historic:period=iron-age independently supports the Iron Age dating",
        "refutation_evidence": [OSM_DID_SE, EN_DID],
    },
    ("593de422-8bfc-4101-8e13-3db406830e60", "period_name"): {
        "verdict": "not_refuted",
        "note": "same",
        "refutation_evidence": [OSM_DID_SE],
    },
}


# Sources that were tried for this claim and failed, so that a "could not check" never
# reads as "checked and clean".
FAILED: dict[tuple[str, str], list[dict]] = {
    ("e2dbb087-8f25-4726-967a-e1054d4be16c", "card_description"): [DDG_KAR, SEP_KAR, IEP_KAR],
}

# The census files its T03 finding against `card_description`, but the fix may belong to
# period_start/period_name (the bucket) or to the card text. Both ends are marked.
CROSS: dict[tuple[str, str], str] = {
    (
        "31860bc4-476a-49bc-9f97-e25220063d19",
        "period_start",
    ): "census finding: T03/all-outside is filed against card_description; here the bucket is the wrong end",
    ("31860bc4-476a-49bc-9f97-e25220063d19", "period_name"): "same T03 finding",
    (
        "31860bc4-476a-49bc-9f97-e25220063d19",
        "card_description",
    ): "the T03 finding is filed here, but the card text is CORRECT; the fix belongs to period_start/period_name",
    (
        "593de422-8bfc-4101-8e13-3db406830e60",
        "period_start",
    ): "census finding: T03/all-outside is filed against card_description; here the bucket is the wrong end",
    ("593de422-8bfc-4101-8e13-3db406830e60", "period_name"): "same T03 finding",
    (
        "593de422-8bfc-4101-8e13-3db406830e60",
        "card_description",
    ): "the T03 finding is filed here, but the card text is CORRECT; the fix belongs to period_start/period_name",
    (
        "e2dbb087-8f25-4726-967a-e1054d4be16c",
        "card_description",
    ): "the T03 finding is filed here and the card text is also wrong, but for a different reason (Zeno) than the date the census flagged",
    (
        "db85cd62-288f-4142-9cad-f15532e4fe26",
        "card_description",
    ): "the T03 finding is filed here; both the card text and the declared bucket are CORRECT (false alarm)",
}


# Why the sources decide the row: only for rows whose evidence needs a summary.
NOTES: dict[tuple[str, str], str] = {
    ("31860bc4-476a-49bc-9f97-e25220063d19", "country"): (
        "Wikidata P17 = Q230 (Georgia) and the Georgian-language article agree; the parenthetical "
        "is a disambiguation hint, and the narrator reads the whole string aloud (shorts_tts.py). "
        "`set 'Georgia'` - the spelling the snapshot already uses on 3 sites."
    ),
    ("31860bc4-476a-49bc-9f97-e25220063d19", "period_start"): (
        "PLOS ONE dates the layer to 25,535-24,408 cal. BP (approx. 23,600-22,400 BC) and "
        "enwiki/ka-wiki describe the same occupation; the record's own card already says 23,500 BC, "
        "so the field contradicts its own card. -23500 and the stored -500 land in different buckets."
    ),
    ("31860bc4-476a-49bc-9f97-e25220063d19", "period_name"): (
        "categorize_period(-23500) = '< 4500 BC' (pipeline/utils/text.py:255); the stored "
        "'500 BC - 1 AD' is the bucket of -500 and cannot hold a Palaeolithic date. Confidence "
        "'authoritative': one peer-reviewed source (PLOS ONE) plus the local bucket function - "
        "enwiki is not counted twice for the same date."
    ),
    ("31860bc4-476a-49bc-9f97-e25220063d19", "lat/lon"): (
        "Three independent candidates 1.25-2.35 km from the stored point (showcaves "
        "42.387795/42.606163, Wikidata P625 with 1.35 km precision, an OSM cave entrance), while "
        "GeoNames repeats the stored value exactly and the stored point sits 50 m from the "
        "Prometheus Cave ticket centre. No candidate outranks the others -> review, no write."
    ),
    ("593de422-8bfc-4101-8e13-3db406830e60", "country"): (
        "Same mechanism as Satsurblia: Wikidata P17 = Q230 and the narrator reads 'Georgia "
        "(country)' aloud; `set 'Georgia'` (authoritative, mechanically applicable)."
    ),
    ("593de422-8bfc-4101-8e13-3db406830e60", "period_start"): (
        "enwiki dates the settlement to the 12th-9th centuries BC and OSM tags it "
        "historic:period=iron-age; both lie in '1500 - 500 BC', not in the stored '3000 - 1500 BC'. "
        "-1500 is that bucket's lower bound and the value 648 of the 987 sites in it use."
    ),
    ("593de422-8bfc-4101-8e13-3db406830e60", "period_name"): (
        "categorize_period(-1500) = '1500 - 500 BC'; the card, the record's own description and "
        "the OSM tags all say Late Bronze / Early Iron Age, i.e. the later bucket."
    ),
}

DEFAULT_NOTE = {
    "CORRECT": (
        "stored value stands against the sources listed (see the per-source notes); the reviewer "
        "verdict records what happened to the census lead, if there was one"
    ),
    "WRONG": (
        "the stored value is contradicted by the sources listed; the replacement is in "
        "proposed_value or the reviewer note"
    ),
    "UNVERIFIABLE": "the sources disagree or do not reach the field; no defensible replacement exists",
}


def main() -> None:
    out = HERE / "PILOT.jsonl"
    rows = 0
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in RECORDS:
            for oc in rec["outcomes"]:
                key = (rec["site_id"], oc["field"])
                row = {
                    "site_id": rec["site_id"],
                    "site_name": rec["site_name"],
                    "field": oc["field"],
                    "current_value": oc["current_value"],
                    "outcome": oc["outcome"],
                    "proposal": oc["proposal"],
                    "proposed_value": oc.get("proposed_value"),
                    "confidence": oc["confidence"],
                    "severity": oc["severity"],
                    "test_id": oc["t1"],
                    "dimension": "Phase 3 pilot",
                    "evidence": [e[0] | {"note": e[1]} for e in E[key]],
                    "reviewer": REVIEW.get(
                        key,
                        {
                            "verdict": "not_required",
                            "note": "no census finding on this field; checked by the finder against >= 2 sources and not contradicted",
                        },
                    ),
                    "census_findings": [
                        f for f in rec["census_findings"] if f["field"] == oc["field"]
                    ],
                    "census_cross_reference": CROSS.get(key),
                    "failed_source_probes": FAILED.get(key, []),
                    "note": oc.get("note") or NOTES.get(key) or DEFAULT_NOTE[oc["outcome"]],
                }
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                rows += 1
    print(f"wrote {out} rows={rows} missing_evidence_keys={len(_missing)}")


if __name__ == "__main__":
    main()
