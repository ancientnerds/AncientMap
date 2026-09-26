# Lane WC: the sentence check of the March descriptions that stay

Owner decision **O5 of 2026-09-26** (`output/remediation/FINISH_PLAN_2026-09-26.md`): "Satzweise
prüfen und kürzen" - every curated description that is still the 2026-03 AI text after the Phase-4
runs is checked sentence by sentence by Opus agents against sources on the web. A supported sentence
stays (still marked as AI text), a contradicted or unsupported one goes, one unsupported clause may
be cut out of an otherwise supported sentence, and a description with nothing left is cleared.

The code:

| file | what |
| --- | --- |
| `scripts/remediation/phase4/wc4.py` | the deterministic core, pure: the sentences, the trim, the pronoun rule, the composed text and citations, the check record, the raw_data, the invariants, the journal-evidence re-check |
| `scripts/remediation/wc/prompts.py` | the frozen texts: the check question, its re-ask block, the judge's question, both briefs (byte-pinned in `tests/remediation/test_wc.py`) |
| `scripts/remediation/wc/answers.py` | the strict answer parsers, the fetcher (`requests`, User-Agent `AncientMapRemediation/1.0 (research)`), the quote check with the mirror and title rules |
| `scripts/remediation/wc/cli.py` | the commands below |
| `scripts/remediation/phase4/write4.py` group **WC** | the journalled write (`plan_wc`, `load_wc_plan`, WC's rules in `validate_rows`, guard 3's clear tests, invariants 5-6) |
| `output/remediation/tools/write_gate4.py --group WC --wc-plan` | the gate: dry, rehearse, apply in steps of at most 100 sites, accept |
| `output/remediation/tools/verify_writes4.py --lane p4wc` | the step's acceptance, from the database and the journal alone |
| `scripts/remediation/phase4/revert4.py --stamp-like 'phase4wc:...'` | the way back |

Tests: `tests/remediation/test_wc.py`, `tests/remediation/test_phase4_wc_write.py`,
`tests/api/test_wc_disclosure.py`, the SSR case in `ancient-nerds-map/src/seo/__tests__/render.test.tsx`;
mutation cases `WC_MUTATIONS` in `scripts/remediation/phase3/mutation_sweep.py` (run with the label
substring `"wc "`).

## 1. The population (measured)

Every curated site (`source_id = 'ancient_nerds'`) that is not retired, carries a description, and
whose description is neither a Phase-4 text (a full W/S/T/R provenance) nor one lane WC checked
before. Each is asked under its marking (`wc4.old_marking`):

- `L` - lane L's provenance: a March text, marked;
- `march-unmarked` - no marking, but lane L's own rule (`legacy4.legacy_provenance`: the text differs
  from the pre-March snapshot `d4526691`) says the March chain wrote it - a site whose P4 write a
  revert took back gets its pre-lane-L `raw_data` back. The checked text then **gains** lane L's
  marking, so a published March text never goes out without the AI footnote;
