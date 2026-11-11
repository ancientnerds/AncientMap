"""From verdicts to targets: the best `depicts` of a site, once the adversarial re-check confirmed it.

The depicts role (`depicts.py`) leaves a site with zero or more `depicts` candidates, each with a
quality. The page gets one of them, and the one it gets is looked at twice. In rounds:

1. the best-ranked `depicts` candidate of every site (`judge.rank_key`: quality, then pixels) that no
   re-check has judged yet is re-checked (`hero_recheck.py`, the role `adversarial`);
2. a site whose pick was confirmed is done - that candidate is its target;
3. a site whose pick was not confirmed goes on with its next-ranked `depicts`, in the next round;
4. a site that has no `depicts` left, every one of them refused, is exhausted: it keeps no picture
   and is listed for the owner with the reasons.

`write-targets` writes the confirmed ones and refuses while any site still waits for a round - a
target nobody re-checked must not be written because a round was forgotten.

A confirmed pick can still fail at the INSERT lane for a reason that lies in the **file**: a credit
its licence demands and the file lacks, an original below the floor, an upscale, a file type the
fetch does not take, a file an excluded row of the site already holds (`image_roles.d59.
FILE_REFUSALS`). Such a pick is refused for good (`refused`, the `(site id, file)` pairs the INSERT
runs name, `d59.refused_files`) and the site goes on exactly as after a rejection: its next-ranked
`depicts` is re-checked in the next round, and `TARGETS.jsonl` - the picks the INSERT lane has
still to try, a statement about the run as it stands - is written again with that pick or without
the site. A refusal that speaks of the site (retired, a thumbnail that moved) passes nothing over.
"""

from __future__ import annotations

import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from candidate_search import judge as CJ  # noqa: E402
from served_image import state as ST  # noqa: E402

from image_roles import stage as SG  # noqa: E402


@dataclass
class Round:
    """Where the sites stand after the re-checks recorded so far."""

    confirmed: dict[str, dict[str, Any]] = field(default_factory=dict)
    to_check: list[dict[str, Any]] = field(default_factory=list)
    exhausted: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    #: The confirmed picks the INSERT lane refused for good, by site, in rank order.
    insert_refused: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

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
    verdicts: Sequence[Mapping[str, Any]],
    rechecks: Sequence[Mapping[str, Any]],
    refused: Collection[tuple[str, str]] = (),
) -> Round:
    """The state of every site with a `depicts`: confirmed, waiting for its next re-check, or
    exhausted (see the module docstring). `refused` holds the `(site id, file in title form)` pairs
    the INSERT lane refused for good: a confirmed pick among them is passed over like a rejected
    one."""
    judged = judged_by_recheck(rechecks)
    result = Round()
    for site_id, rows in sorted(ranked(verdicts).items()):
        passed: list[dict[str, Any]] = []
        for row in rows:
            verdict = judged.get((site_id, str(row["file"])))
            if verdict is None:
                result.to_check.append(row)
                break
            if verdict == CJ.DEPICTS:
                if (site_id, ST.canonical_file(str(row["file"]))) not in refused:
                    result.confirmed[site_id] = row
                    break
                result.insert_refused.setdefault(site_id, []).append(row)
            passed.append(row)
        else:
            result.exhausted[site_id] = passed
    return result


def write_targets(
    out: Path,
    verdicts: Sequence[Mapping[str, Any]],
    rechecks: Sequence[Mapping[str, Any]],
    refused: Collection[tuple[str, str]] = (),
) -> dict[str, Any]:
    """`TARGETS.jsonl` of the confirmed picks, refused while a site still waits for a re-check.
    With `refused` (`pick_round`) it is the list after the INSERT lane's refusals: the next
    confirmed pick of a site whose earlier one was refused for good, and no line for a site that
    has none left."""
    state = pick_round(verdicts, rechecks, refused)
    if state.to_check:
        names = ", ".join(row["site_id"] for row in state.to_check[:3])
        raise SG.StageError(
            f"{len(state.to_check)} site(s) wait for a re-check round (first {names}): export the "
            "next round with `recheck-export` before the targets are written"
        )
    confirmed = {(site_id, str(row["file"])) for site_id, row in state.confirmed.items()}
    summary = CJ.write_targets(out, verdicts, confirmed)
    return summary | {
        "exhausted": len(state.exhausted),
        "insert_refused": sum(len(rows) for rows in state.insert_refused.values()),
    }
