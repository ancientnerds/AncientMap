"""Build the gap run's plan: every (site, field) question the mass run bought no readable verdict for.

The mass run judged 24,255 of the 25,020 fields of the 5,004 curated sites. The rest are three classes,
counted from its own files with the pipeline's own parser (`discover_stage.parse_answer`):

* **over-bound** - 152 sites whose combined evidence exceeded `model_stage.MAX_EVIDENCE_CHARS`, all five
  fields refused whole (`model.json` `skipped`, "the evidence is N characters, over the 64000-character
  bound");
* **empty-stream** - 5 fields whose model stream carried no text (`model.json` `failures`); the mass
  driver marks such a batch done and never asks again;
* **no-verdict** - 37 answers with no readable `VERDICT:` line. The parser is not loosened to rescue
  them (HANDOVER section 7); they are asked again.

802 questions over 194 sites. This tool turns them into `PLAN.gap.jsonl` for `mass_run.py`, with batch
ids `gap-NNNN` - so no journal stamp and no `APPLIED.json` of the mass lane can ever match one of them
(`lanes.py`) - and with every record built from a **fresh read-only export of production**, not from
the 2026-09-20 snapshot the mass run was planned from: two gap sites had their country changed by the
mechanical lane since, and several had other fields written by phase 3.

What a record carries beyond the mass run's shape (`snapshot_plan.discover_site_record`):

* `rerun_fields` - the fields this run was built to ask; the discover pass asks only these and the
  writer refuses any other field of the site (`write_stage.RULE_NOT_RERUN`), so the 42 partly-decided
  sites cannot re-decide what is already done. **No `search_fields`**: that key is the search lane's
  (`search_evidence.search_fields`), and a record without it buys no MiniMax search - this run's
  levers are the narrowed Wikidata evidence and the enwiki sitelink route below. `mass_run.py` reads
  such a plan as a *rerun* plan and runs it through `prepare,fetch,judge`;
* `source_batch` - the mass batch the question comes from;
* `wikidata_route: "narrow"` - the narrowed Wikidata evidence (`fetch_stage`), for every kept item;
* `withheld_wikidata_qid` - an item that is not given to the run, with the reason: an id the reviewed
  repair (`qid_repair.py`) replaces or leaves unresolved, as long as production still holds it, and an
  item more than one curated site carries (a parent or generic item);
* `enwiki_sitelink` - the English article through the item's own sitelink, for a site whose article by
  stored name was missing in the mass run (W12).

Subcommands, in order (only `export` and `sitelinks` leave the machine, both read-only):

    census     runs/mass -> questions.json                       offline
    export     questions.json -> export/ (production, read-only)  ssh + SELECT
    sitelinks  -> sitelinks.json (Wikidata, read-only)            HTTP GET
    plan       -> PLAN.gap.jsonl                                  offline
    measure    a prepared and fetched run dir -> the evidence totals per site, offline
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import unquote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - paths, the JSON-lines reader and the read-only psql seam
import qid_repair  # noqa: E402 - the reviewed id repair, which decides which items are withheld

sys.path.insert(0, str(lanes.REPO / "scripts" / "remediation"))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402 - the key a rerun record names fields under
from phase3 import snapshot_plan as SP  # noqa: E402

GAP = lanes.REMEDIATION / "gap"
QUESTIONS = GAP / "questions.json"
EXPORT = GAP / "export"
SITELINKS = GAP / "sitelinks.json"
PLAN = lanes.REMEDIATION / "phase3_runner" / "PLAN.gap.jsonl"
BATCH_SIZE = 15
OVER_BOUND_RE = re.compile(r"the evidence is (\d+) characters, over the (\d+)-character bound")
OVER_BOUND, EMPTY_STREAM, NO_VERDICT = "over-bound", "empty-stream", "no-verdict"


@dataclass(frozen=True)
class Question:
    """One (site, field) the mass run holds no readable verdict for, and why."""

    site_id: str
    field: str
    source_batch: str
    position: int  #: the site's 0-based position in its mass batch
    why: str
    detail: str


def census(run_dir: pathlib.Path) -> list[Question]:
    """Every gap question of a finished run, in the run's own order (batch, then site, then field).

    A (site, field) that shows up in two classes, a site with only some of its over-bound fields,
    and a skip whose reason is not the evidence bound are refused: each would mean the run's own
    record is not the shape this census reads.
    """
    questions: dict[tuple[str, str], Question] = {}
    other_skips: collections.Counter[str] = collections.Counter()

    def add(question: Question) -> None:
        key = (question.site_id, question.field)
        if key in questions:
            raise SystemExit(
                f"{key} is a gap question twice ({questions[key].why}, {question.why})"
            )
        questions[key] = question

    batches = sorted(path for path in run_dir.iterdir() if (path / "input.json").exists())
    if not batches:
        raise SystemExit(f"{run_dir}: no batch with an input.json")
    for batch in batches:
        payload = json.loads((batch / "input.json").read_text(encoding="utf-8"))
        position = {str(site["site_id"]): index for index, site in enumerate(payload["sites"])}
        model = json.loads((batch / "model.json").read_text(encoding="utf-8"))
        for skip in model.get("skipped") or []:
            match = OVER_BOUND_RE.search(str(skip.get("reason") or ""))
            if match is None:
                other_skips[str(skip.get("reason"))[:60]] += 1
                continue
            site_id = str(skip["site_id"])
            add(
                Question(
                    site_id,
                    str(skip["field"]),
                    batch.name,
                    position[site_id],
                    OVER_BOUND,
                    f"evidence {match.group(1)} characters, bound {match.group(2)}",
                )
            )
        for failure in model.get("failures") or []:
            site_id = str(failure["site_id"])
            add(
                Question(
                    site_id,
                    str(failure["field"]),
                    batch.name,
                    position[site_id],
                    EMPTY_STREAM,
                    str(failure["reason"]),
                )
            )
        for path in sorted((batch / "answers").glob("*.txt")):
            site_id, field_name = unquote(path.stem).split("/", 1)
            answer = DS.parse_answer(path.read_text(encoding="utf-8"))
            if answer.verdict is None:
                add(
                    Question(
                        site_id,
                        field_name,
                        batch.name,
                        position[site_id],
                        NO_VERDICT,
                        "; ".join(answer.problems),
                    )
                )
    if other_skips:
        raise SystemExit(f"skips that are not the evidence bound: {dict(other_skips)}")
    fields = collections.Counter(q.site_id for q in questions.values() if q.why == OVER_BOUND)
    partial = {site: count for site, count in fields.items() if count != len(DS.DISCOVER_FIELDS)}
    if partial:
        raise SystemExit(f"over-bound sites without all five fields skipped: {partial}")
    order = {name: index for index, name in enumerate(DS.DISCOVER_FIELDS)}
    return sorted(questions.values(), key=lambda q: (q.source_batch, q.position, order[q.field]))


def read_questions(path: pathlib.Path = QUESTIONS) -> list[Question]:
    return [Question(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


# ------------------------------------------------------------------------------------ the export
def export_sql(site_ids: list[str]) -> dict[str, str]:
    ids = lanes.sql_literals(site_ids)
    return {
        "unified_sites": (
            "SELECT to_jsonb(t)::text FROM (SELECT id::text AS id, name, description, "
            "period_start, site_type, country, source_id, source_url, lat, lon "
            f"FROM unified_sites WHERE id::text IN ({ids}) ORDER BY id) t;"
        ),
        "card_stats": (
            "SELECT to_jsonb(t)::text FROM (SELECT site_id::text AS site_id, card_description "
            f"FROM card_stats WHERE site_id::text IN ({ids}) ORDER BY site_id) t;"
        ),
        # every curated site's item: whether an item is shared is a property of the whole set
        "site_external_ids": (
            "SELECT to_jsonb(t)::text FROM (SELECT e.site_id::text AS site_id, e.kind, e.value "
            "FROM site_external_ids e JOIN unified_sites u ON u.id = e.site_id "
            "WHERE u.source_id = 'ancient_nerds' AND e.kind = 'wikidata_qid' "
            "ORDER BY e.site_id) t;"
        ),
    }


def export(questions: list[Question], out: pathlib.Path, *, run=lanes.psql) -> dict[str, int]:
    site_ids = sorted({q.site_id for q in questions})
    counts: dict[str, int] = {}
    statements = export_sql(site_ids)
    for table, sql in statements.items():
        rows = lanes.json_rows(run(sql))
        lanes.write_jsonl(out / f"{table}.jsonl", rows)
        counts[table] = len(rows)
    sites = lanes.read_jsonl(out / "unified_sites.jsonl")
    missing = set(site_ids) - {row["id"] for row in sites}
    foreign = [row["id"] for row in sites if row["source_id"] != SP_CURATED]
    if missing or foreign:
        raise SystemExit(f"export: missing {sorted(missing)}, not curated {foreign}")
    (out / "MANIFEST.json").write_text(
        json.dumps(
            {
                "exported_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                "host": lanes.HOST,
                "rows": counts,
                "sites_asked": len(site_ids),
                "sql": statements,
            },
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return counts


SP_CURATED = "ancient_nerds"


# ------------------------------------------------------------------------------------ the routes
def enwiki_missing(path: pathlib.Path) -> bool:
    """Was the mass run's enwiki-by-name page a missing page? A page cut at the cap is not.

    Only two answers are read: a page with a `pageid` (the article exists) and a page marked
    `missing`. Anything else - an API error body, a title the API calls `invalid`, an answer without
    `query.pages` - is refused by name: read as "exists" it would silently keep the site off the
    sitelink route, read as "missing" it would route a site whose own question was never answered.
    """
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if len(text.encode("utf-8")) >= F.MAX_PAGE_BYTES:
            return False  # an article so long it was cut; certainly not missing
        raise SystemExit(f"{path}: an enwiki evidence file that is neither JSON nor cut") from None
    query = payload.get("query") if isinstance(payload, dict) else None
    pages = query.get("pages") if isinstance(query, dict) else None
    if not isinstance(pages, dict) or not pages:
        raise SystemExit(f"{path}: an enwiki answer without query.pages: {text[:200]!r}")
    unread = [
        page
        for page in pages.values()
        if not isinstance(page, dict) or ("missing" not in page and "pageid" not in page)
    ]
    if unread:
        raise SystemExit(
            f"{path}: a page that is neither an article (pageid) nor missing: {unread[0]!r}"
        )
    return any("missing" in page for page in pages.values())


def shared_counts(external: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """`{qid: curated sites carrying it}`, not counting a link the reviewed repair replaces.

    A link the repair has established as wrong (the Tomb of Artaxerxes III on Persepolis' Q129072)
    does not make the item a shared one for the site it really belongs to (Persepolis).
    """
    wrong = {(site.site_id, site.old_qid) for site in qid_repair.SITES if site.rule != "unresolved"}
    return dict(
        collections.Counter(
            str(row["value"])
            for row in external
            if (str(row["site_id"]), str(row["value"])) not in wrong
        )
    )


def withheld_reason(
    site_id: str, qid: str | None, *, shared: Mapping[str, int]
) -> tuple[str | None, str | None]:
    """(the item the run is given, or None; why an item is withheld, or None)."""
    if qid is None:
        return None, None
    repair = {site.site_id: site for site in qid_repair.SITES}.get(site_id)
    if repair is not None:
        if repair.rule == "unresolved":
            return None, (
                f"{qid} is unresolved in the reviewed external-id repair "
                f"(output/remediation/qid_repair/PLAN.md): {repair.evidence[0]}"
            )
        if qid == repair.old_qid:
            return None, (
                f"{qid} is mis-resolved; the reviewed repair replaces it with {repair.new_qid}, "
                "and it is not applied yet"
            )
        if qid != repair.new_qid:
            raise SystemExit(
                f"{site_id}: production carries {qid}, the repair plans {repair.old_qid} -> "
                f"{repair.new_qid}; neither - read the site again before planning it"
            )
    if shared.get(qid, 0) > 1:
        return None, (
            f"{qid} is carried by {shared[qid]} curated sites: a shared item describes a parent or a "
            "generic entity, not this site"
        )
    return qid, None


def site_records(
    questions: list[Question],
    *,
    export_dir: pathlib.Path,
    sitelinks: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One plan record per gap site, in the questions' order."""
    sites = {row["id"]: row for row in lanes.read_jsonl(export_dir / "unified_sites.jsonl")}
    cards = {row["site_id"]: row for row in lanes.read_jsonl(export_dir / "card_stats.jsonl")}
    external = lanes.read_jsonl(export_dir / "site_external_ids.jsonl")
    qids = SP.qids_by_site(external, origin=str(export_dir / "site_external_ids.jsonl"))
    shared = shared_counts(external)
    by_site: dict[str, list[Question]] = collections.OrderedDict()
    for question in questions:
        by_site.setdefault(question.site_id, []).append(question)
    records = []
    for site_id, asked in by_site.items():
        qid, withheld = withheld_reason(site_id, qids.get(site_id), shared=shared)
        record = SP.discover_site_record(site=sites[site_id], card=cards.get(site_id), qid=qid)
        record[SE.RERUN_FIELDS_KEY] = [q.field for q in asked]
        record["source_batch"] = asked[0].source_batch
        record["gap_reasons"] = sorted({q.why for q in asked})
        if qid is not None:
            record[F.WIKIDATA_ROUTE_KEY] = F.WIKIDATA_ROUTE_NARROW
        if withheld is not None:
            record["withheld_wikidata_qid"] = {"qid": qids[site_id], "reason": withheld}
        link = sitelinks.get(site_id)
        if link is not None and link.get("title") and link.get("refused") is None:
            if link["qid"] != qid:
                raise SystemExit(
                    f"{site_id}: the sitelink was resolved for {link['qid']}, not {qid}"
                )
            if link["title"] != record["name"]:
                record[F.ENWIKI_SITELINK_KEY] = {"qid": link["qid"], "title": link["title"]}
        F.targets_for_site(record)  # a record the fetch stage would refuse is refused here
        records.append(record)
    return records


def batches(records: list[dict[str, Any]], size: int = BATCH_SIZE) -> list[R.Batch]:
    """`gap-0001`, `gap-0002`, ... - never `batch-NNNN`, whose stamps the mass lane owns."""
    return R.assign_batches(
        records, size, pass_name=R.DISCOVER_PASS, prefix=lanes.BATCH_PREFIX["gap"]
    )


# ------------------------------------------------------------------------------------ the measure
def measure(run_dir: pathlib.Path) -> list[dict[str, Any]]:
    """Per site of a prepared, fetched run: the evidence the finder would be shown, in characters.

    The same two calls the discover stage makes (`model_stage.evidence_excerpts`, then the bound), so
    "fits" here is "is asked" there. No model is called.
    """
    rows = []
    for batch in sorted(path for path in run_dir.iterdir() if (path / "input.json").exists()):
        payload = json.loads((batch / "input.json").read_text(encoding="utf-8"))
        failures = MS.read_fetch_failures(batch / "fetch.json")
        store = F.EvidenceStore(batch / "evidence")
        for site in payload["sites"]:
            site_id = str(site["site_id"])
            excerpts = MS.evidence_excerpts(
                site_id=site_id,
                site=site,
                store=store,
                hit_pages=False,
                failures=failures.get(site_id),
            )
            total = sum(excerpt.chars for excerpt in excerpts)
            rows.append(
                {
                    "batch": batch.name,
                    "site_id": site_id,
                    "name": site["name"],
                    "total": total,
                    "fits": total <= MS.MAX_EVIDENCE_CHARS,
                    "features": {excerpt.feature: excerpt.chars for excerpt in excerpts},
                    "cut": sorted(excerpt.feature for excerpt in excerpts if excerpt.truncated),
                    "failed": sorted(e.feature for e in excerpts if e.failure is not None),
                }
            )
    return rows


# ------------------------------------------------------------------------------------ the CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gap-plan")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("census")
    one.add_argument("--mass-run", default=str(lanes.lane().run_dir))
    one.add_argument("--out", default=str(QUESTIONS))
    two = sub.add_parser("export")
    two.add_argument("--questions", default=str(QUESTIONS))
    two.add_argument("--out", default=str(EXPORT))
    three = sub.add_parser("sitelinks")
    three.add_argument("--questions", default=str(QUESTIONS))
    three.add_argument("--export", default=str(EXPORT))
    three.add_argument("--mass-run", default=str(lanes.lane().run_dir))
    three.add_argument("--out", default=str(SITELINKS))
    four = sub.add_parser("plan")
    four.add_argument("--questions", default=str(QUESTIONS))
    four.add_argument("--export", default=str(EXPORT))
    four.add_argument("--sitelinks", default=str(SITELINKS))
    four.add_argument("--out", default=str(PLAN))
    five = sub.add_parser("measure")
    five.add_argument("--run-dir", required=True)
    five.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.command == "census":
        questions = census(pathlib.Path(args.mass_run))
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps([asdict(q) for q in questions], indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        by_why = collections.Counter(q.why for q in questions)
        print(
            f"{len(questions)} questions over {len({q.site_id for q in questions})} sites: "
            f"{dict(sorted(by_why.items()))} -> {out}"
        )
        return 0
    if args.command == "export":
        counts = export(read_questions(pathlib.Path(args.questions)), pathlib.Path(args.out))
        print(f"exported {counts} -> {args.out}")
        return 0
    if args.command == "sitelinks":
        return _sitelinks(args)
    if args.command == "plan":
        questions = read_questions(pathlib.Path(args.questions))
        sitelinks = json.loads(pathlib.Path(args.sitelinks).read_text(encoding="utf-8"))
        records = site_records(questions, export_dir=pathlib.Path(args.export), sitelinks=sitelinks)
        planned = batches(records)
        R.write_batches(pathlib.Path(args.out), planned)
        asked = sum(len(record[SE.RERUN_FIELDS_KEY]) for record in records)
        routes = collections.Counter(
            "narrow"
            if F.WIKIDATA_ROUTE_KEY in record
            else ("withheld" if "withheld_wikidata_qid" in record else "no-qid")
            for record in records
        )
        linked = sum(1 for record in records if F.ENWIKI_SITELINK_KEY in record)
        print(
            f"{len(planned)} batches, {len(records)} sites, {asked} questions; wikidata "
            f"{dict(routes)}; enwiki sitelinks {linked} -> {args.out} "
            f"(sha256 {R._sha256(pathlib.Path(args.out))})"
        )
        return 0
    rows = measure(pathlib.Path(args.run_dir))
    pathlib.Path(args.out).write_text(
        json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    over = [row for row in rows if not row["fits"]]
    print(
        f"{len(rows)} sites measured: {len(rows) - len(over)} fit under "
        f"{MS.MAX_EVIDENCE_CHARS}, {len(over)} over -> {args.out}"
    )
    for row in sorted(over, key=lambda row: -row["total"]):
        print(f"  {row['total']:>7} {row['name'][:40]:40} {row['features']} cut={row['cut']}")
    return 0


def _sitelinks(args: argparse.Namespace) -> int:
    """Resolve the English article through the item for sites whose article-by-name was missing."""
    questions = read_questions(pathlib.Path(args.questions))
    export_dir = pathlib.Path(args.export)
    external = lanes.read_jsonl(export_dir / "site_external_ids.jsonl")
    qids = SP.qids_by_site(external, origin=str(export_dir / "site_external_ids.jsonl"))
    shared = shared_counts(external)
    mass = pathlib.Path(args.mass_run)
    wanted: dict[str, str] = {}
    looked = 0
    for site_id, source_batch in sorted({(q.site_id, q.source_batch) for q in questions}):
        qid, _ = withheld_reason(site_id, qids.get(site_id), shared=shared)
        if qid is None:
            continue
        page = F.EvidenceStore(mass / source_batch / "evidence").path_for(site_id, F.FEATURE_ENWIKI)
        looked += 1
        if enwiki_missing(page):
            wanted[site_id] = qid
    with F.HttpFetcher() as fetcher:
        resolved = F.resolve_enwiki_sitelinks(wanted, shared=shared, fetcher=fetcher)
    out = {site_id: asdict(resolution) for site_id, resolution in sorted(resolved.items())}
    pathlib.Path(args.out).write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    titled = sum(1 for row in out.values() if row["title"] and row["refused"] is None)
    print(
        f"{looked} gap sites with an item; {len(wanted)} had no article by name; {titled} resolved "
        f"to an English article -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
