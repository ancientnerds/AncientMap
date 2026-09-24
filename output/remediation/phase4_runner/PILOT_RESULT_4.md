# Phase-4 pilot 4 (2026-09-24): T1-T7 PASS; T8 reported (79.7 %); T10 next

Fresh draw `PILOT4.jsonl` `30ab5e9d...` (seed 20260926; the same 70 fixed members, 62 new draws that
exclude all earlier ones), thresholds unchanged (`PILOT_THRESHOLDS.md` `64ac5334...0fe0c13`), run
directory `runs/pilot4-2026-09-24`, the fixes of `PILOT_RESULT_3.md` in place (the pronoun rule past
the first word in V6, V10, selector rule 10 and the reviewer; selector rule 11 and the reviewer's
DROP line on a sentence the article contradicts, with the whole passage shown to the reviewer; V14's
sub-national names; the review's followed drops; rule 7 stating V6's name match). 90 selector
questions (8 Opus agents, one at a time), 66 review questions (6 agents), the independent audit of
the 64 assembled sites (8 agents, never shown the selector's or reviewer's reasoning):
`pilot4_evidence/AUDIT_VERDICTS.json`. Holds and the run's ledger (385 lines: 229 unbilled S0-S1b
lines, 90 selector and 66 reviewer lines, all `unmetered`) are in `pilot4_evidence/`.

| threshold | pilot 1 | pilot 2 | pilot 3 | pilot 4 |
|---|---|---|---|---|
| T1 0 UNSUPPORTED | PASS | PASS | FAIL (1) | **PASS** - 368 of 368 SUPPORTED |
| T2 0 WRONG_SITE | FAIL (1) | PASS | PASS | **PASS** (0) |
| T3 0 lost hedges / flips | PASS | FAIL (1) | PASS | **PASS** (0 / 0) |
| T4 0 verifier false-passes | PASS | FAIL (2) | FAIL (1) | **PASS** (0) |
| T5 broken <= 1 % | FAIL (1.25 %) | PASS (0.84 %) | PASS (0.55 %) | **PASS** (0 of 368) |
| T6 cards | PASS | FAIL | PASS | **PASS** - 52 cards contained, 80-200 characters, no country, no marker, no missing glyph |
| T7 0 recurring gold errors | PASS | PASS | FAIL (1) | **PASS** (0) - every gold or canary site is written clean or held with a closed-list reason |
| T8 >= 80 % lane-W eligible | 67.5 % | 66.7 % | 73.1 % | 63 of 79 = **79.7 %**, reported, not gating (owner decision of 2026-09-24 in `PILOT_RESULT_3.md`) |
| T9 parse failures | 0 | 0 | 0 | **0** (cost unmetered: Opus through the handoff) |
| T10 writer | not reached | not reached | not reached | next: P4/P5 rehearsal, the pilot write, acceptance |
| T11 / T12 lanes R / T | closed | closed | closed | closed (searches off): their sites stay held |
| T13 MiniMax | not used | not used | not used | not used |

The 16 held lane-W sites: the article is about the modern place or never names the site (Odeon
Theatre, Čertova pec, Neos Panteleimonas, City of Enns, Argos, Peloponnese, Clare, Suffolk, Pheia,
Elis, Ancient City of Troy - abstained); the reviewer kept too little (Las Labradas, Cave of Mayrières
Supérieure); a date or country the record contradicts (Zoque Culture Archaeological Zone, T03
severe; House of Taga, "United States" against the stored Northern Mariana Islands); a pronoun chain
the review broke (Gog Magog Hills, V6); a shorter text replacing a stored one no test proved
defective (Brewer's Castle, Dumpdon Hill, Gaya Tumuli, V9 - this hold cannot occur for the defect
sites of the mass run, whose stored text is proven defective). The random `draw-W` stratum: 24 of 30
eligible.

The pilot passes T1-T7 and T9; only lanes W and S open. Nothing has been written to production yet.
