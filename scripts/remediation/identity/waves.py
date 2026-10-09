"""Waves of the identity package's writes: at most 100 sites, each site in one wave only.

Every write of the final repair is a wave of at most 100 sites with a run stamp of its own, run
through the gates in this order: emit, check, verify, rehearse, probe-guards, apply, read-back,
rehearse-rollback, 0 deviations. A stamp is applied once, so a wave is **selected once**
(`waves/<wave>/WAVE.json`, never replaced) and a site belongs to the first wave that took it. A site
a wave could not write (a skip: its state moved, another record carries its item, its name key is
taken, its links have not landed) is not selected again: the lane's `result` lists it, with the
wave and the reason, in `WAVE_SKIPS.jsonl` (and in the owner list where the lane has one), so no
skip disappears with the wave that made it.

`<lane dir>/waves/<wave>/` also holds the wave's plan files, written by the lane's own planner.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Sequence
from pathlib import Path
from typing import Any

from identity import common

SITES_PER_WAVE = 100
WAVE_FILE = "WAVE.json"
SKIPS_FILE = "WAVE_SKIPS.jsonl"
#: The skips that leave nothing to write: the state the question asked for is already there.
NOTHING_LEFT = frozenset(
    {"already-decided", "already-retired", "already-set", "name-unchanged", "same-as-name"}
)


class WaveError(ValueError):
    """A wave or a chain step that must not be taken. Nothing was written."""


def wave_dir(lane_dir: Path, wave: str) -> Path:
    return lane_dir / "waves" / wave


def planned_sites(lane_dir: Path) -> set[str]:
    """The sites an earlier wave of the lane took."""
    taken: set[str] = set()
    for path in sorted((lane_dir / "waves").glob(f"*/{WAVE_FILE}")):
        taken |= set(json.loads(path.read_text(encoding="utf-8"))["sites"])
    return taken


def select_wave(
    lane_dir: Path, wave: str, candidates: Collection[str], *, limit: int, built_at: str
) -> dict[str, Any]:
    """The next wave's sites: the first `limit` (1 to 100) of `candidates` no earlier wave took, in
    site order. Written once to `waves/<wave>/WAVE.json`."""
    if not 1 <= limit <= SITES_PER_WAVE:
        raise WaveError(f"a wave holds 1..{SITES_PER_WAVE} sites, not {limit}")
    path = wave_dir(lane_dir, wave) / WAVE_FILE
    if path.exists():
        raise WaveError(f"{path} exists: a wave is selected once")
    taken = planned_sites(lane_dir)
    open_sites = [s for s in sorted(candidates) if s not in taken]
    if not open_sites:
        raise WaveError("no site is left for a new wave")
    record = {"wave": wave, "sites": open_sites[:limit], "built_at": built_at}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return record


def load_wave(lane_dir: Path, wave: str) -> dict[str, Any]:
    path = wave_dir(lane_dir, wave) / WAVE_FILE
    if not path.exists():
        raise WaveError(f"{path} does not exist: select the wave first")
    return json.loads(path.read_text(encoding="utf-8"))


def all_waves(lane_dir: Path) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((lane_dir / "waves").glob(f"*/{WAVE_FILE}"))
    ]


def wave_skips(
    lane_dir: Path, plan_skip_files: Callable[[str], Sequence[Path]]
) -> list[dict[str, Any]]:
    """The sites the plans of every wave left out, one row per site and wave (the first reason
    wins): `wave`, `site_id`, `name`, `reason`, `note`. `plan_skip_files(wave)` names the wave's
    skip files; a skip that leaves nothing to write (`NOTHING_LEFT`) is not listed."""
    rows: list[dict[str, Any]] = []
    for record in all_waves(lane_dir):
        seen: set[str] = set()
        for path in plan_skip_files(record["wave"]):
            if not path.exists():
                continue
            for row in common.read_jsonl(path):
                if row["site_id"] in seen or row["reason"] in NOTHING_LEFT:
                    continue
                seen.add(row["site_id"])
                rows.append(
                    {
                        "wave": record["wave"],
                        **{k: row[k] for k in ("site_id", "name", "reason", "note")},
                    }
                )
    return rows
