# Master plan: the final repair of the 5,004 curated sites and the shorts-teaser cards (2026-10-08)

Binding: `output/remediation/OWNER_DECISIONS_2026-10-08.md` (D1-D35). Basis: the read-only state
audit `STATE_AUDIT.md` and the six workstream maps in `plans/` (cards, descriptions, fields,
identity, images, infra), each measured against production on 2026-10-08. This file decides the
order and the open points the maps left to the orchestrator; the maps carry the commands.

**No Shorts production** ("die shorts videos aber noch nicht herstellen!"): no render, no upload,
no OAuth. Shorts-side code changes only where the card lane needs them (S13 pin of a v3 card, the AI
note from `_card_provenance.ai_system`, `spoken_name` read by `shorts_tts`).

## Orchestrator decisions (D8 autonomy; each recorded here before use)

| # | point the maps left open | decision |
| --- | --- | --- |
| X1 | Provenance of sentences appended to a W/S (Phase-4 Wikipedia) text by enrichment | New lane `E` (Provenance with an `added` list, CC BY-SA attribution kept, `ai` generated); deployed before the first E write. |
| X2 | D21 names the Baltic Sea Anomaly, which is retired (E3 natural formation) | D21 applies to shown sites; retirements stand. |
| X3 | Coastal guard edge cases | 2.5 km sea tolerance with an empty polygon query; Cyprus = Northern Cyprus + SBAs; Kosovo, Narona, Heracleion stay refused and listed; Flevum's country goes with its point through wd5. |
| X4 | D18 "author + licence URL" would refuse every public-domain file (no `license_url` on 5,285 PD rows) | `author` + `license_url` required only for attribution licences (CC BY*, CC BY-SA*, GFDL, OGL ...); PD/CC0 need neither; `author_url` never. Uploader-as-author only for self-licensed files. |
| X5 | Migration `0029_unified_sites_spoken_name.sql` (memory: ask before a migration) | D8 "komplett autonom" covers it; additive nullable column. |
| X6 | MiniMax-answered material in run dirs | Never ground truth; moved aside by a tested helper, re-answered by Claude (D10). |
| X7 | WF final measurement size | 100 sites, Opus xhigh, after the last write wave. |
| X8 | The 73 collective entities with unsourced points | Listed, not retired or merged (not covered by D13/D14/D19). |
| X9 | A MiniMax-written `period_start` that Claude cannot source (all 265 filled an empty cell) | Restored to the pre-MiniMax state: NULL start, label `Undated` (D10). |
| X10 | `phase4/assemble._finish` still stamps the Claude+MiniMax `AI_SYSTEM` on new Phase-4 W/S provenance | Fix before the first new W-lane write (D13 re-targets); no W write runs before it. |
| X11 | Where lanes run | The main checkout is the run tree (branch `run/2026-10-09-db-final`, fast-forwarded as code lands); code is built in worktrees `.worktrees/*`. |
| X12 | (2026-10-24) A paper hero when no uncropped picture of the paper qualifies | No crop: the D60 hero kind takes only a record the paper already carries; such a hero stays and is listed (flying-discs, ufos). |
| X13 | (2026-10-24) Sites of Islamic or Byzantine Europe dated 500-1500 (al-Andalus, Sicily: Talamanca, Huescar, Ponferrada, Castle of Cola, Villaggio Bizantino) | Medieval Europe under D58 ("only the medieval Old World of Europe, Byzantium and the Vikings is out"): they stay out; the scope-window lane treats them as outside the label window. |
| X15 | (2026-10-25) Lane WC's pilot judge (Opus xhigh, top tier) failed wc-pj-1/2 by calling a seeded WRONG sentence UNSUPPORTED and an incoherent text coherent; in the WC gate an UNSUPPORTED only counts toward a 5 % share | No release (its reason would be false) and no softer gate: sharpen the judge brief (WRONG vs UNSUPPORTED under the contradiction rule, an explicit coherence step) and recalibrate under new seals wc-pj-1o/2o - the D52 precedent. |
| X14 | (2026-10-24) The site_type alias map of the Phase-8 merge (decision null) | An alias merges into its canonical value only when it is the same category under another spelling or synonym of the vocabulary the frontend filters use; a distinct category is kept. Per-alias reasons in `final-2026-10-08/X14_SITE_TYPE_MAP.md`. |

## Throughput and cost (measured inputs, estimate)

- Model answers over all workstreams: about **35,000** (cards ~19,500; descriptions ~7,300;
  fields ~3,800; identity ~2,100; images ~800; calibration/WF ~2,000), in roughly **3,500-4,500
  agent runs**, mostly Opus 5.5 and Sonnet 5.5.
