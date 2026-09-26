# Ancient Nerds Studio + Claude write: design

Date: 2026-09-26 · Owner: Martin · Status: approved for autonomous build (owner mandate 2026-09-26)

## 0. Mandate and decisions this design rests on

Owner decisions (brainstorm 2026-09-25/26, recorded in memory `project-theo-youtube-studio`):

- Build the **studio** (a new core feature, used for years): YouTube long-form now, Shorts later.
- **Theo does research only.** MiniMax M3 researches on the VPS and stops after moderation. It
  stores a complete **dossier**. No M3 paper, no auto-publish.
- **The paper is written by Claude** in a Claude Code session, fact-checked claim by claim against
  archived source texts, with images checked or replaced. **Claude publishes automatically after all
  checks pass**, and the owner is notified.
- Fully autonomous, including migrations and deploy. Parallelism is unlimited.
- The owner decides Theo's topics (later Theo decides on its own). The topic queue is not touched.
- Rewriting the 31 existing papers comes **later**. The tooling must support it; this build does not run it.
- Video format: the Case File spine (sourced evidence cards, a probability meter, claims tested one
  by one, "what would change our mind"), NERV style, the Shorts narrator voice, no title card, no
  on-screen agents. Burned-in captions only in the ~30 s hook, plus an exact SRT for YouTube. The
  video must be understandable without narration. Markers move with their image and must hit the right
  object. No measuring lines on oblique photos. Comparisons state their basis. 3–5 platform moments
  of 5–15 s each, used only when they answer a question. Retention is the top priority (fast cursor, no dead air).
