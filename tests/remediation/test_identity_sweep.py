"""The mutation sweep of the duplicate merge and the parent lanes is well formed.

`identity/mutation_sweep_merge.py` removes one guard per case and asks one test to notice
(`mechanical/mutation_sweep.py` runs it). Running the sweep is slow and belongs to a parent process on
a clean tree; what is cheap enough for every test run is the static half, as for the mechanical
sweep: every needle occurs exactly once, every mutant compiles, every named test exists, every label
is unique.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from identity import mutation_sweep_merge as M  # noqa: E402
from mechanical import mutation_sweep as S  # noqa: E402


class TestTheRealCases:
    def test_every_needle_occurs_exactly_once_and_every_mutant_compiles(self) -> None:
        for case in M.CASES:
            mutant = S.mutate(S.read(case.path), case.old, case.new)
            assert S.compiles(mutant, case.path), case.label

    def test_every_named_test_exists_in_its_file(self) -> None:
        for case in M.CASES:
            source = (REPO / case.testfile).read_text(encoding="utf-8")
            assert re.search(rf"^\s*def {re.escape(case.test)}\(", source, re.M), case.label

    def test_labels_are_unique(self) -> None:
        labels = [case.label for case in M.CASES]
        assert len(labels) == len(set(labels))

    def test_a_mutant_changes_its_file(self) -> None:
        for case in M.CASES:
            assert case.old != case.new, case.label

    def test_an_if_guard_is_found_by_its_line_and_made_false_at_its_indentation(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "m.py"
        path.write_text(
            "def f(x):\n    if x:\n        return 1\n    if x:\n        return 2\n",
            encoding="utf-8",
        )
        second = M.at("second", path, "    if x:", "test_x", "t.py", nth=1)
        assert (
            second.old == "    if x:\n        return 2"
            and second.new == "    if False:\n        return 2"
        )
        first = M.at("first", path, "    if x:", "test_x", "t.py", nth=0)
        assert first.old == "    if x:\n        return 1"
