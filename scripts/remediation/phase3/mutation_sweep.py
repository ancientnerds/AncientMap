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

# ── the search lane (block A3, 2026-09-22) ───────────────────────────────────────────────────────
SEARCH_TEST = "tests/remediation/test_phase3_search.py"
FROZEN_TEST = "tests/remediation/test_phase3_frozen.py"
MINIMAX_TEST = "tests/pipeline/test_minimax_search.py"
SEARCH_EVIDENCE = "scripts/remediation/phase3/search_evidence.py"
SEARCH_STAGE = "scripts/remediation/phase3/search_stage.py"
SEARCH_PLAN = "scripts/remediation/phase3/search_plan.py"
MINIMAX_SHARED = "pipeline/lyra/minimax_shared.py"
FROZEN = "test_the_question_texts_are_byte_identical_to_the_ones_the_mass_run_was_asked_with"
S_DAMAGED = "test_a_damaged_rerun_fields_value_raises_and_never_widens_to_all_fields"
S_TEXTS = "test_rerun_fields_come_back_in_plan_order_and_the_two_texts_share_one_search"
S_RECORD = "test_a_record_this_module_would_not_write_is_refused"
S_HOSTS = "test_own_and_blocked_hosts_are_excluded_by_host_never_by_substring"
S_HIT = "test_a_hit_becomes_one_excerpt_and_the_filters_drop_our_own_and_blocked_hosts"
S_MERGE = "test_one_url_found_by_two_searches_is_one_page_carrying_both_texts"
S_COLLIDE = "test_a_hit_on_a_fetched_targets_url_raises_instead_of_hiding_a_page"
S_MISSING = "test_a_search_missing_with_no_record_raises_a_recorded_failure_is_named"
S_TWO_FACTS = "test_search_failed_and_no_hits_reach_the_judge_as_two_different_facts"
S_CLASH = "test_a_failure_for_one_feature_in_both_reports_raises"
S_ONLY = "test_the_finder_asks_only_the_rerun_fields"
S_GATE = "test_the_gate_fails_closed"
S_GATE_FIELD = "test_a_missing_quota_field_never_satisfies_the_gate"
S_WINDOW = "test_the_gate_refuses_to_start_inside_theos_batch_window"
S_LEAK = "test_a_slot_value_that_contains_the_value_under_test_is_refused"
S_TEMPLATE = "test_a_template_that_reads_a_field_it_is_asked_about_is_refused"
S_EXISTING = "test_an_existing_search_is_never_bought_again"
S_STOP = "test_a_stop_class_error_ends_the_stage_after_one_request"
S_GATE_BUYS = "test_the_gate_refusing_buys_no_search_and_writes_no_ledger_line"
S_KEEPS_FAILING = "test_a_search_that_keeps_failing_is_a_recorded_failure_not_no_hits"
S_UNDECIDED = "test_the_plan_takes_only_undecided_fields_of_its_scope_verbatim_under_new_ids"
S_UNWRITTEN = "test_held_and_gate_stopped_rows_are_rerun_and_written_rows_are_not"
S_AGREE = "test_the_three_write_records_must_agree"
S_PREFIX = "test_a_prefix_that_could_collide_or_is_not_letters_is_refused"
S_PREPARE = "test_prepare_refuses_a_changed_record_a_changed_copy_and_a_hole"
S_BUDGET = "test_the_budget_dry_run_counts_the_sites_a_search_could_push_over_the_bound"
S_RUN_STOP = "test_a_search_that_asks_the_run_to_stop_stops_it_and_says_why"
S_CEILING = "test_the_search_ceiling_counts_this_runs_search_requests"
S_INCOMPLETE = "test_a_batch_whose_search_is_incomplete_is_never_done"
S_STAGES = "test_the_stage_sequence_must_fit_the_plan"
S_QUOTA = "test_the_progress_file_carries_each_search_batchs_quota_readings"
X_BASE_RESP = "test_a_2xx_whose_base_resp_reports_an_error_raises_and_is_never_read_as_hits"
X_SHAPE = "test_a_contract_break_raises_from_both_the_strict_call_and_the_wrapper"
X_NO_HITS = "test_an_empty_organic_list_is_a_real_no_hits_and_not_an_error"
X_RANKED = "test_a_successful_search_keeps_every_entry_and_ranks_the_ones_that_name_a_page"
X_STATUS = "test_every_non_2xx_raises_its_own_type_and_the_wrapper_still_returns_empty"
X_TRANSPORT = "test_no_response_at_all_is_a_transport_error_with_no_status"
X_VLM = "test_every_vlm_failure_raises_strictly_and_reads_as_a_reject_through_the_wrapper"

# ── the search lane's review fixes (2026-09-23) ─────────────────────────────────────────────────
BLOCKED_TEST = "tests/pipeline/test_blocked_domains.py"
BLOCKED_DOMAINS_PY = "pipeline/lyra/blocked_domains.py"
VLM_PILOT_TEST = "tests/remediation/test_vlm_pilot_common.py"
REVIEW_STAGE = "scripts/remediation/phase3/review_stage.py"
MASS_RUN = "scripts/remediation/phase3/mass_run.py"
RUN_PY = "scripts/remediation/phase3/run.py"
B_WALK = "test_a_host_is_listed_by_itself_or_a_parent_domain_never_by_substring"
B_SHARED = "test_the_three_lists_share_the_walk"
F_WRITE_ONCE = "test_the_write_once_rule_keeps_identical_bytes_and_leaves_no_temp_file"
V_EXACT = "test_only_the_exact_case_name_resolves_and_the_main_tree_comes_first"
S_POOLED = "test_no_query_of_a_site_carries_the_value_of_any_field_it_reruns"
S_CROSS_LEAK = (
    "test_a_slot_value_that_contains_another_rerun_fields_value_is_refused_in_every_query"
)
S_PRODUCTION = "test_a_query_reads_productions_values_never_the_older_snapshot"
S_NAME = "test_a_name_ending_in_the_value_under_test_loses_it_and_one_that_carries_it_is_counted"
S_NAMELESS = "test_a_site_without_a_name_cannot_be_searched"
S_TEMPLATE_NAMES = (
    "test_a_template_that_names_a_field_it_does_not_declare_or_a_key_without_one_is_refused"
)
S_STORED_QUERY = "test_a_stored_search_is_reused_only_for_the_query_it_answered"
S_RESUME_QUOTA = "test_a_resumed_batch_keeps_what_its_first_run_measured"
S_QUOTA_DAMAGE = "test_a_damaged_quota_history_raises_instead_of_being_dropped"
S_PROBE_ERROR = "test_a_failed_probe_is_recorded_with_its_error"
S_NO_STATUS = "test_an_error_that_carries_no_status_is_ledgered_as_a_transport_failure"
S_SETTINGS = "test_the_real_searcher_is_built_only_from_a_key_and_a_base_url"
S_LIVE = "test_search_live_writes_its_report_and_exits_with_what_happened"
S_GATE_REASON = "test_the_gate_refusal_is_the_reason_not_the_probes_nested_error"
S_THIS_CALL = "test_the_stop_reason_is_read_from_this_calls_output_only"
S_OWN_ERROR = "test_only_a_reports_own_error_key_is_its_error"
S_DAMAGED_REPORT = "test_a_damaged_search_report_stops_the_driver_before_it_starts"
S_UNION = "test_a_site_failed_in_both_reports_keeps_both_failures"
S_REPEAT = "test_a_rerun_answer_that_repeats_an_unwritten_proposal_is_never_cleared"
S_UNWRITTEN_DAMAGE = (
    "test_a_damaged_unwritten_record_raises_instead_of_letting_a_held_value_through"
)
S_SAME_VALUE = "test_a_repeat_is_recognised_across_case_spacing_and_leading_zeros"
S_CHANGED = "test_a_query_value_is_productions_and_a_field_production_changed_is_not_rerun"
S_EXPORT = "test_a_partial_or_damaged_export_of_production_is_refused"
S_SOURCE_INPUT = "test_a_source_batch_that_is_not_its_own_discover_batch_is_refused"
S_ROW_SHAPE = "test_an_unwritten_row_without_its_proposal_or_planned_twice_is_refused"
S_ROW_DISAGREES = "test_an_unwritten_row_that_disagrees_with_the_snapshot_or_the_answers_raises"
S_UNPLACED = "test_an_answer_nobody_can_place_is_refused"
S_PREPARE_SOURCE = "test_prepare_refuses_a_source_input_that_is_not_the_batch_the_plan_names"
S_CLI_CURRENT = (
    "test_plan_search_needs_productions_values_and_the_written_keys_outside_the_text_scope"
)
S_GOLD = "test_the_pilot_selects_the_gold_standards_own_sites"
S_CARRIED_COUNT = "test_the_plan_counts_the_queries_that_still_carry_the_value_under_test"
X_MALFORMED_BASE = (
    "test_a_malformed_base_resp_is_a_new_raise_where_the_old_wrapper_returned_the_hits"
)
X_BUDGET_FIRST = "test_a_body_that_names_both_the_budget_and_the_rate_cap_is_the_budget"
S_PLAN_LINE = "test_a_plan_line_with_mixed_or_damaged_rerun_fields_is_refused_with_its_line"

