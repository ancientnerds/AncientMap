# Phase 6 item 4 - card_stats recomputed as the generator would: plan (card-stats-2026-11-07d)

Built 2026-11-07T15:22:48+00:00 by `scripts/remediation/mechanical/card_stats.py` from the production export `ddb8b67997033964d0f88d0c0a6610e07a784474f656843d316e8a823e806308` (2026-11-07 15:22:34.233295+00). Lane `card-stats-2026-11-07d`: run stamp `2026-11-07d_mechanical-card-stats`, journal test id `P6/card-stats-recompute`, change keys `card-stats-2026-11-07d:<site_id>:<column>`, target `card_stats.site_id`.

**856 cell(s) over 231 of 4963 card(s) will be written, 41 refused.** 231 of the changed cards belong to sites with a journalled field write; the others change only because a `(site_type, period_name)` share moved.

## The model is the generator's, and it reproduces the stored cards

Counterfactual: 118 journalled input value(s) put back, recomputed with `generator.site_card_stats()`: **0 of 59556 cells differ** from the stored `card_stats`. The empires are ordered as production lists its boundary directories: `shang`, `mitanni`, `assyrian`, `carolingian`, `han`, `gupta`, `kush`, `mycenaean`, `achaemenid`, `seleucid`, `metadata.json`, `parthian`, `qin`, `axum`, `greek`, `byzantine`, `carthaginian`, `sassanid`, `capitals.json`, `zapotec`, `elam`, `zhou`, `roman`, `olmec`, `babylonian`, `teotihuacan`, `kushan`, `hittite`, `regions.json`, `indus_valley`, `aztec`, `roman.geojson`, `etruscan`, `minoan`, `inca`, `maya`, `akkadian`, `phoenician`, `maurya`, `macedonian`, `egyptian`.

The basis the proof stood on: wave 2026-11-07c's own export (2026-11-07 13:29:26.934212+00) (journal horizon 402004, `card_stats.resolve_basis`). This plan's own basis is in `BASIS.json` next to this file: the export's journal horizon, every curated site's content links, images, likes and bookmarks, and the cells planned. The next wave's proof reads it - commit it with the plan that is applied, and never re-plan an applied wave (`--write` refuses one whose run stamp is in the journal).

## The undo holds only while the premise does

`ROLLBACK.sql` carries the write's guard 5: it refuses once any curated site's `site_type` or `period_name` has been written anywhere, or any input of a planned site has moved (its fields, content links, images, likes, bookmarks). From then on this wave is not undone from its file: the next wave recomputes the cards from the inputs as they are, or a reversal is planned from the journal as a new decision (no lane does that for card_stats today).

## Cells per column

| column | cells |
|---|---|
| `antiquity` | 59 |
| `fortification` | 0 |
| `cultural_influence` | 0 |
| `mystery` | 218 |
| `legacy` | 0 |
| `total_power` | 227 |
| `rarity_score` | 218 |
| `rarity_tier` | 52 |
| `category_group` | 0 |
| `civilization` | 0 |
| `empires` | 41 |
| `empire_count` | 41 |

## rarity_tier moves

| from | to | cards |
|---|---|---|
| 2 Uncommon | 1 Common | 4 |
| 2 Uncommon | 3 Rare | 17 |
| 3 Rare | 2 Uncommon | 19 |
| 3 Rare | 4 Epic | 6 |
| 4 Epic | 3 Rare | 5 |
| 4 Epic | 5 Legendary | 1 |

24 card(s) move up, 28 down.

## category_group moves

| from | to | cards |
|---|---|---|

## Refusals

* `no-description`: 41

## Re-run after every later write wave

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --export
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane card-stats-<wave> --emit
```

A wave that is applied must plan 0 cells on the next wave's export, re-planned under a new label (`--wave <wave>b`): that is the read-back that the recompute is complete.
