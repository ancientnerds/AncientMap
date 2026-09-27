# Lane WC: the sentence check of the March descriptions that stay

Owner decision **O5 of 2026-09-26** (`output/remediation/FINISH_PLAN_2026-09-26.md`): "Satzweise
prüfen und kürzen" - every curated description that is still the 2026-03 AI text after the Phase-4
runs is checked sentence by sentence by Opus agents against sources on the web. A supported sentence
stays (still marked as AI text), a contradicted or unsupported one goes, one unsupported clause may
be cut out of an otherwise supported sentence, and a description with nothing left is cleared.

**Every kept text is verified before it is built** (2026-09-27, owner decisions O5 and O2: every
published sentence must be correct). Both pilots of 2026-09-27 failed the sealed judge gate on
single items - a single checking pass lets about one error in 50-60 kept sentences through, and the
gate allows none - so, as in lane WB (`CARD_DESCRIPTIONS.md` 2.1), an independent Opus agent
verifies the kept text of every site (`verify`), a sentence it does not confirm is dropped, and a
text a drop changed is verified once more by a new agent (`verify2`) or cleared (section 2, "The
verification"; section 10).

The code:

| file | what |
| --- | --- |
| `scripts/remediation/phase4/wc4.py` | the deterministic core, pure: the sentences, the trim, the pronoun rule, the verification (`run_verification`, `apply_verification`, `verification_problems`), the composed text and citations, the check record, the raw_data, the invariants, the journal-evidence re-check |
| `scripts/remediation/wc/prompts.py` | the frozen texts: the check question, its re-ask block, the verifier's question, the judge's question, their briefs (byte-pinned in `tests/remediation/test_wc.py`) |
| `scripts/remediation/wc/answers.py` | the strict answer parsers (check, verify, judge), the fetcher (`requests`, User-Agent `AncientMapRemediation/1.0 (research)`), the quote check with the mirror and title rules |
| `scripts/remediation/wc/cli.py` | the commands below |
| `scripts/remediation/phase4/write4.py` group **WC** | the journalled write (`plan_wc`, `load_wc_plan` - which refuses a plan whose sites lack a passed verification -, WC's rules in `validate_rows`, guard 3's clear tests, invariants 5-6) |
| `output/remediation/tools/write_gate4.py --group WC --wc-plan` | the gate: dry, rehearse, apply in steps of at most 100 sites, accept |
| `output/remediation/tools/verify_writes4.py --lane p4wc` | the step's acceptance, from the database and the journal alone |
| `scripts/remediation/phase4/revert4.py --stamp-like 'phase4wc:...'` | the way back |

Tests: `tests/remediation/test_wc.py`, `tests/remediation/test_wc_verify.py` (the verification),
`tests/remediation/test_phase4_wc_write.py`, `tests/api/test_wc_disclosure.py`, the SSR case in
`ancient-nerds-map/src/seo/__tests__/render.test.tsx`; mutation cases `WC_MUTATIONS` and
`WC_VERIFY_MUTATIONS` in `scripts/remediation/phase3/mutation_sweep.py` (run with the label
substring `"wc "`; the verification's alone with `"wc verify"`).

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

**The verification** (`wc4.run_verification`, `wc4.apply_verification`; 2026-09-27). After every
check round is imported and before the build, every site whose check kept a sentence goes to an
independent Opus verifier - a different agent than the checker of that site - in batches of 5
sites (stage `verify`, batches `verify-NNNN`). The question (`prompts.VERIFY_QUESTION`) is the
pilot judge's, applied to the **kept text as it will be published**: the kept sentences in order as
K1..Km with the trims applied, the old sentence each piece was cut from, the checker's verified
quotes, and the dropped sentences as context only (what a kept sentence may have referred to), never
judged. The answer is the judge's shape for the kept sentences (`answers.parse_verify`: each
SUPPORTED, UNSUPPORTED or WRONG - a WRONG with a quote - and `coherent`) plus `broken`: the K
numbers whose reference or meaning broke, ascending, empty when the text is coherent. The import
checks every quote by machine on pages it fetches itself (`answers.check_quotes`, into
`<run>/verify/pages/`) and records the outcome; it does not change a verdict. Per sentence and site:

- SUPPORTED: the sentence stays;
- UNSUPPORTED or WRONG: the sentence is dropped (`verify-unsupported`, `verify-wrong`) - a WRONG
  also when code did not find its quote: a contradiction is never waved through as merely unproven;
- coherent false: every sentence the verifier named in `broken` is dropped (`verify-incoherent`); an
  incoherent text with no sentence named - the verifier could not name the broken reference - is
  cleared (every kept sentence `verify-cleared`);
- then the pronoun rule again: a kept sentence that leans on a sentence the verifier dropped goes.

Dropping never re-adds text. A dropped sentence can break what stays (the Nyons case of pilot 2), so
**a text a drop of `verify` changed and that still keeps a sentence** goes once more to a new agent
(stage `verify2`, batches `verify2-NNNN`), on the text as it now stands: coherent and every sentence
SUPPORTED keeps it; anything else clears the site (`verify-cleared`). There is no third round. A
site ends `verified`, `cleared` or - when its check kept nothing - `nothing-kept`
(`wc4.VerifyStatus`). The import refuses a verifier whose name checked the site (any check round)
or verified it in round 1 (`cmd_verify_import`), and `wc4.verification_problems` refuses such a
record again wherever it is read (section 8 says what that comparison can and cannot see).
`build` is refused while a verification round is due and composes the text from the verified
decisions; a site with nothing left is cleared as before.

**The text** (`wc4.compose`, `wc4.with_markers`): the verified kept sentences in order, joined by
one space, each with one `' [n]'` per distinct page of its verified quotes, ascending, numbered by
first use across the text: in front of the final `. ! ?` (Phase 4's edit 5); after a closing
quotation mark or bracket that follows it (`of the City." [1]`); and for a sentence without final
punctuation (4 of 15,133, all a text's last sentence) the markers and a full stop - the one
character code ever adds. `description_citations` is rebuilt from exactly those pages:
`{n, url, title, domain}`.

**The raw_data** (`wc4.written_raw_data`): the old object without `description_citations`,
`_description_provenance`, `_description_check`; for a kept text the new citations, the check record
and - for a March text (`L`, `march-unmarked`) - lane L's provenance hashing the new text. Every
other key stays as it was. Nothing kept: the description is NULL, none of the three keys remains,
and `raw_data` is NULL when nothing else is left. A site whose `raw_data` was NULL already (12 of the
14 unclaimed texts on 2026-09-26) is cleared by its description row alone: NULL over NULL is no
change, and the plan's rules refused the whole batch for such a row before the fix round.

**The check record** `raw_data._description_check` (`wc4.DescriptionCheck`, v2 since 2026-09-27;
no v1 record was ever written - production held none, read-only, that day): `run`, `checker`
(`model4.AI_SYSTEM`, the Opus handoff's), `checked_sha256` (the stored March text that was asked),
`kept` of `of`, `trimmed`, per sentence `{n, verdict, reason, cites, quote_sha256}` (a reason may be
one of the verification's), `desc_sha256` of the served text, **`verifiers`** (the agents that
verified it, one per verification round, in order) and **`verified_sha256`** (the sha256 of the text
the last verifier confirmed, markers included - held to `desc_sha256` by `wc_problems` and by the
transaction's invariant 5). It is public (`/api/sites/{id}` serves `raw_data` whole), so it carries
each verified quote's sha256 and never its words; the words, URLs, titles, every agent answer, what
the check said of each quote, each sentence's decision before the verification (`checked`) and the
whole verification record (`verification`: status, the sentences the check kept, every round with
its agent, prompt and answer sha256, the verdicts with the quote check's outcome, `coherent`,
`broken`, what it dropped and the text it judged) are in the journal evidence of both rows
(`remediation_change_log.evidence`), from which `verify_writes4 --lane p4wc` re-composes the text
and re-derives the verification.

**The invariants** (`wc4.wc_problems`, asked by the plan, the in-database transaction, the read-back
and the acceptance): a kept text carries its check record whose `desc_sha256` and `verified_sha256`
are the text's; a provenance beside it is lane L's and hashes the text (D4); the citations are
exactly the numbers the markers use, `1..N` by first use, each `{n, url, title, domain}` with the
URL's host (D1); the check record's kept sentences cite those numbers. A cleared site carries none
of the three keys.

**The verification the plan rests on** (`wc4.verification_problems`, asked by `write4.load_wc_plan`
for every outcome - a plan fails whole -, by the plan's rules for every site's rows, by `build`, and
by the acceptance through `evidence_problems`): the record is there; it is exactly what its rounds
give from the check's decisions; the evidence's final decisions are the verified ones; a kept text
is the one the last verifier confirmed and its verification ended `verified`, a cleared site's
`cleared` or `nothing-kept`; no verifier is an agent that checked the site, and none verified it
twice. A plan built before the verify stage has no record and is never written.

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
  **`pages/`** (the import's own page store), `verify/round-<n>/ROUND.json` (the export: handoff,
  batches, the sentences each question showed) and `VERIFIED.jsonl` (the import, per site),
  `verify/pages/` (the pages the verifiers quoted, fetched by code), `FINAL.jsonl` (with each site's
  `verification`), `SUMMARY.json` (with the verification's counts), `WC4.jsonl` (the gate plan),
  `judge/` (the pilot's measurement, with its own `pages/`; `ROUND.json` and `RESULT.json` name the
  judged plan's sha256).
- Handoff: `output/remediation/handoff/wc-<run>-r<round>/<batch>/` (`MANIFEST.jsonl`, the prompts,
  the answers), the agent's page store `<batch>/pages/` (filled by `check-answer`), and its scratch
  `output/remediation/handoff/wc-<run>-r<round>-scratch/<batch>/`; the verification's
  `wc-<run>-verify/` and `wc-<run>-verify2/` (batches `verify-NNNN`, `verify2-NNNN`, scratch
  `<handoff>-scratch/<batch>/`). Batches are independent: one agent per batch, its own scratch and
  page store; a verifier batch is never answered by an agent that answered any other batch of the
  run (the orchestrator's rule; the import refuses a name that checked or verified the site).
- **The import never reads an agent's page store.** It fetches every quoted URL once per run into
  `<run>/pages/`, as the acceptance does (`<run>/judging/pages/`): what counts rests only on pages
  code fetched itself. A page that failed in round 1 stays failed in the re-ask.
- The apply root is the lane's: `output/remediation/logs/_write_apply_p4wc/`; step logs in
  `output/remediation/logs/p4wc/`.

## 4. The runbook

From the main checkout (after `wip/wc` and `wip/wc2` are merged), main venv. `R`, `P` and the
handoffs are the names of this run; numbering continues past every earlier WC plan
(`--first-batch`, section 5).

    PY=C:/PythonProjects/AncientMap/.venv/Scripts/python.exe
    M=output/remediation; RUNS=$M/wc_runner/runs; H=$M/handoff; L=$M/logs/p4wc
    mkdir -p "$RUNS" "$L"      # both are gitignored: a fresh checkout has neither
    C="$PY scripts/remediation/wc/cli.py"; OH="$PY scripts/remediation/opus_handoff.py"
    G="$PY $M/tools/write_gate4.py --group WC"
    # the acceptance names lane WB's provenance stamp as a later lane (section 5): WB writes
    # raw_data._card_provenance into the sites WC made final, and without it that is CHANGED LATER
    V="$PY $M/tools/verify_writes4.py --lane p4wc --allow-stamp wb-teaser-prov-%"

**0. Preconditions.** WA's last P4 step is accepted (the read must see WA's texts). The gates of
section 7 are green on the merged tree. No run built before 2026-09-27's verify stage is written:
its outcomes carry no verification, and the writer refuses them. `$M/logs/_write_apply_p4wc/` holds
no batch of a plan you do not name. Any other later writer of these sites' `raw_data` than lane WB
(a hand edit, a lane not named in `V`) makes the next acceptance report CHANGED LATER: read it,
never widen `--allow-stamp` to pass it.

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
    # the verification: every site whose check kept a sentence, one NEW Opus agent per batch -
    # never an agent that checked (the brief names it opus-wc-verify-000N)
    $C verify-export --run-dir $RUNS/$P --handoff $H/wc-$P-verify   # stage verify, verify-000N
    $C verify-brief  --run-dir $RUNS/$P --handoff $H/wc-$P-verify --batch-id verify-000N
    $OH validate --dir $H/wc-$P-verify
    $C verify-import --run-dir $RUNS/$P --handoff $H/wc-$P-verify   # prints to_verify2
    # only if verify-import reports to_verify2 > 0 (once): the texts a drop changed, new agents
    $C verify-export --run-dir $RUNS/$P --handoff $H/wc-$P-verify2  # stage verify2, verify2-000N
    $C verify-brief  --run-dir $RUNS/$P --handoff $H/wc-$P-verify2 --batch-id verify2-000N
    $OH validate --dir $H/wc-$P-verify2
    $C verify-import --run-dir $RUNS/$P --handoff $H/wc-$P-verify2
    $C build  --run-dir $RUNS/$P --first-batch 4001                 # FINAL, SUMMARY, WC4.jsonl
    $C judge-export --run-dir $RUNS/$P --handoff $H/wc-$P-judge     # the post-verification text
    # per judge batch, one FRESH Opus agent - no checker and no verifier of this run (the brief
    # names it opus-wc-judge-<batch>):
    $C judge-brief  --run-dir $RUNS/$P --handoff $H/wc-$P-judge --batch-id judge-000N
    $OH validate --dir $H/wc-$P-judge
    $C judge-import --run-dir $RUNS/$P --handoff $H/wc-$P-judge     # RESULT.json, JUDGE_EXIT=

A verifier checks each answer's shape with `verify-check-answer` (the brief gives the command;
nothing is fetched, no verdict judged) and records it with `opus_handoff.py answer`. `verify-export`
decides the round by itself: `verify` first, `verify2` only after `verify` is imported and only for
the sites a drop changed; it refuses with "nothing to verify" when no site is due (then build).
`verify-import` imports a round once and refuses a verifier whose name checked or verified the site;
`build` refuses while a round is due. The judge measures the text **after** the verification: the
pilot passes only if the check and the verification together leave no WRONG kept sentence and no
incoherent site.

**The pilot's pass mark** (`cli.J_THRESHOLDS`, sealed with the lane, unchanged by the verification):
no kept sentence the judge shows `WRONG` with a quote code found; at most 5 % of kept sentences
`UNSUPPORTED` (a `WRONG` whose quote was not found counts here); no site whose kept text is
incoherent (a pronoun without its referent, an ungrammatical trim, a trim that changed what the
sentence says); every judged site answered by a fresh agent - since 2026-09-27 one whose name
checked or verified **no** site of the run (it was: none of the site's own check questions).
`DROP_WRONG` (a dropped sentence a source supports) is measured and reported, not gating: a wrong
drop loses text, never publishes a false one. `JUDGE_EXIT=1` stops the lane: fix the cause, re-pin,
and run a new pilot (a new run, a new seed), never a re-judge of the same answers. **The gate
enforces it** (`cli.pilot_approval`): no WC plan is planned unless the first `--wc-plan` is a pilot
run's whose `judge/RESULT.json` says `passed: true`, and every pilot run named passed **on exactly
that plan** (`plan_sha256` in `RESULT.json` is the sha256 of the `WC4.jsonl` its judge judged; a
plan built again afterwards is refused); the gate prints each approving pilot with its RESULT.json
sha256. So the pilot is judged before its own dry run.

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
    $C verify-export --run-dir $RUNS/$R --handoff $H/wc-$R-verify
    #   ... one NEW Opus agent per verify batch (verify-brief), validate, verify-import;
    #   verify-export --handoff $H/wc-$R-verify2 / new agents / validate / verify-import once if
    #   to_verify2 > 0 ...
    $C build  --run-dir $RUNS/$R --first-batch <the last ordinal of every earlier WC plan + 1>

Repeat with `mass-02`, `mass-03`, ... until `export` refuses with "nothing to ask". A chunk has
no judge of its own: the verification is what stands between its check and its write, and the
writer refuses a plan whose sites lack a passed verification (`write4.load_wc_plan`).

**Costs of the verification** (estimates from the pilots of 2026-09-27; measure them on the next
pilot). The population read on 2026-09-27 00:43 UTC holds 2,168 sites (8,342 sentences; WA was still
writing, so a later read holds fewer). In both pilots 18 of 20 sites kept a sentence, so `verify`
asks about 90 % of a chunk's sites - one question per site, 5 per batch: for the whole population
about 1,950 questions in about 390 batches, next to the check round's 2,168 questions in 434. A
verify question carries the kept text only (the pilots: about 3 kept sentences a site, their quotes)
and the verifier researches every kept sentence on the web, so it costs about what a pilot judge
question does - of the order of the ~11k tokens per site measured for Phase 4's Opus sentence audit
(2026-09-24/25). `verify2` asks only the texts a drop changed: the judges'
findings of the two pilots would have sent 1 and 3 of 20 sites (5-15 %, about 100-300 questions for
the population), each a text shorter by the dropped sentence. The verification therefore adds
roughly as much agent time as the check round itself, and no fetch time worth counting: the
verifiers' quotes are fetched once per run and only recorded.

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
| `verify-export` | every check round imported; `verify`: every site whose check kept a sentence, its kept text as published; `verify2`: after `verify` is imported, every text a drop changed that keeps a sentence | a round exported but not imported; a third round; a handoff that is not empty; nothing due ("nothing to verify") |
| `verify-check-answer` (the verifier's aid) | the answer's shape (`answers.parse_verify`) | nothing is recorded; exit 1 while not in shape |
| `verify-import` | the round validates; every prompt rebuilt from the site's state at this round, byte for byte; the answer's shape; every quote checked on the run's own fetch (recorded, not gating: a WRONG drops either way); every site's round read by `wc4.run_verification` before anything is written | a verifier whose name checked the site or verified it in round 1; a changed question; a malformed answer; an unvalidated round; a round imported twice |
| `wc4.trim` (import, `check-answer`, build) | the piece: once, between words, no bare modifier or hedge frame, no qualifier taken off what stays (a telling or doubt of the sentence, a report outside its own figure, a negation's clause), no end of an unpunctuated sentence; the rest: no new sentence problem, the opening and the end asked apart | the answer is not in shape: the sentence is re-asked once, then dropped |
| `build` | every site's decisions, pronoun rule, verification, text, citations, record (verifiers, verified text), raw_data, evidence with the marking and the verification record; `wc_problems` and `evidence_problems` (the AI disclosure the marking requires, the verification) on each | a due or unimported re-ask; a verification round due or exported and not imported; `--first-batch` below 4001; a site never answered |
| `judge-import` | the judge round validates; quotes on the judge's own fetch; independence from every checker and verifier of the run; `RESULT.json` names the judged plan's sha256 | `JUDGE_EXIT=1` below the pass mark |
| gate: the pilot's verdict (`cli.pilot_approval`) | the first `--wc-plan` is a pilot run's, and every pilot named has `judge/RESULT.json` `passed: true` on exactly this plan (`plan_sha256`) | the whole run: nothing is planned |
| gate: the verification (`write4.load_wc_plan`, `wc4.verification_problems`) | every outcome of every named plan carries a verification record that holds (section 2) | the whole run: a plan built before the verify stage, a verifier that checked the site, a record that is not what its rounds give |
| gate dry run | reads each site's live description and raw_data (read-only); plans: a written site is the batch's while its description and WC's three keys are the outcome's (lane WB stamps others) | `written-by-p4` (a P4 text since), `asked-again-later` (a later plan asks it again and this batch did not write it), `moved-since-check` (not written by the batch and not the whole checked pair) - per site, the rest of the batch goes on |
| gate: one site, one batch (`write4.wc_sites_planned_twice`) | no site is planned with rows by two batches | the whole run, before anything is rendered |
| gate plan (`validate_rows`) | site-atomic pairs (kept, clear, raw_data alone for a byte-identical text, the description alone for the clear of a NULL raw_data), one evidence on both rows, the evidence's transition, `wc_problems`, the recorded marking re-derived from the row's old value and the AI disclosure it requires, the verification (`verification_problems`), no key outside the three changes, no full provenance | the whole batch |
| in the transaction | guards 1-4 (curated site, allow-list, real change - NULL only for WC's two clear tests, old value held), invariants 1-2 (new values, journal both ways), 5 (the check record's `desc_sha256` and `verified_sha256` are the description's), 6 (provenance is lane L's and hashes it; a cleared description leaves none of the WC keys) | `RAISE`: nothing is written |
| read-back and inverse proof | every row, the journal, `wc_problems` on the stored pair; `ROLLBACK.sql` rehearsed | `STOPPED.json` |
| `verify_writes4 --lane p4wc --allow-stamp wb-teaser-prov-%` | the chain (a later write by lane WB counted as superseded, any other as CHANGED LATER), `wc_problems` and T08 on every written site, and that the live description, citations, check record and AI disclosure are exactly what the journal evidence of its last WC write composes, after the verification that evidence records (read from either row of the write) | any deviation: the step is not accepted |
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

**After the verification** (2026-09-27, worktree `wip/wc2`, main venv): pytest **8,351 passed**,
119 skipped, 57 deselected (116 skips are gitignored data absent from a worktree, 3 the older opt-in
or retired tests above); ruff check `api/ pipeline/` clean, ruff check and format clean on the 12
touched Python files; lint-imports 2 contracts kept; vulture clean; nothing under `pipeline/` or the
frontend changed (no Lyra import check, no vitest run needed). Mutation sweep: the 30 verification
cases (`"wc verify"`) **30/30 caught**, and the whole WC set (`"wc "`, the 86 earlier cases with the
re-anchored judge case and the 30 new ones) **116/116 caught**, the tree byte-identical after each
run. The verification's tests: `tests/remediation/test_wc_verify.py` (55), plus the gate's refusal,
the pilot plan's tie, the acceptance's re-check and invariant 5 in `test_phase4_wc_write.py`.

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
- **Independence of the verifiers and the pilot's judge is procedural.** `verify-import` compares a
  verifier's `answered_by` with the site's check answers and its round-1 verifier, `judge-import` the
  judge's with every check and verification answer of the run; all are the names the briefs
  prescribe (`opus-check-r<round>-<batch>`, `opus-wc-verify-<n>`, `opus-wc-verify2-<n>`,
  `opus-wc-judge-<batch>`), so the comparison catches a mislabelled or reused agent, not a checker
  that verifies or judges under another batch's name. The orchestrator spawns every verifier and
  judge batch as a new agent that answered no other batch of the lane. The Opus handoff records no
  other identity: `CLAUDE_CODE_SESSION_ID` is visible in an agent's shell, but it is unverified
  whether batch agents of one workflow get distinct ids, and a shared id would mark every judge
  dependent and block every pilot. Independence therefore rests on spawning the judges as their own
  agents with a brief that forbids reading any other batch (the review of 2026-09-26, not changed).
- **A trim's meaning beyond the qualifier rules** (a cut that keeps a grammatical sentence but
  narrows or shifts it otherwise) is the agent's (rule 5), the verifier's (`coherent`, `broken`) and
  the pilot judge's (`coherent`); code refuses the forms it can read (section 2).
- **The verification only drops.** A sentence a verifier wrongly finds UNSUPPORTED is lost (the
  pilot judge measures such losses among the dropped sentences as `DROP_WRONG`, reported and not
  gating); nothing a verifier says is ever added to a text.
- `mass4` digests `scripts/remediation/phase4/*.py`: this lane adds `wc4.py` and changes
  `write4.py` and `sentences.py` (the group pattern `protected_pattern(*groups)`, `PROTECTED`
  unchanged), so it is merged into a tree only when no mass4 run executes from that tree. The
  verification of 2026-09-27 (`wip/wc2`) changes `wc4.py` and `write4.py` again: the same holds.
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

## 10. The verification of 2026-09-27 (worktree `wip/wc2`)

Both pilots of 2026-09-27 failed the sealed judge gate on single items, neither was written:

| pilot | sites | kept | dropped | judge |
| --- | --- | --- | --- | --- |
| `pilot-2026-09-27` | 20 | 59 (39 whole, 20 trimmed) | 17 | 1 WRONG (Cloghanmore: "passage tomb-style" and "the only court tomb with carvings", disputed), 0 unsupported, 0 incoherent |
| `pilot-2026-09-27b` (rule 1 re-pinned, eae4f88) | 20 | 51 | 22 | 1 WRONG ("carved" where the sources say built), 1 incoherent (Nyons: a trim of sentence 1 left sentence 2's "the ancient name" pointing at another referent), 1.96 % unsupported |

A single checking pass lets about one error in 50-60 kept sentences through; the gate allows none.
The same problem in lane WB (every card faithful to its description, 3 of 40 repeating a sentence the
web contradicts) was solved by a web verification of every accepted card (`CARD_DESCRIPTIONS.md`
2.1). Lane WC now does the same per site (section 2, "The verification"): an independent verifier
on the kept text as published, drops only, a second verifier for a text a drop changed, the site
cleared when that one does not confirm it; the record in the journal, the verifiers and the verified
text's sha256 in the check record, the writer refusing a plan without it, and the pilot's fresh judge
measuring the text after the verification against the unchanged thresholds. The next pilot is a new
run with a new seed, built and judged with this stage.
