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
            (`run_t03/findings.jsonl`) and the pilot's site ids - the design's pilot set
            (`--pilot PILOT.jsonl`, drawn by `phase4/pilot4.py`), or the 36 gold-standard sites
            (`--gold`, the default) - then `write_plan`: `PLAN4.jsonl`, batches of 15 named
            `p4-NNNN`. Its summary lists the stored titles MediaWiki refuses (`invalid_titles`)
            for the data repair. `build --pilot PILOT.jsonl --defect-scope` writes the mass run's
            plan instead: the plan's sites after the pilot's, only those of the owner's defect
            scope version 1, numbered after the pilot's batches (`write_scoped_plan`).
            `build --pilot PILOT.jsonl --scope-list <list> [--scope-list <list> ...] --after
            <plan> ... --first-batch N` writes the plan of the lists a later scope version added:
            their sites after the pilot's, less every site an earlier plan carries, in batches
            numbered from p4-N (`write_list_plan`). `--exclude FILE` leaves the named sites out
            (accounted, printed as a count and the file's sha256), `--take-deferred RUN_DIR` plans
            the sites that run deferred `revision-too-fresh` once their 48 h have passed although
            an `--after` plan carries them. A plan of a list version 3 added writes descriptions
            only (`scope4.DESCRIPTIONS_ONLY_LISTS`): its batches carry
            `scope4.DESCRIPTIONS_ONLY_MARK`.
* `read-march` - the one read-only production SELECT of scope version 3 (`MARCH_SQL`): per curated
            site its `scope_status`, its provenance lane, whether it has a card and whether a
            Phase-5 write of it is live. Written to `MARCH4_ROWS.jsonl`.
* `scope` - offline: the owner's defect scope (`phase4/scope4.py`) from the rows, Phase 3's
            refusals, from version 2 the orphan-citations lane's D1 listing (`--markers`) and from
            version 3 the March read (`--march`), written to the version's file (`SCOPE4.json`,
            `SCOPE4.v2.json`, `SCOPE4.v3.json`); each version's sha256 is pinned in `scope4`
            (`SCOPE_V1_SHA256`, `SCOPE_V2_SHA256`, `SCOPE_SHA256`). `--version 1` and `--version
            2` rebuild those versions byte for byte.
* `legacy` - offline: lane L's own plan (owner decision 2026-09-24, "Alle kennzeichnen") from a
            fresh `read` (`--out LEGACY4_ROWS.jsonl`): every curated site in site-id order, no flag
            derived, in batches of 15 marked `pass: phase4-legacy` and numbered from p4-1001
            (`legacy4.PLAN_MARK`, `legacy4.FIRST_BATCH`), written to `LEGACY4.jsonl`. The write
            gate plans lane L from it (`write_gate4.py --group L --legacy-plan`).

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
rest, each group in `site_id` order. **The pilot fills its own batches** (the last may be short) and
the rest starts a new one: the pilot runs its batches alone, and a batch shared with other sites
would put them into the pilot's model calls and its audit.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import json
import sys
import time
import unicodedata
import uuid
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import write_stage as W  # noqa: E402

from phase4 import legacy4 as L4  # noqa: E402 - lane L's own plan: its pass and numbering
from phase4 import model4 as M  # noqa: E402
from phase4 import revert4 as RV  # noqa: E402 - what "reverted" means in the journal
from phase4 import scope4 as S  # noqa: E402
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
#: The orphan-citations lane's listing (HUMAN_ONLY D9): scope version 2's D1 list reads it.
DEFAULT_MARKERS = REPO / "output" / "remediation" / "mechanical_citations" / "SKIPPED.jsonl"
DEFAULT_GOLD = REPO / "output" / "remediation" / "gold_standard" / "sites.json"
#: The design's pilot set, written by `phase4/pilot4.py` (one JSON object per site, in order).
DEFAULT_PILOT = RUNNER / "PILOT.jsonl"
#: Lane L's own read and plan (`read --out LEGACY4_ROWS.jsonl`, then `legacy`): a fresh read,
#: never S0's rows, whose descriptions and raw_data are the census snapshot's.
DEFAULT_LEGACY_ROWS = RUNNER / "LEGACY4_ROWS.jsonl"
DEFAULT_LEGACY_PLAN = RUNNER / "LEGACY4.jsonl"
#: Scope version 3's read (`read-march`): committed beside the scope file it was built into.
DEFAULT_MARCH = RUNNER / "MARCH4_ROWS.jsonl"

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

