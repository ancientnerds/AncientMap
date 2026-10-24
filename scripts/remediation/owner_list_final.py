"""Phase 8: the one owner list of everything that stays empty, unsourced or open after the repair.

MASTER_PLAN Phase 8: "the owner list of everything that stays empty or unsourced". Every lane that
cannot source a value leaves it as it is and lists it for the owner (D3, D8, D19, D22, D48, D49 ...);
those lists live in each lane's own directory. This collects them, and adds what only production
can say, into

    output/remediation/final-2026-10-08/OWNER_LIST_FINAL.jsonl   one row per site, topic and source
    output/remediation/final-2026-10-08/OWNER_LIST_FINAL.md      per topic, per site (for the owner)

It reads files and production (one read-only export) and writes nothing else. It is rerunnable:
each run rebuilds both files from the state of that moment. **Run it from the main checkout**: the
field runs and their waves are gitignored data there, and a wave names its run by the path the
lane resolved (`fields/owner_list.py`'s `_shown`), so a worktree would match no wave.

## The sources

* **The field runs** (`FIELD_RUNS`: WD3, WD4, wd5 and their pilots and re-asks), each rebuilt with
  `fields/owner_list.build` - never read from an older `OWNER_LIST.jsonl`, which a later run may have
  answered. A `(site, field)` that several runs asked belongs to the **last** run that asked it: a
  wd5 `keep` closes what WD3 left `unresolved`. The adversarial lists (`<run>/adv/OWNER.jsonl`) are in
  those rows already (`FIELDS_WD5.md` section 5: "the owner list shows them as `unresolved`").
* **The identity lanes' lists** (`LANE_LISTS`): the retarget and scope-window results
  (`identity/run.py ... result`), whose rows carry a state and a reason.
* **Production** (`TOPICS`): what stays empty on a shown curated site - no description, no card,
  an old card the shorts-v1 lane kept (D5), no picture, a thumbnail without any gallery row, a small
  hero a larger live row could replace (D48) or one without the credit its licence asks for, no type, no period, a rule-made period, an
  unsourced or unmarked point, no source URL, no Wikidata item, a pending scope, and a card whose
  Wikidata id or article link is no longer its site's (the fill-only `card_stats_ext` lane never
  corrects one an identity lane moved afterwards).

## The small heroes (D48)

D48 puts "the 433 small heroes" on the owner list. The census of 2026-10-08 defined them
(`state-2026-10-08/workflow_result.json`, "Served hero size buckets"; `census_digest.md`: "give the
owner the 433 as a list ... swapping to a larger row is his call"): a shown site's hero - its first
`is_hero`, non-excluded `wiki_images` row - below 1600x900 whose site holds **another** non-excluded
row of at least 1600x900. That is the swap the owner decides, so `hero-small` lists exactly those and
names the largest such row (and how many there are). A small hero without a larger row offers
nothing to decide: the report counts it, the list does not carry it. Measured read-only on
2026-10-24: 809 heroes below 1600x900, 433 of them with a larger live row - the census's figure.

## What is read, and what is named

Every owner-facing artefact under `output/remediation` - a file or directory whose name holds
`owner` or `human_only` (`OWNER_NAME`), outside caches - is either a source above, the field runs'
own lists (rebuilt from their runs), this builder's output, or one of `OUT_OF_SCOPE` with the reason
the list does not read it (the report names those too). Anything else is `unregistered`.

A lane row is still open only while production says so: a row of a retired site is set aside, and
a field row whose stored value production no longer holds was answered by a later write
(`superseded`). Both are counted, never listed.

Every `OWNER_LIST.jsonl` / `OWNER.jsonl` under `output/remediation` that no source covers is named in
the report (`unregistered`). `--final` refuses while a source is missing, a list is unregistered or an
open field row is still `pending`; without it the report names them.

    $PY scripts/remediation/owner_list_final.py build [--final]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[2]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import owner_list as OL  # noqa: E402
from fields import rule as R  # noqa: E402
from licenses import credit_columns  # noqa: E402
from mechanical import site_type_merge as STM  # noqa: E402
from mechanical.field_prov import read_production  # noqa: E402
from mechanical.lane import FIELDS_ROOTS  # noqa: E402
from mechanical.plan import parse_tagged_export, tagged_export_script  # noqa: E402

ROOT = REPO / "output" / "remediation"
OUT_DIR = "final-2026-10-08"
OUT_JSONL, OUT_MD = "OWNER_LIST_FINAL.jsonl", "OWNER_LIST_FINAL.md"
#: The field runs, in the order they ran: a later run's answer closes an earlier run's question.
FIELD_RUNS = ("wd3-pilot", "wd3", "wd4", "wd5-pilot", "wd5", "wd5-reask")
CURATED, RETIRED, SHOWN_CONTRACT = "ancient_nerds", "retired", "shorts-v1"
#: A hero below this is "small", and a row of at least this size can replace it (owner decision
#: D48 over the census of 2026-10-08: "809 heroes under 1600x900; 433 of the 809 have another live
#: row >=1600x900").
HERO_WIDTH, HERO_HEIGHT = 1600, 900
#: An owner-facing artefact: a file (`.jsonl`, `.json`, `.md`) or directory whose name holds this.
OWNER_NAME = re.compile(r"owner|human_only", re.IGNORECASE)
OWNER_SUFFIXES = frozenset({".jsonl", ".json", ".md"})
#: Directories that hold caches, pages or scratch, never a lane's list.
SKIP_PARTS = frozenset({"cache", "pages", "harvest", "wiki_cache"})
#: Owner-facing artefacts that are no list of open sites, each with why this list does not read
#: it (relative to output/remediation). The report names them.
OUT_OF_SCOPE: dict[str, str] = {
    "HUMAN_ONLY.md": (
        "the 2026-09 questions for the owner; answered by HUMAN_ONLY_DECISIONS_2026-09-26.md and "
        "OWNER_DECISIONS_2026-10-08.md - decisions, no open site"
    ),
    "HUMAN_ONLY_DECISIONS_2026-09-26.md": "the owner's answers to HUMAN_ONLY.md - no open site",
    "OWNER_DECISIONS_2026-10-08.md": "the decisions D1-D66 the topics cite - no open site",
    "teaser/runs/owner-d47-2026-10-19": (
        "the 6 cards D47 cleared: each has no card text now and is listed under `card-empty` "
        "from production"
    ),
}


@dataclass(frozen=True)
class LaneList:
    """A lane's own owner list: where it lies, the topic its rows are, and the decision behind it."""

    name: str
    path: str  # relative to output/remediation
    topic: str
    decision: str


