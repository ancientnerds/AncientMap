# Phases 4 and 5: the contracts the four tracks build against (WB-00)

The design is entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json` ("Phases 4
and 5, final design", sha256 `515601c3e91a770ce096ee001e6bfc1659c875d008f11d1b508d07a31d20e5af`).
It is the specification; this file only fixes what the four tracks must agree on so they can be
built in parallel. Where this file and the design differ, the design wins and this file is wrong.

The contract code is `scripts/remediation/phase4/model4.py` (records, vocabularies, word lists,
run-directory file names), `scripts/remediation/phase4/__init__.py` (the import shim) and their
tests `tests/remediation/test_phase4_model.py`. The tracks start from branch `wip/p4-contracts`.

## 1. Rules for every track

1. **`model4.py` belongs to WB-00.** No track edits it. A track that needs a new vocabulary member,
   field or record names the change in its report; the orchestrator lands it on the contracts
   branch before the tracks are merged. The vocabularies (`HoldReason`, `SiteFlag`, `Route`, ...)
   are closed on purpose: a reason that is not in the list is a design question, not a string.
2. **Import like `phase3`.** Modules live in `scripts/remediation/phase4/` and import
   `from phase4 import model4 as M` and `from phase3 import ...`. A module that is also run as a
   script carries the same two lines as every `phase3` module:
   `if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`.
   `import phase4` appends the repository root to `sys.path`, so `pipeline.*` resolves from any
   working directory (tested in a subprocess with `-I`).
3. **Seams are imported, never re-implemented** (design, pipeline): `model_stage.HandoffRunner`
   (the Opus handoff, which replaced `PiRunner` on 2026-09-23 - section 6), `RecordingRunner`,
   `export_calls`, `ModelRunner`, `judge_site`, `ModelCall`, `Prompt`; `fetch_stage.HttpFetcher`, `PacedFetcher`,
   `HostPacer`, `probe_host`, `one_attempt`, `EvidenceStore`, `TRUNCATION_MARKER`;
   `search_stage.MiniMaxSearcher`, `Searcher`, `quota_stop_reason`, `search_slot`;
   `run.assign_batches`, `write_batches`, `read_jsonl`, `Batch`; `write_stage.run_sql`,
   `_json_rows`, `change_key`, `PK_COLUMN`; `mass_run.Spend`, `Budget`, `Progress`,
   `package_digest`, the circuit breaker and spawn retry; `discover_stage.quote_occurs`,
   `normalise_quote`, `claim_problems`; `census.fetch.USER_AGENT`;
   `pipeline.lyra.training_corpus.parse_robots`, `parse_tdmrep`, `reservation_for`,
   `html_reserves_tdm`; `pipeline.lyra.blocked_domains.BLOCKED_DOMAINS`. Never the
   `audit_enrich.py` Wave-4 chain.
4. **No live calls in tests.** No model call, MiniMax, Anthropic, socket or production access in any
   test: a scripted `ModelRunner` or answers the test writes into a handoff directory, a scripted
   fetcher, a recording `SqlRunner`. Fakes refuse what the
   real object refuses. A test that needs gitignored data skips with its reason.
5. **Every guard has a test that goes red without it and a mutation case** in
   `scripts/remediation/phase3/mutation_sweep.py` (phase-4 code and the tools), labelled
   `p4 <module>: <what breaks>`, appended as its own list like `PHASE4_MODEL_MUTATIONS`. Run your
   cases with the label substring and report caught/missed. Note: that file is hashed by
   `mass_run.package_digest` over `phase3/`, so sweep additions land in the same window as the
   other timed `phase3` edits (WB-A1, WB-D1).
6. **Hold, never retry, never move lane.** A site that fails inside its lane is held with a
   `HoldReason` and a non-empty detail. There is no second model call inside a stage; a rerun is
   a new ledgered call.
7. **Streams and exits.** Every tool reconfigures stdout/stderr to UTF-8 and prints its own
   `STAGE_EXIT=`, `WRITE_EXIT=` or `ACCEPT_EXIT=` line; that line is what is read.

## 2. Form, not truth

`model4` refuses **malformed** records and nothing else. It checks: every key present and no
unknown key (`null` where a value is absent); types, with `bool` never accepted as `int`; closed
vocabularies; source ids (`W`, `D`, `T.<lang>`, `R<k>`), sentence ids (`W12`, `T.fr3`) and span ids
(`a1`, kind letter first); offset ranges non-empty, drop ranges sorted and disjoint and inside
their sentence; references (every sentence's `src` is a listed source, every listed source is
cited, source ids unique, card items name existing sentences in ascending order, 1-2 of them); the
fixed pairings lane -> `ai` and lane -> `attribution.changes`; the constants `AI_SYSTEM` (built
from `model_stage.MODEL`, which is `opus_handoff.OPUS_MODEL` - section 6), `LEGACY_AI_SYSTEM`, `LEGACY_BASIS`, version 1, the published licence
CC BY-SA 4.0 and its URL; `attribution.url` is one of the cited sources' URLs; Wikidata (`D`) is
never cited; sentences of one source keep source order without overlap; `PlanSite` digests of
`description` and `card` are their sha256; the selector refusals listed in section 5.

It never checks a record against the world. Hashes against texts, revid against lastrevid, the
permalink form, licences per lane, drops against the offered spans, citation numbering, lengths,
names, dates and everything else V1-V15 names are **verify4's** (WB-C2). Because `model4` already
refuses some shapes a V-rule restates (V1 "it is an integer"), `verify4` reads the raw
`src.<id>.meta` JSON for such checks, so its mutation test can go red, and its mutation tests break
the world (a text, a marker, a hash), not a shape `model4` would refuse first.

## 3. Offsets, spans and ids

- **Offsets** are Python `str` indices (Unicode code points) into the pinned text: the bytes of
  `src.<id>.txt` decoded as UTF-8 (NFC, `\n` line ends). Ranges are half-open `[start, end)`. A
  drop range is in the same space as its sentence, never relative to it.
- **A span's range is exactly the text the prompt shows** after its id: the design's example is
  `a1=", whose tomb lies nearby"`, so the range carries the one adjacent delimiter the edit list
  removes with the span. Edit 1 is therefore "remove the range"; edits 2-5 (collapse double
  spaces, repair `' ,'`, restore the capital after a dropped leading span, insert `' [n]'` before
  the final punctuation) apply after it.
- **Sentence ids** are `<source id><index>`, `index` counting the whole split of the pinned text
  from 1, so an id does not move when the candidate pool is bounded. `section` is the heading, or
  `None` for the lead. Only `W` and `T.<lang>` text is numbered; lane R quotes are located by code.
- **Cards.** A `CARD:` pick's spans are removed on top of its `DESC:` pick's spans.
  `CardItem.drop` is the complete list of ranges removed from the source slice for the card, as
  maximal ranges (a span nested in a dropped span is not listed again), so every range is an
  offered span. `CardItem.sentence` is a 0-based index into `provenance.sentences`.
- **Hashes** are `model4.text_sha256`: sha256 of the UTF-8 bytes, lowercase hex, the form of
  `encode(sha256(convert_to(x, 'UTF8')), 'hex')`.
- **Parity.** `sentences.py` (B2) and `verify4.py` (C2) each implement the span finder and the
  edit list from the design text; neither reads the other's (C2 never opens `assemble.py`, an AST
  test proves `verify4` does not import it). Both implement the rules of section 7 (decision D3,
  2026-09-23), and a parity test runs both finders over the same fixture texts
  (`tests/remediation/p4_span_cases.py`, `SPAN_CASES`: one case per rule and per refusal, with the
  exact spans) and asserts identical span sets. Before the pilot the orchestrator also runs both
  finders over the same pools: any difference is a contract bug, fixed in the design reading, not
  by making one import the other. What both import is data, never a matcher of the other's:
  `model4.PROTECTED_TOKENS`, `model4.CIRCA_PATTERN` and (pilot 2's T5, section 7)
  `model4.PREPOSITIONS_NO_COMMA`. Measured on wip/p4-verify-sup
  (2026-09-23, section 7 with the shared-comma refusal), read-only over the 3,661 local enwiki
  extracts: 170,528 sentences (81,979 of them in a lane-W pool, 144,272 spans offered by S2),
  **0** sentences on which the two finders differ, and every S2 sentence range is one sentence
  of verify4's own split (V2).

## 4. Records and run directory

| Record (`model4`) | Written by | Read by | Where |
|---|---|---|---|
| `PlanSite` | A3 `plan4` | all | `PLAN4.jsonl` (a `phase3.run.Batch` per line, prefix `p4`, sites as `PlanSite` dicts), copied to each batch's `input.json` |
| `SourceDoc` (+ `SubjectGate`, `Tdm`) | A2, A3 | B2, B3, C2 | `evidence/`, feature `src.<id>.meta` (`source_feature(id, "meta")`) |
| pinned text | A2, A3 | B2, B3, C2 | feature `src.<id>.txt`; the raw response is `src.<id>` |
| `LaneAssignment` | A3 `route_stage` | B, D3 | `lanes.jsonl`, exactly one line per site of the batch |
| `Sentence`, `Span` | B2 `sentences` | B2, B3 | Track B's own files |
| `Selection`, `Pick` | B2 `select_stage` | B3 | Track B's own files |
| `Assembly` (+ `Provenance`, `Citation`) | B3 `assemble`, after `review4` | C2, D2 | `assembly.jsonl` |
| `Hold` | every stage | B4, D2, D3 | `holds.jsonl` per batch; B4 aggregates `HOLDS4.jsonl` |
| `Provenance` / `LegacyProvenance` | B3 / D3 | D2, C3, D4 (API) | `raw_data._description_provenance` (`PROVENANCE_KEY`) |

Batch directory: `output/remediation/phase4_runner/runs/<run>/<batch>/` with `input.json`,
`evidence/`, `fetch.json` (the `model_stage.read_fetch_failures` shape), `lanes.jsonl`,
`assembly.jsonl`, `holds.jsonl` (constants `INPUT_FILE`, `EVIDENCE_DIR`, `FETCH_FAILURES_FILE`,
`LANES_FILE`, `ASSEMBLY_FILE`, `HOLDS_FILE`). Cross-track JSONL is written with
`model4.dump_jsonl` and read with `model4.load_jsonl`. Model answers stay write-once under the
stage's own folder (`answers/`, `reviews/`), as in Phase 3.

**The run's ledger is `<run>/LEDGER.jsonl`** (`model4.LEDGER_FILE`, 2026-09-24): every ledger line
of the run's stages - fetches, searches, model calls - goes there, and it is the only ledger a reader
of the run's per-batch lines reads (the writer's journal evidence, `write4.ledger_labels`; the
routes stage's search count, `route_stage.queries_on_record`). `run4` derives it from `--run-dir`,
`mass4` from its run directory (budget and search allowance included), `write_gate4` from `--run`;
none of the three takes a `--ledger`. Why: batch ids repeat across runs - every pilot is `p4-0001`
.. `p4-0009` - and pilots 1 and 2 shared `phase4_runner/LEDGER.jsonl`, so pilot 2's evidence would
have listed pilot 1's calls for the 70 fixed members. That shared file (and `LEDGER.census.jsonl`)
stays as the record of the runs that wrote it; no Phase-4 tool reads it any more.

## 5. What each track owns and must provide

"Owns" is the work breakdown's file list, verbatim in scope. "Provides" are the functions another
track or the driver calls; each track may add private helpers freely. Every batch entry point has
the shape `<name>_batch(batch_dir: Path, *, ledger: Path, <seams as keywords>) -> int`: `0` when
every site of the batch reached an outcome (a hold is an outcome), non-zero when the batch could
not be completed and the run must stop.

### Track A - sources (WB-A1, WB-A2, WB-A3)

Owns `scripts/remediation/phase3/fetch_stage.py` and `tests/remediation/test_phase3_fetch.py`
(timed edit with WB-D1), `phase4/licences.py`, `phase4/sources_stage.py`, `phase4/subject_gate.py`,
`phase4/route_stage.py`, `phase4/plan4.py`, and
`tests/remediation/test_phase4_sources.py`, `test_phase4_routes.py`, `test_phase4_plan.py`.

Provides:

- `fetch_stage.HttpFetcher(..., max_bytes: int = MAX_PAGE_BYTES)` and the same parameter on
  `_read_capped`; 1 MiB only for `*.wikipedia.org` and `wikidata.org`. The default is byte-neutral.
- `licences.LICENCES_VERSION: str`; `licences.licence_of(url: str) -> M.Licence`;
  `licences.deny_family(url: str) -> str | None` (AI aggregator, Wikipedia mirror,
  `BLOCKED_DOMAINS` or this project's own site; `None` = not denied); `licences.is_mirror(page_text:
  str, wiki_text: str) -> bool` (a shared run of 25 or more words).
- `subject_gate.subject_gate(site: M.PlanSite, *, page: Mapping[str, Any], entity: Mapping[str,
  Any] | None, class_labels: Mapping[str, str], shared_qids: frozenset[str], shared_titles:
  frozenset[str]) -> M.SubjectGate` - pure. `entity` is the entity of the page's **own** item
  (`pageprops.wikibase_item`), `None` when the page names none: the site's witness when the page
  names the stored QID, otherwise the page's item, which the caller fetches
  (`sources_stage.fetch_page_item`). Any other entity raises - a class, a place-level item and the
  P625 stand-in are facts about what the page is about, never about the site's item. For a site
  that stores no QID `own` needs place **and** name (the gate's rule 7; `qid_match` stays `false`).
  `subject_gate.fold(name) -> str` is the one name fold of the gate, plan4 and S1b.
- `sources_stage.open_fetcher(*, pacing_dir: Path, timeout: float = 40.0)` - the live fetcher
  (a context manager): the 1 MiB client for the wiki hosts, the 60 KB client for every other host,
  paced per host. The driver passes it to both stages.
- `sources_stage.sources_batch(batch_dir, *, ledger, fetcher, now: datetime, phase3_run: Path,
  sleep=time.sleep) -> int`: writes `src.W*` and `src.D*` through `EvidenceStore`, `fetch.json`,
  `sources.json` (its report and completion mark: each site's status, verdict and the class labels;
  the statuses `rejected`, `missing`, `invalid-title` and `no-title` are routed to S1b) and holds
  `moved-during-fetch`, `revision-too-fresh`, `fetch-failed`, `scope-pending`. `phase3_run` is the
  Phase-3 mass run whose `wikidata_entity` files are reused
  (`output/remediation/phase3_runner/runs/mass`). Returns `phase3.run.STOP_RUN_EXIT` when a wiki
  host did not answer (then nothing is final and a re-run retries).
- **A `revision-too-fresh` hold is final for its batch directory** (S1 and S1b): the answer is
  stored write-once and the report is the completion mark, so a re-run judges the same answer. The
  design's "defers the site to a later batch" is the driver's (Track B, `mass4`): it re-queues the
  sites held `revision-too-fresh` into a new batch directory once 48 h have passed since their
  `retrieved_at` (built 2026-09-23; section 7, "The re-queue"). `sources_stage.fresh_until(detail)`
  reads that time back out of the hold (`article_problem` writes the answer's `curtimestamp`). The
  Track-A review measured on 2026-09-23: 102 of 4,502 articles were younger than 48 h, about 2 % of
  the sites at any moment.
- `route_stage.routes_batch(batch_dir, *, ledger, fetcher, searcher, max_searches: int, now:
  datetime, probe, wait, sleep=time.sleep) -> int`: writes `src.T.*`, `src.R*` (and `src.W`, `src.D`
  for the sites S1b anchors), then `lanes.jsonl` (one `LaneAssignment` per site, lane 0 included),
  `routes.fetch.json`, `search.json`, `routes.json` (its report and completion mark; `queries` and
  `search_requests` count the batch's route searches over every run of the stage, from the run's
  own ledger, section 4)
  and holds `no-source`, `search-stopped` (the budget), `fetch-failed` (a route that could not be
  asked, whenever no own English article was found), `moved-during-fetch` and `revision-too-fresh`
  (an article S1b found). `max_searches` bounds the queries this run may still send. `probe` is
  `minimax_shared.probe_minimax_quota(force=True)`, `wait` paces the MiniMax host
  (`route_stage.open_search` builds the three live seams; `route_stage.no_search` the three of a
  run that may send no search - no MiniMax client, and each seam raises `SearchesOff`, section 8).
  Returns `STOP_RUN_EXIT` when the quota
  gate refused, a stop-class search error arrived, or a wiki host did not answer: then nothing is
  final - no pin, no `lanes.jsonl`, no hold, no `routes.json`; only `routes.fetch.json` and
  `search.json` are written, and a re-run walks the batch again over the searches on disk.
- Every hold detail a Track-A stage writes opens with its tag (`S1: `, `S1b: `), and
  `sources_stage.write_holds(batch_dir, holds, *, tag)` replaces only the lines of that tag.
- `plan4.build_plan(rows: Sequence[Mapping[str, Any]], *, cleared: Mapping[str, set[str]], t03:
  Mapping[str, Mapping[str, str]], gold: Sequence[str], item_names: Mapping[str, Collection[str]])
  -> list[M.PlanSite]` (`t03` is `{site: {text field: worst severity}}`, because `t03-severe`
  waives V9's floor only for a severe finding on the description; `item_names` are the labels and
  aliases of the shared items, for the duplicate pairs) and `plan4.write_plan(path: Path, sites:
  Sequence[M.PlanSite], *, pilot: int) -> None` (order: pilot, cleared defects, T03, the rest;
  batches of 15 through `assign_batches(prefix="p4")`; the first `pilot` sites fill batches of their
  own, section 8). `plan4.main` runs `read` (the one read-only production
  SELECT), `names` and `build`, each printing `STAGE_EXIT=`; `build`'s summary lists the stored
  titles MediaWiki refuses (`invalid_titles`, a control character in `enwiki_title`) for the data
  repair.
- `extract_text_from_html(html: str) -> str` for lane R: the old private function of
  `content_fetch`, moved unchanged to `pipeline/utils/text.py` by the phase-3 search fixes
  (2026-09-23) and re-exported by `content_fetch`; `route_stage` imports it from
  `pipeline.utils.text`.
- `model4.Route.WIKIDATA_ENTITY` (added by Track A): an item refetched through Phase 3's entity
  request at the 1 MiB cap. The design's narrow route carries neither P279 nor the precision of
  P625, which the subject gate reads.

### Track B - selection (WB-B1, WB-B2, WB-B3, WB-B4)

Owns `pipeline/lyra/text_sentences.py` and `tests/pipeline/test_text_sentences.py`,
`phase4/sentences.py`, `phase4/prompts4.py`, `phase4/select_stage.py`, `phase4/assemble.py`,
`phase4/review4.py`, `phase4/translate_stage.py`, `phase4/restricted_stage.py`, `phase4/run4.py`,
`phase4/mass4.py`, `phase4/audit4.py`, and `tests/remediation/test_phase4_sentences.py`,
`test_phase4_select.py`, `test_phase4_assemble.py`, `test_phase4_review.py`,
`test_phase4_lanes.py`, `test_phase4_runner.py`.

Provides (section 7 records the signatures Track B had to change and its span reading):

- `text_sentences.split_sentences` (unchanged signature) protecting `c.`, `ca.`, `r.`, `fl.`, `b.`,
  `d.` before a digit; its 10 importers' tests run unchanged.
- `sentences.split_source(source_id: str, text: str) -> tuple[M.Sentence, ...]` (every sentence of
  the pinned text, spans offered by the rules of section 7 - on `W` sentences only - none
  containing a `M.PROTECTED_TOKENS` entry) and
  `sentences.candidate_pool(sentences: Sequence[M.Sentence], *, lane: M.Lane, names:
  Sequence[str]) -> tuple[M.Sentence, ...]` (lead plus 6 per section, at most 120 sentences or
  24,000 characters; lane S keeps name-bearing sentences only).
- `prompts4`: the frozen `SELECTOR_QUESTION`, `TRANSLATE_QUESTION`, `RESTRICTED_QUESTION`,
  `REVIEWER_QUESTION` and the LLM01 guard line, pinned by a byte-hash test.
- `select_stage.parse_selection(site_id: str, answer: str, pool: Sequence[M.Sentence]) ->
  M.Selection`: raises `M.SelectionRefused` with `UNKNOWN_LINE`, `UNKNOWN_SID` or
  `SPAN_NOT_OFFERED` itself; builds `M.Selection`, which raises the other seven problems.
  `select_stage.select_batch(batch_dir, *, ledger, runner: model_stage.ModelRunner) -> int`.
- `assemble.assemble(site: M.PlanSite, selection: M.Selection, pool: Sequence[M.Sentence],
  lane: M.Lane, sources: Mapping[str, M.SourceDoc], texts: Mapping[str, str], *, run: str) ->
  M.Assembly`; `assemble.assemble_batch(batch_dir) -> int`.
- `review4.review_batch(batch_dir, *, ledger, runner) -> int` (drop-only, fail-closed, answers
  under `reviews/` never bought twice; re-assembles and re-verifies through
  `verify4.verify_site`); `translate_stage.translate_batch(...)` and
  `restricted_stage.restricted_batch(...)` in the same shape.
- `run4`: subcommands `plan|sources|routes|select|translate|assemble|verify|review|writeplan`,
  each printing `STAGE_EXIT=`; `select` (S3, S3R), `translate` (S3T) and `review` (S6) each take
  `--handoff-export DIR` or `--handoff-import DIR` (section 6); `mass4`: the loop, one handoff
  round per live run (`--stages`, `check_round`), `--max-usd 15`, `--max-searches 700`,
  `package_digest(root=<phase4>)`; `audit4.draw_sample(site_ids: Sequence[str], *, seed: int,
  count: int, exclude: set[str]) -> list[str]` and `audit4.audit_sheet(...) -> str`.

### Track C - checking (WB-C1, WB-C2, WB-C3)

Owns `scripts/remediation/census/tests/t03_years_in_text.py`,
`scripts/remediation/census/tests/t08_citation_markers.py`, `pipeline/video/shorts_audit.py`,
`phase4/verify4.py`, `output/remediation/tools/verify_writes4.py`, and
`tests/remediation/test_phase4_verify.py`, `test_phase4_accept.py` (plus the new S13 cases in the
existing shorts tests).

Provides:

- t03: public `mentions` and `claims`; t08: public `marker_sequence` and `entries`; shorts_audit:
  public `widest_word_px` (used by `_widest_caption` too) and the S13 check
  `sha256(card) == provenance.card.text_sha256`. Callers updated in place, no copies.
- `verify4.verify_site(site: M.PlanSite, assembly: M.Assembly, *, metas: Mapping[str,
  Mapping[str, Any]], texts: Mapping[str, str], quotes: Sequence[str], new_raw_data:
  Mapping[str, Any], witness: tuple[Any, bytes | None]) -> tuple[M.Hold, ...]`: empty means
  V1-V15 pass; every hold carries its rule id (`M.HoldReason.V1` ... `V15`). `metas` are the raw
  `src.<id>.meta` objects, `quotes` the quote per published sentence (the store slice in a batch,
  the journal's at acceptance), `witness` the site's `src.D` (raw meta, raw answer bytes, each
  `None` when S1 pinned none; added 2026-09-24, section 7 "Pilot 1's fixes").
  `verify4.verify_batch(batch_dir) -> int`. Never imports `assemble.py`; one mutation case per rule.
- `verify_writes4`: the acceptance CLI (`ACCEPT_EXIT=`), reusing `verify_writes`' journal-chain
  reader and re-running `verify4.verify_site` on production read-back with the journal quotes.

How verify4 reads what the design leaves open (the p4-verify reviews, closed on
wip/p4-verify-sup, 2026-09-23):

- **V2**: a published `W`/`T.<lang>` range `[start, end)` is exactly one sentence of the pinned
  text's split (section 3: each non-heading line through `text_sentences.split_sentences`, each
  stripped piece found again in its line). A range that starts after `According to X, ` is held,
  although no drop names it. Lane R quotes are located by code and not checked this way.
- **V6/V7 names**: `name_in` folds with `subject_gate.fold` (Phase 4's one name fold) and wants
  the name's tokens as a run of whole tokens, each pair at `fuzz.ratio >= 90` (`Ur` is not in
  `during`). V7's lane-S heading counts only with a stored name or alias **inside** the heading,
  the direction S2's pool reads; the heading inside the name (a sibling `Nether Largie South
  Cairn`, a generic `Pyramid`) does not.
- **V8**: a citation's `domain` is its URL's host without a leading `www.` - the production form
  (`api/main.py`'s seeded citations) and what S4's `assemble.domain_of` writes.
- **V10**: lanes T and R build no card; any card there is held (card scope).
- **V14**: a stored country that is no single `NAME_TO_ISO` name is read part by part
  (`Chile, Easter Island` -> CL); one with no code at all agrees with no named country.
- **The acceptance** re-verifies a `p4` site with the run's card only where production's
  `provenance.card` pins one (a card-held site is written with `card: null`). A lane row whose
  field chain holds a row under its change key **and** its run stamp, each plus `-rollback`
  (revert4 `_reversed`), is reverted: not "changed later", not a second write of its row; a
  planned row whose lane rows are all reverted is judged like one not yet written. So write,
  revert and write round 2 is accepted on the round-2 rows.

### Track D - write and ship (WB-D1 ... WB-D5)

Owns `scripts/remediation/phase3/write_stage.py` and `output/remediation/tools/lanes.py` (timed edit
with WB-A1), `phase4/write4.py`, `phase4/revert4.py`, `output/remediation/tools/write_gate4.py`,
`phase4/legacy4.py`, `phase4/card_json.py`, the WB-D4 API and frontend files, the WB-D5 documents,
and `tests/remediation/test_phase4_write.py`, `test_phase4_legacy.py`, `test_phase4_card_json.py`,
`tests/api/test_ai_act_marking.py`, `tests/api/test_sitemap_lastmod.py`, the render and
sourceFields tests.

Provides:

- `write_stage.change_key(..., lane: str = "phase3")`, byte-identical for the default;
  `lanes.py` lanes `p4`, `p4l`, `p5` with stamp families `phase4:`, `phase4l:`, `phase5:`.
- `write4.new_raw_data(old: Mapping[str, Any] | None, assembly: M.Assembly) -> dict[str, Any]`
  (old with `description_citations` replaced and `_description_provenance` added; the driver
  passes it to `verify4.verify_site`); `write4.journal_evidence(...)` (the design's `p_evidence`,
  whose `sentences[i].quote` C3 reads); `write4.plan_writes(...)` and `write4.render_apply(...)`
  (row groups P4, L, P5, guards 1-5, ROLLBACK.sql, pinned digests); `revert4.render_revert(
  stamp_like: str) -> str`; `write_gate4` (dry run by default, `--rehearse`, `--apply --step
  100`, `--accept <verify_writes4 output>`, `WRITE_EXIT=`).
- `legacy4.legacy_provenance(site: M.PlanSite) -> M.LegacyProvenance | None` (`None` when the
  held text equals snapshot d4526691 or the snapshot does not have the site at all: no claim,
  listed for HUMAN_ONLY under its `NoClaim` reason); `card_json` with `--check`, `--prerender`,
  `--regenerate`.

## 6. What WB-00 decided where the design leaves room

- `PlanSite`, `LaneAssignment`, `Hold`, `Citation`, `SubjectGate`, `Tdm`, `SourceRef`,
  `PublishedSentence`, `Card`, `Attribution`, `Pick` and `LegacyProvenance` are records beside the
  nine the work breakdown names, because each crosses a track boundary.
- R's published text is CC BY-SA 4.0 like W/S/T (the curated layer's declared licence);
  `restricted` is only ever a source licence. R's `attribution` names one of its cited pages.
- The span range carries its delimiter (section 3); a card's drops are the full union.
- `HoldReason` spells every hold the design names; `SelectionProblem` spells the parser's refusals
  plus `no-desc`, `no-card`, `abstain-with-other-lines` and `abstain-without-reason`, which the
  design implies (1-8 DESC, 1-2 CARD, ABSTAIN excludes all other lines and carries a reason).

`model4.py` changes made on a track branch, **accepted by the orchestrator 2026-09-23** (decision
D1; rule 1 of section 1 otherwise holds):

- **The protected tokens** (wip/p4-select-sup, the review of WB-B2). `DESIGN_PROTECTED_TOKENS` is
  the design's V4 list verbatim (the old `PROTECTED_TOKENS`, renamed; the design-file test reads
  it). `PROTECTED_TOKEN_ADDITIONS` adds, per group: hedges `presum*`, `apparent*`, `arguabl*`,
  `seem*`, `appear*`, `suppos*`, `reputed*`, `purported*`, `evidently`, `assum*`, `possible`,
  `probable`, `maybe`; negations `cannot`, `*n't`, `*n’t` (every contracted negation, in both
  apostrophes); refutation `unknown`. `PROTECTED_TOKENS` is the design list then the additions,
  per group: what S2 and V4 read. A new entry rule: a **leading** `*` matches any word that ends
  with the rest (`*n't`: don't, can't, oughtn't). Why: the design promises hedges and negations
  survive by construction (card_texts; pilot T3 stops the run on one lost), and with the design
  list alone 990 offered spans of the 3,681 local enwiki pools carried one of these words
  (`Presumably, `, `, arguably,`, `, it seems,`, `don't`, `cannot`); with the additions 0.
- **Pilot 2's additions to the protected tokens** (wip/p4-pilot, 2026-09-24, T3; accepted by the
  orchestrator under D1). Pilot 2's audit found House of the Faun published as "a dancing faun": a
  `p` drop removed "(actually a satyr, since the lower body is that of a man)", the passage's own
  correction of its head noun, and no entry named a correction. `PROTECTED_TOKEN_ADDITIONS` gains
  `contrast`: `actually`, `in fact`, `in reality`, `instead`, `rather` (so `rather than`),
  `whilst`, `nevertheless`, `nonetheless`, `contrary`, `unlike` (`however` and `although` are the
  design's already), and `refutation`: `wrongly`, `mistaken*`, `erroneous*`, `incorrect*`,
  `misidentif*`, `misattribut*` (the pools offered "(sometimes erroneously written Barà)" - Arc de
  Berà, a gold fixture - and "(which he misidentified as biblical Ramah)"). Measured over the census
  run's 4,259 lane-W/S pools (`runs/census-2026-09-24`: 89,072 pool sentences, 86,343 offered
  spans): **472** offered spans carried one of these entries and are offered no more (t 249, l 139,
  a 56, p 28; per entry: rather 117, instead 76, unlike 71, in fact 43, actually 37, nevertheless
  37, whilst 36, nonetheless 11, contrary 10, erroneous* 8, incorrect* 8, mistaken* 7, wrongly 6,
  in reality 3, misidentif* 2, misattribut* 0). `indeed`, `really` and `so-called` were measured
  (24, 4, 63) and left out: emphasis and labelling, not corrections. Both finders read the data, so
  S2 and V4 refuse the same spans (five new `SPAN_CASES`).
