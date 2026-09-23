"""The reviewed repair of mis-resolved `site_external_ids` rows: rendered here, applied by nobody here.

`site_external_ids` is filled by `pipeline/lyra/prospector/external_ids.py` from each curated site's
`source_url`: the enwiki title in the URL is resolved (redirects followed) and its title and Wikidata
item are stored. Twenty curated sites carry an id that names something other than the site. For the
thirteen generic ids the `source_url` itself names the generic article
(`https://en.wikipedia.org/wiki/History`, `.../Archaeology`, `.../Theatre`, `.../Temples_(band)`); for two
of them the stored name redirects to exactly that section of another article (`Estipeon` -> `Štip#History`,
`Castellum Onagrinum` -> `Begeč#Archaeology`), which looks like a section fragment taken as a title - for
the other eleven how the URL was made is not established. The Tomb of Artaxerxes III's URL is its own
title, which redirects to `Persepolis#Tombs`, so the redirect gave it Persepolis' item. So seven sites
are routed to Q309 ("history", the discipline), two to Q23498 ("archaeology"), three to Q11635
("theatre"), Stabiae to an English rock band, and five Gyeongju belts to their shared World Heritage
parent. Every later pass that asks Wikidata about these sites asks about the wrong thing.

Each site was re-resolved **one at a time** on 2026-09-22 (read-only: `wbsearchentities` by name and
variants, `wbgetentities` for every candidate, a WDQS `wikibase:around` search of 0.6 km for the three
theatres, the enwiki page for the stored name), under two rules and nothing else:

* **A - the stored name is an existing enwiki article's exact title**: the article's own item, the
  identity `external_ids.py` would have stored had the `source_url` been right (confidence
  `two_source`: the article and the item agree);
* **B - otherwise, one item whose label names the site, of the site's kind, at the site's place**
  (confidence `authoritative`).

A site neither rule settles is **unresolved**: the plan leaves its row exactly as it is and lists it.
`enwiki_title` is changed only where the new item links a real English article (not a redirect); a
generic title with no replacement stays and is listed, because replacing it would take a `DELETE`.

What this renders into `output/remediation/qid_repair/` (nothing is applied):

* `PLAN.jsonl` - one row per change, with its evidence and change key;
* `APPLY.sql` - one transaction: guards, a conditional `UPDATE ... WHERE site_id, kind, value = old`
  per row, one journal row each, invariants, `COMMIT`;
* `REHEARSAL.sql` - the same statement ending in `ROLLBACK` (not versioned: it keeps nothing);
* `ROLLBACK.sql` - the inverse, conditional on the new value, journalled under its own stamp;
* `PLAN.md` - the per-site evidence and the unresolved list.

**Why not `apply_remediation_change`.** The primitive addresses a row by one key column
(`WHERE <pk_col>::text = $pk`) and re-reads it by that column for its round-trip check. The key of
`site_external_ids` is `(site_id, kind, value)` and every one of these sites has two rows (its
`enwiki_title` and its `wikidata_qid`), so no single column names the row: by `site_id` the re-read
returns two rows and compares whichever comes first. The statements here therefore do what the
primitive does, spelled for a composite key - the conditional `UPDATE` must match exactly one row,
the row is re-read by its full key, and the journal row is written in the same transaction - and the
plan digest pins both statements to `PLAN.jsonl` (`-- plan digest sha256:`), as `write_stage` does.

**Fixed point.** The boot path (`refresh_site_external_ids(only_missing=True)`, `prospector/__init__.py`)
only reads sites that have no row at all, so a repaired row stays repaired. The manual
`--all` path would insert the `source_url`'s id again beside the repaired one (the key includes the
value, `ON CONFLICT DO NOTHING` does not collide) - that stays true until the twenty `source_url`
values are corrected, which is a separate change to a column many producers read and is listed in
`PLAN.md`, not made here.

    ./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py render
    ./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py check    # read-only pre-flight
    ./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py verify   # read-only, after apply

## Wave 2 (2026-09-23): the wrong links among the B1 name findings whose name does not match

The first wave was applied on 2026-09-23 (26 rows, run stamp `2026-09-22_external-id-repair`); its
plan, statements and rules above are unchanged, so its `verify` still reads what was written. The
owner-case classifier (`scripts/remediation/bcases/`) then found 77 wrong links among the 631 T01 name
findings - the rows whose stored name is none of the item's names *and* whose item is a generic
concept, a shared parent or sibling, an item without a coordinate or one more than 5 km away (classes
Q1-Q4); 18 of them are sites of the first wave. Wave 2 is **not** every suspect link: 72 more rows keep
their name (it is one of the item's names) while their link meets Q1, Q2 or Q4 on its own
(`link_suspect` in `names.jsonl` - "Dolmens of Sardinia" on the class "dolmen", "The Temple of Artemis"
stored in Greece on the Ephesus temple). They were not researched and stay for a later wave or the
owner (HUMAN_ONLY B1/B2). The other **59** of the 77 were researched one at a
time (`scripts/remediation/bcases/qid_research.py`, record `output/remediation/bcases/qid_research.jsonl`):
the English article named exactly like the site, every Wikidata item within 1 km of the stored point
(`list=geosearch`), the first ten `wbsearchentities` hits - each with its names, classes and P625.

Wave 2 keeps rules A and B and adds the gate the remaining-work map set for a replacement ("a wrong
replacement QID is worse than a known-bad generic one, because dedup trusts QIDs"):

* **A** as before, and the article's item must be a site (not a settlement, administrative unit or
  natural feature, not a Wikimedia page), and the item's P625 **or the article's own coordinates**
  must lie within `GATE_M` (1 km) of the stored point;
* **B** as before, and "one item" means exactly one item within `GATE_M` whose names (labels, aliases,
  sitelinks) include the stored name (N1/N2), settlements and Wikimedia pages excluded;
* every settled wave-2 entry records that distance (`gate_m`), and `changes()` refuses an entry
  without one or beyond the gate.

A research suggestion is a lead: Ramesses III Temple's rule-B candidate is refused by hand, because
the record contradicts itself (name and point: Karnak; description and source: Medinet Habu).
Everything that no rule settles stays exactly as it is, with its reason. Wave 2 renders into
`output/remediation/qid_repair/wave2/` under its own run stamp (`--wave 2`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - paths, the JSON-lines reader and the read-only psql seam

OUT = lanes.REMEDIATION / "qid_repair"
RUN_STAMP = "2026-09-22_external-id-repair"
ROLLBACK_STAMP = RUN_STAMP + "-rollback"
TABLE = "site_external_ids"
DIGEST_HEADER = "-- plan digest sha256:"
KINDS = ("wikidata_qid", "enwiki_title")


@dataclass(frozen=True)
class Site:
    """One site's re-resolution, as researched on 2026-09-22."""

    site_id: str
    name: str
    rule: str  #: "A", "B" or "unresolved"
    old_qid: str
    new_qid: str | None
    old_title: str
    new_title: str | None
    evidence: tuple[str, ...]
    #: Wave 2: metres from the stored point to the position proof (P625, or rule A's article).
    gate_m: float | None = None


WD = "https://www.wikidata.org/wiki/"
WP = "https://en.wikipedia.org/wiki/"

