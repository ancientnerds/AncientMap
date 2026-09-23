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
3. **Seams are imported, never re-implemented** (design, pipeline): `model_stage.PiRunner`,
   `ModelRunner`, `judge_site`, `ModelCall`, `Prompt`; `fetch_stage.HttpFetcher`, `PacedFetcher`,
   `HostPacer`, `probe_host`, `one_attempt`, `EvidenceStore`, `TRUNCATION_MARKER`;
   `search_stage.MiniMaxSearcher`, `Searcher`, `quota_stop_reason`, `search_slot`;
   `run.assign_batches`, `write_batches`, `read_jsonl`, `Batch`; `write_stage.run_sql`,
   `_json_rows`, `change_key`, `PK_COLUMN`; `mass_run.Spend`, `Budget`, `Progress`,
   `package_digest`, the circuit breaker and spawn retry; `discover_stage.quote_occurs`,
   `normalise_quote`, `claim_problems`; `census.fetch.USER_AGENT`;
   `pipeline.lyra.training_corpus.parse_robots`, `parse_tdmrep`, `reservation_for`,
   `html_reserves_tdm`; `pipeline.lyra.blocked_domains.BLOCKED_DOMAINS`. Never the
   `audit_enrich.py` Wave-4 chain.
4. **No live calls in tests.** No Pi, MiniMax, Anthropic, socket or production access in any test:
   a scripted `ModelRunner`, a scripted fetcher, a recording `SqlRunner`. Fakes refuse what the
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
from `model_stage.MODEL`), `LEGACY_AI_SYSTEM`, `LEGACY_BASIS`, version 1, the published licence
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
  test proves `verify4` does not import it). Before the pilot the orchestrator runs both finders
  over the same pools: any difference is a contract bug, fixed in the design reading, not by
  making one import the other.

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
  design's "defers the site to a later batch" is the driver's (Track B, `mass4`): after the run it
  re-queues the sites held `revision-too-fresh` into a new batch directory once 48 h have passed
  since their `retrieved_at`. The Track-A review measured on 2026-09-23: 102 of 4,502 articles
  were younger than 48 h, about 2 % of the sites at any moment.
- `route_stage.routes_batch(batch_dir, *, ledger, fetcher, searcher, max_searches: int, now:
  datetime, probe, wait, sleep=time.sleep) -> int`: writes `src.T.*`, `src.R*` (and `src.W`, `src.D`
  for the sites S1b anchors), then `lanes.jsonl` (one `LaneAssignment` per site, lane 0 included),
  `routes.fetch.json`, `search.json`, `routes.json` (its report and completion mark; `queries` and
  `search_requests` count the batch's route searches over every run of the stage, from the ledger)
  and holds `no-source`, `search-stopped` (the budget), `fetch-failed` (a route that could not be
  asked, whenever no own English article was found), `moved-during-fetch` and `revision-too-fresh`
  (an article S1b found). `max_searches` bounds the queries this run may still send. `probe` is
  `minimax_shared.probe_minimax_quota(force=True)`, `wait` paces the MiniMax host
  (`route_stage.open_search` builds the three live seams). Returns `STOP_RUN_EXIT` when the quota
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
  Sequence[M.PlanSite]) -> None` (order: pilot, cleared defects, T03, the rest; batches of 15
  through `assign_batches(prefix="p4")`). `plan4.main` runs `read` (the one read-only production
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

Provides:

- `text_sentences.split_sentences` (unchanged signature) protecting `c.`, `ca.`, `r.`, `fl.`, `b.`,
  `d.` before a digit; its 10 importers' tests run unchanged.
- `sentences.split_source(source_id: str, text: str) -> tuple[M.Sentence, ...]` (every sentence of
  the pinned text, spans offered, none containing a `M.PROTECTED_TOKENS` entry) and
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
- `run4`: subcommands `plan|sources|routes|select|assemble|verify|review|writeplan`, each printing
  `STAGE_EXIT=`; `mass4`: the loop, `--max-usd 15`, `--max-searches 700`,
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
  Mapping[str, Any]) -> tuple[M.Hold, ...]`: empty means V1-V15 pass; every hold carries its rule
  id (`M.HoldReason.V1` ... `V15`). `metas` are the raw `src.<id>.meta` objects, `quotes` the
  quote per published sentence (the store slice in a batch, the journal's at acceptance).
  `verify4.verify_batch(batch_dir) -> int`. Never imports `assemble.py`; one mutation case per rule.
- `verify_writes4`: the acceptance CLI (`ACCEPT_EXIT=`), reusing `verify_writes`' journal-chain
  reader and re-running `verify4.verify_site` on production read-back with the journal quotes.

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

## 7. What Track D decided, and the one thing it needs from Track B (2026-09-23)

Track D (WB-D1 ... WB-D5, branch `wip/p4-write`) built against sections 1-6 unchanged; its
supplement (`wip/p4-write-sup`, the fixes of the two reviews of 2026-09-23) added the two `model4`
fields section 6 lists. What the design left open, and how the writer settled it:

- **Write batches.** A write batch is the rows one row group takes from one plan batch: plan batch
  `p4-0007` gives the write batches `p4-0007` (P4), `p4l-0007` (L) and `p5-0007` (P5), each written
  as **one chunk** (at most 100 sites - the step - and at most 200/100/100 rows), stamped
  `<family>:<batch>:chunk-NNNN`. The chunk number is the write round: 1, or 2 and up for a batch
  written again after a revert (a reverted round's stamps stay in the journal). The step of 100
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
  many lane journal rows as the apply root has written (so it ran after this step, not before),
  and is not the output an earlier step was accepted on. The lane line is parsed in the print
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
  *, open_lanes, audited, verify, ledger)`, `plan_legacy(batch, *, written)` and `plan_cards(batch,
  *, written, card_findings)`; `write4.load_batch(batch_dir)` reads the section-4 files strictly (a
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
