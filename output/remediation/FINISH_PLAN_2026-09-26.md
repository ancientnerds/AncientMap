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
