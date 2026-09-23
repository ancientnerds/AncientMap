"""The acceptance for the write wave: the journal says what changed, the database must agree.

A check the writer's own driver runs is not an acceptance, so this asks production directly - in both
directions. Every journal row for this wave must find its new value in the database, and every planned
row *without* a journal row must still hold its old value, which covers the withheld and the
boundary-refused rows in the same pass.

**It follows the journal chain** (2026-09-22). A field can be written again after phase 3 - the B9
lane respells five phase-3 `United Kingdom` rows as `Northern Ireland` - and a per-row comparison of
the phase-3 value with the live value would report every such row as a deviation. So every field
is read as its whole chain of journal rows, oldest first, across every run stamp: each link must
start where the one before it ended (`journal_chain.first_break`, the rule the mechanical planners
use too), the chain must end at the live value, and a planned field that phase 3 did not write must
start from the planned old value. A phase-3 write that a later journalled write replaced is
*superseded* and reported by stamp - never silently accepted, never counted as a deviation.

**What it reads** (corrected 2026-09-23). First every phase-3 journal row in the three columns, of
any table and any row - not only the planned fields' - and then the whole chain of every planned
field and of every field phase 3 journalled. A phase-3 row outside the plan, or outside
`unified_sites`, is a deviation, as it was for the per-row check this replaced (`FEHLT`).

**A phase-3 rollback is not a phase-3 write.** The writer names a chunk's reversal
`<stamp>-rollback` (`phase3/write_stage.py:rollback_stamp`), which starts with `phase3:batch-` as
well. A field whose chain holds such a link is a deviation (`REVERTED`): this acceptance vouches
that the wave's corrections are in the database, and the per-row check reported a reverted write
too (`NICHT NEU`).

The 2026-09-22 version of this file counted a reversal as the phase-3 write and read the journal
only for the planned rows, so a reverted write and a phase-3 write outside the plan both passed
silently. Both gaps were latent - production held no phase-3 rollback row and every one of the 994
phase-3 fields was planned (read-only, 2026-09-23) - and both are closed here.

Against the per-row check it replaces: every deviation that check reported is still one, except a
value the chain accounts for - a phase-3 write that a later journalled write replaced, reported by
stamp. What it adds: the chain must be unbroken, a later write on a field phase 3 did not touch must
start from the planned old value and end at the live one, and a phase-3 row must be a planned
`unified_sites` field.

    ./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py \
        --rows output/remediation/logs/_write_dry/ALL_ROWS.jsonl
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

LOGS = pathlib.Path(__file__).resolve().parent
#: This file runs from `output/remediation/tools/` and from its working copy in
#: `output/remediation/logs/` (`tools/README.md`); the repository root is three levels up from both.
REPO = pathlib.Path(__file__).resolve().parents[3]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from journal_chain import first_break, is_rollback  # noqa: E402

ROWS = LOGS / "_write_dry" / "ALL_ROWS.jsonl"
HOST = "ancientnerds"
TABLE = "unified_sites"
COLUMNS = ("site_type", "period_start", "country")
PHASE3 = "phase3:batch-"
PSQL = "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1 -t -A -F '|'"


def read_jsonl(path: pathlib.Path) -> list[dict]:
    records: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: not readable JSON: {exc}") from exc
    return records


def psql(sql: str) -> list[list[str]]:
    result = subprocess.run(
        ["ssh", HOST, PSQL],
        input=sql.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"psql failed ({result.returncode}): {result.stderr.decode('utf-8', 'replace')}"
        )
    return [line.split("|") for line in result.stdout.decode("utf-8").splitlines() if line]


#: Unaligned psql prints NULL and '' the same way; this marker keeps them apart.
NULL = "<NULL>"


def _value(text: str) -> str | None:
    return None if text == NULL else text


def _in(values: Sequence[str]) -> str:
    return "('" + "', '".join(values) + "')"


def stored_values(ids: list[str]) -> dict[str, list[str | None]]:
    """Read all three columns for these sites, in one query per 200."""
    rows: dict[str, list[str | None]] = {}
    columns = ", ".join(f"coalesce({c}::text, '{NULL}')" for c in COLUMNS)
    for start in range(0, len(ids), 200):
        window = ids[start : start + 200]
        sql = f"SELECT id, {columns} FROM {TABLE} WHERE id IN {_in(window)};\n"
        for row in psql(sql):
            rows[row[0]] = [_value(v) for v in row[1:]]
    return rows


# ------------------------------------------------------------------------------ the judgement
@dataclass(frozen=True)
class Link:
    """One journal row for one field: `(column, pk)` written from `old` to `new` under `stamp`."""

    id: int
    stamp: str
    column: str
    pk: str
    old: str | None
    new: str | None
    table: str = TABLE


def is_phase3_write(stamp: str) -> bool:
    """A phase-3 write: `phase3:batch-...`, and not the `-rollback` that reverses one."""
    return stamp.startswith(PHASE3) and not is_rollback(stamp)


def is_phase3_rollback(stamp: str) -> bool:
    return stamp.startswith(PHASE3) and is_rollback(stamp)


@dataclass
class Verdict:
    deviations: list[str] = field(default_factory=list)
    written: int = 0
    untouched: int = 0
    superseded: Counter = field(default_factory=Counter)


def chains(links: Sequence[Link]) -> dict[tuple[str, str], list[Link]]:
    """Every field's journal rows, oldest first."""
    out: dict[tuple[str, str], list[Link]] = {}
    for link in sorted(links, key=lambda k: k.id):
        out.setdefault((link.column, link.pk), []).append(link)
    return out


