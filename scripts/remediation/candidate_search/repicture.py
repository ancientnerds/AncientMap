"""Gap 1 (2026-10-24): the lost renderings of the MiniMax pool, fetched again for exactly what needs them.

The candidate run of 2026-10-06 kept every candidate's rendering under `pictures/<sha256(url)[:32]>`
(`judge.download`, `pool.picture_path`) - 5,756 files, 2.5 GB. The worktree that held them was
removed, and on 2026-10-24 none is left: `pool.target_picks` refuses the first missing picture, and
the calibration's adjudication sample has nothing to draw from. The root cause is a deleted copy, not
a code path, so the fix is the copy: the same URLs, fetched again into the same names, for **exactly**
the pictures a step needs - never the whole pool by default - with a manifest that names every one.

The needs, each the question the consuming step itself asks:

* `recheck` - D10: the old targets the adversarial re-check judges (`image_roles/flow.pool_pick_sites`:
  the targets of the population's sites and the 178 written heroes), `--run-dir C --served-run S`;
* `credit` - D18: the targets of the credit-refused sites that need a Claude re-judge first
  (`import_hero/credit_refusals.py` writes `CREDIT_SITES_CLAUDE.txt`), `--sites FILE`;
* `calibration` - the pilot judge's adjudication sample of the image calibration
  (`image_roles/calibrate.adjudication_sample`, the sealed seed and count), `--calibration-dir D
  --read READ.json`;
* `pool` - the whole pool of the population's sites, for a separate pool re-judge (D10 C4), `--run-dir
  C`. The D17 search re-finds these sites' candidates anyway (a MiniMax verdict excludes no file,
  `flow.MINIMAX_WORD`), so this need is optional.

The fetch is the lane's own transport: `served_image.commons.Commons.get` with the lanes' User-Agent
(`research_web`), one request a second per host, an HTTP 429 or 5xx stops the command (run it again),
a gone address is recorded `gone`. A rendering is accepted only when it is the lane's: a Commons host,
a thumbnail URL that names the lane's width (`/1280px-`, `commons.RENDER_WIDTH`), a `Content-Type` of
a still picture, bytes Pillow decodes, at most that width. A picture already on disk is decoded again
and kept (`present`), never fetched twice. The manifest `REPICTURE_<need>.jsonl` is written into the
old run with one line per needed picture - `fetched`, `present`, `gone` or `refused` with the reason,
the sha256 and size of the bytes; the command exits 1 while any line is not on disk. A run that an
HTTP 429, a 5xx or a timeout stops writes the lines it has, then a `stopped` line naming the error and
the pictures never asked, before it exits - the manifest always describes the disk this run left.

    repicture.py --old-run OLD --need recheck     --run-dir C --served-run S   [--dry-run]
    repicture.py --old-run OLD --need credit      --sites CREDIT_SITES_CLAUDE.txt [--dry-run]
    repicture.py --old-run OLD --need calibration --calibration-dir D --read READ.json [--dry-run]
    repicture.py --old-run OLD --need pool        --run-dir C [--dry-run]

The re-fetched bytes are not provably the bytes MiniMax judged (Commons may re-render a thumbnail);
they need not be: every consumer re-judges them with Claude, and the manifest's sha256 ties each new
verdict to the bytes it saw.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_HERE = Path(__file__).resolve()
for _path in (_HERE.parents[3], _HERE.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from PIL import Image  # noqa: E402
from served_image import commons as CM  # noqa: E402
from served_image import state as ST  # noqa: E402

from candidate_search import judge as CJ  # noqa: E402
from candidate_search import pool as PL  # noqa: E402
from candidate_search import search as CS  # noqa: E402

NEEDS = ("recheck", "credit", "calibration", "pool")
HOSTS = frozenset({"upload.wikimedia.org", "thumb.wikimedia.org"})
#: The renderings Commons serves for a still picture (an SVG or TIFF original renders as PNG/JPEG).
RENDER_MIMES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
FETCHED, PRESENT, GONE, REFUSED = "fetched", "present", "gone", "refused"
ON_DISK = frozenset({FETCHED, PRESENT})
#: The last line of a manifest whose run a CommonsError stopped: the picture it stopped on and how
#: many were never asked.
STOPPED = "stopped"


class RepictureError(ST.StateError):
    """The need cannot be named from what was given. Nothing was fetched."""


def manifest_name(need: str) -> str:
    return f"REPICTURE_{need}.jsonl"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RepictureError(f"{path} does not exist")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# -------------------------------------------------------------------------------- the needs
def need_targets(
    old_run: Path, population: Sequence[Mapping[str, Any]], site_ids: set[str]
) -> list[tuple[str, dict[str, Any]]]:
    """`(site id, candidate)` of the old targets of `site_ids` (`pool.target_candidates`)."""
    return [
        (str(site["site_id"]), candidate)
        for site, candidate, _ in PL.target_candidates(old_run, population, site_ids)
    ]


def need_recheck(old_run: Path, run: Path, served_run: Path) -> list[tuple[str, dict[str, Any]]]:
    from image_roles import flow as FL

    state = ST.load_read(served_run / "READ.json")
    records, wanted = FL.pool_pick_sites(run, old_run, state)
    return need_targets(old_run, records, wanted)


def need_credit(old_run: Path, sites_file: Path) -> list[tuple[str, dict[str, Any]]]:
    from served_image import recheck as RC

    wanted = set(RC.read_sites(sites_file))
    targeted = {str(t["site_id"]) for t in _jsonl(old_run / CJ.TARGETS)}
    absent = sorted(wanted - targeted)
    if absent:
        raise RepictureError(
            f"{len(absent)} named site(s) are no target of {old_run.name} (first {absent[0]})"
        )
    return need_targets(old_run, [{"site_id": s} for s in wanted], wanted)


def need_calibration(
    old_run: Path, calibration_dir: Path, read: Path
) -> list[tuple[str, dict[str, Any]]]:
    from image_roles import calibrate as CAL

    thresholds, _, _ = CAL.sealed(calibration_dir)
    state = ST.load_read(read)
    return CAL.adjudication_sample(
        set(state.sites),
        _jsonl(old_run / CS.CANDIDATES),
        _jsonl(old_run / CJ.VERDICTS),
        per_class=int(thresholds["roles"]["pilot_judge"]["per_class"]),
        seed=int(thresholds["seed"]),
    )


def need_pool(old_run: Path, run: Path) -> list[tuple[str, dict[str, Any]]]:
    from image_roles import flow as FL

    ids = {str(s["site_id"]) for s in FL._population(run)}
    return [
        (str(site["site_id"]), dict(candidate))
        for site in _jsonl(old_run / CS.CANDIDATES)
        if str(site["site_id"]) in ids
        for candidate in site["candidates"]
    ]


# -------------------------------------------------------------------------------- the fetch
def rendering_problem(url: str) -> str | None:
    """Why `url` is not a rendering the lane stores, or None."""
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "") not in HOSTS:
        return f"{url!r} is no Commons rendering"
    # A multi-page original (TIFF, PDF, DjVu) renders as `[lossy-|lossless-]page<N>-<W>px-<name>`.
    if "/thumb/" in parts.path and not re.match(
        rf"(?:(?:lossy|lossless)-)?(?:page\d+-)?{CM.RENDER_WIDTH}px-", parts.path.rsplit("/", 1)[-1]
    ):
        return f"{url!r} names another width than the lane's {CM.RENDER_WIDTH} px"
    return None


def decoded(data: bytes) -> tuple[int, int]:
    """The picture's size, or `ValueError` when Pillow cannot decode the bytes as a picture."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return image.size
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError(f"the bytes are no picture Pillow decodes ({exc})") from exc