- **`PREPOSITIONS_NO_COMMA`** (wip/p4-pilot, 2026-09-24, T5; accepted under D1): the closed list of
  prepositions V5 holds and S2's pool refuses directly before a comma - section 7, "Pilot 2's fixes".
- **`LEDGER_FILE`** (wip/p4-pilot, 2026-09-24): the run's own ledger, section 4.
- **`PERSONAL_PRONOUNS`, `SUBJECT_PRONOUNS`, `ARTICLES`** (wip/p4-pilot, 2026-09-24, pilot 3's T1/T4;
  accepted under D1): the words of the pronoun rule past the first word, which V6, V10 and the
  review's drops read - section 7, "Pilot 3's fixes".
- **`country_lookup.SUBNATIONAL_NAME_TO_ISO`** (not `model4`'s; beside `NAME_TO_ISO`, pilot 3's V14
  false hold): sub-national place names that carry a country's name, each with the ISO code of the
  country it lies in - section 7, "Pilot 3's fixes".
- **The demonym table is not `model4`'s** but `pipeline/utils/country_lookup.ISO_TO_DEMONYMS`, beside
  `NAME_TO_ISO` - the country vocabulary it completes (T4/T6, 2026-09-24, on the orchestrator's
  order). **Decision taken 2026-09-24 (the owner): design entry [6] wins** - its card_texts, RULES:
  "No country name. That is the existing style rule ... Cultural adjectives such as Roman, Egyptian
  or Maya are allowed." `country_lookup` splits the words in two, and V10 and the selector's rule (4)
  read the split (section 7, "Pilot 3's decisions"):
  (a) `ANCIENT_CULTURE_ADJECTIVES`, 74 words, each an ancient culture - the design's three examples,
  the owner's list (Roman, Greek, Egyptian, Maya, Mayan, Inca, Aztec, Olmec, Toltec, Zapotec, Mixtec,
  Moche, Nazca, Etruscan, Celtic, Gallic, Iberian, Phoenician, Punic, Carthaginian, Persian,
  Assyrian, Babylonian, Sumerian, Akkadian, Hittite, Minoan, Mycenaean, Nabataean, Thracian, Dacian,
  Scythian, Norse, Viking, Anglo-Saxon, Pictish, Khmer, Nubian, Kushite, Byzantine, Hellenistic,
  Mesopotamian) and, chosen on the branch, the ancient cultures whose word the table carries
  (Hellenic, Hellene, Macedonian: ancient Greece and Macedon), Roman Britain and Roman Gaul
  (Romano-British, Gallo-Roman), three spellings (Incan, Nasca, Nabatean) and the ancient cultures of
  the catalogue's regions the list does not name (Italic, Samnite, Cycladic, Nuragic, Illyrian,
  Celtiberian, Sarmatian, Phrygian, Lydian, Lycian, Urartian, Achaemenid, Parthian, Sasanian,
  Elamite, Canaanite, Meroitic, Aksumite, Harappan, Chavín, Tiwanaku, Wari, Chimú, Puebloan). A word
  of (a) is never held, even where the same word is a modern demonym, nor its plural or `-man` noun,
  nor a demonym inside it ("British" in "Romano-British"). (b) `MODERN_NATIONALITY_DEMONYMS`:
  derived, every demonym of the table that is no word of (a) - 246 of its 251 distinct demonyms
  (Egyptian, Greek, Hellene, Hellenic and Macedonian go to (a)) - what V10 holds (Danish, Spanish,
  French, Italian, Turkish, Mexican, Peruvian, British, English, Irish, Maltese, ...). This retires
  pilot 2's **safe reading** (any use held, an ancient culture's too: the orchestrator's order after
  pilot 2's T6, from design entry **[0]**'s "no country value, alias or demonym", recorded here as a
  departure from entry [6]). **What it costs:** a table cannot tell a culture from a nationality in
  the same word - Bassae's "the first Greek site to be inscribed on the World Heritage List" means
  Greece and passes V10 again; what such a card says is the reviewer's CARD line's and the audit's
  (T6) to judge. A held card still keeps the site's old card (card scope), never the description.
  Measured with `verify4.card_demonyms`, safe reading -> split: pilot 1's cards held 3 -> 1
  (Al-Mnaykhrat "Greek rock-tomb" and "the Bronze Age and Romano-British period" pass, "Bulgarian"
  stays held), pilot 2's 2 -> 1 (Bassae passes, "a Danish hill" stays held); over the census run's
  4,259 lane-W/S pools, card-length (80-200 characters) sentences with a held demonym 4,912 -> 3,553
  of 58,570 (Greek 1,104, Egyptian 153 and Greeks 100 no more, British 428 -> 322: the 106
  Romano-British), and sites with a clean whole-sentence card candidate (no country, no held demonym,
  no parentheses, no pronoun opener) 3,645 -> 3,656.
