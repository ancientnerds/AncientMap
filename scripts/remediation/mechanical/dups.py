"""Owner decision O9: five confirmed duplicate pairs retired (`dup-retire`).

## The decision

`output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`, B1-D (four pairs) and B6 (Banias), decided
on 2026-09-26 under the owner's O9 ("nach meiner Empfehlung entscheiden"): when the reading shows one
site, "der Verlierer wird `retired` (`duplicate_of:<uuid>`). Nichts wird gelöscht." The survivor is the
scope lane's rule (`scope.survivor_rank`: the older row, then more content links, description
citations, images, then the lower id), applied as B6 says for Banias. WD2 read the pairs on 2026-10-01
(read-only, Wikipedia, Wikidata and production) and confirmed five as one site each; the sixth
candidate of B1-D, Lycian Mezari 2 / Amyntas Rock Tombs, is not confirmed and not in this lane.

| retired | survivor | one site by |
|---|---|---|
| Banias (`ae2ca7b1`) | Caesarea Philippi (`ce7db300`) | Q606295, enwiki `Banias`; the modern and the ancient name |
| Ancient Amathunta (`3ebb514f`) | Amathus (`51daf6c9`) | Q2343313, enwiki `Amathus`; 11 m |
| Ñusta Hispana (`dafc7527`) | Conjunto Arqueologico de Ñustahispana (`d41368ba`) | Q13191401, enwiki `Ñusta Hispana`; 470 m |
| Thirty-nine (39) Bridge Street, Chester (`f23a31c3`) | Bridge Street Number 39, Chester (`21ac323f`) | Q4636108, enwiki `39 Bridge Street, Chester`; 14 m |
| Shaduppum (`f967e3c4`) | Tel Hermal Fort (`0d8af59c`) | Q3481186, enwiki `Shaduppum`; 20 m |

**No country is written** (B10: Banias is Syria, Caesarea Philippi Israel, and "welche Zeile bleibt,
entscheidet ein Land" - the owner said leave it). The lane writes two cells per retired row,
`scope_status` and `scope_reason`, both NULL until now, and nothing else: no description, name, link
or image moves, and nothing is deleted. A retired row keeps its content links and images (Banias holds
4 and 20): the hide takes the row out of view, as scope-e4's 19 duplicates were.

## What is checked before anything is planned (`build`, the first failure refuses the plan)

Per pair: both rows exist and are curated; the retired row holds the pinned name and no scope decision,
its scope journal ends at the live values, and no row is retired onto it (retiring a survivor would
leave its duplicates pointing at a hidden row); the survivor holds the pinned name and is not retired;
both rows carry the pinned Wikidata item and Wikipedia title as external ids (the premise of the
retirement, guard 5); the points lie within 2,000 m (`lane.DUP_RETIRE_METRES`, the owner-case
list's `DUP_MAX_M`; the scope lane's 100 m is for pairs it finds itself - two of these are 290 m and
470 m apart); the scope lane's survivor rule keeps the pinned survivor; and each row's description
holds the pinned opening sentence verbatim (whitespace folded). Across pairs: no id appears twice, so
no survivor is another pair's loser. Neither stamp journals a row yet: a lane that has written is
never re-planned.

The transaction repeats what it can: guards 1-4 (curated, two real changes in the two cells, planned
old values NULL, status `retired` only), guard 5 (name and external ids as read), and after the write
the three survivor checks (the survivor is a curated row, not retired - also not by this very write -
within 2,000 m), each probed with a row of its kind.

`--write` reads production read-only, in one snapshot (`plan.tagged_export_script`), keeps the read as
`mechanical_dups/READ.jsonl` and writes `PLAN.jsonl`, `PLAN.md` and `ROLLBACK.sql`. Nothing is written
to production here: `apply.py --lane dup-retire` renders, rehearses, probes and runs the transaction
(docs/procedures/SITES_DB_REMEDIATION_2026-09.md, "Owner decision O9: five duplicates retired").
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import plan as P  # noqa: E402
from mechanical.lane import (  # noqa: E402
    DUP_RETIRE,
    DUP_RETIRE_METRES,
    DUPLICATE_PREFIX,
    sphere_metres,
    sql_literal,
)
from mechanical.scope import survivor_rank  # noqa: E402
from pipeline.utils.public_sites import RETIRED  # noqa: E402

log = logging.getLogger("mechanical.dups")

ROOT = REPO / "output" / "remediation"
READ_PATH = Path(DUP_RETIRE.out_dir_name) / "READ.jsonl"
DECISIONS_FILE = "output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md"
RULE = "o9-duplicate-retire"
EVIDENCE_READ = "read 2026-10-01 through the public MediaWiki and Wikidata APIs"
QID = "wikidata_qid"
ENWIKI = "enwiki_title"
#: What the owner decided, as the decisions file words it (whitespace folded; a test holds each to
#: the file).
B1D_QUOTE = (
    "Belegt die Lesung eine einzige Stätte, wird der Verlierer `retired` (`duplicate_of:<uuid>`). "
    "Nichts wird gelöscht."
)
B6_QUOTE = (
    "Die Überlebensregel gilt wie bei den 19: Banias wird `retired` "
    "(`duplicate_of:ce7db300-8777-425d-917a-2f6d9f325b58`). **Kein Land wird geschrieben** (B10)."
)


@dataclass(frozen=True)
class Pair:
    """One confirmed duplicate pair: the retired row, its survivor and what makes them one site."""

    loser: str
    loser_name: str
    loser_quote: str
    survivor: str
    survivor_name: str
    survivor_quote: str
    qid: str
    title: str
    decision: str
    decision_quote: str
    note: str
    evidence: tuple[Mapping[str, Any], ...]

    @property
    def reason(self) -> str:
        return f"{DUPLICATE_PREFIX}{self.survivor}"


def _wiki(title: str, quote: str) -> dict[str, Any]:
    return {
        "source": f"en.wikipedia.org, article {title!r} ({EVIDENCE_READ})",
        "url": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
        "quote": quote,
    }


def _item(qid: str, quote: str) -> dict[str, Any]:
    return {
        "source": f"wikidata:{qid} ({EVIDENCE_READ})",
        "url": f"https://www.wikidata.org/wiki/{qid}",
        "quote": quote,
    }


PAIRS = (
    Pair(
        loser="ae2ca7b1-89da-46cb-8924-f9d04dd5da2e",
        loser_name="Banias",
        loser_quote=(
            "Banias, also spelled Banyas, is a site in the Israeli-occupied Golan Heights, Syria "
            "near a natural spring, once associated with the Greek god Pan"
        ),
        survivor="ce7db300-8777-425d-917a-2f6d9f325b58",
        survivor_name="Caesarea Philippi",
        survivor_quote=(
            "Caesarea Philippi, originally called Banias, is an ancient site at the foot of Mount "
            "Hermon in the Golan Heights"
        ),
        qid="Q606295",
        title="Banias",
        decision="B6",
        decision_quote=B6_QUOTE,
        note=(
            "Banias and Caesarea Philippi are one site under its modern and its ancient name: both "
            "rows carry Q606295 and the Wikipedia title Banias, which names the Caesarea Philippi "
            "of Josephus and the Gospels as the city founded at the Banias spring; the retired "
            "row's point is 11 m from Wikipedia's (33.24861, 35.69444), the survivor's 279 m"
        ),
        evidence=(
            _wiki(
                "Banias",
                "is a site in the Israeli-occupied Golan Heights, Syria near a natural spring, once "
                "associated with the Greek god Pan",
            ),
            _wiki(
                "Banias",
                "In 3 BCE, Herod's son, Philip (also known as Philip the Tetrarch) founded a city "
                "which became his administrative capital, known from Josephus and the Gospels of "
                "Matthew and Mark as Caesarea or Caesarea Philippi",
            ),
            _item(
                "Q606295",
                "label 'Banias', description 'archaeological site in the Golan Heights', enwiki "
                "sitelink 'Banias'; coordinates 33.2472, 35.6939 and 33.2472, 35.6933",
            ),
        ),
    ),
    Pair(
        loser="3ebb514f-ac4a-4913-b54b-409bcc29eff4",
        loser_name="Ancient Amathunta",
        loser_quote="Ancient Amathus was one of the ancient royal cities of Cyprus",
        survivor="51daf6c9-25d3-4818-8857-0543f1203c57",
        survivor_name="Amathus",
        survivor_quote="Amathus or Amathous was an ancient city-kingdom of Cyprus",
        qid="Q2343313",
        title="Amathus",
        decision="B1-D",
        decision_quote=B1D_QUOTE,
        note=(
            "both rows are the ancient royal city of Amathus near Agios Tychonas: the one item and "
            "the one Wikipedia title, 11 m apart, the same Aphrodite-sanctuary description; "
            "'Amathunta' is the Greek form (Amathounta) of the name. Wikipedia's Amathus article "
            "does not list 'Amathunta' as an alias, so the reading rests on the shared item, title "
            "and place, not on the name"
        ),
        evidence=(
            _wiki(
                "Amathus",
                "Amathus or Amathous (Ancient Greek: Ἀμαθοῦς) was an ancient city-kingdom of "
                "Cyprus. [...] Remains of Amathus can be seen today on the southern coast near "
                "Agios Tychonas, about 6 miles (9.7 km) east of Limassol and 24 miles (39 km) west "
                "of Larnaca",
            ),
            _item(
                "Q2343313",
                "label 'Amathus', description 'ancient city and one of the ancient royal cities of "
                "Cyprus until about 300 BC.', coordinates 34.7125, 33.1419, enwiki sitelink "
                "'Amathus'",
            ),
            _wiki(
                "Amathounta",
                "Amathounta Municipality (Greek: Δήμος Αμαθούντας) is a municipality located in "
                "the Limassol District of Cyprus. Headquartered in Agios Athanasios, it is "
                "composed of eight municipal districts: Agios Athanasios, Germasogeia, Agios "
                "Tychonas, Akrounta, Mathikoloni, Mouttagiaka, Foinikaria, and Armenochori.",
            ),
        ),
    ),
    Pair(
        loser="dafc7527-c6c8-45c3-8c7d-4813d20a4dcf",
        loser_name="Ñusta Hispana",
        loser_quote=(
            "Nusta Hispana (also called Chuquipalta) is an Inca archaeological site in the "
            "Vilcabamba region, Cusco, Peru"
        ),
        survivor="d41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d",
        survivor_name="Conjunto Arqueologico de Ñustahispana",
        survivor_quote=(
            "Nusta Hispana, also known as Chuquipalta, is an Inca archaeological site near "
            "Vilcabamba in Peru's Cusco region"
        ),
        qid="Q13191401",
        title="Ñusta Hispana",
        decision="B1-D",
        decision_quote=B1D_QUOTE,
        note=(
            "both rows are the Inca site Ñusta Hispana (Chuquipalta, with Yurac Rumi) at "
            "Vilcabamba: the one item and the one Wikipedia title, 470 m apart, the same "
            "description; Wikipedia and Wikidata place the single site at -13.11167, -72.92417, "
            "21 m from the retired row's point and 473 m from the survivor's. The two rows tie "
            "on created_at, content links (0), citations (0) and images (20), so the lower id "
            "keeps, and the survivor keeps its own name"
        ),
        evidence=(
            _wiki(
                "Ñusta Hispana",
                "Ñusta Hispana Ñusta Ispanan (also written Ñusta Ispana), previously known as "
                "Chuquipalta (possibly from Quechua chuqi precious metal, p'allta plane) is an "
                "archaeological site in Peru. It is located at Vilcabamba, La Convención Province, "
                "Cusco Region.",
            ),
            _item(
                "Q13191401",
                "label \"Ñusta Hisp'ana\", description 'archaeological site in Peru', coordinates "
                "-13.11167, -72.92417, enwiki sitelink 'Ñusta Hispana'",
            ),
        ),
    ),
    Pair(
        loser="f23a31c3-6833-4df6-8583-3b3930b5a74f",
        loser_name="Thirty-nine (39) Bridge Street, Chester",
        loser_quote=(
            "A Grade I listed building in Chester, England, notable for the remains of a "
            "2nd-century Roman hypocaust in its cellar"
        ),
        survivor="21ac323f-7214-4891-9499-74e55c3d7d56",
        survivor_name="Bridge Street Number 39, Chester",
        survivor_quote=(
            "39 Bridge Street is a Grade I listed building in Chester, England, remarkable for "
            "preserving a Roman hypocaust in its cellar"
        ),
        qid="Q4636108",
        title="39 Bridge Street, Chester",
        decision="B1-D",
        decision_quote=B1D_QUOTE,
        note=(
            "both rows are the one Grade I listed building with a Roman hypocaust in its cellar: "
            "the one item and the one Wikipedia title, 14 m apart, the same 27 surviving columns "
            "(originally 32 in eight rows). The rows tie on created_at, citations (0) and images "
            "(3); the survivor holds 3 content links, the retired row 0"
        ),
        evidence=(
            _wiki(
                "39 Bridge Street, Chester",
                "39 Bridge Street is a building in Chester, Cheshire, England. It is recorded in "
                "the National Heritage List for England as a designated Grade I listed building, "
                "its major archaeological feature being the remains of a Roman hypocaust in its "
                "cellar.",
            ),
            _wiki(
                "39 Bridge Street, Chester",
                "They consist of 27 square columns in a rectangular chamber which originally "
                "contained 32 columns in eight rows of four.",
            ),
            _item(
                "Q4636108",
                "label '39 Bridge Street, Chester', description 'Grade I listed building in "
                "Chester, United Kingdom', coordinates 53.1895, -2.8912, enwiki sitelink "
                "'39 Bridge Street, Chester'",
            ),
        ),
    ),
    Pair(
        loser="f967e3c4-fc5b-4cd0-91d1-06030d51e31c",
        loser_name="Shaduppum",
        loser_quote=(
            "Shaduppum (modern Tell Harmal) was an administrative center in the kingdom of Eshnunna"
        ),
        survivor="0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3",
        survivor_name="Tel Hermal Fort",
        survivor_quote=(
            "Tel Hermal (ancient Shaduppum) is an Old Babylonian site in present-day Baghdad"
        ),
        qid="Q3481186",
        title="Shaduppum",
        decision="B1-D",
        decision_quote=B1D_QUOTE,
        note=(
            "Shaduppum is the ancient name and Tell Harmal / Tel Hermal the modern name of one "
            "tell in Baghdad: the one item and the one Wikipedia title, 20 m apart (B1-D's "
            "'1,7 km' is not what production holds: Wikipedia's point 33.309483, 44.467065 is the "
            "survivor's stored point). The survivor holds 5 content links and 1 citation, the "
            "retired row 0 and 0; the retired row's longer text (Gilgamesh tablets, the Laws of "
            "Eshnunna) is not merged here"
        ),
        evidence=(
            _wiki(
                "Shaduppum",
                "Shaduppum (Šaduppȗm), modern Tell Harmal (also Tell Abu Harmal and Tel Harmal), is "
                "an archaeological site in Baghdad Governorate (Iraq). Nowadays, it lies within "
                "the borders of modern Baghdad about 600 meters from the site of Tell Muhammad",
            ),
            _wiki(
                "Shaduppum",
                "The site, 150 meters in diameter and 5 meters high. Tell Harmal consists of a "
                "heavily fortified irregular rectangle",
            ),
            _item(
                "Q3481186",
                "label 'Shaduppum', description 'Archaeological site in Baghdad', alias 'Tell "
                "Harmal', enwiki sitelink 'Shaduppum'; Wikipedia's coordinates are 33.309483, "
                "44.467065",
            ),
        ),
    ),
)
#: The decision's own words are cited per pair; every quote is held to the file by a test.
DECISION_QUOTES = {"B1-D": B1D_QUOTE, "B6": B6_QUOTE}


# ------------------------------------------------------------------------------------ the read
def read_parts() -> tuple[tuple[str, str], ...]:
    """What the plan reads, each part one query of one read-only snapshot."""
    ids = P.sql_ids([i for pair in PAIRS for i in (pair.loser, pair.survivor)])
    losers = P.sql_ids([pair.loser for pair in PAIRS])
    site = (
        "SELECT u.id::text AS id, u.name, u.source_id, u.scope_status, u.scope_reason, u.lat, "
        "u.lon, u.created_at::text AS created_at, "
        "(SELECT count(*) FROM site_content_links c WHERE c.site_id = u.id) AS links, "
        "(SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS images, "
        "jsonb_array_length(coalesce(u.raw_data->'description_citations', '[]'::jsonb)) "
        "AS citations, coalesce(u.description, '') AS description, "
        f"{DUP_RETIRE.premise_sql} AS premise "
        f"FROM unified_sites u WHERE u.id IN ({ids}) ORDER BY u.id"
    )
    ext = (
        "SELECT e.site_id::text AS id, e.kind, e.value FROM site_external_ids e "
        f"WHERE e.site_id IN ({ids}) ORDER BY e.site_id, e.kind, e.value"
    )
    pairs = ", ".join(f"({sql_literal(p.loser)}, {sql_literal(p.survivor)})" for p in PAIRS)
    metres = (
        f"SELECT p.loser AS loser, {sphere_metres('l', 's')} AS metres "
        f"FROM (VALUES {pairs}) AS p(loser, survivor) "
        "JOIN unified_sites l ON l.id::text = p.loser JOIN unified_sites s ON s.id::text = "
        "p.survivor ORDER BY p.loser"
    )
    onto = (
        "SELECT d.id::text AS id, d.name, d.scope_reason FROM unified_sites d "
        f"WHERE d.source_id = 'ancient_nerds' AND d.scope_status = '{RETIRED}' AND "
        f"d.scope_reason IN ({', '.join(sql_literal(DUPLICATE_PREFIX + p.loser) for p in PAIRS)}) "
        "ORDER BY d.id"
    )
    journal = (
        "SELECT id, row_pk, column_name, run_stamp, coalesce(test_id, '') AS test_id, old_value, "
        "new_value FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND row_pk IN ({losers}) AND column_name IN ('scope_status', 'scope_reason') ORDER BY id"
    )
    stamps = (
        "SELECT run_stamp, count(*) AS n FROM remediation_change_log WHERE run_stamp IN ("
        + ", ".join(sql_literal(s) for s in (DUP_RETIRE.run_stamp, DUP_RETIRE.rollback_run_stamp))
        + ") GROUP BY run_stamp ORDER BY run_stamp"
    )
    return (
        ("site", site),
        ("ext", ext),
        ("metres", metres),
        ("onto", onto),
        ("journal", journal),
        ("stamp", stamps),
    )


@dataclass(frozen=True)
class Read:
    """The production read the plan rests on."""

    sites: Mapping[str, Mapping[str, Any]]
    ext: Mapping[str, tuple[tuple[str, str], ...]]
    metres: Mapping[str, float]
    onto: tuple[Mapping[str, Any], ...]
    journal: Mapping[tuple[str, str], tuple[P.JournalLink, ...]]
    stamps: Mapping[str, int]
    read_at: str


def parse_read(text: str) -> Read:
    """The tagged read (`plan.parse_tagged_export` refuses a line of another kind and a read
    without its one snapshot line)."""
    rows, read_at = P.parse_tagged_export(text, (kind for kind, _sql in read_parts()))
    journal: dict[tuple[str, str], list[P.JournalLink]] = {}
    for r in sorted(rows["journal"], key=lambda r: int(r["id"])):
        journal.setdefault((str(r["row_pk"]), str(r["column_name"])), []).append(
            P.JournalLink(
                int(r["id"]), str(r["run_stamp"]), str(r["test_id"]), r["old_value"], r["new_value"]
            )
        )
    ext: dict[str, list[tuple[str, str]]] = {}
    for r in rows["ext"]:
        ext.setdefault(str(r["id"]), []).append((str(r["kind"]), str(r["value"])))
    return Read(
        sites={str(r["id"]): r for r in rows["site"]},
        ext={sid: tuple(pairs) for sid, pairs in ext.items()},
        metres={str(r["loser"]): float(r["metres"]) for r in rows["metres"]},
        onto=tuple(rows["onto"]),
        journal={cell: tuple(links) for cell, links in journal.items()},
        stamps={str(r["run_stamp"]): int(r["n"]) for r in rows["stamp"]},
        read_at=read_at,
    )


def write_read(path: Path) -> Path:
    """Read production (read-only, one snapshot) and keep the answer as it came."""
    return P.write_tagged_export(P.tagged_export_script(read_parts()), path)


# -------------------------------------------------------------------------------- the decision
def _refuse(pair: Pair, why: str) -> P.PlanError:
    return P.PlanError(f"{pair.loser_name!r} ({pair.loser}) -> {pair.survivor_name!r}: {why}")


def _fold(text: str) -> str:
    return " ".join(text.split())


def _row(read: Read, pair: Pair, site_id: str, name: str, role: str) -> Mapping[str, Any]:
    row = read.sites.get(site_id)
    if row is None:
        raise _refuse(pair, f"the {role} ({site_id}) is not in unified_sites")
    if row["source_id"] != P.CURATED_SOURCE:
        raise _refuse(pair, f"the {role} is not a curated site: {row['source_id']!r}")
    if row["name"] != name:
        raise _refuse(pair, f"the {role} is named {row['name']!r}; the decision names {name!r}")
    return row


def _shares_item(read: Read, pair: Pair, row: Mapping[str, Any], role: str) -> None:
    held = read.ext.get(str(row["id"]), ())
    for kind, wanted in ((QID, pair.qid), (ENWIKI, pair.title)):
        values = [value for k, value in held if k == kind]
        if values != [wanted]:
            raise _refuse(pair, f"the {role}'s {kind} is {values!r}, the pair is one by {wanted!r}")
    if f"{QID}={pair.qid}" not in row["premise"] or f"{ENWIKI}={pair.title}" not in row["premise"]:
        raise _refuse(pair, f"the {role}'s premise {row['premise']!r} does not carry the ids")


def _opens_with(pair: Pair, row: Mapping[str, Any], quote: str, role: str) -> None:
    if _fold(quote) not in _fold(str(row["description"])):
        raise _refuse(pair, f"the {role}'s description does not hold {quote!r}")


def check_pair(read: Read, pair: Pair) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """`(retired row, survivor)` as the decision has them - or the refusal that says why not."""
    loser = _row(read, pair, pair.loser, pair.loser_name, "row to retire")
    survivor = _row(read, pair, pair.survivor, pair.survivor_name, "survivor")
    if loser["scope_status"] is not None or loser["scope_reason"] is not None:
        raise _refuse(
            pair,
            f"the row to retire already has a scope decision: {loser['scope_status']!r}, "
            f"{loser['scope_reason']!r}",
        )
    for column in ("scope_status", "scope_reason"):
        broken = P.journal_break(read.journal.get((pair.loser, column), ()), loser[column])
        if broken is not None:
            raise _refuse(pair, f"{column}: {broken[0]} - {broken[1]}")
    if survivor["scope_status"] == RETIRED:
        raise _refuse(pair, f"the survivor is retired ({survivor['scope_reason']!r})")
    onto = [
        str(r["id"]) for r in read.onto if r["scope_reason"] == f"{DUPLICATE_PREFIX}{pair.loser}"
    ]
    if onto:
        raise _refuse(pair, f"{', '.join(onto)} is retired onto the row to retire already")
    _shares_item(read, pair, loser, "row to retire")
    _shares_item(read, pair, survivor, "survivor")
    metres = read.metres.get(pair.loser)
    if metres is None:
        raise _refuse(pair, "the read holds no distance of the pair")
    if metres > DUP_RETIRE_METRES:
        raise _refuse(
            pair,
            f"the two rows are {metres:.1f} m apart; the lane allows {DUP_RETIRE_METRES} m",
        )
    if sorted((loser, survivor), key=survivor_rank)[0]["id"] != pair.survivor:
        raise _refuse(pair, "the scope lane's survivor rule keeps the row to retire")
    _opens_with(pair, loser, pair.loser_quote, "row to retire")
    _opens_with(pair, survivor, pair.survivor_quote, "survivor")
    return loser, survivor


def _evidence(
    pair: Pair, read: Read, loser: Mapping[str, Any], survivor: Mapping[str, Any]
) -> tuple[dict[str, Any], ...]:
    def counts(site: Mapping[str, Any]) -> str:
        return (
            f"{site['name']!r} ({site['id']}): created {site['created_at']}, {site['links']} "
            f"content link(s), {site['citations']} citation(s), {site['images']} image(s)"
        )

    return (
        {"source": DECISIONS_FILE, "url": None, "quote": f"{pair.decision}: {pair.decision_quote}"},
        *(dict(e) for e in pair.evidence),
        {
            "source": "production:unified_sites.description",
            "url": None,
            "quote": f"{loser['name']!r}: {pair.loser_quote}. {survivor['name']!r}: "
            f"{pair.survivor_quote}",
        },
        {
            "source": "production:site_external_ids",
            "url": None,
            "quote": f"both rows carry {QID}={pair.qid} and {ENWIKI}={pair.title}; "
            f"{read.metres[pair.loser]:.1f} m apart (read {read.read_at})",
        },
        {
            "source": "survivor rule",
            "url": "scripts/remediation/mechanical/scope.py:survivor_rank",
            "quote": "older row, then more content links, description citations, images, then the "
            f"lower id: survivor {counts(survivor)} over {counts(loser)}",
        },
    )


def build(read: Read, built_at: str) -> P.Plan:
    """The plan of the five retirements: a pure function of the read - no network, no database, no
    clock."""
    ids = [i for pair in PAIRS for i in (pair.loser, pair.survivor)]
    if len(set(ids)) != len(ids):
        raise P.PlanError("a row appears in two pairs: a survivor would be another pair's loser")
    written = {stamp: n for stamp, n in read.stamps.items() if n}
    if written:
        raise P.PlanError(
            f"{written} journal row(s) exist for this lane: a lane that has written is never "
            "re-planned - its ROLLBACK.sql may be the only undo"
        )
    changes: list[P.Verdict] = []
    for pair in PAIRS:
        loser, survivor = check_pair(read, pair)
        evidence = _evidence(pair, read, loser, survivor)
        for column, value in (("scope_status", RETIRED), ("scope_reason", pair.reason)):
            changes.append(
                P.Verdict(
                    site_id=pair.loser,
                    site_name=str(loser["name"]),
                    ok=True,
                    old_value=None,
                    new_value=value,
                    rule=RULE,
                    reason="",
                    note=f"{column} NULL -> {value!r} (owner decision O9, {pair.decision}: "
                    f"{pair.note})",
                    phase3=False,
                    finding_test_id=DUP_RETIRE.test_id,
                    evidence=evidence,
                    premise=str(loser["premise"]),
                    column=column,
                )
            )
    return P.Plan(
        changes=tuple(changes),
        skipped=(),
        built_at=built_at,
        counters={"sites": len(PAIRS), "cells": len(changes)},
        lane=DUP_RETIRE,
    )


# ---------------------------------------------------------------------------------- the output
_GUARDS = (
    "guard 1: the row is a curated site",
    "guard 2: two real changes per row, only in `scope_status` and `scope_reason`",
    "guard 3: the row still holds the planned old values (both NULL)",
    "guard 4: the status written is `retired` and nothing else",
    "guard 5: the row's name and external ids (Wikidata item, Wikipedia title) are still as read",
    f"after the write, the survivor its reason names is a curated site, not retired (this write "
    f"included), and within {DUP_RETIRE_METRES} m (three checks, each probed with a row of its "
    "kind)",
    "one journal row per cell, and exactly the planned cells moved",
)


def plan_md(plan: P.Plan, read: Read) -> str:
    lane = plan.lane
    lines = [
        "# Owner decision O9: five duplicates retired (`dup-retire`): plan",
        "",
        f"Built {plan.built_at} by `scripts/remediation/mechanical/dups.py` from the read-only "
        f"production read of {read.read_at} (`READ.jsonl`). Lane `{lane.name}`: run stamp "
        f"`{lane.run_stamp}`, journal test id `{lane.test_id}`, change keys "
        f"`{lane.key_prefix}:<site_id>:<column>`, premise `{lane.premise_sql}`. Decision: "
        f"`{DECISIONS_FILE}`, B1-D and B6 (O9, 2026-09-26).",
        "",
        f"**{plan.counters['sites']} sites, {plan.counters['cells']} cells.** Nothing is deleted "
        "and no country is written (B10).",
        "",
        "| retired | cell | old | new |",
        "|---|---|---|---|",
    ]
    for v in plan.changes:
        old = "NULL" if v.old_value is None else f"`{v.old_value}`"
        lines.append(f"| {v.site_name} (`{v.site_id}`) | {v.column} | {old} | `{v.new_value}` |")
    lines += ["", "## What the transaction checks", "", *[f"* {g}" for g in _GUARDS], ""]
    for pair in PAIRS:
        lines += [
            f"## {pair.loser_name} -> {pair.survivor_name} ({pair.decision})",
            "",
            f"Retired `{pair.loser}`, survivor `{pair.survivor}`: {pair.note}.",
            "",
            *[f"* {e['source']}: {e['quote']}" for e in pair.evidence],
            f"* production: {read.metres[pair.loser]:.1f} m apart; both rows carry {QID}="
            f"{pair.qid} and {ENWIKI}={pair.title}",
            "",
        ]
    lines += [
        "## Run",
        "",
        "```bash",
        "PY=./.venv/Scripts/python.exe",
        *[
            f"$PY scripts/remediation/mechanical/apply.py --lane {lane.name} {flag}"
            for flag in (
                "--check-primitive",
                "--verify",
                "--interests",
                "--emit",
                "--rehearse",
                "--probe-guards",
                "--apply",
                "--verify",
                "--rehearse-rollback",
            )
        ],
        "```",
        "",
        "Undo, only as a decision: `ROLLBACK.sql` sets the ten cells back to NULL.",
        "",
    ]
    return "\n".join(lines)


def write_plan(plan: P.Plan, read: Read, root: Path) -> Path:
    """The lane's files in its directory under `root` (`apply.lane_dir` for the default)."""
    directory = root / plan.lane.out_dir_name
    directory.mkdir(parents=True, exist_ok=True)
    P.write_plan_jsonl(plan, directory / "PLAN.jsonl")
    (directory / "PLAN.md").write_text(plan_md(plan, read), encoding="utf-8", newline="\n")
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo
    P.write_rollback_sql(plan, directory / "ROLLBACK.sql", plan_path=directory / "PLAN.jsonl")
    return directory


# ------------------------------------------------------------------------------------------ CLI
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan owner decision O9: five duplicates retired")
    ap.add_argument("--root", type=Path, default=ROOT, help="default: output/remediation")
    ap.add_argument(
        "--write",
        action="store_true",
        help="read production (read-only) and write PLAN.jsonl, PLAN.md and ROLLBACK.sql",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.write:
        ap.print_help()
        return 0
    try:
        path = write_read(args.root / READ_PATH)
        read = parse_read(path.read_text(encoding="utf-8"))
        plan = build(read, P._now())
    except P.PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    write_plan(plan, read, args.root)
    print(json.dumps(dict(plan.counters), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
