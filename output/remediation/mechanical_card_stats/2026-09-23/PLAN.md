# Phase 6 item 4 - card_stats recomputed as the generator would: plan (card-stats-2026-09-23)

Built 2026-09-25T07:30:42+00:00 by `scripts/remediation/mechanical/card_stats.py` from the production export `090323805599231afd4c646ec751db2c8db747d127db8ab61dca8464ecdd2f6a` (2026-09-25 07:30:33.486561+00). Lane `card-stats-2026-09-23`: run stamp `2026-09-23_mechanical-card-stats`, journal test id `P6/card-stats-recompute`, change keys `card-stats-2026-09-23:<site_id>:<column>`, target `card_stats.site_id`.

**3982 cell(s) over 1055 of 5004 card(s) will be written, 0 refused.** 659 of the changed cards belong to sites with a journalled field write; the others change only because a `(site_type, period_name)` share moved.

## The model is the generator's, and it reproduces the stored cards

Counterfactual: 2390 journalled input value(s) put back, recomputed with `generator.site_card_stats()`: **0 of 60048 cells differ** from the stored `card_stats`. The empires are ordered as production lists its boundary directories: `shang`, `mitanni`, `assyrian`, `carolingian`, `han`, `gupta`, `kush`, `mycenaean`, `achaemenid`, `seleucid`, `metadata.json`, `parthian`, `qin`, `axum`, `greek`, `byzantine`, `carthaginian`, `sassanid`, `capitals.json`, `zapotec`, `elam`, `zhou`, `roman`, `olmec`, `babylonian`, `teotihuacan`, `kushan`, `hittite`, `regions.json`, `indus_valley`, `aztec`, `roman.geojson`, `etruscan`, `minoan`, `inca`, `maya`, `akkadian`, `phoenician`, `maurya`, `macedonian`, `egyptian`.

The basis the proof stood on: the first wave's: every journalled input value put back, the unjournalled inputs as exported (journal horizon 0, `card_stats.resolve_basis`). This plan's own basis is in `BASIS.json` next to this file: the export's journal horizon, every curated site's content links, images, likes and bookmarks, and the cells planned. The next wave's proof reads it - commit it with the plan that is applied, and never re-plan an applied wave (`--write` refuses one whose run stamp is in the journal).

## The undo holds only while the premise does

`ROLLBACK.sql` carries the write's guard 5: it refuses once any curated site's `site_type` or `period_name` has been written anywhere, or any input of a planned site has moved (its fields, content links, images, likes, bookmarks). From then on this wave is not undone from its file: the next wave recomputes the cards from the inputs as they are, or a reversal is planned from the journal as a new decision (no lane does that for card_stats today).

## Cells per column

| column | cells |
|---|---|
| `antiquity` | 180 |
| `fortification` | 257 |
| `cultural_influence` | 0 |
| `mystery` | 894 |
| `legacy` | 27 |
| `total_power` | 961 |
| `rarity_score` | 916 |
| `rarity_tier` | 356 |
| `category_group` | 257 |
| `civilization` | 61 |
| `empires` | 37 |
| `empire_count` | 36 |

## rarity_tier moves

| from | to | cards |
|---|---|---|
| 1 Common | 2 Uncommon | 16 |
| 1 Common | 3 Rare | 18 |
| 2 Uncommon | 1 Common | 10 |
| 2 Uncommon | 3 Rare | 123 |
| 2 Uncommon | 4 Epic | 3 |
| 3 Rare | 1 Common | 3 |
| 3 Rare | 2 Uncommon | 55 |
| 3 Rare | 4 Epic | 71 |
| 4 Epic | 3 Rare | 49 |
| 4 Epic | 5 Legendary | 5 |
| 5 Legendary | 4 Epic | 3 |

236 card(s) move up, 120 down.

## category_group moves

| from | to | cards |
|---|---|---|
| Settlements | Monuments | 68 |
| Megalithic | Monuments | 44 |
| Settlements | Fortifications | 16 |
| Megalithic | Fortifications | 14 |
| Megalithic | Settlements | 13 |
| Megalithic | Infrastructure | 11 |
| Religious | Settlements | 10 |
| Burial & Death | Megalithic | 9 |
| Settlements | Other | 8 |
| Megalithic | Religious | 7 |
| Megalithic | Water & Ports | 6 |
| Fortifications | Settlements | 5 |
| Megalithic | Other | 5 |
| Fortifications | Monuments | 4 |
| Other | Monuments | 4 |
| Settlements | Infrastructure | 4 |
| Religious | Fortifications | 3 |
| Settlements | Religious | 3 |
| Burial & Death | Settlements | 2 |
| Fortifications | Infrastructure | 2 |
| Religious | Monuments | 2 |
| Rock & Cave | Other | 2 |
| Rock & Cave | Settlements | 2 |
| Settlements | Megalithic | 2 |
| Settlements | Water & Ports | 2 |
| Burial & Death | Water & Ports | 1 |
| Infrastructure | Fortifications | 1 |
| Infrastructure | Monuments | 1 |
| Infrastructure | Water & Ports | 1 |
| Megalithic | Burial & Death | 1 |
| Monuments | Other | 1 |
| Monuments | Settlements | 1 |
| Religious | Burial & Death | 1 |
| Settlements | Burial & Death | 1 |

## Re-run after every later write wave

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --export
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane card-stats-<wave> --emit
```

A wave that is applied must plan 0 cells on the next wave's export, re-planned under a new label (`--wave <wave>b`): that is the read-back that the recompute is complete.
