# Card descriptions: the teaser contract (lane WB, 2026-09-26)

`card_stats.card_description` is the up-to-200-character text on a site's card: the SiteCard, the
Forgotten Worlds game, search previews and the voice-over of the site's short video. Since the owner's
decisions of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`, binding) every curated card
is a **teaser**, written by one Opus agent from the site's sourced description and checked claim by
claim by another:

- O2: "die kartentexte für das game waren eigentlich schön. sie sollten die site teasern und mystisch
  sein. diesen text wollte ich auch für die Shorts. sie müssen alle ungefähr gleich lang sein aber
  natürlich müssen sie inhaltlich stimmen!!!"
- O3: "Alle Karten neu" - all ~4,900 cards, the 761 extractive Phase-5 cards included.
- O4: 160-190 characters (the March cards' median was 172; about 11-13 s spoken).
- O10: "ja wie bisher" - the AI disclosure: `data-card-ai` on the SiteCard, the AI footnote on the
  site page, the AI note in the shorts description.

This file is the contract (sections 1-3), the measured population (4), the runbook (5), the reasons
behind the write path (6) and what the merge of the parallel lanes has to do (7). It supersedes the
extractive contract of 2026-09-23 (section 8). Code: `scripts/remediation/teaser/` (contract,
prompts, answers, the run CLI), `scripts/remediation/mechanical/teaser.py` (the write plan),
`pipeline/utils/card_provenance.py` (the provenance and its readers). Tests:
`tests/remediation/test_teaser.py`, `tests/remediation/test_mechanical_teaser.py`,
`tests/api/test_ai_act_marking.py`, `tests/api/test_sites_html_ssr.py`,
`tests/pipeline/video/test_shorts.py`, `ancient-nerds-map/src/seo/__tests__/render.test.tsx`; the
mutation sweep's `teaser:` cases (`scripts/remediation/mechanical/mutation_sweep.py "teaser:"`).

## 1. What a card is

A card is a **teaser in English**: evocative, a little mysterious, inviting the reader to the site;
**160-190 characters** (Python `len` of the final text); one or two sentences; it names or
unmistakably describes **this** site. Mystery is **tone**, never a claim.

### 1.1 The fact basis

Every factual claim of a card comes from the site's **fact basis** and from nothing else:

- the site's **published description** - the one live after lanes WA and WC, and only when a record
  proves where it came from:
  - a Phase-4 text: `raw_data._description_provenance.lane` is `W`, `S`, `T` or `R` **and** its
    `desc_sha256` is the sha256 of the live description (lanes WA and Phase 4);
  - a sentence-checked March text: `raw_data._description_check.desc_sha256` is the sha256 of the
    live description (lane WC, owner decision O5; such a text keeps lane L's provenance or none);
- the site's **name** and **country**.

Lane L alone (the unverified March text) and a text without provenance are no basis: those sites
are listed `not-final` and wait for lane WC. **A site without a published description gets no card:
its card is cleared.** (`teaser/run.py`: `basis_of`, `classify`.)

The writer and the checker see the description as **numbered sentences** (`contract.
description_sentences`): the citation markers taken out (`[1]`, `[2, 3]`, `[4-6]`, with the space
before them - the frontend's `stripCitations` shape), each line split by the project's one sentence
splitter (`pipeline.lyra.text_sentences.split_sentences`, which keeps `c. 3000 BC`, `St.` and
initials whole), numbered `S1`, `S2`, ... in text order. The numbering is a pure function of the
description, so the sentence ids the checker names are reproducible from the text the provenance
hashes.

### 1.2 What counts as a claim

Each of these is a claim and needs a sentence of the description that says it: that something is
unknown, unexplained, unsolved, disputed, secret or mysterious ("no one knows", "a riddle", "a lost
civilization"); superlatives and rankings ("oldest", "largest", "first", "only", "unique"); numbers
(in digits or in words), dates, periods and centuries; names of people, peoples, cultures and places;
materials, sizes, functions and uses. A hedge of the description stays a hedge ("possible offerings"
may not become "offerings"). A question may not imply a claim: "Who built it?" says the builders are
unknown.

### 1.3 The mechanical checks (code, before any checker sees a card)

`scripts/remediation/teaser/contract.py:problems`, on the **final** card - the writer's text after
the Phase-4 assembler's one spoken edit (`phase4.assemble.spoken`: `c.`/`ca.` before a date ->
`circa`):

| check | rule |
| --- | --- |
| length | 160-190 characters, Python `len` |
| layout | one line: no leading/trailing space, no double space, no tab or line break |
| ending | ends with `.` or `?` (a closing quote may follow) |
| sentences | one or two (`split_sentences`); at most one `?`, and the question's sentence at most 60 characters |
| characters | no bracket `()[]{}<>` (citation markers included), no `!`, `#` or `*`; no Unicode `So` (emoji, pictographs, (c), degree), `Sm` (math symbols and most arrows: `+ = \| ~ × ± →`), `No` (superscripts, fractions), `Cs`, `Co`, `Cn`, no zero-width joiner or variation selector |
| circa | no bare `c.`/`ca.` left over |
| numerals | every numeral of the card is a numeral of the fact basis (name + description without markers), read by `phase4.scope4.numerals` - the numeral reading of `scope4.ungrounded_card` (digits with comma thousands and a decimal part, compared as values: `3,701` = `3701`). `ungrounded_card` itself is not called because it reads only the first 500 characters of its input (the March generator's); the basis here is the whole description |
| name | the card contains one of the site's **name forms** (1.4) |
| shorts | every glyph is in the brand font and every caption word fits the frame (`phase4.verify4.card_fit`, `MAX_CAPTION_PX`: V10's own measurement) |

What the code cannot see - a claim the description does not make, a number in words, a superlative,
"no one knows", the tone, whether the card is about this site - is the checker's (2).

### 1.4 The site's name forms (precise)

A card names the site when it contains, as whole words after Phase 4's name fold
(`phase4.sentences.names_in` with `phase4.subject_gate.fold`: accents stripped, lower case, every
non-alphanumeric character a space - `Chichén-Itzá` is found as `Chichen Itza`, `Stonehenge's` as
`Stonehenge`), one of (`contract.name_forms`):

1. the stored name, always (`Ur` too);
2. the stored name without its bracketed parts (`Eryx (Sicily)` -> `Eryx`; `Quesera (Cheeseboard) de
   Zonzamas` -> `Quesera de Zonzamas`) - the bracket's content is no form, it is a disambiguator as
   often as an alias;
3. of that, the part before the first comma (`Gaer Hillfort, Trellech` -> `Gaer Hillfort`) and each
   part between a slash or a spaced dash (`Medicine Wheel/Medicine Mountain ...` -> `Medicine
   Wheel`; `The Black Pyramid- Pyramid of Amenemhat III` -> `Pyramid of Amenemhat III`);
4. each alternative name the catalogue stores (`unified_site_names`) **that the description itself
   uses** (found in it by the same fold) - an alias the fact basis carries;
5. each of these without a leading `The`.

A derived form (2-5) must fold to at least 3 characters. The writer's prompt lists the forms, so the
rule is never a guess.

### 1.5 Style (the writer's rules, `teaser/prompts.py`)

No citation markers, no parentheses, no emojis, no symbols (`+`, `=`, arrows), no hashtags, no
asterisks, no exclamation marks, no marketing phrases ("hidden gem", "must-see", "step back in
time"); numbers written with digits exactly as the description writes them, never computed ("5,000
years ago" from "3000 BC"), rounded or converted; the country only where it adds to the image (the
card shows the flag). The writer's prompt carries four good examples written for this lane from the
live descriptions of Skara Brae, Newgrange, Stonehenge and Sacsayhuamán (read-only SELECT,
2026-09-26 01:13 UTC), each with the sentences it rests on under the ids the full description gives
them and its claim-to-sentence map; a test pins every id and text against the full live texts
(`tests/remediation/teaser_cases.py`). No example asks a question: the first Sacsayhuamán draft
ended "How do you make stone fit like that?", which implies a mystery of technique that its own
sentence S4 answers (the workers cut the boulders to fit) - the pattern a strict checker fails.

## 2. The checker

A **different** Opus agent checks each card (`teaser/prompts.checker_prompt`): it lists every
claim - including what a question implies - with the ids of the sentences that say it (`[]` when none
does); `tone_ok` (the tone rules: evocative, not marketing, mystery only as tone, at most one short
question, hedges kept); `this_site` (not a namesake, a neighbouring town, the region, a museum or an
object kept elsewhere). **PASS only when every claim has support, `tone_ok` and `this_site` are true
and no finding remains**; else FAIL with every finding as one concrete sentence. The answer is
strict JSON (`teaser/answers.parse_checker`): a PASS with an unsupported claim, with a false flag or
with a reason is refused, and so is a FAIL without a reason.

A card that fails (mechanically or at the checker) is **rewritten** by a new writer whose prompt
carries every earlier card and why it failed, and checked by a **new** checker - up to two rewrites
(stages `write`/`check`, `rewrite1`/`check1`, `rewrite2`/`check2`). **After the second failed rewrite
the site gets no card: it is cleared.**

**Independence is a process rule, kept by whoever runs the batches**: every batch of every stage -
and of the pilot judge - gets a **new** agent, and the brief (`run.py brief`) tells an agent that
answered any other batch of lane WB to stop. The import cannot see an agent: `answered_by` is the
batch's name (`teaser-<batch_id>`, and every batch id carries its stage), so its refusal of a checker
or judge whose name wrote or checked the site before catches only a reused or mistyped name - one
agent reused under two batch names goes undetected by code.

## 3. Storage and display

### 3.1 The provenance: `unified_sites.raw_data._card_provenance`

```json
{"v": 1, "kind": "teaser", "lane": "WB", "ai": "generated",
 "ai_system": "Claude Opus (Anthropic): ..., an-sites-remediation-2026-09", "run": "<run>",
 "text_sha256": "<sha256 of the card>", "desc_sha256": "<sha256 of the description it was written from>",
 "check": {"verdict": "PASS", "stage": "check|check1|check2", "by": "teaser-check-007",
           "at": "<answered_at>", "claims": [{"claim": "...", "support": ["S2"]}]}}
```

Its own key, because `_description_provenance` is replaced whole whenever a description is rewritten
and a card outlives that; the leading underscore keeps it out of the popup's raw-data panel. Shape,
builder and readers: `pipeline/utils/card_provenance.py` (stdlib only - the Lyra image ships
`pipeline/` without `api/`). Nothing is defaulted: a malformed provenance raises on every reader.
When lane WB writes a teaser it also sets a Phase-5 extractive `_description_provenance.card` key to
`null`, so two provenances never describe one card.

- **AI-generated** while `text_sha256` hashes the live card: `/api/sites/{id}` returns
  `cardAi: "generated"` (`api/services/description_provenance.card_ai`, which reads the teaser
  provenance first) - the SiteCard's `data-card-ai`; the site page's SSR payload carries `card_ai`
  and `DescriptionDisclosure` shows the existing AI footnote once, whichever of description and card
  is AI-generated; `card_stats.card_description` is therefore a page column (`PAGE_COLUMNS`, lastmod
  and IndexNow) - counted only as lane WB writes it (`PAGE_COLUMN_STAMPS`: `wb-teaser-card-%`, the
  reversals included), because the earlier card writes (the P5 sitting, the card-stats waves)
  changed no byte of the page when they were made and would otherwise move those pages' dates once,
  on the deploy. A card changed by any other path is not the card the provenance describes and
  nothing is claimed for it.
- **Stale** when the description changed after the check (`desc_sha256` differs): the card keeps its
  AI mark, but the shorts export gives it no pin (`shorts_pin` -> S13 fails), so a short narrates
  only a card proven against the text the site shows. `mechanical/teaser.py stale` lists stale cards
  (read-only); `teaser/run.py select` takes them as candidates again.
- **Shorts**: `pipeline/video/shorts_export.py` pins a fresh teaser by its own hash and passes
  `card_ai`; `shorts_render.build_description` adds the AI note (`TEASER_NOTE`) for it. A `site.json`
  exported before lane WB lacks `card_ai` and carries the old card: re-export before rendering.

Retired sites (E4, 78) are not touched: their page answers 410 and their card is never drawn (63 of
them still carry an old card).

## 4. The population (measured 2026-09-26 01:13 UTC, read-only)

One read-only transaction (`BEGIN TRANSACTION READ ONLY` ... `ROLLBACK`) through
`ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -At"`,
counting `unified_sites` (`source_id = 'ancient_nerds'`) joined to `card_stats`, grouped by
`raw_data._description_provenance.lane`, whether its `desc_sha256` hashes the description, whether a
card exists and whether a Phase-5 card key exists. Journal high-water mark 73911. Re-measured
2026-09-26 08:26 UTC the same way (curated, not retired, with a description and a card row; per
lane and hash): every number below unchanged - 4,926; W 963, S 26, L 3,923, none 14; 4,583 cards; 0
sentence checks, 0 teaser provenances.

| what | sites |
| --- | --- |
| curated sites | 5,004 |
| not retired, each with a `card_stats` row | **4,926** (all of them; 78 retired) |
| ... with a published description | 4,926 |
| ... with a card today | 4,583 (343 without; length min 80, median 167, max 200) |
| basis today: lane W, hash ok | 963 (740 with a Phase-5 extractive card key, 127 with an older card, 96 without a card) |
| basis today: lane S, hash ok | 26 (21 Phase-5 keys) |
| **candidates today** | **989** |
| waiting for WA/WC: lane L (March text) | 3,923 |
| waiting for WC: no provenance (HUMAN_ONLY D7) | 14 |
| sentence checks (`_description_check`) / teaser provenances | 0 / 0 |

**Batches** (15 sites per writer batch, `BATCH_SIZE`; a checker batch is the passing cards of one
writer batch; 5 cards per judge batch):

| run | sites | write | check | rewrites |
| --- | --- | --- | --- | --- |
| pilot | 20 | 2 | 2 | as needed |
| the 989 candidates of today | 989 | 66 | <= 66 | ~13 per round at 20 % failing |
| every non-retired curated site (upper bound after WA/WC) | 4,926 | 329 | <= 329 | ~66 per round at 20 % failing |

At 16 agents at a time (O11) a stage of 329 batches is 21 waves. The pilot measures the failure rate
that sizes the rewrite rounds.

## 5. The runbook

Every command runs in the checkout that carries lane WB, with the repository venv; every tool prints
its own result - read that, never a wrapper's status.

```bash
cd /c/PythonProjects/AncientMap
export PYTHONIOENCODING=utf-8
PY=./.venv/Scripts/python.exe
T=scripts/remediation/teaser/run.py
OH=scripts/remediation/opus_handoff.py
MW=scripts/remediation/mechanical/teaser.py
AP=scripts/remediation/mechanical/apply.py
RUN=output/remediation/teaser/runs/wb-pilot-2026-09-27     # a run's name: its date of `select`
H=output/remediation/handoff/teaser-wb-pilot-2026-09-27     # $H-<stage>: one directory per stage
```

### 5.1 One stage (the same for every stage and every run)

1. `$PY $T export --run $RUN --stage <stage> --handoff $H-<stage>` - the stage's questions, batches of
   15 (`<stage>-001`, ...). It refuses while an earlier stage waits for its import, a second export of
   the stage, and a non-empty directory. `"questions": 0` means nobody is due: go to the next stage.
2. For each batch `B`, a **new** Opus agent - never one that answered another batch of lane WB (the
   independence rule, section 2; the code cannot check it); its whole instruction is the output of
   `$PY $T brief --run $RUN --handoff $H-<stage> --batch-id B`. At most 16 agents at a time; each
   answers its own batch into its own scratch directory (`$H-<stage>-scratch/B/`), checks every answer
   with `run.py check-answer` (a writer until it prints `"ok": true`; nothing is recorded by it) and
   records it with `opus_handoff.py answer --answered-by teaser-B` (write-once). An agent that stopped
   (the API limit) is replaced by a new one with the same brief; recorded answers stay.
3. `$PY $OH validate --dir $H-<stage>` - every question answered, for its exact prompt, by Opus, in
   shape. Gate: no missing, stale, malformed or orphan answer.
4. `$PY $T import --run $RUN --stage <stage>` - rebuilds every prompt from the run's pinned files and
   refuses an answer to any other, a checker answer recorded under a name that wrote or checked the
   site before (a reused name, section 2) and a malformed answer (delete that answer file, re-brief
   the batch). Writes `STAGE-<stage>.jsonl`; prints the mechanical failures (writer stages) or the
   verdicts (checker stages).
5. `$PY $T status --run $RUN` - who is due where, accepted, cleared.

The stages in order: `write`, `check`, `rewrite1`, `check1`, `rewrite2`, `check2`. Then
`$PY $T outcomes --run $RUN` (refused while a site is still due) writes `OUTCOMES.jsonl` (each
accepted card with its provenance; each cleared site with its reason: `failed-after-two-rewrites`,
or `no-description` for a site without a description that still has a card) and `OUTCOMES.md`.

### 5.2 The pilots: 20 sites each and an independent web judge

There are two pilots, one per kind of fact basis, because the two kinds of text differ: the
**first** draws from the Phase-4 texts (lanes W/S/T/R: assembled from or restated after a pinned
Wikipedia source - today all 989 candidates are W or S), the **second** from lane WC's
sentence-checked March texts (basis `WC`: shorter, trimmed, the bulk of the final population, about
3,900 sites), before the first mass run over WC texts. Each is the same procedure with its own run:

1. `$PY $T select --run $RUN --pilot 20 --seed <N> --basis W --basis S --basis T --basis R` (the
   first) or `... --basis WC` (the second, `RUN=output/remediation/teaser/runs/wb-pilot-wc-<date>`)
   - one read-only production snapshot (`EXPORT.jsonl`), 20 candidates of those bases drawn with the
   seed (every other candidate is listed `other-basis` or `not-drawn`); `RUN.json` pins `SITES.jsonl`
   and `LISTED.jsonl` by sha256, records `basis_asked` and prints the counts per listing reason and
   per basis. Once per run.
2. The six stages and `outcomes` (5.1).
3. `$PY $T judge-export --run $RUN --handoff $H-judge` - every accepted card, 5 per batch, to a new
   Opus agent with web access (the brief from `$PY $T brief --run $RUN --handoff $H-judge --batch-id
   judge-NNN`) that has worked on no card of the run. The judge sees only the site's name, country and
   card (`prompts.judge_prompt`) and decides every claim SUPPORTED / CONTRADICTED / UNVERIFIABLE
   against pages it opens and quotes; it is told which hosts refuse automated readers (Historic
   England and the Heritage Gateway answer 403, UNESCO often refuses, PDFs may be unreadable) and
   never to cite ancientnerds.com.
4. `$PY $OH validate --dir $H-judge`, then `$PY $T judge-import --run $RUN` - refuses a judge answer
   recorded under a name that wrote or checked the card (section 2); fetches every cited page once
   (User-Agent `AncientMapRemediation/1.0 (research)`, no personal data) into `$RUN/pages/` and
   checks every quote by machine (`scripts/remediation/opus_audit/quotes.py`); writes `JUDGE.jsonl`
   and `JUDGE.md`. **Gate (exit 0): no claim CONTRADICTED - with a proving quote or without one -
   and at most 10 % of all claims without a proving quote** (UNVERIFIABLE, or a quote the machine did
   not find on the page). A contradiction whose page refused the machine (403, a PDF, a JS page) or
   whose quote was mis-copied is still a contradiction: it is counted apart
   (`contradicted_unproven`, `disputed_cards`), shown in the summary line and in `JUDGE.md`'s header,
   and fails the pilot like a proven one.
5. Read `JUDGE.md`: first its section **"Every contradiction"** - each line, proven or not, with the
   page it cites: is the card wrong, or is its description (the card says what a sentence says)? -
   then `OUTCOMES.md` for the tone (evocative, a little mysterious, about the same length). A card
   that departs from its description is a lane-WB failure (prompts or contract); a card faithful to a
   sentence the web contradicts is a description defect - record it in AUDIT_LOG for the lane that
   owns the text (WA/WC). Either way the pilot FAILED: change the prompts or the contract (code,
   tests, commit) where the card was at fault, and draw a **new** pilot run with a new seed; a failed
   pilot's outcomes are never written. A PASS: write the pilot's outcomes (5.4) - they are the first
   step of their kind - and start the mass run over that basis.

### 5.3 The mass run

Preconditions: the sites' descriptions are final - lane WA's P4 writes and lane WC's writes are
accepted for the sites to be asked - and the pilot of their basis passed (5.2). Sites whose text is
not final yet are listed `not-final` and are asked by a later run.

1. `$PY $T select --run $RUN2 --exclude-run $RUN --basis W --basis S --basis T --basis R` (every
   earlier run of lane WB with its own `--exclude-run`): a site asked before is asked again only if
   its description changed since. The `--basis` list keeps the sentence-checked texts out until their
   own pilot passed; after that, a run over them names `--basis WC` (or no `--basis` at all).
2. The six stages and `outcomes` (5.1), 16 agents at a time.
3. The write (5.4), step by step.
4. After WC finishes, the same again for the sites WC made final (`--exclude-run` for every earlier
   run), until `select` lists no `not-final` site.

### 5.4 The write: steps of at most 100 sites, each accepted with 0 deviations

Each step is **two journalled lanes** (6): `teaser-prov-sNNN` (`unified_sites.raw_data`: the teaser
provenance, the Phase-5 card key nulled) and `teaser-card-sNNN` (`card_stats.card_description`: the
card, or `NULL`). Provenance first, card second; undo the other way round.

Once per sitting, before the first apply:

```bash
ssh ancientnerds "cd /var/www/ancientnerds/scripts/remediation && DO_DRILL=1 ./00_backup_and_drill.sh"
#   judged by its VERDICT line
ssh ancientnerds "docker inspect -f '{{.Name}} {{.State.StartedAt}}' ancient_nerds_api ancient_nerds_api2"
#   noted: an API restart inside the sitting re-imports the old card file (5.5)
```

and no other push to `main` until 5.5 is done (a deploy restarts the API, whose boot imports the card
file).

Per step `N` (`NNN` = the step number with three digits; step numbers run across runs):

```bash
$PY $MW plan --run $RUN --step N
#   read-only; --run takes the run's directory ($RUN, as run.py does) or its bare name. The next
#   <=100 outcomes of the run: output/remediation/mechanical_teaser/sNNN/ (export.jsonl, PLAN.md,
#   SKIPPED.jsonl, prov/ and card/ with PLAN.jsonl, and ROLLBACK.sql for a lane with cells).
#   Refused while step N-1 is not closed (accept, or close-reverted after an undo). A site that
#   changed since its check is listed, not written: stale-description, retired, no-card-row,
#   journal-chain-broken, journal-disagrees, raw-data-not-an-object, raw-data-not-reprinted,
#   nothing-to-change (PLAN.md explains each).
for L in prov card; do          # SKIP a lane whose plan has 0 cells (PLAN.md): nothing to write
  $PY $AP --lane teaser-$L-sNNN --emit             # APPLY.sql, pinned to the plan
  $PY $AP --lane teaser-$L-sNNN --rehearse         # the statement with COMMIT -> ROLLBACK
  $PY $AP --lane teaser-$L-sNNN --probe-guards     # every guard refuses its corrupted copy (exit 0)
  $PY $AP --lane teaser-$L-sNNN --apply            # exit 0 = committed and read back
  $PY $AP --lane teaser-$L-sNNN --verify           # read-only read-back
done
for L in card prov; do          # the undo runs (then ROLLBACK), card first; SKIP a 0-cell lane:
  $PY $AP --lane teaser-$L-sNNN --rehearse-rollback  # it has no ROLLBACK.sql
done
$PY $MW accept --step N          # read-only; ACCEPT_EXIT=0 and "RESULT: 0 deviation(s)" only
```

What the gates check:

- the plan (`mechanical/teaser.py classify`): the live description is the one the card was checked
  against (its sha256 is the outcome's `desc_sha256`); the site is curated, not retired, has a
  `card_stats` row; `raw_data` is a JSON object spelled the way the planner prints it; each cell's
  journal is continuous and ends at the live value;
- `apply.py` (every mechanical lane's guards, `docs/procedures/PHASE4_CONTRACTS.md` has the general
  write rules): only curated rows; the plan's old value is the live value (`apply_remediation_change`,
  matched exactly one row); guard 2 - no cell is a no-change, the card fits `varchar(200)`, and only
  the card column may be written `NULL` (`Column.clears`, lane WB's one extension; NULL to NULL is
  never a change); **guard 5 - the premise**: the provenance lane writes only while the description's
  sha256 is the planned one; the card lane only while the teaser provenance's `text_sha256` and
  `desc_sha256` and the live description's sha256 are the planned ones (`text|desc|desc`, or
  `||desc` for a clear) - so a card is written only onto the provenance step 1 wrote and while the
  description is the one checked; guard 6 - the journal chain;
- `--verify` prints, before and after: the teaser provenances, those not hashing their live card (the
  step's site count after the provenance lane, 0 after the card lane), stale teaser cards, Phase-5 card
  keys not hashing the live card, descriptions their provenance does not hash, curated cards;
- `accept` re-reads the step's sites and the journal rows of its two lanes (writes and reversals):
  every planned cell holds its value and has exactly its journal row, no rollback row, no Phase-5
  card key left, an accepted site's teaser provenance hashes the live card and is not stale, a
  cleared site has neither card nor teaser provenance. Only then it records
  `ACCEPTED/step-NNN.json` (once; a later `accept` only re-reads, and a step closed as undone is
  never accepted), which - or a `REVERTED/step-NNN.json` (5.6) - the next `plan` requires.

Between the two applies of a step the old card is live and marked by nothing (its Phase-5 key is
nulled, and the teaser provenance hashes the new card): a window of minutes in which a site claims
less, never more.

### 5.5 The card file: rendered from the database, pushed at once

`public/data/card_descriptions.json` is the authoritative copy of the column
(`docs/procedures/FIELD_CONTRACT.md` section 2.3): every API boot upserts each key it carries into
`card_stats` (`api/services/card_descriptions.py`, logging every non-empty value it replaces as
`[STARTUP] Card description overwritten`); `public/data` is mounted into the API containers from the
VPS checkout, which the deploy pulls. **So after each write sitting, before anything else is pushed:**

```bash
$PY $MW card-file --steps A-B       # the sitting's steps; read-only; WRITE_EXIT=0
$PY scripts/remediation/phase4/card_json.py --check     # ACCEPT_EXIT=0: file == production
git add public/data/card_descriptions.json
MT=output/remediation/mechanical_teaser
git add -f $MT/STEPS.jsonl $MT/ACCEPTED $MT/sNNN/PLAN.md $MT/sNNN/SKIPPED.jsonl \
  $MT/sNNN/prov $MT/sNNN/card          # every step of the sitting; $MT/REVERTED too once it exists
git commit -m "Lane WB steps A-B: the card file regenerated from production"
git push origin main                # immediately; the deploy pulls the file
```

`card-file` renders with `card_json`'s own renderer (`file_from_cards`, `canonical`: existing key
order, new keys in UUID order, cleared keys removed) from a read-only production SELECT, and refuses
unless every step named is closed, every key it changes is a card cell of those steps, and
production holds each such cell as the steps left it (an accepted step's planned card; an undone
step's card from before the step, 5.6) - so the file is exactly the database's for these steps and
nothing else. After the deploy: re-read `StartedAt` of both API containers (they restarted with the
new file), 0 `[STARTUP] Card description overwritten` lines in both containers' logs
(`ssh ancientnerds "docker logs ancient_nerds_api 2>&1 | grep -c 'Card description overwritten'"`,
likewise `ancient_nerds_api2`), `card_json.py --check` (`ACCEPT_EXIT=0`) and `$PY $MW accept --step N`
again for each step (still 0 deviations), and the `commit` field of `http://localhost:8000/` on the VPS
is the pushed HEAD.

**Never push the file before the database write**: the boot import would write the cards without a
journal, and the journalled write would then refuse every row (matched_0). **Never let an API restart
happen between the write and the push**: the boot would re-import the old file over the new cards
without a journal; `StartedAt` before and after proves it did not happen. If it did (the overwrite
lines name the sites), stop: the step's `accept` lists the sites as deviations, and `plan` lists them
as `journal-disagrees` from then on - an incident for AUDIT_LOG, repaired by its own journalled lane,
never by a second push.

**A red CI inside the sitting** (the pre-push hook aborts the push, or the pushed commit fails a CI
gate, so no deploy pulls the file): the database holds the new cards, the VPS checkout still the old
file, and any API restart until a green deploy would put the old cards back without a journal.
Answer it as P5 did, by undoing the sitting - never by leaving the database ahead of the deployed
file: 5.6's commands 1 and 2 (both `ROLLBACK.sql`, `close-reverted`) for **every** step of the
sitting, the last step first; then its commands 3 and 4 once for the sitting: `card-file --steps
A-B` (every step is now closed as undone, so the file is rendered back to the cards from before the
sitting), `card_json.py --check`, one commit (the file and the trail, `REVERTED/` included) and the
push. Main's file then equals the deployed one whatever the CI does next. (If the hook aborted the
sitting's push, `origin/main` still holds the old file, which the undo made the database's again:
the two local commits go out together with the next green push.) Record the incident in AUDIT_LOG,
and write the sitting again, as new steps, once the CI is green.

### 5.6 Undo

One step - after its acceptance (its file may be out already) or before it - or, in reverse step
order, every step of a sitting. The whole order, one command after the other, **no API restart and
no other push in between** (`StartedAt` of both API containers read before and after, as in 5.4):

```bash
# 1. The database: each lane's ROLLBACK.sql (rehearsed in 5.4), card lane first - its premise needs
#    the provenance the provenance lane wrote. A lane that has no ROLLBACK.sql (0 cells) is skipped.
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" \
  < output/remediation/mechanical_teaser/sNNN/card/ROLLBACK.sql
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" \
  < output/remediation/mechanical_teaser/sNNN/prov/ROLLBACK.sql
# 2. The proof, read-only: ACCEPT_EXIT=0 and "RESULT: 0 write(s) still standing"
$PY $MW close-reverted --step N
# 3. The file, rendered back from production - never a `git revert` of the sitting's commit
$PY $MW card-file --steps N         # or the sitting's A-B; read-only; WRITE_EXIT=0
$PY scripts/remediation/phase4/card_json.py --check     # ACCEPT_EXIT=0 - before the push
# 4. The file and the whole trail in one commit, pushed at once
git add public/data/card_descriptions.json
git add -f output/remediation/mechanical_teaser/STEPS.jsonl output/remediation/mechanical_teaser/ACCEPTED \
  output/remediation/mechanical_teaser/REVERTED output/remediation/mechanical_teaser/sNNN/PLAN.md \
  output/remediation/mechanical_teaser/sNNN/SKIPPED.jsonl output/remediation/mechanical_teaser/sNNN/prov \
  output/remediation/mechanical_teaser/sNNN/card
git commit -m "Lane WB step N undone: the card file rendered back from production"
git push origin main
```

What each gate checks:

- each reversal is journalled under the lane's `-rollback` stamp and refuses unless the row still
  holds exactly what the step wrote;
- `close-reverted` closes the step on production's proof that none of its writes stands: every
  planned cell holds its value from before the step, and every write the step had is followed by
  exactly one reversal, its inverse (a lane never applied has neither). It writes
  `REVERTED/step-NNN.json` (once) **beside** an `ACCEPTED/step-NNN.json` if the step had one - the
  acceptance stays as history. `plan` goes on, and the next step plans the undone step's sites again
  from the same outcomes (while their description is still the one checked): no undone site is
  dropped. If the cards themselves were the reason for the undo, the run's outcomes are suspect:
  plan no further step from it, fix the cause, and ask the sites again in a new run (`select --sites
  FILE` without `--exclude-run` of the old one). A step planned and never applied is closed the same
  way;
- `card-file` renders the file from production and expects each card cell of an undone step at its
  value from before the step (a later named step that planned the same site again wins), each of an
  accepted step at its planned card - so it re-renders after an undo exactly as after a sitting, and
  only the undone step's keys change; the other steps of the sitting keep their teasers;
- `card_json.py --check` proves file == production before anything is pushed. The trail files are
  never reverted: `STEPS.jsonl`, `ACCEPTED/`, `REVERTED/` and the step's plans are the record the
  next `plan`, `accept` and `card-file` read.

After the deploy: the checks of 5.5 (both `StartedAt` moved, 0 overwrite lines, `card_json.py
--check`, the `commit` field). Record the undo and its reason in AUDIT_LOG.

### 5.7 Later

- `$PY $MW stale` (read-only): teaser cards whose description moved since their check (not
  shorts-eligible) and cards no longer the one their provenance hashes. A description rewritten later
  (any lane) makes its card stale; the next `select` asks the site again.
- A run is a directory of its own; `select --exclude-run` keeps a site from being asked twice for the
  same description.

### 5.8 Files

`output/remediation/teaser/runs/<run>/` (gitignored): `EXPORT.jsonl`, `RUN.json`, `SITES.jsonl`,
`LISTED.jsonl`, `ROUNDS.jsonl`, `STAGE-<stage>.jsonl`, `OUTCOMES.jsonl`, `OUTCOMES.md`; for the pilot
`JUDGE.jsonl`, `JUDGE.md`, `pages/`. `output/remediation/handoff/teaser-<run>-<stage>/` (and
`-scratch/`): the handoff. `output/remediation/mechanical_teaser/`: `STEPS.jsonl`, `sNNN/...`,
`ACCEPTED/step-NNN.json`, `REVERTED/step-NNN.json` - force-added to git with the card-file commit
(the proof trail; never reverted).

## 6. Why a mechanical lane and not `write_gate4.py --group P5`

The P5 writer is built around the Phase-4 plan: it writes the card of a site whose `PLAN4.jsonl`
assembly carries one, pins the card to `_description_provenance.card` (an extractive card: sentence
items and drops), refuses every site outside `SCOPE4`, and its code lives in `phase4/`, whose package
hash the Phase-4 mass runs check before every batch (lane WA runs there). A teaser has no items, comes
from a lane-WB run, covers every curated site and needs a provenance of its own. Generalising P5 would
change a writer mid-flight. A mechanical lane already has the whole write discipline - plan-pinned
statements, the rollback rendered before the apply, rehearsal, guard probes, conditional writes
through `apply_remediation_change()`, read-back, rollback rehearsal - and needed one extension: a
column that may be **cleared** (`lane.Column.clears`), for the card of a site that gets none. Two
tables are two lanes, so a step is a pair (`TEASER_LANE` in `mechanical/lane.py` resolves
`teaser-prov-sNNN` and `teaser-card-sNNN`); the per-step acceptance and the card file follow the
P5 sitting's rules (database first, file rendered from it, then the push).

## 7. Merging (the parallel lanes of 2026-09-26)

- **Lane WC** (`wip/wc`): `teaser/run.py` spells WC's check key as the literal `CHECK_KEY =
  "_description_check"`, because `phase4/wc4.py` is not on this branch. The merge replaces the literal
  with `from phase4.wc4 import CHECK_KEY`, so the selection tests of the sentence-checked basis run on
  the real spelling.
- **Lane WA** (`wip/wa`) adds a bullet to the old version of this file (a descriptions-only plan
  writes `provenance.card: null`, P5 refuses its sites, the cards come from lane WB): take this
  version; section 8 records that fact.
- Both branches add cases to the mutation sweeps; keep both sides.

## 8. Superseded: the extractive contract of 2026-09-23

From 2026-09-23 to 2026-09-26 a card was an **extractive condensation** of the site's own
description (design entry [6], card_texts; Phase-4 owner decision O3 "same run, extractive"): the
Phase-4 selector picked 1-2 of the description's sentences, code assembled them (`phase4/
assemble.py`), 80-200 characters, no country name, no unattributed evaluative superlative, pinned
by `_description_provenance.card.text_sha256` (V10, V13) and written in the P5 sitting
(`write_gate4.py --group P5`, `card_json.py --prerender/--regenerate/--check`). 761 such cards are
live (measured above). The owner's decisions O2-O4 of 2026-09-26 replace it: every card, those 761
included, is rewritten as a teaser by lane WB. The Phase-4 scope-v3 run writes its descriptions
without cards (`pass: phase4-descriptions-only`, `provenance.card: null`; P5 refuses its sites). The
P5 code stays for the record of the writes it made; its acceptance (`verify_writes4.py --lane p5`)
describes production only until lane WB rewrites a site's card and nulls its Phase-5 key.

## Retired

Never used for this work, and no longer a way to produce card texts:

- the 10-agent generation flow of 2026-03 (batch inputs, parallel agents, merge) and its rule "if
  the wiki excerpt is empty, write a brief factual description based on the site name, type and
  period" - a card is written only from its site's sourced description;
- `scripts/import_card_descriptions.py`, `scripts/merge_rewrites.py` and the `audit_enrich.py`
  Wave-4 merge - none of them journals, and the last two write the file the boot import reads;
- `scripts/verify_descriptions.py` and `scripts/verify_agent.py` as gates: they penalise hedging.