- `unclaimed` - HUMAN_ONLY D7: the text is the pre-March one, or the site is not in the snapshot.
  Checked alike; it claims no AI origin before or after. That these are in the lane is the owner's
  O9 decision on D7 (`output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`, D7: "Satz für Satz
  prüfen und kürzen. Die Provenienz lautet 'Herkunft unbelegt, satzweise geprüft', eine
  März-KI-Herkunft wird nicht behauptet. Ausführung: WC"): the check record says "checked sentence
  by sentence", and no provenance is written.

Listed and never asked, each under its reason in `POPULATION.json`: `retired`, `no-description`,
`phase4-text`, `checked-before`, `provenance-unreadable`, `provenance-hash-differs` (D4 already
fails), `not-splittable`, `excluded`, `earlier-run`.

**Measured 2026-09-26 01:16 UTC**, read-only, with the lane's own read and classification (`cli.py
read` - the one SELECT `cli.WC_SQL` through `write_stage.run_sql`, 5,004 rows, sha256
`ad390ebe...f47b5` - then `cli.population` offline), **before** WA's mass run:

| | sites |
| --- | --- |
| asked | **3,937** (L 3,923; unclaimed 14: 8 same-as-snapshot, 6 not-in-snapshot; march-unmarked 0) |
| listed `phase4-text` | 989 |
| listed `retired` | 78 |
| sentences asked | 15,133 (median 4 per site, at most 8; 1,671 texts carry markers) |

**Re-measured 2026-09-26 09:24 UTC** the same way (fix round): the read's 5,004 rows hash to the
same `ad390ebe...f47b5`, so nothing curated moved since 01:16 and the population is unchanged -
3,937 asked (L 3,923; unclaimed 14: 8 same-as-snapshot, 6 not-in-snapshot, 12 of them with a NULL
`raw_data`), 15,133 sentences, 989 `phase4-text`, 78 `retired`. WA's mass run has not written yet.

WA (Phase 4 scope v3) rewrites part of these first; the lane plans from a **fresh read** after WA's
last accepted step, so every site WA wrote leaves by itself (`phase4-text`).

Dry exercise over all 3,937 real texts (no model, no network, 2026-09-26): with every sentence kept,
every one dropped, and every other one kept, each text composes, its check record and raw_data hold
every invariant (`wc4.wc_problems`), and the composed text re-splits into exactly its kept sentences.

## 2. The contract

**The sentences** (`wc4.checked_sentences`). The stored text without its `[N]` markers (the
frontend's `stripCitations` shape) is split by Phase 4's splitter (`phase4/sentences.split_source` ->
`pipeline.lyra.text_sentences.split_sentences`), numbered from 1. Where the shared splitter ends a
sentence after an abbreviation it does not know - measured: "Rev." (2), "Col." (2), "Lt." (1),
"cal." (2), "(no." (1), in 7 sites - the piece is joined to the next (`JOIN_AFTER`). The shared
splitter is not changed: it is Phase 4's parity-tested split and Lyra's.

**One question per site** (`prompts.CHECK_QUESTION`): the site's stored values to identify it (not
evidence), the numbered sentences, and for each sentence exactly one of

- `KEEP` with 1-4 verbatim quotes that together support every claim;
- `KEEP_TRIMMED` with one exact piece to remove and 1-4 quotes that support everything that stays;
- `DROP` `contradicted` (with the contradicting quote) or `unsupported` (no quote).

Sources: reputable and independent (Wikipedia in any language, UNESCO, registers, museums,
universities, excavation reports, scholarly works). Refused by code before anything is fetched
(`phase4/licences.deny_family`): ancientnerds.com, the AI aggregators, the Wikipedia mirrors, the
blocked domains; a URL with `utm_` parameters.

**The quote check** (`answers.quote_outcomes`), on pages the import fetches itself (section 3): the
quote verbatim on the page (`opus_audit/quotes.py`, whitespace-normalised, the Opus re-verification's
check unchanged); **not** on a non-Wikipedia page that shares a run of 25 words with the checked
description (a copy of our own text, the Phase-4 mirror rule); and the quote's **title** must stand
in the page's text (its heading - the title is published in the citation list, so no invented or
tab-title form reaches it). A kept sentence counts only when every quote it gives passes; a DROP
counts as given. A sentence that does not count - or every asked sentence of an answer out of
shape - is **re-asked once** (round 2, with what failed); after that it is dropped as `unverified`.

**The trim** (`wc4.trim`). The mass run has no judge, so code is the guard against a trim that
publishes new text under a quote of the old sentence. The piece:

- occurs exactly once and is not the whole sentence;
- begins and ends between words (`cuts_token`: letters and digits joined by a hyphen, an apostrophe
  or a number's separator are one token - `3,500`, `2.5`, `Hal-Saflieni`): never `5` out of `3500`,
  never ` c. 3000 BC` out of `c. 3000 BCE`;
- is no bare modifier or hedge frame (`bare_modifier`: nothing left once the V4 list's words, the
  reporting words and the frame words are out - `probably `, ` not`, `only `, `It is believed that `,
  `, it is said,`, `It is uncertain whether `);
- takes no qualifier off what stays (`qualifier_problem`): no word that puts the sentence under a
  telling or into doubt, anywhere (according to, legend, tradition, myth, folklore, V4's refutation
  words - disputed, uncertain, unknown, attributed, ...); a reporting word (believed, thought, said,
  claimed, reportedly, considered, ...) only as the inner clause of its own figure - neither opening
  nor closing the sentence, followed in the piece by `to <claim>` or an adverb's claim and a number
  or date (`, believed to date to about 10,000 BC,`); a negation only with the rest of its clause
  (`, not a tomb,`), and never a piece inside the clause of a negation that stays (" by Evans" out of
  "never excavated by Evans");
- takes no end of a sentence stored without its final mark (4 of 15,133).

The capital is restored when the piece opened the sentence, and the rest has no problem of
`sentence_problems` (length >= 25, opens with a capital or digit, ends with . ! or ? - the two halves
of `is_complete_sentence` asked apart, `text_sentences.opens_like_a_sentence` /
`ends_like_a_sentence` -, not garbled, no double space, no space before punctuation, no dangling
punctuation, balanced parentheses) that the sentence did not already have: a stored `Židovar ...`
that lacks an ASCII capital must still keep its final mark. A clause may go with its own hedge
(` (c. 3000 BC)`, `, dated to approximately 10,000 BC,`): 2,476 of the 15,133 sentences (16.4 %) carry
a hedged number, the March texts' commonest invention, and Phase 4's stricter rule (no span with any
such word) could only drop those sentences whole. The qualifier rules narrow the trims of few
sentences (measured on the same read: a negation in 238, a refutation word in 198, a sentence frame
in 311, a reporting word in 624); a trim they refuse is a DROP. What code cannot read - a trim that
keeps a grammatical sentence but changes its meaning otherwise - stays the agent's (rule 5 of the
question) and is measured by the pilot's judge (`coherent`).

**The pronoun rule** (`wc4.follow_drops`): a kept sentence that leans on the sentence before it
(`sentences.leans_on_predecessor`, Phase 4's V6 reading) goes when that one goes (`leans-on-dropped`).

**The text** (`wc4.compose`, `wc4.with_markers`): the kept sentences in order, joined by one space,
each with one `' [n]'` per distinct page of its verified quotes, ascending, numbered by first use
across the text: in front of the final `. ! ?` (Phase 4's edit 5); after a closing quotation mark or
bracket that follows it (`of the City." [1]`); and for a sentence without final punctuation (4 of
15,133, all a text's last sentence) the markers and a full stop - the one character code ever adds.
`description_citations` is rebuilt from exactly those pages: `{n, url, title, domain}`.

**The raw_data** (`wc4.written_raw_data`): the old object without `description_citations`,
`_description_provenance`, `_description_check`; for a kept text the new citations, the check record
and - for a March text (`L`, `march-unmarked`) - lane L's provenance hashing the new text. Every
other key stays as it was. Nothing kept: the description is NULL, none of the three keys remains,
and `raw_data` is NULL when nothing else is left. A site whose `raw_data` was NULL already (12 of the
14 unclaimed texts on 2026-09-26) is cleared by its description row alone: NULL over NULL is no
change, and the plan's rules refused the whole batch for such a row before the fix round.

**The check record** `raw_data._description_check` (`wc4.DescriptionCheck`, v1): `run`, `checker`
(`model4.AI_SYSTEM`, the Opus handoff's), `checked_sha256` (the stored March text that was asked),
`kept` of `of`, `trimmed`, per sentence `{n, verdict, reason, cites, quote_sha256}`, and
`desc_sha256` of the served text. It is public (`/api/sites/{id}` serves `raw_data` whole), so it
carries each verified quote's sha256 and never its words; the words, URLs, titles, every agent
answer and what the check said of each quote are in the journal evidence of both rows
(`remediation_change_log.evidence`), from which `verify_writes4 --lane p4wc` re-composes the text.

**The invariants** (`wc4.wc_problems`, asked by the plan, the in-database transaction, the read-back
and the acceptance): a kept text carries its check record whose `desc_sha256` is the text's; a
provenance beside it is lane L's and hashes the text (D4); the citations are exactly the numbers the
markers use, `1..N` by first use, each `{n, url, title, domain}` with the URL's host (D1); the check
record's kept sentences cite those numbers. A cleared site carries none of the three keys.

**The AI disclosure is required, not only checked where present** (EU AI Act; the review of
2026-09-26). The journal evidence records the checked text's marking (`wc4.marking_record`: `L`,
`march-unmarked` or `unclaimed`, and the snapshot hash lane L's claim rests on).
`wc4.disclosure_problems` requires lane L's provenance hashing a kept March text, and none on an
unclaimed or pre-March text or a clear; `build`, the writer's plan (`_validate_wc_sites`, which
re-derives the marking from the row's own old value, `old_marking_problems`) and the acceptance
(`evidence_problems`) all ask it. A regression that dropped the provenance would otherwise pass every
invariant above.

**Rendering, no design change.** Every reader derives the disclosure from
`api/services/description_provenance.description_disclosure` (`/api/sites/{id}`, the SSR payload of
`/sites/{country}/{slug}`, the public v1 API): the checked March text keeps `ai: generated`, lane
`L`, the existing AI footnote, no licence and no attribution line; an unclaimed text still claims
nothing; a cleared site is a page without a description, notice or `meta name="description"`
(`tests/api/test_wc_disclosure.py`, `render.test.tsx`).

## 3. Where things live, and who may write them

- Run directory: `output/remediation/wc_runner/runs/<run>/` - `ROWS.jsonl`, `READ.json`,
  `POPULATION.json`, `SITES.jsonl`, `ROUNDS.jsonl`, `round-<n>/ANSWERS.jsonl` and `REASK.json`,
  **`pages/`** (the import's own page store), `FINAL.jsonl`, `SUMMARY.json`, `WC4.jsonl` (the gate
  plan), `judge/` (the pilot's measurement, with its own `pages/`).
- Handoff: `output/remediation/handoff/wc-<run>-r<round>/<batch>/` (`MANIFEST.jsonl`, the prompts,
  the answers), the agent's page store `<batch>/pages/` (filled by `check-answer`), and its scratch
  `output/remediation/handoff/wc-<run>-r<round>-scratch/<batch>/`. Batches are independent: one agent
  per batch, its own scratch and page store.
- **The import never reads an agent's page store.** It fetches every quoted URL once per run into
  `<run>/pages/`, as the acceptance does (`<run>/judging/pages/`): what counts rests only on pages
  code fetched itself. A page that failed in round 1 stays failed in the re-ask.
- The apply root is the lane's: `output/remediation/logs/_write_apply_p4wc/`; step logs in
  `output/remediation/logs/p4wc/`.

## 4. The runbook

From the main checkout (after `wip/wc` is merged), main venv. `R`, `P` and the handoffs are the
names of this run; numbering continues past every earlier WC plan (`--first-batch`, section 5).

    PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe
    M=output/remediation; RUNS=$M/wc_runner/runs; H=$M/handoff; L=$M/logs/p4wc
    mkdir -p "$RUNS" "$L"      # both are gitignored: a fresh checkout has neither
    C="$PY scripts/remediation/wc/cli.py"; OH="$PY scripts/remediation/opus_handoff.py"
    G="$PY $M/tools/write_gate4.py --group WC"
    # the acceptance names lane WB's provenance stamp as a later lane (section 5): WB writes
    # raw_data._card_provenance into the sites WC made final, and without it that is CHANGED LATER
    V="$PY $M/tools/verify_writes4.py --lane p4wc --allow-stamp wb-teaser-prov-%"

**0. Preconditions.** WA's last P4 step is accepted (the read must see WA's texts). The gates of
section 7 are green on the merged tree. `$M/logs/_write_apply_p4wc/` holds no batch of a plan you
do not name. Any other later writer of these sites' `raw_data` than lane WB (a hand edit, a lane not
named in `V`) makes the next acceptance report CHANGED LATER: read it, never widen `--allow-stamp`
to pass it.

**1. The pilot (20 sites), then its independent measurement.**

    P=pilot-2026-09-DD
    $C read   --run-dir $RUNS/$P                                   # one read-only SELECT
    $C export --run-dir $RUNS/$P --handoff $H/wc-$P-r1 --pilot 20 --seed <S>
    # per batch wc-0001..wc-0004, one Opus agent each (14-16 in parallel), whose whole instruction is
    $C brief  --run-dir $RUNS/$P --handoff $H/wc-$P-r1 --batch-id wc-000N
    $OH validate --dir $H/wc-$P-r1                                 # must be clean
    $C import --run-dir $RUNS/$P --handoff $H/wc-$P-r1              # fetches into $RUNS/$P/pages
    # only if the import reports to_reask > 0 (once):
    $C export-reask --run-dir $RUNS/$P --handoff $H/wc-$P-r2
    #   ... the round-2 agents (brief with --handoff $H/wc-$P-r2), validate, import ...
    $C build  --run-dir $RUNS/$P --first-batch 4001                 # FINAL, SUMMARY, WC4.jsonl
    $C judge-export --run-dir $RUNS/$P --handoff $H/wc-$P-judge
    # per judge batch, one Opus agent that did not check (the brief names it opus-wc-judge-<batch>):
    $C judge-brief  --run-dir $RUNS/$P --handoff $H/wc-$P-judge --batch-id judge-000N
    $OH validate --dir $H/wc-$P-judge
    $C judge-import --run-dir $RUNS/$P --handoff $H/wc-$P-judge     # RESULT.json, JUDGE_EXIT=

**The pilot's pass mark** (`cli.J_THRESHOLDS`, sealed with the lane): no kept sentence the judge
shows `WRONG` with a quote code found; at most 5 % of kept sentences `UNSUPPORTED` (a `WRONG` whose
quote was not found counts here); no site whose kept text is incoherent (a pronoun without its
referent, an ungrammatical trim, a trim that changed what the sentence says); every judged site
answered by an agent that checked none of its questions. `DROP_WRONG` (a dropped sentence a source
supports) is measured and reported, not gating: a wrong drop loses text, never publishes a false
one. `JUDGE_EXIT=1` stops the lane: fix the cause, re-pin, and run a new pilot (a new run, a new
seed), never a re-judge of the same answers. **The gate enforces it** (`cli.pilot_approval`): no WC
plan is planned unless the first `--wc-plan` is a pilot run's whose `judge/RESULT.json` says
`passed: true`, and every pilot run named passed; the gate prints each approving pilot with its
RESULT.json sha256. So the pilot is judged before its own dry run.

**2. Write the pilot**, in its own step:

    $G --wc-plan $RUNS/$P/WC4.jsonl                                # dry: plan + render, read-only
    $G --wc-plan $RUNS/$P/WC4.jsonl --rehearse                     # every batch, ends in ROLLBACK
    $G --wc-plan $RUNS/$P/WC4.jsonl --apply --step 100
    $V --plan $M/logs/_write_apply_p4wc/LANE_PLAN.jsonl > $L/accept-pilot.log
    $G --accept $L/accept-pilot.log

**3. The mass run, in chunks.** The import fetches every quoted page itself, one request per host
per second, so one round of ~3,000 sites would spend hours in a single import before the first
write. The mass run is therefore a series of chunk runs of a few hundred sites (`--limit`), each
read, exported, answered, imported, built and written on its own; a chunk's `--after` names every
earlier chunk whose plan is **not yet written** (a written site leaves the population by itself as
`checked-before` or, cleared, `no-description`). The pilot, written in step 2, needs no `--after`.

A site a written batch refused (`moved-since-check`: its text moved between the check and the
write) is asked again by the next chunk, read afresh. Every later gate run names every plan, the
earlier one included, and the later plan **takes the site over**: the earlier batch refuses it as
`asked-again-later` (its written rows stay what they were: none for that site), the later batch
plans it (`write4.plan_wc`). The same holds for a site `revert4 --site` took back from a written
batch and a later chunk asks again: the earlier batch's re-plan leaves it out on the reversal proof
(`sites_taken_back`). Should two batches still both plan rows for one site - two chunks read before
either was written, the `--after` left out - the gate stops before rendering anything and names the
site; rebuild the later chunk as a new run exported with `--exclude` for it (a run has one
population), and move the old chunk's rendered, never written batch directories out of the apply
root (the gate refuses batches of a plan not named).

    R=mass-01
    $C read   --run-dir $RUNS/$R
    $C export --run-dir $RUNS/$R --handoff $H/wc-$R-r1 --limit 500 [--after $RUNS/<unwritten chunk> ...]
    #   ... one Opus agent per batch (brief), 14-16 in parallel; validate; import;
    #   export-reask / agents / validate / import once if to_reask > 0 ...
    $C build  --run-dir $RUNS/$R --first-batch <the last ordinal of every earlier WC plan + 1>

Repeat with `mass-02`, `mass-03`, ... until `export` refuses with "nothing to ask".

**4. Write each chunk, one step of at most 100 sites per invocation** (5 write batches of 20), each
accepted with 0 deviations before the next; every WC plan whose batches are in the apply root is
named, in run order, the passed pilot's first (the gate refuses an apply root holding batches of a
plan not named, and plans nothing unless a passed pilot heads the list):

    PLANS="--wc-plan $RUNS/$P/WC4.jsonl --wc-plan $RUNS/mass-01/WC4.jsonl"   # ... and every later chunk
    $G $PLANS                                                                 # dry
    $G $PLANS --rehearse
    # per step, until the gate says there is no open batch left:
    $G $PLANS --apply --step 100
    $V --plan $M/logs/_write_apply_p4wc/LANE_PLAN.jsonl > $L/accept-step-NN.log
    $G --accept $L/accept-step-NN.log
    # at the end: every planned row written
    $V --plan $M/logs/_write_apply_p4wc/LANE_PLAN.jsonl --complete

