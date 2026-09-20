# Hero repair applied — Phase 2 item 1

Scope: the 5,004 curated sites (`unified_sites.source_id = 'ancient_nerds'`) in the production
database. One flag moved per site, no download, no DELETE, one transaction.
Written and applied **2026-09-20 23:45–23:49 +02:00** from this checkout.

## What changed

`is_hero` was `true` on the row whose local file is the 800 px `THUMB_WIDTH` derivative, so the
image a site serves as its hero (`og:image`, JSON-LD `image`, the LCP image) was no larger than a
gallery thumbnail. For 2,719 sites the site already had a 1600 px file whose Commons original is
genuinely large; the repair sets `is_hero = false` on the old row and `true` on that file.

| | rows | sites |
|---|---|---|
| `is_hero = false -> true` (the new hero) | 2,719 | 2,719 |
| `is_hero = true -> false` (the 800 px hero it replaces) | 2,719 | 2,719 |
| **total rows changed** | **5,438** | **2,719** |

The served image is picked with `ORDER BY is_hero DESC, is_lead DESC, sort_order`
(`api/routes/sites_html.py:111`, `pipeline/static_exporter.py:330`), so the new hero wins on the
first sort key. `is_lead` was deliberately left untouched.

## The rule (and which column decided)

A candidate must (a) not be the hero, not `is_excluded`; (b) be T10 tier `D` (clear) or `C`
(grey), never the suspect `A`/`B`; (c) have a **stored** size >= 1600x900; (d) have a cached true
Commons size (`output/remediation/cache/commons_imageinfo.json`, `status = ok`) >= 1600x900; and
(e) not be larger than that original (no upscale). Rank: tier `D` before `C`, then the largest
true Commons area, then the lowest image id.

Both this plan and the plan's own **3,264** read `wiki_images.width`/`height` — the row's stored
local derivative size. The plan's rule stops there; this plan requires the Commons truth as well,
because T09 measured the stored column larger than the original on 11,653 rows. The claim
reproduces exactly, split:

| | sites |
|---|---|
| repaired (both conditions hold) | 2,719 |
| refused, the stored size was the only witness | 276 |
| refused on the census's suspect tier alone (no size question) | 269 |
| no 1600 px candidate under either rule | 594 |
| **3,264** | 2,719 + 545 |

## Artifacts

| file | sha256 (first 16) | note |
|---|---|---|
| `PLAN.jsonl` | `5e0fafabbdb6180d` | 5,438 records, one per row to change |
| `PLAN.md` | `b5ac81f247bc683e` | rule, funnels, the 3,264 split |
| `SKIPPED.jsonl` | `6e0e3431b0a884c0` | 1,291 untouched sites with the reason per site |
| `ROLLBACK.sql` | `8a8c014294396bf3` | written 23:45:11, **before** APPLY.sql (23:48:54) |
| `APPLY.sql` | `33cbab582f830378` | the file that was applied, byte-for-byte |
| `REHEARSAL.sql` | `f036969e18f195f1` | APPLY.sql with `COMMIT` -> `ROLLBACK` |

`APPLY.sql` holds one `BEGIN`, 5,438 calls to `apply_remediation_change()` (the only write path,
migration 0017 as fixed by 0018), and one `COMMIT`. It contains no hand-written UPDATE against
`wiki_images` and no hand-written INSERT into the journal.

## Commands and results

```bash
# 1. plan (offline, no database)
cd scripts/remediation && ../../.venv/Scripts/python.exe -m hero_repair.plan --write
#   plan: 2719 promotions, 2719 demotions over 2719 sites
#   sites: 5004 curated, 4010 with images, 3858 hero rows, 152 sites with no hero flag
#   row verdicts: eligible 25617, tier-B-suspect 9501, original-too-small 8309,
#                 is-the-hero 3858, local-file-too-small 1741, excluded 659, commons-missing 6
#   wrote PLAN.jsonl (5438 records), PLAN.md, ROLLBACK.sql (5438 records), SKIPPED.jsonl (1291)

# 2. the deployed primitive is the type-safe body from migration 0018
../../.venv/Scripts/python.exe -m hero_repair.apply --check-primitive
#   apply_remediation_change(text, text, text, text, text, text, text, text, text, text, jsonb, uuid)
#   casts_value_to_column_type | casts_old_value | rereads_stored_value
#            t                |        t        |          t

# 3. rehearsal against production: the identical statement, COMMIT replaced by ROLLBACK
../../.venv/Scripts/python.exe -m hero_repair.apply --rehearse
#   NOTICE:  hero repair: 5438 row(s) changed and journalled over 2719 site(s)
#   BEGIN / CREATE TABLE / INSERT 0 5438 / DO / ROLLBACK
#   temp table _hero_plan left behind     | 0
#   journal rows for this run stamp       | 0
#   curated hero rows                     | 3858
#   curated sites with more than one hero | 0

# 4. before, read-only
../../.venv/Scripts/python.exe -m hero_repair.apply --verify
#   curated sites 5004 | sites with at least one image 4010
#   hero rows (curated) 3858 | sites with exactly one hero 3858 | sites with more than one hero 0
#   heroes outside the curated source 0
#   sites whose served image is narrower than 1600 px 3858
#   sites whose served image is shorter than 900 px   3671
#   journal rows for this run stamp 0 | journal rows for this test id 0

# 5. the write: one transaction, 5,438 rows
../../.venv/Scripts/python.exe -m hero_repair.apply --apply
#   NOTICE:  hero repair: 5438 row(s) changed and journalled over 2719 site(s)
#   BEGIN / CREATE TABLE / INSERT 0 5438 / DO / COMMIT
#   journal rows for this run stamp 5438 | curated hero rows 3858
#   curated sites with more than one hero 0

# 6. after, read-only (same file as step 4)
../../.venv/Scripts/python.exe -m hero_repair.apply --verify
#   curated sites 5004 | sites with at least one image 4010
#   hero rows (curated) 3858 | sites with exactly one hero 3858 | sites with more than one hero 0
#   heroes outside the curated source 0
#   sites whose served image is narrower than 1600 px 1139   (was 3858)
#   sites whose served image is shorter than 900 px   1041   (was 3671)
#   journal rows for this run stamp 5438 | journal rows for this test id 5438
```

