"""Where the write and acceptance instruments read and write, per lane, and the one reader they share.

Until 2026-09-22 every instrument hard-coded the mass run: `RUN = runs/mass`, `_write_dry/`,
`_write_apply/`, and the acceptance's `run_stamp LIKE 'phase3:batch-%'`. A second run (the gap run of
the 152 over-bound sites, the MiniMax search lane) would then have been planned from the wrong
directory, and `write_gate.py` would have skipped every one of its batches whose id happens to have an
`APPLIED.json` in the mass lane's apply root - 139 of the 149 batches that hold a gap field do. So a
**lane** now names all of it at once, and nothing of one lane can be read as another's:

| lane | run dir | dry plan | apply root | reviewer logs | journal stamps |
| --- | --- | --- | --- | --- | --- |
| `mass` (default) | `runs/mass` | `logs/_write_dry` | `logs/_write_apply` | `logs/review` | `phase3:batch-%` |
| `<name>` | `runs/<name>` | `logs/_write_dry_<name>` | `logs/_write_apply_<name>` | `logs/review_<name>` | `phase3:<prefix>-%` |

The default lane is exactly the paths the tools had before, so an invocation without `--lane` does
what it always did. The journal stamp of a lane is the writer's own (`write_stage.Chunk.stamp`,
`phase3:<batch_id>:chunk-NNNN`), so a lane's stamps are distinct exactly when its batch ids are: the
gap run's batches are `gap-NNNN`, never `batch-NNNN`.

The paths are derived from this file's own location (`output/remediation/tools/` or its working copy
in `output/remediation/logs/` - both three levels below the repository), so the tools run the same from
either place and from any clone.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

REPO = pathlib.Path(__file__).resolve().parents[3]
REMEDIATION = REPO / "output" / "remediation"
LOGS = REMEDIATION / "logs"
RUNS = REMEDIATION / "phase3_runner" / "runs"
LEDGER = REMEDIATION / "phase3_runner" / "LEDGER.jsonl"
WRITER = REPO / "scripts" / "remediation" / "phase3" / "write_stage.py"
RUNNER = REPO / "scripts" / "remediation" / "phase3" / "run.py"

#: The lane whose paths every instrument defaulted to before lanes existed.
MASS = "mass"

#: A lane's batch-id prefix, which is also its journal stamp's: `phase3:<prefix>-NNNN:chunk-NNNN`.
#: `gap` is the re-run of the fields the mass run never judged (`gap_plan.py`); `search1` and
#: `redecide` are the lanes the 2026-09-22 remaining-work map names (`srch-NNNN`, `rdc-NNNN`).
BATCH_PREFIX: dict[str, str] = {MASS: "batch", "gap": "gap", "search1": "srch", "redecide": "rdc"}


@dataclass(frozen=True)
class Lane:
    """Every path and pattern one lane's instruments use. Built by `lane()`, never by hand."""

    name: str
    run_dir: pathlib.Path
    dry_root: pathlib.Path
    apply_root: pathlib.Path
    review_logs: pathlib.Path
    stamp_like: str

    @property
    def rows(self) -> pathlib.Path:
        return self.dry_root / "ALL_ROWS.jsonl"

    @property
    def refused(self) -> pathlib.Path:
        return self.dry_root / "ALL_REFUSED.jsonl"

    @property
    def holds(self) -> pathlib.Path:
        return self.apply_root / "HOLDS.jsonl"


def lane(name: str = MASS) -> Lane:
    """The paths of one lane. An unknown lane is refused: its batch-id prefix would be a guess."""
    if name not in BATCH_PREFIX:
        raise SystemExit(
            f"unknown lane {name!r}: known lanes are {sorted(BATCH_PREFIX)}; a new lane needs its "
            "batch-id prefix in lanes.BATCH_PREFIX, because that prefix is its journal stamp"
        )
    suffix = "" if name == MASS else f"_{name}"
    return Lane(
        name=name,
        run_dir=RUNS / name,
        dry_root=LOGS / f"_write_dry{suffix}",
        apply_root=LOGS / f"_write_apply{suffix}",
        review_logs=LOGS / f"review{suffix}",
        stamp_like=f"phase3:{BATCH_PREFIX[name]}-%",
    )


def read_jsonl(path: pathlib.Path) -> list[dict]:
    """A JSON-lines file, every line an object. A blank line is skipped; a broken one is named."""
    records: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: not readable JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise SystemExit(f"{path}:{number}: not a JSON object")
        records.append(record)
    return records


def write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    """One object per line, UTF-8, LF - the shape `read_jsonl` reads back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )
