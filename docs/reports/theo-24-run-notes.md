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

## Remaining topics (19, `status = 'queued'`, oldest first, measured 2026-10-05 22:20 UTC)

| # | request_id | question (cut) |
|---|---|---|
| 1 | `b2b6be16-7463-41f1-a30f-a89d627b7b4e` | historical provenance of the Kybalion (1908) |
| 2 | `59468f64-156f-48ab-8bc9-05ce099bc53e` | Electric Universe / Birkeland currents, narrow scope |
| 3 | `ad9fe380-706a-4d71-98b6-76e65a1c1447` | internal physics of a cosmological mystery novel, two-sided |
| 4 | `0a1ace5c-876b-437e-b8d1-1c122ba2cd00` | precise two-sided science briefing |
| 5 | `831af2e1-ae58-48af-bcc4-c5b0bb198ff2` | blind seer, true seeing as absence of grasping |
| 6 | `5c422c52-11bc-46aa-aa90-3ed0776d664a` | two opposed esoteric doctrines of mind reaching reality |
| 7 | `b5bd37ec-b025-4b1c-927f-03fbae6f19b2` | megaliths as tuned stone antennas |
| 8 | `35090cb9-76ef-47c9-adff-3b2900901123` | Schumann resonance, two fields |
| 9 | `e3c4950b-a0de-4253-ab5b-63a30c1a9af0` | Neolithic stone chambers tuned to resonate |
| 10 | `b9713d8f-0353-4679-92e4-9b265e0c179a` | does catastrophe arrive by schedule |
| 11 | `925f3887-6186-48b5-831b-1630d24ae4d2` | are Earth's catastrophes timed by a cycle |
| 12 | `66f439fb-bd26-4713-8849-7b83e30a8ef3` | magnetic-field collapses and mass extinction |
| 13 | `a86db42a-074f-4379-956a-0ce3cb68825c` | rigorous two-sided citation-heavy briefing |
| 14 | `4b08117b-4bd1-46eb-bd04-a8af957139bd` | deceptive cosmic force masquerading as contact |
| 15 | `75c3731d-6584-4e98-aa3a-884e22793b20` | the 'chemical gate' premise, two-sided |
| 16 | `5b018384-318e-4db7-bb30-8ea76aeeb593` | higher reality read downward, never forced upward |
| 17 | `536f3f41-c017-4396-8312-9784e4383f4e` | careful two-sided science briefing |
| 18 | `39eb9e0f-8170-472f-9572-f81776f0edb4` | two esoteric time-shapes that cannot both hold |
| 19 | `238147d2-f1f8-42f6-9eb5-afc594b20351` | what ends a world-age: external physics or inner |

The list was missing one row: `5b5f5803` was queued since 2026-07-05 10:09:48 and never made
it into the table of run 1, so the twenty rows below the headline of that table were not the
twenty rows the database held. Read the ids from `research_requests.question`, ordered by
`created_at`. Run 3 took `5b5f5803` out of this list.

Not to be touched: the `paused`, `cancelled` and `failed` rows of this user and every row
that is already `completed` with `is_public = true`. That is `afe7c26a` and `20091a97`
(paused), `6050b8ac` and `97397c12` (cancelled, both created after the batch) and
`aa881bfc` (failed).

## Run 2 — Rock art sky figures (`6c639144-47b7-4c71-b9e3-912d00733306`), 2026-10-05

**Measured:** 51 archived full texts (23 Europe PMC, 28 Wikipedia), 42 of them cited.
5,304 prose words, 42 references, 24 evidence entries, 120 citations, 67 claim-check tasks
all answered, 13 verified images. Score 96, every gate green.

**Published 2026-10-05 18:44 UTC** after the owner's release: slug
`sky-figures-in-rock-art-message-or-projection`, `published_by = Theo`, journal row 116,
IndexNow ok, Qdrant ok with 7 sections, page answers HTTP 200 with 24 evidence anchors.
99 candidates were looked at over two image rounds.

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
7. **The publish gate takes only `verified` images; the studio import does not.**
   `images-import` fills every opportunity with the first `meaningful` or `weak` candidate
   it finds and prefixes a weak one with `Illustration:`, so a green `paper check` said
   nothing about the publish. `theo_publish` refused with `pictures`: "nobody has opened
   this picture" for each of the five weak ones. Six of the fifteen opportunities had no
   meaningful candidate at all; rewriting five subjects (an alchemical emblem is not the
   Emerald Tablet, a Dobson map is not a curve in per cent) and dropping one raised the count
   from 9 to 13. The studio and the server disagree about what a picture is for, and the
   server is right: **budget a second image round, and give every opportunity a subject a
   photograph can literally satisfy.**
