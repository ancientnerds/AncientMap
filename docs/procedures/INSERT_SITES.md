# D57: the insert lane - new Ancient Nerds Originals for the high-demand sites

Owner decision **D57** (2026-10-24): the 38 high-demand in-scope sites without a curated page, plus
Chaco Canyon, become Ancient Nerds Originals (`source_id = 'ancient_nerds'`: an SSR page, a card,
every lane) through a journalled insert lane - rehearsed, undone by retiring (never DELETE), the
matching `site_proposals` closed as `approved` with `promoted_site_id`, then description, fields,
images and card per ENRICHMENT_AUDIT. **D58** is the scope rule: only the medieval Old World of
Europe, Byzantium and the Vikings is out (L'Anse aux Meadows stays out). E8 (2026-10-08) is the
hand review the list comes from. This is the one sanctioned exception to ENRICHMENT_AUDIT's "only
the admin promotes to Originals".

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
#    answer, validate, import again; the plan refuses to run while a field waits

# 3. the plan (read-only production read): PLAN.jsonl, REFUSALS.jsonl, PLAN.md, STEP.json, ROLLBACK.sql
$I plan --run $R --step 1
#    D8: the pilot_judge (Opus xhigh) reviews PLAN.md and DECISIONS.jsonl of the step before the write

# 4. the write
$I emit              --run $R --step 1      # APPLY.sql, pinned; refused without this plan's ROLLBACK.sql
$I rehearse          --run $R --step 1      # COMMIT -> ROLLBACK on production, 0 journal rows after
$I probe-guards      --run $R --step 1      # 7 corrupted copies, each refused by its own guard
$I apply             --run $R --step 1      # the one write, then the read-back
$I readback          --run $R --step 1      # plan = journal = data, both ways
$I rehearse-rollback --run $R --step 1      # the undo's guards on the landed rows, rolled back
$I accept            --run $R --step 1      # ACCEPTED.json (0 deviations, once), INSERTED_SITES.txt
$I status            --run $R
```

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
  `edited_by = 'remediation-d57'`, `raw_data`, `scope_status = 'in_scope'`, `scope_reason` (D57,
  the stamp), `updated_at = now()`, `parent_site_id` (pinned components only). `description` and
  `thumbnail_url` stay NULL - their lanes write them.
* **`raw_data`**: `_insert_provenance` (D57, run, item, article, every field's decision, quotes and
  answerer, the description's sources), `_period_provenance` (`quote`, or `undated`) and
  `_coord_provenance` (`quote`) - the `field_prov` markers (D12/D19), each hashing its value.
* **`unified_site_names`**: the `label` row, and an `alias` row for each name (and alias) of a
  closed proposal whose key differs - what `POST /api/proposals/{id}/approve` writes.
* **`site_external_ids`**: `wikidata_qid` and `enwiki_title` (the Prospector's rung 0; the daily
  refresh writes only for sites without a row).
* **`site_proposals`**: each open proposal naming the item or the article -> `approved`,
  `promoted_site_id`, `reviewed_by = 'remediation-d57'`, `reviewed_at`, `review_notes` (lane, D57,
  stamp, site), `updated_at`; journalled old -> new.

Guards (before any write; `probe-guards` proves each): 1 no row holds the id or its page prefix; 2
no curated row holds the `source_record_id`; 3 no curated row holds the item or the article; 4 no
shown curated row carries the name key within 50 km; 5 every name key is Postgres' key; 6 every
proposal still holds what the plan read; 7 a parent is a shown curated site of the child's country
within 5 km at depth one. Invariants (after the writes): the rows stand as planned with a page
(`curated_page`), the markers hash their values, exactly the planned names and ids, the proposals
approved for the site, the D25 parent invariants, exactly the planned journal rows per site.

What the plan refuses (`REFUSALS.jsonl`, the owner list): `not-a-candidate`, `already-curated`,
`name-*`, `coordinates-*`, `country-*`, `source_url-*` (`-unresolved`, `-held`, `-exhausted`),
`country-disagrees` (the point is not in the country, D19's 2.5 km coast tolerance),
`name-twin` (a shown curated namesake within 50 km - D14's question), `scope-after-1500`,
`scope-d58-europe` (a start from 500 AD in a European country outside the Americas and Oceania),
`parent-missing|retired|depth|far`, `proposal-promoted`, `proposal-contribution`. A type or a start
nobody could source is written empty (`Undated`) and listed in PLAN.md.

## 5. Undo: retire, never delete

`ROLLBACK.sql` (written by `plan`, pinned to the plan, rehearsed by `rehearse-rollback`) moves each
site `in_scope -> retired` and its `scope_reason` to the undo's, through `apply_remediation_change()`
(the scope lanes' write path), and restores each closed proposal to the values the plan read - one
transaction, journalled under `<run stamp>-rollback`. The names and ids stay with the retired row:
a retired site is hidden everywhere (its URL answers 410) but kept for matching, so the Prospector
does not propose it again. Running it is a decision, never automatic:

```bash
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" \
  < output/remediation/insert_site/$R/step-001/ROLLBACK.sql
$I readback --run $R --step 1 --rollback
```

A retired insert comes back only through the scope lane (un-retire, journalled), never by a second
insert: the plan refuses an item a curated row holds, retired or not.

## 6. After the accept: how the new sites reach every lane

`INSERTED_SITES.txt` (one site id per line) is the list the follow-up lanes take.

1. **Page, sitemap, IndexNow.** The SSR page `/sites/{country}/{slug}` and the country hub serve the
   row at once (`curated_page`: curated, a country, not retired); the sitemap lists it; the hourly
   IndexNow cycle announces it (shown curated sites with journalled page writes,
   `pipeline/indexnow.py`). The API's list and search caches expire within 30 minutes (the longest
   TTL in `api/routes/sites.py`).
2. **Static export** (the globe's `public/data/sites/index.json`): `docker exec ancient_nerds_api
   python -m api.services.rebuild_static`, then `scripts/remediation/static_export_check.py` in the
   API container (PROJECT_LESSONS: never as root).
3. **Names in every language**: `docker exec ancient_nerds_api python -m
   pipeline.wikidata_name_backfill --apply` (it runs over every site with a QID; the constraint drops
   what exists).
4. **Description** (the insert writes none): the Phase-4 W lane once X10 is fixed, else lane WN of
   the WC tool - `scripts/remediation/wc/cli.py export --wn --sites INSERTED_SITES.txt` - with the
   `description_sources` in `raw_data._insert_provenance` as the researcher's lead. D22: a site that
   stays without a text gets no card and no Short.
5. **Pictures (D17)**: the population is re-derived at write time from every shown curated site
   with no image row and no `thumbnail_url` (`candidate_search/population.py`) - the new sites are in
   it, with their item and article from `site_external_ids` and a sourced point (their
   `_coord_provenance`), so the geotag route searches around them.
6. **Cards (WB, D53 judge)**: a new site has **no `card_stats` row** - the insert writes none, and
   both the card lane and the card_stats lane only UPDATE (`apply_remediation_change()`; the
   card_stats lane reports a missing row and writes nothing). So before its card: a journalled
   `card_stats` row per new site (an insert step that this lane does not have - the orchestrator's
   call; never `python -m api.cardgame.generator`, which rewrites every card unjournalled), then the
   card_stats wave computes its stats, then `scripts/remediation/teaser/run.py select --sites
   INSERTED_SITES.txt` after the description. The card_stats lane itself keeps working across the
   insert: its counterfactual treats a site whose journalled insert lies after the basis horizon as
   absent at the basis (`mechanical/card_stats.counterfactual_sites`), and the new sites count in
   the next recompute's `mystery` shares, as the generator counts them.
7. **Identity**: D25 for the reverse relations (the new site as the parent of curated components:
   Ephesus Archaeological Museum, Miletus Ancient Theatre, Susa's Darius palace, KV62 under the
   Valley of the Kings) through the parent lane's own judges; D23's spoken name with the next
   discovery run (`identity/export.py` reads every shown curated site).

## 7. Known limits

* The SQL runs for the first time in the operator's rehearsal (there is no local Postgres). It was
  parsed offline by libpg_query (pglast 8.7: the outer statements and the DO bodies of the apply, the
  undo and all seven probes), and the plan's read ran read-only against production on 2026-10-24.
* D58's "medieval Europe" is applied mechanically as a start from 500 AD in a country the frontend's
  continent map calls Europe; a Byzantine subject outside it (Anatolia) is a pinned exclusion, not a
  rule. No candidate falls in that band outside the Americas and Oceania.
* One step: the list holds 37 sites, under D8's 100.