SITES: tuple[Site, ...] = (
    Site(
        "e8e302a0-70b2-4346-ac75-340a4d6499a2",
        "Argos, Peloponnese",
        "A",
        "Q309",
        "Q189901",
        "History",
        "Argos, Peloponnese",
        (
            f"{WP}Argos,_Peloponnese: the stored name is this article's exact title; its item is "
            "Q189901 'city in Argolis, Peloponnese, Greece' (P31 city, polis), P625 2.14 km from "
            "the stored point",
            f"{WD}Q13533353 'ancient Greek city-state' lies 0.02 km from the stored point but has "
            "no English article; rule A names the article the record is titled after",
        ),
    ),
    Site(
        "1c4ac177-bcca-4044-8e2d-4d15fe0606ab",
        "City of Enns",
        "B",
        "Q309",
        "Q260089",
        "History",
        "Enns (town)",
        (
            "no enwiki article 'City of Enns'",
            f"{WD}Q260089 'Enns' - 'municipality in Linz-Land District, Upper Austria', P625 0.02 km, "
            "enwiki 'Enns (town)': the item the stored name names",
            f"{WD}Q388745 'Lauriacum' (0.02 km) is the Roman city the description is about; the "
            "name is the town, so rule B takes the town and the owner may prefer Lauriacum",
        ),
    ),
    Site(
        "f31b4aea-5e0d-42f8-80f0-60fcf2f3c37f",
        "Clare, Suffolk",
        "A",
        "Q309",
        "Q2559341",
        "History",
        "Clare, Suffolk",
        (
            f"{WP}Clare,_Suffolk: the stored name is this article's exact title; its item is "
            "Q2559341 'town in West Suffolk, England', P625 0.02 km",
        ),
    ),
    Site(
        "7279cb69-c5d2-4b9b-b307-96ef43164e7f",
        "Crantit Chambered Cairn",
        "B",
        "Q309",
        "Q1138920",
        "History",
        None,
        (
            f"{WD}Q1138920 'Crantit' - 'chambered cairn on Mainland, Orkney Islands', P31 chambered "
            "cairn, P625 1.31 km; the record: a Neolithic chambered cairn found 1998 near Kirkwall",
            "no English article (enwiki 'Crantit', 'Crantit tomb', 'Crantit Tomb' missing; the item "
            "links only dewiki 'Crantit Cairn'): the title 'History' has no replacement",
        ),
    ),
    Site(
        "5fffbfc9-f83c-4cd3-9b8d-d2570ce63dbd",
        "Estipeon",
        "B",
        "Q309",
        "Q4810863",
        "History",
        None,
        (
            f"{WD}Q4810863 'Astibo' - 'archaeological site in Macedonia', P31 archaeological site, "
            "P625 0.02 km; the record calls the site 'Estipeon (ancient Astibus)'",
            f"{WD}Q5401395 'Estipeon' carries no statement at all, only a sitelink to a redirect",
            f"{WP}Estipeon and {WP}Astibo both redirect to 'Štip#History' - the section fragment "
            "that became the stored 'History'; no article of its own, so no title replacement",
        ),
    ),
    Site(
        "935c0e07-0e4c-4bf9-a2ea-0113c70a3e3c",
        "Gog Magog Hills",
        "A",
        "Q309",
        "Q369156",
        "History",
        "Gog Magog Hills",
        (
            f"{WP}Gog_Magog_Hills: the stored name is this article's exact title; its item is "
            "Q369156 'range of hills in Cambridgeshire', P625 0.06 km",
        ),
    ),
    Site(
        "52827c54-91cb-4902-99fb-7b0860a71e36",
        "Tlalpan",
        "A",
        "Q309",
        "Q408187",
        "History",
        "Tlalpan",
        (
            f"{WP}Tlalpan: the stored name is this article's exact title; its item is Q408187 "
            "'territorial demarcation of Mexico City' (the borough the record describes), P625 "
            "7.94 km - the borough's centroid, the record's point is the burial find inside it",
        ),
    ),
    Site(
        "4fb5bdfa-4ff6-4897-a54c-7533e2bd2308",
        "Calleva Atrebatum",
        "A",
        "Q23498",
        "Q1027253",
        "Archaeology",
        "Calleva Atrebatum",
        (
            f"{WP}Calleva_Atrebatum: the stored name is this article's exact title; its item is "
            "Q1027253 'Romano-British town at Silchester', P625 0.02 km",
        ),
    ),
    Site(
        "3cde520c-1af6-47b0-84e0-00ec2db63478",
        "Castellum Onagrinum Archaeological Site, Begeč",
        "B",
        "Q23498",
        "Q12756529",
        "Archaeology",
        None,
        (
            f"{WD}Q12756529 labelled 'Castellum Onagrinum' / sr 'Онагринум', srwiki article "
            "'Онагринум', P625 1.14 km from the stored point on the Danube at Begeč",
            f"{WP}Castellum_Onagrinum redirects to 'Begeč#Archaeology' - the fragment that became "
            "the stored 'Archaeology'; no article of its own, so no title replacement",
        ),
    ),
    Site(
        "0f7ccb2e-da01-425e-9a4b-c50f4a785065",
        "Amfiteatar Salona",
        "B",
        "Q11635",
        "Q2844418",
        "Theatre",
        None,
        (
            f"{WD}Q2844418 'Roman amphitheatre of Salona' - 'amphitheatre in Salona, Croatia', P31 "
            "Roman amphitheatre, 0.04 km (WDQS around-search, 0.6 km radius)",
            "no English article: the title 'Theatre' has no replacement",
        ),
    ),
    Site(
        "1f34f490-a5ef-462d-961e-e4bbd8eb5422",
        "Hellenistic-Roman Theatre",
        "B",
        "Q11635",
        "Q70772384",
        "Theatre",
        None,
        (
            f"{WD}Q70772384 'Ancient theatre in Paphos', P31 Roman theatre, 0.05 km (WDQS "
            "around-search, 0.6 km radius); the record: the theatre of Nea Paphos",
            "no English article: the title 'Theatre' has no replacement",
        ),
    ),
    Site(
        "0c00d8bd-d6b3-4237-b4c9-9a86748ee5ab",
        "Κourion Ancient Amphitheatre",
        "B",
        "Q11635",
        "Q4453457",
        "Theatre",
        None,
        (
            f"{WD}Q4453457 'Roman Theatre of Kourion', P31 Roman theatre, 0.02 km (WDQS "
            "around-search, 0.6 km radius); the record: the Greco-Roman theatre of Kourion",
            "no English article: the title 'Theatre' has no replacement",
        ),
    ),
    Site(
        "0e7825f5-26f0-483e-8cd0-687a9228a894",
        "Stabiae",
        "A",
        "Q14832136",
        "Q547910",
        "Temples (band)",
        "Stabiae",
        (
            f"{WP}Stabiae: the stored name is this article's exact title; its item is Q547910 "
            "'ancient city, located near the current Castellammare di Stabia', P625 0.02 km",
            f"{WD}Q14832136 is an English rock band ('Temples (band)')",
        ),
    ),
    Site(
        "30d3fb78-6b80-42f9-87f8-7616e63bec4f",
        "Tikal",
        "unresolved",
        "Q6935864",
        None,
        "Mundo Perdido, Tikal",
        None,
        (
            "the record contradicts itself: its name is Tikal (enwiki 'Tikal' -> Q181172, 0.38 km) "
            "but its description and its source_url are Mundo Perdido, the complex inside Tikal "
            "(Q6935864, 0.14 km) that it is linked to now",
            "which one the record is, is the owner's decision (HUMAN_ONLY B1); nothing is changed",
        ),
    ),
    Site(
        "90e808a1-7ea7-44ce-a1c9-05cf10c133be",
        "Tomb of Artaxerxes III",
        "B",
        "Q129072",
        "Q9630189",
        "Persepolis",
        None,
        (
            f"{WD}Q9630189 'Tomb of Artaxerxes III' - 'tomb in Persepolis, Iran', P31 rock-cut tomb, "
            "0.10 km; Q129072 is Persepolis, the whole site",
            f"{WP}Tomb_of_Artaxerxes_III redirects to 'Persepolis#Tombs'; the item has no English "
            "article, and 'Persepolis' - the article the tomb is described in - stays as the title",
        ),
    ),
    Site(
        "62c8bf00-3a7e-46e6-81ac-2c6fc92af03f",
        "Mount Namsan Belt",
        "B",
        "Q495241",
        "Q66197428",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197428 'Namsam Belt' (sic), P361 part of Q495241 Gyeongju Historic Areas, "
            "P625 1.27 km; the record is that belt, not the whole World Heritage site",
        ),
    ),
    Site(
        "2b0f2420-5602-471f-b4be-eb03e7d33151",
        "The Hwangnyongsa Belt",
        "B",
        "Q495241",
        "Q66197439",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197439 'Hwangnyongsa Belt', P361 part of Q495241, P625 5.33 km: all six "
            "Gyeongju records store the parent's own point (Q495241 is 0.05 km from it), so the "
            "distance is the record's coordinate defect, not the item's",
        ),
    ),
    Site(
        "2dcdec07-a26e-42bc-9490-b277628835f5",
        "The Sanseong Belt",
        "B",
        "Q495241",
        "Q66197443",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197443 'Sanseong Belt', P361 part of Q495241, P625 6.49 km (the record stores "
            "the parent's point)",
        ),
    ),
    Site(
        "44d6f27b-3a9f-49d3-99fa-b1a65380776a",
        "The Tumuli Park Belt",
        "B",
        "Q495241",
        "Q66197435",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197435 'Tumuli Park Belt', P361 part of Q495241, P625 5.12 km (the record "
            "stores the parent's point)",
        ),
    ),
    Site(
        "e8bc112c-9e95-4728-b181-e78d7de1fa26",
        "The Wolseong Belt",
        "B",
        "Q495241",
        "Q66197431",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197431 'Wolseong Belt', P361 part of Q495241, P625 4.57 km (the record stores "
            "the parent's point)",
        ),
    ),
)

