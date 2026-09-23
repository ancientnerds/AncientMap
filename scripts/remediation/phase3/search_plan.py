"""The search lane's plan, its prepared batches, and the evidence-budget dry run. All offline.

Block A3, work item W6 of `output/remediation/logs/remaining_map_2026-09-22.json`: rerun the finder
on the (site, field) pairs the mass run could not decide, and nothing else, in a run directory of
their own.

**What is selected** (`build_search_plan`), read from the mass run's own files and nothing else:

* every finder answer under `<source>/batch-*/answers/` whose verdict, read with the pipeline's own
  `discover_stage.parse_answer`, is `UNVERIFIABLE` - restricted to a scope: `writable` (`period_start`,
  `site_type`, `country`: the columns the writer may change), `text` (`description`,
  `card_description`: report-only) or `all`;
* in the writable scope, also every row of the write plan (`ALL_ROWS.jsonl`) that was **not
  written**: the 72 rows held by hand (`HOLDS.jsonl`) and the rows `write_gate.py`'s country-boundary
  check stopped. Which rows were written is the production journal's answer, exported read-only into
  a key file. These fields are re-examined with the new evidence: the rerun buys a fresh answer in a
  fresh answer store, and the old proposal travels along under `rerun_unwritten` only so that
  `review_stage` can refuse a rerun answer that repeats it (B7/B8: that proposal is not written);
* minus every rerun field whose value production no longer holds: a read-only export of
  production's `country`, `site_type` and `period_start` (`read_current_values`) is compared with
  the snapshot's stored value, and a field another lane has changed since is left out and listed -
  the finder would judge a value that is no longer there, and the writer's pre-flight would refuse
  the row anyway.

**What a plan line is**: one batch per mass batch that holds a selected site, `batch_id`
`<prefix>-NNNN` with the mass batch's own number (so `srch-0011` is `batch-0011`'s rerun and the
journal stamps `phase3:srch-0011:chunk-NNNN` cannot collide with the 428 `phase3:batch-*` stamps
already in production), `pass: "discover"`, and the site records copied **verbatim** from the mass
batch's `input.json` - all five findings, name, qid - plus `rerun_fields` (what is asked again),
`search_fields` (what a MiniMax search is bought for: here the same fields, since every field this
lane reruns is rerun *because* the search adds evidence; `search_evidence.search_fields` requires it
to be a subset of `rerun_fields`), `rerun_why` (why, per field), `rerun_unwritten` (the proposals the mass lane did not write, per
field; `{}` for none), `query_values` (production's value of every field a query reads -
`search_stage.SLOT_FIELDS` - because the snapshot is older than the corrections production holds)
and `source_batch`. The batch names the run directory it came from in `source_run_dir`.

**Why a new run directory**: `model_stage.judge_site` returns an answer already on disk without asking
(measured, `AUDIT_LOG.md`: a changed question written to the same key reuses the recorded answer), so
a rerun inside `runs/mass` would silently re-read the old `UNVERIFIABLE`. `prepare_search_batch`
therefore copies the source batch's evidence files and `fetch.json` into the new batch directory,
byte-identical, and the mass run is only ever read.

**The budget dry run** (`budget_report`) answers one question before any search is bought: how many
rerun sites could the added search hits push over `model_stage.MAX_EVIDENCE_CHARS`? A site over the
bound buys no call at all (`discover_stage.plan_site` records its rerun fields unverifiable), so a
search budget that pushes many sites over would turn money into the same verdict. The per-hit size is
a parameter, not a measurement: nothing in the repository has measured a MiniMax snippet yet.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import discover_stage as DS  # noqa: E402  - the pipeline's own answer parser
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import model as M  # noqa: E402  - which fields are report-only
from phase3 import model_stage as MS  # noqa: E402  - the evidence and its bound
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import search_stage as SS  # noqa: E402  - which fields a query reads, the name rule
from phase3.run import DISCOVER_PASS, InputError, read_jsonl  # noqa: E402
from phase3.snapshot_plan import DISCOVER_FIELDS  # noqa: E402

#: The fields of each scope, in `DISCOVER_FIELDS` order. `writable` is what the writer may change;
#: `text` is report-only (`model.REPORT_ONLY_FIELDS`).
SCOPES: dict[str, tuple[str, ...]] = {
    "writable": tuple(f for f in DISCOVER_FIELDS if f not in M.REPORT_ONLY_FIELDS),
    "text": tuple(f for f in DISCOVER_FIELDS if f in M.REPORT_ONLY_FIELDS),
    "all": DISCOVER_FIELDS,
}

#: A mass batch directory: `batch-NNNN`, the number the search batch keeps.
SOURCE_BATCH_RE = re.compile(r"batch-(\d{4})")

#: A search batch prefix: lowercase letters, and never `batch`, whose stamps production already has.
PREFIX_RE = re.compile(r"[a-z]{2,8}")

#: The keys this plan adds to a copied site record. A source record that already carries one was not
#: produced by the mass run, and planning from it would stack one rerun on another.
ADDED_SITE_KEYS = (
    SE.RERUN_FIELDS_KEY,
    SE.SEARCH_FIELDS_KEY,
    SE.RERUN_WHY_KEY,
    SE.RERUN_UNWRITTEN_KEY,
    SE.QUERY_VALUES_KEY,
    SE.SOURCE_BATCH_KEY,
)

#: The columns the production export carries (`read_current_values`): the writable fields. Every
#: field a query reads is one of them.
CURRENT_VALUE_FIELDS: tuple[str, ...] = SCOPES["writable"]
if not set(SS.SLOT_FIELDS) <= set(CURRENT_VALUE_FIELDS):
    raise InputError(f"a query reads {SS.SLOT_FIELDS}, the export carries {CURRENT_VALUE_FIELDS}")

#: The read-only export `read_current_values` expects, one JSON object per line.
CURRENT_VALUES_SQL = (
    "SELECT json_build_object('site_id', id, 'country', country, 'site_type', site_type, "
    "'period_start', period_start)::text FROM unified_sites WHERE source_id='ancient_nerds' "
    "ORDER BY id"
)

WHY_UNVERIFIABLE = "the mass run's finder answered UNVERIFIABLE"
WHY_HELD = "planned write held by hand, not written: {reason}"
WHY_GATE = (
    "planned write not written and not held: stopped by write_gate.py's country-boundary check; "
    "re-examined with new evidence, never written from the old proposal"
)


@dataclass(frozen=True)
class SourceBatch:
    """One mass batch: its id, its number, its directory and its parsed `input.json`."""

    batch_id: str
    number: int
    root: Path
    batch: dict[str, Any]

    @property
    def sites(self) -> list[dict[str, Any]]:
        return list(self.batch["sites"])


def read_source_batches(source_run_dir: Path) -> list[SourceBatch]:
    """Every `batch-NNNN` directory of the source run, in number order, with its input."""
    if not source_run_dir.is_dir():
        raise InputError(f"{source_run_dir} is not a run directory")
    batches: list[SourceBatch] = []
    for root in sorted(p for p in source_run_dir.iterdir() if p.is_dir()):
        match = SOURCE_BATCH_RE.fullmatch(root.name)
        if match is None:
            continue
        records = read_jsonl(root / "input.json")
        if len(records) != 1 or records[0].get("batch_id") != root.name:
            raise InputError(f"{root}/input.json does not hold exactly batch {root.name}")
        batch = records[0]
        if batch.get("pass") != DISCOVER_PASS or not isinstance(batch.get("sites"), list):
            raise InputError(f"{root}/input.json is not a discover batch with sites")
        batches.append(SourceBatch(root.name, int(match.group(1)), root, batch))
    if not batches:
        raise InputError(f"{source_run_dir} holds no batch-NNNN directory")
    return batches


def unverifiable_fields(source: SourceBatch) -> dict[str, list[str]]:
    """`site_id -> [field]` whose finder answer in this batch reads `UNVERIFIABLE`.

    The answer's file name is the record: `<site_id>%2F<field>.txt`. A file for a site the batch does
    not hold, or for a field the pass never asks, raises - an answer nobody can place is not evidence.
    """
    site_ids = {str(site.get("site_id") or "") for site in source.sites}
    found: dict[str, list[str]] = {}
    for path in sorted((source.root / "answers").glob("*.txt")):
        site_id, _, field_name = unquote(path.stem).partition("/")
        if site_id not in site_ids or field_name not in DISCOVER_FIELDS:
            raise InputError(f"{path}: an answer for a site or field batch {source.batch_id} lacks")
        verdict = DS.parse_answer(path.read_text(encoding="utf-8")).verdict
        if verdict == "UNVERIFIABLE":
            found.setdefault(site_id, []).append(field_name)
    return found


def _read_lines(path: Path) -> list[str]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    return [line for line in lines if line]


@dataclass(frozen=True)
class UnwrittenRow:
    """A planned write of the mass lane that was not written, as the search plan needs it."""

    batch_id: str
    why: str
    kind: str
    change_key: str
    old_value: str | None
    proposed: str


def read_current_values(path: Path) -> dict[str, dict[str, Any]]:
    """`site_id -> {field: production's value}` from the read-only export (`CURRENT_VALUES_SQL`).

    Every line is one object with exactly `site_id` and the `CURRENT_VALUE_FIELDS`; a site twice,
    another key or a missing one raises - a partial export must not read as "nothing changed".
    """
    values: dict[str, dict[str, Any]] = {}
    wanted = {"site_id", *CURRENT_VALUE_FIELDS}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or set(row) != wanted:
            raise InputError(
                f"{path}:{number}: not an object of exactly {sorted(wanted)}: {line!r}"
            )
        site_id = str(row["site_id"])
        if site_id in values:
            raise InputError(f"{path}:{number}: site {site_id} is exported twice")
        values[site_id] = {name: row[name] for name in CURRENT_VALUE_FIELDS}
    if not values:
        raise InputError(f"{path}: the export of production's values is empty")
    return values


def unwritten_rows(
    *, all_rows: Path, written_keys: Path, holds: Path | None
) -> dict[tuple[str, str], UnwrittenRow]:
    """`(site_id, column) -> UnwrittenRow` for every planned row that was not written.

    `written_keys` holds one `change_key` per line - the production journal's
    `phase3:batch-%` keys, exported read-only. Every written key must be a planned row, every hold
    must be a planned row that was not written, and one (site, column) cannot be planned twice: any
    disagreement between the three files raises instead of being reconciled here.
    """
    rows = read_jsonl(all_rows)
    written = set(_read_lines(written_keys))
    held: dict[str, str] = {}
    if holds is not None:
        for record in read_jsonl(holds):
            held[str(record["change_key"])] = str(record["hold_reason"])
    keys = {str(row["change_key"]) for row in rows}
    if written - keys:
        raise InputError(
            f"{written_keys}: {len(written - keys)} written key(s) are not planned rows"
        )
    if set(held) - keys:
        raise InputError(f"{holds}: {len(set(held) - keys)} hold(s) are not planned rows")
    if set(held) & written:
        raise InputError(f"{holds}: {len(set(held) & written)} hold(s) were written after all")
    unwritten: dict[tuple[str, str], UnwrittenRow] = {}
    for row in rows:
        key = str(row["change_key"])
        if key in written:
            continue
        pair = (str(row["site_id"]), str(row["column"]))
        if pair in unwritten:
            raise InputError(f"{all_rows}: {pair} is planned twice")
        proposed = row.get("new_value")
        old_value = row.get("old_value")
        if not isinstance(proposed, str) or not proposed.strip():
            raise InputError(f"{all_rows}: {pair} carries no proposed new_value: {proposed!r}")
        if old_value is not None and not isinstance(old_value, str):
            raise InputError(f"{all_rows}: {pair} carries old_value {old_value!r}, not text")
        unwritten[pair] = UnwrittenRow(
            batch_id=str(row["batch_id"]),
            why=WHY_HELD.format(reason=held[key]) if key in held else WHY_GATE,
            kind="held" if key in held else "write_gate",
            change_key=key,
            old_value=old_value,
            proposed=proposed,
        )
    return unwritten


def _why_class(why: str) -> str:
    """The reason a field is rerun, as one of three words - for the plan's own counts."""
    if why == WHY_UNVERIFIABLE:
        return "unverifiable"
    if why == WHY_GATE:
        return "write_gate"
    if why.startswith(WHY_HELD.split("{", 1)[0]):
        return "held"
    raise InputError(f"a rerun reason this plan does not write: {why!r}")


