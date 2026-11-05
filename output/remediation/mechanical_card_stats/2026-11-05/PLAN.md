# Phase 6 item 4 - card_stats recomputed as the generator would: plan (card-stats-2026-11-05)

Built 2026-11-05T22:52:22+00:00 by `scripts/remediation/mechanical/card_stats.py` from the production export `21200f1e3f26a29a660a53d6e84a468cddcf4cd509a6ce7d5fcf79b82fc9057a` (2026-11-05 22:52:16.465314+00). Lane `card-stats-2026-11-05`: run stamp `2026-11-05_mechanical-card-stats`, journal test id `P6/card-stats-recompute`, change keys `card-stats-2026-11-05:<site_id>:<column>`, target `card_stats.site_id`.

**8392 cell(s) over 2083 of 4975 card(s) will be written, 29 refused.** 2070 of the changed cards belong to sites with a journalled field write; the others change only because a `(site_type, period_name)` share moved.

## The model is the generator's, and it reproduces the stored cards

Counterfactual: 5519 journalled input value(s) put back, recomputed with `generator.site_card_stats()`: **0 of 59724 cells differ** from the stored `card_stats`. The empires are ordered as production lists its boundary directories: `shang`, `mitanni`, `assyrian`, `carolingian`, `han`, `gupta`, `kush`, `mycenaean`, `achaemenid`, `seleucid`, `metadata.json`, `parthian`, `qin`, `axum`, `greek`, `byzantine`, `carthaginian`, `sassanid`, `capitals.json`, `zapotec`, `elam`, `zhou`, `roman`, `olmec`, `babylonian`, `teotihuacan`, `kushan`, `hittite`, `regions.json`, `indus_valley`, `aztec`, `roman.geojson`, `etruscan`, `minoan`, `inca`, `maya`, `akkadian`, `phoenician`, `maurya`, `macedonian`, `egyptian`.

The basis the proof stood on: wave 2026-10-04f's own export (2026-10-04 19:19:41.515456+00) (journal horizon 304160, `card_stats.resolve_basis`). This plan's own basis is in `BASIS.json` next to this file: the export's journal horizon, every curated site's content links, images, likes and bookmarks, and the cells planned. The next wave's proof reads it - commit it with the plan that is applied, and never re-plan an applied wave (`--write` refuses one whose run stamp is in the journal).

## The undo holds only while the premise does

`ROLLBACK.sql` carries the write's guard 5: it refuses once any curated site's `site_type` or `period_name` has been written anywhere, or any input of a planned site has moved (its fields, content links, images, likes, bookmarks). From then on this wave is not undone from its file: the next wave recomputes the cards from the inputs as they are, or a reversal is planned from the journal as a new decision (no lane does that for card_stats today).

## Cells per column

| column | cells |
|---|---|
| `antiquity` | 806 |
| `fortification` | 16 |
| `cultural_influence` | 305 |
| `mystery` | 1723 |
| `legacy` | 8 |
| `total_power` | 1984 |
| `rarity_score` | 1912 |
| `rarity_tier` | 727 |
| `category_group` | 17 |
| `civilization` | 0 |
| `empires` | 453 |
| `empire_count` | 441 |

## rarity_tier moves

| from | to | cards |
|---|---|---|
| 1 Common | 2 Uncommon | 60 |
| 1 Common | 3 Rare | 8 |
| 2 Uncommon | 1 Common | 50 |
| 2 Uncommon | 3 Rare | 201 |
| 3 Rare | 1 Common | 16 |
| 3 Rare | 2 Uncommon | 243 |
| 3 Rare | 4 Epic | 49 |
| 4 Epic | 2 Uncommon | 8 |
| 4 Epic | 3 Rare | 85 |
| 4 Epic | 5 Legendary | 3 |
| 5 Legendary | 4 Epic | 4 |

321 card(s) move up, 406 down.

## category_group moves

| from | to | cards |
|---|---|---|
| Monuments | Settlements | 4 |
| Settlements | Other | 4 |
| Monuments | Other | 3 |
| Burial & Death | Monuments | 1 |
| Fortifications | Settlements | 1 |
| Infrastructure | Other | 1 |
| Megalithic | Monuments | 1 |
| Other | Religious | 1 |
| Settlements | Monuments | 1 |

## Refusals

* `no-description`: 29

## Re-run after every later write wave

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --export
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane card-stats-<wave> --emit
```

A wave that is applied must plan 0 cells on the next wave's export, re-planned under a new label (`--wave <wave>b`): that is the read-back that the recompute is complete.