#: The `source_url` each settled site should carry for the fix to be a fixed point under the
#: prospector's `--all` path. Listed, not written (module docstring).
GENERIC_SOURCE_URL = {
    "Q309": f"{WP}History",
    "Q23498": f"{WP}Archaeology",
    "Q11635": f"{WP}Theatre",
    "Q14832136": f"{WP}Temples_(band)",
}

#: Wave 2's gate: the position proof of a replacement lies within this many metres of the stored point.
GATE_M = 1000.0
_NONE_NEAR = "no item within 1 km of the stored point and no wbsearchentities hit names the site"


def _unresolved(sid: str, name: str, qid: str, title: str, *why: str) -> Site:
    """A wave-2 site no rule settles: its row stays exactly as it is, and the reason is recorded."""
    return Site(sid, name, "unresolved", qid, None, title, None, tuple(why))


#: The second wave (2026-09-23): every wrong link among the B1 name findings that the first wave did
#: not already replace, researched one at a time (`output/remediation/bcases/qid_research.jsonl`).
WAVE2_SITES: tuple[Site, ...] = (
    Site(
        "aed60d2e-9dec-442b-a7bf-86647aca27b9",
        "Battle at the Harzhorn",
        "A",
        "Q2221906",
        "Q555463",
        "Location",
        "Battle at the Harzhorn",
        (
            f"{WP}Battle_at_the_Harzhorn: the stored name is this article's exact title (no "
            "redirect); its item is Q555463 '235 battle between Roman and Germanic troops' (P31 "
            "battle, battlefield); the article's coordinates are 4 m from the stored point (the "
            "item's own P625 is 2.62 km away, elsewhere on the Harzhorn)",
            f"{WD}Q2221906 is 'geographic location', a generic concept (the source_url is "
            f"{WP}Location)",
        ),
        4.0,
    ),
    Site(
        "db9de243-cfb1-43ad-941a-66e656681236",
        "Dinas Dinlle",
        "B",
        "Q744099",
        "Q20590514",
        "Hillfort",
        None,
        (
            f"{WD}Q20590514 'Dinas Dinlle hillfort' - 'hillfort in Gwynedd', P31 contour fort, "
            "alias 'Dinas Dinlle', P625 507 m: the one site-kind item within 1 km named so; the "
            "record is the Iron Age hillfort",
            f"{WP}Dinas_Dinlle belongs to Q3402467, the village (P31 village), and Q106711669 is "
            "the hill (P31 hill, summit) - places that contain the fort, not the fort",
            f"{WD}Q744099 is 'hillfort', the class; no English article of the fort's own, so the "
            "title 'Hillfort' has no replacement",
        ),
        506.7,
    ),
    Site(
        "2051a8ae-6ce5-4a33-bfa6-997ed2479750",
        "Oushiko Shrine",
        "B",
        "Q11584736",
        "Q11574829",
        "Ishi no Hōden",
        None,
        (
            f"{WD}Q11574829 'Oushiko Shrine' - 'Shinto shrine in Hyōgo Prefecture, Japan', P625 "
            "29 m: the one item within 1 km named so; the record is the shrine",
            f"{WD}Q11584736 'Ishi-no-Hōden' is the stone monument the shrine enshrines, and the "
            "item of the curated row 'Ishi no Hōden Megalith' (a938f9bc); no English article of "
            "the shrine, so the title stays",
        ),
        28.7,
    ),
    Site(
        "ce64147f-624e-474d-92af-b6e84001d54d",
        "Dun Cuier",
        "B",
        "Q11764",
        "Q1265207",
        "Iron Age",
        None,
        (
            f"{WD}Q1265207 'Dun Cuier' - 'tower in Outer Hebrides', P31 broch, dun, P625 419 m: "
            "the one item within 1 km named so",
            f"{WD}Q11764 is 'Iron Age', an archaeological period; no English article of the dun, "
            "so the generic title 'Iron Age' has no replacement",
        ),
        418.7,
    ),
    Site(
        "2bbc9730-d938-4fd5-a8e5-594ea046d183",
        "Yarrows Broch",
        "B",
        "Q11764",
        "Q747937",
        "Iron Age",
        None,
        (
            f"{WD}Q747937 'Broch of Yarrows' - 'tower in Highland', P31 broch, P625 16 m: the one "
            "item within 1 km whose names are the stored name less generic words",
            f"{WD}Q11764 is 'Iron Age', an archaeological period; no English article of the "
            "broch, so the generic title 'Iron Age' has no replacement",
        ),
        16.1,
    ),
    Site(
        "b25ebe2e-145f-403c-8f6a-e26cdb57050e",
        "House of Dionysus",
        "B",
        "Q12065255",
        "Q53556398",
        "Paphos Archaeological Park",
        None,
        (
            f"{WD}Q53556398 'House of Dionysus' - 'archaeological site in Paphos', P31 house, "
            "P625 15 m: the one item within 1 km named so",
            f"{WD}Q12065255 is the Paphos Archaeological Park, linked by 8 curated rows; its "
            "article stays the title (the villa has no English article)",
        ),
        15.2,
    ),
    Site(
        "b4fb0095-3513-4b44-a48b-22c539b1a914",
        "Column of Taharqa",
        "B",
        "Q1306397",
        "Q124887901",
        "Precinct of Amun-Re",
        None,
        (
            f"{WD}Q124887901 'Column of Taharqa', P31 column, P625 12 m: the one item within "
            "1 km named so",
            f"{WD}Q1306397 is the whole Precinct of Amun-Re (also First Pylon's link); its "
            "article stays the title",
        ),
        11.9,
    ),
    Site(
        "5e0e44b0-b557-4ffe-9cc1-7db2d3e3ecfc",
        "First Pylon",
        "B",
        "Q1306397",
        "Q124890504",
        "Precinct of Amun-Re",
        None,
        (
            f"{WD}Q124890504 'First Pylon' - 'unfinished pylon of Nectanebo I in Karnak', P31 "
            "pylon, P625 71 m: the one item within 1 km named so",
            f"{WD}Q1306397 is the whole Precinct of Amun-Re; its article stays the title",
        ),
        71.0,
    ),
    Site(
        "75dac040-12f2-4c78-b989-33cd3f5f07a9",
        "Pyramid of Neferhetepes",
        "B",
        "Q1570082",
        "Q1974158",
        "Pyramid of Userkaf",
        None,
        (
            f"{WD}Q1974158 'Pyramid of Neferhetepes', P31 smooth-sided pyramid, P625 122 m: the "
            "one item within 1 km named so",
            f"{WD}Q1570082 is the Pyramid of Userkaf (the curated row eb760e32); "
            f"{WP}Pyramid_of_Neferhetepes redirects to 'Pyramid of Userkaf', which stays the title",
        ),
        122.0,
    ),
    Site(
        "069e0320-14f7-497f-8239-4ffb969049c1",
        "Idaean Cave",
        "B",
        "Q1643807",
        "Q935991",
        "Psychro Cave",
        None,
        (
            f"{WD}Q935991 'Idaean Cave' - 'stalactite cave in Crete', P31 cave, P625 6 m: the one "
            "item within 1 km named so; the record is the cave on Mount Ida",
            f"{WD}Q1643807 is the Dikteon Andron (Psychro Cave, the curated row f0054526), 56 km "
            f"away; {WP}Idaean_Cave and the new item's sitelink 'Cave of Zeus' both redirect to "
            "'Psychro Cave' - the title names another cave and has no replacement",
        ),
        6.2,
    ),
    Site(
        "7bffddb6-2fc1-49cf-987a-d7e78bdc98c5",
        "Temple of Apollo Epicurius",
        "B",
        "Q464923",
        "Q38278862",
        "Bassae",
        None,
        (
            f"{WD}Q38278862 'Temple of Apollo Epicurius in Bassae' - 'ancient temple in "
            "Peloponnese', P625 33 m: the one item within 1 km named so",
            f"{WD}Q464923 is Bassae, the site (the curated row f4f9740d); the item's sitelink "
            "'Temple of Apollo at Bassae' redirects to 'Bassae', which stays the title",
        ),
        32.7,
    ),
    Site(
        "c2628a93-7c87-4a98-8d13-8301f7063403",
        "Er-Grah Tumulus",
        "B",
        "Q508651",
        "Q1347902",
        "Locmariaquer megaliths",
        None,
        (
            f"{WD}Q1347902 'tumulus d'Er Grah' - 'tumulus in Locmariaquer', P625 56 m: the one "
            "item within 1 km named so",
            f"{WD}Q508651 is the Broken Menhir of Er Grah (the curated row 0cd58c95); the "
            "tumulus has no English article, so the title stays",
        ),
        56.3,
    ),
    _unresolved(
        "3f170e16-175a-4e4c-9717-1f0e32d05e8e",
        "Appolonia Temple Ruins",
        "Q15183441",
        "Apollonia (Lycia)",
        "the only item within 1 km (Q135582527, P31 temple, 53 m) has no label to match; the "
        "record's description is the city of Apollonia, the linked item",
    ),
    _unresolved(
        "78123025-5f8c-433a-9623-a60ea4105600",
        "Giants' Graves",
        "Q1523627",
        "Giants' grave",
        "the record is the monument type across Sardinia (over 800 examples; its point "
        "40.0002, 9.00001 is a placeholder), and Q1523627 is that type; no item is this record",
    ),
    _unresolved(
        "88e024ff-c9a8-4ab6-9158-23033f5356fc",
        "Roman Odeon",
        "Q12065255",
        "Paphos Archaeological Park",
        f"{_NONE_NEAR} (the 'Roman Odeon' items are at Ilion and Gortyn)",
    ),
    _unresolved(
        "db0c6ae2-38d9-47b7-ae27-e6a960c0294e",
        "Nakrang Tombs",
        "Q6606081",
        "List of archaeological sites in Korea",
        _NONE_NEAR,
    ),
    _unresolved(
        "8747ac16-0730-4bdc-8afa-49c3d8d6819b",
        "Stairhaven",
        "Q6696423",
        "Luce Bay",
        f"{_NONE_NEAR}; Q6696423 is Luce Bay, the bay the broch stands on",
    ),
    _unresolved(
        "f8c28568-017a-4b61-903c-bed2ba67bce0",
        "Madera Caves",
        "Q5192640",
        "Cueva de la Momia",
        f"{_NONE_NEAR}; the record is a group of caves, Q5192640 one cave 62 km away",
    ),
    _unresolved(
        "74af1ed2-4221-4e13-8a96-e63631d01cc7",
        "Büyük Hamam",
        "Q595329",
        "Phaselis",
        f"{WP}Büyük_Hamam is a hammam in Nicosia (Q16737790, 294 km); every 'Büyük Hamam' item "
        "is an Ottoman bath elsewhere; none within 1 km",
    ),
    _unresolved(
        "7cabe5b9-0710-4205-a52a-55f3b4003896",
        "Early Roman House",
        "Q12065255",
        "Paphos Archaeological Park",
        _NONE_NEAR,
    ),
    _unresolved(
        "da54a7f3-948a-4da4-a775-68b7d1831d29",
        "Castle of Kirkûk",
        "Q1144137",
        "Kirkuk Citadel",
        "the link is right: the record's description is the Kirkuk Citadel, Q1144137; its P625 "
        "is 23.9 km from the stored point - the stored point is the defect, not the link",
    ),
    _unresolved(
        "d2a5b201-c0b4-4e6e-a59a-7ada41de0099",
        "House of Aion",
        "Q12065255",
        "Paphos Archaeological Park",
        f"{WD}Q55068547 'House of Aion' - 'House in the Paphos Archaeological Park' names it but "
        "carries no P625, so the 1 km gate cannot be shown; left for the owner",
    ),
    _unresolved(
        "7c5f9b35-8195-4121-83b7-f2192a87e1fb",
        "Gudit Stelae Field",
        "Q5832",
        "Axum",
        f"{_NONE_NEAR}; Q5832 is the city of Axum",
    ),
    _unresolved(
        "82c9fb95-c776-4450-bb5c-93a70fdcb056",
        "Hoyo Negro Cenote",
        "Q16888327",
        "Naia (skeleton)",
        f"{_NONE_NEAR}; Q16888327 is the skeleton found there, Sistema Sac Actun (34 m) the cave "
        "system that contains the cenote",
    ),
    _unresolved(
        "68e1b08b-3997-45bf-a5fe-7a6938279ce4",
        "Minoan Modi",
        "Q543876",
        "Minoan peak sanctuaries",
        f"{WD}Q6868919 'Minoan Modi' names it but its P625 is 27.5 km from the stored point: one "
        "of the two points is wrong, a coordinate question before a link one",
    ),
    _unresolved(
        "3845e670-6a97-47b6-b6c4-2387e7465523",
        "Tombs of the Nobles",
        "Q690551",
        "List of Theban tombs",
        f"{WD}Q7818709 'Tombs of the Nobles' - 'Ancient Egyptian necropolis in Thebes' is 1.52 km "
        f"away, beyond the 1 km gate; {WP}Tombs_of_the_Nobles is a disambiguation page",
    ),
    _unresolved(
        "f1b3fa7c-d237-4d82-8d06-831a376ce267",
        "Sun Temple of Niuserre (Abu Ghorab)",
        "Q919238",
        "Egyptian sun temple",
        f"{WD}Q2009417 'Sun temple of Nyuserre' (54 m) is a spelling variant, not one of the "
        "item's names under rule B; left for the owner",
    ),
    _unresolved(
        "917cd017-9d91-4c24-a8e2-1af2f6d04c1e",
        "Cave 20 - Pandavleni Caves",
        "Q7130537",
        "Nasik Caves",
        f"{_NONE_NEAR}; the record is one cave of the Nasik Caves, Q7130537",
    ),
    _unresolved(
        "0f654bf4-86b7-4602-8bee-c8da00f3edee",
        "Roman Temple Qsarnaba",
        "Q7267046",
        "Qasr el Banat, Lebanon",
        "the link is right: the description is the temple Qasr el Banat, Q7267046; its P625 is "
        "22.6 km from the stored point - a coordinate question, not a link one",
    ),
    _unresolved(
        "d41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d",
        "Conjunto Arqueologico de Ñustahispana",
        "Q13191401",
        "Ñusta Hispana",
        "the link is right: Q13191401 is Ñusta Hisp'ana (473 m) and the description names it; the "
        "item is shared because the curated row 'Ñusta Hispana' (dafc7527) is the same site - a "
        "duplicate candidate, not a link repair",
    ),
    _unresolved(
        "c3131199-f90a-43c9-901d-87857f47a6f6",
        "Bruach An Druimein, Kimartin Glen",
        "Q5584221",
        "Kilmartin Glen",
        _NONE_NEAR,
    ),
    _unresolved(
        "2ff6f6ff-dada-465c-ad3b-6db67b57a31b",
        "Karta",
        "Q6373497",
        "Kartan industry",
        f"{_NONE_NEAR}; {WP}Karta is a disambiguation page",
    ),
    _unresolved(
        "2eb96a66-8c29-4a38-a704-7d5c6d153a31",
        "La Cobata",
        "Q3062269",
        "Olmec colossal heads",
        f"{WD}Q5683361 'La Cobata Colossal Head' names the object but carries no P625, so the "
        "1 km gate cannot be shown; left for the owner",
    ),
    _unresolved(
        "b42c7181-73fa-48c8-8916-a6fe7b4b74b1",
        "Kerbatch",
        "Q846901",
        "Senegambian stone circles",
        "the only named item within 1 km is Q1739580 'Kerr Batch', the village; the stone "
        "circles have no item of their own",
    ),
    _unresolved(
        "58a5a5b2-735a-4fda-bf2d-52e723fd86bc",
        "House of the Knight",
        "Q391215",
        "Volubilis",
        _NONE_NEAR,
    ),
    _unresolved(
        "9abf8d9a-b474-44cf-b9da-1761e7a6d1ad",
        "Temple of Amun",
        "Q927825",
        "Mortuary temple",
        f"{WD}Q124958525 'Temple of Amun at Karnak' (75 m) contains the name but is not one of "
        "its names (rule B needs N1/N2); the record's description puts the temple on the west "
        f"bank; {WP}Temple_of_Amun redirects to 'Precinct of Amun-Re' - left for the owner",
    ),
    _unresolved(
        "0b18d71c-7057-4b58-9c49-e3dbcb684d46",
        "Hellenistic House",
        "Q12065255",
        "Paphos Archaeological Park",
        _NONE_NEAR,
    ),
    _unresolved(
        "0e627b04-0c07-4967-9b94-0967a2eca175",
        "Lakkos",
        "Q632418",
        "Archanes",
        f"{WD}Q6479724 'Lakkos' - 'archaeological site in Greece' names it but carries no P625; "
        f"{WP}Lakkos redirects to 'Archanes' - left for the owner",
    ),
    _unresolved(
        "b801d712-8e04-4b96-86dd-cf1b4bb9db11",
        "Petroglyphs of Arpa-Uzen",
        "Q12574694",
        "Karatau Petroglyphs",
        f"{WD}Q7178914 'Petroglyphs of Arpa-Uzen' names it but its P625 is 140 km from the "
        "stored point: one of the two points is wrong, a coordinate question first",
    ),
    _unresolved(
        "4e0540cd-333a-4808-8c4e-fa136957c934",
        "Roman Temple of Hercules",
        "Q3157009",
        "Amman Citadel",
        f"{_NONE_NEAR}; the source_url {WP}Temple_of_Hercules_(Amman) redirects to 'Amman "
        "Citadel#Great Temple', the article the link names",
    ),
    _unresolved(
        "e8a07988-7219-449d-8cd1-612761502bfd",
        "Cocoraque Butte Archaeological District",
        "Q1673152",
        "Ironwood Forest National Monument",
        f"{WD}Q16949635 'Cocoraque Butte Archaeological District' names it but carries no P625; "
        "its English title redirects to 'Ironwood Forest National Monument' - left for the owner",
    ),
    _unresolved(
        "2e4b8483-8599-458c-abcc-29e4e92e2ee3",
        "Runestones of Sweden",
        "Q815241",
        "Runestone",
        "the record is the monument type across Sweden (its point 60.0007, 18.0006 is a "
        "placeholder), and Q815241 is that type; no item is this record",
    ),
    _unresolved(
        "4190c8a6-db2f-442b-8125-f2df42cf51a0",
        "Villa of Theseus",
        "Q12065255",
        "Paphos Archaeological Park",
        _NONE_NEAR,
    ),
    _unresolved(
        "3ebb514f-ac4a-4913-b54b-409bcc29eff4",
        "Ancient Amathunta",
        "Q2343313",
        "Amathus",
        "the link is right: Amathunta is Amathus, Q2343313 (24 m); the item is shared because "
        "the curated row 'Amathus' (51daf6c9, 11 m away) is the same site - a duplicate "
        "candidate, not a link repair",
    ),
    _unresolved(
        "d3a35b0d-cf76-4286-8cd4-2f53e52556ad",
        "Porta Nord Acropoli",
        "Q952173",
        "Selinunte",
        f"{WD}Q140891419 'North Gate' - 'ancient gate of Selinus' (72 m) carries no Italian "
        "name to match 'Porta Nord'; left for the owner",
    ),
    _unresolved(
        "0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3",
        "Tel Hermal Fort",
        "Q3481186",
        "Shaduppum",
        "the link is right: the description reads 'Tel Hermal (ancient Shaduppum)'; the item is "
        "shared because the curated row 'Shaduppum' (f967e3c4, 1.7 km away) is the same site - "
        "a duplicate candidate, not a link repair",
    ),
    _unresolved(
        "54dc63d1-d88f-4d40-976b-460b203a07ef",
        "House of Orpheus",
        "Q12065255",
        "Paphos Archaeological Park",
        f"{_NONE_NEAR} (Q16537624 'House of Orpheus' is in Pompeii)",
    ),
    _unresolved(
        "3a86a102-9b92-4f11-8dcf-4230d3534858",
        "Ramesses III Temple",
        "Q932622",
        "Medinet Habu",
        "the record contradicts itself: its name and point are the Karnak temple of Ramesses III "
        f"({WD}Q124894323, 27 m - the research's rule-B lead), its description and source_url "
        "the mortuary temple at Medinet Habu (Q932622, the curated row 274ff0f7); which one the "
        "record is, is the owner's decision (like Tikal)",
    ),
    _unresolved(
        "c8b957fb-37fa-46eb-84fd-39e572072d05",
        "Satellite Pyramid (to Bent Pyramid)",
        "Q459608",
        "Bent Pyramid",
        _NONE_NEAR,
    ),
    _unresolved(
        "6c09f12a-a657-4395-8bc6-d3903f4eaa27",
        "Clachtoll Broch",
        "Q7085578",
        "List of oldest buildings in Scotland",
        f"{WD}Q2794073 'Clachtoll Broch' names it at 1.13 km, beyond the 1 km gate; the stored "
        "point is Stoer village (15 m) - a coordinate question first",
    ),
    _unresolved(
        "cfc78356-fc53-48b9-b1d5-6bb1c7f86426",
        "Ναός Σωτήρου Διός",
        "Q823721",
        "Megalopolis, Greece",
        f"{_NONE_NEAR} (the sanctuary of Zeus Soter at Megalopolis)",
    ),
    _unresolved(
        "b78239e5-3b96-4537-9cab-b700c3d7335c",
        "Milecastles - Hadrian's Wall",
        "Q1568283",
        "Milecastle",
        "the record is all 80 milecastles of Hadrian's Wall, and Q1568283 is that type; no item "
        "is this record",
    ),
    _unresolved(
        "87d83a5b-d7a2-45dc-b8fd-1bed588bbeec",
        "Bhimashankar Buddhist Caves",
        "Q42873620",
        "Manmodi Caves",
        f"{_NONE_NEAR}; the record is one group of the Manmodi caves, Q42873620",
    ),
    _unresolved(
        "8ef3e56e-3dd8-4576-a5bf-eab965bcd0a7",
        "Bhutalinga Buddhist Caves",
        "Q42873620",
        "Manmodi Caves",
        f"{_NONE_NEAR}; the record is one group of the Manmodi caves, Q42873620",
    ),
    _unresolved(
        "0fd636ac-1a80-4a77-b9d0-a065ae811656",
        "Bosnian Pyramid of the Moon",
        "Q746765",
        "Bosnian pyramid claims",
        f"{_NONE_NEAR} (the record is Pljesevica hill)",
    ),
    _unresolved(
        "1d65f378-c797-47d7-827c-252df5243d13",
        "Rocca San Felice",
        "Q467594",
        "Mefitis",
        "the record contradicts itself: named and placed at the town (the article's item Q55085 "
        "is the comune, 18 m), described as the Mefitis sanctuary in the Ansanto valley; which "
        "one the record is, is the owner's decision",
    ),
    _unresolved(
        "f23a31c3-6833-4df6-8583-3b3930b5a74f",
        "Thirty-nine (39) Bridge Street, Chester",
        "Q4636108",
        "39 Bridge Street, Chester",
        "the link is right: Q4636108 is the building (2 m); the item is shared because the "
        "curated row 'Bridge Street Number 39, Chester' (21ac323f, 11 m away) is the same "
        "building - a duplicate candidate, not a link repair",
    ),
    _unresolved(
        "4c5103a2-0ae8-443d-9203-f3a4bf4bbd6f",
        "The Ancient Lycian Mezarı2",
        "Q7818606",
        "Tomb of Amyntas",
        "the description is the Tomb of Amyntas, Q7818606, which the curated row 'Amyntas Rock "
        "Tombs' (e19f7af0, 1.1 km away) also carries; the name is garbled - which tomb the row "
        "is, is the owner's reading",
    ),
    _unresolved(
        "edcaeefb-884f-4f74-b33c-1b3c44ed7c2d",
        "Makry Gialos",
        "Q839954",
        "Archaeological site",
        f"{WP}Makry_Gialos belongs to Q2251628, the municipal unit - not the Minoan villa; no "
        "item of the villa within 1 km",
    ),
)