- Tokens: the read-only mapping agents used ~250k each; answering agents of 5 questions are
  estimated at 100-250k. Order of magnitude **0.4-0.9 billion tokens**. The Claude plan's usage limits
  will pause the runs; workflows resume from their run ids.
- Wall clock is bound by web verification at width <= 3 (Wikimedia throttles this IP at 4+):
  ~14,000 web-checked answers at ~11 min per 5-question batch -> **~7-9 days of continuous running**.
- Disk: the owner freed space (2026-10-08: ~90 GB free); parallel worktrees allowed.
- Wikipedia: a shared serial prefetch (`output/remediation/final-2026-10-08/wiki_cache/`, 4,767
  articles, 0 failures) replaces live Wikipedia fetches by agents; width is bound by RAM, not by
  Wikimedia (the owner offered Webshare proxies; not used - rotating IPs around Wikimedia's
  per-IP throttle would break its API etiquette).

## Order

**Phase 1 - Foundation (code; one branch; one deploy).** Sonnet high builds, Opus high reviews.
1. Roles registry (`scripts/remediation/roles.py`): role -> (model, effort, calibration set,
   sealed threshold); `claude-haiku-5-5` stamp; new answers Claude-only; `--role` refuses a
   model that differs from the registry; `calibrate_claude.py` (seal / prepare / compare / verdict).
2. Disclosure: a Claude-only `AI_SYSTEM` string added to `AI_SYSTEMS` (old strings stay valid),
   `WebProvenance` checks membership, new writes derive `ai_system` from the answering models.
3. DB authoritative for cards: the boot import of `card_descriptions.json` and the card-file
   machinery removed.
4. Static export: atomic writes, nightly scheduler, a locked CLI for after-wave runs, a freshness
   check; then one fresh export.
5. `sites_html`: a duplicate loser answers 301 to its survivor (not 410).
6. Migration 0029 `spoken_name`; `shorts_tts.spoken_name` reads it; `TEASER_NOTE` built from the
   card provenance.
7. Backups cross-copy routine (D24); archive the 16 old renders (local move, manifest).

**Phase 2 - Calibrations** (sealed before each role's first answer; failing role moves up a tier):
fact checker, web verifier, field researcher (+ BP set), adversarial Opus, identity verifier, dup
verdict, scope verdict, WC check/verify/judge, image prefilter (Haiku), image depicts (Sonnet),
hook rater. Each lane's own calibration runs right before that lane if its code is not yet built.

**Phase 3 - Independent repairs (parallel, web width <= 3 in total):**
- Fields `wd5`: one re-research round for the 1,254 rule periods (BP reader), the MiniMax field
  decisions (D10) and the 430 unsourced points; the 19-23 coastal writes; Opus adversarial pass;
  rollback of rejected MiniMax cells; then the `_period_provenance` marker lane; stale-id wave 5.
- Descriptions: finish WC (mass-03/04/05, MiniMax verify answers re-asked), the 141 defects,
  re-check of MiniMax-touched texts.
- Cards: the 167 MiniMax cards re-checked (D10).
- Images: the 47 other_site heroes (D15); credit rule + author backfill (D18) and the refused
  inserts re-seeded.

**Phase 4 - Identity:** duplicates (D14), modern-town re-targets (D13: funnel ~600 -> pilot ->
waves), names + spoken names (D23), scope window review (D20, after wd5), parents (D25).

**Phase 5 - Descriptions follow-ups:** WN (28 + WC clears + re-target needs), disputes (D21),
enrichment lane E: thin texts (D3) and one sourced open question per Shorts-pool site (D4), in fame
order.

**Phase 6 - Images D17:** the 952 (+ D15 clears) after D13/D14/D19: identity research, candidates
(incl. geosearch for sourced points), Haiku prefilter, Sonnet depicts, Opus hero re-check, INSERT
waves; the MiniMax candidate verdicts and the 192 inserted heroes re-judged.

**Phase 7 - Cards shorts-v1** (contract C1-C20 of `STATE_AUDIT`/design digest; new sibling modules,
v1 byte-frozen): pilot 40 -> wave A (non-pool, rich, defect-free, not in an identity funnel) as soon
as the contract and calibration pass -> pool sites after their enrichment -> thin after D3 -> WC/WN
sites after their basis -> re-targeted/merged sites last. A failed or declined site keeps its card
(D5). Provenance v3; steps of <= 100; journal stamps continue at `wb-teaser-*-s035`.

**Image waves (Phase 3/6) - after every accepted wave** re-run the SEO session's gallery thumbnails (separate root
`public/data/images/wiki-thumbs/`, idempotent, never touches the wiki tree; agreed 2026-10-09 with session ancientmap-78):
`ssh ancientnerds "docker exec ancient_nerds_api nice -n 19 python -m pipeline.wiki_thumbs"`.

