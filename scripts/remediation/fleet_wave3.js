// Wave 3 of the remediation: the first real Phase-2 repair (heroes), the census gap that the
// gold standard exposed (the E3 scope window), and the worklist that de-risks the expensive
// Phase 3 before a token of it is spent.
//
// Two lanes write files, on disjoint paths; one lane is read-only recon. Only HERO is allowed
// to touch the production database, and only after writing its plan to disk first.
//
// Loaded via workflowScriptPath so the briefs are byte-exact.

const SHARED = `
PROJECT: C:/PythonProjects/AncientMap (branch main, Windows). Always use the project
interpreter ./.venv/Scripts/python.exe, NEVER bare python. Set PYTHONIOENCODING=utf-8.
The plan you serve is docs/procedures/SITES_DB_REMEDIATION_2026-09.md (853 lines).

WHAT THIS IS
A full deterministic audit of the 5,004 curated sites (unified_sites.source_id =
'ancient_nerds') in a production Postgres, so that every entry ends up either fixed,
verified correct, or explicitly flagged for a human. All ten census checks of Phase 1 are
written, run and audited. Wave 2 closed the two restart-overwriter landmines and produced a
measured false-negative rate. You are part of the wave that turns the census into repairs.

HOW EVIDENCE WORKS HERE (this is the culture of this repo, not decoration)
* No claim without proof: a file:line, or the real output of a command you ran. If you did
  not run it, say 'unverified' and say why. A number you did not measure is not a number.
* Never weaken a check to make it pass. If a gate is red, the work is not done - report the
  redness with its output. Editing a test, a threshold or an expectation so it goes green is
  the single forbidden act in this project.
* Never invent data. Where a value cannot be decided from evidence, the honest output is
  'unverifiable', never a plausible guess. A wrong value is worse than an empty one.
* Never swallow an error to produce an empty result. 'Could not check' must never turn into
  'checked and clean' - that inversion is the most dangerous failure mode of this whole
  effort. Errors are raised, recorded and reported.
* Judge the tooling, do not obey it: a linter or plugin message is a hypothesis. Decide
  whether it is a real defect and fix the real ones. Several findings already triaged here
  are false positives (for example md5 used to reproduce Wikimedia's own upload-directory
  layout - swapping it to sha256 would break the check to please the checker).
* Three times in this session a number that could not be true turned out to be a bug in the
  MEASURING code, not a fact about the world. When your own result looks impossible, suspect
  your instrument first, and say so in the report.
* The production database may only be reached read-only unless your brief explicitly grants
  writes. Every write needs a conditional WHERE clause carrying the old value, and a journal
  entry. Never DELETE, never a bare UPDATE without a condition.

GATES (run them before you claim anything; the project's CI runs them)
  ./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"
  ./.venv/Scripts/python.exe -m ruff check <your files>
  ./.venv/Scripts/python.exe -m mypy <your files>
  -rs is mandatory: skips are silent otherwise. Skipped is not passed.
  Known and expected when the whole suite runs: 3 skips (two refactors, one env-gated), 57
  deselected, currently 1954 passed.

DO NOT: commit or push (a push to main is a live deploy); run git checkout / git clean /
git stash; edit a file another lane owns. Leave your changes in the working tree and report
exactly which files you touched.

ANOTHER LANE IS LIVE IN THIS TREE. A detatched link sweep may invoke
scripts/remediation/census/run.py at any moment, so any file you edit must be importable
after every single edit you make - never leave a half-written module.

REPORTING: end with a short report containing (1) what you produced, with paths; (2) the
exact commands you ran and their real results; (3) anything you could NOT verify, labelled
as such; (4) anything you found wrong that you did not fix, with the reason.
`;

