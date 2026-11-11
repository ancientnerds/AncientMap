# D57: the insert lane - new Ancient Nerds Originals for the high-demand sites

Owner decision **D57** (2026-10-24): the 38 high-demand in-scope sites without a curated page, plus
Chaco Canyon, become Ancient Nerds Originals (`source_id = 'ancient_nerds'`: an SSR page, a card,
every lane) through a journalled insert lane - rehearsed, undone by retiring (never DELETE), the
matching `site_proposals` closed as `approved` with `promoted_site_id`, then description, fields,
images and card per ENRICHMENT_AUDIT. **D58** is the scope rule: only the medieval Old World of
Europe, Byzantium and the Vikings is out (L'Anse aux Meadows stays out). E8 (2026-10-08) is the
hand review the list comes from. This is the one sanctioned exception to ENRICHMENT_AUDIT's "only
the admin promotes to Originals".

**The insert is staged** (orchestrator decision O12, 2026-11-10, under O4 and D143: no page goes
public without text and picture). The rows are written hidden - `scope_status = 'retired'` with a
`scope_reason` that begins `D57 staged:` - each with its `card_stats` row, in one journalled
transaction. A staged site has no page (its URL answers 410), no dot, no sitemap line and no card
draw. The description and picture lanes work on it while it is hidden, and the scope lane's
journalled un-retire shows it once it holds both (section 6).

Code: `scripts/remediation/insert_site/` (`candidates.py`, `research.py`, `plan.py`, `writer.py`,
`run.py`); tests `tests/remediation/test_insert_site.py`; mutation cases `insert-site:` in
`scripts/remediation/mechanical/mutation_sweep.py`. No model is called by the code; no migration,
no new table.

## 1. The candidate list (built 2026-10-24, read-only)

`run.py candidates` reads `agg_inscope_candidates.csv` of the demand audit (the 38 rows with
`manual_verdict = in`; the 16 `zweifelhaft` stay out) and `proposals_by_demand.csv`, adds the pinned
**Chaco Canyon** (Q732463, the park item that the English article "Chaco Canyon" redirects to),
resolves each item and its English article (fields harvest: `wbgetentities`, then the article's
redirect/disambiguation/item check) and reads production once, read-only.

Result of the run `d57-2026-10-24` (`output/remediation/insert_site/d57-2026-10-24/CANDIDATES.md`,
read 2026-10-24 08:22 UTC): **39 candidates - 37 to research, 2 excluded, 0 unresolved, 0 curated
already.**

* Excluded (pinned, `candidates.EXCLUSIONS`): L'Anse aux Meadows (Q189113, D58: Viking subject) and
  the Walls of Constantinople (Q89917, the Theodosian Walls: a Byzantine subject, E8 + D58).
* Merged on Wikidata: Sanchi Stupa's Q10332176 is merged into **Q181123** (Sanchi, enwiki "Sanchi
  Stupa"); the candidate follows the merge and records `qid_asked`.
* Pinned parent (D25, `candidates.PARENTS`): the Terracotta Army (Q47672) is written as a component
  of the curated Qin Shi Huang's Mausoleum (Q910180, `07ea80ce-...`, 1.8 km, China).
* Proposals closed by item or article: 11 (Colosseum, Carthage, Ephesus, Nineveh, Mohenjo-daro,
  Catalhoyuk, Tutankhamun's Tomb (KV62), Sanxingdui, Nan Madol, Mesa Verde - all `new` - and Chaco
  Canyon, `out_of_scope` on the park's 1980 designation date). L'Anse aux Meadows' proposal stays.
* **5 of the 11 mirror a radar contribution** (`site_proposals.contribution_id`): Nineveh
  (`919d5841`), KV62 (`99ee9d62`), Sanxingdui (`15718878`), Nan Madol (`565ea61e`) and Chaco Canyon
  (`ec1e99a7`), all `enrichment_status = 'enriched'` with no `promoted_site_id` (read 2026-10-24).
  The insert promotes each with its proposal (section 4); CANDIDATES.md flags them.
* Proposals that name only the name are listed, never closed (a name does not say which place was
  meant: "Memphis" is also Memphis, Tennessee): Pantheon (needs_decision), Memphis (new), and
  `not_a_place` rows of Carthage, Nineveh, Pella, Susa, Caesarea Maritima; the plan lists those of
  the researched name too ("Chaco Canyon", "KV62").

The 37: Colosseum, Pantheon, Carthage, Terracotta Army, Ephesus, Watson Brake, Antioch, Nineveh,
Giants of Mont'e Prama, Mohenjo-daro, Memphis, Castel Sant'Angelo, Circus Maximus, Çatalhöyük, Arch
of Titus, Tomb of Tutankhamun, Palatine Hill, Appian Way, Londinium, Palmyra, Ctesiphon, Pella, Merv,
Tel Megiddo, Susa, Sanxingdui, Thermopylae, Panathenaic Stadium, Nan Madol, Miletus, Sanchi, Mesa
Verde, Caesarea Maritima, Mausoleum of Augustus, Nicaea, Trajan's Column, Chaco Canyon (the names
are the researcher's to settle).

## 2. Prerequisites

* A Claude Code session (D6/D44: the answers come from Claude agents; the role is
  `field_researcher`, Sonnet 5.5 high, calibrated on `wd1_wd3_rounds_and_bp_set`; its stamp is
  checked at import).
* The checkout the commands run in holds the LFS boundary file the plan's country check reads:
  `git lfs pull --include data/boundaries/countries.geojson` (a sparse worktree has the pointer only).
* The demand directory of 2026-10-08 is in the main checkout:
  `C:/PythonProjects/AncientMap/output/seo-audit-2026-10-08/scratch/demand`.

## 3. The run

```bash
PY=./.venv/Scripts/python.exe; I="$PY scripts/remediation/insert_site/run.py"
R=d57-2026-10-24; H=output/remediation/handoff/insert-$R

# 1. the candidate list (done 2026-10-24; a run's list is built once)
$I candidates --run $R --demand-dir C:/PythonProjects/AncientMap/output/seo-audit-2026-10-08/scratch/demand

# 2. the research handoff: 37 questions, 7 batches of 6
$I research export --run $R --handoff $H-r0
$I research brief  --run $R --handoff $H-r0 --batch-id ins-r0-b001     # one field_researcher agent per batch
#    the agent runs, per question: research check-answer ..., then opus_handoff.py answer ... --role field_researcher
$PY scripts/remediation/opus_handoff.py validate --dir $H-r0
$I research import --run $R                                            # fetches every quoted page once
$I research export-reask --run $R --handoff $H-r1                      # while REASK.json names fields (at most 2 re-asks)
#    answer, validate, import again; the plan refuses to run while a field waits, and while a round
#    exported after the last import is not imported (`round N was exported after the last import`)
$I research export-reask --run $R --handoff $H-r2 --review A           # D104: + the fields the D8 review A
#    (the pilot_judge's answer file about step 1's PLAN.md) vetoed; their old answers stop counting.
#    Move the reviewed step-001 aside first only after the export: the review is checked against its PLAN.md
$I research export-reask --run $R --handoff $H-r3 --review A --owner-round F  # D114: one owner-released round
#    past the last re-ask. F = {"decision": "D114", "questions": {QID: {field: question}}}: only those
#    fields, each vetoed by review A, each asked with the review's reason and the owner's question.
#    An answer that does not count leaves the field exhausted (no further round).

# 3. the plan (read-only production read): PLAN.jsonl, REFUSALS.jsonl, PLAN.md, STEP.json, ROLLBACK.sql
$I plan --run $R --step 1
#    D8: the pilot_judge (Opus xhigh) reviews PLAN.md and DECISIONS.jsonl of the step before the write

# 4. the write
$I emit              --run $R --step 1      # APPLY.sql, pinned; refused without this plan's ROLLBACK.sql
$I rehearse          --run $R --step 1      # COMMIT -> ROLLBACK on production, 0 journal rows after
$I probe-guards      --run $R --step 1      # 8 corrupted copies (7 without a radar-backed proposal), each refused by its own guard
$I apply             --run $R --step 1      # the one write, then the read-back
$I readback          --run $R --step 1      # plan = journal = data, both ways; a NOTE names recomputed card rows
$I rehearse-rollback --run $R --step 1      # the undo's guards on the landed rows, rolled back
$I accept            --run $R --step 1      # ACCEPTED.json (0 deviations, once), INSERTED_SITES.txt
$I status            --run $R
```

`plan`, `emit`, `rehearse` and `apply` refuse a step whose rows do not carry the staged reason
(`REFUSED: ... the plan is not a staged insert - move the step aside and plan again`): a step
planned before O12 says "in scope" and can no longer be written. `plan` prints `journal_rows`; the
count of the stamp in `remediation_change_log` after `apply` must equal it.

Exit codes of the writer steps (the shared writers'): 0 ok, 1 refused (nothing sent), 3 not
committed, 4 committed but psql did not finish cleanly, 5 outcome unknown (read the journal under the
run stamp, never retry), 6 committed but the read-back differs, 7 a rehearsal or a probe failed. After
a 5: wait until no psql session of the write is open, then count the journal rows of the stamp - all
planned rows means it landed, 0 means nothing was written.

## 4. What the write does

One transaction (`writer.render_apply`), journal identity: run stamp `<run>_insert-site-s001`,
`test_id = 'D57/insert-site'`, `confidence = 'one_source'`, `change_key = 'insert-site:<QID>:...'`,
`site_id_ref` the new site. The journal records an insert the way the image lane's INSERT does: one
row per written column, `old_value` NULL, `new_value` read back from the created row.

* **`unified_sites`**, the curated column set: `id` (new uuid4, its 8-hex page prefix free),
  `source_id = 'ancient_nerds'`, `source_record_id = 'd57-<QID>'`, `name`, `name_normalized`
  (`site_key_sql`, the boot reconciliation's key), `lat`, `lon`, `geom`, `site_type`,
  `period_start`, `period_name` (the bucket; `Undated` with no start), `country`, `source_url`,
  `edited_by = 'remediation-d57'`, `raw_data`, `scope_status = 'retired'`, `scope_reason`
  (`plan.staged_reason`: it begins `D57 staged:` - `public_sites.D57_STAGED_PREFIX` - and names the
  stamp), `updated_at = now()`, `parent_site_id` (pinned components only). `description` and
  `thumbnail_url` stay NULL - their lanes write them, which is why the row is written hidden.
* **`raw_data`**: `_insert_provenance` (D57, run, item, article, every field's decision, quotes and
  answerer, the description's sources), `_period_provenance` (`quote`, or `undated`) and
  `_coord_provenance` (`quote`) - the `field_prov` markers (D12/D19), each hashing its value.
* **`unified_site_names`**: the `label` row, and an `alias` row for each name (and alias) of a
  closed proposal whose key differs - what `POST /api/proposals/{id}/approve` writes.
* **`site_external_ids`**: `wikidata_qid` and `enwiki_title` (the Prospector's rung 0; the daily
  refresh writes only for sites without a row).
* **`card_stats`**: the site's row - the zeroed placeholder the admin import writes for a new site
  (`plan.CARD_PLACEHOLDER`: the five stats, `total_power`, `rarity_score` and `rarity_tier` 0,
  `category_group = 'unknown'`; no card text) and the site's country as `civilization`. The
  card_stats lane and the card lane only UPDATE, so the row has to exist; the civilization is
  written because the card_stats lane fills no NULL (a placeholder without it would make the first
  wave that recomputes the site refuse its plan). 11 journal rows per site (`site_id` and the ten
  columns, `row_pk` the site id, `change_key = 'insert-site:<QID>:card:<column>'`).
* **`site_proposals`**: each open proposal naming the item or the article -> `approved`,
  `promoted_site_id`, `reviewed_by = 'remediation-d57'`, `reviewed_at`, `review_notes` (lane, D57,
  stamp, site), `updated_at`; journalled old -> new.
* **`user_contributions`**: the radar row such a proposal mirrors -> `enrichment_status =
  'promoted'`, `promoted_site_id` = the new site - what `POST /api/proposals/{id}/approve` does in its
  own transaction (`_mirror_contribution`), so the radar counts the place as added and never offers
  it for a second promotion; journalled old -> new (2 rows per contribution). The radar's counts
  follow within its 60 s cache TTL (`api/routes/radar.py:CACHE_TTL`).

Guards (before any write; `probe-guards` proves each): 1 no row holds the id or its page prefix; 2
no curated row holds the `source_record_id`; 3 no curated row holds the item or the article; 4 no
shown curated row carries the name key - as its name or as any of its `unified_site_names` (label,
alias, Wikidata alias: the Prospector's same-name rung) - within 50 km; 5 every name key is Postgres'
key; 6 every proposal still holds what the plan read and mirrors the same contribution; 7 a parent
is a shown curated site of the child's country within 5 km at depth one; 8 every radar contribution
still holds what the plan read (and is not `promoted`). Invariants (after the writes): the rows stand
as planned and **staged** - curated, retired with the planned reason, which begins `D57 staged:`
(`lane.d57_staged_sql`), and without a page (`curated_page` is false) -, the markers hash their
values, exactly the planned names and ids, the zeroed `card_stats` placeholder with the country as
civilization (no empires, no card text), the proposals approved for the site, the contributions
promoted to the site, the D25 parent invariants, exactly the planned journal rows per site.

**The card row and the API start.** `generator.backfill_placeholder_stats` recomputes every
`card_stats` row with `rarity_tier = 0` on each API start (every deploy), unjournalled. So the
read-back holds the card's journal rows to the plan always, and the row itself only while its
`rarity_tier` is still 0; a recomputed row is the generator's and no deviation. `readback` prints
a `NOTE` naming such rows and `accept` records them (`card_rows_recomputed` in `ACCEPTED.json`).
Run `apply`, `readback`, `rehearse-rollback` and `accept` in one sitting anyway. The next
card_stats wave reads past the creation's journal rows (`card_stats.created_cards`) and journals
every cell of the new cards that differs from its recompute, from the stored value - the
placeholder's, or what an API start made of it. A cell an API start already set to the recompute's
value gets no journal row: for that cell the journal ends at the insert's placeholder value.

**Each probe corrupts the temp table its guard reads** (`writer.probe_cases`): `_ins_site` for
guards 1-4 and 7, `_ins_name` for 5, `_ins_prop` for 6, `_ins_contrib` for 8. Probe 5 corrupts the
label's key in the name rows (`names[0]["name_key"]`) and leaves the site row's `name_key` alone: a
corrupted site key never reaches guard 5 and is refused only later by the invariant "rows", which
`probe-guards` counts as NOT PROVEN (fixed 2026-10-24 after review;
`test_every_probe_corrupts_the_table_its_guard_reads` renders every probe and compares its rows
with the real APPLY's in that table).

**The old-value guard rides on the two UPDATEs too.** `site_proposals` and `user_contributions` are
no target of `apply_remediation_change()`, so their UPDATEs carry what it carries: every value the
plan read is part of the UPDATE's own `WHERE` (`writer.proposal_held`, `writer.contribution_held`),
and the transaction raises (`writer.WRITE_SAYS`) unless the UPDATE changed exactly the planned rows
(`GET DIAGNOSTICS`). A founder who approves or merges a proposal in the admin UI between guard 6 and
the write stops the insert instead of being overwritten, and the journal's `old_value` is the value
the UPDATE replaced.

**The lint judges code, not text** (`writer.code_of`): comments and quoted literals are blanked in one
pass before it looks for `DELETE`, `TRUNCATE`, `DROP TABLE`, `ALTER TABLE` or a second
`BEGIN`/`COMMIT`, so a web quote in `raw_data` or `evidence` that says DELETE does not refuse a plan.
`plan` renders and lints both statements (`writer.render_checked`) **before** it writes any file of
the step: a statement the lint refuses leaves no PLAN.jsonl behind to block the next `plan`.

What the plan refuses (`REFUSALS.jsonl`, the owner list): `not-a-candidate`, `already-curated`,
`name-*`, `coordinates-*`, `country-*`, `source_url-*` (`-unresolved`, `-held`, `-exhausted`),
`country-disagrees` (the point is not in the country, D19's 2.5 km coast tolerance),
`name-twin` (a shown curated namesake within 50 km - D14's question), `scope-after-1500`,
`scope-d58-europe` (a start from 500 AD in a European country outside the Americas and Oceania),
`parent-missing|retired|depth|far`, `proposal-promoted` (a proposal approved or merged already),
`contribution-promoted` (the radar contribution a proposal mirrors is `promoted` or names a site: the
radar created a row for the place - D14's question, never a second row). A radar contribution in any
other state is promoted with its proposal, never a refusal. A type or a start nobody could source is
written empty (`Undated`) and listed in PLAN.md.

## 5. Undo: the rows stay retired, never deleted

The rows are written retired, so `ROLLBACK.sql` (written by `plan`, pinned to the plan, rehearsed by
`rehearse-rollback`) moves only each site's `scope_reason`, from the staged one to the undo's
(`D57 insert undone (...)`), through `apply_remediation_change()` (the scope lanes' write path) -
one journal row per site; `scope_status` is not touched. Without the staged reason no lane works on
the row and the scope lane's un-retire never shows it. It restores each closed proposal and each
promoted radar contribution to the values the plan read - one transaction, journalled under
`<run stamp>-rollback`.
It locks those rows first (`FOR UPDATE`), refuses unless they still hold what the insert wrote
(undo guards 2 and 3), restores only from those values (the same condition in the UPDATE's `WHERE`,
the row count checked) and journals the values it replaced. The names, ids and the `card_stats` row
stay with the retired row:
a retired site is hidden everywhere (its URL answers 410) but kept for matching, so the Prospector
does not propose it again. Undo guard 1 expects the staged pair (`retired`, the planned reason): once
the scope lane has shown a site, `ROLLBACK.sql` refuses as a whole, and a shown site leaves through
the scope lanes. Running it is a decision, never automatic:

```bash
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" \
  < output/remediation/insert_site/$R/step-001/ROLLBACK.sql
$I readback --run $R --step 1 --rollback
```

An undone insert never comes back by a second insert: the plan refuses an item a curated row holds,
retired or not. IndexNow announces neither the staged nor the undone rows as removed pages (they
never had one): its statement knows both reasons by their prefix (`public_sites.D57_STAGED_PREFIX`,
`D57_UNDONE_PREFIX`, which `writer.retire_reason` begins with).

## 6. After the accept: how the new sites reach every lane

`INSERTED_SITES.txt` (one site id per line) is the list the follow-up lanes take. The sites are
**hidden** until step 6 below; steps 3 to 5 run on hidden rows. The driver's order, checks and the
code each step still waits for are in the lane's playbook
(`output/remediation/final-2026-10-08/drivers/d57-insert/PLAYBOOK.md`).

1. **No page yet.** A staged row is retired: `curated_page` is false, so the SSR route answers 410
   for its URL, and the sitemap, the country hubs, the static export, the globe, the search and
   every card draw leave it out. The 12 closed proposals and the 5 promoted radar contributions name
   a site whose link answers 410 until step 6: keep the time short. **IndexNow**: the hourly cycle
   announces every curated site whose journal wrote `scope_status = 'retired'` in the last two
   hours as a removed page (`pipeline/indexnow.py`, `_RETIRED_SITES_SQL`), and the insert journals
   exactly that row. The statement leaves it out - the row that created the site (`old_value`
   NULL) while the site is staged or its insert was undone (`public_sites.d57_staged`,
   `d57_undone`) - but only in an image that holds this code: `pipeline/` ships in the Lyra image,
   so the change must be **pushed to `main` and deployed before `apply`**. The check (prints `1`):
   `ssh ancientnerds "docker exec ancient_nerds_lyra python -c 'import pipeline.indexnow as i;
   print(i._RETIRED_SITES_SQL)'" | grep -c "D57 staged"`.
2. **Read the hidden rows.** Every lane's population read drops a retired site. The lanes of steps
   4 and 5 admit a staged one - by the predicate `mechanical.lane.d57_staged_sql(alias)` (SQL) and
   the prefix `D57_STAGED_PREFIX` - and only where a `--sites` list names it:
   * lane WN: `wc/cli.py read` holds every row's `scope_reason` beside its `scope_status`, and
     `export --wn --sites F` asks a staged site F names (`cli.staged`). A WN run without the list,
     and every other kind of run (plain, site-list, lane E, the repair passes), lists it `retired`;
   * the picture research: `image_roles/run.py population --sites F` reads a staged site F names
     (`candidate_search.population.population_sql`); a population without the list, and D59's
     credit lane, never hold one;
   * the image INSERT lane: `import_hero/run.py read` holds the staged sites and their rows with
     the shown ones and not among the retired (`import_hero.read.IN_THE_READ`), so `insert-plan`
     plans the row of a staged site its claims name instead of refusing it as `retired`, and
     `insert-accept` answers from a fresh read (it opens no connection to the site's page, which
     still answers 410). Every site row of `READ.json` says which it is (`staged`; `staged_sites`
     in the read's summary), and the claims of a staged site come from the research alone: the
     2025 import's join (`plan`, and `fetch` in a run directory that holds no claims) leaves the
     staged sites out (`plan.join_import`), because no image role judged the import's picture -
     Pella and Nan Madol join a feature of the import by source URL (measured 2026-11-11). A read
     without the column is refused by name where that join asks.

   Nothing that shows a site reads the staged predicate: the page, the sitemap, the static export,
   the search and the card draws keep `scope_status IS DISTINCT FROM 'retired'`.
3. **Names in every language**: `docker exec ancient_nerds_api python -m
   pipeline.wikidata_name_backfill --apply` (it runs over every site with a QID; the constraint drops
   what exists).
4. **Description** (the insert writes none): lane WN of the WC tool, after a fresh
   `scripts/remediation/wc/cli.py read --run-dir R` made by this code (a read made by a checkout
   without the `scope_reason` column, whatever its date, cannot say whether a retired site is
   staged: the export refuses it by name, `the read holds no scope_reason for the retired site`) -
   `scripts/remediation/wc/cli.py export --run-dir R --handoff H --wn --sites INSERTED_SITES.txt
   --pilot 20 --seed S` - with the `description_sources` in `raw_data._insert_provenance` as the
   researcher's lead; the rest of the run and its write through lane WC's gate are
   `SENTENCE_CHECK.md` section 12. D22: a site that stays without a text gets no card and no Short.
5. **Pictures (D17)**: the population is every shown curated site with no image row and no
   `thumbnail_url` (`candidate_search/population.py`) and, named by its list, a staged one:
   `scripts/remediation/image_roles/run.py population --run-dir C --sites F`. The sites carry their
   item and article in `site_external_ids` and a sourced point (their `_coord_provenance`), so the
   geotag route searches around them. The rows go in through the INSERT waves of
   `WD2_SERVED_IMAGE_AND_SCOPE.md` section 3.7 (`judge_run.py insert-claims`, `import_hero/run.py
   read`, `fetch --target insert`, `insert-plan`, the writer's five steps, `insert-accept`).
6. **Go live**: the scope lane's journalled un-retire, class "D57 staged"
   (`WD2_SERVED_IMAGE_AND_SCOPE.md` section 2.2): `mechanical/scope_unretire.py export`, then
   `write --wave <label>`, then `apply.py --lane scope-unretire-<label>` through its steps. A
   staged site comes back when its description is not blank and hashed by its check record or its
   provenance, and it has exactly one live hero row whose file its `thumbnail_url` names; premise
   and invariant hold both. A site that ends without text or picture stays hidden, is listed in
   the wave's `SKIPPED.jsonl` (`d57-no-description`, `d57-no-picture`) and goes on the owner list.
   Then the static export (`docker exec ancient_nerds_api python -m api.services.rebuild_static`,
   `scripts/remediation/static_export_check.py` in the API container; PROJECT_LESSONS: never as
   root) and IndexNow: the hourly cycle announces a shown site only when one of its page columns
   was journalled in the last two hours, and the un-retire writes none - submit the new URLs by
   hand when the image wave is older (`pipeline.indexnow.paths_for`, `page_url`, `submit`).
7. **Cards (WB, D53 judge)**: every new site has its `card_stats` row from the insert. A card_stats
   wave (`mechanical/card_stats.py --wave <label>`) computes the stats of each site with a
   description: its basis stays the last wave's (the creation's journal rows name none), its
   counterfactual treats a site whose journalled insert lies after the basis horizon as absent at
   the basis (`counterfactual_sites`), and the new sites count in the recompute's `mystery` shares,
   as the generator counts them. Then `scripts/remediation/teaser/run.py select --sites ...` over
   the shown sites (lane WB reads only shown sites). Never `python -m api.cardgame.generator`,
   which rewrites every card unjournalled.
8. **Identity**: D25 for the reverse relations (the new site as the parent of curated components:
   Ephesus Archaeological Museum, Miletus Ancient Theatre, Susa's Darius palace, KV62 under the
   Valley of the Kings) through the parent lane's own judges; D23's spoken name with the next
   discovery run (`identity/export.py` reads every shown curated site).

## 7. Known limits

* The SQL runs for the first time in the operator's rehearsal (there is no local Postgres). It was
  parsed offline by libpg_query (pglast 8.7, installed into a scratch directory, not the venv: the
  outer statements and the DO bodies of the apply, the undo and all eight probes, for a step with a
  radar-backed proposal, one with a plain proposal and one with none; re-run 2026-10-24 after the
  contribution, old-value and alias changes, and 2026-11-10 after the staged insert and the
  `card_stats` row, then with every statement inside the DO bodies parsed on its own), and the
  plan's read ran read-only against production on 2026-10-24. Types are not checked offline: the
  rehearsal is the first semantic check - also for the `card_stats` INSERT, whose column list and
  defaults (`empires` `'[]'::jsonb`, `empire_count` 0, no trigger) were read from production's
  catalog on 2026-11-10.
* The staged insert has not run: no step was planned, rehearsed or probed with this code (the
  builder had read-only access). The first `rehearse` and `probe-guards` are its first execution.
* A cell of a new card that an API start set to the recompute's value before the first card_stats
  wave is never journalled as a change (section 4): `apply_remediation_change()` refuses a write
  that changes nothing, and the lane has no journal-only row.
* The alias twin check (guard 4 and the plan's read) found no candidate refused on 2026-10-24: the
  37 labels and articles match curated names or aliases only far away (Antioch of Pisidia 500 km,
  Pella in Jordan 1,487 km, the Roman Circus of Merida 1,624 km).
* D58's "medieval Europe" is applied mechanically as a start from 500 AD in a country the frontend's
  continent map calls Europe; a Byzantine subject outside it (Anatolia) is a pinned exclusion, not a
  rule. No candidate falls in that band outside the Americas and Oceania.
* One step: the list holds 37 sites, under D8's 100.
