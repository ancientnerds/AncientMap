# Mechanical country repair - plan

Built 2026-09-20T22:41:01+00:00 by `scripts/remediation/mechanical/plan.py`. Run stamp `2026-09-21_mechanical-country`, journal test id `T05/country-canonical`, source `ancient_nerds`.

**35 row(s) will be written, 35 candidate(s) refused.** 8 of the written rows are sites the Phase 3 worklist also holds - their T01/T03 findings stay Phase 3's; only `country` is written here.

## The set: 35, not the worklist's 27

The candidates are the 70 T05 findings over 70 distinct sites; 35 of them are `applicable=true` and all of those are `proposal=set`. `output/remediation/phase3_worklist/MECHANICAL.md` lists 27 sites because `build_worklist.py` also filters `AND NOT phase3`; the 8 it drops carry the same applicable country finding next to a non-applicable T01/T03 finding about a *different field*. On the supervisor's decision of 2026-09-21 all 35 are written, because writing 27 would leave each country split across two hub slugs: 20 of the 27 Georgia rows would join the 3 rows already at `/sites/georgia` while the other 7 (all of them Phase-3 sites) stayed at `/sites/georgia-country`, and 7 of the 8 Chile rows would join the 3 already at `/sites/chile` while Easter Island stayed at `/sites/chile-easter-island` - a half-migrated state no rule produces. The 8 stay in the Phase 3 worklist; theirs are Armazi, Didnauri, Dmanisi, Easter Island, Kutaisi, Satsurblia Cave, Tsona Cave, Tsutskhvati Cave Natural Monument. The hub split is measured against the database before and after the write (`apply.py --interests`); the measured table is in `APPLIED.md`.

| stored value | written value | rows | rule |
|---|---|---|---|
| `Georgia (country)` | `Georgia` | 27 | disambiguation-hint |
| `Chile, Easter Island` | `Chile` | 8 | compound-label-country-part |

## Every check, and what it measured

| check | source | what it proves |
|---|---|---|
| reduction | the stored string | a hint or a single resolvable comma part; two candidates refuse |
| canonical form | pipeline/utils/country_lookup.py:canonicalize_country_display_name | the written value is the project's own canonical string and equals the proposal |
| vocabulary 1 | pipeline/utils/country_lookup.py:normalize_country | old and new map to the same ISO-3166-1 alpha-2 code |
| vocabulary 2 | ancient-nerds-map/src/utils/countryFlags.ts:COUNTRY_CODES | the new value is a key carrying that code, so the flag renders |
| geography | naturalearth:ne_10m_admin_0_countries (10m, cached, sha256 ce1ac703) | the row's own point is inside the named country's polygon (T02's 1000 m tolerance) |
| external | wikidata:P17 -> P297 | an independent authority states the same ISO code; a contradicting P17 refuses the row |
| fixed point | census T05 predicate | the census would not flag the written value again |

## Witness coverage

35 written row(s); 34 carry a Wikidata `P17 -> P297` witness. The 1 without one are Kudaro: its Wikidata entity states no `P17` at all, which is recorded per row in `PLAN.jsonl` as a gap rather than a pass. Every written row carries the two project vocabularies and the Natural Earth point-in-polygon check; the Wikidata witness is the only optional one. Anchors: {'site_external_ids:wikidata_qid': 33, 'wikidata:label+coordinate': 2}.

## Refusals

| reason | candidates | what it means |
|---|---|---|
| `finding-not-applicable` | 35 | T05 named a defect no snapshot can settle (spelling split, vocabulary gap, not a country) |

All 35 refusals are in `SKIPPED.jsonl` with the measurement that produced them. None of them is deleted, and none of them is written.

## What a restart does to this column

`unified_sites.country` has no boot-time producer for a curated row: the only writer that runs at startup is `pipeline/lyra/data_patches.py::fix_countries()`, scoped `source_id = 'lyra' AND country IS NULL` (orchestrator.py:1062), and `scripts/audit_enrich.py:560-576` fills `country` only `WHERE country IS NULL`. A written value therefore survives a restart. `card_stats.civilization` is a copy of `country` (`api/cardgame/stats.py:184`, upserted by `api/cardgame/generator.py::_upsert_stats`) and is **not** written here - that generator runs by hand or as a pipeline job, not at API boot; the divergence this leaves is a named residual in `APPLIED.md` with its check SQL.

## Reproduce

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/plan.py --collect
./.venv/Scripts/python.exe scripts/remediation/mechanical/plan.py --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --check-primitive
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --verify
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --interests
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --emit
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --rehearse
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --probe-guards
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --apply
./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical.py -q -rs
./.venv/Scripts/python.exe scripts/remediation/mechanical/mutation_sweep.py
```

`--apply` is the write and has been run (2026-09-21, 35 rows); `--collect`/`--write` no longer
reproduce this plan, because production now holds the new values - see `APPLIED.md`.
