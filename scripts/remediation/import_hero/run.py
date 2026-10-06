"""The import-hero lane's commands: `plan`, `fetch`, `insert-plan`, `accept`, `insert-accept`, `remainder`.

```bash
./.venv/Scripts/python.exe scripts/remediation/import_hero/run.py plan     --run-dir $R
run.py fetch    --run-dir $R --root $OFFSITE
run.py insert-plan  --run-dir $R
run.py insert-accept --run-dir $R
./.venv/Scripts/python.exe scripts/remediation/import_hero/run.py accept   --run-dir $R
./.venv/Scripts/python.exe scripts/remediation/import_hero/run.py remainder --run-dir $R
```

`plan` is read-only against production and writes only into the run directory: the read, the join
and the chunks the shared writer (`gallery_audit.chunk_writer`) then applies, five steps each, in
section 3.7 of `docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md`.

`fetch` is the step that has to come first for the sites the plan refuses as
`local_file_too_small`: it downloads the 1600 px derivative each of them needs and writes the
`FETCHED.json` manifest that `plan --fetched` reads. It takes the same read and the same join,
so it names the same sites, and it is resumable - `fetch.run_fetch` carries the manifest along
after every file, because `download_image` opens with `O_EXCL`. Its `--root` is the offsite
copy of the image tree; the VPS copy has to follow it, the two must not drift.

`accept` is the other half: it reads production **again**, after the chunks landed, and asks the
owner's three questions per planned site. It never reuses the plan's read - that one describes what
production looked like before, which is exactly what an acceptance cannot settle.

`insert-plan` and `insert-accept` are the same two halves for the INSERT wave
(`import_hero/insert.py`), which creates rows instead of moving flags: `chunk_writer` refuses an
INSERT, so `insert_writer.py` is its writer and its read-back.

`remainder` is what a lane's last step needs: `write_chunks` refuses an empty plan by name, which
is right for a writer and useless as a completion number. This reports the empty plan and what it
still refuses.

This module is the lane's thin glue; the tested surface is `plan`, `read`, `fetch` and `verify` (like
`served_image/run.py`, whose commands are covered the same way).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from served_image import state as ST  # noqa: E402

from import_hero import fetch as IF  # noqa: E402
from import_hero import insert as IN  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from import_hero import read as RD  # noqa: E402
from import_hero import verify as IV  # noqa: E402

DEFAULT_IMPORT = Path("data/raw/ancient_nerds/ancient_nerds_original.geojson")
ACCEPTANCE_READ = "VERIFY_READ.json"
ACCEPTANCE = "ACCEPTANCE.json"
ACCEPTANCE_INSERT = "ACCEPTANCE_INSERT.json"
REMAINDER = "REMAINDER.json"
CLAIMS = "IMPORT_CLAIMS.json"
REFUSALS = "IMPORT_HERO_REFUSALS.jsonl"
FETCHED = "FETCHED.json"
FETCH_FAILURES = "FETCH_FAILURES.jsonl"
FLOOR = "FLOOR.json"


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True, default=str))


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise IH.ImportHeroError(
            f"{path} does not exist - run `plan --run-dir {path.parent}` first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """A record file of one object per line, as the lane writes them."""
    if not path.is_file():
        raise IH.ImportHeroError(
            f"{path} does not exist - run `plan --run-dir {path.parent}` first"
        )
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _floor_of(run: Path, min_width: int | None, min_height: int | None) -> tuple[int, int]:
    """The `(width, height)` this run serves, from the flags or from the run's own `FLOOR.json`.

    A run that was planned at the owner's lowered floor must be fetched at the same floor, or the
    fetch refuses what the plan would have accepted. Writing the pair into the run directory is
    what makes that checkable instead of remembered.
    """
    if min_width is not None and min_height is not None:
        return min_width, min_height
    if min_width is not None or min_height is not None:
        raise IH.ImportHeroError(
            "--min-width and --min-height travel together: one floor, both halves"
        )
    path = run / FLOOR
    if path.is_file():
        recorded = _load(path)
        return int(recorded["min_width"]), int(recorded["min_height"])
    return IH.HERO_MIN_WIDTH, IH.HERO_MIN_HEIGHT


def _write_floor(run: Path, floor: tuple[int, int]) -> None:
    run.mkdir(parents=True, exist_ok=True)
    (run / FLOOR).write_text(
        json.dumps(
            {
                "min_width": floor[0],
                "min_height": floor[1],
                "note": (
                    "the size a local file must reach for this run; the lane's own is "
                    f"{IH.HERO_MIN_WIDTH}x{IH.HERO_MIN_HEIGHT}, and the owner's lowered floor is "
                    f"{IH.OWNER_FLOOR_WIDTH}x{IH.OWNER_FLOOR_HEIGHT} (owner decision 2026-10-06, "
                    '"for these cases the existing picture becomes the hero")'
                ),
            },
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_once(run: Path) -> tuple[dict[str, Any], str]:
    """The run's read: written once per run directory, loaded again on a second `plan`."""
    path = run / RD.READ
    if path.is_file():
        data = _load(path)
        return data, RD.digest(data)
    data = RD.read_production()
    run.mkdir(parents=True, exist_ok=True)
    return data, RD.write_read(path, data)


