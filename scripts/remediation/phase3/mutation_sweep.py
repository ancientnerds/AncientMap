"""Mutation proofs for the discover pass (piece 5) and its question.

For every guard: back the file up, break exactly that guard, run the one test that is supposed to
catch it, restore, and prove the restore is byte-identical (sha256). Nothing here uses git.

**Run this from a parent process, never from inside a subagent lane.** A lane that is killed on its
30-minute ceiling between applying a mutation and restoring it leaves the mutant in the working tree,
and the tree then looks like finished work - which is exactly what happened to piece 5 (`runs/gold`,
2026-09-21: `snapshot_plan.py` was delivered with mutation 3 still applied). The sweep restores
cleanly when it is allowed to finish; the hazard is being killed mid-flight.

Usage:
    ./.venv/Scripts/python.exe scripts/remediation/phase3/mutation_sweep.py          # all
    ./.venv/Scripts/python.exe scripts/remediation/phase3/mutation_sweep.py silence  # by substring
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / ".venv" / "Scripts" / "python.exe"
BACKUP = REPO / "output" / "remediation" / "logs" / "phase3_mutations" / "backup"
TEST = "tests/remediation/test_phase3_discover.py"
FETCH_TEST = "tests/remediation/test_phase3_fetch.py"
MASSRUN_TEST = "tests/remediation/test_phase3_massrun.py"
MODEL_TEST = "tests/remediation/test_phase3_model.py"
RUNNER_TEST = "tests/remediation/test_phase3_runner.py"
PACE = "test_two_processes_take_turns_on_one_host"
PACE_HOSTS = "test_one_host_waiting_does_not_hold_up_another"
PACE_STALE = "test_a_lock_left_by_a_killed_process_is_taken_over"
PACE_EMPTY = "test_a_lock_file_that_cannot_say_when_it_was_taken_is_not_a_leftover_yet"
PACE_OLD = "test_a_lock_file_that_cannot_say_when_it_was_taken_and_is_old_is_taken_over"
PACE_UNDELETABLE = "test_a_lock_that_cannot_be_deleted_is_waited_out_not_spun_on"
PACE_FOREIGN = "test_a_lock_whose_content_is_not_ours_is_not_deleted_by_us"
PACE_WIRED = "test_the_pace_covers_the_probe_and_the_targets_alike"

REVIEW_TEST = "tests/remediation/test_phase3_review.py"
#: The reviewer's own tests, one per guard (piece 6a). Each name below is the test that must fail
#: when the mutation next to it is applied - a mutation no test can catch is noise, not evidence.
REVIEWER = "test_judge_refuses_the_reviewer_stage_when_the_batch_carries_no_finding"
REVIEW_EMPTY_ANSWERS = "test_judge_refuses_the_reviewer_stage_when_the_answers_folder_is_empty"
REVIEW_ROUTED = "test_judge_reviews_a_batch_that_carries_the_finders_findings"
REVIEW_COUNTS = "test_the_report_counts_what_the_verdicts_say"
REVIEW_UNRESOLVED = "test_unresolved_is_neither_refuted_nor_not_refuted"
REVIEW_RESUMED = "test_a_review_already_on_disk_is_read_and_not_bought_again"
REVIEW_ONLY_WRONG = "test_only_a_complete_wrong_finding_is_asked_about"
REVIEW_NO_ANSWER = "test_a_field_the_finder_never_answered_is_recorded_not_silently_skipped"
REVIEW_VERBATIM = "test_the_prompt_carries_the_finders_answer_verbatim_and_the_same_page"
REVIEW_OWN_REPORT = (
    "test_the_reviewer_writes_its_own_report_and_leaves_the_finders_model_json_alone"
)
LEDGER_LOCK = "test_a_second_writer_never_costs_a_ledger_line"
REVIEW_SHAPE = "test_the_reviewer_question_asks_for_the_verdict_line_the_parser_wants"
REVIEW_KNOWLEDGE = "test_the_reviewer_question_lets_its_own_knowledge_refute_a_finding"
REVIEW_KNOWLEDGE_NO_SOURCE = "test_a_refutation_from_the_reviewers_own_knowledge_needs_no_source"
REVIEW_HALVES = "test_the_reviewer_question_names_both_ways_a_finding_can_fail"
REVIEW_BRIEFING = "test_the_reviewer_is_briefed_on_every_false_alarm_the_plan_lists"
REVIEW_NUMBERED = "test_a_numbered_verdict_line_is_still_a_verdict"

RUN = "test_every_site_buys_one_call_per_field_and_the_call_names_its_field"
ROUTE = "test_the_discover_routing_is_enwiki_by_name_and_wikidata_by_the_qid"
EMPTY = "test_an_empty_stored_value_is_marked_absent_and_the_question_calls_it_wrong"
BIG = "test_an_oversized_site_becomes_its_own_unverifiable_outcome_and_the_batch_carries_on"
NEVER = "test_a_field_whose_evidence_was_never_fetched_is_recorded_not_attempted_and_the_batch_carries_on"
TABLE = "test_every_planned_value_comes_from_the_table_truth_fields_json_names"
NAMELESS = "test_a_snapshot_row_without_a_name_or_without_an_id_is_refused"
LIVE = "test_judge_live_stores_one_answer_per_field_and_one_ledger_line_each"
UNKNOWN = "test_judge_refuses_a_pass_marker_it_does_not_know"
TWO_INPUTS = "test_plan_refuses_the_two_inputs_at_once_and_site_ids_without_the_snapshot_flag"
ANCHOR = "test_the_worklist_plan_still_hashes_to_the_piece_1_anchor"
SNAPSHOT_PLAN = "test_the_snapshot_plan_is_byte_identical_across_runs_and_covers_all_5004_sites"
PREPARE = "test_prepare_writes_the_discover_pass_marker_verbatim"
ORDER = "test_the_question_asks_for_the_evidence_before_the_verdict"
REASON = "test_an_answer_without_a_reason_sentence_is_a_problem"
SILENCE = "test_the_question_refuses_silence_as_agreement"
KNOWLEDGE = "test_the_question_forbids_upholding_a_value_with_the_finders_own_knowledge"
PRECEDENCE = "test_the_field_clause_is_stated_to_beat_the_general_rules"
VOCAB = "test_the_site_type_question_carries_the_catalogues_own_value_list"
VOCAB_REFUSAL = "test_the_site_type_question_refuses_to_be_built_without_the_value_list"
SPANS = "test_the_period_question_gives_the_bucket_spans_and_not_only_lower_bounds"
#: The correction-and-source guards of 2026-09-21: the model must propose a value and cite a page the
#: run itself fetched, so "with sources" is checked rather than believed. One name per guard - a
#: single test with three assertions proves the suite fails, not which guard caught it.
CORRECTION = "test_the_question_asks_for_a_correction_and_names_where_it_must_come_from"
SOURCE_REQUIRED = "test_a_wrong_answer_without_a_source_is_a_problem"
QUOTE_FOLD = "test_a_quote_is_recognised_across_the_differences_a_retyping_has"
QUOTE_ESCAPE = "test_a_quote_is_recognised_across_json_escapes_in_the_evidence"
UNFETCHED_SOURCE = "test_a_cited_page_the_run_did_not_fetch_is_a_problem"
BUDGET = "test_the_call_ceiling_stops_between_batches_and_names_what_was_not_reached"
BREAKER = "test_the_circuit_breaker_trips_after_the_configured_number_of_failures"
BREAKER_RESET = "test_a_success_clears_the_failure_count"
SPAWN_RETRY = "test_a_start_failure_is_retried_and_the_stage_then_succeeds"
TORN_JSON = "test_a_truncated_model_json_is_broken_and_never_done"
LEDGER_COST = "test_a_cost_that_is_not_a_finite_number_is_damage_and_not_a_zero"
MISSING_ANSWER = "test_a_written_judgement_without_its_answer_file_is_broken"
DIGEST_GUARD = "test_the_source_digest_guard_stops_a_run_whose_sources_changed"
ATOMIC = "test_a_crash_between_the_write_and_the_swap_leaves_the_previous_progress_intact"
DRY_RUN = "test_a_dry_run_buys_nothing_and_leaves_the_ledger_exactly_as_it_was"
PREPARE_PLAN = "test_prepare_is_given_the_plan_and_neither_the_ledger_nor_live"
REAL_CLI = "test_every_stage_argv_is_accepted_by_the_real_cli"
CEILING_BASELINE = "test_a_ceiling_means_this_run_and_not_the_ledgers_whole_history"
PACE_COMMAND = "test_the_live_fetch_command_paces_its_requests_across_processes"
PACE_OFF = "test_an_empty_pacing_dir_paces_nothing"
PACE_DRIVER = "test_the_driver_tells_fetch_which_pace_directory_to_use"
PACE_DRIVER_OFF = "test_the_driver_can_be_told_not_to_pace"
SWEEP_TEST = "tests/remediation/test_phase3_sweep.py"
SWEEP_UNREADABLE = "test_a_child_whose_output_cannot_be_read_does_not_kill_the_sweep"
SWEEP_MISSED = "test_a_mutation_that_is_not_caught_is_still_undone"
BOUND_MEASURED = "test_the_evidence_bound_is_above_every_site_the_recall_fixture_measured"
DRIFT = "test_final_drift_names_a_file_that_changed_under_the_sweep"
#: The host's own number: `Retry-After` (RFC 9110 section 10.2.3), 2026-09-21. The host decides how
#: long we wait, our own backoff is only the floor, and a host that asks for longer than this run
#: will block on one host is given up on rather than re-asked sooner than it asked. One name per
#: guard - a guard without a test that catches it is not a guard.
RETRY_AFTER_WAIT = "test_a_host_that_asks_for_longer_than_the_backoff_gets_that_longer_pause"
RETRY_AFTER_CAP = "test_a_host_asking_for_longer_than_the_cap_is_left_alone_not_re_asked"
RETRY_AFTER_UNREADABLE = "test_a_retry_after_that_cannot_be_read_is_treated_as_absent"
RETRY_AFTER_ASCII = "test_delay_seconds_are_ascii_digits_by_the_grammars_own_rule"
RETRY_AFTER_DATE = "test_the_other_form_the_field_may_have_is_an_http_date"
RETRY_AFTER_FLOOR = "test_a_retry_after_of_zero_does_not_shorten_our_own_backoff"

WRITE_TEST = "tests/remediation/test_phase3_write.py"
#: The writer's own guards (piece 6). One guard, one test that must fail when the guard is broken - a
#: mutation no test can catch is noise, not evidence.
WRITE_PLAN = "test_the_plan_takes_the_new_value_from_the_answer_and_the_old_one_from_the_batch"
WRITE_REFUTED = "test_a_refuted_verdict_is_refused_and_counted_as_not_cleared"
WRITE_APPLIES = "test_a_verdict_whose_parts_refute_it_is_not_cleared_by_its_own_applies_flag"
WRITE_NO_VERDICT = "test_a_field_without_a_verdict_is_refused_rather_than_forgotten"
WRITE_REPORT_ONLY = "test_the_report_only_fields_are_refused_though_the_reviewer_cleared_them"
WRITE_REPORT_REASONS = "test_the_two_report_only_reasons_stay_apart"
WRITE_FIXED_POINT = "test_a_site_type_the_normaliser_would_rewrite_is_refused"
WRITE_FIXED_POINT_OK = "test_a_site_type_that_is_a_fixed_point_is_planned"
WRITE_COUNTRY = "test_a_country_is_writable_because_its_patcher_guards_on_the_source"
WRITE_PATCHERS = "test_the_two_startup_patchers_really_guard_their_updates_on_the_lyra_source"
WRITE_PERIOD = "test_a_period_start_that_is_not_a_year_is_refused_before_the_transaction"
WRITE_WIDTH = "test_a_country_longer_than_the_column_is_refused_before_the_transaction"
WRITE_NOT_A_CHANGE = "test_a_value_the_row_already_holds_is_not_a_change"
WRITE_INCOMPLETE = "test_an_answer_the_parser_calls_incomplete_is_refused_with_what_was_missing"
WRITE_NOT_WRONG = "test_a_finder_answer_that_is_not_wrong_has_nothing_to_write"
WRITE_EVIDENCE = "test_the_evidence_carries_the_finders_citations_and_the_reviewers_reason"
WRITE_KEY = "test_the_change_key_is_a_digest_of_the_transition_not_of_the_row"
WRITE_READ_STMT = "test_the_read_statement_names_the_row_its_column_and_refuses_an_unwritable_one"
WRITE_VALIDATE = "test_a_plan_side_row_that_is_not_a_real_change_is_refused"
WRITE_DEFAULT = "test_the_default_step_is_the_owners_hundred_rows"
WRITE_CHUNK_ORDER = "test_chunks_cut_the_plan_in_its_own_order_and_share_the_batch_id"
WRITE_CHUNK_ZERO = "test_a_chunk_size_below_one_is_refused"
WRITE_NO_CHUNK = "test_an_empty_plan_yields_no_chunk"
WRITE_DIGEST = "test_every_chunk_carries_a_digest_over_its_own_rows"
WRITE_STAMP = "test_the_run_stamp_names_the_batch_and_the_chunk_and_the_reversal_gets_its_own"
WRITE_COMMIT = "test_the_write_statement_ends_in_commit_and_the_reversal_in_rollback"
WRITE_STOP = "test_both_statements_set_on_error_stop"
WRITE_ARGS = "test_the_loop_calls_the_primitive_with_the_twelve_arguments_in_order"
WRITE_CURATED = "test_the_write_guard_keeps_the_write_inside_the_curated_source"
WRITE_CHANGE_GUARD = "test_the_write_guard_refuses_a_value_that_is_not_a_change"
WRITE_COMPARE = "test_every_writable_column_has_a_comparison_in_the_guards"
WRITE_JOURNAL = "test_the_journal_invariant_covers_both_directions"
WRITE_REVERSAL = "test_the_reversal_carries_the_values_swapped_and_its_own_change_key"
WRITE_FILES = "test_the_plan_file_is_written_line_by_line_and_the_refusals_beside_it"
WRITE_PIN = "test_the_apply_refuses_a_statement_that_was_generated_from_other_rows"
WRITE_UNRENDERED = "test_the_apply_refuses_when_the_statements_were_never_rendered"
WRITE_MOVED = "test_a_row_that_moved_since_the_snapshot_is_recorded_and_nothing_is_written"
WRITE_LEFT_SOURCE = "test_a_site_that_left_the_curated_source_is_not_written"
WRITE_PREFLIGHT_FIRST = "test_a_pre_flight_that_agrees_sends_the_read_first_and_then_the_write"
WRITE_KEPT_WRITE = "test_the_reversal_leaves_the_write_exactly_as_it_was"
WRITE_READBACK = "test_a_value_the_database_kept_differently_is_a_stop"
WRITE_OUTSIDE_JOURNAL = "test_a_journal_row_outside_the_plan_is_a_stop"
WRITE_KEPT_REVERSAL = "test_a_reversal_that_is_kept_is_a_stop"
WRITE_REPORT = "test_the_report_counts_the_refusals_by_rule_and_names_the_fixed_points"
WRITE_DRY = "test_a_dry_run_sends_nothing_to_the_database"
WRITE_MAIN = "test_main_applies_through_the_seam_and_reports_the_numbers"
WRITE_NO_SUCH_CHUNK = "test_main_refuses_a_chunk_number_the_plan_does_not_have"
WRITE_OTHER_BATCH = "test_the_plan_refuses_a_review_that_names_another_batch"
WRITE_ONLY_DISCOVER = "test_the_plan_refuses_a_batch_that_is_not_the_discover_pass"
WRITE_MISSING = "test_reading_a_missing_batch_directory_says_which_file_is_missing"
WRITE_STAGE = "scripts/remediation/phase3/write_stage.py"

#: The named holes (2026-09-21). Measured: the mass run over 5,004 sites died in 4 of its 334
#: batches because one call's stream came back unreadable, and each death took the answers already
#: on disk with it (`output/remediation/logs/mass/batch-0143.judge.log`). A hole is now a recorded
#: `model_stage.FailedCall` beside the judgements - and "settled" must not become "anything goes":
#: a truncated `model.json` is still not done. One guard, one test that must fail without it.
MODEL_HOLE = "test_an_unreadable_stream_is_a_named_failure_and_the_batch_carries_on"
MODEL_TRANSPORT = "test_a_run_stops_at_the_first_call_it_could_not_measure"
MODEL_HOLE_CLI = "test_judge_live_records_an_unreadable_stream_as_a_hole_and_exits_zero"
#: One guard, one test: `judge_site` reuses the answer that is already on disk instead of asking
#: again. Without the guard the model is paid a second time for a settled question and `write`
#: refuses the second bytes, which is exactly how three consecutive mass-run batches ended on
#: 2026-09-21 and tripped the circuit breaker at 130 of 334 batches.
MODEL_REUSE = "test_a_question_whose_answer_is_already_on_disk_is_not_asked_again"
DISCOVER_HOLE = "test_an_unreadable_stream_for_one_field_is_a_hole_and_the_other_calls_are_bought"
DISCOVER_HOLE_REVIEW = "test_the_reviewer_does_not_clear_a_field_whose_finder_call_was_a_hole"
MASSRUN_HOLE = "test_a_named_failure_counts_as_settled_and_the_batch_is_done"
MASSRUN_HOLE_COUNT = "test_a_model_json_that_lost_a_call_is_broken_even_with_an_empty_failures_list"
MASSRUN_HOLE_VERDICT = "test_a_failure_that_carries_a_verdict_is_not_a_named_failure"
MASSRUN_HOLE_SHAPE = "test_a_failures_list_of_bare_strings_is_broken_rather_than_settled"
WRITE_HOLE = "test_a_field_whose_finder_call_was_a_hole_is_refused_and_no_row_is_planned"

#: (name, file, the exact text to replace, what to replace it with, test file, test name)
MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "reversed field order",
        "scripts/remediation/phase3/discover_stage.py",
        "for name in DISCOVER_FIELDS\n    ]",
        "for name in reversed(DISCOVER_FIELDS)\n    ]",
        TEST,
        RUN,
    ),
    (
        "card_description read from unified_sites",
        "scripts/remediation/phase3/snapshot_plan.py",
        '"card_description": "card_stats",',
        '"card_description": "unified_sites",',
        TEST,
        TABLE,
    ),
    (
        "country dropped from the planned fields",
        "scripts/remediation/phase3/snapshot_plan.py",
        '    "site_type",\n    "country",\n    "card_description",\n)',
        '    "site_type",\n    "card_description",\n)',
        TEST,
        RUN,
    ),
    (
        "over-bound evidence no longer becomes the site's own outcome",
        "scripts/remediation/phase3/discover_stage.py",
        "    try:\n        MS.check_evidence_bound(site_id, excerpts)\n    except MS.EvidenceOverBound as exc:\n"
        "        skipped = [_over_bound_skip(site, field=name, exc=exc) for name in DISCOVER_FIELDS]\n"
        "        return DiscoverPlan(skipped=skipped)\n",
        "    MS.check_evidence_bound(site_id, excerpts)\n",
        TEST,
        BIG,
    ),
    (
        "answer key is the stage, not the field",
        "scripts/remediation/phase3/model_stage.py",
        "return self.field or self.stage.value",
        "return self.stage.value",
        TEST,
        LIVE,
    ),
    (
        "the question no longer asks about a missing value",
        "scripts/remediation/phase3/discover_stage.py",
        'or the field stores no value where one "',
        'or the field stores a value where one "',
        TEST,
        EMPTY,
    ),
    (
        "every value marked present",
        "scripts/remediation/phase3/discover_stage.py",
        "    absent = value is None or (isinstance(value, str) and not value.strip())",
        "    absent = False",
        TEST,
        EMPTY,
    ),
    (
        "the verdict is asked for before the evidence statement",
        "scripts/remediation/phase3/discover_stage.py",
        '    "1. One sentence saying what the evidence in this message gives for this field - the value it "\n'
        '    "states, or the word `silent` if it states nothing about this field.\\n"\n'
        '    "2. Then the verdict line.\\n"\n'
        '    "\\n"\n'
        '    "VERDICT: CORRECT | WRONG | UNVERIFIABLE\\n"\n',
        '    "VERDICT: CORRECT | WRONG | UNVERIFIABLE\\n"\n'
        '    "\\n"\n'
        '    "1. One sentence saying what the evidence in this message gives for this field - the value it "\n'
        '    "states, or the word `silent` if it states nothing about this field.\\n"\n'
        '    "2. Then the verdict line.\\n"\n',
        TEST,
        ORDER,
    ),
    (
        "silence counts as agreement",
        "scripts/remediation/phase3/discover_stage.py",
        '**Silence is not "',
        '**Silence is sometimes "',
        TEST,
        SILENCE,
    ),
    (
        "the finder's own knowledge may uphold a stored value",
        "scripts/remediation/phase3/discover_stage.py",
        'Your own knowledge of the subject is not "',
        'Your own knowledge of the subject may be "',
        TEST,
        KNOWLEDGE,
    ),
    (
        "no qid, no qid skip: the entity route is asked anyway",
        "scripts/remediation/phase3/fetch_stage.py",
        "            if feature == FEATURE_WIKIDATA_ENTITY and not qid:\n                continue\n",
        "",
        TEST,
        ROUTE,
    ),
    (
        "duplicate snapshot ids accepted",
        "scripts/remediation/phase3/snapshot_plan.py",
        "    duplicates = len(ids_in_order) - len(set(ids_in_order))\n"
        "    if duplicates:\n"
        "        raise InputError(\n"
        '            f"{unified_path}: {duplicates} duplicate site id(s); a repeated row would be planned "\n'
        '            "twice and its calls bought twice"\n'
        "        )\n",
        "",
        TEST,
        NAMELESS,
    ),
    (
        "a site with no readable evidence is judged anyway",
        "scripts/remediation/phase3/discover_stage.py",
        "        if not any(e.present for e in item.excerpts):",
        "        if False:",
        TEST,
        NEVER,
    ),
    (
        "--site-ids accepted without --from-snapshot",
        "scripts/remediation/phase3/run.py",
        '    if args.site_ids:\n        raise InputError(\n            "--site-ids selects sites of the snapshot plan; without --from-snapshot it means "\n'
        '            "nothing, and the worklist plan ignores it"\n        )\n',
        "",
        TEST,
        TWO_INPUTS,
    ),
    (
        "a reviewer pass runs over a batch the finder never judged",
        "scripts/remediation/phase3/run.py",
        "        if not _has_answers(answers_root):\n",
        "        if False:  # mutated\n",
        TEST,
        REVIEWER,
    ),
    (
        "an empty answers folder counts as a batch of findings",
        "scripts/remediation/phase3/run.py",
        '    return any(root.glob("*.txt"))\n',
        "    return True  # mutated\n",
        TEST,
        REVIEW_EMPTY_ANSWERS,
    ),
    (
        "the reviewer stage is never routed",
        "scripts/remediation/phase3/run.py",
        "    if args.stage == Stage.REVIEWER.value:\n",
        "    if False:  # mutated\n",
        TEST,
        REVIEW_ROUTED,
    ),
    (
        "a refutation's citation is not checked against the pages the run fetched",
        "scripts/remediation/phase3/review_stage.py",
        "        problems = answer.problems + DS.claim_problems(answer.sources, pages)\n",
        "        problems = list(answer.problems)  # mutated\n",
        REVIEW_TEST,
        REVIEW_COUNTS,
    ),
    (
        "the report follows the order the fields happened to be judged in",
        "scripts/remediation/phase3/review_stage.py",
        "        verdicts=sorted(verdicts, key=lambda v: (_field_rank(v.field), v.site_id)),\n",
        "        verdicts=verdicts,  # mutated\n",
        REVIEW_TEST,
        REVIEW_COUNTS,
    ),
    (
        "an unresolved refutation is treated as not refuted",
        "scripts/remediation/phase3/review_stage.py",
        "        return self.asked and self.refuted is False and not self.problems\n",
        "        return self.asked and not self.refuted and not self.problems  # mutated\n",
        REVIEW_TEST,
        REVIEW_UNRESOLVED,
    ),
    (
        "a review already on disk is bought again",
        "scripts/remediation/phase3/review_stage.py",
        '        if path.exists():\n            text = path.read_text(encoding="utf-8")\n            resumed += 1\n',
        '        if False:  # mutated\n            text = path.read_text(encoding="utf-8")\n            resumed += 1\n',
        REVIEW_TEST,
        REVIEW_RESUMED,
    ),
    (
        "a finding that proposes no change is reviewed anyway",
        "scripts/remediation/phase3/review_stage.py",
        "        if answer.verdict != REVIEWED_VERDICT:\n",
        "        if False:  # mutated\n",
        REVIEW_TEST,
        REVIEW_ONLY_WRONG,
    ),
    (
        "an unusable finding is reviewed anyway",
        "scripts/remediation/phase3/review_stage.py",
        "        if answer.problems:\n",
        "        if False:  # mutated\n",
        REVIEW_TEST,
        REVIEW_ONLY_WRONG,
    ),
    (
        "a field the finder never answered is dropped without a record",
        "scripts/remediation/phase3/review_stage.py",
        "        if not path.exists():\n            plan.unreviewable.append(\n",
        "        if False:  # mutated\n            plan.unreviewable.append(\n",
        REVIEW_TEST,
        REVIEW_NO_ANSWER,
    ),
    (
        "the finder's finding is not given to the reviewer",
        "scripts/remediation/phase3/review_stage.py",
        "            answer_text.strip(),\n",
        '            "",  # mutated\n',
        REVIEW_TEST,
        REVIEW_VERBATIM,
    ),
    (
        "the reviewer's report overwrites the finder's",
        "scripts/remediation/phase3/review_stage.py",
        "    tmp.replace(path)\n",
        '    tmp.replace(path.with_name("model.json"))  # mutated\n',
        REVIEW_TEST,
        REVIEW_OWN_REPORT,
    ),
    (
        "a discover batch judged with the finding-driven path",
        "scripts/remediation/phase3/run.py",
        '    if batch.get("pass") == DISCOVER_PASS:',
        "    if False:",
        TEST,
        LIVE,
    ),
    (
        "an unknown pass marker judged as the default",
        "scripts/remediation/phase3/run.py",
        '    if batch.get("pass") is not None:',
        "    if False:",
        TEST,
        UNKNOWN,
    ),
    (
        "the worklist plan grows a pass marker",
        "scripts/remediation/phase3/run.py",
        '        if self.pass_name is not None:\n            payload["pass"] = self.pass_name',
        '        if True:\n            payload["pass"] = self.pass_name or "worklist"',
        TEST,
        ANCHOR,
    ),
    (
        "the snapshot plan drops its pass marker",
        "scripts/remediation/phase3/run.py",
        "pass_name=DISCOVER_PASS)",
        "pass_name=None)",
        TEST,
        SNAPSHOT_PLAN,
    ),
    (
        "prepare drops the pass marker from the batch it copies",
        "scripts/remediation/phase3/run.py",
        '            json.dumps(batch, ensure_ascii=False, sort_keys=True) + "\\n",',
        '            json.dumps({k: v for k, v in batch.items() if k != "pass"}, ensure_ascii=False, sort_keys=True)\n            + "\\n",',
        TEST,
        PREPARE,
    ),
    # ── the three information defects the second live run exposed ────────────────────────────────
    (
        "the clause no longer beats the general rules",
        "scripts/remediation/phase3/discover_stage.py",
        '    "**The clause above defines what `matches` means for this field, and it beats the general rules "',
        '    "**The general rules below decide wherever the clause above appears to say otherwise. "',
        TEST,
        PRECEDENCE,
    ),
    (
        "the site_type question stops naming the catalogue's value list",
        "scripts/remediation/phase3/discover_stage.py",
        '        "{n} values: {vocabulary}. It has to survive the project\'s normaliser. The evidence will "',
        '        "several values. It has to survive the project\'s normaliser. The evidence will "',
        TEST,
        VOCAB,
    ),
    (
        "an empty value list is accepted instead of refused",
        "scripts/remediation/phase3/discover_stage.py",
        '    if "{vocabulary}" in clause:\n        if not vocabulary:',
        '    if "{vocabulary}" in clause:\n        if False:',
        TEST,
        VOCAB_REFUSAL,
    ),
    (
        "the period question goes back to lower bounds without the spans",
        "scripts/remediation/phase3/discover_stage.py",
        '        "`3000 - 1500 BC`; -1500 up to but not including -500 is `1500 - 500 BC`; -500 up to but "',
        '        "a bucket lower bound (-4500/-3000/-1500/-500/1/500/1000/1500); "',
        TEST,
        SPANS,
    ),
    (
        "bucket boundaries stated as closed ranges",
        "scripts/remediation/phase3/discover_stage.py",
        '        "but not including -3000 is `4500 - 3000 BC`; -3000 up to but not including -1500 is "',
        '        "but not including -3000 is `4500 - 3000 BC`; -3000 to -1500 is "',
        TEST,
        SPANS,
    ),
    (
        "the century conversion is dropped",
        "scripts/remediation/phase3/discover_stage.py",
        '        "evidence often names a century rather than a year, and the direction of BC years is easy to "\n'
        '        "invert: the 2nd century BC is -200 up to but not including -101, and the 4th century BC is "\n'
        '        "-400 up to but not including -301, so **both of those centuries fall in `500 BC - 1 AD` "\n'
        '        "and neither is in `1500 - 500 BC`**. Most sites "',
        '        "Most sites "',
        TEST,
        SPANS,
    ),
    (
        "the question stops asking for a correction value",
        "scripts/remediation/phase3/discover_stage.py",
        '    "PROPOSED: <the value this field should hold, in the field\'s own shape>\\n"\n',
        "",
        TEST,
        CORRECTION,
    ),
    (
        "a WRONG verdict no longer needs a source",
        "scripts/remediation/phase3/discover_stage.py",
        "        if not sources:",
        "        if False:  # mutated",
        TEST,
        SOURCE_REQUIRED,
    ),
    (
        "a quote is matched without folding whitespace and quote marks",
        "scripts/remediation/phase3/discover_stage.py",
        '    return " ".join(unescaped.translate(_QUOTE_FOLD).split()).casefold()',
        "    return unescaped",
        TEST,
        QUOTE_FOLD,
    ),
    (
        "a cited page the run never fetched is accepted",
        "scripts/remediation/phase3/discover_stage.py",
        "        page = pages.get(claim.url)\n        if page is None:",
        "        page = pages.get(claim.url)\n        if False:  # mutated",
        TEST,
        UNFETCHED_SOURCE,
    ),
    (
        "the JSON escapes in the evidence are not undone",
        "scripts/remediation/phase3/discover_stage.py",
        "    unescaped = _ESCAPE_RE.sub(_unescape_match, text)",
        "    unescaped = text",
        TEST,
        QUOTE_ESCAPE,
    ),
    (
        "the pacer lets two processes into one host at once",
        "scripts/remediation/phase3/fetch_stage.py",
        "        if wait > 0:\n            self._sleep(wait)\n",
        "        if False:  # mutated\n            self._sleep(wait)\n",
        FETCH_TEST,
        PACE,
    ),
    (
        "a lock left by a killed process wedges the fleet",
        "scripts/remediation/phase3/fetch_stage.py",
        "        return self._clock() - held_since > self._stale_after\n",
        "        return False  # mutated\n",
        FETCH_TEST,
        PACE_STALE,
    ),
    (
        "a lock whose content is not written yet is stolen",
        "scripts/remediation/phase3/fetch_stage.py",
        "            held_since = lock.stat().st_mtime\n",
        "            return True  # mutated\n",
        FETCH_TEST,
        PACE_EMPTY,
    ),
    (
        "a lock whose content is not written yet is taken over when it is old",
        "scripts/remediation/phase3/fetch_stage.py",
        "                held_since = lock.stat().st_mtime\n",
        "                return False  # mutated\n",
        FETCH_TEST,
        PACE_OLD,
    ),
    (
        "a lock that cannot be deleted aborts the fetch",
        "scripts/remediation/phase3/fetch_stage.py",
        "        except OSError:\n            return False  # held open somewhere (Windows refuses): wait, do not spin\n",
        "        except OSError:\n            raise  # mutated\n",
        FETCH_TEST,
        PACE_UNDELETABLE,
    ),
    (
        "a lock is deleted even when its content is not ours",
        "scripts/remediation/phase3/fetch_stage.py",
        '            if lock.read_text(encoding="utf-8").strip() != token:\n                return\n',
        "            if False:  # mutated\n                return\n",
        FETCH_TEST,
        PACE_FOREIGN,
    ),
    (
        "every host shares one stamp",
        "scripts/remediation/phase3/fetch_stage.py",
        "        stamp = self.stamp_of(host)\n",
        '        stamp = self.stamp_of("every-host")  # mutated\n',
        FETCH_TEST,
        PACE_HOSTS,
    ),
    (
        "the paced fetcher does not pace",
        "scripts/remediation/phase3/fetch_stage.py",
        "        self._pacer.wait(host_of(url))\n        return self._inner.get(url)\n",
        "        return self._inner.get(url)  # mutated\n",
        FETCH_TEST,
        PACE_WIRED,
    ),
    (
        "the call ceiling is not checked between batches",
        "scripts/remediation/phase3/mass_run.py",
        "        reason = budget.stop_reason(Spend.from_ledger(ledger), baseline=baseline)\n"
        "        if reason:\n            return reason\n",
        "        reason = budget.stop_reason(Spend.from_ledger(ledger), baseline=baseline)\n"
        "        if False:  # mutated\n            return reason\n",
        MASSRUN_TEST,
        BUDGET,
    ),
    (
        "the ceiling counts the ledger's whole history",
        "scripts/remediation/phase3/mass_run.py",
        "        bought = spend.calls - (baseline.calls if baseline is not None else 0)\n",
        "        bought = spend.calls  # mutated\n",
        MASSRUN_TEST,
        CEILING_BASELINE,
    ),
    (
        "a cost that is not a number is counted as zero",
        "scripts/remediation/phase3/mass_run.py",
        "                if isinstance(cost, bool) or not isinstance(cost, (int, float)):\n",
        "                if False:  # mutated\n",
        MASSRUN_TEST,
        LEDGER_COST,
    ),
    (
        "a negative or infinite cost is counted",
        "scripts/remediation/phase3/mass_run.py",
        "                if not math.isfinite(value) or value < 0:\n",
        "                if False:  # mutated\n",
        MASSRUN_TEST,
        LEDGER_COST,
    ),
    (
        "the fetch command does not pace its requests",
        "scripts/remediation/phase3/run.py",
        "    if args.pacing_dir:\n"
        "        fetcher = F.PacedFetcher(http, F.HostPacer(Path(args.pacing_dir)))\n",
        "    if False:  # mutated\n"
        "        fetcher = F.PacedFetcher(http, F.HostPacer(Path(args.pacing_dir)))\n",
        FETCH_TEST,
        PACE_COMMAND,
    ),
    (
        "an empty pacing directory is paced anyway",
        "scripts/remediation/phase3/run.py",
        "    if args.pacing_dir:\n"
        "        fetcher = F.PacedFetcher(http, F.HostPacer(Path(args.pacing_dir)))\n",
        "    if True:  # mutated\n"
        "        fetcher = F.PacedFetcher(http, F.HostPacer(Path(args.pacing_dir)))\n",
        FETCH_TEST,
        PACE_OFF,
    ),
    (
        "the child's output is decoded with the locale's codec",
        "scripts/remediation/phase3/mutation_sweep.py",
        '                encoding="utf-8",\n                errors="replace",\n',
        "",
        SWEEP_TEST,
        SWEEP_UNREADABLE,
    ),
    (
        "a mutation is restored only when the sweep itself fails",
        "scripts/remediation/phase3/mutation_sweep.py",
        "        finally:\n            shutil.copy2(backup, path)\n",
        "        except Exception:\n            shutil.copy2(backup, path)\n",
        SWEEP_TEST,
        SWEEP_MISSED,
    ),
    (
        "the driver does not pace its batches",
        "scripts/remediation/phase3/mass_run.py",
        '        if stage == "fetch" and self.pacing_dir is not None:\n'
        "            # Only `fetch` opens sockets, and with `--jobs N` the batches are separate *processes*, so\n"
        "            # an in-memory limiter would multiply the per-host rate by N - the politeness a pacer\n"
        "            # exists to keep. Hence a shared directory of lock files, and hence the driver being the\n"
        "            # one that names it: the driver is what creates concurrency.\n"
        '            argv += ["--pacing-dir", str(self.pacing_dir)]\n',
        "",
        MASSRUN_TEST,
        PACE_DRIVER,
    ),
    (
        "the pace cannot be switched off",
        "scripts/remediation/phase3/mass_run.py",
        '        if stage == "fetch" and self.pacing_dir is not None:\n',
        '        if stage == "fetch":\n',
        MASSRUN_TEST,
        PACE_DRIVER_OFF,
    ),
    (
        "the circuit breaker never trips",
        "scripts/remediation/phase3/mass_run.py",
        "        if consecutive >= failures_before_stop:\n",
        "        if False:  # mutated\n",
        MASSRUN_TEST,
        BREAKER,
    ),
    (
        "a success does not clear the failure count",
        "scripts/remediation/phase3/mass_run.py",
        "                if ok:\n                    consecutive = 0\n",
        "                if ok:\n                    consecutive = consecutive + 0  # mutated\n",
        MASSRUN_TEST,
        BREAKER_RESET,
    ),
    (
        "a failed start is not recognised, so the stage is never retried",
        "scripts/remediation/phase3/mass_run.py",
        "    if code >= NTSTATUS_START_FAILURE:\n        return True\n",
        "    if False:  # mutated: a failed start counts as any other failure\n        return True\n",
        MASSRUN_TEST,
        SPAWN_RETRY,
    ),
    (
        "an artefact that does not parse counts as done",
        "scripts/remediation/phase3/mass_run.py",
        '            return BROKEN, f"{name} does not parse: {exc}"\n',
        '            return DONE, f"{name} does not parse: {exc}"  # mutated\n',
        MASSRUN_TEST,
        TORN_JSON,
    ),
    (
        "a recorded answer that is not on disk still counts as done",
        "scripts/remediation/phase3/mass_run.py",
        "            return BROKEN, f\"answer missing for {row['site_id']}/{row['field']}\"\n",
        "            continue  # mutated\n",
        MASSRUN_TEST,
        MISSING_ANSWER,
    ),
    (
        "the source digest guard is not applied",
        "scripts/remediation/phase3/mass_run.py",
        "        if plan_digest is not None and digest_of() != plan_digest:\n",
        "        if False:  # mutated\n",
        MASSRUN_TEST,
        DIGEST_GUARD,
    ),
    (
        "the progress file is written in place instead of swapped in",
        "scripts/remediation/phase3/mass_run.py",
        '        temporary = path.with_name(path.name + ".tmp")\n'
        '        temporary.write_text(text + "\\n", encoding="utf-8")\n'
        "        os.replace(temporary, path)  # atomic on POSIX and on Windows\n",
        '        path.write_text(text + "\\n", encoding="utf-8")  # mutated: not atomic\n',
        MASSRUN_TEST,
        ATOMIC,
    ),
    (
        "the projection counts one call per site",
        "scripts/remediation/phase3/mass_run.py",
        "FIELDS_PER_SITE = 5\n",
        "FIELDS_PER_SITE = 1  # mutated\n",
        MASSRUN_TEST,
        DRY_RUN,
    ),
    (
        "prepare is not told which plan to prepare",
        "scripts/remediation/phase3/mass_run.py",
        '            return [*argv, "--plan", str(self.plan)]\n',
        "            return list(argv)  # mutated\n",
        MASSRUN_TEST,
        PREPARE_PLAN,
    ),
    (
        "the ledger is sent to prepare as well",
        "scripts/remediation/phase3/mass_run.py",
        '            return [*argv, "--plan", str(self.plan)]\n',
        '            return [*argv, "--plan", str(self.plan), "--ledger", str(self.ledger)]  # mutated\n',
        MASSRUN_TEST,
        REAL_CLI,
    ),
    (
        "the evidence bound falls back below a site it was raised for",
        "scripts/remediation/phase3/model_stage.py",
        "MAX_EVIDENCE_CHARS = 64_000\n",
        "MAX_EVIDENCE_CHARS = 32_000\n",
        MODEL_TEST,
        BOUND_MEASURED,
    ),
    (
        "a file that changed under the sweep is not reported",
        "scripts/remediation/phase3/mutation_sweep.py",
        "        if now != was:\n",
        "        if False:\n",
        SWEEP_TEST,
        DRIFT,
    ),
    (
        "the ledger's appends are not serialised across processes",
        "scripts/remediation/phase3/ledger.py",
        "        with _serialised(self.path):\n",
        "        if True:  # mutated\n",
        RUNNER_TEST,
        LEDGER_LOCK,
    ),
    (
        "the reason sentence is taken from the verdict line instead",
        "scripts/remediation/phase3/discover_stage.py",
        "        if not stripped.upper().startswith(MARKER_PREFIXES):\n",
        "        if True:  # mutated\n",
        TEST,
        REASON,
    ),
    (
        "the reviewer's question stops naming the verdict line the parser reads",
        "scripts/remediation/phase3/model_stage.py",
        '    "REFUTED: YES | NO | UNRESOLVED\\n"\n',
        '    "\\n"\n',
        REVIEW_TEST,
        REVIEW_SHAPE,
    ),
    (
        "the reviewer may no longer refute a finding with its own knowledge",
        "scripts/remediation/phase3/model_stage.py",
        '    "Use everything you have: the evidence in this message and your own knowledge of the subject. "\n',
        '    "\\n"\n',
        REVIEW_TEST,
        REVIEW_KNOWLEDGE,
    ),
    (
        "the reviewer loses the second way a finding can fail",
        "scripts/remediation/phase3/model_stage.py",
        '    "2. the proposed value is contradicted by the evidence.\\n"\n',
        '    "\\n"\n',
        REVIEW_TEST,
        REVIEW_HALVES,
    ),
    (
        "the reviewer loses the plan's false-alarm briefing",
        "scripts/remediation/phase3/model_stage.py",
        '    "\\n" + _false_alarm_block() + "\\n"\n',
        '    "\\n"\n',
        REVIEW_TEST,
        REVIEW_BRIEFING,
    ),
    (
        "a refutation from the reviewer's own knowledge is a problem again",
        "scripts/remediation/phase3/review_stage.py",
        "    if refuted is not True and sources:\n",
        "    if refuted is True and not sources:\n"
        '        problems.append("a `REFUTED: YES` with no `SOURCE:` page")\n'
        "    if refuted is not True and sources:\n",
        REVIEW_TEST,
        REVIEW_KNOWLEDGE_NO_SOURCE,
    ),
    (
        "a verdict line the model numbered is no longer read as a verdict",
        "scripts/remediation/phase3/review_stage.py",
        'REFUTED_RE = re.compile(r"^\\s*(?:\\d+[.)]\\s*)?REFUTED:\\s*(?P<value>\\S+)\\s*$", re.MULTILINE)',
        'REFUTED_RE = re.compile(r"^\\s*REFUTED:\\s*(?P<value>\\S+)\\s*$", re.MULTILINE)',
        REVIEW_TEST,
        REVIEW_NUMBERED,
    ),
    (
        "the host's own Retry-After is ignored and our own backoff decides",
        "scripts/remediation/phase3/fetch_stage.py",
        "        wait = RETRY_BACKOFF_SECONDS[number - 1]\n"
        "        if asked is not None and asked > wait:\n"
        "            wait = asked\n",
        "        wait = RETRY_BACKOFF_SECONDS[number - 1]\n",
        FETCH_TEST,
        RETRY_AFTER_WAIT,
    ),
    (
        "a host asking for longer than the cap is re-asked sooner instead of left alone",
        "scripts/remediation/phase3/fetch_stage.py",
        "        if not last and asked is not None and asked > RETRY_AFTER_CAP_SECONDS:\n",
        "        if False:\n",
        FETCH_TEST,
        RETRY_AFTER_CAP,
    ),
    (
        "a Retry-After that cannot be read is guessed at as zero",
        "scripts/remediation/phase3/fetch_stage.py",
        "    except (TypeError, ValueError):\n        return None\n",
        "    except (TypeError, ValueError):\n        return 0.0\n",
        FETCH_TEST,
        RETRY_AFTER_UNREADABLE,
    ),
    (
        "delay-seconds accepts any script's digits, not only ASCII ones",
        "scripts/remediation/phase3/fetch_stage.py",
        "    if text.isascii() and text.isdigit():\n",
        "    if text.isdigit():\n",
        FETCH_TEST,
        RETRY_AFTER_ASCII,
    ),
    (
        "a Retry-After date already in the past becomes a negative delay",
        "scripts/remediation/phase3/fetch_stage.py",
        "    return max(0.0, when.timestamp() - received_at)\n",
        "    return when.timestamp() - received_at\n",
        FETCH_TEST,
        RETRY_AFTER_DATE,
    ),
    (
        "Retry-After: 0 shortens our own backoff instead of leaving it standing",
        "scripts/remediation/phase3/fetch_stage.py",
        "        if asked is not None and asked > wait:\n",
        "        if asked is not None:\n",
        FETCH_TEST,
        RETRY_AFTER_FLOOR,
    ),
    (
        "the reason we gave up on a target stops reaching the judge's sentence",
        "scripts/remediation/phase3/fetch_stage.py",
        "        elif self.given_up_reason:\n",
        "        elif False:\n",
        FETCH_TEST,
        RETRY_AFTER_CAP,
    ),
    (
        "the Retry-After header is never read off the response",
        "scripts/remediation/phase3/fetch_stage.py",
        "                    retry_after=parse_retry_after(\n"
        '                        response.headers.get("retry-after"), received_at=self._clock()\n'
        "                    ),\n",
        "                    retry_after=None,\n",
        FETCH_TEST,
        RETRY_AFTER_WAIT,
    ),
    # ── the writer (piece 6) ─────────────────────────────────────────────────────────────────────
    (
        "the site_type fixed point is never checked",
        WRITE_STAGE,
        '    if field_name == "site_type" and not M.site_type_fixed_point(value):',
        "    if False:  # mutant: no fixed-point check",
        WRITE_TEST,
        WRITE_FIXED_POINT,
    ),
    (
        "the report-only fields are written like any other",
        WRITE_STAGE,
        "    if field_name in M.REPORT_ONLY_FIELDS:",
        "    if False:  # mutant: report-only fields are writable",
        WRITE_TEST,
        WRITE_REPORT_ONLY,
    ),
    (
        "the width of the varchar column is not checked",
        WRITE_STAGE,
        "        if len(value) > limit:",
        "        if False:  # mutant: no width check",
        WRITE_TEST,
        WRITE_WIDTH,
    ),
    (
        "a value the row already holds is planned as a change",
        WRITE_STAGE,
        "    if new_value == old_value:",
        "    if False:  # mutant: no equality check",
        WRITE_TEST,
        WRITE_NOT_A_CHANGE,
    ),
    (
        "the pre-flight stops comparing the stored value",
        WRITE_STAGE,
        '            if not same_value(observed=observed.get("value"), planned=row.old_value, '
        "column=column):",
        "            if False:  # mutant: every row counts as held",
        WRITE_TEST,
        WRITE_MOVED,
    ),
    (
        "the digest pin accepts any digest of the right shape",
        WRITE_STAGE,
        "    if pinned != want:",
        "    if len(pinned) != len(want):",
        WRITE_TEST,
        WRITE_PIN,
    ),
    (
        "the read-back ignores what the database kept",
        WRITE_STAGE,
        '            if not same_value(observed=observed.get("value"), planned=row.new_value, '
        "column=column):",
        "            if False:  # mutant: the read-back always agrees",
        WRITE_TEST,
        WRITE_READBACK,
    ),
    (
        "the reversal is not checked for having been rolled back",
        WRITE_STAGE,
        "    if not inverse.ok:",
        "    if False:  # mutant: whatever the reversal did is fine",
        WRITE_TEST,
        WRITE_KEPT_REVERSAL,
    ),
    (
        "the reversal reuses the write's own change key",
        WRITE_STAGE,
        '        key = row.change_key + (ROLLBACK_KEY_SUFFIX if reversal else "")',
        "        key = row.change_key",
        WRITE_TEST,
        WRITE_REVERSAL,
    ),
    (
        "the reversal commits instead of rolling back",
        WRITE_STAGE,
        '    add("ROLLBACK;")',
        '    add("COMMIT;")',
        WRITE_TEST,
        WRITE_COMMIT,
    ),
    (
        "the chunk step is one row too long",
        WRITE_STAGE,
        "        Chunk(batch_id=plan.batch_id, index=index, rows=tuple(rows[start : start + "
        "chunk_size]))",
        "        Chunk(batch_id=plan.batch_id, index=index, rows=tuple(rows[start : start + "
        "chunk_size + 1]))",
        WRITE_TEST,
        WRITE_CHUNK_ORDER,
    ),
    (
        "the statements no longer stop on the first database error",
        WRITE_STAGE,
        '    lines.append("\\\\set ON_ERROR_STOP on")\n    lines.append("BEGIN;")\n',
        '    lines.append("BEGIN;")\n',
        WRITE_TEST,
        WRITE_STOP,
    ),
    (
        "the loop passes the new value as the old one",
        WRITE_STAGE,
        "    add(\"            'unified_sites', r.column_name, r.pk_column, r.pk,\")\n"
        '    add("            r.old_value, r.new_value,")\n'
        '    add(f"            r.test_id, {_sql_text(chunk.stamp)}, r.change_key, '
        '{_sql_text(CONFIDENCE)},")\n',
        "    add(\"            'unified_sites', r.column_name, r.pk_column, r.pk,\")\n"
        '    add("            r.new_value, r.old_value,")\n'
        '    add(f"            r.test_id, {_sql_text(chunk.stamp)}, r.change_key, '
        '{_sql_text(CONFIDENCE)},")\n',
        WRITE_TEST,
        WRITE_ARGS,
    ),
    (
        "the write guard no longer checks the source",
        WRITE_STAGE,
        '    add(f"     WHERE u.id IS NULL OR u.source_id <> {_sql_text(CURATED_SOURCE)};")',
        '    add("     WHERE u.id IS NULL;")',
        WRITE_TEST,
        WRITE_CURATED,
    ),
    (
        "the period_start comparison loses its integer cast",
        WRITE_STAGE,
        '    "period_start": "u.period_start IS DISTINCT FROM {planned}::integer",',
        '    "period_start": "u.period_start IS DISTINCT FROM {planned}",',
        WRITE_TEST,
        WRITE_COMPARE,
    ),
    (
        "the column allowlist is cut down to one column",
        WRITE_STAGE,
        '    columns = ", ".join(_sql_text(column) for column in WRITABLE_COLUMNS)',
        '    columns = ", ".join(_sql_text(column) for column in WRITABLE_COLUMNS[:1])',
        WRITE_TEST,
        WRITE_CHANGE_GUARD,
    ),
    (
        "the journal invariant only looks one way",
        WRITE_STAGE,
        '    add("       AND NOT EXISTS (SELECT 1 FROM _phase3_plan p WHERE p.change_key = '
        'l.change_key);")',
        '    add("       ;")',
        WRITE_TEST,
        WRITE_JOURNAL,
    ),
    (
        "the review file's own applies boolean is trusted",
        WRITE_STAGE,
        '        refuted=_tristate(raw.get("refuted")),',
        '        refuted=False if raw.get("applies") else _tristate(raw.get("refuted")),',
        WRITE_TEST,
        WRITE_APPLIES,
    ),
    (
        "a review may be joined to any batch's input",
        WRITE_STAGE,
        '    if review.get("batch_id") != batch_id:',
        "    if False:  # mutant: the batch ids need not agree",
        WRITE_TEST,
        WRITE_OTHER_BATCH,
    ),
    (
        "the discover pass marker is not checked",
        WRITE_STAGE,
        "    if pass_name != DISCOVER_PASS:",
        "    if False:  # mutant: any pass may be written",
        WRITE_TEST,
        WRITE_ONLY_DISCOVER,
    ),
    (
        "the read statement takes any column name",
        WRITE_STAGE,
        "    if column not in WRITABLE_COLUMNS:",
        "    if False:  # mutant: any column may be read",
        WRITE_TEST,
        WRITE_READ_STMT,
    ),
    # ── the named holes (2026-09-21) ─────────────────────────────────────────────────────────────
    (
        "an unreadable stream ends the finding-driven batch again",
        "scripts/remediation/phase3/model_stage.py",
        "        try:\n"
        "            judged = judge_site(prepared=item, runner=runner, ledger=ledger, answers=answers)\n"
        "        except UnreadableStream as exc:\n"
        "            named_failures.append(\n"
        "                FailedCall(site_id=site_id, field=item.call.field, reason=str(exc))\n"
        "            )\n"
        "            continue\n",
        "        judged = judge_site(prepared=item, runner=runner, ledger=ledger, answers=answers)\n",
        MODEL_TEST,
        MODEL_HOLE,
    ),
    (
        "a stored answer is asked for a second time instead of being reused",
        "scripts/remediation/phase3/model_stage.py",
        "    if answers.exists(call.site_id, call.answer_key):",
        "    if False:  # mutant: every re-run pays for the answer again",
        MODEL_TEST,
        MODEL_REUSE,
    ),
    (
        "every ModelCallFailed is swallowed as a named hole",
        "scripts/remediation/phase3/model_stage.py",
        "        except UnreadableStream as exc:\n",
        "        except ModelCallFailed as exc:\n",
        MODEL_TEST,
        MODEL_TRANSPORT,
    ),
    (
        "the report's call count forgets the holes",
        "scripts/remediation/phase3/model_stage.py",
        "        return len(self.judgements) + len(self.failures)\n",
        "        return len(self.judgements)\n",
        MODEL_TEST,
        MODEL_HOLE_CLI,
    ),
    (
        "an unreadable stream ends the discover batch again",
        "scripts/remediation/phase3/discover_stage.py",
        "        try:\n"
        "            judged = MS.judge_site(prepared=item, runner=runner, ledger=ledger, answers=answers)\n"
        "        except MS.UnreadableStream as exc:\n"
        "            named_failures.append(\n"
        "                MS.FailedCall(site_id=site_id, field=field_name or None, reason=str(exc))\n"
        "            )\n"
        "            continue\n",
        "        judged = MS.judge_site(prepared=item, runner=runner, ledger=ledger, answers=answers)\n",
        TEST,
        DISCOVER_HOLE,
    ),
    (
        "a field the finder's stream left empty is cleared like a finding",
        "scripts/remediation/phase3/review_stage.py",
        "        if not path.exists():\n            plan.unreviewable.append(\n",
        "        if False:  # mutated\n            plan.unreviewable.append(\n",
        TEST,
        DISCOVER_HOLE_REVIEW,
    ),
    (
        "the batch counts only its judgements again",
        "scripts/remediation/phase3/mass_run.py",
        "    if len(judgements) + len(named) != calls:\n",
        "    if len(judgements) != calls:\n",
        MASSRUN_TEST,
        MASSRUN_HOLE,
    ),
    (
        "the call count need not add up",
        "scripts/remediation/phase3/mass_run.py",
        "    if len(judgements) + len(named) != calls:\n",
        "    if len(judgements) + len(named) < 0:  # mutant: any count settles\n",
        MASSRUN_TEST,
        MASSRUN_HOLE_COUNT,
    ),
    (
        "a listed failure is credited whatever it says",
        "scripts/remediation/phase3/model_stage.py",
        "    if not isinstance(row, dict) or set(row) != NAMED_FAILURE_KEYS:\n        return False\n",
        "    if not isinstance(row, dict):\n        return False\n",
        MASSRUN_TEST,
        MASSRUN_HOLE_VERDICT,
    ),
    (
        "any list under `failures` is credited",
        "scripts/remediation/phase3/mass_run.py",
        "    if not isinstance(named, list) or not all(MS.is_named_failure(row) for row in named):\n",
        "    if not isinstance(named, list):\n",
        MASSRUN_TEST,
        MASSRUN_HOLE_SHAPE,
    ),
    (
        "the writer plans a row for a field with no answer on disk",
        WRITE_STAGE,
        "    path = answers.path_for(site_id, field_name)\n    if not path.exists():\n",
        "    path = answers.path_for(site_id, field_name)\n    if False:  # mutant: a missing answer no longer refuses the row\n",
        WRITE_TEST,
        WRITE_HOLE,
    ),
]

#: The guards of 2026-09-22 - the writer's citation and rerun checks, the fetch stage's new routes,
#: the lane-aware write tools and the gap plan. Their own list, appended below, so entries another
#: lane adds above cannot collide with these in a merge.
FETCH_ROUTES_TEST = "tests/remediation/test_phase3_fetch_routes.py"
TOOLS_TEST = "tests/remediation/test_remediation_tools.py"
GAP_TEST = "tests/remediation/test_gap_plan.py"
FETCH_STAGE = "scripts/remediation/phase3/fetch_stage.py"
TOOLS = "output/remediation/tools/"
GAP_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "the writer no longer checks the finder's citation",
        WRITE_STAGE,
        "    citation = DS.source_problems(answer, pages())\n",
        "    citation = ()  # mutant\n",
        WRITE_TEST,
        "test_a_quote_the_cited_page_does_not_carry_is_refused_as_a_citation_failure",
    ),
    (
        "the writer re-decides a field the run was not built to ask",
        WRITE_STAGE,
        "            if asked is not None and field_name not in asked:\n",
        "            if False:  # mutant\n",
        WRITE_TEST,
        "test_a_field_the_run_was_not_built_to_ask_is_not_written_though_cleared",
    ),
    (
        "a page cut at the cap is stored without its marker",
        FETCH_STAGE,
        '        return _complete_utf8(page.body) + TRUNCATION_MARKER.encode("utf-8")\n',
        "        return page.body\n",
        FETCH_ROUTES_TEST,
        "test_a_page_cut_at_the_cap_is_stored_with_the_truncation_marker",
    ),
    (
        "a cut keeps half a character before the marker",
        FETCH_STAGE,
        '        return _complete_utf8(page.body) + TRUNCATION_MARKER.encode("utf-8")\n',
        '        return page.body + TRUNCATION_MARKER.encode("utf-8")\n',
        FETCH_ROUTES_TEST,
        "test_a_cut_through_a_character_leaves_a_file_the_judge_can_read",
    ),
    (
        "a date is read through WDQS",
        FETCH_STAGE,
        'TRUTHY_PROPERTIES: tuple[str, ...] = ("P31", "P17", "P131", "P2348", "P625")\n',
        'TRUTHY_PROPERTIES: tuple[str, ...] = ("P31", "P17", "P131", "P2348", "P625", "P571")\n',
        FETCH_ROUTES_TEST,
        "test_no_date_is_read_through_wdqs",
    ),
    (
        "WDQS is asked at the default pace",
        FETCH_STAGE,
        "        interval = max(self.min_interval, HOST_MIN_INTERVAL_OVERRIDES.get(host, 0.0))\n",
        "        interval = self.min_interval\n",
        FETCH_ROUTES_TEST,
        "test_wdqs_is_asked_at_most_once_a_second_and_other_hosts_at_the_default_pace",
    ),
    (
        "the truthy query scans a variable predicate again",
        FETCH_STAGE,
        '        f"{{ BIND(wd:{pid} AS ?property) {item} p:{pid} ?statement . "\n',
        '        f"{{ BIND(wd:{pid} AS ?property) {item} ?claim ?statement . "\n',
        FETCH_ROUTES_TEST,
        "test_the_truthy_query_names_every_predicate_instead_of_scanning_a_variable_one",
    ),
    (
        "a misspelt Wikidata route is read as the narrow one",
        FETCH_STAGE,
        "        if route != WIKIDATA_ROUTE_NARROW:\n",
        "        if False:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_a_misspelt_or_unanchored_route_is_refused_not_ignored",
    ),
    (
        "a shared item's sitelink is resolved",
        FETCH_STAGE,
        "        if count > 1:\n",
        "        if False:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_a_shared_item_is_refused_without_a_request_and_the_rest_are_resolved",
    ),
    (
        "a sitelink resolved for another item is used",
        FETCH_STAGE,
        '        if link["qid"] != site.get("wikidata_qid"):\n',
        "        if False:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_a_sitelink_for_another_item_or_the_same_title_or_a_bad_shape_is_refused",
    ),
    (
        "the gate reads the mass lane's APPLIED markers for every lane",
        TOOLS + "write_gate.py",
        '        if (apply_root / batch / "APPLIED.json").exists():\n',
        '        if (apply_root.parent / "_write_apply" / batch / "APPLIED.json").exists():\n',
        TOOLS_TEST,
        "test_a_batch_applied_in_the_mass_lane_does_not_suppress_a_gap_batch",
    ),
    (
        "the gate writes rows of another run",
        TOOLS + "write_gate.py",
        "    missing = sorted(batch for batch in by_batch if not (run_dir / batch).is_dir())\n",
        "    missing: list[str] = []  # mutant\n",
        TOOLS_TEST,
        "test_rows_of_another_run_are_refused_before_anything_is_planned",
    ),
    (
        "the gate writes a stale rows file by position",
        TOOLS + "write_gate.py",
        "    if expected == replanned:\n        return\n",
        "    return\n",
        TOOLS_TEST,
        "test_a_rows_file_that_is_not_the_writers_plan_today_is_refused",
    ),
    (
        "the reviewer ceiling keeps queueing after a STOP",
        TOOLS + "review_all.py",
        "            while queue and not stopped and len(pending) < workers:\n",
        "            while queue and len(pending) < workers:\n",
        TOOLS_TEST,
        "test_the_reviewer_ceiling_counts_this_pass_and_really_stops_the_queue",
    ),
    (
        "the acceptance passes a broken journal chain",
        TOOLS + "verify_writes.py",
        "        if link.old != previous.new:\n",
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_broken_chain_is_a_deviation_even_when_the_live_value_matches_its_end",
    ),
    (
        "the acceptance counts a superseded row as carried",
        TOOLS + "verify_writes.py",
        "            if not later:\n",
        "            if True:  # mutant\n",
        TOOLS_TEST,
        "test_a_write_superseded_by_a_later_journalled_lane_is_reported_not_a_deviation",
    ),
    (
        "the hold list reads a rows file whose lines moved",
        TOOLS + "make_holds.py",
        "    if digest != ROWS_KEYS_SHA256:\n",
        "    if False:  # mutant\n",
        TOOLS_TEST,
        "test_the_hold_list_refuses_a_rows_file_whose_lines_moved",
    ),
    (
        "the external-id repair accepts an update that matched no row or two",
        TOOLS + "qid_repair.py",
        '        "        IF n <> 1 THEN",\n',
        '        "        IF n < 0 THEN",\n',
        TOOLS_TEST,
        "test_the_repair_statement_is_guarded_journalled_and_pinned",
    ),
    (
        "the gap plan gives the run an id the repair replaces",
        TOOLS + "gap_plan.py",
        "        if qid == repair.old_qid:\n",
        "        if False:  # mutant\n",
        GAP_TEST,
        "test_a_repaired_or_unresolved_or_shared_item_is_withheld_and_the_rest_is_kept",
    ),
]
MUTATIONS += GAP_MUTATIONS


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_failure(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("FAILED") or line.startswith("E  ") or "assert" in line[:20]:
            return line.strip()[:160]
    return output.strip().splitlines()[-1][:160] if output.strip() else "(no output)"


def final_drift(repo: Path, before: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """Files whose bytes are no longer the ones the sweep started with, and both digests.

    The sweep restores every file it mutates, so at the end the tree has to be byte-identical to the
    moment it started - and that is a statement about the **tree**, not about the loop, which is why
    the per-mutation comparison cannot make it: that comparison only ever ran earlier. On 2026-09-21
    pi-lens wrote into `discover_stage.py` at 13:02 *while a sweep was running*, and afterwards into
    `snapshot_plan.py`, where it deleted the `"country"` element from `DISCOVER_FIELDS` and called it
    a reformat. A change like that is reported here and never repaired: the sweep does not know which
    revision the other writer meant, and guessing would be worse than saying so.
    """
    drift: dict[str, tuple[str, str]] = {}
    for rel, was in before.items():
        now = digest(repo / rel)
        if now != was:
            drift[rel] = (was, now)
    return drift


def main(argv: list[str], *, repo: Path = REPO, backup_dir: Path = BACKUP) -> int:
    """Run every wanted mutation. `repo` and `backup_dir` are parameters so the sweep can be tested
    against a throwaway tree instead of the one it is guarding."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    wanted = [m for m in MUTATIONS if not argv or any(a in m[0] for a in argv)]
    started = {rel: digest(repo / rel) for rel in sorted({m[1] for m in wanted})}
    rows: list[tuple[str, str, bool, str, str]] = []
    for name, rel, old, new, test_file, test_name in wanted:
        path = repo / rel
        original = path.read_text(encoding="utf-8")
        assert original.count(old) >= 1, f"{name}: anchor not found in {rel}"
        before = digest(path)
        backup = backup_dir / path.name
        shutil.copy2(path, backup)
        # The restore is **unconditional**: an exception anywhere after this point (a crash in the
        # sweep itself, a KeyboardInterrupt, a pytest that never returns) must never leave the
        # mutated file in the tree. That happened on 2026-09-21 - a TypeError in this very loop
        # killed the run mid-mutation and left `discover_stage.py` carrying a mutant, which then
        # looked like finished work. A sweep whose failure mode is "the tree is now wrong" is worse
        # than no sweep.
        try:
            path.write_text(original.replace(old, new, 1), encoding="utf-8", newline="\n")
            proc = subprocess.run(
                [str(PY), "-m", "pytest", f"{test_file}::{test_name}", "-q", "-x", "--no-header"],
                cwd=repo,
                capture_output=True,
                text=True,
                # Without this the child's output is decoded with the *locale's* codec (cp1252 on
                # this workstation), and one UTF-8 byte outside cp1252 kills subprocess's reader
                # thread: `stdout` then comes back as None. On 2026-09-21 that TypeError aborted the
                # sweep and left a mutant in `discover_stage.py`. The locale is not the child's
                # encoding - UTF-8 is, and the child is told so.
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            caught = proc.returncode != 0
            if proc.returncode == 4:
                raise SystemExit(
                    f"{name}: the test {test_file}::{test_name} was not collected; nothing was proven"
                )
            detail = (
                first_failure((proc.stdout or "") + (proc.stderr or "")) if caught else "NOT CAUGHT"
            )
        finally:
            shutil.copy2(backup, path)
        after = digest(path)
        rows.append(
            (name, f"{test_name} ({'failed' if caught else 'PASSED'})", caught, detail, before[:16])
        )
        assert after == before, f"{name}: restore is not byte-identical ({before} -> {after})"

    print(f"{'mutation':52} {'verdict':>10}  restored-sha256")
    for name, verdict, caught, detail, prefix in rows:
        print(f"{name[:52]:52} {'CAUGHT' if caught else 'MISSED':>10}  {prefix}")
        print(f"{'':52} {verdict}")
        if caught:
            print(f"{'':52}   {detail}")
    missed = [r[0] for r in rows if not r[2]]
    print(f"\n{len(rows) - len(missed)}/{len(rows)} mutations caught; missed: {missed}")
    # The sweep's own loop is done; what follows is about the tree it ran in.
    drift = final_drift(repo, started)
    if drift:
        for rel, (was, now) in sorted(drift.items()):
            print(f"DRIFT {rel}: {was[:16]} -> {now[:16]} - written while this sweep ran")
        print(f"{len(drift)} file(s) changed under the sweep: the tree is not what it was.")
        return 1
    print(f"the tree is byte-identical to the sweep's start for {len(started)} file(s)")
    return 0 if not missed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
