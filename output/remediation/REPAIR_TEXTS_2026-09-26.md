# Repairing the 2026-03 texts outside the defect scope - executable design (2026-09-26)

Design only: nothing was written to production, pushed, committed or changed in code. Every number
below was measured read-only on 2026-09-25 between 18:10 and 19:00 UTC (production journal
high-water mark `max(remediation_change_log.id)` = 73911, 18:05:06 UTC) or from the local run files;
the method is named at each number. No file under `acceptance/draw-2026-09-25b/` or
`handoff/acceptance-2026-09-25b-*` was opened; the acceptance numbers are the orchestrator's stage-1
summary (not yet second-judged). Worktree paths: `WT=.claude/worktrees/p4-pilot`,
`R=$WT/output/remediation/phase4_runner`.

**Recommendation in one paragraph.** Pin scope version 3 = v2 plus two lists (`march-description`,
`march-card`) derived from a fresh production read, and send the 3,238 population sites no Phase-4
plan has carried yet through the unchanged W/S pipeline (same selector and reviewer pins, so pilot 4's
pass still covers it) as run `v3`, planned from a **fresh** read so P4 replaces the lane-L
provenance in the same `raw_data` row (no L revert). Do **not** open lanes T or R. Everything the
runs hold after that - about 2,100 descriptions and 2,400 cards of March text - is **cleared**
through a new journalled write group `C`, in one sitting with the P5 cards, then Push #3. Reason: the
plan's own bar ("sourced or absent"), the card contract ("known-wrong narration becomes absent"), and
arithmetic: with ~2,100 March descriptions left in the frame, a fresh 60-site acceptance passes A1
with probability 0.0002.

## 1. The population (measured)

**How.** One read-only SELECT over `unified_sites u LEFT JOIN card_stats c` with
`u.source_id='ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired'` (4,926 sites; 78 retired).
Description class from `raw_data->'_description_provenance'->>'lane'`: W/S/T/R = live Phase-4 text,
`L` = March text marked by lane L, none = unmarked. Card class: *P5* = the site has a forward
`phase5:%` journal row without its own `-rollback` (same `change_key`, stamp + `-rollback`); *old* =
no such row and a non-empty `card_description`. SQL kept at `C:/tmp/repair_measure/pop.sql`.

| description \ card | old card (2026-03) | P5 card | P5-cleared (NULL) | sites |
|---|---|---|---|---|
| L (March text, marked) | **3,682** (both) | 0 | **241** (description only) | 3,923 |
| P4 (W/S) | **131** (card only) | 761 | 97 | 989 |
| unmarked (D7: equal to d4526691 or not in it) | **9** (card only) | 0 | 0 (5 without card) | 14 |

