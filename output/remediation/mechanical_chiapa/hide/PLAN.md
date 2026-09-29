# HUMAN_ONLY Nr. 7 - the duplicate hide (`chiapa-hide`): plan

Built 2026-09-29T15:49:43+00:00 by `scripts/remediation/mechanical/chiapa.py` from the read-only production read of 2026-09-29 15:49:43.193037+00 (`../READ.jsonl`). Lane `chiapa-hide`: run stamp `2026-09-29_mechanical-chiapa-hide`, journal test id `Nr7/duplicate-hide`, change keys `chiapa-hide:<site_id>:<column>`, premise `'content links ' || CAST((SELECT count(*) FROM site_content_links c WHERE c.site_id = u.id) AS text) || ', images ' || CAST((SELECT count(*) FROM wiki_images w WHERE w.site_id = u.id) AS text)`. Decision: `output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`, Nr. 7 (O9, 2026-09-26).

**1 site, 2 cells.** Runs first: the rename (`../name/`) is refused by its guard 5 until this has landed.

| site | cell | old | new |
|---|---|---|---|
| Chiapa de Corzo (`24aa135d-4714-47f5-96c0-d58f0bc04b6f`) | scope_status | NULL | `retired` |
| Chiapa de Corzo (`24aa135d-4714-47f5-96c0-d58f0bc04b6f`) | scope_reason | NULL | `duplicate_of:ed186ea9-9ed1-415d-828b-97d9f21401d2` |

Premise carried by every cell: `content links 0, images 0`.

## What the transaction checks

* guard 1: the row is a curated site
* guard 2: two real changes, only in `scope_status` and `scope_reason`
* guard 3: the row still holds the planned old values (both NULL)
* guard 4: the status written is `retired` and nothing else
* guard 5: the row is still empty - premise `content links 0, images 0`
* after the write, the survivor its reason names is a curated site, not retired, and within 100 m (three checks, each probed with a row of its kind)
* one journal row per cell, and exactly the planned cells moved

## Evidence

* output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md: Nr. 7: eine Stätte, Richtung wie empfohlen - Chiapa de Corzo ausblenden (duplicate_of:ed186ea9...) und die Zoque-Zeile in 'Chiapa de Corzo' umbenennen
* production:unified_sites: 'Chiapa de Corzo' (24aa135d-4714-47f5-96c0-d58f0bc04b6f): 0 content link(s), 0 image(s), external ids none; 'Zoque Culture Archaeological Zone' (ed186ea9-9ed1-415d-828b-97d9f21401d2): 3 content link(s), 20 image(s), external ids enwiki_title=Chiapa de Corzo (Mesoamerican site), wikidata_qid=Q4384315; 7.4 m apart (read 2026-09-29 15:49:43.193037+00)
* survivor rule: older row, then more content links, description citations, images: 'Zoque Culture Archaeological Zone' (2026-03-04 21:07:57.660461, 3 links, 0 citations, 20 images) over 'Chiapa de Corzo' (2026-03-04 21:07:57.660461, 0 links, 0 citations, 0 images)

## Run (after the plan; the hide's lane first, then the rename's)

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --check-primitive
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --verify
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --interests
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --emit
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --rehearse
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --probe-guards
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --apply
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --verify
$PY scripts/remediation/mechanical/apply.py --lane chiapa-hide --rehearse-rollback
```

Undo, only as a decision: the rename's `ROLLBACK.sql` first (its guard 5 needs the hide standing), then the hide's.