- **`CIRCA_PATTERN`** (wip/p4-select-sup, decision D2): the one definition of the card's spoken
  edit; `assemble.spoken` (S4) and V10 import it, and no other phase-4 module compiles a circa
  pattern of its own (the splitter's abbreviation rule in `text_sentences` is not the edit).
  Section 7 states it.
- `Route.WIKIDATA_ENTITY` (Track A, recorded in section 5).
- **The AI-system disclosure names Claude Opus (Anthropic)** (wip/opus-handoff, **accepted by the
  orchestrator 2026-09-23 on the owner's order** "no DeepSeek any more - everything with Opus").
  `AI_SYSTEM` is `f"Claude Opus (Anthropic): {MODEL}, an-sites-remediation-2026-09"` with
  `model_stage.MODEL = opus_handoff.OPUS_MODEL` (`anthropic/claude-opus-5-5 (Claude Code
  agent)`), so the disclosure published with every Phase-4 text (EU AI Act Art. 50) still names
  the model every ledger line of its calls names. `LEGACY_AI_SYSTEM` (the March texts) is
  unchanged. No Phase-4 text had been written when it changed, so no row carries the old one.
  With it the transport changed: every Phase-4 call - selector, translator, restricted lane,
  reviewer - is answered by an Opus agent of the orchestrating session through the handoff
  directory (`scripts/remediation/opus_handoff.py`). `run4 select|translate|review
  --handoff-export DIR` runs the stage itself over a scratch copy of the batch directory with a
  recording runner and hands its exact prompts to DIR; after the answers are validated
  (`opus_handoff.py validate`), `--handoff-import DIR` runs the stage on them through
  `model_stage.HandoffRunner`, which refuses a missing answer, an answer to another prompt or by
  another model, and an empty one - a stop, never a hold. `translate` became its own command,
  because S3T's questions are built from the selector's answers; S3 and S3R are one round.
  Every call still goes through `batch4.buy` and `judge_site`, so the journal evidence write4
  requires (decision D5: the selector's answer by name, the reviewer's, each with its prompt and
  its ledger line) holds for these answers unchanged; a ledger line says `metering: unmetered`
  and carries zero tokens and a cost of 0.

## 7. What Track B built against these contracts (WB-B1 ... WB-B4)

Recorded so Tracks C and D, and the parity check before the pilot, read the same thing. Where it
changes a signature of section 5, the change is the smallest one the code needed.

### Spans: the rules both finders implement (decision D3, 2026-09-23)

S2's finder (`sentences.find_spans`) and V4's own candidate-span finder in `verify4` implement
exactly these rules, each in its own code; `tests/remediation/p4_span_cases.py` (`SPAN_CASES`) is
the fixture both are tested against, one case per rule and per refusal with its exact spans. `s`
is the sentence text (`text[start:end]`), offsets are relative to it until the last step, and
"whitespace tokens" are `s.split()`. Python's Unicode `str` semantics apply (`\w`, `\b`, `\s`,
`str.isdigit`, `str.split`).

1. **Which sentences offer spans.** Only a sentence of an English source (`W`). A `T.<lang>`
   sentence offers none: the protected tokens are English words, so a span of it could carry a
   hedge or negation no entry names (`vermutlich`, `n'est ... pas`) and be dropped before the
   translator saw it; lane T selects whole sentences. Of a `W` sentence, only one whose last
   character is `.`, `!` or `?`, and whose parentheses balance: scanning left to right, depth
   rises at `(` and falls at `)`, never goes below 0 (a `)` before its `(` offers nothing) and
   ends at 0.
2. **Top level** is depth 0; the parentheses themselves and everything inside a group are not top
   level. A **top-level group** is a `(` at depth 0 through its matching `)`.
3. **A delimiter comma** is a top-level `,` whose next character is a space (U+0020), so the
   comma of `4,500` delimits nothing. **A spaced dash** is a top-level en dash (U+2013) or em dash
   (U+2014) at index `i` with `0 < i < len(s) - 1`, a space at `i - 1` and a space at `i + 1`; an
   unspaced dash (`temple—the`) is none.
4. **`p`** for every top-level group `[low, high)`: `[low - 1, high)` when `s[low - 1]` is a space;
   else, when `low == 0` and a space follows the group, `[0, high + 1)`; else `[low, high)`.
5. **`a`, comma pairs.** With the delimiter commas `c_1 < ... < c_n`, pair `k` (`1 <= k < n`) is
   `(c_k, c_{k+1})`; its *inner* is `s[c_k + 1 : c_{k+1}]`, and its *tail* is
   `s[c_{k+1} + 1 : c_{k+2}]`, for the last pair `s[c_n + 1 : len(s) - 1]` (up to, not including,
   the final punctuation). The pairs are judged from the last to the first. A pair is **a list
   link** when
   - (i) its tail, left-stripped, opens with `and` or `or` as a whole word (case-insensitive,
     `(?:and|or)\b` at the start); or
   - (ii) its inner is at most 3 tokens, its tail at most 6 tokens, and the tail carries `and` or
     `or` as a whole word (`\b(?:and|or)\b`, case-insensitive); or
   - (iii) its inner is at most 3 tokens and the next pair (`k + 1`) is a list link; or
   - (iv) its inner is at most 3 tokens, it is the last pair, and its tail is at most 3 tokens; or
   - (v) its inner, left-stripped, opens with `and` or `or` as a whole word (`(?:and|or)\b` at
     the start, case-insensitive): a conjunct, not an insertion.
   A pair whose stripped inner is not empty and that is no list link is an **insertion pair**. An
   insertion pair offers `[c_k, c_{k+1} + 1)` (`", built by Khufu,"`) **unless the pair before it
   (`k - 1`) or the pair after it (`k + 1`) is an insertion pair too**: two insertion pairs that
   share a comma leave no reading of which two commas enclose the insertion, so **neither** is
   offered (decision of the orchestrator, 2026-09-23). Agri Bavnehøj W11: "The old Danish word,
   bavn, in Bavnehøj, means ..." offered `, bavn,` and `, in Bavnehøj,`, and dropping the second
   read "The old Danish word, bavn means ..."; Babylon W1 offered `, within modern-day Hillah,`
   beside `, Iraq,`. The judgement is made here, on rule 5 alone, before rule 9's filter: a
   neighbour refused for a protected token (`, probably bavn,`) still refuses its partner. A
   neighbour that is a list link is no insertion pair and refuses nothing (`The finds, which were
   made in 1900, included pottery, coins, and tools.` offers `, which were made in 1900,`).
   Dropping a list link would join two list items into a false one
   (Bela Palanka W11: "Constantine I Tiberius Claudius Nero"); dropping a conjunct hangs what
   follows it on the item before it (Sparta W58: "inscriptions, sculptures founded by Stamatakis
   in 1872" from ", and other objects collected in the local museum,"). The heuristic also
   refuses some genuine insertions; that stays so (decision D7: safety over coverage; the pilot's
   T8 measures coverage). Rule (v) alone took 2,413 of the 25,408 `a` spans of the 3,661 local
   enwiki pools (2026-09-23). The shared-comma refusal took a further 12,750 of the 22,881 comma
   `a` spans of those pools (55.7 %; 10,131 remain), measured on wip/p4-select-sup 2026-09-23;
   the 114 dash `a` spans and every `p`, `l` and `t` span are unchanged.
6. **`a`, dash pairs.** With the spaced dashes `d_1 < ... < d_m`: none when `m` is odd; otherwise
   the pairs are `(d_1, d_2), (d_3, d_4), ...` in order (never `(d_2, d_3)`). A pair `(d, e)`
   offers `[d - 1, e + 1)` (`" – near the old road –"`) when `s[d + 1 : e - 1]` stripped is not
   empty, **neither dash is a range dash** - the nearest character before it or after it that is
   not whitespace is a digit (`str.isdigit`; whitespace is `str.isspace`, as `str.rstrip()` and
   `str.lstrip()` strip it: U+0020, but also an NBSP or a thin space, so `1200` NBSP ` – ` is a
   range dash too) (`1800 – 500`) - and **no top-level `;` lies between them** (Varna W32:
   `type 1 – long; type 2 –`). A `;` inside a parenthesis between them does not refuse the pair.
7. **`l`**: with a first delimiter comma `c_1`, `[0, c_1 + 2)` when `s[:c_1]` is 1-6 tokens,
   `s[c_1 + 2:]` stripped is not empty (`"In 1900, "`; edit 4 restores the capital), and `c_1`
   separates no list items or conjuncts: **pair 1 is no list link** (rule 5, any of (i)-(v)) and
   **`s[c_1 + 1:]`, left-stripped, does not open with `and` or `or`** (`(?:and|or)\b`,
   case-insensitive; this matters when `c_1` is the only delimiter comma). Before such a comma
   stands a list's head and its first item, and dropping it makes the rest the subject (Babylon
   W204: "Sasanian, and Arabic periods excavated in Babylon demonstrate ..." from "Coins from the
   Parthian, "; Sparta W105: "Strategy, and bronze armour ..."). Decided under D7 (safety over
   coverage) on the independent check of wip/p4-select-sup, 2026-09-23: over the 3,661 local
   enwiki pools it took 1,951 of the 15,261 offered `l` spans (1,746 by the list link, 205 by the
   opening coordinator), some of them genuine leading phrases before a coordinated clause (Babylon
   W161: "Under Nabopolassar, Babylon escaped Assyrian rule, and ..."). **The orchestrator
   confirmed this refusal on 2026-09-23**; it stands as written here.
8. **`t`**: with a last delimiter comma `c_n`, `[c_n, len(s) - 1)` when
   `s[c_n + 1 : len(s) - 1]` stripped is not empty (`", whose tomb lies nearby"`).
9. **Protected tokens.** A candidate whose range text contains an entry of
   `model4.PROTECTED_TOKENS` (every group) is never offered. An entry matches case-insensitively:
   `word*` as `\bword\w*`; `*end` as `\b\w*end\b`; an entry ending in `.` (`c.`, `ca.`) as `\bc\.`
   with no boundary after the stop; any other entry as its words joined by `\s+`, between `\b`
   and `\b`.
10. **Ids.** The candidates are collected in the order `p`, `a` (commas), `a` (dashes), `l`, `t`;
    a range already taken is not offered again under a second kind. The kept ranges are sorted
    by `(start, end)` and numbered per kind from 1 (`p1`, `a1`, `a2`, `l1`, `t1`); the offsets are
    then made absolute (`+ start`).

The pair is the insertion's delimiter: `A, X, B` becomes `A B`, never `A, B` (a departure from a
literal "exactly one adjacent delimiter", which would leave `Khufu, built it` after an appositive).
Kinds may overlap (an `a` and the `t` after it share a comma): `select_stage.parse_selection`
refuses a pick whose chosen spans overlap without one holding the other (`span-not-offered`: no
offered span is their union), for a CARD pick together with its DESC pick's spans. A nested span is
dropped with its outer one, and `drop` lists maximal ranges only; ranges that merely touch stay two
ranges.