- **Licensing is out of scope for now (owner 2026-09-26: "ignore such licensing for now, do the best
  possible solution, I will comply later").** Mapbox fly-ins and satellite frames, full source-page
  captures and the music bed are used freely. Credits are still drawn in-frame and listed in the
  description (cheap, and it helps later compliance). Open compliance items are listed in §9.
- Maps are always our globe, never Google Maps. The framework covers all four topic types:
  A single site · B many places · C science/space · D texts/traditions.

Facts discovered while mapping the code (read-only, 2026-09-26) that this design must handle:

1. The M3 writing chain hangs off exactly one event, `ModeratorComplete`
   (handlers/moderator.py:106). It takes about 4 h of a 14 h run.
2. The whole run executes inside `await decomposition.decompose()`
   (convergence_orchestrator.py:317). So the deadline loop, the external-cancellation check and the
   30 s flush in the orchestrator **never run** in production.
3. `training_corpus` writes are not NUL-safe. The citation registry and the source-run links were
   lost for 2 of the last 5 runs.
4. The `specialist_analyses` artifact is always empty, because it is written before the analyses are assembled.
5. The image candidate pool is persisted only inside `paper_final`.
6. Full-text coverage of the sources behind moderated claims is about 50 %: Wikipedia, doi.org and
   YouTube are never fetched, and snippets of 500+ chars are never fetched.
7. The HTTP publish API cannot carry a Claude paper: it needs a Discord JWT and cannot set images or
   title. The only sanctioned paths from a local session are `ssh ancientnerds docker exec -i
   ancient_nerds_api python -m …` (credentials stay on the VPS) and scp into
   `public/data/research-images/<id>/`.
8. Every public reader filters `is_public AND status='completed' AND slug IS NOT NULL`, so a new
   pre-write status is invisible to the public by construction.
9. `recompute_quality_passed` returns False without `quality_score.audit_gate_failures`.
10. nh3 strips `id` attributes: anchors must be injected after sanitising, as `_heading_anchors` does.
11. **Mapbox Product Terms §1.7:** map content in videos is free only when shown incidentally in the
    context of our application. Standalone satellite fly-ins or static images as primary footage need
    purchased video rights. §2.8.1 forbids distributing static map images.
12. **EU AI Act Art. 50(4)/(5)** (in force 2026-08-02): AI-written public-interest text published
    without human editorial review needs a visible AI-generation disclosure.
13. Remotion: the free licence covers organisations with 3 or fewer people (the owner's one-person
    company qualifies). The current line is 4.0.x (latest 4.0.529); 5.0 is not released. All animation
    must be driven by `useCurrentFrame()` (no CSS animations).
14. YouTube: API uploads from unverified projects are forced private; the description is limited to
    5,000 bytes (no `<` `>`); chapters need a first entry at 0:00, at least 3, each at least 10 s; SRT captions are supported.

## 1. System overview

```
VPS (unchanged topic sources)            LOCAL (Claude Code session, owner's machine)
┌───────────────────────────────┐        ┌──────────────────────────────────────────────┐
│ Theo (M3): research only      │        │ pipeline/studio (Python)                      │
│  decompose → search → fetch → │  ssh   │  paper:  pull → write* → check* → images* →   │
│  specialists → synthesis →    │ ─────► │          publish (via ssh docker exec)        │
│  debate → moderator           │        │  video:  casefile* → script* → voice →        │
│  → DossierHandler             │ ◄───── │          capture → timeline → render → lint → │
│  status = 'researched'        │ publish│          package                              │
│  archive completion (full     │  CLI   │ video/ (Remotion renderer, NERV block library) │
│  texts of cited sources)      │        │ .claude/skills + .claude/workflows (tracked)   │
└───────────────────────────────┘        └──────────────────────────────────────────────┘
 * = model work, done by Claude in the session (files in, files out; the code validates)
```

No model API is called from studio code. Every judgement (writing, fact check, image check,
script) is produced by Claude in the session (inline or via workflows) and handed to the code as
files, which the code validates against schemas and rules.

## 2. Theo split (VPS side)

### 2.1 Orchestrator (`pipeline/lyra/convergence_orchestrator.py`)

- Remove registration of `PaperHandler`, `ProbativeImagesHandler`, `FactCheckHandler`,
  `PresentationHandler`, `ImageGenerationHandler` and `JudgeHandler`. Delete those modules
  (handlers/paper.py, fact_check.py, presentation.py, image_generation.py, judge.py, and the
  ProbativeImagesHandler class) and their events (`PaperReady`, `ProbativeImagesReady`,
  `FactCheckComplete`, `PresentationChecked`, `ImageGenComplete`, `QualityPassed`), phases
  (`WRITING`, `IMAGE_CURATION`, `JUDGING`) and prompts (v2_paper_*.txt, coherence_pass.txt,
  hallucination_repair.txt). Before deleting the v2_paper_* prompts, port their editorial spec
  into the Claude writer brief (§3.3). Keep every helper still used elsewhere or by the publish
  gate: theo_citations gate functions, quality_gate, the deterministic parts of hallucination_gate and
  coherence_pass, hero_picker, theo_image_captions, image_fetcher, image_gates, the
  probative_images helper functions used by backfill (`embed_probative_images`, `_claim_image_content`,
  `_limit_tagged`), and illustration_specialist / citation_verifier (journal pipeline).
- New `DossierHandler` (handlers/dossier.py), registered **first** on `ModeratorComplete`:
  1. Builds the dossier (see 2.2) and persists it. It must be idempotent, because the forced-deadline
     path can make the moderator fire twice.
  2. Runs **archive completion** (2.3), bounded by time.
  3. Sets `state.phase = ResearchPhase.DONE` and emits the new event `DossierReady(request_id)`.
     The orchestrator's done signal listens to `DossierReady` (replacing QualityPassed).
- Fix the nesting defect: run the cascade as a task
  (`cascade = asyncio.create_task(decomposition.decompose())`) while the existing deadline loop runs
  concurrently. Then `_check_external_cancellation` and `_flush_progress_to_db` really run. On
  cancellation or error the loop cancels the task. The loop ends when `done_event` is set or the task
  finishes. A finished task without `DossierReady` and without `state.error` is an error
  ("research ended without a dossier").
- Replace the empty-paper guard with a dossier guard. The run succeeds only if a dossier with at
  least 1 moderated final claim was persisted (`state.dossier_ref` set by the handler); otherwise it
  sets `state.error` with the reason.
- `persist_state_graph` keeps working and labels the node with the question.

### 2.2 Dossier storage

In `research_artifacts` (no FK, survives DELETE). `training_corpus.save_artifact` gains
`replace=True` semantics: DELETE rows with the same `(request_id, kind, ref)`, then INSERT, in one
transaction. Kinds written by the DossierHandler:

| kind | payload |
|---|---|
| `dossier` | manifest: `{version: 1, request_id, question, created_at, counts: {angles, findings, sources, final_claims, revised_claims, speculative_claims, images}, kinds: [...], archive: {cited_sources, full_text, abstract_only, missing, tdm_reserved}, research: {llm_calls, total_tokens, duration_s}}` |
| `moderated` | `state.moderated_result` (already written by StatePersist; rewritten here with replace) |
| `synthesis` | `{synthesis, cross_angle_connections}` |
| `debate` | `state.debate_result` |
| `angle_findings` | one row per angle (ref = angle id), as today |
| `specialist_analyses` | **fixed**: findings grouped by specialist_id + panel |
| `citation_registry` | `_registry_payload(registry)` (sources + claims), written here, not at run end |
| `image_candidate_pool` | `state.image_candidate_pool` |

The handler **must fail loudly**: an exception in the dossier write sets `state.error` (the run
becomes `failed`), unlike today's fail-soft corpus writes. All text is NUL-stripped
(`_strip_nul` over str fields and recursively over JSON payloads) in `archive_documents` and
`save_artifact`.

### 2.3 Archive completion (`pipeline/lyra/archive_completion.py`)

For every source id referenced by moderated `final_claims`, `revised_claims` or
`speculative_claims` whose best archive row (`training_corpus.best_archive_rows`: a fetched full text
before a TDM reservation before an adapter abstract, newest within each) is missing or an adapter abstract:

1. Resolve the fetchable URL. For doi.org, follow redirects to the publisher landing page.
   Wikipedia is fetched through its REST HTML endpoint.
2. Fetch with the existing fetch stack (`pipeline/utils` HTTP helpers, content_fetch's `_SKIP`
   rules, **except** that Wikipedia, doi.org and YouTube are allowed here).
3. Extract text: HTML via `pipeline/utils/text.extract_text_from_html`; PDF via `pypdf`
   (added to requirements-api.txt, pinned). YouTube counts as full text when `news_videos` holds
   its transcript; otherwise the fetch fails like any other: the reason goes into
   `manifest.archive.failures`, and the source falls back to its adapter abstract (`abstract_only`)
   or is `missing` without one.
4. Write the result through `archive_documents` and record the run link in `theo_source_archive_runs`
   with `cited=true` (meaning "cited by a moderated claim").

Respect `tdm_opt_out`: store metadata without the body, and mark the source as
`tdm_reserved` in the manifest. The local fact check treats them as source_missing (3.5). The step is bounded
(`THEO_ARCHIVE_COMPLETION_MAX_S`, default 1800 s; `THEO_ARCHIVE_COMPLETION_CONCURRENCY` 4).
Coverage numbers go into the manifest. Failures per source are recorded, never silent.

### 2.4 Worker (`api/services/theo_worker.py`)

- On success, status is `'researched'`, and `result_json` is set to
  `{"dossier": <manifest summary>, "title": null}`. `completed_at` and the counters are set as today.
  Credits are still deducted at research end.
- Still called: `persist_state_graph`, `mark_node_explored` (the topic is researched), `log_thinking`
  (event `dossier_ready`). No `_auto_publish` (deleted).
- `_persist_training_corpus`/`persist_run_corpus` stops writing `citation_registry` (the
  DossierHandler owns it). It keeps writing the failure snapshot on the error paths.
- Pacing: `_avg_batch_run_hours` includes `status IN ('completed','researched')` batch rows, but only
  those with `result_json::jsonb ? 'dossier'` (the research-only duration). `THEO_PAPER_EST_HOURS`
  and `THEO_PAPER_COST_PCT` are renamed to `THEO_RUN_EST_HOURS` (default 11) and
  `THEO_RUN_COST_PCT` (default 9), measured as the research share of the old runs.
- Feeder backlog cap: `_feeder_loop` does not enqueue while the count of `status='researched'`
  rows is at least `THEO_MAX_UNWRITTEN_DOSSIERS` (default 6).
- Notification: `send_discord_webhook` when `DISCORD_WEBHOOK_URL` is set; the `thinking_log` event
  is always written. (DISCORD_WEBHOOK_URL is currently unset, and setting it is an owner action.)

### 2.5 API and UI adjustments for `'researched'`

- `api/routes/theo.py`: the stream terminal set gains `researched`. The owner list and detail show
  it. DELETE keeps its archive-then-delete behaviour (artifacts survive; images are removed). The
  manual publish route requires `completed` and stays for UI/founder flows. It now imports the
  shared publish sequence (2.6).
- `TheoPage.tsx` / `TheoResearchLive.tsx`: remove the WRITE/JUDGE phases and the 'paper' /
  'quality_judge' stages. Show "Researched · awaiting write" for `researched`. The live panel ends at
  "Dossier ready".
- `generate_paper_audio` (tts_generator.py) reads `published_report`, falling back to `report`
  only where `published_report` does not exist yet. This is a bug fix: the page renders
  `published_report` (see memory `project-theo-published-report-trap`).

### 2.6 Shared publish sequence (`pipeline/lyra/theo_publishing.py`)

`_make_slug` and `_auto_publish`'s body move into pipeline (`api` may import `pipeline.lyra.**`;
`pipeline` must not import `api`):