#: (name, file, the exact text to replace, what to replace it with, test file, test name)
MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "reversed field order",
        "scripts/remediation/phase3/discover_stage.py",
        "for name in fields\n    ]",
        "for name in reversed(fields)\n    ]",
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
        "        skipped = [_over_bound_skip(site, field=name, exc=exc) for name in fields]\n"
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
        "            if slot == FEATURE_WIKIDATA_ENTITY and not qid:\n                continue\n",
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
    # ── the search lane (block A3, 2026-09-22) ──────────────────────────────────────────────────
    (
        "a frozen question word changes",
        "scripts/remediation/phase3/discover_stage.py",
        '    "You propose; you do not write."\n)',
        '    "You propose; you never write."\n)',
        FROZEN_TEST,
        FROZEN,
    ),
    (
        "the partial-evidence note changes",
        "scripts/remediation/phase3/model_stage.py",
        "neither confirmation nor a clean bill of health.",
        "neither confirmation nor a full bill of health.",
        FROZEN_TEST,
        FROZEN,
    ),
    (
        "a damaged rerun_fields value widens to all fields",
        SEARCH_EVIDENCE,
        "    if not isinstance(value, list) or not value:\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_DAMAGED,
    ),
    (
        "an unknown rerun field is accepted",
        SEARCH_EVIDENCE,
        "    if unknown:\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_DAMAGED,
    ),
    (
        "the two text fields get a search each",
        SEARCH_EVIDENCE,
        "        served.setdefault(SEARCH_KEY_FOR_FIELD[name], []).append(name)\n",
        "        served.setdefault(name, []).append(name)  # mutated\n",
        SEARCH_TEST,
        S_TEXTS,
    ),
    (
        "a stored search with foreign keys is read",
        SEARCH_EVIDENCE,
        "    if not isinstance(payload, dict) or set(payload) != RECORD_KEYS:\n",
        "    if not isinstance(payload, dict):\n",
        SEARCH_TEST,
        S_RECORD,
    ),
    (
        "our own site becomes evidence",
        SEARCH_EVIDENCE,
        "    if listed_domain_of(host, OWN_DOMAINS) is not None:\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_HOSTS,
    ),
    (
        "blocked hosts are matched by substring",
        BLOCKED_DOMAINS_PY,
        "        if candidate in domains:\n",
        "        if any(entry in host for entry in domains):  # mutated\n",
        SEARCH_TEST,
        S_HOSTS,
    ),
    (
        "every blocklist matches by substring",
        BLOCKED_DOMAINS_PY,
        "        if candidate in domains:\n",
        "        if any(entry in host for entry in domains):  # mutated\n",
        BLOCKED_TEST,
        B_WALK,
    ),
    (
        "theo_sources keeps its own walk and loses the parent domains",
        "pipeline/lyra/theo_sources.py",
        "    return listed_domain_of(_extract_domain(url), BLOCKED_DOMAINS) is not None\n",
        "    return _extract_domain(url) in BLOCKED_DOMAINS  # mutated\n",
        BLOCKED_TEST,
        B_SHARED,
    ),
    (
        "search hits never reach the evidence",
        "scripts/remediation/phase3/model_stage.py",
        "    for slot in SE.search_slots(site):\n",
        "    for slot in ():  # mutated\n",
        SEARCH_TEST,
        S_HIT,
    ),
    (
        "the evidence keeps hits on our own and blocked hosts",
        "scripts/remediation/phase3/model_stage.py",
        "            if SE.excluded_because(hit.url) is not None:\n                continue\n",
        "",
        SEARCH_TEST,
        S_HIT,
    ),
    (
        "one url found by two searches becomes two pages",
        "scripts/remediation/phase3/model_stage.py",
        "merged.setdefault(hit.url, ([], [], path))",
        'merged.setdefault(hit.url + "#" + slot.feature, ([], [], path))',
        SEARCH_TEST,
        S_MERGE,
    ),
    (
        "a hit on a fetched target's url is accepted",
        "scripts/remediation/phase3/model_stage.py",
        "            if hit.url in taken:\n",
        "            if False:  # mutated\n",
        SEARCH_TEST,
        S_COLLIDE,
    ),
    (
        "a missing search is judged as if it were empty",
        "scripts/remediation/phase3/model_stage.py",
        "            elif allow_absent:\n                failure = None\n",
        "            elif True:  # mutated\n                failure = None\n",
        SEARCH_TEST,
        S_MISSING,
    ),
    (
        "the judge never reads the search report's failures",
        "scripts/remediation/phase3/model_stage.py",
        "    for name in (SEARCH_REPORT_NAME, HIT_REPORT_NAME):\n",
        "    for name in (HIT_REPORT_NAME,):  # mutated\n",
        SEARCH_TEST,
        S_TWO_FACTS,
    ),
    (
        "a feature failed in both reports is merged",
        "scripts/remediation/phase3/model_stage.py",
        "        if clash:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_CLASH,
    ),
    (
        "a search plan asks all five fields again",
        "scripts/remediation/phase3/discover_stage.py",
        "    fields = DISCOVER_FIELDS if rerun is None else rerun\n",
        "    fields = DISCOVER_FIELDS  # mutated\n",
        SEARCH_TEST,
        S_ONLY,
    ),
    (
        "a probe that did not answer satisfies the gate",
        SEARCH_STAGE,
        '    if probe.get("ok") is not True:\n',
        '    if probe.get("ok") is False:\n',
        SEARCH_TEST,
        S_GATE,
    ),
    (
        "a missing quota field satisfies the gate",
        SEARCH_STAGE,
        "        if not _number(probe.get(name)):\n",
        "        if name in probe and not _number(probe.get(name)):\n",
        SEARCH_TEST,
        S_GATE_FIELD,
    ),
    (
        "the weekly floor lets its own value through",
        SEARCH_STAGE,
        "    if weekly <= QUOTA_WEEKLY_FLOOR_PCT:\n",
        "    if weekly < QUOTA_WEEKLY_FLOOR_PCT:\n",
        SEARCH_TEST,
        S_GATE,
    ),
    (
        "the 5h floor lets its own value through",
        SEARCH_STAGE,
        "    if five <= QUOTA_FIVE_HOUR_FLOOR_PCT:\n",
        "    if five < QUOTA_FIVE_HOUR_FLOOR_PCT:\n",
        SEARCH_TEST,
        S_GATE,
    ),
    (
        "the search runs inside Theo's batch window",
        SEARCH_STAGE,
        "    if days_left <= THEO_BATCH_MAX_DAYS_TO_RESET:\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_WINDOW,
    ),
    (
        "a query may carry the value under test",
        SEARCH_STAGE,
        "            if stored.casefold() in value.casefold():\n",
        "            if False:  # mutated\n",
        SEARCH_TEST,
        S_LEAK,
    ),
    (
        "a template may read the field it is asked about",
        SEARCH_STAGE,
        "        if leaked:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_TEMPLATE,
    ),
    (
        "a search already on disk is bought again",
        SEARCH_STAGE,
        "        if store.exists(site_id, slot.feature):\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_EXISTING,
    ),
    (
        "a resumed batch with nothing to search is gated anyway",
        SEARCH_STAGE,
        "    if pending:\n        # The gate guards MiniMax requests.",
        "    if True:  # mutated\n        # The gate guards MiniMax requests.",
        SEARCH_TEST,
        "test_a_resumed_batch_with_every_search_on_disk_is_not_gated",
    ),
    (
        "a missing key fails batch by batch instead of stopping the run",
        "scripts/remediation/phase3/run.py",
        "        return STOP_RUN_EXIT\n    pacer = F.HostPacer(",
        "        return 1  # mutated\n    pacer = F.HostPacer(",
        SEARCH_TEST,
        "test_search_live_without_a_key_stops_the_run_and_asks_nothing",
    ),
    (
        "a stop-class error is retried like weather",
        SEARCH_STAGE,
        "    if isinstance(exc, STOP_ERRORS):\n        return False\n",
        "",
        SEARCH_TEST,
        S_STOP,
    ),
    (
        "the stage searches on after it stopped",
        SEARCH_STAGE,
        "        if report.stopped is not None:\n            by_site",
        "        if False:  # mutated\n            by_site",
        SEARCH_TEST,
        S_GATE_BUYS,
    ),
    (
        "a search that failed is recorded as no failure",
        SEARCH_STAGE,
        '            outcome.failure = f"search failed: {error} ({number} request(s) recorded)"\n'
        "            outcome.stops = isinstance(error, STOP_ERRORS)\n",
        "            outcome.stops = isinstance(error, STOP_ERRORS)\n",
        SEARCH_TEST,
        S_KEEPS_FAILING,
    ),
    (
        "the last failed request is not marked given up",
        SEARCH_STAGE,
        "                given_up=last and error is not None,\n",
        "                given_up=False,  # mutated\n",
        SEARCH_TEST,
        S_KEEPS_FAILING,
    ),
    (
        "the plan reruns decided fields too",
        SEARCH_PLAN,
        '        if verdict == "UNVERIFIABLE":\n',
        '        if verdict in ("UNVERIFIABLE", "CORRECT"):  # mutated\n',
        SEARCH_TEST,
        S_UNDECIDED,
    ),
    (
        "the held and gate-stopped rows fall out of the plan",
        SEARCH_PLAN,
        "    extra = dict(extra or {})\n",
        "    extra = {}  # mutated\n",
        SEARCH_TEST,
        S_UNWRITTEN,
    ),
    (
        "a written row is rerun as if it were not written",
        SEARCH_PLAN,
        "        if key in written:\n            continue\n",
        "        if False:  # mutated\n            continue\n",
        SEARCH_TEST,
        S_UNWRITTEN,
    ),
    (
        "a hold that was written after all is accepted",
        SEARCH_PLAN,
        "    if set(held) & written:\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_AGREE,
    ),
    (
        "the batch prefix may collide with the mass run's stamps",
        SEARCH_PLAN,
        '    if not PREFIX_RE.fullmatch(prefix) or prefix == "batch":\n',
        "    if not PREFIX_RE.fullmatch(prefix):  # mutated\n",
        SEARCH_TEST,
        S_PREFIX,
    ),
    (
        "prepare overwrites a copy that differs",
        "scripts/remediation/phase3/fetch_stage.py",
        "        if path.read_bytes() != body:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_PREPARE,
    ),
    (
        "the evidence store overwrites a recorded file",
        "scripts/remediation/phase3/fetch_stage.py",
        "        if path.read_bytes() != body:\n",
        "        if False:  # mutated\n",
        FETCH_TEST,
        F_WRITE_ONCE,
    ),
    (
        "prepare accepts a record that drifted from its source",
        SEARCH_PLAN,
        "        if by_id.get(site_id) != original:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_PREPARE,
    ),
    (
        "prepare accepts a hole in the source record",
        SEARCH_PLAN,
        "                if target.feature not in failures.get(site_id, {}):\n",
        "                if False:  # mutated\n",
        SEARCH_TEST,
        S_PREPARE,
    ),
    (
        "the budget dry run ignores the added hits",
        SEARCH_PLAN,
        "if base <= bound < base + plus",
        "if base <= bound < base",
        SEARCH_TEST,
        S_BUDGET,
    ),
    (
        "the driver ignores a stage that asked the run to stop",
        "scripts/remediation/phase3/mass_run.py",
        "        if stop:\n            return stop\n",
        "        if False:  # mutated\n            return stop\n",
        SEARCH_TEST,
        S_RUN_STOP,
    ),
    (
        "the runner does not record a stage's stop request",
        "scripts/remediation/phase3/mass_run.py",
        '            if code == STOP_RUN_EXIT and stage == "search":\n',
        "            if False:  # mutated\n",
        SEARCH_TEST,
        S_RUN_STOP,
    ),
    (
        "the search ceiling is never reached",
        "scripts/remediation/phase3/mass_run.py",
        "        if self.max_searches is not None and searched >= self.max_searches:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_CEILING,
    ),
    (
        "a batch with an incomplete search counts as done",
        "scripts/remediation/phase3/mass_run.py",
        '    if payload["stopped"] is not None or failed:\n',
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_INCOMPLETE,
    ),
    (
        "a plan runs under the other lane's stages",
        "scripts/remediation/phase3/mass_run.py",
        "    if mismatched:\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_STAGES,
    ),
    (
        "the quota readings are not carried into progress.json",
        "scripts/remediation/phase3/mass_run.py",
        "                if quota is not None:\n",
        "                if False:  # mutated\n",
        SEARCH_TEST,
        S_QUOTA,
    ),
    (
        "a 2xx body's base_resp error is read as hits",
        MINIMAX_SHARED,
        '    base = data.get("base_resp")\n    if base is None:\n',
        '    base = data.get("base_resp")\n    if True:  # mutated\n',
        MINIMAX_TEST,
        X_BASE_RESP,
    ),
    (
        "the legacy search wrapper swallows a contract break",
        MINIMAX_SHARED,
        "    except CodingPlanShapeError:\n        raise\n",
        "",
        MINIMAX_TEST,
        X_SHAPE,
    ),
    (
        "no hits raises like a missing field",
        MINIMAX_SHARED,
        '    if "organic" not in data:\n',
        '    if not data.get("organic"):  # mutated\n',
        MINIMAX_TEST,
        X_NO_HITS,
    ),
    (
        "a result without a link counts as a hit",
        MINIMAX_SHARED,
        "            if isinstance(item.url, str) and item.url\n",
        "            if isinstance(item.url, str)\n",
        MINIMAX_TEST,
        X_RANKED,
    ),
    (
        "a 401 is not an auth error",
        MINIMAX_SHARED,
        "    if status in (401, 403):\n",
        "    if False:  # mutated\n",
        MINIMAX_TEST,
        X_STATUS,
    ),
    (
        "a spent budget is read as a plain HTTP error",
        MINIMAX_SHARED,
        "    if is_quota_error(body):\n",
        "    if False:  # mutated\n",
        MINIMAX_TEST,
        X_STATUS,
    ),
    (
        "a transport failure escapes untyped",
        MINIMAX_SHARED,
        '        raise CodingPlanTransportError(f"POST {path}: {type(exc).__name__}: {exc}") from exc\n',
        "        raise  # mutated\n",
        MINIMAX_TEST,
        X_TRANSPORT,
    ),
    (
        "an empty VLM answer is returned as a result",
        MINIMAX_SHARED,
        "    if not content:\n",
        "    if False:  # mutated\n",
        MINIMAX_TEST,
        X_VLM,
    ),
    # ── the search lane's review fixes (2026-09-23) ─────────────────────────────────────────────
    (
        "a slot whose field the site reruns stays in the query",
        SEARCH_STAGE,
        '        slot_field: "" if slot_field in rerun else _as_text(production[slot_field])\n',
        "        slot_field: _as_text(production[slot_field])  # mutated\n",
        SEARCH_TEST,
        S_POOLED,
    ),
    (
        "a slot value is checked against its own fields only",
        SEARCH_STAGE,
        "    for asked, stored in _under_test(site).items():\n",
        "    for asked, stored in {k: v for k, v in _under_test(site).items() if k in slot.fields}"
        ".items():  # mutated\n",
        SEARCH_TEST,
        S_CROSS_LEAK,
    ),
    (
        "a query reads the snapshot instead of production",
        SEARCH_STAGE,
        '        slot_field: "" if slot_field in rerun else _as_text(production[slot_field])\n',
        '        slot_field: "" if slot_field in rerun else _stored_text(site, slot_field)  # mutated\n',
        SEARCH_TEST,
        S_PRODUCTION,
    ),
    (
        "a record without all query values is searched",
        SEARCH_STAGE,
        "    if not isinstance(values, dict) or set(values) != set(SLOT_FIELDS):\n",
        "    if not isinstance(values, dict):  # mutated\n",
        SEARCH_TEST,
        S_PRODUCTION,
    ),
    (
        "a name keeps its trailing value under test",
        SEARCH_STAGE,
        "        if comma and tail.strip().casefold() == value.casefold():\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_NAME,
    ),
    (
        "a query that still carries the value is not counted",
        SEARCH_STAGE,
        "        if span and any(words[i : i + span] == wanted for i in range(len(words) - span + 1)):\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_NAME,
    ),
    (
        "the plan summary does not count carried values",
        SEARCH_STAGE,
        "        if span and any(words[i : i + span] == wanted for i in range(len(words) - span + 1)):\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_CARRIED_COUNT,
    ),
    (
        "a nameless site is searched",
        SEARCH_STAGE,
        "    if not name:\n"
        '        raise InputError(f"{site_id}: a search starts from the stored name, and there is none")\n',
        "    if False:  # mutated\n"
        '        raise InputError(f"{site_id}: a search starts from the stored name, and there is none")\n',
        SEARCH_TEST,
        S_NAMELESS,
    ),
    (
        "a template may name a field it does not declare",
        SEARCH_STAGE,
        '        if named != {"name", *slots}:\n',
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_TEMPLATE_NAMES,
    ),
    (
        "a search key may lack its template",
        SEARCH_STAGE,
        "    if set(QUERY_TEMPLATES) != set(SE.SEARCH_KEY_FOR_FIELD.values()):\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_TEMPLATE_NAMES,
    ),
    (
        "a stored search is reused for a query it never answered",
        SEARCH_STAGE,
        "            if record.query != query:\n",
        "            if False:  # mutated\n",
        SEARCH_TEST,
        S_STORED_QUERY,
    ),
    (
        "a resumed run drops the quota readings of earlier runs",
        SEARCH_STAGE,
        "        return [*self.earlier_quota, this_run]\n",
        "        return [this_run]  # mutated\n",
        SEARCH_TEST,
        S_RESUME_QUOTA,
    ),
    (
        "the search command does not carry the earlier readings forward",
        RUN_PY,
        "            earlier_quota=SS.read_quota(report_path),\n",
        "            earlier_quota=(),  # mutated\n",
        SEARCH_TEST,
        S_LIVE,
    ),
    (
        "a damaged quota history is read as a clean one",
        SEARCH_STAGE,
        "        isinstance(entry, dict) and set(entry) == QUOTA_ENTRY_KEYS for entry in quota\n",
        "        True for entry in quota  # mutated\n",
        SEARCH_TEST,
        S_QUOTA_DAMAGE,
    ),
    (
        "a failed probe's error is dropped from its reading",
        SEARCH_STAGE,
        '        reading["error"] = probe.get("error")\n',
        "        pass  # mutated\n",
        SEARCH_TEST,
        S_PROBE_ERROR,
    ),
    (
        "an error without a status is ledgered as an answer",
        SEARCH_STAGE,
        "    if isinstance(exc, CodingPlanTransportError) or exc.http_status is None:\n",
        "    if isinstance(exc, CodingPlanTransportError):  # mutated\n",
        SEARCH_TEST,
        S_NO_STATUS,
    ),
    (
        "the searcher is built without a key",
        SEARCH_STAGE,
        "        if not settings.minimax_api_key or not settings.minimax_base_url:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_SETTINGS,
    ),
    (
        "the driver loses the readings of batches it skips",
        MASS_RUN,
        "            progress.quota[planned.batch_id] = earlier\n",
        "            pass  # mutated\n",
        SEARCH_TEST,
        S_QUOTA,
    ),
    (
        "the stop reason is read from a nested error",
        MASS_RUN,
        "        if not line.startswith(TOP_LEVEL_ERROR):\n"
        "            continue\n"
        "        try:\n"
        '            error = json.loads(line[len(TOP_LEVEL_ERROR) :].strip().rstrip(","))\n',
        "        if not line.strip().startswith('\"error\":'):  # mutated\n"
        "            continue\n"
        "        try:\n"
        '            error = json.loads(line.strip()[len(\'"error":\') :].rstrip(",").strip())\n',
        SEARCH_TEST,
        S_RUN_STOP,
    ),
    (
        "report_error reads any error key",
        MASS_RUN,
        "        if not line.startswith(TOP_LEVEL_ERROR):\n"
        "            continue\n"
        "        try:\n"
        '            error = json.loads(line[len(TOP_LEVEL_ERROR) :].strip().rstrip(","))\n',
        "        if not line.strip().startswith('\"error\":'):  # mutated\n"
        "            continue\n"
        "        try:\n"
        '            error = json.loads(line.strip()[len(\'"error":\') :].rstrip(",").strip())\n',
        SEARCH_TEST,
        S_OWN_ERROR,
    ),
    (
        "the stop reason is read from the whole appended log",
        MASS_RUN,
        '                written = log.read_bytes()[start:].decode("utf-8", errors="replace")\n',
        '                written = log.read_bytes().decode("utf-8", errors="replace")  # mutated\n',
        SEARCH_TEST,
        S_THIS_CALL,
    ),
    (
        "the last batch's stop request is not recorded",
        MASS_RUN,
        "        progress.stopped = stop_of()\n",
        "        pass  # mutated\n",
        SEARCH_TEST,
        S_GATE_REASON,
    ),
    (
        "a search report without its verdict fields reads as clean",
        MASS_RUN,
        '    if not isinstance(failed, int) or isinstance(failed, bool) or "stopped" not in payload:\n',
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_INCOMPLETE,
    ),
    (
        "a damaged search report does not stop the driver",
        SEARCH_STAGE,
        "        isinstance(entry, dict) and set(entry) == QUOTA_ENTRY_KEYS for entry in quota\n",
        "        True for entry in quota  # mutated\n",
        SEARCH_TEST,
        S_DAMAGED_REPORT,
    ),
    (
        "a search failure replaces the site's fetch failures",
        "scripts/remediation/phase3/model_stage.py",
        "        mine = failures.setdefault(site_id, {})\n",
        "        mine = failures[site_id] = {}  # mutated\n",
        SEARCH_TEST,
        S_UNION,
    ),
    (
        "a rerun may repeat a proposal the mass lane did not write",
        REVIEW_STAGE,
        "        if repeat is not None and SE.same_value(str(answer.proposed), repeat.proposed):\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_REPEAT,
    ),
    (
        "a missing unwritten record reads as none",
        SEARCH_EVIDENCE,
        "    if not isinstance(value, dict):\n",
        "    if value is None:\n        value = {}\n    if not isinstance(value, dict | list):  # mutated\n",
        SEARCH_TEST,
        S_UNWRITTEN_DAMAGE,
    ),
    (
        "an unwritten proposal may name a field that is not rerun",
        SEARCH_EVIDENCE,
        "        if name not in fields:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_UNWRITTEN_DAMAGE,
    ),
    (
        "an unwritten proposal may carry any kind",
        SEARCH_EVIDENCE,
        '        if row["kind"] not in UNWRITTEN_KINDS:\n',
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_UNWRITTEN_DAMAGE,
    ),
    (
        "a repeated year with a leading zero is a new value",
        SEARCH_EVIDENCE,
        "        return int(left) == int(right)\n",
        "        return left == right  # mutated\n",
        SEARCH_TEST,
        S_SAME_VALUE,
    ),
    (
        "the plan drops the proposals it did not write",
        SEARCH_PLAN,
        "        for name, row in unwritten.items()\n",
        "        for name, row in {}.items()  # mutated\n",
        SEARCH_TEST,
        S_UNWRITTEN,
    ),
    (
        "an unwritten row may disagree with the snapshot",
        SEARCH_PLAN,
        "                if row.old_value != (None if stored is None else str(stored)):\n",
        "                if False:  # mutated\n",
        SEARCH_TEST,
        S_ROW_DISAGREES,
    ),
    (
        "a field may be both UNVERIFIABLE and a planned write",
        SEARCH_PLAN,
        "                if name in fields:\n",
        "                if False:  # mutated\n",
        SEARCH_TEST,
        S_ROW_DISAGREES,
    ),
    (
        "an unwritten row without its proposal is planned",
        SEARCH_PLAN,
        "        if not isinstance(proposed, str) or not proposed.strip():\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_ROW_SHAPE,
    ),
    (
        "a row planned twice is taken once",
        SEARCH_PLAN,
        "        if pair in unwritten:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_ROW_SHAPE,
    ),
    (
        "a field production changed is rerun anyway",
        SEARCH_PLAN,
        "                if production[name] != stored:\n",
        "                if False:  # mutated\n",
        SEARCH_TEST,
        S_CHANGED,
    ),
    (
        "the plan's query values are the snapshot's",
        SEARCH_PLAN,
        "    record[SE.QUERY_VALUES_KEY] = {name: production[name] for name in SS.SLOT_FIELDS}\n",
        "    record[SE.QUERY_VALUES_KEY] = {name: DS.field_finding(site, name).get('current_value') "
        "for name in SS.SLOT_FIELDS}  # mutated\n",
        SEARCH_TEST,
        S_CHANGED,
    ),
    (
        "a site missing from the export is planned",
        SEARCH_PLAN,
        "            if production is None:\n",
        "            if False:  # mutated\n",
        SEARCH_TEST,
        S_CHANGED,
    ),
    (
        "an export line with other keys is read",
        SEARCH_PLAN,
        "        if not isinstance(row, dict) or set(row) != wanted:\n",
        "        if not isinstance(row, dict):  # mutated\n",
        SEARCH_TEST,
        S_EXPORT,
    ),
    (
        "a site exported twice is read",
        SEARCH_PLAN,
        "        if site_id in values:\n",
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_EXPORT,
    ),
    (
        "a source input for another batch is planned from",
        SEARCH_PLAN,
        '        if len(records) != 1 or records[0].get("batch_id") != root.name:\n',
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_SOURCE_INPUT,
    ),
    (
        "a source input of another pass is planned from",
        SEARCH_PLAN,
        '        if batch.get("pass") != DISCOVER_PASS or not isinstance(batch.get("sites"), list):\n',
        "        if False:  # mutated\n",
        SEARCH_TEST,
        S_SOURCE_INPUT,
    ),
    (
        "an answer for a field the pass never asks is read",
        SEARCH_PLAN,
        "        if site_id not in site_ids or field_name not in DISCOVER_FIELDS:\n",
        "        if site_id not in site_ids:  # mutated\n",
        SEARCH_TEST,
        S_UNPLACED,
    ),
    (
        "prepare copies from a source input that is another batch",
        SEARCH_PLAN,
        '    if len(records) != 1 or records[0].get("batch_id") != source_batch:\n',
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_PREPARE_SOURCE,
    ),
    (
        "a plan is built without production's values",
        RUN_PY,
        "    if not args.current_values:\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_CLI_CURRENT,
    ),
    (
        "the gold selection accepts a site twice",
        RUN_PY,
        '    if "" in ids or len(set(ids)) != len(ids):\n',
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_GOLD,
    ),
    (
        "two selections are taken at once",
        RUN_PY,
        "    if args.site_ids and args.gold_sites:\n",
        "    if False:  # mutated\n",
        SEARCH_TEST,
        S_GOLD,
    ),
    (
        "a boolean status code reads as success",
        MINIMAX_SHARED,
        "    if not isinstance(code, int) or isinstance(code, bool):\n",
        "    if not isinstance(code, int):  # mutated\n",
        MINIMAX_TEST,
        X_MALFORMED_BASE,
    ),
    (
        "the rate cap is checked before the budget",
        MINIMAX_SHARED,
        "    if is_quota_error(body):\n"
        "        raise CodingPlanQuotaError(detail, http_status=status, body_bytes=size)\n"
        "    if is_plan_rate_throttle(body):\n"
        "        raise CodingPlanThrottleError(detail, http_status=status, body_bytes=size)\n",
        "    if is_plan_rate_throttle(body):  # mutated\n"
        "        raise CodingPlanThrottleError(detail, http_status=status, body_bytes=size)\n"
        "    if is_quota_error(body):\n"
        "        raise CodingPlanQuotaError(detail, http_status=status, body_bytes=size)\n",
        MINIMAX_TEST,
        X_BUDGET_FIRST,
    ),
    (
        "the driver accepts a plan line without query values",
        MASS_RUN,
        "                    SS.query_values(site)\n",
        "                    pass  # mutated\n",
        SEARCH_TEST,
        S_PLAN_LINE,
    ),
    (
        "the driver accepts a plan line without its unwritten proposals",
        MASS_RUN,
        "                    SE.unwritten_proposals(site)\n",
        "                    pass  # mutated\n",
        SEARCH_TEST,
        S_PLAN_LINE,
    ),
    (
        "an image file is found by a case-insensitive probe",
        "scripts/remediation/vlm_pilot/common.py",
        "        if hit is not None:\n            return root / shard_for(site_id) / filename, hit[1]\n",
        "        if (root / shard_for(site_id) / filename).is_file():  # mutated\n"
        "            return root / shard_for(site_id) / filename, 0\n",
        VLM_PILOT_TEST,
        V_EXACT,
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
        "    citation = DS.source_problems(answer, DS.pages_from_excerpts(evidence))\n",
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
        "        if (apply_root / batch / APPLIED_FILE).exists():\n",
        '        if (apply_root.parent / "_write_apply" / batch / APPLIED_FILE).exists():\n',
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
        "    while (offset := first_break(transitions[start:])) is not None:\n",
        "    while False:  # mutant\n",
        TOOLS_TEST,
        "test_a_broken_chain_is_a_deviation_even_when_the_live_value_matches_its_end",
    ),
    (
        "the acceptance counts a superseded row as carried",
        TOOLS + "verify_writes.py",
        "            if not later:\n",
        "            if True:  # mutant\n",
        TOOLS_TEST,
        "test_a_write_superseded_by_a_listed_later_lane_is_reported_not_a_deviation",
    ),
    (
        "the hold list reads a rows file whose lines moved",
        TOOLS + "lanes.py",
        "    if digest != pinned:\n",
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

#: The review round of 2026-09-23: every guard the reviewers found untested or missing - the gate's
#: wiring and its stops, the acceptance's per-row rules, the pinned plan, the repair statement's
#: guards, the sitelink badges, the truthy citation address and the gap plan's own refusals.
PILOT = "scripts/remediation/vlm_pilot/common.py"  # the lookup rejected_kinds uses
PILOT_TEST = "tests/remediation/test_vlm_pilot_rejected_kinds.py"
REVIEW_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "the gate never calls its stale-plan guard",
        TOOLS + "write_gate.py",
        "    for batch, batch_rows, _ in todo:\n        assert_same_plan(\n",
        "    for batch, batch_rows, _ in []:  # mutant\n        assert_same_plan(\n",
        TOOLS_TEST,
        "test_main_refuses_a_stale_rows_file_before_the_first_write",
    ),
    (
        "the gate re-plans from the mass lane's run",
        TOOLS + "write_gate.py",
        '"--batch-dir", str(run_dir / batch), "--out", str(out)],',
        '"--batch-dir", str(lanes.lane().run_dir / batch), "--out", str(out)],',
        TOOLS_TEST,
        "test_the_replan_asks_the_writer_about_this_lanes_own_batch_directory",
    ),
    (
        "a hold that names no row holds nothing, silently",
        TOOLS + "write_gate.py",
        "    if stray:\n",
        "    if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_hold_that_names_no_planned_row_is_refused",
    ),
    (
        "a writer call that wrote fewer rows than it was handed passes",
        TOOLS + "write_gate.py",
        "    if written != expected:\n",
        "    if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_writer_report_that_is_not_every_row_written_and_journalled_is_a_problem",
    ),
    (
        "a skipped chunk still marks its batch applied",
        TOOLS + "write_gate.py",
        "        if problems:\n            _stop(out, batch, tag, done, problems, report)\n",
        "        if False:  # mutant\n            _stop(out, batch, tag, done, problems, report)\n",
        TOOLS_TEST,
        "test_a_chunk_the_writer_skipped_stops_the_wave_and_is_never_marked_applied",
    ),
    (
        "a resume walks past a stopped batch",
        TOOLS + "write_gate.py",
        "    if stopped:\n",
        "    if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_chunk_the_writer_skipped_stops_the_wave_and_is_never_marked_applied",
    ),
    (
        "a step read-back with deviations lets the wave go on",
        TOOLS + "write_gate.py",
        "            if problems:\n                raise SystemExit(\n",
        "            if False:  # mutant\n                raise SystemExit(\n",
        TOOLS_TEST,
        "test_a_step_read_back_with_deviations_stops_the_wave",
    ),
    (
        "the final read-back's deviations exit 0",
        TOOLS + "write_gate.py",
        "    return 1 if problems else 0\n",
        "    return 0  # mutant\n",
        TOOLS_TEST,
        "test_a_step_read_back_with_deviations_stops_the_wave",
    ),
    (
        "the acceptance takes any value the lane journalled",
        TOOLS + "verify_writes.py",
        "            if row is not None and (link.old, link.new) != (\n",
        "            if False and (link.old, link.new) != (\n",
        TOOLS_TEST,
        "test_a_lane_write_of_a_value_nobody_planned_is_a_deviation",
    ),
    (
        "the acceptance reads an unwritten planned row as unchanged",
        TOOLS + "verify_writes.py",
        '        if row["change_key"] not in withheld:\n',
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_planned_row_neither_withheld_nor_written_is_a_deviation_not_unchanged",
    ),
    (
        "the acceptance passes a withheld row the lane wrote",
        TOOLS + "verify_writes.py",
        '        elif row["change_key"] in withheld:\n',
        "        elif False:  # mutant\n",
        TOOLS_TEST,
        "test_a_withheld_row_the_lane_wrote_is_a_deviation",
    ),
    (
        "the acceptance lets any later stamp supersede a lane row",
        TOOLS + "verify_writes.py",
        "            if foreign:\n                result.deviations.append(\n",
        "            if False:  # mutant\n                result.deviations.append(\n",
        TOOLS_TEST,
        "test_a_write_superseded_by_a_listed_later_lane_is_reported_not_a_deviation",
    ),
    (
        "the acceptance lets any stamp move a withheld row",
        TOOLS + "verify_writes.py",
        "        foreign = _unlisted(after, allowed)\n        if foreign:\n",
        "        foreign = _unlisted(after, allowed)\n        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_withheld_row_another_lane_changed_is_moved_only_for_a_listed_stamp",
    ),
    (
        "the acceptance passes a lane that wrote one row twice",
        TOOLS + "verify_writes.py",
        "        if len(links) > 1:\n",
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_lane_that_wrote_one_row_twice_is_a_deviation",
    ),
    (
        "the acceptance counts a lane row its chain does not hold",
        TOOLS + "verify_writes.py",
        "            if link.id not in ids:\n",
        "            if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_lane_row_missing_from_its_own_chain_is_a_deviation",
    ),
    # Moved here on 2026-09-23 from the mechanical sweep, whose acceptance cases named the
    # `judge()` implementation this merged acceptance replaced: the same guards, on `accept()`.
    (
        "the acceptance drops a lane row outside the three fields",
        TOOLS + "verify_writes.py",
        "        if link.table != TABLE or link.column not in COLUMNS:\n",
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_lane_row_outside_the_three_fields_is_a_deviation_not_dropped",
    ),
    (
        "main filters the lane's rows before the acceptance sees them",
        TOOLS + "verify_writes.py",
        "        lane_links=lane_links,  # all of them: accept() reports a lane row outside the three fields\n",
        "        lane_links=[k for k in lane_links if k.column in COLUMNS and k.table == TABLE],\n",
        TOOLS_TEST,
        "test_main_accepts_a_lane_from_what_the_database_answers",
    ),
    (
        "the acceptance passes a lane row outside the plan",
        TOOLS + "verify_writes.py",
        "        if row is None:\n",
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_lane_journal_row_outside_the_plan_is_a_deviation",
    ),
    (
        "the acceptance passes a planned site missing from the database",
        TOOLS + "verify_writes.py",
        "        if key[2] not in present:\n",
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_planned_site_missing_from_the_database_is_a_deviation",
    ),
    (
        "the acceptance does not compare the live value with the chain's end",
        TOOLS + "verify_writes.py",
        "    elif chain and live != last:\n",
        "    elif False:  # mutant\n",
        TOOLS_TEST,
        "test_a_live_value_that_is_not_the_chains_last_value_is_a_deviation",
    ),
    (
        "the acceptance passes a withheld row changed without a journal row",
        TOOLS + "verify_writes.py",
        "            if value != planned_old:\n",
        "            if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_withheld_row_must_still_hold_its_old_value",
    ),
    (
        "the acceptance passes a withheld row's chain that never held the planned value",
        TOOLS + "verify_writes.py",
        "        if planned_old not in states:\n",
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_withheld_row_another_lane_changed_is_moved_only_for_a_listed_stamp",
    ),
    (
        "the acceptance does not judge a withheld row's later chain",
        TOOLS + "verify_writes.py",
        "        result.deviations.extend(problems)\n        states = ",
        "        states = ",
        TOOLS_TEST,
        "test_a_later_chain_on_a_withheld_row_must_end_at_the_live_value",
    ),
    (
        "the lane read counts reversals as the lane's writes",
        TOOLS + "verify_writes.py",
        "        f\"AND run_stamp NOT LIKE {lanes.sql_text('%' + ROLLBACK_SUFFIX)} ORDER BY id) t;\\n\"\n",
        '        f"ORDER BY id) t;\\n"\n',
        TOOLS_TEST,
        "test_the_lane_query_leaves_out_reversals_but_the_chain_query_reads_every_stamp",
    ),
    (
        "the dry planner overwrites the plan a lane wrote from",
        TOOLS + "write_dry_all.py",
        "    if applied:\n",
        "    if False:  # mutant\n",
        TOOLS_TEST,
        "test_the_dry_planner_refuses_to_replace_the_plan_a_lane_has_written_from",
    ),
    (
        "the hold list's main never checks the pin",
        TOOLS + "make_holds.py",
        "    assert_pinned(rows)\n",
        "    pass  # mutant\n",
        TOOLS_TEST,
        "test_the_hold_list_refuses_a_rows_file_whose_lines_moved",
    ),
    (
        "the repair runs a statement edited under its digest header",
        TOOLS + "qid_repair.py",
        '        if path.read_text(encoding="utf-8") != sql:\n',
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_check_and_verify_read_the_database_and_refuse_an_edited_statement",
    ),
    (
        "the repair writes a site that is not curated",
        TOOLS + "qid_repair.py",
        "\"     WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';\",\n",
        '"     WHERE false;",\n',
        TOOLS_TEST,
        "test_every_guard_and_invariant_of_the_repair_statement_raises",
    ),
    (
        "the repair's guard 2 counts nothing",
        TOOLS + "qid_repair.py",
        '"             WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1",\n',
        '"             WHERE e.site_id = p.site_id AND e.kind = p.kind) < 0",\n',
        TOOLS_TEST,
        "test_every_guard_and_invariant_of_the_repair_statement_raises",
    ),
    (
        "the repair's invariant 1 raises nothing",
        TOOLS + "qid_repair.py",
        "\"        RAISE EXCEPTION 'external-id repair: % row(s) do not hold the new value', bad;\",\n",
        '"        NULL;",\n',
        TOOLS_TEST,
        "test_every_guard_and_invariant_of_the_repair_statement_raises",
    ),
    (
        "a sitelink badged as a redirect is used",
        FETCH_STAGE,
        "                if redirect:\n",
        "                if False:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_a_sitelink_badged_as_a_redirect_is_refused_with_the_badge_named",
    ),
    (
        "a sitelink without badges is read as unbadged",
        FETCH_STAGE,
        "        if not isinstance(title, str) or not title or not isinstance(badges, list):\n",
        "        if False:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_a_sitelink_without_its_badges_list_is_refused_not_read_as_unbadged",
    ),
    (
        "an item the sitelinks answer omits is skipped",
        FETCH_STAGE,
        "            if qid not in links:\n",
        "            if False:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_an_answer_that_omits_an_asked_item_or_was_cut_stops_the_resolution",
    ),
    (
        "a cut sitelinks answer is read",
        FETCH_STAGE,
        "        if not page.ok or page.truncated:\n",
        "        if not page.ok:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_an_answer_that_omits_an_asked_item_or_was_cut_stops_the_resolution",
    ),
    (
        "a sitelinks request asks for more than fifty items",
        FETCH_STAGE,
        "    if not wanted or len(wanted) > 50:\n",
        "    if not wanted:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_the_sitelinks_request_takes_one_to_fifty_items",
    ),
    (
        "a refused resolution with a title still gives a record",
        FETCH_STAGE,
        "        if self.title is None or self.refused is not None:\n",
        "        if self.title is None:  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_a_resolution_with_a_title_and_a_refusal_has_no_record",
    ),
    (
        "a sitelink record with extra keys is read",
        FETCH_STAGE,
        '        if not isinstance(link, Mapping) or set(link) != {"qid", "title"}:\n',
        "        if not isinstance(link, Mapping):  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_a_sitelink_record_with_an_extra_key_is_refused",
    ),
    (
        "the truthy query takes any qid",
        FETCH_STAGE,
        '    item = f"wd:{_require_qid(qid)}"\n',
        '    item = f"wd:{qid}"  # mutant\n',
        FETCH_ROUTES_TEST,
        "test_the_truthy_addresses_refuse_a_qid_that_is_not_a_q_number",
    ),
    (
        "the prompt shows the 2 KB WDQS address as the truthy page",
        FETCH_STAGE,
        "        return wikidata_truthy_citation_url(str(_finding(site, ",
        "        return wikidata_truthy_url(str(_finding(site, ",
        FETCH_ROUTES_TEST,
        "test_a_truthy_line_is_cited_through_the_short_address_the_prompt_shows",
    ),
    (
        "the fetch asks the citation address instead of the query",
        FETCH_STAGE,
        "        page = fetcher.get(target.request_url)\n",
        "        page = fetcher.get(target.url)  # mutant\n",
        FETCH_ROUTES_TEST,
        "test_a_truthy_line_is_cited_through_the_short_address_the_prompt_shows",
    ),
    (
        "an enwiki error body reads as an existing article",
        TOOLS + "gap_plan.py",
        "    if unread:\n",
        "    if False:  # mutant\n",
        GAP_TEST,
        "test_an_enwiki_answer_that_is_neither_an_article_nor_missing_is_refused",
    ),
    (
        "the census counts one question twice",
        TOOLS + "gap_plan.py",
        "        if key in questions:\n",
        "        if False:  # mutant\n",
        GAP_TEST,
        "test_a_question_the_census_finds_twice_is_refused",
    ),
    (
        "the gap plan routes a sitelink resolved for another item",
        TOOLS + "gap_plan.py",
        '            if link["qid"] != qid:\n',
        "            if False:  # mutant\n",
        GAP_TEST,
        "test_a_sitelink_resolved_for_another_item_than_the_exports_is_refused",
    ),
    (
        "the gap export accepts a missing or foreign site",
        TOOLS + "gap_plan.py",
        "    if missing or foreign:\n",
        "    if False:  # mutant\n",
        GAP_TEST,
        "test_an_export_that_misses_a_site_or_returns_a_foreign_one_is_refused",
    ),
    (
        # Retargeted 2026-09-23: the writer's own parser is gone; it reads the list through
        # `search_evidence.rerun_fields`, whose shared reader this breaks for every caller.
        "a rerun_fields mapping is read as its keys",
        SEARCH_EVIDENCE,
        "    if not isinstance(value, list) or not value:\n",
        "    if not value:  # mutant\n",
        WRITE_TEST,
        "test_a_malformed_rerun_list_is_refused_rather_than_read_generously",
    ),
    (
        # Retargeted in the 2026-09-23 merge: rejected_kinds now resolves through the shared
        # common.locate/resolve (the search lane's fix) instead of its own image_on_disk.
        "the rejected-kinds lookup ignores case",
        PILOT,
        "    size = files.get(filename)\n",
        "    size = next((v for k, v in files.items() if k.casefold() == filename.casefold()), None)"
        "  # mutant\n",
        PILOT_TEST,
        "test_a_name_that_differs_only_in_case_is_not_the_file",
    ),
]

