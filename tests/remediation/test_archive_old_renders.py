"""D25: archive the 16 old renders (`scripts/remediation/archive_old_renders.py`).

The planning, the manifest and the move run on a tmp tree; no video of the real tree is touched.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import archive_old_renders as A  # noqa: E402

SLUGS = ("alpha", "beta")


def _tree(root: Path) -> Path:
    shorts = root / "shorts"
    for slug in SLUGS:
        (shorts / slug / "clips").mkdir(parents=True)
        (shorts / slug / "final.mp4").write_bytes(f"{slug}-final".encode())
        (shorts / slug / "clips" / "c1.mp4").write_bytes(f"{slug}-c1".encode())
        (shorts / slug / "audit.json").write_text("{}")
    (shorts / "kerbatch").mkdir()
    (shorts / "kerbatch" / "k.mp4").write_bytes(b"stays")
    (shorts / "QA-NOTES.md").write_text("stays")
    return shorts


def test_the_sixteen_slugs_are_distinct_and_match_infra_3_5():
    assert len(A.SLUGS) == 16 == len(set(A.SLUGS))
    assert "kerbatch" not in A.SLUGS and "voice-samples" not in A.SLUGS
    # the map names "olympia" etc.; the directories carry the full site slugs
    assert "archaeological-site-of-olympia" in A.SLUGS
    assert "karatepe-aslantaş-open-air-museum" in A.SLUGS


def test_plan_lists_one_move_per_slug(tmp_path):
    shorts = _tree(tmp_path)
    archive = tmp_path / "shorts-archive"
    moves = A.plan_moves(shorts, archive, SLUGS)
    assert [(m.source, m.target) for m in moves] == [
        (shorts / "alpha", archive / "alpha"),
        (shorts / "beta", archive / "beta"),
    ]


def test_plan_refuses_a_missing_source(tmp_path):
    shorts = _tree(tmp_path)
    with pytest.raises(A.ArchiveError, match="gamma"):
        A.plan_moves(shorts, tmp_path / "a", (*SLUGS, "gamma"))


def test_plan_refuses_an_existing_target(tmp_path):
    shorts = _tree(tmp_path)
    archive = tmp_path / "a"
    (archive / "beta").mkdir(parents=True)
    with pytest.raises(A.ArchiveError, match="beta"):
        A.plan_moves(shorts, archive, SLUGS)


def test_plan_refuses_an_existing_manifest(tmp_path):
    shorts = _tree(tmp_path)
    archive = tmp_path / "a"
    archive.mkdir()
    (archive / A.MANIFEST).write_text("")
    with pytest.raises(A.ArchiveError, match=A.MANIFEST):
        A.plan_moves(shorts, archive, SLUGS)


def test_manifest_hashes_every_mp4_below_the_given_dirs_with_posix_relative_paths(tmp_path):
    shorts = _tree(tmp_path)
    got = A.build_manifest(shorts, SLUGS)
    assert list(got) == [
        "alpha/clips/c1.mp4",
        "alpha/final.mp4",
        "beta/clips/c1.mp4",
        "beta/final.mp4",
    ]
    assert got["alpha/final.mp4"] == hashlib.sha256(b"alpha-final").hexdigest()


def test_manifest_text_round_trip():
    m = {"a/x.mp4": "a" * 64, "b/y.mp4": "b" * 64}
    assert A.parse_manifest(A.format_manifest(m)) == m
    assert A.format_manifest(m).splitlines()[0] == f"{'a' * 64}  a/x.mp4"


def test_require_same_manifest_names_the_difference():
    a = {"x.mp4": "1" * 64, "y.mp4": "2" * 64}
    A.require_same_manifest(a, dict(a))
    with pytest.raises(A.ArchiveError, match="y.mp4"):
        A.require_same_manifest(a, {"x.mp4": "1" * 64, "y.mp4": "3" * 64})
    with pytest.raises(A.ArchiveError, match="z.mp4"):
        A.require_same_manifest(a, {**a, "z.mp4": "4" * 64})
    with pytest.raises(A.ArchiveError, match="x.mp4"):
        A.require_same_manifest(a, {"y.mp4": "2" * 64})


def test_dry_run_moves_and_writes_nothing(tmp_path, capsys):
    shorts = _tree(tmp_path)
    archive = tmp_path / "shorts-archive"
    assert A.main(["--shorts-dir", str(shorts), "--archive-dir", str(archive)], slugs=SLUGS) == 0
    assert (shorts / "alpha" / "final.mp4").exists()
    assert not archive.exists()
    out = capsys.readouterr().out
    assert "dry run" in out and "alpha" in out and "2 mp4" in out


def test_apply_moves_the_slugs_and_proves_the_hashes(tmp_path):
    shorts = _tree(tmp_path)
    archive = tmp_path / "shorts-archive"
    before = A.build_manifest(shorts, SLUGS)
    rc = A.main(
        ["--shorts-dir", str(shorts), "--archive-dir", str(archive), "--apply"], slugs=SLUGS
    )
    assert rc == 0
    assert not (shorts / "alpha").exists() and not (shorts / "beta").exists()
    assert (archive / "alpha" / "clips" / "c1.mp4").read_bytes() == b"alpha-c1"
    assert (shorts / "kerbatch" / "k.mp4").exists() and (shorts / "QA-NOTES.md").exists()
    assert A.parse_manifest((archive / A.MANIFEST).read_text()) == before
    assert A.parse_manifest((archive / A.MANIFEST_AFTER).read_text()) == before


def test_apply_refuses_when_a_target_exists_and_moves_nothing(tmp_path):
    shorts = _tree(tmp_path)
    archive = tmp_path / "shorts-archive"
    (archive / "beta").mkdir(parents=True)
    with pytest.raises(A.ArchiveError, match="beta"):
        A.main(["--shorts-dir", str(shorts), "--archive-dir", str(archive), "--apply"], slugs=SLUGS)
    assert (shorts / "alpha" / "final.mp4").exists()
    assert not (archive / A.MANIFEST).exists()
