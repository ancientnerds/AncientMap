# Cards workstream plan (D1-D5, D9, card part of D10)

Code read: `.worktrees/db-final` (origin/main + decisions record). Run state read from the main checkout. Production read-only: `C:/tmp/wf_map_cards/q1-q4.sql`, `sites.csv`, `desc.csv`, `defs.json`.

## 0. Key calls

1. **Keep lane WB's machine and version everything beside it.** Prompts are pinned by sha256 in every export (CARD_DESCRIPTIONS 2.3). Editing `prompts.py`, `answers.py` or `contract.py` makes runs 01-06, the gap run and the pilots unimportable, and they are also the calibration material. So shorts-v1 goes into new sibling modules, selected by `RUN.json["contract"]`. The v1 files stay byte-frozen.
2. **There is no `wb` lane in `mcode_driver.py`** (only `wd3`, `wc`, `calibrate`). WB was always driven by Workflow JS scripts (`output/remediation/orchestration/wb-mass.js`, `wb-continue.js`, `wb_step.sh`; gitignored). D6 makes `mcode_driver` moot for this work, because it is MiniMax-specific (`EXEC_MODEL`, quota stop). Plan: a new `wb-shorts.js` using `agent(prompt, {model, effort})` per role. The Workflow API supports both options.
3. **Three shared defects must be fixed first.** They affect other workstreams too (see §6):
   - Stamps and `AI_SYSTEM` still name MiniMax.
   - No `claude-haiku-5-5` stamp exists.
   - The boot import of `card_descriptions.json` makes every card sitting fragile.
4. **D3 and D4 (description enrichment) are the longest pole.** Cards for Shorts-pool sites must be written after enrichment, because enrichment changes `desc_sha256` and stales any card written earlier. Non-pool sites can be carded now.

## 1. Existing tools (worktree paths)

| Tool | What it does |
| --- | --- |
| `docs/procedures/CARD_DESCRIPTIONS.md` | Contract §1-3, runbook §5.1 (one stage), 5.2 (pilot), 5.3 (mass run), 5.4 (write steps), 5.5 (card file), 5.6 (undo) |
| `scripts/remediation/teaser/{contract,prompts,answers,run}.py` | Contract, prompts, answer parsers, CLI |
| `teaser/run.py` | `select`, `export`, `brief`, `check-answer`, `import`, `status`, `outcomes`, `judge-export`, `judge-import` |
| `scripts/remediation/opus_handoff.py` | `export`/`validate`/`answer --model` handoff recorder (`validate` checks every question answered) |
| `scripts/remediation/mechanical/teaser.py` | `plan --run R --step N`, `accept`, `close-reverted`, `card-file --steps A-B`, `stale` |
| `mechanical/apply.py` | `--lane teaser-{prov,card}-sNNN --emit/--rehearse/--probe-guards/--apply/--verify/--rehearse-rollback` |
| `scripts/remediation/phase4/card_json.py` | `--check`, `--regenerate` (renders the card file from production) |
| `output/remediation/orchestration/wb_step.sh RUN N` | Runs one whole write step |
| `output/remediation/model_census/model_census.py` | Maps handoff answers to the real model via Claude Code transcripts |
| `scripts/remediation/gallery_audit/calibrate.py` | Pattern for `seal` (THRESHOLDS.json + sha256 log before any verdict), `jobs`, `evaluate` |
| `mcode_driver.py calibrate` (`Calibration`, `AGREEMENT_FLOOR=0.9`) | O18 comparison logic; reusable for the comparison only |
| `scripts/remediation/wc/` + SENTENCE_CHECK 11-12 | `wc-list` and `wn` modes (write round with verbatim quotes, `verify`, `verify2`, `build`, judge pilot, `write_gate4 --group WC`) |
| `pipeline/utils/card_provenance.py` | Provenance v2 (exact key set; `shorts_pin`, `card_ai`) |
| `pipeline/video/shorts_export.py` | `card_pin_and_mark` pins S13 |
| `pipeline/video/shorts_render.py:87` | `TEASER_NOTE` constant, today "Claude / Anthropic, MiniMax M3.1 Flash" |
| `api/services/card_descriptions.py` + `api/main.py:139` | Boot import; overwrites DB cards from the file |
| `pipeline/utils/public_sites.py:151` | `PAGE_COLUMN_STAMPS = wb-teaser-card-%` |

