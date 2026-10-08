"""D25: archive the 16 old renders (`output/remediation/final-2026-10-08/plans/infra.md` 3.5).

Moves the 16 retired site dirs (HUMAN_ONLY_DECISIONS Nr. 11) from `video-assets/shorts/` to
`video-assets/shorts-archive-2026-10-08/`. A move, never a copy and never a delete: `os.rename` on
the same drive, so nothing is duplicated and a target on another drive fails instead of copying.
`kerbatch`, `voice-samples`, the logs, `AUDIT-REPORT.md` and `QA-NOTES.md` stay where they are. No
render, no upload; the VPS copy `video-assets-offsite` is not touched.

`MANIFEST.sha256` (sha256 of every `*.mp4` of the 16 dirs, written BEFORE the first move) and
`MANIFEST.after.sha256` (the same read from the archive AFTER the last move) must be identical, or
the run fails. Dry run by default; `--apply` moves. It refuses when a source dir is missing, when a
target dir exists or when `MANIFEST.sha256` exists, and then moves nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VIDEO_ASSETS = Path("C:/PythonProjects/AncientMap/video-assets")
MANIFEST = "MANIFEST.sha256"
MANIFEST_AFTER = "MANIFEST.after.sha256"
#: The directory names as measured on disk 2026-10-08 (infra.md 3.5 lists them by short name).
SLUGS = (
    "archaeological-site-of-olympia",
    "archaeological-site-puma-punku",
    "federsee",
    "giza-necropolis",
    "gochang-hwasun-and-ganghwa-dolmen-sites",
    "ishtar-gate",
    "karatepe-aslantaş-open-air-museum",
    "machu-picchu",
    "nazca-lines",
    "pamukkale",
    "rano-raraku",
    "senegambian-stone-circles",
    "stonehenge",
    "tahai-ceremonial-complex",
    "teotihuacan",
    "tomb-of-jahangir",
)


class ArchiveError(RuntimeError):
    """A refusal or a failed proof; nothing further is moved."""


@dataclass(frozen=True)
class Move:
    source: Path
    target: Path


def plan_moves(shorts: Path, archive: Path, slugs: tuple[str, ...]) -> list[Move]:
    missing = [s for s in slugs if not (shorts / s).is_dir()]
    if missing:
        raise ArchiveError(f"source dir missing under {shorts}: {', '.join(missing)}")
    existing = [s for s in slugs if (archive / s).exists()]
    if existing:
        raise ArchiveError(f"target exists under {archive}, refusing: {', '.join(existing)}")
    if (archive / MANIFEST).exists():
        raise ArchiveError(f"{archive / MANIFEST} exists, refusing to overwrite it")
    return [Move(shorts / s, archive / s) for s in slugs]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mp4_files(root: Path, slug: str) -> list[Path]:
    return sorted((root / slug).rglob("*.mp4"))


def build_manifest(root: Path, slugs: tuple[str, ...]) -> dict[str, str]:
    """sha256 of every mp4 below `root/<slug>`, keyed by its posix path relative to `root`."""
    return {p.relative_to(root).as_posix(): _sha256(p) for s in slugs for p in mp4_files(root, s)}


def format_manifest(manifest: dict[str, str]) -> str:
    return "".join(f"{digest}  {name}\n" for name, digest in manifest.items())


def parse_manifest(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        digest, sep, name = line.partition("  ")
        if not sep or len(digest) != 64:
            raise ArchiveError(f"unreadable manifest line: {line!r}")
        out[name] = digest
    return out


def require_same_manifest(before: dict[str, str], after: dict[str, str]) -> None:
    problems = [f"missing after: {n}" for n in before if n not in after]
    problems += [f"new after: {n}" for n in after if n not in before]
    problems += [f"hash differs: {n}" for n in before if n in after and before[n] != after[n]]
    if problems:
        raise ArchiveError("manifest before and after differ: " + "; ".join(problems))


def main(argv: list[str] | None = None, slugs: tuple[str, ...] = SLUGS) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--shorts-dir", type=Path, default=DEFAULT_VIDEO_ASSETS / "shorts")
    ap.add_argument(
        "--archive-dir", type=Path, default=DEFAULT_VIDEO_ASSETS / "shorts-archive-2026-10-08"
    )
    ap.add_argument("--apply", action="store_true", help="move the dirs (default: dry run)")
    args = ap.parse_args(argv)
    shorts, archive = args.shorts_dir, args.archive_dir

    moves = plan_moves(shorts, archive, slugs)
    total = 0
    for m in moves:
        n = len(mp4_files(shorts, m.source.name))
        total += n
        print(f"{m.source.name}: {n} mp4 -> {m.target}")
    print(f"{len(moves)} dirs, {total} mp4")
    if not args.apply:
        print("dry run: nothing moved; --apply moves")
        return 0

    before = build_manifest(shorts, slugs)
    archive.mkdir(parents=True, exist_ok=True)
    (archive / MANIFEST).write_text(format_manifest(before), encoding="utf-8", newline="\n")
    print(f"{MANIFEST}: {len(before)} files hashed before the move")
    for m in moves:
        os.rename(m.source, m.target)
    after = build_manifest(archive, slugs)
    (archive / MANIFEST_AFTER).write_text(format_manifest(after), encoding="utf-8", newline="\n")
    require_same_manifest(before, after)
    print(f"moved {len(moves)} dirs; {MANIFEST_AFTER} identical to {MANIFEST} ({len(after)} files)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # a cp1252 console cannot print "karatepe-aslantaş"
    try:
        sys.exit(main())
    except ArchiveError as exc:
        sys.exit(f"archive_old_renders: {exc}")
