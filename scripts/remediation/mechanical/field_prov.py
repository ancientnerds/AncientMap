"""The provenance markers of a site's period and point: `raw_data._period_provenance` and `_coord_provenance`.

Owner decision D12 (2026-10-08): "the origin of every period marked in raw_data", and D19 for the
point. A marker says where the stored value comes from, so a card or a Short states a period only
where its origin is one a source stands behind (`quote`, `two_source`, `authoritative`,
`import_kept`, `structured`), and no Short is made for a point nobody sourced (`unsourced`):

    {"kind": <KINDS>, "run": <the run stamp or run directory the origin is recorded in>,
     "journal_id": <the journal row the origin is, or null>, "sha": <sha256 of the value described>}

`sha` is the sha256 of the value the marker describes - `<period_start>|<period_name>` (NULL for an
empty one) or `<lat>|<lon>` as Postgres prints them - exactly as `_description_provenance` pins the
description it describes: a value that moves after the marker was written no longer hashes to it,
and the read-back counts such markers (`stale`).

## What a marker may name (`classify`)

A marker names **only a kind the journal and the decision files back**, decided in this order:

* a site whose `period_start` is empty is `undated` (a period only);
* otherwise the **newest journal row of the value** (it must end at the live value, else the site is
  refused) says: a decision entry `unresolved` (lane wd5 cleared or restored the value because no
  source stands behind it) - `unsourced` for a point, no kind for a period; evidence `status: RULE`
  - the kind is the rule's own, `derived`, `band` or `structured` (read from the evidence's source,
  `RULE_VIA`) and **never `quote`**; confidence
  `two_source` - `two_source`; `authoritative` - `authoritative`; `one_source` with a found quote -
  `quote`; a MiniMax model in the evidence - no kind at all;
* a RULE row or a MiniMax-written value that a later decision of Claude **kept** with a found quote
  (`confirmed`: the lane wd5's `keep`) is `quote`, the run the decision's run directory and **no
  journal row** (the row backs `derived`, `band` or nothing, never `quote`);
* a value with **no journal row** is the import's: `import_kept` when no decision speaks of it, WD1's
  `keep` (two quotes) or nothing, and `quote` for a later lane's `keep`; a point whose latest
  decision is `unresolved`, `held` or a `replace` that nothing wrote is `unsourced` (D19: the owner
  list, no Short);
* anything else is **listed and not marked**: a MiniMax answer nobody confirmed
  (`minimax-unconfirmed`), a period no source dated (`unsourced-period`), a confidence the lane does
  not know (`unknown-confidence`), a quote the checker never found (`no-found-quote`), a RULE row
  of a rule it does not know (`rule-unknown`).

The decision files are the lanes' `DECISIONS.jsonl`, in the order the lanes ran; the latest decision
about the live value of a field wins, and a decision about another value is not read.

## The write

`period-prov-<wave>-sNNN` and `coord-prov-<wave>-sNNN`, a cell lane on `unified_sites.raw_data` of at
most 100 sites a step, one journalled cell a site: every other key as it was, only the marker's key
set. The transaction's guards: guard 3 holds the whole old `raw_data` (no other key moved), guard 5
the described value (`<period_start>|<period_name>` or `<lat>|<lon>`) - a value changed since the plan
is refused - and two checks inside the transaction: no `raw_data` is left that is not an object or
holds a marker that does not hash its value (write and reversal alike), and no planned site is left
without a marker of a kind in `KINDS` that hashes its value (write only).

    M=scripts/remediation/mechanical
    $M/field_prov.py wave   --kind period --wave W --decisions A/DECISIONS.jsonl B/DECISIONS.jsonl ...
                                          (read-only; WAVE.json: the unmarked sites, steps of 100)
    $M/field_prov.py step   --kind period --wave W --step N      (read-only; PLAN.jsonl, ROLLBACK.sql)
    $M/apply.py --lane period-prov-W-sNNN --emit | --rehearse | --probe-guards | --apply | --verify
    $M/apply.py --lane period-prov-W-sNNN --rehearse-rollback
    $M/field_prov.py accept --kind period --wave W --step N      (read-only; 0 deviations)
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from phase3.run import read_jsonl  # noqa: E402 - the strict JSON-lines reader (no line skipped)
from prod_write import send  # noqa: E402

from mechanical.citations import canonical, reprint  # noqa: E402
from mechanical.lane import (  # noqa: E402
    FIELD_PROV_LANE,
    LOCK_TIMEOUT,
    STATEMENT_TIMEOUT,
    UNIFIED_SITES,
    Column,
    Lane,
    Residual,
    SiteInvariant,
    journal_readback,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    journal_break,
    parse_tagged_export,
    sql_ids,
    tagged_export_script,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)

ROOT_NAME = "mechanical_field_prov"
ROOT = REPO / "output" / "remediation" / ROOT_NAME
MAX_SITES = 100
WAVE_FILE, WAVE_PIN_FILE, ACCEPTED_FILE = "WAVE.json", "WAVE.sha256", "ACCEPTED.json"
CURATED = "ancient_nerds"
RETIRED = "retired"
#: The decision `answers.py` records a MiniMax agent under, and the stamp of one: any model string
#: that holds this word (`handoff` stamps `minimax/MiniMax-M3.1-Flash-Preview (MiniMax Code agent)`).
MINIMAX_WORD = "minimax"

# the kinds; the period's eight are the owner's (fields.md step 6), the point's add `unsourced`
UNDATED, QUOTE, TWO_SOURCE, AUTHORITATIVE = "undated", "quote", "two_source", "authoritative"
IMPORT_KEPT, UNSOURCED = "import_kept", "unsourced"
RULE_VIA = ("derived", "band", "structured")
PERIOD, COORD = "period", "coord"
#: Journal confidence -> kind. `one_source` is a quote only where the evidence has a found one.
CONFIDENCE_KIND = {"two_source": TWO_SOURCE, "authoritative": AUTHORITATIVE, "one_source": QUOTE}
_RULE_SOURCE = re.compile(r"\((" + "|".join(RULE_VIA) + r"),")


@dataclass(frozen=True)
class Spec:
    """One marker: where it lives, what it describes and the kinds it may name."""

    kind: str
    key: str
    kinds: tuple[str, ...]
    columns: tuple[str, ...]  # the journal columns of the described value
    field: str  # the field name of the decision files
    #: SQL: the text of the described value, on the row `u` - guard 5's premise and the sha's input
    premise: str
    test_id: str

    @property
    def lane_prefix(self) -> str:
        return f"{self.kind}-prov"


SPECS = {
    PERIOD: Spec(
        PERIOD,
        "_period_provenance",
        (QUOTE, TWO_SOURCE, AUTHORITATIVE, IMPORT_KEPT, "structured", "derived", "band", UNDATED),
        ("period_start",),
        "period_start",
        "coalesce({u}period_start::text, 'NULL') || '|' || coalesce({u}period_name, 'NULL')",
        "FP/period-provenance",
    ),
    COORD: Spec(
        COORD,
        "_coord_provenance",
        (QUOTE, TWO_SOURCE, AUTHORITATIVE, IMPORT_KEPT, UNSOURCED),
        ("lat", "lon"),
        "coordinates",
        "{u}lat::text || '|' || {u}lon::text",
        "FP/coord-provenance",
    ),
}


def premise_sql(spec: Spec, alias: str = "u.") -> str:
    return spec.premise.format(u=alias)


def sha_sql(spec: Spec, alias: str = "u.") -> str:
    """sha256 of the described value, as Postgres computes it (`sha` of the marker)."""
    return f"encode(sha256(convert_to({premise_sql(spec, alias)}, 'UTF8')), 'hex')"


def sha_of(premise: str) -> str:
    """`sha_sql` in Python, over the premise text."""
    return hashlib.sha256(premise.encode("utf-8")).hexdigest()


def _kinds_sql(spec: Spec) -> str:
    return ", ".join(sql_literal(k) for k in spec.kinds)


# ------------------------------------------------------------------------------ the lanes
def step_name(step: int) -> str:
    if not 1 <= step <= 999:
        raise ValueError(f"step {step} is not 1-999")
    return f"s{step:03d}"


def _stale(spec: Spec, alias: str = "") -> str:
    """SQL over a row: it holds the marker, and the marker does not hash the value."""
    return (
        f"{alias}raw_data ? '{spec.key}' AND {alias}raw_data -> '{spec.key}' ->> 'sha' "
        f"IS DISTINCT FROM {sha_sql(spec, alias)}"
    )


def prov_lane(kind: str, wave: str, step: int) -> Lane:
    """The lane of one step of one marker kind: its own stamp, key prefix and directory."""
    spec = SPECS[kind]
    name = f"{spec.lane_prefix}-{wave}-{step_name(step)}"
    if FIELD_PROV_LANE.match(name) is None:
        raise ValueError(f"{wave!r} is not a wave label like 2026-10-20 or 2026-10-20b")
    stale = Residual(f"curated sites whose {kind} provenance does not hash their value",
                     _stale(spec))  # fmt: skip
    broken = Residual(
        f"planned sites whose raw_data is not an object or holds a {kind} marker that does not hash",
        f"(raw_data IS NOT NULL AND jsonb_typeof(raw_data) <> 'object') OR ({_stale(spec)})",
    )
    return Lane(
        name=name,
        key_prefix=name,
        run_stamp=f"{wave}_{spec.lane_prefix}-{step_name(step)}",
        test_id=spec.test_id,
        # derived from the journal and the decision files, not researched: no source is claimed
        confidence="authoritative",
        label=f"{kind} provenance marker",
        plan_table=f"_{kind}_prov_plan",
        out_dir_name=f"{ROOT_NAME}/{kind}/{wave}/{step_name(step)}",
        post_commit_residual=stale,
        rehearsal_residual=stale,
        premise_sql=premise_sql(spec),
        lock_timeout=LOCK_TIMEOUT,
        statement_timeout=STATEMENT_TIMEOUT,
        target=UNIFIED_SITES,
        # a site with no raw_data at all gets an object of the marker alone (`fills_null`), and the
        # reversal of that write puts the NULL back - which the mechanical writer calls `clears`
        cells=(Column("raw_data", "jsonb", fills_null=True, clears=True),),
        write_invariant=broken,
        site_invariants=(
            SiteInvariant(
                says=f"planned site(s) hold no {kind} marker of a known kind that hashes their value",
                predicate=(
                    f"NOT (u.raw_data ? '{spec.key}') OR "
                    f"(u.raw_data -> '{spec.key}' ->> 'kind') NOT IN ({_kinds_sql(spec)}) OR "
                    f"({_stale(spec, 'u.')})"
                ),
                probe_column="raw_data",
                probe_values=(
                    "{}",
                    '{"other": 1}',
                    f'{{"{spec.key}": {{"kind": "no such kind", "sha": "0"}}}}',
                ),
            ),
        ),
    )


def lane_of(name: str) -> Lane:
    """`period-prov-2026-10-20-s001` -> the lane; `KeyError` for any other name."""
    match = FIELD_PROV_LANE.match(name)
    if match is None:
        raise KeyError(name)
    return prov_lane(match.group(1), match.group(2), int(match.group(3)))


@functools.cache
def prov_readback(lane: Lane) -> str:
    """The read-only verification of one step, before and after its write."""
    kind = lane.name.split("-", 1)[0]
    spec = SPECS[kind]
    curated = "FROM unified_sites WHERE source_id = 'ancient_nerds' AND "
    stamp = sql_literal(lane.run_stamp)
    journal = f"FROM remediation_change_log l WHERE l.run_stamp = {stamp} AND "
    key = spec.key
    return journal_readback(
        lane,
        [
            (f"curated sites carrying a {kind} provenance", curated + f"raw_data ? '{key}'"),
            (lane.post_commit_residual.metric, curated + lane.post_commit_residual.predicate),
            (
                f"curated sites whose {kind} provenance names a kind outside the vocabulary",
                curated + f"raw_data ? '{key}' AND (raw_data -> '{key}' ->> 'kind') "
                f"NOT IN ({_kinds_sql(spec)})",
            ),
            (
                f"journal rows for this run that changed anything but the {kind} provenance",
                journal + "CASE WHEN l.column_name = 'raw_data' THEN "
                f"(coalesce(l.old_value::jsonb, '{{}}'::jsonb) - '{key}') "
                f"IS DISTINCT FROM (l.new_value::jsonb - '{key}') ELSE true END",
            ),
        ],
    )


# ------------------------------------------------------------------------------ the read
def site_sql(spec: Spec, site_ids: Iterable[str]) -> str:
    return (
        "SELECT u.id::text AS site_id, u.name, u.scope_status, u.source_id, "
        "u.raw_data::text AS raw_data, u.period_start::text AS period_start, u.period_name, "
        f"u.lat::text AS lat, u.lon::text AS lon, {premise_sql(spec)} AS premise "
        f"FROM unified_sites u WHERE u.source_id = 'ancient_nerds' AND u.id::text IN "
        f"({sql_ids(site_ids)}) ORDER BY u.id"
    )


def journal_sql(spec: Spec, site_ids: Iterable[str]) -> str:
    """Every journal row of the value's columns and of `raw_data`, with the evidence."""
    columns = ", ".join(sql_literal(c) for c in (*spec.columns, "raw_data"))
    return (
        "SELECT l.id, l.row_pk, l.column_name, l.run_stamp, coalesce(l.test_id, '') AS test_id, "
        "l.confidence, l.old_value, l.new_value, l.evidence FROM remediation_change_log l "
        f"WHERE l.table_name = 'unified_sites' AND l.column_name IN ({columns}) "
        f"AND l.row_pk IN ({sql_ids(site_ids)}) ORDER BY l.id"
    )


