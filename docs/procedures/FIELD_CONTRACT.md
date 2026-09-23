# Field contract for the site remediation

Status: **active**, written 2026-09-20 from verified source reads. Applies to every write made
by the 2026-09 remediation of the 5,004 `ancient_nerds` sites
(`docs/procedures/SITES_DB_REMEDIATION_2026-09.md`).

Read this before writing anything. A value that is correct in the database can still be wrong
*ten minutes later*, because two code paths in this project rewrite site data on every container
start. This file says which fields those are, what makes a written value survive them, and what
shape each column accepts.

---

## 1. The only supported write path

Every remediation write goes through one function, added in `migrations/0017_remediation_change_log.sql`:

```sql
SELECT apply_remediation_change(
    'unified_sites', 'country', 'id', '<uuid>',
    '<expected current value>', '<new value>',
    'T05/country-compounded', '2026-09-20_remediation',
    '<change_key>', 'authoritative', '<evidence jsonb>'::jsonb, '<site uuid>');
```

It is verified to have these properties (all seven asserted by
`scripts/remediation/0017_migration_selftest.sql`, run green against a scratch database on
2026-09-20):

1. **Conditional WHERE.** The update only applies if the row still holds the exact expected old
   value, compared with `IS NOT DISTINCT FROM` rather than `=` — so correcting a field that is
   currently `NULL` works (`col = NULL` is never true, which would silently match zero rows).
2. **Aborts instead of guessing.** If the row does not hold the expected value, or the primary key
   matches no row, it raises. A correction based on a stale reading is never applied.
3. **Journals atomically.** The value change and its `remediation_change_log` row commit together in
   one statement, so the audit trail cannot disagree with the data.
4. **Reversible.** `old_value` is recorded for every change; `remediation_change_history` exposes
   the preceding value per row.
5. **Table allowlist.** Only `unified_sites`, `card_stats`, `wiki_images`, `site_content_links`,
   `site_external_ids`, `unified_site_names` can be written. Anything else raises.
6. **`run_stamp` required**, so no change can exist without naming the run that made it.
7. **`p_new = NULL` clears a field** and still records what was there.

Non-negotiable consequences:

- **No `DELETE`, ever.** Out-of-scope or unusable rows are flagged or cleared, never removed.
  (Owner decision E1.)
- **No `UPDATE ... SET x = y` by hand**, and no `psql -c "UPDATE ..."` in a loop. An unjournalled
  write to this data is not recoverable by review, only by restoring the dump.
- Scoped tables hold **1,759,676 rows across 28 sources**; `ancient_nerds` is 5,004 of them. The
  UUID primary key makes each call row-exact, but never write a query that filters on a *value*
  without also naming the source.

---

## 2. The restart rule: a written value must be a fixed point

Two code paths re-derive site data on **every** start of the Lyra orchestrator or the API. There is
no opt-out flag. Only the `WHERE ... IS DISTINCT FROM` guard limits how many rows they touch.

### 2.1 `unified_sites.site_type` — normalizer-run

`pipeline/lyra/orchestrator.py:1476-1488`, inside `_run_migrations()` (called from `main()` at
`:1990`, so once per orchestrator start):

```python
_raw_types = conn.execute(
    text("SELECT DISTINCT site_type FROM unified_sites WHERE site_type IS NOT NULL")
).fetchall()
for (raw,) in _raw_types:
    canonical = _norm_type(raw)
    if canonical != raw:
        conn.execute(
            text("UPDATE unified_sites SET site_type = :canonical WHERE site_type = :raw"),
            {"canonical": canonical, "raw": raw},
        )
```

**Rule:** any `site_type` you write must satisfy `normalize_site_type(value) == value`
(`pipeline/normalizers/site_type.py`). Otherwise the next container start rewrites it. An
unmappable value is therefore not a correction at all — it is a temporary edit that reverts itself,
which is why `t04_site_type.py` asserts this as an invariant and emits `Proposal.REVIEW` for
anything it cannot place.

Measured 2026-09-20: all 97 canonical types are fixed points, and the only non-canonical value
present in production is `suspect_modern` (1 site), which the check deliberately skips.

`user_contributions.site_type` is normalized the same way (`:1490-1502`) — irrelevant to this
remediation but part of the same rule.

### 2.2 `unified_sites.name_normalized` — and the trap in its own WHERE clause

`pipeline/lyra/orchestrator.py:1694-1702`:

