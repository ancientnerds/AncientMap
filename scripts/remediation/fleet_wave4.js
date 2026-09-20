// Wave 4 of the remediation. Wave 3 landed the first production write (the hero flag: 5,438
// journalled rows over 2,719 sites, audited line by line). Wave 4 spends that position:
//
//   MECHANICAL - the cheap deterministic wins, applied with the same journalled primitive.
//   PILOT      - price ONE Phase-3 batch of five sites before funding 363 of them. The plan's
//                own cost anchors contradict each other by exactly 2x, so we measure instead
//                of choosing. Read-only.
//   GALLERY    - the one design question that cannot be answered by reading code: what the
//                gallery audit must decide, and whether anything here can decide it visually.
//                Read-only recon + a costed design.
//
// Exactly one lane (MECHANICAL) may touch the production database. PILOT and GALLERY are
// read-only, so the one-writer rule holds.
//
// Loaded via workflowScriptPath so the briefs are byte-exact.

const SHARED = `
PROJECT: C:/PythonProjects/AncientMap (branch main, Windows). Always use the project
interpreter ./.venv/Scripts/python.exe, NEVER bare python. Set PYTHONIOENCODING=utf-8.
The plan you serve is docs/procedures/SITES_DB_REMEDIATION_2026-09.md (853 lines).
Companions: docs/procedures/FIELD_CONTRACT.md (which column survives a restart, and why),
docs/procedures/ENRICHMENT_AUDIT.md, docs/procedures/CARD_DESCRIPTIONS.md.

WHAT THIS IS
A full audit of the 5,004 curated sites (unified_sites.source_id = 'ancient_nerds') in a
production Postgres, so that every entry ends up either fixed, verified correct, or
explicitly flagged for a human. Phase 0 (safeguards) and Phase 1 (the census) are complete:
eleven checks T01..T11 are written, run and independently audited. Wave 2 closed the two
restart-overwriter landmines; wave 3 applied the hero repair - the remediation's first write
to production data - as 5,438 journalled rows over 2,719 sites in one transaction, with a
ROLLBACK.sql verified to be the exact inverse of all 5,438 rows.

WHAT IS ALREADY ESTABLISHED (do not redo it, build on it)
* Baseline, verified against live production: 5,004 sites; 49,691 curated wiki_images of
  which 659 are excluded; 3,858 heroes; 4,010 sites have at least one image and 994 have
  none; 4,618 wikidata_qid and 4,619 enwiki_title external ids; 16,029 content_links; 2,217
  raw_data citations; 5,004 card_stats of which 7 have an empty card_description.
* The census flags, independently reproduced: T01 1,063 - T02 117 - T03 875 - T04 0 -
  T05 70 - T06 3,010 - T07 2,806 - T08 94 - T09 5,004 - T10 4,010 - T11 84.
  T09/T10 flag whole classes, not defects - they cannot be a worklist.
* Factual union (T01/T02/T03/T05) = 1,840 sites; Phase 3 = 1,813; mechanically settlable = 27.
* T10 declares its own signal fidelity on every run, and the declaration matters: signal S, F
  and P are faithful, D is reconstructed, E is partial (6 of the plan's 67 non-photo terms),
  A is a narrow reconstruction and B is UNAVAILABLE (the plan's 41-city list is not in this
  repository). Four of eight signals are rebuilt. Do not quote a tier as if all eight were
  measured.
* api/main.py imports public/data/card_descriptions.json at startup unconditionally, so
  card_stats.card_description is never the source of truth - the JSON is.

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
  whether it is a real defect and fix the real ones. Known false positive here: md5 used to
  reproduce Wikimedia's own upload-directory layout - swapping it to sha256 would break the
  check to please the checker. Also known: the pi-lens plugin reports against ONE REVISION
  BEHIND; ground truth is running ruff/mypy/pytest yourself.
* When your own result looks impossible, suspect your instrument FIRST. Five times in this
  session a number that could not be true was a bug in the measuring code, not a fact about
  the world - including a probe that reported 0 files where 15,230 existed because the cache
  is sharded into 256 subdirectories, and a hero-metric probe that counted rows when the
  question was about sites. Say so in the report when the instrument was yours.
* The production database may only be reached read-only unless your brief explicitly grants
  writes. Every write needs a conditional WHERE clause carrying the old value, and a journal
  entry. Never DELETE, never a bare UPDATE without a condition, and always scope to
  source_id = 'ancient_nerds' - the table holds 1,759,676 rows across 28 sources.
* A value is only 'fixed' if it SURVIVES A RESTART. Two restart overwriters were found and
  closed (the flat-dict fallback that set confidence='high', and a boot statement in
  pipeline/lyra/orchestrator.py). Before you propose any column value, read
  docs/procedures/FIELD_CONTRACT.md and check whether a boot-time producer would overwrite it.
  A value that a restart reverts is not a fix.

GATES (run them before you claim anything; the project's CI runs them)
  ./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"
  ./.venv/Scripts/python.exe -m ruff check <your files>
  ./.venv/Scripts/python.exe -m mypy <your files>
  -rs is mandatory: skips are silent otherwise. Skipped is not passed.
  Known and expected when the whole suite runs: 3 skips (two refactors, one env-gated) and
  57 deselected. The current green count is 2,023 passed.
  The DB-less suite is the local gate. There is NO local database: the database of record is
  production on the VPS. Integration tests need Docker and insert test rows - never point them
  at production.
  Production access: ssh ancientnerds, then
  docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map
  The -i is REQUIRED (without it psql gets empty stdin and silently runs nothing).

DO NOT: commit or push (a push to main is a live deploy); run git checkout / git clean /
git stash; edit a file another lane owns. Leave your changes in the working tree and report
exactly which files you touched.
A census run may invoke scripts/remediation/census/run.py at any moment, so any file you edit
must be importable after every single edit - never leave a half-written module.

REPORTING: end with a short report containing (1) what you produced, with paths; (2) the
exact commands you ran and their real results; (3) anything you could NOT verify, labelled
as such; (4) anything you found wrong that you did not fix, with the reason.
`;

