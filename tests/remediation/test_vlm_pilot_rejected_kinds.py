"""The rejected-kinds record resolves an image by its exact-case name, never by `Path.is_file()`.

`scripts/remediation/vlm_pilot/rejected_kinds.py` maps each kind-labelled rejection of a short to its
file under the offsite image trees. On this Windows checkout `Path.is_file()` answers yes for a name
that differs only in case, which is the mismatch `common.build_tree` exists to catch - so the lookup
goes through the tree listings, and a missing tree root stops the script instead of turning every
lookup into "not on disk". (Re-measured 2026-09-23: the exact-case lookup reproduces all 30
`resolved_path` values of the versioned `REJECTED_KINDS.jsonl`.)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PILOT = Path(__file__).resolve().parents[2] / "scripts" / "remediation" / "vlm_pilot"
if str(PILOT) not in sys.path:
    sys.path.insert(0, str(PILOT))

import rejected_kinds as RK  # noqa: E402
from common import build_tree, shard_for  # noqa: E402

SITE = "abcdef12-0000-4000-8000-000000000001"


def _tree(root: Path, *names: str) -> dict[str, dict[str, int]]:
    shard = root / shard_for(SITE)
    shard.mkdir(parents=True)
    for name in names:
        (shard / name).write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
    return build_tree(root)


def test_an_image_is_found_by_its_exact_name_first_in_the_main_tree(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "wiki", "Temple.webp")
    collisions = _tree(tmp_path / "collisions", "Gate.webp")
    shard = shard_for(SITE)
    assert RK.image_on_disk(tree, collisions, SITE, "Temple.webp") == (
        RK.OFFSITE_IMAGES / shard / "Temple.webp"
    )
    assert RK.image_on_disk(tree, collisions, SITE, "Gate.webp") == (
        RK.OFFSITE_CASE_COLLISIONS / shard / "Gate.webp"
    )
    assert RK.image_on_disk(tree, collisions, SITE, "Missing.webp") is None


def test_a_name_that_differs_only_in_case_is_not_the_file(tmp_path: Path) -> None:
    """`Path.is_file()` says yes here on Windows; the listing says no."""
    tree = _tree(tmp_path / "wiki", "Temple.webp")
    assert RK.image_on_disk(tree, {}, SITE, "temple.webp") is None


def test_a_missing_image_tree_stops_the_listing() -> None:
    with pytest.raises(FileNotFoundError):
        build_tree(Path("C:/no/such/offsite/tree"))
