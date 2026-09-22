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

Which run it writes is the lane's (`lanes.py`): the default is the mass run, its `_write_dry/` rows,
its `_write_apply/` markers and holds - the paths it always had. `--lane gap` reads `runs/gap`,
`_write_dry_gap/ALL_ROWS.jsonl` and marks `_write_apply_gap/`, so an `APPLIED.json` of the mass lane
can never make a batch of another lane look done. Two guards were added with the lanes (2026-09-22),
both refusals before anything is written:

* every row's batch directory must exist in the run directory the rows are applied to - rows of one
  lane handed to another lane's run are refused, not re-planned from the wrong files;
* the writer re-plans each batch from its files, and the per-row apply addresses rows **by their
  position** in that plan (`--chunk-size 1 --chunk K`). A rows file that no longer matches the
  writer's plan - it was built before the writer gained a rule, such as the citation check - would
  shift every position after the first difference and write a different row than the one reviewed.
  So every open batch is re-planned dry first - in the dry run too, so the report is the proof -
  and its change keys must equal the rows file's, in order, before the first row of the wave.

**A check that finds something stops the wave** (2026-09-23). Until then three findings were printed
and walked past: a writer call that wrote fewer rows than it was handed (its pre-flight found a row
that had moved, so the writer - correctly - wrote none of the chunk and exited 0) still got its batch
an `APPLIED.json`, so a resume never looked at it again and the acceptance read its unwritten rows as
withheld; a step read-back with deviations went on to the next hundred; and a hold whose change key
names no planned row - one mistyped character in a hand-written `HOLDS.jsonl` - held nothing while the
count said it held one. Now: every writer report is checked against the rows the call was handed, a
mismatch leaves `STOPPED.json` (never `APPLIED.json`) and ends the wave, a later run refuses a stopped
batch until a person has looked, a read-back deviation ends the wave, and a hold that matches no row is
refused before anything is planned.
"""

from __future__ import annotations

import argparse
import collections
import json
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import country_census as C  # noqa: E402 - the one alias map and point-in-polygon test
import lanes  # noqa: E402 - the lane's paths, the JSON-lines reader and the database seam
import write_dry_all  # noqa: E402 - the writer's child environment, one spelling

#: The marker of a batch whose writer calls all wrote exactly what they were handed.
APPLIED_FILE = "APPLIED.json"
#: The marker of a batch whose writer report did not match what it was handed. Never resumed over.
STOPPED_FILE = "STOPPED.json"


def coordinates(site_ids: set[str], *, host: str) -> dict[str, tuple[float, float]]:
    """The coordinates of every site a country row mentions, in one read-only statement."""
    if not site_ids:
        return {}
    sql = (
        "SELECT to_jsonb(t)::text FROM (SELECT id::text AS id, lat::float8 AS lat, lon::float8 AS lon "
        f"FROM unified_sites WHERE id IN ({lanes.sql_literals(sorted(site_ids))})) AS t;"
    )
    found: dict[str, tuple[float, float]] = {}
    for payload in lanes.json_rows(lanes.psql(sql, host=host)):
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


def load_holds(path: pathlib.Path, rows: list[dict]) -> dict[str, str]:
    """The rows the hand-read refused: change_key -> the reason, one line each.

    The owner's rule of 2026-09-21 reads the first hundred by hand. This is that reading: a row whose
    own reviewer reason does not carry both halves of its claim, or whose evidence does not show the
    proposed value, is refused here - before a statement is rendered, next to the boundary check.

    A hold whose change key is not a planned row's is refused: it would hold nothing, and the row it
    was written for - one character off, typed by hand - would be written.
    """
    if not path.exists():
        return {}
    holds = {record["change_key"]: record["hold_reason"] for record in lanes.read_jsonl(path)}
    planned = {row["change_key"] for row in rows}
    stray = sorted(key for key in holds if key not in planned)
    if stray:
        raise SystemExit(
            f"{path}: {len(stray)} hold(s) name no planned row, so they would hold nothing: "
            f"{stray[:5]} - correct the change keys (copy them from the rows file) and run again"
        )
    return holds


def withheld(
    rows: list[dict], *, positions: dict[str, tuple[float, float]], holds: dict[str, str]
) -> dict[str, tuple[bool, str]]:
    """The gate's verdict per row, with the hand-read's holds on top: one decision, one spelling.

    The write and the acceptance (`verify_writes.py`) both read it, so the rows the gate leaves
    unwritten are exactly the rows the acceptance expects to find unwritten.
    """
    verdicts = gate(rows, positions)
    for row in rows:
        if row["change_key"] in holds:
            verdicts[row["change_key"]] = (
                False,
                f"held after the hand-read: {holds[row['change_key']]}",
            )
    return verdicts


def open_batches(
    rows: list[dict],
    verdicts: dict[str, tuple[bool, str]],
    *,
    run_dir: pathlib.Path,
    apply_root: pathlib.Path,
) -> list[tuple[str, list[dict], list[int]]]:
    """(batch, its rows, the 1-based positions to write) for every batch still to be written.

    A batch is done when **this lane's** apply root carries its `APPLIED.json` - never another lane's,
    which is the whole point of the lane. A row whose batch directory is not in `run_dir` is refused:
    the writer would re-plan it from files that are not the ones the rows came from. A batch that
    carries `STOPPED.json` is refused as well: some of its rows may be in the database and some not,
    and which is a person's reading (`verify_writes.py`), not a resume's guess.
    """
    by_batch: dict[str, list[dict]] = collections.OrderedDict()
    for row in rows:
        by_batch.setdefault(row["batch_id"], []).append(row)
    missing = sorted(batch for batch in by_batch if not (run_dir / batch).is_dir())
    if missing:
        raise SystemExit(
            f"{len(missing)} batch(es) of the rows file are not in {run_dir}: {missing[:5]} - "
            "the rows belong to another run; pass the lane they were planned in"
        )
    stopped = sorted(batch for batch in by_batch if (apply_root / batch / STOPPED_FILE).exists())
    if stopped:
        raise SystemExit(
            f"{len(stopped)} batch(es) stopped in an earlier wave and were never marked applied: "
            f"{stopped[:5]}. Read {apply_root / stopped[0] / STOPPED_FILE}, run verify_writes.py to "
            "see which of their rows are in the database, decide by hand, then remove the marker"
        )
    todo = []
    for batch, batch_rows in sorted(by_batch.items()):
        if (apply_root / batch / APPLIED_FILE).exists():
            continue
        ok_indexes = [
            index for index, row in enumerate(batch_rows, start=1) if verdicts[row["change_key"]][0]
        ]
        if ok_indexes:
            todo.append((batch, batch_rows, ok_indexes))
    return todo


def replan_keys(batch: str, *, run_dir: pathlib.Path, scratch: pathlib.Path) -> list[str]:
    """The change keys, in order, of the plan the writer builds for this batch **now** (dry)."""
    out = scratch / batch
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(lanes.WRITER), "--batch-dir", str(run_dir / batch), "--out", str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        env=write_dry_all.writer_env(),
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"the writer could not plan {batch} dry, exit {proc.returncode}:"
            f"\n{proc.stderr.strip()[-600:]}"
        )
    return [row["change_key"] for row in lanes.read_jsonl(out / lanes.W.PLAN_FILE)]


def assert_same_plan(batch: str, rows: list[dict], replanned: list[str]) -> None:
    """Refuse a batch whose rows file is not the plan the writer builds today, position by position.

    The per-row apply names rows by position (`--chunk K`), so one row missing from the writer's plan
    - a row a newer rule refuses - moves every later position onto a different row. Refused here,
    before any statement for the batch is run.
    """
    expected = [row["change_key"] for row in rows]
    if expected == replanned:
        return
    first = next(
        (
            index
            for index, (want, got) in enumerate(zip(expected, replanned, strict=False), start=1)
            if want != got
        ),
        min(len(expected), len(replanned)) + 1,
    )
    raise SystemExit(
        f"{batch}: the rows file names {len(expected)} row(s), the writer plans {len(replanned)} "
        f"today, and they first differ at position {first}. The rows file is stale. A lane that has "
        "written nothing yet is re-planned with write_dry_all.py (then read the holds again); a lane "
        "that has written keeps the plan it was written from (tools/README.md), and its open "
        "batches need a decision, not a silent re-plan"
    )


def read_back(rows: list[dict], *, host: str) -> list[str]:
    """What the database holds for the rows just written, read without asking the writer."""
    if not rows:
        return []
    columns = sorted({row["column"] for row in rows})
    selects = ", ".join(f"{column}::text AS {column}" for column in columns)
    sql = (
        f"SELECT to_jsonb(t)::text FROM (SELECT id::text AS id, {selects} "
        f"FROM unified_sites WHERE id IN ({lanes.sql_literals(row['pk'] for row in rows)})) AS t;"
    )
    stored: dict[str, dict[str, str | None]] = {}
    for payload in lanes.json_rows(lanes.psql(sql, host=host)):
        site_id = payload.pop("id")
        stored[site_id] = dict(payload)
    problems: list[str] = []
    for row in rows:
        got = stored.get(row["pk"], {}).get(row["column"])
        if got != row["new_value"]:
            problems.append(
                f"{row['site_name'][:34]}.{row['column']}: planned {row['new_value']!r}, "
                f"the database holds {got!r}"
            )
    return problems


def call_problems(report: dict, *, expected: int) -> list[str]:
    """What is wrong with one writer report for a call that was handed `expected` rows.

    The writer exits 0 when its pre-flight finds a moved row: it writes **none** of that chunk and
    records the chunk as skipped (`write_stage.apply_chunk`). That is the right refusal, and an exit
    code cannot carry it - so the report is read, and anything but "every row written and journalled"
    is a problem.
    """
    problems: list[str] = []
    if report.get("dry_run") is not False:
        problems.append(f"the report says dry_run={report.get('dry_run')!r}, not an applied write")
    written = report.get("rows_written")
    if written != expected:
        problems.append(f"{written!r} row(s) written, {expected} handed to the writer")
    if report.get("rows_matched_0"):
        problems.append(
            f"{report['rows_matched_0']} row(s) no longer held the planned old value: "
            f"{report.get('rows_matched_0_reasons')}"
        )
    skipped = [chunk for chunk in report.get("chunk_results") or [] if chunk.get("skipped")]
    for chunk in skipped:
        problems.append(f"chunk {chunk.get('chunk')} skipped: {chunk['skipped']}")
    if report.get("journal_rows_added") != written:
        problems.append(
            f"{report.get('journal_rows_added')!r} journal row(s) for {written!r} written row(s)"
        )
    return problems


def write_batch(
    batch: str,
    rows: list[dict],
    ok_indexes: list[int],
    *,
    host: str,
    run_dir: pathlib.Path,
    apply_root: pathlib.Path,
) -> dict:
    """Apply one batch - the whole plan, or exactly the allowed rows of it.

    `APPLIED.json` is written only when every call wrote exactly the rows it was handed. The first
    call whose report says otherwise writes `STOPPED.json` - what was written before it, what its
    report says - and stops the wave.
    """
    out = apply_root / batch
    out.mkdir(parents=True, exist_ok=True)
    calls: list[tuple[str, list[str], int]] = []
    if len(ok_indexes) == len(rows):
        calls.append(("all", [], len(rows)))
    else:
        calls.extend(
            (f"row-{index}", ["--chunk-size", "1", "--chunk", str(index)], 1)
            for index in ok_indexes
        )
    written = matched_0 = journal = 0
    done: list[str] = []
    for tag, extra, expected in calls:
        command = [
            sys.executable,
            str(lanes.WRITER),
            "--batch-dir",
            str(run_dir / batch),
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
            env=write_dry_all.writer_env(),
        )
        (out / f"{tag}.json").write_text(proc.stdout, encoding="utf-8")
        (out / f"{tag}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            _stop(out, batch, tag, done, [f"the writer exited {proc.returncode}"], None)
            raise SystemExit(
                f"the writer refused ({batch} {tag}), exit {proc.returncode}:"
                f"\n{proc.stderr.strip()[-600:]}"
            )
        start = proc.stdout.find("{")
        if start < 0:
            _stop(out, batch, tag, done, ["the writer printed no JSON report"], None)
            raise SystemExit(f"the writer printed no JSON report ({batch} {tag})")
        try:
            report = json.loads(proc.stdout[start:])
        except json.JSONDecodeError as exc:
            _stop(out, batch, tag, done, [f"the writer's report is not JSON: {exc}"], None)
            raise SystemExit(f"the writer's report is not JSON ({batch} {tag}): {exc}") from exc
        problems = call_problems(report, expected=expected)
        if problems:
            _stop(out, batch, tag, done, problems, report)
            raise SystemExit(
                f"STOP at {batch} {tag}: the writer did not write what it was handed - "
                + "; ".join(problems)
                + f". Nothing else is written; {out / STOPPED_FILE} records what was"
            )
        written += report["rows_written"]
        matched_0 += report["rows_matched_0"]
        journal += report["journal_rows_added"]
        done.append(tag)
        # The writer dumps the plan it read into --out. One call per allowed row means the next call
        # would overwrite it, so it is kept under the call's own name instead of left to look like a
        # plan nobody applied.
        dumped = out / "PLAN.jsonl"
        if dumped.exists():
            dumped.replace(out / f"{tag}.plan.jsonl")
    sites = len({rows[index - 1]["site_id"] for index in ok_indexes})
    (out / APPLIED_FILE).write_text(
        json.dumps(
            {"batch_id": batch, "rows_written": written, "sites": sites}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    return {"written": written, "sites": sites, "matched_0": matched_0, "journal": journal}


def _stop(
    out: pathlib.Path,
    batch: str,
    tag: str,
    done: list[str],
    problems: list[str],
    report: dict | None,
) -> None:
    """Leave the record a person needs before this batch can be touched again."""
    (out / STOPPED_FILE).write_text(
        json.dumps(
            {
                "batch_id": batch,
                "stopped_at_call": tag,
                "calls_written_before": done,
                "problems": problems,
                "report": report,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="write-gate")
    parser.add_argument("--lane", default=lanes.MASS, help="which run's paths (lanes.py)")
    parser.add_argument("--run-dir", default=None, help="override the lane's run directory")
    parser.add_argument("--rows", default=None, help="override the lane's ALL_ROWS.jsonl")
    parser.add_argument("--apply-root", default=None, help="override the lane's apply root")
    parser.add_argument("--hold", default=None, help="override the lane's HOLDS.jsonl")
    parser.add_argument("--host", default=lanes.HOST)
    parser.add_argument("--step", type=int, default=100, help="sites per step, checked after each")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many sites (0 = all)")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    paths = lanes.lane(args.lane)
    run_dir = pathlib.Path(args.run_dir) if args.run_dir else paths.run_dir
    rows_path = pathlib.Path(args.rows) if args.rows else paths.rows
    apply_root = pathlib.Path(args.apply_root) if args.apply_root else paths.apply_root
    hold_path = pathlib.Path(args.hold) if args.hold else paths.holds
    print(f"lane {paths.name}: {run_dir} | rows {rows_path} | markers {apply_root}")

    rows = lanes.read_jsonl(rows_path)
    if not rows:
        raise SystemExit(f"{rows_path}: no planned rows")
    lanes.assert_reviewed_plan(paths.name, rows, path=rows_path)
    holds = load_holds(hold_path, rows)
    positions = coordinates(
        {row["site_id"] for row in rows if row["column"] == "country"}, host=args.host
    )
    verdicts = withheld(rows, positions=positions, holds=holds)
    refused = [row for row in rows if not verdicts[row["change_key"]][0]]
    held = [row for row in refused if row["change_key"] in holds]
    print(
        f"planned rows: {len(rows)} | refused at the boundary: {len(refused) - len(held)} | "
        f"held: {len(held)}"
    )
    for row in refused:
        tag = "HELD" if row["change_key"] in holds else "REFUSED"
        print(
            f"  {tag:8} {row['site_name'][:30]:32} {row['column']:12} "
            f"{row['old_value']!r} -> {row['new_value']!r}: {verdicts[row['change_key']][1]}"
        )

    todo = open_batches(rows, verdicts, run_dir=run_dir, apply_root=apply_root)
    for batch, batch_rows, _ in todo:
        assert_same_plan(
            batch, batch_rows, replan_keys(batch, run_dir=run_dir, scratch=apply_root / "_replan")
        )
    print(f"plan checked: {len(todo)} open batches are the writer's plan of today")
    rows_todo = sum(len(indexes) for _, _, indexes in todo)
    print(
        f"open batches: {len(todo)} | rows in them: {rows_todo}"
        f" | {'WRITING' if args.apply else 'dry run, nothing is written'}"
    )
    if not args.apply:
        return 0

    done_sites = done_rows = done_journal = done_matched_0 = 0
    written_rows: list[dict] = []
    next_check = args.step
    for batch, batch_rows, ok_indexes in todo:
        outcome = write_batch(
            batch,
            batch_rows,
            ok_indexes,
            host=args.host,
            run_dir=run_dir,
            apply_root=apply_root,
        )
        done_sites += outcome["sites"]
        done_rows += outcome["written"]
        done_journal += outcome["journal"]
        done_matched_0 += outcome["matched_0"]
        written_rows.extend(batch_rows[index - 1] for index in ok_indexes)
        print(
            f"{batch} rows={outcome['written']} sites={outcome['sites']} "
            f"matched_0={outcome['matched_0']} journal={outcome['journal']} | "
            f"total {done_sites} sites",
            flush=True,
        )
        if done_sites >= next_check:
            problems = read_back(written_rows, host=args.host)
            print(
                f"\n=== CHECK after {done_sites} sites: {done_rows} rows written, "
                f"{done_journal} journal rows, {len(problems)} deviation(s)",
                flush=True,
            )
            for problem in problems:
                print(f"  DEVIATION {problem}")
            print("=== end of check\n", flush=True)
            if problems:
                raise SystemExit(
                    f"STOP after {done_sites} sites: the read-back found {len(problems)} "
                    "deviation(s); nothing more is written until they are understood"
                )
            next_check += args.step
        if args.limit and done_sites >= args.limit:
            print(f"Halt after {done_sites} sites (--limit {args.limit}).", flush=True)
            break

    problems = read_back(written_rows, host=args.host)
    print(
        f"\ndone: {done_rows} rows written for {done_sites} sites, "
        f"{done_journal} journal rows, matched_0={done_matched_0}, "
        f"read-back deviations: {len(problems)}"
    )
    for problem in problems:
        print(f"  DEVIATION {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