### The edit list and the spoken edit

Edits 2-4 apply to the whole trimmed slice (collapse runs of spaces, `' ,'` -> `','`, uppercase the
first character when the first drop starts at the sentence start); edit 5 is `' [n]'` before the
last character. A lane-T sentence is shown to the translator whole, with edits 2-3
(`translate_stage.shown_sentences`); its published text is the translation with edit 5.

**The card's spoken edit is `model4.CIRCA_PATTERN`** (decision D2, the one definition; S4 and V10
import it):

    (?<![\w.])(?P<c>[Cc])a?\.\s*(?=\d|(?:AD|BC|BCE|CE)\s*\d)

that is, `c.` or `ca.` (either with a capital `C`) not right after a word character or a full stop
(`B.c.`, `Africa.` are no circa), followed by any whitespace or none (`{{circa}}` renders `c.` and
a thin space, U+2009; an NBSP is whitespace too; `ca.300`), in front of a digit or of an era-first
date (`c. AD 79`, `ca. BC 500`; the era word in upper case). A `c.` no number follows is no circa
(`5th c. BCE`, where c. is a century). **Every match is replaced by `circa `, or `Circa ` when group
`c` is a capital `C`** (the letter, the optional `a`, the stop and the whitespace after it go).
Card items are joined with one space.

### The pool

The pool offers only complete sentences (`is_complete_sentence`) of 25-400 characters that end in
`.`, `!` or `?`, outside the sections `see also, references, notes, footnotes, citations, sources,
bibliography, further reading, external links, gallery, literature, works cited, notes and
references, references and notes, explanatory notes, in popular culture, popular culture` and the
same apparatus in the languages lane T reads (`sentences.FOREIGN_EXCLUDED_SECTIONS`: de, fr, es,
it, pt, tr, ca, e.g. `einzelnachweise`, `références`, `referencias`, `note`, `kaynakça`)
(case-insensitive, a subsection by its own title). Lane S filters by name before the
6-per-section count. Names match as whole words after Phase 4's one name fold,
`subject_gate.fold` (accents stripped, lower case, every non-alphanumeric character a space), the
fold the subject gate accepted the article by: `Chichén-Itzá` is found in `Chichen Itza`, `St.
Kilda` in `St Kilda`.

### Signatures changed from section 5

- `sentences.candidate_pool(sentences, *, lane, names, text)`: lane S cannot find a name without
  the pinned text.
- `assemble.assemble(..., run, translations=None)`: lane T passes `sid -> English sentence`.
  Lane R is `assemble.build_restated(site, restatements, sources, *, run)`; `build_picks` builds
  from DESC and 0-2 CARD picks (0 after a review drop). `assemble.quotes_of(assembly, texts)` is
  the `quotes` argument of `verify4.verify_site` in a batch.
- `review4.review_batch(batch_dir, *, ledger, runner, reverify)`: `reverify(site, assembly) ->
  tuple[Hold, ...]` is the seam; `run4` builds it from `verify4.verify_site` with the raw metas, the
  pinned texts, `quotes_of` and `write4.new_raw_data(site.raw_data, assembly)`, so Track B never
  imports Track C or D at module level.
- `run4` adds `prepare` (the plan line to `input.json`, write-once, after `run4.plan_line_sites`
  read every site of it: a line without a non-empty `sites` list is refused before anything is
  written) and `holds` (`HOLDS4.jsonl`); `select` runs S3, S3T and S3R in that order. `plan` and
  `writeplan` forward their arguments to `plan4.main(argv: list[str]) -> int` and
  `write4.main(argv: list[str]) -> int`, which Tracks A and D provide (each prints its own
  report). `sources` and `routes` run inside Track A's `sources_stage.open_fetcher` (the one live
  fetcher: 1 MiB for the wiki hosts, 60 KB for every other, paced per host) and pass Track A's
  keywords: `sources_batch(..., phase3_run=--phase3-run)` (default the Phase-3 mass run,
  `phase3.run.DEFAULT_SOURCE_RUN_DIR`), and `routes_batch(..., max_searches=<the run's remaining
  allowance>, probe=, wait=)` from `route_stage.open_search` - or, when that allowance is 0, from
  `route_stage.no_search` (section 8).
- `batch4.read_batch` is Track A's `sources_stage.read_batch` (on `phase3.run._single_batch`), the
  one reader of `input.json`; `batch4.sha256_file` is `phase3.run._sha256`, and prompt and answer
  digests are `model4.text_sha256`.
