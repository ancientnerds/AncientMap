// Wave 6: the post-review fix pass. Two writer lanes, disjoint trees.
// Every brief is single-quoted only. No backticks anywhere in this file's template literals:
// a backtick inside a template literal terminates it (measured bug, fleet_wave5.js).
const SHARED = 'REPO is C:/PythonProjects/AncientMap, branch main, work with ./.venv/Scripts/python.exe (never bare python). ' +
'Read output/remediation/AUDIT_LOG.md section "Wave 5 review, first half" FIRST: it is the verified finding list you are fixing, with the ' +
'evidence for each. The full lens reports are in the subagent-artifacts directory named in that log entry. ' +
'HARD RULES: (1) Fix at the ROOT, never by suppressing: no hasattr, no # type: ignore, no widened except, no allowlist entry to make a check green. ' +
'(2) NEVER weaken or delete an assertion to make a test pass; NEVER edit a test expectation except where the finding says the assertion is ' +
'vacuous or satisfied by a comment, in which case replace it with one that can actually fail. (3) Prove each fix has TEETH: perturb your own fix ' +
'and show the test fails, then restore and show the file is byte-identical (sha256) to the pre-perturbation state. (4) Run the project gates and ' +
'report their real output: ./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm" tests/remediation/, ' +
'plus ./.venv/Scripts/python.exe -m ruff check and ruff format --check on every file you touch, plus mypy on the scripts you touch (scripts/ is NOT ' +
'type-checked by CI, so you must run it yourself). Also run ruff format on the files you touch and RE-PROVE byte-identity if a formatter rewrites them. ' +
'(5) NO database writes, no psql, no deploys, no git commit, no git push. Read-only DB access via "ssh ancientnerds" is available if you truly need a ' +
'production fact; state any question you answered that way. (6) If a finding is wrong, say so with the counter-evidence (a command output) and do NOT ' +
'change the code for it. (7) Do not touch output/remediation/phase3_pilot/, output/remediation/phase3_worklist/, scripts/remediation/vlm_pilot/, ' +
'or docs/procedures/ - another lane owns them. (8) Deliverable: a report of every finding with status FIXED (with the file:line and the test that now ' +
'kills it) or REFUTED (with the counter-evidence), plus the raw gate output, plus any residual you could not verify. Write that report to the path ' +
'you are given. ';

