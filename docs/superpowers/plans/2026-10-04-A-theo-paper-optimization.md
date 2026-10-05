# Theo research papers — process map and optimisation plan

**Date:** 2026-10-04
**Scope:** understand the paper production process as it runs live, then find the optimisations for
content, structure, citations, sources and images. Target from the owner: **at least one image per
section, goal four images per section.**
**Code changes made:** none. This document is a plan.
**Corpus measured:** the 31 public papers, read-only from production on 2026-10-04.
**Code read at:** `origin/main` = `909b604` (2026-10-04 12:39 +0200), branch `fix/2026-10-04-visitor-faults`.

Every claim is marked **[verified]** (read in the code or measured on the live system today),
**[inferred]** (a conclusion drawn from verified facts, with the reasoning given) or
**[not checked]**. File references are `path:line`.

## 0. Owner decisions taken for this plan

Asked 2026-10-04 15:24, adopted on timeout as the recommended defaults. Each is cheap to reverse.

1. **Scope: both chains, corpus first** — the 31 live papers, then the new dossier → studio chain.
2. **Image rule: 1 image per section as a hard minimum in `paper check`; 4 per section as a target
   that is reported, not enforced.**
3. **House format kept, but 3–6 investigation sections instead of 2–4, and each of the three fixed
   tail sections gets its own image quota.**
4. **Campaign in three stages:** re-embed from the existing pool (quota-neutral) → search only for
   sections that have zero images → top up to 4.

## 1. The process as it runs live

### 1.1 There are three chains; only one is alive

| Chain | Entry point | State on 2026-10-04 |
|---|---|---|
| V1 research + M3 paper writing | `pipeline/lyra/handlers/{paper,fact_check,presentation,image_generation,judge}.py` | **Retired** (commit `0705ee7`) |
| V2/V3 convergence research → dossier | `pipeline/lyra/convergence_orchestrator.py:159` | **Code live, never completed a run** |
| Authoring + publish | `pipeline/studio/paper/`, `pipeline/lyra/theo_publish.py` | **Code live, has never published a first paper** |

Measured proof of the second and third rows **[verified]**:
- `research_artifacts` holds only V1 kinds — `angle_findings` 57, `miner_candidates` 16,
  `curator_output` 15, `curator_input` 15, `specialist_analyses` 7, `paper_final` 6, `synthesis` 6,
  `debate` 6, `moderated` 6, `citation_registry` 5, `failure_snapshot` 2. The newest is 2026-09-26
  17:12 UTC. **There is not a single `dossier` artifact**, so the new chain has never finished a
  research run.
- `theo_paper_publications` holds 30 rows, **all of them `action='correct'`**. Not one
  `action='publish'`. The 31 public papers were published by the retired V1 auto-publish path.
- `THEO_WORKER_DISABLED=1` in the live environment (verified in the `ancient_nerds_api` and
  `ancient_nerds_theo_worker` containers). `scripts/run_theo_worker.py:66-70` logs "idling" and
  calls `signal.pause()`.

**Consequence for this plan [verified]:** every live paper is a *repaired legacy* paper, and the
process that will produce the *next* paper has never run end to end. Optimising only one of the two
would optimise a process that is either dead or unproven, so the plan covers both — corpus first
(decision 1), because that is where the defect is measurable and where readers are.

### 1.2 The research half (on the VPS, unattended)

`orchestrator.py` is **not** the research runner — it is the Lyra news cycle (`orchestrator.py:184`,
`STEP_ORDER`). The research run is `ConvergenceOrchestrator.run`
(`pipeline/lyra/convergence_orchestrator.py:159`); the 14 handlers are instantiated in execution
order at `convergence_orchestrator.py:100-122`. **[verified]**

1. `DecompositionHandler` (`handlers/decomposition.py:45`, prompt `prompts/v2_decomposition.txt`) —
   research angles; `max_angles: 12`, `initial_specialist_count: 6` (`research_state.py:50,52`).
2. Per angle and round:
   - `angle_search.py` — query refinement, `prompts/v2_query_refinement.txt` (`angle_search.py:126`)
   - `AngleImageResearchHandler` (`handlers/angle_image_research.py`) — **image search queries
     only**, 3–5 per angle, prompt `angle_image_queries.txt:3-5`
   - `AuditHandler` (`handlers/angle_audit.py:38-44`) — pure forwarder, no LLM. It must stay:
     `ContentFetchHandler` and `SpecialistHandler` listen on `SourcesAudited`. **[verified]**
   - `ContentFetchHandler` — robots checks and TDM reservation probes (`content_fetch.py:89-103,307`)
   - `SpecialistHandler` — findings, prompt `theo_specialist_analysis.txt` (`theo_specialists.py:1598`);
     rabbit-hole novelty check `v2_novelty_check.txt` (`angle_specialist.py:462`)
3. `ConvergenceChecker` — `saturation_threshold: 2`, `max_search_rounds_per_angle: 4`
   (`research_state.py:48-49,55`).
4. `CrossPollinationHandler` — `prompts/v2_cross_pollination.txt` (`cross_pollination.py:98`).
5. `SynthesisHandler` — `theo_synthesis.txt` produces `consensus_claims / contested_claims /
   unique_insights / open_questions` (`prompts/theo_synthesis.txt:33-62`), plus
   `v2_cross_angle.txt` (`synthesis.py:95`).
6. `DebateHandler` — `theo_debate_challenge.txt` + `theo_debate_defense.txt` (`debate.py:42-43`),
   `max_debate_rounds: 4` (`research_state.py:57`).
7. `ModeratorHandler` — `theo_moderator.txt` produces `final_claims / revised_claims /
   speculative_claims` (`theo_moderator.txt:6-10,35-55`). Citation preservation is explicit:
   *"Preserve ALL source IDs. Never drop citations."* (`theo_moderator.txt:24`).
