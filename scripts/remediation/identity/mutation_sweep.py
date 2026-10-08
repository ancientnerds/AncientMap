"""Mutation sweep for the identity discovery: every guard must be able to fail.

The machinery is `mechanical/mutation_sweep.py`'s (a case counts as FIRED only when its needle occurs
exactly once, the mutant compiles, the named test passed on the unmutated file and is reported
FAILED against the mutant - anything else fails the sweep). Only the cases are this package's:
one per guard of `scripts/remediation/identity/`, each naming the one test that must notice.

Run it from a parent process on a clean committed tree, never from inside a subagent lane (a lane
killed between applying a mutation and restoring it leaves the mutant behind):

    ./.venv/Scripts/python.exe scripts/remediation/identity/mutation_sweep.py            # all
    ./.venv/Scripts/python.exe scripts/remediation/identity/mutation_sweep.py funnel     # by label

`git status` must be clean afterwards: the sweep restores every file and checks its sha256.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical.mutation_sweep import REPO, Case, guard, main  # noqa: E402

IDENTITY = REPO / "scripts/remediation/identity"
COMMON = IDENTITY / "common.py"
ENTITIES = IDENTITY / "entities.py"
EXPORT = IDENTITY / "export.py"
FUNNEL = IDENTITY / "funnel.py"
DUPS = IDENTITY / "dup_clusters.py"
NAMES = IDENTITY / "names_triage.py"
SCOPE = IDENTITY / "scope_window.py"
PARENTS = IDENTITY / "parents.py"

T_EXPORT = "tests/remediation/test_identity_export.py"
T_FUNNEL = "tests/remediation/test_identity_funnel.py"
T_DUPS = "tests/remediation/test_identity_dups.py"
T_NAMES = "tests/remediation/test_identity_names.py"
T_SCOPE = "tests/remediation/test_identity_scope_parents.py"


def swap(label: str, path: Path, old: str, new: str, test: str, testfile: str) -> Case:
    return Case(label, path, old, new, test, testfile)


CASES: list[Case] = [
    # ------------------------------------------------------------------------------ common
    guard(
        "rows with one id",
        COMMON,
        "    if len(by_id) != len(rows):",
        "test_two_rows_with_one_id_are_refused",
        T_EXPORT,
    ),
    # ------------------------------------------------------------------------------ export
    swap(
        "read-only session",
        EXPORT,
        "    return QUIET + READ_ONLY_SET + script[len(QUIET) :]",
        "    return script",
        "test_the_script_sets_the_session_read_only_before_anything_runs",
        T_EXPORT,
    ),
    guard(
        "tagged export starts quiet",
        EXPORT,
        "    if not script.startswith(QUIET):",
        "test_a_tagged_export_that_no_longer_starts_quiet_is_refused",
        T_EXPORT,
    ),
    guard(
        "export without shown site",
        EXPORT,
        '    if not rows["shown"]:',
        "test_an_export_without_a_shown_site_is_refused_not_read_as_empty",
        T_EXPORT,
    ),
    guard(
        "ids of one kind",
        EXPORT,
        '        if row["kind"] == kind:',
        "test_qids_and_titles_are_grouped_per_site_in_the_tables_order",
        T_EXPORT,
    ),
    # ---------------------------------------------------------------------------- entities
    guard(
        "delta classes seeded",
        ENTITIES,
        "    if not classes.exists():",
        "test_the_fetch_asks_only_for_the_items_neither_root_holds_and_seeds_the_classes",
        T_EXPORT,
    ),
    guard(
        "nothing missing opens no fetcher",
        ENTITIES,
        "    if not wanted:",
        "test_nothing_missing_means_no_fetcher_is_opened",
        T_EXPORT,
    ),
    swap(
        "delta after harvest",
        ENTITIES,
        "        self.roots = ((SOURCE_HARVEST, harvest_root), (SOURCE_DELTA, delta_root))",
        "        self.roots = ((SOURCE_DELTA, delta_root), (SOURCE_HARVEST, harvest_root))",
        "test_a_harvested_item_is_found_in_the_harvest",
        T_EXPORT,
    ),
    # ------------------------------------------------------------------------------ funnel
    swap(
        "ancient class is not modern",
        FUNNEL,
        "    return bool(SETTLEMENT.search(label) and MODERN.search(label) and not NOT_MODERN.search(label))",
        "    return bool(SETTLEMENT.search(label) and MODERN.search(label))",
        "test_an_ancient_settlement_class_is_not_modern",
        T_FUNNEL,
    ),
    swap(
        "modern class is a settlement",
        FUNNEL,
        "    return bool(SETTLEMENT.search(label) and MODERN.search(label) and not NOT_MODERN.search(label))",
        "    return bool(MODERN.search(label) and not NOT_MODERN.search(label))",
        "test_the_settlement_cut_comes_first_a_resort_is_not_a_settlement_class",
        T_FUNNEL,
    ),
    swap(
        "modern class is not archaeological",
        FUNNEL,
        "label for label in labels if ARCHAEOLOGICAL.search(label) and label not in modern",
        "label for label in labels if ARCHAEOLOGICAL.search(label)",
        "test_a_modern_class_is_never_also_archaeological",
        T_FUNNEL,
    ),
    swap(
        "tier B has an archaeological class",
        FUNNEL,
        '        p31_tier = ("B" if archaeological else "A") if modern else None',
        '        p31_tier = "A" if modern else None',
        "test_a_village_that_is_also_an_archaeological_site_is_tier_b",
        T_FUNNEL,
    ),
    guard(
        "tier A+rx",
        FUNNEL,
        '    if p31_tier == "A" and opening:',
        "test_a_modern_class_with_an_opening_is_the_first_tier",
        T_FUNNEL,
    ),
    guard(
        "tier B+rx",
        FUNNEL,
        '    if p31_tier == "B" and opening:',
        "test_a_modern_class_with_an_opening_is_the_first_tier",
        T_FUNNEL,
    ),
    guard(
        "tier A",
        FUNNEL,
        '    if p31_tier == "A":',
        "test_each_signal_alone_has_its_own_tier",
        T_FUNNEL,
    ),
    guard(
        "tier rx",
        FUNNEL,
        "    if opening:",
        "test_each_signal_alone_has_its_own_tier",
        T_FUNNEL,
    ),
    guard(
        "tier B",
        FUNNEL,
        '    if p31_tier == "B":',
        "test_each_signal_alone_has_its_own_tier",
        T_FUNNEL,
    ),
    guard(
        "tier shared_qid",
        FUNNEL,
        "    if shared:",
        "test_each_signal_alone_has_its_own_tier",
        T_FUNNEL,
    ),
    guard(
        "item missing is counted",
        FUNNEL,
        "            if entity is None:",
        "test_a_site_whose_item_no_root_holds_is_counted_not_guessed",
        T_FUNNEL,
    ),
    swap(
        "pure opening has no cue",
        FUNNEL,
        "        pure = bool(opened) and not OPENING_ARCHAEOLOGICAL.search(sentence)",
        "        pure = bool(opened)",
        "test_an_opening_that_names_an_ancient_cue_is_not_a_pure_opening",
        T_FUNNEL,
    ),
    swap(
        "site not shared with itself",
        FUNNEL,
        "for o in holders[q]} - {site_id})",
        "for o in holders[q]})",
        "test_a_site_is_never_shared_with_itself",
        T_FUNNEL,
    ),
    swap(
        "funnel ordered by tier",
        FUNNEL,
        '            TIERS.index(r["tier"]),',
        "            0,",
        "test_the_records_are_ordered_by_tier_first",
        T_FUNNEL,
    ),
    # ------------------------------------------------------------------------------- dups
    guard(
        "distance band limit",
        DUPS,
        "        if metres <= limit:",
        "test_the_distance_band_is_the_first_limit_not_exceeded",
        T_DUPS,
    ),
    swap(
        "union joins clusters",
        DUPS,
        "            self.parent[self.find(other)] = root",
        "            pass",
        "test_edges_that_share_a_site_make_one_cluster",
        T_DUPS,
    ),
    guard(
        "article held once",
        DUPS,
        "        if len(sites) < 2:",
        "test_an_article_held_once_is_no_edge",
        T_DUPS,
    ),
    guard(
        "article under one item",
        DUPS,
        "        if len(items) > 1:",
        "test_a_shared_article_under_one_item_is_left_to_the_shared_item",
        T_DUPS,
    ),
    swap(
        "owner-case classes",
        DUPS,
        '    return [r for r in common.read_jsonl(path) if r["class"] in BCASES_CLASSES]',
        "    return [r for r in common.read_jsonl(path)]",
        "test_only_the_dup_and_part_of_pairs_of_the_owner_cases_count",
        T_DUPS,
    ),
    guard(
        "owner-case pair not shown",
        DUPS,
        '        if pair["a"] not in shown or pair["b"] not in shown:',
        "test_an_owner_case_pair_with_a_retired_site_is_counted_and_left_out",
        T_DUPS,
    ),
    swap(
        "members by age",
        DUPS,
        'key=lambda r: (r["created_at"], r["id"]))\n        distances',
        'key=lambda r: (r["created_at"], r["id"]), reverse=True)\n        distances',
        "test_the_members_are_ordered_by_age_then_id",
        T_DUPS,
    ),
    swap(
        "clusters largest first",
        DUPS,
        'records.sort(key=lambda r: (-r["size"], r["cluster_id"]))',
        'records.sort(key=lambda r: (r["size"], r["cluster_id"]))',
        "test_the_clusters_come_largest_first",
        T_DUPS,
    ),
    swap(
        "loser holds something",
        DUPS,
        '        if loser["images"] > 0 or loser["links"] > 0\n',
        "        if True\n",
        "test_a_loser_that_holds_nothing_is_not_listed",
        T_DUPS,
    ),
    swap(
        "loser holds links",
        DUPS,
        '        if loser["images"] > 0 or loser["links"] > 0\n',
        '        if loser["images"] > 0\n',
        "test_a_loser_that_holds_images_or_links_is_listed_with_what_it_holds",
        T_DUPS,
    ),
    swap(
        "survivor retired counted",
        DUPS,
        '1 for r in exported.losers if r["survivor_scope_status"] == "retired"',
        '0 for r in exported.losers if r["survivor_scope_status"] == "retired"',
        "test_a_loser_whose_survivor_is_retired_too_is_counted",
        T_DUPS,
    ),
    # ------------------------------------------------------------------------------ names
    swap(
        "modifier letter is a letter",
        NAMES,
        '    if not char.isalpha() or unicodedata.category(char) == "Lm":',
        "    if not char.isalpha():",
        "test_a_modifier_letter_is_neither_mixed_nor_non_latin",
        T_NAMES,
    ),
    guard(
        "defect non-latin",
        NAMES,
        "    if not is_latin(name):",
        "test_a_name_in_another_script_is_non_latin",
        T_NAMES,
    ),
    guard(
        "defect mixed script",
        NAMES,
        "    if any(len(scripts_of(word)) > 1 for word in name.split()):",
        "test_a_greek_letter_inside_a_latin_word_is_a_mixed_script",
        T_NAMES,
    ),
    guard(
        "defect whitespace",
        NAMES,
        "    if WHITESPACE_ARTIFACT.search(name):",
        "test_a_double_space_and_a_zero_width_character_are_whitespace_artifacts",
        T_NAMES,
    ),
    guard(
        "defect all caps",
        NAMES,
        "    if name.isupper() and len(name) > 3:",
        "test_a_name_in_capitals_is_a_defect_but_a_short_one_is_not",
        T_NAMES,
    ),
    guard(
        "defect mojibake",
        NAMES,
        "    if MOJIBAKE.search(name):",
        "test_mojibake_is_a_defect",
        T_NAMES,
    ),
    guard(
        "defect digit",
        NAMES,
        '    if re.search(r"\\d", name):',
        "test_a_digit_is_a_defect",
        T_NAMES,
    ),
    guard(
        "defect parenthesis",
        NAMES,
        '    if re.search(r"\\(.*\\)", name):',
        "test_a_parenthesis_is_a_defect",
        T_NAMES,
    ),
    guard(
        "defect foreign prefix",
        NAMES,
        "    if FOREIGN_PREFIX.match(name):",
        "test_a_foreign_prefix_is_a_defect",
        T_NAMES,
    ),
    guard(
        "defect comma",
        NAMES,
        '    if "," in name:',
        "test_a_comma_qualifier_is_a_defect",
        T_NAMES,
    ),
    guard(
        "defect long",
        NAMES,
        "    if len(name) > LONG_NAME_CHARS:",
        "test_a_name_longer_than_forty_characters_is_long",
        T_NAMES,
    ),
    guard(
        "label note needs a label",
        NAMES,
        "    if not label:",
        "test_an_item_without_a_label_has_nothing_to_differ_from",
        T_NAMES,
    ),
    swap(
        "suggestion is attested",
        NAMES,
        "is_latin(repaired) and repaired.casefold() in attested:",
        "is_latin(repaired):",
        "test_a_homoglyph_is_repaired_only_to_an_attested_form",
        T_NAMES,
    ),
    swap(
        "suggestion changes the name",
        NAMES,
        "if repaired and repaired != name and is_latin(repaired)",
        "if repaired and is_latin(repaired)",
        "test_a_name_that_is_already_attested_needs_no_suggestion",
        T_NAMES,
    ),
    guard(
        "clean name has no triage",
        NAMES,
        "    if not found:",
        "test_a_defective_site_is_flagged_for_a_model_only_without_a_suggestion",
        T_NAMES,
    ),
    swap(
        "regnal numeral stays",
        NAMES,
        'TRAILING_NUMERAL = re.compile(r"\\s+\\d+[a-z]?\\s*$")',
        'TRAILING_NUMERAL = re.compile(r"\\s+(?:\\d+[a-z]?|[IVX]+)\\s*$")',
        "test_a_regnal_numeral_is_part_of_the_name",
        T_NAMES,
    ),
    swap(
        "droppable words only",
        NAMES,
        "set(kept) <= set(original) and dropped <= DROPPABLE",
        "set(kept) <= set(original)",
        "test_a_shorter_form_that_leaves_out_a_place_word_is_refused",
        T_NAMES,
    ),
    swap(
        "no word added",
        NAMES,
        "bool(dropped) and set(kept) <= set(original) and dropped <= DROPPABLE",
        "bool(dropped) and dropped <= DROPPABLE",
        "test_a_form_that_adds_a_word_while_dropping_a_kind_is_refused",
        T_NAMES,
    ),
    swap(
        "distinctive word kept",
        NAMES,
        "    return max(left - GENERIC or left, key=lambda t: (len(t), t)) in right",
        "    return True",
        "test_a_form_without_the_names_distinctive_word_does_not_stand_for_it",
        T_NAMES,
    ),
    swap(
        "kind is not distinctive",
        NAMES,
        "    return max(left - GENERIC or left, key=lambda t: (len(t), t)) in right",
        "    return max(left, key=lambda t: (len(t), t)) in right",
        "test_the_kind_of_the_thing_is_not_its_distinctive_word",
        T_NAMES,
    ),
    guard(
        "overlap threshold",
        NAMES,
        "    if not left or not right or len(left & right) / len(left | right) < COMPATIBLE:",
        "test_a_form_that_shares_too_few_words_does_not_stand_for_it",
        T_NAMES,
    ),
    guard(
        "residual non-latin",
        NAMES,
        "    if not is_latin(text):",
        "test_a_name_in_another_script_is_not_spoken_by_rule",
        T_NAMES,
    ),
    guard(
        "residual mixed script",
        NAMES,
        "    if any(len(scripts_of(word)) > 1 for word in text.split()):",
        "test_a_mixed_script_name_is_not_spoken_by_rule",
        T_NAMES,
    ),
    guard(
        "residual digit",
        NAMES,
        '    if re.search(r"\\d", text):',
        "test_a_name_with_a_digit_inside_needs_a_model",
        T_NAMES,
    ),
    guard(
        "residual foreign prefix",
        NAMES,
        "    if FOREIGN_PREFIX.match(text):",
        "test_a_foreign_prefix_is_not_spoken_by_rule",
        T_NAMES,
    ),
    guard(
        "residual too long",
        NAMES,
        "    if len(text) > SPOKEN_MAX_CHARS:",
        "test_a_name_over_forty_characters_needs_a_model",
        T_NAMES,
    ),
    guard(
        "residual too short",
        NAMES,
        "    if len(text) < SPOKEN_MIN_CHARS:",
        "test_a_name_that_is_too_short_needs_a_model",
        T_NAMES,
    ),
    guard(
        "residual generic",
        NAMES,
        "    if text.casefold() in GENERIC:",
        "test_a_name_of_one_generic_word_needs_a_model",
        T_NAMES,
    ),
    guard(
        "residual capitals",
        NAMES,
        "    if text.isupper() and len(text) > SPOKEN_MIN_CHARS:",
        "test_a_form_in_capitals_is_not_spoken",
        T_NAMES,
    ),
    guard(
        "step whitespace",
        NAMES,
        "    if text != name:",
        "test_a_clean_name_is_spoken_as_it_is",
        T_NAMES,
    ),
    guard(
        "step qualifier",
        NAMES,
        "    if stripped != text:",
        "test_a_clean_name_is_spoken_as_it_is",
        T_NAMES,
    ),
    guard(
        "step numeral",
        NAMES,
        "    if numberless != stripped:",
        "test_a_clean_name_is_spoken_as_it_is",
        T_NAMES,
    ),
    guard(
        "clean name is an option",
        NAMES,
        "    if clean:",
        "test_a_clean_name_is_spoken_as_it_is",
        T_NAMES,
    ),
    guard(
        "defective form skipped",
        NAMES,
        "        if form == cleaned or residual_defects(form):",
        "test_a_form_in_capitals_is_not_spoken",
        T_NAMES,
    ),
    guard(
        "an option is chosen",
        NAMES,
        "    if options:",
        "test_a_clean_name_is_spoken_as_it_is",
        T_NAMES,
    ),
    guard(
        "own label is not an alias",
        NAMES,
        '        if entry["name_type"] == "label":',
        "test_the_forms_come_from_the_item_the_names_table_and_the_article",
        T_NAMES,
    ),
    guard(
        "missing item in names",
        NAMES,
        "            if entity is None:",
        "test_a_missing_item_is_counted_and_the_name_is_still_triaged",
        T_NAMES,
    ),
    swap(
        "hard defects first",
        NAMES,
        'triage.sort(key=lambda r: (r["severity"] != "hard", r["name"].casefold(), r["id"]))',
        'triage.sort(key=lambda r: (r["name"].casefold(), r["id"]))',
        "test_the_hard_defects_come_before_the_comma_only_ones",
        T_NAMES,
    ),
    swap(
        "comma only severity",
        NAMES,
        '"severity": "comma_only" if found == ["comma_qualifier"] else "hard",',
        '"severity": "hard",',
        "test_a_site_with_only_a_comma_is_comma_only",
        T_NAMES,
    ),
    # ------------------------------------------------------------------------------ scope
    guard(
        "stamp family fields",
        SCOPE,
        "    if fields:",
        "test_a_field_lane_stamp_is_its_lane",
        T_SCOPE,
    ),
    guard(
        "stamp family phase three",
        SCOPE,
        '    if run_stamp.startswith("phase3:"):',
        "test_a_phase_three_chunk_is_phase3",
        T_SCOPE,
    ),
    swap(
        "date used",
        SCOPE,
        '    return row["period_end"] if row["period_end"] else row["period_start"]',
        '    return row["period_end"]',
        "test_an_end_of_zero_or_none_falls_through_to_the_start",
        T_SCOPE,
    ),
    guard(
        "group outside window",
        SCOPE,
        '    if row["outside_window"]:',
        "test_the_sql_windows_verdict_is_trusted_not_recomputed",
        T_SCOPE,
    ),
    guard(
        "group pending",
        SCOPE,
        '    if row["scope_status"] == "pending":',
        "test_a_pending_site_is_in_the_population_inside_the_window_too",
        T_SCOPE,
    ),
    guard(
        "group footpath",
        SCOPE,
        '    if row["id"].startswith(export.HADRIANS_WALL_PATH_PREFIX):',
        "test_a_site_inside_the_window_is_not_in_the_population",
        T_SCOPE,
    ),
    guard(
        "footpath pinned",
        SCOPE,
        '    if len(hadrian) != 1 or hadrian[0]["name"] != HADRIANS_WALL_PATH_NAME:',
        "test_the_footpath_must_be_exactly_one_site_with_the_pinned_name",
        T_SCOPE,
    ),
    guard(
        "population only",
        SCOPE,
        "        if not found:",
        "test_a_site_inside_the_window_is_not_in_the_population",
        T_SCOPE,
    ),
    swap(
        "import origin",
        SCOPE,
        '        origin = start["family"] if start else ORIGIN_IMPORT',
        '        origin = start["family"]',
        "test_a_period_the_journal_never_touched_is_an_import",
        T_SCOPE,
    ),
    swap(
        "recheck wd4",
        SCOPE,
        'RECHECK_FAMILIES = ("fields-wd3", "fields-wd4")',
        'RECHECK_FAMILIES = ("fields-wd3",)',
        "test_a_wd3_or_wd4_period_is_rechecked_first_and_a_wd1_one_is_not",
        T_SCOPE,
    ),
    swap(
        "recheck not wd1",
        SCOPE,
        'RECHECK_FAMILIES = ("fields-wd3", "fields-wd4")',
        'RECHECK_FAMILIES = ("fields-wd1", "fields-wd3", "fields-wd4")',
        "test_a_wd3_or_wd4_period_is_rechecked_first_and_a_wd1_one_is_not",
        T_SCOPE,
    ),
    swap(
        "museum question",
        SCOPE,
        '"museum_question": row["site_type"] == "Museum",',
        '"museum_question": False,',
        "test_a_museum_is_flagged_for_the_museum_question",
        T_SCOPE,
    ),
    # ---------------------------------------------------------------------------- parents
    guard(
        "latitude reach",
        PARENTS,
        '            if b["lat"] - a["lat"] > reach:',
        "test_the_sweep_stops_at_the_latitude_reach",
        T_SCOPE,
    ),
    guard(
        "same country",
        PARENTS,
        '            if a["country"] != b["country"]:',
        "test_two_countries_are_not_a_pair",
        T_SCOPE,
    ),
    swap(
        "strict subset",
        PARENTS,
        "            if not left or not right or left == right or not (left < right or right < left):",
        "            if not left or not right or left == right:",
        "test_names_that_merely_overlap_are_not_a_pair",
        T_SCOPE,
    ),
    swap(
        "equal words",
        PARENTS,
        "            if not left or not right or left == right or not (left < right or right < left):",
        "            if not left or not right or not (left < right or right < left):",
        "test_names_with_the_same_significant_words_are_not_a_pair",
        T_SCOPE,
    ),
    guard(
        "two kilometres",
        PARENTS,
        "            if metres > MAX_METRES:",
        "test_more_than_two_kilometres_apart_is_not_a_pair",
        T_SCOPE,
    ),
    swap(
        "shorter name is the parent",
        PARENTS,
        "            pairs.append((metres, a, b) if left < right else (metres, b, a))",
        "            pairs.append((metres, a, b))",
        "test_the_shorter_name_is_the_parent_of_the_longer_one",
        T_SCOPE,
    ),
    swap(
        "pairs by distance",
        PARENTS,
        '    return sorted(pairs, key=lambda p: (p[0], p[1]["id"], p[2]["id"]))',
        '    return sorted(pairs, key=lambda p: (p[1]["id"], p[2]["id"]))',
        "test_the_pairs_are_ordered_by_distance",
        T_SCOPE,
    ),
    swap(
        "children share an item",
        PARENTS,
        '"shared_qid": bool(',
        '"shared_qid": not bool(',
        "test_the_parent_record_lists_its_children_nearest_first_with_the_flags",
        T_SCOPE,
    ),
    swap(
        "parent is a child",
        PARENTS,
        '"parent_is_child": parent_id in parents_of,',
        '"parent_is_child": False,',
        "test_a_chain_is_flagged_and_a_child_with_two_parents_is_flagged",
        T_SCOPE,
    ),
]


if __name__ == "__main__":
    # `mutation_sweep.py [label substring ...]` runs the cases whose label holds any of them.
    wanted = [c for c in CASES if not sys.argv[1:] or any(a in c.label for a in sys.argv[1:])]
    if not wanted:
        sys.exit(f"no case label contains any of {sys.argv[1:]}")
    sys.exit(main(wanted))
