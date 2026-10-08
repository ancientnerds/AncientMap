"""The candidate judgement's command line: export (images + questions), import (answers),
write-targets (the `depicts` verdicts the INSERT lane's fetch takes).

```bash
$PY scripts/remediation/candidate_search/judge_run.py judge-export  --run-dir <run>
$PY scripts/remediation/candidate_search/judge_run.py judge-import  --run-dir <run>
$PY scripts/remediation/candidate_search/judge_run.py write-targets --run-dir <run>
```

`judge-export` downloads every candidate's Commons rendering into `<run>/pictures/` and writes one
prompt per site into `<run>/<batch_id>/`, which is where the question lives. An agent writes its
answer to `<run>/<batch_id>/<site_id>.answer.json` and **has to name itself and its model** there -
`judge-import` refuses an answer without that stamp, because the audit of a wrong picture is what this
stage exists for. `judge-import` checks every answer and writes `VERDICTS.jsonl` plus the refusals.

After `write-targets` the wave is an ordinary INSERT wave, in three steps that were missing until
`insert-claims` and `import_hero/run.py read` wrote them:

```bash
$PY judge_run.py insert-claims --run-dir <this run> --insert-run <the INSERT wave's run dir>
$PY import_hero/run.py read        --run-dir <the INSERT wave's run dir>
$PY import_hero/run.py fetch       --run-dir <the INSERT wave's run dir> --root <offsite> --target insert
```

`insert-claims` writes the two records the fetch reads - `IMPORT_CLAIMS.json` (the URL of the file
the judge chose) and the `no_target_row` refusal that names the site - because until now only the
2025 import wrote them. `read` writes the `READ.json` the insert plan measures its rows against; the
import lane gets that read from `fetch --start`, which would also have fetched the import's own 417
targets. `insert-plan`, `insert_writer.py` and `insert-accept` are then the same five writer steps
and the same acceptance every other write of this project used.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
for _path in (_ROOT, _ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import httpx  # noqa: E402
from served_image import commons as CM  # noqa: E402

from candidate_search import judge as CJ  # noqa: E402
from candidate_search import run as CR  # noqa: E402
from candidate_search import search as CS  # noqa: E402

HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}
PACE = 1.0


class JudgeError(Exception):
    """A request the run refuses to guess its way past."""


class PacedDownloads(CM.Commons):
    """`Commons`' own pacing, for a download whose non-200 is a refusal and not an exception.

    `judge-export` asks for one rendering per candidate: 190 for the pilot, 5,809 for the full run.
    The `PACE` this module defined was never used, so those downloads went out back to back, and a
    `HTTP 429` would have been recorded as a refused candidate - the site would have lost a picture
    it could have had, by name, for a reason that was never about the picture. The pacing is the one
    the search stage already applies to its questions (Wikimedia's robot policy asks for serial
    requests); only the refusal handling differs, because here a non-200 is an answer.
    """

    def __init__(
        self,
        client: Any,
        cache: Path,
        *,
        pace: float = PACE,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(cache=cache, client=client, pace=pace, sleep=sleep, clock=clock)

    def get(self, url: str) -> Any:
        self._wait(url)
        return self.client.get(url)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise JudgeError(f"{path} does not exist - run the search first")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def recorded(out: Path) -> dict[str, dict[str, Any]]:
    """Every answer the run's batch folders hold, keyed by the site it answers.

    An answer is a `<run>/<batch_id>/<site_id>.answer.json` beside the question it answers, and it
    has to name the agent and the model that judged - a verdict without that stamp is refused by
    `judge.check_answer`, because the audit of a wrong picture is the point of this stage.
    """
    found: dict[str, dict[str, Any]] = {}
    folders = sorted(p for p in out.glob("cand-*") if p.is_dir())
    if not folders:
        raise JudgeError(f"{out} holds no cand-* batch folder - run judge-export first")
    for folder in folders:
        for answer_path in sorted(folder.glob("*.answer.json")):
            answer = json.loads(answer_path.read_text(encoding="utf-8"))
            found[str(answer.get("site_id") or answer_path.stem)] = answer
    return found


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="candidate_search/judge_run.py", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("judge-export", "judge-import", "write-targets", "insert-claims"):
        command = commands.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
        if name == "judge-export":
            command.add_argument("--images-per-batch", type=int, default=CJ.IMAGES_PER_BATCH)
            command.add_argument("--sites-per-batch", type=int, default=CJ.SITES_PER_BATCH)
            command.add_argument(
                "--limit",
                type=int,
                default=None,
                help="only the first N sites with candidates - a pilot that measures the "
                "judgement's precision over the run's real candidates",
            )
        if name == "insert-claims":
            command.add_argument(
                "--insert-run",
                type=Path,
                default=None,
                help="the INSERT wave's run directory (insert-claims writes its claims and refusals)",
            )
            command.add_argument(
                "--sites",
                type=Path,
                default=None,
                help="only these targets (a file of site ids, one per line): a re-seed",
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "judge-export":
            client = PacedDownloads(
                httpx.Client(timeout=60, follow_redirects=True, headers=HEADERS),
                args.run_dir / CR.CACHE,
            )
            sites = read_jsonl(args.run_dir / CS.CANDIDATES)
            if args.limit is not None:
                sites = sites[: args.limit]
            summary = CJ.export(
                args.run_dir,
                sites,
                client,
                images_per_batch=args.images_per_batch,
                sites_per_batch=args.sites_per_batch,
            )
        elif args.command == "judge-import":
            sites = {
                str(site["site_id"]): site for site in read_jsonl(args.run_dir / CS.CANDIDATES)
            }
            summary = CJ.import_answers(args.run_dir, recorded(args.run_dir), sites)
        elif args.command == "write-targets":
            summary = CJ.write_targets(args.run_dir, read_jsonl(args.run_dir / CJ.VERDICTS))
        else:
            if not args.insert_run:
                raise JudgeError(
                    "insert-claims writes the INSERT wave's records into another directory: "
                    "--insert-run names it"
                )
            listed = (
                None
                if args.sites is None
                else [
                    line.strip()
                    for line in args.sites.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            )
            summary = CJ.insert_claims(args.run_dir, args.insert_run, listed)
    except (JudgeError, OSError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
