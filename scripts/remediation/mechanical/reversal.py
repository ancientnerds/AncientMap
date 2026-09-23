"""Undo a named list of journal rows - the journal-reversal lane.

## What it does

Every production write of the remediation left a `remediation_change_log` row with the value it
replaced. Reversing one is a write of its own: the new value is the row's `old_value`, conditioned
on the live value still being the row's `new_value` (guard 3), and the transaction refuses unless
every planned cell is the exact inverse of the *last* journal row of its cell (guard 6). The
reversal gets its own run stamp, test id and change keys, so the phase-3 acceptance
(`output/remediation/tools/verify_writes.py --allow-stamp <stamp>`) reads the reversed rows as
superseded, never as deviations.

The list is explicit and reviewed: `lane.REVERSAL_1_JOURNAL_IDS` in code, and per row the reason and
the evidence in `output/remediation/mechanical_reversal_1/REASONS.json`. Both must name the same
rows.

## How a row is decided (`classify_reversal`, first failure refuses)

1. the journal row exists and is the `unified_sites` cell `REASONS.json` names; 2. the column is
   one the lane owns (`country`, `period_start`); 3. the site is curated; 4. the cell's journal is
   continuous and ends at the live value (`plan.journal_break`); 5. the named row is the cell's last
   link; 6. the value it replaced is not NULL and reads in the column's type; 7. every quote of its
   evidence is where it says: the live description, the page `--collect` fetched (English
   Wikipedia, Wikidata), or the gold-standard record - and a gold-standard quote also needs that
   record to judge the restored value CORRECT.

`--collect` fetches the pages the quotes name (read-only, the project USER_AGENT) into
`export/pages.json`; `--write` reads production (read-only) and writes `PLAN.jsonl`, `PLAN.md`,
`SKIPPED.jsonl`, `ROLLBACK.sql`. `apply.py --lane journal-reversal-1` renders and runs it.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.apply import typed_value  # noqa: E402
from mechanical.lane import REVERSAL_1, REVERSAL_1_JOURNAL_IDS, Lane, sql_literal  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    WIKIDATA_API,
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    _now,
    get_json,
    journal_break,
    psql_json_reader,
    sql_ids,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)
from pipeline.utils.text import categorize_period  # noqa: E402

log = logging.getLogger("mechanical.reversal")

LANE = REVERSAL_1
DEFAULT_OUT = REPO / "output" / "remediation" / LANE.out_dir_name
GOLD = REPO / "output" / "remediation" / "gold_standard" / "sites.json"
ENWIKI_API = "https://en.wikipedia.org/w/api.php"


# ------------------------------------------------------------------------------ the reasons
@dataclass(frozen=True)
class Quote:
    source: str
    text: str


@dataclass(frozen=True)
class Reason:
    journal_id: int
    site_id: str
    name: str
    column: str
    reason: str
    quotes: tuple[Quote, ...]
    residual: str


def load_reasons(path: Path, lane: Lane, expected: Sequence[int]) -> list[Reason]:
    """`REASONS.json`, refused unless it lists exactly the lane's journal rows, each once."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the reviewed reasons are part of the plan")
    raw = json.loads(path.read_text(encoding="utf-8"))
    reasons = [
        Reason(
            journal_id=int(entry["journal_id"]),
            site_id=str(entry["site_id"]),
            name=str(entry["name"]),
            column=str(entry["column"]),
            reason=str(entry["reason"]),
            quotes=tuple(Quote(str(q["source"]), str(q["text"])) for q in entry["quotes"]),
            residual=str(entry.get("residual") or ""),
        )
        for entry in raw["reversals"]
    ]
    ids = [r.journal_id for r in reasons]
    if sorted(ids) != sorted(expected) or len(set(ids)) != len(ids):
        raise PlanError(
            f"{path.name} lists journal rows {sorted(ids)}, the {lane.name} lane reverses "
            f"{sorted(expected)} - the reviewed list and the code must agree"
        )
    for r in reasons:
        if not r.reason or not r.quotes:
            raise PlanError(f"journal row {r.journal_id}: a reversal needs a reason and evidence")
    return reasons


# ------------------------------------------------------------------------------- the state
@dataclass(frozen=True)
class Cell:
    """One reversal's live state: the journal row, the site, the cell's chain and its value."""

    entry: Mapping[str, Any] | None
    site: Mapping[str, Any] | None
    chain: tuple[JournalLink, ...]
    live: str | None


