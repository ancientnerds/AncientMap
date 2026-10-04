# Phase 6 item 4 - card_stats recomputed as the generator would: plan (card-stats-2026-10-04)

Built 2026-10-04T13:56:10+00:00 by `scripts/remediation/mechanical/card_stats.py` from the production export `f1553a47147279f605ac6e0f4b5d4d8c190e21be10a3edf487f42a948da219ff` (2026-10-04 13:55:46.282309+00). Lane `card-stats-2026-10-04`: run stamp `2026-10-04_mechanical-card-stats`, journal test id `P6/card-stats-recompute`, change keys `card-stats-2026-10-04:<site_id>:<column>`, target `card_stats.site_id`.

**15463 cell(s) over 3660 of 4977 card(s) will be written, 27 refused.** 3610 of the changed cards belong to sites with a journalled field write; the others change only because a `(site_type, period_name)` share moved.

## The model is the generator's, and it reproduces the stored cards

Counterfactual: 4686 journalled input value(s) put back, recomputed with `generator.site_card_stats()`: **0 of 59724 cells differ** from the stored `card_stats`. The empires are ordered as production lists its boundary directories: `shang`, `mitanni`, `assyrian`, `carolingian`, `han`, `gupta`, `kush`, `mycenaean`, `achaemenid`, `seleucid`, `metadata.json`, `parthian`, `qin`, `axum`, `greek`, `byzantine`, `carthaginian`, `sassanid`, `capitals.json`, `zapotec`, `elam`, `zhou`, `roman`, `olmec`, `babylonian`, `teotihuacan`, `kushan`, `hittite`, `regions.json`, `indus_valley`, `aztec`, `roman.geojson`, `etruscan`, `minoan`, `inca`, `maya`, `akkadian`, `phoenician`, `maurya`, `macedonian`, `egyptian`.

The basis the proof stood on: wave 2026-09-30's own export (2026-10-03 21:48:08.11327+00) (journal horizon 170695, `card_stats.resolve_basis`). This plan's own basis is in `BASIS.json` next to this file: the export's journal horizon, every curated site's content links, images, likes and bookmarks, and the cells planned. The next wave's proof reads it - commit it with the plan that is applied, and never re-plan an applied wave (`--write` refuses one whose run stamp is in the journal).

## The undo holds only while the premise does

`ROLLBACK.sql` carries the write's guard 5: it refuses once any curated site's `site_type` or `period_name` has been written anywhere, or any input of a planned site has moved (its fields, content links, images, likes, bookmarks). From then on this wave is not undone from its file: the next wave recomputes the cards from the inputs as they are, or a reversal is planned from the journal as a new decision (no lane does that for card_stats today).

## Cells per column

| column | cells |
|---|---|
| `antiquity` | 1600 |
| `fortification` | 278 |
| `cultural_influence` | 19 |
| `mystery` | 2861 |
| `legacy` | 0 |
| `total_power` | 3178 |
| `rarity_score` | 2868 |
| `rarity_tier` | 1127 |
| `category_group` | 299 |
| `civilization` | 0 |
| `empires` | 1617 |
| `empire_count` | 1616 |

## rarity_tier moves

| from | to | cards |
|---|---|---|
| 1 Common | 2 Uncommon | 253 |
| 1 Common | 3 Rare | 114 |
| 2 Uncommon | 1 Common | 109 |
| 2 Uncommon | 3 Rare | 258 |
| 2 Uncommon | 4 Epic | 20 |
| 3 Rare | 2 Uncommon | 211 |
| 3 Rare | 4 Epic | 72 |
| 4 Epic | 3 Rare | 83 |
| 4 Epic | 5 Legendary | 2 |
| 5 Legendary | 4 Epic | 5 |

719 card(s) move up, 408 down.

## category_group moves

| from | to | cards |
|---|---|---|
| Other | Monuments | 117 |
| Other | Settlements | 73 |
| Other | Burial & Death | 31 |
| Other | Religious | 21 |
| Other | Rock & Cave | 21 |
| Other | Fortifications | 20 |
| Other | Infrastructure | 9 |
| Other | Megalithic | 5 |
| Other | Water & Ports | 2 |

## Refusals

* `no-description`: 27

## Re-run after every later write wave

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --export
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane card-stats-<wave> --emit
```

A wave that is applied must plan 0 cells on the next wave's export, re-planned under a new label (`--wave <wave>b`): that is the read-back that the recompute is complete.