def _search_site(
    site: Mapping[str, Any],
    *,
    fields: Mapping[str, str],
    unwritten: Mapping[str, UnwrittenRow],
    production: Mapping[str, Any],
    source_batch: str,
) -> dict[str, Any]:
    """The mass record verbatim, plus what is rerun and searched for and why, the proposals that were
    not written, the values a query reads, and where the record came from."""
    site_id = str(site.get("site_id") or "")
    present = [key for key in ADDED_SITE_KEYS if key in site]
    if present:
        raise InputError(f"{site_id}: the source record already carries {present}")
    record = dict(site)
    rerun = [name for name in DISCOVER_FIELDS if name in fields]
    record[SE.RERUN_FIELDS_KEY] = rerun
    record[SE.SEARCH_FIELDS_KEY] = list(rerun)
    record[SE.RERUN_WHY_KEY] = {name: fields[name] for name in rerun}
    record[SE.RERUN_UNWRITTEN_KEY] = {
        name: {"change_key": row.change_key, "kind": row.kind, "proposed": row.proposed}
        for name, row in unwritten.items()
        if name in rerun
    }
    record[SE.QUERY_VALUES_KEY] = {name: production[name] for name in SS.SLOT_FIELDS}
    record[SE.SOURCE_BATCH_KEY] = source_batch
    return record


