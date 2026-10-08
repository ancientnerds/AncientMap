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

## Throughput and cost (measured inputs, estimate)

- Model answers over all workstreams: about **35,000** (cards ~19,500; descriptions ~7,300;
  fields ~3,800; identity ~2,100; images ~800; calibration/WF ~2,000), in roughly **3,500-4,500
  agent runs**, mostly Opus 5.5 and Sonnet 5.5.
- Tokens: the read-only mapping agents used ~250k each; answering agents of 5 questions are
  estimated at 100-250k. Order of magnitude **0.4-0.9 billion tokens**. The Claude plan's usage limits
  will pause the runs; workflows resume from their run ids.
- Wall clock is bound by web verification at width <= 3 (Wikimedia throttles this IP at 4+):
  ~14,000 web-checked answers at ~11 min per 5-question batch -> **~7-9 days of continuous running**.
- Disk: C: ~19 GB free; no step downloads at scale (largest: image candidates 1-2 GB, pruned
  after verdicts). One worktree only (4.6 GB).

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

**Phase 8 - Close-out:** site_type merge, card_stats wave + the five dead columns, static export,
docs (CLAUDE.md, HANDOVER 0.0.0, CARD_DESCRIPTIONS, SENTENCE_CHECK, FIELDS_*, AUDIT_LOG,
HUMAN_ONLY), WF measurement (X7), the owner list of everything that stays empty or unsourced, the
final report.

## Progress log

- 2026-10-08: decisions recorded (c6c896e); state audit and six workstream maps done; this plan.