#: Scope version 3's one production read (read-only: a single SELECT), the keys of
#: `scope4.MARCH_ROW_KEYS`: a site's card is present when it is not empty, and a Phase-5 write of
#: it is live when a forward `phase5:` journal row of the site has no reversal of its own (revert4's
#: reading: key **and** stamp plus `-rollback`).
MARCH_SQL = (
    "SELECT to_jsonb(t)::text FROM (SELECT u.id::text AS id, u.scope_status, "
    f"u.raw_data -> {W._sql_text(M.PROVENANCE_KEY)} ->> 'lane' AS lane, "
    "(c.card_description IS NOT NULL AND btrim(c.card_description) <> '') AS card, "
    "EXISTS (SELECT 1 FROM remediation_change_log j WHERE j.site_id_ref = u.id "
    "AND j.run_stamp LIKE 'phase5:%' "
    f"AND j.run_stamp NOT LIKE {W._sql_text('%' + W.ROLLBACK_KEY_SUFFIX)} "
    f"AND NOT {RV._reversed('j')}) AS live_p5 "
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
    return plan_site(row, flags=frozenset(flags))


def plan_site(row: Mapping[str, Any], *, flags: frozenset[M.SiteFlag]) -> M.PlanSite:
    """One row of the read (`PLAN_SQL`) as a `PlanSite` with these flags: its old values as the
    read found them, and its other stored names as aliases."""
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
        flags=flags,
    )


def write_plan(path: Path, sites: Sequence[M.PlanSite], *, pilot: int) -> None:
    """`PLAN4.jsonl`: one `phase3.run.Batch` per line, 15 sites each, ids `p4-NNNN`, in order.

    The first `pilot` sites are the pilot's and fill their own batches, the last of them possibly
    short; the rest continue the numbering in a new batch (module docstring).
    """
    if not 0 <= pilot <= len(sites):
        raise R.InputError(f"a pilot of {pilot} sites is no leading part of {len(sites)} sites")
    records = [site.to_dict() for site in sites]
    head = R.assign_batches(records[:pilot], BATCH_SIZE, prefix=BATCH_PREFIX)
    tail = batches_after(records[pilot:], len(head))
    R.write_batches(path, [*head, *tail])


def batches_after(records: Sequence[Mapping[str, Any]], taken: int) -> list[R.Batch]:
    """`records` in batches of 15, numbered after the `taken` batches before them."""
    return [
        R.Batch(
            batch_id=f"{BATCH_PREFIX}-{batch.ordinal + taken:04d}",
            ordinal=batch.ordinal + taken,
            sites=batch.sites,
        )
        for batch in R.assign_batches(records, BATCH_SIZE, prefix=BATCH_PREFIX)
    ]