LANE_LISTS: tuple[LaneList, ...] = (
    LaneList(
        "identity-retarget",
        f"{OUT_DIR}/identity/retarget/OWNER_LIST.jsonl",
        "identity-not-retargeted",
        "D13",
    ),
    LaneList(
        "identity-scope-window",
        f"{OUT_DIR}/identity/scope-window/OWNER_LIST.jsonl",
        "scope-undecided",
        "D20/D58",
    ),
)


@dataclass(frozen=True)
class Topic:
    """One thing production can say stays empty, and the decision that leaves it so."""

    key: str
    title: str
    decision: str
    test: Callable[[Mapping[str, Any]], str | None]


def _blank(value: Any) -> bool:
    return value is None or not str(value).strip()


def _small(hero: Mapping[str, Any] | None) -> bool:
    """A hero with a stored size below `HERO_WIDTH` x `HERO_HEIGHT`."""
    if not hero or hero["width"] is None or hero["height"] is None:
        return False
    return hero["width"] < HERO_WIDTH or hero["height"] < HERO_HEIGHT


def _hero_small(row: Mapping[str, Any]) -> str | None:
    """D48: a small hero whose site holds another live row of at least the size - the swap the
    owner decides. A small hero without one is counted (`hero_sizes`), not listed."""
    hero = row["hero"]
    if not _small(hero):
        return None
    larger = row["hero_larger"]
    if larger is None:
        return None
    return (
        f"hero {hero['filename']} is {hero['width']}x{hero['height']}; the largest other live row "
        f"is {larger['id']} {larger['filename']} ({larger['width']}x{larger['height']}), one of "
        f"{row['hero_larger_rows']} at least {HERO_WIDTH}x{HERO_HEIGHT}"
    )