**After the data repair (handed over by the SEO session, owner-approved):** the 38 high-demand in-scope sites without a
curated page (Colosseum, Carthage, Ephesus, Nineveh, Catalhoyuk, Mohenjo-daro, Nan Madol, ...; Chaco Canyon wrongly
out_of_scope because Wikidata P571=1980 is the park designation; Choquequirao and Comalcalco the same gap), each per
ENRICHMENT_AUDIT; inputs `output/seo-audit-2026-10-08/scratch/demand/agg_inscope_candidates.csv` and
`proposals_by_demand.csv` in the main checkout.

**Phase 8 - Close-out:** site_type merge, card_stats wave + the five dead columns, static export,
docs (CLAUDE.md, HANDOVER 0.0.0, CARD_DESCRIPTIONS, SENTENCE_CHECK, FIELDS_*, AUDIT_LOG,
HUMAN_ONLY), WF measurement (X7), the owner list of everything that stays empty or unsourced, the
final report.

## Progress log

- 2026-10-08: decisions recorded (c6c896e); state audit and six workstream maps done; this plan.
- 2026-10-08/09: Phase 1 built in parallel worktrees, reviewed (Opus, 5 findings, 4 fixed, 1 -> X10),
  merged with the early Phase-3 code (wd5 lane, identity discovery; reviewed, 7 + 5 findings fixed);
  pushed `49ab4c6` (all hook gates green, CI green), live on api and api2, migration 0029 applied,
  0 card overwrites at boot; static export refreshed through the new locked CLI, freshness check
  0 differing sites; Wikipedia cache complete. Phase-2 lane code building (`wf_cdd6677a-8e7`).
- 2026-10-09: calibrations (several rounds; lessons in AUDIT_LOG), D36-D39 (Sonnet instead of Opus, pause at ~90 %
  weekly quota), WD5 pilot written (wave 2026-10-09a: 92 cells at 45 sites, 0 deviations), readers for foreign-language
  dates / regional periods / table coordinates merged (6f1b7e9); WD5 main run started; cards fine-tuning building.

## RESUME POINT - paused 2026-10-09 about 20:30 UTC (owner: weekly quota 95 %) - SUPERSEDED 2026-10-17, see the last section

One of its instructions is history: the run tree is merged and live on `main` at `fc32f37`. Item 2 (D40) stands:
D40 came after D36, and the owner confirmed it on 2026-10-17 (D42).

Nothing is half-written in production: the only write is the WD5 pilot wave 2026-10-09a (92 cells at 45 sites,
accepted, 0 deviations). Run tree = main checkout on `run/2026-10-09-db-final` = `fix/2026-10-08-db-final`; the
branch is NOT pushed (about 25 commits ahead of main: lane code, calibration fixes, releases, D36 moves, readers,
cards tune) - push it first (merge origin/main, CI-only gates, main-push.lock; the SEO session also pushes).

In order after the reset:
1. **WD5 main run** (`output/remediation/fields/wd5`, 1,767 sites): round r0 exported (146 batches, 1,752
   questions), **997 answered** when stopped. Resume workflow `wf_cc685b15-849` from its script (it now stops after
   the r0 import - remove that `return` to continue into the re-asks, the Sonnet re-check (adv-truth-002 passed
   0.96), the backup drill and wave 2026-10-10a), or run the same steps fresh: recorded answers are write-once and
   skipped.
2. **D40**: register owner moves fact_checker and web_verifier to Opus (roles.py, decision D40); calibrate them once
   on the adjudicated gold of teaser-2026-10-10 or release under D40 with the -09c and -10 evidence; card_writer
   stays Sonnet (measured at the pilot). Cards hook_rater and adversarial still failed on Sonnet in -10.
3. **Card pilot** (40 sites), the D10 re-check of the 167 MiniMax cards, then the waves.
4. Pilot re-ask: Olympe, Chitinamit, Shypyntsi (cleared to Undated by 2026-10-09a although a quote states a value).
5. Then the other lanes in the order above (WC finish and defects, identity, enrichment, images, close-out).

