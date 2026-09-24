# Phase-4 pilot 1 (2026-09-24): FAIL on T2, T5 and T8 - stop, fix, re-pilot on a fresh draw

Sealed artefacts: `PILOT.jsonl` `7f66f987...e063fc`, `gold_prose_errors.json` `e4e63d56...74ebb7df`,
`PILOT_THRESHOLDS.md` `64ac5334...0fe0c13` (sealed 01:29:41, before the first export 01:30:25).
Run directory `runs/pilot-2026-09-24` (p4-0001..p4-0009), answering model Opus through the handoff
(owner order 2026-09-23), searches off (owner order: everything with Opus - no MiniMax).

Flow: 132 sites; S1b lanes W 77, S 19, 0 36 (33 search-stopped, 3 scope-pending); 91 selector
questions answered by 8 Opus agents; verify4 held 42 more; 55 review questions answered by 5 Opus
agents; 53 sites reviewed; the independent audit (6 Opus agents that never saw the selector's or
reviewer's reasoning) judged every published sentence and card: `logs/p4_pilot/AUDIT_VERDICTS.json`.

| threshold | result |
|---|---|
| T1 0 UNSUPPORTED | PASS - 318 of 319 sentences SUPPORTED, 0 UNSUPPORTED |
| T2 0 WRONG_SITE | **FAIL - 1**: Orolik sentence 1 describes the modern village (its municipality and county), not the La Tene site of the record |
| T3 0 lost hedges / flipped meanings | PASS - 0 |
| T4 0 verifier false-passes | PASS - 0 |
| T5 broken sentences <= 1 % | **FAIL - 4 of 319 = 1.25 %**: dangling definite references (Condorcaga "the mountain", Kit Hill "Other notable artifacts", Peppercombe Castle "the valley", Ocriticum "the via glareata / the fornax calcaria") |
| T6 cards | PASS - 47 cards, all contained, 80-200 characters, no country, no marker |
| T7 0 recurring gold/canary errors | PASS - 0 |
| T8 >= 80 % of lane-W write-eligible | **FAIL - 52 of 77 = 67.5 %** (lane-W holds: V6 15, V9 8, V14 4, abstained 1) |
| T9 cost / parse failures | cost unmetered (Opus, subscription); 0 parse failures |
| T10 writer | not reached (no write before a passing pilot) |
| T11 / T12 lanes R / T | closed: no search (owner order), no site in either lane - their sites stay held |
| T13 MiniMax | not used |

Root causes (traced, one each):
* **T2** - V6 requires sentence 1 to name the site; where only the article's modern-settlement
  sentence carries the name, the selector is pushed to it, and the reviewer's question "is it about
  this site" did not catch a sentence about the modern administrative place.
* **T5** - the selector may pick a sentence whose definite reference ("the valley", "Other notable
  ...") rests on an unpicked sentence; neither the selector's rules nor the reviewer's questions name
  that case.
* **T8** - V6 knows only the stored name and aliases; stored names such as "Beacon Hill, Burghclere,
  Hampshire" or "Odeon Theatre" never occur verbatim, although the subject gate already tied the
  pinned article to the site. V9: the selector is not told the 200-1100 character bounds.

Under the failure rule of `PILOT_THRESHOLDS.md` (T1-T7 failed): STOP, fix the causes, re-pilot on a
fresh draw of the same strata in a new run directory. Nothing was written to production.