**Population = 4,063 sites**: description-L only 241, card-old only 140 (131 + 9), both 3,682. Old
cards 3,822 (= 3,682 + 131 + 9, the orchestrator's figure); P5 cards 761, P5 clears 338.
`raw_data` of the 3,923 L sites carries only `_description_provenance` (3,923) and
`description_citations` (1,671) - no other key (`jsonb_object_keys`, same filter).

**Already asked vs new** (local join of the site ids with `$R/PLAN4.scope.jsonl` 1,578,
`$R/PLAN4.d9.jsonl` 8, `$R/PILOT4.jsonl` 132; union 1,718): **825** population sites were carried by
an earlier plan and held there (693 desc-L = 241 + 452 with old card; 131 P4-written with a held
card; 1 unmarked). They are never planned again (`verify_writes4.index_runs` refuses a site two runs
carry; contracts section 11). **3,238 are new**: 3,230 both, 8 unmarked-description with an old card.

**How Phase 4 finds an article (Track A).** Not through QID sitelinks. S1 fetches English Wikipedia
by the stored `site_external_ids.enwiki_title` that `PLAN_SQL` puts on each `PlanSite`
(`scripts/remediation/phase4/plan4.py:159-178`) and gates it on the page's `pageprops.wikibase_item`
against the stored `wikidata_qid`, the witness being Phase 3's `wikidata_entity` evidence
(`subject_gate.py`, contracts section 5 Track A). S1b routes only the sites S1 could not anchor:
the `source_url` (an English title, or a non-English article whose English langlink is a W
candidate and whose own text is the T candidate), `list=geosearch` within 2 km at name score >= 90,
then MiniMax search - off (`route_stage.py:523-555`, `_assign` `:1008-1045`; T at `:1035-1038`, R
only from search pages `:1043-1044`). Wikidata sitelinks are read only by the Phase-3 sitelink lane
(`fetch_stage.MAX_WIKI_SITELINKS = 3`). The S0 rows matter because they carry those ids: the ids
repaired on 2026-09-23 (external-id waves) reach Phase 4 only through a fresh read.

**Usable article, measured** with the census run `runs/census-2026-09-24` (all 5,004 sites through
S1/S1b with searches off; `lanes.jsonl` of its 335 batches, `HOLDS4.jsonl`):

| | lane W (own English) | lane S (shared/parent) | lane 0 (none) | of lane 0: other-language article (sitelink census) |
|---|---|---|---|---|
| 3,238 new | 2,477 | 246 | 515: search-stopped 442 (284 no title and no QID, 158 title rejected by the gate), revision-too-fresh 49, scope-pending 24 | 68 (81 have no sitelink record, 366 no QID / withheld) |
| 825 already asked | 577 | 86 | 162 | 33 (42 no record) |
| **4,063** | **3,054** | **332** | **677** | **>= 101** |

The census assigned **0 sites to T and 0 to R** (W 3,887, S 372, 0 745). "Other-language article" =
`output/remediation/sitelink/lane/sitelinks.json` `chosen` non-empty (up to 3 non-English articles
per QID; it covers only the 3,109 sites with Phase-3 unverifiable fields, hence "no record").

## 2. Scope version 3 and the run

### 2.1 The rule and the lists

"A new scope is a new version and a new pin, never an edit of the file" (`scope4.py:7-8`,
contracts section 9 line 1117-1118). Version 3 (`$R/SCOPE4.v3.json`) = every v2 list unchanged
(`VERSION_LISTS`, `scope4.py:96`) plus, appended:

* `march-description` - a curated, non-retired site whose live `_description_provenance.lane` is `L`;
* `march-card` - a curated, non-retired site with a non-empty card and no forward, un-reverted
  `phase5:%` row for it (the section-1 definition; equal to "no live full provenance naming this
  card", D4).

Input: `$R/MARCH4_ROWS.jsonl` from one new read-only SELECT (`MARCH_SQL`: id, scope_status,
provenance lane, card present, live-P5 flag), sha256 recorded in the file's `inputs`. Expected
counts at today's state: 3,923 and 3,822; union 4,063. v3 refuses nothing v2 allowed; the lists add
no `SiteFlag` (`model4` untouched, contracts section 1 rule 1), so V9's 50 % floor
(`verify4.py:1204-1217`) holds for them (mass run: 27 V9 holds in 1,578).

Decision text for `DECISIONS[3]`: the acceptance's stage-1 finding that the Phase-3 finder missed
most text defects (old cards 18/43 WRONG severe, CP95 27-58 %; old L descriptions 9/29, CP95
15-51 %), under the owner order of 2026-09-25. Re-evaluate the wording once stage 2 confirms.

### 2.2 Why the plan reads production afresh (and not `S0_ROWS.jsonl`)

S0 (2026-09-20) predates lane L (3,923 `raw_data` rows), the Phase-3 lanes and reversals the
selector's site block shows, and the external-id repairs. A plan from a fresh `PLAN_SQL` read names
today's `raw_data` (with the L provenance) as the old value; `write4.new_raw_data`
(`write4.py:202-212`) replaces `_description_provenance` and `description_citations` and keeps every
other key, which V12 allows (`verify4.py:1416-1436`). So P4 supersedes the L row inside the same
cell: **no `revert4 --site` of L rows** (the section-11 procedure was needed only because the D9
plan named S0's values), a P4 revert restores the L marking by itself, and lane L's acceptance runs
with `--allow-stamp 'phase4:%'`, without `--complete` (contracts section 11).

### 2.3 Code changes (on `integrate/wave1`, test-first, each guard with a mutation case in `scripts/remediation/phase3/mutation_sweep.py`, contracts section 1 rule 5)

| file : place | change | tests |
|---|---|---|
| `phase4/scope4.py:79-96, 110-155` | `SCOPE_VERSION = 3`, `SCOPE_FILE = SCOPE4.v3.json`, new pin; keep v2 as `SCOPE_V2_FILE/SCOPE_V2_SHA256`; `LISTS` += the two lists; `VERSION_LISTS[3]`, `DECISIONS[3]`, `VERSION_METHODS[3]`; `march_lists(rows)`; `scope_payload(..., march_rows=())` | `tests/remediation/test_phase4_scope.py`: v1 and v2 rebuild byte for byte at their pins; v3 is a superset of v2; a v2 file at the v3 pin refused; fixtures: L provenance -> description list, retired excluded, P5 card and P5 clear not listed |
| `phase4/scope4.py:369-376` `pinned_file` | answer versions 1, 2 and 3 (today only current + 1: v2 would become unreadable) | same file, `load_scope(2)` |
| `phase4/plan4.py` | `read-march` (the one `MARCH_SQL` SELECT, `ROW_KEYS` of `PLAN_SQL` untouched); `scope --version 3 --march`; `build --scope-list` repeatable (union); `--exclude FILE` (UUIDs, accounted as "deferred", printed as count + sha256 only); `--first-batch N` replacing the constant `LIST_PLAN_FIRST_BATCH` (`:119`, check `:450`): refused unless N > every `--after` ordinal and outside L's block 1001-1334 and C's 3001-; `clear` subcommand (below) | `test_phase4_plan.py`: D9 plan rebuilt byte for byte with `--first-batch 901`; union of two lists; excluded sites absent and accounted; collisions refused |
| `phase4/write4.py:94-145` | `Group.C` (family `phase4c`, prefix `p4c`), tests `C/description-clear`, `C/raw_data-clear`, `C/card-clear`; `GROUP_ROWS[C]` over both tables (the renderer already joins both, `:1167-1171`); `MAX_CHUNK_ROWS[C] = 300` | `test_phase4_write.py`, pins in `phase4_write_pins.py` |
| `phase4/write4.py:582-596` `_validate_raw_data` | for C: old carries the L provenance, new carries neither key (NULL when nothing remains) | same |
| `phase4/write4.py` new `plan_clear`, `load_clear_plan` (beside `plan_legacy` `:898`, `load_legacy_plan` `:687`) | per site: L description -> description NULL + raw_data minus both keys; a card no live full provenance names -> card NULL. Refused: `written-by-p4`, `no-march-text`, `unmarked-description` (D7: description kept, listed), `retired`, `not-final` (March text and not held in its latest run) | each rule red without it |
| `output/remediation/tools/write_gate4.py:248-299, 749-775` | `--group C --clear-plan CLEAR4.jsonl --run <each run>` (runs only for the holds evidence); read-only per-window read of lane, card sha, `scope_status` (the `written_sites` pattern, `:191-211`); any `not-final` ends `WRITE_EXIT=1` | `test_phase4_write.py` gate cases |
| `output/remediation/tools/verify_writes4.py:87-91` and the invariants near `:608-620` | lane `p4c` (both tables; no verifier): description NULL implies neither key in `raw_data`; card NULL | `test_phase4_accept.py` |
| `output/remediation/tools/lanes.py:14` | register `p4c` (`phase4c:p4c-%`) | lanes test |
| `phase4/card_json.py:123-140` `planned_cards` | also read the C apply root's card rows (`--c-root logs/_write_apply_p4c`) | `test_phase4_card_json.py`: a C clear removes the key |
| consumers of a NULL curated description | none expected (exporter guards it, `pipeline/static_exporter.py:293, 595`) - prove it | `src/seo/__tests__/render.test.tsx` and a `tests/api` site-detail case with `description = NULL` |
| docs | contracts section 12 (v3, the fresh read, group C); `CARD_DESCRIPTIONS.md` "Held cards" (`:100-108`); HUMAN_ONLY D6 (German); HANDOVER | - |

Not changed: `model4.py`, `prompts4.py` (selector `a0b422e7...`, reviewer `097c4589...`), `mass4.py`
(`outside_scope` reads the current scope, `mass4.py:525-535`), `phase4/audit4.py` and `model4.py`
(the running acceptance imports both: `acceptance/draw.py:48`, `checks.py:34`). Before any of it:
the code audit's 11 Major tooling findings (`output/remediation/CODE_AUDIT_2026-09-25.md`, HANDOVER
section 0 item 2). Merge the result into the worktree branch (`git -C $WT merge --ff-only
integrate/wave1`) before the run: `mass4` hashes `phase4/` before every batch.

### 2.4 Command sequence (from `$WT`, main venv, `export PYTHONIOENCODING=utf-8`, PYTHONPATH as HANDOVER section 4; `P=scripts/remediation/phase4`, `PY=/c/PythonProjects/AncientMap/.venv/Scripts/python.exe`)

```bash
# reads (read-only) and the scope
$PY $P/plan4.py read       --out $R/V3_ROWS.jsonl
$PY $P/plan4.py read-march --out $R/MARCH4_ROWS.jsonl
$PY $P/plan4.py names --rows $R/V3_ROWS.jsonl --out $R/V3_ITEM_NAMES.json   # build refuses without it if the shared QIDs moved (plan4.py:262-264)
$PY $P/plan4.py scope --version 1 --out C:/tmp/s1.json && $PY $P/plan4.py scope --version 2 --out C:/tmp/s2.json  # printed sha256 = the pins (never write over a pinned file)
$PY $P/plan4.py scope --version 3 --march $R/MARCH4_ROWS.jsonl   # -> SCOPE4.v3.json; pin its sha256 in scope4, commit file + pin + AUDIT_LOG seal
# the plan: EXCLUDE = the orchestrator's file of the 60 drawn ids (omit --exclude once the acceptance result exists)
$PY $P/plan4.py build --rows $R/V3_ROWS.jsonl --names $R/V3_ITEM_NAMES.json --pilot $R/PILOT4.jsonl \
  --scope-list march-description --scope-list march-card --after $R/PLAN4.scope.jsonl --after $R/PLAN4.d9.jsonl \
  --exclude $EXCLUDE --first-batch 2001 --out $R/PLAN4.v3.jsonl          # ~216 batches p4-2001 .. p4-2216
M="$PY $P/mass4.py --plan $R/PLAN4.v3.jsonl --run-dir $R/runs/v3-<date> --log-dir output/remediation/logs/p4_v3 --searches-off --live"
H=output/remediation/handoff
$M --stages prepare,sources,routes,select --handoff-export $H/p4-v3-select        # all batches, one round (~25 min)
# per group G of 6 batches (90 sites = one write step), 36 groups:
#  1. 6 agents in parallel, one per batch: answer $H/p4-v3-select/<batch>/select/*.prompt.txt with
#     opus_handoff.py answer --answered-by opus-p4v3-select-<batch>; then opus_handoff.py validate --dir $H/p4-v3-select
$M --only $G --stages select --handoff-import $H/p4-v3-select
$M --only $G --stages translate --handoff-export $H/p4-v3-translate                # T closed: expect no question; stop if one appears
$M --only $G --stages translate,assemble,verify --handoff-import $H/p4-v3-translate
$M --only $G --stages review --handoff-export $H/p4-v3-review
#  2. 6 review agents, validate, then
$M --only $G --stages review --handoff-import $H/p4-v3-review && $PY $P/run4.py holds --run-dir $R/runs/v3-<date>
G4="$PY output/remediation/tools/write_gate4.py --group P4 --run v3-<date> --open-lanes W,S"
$G4 $(printf -- '--batch %s ' $G)                       # dry; then --rehearse; then --apply --step 100
$PY output/remediation/tools/verify_writes4.py --lane p4 --plan output/remediation/logs/_write_apply_p4/LANE_PLAN.jsonl \
  --run runs/pilot4-2026-09-24 --run runs/mass-2026-09-25 --run runs/d9-2026-09-25 --run runs/v3-<date> \
  --allow-stamp 'phase4l:%' > output/remediation/logs/p4_v3/accept-step-NN.log
$G4 --accept output/remediation/logs/p4_v3/accept-step-NN.log         # only on ACCEPT_EXIT=0, RESULT: 0 deviation(s)
# every 500 written v3 sites: audit4.py draw --written (10 sites, excluding earlier samples), Opus audit, as the mass run
```

After the acceptance result: (a) the drawn population sites as `PLAN4.v3b.jsonl` (`--after
PLAN4.v3.jsonl`, no `--exclude`, `--first-batch 2501`, reusing `V3_ROWS.jsonl`: no write touched a
drawn site), run `runs/v3b-<date>`, same cycle; (b) the mass run's 19 `revision-too-fresh` sites
through `mass4.py --plan PLAN4.scope.jsonl --run-dir runs/mass-2026-09-25` (its re-queue,
p4-0116..), still S0 lines, so lane-L-first as in the D9 run (contracts section 11); (c) the v3 run's
own too-fresh sites, re-queued by `mass4` 48 h after its S1 (~2 % of the fetched articles, ~50-65).
Every p4/p5 acceptance from then on names all five runs.

## 3. The held sites

### 3.1 Classes after v3 (now = measured; expected = v3's census lane mix x the mass run's outcome rates W 70.5 % written, S 27 %, lane 0 0 %, card held on 23.2 % of written - AUDIT_LOG mass-run entry)

| class | now | expected after v3 |
|---|---|---|
| H1 description written by P4, card held (V10, card-too-short-after-review) | 131 | +~420 |
| H2 site held with an English article (W/S: abstained, V5/V6/V9/V14/V15, review-too-few, selection-refused, audit-*) | 693 desc-L in earlier runs, all lanes | +~910 (731 W, 180 S) |
| H3 site held with no English article (search-stopped, no-source) | incl. above | +~440 |
| H4 scope-pending (dates outside E3) | incl. above | +24 |
| H5 revision-too-fresh | 19 | ~50-65, re-queued, not final |
| H6 unmarked description (D7) with an old card | 9 | same |

So after v3 about **1,810 new descriptions (56 %) and ~1,395 P5 cards**, and left with March text
about **2,100 descriptions and ~2,430 cards** over ~2,670 sites (held rate 44 %, above the mass run's
39 % because the new population has 15.9 % lane 0 against 9.9 %).

### 3.2 Lanes T and R - what they are, why never opened, what opening needs

**T** (design entry [6] `pipeline` "Lane assignment", `writer` "LANES WITH GENERATED TEXT"): an own
article only in another language; the selector picks source-language sentences, a second call
(`translate_stage.py`, `TRANSLATE_QUESTION`) translates them; text `ai: 'generated'` plus the
attribution; **no card** (V10: "lanes T and R build no card", contracts `:303`). Never opened because
(1) its only route is a non-English `source_url` without an English langlink (`route_stage.py:532-533,
1035-1038`) and the census found **0** such sites; (2) no T pilot ever ran (T12: 0 UNSUPPORTED over
>= 5 sites) - every gate call was `--open-lanes W,S`; (3) a sitelink route is not in the design, and
its only measured analogue, the sitelink pilot, failed its sealed thresholds (HANDOVER 2.5: "sources
of that kind import their own errors"). Opening it needs a new S1b route (QID sitelinks -> T
candidate through S1's gate on the page's own item), a contracts section, a T pilot passing T1-T7 and
T12, a 100 % independent audit before any write (`write4.py:828-834`, `--audited`), and the card is
cleared anyway. Yield: >= 101 lane-0 sites (section 1), at most ~220 with the unrecorded ones - under
10 % of the held set; H2 sites cannot use it (a site never changes lane, contracts section 1 rule 6).

**R**: only non-free pages; 2-4 restated sentences, each with a verbatim quote located by code, no
8-word run copied; `ai: 'generated'`; no card; T11 (0 UNSUPPORTED over >= 8 sites, one hit closes the
lane); 100 % audit. Never opened because its pages come only from MiniMax search hits
(`route_stage.py:22-34`), and the remediation sends no search: no MiniMax for the remediation
(HANDOVER 5.6), `--searches-off`, the search pilot of 2026-09-23 failed. Opening it needs a search
transport the owner allows (an Opus web-search handoff stage in place of `MiniMaxSearcher`: new code
and contract), a pilot, a 100 % audit; and by construction each sentence rests on one quote from one
page, so it never reaches "confirmed against at least two independent sources" (plan 1.3).

**Verdict: open neither in this repair.** A later T run can still fill a cleared site: a NULL
description passes V9 trivially and P4 writes over NULL like over any text.

### 3.3 Clearing - grounds, product effect, vehicle

**Grounds.** Plan 1.1: "sourced or absent"; 1.3: "Every shipped field is either confirmed against at
least two independent sources, or empty" and "The card text ... contains no claim absent from the
sourced description". `CARD_DESCRIPTIONS.md:3-9`: a card is "an extractive condensation of the site's
own published description, never a second free generation"; `:104-108` "Known-wrong narration
becomes absent". The acceptance's stage 1 (orchestrator summary) makes the class known-wrong at
class level: old cards 18/43 severe (CP95 lower bound 27 %), old L descriptions 9/29 (15 %), both far
above A2's 5 % tolerance. The old cards also carry **no AI mark** at all: `card_ai` returns `None` for
lane L and for unprovenanced cards (`api/services/description_provenance.py:115-121`). And
PROTOCOL: L-marked sites are in the frame (their `raw_data` row, `PROTOCOL.md:35-42`); an empty field
is not asked (`:116`). With ~2,100 March descriptions in a ~4,926-site frame at 31 % severe, P(0
severe in 60) = 0.87^60 = 0.0002 - Phase 6 cannot close while they are served.

**Supersedes** (record in HUMAN_ONLY, German, before the first C write): D6 "bleibt beim alten Text",
the card contract's "a held card keeps its old card", and E1's "no bulk rewrite of descriptions
without separate approval" (plan `:44`) - approval under the order of 2026-09-25, as for D5/D9. Undo:
`revert4.py --stamp-like 'phase4c:%'` (rehearse first), then `card_json.py --regenerate` and a push.

**Recommendation per class**

| class | old card | old description |
|---|---|---|
| H1 | **clear** (it is not a condensation of the published P4 text - 1.3's third bullet, deterministic) | already sourced |
| H2, H3, H4 | **clear** | **clear** (description NULL, `raw_data` minus `description_citations` and `_description_provenance`, else D1/D4 fail) |
| H5 | wait for the re-queue; then H1-H4 | same |
| H6 | **clear** if still held | keep, listed for the owner (D7: origin not provable, so not claimed as March text) |

**What the product shows.** Empty card: `SiteCard` falls back to the description
(`ancient-nerds-map/src/components/SiteCard.tsx:105-115`) - for H1 the sourced P4 text, for H2-H4
nothing; `GameCard` detail shows no text (`cards/GameCard.tsx:317-319`), the showcase shows only a
passed `description` (`:238-245`, GamePage mockups); the API omits `cardDescription`
(`api/routes/sites.py:1240-1241`, `cd` at `:402-403`); shorts: not eligible either way (no card
provenance). Empty description: the popup renders no description block and no disclosure in site
mode (`SitePopup/sections/DescriptionSection.tsx:66-85, 96-98`; "No description available" only in
empire mode); the SSR page drops `meta description` and `Place.description`
(`src/seo/meta.ts:261-270`) and keeps name, country, type, period, map, image and links.
**Cost:** ~2,100 of 4,926 site pages (43 %) lose their text - a thin-page risk in Search Console;
watch it with `scripts/gsc_report.py` after the IndexNow announcement.

**Vehicle: group C** (section 2.3), its own plan over every curated site like lane L
(`plan4.py read --out CLEAR4_ROWS.jsonl`, `plan4.py clear` -> `CLEAR4.jsonl`, batches from p4-3001,
mark `pass: phase4-clear`), planned **once the held set is final** (every run, re-queue and v3b done),
site-atomic (description, raw_data, card of one site in one chunk), steps of 100 sites. Journal
evidence per row: the site's latest run, batch and hold lines, the provenance at read, the
contract section, and the acceptance `RESULT.json` sha256.

## 4. Cost and time

| item | basis | v3 (3,238 sites, 216 batches) |
|---|---|---|
| selector questions | mass: 1,392 for 1,578 (0.882/site); lane-adjusted: all but lane 0 (515) and S without a naming sentence (29 % of S = 71) | **2,650-2,860** |
| review questions | mass: 1,003 (0.636/site; 0.72 per selector question) | **1,910-2,060** |
| translate / restricted | lanes closed | 0 |
| tokens | 12k per selector, 8k per review question | 32-34M + 15-17M = **~47-51M** |
| handoff batches (agents) | one agent per batch and stage | 216 select + 216 review = **432**; v3b <= 4+4, the 19 re-queued 2+2, v3's own re-queue ~5+5 |
| wall time, answering | 6 agents in parallel, 15-30 min per batch agent | 452 / 6 = 76 waves -> **19-38 h** |
| same, at the mass run's measured pace | answer files: selector batch median 1.3 min first-to-last answer, 3.8 min between batches; review 0.2 / 1.3 min; 106+106 agents in 13.4 h serial (writes included) | ~7 min per select+review pair -> **~4-5 h** at 6 parallel |
| non-model stages | mass export of 106 batches: 11 min | ~25 min |
| audits | 10 written sites per 500 (design MASS RUN GATES) | 3 blocks, ~1 h each |
| writes | step times from `ACCEPTED/` mtimes: P5 1.3-2.5 min, L ~2 min, P4 ~2-5 min | P4 ~20 steps, P5 ~16, C ~29 (~6,600 rows: ~4,200 description/raw_data + ~2,430 cards) -> **~2-3 h** |
| model spend | handoff answers are unmetered (`--max-usd 15` untouched) | $0 metered |

Calendar: code + tests + audit fixes ~1 day; run 1-2 days (the 48 h re-queue of v3's fresh
revisions overlaps it); the P5+C sitting ~1.5-2 h; follow-through ~1 h; then the fresh acceptance.

## 5. Constraints and order

1. **V3 of the acceptance** (`PROTOCOL.md:173`): no remediation write on a drawn site before the
   result. The v3 plan takes `--exclude <file the orchestrator writes from the draw>`; the design
   never reads the ids. Excluded sites are planned in v3b after the result; the 19 re-queued sites
   and group C run after the result (C needs the final held set anyway). Model questions and writes
   on non-drawn sites do not touch V3.
2. **The 19 `revision-too-fresh` sites**: due from 2026-09-26T21:30Z, run after the result, L row
   first (section 2.4 (b)).
3. **Every write through the journalled gates**: `write_gate4` dry -> `--rehearse` (APPLY ending in
   ROLLBACK) -> `--apply --step 100` (preflight, write, read-back both directions, the two sha256
   invariants, the inverse proof run as-is) -> `verify_writes4` saved -> `--accept`; `revert4.py
   --rehearse` for `phase4c:%` before C's first step; read the `WRITE_EXIT=`/`ACCEPT_EXIT=` lines,
   never a wrapper's status (HANDOVER section 7).
4. **The P5 + C sitting** (`CARD_DESCRIPTIONS.md:50-92`): backup drill (`00_backup_and_drill.sh`,
   `DO_DRILL=1`); record `StartedAt` of `ancient_nerds_api` and `_api2`; P5 plan (v3, v3b, re-queues)
   and C plan dry; `card_json.py --prerender --plan4 $R/PLAN4.jsonl --p5-root ... --c-root ...` (the
   full plan carries every site), commit locally; P5 steps, then C steps, each accepted
   (`verify_writes4 --lane p5 --card-check`, `--lane p4c`); `card_json.py --regenerate` byte-identical;
   `StartedAt` unchanged; **Push #3 at once** (never the file before the database). After the deploy:
   `curl localhost:8000/` `commit` = HEAD, 0 `[STARTUP] Card description overwritten` on both API
   containers, `card_json.py --check`, `verify_writes4 --lane p4l --allow-stamp 'phase4:%'
   --allow-stamp 'phase4c:%'` (no `--complete`).
5. **Follow-through** (AUDIT_LOG Phase-6 runbook `:11141-11182`): the card_stats wave re-planned (its
   premise hashes `md5(description)`, which v3 and C move), the static export on the VPS (step 3),
   the Qdrant resync (step 5, outside 02:55-03:10 UTC), IndexNow (the hourly Lyra step announces the
   journalled description changes; catch-up `indexnow_submit.py --all --lastmod-since <v3 start>`),
   the checks of step 7, then a fresh draw sealed anew (excluding both earlier draws' 60 and v3's
   audit samples via `--phase4-audit-samples`).
6. **Deploy rules** (CLAUDE.md): the code changes are tooling and need no deploy; Push #3 is a live
   deploy through the pre-push gates with the working tree equal to the pushed commit; no
   compose/migration change is involved. The card file loses ~2,430 keys - data removal, authorized
   under the order of 2026-09-25 like Push #2; say so in HUMAN_ONLY.

## 6. What this does not settle

The new pipeline's own flags (stage 1: P5 cards 1/12, P4 W descriptions 1/10) are the acceptance's
to confirm; if confirmed, their class needs its own root cause before the fresh draw. The 7,761
unverifiable Phase-3 fields and the 14 unmarked D7 descriptions stay open owner items.