const FIX1 = 'You are FIX-1, the mechanical-lane repairer. You own exactly these trees: scripts/remediation/mechanical/ (plan.py, apply.py, ' +
'mutation_sweep.py, __init__.py), tests/remediation/test_mechanical.py, migrations/0018_remediation_change_log_boolean.sql, ' +
'scripts/remediation/0018_migration_selftest.sql, .github/workflows/ci.yml, and (for the versioning item only) output/remediation/mechanical/. ' +
'Fix these findings, each of which I verified myself: ' +
'[A] DEPLOY P0-A, deploy-blocking: CI cannot collect tests/remediation/test_mechanical.py. test_mechanical.py imports mechanical.plan at module level; ' +
'plan.py:124-126 imports census.tests.t02_admin_country at module level; that module imports geopandas at :137 and pyproj at :140 at module level; ' +
'ci.yml:184 installs only -r requirements-api.txt -r requirements.lyra.txt, which contain neither (0 matches). So collection raises ModuleNotFoundError, ' +
'the tests job is red, and the deploy job is SKIPPED - which also means migrations 0018/0019 never reach production. Fix by making the atlas/geo imports ' +
'function-local in plan.py (the pattern tests/remediation/test_t02.py already uses: geopandas is imported only inside the guarded path, so CI never needs ' +
'the geo stack). The test classes that genuinely need the dataset must keep skipping, not failing. Verify by simulating a geo-less environment: run ' +
'python -c with sys.modules poisoning or a subprocess whose sys.path excludes site-packages for geopandas, or simplest, uninstall nothing but import ' +
'the module with geopandas/pyproj blocked via an import hook, and show that collection now SUCCEEDS and the dataset-dependent tests SKIP. Report which. ' +
'[B] SECURITY 2: mechanical/apply.py:227 interpolates {source} RAW inside a single-quoted PL/pgSQL RAISE message (line :225 correctly uses ' +
'_literal(source)). Pass it as a percent-argument instead: RAISE EXCEPTION with a %n placeholder and the value as an argument, exactly as G0 does ' +
'(tests/remediation/test_gallery_audit.py has the regression test for that bug - copy its shape). Add the equivalent test for the mechanical lane. ' +
'IMPORTANT CONSEQUENCE: this changes the rendered guard text, therefore the emitted APPLY.sql and ROLLBACK.sql bytes change. Re-render them from the ' +
'versioned output/remediation/mechanical/PLAN.jsonl, publish the new sha256 values, and explain in your report that the DELIVERED files were re-rendered ' +
'after a guard fix while the production write itself is already journalled (remediation_change_log, run_stamp 2026-09-21_mechanical-country, 35 rows) and ' +
'is the authority. Do NOT attempt to re-collect the plan from the database. ' +
'[C] BACKEND B3: mechanical/apply.py:579-592 prints the post-write read-back but asserts nothing about its numbers, and this was already blind once: ' +
'evidence/05_apply.txt shows journal rows for this run stamp = 0 next to rows country = Georgia = 30, because VERIFY_SQL was not an f-string and every ' +
'journal metric read the literal placeholder. Parse the read-back numbers in Python and fail unless journal == len(records) and the planned rows now hold ' +
'the new value. Also add a test that would have caught the original blindness. ' +
'[D] SQL 6: the IF moved <> expected guard in the emitted transaction cannot fire in this lane: expected is count(*) from the same temp table the loop ' +
'counts, in the same transaction, and apply_remediation_change already raises unless n = 1. Either read expected from the plan independently ' +
'(command_verify does this - follow it) or remove the comparison AND state plainly in the lane documents that the primitive is the real instance that ' +
'guards this. Do not leave a decoration that reads like coverage. ' +
'[E] SQL 7 and BACKEND B8, found independently by two lenses: the mechanical rollback journals under the SAME change_key as the apply it undoes ' +
'(apply.py:208 hardcodes country-canonical:<site_id> for both directions). G0 does it correctly (a -rollback suffix). Give the rollback its own key, ' +
'and note that change_key is documented as the stable identity of the exact transition. ' +
'[F] SQL 8: apply.py:397-399 tests site_id_ref::text <> row_pk, which is NULL, not TRUE, for a NULL site_id_ref - so the one state the check exists to ' +
'catch passes as clean. Use IS DISTINCT FROM. Latent today (both lanes pass the id explicitly); it is the check itself that is blind. ' +
'[G] SQL 5 and BACKEND B4, found independently: mutation_sweep.py counts a SKIPPED case as fired (mutation_sweep.py:264-271 and :281-283 compute ' +
'fired = len(rows) - len(survived), and a case whose needle does not occur exactly once is logged SKIPPED and continued). Measured: evidence/10_mutation_sweep.txt ' +
'contains statement must commit ... SKIPPED needle appears 2x and then cases: 30 fired: 30 survived: 0 - and that 30/30 is quoted in APPLIED.md:300 and :389. ' +
'Count skipped separately, print it, and exit non-zero if any case was skipped: a blind spot is not a passed check. Then RE-RUN the sweep and report the ' +
'honest totals, and also report the attribution split the way I measured it (how many mutations were caught by a NAMED test versus only as a suite-level ' +
'failure with an empty fired name). ' +
'[H] SECURITY 4: migrations/0018:123-126 can journal a change where p_old = p_new: the conditional UPDATE matches, the round-trip check passes, and a ' +
'journal row with old_value = new_value is written. 0018 already refuses a truncation for the same journal-may-not-lie reason. Add a refusal at the top ' +
'of the function when p_old IS NOT DISTINCT FROM p_new, add a self-test case to scripts/remediation/0018_migration_selftest.sql, and RE-RUN that self-test ' +
'against production read-only if it can be run read-only; if it cannot, say so. The self-test must have teeth: show it failing with the guard removed. ' +
'[I] CI hygiene, two items. (i) DEPLOY 4a: .github/workflows/ci.yml:198 runs pytest WITHOUT -rs, so a skipped test is silent in the job that gates the ' +
'deploy. Add -rs (this project treats a silent skip as a tool error). (ii) DEPLOY 5: ci.yml:36-51 has no change filter matching migrations/** or ' +
'scripts/** - a push touching only those skips lint-backend, tests and container-scan, yet still deploys and applies migrations. Add migrations/** and ' +
'scripts/** to the backend filter so migration-only pushes run the code gates. ' +
'[J] BACKEND B5: scripts/remediation/mechanical/plan.py:59 and output/remediation/mechanical/PLAN.md:21 claim canonicalize_country_display_name is ' +
'"the function the pipeline routes unified_sites.country writes through". Measured: grep -rn canonicalize_country_display_name pipeline/ api/ finds only ' +
'the definition (pipeline/utils/country_lookup.py:572); its only callers are plan.py:143,590,637 and this lane tests. Its docstring says connectors ' +
'SHOULD route. So the sentence is not covered by the code. Correct the claim to what is true (the project display-name normalizer whose output equals the ' +
'proposal for these values; the load-bearing check is the reduction-versus-proposal comparison) in BOTH the code comment and PLAN.md. Do NOT reword the ' +
'docstring in country_lookup.py - that file is outside your trees. If you believe routing the pipeline through it is the better fix, do not do it: it is ' +
'out of scope and would need its own review. ' +
'[K] DEPLOY 4b, versioning: output/remediation/mechanical/PLAN.jsonl and APPLY.sql are currently gitignored as "regenerable on demand", but the lane ' +
'documents that this is FALSE: PLAN.md:60-61 states --collect/--write no longer reproduce the plan because production now holds the new values. ' +
'output/remediation/mechanical/ is your tree for this item only. Un-ignore PLAN.jsonl and APPLY.sql (keep ignoring nothing else), so the record of the ' +
'35-row write is versioned, and pin their sha256 in output/remediation/mechanical/evidence/11_fingerprints.txt (append the new values with a dated note). ' +
'Check the .gitignore negation ordering trap: a directory negation must precede file-level rules, and verify with: git ls-files --others --exclude-standard output/ ' +
'(NOT git check-ignore -v, which prints negated patterns and misleads). ' +
'[L] TESTS findings in test_mechanical.py: (i) :604 the reconciliation assertion is satisfied by POST_COMMIT_READS and by the header render_transaction ' +
'emits, so deleting invariant 2 leaves all 63 tests green - assert on the invariant unique text l.old_value IS DISTINCT FROM p.old_value. ' +
'(ii) :751 the delivered-rollback test proves only a count and value presence, and both values also occur in each row reason and evidence JSONB, so a ' +
'rollback that does not swap passes; make it pairwise: for each plan row assert the rollback tuple for that same site_id carries (old,new) swapped. ' +
'(iii) :744 the delivered plan is pinned by size and value-set only, never by site identity; add a small versioned expectation file ' +
'(output/remediation/mechanical/EXPECTED_ROWS.csv with site_id,finding_test_id) and assert the plan matches it row for row. ' +
'(iv) :584 the per-record loop for the first record is satisfied by the record own reason string; tighten it so it reads the INSERT tuple. ' +
'(v) :649 and REHEARSAL_READS assert a temp-table-left-behind metric that cannot fail: the query filters nspname = public while _country_plan is a ' +
'CREATE TEMP TABLE living in pg_temp_N, so the count is 0 regardless. Either fix the query to detect a real leftover (to_regclass or a pg_temp prefix) ' +
'or remove the metric and say why in the report. (vi) :47-49 the skip reason names "run plan.py --collect", but plan.py main calls _atlas() unconditionally ' +
'before the collect branch and _atlas raises when the shapefile is missing, so the advice leads into an exception; name the census T02 collect step instead. ' +
'(vii) tests #4-style check of your own new assertions: make sure none of them is satisfied by a comment or by prose in the file - that trap has now ' +
'produced false assurance FIVE times in this session. ' +
'When done: run the full gate, ruff check + format --check, mypy on scripts/remediation/mechanical/, the mutation sweep, and the mechanical re-emit. ' +
'Report raw outputs. Your report path is given in the task.';