@dataclass(frozen=True)
class Wave:
    """One reviewed repair: its sites, its journal stamp, where it renders, its evidence label."""

    number: int
    sites: tuple[Site, ...]
    run_stamp: str
    out: pathlib.Path
    research: str
    #: The position gate a settled site must pass (wave 2); wave 1's rules predate it.
    gate_m: float | None

    @property
    def rollback_stamp(self) -> str:
        return self.run_stamp + "-rollback"


WAVE1 = Wave(1, SITES, RUN_STAMP, OUT, "qid-repair research 2026-09-22", None)
WAVE2 = Wave(
    2,
    WAVE2_SITES,
    "2026-09-23_external-id-repair-wave2",
    OUT / "wave2",
    "qid-repair research 2026-09-23 (wave 2)",
    GATE_M,
)
WAVES = {wave.number: wave for wave in (WAVE1, WAVE2)}


@dataclass(frozen=True)
class Change:
    """One conditional update of one `site_external_ids` row, and what the journal records."""

    site_id: str
    name: str
    kind: str
    old_value: str
    new_value: str
    test_id: str
    confidence: str
    evidence: tuple[str, ...]
    change_key: str

    @property
    def row_pk(self) -> str:
        """The journal's `row_pk`: the site and the kind, which name the row across the change."""
        return f"{self.site_id}/{self.kind}"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def change_key(site_id: str, kind: str, old: str, new: str, test_id: str) -> str:
    parts = json.dumps([site_id, TABLE, kind, old, new, test_id], ensure_ascii=False)
    return "external-id:" + hashlib.sha256(parts.encode("utf-8")).hexdigest()