```python
def make_slug(title: str) -> str
def publish_paper(session, request_id: str, result: dict, *, author: str = "Theo",
                  writer: dict, dry_run: bool) -> PublishOutcome
```

`publish_paper` does the following:
1. Re-runs `validate_paper_artifact` on `result["report"]` (no auto-repair; the local check must
   already have made it clean).
2. Runs `recompute_quality_passed`, the evidence-anchor resolution (every `result["evidence"]` entry
   matches exactly one paragraph), and the image existence check (every `/data/research-images/<id>/…`
   referenced in report, probative_images or hero_image exists under
   `/app/public/data/research-images/<id>/`).
3. Enforces `report == published_report` and `hero_image == published_hero_image`.
4. Picks the slug with collision handling, then in one transaction: UPDATE research_requests
   SET status='completed', completed_at=NOW(), result_json, is_public=TRUE,
   published_at=NOW(), published_by=author, slug WHERE id=:id AND status IN ('researched','completed')
   AND is_public = FALSE (a republish of a public paper goes through `correct_paper`, 2.7), plus an
   INSERT into `theo_paper_publications` (journal).
5. After commit: re-reads and verifies the row, then runs IndexNow (`/research/{slug}`, `/research/`)
   and `index_paper` (Qdrant). Their failures are recorded in the journal row (`side_effects` jsonb)
   and do not undo the publish. The nightly reindex is the documented backstop.

`PublishOutcome` = `{ok, slug, url, gates: {...}, side_effects: {...}, journal_id}`.

CLI (API image): `python -m pipeline.lyra.theo_publish (--dry-run|--apply) < bundle.json`
prints `PublishOutcome` JSON. Exit code ≠ 0 on any failed gate.

### 2.7 Corrections and video registration (same CLI module)

- `python -m pipeline.lyra.theo_publish --correct < correction.json`: `{request_id, report?,
  evidence?, corrections_append: [{date, text, evidence_id?}]}`. It re-runs the gates and keeps
  every existing evidence id: an id may only be retired by a correction entry that names it. It then
  updates report and published_report together, and journals the change.
- `python -m pipeline.lyra.theo_publish --register-video < video.json`: `{request_id, youtube_id,
  title, published_at, evidence_timestamps: {"ev-03": 312, ...}}`. Appends to
  `result_json.videos`.

### 2.8 Dossier export CLI (API image)

`python -m pipeline.lyra.theo_dossier list` prints researched rows with manifest summaries.
`python -m pipeline.lyra.theo_dossier export <request_id> [--texts cited|all]` streams a gzip'd JSON
bundle to stdout:

```json
{"version":1, "texts_mode":"cited", "request": {id, question, status, is_batch, user_id, created_at, completed_at},
 "manifest": {...}, "moderated": {...}, "synthesis": {...}, "debate": {...},
 "angles": [ {id, topic, description, findings:[...]} ],
 "sources": [ {id, url, title, domain, reliability_tier, doi, authors, venue, date, license,
               source_api, archive: {content_type, text_chars, fetched_at, tdm_opt_out}} ],
 "texts": { "<source_id>": "<full text>" },
 "images": { "<angle_id>": [ImageCandidate...] } }
```

`--texts cited` (default) includes the texts of sources referenced by moderated claims and by
angle findings that support them. `all` includes everything (large).

### 2.9 Migrations

- `0025_theo_paper_publications.sql`: table `theo_paper_publications` (id bigserial, request_id uuid
  NULL REFERENCES research_requests(id) ON DELETE SET NULL, action text CHECK IN
  ('publish','correct','register_video'), slug text, writer jsonb NOT NULL, bundle_sha256
  char(64) CHECK hex, gates jsonb NOT NULL, side_effects jsonb, created_at timestamptz default
  now()). Plus an index on research_artifacts (request_id, kind, created_at DESC) if not present.
