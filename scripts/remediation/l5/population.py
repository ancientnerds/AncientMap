"""Who L5 reads, and what production holds about each of them (read-only).

## The population (HUMAN_ONLY_DECISIONS_2026-09-26, B1-L and B1-N)

* **wave1-unresolved** - the one site the first external-id repair left unresolved: Tikal, named
  Tikal but described and linked as Mundo Perdido (`qid_repair.SITES`);
* **wave2-unresolved** - the 47 wrong links wave 2 researched and left unchanged, each with its
  reason (`qid_repair.WAVE2_SITES`; among them the 11 without a 1-km proof and the two records that
  contradict themselves);
* **link-suspect** - the 72 kept names whose link the owner-case classifier flagged on its own
  (`bcases/names.jsonl`, `link_suspect`: a generic item, one other curated rows share, an item more
  than 5 km away); wave 3 researched 39 of them, and its outcome is part of the question;
* **name-n7** - the 46 stored names that are none of the item's names (`bcases/names.jsonl`, class
  N7): their name is asked too;
* **found-by-we** - links found wrong while the WE lanes were planned (`EXTRA`).

The groups are disjoint on the data of 2026-09-26 (167 sites). The name is asked too of the three
records that contradict themselves (`SELF_CONTRADICTORY`, HUMAN_ONLY Nr. 6 "2 widersprüchliche +
Tikal"): which site the record is decides its links and its name together.

Not asked, each listed with its reason (`excluded`):

* a retired site - hidden everywhere, nothing of it is written;
* a duplicate candidate (`DUPLICATE_CANDIDATES`, HUMAN_ONLY B1-D and B6): both rows of a pair carry
  the pair's one item because they are one site, so the link is right for the row that stays and
  the question is which row stays - WD2's, which retires the other (`duplicate_of:<uuid>`). L5
  asking them could take away the item the pair is recognised by;
* a site whose links are not one item and one article - the question's shape.

"Zoque Culture Archaeological Zone" is an N7 name whose rename is decided (HUMAN_ONLY Nr. 7,
`PINNED_NAMES`): its link is asked, its name is not.

`READ.json` (in `export/`, not versioned: it carries descriptions) is the production read the
questions are built from; `POPULATION.jsonl` and `COUNTS.json` are its versioned summary.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import qid_repair as QR  # noqa: E402 - the waves' researched sites
from mechanical.lane import sql_literal  # noqa: E402
from mechanical.plan import UUID_RE, PlanError  # noqa: E402

OUT = REPO / "output" / "remediation" / "l5"
NAMES = REPO / "output" / "remediation" / "bcases" / "names.jsonl"
READ_FILE = "READ.json"
DESCRIPTION_CHARS = 1500

GROUPS = ("wave1-unresolved", "wave2-unresolved", "link-suspect", "name-n7", "found-by-we")

#: Links found wrong while the WE lanes were planned: `(site_id, name, why)`.
EXTRA: tuple[tuple[str, str, str], ...] = (
    (
        "6aa4c8de-3794-42fe-b68e-6b6ab77bd8ed",
        "Delphinion",
        "read 2026-09-26 while planning B2-L: its item Q2677787 is the class 'ancient sanctuaries "
        "dedicated to Apollo Delphinius' (P279, no P31, its only P625 deprecated) - a type, not "
        "this sanctuary at Miletus",
    ),
)


#: HUMAN_ONLY Nr. 6, "2 widersprüchliche Einträge (+ Tikal aus Welle 1)": records whose name and
#: point say one site and whose description and source another (`qid_repair` waves 1 and 2).
SELF_CONTRADICTORY: dict[str, str] = {
    "30d3fb78-6b80-42f9-87f8-7616e63bec4f": "Tikal",
    "3a86a102-9b92-4f11-8dcf-4230d3534858": "Ramesses III Temple",
    "1d65f378-c797-47d7-827c-252df5243d13": "Rocca San Felice",
}

#: HUMAN_ONLY B1-D and B6 (decided 2026-09-26 under O9, executed by WD2): the duplicate candidates
#: of the link research and their other rows, as far as L5's sources list them.
DUPLICATE_CANDIDATES: dict[str, str] = {
    "3ebb514f-ac4a-4913-b54b-409bcc29eff4": "Ancient Amathunta / Amathus (about 10 m)",
    "0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3": "Tel Hermal Fort / Shaduppum (1.7 km)",
    "d41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d": "Nustahispana / Nusta Hispana (0.5 km)",
    "f23a31c3-6833-4df6-8583-3b3930b5a74f": "39 Bridge Street, Chester, twice (14 m)",
    "4c5103a2-0ae8-443d-9203-f3a4bf4bbd6f": "Lycian tomb entry / Amyntas Rock Tombs (1.1 km)",
    "e19f7af0-539c-474c-9404-b11f22f48846": "Amyntas Rock Tombs / the Lycian tomb entry (1.1 km)",
    "a939e800-06e4-4719-a000-165e7f5efe92": "The Temple of Artemis (GR) -> Selcuk (B1-D)",
    "e60fc487-9fb9-4e37-b590-4a035e591c7e": "The Temple of Artemis-Selcuk / the GR entry (B1-D)",
    "ce7db300-8777-425d-917a-2f6d9f325b58": "Caesarea Philippi / Banias (290 m, B6)",
}


@dataclass(frozen=True)
class PinnedName:
    """A rename the owner's decisions settle, so no agent is asked: the stored name it replaces,
    the new name, the evidence the decision rests on, and the row that must be hidden first -
    `(site id, the scope_reason it carries once retired)` - because it holds the new name."""

    old: str
    new: str
    evidence: tuple[dict[str, Any], ...]
    hidden_first: tuple[str, str]


#: HUMAN_ONLY Nr. 7, decided 2026-09-26 under O9: one site; the row kept is "Zoque Culture
#: Archaeological Zone" (3 content links, 20 images, Q4384315), renamed "Chiapa de Corzo" - the
#: English label of Q4384315, its enwiki article "Chiapa de Corzo (Mesoamerican site)". The empty
#: row "Chiapa de Corzo" (24aa135d) is hidden by WD2 as `duplicate_of:ed186ea9-...`; until it is,
#: the rename is not planned (two visible rows 7.4 m apart would both carry the name).
PINNED_NAMES: dict[str, PinnedName] = {
    "ed186ea9-9ed1-415d-828b-97d9f21401d2": PinnedName(
        "Zoque Culture Archaeological Zone",
        "Chiapa de Corzo",
        (
            {
                "source": "output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md",
                "url": None,
                "quote": "Nr. 7: eine Stätte, Richtung wie empfohlen - Chiapa de Corzo ausblenden "
                "(duplicate_of:ed186ea9...) und die Zoque-Zeile in 'Chiapa de Corzo' umbenennen",
            },
            {
                "source": "wikidata:Q4384315 en label",
                "url": "https://www.wikidata.org/wiki/Q4384315",
                "quote": "en label = 'Chiapa de Corzo' (bcases/names.jsonl, read 2026-09-23)",
            },
        ),
        (
            "24aa135d-4714-47f5-96c0-d58f0bc04b6f",
            "duplicate_of:ed186ea9-9ed1-415d-828b-97d9f21401d2",
        ),
    )
}


@dataclass(frozen=True)
class Member:
    """One site of the population: its groups, why each asks, and whether its name is asked."""

    site_id: str
    name: str
    groups: tuple[str, ...]
    why: tuple[str, ...]
    ask_name: bool


def _add(
    members: dict[str, dict[str, Any]], site_id: str, name: str, group: str, why: Iterable[str]
) -> None:
    if not UUID_RE.match(site_id):
        raise PlanError(f"{site_id!r} is not a site id")
    entry = members.setdefault(site_id, {"name": name, "groups": [], "why": []})
    if group in entry["groups"]:
        raise PlanError(f"{name} ({site_id}) is listed twice in {group}")
    entry["groups"].append(group)
    entry["why"].extend(f"{group}: {line}" for line in why)


def members(names: Sequence[Mapping[str, Any]]) -> list[Member]:
    """The population from its sources, in site-id order. Pure: `names` is `bcases/names.jsonl`."""
    found: dict[str, dict[str, Any]] = {}
    for site in QR.SITES:
        if site.rule == "unresolved":
            _add(found, site.site_id, site.name, "wave1-unresolved", site.evidence)
    for site in QR.WAVE2_SITES:
        if site.rule == "unresolved":
            _add(found, site.site_id, site.name, "wave2-unresolved", site.evidence)
    wave3 = {site.site_id: site for site in QR.WAVE3_SITES}
    for row in names:
        sid = str(row["site_id"])
        if row["link_suspect"]:
            why = [
                f"the name matches the item, but the link is suspect on its own "
                f"({', '.join(row['link_suspect'])}): item {row['qid']} ('{row['en_label']}', "
                f"P31 {', '.join(row['p31']) or 'none'}), shared by {row['shared_by']} curated "
                f"site(s), P625 {row['p625_km']} km from the stored point"
            ]
            if sid in wave3:
                w3 = wave3[sid]
                why.append(f"wave 3 ({w3.rule}): " + " | ".join(w3.evidence))
            _add(found, sid, str(row["name"]), "link-suspect", why)
        if row["class"] == "N7":
            why = [
                f"the stored name is none of the item's names ({row['n7']}): item {row['qid']} "
                f"is labelled '{row['en_label']}' (P31 {', '.join(row['p31']) or 'none'}), "
                f"P625 {row['p625_km']} km from the stored point"
            ]
            _add(found, sid, str(row["name"]), "name-n7", why)
    for sid, name, why in EXTRA:
        _add(found, sid, name, "found-by-we", [why])
    return [
        Member(
            site_id=sid,
            name=entry["name"],
            groups=tuple(entry["groups"]),
            why=tuple(entry["why"]),
            ask_name=("name-n7" in entry["groups"] or sid in SELF_CONTRADICTORY)
            and sid not in PINNED_NAMES,
        )
        for sid, entry in sorted(found.items())
    ]


def load_names(path: Path = NAMES) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------- the production read
def sites_sql(site_ids: Sequence[str]) -> str:
    ids = ", ".join(f"{sql_literal(s)}::uuid" for s in sorted(site_ids))
    return (
        "SELECT u.id::text AS site_id, u.source_id, u.name, u.name_normalized, u.country, "
        "u.lat::text AS lat, u.lon::text AS lon, u.site_type, u.period_start, u.period_name, "
        f"u.source_url, u.scope_status, left(coalesce(u.description, ''), {DESCRIPTION_CHARS}) "
        "AS description, coalesce((SELECT json_agg(json_build_object('kind', e.kind, 'value', "
        "e.value) ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = u.id), "
        f"'[]'::json) AS ext FROM unified_sites u WHERE u.id IN ({ids}) ORDER BY u.id"
    )


def sharers_sql(qids: Sequence[str]) -> str:
    listed = ", ".join(sql_literal(q) for q in sorted(qids))
    return (
        "SELECT e.value AS qid, u.id::text AS site_id, u.name, u.lat::text AS lat, "
        "u.lon::text AS lon, u.scope_status FROM site_external_ids e JOIN unified_sites u "
        "ON u.id = e.site_id WHERE e.kind = 'wikidata_qid' AND u.source_id = 'ancient_nerds' "
        f"AND e.value IN ({listed}) ORDER BY e.value, u.id"
    )


def read_production(
    population: Sequence[Member], reader: Callable[[str], list[dict[str, Any]]]
) -> dict[str, Any]:
    """The population's rows and every curated site sharing one of their items. Read-only."""
    rows = reader(sites_sql([m.site_id for m in population]))
    by_id = {str(r["site_id"]): r for r in rows}
    missing = [m.site_id for m in population if m.site_id not in by_id]
    if missing:
        raise PlanError(
            f"{len(missing)} population site(s) are not in unified_sites: {missing[:3]}"
        )
    qids = sorted({e["value"] for r in rows for e in r["ext"] if e["kind"] == "wikidata_qid"})
    sharers: dict[str, list[dict[str, Any]]] = {}
    for row in reader(sharers_sql(qids)) if qids else []:
        sharers.setdefault(str(row["qid"]), []).append(row)
    return {
        "read_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "sites": by_id,
        "sharers": sharers,
    }