def pending_sql(spec: Spec) -> str:
    """The curated, live sites that hold no marker of this kind, or one that no longer hashes."""
    return (
        "SELECT u.id::text AS site_id FROM unified_sites u WHERE u.source_id = 'ancient_nerds' "
        f"AND u.scope_status IS DISTINCT FROM 'retired' AND (NOT (coalesce(u.raw_data, '{{}}'::jsonb)"
        f" ? '{spec.key}') OR ({_stale(spec, 'u.')})) ORDER BY u.id"
    )


def read_production(script: str) -> str:
    """Send a read-only export to production and return its output as it came."""
    proc = send(script, rows=True, timeout=900)
    if proc.returncode != 0:
        raise PlanError(f"the read-only export failed (psql exit {proc.returncode}): {proc.stderr}")
    return proc.stdout


@dataclass(frozen=True)
class Live:
    """One site as the step's export read it."""

    site_id: str
    name: str
    scope_status: str | None
    raw_data: str | None
    period_start: str | None
    period_name: str | None
    lat: str
    lon: str
    premise: str


@dataclass(frozen=True)
class Row:
    """One journal row of the value (or of `raw_data`)."""

    id: int
    column: str
    run_stamp: str
    test_id: str
    confidence: str
    old_value: str | None
    new_value: str | None
    evidence: tuple[Mapping[str, Any], ...]

    def link(self, *, raw: bool = False) -> JournalLink:
        old, new = (canonical(self.old_value), canonical(self.new_value)) if raw else (
            self.old_value, self.new_value)  # fmt: skip
        return JournalLink(self.id, self.run_stamp, self.test_id, old, new)


