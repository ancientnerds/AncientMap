"""Phase 6 item 1: undo the phase-3 `site_type` writes that are not site types - the shape lane.

## The defect

Phase 3 wrote three values into `unified_sites.site_type` that are not a type at all, and they are
live in page titles (`<title>Witham Shield — England · suspect_modern | Ancient Nerds</title>`):

* `Grave (burial site) — not representable` on the Treasure of Osztrópataka (batch-0168) - the
  model's own statement that no type fits, written as if it were one;
* `suspect_modern` on the Library of Ashurbanipal (batch-0285) and the Witham Shield (batch-0209) -
  a program's marker token.

This lane restores the value each of those writes replaced: the journal's `old_value`, which the
pre-remediation snapshot must confirm. It **restores, it does not judge** - whether the restored
type is the best one is the search lane's question, not this one's.

## How a row is decided (`classify_shape`, first failure refuses)

Candidates are the curated rows whose `site_type` is outside `CANONICAL_TYPES`
(`pipeline/normalizers/site_type.py`), read live and read-only. 1. curated rows only; 2. a row with
no type is refused for review; 3. only a value of *not-a-type shape* is repaired - a snake_case
marker (`lane.NOT_A_TYPE_MARKER`) or the phrase `not representable` - and every other value outside
the list (`Treasury`, `Altar`) is a real word the vocabulary lacks: it goes to `REVIEW.md` for a
vocabulary decision, never to a write; 4. the journal must end at the live value; 5. the value must
have been written by phase 3 (no journal row: it predates the remediation and is the owner's);
6. the restored value must be canonical and 7. a fixed point of `normalize_site_type`, which the Lyra
container applies at every boot; 8. the pre-remediation snapshot must hold the value the journal
says was replaced.

`--write` reads production (read-only) and the snapshot, and writes
`output/remediation/mechanical_site_type/`: `PLAN.jsonl`, `PLAN.md`, `SKIPPED.jsonl`, `REVIEW.md`,
`ROLLBACK.sql`. `apply.py --lane site-type-shape` renders and runs the transaction.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.lane import (  # noqa: E402
    NOT_A_TYPE_MARKER,
    NOT_A_TYPE_PHRASE,
    SITE_TYPE_SHAPE,
    sql_literal,
)
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    DEFAULT_SNAPSHOT,
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    _now,
    journal_break,
    load_journal,
    psql_json_reader,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)
from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type  # noqa: E402

log = logging.getLogger("mechanical.site_type_shape")

LANE = SITE_TYPE_SHAPE
DEFAULT_OUT = REPO / "output" / "remediation" / LANE.out_dir_name
MARKER = re.compile(NOT_A_TYPE_MARKER)
REVIEW = "outside-canonical-list"


def not_a_type(value: str) -> str | None:
    """Which not-a-type shape the value has (`marker-token`, `model-refusal`), or None."""
    if MARKER.match(value):
        return "marker-token"
    if NOT_A_TYPE_PHRASE in value.casefold():
        return "model-refusal"
    return None


# ------------------------------------------------------------------------------ the candidates
@dataclass(frozen=True)
class Row:
    """A curated row whose site_type is outside the canonical list, with its journal."""

    site_id: str
    name: str
    source_id: str
    site_type: str | None
    journal: tuple[JournalLink, ...] = ()


ROW_SQL = (
    "SELECT u.id::text AS id, u.name, u.source_id, u.site_type FROM unified_sites u "
    f"WHERE u.source_id = {sql_literal(CURATED_SOURCE)} AND (u.site_type IS NULL OR "
    "u.site_type NOT IN (" + ", ".join(sql_literal(t) for t in CANONICAL_TYPES) + ")) "
    "ORDER BY u.id"
)


def load_rows(reader: Callable[[str], list[dict[str, Any]]]) -> list[Row]:
    """The candidates and their `site_type` journal, read from production - read-only."""
    raw = reader(ROW_SQL)
    journal = load_journal(reader, "site_type", [str(r["id"]) for r in raw])
    return [
        Row(
            site_id=str(r["id"]),
            name=str(r["name"]),
            source_id=str(r["source_id"]),
            site_type=r["site_type"],
            journal=journal.get(str(r["id"]), ()),
        )
        for r in raw
    ]


def load_snapshot_types(path: Path) -> dict[str, str | None]:
    """`site_type` per curated site in the pre-remediation snapshot (2026-09-20)."""
    if not path.exists():
        raise PlanError(f"{path} is missing - the pre-remediation snapshot is the second witness")
    out: dict[str, str | None] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("source_id") == CURATED_SOURCE:
                out[str(d["id"])] = d.get("site_type")
    return out


# ------------------------------------------------------------------------------ the decision
@dataclass(frozen=True)
class ShapePlan:
    plan: Plan
    review: tuple[Verdict, ...]
    counters: Mapping[str, int] = field(default_factory=dict)


def classify_shape(row: Row, *, snapshot: Mapping[str, str | None]) -> Verdict:
    """Decide one row. Every check is named, and the first failure is the reason."""
    last = row.journal[-1] if row.journal else None
    written = (
        [
            {
                "source": f"remediation_change_log:{last.id}",
                "url": "remediation_change_log",
                "quote": f"{last.run_stamp} ({last.test_id}): {last.old_value!r} -> "
                f"{last.new_value!r}",
            }
        ]
        if last is not None
        else []
    )

    def verdict(
        ok: bool, reason: str, note: str, evidence: Sequence[dict[str, Any]] = (), **kw: Any
    ) -> Verdict:
        return Verdict(
            site_id=row.site_id,
            site_name=row.name,
            ok=ok,
            old_value=row.site_type,
            new_value=kw.get("new_value"),
            rule=kw.get("rule", ""),
            reason=reason,
            note=note,
            phase3=last is not None and last.run_stamp.startswith("phase3:"),
            finding_test_id="live:unified_sites.site_type",
            evidence=tuple(evidence),
        )

    if row.source_id != CURATED_SOURCE:
        return verdict(
            False,
            "row-not-in-curated-source",
            f"the row belongs to source_id={row.source_id!r}; this lane writes curated sites only",
        )
    if row.site_type is None:
        return verdict(False, "no-site-type", "the row carries no site_type - hand review")
    shape = not_a_type(row.site_type)
    if shape is None:
        return verdict(
            False,
            REVIEW,
            f"{row.site_type!r} is a word, not a malformed value, and the canonical list lacks it: "
            "add it to the vocabulary or map it to a canonical type - a vocabulary decision",
            written,
        )
    broken = journal_break(row.journal, row.site_type)
    if broken is not None:
        return verdict(False, *broken)
    if last is None:
        return verdict(
            False,
            "no-journal-row",
            f"{row.site_type!r} ({shape}) has no journal row: it predates the remediation, so "
            "there is no written value to restore - hand review",
        )
    if not last.run_stamp.startswith("phase3:"):
        return verdict(
            False,
            "not-a-phase3-write",
            f"the value was written by {last.run_stamp!r}, not by phase 3 - this lane undoes phase "
            "3's malformed writes only",
        )
    restore = last.old_value
    if restore not in CANONICAL_TYPES:
        return verdict(
            False,
            "restore-not-canonical",
            f"journal row {last.id} replaced {restore!r}, which is not a canonical type either",
        )
    if normalize_site_type(restore) != restore:
        return verdict(
            False,
            "restore-not-a-fixed-point",
            f"normalize_site_type({restore!r}) = {normalize_site_type(restore)!r}: the Lyra boot "
            "normaliser would rewrite the restored value",
        )
    if row.site_id not in snapshot:
        return verdict(False, "not-in-snapshot", "the pre-remediation snapshot has no such site")
    first = row.journal[0]
    if snapshot[row.site_id] != first.old_value:
        return verdict(
            False,
            "snapshot-disagrees",
            f"the snapshot holds {snapshot[row.site_id]!r}, the journal says the first write "
            f"replaced {first.old_value!r}",
        )
    evidence = [
        *written,
        {
            "source": "output/remediation/snapshot/unified_sites.jsonl.gz (2026-09-20)",
            "url": "output/remediation/snapshot/unified_sites.jsonl.gz",
            "quote": f"site_type = {snapshot[row.site_id]!r} before the remediation",
        },
        {
            "source": "pipeline/normalizers/site_type.py:CANONICAL_TYPES",
            "url": "pipeline/normalizers/site_type.py",
            "quote": f"{restore!r} is canonical and normalize_site_type({restore!r}) = {restore!r}; "
            f"{row.site_type!r} is not canonical ({shape})",
        },
    ]
    return verdict(
        True,
        "",
        f"{row.site_type!r} ({shape}, phase 3 {last.run_stamp}) -> {restore!r}, the value it replaced",
        evidence,
        new_value=restore,
        rule=f"restore-{shape}",
    )


def build_shape_plan(
    rows: Sequence[Row], *, snapshot: Mapping[str, str | None], built_at: str
) -> ShapePlan:
    """A pure function of its inputs: no database, no clock of its own."""
    verdicts = [
        classify_shape(row, snapshot=snapshot) for row in sorted(rows, key=lambda r: r.site_id)
    ]
    changes = tuple(v for v in verdicts if v.ok)
    review = tuple(v for v in verdicts if not v.ok and v.reason == REVIEW)
    skipped = tuple(v for v in verdicts if not v.ok and v.reason != REVIEW)
    counters: dict[str, int] = {
        "candidates": len(verdicts),
        "changes": len(changes),
        "review": len(review),
        "skipped": len(skipped),
        **{f"rule:{k}": n for k, n in sorted(Counter(c.rule for c in changes).items())},
        **{f"skip:{k}": n for k, n in sorted(Counter(s.reason for s in skipped).items())},
    }
    plan = Plan(changes=changes, skipped=skipped, built_at=built_at, counters=counters, lane=LANE)
    return ShapePlan(plan=plan, review=review, counters=counters)


# ------------------------------------------------------------------------------ the output
def write_plan_md(result: ShapePlan, path: Path) -> None:
    plan = result.plan
    add = (lines := []).append
    add("# Phase 6 item 1 - site_type values that are not site types: plan")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/site_type_shape.py`. Lane "
        f"`{LANE.name}`: run stamp `{LANE.run_stamp}`, journal test id `{LANE.test_id}`, change keys "
        f"`{LANE.key_prefix}:<site_id>`."
    )
    add("")
    add(
        f"**{len(plan.changes)} row(s) will be restored to the value phase 3 replaced, "
        f"{len(plan.skipped)} refused, {len(result.review)} left for a vocabulary decision** "
        "(`REVIEW.md`). The lane restores; it does not judge whether the restored type is the best "
        "one."
    )
    add("")
    add("| site | written by phase 3 | restored | shape |")
    add("|---|---|---|---|")
    for c in sorted(plan.changes, key=lambda c: c.site_name):
        add(f"| {c.site_name} (`{c.site_id}`) | `{c.old_value}` | `{c.new_value}` | {c.rule} |")
    add("")
    if plan.skipped:
        add("## Refused (see `REVIEW.md`)")
        add("")
        add("| site | value | reason |")
        add("|---|---|---|")
        for s in plan.skipped:
            add(f"| {s.site_name} | `{s.old_value}` | `{s.reason}` |")
        add("")
    add("## Reproduce")
    add("")
    add("```bash")
    add("./.venv/Scripts/python.exe scripts/remediation/mechanical/site_type_shape.py --write")
    add(
        "./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_site_type.py -q -rs"
    )
    add("```")
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_review_md(result: ShapePlan, path: Path) -> None:
    """Every curated site_type outside the canonical list that this lane does not write."""
    add = (lines := []).append
    add("# site_type values outside the canonical list - for hand review")
    add("")
    add(
        f"Built {result.plan.built_at} by `scripts/remediation/mechanical/site_type_shape.py`, read "
        "live (read-only). The canonical list is `pipeline/normalizers/site_type.py:CANONICAL_TYPES`, "
        "which mirrors the category colours of the globe (`ancient-nerds-map/src/constants/colors.ts`)."
        " None of these rows is written by the mechanical lane."
    )
    add("")
    add("| site | value | journal | why not written | the decision it needs |")
    add("|---|---|---|---|---|")
    for v in sorted(
        result.review + result.plan.skipped, key=lambda v: (str(v.old_value), v.site_name)
    ):
        need = (
            "add the word to CANONICAL_TYPES and colors.ts, or map it to a canonical type"
            if v.reason == REVIEW
            else "decide the type by hand (no written value to restore)"
        )
        journal = next(
            (
                e["quote"]
                for e in v.evidence
                if str(e["source"]).startswith("remediation_change_log")
            ),
            "",
        )
        add(
            f"| {v.site_name} (`{v.site_id}`) | `{v.old_value}` | {journal or v.note.split(';')[0]} | "
            f"`{v.reason}` | {need} |"
        )
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the site_type shape repair (mechanical lane)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    ap.add_argument(
        "--write",
        action="store_true",
        help="write PLAN.jsonl, PLAN.md, SKIPPED.jsonl, REVIEW.md, ROLLBACK.sql (reads prod)",
    )
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.write:
        ap.print_help()
        return 0
    result = build_shape_plan(
        load_rows(psql_json_reader()),
        snapshot=load_snapshot_types(args.snapshot),
        built_at=_now(),
    )
    args.out.mkdir(parents=True, exist_ok=True)
    rows = write_plan_jsonl(result.plan, args.out / "PLAN.jsonl")
    skipped = write_skipped_jsonl(result.plan, args.out / "SKIPPED.jsonl")
    write_plan_md(result, args.out / "PLAN.md")
    write_review_md(result, args.out / "REVIEW.md")
    # ROLLBACK before APPLY: apply.py --emit refuses to write an apply without its undo.
    write_rollback_sql(result.plan, args.out / "ROLLBACK.sql")
    log.info("PLAN.jsonl %d, SKIPPED.jsonl %d, review %d", rows, skipped, len(result.review))
    print(json.dumps(dict(result.counters), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