8. `DossierHandler` (`handlers/dossier.py`) — writes 7 artifact kinds (`dossier.py:84-103`), runs
   archive completion (`dossier.py:107-114`), writes the `dossier` manifest **last**
   (`dossier.py:124-125`), emits `DossierReady` (`dossier.py:145`).

Sidecars: `DeadlineHandler` (`deadline_hours: 72`), `StatePersistHandler` (30 s DB flush).

All LLM calls go through `minimax_shared.py:145` with
`MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M3.1-Flash-Preview")`. **There is no retry or
repair loop on the research path** — one call per stage, JSON parsed, no re-ask. **[verified]**

**Archive completion** (`pipeline/lyra/archive_completion.py`) fetches the full text of every source
a moderated claim cites, with a dedicated Wikipedia path (`:152-153`) and doi.org resolution
(`:10,145`). Budget `THEO_ARCHIVE_COMPLETION_MAX_S` (default 1800, hard cap 2400, `:112-117`),
concurrency `THEO_ARCHIVE_COMPLETION_CONCURRENCY` (default 4, `:113`). Every cited source ends in
exactly one class `full_text | tdm_reserved | abstract_only | missing` (`:368-379`); a TDM-reserved
source is stored with its row and metadata but **without its body** (`:312-324`).
`theo_source_archive` holds **16 802 rows** today. **[verified]**

**Sources** (`pipeline/lyra/theo_sources.py:116-127`), default group `standard`:
`ancientnerds_db, ancientnerds_research, youtube_transcripts, semantic_scholar, openalex, crossref,
wikipedia, minimax`, from `THEO_SOURCE_APIS` (`research_state.py:60`). Key-gated:
`THEO_SEMANTIC_SCHOLAR_KEY` (1 req/s, `:272-277`), `THEO_OPENALEX_KEY/EMAIL`, `THEO_CORE_KEY`,
`THEO_EUROPEANA_KEY`, `THEO_SMITHSONIAN_KEY`, `NARA_API_KEY` (`:1506-1520`).
`ancientnerds_research` and `youtube_transcripts` register only when `importlib.util.find_spec("api")`
succeeds (`:1487-1494`) — true in the worker container, false in the Lyra image. **[verified]**

**Worker** (`api/services/theo_worker.py` + `scripts/run_theo_worker.py`, container
`ancient_nerds_theo_worker`): poll loop `theo_worker.py:948`; claim query `:1016-1032` takes
`status='queued'` or `'deferred'` older than 5 min, `is_batch` rows first, oldest first; `:371`
flips to `running`. Batch gate `:920-931` requires tier `HEALTHY`, known `weekly_pct`,
`days_left <= THEO_BATCH_MAX_DAYS_TO_RESET` and
`weekly_pct >= hours_left/run_hours * THEO_RUN_COST_PCT + days_left * THEO_LYRA_DAILY_RESERVE_PCT`.
The feeder stops at `THEO_MAX_UNWRITTEN_DOSSIERS` un-written dossiers (`:1197-1203`). Boot recovery
re-queues **all** `running` rows (`:1387`); the poll loop restarts 10 s after a crash (`:1396-1403`).
Success: `status='researched'`, `result_json = {"dossier": …, "title": None}` (`:517,531`) plus a
`thinking_log` `dossier_ready` notice (`:664-672`). Failure: `_mark_failed_running` →
`status='failed'` (`:749-751`). **[verified]**

**What the VPS decides — and what it does not [verified]:**

Decided there: which claims exist, their confidence tier and their sources
(`theo_moderator.txt:6-10,24`); which sources exist at all, with tier, licence and TDM flag; the full
text of every cited source; and **3–5 image search queries per angle** (`angle_image_queries.txt:3-5`).

Not decided there: the title, the section structure and headings, the abstract, the prose, the `[N]`
citation numbers, image selection, captions and placement, and the quality gate. All of that belongs
to a local authoring session.

### 1.3 The authoring half (local, `pipeline/studio`)

`pipeline/studio/paper/` is a package: `pull, numbering, gates, claims, images, bundle, publish,
evidence, anchors, workspace`. CLI at `cli_paper.py:147-207`. **[verified]**

1. `paper list` → `theo_dossier list` over the `researched` rows.
2. `paper pull ID` → ssh `theo_dossier export ID` → `dossier.json.gz` (export payload keys `version,
   texts_mode, request, manifest, moderated, synthesis, debate, angles, sources, texts, images`,
   `theo_dossier.py:217-243`), plus `texts/<source_id>.txt` and a rendered `brief.md` from
   `brief_template.md` (`workspace.py:64-90`). `legacy = "dossier" not in parts` (`:181`).
3. The session writes `draft.md` (hook paragraphs, `##` sections, `[S:<12hex>]` source markers, no
   title, no References, no images — `brief_template.md:15-21`), `paper_meta.json`
   `{title, card_description}` and `evidence.json`.
4. `paper number` → `numbering.build_paper`: `[S:id]` → `[N]` **in order of first appearance**
   (`numbering.py:74-83`, `theo_citations.py:196-207`), adds `# <title>`, embeds the selected images,
   builds `## References` with `format_references_list` (`numbering.py:152-158`,
   `theo_citations.py:217-271`); writes `paper.md` + `sources.json` (`:183-187`).
5. `claims-export` / `claims-import` → `mcode claim-check` → `claims_check/{tasks,pending,verdicts}.jsonl`
   with the live source text in `claims_check/live/<sid>.txt` (`claims.py:3-22`).
6. `images-export` → `mcode image-check` → `images-import` → `images/{tasks.jsonl, candidates/,
   selected.json}` (`images.py:1-29`).
7. `paper check` → 12 gates → `check_report.json` (`gates.py:383-446`); exit 1 on any failure.
8. `paper bundle` → `bundle.json` (`bundle.py:89-115`).
9. `paper publish` → scp the images, `--dry-run`, then `--apply` (`publish.py:192-272`).

