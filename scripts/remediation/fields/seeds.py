"""WD1: the fields an earlier reading already found wrong - asked whatever the machine says.

The classification (`classify.py`) asks a field when a machine source contradicts it or cannot
speak. Two earlier Opus readings found fields wrong that a machine source may well "confirm" - a
Wikidata item that repeats the wrong bucket, a P625 on the same wrong village:

* **the stage-1 measurement of the acceptance `draw-2026-09-25b`** (FINISH_PLAN section 2: 60
  sites, 652 questions, the run ended as a measurement by owner decision O1): every counted WRONG
  verdict on a WD1 field. A `period_name` verdict asks `period_start` - the label is the bucket of
  the start (`GOLD_STANDARD.md:79`) and is derived by the write plan. The ten planted canaries
  (`CANARIES.jsonl`) judged a planted value, not the stored one: they are left out.
* **HUMAN_ONLY B13, the 21 "both wrong" cells** (`mechanical_wrong_both/SKIPPED.jsonl`, reasons
  `no-verbatim-evidence` and `judges-disagree`): the value before Phase 3 and the one Phase 3 wrote
  were both judged wrong, and no quote could carry the proposal. HUMAN_ONLY_DECISIONS (O6): "belegt
  ersetzen (woertliches Zitat ueber diese Staette), sonst leeren" - WD1 asks them.

    seeds.py build --out RUN [--stage1 DIR] [--wrong-both FILE]

writes RUN/SEEDS.jsonl (`classify.SEED_KEYS`: site_id, field, source, finding), sorted, and prints the
counts. The inputs are gitignored data of the main checkout; their default paths are this repository's
`output/remediation/...`. Nothing is fetched and production is not asked. A seed about a site that
is retired or outside the harvest is listed by the classification's COUNTS (`seeds`), not applied.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import classify as C  # noqa: E402

STAGE1_DIR = REPO / "output" / "remediation" / "acceptance" / "draw-2026-09-25b"
WRONG_BOTH = REPO / "output" / "remediation" / "mechanical_wrong_both" / "SKIPPED.jsonl"
STAGE1_SOURCE = "acceptance draw-2026-09-25b stage 1"
WRONG_BOTH_SOURCE = "HUMAN_ONLY B13 (wrong-both)"
#: The stage-1 fields WD1 answers, and the field each one asks.
STAGE1_FIELDS = {
    "coordinates": "coordinates",
    "period_start": "period_start",
    "period_name": "period_start",
    "site_type": "site_type",
    "source_url": "source_url",
}
#: The wrong-both refusals that are B13's 21 cells; the other reasons were settled elsewhere
#: (kept by the audit, or rewritten by another lane).
WRONG_BOTH_REASONS = frozenset({"no-verbatim-evidence", "judges-disagree"})
#: How much of an earlier reasoning a question shows.
FINDING_CHARS = 600


class SeedError(ValueError):
    """An input is not what this builder reads. Nothing is written."""


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SeedError(f"{path} is missing")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= FINDING_CHARS else text[: FINDING_CHARS - 3].rstrip() + "..."


def stage1_seeds(
    rows: Iterable[Mapping[str, Any]], canaries: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Every counted WRONG verdict of stage 1 on a WD1 field, the canaries left out."""
    planted = {(str(c["site_id"]), str(c["field"])) for c in canaries}
    out: list[dict[str, Any]] = []
    for row in rows:
        final = row["final"]
        if not final or final["verdict"] != "WRONG" or row["field"] not in STAGE1_FIELDS:
            continue
        if (str(row["site_id"]), str(row["field"])) in planted:
            continue
        attempt = row["attempts"][final["attempt"]]
        answer = attempt["answer"]
        if not attempt["counted"] or answer["verdict"] != "WRONG":
            raise SeedError(f"{row['label']}: the final verdict is not its counted attempt's")
        said = f"an independent Opus check judged the stored {row['field']} WRONG"
        if answer.get("right_value") not in (None, ""):
            said += f" (it proposed {answer['right_value']!r})"
        out.append(
            {
                "site_id": str(row["site_id"]),
                "field": STAGE1_FIELDS[row["field"]],
                "source": STAGE1_SOURCE,
                "finding": _clip(f"{said}: {answer['reasoning']}"),
            }
        )
    return out


def wrong_both_seeds(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """B13: the wrong-both cells no quote could carry."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if row["reason"] not in WRONG_BOTH_REASONS:
            continue
        if row["column"] not in C.FIELDS:
            raise SeedError(f"{row['site_id']}: a B13 cell on {row['column']!r}, not a WD1 field")
        proposal = row["proposed_value"]
        said = (
            f"two Opus readings found both the value before Phase 3 and the one Phase 3 wrote "
            f"wrong ({row['reason']}"
            + (f"; proposed {proposal!r}" if proposal is not None else "")
            + f"): {row['note']}"
        )
        out.append(
            {
                "site_id": str(row["site_id"]),
                "field": str(row["column"]),
                "source": WRONG_BOTH_SOURCE,
                "finding": _clip(said),
            }
        )
    return out


def build(out: Path, *, stage1_dir: Path, wrong_both: Path) -> dict[str, Any]:
    seeds = stage1_seeds(
        _jsonl(stage1_dir / "judging" / "STAGE1.jsonl"), _jsonl(stage1_dir / "CANARIES.jsonl")
    ) + wrong_both_seeds(_jsonl(wrong_both))
    seeds.sort(key=lambda s: (s["site_id"], C.FIELDS.index(s["field"]), s["source"], s["finding"]))
    for seed in seeds:
        if tuple(seed) != C.SEED_KEYS:
            raise SeedError(f"a seed carries {list(seed)}, not {list(C.SEED_KEYS)}")
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(seed, ensure_ascii=False) + "\n" for seed in seeds)
    (out / C.SEEDS_FILE).write_text(text, encoding="utf-8", newline="\n")
    C.read_seeds(out)  # the classification's own reader accepts what was written
    return {
        "seeds": len(seeds),
        "sites": len({s["site_id"] for s in seeds}),
        "by_source_and_field": dict(
            sorted(Counter(f"{s['source']} / {s['field']}" for s in seeds).items())
        ),
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("build", help="RUN/SEEDS.jsonl from the two earlier readings")
    run.add_argument("--out", type=Path, default=C.DEFAULT_OUT)
    run.add_argument("--stage1", type=Path, default=STAGE1_DIR)
    run.add_argument("--wrong-both", type=Path, default=WRONG_BOTH)
    args = parser.parse_args(argv)
    try:
        result = build(args.out, stage1_dir=args.stage1, wrong_both=args.wrong_both)
    except (SeedError, C.ClassifyError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
