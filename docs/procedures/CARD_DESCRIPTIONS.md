# Card descriptions: the teaser contract (lane WB, 2026-09-26)

`card_stats.card_description` is the up-to-200-character text on a site's card: the SiteCard, the
Forgotten Worlds game, search previews and the voice-over of the site's short video. Since the owner's
decisions of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`, binding) every curated card
is a **teaser**, written by one Opus agent from the site's sourced description, checked claim by
claim against that description by another, and **verified claim by claim against pages on the web**
by a third (section 2.1) - a card faithful to a description sentence the web contradicts is still
wrong when it is read aloud:

- O2: "die kartentexte für das game waren eigentlich schön. sie sollten die site teasern und mystisch
  sein. diesen text wollte ich auch für die Shorts. sie müssen alle ungefähr gleich lang sein aber
  natürlich müssen sie inhaltlich stimmen!!!"
- O3: "Alle Karten neu" - all ~4,900 cards, the 761 extractive Phase-5 cards included.
- O4: 160-190 characters (the March cards' median was 172; about 11-13 s spoken).
- O10: "ja wie bisher" - the AI disclosure: `data-card-ai` on the SiteCard, the AI footnote on the
  site page, the AI note in the shorts description.

**Since 2026-10-09 section 9 (contract `shorts-v1`, owner decisions D1-D6 and D10 of 2026-10-08)
supersedes sections 1.3-1.5 for every new card:** the card never names its site, has no question,
is written in three variants and rated for its hook, every answer is given in a registered role by
a registered model, and a failed site keeps its card. Version-1 runs stay importable.

This file is the contract (sections 1-3; the web verification 2.1, the description defects it finds
2.2), the measured population and costs (4), the runbook (5), the reasons behind the write path (6)
and what the merge of the parallel lanes has to do (7). It supersedes the
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
- the site's **name** and **country**;
- in the one rewrite after a failed web verification (2.1) only: the **web facts** (`W1`, `W2`, ...,
  `contract.WebFact`) - each quote of a claim the first verifier found CONTRADICTED that the machine
  found on its page (proven), from a page lane WC's source rule admits by code
  (`wc.answers.url_problem`: not ancientnerds.com, no AI aggregator, no Wikipedia mirror, no blocked
  domain, no `utm_` tracking; a refused page is never proven, 2.1), and **never of the central
  claim** (the verifier's first - what the site is, and where: a page that says the site is
  something else may describe a namesake, so the identity is never corrected from the web;
  `run.web_facts`). The rewrite and its check record the web facts they were shown, and the
  provenance takes them from those records (`run.recorded_web_facts`, which refuses a set the
  first verification no longer offers as it was). A web fact counts only where its page is a reputable
  source - Wikipedia in any language, UNESCO, a national heritage register, a museum, a university,
  an excavation report, a scholarly publication or an established reference work
  (`prompts.REPUTABLE`, lane WC's rule 2) - which the checker of that rewrite decides; the provenance
  records every web fact the card rests on (3.1).

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
| numerals | every numeral of the card is a numeral of the fact basis (name + description without markers; in the rewrite after a failed verification also the web facts' quotes), read by `phase4.scope4.numerals` - the numeral reading of `scope4.ungrounded_card` (digits with comma thousands and a decimal part, compared as values: `3,701` = `3701`). `ungrounded_card` itself is not called because it reads only the first 500 characters of its input (the March generator's); the basis here is the whole description |
| name | the card contains one of the site's **name forms** (1.4) |
| shorts | every glyph is in the brand font, and every caption word fits the frame (1,000 px, `MAX_CAPTION_PX`) **as the short draws it** (`phase4.verify4.card_fit`'s `drawn_px`: `shorts_render.caption_px` at the size the word is drawn, as the short's own audit S3 measures it; Phase 4's V10, unchanged, applies the same measurement at 92 px and is therefore stricter). The short draws a word at 92 px (`CAPTION_SIZE`); a word wider than the frame there - a one-word or hyphenated name: `Saint-Pierre-aux-Nonnains` is 1,407 px in Orbitron 700 - is drawn at the largest integer size at which it fits (`shorts_render.word_face`: `Saint-Pierre-aux-Nonnains` at 65 px), never below 52 px (`CAPTION_MIN_SIZE`, the size of the site's name in its smallest layout). Only a word wider than the frame even at 52 px (about 1,760 px at 92) is refused, with its width and that floor. Since 2026-09-29; until then every word wider than the frame at 92 px was refused, and a site whose name is such a word could get no card (7 writer questions of runs wb-ws-2026-09-27-01, -02 and -04 stalled on it). No prompt states this rule (`check-answer` shows the problem), so the change moved no prompt's sha256: all 4,212 questions exported by runs wb-ws-2026-09-27-01 to -06 rebuild with their exported sha256 (measured 2026-09-29) |

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
the site gets no card: it is cleared** (`failed-after-two-rewrites`). A site that can have no card
at all - every name form holds a glyph the font cannot draw - is declined by its writer and cleared
at once (`name-undrawable`, 2.3).

### 2.1 The web verification (every accepted card)

The checker proves a card faithful to its description; it cannot see a description that is wrong.
The two pilots showed the gap: every card was faithful, and 3 of 40 repeated a description sentence
the web contradicts (Concangis: an aqueduct and latrines where RIB 1049 names a water supply and a
bath-building; Diocletian's Palace: the sphinxes' pharaoh; Syberg: the failed siege in 776, not two
years after 775 - AUDIT_LOG, WB pilots 1 and 2). A card read aloud in a short must not repeat a
contradicted claim (O2: "natürlich müssen sie inhaltlich stimmen"), so **every card a checker
accepted is verified on the web before it can be written**:

- **`verify`** - a **new** Opus agent, the pilot's web judge applied to every card: the same prompt
  (`prompts.judge_prompt`: only name, country and card, never the description; the central claim
  listed first; told which hosts refuse automated readers; never ancientnerds.com), the same answer
  shape (`answers.parse_judge`: every claim SUPPORTED / CONTRADICTED / UNVERIFIABLE with a URL and a
  verbatim quote of at least 20 characters) and the same machine quote check on pages the import
  fetches itself (`opus_audit/quotes.py`, `run.prove_claims`, the lanes' User-Agent, no personal
  data). 5 cards per batch (`JUDGE_BATCH_SIZE`).
- **Every claim, not only the central one**: a verifier's answer lists at least as many claims as
  the check that accepted the card (`run.claims_floor`; `check-answer` tells the verifier the number
  and nothing else, the import refuses a shorter answer). A verifier that listed only the central
  claim, SUPPORTED, would otherwise VERIFY a card whose other claims nobody researched - and the
  mass run has no judge of its own (5.3). The pilot judge is held to the same floor.
- **A proof comes only from a page lane WC's source rule admits** (`wc.answers.url_problem`, the rule
  of the web facts, 1.1): a quote on this project's site, an AI aggregator (`aroundus.com`,
  `grokipedia.com`, ...), a Wikipedia mirror (`wikiwand`, `dbpedia`, ...), a blocked domain or a URL
  with `utm_` tracking is never fetched and never proves anything (`quote_outcome`
  `source refused: <why>`), because such a page may repeat the very text under test - this project's
  card or Wikipedia's wrong sentence - which would make the proof circular. The judge prompt says
  so. A CONTRADICTED claim cited from such a page still counts as a contradiction (never proven).
- **The verdict of a card** (`run.card_verification`), from its judged claims - a claim is
  *proven* when it is SUPPORTED and the machine found its quote on an admitted page:
  - **CONTRADICTED** - at least one claim CONTRADICTED, with a proving quote or without one (a page
    that refused the machine, a PDF, a mis-copied quote): a contradiction is never waved through as
    merely unproven;
  - **VERIFIED** - no contradiction, **at most one claim without a proving quote**
    (`card_provenance.MAX_UNPROVEN_CLAIMS = 1`), and **never the central claim** - the verifier's
    first, which the judge prompt asks to be what kind of place the site is and where (the claim
    without which the card would be about another place);
  - **UNPROVEN** - anything else (two or more claims without a proving quote, or the central one).

  Why this limit: an unproven claim is not a wrong one (the checker proved the description says
  it), but it is a claim no page settled. After the User-Agent fix pilot 2 measured 0 unproven of 122
  claims (pilot 1's 99 were the 403 bug), so the allowance exists for the one page that refuses the
  machine (a heritage register's 403, an unreadable PDF) on a card whose other claims are proven:
  at ~6 claims a card, one is at most a sixth of it. The central claim is never allowed to go
  unproven, because a card whose identity no page confirms may be about a namesake - a class the
  stage-1 measurement of 2026-09-25 found again and again (points on the nearest village or a
  namesake, images of another site; FINISH_PLAN section 2). The aggregate stays measured: every
  `OUTCOMES.md` prints the share of unproven claims of its accepted cards, and the pilot gate holds
  it to 10 % (5.2).
- **`rewrite-v`** - a card not VERIFIED gets **one** rewrite by a new writer
  (`prompts.verify_rewrite_prompt`): the card, every CONTRADICTED claim with its page, quote and
  whether the machine found the quote, every claim the verifier could not prove, and the web facts
  (1.1). The writer drops every contradicted claim or corrects it - **a correction only with a fact
  a sentence of the description or a web fact states** (when in doubt, drop); **what the site is,
  and where, is never corrected from the web** (no web fact is ever offered for it): a contradicted
  central claim is said only as the description says it - `verify2` decides, and the site clears if
  the web contradicts it again - or dropped; the writer keeps at most one unproven claim and never
  the central one, and names for each contradicted claim the description
  sentence that states it (`repeats`: `S3`, or `null` when none does - the input of 2.2). The
  answer is `{"card", "basis", "repeats"}` (`answers.parse_verify_writer`: one entry per
  contradicted claim, each a sentence id of the description or `null`; the basis may name `W1`).
  The card passes the mechanical checks (1.3) against the description plus its web facts.
- **`check-v`** - the ordinary checker (a new agent), on the description plus the web facts: a claim
  may rest on a web fact only if its page is reputable (1.1), else its support is `[]`; a card that
  follows a web fact saying the site is something else, or somewhere else, than the description
  says is `this_site: false` (the page may be about a namesake).
- **`verify2`** - a **new** verifier, as `verify`.
- A card VERIFIED at `verify2` is accepted; the provenance records the web facts its check cites. A
  card still not VERIFIED clears the site: **`contradicted-after-verify`** (still contradicted) or
  **`unproven-after-verify`**; a rewrite that fails the mechanical checks or `check-v` never reaches
  `verify2` and clears the site as **`failed-after-verify-rewrite`**. There is no second rewrite.

Only a VERIFIED card is ever written (5.4). The stage order of a run is **`write`, `check`,
`rewrite1`, `check1`, `rewrite2`, `check2`, `verify`, `rewrite-v`, `check-v`, `verify2`**: the
verification follows every check round, so `verify` is exported once for every card any checker
accepted.

**The data ties every judgement to its card**, not the order the stages are run in: every check and
verification records the card it judged, and a site's state counts it only for the card of the
writer record it follows (`run.judging`: else `RunError`, "STAGE-X judged another card than STAGE-Y
holds"). An import that would record another card under a later stage's judgement - a stage
imported again with other answers after a later stage was imported, for example after deleting a
valid answer and having it answered again - is refused before it writes anything
(`run.import_stage`); the earlier record's `written` is the answer the later stages judged. The
provenance repeats the tie: `verify.text_sha256` is the sha256 of the text the verifier judged, and
`card_provenance.validate` refuses it unless it is the card's `text_sha256` (3.1).

### 2.2 The description defects (`DESCRIPTION_DEFECTS.jsonl`)

`run.py outcomes` writes, per run, one line per contradicted claim (proven or not) that repeats the
site's description (`run.description_defects`): site id and name, the description's basis and
sha256, the verifier's `stage`, the claim, the verifier's contradicting `url` and `quote`, whether
the machine found the quote (`proven`, `quote_outcome`), the `verifier`, and where in the
description the claim sits:

- **the first verifier's** (`stage: "verify"`): each claim the rewrite's writer mapped to a sentence
  (`repeats`) - `sentence` n and `sentence_text`, `candidates` that one id, `mapped_by` the writer. A
  claim mapped to no sentence (`null`) is the card's own departure - a lane-WB fault, visible in
  `OUTCOMES.jsonl` - and no description defect;
- **the second verifier's** (`stage: "verify2"`): each contradicted claim of a card `check-v`
  accepted. No writer sees these (the site is cleared), so `sentence`, `sentence_text` and
  `mapped_by` are `null`, and `candidates` lists every description sentence the accepting `check-v`
  cited (the claims of checker and verifier are worded apart, so the machine cannot pair them): the
  repair reads those sentences and finds the one the web contradicts. A card whose `check-v` claims
  rest on web facts alone says nothing of the description, and its contradiction is no defect.

Every contradiction also stays in `OUTCOMES.jsonl` (`verifications`) and in `OUTCOMES.md`'s section
"Every contradiction the verifiers found".

**Who repairs them**: the lane whose text it is - `owner_lane` `WA` for a Phase-4 text (basis
W/S/T/R, lane WA's scope-v3 descriptions and the Phase-4 texts before it), `WC` for a
sentence-checked March text (basis `WC`) - by lane WC's method (the sentence checked against a
quoted source and kept, trimmed or dropped, `docs/procedures/SENTENCE_CHECK.md`). Until that lane
runs a repair step for them, the files are the list - both kinds of line, a `verify2` line with its
candidate sentences instead of one: each run's count goes into AUDIT_LOG with the run. A repaired
description changes its sha256, so the site's card turns stale (3.1) and the next `select` asks the
site again.

**Independence is a process rule, kept by whoever runs the batches**: every batch of every stage -
and of the pilot judge - gets a **new** agent, and the brief (`run.py brief`) tells an agent that
answered any other batch of lane WB to stop. The import cannot see an agent: `answered_by` is the
batch's name (`teaser-<batch_id>`, and every batch id carries its stage), so its refusal of a checker
or verifier whose name wrote, checked or verified the site before (a verifier never wrote or checked
its card; `verify2` is never `verify`'s agent), and of a pilot judge whose name answered any question
of the run, catches only a reused or mistyped name - one agent reused under two batch names goes
undetected by code. The provenance repeats the one check it can make itself: its verifier is not its
checker.

### 2.3 A site no card can be written for (`name-undrawable`, since 2026-09-30)

A card must contain a name form (1.4), and every glyph of the site's name and card must be one the
shorts font draws (1.3: `fit(site.name, card)`). A site whose **every name form contains a glyph
neither brand font draws** can pass neither: with its name the font check refuses the card, without
it the name check does. So `Jabal al-ʿHayn` (7ccaad38-8cfb-401e-a938-e2c792914b75; U+02BF is in
neither Orbitron 700 nor JetBrains Mono 700) stalled batch write-014 of run wb-ws-2026-09-27-02
(449 of 450 answered): `check-answer` reported a `name` and a `font` problem for every card, and the
write stage had no way to decline. Owner O2/O3 (a card is a shorts-drawable teaser) and O6 ("belegt
ersetzen, sonst leeren"): such a site gets **no card - it is cleared**, never a card without its name
or with a glyph the short draws as a box.

- **The answer**: `{"card": null, "basis": [], "undrawable": true}`, in `write`, `rewrite1` or
  `rewrite2` (`answers.parse_writer` -> `Declined`; any other shape is refused, and the rewrite after
  a failed verification never declines: its card passed both checks, so a name form can be drawn).
- **Only where the contract proves it**: `check-answer` and the import accept it only if
  `contract.undrawable_proof` does - the font check itself, the same `fit(site.name, form)` call that
  measures every card (no second glyph table), reports a missing glyph for **every** name form. The
  stored name is drawn with every card, so an undrawable stored name taints every form, a plain alias
  included. For a site with a drawable form the answer is refused and names the forms that can be
  drawn: write the card with one of them. `check-answer` prints `"ok": true, "card": null` and the
  proof (`"undrawable": {form: [glyphs]}`) for an accepted decline.
- **The flow**: the stage record holds `card: null` and the proof; the site is **cleared at once**
  with reason `name-undrawable` - no check, rewrite, verification or second verification asks it
  (`run.progress`), `attempts` is 0, and its `OUTCOMES.jsonl` row carries the proof sentence as its
  finding (`card: null`). `mechanical/teaser.py plan` plans it like every clear (5.4: rule
  `card-clear-name-undrawable`, card `NULL`, the teaser provenance removed, a Phase-5 card key
  nulled, premise = the description's sha256), so a site that holds an old card loses it, and the
  journal evidence quotes the proof.
- **Where the writer learns of it**: the brief (`run.py brief`, appended for `write`, `rewrite1` and
  `rewrite2` batches) and nowhere else. The questions' prompts are unchanged - an export pins its
  prompts' sha256, and a new rule in them would stale every exported answer - so all 7,231 questions
  of the rounds exported so far (runs wb-ws-2026-09-27-01 to -06) rebuild with their exported sha256
  (measured 2026-09-30).
- **Population** (measured 2026-09-30 on run wb-ws-2026-09-27-02's read-only export of the 5,004
  curated sites): two - `Jabal al-ʿHayn` and `Gate of All Nations<U+200C> Persepolis`
  (f9cfc5f7-a6c8-4c6f-9d82-f30151a36d6c, a zero-width non-joiner in its stored name; in no run yet).
- **Tests and sweep**: `TestTheUndrawableProof` and `TestAnUndrawableName` in `test_teaser.py`, the
  clear in `test_mechanical_teaser.py`; `mutation_sweep.py "teaser: undrawable"` (21 cases, all
  fired: `output/remediation/mechanical/evidence/25_mutation_sweep_undrawable.txt`).

## 3. Storage and display

### 3.1 The provenance: `unified_sites.raw_data._card_provenance`

```json
{"v": 2, "kind": "teaser", "lane": "WB", "ai": "generated",
 "ai_system": "Claude Opus (Anthropic): ..., an-sites-remediation-2026-09", "run": "<run>",
 "text_sha256": "<sha256 of the card>", "desc_sha256": "<sha256 of the description it was written from>",
 "check": {"verdict": "PASS", "stage": "check|check1|check2|check-v", "by": "teaser-check-007",
           "at": "<answered_at>", "claims": [{"claim": "...", "support": ["S2", "W1"]}]},
 "verify": {"verdict": "VERIFIED", "stage": "verify|verify2", "by": "teaser-verify-031",
            "at": "<answered_at>", "claims": 6, "unproven": 0,
            "text_sha256": "<sha256 of the text the verifier judged: the card's>"},
 "web_facts": [{"id": "W1", "url": "https://...", "quote": "..."}]}
