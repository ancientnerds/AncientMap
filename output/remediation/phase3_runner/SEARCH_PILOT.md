# The search route's pilot (W9): thresholds fixed before the first search

Written 2026-09-23, before any MiniMax search or model call of the pilot. The sha256 of this file
is recorded in `output/remediation/AUDIT_LOG.md` together with the results, so the thresholds
cannot be moved after the numbers are known.

## What is measured

The plan `PLAN.search-gold.jsonl` (built 2026-09-23 from a fresh read-only export; sha256
`6da329af7f5317fcde67d960f26f9b49ed03f553ed0b3ec24f3f60059c506ff2`) reruns, with MiniMax search
hits added to the evidence, the **59 fields the mass run's finder called UNVERIFIABLE on the 26
gold-standard sites that have such fields** (48 searches). For every one of them a human verdict
exists in `output/remediation/gold_standard/`.

## Pass thresholds (all must hold)

1. **No fabricated citation.** 0 finder answers whose quoted source text is not in the evidence
   the finder was shown (`discover_stage.source_problems`, the writer's RULE_CITATION check).
2. **No harmful decision.** 0 fields decided WRONG by the finder, *not* refuted by the reviewer,
   where the human verdict is CORRECT. (A WRONG the reviewer refutes is not written.)
3. **Agreement.** Of the fields the pipeline decides (finder CORRECT, or finder WRONG that the
   reviewer does not refute), at least 90 % agree with the human verdict.
4. **Transport.** Every search ends in a stored result or a recorded failure; 0 slots unaccounted
   for; the run is not stopped by an auth or contract error.

## Reported, not gated

- The share of the 59 fields that move from UNVERIFIABLE to a decision (the lever itself).
- The quota cost of the 48 searches: `weekly_remains_tokens` before the first and after the last
  batch, an upper bound because Lyra and Theo share the key (Theo idle at the start: 0 running).
- Search latency, hits per search, and the one query that still carries the value under test.

## If a threshold fails

The mass search run does not start. The failure is recorded here and in `AUDIT_LOG.md` with the
cases, and the cause is fixed (query wording, evidence shape, or the route itself) before a new
pilot with a new run directory.
