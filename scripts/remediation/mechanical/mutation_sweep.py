"""Mutation sweep for the mechanical-country lane: every guard must be able to fail.

Each case removes or inverts exactly one guard in `plan.py`/`apply.py` and asks the named test
to go red. A case that stays green means the guard is not actually covered by its test.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path  # noqa: I001

REPO = Path(__file__).resolve().parents[3]
PY = str(REPO / ".venv/Scripts/python.exe")
PLAN = REPO / "scripts/remediation/mechanical/plan.py"
APPLY = REPO / "scripts/remediation/mechanical/apply.py"
TESTFILE = "tests/remediation/test_mechanical.py"

FALSE = "if False:"
CASES: list[tuple[str, Path, str, str, str]] = [
    (
        "finding not applicable",
        PLAN,
        "    if not finding.applicable:",
        FALSE,
        "test_a_review_finding_is_refused",
    ),
    (
        "curated source only",
        PLAN,
        "    if site.source_id != CURATED_SOURCE:",
        FALSE,
        "test_a_row_of_another_source_is_refused",
    ),
    (
        "snapshot matches live",
        PLAN,
        "    if snapshot_country is not None and snapshot_country != site.country:",
        FALSE,
        "test_a_snapshot_value_the_database_no_longer_holds_is_refused",
    ),
    (
        "finding not stale",
        PLAN,
        "    if finding.current_value != site.country:",
        FALSE,
        "test_a_stale_finding_is_refused",
    ),
    (
        "canonical equals proposal",
        PLAN,
        "    if canonical != finding.proposed_value:",
        FALSE,
        "test_a_canonical_form_that_disagrees_with_the_proposal_is_refused",
    ),
    (
        "ISO code unchanged",
        PLAN,
        "    if old_iso is None or new_iso is None or old_iso != new_iso:",
        FALSE,
        "test_a_write_that_would_change_the_iso_code_is_refused",
    ),
    (
        "value is a frontend key",
        PLAN,
        "    if value not in codes or codes[value] != new_iso:",
        FALSE,
        "test_a_frontend_map_that_carries_another_code_is_refused",
    ),
    (
        "point inside the polygon",
        PLAN,
        '    if not ok:\n        return refuse("geography-contradicts"',
        '    if False:\n        return refuse("geography-contradicts"',
        "test_a_point_in_another_country_is_refused",
    ),
    (
        "wikidata non-contradicting",
        PLAN,
        "    if witness_ok is False:",
        FALSE,
        "test_an_external_contradiction_refuses",
    ),
    (
        "fixed point",
        PLAN,
        "    if not _is_canonical(value, dict(codes), normalize):",
        FALSE,
        "test_a_value_the_census_would_flag_again_is_refused",
    ),
    (
        "the value is a change",
        PLAN,
        "    if value == site.country:",
        FALSE,
        "test_a_reduction_that_changes_nothing_is_refused",
    ),
    (
        "preferred rank is decisive",
        PLAN,
        '    preferred = [c for c in claims if c.get("rank") == "preferred"]',
        "    preferred = []",
        "test_history_beside_a_preferred_country_is_not_a_contradiction",
    ),
    (
        "compound needs a state",
        PLAN,
        "            countries = [p for p in known if names_a_country(atlas, p)]",
        "            countries = known",
        "test_compound_reduces_to_the_state_not_the_territory",
    ),
    (
        "Natural Earth names the state",
        PLAN,
        "    return any(key == _fold(f.admin) or key in f.name_keys for f in atlas.features)",
        "    return True",
        "test_both_vocabularies_know_the_territory_as_chile",
    ),
    (
        "compound refuses two countries",
        PLAN,
        "        if len({_iso(p, normalize) for p in known}) == 1 and known:",
        '        return known[0], "compound-label"\n        if len({_iso(p, normalize) for p in known}) == 1 and known:',
        "test_two_candidate_countries_refuse",
    ),
    (
        "plan-side source check",
        APPLY,
        "    if source != CURATED_SOURCE:",
        FALSE,
        "test_a_foreign_source_is_refused",
    ),
    (
        "plan-side old value",
        APPLY,
        "        if not r.old_value:",
        FALSE,
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    (
        "plan-side new value",
        APPLY,
        "        if not r.new_value:",
        FALSE,
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    (
        "plan-side is a change",
        APPLY,
        "        if r.new_value == r.old_value:",
        FALSE,
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    (
        "plan-side column length",
        APPLY,
        "        if len(r.new_value) > COUNTRY_COLUMN_CHARS:",
        FALSE,
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    (
        "plan-side evidence",
        APPLY,
        "        if not r.reason or not r.evidence:",
        FALSE,
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    (
        "plan-side duplicates",
        APPLY,
        "        if r.site_id in seen:",
        FALSE,
        "test_the_same_site_twice_is_refused",
    ),
    (
        "no empty transaction",
        APPLY,
        '    if not records:\n        raise PlanError("refusing to render a transaction with no rows")',
        "    if not records:\n        pass",
        "test_an_empty_plan_is_refused",
    ),
    (
        "rollback written first",
        APPLY,
        "    if not rollback_path.exists():",
        FALSE,
        "test_emit_refuses_when_the_rollback_does_not_exist",
    ),
    (
        "statement must commit",
        APPLY,
        "    if not sep:",
        FALSE,
        "test_a_statement_without_a_commit_cannot_be_rehearsed",
    ),
    (
        "in-transaction scope guard",
        APPLY,
        'add(f"     WHERE u.id IS NULL OR u.source_id <> {_literal(source)};")',
        'add("     WHERE u.id IS NULL;")',
        "test_the_scope_guard_names_the_curated_source",
    ),
    (
        "journal reconciles the data",
        APPLY,
        "row(s) outside ",
        "row(s) next to ",
        "test_the_journal_is_reconciled_inside_the_transaction",
    ),
    (
        "the write uses the old value",
        APPLY,
        "            r.old_value, r.new_value,",
        "            r.new_value, r.new_value,",
        "test_the_conditional_write_uses_the_planned_old_value",
    ),
    (
        "the read-back names its run",
        APPLY,
        'VERIFY_SQL = f"""\\',
        'VERIFY_SQL = """\\',
        "test_the_verify_statement_names_the_run_it_reads_back",
    ),
    (
        "the reversal must exist",
        APPLY,
        '    if not path.exists():\n        raise PlanError(f"{path} does not exist - there is no '
        'reversal to rehearse")',
        "    if not path.exists():\n        pass",
        "test_the_rollback_rehearsal_refuses_without_a_reversal",
    ),
]


