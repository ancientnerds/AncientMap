# Run notes of the 24-paper campaign

The table in [theo-24-run-ledger.md](theo-24-run-ledger.md) is written by
`paper24 ledger` from the reports on disk. This file holds what a run taught the
chain: the change it caused and the rules the next run must not learn again.

## Run 1 — Younger Dryas (`6e51cdfc-2571-43d3-bdec-b8eb5831bbf6`), 2026-10-05

**Chain change: research and text in the mcode session, not a Theo run on the VPS.**
0 API calls per paper instead of about 400. `theo_publishing.publish_paper` needs no
dossier, only status `researched`, so a workspace built from this session's research
passes the same studio gates unchanged. `scripts/paper24_seed.py` builds the workspace
from a research file (`dossier.json.gz`, `texts/`, `brief.md`) and counts the manifest
numbers from that file: `llm_calls: 0`, `total_tokens: 0`, `debate.rounds: 0` are what the
file says, not what a server run would have produced.

**Measured:** before the rewrite 26 of the 69 claims carried no source sentence, after it
0 of 69; the support gate went from 25 issues to 0. 32 sources, 1,090,523 characters of
archived full text, 30 citable. 6,304 prose words, 29 references, 49 evidence entries,
111 claim-check tasks, 18 images. Every server gate green but `status`, which needed the
owner's release.

**Published 2026-10-05 16:50 UTC** after that release: slug
`the-younger-dryas-impact-hypothesis`, `published_by = Theo`, journal row 115 in
`theo_paper_publications` (bundle sha256 `ef6a228e…`, side effects recorded), IndexNow
ok, Qdrant ok with 7 sections, page answers HTTP 200 with all 49 evidence anchors.

### Three gate rules this run taught the chain

1. **Write numbers and units exactly as the source writes them** (`20 y`, `12,870 ± 30
   B.P.`, `12.8ka`, `Ma`, `°C`). Exactly one checkable detail per sentence passes the
   gates; two or none fail. Two markers in one sentence force both sources to carry every
   number.
2. **The `structure` gate allows 2 to 4 investigation sections.** This paper had 6 and had
   to merge two pairs: `What the impact hypothesis claims` + `The blind tests and the
   failed replications`, and `The crater, the correction and the retraction` + `From a
   boundary layer to a lost civilization`. A draft with more than four wastes a whole
   check cycle on this. Merging changes the section label of every paragraph below the
   removed heading, which invalidates both the image tasks and the claim-check tasks for
   those sections — expect one extra cycle and reuse the verdicts per image file instead
   of looking at the pictures again.
3. **An image carries the paper only if someone looked at it.** Of the first 97
   candidates, four opportunities had no image showing their subject: a settlement map
   instead of a lake core, a photo of a magnet separator instead of the grains, a museum
   display instead of a laboratory, a generic Arctic seascape instead of icebergs. Better
   queries fixed all four. `meaningful` must mean the picture shows the subject; a title
   is data, not proof.

## Remaining topics (20, `status = 'queued'`, oldest first)

| # | request_id | question (cut) |
|---|---|---|
| 1 | `6c639144-47b7-4c71-b9e3-912d00733306` | recurring sky-figures in rock art, reception or pattern? |
| 2 | `b2b6be16-7463-41f1-a30f-a89d627b7b4e` | historical provenance of the Kybalion (1908) |
| 3 | `59468f64-156f-48ab-8bc9-05ce099bc53e` | Electric Universe / Birkeland currents, narrow scope |
| 4 | `ad9fe380-706a-4d71-98b6-76e65a1c1447` | internal physics of a cosmological mystery novel, two-sided |
| 5 | `0a1ace5c-876b-437e-b8d1-1c122ba2cd00` | precise two-sided science briefing |
| 6 | `831af2e1-ae58-48af-bcc4-c5b0bb198ff2` | blind seer, true seeing as absence of grasping |
| 7 | `5c422c52-11bc-46aa-aa90-3ed0776d664a` | two opposed esoteric doctrines of mind reaching reality |
| 8 | `b5bd37ec-b025-4b1c-927f-03fbae6f19b2` | megaliths as tuned stone antennas |
| 9 | `35090cb9-76ef-47c9-adff-3b2900901123` | Schumann resonance, two fields |
| 10 | `e3c4950b-a0de-4253-ab5b-63a30c1a9af0` | Neolithic stone chambers tuned to resonate |
| 11 | `b9713d8f-0353-4679-92e4-9b265e0c179a` | does catastrophe arrive by schedule |
| 12 | `925f3887-6186-48b5-831b-1630d24ae4d2` | are Earth's catastrophes timed by a cycle |
| 13 | `66f439fb-bd26-4713-8849-7b83e30a8ef3` | magnetic-field collapses and mass extinction |
| 14 | `a86db42a-074f-4379-956a-0ce3cb68825c` | rigorous two-sided citation-heavy briefing |
| 15 | `4b08117b-4bd1-46eb-bd04-a8af957139bd` | deceptive cosmic force masquerading as contact |
| 16 | `75c3731d-6584-4e98-aa3a-884e22793b20` | the 'chemical gate' premise, two-sided |
| 17 | `5b018384-318e-4db7-bb30-8ea76aeeb593` | higher reality read downward, never forced upward |
| 18 | `536f3f41-c017-4396-8312-9784e4383f4e` | careful two-sided science briefing |
| 19 | `39eb9e0f-8170-472f-9572-f81776f0edb4` | two esoteric time-shapes that cannot both hold |
| 20 | `238147d2-f1f8-42f6-9eb5-afc594b20351` | what ends a world-age: external physics or inner |

