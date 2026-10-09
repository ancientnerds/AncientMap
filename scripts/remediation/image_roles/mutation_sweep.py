"""Mutation sweep for the image lanes' new guards (D15, D17, D18 of 2026-10-08).

The machinery is `mechanical/mutation_sweep.py`'s (a case counts as FIRED only when its needle occurs
exactly once, the mutant compiles, the named test passed on the unmutated file and is reported
FAILED against the mutant - anything else fails the sweep). Only the cases are this package's.

Run it from a parent process on a clean committed tree, never from inside a subagent lane (a lane
killed between applying a mutation and restoring it leaves the mutant behind):

    ./.venv/Scripts/python.exe scripts/remediation/image_roles/mutation_sweep.py            # all
    ./.venv/Scripts/python.exe scripts/remediation/image_roles/mutation_sweep.py "img d18"  # by label

`git status` must be clean afterwards: the sweep restores every file and checks its sha256.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if str(_root) not in sys.path:
        sys.path.insert(0, _root)

from mechanical.mutation_sweep import REPO, Case, guard, main  # noqa: E402

REMEDIATION = REPO / "scripts/remediation"
LICENSES = REMEDIATION / "licenses.py"
FETCH = REMEDIATION / "import_hero/fetch.py"
IH_PLAN = REMEDIATION / "import_hero/plan.py"
INSERT = REMEDIATION / "import_hero/insert.py"
INSERT_WRITER = REMEDIATION / "import_hero/insert_writer.py"
CREDIT = REMEDIATION / "import_hero/credit_refusals.py"
ATTRIB = REMEDIATION / "gallery_audit/attribution.py"
JUDGE = REMEDIATION / "candidate_search/judge.py"

SERVED = REMEDIATION / "served_image"
V_PY = SERVED / "vision.py"
RECHECK_PY = SERVED / "recheck.py"
SERVED_PLAN = SERVED / "plan.py"
PRECHECK_PY = SERVED / "precheck.py"
COMMONS_PY = SERVED / "commons.py"
CS_DIR = REMEDIATION / "candidate_search"
SEARCH = CS_DIR / "search.py"
POPULATION = CS_DIR / "population.py"
POOL = CS_DIR / "pool.py"
ROLES_DIR = REMEDIATION / "image_roles"
STAGE = ROLES_DIR / "stage.py"
PREFILTER = ROLES_DIR / "prefilter.py"
DEPICTS = ROLES_DIR / "depicts.py"
HERO = ROLES_DIR / "hero_recheck.py"
TARGETS = ROLES_DIR / "targets.py"
IDENTITY = ROLES_DIR / "identity.py"
FLOW = ROLES_DIR / "flow.py"
WIKI = ROLES_DIR / "wiki_cache.py"
CALIBRATE = ROLES_DIR / "calibrate.py"

T_SERVED_RECHECK = "tests/remediation/test_served_image_recheck.py"
T_ROUTES = "tests/remediation/test_candidate_routes.py"
T_ROLES = "tests/remediation/test_image_roles.py"
T_FLOW = "tests/remediation/test_image_flow.py"
T_CAL = "tests/remediation/test_image_calibrate.py"
T_SEARCH = "tests/remediation/test_candidate_search.py"
T_SERVED = "tests/remediation/test_served_image.py"
T_LICENSES = "tests/remediation/test_licenses.py"
T_FETCH = "tests/remediation/test_import_hero.py"
T_INSERT = "tests/remediation/test_import_hero_insert.py"
T_CREDIT = "tests/remediation/test_credit_refusals.py"
T_ATTRIB = "tests/remediation/test_gallery_attribution.py"
T_JUDGE = "tests/remediation/test_candidate_judge.py"

D18_CASES: list[Case] = [
    # ------------------------------------------------------------------ the rule (licenses.py)
    guard(
        "img d18: a free licence asks for no credit",
        LICENSES,
        "    if is_free(license_name):",
        "test_a_public_domain_or_cc0_file_asks_for_no_credit",
        T_LICENSES,
    ),
    Case(
        "img d18: the free prefixes",
        LICENSES,
        "    return name in FREE_LICENSES or name.startswith(FREE_LICENSE_PREFIXES)",
        "    return name in FREE_LICENSES",
        "test_a_public_domain_or_cc0_file_asks_for_no_credit",
        T_LICENSES,
    ),
    guard(
        "img d18: Attribution asks for the author only",
        LICENSES,
        "    if license_name.strip().casefold() in AUTHOR_ONLY_LICENSES:",
        "test_commons_attribution_asks_for_the_author_and_has_no_licence_page",
        T_LICENSES,
    ),
    Case(
        "img d18: the author_url is never demanded",
        LICENSES,
        '    return ("author", "license_url")',
        '    return ("author", "author_url", "license_url")',
        "test_the_author_url_is_never_demanded",
        T_LICENSES,
    ),
    Case(
        "img d18: the scope predicate leaves the free names out",
        LICENSES,
        "AND lower({column}) NOT IN ({exact}) AND NOT ({likes}))",
        "AND lower({column}) NOT IN ({exact}))",
        "test_the_sql_predicate_is_built_from_the_same_names",
        T_LICENSES,
    ),
    # ------------------------------------------------------------------ the manifest
    guard(
        "img d18: the manifest names what a licence demands",
        FETCH,
        "    if missing:",
        "test_the_author_is_required_where_the_licence_asks_for_attribution",
        T_FETCH,
    ),
    Case(
        "img d18: a manifest of a free licence may carry no credit",
        FETCH,
        '    required = required_columns(entry["license"])',
        '    required = required_columns("CC BY 4.0")',
        "test_a_free_licence_needs_neither_an_author_nor_a_licence_url",
        T_FETCH,
    ),
    Case(
        "img d18: the update path stores a missing credit as NULL",
        IH_PLAN,
        '        elif column in NULLABLE_FETCH_COLUMNS and str(value) == "":',
        "        elif False:",
        "test_the_hero_wave_stores_a_missing_credit_as_null",
        T_FETCH,
    ),
    # ------------------------------------------------------------------ the INSERT lane
    Case(
        "img d18: a missing credit is NULL in the planned row",
        INSERT,
        '    return None if column in NULLABLE_FETCH_COLUMNS and text == "" else text',
        "    return text",
        "test_the_manifests_empty_credit_becomes_none_in_the_planned_row",
        T_INSERT,
    ),
    Case(
        "img d18: the temp table allows the NULL",
        INSERT,
        '        null = "" if column in NULLABLE_FETCH_COLUMNS else " NOT NULL"',
        '        null = " NOT NULL"',
        "test_the_statement_inserts_null_and_the_temp_table_allows_it",
        T_INSERT,
    ),
    Case(
        "img d18: a chunk file keeps None as None",
        INSERT,
        '            values={k: None if v is None else str(v) for k, v in dict(record["values"]).items()},',
        '            values={k: str(v) for k, v in dict(record["values"]).items()},',
        "test_a_chunk_file_keeps_none_as_none",
        T_INSERT,
    ),
    guard(
        "img d18: the read-back compares the credit",
        INSERT_WRITER,
        "            if held.get(column) != planned.values[column]:",
        "test_the_readback_compares_null_with_null",
        T_INSERT,
    ),
    Case(
        "img d18: a re-seed keeps the source it was given",
        INSERT,
        '                    "source": str(refusal.get("source") or "")\n                    or (',
        '                    "source": ""\n                    or (',
        "test_a_source_refusal_with_a_source_of_its_own_keeps_it",
        T_INSERT,
    ),
    guard(
        "img d18: a named site must be a target",
        JUDGE,
        "        if absent:",
        "test_a_named_site_that_is_no_target_is_refused_by_name",
        T_JUDGE,
    ),
    Case(
        "img d18: a re-seed claims only the named sites",
        JUDGE,
        '        targets = [t for t in targets if str(t.get("site_id") or "") in wanted]',
        "        targets = targets",
        "test_a_re_seed_claims_only_the_sites_it_names",
        T_JUDGE,
    ),
    # ------------------------------------------------------------------ the credit refusals
    Case(
        "img d18: only credit columns make a credit refusal",
        CREDIT,
        "    return columns is not None and set(columns) <= set(NULLABLE_FETCH_COLUMNS)",
        "    return columns is not None",
        "test_only_credit_columns_make_a_credit_refusal",
        T_CREDIT,
    ),
    Case(
        "img d18: a fetched site is not asked again",
        CREDIT,
        "if s not in fetched and is_credit_refusal(why)",
        "if is_credit_refusal(why)",
        "test_a_site_a_later_wave_fetched_is_not_asked_again",
        T_CREDIT,
    ),
    # ------------------------------------------------------------------ A5 and the scope
    guard(
        "img d18: A5 refuses a bot uploader",
        ATTRIB,
        "    if _BOT_NAME.search(user):",
        "test_a5_refuses_a_bot_account_as_the_author",
        T_ATTRIB,
    ),
    guard(
        "img d18: A5 refuses a file with no upload version",
        ATTRIB,
        "    if not user:",
        "test_a5_refuses_a_file_with_no_upload_version",
        T_ATTRIB,
    ),
    guard(
        "img d18: A5 waits for the upload history",
        ATTRIB,
        "    if not page.uploader_read:",
        "test_a_self_licensed_file_with_no_author_anywhere_waits_for_its_upload_history",
        T_ATTRIB,
    ),
    Case(
        "img d18: an earlier route beats A5",
        ATTRIB,
        "        route_wikitext,\n        route_self_licensed,\n    ):",
        "        route_self_licensed,\n        route_wikitext,\n    ):",
        "test_an_earlier_route_beats_a5",
        T_ATTRIB,
    ),
    guard(
        "img d18: an own-work credit with no one named is A5",
        ATTRIB,
        "    if not users and not _ANCHOR.search(credit):",
        "test_a5_takes_an_own_work_credit_that_names_no_one",
        T_ATTRIB,
    ),
    guard(
        "img d18: the plan stops on an unread history",
        ATTRIB,
        "        if isinstance(found, NeedsUploader):",
        "test_a_plan_over_a_page_whose_history_was_not_read_stops",
        T_ATTRIB,
    ),
    guard(
        "img d18: a long history is refused",
        ATTRIB,
        '    if "continue" in answer:',
        "test_a_history_longer_than_one_answer_is_refused",
        T_ATTRIB,
    ),
    Case(
        "img d18: the first version is the oldest",
        ATTRIB,
        "    oldest = versions[-1]",
        "    oldest = versions[0]",
        "test_the_upload_history_is_read_oldest_first_and_only_where_a5_applies",
        T_ATTRIB,
    ),
    Case(
        "img d18: the history is read only where A5 applies",
        ATTRIB,
        "        if isinstance(page, Page) and isinstance(resolve(page), NeedsUploader):",
        "        if isinstance(page, Page):",
        "test_the_upload_history_is_read_oldest_first_and_only_where_a5_applies",
        T_ATTRIB,
    ),
    guard(
        "img d18: the A5 evidence names the uploader",
        ATTRIB,
        '    if found.rule == "A5":',
        "test_the_plan_writes_the_uploader_as_author_with_its_evidence",
        T_ATTRIB,
    ),
    Case(
        "img d18: only hero rows are listed for the swap",
        ATTRIB,
        "    hero = {row.id: row for row in rows if row.is_hero}",
        "    hero = {row.id: row for row in rows}",
        "test_a_hero_row_that_stays_uncredited_is_listed_for_the_swap",
        T_ATTRIB,
    ),
    Case(
        "img d18: the scope is the licences that ask for an author",
        ATTRIB,
        '{needs_attribution_sql("w.license")}',
        "w.license LIKE 'CC BY%'",
        "test_the_scope_is_every_licence_that_asks_for_an_author",
        T_ATTRIB,
    ),
    guard(
        "img d18: a run is dated",
        ATTRIB,
        '    if not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", date):',
        "test_a_run_of_2026_10_08_is_stamped_attribution_and_its_date",
        T_ATTRIB,
    ),
]


def g(label: str, path: Path, needle: str, test: str, testfile: str) -> Case:
    """A guard of the image lanes: the `if` at `needle` becomes `if False`."""
    return guard(f"img {label}", path, needle, test, testfile)


def c(label: str, path: Path, old: str, new: str, test: str, testfile: str) -> Case:
    return Case(f"img {label}", path, old, new, test, testfile)


D15_CASES: list[Case] = [
    # ------------------------------------------------------------ served_image/vision.py
    g(
        "d15: a recheck needs its context",
        V_PY,
        "    if (population == RECHECK) != (context is not None):",
        "test_a_recheck_needs_its_sites_and_its_context_and_no_one_else_takes_a_context",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a recheck needs its sites",
        V_PY,
        "    if population == RECHECK and sites is None:",
        "test_a_recheck_needs_its_sites_and_its_context_and_no_one_else_takes_a_context",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a named site must serve an image",
        V_PY,
        "    if sites is not None and len(asked) != len(named):",
        "test_a_named_site_that_serves_nothing_is_refused",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: every asked site has its context",
        V_PY,
        '        if absent:\n            raise ST.StateError(f"{len(absent)} site(s) have no context',
        '        if False:\n            raise ST.StateError(f"{len(absent)} site(s) have no context',
        "test_a_recheck_needs_its_sites_and_its_context_and_no_one_else_takes_a_context",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: only the named sites are asked",
        V_PY,
        "        and (sites is None or sid in named)\n        and (population != UNCONFIRMED_ONLY",
        "        and (population != UNCONFIRMED_ONLY",
        "test_only_the_named_sites_are_asked_and_the_record_names_them",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a sites list names a site",
        V_PY,
        "    if not named:",
        "test_a_list_names_each_site_once_and_at_least_one",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a sites list names a site once",
        V_PY,
        "    if len(set(named)) != len(named):",
        "test_a_list_names_each_site_once_and_at_least_one",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a named site is pre-checked",
        V_PY,
        "    if unknown:",
        "test_a_named_site_the_precheck_does_not_know_is_refused",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: a region view keeps the hero",
        V_PY,
        '    return check["verdict"] not in (DEPICTS, REGION_OR_TYPE)',
        '    return check["verdict"] != DEPICTS',
        "test_the_other_populations_still_plan_a_region_view_as_not_depicting",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: the replacement stage names the check stage's sites",
        V_PY,
        "        if recorded is not None and named != set(recorded):",
        "test_the_replacement_stage_must_name_the_sites_of_the_check_stage",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: only the named sites are claimed",
        V_PY,
        "        and (sites is None or sid in named)\n        and wanted_files(",
        "        and wanted_files(",
        "test_a_claimed_site_outside_the_list_is_not_asked",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: an excluded file is not offered again",
        V_PY,
        '    known = {ST.file_of_row(r) for r in state.rows.get(sid, ())} | {served.get("file")}',
        '    known = {ST.file_of_row(r) for r in rows} | {served.get("file")}',
        "test_a_gallery_file_that_was_excluded_is_not_offered_again",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: the two exports name one list",
        V_PY,
        "    if len({tuple(sorted(sites)) for sites in named}) > 1:",
        "test_the_check_and_the_replacement_export_must_name_the_same_sites",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: a recheck other_site is strict",
        V_PY,
        "    asks_more = strict or (question is not None and question.context is not None)",
        "    asks_more = False",
        "test_a_recheck_other_site_names_the_monument_and_cites_commons",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: an other_site names what the picture shows",
        V_PY,
        '        if len(parsed["shows"].split()) < MIN_SHOWS_WORDS:',
        "test_a_recheck_other_site_names_the_monument_and_cites_commons",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: an other_site cites a Commons page",
        V_PY,
        '        if COMMONS_HOST not in parsed["basis"]:',
        "test_a_recheck_other_site_names_the_monument_and_cites_commons",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: the brief runs as the role's model",
        V_PY,
        "    answer_model = ANSWER_MODEL if role is None else RO.role(role).model",
        "    answer_model = ANSWER_MODEL",
        "test_the_brief_names_the_role_and_the_recording_command_carries_it",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: an import in a role refuses another role",
        V_PY,
        "        if role is not None and RO.role_of(answer.answered_by) != role:",
        "test_an_import_in_a_role_the_answers_were_not_given_in_is_refused",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: an answer carries its role's stamp",
        V_PY,
        '        if problem is not None:\n            raise ST.StateError(f"{batch_id}/{label}: {problem}")',
        '        if False:\n            raise ST.StateError(f"{batch_id}/{label}: {problem}")',
        "test_a_stamp_that_is_not_the_roles_model_stops_the_import",
        T_SERVED_RECHECK,
    ),
    # ------------------------------------------------------------ served_image/plan.py
    c(
        "d15: a kept hero is named kept",
        SERVED_PLAN,
        '    outcome = KEPT if check is not None and check["verdict"] == V.REGION_OR_TYPE else CONFIRMED',
        "    outcome = CONFIRMED",
        "test_region_or_type_keeps_the_hero_and_other_site_clears",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: a kept hero is not replaced",
        SERVED_PLAN,
        "    elif not V.needs_replacement(check, population):",
        '    elif check["verdict"] == V.DEPICTS:',
        "test_region_or_type_keeps_the_hero_and_other_site_clears",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a restricted run plans its sites only",
        SERVED_PLAN,
        "    if sites is not None:",
        "test_region_or_type_keeps_the_hero_and_other_site_clears",
        T_SERVED_RECHECK,
    ),
    # ------------------------------------------------------------ served_image/recheck.py
    c(
        "d15: a population row is a hero",
        RECHECK_PY,
        '                and row.get("is_hero")\n',
        "                and True\n",
        "test_a_live_hero_judged_other_site_is_in_and_nothing_else_is",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: a population row is live",
        RECHECK_PY,
        '                and not row.get("is_excluded")\n',
        "                and True\n",
        "test_an_excluded_row_and_a_retired_site_are_out",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: the later stage decides",
        RECHECK_PY,
        "    for row in replaces:\n",
        "    for row in []:\n",
        "test_the_later_stage_decides_for_a_row_judged_twice",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: one hero a site",
        RECHECK_PY,
        '    sites = [str(h["site_id"]) for h in heroes]\n    if len(set(sites)) != len(sites):',
        '    sites = [str(h["site_id"]) for h in heroes]\n    if False:',
        "test_two_heroes_of_one_site_are_refused",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: an empty derivation is refused",
        RECHECK_PY,
        "    if not heroes:",
        "test_an_empty_derivation_is_refused_by_name",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a sites file names a site",
        RECHECK_PY,
        "    if not sites:",
        "test_a_sites_file_names_each_site_once",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: a sites file names each once",
        RECHECK_PY,
        '    if len(set(sites)) != len(sites):\n        raise RecheckError(f"{path} names a site twice")',
        '    if False:\n        raise RecheckError(f"{path} names a site twice")',
        "test_a_sites_file_names_each_site_once",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a failed Wikipedia request is no 'no image'",
        RECHECK_PY,
        "    if response.status_code != 200:",
        "test_a_failed_wikipedia_request_is_not_read_as_no_image",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: one page, one lead",
        RECHECK_PY,
        "    if len(pages) != 1:",
        "test_a_wikipedia_answer_of_two_pages_is_not_read_as_one_lead_image",
        T_SERVED_RECHECK,
    ),
    c(
        "d15: a hero the read does not answer is refused",
        RECHECK_PY,
        "        row = by_site.get(sid)\n        if row is None:",
        "        row = by_site.get(sid)\n        if False:",
        "test_a_hero_the_read_does_not_answer_is_refused",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a site without an article asks nobody",
        RECHECK_PY,
        "        if title:",
        "test_a_site_without_an_article_has_no_lead_and_asks_nobody",
        T_SERVED_RECHECK,
    ),
    # ------------------------------------------------------------ served_image/precheck.py
    g(
        "d15: a named site is in the read",
        PRECHECK_PY,
        "        if unknown:",
        "test_a_named_site_the_read_or_the_harvest_lacks_is_refused",
        T_SERVED_RECHECK,
    ),
    g(
        "d15: a named site is in the harvest",
        PRECHECK_PY,
        "        if absent:",
        "test_a_named_site_the_read_or_the_harvest_lacks_is_refused",
        T_SERVED_RECHECK,
    ),
]

D17_CASES: list[Case] = [
    # ------------------------------------------------------------ served_image/commons.py
    c(
        "d17: a save keeps the other worker's entries",
        COMMONS_PY,
        "            merged = {**self._load(name), **data}",
        "            merged = dict(data)",
        "test_a_save_keeps_the_entries_another_worker_wrote",
        T_ROUTES,
    ),
    g(
        "d17: an article that does not exist is missing",
        COMMONS_PY,
        '            if page.get("missing") or page.get("invalid"):',
        "test_an_article_that_does_not_exist_is_missing_not_empty",
        T_ROUTES,
    ),
    g(
        "d17: one article, one page",
        COMMONS_PY,
        "            if len(pages) != 1:",
        "test_an_answer_of_two_pages_is_refused",
        T_ROUTES,
    ),
    # ------------------------------------------------------------ candidate_search/search.py
    g(
        "d17: the geotag route needs a sourced point",
        SEARCH,
        '    if site.get("coord_sourced"):',
        "test_the_geotag_route_runs_only_for_a_sourced_point_and_carries_the_distance",
        T_ROUTES,
    ),
    g(
        "d17: two items give no item route",
        SEARCH,
        '    if site.get("qid_conflict"):',
        "test_two_items_give_no_item_route_and_say_so",
        T_ROUTES,
    ),
    g(
        "d17: an item needs its entity store",
        SEARCH,
        '    if qid and site.get("qid_conflict") is None and entities is None:',
        "test_a_site_with_an_item_and_no_store_is_an_error",
        T_ROUTES,
    ),
    g(
        "d17: an item nobody holds is an error",
        SEARCH,
        "        if entity is None:",
        "test_an_item_the_store_does_not_hold_is_an_error_not_an_empty_claim",
        T_ROUTES,
    ),
    g(
        "d17: the commonswiki link is a category",
        SEARCH,
        '        if link and link.startswith("Category:"):',
        "test_the_commons_category_the_item_links_is_read",
        T_ROUTES,
    ),
    g(
        "d17: two titles give no article route",
        SEARCH,
        '    if site.get("enwiki_conflict"):',
        "test_two_titles_give_no_article_route_and_say_so",
        T_ROUTES,
    ),
    g(
        "d17: a missing article is noted",
        SEARCH,
        '        if article["missing"]:',
        "test_an_article_that_does_not_exist_is_noted_by_name",
        T_ROUTES,
    ),
    g(
        "d17: a vector lead image is no candidate",
        SEARCH,
        '            if article["lead"] and not article["lead"].lower().endswith(_NOT_FOR_PAGE):',
        "test_a_lead_image_that_is_vector_art_is_not_a_candidate",
        T_ROUTES,
    ),
    g(
        "d17: the researched category is read",
        SEARCH,
        "    if category:",
        "test_the_researched_category_and_local_names_are_searched",
        T_ROUTES,
    ),
    g(
        "d17: a local name equal to the name is searched once",
        SEARCH,
        "        if cleaned and cleaned.casefold() not in seen:",
        "test_the_researched_category_and_local_names_are_searched",
        T_ROUTES,
    ),
    g(
        "d17: a file named twice keeps the first route",
        SEARCH,
        "        if key not in seen:",
        "test_a_file_named_by_two_routes_keeps_the_first",
        T_ROUTES,
    ),
    c(
        "d17: the claim's route is told from its reason",
        SEARCH,
        '            route = ROUTE_P18 if "(P18)" in why else ROUTE_P373',
        "            route = ROUTE_P373",
        "test_the_items_image_and_category_are_the_first_routes",
        T_ROUTES,
    ),
    g(
        "d17: a held file is never offered",
        SEARCH,
        "        if named.title in known:",
        "test_the_gallery_files_and_the_judged_files_are_never_offered",
        T_ROUTES,
    ),
    c(
        "d17: a site keeps sixty candidates",
        SEARCH,
        "            candidates=out[:MAX_CANDIDATES],",
        "            candidates=out,",
        "test_a_site_keeps_sixty_candidates_and_names_the_rest",
        T_ROUTES,
    ),
    g(
        "d17: workers are one or two",
        SEARCH,
        "    if not 1 <= workers <= MAX_WORKERS:",
        "test_at_most_two_sites_at_once",
        T_ROUTES,
    ),
    # ------------------------------------------------------------ candidate_search/population.py
    c(
        "d17: a point is sourced by a current marker",
        POPULATION,
        '        "coord_sourced": bool(kind in SOURCED_KINDS and row.get("coord_marker_current")),',
        '        "coord_sourced": bool(kind in SOURCED_KINDS),',
        "test_a_point_is_sourced_only_by_a_current_marker_of_a_sourced_kind",
        T_ROUTES,
    ),
    g(
        "d17: one item is an identity",
        POPULATION,
        "    if len(distinct) == 1:",
        "test_two_items_are_a_conflict_and_no_item",
        T_ROUTES,
    ),
    g(
        "d17: a site twice is refused",
        POPULATION,
        "    if len(set(ids)) != len(ids):",
        "test_the_population_is_sorted_and_a_site_twice_is_refused",
        T_ROUTES,
    ),
    g(
        "d17: an empty population is refused",
        POPULATION,
        "    if not sites:",
        "test_the_population_is_written_once_and_read_back",
        T_ROUTES,
    ),
    g(
        "d17: a file is held once",
        POPULATION,
        "        if name and name not in out:",
        "test_the_files_of_every_row_are_held_the_excluded_ones_too",
        T_ROUTES,
    ),
    # ------------------------------------------------------------ candidate_search/pool.py
    g(
        "d17: only the population's sites are pooled",
        POOL,
        '        if str(site["site_id"]) not in site_ids:',
        "test_a_site_outside_the_population_is_left_out",
        T_ROUTES,
    ),
    c(
        "d17: a gone picture is named",
        POOL,
        "            if not path.is_file():\n                missing.append",
        "            if False:\n                missing.append",
        "test_the_old_candidates_of_the_named_sites_come_with_their_pictures",
        T_ROUTES,
    ),
    g(
        "d17: a target needs its site, candidate and verdict",
        POOL,
        "        if site is None or candidate is None or verdict is None:",
        "test_a_target_of_a_site_outside_the_population_is_refused",
        T_ROUTES,
    ),
    c(
        "d17: a target's picture must exist",
        POOL,
        '        if not path.is_file():\n            raise PoolError(f"{site_id}: the picture of target',
        '        if False:\n            raise PoolError(f"{site_id}: the picture of target',
        "test_a_target_whose_picture_is_gone_is_refused_by_name",
        T_ROUTES,
    ),
    g(
        "d17: only MiniMax's depicts can be denied",
        POOL,
        '        if old.get("verdict") != CJ.DEPICTS:',
        "test_only_a_pair_minimax_called_depicts_can_be_denied",
        T_ROUTES,
    ),
    g(
        "d17: the prefilter's drop denies",
        POOL,
        '        if key in pre and not pre[key]["survives"]:',
        "test_what_claude_does_not_confirm_is_denied_with_the_reason",
        T_ROUTES,
    ),
    g(
        "d17: the depicts role's refusal denies",
        POOL,
        '            if row["verdict"] != CJ.DEPICTS:',
        "test_what_claude_does_not_confirm_is_denied_with_the_reason",
        T_ROUTES,
    ),
    c(
        "d17: the re-check's rejection denies",
        POOL,
        "            elif key[1] in rejected.get(key[0], ()):",
        "            elif False:",
        "test_what_claude_does_not_confirm_is_denied_with_the_reason",
        T_ROUTES,
    ),
    c(
        "d17: a denied pair is a hero only if served",
        POOL,
        '            if d is not None and row.get("is_hero") and not row.get("is_excluded"):',
        "            if d is not None:",
        "test_a_denied_pair_is_a_hero_only_where_the_page_serves_it",
        T_ROUTES,
    ),
    # ------------------------------------------------------------ image_roles/stage.py
    g(
        "d17: a question once",
        STAGE,
        "    if len(set(labels)) != len(labels):",
        "test_a_question_exported_twice_is_refused",
        T_ROLES,
    ),
    g(
        "d17: every picture has bytes",
        STAGE,
        "            if image.name not in pictures:",
        "test_a_picture_without_bytes_is_refused",
        T_ROLES,
    ),
    g(
        "d17: the picture is the one named",
        STAGE,
        "            if written != image:",
        "test_a_question_that_names_other_bytes_than_it_was_given_is_refused",
        T_ROLES,
    ),
    c(
        "d17: questions must be exported",
        STAGE,
        "    path = run / spec.questions_file\n    if not path.is_file():",
        "    path = run / spec.questions_file\n    if False:",
        "test_a_stage_that_was_not_exported_or_imported_names_the_step_to_run",
        T_ROLES,
    ),
    c(
        "d17: the export record must exist",
        STAGE,
        "    path = run / spec.export_file\n    if not path.is_file():",
        "    path = run / spec.export_file\n    if False:",
        "test_a_stage_that_was_not_exported_or_imported_names_the_step_to_run",
        T_ROLES,
    ),
    g(
        "d17: a batch has questions",
        STAGE,
        "    if not labels:",
        "test_the_brief_names_the_role_model_and_recording_command",
        T_ROLES,
    ),
    g(
        "d17: a checked question exists",
        STAGE,
        "    if question is None:",
        "test_the_shape_of_an_answer_is_checked_without_recording_it",
        T_ROLES,
    ),
    c(
        "d17: a check names the exported handoff",
        STAGE,
        '        raise StageError(f"{handoff} is not the handoff {spec.name} was exported to")\n    question = load_questions',
        "        pass\n    question = load_questions",
        "test_the_shape_of_an_answer_is_checked_without_recording_it",
        T_ROLES,
    ),
    c(
        "d17: an import names the exported handoff",
        STAGE,
        '        raise StageError(f"{handoff} is not the handoff {spec.name} was exported to")\n    if ST.file_sha256',
        "        pass\n    if ST.file_sha256",
        "test_a_handoff_other_than_the_exported_one_is_refused",
        T_ROLES,
    ),
    g(
        "d17: the questions file is the exported one",
        STAGE,
        '    if ST.file_sha256(run / spec.questions_file) != record["questions_sha256"]:',
        "test_a_changed_question_file_stops_the_import",
        T_ROLES,
    ),
    g(
        "d17: an import validates",
        STAGE,
        "    if not validation.ok:",
        "test_an_unanswered_handoff_does_not_import",
        T_ROLES,
    ),
    g(
        "d17: a picture is the one shown",
        STAGE,
        "            if hashlib.sha256(shown.read_bytes()).hexdigest() != image.sha256:",
        "test_a_changed_picture_stops_the_import",
        T_ROLES,
    ),
    g(
        "d17: an answer carries its role's stamp",
        STAGE,
        "        if wrong is not None:",
        "test_an_answer_not_stamped_by_the_roles_model_is_refused",
        T_ROLES,
    ),
    g(
        "d17: an answer is in the stage's role",
        STAGE,
        "        if RO.role_of(answer.answered_by) != spec.role:",
        "test_an_answer_in_another_role_is_refused",
        T_ROLES,
    ),
    g(
        "d17: every shape problem stops the import",
        STAGE,
        "    if problems:",
        "test_every_shape_problem_is_named_and_nothing_is_written",
        T_ROLES,
    ),
    c(
        "d17: results must be imported",
        STAGE,
        "    path = run / spec.result_file\n    if not path.is_file():",
        "    path = run / spec.result_file\n    if False:",
        "test_a_stage_that_was_not_exported_or_imported_names_the_step_to_run",
        T_ROLES,
    ),
    g(
        "d17: a text field is a text",
        STAGE,
        "    if not isinstance(value, str) or not value.strip() or len(value) > longest:",
        "test_the_text_helpers_refuse_what_is_out_of_shape",
        T_ROLES,
    ),
    g(
        "d17: an answer holds a JSON object",
        STAGE,
        "    if data is None:",
        "test_the_text_helpers_refuse_what_is_out_of_shape",
        T_ROLES,
    ),
    g(
        "d17: an answer carries exactly its keys",
        STAGE,
        "    if set(data) != keys:",
        "test_the_text_helpers_refuse_what_is_out_of_shape",
        T_ROLES,
    ),
    # ------------------------------------------------------------ image_roles/prefilter.py
    g(
        "d17: a prefilter question holds sixty",
        PREFILTER,
        "    if not 1 <= batch_size <= BATCH_SIZE:",
        "test_a_question_holds_at_most_sixty",
        T_ROLES,
    ),
    g(
        "d17: every picture is judged",
        PREFILTER,
        "    if not isinstance(given, dict) or set(given) != set(wanted):",
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: a kind is one of the six",
        PREFILTER,
        '        if entry["kind"] not in KINDS:',
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: usable is a boolean",
        PREFILTER,
        '        if not isinstance(entry["usable"], bool):',
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    c(
        "d17: a survivor is usable",
        PREFILTER,
        '    return bool(entry["usable"]) and entry["kind"] in SURVIVING_KINDS',
        '    return entry["kind"] in SURVIVING_KINDS',
        "test_only_a_usable_picture_of_a_kind_that_can_show_a_site_survives",
        T_ROLES,
    ),
    c(
        "d17: a survivor can show a site",
        PREFILTER,
        '    return bool(entry["usable"]) and entry["kind"] in SURVIVING_KINDS',
        '    return bool(entry["usable"])',
        "test_only_a_usable_picture_of_a_kind_that_can_show_a_site_survives",
        T_ROLES,
    ),
    # ------------------------------------------------------------ image_roles/depicts.py
    g(
        "d17: the geotag distance is told to the judge",
        DEPICTS,
        '    if candidate.get("distance_m") is not None:',
        "test_the_prompt_carries_everything_the_old_one_lacked",
        T_ROLES,
    ),
    g(
        "d17: every candidate is judged",
        DEPICTS,
        "    if not isinstance(given, dict) or set(given) != set(wanted):",
        "test_every_candidate_must_be_judged",
        T_ROLES,
    ),
    g(
        "d17: a verdict is one of three",
        DEPICTS,
        "        if verdict not in VERDICTS:",
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: a depicts has a quality",
        DEPICTS,
        "            if isinstance(quality, bool) or quality not in QUALITIES:",
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    c(
        "d17: only a depicts has a quality",
        DEPICTS,
        "        elif quality is not None:",
        "        elif False:",
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: a verdict row has a size",
        DEPICTS,
        "            if (site_id, file) not in sizes:",
        "test_the_verdict_rows_are_what_the_judge_stage_reads",
        T_ROLES,
    ),
    # ------------------------------------------------------------ image_roles/hero_recheck.py
    g(
        "d17: a round is numbered from one",
        HERO,
        "    if round_number < 1:",
        "test_twelve_to_a_batch_and_the_round_in_the_batch_id",
        T_ROLES,
    ),
    c(
        "d17: the re-check is strict",
        HERO,
        "        return V.parse_check(text, strict=True)",
        "        return V.parse_check(text, strict=False)",
        "test_an_other_site_needs_the_monument_and_a_commons_page",
        T_ROLES,
    ),
    g(
        "d17: a confirmed file depicts",
        HERO,
        '        if row["verdict"] == V.DEPICTS:',
        "test_confirmed_and_rejected_files_by_site",
        T_ROLES,
    ),
    g(
        "d17: a rejected file does not",
        HERO,
        '        if row["verdict"] != V.DEPICTS:',
        "test_confirmed_and_rejected_files_by_site",
        T_ROLES,
    ),
    # ------------------------------------------------------------ image_roles/targets.py
    c(
        "d17: the best quality ranks first",
        TARGETS,
        '        rows.sort(key=lambda r: (tuple(-v for v in CJ.rank_key(r)), str(r["file"])))',
        '        rows.sort(key=lambda r: str(r["file"]))',
        "test_the_best_quality_wins_not_the_largest_file",
        T_ROLES,
    ),
    g(
        "d17: only a depicts is ranked",
        TARGETS,
        '        if row.get("verdict") == CJ.DEPICTS:',
        "test_only_depicts_rows_are_ranked",
        T_ROLES,
    ),
    g(
        "d17: a candidate is rechecked once",
        TARGETS,
        '        if key in out and out[key] != row["verdict"]:',
        "test_a_candidate_rechecked_twice_with_two_verdicts_is_refused",
        T_ROLES,
    ),
    c(
        "d17: an unchecked pick waits",
        TARGETS,
        "            if verdict is None:\n                result.to_check.append(row)",
        "            if False:\n                result.to_check.append(row)",
        "test_a_site_waits_for_the_recheck_of_its_best_pick",
        T_ROLES,
    ),
    g(
        "d17: a confirmed pick ends the site",
        TARGETS,
        "            if verdict == CJ.DEPICTS:",
        "test_a_confirmed_pick_ends_the_site",
        T_ROLES,
    ),
    g(
        "d17: targets wait for the rounds",
        TARGETS,
        "    if state.to_check:",
        "test_targets_are_not_written_while_a_site_waits",
        T_ROLES,
    ),
    c(
        "d17: the best quality is the target",
        JUDGE,
        "        if current is None or rank_key(row) > rank_key(current):",
        '        if current is None or row.get("width", 0) > current.get("width", 0):',
        "test_the_best_quality_wins_not_the_largest_file",
        T_ROLES,
    ),
    g(
        "d17: only a confirmed candidate is a target",
        JUDGE,
        '        if confirmed is not None and (site_id, str(row["file"])) not in confirmed:',
        "test_a_confirmed_set_limits_the_eligible_candidates",
        T_ROLES,
    ),
    # ------------------------------------------------------------ image_roles/identity.py
    g(
        "d17: a site without an item has nothing to verify",
        IDENTITY,
        '    if not site.get("qid"):',
        "test_a_site_without_an_item_has_nothing_to_verify_and_a_missing_item_is_flagged",
        T_ROLES,
    ),
    g(
        "d17: a missing item is flagged",
        IDENTITY,
        "    if entity is None:",
        "test_a_site_without_an_item_has_nothing_to_verify_and_a_missing_item_is_flagged",
        T_ROLES,
    ),
    g(
        "d17: a far point is flagged",
        IDENTITY,
        "        if metres / 1000.0 > MAX_POINT_KM:",
        "test_an_item_far_from_the_site_is_flagged",
        T_ROLES,
    ),
    g(
        "d17: a label with no word of the name is flagged",
        IDENTITY,
        "    if wanted and not any(IC.tokens(n) & wanted for n in names if n):",
        "test_a_label_with_no_word_of_the_name_is_flagged_unless_an_alias_has_one",
        T_ROLES,
    ),
    g(
        "d17: a conflicted item is not verified",
        IDENTITY,
        '        if not site.get("qid") or site.get("qid_conflict"):',
        "test_the_verify_population_is_the_flagged_sites_with_the_items_label",
        T_ROLES,
    ),
    g(
        "d17: only a flagged site is asked",
        IDENTITY,
        "        if flags:",
        "test_the_verify_population_is_the_flagged_sites_with_the_items_label",
        T_ROLES,
    ),
    g(
        "d17: the cache path is told to the agent",
        IDENTITY,
        "    if page is not None and cache is not None:",
        "test_the_prompt_names_the_flags_the_cache_and_the_rules_for_the_web",
        T_ROLES,
    ),
    g(
        "d17: a mode is verify or research",
        IDENTITY,
        '    if mode not in ("verify", "research"):',
        "test_batches_of_five_to_verify_and_four_to_research",
        T_ROLES,
    ),
    g(
        "d17: every site is answered",
        IDENTITY,
        "    if not isinstance(given, dict) or set(given) != set(asked):",
        "test_the_answer_covers_exactly_the_sites_asked",
        T_ROLES,
    ),
    g(
        "d17: a status is one of three",
        IDENTITY,
        "        if given[key] not in STATUSES:",
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: an item id is an item id",
        IDENTITY,
        "    if qid is not None and not (isinstance(qid, str) and _QID.fullmatch(qid)):",
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: a category is named without its prefix",
        IDENTITY,
        '    if category is not None and category.lower().startswith("category:"):',
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: a claim needs its evidence",
        IDENTITY,
        "    if (qid or title or category) and not evidence:",
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: confirmed names the held item",
        IDENTITY,
        '    if given["qid_status"] == "confirmed" and qid != asked["qid"]:',
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: confirmed names the held article",
        IDENTITY,
        '    if given["enwiki_status"] == "confirmed" and title != asked["enwiki_title"]:',
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: wrong replaces the item",
        IDENTITY,
        '    if given["qid_status"] == "wrong" and qid == asked["qid"]:',
        "test_an_answer_out_of_shape_is_named",
        T_ROLES,
    ),
    g(
        "d17: a site is answered once",
        IDENTITY,
        "            if site_id in out:",
        "test_a_site_answered_twice_is_refused",
        T_ROLES,
    ),
    g(
        "d17: a confirmed link stays",
        IDENTITY,
        '    if status == "confirmed":',
        "test_a_confirmed_link_stays_and_the_category_and_names_are_added",
        T_ROLES,
    ),
    g(
        "d17: a wrong link is replaced",
        IDENTITY,
        '    if status == "wrong":',
        "test_a_wrong_item_is_replaced_and_the_change_is_marked",
        T_ROLES,
    ),
    c(
        "d17: research asks the sites with no identity",
        IDENTITY,
        '        if (not s.get("qid") and not s.get("enwiki_title")) or str(s["site_id"]) in asked',
        '        if str(s["site_id"]) in asked',
        "test_the_research_population_is_no_identity_or_a_first_search_with_no_file",
        T_ROLES,
    ),
    # ------------------------------------------------------------ image_roles/flow.py
    g(
        "d17: verify needs the items",
        FLOW,
        "        if missing:",
        "test_an_item_nobody_holds_stops_the_verify_export",
        T_FLOW,
    ),
    g(
        "d17: a mode has sites",
        FLOW,
        "    if not asked:",
        "test_verify_asks_the_flagged_sites_and_research_the_nameless",
        T_FLOW,
    ),
    g(
        "d17: an answer belongs to the population",
        FLOW,
        "    if unknown:",
        "test_an_answer_for_a_site_outside_the_population_is_refused",
        T_FLOW,
    ),
    c(
        "d17: a MiniMax verdict never excludes a file",
        FLOW,
        '            if row.get("verdict") != CJ.DEPICTS and MINIMAX_WORD not in model.lower():',
        '            if row.get("verdict") != CJ.DEPICTS:',
        "test_a_claude_pass_excludes_a_file_a_minimax_pass_never_does",
        T_FLOW,
    ),
    g(
        "d17: a site record is needed",
        FLOW,
        '        if site["lat"] is None:',
        "test_the_depicts_role_needs_the_prefilter_first",
        T_FLOW,
    ),
    g(
        "d17: a recheck round has sites",
        FLOW,
        "        if not state.to_check:",
        "test_from_the_population_to_the_targets",
        T_FLOW,
    ),
    g(
        "d17: pictures stay until the targets",
        FLOW,
        "    if not (run / CJ.TARGETS).is_file():",
        "test_pictures_are_not_pruned_while_the_targets_are_unwritten",
        T_FLOW,
    ),
    # ------------------------------------------------------------ image_roles/wiki_cache.py
    g(
        "d17: an indexed page must exist",
        WIKI,
        "        if not path.is_file():",
        "test_an_indexed_page_that_is_gone_is_an_error_not_no_page",
        T_ROLES,
    ),
    g(
        "d17: an index line has its keys",
        WIKI,
        '            if set(row) != {"site_id", "lang", "title", "file"}:',
        "test_an_index_line_in_another_shape_is_refused",
        T_ROLES,
    ),
    g(
        "d17: an empty text has no lead",
        WIKI,
        "    if not body:",
        "test_an_empty_text_has_no_lead",
        T_ROLES,
    ),
    g(
        "d17: a lead fits its length",
        WIKI,
        "        if len(out) + 1 + len(sentence) > chars:",
        "test_the_lead_is_the_first_sentences_that_fit",
        T_ROLES,
    ),
]

CAL_CASES: list[Case] = [
    g(
        "cal: thresholds are sealed before the sample",
        CALIBRATE,
        "    if (directory / GOLD_FILE).exists():",
        "test_a_directory_with_a_sample_cannot_be_sealed",
        T_CAL,
    ),
    g(
        "cal: a seal is never rewritten",
        CALIBRATE,
        '    if path.exists() and path.read_text(encoding="utf-8") != text:',
        "test_other_thresholds_are_never_written_over_a_seal",
        T_CAL,
    ),
    g(
        "cal: a seal is the sealed file",
        CALIBRATE,
        '    if _sha(text) != entries[0]["thresholds_sha256"]:',
        "test_other_thresholds_are_never_written_over_a_seal",
        T_CAL,
    ),
    g(
        "cal: a moved role invalidates the seal",
        CALIBRATE,
        '        if RO.role_sha256(name) != entry["role_sha256"]:',
        "test_a_role_that_moved_after_the_seal_invalidates_it",
        T_CAL,
    ),
    g(
        "cal: a case once",
        CALIBRATE,
        "    if len(set(ids)) != len(ids) or not cases:",
        "test_a_case_twice_or_an_empty_sample_is_refused",
        T_CAL,
    ),
    g(
        "cal: a fixed sample is never rewritten",
        CALIBRATE,
        "    if fixed - {digest}:",
        "test_the_same_sample_again_changes_nothing_another_is_refused",
        T_CAL,
    ),
    g(
        "cal: a fixed sample is the fixed file",
        CALIBRATE,
        '    if _sha(text) != entries[0]["gold_sha256"]:',
        "test_a_sample_edited_after_it_was_fixed_is_refused",
        T_CAL,
    ),
    g(
        "cal: an identity label is wrong or good",
        CALIBRATE,
        '        if item["label"] not in ("wrong", "good"):',
        "test_the_identity_cases_are_sites_with_a_known_label",
        T_CAL,
    ),
    g(
        "cal: an identity case is a population site",
        CALIBRATE,
        "        if site is None:",
        "test_the_identity_cases_are_sites_with_a_known_label",
        T_CAL,
    ),
    c(
        "cal: the kind gold has no error",
        CALIBRATE,
        '        if not v.get("error") and (v.get("parsed") or {}).get("kind") in PF.KINDS',
        '        if (v.get("parsed") or {}).get("kind") in PF.KINDS',
        "test_the_kind_gold_is_opus_s_c1_kind_without_errors",
        T_CAL,
    ),
    c(
        "cal: photo versus non-photo agreement",
        CALIBRATE,
        '    agree = sum((truth[i] in PHOTO_KINDS) == (judged[i]["kind"] in PHOTO_KINDS) for i in truth)',
        "    agree = sum(True for i in truth)",
        "test_a_prefilter_that_drops_a_site_photo_fails_the_recall",
        T_CAL,
    ),
    c(
        "cal: depicts-capable is a surviving kind",
        CALIBRATE,
        "    capable = [i for i, kind in truth.items() if kind in PF.SURVIVING_KINDS]",
        "    capable = list(truth)",
        "test_agreement_and_recall_are_measured_against_the_c1_kind",
        T_CAL,
    ),
    g(
        "cal: a prefilter case is answered",
        CALIBRATE,
        "    if missing:",
        "test_a_case_nobody_answered_is_an_error",
        T_CAL,
    ),
    g(
        "cal: an adjudicated case is adjudicated",
        CALIBRATE,
        "        if entry is None:\n            raise CalibrationError(f\"{c['case_id']}: the pilot judge",
        "test_an_adjudicated_case_without_the_pilot_judge_is_an_error",
        T_CAL,
    ),
    c(
        "cal: a wrong link is flagged on either link",
        CALIBRATE,
        '        flagged = "wrong" in (verdict["qid_status"], verdict["enwiki_status"])',
        '        flagged = verdict["qid_status"] == "wrong"',
        "test_a_wrong_link_is_correct_when_flagged_and_a_good_one_when_confirmed",
        T_CAL,
    ),
    g(
        "cal: a below-floor metric fails",
        CALIBRATE,
        "        if value is None or value < floor:",
        "test_a_prefilter_that_drops_a_site_photo_fails_the_recall",
        T_CAL,
    ),
    g(
        "cal: a false-depicts rate above its ceiling fails",
        CALIBRATE,
        '        if rate is None or rate > t["false_depicts_max"]:',
        "test_the_adjudicated_candidates_take_the_pilot_judge_s_word_as_truth",
        T_CAL,
    ),
    g(
        "cal: a foreign row called depicts fails",
        CALIBRATE,
        '        if t["every_foreign_not_depicts"] and metrics["foreign_called_depicts"]:',
        "test_one_foreign_row_called_depicts_fails_whatever_the_rates_are",
        T_CAL,
    ),
    g(
        "cal: a missed wrong link fails",
        CALIBRATE,
        '        if t["every_wrong_flagged"] and metrics["wrong_not_flagged"]:',
        "test_a_missed_wrong_link_fails_even_with_a_high_rate",
        T_CAL,
    ),
    c(
        "cal: only measured roles are decided",
        CALIBRATE,
        '    if role not in MEASURED:\n        raise CalibrationError(f"role {role} is not measured")\n    t = thresholds',
        '    if False:\n        raise CalibrationError(f"role {role} is not measured")\n    t = thresholds',
        "test_an_unmeasured_role_is_refused",
        T_CAL,
    ),
    c(
        "cal: the pilot judge is gold, not measured",
        CALIBRATE,
        '    if role not in MEASURED:\n        raise CalibrationError(f"role {role} is not measured (the pilot',
        '    if False:\n        raise CalibrationError(f"role {role} is not measured (the pilot',
        "test_the_pilot_judge_is_the_gold_not_a_measured_role",
        T_CAL,
    ),
    g(
        "cal: an answer before the sample is refused",
        CALIBRATE,
        '        if row["answered_at"] < fixed_at:',
        "test_an_answer_older_than_the_sample_is_refused",
        T_CAL,
    ),
    c(
        "cal: a verdict is written once",
        CALIBRATE,
        '    if path.exists():\n        raise CalibrationError(f"{path} exists - a verdict is written once")',
        '    if False:\n        raise CalibrationError(f"{path} exists - a verdict is written once")',
        "test_a_role_that_passes_is_written_once",
        T_CAL,
    ),
    g(
        "cal: a case needs a role's questions",
        CALIBRATE,
        "    if not mine:",
        "test_a_role_without_cases_or_questions_is_refused",
        T_CAL,
    ),
]

CASES: list[Case] = [*D18_CASES, *D15_CASES, *D17_CASES, *CAL_CASES]


if __name__ == "__main__":
    # `mutation_sweep.py [label substring ...]` runs the cases whose label holds any of them.
    wanted = [c for c in CASES if not sys.argv[1:] or any(a in c.label for a in sys.argv[1:])]
    if not wanted:
        sys.exit(f"no case label contains any of {sys.argv[1:]}")
    sys.exit(main(wanted))
