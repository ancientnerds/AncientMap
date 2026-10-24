"""D57 step 1: the candidate list - which sites the insert lane may create, and what is known of each.

**Where the list comes from.** The SEO session's demand audit of 2026-10-08 ranked every place our
records name by its Wikipedia demand and hand-reviewed the ones without a curated page
(`output/seo-audit-2026-10-08/scratch/demand/agg_inscope_candidates.csv` in the main checkout, 54
rows): 38 carry `manual_verdict = in`, 16 `zweifelhaft` (doubtful). D57 takes the 38 and adds Chaco
Canyon (`ADDITIONS`), which the Prospector had refused as `out_of_scope` on the park's 1980
designation date. The 16 doubtful rows stay out: E8 left them to the scope rule, and no decision
since names one of them.

**What is pinned beside it, each with the decision that says so** - never inferred from a row:

* `EXCLUSIONS` - a candidate the scope rule D58 (2026-10-24) keeps out: L'Anse aux Meadows (the owner
  named it in D58: a Viking subject) and the Walls of Constantinople (the Theodosian Walls, a
  Byzantine subject; the scout's already-decided list of 2026-10-24 records it as E8 + D58). It is
  resolved and reported like the others, and the plan never inserts it;
* `PARENTS` - a candidate whose curated parent is already decided (D25, "parent_site_id for
  component sites", and the scout's already-decided list: the Terracotta Army is a component of the
  curated Qin Shi Huang's Mausoleum). The plan writes `parent_site_id` at the insert, under the D25
  lane's own invariants. Every other component relation stays the D25 lane's (`HANDOFF.json`).

**How each candidate is resolved** (`resolve`, first failure wins, recorded as `status` and `reason`):
the Wikidata item exists and is not merged into another (`qid-missing`, `qid-merged`); it has an
English article (`no-enwiki-article`); the article exists, is no redirect and no disambiguation page,
and names this very item (`enwiki-*`). A resolved candidate carries its seeds for the research
question: the item's English label, its P625 point, the curated spelling of its country. A seed is a
starting point the researcher confirms or replaces with a quote - never a written value.

**One read-only production read** (`read_sql`, one repeatable-read transaction) then says, per
candidate: whether a curated row already holds its item or article (`already-curated` - such a site
gets no second row; a retired one comes back through the scope lane, never through this one), which
curated rows carry its name (`name_twins`, the plan's duplicate guard), and which `site_proposals`
rows name its item or article (the rows the insert closes) or only its name (listed, never closed: a
name alone does not say which place a proposal meant - "Memphis" is also Memphis, Tennessee).

    PY=./.venv/Scripts/python.exe
    $PY scripts/remediation/insert_site/run.py candidates --run d57-2026-10-24 \\
        --demand-dir C:/PythonProjects/AncientMap/output/seo-audit-2026-10-08/scratch/demand

Writes `CANDIDATES.jsonl`, `CANDIDATES.md`, `READ.jsonl` (the export as it came) and the item cache
under `<run>/entities/`.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from bcases.collect import claims_record  # noqa: E402 - the truthy P625 and the English label
from census.fetch import Fetcher, chunked  # noqa: E402
from fields import harvest as H  # noqa: E402 - the Wikimedia items and the article resolution
from identity.wiki import article_url  # noqa: E402 - how the site's source_url values spell one
from mechanical.lane import sql_literal  # noqa: E402
from mechanical.plan import (  # noqa: E402
    parse_tagged_export,
    tagged_export_script,
    write_tagged_export,
)

from pipeline.lyra.site_key import site_key_sql  # noqa: E402 - the one name-key definition
from pipeline.utils.public_sites import not_retired  # noqa: E402

LANE = "insert-site"
ROOT = REPO / "output" / "remediation" / "insert_site"
CANDIDATES_FILE = "CANDIDATES.jsonl"
REPORT_FILE = "CANDIDATES.md"
READ_FILE = "READ.jsonl"
INSCOPE_CSV = "agg_inscope_candidates.csv"
PROPOSALS_CSV = "proposals_by_demand.csv"
#: The hand review's verdict that makes a row a candidate (the other one is `zweifelhaft`).
IN_VERDICT = "in"
CURATED = "ancient_nerds"
#: How the CSV of 2026-10-08 was measured: 54 rows, 38 of them `in`. A file that holds another count
#: is another file, and a candidate list built from it would not be the one D57 names.
EXPECTED_IN_ROWS = 38

CANDIDATE, EXCLUDED, UNRESOLVED, ALREADY = "candidate", "excluded", "unresolved", "already-curated"
STATUSES = (CANDIDATE, EXCLUDED, UNRESOLVED, ALREADY)
#: The proposal statuses an insert may close. `approved` and `merged` are closed already
#: (`api/routes/proposals.py:_require_open`); a candidate whose proposal is one of them is refused,
#: because a promoted proposal means a row exists somewhere.
CLOSED_PROPOSALS = frozenset({"approved", "merged"})


class CandidateError(ValueError):
    """The candidate list cannot be built from these inputs. Nothing was written."""


@dataclass(frozen=True)
class Pin:
    """One hand-made entry of the list and the decision that makes it."""

    qid: str
    why: str


#: Candidates beyond the CSV's `in` rows: D57 names Chaco Canyon. Its item is the park, which the
#: English article "Chaco Canyon" redirects to (measured 2026-10-24: `Chaco Canyon` ->
#: `Chaco Culture National Historical Park`, wikibase_item Q732463).
ADDITIONS: tuple[Pin, ...] = (
    Pin(
        "Q732463",
        "D57 (owner, 2026-10-24): 'the 38 high-demand sites without a page (+ Chaco Canyon)'; the "
        "Prospector's out_of_scope read the park's designation date (P571 1980-12-19) as the site's",
    ),
)
#: Candidates the scope rule keeps out (D58, 2026-10-24: only the medieval Old World of Europe,
#: Byzantium and the Vikings is out).
EXCLUSIONS: tuple[Pin, ...] = (
    Pin("Q189113", "D58 (owner, 2026-10-24): 'L'Anse aux Meadows stays out (Viking subject)'"),
    Pin(
        "Q89917",
        "E8 + D58: the Theodosian Walls are a Byzantine subject, out under both readings of the "
        "scope rule (scout already-decided list, 2026-10-24)",
    ),
)


@dataclass(frozen=True)
class ParentPin:
    """A candidate whose curated parent is decided: the parent's Wikidata item, and why."""

    qid: str
    parent_qid: str
    why: str