Live cards the 2026-10-09 adjudication found wrong (the rewrite replaces them): Astale, North Bersted Man, Roman
Ruins of Sao Cucufate, Caesar's Camp (Bracknell Forest), Teotihuacan - Pyramid of the Moon, Nysa Bridge.

## Progress log - 2026-10-17

- Journal consolidated onto one reader (`b850cd7`, `fc32f37`): 80 citation anchors and 14 popover cards measured
  in a real browser on the live site, `articles-grid` gone, `/articles.html#slug` redirects in the browser.
- Story lane root cause fixed (429 on the httpx path): `tweet_verifier.plan_aware_web_chat` +
  a third `detail` return value so `story_reverify` writes a reason (`bc697d7`); the six `failed` stories of
  2026-10-12 re-run green (1 corrected, 5 verified), journal 103 -> 109 lines, IndexNow accepted 8 URLs.
- Worktrees: 10 removed after an audit (`ccby`, `globeload`, `journal`, `model`, `nerv`, `db-rebase`,
  `journal-hub`, `p4-verify-fix`, `p5-wd5-lane`, `p6-cards-tune`); 6 remain - `p4-pilot` holds ~143 MB of
  Phase-4 row sets the main checkout never received (`V3_ROWS`, `V3D_ROWS`, `LEGACY4*`, `PLAN4.v3*`; its
  ledger delta is saved as `output/remediation/patches/p4-pilot-ledger-2026-10-17.patch`), plus the four
  worktrees this plan protects (`mcode-driver`, `haiku55`, `studio`, `google-avg`) and `db-final`.

## RESUME POINT - paused 2026-10-17 about 20:35 UTC (MiniMax Code session; owner: weekly quota 91 %)

**C1, C3-C7 are blocked, not unfinished: they need a Claude Code session.** Owner decision D6 (2026-10-08)
restricts a new answer to `opus_handoff.NEW_ANSWER_MODELS` = `claude-opus-5-5`, `claude-sonnet-5-5`,
`claude-haiku-5-5`; `opus_handoff.py answer` offers exactly those as argparse `choices` and
`fields/handoff.py::_answering_model` raises `HandoffStepError` for anything else, so a MiniMax stamp cannot
even be recorded. `mcode_driver.py` knows the lanes `wd3`, `wc`, `calibrate` - there is no `wd5` lane. Start a
Claude Code session, or have the owner change D6 (then a MiniMax stamp plus a fresh calibration is required).

State of the run, unchanged and complete:
1. **WD5 main run** (`output/remediation/fields/wd5`, 1,767 sites): round r0 exported (146 batches under
   `output/remediation/handoff/fields-wd5-r0/wd5-r0-b00NN`), **997 of 1,752 answered**, **755 open**. Recorded
   answers are write-once and are skipped, so the run resumes by asking only the open cells. The workflow
   `wf_cc685b15-849` still stops after the r0 import (remove that `return` for the re-asks, the Sonnet
   re-check of `adv-truth-002` at 0.96, the backup drill and wave 2026-10-10a).
2. **D40**, scoped by D45 to the card lane - the card lane's own roles `card_fact_checker` and `card_web_verifier`
   on Opus in `roles.py`, calibrated before first use; the shared `fact_checker`/`web_verifier` stay Sonnet; `card_writer`
   stays Sonnet. (Corrected 2026-10-17, owner decision D42: this item first called
   D40 obsolete, but D40 came after D36.)
3. **Card pilot** (40 sites), the D10 re-check of the 167 MiniMax cards, then the waves. The six cards the
   2026-10-09 adjudication found wrong (Astale, North Bersted Man, Roman Ruins of Sao Cucufate, Caesar's
   Camp, Teotihuacan - Pyramid of the Moon, Nysa Bridge) are replaced by the rewrite.
4. Pilot re-asks: Olympe, Chitinamit, Shypyntsi.
5. Then WC finish and the 141 defects, identity (D14, D13, D23, D20 after wd5, D25), descriptions (WN 28+,
   D21, D3, D4), images D17 for the 952 plus the D15 clears, close-out phase 8.
6. The 38 high-demand in-scope sites without a curated page, each per `docs/procedures/ENRICHMENT_AUDIT.md`,
   inputs `output/seo-audit-2026-10-08/scratch/demand/agg_inscope_candidates.csv` and `proposals_by_demand.csv`.
7. After every accepted image wave `python -m pipeline.wiki_thumbs`; after every content wave the locked
   static-export CLI, the freshness check, then the IndexNow catch-up.

