"""The candidate search's command line: the search itself, over the rest inventory's population.

```bash
./.venv/Scripts/python.exe scripts/remediation/candidate_search/run.py \
    --population output/remediation/import_hero/RESTBESTAND_2026-10-06.jsonl \
    --out output/remediation/candidate_search/candidates-2026-10-06 \
    --min-width 800 --min-height 300
```

`--limit 100` is a pilot: the same run over the first 100 sites of the population, with the same
cache, so the full run re-asks nothing the pilot already answered.

The population is the rest inventory's own file: one line per site, and `--class` picks the ones
whose `what_would_close_it` says why they are open. A population of curated sites without a picture
is what the search is for; a site whose gallery already holds the candidate is excluded by name, so
the model's judgement is never spent on a picture the page already serves.

Commons is asked at `PACE` seconds between two requests (Wikimedia's robot policy asks for serial
requests) and every answer is cached under the run's `cache/`, so a second run over the same
population asks nothing twice - which is what makes the pilot's answers reusable in the full run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]
for _path in (_ROOT, _ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import httpx  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from served_image import commons as CM  # noqa: E402

from candidate_search import search as CS  # noqa: E402

DEFAULT_POPULATION = (
    _ROOT / "output" / "remediation" / "import_hero" / "RESTBESTAND_2026-10-06.jsonl"
)
HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}
PACE = 1.0
CACHE = "cache"


class SearchError(Exception):
    """A request the run refuses to guess its way past."""


def population(path: Path, closer: str | None) -> list[dict[str, Any]]:
    """The sites of the rest inventory a closer names, in the file's own order."""
    if not path.is_file():
        raise SearchError(f"{path} does not exist - the rest inventory is the population")
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if closer and record.get("what_would_close_it") != closer:
            continue
        out.append(
            {
                "site_id": record.get("site_id"),
                "name": record.get("name") or "",
                "country": record.get("country") or "",
            }
        )
    return out


def known_files(path: Path) -> set[str]:
    """The Commons files the gallery of every site of the population already holds."""
    if not path.is_file():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        out.add(CM.canonical_file(record.get("original_url") or ""))
        out.add(CM.canonical_file(record.get("filename") or ""))
    out.discard("")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="candidate_search/run.py", description=__doc__)
    parser.add_argument("--population", type=Path, default=DEFAULT_POPULATION)
    parser.add_argument("--class", dest="closer", default="no_picture_at_all")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-width", type=int, default=IH.OWNER_FLOOR_WIDTH)
    parser.add_argument("--min-height", type=int, default=IH.OWNER_FLOOR_HEIGHT)
    parser.add_argument("--limit", type=int, default=None, help="only the first N sites (a pilot)")
    parser.add_argument(
        "--gallery", type=Path, default=None, help="a READ.json, to exclude what it holds"
    )
    args = parser.parse_args(argv)
    try:
        sites = population(args.population, args.closer)
        if args.limit is not None:
            sites = sites[: args.limit]
        args.out.mkdir(parents=True, exist_ok=True)
        client = httpx.Client(timeout=30, follow_redirects=True, headers=HEADERS)
        commons = CM.Commons(cache=args.out / CACHE, client=client, pace=PACE, sleep=time.sleep)
        summary = CS.run(
            args.out,
            sites,
            commons,
            floor=(args.min_width, args.min_height),
            exclude=known_files(args.gallery) if args.gallery else (),
        )
    except (SearchError, CM.CommonsError, FileNotFoundError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