def parse_export(text: str) -> tuple[dict[str, Live], dict[str, list[Row]]]:
    rows, _at = parse_tagged_export(text, ("site", "journal"))
    live = {
        str(r["site_id"]): Live(
            str(r["site_id"]),
            str(r["name"]),
            r["scope_status"],
            r["raw_data"],
            r["period_start"],
            r["period_name"],
            str(r["lat"]),
            str(r["lon"]),
            str(r["premise"]),
        )  # fmt: skip
        for r in rows["site"]
    }
    journal: dict[str, list[Row]] = {}
    for r in sorted(rows["journal"], key=lambda r: int(r["id"])):
        evidence = r["evidence"] if isinstance(r["evidence"], list) else []
        journal.setdefault(str(r["row_pk"]), []).append(
            Row(
                int(r["id"]),
                str(r["column_name"]),
                str(r["run_stamp"]),
                str(r["test_id"]),
                str(r["confidence"]),
                r["old_value"],
                r["new_value"],
                tuple(evidence),
            )  # fmt: skip
        )
    return live, journal


# ------------------------------------------------------------------------------ the decisions
@dataclass(frozen=True)
class Decision:
    """The latest decision about one field of one site, and the run directory it came from."""

    run: str
    row: Mapping[str, Any]

    @property
    def verdict(self) -> str:
        return str(self.row["decision"])

    @property
    def by_minimax(self) -> bool:
        return MINIMAX_WORD in str(self.row.get("model") or "").lower()

    @property
    def found_quote(self) -> bool:
        return any(q.get("outcome") == "found" for q in self.row.get("quotes") or ())


