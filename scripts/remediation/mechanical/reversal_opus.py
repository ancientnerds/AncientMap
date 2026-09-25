"""Build journal-reversal-3's list from the Opus re-verification's reversal input.

`output/remediation/opus_audit/REVERSAL_3_INPUT.jsonl` names every write the audit decided to
revert (a final revert, not superseded) by its `change_key`, with the quotes of the verdicts that
decided it - and no journal row. This builder turns it into the list the journal-reversal lane
reads (`reversal.py --lane journal-reversal-3`):

* **the journal row** of each change key, read from production read-only (`read_journal`), refused
  unless it is exactly one row and exactly the write the line names - `unified_sites`, the site, the
  column, the old and the written value;
* **the period label** of every `period_start` row whose restored start falls in another bucket
  (`bucket_changes`): the period-name lane re-derived `period_name` from the written start, and the
  label row that did it names that start's journal row in its evidence
  (`remediation_change_log:<id>`, `read_labels`). Restoring the start without it would leave a label
  of another bucket, which `reversal.keep_the_period_label` refuses. A start no label row cites is
  listed alone (`Built.unlabelled`) - the lane decides whether its label holds it;
* **`REASONS.json`** in the lane's directory: each audit row quoting its deciding verdicts as
  `opus:<change_key>` (checked by `reversal.quote_problem` against the audit's own files), each label
  quoting its own journal row's evidence (`journal`), and the input's sha256;
* **`reversal_3_list.py`**, generated beside this module: the journal ids `lane.REVERSAL_LISTS`
  names, which `REASONS.json` must name too (`reversal.load_reasons`).

Nothing here writes to production. After it: `reversal.py --lane journal-reversal-3 --collect
--write`, then `apply.py --lane journal-reversal-3` (AUDIT_LOG.md, "journal-reversal-3").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.apply import lane_dir  # noqa: E402
from mechanical.lane import REVERSAL_3, sql_literal  # noqa: E402
from mechanical.plan import PlanError, psql_json_reader, sql_ids  # noqa: E402
from pipeline.utils.text import categorize_period  # noqa: E402

INPUT = "output/remediation/opus_audit/REVERSAL_3_INPUT.jsonl"
LIST_MODULE = _HERE.parent / "reversal_3_list.py"
#: The only keys the audit's input holds: a phase-3 write's `change_key`, spliced into SQL.
CHANGE_KEY = re.compile(r"phase3:[0-9a-f]{64}")
ABOUT = (
    "The third journal-reversal list, read by scripts/remediation/mechanical/reversal.py --lane "
    "journal-reversal-3 and built by reversal_opus.py --write from the Opus re-verification's "
    "REVERSAL_3_INPUT.jsonl (source): every write the audit decided to revert (a final revert, not "
    "superseded), its journal row read from production by change_key, quoting the verdicts that "
    "decided it as opus:<change_key> - checked against output/remediation/opus_audit/ "
    "DECISIONS.jsonl and the verdict files it names, each quote found by the audit's machine quote "
    "check -; and the period_name label the period-name lane derived from each period_start whose "
    "restored start falls in another bucket, quoting that label row's own journal evidence. The "
    "list must equal lane.REVERSAL_3_JOURNAL_IDS (reversal_3_list.py)."
)

Reader = Callable[[str], list[dict[str, Any]]]


# ------------------------------------------------------------------------------ production
def read_journal(reader: Reader, keys: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """Every journal row of each change key, read-only, grouped by key (a key with no row is
    absent: `build_list` refuses it)."""
    wanted = sorted(set(keys))
    for key in wanted:
        if not CHANGE_KEY.fullmatch(key):
            raise PlanError(f"{key!r} is not a phase-3 change key - refusing to send it")
    listed = ", ".join(sql_literal(key) for key in wanted)
    found: dict[str, list[dict[str, Any]]] = {}
    for row in reader(
        "SELECT id, change_key, table_name, column_name, row_pk, old_value, new_value "
        f"FROM remediation_change_log WHERE change_key IN ({listed}) ORDER BY id"
    ):
        found.setdefault(str(row["change_key"]), []).append(row)
    return found


def read_labels(reader: Reader, site_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Every `period_name` journal row of the sites, read-only, with its evidence."""
    sites = sorted(set(site_ids))
    if not sites:
        return []
    return reader(
        "SELECT id, row_pk, run_stamp, old_value, new_value, evidence FROM remediation_change_log "
        "WHERE table_name = 'unified_sites' AND column_name = 'period_name' "
        f"AND row_pk IN ({sql_ids(sites)}) ORDER BY id"
    )


# ------------------------------------------------------------------------------ the list
def _bucket(value: str) -> str | None:
    return categorize_period(int(value))


def changes_bucket(r: Mapping[str, Any]) -> bool:
    """Whether the row is a `period_start` whose restored start is in another bucket."""
    return r["column"] == "period_start" and _bucket(r["old_value"]) != _bucket(r["new_value"])