#: Two keys, two meanings (2026-09-23). The merged tree gave `rerun_fields` both "what a run asks
#: again" (the gap lane) and "what a run searches for" (the search lane): a gap run would have been
#: driven as a search run, and the writer's rerun test failed on a search nobody bought. Every guard
#: of the split - `search_fields` as its own key, the plan kinds, the one parser - has its test here.
LANE_TEST = "tests/remediation/test_phase3_lane_shapes.py"
L_KINDS = "test_mass_run_reads_each_plan_as_its_own_kind_and_runs_its_own_stages"
L_MIXED_PLAN = "test_a_plan_whose_lines_are_of_two_kinds_is_refused"
L_OLD_SEARCH_PLAN = "test_a_search_plan_built_before_search_fields_is_refused_not_run_as_a_rerun"
L_ASKED = "test_the_finder_asks_exactly_the_fields_the_plan_reruns"
L_GAP_EVIDENCE = "test_a_gap_record_is_judged_on_its_fetched_pages_and_buys_no_search"
L_SEARCH_EVIDENCE = "test_a_search_record_is_judged_only_once_its_search_is_on_disk"
L_REVIEWER = "test_the_reviewer_is_asked_about_a_rerun_finding"
L_WRITER = "test_the_writer_writes_a_rerun_field_and_refuses_one_outside_rerun_fields"
S_SUBSET = "test_search_fields_are_a_non_empty_subset_of_the_rerun_fields_and_never_widen_them"
S_LOST_SEARCH = "test_a_search_record_without_search_fields_is_refused_not_run_without_searches"
S_UNWRITTEN_KEY = (
    "test_a_search_record_must_name_its_unwritten_proposals_a_rerun_only_record_names_none"
)
S_NOT_SEARCHED = "test_a_batch_whose_sites_name_no_search_fields_is_not_a_search_batch"
S_ASKED_NOT_SEARCHED = "test_a_field_asked_again_but_not_searched_stays_out_of_every_query"
W_ONE_PARSER = "test_the_writer_reads_the_rerun_list_with_the_discover_passs_own_parser"
W_RERUN_ONLY = "test_a_field_the_run_was_not_built_to_ask_is_not_written_though_cleared"
G_RECORDS = "test_the_records_carry_the_fresh_values_the_fields_to_ask_and_the_routes"
SPLIT_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "the search slots are read from rerun_fields: a gap record is searched",
        SEARCH_EVIDENCE,
        "    fields = search_fields(site)\n",
        "    fields = rerun_fields(site)  # mutant\n",
        LANE_TEST,
        L_GAP_EVIDENCE,
    ),
    (
        "the search slots are read from rerun_fields: the writer wants a search",
        SEARCH_EVIDENCE,
        "    fields = search_fields(site)\n",
        "    fields = rerun_fields(site)  # mutant\n",
        WRITE_TEST,
        W_RERUN_ONLY,
    ),
    (
        "search_fields outside rerun_fields are accepted",
        SEARCH_EVIDENCE,
        "    if outside:\n",
        "    if False:  # mutant\n",
        SEARCH_TEST,
        S_SUBSET,
    ),
    (
        "a search_fields mapping is read as its keys",
        SEARCH_EVIDENCE,
        "    if not isinstance(value, list) or not value:\n",
        "    if not value:  # mutant\n",
        SEARCH_TEST,
        S_SUBSET,
    ),
    (
        "a search record that lost search_fields runs without searches",
        SEARCH_EVIDENCE,
        "        if carried:\n",
        "        if False:  # mutant\n",
        SEARCH_TEST,
        S_LOST_SEARCH,
    ),
    (
        "an old search plan is walked as a rerun plan",
        SEARCH_EVIDENCE,
        "        if carried:\n",
        "        if False:  # mutant\n",
        LANE_TEST,
        L_OLD_SEARCH_PLAN,
    ),
    # One case per search-plan-only key (review 2026-09-23): the test used to take its cases from
    # `SEARCH_PLAN_KEYS` itself, so a key dropped from the tuple dropped its own case with it.
    (
        "a search record carrying only rerun_why reads as a rerun record",
        SEARCH_EVIDENCE,
        "SEARCH_PLAN_KEYS = (RERUN_WHY_KEY, RERUN_UNWRITTEN_KEY, QUERY_VALUES_KEY)\n",
        "SEARCH_PLAN_KEYS = (RERUN_UNWRITTEN_KEY, QUERY_VALUES_KEY)  # mutant\n",
        SEARCH_TEST,
        S_LOST_SEARCH,
    ),
    (
        "a search record carrying only rerun_unwritten reads as a rerun record",
        SEARCH_EVIDENCE,
        "SEARCH_PLAN_KEYS = (RERUN_WHY_KEY, RERUN_UNWRITTEN_KEY, QUERY_VALUES_KEY)\n",
        "SEARCH_PLAN_KEYS = (RERUN_WHY_KEY, QUERY_VALUES_KEY)  # mutant\n",
        SEARCH_TEST,
        S_LOST_SEARCH,
    ),
    (
        "a search record carrying only query_values reads as a rerun record",
        SEARCH_EVIDENCE,
        "SEARCH_PLAN_KEYS = (RERUN_WHY_KEY, RERUN_UNWRITTEN_KEY, QUERY_VALUES_KEY)\n",
        "SEARCH_PLAN_KEYS = (RERUN_WHY_KEY, RERUN_UNWRITTEN_KEY)  # mutant\n",
        SEARCH_TEST,
        S_LOST_SEARCH,
    ),
    # A field asked again but not searched (search_fields strictly inside rerun_fields) is still
    # judged on every search of its site, so the query rules read rerun_fields (review 2026-09-23).
    (
        "a field asked again but not searched keeps its name suffix",
        SEARCH_STAGE,
        "        name: text for name in SE.rerun_fields(site) or ()"
        " if (text := _stored_text(site, name))\n",
        "        name: text for name in SE.search_fields(site) or ()"
        " if (text := _stored_text(site, name))  # mutant\n",
        SEARCH_TEST,
        S_ASKED_NOT_SEARCHED,
    ),
    (
        "a field asked again but not searched fills its query slot",
        SEARCH_STAGE,
        "    rerun = set(SE.rerun_fields(site) or ())\n",
        "    rerun = set(SE.search_fields(site) or ())  # mutant\n",
        SEARCH_TEST,
        S_ASKED_NOT_SEARCHED,
    ),
    (
        "a search record without its unwritten proposals reads as none",
        SEARCH_EVIDENCE,
        "    if search_fields(site) is None:\n        return {}\n",
        "    if True:  # mutant\n        return {}\n",
        SEARCH_TEST,
        S_UNWRITTEN_KEY,
    ),
    (
        "the reviewer demands unwritten proposals of a gap record",
        SEARCH_EVIDENCE,
        "    if search_fields(site) is None:\n        return {}\n",
        "    if False:  # mutant\n        return {}\n",
        LANE_TEST,
        L_REVIEWER,
    ),
    (
        "mass_run classifies a rerun-only plan as a search plan",
        MASS_RUN,
        "        return SEARCH_PLAN if self.searches else RERUN_PLAN\n",
        "        return SEARCH_PLAN  # mutant\n",
        LANE_TEST,
        L_KINDS,
    ),
    (
        "mass_run runs a rerun plan under the search stages",
        MASS_RUN,
        "    RERUN_PLAN: STAGES,\n",
        "    RERUN_PLAN: SEARCH_STAGES,  # mutant\n",
        LANE_TEST,
        L_KINDS,
    ),
    (
        "mass_run lets either lane run under the other's stages",
        MASS_RUN,
        "    if mismatched:\n",
        "    if False:  # mutant\n",
        LANE_TEST,
        L_KINDS,
    ),
    (
        "mass_run takes a line whose sites disagree about search_fields",
        MASS_RUN,
        "        for key, named in ((SE.RERUN_FIELDS_KEY, rerun), (SE.SEARCH_FIELDS_KEY, searched)):\n",
        "        for key, named in ((SE.RERUN_FIELDS_KEY, rerun),):  # mutant\n",
        SEARCH_TEST,
        S_PLAN_LINE,
    ),
    (
        "mass_run walks a plan of two kinds",
        MASS_RUN,
        "    if len(kinds) > 1:\n",
        "    if False:  # mutant\n",
        LANE_TEST,
        L_MIXED_PLAN,
    ),
    (
        "the search stage searches for a rerun-only record",
        SEARCH_STAGE,
        "        if not site_id or not slots:\n",
        "        if not site_id:  # mutant\n",
        SEARCH_TEST,
        S_NOT_SEARCHED,
    ),
    (
        "a search record is judged without its search",
        "scripts/remediation/phase3/model_stage.py",
        "    for slot in SE.search_slots(site):\n",
        "    for slot in ():  # mutant\n",
        LANE_TEST,
        L_SEARCH_EVIDENCE,
    ),
    (
        "the finder asks a rerun record all five fields",
        "scripts/remediation/phase3/discover_stage.py",
        "    fields = DISCOVER_FIELDS if rerun is None else rerun\n",
        "    fields = DISCOVER_FIELDS  # mutant\n",
        LANE_TEST,
        L_ASKED,
    ),
    (
        "the search plan names no search_fields",
        SEARCH_PLAN,
        "    record[SE.SEARCH_FIELDS_KEY] = list(rerun)\n",
        "",
        LANE_TEST,
        L_SEARCH_EVIDENCE,
    ),
    (
        "the gap plan buys a search for every field it asks",
        TOOLS + "gap_plan.py",
        "        record[SE.RERUN_FIELDS_KEY] = [q.field for q in asked]\n",
        "        record[SE.RERUN_FIELDS_KEY] = [q.field for q in asked]\n"
        "        record[SE.SEARCH_FIELDS_KEY] = [q.field for q in asked]  # mutant\n",
        GAP_TEST,
        G_RECORDS,
    ),
    (
        "the writer ignores the run's rerun_fields",
        WRITE_STAGE,
        "            asked = SE.rerun_fields(site)\n",
        "            asked = None  # mutant\n",
        LANE_TEST,
        L_WRITER,
    ),
    (
        "the writer parses rerun_fields a second time, its own way",
        WRITE_STAGE,
        "            asked = SE.rerun_fields(site)\n",
        "            asked = tuple(site[SE.RERUN_FIELDS_KEY]) if SE.RERUN_FIELDS_KEY in site else None"
        "  # mutant: a second parser\n",
        WRITE_TEST,
        W_ONE_PARSER,
    ),
]
#: The three writer fixes after the search pilot failed (2026-09-23): the period-bucket gate, the
#: search-hit page check with its stage (`phase3/hit_stage.py`), and the reviewer contradiction hold.
HITS_TEST = "tests/remediation/test_phase3_hits.py"
HIT_STAGE = "scripts/remediation/phase3/hit_stage.py"
MODEL_STAGE = "scripts/remediation/phase3/model_stage.py"
DISCOVER_STAGE = "scripts/remediation/phase3/discover_stage.py"
W_BUCKET_IN = "test_a_period_start_change_inside_the_stored_bucket_is_refused"
W_BUCKET_ACROSS = "test_a_period_start_change_across_buckets_is_still_planned"
W_BUCKET_ONE = "test_the_bucket_gate_reads_the_pipelines_own_buckets"
W_CONTRA = "test_a_cleared_verdict_whose_why_line_names_a_failing_half_is_held"
R_NAMED = "test_a_why_line_that_names_a_failing_half_is_recognised"
R_BOTH_HOLD = "test_a_why_line_that_says_both_halves_hold_names_no_failing_half"
H_FETCH = "test_the_stage_fetches_the_cited_hits_and_no_other"
H_TARGET = "test_a_cited_fetched_target_is_not_a_hit_and_is_not_fetched_again"
H_DISK = "test_a_page_already_on_disk_is_not_fetched_again"
H_CAP = "test_a_cited_hit_past_the_cap_is_recorded_not_fetched"
H_GEOM = "test_a_hit_url_asking_for_raw_geometry_is_recorded_not_fetched"
H_FEATURE = "test_two_cited_urls_under_one_feature_are_refused"
H_ENTITIES = "test_a_hit_page_is_read_as_its_text_with_the_entities_undone"
H_LYRA = "test_the_page_reader_is_the_one_lyra_uses"
H_REVIEW_HOLE = "test_the_reviewer_is_not_asked_about_a_cited_hit_nobody_tried_to_verify"
H_REVIEW_PAGE = "test_the_reviewer_is_shown_the_page_behind_the_hit"
H_LONG = "test_a_long_hit_page_is_cut_for_the_prompt_and_read_whole_by_the_citation_check"
H_ROOM = "test_the_hit_pages_share_the_room_the_evidence_bound_leaves"
H_UNVERIFIED = "test_a_hit_page_that_could_not_be_fetched_or_read_leaves_the_citation_unverified"
H_WRITER_HOLE = "test_the_writer_raises_when_nobody_tried_to_verify_a_cited_hit"
H_FINDER = "test_the_finders_pages_keep_the_snippet_and_leave_the_hit_page_out"
H_LIVE = "test_verify_hits_live_writes_its_report_through_the_real_command"
H_SCORE_WRITER = "test_the_scorer_reports_what_the_writer_would_write_beside_the_sealed_block"
H_SCORE_SEALED = (
    "test_the_scorer_keeps_the_sealed_citation_definition_and_the_writer_refuses_the_page"
)
S_SNIPPET = "test_a_quote_from_a_snippet_counts_only_once_the_fetched_page_carries_it"
S_HIT_DONE = "test_a_search_batch_is_done_only_once_its_hit_pages_are_verified"
S_ARGV = "test_every_search_lane_argv_is_accepted_by_the_real_cli"
T_MEASURE = "test_the_measurement_counts_holds_false_holds_and_bucket_moves_with_the_writers_rules"
PILOT_FIX_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    # (a) the period-bucket gate
    (
        "the writer has no period-bucket gate",
        WRITE_STAGE,
        "    inside = _same_bucket_refusal(site_id, field_name, old_value, new_value)\n"
        "    if inside is not None:\n"
        "        return inside\n",
        "",
        WRITE_TEST,
        W_BUCKET_IN,
    ),
    (
        "the bucket gate reads the lower bound as exclusive",
        WRITE_STAGE,
        "    bucket = categorize_period(int(old_value))\n"
        "    return bucket if categorize_period(int(new_value)) == bucket else None\n",
        "    bucket = categorize_period(int(old_value) - 1)  # mutant\n"
        "    return bucket if categorize_period(int(new_value) - 1) == bucket else None\n",
        WRITE_TEST,
        W_BUCKET_ACROSS,
    ),
    (
        "the bucket gate refuses a move across buckets",
        WRITE_STAGE,
        "    return bucket if categorize_period(int(new_value)) == bucket else None\n",
        "    return bucket  # mutant\n",
        WRITE_TEST,
        W_BUCKET_ACROSS,
    ),
    (
        "the writer keeps a second spelling of the buckets",
        WRITE_STAGE,
        "from pipeline.utils.text import categorize_period  # noqa: E402  - the card's own buckets\n",
        "from pipeline.utils.text import categorize_period as _pipeline_buckets  # noqa: E402\n"
        "\n\ndef categorize_period(year):  # mutant: a second spelling\n"
        "    return _pipeline_buckets(year)\n",
        WRITE_TEST,
        W_BUCKET_ONE,
    ),
    # (c) the reviewer contradiction hold
    (
        "the writer ignores a WHY line that names a failing half",
        WRITE_STAGE,
        "            failing = RS.failing_half(cleared.reason)\n",
        "            failing = None  # mutant\n",
        WRITE_TEST,
        W_CONTRA,
    ),
    (
        "'Neither half holds' is not read as a failing half",
        REVIEW_STAGE,
        '    ("neither half holds", r"\\bneither half holds\\b"),\n',
        "",
        REVIEW_TEST,
        R_NAMED,
    ),
    (
        "'the stored value is not wrong' is not read as a failing half",
        REVIEW_STAGE,
        '        "the stored value is not wrong",\n'
        '        r"\\bstored" + _SAME_CLAUSE + r" (?:is|was|are) not wrong\\b",\n',
        '        "the stored value is not wrong",\n        r"(?!x)x",  # mutant\n',
        REVIEW_TEST,
        R_NAMED,
    ),
    (
        "'the stored text is not shown wrong' is not read as a failing half",
        REVIEW_STAGE,
        '        r"\\bstored" + _SAME_CLAUSE + r" (?:is|was|are) not shown (?:to be )?wrong\\b",\n',
        '        r"\\bstored" + _SAME_CLAUSE + r" (?:is|was|are) never shown wrong\\b",  # mutant\n',
        WRITE_TEST,
        W_CONTRA,
    ),
    (
        "'nor the proposed X is contradicted' holds a cleared row",
        REVIEW_STAGE,
        '        r"(?<!nor the )(?<!nor )(?<!if the )(?<!whether the )"\n',
        '        r""  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "a phrase runs from the stored value into the proposed value's clause",
        REVIEW_STAGE,
        "_SAME_CLAUSE = (\n"
        '    r"(?: (?!(?:is|was|are|and|or|but|while|so|whereas|proposed|proposal|stored|not|'
        'also)\\b)"\n'
        '    r"[^\\s,;:.\\u2014\\u2013]+){0,4}"\n'
        ")\n",
        '_SAME_CLAUSE = r"(?: [^\\s,;:.\\u2014\\u2013]+){0,8}"  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "the measurement counts false holds over the held rows",
        TOOLS + "measure_review_holds.py",
        '    print(f"  false holds on written rows: {held_by_rule[WRITTEN]}/{len(groups[WRITTEN])}")\n',
        '    print(f"  false holds on written rows: {held_by_rule[HELD]}/{len(groups[WRITTEN])}")\n',
        TOOLS_TEST,
        T_MEASURE,
    ),
    # (b) a search hit counts only through the page behind it
    (
        "a snippet answers a citation again",
        MODEL_STAGE,
        "        if self.kind == KIND_SEARCH_HIT:\n            return None\n",
        "        if self.kind == KIND_SEARCH_HIT:\n            return self.text  # mutant\n",
        SEARCH_TEST,
        S_SNIPPET,
    ),
    (
        "a hit page is cited against the part the prompt shows",
        MODEL_STAGE,
        "            return self.page_text\n",
        "            return self.text  # mutant\n",
        HITS_TEST,
        H_LONG,
    ),
    (
        "a hit page is shown whole, past its prompt bound",
        MODEL_STAGE,
        "        elif len(page) <= share:\n",
        "        elif True:  # mutant\n",
        HITS_TEST,
        H_LONG,
    ),
    (
        "the hit pages ignore the room the evidence bound leaves",
        MODEL_STAGE,
        "    share = max(0, min(HIT_PAGE_PROMPT_CHARS, room // readable)) if readable else 0\n",
        "    share = HIT_PAGE_PROMPT_CHARS  # mutant\n",
        HITS_TEST,
        H_ROOM,
    ),
    (
        "a cut hit page carries no marker",
        MODEL_STAGE,
        "            shown = page[: max(0, share - len(HIT_PAGE_CUT_MARKER))] + HIT_PAGE_CUT_MARKER\n",
        "            shown = page[:share]  # mutant\n",
        HITS_TEST,
        H_LONG,
    ),
    (
        "the evidence never carries a hit page",
        MODEL_STAGE,
        "        excerpts.extend(\n"
        "            _hit_page_excerpts(site_id=site_id, store=store, recorded=recorded, "
        "excerpts=excerpts)\n"
        "        )\n",
        "        pass  # mutant\n",
        HITS_TEST,
        H_REVIEW_PAGE,
    ),
    (
        "a cited hit nobody tried to verify passes the writer",
        MODEL_STAGE,
        "        if page is None:\n            raise EvidenceUnusable(\n",
        "        if page is None:\n            continue  # mutant\n            raise EvidenceUnusable(\n",
        HITS_TEST,
        H_WRITER_HOLE,
    ),
    (
        "a cited hit nobody tried to verify passes the reviewer",
        MODEL_STAGE,
        "        if page is None:\n            raise EvidenceUnusable(\n",
        "        if page is None:\n            continue  # mutant\n            raise EvidenceUnusable(\n",
        HITS_TEST,
        H_REVIEW_HOLE,
    ),
    (
        "the reviewer does not ask for the cited hits' pages",
        REVIEW_STAGE,
        "        MS.cited_hit_pages(\n"
        '            [claim.url for claim in answer.sources], excerpts, where=f"{site_id}/{name}"\n'
        "        )\n",
        "        pass  # mutant\n",
        HITS_TEST,
        H_REVIEW_HOLE,
    ),
    (
        "the judge never reads the hit-page report",
        MODEL_STAGE,
        "    for name in (SEARCH_REPORT_NAME, HIT_REPORT_NAME):\n",
        "    for name in (SEARCH_REPORT_NAME,):  # mutant\n",
        HITS_TEST,
        H_CAP,
    ),
    (
        "a stored page that is not text is read anyway",
        SEARCH_EVIDENCE,
        '        markup = body.decode("utf-8")\n',
        '        markup = body.decode("utf-8", errors="replace")  # mutant\n',
        HITS_TEST,
        H_UNVERIFIED,
    ),
    (
        "a hit page keeps its HTML entities",
        SEARCH_EVIDENCE,
        "    return html.unescape(extract_text_from_html(markup))\n",
        "    return extract_text_from_html(markup)  # mutant\n",
        HITS_TEST,
        H_ENTITIES,
    ),
    (
        "the Lyra handler reads a page with a second spelling",
        "pipeline/lyra/handlers/content_fetch.py",
        "from pipeline.utils.text import extract_text_from_html\n",
        "from pipeline.utils.text import extract_text_from_html as _shared_reader\n"
        "\n\ndef extract_text_from_html(html: str) -> str:  # mutant: a second spelling\n"
        "    return _shared_reader(html)\n",
        HITS_TEST,
        H_LYRA,
    ),
    (
        "the writer accepts a hit whose page failed or is not text",
        WRITE_STAGE,
        "        if page.citable is None:\n            return Refusal(\n",
        "        if False:  # mutant\n            return Refusal(\n",
        HITS_TEST,
        H_UNVERIFIED,
    ),
    (
        "the finder's pages include the hit page it never saw",
        DISCOVER_STAGE,
        "    return {e.url: e.text for e in excerpts if e.text is not None and e.kind != "
        "MS.KIND_HIT_PAGE}\n",
        "    return {e.url: e.text for e in excerpts if e.text is not None}  # mutant\n",
        HITS_TEST,
        H_FINDER,
    ),
    (
        "the stage fetches a cited fetched target",
        HIT_STAGE,
        "            if claim.url not in hits:\n                continue\n",
        "            if False:  # mutant\n                continue\n",
        HITS_TEST,
        H_TARGET,
    ),
    (
        "the stage fetches a page already on disk again",
        HIT_STAGE,
        "        if store.exists(site_id, hit.feature):\n            outcome.existing = True\n",
        "        if False:  # mutant\n            outcome.existing = True\n",
        HITS_TEST,
        H_DISK,
    ),
    (
        "the stage fetches past its cap",
        HIT_STAGE,
        "        elif index >= MAX_HIT_PAGES_PER_SITE:\n",
        "        elif False:  # mutant\n",
        HITS_TEST,
        H_CAP,
    ),
    (
        "the stage sends a raw-geometry url to the fetcher",
        HIT_STAGE,
        "                F.assert_named_feature(hit.url)\n",
        "                pass  # mutant\n",
        HITS_TEST,
        H_GEOM,
    ),
    (
        "two cited urls share one stored page",
        HIT_STAGE,
        "        if other != url:\n",
        "        if False:  # mutant\n",
        HITS_TEST,
        H_FEATURE,
    ),
    (
        "the stage fetches every hit of the search, cited or not",
        HIT_STAGE,
        "    cited: list[CitedHit] = []\n",
        "    for url in sorted(hits):  # mutant\n"
        '        fields_of.setdefault(url, ["period_start"])\n'
        "    cited: list[CitedHit] = []\n",
        HITS_TEST,
        H_FETCH,
    ),
    (
        "the live command writes no report",
        RUN_PY,
        "    HS.write_report(run_dir / batch_id / MS.HIT_REPORT_NAME, report)\n",
        "",
        HITS_TEST,
        H_LIVE,
    ),
    (
        "the live command is not paced",
        RUN_PY,
        "            fetcher=F.PacedFetcher(http, F.HostPacer(Path(args.pacing_dir))),\n",
        "            fetcher=http,  # mutant\n",
        HITS_TEST,
        H_LIVE,
    ),
    (
        "a search batch is done before its hit pages are verified",
        MASS_RUN,
        "    hits = hit_state(root)\n    if hits is not None:\n        return hits\n",
        "",
        SEARCH_TEST,
        S_HIT_DONE,
    ),
    (
        "the search sequence ends at the judge",
        MASS_RUN,
        'SEARCH_STAGES = ("prepare", "search", "judge", VERIFY_HITS)\n',
        'SEARCH_STAGES = ("prepare", "search", "judge")  # mutant\n',
        SEARCH_TEST,
        S_STAGES,
    ),
    (
        "the driver does not name the pace directory to verify-hits",
        MASS_RUN,
        '        if stage == "verify-hits" and self.pacing_dir is not None:\n',
        "        if False:  # mutant\n",
        SEARCH_TEST,
        S_ARGV,
    ),
    (
        "the pilot's sealed threshold 1 reads the writer's pages",
        TOOLS + "score_search_pilot.py",
        "            shown = DS.finder_pages(excerpts)\n",
        "            shown = DS.pages_from_excerpts(excerpts)  # mutant\n",
        HITS_TEST,
        H_SCORE_SEALED,
    ),
    (
        "the pilot's writer block counts no row",
        TOOLS + "score_search_pilot.py",
        "        for row in plan.rows:\n",
        "        for row in ():  # mutant\n",
        HITS_TEST,
        H_SCORE_WRITER,
    ),
]
#: The fixer's review of the three writer fixes (2026-09-23): the guards it found without a sweep case
#: (the empty-bucket branch, the field check, the unreadable mark, the no-search refusal, the
#: recorded-failure branch, every phrase exclusion), and the guards it added (the phrase exclusions
#: for a value half that holds, the hand-read marker, the finder kept off the hit pages, the resume at
#: `verify-hits`, the cut hit page, the public-address check, the per-rule cost, the lists for Martin).
FETCH_STAGE_PY = "scripts/remediation/phase3/fetch_stage.py"
W_EMPTY_BUCKET = "test_a_period_start_that_stores_nothing_is_filled_not_refused_as_same_bucket"
W_BUCKET_FIELD = "test_the_bucket_gate_reads_period_start_only"
W_HAND_READ = "test_a_hold_by_a_phrase_that_misfired_on_written_rows_goes_to_the_hand_read"
R_HAND_READ_NAMES = "test_every_hand_read_phrase_is_a_failing_half_phrase"
H_NO_SEARCH = "test_a_batch_that_bought_no_search_is_refused"
H_FINDER_AFTER = "test_a_finder_asked_after_verify_hits_is_not_shown_the_hit_page"
H_CUT = "test_a_quote_past_the_page_cap_is_unverified_not_fabricated"
H_CUT_TARGET = "test_a_fetched_target_knows_it_was_cut_too"
H_PRIVATE = "test_a_hit_url_on_a_non_public_host_is_recorded_not_fetched"
H_REDIRECT = "test_a_redirect_to_a_non_public_host_is_refused_before_it_is_followed"
H_FETCHER_PRIVATE = "test_the_fetcher_itself_refuses_a_non_public_address_before_a_socket"
H_LYRA_URL = "test_the_public_address_check_is_the_one_lyra_uses"
H_RULE_COST = "test_the_scorer_measures_what_each_rule_alone_refuses"
S_RESUME = "test_a_judged_search_batch_without_its_hit_report_resumes_at_verify_hits_alone"
_PROPOSED_LOOKBEHINDS = '        r"(?<!nor the )(?<!nor )(?<!if the )(?<!whether the )"\n'
_EVIDENCE_LOOKBEHINDS = (
    '        r"(?<!no )(?<!nothing in the )(?<!nor )\\bevidence supports the stored "\n'
)
REVIEW_FIX_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    # the period-bucket gate's two branches that had no case
    (
        "the bucket gate reads a stored None as a year",
        WRITE_STAGE,
        "    if old_value is None:\n        return None\n"
        "    bucket = categorize_period(int(old_value))\n",
        "    bucket = categorize_period(int(old_value))  # mutant\n",
        WRITE_TEST,
        W_EMPTY_BUCKET,
    ),
    (
        "the bucket gate reads every field as a year",
        WRITE_STAGE,
        '    if field_name != "period_start":\n        return None\n'
        "    bucket = same_bucket(old_value, new_value)\n",
        "    bucket = same_bucket(old_value, new_value)  # mutant\n",
        WRITE_TEST,
        W_BUCKET_FIELD,
    ),
    # the hit stage's guards that had no case
    (
        "a stored hit page that is not text is not marked unreadable",
        HIT_STAGE,
        "            outcome.unreadable = _unreadable(store, hit)\n",
        "            pass  # mutant\n",
        HITS_TEST,
        H_UNVERIFIED,
    ),
    (
        "verify-hits runs a batch that bought no search",
        HIT_STAGE,
        "        if not SE.search_slots(site):\n            raise InputError(\n",
        "        if False:  # mutant\n            raise InputError(\n",
        HITS_TEST,
        H_NO_SEARCH,
    ),
    (
        "a hit page recorded as not fetched is left out of the evidence",
        MODEL_STAGE,
        "        elif feature in recorded:\n"
        "            found.append((excerpt.url, feature, path, None, recorded[feature], False))\n",
        "",
        HITS_TEST,
        H_UNVERIFIED,
    ),
    # the phrase set: every exclusion, one at a time
    (
        "a quoted half name is not read as the reason half",
        REVIEW_STAGE,
        '        r"\\bthe " + _OPEN_QUOTE + r"(?:reason|first)" + _CLOSE_QUOTE + r" half fails',
        '        r"\\bthe (?:reason|first)" + r" half fails',
        REVIEW_TEST,
        R_NAMED,
    ),
    (
        "a quoted half name is not read as the value half",
        REVIEW_STAGE,
        "        + _OPEN_QUOTE\n"
        '        + r"(?:value|second|proposal|proposed[- ]value)"\n'
        "        + _CLOSE_QUOTE\n",
        '        + r"(?:value|second|proposal|proposed[- ]value)"  # mutant\n',
        REVIEW_TEST,
        R_NAMED,
    ),
    (
        "'the first half fails only if' holds a cleared row",
        REVIEW_STAGE,
        '+ r"(?:reason|first)" + _CLOSE_QUOTE + r" half fails\\b(?! only if)",\n',
        '+ r"(?:reason|first)" + _CLOSE_QUOTE + r" half fails\\b",  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'the second half fails only if' holds a cleared row",
        REVIEW_STAGE,
        '        + r" half fails\\b(?! only if)",\n',
        '        + r" half fails\\b",  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor the reason fails' holds a cleared row",
        REVIEW_STAGE,
        "        r\"(?<!nor )\\bthe (?:finding'?s |finder'?s )?reason(?:ing)? fails",
        "        r\"\\bthe (?:finding'?s |finder'?s )?reason(?:ing)? fails",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'the reason fails only if' holds a cleared row",
        REVIEW_STAGE,
        'reason(?:ing)? fails\\b(?! only if)",\n',
        'reason(?:ing)? fails\\b",  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor the proposal fails' holds a cleared row",
        REVIEW_STAGE,
        '    ("the proposal fails", r"(?<!nor )\\bthe proposal fails\\b(?! only if)"),\n',
        '    ("the proposal fails", r"\\bthe proposal fails\\b(?! only if)"),  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'the proposal fails only if' holds a cleared row",
        REVIEW_STAGE,
        '    ("the proposal fails", r"(?<!nor )\\bthe proposal fails\\b(?! only if)"),\n',
        '    ("the proposal fails", r"(?<!nor )\\bthe proposal fails\\b"),  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'does not show the proposed value wrong' holds a cleared row",
        REVIEW_STAGE,
        "not show (?!(?:that )?the propos)[^",
        "not show [^",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'no evidence supports the stored' holds a cleared row",
        REVIEW_STAGE,
        _EVIDENCE_LOOKBEHINDS,
        '        r"(?<!nothing in the )(?<!nor )\\bevidence supports the stored "  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nothing in the evidence supports the stored' holds a cleared row",
        REVIEW_STAGE,
        _EVIDENCE_LOOKBEHINDS,
        '        r"(?<!no )(?<!nor )\\bevidence supports the stored "  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor evidence supports the stored' holds a cleared row",
        REVIEW_STAGE,
        _EVIDENCE_LOOKBEHINDS,
        '        r"(?<!no )(?<!nothing in the )\\bevidence supports the stored "  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'the evidence supports the stored value being wrong' holds a cleared row",
        REVIEW_STAGE,
        "(?!'s? being| being| is wrong| was wrong)\",\n",
        '",  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor the proposed X is contradicted' alone holds a cleared row",
        REVIEW_STAGE,
        _PROPOSED_LOOKBEHINDS,
        '        r"(?<!nor )(?<!if the )(?<!whether the )"  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor proposed X is contradicted' holds a cleared row",
        REVIEW_STAGE,
        _PROPOSED_LOOKBEHINDS,
        '        r"(?<!nor the )(?<!if the )(?<!whether the )"  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'if the proposed X is contradicted' holds a cleared row",
        REVIEW_STAGE,
        _PROPOSED_LOOKBEHINDS,
        '        r"(?<!nor the )(?<!nor )(?<!whether the )"  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'whether the proposal is contradicted' holds a cleared row",
        REVIEW_STAGE,
        _PROPOSED_LOOKBEHINDS,
        '        r"(?<!nor the )(?<!nor )(?<!if the )"  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor its proposed value is contradicted' holds a cleared row",
        REVIEW_STAGE,
        '_NOR_OWNERS: tuple[str, ...] = (\n    "its",\n',
        "_NOR_OWNERS: tuple[str, ...] = (\n",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor the finding's proposed value' holds a cleared row",
        REVIEW_STAGE,
        '    "the finding[\'\\u2019]s",\n',
        "",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor the finder's proposed value' holds a cleared row",
        REVIEW_STAGE,
        '    "the finder[\'\\u2019]s",\n',
        "",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor finding's proposed value' holds a cleared row",
        REVIEW_STAGE,
        '    "finding[\'\\u2019]s",\n',
        "",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'nor finder's proposed value' holds a cleared row",
        REVIEW_STAGE,
        '    "finder[\'\\u2019]s",\n',
        "",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'contradicted by neither source' holds a cleared row",
        REVIEW_STAGE,
        '        r"contradicted\\b(?! (?:by|in) (?:neither|nothing|none|no)\\b)"\n',
        '        r"contradicted\\b"  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'contradicted neither by' holds a cleared row",
        REVIEW_STAGE,
        '        r"(?! neither\\b)"\n',
        "",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'contradicted only if' holds a cleared row",
        REVIEW_STAGE,
        '        r"(?! only if\\b)"\n',
        "",
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    (
        "'is contradicted by the evidence? No' holds a cleared row",
        REVIEW_STAGE,
        '        r"(?![^.,;:!?\\u2014\\u2013]{0,40}\\?)",\n',
        '        r"",  # mutant\n',
        REVIEW_TEST,
        R_BOTH_HOLD,
    ),
    # a hold by a phrase that misfired goes to the hand-read
    (
        "a hold by a misfiring phrase counts as a settled refusal",
        WRITE_STAGE,
        'f"line names a failing half ({failing!r}){_hand_read(failing)}; "\n',
        'f"line names a failing half ({failing!r}); "  # mutant\n',
        WRITE_TEST,
        W_HAND_READ,
    ),
    (
        "'neither half holds' is not routed to the hand-read",
        REVIEW_STAGE,
        '    "neither half holds": (4, 7),\n',
        "",
        WRITE_TEST,
        W_HAND_READ,
    ),
    (
        "a hand-read phrase names no failing-half phrase",
        REVIEW_STAGE,
        '    "neither half holds": (4, 7),\n',
        '    "neither half hold": (4, 7),  # mutant\n',
        REVIEW_TEST,
        R_HAND_READ_NAMES,
    ),
    # the finder is kept off the hit pages; the reviewer and the writer read them
    (
        "a finder planned after verify-hits is shown the hit pages",
        DISCOVER_STAGE,
        "        store=store,\n        hit_pages=False,\n        allow_absent=allow_absent,\n",
        "        store=store,\n        hit_pages=True,  # mutant\n        allow_absent=allow_absent,\n",
        HITS_TEST,
        H_FINDER_AFTER,
    ),
    (
        "the evidence carries the hit pages whatever the role",
        MODEL_STAGE,
        "    if hit_pages:\n        excerpts.extend(\n",
        "    if True:  # mutant\n        excerpts.extend(\n",
        HITS_TEST,
        H_FINDER_AFTER,
    ),
    (
        "the reviewer is not shown the hit pages",
        REVIEW_STAGE,
        "        hit_pages=True,\n",
        "        hit_pages=False,  # mutant\n",
        HITS_TEST,
        H_REVIEW_PAGE,
    ),
    (
        "the writer does not read the hit pages",
        WRITE_STAGE,
        "site_id=site_id, site=site, store=evidence, hit_pages=True, failures=failures",
        "site_id=site_id, site=site, store=evidence, hit_pages=False, failures=failures",
        HITS_TEST,
        H_UNVERIFIED,
    ),
    # a batch stopped inside verify-hits resumes there
    (
        "a judged search batch without its hit report re-runs every stage",
        MASS_RUN,
        "        if judged_state(root)[0] == DONE and hit_state(root) is not None:\n",
        "        if False:  # mutant\n",
        SEARCH_TEST,
        S_RESUME,
    ),
    # a quote past the page cap is unverified, not fabricated
    (
        "a quote missing from a cut hit page is called fabricated",
        WRITE_STAGE,
        "        if page.truncated and not DS.quote_occurs(claim.quote, page.citable):\n",
        "        if False:  # mutant\n",
        HITS_TEST,
        H_CUT,
    ),
    (
        "a hit page never knows it was cut",
        MODEL_STAGE,
        "            cut = body.endswith(marker)\n",
        "            cut = False  # mutant\n",
        HITS_TEST,
        H_CUT,
    ),
    (
        "a fetched target never knows it was cut",
        MODEL_STAGE,
        "                truncated=text is not None and text.endswith(F.TRUNCATION_MARKER),\n",
        "                truncated=False,  # mutant\n",
        HITS_TEST,
        H_CUT_TARGET,
    ),
    # a hit on a non-public host is never asked, nor a redirect into one
    (
        "the hit stage hands a non-public hit to the fetcher",
        HIT_STAGE,
        "                F.assert_public_address(hit.url)\n",
        "                pass  # mutant\n",
        HITS_TEST,
        H_PRIVATE,
    ),
    (
        "the fetcher asks a non-public address",
        FETCH_STAGE_PY,
        "        assert_named_feature(url)\n        assert_public_address(url)\n",
        "        assert_named_feature(url)\n",
        HITS_TEST,
        H_FETCHER_PRIVATE,
    ),
    (
        "the fetcher follows a redirect into a non-public address",
        FETCH_STAGE_PY,
        '            event_hooks={"request": [_refuse_non_public_hop]},\n',
        "",
        HITS_TEST,
        H_REDIRECT,
    ),
    (
        "Lyra keeps a second spelling of the address check",
        "pipeline/lyra/handlers/content_fetch.py",
        "from pipeline.utils.http import is_public_http_url\n",
        "from pipeline.utils.http import is_public_http_url as _shared_check\n"
        "\n\ndef is_public_http_url(url: str) -> bool:  # mutant: a second spelling\n"
        "    return _shared_check(url)\n",
        HITS_TEST,
        H_LYRA_URL,
    ),
    # the scorer's per-rule cost reaches each rule
    (
        "the scorer's (a) switch misses the bucket gate",
        TOOLS + "score_search_pilot.py",
        '    "(a) period-bucket gate": ((W, "_same_bucket_refusal", lambda *args, **kwargs: None),),\n',
        '    "(a) period-bucket gate": (),  # mutant\n',
        HITS_TEST,
        H_RULE_COST,
    ),
    (
        "the scorer's (b) switch misses the hit-page check",
        TOOLS + "score_search_pilot.py",
        '        (W, "_hit_page_refusal", lambda **kwargs: None),\n',
        "",
        HITS_TEST,
        H_RULE_COST,
    ),
    (
        "the scorer's (c) switch misses the contradiction hold",
        TOOLS + "score_search_pilot.py",
        '    "(c) contradiction hold": ((RS, "failing_half", lambda reason: None),),\n',
        '    "(c) contradiction hold": (),  # mutant\n',
        HITS_TEST,
        H_RULE_COST,
    ),
    # the lists Martin decides on
    (
        "the hold list for Martin misses a written row",
        TOOLS + "measure_review_holds.py",
        '        if phrase is not None:\n            held.append({**record(row), "phrase": phrase})\n',
        '        if False:  # mutant\n            held.append({**record(row), "phrase": phrase})\n',
        TOOLS_TEST,
        T_MEASURE,
    ),
    (
        "the bucket list for Martin misses a written row",
        TOOLS + "measure_review_holds.py",
        "            if inside is not None:\n                bucket.append(",
        "            if False:  # mutant\n                bucket.append(",
        TOOLS_TEST,
        T_MEASURE,
    ),
]
#: The owner cases of HUMAN_ONLY section B (2026-09-23): the classifier's gates, the witness rule, the
#: duplicate rule, what is fetched, the coordinate plan, the research behind the external-id repair's
#: second wave and that wave's position gate. Every label starts with "bcases" so the set runs alone.
BCASES = "scripts/remediation/bcases/"
BCASES_TEST = "tests/remediation/test_bcases.py"
BCASES_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "bcases: a P625 imported from Wikipedia is a second witness",
        BCASES + "classify.py",
        "    if a.derived_from == b.kind or b.derived_from == a.kind:\n        return False\n",
        "    if False:  # mutant\n        return False\n",
        BCASES_TEST,
        "test_a_p625_imported_from_english_wikipedia_is_not_a_second_witness",
    ),
    (
        "bcases: one point copied twice is two witnesses",
        BCASES + "classify.py",
        "    return _m(a, b) > same_point_m(a, b)\n",
        "    return True  # mutant\n",
        BCASES_TEST,
        "test_petroglyph_beach_counts_once_because_both_points_are_one_point",
    ),
    (
        "bcases: a witness at the stored point does not stop a move",
        BCASES + "classify.py",
        "    if pairs and not near:\n",
        "    if pairs:  # mutant\n",
        BCASES_TEST,
        "test_a_pair_that_agrees_elsewhere_while_one_of_them_is_at_the_stored_point_is_read",
    ),
    (
        "bcases: a shared item speaks for the site's point",
        BCASES + "classify.py",
        '    if shared.get(qid, 0) > 1:\n        return "shared-item", p31\n',
        '    if False:  # mutant\n        return "shared-item", p31\n',
        BCASES_TEST,
        "test_an_item_that_is_not_the_site_is_never_a_witness",
    ),
    (
        "bcases: a village speaks for the site's point",
        BCASES + "classify.py",
        '    if any(map(is_container_class, p31)):\n        return "container-item", p31\n',
        '    if False:  # mutant\n        return "container-item", p31\n',
        BCASES_TEST,
        "test_an_item_that_is_not_the_site_is_never_a_witness",
    ),
    (
        "bcases: an item of another name speaks for the site",
        BCASES + "classify.py",
        '    if identity not in ("N1", "N2"):\n',
        "    if False:  # mutant\n",
        BCASES_TEST,
        "test_an_item_that_is_not_the_site_is_never_a_witness",
    ),
    (
        "bcases: a museum object is moved from anywhere",
        BCASES + "classify.py",
        '        if verdict["verdict"] == "move" and not at:\n',
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_museum_object_stored_elsewhere_is_never_moved_to_the_find_spot",
    ),
    (
        "bcases: a class word matches inside another word",
        BCASES + "classify.py",
        '    return any(re.search(r"(?<![\\w-])" + re.escape(w) + r"(?![\\w-])", low) for w in words)\n',
        "    return any(w in low for w in words)  # mutant\n",
        BCASES_TEST,
        "test_a_modern_place_contains_a_site_and_an_ancient_one_is_the_site",
    ),
    (
        "bcases: an ancient city is a container",
        BCASES + "classify.py",
        "    return _has_word(label, CONTAINER_WORDS) and not _has_word(label, SITE_WORDS)\n",
        "    return _has_word(label, CONTAINER_WORDS)  # mutant\n",
        BCASES_TEST,
        "test_a_modern_place_contains_a_site_and_an_ancient_one_is_the_site",
    ),
    (
        "bcases: a name of generic words matches the item",
        BCASES + "classify.py",
        "        item_names = {_dup_key(n) for n in known_names(qid, names)} - {()}\n",
        "        item_names = {_dup_key(n) for n in known_names(qid, names)}  # mutant\n",
        BCASES_TEST,
        "test_a_name_of_generic_words_only_is_no_name_of_the_item",
    ),
    (
        "bcases: a group that is not all duplicates gets a survivor",
        BCASES + "classify.py",
        "        if any(frozenset(pair) not in dup_set for pair in itertools.combinations(members, 2)):\n",
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_group_whose_members_are_not_all_duplicates_is_left_unresolved",
    ),
    (
        "bcases: the survivor rule ignores content links",
        BCASES + "classify.py",
        '    return (-int(site["n_links"]), -sources, str(site["created_at"]), str(site["id"]))\n',
        '    return (0, -sources, str(site["created_at"]), str(site["id"]))  # mutant\n',
        BCASES_TEST,
        "test_dooeys_cairn_and_ballymacaldrack_are_one_tomb_and_the_richer_row_survives",
    ),
    (
        "bcases: a busy answer is read back from the cache",
        BCASES + "collect.py",
        "        payload = net.get_json(url, params=dict(params), ns=ns, force=attempt > 0)\n",
        "        payload = net.get_json(url, params=dict(params), ns=ns, force=False)  # mutant\n",
        BCASES_TEST,
        "test_a_busy_api_is_asked_again_past_the_cache_and_a_refusal_raises",
    ),
    (
        "bcases: an API refusal is asked again like a busy answer",
        BCASES + "collect.py",
        '        if error.get("code") not in TRANSIENT_ERRORS:\n',
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_busy_api_is_asked_again_past_the_cache_and_a_refusal_raises",
    ),
    (
        "bcases: a partial Wikipedia answer is read as complete",
        BCASES + "collect.py",
        '        if "continue" in body:\n',
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_wikipedia_coordinates_are_asked_for_every_page_and_a_partial_answer_raises",
    ),
    (
        "bcases: Wikipedia is asked for ten coordinates a request",
        BCASES + "collect.py",
        '                "colimit": "max",\n',
        "",
        BCASES_TEST,
        "test_wikipedia_coordinates_are_asked_for_every_page_and_a_partial_answer_raises",
    ),
    (
        "bcases: a short export is classified",
        BCASES + "collect.py",
        "    if len(rows) != CURATED_SITES:\n",
        "    if False:  # mutant\n",
        BCASES_TEST,
        "test_a_short_export_is_refused_not_classified",
    ),
    (
        "bcases: a move with one witness is planned",
        BCASES + "coord_plan.py",
        '        if len(row["agreeing"]) < 2:\n',
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_move_needs_two_witnesses_a_geom_a_real_change_and_a_point_on_earth",
    ),
    (
        "bcases: a move without a geom is planned",
        BCASES + "coord_plan.py",
        '        if old["geom"] is None:\n',
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_move_needs_two_witnesses_a_geom_a_real_change_and_a_point_on_earth",
    ),
    (
        "bcases: a move to the stored point is planned",
        BCASES + "coord_plan.py",
        '        if float(old["lat"]) == lat and float(old["lon"]) == lon:\n',
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_move_needs_two_witnesses_a_geom_a_real_change_and_a_point_on_earth",
    ),
    (
        "bcases: a move off the Earth is planned",
        BCASES + "coord_plan.py",
        "        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):\n",
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_move_needs_two_witnesses_a_geom_a_real_change_and_a_point_on_earth",
    ),
    (
        "bcases: the statement moves lat and lon without geom",
        BCASES + "coord_plan.py",
        "        \"        HAVING array_agg(column_name ORDER BY column_name) <> ARRAY['geom', 'lat', 'lon']\",\n",
        '        "        HAVING false",\n',
        BCASES_TEST,
        "test_the_statement_is_guarded_and_every_change_goes_through_the_primitive",
    ),
    (
        "bcases: the statement writes a geom that is not the point",
        BCASES + "coord_plan.py",
        "        f\"        RAISE EXCEPTION '{LABEL}: % planned geom value(s) are not the planned point', bad;\",\n",
        '        "        NULL;",\n',
        BCASES_TEST,
        "test_the_statement_is_guarded_and_every_change_goes_through_the_primitive",
    ),
    (
        "bcases: the plan runs a statement edited by hand",
        BCASES + "coord_plan.py",
        '        if path.read_text(encoding="utf-8") != sql:\n',
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_check_and_verify_read_the_database_and_refuse_an_edited_statement",
    ),
    (
        "bcases: verify accepts a move nobody journalled",
        BCASES + "coord_plan.py",
        "        if keys != {row.change_key for row in rows}:\n",
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_check_and_verify_read_the_database_and_refuse_an_edited_statement",
    ),
    (
        "bcases: the evidence renders in dict order and breaks the round trip",
        BCASES + "coord_plan.py",
        "json.dumps(list(row.evidence), ensure_ascii=False, sort_keys=True)",
        "json.dumps(list(row.evidence), ensure_ascii=False)",
        BCASES_TEST,
        "test_check_and_verify_read_the_database_and_refuse_an_edited_statement",
    ),
    (
        "bcases: rule A takes the village a fort is named after",
        BCASES + "qid_research.py",
        "        if c is not None and is_site_kind(c) and placed:\n",
        "        if c is not None and placed:  # mutant\n",
        BCASES_TEST,
        "test_rule_a_never_takes_a_village_for_the_hillfort_it_is_named_after",
    ),
    (
        "bcases: rule B takes one of two name matches",
        BCASES + "qid_research.py",
        "    if len(near) == 1:\n",
        "    if near:  # mutant\n",
        BCASES_TEST,
        "test_rule_b_needs_exactly_one_name_match_within_the_gate",
    ),
    (
        "bcases: rule A accepts an article far from the site",
        BCASES + "qid_research.py",
        "        ) or (article_m is not None and article_m <= RADIUS_M)\n",
        "        ) or (article_m is not None)  # mutant\n",
        BCASES_TEST,
        "test_rule_a_proves_the_place_by_the_article_when_wikidata_points_elsewhere",
    ),
    (
        "bcases: the wave-2 repair takes a replacement without its position proof",
        TOOLS + "qid_repair.py",
        "        if gate_m is not None and (site.gate_m is None or not 0 <= site.gate_m <= gate_m):\n",
        "        if False:  # mutant\n",
        TOOLS_TEST,
        "test_a_wave_two_replacement_without_its_position_proof_is_refused",
    ),
    (
        "bcases: the wave-2 repair journals under wave 1's stamp",
        TOOLS + "qid_repair.py",
        "    stamp = wave.rollback_stamp if reversal else wave.run_stamp\n",
        "    stamp = ROLLBACK_STAMP if reversal else RUN_STAMP  # mutant\n",
        TOOLS_TEST,
        "test_wave_two_renders_under_its_own_stamp_and_wave_one_is_what_was_applied",
    ),
    (
        "bcases: the wave-2 verify reads wave 1's journal",
        TOOLS + "qid_repair.py",
        '                f"WHERE run_stamp = {lanes.sql_text(wave.run_stamp)}) t;"\n',
        '                f"WHERE run_stamp = {lanes.sql_text(RUN_STAMP)}) t;"\n',
        TOOLS_TEST,
        "test_wave_two_check_and_verify_read_their_own_rows_and_stamp",
    ),
]
#: The review of the owner cases (2026-09-23): the guards a reviewer's own mutations found untested -
#: the witness rule's grids and floors, the item gate, the fetch and cache shape checks, the plan's
#: UUID/whole-site/compare checks, the research rules - and the new guards of that review (rounded
#: copies, the preferred-rank P625, the link a kept name does not vouch for, a transboundary text, a
#: duplicate across a border). Labels start with "bcases" so `mutation_sweep.py bcases` runs them too.
_CL, _CO, _CP = BCASES + "classify.py", BCASES + "collect.py", BCASES + "coord_plan.py"
_IN, _QR = BCASES + "inputs.py", BCASES + "qid_research.py"
_RULE_A = "test_rule_a_needs_the_exact_title_of_an_existing_article_of_another_item"
_RULE_B = "test_rule_b_takes_neither_the_old_item_nor_a_partial_name_nor_a_wikimedia_page"
_ARTICLE = "test_an_article_is_a_witness_only_for_its_own_item_on_earth"
_COMPARE = "test_check_and_verify_compare_every_column_and_the_geometry"
_STATEMENT = "test_the_statement_is_guarded_and_every_change_goes_through_the_primitive"
_GRIDS = "test_the_witnesses_carry_the_grid_their_digits_are_written_on"
BCASES_REVIEW_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "bcases: a rounded copy is a second witness",
        _CL,
        "    if rounded_copy(a, b) is not None:\n        return False\n",
        "    if False:  # mutant\n        return False\n",
        BCASES_TEST,
        "test_a_rounded_copy_further_apart_than_an_arcsecond_is_still_one_witness",
    ),
    (
        "bcases: any value on the grid is a rounding",
        _CL,
        "    return math.floor(units + slack) <= round(rounded / step) <= math.ceil(units - slack)\n",
        "    return True  # mutant\n",
        BCASES_TEST,
        "test_calakmul_moves_to_the_item_where_wikidata_and_wikipedia_agree",
    ),
    (
        "bcases: two equal points read as a rounding",
        _CL,
        "    if (a.lat, a.lon) == (b.lat, b.lon):\n        return None\n",
        "    if False:  # mutant\n        return None\n",
        BCASES_TEST,
        "test_petroglyph_beach_counts_once_because_both_points_are_one_point",
    ),
    (
        "bcases: a rounding on one axis is a copy",
        _CL,
        "            and _rounds_to(fine.lon, coarse.lon, coarse.step)\n",
        "",
        BCASES_TEST,
        "test_one_point_within_an_arcsecond_is_one_witness",
    ),
    (
        "bcases: one point is five metres again",
        _CL,
        "SAME_POINT_M = METRES_PER_DEGREE / 3600.0\n",
        "SAME_POINT_M = 5.0  # mutant\n",
        BCASES_TEST,
        "test_one_point_within_an_arcsecond_is_one_witness",
    ),
    (
        "bcases: a coarse grid does not widen one point",
        _CL,
        "        *(w.step * METRES_PER_DEGREE for w in (a, b)),\n",
        "",
        BCASES_TEST,
        "test_a_point_given_to_three_decimals_cannot_confirm_another_within_its_step",
    ),
    (
        "bcases: a coarse P625 precision does not widen one point",
        _CL,
        "        *(2.0 * w.precision_m for w in (a, b)),\n",
        "",
        BCASES_TEST,
        "test_a_coarse_wikidata_precision_makes_two_points_one",
    ),
    (
        "bcases: a whole-degree grid swallows an arcsecond",
        _CL,
        "    return min(ON_GRID * step, ON_GRID_MAX) / step\n",
        "    return ON_GRID  # mutant\n",
        BCASES_TEST,
        "test_a_rounded_copy_further_apart_than_an_arcsecond_is_still_one_witness",
    ),
    (
        "bcases: the P625 witness has no grid",
        _CL,
        '                grid_of(p625["lat"], p625["lon"]),\n',
        "                0.0,  # mutant\n",
        BCASES_TEST,
        _GRIDS,
    ),
    (
        "bcases: the article witness has no grid",
        _CL,
        "                step=step,\n",
        "                step=0.0,  # mutant\n",
        BCASES_TEST,
        _GRIDS,
    ),
    (
        "bcases: a kept name hides a wrong link",
        _CL,
        '    suspect = [q for q in ("Q1", "Q2", "Q4") if link[q]] if NAME_GROUP[cls] == "keep" else []\n',
        "    suspect: list[str] = []  # mutant\n",
        BCASES_TEST,
        "test_a_kept_name_does_not_vouch_for_its_link",
    ),
    (
        "bcases: an item without a coordinate is a residual",
        _CL,
        '        elif link["Q3"]:\n            cls = "Q3"\n',
        '        elif False:  # mutant\n            cls = "Q3"\n',
        BCASES_TEST,
        "test_an_item_without_a_coordinate_is_a_wrong_link_not_a_residual",
    ),
    (
        "bcases: a transboundary text gets one country",
        _CL,
        '            cls = "c2" if desc_stored and desc_ne else "b"\n',
        '            cls = "b"  # mutant\n',
        BCASES_TEST,
        "test_a_site_whose_own_text_spans_the_border_is_not_a_wrong_country",
    ),
    (
        "bcases: the counts carry keys JSON cannot give back",
        _CL,
        '                    "open" if r["state"] == "open" else "written since the census" for r in b2_rows\n',
        '                    r["state"] != "open" for r in b2_rows  # mutant\n',
        BCASES_TEST,
        "test_the_counts_returned_are_the_counts_written",
    ),
    (
        "bcases: a duplicate across a border goes to the scope lane",
        _CL,
        "        if len(countries) > 1:\n",
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_one_site_recorded_on_two_sides_of_a_border_is_held_for_the_owner",
    ),
    (
        "bcases: a road's point speaks for the site",
        _CL,
        '    if any(map(is_linear_or_areal_class, p31)):\n        return "linear-or-areal-item", p31\n',
        '    if False:  # mutant\n        return "linear-or-areal-item", p31\n',
        BCASES_TEST,
        "test_a_road_or_a_wall_is_a_line_whose_point_is_an_arbitrary_spot",
    ),
    (
        "bcases: another item's article is a witness",
        _CL,
        'candidate.get("wikibase_item") == qid and not candidate.get("missing")',
        'not candidate.get("missing")',
        BCASES_TEST,
        _ARTICLE,
    ),
    (
        "bcases: a missing article is a witness",
        _CL,
        'candidate.get("wikibase_item") == qid and not candidate.get("missing")',
        'candidate.get("wikibase_item") == qid',
        BCASES_TEST,
        _ARTICLE,
    ),
    (
        "bcases: an article's point on another globe is a witness",
        _CL,
        'page.get("lat") is None or (page.get("globe") or "earth") != "earth"',
        'page.get("lat") is None',
        BCASES_TEST,
        _ARTICLE,
    ),
    (
        "bcases: a P625 on another globe is a witness",
        _CL,
        '    elif p625.get("globe") not in (None, "Q2"):\n',
        "    elif False:  # mutant\n",
        BCASES_TEST,
        "test_a_p625_on_another_globe_is_no_witness",
    ),
    (
        "bcases: an object with two find-spots moves to one",
        _CL,
        'if len(record.get("p189") or ()) == 1 and holders:',
        'if record.get("p189") and holders:',
        BCASES_TEST,
        "test_an_object_with_two_find_spots_names_no_find_spot",
    ),
    (
        "bcases: a coarse P625 does not widen the tolerance",
        _CL,
        "    return max([TOLERANCE_M, *(w.precision_m for w in ws)])\n",
        "    return TOLERANCE_M  # mutant\n",
        BCASES_TEST,
        "test_the_tolerance_widens_with_a_coarse_wikidata_precision",
    ),
    (
        "bcases: a P625 imported by URL is a second witness",
        _CL,
        '    return any("en.wikipedia.org" in url for url in references.get("P4656") or ())\n',
        "    return False  # mutant\n",
        BCASES_TEST,
        "test_a_p625_whose_import_url_is_english_wikipedia_is_not_a_second_witness",
    ),
    (
        "bcases: a normal P625 is read beside a preferred one",
        _CO,
        '    return [s for s in statements if s.get("rank") == "preferred"] or statements\n',
        "    return statements  # mutant\n",
        BCASES_TEST,
        "test_the_witness_is_the_preferred_p625_and_never_a_deprecated_one",
    ),
    (
        "bcases: a deprecated P625 is a witness",
        "scripts/remediation/mechanical/plan.py",
        '    return [c for c in (entity.get("claims") or {}).get(prop, []) if c.get("rank") != "deprecated"]\n',
        '    return list((entity.get("claims") or {}).get(prop, []))  # mutant\n',
        BCASES_TEST,
        "test_the_witness_is_the_preferred_p625_and_never_a_deprecated_one",
    ),
    (
        "bcases: an item Wikidata did not answer is taken as answered",
        _CO,
        "    if absent:\n",
        "    if False:  # mutant\n",
        BCASES_TEST,
        "test_wikidata_must_answer_for_every_item_asked",
    ),
    (
        "bcases: an answer without entities is read",
        _CO,
        "    if not isinstance(entities, dict):\n",
        "    if False:  # mutant\n",
        BCASES_TEST,
        "test_wikidata_must_answer_for_every_item_asked",
    ),
    (
        "bcases: a title Wikipedia did not answer is read",
        _CO,
        "            if page is None:\n",
        "            if False:  # mutant\n",
        BCASES_TEST,
        "test_wikipedia_must_answer_for_every_title_asked",
    ),
    (
        "bcases: a Wikipedia answer without a query is read",
        _CO,
        "        if not isinstance(query, dict):\n",
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_wikipedia_must_answer_for_every_title_asked",
    ),
    (
        "bcases: an answer that is not JSON is read",
        _CO,
        "        if not isinstance(body, dict):\n",
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_an_answer_that_is_not_a_json_object_is_refused",
    ),
    (
        "bcases: a census link held twice is overwritten",
        _IN,
        '        if row["kind"] in mine:\n',
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_census_link_held_twice_is_refused_not_overwritten",
    ),
    (
        "bcases: a missing cache file is not named",
        _IN,
        '    if not path.exists():\n        raise InputError(f"{path} is missing - `run.py collect` writes it")\n',
        '    if False:  # mutant\n        raise InputError(f"{path} is missing - `run.py collect` writes it")\n',
        BCASES_TEST,
        "test_a_cache_file_that_is_missing_or_not_derived_is_refused",
    ),
    (
        "bcases: a cache file without records is read",
        _IN,
        "    if not isinstance(records, dict):\n",
        "    if False:  # mutant\n",
        BCASES_TEST,
        "test_a_cache_file_that_is_missing_or_not_derived_is_refused",
    ),
    (
        "bcases: a plan names a site by something else than a UUID",
        _CP,
        '        if not UUID_RE.match(sid):\n            raise PlanError(f"{sid!r} is not a UUID")\n        if sid in seen:\n',
        '        if False:  # mutant\n            raise PlanError(f"{sid!r} is not a UUID")\n        if sid in seen:\n',
        BCASES_TEST,
        "test_a_plan_names_each_site_once_and_by_its_uuid",
    ),
    (
        "bcases: a site is planned twice",
        _CP,
        "        if sid in seen:\n",
        "        if False:  # mutant\n",
        BCASES_TEST,
        "test_a_plan_names_each_site_once_and_by_its_uuid",
    ),
    (
        "bcases: a statement moves part of a site",
        _CP,
        "    if len(rows) % len(COLUMNS):\n",
        "    if False:  # mutant\n",
        BCASES_TEST,
        "test_a_statement_moves_whole_sites_only",
    ),
    (
        "bcases: the read interpolates what is not a UUID",
        _CP,
        "    for sid in ids:\n        if not UUID_RE.match(sid):\n",
        "    for sid in ids:\n        if False:  # mutant\n",
        BCASES_TEST,
        "test_the_read_names_its_sites_by_uuid_only",
    ),
    (
        "bcases: verify accepts a geom that is not the point",
        _CP,
        '            if not live["geom_is_point"]:\n',
        "            if False:  # mutant\n",
        BCASES_TEST,
        _COMPARE,
    ),
    (
        "bcases: check accepts another old geom",
        _CP,
        '            if want == "old" and live["geom"] != expected:\n',
        "            if False:  # mutant\n",
        BCASES_TEST,
        _COMPARE,
    ),
    (
        "bcases: check accepts a moved lat",
        _CP,
        "        elif float(live[row.column]) != float(expected):\n",
        "        elif False:  # mutant\n",
        BCASES_TEST,
        _COMPARE,
    ),
    (
        "bcases: the statement runs without a statement timeout",
        _CP,
        '        f"SET LOCAL statement_timeout = {sql_literal(STATEMENT_TIMEOUT)};",\n',
        "",
        BCASES_TEST,
        _STATEMENT,
    ),
    (
        "bcases: guard 3 does not compare the old lon",
        _CP,
        "        \"        OR (p.column_name = 'lon' AND u.lon IS DISTINCT FROM p.old_value::double precision)\",\n",
        "",
        BCASES_TEST,
        _STATEMENT,
    ),
    (
        "bcases: guard 3 does not compare the old geom",
        _CP,
        "        \"        OR (p.column_name = 'geom' AND u.geom IS DISTINCT FROM p.old_value::geometry);\",\n",
        '        "        ;",\n',
        BCASES_TEST,
        _STATEMENT,
    ),
    (
        "bcases: invariant 1 does not read the new lat back",
        _CP,
        "        \"     WHERE (p.column_name = 'lat' AND u.lat IS DISTINCT FROM p.new_value::double precision)\",\n",
        '        "     WHERE false",\n',
        BCASES_TEST,
        _STATEMENT,
    ),
    (
        "bcases: rule A takes a redirect",
        _QR,
        ' and not page.get("redirected"):',
        ":  # mutant",
        BCASES_TEST,
        _RULE_A,
    ),
    (
        "bcases: rule A takes a missing page",
        _QR,
        ' and not page.get("missing") and not page.get("redirected"):',
        ' and not page.get("redirected"):',
        BCASES_TEST,
        _RULE_A,
    ),
    (
        "bcases: rule A replaces an item by itself",
        _QR,
        "    if item and item != old and not",
        "    if item and not",
        BCASES_TEST,
        _RULE_A,
    ),
    (
        "bcases: rule B takes the old item back",
        _QR,
        '        if c["qid"] != old\n',
        "        if True  # mutant\n",
        BCASES_TEST,
        _RULE_B,
    ),
    (
        "bcases: rule B takes a partial name",
        _QR,
        '        and c["identity"] in ("N1", "N2")\n',
        '        and c["identity"] != "none"  # mutant\n',
        BCASES_TEST,
        _RULE_B,
    ),
    (
        "bcases: rule B takes a Wikimedia page",
        _QR,
        ' or label.startswith("Wikimedia")',
        "",
        BCASES_TEST,
        _RULE_B,
    ),
    (
        "bcases: a geosearch answer without its list is read",
        _QR,
        '    hits = (body.get("query") or {}).get("geosearch")\n    if hits is None:\n',
        '    hits = (body.get("query") or {}).get("geosearch")\n    if False:  # mutant\n',
        BCASES_TEST,
        "test_the_research_refuses_an_answer_without_its_list",
    ),
    (
        "bcases: a search answer without its list is read",
        _QR,
        '    hits = body.get("search")\n    if hits is None:\n',
        '    hits = body.get("search")\n    if False:  # mutant\n',
        BCASES_TEST,
        "test_the_research_refuses_an_answer_without_its_list",
    ),
    (
        "bcases: the wave-2 journal cites wave 1's research",
        TOOLS + "qid_repair.py",
        "{_evidence_json(row, wave.research)}",
        "{_evidence_json(row, WAVE1.research)}",
        TOOLS_TEST,
        "test_the_delivered_wave_two_statements_are_the_rendered_ones",
    ),
    (
        "bcases: a wave-2 gate is typed wrong",
        TOOLS + "qid_repair.py",
        "        506.7,\n",
        "        50.7,  # mutant\n",
        TOOLS_TEST,
        "test_every_wave_two_gate_is_the_distance_the_research_measured",
    ),
]
P4_MODEL = "scripts/remediation/phase4/model4.py"
P4_INIT = "scripts/remediation/phase4/__init__.py"
P4_MODEL_TEST = "tests/remediation/test_phase4_model.py"
#: The Phase-4/5 contracts (WB-00): every guard in `phase4/model4.py` and the package shim, each with
#: the one test that must fail when it is broken.
PHASE4_MODEL_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "p4 model: a bool passes as an int",
        P4_MODEL,
        "    return isinstance(value, int) and not isinstance(value, bool)\n",
        "    return isinstance(value, int)  # mutant\n",
        P4_MODEL_TEST,
        "test_a_bool_is_never_an_int",
    ),
    (
        "p4 model: an empty or reversed range passes",
        P4_MODEL,
        "    if not start < end:\n",
        "    if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_an_empty_or_reversed_range_is_refused",
    ),
    (
        "p4 model: overlapping drop ranges pass",
        P4_MODEL,
        "        if low < previous_end:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_overlapping_or_unsorted_drops_are_refused",
    ),
    (
        "p4 model: a drop range leaves its sentence",
        P4_MODEL,
        "        if low < start or high > end:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_drop_range_outside_its_sentence_is_refused",
    ),
    (
        "p4 model: a card drop leaves its sentence",
        P4_MODEL,
        '                _need_drops_within(item.drop, cut.start, cut.end, f"card item {item.sentence}")\n',
        "",
        P4_MODEL_TEST,
        "test_a_card_drop_stays_inside_its_sentence",
    ),
    (
        "p4 model: a constructed drop need not be a pair",
        P4_MODEL,
        "        if not isinstance(pair, tuple) or len(pair) != 2:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_constructed_drop_is_a_pair_too",
    ),
    (
        "p4 model: a JSON drop need not be a pair",
        P4_MODEL,
        "        if not isinstance(pair, list) or len(pair) != 2:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_drop_is_a_pair",
    ),
    (
        "p4 model: any string is a sha256 digest",
        P4_MODEL,
        "    if not isinstance(value, str) or not _HEX64.fullmatch(value):\n",
        "    if not isinstance(value, str):  # mutant\n",
        P4_MODEL_TEST,
        "test_digests_are_lowercase_sha256_hex",
    ),
    (
        "p4 model: an unknown key is dropped",
        P4_MODEL,
        "    if missing or unknown:\n",
        "    if missing:  # mutant\n",
        P4_MODEL_TEST,
        "test_an_unknown_key_is_refused_not_dropped",
    ),
    (
        "p4 model: a missing key is not named",
        P4_MODEL,
        "    if missing or unknown:\n",
        "    if unknown:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_missing_key_is_refused_even_when_its_value_would_be_null",
    ),
    (
        "p4 model: NaN is read as JSON",
        P4_MODEL,
        "    return json.loads(text, parse_constant=_refuse_constant)\n",
        "    return json.loads(text)  # mutant\n",
        P4_MODEL_TEST,
        "test_nan_and_infinity_are_not_json",
    ),
    (
        "p4 model: a string passes for an enum member",
        P4_MODEL,
        "    if not isinstance(value, enum_cls):\n",
        "    if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_constructed_record_takes_enum_members_not_their_strings",
    ),
    (
        "p4 model: the AI mark does not follow the lane",
        P4_MODEL,
        "        if self.ai is not LANE_AI[self.lane]:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_the_ai_mark_follows_the_lane",
    ),
    (
        "p4 model: the change note does not follow the lane",
        P4_MODEL,
        "        if self.attribution.changes is not LANE_CHANGES[self.lane]:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_the_change_note_follows_the_lane",
    ),
    (
        "p4 model: any ai_system is disclosed",
        P4_MODEL,
        "        if self.ai_system != AI_SYSTEM:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_the_disclosed_ai_system_is_the_model_that_is_called",
    ),
    (
        "p4 model: the disclosure names a model that is not called",
        P4_MODEL,
        'AI_SYSTEM = f"{MODEL} via Pi (an-sites-remediation-2026-09)"\n',
        'AI_SYSTEM = "deepseek via Pi (an-sites-remediation-2026-09)"  # mutant\n',
        P4_MODEL_TEST,
        "test_the_disclosed_ai_system_is_the_model_that_is_called",
    ),
    (
        "p4 model: published text under another licence",
        P4_MODEL,
        "        if self.licence is not PUBLISHED_LICENCE:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_published_text_is_cc_by_sa_4_and_links_that_licence",
    ),
    (
        "p4 model: the attribution links another licence",
        P4_MODEL,
        "        if self.attribution.licence_url != PUBLISHED_LICENCE_URL:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_published_text_is_cc_by_sa_4_and_links_that_licence",
    ),
    (
        "p4 model: the attribution points at an uncited page",
        P4_MODEL,
        "        if self.attribution.url not in {source.url for source in self.sources}:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_the_attribution_points_at_a_cited_source",
    ),
    (
        "p4 model: lane 0 or L gets a full provenance",
        P4_MODEL,
        "        if self.lane not in LANE_CHANGES:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_lane_0_and_lane_l_have_no_full_provenance",
    ),
    (
        "p4 model: a sentence cites an unlisted source",
        P4_MODEL,
        "        if unknown:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_every_sentence_names_a_listed_source",
    ),
    (
        "p4 model: a listed source is cited by nothing",
        P4_MODEL,
        "        if uncited:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_every_listed_source_is_cited",
    ),
    (
        "p4 model: a source is listed twice",
        P4_MODEL,
        "        if not source_ids or len(set(source_ids)) != len(source_ids):\n",
        "        if not source_ids:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_source_is_listed_once",
    ),
    (
        "p4 model: Wikidata is cited",
        P4_MODEL,
        "        if kind not in CITABLE_KINDS:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_wikidata_is_a_witness_and_never_cited",
    ),
    (
        "p4 model: sentences leave source order",
        P4_MODEL,
        "            if sentence.start < last_end.get(sentence.src, 0):\n",
        "            if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_sentences_of_one_source_keep_source_order_and_do_not_overlap",
    ),
    (
        "p4 model: a card names a sentence that is not there",
        P4_MODEL,
        "                if item.sentence >= len(self.sentences):\n",
        "                if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_card_names_published_sentences_in_source_order",
    ),
    (
        "p4 model: card items leave source order",
        P4_MODEL,
        "        if indices != sorted(set(indices)):\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_card_names_published_sentences_in_source_order",
    ),
    (
        "p4 model: a card has 0 or 3 items",
        P4_MODEL,
        "        if not 1 <= len(self.items) <= MAX_CARD:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_card_has_one_or_two_items",
    ),
    (
        "p4 model: any provenance version is read",
        P4_MODEL,
        "    if not _is_int(value) or value != PROVENANCE_VERSION:\n",
        "    if not _is_int(value):  # mutant\n",
        P4_MODEL_TEST,
        "test_legacy_provenance_refuses_any_other_wording",
    ),
    (
        "p4 model: lane L claims another ai_system",
        P4_MODEL,
        "        if self.ai_system != LEGACY_AI_SYSTEM:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_legacy_provenance_refuses_any_other_wording",
    ),
    (
        "p4 model: lane L claims another basis",
        P4_MODEL,
        "        if self.basis != LEGACY_BASIS:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_legacy_provenance_refuses_any_other_wording",
    ),
    (
        "p4 model: lane L is read as the full shape",
        P4_MODEL,
        '    if data.get("lane") == Lane.L.value:\n',
        "    if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_provenance_from_dict_reads_both_shapes_by_lane",
    ),
    (
        "p4 model: an assembly carries legacy provenance",
        P4_MODEL,
        "        if not isinstance(self.provenance, Provenance):\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_an_assembly_carries_a_full_provenance",
    ),
    (
        "p4 model: a selection without DESC",
        P4_MODEL,
        "        if not self.desc:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_selection_refusal_is_named",
    ),
    (
        "p4 model: a selection with 9 DESC lines",
        P4_MODEL,
        "        if len(self.desc) > MAX_DESC:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_selection_refusal_is_named",
    ),
    (
        "p4 model: the DESC bound is not 8",
        P4_MODEL,
        "MAX_DESC = 8\n",
        "MAX_DESC = 7  # mutant\n",
        P4_MODEL_TEST,
        "test_the_selector_bounds_are_the_contracts",
    ),
    (
        "p4 model: a selection without CARD",
        P4_MODEL,
        "        if not self.card:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_selection_refusal_is_named",
    ),
    (
        "p4 model: a selection with 3 CARD lines",
        P4_MODEL,
        "        if len(self.card) > MAX_CARD:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_selection_refusal_is_named",
    ),
    (
        "p4 model: a repeated sid in DESC or CARD",
        P4_MODEL,
        "            if len(set(sids)) != len(sids):\n",
        "            if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_selection_refusal_is_named",
    ),
    (
        "p4 model: a CARD sid outside DESC",
        P4_MODEL,
        "        if outside:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_selection_refusal_is_named",
    ),
    (
        "p4 model: ABSTAIN beside picks",
        P4_MODEL,
        "            if self.desc or self.card:\n",
        "            if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_selection_refusal_is_named",
    ),
    (
        "p4 model: ABSTAIN without a reason",
        P4_MODEL,
        "            if not self.abstain.strip():\n",
        "            if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_selection_refusal_is_named",
    ),
    (
        "p4 model: a span dropped twice in one line",
        P4_MODEL,
        "        if len(set(self.drop)) != len(self.drop):\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_span_dropped_twice_in_one_line_is_a_duplicate",
    ),
    (
        "p4 model: a pick names no numbered sentence",
        P4_MODEL,
        "        if not isinstance(self.sid, str) or not _SID.fullmatch(self.sid):\n",
        "        if not isinstance(self.sid, str):  # mutant\n",
        P4_MODEL_TEST,
        "test_a_pick_names_a_numbered_wikipedia_sentence",
    ),
    (
        "p4 model: R or D text is numbered into sentences",
        P4_MODEL,
        "        if kind not in SELECTABLE_KINDS:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_only_wikipedia_text_is_numbered_into_sentences",
    ),
    (
        "p4 model: a span id names another kind",
        P4_MODEL,
        "        if self.id[0] != self.kind.value:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_span_id_names_its_kind",
    ),
    (
        "p4 model: a span leaves its sentence",
        P4_MODEL,
        "            if span.start < self.start or span.end > self.end:\n",
        "            if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_span_outside_its_sentence_is_refused",
    ),
    (
        "p4 model: a span id is offered twice",
        P4_MODEL,
        "        if len({span.id for span in self.spans}) != len(self.spans):\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_span_id_is_offered_once_per_sentence",
    ),
    (
        "p4 model: a store id outside the layout",
        P4_MODEL,
        "    if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):\n",
        "    if not isinstance(source_id, str):  # mutant\n",
        P4_MODEL_TEST,
        "test_source_ids_follow_the_store_layout",
    ),
    (
        "p4 model: an unknown store part",
        P4_MODEL,
        "    if part not in suffix:\n",
        "    if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_source_ids_follow_the_store_layout",
    ),
    (
        "p4 model: a lane uses another kind of source",
        P4_MODEL,
        "        if not fits:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_each_lane_uses_its_own_kind_of_source",
    ),
    (
        "p4 model: lane L is assigned",
        P4_MODEL,
        "        if self.lane not in ASSIGNED_LANES:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_the_lanes_that_can_be_assigned",
    ),
    (
        "p4 model: a plan digest is not its text's",
        P4_MODEL,
        "            if value is not None and text_sha256(value) != digest:\n",
        "            if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_plan_site_digest_is_the_sha256_of_its_text",
    ),
    (
        "p4 model: a plan text and its digest disagree on null",
        P4_MODEL,
        "            if (value is None) != (digest is None):\n",
        "            if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_plan_site_digest_is_the_sha256_of_its_text",
    ),
    (
        "p4 model: plan raw_data and its digest disagree on null",
        P4_MODEL,
        "        if (self.raw_data is None) != (self.raw_data_sha256 is None):\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_plan_site_digest_is_the_sha256_of_its_text",
    ),
    (
        "p4 model: a plan flag listed twice",
        P4_MODEL,
        "        if len(set(map(str, flags))) != len(flags):\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_a_plan_site_flag_listed_twice_is_refused",
    ),
    (
        "p4 model: a card-only reason holds a site",
        P4_MODEL,
        "        if self.reason in CARD_ONLY_REASONS and self.scope is not HoldScope.CARD:\n",
        "        if False:  # mutant\n",
        P4_MODEL_TEST,
        "test_card_only_reasons_cannot_hold_a_site",
    ),
    (
        "p4 model: a hold without detail",
        P4_MODEL,
        '        _need_text(self.detail, f"hold {self.site_id}: detail")\n',
        "",
        P4_MODEL_TEST,
        "test_a_hold_names_its_reason",
    ),
    (
        "p4 model: a protected negation goes missing",
        P4_MODEL,
        '        "negations": ("not", "no", "never", "neither", "nor", "without"),\n',
        '        "negations": ("not", "never", "neither", "nor", "without"),  # mutant\n',
        P4_MODEL_TEST,
        "test_the_protected_tokens_are_the_design_list_verbatim",
    ),
    (
        "p4 model: a pronoun opener goes missing",
        P4_MODEL,
        '    "The former", "Here", "There",\n',
        '    "The former", "Here",  # mutant\n',
        P4_MODEL_TEST,
        "test_the_pronoun_openers_are_the_design_list_verbatim",
    ),
    (
        "p4 model: the provenance key loses its underscore",
        P4_MODEL,
        'PROVENANCE_KEY = "_description_provenance"\n',
        'PROVENANCE_KEY = "description_provenance"  # mutant\n',
        P4_MODEL_TEST,
        "test_the_raw_data_keys_are_the_ones_the_frontend_reads_and_skips",
    ),
    (
        "p4 model: a citation spells licence the other way",
        P4_MODEL,
        '            "license": self.license.value,\n',
        '            "licence": self.license.value,  # mutant\n',
        P4_MODEL_TEST,
        "test_a_citation_is_the_description_citation_shape_plus_license_without_claim",
    ),
    (
        "p4 model: provenance loses desc_sha256",
        P4_MODEL,
        '            "desc_sha256": self.desc_sha256,\n',
        "",
        P4_MODEL_TEST,
        "test_provenance_json_is_the_production_write_schema_exactly",
    ),
    (
        "p4 shim: importing phase4 leaves the repository root off the path",
        P4_INIT,
        "    sys.path.append(str(REPO))\n",
        "    pass  # mutant\n",
        P4_MODEL_TEST,
        "test_importing_phase4_puts_the_repository_root_on_the_path",
    ),
]
MUTATIONS += GAP_MUTATIONS
MUTATIONS += REVIEW_MUTATIONS
MUTATIONS += SPLIT_MUTATIONS
MUTATIONS += PILOT_FIX_MUTATIONS
MUTATIONS += REVIEW_FIX_MUTATIONS