def _hero_size_unknown(row: Mapping[str, Any]) -> str | None:
    hero = row["hero"]
    if hero and (hero["width"] is None or hero["height"] is None):
        return f"hero {hero['filename']} has no stored size"
    return None


def _hero_credit(row: Mapping[str, Any]) -> str | None:
    hero = row["hero"]
    if not hero:
        return None
    wanted = credit_columns(hero["license"] or "")
    missing = [c for c in wanted if _blank(hero[c])]
    if missing:
        return f"hero {hero['filename']} ({hero['license'] or 'no licence'}) lacks {', '.join(missing)}"
    return None


def _card_drift(row: Mapping[str, Any]) -> str | None:
    """`card_stats_ext.readback`'s two drift metrics, per site: a filled card id that is not the
    site's `site_external_ids` value."""
    out = []
    if row["card_qid"] is not None and row["card_qid"] != row["qid"]:
        out.append(f"card wikidata_qid {row['card_qid']}, the site's {row['qid']}")
    if row["card_wiki_url"] is not None and row["card_wiki_url"] != _english_url(
        row["enwiki_title"]
    ):
        out.append(f"card best_wiki_url {row['card_wiki_url']}, the site's {row['enwiki_title']!r}")
    return "; ".join(out) or None


def _english_url(title: str | None) -> str | None:
    return None if title is None else "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")


TOPICS: tuple[Topic, ...] = (
    Topic(
        "description-empty",
        "no description",
        "D22",
        lambda r: "the description is empty" if r["no_description"] else None,
    ),
    Topic(
        "card-empty",
        "no card text",
        "D3/D22/D53",
        lambda r: "no card text" if _blank(r["card_description"]) else None,
    ),
    Topic(
        "card-old-kept",
        "an old card the shorts-v1 lane did not replace",
        "D5",
        lambda r: (
            f"card contract {r['card_contract'] or 'none'}"
            if not _blank(r["card_description"]) and r["card_contract"] != SHOWN_CONTRACT
            else None
        ),
    ),
    Topic(
        "image-none",
        "no picture at all",
        "D17",
        lambda r: (
            "no thumbnail and no gallery row"
            if _blank(r["thumbnail_url"]) and r["images"] == 0
            else None
        ),
    ),
    Topic(
        "image-thumbnail-only",
        "a thumbnail without any gallery row",
        "D59",
        lambda r: (
            f"thumbnail {r['thumbnail_url']} only"
            if not _blank(r["thumbnail_url"]) and r["images"] == 0
            else None
        ),
    ),
    Topic(
        "hero-small",
        f"a hero below {HERO_WIDTH}x{HERO_HEIGHT} that a larger live row could replace",
        "D48",
        _hero_small,
    ),
    Topic("hero-size-unknown", "a hero without a stored size", "D48", _hero_size_unknown),
    Topic(
        "hero-credit-missing", "a hero without the credit its licence asks", "D49/D28", _hero_credit
    ),
    Topic(
        "site-type-empty",
        "no site type",
        "O14",
        lambda r: "site_type is empty" if _blank(r["site_type"]) else None,
    ),
    Topic(
        "period-undated",
        "no period (Undated)",
        "D12",
        lambda r: f"period_name {r['period_name']!r}" if r["period_start"] is None else None,
    ),
    Topic(
        "period-rule-made",
        "a period a rule made, found in no source",
        "D12",
        lambda r: (
            f"marker kind {r['period_kind']}" if r["period_kind"] in ("derived", "band") else None
        ),
    ),
    Topic(
        "period-unmarked",
        "a period without a provenance marker",
        "D12",
        lambda r: "no raw_data._period_provenance" if r["period_kind"] is None else None,
    ),
    Topic(
        "point-unsourced",
        "a point no source stands behind (no Short)",
        "D19",
        lambda r: f"point {r['lat']}, {r['lon']}" if r["coord_kind"] == "unsourced" else None,
    ),
    Topic(
        "point-unmarked",
        "a point without a provenance marker",
        "D19",
        lambda r: "no raw_data._coord_provenance" if r["coord_kind"] is None else None,
    ),
    Topic(
        "source-url-empty",
        "no source URL",
        "D10",
        lambda r: "source_url is empty" if _blank(r["source_url"]) else None,
    ),
    Topic(
        "wikidata-id-none",
        "no Wikidata item",
        "D25",
        lambda r: "no site_external_ids wikidata_qid" if not r["has_qid"] else None,
    ),
    Topic(
        "scope-pending",
        "a scope still pending",
        "D20",
        lambda r: "scope_status pending" if r["scope_status"] == "pending" else None,
    ),
    Topic(
        "card-id-drift",
        "a card whose Wikidata id or article link is no longer its site's",
        "D25",
        _card_drift,
    ),
)
TOPIC_OF = {t.key: t for t in TOPICS}
FIELD_TOPIC = {
    field: f"field-{field}" for field in ("coordinates", "period_start", "site_type", "source_url")
}