8. **A new image set re-asks exactly one claim-check task.** The coherence task lists every
   measurement of the paper, and the numbers in the image captions are measurements, so the
   second import invalidated `coherence:numbers` and nothing else. `claims-export` then
   reported 66 accepted, 1 pending: re-answer that one instead of the whole paper.

### What this means for an autonomous writer on the VPS

Every rule above except 6 is **already a gate**: `audit_citations` counts the uncited
paragraphs, `gate_structure` counts the hooks and the words, `gate_meta` checks the title
characters, `gate_specifics` checks the wording against the source text, `gate_coherence`
checks the title terms, the evidence and image checks resolve the prefix anchors, and
`theo_publish`'s `pictures` gate rejects every picture nobody looked at. A writer that is
forced through `paper check` **and** `theo_publish --dry-run` cannot ship any of them. The
gap is not the gate — it is that nobody has written a writer spec that produces a draft
passing these gates on the first try, so every one of these costs a check cycle today.

What such a spec has to say, in the order the costs came in: put every argument in a cited
paragraph rather than in a paragraph of its own; write a proper noun the way the source
writes it; plan the hook as two paragraphs and the title without a colon; plan the fold
before writing `evidence.json`; give every image opportunity a subject a photograph can
literally satisfy; and quote by hand every sentence the locator cannot find.

## Run 3 — Mentalism and the measurement problem (`5b5f5803-40ff-4cde-aeba-0cffdacc93a9`), 2026-10-05

**Measured:** 47 archived full texts (20 Europe PMC, 27 Wikipedia), 2,624,575 characters,
83 claims over 6 angles, 24 of them citable. 5,255 prose words, 4 investigation sections,
1 hook paragraph, 86 citations, 20 references, 62 claim-check tasks all answered in one
round, 9 verified images, score 96.

**Published 2026-10-05 20:02 UTC** after the owner's release: slug
`mentalism-the-double-slit-and-the-measurement-problem`, `published_by = Theo`, journal
row 117, IndexNow ok, Qdrant ok with 7 sections, page answers HTTP 200 with 26 evidence
anchors. Discord stays off because the owner keeps `DISCORD_WEBHOOK_URL` unset.

**Chain change: none, and that is the finding.** Run 2 ended with eight rules and an
ordered list of what a writer spec must say. This run wrote the draft to that list and
every text gate was green before the first `paper check`: 1 iteration on the report, 1
claim round, 3 image rounds. The costs of run 1 and run 2 were not research costs and
not gate costs. They were the cost of writing a draft without knowing the rules.

### Three rules this run added

1. **A quote the locator cannot find is a sentence written wrong, not a missing quote.**
   Run 2's rule 6 answered 14 of 67 unlocatable quotes by hand. This run wrote the
   sentence so the source carries it, and 5 of them were fixed by rewriting the sentence
   in the terms the source uses; 3 still needed a hand-picked quote. So the order is
   wrong: try the sentence first, hand only what survives it. Hand-picking a quote is the
   last resort, not the method.
2. **`paper24_markersync` finds the numbers before `paper check` does.** It compares every
   marker in the draft against the source it names and names the marker and the value
   that is missing. That is `number_exact` from the support gate, run as a cheap report
   over one file, so a draft can be repaired before a full gate cycle.
3. **A hero can come from the paper's own oldest layer.** The first paper's hero was a
   crater, the second's a painted figure, this one's is de Bry's woodcut of Hermes
   Trismegistus (`s29751d5e_Mercurius_Trismegistus_Tractatus_posthumus_de_divinatione_magicis-12.jpg`,
   public domain). The paper argues that the mentalist vocabulary was assembled from
   older layers, so the oldest available layer is the honest picture of its subject —
   and it is already in the archived sources.

### The ledger lost a topic and would not say so (found 2026-10-05 22:05 UTC)

`paper24 ledger` rewrote the table with two rows numbered `1`. The driver keeps its list
of the topics it owns in `video-assets/studio/paper24_state.json`, next to the real
workspaces, and a request id that is not one of the campaign's had been written into
that file — so the first two topics were no longer "owned", were kept as if they belonged
to another campaign, and the campaign was silently renumbered. The command had no way to
report that: it wrote the table and printed `rows: 1`.