**5. Afterwards** (workstream WF): the static export (`public/data/` carries the descriptions), the
Qdrant resync, IndexNow for the changed site pages; then WB writes each site's card from its final
description.

## 5. What each gate checks

| gate | checks | refuses |
| --- | --- | --- |
| `export` | a fresh population, the frozen question per site; `--pilot` a seeded draw, `--limit` a chunk | a run exported twice; `--pilot` without `--seed`; `--limit` below 1 or beside `--pilot`; an empty population ("nothing to ask"); a handoff that is not empty |
| `check-answer` (the agent's aid) | shape, fetch into the batch's store, quotes, mirror and title rules, the text the answer leaves | nothing is recorded; exit 1 while not clean |
| `opus_handoff.py validate` | every question answered once, no stale or orphan answer | the import runs only on a clean round |
| `import` | the manifest is the round's record; every prompt rebuilt byte for byte; the answer's shape; every quote on the run's own fetch | a changed question (`not this question's`); an unvalidated round |
| `export-reask` | the sentences round 1 could not count, with what failed | a second re-ask round |
| `wc4.trim` (import, `check-answer`, build) | the piece: once, between words, no bare modifier or hedge frame, no qualifier taken off what stays (a telling or doubt of the sentence, a report outside its own figure, a negation's clause), no end of an unpunctuated sentence; the rest: no new sentence problem, the opening and the end asked apart | the answer is not in shape: the sentence is re-asked once, then dropped |
| `build` | every site's decisions, pronoun rule, text, citations, record, raw_data, evidence with the marking; `wc_problems` and `evidence_problems` (the AI disclosure the marking requires) on each | a due or unimported re-ask; `--first-batch` below 4001; a site never answered |
| `judge-import` | the judge round validates; quotes on the judge's own fetch; independence | `JUDGE_EXIT=1` below the pass mark |
| gate: the pilot's verdict (`cli.pilot_approval`) | the first `--wc-plan` is a pilot run's, and every pilot named has `judge/RESULT.json` `passed: true` | the whole run: nothing is planned |
| gate dry run | reads each site's live description and raw_data (read-only); plans: a written site is the batch's while its description and WC's three keys are the outcome's (lane WB stamps others) | `written-by-p4` (a P4 text since), `asked-again-later` (a later plan asks it again and this batch did not write it), `moved-since-check` (not written by the batch and not the whole checked pair) - per site, the rest of the batch goes on |
| gate: one site, one batch (`write4.wc_sites_planned_twice`) | no site is planned with rows by two batches | the whole run, before anything is rendered |
| gate plan (`validate_rows`) | site-atomic pairs (kept, clear, raw_data alone for a byte-identical text, the description alone for the clear of a NULL raw_data), one evidence on both rows, the evidence's transition, `wc_problems`, the recorded marking re-derived from the row's old value and the AI disclosure it requires, no key outside the three changes, no full provenance | the whole batch |
| in the transaction | guards 1-4 (curated site, allow-list, real change - NULL only for WC's two clear tests, old value held), invariants 1-2 (new values, journal both ways), 5 (check record hashes the description), 6 (provenance is lane L's and hashes it; a cleared description leaves none of the WC keys) | `RAISE`: nothing is written |
| read-back and inverse proof | every row, the journal, `wc_problems` on the stored pair; `ROLLBACK.sql` rehearsed | `STOPPED.json` |
| `verify_writes4 --lane p4wc --allow-stamp wb-teaser-prov-%` | the chain (a later write by lane WB counted as superseded, any other as CHANGED LATER), `wc_problems` and T08 on every written site, and that the live description, citations, check record and AI disclosure are exactly what the journal evidence of its last WC write composes (read from either row of the write) | any deviation: the step is not accepted |
| `--accept` | the log is one run of the acceptance, lane p4wc, `RESULT: 0 deviation(s)` | the next `--apply` until accepted |

## 6. How to undo

The journal is the undo (`revert4.py` reads what to reverse from `remediation_change_log`; no
local file needed). Its conditional `WHERE` needs each field to still hold the value WC wrote: a
later write to the site's description or raw_data (WB's, WD's, a hand edit) makes it refuse, and
nothing is reversed - revert that later write first.

    R4="$PY scripts/remediation/phase4/revert4.py"
    $R4 --stamp-like 'phase4wc:p4wc-4003:%' --rehearse          # one write batch, ends in ROLLBACK
    $R4 --stamp-like 'phase4wc:p4wc-4003:%' --apply
    $R4 --stamp-like 'phase4wc:%' --site <site id> --apply       # one site of a written batch
    $R4 --stamp-like 'phase4wc:%' --apply                        # the whole lane
    $G --close-reverted                                          # a step reverted before its acceptance

A reverted batch is written again only as its next round (`--apply --round 2`, on production's
proof that round 1 is reversed). A reversal restores the checked March text, its old citations and
its lane-L provenance byte for byte, a cleared site's too (`test_revert4_takes_a_written_wc_chunk_
back_the_cleared_site_included`).

## 7. Gates of the code (2026-09-26, worktree `wip/wc`)

    ./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"
    ruff check api/ pipeline/ ; ruff format --check <touched files> ; lint-imports
    vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80
    cd ancient-nerds-map && npm run type-check && npm run test
    $PY scripts/remediation/phase3/mutation_sweep.py "wc "

Measured 2026-09-26 in the worktree (main venv): pytest **7,246 passed**, 118 skipped, 57
deselected (115 skips are gitignored data absent from a worktree - Natural Earth caches, the
snapshot, the phase-3 worklist, bcases, fonts, video assets, the design file, exports; 3 are
older and unrelated: two retired article-generator tests and the opt-in `THEO_REGEN_TEST`); ruff
check and format clean; lint-imports 2 contracts kept; vulture clean; type-check clean; vitest
1,007 tests in 105 files. Mutation sweep: the 58 WC cases **and** the 317 older cases on the files
this lane changed (`write4.py`, `write_gate4.py`, `verify_writes4.py`, `quotes.py`,
`write_stage.py`): **375/375 caught**, the tree byte-identical afterwards.

**After the review's fix round** (2026-09-26, worktree, main venv): pytest **7,316 passed**, 115
skipped, 57 deselected (112 skips are gitignored data absent from a worktree, 3 the older opt-in or
retired tests above); ruff check `api/ pipeline/` clean, ruff check and format clean on the 17 touched
Python files; lint-imports 2 contracts kept; vulture clean; the Lyra import check green (the fix
round touched `pipeline/lyra/text_sentences.py`); no frontend file changed. Mutation sweep: the 86
WC cases in one run **86/86 caught**, and the 340 older cases on every file the fix round changed
(`write4.py`, `write_gate4.py`, `sentences.py`, `verify_writes4.py`, `acceptance/judge.py`,
`text_sentences.py`, the sweep itself) **340/340 caught**, the tree byte-identical after each run.

End-to-end smoke on live data (Duggleby Howe, one site; a machinery test, never written): export,
brief, `check-answer` against the live Wikipedia page (the circa-date trim applied, the rejoined
"Rev." sentence intact, a tab-title `Duggleby Howe - Wikipedia` refused as `title not on page`),
record, validate, import (its own fetch into the run), build, and the gate's dry run against
production's live row (read-only): 2 rows planned, no refusal. An import after the question text
changed was refused (`the exported prompt is not this question's`), as designed.

## 8. Known limits and merge notes

- The fetcher follows redirects without re-checking the target host (the same as the Opus
  re-verification's `quotes.http_client`); `not_fetchable` refuses production and non-public URLs
  before the first request.
- **Independence of the pilot's judge is procedural.** `judge-import` compares the judge's
  `answered_by` with every check answer's; both are the names the briefs prescribe
  (`opus-check-r<round>-<batch>`, `opus-wc-judge-<batch>`), so the comparison catches a mislabelled
  or reused agent, not a checker that judges under the judge's name. The Opus handoff records no
  other identity: `CLAUDE_CODE_SESSION_ID` is visible in an agent's shell, but it is unverified
  whether batch agents of one workflow get distinct ids, and a shared id would mark every judge
  dependent and block every pilot. Independence therefore rests on spawning the judges as their own
  agents with a brief that forbids reading any other batch (the review of 2026-09-26, not changed).
- **A trim's meaning beyond the qualifier rules** (a cut that keeps a grammatical sentence but
  narrows or shifts it otherwise) is the agent's (rule 5) and the pilot judge's (`coherent`); code
  refuses the forms it can read (section 2).
- `mass4` digests `scripts/remediation/phase4/*.py`: this lane adds `wc4.py` and changes
  `write4.py` and `sentences.py` (the group pattern `protected_pattern(*groups)`, `PROTECTED`
  unchanged), so it is merged into a tree only when no mass4 run executes from that tree.
- Outside the lane's own files the fix round of 2026-09-26 touched `pipeline/lyra/text_sentences.py`
  (the two halves of `is_complete_sentence`, behaviour unchanged, Lyra import check green),
  `scripts/remediation/acceptance/judge.py` (its clock and writers now `run_files.py`'s) and the
  new `scripts/remediation/run_files.py`.
- WA changes `write4.py`, `write_gate4.py`, `verify_writes4.py` and appends to
  `mutation_sweep.py` too; the hunks are adjacent (the rule constants after `RULE_MARKED`, the plan
  loaders, the gate's `_run`, the end of the sweep), so the conflicts are mechanical. Re-run the
  sweep's `"wc "` cases after the merge.
- Lane WB (`wip/wb`) spells WC's check key as a literal until the merge (its CARD_DESCRIPTIONS.md,
  section 7); WB's step runbook needs nothing from WC's, but WC's acceptance names WB's provenance
  stamp (`--allow-stamp wb-teaser-prov-%`, section 4).

## 9. The independent review of 2026-09-26 and its fix round

The review (HEAD `5ff0a31`, verdict "fix") reported 3 major and 9 minor findings. Each, with what
became of it:

| # | finding | outcome |
| --- | --- | --- |
| 1 | a trim may cut inside a word or number (`5` of `3500`, ` c. 3000 BC` of `c. 3000 BCE`) | fixed: `cuts_token` (hyphen, apostrophe and separators join a token) |
| 2 | a hedge or reporting frame with filler words passes (`According to legend, `, `It is believed that `) | fixed: frame words in `bare_modifier`; `qualifier_problem` refuses a telling or doubt of the sentence anywhere and a report outside its own figure |
| 3 | lane WB's `raw_data` stamp makes a written site "moved": the re-plan stops in `sites_taken_back`, the acceptance reports CHANGED LATER | fixed: a written site is the batch's while its description and WC's three keys are the outcome's; the acceptance names `--allow-stamp wb-teaser-prov-%` (section 4) |
| 4 | a site a written plan refused and a later chunk asks again: "listed twice", the run refused | fixed: outcomes by plan batch; the later plan takes the site over (`asked-again-later`); two batches that still both plan a site stop the gate before rendering |
| 5 | completeness compared as one problem: a stored `Židovar ...` lets any fragment pass | fixed: the opening and the end asked apart (`text_sentences.opens_like_a_sentence` / `ends_like_a_sentence`); no piece takes the end of a sentence stored without its final mark |
| 6 | a cut inside a negated clause widens or inverts it | fixed for the forms code can read (a negation cut without its clause, a piece inside a negation's clause); meaning otherwise stays the agent's and the pilot judge's (section 8) |
| 7 | the AI disclosure was checked only where present | fixed: the evidence records the marking; `disclosure_problems` requires lane L's provenance on a kept March text in build, plan and acceptance |
| 8 | independence compares self-reported names; nothing ties a mass plan to a passed pilot | gating fixed (`cli.pilot_approval` in the gate); identity not changed - no verifiable per-agent identity exists in the handoff (section 8) |
| 9 | the 14 unclaimed texts go beyond O5 | no change: the owner's O9 decision on D7 assigns them to WC with no AI claim (section 1) |
| 10 | the runbook's `$L` does not exist | fixed: `mkdir -p "$RUNS" "$L"` |
| 11 | duplicated file helpers; a weak UUID check | fixed: `scripts/remediation/run_files.py` shared with `acceptance/judge.py`; `revert4.check_site` |
| 12 | the worktree held an uncommitted, unpinned half-fix | fixed: finished, pinned, committed |

Found while testing finding 4: the clear of a site whose `raw_data` is NULL planned a NULL-over-NULL
row that the plan's rules refuse, which would have stopped the whole batch (12 of the 14 unclaimed
texts); such a clear is now its description row alone, and the acceptance reads a site's evidence
from either row.