def excluded(row: Mapping[str, Any]) -> str | None:
    """Why a population site is not asked, or None."""
    if row["source_id"] != "ancient_nerds":
        return f"a {row['source_id']} row, not curated"
    if row["scope_status"] == "retired":
        return "retired: hidden everywhere, nothing of it is written"
    if str(row["site_id"]) in DUPLICATE_CANDIDATES:
        return (
            f"duplicate candidate: {DUPLICATE_CANDIDATES[str(row['site_id'])]} - which row stays "
            "is WD2's (HUMAN_ONLY B1-D/B6), the pair's item is right for it"
        )
    kinds = Counter(str(e["kind"]) for e in row["ext"])
    if kinds != Counter({"wikidata_qid": 1, "enwiki_title": 1}):
        return f"links: {dict(sorted(kinds.items()))} - the question reads one item and one article"
    return None


def population_records(
    population: Sequence[Member], read: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """`POPULATION.jsonl`: each member with its stored links and whether it is asked."""
    out = []
    for member in population:
        row = read["sites"][member.site_id]
        out.append(
            {
                **asdict(member),
                "stored_name": row["name"],
                "ext": row["ext"],
                "source_url": row["source_url"],
                "scope_status": row["scope_status"],
                "excluded": excluded(row),
            }
        )
    return out


def counts(records: Sequence[Mapping[str, Any]], read_at: str) -> dict[str, Any]:
    asked = [r for r in records if r["excluded"] is None]
    return {
        "read_at": read_at,
        "members": len(records),
        "by_group": dict(Counter(g for r in records for g in r["groups"])),
        "asked": len(asked),
        "names_asked": sum(1 for r in asked if r["ask_name"]),
        "names_pinned": sum(1 for r in asked if r["site_id"] in PINNED_NAMES),
        "excluded": dict(
            Counter(str(r["excluded"]).split(":")[0] for r in records if r["excluded"])
        ),
        "asked_on_an_enwiki_source_url": sum(
            1 for r in asked if str(r["source_url"] or "").startswith(QR.ENWIKI)
        ),
    }


def write(out: Path, population: Sequence[Member], read: Mapping[str, Any]) -> dict[str, Any]:
    records = population_records(population, read)
    summary = counts(records, str(read["read_at"]))
    (out / "export").mkdir(parents=True, exist_ok=True)
    (out / "export" / READ_FILE).write_text(
        json.dumps(read, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with (out / "POPULATION.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    (out / "COUNTS.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def load_read(out: Path = OUT) -> dict[str, Any]:
    path = out / "export" / READ_FILE
    if not path.exists():
        raise PlanError(f"{path} is missing - run `run.py population` first")
    return dict(json.loads(path.read_text(encoding="utf-8")))


def load_population(out: Path = OUT) -> list[dict[str, Any]]:
    path = out / "POPULATION.jsonl"
    if not path.exists():
        raise PlanError(f"{path} is missing - run `run.py population` first")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
