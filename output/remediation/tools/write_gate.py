"""Gate the planned rows against each site's own coordinates, then write them in steps of a hundred.

Why the gate is not inside the writer: `write_stage.py` is frozen, and its plan is a pure function of a
batch's own files - which carry no coordinates. The gate needs the coordinates and the boundary
polygons the project ships, so it sits in the driver that hands rows to the writer, while the writer
keeps its conditional WHERE, its journal and its own read-back unchanged.

Why the gate exists at all: of the ten `country` rows the reviewer cleared, three were name collisions
five thousand and ten thousand kilometres from the coordinates of the row they claim to describe, and a
fourth is a political line (2026-09-21, `AUDIT_LOG.md`, `country_probe.py`). A country proposal must
contain the site's own coordinates - those coordinates are not part of any write, they were curated, and
a name that matches a continent away is the finder's error rather than a correction.

Steps: the writer's unit is a batch, so this driver walks batches in order and applies only the allowed
rows - plain `--apply` for a batch whose rows all pass, `--chunk-size 1 --chunk K` for a batch where the
gate withheld one. Every `--step` sites it stops, reads the affected rows back out of the database
itself and prints what it found, so the owner's "after every hundred, a check, and only then continue"
is a check rather than a promise. A batch that is done gets a marker file, so a second run resumes
instead of rewriting rows whose old value is no longer there to match.

Without `--apply` this is a report.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import subprocess
import sys

# A console that cannot encode a site name must not be able to kill a production write: this tool
# prints its refusals and its holds *before* it writes the first row, so one encoding error aborts the
# whole wave. Measured 2026-09-22: a cp1252 console died on U+0259 with nothing written.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        _reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(r"C:/PythonProjects/AncientMap")
SCRIPTS = ROOT / "scripts/remediation"
LOGS = ROOT / "output/remediation/logs"
RUN = ROOT / "output/remediation/phase3_runner/runs/mass"
WRITER = SCRIPTS / "phase3/write_stage.py"
PYTHON = ROOT / ".venv/Scripts/python.exe"

sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(LOGS))

import country_census as C  # noqa: E402 - the one alias map and point-in-polygon test
from phase3 import (
    write_stage as W,  # noqa: E402 - its psql seam and SQL quoting are the tested ones
)


def read_rows(path: pathlib.Path) -> list[dict]:
    rows: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: not readable JSON: {exc}") from exc
    return rows


def psql_json_rows(sql: str, *, host: str) -> list[dict]:
    """A `to_jsonb(...)::text` read comes back as one JSON object per line.

    A line that is not one is damage rather than something to skip: every read in this driver goes
    through `to_jsonb` precisely so that a value containing the field separator cannot shift a column.
    """
    try:
        text = W.run_sql(sql, host=host)
    except W.WriteRefused as exc:
        raise SystemExit(f"die Datenbank hat nicht geantwortet: {exc}") from exc
    rows: list[dict] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"psql lieferte keine JSON-Zeile ({number}): {line[:120]!r}") from exc
    return rows


def coordinates(site_ids: set[str], *, host: str) -> dict[str, tuple[float, float]]:
    """The coordinates of every site a country row mentions, in one read-only statement."""
    if not site_ids:
        return {}
    ids = ", ".join(W._sql_text(site_id) for site_id in sorted(site_ids))
    sql = (
        "SELECT to_jsonb(t)::text FROM (SELECT id::text AS id, lat::float8 AS lat, lon::float8 AS lon "
        f"FROM unified_sites WHERE id IN ({ids})) AS t;"
    )
    found: dict[str, tuple[float, float]] = {}
    for payload in psql_json_rows(sql, host=host):
        if payload["lat"] is None or payload["lon"] is None:
            continue
        found[payload["id"]] = (payload["lat"], payload["lon"])
    return found


def gate(
    rows: list[dict], positions: dict[str, tuple[float, float]]
) -> dict[str, tuple[bool, str]]:
    """Per planned row: may it be written, and if not, why - in the words of the boundary file."""
    names, geometries, tree = C.load_countries()
    verdicts: dict[str, tuple[bool, str]] = {}
    for row in rows:
        key = row["change_key"]
        if row["column"] != "country":
            verdicts[key] = (True, "")
            continue
        position = positions.get(row["site_id"])
        if position is None:
            verdicts[key] = (False, "no coordinates for this site")
            continue
        here = C.country_at(names, geometries, tree, *position)
        if not here:
            verdicts[key] = (False, f"the point {position} falls in no boundary polygon")
            continue
        if C.canonical(row["new_value"]) not in {C.canonical(item) for item in here}:
            verdicts[key] = (
                False,
                f"the point {position} lies in {', '.join(here)}, not in {row['new_value']!r}"
                " - the evidence matched a different place of the same name",
            )
            continue
        verdicts[key] = (True, "")
    return verdicts


def load_holds(path: pathlib.Path) -> dict[str, str]:
    """The rows the hand-read refused: change_key -> the reason, one line each.

    The owner's rule of 2026-09-21 reads the first hundred by hand. This is that reading: a row whose
    own reviewer reason does not carry both halves of its claim, or whose evidence does not show the
    proposed value, is refused here - before a statement is rendered, next to the boundary check.
    """
    if not path.exists():
        return {}
    holds: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: not readable JSON: {exc}") from exc
        holds[record["change_key"]] = record["hold_reason"]
    return holds


def read_back(rows: list[dict], *, host: str) -> list[str]:
    """What the database holds for the rows just written, read without asking the writer."""
    if not rows:
        return []
    ids = ", ".join(W._sql_text(row["pk"]) for row in rows)
    columns = sorted({row["column"] for row in rows})
    selects = ", ".join(f"{column}::text AS {column}" for column in columns)
    sql = (
        f"SELECT to_jsonb(t)::text FROM (SELECT id::text AS id, {selects} "
        f"FROM unified_sites WHERE id IN ({ids})) AS t;"
    )
    stored: dict[str, dict[str, str | None]] = {}
    for payload in psql_json_rows(sql, host=host):
        site_id = payload.pop("id")
        stored[site_id] = dict(payload)
    problems: list[str] = []
    for row in rows:
        got = stored.get(row["pk"], {}).get(row["column"])
        if got != row["new_value"]:
            problems.append(
                f"{row['site_name'][:34]}.{row['column']}: geplant {row['new_value']!r}, "
                f"in der Datenbank steht {got!r}"
            )
    return problems


def write_batch(batch: str, rows: list[dict], ok_indexes: list[int], *, host: str) -> dict:
    """Apply one batch - the whole plan, or exactly the allowed rows of it."""
    out = LOGS / "_write_apply" / batch
    out.mkdir(parents=True, exist_ok=True)
    calls: list[tuple[str, list[str]]] = []
    if len(ok_indexes) == len(rows):
        calls.append(("all", []))
    else:
        calls.extend(
            (f"row-{index}", ["--chunk-size", "1", "--chunk", str(index)]) for index in ok_indexes
        )
    written = sites = matched_0 = journal = 0
    for tag, extra in calls:
        command = [
            str(PYTHON),
            str(WRITER),
            "--batch-dir",
            str(RUN / batch),
            "--out",
            str(out),
            "--host",
            host,
            "--apply",
            *extra,
        ]
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            # `phase3.model` imports `pipeline.normalizers`, so the child needs the repository on its
            # own import path. Carrying it here rather than inheriting it from the calling shell means
            # the gate runs the same way from a bare prompt as it does from the acceptance above.
            env={**os.environ, "PYTHONPATH": f"{ROOT}{os.pathsep}{SCRIPTS}"},
        )
        (out / f"{tag}.json").write_text(proc.stdout, encoding="utf-8")
        (out / f"{tag}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            raise SystemExit(
                f"der Schreiber hat abgelehnt ({batch} {tag}), exit {proc.returncode}:"
                f"\n{proc.stderr.strip()[-600:]}"
            )
        start = proc.stdout.find("{")
        if start < 0:
            raise SystemExit(f"der Schreiber hat keinen JSON-Bericht gedruckt ({batch} {tag})")
        try:
            report = json.loads(proc.stdout[start:])
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"der Bericht des Schreibers ist kein JSON ({batch} {tag}): {exc}"
            ) from exc
        written += report.get("rows_written") or 0
        sites += report.get("sites_planned") or 0
        matched_0 += report.get("rows_matched_0") or 0
        journal += report.get("journal_rows_added") or 0
        # The writer dumps the plan it read into --out. One call per allowed row means the next call
        # would overwrite it, so it is kept under the call's own name instead of left to look like a
        # plan nobody applied.
        dumped = out / "PLAN.jsonl"
        if dumped.exists():
            dumped.replace(out / f"{tag}.plan.jsonl")
    (out / "APPLIED.json").write_text(
        json.dumps(
            {"batch_id": batch, "rows_written": written, "sites": sites}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    return {"written": written, "sites": sites, "matched_0": matched_0, "journal": journal}


def main() -> int:
    parser = argparse.ArgumentParser(prog="write-gate")
    parser.add_argument("--rows", default=str(LOGS / "_write_dry" / "ALL_ROWS.jsonl"))
    parser.add_argument("--host", default=W.SSH_HOST)
    parser.add_argument("--step", type=int, default=100, help="sites per step, checked after each")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many sites (0 = all)")
    parser.add_argument("--hold", default=str(LOGS / "_write_apply" / "HOLDS.jsonl"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    rows = read_rows(pathlib.Path(args.rows))
    if not rows:
        raise SystemExit(f"{args.rows}: no planned rows")
    positions = coordinates(
        {row["site_id"] for row in rows if row["column"] == "country"}, host=args.host
    )
    verdicts = gate(rows, positions)
    holds = load_holds(pathlib.Path(args.hold))
    for row in rows:
        if row["change_key"] in holds:
            verdicts[row["change_key"]] = (
                False,
                f"Zurueckgehalten nach Handpruefung: {holds[row['change_key']]}",
            )
    refused = [row for row in rows if not verdicts[row["change_key"]][0]]
    print(
        f"geplante Zeilen: {len(rows)} | von den Grenzen abgelehnt: "
        f"{len(refused) - len(holds)} | zurueckgehalten: {len(holds)}"
    )
    for row in refused:
        tag = "ZURUECKGEHALTEN" if row["change_key"] in holds else "ABGELEHNT"
        print(
            f"  {tag} {row['site_name'][:30]:32} {row['column']:12} "
            f"{row['old_value']!r} -> {row['new_value']!r}: {verdicts[row['change_key']][1]}"
        )

    by_batch: dict[str, list[dict]] = collections.OrderedDict()
    for row in rows:
        by_batch.setdefault(row["batch_id"], []).append(row)

    todo = []
    for batch, batch_rows in sorted(by_batch.items()):
        if (LOGS / "_write_apply" / batch / "APPLIED.json").exists():
            continue
        ok_indexes = [
            index for index, row in enumerate(batch_rows, start=1) if verdicts[row["change_key"]][0]
        ]
        if ok_indexes:
            todo.append((batch, batch_rows, ok_indexes))
    sites_todo = sum(len(indexes) for _, _, indexes in todo)
    print(
        f"offene Batches: {len(todo)} | Zeilen darin: {sites_todo}"
        f" | {'SCHREIBEN' if args.apply else 'Probelauf, es wird nichts geschrieben'}"
    )
    if not args.apply:
        return 0

    done_sites = done_rows = done_journal = done_matched_0 = 0
    written_rows: list[dict] = []
    next_check = args.step
    for batch, batch_rows, ok_indexes in todo:
        outcome = write_batch(batch, batch_rows, ok_indexes, host=args.host)
        done_sites += outcome["sites"]
        done_rows += outcome["written"]
        done_journal += outcome["journal"]
        done_matched_0 += outcome["matched_0"]
        written_rows.extend(batch_rows[index - 1] for index in ok_indexes)
        print(
            f"{batch} zeilen={outcome['written']} sites={outcome['sites']} "
            f"matched_0={outcome['matched_0']} journal={outcome['journal']} | "
            f"gesamt {done_sites} Sites",
            flush=True,
        )
        if done_sites >= next_check:
            problems = read_back(written_rows, host=args.host)
            print(
                f"\n=== PRUEFUNG nach {done_sites} Sites: {done_rows} Zeilen geschrieben, "
                f"{done_journal} Journaleintraege, {len(problems)} Abweichungen",
                flush=True,
            )
            for problem in problems:
                print(f"  ABWEICHUNG {problem}")
            print("=== Ende der Pruefung\n", flush=True)
            next_check += args.step
        if args.limit and done_sites >= args.limit:
            print(f"Halt nach {done_sites} Sites (--limit {args.limit}).", flush=True)
            break

    problems = read_back(written_rows, host=args.host)
    print(
        f"\nfertig: {done_rows} Zeilen fuer {done_sites} Sites geschrieben, "
        f"{done_journal} Journaleintraege, matched_0={done_matched_0}, "
        f"Abweichungen beim Nachlesen: {len(problems)}"
    )
    for problem in problems:
        print(f"  ABWEICHUNG {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
