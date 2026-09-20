# Mechanical country repair — what was applied

**Written 2026-09-21. 35 rows, one column (`unified_sites.country`), one source
(`source_id = 'ancient_nerds'`).** Run stamp `2026-09-21_mechanical-country`, journal test id
`T05/country-canonical`, `applied_by = ancient_map`, confidence `authoritative`.

Producer: `scripts/remediation/mechanical/plan.py` (derive, refuse, emit `PLAN.jsonl`, `PLAN.md`,
`SKIPPED.jsonl`, `ROLLBACK.sql`) and `scripts/remediation/mechanical/apply.py` (render, rehearse,
probe, apply, verify). The write went through `apply_remediation_change(...)` (migrations/0017+0018)
in one transaction. Nothing was deleted.

Evidence for every number below: `output/remediation/mechanical/evidence/` (also on the VPS at
`/var/www/ancientnerds/backups/remediation-evidence/mechanical-country/` — 20 files, 520 KB, lane-scoped:
the shared directory holds the hero lane's files and was not touched).

---

## 1. The set: 35 rows, not the worklist's 27

**This is the first thing to read.** `output/remediation/phase3_worklist/MECHANICAL.md` lists **27**
sites; this lane wrote **35**. The difference is not an error and not a reconciliation — the two
files answer different questions:

| | definition | count |
|---|---|---|
| `MECHANICAL.md` | `mechanically_settable AND NOT phase3` — the mechanical repairs *Phase 3 does not have to revisit* | 27 |
| the census's own predicate | T05 `applicable = true` | **35** |

`output/remediation/run_t05/findings.jsonl` holds 70 findings over 70 distinct sites — one T05 row
per site (28 `spelling-split`, 27 `disambiguated`, 8 `compound`, 4 `vocabulary-gap`, 2
`official-long-form`, 1 `not-a-country`). **35** of them are `applicable = true` (all `proposal =
set`, `confidence = authoritative`):

* **27** `T05/disambiguated` — `Georgia (country)` → `Georgia`
* **8** `T05/compound` — `Chile, Easter Island` → `Chile`

The 8 leave the shortlist through a **second, independent flag — not through a different country
finding.** In `output/remediation/phase3_worklist/WORKLIST.jsonl` all 35 are
`mechanically_settable = true`; of those, **8 are additionally `phase3 = true`** and 27 are not:

```
mechanically_settable in the worklist: 35 | of them phase3: 8 | not phase3: 27
```

`MECHANICAL.md` filters on `mechanically_settable AND NOT phase3`, which is where its 27 come from.
Those 8 are Phase 3's for *other fields* — measured per site from the worklist:

| site | the non-applicable finding that makes it Phase 3 |
|---|---|
| Armazi | `lat/lon` and `name` (D3-LOCATION / D4-NAME) |
| Kutaisi, Easter Island, Didnauri, Satsurblia Cave | `lat/lon` (D3-LOCATION / D4-NAME) |
| Dmanisi | `description` (period / description text) |
| Tsona Cave, Tsutskhvati Cave Natural Monument, Satsurblia Cave | `card_description` (period / description text) |

The `country` finding of those 8 is identical in kind to the 27's: same field, same test, same
`applicable = true`, same `proposal = set` / `confidence = authoritative`. Nothing about the country
value says "Phase 3"; the site's other fields do.

Owner decision **B** (2026-09-21): write all 35. Writing 27 would have created a new defect — one
country split across two hub slugs (§3 measures it). The three conditions attached to that decision
are §2 (canonical value), §3 (the measurement) and this section (the 8 stay in the worklist).

**The 8 keep their place in the Phase-3 worklist.** `country` is not a field Phase 3 owns; their
T01/T03 findings are untouched and remain Phase 3's work. This lane wrote `country` and nothing else
for them:

| site | site id | written |
|---|---|---|
| Armazi | `21660e33-c3b7-462f-aaec-cbaded7b4a8d` | `Georgia (country)` → `Georgia` |
| Kutaisi | `2f8f4a6f-2480-49a1-ae22-23ad1102f77d` | `Georgia (country)` → `Georgia` |
| Satsurblia Cave | `31860bc4-476a-49bc-9f97-e25220063d19` | `Georgia (country)` → `Georgia` |
| Didnauri | `593de422-8bfc-4101-8e13-3db406830e60` | `Georgia (country)` → `Georgia` |
| Dmanisi | `5d97461b-02b7-4227-8918-bc6c80a531ac` | `Georgia (country)` → `Georgia` |
| Easter Island | `baf13030-1578-4edc-a351-ca627828a326` | `Chile, Easter Island` → `Chile` |
| Tsutskhvati Cave Natural Monument | `c254f03d-ccce-4588-8094-5a11fbe67b6f` | `Georgia (country)` → `Georgia` |
| Tsona Cave | `c30712db-a675-4203-a442-cb3f9b1c5848` | `Georgia (country)` → `Georgia` |

(These are the 8 rows `PLAN.jsonl` marks `phase3: true`, in site-id order. The per-row truth is
`PLAN.jsonl`; the T01/T03 findings of these sites are **not** copied into this lane's journal
records — they stay in `output/remediation/phase3_worklist/` and in the census output, which is where
Phase 3 reads them. What this lane leaves for Phase 3 is the `country` write and the `phase3: true`
mark, nothing more.)

**Re-derivation, not the worklist's word.** Each of the 35 values was re-derived from the source the
evidence names, never copied from T05's proposal:

1. reduce the stored value to a plain country — hint regex (`… (country|state|nation|republic)`) or
   the comma part that **both** project vocabularies know **and** Natural Earth carries as its own
   feature (`Chile, Easter Island` → `Chile`: `Easter Island` is `CL` in *both* vocabularies, so the
   tie-break is Natural Earth's own feature list, not a judgement);
2. `canonicalize_country_display_name(plain)` must **equal** T05's proposal, else refuse (§2);
3. ISO-2 unchanged; 4. the value is a key of the frontend's country vocabulary; 5. the point is
   inside the Natural Earth polygon (or ≤ 1000 m from it — Ahu Nau Nau is 0.6 km from Chile's
   boundary, Easter Island being a Pacific territory); 6. the Wikidata `P17 → P297` witness does not
   contradict (rank-aware: only `preferred` claims are decisive, so Georgia's `Soviet Union` /
   `Russian Empire` normal-rank history does not refuse anything); 7. the value is a fixed point of
   the same canonicalisation; 8. the value is NFC, ≤ 100 characters, no control characters or
   whitespace. 34 of 35 carry a Wikidata witness; the one without (Kudaro) states no `P17` at all,
   recorded as a gap in `PLAN.jsonl` rather than silently passed.

`output/remediation/mechanical/PLAN.md` is the reviewable rendering; `SKIPPED.jsonl` holds the other
35 T05 findings (all `finding-not-applicable`) with the measurement that refuses each one.

## 2. Condition (b): the written value is the project's own canonical string

Every row passes `canonicalize_country_display_name(reduced) == proposal`; a row where the project's
own normalisation disagrees with T05 is refused as `canonicalisation-differs-from-proposal`.
**Refusals of that kind: 0** — so the two written strings are the project's canonical strings by the
project's own function. Measured (`evidence/12_canonical_form.txt`):

```
stored  'Georgia (country)'   canonicalize_country_display_name -> 'Georgia (country)'   (not a fixed point)
        'Georgia'             canonicalize_country_display_name -> 'Georgia'             equals the proposal: True
        getCountryCode: stored 'GE', written 'GE';  normalize_country: 'GE' / 'GE'
stored  'Chile, Easter Island' canonicalize_country_display_name -> 'Chile, Easter Island'
        'Chile'               canonicalize_country_display_name -> 'Chile'               equals the proposal: True
        getCountryCode: stored 'CL', written 'CL';  normalize_country: 'CL' / 'CL'
```

Two consequences worth naming. The normaliser does **not** strip a parenthetical hint (it returns
`'Georgia (country)'` unchanged), so the reduction has to come from the hint rule — the normaliser
alone would have refused everything. And the *flag* was never the defect: `countryFlags.ts:289` maps
`Easter Island` → `CL`, so the old value already produced the right flag code. What is wrong is the
hub slug and the globe filter (below), not the flag.

## 3. Condition (c): the hub split, measured (not asserted)

`api/routes/sites_html.py:75-96` matches the hub by `country_slug(row.country)`; `country_slug` is
`pipeline.sites_html_renderer.country_slug` (imported at `api/routes/sites_html.py:25`, i.e. the
route and this measurement call the same function). From the database, before and after the write
(`apply.py --interests`, `evidence/01_interests_before.txt` / `07_interests_after.txt`):

| country value | slug | rows before | rows after |
|---|---|---|---|
| `Georgia (country)` | `georgia-country` | 27 | **0** |
| `Georgia` | `georgia` | 3 | **30** |
| `Chile, Easter Island` | `chile-easter-island` | 8 | **0** |
| `Chile` | `chile` | 3 | **11** |

`country_slug('Georgia (country)') = 'georgia-country'` vs `country_slug('Georgia') = 'georgia'`;
`country_slug('Chile, Easter Island') = 'chile-easter-island'` vs `country_slug('Chile') = 'chile'`.
Distinct curated country values: **98 → 96** (two values retired, none invented).

**The counterfactual that decided the scope:** had only the 27 been written, `/sites/georgia` would
hold 3 + 20 = 23 rows and `/sites/georgia-country` 7, and `/sites/chile` 10 against
`/sites/chile-easter-island` 1 — one country, two hubs, halfway migrated. That is a state no rule
produces, which is why the 8 are written here.

## 4. The statement, and why the rollback came first

`ROLLBACK.sql` (delivered) is dated **before** `APPLY.sql`, and `apply.py --emit` raises if
`ROLLBACK.sql` is absent — the reversal is a generator product, never hand-typed. Both are rendered
from the same `PLAN.jsonl`; `evidence/11_fingerprints.txt` shows that re-rendering either file from
the delivered plan with the delivered code produces a **byte-identical** file:

```
APPLY.sql:    0 differing line(s); byte-identical True   (77332 bytes, sha256 0e2cb32716c0c2a1…)
ROLLBACK.sql: 0 differing line(s); byte-identical True   (76977 bytes, sha256 df1bf7b0c18e73b2…)
```

Shape of `APPLY.sql` (154 lines):

* `\set ON_ERROR_STOP on` + `BEGIN;`
* `CREATE TEMP TABLE _country_plan (site_id UUID PRIMARY KEY, old_value, new_value, change_key,
  reason, evidence JSONB) ON COMMIT DROP;` + one `INSERT … VALUES` tuple per row (35);
* `DO $$ … $$` containing **three scope guards, then the only writer, then two invariants**:
  1. every planned row exists and is `source_id = 'ancient_nerds'` — raise otherwise (the table holds
     1,759,676 rows over 30 sources, measured 2026-09-21);
  2. every planned row is a real change that fits the column (`length ≤ 100`);
  3. every planned row still holds the old value the plan names (`IS DISTINCT FROM`);
  4. `FOR r IN SELECT * FROM _country_plan ORDER BY site_id LOOP … apply_remediation_change(
     'unified_sites','country','id', r.site_id::text, r.old_value, r.new_value, …)`;
  5. invariant: each planned row now holds the new value, and the count of changed rows equals the
     count of planned rows;
  6. invariant: the journal and the data agree **row for row in both directions** for this run stamp,
     and this run stamp journalled nothing outside `unified_sites.country`;
* `COMMIT;` then the post-commit reads.

**Deviation from the brief's literal wording, stated plainly:** the transaction has **one
`apply_remediation_change(` call site**, not 35 literal calls — it is a loop over the 35-row temp
table. The invariant that `moved = expected` plus the post-commit reconciliation (§6, all 35 rows
present exactly once, old and new values matching) is what proves all 35 rows were visited. If the
review wants 35 literal calls, that is a rewrite of `render_transaction`, not a behaviour change.

## 5. Rehearsal before the write (byte-identical, `COMMIT` → `ROLLBACK`)

`apply.py --rehearse` runs the delivered statement with `COMMIT;` swapped for `ROLLBACK;` and reads
what must not change (`evidence/03_rehearsal_apply.txt`):

```
NOTICE:  country repair: 35 row(s) changed and journalled over 35 curated site(s)
BEGIN / CREATE TABLE / INSERT 0 35 / DO / ROLLBACK
 journal rows for this run stamp          | 0
 curated rows still holding the old value | 35
 curated sites                            | 5004
 temp table _country_plan left behind     | 0
```

So the whole path — guards, 35 writes, journal, invariants — ran against production and left
nothing: the journal had 0 rows for the run stamp afterwards and all 35 rows still held the old
value. The reversal was rehearsed the same way, **after** the write, from the state the write left
behind (`--rehearse-rollback`, `evidence/09_rehearsal_rollback.txt`):

```
NOTICE:  country repair: 35 row(s) changed and journalled over 35 curated site(s)
 journal rows for the rollback stamp          | 0
 planned rows still holding the written value | 35
 curated sites                                | 5004
 temp table _country_plan left behind         | 0
```

## 6. The write, and the read-back from the database

`apply.py --apply` (`evidence/05_apply.txt`): verify → the statement → verify again. The transaction
committed once; all 35 journal rows share a single `applied_at`
(`2026-09-20 22:42:50.695778+00` … `2026-09-20 22:42:50.695778+00`, UTC), which is what one
transaction looks like in the journal.

**Before → after, read from `unified_sites` (not from the plan):**

| metric | before | after |
|---|---|---|
| `country = 'Georgia (country)'` | 27 | **0** |
| `country = 'Georgia'` | 3 | **30** |
| `country = 'Chile, Easter Island'` | 8 | **0** |
| `country = 'Chile'` | 3 | **11** |
| distinct country values (curated) | 98 | 96 |
| curated sites | 5004 | 5004 (nothing deleted) |
| curated rows whose country is NULL/empty | 0 | 0 |
| curated rows with a parenthetical or comma country | 35 | **0** |

**Journal reconciliation, read back from the database afterwards** (raw SQL, `evidence/08_reconcile.txt`):

```
log rows for my run stamp                   | 35
distinct site rows journalled               | 35
distinct stamps for my test id              | 1
table.column pairs in my run                | unified_sites.country
value mismatches (data vs journal)          | 0
my rows touched by another run              | 0
other lanes writing while I did             | 0
old values in my run                        | Chile, Easter Island | Georgia (country)
new values in my run                        | Chile | Georgia
applied_by                                  | ancient_map
confidence                                  | authoritative
my run rows with an evidence payload        | 35
curated rows with a hint/comma country left | 0
applied_at span    | 2026-09-20 22:42:50.695778+00 .. 2026-09-20 22:42:50.695778+00
```

0 rows unaccounted, 0 value mismatches, exactly one table.column pair, one run stamp, one test id.

**The guards were not taken on trust.** `--probe-guards` sends four corrupted copies of the
statement to production, each with its own run stamp, each `BEGIN … ROLLBACK`
(`evidence/04_probe_guards.txt`); every one must be refused by the *database* and leave 0 journal rows:

| probe | what it corrupts | result |
|---|---|---|
| guard 1 | a row of another source (`canmore_scotland`) | `ERROR: country repair: 1 planned row(s) are not ancient_nerds sites` |
| guard 2 | one row made a no-op (new = old) | `ERROR: … 1 planned row(s) are not writable changes` |
| guard 2 | one value 101 characters long | `ERROR: … 1 planned row(s) are not writable changes` |
| guard 3 | a planned old value no row holds | `ERROR: … 1 planned row(s) no longer hold the planned old value` |

All four raised; all four left `journal rows left by this probe: 0`.

The deployed primitive was checked before the write (`--check-primitive`,
`evidence/02_check_primitive.txt`):

```
apply_remediation_change(text, text, text, text, text, text, text, text, text, text, jsonb, uuid)
casts_value_to_column_type | t   casts_old_value | t   rereads_stored_value | t
```

i.e. migration 0018's body (boolean path cast, old value cast, stored value re-read), not 0017's.

## 7. What a restart does to these columns

`unified_sites.country` — **no boot-time producer writes it for a curated row.** The only startup
writer is `pipeline/lyra/data_patches.py::fix_countries()`, scoped
`source_id = 'lyra' AND country IS NULL` (called from `pipeline/lyra/orchestrator.py:1062`), and
`scripts/audit_enrich.py:560-576` fills `country` only `WHERE country IS NULL AND lat IS NOT NULL …`.
A written, non-NULL value is therefore not reverted and not overwritten at boot. The value is
`varchar(100)` (contract), and every written value is NFC and 5 or 7 characters (`Chile`, `Georgia`).

`card_stats.civilization` — **not written by this lane**, and no boot-time producer either: the value
comes from `api/cardgame/stats.py:184` (`"civilization": country`) and is upserted by
`api/cardgame/generator.py::_upsert_stats`, which runs by hand or as a pipeline job — never at API
boot. Consequence: for the 35 rows, `card_stats.civilization` still repeats the **old** value. That
is a residual, not an oversight (§9), and it is visible: `apply.py --verify` counts it as
`card_stats rows whose civilization differs from the site country | 35`.

## 8. Mutation proof

`tests/remediation/test_mechanical.py` — **63 tests, all passing**. Every guard carries a test that
fails when the guard is removed; `scripts/remediation/mechanical/mutation_sweep.py` does exactly that
mechanically (removes/inverts one guard, asks the named test to go red, restores the file and checks
the hash):

```
cases: 30  fired: 30  survived: 0
```

Full table in `evidence/10_mutation_sweep.txt`. Coverage includes: a non-applicable finding, a row of
another source, a snapshot/live mismatch, a stale finding, a canonicalisation that disagrees, an ISO
change, a value the frontend vocabulary does not carry, a geography contradiction, a Wikidata
contradiction, `preferred` rank being decisive, the compound tie-break, the fixed-point test, the
plan-side mirror (old value, new value, no-op, column length, evidence, duplicates), the empty
transaction, the rollback-before-apply order, the "statement must commit" check, all three
in-transaction scope guards, the journal/data reconciliation, the loop passing the *planned* old
value to the writer, and the read-back statements naming the run they read.

The two guards that were **found broken while writing this lane** are in §10; both now have tests and
mutation cases of their own.

## 9. Residuals — what this lane leaves behind (with check SQL)

1. **Two hub URLs now 404.** `/sites/georgia-country` and `/sites/chile-easter-island` matched rows
   before the write and match none now. `api/routes/sites_html.py:78-96` resolves the hub by
   `country_slug(row.country)` and only issues a 301 for a *case variant of a slug that still
   matches* (`/sites/Turkey` → `/sites/turkey`), so an unknown slug falls through to
   `render_error_html("Country")` with status **404** — no redirect exists for the two retired slugs,
   and this lane did not add one. Check after any change:
   `SELECT DISTINCT country_slug(country) FROM unified_sites WHERE source_id = 'ancient_nerds';`
   Follow-up: register a 301 for both old slugs (frontend/API change, out of this lane's scope) or
   accept the 404 — the decision is the owner's.
2. **`card_stats.civilization` still repeats the old value for the 35 rows** (measured: 35 divergences).
   Check:
   ```sql
   SELECT cs.civilization, u.country, count(*) FROM card_stats cs
     JOIN unified_sites u ON u.id = cs.site_id
    WHERE u.source_id = 'ancient_nerds' AND cs.civilization IS DISTINCT FROM u.country
    GROUP BY 1, 2 ORDER BY 3 DESC;
   ```
   Follow-up: re-run `api/cardgame/generator.py` so `_upsert_stats` re-derives the column; it is
   derived data and a boot does not touch it.
3. **The 8 Phase-3 sites keep their T01/T03 findings.** Their `country` is settled here; their
   remaining findings are Phase 3's, and they stay in `output/remediation/phase3_worklist/`.
4. **The plan is no longer re-derivable, by design.** `plan.py --write` now refuses all 35 with
   `snapshot-live-mismatch` (the census snapshot still says `Georgia (country)`, the live row says
   `Georgia`). That is the stale-finding guard doing its job — and the reason `PLAN.jsonl`,
   `PLAN.md` and `ROLLBACK.sql` are **frozen artifacts**: re-running `--write` would overwrite the
   record of what was applied with an empty plan.
5. **The census's own note about the TTS line is wrong** (reported, not fixed):
   `output/remediation/run_t05/findings.jsonl` claims the spoken line "already drops" the region for
   `Chile, Easter Island`. `pipeline/video/shorts_tts.py::specific_place` takes the **last** comma
   part, so the closing line changes from `Easter Island` to `Chile`. The wrong claim is **not**
   quoted in the journal evidence; correcting it belongs to the census lane.
6. **Frontend vocabulary keeps `Easter Island → CL`.** `countryFlags.ts:289` and
   `COUNTRY_CODES`/`NAME_TO_ISO` are untouched — deliberately: they are not the defect, and changing
   a shared vocabulary table is another lane's decision. The *globe filter* was a second defect and
   it is closed for these rows: `searchUtils.ts::extractCountry` returns the **last** comma part, so
   it read `Easter Island` where a country is expected; with `Chile` stored it reads `Chile`.

## 10. Found wrong while writing this lane, and fixed

1. **`VERIFY_SQL` was an unformatted template — a read-back that could not fail.** It was written
   `VERIFY_SQL = """… WHERE run_stamp = '{RUN_STAMP}' …"""`, so all six journal metrics compared
   against the *literal* `{RUN_STAMP}` and printed **0** — before *and* after the write. A count of 0
   in a read-back reads as "clean", so this would have certified the write with an instrument that
   never looked at it. The row counts in the same query were correct (literal SQL); only the
   journal-scoped metrics were blind. Fixed (f-string), re-read: 35/35. Covered by
   `TestReadBackStatements` and the mutation "the read-back names its run".
2. **`PSQL_ROWS` used `-F|`** — through `ssh` the remote login shell parses the bare `|` as a pipe
   (`bash: -c: line 2: syntax error: unexpected end of file`, then
   `ValueError: could not convert string to float: ' coalesce '`). Removed; unaligned output already
   separates on `|`.
3. **`evidence=list(...)` where `ChangeRecord.evidence` is a tuple** (a static-analysis finding on
   `plan.py:1102`). Fixed at the call site (`tuple(...)`), no `type: ignore`.
4. **`_hub_rows()` imported the API route to get `country_slug`**, dragging the whole FastAPI import
   chain (and a misleading "connection refused … localhost:5432" warning) into the evidence. Now it
   imports `pipeline.sites_html_renderer.country_slug` — the same function the route imports
   (`api/routes/sites_html.py:25`).

Two static-analysis findings were **triaged as false positives and deliberately not "fixed"**:
`apply.py:95` (`json.loads` on a plan line) and `apply.py:455` (`int(count)` on a database count).
Wrapping them would turn "could not check" into "checked and clean" — the one thing this project's
rules forbid. A malformed plan file or a non-numeric count must abort the run with a traceback.

## 11. Gates and what could not be verified

Run on this machine, 2026-09-21:

| gate | command | result |
|---|---|---|
| backend suite | `./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"` | **2136 passed, 3 skipped, 57 deselected** in 160.85 s on the final tree (the count moves while other lanes add tests — it was 2099 twenty minutes earlier; this lane contributes 63). The 3 skips are the known pre-existing ones, named by `-rs` |
| this lane's tests | `… -m pytest tests/remediation/test_mechanical.py -q -rs` | **63 passed** |
| lint | `./.venv/Scripts/python.exe -m ruff check api/ pipeline/` and `… scripts/remediation/mechanical/ tests/remediation/test_mechanical.py` | clean |
| types (this lane) | `… -m mypy scripts/remediation/mechanical/ tests/remediation/test_mechanical.py` | clean |
| mutation sweep | `… scripts/remediation/mechanical/mutation_sweep.py` | 30 cases, 30 fired, 0 survived |

**Not verified / not verifiable here:**

* **`mypy api/` — the CI gate — is not green, and was not before this lane.** 93 errors in 14 files
  (`api/cardgame/discord_commands.py` 35, `api/routes/public_v1.py` 17, `api/services/discord_bot.py`
  13, …). None of them is in a file this lane touched (`git status` shows only
  `scripts/remediation/mechanical/`, `tests/remediation/test_mechanical.py` and
  `output/remediation/mechanical/` as new; nothing under `api/`, `pipeline/`, `migrations/`,
  `ancient-nerds-map/`). Reported, not fixed: it is another lane's surface.
* **No local database** — every number above was measured against production over `ssh`. The
  integration tests need Docker and are deselected by CI; they were not run.
* **The backup this write relies on** was not re-verified by this lane:
  `/var/www/ancientnerds/backups/2026-09-20_remediation/database_2026-09-20_remediation.dump`
  (654,604,671 bytes) carries `DRILL_REPORT.txt` with the verdict "restorable and matches production
  row-for-row". That drill is another lane's measurement; this lane only cites it.
* **`card_stats` was not re-derived.** The 35 divergences (§9.2) are counted, not repaired, and the
  card game's `civilization` is a *card-game* field: whether an Easter Island ahu should read
  `Chile` there was not re-derived.
* **The frontend was not run.** The globe-filter consequence is reasoned from `searchUtils.ts` and the
  measured hub tables; no browser check was made.
* **`ROLLBACK.sql` has not been committed anywhere** (it never will be unless the owner reverses
  this). Its executability was proven without committing: §5, `--rehearse-rollback`.
* **`PLAN.md` is hand-synced** for §7's wording and the command list, because the plan can no longer
  be regenerated (§9.4). The statement files are provably generator output
  (`evidence/11_fingerprints.txt`); `PLAN.md`'s prose paragraphs are not byte-reproducible and this is
  the one place where that matters.
* `pycountry`/`babel` are **not installed** in this venv, so no third ISO authority was consulted;
  the ISO-2 anchors are the project's own `normalize_country` and the frontend's flag table.

## 12. How to reverse it

```bash
# the reversal, written before the apply and never hand-typed:
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map \
  -v ON_ERROR_STOP=1" < output/remediation/mechanical/ROLLBACK.sql
```

* run stamp of the reversal: `2026-09-21_mechanical-country-rollback` (distinct from the write's, so
  the journal keeps the write's record and gains the reversal's).
* expected afterwards: `Georgia (country)` 27 / `Georgia` 3, `Chile, Easter Island` 8 / `Chile` 3,
  journal rows for the rollback stamp 35, and both old hub slugs live again.
* the reversal re-creates the *old* hub split (that is the point of a reversal, and the reason the
  write had to cover all 35 rows in the first place).
* reversal is itself journalled and itself conditional on the current values, so it refuses rather
  than writes if the rows no longer hold what it expects.
