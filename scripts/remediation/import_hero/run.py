"""The import-hero lane's four commands: `plan`, `fetch`, `accept`, `remainder`.

```bash
./.venv/Scripts/python.exe scripts/remediation/import_hero/run.py plan     --run-dir $R
./.venv/Scripts/python.exe scripts/remediation/import_hero/run.py fetch    --run-dir $R --root $IMAGES
./.venv/Scripts/python.exe scripts/remediation/import_hero/run.py accept   --run-dir $R
./.venv/Scripts/python.exe scripts/remediation/import_hero/run.py remainder --run-dir $R
```

`plan` is read-only against production and writes only into the run directory: the read, the join
and the chunks the shared writer (`gallery_audit.chunk_writer`) then applies, five steps each, in
section 3.7 of `docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md`.

`fetch` is the step before those sites can be planned at all: the 1600 px derivative of every file
the plan refused as `local_file_too_small`. It reads the run's own claims and refusals, downloads
into the tree the caller names - the offsite copy, never the VPS, which is a separate transfer -
and writes the manifest that `plan --fetched` reads. Nothing else in this module touches the
network.

`accept` is the other half: it reads production **again**, after the chunks landed, and asks the
owner's three questions per planned site. It never reuses the plan's read - that one describes what
production looked like before, which is exactly what an acceptance cannot settle.

`remainder` is what a lane's last step needs: `write_chunks` refuses an empty plan by name, which
is right for a writer and useless as a completion number. This reports the empty plan and what it
still refuses.

This module is the lane's thin glue; the tested surface is `plan`, `read`, `verify` and `fetch`
(like `served_image/run.py`, whose commands are covered the same way).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from served_image import state as ST  # noqa: E402

from import_hero import fetch as IF  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from import_hero import read as RD  # noqa: E402
from import_hero import verify as IV  # noqa: E402

DEFAULT_IMPORT = Path("data/raw/ancient_nerds/ancient_nerds_original.geojson")
ACCEPTANCE_READ = "VERIFY_READ.json"
ACCEPTANCE = "ACCEPTANCE.json"
REMAINDER = "REMAINDER.json"
CLAIMS = "IMPORT_CLAIMS.json"
REFUSALS = "IMPORT_HERO_REFUSALS.jsonl"
FETCHED = "FETCHED.json"
FETCH_FAILURES = "FETCH_FAILURES.jsonl"


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True, default=str))


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise IH.ImportHeroError(
            f"{path} does not exist - run `plan --run-dir {path.parent}` first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise IH.ImportHeroError(
            f"{path} does not exist - run `plan --run-dir {path.parent}` first"
        )
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


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
) -> dict[str, Any]:
    """The read, the join and the chunks. Nothing outside `run` is written."""
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
    )
    return {
        "read_sha256": sha,
        "import_features": len(features),
        "shown_sites": len(state.sites),
        **summary,
    }


def cmd_accept(run: Path) -> int:
    """The wave's three questions, asked of a fresh production read. Writes ACCEPTANCE.json."""
    data = RD.read_production()
    read_path = run / ACCEPTANCE_READ
    if read_path.is_file():
        read_path.unlink()
    sha = RD.write_read(read_path, data)
    state = ST.load_read(read_path)
    result = IV.check_wave(state, _load(run / CLAIMS), IV.wave_site_ids(run))
    record = {
        "run_id": run.name,
        "read_sha256": sha,
        "read_at": state.read_at,
        "shown_sites": len(state.sites),
        "chunks": sorted(p.name for p in run.glob("chunk-0*")),
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
    planned = IH.plan(state, claims, dimensions=RD.dimensions(data))
    by_reason: dict[str, int] = {}
    for refusal in planned.refusals:
        by_reason[refusal.reason] = by_reason.get(refusal.reason, 0) + 1
    record = {
        "run_id": run.name,
        "read_sha256": state.sha256,
        "read_at": state.read_at,
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


def cmd_fetch(
    run: Path,
    *,
    root: Path,
    out: Path | None = None,
    limit: int | None = None,
    delay_s: float | None = None,
) -> dict[str, Any]:
    """The 1600 px fetch for the `local_file_too_small` refusals of this run.

    Every target lands in `root`, which the caller names: the offsite copy is where this lane reads
    its pictures (runbook 3.2), the VPS copy is what production serves, and the transfer between
    them is a separate, explicit step - nothing here writes to the VPS.

    `limit` takes the first N targets, for the pilot before a wave of several hundred, and `out`
    writes the manifest somewhere else than the run directory, because a manifest is written once
    per path and a pilot has to leave room for the wave's own.
    """
    targets = IF.plan_targets(_load(run / CLAIMS), _load_jsonl(run / REFUSALS))
    if limit is not None:
        targets = targets[:limit]
    manifest, failures = IF.fetch_manifest(targets, root, delay_s=delay_s)
    path = out or (run / FETCHED)
    digest = IF.write_manifest(path, manifest)
    path.with_name(FETCH_FAILURES).write_text(
        "".join(
            json.dumps(
                {"site_id": site_id, "commons_file": commons_file, "why": why},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
            for site_id, commons_file, why in failures
        ),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "run_id": run.name,
        "targeted": len(targets),
        "fetched": len(manifest),
        "failed": len(failures),
        "fetched_json": str(path),
        "fetched_sha256": digest,
        "root": str(root),
    }


def _stamp(run: Path) -> str:
    """The run stamp every journal row of this wave carries: the run directory's own name."""
    return run.name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="import_hero/run.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    commands: dict[str, argparse.ArgumentParser] = {}
    helps = {
        "plan": "read production, join the 2025 import, write the chunks (writes only into R)",
        "fetch": "download the 1600 px files the plan refused as too small, into --root",
        "accept": "read production again and ask the three questions per planned site",
        "remainder": "what the lane would still write over this run's read, and what it refuses",
    }
    for name, help_text in helps.items():
        commands[name] = sub.add_parser(name, help=help_text)
        commands[name].add_argument("--run-dir", required=True, type=Path)
    commands["plan"].add_argument("--import", dest="source", type=Path, default=DEFAULT_IMPORT)
    commands["plan"].add_argument("--sites-per-chunk", type=int, default=100)
    commands["plan"].add_argument("--fetched", type=Path, default=None)
    commands["fetch"].add_argument("--root", required=True, type=Path)
    commands["fetch"].add_argument("--out", type=Path, default=None)
    commands["fetch"].add_argument("--limit", type=int, default=None)
    commands["fetch"].add_argument("--delay", dest="delay_s", type=float, default=None)
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            _print(
                cmd_fetch(
                    args.run_dir,
                    root=args.root,
                    out=args.out,
                    limit=args.limit,
                    delay_s=args.delay_s,
                )
            )
            return 0
        if args.command == "accept":
            return cmd_accept(args.run_dir)
        if args.command == "remainder":
            return cmd_remainder(args.run_dir)
        _print(
            cmd_plan(
                args.run_dir,
                source=args.source,
                sites_per_chunk=args.sites_per_chunk,
                fetched=args.fetched,
            )
        )
    except (IH.ImportHeroError, ST.StateError, FileNotFoundError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