def _line(
    site_id: str, candidate: Mapping[str, Any], path: Path, status: str, **extra: Any
) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "file": str(candidate.get("file") or ""),
        "picture_url": str(candidate.get("picture_url") or ""),
        "name": path.name,
        "status": status,
        **extra,
    }


def _accepted(data: bytes, content_type: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """`(the facts of an accepted rendering, None)` or `(None, why it is refused)`."""
    mime = (content_type or "").split(";")[0].strip().lower()
    if content_type is not None and mime not in RENDER_MIMES:
        return None, f"Content-Type {mime!r} is no still picture"
    try:
        width, height = decoded(data)
    except ValueError as exc:
        return None, str(exc)
    if width > CM.RENDER_WIDTH:
        return None, f"the rendering is {width} px wide, more than the lane's {CM.RENDER_WIDTH}"
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "width": width,
        "height": height,
        **({"content_type": mime} if content_type is not None else {}),
    }, None


def fetch_one(
    old_run: Path, site_id: str, candidate: Mapping[str, Any], commons: Any
) -> dict[str, Any]:
    """One needed picture on disk, or the reason it is not. A CommonsError (HTTP 429, a 5xx, a
    timeout) is raised: the run stops and is made again, it is never recorded as a refusal."""
    path = PL.picture_path(old_run, candidate)
    url = str(candidate.get("picture_url") or "")
    if not url:
        return _line(site_id, candidate, path, REFUSED, reason="the search recorded no rendering")
    problem = rendering_problem(url)
    if problem is not None:
        return _line(site_id, candidate, path, REFUSED, reason=problem)
    if path.is_file():
        facts, why = _accepted(path.read_bytes(), None)
        if facts is None:
            return _line(site_id, candidate, path, REFUSED, reason=f"on disk, but {why}")
        return _line(site_id, candidate, path, PRESENT, **facts)
    try:
        response = commons.get(url)
    except CM.Unfetchable as exc:
        return _line(site_id, candidate, path, GONE, reason=str(exc))
    facts, why = _accepted(response.content, response.headers.get("content-type", ""))
    if facts is None:
        return _line(site_id, candidate, path, REFUSED, reason=why)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(response.content)
    tmp.replace(path)
    return _line(site_id, candidate, path, FETCHED, **facts)


