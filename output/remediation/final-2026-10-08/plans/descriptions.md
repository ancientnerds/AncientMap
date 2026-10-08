# Workstream "descriptions": D3, D4, D21, D22, D25 (finish WC, repair 141 defects)

Nothing was written to production or to tracked files. The `C:/tmp/wf_map_descriptions/` scratch (queries `q1`–`q13`, scripts in `s/`, data in `data/`) is the only thing I created. It includes one copy of the mass-05 run, built in `C:/tmp` to measure outcomes.

## 1. Existing tools

Code is in `.worktrees/db-final` (origin/main plus the decisions record). Run state is gitignored, mostly in the main checkout `output/remediation/`, and the WN run is in `.claude/worktrees/db-finish/`.

| Need | Tool and runbook |
|---|---|
| WC check, verify, build, judge | `scripts/remediation/wc/cli.py` with `phase4/wc4.py`, `wc/answers.py`, `wc/prompts.py`. Runbook: SENTENCE_CHECK.md §4 (plain WC), §11.3 (site-list run with `--defects`), §12.6 (WN). |
| Sonnet briefs and questions | `wc/prompts_sonnet.py` (`CHECK_QUESTION_LISTED`, `WRITE_QUESTION`, `VERIFY_QUESTION_WN`, `JUDGE_QUESTION_WN`). The briefs hard-code `--model claude-sonnet-5-5` and the agent names `sonnet-…`/`opus-…`. |
| Write, accept, undo | `output/remediation/tools/write_gate4.py --group WC --wc-plan …` (dry, `--rehearse`, `--apply --step 100`, `--accept`). `verify_writes4.py --lane p4wc --allow-stamp wb-teaser-prov-%`. `phase4/revert4.py --stamp-like 'phase4wc:…'`. |
| Pilot gate | `cli.pilot_approval`. One pilot per kind (WC or WN). The plain WC pilot must come first in the chain. A list run can never be the pilot. |
| State machine | `scripts/remediation/mcode_driver.py` (`wc_next_step`, `copy_for_calibration`, `register_calibration_run`, `compare_answers`). Its `AGREEMENT_FLOOR` is 0.9. The exec backend is MiniMax-only and the paths are hard-coded (`REPO`, `WORKTREE`). |
| Stamps | `opus_handoff.ANSWER_MODELS` has only opus-5-5, sonnet-5-5 and MiniMax. `model4.AI_SYSTEM` is the combined Claude+MiniMax string; `AI_SYSTEMS` accepts three strings. |
| Defects | `cli.py defect-sites` takes every `DESCRIPTION_DEFECTS.jsonl`; `export --sites F --defects F.report.json`. |

## 2. Measured state

Production was read read-only on 2026-10-08.

**Shown curated texts by basis**

| Basis | Sites | Under 300 chars | In Shorts pool (≥6 usable images) | Pool and under 300 |
|---|---|---|---|---|
| P4 W/S | 2,782 | 71 | 1,505 | 13 |
| WN (lane N) | 17 | 2 | 6 | 1 |
| WC-checked | 952 | 303 | 399 | 92 |
| L only, unverified | 1,114 | 79 | 470 | 34 |
| No provenance | 7 | 4 | 0 | 0 |
| No description | 28 | – | 7 | – |

- Total under 300 chars is 459, of which 140 are in the pool.
- The pool with a description is about 2,380 sites. This is my own definition of "usable" (`NOT is_excluded`, short side ≥900, aspect ≤2.0), so it differs slightly from the audit's 2,317.
- 4,518 of the 4,900 shown sites have an enwiki title.

**WC runs** (all in the main checkout `wc_runner/runs/`, handoffs in `handoff/wc-<run>-…`)

| Run | Sites | State | Who answered |
|---|---|---|---|
| `mass-…-01`, `-02`, `pilot-…-27c` | – | Built and written (steps 1–12, 0 deviations) | – |
| `mass-…-03` | 500 | Check imported. Verify round 1 exported and answered (492/492), **not imported**, no verify2. | **MiniMax, all 492** |
| `mass-…-04` | 500 | Check imported. Verify r1 imported (480: 371 Sonnet, **109 MiniMax**). Verify2 exported (83), 60 answered, **23 open**, not imported. | The 60 are MiniMax |
| `mass-…-05` | 148 | Everything imported (verify2 28 sites, all **MiniMax**). **Ready to build.** | – |
| `defects-2026-10-02` | 136 | 45 answered (Sonnet 5.5), **91 held**. | Sonnet |

