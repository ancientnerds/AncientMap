# Phase 6 item 4 - card_stats recomputed as the generator would: plan (card-stats-2026-09-23)

Built 2026-09-23T04:04:04+00:00 by `scripts/remediation/mechanical/card_stats.py` from the production export `cc2c335613403bf688198c14a3589644f31330897c346464972dce79c28c6034` (2026-09-23 03:59:54.81158+00). Lane `card-stats-2026-09-23`: run stamp `2026-09-23_mechanical-card-stats`, journal test id `P6/card-stats-recompute`, change keys `card-stats-2026-09-23:<site_id>:<column>`, target `card_stats.site_id`.

**6104 cell(s) over 1566 of 5004 card(s) will be written, 0 refused.** 927 of the changed cards belong to sites with a journalled field write; the others change only because a `(site_type, period_name)` share moved.

## The model is the generator's, and it reproduces the stored cards

Counterfactual: 1275 journalled input value(s) put back, recomputed with `generator.site_card_stats()`: **0 of 60048 cells differ** from the stored `card_stats`. The empires are ordered as production lists its boundary directories: `shang`, `mitanni`, `assyrian`, `carolingian`, `han`, `gupta`, `kush`, `mycenaean`, `achaemenid`, `seleucid`, `metadata.json`, `parthian`, `qin`, `axum`, `greek`, `byzantine`, `carthaginian`, `sassanid`, `capitals.json`, `zapotec`, `elam`, `zhou`, `roman`, `olmec`, `babylonian`, `teotihuacan`, `kushan`, `hittite`, `regions.json`, `indus_valley`, `aztec`, `roman.geojson`, `etruscan`, `minoan`, `inca`, `maya`, `akkadian`, `phoenician`, `maurya`, `macedonian`, `egyptian`.

## Cells per column

| column | cells |
|---|---|
| `antiquity` | 290 |
| `fortification` | 481 |
| `cultural_influence` | 0 |
| `mystery` | 1354 |
| `legacy` | 0 |
| `total_power` | 1452 |
| `rarity_score` | 1354 |
| `rarity_tier` | 502 |
| `category_group` | 481 |
| `civilization` | 62 |
| `empires` | 65 |
| `empire_count` | 63 |

## rarity_tier moves

| from | to | cards |
|---|---|---|
| 1 Common | 2 Uncommon | 76 |
| 1 Common | 3 Rare | 16 |
| 2 Uncommon | 1 Common | 13 |
| 2 Uncommon | 3 Rare | 200 |
| 2 Uncommon | 4 Epic | 3 |
| 3 Rare | 1 Common | 2 |
| 3 Rare | 2 Uncommon | 63 |
| 3 Rare | 4 Epic | 84 |
| 4 Epic | 3 Rare | 38 |
| 4 Epic | 5 Legendary | 5 |
| 5 Legendary | 4 Epic | 2 |

384 card(s) move up, 118 down.

## category_group moves

| from | to | cards |
|---|---|---|
| Settlements | Monuments | 217 |
| Megalithic | Monuments | 45 |
| Settlements | Fortifications | 20 |
| Megalithic | Fortifications | 14 |
| Megalithic | Settlements | 14 |
| Religious | Settlements | 14 |
| Burial & Death | Megalithic | 12 |
| Megalithic | Infrastructure | 12 |
| Settlements | Other | 12 |
| Megalithic | Other | 11 |
| Fortifications | Settlements | 10 |
| Religious | Fortifications | 10 |
| Fortifications | Monuments | 9 |
| Megalithic | Religious | 7 |
| Megalithic | Water & Ports | 7 |
| Religious | Monuments | 7 |
| Burial & Death | Other | 5 |
| Burial & Death | Settlements | 4 |
| Other | Monuments | 4 |
| Rock & Cave | Other | 4 |
| Settlements | Infrastructure | 4 |
| Infrastructure | Fortifications | 3 |
| Rock & Cave | Monuments | 3 |
| Settlements | Burial & Death | 3 |
| Settlements | Religious | 3 |
| Settlements | Water & Ports | 3 |
| Burial & Death | Monuments | 2 |
| Fortifications | Infrastructure | 2 |
| Infrastructure | Other | 2 |
| Megalithic | Rock & Cave | 2 |
| Religious | Burial & Death | 2 |
| Rock & Cave | Settlements | 2 |
| Settlements | Megalithic | 2 |
| Burial & Death | Water & Ports | 1 |
| Infrastructure | Megalithic | 1 |
| Infrastructure | Monuments | 1 |
| Infrastructure | Water & Ports | 1 |
| Megalithic | Burial & Death | 1 |
| Monuments | Other | 1 |
| Monuments | Settlements | 1 |
| Religious | Rock & Cave | 1 |
| Rock & Cave | Religious | 1 |
| Water & Ports | Settlements | 1 |

## Re-run after every later write wave

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --export
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane card-stats-<wave> --emit
```

A wave that is applied must plan 0 cells on its next export: that is the read-back that the recompute is complete.