def broken(chain: Sequence[Link]) -> str | None:
    """Why a chain is not continuous, or None (`journal_chain.first_break`)."""
    at = first_break([(link.old, link.new) for link in chain])
    if at is None:
        return None
    before, after = chain[at - 1], chain[at]
    return (
        f"journal row {after.id} ({after.stamp}) starts from {after.old!r}, the row before "
        f"it ({before.id}, {before.stamp}) ended at {before.new!r}"
    )


def reverted(chain: Sequence[Link]) -> str | None:
    """Which phase-3 rollback a chain holds, or None: a reversed phase-3 write is no correction."""
    undone = [link for link in chain if is_phase3_rollback(link.stamp)]
    if not undone:
        return None
    return ", ".join(f"journal row {link.id} ({link.stamp})" for link in undone)


def judge(
    planned: Sequence[Mapping],
    links: Sequence[Link],
    stored: Mapping[str, Sequence[str | None]],
) -> Verdict:
    """The acceptance as a pure function of the plan, the journal and the live values."""
    verdict = Verdict()
    for link in links:
        if link.table != TABLE and link.stamp.startswith(PHASE3):
            verdict.deviations.append(
                f"  OUTSIDE TABLE  {link.table}.{link.column} {link.pk}: journal row {link.id} "
                f"({link.stamp}) - the wave writes {TABLE} only"
            )
    by_field = chains([link for link in links if link.table == TABLE])
    planned_fields = {(row["column"], row["pk"]) for row in planned}

    def live(column: str, pk: str) -> str | None:
        row = stored.get(pk)
        return None if row is None else row[COLUMNS.index(column)]

    written = {
        key for key, chain in by_field.items() if any(is_phase3_write(k.stamp) for k in chain)
    }
    for (column, pk), chain in sorted(by_field.items()):
        if column not in COLUMNS:
            continue
        if (column, pk) not in planned_fields:
            phase3 = [k for k in chain if k.stamp.startswith(PHASE3)]
            if phase3:
                verdict.deviations.append(
                    f"  OUTSIDE PLAN   {pk} {column}: journalled by "
                    + ", ".join(f"{k.stamp} (row {k.id})" for k in phase3)
                    + ", but no planned row names this field"
                )
            continue
        if (column, pk) not in written:
            continue
        verdict.written += 1
        if pk not in stored:
            verdict.deviations.append(f"  MISSING      {pk} ({column})")
            continue
        problem = broken(chain)
        if problem is not None:
            verdict.deviations.append(f"  BROKEN CHAIN {pk} {column}: {problem}")
            continue
        if live(column, pk) != chain[-1].new:
            verdict.deviations.append(
                f"  NOT NEW      {pk} {column}: the journal ends at {chain[-1].new!r}, "
                f"the row holds {live(column, pk)!r}"
            )
            continue
        undone = reverted(chain)
        if undone is not None:
            verdict.deviations.append(
                f"  REVERTED     {pk} {column}: the phase-3 write was reversed by {undone}"
            )
            continue
        if not is_phase3_write(chain[-1].stamp):
            verdict.superseded[chain[-1].stamp] += 1

    for row in planned:
        key = (row["column"], row["pk"])
        if key in written:
            continue
        verdict.untouched += 1
        if row["pk"] not in stored:
            verdict.deviations.append(f"  MISSING      {row['site_name']} ({row['pk']})")
            continue
        chain = by_field.get(key, [])
        old = None if row["old_value"] is None else str(row["old_value"])
        if not chain:
            if live(*key) != old:
                verdict.deviations.append(
                    f"  CHANGED ANYWAY {row['site_name'][:34]:35} {row['column']:12} expected "
                    f"old {old!r}, read {live(*key)!r}"
                )
            continue
        problem = broken(chain)
        if problem is None and chain[0].old != old:
            problem = f"the first journal row starts from {chain[0].old!r}, the plan had {old!r}"
        if problem is None and live(*key) != chain[-1].new:
            problem = f"the journal ends at {chain[-1].new!r}, the row holds {live(*key)!r}"
        if problem is None and reverted(chain) is not None:
            problem = f"a phase-3 rollback on a field phase 3 never wrote: {reverted(chain)}"
        if problem is not None:
            verdict.deviations.append(
                f"  BROKEN CHAIN {row['site_name'][:34]:35} {row['column']}: {problem}"
            )
            continue
        verdict.superseded[chain[-1].stamp] += 1
    return verdict