def read_decisions(paths: Sequence[Path]) -> dict[tuple[str, str], Decision]:
    """The latest decision of each (site, field) over the files, in the order given - the lanes'
    order: a later file overrides an earlier one."""
    latest: dict[tuple[str, str], Decision] = {}
    for path in paths:
        if not path.exists():
            raise PlanError(f"{path} is missing")
        for row in read_jsonl(path):
            latest[(str(row["site_id"]), str(row["field"]))] = Decision(path.parent.name, row)
    return latest


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------------------ the decision
@dataclass(frozen=True)
class Marker:
    kind: str
    run: str
    journal_id: int | None
    sha: str

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "run": self.run, "journal_id": self.journal_id, "sha": self.sha}


@dataclass(frozen=True)
class Refused:
    reason: str
    note: str


MINIMAX_UNCONFIRMED = "minimax-unconfirmed"
UNSOURCED_PERIOD = "unsourced-period"
UNKNOWN_CONFIDENCE = "unknown-confidence"
NO_FOUND_QUOTE = "no-found-quote"
RULE_UNKNOWN = "rule-unknown"
REFUSAL_MEANING = {
    MINIMAX_UNCONFIRMED: "a MiniMax agent decided or wrote this value and no Claude decision "
    "confirmed it with a quote: no marker names an origin nobody checked",
    UNSOURCED_PERIOD: "no source dated this period (the latest decision is unresolved, held or "
    "left it): no marker, so no card states it",
    UNKNOWN_CONFIDENCE: "the journal row's confidence is none this lane maps to a kind",
    NO_FOUND_QUOTE: "a one-source journal row whose evidence holds no quote the checker found",
    RULE_UNKNOWN: "a RULE row whose evidence names a rule other than derived, band, structured",
    "journal-chain-broken": "a journal is not continuous",
    "journal-disagrees": "a journal does not end at the live value",
    "raw-data-not-an-object": "raw_data is JSON but not an object",
    "raw-data-not-reprinted": "raw_data is not printed the way this planner prints JSON",
    "not-a-curated-site": "the site is no longer a curated site",
    "retired": "the site was retired after the wave was planned",
    "already-marked": "the site already holds exactly this marker",
}


