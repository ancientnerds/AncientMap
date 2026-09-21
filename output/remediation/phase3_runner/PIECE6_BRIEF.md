# Piece 6 — the writer: one reviewer-confirmed finding becomes one guarded production write

**Status:** brief, not yet built. Succeeds piece 5 (the discover pass).
**Written:** 2026-09-21 by the supervisor.

## 1. What this piece is for

Finder and reviewer only *propose*. The plan is unambiguous about the step that follows
(`SITES_DB_REMEDIATION_2026-09.md`, Phase 3):

> Only `refuted = false` is applied, with a conditional WHERE clause and a journal entry.

Everything before this piece produces text; this piece is the only one that changes the database. It
is therefore the piece where a mistake is not a wasted call but a corrupted record.

## 2. What already exists and must be reused, not reinvented

* `apply_remediation_change(...)` — the 12-argument SQL function (`p_table`, `p_column`, `p_pk_col`,
  `p_pk`, `p_old`, `p_new`, `p_test_id`, `p_run_stamp`, `p_change_key`, `p_confidence`, `p_evidence`
  jsonb, `p_site_id uuid`). Installed definition length **7148** with the no-op guard from item `[H]`.
* `remediation_change_log` — the journal, **5,578 rows** in production, three columns ever written.
* The mechanical lane's proven shape (`scripts/remediation/mechanical/`): a digest-pinned plan →
  `APPLY.sql` + `ROLLBACK.sql` → guarded apply → read-back verification → an independently proven
  exact inverse. Its 35-row write and the gallery lane's 105-row write both landed this way, and both
  undos were verified as exact inverses row by row.
* The mutation-sweep habit: the mechanical lane ran **30 cases, 30 fired, 0 survived**. This piece
  needs the same treatment for its guards.

## 3. The hard part: the fixed point

A write the boot producers would overwrite is not a repair, it is a journal entry for nothing. The
plan names this landmine (§10.1) and the surface is known:

| column | who overwrites it | when |
| --- | --- | --- |
| `unified_sites.site_type` | `orchestrator.py:1476-1488` | container restart |
| `unified_sites.name_normalized` | `orchestrator.py:1694-1702` | container restart |
| `card_stats.card_description` | the card-stats producer | enrichment |
| `fix_countries()` via `run_data_patches` (`orchestrator.py:1063-1065`) | `data_patches.py:54` | container restart |

So: **every proposed value is checked against the producing rule before it is written.** Three
outcomes, and the writer must be able to say which one it took:

1. the producer agrees → write it (the value is a fixed point);
2. the producer would replace it → **refuse the write** and record the site for manual review, with the
   producer and the rule named as the reason;
3. the column has no producer → write it (`unified_sites.description` is not a boot overwriter).

Writing first and noticing later is exactly the failure mode this section exists to prevent. `country`
is the interesting case: `fix_countries()` runs on every restart, so a country write is only real if
`fix_countries()` would produce the same country from the corrected data — the 35-row mechanical write
already had to establish this.

## 4. Requirements

1. **Input:** a batch's reviewer verdicts, taking **only** findings the reviewer did not refute. A
   finding with `outcome="unverifiable"` is not a write candidate, and neither is one the reviewer
   refuted. Both stay visible in the record as "not applied, and why".
2. **One row per statement.** A plan is a list of single-row updates, each with the table, the primary
   key, the column, the old value, the new value, the evidence, and the finding that bought it. No
   `UPDATE ... WHERE` that could touch a row the plan never examined.
3. **The old value is in the WHERE clause, always** — `AND <column> IS NOT DISTINCT FROM <old>`. A row
   whose value moved since the snapshot invalidates that row's plan entry: the write must affect 0 rows
   and say so, rather than overwrite a change somebody else made.
4. **`change_key`** is a deterministic digest over (site, table, column, old, new, test_id), so a re-run
   is idempotent and a duplicate is visible as a duplicate rather than as a second write.
