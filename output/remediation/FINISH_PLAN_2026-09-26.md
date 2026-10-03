# Finishing the sites remediation - the owner's mandate of 2026-09-26 and the plan

This file is the anchor for the last stretch. Where it and older files (HANDOVER, REPAIR_TEXTS,
PROTOCOL, CARD_DESCRIPTIONS) disagree, this file wins; it records what changed and why.

## 1. The owner's decisions (2026-09-26, asked once at the start, then autonomous)

Asked through AskUserQuestion after the fresh acceptance's stage 1 (`draw-2026-09-25b`) measured
46 of 60 sites with at least one WRONG verdict (30 severe; per field below). Verbatim answers:

| # | question | owner's answer |
|---|---|---|
| O1 | When is the database done? | **"Keine Abnahme mehr"** - finish the repairs and report the measured error rates per field; no pass/fail gate. The running acceptance `draw-2026-09-25b` ends as a measurement (stage 1 only); its V3 write freeze on the 60 drawn sites is lifted. |
| O2 | Old March texts without a sourced replacement: cards | **"die kartentexte für das game waren eigentlich schön. sie sollten die site teasern und mystisch sein. diesen text wollte ich auch für die Shorts. sie müssen alle ungefähr gleich lang sein aber natürlich müssen sie inhaltlich stimmen!!!"** |
| O3 | Which cards get the teaser style | **"Alle Karten neu"** - all ~4,900 cards, the 761 extractive Phase-5 cards included. Opus writes each from sourced facts; an independent Opus checker must confirm every claim with a source, else rewrite. |
| O4 | Card length | **160-190 characters** (the March cards' median is 172; about 11-13 s spoken). |
| O5 | Old March descriptions that the extended Phase 4 cannot replace | **"Satzweise prüfen und kürzen"** - Opus checks each sentence against sources; supported sentences stay (AI-marked), contradicted/unsupported ones go; nothing left -> the description is cleared. |
| O6 | Single fields refuted or unverifiable (period, type, image, source URL, ...) | **"Belegt ersetzen, sonst leeren"** - replace only with a sourced value; else the field is emptied. |
| O7 | Oceania | **"Ja, Ozeanien wie Amerika"** - Oceania's time limit is 1500 AD like the Americas' (E3). |
| O8 | Deploys | **"Ja, alles autonom"** - every finished step goes live after green gates and an accepted journalled write, field clears included. |
| O9 | HUMAN_ONLY leftovers | **"Nach meiner Empfehlung entscheiden"** - each open item is decided by its recorded recommendation and documented. |
| O10 | AI disclosure of teaser cards | **"ja wie bisher"** (data-card-ai on the SiteCard, the AI footnote on the site page, the AI note in the shorts description). |
| O11 | Parallelism | **"geh doch mal lieber auf 16 agenten damit es schneller geht. du kannst ja automatisch fortführen wenn das api limit resettet."** |

Standing rules that still hold: Opus only (no DeepSeek/Pi/opencode/MiniMax for the remediation);
every production write journalled (rehearse, apply in steps of <=100 sites, read back, rollback
rehearsal, per-step acceptance with 0 deviations); no DELETE, no TRUNCATE on `unified_sites`; the
card file is regenerated from the DB and pushed **immediately** after card writes (the API boot
imports the file); never read `video-assets/prod-db.env`; no personal data in any web request.

## 2. Where the data stands (stage-1 measurement of `draw-2026-09-25b`, 60 sites, 652 questions)

| field | CORRECT | WRONG (severe) | UNVERIFIABLE |
|---|---|---|---|
| card_description (55 with a card) | 32 | 19 (19) | 4 |
| description | 40 | 15 (15) | 5 |
| period_name | 30 | 22 | 8 |
| period_start | 32 | 16 (2) | 12 |
| served_image | 35 | 11 (2) | 1 |
| site_type | 50 | 8 | 2 |
| coordinates | 52 | 7 (5) | 1 |
| source_url | 55 | 4 | 1 |
| scope | 58 | 2 (2) | 0 |
| name | 56 | 1 (cosmetic) | 3 |
| country | 60 | 0 | 0 |

Split by origin: old March cards 18/43 WRONG vs Phase-5 cards 1/12; old March descriptions 9/29 vs
Phase-4 descriptions 1/10 (at the time of the tally). All 10 planted canaries were caught at stage 1.
Classes seen: invented numbers/dates in March texts; points on the nearest village or a namesake
(Mamai-Hora, Peñas de Cabrera, Gabrovnica, Trojanov Grad, La Muerta, Corycus 110 km, Tayma Stones on
the Louvre); period buckets one or more buckets off; images of the region or another namesake site;
source URLs on the island/town article; non-sites (Baltic Sea Anomaly) and medieval sites (Kłopot).

## 3. The workstreams

| id | what | population | how |
|---|---|---|---|
| W0 | housekeeping: record the measurement, merge `wip/audit-fix`, push | - | this session |
| WA | **descriptions, Phase 4 scope v3** | the ~3,238 curated sites Phase 4 never saw (REPAIR_TEXTS_2026-09-26.md) | code per the design (scope v3, plan flags), then mass4 export -> Opus handoff (selector, review) -> write_gate4 P4 (and L) in steps. **No P5**: cards come from WB. |
| WC | **descriptions, sentence check and trim** | every site still carrying March description text after WA | new lane: code splits sentences; Opus researches each (keep verbatim with a machine-checked quote / drop, optional exact drop span); new text + rebuilt citations + provenance; nothing kept -> cleared |
| WB | **teaser cards** | every curated site with a published description after WA/WC | new lane: writer (Opus, 160-190 chars, evocative, only facts from the site's sourced fact sheet) -> independent checker (Opus, every claim supported, length/style/this-site) -> up to 2 rewrites -> else card cleared; provenance marks it AI-generated and shorts-eligible; card file regenerated and pushed at once |
| WD | **structured fields** | all curated sites | mechanical Wikidata/Wikipedia harvest (P625, P571/P580, P31, P18, P373, sitelinks) -> per-field status; Opus resolves conflicts/missing per site (coordinates, period_start -> period_name, site_type, served image, source_url, scope incl. natural features); replace with sourced value, else clear (O6); scope rule with Oceania (O7) |
| WE | HUMAN_ONLY leftovers | the open items | decided by their recorded recommendations (O9); those WD covers go there |
| WF | ship and report | - | static export, card file, Qdrant, IndexNow, push; a final measurement of error rates per field (reporting, not gating); docs (HANDOVER, CLAUDE.md, AUDIT_LOG, memory) |

Order: W0 -> build WA/WB/WC/WD (in parallel worktrees, each reviewed) -> WD harvest (cheap) ->
WA mass run -> WC -> WB (per site after its description is final) -> WD conflicts -> WE -> WF.

## 4. Progress log

(appended as the work proceeds; newest last)

- 2026-09-26 ~01:30 UTC: decisions O1-O11 recorded; stage-1 import of `draw-2026-09-25b` running.
- 2026-09-26 ~01:45 UTC: stage-1 import done (494 counted: 370 CORRECT, 37 UNVERIFIABLE, 87 WRONG; 158 not counted); the run ends as a measurement (O1), recorded in AUDIT_LOG with its files (1bff027).
- 2026-09-26 ~01:50 UTC: `wip/audit-fix` merged (4a973d9); gates green (pytest 7219 passed); origin/main (9 commits from other sessions) merged; pushed **9eb6416** to main.
- 2026-09-26 ~01:50 UTC: workflow `finish-build-lanes` (wf_c86bd2b6-da0) builds WA, WB, WC, WD1, WD2 in worktrees `.claude/worktrees/{wa,wb,wc,wd1,wd2}` (branches `wip/*` from 4a973d9), each followed by an adversarial review and a fix round.
- 2026-09-26 ~02:15 UTC: WE analysis written to `HUMAN_ONLY_DECISIONS_2026-09-26.md` (27 open items: 13 go to a workstream, 10 need their own action, 4 documentation only). Genuinely owner-only: A4 (the VPS has no MTA - a Discord webhook URL or a relay account is needed) and A5's third copy location (a storage account). **Ordering constraint:** B1-L/B1-N (a journalled link/name pass "L5", up to 120 sites with generic or wrong Wikidata items) must run before WD1's harvest is trusted.
- 2026-09-26 (after the interruption): both build workflows resumed from their run ids (cached stages kept; the unfinished fix/build agents told to continue from their worktrees). WA was complete (build, review, fix at c3cbf33) and merged (6e448e3); p4-pilot fast-forwarded.
- WA v3 in production (read-only so far): pin check `5a2949fb...` held; fresh read; plan `PLAN4.v3.jsonl` sha256 `779021ad...` built from 6e448e3 with `--exclude V3_EXCLUDE_L5.txt` (the 167-site L5 population, runbook 0.3; `ab493aa1...`): **3,124 sites, 209 batches p4-2001..p4-2209**. Export of the selector round: 205 batches at once, 4 failed on a Wikipedia pacing-lock timeout (transient) and were re-exported (STAGE_EXIT=0); 472 sites held before any question. Workflow `wa-v3-handoff` (wf_d3b93bee-b6b) answers selector and review questions (one Opus agent per batch) with serialized imports per group of 8.
- 2026-09-26 ~13:00-14:40 UTC: WA handoff complete (wf_d3b93bee-b6b, 472 agents; all 209 batches' select and review imported, 0 problem groups; p4-2061 repaired before its import, p4-2006/p4-2011 held selection-refused). L5: three rounds (155 decided, 4 held), plan (76 link sites, 198 rows, 2 renames, 28 untrusted links, Chiapa rename skipped until WD2's hide exists), step-001 and name-l5 applied, verified, rollback rehearsed (b390c17). Lanes WB, WC, WD1, WD2 merged (af4e9e5 .. 77797bb, e3a33e6, f8d2f3f); merge seams fixed (card_ai signature, the NULL-to-NULL message and its two sweep cases).
- 2026-09-26 ~16:55 UTC: **three background commands killed by Claude Code for low system memory** (3.6 of 31.3 GB free; WSL's vmmem 10 GB, PyCharm 4.4 GB): (1) the WA write loop during its full rehearsal - it stopped at p4-2143 (psql failed to start, 0xC0000142); rehearsals end in ROLLBACK and the journal holds **0** `phase4:p4-2%` rows, so nothing was written; (2) the WD1 harvest (read-only, resumable from its cache); (3) the push of 1557d62 during the pytest gate - origin/main is still 6e2edea. Restart only on the owner's word (the harness rule for pressure-killed commands).
- 2026-09-26 ~17:00 UTC (owner: "weiter mit ultracode mit den ressourcen die wir haben"): restarted with fewer agents at a time. WD1 harvest complete (4,585 entities, 4,546 enwiki records, all source URLs); three unmapped P31 classes mapped (dec81b8); parts cut: part 1 80 pilot + 1,243, part 2 80 pilot + 3,359 asked. Pushed **63668be** to main (all gates green; lanes WA-WD2, WE1/WE2, L5 records). Running: WA full rehearsal then write steps; WB pilot 1 (20 W/S sites); WD1 part-1 and part-2 pilots (handoff, re-asks, pilot gate).
- 2026-09-26 ~19:00-21:30 UTC: **03359e8 live** (CI green; api/api2 on 03359e86; 0 card overwrites at boot). On the way: dec81b8 reached main outside this orchestrator's push (an agent; CI failed on test_e3_oceania - countries.geojson is an LFS pointer on the runner - so nothing deployed); CI now pulls that LFS object (3ec8986); the WC User-Agent sweep case re-anchored. WB pilots 1 and 2 FAILED by the gate (pilot 1: Wikimedia refused the bare User-Agent - fixed, one constant `research_web.USER_AGENT`; pilot 2: 120/122 claims proven, 2 contradicted, both faithful to wrong Wikipedia sentences, like Concangis in pilot 1) -> lane WB gets a per-card web verification before any write (`wip/wb2`, building). WA writes: step 1 (96 sites) accepted after the loop's acceptance capture was fixed (stdout only, `^ACCEPTED`); steps continue, a 10-site Opus audit after every 500 written sites.
- 2026-09-26 ~21:45 UTC: WA writes past 2,200 sites (every step 0 deviations; audits 1 and 2: 121/121 sentences supported; one duplicate-loop race recorded, no double write). **v3d** built after the 48 h window (`PLAN4.v3d.jsonl` `7a147b7f...`): 133 sites in 9 batches p4-2501..p4-2509 (the mass run's 19 deferred + the L5 population's March sites, now that L5 landed); exported (72 held before any question); workflow `wa-v3d-handoff` answers it. WD1: both pilots PASS and written (waves 2026-09-26a: 63 sites/158 cells; 2026-09-26c: 46 sites/89 cells); the bulk parts run (`wd1` 1,243 sites, `wd1-rest` 3,359). WB: `wip/wb2` (per-card web verification, verified-text hash in the provenance) merged (f5df945); pilot 3 running with the full stage chain.
- 2026-09-27 ~10:50 UTC: after two usage-limit pauses (the workflows waited and resumed; 56 WD1 part-1 batches and the WD1 imports failed at the limit and were resumed from cache): **WA complete** (1,769 sites, AUDIT_LOG). **WB**: pilot 3 PASS; card sittings 1 (19 cards, 14ef1f9) and 2 (chunk 03: 446 cards, 4 clears, steps 2-6, **5b9fc5b live**; 0 boot overwrites, card file = DB, steps re-accepted); chunks 01/02/04/05/06 continue (`wb-continue`). **WC**: pilots 1 and 2 failed the judge on single items -> `wip/wc2` (independent per-site verification, text-bound, write-once import) merged (590d2d2); pilot 3 running. **WD1**: part 2 r0 fully answered (3,359), import and re-asks running; part 1 r0 823/1,243, the rest re-running.

## 5. RESUME POINT - stopped cleanly on the owner's word, 2026-09-27 ~14:30 UTC ("stop so dass wir später weitermachen können")

**Production, nothing in flight** (every write journalled and accepted; no step pending in any apply root):
- live main **5b9fc5b** (API on it; card file = DB). `integrate/wave1` is ahead with docs, the WC
  verification merge (590d2d2, scripts only) and the records below - push them with the next sitting
  (by fixed SHA: `git push origin $(git rev-parse HEAD):refs/heads/main`, never commit during a push).
- **WA done**: 1,769 sourced descriptions (v3 1,750 + v3d 19). Re-queues due: v3 48 sites from
  2026-09-28T07:57Z, v3d 2 from 2026-09-28T21:42Z (PHASE4_V3_RUNBOOK section 9.1, from the p4-pilot
  worktree; then write with `orchestration/p4v3_write_loop.sh` / `p4v3d_write_loop.sh`).
- **L5 done** (76 link sites, 2 renames). **WD1 pilots written** (waves 2026-09-26a, 2026-09-26c).
- **WB**: 465 teaser cards live (steps 1-6: pilot 19 + chunk 03 446, 5 clears).
- **WC**: pilot 3 written (p4wc-4003, 20 sites).

**Stopped mid-run - resume in this order** (Workflow `resumeFromRunId` replays finished agents from
cache; the scripts are also kept in `output/remediation/orchestration/`):
1. **WB caption fix** (`wip/wb3`, worktree `.claude/worktrees/wb3`: 1 commit 884f185 + the builder's
   uncommitted edits - it was stopped mid-build): resume workflow `wf_fedd4fb6-478` (script
   `.../workflows/scripts/wb3-build-wf_fedd4fb6-478.js`), or finish by hand: long caption words are
   drawn at their own smaller size, the contract refuses only words beyond the floor. Merge, then
   resume the WB chunks with `orchestration/wb-continue.js` (args `{"runs": ["wb-ws-2026-09-27-04",
   "wb-ws-2026-09-27-02", "wb-ws-2026-09-27-01", "wb-ws-2026-09-27-05", "wb-ws-2026-09-27-06"],
   "width": 5}`): the stuck write labels are exactly the too-wide-word sites (Sammallahdenmaeki,
   Hohlenstein-Stadel, Saint-Pierre-aux-Nonnains, Sainte-Colombe-sur-Seine, Strubben-Kniphorstbos,
   a card naming Mecklenburg-Vorpommern; chunk 05 rewrite1-001 one label). Chunk states: 01/02/04/06
   write exported (01: 446/450 answered, 02: 447, 04: 449, 06 write not imported), 05 at rewrite1
   (5/6) with 444 due verify. Then per finished chunk: a card sitting (`orchestration/wb_step.sh RUN N`
   per step, drill first, `teaser.py card-file --steps A-B`, `card_json.py --check`, commit, push at
   once, after-deploy checks) - CARD_DESCRIPTIONS.md 5.4-5.5.
2. **WD1 part 2** (`output/remediation/fields/wd1-rest`): r0 (3,359) and r1 (161) imported, r2
   exported 11 questions, 9 answered: resume `wf_4368c592-77b` (script `C:/tmp/wd1-handoff-pool.js`
   = `orchestration/wd1-handoff-pool.js`, args `{"run": "output/remediation/fields/wd1-rest", "ho":
   "output/remediation/handoff/fields-wd1-rest", "pilot": false, "width": 7}`). Then write wave
   **2026-09-26d** with `orchestration/wd1_wave.sh 2026-09-26d output/remediation/fields/wd1-rest`.
3. **WD1 part 1** (`output/remediation/fields/wd1`): r0 1,003 of 1,243 answered: resume
   `wf_9bc72d57-5d4` (same script, args `{"run": "output/remediation/fields/wd1", "ho":
   "output/remediation/handoff/fields-wd1", "pilot": false, "width": 5}`), then wave **2026-09-26b**.
   After both parts: the card_stats wave and the site_external_ids follow-up from each wave's
   HANDOFF.json (FIELDS_WD1.md 3.4 step 15).
4. **WC mass**: chunk `mass-2026-09-27-01` exported (500 sites, 36 answered); `mass-2026-09-27-02`
   has READ.json but no export. Resume `wf_710ea3ca-153` (`orchestration/wc-mass.js`, args
   `{"prefix": "mass-2026-09-27", "chunks": 6, "limit": 500, "firstBatchBase": 4100, "width": 4}`) -
   note: its export op for chunk 02 will be re-run and `read` refuses a second read of that run dir
   (written once): run chunk 02's `export` (with `--after` chunk 01) by hand or use fresh run names
   for chunks 02+. Write each built chunk with `orchestration/wc_write.sh <pilot-c WC4> <chunk WC4 ...>`
   (every WC plan named, the passed pilot first).
5. Then, in order: WB over the WC texts (a pilot with `--basis WC` first), WD2 (scope review of
   non-sites incl. Richat Structure / Hadrian's Wall Path / Baltic Sea Anomaly, Oceania; then the
   served image), the Chiapa de Corzo hide + rename, the description-defect list (AUDIT_LOG: the WA
   audits' gold errors, WB DESCRIPTION_DEFECTS.jsonl), WF (static export, Qdrant, IndexNow, final
   measurement of error rates per field, HANDOVER/CLAUDE.md/memory).
Owner-only, unchanged: A4 (Discord webhook URL for backup alerts), A5 third backup location.
- 2026-09-29 ~14:30 UTC (new session, owner: "limits resett. bitte weitermachen"): nothing moved on main (5b9fc5b live, no other pushes). Workflow run ids of the old session cannot be resumed, so continuing workflows were started from the on-disk state (write-once answers are skipped): `wd1-continue` (wd1-rest r2 + import, wd1 r0 remainder + re-asks), `wb3-build-resume` (caption fix), `wc-mass-continue` (chunk 01 remainder, chunk 02 export, further chunks), and the **re-queues**: v3's 48 sites (new batches p4-2210..p4-2213, handoff `p4-v3-select-rq`) and v3d's 2 (p4-2510, `p4-v3d-select-rq`) exported and answered by `wa-v3-requeue` / `wa-v3d-requeue`.

## 6. RESUME POINT 2026-09-30 (newer than section 5) - stopped by the weekly usage limit (resets 2026-10-06 14:00 Europe/Berlin)

All Opus work (answers, verifications) is blocked until then; the operators' deterministic steps are not. **Nothing is half-written in production**: every write is journalled and accepted; no step is pending. Live main **31ada02** (card file = DB, steps 1-16 accepted); `integrate/wave1` is ahead with records only.

**Done since section 5** (AUDIT_LOG 2026-09-29/30): WA re-queues (25 sites; 3 + Nea Paphos wait until 2026-10-01T14:31Z), Chiapa hide + rename (`wip/chiapa`), WD1 part 2 (wave 2026-09-26d, 2,296 sites, 23 steps) and part 1 (wave 2026-09-26b, 1,056 sites, 11 steps), WD2 scope review (20 sites retired, wave 2026-09-30), WB chunks 03/04/01/06 finished their stage chain - **cards live: chunks 03, 04 and 01 (steps 1-16)**; chunk **06 is finished (441 accepted, 7 cleared) but NOT yet written** (step numbers 17-21: `wb_step.sh wb-ws-2026-09-27-06 N`), `wip/wb4` (writer may decline an undrawable-name site) merged.

**Resume in this order** (new workflows; answers are write-once, finished batches are skipped; LF scripts in `output/remediation/orchestration/`):
1. **WB**: (a) a card sitting for chunk 06 (steps 17-21): drill `ssh ancientnerds "cd /var/www/ancientnerds/scripts/remediation && DO_DRILL=1 ./00_backup_and_drill.sh"`, note API StartedAt, `wb_step.sh` per step, `teaser.py card-file --steps 17-21`, `card_json.py --check`, commit, push a **fixed SHA** immediately (the pre-push gates take ~20-30 min under load; the frontend tests MapSection.lazyError and geoLabelLazy are flaky - retry the same SHA), after-deploy checks. (b) `wb-continue.js` args `{"runs":["wb-ws-2026-09-27-05","wb-ws-2026-09-27-02"],"width":6}`: 05 needs ONE rewrite2 answer (batch rewrite2-001, label 4a07cc38, Temple of Augustus, Split - the workflow's state agent misreads it as "needs-import": answer it with a direct Agent using `run.py brief --batch-id rewrite2-001`, then re-run the workflow), then verify (449); 02 is at verify (449 due, 320 answered; verify-065..090 missing), then rewrite-v/check-v/verify2. Then a sitting each (steps after 21). A verify import that refuses a malformed answer names the file: delete it and re-run.
2. **WC mass** (`C:/tmp/wc-mass-continue.js` = copy at `orchestration/wc-mass-continue.js` if missing; args `{"prefix":"mass-2026-09-27","chunks":6,"limit":500,"firstBatchBase":4100,"width":6}`): chunk 01 and 02 round 1 fully answered and imported (chunk 01: 12 re-ask questions, r2 exported; chunk 02: 19 re-ask, r2 exported with 3 batches) - their r2 answers, verification rounds and build are next; chunk 03: 291/500 answered (imports take 30-85 min: per-host pacing); chunks 04 (500) and 05 (148) unanswered. Write each built chunk with `orchestration/wc_write.sh <pilot-c WC4> <chunk WC4 ...>` (pilot p4wc-4003 first).
3. **WD2 served image**: `orchestration/wd2-image.js` args `{"width":4,"run":"output/remediation/served_image/served-image-2026-09-30","handoff":"output/remediation/handoff/served-image-2026-09-30"}`: READ, PRECHECK done, `export-check` done (339 batches, 4,064 questions, 780 answered - population `all`, signed off in AUDIT_LOG 2026-09-29); then import-check, replace stage, plan, chunks through `chunk_writer.py` (runbook 3.5), then a card_stats wave (3.5 end, after WD1/WD2 - WD1's period writes are card inputs too).
4. After WC is written: **WB over the WC texts** (a pilot with `--basis WC` first, CARD_DESCRIPTIONS 5.2), the description-defect repair list (`DESCRIPTION_DEFECTS.jsonl` in every WB run: ~150 lines, lane WC's method), the second site whose name the font cannot draw (f9cfc5f7, "Gate of All Nations" + U+200C + "Persepolis"; no run yet), the card_stats wave, the site_external_ids follow-up from each WD1 wave's HANDOFF.json, **WF** (static export, Qdrant, IndexNow, final measurement of error rates per field, HANDOVER/CLAUDE.md/memory).
5. Re-queue on 2026-10-01T14:31Z: v3 (3 sites) and v3d (Nea Paphos) - PHASE4_V3_RUNBOOK 9.1 from the p4-pilot worktree, then `orchestration/p4v3_write_loop.sh` / `p4v3d_write_loop.sh`.

Memory: keep at most ~14 agents at once (free RAM fell to 4.6 GB at 22); the harness kills background commands below ~3.6 GB. Owner-only, unchanged: A4 (Discord webhook URL), A5 (third backup location). Also for the owner: 672 + 252 sites keep their old coordinates (no sourced point; coordinates cannot be emptied), and ~2,200 sites lost their period start for lack of two dated sources (O6).

## 7. RESUME POINT 2026-10-01 (newer than section 6) - the owner is away ~48 h; finish autonomously

**Owner decisions of 2026-10-01** (asked once; verbatim answers):

| # | question | answer |
|---|---|---|
| O12 | Models | "opus 5.5 für orchestrierung hier in der sitzung und sonnet 5.5 für alle subagenten mit sinnvollen efforts" - every workflow `agent()` sets `model: 'sonnet'` explicitly (never inherited); efforts: operators `low`, state operators `medium`, answering/judging agents and code builders `high`. |
| O13 | Evidence for a researched field value | "Wikipedia/Wikidata reicht" - one source suffices (other reputable sources where Wikipedia/Wikidata say nothing); the verbatim quote is still machine-checked on its page; no second agent. |
| O14 | Nothing sourced | "Feld bleibt leer (Recommended)" - the owner gets a list. |
| O15 | Coordinates without a sourced point (672 + 252) | "Recherchieren, sonst behalten (Recommended)" - research; else the stored point stays and is listed. |
| O16 | A site left without a description | "Neu aus Webquellen (Recommended)" - a Sonnet agent writes it from quoted reputable web sources, checker + verification as for the cards, AI-marked, then a teaser card. |

**Found 2026-10-01: the answer stamp was not the answering model.** `opus_handoff.answer` stamped the constant `OPUS_MODEL` on every answer. The transcripts' `model` field shows 11,456 answers by Opus and 8,471 by Sonnet 5.5 (sessions of 2026-09-27..10-01; e.g. WB check/verify/rewrite stages of chunks 01/02/04/05/06, WD1 r0-r2 parts, the scope review, WC r1 of chunks 01-03, 2,170 image checks), 1 ambiguous (Opus). Census: `output/remediation/model_census/ANSWERS_TRUE_MODEL.jsonl` (+ its script). Nothing is re-answered (O12 makes Sonnet the answering model); the stamp and disclosure are made truthful: branch `wip/model-stamp` (`answer --model`, `ANSWER_MODELS`, `model4.AI_SYSTEM` = "Claude Opus and Claude Sonnet (Anthropic): ...", `AI_SYSTEM_OPUS` kept and accepted). 185 live cards whose final text a Sonnet rewrite wrote get the new disclosure through a journalled correction lane (`wip/fixes`).

**Done today:** WB chunk 06 steps 17-21 written and live (df03b5d: 441 cards, 7 cleared, 0 overwrites, re-accepted); records c984be6. The three lane workflows started this morning on Sonnet with Opus stamps were stopped (WC wf_626cfd97-03a, WD2 wf_e0298c06-b9f, WB wf_2bcd6924-5eb); their recorded answers stand (1 import: chunk 05 check2, Temple of Augustus cleared). Do not resume those runs - relaunch with the patched scripts.

**Order to the end** (one step after the other where they depend; RAM: at most ~14 agents at once):
1. Merge `wip/model-stamp` (after its review/fix, workflow wf_f0f46ee0-632) into `integrate/wave1`, gates; commit the patched scripts `orchestration/wb-continue.js`, `wd2-image.js` and the new state-aware `wc-continue.js` (the old wc-mass scripts re-import imported rounds and are refused).
2. Relaunch: `wb-continue.js` `{"runs":["wb-ws-2026-09-27-05","wb-ws-2026-09-27-02"],"width":4}`; `wc-continue.js` `{"runs":["mass-2026-09-27-01","mass-2026-09-27-02","mass-2026-09-27-03","mass-2026-09-27-04","mass-2026-09-27-05"],"firstBatchBase":4100,"width":6}`; `wd2-image.js` `{"width":4,"run":"output/remediation/served_image/served-image-2026-09-30","handoff":"output/remediation/handoff/served-image-2026-09-30"}`.
3. From 2026-10-01T14:32Z: the re-queue of v3 (3 sites) and v3d (Nea Paphos), PHASE4_V3_RUNBOOK 9.1, from the p4-pilot worktree fast-forwarded to `integrate/wave1` (between rounds), answers by Sonnet with `--model claude-sonnet-5-5`; then `orchestration/p4v3_write_loop.sh` / `p4v3d_write_loop.sh`.
4. Merge `wip/fixes`, `wip/wd3`, `wip/wn` as their build workflow (wf_3c71f215-985) delivers them; gates each.
5. Card sittings for WB 05/02 once their outcomes exist (steps 22 on; CARD_DESCRIPTIONS 5.4/5.5). **Before every push: merge `origin/main`** (another session pushes to main: 6c31821), push a fixed SHA, after-deploy checks.
6. WC writes per built chunk (`orchestration/wc_write.sh`), WD2 replace/plan/chunk writes (runbook 3.5), the card disclosure correction lane, the two renames (Temple of Augustus, Split -> Pula; the U+200C name at Persepolis).
7. WD3 (fields, O13-O15): population, rounds, waves; owner list. WN (O16): 20-site pilot with judge, then mass. A WC site-list run over every WB run's DESCRIPTION_DEFECTS.jsonl.
8. WB over the WC/WN texts (`select --basis WC`, CARD_DESCRIPTIONS 5.2) incl. the renamed site, then sittings.
9. The card_stats wave (after WD1/WD2/WD3), the site_external_ids follow-up of each WD1/WD3 wave.
10. WF: static export, Qdrant resync, IndexNow, the final measurement of error rates per field (reporting only, O1), docs (HANDOVER, CLAUDE.md top paragraph, AUDIT_LOG, memory), and one owner list of everything that stays empty or unsourced.

A heartbeat (session cron, every 30 min) re-invokes the orchestrator: if a workflow died on a usage limit it is resumed from its run id; if nothing runs, the next item above starts. Nothing is ever half-written: a write step is either accepted or rolled back before the next starts.

**Progress 2026-10-01 (newest last):**
- ~12:30Z usage-limit reset; workflows stopped and resumed with explicit Sonnet models.
- WB complete: chunk 05 (steps 22-26, 5611042/46ea685) and chunk 02 (steps 27-31, 90708d4) live, re-accepted, 0 overwrites. A parallel session's deploy (4b8c1a5) nearly re-imported the old card file; averted (AUDIT_LOG). Peer sessions ancientmap-aa/-5b announce pushes to main first.
- Builds merged: wip/model-stamp, wip/fixes, wip/wd3, wip/wn (suite 9,041 passed); pushed bfa5b5e (WN disclosure in the API). Regression fixed: wc4.check_record takes the written checker (dc80687; p4wc and p4 acceptances 0 deviations).
- Live: name-fix (2 renames), card-disclosure s001/s002 (185 cells), P4 v3 re-queue p4-2214 (2 sites). House of Dionysus and Paphos Archaeological Park due again 2026-10-03T14:33Z (one-shot cron set).
- Inventory of unwritten lanes (agent report): country-b2, name-key-lyra (Nr. 9), VPS Nr. 8 -> workflow apply-delivered; 5 shared-item duplicate pairs -> workflow duplicates-lane (research + build); Hadrian's Wall Path -> next scope wave; WD1 follow-ups after WD3; WF last.
- Running: WC chunks (wc-continue wf_dca4b49f-f99), WD2 replace re-export (partial dir moved to handoff/_partial-2026-10-01_...), WD3 (wd3-run wf_760ce4cd-297: pilot 80 sites, wave labels 2026-10-01a/b).

## 8. 2026-10-03 (newer than section 7) - the harness changes: MiniMax Code replaces Claude Code

**Owner decision of 2026-10-03** (verbatim): "ich will claude code damit ersetzen. es muss zuverlässig
mit hoher qualität alle offenen punkte im Ancient Nerds projekt aschließen können." Claude Code is too
expensive; the remaining work runs in MiniMax Code CLI (`mcode`, `MiniMax-M3.1-Flash-Preview`, M Plan
login). This supersedes O12 (Opus orchestrator, Sonnet subagents) for all new work. Setup and measured
behaviour: owner memory `reference-minimax-code-cli`.

What this changes, in order, before any MiniMax answer is written to production:
1. **Truthful stamp and disclosure.** `opus_handoff.ANSWER_MODELS`, `model4.AI_SYSTEM` (and the
   gates/acceptances that accept a fixed set of disclosure strings) must accept a MiniMax stamp and a
   disclosure that names MiniMax for texts it writes or checks; tests first.
2. **No Workflow tool.** The `orchestration/*.js` scripts run only in Claude Code's Workflow runtime and
   cannot be resumed from mcode (their `wf_...` run ids are Claude Code state). Their operator steps are
   plain commands; a Python driver replaces them: export/validate/import run directly, and each batch is
   one `mcode exec --permission full --effort <level> --timeout ... --output-format json` following
   its `brief`. The driver checks after every batch that no tracked file changed (`git status`), keeps
   each run's exec JSON, and records `--model MiniMax-M3.1-Flash-Preview` as the stamp.
3. **Calibration.** Before any lane's mass run: M3.1 Flash re-answers already-answered batches of that
   lane type (WC sentence check, WD3 field research, WB checker/writer, WD2 image) into a copy of the
   handoff; agreement with the recorded answers is measured against a threshold fixed before the run.
   A lane that fails stays on hold and goes to the owner.
4. Then the order of section 7 continues from where the progress log stands.

**Owner decisions of 2026-10-03 for the MiniMax Code phase** (asked once; answers):

| # | question | answer |
|---|---|---|
| O17 | Who builds the prerequisites (truthful stamp/disclosure, Python driver replacing the Workflow tool) | **mcode alone** - no Claude review. |
| O18 | Calibration threshold per lane | **>= 90 % agreement with the recorded answers and 0 false sources** (an invented or wrong citation); else the lane holds and goes to the owner. |
| O19 | Public AI disclosure for texts M3.1 Flash writes or checks | **One combined disclosure** naming both families, e.g. "Claude (Anthropic) and MiniMax M3.1 Flash (MiniMax)": one new `AI_SYSTEM` string for new writes; existing writes keep their strings. The answer stamp itself stays per answer and exact (`MiniMax-M3.1-Flash-Preview`). |
| O20 | Weekly quota stop (shared with Lyra) | a batch run stops when `current_weekly_remaining_percent` of the plan (`/v1/token_plan/remains`) is **<= 10 %**, and resumes after the reset. |
| O21 | Where | **local first**; the VPS only after the calibration has passed. |
| O22 | Parallelism | **"so viel wie möglich ohne das minimax 429 wirft"**: the driver starts small and raises the number of concurrent `mcode exec` runs while no 429/rate-limit appears, backs off on the first one; local RAM caps it (~14 agents, PROJECT_LESSONS). |
| O23 | Effort for answering/judging agents | **max**. |

Also found 2026-10-03: `.git/config` had `core.bare = true` since 2026-10-02 18:55 (cause unknown, an earlier session) - every git command failed; reset to `false` with the owner's consent.
