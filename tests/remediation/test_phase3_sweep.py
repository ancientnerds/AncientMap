"""The mutation sweep is the instrument every other guard is measured with, so the instrument gets
its own tests - in a throwaway tree, because a sweep test that touches the real one can leave a
mutant behind, which is the very failure it exists to prevent.

Both failure modes here are measured, not guessed. On 2026-09-21 this sweep died inside its own loop
(`TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'`) and left a mutant in
`discover_stage.py`:

* `stdout` came back **None**, because the child's output had been decoded with the locale's codec
  (cp1252) and a UTF-8 byte outside cp1252 killed `subprocess`'s reader thread.
* nothing restored the file, because the copy back happened *after* the line that raised.

So one test pins the encoding the child is read with, and one pins that the restore is not tied to
the mutation being caught.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import mutation_sweep as S  # noqa: E402

MUTATION = "the JSON escapes in the evidence are not undone"
TARGET = Path("scripts/remediation/phase3/discover_stage.py")


def _throwaway_tree(tmp_path: Path) -> Path:
    """A copy of the one file this mutation targets, plus nothing else the sweep may touch."""
    root = tmp_path / "repo"
    (root / TARGET).parent.mkdir(parents=True)
    shutil.copy2(S.REPO / TARGET, root / TARGET)
    return root


def _stub(
    monkeypatch: pytest.MonkeyPatch, code: int, stdout: str | None
) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, code, stdout, None)

    monkeypatch.setattr(S.subprocess, "run", fake_run)
    return calls


def test_a_child_whose_output_cannot_be_read_does_not_kill_the_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _throwaway_tree(tmp_path)
    before = (root / TARGET).read_bytes()
    calls = _stub(monkeypatch, code=1, stdout=None)  # exactly what the locale bug produced

    assert S.main([MUTATION], repo=root, backup_dir=tmp_path / "backup") == 0  # caught, not crashed
    assert (root / TARGET).read_bytes() == before

    encoded = [c for c in calls if "encoding" in c]
    assert encoded, "the child is read without an explicit encoding - the locale decides, not us"
    assert encoded[0]["encoding"] == "utf-8"
    assert encoded[0]["env"]["PYTHONIOENCODING"] == "utf-8"  # type: ignore[index]


def test_a_mutation_that_is_not_caught_is_still_undone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The restore must not depend on the verdict: a survived mutation is still a mutant in the tree."""
    root = _throwaway_tree(tmp_path)
    before = (root / TARGET).read_bytes()
    _stub(monkeypatch, code=0, stdout="1 passed")  # the test did not notice the mutation

    assert S.main([MUTATION], repo=root, backup_dir=tmp_path / "backup") == 1  # reported as missed
    assert (root / TARGET).read_bytes() == before


def test_final_drift_names_a_file_that_changed_under_the_sweep(tmp_path: Path) -> None:
    """The end check is about the TREE, not about the loop - which is why the loop cannot make it.

    Every per-mutation comparison ran earlier, so a writer that touches a `phase3/` file *after* the
    last restore is invisible to all of them. That is not hypothetical: on 2026-09-21 pi-lens wrote
    into `discover_stage.py` at 13:02 while a sweep was running, and into `snapshot_plan.py`
    afterwards, where it deleted the `"country"` element from `DISCOVER_FIELDS` and called it a
    reformat. Caught by hand that day, and this check is the instrument that replaces the hand.
    """
    root = _throwaway_tree(tmp_path)
    before = {str(TARGET): S.digest(root / TARGET)}
    assert S.final_drift(root, before) == {}  # the sweep's own restore leaves no drift

    (root / TARGET).write_text("x = 1  # a plugin, not this sweep\n", encoding="utf-8")

    drift = S.final_drift(root, before)
    assert list(drift) == [str(TARGET)]  # named, not merely counted
    was, now = drift[str(TARGET)]
    assert was == before[str(TARGET)]
    assert now == S.digest(root / TARGET)
    assert was != now


def test_every_mutation_names_an_anchor_and_a_test_that_exist() -> None:
    """An entry whose anchor moved does not prove anything - it stops the whole sweep at its assert.

    Measured 2026-09-23: the narrowed-route change rewrote `if feature == FEATURE_WIKIDATA_ENTITY and
    not qid:` as `if slot == ...`, and the "no qid, no qid skip" entry had pointed at nothing since;
    the gap branch ran only its own 19 entries, so no run noticed. This reads every entry against
    the tree, without mutating anything, and fails on the first one that no longer lands.
    """
    stale = [
        name
        for name, rel, old, _new, test_file, test_name in S.MUTATIONS
        if (REPO / rel).read_text(encoding="utf-8").count(old) < 1
        or f"def {test_name}(" not in (REPO / test_file).read_text(encoding="utf-8")
    ]
    assert stale == []