- `0026_studio_episodes.sql`: ledger for studio renders (see 4.9).

## 3. Paper studio (local, `pipeline/studio/paper/`)

### 3.1 Workspace

`<STUDIO_ASSETS>/papers/<request_id>/`. STUDIO_ASSETS defaults to
`<main checkout>/video-assets/studio` and can be overridden by the env var `STUDIO_ASSETS`. The
layout:

```
dossier.json.gz      (pulled bundle)          brief.md        (writer brief, generated)
sources.json         (numbering [N] -> source id, generated from what the paper cites)
paper.md             (written by Claude)      evidence.json   (written by Claude, validated)
claims_check/        (handoff: tasks + verdicts)  images/ (candidates, checks, selected)
check_report.json    (all gates)              bundle.json     (publish bundle)
publish_outcome.json
```

### 3.2 CLI (`python -m pipeline.studio paper …`)

| command | does |
|---|---|
| `list` | ssh → `theo_dossier list` |
| `pull <id>` | ssh → `theo_dossier export`, writes dossier.json.gz, generates brief.md (question, the house-format rules, moderated claims with source ids, synthesis highlights, contested points and debate outcomes, the source list with tiers) |
| `number <id>` | reads the `[S:<source_id>]` markers in the draft and writes `sources.json` + the numbered `paper.md` with `[N]` and a `## References` block via `CitationRegistry.format_references_list` (the exact line format the gate accepts) |
| `check <id>` | deterministic gates (3.4) + completeness of the claim-check verdicts; writes check_report.json |
| `claims-export <id>` / `claims-import <id>` | handoff for the claim-by-claim fact check (3.5) |
| `images-export <id>` / `images-import <id>` | handoff for the image check (3.6) |
| `bundle <id>` | builds the publish bundle (report == published_report, title, card_description, probative_images, hero_image == published_hero_image, quality_score, audit, evidence, corrections: [], writer) |
| `publish <id> [--dry-run]` | scp the selected images → `research-images/<id>/`, ssh → `theo_publish --dry-run`, then `--apply`; writes publish_outcome.json |
| `correct <id>` / `register-video <id>` | 2.7 |

### 3.3 Writer brief (house format)

This ports the editorial spec of `v2_paper_outline/hook/section/connecting/otherside/assessment.txt`:

- Sequence: hook (1–2 paragraphs under the title, no heading) → 2–4 investigation sections →
  `Connecting the Dots` → `The Other Side` → `What We Actually Know` → `References`.
- 5,000–7,500 words. Every factual paragraph over 50 chars carries at least one citation.
- Speculation is labelled as speculation, and "The Other Side" argues the opposing case at full strength.
- Probability language for verdicts: almost certain · very likely · likely · roughly even ·
  unlikely · very unlikely.
- While drafting, Claude cites with `[S:<source_id>]` (registry ids from the dossier).
  `paper number` converts these to `[N]` and generates References.
- Every factual paragraph that carries a checkable claim gets an entry in `evidence.json`.

The brief lives in `pipeline/studio/paper/brief_template.md` (versioned) and is filled in by
`pull`.

### 3.4 Deterministic gates (`pipeline/studio/paper/gates.py`, pure, tested)

1. `validate_paper_artifact(report)` passes (theo_citations).
2. The five fixed or counted h2 groups are present in order (2–4 investigation h2s,
   `Connecting the Dots`, `The Other Side`, `What We Actually Know`, `References`), the hook has
   1–2 paragraphs, and the word count is inside the range.
3. Every `[N]` resolves in `sources.json`, and every source id exists in the dossier.
4. `hallucination_gate.extract_specifics` over the report: every number, date and proper-noun
   specific is found in the cited sources' archived texts (`verify_against_pack` with the texts as
   the pack). Unmatched specifics are listed; any unmatched specific in a cited paragraph fails.
5. `coherence_pass` title terms and numeric conflicts: 0 high conflicts.
6. evidence.json validates. Each entry `{id: "ev-NN", anchor_text, claim, source_ids, quote,
   quote_source_id, verdict}` has `anchor_text` matching exactly one paragraph, and `quote` occurs
   verbatim (whitespace-normalised) in the archived text of `quote_source_id`.
7. The claim-check verdicts cover every evidence entry and every cited factual paragraph, with no
   `unsupported` verdict (3.5).
8. Images: every embedded image has a check verdict of `meaningful` (probative) or `weak`
   (captioned "Illustration:"), plus licence, attribution and source URL. `misleading` and `off_topic`
   are dropped.
9. The hero image is chosen by `hero_picker.pick_hero_image` from the verified images.
10. `quality_score` is computed from these gates:
    `{score, badge: "Claim-checked", passed, metrics: {citation_coverage, reference_integrity,
    section_completeness, source_diversity, research_depth}, meta: {word_count, total_sources,
    total_claims, claims_verified, claims_checked, images_verified}, audit_gate_failures:
    {audit_passed, hallucination_final: 0, high_contradictions: 0, undefined_title_terms: 0, ...}}`.
    `passed` is true only when all gates pass.

### 3.5 Claim-by-claim fact check (handoff)

`claims-export` writes one task per evidence entry and per cited factual paragraph:
`claims_check/tasks.jsonl` holds `{task_id, kind, paragraph, claim, cited: [{source_id, url,
text_excerpt_or_path}], prompt_sha256}`. Full texts are referenced by path so agents read them
directly.

