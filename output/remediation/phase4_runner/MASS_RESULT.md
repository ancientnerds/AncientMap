# Phase-4 mass run (2026-09-24/25): complete; 984 defect sites carry a new description, every step 0 deviations

Plan `PLAN4.scope.jsonl` (`fec90379...`, the owner's defect scope `SCOPE4.json` v1 `19a57e9f...`):
**1,578 sites in 106 batches, `p4-0010` .. `p4-0115`**; run directory `runs/mass-2026-09-25`, apply
root `logs/_write_apply_p4`, pilot 4's thresholds, prompts and gates (`PILOT_RESULT_4.md`) with the
reviewer fix below; lanes W and S open, searches off (0 searches, no MiniMax client built). Every
model question was answered by Opus through the handoff: **1,392 selector and 1,003 review questions,
one Opus agent per batch and stage (106 + 106), the agents' answering times never overlapping**. The
run's ledger (`runs/mass-2026-09-25/LEDGER.jsonl` `55b48e29...`, 4,485 lines): 2,090 fetch lines, 2,395
model lines, every one `anthropic/claude-opus-5-5 (Claude Code agent)`, unmetered. Evidence
(gitignored): `logs/p4_mass/`, `logs/_write_apply_p4/ACCEPTED/step-0001..0014.json`,
`runs/mass-2026-09-25/HOLDS4.jsonl` (`3b16b3a9...`).

| step | batches | sites written | rows | lane rows carried after | re-verified after (V1-V15) | deviations |
|---|---|---|---|---|---|---|
| 1 (pilot 4) | p4-0001 .. p4-0009 | 26 | 52 | 52 | 26 | 0 |
| 2 | p4-0010 .. p4-0017 | 71 | 142 | 194 | 97 | 0 |
| 3 | p4-0018 .. p4-0025 | 84 | 168 | 362 | 181 | 0 |
| 4 | p4-0026 .. p4-0033 | 76 | 152 | 514 | 257 | 0 |
| 5 | p4-0034 .. p4-0041 | 79 | 158 | 672 | 336 | 0 |
| mid-run audit: 2 sites taken back | - | -2 | -4 | 668 | 334 | 0 |
| 6 | p4-0042 .. p4-0049 | 75 | 150 | 818 | 409 | 0 |
| 7 | p4-0050 .. p4-0057 | 78 | 156 | 974 | 487 | 0 |
| 8 | p4-0058 .. p4-0065 | 72 | 144 | 1,118 | 559 | 0 |
| 9 | p4-0066 .. p4-0073 | 64 | 128 | 1,246 | 623 | 0 |
| 10 | p4-0074 .. p4-0081 | 64 | 128 | 1,374 | 687 | 0 |
| 11 | p4-0082 .. p4-0089 | 74 | 148 | 1,522 | 761 | 0 |
| 12 | p4-0090 .. p4-0097 | 63 | 126 | 1,648 | 824 | 0 |
| 13 | p4-0098 .. p4-0105 | 75 | 150 | 1,798 | 899 | 0 |
| 14 | p4-0106 .. p4-0115 | 85 | 170 | **1,968** | **984** | **0** |

Rows are the site's `description` and its `raw_data` provenance, one each. The mass run wrote **960
sites (1,920 rows)**; with pilot 4's 26 that is 986 written, 2 taken back, **984 live** (958 mass + 26
pilot). The other **618 planned sites are held** and keep their text (the gate's `site-held` refusals,
group by group 49, 36, 44, 41, 45, 42, 48, 56, 56, 46, 57, 45, 53).

**Holds** (`HOLDS4.jsonl`, 909 lines): site scope 625 lines over 620 sites - abstained 267,
search-stopped 103 (lanes T/R/B3, searches off), V14 82, scope-pending 35, no-source 29, V9 27, V6 24,
revision-too-fresh 19, review-too-few-sentences 15, V5 14, selection-refused 4, audit-wrong-site 2, V7
2, V8 1, V15 1 (five sites carry two); card scope 284 lines over 265 sites - V10 162,
card-too-short-after-review 122 (19 carry both); 223 of them carry a written description (Roman Bath
and Altar of Athena Polias were taken back), 42 are site-held; what their cards get is Phase 5's.

**T8-style coverage**, reported, not gating (owner decision 2026-09-24, `PILOT_RESULT_3.md`): lanes at
S1b W 1,321, S 100, none 157; written **933 of 1,321 lane-W sites = 70.6 %** (931 after the two
reverts), 27 of 100 lane-S sites.

| check | sample | result |
|---|---|---|
| mid-run audit, after step 5 | 45 of the 336 written sites, 280 sentences, 36 cards | 279 SUPPORTED, **1 WRONG_SITE** (Roman Bath, York: its lead sentence is about the 1929-31 pub); cards all contained; 0 lost hedges, flips, broken sentences, verifier false-passes, gold errors. Writes stopped |
| WRONG_SITE check of every written site | 336 sites, 2,046 sentences | flagged: Roman Bath (sentences 1-2), Altar of Athena Polias (sentence 4, the Archaic temple's Gigantomachy pediment), Kit Hill (sentence 6, the 19th-century mine). Roman Bath and Altar taken back with `revert4.py --site` and held `audit-wrong-site`; Kit Hill kept - the mine is a later use of the hill itself (the orchestrator's judgement, recorded in `C:/tmp/applied_today.md`) |
| 500-site audit, after step 8 | 10 sites written since the first audit, 66 sentences, 8 cards | 66 SUPPORTED, 0 flags |

Fixed during the run, each test-first: the reviewer's DROP line for a later building, business or
institution that shares the site's name (reviewer pin `097c4589...`; group 5's 78 review questions
asked again under it); `revert4.py --site` and `audit4.py hold` (one written site taken back without
its batch); `verify_writes4.py --run` repeatable, since the pilot's and the mass run's writes share
the `phase4:` stamps (`ccfb426`), and read only batches holding a written site (`004d522`); T03 reads a
dot thousands separator (`9c8f5ef`, `9f01785`: "35.000 BC" on p4-0076 and "5.200 BC" on p4-0084 stopped
the review import and the gate, fail-closed, nothing written).

Open: lane L (marking the March-AI texts, re-planned after this run: 4,003 rows; being written);
the Phase-5 sitting and Push #2 (HUMAN_ONLY D5); the card_stats wave; the 19 `revision-too-fresh`
sites, which the runner re-queues itself 48 h after their hold (the first at
2026-09-26T21:30:14+00:00); the sealed final acceptance of 60 sites (`acceptance/PROTOCOL.md`; the
draw excludes this run's audit samples, `logs/p4_mass/midrun_sample.txt` and `audit500_sample.txt`).
The next 10-site audit is due at 1,000 mass sites written; 960 are.