**The studio image model, in the owner's own words in the code [verified]:**
`images.py:3` — the *model* names the image opportunities in `images/opportunities.json`;
`images.py:28` — *"One image per opportunity, so …"*; `brief_template.md:35` — *"4 to 10 places where
an image would show the reader the evidence"*; `brief_template.md:39` — *"images never sit in the
hook"*. `MAX_CANDIDATES = 8` (`images.py:88`), `MIN_WIDTH = 320` (`:89`),
`MAX_CAPTION_CHARS = 120` (`:90`), `JPEG_MAX_WIDTH = 1600` (`:91`).
The images gate requires the report to embed exactly the selected set (`gates.py:260-262`).

**This is the first hard blocker for the goal [inferred from verified numbers]:** the visible image
count equals the opportunity count, and the brief asks for 4–10 opportunities for a whole paper,
while the house format has 5–7 sections. 4–10 opportunities can cover at most two sections with one
image each. The new chain therefore cannot reach one image per section as written, and certainly not
four.

### 1.4 The publish half (VPS CLI)

`theo_publish.py:157-199` → `publish_paper` (`theo_publishing.py:825-929`): every gate runs, then the
slug, then a guarded `UPDATE` and the journal `INSERT` **in one commit** (`:893-911`), then a
re-read verification (`:912`) and the side effects (`:913-928`).

- **Bundle envelope** (`theo_publish.py:43-63`), no unknown keys: `publish {version, request_id,
  writer, result}`; `correct {version, request_id, writer, corrections_append}` plus optional
  `report, evidence, result, rewrite, dossier_request_id`; `register_video` with `poster`.
  `version` must be `int 1` (`:112`); `request_id` a canonical lowercase UUID (`:117`).
- **`result` keys** (`theo_publishing.py:261-273`): required `title, card_description, report,
  published_report, probative_images, published_block_ids` (must be `[]`), `quality_score` (needs
  `audit_gate_failures`), `evidence` (non-empty), `corrections` (must be `[]`); required-nullable
  `hero_image, published_hero_image`; optional `audit, writer`. `writer = {model, tool,
  research_model, published ∈ {automatic, manual}, human_review}` (`:248-295`), studio stamp
  `MiniMax-M3.1-Flash-Preview` / `mcode` / `MiniMax-M3` (`bundle.py:34-40`).
- **Idempotency:** a first publish is refused when `status ∉ {researched, completed}` or `is_public`
  (`:498-517`) and again in SQL with `AND is_public = FALSE` (`:610`); `rowcount != 1` raises
  `PublishConflictError` (`:897-901`). A `correct` on a public paper is the intended repair path.
- **Journal** `theo_paper_publications(request_id, action, slug, writer, bundle_sha256, gates,
  side_effects)` (`:591-597`) is written with the paper, never for a dry run. Side effects
  (`indexnow`, `qdrant`, `api_cache`, `notify`) are recorded in a second commit afterwards
  (`:928, 681-683`) and never undo the publish.
- **Exit codes** 0 ok, 1 gate failed, 2 unusable input, 3 the row changed between read and write
  (nothing committed), 4 committed but the re-read row differs. On exit 3 or 4 a journal row with
  the sent `bundle_sha256` means the write committed — never re-run it.

### 1.5 The gate

`validate_paper_artifact` (`pipeline/lyra/theo_citations.py:1645-1758`). It does not repair. Every
entry in `issues` fails the gate. **[verified]**

- exactly 0 or >1 References heading (`:1668-1672`; heading regex `^#{2,3}\s+(?:References|Sources)\s*$`
  at `:1519`, split on the **last** match, `:1559-1562`)
- any non-empty References line that parses with neither reference regex (`:1686-1692`)
- duplicate reference numbers (`:1694`), non-contiguous numbering (`:1699`)
- `[N]` cited but absent from the list (`:1707`), `[N]` in the list but never cited (`:1711`)
- uncited factual paragraphs (`:1719-1723`), `[N - topic]` placeholders (`:1725`), non-Latin script
  runs (`:1729`), non-numeric bracket tokens (`:1736`)

**What counts as a factual paragraph** — `_is_factual_paragraph` (`:952-964`) calls
`_is_non_prose_block` (`:921-940`), which exempts every heading block, a block starting with `![`, an
italic block containing `[Source](`, a bare `[Source](…)`, a bare `[x](y)` link and a block equal to
its own section title. Exempt sections: `abstract | introduction | methodology` (`:875-881`). Plus
sentence starts such as "this paper/research/study", "in summary", "to summarize" (`:886-902`) and
list items (`:902`). **That is the mechanism by which image captions never need a citation** — the
exemption lives in `_is_non_prose_block`, not in the uncited rule itself.

**Reference grammar**, verbatim (`:1931-1951`):
`[N] Title — https://…(accessed YYYY-MM-DD)[Academic]` and
`[N] Authors (YYYY). Title. Venue. DOI: 10.x/y(accessed …)[Academic]`.
`format_references_list` (`:248-252`) emits `[Academic]` only for `reliability_tier == 1` and
`[Reputable]` only for `== 2`; **tier 3 gets no tag at all**, and a `[Popular]` line matches neither
regex — inside `validate_paper_artifact` that is a hard `unparseable_ref_lines` failure, not a silent
zero.

`total_citations` counts `[N]` **occurrences**, not covered references (`:1703-1704`), so a ratio of
the two is not a coverage rate. The real completeness measures are `orphaned_refs` and
`uncited_paragraphs`. `quality_gate_passed` (`quality_gate.py:45-54`) is redundant: it demands
`citation_coverage = max(0, 15 - 3 × uncited) >= 9` (≤2 uncited) and `reference_integrity == 10`
(0 orphaned + 0 invalid) — both already implied by the artifact gate.

Studio gates: `gates.py:418-432` — artifact, structure, meta, references, specifics, coherence,
evidence, page_anchors, claims, images, hero, quality. The `claims` gate fails while answers are
missing (`claims.py:124-125`).

### 1.6 What the reader gets

