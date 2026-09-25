# Handover: the 2026-09 remediation of all 5,004 sites

Written 2026-09-22 at the end of the Phase-3 write and brought up to date on 2026-09-25 after the
Phase-4 mass run, for a session that does not have this one's context -
possibly in another harness. Read this first; `AUDIT_LOG.md` carries the evidence behind every number
below (about 10,000 lines; the Phase-4 entries - pilots 3-4, the defect scope, the mass run, lane L -
are on branch `wip/p4-pilot` until it is merged, see 2.4), and the plan is
`docs/procedures/SITES_DB_REMEDIATION_2026-09.md`.

## 0. Resume point - paused 2026-09-25 evening at the owner's request (usage limit)

Everything below section 0 was written before these last steps; where they differ, this section wins.

**Done and live since the Phase-4 mass run** (every write journalled, rehearsed, read back, its
rollback rehearsed, accepted with 0 deviations; the day's production log is in the session notes and
in the AUDIT_LOG sections of 2026-09-25):
- `wip/p4-pilot` merged into `integrate/wave1`, `origin/main` merged in; **Push #2 = 417386f**
  (P5 sitting: backup drill passed, 1,107 cards in 13 accepted steps, card file byte-identical,
  0 boot overwrites), then **2aa68cf** (the D9 run). `integrate/wave1` is ahead of `main` again by
  the commits after 2aa68cf (docs, dangling-markers, acceptance draw, audit) - no code a deploy needs.
- Lane L: 4,003 March-AI texts marked. card_stats: 4,106 cells over 1,082 cards (wave 2026-09-25
  plans 0). Static export on the VPS (root-owned files fixed), Qdrant resync, IndexNow (5,085 + 4,919).
- Acceptance run `draw-2026-09-25` recorded **FAIL on A3** (D1, Kuntur Amaya; no judge ran). Class
  repaired: `orphan-citations` (69 sites), the D9 run (scope v2, 6 sourced descriptions),
  `dangling-markers` (3 held sites). **D1 and D4 now hold on all 5,004 curated sites.**
- `verify_writes4` gained `--allow-stamp` (use `'phase4l:%'` for P4; for L use the orphan-citations,
  `phase4:%` and dangling-markers stamps) and multi-run `--run` (pilot4, mass, d9).

**In flight, stopped cleanly:**
1. **Fresh acceptance `draw-2026-09-25b`** (seed 20260926, canaries 20260927; sealed in AUDIT_LOG;
   D1-D6 hold). Stage 1: 652 questions in 54 batches under
   `output/remediation/handoff/acceptance-2026-09-25b-s1`; **14 answered** (card_description-01
   complete, -02 partly). Resume the judges with the workflow script `C:/tmp/acceptance_s1.js`
   (resumeFromRunId `wf_57394bdd-e52`, same args; each agent runs `judge.py brief ... --batch-id B`
   and follows it; an already-recorded answer is refused as write-once - the re-run judge of
   card_description-02 skips those labels). Then: `opus_handoff.py validate`, `judge.py import-stage1`,
   re-asks (`export-reask`, at most twice), stage 2 / stage 3, `judge.py result`; commands in the
   AUDIT_LOG section of the acceptance tooling. **No remediation write may touch a drawn site
   before the result (V3)** - that includes the 19 re-queued `revision-too-fresh` sites below.
2. **Code audit** (docs/procedures/CODE_AUDIT.md, backend mode on the remediation's api/pipeline
   changes + the production-writing tooling): steps 0.5-5 done, **no fix made yet**; report
   `output/remediation/CODE_AUDIT_2026-09-25.md` (6e5d028). The 14 changed api/pipeline files check
   out; the quality gate's hard conditions pass. **Fix before the next production write**: the 11
   Major tooling findings in its fix order - above all `write_gate4 --accept` taking a log with a
   failing and a passing run appended, `
` -> `
` on Windows in `prod_write.send` /
   `write_stage.run_sql` (read-only checks found no damage), a psql timeout leaving no
   `STOPPED.json`, `--batch` skipping the stopped-batch check, no 100-site cap on `--step`. Run its
   mutation sweeps in a scratch worktree (the acceptance code imports `prod_write` and
   `mechanical/lane`). A stray `%TEMP%/gettext.py` (an agent's page fetcher of 2026-09-23 that
   shadowed the stdlib module) was renamed to `fetch_page_text_2026-09-23.py`.