#: Another live row of the site (`h` is its hero) of at least the size: a row D48 could swap in.
_LARGER = (
    "x.site_id = u.id AND NOT x.is_excluded AND x.id <> h.id AND "
    f"x.width >= {HERO_WIDTH} AND x.height >= {HERO_HEIGHT}"
)
SITES_SQL = (
    "SELECT u.id::text AS site_id, u.name, u.country, u.scope_status, u.site_type, "
    "u.period_start, u.period_name, u.lat::text AS lat, u.lon::text AS lon, u.source_url, "
    "u.thumbnail_url, (u.description IS NULL OR btrim(u.description) = '') AS no_description, "
    "c.card_description, coalesce(u.raw_data -> '_card_provenance' ->> 'contract', '') AS "
    "card_contract, u.raw_data -> '_coord_provenance' ->> 'kind' AS coord_kind, "
    "u.raw_data -> '_period_provenance' ->> 'kind' AS period_kind, "
    "(SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id AND NOT w.is_excluded) AS images, "
    "CASE WHEN h.id IS NULL THEN NULL ELSE json_build_object('id', h.id, 'filename', h.filename, "
    "'width', h.width, 'height', h.height, 'license', h.license, 'author', h.author, "
    "'license_url', h.license_url) END AS hero, "
    "(SELECT json_build_object('id', x.id, 'filename', x.filename, 'width', x.width, 'height', "
    f"x.height) FROM wiki_images x WHERE {_LARGER} ORDER BY x.width::bigint * x.height DESC, x.id "
    "LIMIT 1) AS hero_larger, "
    f"(SELECT count(*) FROM wiki_images x WHERE {_LARGER}) AS hero_larger_rows, "
    "EXISTS (SELECT 1 FROM site_external_ids e WHERE e.site_id = u.id AND "
    "e.kind = 'wikidata_qid') AS has_qid, c.wikidata_qid AS card_qid, c.best_wiki_url AS "
    "card_wiki_url, (SELECT e.value FROM site_external_ids e WHERE e.site_id = u.id AND "
    "e.kind = 'wikidata_qid') AS qid, (SELECT e.value FROM site_external_ids e WHERE "
    "e.site_id = u.id AND e.kind = 'enwiki_title') AS enwiki_title "
    "FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
    "LEFT JOIN LATERAL (SELECT w.* FROM wiki_images w WHERE w.site_id = u.id AND w.is_hero AND "
    "NOT w.is_excluded ORDER BY w.id LIMIT 1) h ON true "
    f"WHERE u.source_id = '{CURATED}' ORDER BY u.id"
)


class OwnerListFinalError(RuntimeError):
    """The list cannot be built as asked (a missing source in `--final`)."""