Two changes, both at the cause:

- **The iteration count moved into the workspace** (`checks.jsonl`, one line per gate run,
  written by `check` and by `finish`, which is what actually ran the gates). The count is
  the campaign's own limit ("at most two iterations per paper"), and it can no longer be
  disturbed by anything that rewrites the state file. The counts for papers 1 to 3 were
  reconstructed from the run notes above and are marked `reconstructed: true` in the file;
  paper 2 is the one that took two.
- **`ledger` refuses a table whose campaign numbers collide** and names the number and the
  lost request id, because a kept row that collides is a lost topic, not a foreign
  campaign. Verified against the damaged state: exit 2, the table unchanged.

## State of the production rows (measured 2026-10-05 22:20 UTC)

33 `completed`, 19 `queued`, 1 `failed`, 2 `paused`, 2 `cancelled` for
`user_id = '442000112756064260'`. Three rows were written by hand in this campaign, each
the guarded `UPDATE … SET status = 'researched' WHERE id = … AND status = 'queued'` the
publish needs. The three publishes set `completed`, `is_public`, `published_at`,
`published_by` and the slug in their own transaction, journal rows 115, 116 and 117.

The `running` row the 18:50 note recorded is not in that state any more, and no
non-completed row of this owner carries a `started_at` or `completed_at` from today, so
whatever left that state was not this campaign's work: this chain writes one row per
paper, and only rows that were `queued`.

### A stamp the papers named wrongly, and a fix that stopped half way (found 2026-10-06 07:50 UTC)

All four published pages carried `research_model: "MiniMax-M3"` — the pipeline's model.
Nobody researched these papers: the research, the sources and the text were produced in
the writing session on `MiniMax-M3.1-Flash-Preview`, which the bundle's `model` already
named and which `published_by: Theo` says nothing about. A stamp that names the wrong
model is worse than no stamp, so `bundle.writer_for()` was given the dossier's own
`manifest.research.researcher` and the constant stays only as the fallback for a dossier
that names nobody.

The first attempt at correcting the four pages failed on all four, at the server:

```
error: theo_publish --correct --dry-run refused: failing gates ['shape']:
  {'shape': {'passed': False, 'issues': ["result.writer differs from the bundle's writer"]}}
```

The cause is one line. `theo_publishing._result_issues` refuses a republish whose
`result.writer` differs from the envelope's `writer`, and `publish.correct()` sent the
**module constant** in the envelope while sending the bundle's own writer inside `result`.
The two were the same object for every paper the worker wrote, so the disagreement only
became possible once `writer_for()` made the bundle honest — the earlier fix moved half
the distance and the half it did not move was the half the gate reads. `bundle.json` never
had the problem: it sets the envelope's writer and `result.writer` from one value
(`bundle.py`, `build_bundle`), which is why the first publishes went through.

Changes, both at the cause:

- **`correct()` sends `bundle["writer"]` on the republish path**, with the reason next to
  it. The envelope's writer has no meaning of its own — it exists to be compared with the
  result's, and the result's is the bundle's.
- **`test_a_republish_envelope_carries_the_bundles_own_writer`** builds a workspace
  whose dossier names the session model and asserts on the bytes `correct()` sends:
  `sent["writer"] == sent["result"]["writer"] == bundle["writer"]`.

The lesson is about where the test sat, not about the gate. The first fix was verified by
a unit test on `writer_for()`'s return value, which was green while the command it was
meant to enable could not write a single page. **A change to what a bundle says has to be
asserted on the payload the CLI sends**, because that payload — not the helper — is what
the server reads. A helper test that never leaves the process is evidence about a
function, not about a paper.

Cost: four papers were bundled, checked and gated locally before the write was refused, and
the first three publishes of the campaign had already gone out with the false stamp. What
it buys the next run: the stamp is decided once, in `writer_for`, and the republish path
cannot contradict it.

### Corrected pages (2026-10-06 07:59 UTC)

Journal rows 119 to 122, one `correct` per paper, each a dry run that passed before its
apply. `research_model` and `model` now both read `MiniMax-M3.1-Flash-Preview` on all
four rows; slug, `published_at`, `published_by` and the image set are unchanged; each page
carries one dated correction-log entry that names what changed. Papers 2 and 3 also
carried the reworded sentences of the support-gate repair. IndexNow, Qdrant (7 sections)
and the API cache ran on each write; Discord is off.

