# Gold-standard sample draw (written BEFORE any census output was opened)

Written: 2026-09-20, at the very start of the run, before `output/remediation/census.jsonl`,
`output/remediation/findings.jsonl` or any `output/remediation/run_*/` directory was read.
See `GOLD_STANDARD.md` §"Double-blind proof" for the file mtimes that document the order.

## Frame

Population: the 5,004 rows of `unified_sites` with `source_id = 'ancient_nerds'`, joined to
`card_stats` on `site_id`. Both read from the local snapshot
`output/remediation/snapshot/{unified_sites,card_stats}.jsonl.gz`
(exported 2026-09-20T20:20:01+02:00 from the production host, see `snapshot/MANIFEST.txt`).
No database was touched.

Frame size: 5,004 sites, 5,004 `card_stats` rows (0 sites without a card_stats row).

## Strata: measured `rarity_tier` distribution

| tier | sites | share |
|---|---|---|
| 1 | 525 | 10.49 % |
| 2 | 1,796 | 35.89 % |
| 3 | 2,310 | 46.16 % |
| 4 | 353 | 7.05 % |
| 5 | 20 | 0.40 % |

## Allocation (n = 36, the plan's 30-40 with tiers 4/5 over-weighted)

The pilot (plan §2) over-weighted tiers 4/5 at 25 % against a population share of 7.45 %.
This sample keeps that ratio exactly: 25 % of 36 = **9 sites from tiers 4+5**.

The remaining 27 sites are allocated proportionally to the tier shares *within tiers 1-3*:

| tier | population (t1-t3) | share | allocated |
|---|---|---|---|
| 1 | 525 | 11.33 % | 3 |
| 2 | 1,796 | 38.78 % | 10 |
| 3 | 2,310 | 49.88 % | 14 (13.47 rounded up to close the sum) |

| tier | population | sampled | design weight (N_h / n_h) |
|---|---|---|---|
| 1 | 525 | 3 | 175.0 |
| 2 | 1,796 | 10 | 179.6 |
| 3 | 2,310 | 14 | 165.0 |
| 4 | 353 | 7 | 50.43 |
| 5 | 20 | 2 | 10.0 |
| total | 5,004 | 36 | — |

The raw (unweighted) error and false-negative counts are reported alongside an
inverse-probability-weighted estimate, weight `w_h = N_h / n_h` per tier (plan §2 names the
missing weighting as a known weakness of the pilot).

## Selection rule (reproducible)

1. Read `unified_sites` from the snapshot, keep `source_id == 'ancient_nerds'`.
2. Join `card_stats.rarity_tier` on `site_id`. Every site has a tier; no site was dropped.
3. Within each tier, sort site ids ascending as strings (UUID text) — this removes any file-order
   or dict-order dependence.
4. For tier in `[5, 4, 3, 2, 1]` (descending, so the small strata are drawn first and a partial run
   still covers the over-weighted tiers), take `random.Random(20260920).sample(sorted_ids, k)`.

Seed: **20260920**. RNG: CPython `random.Random` (Mersenne Twister), `random.sample` (no
replacement). Re-running the script below on the same snapshot reproduces the sample exactly.

Script: `output/remediation/gold_scratch/draw_sample.py`
Output:  `output/remediation/gold_standard/sample.json`

## What is NOT in the frame

- The 28 other `source_id` values (1,754,672 rows) — out of scope per plan §0/§1.2 E2.
- Sites with a missing `card_stats` row — there are none.
- No row was excluded because it already looked clean or already looked broken. Exclusions would
  bias the false-negative rate.