## 2. Run state (measured 2026-10-08)

Journal high-water mark 345369. 34 write steps are done and accepted. **Next step is 35.** `site_shorts` has 0 rows.

**Teaser provenance, 2,830 total.** All are v2.
- The 167 gap-run cards (`wb-cardgap-2026-10-07`) are stamped `ai_system` "Claude (Anthropic) and MiniMax…". All their `STAGE-*` answers are MiniMax (640 answer files: write 177, check 176, verify 176, and so on).
- The earlier runs are Opus or Sonnet.

**Basis × card state × images**, from `q1.sql` over 4,900 shown sites. Image criterion: non-excluded, short side ≥900, aspect ≤2.0 (the `shorts_select` rules). My image-pool counts differ slightly from the audit's 2,317.

| basis | wb-v2 card | old card | no card |
| --- | --- | --- | --- |
| P4 (W/S) | 2,717 | 63 | 2 |
| WC | 111 | 850 | 8 |
| lane L / none | 0 | 996 | 125 |
| no description | 0 | 0 | 28 |

- **Valid basis = P4 + WC = 3,751.** Of these, 2,828 have a wb-v2 card, 913 an old March card, 10 no card.
- **Pool (≥6 good images) among valid basis: 1,910** (P4 1,505, WC 405).
  - Rich (≥300 chars) and defect-free: 1,722.
  - Thin: 105.
  - Defect: 83.
