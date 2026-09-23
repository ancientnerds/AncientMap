"""S0 PLAN: every curated site with its old values, its flags and its place in the run. No LLM.

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, section
pipeline ("S0 PLAN"). Work item WB-A3.

Three steps, each its own subcommand, so the one production read is made once and the plan can be
rebuilt from it offline, byte for byte:

* `read`  - one read-only production SELECT (`PLAN_SQL`, through `write_stage.run_sql`, parsed by
            `write_stage._json_rows`): per curated site the stored fields, the sha256 of its
            description, `raw_data::text` and card as Postgres computes them, its `wikidata_qid` and
            `enwiki_title`, its `unified_site_names` and its description in pre-March snapshot
            d4526691. Written to `S0_ROWS.jsonl`.
* `names` - the labels and aliases (every language) of the Wikidata items more than one curated site
            shares, the one fact the duplicate-pair rule needs that the database does not hold
            (`wbgetentities props=labels|aliases`, through the 1 MiB wiki client, ledgered).
* `build` - offline: `build_plan` over the rows, the reviewer-cleared defects
            (`logs/_write_dry/ALL_REFUSED.jsonl`, rule `report-only-field`), the T03 findings
            (`run_t03/findings.jsonl`) and the pilot's site ids (`gold_standard/sites.json`), then
            `write_plan`: `PLAN4.jsonl`, batches of 15 named `p4-NNNN`. Its summary lists the
            stored titles MediaWiki refuses (`invalid_titles`) for the data repair.

Derived here, from data and not from the B block's temp files (`SiteFlag`):

* `shared-qid` / `shared-title` - a QID or title more than one curated site stores (GROUP BY ...
  HAVING count > 1);
* `scope-pending` - outside `pipeline.normalizers.dates.passes_date_cutoff`, or undated (no
  `period_start` and no `period_end`): S1 holds these, because E4 hides them;
* `duplicate-pair` - two sites sharing an item whose stored names are both labels or aliases of it
  (folded: accents, case and punctuation), within 2 km. Listed for the B duplicate lane and written
  like any other site;
* `cleared-description-defect` / `cleared-card-defect` - Phase 3's reviewer cleared a defect of
  that text (V9's floor is waived for the first, P5/card-clear allowed for the second);
* `t03` / `t03-severe` - the site is in T03's findings; severe **on the description**, because the
  flag waives V9's floor, which protects the description: a severe finding on the card says nothing
  about the description's text.

Order: the pilot's sites (in the order given), then the cleared-defect sites, then T03, then the
rest, each group in `site_id` order.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import time
import unicodedata
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import write_stage as W  # noqa: E402

from phase4 import model4 as M  # noqa: E402
from phase4 import sources_stage as S1  # noqa: E402
from phase4 import subject_gate as SG  # noqa: E402
from pipeline.normalizers.dates import passes_date_cutoff  # noqa: E402
from pipeline.utils.geo import haversine_distance  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
RUNNER = REPO / "output" / "remediation" / "phase4_runner"
DEFAULT_ROWS = RUNNER / "S0_ROWS.jsonl"
DEFAULT_NAMES = RUNNER / "S0_ITEM_NAMES.json"
DEFAULT_PLAN = RUNNER / "PLAN4.jsonl"
DEFAULT_LEDGER = RUNNER / "LEDGER.jsonl"
DEFAULT_EVIDENCE = RUNNER / "plan_evidence"
DEFAULT_REFUSED = REPO / "output" / "remediation" / "logs" / "_write_dry" / "ALL_REFUSED.jsonl"
DEFAULT_T03 = REPO / "output" / "remediation" / "run_t03" / "findings.jsonl"
DEFAULT_GOLD = REPO / "output" / "remediation" / "gold_standard" / "sites.json"

#: The pre-March snapshot lane L compares against (plan section 15.3; `db_snapshots`, 5,005 rows).
SNAPSHOT_ID = "d4526691-28eb-4623-b9eb-daeabafb167e"
BATCH_SIZE = 15
BATCH_PREFIX = "p4"
#: Two sites sharing an item are a duplicate pair only this close (design S0).
DUPLICATE_KM = 2.0
#: wbgetentities answers every language's labels and aliases; ten items keep one answer far below
#: the 1 MiB cap (a chosen bound).
NAMES_PER_REQUEST = 10
#: The refusal rule whose rows are the reviewer-cleared text defects (Phase 3's writer).
CLEARED_RULE = W.RULE_REPORT_ONLY
TEXT_FIELDS = frozenset({"description", "card_description"})
T03_SEVERITIES = frozenset({"severe", "moderate", "minor"})

#: The keys of one row of `PLAN_SQL`, exactly.
ROW_KEYS = frozenset(
    {
        "id",
        "name",
        "country",
        "site_type",
        "period_start",
        "period_end",
        "lat",
        "lon",
        "description",
        "description_sha256",
        "raw_data",
        "raw_data_sha256",
        "source_url",
        "card",
        "card_sha256",
        "wikidata_qid",
        "enwiki_title",
        "names",
        "in_snapshot",
        "snapshot_description",
    }
)

#: The one production read (read-only: a single SELECT). The hashes are Postgres' own, the form of
#: the writer's in-database invariants; a scalar subquery that finds two ids of one kind for a site
#: fails the read instead of picking one.
PLAN_SQL = (
    "SELECT to_jsonb(t)::text FROM (SELECT u.id::text AS id, u.name, u.country, u.site_type, "
    "u.period_start, u.period_end, u.lat::float8 AS lat, u.lon::float8 AS lon, u.description, "
    "encode(sha256(convert_to(u.description, 'UTF8')), 'hex') AS description_sha256, "
    "u.raw_data, encode(sha256(convert_to(u.raw_data::text, 'UTF8')), 'hex') AS raw_data_sha256, "
    "u.source_url, c.card_description AS card, "
    "encode(sha256(convert_to(c.card_description, 'UTF8')), 'hex') AS card_sha256, "
    "(SELECT e.value FROM site_external_ids e WHERE e.site_id = u.id "
    "AND e.kind = 'wikidata_qid') AS wikidata_qid, "
    "(SELECT e.value FROM site_external_ids e WHERE e.site_id = u.id "
    "AND e.kind = 'enwiki_title') AS enwiki_title, "
    "COALESCE((SELECT array_agg(n.name ORDER BY n.name) FROM unified_site_names n "
    "WHERE n.site_id = u.id), '{}') AS names, "
    "EXISTS (SELECT 1 FROM snapshot_rows s "
    f"WHERE s.snapshot_id = '{SNAPSHOT_ID}' AND s.site_id = u.id) AS in_snapshot, "
    "(SELECT s.old_data->>'description' FROM snapshot_rows s "
    f"WHERE s.snapshot_id = '{SNAPSHOT_ID}' AND s.site_id = u.id) AS snapshot_description "
    "FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
    f"WHERE u.source_id = '{W.CURATED_SOURCE}' ORDER BY u.id) t;"
)


# ------------------------------------------------------------------------------------- inputs


def read_rows(runner: W.SqlRunner, *, host: str = W.SSH_HOST) -> list[dict[str, Any]]:
    """The production read: one `to_jsonb` object per curated site."""
    return W._json_rows(runner(PLAN_SQL, host=host))


def cleared_defects(rows: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """`{site_id: {text field}}` of the defects Phase 3's reviewer cleared (`report-only-field`)."""
    cleared: dict[str, set[str]] = {}
    for row in rows:
        if row.get("rule") != CLEARED_RULE:
            continue
        field_name = row.get("field")
        if field_name not in TEXT_FIELDS or not row.get("site_id"):
            raise R.InputError(f"a {CLEARED_RULE} row outside the two text fields: {row!r}")
        cleared.setdefault(str(row["site_id"]), set()).add(str(field_name))
    return cleared


