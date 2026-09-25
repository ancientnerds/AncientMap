"""E4: flag out-of-scope sites and hide them - the scope lane (`scope_status`, `scope_reason`).

## The decision it carries out

E3 (owner, 2026-09-19): the project covers the Americas through 1500 AD and the rest of the world
through 500 AD, and museums stay if they exhibit ancient material. E4: an out-of-scope site is
flagged AND hidden platform-wide, never deleted. Migration 0020 added `scope_status`
(`in_scope`/`retired`/`pending`) and `scope_reason`; every consumer reads it through
`pipeline/utils/public_sites.not_retired()`. On 2026-09-23 both are NULL on all 5,004 curated rows.

## The four rules (`classify_scope`)

The candidates are the census T11 findings over a fresh read-only export - T11 is imported and run,
never re-typed (`census/tests/t11_scope_window.py`) - plus the duplicate pairs.

* **(a) `T11/out-of-window`**: the current `period_start` lies past the region's cutoff. Retired, with
  T11's own note as the reason - unless `DECISIONS.json` names a sentence of the site's own
  description that dates part of the site inside the window. Then the row is `pending`: the date
  and the dataset disagree, and which one is wrong is a `period_start` question (T11's docstring;
  the remaining map's note on the 11 sites phase 3 moved out of the window).
* **(b) `T11/undecidable-date`**: no date at all. `pending`, unless `DECISIONS.json` quotes the site's
  own description placing it outside the window (retired) - or the row is a Museum kept by the
  E3 museum rule (rule d).
* **(c) duplicates**: two curated rows within 100 m that share one Wikidata item, and whose names are
  *both* names of that item (label, alias or sitelink title in any language, compared after NFKC,
  case-fold and whitespace folding). The survivor is the older row, then the one with more
  content links, more description citations, more images, then the lower id; the other is retired
  with the reason `duplicate_of:<survivor id>`. The owner-case list
  `output/remediation/bcases/DUPLICATES.jsonl` (2026-09-23, `bcases/classify.py`: the same two-names
  test within 2 km, its own survivor rule, each line a loser, its survivor and the evidence) is
  retired the same way. Each listed pair is re-read in the export first - both rows curated, both
  still carrying the one item the line names, still within the list's 2 km - and a pair the lane
  finds itself and the list names too is one retirement with both evidences, never two; a loser
  the two name with different survivors is refused. No duplicate touches a site held for the owner
  (`DUPLICATES_HELD.jsonl`: Banias / Caesarea Philippi, B10), whoever found it.
* **(d) `T11/museum-past-cutoff`** (and an undated Museum row): the `period_start` of a museum is its
  founding year. Plan section 8.2 reviewed all 51 Museum rows: 41 stay, 3 leave. Every such row
  needs a `DECISIONS.json` entry quoting its description: `in_scope` for ancient material, `retired`
  for the three section 8.2 names.

Every quote must appear verbatim in the live description, or the decision is refused. A row whose
`scope_status` is already set is left alone (the lane fills an unassessed column); a site decided
twice in `DECISIONS.json` stops the plan, and a duplicate loser that another rule decides too is
refused (`two-decisions`). Every write carries its premise - the date, point, type, name and
description (as an md5) the decision rests on - so the transaction refuses a site that changed
after the export (guard 5): a reviewed decision quotes the description, and a quote the row no
longer holds is no evidence. What the premise does not hold is a duplicate's ranking (`created_at`
and the link, citation and image counts of both rows): the survivor is not a planned row, so no
per-row guard can condition on it - the counts are the export's, printed in `REVIEW.md`.

`--export` reads production (read-only, one `READ ONLY` transaction) into
`output/remediation/mechanical_scope/export/`; `--collect` fetches the Wikidata names of the items
the pairs share (the project USER_AGENT); `--write` needs neither network nor database and writes
`PLAN.jsonl`, `PLAN.md`, `REVIEW.md` (every site, its rule and its evidence - read it before
applying), `SKIPPED.jsonl`, `ROLLBACK.sql`. `apply.py --lane scope-e4` renders and runs it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from bcases.classify import DUP_MAX_M  # noqa: E402

from mechanical.lane import SCOPE, sql_literal  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    UUID_RE,
    WIKIDATA_API,
    Plan,
    PlanError,
    Verdict,
    _now,
    get_json,
    parse_tagged_export,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
    write_tagged_export,
)
from pipeline.utils.geo import haversine_distance  # noqa: E402
from pipeline.utils.public_sites import RETIRED, SCOPE_STATUSES  # noqa: E402

log = logging.getLogger("mechanical.scope")

LANE = SCOPE
DEFAULT_OUT = REPO / "output" / "remediation" / LANE.out_dir_name
DEFAULT_CACHE = REPO / "output" / "remediation" / "cache"
#: The owner-case duplicate list and the pairs it holds back for the owner (`bcases/classify.py`).
BCASES = REPO / "output" / "remediation" / "bcases"
DUPLICATES_LIST = BCASES / "DUPLICATES.jsonl"
DUPLICATES_HELD = BCASES / "DUPLICATES_HELD.jsonl"
LISTED_URL = "output/remediation/bcases/DUPLICATES.jsonl"
DUPLICATE_METRES = 100
DUPLICATE_PREFIX = "duplicate_of:"
PENDING, IN_SCOPE = "pending", "in_scope"

#: What T11 names each finding kind, and the rule that decides it here.
OUT_OF_WINDOW = "T11/out-of-window"
UNDATED = "T11/undecidable-date"
MUSEUM = "T11/museum-past-cutoff"
RULE_OF = {OUT_OF_WINDOW: "a", UNDATED: "b", MUSEUM: "d"}

# ------------------------------------------------------------------------------- the export
EXPORT_SITES_SQL = (
    "SELECT u.id::text AS id, u.name, u.source_id, u.site_type, u.country, u.lat, u.lon, "
    "u.period_start, u.period_end, u.period_name, u.description, u.source_url, "
    "u.created_at::text AS created_at, u.scope_status, u.scope_reason, "
    f"{LANE.premise_sql} AS premise, "
    "(SELECT count(*) FROM site_content_links s WHERE s.site_id = u.id) AS links, "
    "(SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS images, "
    "jsonb_array_length(coalesce(u.raw_data->'description_citations', '[]'::jsonb)) AS citations, "
    "(SELECT json_object_agg(e.kind, e.value) FROM site_external_ids e WHERE e.site_id = u.id) AS ext "
    f"FROM unified_sites u WHERE u.source_id = {sql_literal(CURATED_SOURCE)} ORDER BY u.id"
)

#: Curated pairs within 100 m that name the same Wikidata item - the duplicate candidates.
EXPORT_PAIRS_SQL = (
    "SELECT a.id::text AS a, b.id::text AS b, ea.value AS qid, "
    "ST_Distance(a.geom::geography, b.geom::geography) AS metres "
    "FROM unified_sites a "
    "JOIN site_external_ids ea ON ea.site_id = a.id AND ea.kind = 'wikidata_qid' "
    "JOIN site_external_ids eb ON eb.kind = 'wikidata_qid' AND eb.value = ea.value "
    "AND eb.site_id <> a.id "
    "JOIN unified_sites b ON b.id = eb.site_id "
    f"WHERE a.source_id = {sql_literal(CURATED_SOURCE)} AND b.source_id = {sql_literal(CURATED_SOURCE)} "
    f"AND a.id < b.id AND ST_DWithin(a.geom::geography, b.geom::geography, {DUPLICATE_METRES}) "
    "ORDER BY 1, 2"
)

EXPORT_JOURNAL_SQL = (
    "SELECT l.id, l.row_pk, l.column_name, l.old_value, l.new_value, l.run_stamp "
    "FROM remediation_change_log l WHERE l.table_name = 'unified_sites' "
    "AND l.column_name IN ('period_start', 'scope_status') ORDER BY l.id"
)


EXPORT_PARTS = (
    ("site", EXPORT_SITES_SQL),
    ("pair", EXPORT_PAIRS_SQL),
    ("journal", EXPORT_JOURNAL_SQL),
)


def export_script() -> str:
    """The sites, the pairs and the journal from one read-only snapshot, tagged by kind."""
    return tagged_export_script(EXPORT_PARTS)


@dataclass(frozen=True)
class Export:
    sites: tuple[dict[str, Any], ...]
    pairs: tuple[dict[str, Any], ...]
    journal: tuple[dict[str, Any], ...]
    exported_at: str


def parse_export(text: str) -> Export:
    """The export's tagged lines (`plan.parse_tagged_export` refuses a line of another kind and an
    export without its one snapshot line)."""
    rows, exported_at = parse_tagged_export(text, (kind for kind, _sql in EXPORT_PARTS))
    if not rows["site"]:
        raise PlanError("the export holds no curated site")
    return Export(
        sites=tuple(rows["site"]),
        pairs=tuple(rows["pair"]),
        journal=tuple(rows["journal"]),
        exported_at=exported_at,
    )


def write_export(directory: Path) -> Path:
    return write_tagged_export(export_script(), directory / "export.jsonl")


# ------------------------------------------------------------------------ the Wikidata names
def fold(name: str) -> str:
    """A name as the duplicate test compares it: NFKC, case-folded, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def wikidata_names(entity: Mapping[str, Any]) -> frozenset[str]:
    """Every name Wikidata gives an item: labels, aliases and sitelink titles, all languages."""
    names = {fold(v["value"]) for v in entity.get("labels", {}).values()}
    names |= {fold(v["value"]) for vs in entity.get("aliases", {}).values() for v in vs}
    names |= {fold(v["title"]) for v in entity.get("sitelinks", {}).values()}
    return frozenset(names)


