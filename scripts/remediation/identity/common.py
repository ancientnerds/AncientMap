"""What every identity discovery module shares: where the run data lives, how it is written, and
the few measures (distance, name tokens) the modules must agree on."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from prod_write import jsonl_lines  # noqa: E402

from pipeline.utils.geo import haversine_distance  # noqa: E402
from pipeline.utils.git_env import run_git  # noqa: E402

RUN_SUBDIR = Path("output") / "remediation" / "final-2026-10-08" / "identity"
HARVEST_SUBDIR = Path("output") / "remediation" / "fields" / "harvest"
EXPORT_FILE = "EXPORT.jsonl"
COUNTS_FILE = "COUNTS.json"


class IdentityError(RuntimeError):
    """An input is not what the discovery needs; nothing is written from it."""


def main_checkout() -> Path:
    """The main checkout of this repository (worktree-safe): it holds the gitignored run data and
    the harvest, which a worktree does not carry."""
    proc = run_git(REPO, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if proc.returncode != 0:
        raise IdentityError(f"cannot locate the main checkout: {proc.stderr.strip()[-300:]}")
    common = Path(proc.stdout.strip())
    if common.name != ".git":
        raise IdentityError(f"git common dir {common} is not a '.git' directory")
    return common.parent


def run_dir(root: Path | None = None) -> Path:
    return (root or main_checkout()) / RUN_SUBDIR


def harvest_dir(root: Path | None = None) -> Path:
    return (root or main_checkout()) / HARVEST_SUBDIR


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> int:
    """One JSON object per line, written whole or not at all; returns the number of lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")
    tmp.replace(path)
    return len(lines)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in jsonl_lines(text) if line.strip()]


def record_counts(directory: Path, module: str, counts: Mapping[str, Any]) -> None:
    """The counts of one module, kept beside the others in `COUNTS.json`."""
    path = directory / COUNTS_FILE
    known: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    known[module] = dict(counts)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(known, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    tmp.replace(path)


def metres(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """Great-circle distance in metres between two rows that carry `lat` and `lon`."""
    return haversine_distance(a["lat"], a["lon"], b["lat"], b["lon"]) * 1000.0


#: Words that carry no identity in a site's name (the parents and duplicate matching ignore them).
STOP_TOKENS = frozenset(
    "the of de del la le el and archaeological site ruins temple tomb church fort castle cave "
    "caves stone stones park complex ancient roman city old new north south east west great "
    "little upper lower".split()
)


def fold(text: str) -> str:
    """Lower case, accents removed, anything that is not a letter or digit a space."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", plain)


def tokens(text: str) -> frozenset[str]:
    """The significant words of a name: folded, no stop word, more than two characters."""
    return frozenset(t for t in fold(text).split() if t not in STOP_TOKENS and len(t) > 2)


def rows_by_id(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_id = {r["id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise IdentityError("two rows of the export carry the same id")
    return by_id
