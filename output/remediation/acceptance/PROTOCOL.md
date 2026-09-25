# Phase 6 acceptance - the protocol, sealed before the draw

Written 2026-09-25, before any acceptance site was drawn and before any acceptance question existed.
The plan (`docs/procedures/SITES_DB_REMEDIATION_2026-09.md`, Phase 6 item 6) asks for "60 freshly
drawn sites (not the pilot set) run through the same two-stage method, with a pass threshold fixed
in advance". This file fixes all of it. Its sha256, the sha256 of the draw's code
(`scripts/remediation/acceptance/draw.py`) and of every input the draw reads are recorded in
`output/remediation/AUDIT_LOG.md` before the draw. **Nothing below changes after the draw; no
threshold is loosened after any verdict is seen.** A change before the draw is a new protocol with
a new seal, recorded as such.

## 1. What is accepted

The database as the public surfaces serve it after the remediation's last write, for the sites the
remediation wrote, measured against the plan's own definition of clean (section 1.3):

- every shipped field is confirmed against at least two independent sources, or empty;
- the description's `[N]` markers and `raw_data.description_citations` agree;
- the card text (the spoken narration) carries no claim the sources contradict;
- the site is in scope (E3), or flagged and hidden;
- the image the page serves depicts this site.

It does not accept: the sites outside the frame (section 2); the retired sites beyond the global
check D6; the gallery beyond the served image (the gallery audit's own calibration admitted no
trigger, AUDIT_LOG 2026-09-25); the `lyra` and `ancient_nerds_community` sources.

## 2. When, and the frame

**When.** Once, after the last remediation write: the Phase-4 mass run, the Phase-5 card texts, the
card_stats wave, and every lane after them. Between the draw and the last verdict, no remediation
write may touch a drawn site. The draw records the journal's high-water mark
(`max(remediation_change_log.id)`); a journal row above it on a drawn site before the result is
written **voids** the run (section 9).

**Frame (the population).** Every `unified_sites` row with `source_id = 'ancient_nerds'` and
`scope_status IS DISTINCT FROM 'retired'` that has at least one forward journal row
(`remediation_change_log.site_id_ref` = the site; `run_stamp` not ending in `-rollback` or
`-probe`) on a judged column: `unified_sites.{name, country, lat, lon, site_type, period_start,
period_name, description, raw_data, source_url, thumbnail_url, scope_status, scope_reason}`,
`card_stats.card_description`, `wiki_images.{is_hero, is_excluded}` - "the written sites of the
remediation" (`draw.FRAME_SQL`, `draw.JUDGED_WRITES`). Read 2026-09-25 13:25 UTC, before the Phase-5
card texts: 3,342 sites; the frame at the draw is larger and is what counts.

## 3. Exclusions

Every frame site named in any of these is excluded - sites that were already examined more closely
than the rest, so that the acceptance measures the ordinary written site:

