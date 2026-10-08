"""The read-only acceptance of an identity wave: the plan, the journal and the data agree.

`apply.py --verify` (and the chunk writer's `--readback`) already count the journal rows of a stamp;
this is the other half of "0 deviations": every cell the plan wrote holds its new value in the
database now, read in one read-only statement. A wave is accepted when this reports no deviation
and the lane's own read-back reports none.
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

from mechanical.lane import sql_literal  # noqa: E402

from identity import common  # noqa: E402


def planned_cells(plan_path: Path) -> list[dict[str, Any]]:
    """The `(site_id, column, old_value, new_value)` of every record of a lane's PLAN.jsonl."""
    return [
        {k: r[k] for k in ("site_id", "column", "old_value", "new_value")}
        for r in common.read_jsonl(plan_path)
    ]


def live_cells_sql(site_ids: Sequence[str], columns: Sequence[str]) -> str:
    """The planned columns of the planned sites as the database holds them now. Read-only."""
    for column in columns:
        if not column.replace("_", "").isalnum():
            raise common.IdentityError(f"{column!r} is not a column name")
    ids = ", ".join(f"{sql_literal(s)}::uuid" for s in sorted(set(site_ids)))
    listed = ", ".join(f"u.{c}::text AS {c}" for c in dict.fromkeys(columns))
    return f"SELECT u.id::text AS site_id, {listed} FROM unified_sites u WHERE u.id IN ({ids}) ORDER BY u.id"


def cell_deviations(
    cells: Sequence[Mapping[str, Any]], live: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """Every planned cell that does not hold its new value now (a row gone counts as one)."""
    out = []
    for cell in cells:
        now = live.get(cell["site_id"])
        if now is None:
            out.append(f"{cell['site_id']}: the row is gone")
        elif now[cell["column"]] != cell["new_value"]:
            out.append(
                f"{cell['site_id']}.{cell['column']}: holds {now[cell['column']]!r}, the plan wrote "
                f"{cell['new_value']!r}"
            )
    return out


def wave_report(deviations: Sequence[str], planned: int) -> dict[str, Any]:
    return {
        "planned_cells": planned,
        "deviations": len(deviations),
        "detail": list(deviations[:20]),
        "accepted": not deviations and planned > 0,
    }


def dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
