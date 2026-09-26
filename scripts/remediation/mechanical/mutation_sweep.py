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
        "    if commits != 1:\n        raise PlanError(",
        "test_a_statement_without_a_commit_cannot_be_rehearsed",
    ),
    Case(
        "rollback rehearsal must commit",
        APPLY,
        '    head = _before_the_one_commit(sql, "ROLLBACK.sql")',
        '    head = sql.partition("\\nCOMMIT;\\n")[0]',
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
                '    sql = verify_pinned(\n        out / "APPLY.sql", plan_path=plan_path, expected=apply_statement(records, lane)\n    )\n    # The undo',
                '    sql = (out / "APPLY.sql").read_text(encoding="utf-8")\n    # The undo',
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
        r'CARD_STATS_LANE = re.compile(r"^card-stats-(\d{4}-\d{2}-\d{2}[a-z]?)\Z")',
        r'CARD_STATS_LANE = re.compile(r"^card-stats-(.+)\Z")',
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
                "    if values[filled_side] is None and not cell.clears:",
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
                '    if not path.exists():\n        raise PlanError(f"{path} is missing - the reviewed decisions',
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
            # ---- 2026-09-23: the owner-case duplicate list (bcases/DUPLICATES.jsonl)
            (
                "the duplicate list exists",
                '    if not path.exists():\n        raise PlanError(f"{path} is missing - the owner-case',
                "test_a_missing_list_is_refused",
            ),
            (
                "a listed row is a UUID",
                "            if not UUID_RE.match(sid):",
                "test_a_malformed_list_is_refused",
            ),
            (
                "a listed loser has another row as survivor and evidence",
                "        if listed.loser == listed.survivor or not listed.evidence:",
                "test_a_malformed_list_is_refused",
            ),
            ("a loser is listed once", "    if twice:", "test_a_malformed_list_is_refused"),
            (
                "the held file exists",
                '    if not path.exists():\n        raise PlanError(f"{path} is missing - the pairs held',
                "test_the_held_file_names_every_site_of_its_groups",
            ),
            (
                "a held site is a UUID",
                "            if not UUID_RE.match(str(sid)):",
                "test_the_held_file_names_every_site_of_its_groups",
            ),
            (
                "a listed row is curated",
                "        if loser is None or survivor is None:",
                "test_a_listed_site_that_is_not_curated_is_refused",
            ),
            (
                "a listed pair still shares the item it names",
                '        if qid is None or _item_of(survivor) != qid or f"both rows carry {qid};" not in claim:',
                "test_a_listed_pair_that_no_longer_shares_its_item_is_refused",
            ),
            (
                "a listed pair is within the list's 2 km",
                "        if metres > DUP_MAX_M:",
                "test_a_listed_pair_now_further_apart_than_the_list_allows_is_refused",
            ),
            (
                "no pair held for the owner",
                "        if {dup.loser, dup.survivor} & held:",
                "test_a_pair_held_for_the_owner_is_never_retired",
            ),
            (
                "the listed evidence goes into the journal",
                "        if dup.listed:",
                "test_a_listed_loser_is_retired_as_a_duplicate_of_its_survivor",
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
            (
                "a pair found and listed is one retirement",
                "        elif own.survivor == dup.survivor:",
                "        elif False:",
                "test_a_pair_found_and_listed_is_one_retirement_with_both_evidences",
            ),
            (
                "a disputed loser is not retired",
                "    for loser in sorted(set(by_loser) - disputed):",
                "    for loser in sorted(set(by_loser)):",
                "test_a_loser_the_two_name_with_different_survivors_is_refused",
            ),
            (
                "the planner reads the list",
                "                listed=load_listed_duplicates(DUPLICATES_LIST),",
                "                listed=(),",
                "test_the_planner_reads_the_list_and_the_held_pairs",
            ),
            (
                "the planner reads the held pairs",
                "                held=load_held_sites(DUPLICATES_HELD),",
                "                held=frozenset(),",
                "test_the_planner_reads_the_list_and_the_held_pairs",
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
                '        if problem is not None:\n            return verdict(False, "evidence-not-found", problem)',
                "test_evidence_that_is_not_where_it_says_refuses",
            ),
            # ---- 2026-09-23: the second list - the re-review, the journal quote, the period label
            (
                "the re-review file exists",
                '    if not path.exists():\n        raise PlanError(f"{path} is missing - the re-review',
                "test_the_re_review_file_is_read_by_change_key_once_each",
            ),
            (
                "the re-review decides a write once",
                '        if row["change_key"] in rows:',
                "test_the_re_review_file_is_read_by_change_key_once_each",
            ),
            (
                "a re-review quote names a row of the re-review",
                "    if row is None:",
                "test_a_re_review_row_that_did_not_reverse_this_write_refuses",
            ),
            (
                "the re-review decided to reverse",
                '    if row["decision"] != "reverse":',
                "test_a_re_review_row_that_did_not_reverse_this_write_refuses",
            ),
            (
                "the re-review row is the journal row's write",
                "    if decided != written:",
                "test_a_re_review_row_that_did_not_reverse_this_write_refuses",
            ),
            (
                "a re-review problem refuses the quote",
                "        if problem is not None:\n            return problem",
                "test_a_re_review_row_that_did_not_reverse_this_write_refuses",
            ),
            (
                "the undone row carries evidence",
                '        if entry.get("evidence") is None:',
                "test_a_journal_row_without_evidence_refuses",
            ),
            (
                "a restored label is its start's bucket",
                "        if v.new_value != bucket:",
                "test_a_label_whose_start_is_not_restored_is_refused",
            ),
            (
                "a start never leaves its label behind",
                "        if _bucket(v.new_value) != label:",
                "test_a_start_that_would_leave_its_label_behind_is_refused",
            ),
            (
                "a pair broken before the list does not hold a start",
                "        if _bucket(site[PERIOD_START]) != site[PERIOD_NAME]:",
                "test_a_label_that_was_not_the_bucket_before_does_not_hold_the_start",
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
                '    if not path.exists():\n        raise PlanError(f"{path} is missing - the reviewed reasons',
                "test_a_missing_reasons_file_is_refused",
            ),
            (
                "a reversal needs a reason and quotes",
                "        if not r.reason or not r.quotes or any(not q.text.strip() for q in r.quotes):",
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
            (
                "a journal quote names no other row",
                '    elif kind == "journal" and not ref:',
                '    elif kind == "journal":',
                "test_a_journal_quote_names_no_other_row",
            ),
            (
                "a restored label follows the list's start",
                "            starts[v.site_id].new_value if v.site_id in starts else sites[v.site_id][PERIOD_START]",
                "            sites[v.site_id][PERIOD_START]",
                "test_a_start_and_its_label_go_back_together",
            ),
            (
                "a start is checked against the list's label",
                "        label = names[v.site_id].new_value if v.site_id in names else site[PERIOD_NAME]",
                "        label = site[PERIOD_NAME]",
                "test_a_start_and_its_label_go_back_together",
            ),
            (
                "the list keeps the period label",
                "    verdicts = keep_the_period_label(verdicts, sites)",
                "    pass",
                "test_a_start_that_would_leave_its_label_behind_is_refused",
            ),
            (
                "the period pair is read for every site",
                "    return (*lane.columns, *(c for c in (PERIOD_START, PERIOD_NAME) if c not in lane.columns))",
                "    return lane.columns",
                "test_load_state_reads_the_row_the_site_and_the_chain",
            ),
            (
                "a list that quotes the re-review is found",
                '    return any(q.source.partition(":")[0] == REREVIEW_KIND for r in reasons for q in r.quotes)',
                "    return False",
                "test_only_a_list_that_cites_the_re_review_needs_it",
            ),
            (
                "--lane names a reversal lane",
                '    ap.add_argument("--lane", required=True, choices=sorted(REVERSAL_LISTS))',
                '    ap.add_argument("--lane", required=True)',
                "test_the_lane_is_named_and_must_be_a_reversal_lane",
            ),
            (
                "--write reads the re-review copy",
                "            rereview = load_rereview(out / REREVIEW_FILE) if cites_the_rereview(reasons) else {}",
                "            rereview = {}",
                "test_write_plans_a_rereview_quoted_list_from_the_lane_s_copy",
            ),
        )
    ),
    Case(
        "reversal: the second list reads back the period pair",
        LANE,
        "        (\n            _PERIOD_MISMATCH.metric,\n            f\"FROM unified_sites WHERE source_id = 'ancient_nerds' AND {_PERIOD_MISMATCH.predicate}\",\n        ),\n    ],\n)\n\n#: Each reversal lane",
        "    ],\n)\n\n#: Each reversal lane",
        "test_the_second_list_reads_back_the_period_pair_and_its_own_residual",
        REVERSAL_TESTS,
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
        PROD_WRITE,  # moved from persist_verdicts on 2026-09-25 (audit m9); pv re-exports it
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


# ------------------------------------------------------------ journal-reversal-3 (2026-09-25)
#: The third reversal list: the `opus:<change_key>` source kind (`reversal.load_opus`,
#: `_opus_text`), the lane's registration in `lane.py` and the list's builder (`reversal_opus.py`).
#: A block of its own after the image lanes; every label starts with "reversal 3" -
#: `mutation_sweep.py "reversal 3"` runs exactly these.
REVERSAL_OPUS = MECHANICAL / "reversal_opus.py"
REVERSAL_OPUS_TESTS = "tests/remediation/test_mechanical_reversal_opus.py"
REVERSAL_3_CASES: list[Case] = [
    *(
        guard(f"reversal 3: {label}", REVERSAL, needle, test, REVERSAL_TESTS)
        for label, needle, test in (
            (
                "an opus quote names a row of the audit",
                "    if judged is None:",
                "test_a_decision_that_did_not_revert_this_write_refuses",
            ),
            (
                "the audit decided a reversal",
                "    if not judged.reversal:",
                "test_a_decision_that_did_not_revert_this_write_refuses",
            ),
            (
                "the audit judged the journal row's write",
                "    if audited != wrote:",
                "test_a_decision_that_did_not_revert_this_write_refuses",
            ),
            (
                "an audit problem refuses the quote",
                "        if unjudged is not None:\n            return unjudged",
                "test_a_decision_that_did_not_revert_this_write_refuses",
            ),
            (
                "an opus quote's page is the audit's decisions",
                "    if kind == OPUS_KIND:\n        return OPUS_URL",
                "test_the_audits_decision_to_revert_is_the_evidence",
            ),
            (
                "the audit's decisions exist",
                '    if not path.exists():\n        raise PlanError(\n            f"{path} is missing - the Opus',
                "test_the_decisions_file_is_read_by_change_key_once_each",
            ),
            (
                "the audit decides a write once",
                "        if key in out:",
                "test_the_decisions_file_is_read_by_change_key_once_each",
            ),
            (
                "a basis names a verdict file of the audit",
                "    if not OPUS_VERDICT_FILE.fullmatch(name):",
                "test_a_basis_names_a_verdict_file_of_the_audit_only",
            ),
            (
                "a basis the verdict file holds",
                "    if verdict is None:",
                "test_a_basis_the_verdict_file_does_not_hold_is_refused",
            ),
            (
                "the verdict file holds the basis's verdict",
                '            if verdict["verdict"] != basis["verdict"]:',
                "test_a_basis_the_verdict_file_does_not_hold_is_refused",
            ),
            (
                "the quote check is the verdict's own",
                '            if [c["source"] for c in checked] != [q["source"] for q in verdict["quotes"]]:',
                "test_the_quote_check_must_be_the_verdicts_own",
            ),
        )
    ),
    *(
        Case(f"reversal 3: {label}", REVERSAL, old, new, test, REVERSAL_TESTS)
        for label, old, new, test in (
            (
                "an opus quote is a source the lane checks",
                "    elif kind == OPUS_KIND:",
                "    elif False:",
                "test_the_audits_decision_to_revert_is_the_evidence",
            ),
            (
                "the change key is part of the write",
                "    audited = (judged.change_key, judged.site_id, judged.column)",
                '    audited = (entry["change_key"], judged.site_id, judged.column)',
                "test_a_decision_on_another_write_of_the_same_cell_refuses",
            ),
            (
                "a keep verdict decides a revert",
                '            if basis["verdict"] == OPUS_KEEP or not basis["counted"]:',
                '            if not basis["counted"]:',
                "test_a_quote_the_deciding_verdicts_do_not_carry_refuses",
            ),
            (
                "a verdict that does not count carries quotes",
                '            if basis["verdict"] == OPUS_KEEP or not basis["counted"]:',
                '            if basis["verdict"] == OPUS_KEEP:',
                "test_a_verdict_that_does_not_count_carries_no_quote",
            ),
            (
                "a quote the audit's check did not find",
                '                if c["outcome"] == OPUS_FOUND',
                "                if True",
                "test_a_quote_the_audits_check_did_not_find_is_none",
            ),
            (
                "a list that quotes the audit is found",
                '    return any(q.source.partition(":")[0] == OPUS_KIND for r in reasons for q in r.quotes)',
                "    return False",
                "test_only_a_list_that_cites_the_opus_audit_needs_it",
            ),
            (
                "a quote is checked against the audit",
                "        problem = quote_problem(quote, reason, cell, pages, gold, rereview, opus)",
                "        problem = quote_problem(quote, reason, cell, pages, gold, rereview)",
                "test_the_audits_decision_to_revert_is_the_evidence",
            ),
            (
                "the plan passes the audit on",
                "            rereview=rereview,\n            opus=opus,\n        )",
                "            rereview=rereview,\n        )",
                "test_a_start_the_audit_reverts_and_its_label_go_back_together",
            ),
            (
                "--write reads the audit",
                "            opus = load_opus(OPUS_AUDIT) if cites_the_opus_audit(reasons) else NO_OPUS",
                "            opus = NO_OPUS",
                "test_write_plans_an_opus_quoted_list_from_the_audit_files",
            ),
            (
                "--write plans on the audit",
                "                built_at=_now(),\n                opus=opus,",
                "                built_at=_now(),",
                "test_write_plans_an_opus_quoted_list_from_the_audit_files",
            ),
        )
    ),
    # ------------------------------------------------------------------- the lane (lane.py)
    *(
        Case(f"reversal 3: {label}", LANE, old, new, test, REVERSAL_TESTS)
        for label, old, new, test in (
            (
                "the lane writes country",
                '    Column("period_name", "character varying", max_chars=100),\n'
                '    Column("country", "character varying", max_chars=100),\n)',
                '    Column("period_name", "character varying", max_chars=100),\n)',
                "test_the_lane_writes_every_column_the_audit_reverts_and_the_labels",
            ),
            (
                "the lane is a reversal list",
                "REVERSAL_LISTS[REVERSAL_3.name] = REVERSAL_3_JOURNAL_IDS",
                "pass",
                "test_the_lane_writes_every_column_the_audit_reverts_and_the_labels",
            ),
            (
                "the lane is registered",
                "LANES[REVERSAL_3.name] = REVERSAL_3",
                "pass",
                "test_the_lane_writes_every_column_the_audit_reverts_and_the_labels",
            ),
            (
                "the lane has its read-back",
                "LANE_READBACKS[REVERSAL_3.name] = REVERSAL_3_READBACK",
                "pass",
                "test_the_lane_reads_back_its_residual_the_period_pair_and_the_card_country",
            ),
            (
                "the lane reads back the period pair",
                "        (\n            _PERIOD_MISMATCH.metric,\n"
                "            f\"FROM unified_sites WHERE source_id = 'ancient_nerds' AND "
                '{_PERIOD_MISMATCH.predicate}",\n        ),\n        (\n'
                '            "card_stats rows whose civilization differs from the site country",',
                '        (\n            "card_stats rows whose civilization differs from the site country",',
                "test_the_lane_reads_back_its_residual_the_period_pair_and_the_card_country",
            ),
            (
                "the lane reads back the card country",
                '        (\n            "card_stats rows whose civilization differs from the site country",\n'
                '            "FROM card_stats cs JOIN unified_sites u ON u.id = cs.site_id "\n'
                "            \"WHERE u.source_id = 'ancient_nerds' AND cs.civilization IS DISTINCT FROM "
                'u.country",\n        ),\n    ],\n)\nREVERSAL_LISTS[REVERSAL_3.name]',
                "    ],\n)\nREVERSAL_LISTS[REVERSAL_3.name]",
                "test_the_lane_reads_back_its_residual_the_period_pair_and_the_card_country",
            ),
        )
    ),
    # ------------------------------------------------------ the list's builder (reversal_opus.py)
    *(
        guard(f"reversal 3 list: {label}", REVERSAL_OPUS, needle, test, REVERSAL_OPUS_TESTS)
        for label, needle, test in (
            (
                "only a phase-3 change key is sent",
                "        if not CHANGE_KEY.fullmatch(key):",
                "test_a_change_key_that_is_not_a_phase_3_key_is_never_sent",
            ),
            (
                "no start reads no label",
                "    if not sites:\n        return []",
                "test_no_start_that_changes_bucket_reads_no_label",
            ),
            (
                "a change key is one journal row",
                "    if len(found) != 1:",
                "test_a_change_key_that_is_not_exactly_one_journal_row_is_refused",
            ),
            (
                "the journal row is the write the input names",
                "    if wrote != named:",
                "test_a_journal_row_that_is_not_the_write_the_audit_judged_is_refused",
            ),
            (
                "two label rows citing one start",
                "    if len(found) > 1:",
                "test_two_label_rows_citing_one_start_are_refused",
            ),
            (
                "a start within its bucket takes no label",
                "        if not changes_bucket(r):\n            continue",
                "test_a_start_within_its_bucket_takes_no_label",
            ),
            (
                "a journal row named twice",
                "    if len(set(ids)) != len(ids):",
                "test_a_journal_row_named_twice_is_refused",
            ),
        )
    ),
    *(
        Case(f"reversal 3 list: {label}", REVERSAL_OPUS, old, new, test, REVERSAL_OPUS_TESTS)
        for label, old, new, test in (
            (
                "the write is not unified_sites",
                '    named = ("unified_sites", r["column"], r["site_id"], r["old_value"], r["new_value"])',
                '    named = (row["table_name"], r["column"], r["site_id"], r["old_value"], r["new_value"])',
                "test_a_journal_row_that_is_not_the_write_the_audit_judged_is_refused",
            ),
            (
                "a start that keeps its bucket changes it",
                '    return r["column"] == "period_start" and _bucket(r["old_value"]) != _bucket(r["new_value"])',
                '    return r["column"] == "period_start" and _bucket(r["old_value"]) == _bucket(r["new_value"])',
                "test_a_start_that_changes_bucket_takes_the_label_the_period_name_lane_derived",
            ),
            (
                "the label cites any start",
                '        if e.get("source") == cites',
                '        if str(e.get("source")).startswith("remediation_change_log:")',
                "test_only_the_label_row_that_cites_the_start_s_own_write_is_taken",
            ),
            (
                "the label is any site's",
                '        if row["row_pk"] == r["site_id"]',
                "        if True",
                "test_a_label_row_of_another_site_is_never_taken",
            ),
            (
                "an unlabelled start is not reported",
                '            unlabelled.append(r["name"])',
                "            pass",
                "test_only_the_label_row_that_cites_the_start_s_own_write_is_taken",
            ),
            (
                "the reasons are not sorted by journal row",
                '            "reversals": sorted(entries, key=lambda e: e["journal_id"]),',
                '            "reversals": entries,',
                "test_every_audit_row_is_undone_by_its_journal_row_on_its_deciding_quotes",
            ),
            (
                "labels are read for every row",
                '        labels = read_labels(reader, [r["site_id"] for r in bucket_changes(rows)])',
                '        labels = read_labels(reader, [r["site_id"] for r in rows])',
                "test_write_builds_the_reasons_and_the_list_from_the_input",
            ),
            (
                "the input's digest is not recorded",
                "        sha = hashlib.sha256(data).hexdigest()",
                '        sha = "0" * 64',
                "test_write_builds_the_reasons_and_the_list_from_the_input",
            ),
            (
                "the list module is not written",
                "    args.module.write_text(render_list_module(built.ids, sha), "
                'encoding="utf-8", newline="\\n")',
                "    pass",
                "test_write_builds_the_reasons_and_the_list_from_the_input",
            ),
        )
    ),
]
CASES += REVERSAL_3_CASES


# ------------------------------------------------------------- the wrong-both lane (2026-09-25)
#: The correction lane of RULES.md rule 5 (`wrong_both.py`) and its registration in `lane.py`. A
#: block of its own after journal-reversal-3's; every label starts with "wrong-both" -
#: `mutation_sweep.py wrong-both` runs exactly these.
WRONG_BOTH = MECHANICAL / "wrong_both.py"
WRONG_BOTH_TESTS = "tests/remediation/test_mechanical_wrong_both.py"
_YEAR_IN = "test_a_year_with_its_era_states_it"
_YEAR_OUT = "test_a_year_without_its_era_or_in_another_does_not"
_TYPE_IN = "test_a_term_the_normalizer_resolves_to_the_type_states_it"
_COUNTRY_OUT = "test_a_country_outside_the_convention_is_named"
_WRITTEN = "test_a_row_whose_judges_agree_and_whose_quote_states_the_value_is_written"
WRONG_BOTH_CASES: list[Case] = [
    *(
        guard(f"wrong-both: {label}", WRONG_BOTH, needle, test, WRONG_BOTH_TESTS)
        for label, needle, test in (
            (
                "the verdict file holds the basis's verdict",
                '    if verdict["verdict"] != basis["verdict"]:',
                "test_a_basis_whose_verdict_file_holds_another_verdict_is_refused",
            ),
            (
                "the quote check is the verdict's own",
                '    if [c["source"] for c in checked] != [q["source"] for q in verdict["quotes"]]:',
                "test_a_quote_check_that_is_not_the_verdicts_own_is_refused",
            ),
            (
                "the decisions exist",
                '    if not path.exists():\n        raise PlanError(f"{path} is missing',
                "test_missing_decisions_are_refused",
            ),
            (
                "a decision once",
                "        if key in seen:",
                "test_a_decision_named_twice_is_refused",
            ),
            (
                "a candidate carries a wrong-both",
                "        if not any(j.verdict == WRONG_BOTH_VERDICT for j in judges):",
                "test_every_row_with_a_wrong_both_on_its_route_is_a_candidate_with_its_judges",
            ),
            (
                "the year's era",
                '        if (match["bc"] is not None) == (year < 0):',
                _YEAR_IN,
            ),
            (
                "AD before the year",
                "    if year > 0:\n        for match in _PREFIX.finditer(text):",
                _YEAR_IN,
            ),
            (
                "the year after AD is the year",
                '            if int(match["n"].replace(",", "")) == year:',
                _YEAR_IN,
            ),
            (
                "a quote from the row's evidence file is about the site",
                "    if not Q.is_url(source):\n        return EVIDENCE_FILE",
                _WRITTEN,
            ),
            (
                "a page that cannot be read refuses",
                "    if read.failure:\n        raise PlanError(",
                "test_a_page_the_audit_found_the_quote_on_must_still_hold_it",
            ),
            (
                "a page without the name near the quote",
                "            if word is None:\n                return None",
                "test_a_page_quote_that_stands_far_from_the_site_s_name_is_no_evidence",
            ),
            (
                "a country spelling the project carries",
                "    if not _is_canonical(value, dict(codes), normalize):",
                _COUNTRY_OUT,
            ),
            ("a country with an ISO code", "    if iso is None:", _COUNTRY_OUT),
            (
                "the United Kingdom by its parts",
                '    if iso == "GB" and value not in UK_PARTS.allowed_new_values:',
                _COUNTRY_OUT,
            ),
            (
                "an uncounted judge gives no evidence",
                "        if not judge.counted:\n            continue",
                "test_a_quote_of_a_judge_that_does_not_count_is_no_evidence",
            ),
            (
                "a quote the check did not find",
                "            if outcome != Q.FOUND:",
                "test_a_quote_the_check_did_not_find_is_no_evidence",
            ),
            (
                "a quote that states nothing",
                "            if stated is None:",
                "test_no_quote_that_states_the_value_lists_the_row",
            ),
            (
                "a quote not about the site",
                "            if about is None:",
                "test_a_page_quote_that_stands_far_from_the_site_s_name_is_no_evidence",
            ),
            (
                "why no quote carries it",
                "    if not stating:",
                "test_no_quote_that_states_the_value_lists_the_row",
            ),
            (
                "a kept row is listed",
                "    if c.decision != REVERT:",
                "test_a_row_the_audit_kept_is_listed",
            ),
            (
                "a curated site",
                '    if site is None or site["source_id"] != CURATED_SOURCE:',
                "test_a_site_that_is_not_curated_is_listed",
            ),
            (
                "the journal ends at the live value",
                "    if broken is not None:\n        return refuse(*broken)",
                "test_a_journal_that_does_not_end_at_the_live_value_is_listed",
            ),
            (
                "the judges name one value",
                "    if len(named) != 1:",
                "test_judges_that_name_two_values_are_listed",
            ),
            (
                "not the old value",
                "    if value == c.old_value:",
                "test_a_proposal_of_the_old_or_the_written_value_is_listed",
            ),
            (
                "not the reverted value",
                "    if value == c.written_value:",
                "test_a_proposal_of_the_old_or_the_written_value_is_listed",
            ),
            (
                "a canonical site type",
                "        if value not in CANONICAL_TYPES:",
                "test_a_site_type_that_is_not_a_canonical_fixed_point_is_listed",
            ),
            (
                "the bucket rules agree",
                "        if frontend(year) != bucket:",
                "test_the_bucket_rules_must_agree",
            ),
            (
                "a start in another bucket takes its label",
                "        if live_label != bucket:",
                "test_a_start_that_changes_bucket_writes_its_label_with_it",
            ),
            (
                "a label to condition on",
                "            if live_label is None:",
                "test_a_label_the_row_holds_none_of_is_listed",
            ),
            (
                "the label's journal ends at it",
                "            if label_broken is not None:",
                "test_a_label_whose_journal_does_not_end_at_it_is_listed",
            ),
            (
                "the country convention lists the row",
                "        if problem is not None:",
                "test_a_country_row_outside_the_convention_is_listed",
            ),
            (
                "no evidence lists the row",
                "    if evidence is None:",
                "test_no_quote_that_states_the_value_lists_the_row",
            ),
            (
                "a correction without a label",
                "    if label is None:\n        return (written,)",
                _WRITTEN,
            ),
            (
                "list and write are two runs",
                "    if args.list and args.write:",
                "test_list_and_write_in_one_run_are_refused",
            ),
            (
                "no flag reads nothing",
                "    if not (args.list or args.write):",
                "test_no_flag_reads_nothing",
            ),
            (
                "the plan follows the lane's list",
                "            if rows != listed_rows():",
                "test_write_refuses_a_plan_that_is_not_the_lane_s_list",
            ),
            (
                "--list writes the list",
                "        if args.list:",
                "test_list_writes_the_journal_rows_the_corrections_follow",
            ),
        )
    ),
    *(
        Case(f"wrong-both: {label}", WRONG_BOTH, old, new, test, WRONG_BOTH_TESTS)
        for label, old, new, test in (
            (
                "a year in the other era states nothing",
                '        if (match["bc"] is not None) == (year < 0):',
                "        if True:",
                _YEAR_OUT,
            ),
            (
                "another year after AD states nothing",
                '            if int(match["n"].replace(",", "")) == year:',
                "            if True:",
                _YEAR_OUT,
            ),
            (
                "the judge counts as its basis says",
                '        counted=bool(basis["counted"]),',
                "        counted=True,",
                "test_a_basis_that_did_not_count_is_read_as_one",
            ),
            (
                "a term of several words",
                "min(len(words), i + MAX_TERM_WORDS) + 1",
                "min(len(words), i + 1) + 1",
                _TYPE_IN,
            ),
            (
                "a slash joins a word",
                r'_WORD = re.compile(r"[^\W\d_]+(?:/[^\W\d_]+)*")',
                r'_WORD = re.compile(r"[^\W\d_]+")',
                _TYPE_IN,
            ),
            (
                "the normalizer resolves the term",
                "            if normalize_site_type(run) == value:",
                "            if run.lower() == value.lower():",
                _TYPE_IN,
            ),
            (
                "the number is the year's",
                '        if match is None or int(match["n"].replace(",", "")) != abs(year):',
                "        if match is None:",
                _YEAR_IN,
            ),
            (
                "a range reads on to its era",
                r'_RANGE = r"(?:\s?[–—\-/]\s?\d[\d,]*|\s(?:to|and)\s\d[\d,]*)*"',
                '_RANGE = r""',
                _YEAR_IN,
            ),
            (
                "the era stands whole",
                r'r"\s?(?:(?P<bc>" + _BC + r")|(?P<ad>" + _AD + r"))(?![^\W\d_])"',
                r'r"\s?(?:(?P<bc>" + _BC + r")|(?P<ad>" + _AD + r"))"',
                _YEAR_OUT,
            ),
            (
                "a number starts whole",
                r'_DIGIT = re.compile(r"(?<![\d.,])\d")',
                r'_DIGIT = re.compile(r"\d")',
                _YEAR_OUT,
            ),
            (
                "a number with thousands commas",
                r'_NUMBER = r"(?P<n>\d{1,3}(?:,\d{3})+|\d+)"',
                r'_NUMBER = r"(?P<n>\d+)"',
                _YEAR_IN,
            ),
            (
                "AD stands whole before the year",
                r'_PREFIX = re.compile(r"(?<![^\W\d_])(?:A\.\s?D\.|AD)\s?" + _NUMBER + r"(?![^\W_]|[.,]\d)")',
                r'_PREFIX = re.compile(r"(?:A\.\s?D\.|AD)\s?" + _NUMBER + r"(?![^\W_]|[.,]\d)")',
                _YEAR_OUT,
            ),
            (
                "a longer country name is not the country",
                '        text = text.replace(longer, " " * len(longer))',
                "        pass",
                "test_a_country_is_stated_by_its_name_standing_whole",
            ),
            (
                "a country name stands whole",
                r'match = re.search(r"(?<![^\W_])" + re.escape(value) + r"(?![^\W_])", text)',
                "match = re.search(re.escape(value), text)",
                "test_a_country_is_stated_by_its_name_standing_whole",
            ),
            (
                "another column is refused",
                '    raise PlanError(f"{column!r} is not a column a wrong-both correction writes")',
                "    return None",
                "test_a_column_the_lane_does_not_correct_is_refused",
            ),
            (
                "a page that no longer holds the quote refuses",
                "    raise PlanError(f\"{source} no longer holds {text!r}, which the audit's check "
                'found there")',
                "    return None",
                "test_a_page_the_audit_found_the_quote_on_must_still_hold_it",
            ),
            (
                "only a counted judge names a value",
                "        if judge.counted and judge.right_value:",
                "        if judge.right_value:",
                "test_only_a_counted_judge_s_value_counts",
            ),
            (
                "the last write is a journal row",
                "        last is None\n        or last.run_stamp",
                "        False\n        or last.run_stamp",
                "test_a_cell_the_journal_holds_nothing_for_is_listed",
            ),
            (
                "the last write is journal-reversal-3's",
                "        or last.run_stamp != REVERSAL_3.run_stamp\n",
                "",
                "test_a_cell_journal_reversal_3_did_not_restore_from_the_judged_write_is_listed",
            ),
            (
                "journal-reversal-3 restored the judged write",
                "        or (last.old_value, last.new_value) != (c.written_value, c.old_value)\n",
                "",
                "test_a_cell_journal_reversal_3_did_not_restore_from_the_judged_write_is_listed",
            ),
            (
                "an integer year as the database prints it",
                "            year = typed_value(LANE.cell(PERIOD_START), value)",
                "            year = int(float(value))",
                "test_a_period_start_that_is_not_an_integer_year_is_listed",
            ),
            (
                "the corrections are counted apart from the labels",
                '            "corrections": sum(v.rule == RULE for v in changes),',
                '            "corrections": len(changes),',
                "test_the_plan_writes_the_corrections_and_lists_the_rest",
            ),
            (
                "the list is the corrections' rows",
                "    return tuple(sorted(int(str(v.journal_id)) for v in plan.changes if v.rule == "
                "RULE))",
                "    return tuple(sorted(int(str(v.journal_id)) for v in plan.changes))",
                "test_the_plan_writes_the_corrections_and_lists_the_rest",
            ),
        )
    ),
    *(
        Case(f"wrong-both: {label}", LANE, old, new, test, WRONG_BOTH_TESTS)
        for label, old, new, test in (
            (
                "the lane is registered",
                "LANES[WRONG_BOTH.name] = WRONG_BOTH\n",
                "",
                "test_the_lane_owns_four_cells_and_reverses_no_journal_row",
            ),
            (
                "the lane reads back",
                "LANE_READBACKS[WRONG_BOTH.name] = WRONG_BOTH_READBACK\n",
                "",
                "test_the_lane_owns_four_cells_and_reverses_no_journal_row",
            ),
            (
                "the lane owns the canonical types",
                '        "site_type", "character varying", max_chars=100, '
                "allowed_new_values=tuple(CANONICAL_TYPES)\n",
                '        "site_type", "character varying", max_chars=100\n',
                "test_the_lane_owns_four_cells_and_reverses_no_journal_row",
            ),
            (
                "the lane owns the bucket labels",
                "        allowed_new_values=tuple(label for label, _lo, _hi in PERIOD_BUCKETS),\n"
                "    ),\n"
                '    Column("country", "character varying", max_chars=100),\n)\n'
                "_WRONG_BOTH_RESIDUAL",
                "    ),\n"
                '    Column("country", "character varying", max_chars=100),\n)\n'
                "_WRONG_BOTH_RESIDUAL",
                "test_the_lane_owns_four_cells_and_reverses_no_journal_row",
            ),
            (
                "the residual is the lane's list",
                "    reversal_residual(WRONG_BOTH_JOURNAL_IDS, _WRONG_BOTH_CELLS).predicate,",
                "    reversal_residual(REVERSAL_3_JOURNAL_IDS, _WRONG_BOTH_CELLS).predicate,",
                "test_the_residual_is_the_restored_values_the_list_names",
            ),
            (
                "the lane reads back its list",
                "        *reversal_metrics(WRONG_BOTH, WRONG_BOTH_JOURNAL_IDS, "
                "_WRONG_BOTH_RESIDUAL),\n",
                "",
                "test_the_residual_is_the_restored_values_the_list_names",
            ),
            (
                "the lane reads back the period pair",
                "        (_PERIOD_MISMATCH.metric, _CURATED_ROWS + _PERIOD_MISMATCH.predicate),\n",
                "",
                "test_the_residual_is_the_restored_values_the_list_names",
            ),
        )
    ),
]
CASES += WRONG_BOTH_CASES

# ------------------------------------------ the card_stats basis next to Phase 5 (2026-09-25)
#: Phase 5 journals `card_stats.card_description` (`phase4/write4.py`); the basis pointer reads
#: the twelve columns only, so a card text never makes a later wave refuse to plan - and a write
#: to one of the twelve that no wave made still does, whoever made it.
_BASIS_ROWS = (
    '    cards = [j for j in journal if j["table_name"] == "card_stats" and j["column_name"] in '
    "COLUMNS]"
)
CARD_STATS_P5_CASES: list[Case] = [
    Case(f"card_stats: {label}", CARD_STATS, _BASIS_ROWS, new, test, CARD_TESTS)
    for label, new, test in (
        (
            "a Phase-5 card text names no basis",
            '    cards = [j for j in journal if j["table_name"] == "card_stats"]',
            "test_a_phase_5_card_text_is_no_basis_of_the_stats",
        ),
        (
            "the next wave plans after Phase 5",
            '    cards = [j for j in journal if j["table_name"] == "card_stats"]',
            "test_the_next_wave_plans_after_phase_5_wrote_card_texts",
        ),
        (
            "the twelve columns name the basis",
            '    cards = [j for j in journal if j["table_name"] == "card_stats" and j["column_name"] '
            "not in COLUMNS]",
            "test_the_write_and_the_undo_name_their_own_sides",
        ),
        (
            "a stats cell of Phase 5 still refuses",
            '    cards = [j for j in journal if j["table_name"] == "card_stats" and not '
            'str(j["run_stamp"]).startswith("phase5:")]',
            "test_a_stats_cell_written_by_phase_5_still_refuses",
        ),
    )
]
CASES += CARD_STATS_P5_CASES

# ------------------------------------------- T1 for a thumbnail on an excluded row (2026-09-25)
#: `hero_repair/thumbnail.py`: the thumbnail that names the local file of its own site's excluded
#: row gets the served image's file, or none (Dedan). Labels start with "img" like every image case.
THUMB = REPO / "scripts/remediation/hero_repair/thumbnail.py"
DECIDE = REPO / "scripts/remediation/gallery_audit/decide.py"
THUMB_TESTS = "tests/remediation/test_hero_thumbnail.py"
THUMBNAIL_CASES: list[Case] = [
    *(
        guard(f"img thumbnail: {label}", THUMB, needle, test, THUMB_TESTS)
        for label, needle, test in (
            (
                "an image row of no site of the read",
                '        if str(row["site_id"]) not in by_site:',
                "test_an_image_row_of_a_site_the_read_did_not_return_is_refused",
            ),
            (
                "only curated sites",
                '        if site["source_id"] != CURATED_SOURCE:',
                "test_a_site_outside_the_curated_source_is_refused",
            ),
            (
                "a thumbnail on no excluded row is listed",
                "        if not excluded:",
                "test_a_thumbnail_that_names_a_live_row_is_not_this_lane_s",
            ),
            (
                "another shard's file is not the site's",
                "        if not excluded:",
                "test_a_file_of_another_shard_is_not_the_site_s",
            ),
            (
                "a file a live row shares is still served",
                "        if len(excluded) != len(named):",
                "test_a_file_an_excluded_and_a_live_row_share_is_still_served",
            ),
            (
                "the directory names the date",
                "    if match is None:",
                "test_the_stamp_is_the_output_directory_s_date",
            ),
            (
                "an empty plan writes nothing",
                "    if not changes:",
                "test_a_read_that_plans_nothing_writes_nothing",
            ),
        )
    ),
    *(
        Case(f"img thumbnail: {label}", path, old, new, test, THUMB_TESTS)
        for label, path, old, new, test in (
            (
                "the shard is the site's short id",
                THUMB,
                '    return f"/data/images/wiki/{site_id_short(site_id)}/{filename}"',
                '    return f"/data/images/wiki/{site_id[:8]}/{filename}"',
                "test_the_shard_is_the_site_s_short_id",
            ),
            (
                "the served image's file, or none",
                THUMB,
                '        new = None if served is None else local_path(site_id, str(served["filename"]))',
                "        new = None",
                "test_a_site_that_serves_a_live_image_gets_that_image_s_file",
            ),
            (
                "the exclusion's journal rows are evidence",
                THUMB,
                '                for entry in history.get(str(row["id"]), ())',
                "                for entry in ()",
                "test_a_site_that_serves_no_image_has_no_thumbnail",
            ),
            (
                "T1 names what a site without an image gets",
                DECIDE,
                "<served filename>', or NULL when the site serves no image (hero_repair",
                "<served filename>' (hero_repair",
                "test_the_rule_table_says_what_a_site_without_an_image_gets",
            ),
        )
    ),
]
CASES += THUMBNAIL_CASES

# ----------------------------------------------- Phase 6 follow-through (2026-09-25)
#: The match-key lane (`name_key/plan.py`) and the chunk writer's two key columns, the static
#: export's preflight, Lyra's semantic search without retired sites and Lyra's alias key in SQL.
NAME_KEY = REPO / "scripts/remediation/name_key/plan.py"
NAME_KEY_TESTS = "tests/remediation/test_name_key_lane.py"
LYRA_TOOLS = REPO / "api/services/lyra_tools.py"
SITE_IDENTIFIER = REPO / "pipeline/lyra/site_identifier.py"
PREFLIGHT_TESTS = "tests/pipeline/test_static_export_preflight.py"
VECTOR_TESTS = "tests/api/test_lyra_vector_search_scope.py"
ALIAS_TESTS = "tests/pipeline/test_wikidata_alias_key.py"
PHASE6_CASES: list[Case] = [
    *(
        guard(f"name key: {label}", path, needle, test, testfile)
        for label, path, needle, test, testfile in (
            (
                "the name row guard is rendered",
                CHUNK,
                '    if any(c.table == "unified_site_names" for c in rows):',
                "test_the_name_row_guard_is_rendered_in_both_directions",
                NAME_KEY_TESTS,
            ),
            (
                "a key is never cleared",
                CHUNK,
                '    if change.column == "name_normalized" and change.new_value is None:',
                "test_a_key_is_never_cleared",
                NAME_KEY_TESTS,
            ),
            (
                "a key another row holds is listed",
                NAME_KEY,
                '    if row.get("collides_with") is not None:',
                "test_a_key_another_row_of_the_site_already_holds_is_listed_not_planned",
                NAME_KEY_TESTS,
            ),
            (
                "only the writer's source is planned",
                NAME_KEY,
                '    if row["source_id"] != WRITER_SOURCE:',
                "test_a_row_of_another_source_is_listed_not_planned",
                NAME_KEY_TESTS,
            ),
            (
                "a row already keyed is a bad read",
                NAME_KEY,
                "    if key == stored:",
                "test_a_read_the_plan_cannot_trust_is_refused",
                NAME_KEY_TESTS,
            ),
            (
                "a key comes from Postgres",
                NAME_KEY,
                "    if not isinstance(key, str) or not key:",
                "test_a_read_the_plan_cannot_trust_is_refused",
                NAME_KEY_TESTS,
            ),
            (
                "an empty plan writes nothing",
                NAME_KEY,
                "    if not changes:",
                "test_nothing_divergent_plans_nothing_and_writes_nothing",
                NAME_KEY_TESTS,
            ),
            (
                "the directory names the date",
                NAME_KEY,
                "    if match is None:",
                "test_the_lane_is_stamped_with_its_directory_s_date",
                NAME_KEY_TESTS,
            ),
            (
                "the export refuses root",
                EXPORTER,
                '    if hasattr(os, "geteuid") and os.geteuid() == 0:',
                "test_the_export_refuses_to_run_as_root",
                PREFLIGHT_TESTS,
            ),
            (
                "the export names an unwritable path",
                EXPORTER,
                "        if not _writable(probe):",
                "test_every_unwritable_target_is_named_before_anything_is_written",
                PREFLIGHT_TESTS,
            ),
            (
                "Lyra's site search reads the scope",
                LYRA_TOOLS,
                '    if collection == "sites":',
                "test_a_retired_site_is_dropped_before_the_rerank",
                VECTOR_TESTS,
            ),
        )
    ),
    *(
        Case(f"name key: {label}", path, old, new, test, testfile)
        for label, path, old, new, test, testfile in (
            (
                "the premise is the write's only",
                CHUNK,
                "    if not rollback:",
                "    if True:",
                "test_the_key_premise_is_postgres_s_own_key_of_the_row_name_on_the_write_only",
                NAME_KEY_TESTS,
            ),
            (
                "the premise is Postgres's key",
                CHUNK,
                '                    .replace("{derived}", site_key_sql(f"{alias}.name"))',
                '                    .replace("{derived}", "p.old_value")',
                "test_the_key_premise_is_postgres_s_own_key_of_the_row_name_on_the_write_only",
                NAME_KEY_TESTS,
            ),
            (
                "a name row is keyed by its integer id",
                CHUNK,
                'KEY_TYPES = {"wiki_images": "integer", "unified_sites": "uuid", '
                '"unified_site_names": "integer"}',
                'KEY_TYPES = {"wiki_images": "integer", "unified_sites": "uuid", '
                '"unified_site_names": "uuid"}',
                "test_a_name_row_is_keyed_by_its_integer_id",
                NAME_KEY_TESTS,
            ),
            (
                "the export runs its preflight",
                EXPORTER,
                "        preflight(export_targets(self.output_dir, sites_only=sites_only, "
                "library=library))",
                "        pass",
                "test_every_unwritable_target_is_named_before_anything_is_written",
                PREFLIGHT_TESTS,
            ),
            (
                "the hubs refresh runs its preflight",
                EXPORTER,
                "    preflight([path])",
                "    pass",
                "test_the_hubs_only_refresh_is_checked_too",
                PREFLIGHT_TESTS,
            ),
            (
                "Lyra's site search drops the retired",
                LYRA_TOOLS,
                "    return [p for p in points if str(p.id) not in retired]",
                "    return points",
                "test_a_retired_site_is_dropped_before_the_rerank",
                VECTOR_TESTS,
            ),
            (
                "an alias is not the site's own name",
                SITE_IDENTIFIER,
                "    f\"WHERE {site_key_sql(':name')} <> {site_key_sql(':canonical')} \"",
                '    "WHERE TRUE "',
                "test_the_key_is_computed_in_the_insert_from_the_raw_name",
                ALIAS_TESTS,
            ),
        )
    ),
]
CASES += PHASE6_CASES

#: The acceptance draw (`acceptance/draw.py`), sealed with PROTOCOL.md.
DRAW = REPO / "scripts/remediation/acceptance/draw.py"
DRAW_TESTS = "tests/remediation/test_acceptance_draw.py"
ACCEPTANCE_CASES: list[Case] = [
    guard(
        "acceptance: a pool below 60 refuses",
        DRAW,
        "    if len(pool) < SAMPLE_SIZE:",
        "test_a_pool_smaller_than_the_sample_refuses",
        DRAW_TESTS,
    ),
    guard(
        "acceptance: a draw is taken once",
        DRAW,
        "    if out.exists():",
        "test_a_draw_is_taken_once",
        DRAW_TESTS,
    ),
    Case(
        "acceptance: the exclusions are applied",
        DRAW,
        "        excluded.update(removed)",
        "        pass",
        "test_the_draw_is_the_project_s_seeded_draw_over_the_pool",
        DRAW_TESTS,
    ),
    Case(
        "acceptance: a country donor is far away",
        DRAW,
        "        if distance >= COUNTRY_CANARY_MIN_KM:",
        "        if True:",
        "test_a_country_canary_is_another_country_far_away",
        DRAW_TESTS,
    ),
]
CASES += ACCEPTANCE_CASES

#: The fresh draw of PROTOCOL.md section 10 (`acceptance/redraw.py`): draw.py stays sealed, and the
#: next seed and the previous draws' exclusion are this module's. Labels start "acceptance-redraw".
REDRAW = REPO / "scripts/remediation/acceptance/redraw.py"
REDRAW_TESTS = "tests/remediation/test_acceptance_redraw.py"
REDRAW_CASES: list[Case] = [
    *(
        guard(f"acceptance-redraw: {label}", REDRAW, needle, test, REDRAW_TESTS)
        for label, needle, test in (
            (
                "a previous draw has its result",
                '    if not (run / "RESULT.md").is_file():',
                "test_a_previous_draw_without_its_result_refuses",
            ),
            (
                "the previous sample is the pinned one",
                '    if digest != draw["sha256"]["SAMPLE.jsonl"]:',
                "test_a_sample_that_is_not_the_one_its_draw_pins_refuses",
            ),
            (
                "the previous sample holds its draw's sites",
                '    if len(set(ids)) != len(ids) or len(ids) != int(draw["sample_size"]):',
                "test_a_sample_that_is_not_its_draw_s_size_refuses",
            ),
            (
                "a previous draw is named",
                "    if not previous:",
                "test_there_is_no_fresh_draw_without_a_previous_one",
            ),
            (
                "a pool below 60 refuses",
                "    if len(pool) < D.SAMPLE_SIZE:",
                "test_a_pool_smaller_than_the_sample_refuses",
            ),
            ("a draw is taken once", "    if out.exists():", "test_a_fresh_draw_is_taken_once"),
            (
                "the Phase-4 audit samples are required",
                "    if not args.phase4_audit_samples:",
                "test_the_phase4_audit_samples_are_still_required",
            ),
        )
    ),
    *(
        Case(f"acceptance-redraw: {label}", REDRAW, old, new, test, REDRAW_TESTS)
        for label, old, new, test in (
            (
                "the seed is one past the last",
                "    return max(p.seed for p in previous) + 1",
                "    return max(p.seed for p in previous)",
                "test_the_next_seed_is_one_past_the_highest_previous_seed",
            ),
            (
                "the previous draws' sites are excluded",
                "        excluded.update(removed)",
                "        pass",
                "test_only_the_previous_draws_own_sites_are_excluded_and_recorded",
            ),
            (
                "the draw takes the next seed",
                "    drawn = draw_sample(sorted(frame_ids), seed=seed,",
                "    drawn = draw_sample(sorted(frame_ids), seed=D.SEED,",
                "test_the_draw_is_the_project_s_seeded_draw_with_the_next_seed",
            ),
            (
                "the canaries take the seed after the draw's",
                "    canary_rows = D.canaries(values, frame, seed=seed)",
                "    canary_rows = D.canaries(values, frame)",
                "test_the_canaries_are_picked_with_the_seed_after_the_draw_s",
            ),
            (
                "DRAW.json names the fresh draw's script",
                '        "redraw_py_sha256": D.sha256_of(_HERE),\n',
                "",
                "test_a_fresh_draw_writes_the_files_the_judging_reads_and_pins_them",
            ),
        )
    ),
]
CASES += REDRAW_CASES

# -------------------------------------------------- the orphan-citations lane (D1, 2026-09-25)
#: The repair of the acceptance's D1 class (`citations.py`) and its registration in `lane.py`.
#: Every label starts with "orphan-citations" - `mutation_sweep.py orphan-citations` runs these.
CITATIONS = MECHANICAL / "citations.py"
CITATIONS_TESTS = "tests/remediation/test_mechanical_citations.py"
_LANE_TEST = "test_the_lane_writes_one_jsonb_cell_conditioned_on_the_description"
ORPHAN_CITATIONS_CASES: list[Case] = [
    *(
        guard(f"orphan-citations: {label}", CITATIONS, needle, test, CITATIONS_TESTS)
        for label, needle, test in (
            (
                "a site D1 holds on is no candidate",
                "    if failure is None:",
                "test_a_site_d1_holds_on_is_no_candidate",
            ),
            (
                "a marker without an entry lists the site",
                "    if unanswered:",
                "test_a_marker_without_an_entry_is_listed_and_nothing_of_the_site_is_written",
            ),
            (
                "the journal ends at the live value",
                "    if broken is not None:",
                "test_a_journal_that_does_not_end_at_the_live_value_is_listed",
            ),
            (
                "the value is printed as Postgres prints it",
                "    if site.raw_data is None or reprint(raw) != site.raw_data:",
                "test_a_raw_data_the_writer_would_not_print_as_postgres_does_is_listed",
            ),
            (
                "the plan is read against D1",
                "            if after is not None:",
                "test_a_plan_whose_value_would_not_make_d1_hold_is_refused",
            ),
            (
                "--write plans",
                "        if args.write:",
                "test_write_writes_the_lane_s_files_from_the_export_alone",
            ),
            (
                "--export reads production",
                "        if args.export:",
                "test_export_reads_production_into_the_lane_s_export_directory",
            ),
        )
    ),
    *(
        Case(f"orphan-citations: {label}", CITATIONS, old, new, test, CITATIONS_TESTS)
        for label, old, new, test in (
            (
                "unreadable entries are listed",
                "    except ValueError as exc:\n        return listed(NOT_READABLE",
                "    except KeyError as exc:\n        return listed(NOT_READABLE",
                "test_unreadable_citations_are_listed",
            ),
            (
                "the journal is compared as JSON",
                "                canonical(link.new_value),",
                "                link.new_value,",
                "test_the_raw_data_journal_is_compared_as_json",
            ),
            (
                "a text without markers loses the key",
                "if key != CITATIONS_KEY}",
                "if True}",
                "test_entries_of_a_text_without_markers_go_with_their_key_and_nothing_else_moves",
            ),
            (
                "only the uncited entries go",
                'key: [e for e in value if e["n"] in markers] if key',
                "key: [e for e in value] if key",
                "test_uncited_entries_go_and_the_cited_stay_byte_for_byte",
            ),
            (
                "the journal is read in id order",
                'for r in sorted(rows["journal"], key=lambda r: int(r["id"])):',
                'for r in rows["journal"]:',
                "test_the_export_is_parsed_into_sites_and_each_site_s_journal",
            ),
            (
                "the export reads the raw_data journal",
                "l.column_name = 'raw_data'",
                "l.column_name = 'description'",
                "test_the_export_is_one_read_only_snapshot_of_the_curated_rows_and_their_raw_data"
                "_journal",
            ),
            (
                "the write is conditioned on its premise",
                "        premise=site.premise,\n",
                "",
                "test_the_plan_is_one_the_framework_renders_and_reverses",
            ),
        )
    ),
    *(
        Case(f"orphan-citations: {label}", LANE, old, new, test, CITATIONS_TESTS)
        for label, old, new, test in (
            (
                "the lane is registered",
                "LANES[ORPHAN_CITATIONS.name] = ORPHAN_CITATIONS\n",
                "",
                _LANE_TEST,
            ),
            (
                "the lane reads back",
                "LANE_READBACKS[ORPHAN_CITATIONS.name] = ORPHAN_CITATIONS_READBACK\n",
                "",
                _LANE_TEST,
            ),
            (
                "the premise is the description's sha256",
                "    premise_sql=\"encode(sha256(convert_to(coalesce(u.description, ''), 'UTF8')), "
                "'hex')\",\n",
                "    premise_sql=\"md5(coalesce(u.description, ''))\",\n",
                _LANE_TEST,
            ),
            (
                "the residual reads both halves",
                '    f"({CITATIONS_UNCITED} OR {CITATIONS_UNANSWERED})",',
                '    f"({CITATIONS_UNCITED})",',
                "test_the_residual_is_d1_read_with_the_census_marker",
            ),
            (
                "the residual reads the census marker",
                "(\\d+)\\]', 'g')",
                "(\\d)\\]', 'g')",
                "test_the_residual_is_d1_read_with_the_census_marker",
            ),
            (
                "the readback counts added entries",
                '            "journal rows for this run that added a citation entry",\n',
                '            "journal rows for this run that removed a citation entry",\n',
                "test_the_readback_measures_both_halves_and_that_nothing_else_moved",
            ),
        )
    ),
]
CASES += ORPHAN_CITATIONS_CASES

# ---------------------------------------------- the dangling-markers lane (D9 (b), 2026-09-25)
#: The removal of the markers without an entry (`dangling_markers.py`) and its registration in
#: `lane.py`. Every label starts with "dangling-markers" - `mutation_sweep.py dangling-markers`.
DANGLING = MECHANICAL / "dangling_markers.py"
DANGLING_TESTS = "tests/remediation/test_mechanical_dangling_markers.py"
_DANGLING_LANE_TEST = (
    "test_the_lane_writes_the_description_and_raw_data_of_a_site_in_one_transaction"
)
_RULE = "test_a_dangling_marker_goes_with_the_space_before_its_run"
_FAULTS = "test_a_removal_that_is_not_clean_is_named"
DANGLING_MARKERS_CASES: list[Case] = [
    *(
        guard(f"dangling-markers: {label}", DANGLING, needle, test, DANGLING_TESTS)
        for label, needle, test in (
            (
                "a site D1 holds on is no candidate",
                "    if failure is None:",
                "test_a_site_d1_holds_on_is_no_candidate",
            ),
            (
                "the export's premise is its provenance",
                "    if parse_json(site.premise) != parse_json(premise_of(raw)):",
                "test_an_export_whose_premise_is_not_its_provenance_is_refused",
            ),
            (
                "a failure without a dangling marker is listed",
                "    if not dangling:",
                "test_the_orphan_citations_class_is_listed_not_repaired_here",
            ),
            (
                "grouped markers are listed",
                "    if [int(n) for n in _TOKEN.findall(text)] != markers:",
                "test_grouped_markers_are_listed",
            ),
            (
                "no provenance is refused",
                "    if provenance is None:\n        return listed(NO_PROVENANCE",
                "test_a_site_without_the_lane_l_marking_is_refused",
            ),
            (
                "a Phase-4 provenance is refused",
                '    if not isinstance(provenance, dict) or provenance.get("lane") != '
                "TextLane.L.value:",
                "test_a_site_with_live_phase4_provenance_is_refused",
            ),
            (
                "a hash that already differs is listed",
                "    if legacy.desc_sha256 != text_sha256(text):",
                "test_a_provenance_that_already_disagrees_with_the_text_is_listed",
            ),
            (
                "each cell's journal ends at the live value",
                "        if broken is not None:",
                "test_the_description_journal_must_end_at_the_live_text",
            ),
            (
                "the value is printed as Postgres prints it",
                "    if site.raw_data is None or reprint(raw) != site.raw_data:",
                "test_a_raw_data_the_writer_would_not_print_as_postgres_does_is_listed",
            ),
            (
                "an unclean removal is listed",
                "    if faults:",
                "test_a_removal_that_is_not_clean_is_listed",
            ),
            (
                "the kept markers are the old ones",
                "    if marker_sequence(new) != kept:",
                _FAULTS,
            ),
            (
                "nothing but the tokens changes",
                '    if re.sub(r"\\s", "", new) != re.sub(r"\\s", "", tokens_out):',
                _FAULTS,
            ),
            (
                "no spacing fault is added",
                "        if len(pattern.findall(new)) > len(pattern.findall(old)):",
                _FAULTS,
            ),
            (
                "--write plans",
                "        if args.write:",
                "test_write_writes_the_lane_s_files_from_the_export_alone",
            ),
            (
                "--export reads production",
                "        if args.export:",
                "test_export_reads_production_into_the_lane_s_export_directory",
            ),
            (
                "the reversal is written with the plan",
                "            if plan.changes:",
                "test_write_writes_the_lane_s_files_from_the_export_alone",
            ),
        )
    ),
    *(
        Case(f"dangling-markers: {label}", DANGLING, old, new, test, DANGLING_TESTS)
        for label, old, new, test in (
            (
                "unreadable entries are listed",
                "    except ValueError as exc:\n        return listed(NOT_READABLE",
                "    except KeyError as exc:\n        return listed(NOT_READABLE",
                "test_unreadable_citations_are_listed",
            ),
            (
                "an unreadable legacy provenance is listed",
                "    except ValueError as exc:\n        return listed(PROVENANCE_NOT_READABLE",
                "    except KeyError as exc:\n        return listed(PROVENANCE_NOT_READABLE",
                "test_a_provenance_that_does_not_read_is_listed",
            ),
            (
                "the raw_data journal is compared as JSON",
                "                    canonical(link.new_value),",
                "                    link.new_value,",
                "test_the_raw_data_journal_is_compared_as_json_and_must_end_at_the_live_value",
            ),
            (
                "a run keeps its space while it keeps a marker",
                '        return match["space"] + kept if kept else ""',
                "        return kept",
                _RULE,
            ),
            (
                "a run that loses every marker loses its space",
                '        return match["space"] + kept if kept else ""',
                '        return match["space"] + kept',
                _RULE,
            ),
            (
                "only the dangling markers go",
                "            if int(token.group(1)) not in dangling",
                "            if int(token.group(1)) in dangling",
                _RULE,
            ),
            (
                "the hash moves to the new text",
                "        key: {**value, HASH_KEY: text_sha256(description)} if key",
                "        key: {**value} if key",
                "test_a_dangling_marker_is_removed_and_the_hash_moves_in_the_same_site",
            ),
            (
                "an entry left uncited goes",
                "    fixed = repaired(raw, markers)",
                "    fixed = dict(raw)",
                "test_an_entry_the_removal_leaves_uncited_goes_with_the_orphan_citations_rule",
            ),
            (
                "the premise leaves out the hash",
                "provenance.items() if key != HASH_KEY})",
                "provenance.items()})",
                "test_the_premise_is_the_legacy_provenance_without_the_hash_the_lane_moves",
            ),
            (
                "the plan is read against D1",
                '(("D1", d1(after)), ("D4", d4(after)))',
                '(("D1", None), ("D4", d4(after)))',
                "test_a_plan_on_which_d1_would_still_fail_is_refused",
            ),
            (
                "the plan is read against D4",
                '(("D1", d1(after)), ("D4", d4(after)))',
                '(("D1", d1(after)), ("D4", None))',
                "test_a_plan_on_which_d4_would_fail_is_refused",
            ),
            (
                "the journal is read in id order",
                'for r in sorted(rows["journal"], key=lambda r: int(r["id"])):',
                'for r in rows["journal"]:',
                "test_the_export_is_parsed_into_sites_and_each_cell_s_journal_in_id_order",
            ),
            (
                "the export reads both journals",
                "l.column_name IN ('description', 'raw_data')",
                "l.column_name IN ('raw_data')",
                "test_the_export_is_one_read_only_snapshot_of_the_rows_and_both_journals",
            ),
            (
                "the write is conditioned on its premise",
                '        "premise": site.premise,\n',
                "",
                "test_the_plan_is_one_the_framework_renders_and_reverses",
            ),
        )
    ),
    *(
        Case(f"dangling-markers: {label}", LANE, old, new, test, DANGLING_TESTS)
        for label, old, new, test in (
            (
                "the lane is registered",
                "LANES[DANGLING_MARKERS.name] = DANGLING_MARKERS\n",
                "",
                _DANGLING_LANE_TEST,
            ),
            (
                "the lane reads back",
                "LANE_READBACKS[DANGLING_MARKERS.name] = DANGLING_MARKERS_READBACK\n",
                "",
                _DANGLING_LANE_TEST,
            ),
            (
                "the lane writes both cells",
                '    cells=(Column("description", "text"), Column("raw_data", "jsonb")),',
                '    cells=(Column("raw_data", "jsonb"),),',
                _DANGLING_LANE_TEST,
            ),
            (
                "the premise is the provenance less its hash",
                "\"coalesce((u.raw_data -> '_description_provenance') - 'desc_sha256', "
                "'null'::jsonb)::text\"",
                "\"coalesce(u.raw_data -> '_description_provenance', 'null'::jsonb)::text\"",
                "test_the_premise_is_the_legacy_provenance_without_the_hash_the_lane_moves",
            ),
            (
                "the raw_data casts sit behind a CASE",
                "    return _DANGLING_ROWS + f\"CASE WHEN l.column_name = 'raw_data' THEN "
                '{predicate} ELSE false END"',
                '    return _DANGLING_ROWS + f"{predicate}"',
                "test_every_raw_data_cast_of_the_readback_skips_the_description_rows",
            ),
            (
                "the readback names the provenance lane",
                '            "journal rows for this run whose provenance is not lane L",\n',
                '            "journal rows for this run whose provenance is not lane W",\n',
                "test_the_residual_is_d1_and_the_readback_measures_d4_and_what_the_journal_may_hold",
            ),
            (
                "the D4 predicate is shared",
                '        _D4_FAILS,\n        (\n            "journal rows for this run that changed',
                '        (\n            "journal rows for this run that changed',
                "test_the_d4_predicate_is_shared_with_the_orphan_citations_readback",
            ),
        )
    ),
]
CASES += DANGLING_MARKERS_CASES


#: The fixes of the 2026-09-25 code audit (`output/remediation/CODE_AUDIT_2026-09-25.md`) in the
#: mechanical lanes and the shared transport. Every label starts with "audit-fix:", so the list runs
#: on its own: `mutation_sweep.py audit-fix:`.
AUDIT_FIX_CASES: list[Case] = [
    Case(
        "audit-fix: M2 send delivers LF as LF",
        PROD_WRITE,
        '            input=sql.encode("utf-8"),',
        '            input=sql.replace("\\n", "\\r\\n").encode("utf-8"),',
        "test_send_delivers_a_newline_as_lf_on_every_platform",
        PROD_TESTS,
    ),
    Case(
        "audit-fix: M7 AD-then-year has no right boundary",
        MECHANICAL / "wrong_both.py",
        r'_NUMBER + r"(?![^\W_]|[.,]\d)")',
        "_NUMBER)",
        "test_a_year_without_its_era_or_in_another_does_not",
        "tests/remediation/test_mechanical_wrong_both.py",
    ),
    Case(
        "audit-fix: M8 a found loser keeps its last pair",
        SCOPE,
        "    for dup in found:\n        own = by_loser.get(dup.loser)\n",
        "    for dup in found:\n        own = None  # mutant\n",
        "test_a_loser_found_with_two_survivors_is_refused_in_any_pair_order",
        SCOPE_TESTS,
    ),
    Case(
        "audit-fix: M9 the value table splits on |",
        APPLY,
        "    rows = psql_json_reader()(\n"
        '        f"SELECT {lane.column} AS value, count(*) AS n FROM unified_sites "',
        '    rows = (lambda sql: [dict(zip(("value", "n"), r)) for r in read_rows(sql)])(\n'
        '        f"SELECT {lane.column} AS value, count(*) AS n FROM unified_sites "',
        "test_a_value_with_the_separator_or_a_newline_is_read_whole",
    ),
    Case(
        "audit-fix: m1 the apply sends beside an unverified undo",
        APPLY,
        '    verify_pinned(\n        out / "ROLLBACK.sql", plan_path=plan_path, expected=rollback_statement(records, lane)\n    )\n    already',
        "    already",
        "test_the_apply_refuses_an_edited_rollback_before_anything_is_sent",
    ),
    Case(
        "audit-fix: m2 a second COMMIT is rehearsed away",
        APPLY,
        "    if commits != 1:\n",
        "    if commits == 0:  # mutant\n",
        "test_a_statement_with_two_commits_cannot_be_rehearsed",
    ),
    guard(
        "audit-fix: m3 a NUL reaches psql inside a literal",
        PROD_WRITE,
        '    if "\\x00" in value:',
        "test_one_quoting_rule_for_every_writer_and_it_refuses_nul",
        PROD_TESTS,
    ),
    guard(
        "audit-fix: m4 a spliced $$ ends the DO block",
        APPLY,
        '    if "$$" in block:',
        "test_a_value_that_would_end_the_do_block_is_refused",
    ),
    Case(
        "audit-fix: m6 an empty quote is evidence",
        REVERSAL,
        " or any(not q.text.strip() for q in r.quotes):",
        ":",
        "test_a_quote_without_text_is_no_evidence",
        REVERSAL_TESTS,
    ),
    guard(
        "audit-fix: m7 a list provenance crashes the premise",
        MECHANICAL / "dangling_markers.py",
        "    if isinstance(provenance, list):",
        "test_a_provenance_that_is_no_object_is_listed_not_a_crash",
        "tests/remediation/test_mechanical_dangling_markers.py",
    ),
    guard(
        "audit-fix: m8 the citations export's premise is not checked",
        MECHANICAL / "citations.py",
        "    if site.premise != premise_of(site.description):",
        "test_an_export_whose_premise_is_not_its_description_is_refused",
        "tests/remediation/test_mechanical_citations.py",
    ),
    Case(
        "audit-fix: m10 any other column is taken for the country",
        MECHANICAL / "wrong_both.py",
        "    elif c.column == COUNTRY:\n",
        "    elif True:  # mutant\n",
        "test_a_country_row_outside_the_convention_is_listed",
        "tests/remediation/test_mechanical_wrong_both.py",
    ),
    guard(
        "audit-fix: m11 an undated Museum without a decision is pending",
        SCOPE,
        '        if decision is None and "museum" in str(site["site_type"]).casefold():',
        "test_an_undated_museum_without_a_decision_is_refused_not_pending",
        SCOPE_TESTS,
    ),
    Case(
        "audit-fix: m13 a UUID may end in a newline",
        PLAN,
        r'[0-9a-f]{12}\Z")',
        r'[0-9a-f]{12}$")',
        "test_a_uuid_with_a_trailing_newline_is_not_a_uuid",
    ),
    Case(
        "audit-fix: m13 a lane constant may end in a newline",
        LANE,
        r'_KEY_PREFIX = re.compile(r"^[a-z0-9-]+\Z")',
        r'_KEY_PREFIX = re.compile(r"^[a-z0-9-]+$")',
        "test_a_lane_constant_with_a_trailing_newline_is_refused",
    ),
    Case(
        "audit-fix: M10 the curated name match sends a Python key",
        REPO / "pipeline/lyra/site_identifier.py",
        "    site_ids = _match_site_ids(session, site_name)",
        "    site_ids = _match_site_ids(session, normalized)",
        "test_the_raw_name_goes_to_the_postgres_key",
        "tests/pipeline/test_site_match_key.py",
    ),
    Case(
        "audit-fix: M10 the curated name match takes any source",
        REPO / "pipeline/lyra/site_identifier.py",
        '.filter(UnifiedSite.id.in_(site_ids), UnifiedSite.source_id == "ancient_nerds")',
        ".filter(UnifiedSite.id.in_(site_ids))",
        "test_no_python_key_is_compared_with_the_column",
        "tests/pipeline/test_site_match_key.py",
    ),
    Case(
        "audit-fix: m9 jsonl_lines splits at every line break",
        PROD_WRITE,
        '    return text.split("\\n")',
        "    return text.splitlines()",
        "test_every_psql_json_reader_splits_at_lf_only",
        PROD_TESTS,
    ),
    Case(
        "audit-fix: m9 the tagged export splits at every line break",
        PLAN,
        "    for line in jsonl_lines(text):",
        "    for line in text.splitlines():",
        "test_every_psql_json_reader_splits_at_lf_only",
        PROD_TESTS,
    ),
    Case(
        "audit-fix: m9 the JSON reader splits at every line break",
        PLAN,
        "for line in jsonl_lines(proc.stdout) if line.strip()]",
        "for line in proc.stdout.splitlines() if line.strip()]",
        "test_every_psql_json_reader_splits_at_lf_only",
        PROD_TESTS,
    ),
]
CASES += AUDIT_FIX_CASES


# ------------------------------------------------------ the WD1 structured-field lane (2026-09-26)
FIELDS = REPO / "scripts/remediation/fields"
FIELDS_LANE_TESTS = "tests/remediation/test_mechanical_fields_lane.py"
FIELDS_ANSWER_TESTS = "tests/remediation/test_fields_answers.py"
FIELDS_CLASSIFY_TESTS = "tests/remediation/test_fields_classify.py"
FIELDS_HANDOFF_TESTS = "tests/remediation/test_fields_handoff.py"
FIELDS_PLAN_TESTS = "tests/remediation/test_fields_plan.py"

#: What the mechanical writer gained for WD1 (a column a lane may empty, the coordinate types, site
#: invariants) and WD1's own guards (the answer checks, the identity rule, the write plan's
#: refusals, the step gate). Every label starts with "wd1:", so the list runs on its own:
#: `mutation_sweep.py wd1:`.
WD1_CASES: list[Case] = [
    guard(
        "wd1: plan-side NULL to NULL is no change",
        APPLY,
        "    if r.old_value is None and r.new_value is None:",
        "test_null_to_null_is_no_change",
        FIELDS_LANE_TESTS,
    ),
    guard(
        "wd1: plan-side an emptied cell owns no value",
        APPLY,
        "    if lane_value is None:",
        "test_an_emptied_owned_cell_owns_no_value",
        FIELDS_LANE_TESTS,
    ),
    guard(
        "wd1: plan-side a double is read as a number",
        APPLY,
        '    if cell.sql_type == "double precision":',
        "test_a_double_is_compared_as_a_number",
        FIELDS_LANE_TESTS,
    ),
    guard(
        "wd1: guard 2 refuses NULL where a column does not clear",
        APPLY,
        "        if not cell.clears:",
        "test_guard_2_lets_a_clearing_column_end_in_null",
        FIELDS_LANE_TESTS,
    ),
    Case(
        "wd1: site invariants run on the write only",
        APPLY,
        "    for invariant in () if rollback else lane.site_invariants:",
        "    for invariant in lane.site_invariants:",
        "test_the_site_invariants_run_after_the_write_and_only_on_the_write",
        FIELDS_LANE_TESTS,
    ),
    Case(
        "wd1: site invariants are rendered",
        APPLY,
        "    for invariant in () if rollback else lane.site_invariants:",
        "    for invariant in ():",
        "test_the_site_invariants_run_after_the_write_and_only_on_the_write",
        FIELDS_LANE_TESTS,
    ),
    Case(
        "wd1: every invariant gets its probe",
        APPLY,
        "    for invariant in lane.site_invariants:\n        # the first planned cell",
        "    for invariant in ():\n        # the first planned cell",
        "test_each_invariant_gets_a_probe_that_breaks_it",
        FIELDS_LANE_TESTS,
    ),
    guard(
        "wd1: a site invariant's message is checked",
        LANE,
        "        if not _SAYS.match(self.says):",
        "test_a_site_invariant_is_checked_before_it_is_spliced",
        FIELDS_LANE_TESTS,
    ),
    guard(
        "wd1: site invariants belong to a cell lane",
        LANE,
        "            if self.site_invariants:",
        "test_a_site_invariant_is_checked_before_it_is_spliced",
        FIELDS_LANE_TESTS,
    ),
    guard(
        "wd1: answers rest on two families",
        FIELDS / "answers.py",
        "    if len(quotes) < 2 or len({source_family(q.url) for q in quotes}) < 2:",
        "test_keep_and_replace_rest_on_two_families",
        FIELDS_ANSWER_TESTS,
    ),
    guard(
        "wd1: a replaced point moves more than a kilometre",
        FIELDS / "answers.py",
        "    if answer.decision == REPLACE and distance <= KEEP_KM:",
        "test_replace_moves_more_than_a_kilometre",
        FIELDS_ANSWER_TESTS,
    ),
    guard(
        "wd1: a coarse coordinate quote cannot place a site",
        FIELDS / "answers.py",
        "    if step > MAX_GRID * (1 + 1e-9):",
        "test_a_coarse_quote_is_read_within_its_own_digits",
        FIELDS_ANSWER_TESTS,
    ),
    guard(
        "wd1: a period quote carries a date",
        FIELDS / "answers.py",
        "        if not dated(quote):",
        "test_every_quote_carries_a_date",
        FIELDS_ANSWER_TESTS,
    ),
    guard(
        "wd1: a type is quoted by its word",
        FIELDS / "answers.py",
        "    if not any(s in fold(q, keep_parentheses=True) for _, q in answer.quotes for s in stems):",
        "test_a_type_that_is_not_canonical_or_not_quoted_is_refused",
        FIELDS_ANSWER_TESTS,
    ),
    guard(
        "wd1: a source_url is quoted from its own page",
        FIELDS / "answers.py",
        "    if not any(Q.canonical_url(url)[0] == Q.canonical_url(value)[0] for url, _ in answer.quotes):",
        "test_what_a_source_url_value_may_not_be",
        FIELDS_ANSWER_TESTS,
    ),
    Case(
        "wd1: a container puts the item in doubt",
        FIELDS / "classify.py",
        "    return Identity(bool(containers) and not held, containers)",
        "    return Identity(False, containers)",
        "test_a_container_that_holds_no_stored_type_puts_the_item_in_doubt",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: a specific class speaks before a generic one",
        FIELDS / "classify.py",
        "    if specific:\n        labels = ",
        "test_a_generic_type_beside_a_specific_class_is_a_downgrade",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: a section redirect is a conflict",
        FIELDS / "classify.py",
        '        if record["fragment"]:',
        "test_what_makes_an_article_a_conflict",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: the harvest and the stored export are one state",
        FIELDS / "classify.py",
        "        if not _agrees(site, row):",
        "test_a_harvest_and_an_export_of_different_states_are_refused",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: a quote that is not found does not count",
        FIELDS / "handoff.py",
        "            if failed:",
        "test_a_quote_not_on_its_page_is_asked_again",
        FIELDS_HANDOFF_TESTS,
    ),
    guard(
        "wd1: the import refuses an edited prompt",
        FIELDS / "handoff.py",
        '            if OH.prompt_sha256(prompt) != line["prompt_sha256"]:',
        "test_an_edited_prompt_is_refused_at_import",
        FIELDS_HANDOFF_TESTS,
    ),
    Case(
        "wd1: an exhausted point is held, not cleared",
        FIELDS / "handoff.py",
        '"decision": A.UNRESOLVED if field == "coordinates" else A.CLEAR,',
        '"decision": A.CLEAR,',
        "test_after_the_last_round_a_field_is_cleared_and_a_point_held",
        FIELDS_HANDOFF_TESTS,
    ),
    guard(
        "wd1: a point that crosses a border is held",
        FIELDS / "plan.py",
        '            if not country["agrees"]:',
        "test_a_point_that_crosses_a_border_is_held",
        FIELDS_PLAN_TESTS,
    ),
    guard(
        "wd1: a decision about another value is refused",
        FIELDS / "plan.py",
        "        if current_text != stored_text:",
        "test_a_decision_about_another_value_is_refused",
        FIELDS_PLAN_TESTS,
    ),
    guard(
        "wd1: a start after the end is refused",
        FIELDS / "plan.py",
        "            if new is not None and end is not None and int(end) != 0 and int(new) > int(end):",
        "test_a_start_after_the_end_is_refused",
        FIELDS_PLAN_TESTS,
    ),
    guard(
        "wd1: a label follows its start",
        FIELDS / "plan.py",
        '    if label != live["period_name"]:',
        "test_a_label_follows_an_unchanged_start",
        FIELDS_PLAN_TESTS,
    ),
    guard(
        "wd1: a step waits for the one before it",
        FIELDS / "plan.py",
        "    if not accepted.exists():",
        "test_a_step_waits_for_the_one_before_it",
        FIELDS_PLAN_TESTS,
    ),
    guard(
        "wd1: a deviation refuses the step",
        FIELDS / "plan.py",
        "    if found:",
        "test_any_deviation_refuses_the_step",
        FIELDS_PLAN_TESTS,
    ),
    guard(
        "wd1: a stacked point is a conflict",
        FIELDS / "classify.py",
        "    if stacked:",
        "test_a_stacked_point_is_a_conflict_whatever_the_witnesses",
        FIELDS_CLASSIFY_TESTS,
    ),
    Case(
        "wd1: a retired site stacks nothing",
        FIELDS / "classify.py",
        '        if row["scope_status"] != "retired"\n    )',
        "    )",
        "test_a_point_another_live_site_holds_is_stacked",
        FIELDS_CLASSIFY_TESTS,
    ),
    Case(
        "wd1: a flag asks its field",
        FIELDS / "classify.py",
        "        return self.status in ASKED or bool(self.flags)",
        "        return self.status in ASKED",
        "test_a_flag_asks_a_field_the_machine_confirms",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: the seeds file must exist",
        FIELDS / "classify.py",
        '    if not path.exists():\n        raise ClassifyError(f"{path} is missing - run `seeds.py',
        "test_the_seeds_must_be_there_and_well_formed",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: a seed names a WD1 field",
        FIELDS / "classify.py",
        '        if tuple(seed) != SEED_KEYS or seed["field"] not in FIELDS:',
        "test_the_seeds_must_be_there_and_well_formed",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: an empty source_url is asked",
        FIELDS / "classify.py",
        "    if kind == H.URL_NONE:",
        "test_no_url_is_asked_for_and_a_search_url_is_a_conflict",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: a stale url record is refused",
        FIELDS / "harvest.py",
        '    if record["source_url"] != site["source_url"]:\n        raise HarvestError(',
        "test_a_record_of_another_url_is_asked_again_and_never_read",
        "tests/remediation/test_fields_harvest.py",
    ),
    guard(
        "wd1: a stale url record is asked again",
        FIELDS / "harvest.py",
        '        if record["source_url"] != site["source_url"]:\n            return True',
        "test_a_record_of_another_url_is_asked_again_and_never_read",
        "tests/remediation/test_fields_harvest.py",
    ),
    guard(
        "wd1: a canary is no seed",
        FIELDS / "seeds.py",
        '        if (str(row["site_id"]), str(row["field"])) in planted:',
        "test_a_counted_wrong_verdict_on_a_wd1_field_is_a_seed",
        "tests/remediation/test_fields_seeds.py",
    ),
    guard(
        "wd1: B13 takes only its two reasons",
        FIELDS / "seeds.py",
        '        if row["reason"] not in WRONG_BOTH_REASONS:',
        "test_only_the_two_open_reasons_are_seeds",
        "tests/remediation/test_fields_seeds.py",
    ),
    Case(
        "wd1: a part takes only its own sites",
        FIELDS / "classify.py",
        '        lines = [line for line in lines if in_conflict_part(line) == (part == "conflict")]',
        "        lines = list(lines)",
        "test_the_two_parts_split_the_sites_by_conflict_or_flag",
        FIELDS_CLASSIFY_TESTS,
    ),
    guard(
        "wd1: the prompt shows a flag",
        FIELDS / "handoff.py",
        '        if status["flags"]:',
        "test_a_flag_and_an_empty_field_are_shown",
        FIELDS_HANDOFF_TESTS,
    ),
]
CASES += WD1_CASES


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