#: The gallery audit's guards (2026-09-23, W5/W9/W10): liveness, the vision stage, the current
#: tiers, the label sets, the sealed rule table and C1 calibration. Every name starts with
#: "gallery:" so the list runs on its own: `mutation_sweep.py gallery:`.
GALLERY = "scripts/remediation/gallery_audit/"
LIVENESS_TEST = "tests/remediation/test_gallery_liveness.py"
VISION_TEST = "tests/remediation/test_gallery_vision.py"
CALIBRATE_TEST = "tests/remediation/test_gallery_calibrate.py"
GALLERY_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "gallery: a title the answer does not mention is skipped",
        GALLERY + "liveness.py",
        "        if page is None:\n            raise LivenessError(\n",
        "        if page is None:  # mutant\n            continue\n            raise LivenessError(\n",
        LIVENESS_TEST,
        "test_a_title_the_answer_does_not_mention_stops_the_sweep",
    ),
    (
        "gallery: a truncated log reads as an unexplained file",
        GALLERY + "liveness.py",
        '        if "continue" in answer.body:\n',
        "        if False:  # mutant\n",
        LIVENESS_TEST,
        "test_a_truncated_log_without_a_deletion_or_move_is_refused",
    ),
    (
        "gallery: a cached maxlag answer is read again",
        GALLERY + "liveness.py",
        "ns=ns, force=attempt > 0)",
        "ns=ns, force=False)  # mutant",
        LIVENESS_TEST,
        "test_a_maxlag_answer_is_asked_again_past_the_cache_and_a_persistent_one_stops",
    ),
    (
        "gallery: a refused long URI is not split",
        GALLERY + "liveness.py",
        '        if not str(exc).endswith(": HTTP 414") or len(titles) == 1:\n',
        "        if True:  # mutant\n",
        LIVENESS_TEST,
        "test_a_refused_long_uri_is_asked_again_in_halves",
    ),
    (
        "gallery: the sweep outlives its deadline",
        GALLERY + "liveness.py",
        "        if self._deadline is not None and now > self._deadline:\n",
        "        if False:  # mutant\n",
        LIVENESS_TEST,
        "test_the_pace_counts_from_the_start_of_a_request_and_the_deadline_stops_the_run",
    ),
    (
        "gallery: the pace counts from the end of a request",
        GALLERY + "liveness.py",
        "            pace.mark(started)\n",
        "            pace.mark(pace._clock())  # mutant\n",
        LIVENESS_TEST,
        "test_the_pace_counts_from_the_start_of_a_request_and_the_deadline_stops_the_run",
    ),
    (
        "gallery: every deletion reads as another deletion",
        GALLERY + "liveness.py",
        "DELETED_COPYVIO if COPYVIO_RE.search(",
        "DELETED_OTHER if COPYVIO_RE.search(",
        LIVENESS_TEST,
        "test_a_deletion_is_a_copyright_deletion_only_when_its_comment_says_so",
    ),
    (
        "gallery: the oldest deletion or move decides",
        GALLERY + "liveness.py",
        "    return max(relevant, key=",
        "    return min(relevant, key=",
        LIVENESS_TEST,
        "test_the_newest_deletion_or_move_decides_and_uploads_do_not",
    ),
    (
        "gallery: rows of other sources are referenced",
        GALLERY + "liveness.py",
        '        if str(row["site_id"]) not in curated:\n            continue\n',
        "",
        LIVENESS_TEST,
        "test_only_curated_rows_with_a_commons_identity_are_referenced",
    ),
    (
        "gallery: a string passes as other_site",
        GALLERY + "vision.py",
        '        if not isinstance(parsed.get("other_site"), bool):\n',
        '        if parsed.get("other_site") is None:  # mutant\n',
        VISION_TEST,
        "test_a_gallery_answer_that_is_not_exactly_a_verdict_is_no_verdict",
    ),
    (
        "gallery: a kind outside the six is accepted",
        GALLERY + "vision.py",
        "        if kind not in KINDS:\n",
        "        if kind is None:  # mutant\n",
        VISION_TEST,
        "test_a_gallery_answer_that_is_not_exactly_a_verdict_is_no_verdict",
    ),
    (
        "gallery: the case-collision tree is not searched",
        GALLERY + "vision.py",
        "        hit = pilot.locate(self.trees, site_id, filename)\n",
        "        hit = pilot.locate(self.trees[:1], site_id, filename)  # mutant\n",
        VISION_TEST,
        "test_the_case_collision_tree_is_searched_by_exact_name",
    ),
    (
        "gallery: an unreadable image goes to the model",
        GALLERY + "vision.py",
        "        except OSError as exc:  # PIL's UnidentifiedImageError is an OSError too\n",
        "        except ValueError as exc:  # mutant\n",
        VISION_TEST,
        "test_an_image_that_cannot_be_read_is_a_failed_line_and_costs_no_call",
    ),
    (
        "gallery: a failed judgement does not stop the run",
        GALLERY + "vision.py",
        "            )\n            stop.set()\n\n    with ThreadPoolExecutor",
        "            )\n\n    with ThreadPoolExecutor",
        VISION_TEST,
        "test_a_failed_judgement_stops_new_calls_and_exits_3",
    ),
    (
        "gallery: the budget is never checked",
        GALLERY + "vision.py",
        "                if ledger.spent_usd >= budget_usd:\n",
        "                if False:  # mutant\n",
        VISION_TEST,
        "test_the_budget_is_read_from_the_ledger_and_stops_before_the_next_call",
    ),
    (
        "gallery: a failed line's cost is not spent",
        GALLERY + "vision.py",
        '        self._spent = sum(float(entry.line["cost_usd"]) for entry in self.lines)\n',
        '        self._spent = sum(float(entry.line["cost_usd"]) for entry in self.lines if entry.ok)\n',
        VISION_TEST,
        "test_the_budget_is_read_from_the_ledger_and_stops_before_the_next_call",
    ),
    (
        "gallery: a torn ledger line is skipped",
        GALLERY + "vision.py",
        '                raise VisionError(f"{path}:{lineno}: a damaged ledger line ({exc})") from exc\n',
        "                continue  # mutant\n",
        VISION_TEST,
        "test_a_verdict_id_is_the_sha256_of_its_line_and_a_torn_line_stops_the_reader",
    ),
    (
        "gallery: a verdict under another prompt counts",
        GALLERY + "vision.py",
        '        if line["prompt_sha256"] != prompt_sha256(template):\n',
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_verdict_counts_only_under_the_frozen_prompt_and_the_pilot_model",
    ),
    (
        "gallery: more workers without a clean ramp probe",
        GALLERY + "vision.py",
        "    if failed or p90 >= RAMP_P90_MS:\n",
        "    if False:  # mutant\n",
        VISION_TEST,
        "test_more_than_four_workers_need_a_clean_ramp_probe",
    ),
    (
        "gallery: the frozen gallery question drifts",
        GALLERY + "vision.py",
        "including a neighbouring monument, a nearby modern park",
        "including a related monument, a nearby modern park",
        VISION_TEST,
        "test_the_frozen_prompts_hash_to_their_pins",
    ),
    (
        "gallery: an unmoved row's tier is not proven",
        GALLERY + "worklist.py",
        "                if tier != census:\n",
        "                if False:  # mutant\n",
        VISION_TEST,
        "test_retiering_is_proven_against_the_census_for_every_unmoved_row",
    ),
    (
        "gallery: a hero move is applied without its old value",
        GALLERY + "worklist.py",
        '                if bool(row.get("is_hero")) != old:\n',
        "                if False:  # mutant\n",
        VISION_TEST,
        "test_a_hero_move_that_does_not_fit_the_snapshot_or_the_repair_is_refused",
    ),
    (
        "gallery: a NULL sort_order is served first",
        GALLERY + "worklist.py",
        '            r.get("sort_order") is None,\n',
        '            r.get("sort_order") is not None,  # mutant\n',
        VISION_TEST,
        "test_the_served_image_is_the_pages_own_order_with_nulls_last",
    ),
    (
        "gallery: the grey probes are drawn in id order",
        GALLERY + "worklist.py",
        'key=lambda r: probe_rank(seed, int(r["id"])),',
        'key=lambda r: int(r["id"]),  # mutant',
        VISION_TEST,
        "test_the_stage_builders_pick_what_the_design_names",
    ),
    (
        "gallery: an escalation leaves tier D out",
        GALLERY + "worklist.py",
        "        for row in state.live_rows(sid)\n    ]\n\n\ndef strict_jobs(",
        '        for row in state.live_rows(sid)\n        if row["_tier"] != CLEAR  # mutant\n    ]\n\n\ndef strict_jobs(',
        VISION_TEST,
        "test_the_stage_builders_pick_what_the_design_names",
    ),
    (
        "gallery: a collection span need not be in its entry",
        GALLERY + "labels.py",
        "                    if member.span not in entry:\n",
        "                    if False:  # mutant\n",
        VISION_TEST,
        "test_derive_resolves_single_entries_and_refuses_a_span_its_entry_does_not_hold",
    ),
    (
        "gallery: the checked population is not proven",
        GALLERY + "labels.py",
        '        if len(rows) != block["checked"]:\n',
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_derive_refuses_a_checked_count_that_is_not_the_live_rows",
    ),
    (
        "gallery: a manual row can be excluded",
        GALLERY + "decide.py",
        '            if row.get("is_excluded") or row.get("source_type") == MANUAL:\n',
        '            if row.get("is_excluded"):  # mutant\n',
        VISION_TEST,
        "test_exclusions_spare_manual_rows_and_artifacts_and_take_the_heros_flag_with_them",
    ),
    (
        "gallery: a trigger calibration did not admit excludes",
        GALLERY + "decide.py",
        "                if fired and admission.admits(rule_id):\n",
        "                if fired:  # mutant\n",
        VISION_TEST,
        "test_nothing_is_written_that_calibration_did_not_admit",
    ),
    (
        "gallery: a recorded image_kind is overwritten",
        GALLERY + "decide.py",
        "                if current is None:\n",
        "                if True:  # mutant\n",
        VISION_TEST,
        "test_kind_writes_need_admission_and_never_overwrite_a_recorded_kind",
    ),
    (
        "gallery: an excluded hero keeps its flag",
        GALLERY + "decide.py",
        '                    excluded_now.add(image_id)\n                    if row.get("is_hero"):\n',
        "                    excluded_now.add(image_id)\n                    if False:  # mutant\n",
        VISION_TEST,
        "test_exclusions_spare_manual_rows_and_artifacts_and_take_the_heros_flag_with_them",
    ),
    (
        "gallery: a hero needs no author under an attribution licence",
        GALLERY + "decide.py",
        '    return bool(licence) and bool((row.get("author") or "").strip())\n',
        "    return True  # mutant\n",
        VISION_TEST,
        "test_the_hero_moves_to_the_best_strict_confirmed_candidate",
    ),
    (
        "gallery: a hero derivative under 900 px high qualifies",
        GALLERY + "decide.py",
        "    if projected is None or not _hero_ready(*projected):\n",
        "    if projected is None:  # mutant\n",
        VISION_TEST,
        "test_the_hero_moves_to_the_best_strict_confirmed_candidate",
    ),
    (
        "gallery: a served image that is no site photo passes",
        GALLERY + "decide.py",
        '    if first.verdict["kind"] != "site_photo" or first.verdict["other_site"] is True:\n',
        "    if False:  # mutant\n",
        VISION_TEST,
        "test_the_served_image_state_names_every_case",
    ),
    (
        "gallery: L1 leaves the flag on a deleted hero",
        GALLERY + "decide.py",
        '                        evidence,\n                    )\n                )\n                if row.get("is_hero"):\n',
        "                        evidence,\n                    )\n                )\n                if False:  # mutant\n",
        VISION_TEST,
        "test_a_deleted_file_is_excluded_and_its_hero_replaced_by_the_repairs_own_rule",
    ),
    (
        "gallery: L2 takes a URL a sibling row holds",
        GALLERY + "decide.py",
        "                if clash:\n",
        "                if False:  # mutant\n",
        VISION_TEST,
        "test_a_moved_file_gets_both_urls_of_its_live_target_unless_a_sibling_holds_them",
    ),
    (
        "gallery: a plan with two heroes passes",
        GALLERY + "decide.py",
        "        if len(heroes) > 1:\n",
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_plan_that_breaks_the_hero_invariants_is_refused",
    ),
    (
        "gallery: the rule table drifts",
        GALLERY + "decide.py",
        "only if C1 admitted X1; never on a manual row",
        "only if C1 admitted X1",
        VISION_TEST,
        "test_the_rule_table_is_sealed",
    ),
    (
        "gallery: thresholds may be sealed after the first call",
        GALLERY + "calibrate.py",
        '    if (run_dir / LEDGER_FILE).exists():\n        raise CalibrationError(\n            f"{run_dir / LEDGER_FILE} exists - thresholds are sealed',
        '    if False:  # mutant\n        raise CalibrationError(\n            f"{run_dir / LEDGER_FILE} exists - thresholds are sealed',
        CALIBRATE_TEST,
        "test_the_seal_is_written_and_logged_before_any_verdict_exists",
    ),
    (
        "gallery: thresholds changed after the seal pass",
        GALLERY + "calibrate.py",
        '    if digest != entries[0]["thresholds_sha256"]:\n',
        "    if False:  # mutant\n",
        CALIBRATE_TEST,
        "test_thresholds_changed_after_the_seal_are_refused",
    ),
    (
        "gallery: a verdict judged before the seal counts",
        GALLERY + "calibrate.py",
        "    if early:\n",
        "    if False:  # mutant\n",
        CALIBRATE_TEST,
        "test_a_verdict_judged_before_the_seal_is_refused",
    ),
    (
        "gallery: a job without a verdict still admits",
        GALLERY + "calibrate.py",
        "    if missing:\n",
        "    if False:  # mutant\n",
        CALIBRATE_TEST,
        "test_a_job_without_a_verdict_admits_nothing",
    ),
    (
        "gallery: X1 is admitted without the gold rows",
        GALLERY + "calibrate.py",
        "        and gold_foreign_flagged == len(gold_foreign)\n",
        "",
        CALIBRATE_TEST,
        "test_one_unflagged_gold_foreign_row_drops_x1",
    ),
    (
        "gallery: the strict pass is judged without its eye labels",
        GALLERY + "calibrate.py",
        '    if len(labelled_a) < t_strict["tiles"]:\n',
        "    if False:  # mutant\n",
        CALIBRATE_TEST,
        "test_the_strict_pass_is_not_admitted_without_eye_labels",
    ),
    (
        "gallery: a verdict about other bytes passes the evidence check",
        GALLERY + "decide.py",
        '        if digests[path] != line["image_sha256"]:\n',
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_planned_row_must_cite_a_ledger_verdict_about_todays_bytes",
    ),
    (
        "gallery: a row citing no ledger verdict passes the evidence check",
        GALLERY + "decide.py",
        "        if entry is None:\n            problems.append(",
        "        if entry is None:\n            continue  # mutant\n            problems.append(",
        VISION_TEST,
        "test_a_planned_row_must_cite_a_ledger_verdict_about_todays_bytes",
    ),
]
MUTATIONS += GALLERY_MUTATIONS