# ------------------------------------------------------------------------------ production
def production_rows(sites: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row per open topic of every shown curated site. Pure."""
    out: list[dict[str, Any]] = []
    for site in sites:
        if site["scope_status"] == RETIRED:
            continue
        for topic in TOPICS:
            reason = topic.test(site)
            if reason is not None:
                out.append(_row(site, topic.key, "production", "open", reason, topic.decision))
    return out


def _row(
    site: Mapping[str, Any], topic: str, source: str, state: str, reason: str, decision: str
) -> dict[str, Any]:
    return {
        "site_id": str(site["site_id"]),
        "name": site.get("name"),
        "country": site.get("country"),
        "topic": topic,
        "source": source,
        "state": state,
        "reason": str(reason)[: OL.REASON_CHARS],
        "decision": decision,
    }


# ------------------------------------------------------------------------------ the field runs
def _same(field: str, stored: Any, site: Mapping[str, Any], type_merges: Mapping[str, str]) -> bool:
    """Whether production still holds the value a field run classified (`stored` as the run's
    CLASSIFIED.jsonl printed it: a point as `lat, lon`). A site type also counts as held when
    production holds the site_type merge's target of the stored alias (`type_merges`, alias ->
    target): the merge renames the vocabulary and answers no question, so a row it moved from
    `Settlement` to `City/town/settlement` stays open. Any other change of the type (`Settlement`
    to `Urban` included, though both merge into one target) is a later write: superseded."""
    if field == "coordinates":
        if stored is None or site["lat"] is None:
            return stored is None and site["lat"] is None
        lat, lon = (float(part) for part in str(stored).split(","))
        return lat == float(site["lat"]) and lon == float(site["lon"])
    if field == "site_type" and stored in type_merges:
        return site[field] in (stored, type_merges[stored])
    return stored == site[field]


def field_rows(
    runs: Sequence[tuple[str, Mapping[str, Any], set[tuple[str, str]]]],
    sites: Mapping[str, Mapping[str, Any]],
    type_merges: Mapping[str, str],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """The open field rows: per `(site, field)` the row of the **last** run that asked it, kept only
    while the site is shown and holds the value the run classified (a site type up to the merge
    map, `_same`). `runs` is `(name, build result, asked cells)` in the order the runs ran. Pure."""
    latest: dict[tuple[str, str], tuple[str, dict[str, Any] | None]] = {}
    for name, result, asked in runs:
        listed = {(r["site_id"], r["field"]): r for r in result["rows"]}
        for cell in asked:
            latest[cell] = (name, listed.get(cell))
    out: list[dict[str, Any]] = []
    set_aside: Counter[str] = Counter()
    for (site_id, field), (name, row) in sorted(latest.items()):
        if row is None:
            continue
        site = sites.get(site_id)
        if site is None or site["scope_status"] == RETIRED:
            set_aside["retired-or-gone"] += 1
            continue
        if not _same(field, row["stored"], site, type_merges):
            set_aside["superseded"] += 1
            continue
        reason = f"{row['open_because']}: {row['reason']}"
        if field == "site_type" and row["stored"] != site[field]:
            reason = f"(the site_type merge renamed {row['stored']!r} to {site[field]!r}) {reason}"
        out.append(
            _row(site, FIELD_TOPIC[field], f"fields-{name}", row["state"], reason, "D10/D12/D19")
        )
    return out, set_aside


def asked_cells(run: Path) -> set[tuple[str, str]]:
    """Every `(site, field)` the run asked: its rounds and carried cells, or - for a run without
    rounds - its whole classification (`owner_list.asked_by_rounds`)."""
    asked = OL.asked_by_rounds(run)
    if asked is not None:
        return asked
    return {
        (line["site_id"], field)
        for line in OL._rows(run / OL.C.CLASSIFIED_FILE)
        for field in line["asked"]
    }


def build_field_run(root: Path, name: str) -> tuple[dict[str, Any], set[tuple[str, str]]]:
    run = root / "fields" / name
    stage = R.read_rule(run).stage
    return OL.build([run], root / FIELDS_ROOTS[stage]), asked_cells(run)


# ------------------------------------------------------------------------------ the lane lists
def lane_rows(
    lane: LaneList, rows: Iterable[Mapping[str, Any]], sites: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """A lane list's rows that are still open: the site is shown. Pure."""
    out: list[dict[str, Any]] = []
    aside = 0
    for row in rows:
        site = sites.get(str(row["site_id"]))
        if site is None or site["scope_status"] == RETIRED:
            aside += 1
            continue
        state = str(row.get("state") or "listed")
        verdict = row.get("verdict")
        reason = f"{verdict}: {row.get('reason', '')}" if verdict else str(row.get("reason", ""))
        out.append(_row(site, lane.topic, lane.name, state, reason, lane.decision))
    return out, aside


