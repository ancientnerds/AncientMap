| # | request_id | topic | iterations | green | support findings | bundle | chain change |
|---|---|---|---|---|---|---|---|
| 1 | `6e51cdfc-2571-43d3-bdec-b8eb5831bbf6` | What caused the sudden onset of the Younger Dryas cold snap about 12,9 | 0 | yes | 0 | yes | |

## Run 1 (2026-10-05): research and text written in the session, not by a Theo run

**What changed in the chain.** The paper was researched and written in the mcode session
instead of by a Theo run on the VPS: 0 API calls instead of about 400 per paper. `theo_publish`
needs no dossier, only status `researched`, so the whole paper can be produced locally while
the studio's gates run unchanged. `scripts/paper24_seed.py` builds the workspace from a
research file (`dossier.json.gz`, `texts/`, `brief.md`) and counts the manifest numbers from
that file, so nothing is invented: `llm_calls: 0`, `total_tokens: 0`, `debate.rounds: 0`.

**Measured effect on the claims.** Before the rewrite, 26 of the 69 claims in the text carried
no source sentence; after rewriting them in the wording of their sources, 0 of 69 do. The
support gate went from 25 issues to 0.

**What the run measured, in numbers.**

- 32 sources, 1,090,523 characters of archived full text, 30 citable
- 69 claims, 6 angles, 6 investigation chapters, 3 mandatory chapters
- 6,304 prose words, 29 references, 49 evidence entries, 111 claim-check tasks
- 18 images, all 18 with licence, attribution, source URL and a caption; every one looked at
- every server gate green except `status`: the row is still `queued`

**Three gate rules this run taught the chain** (they are in the tools now, not in a paper):

1. Write numbers and units exactly as the source writes them (`20 y`, `12,870 ± 30 B.P.`,
   `12.8ka`, `Ma`, `°C`). Exactly one checkable detail per sentence passes; two or none fail.
2. The `structure` gate allows **2 to 4** investigation sections. This paper had 6 and had to
   merge two pairs (`What the impact hypothesis claims` + `The blind tests and the failed
   replications`, and `The crater, the correction and the retraction` + `From a boundary layer
   to a lost civilization`). A draft with 6 sections wastes a whole check cycle on this.
3. An image carries the paper only if someone looked at it. Of the first 97 candidates, 4
   opportunities had no image that showed their subject: a settlement map instead of a lake
   core, a photo of a magnet separator instead of the grains, an exhibition display instead of
   a laboratory, a generic Arctic seascape instead of icebergs. Better queries fixed all four.