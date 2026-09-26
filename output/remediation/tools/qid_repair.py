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

## Wave 3 (2026-09-23): the kept names on a suspect link

Wave 2 was applied on 2026-09-23 (13 rows, run stamp `2026-09-23_external-id-repair-wave2`). Wave 3
takes the 39 B1 name findings whose name matched ("keep") while their link met Q1 (a generic concept)
or Q2 (an item other curated rows share) on its own - `link_suspect` in `names.jsonl`; a link that is
only far away (Q4 alone) is a coordinate question first and stays out. The research is wave 2's, rule
for rule and with the same 1 km gate (`run.py research --suspects`, record
`output/remediation/bcases/qid_research_suspects.jsonl`), plus the curated rows that share each item.

A matched name makes most of these links right, so a wave-3 site that keeps its link says why
(`Site.rule`): **keep-type** - the record *is* the type ("Dolmens of Sardinia": over 200 dolmens in
one record), as wave 2 kept Giants' Graves; **duplicate-candidate** - the item is shared because another
curated row is the same site, the owner's merge and not a link repair; **link-right** - the suspicion
does not hold (the other row's link was wave 2's repair, or the other row is a part of this site);
**unresolved** - no rule proves a replacement. Only **A**/**B** change a row, under the gate. Wave 3
renders into `output/remediation/qid_repair/wave3/` under its own run stamp (`--wave 3`).

## Wave 4 (2026-09-23): the curated `source_url` values that hold two URLs

Twenty `unified_sites` rows - all curated, all from the 2026-03-04 import - carry
`source_url = '<url1>\\n<url2>'`, and no other row of the table carries a control character there.
Nineteen are Mesoamerican sites with a megalithic.co.uk URL first and (except Cantil de las animas,
whose second URL is a blog) an English Wikipedia article second, so `refresh_site_external_ids`
(which reads `source_url LIKE 'https://en.wikipedia.org/wiki/%'`) never gave them an id. Petra has the
article first and a Khan Academy page second: `enwiki_title_from_url` took the whole value for a
title, the API answered it as `invalid`, and `_parse_query` stored it (both fixed in
`pipeline/lyra/prospector/wiki.py`). The orchestrator's decisions (2026-09-23):

* `source_url` keeps the **first** URL, the curator's order; the old value stays in the journal. The
  write goes through `apply_remediation_change()` (its allow-list names the table `unified_sites`,
  migrations 0017/0018/0022 - every column of it).
* the English Wikipedia URL (second for 18 Mesoamerican sites, first for Petra) becomes
  `enwiki_title` + `wikidata_qid` through the **same path** the boot refresh takes
  (`enwiki_title_from_url` + `resolve_titles`: the canonical title after redirects, the page's item);
  Petra's broken title is corrected. A resolution that finds no page, a disambiguation page, an
  item that is a place (a settlement, an administrative unit or a natural feature - P31 judged by
  `bcases.qid_research.is_site_kind`, the gate of waves 2 and 3; orchestrator decision
  2026-09-23), or an item another curated site already carries is not written, for both kinds;
  it is listed with its reason, and a shared item as a duplicate candidate. A refusal the rule
  gets wrong is overridden only by a hand-read entry (`WAVE4_HAND_READ`, like wave 2's hand
  entries) that names that very refusal and quotes its evidence: Petra, whose item carries the
  class "city" beside "ancient city" and "archaeological site".
* a new `(site, kind)` row is an `INSERT` with old value `NULL` ("no row"), guarded by "no row of
  that kind exists"; its reversal deletes exactly that row, conditional on its value, and journals it.

`resolve --wave 4` reads production (read-only) and asks Wikipedia (the project user agent) and
writes `wave4/RESOLUTION.json`; `render --wave 4` plans from that file alone. Once migration 0023
(`CHECK (source_url !~ '[\\x00-\\x1f\\x7f]')`) is applied, the `source_url` half of this wave's
ROLLBACK.sql can no longer run: the constraint refuses the two-URL value it would restore.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - paths, the JSON-lines reader and the read-only psql seam
from bcases import collect as bcases_collect  # noqa: E402 - the research's Wikidata reads
from bcases import inputs as bcases_inputs  # noqa: E402
from bcases.qid_research import is_site_kind  # noqa: E402 - waves 2-3's gate
from census.fetch import Fetcher  # noqa: E402

from pipeline.lyra.prospector.wiki import (  # noqa: E402
    CONTROL_RE,
    TitleResolution,
    enwiki_title_from_url,
    resolve_titles,
)

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
    rule: str  #: "A" or "B" (a change), or one of `UNCHANGED` (none)
    old_qid: str
    new_qid: str | None
    old_title: str
    new_title: str | None
    evidence: tuple[str, ...]
    #: Wave 2: metres from the stored point to the position proof (P625, or rule A's article).
    gate_m: float | None = None


WD = "https://www.wikidata.org/wiki/"
WP = "https://en.wikipedia.org/wiki/"

#: The rules that leave a site's rows exactly as they are. Waves 1 and 2 know only "unresolved"; wave 3
#: says why a suspect link stays (module docstring).
UNCHANGED = ("keep-type", "duplicate-candidate", "link-right", "unresolved")

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


def _leave(rule: str, sid: str, name: str, qid: str, title: str, *why: str) -> Site:
    """A wave-3 site whose rows stay exactly as they are, under the reason `rule` names."""
    return Site(sid, name, rule, qid, None, title, None, tuple(why))


_SAME = "is the same site - a duplicate candidate, not a link repair"
_LISTED = "listed in output/remediation/bcases/DUPLICATES.jsonl"
_UNLISTED = "not in DUPLICATES.jsonl, whose rule needs both names to be the item's names"

#: The third wave (2026-09-23): every kept name on a generic or shared link, researched one at a time
#: (`output/remediation/bcases/qid_research_suspects.jsonl`); production read 2026-09-23 for who
#: shares each item after wave 2.
WAVE3_SITES: tuple[Site, ...] = (
    Site(
        "1c57e536-a94f-4b39-a578-a448932a4cb5",
        "Ancient Theatre of Megalopolis",
        "B",
        "Q823721",
        "Q22681531",
        "Megalopolis, Greece",
        None,
        (
            f"{WD}Q22681531 'Ancient Theater of Megalopolis' - 'ancient Greek theatre in "
            "Megalopoli, Greece', P31 Greek theatre, name 'Theatre of Megalopolis', P625 31 m: "
            "the one item within 1 km named so; the record is the theatre of c. 370 BC",
            f"{WD}Q823721 'Megalopoli' is the modern town ('modern town in Arcadia, Greece', P31 "
            "town, P625 1.25 km) - the kept name only contains the town's name - and the link of "
            "the curated row 'Ναός Σωτήρου Διός' (cfc78356); the theatre has no English article, so "
            "the title 'Megalopolis, Greece' stays",
        ),
        31.1,
    ),
    Site(
        "dbbef6f8-f2bb-4ea3-9691-90c09205f678",
        "Siega Verde",
        "B",
        "Q552106",
        "Q2717874",
        "Prehistoric Rock Art Sites in the Côa Valley and Siega Verde",
        None,
        (
            f"{WD}Q2717874 'Siega Verde' - 'cultural property in Villar de Argañán, Spain', P31 "
            "petroglyph, archaeological site, P625 16 m: the one item within 1 km named so; the "
            "record is the Spanish rock-art site on the Águeda",
            f"{WD}Q552106 is the Côa Valley rock art in Portugal ('paleolithic archaeological site "
            "in Portugal', P625 53.5 km away), the link of the curated row 'Prehistoric Rock Art "
            f"Sites in the Côa Valley and Siega Verde' (74ef6000); {WP}Siega_Verde and the new "
            "item's sitelink 'Siega Verde' redirect to that joint article, which stays the title",
        ),
        16.4,
    ),
    _leave(
        "keep-type",
        "b0b49640-6fb4-4cb1-b875-01dc81298e34",
        "Dolmens of Sardinia",
        "Q101659",
        "Dolmen",
        "the record is the monument type across the island ('Sardinia hosts over 200 dolmens "
        "...'), its point one spot standing for Sardinia (no dolmen item within 1 km), and "
        "Q101659 'dolmen' is that type; no item is this record - the type link stays, as wave 2 "
        "kept Giants' Graves",
    ),
    _leave(
        "keep-type",
        "a777855f-56f5-4860-8707-d90dfb1f5053",
        "Nuraghes of Sardinia",
        "Q688292",
        "Nuraghe",
        "the record is the monument type across the island ('More than 7,000 nuraghes have been "
        "catalogued'), and Q688292 'nuraghe' is that type; the nearest item, an unlabelled "
        "nuraghe (Q122327476, 38 m), is one of the 7,000, not the record - the type link stays",
    ),
    _leave(
        "keep-type",
        "d91a6d50-451d-42b1-9276-35b97c52bf5d",
        "Milefortlet - Hadrians Wall",
        "Q1568283",
        "Milecastle",
        "the record is the milefortlets of the Cumbrian coast as a type ('Milefortlets were small "
        "Roman forts extending Hadrian's Wall defensive system along the Cumbrian coast'), on the "
        "placeholder point of 'Milecastles - Hadrian's Wall' (b78239e5, 0 m) - two type records "
        "on one type item, not one site twice",
        "Wikidata has no milefortlet type: its milefortlets are instances of Q1568283 "
        f"({WD}Q16247408 'Milefortlet 1' ... {WD}Q6851204 'Milefortlet 21', P31 milecastle; "
        f"wbsearchentities 'milefortlet'), and {WP}Milefortlet redirects to 'Milecastle' - the "
        "type link stays",
    ),
    _leave(
        "duplicate-candidate",
        "cf49332c-0a05-4ba7-bf4f-48a703ee7a1e",
        "Ciudad Romana de Cáparra",
        "Q2580972",
        "Cáparra",
        "the link is right: Q2580972 'Capera' - 'ancient city in Cáceres Province' (323 m) is the "
        f"Roman city; the curated row 'Cáparra' (577f2ec4, 343 m away) {_SAME} ({_LISTED}); the "
        "other items within 1 km named Cáparra are its parts (tetrapylon, amphitheatre, bridge)",
    ),
    _leave(
        "duplicate-candidate",
        "577f2ec4-3dc0-4d10-9425-39f1cb654009",
        "Cáparra",
        "Q2580972",
        "Cáparra",
        f"the link is right: {WP}Cáparra is this item's article, Q2580972 'Capera' 26 m; "
        f"the curated row 'Ciudad Romana de Cáparra' (cf49332c, 343 m away) {_SAME} ({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "dcda1568-0730-4cba-a9ce-c50c80ed941d",
        "Enkomi",
        "Q1343280",
        "Enkomi",
        "the curated row 'Engomi Ancient City Ruins' (0999c397, 2.06 km away) describes the same "
        "Late Bronze Age city, and both link Q1343280 'Egkomi Ammochostou', the village (P31 "
        "village, archaeological site; 818 m) - a duplicate candidate first",
        f"the site's own item {WD}Q22987223 'Enkomi' - 'archaeological site in Cyprus' (enwiki "
        "'Enkomi (archaeological site)') carries two P625 1.9 km apart: the one read (German "
        "Wikipedia) 2.07 km from this row and 93 m from 'Engomi Ancient City Ruins', the other "
        "286 m from this row - its place cannot pass the 1 km gate; which row and which point stay "
        "is the owner's question",
    ),
    _leave(
        "duplicate-candidate",
        "0999c397-1333-4ff3-aa26-fe854f46de9c",
        "Engomi Ancient City Ruins",
        "Q1343280",
        "Enkomi",
        "the curated row 'Enkomi' (dcda1568, 2.06 km away) describes the same city ('Enkomi (also "
        "known as Engomi)'); both link the village Q1343280 (1.24 km) - a duplicate candidate first",
        "no candidate came back for this row: Wikidata's geosearch places Q22987223 at its other "
        "point, 1.77 km away, though its first P625 is 93 m from this row; none of its names "
        "('Enkomi', 'Égkomi', 'Έγκωμη') is the stored name, so rule B could not take it anyway",
    ),
    _leave(
        "duplicate-candidate",
        "109fcdea-c114-4143-87ac-77c4c9c20f16",
        "Hattusas",
        "Q181007",
        "Hattusa",
        "the link is right: Q181007 'Hattusa' - 'capital of Hittite empire' (1.38 km; 'Hattusas' "
        f"is one of its names); the curated row 'Hattuşa Örenyeri' (7e33b1ac, 1.22 km away) {_SAME} "
        f"({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "318414bc-098b-4459-95c0-41e1ec49c8a8",
        "Templos de Tarxien",
        "Q1064331",
        "Tarxien Temples",
        "the link is right: Q1064331 'Tarxien Temples' (48 m); the curated row 'Tarxien Temples' "
        f"(4a5a324f, 38 m away) {_SAME} ({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "56f594fc-6819-4d51-98a4-1cf5b4a265a6",
        "Archaeological Site of Dodoni",
        "Q382317",
        "Dodona",
        "the link is right: Q382317 'Dodona' - 'ancient Greek sanctuary and oracle' (248 m); the "
        f"curated row 'Dodona' (5a04d6f3, 250 m away) {_SAME} ({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "ab077874-2a7f-4add-adec-8cb42e9e9561",
        "Madain Saleh",
        "Q27356",
        "Hegra",
        "the research's rule-B lead Q12239409 'Hejaz railway station, el-Ula' (890 m, P31 "
        "railway station, name 'Madaïn Saleh') is the station named after the site, not the "
        "site - refused",
        "the link is right: Q27356 'Hegra' (1.23 km; 'Madain Saleh' is one of its names); the "
        f'curated row "Hegra - Mada\'in Salih" (47eb07cd, 1.77 km away) {_SAME} - both describe the '
        f"Nabataean tombs of Hegra ({_UNLISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "93391ee6-8e80-42db-922c-11f64ea57db9",
        "Termantia",
        "Q2429023",
        "Termantia",
        f"the link is right: {WP}Termantia is this item's article, Q2429023 'Tiermes' 23 m; the "
        f"curated row 'Tiermes Archaeological Site' (84ef64f3, 163 m away) {_SAME} ({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "f6b6e039-36f1-4107-b730-dc2aa34b7a92",
        "Ballymacaldrack Court Tomb",
        "Q1242421",
        "Dooey's Cairn",
        "the link is right: Q1242421 \"Dooey's Cairn\" (12 m; 'Ballymacaldrack Court Tomb' is one "
        f'of its names); the curated row "Dooey\'s Cairn" (f5ca382a, 7 m away) {_SAME} '
        f"({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "24676ed3-9308-42d4-bf35-1c739f0652e2",
        "Archaeological Site, Heraion",
        "Q2070087",
        "Heraion of Perachora",
        "the link is right: Q2070087 'Heraion of Perachora' (136 m); the curated row 'Heraion of "
        f"Perachora' (9d9d94a0, 122 m away) {_SAME} ({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "f5df832e-ab5e-4e9c-b6c9-037441011945",
        "Twin Gates of Pula",
        "Q12630293",
        "Porta Gemina",
        "the link is right: Q12630293 'Porta Gemina' - '2nd-century Roman city gate in Pula' "
        "(38 m); the record reads 'The Dvojna vrata (Twin Gates), also called Porta Gemina'; the "
        f"curated row 'Porta Gemina' (d4714397, 30 m away) {_SAME} ({_UNLISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "891ad351-7985-4c16-b6a6-830c26bc268f",
        "Great Basilica, Plovdiv",
        "Q20500169",
        "Great Basilica, Plovdiv",
        f"the link is right: {WP}Great_Basilica,_Plovdiv is this item's article, Q20500169 11 m; "
        f'the curated row "Bishop\'s Basilica of Philippopolis" (b46b6969, 6 m away) {_SAME} '
        f"({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "58d2d752-30cc-4f22-b2d5-ff27a4b395d1",
        "Hipogeo de Biniai nou",
        "Q27987850",
        "Biniai Nou hypogea",
        "the link is right: Q27987850 'Hipogeos de Biniai Nou' (5 m); the curated row 'Biniai Nou "
        f"Hypogea' (13bdea38, 17 m away) {_SAME} ({_UNLISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "13bdea38-cb6c-4c6b-85cb-402a31427819",
        "Biniai Nou Hypogea",
        "Q27987850",
        "Biniai Nou hypogea",
        "the link is right: Q27987850 'Hipogeos de Biniai Nou' (21 m; enwiki 'Biniai Nou "
        f"hypogea'); the curated row 'Hipogeo de Biniai nou' (58d2d752, 17 m away) {_SAME} "
        f"({_UNLISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "69aaac26-9f4a-47da-beb4-d31ef8d4301f",
        "Killarumiyoq",
        "Q17074808",
        "Killarumiyuq",
        "the link is right: Q17074808 'Killarumiyuq' (77 m; the stored name is a spelling of it); "
        f"the curated row 'Killarumiyuq' (ddc0a0bf, 92 m away) {_SAME} ({_UNLISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "4a9b3802-1067-4f6b-a144-4c2ffe9619a4",
        "Qorikancha",
        "Q817594",
        "Coricancha",
        "the link is right: Q817594 'Coricancha' (114 m; 'Qorikancha' is one of its names); the "
        f"curated row 'Coricancha' (4e6247b0, 101 m away) {_SAME} ({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "ce7db300-8777-425d-917a-2f6d9f325b58",
        "Caesarea Philippi",
        "Q606295",
        "Banias",
        f"the research's rule-B lead {WD}Q2484244 'Caesarea Philippi' - 'ancient Roman city' "
        "(62 m; its sitelink redirects to 'Banias') is refused here: this row and 'Banias' "
        "(ae2ca7b1, 290 m away) are one site recorded twice - both names are names of Q606295 - "
        "and the pair is held for the owner because the rows stand on the two sides of the Golan "
        "line (DUPLICATES_HELD.jsonl, B10)",
        "relinking this row alone would split one site into two items and settle by link what the "
        "owner holds by country; Q2484244 stays a lead for the row the owner keeps",
    ),
    _leave(
        "duplicate-candidate",
        "37008e3f-056c-43dc-81c2-74904cacdb4e",
        "Obelisk of Ark",
        "Q2308606",
        "Obelisk of Axum",
        "the link is right: the record describes the Obelisk of Axum ('Ark' is a misspelling), "
        "Q2308606 (228 m); the curated row 'Obelisk of Axum' (a50cf939, 222 m away) "
        f"{_SAME} ({_UNLISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "07fb4e2f-26e5-4720-a949-9c28d4712e11",
        "Templo Romano Évora",
        "Q737441",
        "Roman Temple of Évora",
        "the link is right: Q737441 'Roman Temple of Évora' (28 m); the curated row 'Roman Temple "
        f"of Évora' (9152beea, 52 m away) {_SAME} ({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "485c3c0c-31f0-45a7-a06b-797c4c021466",
        "Dolmen de Menga",
        "Q1143218",
        "Dolmen of Menga",
        "the link is right: Q1143218 'Dolmen of Menga' (34 m); the curated row 'Dolmen of Menga' "
        f"(ab03fa75, 179 m away) {_SAME} ({_LISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "b9fdfd6f-b222-4c64-9953-b04fef1f55aa",
        "Birdoswald Roman Fort",
        "Q2061016",
        "Banna (Birdoswald)",
        "the link is right: Q2061016 'Banna' - 'Roman fort in Cumbria' (66 m; 'Birdoswald Roman "
        f"Fort' is one of its names); the curated row 'Banna, Birdoswald' (2048dfe4, 2 m away) "
        f"{_SAME} ({_UNLISTED})",
    ),
    _leave(
        "duplicate-candidate",
        "e19f7af0-539c-474c-9404-b11f22f48846",
        "Amyntas Rock Tombs",
        "Q7818606",
        "Tomb of Amyntas",
        "the link is right: the record describes the Tomb of Amyntas, Q7818606 (163 m); the "
        "curated row 'The Ancient Lycian Mezarı2' (4c5103a2, 1.12 km away) describes the same "
        "tomb under a garbled name (wave 2 left its reading to the owner) - a duplicate candidate, "
        "not a link repair",
    ),
    _leave(
        "link-right",
        "192467da-7219-4481-9b2d-34fc4cd5c6fd",
        "Themistoclean Wall",
        "Q12877842",
        "Themistoclean Wall",
        f"{WP}Themistoclean_Wall is this item's article (no redirect), and Q12877842 'walls of "
        "Themistocles' - '5th c. BCE city walls in Athens' (P31 archaeological site, city walls) "
        "is the wall itself; the Q1 test read its lower-case English label and missing P625 as a "
        "generic concept - it is one wall without a coordinate, and no other row links it",
    ),
    _leave(
        "link-right",
        "f0054526-9c55-402b-904f-9f4fa40ebd79",
        "Psychro Cave",
        "Q1643807",
        "Psychro Cave",
        f"{WP}Psychro_Cave is this item's article (no redirect), Q1643807 'Dikteon Andron' 28 m; "
        "the item was shared with 'Idaean Cave' (069e0320), whose link wave 2 replaced "
        "(Q1643807 -> Q935991, applied) - production holds it on this row alone (read 2026-09-23)",
    ),
    _leave(
        "link-right",
        "0cd58c95-e8da-453a-9ac4-ecaeeda843cc",
        "Locmariaquer Megaliths",
        "Q508651",
        "Locmariaquer megaliths",
        f"{WP}Locmariaquer_megaliths, the stored title and source_url, is the article of "
        "Q508651 'menhir d'Er Grah' (86 m); no other item of the complex within 1 km (the named "
        "ones are the commune and its settlement); the item was shared with 'Er-Grah Tumulus' "
        "(c2628a93), whose link wave 2 replaced (Q508651 -> Q1347902, applied) - production holds "
        "it on this row alone (read 2026-09-23)",
    ),
    _leave(
        "link-right",
        "d7a08c8b-4f1a-4067-a197-11922b0e34c6",
        "Pandavleni Caves",
        "Q7130537",
        "Nasik Caves",
        f"{WP}Pandavleni_Caves redirects to 'Nasik Caves', Q7130537 'ancient Buddhist cave complex "
        "in Nashik, India' (84 m), and the record is that complex; the item is shared with 'Cave "
        "20 - Pandavleni Caves' (917cd017), one cave of the complex on the complex's link (wave 2: "
        "no item of its own) - that row's question, not this link",
    ),
    _leave(
        "link-right",
        "e60fc487-9fb9-4e37-b590-4a035e591c7e",
        "The Temple of Artemis-Selçuk",
        "Q43018",
        "Temple of Artemis",
        "Q43018 'Temple of Ephesian Artemis' - 'temple in Ephesus, one of the Seven Wonders of the "
        "Ancient World' is 26 m from the stored point; the item is shared because 'The Temple of "
        "Artemis' (a939e800) describes the same temple on a point on Thasos, 388 km away - that "
        "record's contradiction (unresolved), not this link",
    ),
    _leave(
        "unresolved",
        "a939e800-06e4-4719-a000-165e7f5efe92",
        "The Temple of Artemis",
        "Q43018",
        "Temple of Artemis",
        "the record contradicts itself: its point (40.7802, 24.7156) and country are Limenas on "
        "Thasos, its description and link the Ephesus temple ('located in Ephesus (near modern "
        "Selçuk, Turkey)'; Q43018, 388 km), which the curated row 'The Temple of Artemis-Selçuk' "
        "(e60fc487) carries too",
        "no Thasos Artemis item passes rule B: none of the 15 items within 1 km names Artemis "
        "(the nearest are the Grave of Glaukos Q116213388, 129 m, and the ancient city of Thasos "
        "Q21083662, 189 m), and wbsearchentities finds no item for 'Artemision Thasos', "
        "'Sanctuary of Artemis Thasos', 'Temple of Artemis Thasos' or 'Artemision (Thasos)'",
        "which one the record is, is the owner's decision: Ephesus makes it a duplicate of "
        "e60fc487, Thasos leaves it with no item to link",
    ),
    _leave(
        "unresolved",
        "4c555421-7d9c-4921-b5c1-f5e386c6f6bd",
        "Asklepion, Kos",
        "Q731841",
        "Asclepieion",
        "Q731841 'Asclepeion' is the class ('healing sanctuary of ancient Greece'), also the link "
        "of 'Asklepieion - Pathos' (860e80c9, Cyprus, 520 km)",
        f"{WD}Q2655433 'Asclepeion of Kos' (258 m, P31 Asclepeion, archaeological site; article "
        "'Temple of Asclepius, Kos') is the sanctuary, but its names hold the stored name only as "
        "'Asklepion (Kos)', a descriptive match (N3) - rule B needs the name itself; left for "
        "the owner with that lead",
    ),
    _leave(
        "unresolved",
        "860e80c9-8b12-409d-867b-270c9acc17bb",
        "Asklepieion - Pathos",
        "Q731841",
        "Asclepieion",
        "Q731841 'Asclepeion' is the class, also the link of 'Asklepion, Kos' (4c555421, 520 km)",
        f"{WD}Q82073722 'Asclepieion in Paphos' (20 m, P31 ancient Greek temple) is the "
        "sanctuary, but 'Asklepieion - Pathos' (Paphos misspelt) is none of its names - rule B "
        "cannot take it; left for the owner with that lead",
    ),
    _leave(
        "unresolved",
        "fcd0a337-27f9-4223-82e9-d89a98795bd3",
        "Caunos Tombs of The Kings",
        "Q608095",
        "Kaunos",
        "the record is the rock-cut tombs of Kaunos; Q608095 is the whole city, the link of the "
        "curated row 'Kaunos' (b19343e4, 1.44 km away) - a part on its parent's link, not a "
        "duplicate",
        "the only tomb item within 1 km, Q134728223 ('mausoleum, rock-cut tomb in Köyceğiz "
        "District', 143 m), has no label to match; no item names the tombs",
    ),
    _leave(
        "unresolved",
        "3c466fde-b751-4065-8de2-bd5c9280afe5",
        "Bosnian Pyramid of the Sun",
        "Q746765",
        "Bosnian pyramid claims",
        "the record is Visočica hill ('The so-called Bosnian Pyramid of the Sun is Visocica "
        f"Hill'); {WD}Q797511 'Visočica' (185 m) is that hill, but none of its names is the "
        "stored name, and rule B takes no natural feature",
        "Q746765 'Bosnian pyramid claims' is the claims themselves, linked by all three hills' "
        "rows (the Moon 0fd636ac, Love 8df8659c) - left for the owner",
    ),
    _leave(
        "unresolved",
        "8df8659c-49be-4a66-b25a-ecbf96541515",
        "Bosnian Pyramid of Love",
        "Q746765",
        "Bosnian pyramid claims",
        "no item within 1 km names the hill (the nearest, Q21744278 'Cemorac', 97 m, is a "
        "mountain none of whose names is the stored name); Q746765 is the claims themselves, "
        "linked by all three hills' rows - left for the owner",
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
WAVE3 = Wave(
    3,
    WAVE3_SITES,
    "2026-09-23_external-id-repair-wave3",
    OUT / "wave3",
    "qid-repair research 2026-09-23 (wave 3)",
    GATE_M,
)
#: Wave 4 plans from its resolution record (`RESOLUTION.json` in its directory), not from sites.
WAVE4 = Wave(
    4,
    (),
    "2026-09-23_source-url-split-wave4",
    OUT / "wave4",
    "source-url split 2026-09-23 (wave 4)",
    None,
)
WAVES = {wave.number: wave for wave in (WAVE1, WAVE2, WAVE3, WAVE4)}

#: The table and column wave 4 writes beside `site_external_ids`.
SITES_TABLE = "unified_sites"
URL_COLUMN = "source_url"


@dataclass(frozen=True)
class Change:
    """One conditional change of one row, and what the journal records.

    A `site_external_ids` row (waves 1-4): `kind` is its kind, `old_value` None means the site has
    no row of the kind and the row is inserted (wave 4). A `unified_sites` row (waves 4 and L5):
    `kind` is the column, written through `apply_remediation_change()`. `new_value` None is a
    removal - of the row, or a cleared column - and only L5 plans one (`render_split(removals=True)`).
    """

    site_id: str
    name: str
    kind: str
    old_value: str | None
    new_value: str | None
    test_id: str
    confidence: str
    evidence: tuple[str, ...]
    change_key: str
    table: str = TABLE

    @property
    def column(self) -> str:
        """The journal's `column_name`: an external id's `value`, or the site column itself."""
        return "value" if self.table == TABLE else self.kind

    @property
    def row_pk(self) -> str:
        """The journal's `row_pk`: the site and the kind, which name the row across the change -
        or, for a site column, the site's id (what `apply_remediation_change` journals)."""
        return f"{self.site_id}/{self.kind}" if self.table == TABLE else self.site_id

    def to_json_line(self) -> str:
        record = asdict(self)
        if self.table == TABLE:
            # waves 1-3 wrote their site_external_ids rows without the key; their plans stay theirs
            del record["table"]
        return json.dumps(record, ensure_ascii=False, sort_keys=True)


def change_key(
    site_id: str, kind: str, old: str | None, new: str | None, test_id: str, *, table: str = TABLE
) -> str:
    parts = json.dumps([site_id, table, kind, old, new, test_id], ensure_ascii=False)
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
        if site.rule in UNCHANGED:
            if site.new_qid is not None or site.new_title is not None:
                raise SystemExit(
                    f"{site.name}: a site the plan leaves ({site.rule}) cannot carry a new value"
                )
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
    """Every SQL file the runbook runs, as `render` (wave 4: `render_split`) writes it."""
    make = render_split if wave.number == SPLIT_WAVE else render
    return {
        "APPLY.sql": make(rows, reversal=False, wave=wave),
        "REHEARSAL.sql": make(rows, reversal=False, rehearsal=True, wave=wave),
        "ROLLBACK.sql": make(rows, reversal=True, wave=wave),
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


#: Wave 3's outcomes in the order its plan lists them: the replacements, then why the others stay.
OUTCOMES = ("replace", *UNCHANGED)


def outcome(site: Site) -> str:
    """`replace` for a rule-A/B site, else the reason its rows stay (`UNCHANGED`)."""
    return "replace" if site.rule in ("A", "B") else site.rule


def outcome_counts(sites: tuple[Site, ...]) -> dict[str, int]:
    return {name: sum(1 for site in sites if outcome(site) == name) for name in OUTCOMES}


def wave3_markdown(rows: list[Change]) -> str:
    """Wave 3's decision record: every suspect link, replaced or not, with its outcome and evidence."""
    wave = WAVE3
    counts = outcome_counts(wave.sites)
    listed = sum(
        1
        for site in wave.sites
        if site.rule == "duplicate-candidate" and any(_LISTED in line for line in site.evidence)
    )
    lines = [
        "# External-id repair, wave 3 (2026-09-23) - planned, not applied",
        "",
        f"{len(rows)} row changes at {counts['replace']} sites (run stamp `{wave.run_stamp}`); the "
        f"other {len(wave.sites) - counts['replace']} sites keep their rows exactly as they are: "
        + ", ".join(f"{counts[name]} {name}" for name in UNCHANGED)
        + f". The {len(wave.sites)} sites are the B1 name findings whose name matched (group "
        "`keep`) while their link is a generic concept (Q1) or an item other curated rows share "
        "(Q2) - `link_suspect` in `output/remediation/bcases/names.jsonl`; a link only far away "
        "(Q4 alone) is not in this wave. The research record is "
        "`output/remediation/bcases/qid_research_suspects.jsonl`; the rules, the 1 km gate and "
        "what each outcome means are in the module docstring of "
        "`output/remediation/tools/qid_repair.py`.",
        "",
        "| site | outcome | wikidata_qid | enwiki_title | gate | evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for site in sorted(wave.sites, key=lambda s: (OUTCOMES.index(outcome(s)), s.name)):
        qid = f"`{site.old_qid}` -> `{site.new_qid}`" if site.new_qid else f"`{site.old_qid}`"
        title = (
            f"`{site.old_title}` -> `{site.new_title}`" if site.new_title else f"`{site.old_title}`"
        )
        label = f"replace ({site.rule})" if outcome(site) == "replace" else site.rule
        gate = "" if site.gate_m is None else f"{site.gate_m:.0f} m"
        lines.append(
            f"| {site.name} (`{site.site_id}`) | {label} | {qid} | {title} | {gate} | "
            + "<br>".join(site.evidence)
            + " |"
        )
    lines += [
        "",
        "## Left as they are, and why",
        "",
        "* A kept name mostly means a right link, so every row but the replacements keeps its "
        "link: a replacement the rules cannot prove is worse than a known-bad anchor (dedup trusts "
        f"item ids). **keep-type** ({counts['keep-type']}): the record is the type, as wave 2 kept "
        f"Giants' Graves. **duplicate-candidate** ({counts['duplicate-candidate']}): the item is "
        f"shared because another curated row is the same site - the owner's merge ({listed} of "
        "them are already in `output/remediation/bcases/DUPLICATES.jsonl`, Caesarea Philippi is "
        "the held Golan pair, the rest are named here). **link-right** "
        f"({counts['link-right']}): the suspicion does not hold. **unresolved** "
        f"({counts['unresolved']}): no rule proves a replacement; the leads are in the evidence.",
        "* Two research leads are refused by hand: Madain Saleh's (a railway station named after "
        "the site) and Caesarea Philippi's (it would split the held duplicate pair by link).",
        "* The same fixed point as waves 1 and 2: `unified_sites.source_url` of the two replaced "
        "sites still names the article the old id came from (`Megalopolis,_Greece`; `Siega_Verde`, "
        "a redirect to the joint Côa article), so `refresh_site_external_ids(only_missing=False)` "
        "would add the old id back beside the repaired one; the boot path "
        "(`only_missing=True`) does not.",
        "* `gap_plan.py` withholds the links of wave 1 only (`qid_repair.SITES`); wave 3's two "
        "replaced links are named here for the gap lane's next re-plan.",
        "",
        "## How to run it (the orchestrator's job, in this order)",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        "$PY output/remediation/tools/qid_repair.py render --wave 3   # REHEARSAL.sql is not versioned",
        "$PY output/remediation/tools/qid_repair.py check --wave 3    # read-only",
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave3/REHEARSAL.sql',
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave3/APPLY.sql',
        "$PY output/remediation/tools/qid_repair.py verify --wave 3   # read-only",
        "```",
        "",
    ]
    return "\n".join(lines)


# ── wave 4: the curated source_url values that hold two URLs ──────────────────────────────────
SPLIT_WAVE = WAVE4.number
RESOLUTION = "RESOLUTION.json"
CURATED = "ancient_nerds"
ENWIKI = "https://en.wikipedia.org/wiki/"
#: The one separator the values carry (measured 2026-09-23: 20 rows, each exactly one '\n', no '\r').
SEPARATOR = "\n"
#: One URL: a scheme and no whitespace or control character.
URL_RE = re.compile(r"https?://[^\s\x00-\x1f\x7f]+")

#: Every row whose source_url carries a control character, whatever its source: the plan refuses a
#: row that is not curated, and migration 0023 needs every one of them fixed.
SCOPE_SQL = (
    "SELECT to_jsonb(t)::text FROM (SELECT id::text AS site_id, name, source_id, source_url, "
    "created_at::date::text AS created FROM unified_sites "
    r"WHERE source_url ~ '[\x00-\x1f\x7f]' ORDER BY id) t;"
)
EXTERNAL_SQL = (
    "SELECT to_jsonb(t)::text FROM (SELECT site_id::text AS site_id, kind, value "
    f"FROM {TABLE} WHERE site_id::text IN ({{ids}}) ORDER BY site_id, kind, value) t;"
)
HOLDERS_SQL = (
    "SELECT to_jsonb(t)::text FROM (SELECT e.value AS qid, e.site_id::text AS site_id, u.name, "
    "u.source_url "
    f"FROM {TABLE} e JOIN unified_sites u ON u.id = e.site_id WHERE e.kind = 'wikidata_qid' "
    f"AND u.source_id = '{CURATED}' AND e.value IN ({{qids}}) ORDER BY e.value, e.site_id) t;"
)


#: The resolution of a URL that names no title.
NO_PAGE = {"canonical_title": None, "qid": None, "disambiguation": False, "redirected": False}


@dataclass(frozen=True)
class HandRead:
    """A wave-4 resolution read by hand: the rule refused it, and the quoted evidence overrides
    exactly that refusal - `overrides` is the rule's reason, verbatim. Any other refusal of the site
    (an item another curated site carries) still stands."""

    site_id: str
    name: str
    overrides: str
    evidence: tuple[str, ...]


#: The hand-read entries of wave 4 (orchestrator decision 2026-09-23), read like wave 2's hand
#: entries: every fact quoted from what Wikidata and Wikipedia answered that day (read-only:
#: `wbgetentities` Q5788 with its class labels, `resolve_titles(['Petra'])`).
WAVE4_HAND_READ: tuple[HandRead, ...] = (
    HandRead(
        "a06a95d0-35b4-44bb-a0c1-716cbf972b19",
        "Petra",
        "Q5788 is a place, not the site (P31: ancient city, city, archaeological site)",
        (
            f"{WD}Q5788 'Petra' - 'ancient rock-cut historical city in Jordan': P31 archaeological "
            "site (Q839954), ancient city (Q15661340) and city (Q515), all normal rank - the city "
            "is the historical city that is the site, not a settlement that contains it",
            f"{WD}Q5788: P1435 heritage designation World Heritage Site (Q9259), P757 World "
            "Heritage Site ID 326 - the item of the UNESCO World Heritage Site Petra",
            f"{WP}Petra: the stored name 'Petra' is this article's exact title (no redirect, not "
            "a disambiguation page), and the article's item is Q5788 (Q5788's enwiki sitelink is "
            "'Petra')",
        ),
    ),
)


@dataclass(frozen=True)
class Left:
    """A wave-4 value the rules do not write, and why."""

    site_id: str
    name: str
    what: str
    reason: str


@dataclass(frozen=True)
class SplitPlan:
    rows: list[Change]
    left: list[Left]
    record: Mapping[str, Any]
    #: Sites whose article's item another curated site carries: the owner's merge, not a link.
    duplicates: list[dict[str, Any]]
    #: The hand-read entries the plan applied.
    hand_read: tuple[HandRead, ...]


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def item_classes(qids: list[str]) -> dict[str, list[str]]:
    """The English labels of each item's P31 classes, read the way the bcases research reads them
    (`bcases.collect.fetch_claims` + `fetch_labels`, the census Fetcher and the bcases cache). A
    class without an English label stops the read: the place-level test could not judge it."""
    with Fetcher(root=bcases_inputs.CACHE / "http", workers=1) as net:
        claims = bcases_collect.fetch_claims(net, qids)
        classes = sorted({c for qid in qids for c in claims[qid]["p31"]})
        labels = bcases_collect.fetch_labels(net, classes) if classes else {}
    unlabelled = [c for c in classes if not labels.get(c)]
    if unlabelled:
        raise SystemExit(f"no English label for the P31 class(es) {unlabelled}")
    return {qid: [str(labels[c]) for c in claims[qid]["p31"]] for qid in qids}


def resolve_split(
    run: Callable[[str], str],
    *,
    resolve: Callable[[list[str]], dict[str, TitleResolution]] = resolve_titles,
    classes: Callable[[list[str]], dict[str, list[str]]] = item_classes,
    now: Callable[[], str] = _utc_now,
) -> dict[str, Any]:
    """Wave 4's input: production (read-only) and the boot refresh's own Wikipedia resolution."""
    read_at = now()
    sites = lanes.json_rows(run(SCOPE_SQL))
    if not sites:
        raise SystemExit("no source_url carries a control character - there is nothing to plan")
    ids = [str(site["site_id"]) for site in sites]
    held: dict[str, dict[str, list[str]]] = {sid: {} for sid in ids}
    for row in lanes.json_rows(run(EXTERNAL_SQL.format(ids=lanes.sql_literals(ids)))):
        held[row["site_id"]].setdefault(row["kind"], []).append(row["value"])
    titles = sorted(
        {
            title
            for site in sites
            for part in str(site["source_url"]).split(SEPARATOR)
            if URL_RE.fullmatch(part) and part.startswith(ENWIKI)
            for title in (enwiki_title_from_url(part),)
            if title
        }
    )
    resolved_at = now()
    resolutions = resolve(titles)
    qids = sorted({r.qid for r in resolutions.values() if r.qid})
    holders: dict[str, list[dict[str, str]]] = {qid: [] for qid in qids}
    if qids:
        for row in lanes.json_rows(run(HOLDERS_SQL.format(qids=lanes.sql_literals(qids)))):
            holders[row["qid"]].append(
                {"site_id": row["site_id"], "name": row["name"], "source_url": row["source_url"]}
            )
    p31 = classes(qids) if qids else {}
    return {
        "read_at": read_at,
        "resolved_at": resolved_at,
        "scope": SCOPE_SQL,
        "sites": [{**site, "external_ids": held[str(site["site_id"])]} for site in sites],
        "resolutions": {
            title: {
                "canonical_title": r.canonical_title,
                "qid": r.qid,
                "disambiguation": r.disambiguation,
                "redirected": r.redirected,
            }
            for title, r in sorted(resolutions.items())
        },
        "qid_holders": holders,
        "p31": p31,
    }


def write_resolution(out: pathlib.Path, record: Mapping[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / RESOLUTION).write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_resolution(out: pathlib.Path) -> dict[str, Any]:
    path = out / RESOLUTION
    if not path.exists():
        raise SystemExit(f"{path} does not exist; run `resolve --wave {SPLIT_WAVE}` first")
    record = json.loads(path.read_text(encoding="utf-8"))
    missing = {"read_at", "resolved_at", "sites", "resolutions", "qid_holders", "p31"} - set(record)
    if missing:
        raise SystemExit(f"{path} is not a wave-4 resolution record (missing {sorted(missing)})")
    return record


def _split_change(
    site: Mapping[str, Any],
    kind: str,
    old: str | None,
    new: str,
    confidence: str,
    evidence: tuple[str, ...],
    *,
    table: str = TABLE,
) -> Change:
    sid, test_id = str(site["site_id"]), f"EXT/{kind}"
    return Change(
        site_id=sid,
        name=str(site["name"]),
        kind=kind,
        old_value=old,
        new_value=new,
        test_id=test_id,
        confidence=confidence,
        evidence=evidence,
        change_key=change_key(sid, kind, old, new, test_id, table=table),
        table=table,
    )


def _not_the_site(res: Mapping[str, Any], p31: Mapping[str, list[str]]) -> str | None:
    """Why the article's resolution names no page of the site: no page, a disambiguation page, or
    an item that is a place - a settlement, an administrative unit or a natural feature that
    contains a site (`bcases.qid_research.is_site_kind`, the gate of waves 2 and 3). Or None."""
    if not res["canonical_title"]:
        return "no English Wikipedia page by that title"
    if res["disambiguation"]:
        return f"{res['canonical_title']!r} is a disambiguation page"
    qid = res["qid"]
    if qid is None:
        return None
    if qid not in p31:
        raise SystemExit(f"the record holds no P31 of {qid}; run `resolve` again")
    if not is_site_kind({"p31": p31[qid]}):
        return f"{qid} is a place, not the site (P31: {', '.join(p31[qid])})"
    return None


def _sharers(
    sid: str,
    qid: str,
    by_qid: Mapping[str, list[str]],
    holders: Mapping[str, list[Mapping[str, str]]],
    sites: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[dict[str, str]]] | None:
    """The other curated sites on this item - production's holders first, then this wave's own
    sites that resolve to it - with the reason the ids are not written, or None."""
    others = [dict(h) for h in holders.get(qid, []) if h["site_id"] != sid]
    if others:
        carried = ", ".join(f"{h['name']} ({h['site_id']})" for h in others)
        return f"{qid} is already carried by the curated site {carried}", others
    twins = [
        {"site_id": t, "name": str(sites[t]["name"]), "source_url": str(sites[t]["source_url"])}
        for t in by_qid[qid]
        if t != sid
    ]
    if twins:
        named = ", ".join(f"{t['name']} ({t['site_id']})" for t in twins)
        return f"{qid} is the item of {named} too", twins
    return None


def _shape_problem(site: Mapping[str, Any]) -> str | None:
    """Why this wave does not split a row's source_url, or None: a curated row, two URLs."""
    if site["source_id"] != CURATED:
        return f"a {site['source_id']} row, not curated"
    parts = str(site["source_url"]).split(SEPARATOR)
    if len(parts) != 2 or not all(URL_RE.fullmatch(part) for part in parts):
        return "not two URLs joined by one newline"
    return None


def split_plan(record: Mapping[str, Any], *, hand_read: tuple[HandRead, ...]) -> SplitPlan:
    """Wave 4's rows from its resolution record. Pure: the record is the only input.

    Per site, in name order: `source_url` keeps its first URL; the one English Wikipedia URL among
    the two becomes `enwiki_title` + `wikidata_qid` as the boot refresh would store them - a new row
    where the site has none of the kind, a correction only of a value that carries a control
    character. Anything else is left, with its reason - unless a hand-read entry names that very
    refusal and quotes the evidence that overrides it.
    """
    hands = {entry.site_id: entry for entry in hand_read}
    if len(hands) != len(hand_read) or not all(entry.evidence for entry in hand_read):
        raise SystemExit("a hand-read entry names its site twice or quotes no evidence")
    sites = sorted(record["sites"], key=lambda s: (str(s["name"]).casefold(), str(s["site_id"])))
    if len({s["site_id"] for s in sites}) != len(sites):
        raise SystemExit("the resolution record names a site twice")
    by_id = {str(s["site_id"]): s for s in sites}
    # the article of every site whose source_url this wave splits (one English Wikipedia URL)
    articles: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for site in sites:
        if _shape_problem(site) is not None:
            continue
        wiki = [p for p in str(site["source_url"]).split(SEPARATOR) if p.startswith(ENWIKI)]
        if len(wiki) == 1:
            title = enwiki_title_from_url(wiki[0])
            if title is None:  # the URL ends at /wiki/: it names no page
                articles[str(site["site_id"])] = (wiki[0], NO_PAGE)
                continue
            if title not in record["resolutions"]:
                raise SystemExit(f"{site['name']}: no resolution of {title!r}; run `resolve` again")
            articles[str(site["site_id"])] = (wiki[0], record["resolutions"][title])
    by_qid: dict[str, list[str]] = {}
    for sid, (_, res) in articles.items():
        if res["qid"]:
            by_qid.setdefault(res["qid"], []).append(sid)

    rows: list[Change] = []
    left: list[Left] = []
    duplicates: list[dict[str, Any]] = []
    for site in sites:
        sid, name, value = str(site["site_id"]), str(site["name"]), str(site["source_url"])
        problem = _shape_problem(site)
        if problem is not None:
            left.append(Left(sid, name, URL_COLUMN, problem))
            continue
        first, second = value.split(SEPARATOR)
        parts = [first, second]
        rows.append(
            _split_change(
                site,
                URL_COLUMN,
                value,
                first,
                "authoritative",
                (
                    f"source_url holds two URLs joined by a newline (row created {site['created']}): "
                    f"{first} and {second}",
                    "the curator's first URL is kept (orchestrator decision 2026-09-23); the whole "
                    "old value stays in this journal row",
                ),
                table=SITES_TABLE,
            )
        )
        wiki = [part for part in parts if part.startswith(ENWIKI)]
        if len(wiki) != 1:
            left.append(
                Left(
                    sid,
                    name,
                    "external ids",
                    "neither URL is an English Wikipedia article"
                    if not wiki
                    else "both URLs are English Wikipedia articles",
                )
            )
            continue
        url, res = articles[sid]
        why = _not_the_site(res, record["p31"])
        hand = hands.pop(sid, None)
        if hand is not None:
            if why != hand.overrides:
                raise SystemExit(
                    f"{name}: the hand-read entry overrides {hand.overrides!r}, but the rule's "
                    f"refusal is {why!r} - a hand entry names the refusal it overrides"
                )
            why = None
        if why is None and res["qid"] is not None:
            shared = _sharers(sid, res["qid"], by_qid, record["qid_holders"], by_id)
            if shared is not None:
                why, others = shared
                duplicates.append(
                    {
                        "site_id": sid,
                        "name": name,
                        "qid": res["qid"],
                        "article": url,
                        "others": others,
                    }
                )
        if why is not None:
            left.append(Left(sid, name, "external ids", f"{url}: {why}"))
            continue
        resolved = (
            f"{url}: resolve_titles, the path of refresh_site_external_ids "
            f"({record['resolved_at']}): page {res['canonical_title']!r}"
            + (" (after a redirect)" if res["redirected"] else "")
            + (f", item {res['qid']}" if res["qid"] else ", no Wikidata item")
        )
        for kind, new in (("enwiki_title", res["canonical_title"]), ("wikidata_qid", res["qid"])):
            if new is None:
                continue
            have = list(site["external_ids"].get(kind, []))
            if have == [new]:
                continue
            evidence = [resolved]
            if hand is not None:
                evidence += [f"hand-read, overriding: {hand.overrides}", *hand.evidence]
            old: str | None = None
            if len(have) == 1 and CONTROL_RE.search(have[0]):
                old = have[0]
                evidence.append(
                    f"the stored {kind} is the whole two-URL source_url taken for a title; the "
                    "API answers it as invalid"
                )
            elif have:
                left.append(Left(sid, name, kind, f"the site already carries {have!r}"))
                continue
            if kind == "wikidata_qid":
                evidence.append(
                    f"no other curated site carries {new} (production, {record['read_at']})"
                )
            rows.append(_split_change(site, kind, old, new, "two_source", tuple(evidence)))
    if hands:
        raise SystemExit(
            f"hand-read entries for {sorted(hands)}: the wave resolves no article of those sites"
        )
    return SplitPlan(rows, left, record, duplicates, tuple(hand_read))


def sql_value(value: str | None) -> str:
    """`lanes.sql_text`, with each control character spelled `chr(n)` outside the quotes.

    A raw newline inside a literal would put the value's line break into the statement file, where
    a CRLF working copy turns it into CR LF and the guard then compares another value. A value
    without a control character is spelled exactly as `lanes.sql_text` spells it.
    """
    if value is None or not CONTROL_RE.search(value):
        return lanes.sql_text(value)
    pieces = []
    for piece in re.split(f"({CONTROL_RE.pattern})", value):
        if CONTROL_RE.fullmatch(piece):
            pieces.append(f"chr({ord(piece)})")
        elif piece:
            pieces.append(lanes.sql_text(piece))
    return "(" + " || ".join(pieces) + ")"


def render_split(
    rows: list[Change],
    *,
    reversal: bool,
    rehearsal: bool = False,
    wave: Wave = WAVE4,
    removals: bool = False,
) -> str:
    """Wave 4's transaction: the source_url rows through `apply_remediation_change()`, the
    external-id rows by their full key (a new row inserted where the site holds none of its kind;
    the reversal deletes exactly that row), each journalled, then guards and invariants.

    `removals` is L5's form of the same transaction (HUMAN_ONLY B1-L, 2026-09-26: "sonst wird der
    falsche Link entfernt"): a planned new value may be None - the write deletes exactly that
    external-id row, or clears `source_url` - and its reversal restores it. Four things change
    with it, and nothing else: the plan tables take NULL on both sides; guard 5 (no other curated
    site carries a planned item) reads the write only, because a reversal restores the state the
    write found, an item two rows shared included; the write alone also refuses one new item
    planned for two sites (guard 6 - guard 5 reads the state before the write, so both would pass
    it) and checks after its writes that every item it wrote is carried by exactly one curated site
    (invariant 5); and invariant 4 (the fixed point) refuses a planned site left without any
    external-id row while its `source_url` is still an English Wikipedia article -
    `refresh_site_external_ids`, run daily by the prospector, would resolve that URL and write the
    removed link back. Without `removals` the statement is wave 4's, byte for byte (its delivered
    files are pinned).
    """
    if not rows:
        raise SystemExit("refusing to render a statement with no rows")
    urls = [row for row in rows if row.table == SITES_TABLE]
    ext = [row for row in rows if row.table == TABLE]
    if len(urls) + len(ext) != len(rows) or any(row.kind != URL_COLUMN for row in urls):
        raise SystemExit("wave 4 writes unified_sites.source_url and site_external_ids only")
    if any(
        (row.new_value is None and not removals)
        or (row.new_value is not None and CONTROL_RE.search(row.new_value))
        for row in rows
    ):
        raise SystemExit("a planned new value carries a control character or is missing")
    stamp = wave.rollback_stamp if reversal else wave.run_stamp
    s = lanes.sql_text(stamp)

    def values(group: list[Change], *, with_kind: bool) -> str:
        out = []
        for row in group:
            old, new = (
                (row.new_value, row.old_value) if reversal else (row.old_value, row.new_value)
            )
            key = row.change_key + ("-rollback" if reversal else "")
            kind = f"{lanes.sql_text(row.kind)}, " if with_kind else ""
            out.append(
                f"    ({lanes.sql_text(row.site_id)}::uuid, {kind}{sql_value(old)}, "
                f"{sql_value(new)}, {lanes.sql_text(key)}, {lanes.sql_text(row.test_id)}, "
                f"{lanes.sql_text(row.confidence)}, {_evidence_json(row, wave.research)})"
            )
        return ",\n".join(out) + ";"

    lines = [
        "-- Generated by output/remediation/tools/qid_repair.py - do not edit by hand.",
        f"{DIGEST_HEADER}{plan_digest(rows)}",
        f"-- the {'reversal' if reversal else 'repair'} of {len(rows)} row(s): {len(urls)} "
        f"unified_sites.source_url and {len(ext)} site_external_ids; run stamp '{stamp}'.",
        "-- source_url goes through apply_remediation_change() (migrations 0017/0018/0022). An",
        "-- external-id row is addressed by its full key (site_id, kind, value = the old value) and",
        "-- must match exactly one row; an old value NULL means the site holds no row of the kind and",
        "-- the row is inserted. Every row is journalled in the same transaction.",
    ]
    if removals:
        lines += [
            "-- L5 (HUMAN_ONLY B1-L): a new value NULL removes exactly that external-id row, or clears",
            "-- source_url; the reversal restores it. Invariant 4 keeps the fixed point of the daily",
            "-- external-id refresh: no planned site is left without an external-id row while its",
            "-- source_url is an English Wikipedia article.",
        ]
    elif reversal:
        lines += [
            "-- The reversal deletes exactly the rows the repair inserted, by their value. Once",
            "-- migration 0023 is applied, its CHECK refuses the two-URL source_url restored here.",
        ]
    url_table = [
        "CREATE TEMP TABLE _url_plan (",
        "    site_id    UUID PRIMARY KEY,",
        "    old_value  TEXT NOT NULL,",
        "    new_value  TEXT NOT NULL,",
        "    change_key TEXT NOT NULL,",
        "    test_id    TEXT NOT NULL,",
        "    confidence TEXT NOT NULL,",
        "    evidence   JSONB NOT NULL",
        ") ON COMMIT DROP;",
    ]
    if removals:
        url_table[2:4] = ["    old_value  TEXT,", "    new_value  TEXT,"]
        url_table[7:8] = [
            "    evidence   JSONB NOT NULL,",
            "    CHECK (old_value IS NOT NULL OR new_value IS NOT NULL)",
        ]
    guard5 = [
        "    SELECT count(*) INTO bad FROM _ext_plan p",
        f"      JOIN {TABLE} e ON e.kind = p.kind AND e.value = p.new_value AND e.site_id <> p.site_id",
        f"      JOIN unified_sites u ON u.id = e.site_id AND u.source_id = '{CURATED}'",
        "     WHERE p.kind = 'wikidata_qid';",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'source-url split: % planned item(s) are carried by another curated site', bad;",
        "    END IF;",
    ]
    if removals and reversal:
        guard5 = [
            "    -- (the write's only: a reversal restores the items the write found, shared or not)"
        ]
    one_site: list[str] = []
    one_site_after: list[str] = []
    if removals and not reversal:
        one_site = [
            "    -- guard 6: no item is planned for two sites (guard 5 reads the state before the",
            "    -- write, so two planned sites given one new item would both pass it)",
            "    SELECT count(*) INTO bad FROM (SELECT new_value FROM _ext_plan",
            "     WHERE kind = 'wikidata_qid' AND new_value IS NOT NULL",
            "     GROUP BY new_value HAVING count(*) > 1) d;",
            "    IF bad > 0 THEN",
            "        RAISE EXCEPTION 'source-url split: % item(s) are planned for more than one site', bad;",
            "    END IF;",
        ]
        one_site_after = [
            "    -- invariant 5: every item written is carried by exactly one curated site",
            "    SELECT count(*) INTO bad FROM _ext_plan p",
            "     WHERE p.kind = 'wikidata_qid' AND p.new_value IS NOT NULL",
            f"       AND (SELECT count(*) FROM {TABLE} e",
            f"              JOIN unified_sites u ON u.id = e.site_id AND u.source_id = '{CURATED}'",
            "             WHERE e.kind = 'wikidata_qid' AND e.value = p.new_value) <> 1;",
            "    IF bad > 0 THEN",
            "        RAISE EXCEPTION 'source-url split: % written item(s) are not carried by exactly one curated site', bad;",
            "    END IF;",
        ]
    fixed_point: list[str] = []
    if removals:
        fixed_point = [
            "    -- invariant 4: the fixed point - no planned site is left without an external-id row",
            "    -- while its source_url is an English Wikipedia article (the daily refresh would",
            "    -- resolve it and write the removed link back)",
            "    SELECT count(*) INTO bad",
            "      FROM (SELECT site_id FROM _url_plan UNION SELECT site_id FROM _ext_plan) p",
            "      JOIN unified_sites u ON u.id = p.site_id",
            f"     WHERE u.source_url LIKE {lanes.sql_text(ENWIKI + '%')}",
            f"       AND NOT EXISTS (SELECT 1 FROM {TABLE} e WHERE e.site_id = p.site_id);",
            "    IF bad > 0 THEN",
            "        RAISE EXCEPTION 'source-url split: % site(s) left without a link on an English Wikipedia source_url', bad;",
            "    END IF;",
        ]
    lines += [
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        "",
        *url_table,
        "",
        "CREATE TEMP TABLE _ext_plan (",
        "    site_id    UUID NOT NULL,",
        "    kind       TEXT NOT NULL,",
        "    old_value  TEXT,",
        "    new_value  TEXT,",
        "    change_key TEXT NOT NULL,",
        "    test_id    TEXT NOT NULL,",
        "    confidence TEXT NOT NULL,",
        "    evidence   JSONB NOT NULL,",
        "    PRIMARY KEY (site_id, kind),",
        "    CHECK (old_value IS NOT NULL OR new_value IS NOT NULL)",
        ") ON COMMIT DROP;",
        "",
    ]
    if urls:
        lines += [
            "INSERT INTO _url_plan (site_id, old_value, new_value, change_key, test_id,",
            "                       confidence, evidence) VALUES",
            values(urls, with_kind=False),
            "",
        ]
    if ext:
        lines += [
            "INSERT INTO _ext_plan (site_id, kind, old_value, new_value, change_key, test_id,",
            "                       confidence, evidence) VALUES",
            values(ext, with_kind=True),
            "",
        ]
    write_ext = [
        "        IF r.old_value IS NULL THEN",
        f"            INSERT INTO {TABLE} (site_id, kind, value) VALUES (r.site_id, r.kind, r.new_value);",
    ]
    if reversal or removals:
        write_ext += [
            "        ELSIF r.new_value IS NULL THEN",
            f"            DELETE FROM {TABLE}",
            "             WHERE site_id = r.site_id AND kind = r.kind AND value = r.old_value;",
        ]
    write_ext += [
        "        ELSE",
        f"            UPDATE {TABLE} SET value = r.new_value",
        "             WHERE site_id = r.site_id AND kind = r.kind AND value = r.old_value;",
        "        END IF;",
    ]
    lines += [
        "DO $$",
        "DECLARE",
        "    bad      INTEGER;",
        "    n        INTEGER;",
        "    moved    INTEGER := 0;",
        f"    expected INTEGER := {len(rows)};",
        "    r        RECORD;",
        "BEGIN",
        "    -- guard 1: every site is a curated site that still exists",
        "    SELECT count(*) INTO bad",
        "      FROM (SELECT site_id FROM _url_plan UNION SELECT site_id FROM _ext_plan) p",
        "      LEFT JOIN unified_sites u ON u.id = p.site_id",
        f"     WHERE u.id IS NULL OR u.source_id <> '{CURATED}';",
        "    IF bad > 0 THEN RAISE EXCEPTION 'source-url split: % site(s) are not curated sites', bad;",
        "    END IF;",
        "    -- guard 2: every source_url still holds the planned old value",
        "    SELECT count(*) INTO bad FROM _url_plan p JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE u.source_url IS DISTINCT FROM p.old_value;",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'source-url split: % source_url value(s) no longer hold the planned old value', bad;",
        "    END IF;",
        "    -- guard 3: an external-id row with an old value is the one row of its kind and holds it",
        "    SELECT count(*) INTO bad FROM _ext_plan p",
        "     WHERE p.old_value IS NOT NULL",
        f"       AND ((SELECT count(*) FROM {TABLE} e",
        "              WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1",
        f"         OR NOT EXISTS (SELECT 1 FROM {TABLE} e WHERE e.site_id = p.site_id",
        "                           AND e.kind = p.kind AND e.value = p.old_value));",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'source-url split: % external-id row(s) no longer hold the planned old value', bad;",
        "    END IF;",
        "    -- guard 4: a row planned as new is new - the site holds no row of its kind",
        "    SELECT count(*) INTO bad FROM _ext_plan p",
        "     WHERE p.old_value IS NULL",
        f"       AND EXISTS (SELECT 1 FROM {TABLE} e WHERE e.site_id = p.site_id AND e.kind = p.kind);",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'source-url split: % site(s) already hold a row of a kind planned as new', bad;",
        "    END IF;",
        "    -- guard 5: no other curated site carries a planned item",
        *guard5,
        *one_site,
        "    -- the source_url writes: the journal primitive, one call and one journal row each",
        "    FOR r IN SELECT * FROM _url_plan ORDER BY site_id LOOP",
        "        moved := moved + apply_remediation_change(",
        f"            '{SITES_TABLE}', '{URL_COLUMN}', 'id', r.site_id::text, r.old_value, r.new_value,",
        f"            r.test_id, {s}, r.change_key, r.confidence, r.evidence, r.site_id);",
        "    END LOOP;",
        "    -- the external-id writes: exactly one row each, and its journal row",
        "    FOR r IN SELECT * FROM _ext_plan ORDER BY site_id, kind LOOP",
        *write_ext,
        "        GET DIAGNOSTICS n = ROW_COUNT;",
        "        IF n <> 1 THEN",
        "            RAISE EXCEPTION 'source-url split: %/% matched % row(s), not 1',",
        "                r.site_id, r.kind, n;",
        "        END IF;",
        "        INSERT INTO remediation_change_log (run_stamp, test_id, table_name, column_name,",
        "            row_pk, old_value, new_value, change_key, confidence, evidence, site_id_ref)",
        f"        VALUES ({s}, r.test_id, {lanes.sql_text(TABLE)}, 'value',",
        "            r.site_id::text || '/' || r.kind, r.old_value, r.new_value, r.change_key,",
        "            r.confidence, r.evidence, r.site_id);",
        "        moved := moved + n;",
        "    END LOOP;",
        "    IF moved <> expected THEN",
        "        RAISE EXCEPTION 'source-url split: % row(s) changed, % planned', moved, expected;",
        "    END IF;",
        "    -- invariant 1: every source_url holds its new value",
        "    SELECT count(*) INTO bad FROM _url_plan p JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE u.source_url IS DISTINCT FROM p.new_value;",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'source-url split: % source_url value(s) do not hold the new value', bad;",
        "    END IF;",
        "    -- invariant 2: an external-id row holds its new value and is the one row of its kind;",
        "    -- a row the plan removes is gone",
        "    SELECT count(*) INTO bad FROM _ext_plan p",
        "     WHERE (p.new_value IS NOT NULL",
        f"            AND ((SELECT count(*) FROM {TABLE} e WHERE e.site_id = p.site_id",
        "                   AND e.kind = p.kind AND e.value = p.new_value) <> 1",
        f"              OR (SELECT count(*) FROM {TABLE} e",
        "                   WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1))",
        "        OR (p.new_value IS NULL",
        f"            AND EXISTS (SELECT 1 FROM {TABLE} e WHERE e.site_id = p.site_id AND e.kind = p.kind));",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'source-url split: % external-id row(s) do not hold the new value', bad;",
        "    END IF;",
        "    -- invariant 3: the journal and the plan agree in both directions",
        "    SELECT count(*) INTO bad FROM (",
        f"        SELECT change_key, '{SITES_TABLE}' AS table_name, '{URL_COLUMN}' AS column_name,",
        "               site_id::text AS row_pk, old_value, new_value FROM _url_plan",
        "        UNION ALL",
        f"        SELECT change_key, {lanes.sql_text(TABLE)}, 'value', site_id::text || '/' || kind,",
        "               old_value, new_value FROM _ext_plan",
        "    ) p LEFT JOIN remediation_change_log l",
        f"        ON l.run_stamp = {s} AND l.change_key = p.change_key",
        "       AND l.table_name = p.table_name AND l.column_name = p.column_name",
        "       AND l.row_pk = p.row_pk AND l.old_value IS NOT DISTINCT FROM p.old_value",
        "       AND l.new_value IS NOT DISTINCT FROM p.new_value",
        "     WHERE l.id IS NULL;",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'source-url split: % row(s) have no matching journal row', bad;",
        "    END IF;",
        "    SELECT count(*) INTO bad FROM remediation_change_log l",
        f"     WHERE l.run_stamp = {s}",
        "       AND NOT EXISTS (SELECT 1 FROM _url_plan p WHERE p.change_key = l.change_key)",
        "       AND NOT EXISTS (SELECT 1 FROM _ext_plan p WHERE p.change_key = l.change_key);",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'source-url split: this stamp journalled % row(s) outside the plan',",
        "            bad;",
        "    END IF;",
        *fixed_point,
        *one_site_after,
        "    RAISE NOTICE 'source-url split: % row(s) changed and journalled', moved;",
        "END $$;",
        "",
        "ROLLBACK;" if rehearsal else "COMMIT;",
        "",
        "SELECT 'journal rows for this stamp' AS metric, count(*)::text AS value",
        f"  FROM remediation_change_log WHERE run_stamp = {s};",
        "",
    ]
    return "\n".join(lines)


def _cell(value: str | None) -> str:
    if value is None:
        return "(no row)"
    return "<br>".join(f"`{part}`" for part in value.split(SEPARATOR))


def _duplicate_evidence(dup: Mapping[str, Any], other: Mapping[str, str]) -> str:
    same = " - the same article" if other["source_url"] == dup["article"] else ""
    return (
        f"this site's article {dup['article']} resolves to `{dup['qid']}`, the item the other "
        f"row carries; the other row's source_url is {_cell(other['source_url'])}{same}"
    )


def wave4_markdown(plan: SplitPlan) -> str:
    """Wave 4's decision record: every row, every value left and why, and how to run it."""
    wave, record, rows = WAVE4, plan.record, plan.rows
    urls = [row for row in rows if row.table == SITES_TABLE]
    new = [row for row in rows if row.table == TABLE and row.old_value is None]
    corrected = [row for row in rows if row.table == TABLE and row.old_value is not None]
    # the state the apply leaves: each site's source_url, the kinds it holds, the values kept
    after_url = {str(s["site_id"]): str(s["source_url"]) for s in record["sites"]}
    after_url.update({row.site_id: row.new_value for row in urls})
    kinds = {
        str(s["site_id"]): {k for k, v in s["external_ids"].items() if v} for s in record["sites"]
    }
    for row in rows:
        if row.table == TABLE:
            kinds[row.site_id].add(row.kind)
    refused = {item.site_id for item in plan.left if item.what == "external ids"}
    wiki_after = [
        str(s["site_id"])
        for s in record["sites"]
        if after_url[str(s["site_id"])].startswith(ENWIKI)
    ]
    names = {str(s["site_id"]): str(s["name"]) for s in record["sites"]}
    reread = sorted(names[sid] for sid in wiki_after if not kinds[sid])
    refused_wiki = sorted(names[sid] for sid in wiki_after if sid in refused)
    fixed = {(row.site_id, row.kind) for row in corrected}
    broken_kept = sorted(
        (str(s["name"]), kind)
        for s in record["sites"]
        for kind, values in s["external_ids"].items()
        for value in values
        if CONTROL_RE.search(value) and (str(s["site_id"]), kind) not in fixed
    )
    lines = [
        "# Source-url split, wave 4 (2026-09-23) - planned, not applied",
        "",
        f"{len(rows)} row changes (run stamp `{wave.run_stamp}`): {len(urls)} "
        f"`unified_sites.source_url` values keep their first URL, {len(new)} `site_external_ids` "
        f"rows are new and {len(corrected)} corrected; {len(plan.left)} value(s) are left, each with "
        f"its reason. The input is `wave4/{RESOLUTION}`: production read {record['read_at']} (every "
        f"`unified_sites` row whose `source_url` carries a control character: "
        f"{len(record['sites'])}), English Wikipedia resolved {record['resolved_at']} through "
        "`pipeline.lyra.prospector.wiki.resolve_titles`. The rules are in the module docstring of "
        "`output/remediation/tools/qid_repair.py`.",
        "",
        "| site | column / kind | old | new |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.name} (`{row.site_id}`) | {row.kind} | {_cell(row.old_value)} | "
            f"{_cell(row.new_value)} |"
        )
    lines += [
        "",
        "## Left as they are, and why",
        "",
        "| site | what | reason |",
        "| --- | --- | --- |",
        *(
            f"| {item.name} (`{item.site_id}`) | {item.what} | {item.reason} |"
            for item in plan.left
        ),
        "",
        "## Hand-read (a refusal of the rule overridden by quoted evidence)",
        "",
        "| site | the refusal it overrides | evidence |",
        "| --- | --- | --- |",
        *(
            f"| {entry.name} (`{entry.site_id}`) | {entry.overrides} | "
            + "<br>".join(entry.evidence)
            + " |"
            for entry in plan.hand_read
        ),
        "",
        "## Duplicate candidates (the owner's merge, not a link)",
        "",
        "| site | the other curated site | shared item | evidence |",
        "| --- | --- | --- | --- |",
        *(
            f"| {dup['name']} (`{dup['site_id']}`) | {other['name']} (`{other['site_id']}`) | "
            f"`{dup['qid']}` | {_duplicate_evidence(dup, other)} |"
            for dup in plan.duplicates
            for other in dup["others"]
        ),
        "",
        "## Order and fixed point",
        "",
        "* After the apply the boot refresh (`refresh_site_external_ids(only_missing=True)`) reads "
        "only a site with no external-id row and an English Wikipedia `source_url`: "
        + (", ".join(reread) if reread else "none of these sites")
        + ". The manual `--all` path reads every curated site whose `source_url` is an English "
        "Wikipedia article, and would write the ids this wave refuses for "
        + (", ".join(refused_wiki) if refused_wiki else "none of them")
        + " - the fixed point waves 1-3 name for their own rows.",
        *(
            f"* {name} keeps its stored {kind} value with a control character: the wave refuses the "
            "article's resolution, so it has no replacement to write, and a removal is a `DELETE` - "
            "the owner's call."
            for name, kind in broken_kept
        ),
        "* `migrations/0023_source_url_no_control_chars.sql` may reach the deploy only after this "
        "wave is applied and verified: it fails while any `source_url` carries a control character, "
        "and a failing migration stops the deploy. Once it is applied, the `source_url` half of "
        "`ROLLBACK.sql` cannot run (the CHECK refuses the two-URL value).",
        "",
        "## How to run it (the orchestrator's job, in this order)",
        "",
        f"`resolve --wave 4` (read-only: production and English Wikipedia) wrote `{RESOLUTION}`, "
        "the versioned input of this plan. Run it again only to re-plan: it renews both "
        "timestamps, so every row's evidence and the plan digest change with it.",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        "$PY output/remediation/tools/qid_repair.py render --wave 4   # REHEARSAL.sql is not versioned",
        "$PY output/remediation/tools/qid_repair.py check --wave 4    # read-only",
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave4/REHEARSAL.sql',
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/wave4/APPLY.sql',
        "$PY output/remediation/tools/qid_repair.py verify --wave 4   # read-only",
        "```",
        "",
    ]
    return "\n".join(lines)


def planned_rows(wave: Wave, out: pathlib.Path) -> list[Change]:
    """The rows a wave changes: waves 1-3 from their researched sites, wave 4 from its record."""
    if wave.number == SPLIT_WAVE:
        return split_plan(load_resolution(out), hand_read=WAVE4_HAND_READ).rows
    return changes(wave.sites, gate_m=wave.gate_m)


#: Each wave's decision record (wave 4's is `wave4_markdown`, over its whole plan).
MARKDOWN: dict[int, Callable[[list[Change]], str]] = {
    1: plan_markdown,
    2: wave2_markdown,
    3: wave3_markdown,
}


def write_files(out: pathlib.Path = OUT, wave: Wave = WAVE1) -> list[Change]:
    if wave.number == SPLIT_WAVE:
        plan = split_plan(load_resolution(out), hand_read=WAVE4_HAND_READ)
        rows, markdown = plan.rows, wave4_markdown(plan)
    else:
        rows = changes(wave.sites, gate_m=wave.gate_m)
        markdown = MARKDOWN[wave.number](rows)
    out.mkdir(parents=True, exist_ok=True)
    (out / "PLAN.jsonl").write_text(
        "".join(row.to_json_line() + "\n" for row in rows), encoding="utf-8", newline="\n"
    )
    for name, sql in statements(rows, wave).items():
        (out / name).write_text(sql, encoding="utf-8", newline="\n")
    (out / "PLAN.md").write_text(markdown, encoding="utf-8", newline="\n")
    return rows


def read_rows(rows: list[Change], *, run: Callable[[str], str]) -> dict[tuple[str, str], list[str]]:
    """`{(site_id, kind): [values]}` for the planned rows, read-only (a site column's key is
    `(site_id, column)`)."""
    found: dict[tuple[str, str], list[str]] = {}
    ext = [row for row in rows if row.table == TABLE]
    if ext:
        ids = sorted({row.site_id for row in ext})
        sql = (
            "SELECT to_jsonb(t)::text FROM (SELECT site_id::text AS site_id, kind, value "
            f"FROM {TABLE} WHERE site_id::text IN ({lanes.sql_literals(ids)}) "
            f"AND kind IN ({lanes.sql_literals(KINDS)})) t;"
        )
        for record in lanes.json_rows(run(sql)):
            found.setdefault((record["site_id"], record["kind"]), []).append(record["value"])
    urls = [row for row in rows if row.table == SITES_TABLE]
    if urls:
        # by the key in its own type, so the primary-key index is used (the 0022 lesson)
        keys = ", ".join(
            f"{lanes.sql_text(sid)}::uuid" for sid in sorted({r.site_id for r in urls})
        )
        sql = (
            f"SELECT to_jsonb(t)::text FROM (SELECT id::text AS site_id, {URL_COLUMN} AS value "
            f"FROM {SITES_TABLE} WHERE id IN ({keys})) t;"
        )
        for record in lanes.json_rows(run(sql)):
            # a cleared source_url (an L5 removal) holds no value, like a removed external-id row
            value = record["value"]
            found[(record["site_id"], URL_COLUMN)] = [] if value is None else [value]
    return found


def compare(rows: list[Change], found: dict[tuple[str, str], list[str]], *, want: str) -> list[str]:
    """What differs from the plan's `old` (pre-flight) or `new` (after the apply) values. An old
    value None is "no row of the kind"."""
    problems = []
    for row in rows:
        expected = row.old_value if want == "old" else row.new_value
        values = found.get((row.site_id, row.kind), [])
        if values != ([] if expected is None else [expected]):
            problems.append(f"{row.name} {row.kind}: expected [{expected!r}], found {values!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qid-repair")
    parser.add_argument("command", choices=("resolve", "render", "check", "verify"))
    parser.add_argument("--wave", type=int, choices=sorted(WAVES), default=1)
    parser.add_argument("--dir", default=None, help="where the plan and statements live")
    parser.add_argument("--host", default=lanes.HOST)
    args = parser.parse_args(argv)
    wave = WAVES[args.wave]
    out = pathlib.Path(args.dir) if args.dir else wave.out

    def run(sql: str) -> str:
        return lanes.psql(sql, host=args.host)

    if args.command == "resolve":
        if wave.number != SPLIT_WAVE:
            raise SystemExit(f"only wave {SPLIT_WAVE} is resolved; waves 1-3 are researched sites")
        record = resolve_split(run)
        write_resolution(out, record)
        print(
            f"{len(record['sites'])} site(s), {len(record['resolutions'])} title(s) resolved "
            f"into {out / RESOLUTION}"
        )
        return 0
    if args.command == "render":
        rows = write_files(out, wave)
        print(f"{len(rows)} changes rendered into {out} (digest {plan_digest(rows)[:16]})")
        return 0
    rows = [
        Change(**{**r, "evidence": tuple(r["evidence"])})
        for r in lanes.read_jsonl(out / "PLAN.jsonl")
    ]
    if rows != planned_rows(wave, out):
        raise SystemExit("PLAN.jsonl is not the plan this script renders; run `render` again")
    assert_rendered(out, rows, wave)

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