PARENTS: tuple[ParentPin, ...] = (
    ParentPin(
        "Q47672",
        "Q910180",
        "D25 ('parent_site_id for component sites'): the Terracotta Army pits are a component of "
        "Qin Shi Huang's Mausoleum (scout already-decided list, 2026-10-24: 'its own page with "
        "parent_site_id pointing to the Mausoleum')",
    ),
)


# ------------------------------------------------------------------------------------ the inputs
def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise CandidateError(f"{path} does not exist - name the demand directory of 2026-10-08")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def seed_rows(demand_dir: Path) -> list[dict[str, Any]]:
    """The CSV's `in` rows and the additions, one per item, in the CSV's order of demand.

    Refused: a CSV that does not hold the 38 `in` rows the 2026-10-08 review produced, an item that
    occurs twice, an addition that is already a row, and a pin (exclusion or parent) that names no
    candidate - a pin that matches nothing would read as a decision that was applied.
    """
    rows = read_csv(demand_dir / INSCOPE_CSV)
    chosen = [r for r in rows if r["manual_verdict"] == IN_VERDICT]
    if len(chosen) != EXPECTED_IN_ROWS:
        raise CandidateError(
            f"{INSCOPE_CSV} holds {len(chosen)} '{IN_VERDICT}' rows, the review of 2026-10-08 "
            f"produced {EXPECTED_IN_ROWS}: this is not the list D57 names"
        )
    queue = {r["qid"]: r for r in read_csv(demand_dir / PROPOSALS_CSV) if r.get("qid")}
    out: list[dict[str, Any]] = []
    for row in chosen:
        out.append(
            {
                "qid": row["qid"],
                "origin": f"{INSCOPE_CSV} rank {row['rank']}",
                "wp_title": row["wp_title"],
                "our_names": row["our_names"],
                "csv_country": row["country"],
                "wp_views_jul_sep_2026": int(row["wp_views_jul_sep_2026"] or 0),
                "note": row["manual_note"],
                "queue_2026_10_08": (queue.get(row["qid"]) or {}).get("status"),
            }
        )
    for pin in ADDITIONS:
        out.append(
            {
                "qid": pin.qid,
                "origin": pin.why,
                "wp_title": None,
                "our_names": None,
                "csv_country": None,
                "wp_views_jul_sep_2026": None,
                "note": None,
                "queue_2026_10_08": (queue.get(pin.qid) or {}).get("status"),
            }
        )
    counts = Counter(r["qid"] for r in out)
    twice = sorted(q for q, n in counts.items() if n > 1)
    if twice:
        raise CandidateError(f"item(s) {twice} occur twice in the candidate list")
    named = set(counts)
    for qid in [p.qid for p in EXCLUSIONS] + [p.qid for p in PARENTS]:
        if qid not in named:
            raise CandidateError(f"a pin names {qid}, which is no candidate")
    return out