- `audit4 draw` takes `--written` (the ids written to the database: the journal's, or
  `verify_writes4`'s read-back) and draws only from them; every written id must be a site a
  finished review kept (`audit4.reviewed_sites`: batches `mass4.batch_done` counts as done, minus
  site-held sites, a hold appended after the review included).
- A batch function's non-zero return stops the whole run (`mass4` reads `STAGE_EXIT=`); a stage
  that prints no exit line fails its batch and counts for the circuit breaker. The routes stages of
  parallel batches take turns (`Phase4StageRunner.search_turn`), so the allowances handed out never
  add up to more than `--max-searches`.

### The re-queue (design S1: "A revision younger than 48 h defers the site to a later batch")

A site's **latest batch** is the last line of `PLAN4.jsonl`, then of the run directory's
`REQUEUE4.jsonl`, that lists it. When its latest batch holds it `revision-too-fresh` at site
scope, `mass4` re-queues it once `sources_stage.fresh_until(hold.detail)` has passed (48 h after
the answer's `curtimestamp`, which S1's and S1b's detail both name): each live invocation appends
the ready sites to `REQUEUE4.jsonl` in new batches - PLAN4's line shape, 15 sites each
(`plan4.BATCH_SIZE`), ids `p4-NNNN` numbered after the last ordinal of the plan and of every earlier
re-queue - and runs them after the plan's batches; `run4 prepare --plan <run>/REQUEUE4.jsonl`
copies such a line into a new batch directory. A dry run writes nothing and says how many sites are
ready and how many wait (and until when). `mass4.read_requeue` refuses a line that is not the new
batch of its ordinal, carries a site the plan does not, or carries a site twice. A re-queued site
lives in two batch directories: **its latest batch is its state** - `run4.aggregate_holds` keeps
only the holds of each site's latest batch, so the hold it left behind no longer keeps it
unwritten. A reader of the per-batch `holds.jsonl` files (Track D's writer, verify_writes4) must
apply the same rule, or read `HOLDS4.jsonl`.

### Track B's files in a batch directory

`pools.jsonl`, `selection.jsonl` (`Selection`), `translations.jsonl`, `restatements.jsonl`, and
`prompts/`, `answers/`, `reviews/` (write-once, `EvidenceStore`); each LLM stage writes its file
even when empty, and an absent one means the stage never ran. Reports: `select.json`,
`translate.json`, `restricted.json` (per site: `label`, `prompt_sha256`, `answer_sha256`,
`cost_usd`, `outcome`) and `review4.json` (per site: the reviewer's `lines`, `kept`, `followed` -
the sentences dropped with a dropped predecessor they lean on, since pilot 3 - `card`, and at the
top `assembly_sha256`). `assembly.jsonl` is written by `assemble` and rewritten by `review`
with exactly the sites that passed; it counts as reviewed only when `review4.json` has
`error: null` and its `assembly_sha256` is the file's (the design's "the reviewer answered").

### Holds Track B writes, and one open vocabulary request

- `no-source` also for a lane-W/S/T site whose pool is empty (lane S with no name-bearing
  sentence), before any call.
- `card-too-short-after-review` (card scope) also when the reviewer drops the card or writes no
  CARD line.
- **Open, for WB-00:** lanes T and R build no card (their text is not the source's, so no offered
  span applies) and write no hold for it, because no `HoldReason` fits. `Assembly.card is None` is
  the signal meanwhile; a card-scope reason such as `card-not-extractive` would let the writer
  treat a T/R site's cleared-defect card like any held card (P5/card-clear). verify4's V10 holds
  any card an assembly of lane T or R does carry (card scope, 2026-09-23), so an assembler bug
  cannot publish French or restricted wording as a card.
- **`PlanSite.in_snapshot` - accepted by the orchestrator 2026-09-23 (decision D4, Track D
  supplement).** A boolean: snapshot d4526691 has a row for the site (`plan4.PLAN_SQL` asks with
  `EXISTS` on `snapshot_rows`). `snapshot_description` is `null` both for a site the snapshot does
  not have and for one it holds without a description; only the second can carry the design's
  basis "description differs from pre-March snapshot d4526691", so lane L (`legacy4`) makes no
  claim for a site absent from the snapshot and lists it under the closed `NoClaim` reason
  `not-in-snapshot` (8 curated sites were created after 2026-03-04, 7 of them on 2026-04-24).
  `model4` refuses a snapshot text for a site not in the snapshot. Every producer and fixture of
  `PlanSite` carries the key; Track B's `tests/remediation/p4_fixtures.py` and Track C's
  `tests/remediation/phase4_cases.py` need the one line on their merge.
- **The model-call features - accepted by the orchestrator 2026-09-23 (decision D5, Track D
  supplement).** `SELECT_FEATURE` (`select`), `TRANSLATE_FEATURE` (`translate`),
  `RESTRICTED_FEATURE` (`restricted`), `REVIEW_FEATURE` (`review`) and `LANE_ANSWERS`: the calls a
  written site of each lane answered under `answers/` (W and S: select; T: select and translate;
  R: restricted - lane R selects nothing). A call's feature names its answer file, its prompt file
  and its ledger label (`<site_id>/<feature>`). These are the names Track B's `batch4` stores
  under (`SELECT_FIELD` ... `REVIEW_FIELD` on `wip/p4-select`); on that merge `batch4` takes them
  from `model4`, so there is one spelling.

### Pilot 1's fixes (2026-09-24): the two questions and V6's names

Pilot 1 (`output/remediation/phase4_runner/PILOT_RESULT_1.md`, run `pilot-2026-09-24`) failed T2
(Orolik: the selector picked the lead sentence about the modern village, its municipality and
county, and the reviewer kept it), T5 (4 of 319 sentences with a dangling definite reference:
Condorcaga "the mountain", Kit Hill "Other notable artifacts", Peppercombe Castle "the valley",
Ocriticum "the via glareata") and T8 (52 of 77 lane-W sites write-eligible; V6 held 15, V9 8).
Under the thresholds' failure rule the causes were fixed before pilot 2; no threshold changed.

**The selector question** (`prompts4.SELECTOR_QUESTION`, sha256 `8969add9...baad046`, was
`a9dad5c0...439498e28`) keeps the design's rules (1)-(5) verbatim and adds, before the answer lines:

    (6) the description is your DESC sentences after their removals, joined by spaces: it must be 200-1100 characters long in total;
    (7) your first DESC sentence must name the site: its name, an alias or an also_named name of the site element;
    (8) never pick a sentence about the modern village, town or municipality (its administration, its population, its modern founding), even when it names the site; if the only sentence that names the site is such a sentence, answer ABSTAIN with that reason;
    (9) every picked sentence must be understandable from your picked sentences alone: never pick a sentence with a definite reference ("the valley", "the mountain", "other ...", "it") whose antecedent is not among your picks.

(6) is V9's bound, which the selector was never told (8 lane-W V9 holds). (7) is V6's first-sentence
rule, which (8)'s ABSTAIN presupposes. **The reviewer question** (`REVIEWER_QUESTION`, sha256
`529c9678...461d0cb3`, was `8d2362a9...2c4399`) adds after "Ask the same of the card, against the
description.":

    DROP a sentence about the modern village, town or municipality (its administration, its population, its modern founding) rather than the site, even when it names the site.
    DROP a sentence with a definite reference ("the valley", "the mountain", "other ...", "it") whose antecedent is in no published sentence before it: the source sentences before it are not published.

The answer lines (`DESC:`/`CARD:`/`ABSTAIN:`, `R<i>: KEEP|DROP <why>`, `CARD: KEEP|DROP <why>`) and
both parsers are unchanged; the byte pins in `test_phase4_select.py` were re-pinned with the reason.

**V6's names** (design: "The article title and Wikidata labels count only for a strong 'own'
verdict (QID + coordinates + not place-level)"). Sentence 1 must name the site by the stored name or
a `unified_site_names` alias; for a strong 'own' verdict of sentence 1's source (verdict `own`,
`qid_match`, a known `km`, no `place_item`) also by the pinned article's title and by the **English
label of the site's pinned Wikidata item** (`src.D`). The title already counted; the label is new:
until now `verify_site` never saw the item and read "Wikidata labels" as the title alone. The label
counts only as S1 pinned it: the meta is `src.D`'s, the stored answer hashes to its `sha256_raw`,
and the answer carries the stored QID. Fold and token rules are unchanged (`name_in`). **This is
not a loosening of identity:** a strong 'own' verdict means the subject gate already verified
article <-> site (the page's item is the stored QID, the article lies within `max(5 km, P625
precision)`, the item is no concept and no place-level item), so the title and the label are
names of the verified site; a place-level item (a town's article, 'Clare', 'Enns (town)') still
adds no name - that is the T2 trap. Re-measured on a scratch copy of pilot 1's run (its stored
selections re-assembled and re-verified, 2026-09-24): the V6 name holds fall from 14 to 9 - 'Beacon
Hill, Burghclere, Hampshire' (label 'Beacon Hill'), 'Justinianopolis (Epirus)', 'Altar Stone -
Stonehenge', 'Pant-y-Saer Burial Chamber' and 'Windmill Hill, Avebury' pass; the 4 place-level
items (City of Enns, Argos, Clare, Ai-Khanoum) and the 5 sites whose first pick carries none of
the names (Odeon, Čertova pec, Partiscum, Temple of Dakka, Orbe-Boscéaz) stay held - rule (7)
now asks the selector for that first name.

- `verify_site(..., witness)` (section 5): `verify4.read_witness(store, site_id)` reads it in S5
  (`verify_batch`), the review's S5 (`run4.reverify_for`) and the acceptance (`verify_writes4`);
  `write4.witness_files` in the P4 plan. `verify4.v6_names` and `verify4.witness_label` are public;
  a failed V6 names every name it tried and, for a strong 'own' verdict, why the witness added none.
- **The same rule on S3's side, in its own code** (the D3 idea): `select_stage.v6_names` reads the
  source's `SubjectGate` record and `src.D` through `batch4`, and the selector's site element shows
  the names beyond the stored ones as `also_named` (`select_stage.also_named`, by Phase 4's one name
  fold) - rule (7)'s names. `run4 select`'s preview measures that exact prompt
  (`select_stage.site_selector_prompt`). Neither module imports the other; the parity test
  `test_s3_and_v6_accept_the_same_names` runs both over the same store (strong, no distance, QID
  mismatch, place item, shared, no witness, another item, unpinned, no English label, a meta filed
  under another id) and asserts the same names. The lane-S pool filter (`candidate_pool`'s `names`)
  stays the stored names only: it mirrors V7, not V6, and lane S's verdict is `shared`, never a
  strong 'own'.

### Pilot 2's fixes (2026-09-24): a correction, the demonyms, two garbles, the name's base

Pilot 2 (`output/remediation/phase4_runner/PILOT_RESULT_2.md`, run `pilot2-2026-09-24`) passed T1, T2,
T5 and T7 and failed T3 (House of the Faun: a `p` drop removed the passage's own correction "actually
a satyr"), T4 and T6 (V10 let "a Danish hill" and "the first Greek site" through: no demonym table)
and T8 (52 of 78 lane-W sites write-eligible); its T5 pass still named three rule gaps (Bassae,
Vindobala, Bejsebakke). Under the thresholds' failure rule the causes were fixed before pilot 3; no
threshold changed. Each fix keeps D3: the selection side and verify4 implement the rule each in its
own code, and a parity test runs both over shared fixtures.

- **T3, the protected tokens** - section 6 (`contrast` and `refutation` additions, 472 offered spans
  fewer over the census pools); both finders read the data, five new `SPAN_CASES` hold them together.
- **T4/T6, V10's demonyms** (narrowed before pilot 3's first answer: "Pilot 3's decisions" below) -
  `verify4.card_demonyms` matches `country_lookup.ISO_TO_DEMONYMS`
  (section 6; 199 country codes, 251 distinct demonyms) as whole words written as proper nouns, alone or
  with a plural `s` or a `-man`/`-men`/`-woman`/`-women` noun ("Greeks", "Englishman"), and V10 holds
  the card ("the card names a nationality: [...]", card scope). The selection side is the selector
  question: rule (4) now reads

      (4) CARD: pick 1-2 of your DESC sentences whose remaining text is 80-200 characters, names no country and no nationality adjective such as Greek or Danish, has no parentheses, does not open with a pronoun, and states something concrete; prefer one that carries a date;

  (`SELECTOR_QUESTION` sha256 `ce36085f...afb79c`, was `8969add9...baad046`; a test ties "Greek" and
  "Danish" to the table). Measured: 3 of pilot 1's 47 cards and 2 of pilot 2's 49 carry a demonym;
  over the census pools 4,924 of 58,622 sentences of card length (80-200 characters) do, and the
  sites with at least one whole-sentence card candidate without a country, a demonym, parentheses or
  a pronoun opener fall from 3,680 to 3,646 of 4,259.
- **T5, two garbles V5 holds and S2 never offers.** `verify4.ill_formed` (V5) and
  `sentences.garbled` (S2's `publishable`, so the pool) each implement: (a) a full stop, then
  whitespace, then a lowercase word inside the sentence - unless the word the stop ends is a single
  letter or carries a full stop of its own (an initialism: `B.C. and`, `i.e. the`, `a.m. and`,
  `F. da Silva`), since that stop ends no sentence; the shared splitter never splits before a
  lowercase word, so Bassae's source typo "Cotylion Mountain. near the village" reached the pool
  whole; (b) a word of `model4.PREPOSITIONS_NO_COMMA` (`of at by for from into onto to upon with than
  until during towards toward among amongst amid via`: the prepositions that stand as no adverb or
  particle) in lower case, as a whole word, directly before a comma (Vindobala: "the hamlet of,
  Rudchester"). A preposition stranded in a coordination ("1 km west of, and within sight of, the
  town") is fine English and is refused too (D7). Measured over the census pools: (a) 186 and (b) 66
  of the 89,072 pool sentences (156 and 65 sites; 251 sentences together) are offered no more; (a)
  without the initialism exemption would have been 431, mostly `B.C.`, `i.e.`, `A.D.`.
  `tests/remediation/p4_garble_cases.py` (27 cases) is the shared fixture. Bejsebakke's garble
  ("This excavation was found among other traces more than 350 pit houses") has no deterministic
  shape; **the reviewer question** gains, after the dangling-reference criterion:

      DROP a sentence that is garbled or ungrammatical, even when it copies the source word for word.

  (`REVIEWER_QUESTION` sha256 `59a1714e...a7d999`, was `529c9678...461d0cb3`.) The answer lines and
  both parsers are unchanged; the pins in `test_phase4_select.py` were re-pinned with the reasons.
- **T8, the stored name's base.** For a strong 'own' verdict of sentence 1's source (the same
  condition as the title and the item label), V6 also accepts the stored name without its
  disambiguator: `X (Y)` -> X when the name ends in one flat parenthetical group, else `X, Y` -> X
  (the text before the first comma). Fold and token rules are unchanged (`name_in`); under any other
  verdict nothing is added - "Clare, Suffolk", "Argos, Peloponnese" and "Marion, Cyprus" (place-level
  or unverified articles) stay held, the Orolik/Clare trap. `verify4.name_base` and
  `select_stage.name_base` each implement it; S3 shows the base as `also_named` (rule (7) already
  names those); the parity test `test_s3_and_v6_accept_the_same_base_name` runs both over 12 names x
  the 10 gate and witness cases of `NAME_PARITY_CASES`. **Measured on a scratch copy of pilot 2's run**
  (its stored selections re-assembled and re-verified with this code): V6 holds fall from **16 to 14**
  - Partiscum (Castra) and Al Thumamah, Riyadh pass; 9 of the 14 left are pronoun-adjacency holds, 5
  name holds (Odeon Theatre and Ancient City of Perrin carry no disambiguator; the three traps above).
  The same re-verification now holds every pilot-2 audit finding but Bejsebakke's deterministically:
  House of the Faun (V4, `actually`), Arc de Berà (V4, `erroneous*`), Bassae and Vindobala (V5), and
  the Danish, Greek, Australian and British cards (V10).

### Pilot 3's decisions (2026-09-24, before its first answer): cultural adjectives, V6's pronoun rule

Two owner decisions, taken after pilot 3's select export (87 questions, `ce36085f...`) and before any
of them was answered; the questions were re-exported with the new selector question (section 8,
AUDIT_LOG). No threshold changed, no model was asked.

- **Decision 1 - design entry [6] wins** (section 6: `country_lookup`'s split into
  `ANCIENT_CULTURE_ADJECTIVES` and `MODERN_NATIONALITY_DEMONYMS`). `verify4.card_demonyms` (V10)
  matches (b) only - a whole word written as a proper noun, alone or with a plural `s` or a
  `-man`/`-men`/`-woman`/`-women` noun - and drops a match that lies inside a match of (a), so
  "Romano-British" passes and "a Romano-British villa in the British countryside" is held for the
  second "British". The selection side is the selector question: rule (4) now reads

      (4) CARD: pick 1-2 of your DESC sentences whose remaining text is 80-200 characters, names no country and no modern nationality adjective such as Danish or Spanish, has no parentheses, does not open with a pronoun, and states something concrete; cultural adjectives such as Roman, Egyptian or Maya are fine; prefer one that carries a date;

  A test ties its examples to the data V10 reads: Danish and Spanish are in (b); Roman, Egyptian and
  Maya are in (a) and not in (b).
- **Decision 2 - V6's positional pronoun rule is stated to the selector as rule (10).** V6 holds a
  published sentence that opens with a word of its closed list (`model4.PRONOUN_OPENERS`: It, Its,
  This, These, They, Their, He, She, His, Her, The latter, The former, Here, There), read after the
  edits - so a removed leading phrase can expose one - unless the sentence published right before it
  is its source predecessor (the same source, nothing but whitespace between the two); sentence 1
  therefore never opens with one, and no card item does (V10). Rule (9) only asks for an antecedent
  among the picks, and 9 of pilot 2's 14 re-verified V6 holds broke this rule. The selector question
  adds, after (9) and before the answer lines:

      (10) a DESC sentence may open with It, Its, This, These, They, Their, He, She, His, Her, The latter, The former, Here or There (after its removals) only if the sentence numbered one lower, in the same section, is also one of your DESC sentences; so your first DESC sentence never opens with one of these words.

  "Numbered one lower, in the same section" is V6's adjacency as the selector sees its pool: the
  published order is the source order (S4), sids number every sentence of the pinned text
  consecutively (`split_source`), and a heading lies between two sections. Measured over every
  consecutive sentence pair of the pinned texts: pilot 3's 96 texts, 6,575 pairs, all agree (same
  section <=> only whitespace between); the census run's 4,259 texts, 207,655 of 207,656 - the one
  exception is an article whose "See also" heading comes twice, where the rule is looser than V6 and
  V6 holds. A test ties the rule's words to `model4.PRONOUN_OPENERS`, in its order.

`SELECTOR_QUESTION` sha256 `85e6e47b...9066b701`, was `ce36085f...afb79c` (re-pinned in
`test_phase4_select.py` with the reasons). The reviewer question, the answer lines and both parsers
are unchanged; rule (9) stays verbatim. Mutation cases: 12 new in `P4_PILOT3_MUTATIONS` ("pilot 3,
decision 1" and "decision 2"), four re-anchored on the lines this rewrote.

### Pilot 3's fixes (2026-09-24, after its audit): the pronoun past the first word, the contradicted lead, sub-national names, the review's drops, the name V6 accepts

Pilot 3 (`output/remediation/phase4_runner/PILOT_RESULT_3.md`, run `pilot3-2026-09-24`) failed T1
(Stanydale Temple: "Pottery sherds show that it was also occupied ..." published without the sentence
*it* refers to), T4 (Dolebury Warren's card "Standing on a limestone ridge ..., it was made into a
hill fort ...", which V10 let through), T7 (Partiscum, CANARY-03: the lead the article's own body
contradicts) and T8 (57 of 78 lane-W sites write-eligible, three of the holds pipeline defects).
Under the thresholds' failure rule the causes were fixed before pilot 4; no threshold changed. The
measurements are in AUDIT_LOG, "Phase-4 pilot 4, sealed before its first model question".

- **T1 + T4, one gap: the pronoun past the first word.** The rule, in one sentence: *a sentence also
  leans on the sentence before it in its source when its first word of `model4.PERSONAL_PRONOUNS`
  (it, its, they, their, them, he, his, him, she, her; whole, any case) is one of `SUBJECT_PRONOUNS`
  (it, they, he, she) and stands right after the sentence's first comma (`, `), or right after the
  word "that" with no word of `ARTICLES` (the, a, an) before it.* A word is whole when no word
  character, apostrophe or hyphen stands beside it (`item`, `it's` are no *it*). V6 holds such a
  sentence unless its source predecessor is published right before it - exactly as it holds an
  opener of `PRONOUN_OPENERS`, which still counts (`verify4.leaning_pronoun`, read after the edits);
  V10 holds a card item that leans (card scope). **Measured cost**, over the census run's 88,936
  lane-W/S pool sentences of 4,100 sites: the rule binds 1,738 beyond the opener rule (158 of them
  have no adjacent predecessor in their pool, so they can never be published), 1 site loses its
  last possible sentence 1 (3,806 -> 3,805), 915 of the 42,401 card-length plain sentences are held
  as cards and 11 sites lose their last whole-sentence card candidate (3,656 -> 3,645); over pilots
  1-3's published texts it holds 7 sentences and 1 card, every one a pronoun whose antecedent lies
  outside its sentence (Stanydale's, the one the audit found broken; The Gop, the Altar Stone, Teman,
  Dolebury Warren; Dolebury's card). Of fifteen candidates measured beside the opener rule it is the
  most precise that holds both pilot-3 cases; a seeded sample of 60 of the 1,738, read by hand: 46
  refer outside their sentence, 9 are an expletive *it*, 5 refer inside it. The selector's rule (10) adds: "The same
  holds for a DESC sentence whose first it, its, they, their, them, he, his, him, she or her (after
  its removals) is it, they, he or she and stands right after the sentence's first comma, or right
  after "that" with no "the", "a" or "an" before it: "Standing on a ridge, it was made into a fort"
  and "Pottery sherds show that it was occupied" need the sentence before them."; rule (4) says the
  card "carries no pronoun that rule (10) ties to the sentence before it"; the reviewer gains "DROP a
  sentence in which it, its, they, their, them, he, his, him, she or her - at its start, after a
  fronted phrase or in a that-clause - refers to something no published sentence before it names, and
  DROP the card when such a pronoun has no antecedent inside the card: the card is read on its own."
  Tests tie the rule's words to the three lists, in their order.
- **T7: a sentence another sentence of the article contradicts.** The selector's rule (11): "never
  pick a sentence that another listed sentence contradicts, or reduces to a presumption, an
  assumption or a dispute, even when it is the article's lead." **The gap:** the reviewer was shown,
  per published sentence, the untrimmed source sentence, the two source sentences before it and its
  heading - for a lead, nothing - so the sentences that contradict a published one were never in
  front of it. `review4.passage` closes it: the reviewer's block (`prompts4.reviewer_block(site, rows,
  card, *, passage)`) opens with `<source id="PASSAGE">`, the passage the sentences were chosen from -
  the selector's pool for lanes W, S and T (`prompts4.pool_passage`: sid, section and text of every
  candidate, bounded by the pool's 24,000 characters), every cited page whole for lane R
  (`page_passage`). The question says "before them you see the passage the sentences were chosen
  from (PASSAGE)" and gains "DROP a sentence that another sentence of the passage contradicts, or
  reduces to a presumption, an assumption or a dispute, even when it is the article's lead; ask the
  same of the card." No gold or canary anchor is matched in code or named in a prompt.
- **V14: sub-national names that carry a country's name.** `country_lookup.SUBNATIONAL_NAME_TO_ISO`
  (15 verified entries from a scan of the census pools for a `NAME_TO_ISO` name directly preceded by
  a capitalised word or inside a longer proper name: New South Wales AU, New Mexico US, New England
  US, Central, Western and Greek Macedonia and Eastern Macedonia and Thrace GR, West Azerbaijan
  province IR, Upper Jordan Valley IL, Jordan Hill GB, Kraku Lu Jordan RS, El Peru GT, Inner Niger
  Delta ML, Lapis Niger IT, Denmark Fjord GL). `verify4`'s country regex reads both tables, longest
  first, so the whole name is read before the country inside it, and V14 compares the whole name's
  code; "South Wales" stays Wales. V10 still holds a card that carries such a name. Measured: V14's
  location holds over the census pools 74 -> 67 sentences (69 -> 62 sites).
- **T8: a review drop takes along the sentence that leans on it.** `review4.follow_drops` runs after
  the reviewer's verdict is parsed: a kept sentence that leans on the sentence before it
  (`sentences.leans_on_predecessor`, the pronoun rule above in the review's own code) whose published
  predecessor is dropped is dropped too, in order, so a chain goes whole; each is recorded in
  `review4.json` under `followed` (`sentence`, `follows`, `reason`: `review4.FOLLOWS_A_DROP`,
  `leans-on-a-dropped-sentence`), the reviewer's `lines` stay as written, and the site is judged on
  what remains (two sentences at least; S4 and S5 again, V9 included). A parity test runs both
  readings over `tests/remediation/p4_pronoun_cases.py`. Measured on pilot 3's answered reviews
  (rebuilt read-only): 3 of 63 reviewed sites - Stanydale R6, Mersinaki R4, Diana Fort R4.
- **Rule (7): the name V6 accepts, stated.** It now reads "(7) your first DESC sentence must name the
  site: its name, an alias or an also_named name of the site element, all of that name's words in
  their order with nothing but spaces or punctuation between them (case and accents do not matter); a
  name written "X (Y)" - ending in one bracket with no bracket inside it - or else "X, Y" - X before
  the first comma - is named by X alone only when also_named lists X; if no listed sentence names the
  site so, answer ABSTAIN with that reason;" - `verify4.name_in` and pilot 2's `name_base`, which S3
  lists in `also_named` exactly for a strong 'own' verdict. A test reads the two forms literally and
  gets `name_base`'s base in verify4's and select_stage's code for 17 names.

`SELECTOR_QUESTION` sha256 `a0b422e7...2a367ef93` (was `85e6e47b...9066b701`), `REVIEWER_QUESTION`
`89e6035d...fc71e7523` (was `59a1714e...a7d999`), each re-pinned per fix in `test_phase4_select.py`
with its reason. The answer lines and both parsers are unchanged. Mutation cases:
`P4_PILOT4_MUTATIONS`, and five older ones re-anchored on the lines this rewrote.

## 7. What Track D decided, and the one thing it needs from Track B (2026-09-23)

Track D (WB-D1 ... WB-D5, branch `wip/p4-write`) built against sections 1-6 unchanged; its
supplement (`wip/p4-write-sup`, the fixes of the two reviews of 2026-09-23) added the two `model4`
fields section 6 lists. What the design left open, and how the writer settled it:

- **Write batches.** A write batch is the rows one row group takes from one plan batch: plan batch
  `p4-0007` gives the write batches `p4-0007` (P4), `p4l-0007` (L) and `p5-0007` (P5), each written
  as **one chunk** (at most 100 sites - the step - and at most 200/100/100 rows), stamped
  `<family>:<batch>:chunk-NNNN`. The chunk number is the write round: 1, or 2 and up for a batch
  written again after a revert (a reverted round's stamps stay in the journal; `write_gate4.py
  --round N`, see "After a revert" below). The step of 100
  sites is `write_gate4.py --apply --step 100`: one step per invocation, and a batch is written
  only while it still fits into the step (with 15-site batches a step writes 90 sites; a batch
  larger than the step is refused).
- **The acceptance between steps is a handshake, not a promise** (supplement). After every
  written batch the gate records `STEP.json` in the apply root (the step's batches, stamps, sites
  and rows) and `LANE_PLAN.jsonl` (every rendered batch's plan rows: the `--plan` the acceptance
  reads). While `STEP.json` exists, `--apply` writes nothing and says why. The step is accepted by
  running `verify_writes4.py --lane <lane> --plan <apply root>/LANE_PLAN.jsonl --run <run dir>`
  (the command the gate prints; lanes p4 and p5 re-run V1-V15 and need `--run`), saving its
  output, and handing it to `write_gate4.py --group <G> --run <run> --accept <file>`. `--accept`
  records `ACCEPTED/step-NNNN.json` (the step, the output and its sha256) and removes `STEP.json`
  only when the output ends in `ACCEPT_EXIT=0`, says `RESULT: 0 deviation(s)`, has exactly one lane
  line for the step's lane whose stamp pattern covers every stamp the step wrote, read at least as
  many lane journal rows as the apply root has written under that pattern - every round, the
  reverted ones too (so it ran after this step, not before) - and is not the output an earlier
  step was accepted on. The lane line is parsed in the print
  format of `verify_writes4.py` (Track C, `wip/p4-verify`); a change of that line must change
  `write_gate4._ACCEPT_LANE` with it.
- **Write rounds, and what the reversal skips** (supplement). A change key names a transition, not
  a write: round 2 of a batch journals the same keys as round 1 under its own stamp. Every journal
  read is therefore scoped to the stamp as well - the read-back (`write_stage.journal_rows_sql(
  change_keys, run_stamp)`, shared through `journal_mismatches`) and `revert4`'s "reverted
  already" (the key **and** the stamp plus `-rollback`). `revert4` **skips** a matched write that
  already has its own reversal instead of refusing the pattern, and raises only when the pattern
  matches no write or every matched write is reverted already. Why: after one revert and one
  re-write, `--stamp-like 'phase5:%'` matches both rounds. Refusing would leave the live round
  revertable only by its exact stamp, so the red-CI answer of the P5 sitting would fail exactly
  the second time it is needed; reverting the reverted round again would need its field to hold
  its written value - which round 2 may have put back - and would undo round 2's write under round
  1's stamp. The set is fixed inside the transaction before anything moves (`ids := ARRAY(...)`);
  every guard, the loop and both invariants run over exactly that set. This PL/pgSQL has run only
  as pinned text and through SQLite evaluations of its set and post-read: rehearse it on
  production (`revert4.py --rehearse`) before relying on it.
- **After a revert: what the operator does** (supplement, checker review of 2026-09-23). `revert4`
  changes production only; the gate's `APPLIED.json` files are local records and learn of a revert
  only through the steps below. The gate's proof that a round is reverted is `revert4`'s own read
  (`revert4.reversal_read`, `write_gate4.prove_reverted`, read-only): the journal holds exactly as
  many writes under the round's stamp as its `APPLIED.json` says it wrote, and each has its own
  reversal kept (key and stamp plus `-rollback`).
  1. If the reverted step had no acceptance yet (`STEP.json` pending - the P5 red-CI case, or any
     revert of a step whose acceptance was red): `write_gate4.py --group <G> --run <run>
     --close-reverted`. On the proof for every batch of the step it records the step in
     `CLOSED/step-NNNN.json` with the proofs (never in `ACCEPTED/`: it was taken back, not
     accepted), moves each batch's `APPLIED.json` to `chunks/chunk-NNNN/` beside a `REVERTED.json`
     (the proof) and removes `STEP.json`. A row still live refuses the whole close. Until the step
     is accepted or closed, its batches are frozen: `--round` does not re-open them.
  2. `write_gate4.py --group <G> --run <run> --apply --round 2 --step 100` (the same `--round` for
     every step of the second sitting). A batch applied in round 1 is re-opened on the proof (its
     round-1 record kept as in 1), and chunk-0002 is rendered and written. A round the batch cannot
     take is refused with `WRITE_EXIT=1`, never skipped: `--round 3` over a round-1 batch, `--round
     2` for a batch never written (name the reverted batches with `--batch`, or write the others
     as round 1), `--round 1` for a re-opened batch. A batch already applied in the named round is
     done. Without `--round`, a reverted batch still reads as applied ("no open batch"): only
     `--round` asks production.
  3. The acceptance of every step after it: `--accept` counts every written round - live and
     reverted, from the records kept in 1 and 2 - under the stamps the output read, so an output
     taken between a revert and round 2 does not accept round 2.

  **Open for the `wip/p4-verify` merge (orchestrator decision).** Track C's `verify_writes4.
  accept4` reports a lane write followed by its own kept reversal as `CHANGED LATER`, and round 1
  plus round 2 of a key as `WRITTEN TWICE`; so after any revert in a lane no acceptance of that
  lane reaches `ACCEPT_EXIT=0` and `--apply` stays blocked (fail-closed). A round-scoped
  `--stamp-like` does not cure it once a lane mixes rounds: with batch 1 reverted and written as
  round 2 and batch 2 live in round 1, `phase5:%` gives `WRITTEN TWICE` and `CHANGED LATER` for
  batch 1 and `phase5:%:chunk-0002` gives `MOVED` for batch 2 (checker probes of 2026-09-23 against
  `wip/p4-verify` 6782fe3). What the gate needs from `accept4`: a lane link that has its own kept
  reversal is closed - no `CHANGED LATER` for it, not counted in `WRITTEN TWICE`, and a planned row
  whose only lane links are closed is judged like a row not written yet - plus a merged-branch test
  (write, revert, `--close-reverted` or accept, `--round 2`, accept). The printed acceptance
  command stays the lane's own pattern; the rows-read rule above is already scoped to it.
- **The statements' guards are pinned byte for byte** (supplement). The fake psql of the tests
  cannot evaluate PL/pgSQL, so every guard's predicate and RAISE in `render_apply`,
  `render_rollback` and `render_revert` is pinned in `tests/remediation/phase4_write_pins.py`;
  33 mutation cases each break one predicate or RAISE and go red on those pins.
- **The site page's lastmod** (WB-D4, supplement; decision D6). `pipeline/utils/public_sites.
  PAGE_COLUMNS` - read by the sitemap and IndexNow - counts a journalled write of a column the
  SSR page reads: 12 `unified_sites` columns (the design's six plus period_end, period_name, lat,
  lon, source_url, parent_site_id), `card_stats.best_wiki_url` and `source_language`, and the
  `wiki_images` columns that choose the page's one image or that it renders of it (a hero change
  advances the page). The P5 card writes do not. A test derives the lists from the route's SQL.
- **The group table lives in the writer** (`write4.GROUP_FAMILY`, `GROUP_PREFIX`), and
  `output/remediation/tools/lanes.py` registers the lanes `p4`, `p4l`, `p5` from it (their
  `family` and `stamp_like`; `run_dir` is `phase4_runner/runs`, the run is chosen with `--run`).
- **The verifier runs inside the plan.** `write4.plan_p4` calls `verify4.verify_site` itself, on the
  exact `new_raw_data`, texts, metas and quotes the rows write (with `card: null` where the card is
  held), so no row is planned from a verification of other bytes. `write_gate4` imports
  `phase4.verify4` when it plans P4.
- **Entry points.** `write4.plan_writes(batch, *, group, **inputs)` dispatches to `plan_p4(batch,
  *, scope, open_lanes, audited, verify, ledger)`, `plan_legacy(batch, *, written)` and
  `plan_cards(batch, *, scope, written, card_findings)` (`scope` for P4 and P5 since 2026-09-24,
  section 9; L takes none since the owner's decision of the same day, "Lane L marks every March-AI
  text" there); `write4.load_legacy_plan(path)` reads lane L's own plan (section 9);
  `write4.load_batch(batch_dir)` reads the section-4 files strictly (a
  site with neither an assembly nor a site hold is a hole and raises); `write4.render_apply(chunk,
  *, rehearse=False)`, `render_rollback(chunk)`, `apply_chunk(chunk, *, out, rehearse, runner,
  host)`; `write4.journal_evidence(assembly, *, texts, subject_gate, lane_detail, files, reviews,
  labels)`; `write4.exit_line(tag, run)` prints every Track-D tool's `*_EXIT=` line.
- **Lane gates are inputs, not guesses.** Which lanes passed their pilot (`--open-lanes`) and which
  lane-T/R sites the independent audit cleared (`--audited`, one site id per line) are handed to
  the plan; a site outside them is refused and counted, never written.

**Needed from Track B (a contract addition, section 4): the prompts on disk.** The journal evidence
of a written site records the sha256 of every file the model stages left for it - the answers
(`answers/`), the reviewer's answers (`reviews/`) and **the exact prompt of every call
(`prompts/`)** - plus its ledger labels (`<site_id>/<answer_key>`). `judge_site` stores answers but
not prompts, so every model stage (select, review, translate, restricted) must also store the prompt
it sends, write-once, through an `EvidenceStore` rooted at `<batch>/prompts/` under the same feature
as its answer. `write4` requires a written site's calls **by name** (section 6, decision D5): the
selector's answer for lanes W, S and T (the design's "selector-answer sha256"), T's translation
beside it, lane R's restricted call, and the reviewer's answer for every lane; every answer needs
its prompt of the same feature and its ledger line, and every ledger call of the site its answer.
A site that lacks one is refused (`journal-evidence-incomplete`), so without this addition no P4
row is planned.

## 8. The pilot's additions (wip/p4-pilot, 2026-09-24)

Owner order 2026-09-23, "everything with Opus": no model API and **no MiniMax search** is called from
the pipeline. What the Phase-4 pilot added so it could run under that order and the design's pilot
section (AUDIT_LOG, "the Phase-4 pilot, sealed before its first model question"):

- `route_stage.no_search()` - the searcher (`NoSearcher`, endpoint `SEARCHES_OFF_ENDPOINT`), the
  quota probe and the MiniMax pace of a run that may send no search; each raises `SearchesOff` if
  reached. `routes_batch` with `max_searches=0` never reaches them: a site only a search could anchor
  is held `search-stopped`. `run4 routes --max-searches 0` builds these seams and no MiniMax client.
- `mass4 --searches-off` (never with `--max-searches`): every routes stage is told 0, and the run
  carries no search ceiling (a ceiling of 0 is reached before the first batch).
- `plan4 build --pilot PILOT.jsonl` (never with `--gold`): the pilot is PILOT.jsonl's sites in its
  order (`plan4.pilot_site_ids`), and `write_plan(..., pilot=N)` gives them batches of their own, so
  the pilot's batches carry no other site into its model calls and audit.
- `phase4/pilot4.py` - `routeless` (the B3 read, one read-only SELECT), `build` (PILOT.jsonl: the
  seeded draw over a census run of the whole plan through S1 and S1b), `prose-errors`
  (`gold_prose_errors.json`) and `thresholds` (`PILOT_THRESHOLDS.md`, verbatim from the design).
- `phase3.fetch_stage.HostPacer.wait` waits for a lock its holder is deleting (Windows answers the
  re-create with access denied while the file is "delete pending") instead of dying of it.
- **Pilot 2** (2026-09-24, after pilot 1 failed T2, T5 and T8): `pilot4 build --after PILOT.jsonl
  --seed 20260924` - pilot 1's fixed members, refused unless site for site and in order, and a fresh
  draw of every seeded stratum excluding pilot 1's 62 draws (`PILOT2.jsonl`); `PILOT_THRESHOLDS.md`
  and `gold_prose_errors.json` stay pilot 1's, byte for byte. Its plan is `PLAN4.pilot2.jsonl` and
  its run `runs/pilot2-2026-09-24`. The fixes it runs with are section 7, "Pilot 1's fixes".
- **Pilot 3** (2026-09-24, after pilot 2 failed T3, T4, T6 and T8): `pilot4 build --after PILOT.jsonl
  --after PILOT2.jsonl --seed 20260925` - `--after` once per earlier pilot, each one's fixed members
  refused unless site for site and in order, and a fresh draw of every seeded stratum excluding the
  124 draws of pilots 1 and 2 (`PILOT3.jsonl`, sha256 `a4fa2f5f...f04152fc`); `PILOT_THRESHOLDS.md`
  and `gold_prose_errors.json` stay pilot 1's, byte for byte. Its plan is `PLAN4.pilot3.jsonl` and
  its run `runs/pilot3-2026-09-24`, whose ledger is its own (`runs/pilot3-2026-09-24/LEDGER.jsonl`,
  section 4). The fixes it runs with are section 7, "Pilot 1's fixes" and "Pilot 2's fixes". Before
  its first answer, section 7's "Pilot 3's decisions" changed the selector question, and its select
  questions were exported again (`handoff/p4-pilot3-select`, 87 questions, the S0/S1/S1b results of
  its run directory unchanged).
- **Pilot 4** (2026-09-24, after pilot 3 failed T1, T4, T7 and T8): `pilot4 build --after PILOT.jsonl
  --after PILOT2.jsonl --after PILOT3.jsonl --seed 20260926` (`pilot4.SEED_PILOT4`) - the same 70
  fixed members, a fresh draw of every seeded stratum excluding the 186 draws of pilots 1-3
  (`PILOT4.jsonl`, sha256 `30ab5e9d...57b2a26`; the B3 stratum's last 5 routeless sites);
  `PILOT_THRESHOLDS.md` and `gold_prose_errors.json` stay pilot 1's, byte for byte. Its plan is
  `PLAN4.pilot4.jsonl` and its run `runs/pilot4-2026-09-24` (its own ledger inside), its logs
  `output/remediation/logs/p4_pilot4`. The fixes it runs with are section 7, "Pilot 1's fixes",
  "Pilot 2's fixes", "Pilot 3's decisions" and "Pilot 3's fixes"; its select questions are in
  `handoff/p4-pilot4-select` (90 questions, none answered).

## 9. The owner's defect scope (wip/p4-pilot, 2026-09-24)

Owner decision 2026-09-23 (Martin, "Nur Defekt-Sites (Recommended)"): after a passing Phase-4 pilot,
Phases 4/5 write **only the sites with proven text defects** - the Phase-3 cleared defects plus the
ungrounded card texts, in the design's order; every other site's description and card stay exactly
as they are. Pilot 4 passed T1-T7 (`PILOT_RESULT_4.md`). The decision narrows the populations the
design gives P4, L and P5 (production_write, VOLUME: "about 4,300-4,500 P4 sites") and, like every
owner decision, ranks above the design.

- **The scope is data, pinned.** `phase4/scope4.py` derives it; `phase4_runner/SCOPE4.json` (v1,
  sha256 `19a57e9fd17f53601fecdd5424d3ea3e085c2690e8250cb72b004f010f833d6a`, pinned in
  `scope4.SCOPE_SHA256`, since version 2 in `scope4.SCOPE_V1_SHA256`) holds every site id with the
  lists it came from, the inputs' sha256 and the site list's own digest; `plan4.py scope` rebuilds
  it byte for byte from `S0_ROWS.jsonl` (`2c99f96f...`) and `logs/_write_dry/ALL_REFUSED.jsonl`
  (`7b4026d0...`). Three lists: `phase3-cleared-description` 322, `phase3-cleared-card` 709,
  `ungrounded-card` 876 - 1,623 sites. Its readers take that file or none: a file whose bytes are
  not the pin is refused (the gate ends `WRITE_EXIT=1`). A new scope is a new version and a new pin,
  never an edit of the file. Since 2026-09-25 the writers read version 2 (`SCOPE4.v2.json`, section
  11); version 1 stays byte for byte at its own pin and rebuilds the mass run's plan.
- **Which flags are a proven text defect.** `cleared-description-defect` and `cleared-card-defect`
  (a defect Phase 3's reviewer cleared) and an ungrounded card (no `SiteFlag`; `scope4` derives it).
  Not `t03` - its own comment says "order only" - and not `t03-severe` on its own: T03 names a
  contradiction between the text's years and the period bucket, not which side is wrong. Its
  findings are proposals for human review (the census counts 0 of them applicable), plan section 4.3
  names two severe T03 patterns as false alarms (7, 8), V14 holds a severe finding "for reading" for
  that reason, and of the 185 sites flagged severe on the description Phase 3's reviewer cleared the
  description defect of 18 (in the scope already) and refuted it on 16. V9's waiver is a lower bar -
  it lets a shorter text replace one that may be wrong - than the owner's "proven"; `t03-severe`
  keeps that job, and the order, inside the scope. Counted, it would add 101 sites.
- **The ungrounded cards, recomputed.** Plan section 5.1 counted 904 on 2026-09-19 (a card number
  that never appeared in the generator's input, `LEFT(description, 500)` of snapshot d4526691) and
  kept no list; `output/remediation` holds none. `scope4.ungrounded_card` applies the documented
  method to `S0_ROWS.jsonl`, whose cards and descriptions are byte-identical to the census snapshot of
  2026-09-20 for all 5,004 sites: a number is a numeral as written (ASCII digits, comma thousands
  separators, a decimal part) read as its value, and it appeared when the same value is a numeral of
  the input's first 500 characters - not a digit run inside a longer numeral. 876 cards; the plan's
  three named examples (House of Taga, Hatunmarka, Maray Qalla) among them. One card that writes
  numbers belongs to a site the snapshot does not have (Temple of Baalshamin, created after
  d4526691): its input is unknown, so it is not claimed and the file lists it under `unclaimed`. The
  2026-09-19 matcher was not kept, so 904 cannot be reproduced exactly; 40 readings of it measured on
  the same data give 788-897 with Baalshamin counted (this one 877), and a digit-run substring match
  does not even catch House of Taga (AUDIT_LOG, "The owner's defect scope").
- **The refusal is the writer's, not a `HoldReason`.** `write4.RULE_OUT_OF_SCOPE =
  "outside-defect-scope"` joins the writer's refusal rules (section 7): `plan_p4` and `plan_cards`
  take `scope` as a required keyword (no default: a plan without it is a `TypeError`) and ask it
  **before every other rule**, so a site outside the scope is counted under it whatever else would
  hold it, and nothing of it is verified or read. `write_gate4` loads the pinned scope for P4 and
  P5, prints it, counts the refusals on its "refused by rule" line, and has no flag to switch it
  off.
  (Until 2026-09-24 L was scoped too; see "Lane L marks every March-AI text" below.)
  `model4` is unchanged (section 1, rule 1): no stage holds a site for the scope, because the mass
  run's plan never carries one (below).
- **L.** Not scoped since the owner's decision of 2026-09-24 ("Lane L marks every March-AI text",
  below). From c9cf66e to that decision L marked only a scope site Phase 4 held, and the March texts
  outside the scope stayed unmarked - the owner's question this section recorded as open.
- **P5.** No card and no card clear outside the scope. A held card that is only ungrounded (not one
  of the 709) keeps its text: the design clears the 709 alone.
- **V9 inside the scope.** Its floor stays waived only for `cleared-description-defect` and
  `t03-severe`. A site in the scope for its card alone keeps V9's 50 % floor on its description, so
  `PILOT_RESULT_4.md`'s "this hold cannot occur for the defect sites of the mass run" holds for the
  description defects only: Brewer's Castle, held V9 in pilot 4, is an ungrounded-card site.
- **The mass run's plan** is `plan4.py build --pilot PILOT4.jsonl --defect-scope --out
  PLAN4.scope.jsonl` (`plan4.write_scoped_plan`): the full plan's sites after the pilot's, in the
  design's order (cleared defects, T03, the rest), only the scope's, in batches of 15 numbered after
  the pilot's own (`p4-0010` on) - a journal stamp names its batch, so no mass batch reuses a pilot
  id. Pilot 4's sites stay its run's (written or held there, never asked again); the draws of the
  failed pilots 1-3 were never written and go in like any site. `mass4` prints, on every run, how
  many sites of its open batches lie outside the scope, and refuses a live round that holds a model
  stage while one does (a done batch asks nothing again, so re-driving a pilot's run is not refused).
- **A re-plan without rows drops the statements an earlier plan rendered** for that round
  (`write_gate4.drop_unwritten_statements`): the scope emptied pilot 4's `p4-0004`, whose
  `APPLY.sql` from the unscoped dry run would otherwise have stayed beside an empty `PLAN.jsonl`. A
  round's record (`APPLIED.json`, `REVERTED.json`) and a stopped batch's statements are never
  touched.

### Lane L marks every March-AI text (owner decision 2026-09-24; wip/p4-L, 2026-09-25)

Owner decision 2026-09-24 (Martin, "Alle kennzeichnen (Recommended)"): lane L - which writes no
text, only the provenance that makes a site show the existing "AI-generated text" footnote (EU AI
Act Art. 50) - marks **every** March-AI text, not only the 1,623 sites of the defect scope. P4 and
P5 stay scoped ("Nur Defekt-Sites"). What stays: a text equal to its pre-March state (d4526691) gets
no marking (HUMAN_ONLY D7: its origin is not provable; `UNCLAIMED.jsonl`), and so does a site the
snapshot lacks; a site whose description P4 wrote (live phase-4 provenance) is never touched by L; a
provenance already present is never overwritten; L never changes a description. This restores the
design's own reach: its P4 population was every curated site, so its "held sites" were every site P4
did not write (licensing_and_ai_act: "so no LLM-processed text stays unmarked").

- **The population.** Every curated site whose live description differs from d4526691's and that
  carries no live phase-4 provenance - inside the scope or not. `write4.plan_legacy(batch, *,
  written)` takes no scope (one handed to it is a `TypeError`); `write_gate4` neither reads nor asks
  the scope for L and prints `LEGACY_UNSCOPED` instead of the scope line.
- **L's own plan, not a run's batches.** Until this decision `write_gate4 --group L --run <run>`
  planned the held sites of one run's plan batches (`p4l-NNNN` for `p4-NNNN`); a run's batches hold
  only its own sites, so no plan over runs could reach the curated sites outside the scope. Now:
  `plan4.py read --out LEGACY4_ROWS.jsonl` (the one read-only SELECT, a fresh read - never S0's
  rows) and `plan4.py legacy` (offline) write `phase4_runner/LEGACY4.jsonl`: every curated site in
  site-id order as a `PlanSite` without flags (they steer Phase 4's stages; L asks none), in batches
  of 15 marked `pass: phase4-legacy` (`legacy4.PLAN_MARK`; a P4 plan's batches carry no `pass`) and
  numbered from **p4-1001** (`legacy4.FIRST_BATCH`): past every P4 plan batch (unscoped p4-0334,
  scoped mass run p4-0115), so no write batch `p4l-1001` .. or journal stamp
  `phase4l:p4l-1NNN:chunk-NNNN` names a P4 plan batch or one of the per-run L plans rendered before.
  `write4.load_legacy_plan` reads it strictly (the mark, a plan batch id, no batch id or site
  twice); an L batch carries no stage outcome (no lanes, assemblies or holds - `holds` in an L row's
  evidence is therefore empty; a scope site's P4 holds stay in its run's `HOLDS4.jsonl`).
- **The gate.** `write_gate4.py --group L --legacy-plan <LEGACY4.jsonl>`, dry, `--rehearse` or
  `--apply --step 100`, and `--accept` / `--close-reverted` like every group. L never takes `--run`;
  P4 and P5 never take `--legacy-plan` (`plan_source_problem`): one L population, because a per-run
  L plan beside it would put a site into two write batches of one lane. Production is asked,
  read-only, which of the plan's sites carry a live phase-4 provenance (`written_sites`, windows of
  200); they are refused `written-by-p4`. An apply root holding write batches of another L plan is
  refused by name (`legacy_batches`): the acceptance's lane plan is every `PLAN.jsonl` in it. The
  step's acceptance command names no run: `verify_writes4.py --lane p4l --plan <apply
  root>/LANE_PLAN.jsonl` (lane p4l re-runs no verifier).
- **When L is written: once the held set is final** (design, production_write, ORDER: "then the L
  rows once the held set is final"). An L row changes `raw_data`; a scope site P4 writes after its L
  row no longer holds the `raw_data` its P4 plan names, and P4's preflight refuses the whole P4
  batch (fail-closed, never a silent overwrite; the way back is `revert4.py --stamp-like
  'phase4l:...' --site <id>`). So `plan4.py read` and `plan4.py legacy` run **after the last P4 step
  of the mass run is accepted**, and L's steps follow. Measured on 2026-09-25 (AUDIT_LOG): 1,115 of
  L's 4,499 rows are sites of the mass run's plan, 29 of them in L's first step. A site P4 holds
  under a lane whose pilot has not passed (T, R) is marked like any held site; should that lane open
  later, its L row is reverted before its P4 write.
- **The per-run L dry plans** rendered before (pilot 4: `logs/_write_apply_p4l/p4l-0001` ..
  `p4l-0009`, dry, never rehearsed or written; `phase4l:%` journals 0 rows) are moved aside before
  the first L plan is rendered into that apply root - the gate refuses otherwise.

## 10. The mass run's mid-run audit: the later namesake building, and one written site taken back (wip/p4-pilot, 2026-09-25)

The design's mass-run gate (entry [6], "MASS RUN GATES": "10 random written sites after every 500.
Any T1, T2 or T3 hit stops the writes and triggers re-verification of every written site of that
lane or rule; a systematic cause is reverted through revert4.py"). The mid-run audit of run
`mass-2026-09-25` (45 written sites, `logs/p4_mass/MIDRUN_AUDIT_VERDICTS.json`) found one T2:
Roman Bath, York (p4-0036), sentence 1 "The Roman Bath is a Grade II* listed public house ...", the
pub built in 1929-31 over the Roman bath house the record stands for. AUDIT_LOG, "Phase-4 mass run:
the mid-run audit's WRONG_SITE", has the evidence and the numbers.

- **The reviewer question** (`prompts4.REVIEWER_QUESTION`, sha256 `097c4589...d7d143106a8`, was
  `89e6035d...fc71e7523`) gains, right after the modern-place line: "DROP a sentence whose subject is
  a later building, business or institution (a pub, hotel, house, museum, shop, church, station
  ...) that shares or contains the site's name rather than the ancient site itself, even when it
  names the site." The review import is unchanged: what leans on a dropped sentence goes with it
  (`follow_drops`), and S4 and S5 run again - on Roman Bath, V6 then holds the site (sentence 1 of
  what is left names it by no V6 name). **The selector question is unchanged** (`a0b422e7...`): its
  rule (8) has the same gap, but the mass run's selector questions are answered under its pin, and
  a changed selector would make every exported answer stale. Review questions exported under the old
  pin and not imported are exported again (their answers kept, never deleted, in
  `handoff/p4-mass-review-stale-reviewer-89e6035d`).
- **No deterministic check.** The class is a question of which referent a sentence's subject has and
  when it was built. Measured over the census run's 88,936 lane-W/S pool sentences and the 2,046
  published sentences of the 336 written sites, "names the site and is/was a/an ... <noun>" with the
  businesses (pub, inn, hotel, restaurant, bar, shop, ...) fires on Roman Bath and on one false
  "bar"; with the buildings (house, museum, church, station, theatre, school, ...) on 48 census
  sentences, most of them ancient members (a Roman house, a Roman theatre, a road station, an
  open-air museum on its site) beside the true ones (an 18th-century house, a secondary school).
  It cannot be stated precisely in one sentence, so no V-rule is added.
- **`audit4.py hold --run-dir R --site <id> --audit <verdict file>`** writes the closed list's S6b
  reasons, which `model4.HoldReason` has carried since WB-00 and no code wrote before: a WRONG_SITE
  sentence `audit-wrong-site`, an UNSUPPORTED one `audit-unsupported` (site scope), a NOT_CONTAINED
  card `audit-not-contained` (card scope). The hold goes into the `holds.jsonl` of the batch that
  carries the site - its latest (`run4.aggregate_holds`) - after that batch's review, with the
  detail `<file name> sha256 <digest>: sentence <n> <verdict>: <note>`; `HOLDS4.jsonl` is rewritten
  (`run4.write_holds4`). `mass4.batch_done` is unaffected (the site is assembled and held), the
  site leaves `audit4.reviewed_sites` (so `audit4 draw --written` refuses it while it is still live:
  revert it first, or `--exclude` it), `write4.plan_p4` refuses it (`site-held`), and lane L treats
  it as any held site. Refused, with nothing written: a site the file judges not exactly once, a
  verdict outside `SUPPORTED | UNSUPPORTED | WRONG_SITE` or `CONTAINED | NOT_CONTAINED`, a record whose
  `name` is not the site's, a site outside the run, a record without a finding. Idempotent.
- **`revert4.py --site <id>`** narrows the matched writes to the rows journalled for that site
  (`site_id_ref`), and nothing else: the set is fixed before anything moves and every guard, the
  loop, both invariants and the reversal read after it run over it; without `--site` the statement
  is the pinned one byte for byte. The chunk's other sites keep their writes; a later revert of the
  whole chunk skips the site's rows (reverted already, section 7). `reversal_read` and
  `reversal_counts` take the same `site`.
- **`write_gate4` and a written batch re-planned without a site** (`sites_taken_back`). A written
  batch still keeps the plan it was written from; the one re-plan it accepts is that plan without
  the rows of whole sites, and only on production's read-only proof that every row the round wrote
  for each such site has its own reversal kept (`reversal_counts(stamp, site=...)`). Otherwise it
  refuses (`WRITE_EXIT=1`) and names `revert4.py --stamp-like <stamp> --site <id>`. `PLAN.jsonl`,
  `APPLIED.json` and so `LANE_PLAN.jsonl` stay what was written.
- **The acceptance after a site revert** is unchanged code (`verify_writes4.accept4`, section 7): the
  site's lane rows have their own kept reversal, and its planned rows - still in the lane plan - are
  judged like a reverted batch's, not yet written and at their old value; the rest of its chunk is
  carried and verified again. 0 deviations (tested). A `--complete` acceptance names the site's two
  rows `NOT WRITTEN`, as it would a reverted batch never written again.
- **The operator's sequence**, per site: `audit4.py hold` (the reason, in the run), `revert4.py
  --stamp-like '<its chunk's stamp>' --site <id>` rendered, `--rehearse`d, then `--apply`ed (the
  orchestrator), `write_gate4.py ... --batch <its batch>` dry (the proof, read-only), and
  `verify_writes4.py --lane p4 --plan <apply root>/LANE_PLAN.jsonl --run <every run>` (0 deviations).