def changes(sites: tuple[Site, ...] = SITES, *, gate_m: float | None = None) -> list[Change]:
    """Every row the plan changes, in site order then kind order. An unresolved site has none.

    With `gate_m` (wave 2) a settled site must carry the distance of its position proof, and that
    distance must lie within the gate - the replacement is the site's place, not a namesake's.
    """
    out: list[Change] = []
    seen: set[str] = set()
    for site in sites:
        if site.site_id in seen:
            raise SystemExit(f"{site.site_id} is planned twice")
        seen.add(site.site_id)
        if site.rule == "unresolved":
            if site.new_qid is not None or site.new_title is not None:
                raise SystemExit(f"{site.name}: an unresolved site cannot carry a new value")
            continue
        if site.rule not in ("A", "B") or site.new_qid is None:
            raise SystemExit(f"{site.name}: rule {site.rule!r} with new qid {site.new_qid!r}")
        if gate_m is not None and (site.gate_m is None or not 0 <= site.gate_m <= gate_m):
            raise SystemExit(
                f"{site.name}: a replacement needs its position proof within {gate_m:.0f} m, "
                f"not {site.gate_m!r}"
            )
        confidence = "two_source" if site.rule == "A" else "authoritative"
        pairs = [("wikidata_qid", site.old_qid, site.new_qid)]
        if site.new_title is not None:
            pairs.append(("enwiki_title", site.old_title, site.new_title))
        for kind, old, new in pairs:
            if old == new:
                raise SystemExit(f"{site.name}: {kind} {old!r} is not a change")
            test_id = f"EXT/{kind}"
            out.append(
                Change(
                    site_id=site.site_id,
                    name=site.name,
                    kind=kind,
                    old_value=old,
                    new_value=new,
                    test_id=test_id,
                    confidence=confidence,
                    evidence=site.evidence,
                    change_key=change_key(site.site_id, kind, old, new, test_id),
                )
            )
    return out


