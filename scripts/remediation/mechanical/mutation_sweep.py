"""Mutation sweep for the mechanical lanes: every guard must be able to fail.

Each case removes or inverts exactly one guard and asks the named test to go red. A case that stays
green means the guard is not actually covered by its test.

A case counts as **fired** only when every one of these holds:

* the needle occurs exactly once in its file, matched in the file's own line endings;
* the mutant compiles - a mutant that is a SyntaxError proves nothing about any test;
* the named test PASSED against the unmutated file, and was not skipped;
* the named test is reported FAILED, by name, against the mutant.

Anything else fails the sweep: a SKIPPED case (needle count != 1), an INVALID one (the mutant does
not compile), an UNPROVEN one (the named test does not pass, or is skipped, on the original), an
ERRORED one (pytest could not run the named test against the mutant) and, of course, a SURVIVED one.

Why the rules are this strict (measured 2026-09-22, recorded in AUDIT_LOG.md): the delivered sweep
counted a skipped case as fired, and counted any non-zero pytest exit as fired. Its `if False:`
replacement dropped the guard's indentation, so 17 of its 30 mutants were IndentationErrors that
failed *collection* - the named test never ran - and on a CRLF checkout 3 more needles matched
nothing. The printed result was still `cases: 30  fired: 30  survived: 0`, exit 0.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MECHANICAL = REPO / "scripts/remediation/mechanical"
PLAN = MECHANICAL / "plan.py"
APPLY = MECHANICAL / "apply.py"
LANE = MECHANICAL / "lane.py"
TESTFILE = "tests/remediation/test_mechanical.py"

#: The interpreter that runs the sweep runs the tests too: a hard-coded `.venv` path does not exist in
#: a git worktree, and a second interpreter could test different packages than the one reporting.
PY = sys.executable

FIRED = "fired"
SURVIVED = "SURVIVED"
SKIPPED = "SKIPPED"
INVALID = "INVALID"
UNPROVEN = "UNPROVEN"
ERRORED = "ERRORED"


@dataclass(frozen=True)
class Case:
    """One guard, the edit that removes it, and the test that has to notice."""

    label: str
    path: Path
    old: str
    new: str
    test: str
    testfile: str = TESTFILE


def falsify(needle: str) -> str:
    """The same `if` guard with its condition replaced by `False`, at the guard's own indentation.

    The indentation is the point: `if False:` at column 0 inside a function body is an
    IndentationError, and a mutant that does not compile fails every test in the file for a reason
    that has nothing to do with the guard.
    """
    first, sep, rest = needle.partition("\n")
    stripped = first.strip()
    if not (stripped.startswith("if ") and stripped.endswith(":")):
        raise ValueError(f"not an if-guard needle: {first!r}")
    indent = first[: len(first) - len(first.lstrip(" "))]
    return f"{indent}if False:{sep}{rest}"


def guard(label: str, path: Path, needle: str, test: str, testfile: str = TESTFILE) -> Case:
    """A case that turns the guard's `if` condition into `False`."""
    return Case(label, path, needle, falsify(needle), test, testfile)


