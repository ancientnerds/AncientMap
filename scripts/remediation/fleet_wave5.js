// Wave 5: adversarial review of wave 4's three lane trees plus G0.
//
// Wave 4 wrote to production in two places - MECHANICAL's 35 country rows and G0's 105
// image_kind rows - and PILOT produced the cost basis for the whole Phase-3 decision. All
// three lanes reported success. This wave exists because a lane's own report is not a review,
// and because different QUESTIONS find different defects (a second reviewer with the same
// question is money burnt).
//
// Every lane here is READ-ONLY. The five `pruefer-*` lenses have no shell and no write tool,
// so their artefacts are handed to them as FILE PATHS - a role that can fetch nothing must be
// given the files it is to judge. `gegenpruefer` is the only one with a shell, because it is
// asked to MEASURE rather than to read.
//
// `pruefer-frontend` is deliberately absent: none of these three lanes touches React or SSR.
// Loading it would be a question without a subject.

const SHARED = `
PROJECT: C:/PythonProjects/AncientMap (branch main, Windows). Interpreters: read only, this
wave changes nothing. The plan served is docs/procedures/SITES_DB_REMEDIATION_2026-09.md.

WHAT HAPPENED (established, independently audited, not up for re-litigation)
An audit/remediation of the 5,004 curated sites (unified_sites.source_id='ancient_nerds') in a
production Postgres. Phase 1 produced eleven census checks T01..T11; the factual union of
T01/T02/T03/T05 is 1,840 sites. Three writes to production have landed, each through the
journalled primitive apply_remediation_change (migrations/0017):

  1. HERO     - 5,438 journal rows over 2,719 sites (wiki_images.is_hero, true<->false pairs).
  2. MECHANICAL - 35 rows, unified_sites.country: 'Georgia (country)' -> 'Georgia' (27) and
                'Chile, Easter Island' -> 'Chile' (8), run stamp 2026-09-21_mechanical-country.
  3. G0       - 105 rows, wiki_images.image_kind = 'site_photo', run stamp
                2026-09-21_gallery-verdicts-persist.

THE ARTEFACTS YOU ARE TO JUDGE (read these files; do not go looking for others)
* Mechanical lane: scripts/remediation/mechanical/{plan.py,apply.py,mutation_sweep.py},
  tests/remediation/test_mechanical.py, and
  output/remediation/mechanical/{PLAN.md,PLAN.jsonl,SKIPPED.jsonl,APPLY.sql,ROLLBACK.sql,REHEARSAL_ROLLBACK.sql,APPLIED.md,evidence/01..12}
* G0 lane: scripts/remediation/gallery_audit/persist_verdicts.py,
  tests/remediation/test_gallery_audit.py, and
  output/remediation/gallery_audit/{PLAN.md,PLAN.jsonl,SKIPPED.jsonl,APPLY.sql,ROLLBACK.sql}
* PILOT lane: output/remediation/phase3_pilot/{PILOT.md,PILOT.jsonl,COST.md,BRIEF_GAPS.md,http_get.py,build_pilot_jsonl.py,fetch_log.jsonl}
* Supporting: output/remediation/phase3_worklist/WORKLIST.jsonl, migrations/0017..0019,
  docs/procedures/FIELD_CONTRACT.md, .githooks/pre-push, .github/workflows/ci.yml, .gitignore

HOW EVIDENCE WORKS HERE (the culture of this repo, not decoration)
* No claim without proof: a file:line, or the real output of a command you ran. A number you
  did not measure is not a number. Say 'unverified' and say why rather than guessing.
* A test whose failure you cannot observe is not a test. An assertion that would still pass
  with the guarded behaviour deleted has no teeth.
* A false positive is not a finding. If a file is correct, say it is correct and say what you
  checked to decide that - a reviewer who reports nothing must still show what was examined.
* Report findings as: file:line, what is wrong, the evidence, and what it would cost. Rank by
  consequence, not by how easy the finding was to make.

OUTPUT: your findings as your final message. There is no file to write - you have no write
tool, by design. Be specific and terse; a finding without a file:line will be discarded.
`;

