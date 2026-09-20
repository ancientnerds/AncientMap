"""Teeth for scripts/merge_rewrites.py: it must not be able to report success without succeeding.

The script this replaces contained no `sys.exit` at all. In a faithful sandbox it exited 0 while:
  * all ten rewrite batches were missing (it printed a WARNING and copied to public/data/ anyway),
  * every rewrite in the one present batch was invalid (it printed the errors and applied the
    valid subset, because the apply loop never consulted `errors`).
`docs/procedures/FIELD_CONTRACT.md:220` records the consequence: "Do not trust its exit code."

These tests drive the REAL merge_rewrites.py and the REAL verify_descriptions.py in a throwaway
tree. Both resolve their paths from `__file__` (`ROOT = Path(__file__).resolve().parent.parent`),
so copying them into <tmp>/scripts/ makes <tmp> the project root - nothing under the real
repository is read or written.

Every guard is shown capable of failing: test_mutation_guard_is_load_bearing removes the
incomplete-batch guard from a copy of the script and shows the corresponding test then breaks.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
REAL_MERGE = REPO / "scripts" / "merge_rewrites.py"
REAL_VERIFY = REPO / "scripts" / "verify_descriptions.py"

NUM_BATCHES = 10

# Exit codes the script contracts on.
EXIT_INPUT = 1
EXIT_INCOMPLETE = 2
EXIT_INVALID = 3
EXIT_NOTHING = 4
EXIT_REGRESSED = 5

CLEAN = [
    "Kyffhauser hillfort crowned a ridge above the plain.",
    "Vix grave held a bronze krater of exceptional size.",
    "Alepotrypa cave mouth opened onto a sheltered valley.",
    "Stari Grad plain retains its Greek field divisions.",
    "Nebra sky disc emerged from a hilltop enclosure.",
    "Chauvet cave paintings line a limestone gallery.",
]


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_sandbox(
    tmp_path: Path,
    *,
    descriptions: dict[str, str] | None = None,
    batches: dict[int, dict[str, Any]] | None = None,
    merge_src: Path | None = None,
) -> Path:
    """Create a throwaway project root with the real scripts and controlled fixtures.

    descriptions: dict of site_id -> text (defaults to CLEAN, one per index)
    batches:      dict of batch index -> {"rewrites": {...}}; absent indexes are MISSING files
    merge_src:    source text for merge_rewrites.py (used by the mutation test)
    """
    root = tmp_path
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)
    (root / "public" / "data").mkdir(parents=True, exist_ok=True)

    shutil.copy2(merge_src or REAL_MERGE, root / "scripts" / "merge_rewrites.py")
    shutil.copy2(REAL_VERIFY, root / "scripts" / "verify_descriptions.py")

    if descriptions is None:
        descriptions = {f"site-{i}": text for i, text in enumerate(CLEAN)}
    _write(root / "output" / "card_descriptions.json", {"descriptions": descriptions})
    _write(
        root / "output" / "card_sites.json",
        [
            {"site_id": sid, "name": f"Site {i}", "country": "Germany"}
            for i, sid in enumerate(descriptions)
        ],
    )
    # The deploy-relevant file, pre-existing, which a failed run must leave alone.
    _write(
        root / "public" / "data" / "card_descriptions.json",
        {"descriptions": {"sentinel": "untouched"}},
    )

    for index, payload in (batches or {}).items():
        _write(root / "output" / f"rewrite_output_{index:02d}.json", payload)

    return root


def run_merge(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "merge_rewrites.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(root),
    )


def public_payload(root: Path) -> dict[str, Any]:
    return json.loads(
        (root / "public" / "data" / "card_descriptions.json").read_text(encoding="utf-8")
    )


def output_payload(root: Path) -> dict[str, Any]:
    return json.loads((root / "output" / "card_descriptions.json").read_text(encoding="utf-8"))


def valid_batches(overrides: dict[int, str] | None = None) -> dict[int, dict[str, Any]]:
    """Ten batches, each rewriting one site with a clean sentence."""
    overrides = overrides or {}
    batches: dict[int, dict[str, Any]] = {}
    for i in range(NUM_BATCHES):
        sid = f"site-{i % 6}"
        text = overrides.get(i, "A revised sentence about this place sits here.")
        batches[i] = {"rewrites": {sid: text}}
    return batches


# --- the failure modes the old script reported as success -------------------------------------


def test_all_batches_missing_writes_nothing(tmp_path):
    """Today's real state: ten missing batch files must not touch public/data/."""
    root = build_sandbox(tmp_path, batches={})
    res = run_merge(root)
    assert res.returncode == EXIT_INCOMPLETE, res.stdout + res.stderr
    assert "missing" in res.stdout.lower()
    assert public_payload(root) == {"descriptions": {"sentinel": "untouched"}}
    assert "sentinel" not in output_payload(root)["descriptions"]