const MECHANICAL = `
ASSIGNMENT: settle the sites a deterministic script can settle, and write them to production.
Read docs/procedures/SITES_DB_REMEDIATION_2026-09.md Phase 2 and Phase 3, and
output/remediation/phase3_worklist/MECHANICAL.md plus WORKLIST.jsonl before writing code.

You are authorised to write to production data (owner decision E1), under these conditions.

WHY THIS SET AND NOT ANOTHER
Finding.applicable (scripts/remediation/census/model.py:110-117) is the predicate
"proposal in {set,clear} AND confidence in {two_source,authoritative} AND evidence non-empty"
- i.e. "a deterministic script can apply this". Every T01/T02/T03 finding is review/unverifiable
(0 applicable); T05 is where the applicable findings are. MECHANICAL.md is the derived list.
CONFIRM THAT YOURSELF against the census outputs before you write anything: if your count
differs from the worklist's, that is the first thing to report, not to reconcile away.

THE RULES YOU MUST KEEP
1. RE-DERIVE EVERY VALUE. Do not write a value because the census proposed it. Independently
   re-derive it from the source the evidence names, and refuse (move to SKIPPED with the
   reason) if you cannot. The census is an instrument, not the truth.
2. JOURNAL AND DATA CANNOT DISAGREE. Use apply_remediation_change(...) - the 12-argument
   function from migrations/0017, whose boolean path migrations/0018 fixed. One statement
   writes the conditional UPDATE and the journal INSERT together, so a rolled-back change
   cannot leave a journal row. Signature:
     p_table, p_column, p_pk_col, p_pk, p_old, p_new, p_test_id, p_run_stamp,
     p_change_key, p_confidence, p_evidence jsonb, p_site_id uuid
   The truncation guard compares in the column's BASE type (format_type(atttypid, NULL)) -
   never the full type, because a cast to varchar(n) truncates as silently as an assignment
   and a full-type comparison can therefore never fail. If a value is longer than the column,
   that is a real error: report it, do not truncate.
3. ONE TRANSACTION. Write ROLLBACK.sql BEFORE APPLY.sql, both emitted by a generator (never
   typed by hand), then rehearse the byte-identical file with COMMIT replaced by ROLLBACK and
   report the post-rollback state. After the write, read the journal back and reconcile it
   against your plan: 0 rows unaccounted for either way, 0 value mismatches, only the table
   and column you intended, only your run stamp and test id.
4. SCOPE GUARDS. Assert in-transaction that every touched row belongs to source_id =
   'ancient_nerds' and raise before commit otherwise. The table holds 1,759,676 rows; a
   missing filter is the difference between 27 sites and the whole database.
5. VERIFY AFTER, FROM THE DATABASE - not from your own plan. Report before/after counts.
6. SURVIVES A RESTART: read docs/procedures/FIELD_CONTRACT.md and state, per column you
   touch, whether a boot-time producer writes it. If one does, say so and either do not write
   that column or explain why the producer preserves your value.
7. NO DELETE. Out-of-scope or undecidable sites are flagged, never removed.

IF YOU CANNOT WRITE ANY OF THEM, SAY SO INSTEAD. A refusal with a reason is a result; an
invented value is not.

DELIVERABLES
  scripts/remediation/mechanical/plan.py, apply.py
  tests/remediation/test_mechanical.py  (mutation-proven: show each guard can fail)
  output/remediation/mechanical/  PLAN.md, PLAN.jsonl, SKIPPED.jsonl, APPLY.sql, ROLLBACK.sql,
                                  REHEARSAL.sql, APPLIED.md
In APPLIED.md record, verbatim: the pre-write backup path you relied on, the rehearsal
output, the apply output, the journal read-back, and the post-write verification query with
its result. If you wrote nothing to production, say that plainly.
`;