def write_scoped_plan(
    path: Path, sites: Sequence[M.PlanSite], *, pilot: int, scope: S.DefectScope
) -> list[M.PlanSite]:
    """The mass run's plan under the owner's decision of 2026-09-23: the plan's sites after the
    pilot's, in the plan's order (the design's: cleared defects, T03, the rest), only those in the
    defect scope, in batches of 15 numbered after the pilot's own batches. The pilot's sites are the
    pilot run's - written or held there - and are never asked again; a batch id is never the
    pilot's, because a journal stamp names its batch. Returns the plan's sites."""
    if not 0 < pilot <= len(sites):
        raise R.InputError(f"the mass run's plan follows a pilot: {pilot} of {len(sites)} sites")
    tail = [site for site in sites[pilot:] if site.site_id in scope]
    first = -(-pilot // BATCH_SIZE)
    R.write_batches(path, batches_after([site.to_dict() for site in tail], first))
    return tail


def legacy_block(curated: int) -> range:
    """The batch numbers lane L's own plan takes (`legacy4.FIRST_BATCH`, 15 sites a batch, every
    curated site - `write_legacy_plan`): p4-1001 .. p4-1334 for the 5,004 curated sites."""
    return range(L4.FIRST_BATCH, L4.FIRST_BATCH + -(-curated // BATCH_SIZE))


def write_list_plan(
    path: Path,
    sites: Sequence[M.PlanSite],
    *,
    pilot: int,
    scope: S.DefectScope,
    scope_lists: Sequence[str],
    earlier: Collection[str],
    taken: int,
    first_batch: int,
    excluded: Collection[str],
) -> list[M.PlanSite]:
    """The plan of the lists a later scope version added (owner orders 2026-09-25, HUMAN_ONLY D9, and
    2026-09-26, scope version 3): the plan's sites after the pilot's, in the plan's order, whose
    scope lists name one of `scope_lists` (their union), less every site an `earlier` plan carries -
    that run held or wrote it and never asks it again, and `verify_writes4.index_runs` refuses a
    site two runs carry - and less the `excluded` ones, in batches of 15 from `first_batch`.

    Every run writes into the one P4 apply root and a journal stamp names its batch
    (`phase4:p4-NNNN:chunk-NNNN`), so the block must lie past `taken` (the highest ordinal of the
    earlier plans) and outside lane L's (`legacy_block`, from p4-1001); the D9 plan took p4-0901.
    Every listed site is accounted for: the pilot's, an earlier plan's, excluded, or planned here.
    A plan of a list version 3 added writes descriptions only: its batches carry
    `scope4.DESCRIPTIONS_ONLY_MARK` (owner decisions 2026-09-26, O2 and O3). Returns the plan's
    sites."""
    if not scope_lists or len(set(scope_lists)) != len(scope_lists):
        raise R.InputError(f"--scope-list names each list once, at least one: {list(scope_lists)}")
    for scope_list in scope_lists:
        if scope_list not in S.VERSION_LISTS[scope.version]:
            raise R.InputError(f"scope version {scope.version} carries no list {scope_list!r}")
    if not 0 < pilot <= len(sites):
        raise R.InputError(f"a list plan follows a pilot: {pilot} of {len(sites)} sites")
    if taken >= first_batch:
        raise R.InputError(
            f"an earlier plan numbers up to {BATCH_PREFIX}-{taken:04d}: a list plan starts past "
            f"every plan it follows, not at {BATCH_PREFIX}-{first_batch:04d}"
        )
    planned = {site.site_id for site in sites}
    stray = sorted(set(excluded) - planned)
    if stray:
        raise R.InputError(
            f"--exclude names {len(stray)} site(s) that are no curated row: {stray[:3]}"
        )
    wanted = set(scope_lists)
    listed = {site_id for site_id, lists in scope.sites.items() if wanted & set(lists)}
    unplaced = sorted(listed - planned - set(earlier))
    if unplaced:
        raise R.InputError(
            f"{len(unplaced)} site(s) of {', '.join(scope_lists)} no plan accounts for (not a row "
            f"of this build, not an earlier plan's): {unplaced[:5]}"
        )
    tail = [
        site
        for site in sites[pilot:]
        if site.site_id in listed and site.site_id not in earlier and site.site_id not in excluded
    ]
    if not tail:
        raise R.InputError(f"no site of {', '.join(scope_lists)} is left to plan")
    block = range(first_batch, first_batch + -(-len(tail) // BATCH_SIZE))
    lane_l = legacy_block(len(sites))
    if block.start < lane_l.stop and lane_l.start < block.stop:
        raise R.InputError(
            f"the plan would number {BATCH_PREFIX}-{block.start:04d} .. "
            f"{BATCH_PREFIX}-{block.stop - 1:04d}, inside lane L's block {BATCH_PREFIX}-"
            f"{lane_l.start:04d} .. {BATCH_PREFIX}-{lane_l.stop - 1:04d}: a stamp would name two plans"
        )
    mark = S.DESCRIPTIONS_ONLY_MARK if wanted & set(S.DESCRIPTIONS_ONLY_LISTS) else None
    batches = batches_after([site.to_dict() for site in tail], first_batch - 1)
    R.write_batches(path, [dataclasses.replace(batch, pass_name=mark) for batch in batches])
    return tail


def read_excluded(path: Path) -> list[str]:
    """`--exclude`: one site id per line (blank lines aside), each a UUID, each once."""
    ids: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            uuid.UUID(text)
        except ValueError:
            raise R.InputError(f"{path}:{number}: {text!r} is not a site id") from None
        if text in ids:
            raise R.InputError(f"{path}:{number}: {text} is listed twice")
        ids.append(text)
    return ids


def pilot_site_ids(path: Path) -> list[str]:
    """The pilot's site ids in its order: one JSON object per line of `PILOT.jsonl`, each with a
    `site_id` (`phase4/pilot4.py` writes it). A line without one is refused, never skipped."""
    ids: list[str] = []
    for number, line in enumerate(R.read_jsonl(path), start=1):
        site_id = line.get("site_id")
        if not isinstance(site_id, str) or not site_id:
            raise R.InputError(f"{path}:{number}: a pilot line without a site id: {line!r}")
        ids.append(site_id)
    return ids


def legacy_sites(rows: Sequence[Mapping[str, Any]]) -> list[M.PlanSite]:
    """Lane L's population (owner decision 2026-09-24): every curated site of one production read
    (`PLAN_SQL`), as a `PlanSite` in site-id order. No flag is derived: flags order and steer Phase
    4's model stages, and lane L asks none of them."""
    for row in rows:
        _check_row(row)
    ids = [row["id"] for row in rows]
    if len(set(ids)) != len(ids):
        raise R.InputError("a site id occurs twice in the rows")
    return [plan_site(row, flags=frozenset()) for row in sorted(rows, key=lambda row: row["id"])]


def write_legacy_plan(path: Path, sites: Sequence[M.PlanSite]) -> None:
    """`LEGACY4.jsonl`: lane L's own plan - the sites in batches of 15, each marked with
    `legacy4.PLAN_MARK` and numbered from `legacy4.FIRST_BATCH` (p4-1001 ...)."""
    batches = batches_after([site.to_dict() for site in sites], L4.FIRST_BATCH - 1)
    R.write_batches(path, [dataclasses.replace(batch, pass_name=L4.PLAN_MARK) for batch in batches])


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


def read_march_rows(runner: W.SqlRunner, *, host: str = W.SSH_HOST) -> list[dict[str, Any]]:
    """Scope version 3's production read: one `to_jsonb` object per curated site (`MARCH_SQL`)."""
    return W._json_rows(runner(MARCH_SQL, host=host))


def cmd_read_march(args: argparse.Namespace, *, runner: W.SqlRunner = W.run_sql) -> int:
    rows = read_march_rows(runner, host=args.host)
    descriptions, cards = S.march_lists(rows)
    out = Path(args.out)
    _write_rows(out, rows)
    summary = {
        "out": str(out),
        "rows": len(rows),
        S.MARCH_DESCRIPTION: len(descriptions),
        S.MARCH_CARD: len(cards),
        "union": len(set(descriptions) | set(cards)),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    print(json.dumps(summary, sort_keys=True))
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
    if args.defect_scope and not args.pilot:
        raise R.InputError(
            "--defect-scope builds the mass run after its pilot: name it with --pilot"
        )
    if args.scope_list and (
        args.defect_scope or not args.pilot or not args.after or args.first_batch is None
    ):
        raise R.InputError(
            "--scope-list builds the plan of later lists after the pilot and the plans before it: "
            "name --pilot, every earlier plan with --after and the plan's --first-batch, and not "
            "--defect-scope"
        )
    if not args.scope_list and (args.first_batch is not None or args.exclude or args.take_deferred):
        raise R.InputError(
            "--first-batch, --exclude and --take-deferred shape a --scope-list plan; name the lists"
        )
    rows = R.read_jsonl(Path(args.rows))
    names = json.loads(Path(args.names).read_text(encoding="utf-8"))
    pilot = pilot_site_ids(Path(args.pilot)) if args.pilot else R._gold_site_ids(Path(args.gold))
    sites = build_plan(
        rows,
        cleared=cleared_defects(R.read_jsonl(Path(args.refused))),
        t03=t03_findings(R.read_jsonl(Path(args.t03))),
        gold=pilot,
        item_names=names,
    )
    out = Path(args.out)
    if args.scope_list:
        return _list_summary(out, sites, pilot=pilot, args=args, now=datetime.now(UTC))
    if args.defect_scope:
        return _scoped_summary(out, sites, pilot=pilot, pilot_path=args.pilot)
    write_plan(out, sites, pilot=len(pilot))
    flags = collections.Counter(flag.value for site in sites for flag in site.flags)
    pilot_batches = -(-len(pilot) // BATCH_SIZE)
    summary = {
        "batches": pilot_batches + -(-(len(sites) - len(pilot)) // BATCH_SIZE),
        "flags": dict(sorted(flags.items())),
        "out": str(out),
        "pilot": str(args.pilot or args.gold),
        "pilot_batches": pilot_batches,
        "pilot_sites": len(pilot),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "invalid_titles": invalid_titles(rows),
        "sites": len(sites),
    }
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def _scoped_summary(
    out: Path, sites: Sequence[M.PlanSite], *, pilot: Sequence[str], pilot_path: str
) -> int:
    # The mass run was planned and written under version 1: its plan is rebuilt from it byte for
    # byte, and a later version's list gets a plan of its own (`--scope-list`).
    scope = S.load_scope(1)
    tail = write_scoped_plan(out, sites, pilot=len(pilot), scope=scope)
    batches = R.read_jsonl(out)
    lists = collections.Counter(name for site in tail for name in scope.sites[site.site_id])
    summary = {
        "batches": len(batches),
        "first_batch": batches[0]["batch_id"] if batches else None,
        "flags": dict(sorted(collections.Counter(f.value for s in tail for f in s.flags).items())),
        "lists": dict(sorted(lists.items())),
        "out": str(out),
        "pilot": pilot_path,
        "pilot_batches": -(-len(pilot) // BATCH_SIZE),
        "pilot_sites": len(pilot),
        "pilot_sites_in_scope": sum(site_id in scope for site_id in pilot),
        "scope": scope.label,
        "scope_sites": len(scope.sites),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "sites": len(tail),
    }
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def taken_over(run_dirs: Sequence[str], *, now: datetime) -> dict[str, list[str]]:
    """`--take-deferred`: per run directory, the sites it deferred `revision-too-fresh` in their
    latest batch whose 48 h have passed (`mass4.ready_to_hand_over`, which refuses while one still
    waits or once the run re-queued one itself). A later plan takes them over: the run held them and
    wrote nothing of them, and `verify_writes4.index_runs` reads them from the run that writes
    them."""
    # mass4 imports this module; its re-queue reading is imported when a plan takes sites over.
    from phase4 import mass4

    return {
        run_dir: [item.site.site_id for item in mass4.ready_to_hand_over(Path(run_dir), now=now)]
        for run_dir in run_dirs
    }


def _list_summary(
    out: Path,
    sites: Sequence[M.PlanSite],
    *,
    pilot: Sequence[str],
    args: argparse.Namespace,
    now: datetime,
) -> int:
    scope = S.load_scope()
    earlier = [R.read_jsonl(Path(path)) for path in args.after]
    carried = {site["site_id"] for plan in earlier for batch in plan for site in batch["sites"]}
    taken = max((batch["ordinal"] for plan in earlier for batch in plan), default=0)
    handed = taken_over(args.take_deferred, now=now)
    handed_ids = {site_id for ids in handed.values() for site_id in ids}
    wanted = set(args.scope_list)
    listed = sorted(site_id for site_id, lists in scope.sites.items() if wanted & set(lists))
    unlisted = sorted(handed_ids - set(listed))
    if unlisted:
        raise R.InputError(
            f"{len(unlisted)} deferred site(s) to take over that no list of this plan names: "
            f"{unlisted[:3]}"
        )
    # A deferring run's other sites are that run's: without its plan among --after they would be
    # planned a second time, and the acceptance refuses a site two runs could have written.
    uncarried = sorted(handed_ids - carried)
    if uncarried:
        raise R.InputError(
            f"{len(uncarried)} deferred site(s) to take over that no --after plan carries: name "
            f"the plan the deferring run was driven from ({uncarried[:3]})"
        )
    exclude_path = Path(args.exclude) if args.exclude else None
    excluded = read_excluded(exclude_path) if exclude_path is not None else []
    tail = write_list_plan(
        out,
        sites,
        pilot=len(pilot),
        scope=scope,
        scope_lists=args.scope_list,
        earlier=carried - handed_ids,
        taken=taken,
        first_batch=args.first_batch,
        excluded=set(excluded),
    )
    batches = R.read_jsonl(out)
    planned = {site.site_id for site in tail}
    block = legacy_block(len(sites))
    summary = {
        "after": list(args.after),
        "batches": len(batches),
        "carried_by_earlier_plans": [s for s in listed if s in carried and s not in handed_ids],
        "excluded": None
        if exclude_path is None
        else {
            "file_sha256": hashlib.sha256(exclude_path.read_bytes()).hexdigest(),
            "sites": len(excluded),
            "listed": len(set(excluded) & set(listed)),
        },
        "first_batch": batches[0]["batch_id"],
        "flags": dict(sorted(collections.Counter(f.value for s in tail for f in s.flags).items())),
        "in_pilot": [site_id for site_id in listed if site_id in set(pilot)],
        "lane_l_block": [block.start, block.stop - 1],
        "last_batch": batches[-1]["batch_id"],
        "listed": len(listed),
        "lists": list(args.scope_list),
        "out": str(out),
        "pass": batches[0].get("pass"),
        "pilot": args.pilot,
        "scope": scope.label,
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "sites": len(tail),
        "taken_over": {
            run_dir: {"deferred": len(ids), "planned": sum(i in planned for i in ids)}
            for run_dir, ids in handed.items()
        },
    }
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def cmd_scope(args: argparse.Namespace) -> int:
    """The scope file of `--version` (`phase4/scope4.py`): from the S0 rows and Phase 3's refusals,
    from version 2 on the orphan-citations lane's D1 listing (`--markers`), from version 3 on the
    March read (`--march`, `read-march`)."""
    rows_path, refused_path = Path(args.rows), Path(args.refused)
    rows = R.read_jsonl(rows_path)
    for row in rows:
        _check_row(row)
    paths = [rows_path, refused_path]
    markers: list[str] = []
    march: list[dict[str, Any]] = []
    carried = S.VERSION_LISTS.get(args.version, ())
    if S.D1_MARKER_WITHOUT_ENTRY in carried:
        markers_path = Path(args.markers)
        markers = S.listed_markers(R.read_jsonl(markers_path))
        paths.append(markers_path)
    if S.MARCH_DESCRIPTION in carried:
        march_path = Path(args.march)
        march = R.read_jsonl(march_path)
        paths.append(march_path)
    inputs = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    payload = S.scope_payload(
        rows,
        cleared_defects(R.read_jsonl(refused_path)),
        inputs=inputs,
        version=args.version,
        markers=markers,
        march_rows=march,
    )
    data = S.render_scope(payload)
    out = Path(args.out) if args.out else S.pinned_file(args.version)[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    summary = {
        "lists": payload["lists"],
        "out": str(out),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sites": len(payload["sites"]),
        "unclaimed": payload["unclaimed"],
        "version": payload["version"],
    }
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def cmd_legacy(args: argparse.Namespace) -> int:
    """`LEGACY4.jsonl`, lane L's own plan, from a fresh read (`read --out LEGACY4_ROWS.jsonl`)."""
    rows_path, out = Path(args.rows), Path(args.out)
    sites = legacy_sites(R.read_jsonl(rows_path))
    write_legacy_plan(out, sites)
    batches = R.read_jsonl(out)
    lanes_at_read = collections.Counter(
        str((site.raw_data or {}).get(M.PROVENANCE_KEY, {}).get("lane", "none")) for site in sites
    )
    summary = {
        "batches": len(batches),
        "first_batch": batches[0]["batch_id"] if batches else None,
        "last_batch": batches[-1]["batch_id"] if batches else None,
        "out": str(out),
        "provenance_at_read": dict(sorted(lanes_at_read.items())),
        "rows": str(rows_path),
        "rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
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
    march = sub.add_parser("read-march", help="scope version 3's one read-only production SELECT")
    march.add_argument("--out", default=str(DEFAULT_MARCH))
    march.add_argument("--host", default=W.SSH_HOST)
    march.set_defaults(handler=cmd_read_march)
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
    pilot = build.add_mutually_exclusive_group()
    pilot.add_argument("--gold", default=str(DEFAULT_GOLD), help="the pilot: the gold standard")
    pilot.add_argument("--pilot", default=None, help="the pilot: PILOT.jsonl (phase4/pilot4.py)")
    build.add_argument("--out", default=str(DEFAULT_PLAN))
    build.add_argument(
        "--defect-scope",
        action="store_true",
        help="the mass run's plan: the owner's defect scope v1 after the pilot (needs --pilot)",
    )
    build.add_argument(
        "--scope-list",
        action="append",
        default=[],
        help="a list of the current scope (repeatable: the union); needs --pilot, --after and "
        "--first-batch",
    )
    build.add_argument(
        "--after",
        action="append",
        default=[],
        help="an earlier plan (repeatable): its sites are never planned again by --scope-list",
    )
    build.add_argument(
        "--first-batch",
        type=int,
        default=None,
        help="--scope-list: the plan's first batch number, past every --after plan and outside "
        "lane L's block (the D9 plan: 901)",
    )
    build.add_argument(
        "--exclude",
        default=None,
        help="--scope-list: a file of site ids (one per line) left out of the plan",
    )
    build.add_argument(
        "--take-deferred",
        action="append",
        default=[],
        metavar="RUN_DIR",
        help="--scope-list: plan the sites this run deferred revision-too-fresh, once ready",
    )
    build.set_defaults(handler=cmd_build)
    scope = sub.add_parser("scope", help="the owner's defect scope of one version, offline")
    scope.add_argument("--rows", default=str(DEFAULT_ROWS))
    scope.add_argument("--refused", default=str(DEFAULT_REFUSED))
    scope.add_argument("--markers", default=str(DEFAULT_MARKERS))
    scope.add_argument("--march", default=str(DEFAULT_MARCH), help="version 3: read-march's rows")
    scope.add_argument("--version", type=int, default=S.SCOPE_VERSION)
    scope.add_argument("--out", default=None, help="default: the version's pinned file")
    scope.set_defaults(handler=cmd_scope)
    legacy = sub.add_parser("legacy", help="lane L's own plan over every curated site, offline")
    legacy.add_argument("--rows", default=str(DEFAULT_LEGACY_ROWS))
    legacy.add_argument("--out", default=str(DEFAULT_LEGACY_PLAN))
    legacy.set_defaults(handler=cmd_legacy)
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
