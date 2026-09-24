# Phase-4 pilot 2 (2026-09-24): FAIL on T3, T4, T6 and T8 - narrower than pilot 1

Fresh draw `PILOT2.jsonl` `9caaaa03...cc9f81c` (same 70 fixed members, 62 new seeded draws), thresholds
unchanged (`PILOT_THRESHOLDS.md` `64ac5334...0fe0c13`), run directory `runs/pilot2-2026-09-24`, the
fixes of `PILOT_RESULT_1.md` in place (selector rules 6-9, reviewer DROP rules, V6 names for a strong
'own' subject verdict). 87 selector questions (8 Opus agents), 54 review questions (5 agents), the
independent audit of 54 reviewed sites (6 agents): `logs/p4_pilot2/AUDIT_VERDICTS.json`.

| threshold | pilot 1 | pilot 2 |
|---|---|---|
| T1 0 UNSUPPORTED | PASS | PASS - 358 of 358 SUPPORTED |
| T2 0 WRONG_SITE | FAIL (1) | **PASS** (0) - the selector/reviewer rules hold |
| T3 0 lost hedges / flips | PASS | **FAIL (1)** - House of the Faun: a `p` drop removed "(actually a satyr, since the lower body is that of a man)", the passage's own correction |
| T4 0 verifier false-passes | PASS | **FAIL (2)** - V10 has no demonym table although the design promises one: "a Danish hill" (Agri Bavnehoj), "the first Greek site" (Bassae) pass |
| T5 broken <= 1 % | FAIL (1.25 %) | PASS (3 of 358 = 0.84 %) - Bejsebakke and Vindobala copy source garbles, Bassae keeps a mid-sentence full stop of the source; each still needs its rule gap closed |
| T6 cards | PASS | **FAIL** - the same two demonym cards name a country |
| T7 0 recurring gold errors | PASS | PASS |
| T8 >= 80 % lane-W eligible | FAIL (67.5 %) | **FAIL (52 of 78 = 66.7 %)** - lane-W holds V6 16, abstained 7, V14 6, V8 1 |

V9 holds fell from 16 to 0 (the selector now knows the length bounds). Remaining root causes: `p`
spans may carry a correction ("actually ..."); V10 lacks the design's demonym table; V5 does not catch a
mid-sentence ". lowercase" or a preposition directly before a comma; V6 still refuses a stored name
with a disambiguator ("Partiscum (Castra)", "Clare, Suffolk") under a strong 'own' verdict.
Nothing was written to production.