def row_kind(row: Row) -> str | Refused:
    """The kind one journal row's evidence and confidence back, or why none."""
    if any(e.get("decision") == "unresolved" for e in row.evidence):
        # lane wd5 cleared or restored this value because no source stands behind it: it is no
        # sourced value whatever the row's confidence says
        if row.column in ("lat", "lon"):
            return UNSOURCED
        return Refused(
            UNSOURCED_PERIOD, f"journal row {row.id}: wd5 withdrew the value, unresolved"
        )
    if any(e.get("status") == "RULE" for e in row.evidence):
        for entry in row.evidence:
            if entry.get("status") == "RULE":
                found = _RULE_SOURCE.search(str(entry.get("source")))
                if found:
                    return found.group(1)
        return Refused(RULE_UNKNOWN, f"journal row {row.id}: {row.run_stamp}")
    if any(MINIMAX_WORD in str(e.get("model") or "").lower() for e in row.evidence):
        return Refused(MINIMAX_UNCONFIRMED, f"journal row {row.id} was written by a MiniMax agent")
    kind = CONFIDENCE_KIND.get(row.confidence)
    if kind is None:
        return Refused(UNKNOWN_CONFIDENCE, f"journal row {row.id}: confidence {row.confidence!r}")
    if kind == QUOTE and not any(e.get("outcome") == "found" for e in row.evidence):
        return Refused(
            NO_FOUND_QUOTE, f"journal row {row.id} ({row.run_stamp}) quotes nothing found"
        )
    return kind


def _about(spec: Spec, live: Live, decision: Decision | None) -> bool:
    """Whether the decision was made about the value the row holds now."""
    if decision is None:
        return False
    stored = decision.row.get("stored")
    if spec.kind == PERIOD:
        return (None if stored is None else str(stored)) == live.period_start
    if stored is None:
        return False
    lat, lon = (float(x) for x in str(stored).split(","))
    return (lat, lon) == (float(live.lat), float(live.lon))


def _confirms(spec: Spec, live: Live, decision: Decision | None) -> bool:
    """Whether a later decision confirmed the live value with a found quote - a `keep` that no
    MiniMax agent made."""
    return (
        decision is not None
        and _about(spec, live, decision)
        and decision.verdict == "keep"
        and not decision.by_minimax
        and decision.found_quote
    )


def classify(
    spec: Spec, live: Live, rows: Sequence[Row], decision: Decision | None
) -> Marker | Refused:
    """The marker of one site's value, or why it gets none (the module doc)."""
    sha = sha_of(live.premise)
    newest = max((r for r in rows if r.column in spec.columns), key=lambda r: r.id, default=None)

    def marker(kind: str, run: str, row: Row | None) -> Marker:
        return Marker(kind, run, None if row is None else row.id, sha)

    if spec.kind == PERIOD and live.period_start is None:
        return marker(UNDATED, "import" if newest is None else newest.run_stamp, newest)
    decided = decision if _about(spec, live, decision) else None
    if newest is not None:
        kind = row_kind(newest)
        if decision is not None and _confirms(spec, live, decision):
            if kind == QUOTE:
                return marker(QUOTE, decision.run, newest)
            if kind in RULE_VIA or (
                isinstance(kind, Refused) and kind.reason in (MINIMAX_UNCONFIRMED, NO_FOUND_QUOTE)
            ):
                # the kind is the decision's, not the row's: the row backs `derived`, `band` or
                # nothing, never `quote`, so the marker names the decision's run and no journal row
                return marker(QUOTE, decision.run, None)
        if isinstance(kind, Refused):
            return kind
        return marker(kind, newest.run_stamp, newest)
    if decided is None:
        return marker(IMPORT_KEPT, "import", None)
    if decided.by_minimax:
        return Refused(MINIMAX_UNCONFIRMED, f"{decided.run}: {decided.verdict} by a MiniMax agent")
    if decided.verdict == "keep":
        # WD1 recorded no model: its keep rests on two quotes of two families - the import's value
        kind = IMPORT_KEPT if decided.row.get("model") is None else QUOTE
        return marker(kind, decided.run, None)
    if spec.kind == COORD:
        return marker(UNSOURCED, decided.run, None)  # unresolved, held, or a better point unwritten
    return Refused(UNSOURCED_PERIOD, f"{decided.run}: the latest decision is {decided.verdict}")