`api/routes/research_html.py:130-166` builds
`body_html = inject_evidence_anchors(markdown_to_html(paper_markdown(row, title)))`; the SSR payload
renders in `ResearchPaperPage.tsx:141` → `PaperArticle.tsx:133-136` → `SanitizedMarkdownHtml`
(`dangerouslySetInnerHTML`). The whole paper is **one HTML blob**; there is no client-side markdown
parser and no second layout. `markdown_to_html` (`article_html_renderer.py:249-260`) adds h2/h3 slug
ids (`:227-246`) and wraps an image-only paragraph in `<figure><figcaption>` whose caption is the
**alt text** (`:178-221`). `galleryParser.ts` / `TheoPaperBody.tsx` (figure, mosaic, carousel,
lightbox) are used only by the SSE overlay (`TheoReportOverlay.tsx:171`), never by the published
page. **[verified]**

Measured on the live page `https://ancientnerds.com/research/the-engineering-and-origins-of-the-baalbek-megaliths`
today: HTTP 200, 25 `<figure>`, 25 `<img>`, **`loading="lazy"` count 0**, and **52 occurrences of the
machine marker `gallery:561e16f1|verified:yes|<title>` inside the rendered output** — i.e. the
internal gallery prefix is visible to readers in the caption. **[verified]**

## 2. Baseline, measured on the live corpus

All numbers below are from the 31 public papers, read from production today. **[verified]**

### 2.1 Structure

| Measure | Value |
|---|---|
| public papers | 31, all `is_public`, oldest 2026-05-14, newest 2026-09-25 |
| content sections (every `##` except References) | **220** (5–8 per paper, median 7) |
| investigation sections per paper | 1×1, 3×2, 10×3, **14×4** — 14 papers sit exactly on the cap of 4 |
| fixed tail sections | 93 instances (31 × `Connecting the Dots` / `The Other Side` / `What We Actually Know`) |
| section length | median 634 words, min 168, max 1418 |
| eligible paragraphs per section (>80 chars) | median 4, mean 4.2, max 8; **788 in the corpus** |
| prose words per paper | median **4182**, min 2006, max 7481 |
| papers below the studio's 5000-word floor | **21 of 31** (none above the 7500 ceiling) |

### 2.2 Images — the decisive table

| Measure | Value |
|---|---|
| images visible in the published text | **482** |
| images in `probative_images` (the pool) | **530** |
| pool images not visible on the page | **48** (24 of them in `the-enuma-elish-…`, whose text has **zero** images) |
| **sections with zero images** | **123 of 220 (56 %)** |
| fixed tail sections with zero images | **76 of 93 (82 %)**, mean 0.46 images per instance |
| investigation sections with zero images | 47 of 127 (37 %), mean 2.19 images per instance |
| median images per section | **0** (mean 1.76, max 16) |
| sections with ≥1 image | 97 of 220 |
| sections with ≥4 images | **45** |
| images missing to reach 1 per section (corpus) | **123** |
| images missing to reach 4 per section (corpus) | **598** |
| share of a paper's images sitting in its single most illustrated section | mean 54 %, median 50 % |
| pool entries carrying `section_heading` **and** `paragraph_index` | **530 of 530** |
| pool entries with `section_heading == "[inline]"` (placed outside any section) | **26** |
| captions marked "Illustration:" | present in most papers (the `weak`-verdict marker) |
| long section per paper with **zero** images | 11 of 31 |

`the-enuma-elish-tiamat-and-the-sitchin-nibiru-controversy` is the extreme case: 24 images in the
pool, 0 in the text, 6 sections, all six without an image. Its `report` field is also image-free, so
the images are in the pool only. **[verified]** The most likely cause is today's text correction
replacing the whole report with a file that carried no image markup while the pool was preserved —
which matches the known rule that `--report-file` cannot change the image set. **[inferred]**

### 2.3 Citations

| Measure | Value |
|---|---|
| `[N]` reference lines in the corpus | **1052** |
| orphaned refs / invalid markers / unparseable ref lines | **0 / 0 / 0** (structure intact, measured earlier over the same corpus) |
| citation density | min 1.11, median 1.95, max 3.76 markers per 100 prose words |
| density in the fixed tail sections | **1.29 per 100 words** |
| density in the investigation sections | **1.29 per 100 words** |
| reference lines containing a raw HTML tag | 3 (e.g. `<i>Tuka</i>`, a broken `<sup>☆`) |

The structure of citations is not a bottleneck. The density in the fixed tail sections is **identical**
to the investigation sections, so the tail is not under-cited — it is only under-illustrated.

### 2.4 Sources

| Measure | Value |
|---|---|
| distinct source domains across the corpus | **535** |
| distinct domains per paper | median 25 (min 8, max 39) |
| reference lines with an `http` URL | **969 of 1052** — 83 lines carry no URL, **but every one of them has a DOI**, so 0 are unresolvable |
| reference lines with a DOI | 122 (11.6 %) |'
| `[Academic]` tag | 318 (30.2 %) |
| `[Reputable]` tag | 112 (10.6 %) |
| no tier tag at all | **622 (59.1 %)** |
| low-tier platform share | **141 (13.4 %)**: `youtu.be` 67 (6.4 %), `researchgate.net` 22, `academia.edu` 20, `core.ac.uk` 18, `semanticscholar.org` 8, `scribd.com` 6 |

Top domains overall: `en.wikipedia.org` 92, `youtu.be` 67, `researchgate.net` 22, `academia.edu` 20,
`core.ac.uk` 18, `arxiv.org` 15, `ui.adsabs.harvard.edu` 14, `pubmed.ncbi.nlm.nih.gov` 13.

### 2.5 Campaign state of 2026-10-04

- `theo_paper_publications`: 30 rows, all `action='correct'`, between 2026-10-02 17:24 and
  2026-10-04 12:48 UTC. **22 distinct papers**; **6 papers carry 2–3 rows** (`95fa3798` ×2,
  `ef52c194` ×3, `099ad920` ×2, `1d0053d4` ×3, `29436601` ×2, `e82bd854` ×2). Each row is a separate
  text revision, so readers see more correction rounds than the owner may intend. **[verified]**