const FIX2 = 'You are FIX-2, the gallery-audit and migration repairer. You own exactly these trees: scripts/remediation/gallery_audit/persist_verdicts.py, ' +
'tests/remediation/test_gallery_audit.py, migrations/0019_wiki_images_image_kind.sql, scripts/remediation/0019_migration_selftest.sql, and (for the ' +
'versioning item only) output/remediation/gallery_audit/. Fix these findings, each of which I verified myself: ' +
'[A] BACKEND B1, the most severe finding of the wave: a --plan AFTER the write DESTROYS the rollback artefact. command_plan calls emit(write, skipped, state) ' +
'at persist_verdicts.py:834, but the empty-plan check if not write: only comes at :840. emit writes PLAN.md, PLAN.jsonl, SKIPPED.jsonl, ROLLBACK.sql ' +
'(:819) and APPLY.sql (:820) unconditionally, and render_rollback (:600) / render_apply (:552) have no empty guard. So re-running --plan renders a ' +
'ROLLBACK.sql containing an empty VALUES list and expected integer := 0 - replacing the undo for the 105 landed rows. The lane documentation tells the ' +
'operator to run --plan as the FIRST of four post-write verification commands (output/remediation/gallery_audit/PLAN.md:132-135), so the trigger is ' +
'documented behaviour. Fix: move the emptiness check BEFORE emit, AND make render_rollback/render_apply raise PersistError on an empty plan. That is ' +
'fail-closed, and it makes the same mistake impossible even if a future caller forgets the order. Add a test that calls emit/command_plan with write=[] ' +
'and shows the pre-existing ROLLBACK.sql is NOT overwritten (today no test passes an empty write list - test_gallery_audit.py:334 passes one candidate). ' +
'[B] SQL 1 and BACKEND B2, found independently: --verify compares a run-local count with a TABLE-WIDE count, so it will raise a FALSE alarm on the next ' +
'legitimate write. persist_verdicts.py:1007 reads metrics["rows this run marked site_photo"] and :1011 fails when journal != marked, but the SQL at :535 ' +
'(identical at :503) is count(*) FROM wiki_images WHERE image_kind = site_photo - no run_stamp, no source_id, no restriction to the 105 planned ids. ' +
'The two numbers agree today only because G0 was the first writer of site_photo. Second half of the same finding: RUN_STAMP is a module constant (:78) ' +
'while the gallery batch is not a one-off, so a second batch journals under the same stamp and the two batches become indistinguishable. Fix: compare ' +
'IDENTITIES, not cardinalities - fail unless (a) every journalled row of this stamp still holds its new_value, and (b) every row in the table with ' +
'image_kind = site_photo has a journal row for this stamp. Keep the existing journal != planned check (PLAN.jsonl is an independent source and it is the ' +
'load-bearing comparison). If the table-wide number is useful, print it under an honest label and never compare it to the journal. Do NOT change RUN_STAMP ' +
'for the already-applied run - 105 rows in production carry the stamp 2026-09-21_gallery-verdicts-persist - but make the stamp derive from the batch so a ' +
'future batch cannot collide, and say clearly in your report what you did and did not change for the landed run. ' +
'[C] SQL 2: the G0 ROLLBACK.sql has no executable code path at all, three guards fewer than the apply, and has never been parsed by psql - its first parse ' +
'will be the real production rollback. The mechanical lane has cmd_rehearse_rollback (apply.py:547) with --rehearse-rollback (:677-681) and a proof ' +
'(evidence/09_rehearsal_rollback.txt shows NOTICE country repair 35 rows changed and journalled, then ROLLBACK). G0 has none: command_rehearse hardcodes ' +
'OUTPUT/APPLY.sql and the CLI has no rollback mode (:1028-1034). Missing versus the apply: the existence guard (apply :134-139), the curated-scope guard ' +
'(source_id = ancient_nerds, apply :141-149 - source_id does not appear in ROLLBACK.sql at all), and the journal-versus-data invariant (apply :185-195). ' +
'Fix: port the apply guard block into the rollback generator rather than hand-shortening it, and add a --rehearse-rollback mode mirroring the mechanical ' +
'lane (transform COMMIT to ROLLBACK, plus its own reads). Prove it by running --rehearse-rollback and showing psql parses and rolls back, with ' +
'ON_ERROR_STOP on. ' +
'[D] SQL 3: gallery_audit/ROLLBACK.sql is 105 tuples on ONE 86.7 KB line, because persist_verdicts.py:658 joins with "," while :419 joins with ",\\n". ' +
'Consequence: the file cannot be read by line-oriented tools, cannot be diffed, and the SQL lens could only verify the inversion by falsification - which ' +
'is exactly why it could not check all 105 tuples. Fix to ",\\n".join, re-render, and then verify the inversion PAIRWISE over all 105 tuples (the mechanical ' +
'lane is the model). ' +
'[E] SECURITY 1: persist_verdicts.py:416-419 passes v.slug into an f-string un-repr-ed, the only external value in either lane that is not - on the same ' +
'lines filename is !r (:417), kind is !r (:418), the evidence blob is json.dumps (:415), and evidence_for reprs every external value. v.slug is an ' +
'external filesystem name (load_verdicts:133). _sql_literal (:392-395) only doubles apostrophes, so a directory name containing a newline could put a ' +
'line-initial backslash into a script that is piped to psql as a file. The exploit is UNPROVEN (the lens says so itself: no shell, no DB, it could not ' +
'confirm psql fires on it inside an open literal) - so fix the ASYMMETRY and say plainly in your report that the exploit remains unproven. Make it !r like ' +
'its neighbours, and additionally make _sql_literal refuse control characters outright (fail closed), with a test. ' +
'[F] SQL 9: inside the transaction the mechanical lane RAISEs on a journal-scope violation while G0 only prints, so G0 aborts after the COMMIT instead of ' +
'before it. Move the same check into G0 guard block as a RAISE. Unreachable today; it is the difference between fail-closed and fail-late. ' +
'[G] BACKEND B6: persist_verdicts.py:59-60 claims --verify compares VOCAB with the migration CHECK constraint, but VOCAB (:61) is used only for input ' +
'validation (:168,:171) and verify_sql carries a THIRD hardcoded copy of the vocabulary (:543-545) and never reads VOCAB. So a drift between them would make ' +
'load_verdicts assert something about a foreign file that was never checked. Build the list in verify_sql from sorted(VOCAB), or genuinely compare against ' +
'pg_constraint, and correct the comment to describe what actually happens. ' +
'[H] SECURITY 3 and BACKEND B7, the same missing integrity link: --apply reads APPLY.sql and sends it to production with no cryptographic tie to the plan ' +
'it was rendered from (persist_verdicts.py:952-966 validates only the header row count). No privilege gain - writing that file needs the same access as ' +
'editing the generator - but the undo a reviewer checks is unverified. Add a hash of the rendered record set to the header of BOTH APPLY.sql and ' +
'ROLLBACK.sql at render time and verify it before sending, failing closed. Related (B7): run_psql uses subprocess.run(timeout=900) and lets ' +
'subprocess.TimeoutExpired escape; main catches only PersistError, so a timeout mid-write surfaces as a traceback that does not say whether the ' +
'transaction committed, and a retry then reports APPLY FAILED psql exit=3 for a write that actually landed. Catch the timeout, print plainly that the ' +
'outcome is UNKNOWN and that remediation_change_log for the run stamp must be checked before retrying, and treat a retry whose guard violation is ' +
'accompanied by a complete journal as already-applied. Also add ssh ConnectTimeout/keepalive so a hung channel cannot sit for 900 s. ' +
'[I] DEPLOY 3 and TESTS, both found independently: migration 0019 re-runs on EVERY deploy because it is deliberately not in applied_migrations, and ' +
'(i) ALTER TABLE ... ADD COLUMN IF NOT EXISTS still takes ACCESS EXCLUSIVE on a ~49,691-row table under lock_timeout=20s, so a concurrent reader can make ' +
'the deploy fail for a reason unrelated to the change, and (ii) its self-test does a REAL UPDATE on a real row (0019:97-118) and (iii) SELECT id FROM ' +
'wiki_images LIMIT 1 picks an arbitrary row and then requires it to be NULL, so on a database where that row already carries a kind the migrate step aborts ' +
'with a spurious SELFTEST FAILED. Make a re-run a true no-op: guard the ALTER behind a catalog check and guard the writing self-test so it only runs when ' +
'the column does not yet exist (the read-only variant already exists as scripts/remediation/0019_migration_selftest.sql). Keep teeth: the self-test must ' +
'still fail if the CHECK constraint is removed - prove that with a mutation against a scratch/throwaway context, NOT against production. ' +
'[J] TESTS 1, deploy-blocking: test_gallery_audit.py:145 test_load_verdicts_on_the_real_input_finds_105_rows calls load_verdicts() on the default base ' +
'ROOT/video-assets/shorts, which .gitignore excludes, and load_verdicts RAISES when the directory is missing - so in a clean checkout the test ERRORS ' +
'rather than skipping, and the tests job goes red on the next push to main. The other two data dependencies in the wave are guarded (needs_dataset, ' +
'needs_deliverable); this one was forgotten. Guard it with skipif on the directory existing, or better, move the stills-only shape of the 16 selection.json ' +
'files into a small tracked fixture and keep the 105-row pin as an explicitly-labelled local-only check. Choose and justify. ' +
'[K] TESTS 3: test_gallery_audit.py:359 and :367 re-implement the rehearsal transform INLINE (tmp_path is never used, which is the tell) - they assert on ' +
'their own arithmetic, so the module transform and its refusal guard in command_rehearse (the check that APPLY.sql ends in exactly one COMMIT) are ' +
'completely untested. Consequence if the strip breaks: --rehearse runs the real statement to COMMIT against production and prints REHEARSAL OK - a ' +
'rehearsal that applies the 105 rows. Fix by extracting a pure rehearsal_of(script: str) -> str into the module and asserting on it, and by monkeypatching ' +
'run_psql to feed command_rehearse both a good file and a two-COMMIT file. The mechanical lane equivalent (A.rehearse) is already tested properly - copy ' +
'its shape. ' +
'[L] TESTS 4: two of three assertions in the IS NOT DISTINCT FROM test (test_gallery_audit.py:239 and :245) are satisfied by the module own comment: ' +
'"IS NOT DISTINCT FROM" appears in render_apply header comment (persist_verdicts.py:557) and in a docstring (:31), and the second assertion looks for ' +
'the literal image_kind = NULL which can only ever appear in prose (persist_verdicts.py:456). Fix: apply the existing code-only filter ' +
'(line for line in sql.splitlines() if not line.strip().startswith("--")) to the FIRST assertion too, and either delete the second or assert on the ' +
'comparison operator of guard 3. Note the first assertion on w.image_kind IS DISTINCT FROM p.old_value DOES have teeth; only its neighbours do not. ' +
'[M] TESTS 8: the documented past failure of verify_sql (it referenced _kind_plan, which is ON COMMIT DROP, so a successful write was reported as ' +
'EXIT_VERIFY_FAILED) has NO regression test. Add one line: assert "_kind_plan" not in pv.verify_sql(). ' +
'[N] Versioning: output/remediation/gallery_audit/PLAN.jsonl and APPLY.sql are gitignored as "regenerable", but that premise is false for the same reason ' +
'as the mechanical lane: the input video-assets/shorts/*/selection.json never leaves the workstation. Un-ignore them (this tree only), keep ROLLBACK.sql ' +
'versioned as it already is, and pin the sha256 of the re-rendered files in the lane evidence. Verify with: git ls-files --others --exclude-standard output/ ' +
'- NOT git check-ignore -v, which prints negated patterns and will mislead you. ' +
'[O] After the re-renders in A/D/H, the delivered APPLY.sql and ROLLBACK.sql WILL CHANGE BYTES. Re-render them, publish the new sha256 values, and state ' +
'clearly in your report that the production write itself is already landed and journalled (remediation_change_log run_stamp 2026-09-21_gallery-verdicts-persist, ' +
'105 rows) and remains the authority - the re-rendered files are the record and the undo, never to be re-applied. Run --plan, --rehearse, --rehearse-rollback ' +
'and --verify again and report each one real output. Do NOT run --apply. ' +
'When done: run the full gate and report raw output. Your report path is given in the task.';

return await runs.all([
  {
    key: 'fix1',
    agent: 'fixer',
    task: SHARED + FIX1,
    output: 'output/remediation/wave6/FIX1_REPORT.md',
    context: 'fresh',
  },
  {
    key: 'fix2',
    agent: 'fixer',
    task: SHARED + FIX2,
    output: 'output/remediation/wave6/FIX2_REPORT.md',
    context: 'fresh',
  },
]);
