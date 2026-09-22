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
UK = MECHANICAL / "uk_parts.py"
PERIOD = MECHANICAL / "period_name.py"
SHAPE = MECHANICAL / "site_type_shape.py"
TEXT = REPO / "pipeline/utils/text.py"
TESTFILE = "tests/remediation/test_mechanical.py"
UK_TESTS = "tests/remediation/test_mechanical_uk.py"
PERIOD_TESTS = "tests/remediation/test_mechanical_period_name.py"
SHAPE_TESTS = "tests/remediation/test_mechanical_site_type.py"

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
    # ------------------------------------------------------------- the UK lane (2026-09-22)
    *(
        guard(f"uk: {label}", UK, needle, test, UK_TESTS)
        for label, needle, test in (
            (
                "curated source only",
                "    if site.source_id != CURATED_SOURCE:",
                "test_a_row_of_another_source_is_refused",
            ),
            (
                "Ireland and United Kingdom rows only",
                "    if stored not in IN_SCOPE:",
                "test_a_region_that_is_already_spelled_out_is_never_touched",
            ),
            (
                "a point to locate",
                "    if site.lat is None or site.lon is None:",
                "test_a_row_without_a_point_is_refused",
            ),
            (
                "a decided unit",
                "    if where.unit is None:",
                "test_a_point_at_sea_is_undecided",
            ),
            (
                "the Republic's side of the border",
                "    if unit == IRELAND:",
                "test_a_united_kingdom_row_in_the_republic_is_a_contradiction",
            ),
            (
                "an Ireland row in the Republic is consistent",
                "        if stored == IRELAND:\n            return verdict(",
                "test_an_ireland_row_in_the_republic_is_consistent_and_not_written",
            ),
            (
                "one of the four UK units",
                "    if unit not in UK_UNITS:",
                "test_a_crown_dependency_is_not_a_uk_part",
            ),
            (
                "not at the border",
                "        if to_ireland <= TOLERANCE_M:",
                "test_an_ireland_row_300_m_from_the_border_is_ambiguous",
            ),
            (
                "GB in both vocabularies",
                '    if codes.get(new) != "GB" or new_iso != "GB":',
                "test_without_the_vocabulary_change_every_northern_irish_row_is_refused",
            ),
            (
                "the expected ISO transition",
                "    if (old_iso, new_iso) != EXPECTED_ISO[str(stored)]:",
                "test_an_unexpected_iso_transition_is_refused",
            ),
            (
                "fixed point",
                "    if not _is_canonical(new, dict(codes), normalize):",
                "test_a_value_the_census_would_flag_again_is_refused",
            ),
            (
                "exactly one entity",
                "    if len(candidate.qids) != 1:",
                "test_a_site_needs_exactly_one_entity",
            ),
            (
                "the entity was collected",
                "    if entity is None:",
                "test_an_entity_missing_from_the_cache_is_refused",
            ),
            (
                "the entity has a point",
                "    if point is None:",
                "test_an_entity_without_a_point_is_refused",
            ),
            (
                "the entity point is in the same unit",
                "    if wd_where.unit != unit:",
                "test_an_entity_point_in_another_unit_is_refused",
            ),
            (
                "P17 does not contradict",
                "    if p17_ok is False:",
                "test_a_preferred_p17_of_ireland_contradicts",
            ),
            (
                "P131* reaches no other unit",
                "    if others:",
                "test_a_p131_chain_to_england_contradicts_a_northern_irish_point",
            ),
            (
                "categories name no other unit",
                "    if named - {unit}:",
                "test_a_category_naming_the_republic_contradicts",
            ),
            (
                "a category can witness",
                "    if states_neither and unit in named:",
                "test_a_category_counts_only_when_it_names_the_unit",
            ),
            (
                "an ISO change needs a witness",
                "    if iso_changes and not witnessed:",
                "test_an_ireland_row_without_a_positive_witness_is_refused",
            ),
            (
                "unique unit names",
                "        if not units or len(names) != len(set(names)):",
                "test_duplicate_unit_names_are_refused",
            ),
            (
                "one covering unit decides",
                "        if len(covering) == 1:",
                "test_an_ireland_row_in_northern_ireland_is_written_as_northern_ireland",
            ),
            (
                "one unit within tolerance decides",
                "        if len(near) == 1:",
                "test_an_offshore_point_takes_the_only_unit_within_tolerance",
            ),
        )
    ),
    *(
        Case(f"uk: {label}", UK, old, new, test, UK_TESTS)
        for label, old, new, test in (
            (
                "a category only when the entity states neither P17 nor P131",
                "    if states_neither and unit in named:",
                "    if unit in named:",
                "test_a_category_is_no_witness_for_an_entity_that_states_p131",
            ),
            (
                "a category must name the unit",
                '        if title.endswith(f" in {suffix}")',
                "        if True",
                "test_a_category_counts_only_when_it_names_the_unit",
            ),
            (
                "the tolerance is T02's 1000 m",
                "if (metres := self.distance_m(u.name, lat, lon)) <= TOLERANCE_M",
                "if (metres := self.distance_m(u.name, lat, lon)) <= 10 * TOLERANCE_M",
                "test_open_water_5_km_out_is_undecided",
            ),
            (
                "a phase-3 value is flagged as superseded",
                '    phase3 = last is not None and last.run_stamp.startswith("phase3:")',
                "    phase3 = False",
                "test_a_phase3_write_is_superseded_and_named",
            ),
            (
                "a write carries its premise",
                "            premise=candidate.premise if ok else None,",
                "            premise=None,",
                "test_an_ireland_row_in_northern_ireland_is_written_as_northern_ireland",
            ),
            (
                "an offshore write is named as such",
                '        rule="geo-unit" if where.inside else "geo-unit-within-tolerance",',
                '        rule="geo-unit",',
                "test_an_offshore_row_is_written_by_the_unit_within_tolerance",
            ),
            (
                "the unit is GEOUNIT, not NAME",
                "        units.append(Unit(_text(row.GEOUNIT), _text(row.SOVEREIGNT), geom))",
                "        units.append(Unit(_text(row.NAME), _text(row.SOVEREIGNT), geom))",
                "test_the_unit_is_the_geounit_and_not_the_short_name",
            ),
        )
    ),
    # ------------------------------------------------ the planners' shared helpers (plan.py)
    guard(
        "journal chain unbroken",
        PLAN,
        "        if after.old_value != before.new_value:",
        "test_a_broken_journal_chain_is_refused",
        UK_TESTS,
    ),
    guard(
        "journal agrees with the live value",
        PLAN,
        "    if links and links[-1].new_value != live:",
        "test_a_journal_that_disagrees_with_the_row_is_refused",
        UK_TESTS,
    ),
    guard(
        "no identifier is interpolated unchecked",
        PLAN,
        "        if not UUID_RE.match(sid):",
        "test_a_non_uuid_is_never_interpolated",
        UK_TESTS,
    ),
    # ----------------------------------------------------------- the period lane (2026-09-22)
    *(
        guard(f"period: {label}", PERIOD, needle, test, PERIOD_TESTS)
        for label, needle, test in (
            (
                "curated source only",
                "    if row.source_id != CURATED_SOURCE:",
                "test_a_row_of_another_source_is_refused",
            ),
            (
                "no year, no bucket",
                "    if row.period_start is None:",
                "test_a_label_without_a_year_is_refused",
            ),
            (
                "no year and no label is consistent",
                "        if row.period_name is None:\n            return verdict(False, CONSISTENT",
                "test_no_year_and_no_label_is_consistent",
            ),
            (
                "the two implementations agree",
                "    if bucket != shown:",
                "test_two_implementations_that_disagree_refuse",
            ),
            (
                "a label that is the bucket is left alone",
                "    if bucket == row.period_name:",
                "test_a_label_that_is_already_the_bucket_is_consistent",
            ),
            (
                "a label to condition the write on",
                "    if not row.period_name:",
                "test_a_year_without_a_label_is_refused",
            ),
            (
                "both journals end at the live values",
                "        if broken is not None:\n            reason, note = broken",
                "test_a_period_start_written_around_the_journal_is_refused",
            ),
            (
                "the frontend function exists",
                "    if len(body) != 2:",
                "test_a_source_without_the_function_is_refused",
            ),
            (
                "the frontend comparisons were read",
                "    if not steps or last is None:",
                "test_a_function_without_comparisons_is_refused",
            ),
        )
    ),
    *(
        Case(f"period: {label}", PERIOD, old, new, test, PERIOD_TESTS)
        for label, old, new, test in (
            (
                "the period_name journal is checked too",
                '        ("period_name", row.name_journal, row.period_name),\n',
                "",
                "test_a_period_name_written_around_the_journal_is_refused",
            ),
            (
                "a label after a phase-3 year is flagged",
                '    phase3 = last_start is not None and last_start.run_stamp.startswith("phase3:")',
                "    phase3 = False",
                "test_a_label_left_behind_is_written_as_the_bucket",
            ),
            (
                "a write carries its year",
                "            premise=row.premise if ok else None,",
                "            premise=None,",
                "test_a_label_left_behind_is_written_as_the_bucket",
            ),
        )
    ),
    Case(
        "period: the SQL bucket compares upper bounds strictly",
        LANE,
        'f"WHEN {column} < {hi} THEN {sql_literal(label)}"',
        'f"WHEN {column} <= {hi} THEN {sql_literal(label)}"',
        "test_the_sql_bucket_is_the_frontend_bucket",
        PERIOD_TESTS,
    ),
    # ------------------------------------------------------- the site_type lane (2026-09-22)
    *(
        guard(f"site_type: {label}", SHAPE, needle, test, SHAPE_TESTS)
        for label, needle, test in (
            (
                "curated source only",
                "    if row.source_id != CURATED_SOURCE:",
                "test_a_row_of_another_source_is_refused",
            ),
            (
                "a type to repair",
                "    if row.site_type is None:",
                "test_a_row_without_a_type_is_refused",
            ),
            (
                "only a not-a-type shape is repaired",
                "    if shape is None:",
                "test_a_real_word_outside_the_list_goes_to_review",
            ),
            (
                "the journal ends at the live value",
                "    if broken is not None:\n        return verdict(False, *broken)",
                "test_a_journal_that_disagrees_with_the_row_is_refused",
            ),
            (
                "a written value to restore",
                "    if last is None:",
                "test_a_value_without_a_journal_row_is_refused",
            ),
            (
                "only phase 3's writes",
                '    if not last.run_stamp.startswith("phase3:"):',
                "test_a_value_written_by_another_lane_is_refused",
            ),
            (
                "the restore is canonical",
                "    if restore not in CANONICAL_TYPES:",
                "test_a_non_canonical_restore_is_refused",
            ),
            (
                "the restore survives the boot normaliser",
                "    if normalize_site_type(restore) != restore:",
                "test_a_restore_the_boot_normaliser_would_rewrite_is_refused",
            ),
            (
                "the snapshot knows the site",
                "    if row.site_id not in snapshot:",
                "test_a_site_missing_from_the_snapshot_is_refused",
            ),
            (
                "the snapshot confirms the journal",
                "    if snapshot[row.site_id] != first.old_value:",
                "test_a_snapshot_that_disagrees_with_the_journal_is_refused",
            ),
            (
                "a marker is not a type",
                "    if MARKER.match(value):",
                "test_only_a_marker_or_a_refusal_is_not_a_type",
            ),
            (
                "a refusal is not a type",
                "    if NOT_A_TYPE_PHRASE in value.casefold():",
                "test_only_a_marker_or_a_refusal_is_not_a_type",
            ),
        )
    ),
    Case(
        "site_type: the marker is lowercase snake_case only",
        LANE,
        'NOT_A_TYPE_MARKER = r"^[a-z0-9]+(_[a-z0-9]+)+$"',
        'NOT_A_TYPE_MARKER = r"^[A-Za-z0-9]+(_[a-z0-9]+)+$"',
        "test_only_a_marker_or_a_refusal_is_not_a_type",
        SHAPE_TESTS,
    ),
    Case(
        "site_type: a review item names the write it reviews",
        SHAPE,
        '"add it to the vocabulary or map it to a canonical type - a vocabulary decision",\n'
        "            written,",
        '"add it to the vocabulary or map it to a canonical type - a vocabulary decision",',
        "test_a_real_word_outside_the_list_goes_to_review",
        SHAPE_TESTS,
    ),
    Case(
        "categorize_period: the first bucket is open below",
        TEXT,
        "        if year < hi:",
        "        if _lo <= year < hi:",
        "test_a_year_below_the_table_floor_is_the_deep_past",
        "tests/pipeline/test_categorize_period.py",
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