def cmd_plan(
    run: Path,
    *,
    source: Path = DEFAULT_IMPORT,
    sites_per_chunk: int = 100,
    fetched: Path | None = None,
    floor: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """The read, the join and the chunks. Nothing outside `run` is written."""
    served = _floor_of(run, floor[0] if floor else None, floor[1] if floor else None)
    _write_floor(run, served)
    data, sha = _read_once(run)
    state = ST.load_read(run / RD.READ)
    features = IH.read_import(source)
    claims = IH.join_import(state, features)
    run.mkdir(parents=True, exist_ok=True)
    (run / CLAIMS).write_text(
        json.dumps(claims, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = IH.write_chunks(
        run,
        state,
        claims,
        run_stamp=_stamp(run),
        dimensions=RD.dimensions(data),
        fetched=json.loads(fetched.read_text(encoding="utf-8")) if fetched else None,
        sites_per_chunk=sites_per_chunk,
        floor=served,
    )
    return {
        "read_sha256": sha,
        "import_features": len(features),
        "shown_sites": len(state.sites),
        "floor": {"min_width": served[0], "min_height": served[1]},
        **summary,
    }


def cmd_fetch(
    run: Path,
    *,
    source: Path = DEFAULT_IMPORT,
    root: Path,
    out: Path | None = None,
    limit: int | None = None,
    delay_s: float | None = None,
    target: str = "hero",
    start: bool = False,
    floor: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """The 1600 px files the `local_file_too_small` refusals need, and the manifest `plan --fetched`
    reads. Writes only into the run directory and `root`; production is read at most once, and only
    when the run holds no records of its own (`_wave_of`).

    The run directory is the same one the wave will be planned and applied in: one read, one join,
    one set of site ids. A second `fetch` over it continues where the first stopped - the manifest
    is the resume point, and the sites it carries are not fetched again.

    `out` writes the manifest somewhere else than the run directory, for a pilot that has to leave
    the wave's own path free.
    """
    served = _floor_of(run, floor[0] if floor else None, floor[1] if floor else None)
    _write_floor(run, served)
    data, sha, claims, refusals = _wave_of(run, source, start=start, floor=served)
    by_reason: dict[str, int] = {}
    for refusal in refusals:
        by_reason[str(refusal.get("reason"))] = by_reason.get(str(refusal.get("reason")), 0) + 1
    reasons = {"hero": ("local_file_too_small",), "insert": ("no_target_row",)}[target]
    targets = IF.plan_targets(claims, refusals, reasons=reasons)
    if limit is not None:
        targets = targets[:limit]
    manifest_path = out or (run / FETCHED)

    def progress(site_id: str, entry: dict[str, str]) -> None:
        # stderr, not stdout: stdout is this command's one JSON summary, and a wave of 800
        # downloads has to be watchable while it runs.
        print(
            f"fetched {site_id} -> {entry['filename']} "
            f"({entry['width']}x{entry['height']}, {entry['file_size_bytes']} bytes)",
            file=sys.stderr,
            flush=True,
        )

    outcome = IF.run_fetch(
        targets,
        root,
        manifest_path,
        failures_path=run / FETCH_FAILURES,
        delay_s=delay_s,
        on_site=progress,
        floor=served,
    )
    return {
        "run_id": run.name,
        "read_sha256": sha,
        "offsite_root": str(root),
        "wave": target,
        "floor": {"min_width": served[0], "min_height": served[1]},
        "refusal_classes_fetched_for": list(reasons),
        "refusals_of_the_plan": by_reason,
        **outcome.as_json(),
    }


def _write_refusals(run: Path, refusals: Sequence[IH.Refusal]) -> Path:
    """The plan's refusal record, one object per line - the work list a fetch works from."""
    path = run / REFUSALS
    path.write_text(
        "".join(
            json.dumps(refusal.as_json(), ensure_ascii=False, sort_keys=True) + "\n"
            for refusal in refusals
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _wave_of(
    run: Path,
    source: Path,
    *,
    start: bool = False,
    floor: tuple[int, int] | None = None,
) -> tuple[dict[str, Any] | None, str, dict[str, Any], list[dict[str, Any]]]:
    """`(read, digest, claims, refusals)` of this run, from its own records where it has them.

    The run's `plan` writes both: `IMPORT_CLAIMS.json` and `IMPORT_HERO_REFUSALS.jsonl`. A wave
    whose plan holds nothing to write never got that far - `write_chunks` refuses an empty plan by
    name, which is right for a writer - so those records are absent, and the run's own `READ.json`
    decides: the same read, the same join, the same refusals, and still no second production read.
    """
    claims_path = run / CLAIMS
    refusals_path = run / REFUSALS
    if claims_path.is_file() and refusals_path.is_file():
        read_path = run / RD.READ
        data = _load(read_path) if read_path.is_file() else None
        return data, RD.digest(data) if data else "", _load(claims_path), _load_jsonl(refusals_path)
    read_path = run / RD.READ
    if not read_path.is_file():
        if not run.is_dir() and not start:
            raise IH.ImportHeroError(
                f"{run} does not exist - run `plan --run-dir {run}` first, or pass --start to read "
                "production for a wave that has not started yet"
            )
        run.mkdir(parents=True, exist_ok=True)
        # A run directory that exists but holds nothing is a wave that has not been read yet: the
        # fetch is what the plan's refusals are needed for, so it takes the first read itself.
        data, sha = _read_once(run)
        state = ST.load_read(run / RD.READ)
        claims = IH.join_import(state, IH.read_import(source))
        claims_path.parent.mkdir(parents=True, exist_ok=True)
        claims_path.write_text(
            json.dumps(claims, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        planned = IH.plan(state, claims, dimensions=RD.dimensions(data), floor=floor)
        _write_refusals(run, planned.refusals)
        return data, sha, claims, [r.as_json() for r in planned.refusals]
    data, sha = _read_once(run)
    state = ST.load_read(read_path)
    claims = IH.join_import(state, IH.read_import(source))
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    claims_path.write_text(
        json.dumps(claims, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    planned = IH.plan(state, claims, dimensions=RD.dimensions(data), floor=floor)
    _write_refusals(run, planned.refusals)
    return data, sha, claims, [r.as_json() for r in planned.refusals]


def cmd_accept(run: Path, *, fetched: Path | None = None) -> int:
    """The wave's three questions, asked of a fresh production read. Writes ACCEPTANCE.json."""
    data = RD.read_production()
    read_path = run / ACCEPTANCE_READ
    if read_path.is_file():
        read_path.unlink()
    sha = RD.write_read(read_path, data)
    state = ST.load_read(read_path)
    manifest = fetched or (run / FETCHED)
    result = IV.check_wave(
        state,
        _load(run / CLAIMS),
        IV.wave_site_ids(run),
        fetched=_load(manifest) if manifest.is_file() else None,
    )
    record = {
        "run_id": run.name,
        "read_sha256": sha,
        "read_at": state.read_at,
        "shown_sites": len(state.sites),
        "chunks": sorted(p.name for p in run.glob("chunk-0*")),
        "fetched_manifest": manifest.name if manifest.is_file() else None,
        **result.as_json(),
    }
    (run / ACCEPTANCE).write_text(
        json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    _print(record)
    if not result.ok:
        print(f"REFUSED: {len(result.problems)} site(s) answer a question wrongly", file=sys.stderr)
        return 1
    return 0


def cmd_remainder(run: Path) -> int:
    """What the lane would still write over the run's own read, and what it still refuses."""
    data = _load(run / RD.READ)
    state = ST.load_read(run / RD.READ)
    claims = _load(run / CLAIMS)
    floor = _floor_of(run, None, None)
    planned = IH.plan(state, claims, dimensions=RD.dimensions(data), floor=floor)
    by_reason: dict[str, int] = {}
    for refusal in planned.refusals:
        by_reason[refusal.reason] = by_reason.get(refusal.reason, 0) + 1
    record = {
        "run_id": run.name,
        "read_sha256": state.sha256,
        "read_at": state.read_at,
        "floor": {"min_width": floor[0], "min_height": floor[1]},
        "sites_with_an_import_image": sum(1 for c in claims.values() if c.get("image")),
        "planned_rows": len(planned.changes),
        "planned_sites": len({c.site_id for c in planned.changes}),
        "may_empty_sites": len(planned.may_empty),
        "refused_sites": len(planned.refusals),
        "refusals": by_reason,
    }
    (run / REMAINDER).write_text(
        json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    _print(record)
    return 0


def cmd_insert_plan(
    run: Path,
    *,
    rows_per_chunk: int = 50,
    fetched: Path | None = None,
) -> dict[str, Any]:
    """The rows the INSERT wave would create, and the sites it refuses by name.

    Read-only against production: it takes the run's own `READ.json`, the plan's own
    `IMPORT_HERO_REFUSALS.jsonl` and the fetch's `FETCHED.json`, and writes only into the run
    directory. A site whose fetch was refused stays refused - a row cannot name a file that is not
    on disk - which is what `INSERT_REFUSALS.jsonl` records.
    """
    read_path = run / RD.READ
    if not read_path.is_file():
        raise IH.ImportHeroError(
            f"{read_path} does not exist - the fetch of this wave writes it; run "
            f"`fetch --target insert --run-dir {run}` first"
        )
    manifest_path = fetched or (run / FETCHED)
    state = ST.load_read(read_path)
    planned = IN.plan(state, _load_jsonl(run / REFUSALS), fetched=_load(manifest_path))
    chunks = IN.write_chunks(planned, run, per_chunk=rows_per_chunk)
    return {
        "run_id": run.name,
        "read_sha256": state.sha256,
        "fetched_manifest": manifest_path.name,
        "chunks": len(chunks),
        "stamps": [chunk.run_stamp for chunk in chunks],
        "journal_rows": sum(row.journal_rows for chunk in chunks for row in chunk.inserts),
        **planned.as_json(),
    }


def _planned_inserts(run: Path) -> list[IN.Insert]:
    """The rows the wave's chunks plan, as they were planned - not as a second plan would see them."""
    chunks = sorted(run.glob("chunk-0*"))
    if not chunks:
        raise IH.ImportHeroError(f"{run} holds no chunk - run `insert-plan` first")
    out: list[IN.Insert] = []
    for directory in chunks:
        path = directory / "INSERT.jsonl"
        if not path.is_file():
            raise IH.ImportHeroError(f"{path} does not exist")
        out.extend(
            IN.Insert.from_json(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return out


def cmd_insert_accept(run: Path) -> int:
    """The INSERT wave's three questions, asked of a fresh production read. Writes ACCEPTANCE_INSERT.json."""
    inserts = _planned_inserts(run)
    data = RD.read_production()
    read_path = run / ACCEPTANCE_READ
    if read_path.is_file():
        read_path.unlink()
    sha = RD.write_read(read_path, data)
    state = ST.load_read(read_path)
    result = IN.check(state, inserts)
    record = {
        "run_id": run.name,
        "read_sha256": sha,
        "read_at": state.read_at,
        "shown_sites": len(state.sites),
        "chunks": sorted(p.name for p in run.glob("chunk-0*")),
        **result,
    }
    (run / ACCEPTANCE_INSERT).write_text(
        json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    _print(record)
    if not result["ok"]:
        print(
            f"REFUSED: {len(result['problems'])} site(s) answer a question wrongly", file=sys.stderr
        )
        return 1
    return 0


def _stamp(run: Path) -> str:
    """The run stamp every journal row of this wave carries: the run directory's own name."""
    return run.name


def main(argv: list[str] | None = None) -> int:
    # A Commons title carries every script of every site, and a Windows console encodes cp1252: one
    # file named in Turkish or Georgian kills the run in the middle of the wave with a
    # UnicodeEncodeError from a progress line (measured 2026-10-06, twice). The record is written
    # before the line is printed, so nothing was lost - but a wave of 800 downloads is no place for
    # a console to decide what may be printed. `backslashreplace` keeps every byte visible.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="import_hero/run.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    commands: dict[str, argparse.ArgumentParser] = {}
    helps = {
        "plan": "read production, join the 2025 import, write the chunks (writes only into R)",
        "fetch": "download the 1600 px file every `local_file_too_small` refusal needs -> FETCHED.json",
        "insert-plan": "the rows of the INSERT wave: chunk-001.., INSERT_REFUSALS.jsonl (writes only into R)",
        "insert-accept": "read production again and ask the INSERT wave's three questions per row",
        "accept": "read production again and ask the three questions per planned site",
        "remainder": "what the lane would still write over this run's read, and what it refuses",
    }
    for name, help_text in helps.items():
        commands[name] = sub.add_parser(name, help=help_text)
        commands[name].add_argument("--run-dir", required=True, type=Path)
    commands["plan"].add_argument("--import", dest="source", type=Path, default=DEFAULT_IMPORT)
    commands["plan"].add_argument("--sites-per-chunk", type=int, default=100)
    commands["plan"].add_argument("--fetched", type=Path, default=None)
    for name in ("plan", "fetch"):
        commands[name].add_argument(
            "--min-width",
            type=int,
            default=None,
            help=(
                "the width a local file must reach for this run, with --min-height; the owner's "
                f"lowered floor for the import picture of a site that already has one is "
                f"{IH.OWNER_FLOOR_WIDTH}x{IH.OWNER_FLOOR_HEIGHT}, the lane's own is "
                f"{IH.HERO_MIN_WIDTH}x{IH.HERO_MIN_HEIGHT}"
            ),
        )
        commands[name].add_argument(
            "--min-height", type=int, default=None, help="the height half of --min-width"
        )
    commands["fetch"].add_argument("--import", dest="source", type=Path, default=DEFAULT_IMPORT)
    commands["fetch"].add_argument(
        "--root",
        required=True,
        type=Path,
        help="the offsite copy of the image tree; the VPS copy has to follow it",
    )
    commands["fetch"].add_argument(
        "--out", type=Path, default=None, help="write the manifest here instead of into the run dir"
    )
    commands["fetch"].add_argument(
        "--start",
        action="store_true",
        help="read production for a wave that has no read yet (the INSERT wave starts one)",
    )
    commands["fetch"].add_argument(
        "--target",
        choices=("hero", "insert"),
        default="hero",
        help=(
            "which wave to fetch for: `hero` the sites whose row exists but whose file is too "
            "small, `insert` the sites that need a row for the import's file"
        ),
    )
    commands["fetch"].add_argument(
        "--limit", type=int, default=None, help="only the first N targets (a pilot)"
    )
    commands["fetch"].add_argument(
        "--delay", dest="delay_s", type=float, default=None, help="seconds between downloads"
    )
    commands["insert-plan"].add_argument("--rows-per-chunk", type=int, default=50)
    commands["insert-plan"].add_argument(
        "--fetched",
        type=Path,
        default=None,
        help="the fetch manifest to plan from (the run's own FETCHED.json by default)",
    )
    commands["accept"].add_argument(
        "--fetched",
        type=Path,
        default=None,
        help="the fetch manifest that resolved the import's links (the run's own FETCHED.json by "
        "default): a served row is then accepted by its upload URL, not by the slug in the link",
    )
    args = parser.parse_args(argv)
    try:
        # `plan` and `fetch` carry the floor flags; the other commands read the run's own FLOOR.json
        floor = None
        width, height = getattr(args, "min_width", None), getattr(args, "min_height", None)
        if width is not None or height is not None:
            floor = (width, height)
        if args.command == "fetch":
            _print(
                cmd_fetch(
                    args.run_dir,
                    source=args.source,
                    root=args.root,
                    out=args.out,
                    limit=args.limit,
                    delay_s=args.delay_s,
                    target=args.target,
                    start=args.start,
                    floor=floor,
                )
            )
            return 0
        if args.command == "insert-plan":
            _print(
                cmd_insert_plan(
                    args.run_dir, rows_per_chunk=args.rows_per_chunk, fetched=args.fetched
                )
            )
            return 0
        if args.command == "insert-accept":
            return cmd_insert_accept(args.run_dir)
        if args.command == "accept":
            return cmd_accept(args.run_dir, fetched=args.fetched)
        if args.command == "remainder":
            return cmd_remainder(args.run_dir)
        _print(
            cmd_plan(
                args.run_dir,
                source=args.source,
                sites_per_chunk=args.sites_per_chunk,
                fetched=args.fetched,
                floor=floor,
            )
        )
    except (IH.ImportHeroError, IF.FetchError, ST.StateError, FileNotFoundError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
