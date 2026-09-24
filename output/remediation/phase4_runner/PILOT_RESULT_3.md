# Phase-4 pilot 3 (2026-09-24): FAIL on T1, T4, T7 and T8

Fresh draw `PILOT3.jsonl` `a4fa2f5f...` (seed 20260925; the same 70 fixed members, new seeded draws),
thresholds unchanged (`PILOT_THRESHOLDS.md` `64ac5334...0fe0c13`), run directory
`runs/pilot3-2026-09-24`, the fixes of `PILOT_RESULT_2.md` in place plus the two decisions of
`64f5870` (cultural adjectives pass V10 per design entry [6]; the selector is told V6's pronoun rule
as rule 10). 87 selector questions (8 Opus agents, one at a time), 63 review questions (6 agents), the
independent audit of the 57 assembled sites (7 agents, never shown the selector's or reviewer's
reasoning): `pilot3_evidence/AUDIT_VERDICTS.json`. Holds and the run's ledger (381 lines: 231
unbilled S0-S1b lines, 87 selector and 63 reviewer lines, all `unmetered`) are in `pilot3_evidence/`.

| threshold | pilot 1 | pilot 2 | pilot 3 |
|---|---|---|---|
| T1 0 UNSUPPORTED | PASS | PASS | **FAIL (1)** - Stanydale Temple sentence 5, "Pottery sherds show that **it** was also occupied in the late Bronze Age ...": in the source *it* is the settlement of the unpicked sentence before; published after sentence 4 it reads as the temple building |
| T2 0 WRONG_SITE | FAIL (1) | PASS | PASS (0) |
| T3 0 lost hedges / flips | PASS | FAIL (1) | PASS (0) |
| T4 0 verifier false-passes | PASS | FAIL (2) | **FAIL (1)** - Dolebury Warren's card "Standing on a limestone ridge ..., **it** was made into a hill fort ...": V10's pronoun check reads only the card's first word, so a fronted phrase lets a dangling subject pronoun through |
| T5 broken <= 1 % | FAIL (1.25 %) | PASS (0.84 %) | PASS - 2 of 364 = 0.55 % (Stanydale above; Mam Tor "At a later stage", whose anchor sentence was not picked) |
| T6 cards | PASS | FAIL | PASS - 48 cards contained, 80-200 characters, no country, no marker, no missing glyph |
| T7 0 recurring gold errors | PASS | PASS | **FAIL (1)** - Partiscum (Castra), CANARY-03: "Partiscum was a fort in the Roman province of Dacia ... It is the most Western fort of Dacia", verbatim from the pinned lead, which the article's own body contradicts ("the territory of the Iazyges", "the presumed fort"); the card repeats it. In pilots 1 and 2 V6 held the site; pilot 2's name-base fix let it through |
| T8 >= 80 % lane-W eligible | FAIL (67.5 %) | FAIL (66.7 %) | **FAIL (57 of 78 = 73.1 %)**; before the review 63 of 78 (80.8 %) |
| T9 parse failures | 0 | 0 | 0 (cost unmetered: Opus through the handoff) |
| T10 writer | not reached | not reached | not reached |
| T11 / T12 lanes R / T | closed (searches off) | closed | closed |
| T13 MiniMax | not used | not used | not used |

Audit totals: 364 published sentences, 363 SUPPORTED, 1 UNSUPPORTED, 0 WRONG_SITE, 0 lost hedges, 0
flipped meanings, 2 broken; 48 cards, 1 carrying a canary error (Partiscum, counted under T7).

## The 21 held lane-W sites, one by one

* **Held correctly (the source or the record is the problem), 18:**
  * the article is about the modern place: Čertova pec, Neos Panteleimonas (canary), City of Enns,
    Clare, Suffolk, Ide, Devon and Starčevo (abstained); Argos, Peloponnese (abstained on the name)
  * the text dates the site outside its stored period (V14/T03 severe): Lindos, Himera, Reculver
  * no name or no material: Odeon Theatre ("the Odeon" only), Macedonian Tombs, Korinos (the
    article describes one tomb), Hellenistic Theatre of Dion, Purunllacta, Soloco (two sentences)
  * the reviewer dropped what the selector picked: Las Labradas (sentences about a river mouth, a
    port and the region's petroglyphs), Sidi Said (sentences about Volubilis and Roman history),
    Ffridd Faldwyn, Montgomery (source garbles such as "Montgomeryshire, It is sited"); Pločnik (the drop of "(archaeological site)" left
    "Pločnik is located in Pločnik"; the reviewer dropped it, V6 then held)
* **Held by a defect of the pipeline, 3:**
  * Lake Mungo - V14 reads "Wales" inside "New South Wales" as the country Wales
  * Mersinaki and Diana Fort - the reviewer dropped a sentence whose successor opens with a
    pronoun; V6 then held the site instead of the successor being dropped with it

By stratum: the fixed members 28 of 34 lane-W eligible, the random `draw-W` stratum 19 of 30
(63 %). With the three defects removed, coverage would be at most 60 of 78 (76.9 %): the gap to 80 %
is correct holds, not pipeline defects.

## Root causes and what closes them

* **T1 and T4 are one gap:** the pronoun rule (V6 for sentences, V10 for cards, selector rule 10)
  reads only the first word. A subject pronoun after a fronted phrase ("Standing on ..., it") or in a
  that-clause ("show that it was") depends on the unpicked sentence just the same.
* **T7:** a lead that the article's body contradicts or reduces to a presumption. Neither the
  selector's rules nor the reviewer's questions ask whether another sentence of the passage
  contradicts or hedges a picked one.
* **T8 defects:** V14's country regex lacks the sub-national names that contain a country name; the
  reviewer's DROP does not take a following pronoun-opening sentence with it.

Under the failure rule of `PILOT_THRESHOLDS.md` (T1, T4 and T7 failed): STOP, fix the causes,
re-pilot on a fresh draw in a new run directory. T8 is reported to the owner: the thresholds are
never loosened after the data is seen, and the correct holds alone keep coverage under 80 %.
Nothing was written to production.
