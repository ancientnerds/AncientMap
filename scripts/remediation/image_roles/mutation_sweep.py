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

CASES: list[Case] = [*D18_CASES]


if __name__ == "__main__":
    # `mutation_sweep.py [label substring ...]` runs the cases whose label holds any of them.
    wanted = [c for c in CASES if not sys.argv[1:] or any(a in c.label for a in sys.argv[1:])]
    if not wanted:
        sys.exit(f"no case label contains any of {sys.argv[1:]}")
    sys.exit(main(wanted))
