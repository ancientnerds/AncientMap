"""From verdicts to targets: the best `depicts` of a site, once the adversarial re-check confirmed it.

The depicts role (`depicts.py`) leaves a site with zero or more `depicts` candidates, each with a
quality. The page gets one of them, and the one it gets is looked at twice. In rounds:

1. the best-ranked `depicts` candidate of every site (`judge.rank_key`: quality, then pixels) that no
   re-check has judged yet is re-checked (`hero_recheck.py`, Opus high);
2. a site whose pick was confirmed is done - that candidate is its target;
3. a site whose pick was not confirmed goes on with its next-ranked `depicts`, in the next round;
4. a site that has no `depicts` left, every one of them refused, is exhausted: it keeps no picture
   and is listed for the owner with the reasons.

`write-targets` writes the confirmed ones and refuses while any site still waits for a round - a
target nobody re-checked must not be written because a round was forgotten.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from candidate_search import judge as CJ  # noqa: E402

from image_roles import stage as SG  # noqa: E402


@dataclass
class Round:
    """Where the sites stand after the re-checks recorded so far."""

    confirmed: dict[str, dict[str, Any]] = field(default_factory=dict)
    to_check: list[dict[str, Any]] = field(default_factory=list)
    exhausted: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "confirmed": len(self.confirmed),
            "to_check": len(self.to_check),
            "exhausted": len(self.exhausted),
        }


def ranked(verdicts: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """The `depicts` rows of every site, best first (`rank_key` descending, then the file name)."""
    by_site: dict[str, list[dict[str, Any]]] = {}
    for row in verdicts:
        if row.get("verdict") == CJ.DEPICTS:
            by_site.setdefault(str(row["site_id"]), []).append(dict(row))
    for rows in by_site.values():
        rows.sort(key=lambda r: (tuple(-v for v in CJ.rank_key(r)), str(r["file"])))
    return by_site


def judged_by_recheck(rechecks: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], str]:
    """`{(site id, file): verdict}` over every re-check recorded; one candidate judged twice with
    two different verdicts is refused."""
    out: dict[tuple[str, str], str] = {}
    for row in rechecks:
        key = (str(row["meta"]["site_id"]), str(row["meta"]["file"]))
        if key in out and out[key] != row["verdict"]:
            raise SG.StageError(f"{key[0]}: {key[1]!r} was re-checked twice with two verdicts")
        out[key] = row["verdict"]
    return out


def pick_round(
    verdicts: Sequence[Mapping[str, Any]], rechecks: Sequence[Mapping[str, Any]]
) -> Round:
    """The state of every site with a `depicts`: confirmed, waiting for its next re-check, or
    exhausted (see the module docstring)."""
    judged = judged_by_recheck(rechecks)
    result = Round()
    for site_id, rows in sorted(ranked(verdicts).items()):
        refused: list[dict[str, Any]] = []
        for row in rows:
            verdict = judged.get((site_id, str(row["file"])))
            if verdict is None:
                result.to_check.append(row)
                break
            if verdict == CJ.DEPICTS:
                result.confirmed[site_id] = row
                break
            refused.append(row)
        else:
            result.exhausted[site_id] = refused
    return result


def write_targets(
    out: Path, verdicts: Sequence[Mapping[str, Any]], rechecks: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """`TARGETS.jsonl` of the confirmed picks, refused while a site still waits for a re-check."""
    state = pick_round(verdicts, rechecks)
    if state.to_check:
        names = ", ".join(row["site_id"] for row in state.to_check[:3])
        raise SG.StageError(
            f"{len(state.to_check)} site(s) wait for a re-check round (first {names}): export the "
            "next round with `recheck-export` before the targets are written"
        )
    confirmed = {(site_id, str(row["file"])) for site_id, row in state.confirmed.items()}
    summary = CJ.write_targets(out, verdicts, confirmed)
    return summary | {"exhausted": len(state.exhausted)}
