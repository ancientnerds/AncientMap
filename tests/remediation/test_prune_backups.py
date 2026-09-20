"""Behavioural tests for scripts/remediation/00_prune_backups.sh.

This script deletes directories, so its retention logic is tested rather than assumed. The
test builds a synthetic backup tree with controlled mtimes and runs the real script against
it - there is no reimplementation here, because a reimplementation would pass while the
script was broken.

Scope note: these run against a temporary BACKUP_ROOT, never the real backup directory.

The case that matters most is `test_hand_made_backup_is_never_pruned`: the backups directory
also holds a hand-taken pre-audit restore point, and a pruner that globs too widely would
delete the very thing it exists to protect.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PRUNER = REPO / "scripts" / "remediation" / "00_prune_backups.sh"

# shutil.which returns Optional[str]; narrowing it here keeps the constant typed as str for
# the subprocess argument lists while `_BASH_MISSING` drives the skip below.
_BASH = shutil.which("bash")
BASH: str = _BASH or ""
BASH_MISSING = _BASH is None

pytestmark = pytest.mark.skipif(BASH_MISSING, reason="bash is not available")


def _bash_path(p: Path) -> str:
    """Render a path the way bash on this machine sees it.

    The script requires an absolute POSIX path (a bad BACKUP_ROOT must not become a recursive
    delete), but pytest's tmp_path is `C:\\Users\\...` on Windows, which is not absolute to
    Git Bash. Without this translation every case below would silently skip on Windows - a
    skip that looks green is worse than a failure.
    """
    if os.name != "nt":
        return str(p)
    cygpath = shutil.which("cygpath")
    if cygpath is None:
        return str(p)  # the script will refuse it and the sanity fixture skips loudly
    out = subprocess.run([cygpath, "-u", str(p)], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _run(
    root: Path, *args: str, keep: str = "7", dry_run: str = "0"
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, BACKUP_ROOT=_bash_path(root), KEEP=keep, DRY_RUN=dry_run)
    return subprocess.run(
        [BASH, str(PRUNER), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _stamps(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.name.endswith("_remediation"))


def _make_tree(root: Path, count: int = 10) -> None:
    """Create `count` stamp dirs with strictly increasing mtimes, plus decoys."""
    for i in range(1, count + 1):
        d = root / f"2026-09-{i:02d}_remediation"
        d.mkdir()
        (d / "database.dump").write_text("dump", encoding="utf-8")
        # A fixed, increasing mtime - the pruner sorts by time, so order must be unambiguous.
        mtime = 1_756_000_000 + i * 3600
        os.utime(d, (mtime, mtime))
    # A hand-made restore point that must survive every run.
    pre = root / "2026-09-19_pre-audit"
    pre.mkdir()
    os.utime(pre, (1_756_000_000 + 99 * 3600, 1_756_000_000 + 99 * 3600))
    # A non-directory in the same folder must not disturb anything.
    (root / "cron.log").write_text("log", encoding="utf-8")


@pytest.fixture(autouse=True)
def _sanity(root_factory):  # type: ignore[no-untyped-def]
    """Skip loudly if the script cannot run here at all.

    Without this, a missing interpreter or an unsupported `stat` would make the refusal
    tests below pass for the wrong reason: a command that cannot start also exits non-zero.
    """
    root = root_factory([])
    proc = _run(root, "x")
    if proc.returncode != 0:
        pytest.skip(f"00_prune_backups.sh cannot run in this environment: {proc.stderr.strip()}")


@pytest.fixture
def root_factory(tmp_path):  # type: ignore[no-untyped-def]
    def make(count: list[str] | int = 10) -> Path:
        d = tmp_path / f"backups{len(list(tmp_path.iterdir()))}"
        d.mkdir()
        if isinstance(count, int):
            _make_tree(d, count)
        return d

    return make


def test_prunes_only_beyond_keep(root_factory) -> None:  # type: ignore[no-untyped-def]
    root = root_factory()
    proc = _run(root, "2026-09-10_remediation", keep="7")
    assert proc.returncode == 0, proc.stderr
    assert len(_stamps(root)) == 7
    assert not (root / "2026-09-01_remediation").exists()
    assert not (root / "2026-09-03_remediation").exists()
    # Boundary: the 7 newest are kept, so 04 survives and 03 does not.
    assert (root / "2026-09-04_remediation").exists()
    assert (root / "2026-09-10_remediation").exists()


def test_hand_made_backup_is_never_pruned(root_factory) -> None:  # type: ignore[no-untyped-def]
    root = root_factory()
    _run(root, "2026-09-10_remediation", keep="1")
    assert (root / "2026-09-19_pre-audit").is_dir(), "the pre-audit restore point was deleted"
    assert (root / "cron.log").is_file(), "a non-directory was deleted"


def test_protected_stamp_survives_when_older_than_keep(root_factory) -> None:  # type: ignore[no-untyped-def]
    root = root_factory()
    _run(root, "2026-09-01_remediation", keep="3")
    assert (root / "2026-09-01_remediation").is_dir()
    assert len(_stamps(root)) == 4  # the 3 newest plus the protected one


def test_keep_zero_keeps_only_the_protected_stamp(root_factory) -> None:  # type: ignore[no-untyped-def]
    root = root_factory()
    _run(root, "2026-09-05_remediation", keep="0")
    assert _stamps(root) == ["2026-09-05_remediation"]
    assert (root / "2026-09-19_pre-audit").is_dir()


def test_dry_run_deletes_nothing(root_factory) -> None:  # type: ignore[no-untyped-def]
    root = root_factory()
    before = _stamps(root)
    _run(root, "2026-09-10_remediation", keep="2", dry_run="1")
    assert _stamps(root) == before


def test_keep_larger_than_tree_deletes_nothing(root_factory) -> None:  # type: ignore[no-untyped-def]
    root = root_factory()
    _run(root, "2026-09-10_remediation", keep="99")
    assert len(_stamps(root)) == 10


def test_real_run_does_not_claim_to_be_a_dry_run(root_factory) -> None:  # type: ignore[no-untyped-def]
    """Regression: `"${DRY_RUN:+ (dry run)}"` printed "(dry run)" on REAL runs.

    It tested whether the variable was set, not whether it was "1", and the script itself
    defaults it to "0" - so every real deletion was reported as a rehearsal. An operator
    reading that would believe nothing had been deleted while backups were being removed.
    """
    root = root_factory()
    proc = _run(root, "2026-09-10_remediation", keep="2")
    assert "dry run" not in proc.stdout, f"a real run claimed to be a dry run: {proc.stdout!r}"
    assert "deleted" in proc.stdout
    # ...and it really did delete, so the message and the behaviour agree.
    assert not (root / "2026-09-01_remediation").exists()
    assert len(_stamps(root)) == 2


def test_dry_run_says_so_and_deletes_nothing(root_factory) -> None:  # type: ignore[no-untyped-def]
    root = root_factory()
    proc = _run(root, "2026-09-10_remediation", keep="2", dry_run="1")
    assert "dry run" in proc.stdout
    assert (root / "2026-09-01_remediation").is_dir()


def test_empty_root_is_a_successful_no_op(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    (root / "unrelated").mkdir()
    proc = _run(root, "x")
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize(
    ("env_root", "expected_message"),
    [
        ("/", "must not be /"),
        ("relative/path", "must be an absolute path"),
        ("/nonexistent_dir_for_prune_test", "is not a directory"),
    ],
)
def test_refuses_dangerous_roots(env_root: str, expected_message: str, tmp_path: Path) -> None:
    """A bad BACKUP_ROOT must not turn this into a recursive delete of something else.

    Asserts the reason, not merely a non-zero exit: a script that fails to start also exits
    non-zero and would otherwise look like a correct refusal.
    """
    env = dict(os.environ, BACKUP_ROOT=env_root, KEEP="7", DRY_RUN="0")
    proc = subprocess.run(
        [BASH, str(PRUNER), "x"], capture_output=True, text=True, env=env, check=False
    )
    assert proc.returncode != 0
    assert expected_message in proc.stderr


def test_refuses_non_numeric_keep(root_factory) -> None:  # type: ignore[no-untyped-def]
    root = root_factory()
    proc = _run(root, "x", keep="abc")
    assert proc.returncode != 0
    assert "non-negative integer" in proc.stderr
