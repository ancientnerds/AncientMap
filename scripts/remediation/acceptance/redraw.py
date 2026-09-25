"""Phase 6, PROTOCOL.md section 10: the fresh draw after a FAIL or a VOID.

Under FAIL: "a fresh acceptance on a new draw - `draw.py` sealed again with seed 20260926 (its canaries
20260927), excluding this draw's 60 - under these same thresholds". Under VOID: "a fresh draw with the
next seed as under FAIL".

`draw.py` stays byte for byte as it ran the first draw. `SEAL.json`, AUDIT_LOG and that draw's
`DRAW.json` pin it, and `test_acceptance_draw.test_the_seal_holds` holds it there. Its seed is a
module constant, and its exclusions have no place for a draw that went before. This module therefore
imports the draw instead of changing it: the reads, the exclusion sources, `phase4.audit4.draw_sample`,
the canaries and the files are all `draw.py`'s. It adds exactly two things:

* **The seed** is one past the highest seed of the draws named with `--after` (`next_seed`). The
  canaries use the seed after that, as `draw.canaries` has done from the start (`seed + 1`).
* **The previous draws' sites are excluded.** Each `--after` directory is read only when its
  `RESULT.md` is written, because section 10 follows a result. Its `SAMPLE.jsonl` is read only when
  its bytes are the ones its `DRAW.json` pins, and it must hold exactly that draw's `sample_size`
  distinct sites (`previous_draw`). The drawn `site_id`s are excluded, recorded as
  `previous-draw-<name>`, and nothing else is: a frame id that a sample's values happen to name
  (a duplicate's survivor in `scope_reason`) is no drawn site.

    redraw.py --out output/remediation/acceptance/draw-<date> \\
              --after output/remediation/acceptance/draw-2026-09-25 \\
              --phase4-audit-samples <file> [<file> ...]

It writes the files `draw.py` writes, into a directory that must not exist. `judge.py` reads them
unchanged. `DRAW.json` also names the canary seed, the previous draws (name, seed, the sha256 of
their sample) and the sha256 of both scripts. Sealing it again is the orchestrator's step before the
draw: the sha256 of this file, next to the unchanged `PROTOCOL.md` and `draw.py`, is recorded in
AUDIT_LOG.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (
    ROOT,
    ROOT / "scripts" / "remediation",
    ROOT / "scripts" / "remediation" / "gallery_audit",
):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import persist_verdicts as pv  # noqa: E402
from phase4.audit4 import draw_sample  # noqa: E402

from acceptance import draw as D  # noqa: E402


@dataclass(frozen=True)
class PreviousDraw:
    """A finished draw: its name, its seed, its drawn sites and the sha256 of its sample."""

    name: str
    seed: int
    site_ids: frozenset[str]
    sample_path: Path
    sample_sha256: str


def _lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def previous_draw(run: Path) -> PreviousDraw:
    """A draw directory whose result is written, read from the sample its DRAW.json pins."""
    if not (run / "RESULT.md").is_file():
        raise D.DrawError(
            f"{run} has no RESULT.md: a fresh draw follows a result (PROTOCOL.md section 10)"
        )
    draw = json.loads((run / "DRAW.json").read_text(encoding="utf-8"))
    sample_path = run / "SAMPLE.jsonl"
    data = _lf(sample_path)
    digest = hashlib.sha256(data).hexdigest()
    if digest != draw["sha256"]["SAMPLE.jsonl"]:
        raise D.DrawError(f"{sample_path} is not the SAMPLE.jsonl its DRAW.json pins")
    ids = [json.loads(line)["site_id"] for line in data.decode("utf-8").split("\n") if line]
    if len(set(ids)) != len(ids) or len(ids) != int(draw["sample_size"]):
        raise D.DrawError(
            f"{sample_path} holds {len(set(ids))} distinct sites in {len(ids)} lines, its "
            f"DRAW.json says {draw['sample_size']} sites"
        )
    return PreviousDraw(run.name, int(draw["seed"]), frozenset(ids), sample_path, digest)


def next_seed(previous: Sequence[PreviousDraw]) -> int:
    """One past the highest seed drawn so far (section 10: "the next seed")."""
    if not previous:
        raise D.DrawError("a fresh draw follows a previous one: name it with --after")
    return max(p.seed for p in previous) + 1


def take_redraw(
    frame: Sequence[Mapping[str, Any]],
    sources: Sequence[tuple[str, Path]],
    previous: Sequence[PreviousDraw],
    *,
    seed: int,
) -> dict[str, Any]:
    """`draw.take_draw` with the seed given and the previous draws' sites excluded."""
    frame_ids = {str(row["site_id"]) for row in frame}
    if len(frame_ids) != len(frame):
        raise D.DrawError("the frame read carries a site twice")
    excluded, records = D.exclusions(frame_ids, sources)
    for p in previous:
        removed = sorted(p.site_ids & frame_ids)
        excluded.update(removed)
        records.append(
            {
                "label": f"previous-draw-{p.name}",
                "path": p.sample_path.as_posix(),
                "sha256": p.sample_sha256,
                "frame_ids_removed": removed,
            }
        )
    pool = frame_ids - excluded
    if len(pool) < D.SAMPLE_SIZE:
        raise D.DrawError(
            f"{len(pool)} frame sites remain after the exclusions; {D.SAMPLE_SIZE} needed"
        )
    drawn = draw_sample(sorted(frame_ids), seed=seed, count=D.SAMPLE_SIZE, exclude=excluded)
    return {"frame_ids": frame_ids, "excluded": excluded, "records": records, "drawn": drawn}