def read(path: Path) -> str:
    """Read without newline translation, so a restored file is byte-identical."""
    with path.open(encoding="utf-8", newline="") as fh:
        return fh.read()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(selector: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", TESTFILE, "-q", "-x", "--timeout", "120", "-k", selector],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    failed = re.findall(r"FAILED [^\s:]+::(\S+)", proc.stdout)
    return proc.returncode != 0, (failed[0] if failed else "")


def main() -> int:
    originals = {p: read(p) for p in (PLAN, APPLY)}
    hashes = {p: sha(p) for p in (PLAN, APPLY)}
    rows: list[tuple[str, str, str]] = []
    survived: list[str] = []
    try:
        for label, path, old, new, selector in CASES:
            text = originals[path]
            occurrences = text.count(old)
            if occurrences != 1:
                rows.append((label, f"SKIPPED needle appears {occurrences}x", selector))
                continue
            path.write_text(text.replace(old, new), encoding="utf-8", newline="")
            try:
                red, first_failure = run(selector)
            finally:
                path.write_text(originals[path], encoding="utf-8", newline="")
            if red:
                rows.append((label, f"fired: {first_failure}", selector))
            else:
                rows.append((label, "SURVIVED (test stayed green)", selector))
                survived.append(label)
    finally:
        for path in originals:
            assert sha(path) == hashes[path], f"{path} not restored"
    print(f"{'guard removed':<32} {'test asked to fail':<52} result")
    for label, result, selector in rows:
        print(f"{label:<32} {selector:<52} {result}")
    print()
    print(f"cases: {len(rows)}  fired: {len(rows) - len(survived)}  survived: {len(survived)}")
    if survived:
        print("SURVIVED: " + ", ".join(survived))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
