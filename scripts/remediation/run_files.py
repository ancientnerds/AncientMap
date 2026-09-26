"""The file helpers the Opus-handoff lanes share: the UTC clock their records carry, and the JSON and
JSON-lines writers of their run directories (UTF-8, LF, keys sorted, parents created).

Used by the fresh acceptance (`acceptance/judge.py`) and lane WC (`wc/cli.py`), which carried
the same bodies each (the WC review of 2026-09-26). Nothing here reads: each tool keeps its own
strict reader.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now() -> str:
    """The current UTC time, to the second, as the run records carry it."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def write_json(path: Path, data: Any) -> None:
    """One JSON document: indented by one space, keys sorted, UTF-8 with an LF at the end."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """One JSON object per line, keys sorted, UTF-8 with LF line ends."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8", newline="\n")
