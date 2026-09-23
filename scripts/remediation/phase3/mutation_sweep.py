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
        "    for site_id, rows in _read_outcome_failures(path.with_name(SEARCH_REPORT_NAME)).items():\n",
        "    for site_id, rows in {}.items():  # mutated\n",
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
P4_VERIFY = "scripts/remediation/phase4/verify4.py"
P4_VERIFY_TEST = "tests/remediation/test_phase4_verify.py"
P4_ACCEPT = "output/remediation/tools/verify_writes4.py"
P4_ACCEPT_TEST = "tests/remediation/test_phase4_accept.py"
SHORTS_AUDIT = "pipeline/video/shorts_audit.py"
SHORTS_EXPORT = "pipeline/video/shorts_export.py"
SHORTS_TEST = "tests/pipeline/video/test_shorts.py"
#: Track C (WB-C1, WB-C2, WB-C3): the verifier's reading and every V-rule, the acceptance, and the
#: shorts S13 card trace - each guard with the one test that must fail when it is broken.
PHASE4_VERIFY_MUTATIONS: list[tuple[str, str, str, str, str, str]] = [
    (
        "p4 verify4: a protected span is offered",
        P4_VERIFY,
        "        if not protected_in(text[low:high])\n",
        "        if True  # mutant\n",
        P4_VERIFY_TEST,
        "test_a_span_with_a_protected_token_is_never_offered",
    ),
    (
        "p4 verify4: a number comma is a delimiter",
        P4_VERIFY,
        '        if text[i] == "," and i + 1 < end and text[i + 1].isspace() and depth[i - start] == 0\n',
        '        if text[i] == "," and i + 1 < end and depth[i - start] == 0  # mutant\n',
        P4_VERIFY_TEST,
        "test_a_number_comma_and_a_bracketed_comma_are_no_delimiters",
    ),
    (
        "p4 verify4: a bracketed comma is a delimiter",
        P4_VERIFY,
        '        if text[i] == "," and i + 1 < end and text[i + 1].isspace() and depth[i - start] == 0\n',
        '        if text[i] == "," and i + 1 < end and text[i + 1].isspace()  # mutant\n',
        P4_VERIFY_TEST,
        "test_a_number_comma_and_a_bracketed_comma_are_no_delimiters",
    ),
    (
        "p4 verify4: an unspaced dash pair is offered",
        P4_VERIFY,
        '        and text[i - 1] == " "\n',
        "        and True  # mutant\n",
        P4_VERIFY_TEST,
        "test_an_unspaced_dash_pair_is_not_offered",
    ),
    (
        "p4 verify4: a leading phrase of 7 tokens is offered",
        P4_VERIFY,
        "        if 1 <= len(tokens) <= 6 and first + 2 < final:\n",
        "        if 1 <= len(tokens) <= 7 and first + 2 < final:  # mutant\n",
        P4_VERIFY_TEST,
        "test_a_leading_phrase_is_at_most_six_tokens",
    ),
    (
        "p4 verify4: edit 2 keeps double spaces",
        P4_VERIFY,
        '    out = _SPACES.sub(" ", "".join(pieces))\n',
        '    out = "".join(pieces)  # mutant\n',
        P4_VERIFY_TEST,
        "test_the_edit_list_removes_repairs_restores_and_marks",
    ),
    (
        "p4 verify4: edit 3 keeps ' ,'",
        P4_VERIFY,
        '    out = out.replace(" ,", ",")\n',
        "    out = out  # mutant\n",
        P4_VERIFY_TEST,
        "test_the_edit_list_removes_repairs_restores_and_marks",
    ),
    (
        "p4 verify4: edit 4 restores no capital",
        P4_VERIFY,
        "    if drop and drop[0][0] == start and out[:1].islower():\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_the_edit_list_removes_repairs_restores_and_marks",
    ),
    (
        "p4 verify4: edit 5 puts the marker after the stop",
        P4_VERIFY,
        '    return f"{sentence[: match.start()]} [{n}]{sentence[match.start() :]}"\n',
        '    return f"{sentence} [{n}]"  # mutant\n',
        P4_VERIFY_TEST,
        "test_the_edit_list_removes_repairs_restores_and_marks",
    ),
    (
        "p4 verify4: the card speaks a bare c.",
        P4_VERIFY,
        '    return _CIRCA.sub(lambda m: "Circa " if m.group(1) == "C" else "circa ", text)\n',
        "    return text  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_the_card_speaks_circa_where_the_description_writes_c",
    ),
    (
        "p4 verify4: V1 a text that is not the pinned one passes",
        P4_VERIFY,
        "        if M.text_sha256(text) != pinned:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_a_text_that_is_not_the_pinned_one_is_held",
    ),
    (
        "p4 verify4: V1 a bool revision passes",
        P4_VERIFY,
        "    if type(revid) is not int or type(lastrevid) is not int:\n",
        "    if not isinstance(revid, int) or not isinstance(lastrevid, int):  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_a_revision_that_is_not_an_integer_is_held",
    ),
    (
        "p4 verify4: V1 a moved revision passes",
        P4_VERIFY,
        "    elif revid != lastrevid:\n",
        "    elif False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_a_revision_that_moved_is_held",
    ),
    (
        "p4 verify4: V1 any URL is a permalink",
        P4_VERIFY,
        "    if not is_permalink(permalink, lang=lang, revid=revid):\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_a_url_that_is_not_an_oldid_permalink_is_held",
    ),
    (
        "p4 verify4: V1 a permalink of another revision passes",
        P4_VERIFY,
        '        and query["oldid"] == [str(revid)]\n',
        "        and True  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_a_url_that_is_not_an_oldid_permalink_is_held",
    ),
    (
        "p4 verify4: V1 any licence publishes",
        P4_VERIFY,
        '    if meta.get("licence") != WIKIPEDIA_LICENCE.value:\n',
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_lanes_w_s_and_t_publish_only_from_cc_by_sa_wikipedia",
    ),
    (
        "p4 verify4: V1 a lane cites any kind",
        P4_VERIFY,
        "    if kinds != _LANE_KINDS[c.lane]:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_a_lane_that_cites_a_source_of_another_kind_is_held",
    ),
    (
        "p4 verify4: V1 the deny list is not asked",
        P4_VERIFY,
        "        if family is not None:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_a_restricted_page_on_the_deny_list_is_held",
    ),
    (
        "p4 verify4: V1 the attribution names any title",
        P4_VERIFY,
        "        if c.provenance.attribution.title != title:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v1_the_attribution_names_the_article_it_links",
    ),
    (
        "p4 verify4: V2 a quote need not be the slice",
        P4_VERIFY,
        '        if unicodedata.normalize("NFC", text[sentence.start : sentence.end]) != quote:\n',
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v2_a_quote_that_is_not_the_source_slice_is_held",
    ),
    (
        "p4 verify4: V2 quote_occurs is not asked",
        P4_VERIFY,
        "        if not DS.quote_occurs(quote, text):\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v2_a_quote_that_does_not_occur_in_the_text_is_held",
    ),
    (
        "p4 verify4: V2 a missing quote passes",
        P4_VERIFY,
        "    if len(c.quotes) != len(c.sentences):\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v2_every_published_sentence_needs_its_quote",
    ),
    (
        "p4 verify4: V3 a sentence that is not rebuilt passes",
        P4_VERIFY,
        '            elif want != got.body + f" [{got.n}]" + got.final:\n',
        "            elif False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v3_a_published_sentence_the_edit_list_does_not_rebuild_is_held",
    ),
    (
        "p4 verify4: V3 a description that does not split passes",
        P4_VERIFY,
        '    if c.published is None:\n        found = "no"',
        '    if False:  # mutant\n        found = "no"',
        P4_VERIFY_TEST,
        "test_v3_a_description_that_does_not_split_into_its_sentences_is_held",
    ),
    (
        "p4 verify4: V3 lane R may drop",
        P4_VERIFY,
        "            if sentence.drop:\n",
        "            if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v3_lane_r_drops_nothing_from_a_quote",
    ),
    (
        "p4 verify4: V4 any range may be dropped",
        P4_VERIFY,
        "        if (low, high) not in candidates:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v4_a_drop_that_is_not_an_offered_span_is_held",
    ),
    (
        "p4 verify4: V4 a protected token may be dropped",
        P4_VERIFY,
        "        hit = protected_in(text[low:high])\n",
        "        hit = ()  # mutant\n",
        P4_VERIFY_TEST,
        "test_v4_a_drop_that_removes_a_protected_token_is_held",
    ),
    (
        "p4 verify4: V4 a card keeps what its sentence dropped",
        P4_VERIFY,
        "            if not any(a <= low and high <= b for a, b in item.drop):\n",
        "            if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v4_a_card_that_keeps_a_span_its_sentence_dropped_is_held",
    ),
    (
        "p4 verify4: V5 any length passes",
        P4_VERIFY,
        "        if not SENTENCE_MIN <= len(text) <= SENTENCE_MAX:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v5_a_sentence_that_is_too_short_or_opens_small_is_held",
    ),
    (
        "p4 verify4: V5 a small opening passes",
        P4_VERIFY,
        "        if not _STARTS.match(first) or (first.isalpha() and not first.isupper()):\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v5_a_sentence_that_is_too_short_or_opens_small_is_held",
    ),
    (
        "p4 verify4: V5 an incomplete sentence passes",
        P4_VERIFY,
        "        if not is_complete_sentence(text):\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v5_a_sentence_that_ends_on_an_abbreviation_is_held",
    ),
    (
        "p4 verify4: V5 an artefact passes",
        P4_VERIFY,
        "            if pattern.search(text):\n",
        "            if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v5_an_extract_artefact_is_held",
    ),
    (
        "p4 verify4: V5 unbalanced quotes pass",
        P4_VERIFY,
        "        if not balanced(text):\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v5_unbalanced_quotes_are_held",
    ),
    (
        "p4 verify4: V6 a pronoun needs no predecessor",
        P4_VERIFY,
        "        if not adjacent:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v6_a_pronoun_without_its_source_predecessor_is_held",
    ),
    (
        "p4 verify4: V6 sentence 1 need not name the site",
        P4_VERIFY,
        "    if not any(name_in(name, first) for name in names):\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v6_the_first_sentence_must_name_the_site",
    ),
    (
        "p4 verify4: V6 the name match turns round",
        P4_VERIFY,
        "    if not needle or len(needle) > len(haystack):\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v6_the_name_match_is_directional",
    ),
    (
        "p4 verify4: V6 a weak own verdict lends its title",
        P4_VERIFY,
        '        and gate.get("km") is not None\n',
        "        and True  # mutant\n",
        P4_VERIFY_TEST,
        "test_v6_the_article_title_counts_only_for_a_strong_own_verdict",
    ),
    (
        "p4 verify4: V7 any verdict allows the lane",
        P4_VERIFY,
        "            if verdict != wanted.value:\n",
        "            if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v7_a_verdict_that_does_not_allow_the_lane_is_held",
    ),
    (
        "p4 verify4: V7 lane S publishes any sentence",
        P4_VERIFY,
        "    if c.lane is M.Lane.S and c.published is not None:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v7_lane_s_publishes_only_name_bearing_or_matching_section_sentences",
    ),
    (
        "p4 verify4: V7 the batch ignores the assigned lane",
        P4_VERIFY,
        "    if provenance.lane is not assignment.lane:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_the_batch_holds_a_site_whose_lane_is_not_the_assigned_one",
    ),
    (
        "p4 verify4: V8 a marker needs no citation",
        P4_VERIFY,
        "    if sorted(cited - set(declared)):\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v8_a_marker_without_a_citation_is_held",
    ),
    (
        "p4 verify4: V8 numbers need not follow first appearance",
        P4_VERIFY,
        "        if sentence.n != expected:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v8_citations_are_numbered_by_first_appearance",
    ),
    (
        "p4 verify4: V8 a citation may link another URL",
        P4_VERIFY,
        "        if citation.url != pinned:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v8_a_citation_must_link_the_pinned_permalink",
    ),
    (
        "p4 verify4: V9 any length passes",
        P4_VERIFY,
        "    if not DESCRIPTION_MIN <= length <= DESCRIPTION_MAX:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v9_a_description_that_is_too_short_or_under_the_floor_is_held",
    ),
    (
        "p4 verify4: V9 the stored-length floor is gone",
        P4_VERIFY,
        "    if length < STORED_FLOOR * stored and not (c.site.flags & FLOOR_WAIVERS):\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v9_a_description_that_is_too_short_or_under_the_floor_is_held",
    ),
    (
        "p4 verify4: V9 the floor is never waived",
        P4_VERIFY,
        "    if length < STORED_FLOOR * stored and not (c.site.flags & FLOOR_WAIVERS):\n",
        "    if length < STORED_FLOOR * stored:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v9_a_description_that_is_too_short_or_under_the_floor_is_held",
    ),
    (
        "p4 verify4: V10 any card length passes",
        P4_VERIFY,
        "    if not CARD_MIN <= len(card) <= CARD_MAX:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_card_out_of_its_length_is_held",
    ),
    (
        "p4 verify4: V10 a card need not be its items",
        P4_VERIFY,
        "    elif card != want:\n",
        "    elif False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_card_that_is_not_its_items_is_held",
    ),
    (
        "p4 verify4: V10 a card may carry a marker",
        P4_VERIFY,
        "    if T08.marker_sequence(card):\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_card_with_parentheses_or_a_marker_is_held",
    ),
    (
        "p4 verify4: V10 a card may carry parentheses",
        P4_VERIFY,
        '    if "(" in card or ")" in card:\n',
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_card_with_parentheses_or_a_marker_is_held",
    ),
    (
        "p4 verify4: V10 a card may name a country",
        P4_VERIFY,
        "    if named:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_card_that_names_a_country_is_held",
    ),
    (
        "p4 verify4: V10 a card may carry a superlative",
        P4_VERIFY,
        "    if found:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_card_with_an_evaluative_superlative_is_held",
    ),
    (
        "p4 verify4: V10 a card may open with a pronoun",
        P4_VERIFY,
        "        if text is not None and opens_with_pronoun(\n",
        "        if False and opens_with_pronoun(  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_card_opening_with_a_pronoun_is_held",
    ),
    (
        "p4 verify4: V10 a missing glyph passes",
        P4_VERIFY,
        "    if fit.missing:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_card_the_heading_font_cannot_draw_is_held",
    ),
    (
        "p4 verify4: V10 a word wider than the frame passes",
        P4_VERIFY,
        "    if fit.px > MAX_CAPTION_PX:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v10_a_caption_word_wider_than_the_frame_is_held",
    ),
    (
        "p4 verify4: V11 a new number passes",
        P4_VERIFY,
        "        if missing:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v11_a_translated_number_that_is_not_in_its_quote_is_held",
    ),
    (
        "p4 verify4: V11 a new capitalised word passes",
        P4_VERIFY,
        "        if absent:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v11_a_capitalised_word_that_is_not_in_its_quote_is_held",
    ),
    (
        "p4 verify4: V11 a flipped era passes",
        P4_VERIFY,
        "        if mention.marked and (mention.lo, mention.hi) not in wanted:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v11_a_restated_year_whose_era_flipped_is_held",
    ),
    (
        "p4 verify4: V11 claim_problems is not asked",
        P4_VERIFY,
        '        problems.extend(f"{where}: {p}" for p in DS.claim_problems([claim], {ref.url: page}))\n',
        "        pass  # mutant\n",
        P4_VERIFY_TEST,
        "test_v11_an_r_quote_that_is_not_on_its_page_is_held",
    ),
    (
        "p4 verify4: V11 an 8-word copy passes",
        P4_VERIFY,
        "        if tuple(words[i : i + NO_COPY_WORDS]) in runs:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v11_a_restatement_that_copies_eight_words_is_held",
    ),
    (
        "p4 verify4: V12 another key may change",
        P4_VERIFY,
        "    if changed:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v12_a_raw_data_that_changes_another_key_is_held",
    ),
    (
        "p4 verify4: V12 a key may be lost",
        P4_VERIFY,
        "    if set(new) != set(old) | replaced:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v12_a_raw_data_that_changes_another_key_is_held",
    ),
    (
        "p4 verify4: V12 empty citations pass",
        P4_VERIFY,
        "    if not citations:\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v12_empty_citations_would_let_the_boot_seed_fire",
    ),
    (
        "p4 verify4: V12 another provenance is written",
        P4_VERIFY,
        "    if new.get(M.PROVENANCE_KEY) != c.provenance.to_dict():\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v12_the_provenance_written_is_the_assemblys",
    ),
    (
        "p4 verify4: V13 any desc_sha256 passes",
        P4_VERIFY,
        "    if c.provenance.desc_sha256 != M.text_sha256(c.assembly.description):\n",
        "    if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v13_a_description_hash_that_is_not_its_text_is_held",
    ),
    (
        "p4 verify4: V13 any card hash passes",
        P4_VERIFY,
        "    elif card is not None and pinned is not None and pinned.text_sha256 != M.text_sha256(card):\n",
        "    elif False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v13_a_card_hash_that_is_not_its_card_is_held",
    ),
    (
        "p4 verify4: V14 a severe T03 date passes",
        P4_VERIFY,
        "        if finding.severity is Severity.SEVERE:\n",
        "        if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v14_a_severe_t03_date_in_the_new_text_is_held",
    ),
    (
        "p4 verify4: V14 another country passes",
        P4_VERIFY,
        "            if not same:\n",
        "            if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v14_a_location_sentence_naming_another_country_is_held",
    ),
    (
        "p4 verify4: V15 an injection tell passes",
        P4_VERIFY,
        "            if tell.search(text):\n",
        "            if False:  # mutant\n",
        P4_VERIFY_TEST,
        "test_v15_an_injection_tell_is_held",
    ),
    (
        "p4 verify4: the batch keeps stale V holds",
        P4_VERIFY,
        "            if reason not in V_REASONS:\n",
        "            if True:  # mutant\n",
        P4_VERIFY_TEST,
        "test_the_batch_verifies_from_the_store_and_replaces_only_its_own_holds",
    ),
    (
        "p4 verify4: the batch reads the text in text mode",
        P4_VERIFY,
        '    text = text_path.read_bytes().decode("utf-8") if text_path.exists() else None\n',
        '    text = text_path.read_text(encoding="utf-8") if text_path.exists() else None  # mutant\n',
        P4_VERIFY_TEST,
        "test_the_batch_reads_the_text_as_bytes_not_as_translated_lines",
    ),
    (
        "p4 verify4: V14 holds reach no field_conflicts report",
        P4_VERIFY,
        "    conflicts = [hold for hold in found if hold.reason is M.HoldReason.V14]\n",
        "    conflicts: list[M.Hold] = []  # mutant\n",
        P4_VERIFY_TEST,
        "test_the_batch_writes_v14_holds_to_the_field_conflicts_report",
    ),
    (
        "p4 verify_writes4: raw_data compared as text",
        P4_ACCEPT,
        "        return json.dumps(parsed, ensure_ascii=False, sort_keys=True)\n",
        "        return value if isinstance(value, str) else json.dumps(parsed)  # mutant\n",
        P4_ACCEPT_TEST,
        "test_raw_data_is_compared_as_json_not_as_postgres_text",
    ),
    (
        "p4 verify_writes4: a moved unwritten row passes",
        P4_ACCEPT,
        '        elif live.get(key) != canonical(key[0], key[1], row["old_value"]):\n',
        "        elif False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_planned_row_the_lane_has_not_written_yet_must_hold_its_old_value",
    ),
    (
        "p4 verify_writes4: --complete accepts an unwritten row",
        P4_ACCEPT,
        "        elif complete:\n",
        "        elif False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_planned_row_the_lane_has_not_written_yet_must_hold_its_old_value",
    ),
    (
        "p4 verify_writes4: another value than the plan passes",
        P4_ACCEPT,
        "                if (link.old, link.new) != want:\n",
        "                if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_lane_row_with_another_value_than_the_plan_is_a_deviation",
    ),
    (
        "p4 verify_writes4: a row written twice passes",
        P4_ACCEPT,
        "        if len(links) > 1:\n",
        "        if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_row_written_twice_or_changed_later_is_a_deviation",
    ),
    (
        "p4 verify_writes4: a later change passes",
        P4_ACCEPT,
        "            if later:\n",
        "            if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_row_written_twice_or_changed_later_is_a_deviation",
    ),
    (
        "p4 verify_writes4: a write outside the lane passes",
        P4_ACCEPT,
        "        if (link.table, link.column) not in columns:\n",
        "        if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_lane_row_outside_the_plan_or_the_lanes_columns_is_a_deviation",
    ),
    (
        "p4 verify_writes4: a write outside the plan passes",
        P4_ACCEPT,
        '            result.deviations.append(f"OUTSIDE THE PLAN {where}: journalled, never planned")\n',
        "            pass  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_lane_row_outside_the_plan_or_the_lanes_columns_is_a_deviation",
    ),
    (
        "p4 verify_writes4: a missing site passes",
        P4_ACCEPT,
        "        if (key[0], key[2]) not in present:\n",
        "        if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_planned_site_missing_from_the_database_is_a_deviation",
    ),
    (
        "p4 verify_writes4: the chain is not judged",
        P4_ACCEPT,
        "        problems, _ = VW.check_chain(\n            key, chain, live.get(key), missing=(key[0], key[2]) not in present\n        )\n",
        "        problems: list[str] = []  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_live_value_that_is_not_the_chains_last_is_a_deviation",
    ),
    (
        "p4 verify_writes4: journal offsets are not compared",
        P4_ACCEPT,
        '        if (entry.get("start"), entry.get("end")) != (sentence.start, sentence.end):\n',
        "        if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_journal_evidence_without_quotes_or_with_other_offsets_is_a_deviation",
    ),
    (
        "p4 verify_writes4: the store's slices replace the journal quotes",
        P4_ACCEPT,
        "            entry.site, assembly, metas=metas, texts=texts, quotes=quotes, new_raw_data=raw\n",
        "            entry.site, assembly, metas=metas, texts=texts, new_raw_data=raw,  # mutant\n            quotes=[texts[s.src][s.start : s.end] for s in provenance.sentences],\n",
        P4_ACCEPT_TEST,
        "test_the_journal_quotes_are_the_ones_verified",
    ),
    (
        "p4 verify_writes4: a verifier hold is not reported",
        P4_ACCEPT,
        '                f"REVERIFY {site_id} {hold.reason.value} ({hold.scope.value}): {hold.detail}"\n',
        '                f"(mutant) {hold.reason.value}"\n',
        P4_ACCEPT_TEST,
        "test_a_written_site_that_no_longer_verifies_is_a_deviation",
    ),
    (
        "p4 verify_writes4: the description invariant is not read",
        P4_ACCEPT,
        '        if lane in ("p4", "p4l") and row["desc_invariant"] is not True:\n',
        "        if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_the_in_database_invariants_are_postgres_own",
    ),
    (
        "p4 verify_writes4: the card invariant is not read",
        P4_ACCEPT,
        '            and row["card_invariant"] is not True\n',
        "            and False  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_card_that_is_not_the_pinned_one_fails_the_p5_invariant",
    ),
    (
        "p4 verify_writes4: the legacy provenance is not read",
        P4_ACCEPT,
        '                M.LegacyProvenance.from_dict(row["raw_data"][M.PROVENANCE_KEY])\n',
        "                pass  # mutant\n",
        P4_ACCEPT_TEST,
        "test_a_legacy_provenance_that_does_not_read_is_a_deviation",
    ),
    (
        "p4 verify_writes4: T08 is not run",
        P4_ACCEPT,
        "        for finding in T08.run(_Sites(sites))\n",
        "        for finding in []  # mutant\n",
        P4_ACCEPT_TEST,
        "test_t08_runs_over_the_written_sites",
    ),
    (
        "p4 verify_writes4: a failing card check passes",
        P4_ACCEPT,
        "    if code != 0:\n",
        "    if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_the_card_file_check_reads_the_tools_own_exit_line",
    ),
    (
        "p4 verify_writes4: the first exit line is read",
        P4_ACCEPT,
        "    return codes[-1] if codes else None\n",
        "    return codes[0] if codes else None  # mutant\n",
        P4_ACCEPT_TEST,
        "test_the_card_file_check_reads_the_tools_own_exit_line",
    ),
    (
        "p4 verify_writes4: an overwrite line passes",
        P4_ACCEPT,
        "        if count:\n",
        "        if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_the_boot_logs_of_both_containers_carry_no_overwrite",
    ),
    (
        "p4 verify_writes4: a failed docker logs passes",
        P4_ACCEPT,
        "        if status != 0:\n",
        "        if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_the_boot_logs_of_both_containers_carry_no_overwrite",
    ),
    (
        "p4 verify_writes4: any --since reaches the remote shell",
        P4_ACCEPT,
        "    if not _INSTANT.fullmatch(since):\n",
        "    if False:  # mutant\n",
        P4_ACCEPT_TEST,
        "test_the_boot_log_instant_is_checked_before_it_reaches_a_remote_shell",
    ),
    (
        "p4 verify_writes4: the live read scans the whole table",
        P4_ACCEPT,
        '        f"WHERE u.id IN ({_uuids(pks)})) t;\\n"\n',
        '        f"WHERE u.id::text IN ({lanes.sql_literals(pks)})) t;\\n"  # mutant\n',
        P4_ACCEPT_TEST,
        "test_the_live_read_uses_the_key_columns_own_type",
    ),
    (
        "p4 shorts_audit: S13 passes any card",
        SHORTS_AUDIT,
        '            pinned is not None and m["card_sha256"] == pinned,\n',
        "            True,  # mutant\n",
        SHORTS_TEST,
        "test_s13_a_card_that_is_not_the_pinned_one_fails",
    ),
    (
        "p4 shorts_audit: S13 passes a card without provenance",
        SHORTS_AUDIT,
        '            pinned is not None and m["card_sha256"] == pinned,\n',
        '            pinned is None or m["card_sha256"] == pinned,  # mutant\n',
        SHORTS_TEST,
        "test_s13_a_card_without_card_provenance_is_not_shorts_eligible",
    ),
    (
        "p4 shorts_audit: a caption word is measured with its punctuation",
        SHORTS_AUDIT,
        "        shown = display_text(word)\n",
        "        shown = word  # mutant\n",
        SHORTS_TEST,
        "test_the_widest_word_is_measured_as_shown_with_its_outline",
    ),
    (
        "p4 shorts_audit: the caption audit measures on its own",
        SHORTS_AUDIT,
        '    return widest_word_px((word["text"] for word in captions), caption_font(font_path))\n',
        '    return "", 0  # mutant\n',
        SHORTS_TEST,
        "test_the_caption_audit_measures_through_the_public_helper",
    ),
    (
        "p4 shorts_export: site.json drops the pinned card hash",
        SHORTS_EXPORT,
        '        "card_text_sha256": row["card_text_sha256"],\n',
        '        "card_text_sha256": None,  # mutant\n',
        SHORTS_TEST,
        "test_s13_the_export_carries_the_pinned_hash_into_site_json",
    ),
]
MUTATIONS += GAP_MUTATIONS
MUTATIONS += REVIEW_MUTATIONS
MUTATIONS += SPLIT_MUTATIONS
MUTATIONS += PHASE4_MODEL_MUTATIONS
MUTATIONS += PHASE4_VERIFY_MUTATIONS


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