## Run 4: topic 5 (the plasma coupling mechanics), 2026-10-06 09:43 UTC

Published as `birkeland-filaments-impedance-matching-and-the-vibration-principle`,
journal row 123. 5,874 prose words, 115 evidence entries, 172 claim tasks, 12 verified
images over nine sections, 68 archived sources (2.6 million characters, 47 Wikipedia
plus 17 from the Kybalion archives of run 3). Zero API calls.

Six things in this run cost a cycle each and none of them was the paper's fault. They are
recorded here because each one is a rule for the next run, not an anecdote about this one.

**`paper.md` is generated, `draft.md` is the source.** The support repair of topic 4 was
applied to the numbered paper; the next `paper number` regenerated that file from the draft
and every fix in it was gone. `number` reads `draft.md`, writes `paper.md`, and
`require_fresh_check` compares against `build_paper(ws)`. **A text repair for any paper is
written to `draft.md`, with `[S:<id>]` markers, and then numbered.** Patching the numbered
file looks like it works — the local `check` passes — and the work is discarded silently.

**A citation is a request that the source carry the sentence, not a promise that it does.**
The first support pass removed the marker from fifteen commentary sentences, which is
right, but then measured nothing: the sentences it left marked all carried their fact, in
my wording rather than the source's ("on clear nights above the poles", "the older text
states its axiom first and plainly"). Twelve of them failed an honest re-check. The rule
that holds: a marked sentence must be the source's wording, and the framing goes in an
unmarked neighbour. What finally worked was to give each factual claim its own sentence
and let the commentary sit between them.

**The claim check has to be an independent measure, not the builder's own locator.** The
evidence builder finds a quote by locating the sentence in the text. A check that reuses
that locator verifies nothing. Run 4 checks each marked sentence by token coverage and by
the presence of every number in the cited archived text, and reports the misses rather than
the hits. That measure found 21 of 172 tasks unsupported where the builder saw none.

**Three field shapes cost an import each.** An evidence entry's `verdict` is `supported` —
the probability ladder belongs to the prose, not to the record. An image answer carries
`prompt_sha256`, keyed to the prompt it answered, or the merge refuses it. Its `subject_box`
is `[x, y, w, h]` in fractions of the image, not `[x1, y1, x2, y2]`; eleven answers were
written in the second form and all eleven were refused.

**One image per opportunity, so a failed opportunity is not a thin section.** `import_images`
walks the opportunities and takes the best candidate of each, meaningful before weak. An
opportunity with nothing meaningful falls back to a weak candidate, and the picture gate
then refuses the paper for a picture nobody vouched for. The honest repair is to delete the
opportunity, not to promote the verdict: both weak candidates in this run (a reflection
nebula for a laboratory current filament, an L-network quiz diagram for a Smith chart)
failed because they did not show their subject, and their sections already had a verified
picture of their own.

**Images move the paragraphs.** Embedding a figure changes `paper.md`, so the evidence
anchors and the claim tasks are rebuilt after `images-import`, not before it. The run order
that held is: `number`, `evidence`, `claims`, `images-export`, `images-import`, then
`number`, `evidence`, `claims`, `check`. Skipping the second pass is what produced a
green-looking paper whose evidence gate turned red the moment the pictures were in.

## The campaign's own limit was not met, and the ledger could not see it (found 2026-10-07 13:20 UTC)

The goal set **at most two check iterations per paper** and made a third one a chain
failure. Measured on 2026-10-07 from the workspaces' own `checks.jsonl`, the four papers
whose history survived record **6, 6, 5 and 11** gate runs. Paper 4 (the Kybalion
provenance) needed eleven. The other six published papers — 5 through 10, including
topic 10 — have **no `checks.jsonl` at all**, so their count is not zero, it is unknown;
topic 10 went through eighteen text repair rounds before it was green, by the working
notes of that run. **The limit was exceeded on every paper that can be counted, and
probably on all ten.**

Two separate failures produced that, and both are the ledger's, not the papers'.