@dataclass
class SearchPlan:
    """The plan's lines and the counts a human checks them against.

    `changed_in_production` lists the selected fields left out because production no longer holds
    the snapshot's value (see the module docstring).
    """

    batches: list[dict[str, Any]]
    changed_in_production: list[dict[str, Any]] = field(default_factory=list)

    def text(self) -> str:
        return "".join(
            json.dumps(batch, ensure_ascii=False, sort_keys=True) + "\n" for batch in self.batches
        )

    def summary(self) -> dict[str, Any]:
        sites = [site for batch in self.batches for site in batch["sites"]]
        by_field: Counter[str] = Counter()
        by_why: Counter[str] = Counter()
        for site in sites:
            for name, why in site["rerun_why"].items():
                by_field[name] += 1
                by_why[_why_class(why)] += 1
        carried: Counter[str] = Counter(
            name for site in sites for name in SS.carried_by_queries(site)
        )
        return {
            "batches": len(self.batches),
            "changed_in_production": self.changed_in_production,
            "fields": sum(by_field.values()),
            "fields_by_field": dict(sorted(by_field.items())),
            "fields_by_reason": dict(sorted(by_why.items())),
            # Sites whose name or fixed query wording still carries a value under test, per field:
            # the one place `build_query` cannot take it out (`search_stage.query_carries`).
            "queries_still_carry_the_value_under_test": dict(sorted(carried.items())),
            "searches": sum(len(SE.search_slots(site)) for site in sites),
            "sites": len(sites),
        }