## 11. Scope version 2 and the D9 run: the marker without an entry (wip/p4-pilot, 2026-09-25)

Owner order 2026-09-25 (Martin, "keine Fragen mehr, autonom Empfehlungen umsetzen"), recommendation
(c) of HUMAN_ONLY D9: a description that sets a `[N]` marker `raw_data.description_citations` has no
entry for is a proven text defect - the reader sees a bare number and the source is not in the data
(acceptance D1; the orphan-citations lane listed 9 such sites and wrote none of them). So those sites
join the defect scope and get a sourced description through the same Phase-4 pipeline, or stay held
with a closed-list reason. AUDIT_LOG, "HUMAN_ONLY D9 into Phase 4", has the evidence and numbers.

- **Scope version 2** (`phase4_runner/SCOPE4.v2.json`, pinned in `scope4.SCOPE_SHA256`, since
  version 3 in `scope4.SCOPE_V2_SHA256`, 1,631 sites) is version 1 and the list
  `d1-marker-without-entry` (9 sites), derived by `plan4.py scope` (the current version by default)
  from version 1's two inputs and the lane's listing (`mechanical_citations/SKIPPED.jsonl`,
  `--markers`, reason `marker-without-entry`): each listed site must be a curated S0 row whose own
  text fails D1 that way (`scope4.markers_without_entry`, census T08's `marker_sequence` and
  `entries`), never taken on the listing's word. Every version-1 site keeps its lists and the new
  list is appended (`scope4.VERSION_LISTS`), so version 2 refuses nothing version 1 allowed; the
  list adds no `SiteFlag` (V9's floor stays for its sites). The writers (`write_gate4` for P4 and
  P5), `mass4` and `build --scope-list` read version 2.