Claude answers through a workflow (`.claude/workflows/theo-claim-check.js`, tracked). Each task gets
one verifier plus an adversarial skeptic for anything judged `supported`, and writes
`claims_check/verdicts.jsonl`: `{task_id, verdict: supported|partly|unsupported|source_missing,
quote, quote_source_id, explanation, fix_suggestion, answered_by, prompt_sha256}`.

`claims-import` validates shape, coverage and prompt hashes. `partly` and `unsupported` block the
publish until the paper is fixed and re-checked. `source_missing` (a TDM-reserved or unfetchable
source) requires the claim to be re-sourced or removed.

### 3.6 Image check and replacement (handoff)

`images-export` collects candidates: the dossier pool plus new searches through
`image_fetcher.fetch_candidates` (Commons, Europeana, Smithsonian, Met, NARA) for each image
opportunity (a paragraph plus the intended subject). It pre-filters with `image_gates.metadata_gate_passes`
and dedup (`_claim_image_content` md5/dhash), downloads the bytes, and writes
`images/tasks.jsonl` with local file paths.

Claude checks each image visually (workflow `.claude/workflows/theo-image-check.js`) and writes
`{task_id, verdict: meaningful|weak|misleading|off_topic, depicts, subject_box: [x,y,w,h]|null,
caption, answered_by}`. `images-import` embeds with `theo_image_captions.image_markdown`/
`insert_image_after_paragraph` (web paths `/data/research-images/<id>/<file>`).

### 3.7 Disclosure

- `published_by` stays `'Theo'`, which keeps the Organization in JSON-LD and the "AI research agent" label.
- `result_json.writer = {model: "claude-opus-5-5", tool: "claude-code", research_model:
  "MiniMax-M3", published: "automatic", human_review: false}`.
- The paper page renders a visible disclosure line from `writer`: "Researched by Theo (AI research
  agent) · written by Claude (Anthropic) · published automatically after automated source
  checks, without human editorial review". This satisfies AI Act Art. 50(4)/(5).

## 4. Video studio (local, `pipeline/studio/` + `video/`)

### 4.1 Episode workspace

`<STUDIO_ASSETS>/episodes/<slug>/`:

```
episode.json   (config: paper request_id/slug, topic type A-D, voice, speed, licences)
casefile.json  (Claude-authored, validated)   script.json (Claude-authored, validated)
review.html    (owner-facing script table)    voice/ (beat mp3s, words.json)
captures/      (platform/globe/source clips + manifests)   media/ (stills, checked)
timeline.json  (compiled, frame-exact)        render/ (Remotion out, lint report)
package/       (mp4, srt, description.txt, titles.txt, thumbnail_3840.png, thumbnail_1280.jpg, youtube.json)
```

### 4.2 Case file (`pipeline/studio/casefile.py`)

A JSON schema plus a validator (a dataclass model, loaded from and dumped to JSON):

```json
{"version":1, "paper": {"request_id": "...", "slug": "...", "report_sha256": "..."} | null,
 "topic_type": "A|B|C|D",
 "claims": [{"id":"c1","label":"No one could move 800 t without machines","by":"core claim",
             "icon":"weight","status":"pending|supported|weakened|refuted|open"}],
 "evidence": [{"id":"e1","claim_id":"c1","kind":"fact|quote|quantity|date|image|place",
               "statement":"...","source":{"url","title","source_id"?,"tier","license","quote",
               "locator"}, "paper_anchor":"ev-07"|null,
               "verification":{"status":"verified|unverified|refuted","by","at","method"}}],
 "places": [{"id":"p1","name":"Baalbek quarry","lat":33.99917,"lng":36.20028,
             "site_id":"be81c1a6-..."|null,"coord_source":"..."}],
 "quantities": [{"id":"q1","label":"2014 block","value":[1500,1650],"unit":"t",
                 "basis":"sources differ: DAI 2014 vs Wikipedia","evidence":["e3","e4"]}],
 "media": [{"id":"m1","path":"media/stone_person.jpg","license":"CC BY-SA 4.0","attribution":"...",
            "source_url":"...","depicts":"...",
            "markers":[{"id":"mk1","box":[x,y,w,h],"label":"1 PERSON","verified":"crop-check"}]}],
 "meter": {"hypotheses":["Roman engineers","An older, lost civilization"], "start":[50,50]}}
```

Validation rules:
- The ids are unique.
- Every evidence item used by the script is `verified`.
- A quantity with a range must show the range (sources differ).
- A marker must have `verified: "crop-check"`.
- Places need `coord_source`.
- Media need a licence and attribution.

### 4.3 Script (`pipeline/studio/script.py`)

```json
{"version":1, "episode":"baalbek-c5", "fps":60, "voice":{"id":"English_expressive_narrator","speed":1.0},
 "beats":[{"id":"b01","chapter":"Hook","spoken":"This stone weighs about a thousand tonnes.",
           "display":"This stone weighs about 1,000 tonnes.", "hook":true,
           "evidence":["e1"], "visual":{"block":"PhotoPlate","props":{...}},
           "cues":[{"at_word":"person","do":"show","target":"mk1"}], "min_s":3.0}],
 "chapters":[{"title":"...","beat":"b01"}]}
```

Validator rules (errors block the voice/render steps):

- Every beat with a factual `spoken` sentence lists evidence ids, and all of them are verified in the case file.
- `display` differs from `spoken` only in the spelling of numbers and units (a token-level check).
- Hook: the beats flagged `hook` total at most 32 s (an estimate from words at 2.6 w/s; exact after voice).
- There is no title-card block, and no agent/character block exists.
- Platform moments: 3–5 per full episode (slices exempt), each at most 15 s.
- Every scene showing map content (`MapboxFlyover`, `MapboxTopdown`, `PlatformClip` with a map,
  `GlobeShot` with satellite) carries the in-frame credit (`© Mapbox © Maxar` / `© OpenStreetMap`).