def t03_findings(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """`{site_id: {text field: severity}}` of T03's findings, the worst severity per field."""
    rank = {"minor": 0, "moderate": 1, "severe": 2}
    found: dict[str, dict[str, str]] = {}
    for row in rows:
        site_id, field_name, severity = row.get("site_id"), row.get("field"), row.get("severity")
        if not site_id or field_name not in TEXT_FIELDS or severity not in T03_SEVERITIES:
            raise R.InputError(f"a T03 finding this plan cannot place: {row!r}")
        fields = found.setdefault(str(site_id), {})
        if field_name not in fields or rank[severity] > rank[fields[field_name]]:
            fields[str(field_name)] = str(severity)
    return found


def invalid_titles(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """The site ids whose stored `enwiki_title` carries a control character, sorted.

    MediaWiki refuses such a title (`invalid`), so S1 routes the site like a title Wikipedia does
    not have. The plan lists them for the data repair; it does not stop on them. Measured
    2026-09-23: one row, Petra's (a06a95d0-35b4-44bb-a0c1-716cbf972b19), stores its title, a newline
    and a second URL.
    """
    return sorted(
        str(row["id"])
        for row in rows
        if row["enwiki_title"] is not None
        and any(unicodedata.category(ch) == "Cc" for ch in row["enwiki_title"])
    )


# ------------------------------------------------------------------------------- the plan


def _check_row(row: Mapping[str, Any]) -> None:
    missing = sorted(ROW_KEYS - row.keys())
    unknown = sorted(row.keys() - ROW_KEYS)
    if missing or unknown:
        raise R.InputError(f"a plan row with missing keys {missing}, unknown keys {unknown}")
    names = row["names"]
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise R.InputError(f"{row['id']}: names is not a list of strings: {names!r}")


def _shared(rows: Sequence[Mapping[str, Any]], key: str) -> frozenset[str]:
    counts = collections.Counter(row[key] for row in rows if row[key] is not None)
    return frozenset(value for value, count in counts.items() if count > 1)


def _scope_pending(row: Mapping[str, Any]) -> bool:
    undated = row["period_start"] is None and row["period_end"] is None
    return undated or not passes_date_cutoff(dict(row))


def duplicate_pairs(
    rows: Sequence[Mapping[str, Any]],
    *,
    shared_qids: Collection[str],
    item_names: Mapping[str, Collection[str]],
) -> set[str]:
    """The site ids of every duplicate pair (design S0), from the shared items' names."""
    uncovered = sorted(set(shared_qids) - set(item_names))
    if uncovered:
        raise R.InputError(f"no labels or aliases for the shared items {uncovered}")
    by_qid: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if row["wikidata_qid"] in shared_qids:
            by_qid.setdefault(row["wikidata_qid"], []).append(row)
    paired: set[str] = set()
    for qid, members in sorted(by_qid.items()):
        names = {SG.fold(name) for name in item_names[qid]}
        named = [row for row in members if SG.fold(row["name"]) in names]
        for index, one in enumerate(named):
            for other in named[index + 1 :]:
                km = haversine_distance(one["lat"], one["lon"], other["lat"], other["lon"])
                if km <= DUPLICATE_KM:
                    paired.update({one["id"], other["id"]})
    return paired


def build_plan(
    rows: Sequence[Mapping[str, Any]],
    *,
    cleared: Mapping[str, set[str]],
    t03: Mapping[str, Mapping[str, str]],
    gold: Sequence[str],
    item_names: Mapping[str, Collection[str]],
) -> list[M.PlanSite]:
    """Every curated site as a `PlanSite`, flagged and in run order (module docstring)."""
    for row in rows:
        _check_row(row)
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise R.InputError("a site id occurs twice in the plan rows")
    known = set(ids)
    for what, wanted in (("cleared", cleared), ("t03", t03), ("pilot", gold)):
        unknown = sorted(set(wanted) - known)
        if unknown:
            raise R.InputError(f"{what} names sites that are not curated rows: {unknown[:10]}")
    if len(set(gold)) != len(gold):
        raise R.InputError("the pilot names a site twice")
    for site_id, fields in cleared.items():
        if not set(fields) <= TEXT_FIELDS:
            raise R.InputError(f"{site_id}: cleared fields {sorted(fields)} are not text fields")
    shared_qids = _shared(rows, "wikidata_qid")
    shared_titles = _shared(rows, "enwiki_title")
    pairs = duplicate_pairs(rows, shared_qids=shared_qids, item_names=item_names)
    sites = {
        row["id"]: _site(
            row,
            cleared=cleared.get(row["id"], set()),
            t03=t03.get(row["id"], {}),
            shared_qids=shared_qids,
            shared_titles=shared_titles,
            paired=row["id"] in pairs,
        )
        for row in rows
    }
    order = list(gold)
    placed = set(order)
    for wanted in (lambda s: s in cleared, lambda s: s in t03, lambda s: True):
        for site_id in sorted(sites):
            if site_id not in placed and wanted(site_id):
                order.append(site_id)
                placed.add(site_id)
    return [sites[site_id] for site_id in order]


def _site(
    row: Mapping[str, Any],
    *,
    cleared: set[str],
    t03: Mapping[str, str],
    shared_qids: frozenset[str],
    shared_titles: frozenset[str],
    paired: bool,
) -> M.PlanSite:
    flags: set[M.SiteFlag] = set()
    if _scope_pending(row):
        flags.add(M.SiteFlag.SCOPE_PENDING)
    if row["wikidata_qid"] in shared_qids:
        flags.add(M.SiteFlag.SHARED_QID)
    if row["enwiki_title"] in shared_titles:
        flags.add(M.SiteFlag.SHARED_TITLE)
    if paired:
        flags.add(M.SiteFlag.DUPLICATE_PAIR)
    if "description" in cleared:
        flags.add(M.SiteFlag.CLEARED_DESCRIPTION_DEFECT)
    if "card_description" in cleared:
        flags.add(M.SiteFlag.CLEARED_CARD_DEFECT)
    if t03:
        flags.add(M.SiteFlag.T03)
    if t03.get("description") == "severe":
        flags.add(M.SiteFlag.T03_SEVERE)
    aliases = sorted({name for name in row["names"] if name != row["name"]})
    return M.PlanSite(
        site_id=row["id"],
        name=row["name"],
        aliases=tuple(aliases),
        country=row["country"],
        site_type=row["site_type"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        lat=row["lat"],
        lon=row["lon"],
        description=row["description"],
        description_sha256=row["description_sha256"],
        raw_data=row["raw_data"],
        raw_data_sha256=row["raw_data_sha256"],
        card=row["card"],
        card_sha256=row["card_sha256"],
        source_url=row["source_url"],
        wikidata_qid=row["wikidata_qid"],
        enwiki_title=row["enwiki_title"],
        in_snapshot=row["in_snapshot"],
        snapshot_description=row["snapshot_description"],
        flags=frozenset(flags),
    )


def write_plan(path: Path, sites: Sequence[M.PlanSite]) -> None:
    """`PLAN4.jsonl`: one `phase3.run.Batch` per line, 15 sites each, ids `p4-NNNN`, in order."""
    records = [site.to_dict() for site in sites]
    R.write_batches(path, R.assign_batches(records, BATCH_SIZE, prefix=BATCH_PREFIX))


# ----------------------------------------------------------------------------- the item names


def item_names_url(qids: Sequence[str]) -> str:
    """The labels and aliases, in every language, of up to `NAMES_PER_REQUEST` items."""
    if not 1 <= len(qids) <= NAMES_PER_REQUEST:
        raise R.InputError(f"{len(qids)} ids: this request takes 1 to {NAMES_PER_REQUEST}")
    for qid in qids:
        if not F.QID_PATTERN.fullmatch(qid):
            raise R.InputError(f"{qid!r} is not a Q-number")
    return (
        F.WIKIDATA_ENDPOINT
        + "?"
        + urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(qids),
                "props": "labels|aliases",
                "format": "json",
            },
            quote_via=quote,
        )
    )


def parse_item_names(body: bytes, qids: Sequence[str]) -> dict[str, list[str]]:
    """`{qid: every label and alias}` for every asked item; an absent or missing item raises."""
    payload = json.loads(body.decode("utf-8"))
    entities = payload.get("entities") if isinstance(payload, dict) else None
    if not isinstance(entities, dict):
        raise R.InputError(f"the names answer carries no entities: {str(payload)[:200]}")
    names: dict[str, list[str]] = {}
    for qid in qids:
        entity = entities.get(qid)
        if not isinstance(entity, dict) or "missing" in entity:
            raise R.InputError(f"{qid}: the names answer has no such item")
        names[qid] = sorted(set(SG.entity_labels(entity)))
    return names


def fetch_item_names(
    qids: Collection[str],
    *,
    fetcher: F.Fetcher,
    evidence: Path,
    ledger: Path,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, list[str]]:
    """The shared items' names, every request ledgered and stored. Any failure raises: a plan
    built on a failed lookup would flag fewer duplicate pairs without saying so."""
    fetches = S1.Fetches(
        batch_id="plan",
        fetcher=fetcher,
        store=F.EvidenceStore(evidence),
        ledger=L.Ledger(ledger),
        sleep=sleep,
    )
    ordered = sorted(qids)
    names: dict[str, list[str]] = {}
    for start in range(0, len(ordered), NAMES_PER_REQUEST):
        chunk = ordered[start : start + NAMES_PER_REQUEST]
        digest = hashlib.sha256("|".join(chunk).encode("ascii")).hexdigest()[:12]
        stored = fetches.get(
            F.Target(
                site_id="plan",
                feature=f"s0.item_names.{digest}",
                url=item_names_url(chunk),
                reason="S0 duplicate pairs",
            )
        )
        if not stored.ok:
            raise R.InputError(f"the names of {chunk} could not be read: {stored.failure}")
        names.update(parse_item_names(stored.body or b"", chunk))
    return names


def shared_qids_of(rows: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    for row in rows:
        _check_row(row)
    return _shared(rows, "wikidata_qid")


# --------------------------------------------------------------------------------------- CLI


def _write_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8", newline="\n")


def cmd_read(args: argparse.Namespace, *, runner: W.SqlRunner = W.run_sql) -> int:
    rows = read_rows(runner, host=args.host)
    _write_rows(Path(args.out), rows)
    print(json.dumps({"out": str(args.out), "rows": len(rows)}, sort_keys=True))
    return 0


def cmd_names(args: argparse.Namespace, *, fetcher: F.Fetcher | None = None) -> int:
    rows = R.read_jsonl(Path(args.rows))
    qids = shared_qids_of(rows)
    if fetcher is None:
        with S1.open_fetcher(pacing_dir=Path(args.pacing_dir)) as live:
            names = fetch_item_names(
                qids, fetcher=live, evidence=Path(args.evidence), ledger=Path(args.ledger)
            )
    else:
        names = fetch_item_names(
            qids, fetcher=fetcher, evidence=Path(args.evidence), ledger=Path(args.ledger)
        )
    S1.write_json(Path(args.out), names)
    print(json.dumps({"out": str(args.out), "shared_items": len(names)}, sort_keys=True))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    rows = R.read_jsonl(Path(args.rows))
    names = json.loads(Path(args.names).read_text(encoding="utf-8"))
    sites = build_plan(
        rows,
        cleared=cleared_defects(R.read_jsonl(Path(args.refused))),
        t03=t03_findings(R.read_jsonl(Path(args.t03))),
        gold=R._gold_site_ids(Path(args.gold)),
        item_names=names,
    )
    out = Path(args.out)
    write_plan(out, sites)
    flags = collections.Counter(flag.value for site in sites for flag in site.flags)
    summary = {
        "batches": -(-len(sites) // BATCH_SIZE),
        "flags": dict(sorted(flags.items())),
        "out": str(out),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "invalid_titles": invalid_titles(rows),
        "sites": len(sites),
    }
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plan4", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    read = sub.add_parser("read", help="the one read-only production SELECT")
    read.add_argument("--out", default=str(DEFAULT_ROWS))
    read.add_argument("--host", default=W.SSH_HOST)
    read.set_defaults(handler=cmd_read)
    names = sub.add_parser("names", help="labels and aliases of the shared Wikidata items")
    names.add_argument("--rows", default=str(DEFAULT_ROWS))
    names.add_argument("--out", default=str(DEFAULT_NAMES))
    names.add_argument("--evidence", default=str(DEFAULT_EVIDENCE))
    names.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    names.add_argument("--pacing-dir", default=str(R.DEFAULT_PACING_DIR))
    names.set_defaults(handler=cmd_names)
    build = sub.add_parser("build", help="the plan, offline, from the read and the files")
    build.add_argument("--rows", default=str(DEFAULT_ROWS))
    build.add_argument("--names", default=str(DEFAULT_NAMES))
    build.add_argument("--refused", default=str(DEFAULT_REFUSED))
    build.add_argument("--t03", default=str(DEFAULT_T03))
    build.add_argument("--gold", default=str(DEFAULT_GOLD))
    build.add_argument("--out", default=str(DEFAULT_PLAN))
    build.set_defaults(handler=cmd_build)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one subcommand and print `STAGE_EXIT=<code>`: that line is what a caller reads."""
    # A cp1252 console dies on the first site name outside it (write_gate.py, measured
    # 2026-09-22); a stream without `reconfigure` (a test's capture) is already text.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        code = args.handler(args)
    except BaseException:
        print("STAGE_EXIT=1", flush=True)
        raise
    print(f"STAGE_EXIT={code}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