- **Version 1 stays** (`SCOPE4.json`, `scope4.SCOPE_V1_SHA256`, unchanged): `plan4.py scope
  --version 1` rebuilds it byte for byte, `scope4.load_scope(1)` reads it at its own pin, and `plan4.py
  build --pilot PILOT4.jsonl --defect-scope` builds the mass run's plan from it, so `PLAN4.scope.jsonl`
  rebuilds byte for byte. A file of one version at the other's pin is refused.
- **The plan of one list**: `plan4.py build --pilot PILOT4.jsonl --scope-list d1-marker-without-entry
  --after PLAN4.scope.jsonl --out PLAN4.d9.jsonl` (`plan4.write_list_plan`): the plan's sites after the
  pilot's, in the design's order, whose scope lists name the list, less every site an `--after` plan
  carries. Such a site's run held or wrote it and never asks it again, and `verify_writes4.index_runs`
  refuses a site two runs carry - Killa Mach'ay, in version 1 as a cleared card, was held `abstained`
  by the mass run's p4-0042 and stays so. `--after` names the plans that were run as a whole: not
  `PLAN4.pilot4.jsonl`, whose batches past the pilot's never ran (the pilot's sites are `--pilot`'s).
  Every listed site must be the pilot's, an earlier plan's or planned here; an empty plan is refused.
