# G0b - persist the kinds the shorts pipeline stated in its rejections (gallery-verdicts-persist-07817ee0)

30 row(s) to write, 0 named refusal(s).

Input: `output/remediation/vlm_pilot/REJECTED_KINDS.jsonl`, `PROVEN` records only. Each
names the row its rejection belongs to, proven by the short's candidate pool and the
snapshot agreeing; the kind is the one the rejection states verbatim (`kind=<kind>`).
`image_kind` is written only where it is NULL, only where production still holds the row
on the proof's site under the proof's filename, and only for `ancient_nerds` sites.

Run stamp `gallery-verdicts-persist-07817ee0` - derived from this batch's own ids, never G0's landed stamp.

## Rows to write

| image_id | slug | kind | filename |
|---|---|---|---|
| 61954 | ishtar-gate | `artifact` | `Close-up_of_Ishtar_Gate_tiles,_Pergamon_Museum_3.webp` |
| 61955 | ishtar-gate | `artifact` | `Flower_from_the_2nd_building_phase_of_the_Ishtar_Gate_of_Babylon,_colored_glaze_on_flat_bricks._6th_century_BCE._Pergamon_Museum.webp` |
| 61959 | ishtar-gate | `artifact` | `Ishtar_Gate_Dragon.webp` |
| 61961 | ishtar-gate | `map_or_document` | `Ishtar_gate_schematic.webp` |
| 61962 | ishtar-gate | `artifact` | `Istanbul_Ancient_Orient_Museum_Ishtar_Gate_Bull_walking_right_in_2019_08_2184.webp` |
| 61965 | ishtar-gate | `artifact` | `Istanbul_Ancient_Orient_Museum_Ishtar_Gate_Mušḫuššu_walking_left_in_2019_51_2187.webp` |
| 63780 | senegambian-stone-circles | `map_or_document` | `Senegambian_Megaliths.webp` |
| 63785 | senegambian-stone-circles | `other` | `Πέτρινοι κύκλοι της Σενεγκάμπια(κάτοψη).webp` |
| 64264 | stonehenge | `painting_or_artwork` | `Constable_-_Stonehenge,_1629-1888,_2006AK8142.webp` |
| 64265 | stonehenge | `map_or_document` | `Expansion_of_farming_in_western_Eurasia,_9600–4000_BCE.webp` |
| 64267 | stonehenge | `map_or_document` | `Stone_Plan.webp` |
| 64270 | stonehenge | `painting_or_artwork` | `Stonehenge_-_Wiltonia_sive_Comitatus_Wiltoniensis;_Anglice_Wilshire_(Atlas_van_Loon).webp` |
| 64273 | stonehenge | `painting_or_artwork` | `Stonehenge_Lucas_de_Heere.webp` |
| 64278 | stonehenge | `map_or_document` | `Stonehenge_phase_one.webp` |
| 64279 | stonehenge | `map_or_document` | `Stonehenge_plan.webp` |
| 64280 | stonehenge | `map_or_document` | `Stonehenge_stones_plan_by_Nash_et_al_2021.webp` |
| 64487 | karatepe-aslantaş-open-air-museum | `artifact` | `Karatepe Museum 5207.webp` |
| 64488 | karatepe-aslantaş-open-air-museum | `artifact` | `Karatepe Museum 5208.webp` |
| 64489 | karatepe-aslantaş-open-air-museum | `artifact` | `Karatepe Museum 5209.webp` |
| 64490 | karatepe-aslantaş-open-air-museum | `artifact` | `Karatepe Museum 5210.webp` |
| 64491 | karatepe-aslantaş-open-air-museum | `artifact` | `Karatepe Museum 5214.webp` |
| 64495 | karatepe-aslantaş-open-air-museum | `artifact` | `Karatepe_Museum.webp` |
| 64496 | karatepe-aslantaş-open-air-museum | `artifact` | `Karatepe_Museum_5212.webp` |
| 64497 | karatepe-aslantaş-open-air-museum | `artifact` | `Karatepe_Museum_5228.webp` |
| 73069 | machu-picchu | `map_or_document` | `Map_of_the_Peruvian_Expedition_of_1912.webp` |
| 73429 | tomb-of-jahangir | `artifact` | `Jehangir's_tomb,_detail.webp` |
| 73430 | tomb-of-jahangir | `map_or_document` | `Jehangir_Tomb5.webp` |
| 101064 | teotihuacan | `artifact` | `Teotihuacan_Obsidian_Blade.webp` |
| 101068 | teotihuacan | `artifact` | `Teotihuacán_mask.webp` |
| 104494 | giza-necropolis | `artifact` | `Gizeh-Stele_du_reve.webp` |

## Named refusals

None.
## Verification

```bash
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --source rejected-kinds --plan
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --source rejected-kinds --rehearse
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --source rejected-kinds --apply
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --source rejected-kinds --verify
./.venv/Scripts/python.exe scripts/remediation/gallery_audit/persist_verdicts.py --source rejected-kinds --rehearse-rollback
```

