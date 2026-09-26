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
