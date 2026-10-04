# Phase 6 item 4 - card_stats recomputed as the generator would: plan (card-stats-2026-10-04f)

Built 2026-10-04T19:20:09+00:00 by `scripts/remediation/mechanical/card_stats.py` from the production export `0f055911b2404c3ca7bb1fb861dd44897686c7aa5daf24357b92ccd613d6938f` (2026-10-04 19:19:41.515456+00). Lane `card-stats-2026-10-04f`: run stamp `2026-10-04f_mechanical-card-stats`, journal test id `P6/card-stats-recompute`, change keys `card-stats-2026-10-04f:<site_id>:<column>`, target `card_stats.site_id`.

**4 cell(s) over 1 of 4977 card(s) will be written, 27 refused.** 1 of the changed cards belong to sites with a journalled field write; the others change only because a `(site_type, period_name)` share moved.

## The model is the generator's, and it reproduces the stored cards

Counterfactual: 104 journalled input value(s) put back, recomputed with `generator.site_card_stats()`: **0 of 59724 cells differ** from the stored `card_stats`. The empires are ordered as production lists its boundary directories: `shang`, `mitanni`, `assyrian`, `carolingian`, `han`, `gupta`, `kush`, `mycenaean`, `achaemenid`, `seleucid`, `metadata.json`, `parthian`, `qin`, `axum`, `greek`, `byzantine`, `carthaginian`, `sassanid`, `capitals.json`, `zapotec`, `elam`, `zhou`, `roman`, `olmec`, `babylonian`, `teotihuacan`, `kushan`, `hittite`, `regions.json`, `indus_valley`, `aztec`, `roman.geojson`, `etruscan`, `minoan`, `inca`, `maya`, `akkadian`, `phoenician`, `maurya`, `macedonian`, `egyptian`.

The basis the proof stood on: wave 2026-10-04b's own export (2026-10-04 18:08:44.180088+00) (journal horizon 302221, `card_stats.resolve_basis`). This plan's own basis is in `BASIS.json` next to this file: the export's journal horizon, every curated site's content links, images, likes and bookmarks, and the cells planned. The next wave's proof reads it - commit it with the plan that is applied, and never re-plan an applied wave (`--write` refuses one whose run stamp is in the journal).

## The undo holds only while the premise does

`ROLLBACK.sql` carries the write's guard 5: it refuses once any curated site's `site_type` or `period_name` has been written anywhere, or any input of a planned site has moved (its fields, content links, images, likes, bookmarks). From then on this wave is not undone from its file: the next wave recomputes the cards from the inputs as they are, or a reversal is planned from the journal as a new decision (no lane does that for card_stats today).

## Cells per column

| column | cells |
|---|---|
| `antiquity` | 0 |
| `fortification` | 0 |
| `cultural_influence` | 0 |
| `mystery` | 1 |
| `legacy` | 0 |
| `total_power` | 1 |
| `rarity_score` | 1 |
| `rarity_tier` | 1 |
| `category_group` | 0 |
| `civilization` | 0 |
| `empires` | 0 |
| `empire_count` | 0 |

## rarity_tier moves

| from | to | cards |
|---|---|---|
| 2 Uncommon | 3 Rare | 1 |

1 card(s) move up, 0 down.

## category_group moves

| from | to | cards |
|---|---|---|

## Refusals

* `no-description`: 27

## Re-run after every later write wave

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --export
./.venv/Scripts/python.exe scripts/remediation/mechanical/card_stats.py --wave <wave> --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane card-stats-<wave> --emit
```

A wave that is applied must plan 0 cells on the next wave's export, re-planned under a new label (`--wave <wave>b`): that is the read-back that the recompute is complete.