def collect_names(pairs: Iterable[Mapping[str, Any]], path: Path) -> int:
    """Fetch the shared items' names (read-only, the project USER_AGENT) and keep them as fetched."""
    qids = sorted({str(p["qid"]) for p in pairs})
    entities: dict[str, Any] = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i : i + 50]
        data = get_json(
            WIKIDATA_API,
            {
                "action": "wbgetentities",
                "ids": "|".join(chunk),
                "props": "labels|aliases|sitelinks",
                "format": "json",
            },
        )
        entities.update(data["entities"])
    missing = sorted(set(qids) - set(entities))
    if missing:
        raise PlanError(f"Wikidata answered no entity for {missing}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": _now(), "entities": entities}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    return len(entities)


# ------------------------------------------------------------------------------ T11, imported
def t11_findings(sites: Sequence[Mapping[str, Any]], cache: Path) -> dict[str, Any]:
    """T11 over the exported rows: its findings by site id (the census module, run as it is).

    T11 needs the geo stack (geopandas) and Natural Earth in `cache` - the census's own cache.
    """
    from census.tests import t11_scope_window as t11

    return index_findings(
        t11.run(SimpleNamespace(cache=Path(cache), sites=[dict(s) for s in sites]))
    )


def index_findings(findings: Iterable[Any]) -> dict[str, Any]:
    """T11's findings by site id - one per site, or the site would get two decisions."""
    by_site: dict[str, Any] = {}
    for finding in findings:
        if finding.site_id in by_site:
            raise PlanError(f"T11 reported {finding.site_id} twice")
        by_site[finding.site_id] = finding
    return by_site


