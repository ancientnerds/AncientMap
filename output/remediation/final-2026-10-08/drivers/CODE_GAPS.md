# Code gaps named by the lane scouts (2026-11-10)

Each gap: the lane, a size (S under an hour, M a few hours, L a day), what must exist, the files, and the step of the lane playbook it blocks. The playbook of the lane (`drivers/<lane>/PLAYBOOK.md`) describes the gap in its context.

## cards-a2-a4

### cards-a2-a4#1 [S]

Commit the D153 Fable switch that lane WB runs on (present in the working tree, uncommitted, tests not run): a run that recorded Opus must brief and accept claude-fable-5-2 (teaser/run.py role_now, role_problem, role_brief, agent_jobs) and the disclosure must exist for the stamp sets {Fable} and {Opus, Fable} (model4.CLAUDE_DISCLOSURES / AI_SYSTEMS)

Files: scripts/remediation/roles.py, scripts/remediation/opus_handoff.py, scripts/remediation/phase4/model4.py, scripts/remediation/teaser/run.py, scripts/remediation/teaser/calibrate.py, scripts/remediation/wc/cli.py, scripts/remediation/teaser/mutation_sweep.py, scripts/remediation/mechanical/mutation_sweep.py, tests/remediation/*

Blocks: every answering step (playbook 4.2 from the first verify batch on), run.py outcomes and mechanical/teaser.py plan; gate: playbook 3.1 (git status clean for the lane's code, tools/preflight.py prints PREFLIGHT OK)

### cards-a2-a4#2 [M]

The planner never plans a card again once a step of its run listed it judge-not-clean, so a later clean judge-import (a page that was only unreachable) is never written; needed only to recover such cards, e.g. the 9 cards of run a1 blocked by web.archive.org (D132 'retried later')

Files: scripts/remediation/mechanical/teaser.py (next_outcomes / plan_step), tests/remediation/test_mechanical_teaser*.py

Blocks: none in a2-a4 (the playbook exhausts the judge-import retries before the first plan, 4.5); blocks the D132 retry of run a1's 9 cards

## d57-insert

### d57-insert#1 [M]

G1 Staged insert: the insert lane writes scope_status 'retired' with a scope_reason beginning 'D57 staged:' (shared constant + SQL predicate beside D50_DISPUTED_SITES); APPLY invariant 'rows', read-back, ROLLBACK guard 1 and undo (only scope_reason moves, 1 journal row per site) and rollback_readback follow; probes re-proved. Today it writes in_scope and checks curated_page (writer.py:448, :464, :600), i.e. 37 public pages without text or picture.

Files: scripts/remediation/insert_site/plan.py, scripts/remediation/insert_site/writer.py, scripts/remediation/mechanical/lane.py, tests/remediation/test_insert_site.py, scripts/remediation/mechanical/mutation_sweep.py (insert-site: cases), docs/procedures/INSERT_SITES.md

Blocks: B2 plan (and the D8 review, emit, apply: phase B and C)

### d57-insert#2 [M]

G2 card_stats row of each new site: created journalled inside the insert transaction (zeroed placeholder as generator.backfill_placeholder_stats defines it: rarity_tier 0, category_group 'unknown'), read back, counted in journal_rows; mechanical/card_stats.resolve_basis must accept those journal rows instead of refusing them as a foreign write to the twelve columns, and the next wave must journal the stat cells even after an API boot filled the placeholder unjournalled. Nothing creates the row today: the card_stats lane and lane WB only UPDATE.

Files: scripts/remediation/insert_site/plan.py, scripts/remediation/insert_site/writer.py, scripts/remediation/mechanical/card_stats.py, tests/remediation/test_insert_site.py, the card_stats tests, mutation cases

Blocks: B2 plan (same transaction); phase G card_stats wave; phase H teaser select (no-card-row)

### d57-insert#3 [S]

G3 Lane WN admits a staged site: WC_SQL reads u.scope_reason beside scope_status, hidden() keeps a retired row with the staged prefix in the population (as it keeps D50_DISPUTED_SITES), population() drops the new key before plan4.plan_site. Today export --wn --sites over the 37 answers 'a pilot of 20 from a population of 0'.

Files: scripts/remediation/wc/cli.py, tests/remediation/test_wn.py, scripts/remediation/phase3/mutation_sweep.py (the hidden anchor)

Blocks: D3 WN export (phase D)

### d57-insert#4 [S]

G4 Picture research and image INSERT lane admit a staged site: population_sql (line 127) and the three reads of import_hero/read.py (lines 38, 54, 61) filter scope_status IS DISTINCT FROM 'retired'; insert-accept (verify.py) must not ask a staged site's page over HTTP.

Files: scripts/remediation/candidate_search/population.py, scripts/remediation/import_hero/read.py, scripts/remediation/import_hero/verify.py, tests/remediation/test_candidate_*.py, tests/remediation/test_import_hero*.py, WD2_CASES in mechanical/mutation_sweep.py

Blocks: E2 population and E9 image INSERT wave (phase E)

### d57-insert#5 [M]

G5 Un-retire class 'D57 staged' in the scope lane: a curated row retired with the staged reason goes retired -> in_scope when its description is not empty and hashed by its check record or provenance and it has one live hero row whose file the thumbnail names; otherwise SKIPPED as d57-no-description / d57-no-picture; premise and invariant hold the description md5 and the hero file. scope_unretire.py knows only the D58 numeric-cut retirements and the six pinned D50 sites.

Files: scripts/remediation/mechanical/scope_unretire.py, scripts/remediation/mechanical/identity_lanes.py (scope_unretire_lane), its tests, mechanical/mutation_sweep.py, docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md section 2.2

Blocks: F2 un-retire wave (go live, phase F)

### d57-insert#6 [S]

G6 Transfer of fetched image files to the VPS: import_hero fetch writes into C:/PythonProjects/AncientMap-Offsite/<id8>/<file>.webp; no tool and no runbook command copies the files to /var/www/ancientnerds/public/data/images/wiki/<id8>/ and verifies their size inside ancient_nerds_api (October's waves left only FETCHED_PACKED.json from a lost scratch script). Shared with the image lane D17.

Files: new scripts/remediation/import_hero/transfer.py (pack from FETCHED.json, scp, unpack, size check), docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md section 3.7

Blocks: E8 files on the VPS, before E9 writes the rows

## images

### images#1 [S]

Re-check prompt served-check-v3 lacks D127's condition (a loose museum find counts only when the picture shows its provenance); on the clean gold this caused 11 of the 15 real errors in 200

Files: scripts/remediation/served_image/vision.py (new served-check-v4), scripts/remediation/image_roles/hero_recheck.py, tests/remediation/test_served_image_recheck.py, image_roles/mutation_sweep.py

Blocks: No step refuses; it weakens every re-check (A7, B5, C13, E5, F3). Must land before A6 or between parts, never between a D15 export and its import

### images#2 [S]

flow.denied refuses (PoolError) when a MiniMax depicts file of a stage site was not judged again by the fresh search; pool-picks refuses a target without a rendering (Qasr Qaroun 3ac3c796)

Files: scripts/remediation/candidate_search/pool.py, scripts/remediation/image_roles/flow.py

Blocks: F4 (deny list of the D10 hero re-check); F1-F3 can run

### images#3 [M]

The 433 small heroes are only listed, never planned; D82 wants them searched within D17

Files: scripts/remediation/served_image/hero_moves.py (problem kind small, rules, tests)

Blocks: Part E for the 433 small-hero sites (about 1,300 more answers once built, not in the estimate)

### images#4 [L]

No Commons search for a site that already serves pictures (population kind, claim wording, review before an INSERT that demotes a hero)

Files: scripts/remediation/candidate_search/population.py, scripts/remediation/candidate_search/judge.py (insert_claims), scripts/remediation/import_hero/insert.py

Blocks: Part E for rest-list sites without a qualifying row of their own

### images#5 [S]

After a final INSERT refusal (credit, upscale, file type) the next-ranked depicts candidate is never tried; TARGETS.jsonl is written once

Files: scripts/remediation/image_roles/targets.py, scripts/remediation/image_roles/flow.py

Blocks: None; costs a few sites per stage (they go to the owner list)

### images#6 [S]

No tool packs, sends and verifies the files of an INSERT wave; the playbook gives hand commands (the two tar transfers are untested)

Files: scripts/remediation/import_hero/run.py (a transfer command)

Blocks: None; W7 and W10 of every INSERT wave are typed by hand

### images#7 [S]

Offsite image copy drifted: the 2026-10 waves fetched 920 files into AncientMap-Offsite/<id8>/ instead of images/wiki/<id8>/ (524 missing there, 18 stale), so Images() refuses those rows

Files: one-off merge tool, or scripts/remediation/vlm_pilot/common.py (OFFSITE roots)

Blocks: None with the per-site refresh A3/E2; without it A9, E3, E8 and F5 stop on affected rows

### images#8 [M]

A site not yet in production cannot enter the image population, but the 37 D143 sites need a picture before their insert

Files: scripts/remediation/candidate_search/population.py, scripts/remediation/insert_site/

Blocks: The D57 lane's picture step (not this lane)

### images#9 [S]

No per-site outcome list for a D17 research run (only d59.py outcomes for a D59 run); new owner-facing files are unregistered in owner_list_final.py

Files: scripts/remediation/image_roles/d59.py, scripts/remediation/owner_list_final.py

Blocks: Phase 8: the owner list with a reason per imageless site, and owner_list_final.py build --final

## d14b-duplicates

### d14b-duplicates#1 [M]

G1: copy image files with a moved wiki_images row. Every reader builds the served path from the site id (/data/images/wiki/<site id8>/<filename>), so a row moved to the survivor answers 404 while its file stays in the loser's folder. plan-move must read filename, keep a row on the loser when the survivor's folder already uses that filename for another picture (hero.webp; no unique index), and write a file list; a files command copies (never moves, never overwrites) on the VPS, verifies sha256, and checks HTTP 200 after the apply.

Files: scripts/remediation/mechanical/dup_merge.py, scripts/remediation/mechanical/lane.py, tests/remediation/test_mechanical_dup_merge.py, scripts/remediation/identity/mutation_sweep_merge.py

Blocks: Step 9.3 (file gate) and so the move of every wave whose plan has images > 0: Tarxien, Dodona (40 images) and each new merge whose survivor lacks a loser's picture

### d14b-duplicates#2 [S]

G2: list a retired loser whose name is no alias of its survivor. dup_clusters.py lists retired losers only when they hold images or links, so Ciudad Romana de Caparra (cf49332c: 0 images, 0 links) never becomes a pair and its name never becomes an alias of Caparra.

Files: scripts/remediation/identity/dup_clusters.py, tests/remediation/test_identity_dups.py

Blocks: Step 2 for Caparra only (grep cf49332c in DUP_CLUSTERS.jsonl); the rest of the lane goes on

### d14b-duplicates#3 [S]

G3: the retirement's guard probe takes its neighbour from the first planned loser only (apply.neighbour_of) and refuses the whole probe when that site has no other shown curated site within 2,000 m. It should try the planned losers in order.

Files: scripts/remediation/mechanical/apply.py, tests/remediation/test_mechanical_dups.py

Blocks: Step 9.6 (--probe-guards of dup-merge-retire-<wave>); pre-flight 9.1 finds it before the move is applied

### d14b-duplicates#4 [S]

G0: the Fable switch (D153, D154) is uncommitted in the working tree and still being edited by another agent. Without it the briefs name another model, answer --role refuses, and the identity import demands --calibration.

Files: scripts/remediation/roles.py, scripts/remediation/opus_handoff.py, scripts/remediation/calibrate_claude.py, scripts/remediation/identity/label_rounds.py

Blocks: Steps 3 to 6 (brief, answer, import); gate in step 0

## d20-scope

### d20-scope#1 [M]

X13 is not in the D20 lane: the discovery holds sites of Spain, Portugal, Malta and Sicily dated 500-1500 out of the population (held_label_open_question) and the plan skips an OUT_OF_WINDOW for them (label-open-question)

Files: scripts/remediation/identity/scope_window.py (build), scripts/remediation/identity/scope_judge.py (build), tests/remediation/test_identity_b_scope.py, tests/remediation/test_identity_scope_parents.py, tests/remediation/identity_fixtures.py, scripts/remediation/identity/mutation_sweep_b.py, docs/procedures/WD2_SERVED_IMAGE_AND_SCOPE.md section 1b

Blocks: S19: the follow-on round for the 5 held sites (Huescar, Ponferrada, Ponte de Rubiaes, Ruins of Talamanca, Villaggio Bizantino). If it lands before S1 they are simply part of round r1 (population 74).

### d20-scope#2 [M]

No writer for the corrected starts of D20: PERIOD_WRONG.jsonl has no reader. period_fix.py --cited stamps a start as D124 (Eddisbury), and population.py build --stage wd5 --sites refuses a site that holds a period

Files: scripts/remediation/mechanical/period_fix.py (an input for the D20 rows with its own rule name and the D20 decision, the web answer's quote, agent and model as evidence), tests/remediation/test_mechanical_period_fix.py, scripts/remediation/mechanical/mutation_sweep.py

Blocks: S18: writing the corrected period_start values (then a card_stats wave and the static export). The scope wave itself does not wait for it.

### d20-scope#3 [S]

Fable switch of the identity import gate is only in the working tree, uncommitted (import without --calibration for a role that stands by D153; answer --model claude-fable-5-2)

Files: scripts/remediation/roles.py, scripts/remediation/opus_handoff.py, scripts/remediation/identity/rounds.py, scripts/remediation/identity/run.py (another agent is building it; preflight S0 proves it is present)

Blocks: S3, S4, S7: recording answers as Fable and every import

### d20-scope#4 [S]

A site the plan skips as entry-moved is told 'asked again', but no command asks a decided site again (export asks only sites never asked, export-reask only held ones)

Files: scripts/remediation/identity/run.py, scripts/remediation/identity/rounds.py

Blocks: Only a site skipped entry-moved in S13; it goes to the owner list until this exists

## wc-finish

### wc-finish#1 [S]

Fable switch committed and at rest (roles on claude-fable-5-2, the stamp, earlier stamps valid at import, Fable disclosure strings, re-pinned brief tests). Uncommitted work of another agent at 19:55 UTC; the playbook's P0.3 probe already passes on it.

Files: scripts/remediation/roles.py, scripts/remediation/opus_handoff.py, scripts/remediation/phase4/model4.py, scripts/remediation/wc/cli.py, scripts/remediation/wc/enrich.py, tests/remediation/test_roles.py, test_opus_handoff.py, test_phase4_model.py, test_wc*.py, test_wn.py

Blocks: P0.2 preflight, so every answer, import, build and write of the lane

### wc-finish#2 [M]

**Built 2026-11-12 (decision O23):** `wc/cli.py judge-drops [--apply]`, then `build` again; the gate accepts the rebuilt plan by `judge/O23.json` (no second judge: O23 writes it as strictly better than the live text). Runbook `docs/procedures/SENTENCE_CHECK.md` 15.4a, playbook `wc-finish` A1.7a.

Only if a sampled judge fails: no command writes a chunk without its judged-wrong sentences (turn the judge's WRONG/incoherent findings into drops, rebuild, judge again). Today a failed chunk stays unwritten or must be asked again whole.

Files: scripts/remediation/wc/cli.py, scripts/remediation/phase4/wc4.py, tests/remediation/test_wc*.py

Blocks: A1.8 / A2.12 / A3 write and phase D write, only for a run whose judge-import ends JUDGE_EXIT=1

## wn-and-disputes

### wn-and-disputes#1 [S]

G1: the dispute screen cannot be told to ask a named site; Pantelleria Vecchia Bank Megalith (daa1ea4b-c002-4552-a4ef-45d996c6cea6, the site D21 names) carries no signal and is never researched. Needs `disputes.py candidates --include F`.

Files: scripts/remediation/wc/disputes.py, tests/remediation/test_disputes.py, scripts/remediation/phase3/mutation_sweep.py

Blocks: DS-3 (candidates) for that one site; the screen itself runs without it

### wn-and-disputes#2 [S]

G2: `export --enrich --disputes` refuses the whole DISPUTES.jsonl when one brief's site is not asked by the run (not enrichable, or already in the pilot); no command writes a subset of the briefs.

Files: scripts/remediation/wc/cli.py (_read_disputes) or scripts/remediation/wc/disputes.py (a subset command), tests/remediation/test_enrich.py, tests/remediation/test_disputes.py, scripts/remediation/phase3/mutation_sweep.py

Blocks: EN-3 (lane-E pilot export) whenever a confirmed dispute is not enrichable; EN-9 (the rest after the pilot) always

### wn-and-disputes#3 [M]

G3: after verification one of the two dispute sentences can be dropped; the build still plans the site with one position only, and the D50 gate reads the classes written, not the classes kept. Needs both-kept-or-neither in the build and kept classes in the gate.

Files: scripts/remediation/wc/cli.py (outcome_of, _not_planned) or scripts/remediation/phase4/wc4.py, scripts/remediation/wc/enrich.py, scripts/remediation/mechanical/scope_unretire.py (dispute_text_problems), scripts/remediation/mechanical/identity_lanes.py (dispute_enriched_sql), their tests and mutation sweeps

Blocks: EN-6 to EN-8 (build, judge and write of the dispute enrichment)

### wn-and-disputes#4 [M]

G4: the card lane refuses a retired site (teaser/run.py classify and seed_reason, mechanical/teaser.py SITE_RETIRED), while scope-unretire refuses a D50 site whose card was not written or cleared after its dispute text: a deadlock for all six D50 sites.

Files: scripts/remediation/teaser/run.py, scripts/remediation/mechanical/teaser.py, tests/remediation/test_teaser*.py, scripts/remediation/teaser/mutation_sweep.py, scripts/remediation/mechanical/mutation_sweep.py, docs/procedures/CARD_DESCRIPTIONS.md

Blocks: UR-1 (card step of the six D50 sites) and UR-3 (the un-retire wave)

### wn-and-disputes#5 [M]

G5: D84 has no journalled lane that writes unified_sites.country NULL for the Baltic Sea Anomaly (c8d2c13e, today 'Baltic Sea'); country_b2.py knows only its two pinned pairs and wants an ISO country. Un-retired with 'Baltic Sea' the site would get a /sites/baltic-sea/ page and a country hub (against D84 and D149).

Files: scripts/remediation/mechanical/country_b2.py or a new lane module, scripts/remediation/mechanical/lane.py, tests/remediation, scripts/remediation/mechanical/mutation_sweep.py

Blocks: UR-2 and UR-3 for c8d2c13e only

## lane-e-enrichment

### lane-e-enrichment#1 [S]

The D153/D154 switch that lane E needs is uncommitted work of another agent (Fable roles, Fable disclosure strings, enrich.writer_standing used by pilot_approval). It answered correctly in the working tree at 19:55 UTC; its tests and gates were not run by me. Verify with tools/lane_state.py (playbook P1).

Files: scripts/remediation/roles.py, scripts/remediation/opus_handoff.py, scripts/remediation/phase4/model4.py, scripts/remediation/wc/enrich.py, scripts/remediation/wc/cli.py, tests/remediation/test_enrich_calibration.py, tests/remediation/test_phase4_model.py, tests/remediation/test_roles.py

Blocks: step 4 (briefs and answers name the role's model), step 8 (build derives the disclosure), W3 (the gate asks the writer's standing), W6 (the acceptance reads model4.AI_SYSTEMS)

### lane-e-enrichment#2 [S]

Only if the owner wants more than the texts under 300 characters: enrich.THIN_CHARS is a constant, and the frozen question is byte-pinned in tests and the mutation sweep.

Files: scripts/remediation/wc/enrich.py, scripts/remediation/wc/prompts_enrich.py, tests/remediation/test_enrich.py, scripts/remediation/phase3/mutation_sweep.py

Blocks: step 2 (list) and step 3 (export), only on that owner decision

### lane-e-enrichment#3 [M]

Only if the owner wants thin sites without an open question: the question offers the open_question class to every site and no flag switches it off.

Files: scripts/remediation/wc/prompts_enrich.py, scripts/remediation/wc/enrich.py, scripts/remediation/wc/answers.py, tests/remediation/test_enrich.py

Blocks: step 3 (export), only on that owner decision

### lane-e-enrichment#4 [S]

The repository has no list builder and no state reader for lane E. I supplied both as driver helpers; build_list.py is tested on today's read (402 listed), lane_state.py is untested for the stages after the import.

Files: output/remediation/final-2026-10-08/drivers/lane-e-enrichment/tools/build_list.py, output/remediation/final-2026-10-08/drivers/lane-e-enrichment/tools/lane_state.py, output/remediation/final-2026-10-08/drivers/lane-e-enrichment/env.sh

Blocks: none

### lane-e-enrichment#5 [S]

The runbook still describes lane E with Sonnet and Opus roles and a writer calibration gate (docs only).

Files: docs/procedures/SENTENCE_CHECK.md (section 14)

Blocks: none

## d23-names-d25-parents

### d23-names-d25-parents#1 [S]

Fable registry and owner-standing gate (D153/D154) for the identity answers and imports: written in the working tree on 2026-11-10 by another agent, not committed

Files: scripts/remediation/roles.py, scripts/remediation/opus_handoff.py, scripts/remediation/identity/rounds.py, scripts/remediation/identity/label_rounds.py, scripts/remediation/identity/run.py, tests/remediation/test_roles.py, test_opus_handoff.py, test_identity_b_rounds.py, test_identity_b_run.py, test_identity_rounds_wiki.py

Blocks: L3 (opus_handoff.py answer --role ... --model claude-fable-5-2) and L5 (every import of both chains: run.py --lane names import, parent_judge.py import, now without --calibration); playbook checks A2.1 and A2.2

## d13-retarget

### d13-retarget#1 [S]

Fable switch and identity import without --calibration are uncommitted working-tree edits (in progress by another agent; run.py status and import --help worked from them on 2026-11-10 20:38)

Files: scripts/remediation/roles.py, opus_handoff.py, calibrate_claude.py, identity/rounds.py, identity/run.py, identity/label_rounds.py

Blocks: every step (gate G0: clean git status for scripts/remediation before the pilot export)

### d13-retarget#2 [L]

D83: re-target without a Wikidata item and/or English article - prompt verdict text and rules, answer shape (qid, enwiki_title null), gates (name attested by the quoted scholarly page, point by its quote instead of P625), link plan (remove the town's site_external_ids rows, source_url = scholarly page), landed checks, hand-off records, and the no-Short marker with a journalled write. The 2026-10-24 gold answered Bayston Hill KEEP only because the hillfort has no article.

Files: scripts/remediation/identity/retarget.py, identity/retarget_plan.py, identity/run.py, mechanical/identity_lanes.py, pipeline/video/shorts_export.py, tests/remediation/test_identity_b_retarget.py, test_identity_b_plan.py, test_identity_b_run.py, identity/mutation_sweep_b.py

Blocks: step 2 (pilot export): the import rebuilds every prompt byte for byte and a decided site is never asked again, so the template must be final before round 1

### d13-retarget#3 [S]

RESEARCH constant says 'web verifier Sonnet, adversarial re-check Opus' and is written into every journal row's evidence (false under D153)

Files: scripts/remediation/identity/retarget_plan.py and its tests

Blocks: step 9a (plan-links: a delivered step directory is never replaced)

### d13-retarget#4 [S]

A name-unchanged skip counts as 'a plan skipped it' in _skipped_sites: a re-target whose new name equals the stored name can never pass chain-done name or handoffs

Files: scripts/remediation/identity/run.py (_skipped_sites), tests/remediation/test_identity_b_run.py

Blocks: step 9b (chain-done name) and handoffs for those sites

### d13-retarget#5 [S]

A page whose fetch failed (403, 429, timeout) is cached for the stage and never fetched again by a later round's import, so a throttled EntityData or Wikipedia URL keeps its site held through both re-asks

Files: scripts/remediation/identity/rounds.py (import_round), opus_audit/quotes.py (collect)

Blocks: steps 6 and 7 (re-asks of sites held for 'fetch failed')

### d13-retarget#6 [L]

Fields run for re-targeted sites: point, site type and period asked afresh although values are stored (population build --stage wd5 --sites only asks the start of an undated site and refuses a site that holds a value), with the D13 point as hint and a plan that may replace sourced values

Files: scripts/remediation/fields/population.py, fields/handoff.py, fields/plan.py, their tests and mutation sweep

Blocks: chain stages point_type and period; through gate G5 also step 9 (no link write before)

### d13-retarget#7 [L]

Description for a site whose stored text describes the town: no lane replaces a text whose subject is wrong (WN asks only sites without a description; Phase-4 lane W is pinned to SCOPE4.v3). Needed: WN with a replace list, conditioned on the stored text and its provenance

Files: scripts/remediation/wc/cli.py, phase4/wc4.py, their tests and mutation sweep

Blocks: chain stage description (and the records of gallery, period, card after it); through gate G5 also step 9

### d13-retarget#8 [M]

Retirement of a confirmed RETIRE verdict: nothing reads RETIRE_LIST.jsonl (scope_review.py and the scope-window lane ask their own populations); needs a retarget-retire-<wave> lane in the scope-review shape

Files: scripts/remediation/identity/retarget_plan.py, identity/run.py, mechanical/identity_lanes.py

Blocks: step 8 follow-up: the retirements only (the re-target waves go on without it)

## phase8-closeout

### phase8-closeout#1 [L]

G1 WF measurement X7 cannot be drawn or reported: draw.py/redraw.py draw a fixed, pinned 60; redraw --after refuses draw-2026-09-25b (no RESULT.md) and would otherwise repeat seed 20260926; two phase-4 audit sample files lay in the removed p4-pilot worktree; judge.py's brief says 'Opus judge' and '--model claude-sonnet-5-5 or claude-opus-5-5' without --role; score.py gates on '3 of the 60 sites'; no deterministic check of the shorts-v1 card form (D7). Needed: a new draw module (100 sites, seed 20260928, both earlier samples excluded), brief with --role pilot_judge --model claude-fable-5-2, report-only result, check D7, tests.

Files: scripts/remediation/acceptance/ (new wf_draw.py; judge.py, score.py, checks.py), tests/remediation/test_acceptance_*.py, the acceptance mutation cases

Blocks: C3 (WF measurement X7)

### phase8-closeout#2 [M]

G2 owner_list_final.py build --final refuses: 12 owner artefacts are unregistered today (fields/d121/d124/adv/OWNER.jsonl, four under fields/wd5r, two under fields/wd5x, three insert_site/d57-2026-11-05/D1xx_OWNER_ROUND.json, two served_image/hero-moves-2026-11-06*/OWNER_LIST.jsonl) and every lane finishing later adds its own; each must become a source or an OUT_OF_SCOPE entry with its reason; CLOSEOUT_FOLLOWUPS.jsonl must become a source whose open rows are listed.

Files: scripts/remediation/owner_list_final.py, tests/remediation/test_owner_list_final.py

Blocks: C1 (final owner list) and C2 (follow-ups on the list)

### phase8-closeout#3 [M]

G3 no command asks one named site's coordinates again: fields/population.py build --sites builds a period_start question only, so follow-up 1 (Sybaris on the Traeis carries Sybaris' point) has no tool path.

Files: scripts/remediation/fields/population.py, scripts/remediation/fields/handoff.py and their tests (fields lane code)

Blocks: A4/C2 follow-up 1; without it the site goes to the owner list

