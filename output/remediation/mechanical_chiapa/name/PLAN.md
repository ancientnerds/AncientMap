# HUMAN_ONLY Nr. 7 - the rename (`chiapa-name`): plan

Built 2026-09-29T15:49:43+00:00 by `scripts/remediation/mechanical/chiapa.py` from the read-only production read of 2026-09-29 15:49:43.193037+00 (`../READ.jsonl`). Lane `chiapa-name`: run stamp `2026-09-29_mechanical-chiapa-name`, journal test id `Nr7/rename`, change keys `chiapa-name:<site_id>:<column>`, premise `'duplicates retired onto it: ' || CAST((SELECT count(*) FROM unified_sites d WHERE d.source_id = 'ancient_nerds' AND d.scope_status = 'retired' AND d.scope_reason = 'duplicate_of:' || CAST(u.id AS text)) AS text) || ', highest id ' || coalesce((SELECT max(CAST(d.id AS text)) FROM unified_sites d WHERE d.source_id = 'ancient_nerds' AND d.scope_status = 'retired' AND d.scope_reason = 'duplicate_of:' || CAST(u.id AS text)), 'none')`. Decision: `output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`, Nr. 7 (O9, 2026-09-26).

**1 site, 2 cells.** Runs second: refused by guard 5 until the hide (`../hide/`) has landed.

| site | cell | old | new |
|---|---|---|---|
| Zoque Culture Archaeological Zone (`ed186ea9-9ed1-415d-828b-97d9f21401d2`) | name | `Zoque Culture Archaeological Zone` | `Chiapa de Corzo` |
| Zoque Culture Archaeological Zone (`ed186ea9-9ed1-415d-828b-97d9f21401d2`) | name_normalized | `zoque culture archaeological zone` | `chiapa de corzo` |

Premise carried by every cell: `duplicates retired onto it: 1, highest id 24aa135d-4714-47f5-96c0-d58f0bc04b6f`.

## What the transaction checks

* guard 1: the row is a curated site
* guard 2: real changes, only in `name` and `name_normalized`, each within 500 characters
* guard 3: the row still holds the planned old name 'Zoque Culture Archaeological Zone' and its key
* guard 5: the hide has landed with exactly its reason - premise `duplicates retired onto it: 1, highest id 24aa135d-4714-47f5-96c0-d58f0bc04b6f`; before the hide the row reads `duplicates retired onto it: 0, highest id none` and the rename is refused
* invariant 3: the key written is the key Postgres derives from the name written
* one journal row per cell, and exactly the planned cells moved

## Evidence

* output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md: Nr. 7: eine Stätte, Richtung wie empfohlen - Chiapa de Corzo ausblenden (duplicate_of:ed186ea9...) und die Zoque-Zeile in 'Chiapa de Corzo' umbenennen
* wikidata:Q4384315 en label: en label = 'Chiapa de Corzo' (bcases/names.jsonl, read 2026-09-23)
* production:unified_sites: 'Chiapa de Corzo' (24aa135d-4714-47f5-96c0-d58f0bc04b6f): 0 content link(s), 0 image(s), external ids none; 'Zoque Culture Archaeological Zone' (ed186ea9-9ed1-415d-828b-97d9f21401d2): 3 content link(s), 20 image(s), external ids enwiki_title=Chiapa de Corzo (Mesoamerican site), wikidata_qid=Q4384315; 7.4 m apart (read 2026-09-29 15:49:43.193037+00)

## Run (after the plan; the hide's lane first, then the rename's)

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --check-primitive
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --verify
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --interests
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --emit
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --rehearse
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --probe-guards
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --apply
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --verify
$PY scripts/remediation/mechanical/apply.py --lane chiapa-name --rehearse-rollback
```

Undo, only as a decision: the rename's `ROLLBACK.sql` first (its guard 5 needs the hide standing), then the hide's.