**Running in production, no owner action needed:** the story backbone works through the open backlog in waves
of 30 (`story_backbone.sh` on the VPS, log `story_backbone.log`, journal
`logs/story_reverify/journal.jsonl`). It stops by itself when the backlog is empty, when the weekly MiniMax
quota falls below 30 %, or when a query fails. Start: 2,644 open, 91 % weekly quota, journal 109 lines.
To watch: `ssh ancientnerds 'tail -f /home/deploy/story_backbone.log'`. To stop:
`ssh ancientnerds 'pkill -f story_backbone.sh'` - the waves are journalled and `story_reverify --rollback`
exists. Every write is journalled, so an interrupted wave costs at most the items it had not journalled yet.
## Owner decisions 2026-10-17 (Claude Code session)

D42 D40 stands (checkers on Opus, card_writer Sonnet); D45 scopes it to the card lane (own roles
`card_fact_checker`, `card_web_verifier`). D43 run Phase C now, autonomously, until about 90 % of the
weekly Claude quota, then pause cleanly. D44 D6 stays closed to MiniMax. Recorded in `OWNER_DECISIONS_2026-10-08.md`.

## RESUME POINT - 2026-10-18 (Claude Code session, Opus 5.5; owner away)

Owner decisions D42-D45 (2026-10-17/18, `OWNER_DECISIONS_2026-10-08.md`): D40 stands, scoped to the card lane (D45:
own roles `card_fact_checker`, `card_web_verifier` on Opus; shared `fact_checker`/`web_verifier` stay Sonnet);
Phase C runs in Claude Code sessions to ~90 % weekly quota (D43); D6 stays closed to MiniMax (D44). Details and
numbers: AUDIT_LOG 2026-10-18.

Done:
1. **WD5 main run** - finished and live: wave 2026-10-17a, 10 steps, 1,795 cells at 867 sites, 0 deviations,
   journal recounted; static export fresh (0 differing), IndexNow 938 URLs. 163 cells on `wd5/adv/OWNER.jsonl`.
2. **Card roles calibrated on Opus and released under D40** (top tier, held): `card_fact_checker` teaser-2026-10-18,
   `hook_rater` (tier move after -10) and `card_web_verifier` teaser-2026-10-18b. Note: any edit of a sealed module
   (`roles.py`, `web_rules.py`, `teaser/*`) makes `agents` of those calibration dirs refuse; `standing` still holds.
3. **Reader-gap re-ask lane built** (`935c3d5`, FIELDS_WD5.md section 12): run `output/remediation/fields/wd5-reask`
   is exported and built - 89 sites (60 dated-statement, 28 period-name, 1 bp-age; Olympe, Chitinamit, Shypyntsi in),
   hints copied. Section 10's "92 BP-lost" premise was wrong (wd5 asked them).

In order next:
1. **Card pilot** `output/remediation/teaser/runs/wb-shorts-pilot-2026-10-18` (40 sites, seed 20261018; nothing
   written): state at 2026-10-18 ~13:00 local: 17 accepted, 17 cleared, 6 due verify2 (workflow `wf_a2fb7c9e-455` still running at handover); check `teaser/run.py status`, finish the stages from `verify` on (verify, rewrite-v,
   check-v, verify2), `outcomes`, `judge-export`/`judge-import`, then `calibrate.py evaluate --role card_writer
   --writer-run <pilot>` and the pilot gate of plans/cards.md 3.6. Measured so far: checker PASS at attempt 1 is
   23/39 (59 %, gate 70 %) - the findings are real writer faults (dropped hedges, a town in sentence 1, a name the
   listener can assemble, an ambiguous "it", generic cards), 10 of 40 cleared after two rewrites (they keep their
   card, D5). If the gate fails on the first-attempt share only, tune the writer prompt with those findings and run a
   second pilot; never lower the checker.
2. **wd5-reask research**: export r0 (`handoff.py export --run $R --handoff output/remediation/handoff/fields-wd5-reask-r0`),
   then the rounds, adversarial re-check, backup drill and wave as the WD5 main run (workflow script
   `wd5-main-resume` of this session is the template; seed, wave id `2026-10-18r` or the day's). Web width <= 3 in
   total across all running lanes.
3. D10 re-check of the 167 MiniMax cards (recheck-v1: check/verify on the card roles; `adversarial` failed
   teaser-2026-10-10 on Sonnet with a tier move - decide its card calibration before the re-check).
4. Then the card waves (after a passed pilot), WC finish + 141 defects, identity (D14, D13, D23, D20, D25),
   descriptions (WN, D21, D3, D4), images D17 + D15, the 38 high-demand sites, close-out phase 8 - MASTER_PLAN order.
