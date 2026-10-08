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

`pipeline/lyra/orchestrator.py`, inside `_run_migrations()` (called from `main()`, so once per
orchestrator start):

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

`user_contributions.site_type` is normalized the same way (the next loop) — irrelevant to this
remediation but part of the same rule.

### 2.2 `unified_sites.name_normalized` — and the trap in its own WHERE clause

`pipeline/lyra/orchestrator.py`, inside `_run_migrations()`:

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

`unified_site_names.name_normalized` is re-normalised **in place** by the UPDATE that runs just
before the `unified_sites` one (from itself, not from `name`), so its fixed point is the same
condition, `value = left(lower(unaccent(value)), 500)`. The DELETE just before that removes
duplicate `unified_site_names` rows keeping the lowest id, so inserting a duplicate name here is
undone on the next start.

### 2.3 `card_stats.card_description` — the database is the one copy (D25, 2026-10-08)

Until D25 this was the field the JSON file won on every API boot: `api/main.py::lifespan` ran
`api/services/card_descriptions.py::import_card_descriptions`, an unconditional upsert of
`public/data/card_descriptions.json` over the column, so a database-only write was reverted at the
next API start and every card write had to be rendered into the file and pushed in the same sitting.

**Rule (since D25): the authoritative copy of a card text is `card_stats.card_description` in the
database.** Nothing re-derives it on a start: the boot import, `api/services/card_descriptions.py`,
`teaser.py card-file` and `phase4/card_json.py` are removed, the frontend and the static exporter
read the column. A card is written through the journal (`apply_remediation_change`, the mechanical
lanes `teaser-prov-sNNN` / `teaser-card-sNNN`, or `write_gate4.py --group P5`) and nothing else is
needed: no file, no push, no push lock (`docs/procedures/CARD_DESCRIPTIONS.md` section 5.5).

- This holds from the deploy of the push that removed the import. Before it the old rule is in force:
  the file wins on every boot, so a card write needs the file rendered and pushed at once.
- `public/data/card_descriptions.json` stays in the tree until that deploy is verified (the `commit`
  field of `http://localhost:8000/` on the VPS equals the pushed HEAD), and is then deleted by a
  later push. Never edit it; nobody reads it.
- `scripts/import_card_descriptions.py`, `scripts/merge_rewrites.py` and the `audit_enrich.py` Wave-4
  merge write that file or the database without a journal. They are not remediation paths.
- A new site needs a `card_stats` row to be drawable: a zeroed placeholder row
  (`rarity_tier = 0`) is filled in by the API boot's `backfill_placeholder_stats`
  (`api/cardgame/generator.py`), a row that does not exist at all by `generate_stats`.
- `api/routes/sites.py` writes the column with `COALESCE(EXCLUDED.card_description,
  card_stats.card_description)`: it never clears a value.

The history (the 4,996 card texts byte-identical to the file on 2026-09-20, the carrier chain, the
P5 sitting's order "database, file, push", the defects of `merge_rewrites.py`) is in the git history
of this file and in `output/remediation/AUDIT_LOG.md`.

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
| unified_sites | `scope_status` | text, CHECK `unified_sites_scope_status_vocab`: NULL, `in_scope`, `retired`, `pending` (migration 0020; read 2026-09-26) | — | yes |
| unified_sites | `scope_reason` | text (free text; the lanes write `E3: ...` or `duplicate_of:<id>`) | — | yes |
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
- **`geom` (`geometry(Point,4326)`) does not follow `lat`/`lon` by itself**: no trigger exists on
  `unified_sites` (read on production 2026-09-26, PostGIS 3.4.3). A writer that moves a point sets
  `geom` to `ST_SetSRID(ST_MakePoint(lon, lat), 4326)` in the same transaction - WD1's cell lane
  does it and checks it as a site invariant (`docs/procedures/FIELDS_WD1.md`).
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
3. **`card_description` proposals** are written through the journal (section 2.3): since D25 the
   database is the only copy, so a journalled SQL write stands - no file follows it.
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
- `docs/procedures/FIELDS_WD1.md` — lane WD1 (2026-09-26): coordinates, period_start/period_name,
  site_type and source_url, sourced or emptied (owner decision O6), written as journalled cell-lane
  steps of 100 sites.
- `output/remediation/recon/schema-and-overwriters.md` — the recon this contract was verified
  against (three claims re-read at source on 2026-09-20 before this file was written).
