"""The files of a cell-lane plan, written the one way every identity lane writes them.

`PLAN.jsonl` and `ROLLBACK.sql` are `mechanical.plan`'s (the rollback is written **after** the plan it
is pinned to, and `apply.py --emit` refuses a plan that is not the one the rollback names);
`SKIPPED.jsonl` lists every site the plan left out with why, and `PLAN.md` is what a reviewer reads.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import plan as MP  # noqa: E402


def write_cell_plan(
    mech: MP.Plan, skipped: Sequence[Mapping[str, Any]], out: Path, markdown: str
) -> bool:
    """The plan's files into `out`: SKIPPED.jsonl and PLAN.md always, PLAN.jsonl and ROLLBACK.sql
    when the plan writes anything (returns whether it does). A plan whose statement was emitted
    (`APPLY.sql`) is never re-planned: its rollback may be the only undo of a write that landed. A
    plan that writes nothing removes the files of an earlier, unemitted plan of the same wave -
    they would describe cells the live read no longer supports."""
    if (out / "APPLY.sql").exists():
        raise MP.PlanError(
            f"{out / 'APPLY.sql'} exists: a plan that was emitted is not planned again - plan "
            "the next wave from a new read"
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / "SKIPPED.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n" for s in skipped),
        encoding="utf-8",
        newline="\n",
    )
    (out / "PLAN.md").write_text(markdown, encoding="utf-8", newline="\n")
    if not mech.changes:
        for stale in ("PLAN.jsonl", "ROLLBACK.sql"):
            (out / stale).unlink(missing_ok=True)
        return False
    MP.write_plan_jsonl(mech, out / "PLAN.jsonl")
    MP.write_rollback_sql(mech, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    return True


def skipped_lines(skipped: Sequence[Mapping[str, Any]]) -> list[str]:
    if not skipped:
        return []
    return [
        "",
        "## Skipped",
        "",
        *[f"* `{s['site_id']}` {s['name']}: {s['reason']} - {s['note']}" for s in skipped],
    ]


def header_lines(mech: MP.Plan, title: str, built_by: str) -> list[str]:
    lane = mech.lane
    return [
        f"# {title} ({lane.name}) - planned, not applied",
        "",
        f"Built {mech.built_at} by `{built_by}`. Run stamp `{lane.run_stamp}`, journal test id "
        f"`{lane.test_id}`, premise `{lane.premise_sql}`.",
        "",
        "```json",
        json.dumps(dict(mech.counters), indent=1, sort_keys=True),
        "```",
        "",
    ]