const HER0 = `
ASSIGNMENT: Phase 2 step 1 of the plan - the mechanical hero repair. This is the first
production write of the remediation and you are authorised to make it (owner decision E1),
under the conditions below. Read plan section "Phase 2" item 1 and section 6.3 before
writing any code.

THE DEFECT. HERO_WIDTH = 800 (api/routes/wiki_images.py:22) and THUMB_WIDTH = 800
(pipeline/wiki_image_downloader.py:47) are the same value, so the image chosen as a hero is
no larger than a gallery thumbnail. 3,858 of the 49,691 images carry is_hero. The plan says
3,264 of those heroes can be replaced by an image the site already has locally, without any
download; the rest would need an original fetched via commons_page_url.

ALREADY PROVEN - DO NOT RE-LITIGATE, BUT DO RE-VERIFY CHEAPLY
* wiki_images.is_hero has NO restart writer. The only writers are API routes
  (api/routes/sites.py, api/routes/wiki_images.py) and manual scripts. Therefore a hero
  change survives a container restart and a deploy. The wave-2 audit established this with
  file:line evidence; spot-check it rather than re-deriving it.
* A backup exists: a full pg_dump plus per-table CSVs under backups/2026-09-20_remediation/
  (dump 654,604,671 bytes). A restore drill has passed. You do not need a new backup, but
  say in your report which backup you relied on and how you confirmed it exists.

THE TRAP THAT MATTERS MOST
Do NOT select replacement heroes by wiki_images.width. T09 measured that the stored width
disagrees with the true Commons dimension for 11,653 rows - the column is exactly the thing
under suspicion. Real dimensions for 46,070 Commons files are already cached at
output/remediation/cache/commons_imageinfo.json (a wrapper object; read its keys, do not
guess them). Select on THAT. State in your report which source you used and why.

PREFERRED SOURCE OF CANDIDATES
T10's gallery tiers are on disk. Tier D ('clear') means: the file is in the site's own P373
category, carries no off-topic word signal, and the site's own name appears in the filename
or the Commons object name. An image in tier D is the image least likely to be thrown out by
the later gallery audit, so a hero moved onto one is audit-resistant. Prefer tier D, then
tier C, and never a tier A/B ('suspect') image. Read
scripts/remediation/census/tests/t10_gallery_tiers.py to learn the tier values from the code
- do not guess the encoding from a report.

WHAT TO DO, IN THIS ORDER
1. Compute the repair offline from the snapshot. Write the complete plan to
   output/remediation/hero_repair/PLAN.jsonl (one record per row to change: image id, site
   id, old is_hero, new is_hero, the condition that justifies it, and the reason) plus
   output/remediation/hero_repair/PLAN.md with the counts and the method. Verify or refute
   the plan's 3,264. If you get a different number, that is a finding to report with
   evidence - do NOT tune your rule to reach 3,264.
2. Write the rollback statement to output/remediation/hero_repair/ROLLBACK.sql BEFORE
   applying anything, and satisfy yourself that running it restores the exact prior state.
3. Apply, in ONE transaction, using the journal function defined in
   migrations/0017_remediation_change_log.sql (read it; do not invent its signature). Every
   UPDATE carries the old value in its WHERE clause. No DELETE.
4. Verify after the write by querying production read-only: the per-site hero count, the
   total is_hero count, and that no site lost its hero. Report the real numbers.
5. State clearly whether one hero per site is an invariant you enforced or merely observed.

SCOPE OF WRITES: unified_sites.source_id = 'ancient_nerds' only. wiki_images holds rows for
other sources too - a write that is not scoped by site is a defect, not a shortcut. Reach
production exactly as the project does: ssh ancientnerds then docker exec ancient_nerds_db
psql -U ancient_map -d ancient_map. Every query you run against production must be
read-only except the single journaled transaction in step 3.

YOU MAY CREATE: scripts/remediation/hero_repair/** , tests/remediation/test_hero_repair.py ,
output/remediation/hero_repair/**. Do NOT touch scripts/remediation/census/** ,
scripts/remediation/fleet_wave*.js , docs/procedures/** , or another lane's output.
`;

const SCOPE = `
ASSIGNMENT: close the largest gap the gold-standard measurement exposed - the E3 scope
window, which no census check covers even though the plan's own definition of 'clean'
requires it.

THE EVIDENCE FOR THIS TASK (already gathered by the supervisor - verify, then build)
* Plan section 1.3, 'Definition of clean', includes this bullet: 'The site is in scope (E3),
  or flagged as out of scope and hidden.' So a census that cannot test E3 cannot certify a
  site clean, and the acceptance criterion 'every site has a record holding the result of all
  ten tests' is not reachable without it.
* Plan section 1.2 E3 states the rule: 'Cutoff: Americas through 1500 AD, rest of world
  through 500 AD.' E4 adds: 'Flag it AND hide it platform-wide. A new column for this is
  approved - but only during implementation.'
* Plan section 7 gate S12 measures exactly this and reports 4,920 pass / 84 fail.
* The gold-standard sample found 3 E3 errors among 40 blinded errors, and none of them was
  flagged by any of the ten checks. That is the false-negative source you are closing.
* An earlier baseline measurement recorded 69 violations rather than 84. RECONCILE THAT
  DIFFERENCE and report it. A plausible cause is a boundary rule (<= versus <), a region
  rule, or a different date column; find out which it is by running both rules over the
  snapshot, and state the answer with the query. Do not split the difference and do not
  assume the plan is right.

WHAT TO BUILD
A census check as the eleventh module, scripts/remediation/census/tests/t11_scope_window.py,
in exactly the style of its siblings (read t04_site_type.py as the reference, and
model.py / run.py for the contract: TEST_ID, NAME, DIMENSION, optional applies_to, optional
collect, run(ctx) -> list[Finding]).

This check needs NO network: scope is a pure function of stored values (period_start, and
the region the coordinates fall in). Text in collect() that fetches something is a defect
here. Work out from the code how the region is determined for an existing check (T02 does
administrative point-in-polygon work) and reuse it rather than inventing a second geography.

Register it in run.py's REGISTRY exactly as T01..T10 are registered. That file is shared
with a live detached sweep, so make that one-line edit last and confirm run.py still imports
immediately afterwards. Do not restructure run.py.

Then tests in tests/remediation/test_t11.py, including the mandatory mutation proof: force
run() to return [] and show exactly how many of your tests fail, then restore the file
byte-identically and state the sha256 before and after. A test that passes both ways proves
nothing.

REPORT: (a) the reconciled scope rule with the query that decides it, and the number of
violating sites today; (b) the module and test paths; (c) the real gate output; (d) the
mutation result with the sha256; (e) any site where the rule cannot be decided from stored
data, named, with the reason - those must be flagged for review, never silently passed.

YOU MAY CREATE: scripts/remediation/census/tests/t11_scope_window.py ,
tests/remediation/test_t11.py , output/remediation/scope_scratch/**. You may make exactly one
one-line edit to scripts/remediation/census/run.py (the registry entry). Do NOT touch any
other census module, any api/ or pipeline/ code, or another lane's output.
`;