#: The gallery guards the 2026-09-23 review found unproven, and the guards its fixes added (the
#: liveness pre-flight, the applied-plan overlay, the liveness gate, the sealed admission, explicit
#: eye labels, the loose matcher). Same "gallery:" prefix, so `mutation_sweep.py gallery:` runs
#: them with the others.
GALLERY_REVIEW_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "gallery: the recheck does not ask whether a file is back",
        GALLERY + "liveness.py",
        '            if answered[title]["class"] is not None:\n',
        "            if False:  # mutant\n",
        LIVENESS_TEST,
        "test_recheck_asks_imageinfo_again_even_when_the_log_says_nothing_new",
    ),
    (
        "gallery: the recheck reads only deletions and moves",
        GALLERY + "liveness.py",
        '                if (e.get("type"), e.get("action")) in RECHECK_LOG\n',
        '                if (e.get("type"), e.get("action")) in RELEVANT_LOG  # mutant\n',
        LIVENESS_TEST,
        "test_recheck_names_an_upload_newer_than_the_deletion_while_the_file_is_still_missing",
    ),
    (
        "gallery: the recheck names entries older than the stored one",
        GALLERY + "liveness.py",
        "                and log_order(e) > log_order(stored)\n",
        "",
        LIVENESS_TEST,
        "test_recheck_names_a_vanished_entry_a_newer_entry_and_a_dead_move_target",
    ),
    (
        "gallery: the recheck command exits 0 on a problem",
        GALLERY + "liveness.py",
        "    return 0 if not problems else 4\n",
        "    return 0  # mutant\n",
        LIVENESS_TEST,
        "test_the_recheck_command_exits_4_on_a_problem_and_0_on_none",
    ),
    (
        "gallery: a non-200 Commons answer is read",
        GALLERY + "liveness.py",
        '        if payload.get("status") != 200:\n',
        "        if False:  # mutant\n",
        LIVENESS_TEST,
        "test_an_answer_that_is_not_a_query_answer_stops_the_sweep",
    ),
    (
        "gallery: a Commons answer that is not JSON escapes as a crash",
        GALLERY + "liveness.py",
        "        try:\n            body = json.loads(text)\n        except json.JSONDecodeError as exc:\n"
        "            raise LivenessError(\n"
        '                f"{COMMONS_API} answered something that is not JSON: {exc}"\n'
        "            ) from exc\n",
        "        body = json.loads(text)  # mutant\n",
        LIVENESS_TEST,
        "test_an_answer_that_is_not_a_query_answer_stops_the_sweep",
    ),
    (
        "gallery: a Commons answer that is no object is read",
        GALLERY + "liveness.py",
        "        if not isinstance(body, dict):\n",
        "        if False:  # mutant\n",
        LIVENESS_TEST,
        "test_an_answer_that_is_not_a_query_answer_stops_the_sweep",
    ),
    (
        "gallery: a Commons answer without query is read",
        GALLERY + "liveness.py",
        '            if "query" not in body:\n',
        "            if False:  # mutant\n",
        LIVENESS_TEST,
        "test_an_answer_that_is_not_a_query_answer_stops_the_sweep",
    ),
    (
        "gallery: a line without a known class is stored",
        GALLERY + "liveness.py",
        "    if unclassified:\n",
        "    if False:  # mutant\n",
        LIVENESS_TEST,
        "test_a_line_left_without_a_known_class_stops_the_sweep",
    ),
    (
        "gallery: a file without a pixel size reads as live",
        GALLERY + "liveness.py",
        '            if not info or not info.get("width") or not info.get("height"):\n',
        "            if not info:  # mutant\n",
        LIVENESS_TEST,
        "test_a_file_without_a_pixel_size_is_a_page_without_file",
    ),
    (
        "gallery: a missing move target is stored without a class",
        GALLERY + "liveness.py",
        '            if summary["class"] is None:\n                summary["class"] = "missing"\n',
        "",
        LIVENESS_TEST,
        "test_a_move_target_that_is_missing_too_is_stored_as_missing",
    ),
    (
        "gallery: a hand-edited plan record is folded in",
        GALLERY + "planned.py",
        "        if not isinstance(record, dict) or set(record) != PLANNED_KEYS:\n",
        "        if not isinstance(record, dict):  # mutant\n",
        VISION_TEST,
        "test_a_plan_round_trips_and_a_record_that_is_not_a_planned_row_is_refused",
    ),
    (
        "gallery: an empty plan is folded in",
        GALLERY + "planned.py",
        '    if not out:\n        raise PlanError(f"{path} holds no planned row")\n',
        "",
        VISION_TEST,
        "test_a_plan_round_trips_and_a_record_that_is_not_a_planned_row_is_refused",
    ),
    (
        "gallery: a kinds record without its old value is read",
        GALLERY + "planned.py",
        "        if not isinstance(record, dict) or not KINDS_RECORD_KEYS <= set(record):\n",
        "        if not isinstance(record, dict):  # mutant\n",
        VISION_TEST,
        "test_a_kinds_plan_is_read_as_image_kind_rows_only",
    ),
    (
        "gallery: a kinds plan may write another column",
        GALLERY + "planned.py",
        '        if record["table"] != "wiki_images" or record["column"] != "image_kind":\n',
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_kinds_plan_is_read_as_image_kind_rows_only",
    ),
    (
        "gallery: an applied plan may move any column",
        GALLERY + "worklist.py",
        '            if change.table != "wiki_images" or change.column not in APPLIED_COLUMNS:\n',
        "            if False:  # mutant\n",
        VISION_TEST,
        "test_an_applied_plan_is_folded_only_onto_the_old_values_it_names",
    ),
    (
        "gallery: an applied row of another site is folded in",
        GALLERY + "worklist.py",
        "            if hit is None or hit[0] != change.site_id:\n",
        "            if hit is None:  # mutant\n",
        VISION_TEST,
        "test_an_applied_plan_is_folded_only_onto_the_old_values_it_names",
    ),
    (
        "gallery: an applied plan is folded onto any old value",
        GALLERY + "worklist.py",
        "            if current != change.old:\n",
        "            if False:  # mutant\n",
        VISION_TEST,
        "test_an_applied_plan_is_folded_only_onto_the_old_values_it_names",
    ),
    (
        "gallery: a row an applied plan moved keeps its old tier",
        GALLERY + "worklist.py",
        "            if change.column in TIER_COLUMNS:\n                retiered.add(change.key)\n",
        "",
        VISION_TEST,
        "test_an_applied_plan_moves_the_state_and_retiers_the_rows_it_moved",
    ),
    (
        "gallery: a state behind the liveness write passes the gate",
        GALLERY + "worklist.py",
        "            if cls in (liveness.DELETED_COPYVIO, liveness.DELETED_OTHER) and not row.get(\n"
        '                "is_excluded"\n'
        "            ):\n",
        "            if False:  # mutant\n",
        VISION_TEST,
        "test_a_state_that_has_not_folded_the_liveness_write_in_is_refused",
    ),
    (
        "gallery: a row L2 repointed stays blocked",
        GALLERY + "worklist.py",
        '                and row.get("original_url") == target.get("url")\n'
        "            ):\n                continue\n",
        '                and row.get("original_url") == target.get("url")\n'
        "            ):\n                pass  # mutant\n",
        VISION_TEST,
        "test_a_state_that_has_not_folded_the_liveness_write_in_is_refused",
    ),
    (
        "gallery: a file that only redirects is blocked",
        GALLERY + "worklist.py",
        "        if cls in (liveness.LIVE, liveness.MOVED_WITH_REDIRECT):\n",
        "        if cls == liveness.LIVE:  # mutant\n",
        VISION_TEST,
        "test_a_state_that_has_not_folded_the_liveness_write_in_is_refused",
    ),
    (
        "gallery: a liveness line about a row the state lacks is read",
        GALLERY + "worklist.py",
        "    if row is None:\n        raise WorklistError(\n",
        "    if False:  # mutant\n        raise WorklistError(\n",
        VISION_TEST,
        "test_a_state_that_has_not_folded_the_liveness_write_in_is_refused",
    ),
    (
        "gallery: the job builder skips the liveness gate",
        GALLERY + "worklist.py",
        "    liveness_blocked(\n"
        '        liveness.load_store(Path(args.liveness_store) / "NOT_LIVE.jsonl"), state.by_site\n'
        "    )\n",
        "",
        VISION_TEST,
        "test_the_job_builder_refuses_a_state_behind_the_liveness_write",
    ),
    (
        "gallery: decide plans vision without the liveness gate",
        GALLERY + "decide.py",
        "        blocked = worklist.liveness_blocked(\n"
        '            liveness.load_store(Path(args.liveness_store) / "NOT_LIVE.jsonl"), state.by_site\n'
        "        )\n",
        "        blocked: dict[int, str] = {}  # mutant\n",
        VISION_TEST,
        "test_decide_refuses_to_plan_vision_on_a_state_behind_the_liveness_write",
    ),
    (
        "gallery: a vision rule plans on a row whose file is not live",
        GALLERY + "decide.py",
        "            if image_id in blocked:\n",
        "            if False:  # mutant\n",
        VISION_TEST,
        "test_no_vision_rule_plans_on_a_row_whose_file_is_not_live",
    ),
    (
        "gallery: H1 promotes a row whose file is not live",
        GALLERY + "decide.py",
        '        and int(row["id"]) not in excluded_now\n        and int(row["id"]) not in blocked\n',
        '        and int(row["id"]) not in excluded_now\n',
        VISION_TEST,
        "test_h1_never_promotes_a_row_whose_file_is_not_live",
    ),
    (
        "gallery: H1 demotes a hero whose file is not live",
        GALLERY + "decide.py",
        '    if any(int(row["id"]) in blocked for row in current_hero):\n',
        "    if False:  # mutant\n",
        VISION_TEST,
        "test_h1_leaves_a_hero_whose_file_is_not_live_to_the_liveness_lane",
    ),
    (
        "gallery: L1 hands the hero to another dead file",
        GALLERY + "decide.py",
        '                set(ids) | {r.key for r in planned if r.column == "is_excluded"} | not_live,\n',
        '                set(ids) | {r.key for r in planned if r.column == "is_excluded"},  # mutant\n',
        VISION_TEST,
        "test_l1_never_hands_the_hero_to_another_file_that_is_not_live",
    ),
    (
        "gallery: a hand-edited admission is trusted",
        GALLERY + "calibrate.py",
        "    if admission_text(again) != text:\n",
        "    if False:  # mutant\n",
        CALIBRATE_TEST,
        "test_a_hand_edited_admission_switches_nothing_on",
    ),
    (
        "gallery: decide reads an admission without re-deriving it",
        GALLERY + "decide.py",
        "    record, digest = calibrate.verify_admission(calibration_dir)\n",
        '    text = (calibration_dir / "ADMISSION.json").read_text(encoding="utf-8")  # mutant\n'
        "    record, digest = json.loads(text), hashlib.sha256(text.encode()).hexdigest()\n",
        CALIBRATE_TEST,
        "test_a_hand_edited_admission_switches_nothing_on",
    ),
    (
        "gallery: an admission does not name its ledger",
        GALLERY + "calibrate.py",
        '        "ledger_sha256": _sha(ledger_path.read_text(encoding="utf-8")),\n',
        "",
        CALIBRATE_TEST,
        "test_an_admission_measured_on_another_ledger_is_refused",
    ),
    (
        "gallery: an admission does not name its eye labels",
        GALLERY + "calibrate.py",
        '        "eye_labels_sha256": eye_sha,\n',
        "",
        CALIBRATE_TEST,
        "test_an_admission_measured_on_other_eye_labels_is_refused",
    ),
    (
        "gallery: an admission whose T0 failed reaches decide",
        GALLERY + "calibrate.py",
        '    if again["metrics"]["T0"]["pass"] is not True:\n',
        "    if False:  # mutant\n",
        CALIBRATE_TEST,
        "test_an_admission_whose_t0_failed_is_refused_to_decide",
    ),
    (
        "gallery: a missing eye-label file reads as no eye labels",
        GALLERY + "calibrate.py",
        "        if not eye_path.is_file():\n"
        "            raise CalibrationError(\n"
        '                f"{eye_path} does not exist - name the eye labels W8 wrote, or --no-eye-labels"\n'
        "            )\n"
        "        eye = labels.load_eye_labels(eye_path, tiles)\n"
        '        eye_sha = _sha(eye_path.read_text(encoding="utf-8"))\n',
        "        if eye_path.is_file():  # mutant: the old silent fallback\n"
        "            eye = labels.load_eye_labels(eye_path, tiles)\n"
        '            eye_sha = _sha(eye_path.read_text(encoding="utf-8"))\n',
        CALIBRATE_TEST,
        "test_evaluate_names_its_eye_labels_or_says_it_has_none",
    ),
    (
        "gallery: eye labels outside the repository are recorded",
        GALLERY + "calibrate.py",
        "        return path.resolve().relative_to(ROOT).as_posix()\n",
        "        return path.resolve().as_posix()  # mutant\n",
        CALIBRATE_TEST,
        "test_evaluate_names_its_eye_labels_or_says_it_has_none",
    ),
    (
        "gallery: evaluate runs without naming its eye labels",
        GALLERY + "calibrate.py",
        "            eye = cmd.add_mutually_exclusive_group(required=True)\n",
        "            eye = cmd.add_mutually_exclusive_group(required=False)  # mutant\n",
        CALIBRATE_TEST,
        "test_evaluate_names_its_eye_labels_or_says_it_has_none",
    ),
    (
        "gallery: evaluate runs without a ledger",
        GALLERY + "calibrate.py",
        "    if not ledger_path.is_file():\n"
        '        raise CalibrationError(f"{ledger_path} does not exist - run the C1 vision run first")\n',
        "",
        CALIBRATE_TEST,
        "test_evaluate_and_its_verification_need_their_files",
    ),
    (
        "gallery: an admission is verified without its file",
        GALLERY + "calibrate.py",
        "    if not path.is_file():\n"
        '        raise CalibrationError(f"{path} does not exist - run `calibrate.py evaluate` first")\n',
        "",
        CALIBRATE_TEST,
        "test_evaluate_and_its_verification_need_their_files",
    ),
    (
        "gallery: a job line with other keys is read",
        GALLERY + "vision.py",
        "        if set(data) != fields:\n",
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_job_line_with_other_keys_or_an_unknown_pass_is_no_job",
    ),
    (
        "gallery: a job with an unknown pass is read",
        GALLERY + "vision.py",
        '        if data["pass"] not in PASSES:\n',
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_job_line_with_other_keys_or_an_unknown_pass_is_no_job",
    ),
    (
        "gallery: a ledger line without status or cost is read",
        GALLERY + "vision.py",
        '            if line.get("status") not in ("ok", "failed") or "cost_usd" not in line:\n',
        "            if False:  # mutant\n",
        VISION_TEST,
        "test_a_ledger_line_that_is_no_verdict_line_stops_the_reader",
    ),
    (
        "gallery: a subject that is no string passes",
        GALLERY + "vision.py",
        '        for key in ("other_place", "subject"):\n',
        '        for key in ("other_place",):  # mutant\n',
        VISION_TEST,
        "test_a_gallery_answer_that_is_not_exactly_a_verdict_is_no_verdict",
    ),
    (
        "gallery: a structure that is no string passes",
        GALLERY + "vision.py",
        '    if not isinstance(parsed.get("structure"), str):\n',
        "    if False:  # mutant\n",
        VISION_TEST,
        "test_a_hero_answer_needs_real_booleans",
    ),
    (
        "gallery: a crashed judgement ends the run with exit 0",
        GALLERY + "vision.py",
        "    if crashes:\n        raise crashes[0]\n",
        "",
        VISION_TEST,
        "test_a_judgement_that_crashes_is_raised_not_swallowed",
    ),
    (
        "gallery: the dry run exits 0 with images missing",
        GALLERY + "vision.py",
        "        return EXIT_NO_VERDICT if missing else EXIT_OK\n",
        "        return EXIT_OK  # mutant\n",
        VISION_TEST,
        "test_the_dry_run_exits_3_when_an_image_is_missing",
    ),
    (
        "gallery: a plan row outside the rule table passes",
        GALLERY + "decide.py",
        "        if row.rule not in RULES:\n",
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_plan_row_without_a_change_or_outside_the_table_is_refused",
    ),
    (
        "gallery: a plan row without a change passes",
        GALLERY + "decide.py",
        "        if row.old == row.new:\n",
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_plan_row_without_a_change_or_outside_the_table_is_refused",
    ),
    (
        "gallery: a failed verdict passes the evidence check",
        GALLERY + "decide.py",
        '        if not entry.ok or line["model"] != vision.MODEL:\n',
        '        if line["model"] != vision.MODEL:  # mutant\n',
        VISION_TEST,
        "test_a_cited_verdict_must_be_an_ok_verdict_of_the_frozen_question",
    ),
    (
        "gallery: a foreign model's verdict passes the evidence check",
        GALLERY + "decide.py",
        '        if not entry.ok or line["model"] != vision.MODEL:\n',
        "        if not entry.ok:  # mutant\n",
        VISION_TEST,
        "test_a_cited_verdict_must_be_an_ok_verdict_of_the_frozen_question",
    ),
    (
        "gallery: a verdict of another prompt passes the evidence check",
        GALLERY + "decide.py",
        '        if line["prompt_sha256"] != vision.prompt_sha256(templates[line["prompt_id"]]):\n',
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_a_cited_verdict_must_be_an_ok_verdict_of_the_frozen_question",
    ),
    (
        "gallery: evidence that does not repeat its verdict passes",
        GALLERY + "decide.py",
        '        if (row.evidence.get("image_sha256"), row.evidence.get("prompt_sha256")) != (\n',
        '        if False and (row.evidence.get("image_sha256"), row.evidence.get("prompt_sha256")) != (  # mutant\n',
        VISION_TEST,
        "test_a_planned_row_must_repeat_the_hashes_of_the_verdict_it_cites",
    ),
    (
        "gallery: an excluded row is excluded again",
        GALLERY + "decide.py",
        '            if row.get("is_excluded") or row.get("source_type") == MANUAL:\n',
        '            if row.get("source_type") == MANUAL:  # mutant\n',
        VISION_TEST,
        "test_an_excluded_row_is_not_excluded_again",
    ),
    (
        "gallery: L1 excludes a row that is already excluded",
        GALLERY + "decide.py",
        '                if row.get("is_excluded"):\n                    continue\n'
        '                evidence = _liveness_evidence(line, "L1")\n',
        '                evidence = _liveness_evidence(line, "L1")\n',
        VISION_TEST,
        "test_l1_leaves_a_row_that_is_already_excluded_alone",
    ),
    (
        "gallery: L2 repoints to a target that is not live",
        GALLERY + "decide.py",
        '                if target.get("class") != liveness.LIVE or not target.get("url"):\n',
        '                if not target.get("url"):  # mutant\n',
        VISION_TEST,
        "test_a_moved_file_gets_both_urls_of_its_live_target_unless_a_sibling_holds_them",
    ),
    (
        "gallery: H1 promotes a row outside the accepted tiers",
        GALLERY + "decide.py",
        '    if row.get("_tier") not in TIERS_ACCEPTED:\n'
        "        return f\"tier-{row.get('_tier')}\"\n",
        "",
        VISION_TEST,
        "test_h1_never_promotes_a_row_outside_the_accepted_tiers",
    ),
    (
        "gallery: H1 runs without the strict admission",
        GALLERY + "decide.py",
        "        if admission.strict:\n",
        "        if True:  # mutant\n",
        VISION_TEST,
        "test_no_hero_moves_unless_calibration_admitted_the_strict_pass",
    ),
    (
        "gallery: a photo placed elsewhere counts as strict-confirmed",
        GALLERY + "decide.py",
        '        and first.verdict["kind"] == "site_photo"\n'
        '        and first.verdict["other_site"] is False\n'
        "        and second is not None\n",
        '        and first.verdict["kind"] == "site_photo"\n        and second is not None\n',
        VISION_TEST,
        "test_h1_never_promotes_a_photo_the_first_pass_placed_elsewhere",
    ),
    (
        "gallery: a labelled image may appear twice",
        GALLERY + "labels.py",
        '        if line["image_id"] in seen:\n',
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_the_labelled_set_is_refused_with_an_unknown_class_or_an_image_twice",
    ),
    (
        "gallery: a labelled row may carry an unknown class",
        GALLERY + "labels.py",
        "        if labels - set(LABEL_CLASSES):\n",
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_the_labelled_set_is_refused_with_an_unknown_class_or_an_image_twice",
    ),
    (
        "gallery: an image may be labelled twice by eye",
        GALLERY + "labels.py",
        "        if image_id in out:\n"
        '            raise LabelError(f"{path}:{lineno}: image {image_id} labelled twice")\n',
        "",
        VISION_TEST,
        "test_an_image_labelled_twice_by_eye_is_refused",
    ),
    (
        "gallery: a pilot record without a kind is read",
        GALLERY + "labels.py",
        '        if record["kind"] not in vision.KINDS:\n',
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_the_pilot_tiles_need_a_kind_and_a_verdict_each_and_no_image_twice",
    ),
    (
        "gallery: a sampled image without a pilot verdict is read",
        GALLERY + "labels.py",
        "        if image_id not in kinds:\n",
        "        if False:  # mutant\n",
        VISION_TEST,
        "test_the_pilot_tiles_need_a_kind_and_a_verdict_each_and_no_image_twice",
    ),
    (
        "gallery: the pilot sample may hold an image twice",
        GALLERY + "labels.py",
        "    if len({t.image_id for t in tiles}) != len(tiles):\n",
        "    if False:  # mutant\n",
        VISION_TEST,
        "test_the_pilot_tiles_need_a_kind_and_a_verdict_each_and_no_image_twice",
    ),
    (
        "gallery: derive accepts an unknown label class",
        GALLERY + "labels.py",
        "            if cls not in LABEL_CLASSES:\n",
        "            if False:  # mutant\n",
        VISION_TEST,
        "test_derive_refuses_an_unknown_class_and_a_site_name_it_cannot_place",
    ),
    (
        "gallery: derive picks one of two sites of a name",
        GALLERY + "labels.py",
        "        if len(ids) != 1:\n",
        "        if not ids:  # mutant\n",
        VISION_TEST,
        "test_derive_refuses_an_unknown_class_and_a_site_name_it_cannot_place",
    ),
    (
        "gallery: a row without a title matches every hint",
        GALLERY + "labels.py",
        '        r for r in rows if any(k and (k.startswith(key) or key.startswith(k)) for k in r["_keys"])\n',
        '        r for r in rows if any(k.startswith(key) or key.startswith(k) for k in r["_keys"])\n',
        VISION_TEST,
        "test_a_row_without_a_title_is_no_wildcard_for_the_loose_match",
    ),
    (
        "gallery: an empty hero plan is read",
        GALLERY + "worklist.py",
        '    if not moves:\n        raise WorklistError(f"{path} holds no hero move")\n',
        "",
        VISION_TEST,
        "test_an_empty_hero_plan_and_a_row_without_a_census_tier_are_refused",
    ),
    (
        "gallery: a row without a census tier is tiered",
        GALLERY + "worklist.py",
        "            if census is None:\n",
        "            if False:  # mutant\n",
        VISION_TEST,
        "test_an_empty_hero_plan_and_a_row_without_a_census_tier_are_refused",
    ),
    (
        "gallery: a seal log with two hashes is read",
        GALLERY + "calibrate.py",
        '    if len({e["thresholds_sha256"] for e in entries}) != 1:\n',
        "    if False:  # mutant\n",
        CALIBRATE_TEST,
        "test_the_first_seal_counts_and_a_log_with_two_hashes_is_refused",
    ),
    (
        "gallery: the last seal's time counts",
        GALLERY + "calibrate.py",
        '    return json.loads(text), digest, str(entries[0]["sealed_at"])\n',
        '    return json.loads(text), digest, str(entries[-1]["sealed_at"])  # mutant\n',
        CALIBRATE_TEST,
        "test_the_first_seal_counts_and_a_log_with_two_hashes_is_refused",
    ),
    (
        "gallery: T-kind ignores the pilot agreement",
        GALLERY + "calibrate.py",
        '        and kind_agreement["k"] / kind_agreement["n"] >= t_kind["pilot_agreement_min"]\n',
        "",
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-kind ignores the non-photo precision",
        GALLERY + "calibrate.py",
        '        and non_photo_precision["k"] / non_photo_precision["n"] >= t_kind["non_photo_precision_min"]\n',
        "",
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-X1 ignores how many foreign rows resolve",
        GALLERY + "calibrate.py",
        '        len(foreign) >= t_x1["foreign_rows_resolved_min"]\n        and precision["n"]\n',
        '        precision["n"]  # mutant\n',
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-X1 ignores its precision",
        GALLERY + "calibrate.py",
        '        and precision["k"] / precision["n"] >= t_x1["precision_min"]\n',
        "",
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-X1 ignores its recall",
        GALLERY + "calibrate.py",
        '        and recall["k"] / recall["n"] >= t_x1["recall_min"]\n',
        "",
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-X1 ignores flagged gold-correct rows",
        GALLERY + "calibrate.py",
        '        and gold_correct_flagged <= t_x1["gold_correct_flagged_max"]\n',
        "",
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-X2/X3 ignore their minimum of flags",
        GALLERY + "calibrate.py",
        '            rate["n"] >= threshold["flags_min"]\n',
        '            rate["n"]  # mutant\n',
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-X2/X3 ignore their precision",
        GALLERY + "calibrate.py",
        '            and rate["k"] / rate["n"] >= threshold["precision_min"]\n',
        "",
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-strict ignores its precision",
        GALLERY + "calibrate.py",
        '            and s_precision["k"] / s_precision["n"] >= t_strict["precision_min"]\n',
        "",
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: T-strict ignores its recall",
        GALLERY + "calibrate.py",
        '            and s_recall["k"] / s_recall["n"] >= t_strict["recall_min"]\n',
        "",
        CALIBRATE_TEST,
        "test_each_threshold_leg_alone_refuses_its_trigger",
    ),
    (
        "gallery: L2 derives a page URL from a title that is no file title",
        GALLERY + "decide.py",
        '    if not file_title.startswith("File:"):\n',
        "    if False:  # mutant\n",
        VISION_TEST,
        "test_the_l2_page_url_is_the_projects_own_spelling_of_a_file_title",
    ),
]
MUTATIONS += GALLERY_REVIEW_MUTATIONS
MUTATIONS += BCASES_MUTATIONS
MUTATIONS += BCASES_REVIEW_MUTATIONS
MUTATIONS += PHASE4_MODEL_MUTATIONS