**The counter was written by one of the two paths that run the gates.** `_record_check`
is called by `check` and by `finish` *inside this driver*. From 2026-10-06 onward the
gates were run through the studio CLI (`paper check`, `paper number`, `paper bundle`),
which never writes `checks.jsonl`. So the campaign's limit counter stopped counting on
the day the work changed path — while the work kept going. The rule that the campaign was
supposed to enforce on itself went blind at exactly the point where the behaviour needed
watching.

**A missing record read as a count of zero.** `_iterations` returned `0` for a workspace
without a history file, and the ledger wrote that `0` into the `iterations` column. A
paper that went through eleven cycles appeared in the table as one that went through none,
and a campaign of eleven-cycle papers appeared to sit comfortably inside a limit of two.
The verification of 2026-10-07 found this because it counted the files directly instead of
reading the summary the campaign had written about itself.

Changes, both at the cause:

- **`_iterations` returns `int | None`**, and `None` renders as `nicht gemessen` in the
  ledger. No paper reaches a bundle without the gates having run at least once, so a `0` in
  that column can only ever be a lost record; the cell now says so instead of inventing a
  number that reads like a result.
- **`ledger` reports what it could not measure**: `iterations_not_measured` with the ids,
  so the gap is in the command's own output and not only in a table somebody has to
  question later.

The lesson repeats the one from run 3, and it is the same sentence: **the ledger lost a
topic and would not say so.** Run 3 fixed the *topic list* (`paper24_state.json`), and run
4 moved the *count* into the workspace so the state file could not disturb it. What neither
fix covered is that a second, uncoordinated path existed which ran the same gates without
recording anything. A counter measures the writes that go through it, and nobody had asked
whether all the writes do. The next driver that owns a limit must fail when its counter
cannot see one of the paths that can break the limit — not when the count is merely wrong.

What it costs to state plainly: the claim "the campaign held to two iterations per paper"
was never true, and it should never have been made. The ten papers are published, green,
and verified live; the limit that was supposed to keep the chain honest was not enforced,
and the artefact that would have shown it was itself reporting the missing data as success.

### The stamp went backwards on three papers after the correction of 2026-10-06

The correction of 2026-10-06 fixed `research_model` on journal rows 119–122. The verification
of 2026-10-07 found three published papers carrying the old value again:

| journal | slug | `writer.model` | `writer.research_model` |
|---|---|---|---|
| 125 | `the-watched-pot-and-the-willing-mind` | `MiniMax-M3.1-Flash-Preview` | `MiniMax-M3` |
| 127 | `the-loosened-mind-and-what-it-reports` | `MiniMax-M3.1-Flash-Preview` | `MiniMax-M3` |
| 129 | `quartz-granite-and-the-hard-ceiling-on-tuned-stone` | `MiniMax-M3.1-Flash-Preview` | `MiniMax-M3` |

No Theo worker ran and none could have: `THEO_WORKER_DISABLED=1` since 2026-09-26, and the
publish rows 125, 127 and 129 are `mcode` publishes from this campaign's own sessions. The
papers are correctly attributed — nobody researched them on `MiniMax-M3`. The
`research_model` field is the one value in the pair that has no writer of its own here: the
research and the text were both produced by the session, and `bundle.writer_for()` falls back
to the dossier's researcher, which these seeded dossiers do not carry, so the module constant
(`MiniMax-M3`) is what lands. `model` is right because the bundle sets it from the session;
`research_model` is wrong for the same reason the first four were.

**The correction of 2026-10-06 was applied by hand, to the four papers that existed then.**
The fix in `bundle.writer_for()` was supposed to make it impossible, and it does — for a
paper bundled from a dossier that names its researcher. Those three were bundled from
research files that carry no `researcher` field at all. Measured on disk, six of the ten
campaign research files name the session model and four do not:

| research dir | topic | `researcher` |
|---|---|---|
| `yd`, `rockart`, `kybalion`, `plasma`, `nocomm`, `quantobs` | 1–6 | present, names `MiniMax-M3.1-Flash-Preview` |
| `ego`, `zeno`, `will` | 7, 8, 9 | absent |
| `quartz` | 10 | absent |

So `writer_for()` took its documented fallback — the module constant `MiniMax-M3` — on
exactly the papers whose research file was incomplete. The fallback is correct behaviour for
a dossier that genuinely names nobody, and it is the wrong behaviour for a *seed* dossier,
which is by construction a session's own work and therefore always has a researcher. **The
gap is in the seed, not in the reader**: `paper24_seed.py` passes
`research.researcher` through at line 246 and honours an empty string rather than refusing
it, so a research file that forgot the field produced a dossier that looks like a pipeline
run.