def bucket_changes(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The `period_start` rows whose restored start falls in another bucket than the written one."""
    return [r for r in rows if changes_bucket(r)]


@dataclass(frozen=True)
class Built:
    """`REASONS.json`, the journal ids it names, and the starts no label row cites."""

    reasons: dict[str, Any]
    ids: tuple[int, ...]
    unlabelled: tuple[str, ...]


def _journal_row(r: Mapping[str, Any], found: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """The one journal row that is exactly the write the input line names."""
    if len(found) != 1:
        raise PlanError(
            f"{r['change_key']} ({r['name']}): {len(found)} journal row(s) - a change key is "
            "one write"
        )
    (row,) = found
    wrote = (row["table_name"], row["column_name"], row["row_pk"])
    wrote += (row["old_value"], row["new_value"])
    named = ("unified_sites", r["column"], r["site_id"], r["old_value"], r["new_value"])
    if wrote != named:
        raise PlanError(
            f"journal row {row['id']} wrote {wrote!r}, the Opus input names {named!r} for "
            f"{r['change_key']}"
        )
    return row


def _label(
    r: Mapping[str, Any], start_id: int, labels: Sequence[Mapping[str, Any]]
) -> tuple[Mapping[str, Any], str] | None:
    """The period-name lane's row whose evidence names the start's journal row, and that quote."""
    cites = f"remediation_change_log:{start_id}"
    found = [
        (row, e["quote"])
        for row in labels
        if row["row_pk"] == r["site_id"]
        for e in row["evidence"] or ()
        if e.get("source") == cites
    ]
    if len(found) > 1:
        ids = [row["id"] for row, _ in found]
        raise PlanError(
            f"{r['name']}: two label rows {ids} cite the start's journal row {start_id}"
        )
    return found[0] if found else None


def build_list(
    rows: Sequence[Mapping[str, Any]],
    journal: Mapping[str, Sequence[Mapping[str, Any]]],
    labels: Sequence[Mapping[str, Any]],
    *,
    source_sha256: str,
) -> Built:
    """A pure function of its inputs (module docstring)."""
    entries: list[dict[str, Any]] = []
    unlabelled: list[str] = []
    for r in rows:
        key = r["change_key"]
        row = _journal_row(r, journal.get(key, ()))
        entries.append(
            {
                "journal_id": int(row["id"]),
                "site_id": r["site_id"],
                "name": r["name"],
                "column": r["column"],
                "reason": r["reason"],
                "quotes": [{"source": f"opus:{key}", "text": q["text"]} for q in r["quotes"]],
                "residual": r["residual"],
            }
        )
        if not changes_bucket(r):
            continue
        label = _label(r, int(row["id"]), labels)
        if label is None:
            unlabelled.append(r["name"])
            continue
        label_row, quote = label
        entries.append(
            {
                "journal_id": int(label_row["id"]),
                "site_id": r["site_id"],
                "name": r["name"],
                "column": "period_name",
                "reason": (
                    f"the period-name lane derived {label_row['new_value']!r} from the period_start "
                    f"{r['new_value']} that journal row {row['id']} wrote; this list restores "
                    f"period_start {r['old_value']} (bucket {_bucket(r['old_value'])!r}) and the "
                    f"label that row replaced, {label_row['old_value']!r}"
                ),
                "quotes": [{"source": "journal", "text": quote}],
                "residual": "",
            }
        )
    ids = [e["journal_id"] for e in entries]
    if len(set(ids)) != len(ids):
        twice = sorted({i for i in ids if ids.count(i) > 1})
        raise PlanError(f"journal rows {twice} are named twice - one reversal per journal row")
    return Built(
        reasons={
            "_about": ABOUT,
            "source": {"file": INPUT, "sha256": source_sha256, "rows": len(rows)},
            "reversals": sorted(entries, key=lambda e: e["journal_id"]),
        },
        ids=tuple(sorted(ids)),
        unlabelled=tuple(unlabelled),
    )


def render_list_module(ids: Sequence[int], source_sha256: str) -> str:
    """`reversal_3_list.py`: the journal ids as generated code, 13 to a line."""
    lines = [
        '"""The journal rows journal-reversal-3 reverses - generated, do not edit by hand.',
        "",
        "Written by `scripts/remediation/mechanical/reversal_opus.py --write` from",
        f"`{INPUT}`",
        f"(sha256 {source_sha256}). REASONS.json in",
        "`output/remediation/mechanical_reversal_3/` must name exactly these rows.",
        '"""',
        "",
        "JOURNAL_IDS: tuple[int, ...] = (",
        *(
            "    " + " ".join(f"{i}," for i in ids[start : start + 13])
            for start in range(0, len(ids), 13)
        ),
        ")  # fmt: skip",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build journal-reversal-3's list (read-only)")
    ap.add_argument("--write", action="store_true", help="read production and write the list")
    ap.add_argument("--input", type=Path, default=REPO / INPUT)
    ap.add_argument("--out", type=Path, help="the lane's directory unless given")
    ap.add_argument("--module", type=Path, default=LIST_MODULE)
    args = ap.parse_args(argv)
    if not args.write:
        ap.print_help()
        return 0
    out = lane_dir(REVERSAL_3) if args.out is None else args.out
    try:
        data = args.input.read_bytes()
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line]
        reader = psql_json_reader()
        journal = read_journal(reader, [r["change_key"] for r in rows])
        labels = read_labels(reader, [r["site_id"] for r in bucket_changes(rows)])
        sha = hashlib.sha256(data).hexdigest()
        built = build_list(rows, journal, labels, source_sha256=sha)
    except PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    (out / "REASONS.json").write_text(
        json.dumps(built.reasons, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    args.module.write_text(render_list_module(built.ids, sha), encoding="utf-8", newline="\n")
    reversals = built.reasons["reversals"]
    summary = {
        "input_rows": len(rows),
        "journal_rows": len(built.ids),
        "labels": sum(e["column"] == "period_name" for e in reversals),
        "sites": len({e["site_id"] for e in reversals}),
        "bucket_changes": len(bucket_changes(rows)),
        "unlabelled": list(built.unlabelled),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