Not to be touched: the `paused`, `cancelled` and `failed` rows of this user, the one row in
`running`, and every row that is already `completed` with `is_public = true`.

## Run 2 — Rock art sky figures (`6c639144-47b7-4c71-b9e3-912d00733306`), 2026-10-05

**Measured:** 51 archived full texts (23 Europe PMC, 29 Wikipedia), 1,373,820 characters,
42 of them cited. 5,304 prose words, 42 references, 24 evidence entries, 120 citations,
67 claim-check tasks all answered, 9 verified images (the floor is one per section and
there are seven). Score 96, every gate green.

**What the first draft cost.** The first `paper check` was red on eight gates at once:
`artifact` (9 paragraphs over 50 characters carrying no marker), `structure` (3 hook
paragraphs, 4,682 words against a floor of 5,000), `meta` (the title ended on `?`),
`specifics` (2 unmatched), `coherence` (a title term absent from the body), `claims` (64
tasks unanswered), `hero` (no image), `quality`. Not one of them was a research failure.
Every one was a writing-rule failure, and every one was visible before a single model
call — the same argument Run 1 made for running `check` before the claim check, now with
a second data point.

### Six rules this run added

1. **A paragraph of pure argument is an uncited paragraph.** Nine paragraphs longer than
   fifty characters had no marker, because an argument cites nothing and the audit counts
   it anyway. They were folded into the neighbouring cited paragraph
   (`C:\tmp\theo_opt\edit_draft2.py`, the `fold_uncited` step). The folding has a second
   order effect: folding a paragraph in front moves the start of the one behind it, and an
   **anchor is a prefix**, so all 24 evidence anchors were re-derived afterwards
   (`repair_anchors.py`). Do every fold before writing `evidence.json` or
   `images/opportunities.json`, or expect to re-derive both.
2. **`specifics` compares against the source's own wording, so never paraphrase a proper
   noun.** The draft read "the site is National Treasure No. 285 of South Korea"; the
   Bangudae article writes "They are the National Treasure of South Korea No. 285". The
   capitalised run `National Treasure No` became a `person` specific and did not occur in
   the cited text. The second finding was a term carried in from elsewhere: `Upper
   Palaeolithic` sat in a paragraph citing the radiocarbon paper, which never writes it.
   Both were fixed by using the source's own sentence.
3. **The title may not contain a colon either.** `gate_meta` forbids `?`, `:`, dashes and
   quotes, and the reported problem names only the character found. A comma does the job
   the colon was meant to do. The multi-word title terms must then appear verbatim in the
   body: `Sky Figures in Rock Art, Message or Projection` requires `Sky Figures` and
   `Rock Art` (the comma splits the fragments, `in` and `or` split further, single words
   are dropped).
4. **A fold can drag a word into a paragraph with other sources.** `Mentalist` was a
   harmless capitalised word in its own uncited paragraph; folded into the constellation
   paragraph it became `person: Mentalist` against two sources that do not write it. A
   fold is not textually free.
5. **The hook is 1 to 2 paragraphs, and the third one cannot be folded away by the marker
   rule.** It carried markers of its own, so the rule left it alone and `structure` stayed
   red. The hook is counted separately and has to be planned as two.
6. **A quote chosen by word overlap is a ranking, not a judgement.** 14 of the 67
   verdicts had no locatable sentence and fell back to the best-overlap window. Two of
   those quoted the article header glued to the first sentence (`Scientific reports 2023
   / ## Introduction`), and three quoted a neighbouring sentence about something else. The
   windows are now single-line sentences only, and three quotes were read by hand and
   written in. The coherence answer was the same shape of risk and worse: it was
   hardcoded in `paper24_verdicts.py` in paper 1's own words (`the onset is 12,870 ± 30
   B.P.`), so it would have stamped paper 1's reasoning onto paper 2. It is now read from
   `--coherence-note-file` and the command refuses to run without it.

### What this means for an autonomous writer on the VPS

Every rule above except 6 is **already a gate**: `audit_citations` counts the uncited
paragraphs, `gate_structure` counts the hooks and the words, `gate_meta` checks the title
characters, `gate_specifics` checks the wording against the source text, `gate_coherence`
checks the title terms, and the evidence and image checks resolve the prefix anchors. A
writer that is forced through `paper check` cannot ship any of them. The gap is not the
gate — it is that nobody has written a writer spec that produces a draft passing these
gates on the first try, so every one of these costs a check cycle today.

What such a spec has to say, in the order the costs came in: put every argument in a cited
paragraph rather than in a paragraph of its own; write a proper noun the way the source
writes it; plan the hook as two paragraphs and the title without a colon; plan the fold
before writing `evidence.json`; and quote by hand every sentence the locator cannot find.

## State of the production rows (measured 2026-10-05 18:55 CEST)

31 `completed`, 20 `queued`, 1 `running`, 1 `failed`, 2 `paused`, 2 `cancelled` for
`user_id = '442000112756064260'`. Before the first publish of this campaign it was 30
`completed` and 21 `queued`; only one row was written by hand, the guarded
`UPDATE … SET status = 'researched' WHERE id = … AND status = 'queued'` the publish needs.
The publish itself set `completed`, `is_public`, `published_at`, `published_by` and the
slug in its own transaction, journal row 115.