def load_state(
    reader: Callable[[str], list[dict[str, Any]]], reasons: Sequence[Reason], lane: Lane = LANE
) -> dict[int, Cell]:
    """The journal rows, their sites and every journal row of each cell - read-only.

    The live values are read as text (`::text`), the form the journal records them in.
    """
    ids = ", ".join(str(int(r.journal_id)) for r in reasons)
    entries = {
        int(e["id"]): e
        for e in reader(
            "SELECT id, row_pk, table_name, column_name, old_value, new_value, run_stamp, "
            "coalesce(test_id, '') AS test_id FROM remediation_change_log "
            f"WHERE id IN ({ids})"
        )
    }
    values = ", ".join(f"{column}::text AS {column}" for column in lane.columns)
    sites = {
        str(s["id"]): s
        for s in reader(
            # `id IN ('...')`: the literals take the key's type and the primary key is used;
            # `id::text IN` would scan all 1.76M rows (the 0022 lesson)
            f"SELECT id::text AS id, name, source_id, description, {values} FROM unified_sites "
            f"WHERE id IN ({sql_ids(r.site_id for r in reasons)})"
        )
    }
    chains: dict[tuple[str, str], list[JournalLink]] = {}
    columns = ", ".join(sql_literal(c) for c in sorted({r.column for r in reasons}))
    for row in reader(
        "SELECT id, row_pk, column_name, run_stamp, coalesce(test_id, '') AS test_id, old_value, "
        "new_value FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND column_name IN ({columns}) AND row_pk IN ({sql_ids(r.site_id for r in reasons)}) "
        "ORDER BY id"
    ):
        chains.setdefault((str(row["row_pk"]), str(row["column_name"])), []).append(
            JournalLink(
                int(row["id"]),
                str(row["run_stamp"]),
                str(row["test_id"]),
                row["old_value"],
                row["new_value"],
            )
        )
    out: dict[int, Cell] = {}
    for r in reasons:
        site = sites.get(r.site_id)
        out[r.journal_id] = Cell(
            entry=entries.get(r.journal_id),
            site=site,
            chain=tuple(chains.get((r.site_id, r.column), ())),
            live=None if site is None else site.get(r.column),
        )
    return out


# ------------------------------------------------------------------------------ the pages
def collect_pages(reasons: Sequence[Reason], path: Path) -> int:
    """Fetch every page a quote names (English Wikipedia extract, Wikidata item), as fetched."""
    pages: dict[str, str] = {}
    for reason in reasons:
        for quote in reason.quotes:
            kind, _, ref = quote.source.partition(":")
            if kind == "enwiki" and quote.source not in pages:
                data = get_json(
                    ENWIKI_API,
                    {
                        "action": "query",
                        "prop": "extracts",
                        "titles": ref,
                        "explaintext": "1",
                        "redirects": "1",
                        "format": "json",
                    },
                )
                (page,) = data["query"]["pages"].values()
                if "missing" in page:
                    raise PlanError(f"en.wikipedia has no page {ref!r}")
                pages[quote.source] = str(page["extract"])
            elif kind == "wikidata" and quote.source not in pages:
                data = get_json(
                    WIKIDATA_API,
                    {
                        "action": "wbgetentities",
                        "ids": ref,
                        "props": "labels|descriptions|claims",
                        "languages": "en",
                        "format": "json",
                    },
                )
                pages[quote.source] = json.dumps(data["entities"][ref], ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": _now(), "pages": pages}, ensure_ascii=False, indent=1),
        encoding="utf-8",
        newline="\n",
    )
    return len(pages)