- Every claim in the case file that appears on the board has an introduction beat, at least one
  evidence beat and a status beat.
- Chapters: the first starts at 0:00, there are at least 3 for a full episode, and each lasts at least 10 s (checked after voice).
- Every `visual.block` exists in the renderer's block registry (`video/src/blocks/registry.json`).

`python -m pipeline.studio episode review <slug>` renders `review.html`. This is the owner's
script table: time, spoken, picture block, evidence plus source, and check status.

### 4.4 Voice (`pipeline/studio/voice.py`)

- Beats are narrated one by one with `shorts_tts.narrate` (the MiniMax Shorts narrator,
  `tag_mp3_ai_generated`) at the episode speed (default 1.0; the Shorts use 0.92, the pilot 1.06).
  Long beats are split at sentence boundaries under 1,000 chars and concatenated with ffmpeg.
- Word timings come from `shorts_captions.transcribe_words` + `align_words(display_tokens)`, so
  the captions use the script's spelling ("tonnes", "1,000") and never Whisper's.
- Output: `voice/words.json` `{beat_id: {duration_s, words:[{w,s,e}]}}`.
- The MiniMax quota is probed first (`probe_minimax_quota`). The step refuses to start below 10 %
  of the 5 h window (the Theo research shares the plan).

### 4.5 Capture (`pipeline/studio/capture/`)

- **`platform.py`** records the real site via Playwright (Chrome channel) and a CDP screencast at
  1920×1080 with `deviceScaleFactor=2`, so close-ups stay sharp. It targets a local Vite server
  (`VITE_DEV_API_TARGET=https://ancientnerds.com`) or production. Actions come from a declarative
  list: `search`, `click_result`, `pause_rotation`, `fly_wait`, `open_details`, `measure(a,b)`,
  `toggle_layer`, `wait`. The cursor is fast: 0.25 s moves, 45 ms keystrokes. The injected NERV
  cursor is configured through the frontend's new `?video=1` mode (4.6). Frames plus timestamps are
  assembled into a CFR 60 fps MP4, and `capture.json` records the action times, which the timeline
  uses for the virtual camera.
- **`globe.py`** wraps `ancient-nerds-map/video/record.ts` for our vector globe (Three.js; Natural
  Earth coastlines and borders, site dots). New landscape scenes: `studio-globe-flyto` (rotate
  onto lat/lng, zoom to regional level, optional empire layer) and `studio-globe-places` (a set of
  places lighting up, for type B topics), plus the existing Mapbox fly-in scenes in landscape
  (`studio-mapbox-flyin`: space → site → orbit; `studio-mapbox-orbit`), and exact Mapbox Static
  top-down frames with pins projected by `projection.py`.
- **`sources.py`** captures source pages with Playwright: it scrolls to the quote, highlights it
  (a DOM Range wrap), hides banners and cookie bars, and captures the page with the highlight.
  Paywalled or login pages cannot be captured (technical limit), so use a QuoteCard. It also
  captures our paper page scrolled to `#ev-NN`.
- **`projection.py`** holds the pure math (tested): Web-Mercator lat/lng → pixel for a given
  centre/zoom/bearing (512-px tiles), and orthographic lat/lng → globe pixel for our Three.js camera.

### 4.6 Frontend video mode (`ancient-nerds-map`)

`?video=1` (in addition to `?demo=1`):
- It hides `.info-panel-top-right`, `.social-contribute-wrapper`, the FPS/status panels and tooltips.
- It sets `--hud-scale` from `?hud=1.3` and exposes `window.__VIDEO` (a ready flag).
- It never touches browser storage in the SSR render paths.

This is implemented in the globe app's existing demo plumbing (`App.tsx`/`Globe.tsx`/`demoApi.ts`).

### 4.7 Timeline (`pipeline/studio/timeline.py`)

The timeline compiles `script.json`, `voice/words.json`, the capture manifests and the case file
into `timeline.json`:

```json
{"version":1,"fps":60,"width":1920,"height":1080,"durationInFrames":N,
 "audio":{"narration":[{"src":"voice/b01.mp3","from":0}],"music":{"src":"...","gainDb":-8,
          "duck":{"underNarrationDb":-12,"attackFrames":6,"releaseFrames":24}}|null},
 "scenes":[{"id":"b01","from":0,"durationInFrames":540,"block":"PhotoPlate","props":{...},
            "cues":[{"frame":201,"do":"show","target":"mk1"}]}],
 "captions":[{"text":"THIS","from":21,"to":38}],
 "ticker":{"evidence":[{"frame":0,"n":0},...]},
 "chapters":[{"title":"...","frame":0}],
 "credits":[{"sceneId":"b03","text":"© Mapbox © Maxar"}]}
```

- Captions exist only for hook beats (display words).
- Cues resolve `at_word` to frames from the word timings.
- A scene lasts `max(min_s, speech + tail)`. Tails are 0.35 s lead plus 0.6 s after speech, and
  are configurable per beat.

### 4.8 Renderer (`video/`, Remotion 4.0.529, all @remotion/* pinned to the same exact version)

