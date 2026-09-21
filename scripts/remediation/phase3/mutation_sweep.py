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
TORN_JSON = "test_a_truncated_model_json_is_broken_and_never_done"
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
]


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
