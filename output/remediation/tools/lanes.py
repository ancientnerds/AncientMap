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

Two more things live here because every tool needs them once: the way to the database - the writer's
own `run_sql`, `_json_rows` and `_sql_text`, re-exported rather than copied - and the pin of the plan
each written lane was applied from (`REVIEWED_PLAN_KEYS_SHA256`).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[3]
# The writer imports `phase3` (from `scripts/remediation`) and `pipeline` (from the repository root).
for _root in (REPO, REPO / "scripts" / "remediation"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from phase3 import write_stage as W  # noqa: E402 - the one psql seam, parser and quoting

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
#: `redecide` are the lanes the 2026-09-22 remaining-work map names (`srch-NNNN`, `rdc-NNNN`);
#: `sitelink` re-asks the mass run's UNVERIFIABLE fields with the item's other-language articles
#: (`sitelink_plan.py`, `slk-NNNN`; its pilot's batches are `slkg-NNNN` and never write).
BATCH_PREFIX: dict[str, str] = {
    MASS: "batch",
    "gap": "gap",
    "search1": "srch",
    "redecide": "rdc",
    "sitelink": "slk",
}


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


# ------------------------------------------------------------------ the database, through the writer
# The tools reach production through the writer's own seam and read its answers with the writer's own
# parser - one spelling each (`write_stage.run_sql`, `_json_rows`, `_sql_text`), not a copy per tool.
# The writer raises `WriteRefused`; a tool is a command line, so here that becomes a named exit.

#: The production database's ssh alias - the writer's.
HOST = W.SSH_HOST


def psql(sql: str, *, host: str = HOST) -> str:
    """Send one statement to production through `write_stage.run_sql`; a failure stops the tool."""
    try:
        return W.run_sql(sql, host=host)
    except W.WriteRefused as exc:
        raise SystemExit(f"the database did not answer: {exc}") from exc


def json_rows(text: str) -> list[dict]:
    """One `to_jsonb(...)::text` object per line (`write_stage._json_rows`); anything else stops.

    Every read goes through `to_jsonb`, so a value that contains the field separator or a newline
    cannot shift a column or split a row.
    """
    try:
        return W._json_rows(text)
    except W.WriteRefused as exc:
        raise SystemExit(
            f"psql answered something that is not one JSON object per line: {exc}"
        ) from exc


#: A SQL text literal, quotes doubled, `NULL` for `None` - the writer's quoting.
sql_text = W._sql_text


def sql_literals(values: Iterable[str]) -> str:
    """A comma-separated list of SQL text literals (`sql_text` each)."""
    return ", ".join(sql_text(value) for value in values)


# ------------------------------------------------------------------ the plan a lane was written from
#: The plan each **written** lane's production rows were reviewed and applied against, pinned by the
#: sha256 of its change keys in file order (LF-joined, trailing LF). The rows file is regenerable -
#: `write_dry_all.py` re-plans from the batch files with the writer's rules of *today* - and a re-plan
#: after the writer gained a rule is a different file under the same name: on 2026-09-22 the citation
#: check turned the mass lane's 1,074 rows into 1,028, and the acceptance then read the 44 correct
#: production writes the new plan no longer names as 44 deviations. So the acceptance and the hold
#: list refuse a rows file that is not the pinned one, and `write_dry_all.py` refuses to overwrite a
#: lane that has written. A lane is pinned here once its wave is written and accepted.
REVIEWED_PLAN_KEYS_SHA256: dict[str, str] = {
    #: 1,074 rows, `logs/_write_dry/ALL_ROWS.jsonl` of 2026-09-22 (994 written, 80 withheld).
    MASS: "0b7ad95dc6b2ee626d281e31c9a9a2532d0b6ea423acf75ed710be6384ae039b",
}


def keys_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    """sha256 over the rows' change keys in file order, one per line, LF-joined, trailing LF."""
    return hashlib.sha256(
        "".join(str(row["change_key"]) + "\n" for row in rows).encode("utf-8")
    ).hexdigest()


def assert_reviewed_plan(name: str, rows: list[dict], *, path: pathlib.Path) -> None:
    """Refuse a rows file that is not the plan a written lane was pinned to. A lane without a pin
    (nothing written yet) has no reviewed plan to compare with; `write_dry_all.py` guards it instead."""
    pinned = REVIEWED_PLAN_KEYS_SHA256.get(name)
    if pinned is None:
        return
    digest = keys_digest(rows)
    if digest != pinned:
        raise SystemExit(
            f"{path}: its change keys hash to {digest[:16]}, but lane {name!r} was written from the "
            f"plan {pinned[:16]} ({len(rows)} rows here). This is not the plan the production rows "
            "were reviewed against - a re-plan names other rows, or the same rows at other lines. "
            "Restore the reviewed rows file from the archive named in HANDOVER.md"
        )


def write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    """One object per line, UTF-8, LF - the shape `read_jsonl` reads back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
        newline="\n",
    )