const SQL_LENS = `
YOUR ONE QUESTION: is each ROLLBACK.sql the exact inverse of its APPLY.sql, and can any guard
pass while the write does something other than what the plan says?

Concretely, for BOTH the mechanical lane and G0:
1. Read APPLY.sql and ROLLBACK.sql side by side. Are they set-based over the same rows, with
   the same WHERE conditions, so that the rollback touches exactly the rows the apply touched
   and restores exactly the old value? Look for: a rollback keyed on the NEW value instead of
   the old one, a missing condition, a count that does not have to match, an ordering
   dependency, or a rollback that would also fire on rows another run changed.
2. Are the guards real? A guard that cannot fail is decoration. For each guard, name the
   concrete row state that would make it refuse, and check whether that state is reachable.
   Note especially: a CHECK constraint or guard evaluated by a statement that touches 0 rows is
   never evaluated at all.
3. Watch NULL semantics and quoting: '=' against a NULL, a literal embedded inside a quoted
   RAISE message, a value from an external file reaching a literal. One of these already
   produced a real syntax error in this lane.
4. Does the emitted SQL match the plan file row for row - same count, same ids, same old and
   new values? A plan and an apply that disagree is the bug that survives every other check.
`;

const BACKEND_LENS = `
YOUR ONE QUESTION: does either write path have a route that touches a row outside its planned
set, writes a value it did not plan, leaves a half-written state if it dies mid-way, or turns
'could not check' into 'checked and clean'?

Read scripts/remediation/mechanical/{plan.py,apply.py} and
scripts/remediation/gallery_audit/persist_verdicts.py, plus the emitted APPLY.sql for each, and
hunt for:
1. A path where the write's scope is wider than the plan's scope - a missing
   source_id='ancient_nerds', an id taken from an argument rather than from the plan, a join
   that can fan out and update two rows where the plan saw one.
2. A silent fallback: an except that continues, a default that invents a value, a '.get(key,
   something_plausible)', a bare 'if not x: return []'. Compare against the plan's rule that
   an undecidable value must become 'unverifiable'/'review', never a guess.
3. Transaction and failure behaviour: is the write one transaction? If the process dies after
   the UPDATE but before the journal insert, is the world consistent? Is the rollback emitted
   before the apply, so a death cannot leave an un-undoable write?
4. Restart safety: does anything a restart runs later overwrite what was written? Check
   docs/procedures/FIELD_CONTRACT.md and pipeline/lyra/data_patches.py for the columns written
   here, and say plainly if a restart writer can reach unified_sites.country or
   wiki_images.image_kind.
5. Does the post-hoc verification prove the claim it reports? Name anything it asserts that
   would also pass on a wrong write.
`;

const TEST_LENS = `
YOUR ONE QUESTION: which assertions in these test files cannot fail - that is, would still pass
if the behaviour they are supposed to guard were deleted or inverted?

Files: tests/remediation/test_mechanical.py (63 tests), tests/remediation/test_gallery_audit.py
(38 tests), and the modules they test in scripts/remediation/mechanical/ and
scripts/remediation/gallery_audit/.

For each test file:
1. List the tests whose assertion is true for every possible implementation - an assertion on a
   substring that the file's own comments also contain, an assertion that the code contains
   something it cannot not contain, a test that only checks an exit code where that code
   coincides with another error path, an assertion inside a branch never taken, a test that
   asserts a value equals itself.
2. Name the tests that DO have teeth, and say which mutation would kill each - one line per
   test is enough, do not exhaustively enumerate all 101.
3. Look specifically for the failure modes this project has already hit: an assertion matching
   the code's own explanatory comment; a 'teeth' test written as UPDATE ... WHERE false, which
   touches no rows so the constraint under test is never evaluated; an exit code that collides
   with Python's unhandled-exception code 1; a test asserting on a temp table dropped at COMMIT.
4. Does any test assert the number of rows a write touched without also proving the rows are
   the RIGHT rows?
`;

const DEPLOY_LENS = `
YOUR ONE QUESTION: do these three lanes' artefacts need to reach production through the deploy
path, and would CI accept them exactly as they stand?

Read .github/workflows/ci.yml, .githooks/pre-push, .gitignore, migrations/0017, 0018, 0019,
scripts/remediation/001{7,8,9}_migration_selftest.sql, the 'Remediation deliverables' and
'G0: the verdict persister' blocks in .gitignore, and git ls-files for the three lane trees.

Answer:
1. Which of these artefacts MUST arrive on the VPS for the remediation to remain reproducible
   and undoable, and which are workstation-only? State the deploy step that would carry each
   (ci.yml does 'git checkout -- .' then 'git pull' then 'git lfs pull' - so an artefact that
   is gitignored never arrives, and one that is modified on the VPS is discarded).
2. Do the three migrations behave under CI's migration loop, which re-applies every migration
   body on each deploy? 0017 and 0018 and 0019 are deliberately NOT in applied_migrations, so
   they are re-applied every time: prove from the SQL that a second application is a no-op, or
   say which statement is not.
3. Would any CI gate reject these files as they stand: ruff, ruff format --check, mypy (scope:
   api/ and pipeline/ only?), vulture, semgrep, gitleaks, trivy, knip, the pytest subset?
   Note explicitly which of these lanes' files CI does NOT check at all - an unchecked file is
   not a checked file.
4. Is anything in these trees a secret, a credential, or a production datum that must not be
   in git? The evidence directories contain raw fetched web bodies.
`;