```
video/src/Root.tsx          Composition "Episode" + "Thumbnail" (calculateMetadata from timeline.json)
video/src/Episode.tsx       Sequence per scene, audio tracks (narration Audio per beat, music with duck callback)
video/src/theme/            colors (mirror of src/constants/colors + nerv css vars), fonts (@remotion/fonts, local woff2)
video/src/motion/           frame-driven NERV motion: crtOpen, bootIn, borderTrace, typeOn, digitRoll,
                            stampSlam, ringPulse, sweep; NO flicker/alert-flash/emergency-flash
video/src/blocks/           PhotoPlate (image + markers in one transformed layer, Ken Burns),
                            ScaleDrawing (to-scale SVG side view with basis note), UnitGrid,
                            EvidenceCard, SourceViewer (captured page + highlight + scroll),
                            Meter, ClaimBoard (claims appear on cue, statuses), PlatformClip
                            (captured MP4 + virtual camera keyframes), GlobeShot, ShareCard,
                            LowerThird, HookCaptions, Ticker, Stamp, QuoteCard, Timeline (type D),
                            Diagram (type C: NERV wireframe primitives), registry.json
video/src/layout/           zones (safe area, YouTube control zone), LayoutBox registration,
                            overlap checker (pure) + LayoutGuard (lint mode: console.error JSON per violation)
video/scripts/render.ts     bundle → selectComposition → renderMedia (h264, NVENC if possible,
                            chunked by frameRange, concat)
video/scripts/lint.ts       renderFrames every Nth frame (default every 6th frame, scale 0.5) with LINT=1;
                            collects violations from onBrowserLog; exit ≠ 0 on any violation
video/scripts/still.ts      thumbnail master 3840×2160 (scale 2) + 1280×720 JPEG < 2 MB
video/test/                 vitest: layout overlap geometry, marker transform math, timeline→frames helpers
```

- Assets reach Remotion through a per-render public dir (`--public-dir <episode>/render/public`),
  which the Python render step populates with hardlinks or copies of voice, captures and media, plus
  the site fonts from `ancient-nerds-map/public/fonts`. There are no absolute paths in props.
- Mapbox credits are drawn in-frame whenever a map is visible (`credits` in the timeline).

### 4.9 Render, lint, package, ledger

- `python -m pipeline.studio episode render <slug>` runs `node video/scripts/lint.ts` first and
  refuses to render on violations. Then it runs `render.ts`, then loudness: measure the integrated
  LUFS (`shorts_render.measure_lufs`) and apply gain to −14 LUFS with a true-peak limit.
  Afterwards it runs an audit that reuses the shorts audit probes: black frames, frozen runs,
  loudness, duration equal to the timeline.