**Still open after that:** the 19 `revision-too-fresh` sites (re-queued by mass4 from
2026-09-26T21:30Z; lane-L-first order as in the D9 run; only after the acceptance result);
the owner items in `HUMAN_ONLY.md` (Ahin Posh coordinates, 21 wrong-both rows, Chiapa/Zoque,
gallery eye labels, 11 lyra alias keys, 16 old shorts, deleted Commons files on the VPS, 876 vs 904);
a final docs pass (this file's sections 2-7, CLAUDE.md's top paragraph) and a push of the docs.

## 1. The task

Every one of the 5,004 `ancient_nerds` sites in the production database must be **correct** - and
Martin's expanded order of 2026-09-21 added three things to the original plan: the model must
**correct** the content and not merely flag it, it must **research online** and attach **evidence and
sources** to each correction, and everything only a human can do must be listed in one table
(`HUMAN_ONLY.md`).

Phase 3 (finder -> reviewer -> only `refuted = false` applied, conditional `WHERE`, journal entry)
writes only `country`, `site_type`, `period_start`. Phase 4 rewrites `description` from sentences of
a pinned Wikipedia revision that code assembles and a model only selects (design entry [6],
`docs/procedures/PHASE4_CONTRACTS.md`); Phase 5 writes the card texts (`CARD_DESCRIPTIONS.md`); Phase 6
is the follow-through and the final acceptance. **Since the owner's order of 2026-09-23 ("no DeepSeek
any more - everything with Opus") every model judgement is answered by Opus agents of the
orchestrating Claude Code session through the handoff** (`scripts/remediation/opus_handoff.py`;
AUDIT_LOG, "the Opus handoff").

## 2. State, 2026-09-25

### 2.1 In production (each row journalled in `remediation_change_log`, each lane rehearsed, read back and its rollback rehearsed)

| lane (run stamp) | what | size | evidence |
| --- | --- | --- | --- |
| Phase 3 mass (`phase3:batch-*`), 2026-09-21/22 | `site_type` 596, `period_start` 389, `country` 9 | 994 rows at 952 sites | 2.5 below |
| `2026-09-22_mechanical-site-type-shape`, `-period-name`, `-uk-parts` | shape repair, period labels, UK parts (B9) | 3 / 220 / 23 rows | AUDIT_LOG "applied today, and the search pilot that failed" |
| `2026-09-22_external-id-repair`, waves 2, 3, 4 (`source-url-split-wave4`) | Wikidata/enwiki ids, two-URL `source_url` | 26 rows at 19 sites; 13 at 12; 2; 50 | AUDIT_LOG 2026-09-23; `C:/tmp/applied_today.md` |
| gap lane (`phase3:gap-*`), 2026-09-23 | the 802-question gap run's writes | 17 rows at 16 sites | `verify_writes.py --lane gap` |
| owner-case coordinates, waves 1 and 2 | `lat`, `lon`, `geom` with two independent witnesses | 27 rows (9 sites) + 12 rows (4 sites) | `bcases/coords_plan*/` |
| image lanes | `image_kind` 105 (G0) + 30 (G0b), attribution 125, liveness 9, Dedan's thumbnail -> NULL 1 | 270 rows | AUDIT_LOG 2026-09-23/25 |
| `journal-reversal-1`, `-2` (2026-09-23) | 3 cells (Ahin Posh Tape -> Afghanistan, 2 starts); the re-review's 45 sites | 3 + 53 cells | `mechanical_reversal*/` |
| **`journal-reversal-3`** (2026-09-25, `e0cf70d`) | the Opus re-verification's reverts of the DeepSeek-decided rows | **488 cells over 435 sites** | AUDIT_LOG "journal-reversal-3" |
| `wrong-both` (2026-09-25, `5bca584`) | corrections carried by a found verbatim quote | 17 cells over 13 sites | `mechanical_wrong_both/` |
| `scope-e4` (2026-09-25, `be5d6c5`) | E4 scope decisions | 218 cells over 109 sites: 78 retired (19 of them duplicates), 14 pending, 17 in scope | `mechanical_scope/` |
| **Phase 4 P4** (`phase4:p4-NNNN:chunk-0001`), 2026-09-24/25 | `description` + its `raw_data` provenance, defect-scope sites only | **986 sites written, 2 taken back: 984 live, 1,968 rows carried** | `wip/p4-pilot`: `phase4_runner/MASS_RESULT.md` |