# ------------------------------------------------------------------------------ the plan
def _refused(live: Live, reason: str, note: str, spec: Spec) -> Verdict:
    return Verdict(
        site_id=live.site_id,
        site_name=live.name,
        ok=False,
        old_value=None,
        new_value=None,
        rule="",
        reason=reason,
        note=note,
        phase3=False,
        finding_test_id=spec.test_id,
    )


def new_raw_data(raw: Mapping[str, Any] | None, spec: Spec, marker: Marker) -> dict[str, Any]:
    """The raw_data a step writes: the marker set, every other key as it was."""
    return {**(raw or {}), spec.key: marker.as_dict()}


def _evidence(
    spec: Spec, marker: Marker, rows: Sequence[Row], decision: Decision | None
) -> tuple[dict[str, Any], ...]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.id == marker.journal_id:
            out.append({
                "source": f"remediation_change_log id {row.id} ({row.run_stamp})",
                "url": None,
                "quote": f"{row.column}: {row.old_value!r} -> {row.new_value!r}, confidence "
                f"{row.confidence}",
            })  # fmt: skip
    if decision is not None:
        out.append({
            "source": f"{decision.run}/DECISIONS.jsonl",
            "url": None,
            "quote": f"{decision.row['field']} {decision.verdict} by {decision.row.get('model')}: "
            f"{str(decision.row.get('reasoning'))[:300]}",
        })  # fmt: skip
    out.append(
        {
            "source": "scripts/remediation/mechanical/field_prov.py",
            "url": None,
            "quote": f"{spec.key}.kind {marker.kind!r}: the origin the journal and the decision files "
            "back; sha256 of the value described",
        }
    )
    return tuple(out)


def site_verdict(
    spec: Spec,
    live: Live | None,
    rows: Sequence[Row],
    decision: Decision | None,
    site_id: str,
) -> Verdict:
    """One site's cell, or the refusal that lists it. Pure."""
    if live is None:
        return Verdict(site_id, "?", False, None, None, "", "not-a-curated-site",
                       "the export did not return the site", False, spec.test_id)  # fmt: skip
    if live.scope_status == RETIRED:
        return _refused(live, "retired", "retired since the wave", spec)
    raw = None if live.raw_data is None else json.loads(live.raw_data)
    if raw is not None and not isinstance(raw, dict):
        return _refused(live, "raw-data-not-an-object", f"raw_data is a {type(raw).__name__}", spec)
    if live.raw_data is not None and reprint(raw) != live.raw_data:
        return _refused(
            live, "raw-data-not-reprinted", "the journal would record another spelling", spec
        )
    for column in (*spec.columns, "raw_data"):
        links = [r.link(raw=column == "raw_data") for r in rows if r.column == column]
        held = canonical(live.raw_data) if column == "raw_data" else _held(live, column)
        if (
            column in ("lat", "lon")
            and links
            and float(links[-1].new_value or "nan") == float(held)
        ):
            held = links[-1].new_value
        broken = journal_break(links, held)
        if broken is not None:
            return _refused(live, broken[0], f"{column}: {broken[1]}", spec)
    marker = classify(spec, live, rows, decision)
    if isinstance(marker, Refused):
        return _refused(live, marker.reason, marker.note, spec)
    new_text = reprint(new_raw_data(raw, spec, marker))
    if canonical(new_text) == canonical(live.raw_data):
        return _refused(live, "already-marked", f"{spec.key} already holds this marker", spec)
    return Verdict(
        site_id=live.site_id,
        site_name=live.name,
        ok=True,
        old_value=live.raw_data,
        new_value=new_text,
        rule=f"{spec.kind}-prov-{marker.kind}",
        reason="",
        note=f"raw_data.{spec.key} set to kind {marker.kind!r}; every other key as it was",
        phase3=False,
        finding_test_id=spec.test_id,
        evidence=_evidence(spec, marker, rows, decision),
        premise=live.premise,
        column="raw_data",
    )


def _held(live: Live, column: str) -> str | None:
    return {"period_start": live.period_start, "lat": live.lat, "lon": live.lon}[column]


@dataclass(frozen=True)
class StepPlan:
    plan: Plan
    skipped: tuple[Verdict, ...]