def owner_artefacts(root: Path) -> list[str]:
    """Every owner-facing file or directory under `root` (`OWNER_NAME`), caches left out; a
    matching directory is named once, not descended into."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath).relative_to(root)
        descend = []
        for name in sorted(dirnames):
            if name in SKIP_PARTS:
                continue
            if OWNER_NAME.search(name):
                found.append((here / name).as_posix())
            else:
                descend.append(name)
        dirnames[:] = descend
        found += [
            (here / name).as_posix()
            for name in filenames
            if OWNER_NAME.search(name) and Path(name).suffix in OWNER_SUFFIXES
        ]
    return sorted(found)


def unregistered_lists(root: Path, registered: Iterable[str]) -> list[str]:
    """Every owner-facing artefact under `root` that no source covers and `OUT_OF_SCOPE` does not
    explain - so none is dropped unseen. The field runs' lists are rebuilt from their runs (their
    adversarial lists are in those rows), a registered list's `.md` is its rendering, and the
    builder's own files are its output."""
    known = set(registered) | {f"{OUT_DIR}/{OUT_JSONL}", f"{OUT_DIR}/{OUT_MD}"}
    known |= {k.removesuffix(".jsonl") + ".md" for k in known if k.endswith(".jsonl")}
    found: list[str] = []
    for rel in owner_artefacts(root):
        parts = rel.split("/")
        if rel in known or rel in OUT_OF_SCOPE:
            continue
        if parts[0] == "fields" and len(parts) in (3, 4) and parts[1] in FIELD_RUNS:
            continue  # <run>/OWNER_LIST.{jsonl,md} and <run>/adv/OWNER.jsonl
        found.append(rel)
    return found


def hero_sizes(sites: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """The shown curated sites with a small hero, and how many of them hold a larger live row (the
    `hero-small` topic, D48) or none (nothing to swap: counted, not listed). Pure."""
    small = [s for s in sites if s["scope_status"] != RETIRED and _small(s["hero"])]
    larger = sum(1 for s in small if s["hero_larger"] is not None)
    return {"small": len(small), "with_a_larger_row": larger, "without": len(small) - larger}


# ------------------------------------------------------------------------------ the build
def build(
    *,
    root: Path = ROOT,
    read: Callable[[str], str] = read_production,
    final: bool = False,
    field_run: Callable[[Path, str], tuple[dict[str, Any], set[tuple[str, str]]]] = build_field_run,
) -> dict[str, Any]:
    """Every open row and the report around them, from the files and one read-only export."""
    rows_by_kind, read_at = parse_tagged_export(
        read(tagged_export_script([("site", SITES_SQL)])), ("site",)
    )
    sites = {str(s["site_id"]): s for s in rows_by_kind["site"]}
    missing: list[str] = []
    runs = []
    for name in FIELD_RUNS:
        if not (root / "fields" / name / R.RUN_FILE).exists():
            missing.append(f"fields/{name}")
            continue
        result, asked = field_run(root, name)
        runs.append((name, result, asked))
    type_merges = {alias: m.target for alias, m in STM.load_map().merges.items()}
    rows, set_aside = field_rows(runs, sites, type_merges)
    for lane in LANE_LISTS:
        path = root / lane.path
        if not path.exists():
            missing.append(lane.path)
            continue
        listed = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]
        open_rows, aside = lane_rows(lane, listed, sites)
        rows += open_rows
        set_aside[f"{lane.name}:retired-or-gone"] += aside
    rows += production_rows(sites.values())
    unregistered = unregistered_lists(root, (lane.path for lane in LANE_LISTS))
    # a run's `pending` cell whose value production no longer holds was written by a step the run's
    # files do not show (WD3's 2026-10-04 wave kept no WAVE.json): only an open one is pending
    pending = sum(1 for r in rows if r["state"] == OL.PENDING)
    if final and (missing or unregistered or pending):
        raise OwnerListFinalError(
            f"not final: missing {missing}, unregistered {unregistered}, {pending} pending field "
            "question(s)"
        )
    rows.sort(
        key=lambda r: (r["topic"], str(r["country"]), str(r["name"]), r["site_id"], r["source"])
    )
    return {
        "read_at": read_at,
        "rows": rows,
        "counts": dict(sorted(Counter(r["topic"] for r in rows).items())),
        "sites": len({r["site_id"] for r in rows}),
        "shown_sites": sum(1 for s in sites.values() if s["scope_status"] != RETIRED),
        "set_aside": dict(sorted(set_aside.items())),
        "missing": missing,
        "unregistered": unregistered,
        "out_of_scope": {k: v for k, v in OUT_OF_SCOPE.items() if (root / k).exists()},
        "hero_sizes": hero_sizes(sites.values()),
        "pending": pending,
    }