| label | file | frame sites removed on 2026-09-25 |
|---|---|---|
| assessment-pilot-60 | `output/remediation/acceptance/EXCLUDE_ASSESSMENT_PILOT.txt` (the assessment's 60, from the local `output/audit_inventory/sites_batch_01..12.json`, per-file sha256 in its header) | 38 |
| gold-standard-36 | `output/remediation/gold_standard/sample.json` | 28 |
| phase3-pilot-5 | `output/remediation/phase3_pilot/PILOT.jsonl` | 4 |
| phase4-pilot-1 | `output/remediation/phase4_runner/PILOT.jsonl` | 78 |
| phase4-pilot-2 | `output/remediation/phase4_runner/PILOT2.jsonl` | 74 |
| opus-audit-keep-sample | `output/remediation/acceptance/EXCLUDE_OPUS_KEEP_SAMPLE.txt` (rule 4's 60 keys, mapped to sites through `opus_audit/INPUT.jsonl`) | 60 |
| vlm-pilot | `output/remediation/vlm_pilot/SAMPLE.jsonl` | 155 |
| gallery-c1-sample | `output/remediation/gallery_audit/calibration-2026-09-25-opus/JOBS.jsonl` | 189 |
| sitelink-pilot | `output/remediation/sitelink/pilot/questions.json` | 21 |
| phase4-audit-sample-N | the Phase-4 audit's mid-run samples (10 after every 500 written sites) and its final 60 (`phase4/audit4.py draw`), passed to `draw.py --phase4-audit-samples` - at least one file, or the draw refuses | at the draw |

Union on 2026-09-25: 374 of 3,342. The fixed files are pinned by sha256 over their LF bytes in
`EXCLUSIONS.sha256.json` (checked by `tests/remediation/test_acceptance_draw.py`); the draw records
the sha256 of every file it read, the Phase-4 audit samples included, in `EXCLUDED.json`. A frame
id is removed when its UUID occurs anywhere in a source's text.

## 4. The draw

`scripts/remediation/acceptance/draw.py --out output/remediation/acceptance/draw-<date>
--phase4-audit-samples <files>`, run by the orchestrator, once, into a new directory:

- **Sample:** 60 sites, **seed 20260925**, `phase4.audit4.draw_sample` (`random.Random(20260925)
  .sample` over the sorted, de-duplicated frame ids minus the exclusions). A simple random sample:
  the site error rate it estimates is the frame's, with no weighting. (The assessment's 60 were
  stratified by `rarity_tier` and not weighted; its 53 % is reported beside the result, not
  compared as if it were the same estimator.)
- **Frozen values:** `SAMPLE.jsonl`, read in the same run (`draw.VALUES_SQL`): name, country,
  lat/lon, site_type, period_start/end, period_name, description, its citations and provenance,
  source_url, scope_status/reason, card_description, civilization, and the served image (the
  page's own pick: hero, then lead, then sort order, never an excluded row). The judges are shown
  these values - never a later read.
- **Canaries** (`CANARIES.jsonl`, the answer key; local until the result is written, its sha256 in
  `DRAW.json`): 10 drawn sites, picked with `random.Random(20260926)` from the drawn sites that
  carry a country and a point. Five carry, in their `country` question, the country of the
  undrawn frame site of lowest id that has another country and lies at least 3,000 km away; five
  carry, in their `coordinates` question, their own point moved 5 degrees of latitude (north, or
  south above 80 degrees). Each is wrong by construction, whatever the stored value's quality. A
  canary question replaces that site's real question for the field and looks exactly like every
  other question; the real value of that field is asked in an extra question of the same form.
- `DRAW.json`: seed, frame/excluded/pool sizes, the journal's high-water mark, the sha256 of
  `FRAME.jsonl`, `EXCLUDED.json`, `SAMPLE.jsonl`, `CANARIES.jsonl` and of `draw.py` itself.
  `FRAME.jsonl`, `EXCLUDED.json`, `SAMPLE.jsonl` and `DRAW.json` are committed right after the
  draw, before the first question is exported.

## 5. The fields

Eleven judged fields per site (660 questions, plus the 10 canary questions), each against the
definition the remediation wrote to (`docs/procedures/FIELD_CONTRACT.md`; the finder's field
clauses `scripts/remediation/phase3/discover_stage.FIELD_CLAUSE`; the plan's false-alarm patterns,
section 4.3, 1-11):

| # | field | the served value is right when | wrong, and its severity |
|---|---|---|---|
| F1 | name | a reputable source names this site so (transliterations, official titles such as UNESCO's count) | another site's name: severe; a spelling or diacritic slip: cosmetic |
| F2 | country | the site lies in it; `England`/`Scotland`/`Wales`/`Northern Ireland` and `Türkiye`/`Turkey` are the project's design (pattern 2) | severe |
| F3 | coordinates | the point lies on the site, within 1 km or the source item's own precision, whichever is larger (patterns 9, 10) | more than 5 km off or another place: severe; 1-5 km: moderate |
| F4 | site_type | a canonical type that holds what the sources describe; a coarser source never refutes a finer type (pattern 5) | names a different kind of thing: moderate |
| F5 | period_start | it falls in the bucket of the site's securely attested start; a round value is not an error (patterns 1, 7, 8) | two or more buckets off: severe; one bucket: moderate |
| F6 | period_name | it is the bucket of the site's attested start | moderate |
| F7 | description | every factual claim is supported by a source, and it describes this site | a claim the sources contradict, or another site described: severe |
| F8 | card_description | every claim is supported, and it describes this site (it is read aloud) | a contradicted claim or another site: severe |
| F9 | scope | the site's attested start is within E3 (Americas up to 1500 AD, elsewhere up to 500 AD), or it is a museum that exhibits ancient material, or its `scope_status` is `pending` | shown while outside E3 with no decision: severe |
| F10 | served image | it depicts this site or an object from it | another site or place: severe; not the site but its region or type: moderate |
| F11 | source_url | the page is about this site | moderate |

An empty field is not asked: it is clean by section 1.3 (an empty served image included).

## 6. Stage 1 - one independent judge per field

- Each (site, field) is one question, answered by a fresh Opus agent of the orchestrating session
  through the project's handoff (`scripts/remediation/opus_handoff.py`; model recorded per answer).
  No judge answers two questions of one site.
- **Shown:** the site's identity (name, country, point), the field's served value (the canary value
  where the draw put one), the field's row of section 5, the false-alarm patterns. **Never
  shown:** the journal, any remediation evidence, answer or verdict, the Phase-4 provenance or its
  quotes, another field's question or verdict, `CANARIES.jsonl`.
- The judge researches on its own (web search and fetch; reputable sources; one Wikipedia article
  and its Wikidata item are one source family, not two). Verdict:
  - `CORRECT` - at least two independent sources support the value, each with a verbatim quote
    (for F7/F8: every factual claim quoted from a source, two independent sources across the
    field);
  - `WRONG` - a source contradicts the value (verbatim quote), with the right value and the
    severity class of section 5;
  - `UNVERIFIABLE` - the sources do not decide it.
- **Quote check:** every quote a verdict rests on must be found verbatim (whitespace-normalised) in
  the page it cites, fetched and stored by the run with its sha256 - the Opus re-verification's
  rule (`output/remediation/opus_audit/RULES.md`). A verdict with a quote that is not found does
  not count; the question goes to a new judge, at most twice, then stands `UNVERIFIABLE`.

## 7. Stage 2 - a second judge on every flag

- Every stage-1 `WRONG` (canary questions included - they must look like every other) goes to a
  second, independent Opus judge that sees the claim (field, served value, the proposed value, the
  severity) and the false-alarm patterns - **not** stage 1's sources or reasoning - and researches
  on its own: `CONFIRMED` (with a quoted source, same quote check), `REFUTED` (the served value is
  right, or the claim is one of the false-alarm patterns), or `UNDECIDED`.
- `UNDECIDED` goes to a third judge who sees both reasonings and decides `CONFIRMED` or `REFUTED`.
- **Only a `CONFIRMED` field is an error.** Its severity is stage 1's class unless stage 2 names a
  lower one with a reason; the lower one counts.

## 8. Deterministic checks (no judge)

On the frozen values of the 60 (D1-D5) and on production at the draw (D6):

- D1 every `[N]` marker in the description has an entry in `description_citations`, and every
  entry is cited;
- D2 `period_name` is `pipeline.utils.text.categorize_period(period_start)`;
- D3 `card_stats.civilization` equals `country`;
- D4 where the site carries `_description_provenance`: sha256 of the description equals its
  `desc_sha256`, and where it names a card, sha256 of `card_description` equals `card.text_sha256`
  (`scripts/remediation/phase4/model4.py`, `Provenance`, `LegacyProvenance`);
- D5 `name_normalized` equals Postgres's `left(lower(unaccent(name)), 500)` (Phase 6 item 2);
- D6 no curated site outside the E3 window without a scope decision
  (`mechanical/lane.py` SCOPE_READBACK), and no retired site in `/api/sites/all`.

## 9. The thresholds (fixed now)

**Validity** - all must hold, or the run is **VOID** (neither pass nor fail):

- V1 every question has a counted verdict (section 6's quote check passed, or `UNVERIFIABLE`
  after two re-asks);
- V2 at least 9 of the 10 canaries end `CONFIRMED` after stage 2 - the method sees a planted error;
- V3 no remediation write on a drawn site between the draw and the result (section 2).

**Acceptance** - on a valid run, **PASS** only when all hold, else **FAIL**:

- A1 **0 confirmed severe errors** in the 660 real questions;
- A2 **at most 3 of the 60 sites** (5 %) carry any confirmed error, of any severity, in a real
  question (the canary questions never count here);
- A3 **0 failures** of D1-D6.

**Reported, not gating:** confirmed errors per field and severity; `UNVERIFIABLE` per field and
overall with Clopper-Pearson 95 % intervals (the search route for the 7,761 unverifiable fields is
the plan's open item, HANDOVER section 6); the site error rate with its Clopper-Pearson 95 %
interval beside the assessment's 32 of 60 (53 %, stratified, unweighted); stage 2's refutation
rate; the canaries' stage-1 and stage-2 recall.

## 10. After the result

- **PASS:** recorded in AUDIT_LOG with every verdict file's sha256; Phase 6 is closed.
- **FAIL:** stop. Every confirmed error is a finding with its evidence; its class is root-caused and
  repaired through a journalled lane; then a fresh acceptance on a new draw - `draw.py` sealed
  again with seed 20260926 (its canaries 20260927), excluding this draw's 60 - under these same
  thresholds.
- **VOID:** the method's defect is found and fixed (a canary missed: why; a quote check that cannot
  run: why), then a fresh draw with the next seed as under FAIL. A void run's verdicts are never
  reused.

## 11. Files of the run (`output/remediation/acceptance/draw-<date>/`)

`FRAME.jsonl`, `EXCLUDED.json`, `SAMPLE.jsonl`, `DRAW.json` (committed at the draw),
`CANARIES.jsonl` (committed with the result), the questions and answers of both stages and the
fetched pages' sha256 (the handoff's files), `RESULT.json` (every count of section 9) and a
`RESULT.md` beside it.