def command_redraw(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists():
        raise D.DrawError(f"{out} exists - a draw is taken once, into a new directory")
    if not args.phase4_audit_samples:
        raise D.DrawError("the Phase-4 audit's samples are an exclusion source: pass them")
    previous = [previous_draw(Path(run)) for run in args.after]
    seed = next_seed(previous)
    sources = [(label, D.ROOT / path) for label, path in D.FIXED_EXCLUSIONS]
    sources += [
        (f"phase4-audit-sample-{n}", Path(p)) for n, p in enumerate(args.phase4_audit_samples, 1)
    ]
    journal = D.read_journal_mark()
    frame = D.read_frame()
    draw = take_redraw(frame, sources, previous, seed=seed)
    values = D.read_values(draw["drawn"])
    if sorted(str(v["site_id"]) for v in values) != draw["drawn"]:
        raise D.DrawError("the value read does not return exactly the drawn sites")
    canary_rows = D.canaries(values, frame, seed=seed)
    out.mkdir(parents=True)
    files = {
        "FRAME.jsonl": D._jsonl(sorted(frame, key=lambda r: str(r["site_id"]))),
        "EXCLUDED.json": json.dumps(draw["records"], ensure_ascii=False, indent=1) + "\n",
        "SAMPLE.jsonl": D._jsonl(values),
        "CANARIES.jsonl": D._jsonl(canary_rows),
    }
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    summary = {
        "drawn_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "canary_seed": seed + 1,
        "sample_size": D.SAMPLE_SIZE,
        "frame": len(draw["frame_ids"]),
        "excluded": len(draw["excluded"]),
        "pool": len(draw["frame_ids"] - draw["excluded"]),
        "canaries": len(canary_rows),
        "journal_at_draw": journal,
        "after": [
            {"draw": p.name, "seed": p.seed, "sample_sha256": p.sample_sha256} for p in previous
        ],
        "sha256": {
            name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in files.items()
        },
        "draw_py_sha256": D.sha256_of(Path(D.__file__)),
        "redraw_py_sha256": D.sha256_of(_HERE),
    }
    (out / "DRAW.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", required=True, help="output/remediation/acceptance/draw-<date>")
    parser.add_argument(
        "--after",
        action="append",
        required=True,
        help="a previous draw's directory, its result written (repeatable)",
    )
    parser.add_argument(
        "--phase4-audit-samples",
        nargs="+",
        default=[],
        help="the id files of the Phase-4 audit's mid-run samples and its final 60",
    )
    args = parser.parse_args(argv)
    try:
        return command_redraw(args)
    except pv.PersistError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