- 21 of 31 papers carry `writer` and `corrections`; **9 papers were never touched today**:
  `cargo-cults`, `flying-discs`, `global-flood-myths`, `induced-emf`, `marss-lost-atmosphere`,
  `mogollon-pithouse`, `pineal-gland-dmt`, `quantum-approaches`, `the-phaeton-hypothesis`.
- 21 papers have `probative_images` = 24; the remaining 10 hold 4–18.
- `quality_score.badge` reads `Platinum 98` on many papers, but the D1–D7 quality judge applies only
  to journals (`theo_quality_judge.py:74` ← `research_stages.py:39`) — **no live gate maintains that
  badge for research papers**; it is a frozen V1 artifact. **[verified]**

## 3. Findings that block the goal

| # | Finding | Severity | Evidence |
|---|---|---|---|
| F1 | The image pipeline is **paragraph-anchored, never section-aware**. Opportunities are per paragraph (≥3 each), placement is `insert_image_after_paragraph`, and there is no per-section count, quota or floor anywhere in the image path. The only section-related number is a fallback cap of 2. | blocks the goal | `illustration_specialist.py:148-149,163-166`; `probative_images.py:767-769,772-785` |
| F2 | The 24-image paper budget is spent **in reading order**, so early sections consume it and later sections end up empty. | blocks the goal | measured: 54 % of a paper's images sit in its most illustrated section; 11 of 31 longest sections have 0 images; `probative_images.py:475` |
| F3 | The 24 budget is a `getattr` **literal**, not a setting — `probative_images_max_per_paper` does not exist in `pipeline/lyra/config.py`, and `api/services/theo_config.py` contains no image configuration at all. | high | `probative_images.py:475`; grep: 0 hits for the setting name in `config.py` |
| F4 | The studio asks the model for **4–10 opportunities for the whole paper** and takes exactly 1 image per opportunity, while the house format has 5–7 sections. | blocks the goal | `brief_template.md:35`; `images.py:28` |
| F5 | The backfill **cannot use the images a paper already has**: it hard-codes an empty candidate pool and forces an on-demand re-search, and it strips all inline images in `--replace` mode first. | high | `backfill_probative_images.py:182-184,169-172` |
| F6 | Rejected image candidates are **deleted**; there is no pool larger than the shown set for legacy papers. The owner's "pool for the video" only exists in the studio (`images/candidates/` vs `selected.json`). | high | `probative_images.py:709-719`; `studio/paper/images.py:453-489` |
| F7 | The public page shows the internal `gallery:<hash>\|verified:yes\|<title>` marker in the image caption, and loads all 25 images without `loading="lazy"`. | user-visible defect | measured live today: 52 hits, 0 lazy; `article_html_renderer.py:195-215` |
| F8 | The backfill only syncs `published_report` when the image-free prose of `published_report` and `report` match. When they differ it logs *"left untouched … Re-publish the paper to pick up the new images."* | medium | `backfill_probative_images.py:203-227` |
| F9 | 26 pool entries are tagged `section_heading == "[inline]"` — they were placed outside any section. | medium | measured: 13 papers affected |
| F10 | The caption builder duplicates the artist string when the field already contains it (`Photo: Unknown artistUnknown artist / Wikimedia Commons`) and can emit `Photo: Wikimedia Commons` with no artist at all. | medium | measured in the live Baalbek report; `theo_image_captions.py:138-187` |
| F11 | The image licence is stored per image but **never rendered**, although most sources are CC BY. | compliance | `theo_image_captions.py:155-158`; 16 stored keys incl. `license`, `license_url`, `source_url` |
| F12 | `images_per_paragraph_target: int = 3` (`config.py:253`) is **dead configuration** — defined, never read. It is exactly the knob the owner wants. | medium | grep: no reader anywhere |
| F13 | The 2–4 investigation-section cap binds for 14 of 31 papers, and 4 papers have only **one** investigation section. More sections is the cheapest way to create image slots. | high | measured distribution 1/2/3/4 = 4/3/10/14; `gates.py:65,110` |
| F14 | The three fixed tail sections are 82 % image-free, including `The Other Side` at 0.23 images per instance. | high | measured |
| F15 | The word floor (5000) and the section cap (2–4) are in tension: 21 of 31 live papers would be rejected by `paper check` on length alone, so the next paper must be roughly 1.5× longer than most existing ones. | high | measured: median 4182 words; `gates.py:62-63` |
| F16 | 12 prompt files from the retired writing chain are still tracked and have no loader — including `theo_paper_full.txt`, whose lines 15–19 and 56–59 are the only written record of the section and citation-density spec. A reader auditing "what does the model produce" reads a dead spec. | medium | `312703d` removed only part of the set |
| F17 | The relevance and duplicate gates are not on the enqueue path: `POST /research` inserts straight to `queued`. Nothing rejects an irrelevant or duplicate question. | medium | `api/routes/theo.py:499-512`; `relevance_gate.py` only behind `POST /theo/check-relevance` |
| F18 | Worker boot recovery re-queues instead of resuming, so a container restart re-spends the whole LLM budget of a run that may have run for hours. | medium | `theo_worker.py:1387` |
| F19 | The claim query has no `FOR UPDATE SKIP LOCKED`; exclusion is in-process only. | medium, latent | `theo_worker.py:1016-1032` |
| F20 | `THEO_ARCHIVE_COMPLETION_MAX_S` outside 1…2400 raises `ValueError`, and the value is evaluated at the dossier stage — after the full research spend. | medium | `archive_completion.py:112-118` |
| F21 | 7.9 % of reference lines have no URL and 13.4 % come from low-tier platforms, `youtu.be` alone 6.4 %. | high, sources | measured |
| F22 | 59.1 % of reference lines carry no tier tag; the tier decision is host-only, so a `~user` page on `.edu` is labelled `[Academic]`. | high, sources | `score_tier_by_domain`; `reference-citation-tier-is-host-only` |
| F23 | The published `probative_images` entries carry the absolute server path `image_path: /app/public/data/research-images/…` in the public JSON. | low, hygiene | measured on the live row |
| F24 | `research_stages.py` looks retired but is the **journal** path and still calls `judge_paper`. Naming trap. | low | `article_generator.py:1227`; `research_stages.py:716` |