def plan_digest(rows: list[Change]) -> str:
    return hashlib.sha256("".join(row.to_json_line() + "\n" for row in rows).encode()).hexdigest()


def _evidence_json(row: Change, source: str) -> str:
    entries = [{"source": source, "quote": line, "url": None} for line in row.evidence]
    return lanes.sql_text(json.dumps(entries, ensure_ascii=False)) + "::jsonb"


def render(
    rows: list[Change], *, reversal: bool, rehearsal: bool = False, wave: Wave = WAVE1
) -> str:
    """One transaction over every row: guards, one conditional update and one journal row each,
    invariants, then `COMMIT` - or `ROLLBACK` for the rehearsal."""
    if not rows:
        raise SystemExit("refusing to render a statement with no rows")
    stamp = wave.rollback_stamp if reversal else wave.run_stamp
    what = "reversal" if reversal else "repair"
    values = []
    for row in rows:
        old, new = (row.new_value, row.old_value) if reversal else (row.old_value, row.new_value)
        key = row.change_key + ("-rollback" if reversal else "")
        values.append(
            f"    ({lanes.sql_text(row.site_id)}::uuid, {lanes.sql_text(row.kind)}, {lanes.sql_text(old)}, {lanes.sql_text(new)}, "
            f"{lanes.sql_text(key)}, {lanes.sql_text(row.test_id)}, {lanes.sql_text(row.confidence)}, {_evidence_json(row, wave.research)})"
        )
    lines = [
        "-- Generated by output/remediation/tools/qid_repair.py - do not edit by hand.",
        f"{DIGEST_HEADER}{plan_digest(rows)}",
        f"-- the {what} of {len(rows)} site_external_ids row(s); run stamp '{stamp}'.",
        "-- Every row is addressed by its full key (site_id, kind, value = the old value) and must",
        "-- match exactly one row; its journal row is written in the same transaction.",
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        "",
        "CREATE TEMP TABLE _ext_plan (",
        "    site_id    UUID NOT NULL,",
        "    kind       TEXT NOT NULL,",
        "    old_value  TEXT NOT NULL,",
        "    new_value  TEXT NOT NULL,",
        "    change_key TEXT NOT NULL,",
        "    test_id    TEXT NOT NULL,",
        "    confidence TEXT NOT NULL,",
        "    evidence   JSONB NOT NULL,",
        "    PRIMARY KEY (site_id, kind)",
        ") ON COMMIT DROP;",
        "",
        "INSERT INTO _ext_plan (site_id, kind, old_value, new_value, change_key, test_id,",
        "                       confidence, evidence) VALUES",
        ",\n".join(values) + ";",
        "",
        "DO $$",
        "DECLARE",
        "    bad      INTEGER;",
        "    n        INTEGER;",
        "    moved    INTEGER := 0;",
        f"    expected INTEGER := {len(rows)};",
        "    r        RECORD;",
        "BEGIN",
        "    -- guard 1: every site is a curated site that still exists",
        "    SELECT count(*) INTO bad FROM _ext_plan p LEFT JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';",
        "    IF bad > 0 THEN RAISE EXCEPTION 'external-id repair: % row(s) are not curated sites', bad;",
        "    END IF;",
        "    -- guard 2: each site has exactly one row of the kind, and it holds the planned old value",
        "    SELECT count(*) INTO bad FROM _ext_plan p",
        "     WHERE (SELECT count(*) FROM site_external_ids e",
        "             WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1",
        "        OR NOT EXISTS (SELECT 1 FROM site_external_ids e WHERE e.site_id = p.site_id",
        "                          AND e.kind = p.kind AND e.value = p.old_value);",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'external-id repair: % row(s) no longer hold the planned old value', bad;",
        "    END IF;",
        "    -- the writes: one conditional update and one journal row each, exactly one row matched",
        "    FOR r IN SELECT * FROM _ext_plan ORDER BY site_id, kind LOOP",
        f"        UPDATE {TABLE} SET value = r.new_value",
        "         WHERE site_id = r.site_id AND kind = r.kind AND value = r.old_value;",
        "        GET DIAGNOSTICS n = ROW_COUNT;",
        "        IF n <> 1 THEN",
        "            RAISE EXCEPTION 'external-id repair: %/% matched % row(s), not 1',",
        "                r.site_id, r.kind, n;",
        "        END IF;",
        "        INSERT INTO remediation_change_log (run_stamp, test_id, table_name, column_name,",
        "            row_pk, old_value, new_value, change_key, confidence, evidence, site_id_ref)",
        f"        VALUES ({lanes.sql_text(stamp)}, r.test_id, {lanes.sql_text(TABLE)}, 'value',",
        "            r.site_id::text || '/' || r.kind, r.old_value, r.new_value, r.change_key,",
        "            r.confidence, r.evidence, r.site_id);",
        "        moved := moved + n;",
        "    END LOOP;",
        "    IF moved <> expected THEN",
        "        RAISE EXCEPTION 'external-id repair: % row(s) changed, % planned', moved, expected;",
        "    END IF;",
        "    -- invariant 1: every row now holds the new value, read back by its full key",
        "    SELECT count(*) INTO bad FROM _ext_plan p",
        "     WHERE (SELECT count(*) FROM site_external_ids e WHERE e.site_id = p.site_id",
        "             AND e.kind = p.kind AND e.value = p.new_value) <> 1",
        "        OR (SELECT count(*) FROM site_external_ids e",
        "             WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1;",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'external-id repair: % row(s) do not hold the new value', bad;",
        "    END IF;",
        "    -- invariant 2: the journal and the plan agree in both directions",
        "    SELECT count(*) INTO bad FROM _ext_plan p LEFT JOIN remediation_change_log l",
        f"        ON l.run_stamp = {lanes.sql_text(stamp)} AND l.change_key = p.change_key",
        f"       AND l.table_name = {lanes.sql_text(TABLE)} AND l.row_pk = p.site_id::text || '/' || p.kind",
        "       AND l.old_value = p.old_value AND l.new_value = p.new_value",
        "     WHERE l.id IS NULL;",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'external-id repair: % row(s) have no matching journal row', bad;",
        "    END IF;",
        "    SELECT count(*) INTO bad FROM remediation_change_log l",
        f"     WHERE l.run_stamp = {lanes.sql_text(stamp)}",
        "       AND NOT EXISTS (SELECT 1 FROM _ext_plan p WHERE p.change_key = l.change_key);",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'external-id repair: this stamp journalled % row(s) outside the plan',",
        "            bad;",
        "    END IF;",
        "    RAISE NOTICE 'external-id repair: % row(s) changed and journalled', moved;",
        "END $$;",
        "",
        "ROLLBACK;" if rehearsal else "COMMIT;",
        "",
        "SELECT 'journal rows for this stamp' AS metric, count(*)::text AS value",
        f"  FROM remediation_change_log WHERE run_stamp = {lanes.sql_text(stamp)};",
        "",
    ]
    return "\n".join(lines)


