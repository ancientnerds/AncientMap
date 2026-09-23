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

Provides (section 7 records the signatures Track B had to change and its span reading):

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
  100`, `WRITE_EXIT=`).
- `legacy4.legacy_provenance(site: M.PlanSite) -> M.LegacyProvenance | None` (`None` when the
  held text equals snapshot d4526691: no claim, listed for HUMAN_ONLY); `card_json` with
  `--check`, `--prerender`, `--regenerate`.

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

## 7. What Track B built against these contracts (WB-B1 ... WB-B4)

Recorded so Tracks C and D, and the parity check before the pilot, read the same thing. Where it
changes a signature of section 5, the change is the smallest one the code needed.

### Spans (section 3, Track B's reading; C2's finder must agree or the reading is fixed here)

A span is offered only on a sentence that ends in `.`, `!` or `?` and whose parentheses balance;
otherwise the sentence offers none. *Top level* is outside every parenthesis. A *delimiter comma*
is a top-level comma followed by a space (so `4,500` delimits nothing). Every range carries the
delimiter its removal must take, and edit 1 removes exactly the range:

- `p`: a top-level `(...)` group plus the space in front of it (`" (c. 30 m)"`); at the sentence
  start the space after it (`"(...) "`); with no space on either side, the group alone.
- `a`: a paired insertion, from a delimiter comma through the next delimiter comma
  (`", built by Khufu,"`), or from the space before a spaced en/em dash through the next one
  (`" - near the road -"` with en dashes). The pair is the delimiter: `A, X, B` becomes `A B`,
  never `A, B`. This departs from a literal "exactly one adjacent delimiter", which would leave
  `Khufu, built it` after an appositive.
- `l`: the text before the first delimiter comma when it is 1-6 whitespace tokens, plus that comma
  and the space after it (`"In 1900, "`); edit 4 restores the capital.
- `t`: from the last delimiter comma up to, not including, the final punctuation.

A range containing a protected token (`PROTECTED_TOKENS`, whole words, case-insensitive, `*` a
prefix, phrases as consecutive words, `c.`/`ca.` with their stop) is never offered. Identical ranges
are offered once. Ids count per kind in text order (`p1`, `p2`, `a1`, `l1`, `t1`). Kinds may
overlap (an `a` and the `t` after it share a comma): `select_stage.parse_selection` refuses a pick
whose chosen spans overlap without one holding the other (`span-not-offered`: no offered span is
their union), for a CARD pick together with its DESC pick's spans. A nested span is dropped with its
outer one, and `drop` lists maximal ranges only; ranges that merely touch stay two ranges.

Edits 2-4 apply to the whole trimmed slice (collapse runs of spaces, `' ,'` -> `','`, uppercase the
first character when the first drop starts at the sentence start); edit 5 is `' [n]'` before the
last character. The card's spoken edit is `c.`/`ca.` followed by an optional space before a digit
-> `circa ` (lower case only). Card items are joined with one space.

The pool offers only complete sentences (`is_complete_sentence`) of 25-400 characters that end in
`.`, `!` or `?`, outside the sections `see also, references, notes, footnotes, citations, sources,
bibliography, further reading, external links, gallery, literature, works cited, notes and
references, references and notes, explanatory notes, in popular culture, popular culture`
(case-insensitive, a subsection by its own title). Lane S filters by name before the 6-per-section
count. Names match as folded whole words (NFKD without marks, casefold).

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
- `run4` adds `prepare` (the plan line to `input.json`, write-once) and `holds` (`HOLDS4.jsonl`);
  `select` runs S3, S3T and S3R in that order. `plan` and `writeplan` forward their arguments to
  `plan4.main(argv: list[str]) -> int` and `write4.main(argv: list[str]) -> int`, which Tracks A and
  D provide (each prints its own report). `routes` passes `max_searches` = the run's remaining
  allowance; `sources` uses `HttpFetcher(max_bytes=1 MiB)` (WB-A1's parameter), `routes` sends only
  `*.wikipedia.org` and `wikidata.org` to it and every other host to the 60 KB default.
- A batch function's non-zero return stops the whole run (`mass4` reads `STAGE_EXIT=`); a stage
  that prints no exit line fails its batch and counts for the circuit breaker.

### Track B's files in a batch directory

`pools.jsonl`, `selection.jsonl` (`Selection`), `translations.jsonl`, `restatements.jsonl`, and
`prompts/`, `answers/`, `reviews/` (write-once, `EvidenceStore`); each LLM stage writes its file
even when empty, and an absent one means the stage never ran. Reports: `select.json`,
`translate.json`, `restricted.json` (per site: `label`, `prompt_sha256`, `answer_sha256`,
`cost_usd`, `outcome`) and `review4.json` (per site: the reviewer's `lines`, `kept`, `card`, and at
the top `assembly_sha256`). `assembly.jsonl` is written by `assemble` and rewritten by `review`
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
  treat a T/R site's cleared-defect card like any held card (P5/card-clear).