5. **`APPLY.sql` and `ROLLBACK.sql` pin each other by digest.** `apply` refuses when the digest of the
   plan it is handed does not match the one the SQL was generated from. (`[H] SECURITY 3 / BACKEND B7`
   is still open on the older `--apply` path: it reads `APPLY.sql` with no cryptographic tie to the
   plan. Do not copy that defect into this piece — this piece must be the corrected pattern.)
6. **`-v ON_ERROR_STOP=1` always.** Without it `psql` walks past a failed statement and commits an
   empty transaction, which is indistinguishable from success.
7. **Read-back verification** after the write: re-read the written rows and compare against the plan.
   Then prove the inverse **independently**, in a transaction that is rolled back, exactly the way the
   `0018` selftest does it.
8. **No `DELETE`, ever.** No schema change. No write outside `source_id='ancient_nerds'`.
9. **Dry run is the default.** `--apply` needs an explicit flag, the matching digest, and a pre-flight
   count proving how many rows would change.
10. Every report states, in numbers: rows planned, rows written, rows that matched 0 (with the reason),
    journal rows added, and rows refused by the fixed-point check.

## 5. Tests

* The zero-row case: an entry whose old value no longer matches writes nothing **and is recorded**, and
  the batch continues.
* The fixed-point refusal: a `site_type` whose producer would overwrite it is refused, with the producer
  named.
* `change_key` is stable across runs and different for different sites/values.
* `apply` refuses a plan whose digest does not match the SQL.
* The inverse is exact: apply then rollback leaves the journal and the data as they were (the mechanical
  lane's standard).
* Each of the above is **mutation-proven** — name the mutation and the assertion that caught it.

## 6. Non-goals

* Phase 4/5 (rewriting descriptions and card texts with cited sourcing) — a different pipeline, already
  partly built (`web-links` → `cited-description` → `verify-citations`).
* Phase 6 follow-through (`generate_stats()`, `name_normalized` via SQL `unaccent`, static export,
  Qdrant resync, the scope column).
* Deciding *whether* to write to production. That is the owner's decision, and the writer's job is to
  make the decision cheap to make and cheap to reverse.

## 7. The owner's decision of 2026-09-21: 100 sites per step, a check after every step

Verbatim (owner, 2026-09-21): *"wenn wir soweit sind will ich die sites in 100er schritten updaten,
nach 100 immer prüfung, dann erst weiter bis fertig."* - write in steps of 100 sites; after every 100
always the check; only then continue, until done.

That is a requirement on this piece, not a preference about reporting. It settles three things:

1. **The unit of a write is a chunk of 100 sites**, in a stable order - the snapshot's own line order,
   so "the first 100" is the same 100 on every run and after a resume. A chunk is never a set whose
   membership depends on which findings happened to be ready first.
2. **A chunk is finished only together with its check**, and the check comes from the database, not
   from the writer's own memory of what it sent. The shape is the mechanical lane's, once per chunk:
   digest-pinned chunk plan -> `APPLY.sql` + `ROLLBACK.sql` -> guarded apply (`-v ON_ERROR_STOP=1`,
   conditional `WHERE <column> IS NOT DISTINCT FROM <old>`) -> **read-back, with every applied value
   compared against the intended one** -> and only then the next chunk. A chunk whose read-back
   differs is a **stop**, not a warning: the run does not go on to chunk n+1 until the difference is
   understood. That is the whole point of the step size.
3. **That check includes the inverse, per chunk**: the chunk's `ROLLBACK.sql` is proven to undo exactly
   the chunk it just wrote, folded into the same check, so a chunk that cannot be undone does not
   accumulate 99 successors behind a discovery made at the end.

Decided here because the brief must be unambiguous to build from:

* The step size is a **knob with a proven default** (`--chunk-size`, default 100), not a bare constant.
  The owner asked for a step; a step that cannot be raised or lowered without editing code is a
  constant wearing its name.
* The chunk is named by its own `p_run_stamp` value (`apply_remediation_change` requires one per row),
  so a chunk is identifiable after the fact **without a schema change**. Verified in
  `migrations/0018_remediation_change_log_boolean.sql`: `p_run_stamp` is a required argument.
* The read-back is a statement about the *same* sites the chunk named, not a count: a count cannot
  tell "absent" from "changed", which is the trap this project already paid for once.