def test_partial_batches_write_nothing(tmp_path):
    """Nine of ten is not a merge either."""
    root = build_sandbox(tmp_path, batches=valid_batches())
    (root / "output" / "rewrite_output_09.json").unlink()
    res = run_merge(root)
    assert res.returncode == EXIT_INCOMPLETE, res.stdout + res.stderr
    assert public_payload(root) == {"descriptions": {"sentinel": "untouched"}}


def test_all_batches_empty_writes_nothing(tmp_path):
    """Ten present-but-empty batches are not a successful merge."""
    root = build_sandbox(tmp_path, batches={i: {"rewrites": {}} for i in range(NUM_BATCHES)})
    res = run_merge(root)
    assert res.returncode == EXIT_NOTHING, res.stdout + res.stderr
    assert public_payload(root) == {"descriptions": {"sentinel": "untouched"}}


@pytest.mark.parametrize(
    "bad,expected_fragment",
    [
        ("x" * 201, "too long"),
        ("no terminator here", "bad ending"),
    ],
)
def test_invalid_rewrite_writes_nothing(tmp_path, bad, expected_fragment):
    root = build_sandbox(tmp_path, batches=valid_batches({7: bad}))
    res = run_merge(root)
    assert res.returncode == EXIT_INVALID, res.stdout + res.stderr
    assert expected_fragment in res.stdout.lower()
    assert public_payload(root) == {"descriptions": {"sentinel": "untouched"}}


def test_invalid_rewrite_does_not_apply_the_valid_subset(tmp_path):
    """The old script applied everything that passed validation while printing the failures.

    A batch that carries one invalid rewrite is not trustworthy for the rest of its contents, so
    the correct behaviour is to apply none of them.
    """
    batches = valid_batches()
    batches[4]["rewrites"]["ghost-site"] = "An unknown id must abort the run."
    root = build_sandbox(tmp_path, batches=batches)
    res = run_merge(root)
    assert res.returncode == EXIT_INVALID, res.stdout + res.stderr
    assert "unknown site_id" in res.stdout.lower()
    assert public_payload(root) == {"descriptions": {"sentinel": "untouched"}}
    # Not one of the valid rewrites reached the working copy.
    assert output_payload(root)["descriptions"]["site-0"] == CLEAN[0]


def test_regression_rolls_back_and_leaves_public_alone(tmp_path):
    """A merge that makes the re-validation flag MORE descriptions must not be published.

    Three identical openers trip verify_descriptions.py's `repeated_opener` rule (3+ occurrences),
    which is a regression the script must notice - via the flag count, because that script's exit
    code carries no information (it contains no sys.exit).
    """
    opener = "Zarquon the moonbat surveyed this"
    batches = {
        0: {"rewrites": {"site-0": f"{opener} ridge above the plain."}},
        1: {"rewrites": {"site-1": f"{opener} bronze krater of note."}},
        2: {"rewrites": {"site-2": f"{opener} sheltered valley mouth."}},
    }
    for i in range(3, NUM_BATCHES):
        batches[i] = {"rewrites": {}}
    descriptions = {f"site-{i}": text for i, text in enumerate(CLEAN)}
    root = build_sandbox(tmp_path, descriptions=descriptions, batches=batches)

    res = run_merge(root)
    assert res.returncode == EXIT_REGRESSED, res.stdout + res.stderr
    assert "rolled back" in res.stdout.lower()
    assert public_payload(root) == {"descriptions": {"sentinel": "untouched"}}
    # The working copy is restored exactly, not left half-changed.
    assert output_payload(root)["descriptions"] == descriptions


def test_malformed_batch_fails_loudly_and_names_the_file(tmp_path):
    """A batch that is not valid JSON must be reported by name, not left as a bare traceback.

    The failure still happens - this is not a fallback. The point is that a run which cannot read
    its input must not be confusable with one that read it and found nothing.
    """
    batches = valid_batches()
    root = build_sandbox(tmp_path, batches=batches)
    (root / "output" / "rewrite_output_03.json").write_text("{not json at all", encoding="utf-8")
    res = run_merge(root)
    assert res.returncode == EXIT_INPUT, res.stdout + res.stderr
    assert "rewrite_output_03.json" in res.stdout, "the failing file must be named"
    assert "not valid JSON" in res.stdout
    assert public_payload(root) == {"descriptions": {"sentinel": "untouched"}}


def test_rollback_restores_the_file_byte_for_byte(tmp_path):
    """The rollback must reproduce the original bytes, not merely equivalent JSON.

    Writes go through a temp file plus os.replace. Writing in place with mode "w" truncates first,
    so a failure part-way through the dump could leave a truncated card_descriptions.json - and the
    real one is imported by api/main.py at startup. Comparing bytes is what makes that checkable.
    """
    opener = "Zarquon the moonbat surveyed this"
    batches = {
        0: {"rewrites": {"site-0": f"{opener} ridge above the plain."}},
        1: {"rewrites": {"site-1": f"{opener} bronze krater of note."}},
        2: {"rewrites": {"site-2": f"{opener} sheltered valley mouth."}},
    }
    for i in range(3, NUM_BATCHES):
        batches[i] = {"rewrites": {}}
    root = build_sandbox(tmp_path, batches=batches)
    target = root / "output" / "card_descriptions.json"
    before = target.read_bytes()

    res = run_merge(root)
    assert res.returncode == EXIT_REGRESSED, res.stdout + res.stderr
    assert target.read_bytes() == before, "the rollback did not reproduce the original bytes"
    # No half-written temp file is left lying around either.
    assert list((root / "output").glob("*.tmp")) == []