## 4. Optimisations

Nothing below is implemented. Each item names the file that would change, the measured effect, and
what has to be true before it is worth doing.

### 4.1 Images — the primary target

**I1 — Place the 48 unused pool images first. Quota-neutral. [decision 4, stage 1]**
Every one of the 530 pool entries already carries `section_heading` and `paragraph_index` (measured
530/530), and the file it points at is on disk. A placement pass that inserts the pool entries which
are not yet in the text costs **zero image searches and zero VLM calls**. Expected effect: all 31
papers become "pool = text", and `the-enuma-elish-…` goes from 0 to 24 visible images.
*Touches:* `pipeline/lyra/backfill_probative_images.py:182-184` (pass the stored pool into
`embed_probative_images` instead of `{}`) plus a new placement-only mode that does not strip.
*Verify with:* the same per-section measurement used for the baseline in this document.

**I2 — Replace the reading-order budget with a per-section floor, then a target. [decisions 2 + 3]**
Two changes, in this order:
- A **floor pass**: before anything else, every section gets one image. Implementation shape: order
  the opportunities round-robin by section rather than by paragraph index, so the first pass hands
  one image to each section. This is the "1 per section" hard minimum (decision 2) and it is what
  removes the 109 empty sections.
- A **top-up pass**: after the floor is met, spend the remaining budget up to **4 per section**.
  Budget arithmetic: 5–7 sections × 4 = 20–28 images, i.e. the existing 24 is almost exactly the
  4-per-section budget for a 6-section paper. Raising it to `4 × n_sections` (max 28) is therefore a
  small change, not a re-architecture.
*Touches:* `probative_images.py:475` (budget), and the opportunity ordering in
`select_opportunities_with_metrics` (`probative_images.py:438`).
*Honest limit:* the measured rejection counters show 36–189 candidates per paper lost to
`embed_skip_no_safe_candidates`, so **4 per section will not be reachable for every section of every
paper** — which is exactly why decision 2 makes 1 the hard rule and 4 the reported target. The
report must name the sections that stayed below 4 and why.

**I3 — Make the paper budget a real setting, and wire the dead knob. [F3, F12]**
Move the 24 from the `getattr` literal into `pipeline/lyra/config.py` next to
`probative_images_max_per_opportunity` (`config.py:255`), and either wire `images_per_paragraph_target`
(`config.py:253`) as the per-section target or delete it. Without this, every later tuning round is a
code change plus a deploy.

**I4 — Give the three fixed tail sections their own quota. [decision 3]**
`Connecting the Dots`, `The Other Side` and `What We Actually Know` are 82 % image-free and are the
reader's landing (`What We Actually Know` is the confidence-tiered landing by design). With F2 fixed
they will receive images from the floor pass like any other section; this item makes it explicit so a
future budget cut cannot silently strip them again. `The Other Side` at 0.23 images per instance is
the worst case and should be the acceptance test.

**I5 — Fix the studio brief and gate to match the target. [F4, decision 2]**
`brief_template.md:35` must ask for **one opportunity per section plus one per additional paragraph
that carries a concrete, visible subject** — for 5–7 sections that is 8–14 opportunities for the floor
and up to 24–28 for the target, against today's "4 to 10". `pipeline/studio/paper/gates.py:260-262`
must additionally check the **per-section** count, not only that the report embeds exactly the
selected set. Note the tension with `brief_template.md:39` ("images never sit in the hook"): the live
papers do carry lead images there, and 26 pool entries are tagged `[inline]`; the plan keeps the
hook free of images and says so explicitly rather than leaving the two rules in conflict. **[decide]**

**I6 — Stop deleting rejected candidates. [F6]**
Keep every downloaded candidate in a real pool with its verdict, so the video production can use
what the page rejected and a later re-placement needs no new search. The studio already has this
split (`images/candidates/` vs `selected.json`); the legacy path does not. This is also the cheapest
insurance against the next image pipeline change.

**I7 — Remove the two visible page defects. [F7, F10, F11, F23]**
- Strip the `gallery:` prefix before the alt text becomes a `<figcaption>`
  (`article_html_renderer.py:195-215`; the medium path already splits on `|`, `:161`).
- Add `loading="lazy"` to body images and reserve the width/height to avoid layout shift; keep
  `fetchPriority="high"` on the hero only.
- Guard the caption builder against a doubled artist and against a missing one
  (`theo_image_captions.py:138-187`).
- Render the licence next to the source link — the data is already stored
  (`theo_image_captions.py:155-158` currently suppresses it deliberately). CC BY attribution is a
  licence condition, not a nicety, and 59 % of the corpus images are Wikimedia/Europeana material.
- Stop publishing the absolute `/app/public/...` path in the public JSON.

**I8 — Resolve `[inline]` pool entries to a real section. [F9]**
26 entries across 13 papers carry `section_heading == "[inline]"`. Resolve the section from the stored
`paragraph_index` at placement time instead of leaving them unattributed.

### 4.2 Structure