- **Non-pool valid basis: 1,841**, of which 54 + 4 defect and 270 thin.
- **Thin valid basis overall: 375** (<300 raw chars, markers included; the audit's 431 uses another count).
- **Tier ≥4 wave 1 candidates** (valid, pool, rich, defect-free): 186 (135 already wb, 51 old). The audit says 221; mine excludes defect sites.
- **Lane L:** 1,121 sites. 477 of them are in the image pool. They wait for WC (another workstream).
- **Defects:** the 8 `DESCRIPTION_DEFECTS.jsonl` files give **141 shown sites** with a still-current `desc_sha256` (reproduced exactly).
- **Open-question wording:** a strict regex (mystery, unknown, debated, disputed, unclear, "purpose is"…) matches only 90 of the 1,910 pool texts (4.7 %). So about 1,820 pool sites need a new D4 hook sentence.

**Calibration material on disk** (`teaser/runs/wb-*/STAGE-*.jsonl`, Opus and Sonnet-era runs):
- 2,639 checker PASS records and 129 FAIL records (118 `check`, 8 `check-v`, 3 later rounds).
- 136 cards verified CONTRADICTED, with 174 contradicted claims, 154 of them proven by a machine-found quote.
- 2,462 VERIFIED cards and 201 VERIFIED at `verify2`.
- 170 defect lines in the main checkout plus the gap run's 9 = 179.

**Disk:** 98 MB of cached pages per 450 sites (about 0.22 MB per site). Cards for 3,751 sites need about 0.8 GB. Enrichment adds about 0.5 GB. C: has about 20 GB free, so there is no large download.

## 3. Steps, in order

### 3.0 Shared prerequisites (code; worktree; tests first)

1. **Haiku stamp and Claude-only recording.** In `opus_handoff.py` add `HAIKU_MODEL` and `ANSWER_MODELS["claude-haiku-5-5"]`. Add `ANSWER_FAMILIES["claude-haiku-5-5"]="haiku"`. Add a `NEW_ANSWER_MODELS` subset (the three Claude ids) so `answer --model` and the brief's `MODEL_IDS` refuse MiniMax for new answers. Legacy MiniMax stamps stay readable by `validate`/`read_answer`.
   - Derived consumers: `phase3/model_stage.ANSWERING_MODELS`, `scope_review` families.
   - `phase3/mutation_sweep.py` embeds exact source lines of these constants (about lines 15996, 16433-16561). Edit its needles together with the source.
2. **Stamps set by the orchestrator, not self-declared.** The model census of 2026-10-01 found self-declared stamps wrong. The brief gets the role's model id baked in per stage, and `import` refuses an answer whose stamp is not `ROLE_MODELS[stage]`.
   - `ROLE_MODELS` is a new `teaser/roles.py`, sealed with the calibration thresholds. An escalation is recorded in `RUN.json["roles"]`.
   - Gate before `outcomes`: run `model_census.py` over the run's handoffs and require 0 mismatches.
3. **AI disclosure strings.** `model4.AI_SYSTEM` names MiniMax and `WebProvenance.__post_init__` requires equality with it. Any new WN/WC/enrichment description write would claim MiniMax.
   - Add Claude-only strings to `AI_SYSTEMS`: Opus+Sonnet (the existing `AI_SYSTEM_CLAUDE` text is reusable), and a Haiku variant only if Haiku writes anything.
   - `teaser/run.outcome_rows(ai_system=M.AI_SYSTEM)` default must go. Derive `ai_system` from the `models` set; `mechanical/teaser.new_raw_data` validates the derivation.
4. **Card file must stop being a hazard (D25 item, do first).** Deploy a change that removes the overwrite from `api/main.py:139` / `import_card_descriptions` (fill-only for NULL rows, or no import).
   - `card_json.py --regenerate` stays as an export only.
   - Update `PROJECT_LESSONS`/CARD_DESCRIPTIONS 5.5-5.6 and the sweep needles.
   - After this the sittings need no push lock and no `StartedAt` choreography. The only pushes left are the static-export refreshes.
   - Until it is live, use the old discipline (§3.8).
5. **Supersede in writing before any run.**
   - CARD_DESCRIPTIONS §1.3/1.4 (name required, `MAX_QUESTIONS=1`) and §1.5.
   - AUDIT_LOG note of 2026-10-07 ("cards stay plain factual prose").
   - TEASER_NOTE comment.
   - Write §1 of the contract anew.

### 3.1 Contract `shorts-v1` (D1, D2)

New `scripts/remediation/teaser/shorts_v1.py` with `problems_shorts(card, site, anchors, reserve, fit)`. Imports the v1 helpers, never edits them. Rules:

| Rule | Check |
| --- | --- |
| C3 | ≤2 numerals, ≤8 digits, ≤4 digits in s1; numerals still grounded exactly |
| C4 | 160-190 chars, layout, forbidden-character rules from v1 |
| C5 | Exactly 2 sentences; s1 is 40-85 chars |
| C6 | Narration estimate `6.04 + 0.0334·chars + 0.318·digits ≤ 14.0 s` |
| C7 | No name form, `unified_site_names` alias, distinctive name token (≥3 letters, not a generic type word) or country. 13 generic-word names exempt |
| C8 | No administrative word in s1 |
| C9 | Opener rules (location preposition, "This/It…", "A/An/The + site noun") |
| C10 | No `? ! ... …`, "you/your", or CTA words (link, subscribe, guess…); `MAX_QUESTIONS=0` |
| C11 | Mystery/superlative stems only where the description has them |
| C12 | Present-state words flagged for the checker |
| C13 | Caption widths: common word ≤696 px, proper noun from the basis ≤1000 px (`caption_px`) |
| C14 | Anchors verbatim in the card; anchor 1 ends in the last 25 chars of s1; anchor 2 starts at char ≥95; anchor starts ≥28 apart. Only for Shorts-eligible sites (≥6 images and ≥300 chars) |
| C15 | Reserve: a description sentence id not used by the card, or `reveal`; null means `shorts_ready=false` |
| C16 | Diversity at import (3-word opening ≤1 % of cards, no repeated 5-word opening) |
| C20 | Provenance v3 |

- `card_fit(site.name, card)` stays, because the name is drawn at the reveal. Under D1, `name-undrawable` becomes moot for card text (2 sites), but the reveal name must still be drawable (ties to D23's spoken name).
- Mutation sweep: one case per rule in `mechanical/mutation_sweep.py` (a `teaser-shorts:` family, fired and not skipped).
- Tests: new `tests/remediation/test_teaser_shorts.py`. Pin the 11 samples from `pilot_sites.json` and `teaser_design_digest.md`. Pin their descriptions as fixtures, because live texts will be repaired.

### 3.2 Prompts, answers, stages, roles (D6)

New `prompts_shorts.py` and `answers_shorts.py`, dispatched by `RUN.json["contract"]` in `run.prompt_for`, `parse_answer`, `import_stage` and `outcome_rows`.

| Stage | Role | Model / effort | Answer |
| --- | --- | --- | --- |
| `write` | writer | Opus 5.5 high | `{variants:[3×{card,basis,anchors,reserve,hook_type}]}`, or `{card:null,thin:true,reason}` (C19). All 3 must pass `check-answer` |
| `rate` (new) | hook rater | Opus medium | `{ratings:[{variant,first5,hook:1-5}], best}`; sees only variants plus name and country (for the loop test). Floor: best ≥3, else a rewrite round |
| `check` | fact checker | Sonnet high | v1 fields plus `name_leak, hook_ok, s1_no_place, payoff_ok, this_site, generic_ok, loop_ok, tone_ok, anchors_ok`. PASS needs all true |
| `rewrite1`, `rate1`, `check1`, `rewrite2`, `rate2`, `check2` | as above | as above | rewrite writes 3 variants |
| `verify` | web verifier | Sonnet high | Unchanged mechanics: `claims_floor`, machine quote check, `prove_claims`. New `judge_prompt_shorts`: the "central claim" is the card's identity-bearing claim, since a nameless card names no place |
| `rewrite-v` | writer | Opus high | single card |
| `check-v`, `verify2` | Sonnet high | | |
| adversarial re-check | Opus high | | D10 only (§3.7) |

Other details:
- Every check batch carries one seeded-defect canary, excluded from outcomes. A batch whose checker passes the canary is void and asked again.
- The brief tells the agent the fixed stamp (`brief()` and `MODEL_IDS`). Writers, raters, checkers and verifiers keep the independence rule: `answered_by` is per batch, and agents are fresh.
- `import_stage` must store each answer's `model` stamp in the STAGE records (it does not today). Provenance v3 reads `models` from there.
- Verify batches: at most 3 parallel agents, because Wikimedia throttles this office IP at 4+. A 403 or 429 is never a finding; `curl` it first.
- `earlier_sites()` is keyed by `desc_sha` only. A shorts-v1 run that excludes a v1 run would list every v1-asked site `asked-before`. Key by (sha, contract) and never pass v1 runs to `--exclude-run`.

### 3.3 Provenance v3, classify, keep-on-fail (D5)

- `pipeline/utils/card_provenance.py`: `VERSION` becomes a per-version key set. `validate` accepts v2 (2,830 live) and v3.
  - v3 adds `contract:"shorts-v1"`, `models:{write,rate,check,verify}` (answer stamps), `hook:{type,rating,variant}`, `anchors`, `reserve`, `shorts_ready`.
  - `ai_system` must equal the string derived from `models`.
  - `shorts_pin` returns a pin only for v3 with `shorts_ready=true` and a fresh description. `card_ai` is unchanged, so v2 cards remain "generated". Update `api/services/description_provenance.card_ai`, `sites.py` and `sites_html.py` tests (`test_ai_act_marking`, `test_sites_html_ssr`).
- `teaser/run.classify`: CURRENT only for v3 with a matching `contract`. This makes the 2,830 v2 cards candidates again, and old-March sites with a valid basis candidates as before.
- **D5 (leave old March cards):** a site that fails or is declined must not lose its card. Add outcome `status:"kept"` (reasons `thin-declined`, `failed-after-two-rewrites`, `…-after-verify`). `mechanical/teaser.classify` skips it as `kept`, with no `card-clear-*` row. The v1 clear semantics stay for v1 runs.
- **Name re-check at plan time:** D13/D23 can add aliases or change names after a card was written. `classify` re-runs C7 against the live name and aliases and refuses `name-changed`.
- `shorts_export.assemble_site` adds `card_models`. `shorts_render` builds the note from `ai_system` (`teaser_note(ai_system)`). This is the only Shorts-side change the card lane needs; no render or upload. Update `tests/pipeline/video/test_shorts.py:291-304`, which pins the constant.
- Keep run stamps `wb-teaser-prov-sNNN` / `wb-teaser-card-sNNN` and continue at step 35. `PAGE_COLUMN_STAMPS` (lastmod/IndexNow) then keeps working unchanged. A new stamp family would need a change in `public_sites.py`.

### 3.4 Calibration (O18, sealed before the first answer)

- New `teaser/calibrate.py`, following `gallery_audit/calibrate.py`: `seal` (writes THRESHOLDS.json, logs its sha256, refuses if any verdict exists), `jobs` (fixed sample), `export` (calibration handoffs with the v1 or shorts prompts as appropriate), `evaluate` (also reuses `mcode_driver.compare_answers` for the ≥90 % unit agreement).
- A role that fails moves up one tier and is re-run: Sonnet to Opus; Haiku to Sonnet.

| Role | Cases | Pass threshold |
| --- | --- | --- |
| Checker (Sonnet high) | 45 recorded cards from 3 recorded batches (30 PASS-recorded, 15 FAIL-recorded) | ≥90 % claim and verdict agreement, 0 PASS with an unsupported claim |
| | 30 FAIL records with reasons | ≥27 of 30 FAIL again |
| | 30 seeded-defect shorts-v1 cards (one defect each: removed hedge, invented superlative, "unknown" implication, wrong period, name token) | ≥27 of 30 caught |
| | 30 good cards | ≥27 pass |
| Verifier (Sonnet high) | 20 cards with recorded proven CONTRADICTED claims (the 9 of the gap run included) | ≥18 caught |
| | 20 VERIFIED cards | ≤2 falsely CONTRADICTED; ≥90 % per-claim agreement; 0 false sources (machine quote check) |
| Hook rater (Opus medium) | 24 hooks: the 11 sample openers vs 13 live "On/In/At…" openers | 100 % of the strong-vs-weak pairs ordered right; ±1 of the xhigh reference on ≥80 % |
| Writer (Opus high) | 40-site pilot | ≥80 % mechanically clean at first answer |
| Adversarial (Opus high) | 25 recorded contradictions + 25 clean cards | ≥90 % |

Writer and rater are already at the top of their tier or cheap enough to defend; the pilot checks the writer. The Haiku image prefilter is the image workstream's. Seal thresholds in `SEAL.jsonl` before any answer exists.

### 3.5 Enrichment (D3 thin, D4 hook) - the long pole

- **Population:**
  - Hook sentence for pool sites: valid basis, pool, no strict open-question wording = about 1,820.
  - D3 for thin valid-basis sites: 375. Of these, 105 are pool sites; 270 are non-pool and get D3 only.
  - The 141 defect sites go first through WC defect repair (another workstream), then enrichment if needed.
- **Mechanics:** a new `wn-extend` kind on the WC/WN machinery. It reuses the `prompts_sonnet` write round (5 sites per agent), the import that fetches pages and checks every quote, `verify`, `verify2`, the 20-site judge pilot, and `write_gate4 --group WC`.
  - Hook mode appends 1 sentence (2-4 for thin sites) with a verbatim quote from a reputable page.
  - Agents are Sonnet high (D6 period/field research role).
- **Hard design point:** appending sentences breaks the Phase-4 invariant "one published sentence per sentence" and the `desc_sha256` equality. `basis_of` needs `_description_check.desc_sha256 == sha(description)` (so basis becomes WC) or the lane provenance.
  - Keep the CC BY-SA attribution for the Wikipedia sentences: do not turn a W/S text into lane N.
  - Extend `model4.Provenance` with an `appended` list (sentence index, citation n, source id), relax `write4._phase4_problems` and `wc4._phase4_provenance_problems`, and check `description_disclosure`.
  - This needs the same owner as the description workstream. Treat it as a shared design item.
- **Effect on cards:** every enriched site's `desc_sha256` changes, so a card written earlier goes stale. Hence the order in §3.6.

### 3.6 Population, order, pilot (D9)

Run waves as separate `select --sites FILE` runs (each wave a site list in fame order; `rarity_score` is the proxy until the D27 pageview list exists).

1. **Pilot, 40 sites, fixed seed** (the 11 `pilot_sites.json` sites plus 29 drawn: 15 pool rich, 6 WC, 3 English hill forts, 4 thin, 1 long name). To avoid wasted writes, draw them from sites that are not scheduled for D4 or defect repair, or keep the outcomes as evidence only. Gate:
   - 0 contradicted claims from verifier or judge, and ≤5 % unproven claims.
   - ≥80 % of first answers mechanically clean.
   - ≥70 % checker PASS at attempt 1.
   - 100 % of accepted cards pass shorts-v1 code.
   - Fresh Opus xhigh pilot judge (`judge-export`/`judge-import`), plus a shorts-side local check that sentence 1 ends by 7 s, **without any render or upload** (D-session order: no Shorts production). Replace the digest's "6 local renders" with a timing estimate from C6 plus `shorts_tts` timing only if that does not render video; flag to the orchestrator.
2. **Wave A, non-pool valid basis, rich, defect-free:** about 1,841 − 270 − 58 = 1,513. Card now; no enrichment dependency.
3. **Wave B, pool tier ≥4:** 186 plus whatever D4 completes first; card after their hook sentence is written.
4. **Wave C, remaining pool by fame** after D4: about 1,700.
5. **Thin sites** after D3, then the 141 defect sites after repair.
6. **Lane-L sites** once WC or WN gives a basis: first the 477 pool sites, then the rest (tier ≥4 first).
7. **28 empty sites** only after WN again produces a description.

Steps of ≤100 sites: about 38 steps for the 3,751, plus re-cards after enrichment.

### 3.7 D10, the 167 MiniMax cards

Recheck now; do not wait for wave B. They are live and public, with no WB calibration entry.
- Seed a run from the live cards (new `run.py seed-live`: writes `STAGE-write` records from the live card plus the provenance claims).
- Chain: `check` (Sonnet high), `verify` (Sonnet high), then an Opus high adversarial pass on all 167. About 167 + 167 + 167 answers, about 34 agents for the Opus pass at 5 per batch.
- A failure is cleared through the journal (`card-clear-recheck-<reason>`); the replacement comes with shorts-v1. A pass stands until replaced. Roll back to the March card never, because that card is worse (unverified).

### 3.8 Write path and sitting

- Per step N, `wb_step.sh RUN N` (plan, prov/card `--emit --rehearse --probe-guards --apply --verify`, `--rehearse-rollback`, `accept`). Acceptance only with `RESULT: 0 deviation(s)`.
- Once per sitting: `ssh ancientnerds "cd /var/www/ancientnerds/scripts/remediation && DO_DRILL=1 ./00_backup_and_drill.sh"`, and record `StartedAt` of both API containers.
- Until §3.0 item 4 is live:
  - Create `C:\PythonProjects\AncientMap\.git\main-push.lock` before the first apply and keep it until the card-file push is deployed. Every other push takes it too.
  - `mechanical/teaser.py card-file --steps A-B`, `card_json.py --check`, commit the file plus the trail (`git add -f` the `mechanical_teaser` paths), push at once. Group 5-10 steps per sitting, so there are only 5-7 deploys.
  - After the deploy: both `StartedAt` moved, 0 `Card description overwritten` lines, `commit` field equals HEAD, `accept` again for each step.
  - A red CI inside the sitting means undo the sitting (§5.5, §5.6 of the contract).
- After item 4, a sitting needs no push. Refresh the static export (`index.json` `cd`) once per wave.
- Never `git revert` the sitting's commit.

## 4. Dependencies on other workstreams

- **Descriptions:** WC defect repair (141 sites, 179 lines) and finishing WC (1,121 lane-L sites) before their cards. Every description rewrite stales the card.
- **D13 re-target (103 sites), D14 merges, D21 disputed sites, D23 names:** change description, name or aliases. Cards come after, and C7 is re-checked at plan time.
- **Images:** D15/D17/D13 change pool membership. Anchors are advisory for the Shorts selector (D16 vision check is at render time), so image changes do not stale cards.
- **Shorts side (not now):** spoken-name field, tier-3 inclusion in the selector, S13 v3 pin (done in §3.3), pinned-comment first line without the name.
- **D25:** card file and static export automation; card_stats recompute is separate.
- **D11:** AI notice stays off the site. `card_ai` is still computed, and the Shorts description note stays.
- **Shared constants:** `opus_handoff`, `model4.AI_SYSTEMS` (§3.0 items 1 and 3).

## 5. Estimated model answers

For N = 3,751 (assumed first-attempt check pass 75 %, about 30 % of cards need a rewrite round, 8-10 % need a verify rewrite; rates from the 2,639/129 and 136/2,598 records):
- `write` ≈ 4,900 (Opus high), `rate` ≈ 4,900 (Opus medium; 25 per agent ≈ 200 agents).
- `check` ≈ 4,900 + `check-v` ≈ 375 (Sonnet high).
- `verify` 3,751 + `verify2` ≈ 375 (Sonnet high, web; 5 per agent ≈ 825 agents).
- `rewrite-v` ≈ 375 (Opus high).
- **Total ≈ 19,500 answers, about 1,700 agents.** About 10,500 Opus and 9,000 Sonnet.
- Wall clock is dominated by the verify stage at width ≤3: roughly 40-70 h.
- Pilot (40 sites): about 215 answers plus 8 judge agents.
- Calibration: about 400 answers.
- D10 recheck: about 500 answers.
- Enrichment (about 2,100 sites): about 2,100 write + 2,100 verify + 300 verify2 = about 4,500 answers (about 900 agents), plus a 20-site judge pilot.
- Claude quota is unmeasured. Read the weekly usage before and after the pilot to get percent per 100 cards.

## 6. Risks and traps

1. Editing the v1 prompt/contract/answers files stales every earlier export and the calibration sources (§0.1).
2. `AI_SYSTEM`/`WebProvenance` equality names MiniMax; new stamps must be derived (§3.0).
3. Self-declared stamps were wrong before (`model_census`); census gate in §3.0.
4. Boot import of the card file silently re-imports the old cards after any restart or foreign deploy, so the push lock matters until item 4 ships. Never push the file before the DB write.
5. Each push rebuilds the frontend (ffmpeg-static 503 risk). Batch deploys.
6. Wikimedia throttle at 4+ parallel fetchers; false `UNVERIFIABLE` from 403/429 (nine such findings in the gap run).
7. `earlier_sites` keyed by sha only (§3.2).
8. Appending sentences to Phase-4 texts is a provenance problem, not just a lane (§3.5).
9. The verifier's "central claim" has to be redefined for nameless cards; otherwise most cards come out UNPROVEN.
10. Hook material is scarce (4.7 % already carry an open question), so the D4 write step is mandatory for the mysterious tone to be sourced.
11. A MiniMax-era check must not be reused: the gap-run records are not calibration data for Claude roles.
12. The 28 empty and the thin declined sites stay without a Short. The 141 defect sites should not be carded before repair.
13. `pilot_sites.json` samples and `teaser_cases.py` pin live description text; pin fixtures, not live reads.
14. `mcode_driver.py` has no WB lane and still stamps MiniMax. Do not extend it for this work.