const PILOT = `
ASSIGNMENT: price and de-risk Phase 3 by running exactly ONE batch of five sites, end to end,
and reporting what it actually costs. You are READ-ONLY. Do not write to the database and do
not propose an apply.

WHY A PILOT AND NOT THE RUN
output/remediation/phase3_worklist/BATCH_PLAN.md plans 363 batches / 726 agent runs. The plan's
own cost anchors contradict each other by exactly 2x: section 13's "~40,000 tokens/site" implies
91 sites for the first run, while "36 agents x 5 sites" means 180 (consequence: ~36.8 M tokens /
~6.2 h, or ~72.5 M / ~12.2 h). Do not average them and do not pick one. Measure one batch.

WHAT TO RUN
Read output/remediation/phase3_worklist/FINDER_BRIEF.md and REVIEWER_BRIEF.md - they are the
deliverable of the previous wave and your specification. Then take the WORST-FIRST five sites
from WORKLIST.jsonl that are in the phase3 set (a site with only mechanically settlable
findings belongs to the other lane, not to you) and run the audit exactly as those briefs
prescribe: for each (site, field) the finder proposes from evidence, then the reviewer tries to
REFUTE with its OWN research (not by re-reading the finder's evidence), and only refuted=false
is applied. You are allowed to use web research.

ALREADY KNOWN, SO YOU DO NOT REDISCOVER IT
* 35 sites are mechanically settlable and 8 of those 35 ALSO carry at least one review
  finding (Armazi, Didnauri, Dmanisi, Easter Island, Kutaisi, Satsurblia Cave, Tsona Cave,
  Tsutskhvati Cave Natural Monument). So a mechanical lane and a Phase-3 lane would both work
  those 8 unless one of them owns them. The other 27 are the clean mechanical set - which is
  where MECHANICAL.md's 27 comes from. Decide explicitly who owns the 8 and say so.
  (Careful with the wording: the 8 have a set finding under T05 AND a review finding under
  another check. No T05 site carries two proposals - T05's 70 findings sit on 70 distinct
  sites.)
* Plan section 4.3 lists the false-alarm patterns the reviewer must be briefed on. Report which
  of them you actually hit, and any pattern you hit that is NOT in that list - a missing
  pattern is the most valuable thing this pilot can find.
* The gold standard measured a false-negative rate of 60% (24 of 40 known-wrong values caught),
  decomposed as 3 with no check at all, 13 where a check under-fires, 8 beyond a deterministic
  census. Your outcomes should be expressible in those same terms.

DELIVERABLES (all under output/remediation/phase3_pilot/)
  PILOT.md   - the five sites, every (site,field) outcome as CORRECT / WRONG(with the right
               value and its sources) / UNVERIFIABLE, and the reasoning.
  PILOT.jsonl - the same, machine-readable.
  COST.md    - the honest price basis: per site, the number of research fetches, the number of
               turns, and what the whole 363-batch run would therefore cost, with the arithmetic
               shown. Your own token usage is measured by the caller - so report turn and tool
               counts rather than guessing tokens.
  BRIEF_GAPS.md - everything the briefs did not tell you and you had to decide yourself, each
               with the decision you made. This is a deliverable, not a complaint: it is how the
               briefs get fixed before 363 batches run on them.

Be honest about the batch being five sites: say plainly what a five-site sample can and cannot
establish about 363 batches, and do not extrapolate a rate you did not measure.
`;