CASES: list[Case] = [
    guard(
        "finding not applicable",
        PLAN,
        "    if not finding.applicable:",
        "test_a_review_finding_is_refused",
    ),
    guard(
        "curated source only",
        PLAN,
        "    if site.source_id != CURATED_SOURCE:",
        "test_a_row_of_another_source_is_refused",
    ),
    guard(
        "snapshot matches live",
        PLAN,
        "    if snapshot_country is not None and snapshot_country != site.country:",
        "test_a_snapshot_value_the_database_no_longer_holds_is_refused",
    ),
    guard(
        "finding not stale",
        PLAN,
        "    if finding.current_value != site.country:",
        "test_a_stale_finding_is_refused",
    ),
    guard(
        "canonical equals proposal",
        PLAN,
        "    if canonical != finding.proposed_value:",
        "test_a_canonical_form_that_disagrees_with_the_proposal_is_refused",
    ),
    guard(
        "ISO code unchanged",
        PLAN,
        "    if old_iso is None or new_iso is None or old_iso != new_iso:",
        "test_a_write_that_would_change_the_iso_code_is_refused",
    ),
    guard(
        "value is a frontend key",
        PLAN,
        "    if value not in codes or codes[value] != new_iso:",
        "test_a_frontend_map_that_carries_another_code_is_refused",
    ),
    guard(
        "point inside the polygon",
        PLAN,
        '    if not ok:\n        return refuse("geography-contradicts"',
        "test_a_point_in_another_country_is_refused",
    ),
    guard(
        "wikidata non-contradicting",
        PLAN,
        "    if witness_ok is False:",
        "test_an_external_contradiction_refuses",
    ),
    guard(
        "fixed point",
        PLAN,
        "    if not _is_canonical(value, dict(codes), normalize):",
        "test_a_value_the_census_would_flag_again_is_refused",
    ),
    guard(
        "the value is a change",
        PLAN,
        "    if value == site.country:",
        "test_a_reduction_that_changes_nothing_is_refused",
    ),
    Case(
        "preferred rank is decisive",
        PLAN,
        '    preferred = [c for c in claims if c.get("rank") == "preferred"]',
        "    preferred = []",
        "test_history_beside_a_preferred_country_is_not_a_contradiction",
    ),
    Case(
        "compound needs a state",
        PLAN,
        "            countries = [p for p in known if names_a_country(atlas, p)]",
        "            countries = known",
        "test_compound_reduces_to_the_state_not_the_territory",
    ),
    Case(
        "Natural Earth names the state",
        PLAN,
        "    return any(key == _fold(f.admin) or key in f.name_keys for f in atlas.features)",
        "    return True",
        "test_both_vocabularies_know_the_territory_as_chile",
    ),
    Case(
        "compound refuses two countries",
        PLAN,
        "        if len({_iso(p, normalize) for p in known}) == 1 and known:",
        '        return known[0], "compound-label"\n'
        "        if len({_iso(p, normalize) for p in known}) == 1 and known:",
        "test_two_candidate_countries_refuse",
    ),
    guard(
        "plan-side source check",
        APPLY,
        "    if source != CURATED_SOURCE:",
        "test_a_foreign_source_is_refused",
    ),
    guard(
        "plan-side old value",
        APPLY,
        "        if not r.old_value:",
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    guard(
        "plan-side new value",
        APPLY,
        "        if not r.new_value:",
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    guard(
        "plan-side is a change",
        APPLY,
        "        if r.new_value == r.old_value:",
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    guard(
        "plan-side column length",
        APPLY,
        "        if len(r.new_value) > lane.max_chars:",
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    guard(
        "plan-side evidence",
        APPLY,
        "        if not r.reason or not r.evidence:",
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    guard(
        "plan-side duplicates",
        APPLY,
        "        if r.site_id in seen:",
        "test_the_same_site_twice_is_refused",
    ),
    Case(
        "no empty transaction",
        APPLY,
        '    if not records:\n        raise PlanError("refusing to render a transaction with no rows")',
        "    if not records:\n        pass",
        "test_an_empty_plan_is_refused",
    ),
    guard(
        "rollback written first",
        APPLY,
        "    if not rollback_path.exists():",
        "test_emit_refuses_when_the_rollback_does_not_exist",
    ),
    guard(
        "statement must commit",
        APPLY,
        '    if not sep:\n        raise PlanError("the emitted statement has no COMMIT',
        "test_a_statement_without_a_commit_cannot_be_rehearsed",
    ),
    guard(
        "rollback rehearsal must commit",
        APPLY,
        '    if not sep:\n        raise PlanError("ROLLBACK.sql has no COMMIT',
        "test_a_rollback_without_a_commit_cannot_be_rehearsed",
    ),
    Case(
        "in-transaction scope guard",
        APPLY,
        'add(f"     WHERE u.id IS NULL OR u.source_id <> {_literal(source)};")',
        'add("     WHERE u.id IS NULL;")',
        "test_the_scope_guard_names_the_curated_source",
    ),
    Case(
        "journal reconciles the data",
        APPLY,
        "row(s) outside ",
        "row(s) next to ",
        "test_the_journal_is_reconciled_inside_the_transaction",
    ),
    Case(
        "the write uses the old value",
        APPLY,
        "            r.old_value, r.new_value,",
        "            r.new_value, r.new_value,",
        "test_the_conditional_write_uses_the_planned_old_value",
    ),
    Case(
        "the read-back names its run",
        APPLY,
        'VERIFY_SQL = f"""\\',
        'VERIFY_SQL = """\\',
        "test_the_verify_statement_names_the_run_it_reads_back",
    ),
    Case(
        "the reversal must exist",
        APPLY,
        '    if not path.exists():\n        raise PlanError(f"{path} does not exist - there is no '
        'reversal to rehearse")',
        "    if not path.exists():\n        pass",
        "test_the_rollback_rehearsal_refuses_without_a_reversal",
    ),
    # ------------------------------------------------------------------ the lane (2026-09-22)
    guard(
        "plan-side owned value",
        APPLY,
        "        if lane.allowed_new_values and owned not in lane.allowed_new_values:",
        "test_the_plan_side_mirror_refuses_a_value_the_lane_does_not_own",
    ),
    Case(
        "plan-side reversal owns its old value",
        APPLY,
        "        owned = r.old_value if rollback else r.new_value",
        "        owned = r.new_value",
        "test_a_reversal_that_undoes_a_value_the_lane_never_wrote_is_refused",
    ),
    guard(
        "plan-side premise required",
        APPLY,
        "        if lane.premise_sql is not None and r.premise is None:",
        "test_a_lane_with_a_premise_refuses_a_record_without_one",
    ),
    guard(
        "plan-side premise nobody checks",
        APPLY,
        "        if lane.premise_sql is None and r.premise is not None:",
        "test_a_lane_without_a_premise_refuses_one_it_would_not_check",
    ),
    guard(
        "rendered guard 4 (owned values)",
        APPLY,
        "    if lane.allowed_new_values:\n        owned = ",
        "test_the_fourth_guard_is_rendered_only_for_a_lane_that_owns_its_values",
    ),
    Case(
        "rendered guard 4 reads the old value on a reversal",
        APPLY,
        '        owned = "p.old_value" if rollback else "p.new_value"',
        '        owned = "p.new_value"',
        "test_the_uk_reversal_undoes_only_values_the_lane_owns",
    ),
    guard(
        "rendered guard 5 (premise)",
        APPLY,
        '    if premise:\n        add(\n            "    -- scope guard 5',
        "test_the_fifth_guard_conditions_the_write_on_its_premise",
    ),
    Case(
        "the writer journals the lane's test id",
        APPLY,
        'f"            {_literal(lane.test_id)}, {_literal(run_stamp)}, r.change_key, "',
        'f"            {_literal(TEST_ID)}, {_literal(run_stamp)}, r.change_key, "',
        "test_the_uk_statement_carries_its_own_journal_identity_and_none_of_t05s",
    ),
    Case(
        "the rendered width is the lane's",
        APPLY,
        'add(f"        OR length(p.new_value) > {lane.max_chars};")',
        'add("        OR length(p.new_value) > 100;")',
        "test_the_column_width_is_the_lane_s",
    ),
    Case(
        "the reversal has its own key",
        LANE,
        '        return f"{self.key_prefix}-rollback:{site_id}"',
        '        return f"{self.key_prefix}:{site_id}"',
        "test_the_uk_reversal_undoes_only_values_the_lane_owns",
    ),
    Case(
        "the rollback rehearsal reads each row's value",
        APPLY,
        " WHERE u.{column} IS NOT DISTINCT FROM p.written",
        " WHERE u.{column} IS NOT NULL",
        "test_the_rollback_rehearsal_reads_name_the_planned_rows",
    ),
    guard(
        "probe for guard 4",
        APPLY,
        "    if lane.allowed_new_values:\n        not_owned",
        "test_every_rendered_guard_has_its_probe",
    ),
    guard(
        "probe for guard 5",
        APPLY,
        "    if lane.premise_sql is not None:\n        moved",
        "test_every_rendered_guard_has_its_probe",
    ),
    *(
        guard(
            f"lane refuses {what}",
            LANE,
            needle,
            "test_a_lane_that_would_splice_something_unsafe_into_sql_is_refused",
        )
        for what, needle in (
            ("an unsafe column", "        if not _IDENTIFIER.match(self.column):"),
            (
                "an unsafe temp table",
                "        if not _IDENTIFIER.match(self.plan_table) or not "
                'self.plan_table.startswith("_"):',
            ),
            ("an unsafe label", "        if not _LABEL.match(self.label):"),
            ("an unsafe key prefix", "        if not _KEY_PREFIX.match(self.key_prefix):"),
            ("a non-positive width", "        if self.max_chars <= 0:"),
            (
                "an incomplete journal identity",
                "        if not self.run_stamp or not self.test_id or not self.confidence:",
            ),
            (
                "an unwritable owned value",
                "            if not value or len(value) > self.max_chars:",
            ),
        )
    ),
]


# ------------------------------------------------------------------------------ the mutation
class NeedleCount(ValueError):
    """The needle does not occur exactly once: the case cannot say which guard it removes."""

    def __init__(self, count: int) -> None:
        super().__init__(f"needle appears {count}x")
        self.count = count


def read(path: Path) -> str:
    """Read without newline translation, so a restored file is byte-identical."""
    with path.open(encoding="utf-8", newline="") as fh:
        return fh.read()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_ending(text: str) -> str:
    """The file's own line ending. A file that mixes two is refused rather than half-matched."""
    crlf = text.count("\r\n")
    if crlf and crlf != text.count("\n"):
        raise ValueError("the file mixes CRLF and LF line endings")
    return "\r\n" if crlf else "\n"


def mutate(text: str, old: str, new: str) -> str:
    """`text` with the one occurrence of `old` replaced by `new`, in the file's line endings.

    A checkout with `core.autocrlf=true` stores the same source with CRLF, where a needle spanning
    two lines would otherwise match nothing (measured: 3 of the delivered cases on this worktree).
    """
    eol = line_ending(text)
    needle, replacement = old.replace("\n", eol), new.replace("\n", eol)
    count = text.count(needle)
    if count != 1:
        raise NeedleCount(count)
    return text.replace(needle, replacement)


def compiles(source: str, path: Path) -> bool:
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError:
        return False
    return True


# ------------------------------------------------------------------------------ the test runs
_OUTCOME = re.compile(
    r"^\S+?\.py::(?P<node>.+?) (?P<outcome>PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\b", re.M
)


def outcomes(stdout: str) -> dict[str, list[str]]:
    """Per test *function* name, the outcomes pytest -v reported (one per parametrisation)."""
    got: dict[str, list[str]] = defaultdict(list)
    for match in _OUTCOME.finditer(stdout):
        name = match["node"].split("[", 1)[0].rsplit("::", 1)[-1]
        got[name].append(match["outcome"])
    return dict(got)


def run_tests(testfile: str, selector: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", testfile, "-v", "-p", "no:cacheprovider", "--timeout", "120"]
        + ["-k", selector],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout + proc.stderr


def proven(results: Sequence[str]) -> bool:
    """The named test ran and passed on the unmutated file - every parametrisation of it."""
    return bool(results) and all(r == "PASSED" for r in results)


def fired(returncode: int, results: Sequence[str]) -> str:
    """FIRED only when pytest reports the named test FAILED; any other red is not a fire."""
    if returncode == 1 and "FAILED" in results and "ERROR" not in results:
        return FIRED
    if returncode == 0 and results and all(r in ("PASSED", "SKIPPED") for r in results):
        return SURVIVED
    return ERRORED


def exit_code(results: Iterable[str]) -> int:
    """0 only when every case fired; a skip, a survivor, an invalid or unproven case fails."""
    return 0 if all(r == FIRED for r in results) else 1


def baseline(cases: Sequence[Case]) -> dict[tuple[str, str], list[str]]:
    """Every named test, run once against the unmutated files."""
    by_file: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        by_file[case.testfile].add(case.test)
    seen: dict[tuple[str, str], list[str]] = {}
    for testfile, names in sorted(by_file.items()):
        _, stdout = run_tests(testfile, " or ".join(sorted(names)))
        got = outcomes(stdout)
        for name in names:
            seen[(testfile, name)] = got.get(name, [])
    return seen


def main(cases: Sequence[Case] = CASES) -> int:
    paths = sorted({case.path for case in cases})
    originals = {p: read(p) for p in paths}
    hashes = {p: sha(p) for p in paths}
    rows: list[tuple[str, str, str, str]] = []
    try:
        base = baseline(cases)
        for case in cases:
            before = base[(case.testfile, case.test)]
            if not proven(before):
                rows.append(
                    (case.label, case.test, UNPROVEN, f"on the original: {before or 'not run'}")
                )
                continue
            text = originals[case.path]
            try:
                mutant = mutate(text, case.old, case.new)
            except NeedleCount as exc:
                rows.append((case.label, case.test, SKIPPED, str(exc)))
                continue
            if not compiles(mutant, case.path):
                rows.append((case.label, case.test, INVALID, "the mutant does not compile"))
                continue
            case.path.write_text(mutant, encoding="utf-8", newline="")
            try:
                returncode, stdout = run_tests(case.testfile, case.test)
            finally:
                case.path.write_text(originals[case.path], encoding="utf-8", newline="")
            after = outcomes(stdout).get(case.test, [])
            result = fired(returncode, after)
            rows.append((case.label, case.test, result, f"pytest exit {returncode}: {after}"))
    finally:
        for path in originals:
            assert sha(path) == hashes[path], f"{path} not restored"
    print(f"{'guard removed':<34} {'test asked to fail':<64} result")
    for label, test, result, detail in rows:
        print(f"{label:<34} {test:<64} {result} ({detail})")
    print()
    tally = {name: sum(1 for r in rows if r[2] == name) for name in (FIRED, SKIPPED, SURVIVED)}
    others = {name: sum(1 for r in rows if r[2] == name) for name in (INVALID, UNPROVEN, ERRORED)}
    print(
        f"cases: {len(rows)}  fired: {tally[FIRED]}  skipped: {tally[SKIPPED]}  "
        f"survived: {tally[SURVIVED]}  invalid: {others[INVALID]}  unproven: {others[UNPROVEN]}  "
        f"errored: {others[ERRORED]}"
    )
    failing = [f"{label} ({result})" for label, _, result, _ in rows if result != FIRED]
    if failing:
        print("NOT FIRED: " + ", ".join(failing))
    return exit_code(r[2] for r in rows)


if __name__ == "__main__":
    sys.exit(main())