def build_step(
    spec: Spec,
    wave: str,
    step: int,
    sites: Sequence[str],
    live: Mapping[str, Live],
    journal: Mapping[str, Sequence[Row]],
    decisions: Mapping[tuple[str, str], Decision],
    *,
    built_at: str,
) -> StepPlan:
    """The lane plan of one step over `sites` (at most 100). Pure."""
    if len(sites) > MAX_SITES:
        raise PlanError(f"a step writes at most {MAX_SITES} sites, not {len(sites)}")
    verdicts = [
        site_verdict(spec, live.get(s), journal.get(s, ()), decisions.get((s, spec.field)), s)
        for s in sorted(sites)
    ]
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    counters: dict[str, int] = {
        "cells": len(changes),
        **dict(sorted(Counter(v.reason for v in skipped).items())),
    }
    counters.update(
        {
            f"kind:{k}": n
            for k, n in sorted(Counter(v.rule.rsplit("-", 1)[-1] for v in changes).items())
        }
    )
    plan = Plan(changes=changes, skipped=skipped, built_at=built_at, counters=counters,
                lane=prov_lane(spec.kind, wave, step))  # fmt: skip
    return StepPlan(plan, skipped)


# ------------------------------------------------------------------------------ the wave
def wave_dir(kind: str, wave: str, root: Path = ROOT) -> Path:
    return root / kind / wave


def _pin(path: Path) -> str:
    return sha256_file(path)


