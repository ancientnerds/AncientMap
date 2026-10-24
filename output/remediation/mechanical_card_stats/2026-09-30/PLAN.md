# Phase 6 item 4 - card_stats recomputed as the generator would: plan (card-stats-2026-09-30)

Built 2026-10-03T21:48:31+00:00 by `scripts/remediation/mechanical/card_stats.py` from the production export `31970f8086fe910d4aa07094c6993e5f802cf39fb5a46999d9394ce18a4dd844` (2026-10-03 21:48:08.11327+00). Lane `card-stats-2026-09-30`: run stamp `2026-09-30_mechanical-card-stats`, journal test id `P6/card-stats-recompute`, change keys `card-stats-2026-09-30:<site_id>:<column>`, target `card_stats.site_id`.

**21041 cell(s) over 4468 of 4977 card(s) will be written, 27 refused.** 4387 of the changed cards belong to sites with a journalled field write; the others change only because a `(site_type, period_name)` share moved.

## The model is the generator's, and it reproduces the stored cards

Counterfactual: 13620 journalled input value(s) put back, recomputed with `generator.site_card_stats()`: **0 of 60048 cells differ** from the stored `card_stats`. The empires are ordered as production lists its boundary directories: `shang`, `mitanni`, `assyrian`, `carolingian`, `han`, `gupta`, `kush`, `mycenaean`, `achaemenid`, `seleucid`, `metadata.json`, `parthian`, `qin`, `axum`, `greek`, `byzantine`, `carthaginian`, `sassanid`, `capitals.json`, `zapotec`, `elam`, `zhou`, `roman`, `olmec`, `babylonian`, `teotihuacan`, `kushan`, `hittite`, `regions.json`, `indus_valley`, `aztec`, `roman.geojson`, `etruscan`, `minoan`, `inca`, `maya`, `akkadian`, `phoenician`, `maurya`, `macedonian`, `egyptian`.

The basis the proof stood on: wave 2026-09-23's own export (2026-09-25 12:21:51.637605+00) (journal horizon 51782, `card_stats.resolve_basis`). This plan's own basis is in `BASIS.json` next to this file: the export's journal horizon, every curated site's content links, images, likes and bookmarks, and the cells planned. The next wave's proof reads it - commit it with the plan that is applied, and never re-plan an applied wave (`--write` refuses one whose run stamp is in the journal).

## The undo holds only while the premise does

`ROLLBACK.sql` carries the write's guard 5: it refuses once any curated site's `site_type` or `period_name` has been written anywhere, or any input of a planned site has moved (its fields, content links, images, likes, bookmarks). From then on this wave is not undone from its file: the next wave recomputes the cards from the inputs as they are, or a reversal is planned from the journal as a new decision (no lane does that for card_stats today).

## Cells per column

| column | cells |
|---|---|
| `antiquity` | 2514 |
| `fortification` | 770 |
| `cultural_influence` | 460 |
| `mystery` | 3432 |
| `legacy` | 108 |
| `total_power` | 3944 |
| `rarity_score` | 3589 |
| `rarity_tier` | 1624 |
| `category_group` | 805 |
| `civilization` | 2 |
| `empires` | 1907 |
| `empire_count` | 1886 |

## rarity_tier moves

| from | to | cards |
|---|---|---|
| 1 Common | 2 Uncommon | 182 |
| 1 Common | 3 Rare | 38 |
| 2 Uncommon | 1 Common | 222 |
| 2 Uncommon | 3 Rare | 440 |
| 2 Uncommon | 4 Epic | 21 |
| 3 Rare | 1 Common | 82 |
| 3 Rare | 2 Uncommon | 306 |
| 3 Rare | 4 Epic | 165 |
| 4 Epic | 1 Common | 2 |
| 4 Epic | 2 Uncommon | 15 |
| 4 Epic | 3 Rare | 125 |
| 4 Epic | 5 Legendary | 14 |
| 5 Legendary | 2 Uncommon | 1 |
| 5 Legendary | 3 Rare | 4 |
| 5 Legendary | 4 Epic | 7 |

860 card(s) move up, 764 down.

## category_group moves

| from | to | cards |
|---|---|---|
| Settlements | Other | 184 |
| Burial & Death | Other | 45 |
| Religious | Settlements | 45 |
| Megalithic | Settlements | 37 |
| Megalithic | Other | 35 |
| Settlements | Monuments | 35 |
| Rock & Cave | Other | 33 |
| Megalithic | Monuments | 31 |
| Religious | Other | 31 |
| Fortifications | Other | 26 |
| Settlements | Fortifications | 25 |
| Megalithic | Religious | 22 |
| Monuments | Other | 22 |
| Infrastructure | Other | 16 |
| Settlements | Religious | 13 |
| Megalithic | Fortifications | 12 |
| Fortifications | Settlements | 11 |
| Megalithic | Burial & Death | 10 |
| Monuments | Settlements | 10 |
| Burial & Death | Settlements | 9 |
| Infrastructure | Fortifications | 9 |
| Burial & Death | Religious | 7 |
| Megalithic | Infrastructure | 7 |
| Monuments | Burial & Death | 7 |
| Rock & Cave | Religious | 7 |
| Burial & Death | Megalithic | 6 |
| Settlements | Burial & Death | 6 |
| Settlements | Water & Ports | 6 |
| Megalithic | Rock & Cave | 5 |
| Monuments | Religious | 5 |
| Religious | Rock & Cave | 5 |
| Settlements | Infrastructure | 5 |
| Fortifications | Monuments | 4 |
| Religious | Monuments | 4 |
| Rock & Cave | Burial & Death | 4 |
| Water & Ports | Settlements | 4 |
| Burial & Death | Fortifications | 3 |
| Burial & Death | Monuments | 3 |
| Fortifications | Religious | 3 |
| Infrastructure | Rock & Cave | 3 |
| Megalithic | Water & Ports | 3 |
| Monuments | Fortifications | 3 |
| Other | Monuments | 3 |
| Religious | Burial & Death | 3 |
| Religious | Fortifications | 3 |
| Rock & Cave | Monuments | 3 |
| Rock & Cave | Settlements | 3 |
| Water & Ports | Other | 3 |
| Fortifications | Burial & Death | 2 |
| Infrastructure | Monuments | 2 |
| Infrastructure | Settlements | 2 |
| Infrastructure | Water & Ports | 2 |
| Monuments | Rock & Cave | 2 |
| Other | Settlements | 2 |
| Rock & Cave | Infrastructure | 2 |
| Burial & Death | Infrastructure | 1 |
| Infrastructure | Burial & Death | 1 |
| Infrastructure | Megalithic | 1 |
| Monuments | Infrastructure | 1 |
| Monuments | Megalithic | 1 |
| Monuments | Water & Ports | 1 |
| Other | Burial & Death | 1 |
| Other | Rock & Cave | 1 |
| Rock & Cave | Water & Ports | 1 |
| Settlements | Megalithic | 1 |
| Settlements | Rock & Cave | 1 |
| Water & Ports | Religious | 1 |

## Refusals

* `no-description`: 27

## Re-run after every later write wave

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --export
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane card-stats-<wave> --emit
```

A wave that is applied must plan 0 cells on the next wave's export, re-planned under a new label (`--wave <wave>b`): that is the read-back that the recompute is complete.