```

Version 2 since the web verification (2026-09-26; no version 1 was ever written - read-only count
that evening: 0 teaser provenances in production). `verify` is the verifier (stage, agent, time),
its verdict - `VERIFIED` is the only one written - the counts of its claims and of those without a
proving quote (at most 1, and never all: the central claim is proven) and the sha256 of the text it
judged, which must be the card's `text_sha256` (a verification of another text proves nothing about
this card, 2.1); `verify2` belongs to a `check-v` check and `verify` to every other, and the
verifier is never the checker.
`web_facts` is `[]` except on a card rewritten after a failed verification, and then holds exactly
the web facts its check's claims cite (`W1` in a claim's support) - the card's fact basis beyond the
description. The journal evidence of the write carries the rest: each judged claim with its page
(5.4).

Its own key, because `_description_provenance` is replaced whole whenever a description is rewritten
and a card outlives that; the leading underscore keeps it out of the popup's raw-data panel. Shape,
builder and readers: `pipeline/utils/card_provenance.py` (stdlib only - the Lyra image ships
`pipeline/` without `api/`). Nothing is defaulted: a malformed provenance raises on every reader.
`ai_system` is `model4.AI_SYSTEM_OPUS` in every provenance written until 2026-09-30 and
`model4.AI_SYSTEM` (Opus and Sonnet) in every one written after the owner decision of 2026-10-01; the 185
provenances whose card a Sonnet rewrite agent wrote are corrected to the latter (5.9).
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
  `card_ai` and `card_ai_system` (the provenance's `ai_system`); `shorts_render.teaser_note` builds the
  description's AI note from it (owner decision 2026-10-08) and names exactly the models that string
  names, e.g. "Text: AI-generated by Claude Opus 5.5, Claude Sonnet 5.5 (Anthropic) from the site's
  sourced description, each claim checked against it." A string naming no model, or one the note cannot
  name, stops the description. A `site.json` exported before lane WB lacks `card_ai` and carries the old
  card: re-export before rendering. The closing name line is `site.json`'s `spoken_name` (column
  `unified_sites.spoken_name`, migration 0029) where set, else `name`.

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
writer batch; **one verifier batch per 5 cards**, `JUDGE_BATCH_SIZE`, as the pilot judge's):

| run | sites | write | check | rewrites | verify | rewrite-v / check-v | verify2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pilot | 20 | 2 | 2 | as needed | 4 | 1 / 1 | 1 |
| the 989 candidates of today | 989 | 66 | <= 66 | ~13 per round at 20 % failing | <= 198 | ~5 / ~5 | ~15 |
| every non-retired curated site (upper bound after WA/WC) | 4,926 | 329 | <= 329 | ~66 per round at 20 % failing | <= 986 | ~25 / ~25 | ~74 |

The verify column is every accepted card at 5 a batch - the largest stage of a run, three verifier
batches for each writer batch, each card researched and quoted on the web. The verify-rewrite
columns assume the pilots' rate of cards not VERIFIED, 3 of 40 (7.5 %): ~74 of 989, ~370 of 4,926
cards, at 15 per rewrite batch and 5 per `verify2` batch. At 16 agents at a time (O11) a stage of
329 batches is 21 waves and the `verify` stage of the full population 62. The pilot measures the
failure rates that size the rewrite rounds.

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
   15 (`<stage>-001`, ...; a verify stage 5 per batch). It refuses while an earlier stage waits for
   its import, a second export of the stage, and a non-empty directory. `"questions": 0` means nobody
   is due: go to the next stage.
2. For each batch `B`, a **new** Opus agent - never one that answered another batch of lane WB (the
   independence rule, section 2.2's last paragraph; the code cannot check it); its whole instruction
   is the output of `$PY $T brief --run $RUN --handoff $H-<stage> --batch-id B` (a writer, a checker
   or - at `verify` and `verify2` - a verifier with web access). At most 16 agents at a time; each
   answers its own batch into its own scratch directory (`$H-<stage>-scratch/B/`), checks every answer
   with `run.py check-answer` (a writer until it prints `"ok": true`; nothing is recorded by it) and
   records it with `opus_handoff.py answer --model <the model id it runs as> --answered-by teaser-B` (write-once). An agent that stopped
   (the API limit) is replaced by a new one with the same brief; recorded answers stay.
3. `$PY $OH validate --dir $H-<stage>` - every question answered, for its exact prompt, by Opus, in
   shape. Gate: no missing, stale, malformed or orphan answer.
4. `$PY $T import --run $RUN --stage <stage>` - rebuilds every prompt from the run's pinned files and
   refuses an answer to any other, a checker or verifier answer recorded under a name that wrote,
   checked or verified the site before (a reused name) and a malformed answer (delete that answer
   file, re-brief the batch) - a verifier's answer that lists fewer claims than the accepting check
   is one (2.1). It also refuses, writing nothing, an import that would record another card under a
   later stage's check or verification (2.1, "The data ties every judgement to its card"): once a
   later stage is imported, a stage is imported again only with the answers it had. The import of
   `verify` and `verify2` fetches every cited page the source rule admits into `$RUN/pages/`
   (User-Agent `AncientMapRemediation/1.0 (research; https://ancientnerds.com)`,
   `research_web.USER_AGENT`, no personal data, 1 s between two requests to one host) and checks
   every quote by machine. A page is fetched once, except a fetch that failed for a reason that may
   pass - no answer at all, 429, a 5xx (`run.may_pass`) - which every import tries again; any
   other status (a 404, a register's 403) is the page's answer and is kept. The import prints those
   still failing as `transient_failures`: while the list is not empty, wait and **run the same
   import again before exporting the next stage** (it replaces the stage's records; a claim whose
   page keeps failing stays unproven). Duration: pilot 2 cited 32 pages for 20 cards (22 on
   en.wikipedia.org) and fetched them in 29 s; the per-host pace makes the Wikipedia share the
   bound - about 1,600 pages and at least ~18 min for the 989 candidates of today, about 8,000 pages
   and ~1.5 h for the whole population (projected, not measured). Writes `STAGE-<stage>.jsonl`;
   prints the mechanical failures (writer stages) or the verdicts (checker stages: PASS/FAIL; verify
   stages: VERIFIED/CONTRADICTED/UNPROVEN, and `transient_failures`).
5. `$PY $T status --run $RUN` - who is due where, accepted, cleared.

**The stages in order: `write`, `check`, `rewrite1`, `check1`, `rewrite2`, `check2`, `verify`,
`rewrite-v`, `check-v`, `verify2`** (2, 2.1). Then `$PY $T outcomes --run $RUN` (refused while a
site is still due) writes `OUTCOMES.jsonl` - each accepted (checked and VERIFIED) card with its
provenance; each cleared site with its reason: `failed-after-two-rewrites`,
`failed-after-verify-rewrite`, `contradicted-after-verify`, `unproven-after-verify`,
`name-undrawable` (2.3), or `no-description` for a site without a description that still has a card; every row with its
verification state (`verification`: the last verdict, `null` for a card never verified) and every
verification in full (`verifications`: the verifier, the card, each claim with its page, quote and
whether the machine found it) - `OUTCOMES.md` (counts, the unproven share of the accepted cards,
"Every contradiction the verifiers found", a verification column) and `DESCRIPTION_DEFECTS.jsonl`
(2.2).

### 5.2 The pilots: 20 sites each and a fresh independent web judge

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
2. The ten stages and `outcomes` (5.1) - the per-card web verification included: the pilot's
   final cards are the ones its verifiers found VERIFIED.
3. `$PY $T judge-export --run $RUN --handoff $H-judge` - every accepted card (the final, VERIFIED
   card, the one to be written), 5 per batch, to a **fresh** Opus agent with web access (the brief
   from `$PY $T brief --run $RUN --handoff $H-judge --batch-id judge-NNN`) that answered nothing in
   the run - no card written, checked or **verified**. The judge sees only the site's name, country
   and card (`prompts.judge_prompt`, the verifiers' own question) and decides every claim SUPPORTED /
   CONTRADICTED / UNVERIFIABLE against pages it opens and quotes; it is told which hosts refuse
   automated readers (Historic England and the Heritage Gateway answer 403, UNESCO often refuses,
   PDFs may be unreadable) and never to cite ancientnerds.com.
4. `$PY $OH validate --dir $H-judge`, then `$PY $T judge-import --run $RUN` - refuses a judge answer
   recorded under a name that answered any question of the run (a writer, checker or verifier of any
   card) and one that lists fewer claims than the card's accepting check (2.1); fetches every cited
   page the source rule admits into `$RUN/pages/` (the lanes' User-Agent and the retry of a failure
   that may pass, 5.1: while `transient_failures` is not empty, run `judge-import` again) and checks
   every quote by machine (`scripts/remediation/opus_audit/quotes.py`); writes `JUDGE.jsonl` and
   `JUDGE.md`. **Gate (exit 0): on the pilot's final written cards, the fresh judge finds no claim
   CONTRADICTED - with a proving quote or without one - and at most 10 % of all claims without a
   proving quote** (UNVERIFIABLE, or a quote the machine did not find on the page). A contradiction
   whose page refused the machine (403, a PDF, a JS page) or whose quote was mis-copied is still a
   contradiction: it is counted apart (`contradicted_unproven`, `disputed_cards`), shown in the
   summary line and in `JUDGE.md`'s header, and fails the pilot like a proven one.
5. Read `JUDGE.md`: first its section **"Every contradiction"** - each line, proven or not, with the
   page it cites: is the card wrong, or is its description (the card says what a sentence says)? -
   then `OUTCOMES.md`: "Every contradiction the verifiers found" (did the rewrites drop or correct
   them properly?), the unproven share, and the tone (evocative, a little mysterious, about the same
   length); and `DESCRIPTION_DEFECTS.jsonl` (2.2, its count into AUDIT_LOG). A contradiction the
   fresh judge still finds means the per-card verification let a wrong card through - a lane-WB
   failure (prompts, the VERIFIED rule or the contract), whatever the description says. The pilot
   FAILED: change the code (tests, commit) and draw a **new** pilot run with a new seed; a failed
   pilot's outcomes are never written. A PASS: write the pilot's outcomes (5.4) - they are the first
   step of their kind - and start the mass run over that basis. **The mass run relies on the per-card
   verification**: it has no judge of its own.

### 5.3 The mass run

Preconditions: the sites' descriptions are final - lane WA's P4 writes and lane WC's writes are
accepted for the sites to be asked - and the pilot of their basis passed (5.2). Sites whose text is
not final yet are listed `not-final` and are asked by a later run.

1. `$PY $T select --run $RUN2 --exclude-run $RUN --basis W --basis S --basis T --basis R` (every
   earlier run of lane WB **whose outcomes were written** (5.4), each with its own `--exclude-run`):
   a site asked before is asked again only if its description changed since. **Never exclude a run
   that was not written**: the two pilots from before the web verification
   (`wb-pilot-2026-09-26`, `wb-pilot-2026-09-26b`: never written, their outcomes carry no
   verification and cannot be) and any failed pilot (5.2) - their sites would be listed
   `asked-before` and get no teaser while they keep their old card (O3: "Alle Karten neu"); `stale`
   does not list them either, because they have no teaser provenance. The `--basis` list keeps the
   sentence-checked texts out until their own pilot passed; after that, a run over them names
   `--basis WC` (or no `--basis` at all).
2. The ten stages and `outcomes` (5.1), 16 agents at a time - every accepted card verified on the
   web (2.1), the only guard against a description the web contradicts.
3. Record the run in AUDIT_LOG: its counts per reason, the unproven share, the number of
   `DESCRIPTION_DEFECTS.jsonl` lines, handed to the lane whose text it is (2.2).
4. The write (5.4), step by step.
5. After WC finishes, the same again for the sites WC made final (`--exclude-run` for every earlier
   run whose outcomes were written, step 1), until `select` lists no `not-final` site.

### 5.4 The write: steps of at most 100 sites, each accepted with 0 deviations

Each step is **two journalled lanes** (6): `teaser-prov-sNNN` (`unified_sites.raw_data`: the teaser
provenance, the Phase-5 card key nulled) and `teaser-card-sNNN` (`card_stats.card_description`: the
card, or `NULL`). Provenance first, card second; undo the other way round. **Only a VERIFIED card
is written**: an accepted outcome carries `verification: "VERIFIED"` and a provenance whose `verify`
says so; every site the run cleared - `contradicted-after-verify` and the other verify reasons
included - loses the card it has (rule `card-clear-<reason>`). The journal evidence of each card
cell names the writer, the checker with its claims, the verifier with every judged claim and its
page, and each web fact the card rests on.

Once per sitting, before the first apply:

```bash
ssh ancientnerds "cd /var/www/ancientnerds/scripts/remediation && DO_DRILL=1 ./00_backup_and_drill.sh"
#   judged by its VERDICT line
ssh ancientnerds "docker inspect -f '{{.Name}} {{.State.StartedAt}}' ancient_nerds_api ancient_nerds_api2"
#   noted for the record; an API restart inside the sitting is harmless (5.5)
```

A card write is database-only (5.5): no push lock, no file push. A deploy during the sitting is
harmless once the D25 code is live (check the `commit` field of `http://localhost:8000/` on the VPS
against the push that removed the boot import); until then the old boot import still writes the file's
cards over the database at every API start, so the push lock holds.

Per step `N` (`NNN` = the step number with three digits; step numbers run across runs):

```bash
$PY $MW plan --run $RUN --step N
#   read-only; --run takes the run's directory ($RUN, as run.py does) or its bare name. The next
#   <=100 outcomes of the run: output/remediation/mechanical_teaser/sNNN/ (export.jsonl, PLAN.md,
#   SKIPPED.jsonl, prov/ and card/ with PLAN.jsonl, and ROLLBACK.sql for a lane with cells).
#   Refused while step N-1 is not closed (accept, or close-reverted after an undo). A site that
#   changed since its check is listed, not written: stale-description, retired, no-card-row,
#   journal-chain-broken, journal-disagrees, raw-data-not-an-object, raw-data-not-reprinted,
#   nothing-to-change; and an accepted card without a VERIFIED verification: not-verified (an
#   OUTCOMES.jsonl from before the verify stage - PLAN.md explains each).
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

- the plan (`mechanical/teaser.py classify`): an accepted card is VERIFIED (else `not-verified`), and
  its provenance validates (`verify` VERIFIED within the unproven limit, by another agent than the
  checker, of the card itself - `verify.text_sha256` is the card's; `web_facts` exactly the cited
  ones); the live description is the one the card was checked
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

### 5.5 The database is the one copy of a card text

Since D25 (2026-10-08) `card_stats.card_description` lives in the database only; this holds from the
deploy of the push that removed the boot import (before it, 5.4's lock applies). The API boot no
longer imports `public/data/card_descriptions.json` (`api/services/card_descriptions.py` is gone),
`teaser.py card-file` and `phase4/card_json.py` are gone, and the frontend and the static exporter
read the column from the database. So a sitting ends with its `accept --step N`, and:

- **No push lock for card writes.** Any push to `main` and any API restart may happen between two
  steps; nothing re-imports an old card. The lock stays for the pushes themselves.
- **No file to render, check or push.** The write order of 5.4 is the whole procedure: provenance
  lane, card lane, `accept`.
- **The trail is committed, not deployed.** After a sitting, force-add the proof trail and commit it
  with the next push that happens anyway:

```bash
MT=output/remediation/mechanical_teaser
git add -f $MT/STEPS.jsonl $MT/ACCEPTED $MT/sNNN/PLAN.md $MT/sNNN/SKIPPED.jsonl   $MT/sNNN/prov $MT/sNNN/card          # every step of the sitting; $MT/REVERTED too once it exists
git commit -m "Lane WB steps A-B: the trail of the sitting"
```

- **The static export** (`public/data/sites/`) follows the database through the export routine, not
  through a push of a card file.
- **`public/data/card_descriptions.json`** stays in the tree until the code of D25 is live, then a
  later push deletes it. It is a dead copy meanwhile: never edit it, never render it, nobody reads
  it. `scripts/import_card_descriptions.py`, `scripts/merge_rewrites.py` and the `audit_enrich.py`
  Wave-4 merge are not used for card work.

A red CI inside a sitting changes nothing for the cards: the database holds them whatever the
deploy does.

### 5.6 Undo

One step, after its acceptance or before it, or, in reverse step order, every step of a sitting. The
undo is database-only, one command after the other:

```bash
# 1. The database: each lane's ROLLBACK.sql (rehearsed in 5.4), card lane first - its premise needs
#    the provenance the provenance lane wrote. A lane that has no ROLLBACK.sql (0 cells) is skipped.
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1"   < output/remediation/mechanical_teaser/sNNN/card/ROLLBACK.sql
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1"   < output/remediation/mechanical_teaser/sNNN/prov/ROLLBACK.sql
# 2. The proof, read-only: ACCEPT_EXIT=0 and "RESULT: 0 write(s) still standing"
$PY $MW close-reverted --step N
# 3. The trail in one commit (REVERTED/ is new)
git add -f output/remediation/mechanical_teaser/STEPS.jsonl output/remediation/mechanical_teaser/ACCEPTED   output/remediation/mechanical_teaser/REVERTED output/remediation/mechanical_teaser/sNNN/PLAN.md   output/remediation/mechanical_teaser/sNNN/SKIPPED.jsonl output/remediation/mechanical_teaser/sNNN/prov   output/remediation/mechanical_teaser/sNNN/card
git commit -m "Lane WB step N undone: the trail"
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
- the trail files are never reverted: `STEPS.jsonl`, `ACCEPTED/`, `REVERTED/` and the step's plans
  are the record the next `plan` and `accept` read.

Record the undo and its reason in AUDIT_LOG.

### 5.7 Later

- `$PY $MW stale` (read-only): teaser cards whose description moved since their check (not
  shorts-eligible) and cards no longer the one their provenance hashes. A description rewritten later
  (any lane) makes its card stale; the next `select` asks the site again.
- A run is a directory of its own; `select --exclude-run` keeps a site from being asked twice for the
  same description - named only for runs whose outcomes were written (5.3, step 1).

### 5.8 Files

`output/remediation/teaser/runs/<run>/` (gitignored): `EXPORT.jsonl`, `RUN.json`, `SITES.jsonl`,
`LISTED.jsonl`, `ROUNDS.jsonl`, `STAGE-<stage>.jsonl` (for `verify`/`verify2` each claim with its
quote outcome and the card's verdict), `pages/` (every page a verifier or judge cited, fetched once),
`OUTCOMES.jsonl`, `OUTCOMES.md`, `DESCRIPTION_DEFECTS.jsonl` (2.2); for the pilot `JUDGE.jsonl`,
`JUDGE.md`. `output/remediation/handoff/teaser-<run>-<stage>/` (and
`-scratch/`): the handoff. `output/remediation/mechanical_teaser/`: `STEPS.jsonl`, `sNNN/...`,
`ACCEPTED/step-NNN.json`, `REVERTED/step-NNN.json` - force-added to git after each sitting
(the proof trail; never reverted). `output/remediation/mechanical_card_disclosure/`: `LIST.jsonl` (the 185
sites with their census proof), `sNNN/...`, `ACCEPTED/step-NNN.json` (5.9).

### 5.9 The disclosure correction (`card-disclosure-sNNN`, 2026-10-01)

**What it fixes.** Until 2026-09-30 every card provenance named Claude Opus only
(`model4.AI_SYSTEM_OPUS`). The model census of 2026-10-01
(`output/remediation/model_census/ANSWERS_TRUE_MODEL.jsonl`: per handoff answer the agent that recorded
it, its time and the model that really ran, read from the Claude Code transcripts) shows that the
rewrite stages (`rewrite1`, `rewrite2`, `rewrite-v`) of runs `wb-ws-2026-09-27-01`, `-04` and `-06` were
answered by Sonnet 5.5 agents. Where such a rewrite produced a card's final text, the live provenance
names a model that did not write it: **185 cards** (01: 54, 04: 52, 06: 79; read-only, 2026-10-01). The
owner decision of the same day - the orchestrator is Opus 5.5, every answering agent Sonnet 5.5 - makes
`model4.AI_SYSTEM` ("Claude Opus and Claude Sonnet (Anthropic) ...") the disclosure of every new write;
this lane writes it into those 185 provenances and **changes nothing else**.

**Do later runs need it? No.** Runs 02 and 05 have no `OUTCOMES.jsonl` yet; their outcomes are built
after the stamp change (`teaser/run.py outcome_rows(ai_system=model4.AI_SYSTEM)`) and carry
`AI_SYSTEM` from the start. Run 03 was answered by Opus throughout, and the cards of runs 01/04/06 that
an Opus writer wrote keep the Opus-only string, which is true of their text. (The checkers and verifiers
of runs 01/04/06 were Sonnet agents for every card; the provenance names them per card in `check.by` /
`verify.by`, and `ai_system` discloses the system that wrote the text.)

**The list** (`card_disclosure.py list`, offline). Each site a closed lane-WB step left a teaser
provenance on is joined to its run's outcome (its provenance must be the step's) and the outcome's
writer record to the census; it is listed when the model that really wrote the final text is not named
by the provenance's `ai_system`. A writer the census cannot name exactly (no row, two models, a model
other than Opus 5.5 / Sonnet 5.5) is a refusal, never a guess. The list is pinned: `card_disclosure_list.py`
holds the 185 ids and their sha256 (`af59f0ff...13c1`); `list --check` re-derives it, and every `plan` does
so first. Steps of at most 100 sites: **s001 = 100, s002 = 85.**

**What a step writes.** One cell lane per step, `unified_sites.raw_data` (stamp
`wb-card-disclosure-sNNN`, test id `WB/card-disclosure`): `_card_provenance.ai_system`, from `AI_SYSTEM_OPUS`
to `AI_SYSTEM`, every other key as it was. The plan lists, and does not write, a site whose live provenance
is not exactly the run outcome's provenance (`teaser-provenance-moved`), that already names `AI_SYSTEM`
(`already-corrected`), that has none, or whose raw_data is not printed the way the planner prints JSON.
In the transaction: guard 3 holds the whole old `raw_data` (no other key can have moved), guard 5 the
provenance's identity (`run|text_sha256|desc_sha256`: a card replaced since is refused), and the lane
invariant refuses a provenance that names neither disclosure, write and reversal alike. The read-back counts
the journal rows that changed anything but this key (**must be 0**) and the sites still naming the Opus-only
disclosure. Measured read-only on production on 2026-10-01: both steps plan with 0 skipped
(`--verify`: 1,790 provenances name the Opus-only disclosure, 0 the new one, 0 name neither, 0 teaser
provenances do not hash their card).

**Preconditions.** The sitting's usual ones (5.4: backup and drill once, no deploy in between). No lane that
writes `raw_data` of these sites may sit between its `plan` and its `apply`: a lane-WB step, a WC or P4
write step, a P4 v3 batch - their guard 3 would refuse the stale plan, so re-plan them after this lane.
The write changes the page columns of 185 sites (`raw_data` counts as a page write): their sitemap
`lastmod` moves and the hourly IndexNow cycle announces them; no page byte changes (the page shows the AI
mark, not the system string).

```bash
PY=./.venv/Scripts/python.exe; CD=scripts/remediation/mechanical/card_disclosure.py
AP=scripts/remediation/mechanical/apply.py; MW=scripts/remediation/mechanical/teaser.py
$PY $CD list --check                 # offline; LIST_EXIT=0 and "the pinned list holds: 185 sites, sha256 af59f0ff..."
for N in 1 2; do                     # step 2 only after step 1 is accepted
  S=$(printf 's%03d' $N)
  $PY $CD plan --step $N             # read-only; output/remediation/mechanical_card_disclosure/$S/ (PLAN.md,
                                     # SKIPPED.jsonl, PLAN.jsonl, ROLLBACK.sql); WRITE_EXIT=0
  $PY $AP --lane card-disclosure-$S --check-primitive
  $PY $AP --lane card-disclosure-$S --verify      # before: the lane's "listed sites of this step still naming ..." = the step's sites
  $PY $AP --lane card-disclosure-$S --emit        # APPLY.sql, pinned to the plan
  $PY $AP --lane card-disclosure-$S --rehearse    # COMMIT -> ROLLBACK
  $PY $AP --lane card-disclosure-$S --probe-guards     # 6 probes, each refused by its own guard (exit 0)
  $PY $AP --lane card-disclosure-$S --apply       # exit 0 = committed and read back
  $PY $AP --lane card-disclosure-$S --verify      # after: 0 still naming; 0 rows changed anything but the key
  $PY $AP --lane card-disclosure-$S --rehearse-rollback
  $PY $CD accept --step $N           # read-only; ACCEPT_EXIT=0 and "RESULT: 0 deviation(s)" only
done
```

**Gate: 0 deviations - never a blanket allowance.** The later acceptances take this lane by its own stamp,
for its one key, and nothing else:

```bash
# lane WB's own acceptance of every step that wrote one of the 185 sites - the steps 7 to 21 (the
# `step` column of output/remediation/mechanical_card_disclosure/LIST.jsonl): the correction's journal
# row is read as the one-key transition from exactly what the step wrote (teaser.corrected_cell)
for N in $(seq 7 21); do $PY $MW accept --step $N; done   # each ACCEPT_EXIT=0 and "RESULT: 0 deviation(s)"
# verify_writes4 for lane p4 AND p4wc (all 185 sites carry a P4 description - 180 lane W, 5 lane S,
# read-only 2026-10-01 - and every p4 acceptance is cumulative): the stamp pattern of THIS lane beside
# lane WB's, never `%`. As a direct command the quotes are right; inside a variable that is expanded
# unquoted ($V, $ALLOW) leave them out.
$PY output/remediation/tools/verify_writes4.py --lane p4wc --plan <PLAN.jsonl> \
  --allow-stamp 'wb-teaser-prov-%' --allow-stamp 'wb-card-disclosure-s%'
$PY output/remediation/tools/verify_writes4.py --lane p4 <the run arguments of PHASE4_V3_RUNBOOK.md 10> \
  $ALLOW --allow-stamp 'wb-teaser-prov-%' --allow-stamp 'wb-card-disclosure-s%'
```

`teaser.py accept` takes the correction only as ONE journal row of the correction lane's own stamp
(`wb-card-disclosure-sNNN`, regex `^wb-card-disclosure-s\d{3}$`), on `unified_sites.raw_data` of that
site, written once and not reversed, from exactly the `raw_data` the step planned to exactly that value
with `_card_provenance.ai_system` set to `AI_SYSTEM` and nothing else; a journal row of another stamp, an
other column or site, one that started from another value, one whose value is not what production holds,
or one that moved a second key leaves the cell a deviation of the step. `verify_writes4`'s `--allow-stamp`
takes a pattern of stamps, and reads this lane's links by key as well (`superseding`): a link of a
`wb-card-disclosure-sNNN` stamp supersedes only as the one-key transition `AI_SYSTEM_OPUS` ->
`AI_SYSTEM` of `_card_provenance.ai_system`, whichever pattern allows it (even `%`); one that moved a
second key, or did not start from the Opus-only value, stays CHANGED LATER. The pattern still names this
lane only. Besides that, the lane's own read-back (0 journal rows that changed anything but the key) and
`card_disclosure.py accept` (journal old -> new is the one-key transition, plan and journal alike) prove it.

**A re-plan never puts the old string back.** The outcomes of runs 01/04/06 still hold the Opus-only
provenance (the list requires it to equal the step's). `teaser.classify` therefore refuses an accepted
outcome of one of the 185 listed sites whose `ai_system` is `AI_SYSTEM_OPUS` (reason
`disclosure-corrected-since`, a SKIPPED row, nothing written): after undoing a WB step that holds corrected
sites (this lane's ROLLBACK first, see below) the outcomes of those sites have to be rebuilt with the
current `ai_system` before the step can be planned again, or this correction re-run under a new lane.

**Open owner decision: the checkers and verifiers.** The lane keeps to the 185 cards a Sonnet agent
*wrote*. Cards an Opus agent wrote but a Sonnet agent checked and verified keep the Opus-only string:
**1,140** live cards (measured 2026-10-01, census joined to the accepted outcomes: run 01 238 checked and
verified by Sonnet plus 151 verified by Sonnet, run 04 389, run 06 362; run 03 and the pilots were Opus
throughout). New writes disclose both models whoever wrote the text (`AI_SYSTEM`), so the two groups now
read differently. Whether a provenance should name every model that checked or verified it is the owner's
call (HUMAN_ONLY); if yes, extend `build_list` to "any Sonnet agent wrote, rewrote, checked or verified"
(a new pinned list and a new lane: this one's list is pinned at 185).

**Undo** (only as a decision; the lane's stamp is single-use, so a second attempt needs a new lane):

```bash
# 1. this lane's ROLLBACK.sql first - before any undo of the WB step that wrote the provenance
ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map -v ON_ERROR_STOP=1" \
  < output/remediation/mechanical_card_disclosure/sNNN/ROLLBACK.sql
# 2. the proof, read-only: the rollback rows are the only deviation card_disclosure.py accept names
#    (it is the record of the undo); teaser.py accept --step N is 0 deviations again, since every
#    provenance cell holds the value its step planned
$PY $MW accept --step N
```

Record the sitting (counts, `StartedAt` not needed: no API restart) in AUDIT_LOG, then
`git add -f output/remediation/mechanical_card_disclosure/LIST.jsonl output/remediation/mechanical_card_disclosure/ACCEPTED
output/remediation/mechanical_card_disclosure/s001 output/remediation/mechanical_card_disclosure/s002` (the
whole trail, never reverted).

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
`teaser-prov-sNNN` and `teaser-card-sNNN`); the per-step acceptance follows the
P5 sitting's rules, minus the card file (database only since D25, 5.5).

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
(`write_gate4.py --group P5`, with `card_json.py` for the file until D25). 761 such cards are
live (measured above). The owner's decisions O2-O4 of 2026-09-26 replace it: every card, those 761
included, is rewritten as a teaser by lane WB. The Phase-4 scope-v3 run writes its descriptions
without cards (`pass: phase4-descriptions-only`, `provenance.card: null`; P5 refuses its sites). The
P5 code stays for the record of the writes it made; its acceptance (`verify_writes4.py --lane p5`)
describes production only until lane WB rewrites a site's card and nulls its Phase-5 key.

## 9. Contract shorts-v1 and the Claude re-check (since 2026-10-09)

The owner's request of 2026-10-08 ("ein teaser für die site, mysterious aber natürlich korrekt ...
dieser kartentext soll dann für Youtube shorts genutzt werden ... ich will dass die viewer mehr über
die site wissen wollen") and decisions D1-D6, D10 and D35 of
`output/remediation/OWNER_DECISIONS_2026-10-08.md` replace parts of sections 1.3, 1.4 and 1.5 for
every card written from now on, and the AUDIT_LOG note of 2026-10-07 ("the cards stay plain factual
prose") with them. **What stays:** the fact basis (1.1), the claim rule (1.2), the length (160-190
characters, D2), the checker (2), the web verification (2.1), the description defects (2.2) and the
write path (5.4-5.6). **What is superseded:** the name rule (D1: the card never names its site), the
one allowed question, the style rules, the AI note's model list (built from the provenance, D6) and
the clear of a failed card (D5: it keeps its card).

The v1 files `teaser/contract.py`, `prompts.py` and `answers.py` are **byte-frozen**: prompts are
pinned by sha256 in every export, so editing them would make runs 01-06, the gap run and the pilots
unimportable - they are also the calibration material. The new contract is a set of sibling modules,
chosen by `RUN.json["contract"]` (`run.contract_of`; a v1 run holds an object there, its limits):

| module | what |
| --- | --- |
| `teaser/shorts_v1.py` | the mechanical rules C3-C16, the seeded defects, `ShortsBasis` |
| `teaser/prompts_shorts.py` | the writer's (three variants), the rewriter's, the hook rater's, the checker's, the web judge's and the adversarial reviewer's questions |
| `teaser/answers_shorts.py` | their answer shapes |
| `teaser/run.py` | the chain by contract (`Spec`): `v1`, `shorts-v1`, `recheck-v1` |
| `teaser/calibrate.py` | the calibration of the roles (9.5) |
| `pipeline/utils/card_provenance.py` | provenance version 3 |

### 9.1 The card (design digest JUDGE, rules C1-C20)

Nameless, two sentences, 160-190 characters; the Short shows the country from its first frame and
reveals "Name, Country." at the end. `shorts_v1.problems_shorts` checks, on the final card:

| rule | check |
| --- | --- |
| C3 | at most 2 numerals and 8 digits, at most 4 digits in sentence 1; no Roman numeral; every numeral grounded as in 1.3 |
| C4 | the v1 mechanical contract (1.3) without its name, sentence-count and question rules; the font on the card alone |
| C5 | exactly two sentences, each ending in a full stop; sentence 1 is 40-85 characters |
| C6 | narration `6.04 + 0.0334 x characters + 0.318 x digits` at most 14.0 s |
| C7 | no form of the stored name, no `unified_site_names` alias (whole phrase; a single common word is exempt), no distinctive word of the name (3+ letters, not a type or function word; a name of generic words only is exempt) |
| C8 | no country name or demonym (`COUNTRY_TERMS`), no administrative word in sentence 1 |
| C9 | sentence 1 opens with no location preposition (unless a number follows), no `Located/It/This/...`, no "A/An/The + site noun" |
| C10 | no question mark, exclamation mark or ellipsis, no `you`, no call to action |
| C11 | a mystery or superlative word only where the description has the same stem |
| C12 | present-state words are a **flag** for the checker, not a refusal |
| C13 | every caption word at most 696 px, a proper noun of the description at most 1,000 px |
| C14 | a Shorts-eligible site (6+ usable images, 300+ description characters): 1-3 anchors, verbatim once, anchor 1 ends in the last 25 characters of sentence 1, later anchors start at character 95+, 28+ apart; any other site: no anchors |
| C15 | the reserve: description sentence ids the card does not use, or `reveal`; `null` means not `shorts_ready` |
| C16 | at import of the rating: no repeated 5-word opening, no 3-word opening in more than 1 % of the run's cards (one is always allowed) |
| C19 | a thin description (under 300 raw characters) may be declined instead of padded: `{"card": null, "thin": true, "reason": ...}`; the code refuses the decline for a longer text |

### 9.2 The stages, the roles and the models (D6)

`write`/`rewrite1`/`rewrite2` (writer: three variants) -> `rate`/`rate1`/`rate2` (hook rater; the
best variant needs a rating of 3, else the round fails) -> `check`/`check1`/`check2` (checker) ->
`verify` (web verifier; its first claim is the card's **identity-bearing** claim, since a nameless card
names no place) -> on a failed verification `rewrite-v` -> `check-v` -> `verify2`. A variant with a
mechanical problem is not rated; a round with no clean variant fails with the problems as findings.

| role | stages | model, effort |
| --- | --- | --- |
| `card_writer` | write, rewrite1, rewrite2, rewrite-v | Opus 5.5 high |
| `hook_rater` | rate, rate1, rate2 | Opus 5.5 medium |
| `fact_checker` | check, check1, check2, check-v | Sonnet 5.5 high |
| `web_verifier` | verify, verify2 | Sonnet 5.5 high |
| `pilot_judge` | judge | Opus 5.5 xhigh |
| `adversarial` | adversarial (re-check run only) | Opus 5.5 high |

The run records the registry's models in `RUN.json["roles"]` at its start. The import refuses an
answer whose `answered_by` is not `<role>:<agent>` of the stage's role, or whose stamp is not that
role's model; `run.py brief` and `run.py agents` name the role, the fixed model id and the effort, and
the recorder's flags (`opus_handoff.py answer --role R --model M`). A failed calibration moves a role
up one tier before its first round (`run.py escalate`). Web agents (verifier, judge, adversary) are
told to read the site's Wikipedia text from `output/remediation/final-2026-10-08/wiki_cache/` first, to
fetch other pages live at most a few requests per site, and that a 403 or 429 is never a finding;
at most 3 run at the same time (Wikimedia throttles this IP from 4).

**The canary.** Every check batch carries one seeded-defect card (`shorts_v1.canary_card`: a removed
hedge, an invented superlative, an implied unknown, a moved period or a word of the name), asked
beside the real questions under a label of its own. A batch whose checker **passes** its canary is void:
`run.py import` is refused with nothing written (`CanaryPassed`), `run.py void-batch` sets that batch's
answers aside (`<handoff>-void/`) and a new agent answers it.

### 9.3 Keep-on-fail (D5)

A site whose chain fails (`failed-after-two-rewrites`, `contradicted-after-verify`,
`unproven-after-verify`, `failed-after-verify-rewrite`) or whose writer declined its thin description
(`thin-declined`) **keeps its card**: its outcome is `status: kept`, `mechanical/teaser.py` lists it as
`kept` and writes no clear row. A site without a description that has a card is `kept` too. At plan
time the name rule runs again against the **live** name, aliases and country (D13 and D23 can change
them after a card was written): a card that gives its site away is listed `name-changed`.

### 9.4 Provenance version 3 (D6)

`v` 3 keeps every key of version 2 and adds `contract: "shorts-v1"`, `models` (the answer stamps of
`write`, `rate`, `check`, `verify`; `rate` is `null` for the one card rewritten after a failed
verification), `hook` (`type`, `rating` 1-5, `variant` 1-3; `null`/`null` for that rewrite), `anchors`,
`reserve` and `shorts_ready` (an eligible site with a reserve and an anchor). `ai_system` is the string
`model4.ai_system_for` derives from `models`; `mechanical/teaser.new_raw_data` refuses any other.
Version 2 stays valid (the 2,830 live cards, still "generated" on the site page). `shorts_pin`, and so
the Shorts gate S13, pins a **version-3 `shorts_ready` card with a fresh description only**; a
version-2 card names its site and is never narrated. The next run of the new contract treats a
version-2 card as a candidate again (`run.current_for`): only a version-3 card of the same contract is
current. The Shorts description's AI note is built from the card's `ai_system`
(`shorts_render.teaser_note`).

### 9.5 The Claude re-check of the 167 MiniMax cards (D10)

`run.py seed-live --run R --provenance-run wb-cardgap-2026-10-07` records every live card of that run
as the seeded `write` stage of a `recheck-v1` run (`model` = MiniMax's stamp: the gap run's every
answer was MiniMax's). `check` (Sonnet, the v1 checker prompt), `verify` (Sonnet, the v1 judge prompt)
and `adversarial` (Opus; it may check the web; the checker's claim map and the verifier's evidence are
in its prompt) follow. A card that passes all three is `confirmed` and stands; any failure clears it
(`card-clear-recheck-<reason>`: `check-failed`, `contradicted`, `unproven`, `adversarial-failed`,
`mechanical`) through the journal, and the replacement comes with shorts-v1.

### 9.6 Calibration (D6; `teaser/calibrate.py`)

Each role is measured against already-judged cases with a threshold **sealed before any answer**
(`THRESHOLDS.json`, its sha256 in `SEAL.jsonl`, bound to the bytes of the prompt modules and the role
registry). Cases come from the Opus-era runs (never a MiniMax answer), the production export and a
file of vetted shorts-v1 cards. A failing role moves up one tier (`tier_move` in `VERDICT-<role>.json`).

| role | set | pass threshold |
| --- | --- | --- |
| `fact_checker` | 45 recorded cards (30 PASS, 15 FAIL) under the v1 prompt | 90 % verdict agreement, 0 PASS of a card with an unsupported claim |
| | 30 recorded FAIL | 27 FAIL again |
| | 30 shorts-v1 cards with one seeded defect | 27 caught |
| | the same 30 cards unflawed | 27 PASS |
| `web_verifier` | 20 recorded proven contradictions | 18 CONTRADICTED |
| | 20 recorded VERIFIED cards | at most 2 falsely CONTRADICTED, 90 % per-claim agreement, 0 false sources (a quote the machine did not find, or a refused page) |
| `hook_rater` | 11 sample openers against 13 live place-word openers | every strong rated above every weak; within one of the `pilot_judge`'s ratings on 80 % |
| `card_writer` | the 40-site pilot | 80 % of first answers mechanically clean |
| `adversarial` | 25 recorded contradictions (the web finding withheld from the evidence) and 25 clean cards | 90 % |

### 9.7 The runbook for one run of shorts-v1

```bash
T=./.venv/Scripts/python.exe scripts/remediation/teaser/run.py
R=output/remediation/teaser/runs/<run>     H=output/remediation/handoff/teaser-<run>
$T select --run $R --contract shorts-v1 --sites SITES.txt [--pilot 40 --seed N]   # read-only
for each stage S in write rate check verify (then rewrite1 rate1 check1 ... while someone is due):
  $T export  --run $R --stage S --handoff $H-S
  $T agents  --run $R --handoff $H-S           # one workflow job per batch: role, model, effort, brief
  #   start one fresh agent per job (agent(brief, {model, effort}), at most max_parallel at once)
  opus_handoff.py validate --dir $H-S
  $T import  --run $R --stage S                # CanaryPassed: void-batch, answer again
$T outcomes --run $R                           # OUTCOMES.jsonl: accepted / kept
$T judge-export --run $R --handoff $H-judge    # the pilot only: a fresh pilot_judge
```

The write steps are 5.4's (`mechanical/teaser.py plan`, `apply.py`, `accept`); journal stamps continue
at `wb-teaser-prov-s035` / `wb-teaser-card-s035`.

## Retired

Never used for this work, and no longer a way to produce card texts:

- the 10-agent generation flow of 2026-03 (batch inputs, parallel agents, merge) and its rule "if
  the wiki excerpt is empty, write a brief factual description based on the site name, type and
  period" - a card is written only from its site's sourced description;
- `scripts/import_card_descriptions.py`, `scripts/merge_rewrites.py` and the `audit_enrich.py`
  Wave-4 merge - none of them journals, and the last two write a card file nobody reads since D25;
- `scripts/verify_descriptions.py` and `scripts/verify_agent.py` as gates: they penalise hedging.
