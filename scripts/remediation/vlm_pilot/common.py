"""Shared paths and the proven `wiki_images` row -> image file mapping.

The mapping rule, with its evidence, is written up in
`output/remediation/vlm_pilot/METHOD.md` section 1 and re-proved on every run by
`prove_mapping.py`. In one line:

    <offsite>/images/wiki/<site_id hex, dashes removed, first 8 chars>/<filename>

Both halves come from the production code, not from observation:
`pipeline/wiki_image_downloader.py:155-157` (`site_image_dir` returns
`IMAGE_DIR / site_id[:8]`) and `:1001-1007` (the `filename` column: `hero.webp`
for the first image of a site, otherwise the sanitised Commons file title with
its extension forced to `.webp`). `pipeline/static_exporter.py:569-572` writes
the same pair into `images/index.json` as a URL, and
`scripts/reindex_wiki_images.py:77-95` reads the directory name back as "the
first 8 chars of the UUID without dashes".

Case matters: NTFS resolves `Huelva.webp` to `HUELVA.webp`, so every lookup here
compares against the directory listing instead of trusting `Path.is_file()`.
Three files whose names differ from a sibling only in case live in
`images-case-collisions/` on this machine (see that tree's README); they are
searched too, second.
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterator, Mapping

#: Repository root, derived from this file's location (`scripts/remediation/vlm_pilot/`).
REPO_ROOT = Path(__file__).resolve().parents[3]

# Importing this module must be enough to reach `pipeline.*` and its own siblings,
# whether the caller was launched as a script from `scripts/remediation/vlm_pilot/`
# or with the repository root as the working directory.
for _entry in (REPO_ROOT, Path(__file__).resolve().parent):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

#: The offsite copy of the production image tree. 49,785 `.webp` in
#: `images/wiki`, plus the three case-collision files.
OFFSITE_ROOT = Path("C:/PythonProjects/AncientMap-Offsite")
OFFSITE_IMAGES = OFFSITE_ROOT / "images" / "wiki"
OFFSITE_CASE_COLLISIONS = OFFSITE_ROOT / "images-case-collisions" / "wiki"

OUT_DIR = REPO_ROOT / "output" / "remediation" / "vlm_pilot"

#: The frozen 2026-09-20T20:20:01+02:00 export of the production database.
SNAPSHOT_DIR = REPO_ROOT / "output" / "remediation" / "snapshot"
WIKI_IMAGES_SNAPSHOT = SNAPSHOT_DIR / "wiki_images.jsonl.gz"
UNIFIED_SITES_SNAPSHOT = SNAPSHOT_DIR / "unified_sites.jsonl.gz"
CARD_STATS_SNAPSHOT = SNAPSHOT_DIR / "card_stats.jsonl.gz"

#: T10's per-row tier verdicts, one finding per `wiki_images` row.
T10_FINDINGS = REPO_ROOT / "output" / "remediation" / "run_t10" / "findings.jsonl"

#: The downloader's own URL shape for a stored file
#: (`pipeline/wiki_image_downloader.py:1126`).
URL_PREFIX = "/data/images/wiki"

WEBP_MAGIC_OFFSET = 8


def shard_for(site_id: str) -> str:
    """The on-disk shard directory for a site: first 8 hex chars of the UUID.

    Same spelling as `pipeline/sites_html_renderer.py:22-24` `site_id_short`.
    """
    return str(site_id).replace("-", "")[:8]


def image_url(site_id: str, filename: str) -> str:
    """The row's URL on the site, as the exporter writes it."""
    return f"{URL_PREFIX}/{shard_for(site_id)}/{filename}"


def read_jsonl_gz(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_tree(root: Path) -> dict[str, dict[str, int]]:
    """One scandir pass over an image tree: shard -> {exact filename: size}.

    Returns the exact-case names, which is the point: a Windows lookup would
    otherwise accept a case-only mismatch as a hit.
    """
    tree: dict[str, dict[str, int]] = {}
    for shard in os.scandir(root):
        if not shard.is_dir():
            continue
        files: dict[str, int] = {}
        for entry in os.scandir(shard.path):
            if entry.is_file():
                files[entry.name] = entry.stat().st_size
        tree[shard.name] = files
    return tree


def resolve(
    tree: Mapping[str, Mapping[str, int]], site_id: str, filename: str
) -> tuple[str, int] | None:
    """(exact filename found, size) for a row, or None.

    The shard is always `<site_id[:8]>`; only the exact-case name is accepted.
    """
    files = tree.get(shard_for(site_id))
    if not files:
        return None
    size = files.get(filename)
    if size is None:
        return None
    return filename, size


def is_webp(path: Path) -> tuple[bool, str]:
    """Read the header only: `RIFF....WEBP` (12 bytes)."""
    with open(path, "rb") as handle:
        head = handle.read(12)
    if len(head) < 12:
        return False, head.hex()
    ok = head[0:4] == b"RIFF" and head[8:12] == b"WEBP"
    return ok, head.hex()


def webp_bytes_ok(path: Path) -> bool:
    ok, _ = is_webp(path)
    return ok


def site_names(snapshot: Path = UNIFIED_SITES_SNAPSHOT) -> dict[str, str]:
    return {row["id"]: row["name"] for row in read_jsonl_gz(snapshot)}


def card_descriptions(snapshot: Path = CARD_STATS_SNAPSHOT) -> dict[str, str]:
    """`card_stats.card_description` - the text `shorts_export.py:230` turns into `card_text`."""
    out: dict[str, str] = {}
    for row in read_jsonl_gz(snapshot):
        out[row["site_id"]] = (row.get("card_description") or "").strip()
    return out


def site_descriptions(snapshot: Path = UNIFIED_SITES_SNAPSHOT) -> dict[str, str]:
    return {row["id"]: (row.get("description") or "").strip() for row in read_jsonl_gz(snapshot)}


def image_rows() -> dict[int, dict[str, Any]]:
    """`wiki_images.id` -> the snapshot row, for the two columns T10's findings omit
    (`title`, the Commons file title the VLM prompt is fed, and `original_url`)."""
    return {row["id"]: row for row in read_jsonl_gz(WIKI_IMAGES_SNAPSHOT)}
