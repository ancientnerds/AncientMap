"""The mutation sweep of the web verifier's calibration repair is well formed.

`teaser/mutation_sweep.py` removes one guard per case and asks one test to notice
(`mechanical/mutation_sweep.py` runs it). Running the sweep is slow and belongs to a parent process on
a clean tree; what is cheap enough for every test run is the static half: every needle occurs exactly
once, every mutant compiles, every named test exists, every label is unique.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import mutation_sweep as S  # noqa: E402
from teaser import mutation_sweep as M  # noqa: E402


def test_every_needle_occurs_exactly_once_and_every_mutant_compiles() -> None:
    for case in M.CASES:
        mutant = S.mutate(S.read(case.path), case.old, case.new)
        assert S.compiles(mutant, case.path), case.label


def test_every_named_test_exists_in_its_file() -> None:
    for case in M.CASES:
        source = (REPO / case.testfile).read_text(encoding="utf-8")
        assert re.search(rf"^\s*def {re.escape(case.test)}\(", source, re.M), case.label


def test_labels_are_unique_and_every_mutant_changes_its_file() -> None:
    labels = [case.label for case in M.CASES]
    assert len(labels) == len(set(labels))
    assert all(case.old != case.new for case in M.CASES)
