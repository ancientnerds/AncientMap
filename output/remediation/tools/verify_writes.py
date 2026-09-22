"""The acceptance for the write wave: the journal says what changed, the database must agree.

A check the writer's own driver runs is not an acceptance, so this asks production directly - in both
directions. Every journal row for this wave must find its new value in the database, and every planned
row *without* a journal row must still hold its old value, which covers the withheld and the
boundary-refused rows in the same pass.

**It follows the journal chain** (2026-09-22). A field can be written again after phase 3 - the B9
lane respells five phase-3 `United Kingdom` rows as `Northern Ireland` - and a per-row comparison of
the phase-3 value with the live value would report every such row as a deviation. So every field
this wave planned is read as its whole chain of journal rows, oldest first, across every run stamp:
each link must start where the one before it ended, the chain must end at the live value, and a
planned field that phase 3 did not write must start from the planned old value. A phase-3 write that
a later journalled write replaced is *superseded* and reported by stamp - never silently accepted,
never counted as a deviation. The check is strictly stronger than the per-row one it replaces: the
live value must still equal the last journalled value, and the chain itself must be unbroken.

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
ROWS = LOGS / "_write_dry" / "ALL_ROWS.jsonl"
HOST = "ancientnerds"
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


def stored_values(ids: list[str]) -> dict[str, list[str | None]]:
    """Read all three columns for these sites, in one query per 200."""
    rows: dict[str, list[str | None]] = {}
    columns = ", ".join(f"coalesce({c}::text, '{NULL}')" for c in COLUMNS)
    for start in range(0, len(ids), 200):
        window = ids[start : start + 200]
        sql = (
            f"SELECT id, {columns} FROM unified_sites WHERE id IN ('"
            + "', '".join(window)
            + "');\n"
        )
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
    """Why a chain is not continuous, or None: each link starts where the one before ended."""
    for before, after in zip(chain, chain[1:], strict=False):
        if after.old != before.new:
            return (
                f"journal row {after.id} ({after.stamp}) starts from {after.old!r}, the row before "
                f"it ({before.id}, {before.stamp}) ended at {before.new!r}"
            )
    return None


def judge(
    planned: Sequence[Mapping],
    links: Sequence[Link],
    stored: Mapping[str, Sequence[str | None]],
) -> Verdict:
    """The acceptance as a pure function of the plan, the journal and the live values."""
    verdict = Verdict()
    by_field = chains(links)

    def live(column: str, pk: str) -> str | None:
        row = stored.get(pk)
        return None if row is None else row[COLUMNS.index(column)]

    written = {
        key for key, chain in by_field.items() if any(k.stamp.startswith(PHASE3) for k in chain)
    }
    for (column, pk), chain in sorted(by_field.items()):
        if (column, pk) not in written or column not in COLUMNS:
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
        if not chain[-1].stamp.startswith(PHASE3):
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
        if problem is not None:
            verdict.deviations.append(
                f"  BROKEN CHAIN {row['site_name'][:34]:35} {row['column']}: {problem}"
            )
            continue
        verdict.superseded[chain[-1].stamp] += 1
    return verdict


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Accept the phase-3 write wave against production")
    ap.add_argument("--rows", type=pathlib.Path, default=ROWS, help="the wave's ALL_ROWS.jsonl")
    args = ap.parse_args(argv)
    planned = read_jsonl(args.rows)
    ids = sorted({row["pk"] for row in planned})
    raw = []
    for start in range(0, len(ids), 200):
        window = ids[start : start + 200]
        raw += psql(
            f"SELECT id, run_stamp, column_name, row_pk, coalesce(old_value, '{NULL}'), "
            f"coalesce(new_value, '{NULL}') FROM remediation_change_log "
            "WHERE table_name = 'unified_sites' "
            "AND column_name IN ('"
            + "', '".join(COLUMNS)
            + "') AND row_pk IN ('"
            + "', '".join(window)
            + "') ORDER BY id;\n"
        )
    links = [
        Link(int(i), stamp, column, pk, _value(old), _value(new))
        for i, stamp, column, pk, old, new in raw
    ]
    print(f"journal rows for the planned fields: {len(links)}")
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