def load_gold(path: Path = GOLD) -> dict[str, Mapping[str, Any]]:
    """The gold-standard records by site id (`output/remediation/gold_standard/sites.json`)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(r["site_id"]): r for r in raw["records"]}


def quote_problem(
    quote: Quote,
    reason: Reason,
    cell: Cell,
    pages: Mapping[str, str],
    gold: Mapping[str, Mapping[str, Any]],
) -> str | None:
    """Why a quote is not where it says it is - or None when it is."""
    kind, _, ref = quote.source.partition(":")
    if kind == "description":
        text = str((cell.site or {}).get("description") or "")
    elif kind in ("enwiki", "wikidata"):
        if quote.source not in pages:
            return f"{quote.source} was not collected - run --collect"
        text = pages[quote.source]
    elif kind == "gold_standard":
        record = gold.get(ref)
        if record is None or ref != reason.site_id:
            return f"the gold standard has no record {ref} for this site"
        verdicts = {v["field"]: v for v in record["verdicts"]}
        verdict = verdicts.get(reason.column)
        if verdict is None or verdict["verdict"] != "CORRECT":
            return f"the gold standard does not judge {reason.column} CORRECT"
        restored = (cell.entry or {}).get("old_value")
        if str(record["db_fields"].get(reason.column)) != str(restored):
            return (
                f"the gold standard judged {record['db_fields'].get(reason.column)!r}, the "
                f"reversal restores {restored!r}"
            )
        text = str(verdict["note"])
    else:
        return f"{quote.source!r} is not a source this lane can check"
    if quote.text not in text:
        return f"{quote.text!r} is not in {quote.source}"
    return None


# ------------------------------------------------------------------------------ the decision
def classify_reversal(
    reason: Reason,
    cell: Cell,
    *,
    lane: Lane,
    pages: Mapping[str, str],
    gold: Mapping[str, Mapping[str, Any]],
) -> Verdict:
    """Decide one reversal. Every check is named, and the first failure is the reason."""
    entry, site = cell.entry, cell.site

    def verdict(ok: bool, why: str, note: str, evidence: Sequence[dict[str, Any]] = ()) -> Verdict:
        return Verdict(
            site_id=reason.site_id,
            site_name=reason.name if site is None else str(site["name"]),
            ok=ok,
            old_value=cell.live,
            new_value=None if entry is None else entry["old_value"],
            rule="journal-reversal",
            reason=why,
            note=note,
            phase3=entry is not None and str(entry["run_stamp"]).startswith("phase3:"),
            finding_test_id=f"journal:{reason.journal_id}",
            evidence=tuple(evidence),
            column=reason.column,
            journal_id=reason.journal_id if ok else None,
        )

    if entry is None:
        return verdict(False, "journal-row-missing", f"no journal row {reason.journal_id}")
    if (
        entry["table_name"] != "unified_sites"
        or entry["column_name"] != reason.column
        or entry["row_pk"] != reason.site_id
    ):
        return verdict(
            False,
            "journal-row-is-another-cell",
            f"journal row {reason.journal_id} is {entry['table_name']}.{entry['column_name']} of "
            f"{entry['row_pk']}, the reason names unified_sites.{reason.column} of {reason.site_id}",
        )
    if reason.column not in lane.columns:
        return verdict(
            False, "column-not-owned", f"the {lane.name} lane does not write {reason.column}"
        )
    if site is None or site["source_id"] != CURATED_SOURCE:
        return verdict(False, "row-not-in-curated-source", "not a curated site")
    broken = journal_break(cell.chain, cell.live)
    if broken is not None:
        return verdict(False, *broken)
    if not cell.chain or cell.chain[-1].id != reason.journal_id:
        later = cell.chain[-1].id if cell.chain else None
        return verdict(
            False,
            "not-the-last-write",
            f"journal row {later} wrote the cell after {reason.journal_id}; reverse that one first",
        )
    restored = entry["old_value"]
    if restored is None:
        return verdict(
            False, "restores-null", "the row replaced a NULL; this lane never clears a column"
        )
    try:
        typed_value(lane.cell(reason.column), str(restored))
    except PlanError as exc:
        return verdict(False, "restored-value-unreadable", str(exc))
    for quote in reason.quotes:
        problem = quote_problem(quote, reason, cell, pages, gold)
        if problem is not None:
            return verdict(False, "evidence-not-found", problem)
    evidence: list[dict[str, Any]] = [
        {
            "source": f"remediation_change_log:{entry['id']}",
            "url": "remediation_change_log",
            "quote": f"{entry['run_stamp']} ({entry['test_id']}): {reason.column} "
            f"{entry['old_value']!r} -> {entry['new_value']!r} - the write this row undoes",
        },
        *({"source": q.source, "url": _url(q.source), "quote": q.text} for q in reason.quotes),
    ]
    if reason.column == "period_start":
        before, after = categorize_period(int(restored)), categorize_period(int(str(cell.live)))
        evidence.append(
            {
                "source": "pipeline/utils/text.py:categorize_period",
                "url": "pipeline/utils/text.py",
                "quote": f"categorize_period({restored}) = {before!r}, "
                f"categorize_period({cell.live}) = {after!r}"
                + (" - the same bucket" if before == after else " - another bucket"),
            }
        )
    if reason.residual:
        evidence.append({"source": "residual", "url": "REASONS.json", "quote": reason.residual})
    return verdict(True, "", reason.reason, evidence)


def _url(source: str) -> str:
    kind, _, ref = source.partition(":")
    if kind == "enwiki":
        return "https://en.wikipedia.org/wiki/" + ref.replace(" ", "_")
    if kind == "wikidata":
        return f"https://www.wikidata.org/wiki/{ref}"
    if kind == "gold_standard":
        return "output/remediation/gold_standard/sites.json"
    return "unified_sites.description"


def build_reversal_plan(
    reasons: Sequence[Reason],
    state: Mapping[int, Cell],
    *,
    lane: Lane,
    pages: Mapping[str, str],
    gold: Mapping[str, Mapping[str, Any]],
    built_at: str,
) -> Plan:
    """A pure function of its inputs: no database, no network, no clock of its own."""
    verdicts = [
        classify_reversal(r, state[r.journal_id], lane=lane, pages=pages, gold=gold)
        for r in sorted(reasons, key=lambda r: r.journal_id)
    ]
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    return Plan(
        changes=changes,
        skipped=skipped,
        built_at=built_at,
        counters={"reversals": len(verdicts), "changes": len(changes), "skipped": len(skipped)},
        lane=lane,
    )


def write_plan_md(plan: Plan, reasons: Sequence[Reason], path: Path) -> None:
    by_id = {r.journal_id: r for r in reasons}
    add = (lines := []).append
    add(f"# Journal reversal - plan ({plan.lane.name})")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/reversal.py`. Lane "
        f"`{plan.lane.name}`: run stamp `{plan.lane.run_stamp}`, journal test id "
        f"`{plan.lane.test_id}`, change keys `{plan.lane.key_prefix}:<site_id>:<column>`."
    )
    add("")
    add(
        f"**{len(plan.changes)} cell(s) will be written, {len(plan.skipped)} refused.** Each restores "
        "the value a journal row replaced, conditioned on the live value being the value that row "
        "wrote, and on that row being the last write of its cell (guard 6)."
    )
    add("")
    for change in plan.changes:
        reason = by_id[int(str(change.journal_id))]
        add(f"## {change.site_name} - `{change.column}` {change.old_value} -> {change.new_value}")
        add("")
        add(f"Site `{change.site_id}`, journal row {change.journal_id}.")
        add("")
        add(f"**Reason.** {reason.reason}.")
        add("")
        for e in change.evidence:
            add(f"* {e['source']}: {e['quote']}")
        add("")
    for s in plan.skipped:
        add(f"* REFUSED {s.site_name} ({s.finding_test_id}): `{s.reason}` - {s.note}")
    add("")
    add("## After the apply")
    add("")
    add(
        "The phase-3 acceptance reads these cells as superseded once it is told the stamp: "
        f"`verify_writes.py --allow-stamp {plan.lane.run_stamp}` (with the UK lane's stamp as "
        "before). Re-plan the card_stats recompute afterwards: `civilization` and `antiquity` "
        "derive from these cells."
    )
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan a journal reversal (mechanical lane)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--collect", action="store_true", help="fetch the pages the quotes name")
    ap.add_argument("--write", action="store_true", help="read production (read-only) and plan")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not (args.collect or args.write):
        ap.print_help()
        return 0
    try:
        reasons = load_reasons(args.out / "REASONS.json", LANE, REVERSAL_1_JOURNAL_IDS)
        pages_path = args.out / "export" / "pages.json"
        if args.collect:
            log.info("%d page(s) collected", collect_pages(reasons, pages_path))
        if args.write:
            if not pages_path.exists():
                raise PlanError(f"{pages_path} is missing - run --collect")
            pages = json.loads(pages_path.read_text(encoding="utf-8"))["pages"]
            plan = build_reversal_plan(
                reasons,
                load_state(psql_json_reader(), reasons),
                lane=LANE,
                pages=pages,
                gold=load_gold(),
                built_at=_now(),
            )
            write_plan_jsonl(plan, args.out / "PLAN.jsonl")
            write_skipped_jsonl(plan, args.out / "SKIPPED.jsonl")
            write_plan_md(plan, reasons, args.out / "PLAN.md")
            write_rollback_sql(plan, args.out / "ROLLBACK.sql", plan_path=args.out / "PLAN.jsonl")
            print(json.dumps(dict(plan.counters), indent=1, sort_keys=True))
    except PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
