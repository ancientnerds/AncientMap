"""Does the mutation sweep refuse to call a case "fired" when nothing was proven?

The sweep is the evidence that every guard of the mechanical lanes has a test that notices its
removal. Its own verdict is therefore a guard too, and these tests pin each rule that decides it:
a needle that is not unique is a failure and not a fire, a mutant that does not compile proves
nothing, a non-zero pytest exit without the named test failing is not a fire, and a test that does
not pass on the original file cannot prove anything about the mutant.

The last class runs every real case statically (needle unique, mutant compiles, test exists), so a
refactor that makes a needle ambiguous fails in the normal test run - the sweep itself is not part
of any gate.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from mechanical import mutation_sweep as S  # noqa: E402

VERBOSE_FAILED = (
    "tests/remediation/test_mechanical.py::TestX::test_guard FAILED [ 50%]\n"
    "tests/remediation/test_mechanical.py::TestX::test_other PASSED [100%]\n"
)
COLLECTION_ERROR = (
    "ERROR collecting tests/remediation/test_mechanical.py\n"
    "E   IndentationError: unindent does not match any outer indentation level\n"
)


class TestTheMutation:
    def test_a_needle_that_occurs_twice_is_not_a_mutation(self) -> None:
        """The delivered 'statement must commit' needle occurred twice and was reported SKIPPED."""
        with pytest.raises(S.NeedleCount) as info:
            S.mutate("    if not sep:\n    if not sep:\n", "    if not sep:", "    if False:")
        assert info.value.count == 2

    def test_a_needle_that_occurs_nowhere_is_not_a_mutation(self) -> None:
        with pytest.raises(S.NeedleCount) as info:
            S.mutate("x = 1\n", "y = 2", "y = 3")
        assert info.value.count == 0

    def test_a_two_line_needle_matches_a_crlf_file(self) -> None:
        """`core.autocrlf=true` checks the same source out with CRLF."""
        text = "def f(x):\r\n    if not x:\r\n        raise E()\r\n    return x\r\n"
        mutant = S.mutate(
            text, "    if not x:\n        raise E()", "    if False:\n        raise E()"
        )
        assert mutant == "def f(x):\r\n    if False:\r\n        raise E()\r\n    return x\r\n"

    def test_mixed_line_endings_are_refused(self) -> None:
        with pytest.raises(ValueError, match="mixes"):
            S.line_ending("a\r\nb\n")

    def test_falsify_keeps_the_guard_s_indentation(self) -> None:
        """`if False:` at column 0 inside a function is an IndentationError, not a mutation."""
        source = "def f(x):\n    if not x:\n        return 0\n    return x\n"
        assert S.falsify("    if not x:") == "    if False:"
        assert S.compiles(S.mutate(source, "    if not x:", S.falsify("    if not x:")), Path("f"))
        dedented = S.mutate(source, "    if not x:", "if False:")
        assert not S.compiles(dedented, Path("f"))

    def test_falsify_refuses_what_is_not_an_if_guard(self) -> None:
        with pytest.raises(ValueError, match="not an if-guard"):
            S.falsify("    return x")


class TestTheVerdict:
    def test_a_named_failure_is_a_fire(self) -> None:
        assert S.fired(1, S.outcomes(VERBOSE_FAILED)["test_guard"]) == S.FIRED

    def test_a_collection_error_is_not_a_fire(self) -> None:
        """pytest exits 2 when a mutant breaks the import: the named test never ran."""
        assert S.fired(2, S.outcomes(COLLECTION_ERROR).get("test_guard", [])) == S.ERRORED

    def test_a_red_run_without_the_named_failure_is_not_a_fire(self) -> None:
        assert S.fired(1, S.outcomes(VERBOSE_FAILED)["test_other"]) == S.ERRORED

    def test_a_green_run_is_a_survivor(self) -> None:
        assert S.fired(0, ["PASSED"]) == S.SURVIVED

    def test_a_skipped_named_test_is_a_survivor_not_a_fire(self) -> None:
        assert S.fired(0, ["SKIPPED"]) == S.SURVIVED

    def test_a_skipped_or_failing_baseline_proves_nothing(self) -> None:
        assert S.proven(["PASSED", "PASSED"])
        assert not S.proven([])
        assert not S.proven(["SKIPPED"])
        assert not S.proven(["PASSED", "FAILED"])

    @pytest.mark.parametrize("bad", [S.SKIPPED, S.SURVIVED, S.INVALID, S.UNPROVEN, S.ERRORED])
    def test_every_result_other_than_a_fire_fails_the_sweep(self, bad: str) -> None:
        """The delivered sweep exited 0 with a SKIPPED case in its table."""
        assert S.exit_code([S.FIRED, bad, S.FIRED]) == 1
        assert S.exit_code([S.FIRED, S.FIRED]) == 0

    def test_parametrised_ids_with_spaces_are_read_by_function_name(self) -> None:
        stdout = (
            "tests/remediation/test_mechanical.py::TestR::test_mirror[change4-the column holds "
            "100] FAILED [ 90%]\n"
            "tests/remediation/test_mechanical.py::TestR::test_mirror[change5-not auditable] "
            "PASSED [100%]\n"
        )
        assert S.outcomes(stdout) == {"test_mirror": ["FAILED", "PASSED"]}


class TestTheRealCases:
    """Static checks of every case the sweep would run, cheap enough for every test run."""

    def test_every_needle_occurs_exactly_once_and_every_mutant_compiles(self) -> None:
        for case in S.CASES:
            mutant = S.mutate(S.read(case.path), case.old, case.new)
            assert S.compiles(mutant, case.path), case.label
            ast.parse(mutant)

    def test_every_named_test_exists_in_its_file(self) -> None:
        for case in S.CASES:
            source = (REPO / case.testfile).read_text(encoding="utf-8")
            assert re.search(rf"^\s*def {re.escape(case.test)}\(", source, re.M), case.label

    def test_labels_are_unique(self) -> None:
        labels = [case.label for case in S.CASES]
        assert len(labels) == len(set(labels))