const SECURITY_LENS = `
YOUR ONE QUESTION: can any value that reaches the emitted SQL from an external file escape its
literal, and can any journalled evidence be forged or misattributed?

Read scripts/remediation/gallery_audit/persist_verdicts.py (especially _sql_literal and the
evidence rendering), scripts/remediation/mechanical/{plan.py,apply.py}, and the emitted
APPLY.sql/ROLLBACK.sql of both, then check:
1. Every path by which a string from outside the program (a filename from
   video-assets/shorts/*/selection.json, a 'reason' string, a wiki title, a URL) reaches the
   generated SQL. Is each one escaped, and is the escaping the only thing standing between the
   file and the statement? A quote, a backslash, a newline, a NUL, or a semicolon in that
   string - what does the generated SQL do?
2. Are the plan and the apply derived from the SAME input read, or could the file change
   between reading and writing? Is anything re-read between the plan and the apply?
3. Can the journal be written for a row that was not actually changed, or can a change land
   without a journal row? The whole undo depends on the journal being complete and honest.
4. The write runs as the database superuser 'ancient_map' over ssh. Is there a credential,
   a password, or a connection string in any file in these trees, in the evidence, or in any
   committed output?
`;

const GEGENPRUEFER = `
YOUR ONE QUESTION: are PILOT's numbers reproducible, or is its measured cost basis built on
claims that do not survive being measured?

You are the ONLY role in this wave with a shell. MEASURE - do not read and agree. Use
./.venv/Scripts/python.exe, never bare python, and set PYTHONIOENCODING=utf-8.

Candidates to attack (each is a claim PILOT makes; refute or confirm each, with the command
you ran and its real output):
1. 'The worklist has 2,210 phase-3 findings of which only 8 are proposal=set (0.4%).' Derive
   both numbers yourself from output/remediation/phase3_worklist/WORKLIST.jsonl. State the
   exact predicate you used. If your predicate gives a different number, say which predicate
   is right and why the other is wrong - do not average them.
2. '285 coords-only sites can never produce a write.' Reproduce it or refute it.
3. PILOT.jsonl's own split: 40 rows, 28 CORRECT / 11 WRONG / 1 UNVERIFIABLE, 6 field-level
   'set' proposals, 110 evidence items, 15 census findings mapped. Count them from the file.
   Then check whether the evidence of any row actually supports the status that row claims -
   pick the 3 rows that look weakest and say what is missing.
4. COST.md: does it really refuse to average the plan's two contradictory cost anchors? Quote
   the lines. Does its per-site token figure come from a measurement or from the plan?
5. PILOT.md section 5 claims '3 defects the census never named'. Check each of the three
   against the census output and say whether the census really misses it, or whether the
   census covers it and PILOT's claim is wrong. A claimed gap that is not a gap is a false
   finding, and false findings cost as much as missed ones.

Report each verdict as CONFIRMED or REFUTED with the command and its output. A refutation
without a command is an opinion.
`;

const TASKS = [
  { key: "SQL", body: SQL_LENS, agent: "pruefer-sql" },
  { key: "BACKEND", body: BACKEND_LENS, agent: "pruefer-backend" },
  { key: "TESTS", body: TEST_LENS, agent: "pruefer-tests" },
  { key: "DEPLOY", body: DEPLOY_LENS, agent: "pruefer-deploy" },
  { key: "SECURITY", body: SECURITY_LENS, agent: "pruefer-security" },
  { key: "GEGENPRUEFER", body: GEGENPRUEFER, agent: "gegenpruefer" },
];

const children = TASKS.map(function (t) {
  const task = SHARED
    + "\n================================================================\n"
    + "YOUR ASSIGNMENT\n"
    + t.body;

  return {
    key: t.key,
    agent: t.agent,
    task: task,
    model: "opencode-go/deepseek-v4.1-flash",
    context: "fresh",
    timeoutMs: 2400000,
    usageBudget: { tokens: { hard: 3000000 } },
    control: { activeNoticeAfterMs: 600000, needsAttentionAfterMs: 600000 },
  };
});

return await runs.all(children);