def statements(rows: list[Change], wave: Wave = WAVE1) -> dict[str, str]:
    """Every SQL file the runbook runs, as `render` writes it."""
    return {
        "APPLY.sql": render(rows, reversal=False, wave=wave),
        "REHEARSAL.sql": render(rows, reversal=False, rehearsal=True, wave=wave),
        "ROLLBACK.sql": render(rows, reversal=True, wave=wave),
    }


def assert_rendered(out: pathlib.Path, rows: list[Change], wave: Wave = WAVE1) -> None:
    """Refuse a statement on disk that is not, byte for byte, the one `render` makes from the plan.

    The digest header alone would pass a hand-edited body under an untouched header - and these files
    are run against production as they are. So every file is compared whole.
    """
    for name, sql in statements(rows, wave).items():
        path = out / name
        if not path.exists():
            raise SystemExit(f"{path} does not exist; run `render` first")
        if path.read_text(encoding="utf-8") != sql:
            raise SystemExit(
                f"{path} is not the statement this plan renders (edited by hand, or rendered from "
                "another plan); run `render` again and read the diff"
            )


def plan_markdown(rows: list[Change]) -> str:
    settled = [site for site in SITES if site.rule != "unresolved"]
    lines = [
        "# The repair of mis-resolved `site_external_ids` rows (2026-09-22) - planned, not applied",
        "",
        f"{len(rows)} row changes at {len(settled)} sites (run stamp `{RUN_STAMP}`); "
        f"{len(SITES) - len(settled)} site unresolved. Rendered by "
        "`output/remediation/tools/qid_repair.py` - the module docstring states the two rules, why "
        "the statements do not use `apply_remediation_change`, and the fixed point.",
        "",
        "| site | rule | wikidata_qid | enwiki_title | evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for site in SITES:
        qid = (
            f"`{site.old_qid}` -> `{site.new_qid}`"
            if site.new_qid
            else f"`{site.old_qid}` (unchanged)"
        )
        title = (
            f"`{site.old_title}` -> `{site.new_title}`"
            if site.new_title
            else f"`{site.old_title}` (unchanged)"
        )
        lines.append(
            f"| {site.name} (`{site.site_id}`) | {site.rule} | {qid} | {title} | "
            + "<br>".join(site.evidence)
            + " |"
        )
    generic = [
        site
        for site in SITES
        if site.new_title is None and site.old_title in ("History", "Archaeology", "Theatre")
    ]
    lines += [
        "",
        "## Left as they are, and why",
        "",
        f"* **Generic `enwiki_title` with no replacement ({len(generic)})**: "
        + ", ".join(f"{site.name} (`{site.old_title}`)" for site in generic)
        + ". The repaired item has no English article, so the only fix is to delete the row - a "
        "deletion is the owner's call, and the prospector's dedup reads the title as a hard id "
        "(a candidate called 'Theatre' would match three curated sites) until then.",
        "* **Tikal**: unresolved - the record is named Tikal and describes Mundo Perdido (HUMAN_ONLY "
        "B1).",
        "* **`unified_sites.source_url`** of the settled sites still names the generic article "
        "(`" + "`, `".join(sorted(GENERIC_SOURCE_URL.values())) + "`). It is the root cause: "
        "`external_ids.py` resolves ids from it, so `refresh_site_external_ids(only_missing=False)` "
        "would add the generic id back beside the repaired one. The boot path "
        "(`only_missing=True`) does not. Correcting `source_url` is a separate change to a column "
        "many producers read (ingesters, the content linker, the image resolvers) and needs its "
        "own fixed-point analysis.",
        "* The already-judged sites whose phase-3 Wikidata evidence was the wrong item should be "
        "re-judged after the repair: City of Enns, Crantit Chambered Cairn, Castellum Onagrinum, the "
        "three theatres and four of the Gyeongju belts (Mount Namsan, Hwangnyongsa, Sanseong, Tumuli "
        "Park); the gap run (output/remediation/gap/GAP_PLAN.md) re-asks the other ten.",
        "",
        "## How to run it (the orchestrator's job, in this order)",
        "",
        "```bash",
        "./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py render    # REHEARSAL.sql is not versioned",
        "./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py check     # read-only",
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/REHEARSAL.sql',
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/APPLY.sql',
        "./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py verify    # read-only",
        "```",
        "",
    ]
    return "\n".join(lines)


def wave2_markdown(rows: list[Change]) -> str:
    """Wave 2's decision record: every researched site, settled or not, with its evidence."""
    wave = WAVE2
    settled = [site for site in wave.sites if site.rule != "unresolved"]
    lines = [
        "# External-id repair, wave 2 (2026-09-23) - planned, not applied",
        "",
        f"{len(rows)} row changes at {len(settled)} sites (run stamp `{wave.run_stamp}`); "
        f"{len(wave.sites) - len(settled)} sites unresolved and left exactly as they are. The 59 "
        "sites are the wrong links among the B1 name findings whose name does not match, that wave 1 "
        "did not already replace (`output/remediation/bcases/names.jsonl`, classes Q1-Q4; the 72 kept "
        "names on a suspect link, `link_suspect`, are not in this wave); the research record is "
        "`output/remediation/bcases/qid_research.jsonl`, the rules and the 1 km gate are in the "
        "module docstring of `output/remediation/tools/qid_repair.py`.",
        "",
        "| site | rule | wikidata_qid | enwiki_title | gate | evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for site in sorted(wave.sites, key=lambda s: (s.rule == "unresolved", s.name)):
        qid = f"`{site.old_qid}` -> `{site.new_qid}`" if site.new_qid else f"`{site.old_qid}`"
        title = (
            f"`{site.old_title}` -> `{site.new_title}`" if site.new_title else f"`{site.old_title}`"
        )
        gate = "" if site.gate_m is None else f"{site.gate_m:.0f} m"
        lines.append(
            f"| {site.name} (`{site.site_id}`) | {site.rule} | {qid} | {title} | {gate} | "
            + "<br>".join(site.evidence)
            + " |"
        )
    lines += [
        "",
        "## Left as they are, and why",
        "",
        "* Every unresolved row above keeps its link: a replacement the rules cannot prove is worse "
        "than a known-bad anchor (dedup trusts item ids). Seven of them are right links on a record "
        "whose own point or name is the defect (Castle of Kirkûk, Roman Temple Qsarnaba) or on a "
        "second curated row of the same site (Ancient Amathunta, Tel Hermal Fort, Ñustahispana, "
        "39 Bridge Street, the Lycian tomb) - duplicate candidates for the owner, not link repairs.",
        "* The same fixed point as wave 1: `unified_sites.source_url` of the settled sites still "
        "names the article the old id came from (`Location`, `Hillfort`, `Iron_Age`, the parent "
        "sites' articles), so `refresh_site_external_ids(only_missing=False)` would add the old id "
        "back beside the repaired one; the boot path (`only_missing=True`) does not.",
        "* `gap_plan.py` withholds the links of wave 1 only (`qid_repair.SITES`); the gap lane's "
        "plan is already built, so wave 2's wrong links are named here for its next re-plan.",
        "",
        "## How to run it (the orchestrator's job, in this order)",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        "$PY output/remediation/tools/qid_repair.py render --wave 2   # REHEARSAL.sql is not versioned",
        "$PY output/remediation/tools/qid_repair.py check --wave 2    # read-only",
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave2/REHEARSAL.sql',
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave2/APPLY.sql',
        "$PY output/remediation/tools/qid_repair.py verify --wave 2   # read-only",
        "```",
        "",
    ]
    return "\n".join(lines)


def write_files(out: pathlib.Path = OUT, wave: Wave = WAVE1) -> list[Change]:
    rows = changes(wave.sites, gate_m=wave.gate_m)
    out.mkdir(parents=True, exist_ok=True)
    (out / "PLAN.jsonl").write_text(
        "".join(row.to_json_line() + "\n" for row in rows), encoding="utf-8", newline="\n"
    )
    for name, sql in statements(rows, wave).items():
        (out / name).write_text(sql, encoding="utf-8", newline="\n")
    markdown = plan_markdown(rows) if wave.number == 1 else wave2_markdown(rows)
    (out / "PLAN.md").write_text(markdown, encoding="utf-8", newline="\n")
    return rows


def read_rows(rows: list[Change], *, run: Callable[[str], str]) -> dict[tuple[str, str], list[str]]:
    """`{(site_id, kind): [values]}` for the planned rows, read-only."""
    ids = sorted({row.site_id for row in rows})
    found: dict[tuple[str, str], list[str]] = {}
    sql = (
        "SELECT to_jsonb(t)::text FROM (SELECT site_id::text AS site_id, kind, value "
        f"FROM {TABLE} WHERE site_id::text IN ({lanes.sql_literals(ids)}) "
        f"AND kind IN ({lanes.sql_literals(KINDS)})) t;"
    )
    for record in lanes.json_rows(run(sql)):
        found.setdefault((record["site_id"], record["kind"]), []).append(record["value"])
    return found


def compare(rows: list[Change], found: dict[tuple[str, str], list[str]], *, want: str) -> list[str]:
    """What differs from the plan's `old` (pre-flight) or `new` (after the apply) values."""
    problems = []
    for row in rows:
        expected = row.old_value if want == "old" else row.new_value
        values = found.get((row.site_id, row.kind), [])
        if values != [expected]:
            problems.append(f"{row.name} {row.kind}: expected [{expected!r}], found {values!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qid-repair")
    parser.add_argument("command", choices=("render", "check", "verify"))
    parser.add_argument("--wave", type=int, choices=sorted(WAVES), default=1)
    parser.add_argument("--dir", default=None, help="where the plan and statements live")
    parser.add_argument("--host", default=lanes.HOST)
    args = parser.parse_args(argv)
    wave = WAVES[args.wave]
    out = pathlib.Path(args.dir) if args.dir else wave.out
    if args.command == "render":
        rows = write_files(out, wave)
        print(f"{len(rows)} changes rendered into {out} (digest {plan_digest(rows)[:16]})")
        return 0
    rows = [
        Change(**{**r, "evidence": tuple(r["evidence"])})
        for r in lanes.read_jsonl(out / "PLAN.jsonl")
    ]
    if rows != changes(wave.sites, gate_m=wave.gate_m):
        raise SystemExit("PLAN.jsonl is not the plan this script renders; run `render` again")
    assert_rendered(out, rows, wave)

    def run(sql: str) -> str:
        return lanes.psql(sql, host=args.host)

    problems = compare(
        rows, read_rows(rows, run=run), want="old" if args.command == "check" else "new"
    )
    for problem in problems:
        print(f"  DEVIATION {problem}")
    if args.command == "verify" and not problems:
        journal = lanes.json_rows(
            run(
                "SELECT to_jsonb(t)::text FROM (SELECT change_key FROM remediation_change_log "
                f"WHERE run_stamp = {lanes.sql_text(wave.run_stamp)}) t;"
            )
        )
        keys = {record["change_key"] for record in journal}
        if keys != {row.change_key for row in rows}:
            problems.append(
                f"journal holds {len(keys)} rows for {wave.run_stamp}, the plan {len(rows)}"
            )
            print(f"  DEVIATION {problems[-1]}")
    print(f"{args.command}: {len(rows)} rows, {len(problems)} deviation(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