# ------------------------------------------------------------------------------ the writing
def _cell(text: Any) -> str:
    return str(text if text is not None else "-").replace("|", "/").replace("\n", " ")


def _title(topic: str) -> tuple[str, str]:
    if topic in TOPIC_OF:
        return TOPIC_OF[topic].title, TOPIC_OF[topic].decision
    for lane in LANE_LISTS:
        if lane.topic == topic:
            return f"{lane.name} (lane list)", lane.decision
    field = topic.removeprefix("field-")
    return f"{field}: a field the research could not source (it stays as it is)", "D10/D12/D19"


def render(result: Mapping[str, Any]) -> str:
    out = [
        "# Owner list (final): everything that stays empty, unsourced or open",
        "",
        f"Built {datetime.now(UTC).replace(microsecond=0).isoformat()} by "
        "`scripts/remediation/owner_list_final.py` from the lanes' files and one read-only "
        f"production export ({result['read_at']}). {result['sites']} of {result['shown_sites']} "
        "shown curated sites carry at least one row. A lane row of a retired site, or of a value a "
        "later write replaced, is set aside (counted below, not listed).",
        "",
        "| topic | rows | decision |",
        "|---|---|---|",
    ]
    for topic, n in result["counts"].items():
        title, decision = _title(topic)
        out.append(f"| {title} (`{topic}`) | {n} | {decision} |")
    out += ["", f"Set aside: {result['set_aside'] or 'none'}."]
    sizes = result["hero_sizes"]
    out += [
        "",
        f"**Small heroes (D48).** {sizes['small']} heroes are below {HERO_WIDTH}x{HERO_HEIGHT}. "
        f"`hero-small` lists the {sizes['with_a_larger_row']} whose site holds another live row of "
        "at least that size and names the largest: the swap is the owner's call (the census of "
        f"2026-10-08 counted 433). The other {sizes['without']} have no larger live row, so there "
        "is nothing to swap: they are counted here, not listed.",
    ]
    if result["out_of_scope"]:
        out += ["", "Owner-facing files this list does not read, and why:", ""]
        out += [f"- `{k}`: {v}" for k, v in result["out_of_scope"].items()]
    if result["missing"] or result["unregistered"]:
        out += [
            "",
            "**Not final.** Sources not built yet: "
            + (", ".join(f"`{m}`" for m in result["missing"]) or "none")
            + ". Owner lists no source covers: "
            + (", ".join(f"`{u}`" for u in result["unregistered"]) or "none")
            + ".",
        ]
    if result["pending"]:
        out += [
            "",
            f"**{result['pending']} pending field question(s)** (state `pending`): the list is "
            "final only without them.",
        ]
    for topic in result["counts"]:
        title, decision = _title(topic)
        mine = [r for r in result["rows"] if r["topic"] == topic]
        out += [
            "",
            f"## {title}: {len(mine)} ({decision})",
            "",
            "| site | country | source | state | reason |",
            "|---|---|---|---|---|",
        ]
        out += [
            f"| {_cell(r['name'])} (`{r['site_id']}`) | {_cell(r['country'])} | {r['source']} | "
            f"{r['state']} | {_cell(r['reason'])} |"
            for r in mine
        ]
    return "\n".join(out) + "\n"


def write(result: Mapping[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / OUT_JSONL).write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in result["rows"]),
        encoding="utf-8",
        newline="\n",
    )
    (out / OUT_MD).write_text(render(result), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("build")
    cmd.add_argument("--final", action="store_true", help="refuse while a source is not final")
    args = parser.parse_args(argv)
    try:
        result = build(final=args.final)
    except (OwnerListFinalError, OL.OwnerListError, R.RuleError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    write(result, ROOT / OUT_DIR)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "rows"} | {"rows": len(result["rows"])},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