def build_search_plan(
    *,
    source_run_dir: Path,
    scope: str,
    prefix: str,
    current: Mapping[str, Mapping[str, Any]],
    site_ids: Iterable[str] | None = None,
    extra: Mapping[tuple[str, str], UnwrittenRow] | None = None,
) -> SearchPlan:
    """One search batch per mass batch that holds a selected (site, field). See the module docstring.

    `current` is `read_current_values`'s result: production's values, which every planned site must
    have. `extra` is `unwritten_rows`'s result; it is only meaningful in the writable scope, every
    one of its rows must land on a site of the batch it names, and its `old_value` must be the
    snapshot's stored value, or the build raises.
    """
    if scope not in SCOPES:
        raise InputError(f"scope {scope!r} is not one of {sorted(SCOPES)}")
    if not PREFIX_RE.fullmatch(prefix) or prefix == "batch":
        raise InputError(
            f"prefix {prefix!r}: two to eight lowercase letters, and never 'batch' - the mass run's "
            "batch ids already carry production journal stamps"
        )
    extra = dict(extra or {})
    unknown = sorted({column for _, column in extra} - set(SCOPES[scope]))
    if unknown:
        raise InputError(f"unwritten rows on {unknown} do not belong to the {scope!r} scope")
    wanted = None if site_ids is None else set(site_ids)
    source_root = source_run_dir.resolve()
    placed: set[tuple[str, str]] = set()
    seen_sites: set[str] = set()
    changed: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    for source in read_source_batches(source_run_dir):
        found = unverifiable_fields(source)
        sites: list[dict[str, Any]] = []
        for site in source.sites:
            site_id = str(site.get("site_id") or "")
            if wanted is not None and site_id not in wanted:
                continue
            seen_sites.add(site_id)
            fields = {
                name: WHY_UNVERIFIABLE for name in found.get(site_id, []) if name in SCOPES[scope]
            }
            unwritten: dict[str, UnwrittenRow] = {}
            for name in SCOPES[scope]:
                row = extra.get((site_id, name))
                if row is None:
                    continue
                if row.batch_id != source.batch_id:
                    raise InputError(
                        f"{site_id}/{name}: the write plan puts it in {row.batch_id}, the run in "
                        f"{source.batch_id}"
                    )
                if name in fields:
                    raise InputError(f"{site_id}/{name} is both UNVERIFIABLE and a planned write")
                stored = DS.field_finding(site, name).get("current_value")
                if row.old_value != (None if stored is None else str(stored)):
                    raise InputError(
                        f"{site_id}/{name}: the write plan's old value {row.old_value!r} is not the "
                        f"snapshot's stored {stored!r}"
                    )
                fields[name] = row.why
                unwritten[name] = row
                placed.add((site_id, name))
            if not fields:
                continue
            production = current.get(site_id)
            if production is None:
                raise InputError(f"{site_id}: the export of production's values lacks this site")
            for name in [n for n in fields if n in CURRENT_VALUE_FIELDS]:
                stored = DS.field_finding(site, name).get("current_value")
                if production[name] != stored:
                    changed.append(
                        {
                            "field": name,
                            "production": production[name],
                            "site_id": site_id,
                            "snapshot": stored,
                        }
                    )
                    del fields[name]
            if fields:
                sites.append(
                    _search_site(
                        site,
                        fields=fields,
                        unwritten=unwritten,
                        production=production,
                        source_batch=source.batch_id,
                    )
                )
        if sites:
            batches.append(
                {
                    "batch_id": f"{prefix}-{source.number:04d}",
                    "ordinal": source.number,
                    "pass": DISCOVER_PASS,
                    "sites": sites,
                    "source_run_dir": source_root.as_posix(),
                }
            )
    if wanted is not None and wanted - seen_sites:
        missing = sorted(wanted - seen_sites)
        raise InputError(f"{len(missing)} selected site(s) are in no source batch: {missing[:5]}")
    stray = sorted(pair for pair in set(extra) - placed if wanted is None or pair[0] in wanted)
    if stray:
        raise InputError(f"{len(stray)} unwritten row(s) found no site in the run: {stray[:5]}")
    if not batches:
        raise InputError(f"the {scope!r} scope selects nothing in {source_run_dir}")
    return SearchPlan(batches=batches, changed_in_production=changed)