def _write_manifest(old_run: Path, need: str, lines: Sequence[Mapping[str, Any]]) -> None:
    text = "".join(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n" for line in lines)
    (old_run / manifest_name(need)).write_text(text, encoding="utf-8", newline="\n")


def repicture(
    old_run: Path,
    need: str,
    needed: Sequence[tuple[str, Mapping[str, Any]]],
    commons: Any,
    *,
    dry_run: bool = False,
    now: Callable[[], str] = lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
) -> dict[str, Any]:
    """Every needed picture on disk (or, `dry_run`, only counted), and `REPICTURE_<need>.jsonl`.

    The manifest describes the need as it stands after this run - one line per needed picture -
    and is rewritten by every run of the same need, because it is a statement about the disk, not
    a record of an answer. A picture needed twice (one candidate of two needs) is one line."""
    if need not in NEEDS:
        raise RepictureError(f"need {need!r} is not one of {NEEDS}")
    if not needed:
        raise RepictureError(f"the need {need!r} names no picture")
    unique: dict[Path, tuple[str, Mapping[str, Any]]] = {}
    for site_id, candidate in needed:
        unique.setdefault(PL.picture_path(old_run, candidate), (site_id, candidate))
    if dry_run:
        missing = [p for p in unique if not p.is_file()]
        return {"need": need, "needed": len(unique), "on_disk": len(unique) - len(missing),
                "missing": len(missing), "dry_run": True}  # fmt: skip
    lines: list[dict[str, Any]] = []
    for site_id, candidate in unique.values():
        try:
            lines.append(fetch_one(old_run, site_id, candidate, commons))
        except CM.CommonsError as exc:
            path = PL.picture_path(old_run, candidate)
            stop = _line(site_id, candidate, path, STOPPED, reason=str(exc))
            _write_manifest(old_run, need, [*lines, stop | {"not_asked": len(unique) - len(lines)}])
            raise
    _write_manifest(old_run, need, lines)
    counts: dict[str, int] = {}
    for line in lines:
        counts[line["status"]] = counts.get(line["status"], 0) + 1
    off = [
        f"{line['site_id']}: {line['file']} ({line['reason']})"
        for line in lines
        if line["status"] not in ON_DISK
    ]
    return {
        "need": need,
        "made_at": now(),
        "needed": len(lines),
        "statuses": counts,
        "manifest": str(old_run / manifest_name(need)),
        "not_on_disk": off[:20],
        "ok": not off,
    }


# ------------------------------------------------------------------------------------ the CLI
def main(argv: Sequence[str] | None = None) -> int:
    import research_web

    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(
        prog="candidate_search/repicture.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--old-run", required=True, type=Path, help="candidates-2026-10-06")
    parser.add_argument("--need", required=True, choices=NEEDS)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--served-run", type=Path, default=None)
    parser.add_argument("--sites", type=Path, default=None)
    parser.add_argument("--calibration-dir", type=Path, default=None)
    parser.add_argument("--read", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    required = {
        "recheck": ("run_dir", "served_run"),
        "credit": ("sites",),
        "calibration": ("calibration_dir", "read"),
        "pool": ("run_dir",),
    }[args.need]
    try:
        absent = [f"--{name.replace('_', '-')}" for name in required if getattr(args, name) is None]
        if absent:
            raise RepictureError(f"--need {args.need} needs {', '.join(absent)}")
        if args.need == "recheck":
            needed = need_recheck(args.old_run, args.run_dir, args.served_run)
        elif args.need == "credit":
            needed = need_credit(args.old_run, args.sites)
        elif args.need == "calibration":
            needed = need_calibration(args.old_run, args.calibration_dir, args.read)
        else:
            needed = need_pool(args.old_run, args.run_dir)
        commons = CM.Commons(args.old_run / "commons", research_web.client(), pace=CM.PACE_SECONDS)
        payload = repicture(args.old_run, args.need, needed, commons, dry_run=args.dry_run)
    except (ST.StateError, CM.CommonsError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if payload.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