const FACTS = `
ASSIGNMENT: read-only reconnaissance for Phase 3, the expensive two-stage factual audit. Do
not fix anything and do not write to the database. Your product is a worklist and a costed,
batched plan that lets the supervisor spend that budget deliberately instead of discovering
its size halfway through.

THE PROBLEM YOU ARE SOLVING
Plan Phase 3 is 'Only for sites Phase 1 could not conclusively settle', at roughly 40,000
tokens per site across a finder stage and an adversarial reviewer stage, 5 sites per agent.
The naive reading of 'flagged by Phase 1' is useless: the census flags 4,010 sites in T10 and
all 5,004 in T09, so 'has any finding' means almost every site. The worklist must therefore
be built from the FACTUAL dimensions only, and you must say exactly which test ids and
dimensions you counted as factual and which you deliberately excluded, and why.

BUILD THIS
1. output/remediation/phase3_worklist/WORKLIST.md and .jsonl: every site that a factual check
   flagged, deduplicated across checks, with per-site which checks flagged it, in which
   dimension, with the current value and the proposed value where one exists. Count it.
   Give the totals per dimension and the size of the intersection and the union.
2. A batching plan: how many agents, how many sites each, how many batches, in what order
   (worst first), and the arithmetic that produced the numbers - not a vibe. State how many
   agent runs that is and what the wall clock would be at the concurrency the plan measured
   (10-14 parallel).
3. Name the sites that no deterministic check can settle at all, separately from the ones a
   check can settle mechanically. The first set is Phase 3; the second set is a script, and
   conflating them is how a $1,000 workstream becomes a $1,400 one.
4. Read plan sections 4.3 (the false-alarm patterns the reviewer must be briefed on) and the
   Phase 3 method, and draft the exact finder brief and the exact reviewer brief that a
   Phase-3 lane would be given - including that the reviewer must refute with its OWN
   research rather than re-reading the finder's evidence, and that only refuted=false is
   applied. That draft is a deliverable, not commentary.

EVIDENCE DISCIPLINE FOR THIS LANE
The census outputs are output/remediation/run_t01 .. run_t10 (census.jsonl and
findings.jsonl each). The top-level output/remediation/findings.jsonl is NOT the union - it
holds only one check. Build the union yourself from the run_t* directories, and say in the
report how you verified you had all ten.

YOU MAY CREATE only output/remediation/phase3_worklist/**. Do not edit any source file, do
not write to the database, do not commit.
`;

const TASKS = [
  { key: "HERO", body: HER0, slow: true },
  { key: "SCOPE", body: SCOPE, slow: true },
  { key: "FACTS", body: FACTS, slow: false },
];

const children = TASKS.map(function (t) {
  const task = SHARED
    + "\n================================================================\n"
    + "YOUR ASSIGNMENT\n"
    + t.body;

  return {
    key: t.key,
    agent: t.key === "FACTS" ? "scout" : "worker",
    task: task,
    model: "opencode-go/deepseek-v4.1-flash",
    context: "fresh",
    timeoutMs: t.slow ? 4200000 : 2400000,
    usageBudget: { tokens: { hard: 6000000 } },
  };
});

return await runs.all(children);