def _load_merge_module():
    """Import the real merge_rewrites.py as a module WITHOUT running it.

    Its `if __name__ == "__main__"` guard means importing only defines things, and the functions
    under test take their paths as arguments, so nothing in the real repository is touched.
    """
    spec = importlib.util.spec_from_file_location("merge_rewrites_under_test", REAL_MERGE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_atomic_write_cannot_truncate_the_target(tmp_path, monkeypatch):
    """Fault injection: a write that dies part-way must leave the target exactly as it was.

    This is the property the byte-for-byte rollback test cannot show on its own - it proves the
    rollback CONTENT, not that an interrupted write cannot half-destroy the file. Without the temp
    file plus os.replace, mode "w" would have truncated the target before the dump failed.
    """
    mod = _load_merge_module()
    target = tmp_path / "card_descriptions.json"
    mod.write_json_atomic(target, {"descriptions": {"a": "original text"}})
    good = target.read_bytes()
    assert not list(tmp_path.glob("*.tmp"))

    def boom(*args, **kwargs):
        raise OSError("simulated failure part-way through the dump")

    monkeypatch.setattr(mod.json, "dump", boom)
    with pytest.raises(mod.MergeInputError):
        mod.write_json_atomic(target, {"descriptions": {"a": "replacement text"}})

    assert target.read_bytes() == good, "a failed write changed or truncated the target"
    assert list(tmp_path.glob("*.tmp")) == [], "a failed write left its temp file behind"


# --- the guard must be able to fail -----------------------------------------------------------


def test_mutation_guard_is_load_bearing(tmp_path):
    """Remove the incomplete-batch guard and the corresponding test must break.

    Without this, `test_all_batches_missing_writes_nothing` could pass for the wrong reason - a
    guard nobody can break is not a guard. The mutation deletes the early return, so the script
    walks on and reports whatever it does next instead of EXIT_INCOMPLETE.
    """
    source = REAL_MERGE.read_text(encoding="utf-8")
    guard = "    if missing:\n"
    assert guard in source, "the incomplete-batch guard moved; update this mutation"
    # Disable the guard's CONDITION rather than deleting the block: a textual deletion is brittle
    # (the f-string inside carries its own parentheses) and a mutation that produces a syntax
    # error would make this test pass for the wrong reason - the script would exit 1 for a
    # parse failure, not because the guard was load-bearing.
    mutated = source.replace(guard, "    if False:  # MUTATED\n", 1)
    compile(mutated, "mutated_merge_rewrites", "exec")  # the mutation must be a live script

    root = build_sandbox(tmp_path / "mutated", batches={}, merge_src=None)
    (root / "scripts" / "merge_rewrites.py").write_text(mutated, encoding="utf-8")
    res = run_merge(root)
    # With the guard disabled the script walks on to the NEXT guard and reports "nothing to
    # merge" instead of "incomplete". That is the proof the incomplete-batch guard did the work.
    assert res.returncode == EXIT_NOTHING, (
        f"the mutation did not change behaviour (returncode {res.returncode}) - "
        "the incomplete-batch test proves nothing"
    )
    assert res.returncode != EXIT_INCOMPLETE


# --- and the happy path still works -----------------------------------------------------------


def test_complete_valid_merge_is_published(tmp_path):
    """The guards must not block a legitimate merge: exit 0, published, count preserved.

    Five of six sites are rewritten; `site-5` is deliberately left alone so the test can show that
    an untouched site keeps its original text (batches 5..9 are present but empty, which is not the
    same as the all-empty case that must fail).
    """
    batches = {
        i: {"rewrites": {f"site-{i}": f"Sentence number {i} about the place sits here."}}
        for i in range(5)
    }
    for i in range(5, NUM_BATCHES):
        batches[i] = {"rewrites": {}}
    root = build_sandbox(tmp_path, batches=batches)

    res = run_merge(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "OK: applied 5 rewrites" in res.stdout
    published = public_payload(root)["descriptions"]
    assert published["site-0"] == "Sentence number 0 about the place sits here."
    assert len(published) == len(CLEAN), "the merge must never add or drop a description"
    # The untouched site keeps its original text.
    assert published["site-5"] == CLEAN[5]


def test_sandbox_never_touches_the_real_repository(tmp_path):
    """The real public/data/card_descriptions.json is the API's startup input - prove it is safe."""
    real = REPO / "public" / "data" / "card_descriptions.json"
    before = real.read_bytes()
    root = build_sandbox(tmp_path, batches=valid_batches())
    run_merge(root)
    assert real.read_bytes() == before
