"""Waves of the identity package's writes: at most 100 sites, each site in one wave only.

Every write of the final repair is a wave of at most 100 sites with a run stamp of its own, run
through the gates in this order: emit, check, verify, rehearse, probe-guards, apply, read-back,
rehearse-rollback, 0 deviations. A stamp is applied once, so a wave is **selected once**
(`waves/<wave>/WAVE.json`, never replaced) and a site belongs to the first wave that took it; a site a
wave could not write (a skip) is asked again in a later round, not carried in the old wave.

`<lane dir>/waves/<wave>/` also holds the wave's plan files, written by the lane's own planner.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from pathlib import Path
from typing import Any

SITES_PER_WAVE = 100
WAVE_FILE = "WAVE.json"


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