**The Opus re-verification** (2026-09-24/25, `output/remediation/opus_audit/`, rules sealed before the
first verdict in `RULES.md`): the 934 production rows a DeepSeek finder and reviewer decided, judged
by independent Opus judges in four rounds - final **keep 481, revert 453** (`DECISIONS.jsonl`
`a1f5cb87...`); the reverts are journal-reversal-3. Of the 42 rows a judge called wrong both ways, the
wrong-both lane wrote 13 whose value a found verbatim quote carries and listed 29
(`mechanical_wrong_both/SKIPPED.jsonl`), 21 of them for a human.

**The independent acceptances, both 0 deviations** (read-only, 2026-09-25): Phase 3 mass lane - of
the 994 writes **499 carried, 495 superseded** by later lanes (reversal-3 426, reversal-2 45,
wrong-both 13, uk-parts 5, reversal-1 3, site-type-shape 3), 80 withheld unchanged; gap lane 14
carried, 3 superseded, 12 withheld (`verify_writes.py`, command in AUDIT_LOG's Phase-6 runbook step
7). Phase 4: `verify_writes4.py --lane p4`, step 14: 1,972 planned, 1,972 journal rows, 1,968 carried,
4 not yet written (the two sites taken back), **984 sites re-verified with V1-V15**.

**Deployed**: `122249d` (2026-09-23; migration 0023, the `source_url` control-character CHECK) and
`8a957b4` = **Push #1** (2026-09-23: the source line under the description, provenance in the API,
licence lines in disclaimer and `terms.html`). `origin/main` is `b1596c5` (2026-09-24 23:10 +0200);
`integrate/wave1` was 92 commits ahead of it before this record.

### 2.2 The Phase-4 mass run (complete)

The owner's defect scope (`SCOPE4.json` v1, 1,623 sites: Phase 3's cleared description and card
defects plus 876 ungrounded cards) left **1,578 sites in 106 batches** after pilot 4's. 1,392 selector
and 1,003 review questions were answered by Opus through the handoff (one agent per batch and stage,
one at a time); 960 sites were written in 13 accepted steps, every step 0 deviations. The mid-run
audit (45 written sites) found 1 WRONG_SITE (Roman Bath, York: the lead is about the 1929-31 pub):
writes stopped, the reviewer gained a DROP line (pin `097c4589...`), a check of all 336 sites written
by then flagged Altar of Athena Polias too, and both were taken back with `revert4.py --site` and held
(Kit Hill's flagged sentence, the 19th-century mine, was kept as a later use of the hill itself). The
500-site audit (10 sites) found nothing. 618 planned sites are held and keep their text (620 with
the two taken back; reasons in `runs/mass-2026-09-25/HOLDS4.jsonl`); lane-W coverage 933 of 1,321 =
70.6 %, reported, not gating. Everything, with digests: AUDIT_LOG (`wip/p4-pilot`), "Phase-4 mass
run: 1,578 sites planned, 960 written ...", and `phase4_runner/MASS_RESULT.md`.

### 2.3 Running now

**Lane L** (legacy AI marking: `raw_data` provenance only, never a description) is being written by a
background loop from the worktree `.claude/worktrees/p4-pilot` (only gitignored logs change there;
do not touch its scripts or logs). Re-planned after the mass run: `LEGACY4.jsonl` `62772cac...`, 334
batches, **4,003 rows** (984 refused `written-by-p4`, 17 unclaimed - HUMAN_ONLY D7). At 14:02 CEST on
2026-09-25 steps 1-2 were accepted (193 rows carried, 0 deviations; `logs/p4l/accept-step-NN.log`).
It ends with `verify_writes4.py --lane p4l --plan logs/_write_apply_p4l/LANE_PLAN.jsonl --complete`.

### 2.4 Next, in this order

0. **Lane L to its end** (above). Then **merge `wip/p4-pilot` into `integrate/wave1`**: the merge
   branch `wip/merge-p4` (worktree `.claude/worktrees/merge-p4`) holds `wip/p4-pilot` up to `9f01785`;
   it lacks the mass-run record `1cfda28` and `integrate/wave1`'s five Phase-6 commits `ff9a570` ..
   `a2ac917`. Push #2 pushes `integrate/wave1`, so the merge comes first.
1. **The Phase-6 runbook** - AUDIT_LOG (`integrate/wave1`), "Phase 6 follow-through prepared", "The
   runbook", steps 1-8, in order: (1) the card_stats wave `card-stats-2026-09-23` (re-plan first: its
   premise holds `md5(description)` and the P4 writes moved it); (2) name keys (expected: nothing to
   plan); (3) the static export on the VPS (chown the root-owned files, export as the container
   user); (4) the Phase-5 sitting and **Push #2** (HUMAN_ONLY D5); (5) the Qdrant resync; (6) the
   IndexNow catch-up; (7) the checks, both acceptances; (8) the acceptance draw and its judging
   (`acceptance/PROTOCOL.md`, sealed; the draw excludes the mass run's audit samples
   `logs/p4_mass/midrun_sample.txt` and `audit500_sample.txt`).