- **Its own batch block, from p4-0901** (since 2026-09-26 `build --first-batch 901`, section 12):
  every run writes into the one P4 apply root and a journal stamp names its batch, the mass run's
  plan ends at p4-0115 and `mass4.requeue_lines` would number a re-queue of the mass run on from
  p4-0116, and lane L's plan starts at p4-1001. (Superseded 2026-09-26: the mass run's 19
  `revision-too-fresh` sites are not re-queued there - they are the v3d plan's, section 12 and
  `PHASE4_V3_RUNBOOK.md` section 8, and `mass4` refuses a live round of the mass run once one of
  them is ready.) A list plan refuses to start where an earlier plan already numbers.
- **A batch short of its outcome files** (`lanes.jsonl`, `assembly.jsonl`, `holds.jsonl`) is refused
  by `write4.load_batch` as a hole (`PlanInputError`), so the gate prints `REFUSED` and its
  `WRITE_EXIT=1` line; before, a dry run over the D9 run after its select export ended in a
  `FileNotFoundError` without the exit line. The gate plans a batch once its review is imported.
- **Lane L before a later P4 write (section 9, "its L row is reverted before its P4 write").** Lane L
  marked every March-AI text P4 had not written, the listed sites among them; their D9 plan names
  S0's values, which production still holds except for L's `_description_provenance`, so P4's
  preflight would refuse the batch (`raw_data: the row no longer holds the planned old value`). The
  design's way back is taken, for the sites the P4 dry plan writes and only after the review
  import: `revert4.py --stamp-like 'phase4l:<its batch>:chunk-0001' --site <id>` rendered,
  `--rehearse`d, `--apply`ed, then P4's rehearsal and write. A site P4 holds keeps its L row. Lane L's
  acceptance afterwards names `--allow-stamp 'phase4:%'` beside the orphan-citations stamp and runs
  without `--complete`: a taken-back L row that P4 then wrote is superseded, while `--complete` names
  it `NOT WRITTEN`, as it names a P4 site taken back (section 10; tested). The mass run's 19
  `revision-too-fresh` sites do not take this way (superseded 2026-09-26): the v3d plan takes them
  over from a fresh read (section 12, `PHASE4_V3_RUNBOOK.md` section 8), so P4 replaces their L
  marking in the same cell and no L row of theirs is reverted.
- **The D9 run** is `runs/d9-2026-09-25` (plan `PLAN4.d9.jsonl`, batch p4-0901), its handoff
  `handoff/p4-d9-select` and `-review`, its logs `logs/p4_d9`; it writes into the same apply roots
  (`logs/_write_apply_p4`, `_write_apply_p5`), and every acceptance of lanes p4 and p5 names all
  three runs: `--run runs/pilot4-2026-09-24 --run runs/mass-2026-09-25 --run runs/d9-2026-09-25`.

## 12. Scope version 3: the March texts, descriptions only (lane WA, 2026-09-26)

Owner decisions of 2026-09-26 (`output/remediation/FINISH_PLAN_2026-09-26.md`, O1-O11), over the
design `output/remediation/REPAIR_TEXTS_2026-09-26.md`: the fresh acceptance's stage 1 measured the
2026-03 texts wrong far above tolerance (old descriptions 9 of 29, old cards 18 of 43, all severe),
so every curated site still carrying March text is a text-defect site. Its description goes through
the unchanged Phase-4 pipeline (same selector and reviewer pins, lanes W and S; T and R stay closed);
its card is lane WB's (O2, O3). The runbook, with the measured population and every command, is
`docs/procedures/PHASE4_V3_RUNBOOK.md`; the evidence is AUDIT_LOG, "Lane WA".

- **Scope version 3** (`phase4_runner/SCOPE4.v3.json`, `scope4.SCOPE_SHA256`
  `fb775d0e5563d9d441c7b7a33bd6e96016a5ac2f9db9524c566f10aeb84ad0ef`, 4,954 sites) is version 2 and
  the lists `march-description` (3,923: live provenance lane `L`) and `march-card` (3,822: a
  non-empty card no live Phase-5 write put there - a forward `phase5:` row without its own reversal,
  revert4's reading), retired sites in neither. Input: `MARCH4_ROWS.jsonl` (committed, `5a2949fb...`)
  from one read-only SELECT (`plan4.py read-march`, `plan4.MARCH_SQL`), whose sites must be exactly
  S0's (`scope4.march_lists`, `scope_payload(..., march_rows=)`). Versions 1 and 2 stay byte for byte
  at their own pins (`SCOPE_V1_*`, `SCOPE_V2_*`; `load_scope(1)`, `load_scope(2)`); version 3
  refuses nothing version 2 allowed. The March lists add no `SiteFlag` (V9's floor stays).
- **Descriptions only.** A plan of a list version 3 added (`scope4.DESCRIPTIONS_ONLY_LISTS`) carries
  `pass: phase4-descriptions-only` (`scope4.DESCRIPTIONS_ONLY_MARK`) on every batch. `run4 prepare`
  copies it into `input.json`; `mass4` reads it (`line_pass`: none or the mark, lane L's plan and
  anything else refused, one pass per plan) and gives it to every re-queued batch;
  `write4.load_batch` reads it into `BatchInputs.descriptions_only`. Then P4 writes the description
  with `card: null` (`without_card`, as for a card-scope hold; the journal evidence says
  `card_withheld`), so no provenance names a card that is never served (acceptance D4), and P5
  refuses every site of the batch (`descriptions-only-plan`, right after the scope): the P5 group of
  a v3 run is never run, and `verify_writes4 --lane p4` re-verifies such a site with no card. The
  plans of versions 1 and 2 carry no pass: their bytes are unchanged (the D9 plan rebuilds with
  `--first-batch 901`).
- **`plan4.py build --scope-list` is repeatable** (the union, each site once, in the plan's order)
  and takes `--first-batch N` (required; replaces the constant p4-0901): the block must lie past
  every `--after` ordinal and outside lane L's (`plan4.legacy_block`: p4-1001 .. p4-1334 for the
  5,004 curated sites). `--exclude FILE` leaves sites out (UUIDs, each a curated row; the summary
  prints a count and the file's sha256, never the ids). `--take-deferred RUN_DIR` plans the sites a
  run deferred `revision-too-fresh` in their latest batch although an `--after` plan carries them
  (`mass4.ready_to_hand_over`: refused while one still waits for its 48 h, or once the run re-queued
  one itself; each must be in a listed list and carried by an `--after` plan - the deferring run's
  plan must be named, or its other sites would be planned twice).
- **The two v3 plans** (measured 2026-09-26 from a fresh read, `PHASE4_V3_RUNBOOK.md`): `PLAN4.v3.jsonl`,
  3,238 sites in 216 batches, p4-2001 .. p4-2216 (`--after` the mass and D9 plans); and
  `PLAN4.v3d.jsonl` for the mass run's 19 `revision-too-fresh` sites, due 2026-09-26T21:30:14Z ..
  21:40:06Z: held there and never written, so not "new" - the v3 plan leaves them to the mass plan
  that carries them, and the follow-up plan takes them over (`--after` also `PLAN4.v3.jsonl`,
  `--take-deferred runs/mass-2026-09-25`, `--first-batch 2501`: 19 sites, p4-2501 .. p4-2502), run
  `runs/v3d-<date>`. The main plan so need not wait for 21:40Z, and the block p4-2501 leaves v3's own
  re-queue (p4-2217 on) room.
- **A plan without a pass never re-queues a descriptions-only site**
  (`mass4.descriptions_only_claims`, review finding 2026-09-26). A live round of the mass run after
  the 19's 48 h would have re-queued them into its own plan (p4-0116): S0's old values, P5 planning
  their extractive card, and then either v3d's `--take-deferred` refused or both runs assembling
  them. So `mass4` refuses a live round of a plan without a pass (scope versions 1 and 2) while a
  ready deferred site of it is named by a descriptions-only list, before `REQUEUE4.jsonl` is
  written; the dry run names them (`hand over`). A descriptions-only plan re-queues its own sites as
  before. The rule does not rest on the runbook's "never drive the mass run live again".
- **Preconditions of the plan's read** (`PHASE4_V3_RUNBOOK.md` section 0): the link and name pass L5
  (HUMAN_ONLY_DECISIONS B1-L, B1-N) is applied before `plan4.py read` - S1 fetches by the stored
  `enwiki_title`, so a wrong link gives a sourced description of the wrong subject (43 of the 72
  `link_suspect` sites are v3 sites), or L5's candidates are `--exclude`d and planned after L5; and
  the `scope-pending` flags come from the merged tree's E3 rule at build time (WD2's O7 changes 0
  of the v3 plan's 20, measured).
- **The acceptance and a deferred site.** `verify_writes4.index_runs` refused a site two runs carry.
  A run that held the site `revision-too-fresh` (site scope) and assembled nothing for it
  (`RunSite.deferred`, `deferred_in`) never wrote it: the site is read from the other run, in either
  order. Two runs that both could have written it stay refused.
- **The handoff at scale** (O11, 16 agents): `phase4/handoff4.py` - `brief` prints one batch agent's
  whole instruction for the selector or the reviewer (only its prompt files, no web, drafts in its
  own `<handoff>-scratch/<batch>/`, `--answered-by opus-<handoff name>-<batch>`); `check-answer`
  reads a draft through the stage's own parser against the batch's own pool or assembly, after
  proving the batch still builds the exported prompt, and asks a review for every shown sentence and
  the CARD line once; `ready --run-dir` names the batches whose every question is answered in
  shape, lists a named batch of the run that asked nothing (no folder: every site held before the
  stage) apart without waiting for it, and refuses a name that is no batch of the run. Agents
  answer different batches of one directory at once; `mass4` import rounds stay one at a time
  (`--only` the ready batches); `mass4`'s dry run prints the done batches (`done` line) the write
  gate may plan.
- **Lane L and v3.** The plan reads production afresh (`plan4.py read`), so its `raw_data` old values
  carry lane L's provenance and P4 replaces it in the same cell: no L row is reverted (section 11 was
  needed only because the D9 plan named S0's values). Lane L's acceptance afterwards runs with
  `--allow-stamp 'phase4:%'` (beside the orphan-citations and dangling-markers stamps) and without
  `--complete`. A P4 revert of a v3 site restores the March text and its L marking together.
- **Later lanes and the p4 acceptance.** The p4 acceptance re-reads every row P4 ever planned, so a
  lane that writes a cell of a P4-written site afterwards is named with `--allow-stamp` in every
  later p4 acceptance (its rows are then superseded, not re-verified as P4's): lane L `phase4l:%`,
  lane WB's provenance lane `wb-teaser-prov-%` (a new `raw_data` key `_card_provenance`, V12 would
  refuse it as P4's), lane WC `phase4wc:%`. WC and WB take only final sites: a site of a v3 batch
  not yet written, or held `revision-too-fresh` (it comes back through the re-queue), is still
  Phase 4's, and another lane's write would stop its batch at the preflight.
- **Not built** (owner decisions 2026-09-26): the design's clearing group C (lanes WC and WB take the
  held texts), and the exclusion of an acceptance draw (O1: no acceptance any more).