def build_wave(
    kind: str,
    wave: str,
    decisions: Sequence[Path],
    *,
    read: Callable[[str], str] = read_production,
    root: Path = ROOT,
) -> dict[str, Any]:
    """WAVE.json: the sites that hold no current marker, in steps of 100, and the decision files
    (path and sha256) the steps read - from one read-only production read."""
    spec = SPECS[kind]
    prov_lane(kind, wave, 1)  # refuses a wave label no lane resolves
    target = wave_dir(kind, wave, root)
    if (target / WAVE_FILE).exists():
        raise PlanError(f"{target / WAVE_FILE} exists: a wave is planned once")
    text = read(tagged_export_script([("site", pending_sql(spec))]))
    rows, at = parse_tagged_export(text, ("site",))
    sites = sorted(str(r["site_id"]) for r in rows["site"])
    steps = [sites[i : i + MAX_SITES] for i in range(0, len(sites), MAX_SITES)]
    record = {
        "kind": kind,
        "wave": wave,
        "read_at": at,
        "decisions": {p.as_posix(): _pin(p) for p in decisions},
        "sites": len(sites),
        "steps": steps,
    }
    target.mkdir(parents=True, exist_ok=True)
    (target / WAVE_FILE).write_text(
        json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    (target / WAVE_PIN_FILE).write_text(
        _pin(target / WAVE_FILE) + "\n", encoding="utf-8", newline="\n"
    )
    return {"kind": kind, "wave": wave, "sites": len(sites), "steps": len(steps)}


def read_wave(kind: str, wave: str, root: Path = ROOT) -> dict[str, Any]:
    """A wave's WAVE.json - refused when it is not the file its pin names."""
    target = wave_dir(kind, wave, root)
    path = target / WAVE_FILE
    if not path.exists():
        raise PlanError(f"{path} is missing - run `field_prov.py wave` first")
    if _pin(path) != (target / WAVE_PIN_FILE).read_text(encoding="utf-8").strip():
        raise PlanError(f"{path} is not the pinned wave: it was edited")
    return json.loads(path.read_text(encoding="utf-8"))


def _step_dir(kind: str, wave: str, step: int, root: Path) -> Path:
    return wave_dir(kind, wave, root) / step_name(step)


def plan_step(
    kind: str, wave: str, step: int, *, read: Callable[[str], str] = read_production,
    root: Path = ROOT,
) -> dict[str, Any]:  # fmt: skip
    """Plan step `step` from the pinned wave and a fresh read-only production read - never a step
    before the one before it is accepted."""
    spec = SPECS[kind]
    record = read_wave(kind, wave, root)
    if not 1 <= step <= len(record["steps"]):
        raise PlanError(f"wave {wave} has steps 1..{len(record['steps'])}, not {step}")
    if step > 1 and not (_step_dir(kind, wave, step - 1, root) / ACCEPTED_FILE).exists():
        raise PlanError(
            f"step {step - 1} is not accepted: `field_prov.py accept --step {step - 1}`"
        )
    out = _step_dir(kind, wave, step, root)
    if out.exists():
        raise PlanError(f"{out} exists: a step is planned once")
    paths = [Path(p) for p in record["decisions"]]
    for path in paths:
        if _pin(path) != record["decisions"][path.as_posix()]:
            raise PlanError(f"{path} is not the decision file the wave was built from")
    sites = record["steps"][step - 1]
    text = read(
        tagged_export_script(
            [("site", site_sql(spec, sites)), ("journal", journal_sql(spec, sites))]
        )
    )
    live, journal = parse_export(text)
    built = build_step(spec, wave, step, sites, live, journal, read_decisions(paths),
                       built_at=datetime.now(UTC).isoformat())  # fmt: skip
    out.mkdir(parents=True)
    (out / "export.jsonl").write_text(text, encoding="utf-8", newline="\n")
    write_skipped_jsonl(built.plan, out / "SKIPPED.jsonl")
    if built.plan.changes:
        write_plan_jsonl(built.plan, out / "PLAN.jsonl")
        write_rollback_sql(built.plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    return {"step": step, "lane": built.plan.lane.name, **built.plan.counters}


# ------------------------------------------------------------------------------ the acceptance
def deviations(
    spec: Spec,
    lane: Lane,
    rows: Sequence[Mapping[str, Any]],
    live: Mapping[str, Live],
    journal: Sequence[Mapping[str, Any]],
) -> list[str]:
    """What production holds that the step did not plan, or lacks that it did. Pure."""
    found: list[str] = []
    written = [j for j in journal if j["run_stamp"] == lane.run_stamp]
    undone = [j for j in journal if j["run_stamp"] == lane.rollback_run_stamp]
    if undone:
        found.append(f"{lane.name}: {len(undone)} rollback journal row(s)")
    by_site = {j["row_pk"]: j for j in written}
    if len(by_site) != len(written) or set(by_site) != {r["site_id"] for r in rows}:
        found.append(f"{lane.name}: {len(written)} journal row(s) for {len(rows)} planned")
    for row in rows:
        site = live[row["site_id"]]
        entry = by_site.get(row["site_id"])
        if canonical(site.raw_data) != canonical(row["new_value"]):
            found.append(f"{row['site_id']}: raw_data does not hold the planned value")
        if entry is None or canonical(entry["new_value"]) != canonical(row["new_value"]):
            found.append(f"{row['site_id']}: the journal row is not the plan's")
        held = json.loads(site.raw_data).get(spec.key) if site.raw_data else None
        if held is None or held.get("sha") != sha_of(site.premise):
            found.append(f"{row['site_id']}: the marker does not hash the live value")
    return found


def accept_step(
    kind: str, wave: str, step: int, *, read: Callable[[str], str] = read_production,
    root: Path = ROOT,
) -> tuple[int, list[str]]:  # fmt: skip
    """Re-read production (read-only) for one step; record its acceptance at 0 deviations - once."""
    spec = SPECS[kind]
    lane = prov_lane(kind, wave, step)
    out = _step_dir(kind, wave, step, root)
    rows = read_jsonl(out / "PLAN.jsonl") if (out / "PLAN.jsonl").exists() else []
    sites = [r["site_id"] for r in rows]
    stamps = ", ".join(sql_literal(s) for s in (lane.run_stamp, lane.rollback_run_stamp))
    text = read(
        tagged_export_script(
            [
                ("site", site_sql(spec, sites)),
                (
                    "journal",
                    "SELECT l.row_pk, l.column_name, l.run_stamp, l.old_value, l.new_value "
                    f"FROM remediation_change_log l WHERE l.run_stamp IN ({stamps}) ORDER BY l.id",
                ),
            ]
        )  # fmt: skip
    )
    parsed, at = parse_tagged_export(text, ("site", "journal"))
    live = {
        str(r["site_id"]): Live(
            str(r["site_id"]),
            str(r["name"]),
            r["scope_status"],
            r["raw_data"],
            r["period_start"],
            r["period_name"],
            str(r["lat"]),
            str(r["lon"]),
            str(r["premise"]),
        )  # fmt: skip
        for r in parsed["site"]
    }
    found = deviations(spec, lane, rows, live, parsed["journal"])
    accepted = out / ACCEPTED_FILE
    if not found and not accepted.exists():
        accepted.write_text(
            json.dumps({"accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
                        "read_at": at, "sites": len(sites), "cells": len(rows)}, indent=1) + "\n",
            encoding="utf-8", newline="\n",
        )  # fmt: skip
    return (0 if not found else 1), found


# ------------------------------------------------------------------------------ the CLI
def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("wave", "step", "accept"):
        command = sub.add_parser(name)
        command.add_argument("--kind", choices=sorted(SPECS), required=True)
        command.add_argument(
            "--wave", required=True, help="a date label: 2026-10-20 or 2026-10-20b"
        )
        if name != "wave":
            command.add_argument("--step", type=int, required=True)
        else:
            command.add_argument("--decisions", type=Path, nargs="+", required=True,
                                 help="the lanes' DECISIONS.jsonl, in the order they ran")  # fmt: skip
    args = parser.parse_args(argv)
    try:
        if args.command == "wave":
            _print(build_wave(args.kind, args.wave, args.decisions))
        elif args.command == "step":
            _print(plan_step(args.kind, args.wave, args.step))
        else:
            code, found = accept_step(args.kind, args.wave, args.step)
            _print({"deviations": found})
            print(f"ACCEPT_EXIT={code}")
            return code
    except (PlanError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