P4_FETCH_STAGE = "scripts/remediation/phase3/fetch_stage.py"
P4_LICENCES = "scripts/remediation/phase4/licences.py"
P4_GATE = "scripts/remediation/phase4/subject_gate.py"
P4_SOURCES = "scripts/remediation/phase4/sources_stage.py"
P4_ROUTES = "scripts/remediation/phase4/route_stage.py"
P4_PLAN = "scripts/remediation/phase4/plan4.py"
P4_CONTENT_FETCH = "pipeline/lyra/handlers/content_fetch.py"
P4_SOURCES_TEST = "tests/remediation/test_phase4_sources.py"
P4_ROUTES_TEST = "tests/remediation/test_phase4_routes.py"
P4_PLAN_TEST = "tests/remediation/test_phase4_plan.py"
#: Track A of Phases 4/5 (WB-A1, WB-A2, WB-A3): the fetch cap parameter, the licence registry
#: and deny list, the subject gate, S1, S1b, the plan and the public page-text function - every
#: guard with the one test that must fail when it is broken.
PHASE4_SOURCES_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "p4 fetch_stage: the reader ignores its cap parameter",
        P4_FETCH_STAGE,
        "        room = max_bytes - len(body)\n",
        "        room = MAX_PAGE_BYTES - len(body)  # mutant\n",
        FETCH_TEST,
        "test_a_1_mib_cap_stops_the_stream_at_1_mib_and_not_before",
    ),
    (
        "p4 fetch_stage: the exact-cap stop reads the 60 KB constant",
        P4_FETCH_STAGE,
        "        if len(body) == max_bytes:\n",
        "        if len(body) == MAX_PAGE_BYTES:  # mutant\n",
        FETCH_TEST,
        "test_a_body_of_exactly_60_kb_is_not_called_cut_under_a_1_mib_cap",
    ),
    (
        "p4 fetch_stage: HttpFetcher drops its cap before the reader",
        P4_FETCH_STAGE,
        "_read_capped(response.iter_bytes(), self._max_bytes)",
        "_read_capped(response.iter_bytes())",
        FETCH_TEST,
        "test_a_page_between_the_two_caps_is_whole_under_1_mib_and_cut_under_the_default",
    ),
    (
        "p4 fetch_stage: the default cap moves off 60 KB",
        P4_FETCH_STAGE,
        "        max_bytes: int = MAX_PAGE_BYTES,\n    ) -> None:\n",
        "        max_bytes: int = 1024 * 1024,  # mutant\n    ) -> None:\n",
        FETCH_TEST,
        "test_the_cap_parameter_defaults_to_the_60_kb_cap_on_the_client_and_the_reader",
    ),
    (
        "p4 fetch_stage: a cap that is no byte count is accepted",
        P4_FETCH_STAGE,
        "        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:\n",
        "        if False:  # mutant\n",
        FETCH_TEST,
        "test_a_cap_that_is_not_a_positive_byte_count_is_refused",
    ),
    (
        "p4 licences: a mirror host is not denied",
        P4_LICENCES,
        '    if any(label in MIRROR_NAMES for label in host.split(".")):\n',
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_wikipedia_mirrors_are_counted_as_the_wikimedia_family",
    ),
    (
        "p4 licences: an AI aggregator is not denied",
        P4_LICENCES,
        "    if listed_domain_of(host, AI_AGGREGATORS) is not None:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_ai_aggregators_the_design_names_are_denied",
    ),
    (
        "p4 licences: a blocked domain is not denied",
        P4_LICENCES,
        "    if listed_domain_of(host, BLOCKED_DOMAINS) is not None:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_blocked_domain_and_our_own_site_are_denied",
    ),
    (
        "p4 licences: our own site is not denied",
        P4_LICENCES,
        "    if listed_domain_of(host, OWN_DOMAINS) is not None:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_blocked_domain_and_our_own_site_are_denied",
    ),
    (
        "p4 licences: hosts are matched by substring",
        P4_LICENCES,
        '    return host == domain or host.endswith("." + domain)\n',
        "    return domain in host  # mutant\n",
        P4_SOURCES_TEST,
        "test_only_wikipedia_and_wikidata_are_wiki_hosts",
    ),
    (
        "p4 licences: a 24-word run makes a mirror",
        P4_LICENCES,
        "MIRROR_RUN_WORDS = 25\n",
        "MIRROR_RUN_WORDS = 24  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_shared_run_of_25_words_is_a_mirror_and_24_is_not",
    ),
    (
        "p4 licences: the mirror detector is case-sensitive",
        P4_LICENCES,
        "    wiki_runs = set(_runs(_WORD.findall(wiki_text.casefold())))\n",
        "    wiki_runs = set(_runs(_WORD.findall(wiki_text)))  # mutant\n",
        P4_SOURCES_TEST,
        "test_case_punctuation_and_line_breaks_do_not_hide_a_copy",
    ),
    (
        "p4 licences: every other page is CC BY-SA",
        P4_LICENCES,
        "    return M.Licence.RESTRICTED\n",
        "    return M.Licence.CC_BY_SA_4  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_licence_of_a_page_follows_its_host",
    ),
    (
        "p4 licences: a URL of another scheme gets a licence",
        P4_LICENCES,
        '    if urlsplit(url).scheme not in ("http", "https"):\n',
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_url_without_an_http_host_has_no_licence",
    ),
    (
        "p4 subject_gate: a class item is not wrong",
        P4_GATE,
        "    elif concept:\n",
        "    elif False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_class_item_is_wrong_even_when_everything_else_matches",
    ),
    (
        "p4 subject_gate: a deprecated statement counts",
        P4_GATE,
        '    return [s for s in claims.get(pid, []) if s.get("rank") != "deprecated"]\n',
        "    return list(claims.get(pid, []))  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_deprecated_subclass_statement_does_not_make_a_class",
    ),
    (
        "p4 subject_gate: a distant article is not wrong",
        P4_GATE,
        "    elif km is not None and km > wrong_km(site.site_type):\n",
        "    elif False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_an_article_more_than_25_km_away_is_wrong",
    ),
    (
        "p4 subject_gate: roads get no wider radius",
        P4_GATE,
        "    return WRONG_KM_LINEAR if _type_parts(site_type) & LINEAR_TYPE_PARTS else WRONG_KM\n",
        "    return WRONG_KM  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_road_wall_or_aqueduct_is_wrong_only_beyond_50_km",
    ),
    (
        "p4 subject_gate: a shared anchor is not shared",
        P4_GATE,
        "    elif shared or (place_item and not is_settlement_type(site.site_type)):\n",
        "    elif place_item and not is_settlement_type(site.site_type):  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_shared_qid_or_title_makes_the_article_shared",
    ),
    (
        "p4 subject_gate: a place-level item is not shared",
        P4_GATE,
        "    elif shared or (place_item and not is_settlement_type(site.site_type)):\n",
        "    elif shared:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_place_level_item_is_shared_unless_the_site_is_a_settlement",
    ),
    (
        "p4 subject_gate: a settlement type gets no exemption",
        P4_GATE,
        "    elif shared or (place_item and not is_settlement_type(site.site_type)):\n",
        "    elif shared or place_item:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_place_level_item_is_shared_unless_the_site_is_a_settlement",
    ),
    (
        "p4 subject_gate: place-level words match inside words",
        P4_GATE,
        "            set(_WORD.findall(class_labels[cls].casefold())) & PLACE_LEVEL_WORDS\n",
        "            any(word in class_labels[cls].casefold() for word in PLACE_LEVEL_WORDS)  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_place_level_word_inside_another_word_is_not_one",
    ),
    (
        "p4 subject_gate: any page matches the stored QID",
        P4_GATE,
        "    qid_match = site.wikidata_qid is not None and item == site.wikidata_qid\n",
        "    qid_match = site.wikidata_qid is not None  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_qid_that_is_not_the_articles_item_is_no_own_article",
    ),
    (
        "p4 subject_gate: the own radius is ignored",
        P4_GATE,
        "        verdict = M.SubjectVerdict.OWN if km <= own_km else M.SubjectVerdict.NONE\n",
        "        verdict = M.SubjectVerdict.OWN  # mutant\n",
        P4_SOURCES_TEST,
        "test_between_5_and_25_km_an_article_is_neither_own_nor_wrong",
    ),
    (
        "p4 subject_gate: the P625 precision is ignored",
        P4_GATE,
        "        own_km = max(OWN_KM, _precision_km(p625[2]))\n",
        "        own_km = OWN_KM  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_coarse_p625_precision_widens_the_own_radius",
    ),
    (
        "p4 subject_gate: the item's point does not stand in",
        P4_GATE,
        "    if point is None and p625 is not None:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_item_coordinates_stand_in_when_the_article_has_none",
    ),
    (
        "p4 subject_gate: the article's point is not read",
        P4_GATE,
        "    point = _article_point(page)\n",
        "    point = None  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_article_coordinates_come_before_the_items",
    ),
    (
        "p4 subject_gate: token_set_ratio instead of token_sort",
        P4_GATE,
        "    return max(fuzz.token_sort_ratio(a, b) for a in folded_names for b in folded_labels)\n",
        "    return max(fuzz.token_set_ratio(a, b) for a in folded_names for b in folded_labels)  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_name_that_is_only_a_subset_of_the_label_does_not_match",
    ),
    (
        "p4 subject_gate: accents are not folded",
        P4_GATE,
        "    folded = normalize_name(name, remove_parentheses=False, remove_brackets=False)\n",
        "    folded = name.lower()  # mutant\n",
        P4_SOURCES_TEST,
        "test_names_are_compared_without_accents_and_aliases_count",
    ),
    (
        "p4 subject_gate: the name match does not stand in",
        P4_GATE,
        "    elif qid_match and score is not None and score >= NAME_MATCH_MIN:\n",
        "    elif False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_without_coordinates_a_directional_name_match_stands_in",
    ),
    (
        "p4 subject_gate: a disambiguation page passes",
        P4_GATE,
        '    if "disambiguation" in pageprops or _LIST_TITLE.match(title):\n',
        "    if _LIST_TITLE.match(title):  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_disambiguation_page_or_a_list_is_refused",
    ),
    (
        "p4 subject_gate: a List-of page passes",
        P4_GATE,
        '    if "disambiguation" in pageprops or _LIST_TITLE.match(title):\n',
        '    if "disambiguation" in pageprops:  # mutant\n',
        P4_SOURCES_TEST,
        "test_a_disambiguation_page_or_a_list_is_refused",
    ),
    (
        "p4 subject_gate: a stranger anywhere is a parent page",
        P4_GATE,
        "        verdict = M.SubjectVerdict.SHARED if km is not None else M.SubjectVerdict.NONE\n",
        "        verdict = M.SubjectVerdict.SHARED  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_parent_page_within_reach_is_shared_and_a_distant_stranger_is_not",
    ),
    (
        "p4 subject_gate: an uncovered class passes",
        P4_GATE,
        "        if uncovered:\n            raise ValueError(",
        "        if False:  # mutant\n            raise ValueError(",
        P4_SOURCES_TEST,
        "test_a_class_the_label_pass_did_not_cover_raises",
    ),
    (
        "p4 subject_gate: a QID-less site is own by place alone",
        P4_GATE,
        "        and score >= NAME_MATCH_MIN\n",
        "        and score >= 0  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_site_without_a_qid_is_own_only_by_place_and_name_together",
    ),
    (
        "p4 subject_gate: a QID-less site is own by name alone",
        P4_GATE,
        "        and km <= own_km\n",
        "        and km >= 0  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_site_without_a_qid_is_own_only_by_place_and_name_together",
    ),
    (
        "p4 subject_gate: the title counts for a QID site",
        P4_GATE,
        "    if site.wikidata_qid is None:\n        labels = (title, *labels)\n",
        "    if True:  # mutant\n        labels = (title, *labels)\n",
        P4_SOURCES_TEST,
        "test_the_page_title_counts_as_a_name_only_for_a_qid_less_site",
    ),
    (
        "p4 subject_gate: another item judges a QID-less site",
        P4_GATE,
        "    if judged_on != item:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_qid_less_site_is_judged_on_its_pages_own_item_and_no_other",
    ),
    (
        "p4 sources_stage: a web host gets the 1 MiB client",
        P4_SOURCES,
        "        client = self._wiki if LIC.is_wiki_host(F.host_of(url)) else self._web\n",
        "        client = self._wiki  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_wiki_hosts_get_the_1_mib_client_and_every_other_host_the_60_kb_one",
    ),
    (
        "p4 sources_stage: the live wiki client keeps 60 KB",
        P4_SOURCES,
        "    wiki = F.HttpFetcher(timeout=timeout, max_bytes=WIKI_MAX_BYTES)\n",
        "    wiki = F.HttpFetcher(timeout=timeout)  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_live_fetcher_builds_one_client_per_cap_and_paces_them",
    ),
    (
        "p4 sources_stage: a moved revision is pinned",
        P4_SOURCES,
        "    if article.revid != article.lastrevid:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_revid_and_lastrevid_that_differ_hold_the_site_moved_during_fetch",
    ),
    (
        "p4 sources_stage: a fresh revision is pinned",
        P4_SOURCES,
        "    if age < FRESH:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_revision_younger_than_48_hours_is_deferred",
    ),
    (
        "p4 sources_stage: the 48 h rule reads the wrong side",
        P4_SOURCES,
        "    if age < FRESH:\n",
        "    if age > FRESH:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_revision_younger_than_48_hours_is_deferred",
    ),
    (
        "p4 sources_stage: a wrong-subject article is used",
        P4_SOURCES,
        "    if not usable_verdict(gate):\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_wrong_subject_article_is_rejected_whatever_its_age",
    ),
    (
        "p4 sources_stage: a cut answer is parsed",
        P4_SOURCES,
        '        return Stored(body=body, failure="the answer was cut at the fetch cap", truncated=True)\n',
        "        return Stored(body=body, failure=None)  # mutant\n",
        P4_SOURCES_TEST,
        "test_an_article_at_the_1_mib_cap_is_a_failure_and_never_parsed",
    ),
    (
        "p4 sources_stage: a scope-pending site is fetched",
        P4_SOURCES,
        "        if M.SiteFlag.SCOPE_PENDING in site.flags:\n",
        "        if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_scope_pending_site_is_held_and_nothing_is_fetched_for_it",
    ),
    (
        "p4 sources_stage: a file for another QID is reused",
        P4_SOURCES,
        "    entity = entities.get(qid) if isinstance(entities, dict) else None\n",
        "    entity = next(iter(entities.values())) if isinstance(entities, dict) else None  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_phase3_entity_that_cannot_serve_is_refetched_at_the_wiki_cap",
    ),
    (
        "p4 sources_stage: conflicting Phase-3 files are picked from",
        P4_SOURCES,
        "    if len(bodies) > 1:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_two_phase3_files_that_differ_for_one_site_are_a_conflict",
    ),
    (
        "p4 sources_stage: a failed label pass reaches the gate",
        P4_SOURCES,
        "    uncovered = [cls for cls in classes if cls in label_failures]\n",
        "    uncovered = []  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_label_pass_that_failed_holds_the_sites_that_need_it",
    ),
    (
        "p4 sources_stage: a wiki outage does not stop S1",
        P4_SOURCES,
        "    if any(LIC.is_wiki_host(host) for host in fetches.unreachable()):\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_wiki_host_that_does_not_answer_stops_the_batch_and_nothing_is_final",
    ),
    (
        "p4 sources_stage: a finished batch runs again",
        P4_SOURCES,
        "    if report_path.exists():\n        return 0\n",
        "    if False:  # mutant\n        return 0\n",
        P4_SOURCES_TEST,
        "test_a_finished_batch_is_not_asked_again_and_its_report_stands",
    ),
    (
        "p4 sources_stage: another stage's holds are dropped",
        P4_SOURCES,
        "        kept = [h for h in M.load_jsonl(path, M.Hold) if not h.detail.startswith(prefix)]\n",
        "        kept = []  # mutant\n",
        P4_SOURCES_TEST,
        "test_holds_are_tagged_and_a_rerun_replaces_only_its_own",
    ),
    (
        "p4 sources_stage: a rerun keeps its old holds",
        P4_SOURCES,
        "        kept = [h for h in M.load_jsonl(path, M.Hold) if not h.detail.startswith(prefix)]\n",
        "        kept = M.load_jsonl(path, M.Hold)  # mutant\n",
        P4_SOURCES_TEST,
        "test_holds_are_tagged_and_a_rerun_replaces_only_its_own",
    ),
    (
        "p4 sources_stage: an untagged hold is written",
        P4_SOURCES,
        "    if foreign:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_holds_are_tagged_and_a_rerun_replaces_only_its_own",
    ),
    (
        "p4 sources_stage: a meta is pinned over other bytes",
        P4_SOURCES,
        "    if sha256_hex(raw) != meta.sha256_raw:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_write_source_refuses_a_meta_whose_hashes_are_not_its_bytes",
    ),
    (
        "p4 sources_stage: the permalink is no oldid link",
        P4_SOURCES,
        '    return f"https://{lang}.wikipedia.org/w/index.php?title={encoded}&oldid={revid}"\n',
        '    return f"https://{lang}.wikipedia.org/wiki/{encoded}"  # mutant\n',
        P4_SOURCES_TEST,
        "test_the_permalink_is_the_oldid_form_of_the_design",
    ),
    (
        "p4 sources_stage: the pinned text is not NFC",
        P4_SOURCES,
        '    return unicodedata.normalize("NFC", extract.replace("\\r\\n", "\\n").replace("\\r", "\\n"))\n',
        "    return extract  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_pinned_text_is_nfc_with_lf_line_ends",
    ),
    (
        "p4 sources_stage: the article query drops the server clock",
        P4_SOURCES,
        '            "curtimestamp": "1",\n            "titles": title,\n',
        '            "titles": title,  # mutant\n',
        P4_SOURCES_TEST,
        "test_the_article_query_is_the_designs_plus_the_server_clock",
    ),
    (
        "p4 sources_stage: a refetched entity is pinned without its clock",
        P4_SOURCES,
        "        retrieved_at = answer_time(body)\n",
        '        retrieved_at = "2026-01-01T00:00:00Z"  # mutant\n',
        P4_SOURCES_TEST,
        "test_a_refetched_entity_without_its_server_clock_is_not_pinned",
    ),
    (
        "p4 sources_stage: a shared title flag does not reach the gate",
        P4_SOURCES,
        "        {site.enwiki_title} if M.SiteFlag.SHARED_TITLE in site.flags and site.enwiki_title else ()\n",
        "        ()  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_shared_anchor_from_the_plan_flags_reaches_the_gate",
    ),
    (
        "p4 route_stage: a denied host is fetched",
        P4_ROUTES,
        "    denial = web_denial(url)\n",
        "    denial = None  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_denied_host_is_never_asked",
    ),
    (
        "p4 route_stage: a TDM reservation is ignored",
        P4_ROUTES,
        "    if verdict.opt_out:\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_the_tdm_check_runs_before_the_page_and_a_failed_check_refuses_it",
    ),
    (
        "p4 route_stage: a failed TDM check lets the page through",
        P4_ROUTES,
        '    if problem is not None or verdict.signal == "check_failed":\n',
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_the_tdm_check_runs_before_the_page_and_a_failed_check_refuses_it",
    ),
    (
        "p4 route_stage: a non-JSON tdmrep is no reservation",
        P4_ROUTES,
        "                json.loads(text)\n",
        "                pass  # mutant\n",
        P4_ROUTES_TEST,
        "test_the_tdm_check_runs_before_the_page_and_a_failed_check_refuses_it",
    ),
    (
        "p4 route_stage: a rate-limited robots.txt counts as absent",
        P4_ROUTES,
        "    if status is not None and 400 <= status < 500 and status not in (408, 429):\n",
        "    if status is not None and 400 <= status < 500:  # mutant\n",
        P4_ROUTES_TEST,
        "test_the_tdm_check_runs_before_the_page_and_a_failed_check_refuses_it",
    ),
    (
        "p4 route_stage: a page whose HTML reserves TDM is kept",
        P4_ROUTES,
        "    if html_reserves_tdm(html):\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_page_whose_html_reserves_tdm_is_deleted_after_the_check",
    ),
    (
        "p4 route_stage: the reserved copy stays in the store",
        P4_ROUTES,
        "        routing.store.path_for(site.site_id, feature).unlink()\n",
        "        pass  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_page_whose_html_reserves_tdm_is_deleted_after_the_check",
    ),
    (
        "p4 route_stage: a redirect to a denied host is followed",
        P4_ROUTES,
        "    denial = web_denial(final)\n",
        "    denial = None  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_page_that_redirects_to_a_denied_host_is_refused",
    ),
    (
        "p4 route_stage: web identity skips the name",
        P4_ROUTES,
        "    if not any(_padded(name) in page for name in names):\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_web_identity_wants_the_name_and_the_country_or_a_nearby_point",
    ),
    (
        "p4 route_stage: web identity skips the place",
        P4_ROUTES,
        '    return "the page names neither the stored country nor a point within 25 km"\n',
        "    return None  # mutant\n",
        P4_ROUTES_TEST,
        "test_web_identity_wants_the_name_and_the_country_or_a_nearby_point",
    ),
    (
        "p4 route_stage: the mirror detector is skipped",
        P4_ROUTES,
        "        if LIC.is_mirror(text, wiki_text):\n",
        "        if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_page_that_copies_the_sites_wikipedia_text_is_a_mirror",
    ),
    (
        "p4 route_stage: a third query is bought",
        P4_ROUTES,
        'QUERY_TEMPLATES: tuple[str, ...] = (\'"{name}" {rest}\', "{name} {rest}")\n',
        'QUERY_TEMPLATES: tuple[str, ...] = (\'"{name}" {rest}\', "{name} {rest}", "{name}")  # mutant\n',
        P4_ROUTES_TEST,
        "test_at_most_two_queries_per_site",
    ),
    (
        "p4 route_stage: the search goes on after an own article",
        P4_ROUTES,
        "        if found.own is not None:\n            return\n        slot = route_slot(number)\n",
        "        if False:  # mutant\n            return\n        slot = route_slot(number)\n",
        P4_ROUTES_TEST,
        "test_a_wikipedia_hit_goes_back_through_s1_and_wins_lane_w",
    ),
    (
        "p4 route_stage: the quota gate is not asked",
        P4_ROUTES,
        "        refusal = SS.quota_stop_reason(reading, now_utc=routing.now)\n",
        "        refusal = None  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_quota_gate_refusal_stops_the_run_and_a_resumed_run_searches",
    ),
    (
        "p4 route_stage: the budget is not counted",
        P4_ROUTES,
        "    if routing.queries >= routing.budget:\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_spent_budget_holds_the_site_and_the_batch_still_completes",
    ),
    (
        "p4 route_stage: a search the budget stopped still gets a lane",
        P4_ROUTES,
        "        if found.stopped is not None:\n",
        "        if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_spent_budget_holds_the_site_and_the_batch_still_completes",
    ),
    (
        "p4 route_stage: could-not-look is filed as found-nothing",
        P4_ROUTES,
        "        if found.failures:\n            return zero(\n",
        "        if False:  # mutant\n            return zero(\n",
        P4_ROUTES_TEST,
        "test_searches_that_could_not_be_made_hold_fetch_failed_not_no_source",
    ),
    (
        "p4 route_stage: a stop-class error does not stop the run",
        P4_ROUTES,
        "        return self.outage() or self.stopped is not None\n",
        "        return self.outage()  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_stop_class_search_error_stops_the_run",
    ),
    (
        "p4 route_stage: geosearch keeps every nearby article",
        P4_ROUTES,
        "    matched = [t for t in titles if (SG.name_score(names, [t]) or 0.0) >= SG.NAME_MATCH_MIN]\n",
        "    matched = titles  # mutant\n",
        P4_ROUTES_TEST,
        "test_geosearch_keeps_only_articles_that_carry_the_stored_name",
    ),
    (
        "p4 route_stage: the article S1 rejected is asked again",
        P4_ROUTES,
        '    if fact.get("title"):\n',
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_the_article_s1_rejected_is_not_asked_again",
    ),
    (
        "p4 route_stage: a search is bought during a wiki outage",
        P4_ROUTES,
        '    if routing.outage():\n        return "a wiki host did not answer its probe"\n',
        '    if False:  # mutant\n        return "a wiki host did not answer its probe"\n',
        P4_ROUTES_TEST,
        "test_a_wiki_host_outage_in_s1b_stops_and_leaves_nothing_final",
    ),
    (
        "p4 route_stage: only the first URL of a source_url is read",
        P4_ROUTES,
        '    return (site.source_url or "").split()\n',
        "    return [site.source_url] if site.source_url else []  # mutant\n",
        P4_ROUTES_TEST,
        "test_every_url_of_a_multi_line_source_url_is_a_route",
    ),
    (
        "p4 route_stage: a QID-less site gets no witness",
        P4_ROUTES,
        "        if site.wikidata_qid is None:\n            witness = page_item\n",
        "        if False:  # mutant\n            witness = page_item\n",
        P4_ROUTES_TEST,
        "test_a_qid_less_site_is_judged_on_its_pages_item_and_pins_it_as_src_d",
    ),
    (
        "p4 route_stage: an own article in another language is dropped",
        P4_ROUTES,
        "        if gate.verdict is M.SubjectVerdict.OWN and found.other is None:\n",
        "        if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_an_own_article_only_in_another_language_is_lane_t",
    ),
    (
        "p4 route_stage: an R page claims no TDM check",
        P4_ROUTES,
        "            tdm=M.Tdm(checked=True, reserved=False, signal=None),\n",
        "            tdm=None,  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_web_page_that_passes_every_check_is_pinned_as_lane_r",
    ),
    (
        "p4 route_stage: the live probe may be a cached reading",
        P4_ROUTES,
        "        yield searcher, (lambda: probe_minimax_quota(force=True)), (lambda: pacer.wait(host))\n",
        "        yield searcher, (lambda: probe_minimax_quota()), (lambda: pacer.wait(host))  # mutant\n",
        P4_ROUTES_TEST,
        "test_the_live_search_seams_are_the_search_lanes_own",
    ),
    (
        "p4 route_stage: a negative budget is accepted",
        P4_ROUTES,
        "    if not isinstance(max_searches, int) or isinstance(max_searches, bool) or max_searches < 0:\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_negative_or_boolean_budget_is_refused",
    ),
    (
        "p4 content_fetch: the old private name comes back",
        P4_CONTENT_FETCH,
        "@dataclass\nclass _Page:\n",
        "_extract_text_from_html = extract_text_from_html  # mutant\n\n\n@dataclass\nclass _Page:\n",
        P4_ROUTES_TEST,
        "test_the_page_text_function_is_public_and_its_old_name_is_gone_everywhere",
    ),
    (
        "p4 plan4: an undated site is in scope",
        P4_PLAN,
        "    return undated or not passes_date_cutoff(dict(row))\n",
        "    return not passes_date_cutoff(dict(row))  # mutant\n",
        P4_PLAN_TEST,
        "test_a_site_outside_the_date_window_or_undated_is_scope_pending",
    ),
    (
        "p4 plan4: the date window is not applied",
        P4_PLAN,
        "    return undated or not passes_date_cutoff(dict(row))\n",
        "    return undated  # mutant\n",
        P4_PLAN_TEST,
        "test_a_site_outside_the_date_window_or_undated_is_scope_pending",
    ),
    (
        "p4 plan4: a severe card finding waives the description floor",
        P4_PLAN,
        '    if t03.get("description") == "severe":\n',
        '    if "severe" in t03.values():  # mutant\n',
        P4_PLAN_TEST,
        "test_t03_severe_is_flagged_only_for_the_description",
    ),
    (
        "p4 plan4: one site shares an anchor with itself",
        P4_PLAN,
        "    return frozenset(value for value, count in counts.items() if count > 1)\n",
        "    return frozenset(value for value, count in counts.items() if count >= 1)  # mutant\n",
        P4_PLAN_TEST,
        "test_a_qid_or_title_two_sites_store_is_shared_and_one_site_is_not",
    ),
    (
        "p4 plan4: duplicate pairs ignore the distance",
        P4_PLAN,
        "                if km <= DUPLICATE_KM:\n",
        "                if True:  # mutant\n",
        P4_PLAN_TEST,
        "test_a_shared_item_beyond_2_km_or_under_another_name_is_no_pair",
    ),
    (
        "p4 plan4: duplicate pairs ignore the names",
        P4_PLAN,
        '        named = [row for row in members if SG.fold(row["name"]) in names]\n',
        "        named = list(members)  # mutant\n",
        P4_PLAN_TEST,
        "test_a_shared_item_beyond_2_km_or_under_another_name_is_no_pair",
    ),
    (
        "p4 subject_gate: the one fold keeps punctuation",
        P4_GATE,
        '    return " ".join("".join(ch if ch.isalnum() else " " for ch in folded).split())\n',
        "    return folded  # mutant\n",
        P4_PLAN_TEST,
        "test_the_pair_names_are_compared_folded",
    ),
    (
        "p4 plan4: a shared item without names passes",
        P4_PLAN,
        '    if uncovered:\n        raise R.InputError(f"no labels or aliases',
        '    if False:  # mutant\n        raise R.InputError(f"no labels or aliases',
        P4_PLAN_TEST,
        "test_a_shared_item_without_its_names_stops_the_plan",
    ),
    (
        "p4 plan4: the pilot is not first",
        P4_PLAN,
        "    order = list(gold)\n",
        "    order: list[str] = []  # mutant\n",
        P4_PLAN_TEST,
        "test_the_order_is_pilot_then_cleared_then_t03_then_the_rest",
    ),
    (
        "p4 plan4: T03 comes before the cleared defects",
        P4_PLAN,
        "    for wanted in (lambda s: s in cleared, lambda s: s in t03, lambda s: True):\n",
        "    for wanted in (lambda s: s in t03, lambda s: s in cleared, lambda s: True):  # mutant\n",
        P4_PLAN_TEST,
        "test_the_order_is_pilot_then_cleared_then_t03_then_the_rest",
    ),
    (
        "p4 plan4: a site id that is no curated row passes",
        P4_PLAN,
        '        if unknown:\n            raise R.InputError(f"{what} names sites',
        '        if False:  # mutant\n            raise R.InputError(f"{what} names sites',
        P4_PLAN_TEST,
        "test_a_site_id_that_is_not_a_curated_row_stops_the_plan",
    ),
    (
        "p4 plan4: the batches are not 15",
        P4_PLAN,
        "BATCH_SIZE = 15\n",
        "BATCH_SIZE = 16  # mutant\n",
        P4_PLAN_TEST,
        "test_the_plan_is_batches_of_15_named_p4_and_byte_identical_across_runs",
    ),
    (
        "p4 plan4: every refusal counts as a cleared defect",
        P4_PLAN,
        '        if row.get("rule") != CLEARED_RULE:\n',
        "        if False:  # mutant\n",
        P4_PLAN_TEST,
        "test_the_cleared_defects_are_the_report_only_rows_of_the_write_dry_run",
    ),
    (
        "p4 plan4: the stored name is kept among the aliases",
        P4_PLAN,
        '    aliases = sorted({name for name in row["names"] if name != row["name"]})\n',
        '    aliases = sorted(set(row["names"]))  # mutant\n',
        P4_PLAN_TEST,
        "test_the_aliases_are_the_other_stored_names_once_each_in_order",
    ),
    (
        "p4 plan4: a failing step prints no exit line",
        P4_PLAN,
        '        print("STAGE_EXIT=1", flush=True)\n',
        "        pass  # mutant\n",
        P4_PLAN_TEST,
        "test_a_failing_step_still_prints_its_exit_line",
    ),
    (
        "p4 plan4: a failed names request is read anyway",
        P4_PLAN,
        '        if not stored.ok:\n            raise R.InputError(f"the names of',
        '        if False:  # mutant\n            raise R.InputError(f"the names of',
        P4_PLAN_TEST,
        "test_a_names_request_that_fails_stops_the_plan",
    ),
    (
        "p4 plan4: a row of another shape passes",
        P4_PLAN,
        '    if missing or unknown:\n        raise R.InputError(f"a plan row with',
        '    if False:  # mutant\n        raise R.InputError(f"a plan row with',
        P4_PLAN_TEST,
        "test_a_row_of_another_shape_is_refused",
    ),
    # Review of wip/p4-sources, 2026-09-23: a page is judged on its own item, an invalid title
    # is routed, a stop is never final, pins wait for the whole walk, wiki hosts never land in
    # lane R, a redirect passes the policy of where it landed, and the guards that had no test.
    (
        "p4 subject_gate: a wrong-subject page is judged on the site's item",
        P4_GATE,
        "    if judged_on != item:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_wrong_subject_page_is_judged_on_its_own_item_never_on_the_stored_one",
    ),
    (
        "p4 subject_gate: a parent page without a point is shared",
        P4_GATE,
        "        verdict = M.SubjectVerdict.SHARED if km is not None else M.SubjectVerdict.NONE\n",
        "        verdict = M.SubjectVerdict.SHARED  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_parent_page_without_coordinates_takes_its_own_items_point_never_the_sites",
    ),
    (
        "p4 sources_stage: a mismatched page's own item is never fetched",
        P4_SOURCES,
        "        if item is not None and item != site.wikidata_qid:\n",
        "        if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_wrong_subject_article_is_judged_on_its_own_item_and_rejected",
    ),
    (
        "p4 sources_stage: a mismatched page is judged on the site's item",
        P4_SOURCES,
        "        entity = page_item.entity\n",
        "        entity = stored_entity  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_coordinate_less_stranger_stays_none_although_the_sites_item_has_a_point",
    ),
    (
        "p4 sources_stage: an unreadable page item reaches the gate",
        P4_SOURCES,
        "        if page_item.failure is not None:\n",
        "        if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_an_article_whose_own_item_cannot_be_read_holds_the_site",
    ),
    (
        "p4 sources_stage: a page item's classes are not covered",
        P4_SOURCES,
        "        problem = _uncovered(page_item.entity, label_failures)\n",
        "        problem = None  # mutant\n",
        P4_SOURCES_TEST,
        "test_an_article_whose_own_items_classes_have_no_labels_holds_the_site",
    ),
    (
        "p4 sources_stage: a QID-less article is pinned without its witness",
        P4_SOURCES,
        "        witness=page_item if site.wikidata_qid is None else None,\n",
        "        witness=None,  # mutant\n",
        P4_SOURCES_TEST,
        "test_a_titled_site_without_a_qid_is_own_by_place_and_name_and_pins_its_witness",
    ),
    (
        "p4 sources_stage: an invalid title is held as a failure",
        P4_SOURCES,
        '        raise TitleInvalid(str(page.get("invalidreason")))\n',
        '        raise ArticleUnreadable(str(page.get("invalidreason")))  # mutant\n',
        P4_SOURCES_TEST,
        "test_a_title_wikipedia_calls_invalid_is_routed_not_held",
    ),
    (
        "p4 sources_stage: an invalid title is not routed",
        P4_SOURCES,
        "    {STATUS_REJECTED, STATUS_MISSING, STATUS_INVALID_TITLE, STATUS_NO_TITLE}\n",
        "    {STATUS_REJECTED, STATUS_MISSING, STATUS_NO_TITLE}  # mutant\n",
        P4_ROUTES_TEST,
        "test_petras_invalid_title_reaches_its_source_url",
    ),
    (
        "p4 sources_stage: an empty extract is pinned",
        P4_SOURCES,
        '    if not (article.extract or "").strip():\n        detail = f"{article.title!r}: verdict',
        '    if False:  # mutant\n        detail = f"{article.title!r}: verdict',
        P4_SOURCES_TEST,
        "test_an_own_article_with_an_empty_extract_is_never_pinned",
    ),
    (
        "p4 sources_stage: the label pass takes any count",
        P4_SOURCES,
        "    if not 1 <= len(qids) <= LABELS_PER_REQUEST:\n",
        "    if False:  # mutant\n",
        P4_SOURCES_TEST,
        "test_the_label_pass_asks_1_to_50_classes_a_request",
    ),
    (
        "p4 sources_stage: an absent class gets a label",
        P4_SOURCES,
        '        if not isinstance(entity, dict):\n            raise ArticleUnreadable(f"{qid}: asked',
        '        if False:  # mutant\n            raise ArticleUnreadable(f"{qid}: asked',
        P4_SOURCES_TEST,
        "test_a_label_answer_without_an_asked_class_is_unreadable",
    ),
    (
        "p4 licences: a URL without a host gets a licence",
        P4_LICENCES,
        "    return F.host_of(url)\n",
        '    return urlsplit(url).hostname or ""  # mutant\n',
        P4_SOURCES_TEST,
        "test_a_url_without_an_http_host_has_no_licence",
    ),
    (
        "p4 route_stage: a mismatched candidate is judged without its item",
        P4_ROUTES,
        "    elif article.item is not None:\n",
        "    elif False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_wrong_subject_candidate_is_judged_on_its_own_item_not_the_sites",
    ),
    (
        "p4 route_stage: an unreadable candidate item is judged anyway",
        P4_ROUTES,
        "        if page_item.entity is None:\n",
        "        if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_qid_less_site_whose_page_item_cannot_be_read_gets_no_article",
    ),
    (
        "p4 route_stage: an invalid candidate title is a failure",
        P4_ROUTES,
        '        found.notes.append(f"{label}: an invalid title: {exc}")\n',
        '        found.failures.append(f"{label}: an invalid title: {exc}")  # mutant\n',
        P4_ROUTES_TEST,
        "test_an_invalid_candidate_title_is_an_answer_not_a_failure",
    ),
    (
        "p4 route_stage: a stopped walk is decided on",
        P4_ROUTES,
        "    if routing.halted():\n        # Not a fact about the sites",
        "    if False:  # mutant\n        # Not a fact about the sites",
        P4_ROUTES_TEST,
        "test_a_quota_gate_refusal_stops_the_run_and_a_resumed_run_searches",
    ),
    (
        "p4 route_stage: an outage pins what the walk found before it",
        P4_ROUTES,
        "    if routing.halted():\n        # Not a fact about the sites",
        "    if False:  # mutant\n        # Not a fact about the sites",
        P4_ROUTES_TEST,
        "test_an_outage_later_in_the_batch_pins_nothing_for_the_sites_before_it",
    ),
    (
        "p4 route_stage: a stopped walk walks on",
        P4_ROUTES,
        "        if routing.halted():\n            break\n",
        "        if False:  # mutant\n            break\n",
        P4_ROUTES_TEST,
        "test_a_stopped_walk_asks_nothing_for_the_sites_after_it",
    ),
    (
        "p4 route_stage: the quota readings of earlier runs are dropped",
        P4_ROUTES,
        "        earlier_quota=SS.read_quota(search_report),\n",
        "        earlier_quota=[],  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_quota_gate_refusal_stops_the_run_and_a_resumed_run_searches",
    ),
    (
        "p4 route_stage: the queries of earlier runs are not counted",
        P4_ROUTES,
        '            "queries": queries,\n',
        '            "queries": routing.queries,  # mutant\n',
        P4_ROUTES_TEST,
        "test_queries_bought_before_an_outage_are_counted",
    ),
    (
        "p4 route_stage: every attempt counts as a query",
        P4_ROUTES,
        '    return sum(1 for entry in lines if entry.get("attempt") == 1), len(lines)\n',
        "    return len(lines), len(lines)  # mutant\n",
        P4_ROUTES_TEST,
        "test_searches_that_could_not_be_made_hold_fetch_failed_not_no_source",
    ),
    (
        "p4 route_stage: a wiki page is a lane-R page",
        P4_ROUTES,
        "    if LIC.is_wiki_host(LIC.host_of(url)):\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_simple_english_hit_is_never_a_lane_r_page",
    ),
    (
        "p4 route_stage: a redirect into Wikipedia is a lane-R page",
        P4_ROUTES,
        "    if LIC.is_wiki_host(LIC.host_of(url)):\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_page_that_redirects_into_wikipedia_is_never_a_lane_r_page",
    ),
    (
        "p4 route_stage: a same-host redirect is not checked again",
        P4_ROUTES,
        "    if final != url:\n",
        "    if LIC.host_of(final) != LIC.host_of(url):  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_redirect_into_a_reserved_path_is_refused_and_deleted",
    ),
    (
        "p4 route_stage: a redirect is never checked again",
        P4_ROUTES,
        "    if final != url:\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_redirect_into_a_reserved_path_is_refused_and_deleted",
    ),
    (
        "p4 route_stage: a failed route lets a lower lane through",
        P4_ROUTES,
        "        if found.failures:\n            return zero(\n",
        "        if False:  # mutant\n            return zero(\n",
        P4_ROUTES_TEST,
        "test_a_failed_wikipedia_route_holds_the_site_instead_of_a_lower_lane",
    ),
    (
        "p4 route_stage: a page that is not UTF-8 is kept",
        P4_ROUTES,
        '        return f"{TDM_REFUSED}: the page is not UTF-8 text, so its HTML reservation is unknown"\n',
        '        return "the page is not UTF-8 text"  # mutant\n',
        P4_ROUTES_TEST,
        "test_a_page_that_is_not_utf8_counts_as_reserved_and_is_deleted",
    ),
    (
        "p4 route_stage: a deleted page is fetched again",
        P4_ROUTES,
        "    if refusal.exists():\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_page_deleted_for_tdm_is_never_fetched_again_by_a_resumed_run",
    ),
    (
        "p4 route_stage: a deleted page leaves no record",
        P4_ROUTES,
        '            feature=f"{feature}{TDM_REFUSED_SUFFIX}",\n',
        '            feature=f"{feature}.unread",  # mutant\n',
        P4_ROUTES_TEST,
        "test_a_page_deleted_for_tdm_is_never_fetched_again_by_a_resumed_run",
    ),
    (
        "p4 route_stage: an S1b article is pinned whatever its answer says",
        P4_ROUTES,
        "    if problem is not None:\n        raise _Held(problem[0], problem[1])\n",
        "    if False:  # mutant\n        raise _Held(problem[0], problem[1])\n",
        P4_ROUTES_TEST,
        "test_an_article_s1b_found_is_held_by_the_rules_on_its_response",
    ),
    (
        "p4 route_stage: a page outside the article namespace is kept",
        P4_ROUTES,
        '    if article.page.get("ns") != 0:\n',
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_candidate_outside_the_article_namespace_is_never_kept",
    ),
    (
        "p4 route_stage: a cut policy file is read",
        P4_ROUTES,
        '        if stored.truncated:\n            return f"{what} was cut at the page cap"\n',
        '        if False:  # mutant\n            return f"{what} was cut at the page cap"\n',
        P4_ROUTES_TEST,
        "test_a_policy_file_that_cannot_be_read_whole_refuses_the_page",
    ),
    (
        "p4 route_stage: a policy file that is not UTF-8 is read",
        P4_ROUTES,
        '            text = stored.body.decode("utf-8")\n',
        '            text = stored.body.decode("utf-8", errors="replace")  # mutant\n',
        P4_ROUTES_TEST,
        "test_a_policy_file_that_cannot_be_read_whole_refuses_the_page",
    ),
    (
        "p4 route_stage: one site fetches any number of web hits",
        P4_ROUTES,
        "    if found.web_fetches >= MAX_WEB_FETCHES_PER_SITE:\n",
        "    if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_one_site_fetches_at_most_six_web_hits",
    ),
    (
        "p4 route_stage: one site pins any number of lane-R pages",
        P4_ROUTES,
        "        if len(found.pages) >= MAX_R_PAGES_PER_SITE:\n",
        "        if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_one_site_pins_at_most_three_lane_r_pages",
    ),
    (
        "p4 route_stage: a stored search for another query is read",
        P4_ROUTES,
        "            if record.query != query:\n",
        "            if False:  # mutant\n",
        P4_ROUTES_TEST,
        "test_a_stored_search_for_another_query_stops_the_stage",
    ),
    (
        "p4 route_stage: a site without an S1 outcome is routed",
        P4_ROUTES,
        '    if missing:\n        raise R.InputError(f"{batch_dir}: {S1.SOURCES_REPORT} has no outcome',
        '    if False:  # mutant\n        raise R.InputError(f"{batch_dir}: {S1.SOURCES_REPORT} has no outcome',
        P4_ROUTES_TEST,
        "test_a_sources_report_without_a_site_of_the_batch_stops_the_stage",
    ),
    (
        "p4 plan4: a names list of another type passes",
        P4_PLAN,
        "    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):\n",
        "    if False:  # mutant\n",
        P4_PLAN_TEST,
        "test_a_row_of_another_shape_is_refused",
    ),
    (
        "p4 plan4: a control-character title is not listed",
        P4_PLAN,
        '        and any(unicodedata.category(ch) == "Cc" for ch in row["enwiki_title"])\n',
        "        and False  # mutant\n",
        P4_PLAN_TEST,
        "test_a_stored_title_with_a_control_character_is_listed_for_the_repair",
    ),
    (
        "p4 plan4: the build summary drops the invalid titles",
        P4_PLAN,
        '        "invalid_titles": invalid_titles(rows),\n',
        '        "invalid_titles": [],  # mutant\n',
        P4_PLAN_TEST,
        "test_build_writes_the_plan_and_prints_its_exit_line",
    ),
]
MUTATIONS += PHASE4_SOURCES_MUTATIONS
#: The owner-case coordinates' second wave (2026-09-23): a third witness from the web, proven from the
#: live page (`bcases/web_witness.py`), weighed under the unchanged rule (`classify.weigh`) and planned
#: under its own stamp (`coord_plan.WAVE2`). Each case breaks one guard and names the test that must go
#: red. Every label starts with "bcases web: ", so `mutation_sweep.py "bcases web"` runs the set alone.
_WW = BCASES + "web_witness.py"
_WW_RUN = BCASES + "run.py"
_WW_TEST = "tests/remediation/test_bcases_web.py"
_WW_HOST = "test_a_wiki_host_or_mirror_is_never_a_web_witness"
_WW_NAMED = "test_the_named_mirrors_are_in_the_list_and_matched_by_domain_only"
_WW_NUMBERS = "test_the_numbers_are_the_pages_not_the_agents"
_WW_FAR = "test_a_list_pages_coordinate_far_from_the_name_is_not_the_sites"
_WW_WORDS = "test_generic_and_short_words_of_the_name_do_not_identify_it"
_WW_FORGED = "test_an_accepted_row_verify_candidate_did_not_write_is_refused"
_WW_RESEARCH = "test_the_research_file_is_refused_when_it_is_not_one_line_per_case"
_WW_LABEL = "test_a_web_witness_is_named_by_its_host_and_one_host_is_one_witness"
_WW_WAVE2 = "test_wave_two_renders_under_its_own_stamp_and_directory"
_WW_WAVE1_SITE = "test_wave_two_refuses_a_site_of_wave_one"
WEB_WITNESS_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "bcases web: a Wikipedia or mirror page is asked for its coordinates",
        _WW,
        '    if wiki is not None:\n        raise Rejected("wiki-host", f"{host} is {wiki}',
        '    if False:  # mutant\n        raise Rejected("wiki-host", f"{host} is {wiki}',
        _WW_TEST,
        _WW_HOST,
    ),
    (
        "bcases web: a redirect into Wikipedia is read as the page",
        _WW,
        '    if wiki is not None:\n        raise Rejected("wiki-host", f"{url} redirected',
        '    if False:  # mutant\n        raise Rejected("wiki-host", f"{url} redirected',
        _WW_TEST,
        "test_a_redirect_into_wikipedia_is_rejected",
    ),
    (
        "bcases web: a named mirror drops off the list",
        _WW,
        '        "wikiwand.com",\n',
        "",
        _WW_TEST,
        _WW_NAMED,
    ),
    (
        "bcases web: the wiki list is matched by substring",
        _WW,
        "    wiki = listed_domain_of(host, WIKI_HOSTS)\n    if wiki is not None:\n",
        "    wiki = next((d for d in WIKI_HOSTS if d in host), None)  # mutant\n"
        "    if wiki is not None:\n",
        _WW_TEST,
        _WW_NAMED,
    ),
    (
        "bcases web: our own site or a blocked host is a witness",
        _WW,
        "    if refused is not None:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_our_own_site_and_a_blocked_host_are_refused",
    ),
    (
        "bcases web: a private address is asked",
        _WW,
        '    if not is_public_http_url(url):\n        raise Rejected("not-public"',
        '    if False:  # mutant\n        raise Rejected("not-public"',
        _WW_TEST,
        "test_a_private_address_is_never_asked",
    ),
    (
        "bcases web: a redirect hop into a private address is followed",
        _WW,
        "        if not is_public_http_url(url):\n            raise NonPublicAddress",
        "        if False:  # mutant\n            raise NonPublicAddress",
        _WW_TEST,
        "test_a_redirect_hop_into_a_private_address_is_refused_inside_the_transport",
    ),
    (
        "bcases web: a refusing host is asked four times",
        _WW,
        "MAX_ATTEMPTS = 1\n",
        "MAX_ATTEMPTS = 4  # mutant\n",
        _WW_TEST,
        "test_the_real_fetcher_asks_a_refusing_host_once_and_caches_a_page",
    ),
    (
        "bcases web: a refused page is read as an empty page",
        _WW,
        '    except FetchError as exc:\n        raise Rejected("http", str(exc)) from None\n',
        '    except FetchError:  # mutant\n        return url, ""\n',
        _WW_TEST,
        "test_an_http_refusal_is_a_rejection_with_its_status_and_one_request",
    ),
    (
        "bcases web: a 404 page is read",
        _WW,
        '    if payload["error"]:\n',
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_a_missing_page_is_a_rejection",
    ),
    (
        "bcases web: a PDF is read as a page",
        _WW,
        "    if media not in HTML_TYPES:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_a_pdf_or_another_document_is_not_read",
    ),
    (
        "bcases web: a challenge page is read as a page",
        _WW,
        '    if wall is not None:\n        raise Rejected("bot-wall"',
        '    if False:  # mutant\n        raise Rejected("bot-wall"',
        _WW_TEST,
        "test_a_challenge_page_served_with_200_is_a_bot_wall",
    ),
    (
        "bcases web: the Cloudflare challenge title is not recognised",
        _WW,
        '    ("<title>just a moment...</title>", "a Cloudflare challenge page"),\n',
        "",
        _WW_TEST,
        "test_a_challenge_page_served_with_200_is_a_bot_wall",
    ),
    (
        "bcases web: the quote need not occur in the page",
        _WW,
        "    if needle not in hay:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_the_quote_must_occur_in_the_page",
    ),
    (
        "bcases web: a script's text counts as page text",
        _WW,
        "    return normalise(html.unescape(extract_text_from_html(markup)))\n",
        "    return normalise(html.unescape(markup))  # mutant\n",
        _WW_TEST,
        "test_a_coordinate_inside_a_script_is_not_page_text",
    ),
    (
        "bcases web: the page's entities are compared undecoded",
        _WW,
        "    return normalise(html.unescape(extract_text_from_html(markup)))\n",
        "    return normalise(extract_text_from_html(markup))  # mutant\n",
        _WW_TEST,
        "test_the_page_and_the_quote_are_compared_across_glyph_variants",
    ),
    (
        "bcases web: the glyphs are unified only after NFKC broke them",
        _WW,
        '    unified = unicodedata.normalize("NFKC", text.translate(_GLYPHS)).translate(_GLYPHS)\n',
        '    unified = unicodedata.normalize("NFKC", text).translate(_GLYPHS)  # mutant\n',
        _WW_TEST,
        "test_the_glyphs_are_unified_before_nfkc_would_break_them",
    ),
    (
        "bcases web: whitespace runs are compared as they stand",
        _WW,
        '    return " ".join(unified.replace("\'\'", \'"\').split())\n',
        "    return unified.replace(\"''\", '\"')  # mutant\n",
        _WW_TEST,
        "test_whitespace_runs_are_one_space",
    ),
    (
        "bcases web: a grid reference is parsed as degrees",
        _WW,
        "    if grid is not None:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_a_grid_reference_is_not_read",
    ),
    (
        "bcases web: a D M S value without its letter is read",
        _WW,
        "    if minutes is not None and letter is None:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_a_dms_value_needs_its_hemisphere_letter",
    ),
    (
        "bcases web: a whole number is read as a coordinate",
        _WW,
        '    if letter is None and "." not in deg and groups.get("dg") is None:\n',
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_a_whole_number_is_not_a_coordinate",
    ),
    (
        "bcases web: three values are read as two",
        _WW,
        "        if len(found) == 2 and not any(_letter(m) for m in found):\n",
        "        if found and not any(_letter(m) for m in found):  # mutant\n",
        _WW_TEST,
        "test_two_values_in_one_form_and_no_more",
    ),
    (
        "bcases web: a word beside the numbers is read as a label",
        _WW,
        "    if stray:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_words_beside_the_coordinates_are_not_read",
    ),
    (
        "bcases web: a sign and a letter are read together",
        _WW,
        "    if sign and letter:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_a_sign_and_a_letter_together_are_not_read",
    ),
    (
        "bcases web: one axis named twice is read",
        _WW,
        "        if len(axis) != 2:\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        "test_one_axis_named_twice_is_not_read",
    ),
    (
        "bcases web: a point off the Earth is read",
        _WW,
        '    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):\n        raise Rejected("unparsed"',
        '    if False:  # mutant\n        raise Rejected("unparsed"',
        _WW_TEST,
        "test_a_point_off_the_earth_is_not_read",
    ),
    (
        "bcases web: sixty minutes are read",
        _WW,
        "            if float(part) >= 60.0:\n",
        "            if False:  # mutant\n",
        _WW_TEST,
        "test_minutes_and_seconds_stay_below_sixty",
    ),
    (
        "bcases web: the agent's numbers stand for the page's",
        _WW,
        "    if abs(got_lat - lat) > MATCH_DEGREES or abs(got_lon - lon) > MATCH_DEGREES:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        _WW_NUMBERS,
    ),
    (
        "bcases web: the numbers match to a thousandth of a degree",
        _WW,
        "MATCH_DEGREES = 1e-6\n",
        "MATCH_DEGREES = 1e-3  # mutant\n",
        _WW_TEST,
        _WW_NUMBERS,
    ),
    (
        "bcases web: the witness carries the agent's numbers",
        _WW,
        '        "lat": got_lat,\n',
        '        "lat": lat,  # mutant\n',
        _WW_TEST,
        _WW_NUMBERS,
    ),
    (
        "bcases web: a page need not name the site",
        _WW,
        "    if word is None:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        _WW_FAR,
    ),
    (
        "bcases web: the name may stand anywhere on the page",
        _WW,
        "IDENTITY_WINDOW = 1500\n",
        "IDENTITY_WINDOW = 15000  # mutant\n",
        _WW_TEST,
        _WW_FAR,
    ),
    (
        "bcases web: a short word of the name identifies it",
        _WW,
        "    return sorted(t for t in C.tokens(name) if len(t) >= MIN_TOKEN)\n",
        "    return sorted(C.tokens(name))  # mutant\n",
        _WW_TEST,
        _WW_WORDS,
    ),
    (
        "bcases web: a generic word of the name identifies it",
        _WW,
        "    return sorted(t for t in C.tokens(name) if len(t) >= MIN_TOKEN)\n",
        "    return sorted(t for t in C.fold(name).split() if len(t) >= MIN_TOKEN)  # mutant\n",
        _WW_TEST,
        _WW_WORDS,
    ),
    (
        "bcases web: the whole name matches inside a word",
        _WW,
        '        if whole and f" {whole} " in f" {folded} ":\n',
        "        if whole and whole in folded:  # mutant\n",
        _WW_TEST,
        "test_a_name_without_a_distinctive_word_is_matched_whole",
    ),
    (
        "bcases web: a name in parentheses on the page is dropped",
        _WW,
        "        folded = C.fold(window, keep_parentheses=True)\n",
        "        folded = C.fold(window)  # mutant\n",
        _WW_TEST,
        "test_a_name_in_parentheses_on_the_page_identifies_the_site",
    ),
    (
        "bcases web: a candidate's numbers are not checked",
        _WW,
        "        if (\n            isinstance(value, bool)\n            or not isinstance(value, int | float)\n"
        "            or not math.isfinite(value)\n        ):\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        "test_a_malformed_candidate_is_rejected_and_nothing_is_asked",
    ),
    (
        "bcases web: a research line for a foreign site is read",
        _WW,
        "        if sid not in known:\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        _WW_RESEARCH,
    ),
    (
        "bcases web: a site researched twice is read twice",
        _WW,
        "        if sid in seen:\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        _WW_RESEARCH,
    ),
    (
        "bcases web: stale web witnesses are weighed",
        _WW,
        "    if asked != answered:\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_the_web_witnesses_must_be_the_verification_of_the_research",
    ),
    (
        "bcases web: a forged witness on a wiki host is weighed",
        _WW,
        "        if listed_domain_of(host, WIKI_HOSTS) is not None:\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        _WW_FORGED,
    ),
    (
        "bcases web: a witness whose step is not its grid is weighed",
        _WW,
        '        if w["step"] != C.grid_of(w["lat"], w["lon"]):\n',
        "        if False:  # mutant\n",
        _WW_TEST,
        _WW_FORGED,
    ),
    (
        "bcases web: a witness that is not the page read is weighed",
        _WW,
        '        if w["kind"] != "web" or w["url"] != row["final_url"] or host is None:\n',
        "        if host is None:  # mutant\n",
        _WW_TEST,
        _WW_FORGED,
    ),
    (
        "bcases web: a host with two points gives a witness",
        _WW,
        "            if len(points) == 1:\n",
        "            if True:  # mutant\n",
        _WW_TEST,
        "test_one_host_is_one_witness_and_a_host_with_two_points_gives_none",
    ),
    (
        "bcases web: a first-wave site is weighed again",
        _WW,
        "        if sid in wave1:\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        "test_a_first_wave_site_is_never_reweighed",
    ),
    (
        "bcases web: a case that was not open is weighed",
        _WW,
        '        if old["verdict"] != "review":\n',
        "        if False:  # mutant\n",
        _WW_TEST,
        "test_only_a_review_case_is_reweighed",
    ),
    (
        "bcases web: a cache that does not reproduce the first wave is used",
        _WW,
        "        if json.loads(json.dumps(again)) != first:\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        "test_reweigh_refuses_a_cache_that_does_not_reproduce_the_first_wave",
    ),
    (
        "bcases web: a move into another country is planned",
        _WW,
        '            if not country["agrees"]:\n',
        "            if False:  # mutant\n",
        _WW_TEST,
        "test_a_move_into_another_country_is_held_for_review",
    ),
    (
        "bcases web: a research input of other sites is weighed",
        _WW,
        '    if {str(r["site_id"]) for r in delivered} != set(cases):\n',
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_reweigh_refuses_a_research_input_that_is_not_the_review_cases",
    ),
    (
        "bcases web: two pages of one host are two witnesses",
        _CL,
        "    if a.label == b.label:\n        return False\n",
        "    if False:  # mutant\n        return False\n",
        _WW_TEST,
        _WW_LABEL,
    ),
    (
        "bcases web: a web page outranks the item",
        _CL,
        'PRIORITY = {"wikidata": 0, "enwiki": 1, "web": 2}\n',
        'PRIORITY = {"wikidata": 1, "enwiki": 2, "web": 0}  # mutant\n',
        _WW_TEST,
        "test_a_web_page_that_confirms_the_item_moves_the_site_to_the_items_point",
    ),
    (
        "bcases web: a web page outranks the article",
        _CL,
        'PRIORITY = {"wikidata": 0, "enwiki": 1, "web": 2}\n',
        'PRIORITY = {"wikidata": 0, "enwiki": 2, "web": 1}  # mutant\n',
        _WW_TEST,
        "test_the_article_outranks_a_web_page",
    ),
    (
        "bcases web: every web page is one witness named web",
        _CL,
        '        return f"web:{web_host(self.url)}" if self.kind == "web" else self.kind\n',
        "        return self.kind  # mutant\n",
        _WW_TEST,
        _WW_LABEL,
    ),
    (
        "bcases web: www.x.org and x.org are two publishers",
        _CL,
        '    return host.rstrip(".").removeprefix("www.")\n',
        '    return host.rstrip(".")  # mutant\n',
        _WW_TEST,
        _WW_LABEL,
    ),
    (
        "bcases web: two agreeing pairs on two points move the site",
        _CL,
        "        if clash:\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        "test_two_agreeing_pairs_on_two_points_are_read_not_moved",
    ),
    (
        "bcases web: two witnesses of one label overwrite each other",
        _CL,
        "    if len(distances) != len(ordered):\n",
        "    if False:  # mutant\n",
        _WW_TEST,
        "test_two_witnesses_of_one_label_cannot_be_weighed_together",
    ),
    (
        "bcases web: a site without an item ignores its web witnesses",
        _CL,
        "        if not web:\n",
        "        if True:  # mutant\n",
        _WW_TEST,
        "test_two_web_pages_of_two_hosts_pair_for_a_site_without_an_item",
    ),
    (
        "bcases web: a museum object's web witnesses are dropped",
        _CL,
        "        ws = [*ws, *web]\n        verdict = weigh(stored, ws)\n",
        "        ws = list(ws)  # mutant\n        verdict = weigh(stored, ws)\n",
        _WW_TEST,
        "test_a_museum_object_keeps_the_first_waves_rule",
    ),
    (
        "bcases web: the item's web witnesses are dropped",
        _CL,
        "    ws = [*ws, *web]\n    record.update(witnesses=",
        "    ws = list(ws)  # mutant\n    record.update(witnesses=",
        _WW_TEST,
        "test_reweigh_moves_a_case_a_web_page_confirms",
    ),
    (
        "bcases web: a web witness's label is not recorded",
        _CL,
        '    if w.kind == "web":\n        out["label"] = w.label\n',
        '    if False:  # mutant\n        out["label"] = w.label\n',
        _WW_TEST,
        "test_two_web_pages_of_two_hosts_pair_for_a_site_without_an_item",
    ),
    (
        "bcases web: the reason names only the first two of three witnesses",
        _CL,
        "    if len(ws) == 2:\n",
        "    if len(ws) >= 2:  # mutant\n",
        _WW_TEST,
        "test_the_reason_names_every_pair_when_three_witnesses_do_not_agree",
    ),
    (
        "bcases web: wave 2 journals under wave 1's stamp",
        _CP,
        "    stamp = wave.rollback_stamp if reversal else wave.run_stamp\n",
        "    stamp = ROLLBACK_STAMP if reversal else RUN_STAMP  # mutant\n",
        _WW_TEST,
        _WW_WAVE2,
    ),
    (
        "bcases web: wave 2's verify reads wave 1's journal",
        _CP,
        "            + sql_literal(wave.run_stamp)\n",
        "            + sql_literal(RUN_STAMP)  # mutant\n",
        _WW_TEST,
        "test_wave_two_check_and_verify_read_their_own_rows_and_stamp",
    ),
    (
        "bcases web: wave 2 plans a site of wave 1",
        _CP,
        "        if again:\n",
        "        if False:  # mutant\n",
        _WW_TEST,
        _WW_WAVE1_SITE,
    ),
    (
        "bcases web: wave 2 does not know wave 1's plan",
        _CP,
        "    (PLAN_DIR,),\n)",
        "    (),  # mutant\n)",
        _WW_TEST,
        _WW_WAVE1_SITE,
    ),
    (
        "bcases web: wave 2 renders into wave 1's directory",
        _CP,
        '    "coords_plan_wave2",\n',
        "    PLAN_DIR,  # mutant\n",
        _WW_TEST,
        _WW_WAVE2,
    ),
    (
        "bcases web: the web page a move rests on drops out of its evidence",
        _CP,
        '        if label_of(w) in row["agreeing"]\n    ]',
        '        if w["kind"] in row["agreeing"]  # mutant\n    ]',
        _WW_TEST,
        _WW_WAVE2,
    ),
    (
        "bcases web: a wave without a move renders an empty statement",
        _CP,
        '    if not rows:\n        raise PlanError(f"{wave.verdicts} holds no move',
        '    if False:  # mutant\n        raise PlanError(f"{wave.verdicts} holds no move',
        _WW_TEST,
        "test_a_wave_without_a_move_has_nothing_to_plan",
    ),
    (
        "bcases web: wave 1's plan reads another source",
        _CP,
        '    "the classifier\'s `move` verdicts",\n',
        '    "the classifier\'s verdicts",  # mutant\n',
        _WW_TEST,
        "test_wave_one_still_renders_what_is_committed",
    ),
    (
        "bcases web: the command line plans wave 1 for --wave 2",
        _WW_RUN,
        "    wave = P.WAVES[args.wave]\n",
        "    wave = P.WAVE1  # mutant\n",
        _WW_TEST,
        "test_the_command_line_plans_the_second_wave",
    ),
]
MUTATIONS += WEB_WITNESS_MUTATIONS


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