**S1 — Raise the investigation-section cap from 2–4 to 3–6. [decision 3, F13]**
14 of 31 papers sit exactly on the cap of 4 and 4 papers have only one investigation section, so the
cap is binding. Raising it to 3–6 creates image slots without inventing content: with the three fixed
sections that yields 6–9 sections, i.e. 24–36 image slots at the 4-per-section target.
*Touches, all three must change together or the paper fails its own gate:*
`gates.py:65,110` (cap), `brief_template.md:50-51` (rule text), and the outline rules in
`brief_template.md:148-156` (which currently force angles to merge, rule 5: *"Two angles with closely
related findings merge into one section"*).
**Resolve the tension with F15 explicitly:** more sections plus a 5000-word floor means either
shorter sections or a longer paper. The plan's recommendation is to keep the floor at 5000 and let
sections become shorter (median today is 634 words; 6–9 sections at 5000 words means ~550–830 words
per section, i.e. the current median is already right).

**S2 — Add a per-section image quota to the structure gate.** Same place as I5: the structure gate
(`gates.py:383-446`) is the natural home for "1 image per section", because it already knows the
section list. One gate, not two.

**S3 — Decide what the fixed tail is for, in writing.** `The Other Side` is meant to argue the
opposing case at full strength (`docs/superpowers/plans/assets/writer-brief-editorial.md:86`,
`theo_moderator` design docs). It is also the emptiest section in the corpus (7 images across 31
instances) and the one most likely to restate claims without new sources. Its citation density is
fine (1.29/100 words, identical to the investigation sections), so the fix is not more citations but
more specificity: the brief should require each counter-argument to name a concrete source, which
also gives the image pipeline something to depict. **[decide]**

### 4.3 Content

**C1 — Put the relevance and duplicate gate on the enqueue path. [F17]**
`POST /research` currently inserts straight to `queued` (`api/routes/theo.py:499-512`); the gate exists
but is only reachable through a standalone endpoint. A thin or duplicate dossier costs a full research
run and produces a paper with nothing to illustrate — which then cannot meet any image floor.

**C2 — Make worker restarts resumable, or at least cheaper. [F18, F20]**
Boot recovery re-queues every `running` row (`theo_worker.py:1387`), re-spending the whole LLM budget
after a container restart; a deploy during a run is enough to trigger it. The dossier artifacts are
written per stage, so a resume-from-artifacts path exists in principle. Validate the
`THEO_ARCHIVE_COMPLETION_MAX_S` value at config load, not at the dossier stage, so a typo cannot
surface after the spend.

**C3 — Cap the brief's evidence truncation consciously. [not checked]**
`pull.py:30-31` caps debate output at 40 and angle findings at 30. Whether that truncates material
the writer needs is not verified. If it does, the fix is a per-angle summary line rather than a
larger cap.

**C4 — Do not treat `quality_score.badge` as a quality signal. [2.5]**
`Platinum 98` is a frozen V1 artifact; the D1–D7 judge only runs for journals. Either compute it for
the studio path from the studio gates or remove the badge from the paper page. Leaving a number on the
page that no live gate maintains is the kind of thing the owner's citation-integrity work is about.

### 4.4 Citations

**K1 — Do not rebuild the citation structure. [2.3]**
1052 references, 0 orphaned, 0 invalid, 0 unparseable, contiguous everywhere. The structure is not a
bottleneck and must not be touched.

**K2 — Make attribution accuracy a measured, gated property. [2.3 + the audit corpus]**
The stored `audit` is worthless as a reference (M3 marked 42/42 claims "supported"; M3.1 agrees on
only 31 %, and all 29 deviations plus 10 spot checks held against the source text). In the five papers
audited so far, 45–73 % of assertions were unsupported, misattributed or unverifiable. The studio has
a real claim gate (`claims.py:124-125`) that fails while answers are missing, and the owner rule says
a check type without an independently written verdict **holds**. So the plan is not a new check — it is
to make the existing one mandatory in the publish path: no paper is published while `claims_check` is
incomplete, and the verdict file must come from an independent agent run, not a self-stamped one.

**K3 — Add two mechanical reference-line rules. [2.4, F21]**
Both are cheap and both are objective: **every** reference line must carry a resolvable URL or a DOI
(83 lines today do not), and no reference line may contain raw HTML (3 today). Both belong in
`validate_paper_artifact` next to the existing `unparseable_ref_lines` check, not in a new gate.

### 4.5 Sources

**Q1 — Fix the tier decision to look at the path, not only the host. [F22]**
`score_tier_by_domain` checks the host only, so a `~user` page on `.edu` becomes `[Academic]`
(measured: a 378-word student page) and `prefer_tier_1_source_ids` even prefers such sources during
injection. A path check for `/~user/`, `/user/`, `/students/`, `/home/` and a document/lecture
directory exception is the documented fix; the code change was ordered on 2026-10-04 and is not part
of this plan.

**Q2 — Report the tier distribution instead of leaving it implicit. [2.4]**
59.1 % of reference lines carry no tag at all. Tier 3 getting no tag is by design
(`theo_citations.py:248-252`) but the effect is invisible on the page. Either render "no tier" as an
explicit state or stop implying that an untagged line was not classified.

**Q3 — Set a deliberate budget for weak source types. [F21]**
`youtu.be` is the second most cited domain in the corpus (67 lines, 6.4 %), ahead of every journal.
Video evidence is legitimate, but as *primary* support for a specific factual claim it is the weakest
class in the set. Proposal: a reference to a video must be one of several supporting sources for a
claim, never the only one — mechanically checkable, because the claim's marker list is known.
`researchgate.net`, `academia.edu` and `scribd.com` are upload platforms, not publishers; the same
rule applies.

**Q4 — Prefer the DOI when one exists. [2.4]**
Only 11.6 % of reference lines carry a DOI although `crossref` and `openalex` are in the live adapter
group and archive completion already resolves doi.org landing pages. Every source that has a DOI
should cite it, because the DOI is the one identifier that survives a dead landing page.

## 5. Campaign

Ordered so that each stage pays for itself before the next one starts, and so that the expensive
stage only runs for what is still missing. Quota figures are the operating experience
(~2 % of the weekly quota per paper for a full backfill, ~6–15 min) and are **[inferred, not
measured in this pass]**.

**Stage 0 — Baseline and harness (no quota).**
Freeze this document's measurements as the acceptance baseline: per-section image counts, zero-image
section list, pool-vs-text delta, reference-line defects, the live-page marker leak. Ship the
measurement scripts so the same numbers can be recomputed after every stage. Nothing else can be
judged without this.

*The scripts that produced every number in section 2 exist today at `C:\tmp\theo_opt\`* — `an01`
(inspect one report), `an02` (per-section baseline → `baseline/baseline.{json,csv}`), `an03` (image
zones), `an04` (fixed vs own sections), `an05` (sources and citation density), `an06` (reference-line
detail), `an07` (syncability), `an08` (final comparison), plus the read-only VPS probes
`probe0{1..6}_*.sh` and the JSONL export `papers.jsonl` (31 papers, 3.7 MB). `C:\tmp` is not durable —
Stage 0 consists of moving them into the repo under a path agreed with the owner, not of rewriting
them.

**Stage 1 — Place what we already own. Quota-neutral. (I1, I8)**
Insert the 48 unused pool images, resolve the 26 `[inline]` entries. Expected: 31/31 papers with
pool = text; `the-enuma-elish-…` from 0 to 24 visible images. No search, no VLM.
*Acceptance:* zero-image sections drop from 109; no image appears outside the section its
`section_heading` names; no file is deleted; every paper still passes `validate_paper_artifact`.
*Rollback:* the pool is unchanged, so removing the inserted markup restores the previous text; the
write path is the journalled `theo_publish --correct --report-file`, which is dry-runnable first.

**Stage 2 — One image per section, everywhere. [decisions 2 + 4]**
Floor pass only, over the 9 untouched papers and every section still empty. This is the campaign that
actually enforces the owner's minimum.
*Acceptance:* 0 of 220 sections without an image, or a named list of sections where no probative
image exists and the reason (this is the honest outcome the target must allow for).
*Cost:* 123 images at the corpus level, i.e. roughly 4–6 per paper for the 31 papers — well under a
full backfill each.

**Stage 3 — Top up to 4 per section. [decisions 2 + 4]**
Only for sections that are at 1–3. Budget `4 × n_sections`, max 28, raised to 6–9 sections after S1.
*Acceptance:* report per paper the sections that reached 4, and the ones that did not with the
rejection reason from the image counters. **Do not raise the budget above 4 per section to make the
number look better** — the counted loss is dominated by `embed_skip_no_safe_candidates`, not by the
budget.

**Stage 4 — The new chain, before its first paper.**
Apply I3, I5, S1, S2, K3 to the authoring path, and switch the worker on. The first new paper is the
real acceptance test of the whole plan; the corpus work above does not prove the new path, because the
new path has never run.
*Acceptance:* one paper published through `action='publish'`, passing `paper check` with a real
independently written `claims_check`, with ≥1 image in every section.

**Cross-cutting, any stage:** I7 (visible page defects) can ship first and independently — it is
small, it is user-visible today, and it carries no quota cost.

### Operational notes

- Every write goes through the journalled CLI, never a direct `result_json` update: dry run first
  (exit 1 = gate red, nothing written), then apply, then read `theo_paper_publications` to confirm one
  row per write. A `bundle_sha256` matching a sent bundle means the write committed; never re-run it.
- The 6 papers with 2–3 journal rows should be reviewed before Stage 1 adds more rounds: each stage
  that changes a public paper adds a visible correction entry.
- Quota is shared with Lyra (`THEO_LYRA_DAILY_RESERVE_PCT` is part of the batch gate). Stages 1 and 2
  are quota-neutral or cheap; Stage 3 is the expensive one and should be scheduled against the weekly
  reset, not run mid-week.
- No MiniMax PAYG path exists and none may be planned. Everything above runs inside the quota or on
  the Anthropic path.

## 6. Still open for the owner

1. **The hook.** `brief_template.md:39` forbids images in the hook; the live papers have lead images
   there and 26 pool entries are tagged `[inline]`. Pick one rule (I5).
2. **`The Other Side` content rule** — should each counter-argument be required to name a concrete
   source (S3)? It is an editorial change to the tone document.
3. **The badge** — recompute `quality_score` for the studio path, or remove it from the page (C4).
4. **The 6 papers with duplicate journal rows** — keep the history, or plan a reversal like the
   established `output/remediation/mechanical_reversal_*` pattern.
5. **Video claim on untagged candidates** — I6 keeps rejected candidates in a pool. Confirm the video
   production may use `weak`-verdict images, since those are the ones the page marks "Illustration:".

## 7. Not checked

- Runtime behaviour of any prompt or model call — this is a code and data reading, not an experiment.
- Whether `pull.py:30-31`'s caps (debate 40, angle findings 30) truncate material the writer needs.
- The cost and duration figures in Stage 3 (~2 % weekly quota, 6–15 min per paper) come from
  operating experience, not from a measurement taken in this pass.
- Whether the studio's `claims_check` verdicts on the five already-audited papers were written
  independently, and with what result.
- `angle_image_research.py`'s image *pool* builder in detail — it produces query strings only, and
  the actual fetching is `image_fetcher.py`; the connector-level candidate caps were mapped, the
  connector internals were not.
- Whether the paper page's evidence anchors, the corrections display and the `dossier_ready` /
  `paper_published` notices render correctly today — out of scope for this pass.
- Live `.env` values beyond `THEO_WORKER_DISABLED` and `LYRA_LLM_BACKEND`, which were read from the
  running containers. The remaining `THEO_*` keys and the source-API keys were not read.
- The video renderer's consumption of a paper's image set, except the glyph-rule intersection noted in
  the image-chain review (captions are only drawn if a caption is written into `timeline.credits`).

> **Corrected 2026-10-04 18:40.** Two figures in this document were wrong and are now fixed:
> the content-section count (the heading walk dropped the first `##` of every paper because it
> treated it as the title, though the title is the `#` line) and the source finding below (83
> reference lines have no URL, but all of them carry a DOI, so none is unresolvable). The gallery
> figure of 52 was the count in the served HTML of one page; the stored reports carry 235. Full
> table of the corrected numbers and how the error was caught:
> `2026-10-04-C-no-second-correction-round.md` section 4. The conclusions are unchanged.