# ------------------------------------------------------------------------------ the reads
def _links(raw: Sequence[Sequence[str]]) -> list[Link]:
    return [
        Link(int(i), stamp, column, pk, _value(old), _value(new), table)
        for i, stamp, table, column, pk, old, new in raw
    ]


_SELECT = (
    f"SELECT id, run_stamp, table_name, column_name, row_pk, coalesce(old_value, '{NULL}'), "
    f"coalesce(new_value, '{NULL}') FROM remediation_change_log "
)


def phase3_links() -> list[Link]:
    """Every phase-3 journal row in the three columns - of any table and any row, never only the
    planned ones: a phase-3 write outside the plan must be seen to be reported."""
    return _links(
        psql(
            _SELECT + f"WHERE run_stamp LIKE '{PHASE3}%' AND column_name IN {_in(COLUMNS)} "
            "ORDER BY id;\n"
        )
    )


def chain_links(ids: Sequence[str]) -> list[Link]:
    """Every journal row, under any stamp, of the three `unified_sites` columns of these rows."""
    links: list[Link] = []
    for start in range(0, len(ids), 200):
        window = list(ids[start : start + 200])
        links += _links(
            psql(
                _SELECT + f"WHERE table_name = '{TABLE}' AND column_name IN {_in(COLUMNS)} "
                f"AND row_pk IN {_in(window)} ORDER BY id;\n"
            )
        )
    return links


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Accept the phase-3 write wave against production")
    ap.add_argument("--rows", type=pathlib.Path, default=ROWS, help="the wave's ALL_ROWS.jsonl")
    args = ap.parse_args(argv)
    planned = read_jsonl(args.rows)
    phase3 = phase3_links()
    elsewhere = [link for link in phase3 if link.table != TABLE]
    ids = sorted({row["pk"] for row in planned} | {k.pk for k in phase3 if k.table == TABLE})
    links = chain_links(ids) + elsewhere
    print(
        f"phase-3 journal rows in the three columns: {len(phase3)}; journal rows read for "
        f"{len(ids)} sites' chains: {len(links) - len(elsewhere)}"
    )
    stored = stored_values(ids)
    print(f"read from the database: {len(stored)} of {len(ids)} sites")

    verdict = judge(planned, links, stored)
    for line in verdict.deviations:
        print(line)
    print(
        f"\n{verdict.written} phase-3 field(s) journalled, {verdict.untouched} planned field(s) "
        f"phase 3 did not write, {len(stored)} sites read"
    )
    for stamp, count in sorted(verdict.superseded.items()):
        print(f"{count} field(s) superseded by the later journalled write {stamp}")
    print(f"RESULT: {len(verdict.deviations)} deviation(s)")
    return 1 if verdict.deviations else 0


if __name__ == "__main__":
    sys.exit(main())
