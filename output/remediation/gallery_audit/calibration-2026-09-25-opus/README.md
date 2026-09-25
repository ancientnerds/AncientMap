# C1 calibration of the gallery audit - the Opus route (sealed 2026-09-25)

**Answering model: `anthropic/claude-opus-5-5 (Claude Code agent)`** (`vision.MODEL` =
`opus_handoff.OPUS_MODEL`): an Opus agent of the orchestrating Claude Code session reads each
question and its image from the Opus handoff directory and answers through
`scripts/remediation/opus_handoff.py answer`. No model API is called by the lane. Owner order,
Martin, 2026-09-23: "no DeepSeek any more - everything with Opus".

**Why this directory exists.** `../calibration-2026-09-23/` was sealed on 2026-09-23 04:10:40Z for
`deepseek-v4-flash-vision-exp` over the opencode gateway. Its run on 2026-09-23
produced no verdict: the gateway refused the first four questions with HTTP 401 ("Upstream request
failed: Invalid credential"), three attempts each, and the run stopped with exit 3. Those four
failed lines are kept as evidence of the failed attempt in
`../calibration-2026-09-23/failed-deepseek-401/VERDICTS.jsonl`; nothing of that attempt is read
here, and `calibrate.py` refuses to fix, ask or measure a directory sealed for another model.

**Sealed here before any question was exported** (`calibrate.py seal`, then `calibrate.py jobs`;
both sha256 in `SEAL.jsonl`, over these LF bytes):

| file | sha256 | what |
|---|---|---|
| `THRESHOLDS.json` | `e65604571e5b6717a4c13982039fa94c3d5646101f36b6d53eecde3cdddc61a2` | T0, T-kind, T-X1, T-X2, T-X3, T-strict, early gate, final acceptance (design entry 7); identical to the DeepSeek seal except `definitions.model` |
| `JOBS.jsonl` | `f0c4ccd6833f2de456e2d1ca110d2520ae6772cd9c3ebd4ec789a032de70e5c9` | the C1 sample: 939 questions, byte-identical to the DeepSeek seal's |

The sample: the gallery question (`gallery-v1`) on 889 images - the 200 pilot tiles, the 652
labelled rows (5 of them also tiles) and all 42 rows of the three gold galleries (12 gold-foreign,
13 gold-correct) - and the hero question (`hero-v1`) on the 50 tier-A pilot tiles.

**The round.** `calibrate.py vision --run-dir <this dir> --handoff-export H`; the Opus agents answer
every question in `H`; `opus_handoff.py validate --dir H` must be clean;
`calibrate.py vision --run-dir <this dir> --handoff-import H` writes `VERDICTS.jsonl`;
`calibrate.py evaluate --run-dir <this dir> (--eye-labels ... | --no-eye-labels)` writes
`ADMISSION.json`. No threshold changes after its data is seen; a trigger that fails is dropped, not
re-tuned.
