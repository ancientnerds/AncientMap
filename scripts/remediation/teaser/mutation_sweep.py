"""Mutation sweep for the repair of the web verifier's calibration (teaser-2026-10-09, 2026-10-09).

The machinery is `mechanical/mutation_sweep.py`'s (a case counts as FIRED only when its needle occurs
exactly once, the mutant compiles, the named test passed on the unmutated file and is reported
FAILED against the mutant - anything else fails the sweep). The cases are the repair's: the claims
floor, the coverage measure, the disputed gold, the told-apart quote standings, the opaque cache map,
`check-answer`, the recorder's `--check` hook, `void`, and the seal over the code that judges.

Run it from a parent process on a clean committed tree, never from inside a subagent lane (a lane
killed between applying a mutation and restoring it leaves the mutant behind):

    ./.venv/Scripts/python.exe scripts/remediation/teaser/mutation_sweep.py            # all
    ./.venv/Scripts/python.exe scripts/remediation/teaser/mutation_sweep.py "void"     # by label

`git status` must be clean afterwards: the sweep restores every file and checks its sha256.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from mechanical.mutation_sweep import REPO, Case, guard, main  # noqa: E402

REMEDIATION = REPO / "scripts/remediation"
CAL = REMEDIATION / "teaser/calibrate.py"
RUN = REMEDIATION / "teaser/run.py"
HANDOFF = REMEDIATION / "opus_handoff.py"
QUOTE_CHECK = REMEDIATION / "quote_check.py"
STAGE = REMEDIATION / "image_roles/stage.py"

T_REPAIR = "tests/remediation/test_teaser_calibrate_repair.py"
T_RUN = "tests/remediation/test_teaser_shorts_run.py"
T_QUOTE = "tests/remediation/test_quote_check.py"
T_RELEASE = "tests/remediation/test_teaser_calibrate_release.py"


def g(label: str, path: Path, needle: str, test: str, testfile: str = T_REPAIR) -> Case:
    return guard(f"teaser repair: {label}", path, needle, test, testfile)


def c(label: str, path: Path, old: str, new: str, test: str, testfile: str = T_REPAIR) -> Case:
    return Case(f"teaser repair: {label}", path, old, new, test, testfile)


def rel(label: str, needle: str, test: str) -> Case:
    return guard(f"teaser release: {label}", CAL, needle, test, T_RELEASE)


CASES: list[Case] = [
    # ------------------------------------------------------------------ the claims floor
    g(
        "a verifier's answer needs the claims floor",
        CAL,
        "        if short is not None:",
        "test_a_short_answer_passes_no_floor_it_was_not_given",
    ),
    # ------------------------------------------------------------------ the coverage measure
    c(
        "a fresh claim covers a recorded one by its words",
        CAL,
        "if max(score) >= CLAIM_MATCH]",
        "if max(score) >= 2]",
        "test_the_five_claims_of_the_undavalli_card_are_covered_by_the_three_the_agent_listed",
    ),
    c(
        "the checker must agree on the covered claims",
        CAL,
        '        and _met(claim_cover.agreement, rule["claim_agreement_min"])\n',
        "",
        "test_claims_covered_with_the_other_support_fail_the_checker_alone",
    ),
    c(
        "the verifier must cover the recorded claims",
        CAL,
        '            and claim_cover.coverage >= rule_v["claim_coverage_min"]\n',
        "",
        "test_a_verifier_that_lists_too_few_claims_covers_too_little",
    ),
    c(
        "the verifier must agree on the covered claims",
        CAL,
        '            and claim_cover.agreement >= rule_v["claim_agreement_min"]\n',
        "",
        "test_covered_claims_with_another_verdict_fail_the_verifier",
    ),
    # ------------------------------------------------------------------ the disputed gold
    c(
        "a disputed contradiction leaves the denominator",
        CAL,
        "    counted = [k for k in contradicted if k not in disputed]\n",
        "    counted = list(contradicted)\n",
        "test_a_disputed_contradiction_the_verifier_missed_leaves_the_denominator",
    ),
    c(
        "the minimum scales with the cases that count",
        CAL,
        '    required = math.ceil(rule_c["caught_min"] * len(counted) / rule_c["cases"])\n',
        '    required = rule_c["caught_min"]\n',
        "test_a_disputed_contradiction_the_verifier_missed_leaves_the_denominator",
    ),
    # ------------------------------------------------------------------ not found by machine
    c(
        "a quote on the page up to typography is the machine's miss",
        CAL,
        "        return MACHINE_MISS\n",
        "        return FABRICATED\n",
        "test_a_quote_that_differs_from_the_page_in_typography_is_not_found_by_machine",
    ),
    c(
        "a fabricated quote is a false source",
        CAL,
        "    false_sources = [*standing[FABRICATED], *standing[REFUSED]]\n",
        "    false_sources = [*standing[REFUSED]]\n",
        "test_a_quote_the_page_never_says_is_fabricated",
    ),
    # ------------------------------------------------------------------ the cache map
    g(
        "a web batch gets its cache map",
        CAL,
        "        if cache is not None:",
        "test_each_web_batch_gets_a_map_from_its_opaque_labels_to_the_cached_pages",
    ),
    c(
        "the map names the pages of the question's site",
        CAL,
        'for lang, row in sorted(cache.pages.get(job["site_id"], {}).items())',
        "for lang, row in sorted({}.items())",
        "test_each_web_batch_gets_a_map_from_its_opaque_labels_to_the_cached_pages",
    ),
    # ------------------------------------------------------------------ check-answer
    c(
        "check-answer refuses a shape that does not parse",
        CAL,
        "        result.update(ok=False, problems=[str(exc)])",
        "        result.update(ok=True, problems=[str(exc)])",
        "test_an_answer_in_the_old_five_field_schema_is_refused_for_a_shorts_case",
    ),
    c(
        "the brief records through the check",
        CAL,
        '--text-file {scratch}/<label>.json --check "{check}"',
        "--text-file {scratch}/<label>.json",
        "test_the_brief_has_the_check_step_before_the_record_step",
    ),
    g(
        "the recorder runs the check it is given",
        HANDOFF,
        "    if args.check is not None:",
        "test_a_failing_check_stops_the_record",
    ),
    g(
        "the recorder refuses an answer whose check failed",
        HANDOFF,
        "    if done.returncode != 0:",
        "test_a_failing_check_stops_the_record",
    ),
    # ------------------------------------------------------------------ void
    g(
        "a void needs its reason",
        CAL,
        '    if not reason.strip():\n        raise CalibrationError("a void needs its reason',
        "test_a_question_without_an_answer_a_missing_reason_and_a_repeat_are_refused",
    ),
    g(
        "a void names a question of the role",
        CAL,
        "        if label not in batch_of:",
        "test_a_question_of_another_role_is_refused",
    ),
    g(
        "a void needs a recorded answer",
        CAL,
        "        if not source.is_file():",
        "test_a_question_without_an_answer_a_missing_reason_and_a_repeat_are_refused",
    ),
    g(
        "a void refuses an answer of another role",
        CAL,
        "        if named != role:",
        "test_an_answer_of_another_role_is_refused",
    ),
    g(
        "an answer is voided once",
        CAL,
        "        if target.exists():",
        "test_an_answer_is_voided_once",
    ),
    c(
        "a void checks the seal's integrity only",
        CAL,
        "    integrity(run_dir)\n    if not reason.strip():",
        "    sealed(run_dir)\n    if not reason.strip():",
        "test_a_void_serves_a_calibration_whose_modules_moved_after_the_seal",
    ),
    # ------------------------------------------------------------------ the seal
    c(
        "the seal hashes the quote check",
        CAL,
        '    "scripts/remediation/opus_audit/quotes.py",\n',
        "",
        "test_the_modules_hash_the_question_builder_the_judge_and_the_quote_check",
    ),
    # ------------------------------------------------------------------ the briefs
    c(
        "the verifier's brief carries the cache rule",
        RUN,
        "    + WR.VERIFIER_RULE\n",
        '    + ""\n',
        "test_a_verifier_is_told_where_the_wikipedia_text_is_and_that_a_403_is_no_finding",
        T_RUN,
    ),
    # ------------------------------------------------------------------ the agent's own quote check
    g(
        "the quote check says where the page differs",
        QUOTE_CHECK,
        "    if result.outcome == Q.NOT_FOUND:",
        "test_a_quote_the_page_does_not_hold_says_where_the_page_differs",
        T_QUOTE,
    ),
    # ------------------------------------------------------------------ the release of a held verdict
    rel(
        "a role without a verdict has nothing to stand on",
        "    if not path.is_file():\n"
        '        raise CalibrationError(f"role {role} has no verdict in {run_dir}: {path} is missing")',
        "test_a_missing_verdict_is_not_released",
    ),
    rel(
        "the role is registered as it was sealed",
        '    if RO.role_sha256(role) != entry["sha256"]:',
        "test_a_role_that_changed_after_the_seal_is_not_released",
    ),
    rel(
        "the verdict is the role's",
        '    if verdict["role"] != role:',
        "test_a_verdict_of_another_role_than_the_file_names_is_not_released",
    ),
    rel(
        "the verdict rests on the sealed thresholds",
        '    if verdict["thresholds_sha256"] != digest:',
        "test_a_verdict_that_does_not_rest_on_the_sealed_thresholds_is_not_released",
    ),
    rel(
        "it names who decided",
        "    if not decided_by.strip():",
        "test_a_release_names_who_decided_and_why",
    ),
    rel(
        "it names why",
        '    if not reason.strip():\n        raise CalibrationError("reason is empty',
        "test_a_release_names_who_decided_and_why",
    ),
    rel(
        "a pass is not released",
        '    if verdict["passed"]:\n'
        '        raise CalibrationError(f"role {role} passed: there is nothing to release")',
        "test_a_pass_is_not_released",
    ),
    rel(
        "a verdict with a tier move is not released",
        '    if verdict["tier_move"] is not None:\n'
        "        raise CalibrationError(\n"
        '            f"role {role} carries a tier move',
        "test_a_verdict_with_a_tier_move_is_moved_not_released",
    ),
    rel(
        "only a held verdict is released",
        '    if not verdict.get("held"):',
        "test_a_failed_verdict_that_is_not_held_is_not_released",
    ),
    rel(
        "a release is written once",
        "    if release_path.exists():",
        "test_a_release_is_written_once",
    ),
    rel(
        "a pass stands as passed",
        '    if verdict["passed"]:\n        return {**line, "standing": CC.PASSED}',
        "test_a_passed_verdict_stands_as_passed",
    ),
    rel(
        "a held verdict stands only with its release",
        '    if verdict["tier_move"] is not None or not verdict.get("held") or not release_path.is_file():',
        "test_a_held_verdict_without_its_release_does_not_stand",
    ),
    Case(
        "teaser release: a failed verdict stands with a release only when it is held",
        CAL,
        '    if verdict["tier_move"] is not None or not verdict.get("held") or not release_path.is_file():',
        '    if verdict["tier_move"] is not None or not release_path.is_file():',
        "test_a_release_beside_a_failed_verdict_that_is_not_held_does_not_stand",
        T_RELEASE,
    ),
    rel(
        "the release names the calibration and the role",
        '    if record["calibration_id"] != run_dir.name or record["role"] != role:',
        "test_a_release_naming_another_calibration_or_role_does_not_stand",
    ),
    rel(
        "a release rests on evidence",
        '    if not record["evidence"]:',
        "test_a_release_with_no_evidence_does_not_stand",
    ),
    rel(
        "the verdict is unchanged since the release",
        '    if record["verdict_sha256"] != CC.sha256_file(path):',
        "test_a_release_whose_binding_changed_is_refused_by_name",
    ),
    rel(
        "the thresholds and the role are unchanged since the release",
        '    if record["thresholds_sha256"] != digest or record["role_sha256"] != RO.role_sha256(role):',
        "test_a_release_whose_binding_changed_is_refused_by_name",
    ),
]


if __name__ == "__main__":
    # `mutation_sweep.py [label substring ...]` runs the cases whose label holds any of them.
    wanted = [x for x in CASES if not sys.argv[1:] or any(a in x.label for a in sys.argv[1:])]
    if not wanted:
        sys.exit(f"no case label contains any of {sys.argv[1:]}")
    sys.exit(main(wanted))
