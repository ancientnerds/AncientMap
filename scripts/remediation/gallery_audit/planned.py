"""The planned-row record of the gallery lanes, its writer and its strict readers.

`decide.py` writes every plan it makes as one `PlannedRow` per line (the liveness store's
PLANNED.jsonl, a G run's PLANNED-chunk-NNN.jsonl). Once such a plan has reached production it is
folded back into the current state (`worklist.build_state`, ``--applied``), and so are the
`image_kind` plans of G0 and G0b (``--kinds-from``, the `persist_verdicts` record). Both readers
refuse anything that is not exactly the record they name: a plan read loosely would put a value
into the state that production does not hold.

This module sits apart from `decide.py` and `worklist.py` because both need it and `decide`
imports `worklist`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


class PlanError(RuntimeError):
    """A plan file that is not the record it claims to be."""


@dataclass(frozen=True)
class PlannedRow:
    table: str
    key: int
    site_id: str
    column: str
    old: Any
    new: Any
    rule: str
    role: str
    evidence: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


PLANNED_KEYS = frozenset(f.name for f in fields(PlannedRow))


def write_plan(path: Path, planned: Sequence[PlannedRow]) -> str:
    text = "".join(
        json.dumps(row.as_json(), ensure_ascii=False, sort_keys=True) + "\n" for row in planned
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _records(path: Path) -> list[tuple[int, dict[str, Any]]]:
    """The non-empty lines of a plan. A plan without a row is refused: folding an empty file in
    proves nothing about what production holds, and it is far more often a wrong path."""
    out = []
    for lineno, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if text.strip():
            out.append((lineno, json.loads(text)))
    if not out:
        raise PlanError(f"{path} holds no planned row")
    return out


def read_plan(path: Path) -> list[PlannedRow]:
    """A `decide.py` plan, row for row, with exactly the `PlannedRow` keys."""
    rows = []
    for lineno, record in _records(path):
        if not isinstance(record, dict) or set(record) != PLANNED_KEYS:
            raise PlanError(f"{path}:{lineno}: not a planned row (keys differ from PlannedRow)")
        rows.append(PlannedRow(**record))
    return rows


#: What a G0/G0b record must carry to be folded in as a planned row.
KINDS_RECORD_KEYS = frozenset({"table", "column", "image_id", "site_id", "old_value", "new_value"})


def read_kinds_plan(path: Path) -> list[PlannedRow]:
    """A G0/G0b `image_kind` plan (the `persist_verdicts` record), as planned rows."""
    rows = []
    for lineno, record in _records(path):
        if not isinstance(record, dict) or not KINDS_RECORD_KEYS <= set(record):
            raise PlanError(
                f"{path}:{lineno}: not an image_kind plan record (needs {sorted(KINDS_RECORD_KEYS)})"
            )
        if record["table"] != "wiki_images" or record["column"] != "image_kind":
            raise PlanError(f"{path}:{lineno}: a record that is not an image_kind write")
        image_id = record["image_id"]
        rows.append(
            PlannedRow(
                table="wiki_images",
                key=image_id,
                site_id=record["site_id"],
                column="image_kind",
                old=record["old_value"],
                new=record["new_value"],
                rule=str(record.get("test_id")),
                role="kind",
                evidence={"change_key": record.get("change_key")},
            )
        )
    return rows