The fix belongs in the seed: a seeded workspace whose research file names no researcher
should be refused, the same way the seed already refuses a source without text or a claim
citing an unknown source id. Everything the seed writes is supposed to describe a run that
happened in this session, and "nobody did this research" is not one of the states it can
produce. `writer_for()`'s constant stays as the fallback for a real dossier from a real
Theo run.

**The lesson: a fix that was verified on four paths and left five untouched is not a fix, it
is a correction.** The stamped field has to be asserted on the bytes of the path that
produced the bundle. The 2026-10-06 lesson already demanded exactly this and it was not done
for the seed path — the test asserted `writer_for()`'s return value, which the seed path
never exercised.

### The correction needed two rounds, and the first three writes changed nothing

With the owner's release (2026-10-07 13:21 UTC) three papers were corrected with
`paper correct --republish`. Journal rows 130, 131 and 132 committed, every gate passed,
every side effect ran — **and `research_model` stayed `MiniMax-M3` on all three.** Only the
read-back said so; the outcome said nothing.

The cause is one line in `_fresh_bundle`:

```python
raw = ws.require(ws.bundle, "run `paper bundle`")   # liest die Datei von der Platte
```

The name says *fresh* and the function builds nothing: it reads the last `bundle.json` from
disk and only checks that its report still matches the draft. So the research record written
into the dossier minutes earlier changed nothing, because the bundle carrying the stamp was
built before it. **The write was correct, journalled and completely without effect** — the
hardest kind of failure to notice, because every line of its own output said success.

The lesson is not "run `paper bundle` first", which is the symptom. It is that a command
named for a property it does not have will be read as if it had it, and a journalled write
whose payload was stale looks exactly like an effective one in every log it prints. Two
consequences, the first of which would have saved the three writes:

1. **A republish must refuse a bundle older than the record it draws from.** The workspace
   knows when `dossier.json.gz` was written; a `bundle.json` older than that cannot describe
   that dossier, whatever its report matches.
2. **The outcome of a stamp correction must name the value it wrote.** `correct()` returned
   a slug and a journal id and said nothing about `research_model`, so proving that a stamp
   changed needed a separate query afterwards.

Journal rows 133, 134 and 135 are the three corrections that took, after `paper bundle` was
re-run for each workspace. Measured after them: **0 of the 10 published papers carry a wrong
stamp**, read from the database and then from the public API, where `ai_system` now reads
`theo-research (MiniMax-M3.1-Flash-Preview) + MiniMax-M3.1-Flash-Preview (mcode)` on all
three pages.

`ai_system` is the second half of why this was worth doing. The public attribution line is
built from the pair, so a paper researched and written entirely in one session announced a
two-model provenance in which one of the models never touched it.

## Verification of the campaign close (2026-10-07 13:20 UTC)

Read-only, after topic 10 went out and the owner stopped the campaign:

- **10 papers published**, journal rows 115–129, one `publish` per paper, each with its own
  `bundle_sha256`. Topic 10 is row 129.
- **`research_requests`**: all ten `status = 'completed'`, `is_public = true`, slug set.
- **Live page of topic 10** answers HTTP 200 with the full text, all closing sections and
  **no `verified:no` marker**; 10 of 10 image URLs answer HTTP 200 and were confirmed as
  JPEG by their first bytes.
- **Twelve topics remain `queued`** and were not touched: `35090cb9`, `e3c4950b`, `b9713d8f`,
  `925f3887`, `66f439fb`, `a86db42a`, `4b08117b`, `75c3731d`, `5b018384`, `536f3f41`,
  `39eb9e0f`, `238147d2`. The two `paused` rows (`afe7c26a`, `20091a97`) were not touched.
- **The owner's stop instruction is not in this repository.** It came through the session on
  2026-10-07 ("nach diesem paper aufhören bitte, nach der veröffentlichung") and no artefact
  of this campaign records it, because nothing in the driver writes an owner's decision. The
  session log is the only place it exists. Stating it here is a note written after the fact,
  not evidence that was there at the time — which is exactly the gap that made the claim
  unfalsifiable from the repo.
- **Eleven chain commits sit on `feat/2026-10-04-paper-image-floor` and none is on
  `origin/main`.** The fixes recorded above are therefore local only until that branch is
  pushed.