- The 1,148 sites of runs 03/04/05 are 1,132 unchanged and 16 rewritten by P4 since the read. The gate refuses those 16 per site as `written-by-p4`.
- Of the 1,148, 1,019 carry a March card, 125 have no card, none carries a WB card, and 85 are already under 300 chars.
- Check-stage answers of 03/04/05 are all Opus or Sonnet. The Sonnet check answers of mass-03 and mass-04 round 2 are stamped `sonnet`.
- A build of mass-05 in a `C:/tmp` copy gave 148 sites, 14 cleared (9.5 %), 134 texts kept, 60 of them under 300 chars (45 %), 25 under 150. Runs 01 and 02 gave 35 % and 37 % under 300 and 5–6 % cleared.
- Forecast for the 1,132: about 60–70 cleared and 400–480 under 300 chars. Final shown thin texts: about 800 (700–900).
- The 17 WN texts (run `wn-2026-10-06`, pilot of 20 of 26) were written, verified and judged **entirely by MiniMax**. The three pilot-empty sites are Kyaneai Tarihi Sarnıç, Templo del Sol and Te Pito Kura.
- 63 verify2 answers of the **already written** mass-02 are MiniMax. 57 of those sites still hold their text, 5 are now cleared and 1 has no check record.
- The MiniMax stamps are partly mislabelled: answers with model MiniMax carry `answered_by` `opus-wc-verify-…`.
- **Defects:**
  - 179 lines across 8 files (7 in main `teaser/runs/`, 9 lines in `.claude/worktrees/db-finish/.../wb-cardgap-2026-10-07/`) cover **141 sites**.
  - `defects-2026-10-02` holds 136 of them; 5 sites (Wamanmarka, Tanqa Tanqa, Lakhan-Jo-Daro, Wain's Hill, Cave of Niaux) are new and WC-basis.
  - Every line's `desc_sha256` equals the live text.
  - 136 of the 141 sites carry a WB card, so all 136 go stale on repair.
- **28 empty sites** (listed by id and name in the q4 output):
  - 12 have an enwiki title, e.g. Trajan's Bridge, Valley of the Thracian Rulers, Tlalpan, Naveta Biniac, Ligures Baebiani, Saoba Stone Pillars.
  - Çatalat Viranşehir points at the modern town.
  - Te Pito Kura probably duplicates Te Pito O Te Henua (4ccebe8e), which belongs to D14.
- **Disputed sites:**
  - Description text and enwiki category signals found Pantelleria Vecchia Bank (daa1ea4b, L-only, mass-04), Te Pito O Te Henua (already shows both views), America's Stonehenge, Gunung Padang, Dighton Rock, Sakdrisi, Kuhikugu, Vottovaara, Sacsayhuamán, Carn Menyn, Beglik Tash.
  - **Baltic Sea Anomaly is retired** (E3 natural formation). So are the 3 Bosnian pyramids, Yonaguni and Richat. D21 as worded conflicts with D20 here (see section 6).
- **Open-question wording:** explicit wording appears in 2–5 % of texts (L 2.5 %, W 5.0 %). In a sample of 80 W/S pool sites, 24 (30 %) had a regex-level hedge sentence in the live Wikipedia article that is not in the description. That is an upper bound; many are false positives.

## 3. Steps per decision

**Order:** (A) finish WC → (B) MiniMax re-check list and defect repair → (C) WN → (D) disputes → (E) enrichment. Card writes come after each site's last description write.

**Cross-cutting code first** (owned by the infra workstream, listed here as my dependency):
- `opus_handoff.py`: add `claude-haiku-5-5` and a per-role model table with an import-time check.
- `model4.py`: a Claude-only `AI_SYSTEM`. Keep the three old strings in `AI_SYSTEMS`, and make `WebProvenance` accept `in AI_SYSTEMS` (it uses `!=` today, which would break the 17 WN rows).
- Parametrise `--model` and the `answered_by` prefix in `wc/prompts.py`, `wc/prompts_sonnet.py` and `wc/cli.py:judge_brief` (byte pins in `tests/remediation/test_wc*.py`, `test_wn.py` must be re-pinned).
- A `calibrate` command with a Claude backend that reuses `copy_for_calibration`, `register_calibration_run` and `compare_answers`.
- Note that `phase4/*.py` is mass4-hashed, so edit it only where no mass4 run executes (`wip/p4-pilot` is still unmerged).
- Run the code from a tree whose `output/remediation/` holds the apply root `logs/_write_apply_p4wc/` and the runs. Use junctions for `wc_runner`, `handoff` and `logs` into the db-final worktree, or fast-forward the main checkout. Copy `wn-2026-10-06/{POPULATION.json,judge/RESULT.json,WC4.jsonl}` into main `runs/`, because the gate chain must name the WN pilot.

### D25a: finish WC on the 1,132 sites
1. **Calibrate** (seal before running; if a role fails it moves up one tier):
   - Sonnet high check: 30 sites from pilots 27/27b/27c, 6 batches, judged cases (Cloghanmore WRONG, Nyons incoherent, "carved" WRONG). Pass: ≥90 % verdict agreement with KEEP and KEEP_TRIMMED merged, all 3 known errors not kept, 0 quotes not found by machine.
   - Sonnet high verify: the 15 questions of `calibration/wc-verify-02` (69 units). Pass: ≥95 % and the known errors caught.
   - Opus xhigh judge: the same pilot sites. Pass: the 3 known findings recalled and ≤1 extra WRONG.
2. **Move the MiniMax answers aside** (local files only):
   - mass-03: move 492 answers out of `handoff/wc-mass-2026-09-27-03-verify/*/verify/`.
   - mass-04: move the 109 MiniMax r1 answers, rename `verify/round-1/VERIFIED.jsonl` to `.void`, delete `round-2/ROUND.json`, archive `…-verify2`.
   - mass-05: do the same for round 2 (28).
   - Implement this as a tested `verify-void` helper, not hand edits.
3. Per run: `cli.py brief|verify-brief` → one Sonnet agent per batch → `opus_handoff.py validate` → `verify-import` → `verify-export --handoff …-verify2` if `to_verify2 > 0` → answer → import → `build --first-batch 4400` (03), 4500 (04), 4600 (05). `--first-batch` must be above 4325.
4. **Sampled Opus xhigh judge** of about 55 built texts per chunk. Needs a new `judge-export --sample N --seed S`, because today's judge runs on every built site.
5. **Write:** `PLANS` = pilot-27c, mass-01, mass-02, WN pilot, then the new chunks in run order. Dry, `--rehearse`, `--apply --step 100`, acceptance, `--accept`, finally `--complete`. Run the acceptance from the tree that has the new `AI_SYSTEMS` (otherwise 209 false deviations).
6. **Afterwards:** the 60–70 cleared sites go to WN (section C). The 16 P4-rewritten sites drop out by themselves.

### D10 for descriptions: Claude re-check of MiniMax-touched texts
- A `wc-list` run over about 57 mass-02 sites plus the 17 WN texts (about 75), with Sonnet check, Sonnet verify and Opus judge. The 17 WN texts are `web`-marked and are asked again as lane N.
- Not listed in D10 itself; I recommend it so the Claude-only disclosure stays true. Add the 5 mass-02 sites that MiniMax cleared to the WN population.

### D25b: repair the 141 defects
1. Copy the cardgap `DESCRIPTION_DEFECTS.jsonl` into main `teaser/runs/wb-cardgap-2026-10-07/`. Rebuild the list with `defect-sites` over all 8 files from a fresh `read`.
2. Answer the 91 held questions of `defects-2026-10-02` with Sonnet. They keep their frozen prompts and the defect claims embedded in them. Run the 5 new sites as `defects-2026-10-08 --after defects-2026-10-02`.
3. Verify and build with `--first-batch 4700`. Phase-4 texts are only kept or dropped, with the provenance filtered to the kept sentences. A text whose check keeps everything is `defect-kept` and not written.
4. For each `defect-kept` site (`SUMMARY.json`), an Opus-high adversarial second check with the same defect text. Either the sentence is dropped, or the refutation is recorded in AUDIT_LOG and the defect line is closed. This replaces the owner list (D8).
5. Parked content question: Tebessa 304 vs 305 gets a sourced decision in this check.
- A repair can only drop. It does not add a corrected sentence. Run enrichment (E) afterwards.

### D22: WN for the 28 (and the WC clears)
1. Run it **after A**, over about 28 + 65 + 5 ≈ 100 sites, so one 20-site pilot suffices.
2. `export --wn --pilot 20 --seed S`: Sonnet high writes (add the enwiki title and QID to the site block), new Sonnet agents verify (verify2 where a drop changed the text), Opus xhigh judges. `J_THRESHOLDS` are unchanged: 0 WRONG, ≤5 % unsupported, 0 incoherent, ≥10 of 20 judged.
3. The new pilot is the second WN plan in the chain. The old MiniMax-judged pilot (RESULT passed) stays first, because its batch is in the apply root.
4. The rest runs as a chunk with `--after`. Sites that stay empty are final (no card, no Short).
5. Precondition: the live API already knows lane N (the gate checks `commit`). I expect it is live, since 17 WN texts are written.
6. WN sentences paraphrase (12-word run limit), so they are not CC BY-SA copies.

### D21: disputed sites
1. **Candidates, in code:** description-text regex, the enwiki categories (`Pseudoarchaeology`, `Archaeological controversies`, `…runestone hoaxes`, `Lost City of Z`, rock-formation categories), and site types such as "Magnetic anomaly". Expect 60–150.
2. **Calibrate** the dispute screen on 15 known positives (9 shown sites above plus the 6 retired E3 sites) and 60 random negatives. Pass: ≥90 % recall.
3. **Sonnet** researches each candidate with quotes (position A, position B, sources). **Opus high** adjudicates.
4. **Write**, through the two mechanisms already planned:
   - First a `wc-list` pass where the dispute is fed in as a reported claim (the `DEFECTS_HEAD` mechanism) so the sentence that asserts one side is dropped, e.g. Pantelleria states the 2015 reading as fact.
   - Then an enrichment append of two to three sentences naming both positions with quotes.
5. The card then asserts neither. The card contract only allows "debated" when the description says so.

### D3 and D4: enrichment, a new `wn-enrich` kind on WN machinery

**Populations**
- A = all shown texts under 300 chars. Today 459; about 800 after WC.
- B = the Shorts pool, about 2,380 sites, one sourced open question each.
- Do pool-and-thin first (140 now, about 300 after WC), then B in fame order (D27).
- Expect real hook yield of roughly 35–55 %, not 100 %. A site with no sourced open question gets none, and its card then uses a factual detail instead of a mystery claim.

**Question and answer shape**
- One Sonnet-high writer question per site. The site block, the existing sentences S1..Sn (context, not evidence) and the allowed classes (`fact` up to 3 for thin texts, `open_question` 0–1, `dispute_*` for D21).
- A new `answers.parse_enrich` with the same quote format and the 12-word rule. Reject duplicates of existing sentences, total added length >450 chars, and a hook >220 chars.
- `import` fetches every quoted page itself and checks every quote, as WN does. An independent Sonnet verifier sees the whole new text with only the new sentences marked for judgement, verify2 where a drop changed the text, drops only.
- An Opus-xhigh judge on the pilot of 20 at the WN thresholds, plus a new metric "hook invented" = 0.

**Reuse and new code**
- Reuse `cli.py` (new `KIND_ENRICH`, export and import, `outcome_of`, `_not_planned`), `wc4.py`, `write4.py`, the gate and `verify_writes4`.
- New `wc4.compose_append`. It keeps the old text and its `[n]`, numbers new pages from N+1 and appends citations.
- New `ENRICH_*` prompts.
- A new check-record block: extend `_description_check` or add `_description_enrichment` (add it to `WC_KEYS`). Its `desc_sha256` and `verified_sha256` must move to the new text, because the card basis reads `_description_check.desc_sha256`.
- `cli.pilot_approval`: add the new kind as its own pilot class.
- Mutation cases `ENRICH_MUTATIONS` in `phase3/mutation_sweep.py` (about 12): appended markers, numbering reuse, duplicate guard, provenance not rehashed, hash not updated, 12-word rule, hook count, pilot class bypass, invariant 6, role-model check, acceptance re-derivation. Add `tests/remediation/test_wn_enrich*.py` and a new SENTENCE_CHECK.md §14.

**Provenance** (the real design problem)
- L, WC-checked, N and unclaimed texts: rehash lane L or N provenance. No schema change.
- **W/S texts (about 1,500 pool sites):**
  - A Phase-4 `Provenance` can only list verbatim Wikipedia spans (`PublishedSentence`, V3). AI-written web sentences cannot be represented, and the disclosure shows nothing once the hash differs.
  - **Recommended:** a new lane `E` (`Provenance` v2 with an `added` list), `ai` = generated, attribution kept. Then add `"E"` to `ATTRIBUTION_LANES` in `api/services/description_provenance.py` and to `BASIS_LANES` and `OWNER_LANE` in `teaser/run.py`. Add tests in `tests/api/`, and a gate guard like the lane-N API-commit check; deploy before the first E write.
  - **Cheaper alternative:** for W/S only, pick more verbatim sentences from the pinned revision with no new provenance. The yield is at most about 20–30 % of sites.
  - Decide this before building.

**Write path:** group WC, stamp `phase4wc:p4wc-NNNN`, `--first-batch 4800+`, steps of ≤100 sites, rehearse, accept with 0 deviations, undo via `revert4 --stamp-like`.

**Calibration of the writer:** the 20 WN pilot sites run through the full chain, plus a leave-one-out on about 40 sites whose descriptions already carry a sourced open question, remove the sentence and measure recovery (seal ≥70 %). Pass: 0 WRONG, ≤5 % unsupported, ≥10 judged.

## 4. Dependencies and card staleness

- **Cards that go stale and must be re-carded:**
  - Defect repair makes the 136 WB cards of the 141 sites stale. The census figure of 179 is not what I measured.
  - Every enriched site with a WB card goes stale. WB's `select` finds these by the `desc_sha256` tie in `CP.stale`.
  - Dispute rewrites go stale.
- **No stale effect:**
  - The WC finish: the 1,148 sites hold March cards or none. They only become eligible.
  - WN texts: they have no cards.
- **Order rule:** the description wave must precede the shorts-v1 card for each site. The 11 pilot sites (`pilot_sites.json`) get enriched first. The static export (WF), Qdrant and IndexNow follow every description write.
- **Cross-workstream:**
  - Exclude from enrichment the 103 modern-town records (D13), the roughly 27 duplicate pairs (D14), anything D20 retires and Pantelleria while its coordinates are wrong. Te Pito Kura and Te Pito O Te Henua need the duplicate decision first.
  - The new `AI_SYSTEM`, `BASIS_LANES` and the `--allow-stamp` pattern for the new card lane come from the infra and card workstreams.
  - Any additional description-field writes must follow the WC `moved-since-check` rules.

## 5. Estimated model answers (questions answered; agent runs are about one fifth)

| Stage | Answers | Model |
|---|---|---|
| Calibrations (check, verify, judge, dispute, writer) | about 200 | Sonnet / Opus |
| WC finish: re-verify 03 (492), 04 (109 + about 83 verify2), 05 (28), verify2 for 03 (about 85), sampled judge (about 150) | about 950 | Sonnet / Opus xhigh |
| MiniMax re-check list | about 160 | Sonnet / Opus |
| Defects | about 270 (91 + 5 check, about 120 verify, about 20 verify2, about 30 adversarial) | Sonnet / Opus |
| WN | about 200 | Sonnet / Opus |
| Disputes | about 360 | Sonnet / Opus |
| Enrichment | about 5,250 (about 2,930 writes, about 1,300 verify, about 200 verify2, about 150 judge, pilots) | Sonnet / Opus |
| **Total** | **about 7,000–7,500** | – |

- Token estimate is about 100–150 M. It is derived from about 11k per site for a verify and an unmeasured 30k for a write; measure it in the pilot.
- Operators run as Haiku low and need no calibration beyond reproducing `wc_next_step` on the 6 real runs.
- Wall time is bounded by the Wikimedia limit (≤3 parallel local fetchers), roughly 4–6 days of continuous running. The enrichment hook wave is the long pole, so run it in fame order.

## 6. Risks and traps

- **Disk:** C: has about 22 GB free, and `handoff/` is 20 GB, `wc_runner/` 3.7 GB, `cache/` 0.6 GB. Per site, a check or write round costs about 1.4 MB handoff plus about 1.8 MB run pages. The enrichment wave of about 2,930 sites would add about 4–9 GB, so prune or archive old handoff pages before it.
- **Write-once rounds:** `import` and `verify-import` run once per round, and `verify-export` refuses an exported round. Voiding MiniMax answers therefore needs the careful helper above. Never hand-edit a recorded round.
- **Round independence is name-based.** The `answered_by` prefixes are wrong for MiniMax answers (`opus-wc-verify-…`). A Claude verifier must not reuse a checker's name.
- **Baltic Sea Anomaly:** D21 names it, but it is retired (E3 natural formation, as are the Bosnian pyramids, Yonaguni and Richat). I recommend D21 applies to shown sites and the retirement stands, unless the owner wants to un-retire them for Shorts (a scope-lane decision).
- **Briefs:** the briefs say "reputable pages" and refuse ancientnerds.com, AI aggregators and Wikipedia mirrors. Several hosts refuse the fetcher (historicengland, canmore, britishmuseum, smarthistory, megalithic.co.uk, cookie walls).
- **Fetching:** a 403 or 429 is never a finding. Always test with curl yourself.
- **Acceptance output:** PowerShell 5.1 `1>` writes UTF-16 and breaks `--accept`. Write the log as UTF-8 without BOM. Git Bash `>` is fine.
- **Chain:** the gate refuses an apply root holding a plan not named. Name every plan, the WC pilot first. A plan whose judge failed is never in the root. The WN pilot path lives in db-finish.
- **CLAUDE.md claims no description footnote, but the AI footnote is off by decision D11.** The CC BY-SA attribution line must stay for W/S/T and E.
- **Static export** is stale from 2026-10-06 for 499 descriptions, so run WF after each description step.