def write_plan(path: Path, plan: SearchPlan) -> str:
    """Write the plan (sorted keys, LF, no timestamp) and return its sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = plan.text()
    path.write_text(body, encoding="utf-8", newline="\n")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ── prepare: the new batch directory gets the source batch's evidence ─────────────────────────────


def _source_of(batch: Mapping[str, Any]) -> tuple[Path, str]:
    """The source run directory and the one mass batch every site of this batch comes from."""
    batch_id = str(batch.get("batch_id") or "")
    root = batch.get("source_run_dir")
    if not isinstance(root, str) or not root:
        raise InputError(f"{batch_id}: a search batch names its source_run_dir")
    sources = {str(site.get("source_batch") or "") for site in batch.get("sites") or []}
    if len(sources) != 1 or "" in sources:
        raise InputError(f"{batch_id}: its sites name {sorted(sources)}, not one source batch")
    return Path(root), sources.pop()


def _copy_bytes(src: Path, dst: Path) -> bool:
    """Copy `src` to `dst` byte for byte, under the evidence store's own write rule."""
    return F.write_once(dst, src.read_bytes(), source=str(src))


def prepare_search_batch(batch: Mapping[str, Any], batch_dir: Path) -> dict[str, int]:
    """Copy the source batch's `fetch.json` and each selected site's evidence into `batch_dir`.

    Byte-identical copies, idempotent on a re-run, and the source is only read. Each site record must
    still equal the source batch's own record (the plan copied it verbatim), and every fetch target of
    a site must be on disk in the source or recorded there as failed - a hole in the source record is
    refused here rather than discovered by the judge.
    """
    source_run_dir, source_batch = _source_of(batch)
    source_dir = source_run_dir / source_batch
    records = read_jsonl(source_dir / "input.json")
    if len(records) != 1 or records[0].get("batch_id") != source_batch:
        raise InputError(f"{source_dir}/input.json does not hold exactly batch {source_batch}")
    by_id = {str(site.get("site_id") or ""): site for site in records[0]["sites"]}
    fetch_json = source_dir / "fetch.json"
    failures = MS.read_fetch_failures(fetch_json)
    source_store = F.EvidenceStore(source_dir / "evidence")
    store = F.EvidenceStore(batch_dir / "evidence")
    copied = kept = 0
    for site in batch["sites"]:
        site_id = str(site["site_id"])
        original = {key: value for key, value in site.items() if key not in ADDED_SITE_KEYS}
        if by_id.get(site_id) != original:
            raise InputError(f"{site_id}: the record differs from {source_dir}/input.json")
        for target in F.targets_for_site(site):
            src = source_store.path_for(site_id, target.feature)
            if not src.exists():
                if target.feature not in failures.get(site_id, {}):
                    raise InputError(f"{src} is missing and {fetch_json} records no failure")
                continue
            if _copy_bytes(src, store.path_for(site_id, target.feature)):
                copied += 1
            else:
                kept += 1
    _copy_bytes(fetch_json, batch_dir / "fetch.json")
    return {"evidence_copied": copied, "evidence_already_there": kept}


