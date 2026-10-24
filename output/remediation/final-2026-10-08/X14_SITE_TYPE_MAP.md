# X14 - the site_type alias map of the Phase-8 merge (2026-10-24)

Orchestrator decision X14 (MASTER_PLAN): an alias merges into its canonical value only when it is the
same category under another spelling or synonym of the vocabulary the frontend filters use; a
distinct category is kept; two genuinely different types are never merged.

Sources read: `pipeline/normalizers/site_type.py` (`CANONICAL_TYPES`, `_SYNONYMS`: "Do NOT merge
distinct types (castle != fort != fortress)"), `ancient-nerds-map/src/constants/colors.ts`
(`CATEGORY_COLORS`, `CATEGORY_TO_GROUP`, the filter groups), `ancient-nerds-map/src/seo/display.ts`
(`SITE_TYPE_LABELS`, the title labels), `api/cardgame/constants.py` (`_GROUP_DEFINITIONS`),
`plans/fields.md` item 8, and the live curated rows of every value (production, read-only,
2026-10-24 ~17:00 UTC). Counts are `site_type_merge.py report` (curated rows / of them retired).

## Merged (17)

| Alias | Rows | Target | Reason |
|---|---|---|---|
| Settlement | 110 / 1 | City/town/settlement | the compound names "settlement"; its title label is "Settlement" |
| Town | 11 / 0 | City/town/settlement | the compound names "town" |
| City | 92 / 1 | City/town/settlement | the compound names "city" (its first term); same rule as Town. Was "for the decision" in `not_merged`; the earlier note (city also names size and rank) holds for Town just the same |
| Urban | 3 / 0 | City/town/settlement | synonym of city (display.ts already titles `Urban` as "City"); rows: Bilbao (GT), Incahuasi, a proto-urban site |
| Villa | 12 / 0 | Residence/villa/farmhouse | the compound names "villa" |
| Fortress | 20 / 1 | Fortress/citadel | the compound names "fortress"; its title label is "Fortress" |
| Citadel | 3 / 0 | Fortress/citadel | the compound names "citadel" (Mycenae, Anku, Tall-e Takht) |
| Castle | 9 / 0 | Castle/palace | the compound names "castle" (its first term). Was "for the decision" in `not_merged` |
| Gate | 9 / 0 | Gate/archway/bridge | the compound names "gate"; rows are all city gates/pylons |
| Church | 7 / 0 | Church/cathedral | the compound names "church"; its title label is "Church" |
| Necropolis | 9 / 0 | Necropolis/tombs complex | the compound names "necropolis"; its title label is "Necropolis" |
| Megalithic | 5 / 0 | Megalithic structures | both are the group's generic word; display.ts titles both "Megalithic site"; colors.ts maps both to the Megalithic filter group (Apazzu, Cauria, Rinaghju, Dolmen of Guadalperal, Talang Kecepol) |
| Cave | 14 / 0 | Cave Structures | the curated cave type; its title label is "Cave site" |
| Road | 3 / 0 | Road/avenue/trackway | the compound names "road"; display.ts already titles both "Ancient road" |
| Mine | 2 / 0 | Mine/quarry | the compound names "mine" |
| Quarry | 3 / 0 | Mine/quarry | the compound names "quarry" |
| Theater | 1 / 0 | Theatre | American spelling of the same word; display.ts already titles it "Theatre" |

313 curated rows (310 shown), 0 refused by `classify` in the report.

## Kept (not merged)

| Value | Rows | Reason |
|---|---|---|
| Village | 32 | a village is a kind of settlement, not a spelling or synonym of a term the compound names; Village is a filter value of its own (rows: Chysauster, Carn Euny, nuragic villages) |
| Fort | 142 | fort is not fortress (normalizer rule castle != fort != fortress) |
| Bridge | 6 | other category group (Infrastructure vs Fortifications); the tool refuses the pair |
| Aqueduct | 7 | other category group (Water & Ports vs Infrastructure); the tool refuses the pair |
| Tomb | 71 | a tomb is not a tombs complex |
| Temple | 81 | a temple is not a temple complex |
| Museum, Geological interest, Natural feature, Magnetic anomaly | 36, 25, 20, 1 | scope questions, not vocabulary |

## State: not applied

The map is `scripts/remediation/mechanical/site_type_merge.json` (tracked), pinned by
`MAP_SHA256` in `site_type_merge.py` (tracked); `load_map()` takes no path from the CLI, and
`apply.py` resolves the lane through the same `load_map()`. Writing the decision therefore needs
tracked edits this sitting may not make. The decided map is staged untracked as
`output/remediation/final-2026-10-08/X14_site_type_merge.decided.json`
(sha256 of the LF text `de765fcd1cbb203924df57488779432d09ad4f5abc52e1ef55249260285c9313`),
validated by `load_map(path, pin=...)` and a read-only `report` against production (17 merges,
313 rows, decided, 0 refused).

The commit that releases the lane:

1. copy `X14_site_type_merge.decided.json` over `scripts/remediation/mechanical/site_type_merge.json`;
2. `site_type_merge.py`: `MAP_SHA256 = "de765fcd1cbb203924df57488779432d09ad4f5abc52e1ef55249260285c9313"`;
3. `tests/remediation/test_mechanical_site_type_merge.py`: `len(merge_map.merges) == 15` -> `17`;
   `test_the_delivered_map_is_a_proposal_until_it_is_decided` (`decision is None`) -> assert the
   decision is set; in `test_the_p31_table_keeps_every_alias_until_the_merge_is_in_production`
   drop `assert merge_map.decision is None` (the subset assertion must still hold: check that
   `City` and `Castle` are offered by `fields/p31_site_types.json`).

Then `wave --wave 2026-10-24` (4 steps of at most 100), per step `step`, `apply.py --lane
site-type-merge-2026-10-24-sNNN --emit | --rehearse | --probe-guards | --apply | --verify |
--rehearse-rollback`, `accept` (0 deviations), journal recount; after the last accept
`table --write` with `classify.TABLE_SHA256` in one commit, before the final card_stats wave.


## Adversarial check (independent Opus agent, 2026-10-24) and the final map

16 of the 17 proposed merges hold. **Megalithic is refuted and kept** (`not_merged`): it is the Megalithic group's own generic word, shared by four subtypes; the normaliser maps a single megalith to it; its rows split between Megalithic stones (alignments such as Rinaghju, next to Paddaghju) and Megalithic structures - a per-site question, not a spelling. Final map: 16 merges, 308 curated rows, pinned in `scripts/remediation/mechanical/site_type_merge.py` (`MAP_SHA256 = 56418e49...`). The check also confirmed Fort, Bridge, Aqueduct, Village, Tomb, Temple and the scope types as distinct, and noted that 95 of 142 Fort rows and 288 of 472 Fortress/citadel rows mention hillforts - a per-row question for later, not a vocabulary merge.