# ------------------------------------------------------------------------------ the decisions
@dataclass(frozen=True)
class Decision:
    site_id: str
    name: str
    rule: str
    status: str
    quote: str
    note: str


def load_decisions(path: Path) -> dict[str, Decision]:
    """`DECISIONS.json`: the reviewed per-site entries (see its `_about`)."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the reviewed decisions are part of the plan")
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, Decision] = {}
    for entry in raw["decisions"]:
        decision = Decision(**{k: str(entry[k]) for k in Decision.__dataclass_fields__})
        if not UUID_RE.match(decision.site_id):
            raise PlanError(f"{decision.site_id!r} is not a UUID")
        if decision.site_id in out:
            raise PlanError(f"{decision.site_id} is decided twice in {path.name}")
        if decision.status not in SCOPE_STATUSES or decision.rule not in ("a", "b", "d"):
            raise PlanError(f"{decision.site_id}: rule {decision.rule!r} / {decision.status!r}")
        if not decision.quote or not decision.note:
            raise PlanError(f"{decision.site_id}: a decision needs a quote and a note")
        out[decision.site_id] = decision
    return out


# ------------------------------------------------------------------------------ duplicates
def survivor_rank(site: Mapping[str, Any]) -> tuple[Any, ...]:
    """The survivor rule, as a sort key: older, then more content links, citations, images."""
    return (
        str(site["created_at"]),
        -int(site["links"]),
        -int(site["citations"]),
        -int(site["images"]),
        str(site["id"]),
    )


@dataclass(frozen=True)
class Duplicate:
    """A loser and its survivor. `found`: this lane's own 100 m rule found the pair; `listed`: the
    evidence of its `DUPLICATES.jsonl` line, when the owner-case list names it."""

    loser: str
    survivor: str
    qid: str
    metres: float
    names: tuple[str, str]
    found: bool = True
    listed: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ListedDuplicate:
    """One line of `DUPLICATES.jsonl`: `loser_id`, `survivor_id`, `evidence`."""

    loser: str
    survivor: str
    evidence: tuple[dict[str, Any], ...]


def load_listed_duplicates(path: Path) -> list[ListedDuplicate]:
    """The owner-case duplicate list, refused unless every line is a loser, its survivor and the
    evidence, and no loser is listed twice."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the owner-case duplicate list is part of the plan")
    out: list[ListedDuplicate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        listed = ListedDuplicate(
            loser=str(raw["loser_id"]),
            survivor=str(raw["survivor_id"]),
            evidence=tuple(dict(e) for e in raw["evidence"]),
        )
        for sid in (listed.loser, listed.survivor):
            if not UUID_RE.match(sid):
                raise PlanError(f"{path.name}: {sid!r} is not a UUID")
        if listed.loser == listed.survivor or not listed.evidence:
            raise PlanError(
                f"{path.name}: {listed.loser} needs another row as survivor and evidence"
            )
        out.append(listed)
    losers = Counter(d.loser for d in out)
    twice = sorted(sid for sid, n in losers.items() if n > 1)
    if twice:
        raise PlanError(f"{path.name} lists {twice} as a loser more than once")
    return out


def load_held_sites(path: Path) -> frozenset[str]:
    """Every site of a duplicate group held for the owner (`DUPLICATES_HELD.jsonl`)."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the pairs held for the owner are part of the plan")
    held: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        for sid in json.loads(line)["site_ids"]:
            if not UUID_RE.match(str(sid)):
                raise PlanError(f"{path.name}: {sid!r} is not a UUID")
            held.add(str(sid))
    return frozenset(held)


def find_duplicates(
    export: Export, entities: Mapping[str, Any]
) -> tuple[list[Duplicate], list[dict[str, Any]]]:
    """True duplicates among the pairs, and the pairs that are not (with the reason)."""
    by_id = {s["id"]: s for s in export.sites}
    dups: list[Duplicate] = []
    others: list[dict[str, Any]] = []
    for pair in export.pairs:
        a, b = by_id[pair["a"]], by_id[pair["b"]]
        entity = entities.get(pair["qid"])
        if entity is None:
            raise PlanError(f"{pair['qid']} was not collected - run --collect")
        names = wikidata_names(entity)
        known = [fold(a["name"]) in names, fold(b["name"]) in names]
        if float(pair["metres"]) > DUPLICATE_METRES or not all(known):
            others.append({**pair, "names_known": known, "a_name": a["name"], "b_name": b["name"]})
            continue
        survivor, loser = sorted((a, b), key=survivor_rank)
        dups.append(
            Duplicate(
                loser=loser["id"],
                survivor=survivor["id"],
                qid=str(pair["qid"]),
                metres=float(pair["metres"]),
                names=(survivor["name"], loser["name"]),
            )
        )
    return dups, others


Refusal = tuple[Mapping[str, Any], str, str]


def _item_of(site: Mapping[str, Any]) -> str | None:
    """The site's Wikidata item as the export read it from `site_external_ids`."""
    ext = site["ext"]
    return None if ext is None else ext.get("wikidata_qid")


def check_listed(
    export: Export, listed: Sequence[ListedDuplicate]
) -> tuple[list[Duplicate], list[Refusal]]:
    """The listed pairs that still hold in the export, and the ones that no longer do.

    A line is a claim about the rows as `bcases` read them: both carry one item, within 2 km. The
    coordinate and item waves of 2026-09-23 wrote after that read, so each claim is re-read here:
    the item both rows carry today must be the one the line names, and the rows must still lie
    within the list's own 2 km (`bcases.classify.DUP_MAX_M`).
    """
    by_id = {s["id"]: s for s in export.sites}
    dups: list[Duplicate] = []
    refused: list[Refusal] = []
    for line in listed:
        loser, survivor = by_id.get(line.loser), by_id.get(line.survivor)
        if loser is None or survivor is None:
            missing = line.loser if loser is None else line.survivor
            raise PlanError(f"DUPLICATES.jsonl names {missing}, which is not a curated site")
        qid = _item_of(loser)
        claim = str(line.evidence[0].get("quote", ""))
        if qid is None or _item_of(survivor) != qid or f"both rows carry {qid};" not in claim:
            refused.append(
                (
                    loser,
                    "listed-item-moved",
                    f"the rows carry {qid} and {_item_of(survivor)} today; the list says {claim!r}",
                )
            )
            continue
        metres = 1000.0 * haversine_distance(
            float(loser["lat"]), float(loser["lon"]), float(survivor["lat"]), float(survivor["lon"])
        )
        if metres > DUP_MAX_M:
            refused.append(
                (
                    loser,
                    "listed-pair-too-far",
                    f"{metres:.1f} m from its survivor today, past the list's {DUP_MAX_M:.0f} m",
                )
            )
            continue
        dups.append(
            Duplicate(
                loser=line.loser,
                survivor=line.survivor,
                qid=qid,
                metres=metres,
                names=(str(survivor["name"]), str(loser["name"])),
                found=False,
                listed=line.evidence,
            )
        )
    return dups, refused


def resolve_duplicates(
    export: Export,
    found: Sequence[Duplicate],
    listed: Sequence[Duplicate],
    held: frozenset[str],
) -> tuple[list[Duplicate], list[Refusal]]:
    """The lane's own duplicates and the listed ones as one set, one retirement per loser.

    A loser both name with the same survivor is one duplicate carrying both evidences; with two
    different survivors it is refused - which row stays is then a question, not a rule. The same
    holds for a loser this lane's own rule finds with two survivors (a triangle of pairs): refused,
    never decided by whichever pair came last (audit 2026-09-25 M8). A pair touching a site held
    for the owner is refused whoever found it.
    """
    by_id = {s["id"]: s for s in export.sites}
    by_loser: dict[str, Duplicate] = {}
    refused: list[Refusal] = []
    disputed: set[str] = set()
    for dup in found:
        own = by_loser.get(dup.loser)
        if own is None:
            by_loser[dup.loser] = dup
        elif dup.loser not in disputed:
            disputed.add(dup.loser)
            refused.append(
                (
                    by_id[dup.loser],
                    "survivors-disagree",
                    f"this lane's rule finds it beside {own.survivor} and {dup.survivor}",
                )
            )
    for dup in listed:
        if dup.loser in disputed:
            continue
        own = by_loser.get(dup.loser)
        if own is None:
            by_loser[dup.loser] = dup
        elif own.survivor == dup.survivor:
            by_loser[dup.loser] = replace(own, listed=dup.listed)
        else:
            disputed.add(dup.loser)
            refused.append(
                (
                    by_id[dup.loser],
                    "survivors-disagree",
                    f"this lane's rule keeps {own.survivor}, DUPLICATES.jsonl keeps {dup.survivor}",
                )
            )
    out: list[Duplicate] = []
    for loser in sorted(set(by_loser) - disputed):
        dup = by_loser[loser]
        if {dup.loser, dup.survivor} & held:
            refused.append(
                (
                    by_id[dup.loser],
                    "held-for-the-owner",
                    f"DUPLICATES_HELD.jsonl holds this pair for the owner (survivor {dup.survivor})",
                )
            )
            continue
        out.append(dup)
    return out, refused


# ------------------------------------------------------------------------------ the decision
@dataclass(frozen=True)
class SiteDecision:
    """One site's scope decision - the two cells it becomes, and the evidence the review reads."""

    site: Mapping[str, Any]
    rule: str
    status: str
    reason: str
    evidence: tuple[dict[str, Any], ...]
    finding: str


@dataclass(frozen=True)
class ScopePlan:
    plan: Plan
    decisions: tuple[SiteDecision, ...]
    refused: tuple[tuple[Mapping[str, Any], str, str], ...]
    others: tuple[dict[str, Any], ...]
    counters: Mapping[str, int] = field(default_factory=dict)


def _quote_evidence(site: Mapping[str, Any], decision: Decision) -> dict[str, Any]:
    return {
        "source": "unified_sites.description",
        "url": str(site.get("source_url") or "unified_sites.description"),
        "quote": decision.quote,
    }


def _finding_evidence(finding: Any) -> list[dict[str, Any]]:
    return [
        {"source": e.source, "url": e.url or e.source, "quote": e.quote} for e in finding.evidence
    ]


def classify_scope(
    export: Export,
    findings: Mapping[str, Any],
    decisions: Mapping[str, Decision],
    duplicates: Sequence[Duplicate],
) -> tuple[list[SiteDecision], list[tuple[Mapping[str, Any], str, str]]]:
    """Every candidate, decided: `(decisions, refused)` - each refusal with its reason."""
    by_id = {s["id"]: s for s in export.sites}
    period_writes: dict[str, list[Mapping[str, Any]]] = {}
    for entry in export.journal:
        if entry["column_name"] == "period_start":
            period_writes.setdefault(entry["row_pk"], []).append(entry)
    out: list[SiteDecision] = []
    refused: list[tuple[Mapping[str, Any], str, str]] = []
    unused = set(decisions)
    retired_survivors = {d.survivor for d in duplicates}

    def journal_evidence(site_id: str) -> list[dict[str, Any]]:
        return [
            {
                "source": f"remediation_change_log:{j['id']}",
                "url": "remediation_change_log",
                "quote": f"{j['run_stamp']}: period_start {j['old_value']} -> {j['new_value']}",
            }
            for j in period_writes.get(site_id, ())
        ]

    for site_id, finding in sorted(findings.items()):
        site = by_id[site_id]
        kind = finding.test_id
        decision = decisions.get(site_id)
        unused.discard(site_id)
        rule = RULE_OF.get(kind)
        if rule is None:
            refused.append((site, "t11-kind-not-decided-here", f"{kind}: {finding.note}"))
            continue
        base = [*_finding_evidence(finding), *journal_evidence(site_id)]
        if decision is not None:
            if decision.name != site["name"]:
                refused.append(
                    (site, "decision-names-another-site", f"the decision names {decision.name!r}")
                )
                continue
            if decision.quote not in (site["description"] or ""):
                refused.append(
                    (
                        site,
                        "quote-not-in-description",
                        f"{decision.quote!r} is not in the description",
                    )
                )
                continue
        if kind == OUT_OF_WINDOW:
            if decision is None:
                # T11's own words, up to where its note turns to E4 and the second geography
                reason = "E3: " + finding.note.split(", and E4 says", 1)[0]
                out.append(SiteDecision(site, "a", RETIRED, reason, tuple(base), kind))
            elif decision.rule == "a" and decision.status == PENDING:
                out.append(
                    SiteDecision(
                        site,
                        "a",
                        PENDING,
                        f"E3: period_start {site['period_start']} is past the cutoff, but the site's "
                        f"own description dates part of it inside the window: {decision.note}",
                        (_quote_evidence(site, decision), *base),
                        kind,
                    )
                )
            else:
                refused.append(
                    (
                        site,
                        "decision-not-allowed",
                        f"rule (a) allows only pending, not {decision.status}",
                    )
                )
            continue
        if kind == MUSEUM:
            if decision is None or decision.rule != "d" or decision.status == PENDING:
                refused.append(
                    (
                        site,
                        "museum-needs-a-decision",
                        "plan section 8.2: every Museum row past the cutoff is decided by hand",
                    )
                )
                continue
            out.append(
                SiteDecision(
                    site,
                    "d",
                    decision.status,
                    f"E3 museum rule (plan section 8.2): {decision.note}",
                    (_quote_evidence(site, decision), *base),
                    kind,
                )
            )
            continue
        # UNDATED
        if decision is None and "museum" in str(site["site_type"]).casefold():
            # rule (d): every Museum row is decided by hand, the undated ones too (audit m11)
            refused.append(
                (
                    site,
                    "museum-needs-a-decision",
                    "plan section 8.2: an undated Museum row is decided by hand",
                )
            )
        elif decision is None:
            out.append(
                SiteDecision(
                    site,
                    "b",
                    PENDING,
                    "E3: no date, and no source of the row places it outside the window",
                    tuple(base),
                    kind,
                )
            )
        elif decision.rule == "b" and decision.status in (RETIRED, PENDING):
            words = (
                "its own source places it outside the window"
                if decision.status == RETIRED
                else "no source of the row places it outside the window"
            )
            out.append(
                SiteDecision(
                    site,
                    "b",
                    decision.status,
                    f"E3: no date, and {words}: {decision.note}",
                    (_quote_evidence(site, decision), *base),
                    kind,
                )
            )
        elif (
            decision.rule == "d"
            and decision.status == IN_SCOPE
            and "museum" in str(site["site_type"]).casefold()
        ):
            out.append(
                SiteDecision(
                    site,
                    "d",
                    IN_SCOPE,
                    f"E3 museum rule (plan section 8.2): {decision.note}",
                    (_quote_evidence(site, decision), *base),
                    kind,
                )
            )
        else:
            refused.append(
                (
                    site,
                    "decision-not-allowed",
                    f"an undated row cannot be {decision.status} by rule {decision.rule}",
                )
            )

    decided = {d.site["id"] for d in out}
    for dup in duplicates:
        loser, survivor = by_id[dup.loser], by_id[dup.survivor]
        if dup.loser in decided or dup.loser in retired_survivors - {dup.survivor}:
            refused.append(
                (loser, "two-decisions", "the duplicate loser is decided by another rule too")
            )
            continue
        survivor_retired = survivor["scope_status"] == RETIRED or any(
            d.site["id"] == dup.survivor and d.status == RETIRED for d in out
        )
        if survivor_retired:
            refused.append(
                (loser, "survivor-retired", f"the survivor {dup.survivor} is or would be retired")
            )
            continue
        evidence: list[dict[str, Any]] = []
        if dup.found:
            evidence += [
                {
                    "source": f"wikidata:{dup.qid}",
                    "url": f"https://www.wikidata.org/wiki/{dup.qid}",
                    "quote": f"both {dup.names[0]!r} and {dup.names[1]!r} are names of {dup.qid}, "
                    f"and the two rows are {dup.metres:.1f} m apart",
                },
                {
                    "source": "survivor rule",
                    "url": "scripts/remediation/mechanical/scope.py:survivor_rank",
                    "quote": "older row, then more content links, description citations, images: "
                    f"survivor {survivor['name']} ({survivor['links']} links, "
                    f"{survivor['citations']} citations, {survivor['images']} images) over "
                    f"{loser['name']} ({loser['links']} links, {loser['citations']} citations, "
                    f"{loser['images']} images)",
                },
            ]
        if dup.listed:
            evidence.append(
                {
                    "source": "bcases:DUPLICATES.jsonl",
                    "url": LISTED_URL,
                    "quote": f"listed for the scope lane; re-read in the export: both rows carry "
                    f"{dup.qid}, {dup.metres:.1f} m apart",
                }
            )
            evidence += [{**e, "url": e.get("url") or LISTED_URL} for e in dup.listed]
        out.append(
            SiteDecision(
                loser,
                "c",
                RETIRED,
                f"{DUPLICATE_PREFIX}{dup.survivor}",
                tuple(evidence),
                "duplicate",
            )
        )
        decided.add(dup.loser)
    for site_id in sorted(unused):
        site = by_id.get(site_id)
        if site is None:
            raise PlanError(f"DECISIONS.json names {site_id}, which is not a curated site")
        refused.append((site, "decision-without-finding", "no T11 finding for this site any more"))
    already = [d for d in out if d.site["scope_status"] is not None]
    for d in already:
        refused.append((d.site, "already-assessed", f"scope_status is {d.site['scope_status']!r}"))
    out = [d for d in out if d.site["scope_status"] is None]
    return out, refused


def to_verdicts(decisions: Sequence[SiteDecision]) -> list[Verdict]:
    """Two cells per site: the status and its reason, filled from NULL in one transaction."""
    cells: list[Verdict] = []
    for d in sorted(decisions, key=lambda d: d.site["id"]):
        site = d.site
        for column, value in (("scope_status", d.status), ("scope_reason", d.reason)):
            cells.append(
                Verdict(
                    site_id=site["id"],
                    site_name=str(site["name"]),
                    ok=True,
                    old_value=site[column],
                    new_value=value,
                    rule=f"e4-rule-{d.rule}",
                    reason="",
                    note=f"{column} NULL -> {value!r} ({d.finding})",
                    phase3=False,
                    finding_test_id=d.finding,
                    evidence=d.evidence,
                    premise=str(site["premise"]),
                    column=column,
                )
            )
    return cells


def build_scope_plan(
    export: Export,
    findings: Mapping[str, Any],
    decisions: Mapping[str, Decision],
    entities: Mapping[str, Any],
    *,
    listed: Sequence[ListedDuplicate],
    held: frozenset[str],
    built_at: str,
) -> ScopePlan:
    """A pure function of its inputs: no network, no database, no clock of its own.

    `listed` is `DUPLICATES.jsonl`, `held` every site of `DUPLICATES_HELD.jsonl`.
    """
    found, others = find_duplicates(export, entities)
    still_listed, gone = check_listed(export, listed)
    duplicates, disputed = resolve_duplicates(export, found, still_listed, held)
    decided, refused = classify_scope(export, findings, decisions, duplicates)
    refused = [*gone, *disputed, *refused]
    skipped = tuple(
        Verdict(
            site_id=site["id"],
            site_name=str(site["name"]),
            ok=False,
            old_value=site["scope_status"],
            new_value=None,
            rule="",
            reason=reason,
            note=note,
            phase3=False,
            finding_test_id="scope",
            column="scope_status",
        )
        for site, reason, note in refused
    )
    status_count = Counter((d.rule, d.status) for d in decided)
    counters = {
        "t11_findings": len(findings),
        "duplicate_pairs_within_100m_sharing_an_item": len(export.pairs),
        "duplicate_pairs_both_names_known": len(found),
        "duplicates_listed": len(listed),
        "duplicates_listed_still_holding": len(still_listed),
        "duplicates_found_and_listed": sum(1 for d in duplicates if d.found and d.listed),
        "duplicates": len(duplicates),
        "sites": len(decided),
        "cells": 2 * len(decided),
        "refused": len(refused),
        **{f"rule_{rule}:{status}": n for (rule, status), n in sorted(status_count.items())},
        **{f"status:{s}": sum(1 for d in decided if d.status == s) for s in SCOPE_STATUSES},
    }
    plan = Plan(
        changes=tuple(to_verdicts(decided)),
        skipped=skipped,
        built_at=built_at,
        counters=counters,
        lane=LANE,
    )
    return ScopePlan(
        plan=plan,
        decisions=tuple(decided),
        refused=tuple(refused),
        others=tuple(others),
        counters=counters,
    )


# ------------------------------------------------------------------------------ the output
_RULE_TITLES = {
    "a": "(a) outside the E3 window by the current period_start",
    "b": "(b) no date",
    "c": "(c) true duplicates",
    "d": "(d) Museum rows (plan section 8.2)",
}


def write_review_md(result: ScopePlan, export: Export, path: Path) -> None:
    """Every site, its rule, its decision and the evidence it rests on - for the reviewer."""
    add = (lines := []).append
    add("# E4 scope decisions - per-site review")
    add("")
    add(
        f"Built {result.plan.built_at} from the production export of {export.exported_at}. "
        "Read this before `apply.py --lane scope-e4 --apply`: every row below becomes two journalled "
        "cells (`scope_status`, `scope_reason`). `retired` hides the site everywhere a visitor, a "
        "crawler or a card draw reaches it; `pending` keeps it shown and flags it; `in_scope` "
        "records the decision to keep it. T11 ran over the live export, not the 2026-09-20 "
        "snapshot its evidence lines are labelled with (`snapshot:unified_sites...` is T11's "
        "wording for the rows it was given)."
    )
    add("")
    add(
        "What this lane does not do: it moves nothing. A retired duplicate keeps its images and "
        "content links; where the survivor has fewer (the counts are on each line below), moving "
        "them is a follow-up before the survivor's page is relied on. A `pending` row stays shown "
        "until its date or scope is settled - the evidence says what to settle."
    )
    add("")
    for rule in ("a", "b", "c", "d"):
        rows = sorted(
            (d for d in result.decisions if d.rule == rule),
            key=lambda d: (d.status, d.site["name"]),
        )
        add(f"## {_RULE_TITLES[rule]} - {len(rows)} site(s)")
        add("")
        for status in ("retired", "pending", "in_scope"):
            group = [d for d in rows if d.status == status]
            if not group:
                continue
            add(f"### {status} ({len(group)})")
            add("")
            for d in group:
                s = d.site
                add(
                    f"* **{s['name']}** (`{s['id']}`) - {s['country']}, {s['site_type']}, "
                    f"period_start {s['period_start']}, {s['links']} link(s), {s['images']} image(s)"
                )
                add(f"  * reason: {d.reason}")
                for e in d.evidence:
                    add(f"  * {e['source']}: {e['quote']}")
            add("")
    if result.refused:
        add(f"## Refused ({len(result.refused)})")
        add("")
        for site, reason, note in result.refused:
            add(f"* {site['name']} (`{site['id']}`): `{reason}` - {note}")
        add("")
    add(
        f"## Pairs within {DUPLICATE_METRES} m that share a Wikidata item but are not duplicates ({len(result.others)})"
    )
    add("")
    add(
        "At least one of the two names is not a name of the shared item: a sub-site, a part-of pair "
        "or a wrong anchor - never retired here."
    )
    add("")
    for p in sorted(result.others, key=lambda p: (p["qid"], p["a_name"])):
        add(
            f"* {p['qid']}: {p['a_name']} / {p['b_name']} ({float(p['metres']):.1f} m; names known: "
            f"{p['names_known'][0]}/{p['names_known'][1]})"
        )
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_plan_md(result: ScopePlan, export: Export, path: Path) -> None:
    c = result.counters
    add = (lines := []).append
    add("# E4 scope lane - plan")
    add("")
    add(
        f"Built {result.plan.built_at} by `scripts/remediation/mechanical/scope.py` from the production "
        f"export of {export.exported_at}. Lane `{LANE.name}`: run stamp `{LANE.run_stamp}`, journal "
        f"test id `{LANE.test_id}`, change keys `{LANE.key_prefix}:<site_id>:<column>`, premise "
        f"`{LANE.premise_sql}`."
    )
    add("")
    add(
        f"**{c['sites']} site(s), {c['cells']} cell(s): {c['status:retired']} retired, "
        f"{c['status:pending']} pending, {c['status:in_scope']} in_scope; {c['refused']} refused.** "
        f"T11 found {c['t11_findings']} site(s); {c['duplicate_pairs_within_100m_sharing_an_item']} "
        f"curated pair(s) within {DUPLICATE_METRES} m share a Wikidata item, "
        f"{c['duplicate_pairs_both_names_known']} of them under two of its names. "
        f"`{LISTED_URL}` lists {c['duplicates_listed']} loser(s), "
        f"{c['duplicates_listed_still_holding']} of them still holding in the export, "
        f"{c['duplicates_found_and_listed']} also found by this lane's own rule: "
        f"{c['duplicates']} duplicate(s) in all, each loser counted once."
    )
    add("")
    add("| rule | status | sites |")
    add("|---|---|---|")
    for key, n in sorted(c.items()):
        if key.startswith("rule_"):
            rule, status = key[5:].split(":")
            add(f"| {_RULE_TITLES[rule]} | {status} | {n} |")
    add("")
    add(
        "The per-site decisions and their evidence are in `REVIEW.md`; the hand-reviewed entries in"
    )
    add("`DECISIONS.json`. Reproduce:")
    add("")
    add("```bash")
    add("./.venv/Scripts/python.exe scripts/remediation/mechanical/scope.py --export --collect")
    add("./.venv/Scripts/python.exe scripts/remediation/mechanical/scope.py --write")
    add("./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane scope-e4 --emit")
    add("```")
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the E4 scope decisions (mechanical lane)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--cache", type=Path, default=DEFAULT_CACHE, help="the census cache (Natural Earth)"
    )
    ap.add_argument(
        "--export", action="store_true", help="read production (read-only) into export/"
    )
    ap.add_argument("--collect", action="store_true", help="fetch the shared items' Wikidata names")
    ap.add_argument(
        "--write", action="store_true", help="plan from export/ (no network, no database)"
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not (args.export or args.collect or args.write):
        ap.print_help()
        return 0
    export_dir = args.out / "export"
    try:
        if args.export:
            log.info("export written: %s", write_export(export_dir))
        export = parse_export((export_dir / "export.jsonl").read_text(encoding="utf-8"))
        if args.collect:
            log.info(
                "%d entities collected",
                collect_names(export.pairs, export_dir / "wikidata_names.json"),
            )
        if args.write:
            names_path = export_dir / "wikidata_names.json"
            if not names_path.exists():
                raise PlanError(f"{names_path} is missing - run --collect")
            entities = json.loads(names_path.read_text(encoding="utf-8"))["entities"]
            result = build_scope_plan(
                export,
                t11_findings(export.sites, args.cache),
                load_decisions(args.out / "DECISIONS.json"),
                entities,
                listed=load_listed_duplicates(DUPLICATES_LIST),
                held=load_held_sites(DUPLICATES_HELD),
                built_at=_now(),
            )
            write_plan_jsonl(result.plan, args.out / "PLAN.jsonl")
            write_skipped_jsonl(result.plan, args.out / "SKIPPED.jsonl")
            write_plan_md(result, export, args.out / "PLAN.md")
            write_review_md(result, export, args.out / "REVIEW.md")
            write_rollback_sql(
                result.plan, args.out / "ROLLBACK.sql", plan_path=args.out / "PLAN.jsonl"
            )
            print(json.dumps(dict(result.counters), indent=1, sort_keys=True))
    except PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