const GALLERY = `
ASSIGNMENT: design the gallery-audit stage (plan Phase 2 items 2-5) and answer the one question
that cannot be answered by reading code: can anything available here actually judge an image
visually? READ-ONLY reconnaissance that must end in a costed, decisive design.

WHAT IS AT STAKE
49,691 curated images across 4,010 sites. T10 tier A (3,858 - the current heroes, i.e. T09's
is-the-hero signal) and tier B (9,559 - 'suspect') are the images a human would want looked at.
The hero repair just promoted 2,719 images chosen from tier D (clear) and tier C (grey), on the
strength of a tier system whose own warning says four of eight signals are rebuilt (D
reconstructed, E partial, A narrow, B unavailable). So the tier labels are weaker evidence than
they look, and the gallery audit is where that gets tested rather than assumed.

QUESTIONS TO ANSWER WITH EVIDENCE
1. Per image, what does the audit need to DECIDE? Separate the decisions that are decidable from
   metadata already held (wiki_images carries original_url, commons_page_url, author, license,
   title, width/height, is_hero, is_lead, sort_order, plus the P373 category membership that
   T10 fetched) from the ones that require seeing the picture. Give the split as counts.
2. IS A VISION-CAPABLE MODEL AVAILABLE HERE? Establish this rather than assuming either way:
   read the configured models (~/.pi/agent/models.json), the Pi documentation under
   C:/Users/marti/AppData/Local/node/current/node_modules/@earendil-works/pi-coding-agent/docs,
   and the subagent configuration, and report which models this environment can actually reach
   and whether any of them accepts an image. If none does, say so plainly and give the
   alternatives with what each CANNOT decide.
3. Commons structured data as the substitute: what can be decided from the image's own Commons
   page and its categories (the plan's section 6.4 signals S/A/B/D/E/P are the starting point),
   how many of the 9,559 suspect images would that settle, and what is the measured precision
   and recall of those signals (section 6.4 already reports P/R per signal - use it, do not
   re-measure it)?
4. The image-kind column (Phase 2 item 3): what exactly should it hold, which values, who writes
   it, and does it survive a restart (docs/procedures/FIELD_CONTRACT.md)? Propose the column and
   the writer, and say what a wrong value would cost.
5. COSTED DESIGN: the stages in order, how many images each touches, the tokens or the API calls,
   the wall clock, and what each stage produces. End with a recommendation of what to do FIRST
   and what to NOT do at all, with the reason.

DO NOT propose a VLM stage you cannot show is reachable. A design that assumes a model which is
not available is worse than one that says the visual question cannot be answered here.

DELIVERABLE: output/remediation/gallery_design/DESIGN.md and COST.md. No writes to the
database, no source edits, no commit.
`;

const TASKS = [
  { key: "MECHANICAL", body: MECHANICAL, agent: "worker", slow: true },
  { key: "PILOT", body: PILOT, agent: "worker", slow: true },
  { key: "GALLERY", body: GALLERY, agent: "scout", slow: false },
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
    timeoutMs: t.slow ? 4200000 : 2400000,
    usageBudget: { tokens: { hard: 6000000 } },
  };
});

return await runs.all(children);