# ------------------------------------------------------------------------------------ resolution
def _excluded() -> dict[str, str]:
    return {p.qid: p.why for p in EXCLUSIONS}


def _parents() -> dict[str, ParentPin]:
    return {p.qid: p for p in PARENTS}


def resolve(
    seeds: Sequence[Mapping[str, Any]],
    entities: Mapping[str, Mapping[str, Any]],
    articles: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Each seed with its item, article and seeds - or the reason it does not resolve.

    `entities` maps an item id to the served entity (`fields.harvest.load_entity`), `articles` an
    English title to its resolution (`fields.harvest.resolve_wiki_titles`).
    """
    excluded = _excluded()
    parents = _parents()
    out: list[dict[str, Any]] = []
    for seed in seeds:
        qid = str(seed["qid"])
        line: dict[str, Any] = {
            **seed,
            "status": CANDIDATE,
            "reason": None,
            "label_en": None,
            "enwiki_title": None,
            "enwiki_url": None,
            "p625": None,
            "parent_qid": parents[qid].parent_qid if qid in parents else None,
            "parent_why": parents[qid].why if qid in parents else None,
        }
        entity = entities.get(qid)
        if entity is None or "missing" in entity:
            line.update(status=UNRESOLVED, reason="qid-missing")
            out.append(line)
            continue
        # A merged item is the same entity under the id it was merged into: Wikidata answers the
        # asked id with the target's entity and `redirects`. The candidate takes the target's id
        # (the id every later read and the site's external ids carry) and keeps the asked one.
        merged_into = str(entity.get("id"))
        if merged_into != qid:
            if (entity.get("redirects") or {}).get("from") != qid:
                raise CandidateError(f"Wikidata answered {qid} with {merged_into} and no redirect")
            line.update(qid=merged_into, qid_asked=qid)
        record = claims_record(entity)
        line["label_en"] = record["en_label"]
        point = record["p625"]
        if point is not None and point["globe"] in ("Q2", None):
            line["p625"] = {
                "lat": point["lat"],
                "lon": point["lon"],
                "precision": point["precision"],
            }
        title = record["enwiki"]
        if not title:
            line.update(status=UNRESOLVED, reason="no-enwiki-article")
            out.append(line)
            continue
        if line["p625"] is None:
            # the research's coordinate answer is a keep or a replace against a seed point
            # (`fields/answers.py`), so a candidate without one has no question to ask
            line.update(status=UNRESOLVED, reason="no-p625: the item carries no point on Earth")
            out.append(line)
            continue
        page = articles[title]
        problem = (
            "enwiki-missing"
            if page["missing"] or page["invalid"]
            else "enwiki-redirect"
            if page["redirected"]
            else "enwiki-disambiguation"
            if page["disambiguation"]
            else f"enwiki-other-item: {page['wikibase_item']}"
            if page["wikibase_item"] != line["qid"]
            else None
        )
        line.update(
            enwiki_title=page["resolved_title"],
            enwiki_url=article_url("en", page["resolved_title"]),
        )
        if problem is not None:
            line.update(status=UNRESOLVED, reason=problem)
        elif qid in excluded:
            line.update(status=EXCLUDED, reason=excluded[qid])
        out.append(line)
    counts = Counter(str(line["qid"]) for line in out)
    twice = sorted(q for q, n in counts.items() if n > 1)
    if twice:
        raise CandidateError(f"item(s) {twice} are two candidates after Wikidata's merges")
    return out


def fetch_items(
    net: Fetcher, root: Path, seeds: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The items and their English articles, from the Wikimedia APIs (cached under `root`)."""
    qids = [str(s["qid"]) for s in seeds]
    H.fetch_entities(net, root, qids)
    entities = {qid: H.load_entity(root, qid) for qid in qids}
    titles = sorted(
        {t for t in (H.enwiki_sitelink(e) for e in entities.values() if "missing" not in e) if t}
    )
    articles: dict[str, Any] = {}
    for chunk in chunked(titles, H.BATCH):
        articles.update(H.resolve_wiki_titles(net, "en", chunk))
    return entities, articles


# ------------------------------------------------------------------------------------ production
KINDS = ("ids", "twins", "proposals", "name_proposals", "parents", "vocabulary")
VOCABULARY_FILE = "VOCABULARY.json"


def _values(lines: Sequence[Mapping[str, Any]]) -> str:
    """The candidates as a VALUES list: item, label, title, point (NULL without a P625)."""
    rows = []
    for line in lines:
        point = line.get("p625") or {}
        rows.append(
            "({qid}, {label}, {title}, {lat}::double precision, {lon}::double precision)".format(
                qid=sql_literal(str(line["qid"])),
                label=sql_literal(line.get("label_en")),
                title=sql_literal(line.get("enwiki_title")),
                lat=point.get("lat", "NULL") if point else "NULL",
                lon=point.get("lon", "NULL") if point else "NULL",
            )
        )
    return ",\n".join(rows)


def read_sql(lines: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """The read's parts, each over the candidates' `VALUES` list `k(qid, label, title, lat, lon)`.

    * `ids` - curated rows (any scope status) that hold the item or the article in
      `site_external_ids`: the Prospector's rung 0, here the refusal `already-curated`;
    * `twins` - shown curated rows whose name key is the label's or the title's (`site_key_sql`, the
      key computed in Postgres), with the distance from the item's point when it has one;
    * `proposals` - `site_proposals` that name the item or the article (the rows the insert closes);
    * `name_proposals` - proposals with neither, whose name key is the label's or the title's
      (listed, never closed);
    * `parents` - the curated rows that hold a pinned parent's item;
    * `vocabulary` - the country spellings of the shown curated sites, with their counts: the
      research question lists them, and the plan's country check reads them (`VOCABULARY.json`).
    """
    values = _values(lines)
    k = f"(VALUES\n{values}\n) AS k(qid, label, title, lat, lon)"
    parent_qids = sorted({p.parent_qid for p in PARENTS})
    parents = ", ".join(sql_literal(q) for q in parent_qids) or "NULL"
    return [
        (
            "ids",
            f"SELECT k.qid, e.kind, e.value, u.id::text AS site_id, u.name, u.scope_status "
            f"FROM {k} JOIN site_external_ids e ON (e.kind = 'wikidata_qid' AND e.value = k.qid) "
            f"OR (e.kind = 'enwiki_title' AND e.value = k.title) "
            f"JOIN unified_sites u ON u.id = e.site_id AND u.source_id = '{CURATED}'",
        ),
        (
            "twins",
            f"SELECT k.qid, u.id::text AS site_id, u.name, u.country, "
            f"CASE WHEN k.lat IS NULL THEN NULL ELSE round(ST_DistanceSphere("
            f"ST_MakePoint(u.lon, u.lat), ST_MakePoint(k.lon, k.lat))::numeric) END AS metres "
            f"FROM {k} JOIN unified_sites u ON u.source_id = '{CURATED}' AND {not_retired('u')} "
            f"AND u.name_normalized IN ({site_key_sql('k.label')}, {site_key_sql('k.title')})",
        ),
        (
            "proposals",
            f"SELECT k.qid, p.id::text AS proposal_id, p.name, p.status, p.wikidata_qid, "
            f"p.enwiki_title, p.promoted_site_id::text AS promoted_site_id, "
            f"p.contribution_id::text AS contribution_id, p.evidence_count "
            f"FROM {k} JOIN site_proposals p ON p.wikidata_qid = k.qid OR p.enwiki_title = k.title",
        ),
        (
            "name_proposals",
            f"SELECT k.qid, p.id::text AS proposal_id, p.name, p.status, p.evidence_count "
            f"FROM {k} JOIN site_proposals p ON p.wikidata_qid IS NULL AND p.enwiki_title IS NULL "
            f"AND p.name_key IN ({site_key_sql('k.label')}, {site_key_sql('k.title')})",
        ),
        (
            "parents",
            f"SELECT e.value AS parent_qid, u.id::text AS site_id, u.name, u.country, u.lat, u.lon, "
            f"u.scope_status, u.parent_site_id::text AS parent_site_id "
            f"FROM site_external_ids e JOIN unified_sites u ON u.id = e.site_id "
            f"AND u.source_id = '{CURATED}' WHERE e.kind = 'wikidata_qid' AND e.value IN ({parents})",
        ),
        (
            "vocabulary",
            f"SELECT country, count(*) AS sites FROM unified_sites u WHERE u.source_id = "
            f"'{CURATED}' AND {not_retired('u')} AND country IS NOT NULL GROUP BY country",
        ),
    ]


READ_ONLY_SET = "SET default_transaction_read_only = on;\n"


def read_only_script(parts: Sequence[tuple[str, str]]) -> str:
    """`SET default_transaction_read_only = on`, then the tagged export's own read-only
    repeatable-read transaction - the identity package's read (`identity/export.build_script`)."""
    script = tagged_export_script(parts)
    quiet = "\\set QUIET on\n"
    if not script.startswith(quiet):
        raise CandidateError("the tagged export no longer starts with \\set QUIET on")
    return quiet + READ_ONLY_SET + script[len(quiet) :]


def read_script(lines: Sequence[Mapping[str, Any]]) -> str:
    return read_only_script(read_sql(lines))


def apply_read(
    lines: Sequence[Mapping[str, Any]], rows: Mapping[str, Sequence[Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    """The read's answer per candidate: `already-curated`, its twins, its proposals, its parent."""
    by: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for kind in ("ids", "twins", "proposals", "name_proposals"):
        for row in rows[kind]:
            by.setdefault(str(row["qid"]), {}).setdefault(kind, []).append(dict(row))
    parents: dict[str, list[dict[str, Any]]] = {}
    for row in rows["parents"]:
        parents.setdefault(str(row["parent_qid"]), []).append(dict(row))
    out: list[dict[str, Any]] = []
    for line in lines:
        mine = by.get(str(line["qid"]), {})
        held = mine.get("ids", [])
        proposals = sorted(mine.get("proposals", []), key=lambda p: p["proposal_id"])
        line = {
            **line,
            "curated_ids": held,
            "name_twins": mine.get("twins", []),
            "proposals": proposals,
            "name_proposals": sorted(
                mine.get("name_proposals", []), key=lambda p: p["proposal_id"]
            ),
            "parent": None,
        }
        if line["parent_qid"] is not None:
            found = parents.get(str(line["parent_qid"]), [])
            if len(found) != 1:
                raise CandidateError(
                    f"{line['qid']}: its pinned parent {line['parent_qid']} is held by "
                    f"{len(found)} curated row(s), not one - the pin names no single site"
                )
            line["parent"] = found[0]
        if line["status"] == CANDIDATE and held:
            sites = sorted({h["site_id"] for h in held})
            line.update(
                status=ALREADY,
                reason=f"already-curated: {', '.join(sites)} hold(s) the item or the article",
            )
        out.append(line)
    return out


# ------------------------------------------------------------------------------------ the files
def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
        newline="\n",
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise CandidateError(f"{path} does not exist")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x.strip()]


def read_candidates(run: Path) -> list[dict[str, Any]]:
    """The run's candidate list; refused when it was never built."""
    rows = read_jsonl(run / CANDIDATES_FILE)
    if not rows:
        raise CandidateError(f"{run / CANDIDATES_FILE} is empty")
    return rows


def report(lines: Sequence[Mapping[str, Any]]) -> str:
    """`CANDIDATES.md`: the counts, then one row per candidate."""
    counts = Counter(str(line["status"]) for line in lines)
    open_proposals = [
        p
        for line in lines
        if line["status"] == CANDIDATE
        for p in line["proposals"]
        if p["status"] not in CLOSED_PROPOSALS
    ]
    closing = len(open_proposals)
    radar = sum(1 for p in open_proposals if p["contribution_id"] is not None)
    out = [
        "# D57 insert lane - the candidate list",
        "",
        f"{len(lines)} candidates: "
        + ", ".join(f"{counts.get(s, 0)} {s}" for s in STATUSES)
        + f". The {counts.get(CANDIDATE, 0)} candidates name {closing} open proposal(s) by item or "
        f"article (the rows the insert closes); {radar} of them mirror a radar contribution, which "
        "the insert marks promoted in the same transaction (`plan._proposals`).",
        "",
        "| # | item | name (label) | English article | status | proposals (item/article) | "
        "name-only proposals | name twins | parent |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for number, line in enumerate(lines, start=1):
        proposals = (
            "; ".join(
                f"{p['name']} ({p['status']}"
                + (f", radar contribution {p['contribution_id']}" if p["contribution_id"] else "")
                + ")"
                for p in line["proposals"]
            )
            or "-"
        )
        named = "; ".join(f"{p['name']} ({p['status']})" for p in line["name_proposals"]) or "-"
        twins = (
            "; ".join(f"{t['name']} ({t['country']}, {t['metres']} m)" for t in line["name_twins"])
            or "-"
        )
        parent = line["parent"]["name"] if line.get("parent") else "-"
        status = line["status"] + (f": {line['reason']}" if line["reason"] else "")
        out.append(
            f"| {number} | {line['qid']} | {line['label_en'] or '-'} | {line['enwiki_title'] or '-'} "
            f"| {status} | {proposals} | {named} | {twins} | {parent} |"
        )
    return "\n".join(out) + "\n"


def build(
    run: Path,
    demand_dir: Path,
    *,
    net: Fetcher | None = None,
    export: Callable[[str, Path], Path] = write_tagged_export,
) -> dict[str, Any]:
    """Resolve, read production (read-only), write the list. Refused when the run already holds one:
    a question is asked of a list as it was built, so the list is built once."""
    if (run / CANDIDATES_FILE).exists():
        raise CandidateError(
            f"{run / CANDIDATES_FILE} exists: a run's candidate list is built once"
        )
    seeds = seed_rows(demand_dir)
    own = net is None
    client = H.open_fetcher(run) if own else net
    try:
        entities, articles = fetch_items(client, run, seeds)
    finally:
        if own:
            client.close()
    lines = resolve(seeds, entities, articles)
    path = export(read_script(lines), run / READ_FILE)
    rows, exported_at = parse_tagged_export(path.read_text(encoding="utf-8"), KINDS)
    lines = [{**line, "read_at": exported_at} for line in apply_read(lines, rows)]
    vocabulary = {str(r["country"]): int(r["sites"]) for r in rows["vocabulary"]}
    if not vocabulary:
        raise CandidateError("the read holds no country of a shown curated site")
    write_json(run / VOCABULARY_FILE, {"read_at": exported_at, "countries": vocabulary})
    write_jsonl(run / CANDIDATES_FILE, lines)
    (run / REPORT_FILE).write_text(report(lines), encoding="utf-8", newline="\n")
    counts = Counter(str(line["status"]) for line in lines)
    return {
        "run": run.name,
        "candidates": len(lines),
        "by_status": dict(sorted(counts.items())),
        "read_at": exported_at,
        "unresolved": [
            {"qid": line["qid"], "reason": line["reason"]}
            for line in lines
            if line["status"] == UNRESOLVED
        ],
    }


def read_vocabulary(run: Path) -> dict[str, int]:
    """The country spellings of the shown curated sites, as the candidate read found them."""
    path = run / VOCABULARY_FILE
    if not path.is_file():
        raise CandidateError(f"{path} does not exist - build the candidate list first")
    return dict(json.loads(path.read_text(encoding="utf-8"))["countries"])


def chosen(lines: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The candidates the research asks about: resolved, not excluded, not curated already."""
    return [dict(line) for line in lines if line["status"] == CANDIDATE]