```sql
UPDATE unified_sites
SET name_normalized = left(lower(unaccent(name)), 500)
WHERE name_normalized IS NULL
   OR name_normalized IS DISTINCT FROM lower(unaccent(name_normalized))
```

The `SET` derives from **`name`**; the `WHERE` compares against **`name_normalized`**. That
asymmetry is the whole story:

- A written value survives **iff** `value = left(lower(unaccent(value)), 500)` — i.e. it is already
  normalised and at most 500 characters.
- If it is not, the row is rewritten from `name`, and the value is gone.

So a `name_normalized` that is a normalisation fixed point persists **even when it does not match
`lower(unaccent(name))`** — the guard never fires, so nothing corrects it. That is a footgun in both
directions: it means a wrong-but-well-formed value is durable, and it means "the normalizer will
clean it up for me" is false.

**Rule: write `left(lower(unaccent(name)), 500)` — the derivation the code intends — not merely some
fixed point.** That satisfies both the intent and the guard.

`unified_site_names.name_normalized` (`:1687-1692`) is re-normalised **in place** (from itself, not
from `name`), so its fixed point is the same condition, `value = left(lower(unaccent(value)), 500)`.
The same block (`:1679-1685`) deletes duplicate `unified_site_names` rows keeping the lowest id, so
inserting a duplicate name here is undone on the next start.

### 2.3 `card_stats.card_description` — the JSON file wins on every API boot

`api/main.py:493-552`, an unconditional startup import:

- Source: `public/data/card_descriptions.json`, key `descriptions`. A normal git blob, **not
  LFS** (`.gitattributes` puts `public/data/sites/*`, `*.geojson` and `*.json.gz` into LFS,
  not this file; `git check-attr filter` answers `unspecified`, verified 2026-09-23).
- Upsert at `api/main.py:527-531`:

```sql
INSERT INTO card_stats (site_id, card_description, ...)
VALUES (:id, :desc, 0, 0, 0, 0, 0, 0, 0, 0, 'unknown')
ON CONFLICT (site_id) DO UPDATE SET card_description = :desc
WHERE card_stats.card_description IS DISTINCT FROM :desc
```

- Truncated to 200 characters at `api/main.py:533`.

The `IS DISTINCT FROM` guard only prevents rewriting an identical value. It does **not** protect a
differing one — the JSON value overwrites the database value on every API start.

**Rule: never treat `card_stats.card_description` as the source of truth, and never fix a card text
in the database alone. Any Phase 5 correction must be applied to `public/data/card_descriptions.json`
*and* the database, or it is reverted at the next API restart.**

**The P5 order (2026-09 remediation, design entry [6], production_write step 3): the database
first, journalled; then the file, byte for byte; then the push - in one sitting.**

1. `scripts/remediation/phase4/card_json.py --prerender` renders the file the P5 plan leaves
   behind, from the plan alone, and it is committed locally (not pushed);
2. `output/remediation/tools/write_gate4.py --group P5 --apply --step 100` writes the cards through
   `apply_remediation_change` (journal row, conditional old value, read-back, inverse proof), with
   `verify_writes4.py` after every step;
3. `card_json.py --regenerate` renders the file again from a read-only production SELECT and
   passes only when it is byte for byte the pre-render;
4. Push #2 (owner), then 0 `[STARTUP] Card description overwritten` lines on both API containers
   and `card_json.py --check` (`ACCEPT_EXIT=0`).

**Pushing the file before the database write is forbidden**: the boot import would write the cards
without a journal, and the journalled write would then refuse every row with matched_0. A red CI
inside the sitting is answered by `scripts/remediation/phase4/revert4.py --stamp-like 'phase5:%'`
plus a `git revert` of the JSON commit. The full sitting is in `docs/procedures/CARD_DESCRIPTIONS.md`
("How a card reaches production").

For contrast, `api/routes/sites.py:1743-1751` deliberately does **not** overwrite — it uses
`card_description = COALESCE(EXCLUDED.card_description, card_stats.card_description)`. Two write
paths, opposite semantics; only the startup one is authoritative.

#### The carrier chain, and the decision not to change the importer

Measured 2026-09-20 in the api container: production's **4,996 card texts are byte-identical to
`public/data/card_descriptions.json`** (4,996 entries, 4,996 rows found, 4,996 identical,
`would_be_overwritten 0`). There is **no drift today**, and the reason is that the startup import
is the step which carries the file into the rows. It is a propagation mechanism, not an
overwriter — and §10.1 of the plan names it as a landmine for exactly that reason.

