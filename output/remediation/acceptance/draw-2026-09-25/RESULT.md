# Phase-6 acceptance, `draw-2026-09-25`: FAIL (A3, check D1)

Written by hand on 2026-09-25. `judge.py result` cannot write this result: it scores a finished run
and needs the final records of every stage (`judge._final_records` refuses a stage that was never
imported), and no question of this run was ever answered.

## Outcome

**FAIL** under `PROTOCOL.md` (sha256 `f40fac87230a26e7b1a4818e9d50d16dedfcb6936fc795b532e2cb35789f8bff`),
section 9, rule **A3**: "0 failures of D1-D6". The deterministic check **D1** fails on one of the 60
drawn sites. That settles the run: no verdict of stages 1-3 can turn it into a PASS.

Stages 1-3 (sections 6-7) were **not run**. Stage 1 was exported (653 questions in 54 batches,
2026-09-25 15:34:10 UTC, `output/remediation/handoff/acceptance-2026-09-25-s1`) and got **0 answers**.
Its verdicts could have ended the run only as FAIL, or as VOID under a validity rule. Section 10
prescribes the same next step for both: a fresh draw with the next seed. **No artefact of this run
is reused**: not its sample, its questions, its canaries or any verdict.

## The D1 evidence

`SAMPLE.jsonl` holds the frozen values. Their D1 reading is in `DETERMINISTIC.json`, written by
`judge.py deterministic`, checked 2026-09-25 15:34:43 UTC:

* **Kuntur Amaya** (`fc514046-4f2c-42b1-a3f6-ca88404d2e18`, Bolivia):
  `markers without an entry [], entries never cited [1]`.
  * The description has **no `[N]` marker**. It starts "Kuntur Amaya is an archaeological
    necropolis in Bolivia's La Paz Department, Aroma Province, Umala Municipality, near
    Wayllani." and has 440 characters.
  * `raw_data.description_citations` holds **entry 1**:
    `{"n": 1, "url": "https://en.wikipedia.org/wiki/Kuntur_Amaya", "title": "Kuntur Amaya", "domain": "en.wikipedia.org", "claim": "Location, chullpas, National Monument status, and date of declaration"}`.
  * This is census T08's `no-markers` class. The docstring of
    `scripts/remediation/census/tests/t08_citation_markers.py` names this site. The text is the
    March text that lane L marked: `_description_provenance` lane `L`, `desc_sha256`
    `475f7d08df7ed30600ca9cab5e754b1d9a844fd23099457c1e0c46305b3ee9a4`.

## The deterministic checks (section 8)

| check | result |
|---|---|
| D1 markers and entries agree | **fails on 1 of 60** (above) |
| D2 `period_name` is the bucket of `period_start` | holds on 60 |
| D3 `civilization` equals `country` | holds on 60 |
| D4 the provenance hashes | holds on 60 |
| D5 `name_normalized` is Postgres's key | holds on 60 |
| D6 production | holds: 0 curated sites outside E3 without a decision; 78 retired, none of them among the 4,926 `ancient_nerds` sites `/api/sites/all` served |

## Validity (section 9), as far as it was read

* **V1** (every question has a counted verdict) and **V2** (at least 9 of 10 canaries confirmed):
  not assessed, because no question was answered.
* **V3** (no remediation write on a drawn site after the draw): **holds**. Read-only at 2026-09-25
  15:51:53 UTC: the journal's maximum id is still the draw's high-water mark 73180. No row above
  it exists on any site.

## What follows (section 10)

Stop. The D1 class is root-caused, measured over every curated site, and repaired through a
journalled lane: AUDIT_LOG, 2026-09-25, "Acceptance draw-2026-09-25 ends FAIL on A3 (D1)". Then
comes a fresh acceptance on a new draw under the same thresholds: seed **20260926**, canaries
**20260927**, excluding this draw's 60 sites.

## Files of the run (sha256 over LF bytes)

| file | sha256 | committed |
|---|---|---|
| `DRAW.json` | `09b33ab034199d2332612d7d7d8019ca84f37eca823e3b00c279f6d6ccbe1b7f` | at the draw |
| `FRAME.jsonl` | `c60624588173cb87b52f2cf4e19b1492bd24e04743050af647339c099e06ee3a` | at the draw |
| `EXCLUDED.json` | `2589b69482a8c0ec3c64d6edf4dec21f019638e194962c6f60a504b3be444a89` | at the draw |
| `SAMPLE.jsonl` | `9511373575fc7cd603da8e149d04afedd63c8755cba81e7907a0fb03748e2097` | at the draw |
| `CANARIES.jsonl` | `c25821753fdb4dede2172d77809c8175f4ae8a0325b43c0e61a0647d07b1f34c` (the pin in `DRAW.json`) | with this result |
| `DETERMINISTIC.json` | `2a5763453d755b79ebccc76d9513201dbe0512f3fbfd91c33c7317cabfac3e6e` | at the check |
| `DETERMINISTIC_EXPORT.jsonl` | `4565c85103b8ee64291a3cc380df6f9b3d9306de434c2f8d6c300fdf10cb7bfe` | at the check |
| `judging/QUESTIONS.jsonl` | `1ad7e9bfe996b00d6eaf07f8bd0caec260681f2ae8fa85138de96693947e280c` | local (gitignored) |
| `judging/ROUNDS.jsonl` | `cc3218281021f50a9a260dce2e69716e0d14d0c68b4c891044991f9b1db729a2` | local (gitignored) |