- `episode package <slug>` writes `package/`:
  - the MP4 and the SRT, built from display words and non-overlapping cues (max 6 words per cue, broken at punctuation);
  - `description.txt`, at most 5,000 UTF-8 bytes with `<` and `>` stripped. It contains the hook
    sentence, the chapters (from the timeline; the first at 0:00, at least 3, each at least 10 s),
    "Evidence" timestamps with paper anchor links (UTM `utm_source=youtube&utm_medium=longform`),
    image and map credits, the music credit, and the AI disclosure ("Narration: AI-generated voice
    (MiniMax speech-2.8-hd). Research: Theo (AI). Script: Claude (AI).");
  - `titles.txt` (candidates the owner picks from);
  - the thumbnails;
  - `youtube.json` `{title, description, tags, categoryId: 27, containsSyntheticMedia: false,
    madeForKids: false, chapters, captions: "…srt"}`. `containsSyntheticMedia` becomes true
    automatically if any photorealistic AI-generated imagery is used, which the case file forbids
    by default.
- Upload stays **off**: `distributor.py` is not wired, and there is no OAuth token.
- Ledger `studio_episodes` (migration 0026): id, slug, paper_request_id uuid NULL FK SET NULL,
  topic_type, casefile_sha256, script_sha256, voice_id, pipeline_commit, video_sha256 UNIQUE,
  duration_s, youtube_id, status rendered|published|withdrawn (CHECKs as site_shorts),
  rendered_at, published_at. It is written through `ssh ancientnerds docker exec -i ancient_nerds_api
  python -m pipeline.studio.ledger_cli --record < row.json`. The module is stdlib + SQLAlchemy
  only and ships in the image. `episode register-youtube` sets the youtube_id after a manual upload
  and calls `theo_publish --register-video`.

### 4.10 Topic types → blocks

| type | place blocks | main infographics |
|---|---|---|
| A single site | PlatformClip (search → fly → details, Measure tool), GlobeShot flyto, PhotoPlate markers | ScaleDrawing, UnitGrid, Timeline of phases |
| B many places | GlobeShot places / PlatformClip with filters and layers | world distribution, frequency bars, Timeline |
| C science/space | GlobeShot only where places matter; SourceViewer of our paper page | Diagram (orbits, field lines, curves), orders-of-magnitude UnitGrid |
| D texts/traditions | GlobeShot places of origin, SourceViewer (text passage highlighted) | Timeline of transmission, QuoteCard |

Common to all: hook, ClaimBoard + Meter, EvidenceCard/SourceViewer, twist, ShareCard, verdict,
"what would change our mind".

### 4.11 GPU: always the NVIDIA RTX 3080, never the integrated AMD (binding, owner 2026-09-26)

The workstation is a hybrid laptop: **NVIDIA GeForce RTX 3080 Laptop GPU** (Windows Task Manager
"GPU 1"; the only CUDA device, so CUDA/NVENC index **0**) and an integrated **AMD Radeon** (Task
Manager "GPU 0"). Owner rule: every GPU workload of the studio runs on the NVIDIA; the AMD is never
used, and a run that would land on it (or on software rendering) must fail loudly instead.

- **Every Chromium the studio drives** (the Puppeteer recorder `ancient-nerds-map/video/record.ts`,
  the Playwright platform and source captures, Remotion's browser for lint/render/still) runs on the
  NVIDIA. For Puppeteer/Playwright: the flags `record.ts` already uses (`--use-angle=d3d11`,
  `--force_high_performance_gpu`, `--force-high-performance-gpu`, `--enable-gpu-rasterization`,
  `--ignore-gpu-blocklist`). Remotion does not accept arbitrary Chromium flags, so its browser
  executable gets the Windows per-app GPU preference (registry
  `HKCU\Software\Microsoft\DirectX\UserGpuPreferences`, value name = absolute exe path, data
  `GpuPreference=2;`), set by `python -m pipeline.studio doctor --fix-gpu` and checked by `doctor`.
- **Proof, not assumption:** each capture and each lint/render/still start reads WebGL's
  `UNMASKED_RENDERER_WEBGL` in the page it drives and aborts with a precise error unless it names
  the NVIDIA (not AMD, not SwiftShader/"Basic Render"). The capture manifest and the render ledger
  record the renderer string.
- **Encoding:** H.264/HEVC encodes run on NVENC explicitly (`h264_nvenc`/`hevc_nvenc` with
  `-gpu 0`). Remotion's `hardwareAcceleration: 'if-possible'` is not used: on Windows it silently
  encodes in software, which is exactly the fallback this project forbids. If Remotion itself cannot
  encode on NVENC here, it renders an intermediate (e.g. ProRes/PNG sequence or a lossless chunk) and
  the studio encodes that with ffmpeg NVENC; a missing NVENC is an error, not a software encode.
- **Transcription:** the studio's word timings run faster-whisper on `device="cuda",
  device_index=0` (float16). If the CUDA runtime libraries do not load, that is a setup error to fix
  (install the pinned NVIDIA wheels), never a silent CPU run. The site Shorts keep their current CPU
  setting unless changed deliberately; the studio passes its device explicitly.
- `doctor` reports the GPU state (nvidia-smi, the renderer strings, the registry preference, NVENC
  availability) and exits non-zero on any mismatch.

## 5. Claude Code operation

- The `.gitignore` gains exceptions `!.claude/skills/`, `!.claude/skills/**`, `!.claude/workflows/`,
  `!.claude/workflows/**`.
- Skills: `.claude/skills/theo-write/SKILL.md` (the weekly paper session end to end),
  `.claude/skills/studio-video/SKILL.md` (case file → script → … → package), and
  `.claude/skills/studio-casefile/SKILL.md` (how to build and verify a case file from a paper,
  including crop checks for markers).
- Workflows: `.claude/workflows/theo-claim-check.js`, `theo-image-check.js`,
  `studio-casefile-verify.js`, `studio-marker-check.js`.
- Procedure: `docs/procedures/STUDIO.md` (runbook, gates, recovery). CLAUDE.md gets a Studio
  section and an updated Theo section.

## 6. Error handling rules (no fallback code)

- Every CLI step validates its inputs and exits non-zero with a precise message. Nothing is
  skipped silently.
- Dossier writes fail loudly. Archive completion records per-source failures in the manifest.
- The publish CLI never auto-repairs, and the local check is the only place a paper gets fixed.
- Side effects after the publish commit (IndexNow, Qdrant) are journalled. Failure is visible in
  `publish_outcome.json` and in the journal.
- Render lint violations block the render. An audit failure marks the package `failed` with reasons.

## 7. Testing

- **Python** (`tests/pipeline/studio/`, `tests/pipeline/test_theo_*`, `tests/api/…`): schema
  validators, script rules, the timeline compiler (word → frame), projection math, description and
  SRT builders (byte limit, chapter rules), gates on fixture papers, NUL stripping, DossierHandler
  idempotency, the orchestrator research-only flow with fake handlers (the done signal, cancellation
  now working), the worker researched branch (no auto-publish, credits, graph), publish_paper gates
  (fixture result_json, anchor resolution, image existence with tmp dirs), dossier export shape.
  Heavy deps are imported lazily and tests use `importorskip`. No test touches video-assets.
- **Frontend**: SSR render test for the paper page with evidence anchors, video embed, corrections
  and disclosure; pyref fixtures updated; no browser storage.
- **Renderer**: `tsc`, vitest (layout, markers, timeline helpers), and a smoke render of a
  10-second fixture timeline in CI-less local verification.
- **CI**: new job `lint-video` (path filter `video/**`: npm ci, tsc, vitest). The pre-push hook
  gains the same checks when `video/` changed.

## 8. Rollout

1. Build on branch `feat/studio` (worktree `C:/PythonProjects/AncientMap-studio`), all gates green, adversarial review.
2. Push to main. The deploy applies 0025/0026 before the image rebuild. The api/lyra/ssr/frontend
   rebuild; theo-worker swaps only when idle. The run b26f8c69 finishes on the old code and
   auto-publishes. After the swap (`scripts/swap_theo_worker_when_idle.sh` if needed), queued runs
   produce dossiers.
3. Verify: the running API commit equals HEAD, the migrations are applied, a researched row appears
   after the next batch run, and the dossier artifacts are complete.
4. Acceptance:
   - (a) `theo_publish --dry-run` on a bundle built from an existing complete dossier (95fa3798) with
     a Claude-written test paper, **dry-run only** (existing papers are not rewritten now);
   - (b) the first new dossier after the swap is written, checked and published by Claude per
     `theo-write`;
   - (c) the Baalbek claim-5 slice is rendered end to end through the studio (Claude case file and
     script with a web-sourced fact check, because the old run has no archived texts).

## 9. Out of scope (recorded, not built)

- YouTube upload automation: an OAuth token is needed, and unverified projects force uploads private.
- Rewriting the 31 existing papers.
- Shorts derivation from the case file.
- Compliance items the owner will handle later (not enforced by code now): Mapbox video rights
  (§1.7/§2.8.1 of the Product Terms), quotation rules for copyrighted source pages, music licence
  provenance, and the Remotion licence headcount check before hiring.
- Setting DISCORD_WEBHOOK_URL (owner action).
- Music: the current bed (`video-assets/music/MA_JonathanCarlile_…wav`) is used, with the credit in the description.