The chain is already wired end to end, which is why the importer's semantics stay as they are:

```
generation -> output/card_descriptions.json          <- gitignored, DOES NOT EXIST until generated
           -> scripts/import_card_descriptions.py    (reads :25, UPDATEs card_stats, copy2 -> public/ :58)
           -> commit + deploy
           -> api/main.py startup import             (the only path to an existing row)
```

`scripts/merge_rewrites.py:2` ("Merge rewrite outputs into card_descriptions.json, then
re-validate") is the other half of the same workflow.

**Neither is a remediation path** (2026-09-23): the P5 sitting above writes the rows through the
journal and renders the file with `card_json.py`; `import_card_descriptions.py` UPDATEs
`card_stats` without a journal row, and both carry a docstring saying so.

#### Step 1 does not exist by default - bootstrap it before Phase 5

Measured 2026-09-20: **`output/card_descriptions.json` is absent**; only the deployed
`public/data/card_descriptions.json` (1,098,379 B) exists. `scripts/import_card_descriptions.py:29-31`
fails closed on that, printing `Error: ... not found. Run card description generation first.` and
`sys.exit(1)`. So the workflow above is **broken at step 1** until the file is created - this was
found by the OVERWRITER lane after this section was first written, and the section was wrong.

The two files have the same shape, so the bootstrap is a copy. Verified contents of the deployed
file: exactly one top-level key `descriptions`, **4,996 entries**, UUID site_ids as keys, and a
**maximum value length of 200** - matching `varchar(200)` and the truncation at `api/main.py:533`.

```bash
cp public/data/card_descriptions.json output/card_descriptions.json   # then edit output/ and run:
./.venv/Scripts/python.exe scripts/import_card_descriptions.py
```

Running the script is what updates the database *without* waiting for a restart, and its
`shutil.copy2` is what refreshes the file the API loads. Editing `public/data/card_descriptions.json`
directly also works, since that is the file the startup import reads - but then the DB follows only
at the next boot, and the copy step is skipped.

#### The generator that feeds this chain cannot fail, and cannot notice that it did nothing

Measured 2026-09-20 by **running** `scripts/merge_rewrites.py` in a faithful sandbox - its paths
derive from `__file__`, so a whole tree was recreated around a copy of it, with a stub verifier that
exits 3:

| scenario | exit code | what it actually did |
|---|---|---|
| all 10 `rewrite_output_*.json` missing (**today's state**) | **0** | printed `WARNING: Missing batch files: [0..9]`, applied 0, and **still wrote `public/data/card_descriptions.json`** |
| a batch present but every rewrite invalid | **0** | printed `Validation errors (3)`, applied 1, skipped 1 |

Four defects of one kind - a command that reports success without having succeeded:

1. **It cannot fail.** `sys.exit` appears **0 times** in the file, and the verifier's exit code is
   never read (`returncode` appears **0 times**). The subprocess may fail completely and the script
   still exits 0.
2. **Missing batch files are a `WARNING`, not a failure.** A Phase-5 run that forgot to generate its
   batches is indistinguishable from a successful one.
3. **Validation errors are printed and then ignored.** The apply loop's only condition is
   `sid in descs and len(new_desc) <= 200` (`:78`); it never consults the `errors` list. A rewrite
   rejected as `BAD ENDING` is applied anyway. Only the >200 case is filtered, and only by accident.
4. **Even the do-nothing run overwrites** the deploy-relevant
   `public/data/card_descriptions.json`.

**Status: fixed - `merge_rewrites.py` fails closed** (its docstring, "WHY THIS SCRIPT IS WRITTEN
THIS WAY"; `tests/remediation/test_merge_rewrites_fails_closed.py`): all ten batches present, every
rewrite valid, at least one applied, the count unchanged and the re-validation not worse - or it
exits non-zero and writes nothing to `public/data/`. The table above is the defect as measured
before the fix.

**Consequence for the bootstrap above:** copying the public file back makes
`import_card_descriptions.py` usable, and it also makes `merge_rewrites.py` runnable - which is what
makes its silent no-op reachable. **Do not trust its exit code.** Before Phase 5, assert
`Applied N rewrites` with N > 0 and confirm the public file actually changed. `verify_descriptions.py`
contains no `sys.exit` either, which independently supports the plan's decision to retire it as a
gate.

**Rejected alternatives, recorded so they are not re-litigated.** Writing only into a NULL or
empty target kills this chain — an edited file could never reach a row that already holds text.
Guarding the import against site_ids recorded in migration 0017's `remediation_change_log` would
give production API boot code a permanent dependency on a table that exists for one audit; a
`to_regclass` guard is a band-aid over that coupling, not a fix.

**What was done instead:** the import keeps file-authoritative semantics and gains logging of
every discarded non-empty value (site_id and both values), so a reverted remediation write is
visible at boot rather than silent. The remediation is then made correct **by construction**
rather than by a guard — which is what the rule above already demanded.

---

## 3. Column shape: what a proposed value must fit

Verified against `information_schema.columns` on production, 2026-09-20. A value that violates these
is either truncated silently or rejected — so the census must not propose one.

| Table | Column | Type | Limit | Nullable |
|---|---|---|---|---|
| unified_sites | `name` | varchar | **500** | no |
| unified_sites | `name_normalized` | varchar | **500** | yes |
| unified_sites | `site_type` | varchar | **100** | yes |
| unified_sites | `country` | varchar | **100** | yes |
| unified_sites | `period_name` | varchar | **100** | yes |
| unified_sites | `period_start` / `period_end` | integer | — | yes |
| unified_sites | `lat` / `lon` | double precision | — | **no** |
| unified_sites | `description` / `source_url` / `thumbnail_url` | text | — | yes |
| unified_sites | `edited_by` | varchar | **20** | no |
| unified_sites | `raw_data` | jsonb | — | yes |
| card_stats | `card_description` | varchar | **200** | yes |
| card_stats | `civilization` | varchar | **100** | yes |
| card_stats | `rarity_tier` | integer | — | **no** |
| card_stats | `heritage_designation` | text | — | yes |
| card_stats | `inception_year` | integer | — | yes |
| wiki_images | `width` / `height` / `thumb_width` / `file_size_bytes` | integer | — | yes |
| wiki_images | `is_hero` / `is_lead` / `is_excluded` | boolean | — | no |
| wiki_images | `sort_order` | integer | — | no |

Notes that follow from the table:

- **`edited_by` is only 20 characters.** It is the provenance marker (`'audit'`,
  `'cited_enrichment'`, `'QuetzalcoatlCat'`, `'initial'`). `'remediation-2026-09'` is 18 and fits;
  anything longer fails. Do not invent a marker that does not fit.
- **`lat`/`lon` are `NOT NULL` and `double precision`.** They can be corrected, never cleared.
- **`card_description` is 200 characters**, and the startup import truncates to 200 as well. A
  longer generated text is silently cut, so a card-text fix that relies on the tail of a sentence is
  a fix that will not appear.
- **`wiki_images` boolean/int columns are `NOT NULL`** — `is_hero` can be moved, not nulled.

---

## 4. What this means for the census

The ten Phase-1 checks run against the local snapshot and may propose values. Every proposal must be
read through this contract before it becomes a write:

1. **`site_type` proposals** must be fixed points of `normalize_site_type()`. Anything else is a
   revert-on-restart edit — emit `REVIEW` instead. (Enforced in `t04_site_type.py`.)
2. **`name_normalized` proposals** must equal `left(lower(unaccent(name)), 500)`.
3. **`card_description` proposals** are never a database-only fix. Phase 5 writes the rows through
   the journal *and* renders the file from the same plan, in the order of section 2.3 - a plan that
   only writes SQL is reverted at the next boot, a file pushed first writes without a journal.
4. **Value proposals must fit the column**, checked before the proposal is made, not at write time.
5. **`country` and `site_type` are `varchar(100)`** — a compound value like `"Chile, Easter Island"`
   fits, but the replacement must also fit.
6. **Coordinate proposals** are the highest-risk: `lat`/`lon` are not nullable, and a wrong
   coordinate moves a dot on a globe rather than merely looking wrong. Disagreements with Wikidata
   or Natural Earth are `REVIEW`, never an automatic overwrite.

---

## 5. Related

- `docs/procedures/SITES_DB_REMEDIATION_2026-09.md` — the plan; §1.2 holds owner decisions E1–E5.
- `docs/procedures/ENRICHMENT_AUDIT.md` — audit dimensions, anti-patterns, SQL conventions.
- `migrations/0017_remediation_change_log.sql` — the write primitive.
- `scripts/remediation/0017_migration_selftest.sql` — its seven verified properties.
- `scripts/remediation/census/tests/t04_site_type.py` — the fixed-point rule as executable code.
- `output/remediation/recon/schema-and-overwriters.md` — the recon this contract was verified
  against (three claims re-read at source on 2026-09-20 before this file was written).