# ── the budget dry run ────────────────────────────────────────────────────────────────────────────


def _site_evidence_chars(site: Mapping[str, Any], batch_dir: Path) -> int:
    """The site's evidence as the judge would count it today: `evidence_excerpts` with no search."""
    plain = {key: value for key, value in site.items() if key not in ADDED_SITE_KEYS}
    failures = MS.read_fetch_failures(batch_dir / "fetch.json")
    excerpts = MS.evidence_excerpts(
        site_id=str(site["site_id"]),
        site=plain,
        store=F.EvidenceStore(batch_dir / "evidence"),
        failures=failures.get(str(site["site_id"])),
    )
    return sum(excerpt.chars for excerpt in excerpts)


def budget_report(
    batches: Sequence[Mapping[str, Any]], *, hits_per_search: int, chars_per_hit: int
) -> dict[str, Any]:
    """How many sites the added hits could push over `MAX_EVIDENCE_CHARS`. No network, no writes.

    Each site's evidence is counted from its source batch through `model_stage.evidence_excerpts`
    (the judge's own count), and the search adds `slots x hits_per_search x chars_per_hit` - an upper
    bound, since hits shared between searches are merged into one excerpt.
    """
    if hits_per_search < 1 or chars_per_hit < 1:
        raise InputError("hits per search and characters per hit must both be positive")
    bound = MS.MAX_EVIDENCE_CHARS
    rows: list[tuple[int, int]] = []
    for batch in batches:
        source_run_dir, source_batch = _source_of(batch)
        for site in batch["sites"]:
            base = _site_evidence_chars(site, source_run_dir / source_batch)
            rows.append((base, len(SE.search_slots(site))))
    over_already = sum(1 for base, _ in rows if base > bound)
    added = [slots * hits_per_search * chars_per_hit for _, slots in rows]
    pushed = sum(
        1 for (base, _), plus in zip(rows, added, strict=True) if base <= bound < base + plus
    )
    fits = [(bound - base) // (slots * chars_per_hit) for base, slots in rows if base <= bound]
    fits.sort()
    return {
        "bound_chars": bound,
        "chars_per_hit": chars_per_hit,
        "hits_per_search": hits_per_search,
        "sites": len(rows),
        "sites_over_the_bound_already": over_already,
        "sites_pushed_over_the_bound": pushed,
        "sites_staying_under": len(rows) - over_already - pushed,
        "searches": sum(slots for _, slots in rows),
        "evidence_chars_max": max(base for base, _ in rows),
        "evidence_chars_median": sorted(base for base, _ in rows)[len(rows) // 2],
        "hits_per_search_every_site_fits": fits[0] if fits else None,
        "hits_per_search_that_fit_p05": fits[len(fits) // 20] if fits else None,
    }