2. **The 19 `revision-too-fresh` sites** of the mass run: `mass4.py` re-queues them itself 48 h after
   their hold, the first at 2026-09-26T21:30:14Z. Any P4 write they bring must land **before the
   draw** (PROTOCOL: the acceptance is VOID when a write touches a drawn site after the draw); a
   description written after the card_stats wave is the next card_stats wave's work.

### 2.5 Phase 3's own numbers (measured 2026-09-22)

Re-derived on 2026-09-22 from the run's own files with the pipeline's own parser
(`discover_stage.parse_answer`) and from production (read-only). Four figures of the first version of
this table were wrong; they stay visible in the last column rather than being overwritten.

| | | first version said |
| --- | --- | --- |
| sites examined | **5,004** (all of them, not the 1,813 worklist), in 334 batches (333 x 15 + 1 x 9) | |
| fields | 25,020 = 24,255 answered + 760 never asked (152 sites over the evidence bound, `model.json` `skipped`) + 5 empty model streams (`model.json` `failures`) | |
| fields answered | 24,255 over 4,852 sites | |
| verdicts: correct / wrong / unverifiable / none | 11,747 / **4,710** / 7,761 / 37 (sum 24,255) | wrong 4,708 (the row then summed to 24,253) |
| answers with two different `VERDICT:` values | 42 (the first one counts); none of them reached the write plan | |
| reviewer | 4,579 asked (4,569 calls + 10 resumed): **2,108 cleared** (`applies`), 2,202 refuted, 173 unresolved, 161 with problems | confirmed 2,204 (= asked - refuted - unresolved, which counts 96 answers with problems as confirmed) |
| planned writes (writable columns only) | 1,074 rows at 1,022 sites | |
| **written to production** | **994 rows at 952 sites** - 596 `site_type`, 389 `period_start`, 9 `country` | 994 rows at 1,022 sites (1,022 is the *planned* site count) |
| held by hand / stopped by the boundary check | 72 / 8 | |
| planned rows deliberately left unchanged | 80 | |
| acceptance, both directions | **0 deviations** - re-run 2026-09-22 with the chain-following acceptance: 994 carried, 0 superseded, 80 unchanged, 0 moved (2026-09-25: 499 carried, 495 superseded, see 2.1) | |
| written rows whose finder citation is not in the batch's own evidence | **44** (22 `site_type`, 22 `period_start`), plus 2 of the 80 unwritten; the writer refuses such rows since 2026-09-22 (`RULE_CITATION`) | not measured |
| judged sites shown an evidence page cut at the 61,440-byte cap, unmarked | 27 (23 `wikidata_entity`, 4 `enwiki` pages) | not measured |
| spend | ~**$27**: finder $22.51 over 24,260 calls (`model.json` totals of `runs/mass`; the ledger holds $23.72 for every finder call including the gold rounds), reviewer $4.63 over 4,569 calls (`review.json`; ledger $4.65) | ~$31 (finder 25.87 + reviewer 4.65; the 25.87 has no derivation in the run's files) |

**The 7,761 unverifiable fields stay unverifiable.** The search pilot (DeepSeek finder, MiniMax
searches, 2026-09-23) and the sitelink pilot (other-language Wikipedias, answered by Opus, 2026-09-24)
both failed their sealed thresholds: sources of that kind import their own errors (AUDIT_LOG, "the
sitelink pilot, answered by Opus: FAIL"). A future route needs a source the gold standard can trust
more (national registers, excavation reports); none is built. The gap run (802 questions over 194
sites) and the external-id repairs are applied (2.1).

## 3. Where everything lives

**Versioned** (a fresh clone has it):

| path | what |
| --- | --- |
| `scripts/remediation/phase3/*.py` | the Phase-3 runner: `discover_stage`, `fetch_stage`, `model_stage`, `review_stage`, `write_stage`, `mass_run`, `mutation_sweep`, `snapshot_plan` |
| `scripts/remediation/phase4/*.py` | the Phase-4/5 runner: `mass4` (the rounds), `run4`, `plan4`, `scope4`, `prompts4`, `verify4` (V1-V15), `review4`, `write4`, `revert4`, `audit4`, `legacy4` |
| `scripts/remediation/opus_handoff.py` | the one contract through which Opus answers every model question (export, `answer`, `validate`, import) |
| `scripts/remediation/opus_audit/`, `output/remediation/opus_audit/` | the Opus re-verification: sealed rules, verdicts of rounds 1-4, quote check, decisions |
| `scripts/remediation/mechanical/` | the journal lanes (`apply.py --lane <name>`: country, reversals 1-3, wrong-both, scope-e4, card_stats, ...), each with `--rehearse`, `--probe-guards`, `--verify`, `--rehearse-rollback` |
| `output/remediation/AUDIT_LOG.md` | the full record, every number and every adjudicated finding |
| `output/remediation/HUMAN_ONLY.md` | what only Martin can do (German, addressed to him) |
| `output/remediation/HANDOVER.md` | this file |
| `output/remediation/tools/` | the instruments: `write_gate.py` / `verify_writes.py` (Phase 3, lane-aware), `write_gate4.py` / `verify_writes4.py` (Phase 4/5 and L) - see their README |
| `output/remediation/phase4_runner/` (on `wip/p4-pilot`) | `PILOT_THRESHOLDS.md`, `PILOT_RESULT_1..4.md`, `MASS_RESULT.md`, `SCOPE4.json` |
| `output/remediation/acceptance/` | the sealed final-acceptance protocol and its exclusions |
| `output/remediation/phase3_runner/PIECE*.md` | the Phase-3 design briefs, including the 100-step write rule (PIECE6 §7) |
| `tests/remediation/` | the gate suite for all of the above |
| `docs/procedures/SITES_DB_REMEDIATION_2026-09.md`, `PHASE4_CONTRACTS.md`, `CARD_DESCRIPTIONS.md` | the plan and the contracts |

**Local only** (gitignored, on this machine, and not in a clone):

| path | what | size |
| --- | --- | --- |
| `phase3_runner/runs/mass/batch-*/` | **334 batch directories**, 15 sites each (the last 9): `answers/<site-id>%2F<field>.txt` (24,255 files), `evidence/<site-id>%2F<source>.txt` (9,622), `reviews/` (4,579), `writes/`, plus `input.json`, `fetch.json`, `model.json`, `review.json`. The first version said "one per five sites" and "38,456 answer files" - 38,456 is answers, reviews and evidence together | 195 MB |
| `logs/_write_apply/` | one `ROLLBACK.sql` per written chunk (428 files) and the `APPLIED.json` marker per batch (317) - the Phase-3 undo path | 27 MB |
| `logs/_write_dry/` | the full Phase-3 write plan `ALL_ROWS.jsonl` (1,074 rows) and `ALL_REFUSED.jsonl` (23,946) | 35 MB |
| worktree `.claude/worktrees/p4-pilot`: `phase4_runner/runs/` | the Phase-4 runs: census, pilots 1-4, `mass-2026-09-25` (batch directories, `LEDGER.jsonl`, `HOLDS4.jsonl`) | |
| the same worktree: `logs/_write_apply_p4/`, `logs/_write_apply_p4l/` | the P4 and L apply roots: per batch `PLAN.jsonl`, `REFUSED.jsonl`, `APPLIED.json`, chunks; `LANE_PLAN.jsonl`; `ACCEPTED/step-*.json` | |
| the same worktree: `logs/p4_mass/`, `logs/p4l/`, `handoff/` | the mass run's and lane L's logs, audit sheets and verdicts; every handoff question and Opus answer | |
| `logs/` (the rest) | gate and acceptance logs, the hold list, the working copies of the instruments | ~150 MB |
| `phase3_runner/LEDGER.jsonl` | the Phase-3 cost ledger. It is *tracked* and 18 MB, which is worth a look | 18 MB |

The Phase-3 state is carried to another machine by one archive, made for exactly that:

    output/remediation/run-2026-09-22-complete.tgz     # 34 MB, 49,470 entries
    # tar -czf run-2026-09-22-complete.tgz -C output/remediation phase3_runner/runs \
    #     logs/_write_apply logs/_write_dry logs/_country_mismatches.txt logs/review_totals.txt

No such archive exists yet for the Phase-4 runs. The **results** are durable in production regardless:
every write has a `remediation_change_log` row with old and new value, so the undo path is
reconstructible from the database even without those files.

## 4. How to run it

```bash
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
export PYTHONPATH="C:/PythonProjects/AncientMap;C:/PythonProjects/AncientMap/scripts/remediation"

# the gate suite - DB-less, and the only definition of "green"
# (2026-09-25 on integrate/wave1: 6,313 passed, 3 skipped, 57 deselected)
./.venv/Scripts/python.exe -m pytest -q -rs --timeout 300 -m "not integration and not live_llm"

# Phase 3's writer: dry first (it prints "dry run, nothing is written"), then for real; run the
# versioned tools in output/remediation/tools/ - the copies in logs/ predate the lanes and the stops
./.venv/Scripts/python.exe output/remediation/tools/write_gate.py --step 100
./.venv/Scripts/python.exe output/remediation/tools/write_gate.py --apply --step 100

# the independent Phase-3 acceptance - asks the database in both directions; prints
# "RESULT: N deviation(s)". Every later lane that rewrote a phase-3 cell is named by its stamp; the
# full command (six --allow-stamp) is step 7 of AUDIT_LOG's Phase-6 runbook
./.venv/Scripts/python.exe output/remediation/tools/verify_writes.py --allow-stamp 2026-09-22_mechanical-uk-parts ...

# a journal lane (mechanical): plan, check, rehearse, apply, read back, rehearse the rollback
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane <lane> --verify | --probe-guards | --rehearse | --apply | --rehearse-rollback

# never re-plan a lane that has written: logs/_write_dry/ALL_ROWS.jsonl is the plan the 994 rows
# were written from (pinned, lanes.REVIEWED_PLAN_KEYS_SHA256); write_dry_all.py refuses to replace
# it, and a measurement goes to --out

# a read-only database question (there is no local database; production is the one that counts)
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map \
  -v ON_ERROR_STOP=1 -t -A -F '|'" < some.sql
```

Phase 4 runs from the worktree `.claude/worktrees/p4-pilot` with the main venv: the per-group
sequence (handoff export, Opus answers, `validate`, import, write gate dry / `--rehearse` / `--apply
--step 100`, `verify_writes4.py`, `--accept`) is written out in AUDIT_LOG's mass-run entry, lane L's
in its own entry. `mass_run.py` and `mass4.py` hash their packages (`phase3/`, `phase4/`) before
every batch, which is why nothing there may be edited while a run is in flight.

## 5. Decisions already taken (do not re-open without Martin)

1. The 72 rows held by hand stay held - the proposals were not proven.
2. The United Kingdom's parts are spelled by region: **`Northern Ireland`**, not `United Kingdom`
   (done: the UK lane wrote it, including the five Phase-3 rows that said `United Kingdom`).
3. The 4 rows refused as "not writable in the columns' shape" are not written.
4. The 29 geopolitical census rows are left as they are.
5. Deploy only after all 5,004 are through - **that condition is met**.
6. **Every model judgement by Opus** through the handoff (owner, 2026-09-23: "no DeepSeek any more -
   everything with Opus"). No DeepSeek, Pi or opencode gateway, ever. MiniMax is not used by the
   remediation: the Phase-4 runs keep searches off (`--searches-off`, no MiniMax client built), and
   the search route of 2026-09-22 ended with the two failed pilots (2.5).
7. B7/B8/B9/B10 are decided (2026-09-21); see `HUMAN_ONLY.md`.
8. The D2 wording and the precise D3 sentence (2026-09-23), both live with Push #1.
9. **Phases 4/5 write only the defect sites** (2026-09-23, "Nur Defekt-Sites"): `SCOPE4.json` v1;
   every other site keeps its description and card.
10. **T8 is reported, not gating** (2026-09-24, `PILOT_RESULT_3.md`); T1-T7, T9 and T10 stay gates.
11. **Lane L marks every March-AI text** (2026-09-24, "Alle kennzeichnen"), not only the scope's.
12. **The owner's order of 2026-09-25** ("keine Fragen mehr, autonom Empfehlungen umsetzen"): the
    recommended path is carried out without asking - under it the 19 duplicate retirements were
    applied (scope-e4) and Push #2 (D5) is authorized.
13. A push to `main` is a live deploy, and `.githooks/pre-push` aborts when the working tree differs
    from the pushed commit. Push #1 is live; Push #2 is runbook step 4.

## 6. Open work

- **Lane L** to its end, then the **merge** of `wip/p4-pilot` and the **Phase-6 runbook** (2.4).
- **The 19 `revision-too-fresh` sites** (2.4, item 2).
- **Owner items** (`HUMAN_ONLY.md`, each with its evidence file): Ahin Posh Tape's point (no second
  independent witness; every source puts it about 95 km from the stored point, near Jalalabad); the
  21 wrong-both rows for a human (of 29 listed); Chiapa de Corzo / Zoque Culture Archaeological Zone;
  Banias / Caesarea Philippi; the gallery vision (C1 admitted no trigger; the eye labels
  `vlm_pilot/LABELS.jsonl` do not exist); the 11 `lyra` alias name keys; objections to the acceptance
  thresholds, only before the draw; the 16 old shorts and the A6 credential; the deleted Commons
  files still served from the VPS; 876 vs 904 ungrounded cards; the Phase-4 hold list (D6) and the
  unclaimed old texts (D7); and the older B1/B2 reading lists (46 names, 171 coordinates, 2 countries,
  `Baltic Sea`).
- Code, recorded and not built: the selector's rule (8) keeps the gap the reviewer's new DROP line
  closes; the gallery G runs' missing links (none can write while C1 admits no trigger); the mypy
  `api/` debt (A7).

## 7. Traps that cost real time here

- **A pipeline's exit status is its last command's.** Always read the log's own
  `GATE_EXIT=` / `WRITE_EXIT=` / `STAGE_EXIT=` / `ACCEPT_EXIT=` / `DRIVER_EXIT=` / `PYTEST_EXIT=` line.
  A background wrapper's exit-code 0 is not the run's exit code.
- **The Opus handoff is a fixed cycle**: a stage exports its questions (`--handoff-export`), Opus
  agents answer each prompt file with `opus_handoff.py answer` (the answer carries the prompt's sha256
  and the Opus model string), `opus_handoff.py validate` must report every question answered, 0
  stale, 0 malformed, and only then the stage imports (`--handoff-import`) through its unchanged
  parser and gates. A prompt changed after its export (a re-pinned question) makes every old answer
  stale: move them aside whole and export again - never edit an answer to fit.
- **One agent at a time, one per batch and stage.** Every pilot and the whole mass run were answered
  so (106 selector and 106 review agents, their answering times never overlapping; AUDIT_LOG mass-run
  entry).
- **No DeepSeek, no Pi, no opencode gateway, no MiniMax for the remediation** (5.6). The gateway
  answered 401 "Invalid credential" to every model on 2026-09-23 anyway.
- **The scope is enforced in the writer, not by discipline.** P4 and P5 refuse every site outside
  `SCOPE4.json` v1 (`outside-defect-scope`, no switch; a changed file is refused against the pin);
  lane L takes no scope and plans from its own `LEGACY4.jsonl`.
- **A Phase-4 acceptance names every run that wrote under `phase4:`.** `verify_writes4.py --lane p4`
  needs `--run runs/pilot4-2026-09-24 --run runs/mass-2026-09-25`: with one run the other's sites are
  found in no run and counted as deviations (`ccfb426`).
- **`verify_writes4.py` reads only the batches that hold a written site** (`004d522`) - reading every
  batch stopped the first mass step on an unassembled one. And the lane plan is every rendered
  batch's `PLAN.jsonl`: a dry run of the next group adds "not yet written" rows to the current step's
  acceptance (step 10: 34). They sit at their old value and are not deviations - read the numbers.
- **Taking back one written site**: `revert4.py --stamp-like 'phase4:p4-NNNN:chunk-0001' --site <id>`
  after `audit4.py hold` with the verdict file; the gate then re-plans the batch without the site. An
  audit draw over written sites must be given the live written set.
- **A dry run is not a write, and it is the cheapest proof.** `write_gate.py` / `write_gate4.py`
  without `--apply` write nothing and still measure the whole plan against production.
- **A write that "failed" may have written nothing.** Prove it: re-run the dry gate and compare the
  numbers. That is how the cp1252 crash below and the T03 assert of 2026-09-25 ("35.000 BC") were
  shown to have left the database untouched.
- **Encoding.** A console that cannot encode a site name killed a whole wave on a `print` **before**
  the first row, because `PYTHONIOENCODING=utf-8` was missing from a background launch. The gate now
  reconfigures its own streams.
- **The `.env` file is policy-protected.** Never read it; establish a credential's presence
  functionally. `LyraSettings` reads it at runtime - that is the pipeline's business, not the agent's.
- **`matched_0` is the load-bearing number of a write.** If a planned row no longer holds the old
  value the plan assumed, the write must affect 0 rows - not "close enough".
- **The journal table is project-wide.** `remediation_change_log` carries rows from every phase and
  lane; each is stamped (`phase3:batch-…`, `phase4:p4-…`, `phase4l:p4l-…`, `2026-09-2N_mechanical-…`).
  Never present the table's total as one action's count.
- **A card_stats wave's `ROLLBACK.sql` expires.** It carries the write's premise guard (guard 5),
  which hashes every curated `(site_type, period_name)` pair and each planned site's inputs
  (fields, `md5(description)`, content links, images, likes, bookmarks). The undo refuses as soon as
  any of them moves - in practice at the next field or description write. From then on the wave is
  not undone from its file: the next card_stats wave recomputes the cards from the inputs as they
  are. Each wave's `BASIS.json` must be committed with the plan that is applied: the next wave's proof
  reads it (`scripts/remediation/mechanical/card_stats.py`, "The basis a wave's proof stands on").
- **Never point the integration tests at production.** They INSERT test rows into `unified_sites`.
- **Never weaken a check to make it green**, and never edit a test to match prose - if a test really
  encodes a superseded defect, rewrite it strictly stronger and say why.
- **Do not trust `comm`/`sort` across Linux and Windows** without fixed collation, and remember a
  Windows Python writing `/tmp/x.sql` writes `C:\tmp\x.sql`, not Git Bash's `/tmp`.
- **Commit messages and apostrophes.** A message written through a Python single-quoted triple
  string makes the apostrophe awkward, and rather than escape it I wrote around it - which is how
  three commit messages in this action came out as "the file is own numbers". Escape it, or use a
  double-quoted string.

## 8. Portability to another harness

- The **write path is harness-independent**: conditional `WHERE`, journal row, `ROLLBACK.sql`,
  read-back, and an acceptance that re-reads the database. It was proven on production.
- The **model stages** run through the handoff: any harness whose agents can read a prompt file and
  run `opus_handoff.py answer` can answer them; the answer names its model, and the ledger and the
  published disclosure name that model. The Pi transport (`pi -p --mode json`) was removed with the
  DeepSeek route on 2026-09-23.
- **Cost, measured on 2026-09-22** (before the Opus order): the same token volume on a Claude model
  came out about 68x the DeepSeek price (18,610 judgements: DeepSeek $17.07, the Claude comparison
  $1,156). The Opus answers of the handoff are not metered per call (the ledgers record them as
  `unmetered`).
- Everything an agent writes down is **English**; `HUMAN_ONLY.md` and the chat stay German because
  Martin reads exactly those.

### What a foreign machine does not get from this repository

| needed | where it lives | who can supply it |
| --- | --- | --- |
| the commits | `origin/main` = `b1596c5` (2026-09-24); `integrate/wave1` and `wip/p4-pilot` are local branches | push them, or copy the repository |
| the run state and the undo paths | Phase 3: `output/remediation/run-2026-09-22-complete.tgz`, 34 MB; Phase 4: the worktree's gitignored directories (section 3), no archive yet | copy the files, then see the tools README for the restore order |
| the SSH alias `ancientnerds` | the user's SSH config, outside the repo | Martin, or use the VPS address directly |
| the database credentials | `.env`, policy-protected - never read it, establish a credential's presence functionally | Martin |
| the Python environment | `.venv/` locally; the repo carries the `requirements*.txt` | rebuild it |

Everything else - the code, the plan, the audit, the instruments, the tests - is in git.
