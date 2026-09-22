"""The VLM pilot's row -> image file lookup (`scripts/remediation/vlm_pilot/common.py`).

The offsite image tree lives on NTFS, where `Path.is_file()` accepts `Huelva.webp` for `HUELVA.webp`.
The lookup compares against the directory listing instead, main tree first, then the case-collision
tree - and `rejected_kinds.py` and `make_sample.py` both go through it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VLM_PILOT = REPO / "scripts" / "remediation" / "vlm_pilot"
if str(VLM_PILOT) not in sys.path:
    sys.path.insert(0, str(VLM_PILOT))

import common  # noqa: E402

SITE_ID = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
SHARD = "0a1b2c3d"


def _tree(root: Path, *names: str) -> Path:
    shard = root / SHARD
    shard.mkdir(parents=True)
    for name in names:
        (shard / name).write_bytes(b"RIFF\x00\x00\x00\x00WEBP" + name.encode())
    return root


def test_only_the_exact_case_name_resolves_and_the_main_tree_comes_first(tmp_path: Path) -> None:
    main = _tree(tmp_path / "images", "HUELVA.webp", "both.webp")
    collisions = _tree(tmp_path / "collisions", "Huelva.webp", "both.webp")
    trees = ((main, common.build_tree(main)), (collisions, common.build_tree(collisions)))
    hit = common.locate(trees, SITE_ID, "Huelva.webp")
    assert hit is not None and hit[0] == collisions / SHARD / "Huelva.webp"
    assert common.locate(trees, SITE_ID, "both.webp")[0] == main / SHARD / "both.webp"  # type: ignore[index]
    # The case-insensitive probe this replaces would accept a name that is not there.
    assert common.locate(trees, SITE_ID, "huelva.webp") is None
    if (main / SHARD / "huelva.webp").is_file():  # true on NTFS: exactly the defect
        assert common.locate(((main, common.build_tree(main)),), SITE_ID, "huelva.webp") is None
    assert hit[1] == (collisions / SHARD / "Huelva.webp").stat().st_size


def test_a_missing_image_tree_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        common.build_tree(tmp_path / "not-there")
