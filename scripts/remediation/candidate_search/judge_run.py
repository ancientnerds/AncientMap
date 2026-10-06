"""The candidate judgement's command line: export (images + questions), import (answers),
write-targets (the `depicts` verdicts the INSERT lane's fetch takes).

```bash
$PY scripts/remediation/candidate_search/judge_run.py judge-export  --run-dir <run>
$PY scripts/remediation/candidate_search/judge_run.py judge-import  --run-dir <run> --handoff <H>
$PY scripts/remediation/candidate_search/judge_run.py write-targets --run-dir <run>
```

`judge-export` downloads every candidate's Commons rendering into `<run>/pictures/` and writes one
prompt per site into `<run>/<batch_id>/`, which is where the handoff reads it. An agent answers one
JSON object per site; `judge-import` reads the recorded answers back from the handoff (each recorded
under the name of the model that wrote it), checks every one of them and writes `VERDICTS.jsonl` plus
the refusals.

After `write-targets`, the wave is an ordinary INSERT wave: `import_hero/run.py fetch` takes the
`TARGETS.jsonl` pairs, and `insert-plan`, `insert_writer.py` and `insert-accept` are the same five
writer steps and the same acceptance every other write of this project used.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
for _path in (_ROOT, _ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import httpx  # noqa: E402

from candidate_search import judge as CJ  # noqa: E402
from candidate_search import search as CS  # noqa: E402

HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}
PACE = 1.0


class JudgeError(Exception):
    """A request the run refuses to guess its way past."""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise JudgeError(f"{path} does not exist - run the search first")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def recorded(handoff: Path) -> dict[str, dict[str, Any]]:
    """Every answer the handoff holds, keyed by the site it answers."""
    out: dict[str, dict[str, Any]] = {}
    manifest = handoff / "MANIFEST.jsonl"
    if not manifest.is_file():
        raise JudgeError(f"{manifest} does not exist - the handoff has recorded nothing yet")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("stage") not in (None, "judge"):
            continue
        label = str(record.get("label") or "")
        if not label:
            continue
        answer_path = handoff / f"{label}.answer.json"
        if answer_path.is_file():
            out[label] = json.loads(answer_path.read_text(encoding="utf-8"))
    return out


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="candidate_search/judge_run.py", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("judge-export", "judge-import", "write-targets"):
        command = commands.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        if name == "judge-import":
            command.add_argument("--handoff", type=Path, required=True)
        if name == "judge-export":
            command.add_argument("--images-per-batch", type=int, default=CJ.IMAGES_PER_BATCH)
            command.add_argument("--sites-per-batch", type=int, default=CJ.SITES_PER_BATCH)
    args = parser.parse_args(argv)
    try:
        if args.command == "judge-export":
            client = httpx.Client(timeout=60, follow_redirects=True, headers=HEADERS)
            summary = CJ.export(
                args.run_dir,
                read_jsonl(args.run_dir / CS.CANDIDATES),
                client,
                images_per_batch=args.images_per_batch,
                sites_per_batch=args.sites_per_batch,
            )
        elif args.command == "judge-import":
            sites = {
                str(site["site_id"]): site for site in read_jsonl(args.run_dir / CS.CANDIDATES)
            }
            summary = CJ.import_answers(args.run_dir, recorded(args.handoff), sites)
        else:
            summary = CJ.write_targets(args.run_dir, read_jsonl(args.run_dir / CJ.VERDICTS))
    except (JudgeError, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