`3,858 - 2,719 = 1,139`: every site whose served image is still narrower than 1600 px is a site
this plan refused to repair, none of them a site it touched.

## Journal cross-check

The 5,438 journal rows for `run_stamp = '2026-09-20_remediation'` were read back and compared
with `PLAN.jsonl`:

* journal rows not in the plan: **0**
* plan rows absent from the journal: **0**
* rows whose `old_value`/`new_value`/`site_id_ref` differ from the plan: **0**
* `table_name.column_name`: only `wiki_images.is_hero`
* `test_id`, `confidence`: only `T09/hero-not-best`, `authoritative`
* `change_key` == `hero-repair:<site_id>` for all rows
* 2,719 sites, exactly 2 rows each: 2,719 x `(false -> true)` and 2,719 x `(true -> false)`

## One hero per site: enforced, then observed

*Enforced* — inside the same transaction, before it could commit: every planned image is on a
curated site (guard 1), every planned image is on the site the plan names (guard 2), every
touched site has exactly one promotion and one demotion (guard 3), and after the loop every
touched site holds exactly one `is_hero` row, else the transaction raises.

*Observed* — in the database, before and after: 3,858 curated sites with exactly one hero, **0**
with more than one, 0 heroes outside `ancient_nerds`, and 152 sites with images and none
(unchanged: those were never in scope).

The first rehearsal caught a defect in that invariant check itself: it joined `_hero_plan` (two
rows per site) straight to `wiki_images`, counted each remaining hero twice, and refused a correct
repair with `2719 touched site(s) do not end with exactly one hero`. Fixed by driving the check
from `SELECT DISTINCT site_id`, and pinned by
`tests/remediation/test_hero_repair.py::test_the_one_hero_per_site_check_is_not_multiplied_by_the_plan_table`.
That failed run is also the atomicity evidence: it raised inside the transaction and left the
journal at 0 rows and the hero count at 3,858.

`ROLLBACK.sql` was rehearsed the same way against the post-apply state: all 5,438 conditional
updates matched the values the apply wrote (a mismatch would have raised), and the rehearsal was
rolled back. The reversal is executable, not just written.

## `is_lead` was deliberately not touched - and what that costs

The demoted rows keep `is_lead = true` (the re-index script wrote `is_lead = is_hero`), so two
rows per repaired site now carry a lead-ish flag. Every place that *picks* an image orders by
`is_hero DESC, is_lead DESC, sort_order` (`api/routes/sites_html.py:111,331`,
`api/routes/wiki_images.py:274`, `pipeline/static_exporter.py:330`,
`pipeline/video/shorts_export.py:199`), so the new hero wins on the first key and no consumer
selects on `is_lead` alone.

The one place that reads both flags is the popup gallery:
`ancient-nerds-map/src/services/imageService.ts:78` maps `isLeadImage: img.isLead || img.isHero`
and line 107 re-sorts by that single boolean. The sort is stable, both hero rows compare equal,
and the list arrives from the API already in `is_hero DESC` order - so `wikiImages[0]` (the
popup's `wikiHero`) is the new 1600 px file. `isLeadImage` appears nowhere else in the frontend
(checked), so the second true flag is invisible. Clearing `is_lead` on the demoted row would be a
second journalled change in a column this plan declares out of scope; it is recorded here rather
than done quietly.

## Backup relied on

`ssh ancientnerds`, `/var/www/ancientnerds/backups/2026-09-20_remediation/`:
`database_2026-09-20_remediation.dump` (654,604,671 bytes), plus per-table CSVs including
`wiki_images.csv.gz` (4.4 MB). `DRILL_REPORT.txt`: restore drill at 2026-09-20T20:28:59+02:00 into
a scratch database, `pg_restore exit=0`, `unified_sites 1759676/1759676 OK`,
`wiki_images 49693/49693 OK`, verdict "dump is restorable and matches production row-for-row".
(An earlier local check said "not found" because the dump lives on the VPS, not in this
checkout.)

## Not done here

* **The 545 rejected sites** (`SKIPPED.jsonl`) need a genuinely larger original (fetch or
  re-export) or a different image: 276 have only candidates whose stored size the Commons truth
  contradicts, 269 have only T10-suspect candidates.
* **The 152 hero-less sites** keep no hero flag: they serve their lowest-`sort_order` gallery
  file through the `is_lead DESC, sort_order` fallback, which is already a 1600 px local file.
  Planting a flag there would change which image the site serves with no size defect to justify
  it.
* **`HERO_WIDTH = 800` / `THUMB_WIDTH = 800`** are untouched: a *newly downloaded* hero still
  arrives at 800 px. Raising them is a code change with its own review; the flag move does not
  depend on it.
* **The static globe data** re-export: the API-rendered pages (country hubs, detail pages, the
  `og:image` / JSON-LD hero) read the database per request and pick up the change immediately;
  the checked-in JSON under `public/data/` is regenerated by `pipeline/static_exporter.py` and is
  not part of this write.
