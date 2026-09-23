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
PROD_WRITE = REPO / "scripts/remediation/prod_write.py"
JOURNAL_CHAIN = REPO / "scripts/remediation/journal_chain.py"
CARD_STATS = MECHANICAL / "card_stats.py"
SCOPE = MECHANICAL / "scope.py"
REVERSAL = MECHANICAL / "reversal.py"
GENERATOR = REPO / "api/cardgame/generator.py"
TESTFILE = "tests/remediation/test_mechanical.py"
UK_TESTS = "tests/remediation/test_mechanical_uk.py"
PERIOD_TESTS = "tests/remediation/test_mechanical_period_name.py"
SHAPE_TESTS = "tests/remediation/test_mechanical_site_type.py"
PROD_TESTS = "tests/remediation/test_prod_write.py"
CHAIN_TESTS = "tests/remediation/test_journal_chain.py"
LOADER_TESTS = "tests/remediation/test_mechanical_loaders.py"
CELL_TESTS = "tests/remediation/test_mechanical_cells.py"
CARD_TESTS = "tests/remediation/test_mechanical_card_stats.py"
SCOPE_TESTS = "tests/remediation/test_mechanical_scope.py"
REVERSAL_TESTS = "tests/remediation/test_mechanical_reversal.py"
GENERATOR_TESTS = "tests/api/test_cardgame_generator_stats.py"

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
        "    if not r.old_value:",
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    guard(
        "plan-side new value",
        APPLY,
        "    if not r.new_value:",
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    guard(
        "plan-side is a change",
        APPLY,
        "    if r.new_value == r.old_value:",
        "test_the_plan_side_mirror_refuses_a_corrupt_record",
    ),
    guard(
        "plan-side column length",
        APPLY,
        "    if len(r.new_value) > lane.max_chars:",
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
        "        if cell in seen:",
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
        "    if lane.allowed_new_values and owned not in lane.allowed_new_values:",
        "test_the_plan_side_mirror_refuses_a_value_the_lane_does_not_own",
    ),
    Case(
        "plan-side reversal owns its old value",
        APPLY,
        "    owned = r.old_value if rollback else r.new_value",
        "    owned = r.new_value",
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
        '        holds = f"u.{lane.column} IS NOT DISTINCT FROM p.written"',
        '        holds = f"u.{lane.column} IS NOT NULL"',
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
            ("an unsafe column", "    if not _IDENTIFIER.match(lane.column):"),
            (
                "an unsafe temp table",
                "        if not _IDENTIFIER.match(self.plan_table) or not "
                'self.plan_table.startswith("_"):',
            ),
            ("an unsafe label", "        if not _LABEL.match(self.label):"),
            ("an unsafe key prefix", "        if not _KEY_PREFIX.match(self.key_prefix):"),
            ("a non-positive width", "    if lane.max_chars <= 0:"),
            (
                "an incomplete journal identity",
                "        if not self.run_stamp or not self.test_id or not self.confidence:",
            ),
            (
                "an unwritable owned value",
                "        if not value or len(value) > lane.max_chars:",
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
                "test_schematic_a_row_of_another_source_is_refused",
            ),
            (
                "Ireland and United Kingdom rows only",
                "    if stored not in IN_SCOPE:",
                "test_schematic_a_region_already_spelled_out_is_out_of_scope",
            ),
            (
                "a point to locate",
                "    if site.lat is None or site.lon is None:",
                "test_schematic_a_row_without_a_point_is_refused",
            ),
            (
                "a decided unit",
                "    if where.unit is None:",
                "test_schematic_a_point_5_km_at_sea_is_undecided",
            ),
            (
                "the Republic's side of the border",
                "    if unit == IRELAND:",
                "test_schematic_a_united_kingdom_row_in_the_republic_contradicts",
            ),
            (
                "an Ireland row in the Republic is consistent",
                "        if stored == IRELAND:\n            return verdict(",
                "test_schematic_an_ireland_row_in_the_republic_is_consistent",
            ),
            (
                "one of the four UK units",
                "    if unit not in UK_UNITS:",
                "test_schematic_a_crown_dependency_is_not_a_uk_part",
            ),
            (
                "not at the border",
                "        if to_ireland <= TOLERANCE_M:",
                "test_schematic_an_ireland_row_300_m_from_the_border_is_ambiguous",
            ),
            (
                "GB in both vocabularies",
                '    if codes.get(new) != "GB" or new_iso != "GB":',
                "test_schematic_without_the_vocabulary_change_northern_ireland_is_refused",
            ),
            (
                "the expected ISO transition",
                "    if (old_iso, new_iso) != EXPECTED_ISO[str(stored)]:",
                "test_schematic_an_unexpected_iso_transition_is_refused",
            ),
            (
                "fixed point",
                "    if not _is_canonical(new, dict(codes), normalize):",
                "test_schematic_a_value_the_census_would_flag_again_is_refused",
            ),
            (
                "exactly one entity",
                "    if len(candidate.qids) != 1:",
                "test_schematic_a_site_needs_exactly_one_entity",
            ),
            (
                "the entity was collected",
                "    if entity is None:",
                "test_schematic_an_entity_missing_from_the_cache_is_refused",
            ),
            (
                "the entity has a point",
                "    if point is None:",
                "test_schematic_an_entity_without_a_point_is_refused",
            ),
            (
                "the entity point is in the same unit",
                "    if wd_where.unit != unit:",
                "test_schematic_an_entity_point_in_another_unit_is_refused",
            ),
            (
                "P17 does not contradict",
                "    if p17_ok is False:",
                "test_schematic_a_preferred_p17_of_ireland_contradicts",
            ),
            (
                "P131* reaches no other unit",
                "    if others:",
                "test_schematic_a_p131_chain_to_another_unit_contradicts",
            ),
            (
                "categories name no other unit",
                "    if named - {unit}:",
                "test_schematic_a_category_naming_the_republic_contradicts",
            ),
            (
                "a category can witness",
                "    if states_neither and unit in named:",
                "test_schematic_a_category_counts_only_when_it_names_the_unit",
            ),
            (
                "an ISO change needs a witness",
                "    if iso_changes and not witnessed:",
                "test_schematic_an_ireland_row_without_a_positive_witness_is_refused",
            ),
            (
                "unique unit names",
                "        if not units or len(names) != len(set(names)):",
                "test_schematic_duplicate_unit_names_are_refused",
            ),
            (
                "one covering unit decides",
                "        if len(covering) == 1:",
                "test_schematic_one_covering_unit_decides",
            ),
            (
                "one unit within tolerance decides",
                "        if len(near) == 1:",
                "test_schematic_an_offshore_row_takes_the_only_unit_within_tolerance",
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
                "test_schematic_a_category_is_no_witness_for_an_entity_that_states_p131",
            ),
            (
                "a category must name the unit",
                '        if title.endswith(f" in {suffix}")',
                "        if True",
                "test_schematic_a_category_counts_only_when_it_names_the_unit",
            ),
            (
                "the tolerance is T02's 1000 m",
                "if (metres := self.distance_m(u.name, lat, lon)) <= TOLERANCE_M",
                "if (metres := self.distance_m(u.name, lat, lon)) <= 10 * TOLERANCE_M",
                "test_schematic_a_point_5_km_at_sea_is_undecided",
            ),
            (
                "a phase-3 value is flagged as superseded",
                '    phase3 = last is not None and last.run_stamp.startswith("phase3:")',
                "    phase3 = False",
                "test_schematic_a_phase3_write_is_superseded_and_named",
            ),
            (
                "a write carries its premise",
                "            premise=candidate.premise if ok else None,",
                "            premise=None,",
                "test_schematic_one_covering_unit_decides",
            ),
            (
                "an offshore write is named as such",
                '        rule="geo-unit" if where.inside else "geo-unit-within-tolerance",',
                '        rule="geo-unit",',
                "test_schematic_an_offshore_row_takes_the_only_unit_within_tolerance",
            ),
            (
                "the unit is GEOUNIT, not NAME",
                "        units.append(Unit(_text(row.GEOUNIT), _text(row.SOVEREIGNT), geom))",
                "        units.append(Unit(_text(row.NAME), _text(row.SOVEREIGNT), geom))",
                "test_schematic_the_unit_is_the_geounit_and_not_the_short_name",
            ),
        )
    ),
    # ------------------------------------------------ the planners' shared helpers (plan.py)
    guard(
        "journal chain unbroken",
        PLAN,
        "    if at is not None:\n        before, after = links[at - 1], links[at]",
        "test_the_planners_use_the_shared_rule",
        CHAIN_TESTS,
    ),
    guard(
        "journal agrees with the live value",
        PLAN,
        "    if links and links[-1].new_value != live:",
        "test_the_planners_use_the_shared_rule",
        CHAIN_TESTS,
    ),
    guard(
        "the chain rule: each link starts where the last ended",
        JOURNAL_CHAIN,
        "        if transitions[index][0] != transitions[index - 1][1]:",
        "test_a_link_that_starts_elsewhere_breaks_the_chain_at_its_index",
        CHAIN_TESTS,
    ),
    Case(
        "a reversal is named by its suffix",
        JOURNAL_CHAIN,
        "    return stamp.endswith(ROLLBACK_SUFFIX)",
        "    return False",
        "test_every_writer_names_its_reversal_with_the_suffix",
        CHAIN_TESTS,
    ),
    # ------------------------------------------- the planners read production as they assume
    *(
        Case(f"loader: {label}", path, old, new, test, testfile)
        for label, path, old, new, test, testfile in (
            (
                "the journal is read oldest first",
                PLAN,
                'row_pk IN ({sql_ids(ids)}) ORDER BY id"',
                'row_pk IN ({sql_ids(ids)})"',
                "test_load_journal_reads_one_column_oldest_first",
                LOADER_TESTS,
            ),
            (
                "the journal is read for one column",
                PLAN,
                'f"AND column_name = {sql_literal(column)} AND row_pk IN',
                'f"AND row_pk IN',
                "test_load_journal_reads_one_column_oldest_first",
                LOADER_TESTS,
            ),
            (
                "the UK premise is the database's",
                UK,
                '                premise=r["premise"],',
                "                premise=f\"{r['lat']},{r['lon']}\",",
                "test_the_uk_candidates_carry_the_database_s_premise_qids_and_country_chain",
                LOADER_TESTS,
            ),
            (
                "the period premise is the database's",
                PERIOD,
                '            premise=r["premise"],',
                '            premise=str(r["period_start"]),',
                "test_the_period_rows_carry_both_journals_and_the_printed_year",
                LOADER_TESTS,
            ),
            (
                "the site_type restore is what the last write replaced",
                SHAPE,
                "    restore = last.old_value",
                "    restore = row.journal[0].old_value",
                "test_a_two_link_chain_restores_what_the_last_write_replaced",
                SHAPE_TESTS,
            ),
            (
                "the snapshot vouches for where the chain began",
                SHAPE,
                "    first = row.journal[0]",
                "    first = row.journal[-1]",
                "test_a_two_link_chain_restores_what_the_last_write_replaced",
                SHAPE_TESTS,
            ),
        )
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
    # --------------------------------- [H] SECURITY 3 / BACKEND B7: the pin and the commit state
    *(
        guard(f"pin: {label}", path, needle, test)
        for label, path, needle, test in (
            (
                "a plan to pin to",
                PLAN,
                '    if not path.exists():\n        raise PlanError(f"{path} does not exist - there is no plan',
                "test_a_missing_plan_cannot_pin_anything",
            ),
            (
                "a statement to verify",
                PLAN,
                '    if not path.exists():\n        raise PlanError(f"{path} does not exist - emit it',
                "test_a_missing_apply_is_refused",
            ),
            (
                "a pin at all",
                PLAN,
                "    if not declared:",
                "test_an_apply_without_a_pin_is_refused",
            ),
            ("one pin only", PLAN, "    if len(declared) > 1:", "test_two_pins_are_refused"),
            (
                "the pin names the plan as it is now",
                PLAN,
                "    if declared[0] != digest:",
                "test_a_plan_changed_after_the_emit_is_refused",
            ),
            (
                "the body is the plan's rendering",
                PLAN,
                "    if text != pinned(expected, digest):",
                "test_a_hand_edited_apply_is_refused",
            ),
            (
                "a stamp is applied once",
                APPLY,
                "    if already:",
                "test_a_stamp_that_already_journals_rows_is_never_applied_again",
            ),
            (
                "a failed exit is settled from the journal",
                APPLY,
                "    if proc.returncode != 0:\n        return settle(",
                "test_a_failed_exit_with_the_whole_journal_is_committed",
            ),
            (
                "all rows journalled means committed",
                APPLY,
                "    if count == len(records):\n        return COMMITTED",
                "test_a_timeout_after_the_commit_is_reported_as_committed",
            ),
            (
                "no row journalled means not committed",
                APPLY,
                "    if count == 0 and session_ended:\n        return NOT_COMMITTED",
                "test_a_script_error_with_an_empty_journal_is_not_committed",
            ),
            (
                "settle says NOT COMMITTED",
                APPLY,
                "    if state == NOT_COMMITTED:",
                "test_a_script_error_with_an_empty_journal_is_not_committed",
            ),
            (
                "a committed read-back is asserted",
                APPLY,
                "        if got.get(name) != want:",
                "test_every_disagreement_is_refused",
            ),
            (
                "an empty journal after a lost answer is no answer",
                APPLY,
                "    if count == 0:\n        raise OutcomeUnknown(",
                "test_a_timeout_with_an_empty_journal_is_an_unknown_outcome",
            ),
            (
                "a probe that leaves a journal row fails",
                APPLY,
                "        if left:",
                "test_a_probe_that_leaves_a_journal_row_is_a_failure",
            ),
            (
                "the server bounds are rendered",
                APPLY,
                "    if lane.lock_timeout is not None or lane.statement_timeout is not None:",
                "test_the_new_lanes_bound_the_transaction_on_the_server",
            ),
            (
                "a journal count has one value",
                APPLY,
                "    if len(rows) != 1 or len(rows[0]) != 1:",
                "test_a_journal_count_of_the_wrong_shape_is_refused",
            ),
        )
    ),
    *(
        Case(f"pin: {label}", path, old, new, test, testfile)
        for label, path, old, new, test, testfile in (
            (
                "the digest is of the text, not the checkout's bytes",
                PLAN,
                '    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()',
                "    return hashlib.sha256(path.read_bytes()).hexdigest()",
                "test_the_digest_is_the_same_on_a_crlf_checkout",
                TESTFILE,
            ),
            (
                "the undo is written pinned",
                PLAN,
                '    path.write_text(pinned(sql, plan_sha256(plan_path)), encoding="utf-8", newline="\\n")',
                '    path.write_text(sql, encoding="utf-8", newline="\\n")',
                "test_emit_writes_the_apply_next_to_an_existing_rollback",
                TESTFILE,
            ),
            (
                "emit refuses an undo of another plan",
                APPLY,
                "    verify_pinned(rollback_path, plan_path=plan_path, expected=rollback_statement(records, lane))",
                "    pass",
                "test_emit_refuses_the_rollback_of_another_plan",
                TESTFILE,
            ),
            (
                "emit pins the apply",
                APPLY,
                "        pinned(apply_statement(records, lane), plan_sha256(plan_path)),",
                "        apply_statement(records, lane),",
                "test_the_apply_is_pinned_to_the_plan_and_verifies",
                TESTFILE,
            ),
            (
                "the rehearsal sends only the verified statement",
                APPLY,
                '    sql = verify_pinned(\n        out / "APPLY.sql", plan_path=plan_path, expected=apply_statement(records, lane)\n    )\n    script = rehearse',
                '    sql = (out / "APPLY.sql").read_text(encoding="utf-8")\n    script = rehearse',
                "test_a_plan_changed_after_the_emit_is_refused",
                TESTFILE,
            ),
            (
                "the apply sends only the verified statement",
                APPLY,
                '    sql = verify_pinned(\n        out / "APPLY.sql", plan_path=plan_path, expected=apply_statement(records, lane)\n    )\n    already',
                '    sql = (out / "APPLY.sql").read_text(encoding="utf-8")\n    already',
                "test_a_hand_edited_apply_is_refused",
                TESTFILE,
            ),
            (
                "the rollback rehearsal sends only the verified undo",
                APPLY,
                "    verify_pinned(path, plan_path=plan_path, expected=rollback_statement(records, lane))",
                "    pass",
                "test_the_rollback_rehearsal_refuses_a_rollback_of_another_plan",
                TESTFILE,
            ),
            (
                "a timeout is settled from the journal",
                APPLY,
                '    except OutcomeUnknown as exc:\n        return settle(records, lane, f"psql timed out',
                '    except KeyError as exc:\n        return settle(records, lane, f"psql timed out',
                "test_a_timeout_after_the_commit_is_reported_as_committed",
                TESTFILE,
            ),
            (
                "an empty journal is final only after psql's own stop",
                APPLY,
                "    if count == 0 and session_ended:",
                "    if count == 0:",
                "test_a_timeout_with_an_empty_journal_is_an_unknown_outcome",
                TESTFILE,
            ),
            (
                "a timeout never ends the session",
                APPLY,
                'f"psql timed out ({exc})", session_ended=False)',
                'f"psql timed out ({exc})", session_ended=True)',
                "test_a_timeout_with_an_empty_journal_is_an_unknown_outcome",
                TESTFILE,
            ),
            (
                "only psql's exit 3 ends the session",
                APPLY,
                "            session_ended=proc.returncode == PSQL_SCRIPT_ERROR,",
                "            session_ended=True,",
                "test_a_dropped_channel_with_an_empty_journal_is_an_unknown_outcome",
                TESTFILE,
            ),
            (
                "the commit state counts this lane's stamp",
                APPLY,
                "        count = journal_count(lane.run_stamp)",
                "        count = journal_count(lane.rollback_run_stamp)",
                "test_a_timeout_after_the_commit_is_reported_as_committed",
                TESTFILE,
            ),
            (
                "apply-once counts this lane's stamp",
                APPLY,
                "    already = journal_count(lane.run_stamp)",
                "    already = journal_count(lane.rollback_run_stamp)",
                "test_a_stamp_that_already_journals_rows_is_never_applied_again",
                TESTFILE,
            ),
            (
                "a settled commit is read back",
                APPLY,
                "    unconfirmed = confirm_committed(records, lane, what)\n    if unconfirmed is not None:\n"
                '        return unconfirmed\n    print(\n        "APPLY LANDED',
                '    print(\n        "APPLY LANDED',
                "test_a_read_back_that_disagrees_after_a_lost_answer_is_no_landing",
                TESTFILE,
            ),
            (
                "a clean commit is read back",
                APPLY,
                "    unconfirmed = confirm_committed(records, lane, what)\n    if unconfirmed is not None:\n"
                '        return unconfirmed\n    print("APPLY OK',
                '    print("APPLY OK',
                "test_a_read_back_that_disagrees_after_a_clean_commit_is_no_success",
                TESTFILE,
            ),
            (
                "a disagreeing read-back is committed, not refused",
                APPLY,
                "    except (OutcomeUnknown, PlanError) as exc:\n        return committed_unconfirmed(lane, what, exc)\n    for name",
                "    except KeyError as exc:\n        return committed_unconfirmed(lane, what, exc)\n    for name",
                "test_a_read_back_that_disagrees_after_a_clean_commit_is_no_success",
                TESTFILE,
            ),
            (
                "a failing read-back after the COMMIT is never a refusal",
                APPLY,
                "    except (OutcomeUnknown, PlanError) as exc:\n        return committed_unconfirmed(lane, what, exc)\n    # Printed",
                "    except KeyError as exc:\n        return committed_unconfirmed(lane, what, exc)\n    # Printed",
                "test_a_read_back_that_fails_after_the_commit_is_never_a_refusal",
                TESTFILE,
            ),
            (
                "a probe counts only its own guard's refusal",
                APPLY,
                "        own = proc.returncode == PSQL_SCRIPT_ERROR and refused_by_its_guard(lane, expected, errors)",
                "        own = bool(errors)",
                "test_a_probe_refused_by_another_guard_is_a_failure",
                TESTFILE,
            ),
            (
                "a probe counts only when psql stopped the script",
                APPLY,
                "        own = proc.returncode == PSQL_SCRIPT_ERROR and refused_by_its_guard(lane, expected, errors)",
                "        own = refused_by_its_guard(lane, expected, errors)",
                "test_a_probe_that_psql_did_not_stop_on_its_guard_is_a_failure",
                TESTFILE,
            ),
            (
                "a probe's refusal names the guard's text",
                APPLY,
                '    own = re.compile(re.escape(f"{lane.label}: ") + r"\\d+ " + re.escape(says))',
                '    own = re.compile(re.escape(f"{lane.label}: "))',
                "test_a_probe_refused_by_another_guard_is_a_failure",
                TESTFILE,
            ),
            (
                "failed probes have an exit code of their own",
                APPLY,
                "        return EXIT_PROBE_FAILED if cmd_probe_guards(records, out, lane) else EXIT_OK",
                "        return cmd_probe_guards(records, out, lane)",
                "test_a_probe_refused_by_another_guard_is_a_failure",
                TESTFILE,
            ),
            (
                "the lane read-backs are ordered",
                LANE,
                '        + "\\nORDER BY 1;\\n"',
                '        + ";\\n"',
                "test_every_lane_readback_is_ordered_by_metric",
                TESTFILE,
            ),
            (
                "a server bound is a plain duration",
                LANE,
                "            if bound is not None and not _DURATION.match(bound):",
                "            if False:",
                "test_a_lane_that_would_splice_something_unsafe_into_sql_is_refused",
                TESTFILE,
            ),
            (
                "a partial journal is no outcome",
                APPLY,
                '    raise OutcomeUnknown(\n        f"the journal holds {count} of',
                '    return COMMITTED or OutcomeUnknown(\n        f"the journal holds {count} of',
                "test_a_partial_journal_is_an_unknown_outcome",
                TESTFILE,
            ),
            (
                "an unreadable journal is an unknown outcome",
                APPLY,
                "    except (OutcomeUnknown, PlanError) as exc:\n        raise OutcomeUnknown(",
                "    except KeyError as exc:\n        raise OutcomeUnknown(",
                "test_a_journal_read_that_fails_is_an_unknown_outcome",
                TESTFILE,
            ),
            (
                "the CLI reports an unknown outcome",
                APPLY,
                '    except OutcomeUnknown as exc:\n        print(f"OUTCOME UNKNOWN',
                '    except KeyError as exc:\n        print(f"OUTCOME UNKNOWN',
                "test_main_reports_an_unknown_outcome_with_its_own_exit_code",
                TESTFILE,
            ),
            (
                "the CLI reports a refusal",
                APPLY,
                '    except PlanError as exc:\n        print(f"REFUSED',
                '    except KeyError as exc:\n        print(f"REFUSED',
                "test_the_cli_never_re_emits_before_it_sends",
                TESTFILE,
            ),
            (
                "only --emit writes APPLY.sql",
                APPLY,
                "    if args.emit:\n        emit(",
                "    if args.emit or args.apply:\n        emit(",
                "test_the_cli_never_re_emits_before_it_sends",
                TESTFILE,
            ),
            (
                "a timeout is never a plain failure",
                PROD_WRITE,
                "    except subprocess.TimeoutExpired as exc:",
                "    except KeyError as exc:",
                "test_a_timeout_is_an_unknown_outcome",
                PROD_TESTS,
            ),
            (
                "a dead channel cannot hang",
                PROD_WRITE,
                'shlex.split(f"ssh {SSH_OPTIONS} {host}',
                'shlex.split(f"ssh {host}',
                "test_a_dead_channel_cannot_hang",
                PROD_TESTS,
            ),
            (
                "the pin is a sha256 digest",
                PROD_WRITE,
                '    if not re.fullmatch(r"[0-9a-f]{64}", digest):',
                "    if False:",
                "test_pin_line_refuses_what_is_not_a_digest",
                PROD_TESTS,
            ),
        )
    ),
    # ------------------------------------------ cell lanes (2026-09-23): the lane shape
    *(
        guard(f"cells: lane refuses {label}", LANE, needle, test, CELL_TESTS)
        for label, needle, test in (
            (
                "a table not keyed by a site id",
                "        if TARGET_KEYS.get(self.table) != self.key_column:",
                "test_a_target_must_be_keyed_by_a_site_id",
            ),
            (
                "u as anything but the site",
                '        if not _IDENTIFIER.match(self.alias) or (self.alias == "u") != self.is_site:',
                "test_u_is_the_site_and_only_the_site",
            ),
            (
                "an unsafe cell column",
                "        if not _IDENTIFIER.match(self.name):",
                "test_a_column_that_would_splice_something_unsafe_is_refused",
            ),
            (
                "a cast type outside the closed set",
                "        if self.sql_type not in CELL_TYPES:",
                "test_a_column_that_would_splice_something_unsafe_is_refused",
            ),
            (
                "a non-positive cell width",
                "        if self.max_chars is not None and self.max_chars <= 0:",
                "test_a_column_that_would_splice_something_unsafe_is_refused",
            ),
            (
                "an unwritable owned cell value",
                "            if not value or (self.max_chars is not None and len(value) > self.max_chars):",
                "test_a_column_that_would_splice_something_unsafe_is_refused",
            ),
            (
                "a cell lane that names a column",
                "    if lane.column or lane.max_chars or lane.allowed_new_values:",
                "test_a_cell_lane_names_its_columns_only_in_cells",
            ),
            (
                "a cell named twice",
                "    if len(set(names)) != len(names):",
                "test_a_cell_lane_names_its_columns_only_in_cells",
            ),
            (
                "a column lane off unified_sites or reversing",
                "    if not lane.target.is_site or lane.reverses_journal:",
                "test_a_column_lane_writes_unified_sites_and_reverses_nothing",
            ),
            (
                "a cell key without its column",
                "        if column is None:",
                "test_a_cell_key_names_its_column_and_a_reversal_its_suffix",
            ),
            (
                "a column lane key of another column",
                "            if column not in (None, self.column):",
                "test_a_cell_key_names_its_column_and_a_reversal_its_suffix",
            ),
            (
                "an unknown lane name",
                "    if match is None:",
                "test_a_card_stats_wave_resolves_and_nothing_else_does",
            ),
        )
    ),
    Case(
        "cells: a wave label is a date",
        LANE,
        r'CARD_STATS_LANE = re.compile(r"^card-stats-(\d{4}-\d{2}-\d{2}[a-z]?)$")',
        r'CARD_STATS_LANE = re.compile(r"^card-stats-(.+)$")',
        "test_a_card_stats_wave_resolves_and_nothing_else_does",
        CELL_TESTS,
    ),
    Case(
        "scope: no longitude is inside the window",
        LANE,
        '    return f"({p}lon IS NOT NULL AND {date} > {cutoff})"',
        '    return f"({date} > {cutoff})"',
        "test_the_residual_is_the_project_s_own_rule_negated",
        SCOPE_TESTS,
    ),
    # ------------------------------------------------------- cell lanes: the plan-side mirror
    *(
        guard(f"cells: plan-side {label}", APPLY, needle, test, CELL_TESTS)
        for label, needle, test in (
            (
                "a column lane record of another column",
                "        if r.column not in (None, lane.column):",
                "test_a_column_lane_record_may_not_name_another_column",
            ),
            (
                "an integer spelled otherwise",
                "        if str(number) != text:",
                "test_every_cell_is_checked_in_its_column_s_type",
            ),
            (
                "NULL where the lane never leaves one",
                "    if values[filled_side] is None:",
                "test_a_fill_may_start_from_null_but_never_end_in_it",
            ),
            (
                "NULL in a column the lane does not fill",
                "    if values[empty_side] is None and not cell.fills_null:",
                "test_a_column_the_lane_does_not_fill_is_never_null",
            ),
            (
                "an empty new value",
                '    if r.new_value == "":',
                "test_every_cell_is_checked_in_its_column_s_type",
            ),
            (
                "a typed no-op",
                '    if values["old"] is not None and typed["old"] == typed["new"]:',
                "test_every_cell_is_checked_in_its_column_s_type",
            ),
            (
                "a cell wider than its column",
                "    if cell.max_chars is not None and r.new_value is not None and len(r.new_value) > cell.max_chars:",
                "test_every_cell_is_checked_in_its_column_s_type",
            ),
            (
                "a value the cell does not own",
                "    if cell.allowed_new_values and lane_value not in cell.allowed_new_values:",
                "test_an_owned_column_refuses_a_value_the_lane_does_not_own",
            ),
            (
                "two premises for one site",
                "        if premises.setdefault(r.site_id, r.premise) != r.premise:",
                "test_every_cell_of_a_site_carries_the_same_premise",
            ),
            (
                "a reversal without its journal row",
                "        if wants_journal_id and r.journal_id is None:",
                "test_a_reversal_names_its_journal_row_and_only_a_reversal_does",
            ),
            (
                "a journal row nobody checks",
                "        if not wants_journal_id and r.journal_id is not None:",
                "test_a_reversal_names_its_journal_row_and_only_a_reversal_does",
            ),
        )
    ),
    *(
        Case(f"cells: plan-side {label}", APPLY, old, new, test, CELL_TESTS)
        for label, old, new, test in (
            (
                "a cell of an unowned column",
                "        lane.cell(r.column)\n    except ValueError",
                "        pass\n    except ValueError",
                "test_a_cell_must_name_a_column_the_lane_owns",
            ),
            (
                "jsonb that does not parse",
                "            return json.loads(text)",
                "            return text",
                "test_every_cell_is_checked_in_its_column_s_type",
            ),
            (
                "a reversal owns the value it undoes",
                "    lane_value = r.old_value if rollback else r.new_value",
                "    lane_value = r.new_value",
                "test_an_owned_column_refuses_a_value_the_lane_does_not_own",
            ),
            (
                "only a reversal's write names journal rows",
                "        wants_journal_id = lane.reverses_journal and not rollback",
                "        wants_journal_id = lane.reverses_journal",
                "test_a_reversal_names_its_journal_row_and_only_a_reversal_does",
            ),
        )
    ),
    # ------------------------------------------------------------- cell lanes: the statement
    *(
        Case(f"cells: rendered {label}", APPLY, old, new, test, CELL_TESTS)
        for label, old, new, test in (
            (
                "guard 1 needs the target row",
                'add(f"     WHERE {row} IS NULL OR u.id IS NULL OR u.source_id <> {_literal(source)};")',
                'add(f"     WHERE u.id IS NULL OR u.source_id <> {_literal(source)};")',
                "test_scope_guard_1_needs_the_card_stats_row_and_a_curated_site",
            ),
            (
                "guard 2 refuses NULL on the filled side",
                '        refused.append(f"{filled} IS NULL")',
                "        pass",
                "test_guard_2_allows_null_only_on_the_side_the_lane_fills",
            ),
            (
                "guard 2 refuses an unowned column",
                '    return "CASE p.column_name" + "".join(whens) + "\\n                ELSE true END"',
                '    return "CASE p.column_name" + "".join(whens) + "\\n                ELSE false END"',
                "test_every_comparison_is_made_in_the_column_s_type",
            ),
            (
                "guards 3 and invariant 1 refuse an unowned column",
                '    otherwise: str = "true",',
                '    otherwise: str = "false",',
                "test_every_comparison_is_made_in_the_column_s_type",
            ),
            (
                "guard 4 reads the old value on a reversal",
                '        lane_side = "p.old_value" if rollback else "p.new_value"',
                '        lane_side = "p.new_value"',
                "test_guard_4_covers_the_owned_columns_only",
            ),
            (
                "guard 6 only on a reversal's write",
                "    journal_guard = lane.reverses_journal and not rollback",
                "    journal_guard = lane.reverses_journal",
                "test_guard_6_is_rendered_for_a_reversal_s_write_only",
            ),
            (
                "guard 6 refuses a later write",
                'add(f"             WHERE {journal_cell} AND l.id > p.journal_id);")',
                'add(f"             WHERE {journal_cell} AND l.id < p.journal_id);")',
                "test_guard_6_is_rendered_for_a_reversal_s_write_only",
            ),
            (
                "the writer names the target",
                'f"            {_literal(target.table)}, r.column_name, {_literal(target.key_column)}, "',
                "f\"            'unified_sites', r.column_name, 'id', \"",
                "test_the_writer_names_the_target_and_each_cell_s_column",
            ),
            (
                "invariant 2 joins each cell's column",
                "add(f\"       AND l.column_name = {'p.column_name' if cells else _literal(column)}\")",
                'add(f"       AND l.column_name = {_literal(column)}")',
                "test_the_writer_names_the_target_and_each_cell_s_column",
            ),
            (
                "a journal row of another column never reads as landed",
                '            column_expr="l.column_name",\n            otherwise="false",',
                '            column_expr="l.column_name",\n            otherwise="true",',
                "test_the_read_backs_compare_each_cell_in_its_type",
            ),
            (
                "a probe value valid in its type",
                '    "integer": "-987654321",',
                '    "integer": "never",',
                "test_each_corrupted_value_is_valid_in_its_column_s_type",
            ),
            (
                "the foreign-column probe names an unowned column",
                '            corrupt(0, column="name"),',
                "            corrupt(0),",
                "test_the_foreign_column_probe_names_a_column_the_lane_does_not_own",
            ),
            (
                "the foreign row of a cell lane reads no column",
                '            f"SELECT u.id::text AS id, u.name{premise} "\n            "FROM unified_sites u',
                '            f"SELECT u.id::text AS id, u.name, u.x AS value{premise} "\n            "FROM unified_sites u',
                "test_the_probes_read_another_source_s_site_without_a_column",
            ),
        )
    ),
    *(
        guard(f"cells: rendered {label}", APPLY, needle, test, CELL_TESTS)
        for label, needle, test in (
            (
                "guard 2 refuses NULL in a column the lane does not fill",
                "        if not cell.fills_null:",
                "test_guard_2_allows_null_only_on_the_side_the_lane_fills",
            ),
            (
                "guard 2 checks each width",
                "        if cell.max_chars is not None:",
                "test_every_comparison_is_made_in_the_column_s_type",
            ),
            (
                "guard 4 on the owned cells",
                "    if owned_cells:",
                "test_guard_4_covers_the_owned_columns_only",
            ),
            (
                "guard 5 once per site",
                "        if cells:\n            # the premise is the site's",
                "test_guard_5_reads_each_site_s_premise_once",
            ),
            (
                "guard 6",
                "    if journal_guard:\n        journal_cell",
                "test_guard_6_is_rendered_for_a_reversal_s_write_only",
            ),
            (
                "a cell lane's probes",
                "    if lane.cells:\n        return _cell_probe_cases(",
                "test_each_corrupted_value_is_valid_in_its_column_s_type",
            ),
            (
                "the too-long probe",
                "    if wide is not None:",
                "test_the_probes_match_the_guards_each_lane_renders",
            ),
            (
                "the guard-6 probe",
                "    if lane.reverses_journal:\n        probes.append(",
                "test_the_probes_match_the_guards_each_lane_renders",
            ),
        )
    ),
    Case(
        "cells: the column lanes render as before",
        APPLY,
        '        add("    site_id     UUID PRIMARY KEY,")',
        '        add("    site_id     UUID  PRIMARY KEY,")',
        "test_every_statement_is_the_pre_generalisation_rendering",
        TESTFILE,
    ),
    # ------------------------------------------------------------ cell lanes: the plan records
    *(
        guard(f"cells: plan record {label}", PLAN, needle, test, CELL_TESTS)
        for label, needle, test in (
            (
                "names an owned column",
                "    if lane.cells:\n        lane.cell(column)",
                "test_a_plan_record_names_its_table_key_and_cell",
            ),
            (
                "keeps the premise expression on a column lane's lines",
                "        if not lane.cells:\n            # A cell lane's premise",
                "test_a_column_lane_record_still_names_its_premise_expression",
            ),
            (
                "carries the journal row",
                "    if lane.reverses_journal:\n        if change.journal_id is None:",
                "test_a_reversal_record_carries_its_journal_row",
            ),
            (
                "refuses a reversal without its journal row",
                "        if change.journal_id is None:",
                "test_a_reversal_record_carries_its_journal_row",
            ),
            (
                "reverses a cell into its own column",
                "    if lane.cells:\n        # A cell's reversal",
                "test_the_undo_restores_null_where_the_lane_filled_it",
            ),
        )
    ),
    Case(
        "cells: plan record keeps the premise expression off each cell",
        PLAN,
        "        if not lane.cells:\n            # A cell lane's premise",
        "        if True:\n            # A cell lane's premise",
        "test_a_plan_record_names_its_table_key_and_cell",
        CELL_TESTS,
    ),
    # ----------------------------------------------------------------- the card_stats planner
    *(
        guard(f"card_stats: {label}", CARD_STATS, needle, test, CARD_TESTS)
        for label, needle, test in (
            (
                "the jsonb spelling is the database's",
                '        if text is not None and cell_text("empires", json.loads(text)) != text:',
                "test_empires_are_spelled_the_way_the_database_prints_them",
            ),
            (
                "the generator's description filter",
                '        if not row["description"]:',
                "test_a_row_without_a_description_is_not_recomputed",
            ),
            (
                "an empire production does not list",
                "        if unranked:",
                "test_an_empire_production_does_not_list_is_refused",
            ),
            (
                "the tagger reads the repository",
                "    if here != HISTORICAL.resolve():",
                "test_the_tagger_must_read_the_repository_s_boundaries",
            ),
            (
                "production lists every empire",
                "    if unlisted:",
                "test_the_tagger_must_read_the_repository_s_boundaries",
            ),
            (
                "only inputs are put back",
                "        if column not in INPUT_COLUMNS:",
                "test_journalled_inputs_are_put_back_newest_first",
            ),
            (
                "the counterfactual must reproduce the cards",
                "    if differ:",
                "test_a_model_that_does_not_reproduce_them_refuses_to_plan",
            ),
            (
                "no row is inserted",
                '        if not row["has_card"]:',
                "test_a_row_without_a_card_is_reported_not_inserted",
            ),
            (
                "an empty plan leaves no statement, a full one its undo",
                "    if plan.changes:\n        write_rollback_sql(",
                "test_a_plan_with_cells_gets_its_undo",
            ),
            (
                "no cell is cleared",
                "            if new is None:",
                "test_a_cell_the_generator_would_clear_is_reported_not_written",
            ),
            # ---- 2026-09-23 review: the guards it found without a case, and the basis
            (
                "a wave label nothing could apply",
                '    if CARD_STATS_LANE.match(f"card-stats-{wave}") is None:',
                "test_a_wave_label_nothing_could_apply_is_refused",
            ),
            (
                "an export without sites",
                '    if not rows["site"]:',
                "test_an_export_without_its_snapshot_line_or_sites_is_refused",
            ),
            (
                "an export without an empire order",
                "    if not empire_order:",
                "test_an_export_without_an_empire_order_is_refused",
            ),
            (
                "a failed empire listing",
                "    if proc.returncode != 0:",
                "test_the_empire_order_is_production_s_listing_or_a_refusal",
            ),
            (
                "an empty empire listing",
                "    if not names:",
                "test_the_empire_order_is_production_s_listing_or_a_refusal",
            ),
            (
                "an incomplete export on disk",
                "        if not needed.exists():",
                "test_the_empire_order_file_is_a_list_of_names",
            ),
            (
                "a tagger that finds no empire",
                "    if not empires:",
                "test_a_tagger_that_finds_no_empire_is_refused",
            ),
            (
                "a row the generator skips",
                "        if stats is None:",
                "test_a_row_the_generator_skips_is_left_as_the_generator_leaves_it",
            ),
            (
                "a row of another source",
                '        if row["source_id"] != CURATED_SOURCE:',
                "test_a_row_of_another_source_is_reported_not_written",
            ),
            (
                "a wave's write names its after-side",
                "        if stamp == lane.run_stamp:",
                "test_the_write_and_the_undo_name_their_own_sides",
            ),
            (
                "a wave's undo names its before-side",
                "        if stamp == lane.rollback_run_stamp:",
                "test_the_write_and_the_undo_name_their_own_sides",
            ),
            (
                "a missing basis file",
                "    if not path.exists():",
                "test_a_missing_basis_file_refuses",
            ),
            (
                "the basis file is the applied plan's",
                '    if cells_digest(wrote) != record["cells_sha256"]:',
                "test_a_basis_file_that_is_not_the_applied_plan_s_refuses",
            ),
            (
                "an undo is the exact inverse of its write",
                '        if cells_digest(undone) != record["cells_sha256"]:',
                "test_an_undo_that_is_not_the_exact_inverse_refuses",
            ),
            (
                "a basis of another wave",
                '    if record["wave"] != wave:',
                "test_a_basis_of_another_wave_refuses",
            ),
            (
                "after a wave, its own export is the basis",
                '    if side == "after":',
                "test_a_like_after_a_wave_s_export_is_put_back",
            ),
            (
                "the curated sites are the basis's",
                "    if set(by_id) != set(basis.unjournalled):",
                "test_a_site_the_basis_does_not_know_refuses",
            ),
            (
                "a row committed below the horizon",
                "    if seen != basis.journal_rows:",
                "test_a_row_committed_below_the_horizon_after_the_export_refuses",
            ),
            (
                "a cell the basis wave refused is not compared",
                '            if (row["id"], column) in excluded:',
                "test_a_cell_the_basis_wave_refused_is_not_compared",
            ),
            (
                "an applied wave is never re-planned",
                "    if applied:",
                "test_an_applied_wave_is_never_re_planned",
            ),
        )
    ),
    *(
        Case(f"card_stats: {label}", CARD_STATS, old, new, test, CARD_TESTS)
        for label, old, new, test in (
            (
                "production's empire order",
                '        stats["empires"] = sorted(stats["empires"], key=rank.__getitem__)',
                "        pass",
                "test_the_empires_take_production_s_directory_order",
            ),
            (
                "mystery counts every curated row",
                '    combos = Counter((row["site_type"], row["period_name"]) for row in sites)',
                '    combos = Counter((row["site_type"], row["period_name"]) for row in sites if row["description"])',
                "test_mystery_counts_every_curated_row_with_a_description_or_not",
            ),
            (
                "only writes past the basis horizon are put back",
                '        if entry["table_name"] != "unified_sites" or int(entry["id"]) <= basis.since:',
                '        if entry["table_name"] != "unified_sites" or int(entry["id"]) <= 0:',
                "test_only_what_was_written_after_the_basis_horizon_is_put_back",
            ),
            (
                "the journal is put back newest first",
                '    for entry in sorted(journal, key=lambda j: int(j["id"]), reverse=True):',
                '    for entry in sorted(journal, key=lambda j: int(j["id"])):',
                "test_journalled_inputs_are_put_back_newest_first",
            ),
            (
                "the unjournalled inputs are the basis's",
                '        row.update(basis.unjournalled[row["id"]])',
                "        pass",
                "test_a_like_after_a_wave_s_export_is_put_back",
            ),
            (
                "a card_stats row no wave wrote refuses",
                "    raise PlanError(\n        f\"card_stats journal row {last['id']} was written by",
                "    return None\n    raise PlanError(\n        f\"card_stats journal row {last['id']} was written by",
                "test_a_card_stats_row_no_wave_wrote_refuses",
            ),
            (
                "an undo restores the basis its wave's proof stood on",
                '    inner = record["proof_basis"]',
                "    inner = None",
                "test_an_undo_of_a_later_wave_restores_the_earlier_wave_s_basis",
            ),
            (
                "--wave is checked before a plan is written",
                "        card_stats_lane(value)\n    except ValueError",
                "        pass\n    except ValueError",
                "test_a_wave_label_nothing_could_apply_is_refused",
            ),
            (
                "--write keeps the wave's basis",
                "            write_basis_json(basis_record(result, export, args.wave), out / BASIS_FILE)\n",
                "",
                "test_main_writes_the_wave_s_basis_next_to_its_plan",
            ),
        )
    ),
    *(
        Case(f"generator: {label}", GENERATOR, old, new, test, GENERATOR_TESTS)
        for label, old, new, test in (
            (
                "a missing content type is a type",
                "        content_types.add(link.content_type)",
                "        content_types.add(link.content_type or 'reference')",
                "test_content_stats_counts_links_types_and_a_3d_model",
            ),
            (
                "a lonely combination counts as one",
                "    combo_count = combo_counts.get(combo_key, 1)",
                "    combo_count = combo_counts.get(combo_key, 100)",
                "test_a_combination_nobody_else_has_counts_as_one",
            ),
            (
                "the upsert writes site_card_stats",
                "            engagement=_get_engagement(session, site.id),",
                "            engagement=(0, 0),",
                "test_the_upsert_writes_exactly_what_site_card_stats_returns",
            ),
        )
    ),
    # ---------------------------------------------------------------------- the scope planner
    *(
        guard(f"scope: {label}", SCOPE, needle, test, SCOPE_TESTS)
        for label, needle, test in (
            (
                "a duplicate needs both names within 100 m",
                '        if float(pair["metres"]) > DUPLICATE_METRES or not all(known):',
                "test_a_name_that_is_not_one_of_the_item_s_is_no_duplicate",
            ),
            (
                "a decision names its site",
                '            if decision.name != site["name"]:',
                "test_a_decision_that_names_another_site_is_refused",
            ),
            (
                "the quote is in the description",
                '            if decision.quote not in (site["description"] or ""):',
                "test_a_quote_the_description_does_not_hold_is_refused",
            ),
            (
                "a museum needs a reviewed decision",
                '            if decision is None or decision.rule != "d" or decision.status == PENDING:',
                "test_a_museum_past_the_cutoff_needs_a_reviewed_decision",
            ),
            (
                "a retired survivor keeps its duplicate",
                "        if survivor_retired:",
                "test_a_survivor_that_is_retired_keeps_its_duplicate",
            ),
            (
                "one decision per site",
                "        if decision.site_id in out:",
                "test_a_site_decided_twice_is_refused",
            ),
            (
                "the decision vocabulary",
                '        if decision.status not in SCOPE_STATUSES or decision.rule not in ("a", "b", "d"):',
                "test_a_malformed_entry_is_refused",
            ),
            (
                "a decision needs its evidence",
                "        if not decision.quote or not decision.note:",
                "test_a_malformed_entry_is_refused",
            ),
            # ---- 2026-09-23 review: the guards it found without a test or a case
            (
                "a T11 kind this lane does not decide",
                "        if rule is None:",
                "test_a_t11_kind_this_lane_does_not_decide_is_refused",
            ),
            (
                "T11 reports a site once",
                "        if finding.site_id in by_site:",
                "test_t11_reporting_a_site_twice_is_refused",
            ),
            (
                "a pair's item was collected",
                "        if entity is None:",
                "test_a_pair_whose_item_was_not_collected_is_refused",
            ),
            (
                "Wikidata answered every item",
                "    if missing:",
                "test_wikidata_answering_no_entity_is_refused",
            ),
            (
                "a decision names a curated site",
                "        if site is None:",
                "test_a_decision_for_a_site_that_is_not_curated_is_refused",
            ),
            (
                "the decisions file exists",
                "    if not path.exists():",
                "test_a_missing_decisions_file_is_refused",
            ),
            (
                "a decision names a UUID",
                "        if not UUID_RE.match(decision.site_id):",
                "test_a_malformed_entry_is_refused",
            ),
            (
                "an export holds a curated site",
                '    if not rows["site"]:',
                "test_an_export_is_its_one_snapshot_and_at_least_one_site",
            ),
        )
    ),
    *(
        Case(f"scope: {label}", SCOPE, old, new, test, SCOPE_TESTS)
        for label, old, new, test in (
            (
                "rule (a) turns retired into pending only",
                '            elif decision.rule == "a" and decision.status == PENDING:',
                "            elif True:",
                "test_rule_a_can_only_turn_a_retirement_into_pending",
            ),
            (
                "only a Museum row is kept by the museum rule",
                '            and "museum" in str(site["site_type"]).casefold()',
                "            and True",
                "test_an_undated_museum_is_kept_by_the_museum_rule_and_nothing_else_is",
            ),
            (
                "the older row survives",
                '        str(site["created_at"]),\n',
                "",
                "test_the_older_row_survives_before_the_one_with_more_links",
            ),
            (
                "an assessed site is left alone",
                '    out = [d for d in out if d.site["scope_status"] is None]',
                "    out = list(out)",
                "test_a_site_already_assessed_is_left_alone",
            ),
            (
                "a decision without a finding is refused",
                "    for site_id in sorted(unused):",
                "    for site_id in sorted(set()):",
                "test_a_decision_without_a_finding_is_refused",
            ),
            (
                "names fold width",
                '    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())',
                '    return " ".join(name.casefold().split())',
                "test_names_fold_case_width_and_spaces_but_nothing_else",
            ),
            (
                "rule (b) retires or keeps pending, nothing else",
                '        elif decision.rule == "b" and decision.status in (RETIRED, PENDING):',
                '        elif decision.rule == "b":',
                "test_an_undated_row_cannot_be_kept_in_scope_by_rule_b",
            ),
            (
                "a duplicate loser another rule decided",
                "        if dup.loser in decided or dup.loser in retired_survivors - {dup.survivor}:",
                "        if dup.loser in retired_survivors - {dup.survivor}:",
                "test_a_duplicate_loser_another_rule_decided_is_refused",
            ),
            (
                "a duplicate loser that is another pair's survivor",
                "        if dup.loser in decided or dup.loser in retired_survivors - {dup.survivor}:",
                "        if dup.loser in decided:",
                "test_a_duplicate_chain_never_retires_a_survivor",
            ),
        )
    ),
    Case(
        "scope: the premise holds the description",
        LANE,
        "        \"coalesce(u.site_type, 'NULL'), u.name, md5(coalesce(u.description, '')))\"",
        "        \"coalesce(u.site_type, 'NULL'), u.name)\"",
        "test_the_premise_holds_the_description_a_quote_rests_on",
        SCOPE_TESTS,
    ),
    # ------------------------------------------------------------------- the reversal planner
    *(
        guard(f"reversal: {label}", REVERSAL, needle, test, REVERSAL_TESTS)
        for label, needle, test in (
            (
                "the list is the code's",
                "    if sorted(ids) != sorted(expected) or len(set(ids)) != len(ids):",
                "test_the_reviewed_list_and_the_code_must_name_the_same_rows",
            ),
            (
                "the journal row exists",
                "    if entry is None:",
                "test_each_check_refuses_with_its_reason",
            ),
            (
                "a column the lane owns",
                "    if reason.column not in lane.columns:",
                "test_a_column_the_lane_does_not_own_is_refused",
            ),
            (
                "a curated site",
                '    if site is None or site["source_id"] != CURATED_SOURCE:',
                "test_each_check_refuses_with_its_reason",
            ),
            ("an unbroken chain", "    if broken is not None:", "test_a_broken_chain_is_refused"),
            (
                "the last write of its cell",
                "    if not cell.chain or cell.chain[-1].id != reason.journal_id:",
                "test_a_row_another_write_superseded_is_not_undone",
            ),
            (
                "no NULL restored",
                "    if restored is None:",
                "test_a_row_that_replaced_null_is_not_restored",
            ),
            (
                "every quote is where it says",
                "        if problem is not None:",
                "test_evidence_that_is_not_where_it_says_refuses",
            ),
            (
                "the gold standard judged it CORRECT",
                '        if verdict is None or verdict["verdict"] != "CORRECT":',
                "test_the_gold_standard_must_judge_the_restored_value_itself",
            ),
            (
                "the gold standard judged the restored value",
                '        if str(record["db_fields"].get(reason.column)) != str(restored):',
                "test_the_gold_standard_must_judge_the_restored_value_itself",
            ),
            (
                "the gold record is the site's",
                "        if record is None or ref != reason.site_id:",
                "test_a_gold_record_of_another_site_does_not_count",
            ),
            # ---- 2026-09-23 review: the guards it found without a test or a case
            (
                "the reasons file exists",
                "    if not path.exists():",
                "test_a_missing_reasons_file_is_refused",
            ),
            (
                "a reversal needs a reason and quotes",
                "        if not r.reason or not r.quotes:",
                "test_a_reversal_without_a_reason_or_evidence_is_refused",
            ),
            (
                "a quoted page was collected",
                "        if quote.source not in pages:",
                "test_evidence_that_is_not_where_it_says_refuses",
            ),
            (
                "the quote is in its source",
                "    if quote.text not in text:",
                "test_evidence_that_is_not_where_it_says_refuses",
            ),
        )
    ),
    *(
        Case(f"reversal: {label}", REVERSAL, old, new, test, REVERSAL_TESTS)
        for label, old, new, test in (
            (
                "the named row is the reason's cell",
                '    if (\n        entry["table_name"] != "unified_sites"',
                '    if False and (\n        entry["table_name"] != "unified_sites"',
                "test_each_check_refuses_with_its_reason",
            ),
            (
                "the restored value reads in its column",
                "    try:\n        typed_value(lane.cell(reason.column), str(restored))",
                "    try:\n        pass",
                "test_a_restored_value_the_column_cannot_read_is_refused",
            ),
            (
                "a source this lane cannot check",
                '        return f"{quote.source!r} is not a source this lane can check"',
                "        text = quote.text",
                "test_a_quote_of_a_source_this_lane_cannot_check_refuses",
            ),
        )
    ),
    # ------------------------------------------ the tagged export the cell lanes share (plan.py)
    *(
        guard(f"tagged export: {label}", PLAN, needle, test, CELL_TESTS)
        for label, needle, test in (
            (
                "a kind is a plain word",
                "        if not _EXPORT_KIND.match(kind) or kind == SNAPSHOT_KIND:",
                "test_a_kind_that_is_not_a_plain_word_is_refused",
            ),
            (
                "one snapshot line",
                "    if len(stamps) != 1:",
                "test_the_rows_of_each_kind_and_one_snapshot",
            ),
        )
    ),
    *(
        Case(f"tagged export: {label}", PLAN, old, new, test, CELL_TESTS)
        for label, old, new, test in (
            (
                "a line of a kind nobody asked for",
                '            raise PlanError(f"the export holds a line of kind {kind!r}: {line[:80]!r}")',
                "            continue",
                "test_the_rows_of_each_kind_and_one_snapshot",
            ),
            (
                "a failed export",
                '    if proc.returncode != 0:\n        raise PlanError(f"the export failed',
                '    if False:\n        raise PlanError(f"the export failed',
                "test_a_failed_export_is_refused_and_keeps_nothing",
            ),
        )
    ),
    # ------------------------------------------ guard 6's inverse clause, its probe, the residual
    *(
        Case(f"cells: {label}", path, old, new, test, CELL_TESTS)
        for label, path, old, new, test in (
            (
                "guard 6: the named row wrote the planned old value",
                APPLY,
                '        add("               AND l.new_value IS NOT DISTINCT FROM p.old_value")\n',
                "",
                "test_guard_6_requires_the_exact_inverse_of_the_named_row",
            ),
            (
                "guard 6: the named row replaced the planned new value",
                APPLY,
                '        add("               AND l.old_value IS NOT DISTINCT FROM p.new_value)")',
                '        add("               )")',
                "test_guard_6_requires_the_exact_inverse_of_the_named_row",
            ),
            (
                "the inverse probe restores another value from its own row",
                APPLY,
                "                corrupt(0, new_value=NEVER_STORED[first_cell.sql_type]),",
                "                corrupt(0, journal_id=0),",
                "test_the_inverse_probe_names_its_own_row_and_restores_another_value",
            ),
            (
                "the reversal residual covers every cell",
                LANE,
                '    holds = typed_case(\n        cells,\n        "l.new_value",',
                '    holds = typed_case(\n        cells[:1],\n        "l.new_value",',
                "test_the_residual_compares_each_cell_of_the_lane_in_its_type",
            ),
        )
    ),
    Case(
        "reversal: the site is read through its key",
        REVERSAL,
        '            f"WHERE id IN ({sql_ids(r.site_id for r in reasons)})"',
        '            f"WHERE id::text IN ({sql_ids(r.site_id for r in reasons)})"',
        "test_load_state_reads_the_row_the_site_and_the_chain",
        REVERSAL_TESTS,
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


# ------------------------------------------------------------------------------ the image lanes
#: The Phase-2 image residue (design entry 7): the shared chunk writer, the hero repair's
#: extracted invariant and transport, G0b, the attribution lane, and the code fixes W2/W3/W14/W15.
#: Every label starts with "img" - `mutation_sweep.py img` runs exactly these.
CHUNK = REPO / "scripts/remediation/gallery_audit/chunk_writer.py"
HERO_APPLY = REPO / "scripts/remediation/hero_repair/apply.py"
PERSIST = REPO / "scripts/remediation/gallery_audit/persist_verdicts.py"
ATTRIB = REPO / "scripts/remediation/gallery_audit/attribution.py"
DOWNLOADER = REPO / "pipeline/wiki_image_downloader.py"
WIKI_ROUTE = REPO / "api/routes/wiki_images.py"
SHORTS = REPO / "pipeline/video/shorts_select.py"
EXPORTER = REPO / "pipeline/static_exporter.py"
T09 = REPO / "scripts/remediation/census/tests/t09_commons_dimensions.py"
CHUNK_TESTS = "tests/remediation/test_image_chunk_writer.py"
GALLERY_TESTS = "tests/remediation/test_gallery_audit.py"
ATTRIB_TESTS = "tests/remediation/test_gallery_attribution.py"
DL_TESTS = "tests/pipeline/test_wiki_image_downloader_fetch.py"
HERO_TESTS = "tests/api/test_wiki_images_hero.py"
SHORTS_TESTS = "tests/pipeline/test_shorts_select_strict.py"
EXPORT_TESTS = "tests/pipeline/test_static_exporter_served_image.py"
T09_TESTS = "tests/remediation/test_t09.py"
EXPRESS = "test_a_change_the_writer_cannot_express_exactly_is_refused"
DO_BLOCK = "test_every_guard_of_the_transaction_is_rendered_with_its_exact_condition"
INVARIANTS = "test_the_readback_names_every_broken_invariant"
JOURNAL = "test_the_readback_compares_every_journal_column_with_the_plan"

IMAGE_CASES: list[Case] = [
    # -- the shared chunk writer (W4)
    guard(
        "img chunk: only the writable columns", CHUNK, "    if kind is None:", EXPRESS, CHUNK_TESTS
    ),
    guard(
        "img chunk: a boolean is true or false",
        CHUNK,
        '        if kind == "boolean" and value not in ("true", "false"):',
        EXPRESS,
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: a no-op is refused",
        CHUNK,
        "    if change.old_value == change.new_value:",
        EXPRESS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: a unified_sites row is its site",
        CHUNK,
        "    elif change.row_key != change.site_id:",
        "    elif False:",
        EXPRESS,
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: a row planned twice",
        CHUNK,
        "        if ident in seen:",
        "test_a_row_planned_twice_is_refused",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: 100 whole sites per chunk",
        CHUNK,
        "    for number, start in enumerate(range(0, len(order), sites_per_chunk), start=1):",
        "    for number, start in enumerate(range(0, len(order), sites_per_chunk - 1), start=1):",
        "test_chunks_hold_at_most_100_whole_sites_in_the_callers_order",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: key casts are guarded by CASE",
        CHUNK,
        "    return f\"CASE WHEN p.table_name = {L(table)} THEN {_key(table, 'p.row_key')} END\"",
        '    return _key(table, "p.row_key")',
        "test_every_key_cast_is_guarded_by_its_table",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: the lint reads the write verbs",
        CHUNK,
        '    for word in ("DELETE", "UPDATE", "TRUNCATE", "DROP", "ALTER"):',
        "    for word in ():",
        "test_the_lint_reads_code_and_not_literals_or_comments",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: the lint blanks literals",
        CHUNK,
        "    code = re.sub(r\"'(?:[^']|'')*'\", \"''\", sql)",
        "    code = sql",
        "test_the_lint_reads_code_and_not_literals_or_comments",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: the undo is written first",
        CHUNK,
        '    (directory / "ROLLBACK.sql").write_text(rollback_sql, encoding="utf-8", newline="\\n")\n'
        '    (directory / "APPLY.sql").write_text(apply_sql, encoding="utf-8", newline="\\n")',
        '    (directory / "APPLY.sql").write_text(apply_sql, encoding="utf-8", newline="\\n")\n'
        '    (directory / "ROLLBACK.sql").write_text(rollback_sql, encoding="utf-8", newline="\\n")',
        "test_the_undo_is_written_before_the_write",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: a delivered chunk is never replaced",
        CHUNK,
        '            raise ChunkError(\n                f"{directory} holds another chunk',
        '            print(\n                f"{directory} holds another chunk',
        "test_a_delivered_chunk_is_never_replaced",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: the delivered bytes are the render",
        CHUNK,
        "        if text != render_statement(chunk, rollback=rollback):",
        "test_a_file_that_is_not_the_plans_is_refused_before_anything_is_sent",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: the pin names this plan",
        CHUNK,
        "        if pin is None or pin.group(1) != digest:",
        "test_a_file_that_is_not_the_plans_is_refused_before_anything_is_sent",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: a CRLF checkout is still the plan",
        CHUNK,
        '    return path.read_text(encoding="utf-8")',
        '    return path.read_bytes().decode("utf-8")',
        "test_a_chunk_checked_out_with_crlf_is_still_the_plans",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: never apply twice",
        CHUNK,
        "    if already:",
        "test_the_apply_writes_journals_and_reads_back_both_ways",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: only psql's exit 3 ends the session",
        CHUNK,
        "            session_ended=proc.returncode == PSQL_SCRIPT_ERROR,",
        "            session_ended=True,",
        "test_a_dropped_channel_with_an_empty_journal_is_unknown_not_uncommitted",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: an ended session with no journal",
        CHUNK,
        "    if count == 0 and session_ended:",
        "test_data_changed_underneath_is_not_committed",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: readback journal -> plan",
        CHUNK,
        "    for ident in sorted(set(journal) - set(planned)):",
        "    for ident in []:",
        "test_the_readback_names_a_journal_row_the_plan_does_not_have",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: readback plan -> journal",
        CHUNK,
        '        if row is None:\n            problems.append(f"plan -> journal:',
        "test_the_readback_names_a_planned_row_the_journal_does_not_have",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: readback of the data",
        CHUNK,
        "        elif now[ident] != want_value:",
        "        elif False:",
        "test_the_readback_names_a_row_that_does_not_hold_its_new_value",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: readback of the invariants",
        CHUNK,
        "            if value != 0:",
        INVARIANTS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: a rehearsal shows read-back and ROLLBACK",
        CHUNK,
        '        READBACK_LABEL in proc_stdout and "ROLLBACK" in proc_stdout and "COMMIT" not in proc_stdout\n    )',
        "        True\n    )",
        "test_the_rehearsal_that_never_showed_its_read_back_and_rollback_fails",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: nothing survives a rehearsal",
        CHUNK,
        "    if left != 0:",
        "test_the_rehearsal_fails_when_its_run_stamp_already_journals_rows",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: the scope guard names the source",
        CHUNK,
        "     WHERE u.id IS NULL OR u.source_id <> {L(CURATED_SOURCE)};",
        "     WHERE u.id IS NULL;",
        "test_the_scope_guard_refuses_every_site_outside_the_curated_source",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: may_empty sites are named",
        CHUNK,
        "        if may_empty\n        else",
        "        if False\n        else",
        "test_a_site_the_chunk_may_empty_is_named_in_the_statement",
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: only named sites may lose their image",
        CHUNK,
        "       AND b.site_id NOT IN (SELECT site_id FROM _img_may_empty);",
        "       AND true;",
        "test_a_site_the_chunk_may_empty_is_named_in_the_statement",
        CHUNK_TESTS,
    ),
    # -- the hero repair: extracted invariant and transport (W4)
    Case(
        "img hero: the transport is prod_write's",
        HERO_APPLY,
        "    proc = send(sql, host=host, timeout=timeout)",
        '    proc = subprocess.run(["ssh", host], input=sql, capture_output=True, text=True, timeout=timeout)',
        "test_the_hero_transport_reports_a_timeout_as_an_unknown_outcome",
        CHUNK_TESTS,
    ),
    Case(
        "img hero: the CLI reports an unknown outcome",
        HERO_APPLY,
        '    except OutcomeUnknown as exc:\n        print(\n            f"OUTCOME UNKNOWN',
        '    except KeyError as exc:\n        print(\n            f"OUTCOME UNKNOWN',
        "test_the_hero_transport_reports_a_timeout_as_an_unknown_outcome",
        CHUNK_TESTS,
    ),
    Case(
        "img hero: the at-most form compares > 1",
        HERO_APPLY,
        '"several rows", "> 1"',
        '"several rows", "<> 1"',
        "test_the_hero_invariant_is_the_hero_repairs_own_in_its_at_most_form",
        CHUNK_TESTS,
    ),
    Case(
        "img hero: the exact form compares <> 1",
        HERO_APPLY,
        '"two rows", "<> 1"',
        '"two rows", "> 1"',
        "test_the_hero_statement_is_byte_identical_after_the_extraction",
        CHUNK_TESTS,
    ),
    guard(
        "img hero: the RAISE label is quote-safe",
        HERO_APPLY,
        "    if not LABEL_RE.fullmatch(label):",
        "test_the_invariant_function_refuses_what_cannot_stand_in_its_sql",
        CHUNK_TESTS,
    ),
    # -- G0b: the kinds stated in the rejections (W6)
    guard(
        "img g0b: only PROVEN is written",
        PERSIST,
        '        if mapping != "PROVEN":',
        "test_a_mapping_that_is_not_proven_is_a_named_refusal",
        GALLERY_TESTS,
    ),
    guard(
        "img g0b: the stated kind is the reason's",
        PERSIST,
        "        if named != kind:",
        "test_a_malformed_mapping_record_stops_the_lane",
        GALLERY_TESTS,
    ),
    Case(
        "img g0b: production still holds the proof's row",
        PERSIST,
        "        if v.site_id is not None and (",
        "        if False and (",
        "test_a_row_that_no_longer_matches_the_proof_is_refused",
        GALLERY_TESTS,
    ),
    Case(
        "img g0b: the stamp is decided against G0's plan",
        PERSIST,
        "    stamp = run_stamp if run_stamp is not None else run_stamp_for(write)",
        "    stamp = run_stamp if run_stamp is not None else run_stamp_for(write, output=output)",
        "test_g0b_never_journals_under_the_landed_g0_stamp",
        GALLERY_TESTS,
    ),
    Case(
        "img g0b: its own directory",
        PERSIST,
        '"rejected-kinds", "G0b", "rejected_kinds"',
        '"rejected-kinds", "G0b", None',
        "test_g0b_lives_in_its_own_directory_and_leaves_g0s_files_alone",
        GALLERY_TESTS,
    ),
    Case(
        "img g0b: its SQL raises as G0b",
        PERSIST,
        '"rejected-kinds", "G0b", "rejected_kinds"',
        '"rejected-kinds", "G0", "rejected_kinds"',
        "test_the_g0b_statement_raises_under_its_own_scope_and_writes_its_own_kinds",
        GALLERY_TESTS,
    ),
    Case(
        "img g0b: verify reads for the batch's kinds",
        PERSIST,
        "        unjournalled_label(kinds),",
        '        unjournalled_label(("site_photo",)),',
        "test_the_g0b_verify_reads_for_its_own_kinds",
        GALLERY_TESTS,
    ),
    guard(
        "img g0b: one image, one kind",
        PERSIST,
        '        if image_id in seen and seen[image_id] != kind:\n            raise PersistError(f"{where}: image',
        "test_one_image_with_two_stated_kinds_stops_the_lane",
        GALLERY_TESTS,
    ),
    guard(
        "img g0b: a batch is one source",
        PERSIST,
        "    if len(sources) != 1:",
        "test_a_batch_that_mixes_the_two_sources_is_refused",
        GALLERY_TESTS,
    ),
    # -- the attribution lane (W7)
    guard(
        "img attrib: no fall-through past a present field",
        ATTRIB,
        "        if result is not None:\n            return result",
        "test_a_present_field_that_cannot_be_read_exactly_ends_the_row",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: a replacement character",
        ATTRIB,
        '    if "\\N{REPLACEMENT CHARACTER}" in author:',
        "test_a_present_field_that_cannot_be_read_exactly_ends_the_row",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: an undecoded HTML entity",
        ATTRIB,
        '    if any(_ENTITY.search(text) for text in (author, url or "")):',
        "test_an_entity_parse_attribution_would_store_literally_is_refused",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: 200 characters",
        ATTRIB,
        "    if len(author) > MAX_AUTHOR:",
        "test_a4_refuses_what_it_cannot_read_exactly",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: a non-name",
        ATTRIB,
        '    if author.strip().casefold().rstrip(".") in NOT_A_NAME:',
        "test_a4_refuses_what_it_cannot_read_exactly",
        ATTRIB_TESTS,
    ),
    Case(
        "img attrib: A3 needs exactly one user link",
        ATTRIB,
        "    if len(users) != 1:",
        "    if not users:",
        "test_an_own_work_credit_without_exactly_one_user_link_ends_the_row",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: A3 needs the own-work marker",
        ATTRIB,
        "    if 'class=\"int-own-work\"' not in credit:",
        "test_a_credit_without_the_own_work_marker_is_not_a3",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: A4 reads markup only as one link",
        ATTRIB,
        "    if re.search(r\"[\\[\\]{}<>|=]|''|~~~|https?://\", value):",
        "test_a4_refuses_what_it_cannot_read_exactly",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: one {{Information}} only",
        ATTRIB,
        "    if len(starts) != 1:",
        "test_an_empty_or_doubled_information_template_gives_no_route",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: one credit, one source",
        ATTRIB,
        '        if row.author_url not in (None, "") and row.author_url != found.author_url:',
        "test_a_row_whose_url_is_another_sources_is_listed_not_mixed",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: an author already set stops the lane",
        ATTRIB,
        '        if row.author not in (None, ""):',
        "test_a_row_that_already_has_an_author_stops_the_lane",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: author_url where the span names one",
        ATTRIB,
        '        if found.author_url is not None and row.author_url in (None, ""):',
        "test_the_plan_writes_author_and_its_url_with_a_pointer_to_the_evidence_line",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: the recheck compares revids",
        ATTRIB,
        '        if page.revid != record["revid"]:',
        "test_the_recheck_passes_on_the_same_page_and_names_every_drift",
        ATTRIB_TESTS,
    ),
    Case(
        "img attrib: maxlag is asked again",
        ATTRIB,
        '        if not answer.get("error"):\n            break',
        "        if True:\n            break",
        "test_a_maxlag_refusal_is_asked_again_and_then_raises",
        ATTRIB_TESTS,
    ),
    # -- the downloader's fetch rule (W2)
    guard(
        "img downloader: a small original is fetched itself",
        DOWNLOADER,
        "    if original_width <= FETCH_BUCKET:",
        "test_an_original_no_wider_than_the_bucket_is_fetched_itself",
        DL_TESTS,
    ),
    guard(
        "img downloader: an upscale is refused",
        DOWNLOADER,
        "            if img.width > original_width:",
        "test_an_image_wider_than_its_original_is_refused_as_an_upscale",
        DL_TESTS,
    ),
    guard(
        "img downloader: a non-200 raises",
        DOWNLOADER,
        "    if resp.status_code != 200:\n        raise DownloadError",
        "test_a_commons_400_is_an_error_and_not_a_skip",
        DL_TESTS,
    ),
    Case(
        "img downloader: never overwrite a file",
        DOWNLOADER,
        '        with dest_path.open("xb") as fh:',
        '        with dest_path.open("wb") as fh:',
        "test_an_existing_file_is_never_overwritten",
        DL_TESTS,
    ),
    guard(
        "img downloader: downscale to LOCAL_MAX_WIDTH",
        DOWNLOADER,
        "            if target != img.size:",
        "test_a_large_original_arrives_as_the_bucket_and_is_stored_at_1600",
        DL_TESTS,
    ),
    Case(
        "img downloader: failures are collected",
        DOWNLOADER,
        '                failures.append(FailedDownload(img.get("title", "?"), e.url, e.reason))',
        "                pass",
        "test_the_sequential_runner_returns_every_failure_by_name",
        DL_TESTS,
    ),
    guard(
        "img downloader: the run exits non-zero",
        DOWNLOADER,
        "    if failures:\n        for failure in failures:",
        "test_a_run_with_failures_exits_non_zero_and_lists_them",
        DL_TESTS,
    ),
    # -- the set-hero endpoint (W3)
    Case(
        "img set-hero: 1600 px",
        WIKI_ROUTE,
        "HERO_WIDTH = 1600",
        "HERO_WIDTH = 800",
        "test_a_wide_source_becomes_a_1600_px_hero_with_its_aspect_kept",
        HERO_TESTS,
    ),
    Case(
        "img set-hero: never upscale",
        WIKI_ROUTE,
        "    if img.width > HERO_WIDTH:",
        "    if img.width != HERO_WIDTH:",
        "test_a_source_narrower_than_the_hero_width_is_never_upscaled",
        HERO_TESTS,
    ),
    Case(
        "img hero-status: the row's own file",
        WIKI_ROUTE,
        '            "path": f"/data/images/wiki/{sid_short}/{row[3]}",',
        '            "path": f"/data/images/wiki/{sid_short}/hero.webp",',
        "test_hero_status_names_the_hero_rows_own_file",
        HERO_TESTS,
    ),
    # -- the shorts selector on the strict VLM call (W14)
    Case(
        "img shorts: auth and quota raise at once",
        SHORTS,
        "        except VLM_NOT_RETRIED:\n            raise\n",
        "",
        "test_a_dead_key_or_a_spent_budget_raises_at_once",
        SHORTS_TESTS,
    ),
    guard(
        "img shorts: the last failure raises",
        SHORTS,
        "            if attempt == VLM_ATTEMPTS:\n                exc.add_note(",
        "test_a_failure_that_outlasts_the_retries_raises_and_names_the_image",
        SHORTS_TESTS,
    ),
    guard(
        "img shorts: no verdict raises",
        SHORTS,
        "        if attempt == VLM_ATTEMPTS:\n            raise NoVerdictError(",
        "test_an_answer_that_never_carries_a_json_verdict_stops_the_run",
        SHORTS_TESTS,
    ),
    Case(
        "img shorts: the strict call",
        SHORTS,
        "            raw = mm.minimax_vlm_strict(client, vlm_bytes(path), prompt)",
        "            raw = mm.minimax_vlm(client, vlm_bytes(path), prompt)",
        "test_a_2xx_whose_base_resp_reports_an_error_is_an_error_not_a_verdict",
        SHORTS_TESTS,
    ),
    # -- the static export's site image (W15)
    Case(
        "img export: an excluded image is never the site image",
        EXPORTER,
        "WHERE site_id = us.id AND is_excluded IS NOT TRUE",
        "WHERE site_id = us.id",
        "test_the_exported_site_image_is_never_an_excluded_row",
        EXPORT_TESTS,
    ),
    # -- review of 2026-09-23: the DO block, condition by condition
    Case(
        "img chunk: guard 2, the image row lives on the named site",
        CHUNK,
        "     WHERE p.table_name = 'wiki_images' AND (w.id IS NULL OR w.site_id IS DISTINCT FROM"
        " p.site_id);",
        "     WHERE false;",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: guard 3 compares the old value",
        CHUNK,
        "       AND t.{column}::text IS DISTINCT FROM p.old_value;",
        "       AND false;",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: exactly the planned rows moved",
        CHUNK,
        "    IF moved <> expected THEN",
        "    IF false THEN",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: invariant 1 compares the new value",
        CHUNK,
        "       AND t.{column}::text IS DISTINCT FROM p.new_value;",
        "       AND false;",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: invariant 2 compares values and keys",
        CHUNK,
        "     WHERE l.id IS NULL OR l.old_value IS DISTINCT FROM p.old_value\n"
        "        OR l.new_value IS DISTINCT FROM p.new_value OR l.change_key IS DISTINCT FROM"
        " p.change_key;",
        "     WHERE l.id IS NULL;",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: invariant 3 counts the whole stamp",
        CHUNK,
        "    IF bad > 0 OR (SELECT count(*) FROM remediation_change_log WHERE run_stamp = {s})"
        " <> expected THEN",
        "    IF bad > 0 THEN",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: invariant 5 reads excluded heroes",
        CHUNK,
        "     WHERE w.site_id IN (SELECT site_id FROM {PLAN_TABLE}) AND w.is_hero AND"
        " w.is_excluded IS TRUE;",
        "     WHERE false;",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: invariant 6 knows the live sites",
        CHUNK,
        "   WHERE w.site_id IN (SELECT site_id FROM {PLAN_TABLE}) AND w.is_excluded IS NOT TRUE;",
        "   WHERE false;",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: invariant 7 reads the vocabulary",
        CHUNK,
        "       AND w.image_kind IS NOT NULL AND w.image_kind NOT IN ({vocab});",
        "       AND false;",
        DO_BLOCK,
        CHUNK_TESTS,
    ),
    # -- the read-back: the invariant read, the journal read, and the settling
    Case(
        "img chunk: after-read, two heroes",
        CHUNK,
        "     GROUP BY w.site_id HAVING count(*) FILTER (WHERE w.is_hero) > 1) x)::int AS"
        " sites_with_two_heroes,",
        "     GROUP BY w.site_id HAVING count(*) FILTER (WHERE w.is_hero) > 9) x)::int AS"
        " sites_with_two_heroes,",
        INVARIANTS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: after-read, excluded heroes",
        CHUNK,
        "     AND w.is_hero AND w.is_excluded IS TRUE)::int AS excluded_heroes,",
        "     AND w.is_hero)::int AS excluded_heroes,",
        INVARIANTS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: after-read, kinds",
        CHUNK,
        "     AND w.image_kind IS NOT NULL AND w.image_kind NOT IN ({vocab}))::int AS"
        " kinds_outside_vocabulary,",
        "     AND w.image_kind IS NOT NULL)::int AS kinds_outside_vocabulary,",
        INVARIANTS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: after-read, the curated source",
        CHUNK,
        "     AND u.source_id <> {source})::int AS sites_outside_the_curated_source",
        "     AND u.source_id <> 'lyra')::int AS sites_outside_the_curated_source",
        INVARIANTS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: the journal read selects test id and confidence",
        CHUNK,
        '        " new_value, change_key, test_id, confidence FROM remediation_change_log"',
        '        " new_value, change_key FROM remediation_change_log"',
        JOURNAL,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: readback compares test id and confidence",
        CHUNK,
        '            "test_id": lane.test_id,\n            "confidence": lane.confidence,\n',
        "",
        JOURNAL,
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: a journal row held twice",
        CHUNK,
        "        if ident in journal:",
        "test_the_readback_names_a_journal_row_it_holds_twice",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: a partial journal is unknown",
        CHUNK,
        "    if count != len(chunk.changes):",
        "test_a_journal_that_holds_part_of_the_chunk_is_an_unknown_outcome",
        CHUNK_TESTS,
    ),
    # -- the plan files and the change model
    guard(
        "img chunk: the change key is the lane's",
        CHUNK,
        '        if row["change_key"] != change_key(lane, change):',
        "test_a_plan_record_whose_change_key_this_lane_does_not_make_is_refused",
        CHUNK_TESTS,
    ),
    guard(
        "img chunk: a rule is a rule id",
        CHUNK,
        "    if not TOKEN_RE.fullmatch(change.rule.lower()):",
        EXPRESS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: a reason carries no control character",
        CHUNK,
        '    _no_control(change.reason, what="a reason")',
        "    pass",
        EXPRESS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: line separators are control characters",
        CHUNK,
        "    return any(ord(ch) < 32 or 127 <= ord(ch) <= 159 or ch in LINE_BREAKERS for ch in value)",
        "    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)",
        EXPRESS,
        CHUNK_TESTS,
    ),
    Case(
        "img chunk: a plan is split at newlines only",
        CHUNK,
        '    for lineno, line in enumerate(pv.jsonl_lines(plan_path.read_text(encoding="utf-8")),'
        " start=1):",
        '    for lineno, line in enumerate(plan_path.read_text(encoding="utf-8").splitlines(),'
        " start=1):",
        "test_a_delivered_value_with_a_line_separator_is_refused_by_name_not_by_traceback",
        CHUNK_TESTS,
    ),
    # -- persist_verdicts: the kind test and the JSON-lines readers
    guard(
        "img pv: kind_test reads the vocabulary",
        PERSIST,
        "    if not kinds or any(kind not in VOCAB for kind in kinds):",
        "test_kind_test_refuses_what_is_not_a_set_of_image_kinds",
        GALLERY_TESTS,
    ),
    Case(
        "img pv: JSON lines split at newlines only",
        PERSIST,
        '    return text.split("\\n")',
        "    return text.splitlines()",
        "test_a_plan_record_with_a_line_separator_is_read_whole",
        GALLERY_TESTS,
    ),
    Case(
        "img pv: production rows split at newlines only",
        PERSIST,
        "    for line in jsonl_lines(proc.stdout):",
        "    for line in proc.stdout.splitlines():",
        "test_a_production_row_with_a_line_separator_is_read_whole",
        GALLERY_TESTS,
    ),
    # -- the attribution lane
    guard(
        "img attrib: wiki markup is not a name",
        ATTRIB,
        '    if any(mark in text for text in (author, url or "") for mark in WIKI_MARKUP):',
        "test_wiki_markup_in_a_rendered_field_is_not_a_name",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: a Wikimedia link must be a user page",
        ATTRIB,
        "    if url is not None and names_the_platform(url):",
        "test_a_link_into_wikimedia_that_is_not_a_user_page_names_the_platform",
        ATTRIB_TESTS,
    ),
    Case(
        "img attrib: a user page does not name the platform",
        ATTRIB,
        "    return not _USER_PATH.fullmatch(urllib.parse.unquote(parts.path))",
        "    return True",
        "test_a_user_page_or_the_authors_own_site_is_the_authors_link",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: only a Wikimedia host names the platform",
        ATTRIB,
        '    if not any(host == domain or host.endswith(f".{domain}") for domain in WIKIMEDIA_DOMAINS):',
        "test_a_user_page_or_the_authors_own_site_is_the_authors_link",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: a control character or line separator",
        ATTRIB,
        '    if any(CW.has_control(text) for text in (author, url or "")):',
        "test_a_control_character_or_line_separator_in_the_span_is_refused",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: a plain web address",
        ATTRIB,
        r"""    if url is not None and not re.fullmatch(r"https?://[^\s\"'<>]+", url):""",
        "test_a_link_that_is_not_a_plain_web_address_is_refused",
        ATTRIB_TESTS,
    ),
    Case(
        "img attrib: A3 without one user link ends the row",
        ATTRIB,
        "        return Refused(\n"
        '            "A3", f"the own-work credit carries {len(users)} user links, not exactly one",'
        " credit\n"
        "        )",
        "        return None",
        "test_an_own_work_credit_without_exactly_one_user_link_ends_the_row",
        ATTRIB_TESTS,
    ),
    Case(
        "img attrib: A3's refusal ends the row",
        ATTRIB,
        '    return _read("A3", "Credit", anchor, anchor)',
        '    found = _read("A3", "Credit", anchor, anchor)\n'
        "    return found if isinstance(found, Found) else None",
        "test_an_own_work_user_link_that_cannot_be_read_ends_the_row",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: a batch answer carries its query",
        ATTRIB,
        '    if "query" not in answer:',
        "test_a_batch_answer_without_a_query_stops_the_lane",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: one revision and its imageinfo",
        ATTRIB,
        "        if len(revisions) != 1 or info is None:",
        "test_a_page_without_one_revision_and_its_imageinfo_is_named",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: the recheck hashes the stored span",
        ATTRIB,
        '        if sha256_text(str(record["span"])) != record["span_sha256"]:',
        "test_the_recheck_passes_on_the_same_page_and_names_every_drift",
        ATTRIB_TESTS,
    ),
    guard(
        "img attrib: an unclosed template",
        ATTRIB,
        "    if body is None:",
        "test_an_unclosed_information_template_gives_no_route",
        ATTRIB_TESTS,
    ),
    Case(
        "img attrib: evidence is split at newlines only",
        ATTRIB,
        '        json.loads(line) for line in pv.jsonl_lines(path.read_text(encoding="utf-8")) if'
        " line.strip()",
        '        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if'
        " line.strip()",
        "test_the_evidence_file_is_read_back_whole_when_a_span_carries_a_line_separator",
        ATTRIB_TESTS,
    ),
    # -- the downloader's site run
    Case(
        "img downloader: answers keyed by the asked title",
        DOWNLOADER,
        "        page = pages.get(dereference(title, normalized))",
        "        page = pages.get(title)",
        "test_an_underscore_media_list_title_is_stored_with_its_width_and_a_bare_url",
        DL_TESTS,
    ),
    Case(
        "img downloader: the original URL is parse_attribution's",
        DOWNLOADER,
        '            "original_url": original["original_url"],',
        '            "original_url": info.get("url"),',
        "test_the_metadata_batch_answers_under_the_title_that_was_asked",
        DL_TESTS,
    ),
    guard(
        "img downloader: an upload original has no query",
        DOWNLOADER,
        "    if parsed.query or parsed.fragment:",
        "test_what_has_no_valid_fetch_is_refused_by_name",
        DL_TESTS,
    ),
    guard(
        "img downloader: the byte cap",
        DOWNLOADER,
        "    if len(raw_bytes) > MAX_RAW_BYTES:",
        "test_an_answer_over_the_byte_limit_is_refused",
        DL_TESTS,
    ),
    Case(
        "img downloader: the rows are read with --force too",
        DOWNLOADER,
        "        rows = session.execute(\n"
        '            text("SELECT original_url, filename FROM wiki_images WHERE site_id = :sid"),',
        "        rows = [] if force else session.execute(\n"
        '            text("SELECT original_url, filename FROM wiki_images WHERE site_id = :sid"),',
        "test_a_file_on_disk_that_a_row_names_is_done",
        DL_TESTS,
    ),
    guard(
        "img downloader: a file no row names is a failure",
        DOWNLOADER,
        "        if on_disk and not registered:",
        "test_a_file_on_disk_that_no_row_names_is_a_named_failure",
        DL_TESTS,
    ),
    guard(
        "img downloader: an insert failure is named",
        DOWNLOADER,
        '            if not (isinstance(exc, IntegrityError) and "uq_wiki_image_site_url" in str(exc)):',
        "test_an_insert_that_fails_is_a_named_failure_and_moves_no_thumbnail",
        DL_TESTS,
    ),
    Case(
        "img downloader: no site-level catch",
        DOWNLOADER,
        "        count, failures = process_site(\n"
        "            site, dry_run=dry_run, max_per_category=max_per_category, force=force\n"
        "        )",
        "        try:\n"
        "            count, failures = process_site(\n"
        "                site, dry_run=dry_run, max_per_category=max_per_category, force=force\n"
        "            )\n"
        "        except Exception:\n"
        "            continue",
        "test_an_error_that_is_not_an_image_failure_stops_the_run",
        DL_TESTS,
    ),
    # -- T09's historic caps, bound to the snapshot they made
    guard(
        "img t09: the caps are bound to their snapshot",
        T09,
        "    if datetime.fromisoformat(exported_at) >= HISTORIC_CAPS_UNTIL:",
        "test_the_800_and_1600_px_notes_are_refused_for_a_later_snapshot",
        T09_TESTS,
    ),
    guard(
        "img t09: a snapshot without an export time",
        T09,
        "    if exported_at is None:",
        "test_the_800_and_1600_px_notes_are_refused_for_a_later_snapshot",
        T09_TESTS,
    ),
]
CASES += IMAGE_CASES


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
    # `mutation_sweep.py [label substring ...]` runs the cases whose label holds any of them,
    # like the phase-3 sweep; no argument runs them all.
    wanted = [c for c in CASES if not sys.argv[1:] or any(a in c.label for a in sys.argv[1:])]
    if not wanted:
        sys.exit(f"no case label contains any of {sys.argv[1:]}")
    sys.exit(main(wanted))
