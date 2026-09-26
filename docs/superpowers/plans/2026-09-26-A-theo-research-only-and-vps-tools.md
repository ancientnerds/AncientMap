# Stream A: Theo research-only split and VPS publish tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Theo (MiniMax M3 on the VPS) stops after moderation, persists a complete, loudly-written dossier with archived full texts of every cited source and ends in status `researched`; the VPS gains the CLIs a local Claude session uses to export that dossier and to publish, correct and video-link Claude-written papers through one gated, journalled sequence.

**Architecture:** A new `DossierHandler` is the only listener on `ModeratorComplete`: it writes every dossier kind to `research_artifacts` with replace semantics, runs a bounded archive-completion step (`archive_completion.py`), writes the manifest last and emits `DossierReady`, the orchestrator's new done signal. The orchestrator runs the event cascade as a task beside its watch loop, so deadline, 30 s flush and external cancellation finally run. The M3 writing chain (paper, probative-image handler, fact check, presentation, hero pick, judge) and its prompts are deleted. `theo_publishing.py` holds the shared publish sequence (slug rule, gates, evidence-anchor matching, journal, IndexNow/Qdrant side effects); `theo_publish.py` and `theo_dossier.py` are the CLIs run via `ssh ancientnerds docker exec -i ancient_nerds_api python -m …`.

**Tech Stack:** Python 3.11 (ruff target py311), asyncio, SQLAlchemy 2 `text()` against PostgreSQL, httpx (+ `httpx.MockTransport` in tests), pypdf 6.19.0, pytest + pytest-asyncio (`asyncio_mode = "auto"`), FastAPI TestClient; React 18 + TypeScript + vitest for the two Theo UI files.

---

## Ground rules for the implementer (read once)

- Worktree: `C:/PythonProjects/AncientMap-studio` (branch `feat/studio`). Every command below runs from the worktree root. In Claude Code the cwd resets between calls, so prefix each command with `cd /c/PythonProjects/AncientMap-studio && `.
- Python is always `./.venv/Scripts/python.exe` (a symlink to the main checkout's venv). Single test files run with `-m "not integration and not live_llm" -q`.
- One-time setup before Task 6: `./.venv/Scripts/python.exe -m pip install pypdf==6.19.0` (CI installs it from `requirements-api.txt`; the local venv does not have it yet).
- Repo rules (CLAUDE.md): no fallback code, no `try/except` that returns empty; fail loudly. `pipeline` must not import `api`. Nothing Lyra imports may import `markdown`, `nh3` or `api` at module level. Tests never read `video-assets/`. vulture (min-confidence 80) flags unused imports and unused parameters; remove every import you orphan. Migrations are forward-only numbered files.
- Several implementers share this worktree. Commit only the files your task lists, always with explicit `git add <paths>` (or `git rm <paths>`), never `git add -A`/`.`. Commit messages are one English sentence describing the change, followed by the attribution line:

  ```bash
  git commit -m "<sentence>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
- After every Python task run ruff on the files you touched: `./.venv/Scripts/python.exe -m ruff format <files> && ./.venv/Scripts/python.exe -m ruff check --fix <files>` (`--fix` also settles import-block blank lines, which `ruff format` leaves alone). CI runs `ruff format --check`, the pre-push hook does not.

---

## File structure

### Created

| File | Responsibility |
|---|---|
| `docs/superpowers/plans/assets/writer-brief-editorial.md` | The editorial spec of the deleted `v2_paper_*.txt` prompts, ported for the Claude writer. Stream C copies it into `pipeline/studio/paper/brief_template.md`. (Pre-written during planning; Task 1 verifies and commits it.) |
| `pipeline/lyra/dossier_manifest.py` | Pure dossier shape: `DOSSIER_KINDS`, `moderated_source_ids`, `cited_source_ids`, `build_manifest`, `manifest_summary`. |
| `pipeline/lyra/archive_completion.py` | Fetch and archive the full text of every source a moderated claim cites (Wikipedia REST, doi redirects, PDF via pypdf, YouTube transcripts), bounded in time and concurrency, TDM-aware, per-source failures recorded. |
| `pipeline/lyra/handlers/dossier.py` | `DossierHandler`: persist dossier kinds (replace semantics), run archive completion, write manifest last, set `DONE`, emit `DossierReady`. Idempotent. Fails loudly. |
| `pipeline/lyra/theo_publishing.py` | Shared publish sequence: `normalize_anchor_text`, `report_paragraphs`, `resolve_evidence_anchors`, `make_slug`, `pick_slug`, the gates, `publish_paper`, `correct_paper`, `register_video`, `run_publish_side_effects`, `PublishOutcome`, error classes. |
| `pipeline/lyra/theo_publish.py` | CLI `python -m pipeline.lyra.theo_publish (--dry-run \| --apply \| --correct [--dry-run] \| --register-video [--dry-run]) < input.json`. |
| `pipeline/lyra/theo_dossier.py` | CLI `python -m pipeline.lyra.theo_dossier list` and `export <request_id> [--texts cited\|all]` (gzip JSON on stdout), incl. legacy runs without a manifest. |
| `migrations/0025_theo_paper_publications.sql` | Journal table `theo_paper_publications` + index `research_artifacts (request_id, kind, created_at DESC)`. |
| `tests/pipeline/theo_publish_fixtures.py` | Shared test fixtures: one paper that passes every gate, a fake session that behaves like the `research_requests` row. |
| `tests/pipeline/test_theo_publishing_anchors.py` | Anchor normalisation and resolution. |
| `tests/pipeline/test_training_corpus_nul.py` | NUL stripping of every corpus write. |
| `tests/pipeline/test_research_state_dossier.py` | `findings_by_specialist`, dossier fields, `MODERATING`, `DossierReady`, deadline phase. |
| `tests/pipeline/test_dossier_manifest.py` | Manifest helpers. |
| `tests/pipeline/test_training_corpus_dossier.py` | Replace semantics, returned ids, best archive rows, classification, monotonic `cited`. |
| `tests/pipeline/test_archive_completion.py` | Archive completion end to end with `httpx.MockTransport`. |
| `tests/pipeline/test_dossier_handler.py` | DossierHandler: order, idempotency, zero-claim failure, loud write failure. |
| `tests/pipeline/test_state_persist.py` | specialist_analyses fix, no `moderated` write, replace flag. |
| `tests/pipeline/test_orchestrator_cascade.py` | `_drive_cascade`: done signal, no-dossier error, ticks, cancellation, quota propagation, unwind grace. |
| `tests/pipeline/test_orchestrator_research_only.py` | Wiring ends at DossierHandler, `DossierReady` done signal, dossier guard, writing chain gone. |
| `tests/pipeline/test_probative_disabled_return.py` | `embed_probative_images` returns five parts when disabled. |
| `tests/pipeline/test_research_only_prompts.py` | Writing prompts and LLM repair/coherence calls are gone. |
| `tests/pipeline/test_theo_publishing_gates.py` | Slug rule and every gate. |
| `tests/pipeline/test_migration_0025.py` | Migration shape. |
| `tests/pipeline/test_theo_publishing_publish.py` | `publish_paper` and `run_publish_side_effects`. |
| `tests/pipeline/test_theo_publishing_corrections.py` | `correct_paper` and `register_video`. |
| `tests/pipeline/test_theo_publish_cli.py` | CLI modes, exit codes, bundle hashing. |
| `tests/pipeline/test_theo_dossier.py` | Export (manifest and legacy), list, CLI. |
| `tests/pipeline/test_tts_published_report.py` | TTS narrates `published_report`. |
| `tests/api/test_theo_worker_researched.py` | Worker researched branch, no auto-publish, feeder cap, pacing average. |
| `tests/api/test_theo_routes_researched.py` | Stream terminal set, DELETE of researched rows, shared slug rule. |
| `ancient-nerds-map/src/components/theo/__tests__/theoResearchLive.test.ts` | Live panel phases end at the dossier. |
| `ancient-nerds-map/src/pages/__tests__/theoStatusLabel.test.ts` | Owner-list status label for `researched`. |

### Modified

| File | Change |
|---|---|
| `pipeline/lyra/convergence_orchestrator.py` | Cascade as task (`_drive_cascade`), handler wiring without the writing chain, `DossierReady` done signal, dossier guard replaces empty-paper guard. |
| `pipeline/lyra/research_events.py` | + `DossierReady(request_id)`; − `PaperReady`, `ProbativeImagesReady`, `FactCheckComplete`, `PresentationChecked`, `ImageGenComplete`, `QualityPassed`, `QualityFailed`. |
| `pipeline/lyra/research_state.py` | + `MODERATING`, `dossier_ref`, `dossier_summary`, `findings_by_specialist()`; − `WRITING`, `IMAGE_CURATION`, `JUDGING`. |
| `pipeline/lyra/training_corpus.py` | NUL-safe writes; `save_artifact(..., replace=)` returns the id; `registry_payload` (renamed); `classify_archive_row`; `best_archive_rows[_in]`; `persist_run_corpus` without `citation_registry`, `cited` from moderated claims, monotonic. |
| `pipeline/lyra/handlers/state_persist.py` | specialist_analyses from the angles; no `moderated` write; replace semantics. |
| `pipeline/lyra/handlers/deadline.py` | Forced moderation sets `MODERATING` (not `WRITING`). |
| `pipeline/lyra/handlers/moderator.py` | Sets `MODERATING`; docstring. |
| `pipeline/lyra/handlers/content_fetch.py` | `fetch_domain_policy` and `domain_of` become module functions (reused by archive completion). |
| `pipeline/lyra/handlers/probative_images.py` | − `ProbativeImagesHandler` class and its imports; disabled branch returns five parts. |
| `pipeline/lyra/handlers/angle_image_research.py`, `pipeline/lyra/image_diversity.py` | Docstrings no longer name the deleted handler. |
| `pipeline/lyra/coherence_pass.py`, `pipeline/lyra/hallucination_gate.py` | − LLM calls `run_coherence_pass`, `repair_prose` (their prompts are deleted); deterministic parts stay. |
| `pipeline/lyra/tts_generator.py` | `report_for_audio()`: narrate `published_report`. |
| `api/services/theo_worker.py` | Success → `researched` with `{"dossier": …, "title": null}`; − `_auto_publish`, `_paper_artifact`; notification; corpus close-out without registry; pacing on research-only runs; feeder cap. |
| `api/services/theo_config.py` | `THEO_RUN_COST_PCT` (9), `THEO_RUN_EST_HOURS` (11), `THEO_MAX_UNWRITTEN_DOSSIERS` (6); − `THEO_PAPER_*`, `THEO_AUTO_PUBLISH_AUTHOR`. |
| `api/routes/theo.py` | Stream terminal set gains `researched`; publish route uses `pick_slug` + `run_publish_side_effects`; − `_make_slug`, `import re`. |
| `ancient-nerds-map/src/components/theo/TheoResearchLive.tsx` | Phases end MODERATE → DOSSIER; no WRITE/JUDGE, no paper/quality_judge stages, no quality flash; "DOSSIER READY". |
| `ancient-nerds-map/src/pages/TheoPage.tsx` | "Researched · awaiting write" label; notifications for researched/published. |
| `requirements-api.txt` | `pypdf==6.19.0`. |
| `tests/pipeline/test_training_corpus.py` | Registry rename; close-out marks moderated sources cited, writes no registry. |
| `tests/pipeline/test_coherence_pass.py`, `tests/pipeline/test_hallucination_gate.py` | − tests of the removed LLM calls. |
| `tests/api/test_theo_worker_quota.py` | Budget numbers for `THEO_RUN_COST_PCT = 9` and 11 h runs. |
| `tests/pipeline/test_hex_token_scrubber.py` | − `test_handler_uses_same_regex` (it reads the deleted `handlers/paper.py` from disk). |

### Deleted

`pipeline/lyra/handlers/paper.py`, `fact_check.py`, `presentation.py`, `image_generation.py`, `judge.py`; `pipeline/lyra/prompts/v2_paper_outline.txt`, `v2_paper_hook.txt`, `v2_paper_section.txt`, `v2_paper_connecting.txt`, `v2_paper_otherside.txt`, `v2_paper_assessment.txt`, `coherence_pass.txt`, `hallucination_repair.txt`; `tests/pipeline/test_paper_claim_pack.py`, `test_paper_repair_pass.py`, `test_paper_title_validation.py`, `test_empty_paper_guard.py`, `test_shining_ones_regen.py` (they only covered removed code).

Kept on purpose (used elsewhere or by the publish gate): `theo_citations`, `quality_gate`, deterministic `hallucination_gate`/`coherence_pass`, `hero_picker`, `theo_image_captions`, `image_fetcher`, `image_gates`, `image_diversity`, `embed_probative_images`/`_claim_image_content`/`_limit_tagged`, `illustration_specialist`, `citation_verifier`. The paper fields on `ResearchState` (`paper_text`, `paper_title`, …) stay: four scripts outside this stream read them (see Cross-stream requests).

---

## Contracts (other streams build on these; do not change them without telling streams B and C)

### C1. Dossier manifest — `research_artifacts` row `kind='dossier'`, `ref=''`

Written last by the DossierHandler; its presence means every other kind of the run is persisted.

```json
{
  "version": 1,
  "request_id": "95fa3798-1c2d-4e5f-8a9b-0c1d2e3f4a5b",
  "question": "Who cut the Baalbek monoliths, and how were they moved?",
  "created_at": "2026-09-28T09:14:03.512345+00:00",
  "angle_ids": ["3f9a0c1b", "77d2e4aa"],
  "counts": {"angles": 7, "findings": 2937, "sources": 3697, "final_claims": 38,
             "revised_claims": 5, "speculative_claims": 9, "images": 150},
  "kinds": ["moderated", "synthesis", "debate", "angle_findings", "specialist_analyses",
            "citation_registry", "image_candidate_pool"],
  "archive": {"cited_sources": 171, "full_text": 150, "abstract_only": 12, "missing": 6, "tdm_reserved": 3,
              "failures": [{"source_id": "a1b2c3d4e5f6", "url": "https://doi.org/10.1017/S0003598X00098264",
                            "reason": "HTTP 403 from https://www.cambridge.org/core/product/identifier/S0003598X00098264/type/journal_article"}],
              "duration_s": 812.4, "timed_out": false},
  "research": {"llm_calls": 399, "total_tokens": 12345678, "duration_s": 39600.0}
}
```

The other kinds (all `ref=''` except `angle_findings`, whose `ref` is the angle id): `moderated` = `state.moderated_result`; `synthesis` = `{"synthesis", "cross_angle_connections"}`; `debate` = `state.debate_result`; `angle_findings` = `asdict(ResearchAngle)`; `specialist_analyses` = `{"analyses": {specialist_id: [finding + "angle_id"]}, "panel": [asdict(ActiveSpecialist)]}`; `citation_registry` = `{"sources": [CitedSource without snippet + "snippet_chars"], "claims": [...], "reference_numbers": {}}`; `image_candidate_pool` = `{angle_id: [ImageCandidate dict]}`.

### C2. `research_requests` row after research

`status = 'researched'`, `completed_at`, counters, `duration_ms` as before, and

```json
{"dossier": {"artifact_id": 8812, "version": 1, "created_at": "2026-09-28T09:14:03.512345+00:00",
             "counts": {"angles": 7, "findings": 2937, "sources": 3697, "final_claims": 38,
                        "revised_claims": 5, "speculative_claims": 9, "images": 150},
             "archive": {"cited_sources": 171, "full_text": 150, "abstract_only": 12, "missing": 6, "tdm_reserved": 3}},
 "title": null}
```

### C3. Dossier export bundle — `python -m pipeline.lyra.theo_dossier export <id> [--texts cited|all]`

gzip (mtime 0) of UTF-8 JSON on stdout. Exit 0 ok, 1 no/incomplete dossier, 2 bad request id.

```json
{
  "version": 1,
  "texts_mode": "cited",
  "request": {"id": "95fa3798-…", "question": "…", "status": "researched", "is_batch": true,
              "user_id": "442000112756064260", "created_at": "2026-09-27T20:01:00", "completed_at": "2026-09-28T09:15:40"},
  "manifest": { "…C1, or the legacy manifest below…" },
  "moderated": {"final_claims": [{"claim": "…", "confidence": "high", "source_ids": ["a1b2c3d4e5f6"], "notes": "…"}],
                "revised_claims": [{"original": "…", "revised": "…", "reason": "…", "source_ids": ["…"]}],
                "speculative_claims": [{"claim": "…", "confidence": "low", "source_ids": ["…"], "notes": "…", "what_would_strengthen": "…"}],
                "dropped_claims": []},
  "synthesis": {"synthesis": {"consensus_claims": [], "contested_claims": [], "unique_insights": [], "open_questions": []},
                "cross_angle_connections": [{"from_angle": "3f9a0c1b", "to_angle": "77d2e4aa", "description": "…"}]},
  "debate": {"rounds": 4, "challenges": [], "defenses": []},
  "angles": [{"id": "3f9a0c1b", "topic": "…", "description": "…",
              "findings": [{"claim": "…", "evidence": "…", "source_ids": ["a1b2c3d4e5f6"], "confidence": "high", "specialist_id": "field_archaeologist"}]}],
  "sources": [{"id": "a1b2c3d4e5f6", "url": "https://…", "title": "…", "domain": "…", "reliability_tier": 1,
               "doi": "10.…", "authors": ["…"], "venue": "…", "date": "2014", "license": "", "source_api": "openalex",
               "archive": {"content_type": "text/html; charset=utf-8", "text_chars": 18234,
                           "fetched_at": "2026-09-28T09:05:11.123456+00:00", "tdm_opt_out": false}}],
  "texts": {"a1b2c3d4e5f6": "<full archived text>"},
  "images": {"3f9a0c1b": [{"url": "https://commons.wikimedia.org/wiki/File:…", "source": "wikimedia", "title": "…",
                            "description": "…", "artist": "…", "license": "CC BY-SA 4.0", "license_url": "…",
                            "thumbnail_url": "…", "metadata": {"width": 4000, "height": 3000}}]}
}
```

Rules: `sources` lists every registry source; `archive` is `null` when nothing is archived for it. `texts` holds only sources with a body that is not TDM-reserved. `--texts cited` = sources of moderated final/revised/speculative claims plus every source of an angle finding that shares a source with them; `--texts all` = every registry source. Legacy runs (no `dossier` row, e.g. 95fa3798) export too; their manifest is `{"version": 1, "legacy": true, "request_id", "question", "created_at": null, "angle_ids": [every angle_findings ref], "counts": {…}, "kinds": [kinds present], "archive": {counts…, "failures": [], "duration_s": 0.0, "timed_out": false}, "research": {"llm_calls", "total_tokens", "duration_s"}}` and `images` comes from the `paper_final` artifact's `image_candidate_pool`.

`python -m pipeline.lyra.theo_dossier list` prints a JSON array: `[{"id", "question", "status": "researched", "is_batch", "created_at", "completed_at", "dossier": <C2 summary>}]`, oldest first.

### C4. Publish bundle — `python -m pipeline.lyra.theo_publish --dry-run|--apply < bundle.json`

Top-level keys exactly `version`, `request_id`, `writer`, `result`.

```json
{
  "version": 1,
  "request_id": "95fa3798-1c2d-4e5f-8a9b-0c1d2e3f4a5b",
  "writer": {"model": "claude-opus-5-5", "tool": "claude-code", "research_model": "MiniMax-M3",
             "published": "automatic", "human_review": false},
  "result": {
    "title": "Roman Engineering at the Baalbek Quarry",
    "card_description": "The Baalbek monoliths were quarried and moved by Roman engineers; the paper tests the lost-civilization reading claim by claim and finds it unsupported.",
    "report": "# Roman Engineering at the Baalbek Quarry\n\nIn 2014 a team from the German Archaeological Institute …[1].\n\n## …\n\n## References\n\n[1] …",
    "published_report": "<identical to report>",
    "hero_image": {"src": "/data/research-images/95fa3798-…/hero_quarry.jpg", "web_path": "/data/research-images/95fa3798-…/hero_quarry.jpg",
                   "title": "…", "caption": "…", "sourceUrl": "https://commons.wikimedia.org/wiki/File:…",
                   "source_name": "Wikimedia Commons", "rationale": "…"},
    "published_hero_image": {"…identical to hero_image…": true},
    "probative_images": [{"title": "…", "artist": "…", "license": "CC BY-SA 4.0", "license_url": "…", "verified": true,
                          "web_path": "/data/research-images/95fa3798-…/p3_trilithon.jpg", "source_url": "…",
                          "source_name": "Wikimedia Commons", "description": "…", "rationale": "…",
                          "paragraph_text": "…", "paragraph_index": 3, "section_heading": "…"}],
    "published_block_ids": [],
    "quality_score": {"score": 94, "badge": "Claim-checked", "passed": true,
                      "metrics": {"citation_coverage": 15, "reference_integrity": 10, "section_completeness": 15,
                                  "source_diversity": 12, "research_depth": 14},
                      "meta": {"word_count": 6120, "total_sources": 41, "total_claims": 38, "claims_verified": 64,
                               "claims_checked": 64, "images_verified": 9},
                      "audit_gate_failures": {"audit_passed": true, "hallucination_final": 0, "high_contradictions": 0,
                                              "undefined_title_terms": 0}},
    "evidence": [{"id": "ev-01", "anchor_text": "In 2014 a team from the German Archaeological Institute",
                  "claim": "…", "source_ids": ["a1b2c3d4e5f6"], "quote": "…verbatim from the archived text…",
                  "quote_source_id": "a1b2c3d4e5f6", "verdict": "supported"}],
    "corrections": [],
    "audit": {"…optional; always recomputed and overwritten…": true}
  }
}
```

`result` keys allowed: the ones above; `audit` and `writer` optional (a `result.writer` must equal the top-level `writer`); nothing else. Image web paths must be `/data/research-images/<request_id>/<name>` with `<name>` matching `[A-Za-z0-9][A-Za-z0-9._-]*`, and the file must exist under the container's `/app/public/data/research-images/<request_id>/` (upload by scp before `--apply`).

### C5. Correction input — `python -m pipeline.lyra.theo_publish --correct [--dry-run] < correction.json`

Top-level keys `version`, `request_id`, `writer`, `corrections_append` (required) and `report`, `evidence` (optional).

```json
{"version": 1, "request_id": "95fa3798-…",
 "writer": {"model": "claude-opus-5-5", "tool": "claude-code", "research_model": "MiniMax-M3", "published": "automatic", "human_review": false},
 "report": "<full corrected markdown; report and published_report are both replaced>",
 "evidence": [{"id": "ev-01", "…": "…"}],
 "corrections_append": [{"date": "2026-10-02", "text": "Corrected the 2014 block's weight range.", "evidence_id": "ev-03"}]}
```

Every evidence id published before must stay in `evidence`, unless an entry of `corrections_append` names it (then it is retired); a retired id is never reused.

### C6. Video registration input — `python -m pipeline.lyra.theo_publish --register-video [--dry-run] < video.json`

Top-level keys exactly `version`, `request_id`, `writer`, `youtube_id`, `title`, `published_at`, `evidence_timestamps`.

```json
{"version": 1, "request_id": "95fa3798-…",
 "writer": {"model": "claude-opus-5-5", "tool": "claude-code", "research_model": "MiniMax-M3", "published": "automatic", "human_review": false},
 "youtube_id": "dQw4w9WgXcQ", "title": "Who Really Moved the Baalbek Stones?",
 "published_at": "2026-10-05T16:00:00+00:00",
 "evidence_timestamps": {"ev-01": 41, "ev-03": 312}}
```

### C7. `result_json` of a published paper (what stream B renders)

The C4 `result` plus: `"audit"` (recomputed), `"writer"` (C4 writer), `"dossier"` (C2 summary, carried over from the research row), later `"corrections": [{"date": "YYYY-MM-DD", "text": "…", "evidence_id": "ev-03"}]` (`evidence_id` optional) and `"videos": [{"youtube_id", "title", "published_at", "evidence_timestamps": {"ev-01": 41}, "registered_at": "<ISO UTC>"}]`. Table columns: `status='completed'`, `is_public=TRUE`, `published_by='Theo'`, `published_at`, `completed_at` (both NOW() at publish), `slug`.

### C8. `PublishOutcome` (stdout of every `theo_publish` mode)

```json
{"ok": true, "action": "publish", "request_id": "95fa3798-…", "dry_run": false,
 "slug": "roman-engineering-at-the-baalbek-quarry",
 "url": "https://ancientnerds.com/research/roman-engineering-at-the-baalbek-quarry",
 "gates": {"status": {"passed": true, "issues": [], "status": "researched", "is_public": false, "apply_allowed": true},
           "shape": {"passed": true, "issues": []},
           "snapshot": {"passed": true, "issues": []},
           "artifact": {"passed": true, "issues": []},
           "quality": {"passed": true, "issues": [], "stored_passed": true, "recomputed_passed": true},
           "evidence": {"passed": true, "issues": [], "resolved": {"ev-01": 0}},
           "images": {"passed": true, "issues": [], "checked": 10, "missing": [], "foreign": []}},
 "side_effects": {"indexnow": {"ok": true}, "qdrant": {"ok": true, "sections": 7}},
 "journal_id": 12}
```

`correct` has gates `status`, `shape`, `retention`, `artifact`, `quality` (recompute only), `evidence`, `images`; `register_video` has `status`, `shape`, `evidence_refs`, `duplicate`, and `side_effects` holds only `indexnow`. Dry runs never write: `journal_id` null, `side_effects` `{}`. A dry run of a publish on an already public row passes the status gate with `apply_allowed: false` (it answers "would this content pass"). Exit codes: 0 ok (side-effect failures are reported, not fatal), 1 a gate failed, 2 unusable input, 3 row changed between read and write (nothing committed), 4 committed but the re-read row differs.

### C9. Evidence-anchor matching rule (shared with stream B)

`from pipeline.lyra.theo_publishing import normalize_anchor_text`. An evidence entry anchors to the paragraph whose `normalize_anchor_text(<paragraph text>)` **starts with** `normalize_anchor_text(anchor_text)`. On the page, apply it to each `<p>`'s text content (tags removed, entities unescaped). A published entry always matched exactly one markdown prose paragraph (`report_paragraphs`), and its normalised anchor is at least `MIN_ANCHOR_CHARS` (20) long. Several entries may anchor to the same paragraph.

---

## Task 1: Commit the ported editorial spec

The M3 writing prompts are deleted in Task 12; their editorial spec must exist first. The file was written during planning.

**Files:**
- Create (verify + commit): `docs/superpowers/plans/assets/writer-brief-editorial.md`

- [ ] **Step 1: Verify the file is present and complete**

Run: `test -f docs/superpowers/plans/assets/writer-brief-editorial.md && grep -c "^## " docs/superpowers/plans/assets/writer-brief-editorial.md`
Expected: `9` (sections 1 Voice … 9 Evidence entries). If the file is missing, stop and ask the planner for it: it is the ported text of `pipeline/lyra/prompts/v2_paper_*.txt` and must not be re-invented.

- [ ] **Step 2: Check it names every rule stream C gates on**

Run: `grep -E "5,000 to 7,500 words|\[S:<source_id>\]|almost certain · very likely · likely · roughly even|Connecting the Dots|The Other Side|What We Actually Know|anchor_text" docs/superpowers/plans/assets/writer-brief-editorial.md | wc -l`
Expected: a number ≥ 7.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/assets/writer-brief-editorial.md
git commit -m "Port the editorial spec of Theo's M3 writing prompts into a writer brief for the Claude write" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 2: Evidence-anchor normalisation (`theo_publishing.py`, part 1)

Stream B imports `normalize_anchor_text`, so this lands first. The module starts small and grows in Tasks 15, 17 and 18.

**Files:**
- Create: `pipeline/lyra/theo_publishing.py`
- Create: `tests/pipeline/theo_publish_fixtures.py`
- Test: `tests/pipeline/test_theo_publishing_anchors.py`

- [ ] **Step 1: Write the shared fixtures module**

`tests/pipeline/theo_publish_fixtures.py` (not collected by pytest: its name does not start with `test_`):

```python
"""Shared fixtures for the Theo publish tests: one paper that passes every gate.

REPORT was checked against validate_paper_artifact (passed, no issues) and
recompute_quality_passed (True with QUALITY) when this plan was written.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

from tests.fake_sql import FakeResult, RecordingSession

REQ = "11111111-2222-3333-4444-555555555555"
OTHER_REQ = "99999999-8888-7777-6666-555555555555"
IMG_NAME = "p1_trilithon.jpg"
IMG = f"/data/research-images/{REQ}/{IMG_NAME}"
SOURCE_A = "a1b2c3d4e5f6"
SOURCE_B = "0f1e2d3c4b5a"

REPORT = f"""# The Baalbek Trilithon

In 2014 a team from the German Archaeological Institute measured a third monolith in the Baalbek quarry [1].

## The Quarry Blocks

The Stone of the Pregnant Woman weighs roughly 1,000 tonnes according to the institute survey [1]. A second block nearby is heavier still [2].

![Quarry block with a person for scale]({IMG})

*Quarry block with a person for scale* [Source](https://commons.wikimedia.org/wiki/File:Baalbek.jpg)

## Connecting the Dots

Both blocks were cut from the same limestone bed that supplied the temple podium [2].

## The Other Side

Roman engineers moved blocks of this size with capstans and ramps, as the survey notes [1].

## What We Actually Know

The quarry dates to the Roman period, which the excavation layers confirm [2].

## References

[1] Baalbek quarry survey — https://a.example/survey (accessed 2026-09-01) [Academic]
[2] Limestone beds of the Beqaa — https://a.example/beds (accessed 2026-09-01)
"""

WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}

QUALITY = {
    "score": 92,
    "badge": "Claim-checked",
    "passed": True,
    "metrics": {"citation_coverage": 15, "reference_integrity": 10},
    "meta": {"word_count": 120},
    "audit_gate_failures": {
        "audit_passed": True,
        "hallucination_final": 0,
        "high_contradictions": 0,
        "undefined_title_terms": 0,
    },
}

HERO = {
    "src": IMG,
    "web_path": IMG,
    "title": "Quarry block",
    "caption": "Quarry block with a person for scale",
    "sourceUrl": "https://commons.wikimedia.org/wiki/File:Baalbek.jpg",
    "source_name": "Wikimedia Commons",
    "rationale": "Shows the block with a person for scale",
}

EVIDENCE = [
    {
        "id": "ev-01",
        "anchor_text": "The Stone of the Pregnant Woman weighs roughly",
        "claim": "The Stone of the Pregnant Woman weighs about 1,000 tonnes.",
        "source_ids": [SOURCE_A],
        "quote": "weighs about 1,000 tonnes",
        "quote_source_id": SOURCE_A,
        "verdict": "supported",
    },
    {
        "id": "ev-02",
        "anchor_text": "The quarry dates to the Roman period",
        "claim": "The quarry is Roman.",
        "source_ids": [SOURCE_B],
        "quote": "Roman period",
        "quote_source_id": SOURCE_B,
        "verdict": "supported",
    },
]

DOSSIER_SUMMARY = {
    "artifact_id": 8,
    "version": 1,
    "created_at": "2026-09-28T09:00:00+00:00",
    "counts": {
        "angles": 2,
        "findings": 10,
        "sources": 40,
        "final_claims": 4,
        "revised_claims": 0,
        "speculative_claims": 1,
        "images": 12,
    },
    "archive": {
        "cited_sources": 6,
        "full_text": 5,
        "abstract_only": 1,
        "missing": 0,
        "tdm_reserved": 0,
    },
}


def make_result(**overrides) -> dict:
    """A publish-bundle `result` that passes every gate."""
    result = {
        "title": "The Baalbek Trilithon",
        "card_description": "The quarry blocks of Baalbek are Roman work, moved with capstans and ramps.",
        "report": REPORT,
        "published_report": REPORT,
        "hero_image": copy.deepcopy(HERO),
        "published_hero_image": copy.deepcopy(HERO),
        "probative_images": [
            {
                "title": "Quarry block",
                "web_path": IMG,
                "verified": True,
                "license": "CC BY-SA 4.0",
                "source_url": "https://commons.wikimedia.org/wiki/File:Baalbek.jpg",
            }
        ],
        "published_block_ids": [],
        "quality_score": copy.deepcopy(QUALITY),
        "evidence": copy.deepcopy(EVIDENCE),
        "corrections": [],
    }
    result.update(overrides)
    return result


def research_row(**overrides) -> SimpleNamespace:
    """The research_requests row as theo_publishing reads it (researched, not public)."""
    values = {
        "id": REQ,
        "status": "researched",
        "is_public": False,
        "slug": None,
        "question": "Who cut the Baalbek monoliths?",
        "user_id": "442000112756064260",
        "published_by": None,
        "published_at": None,
        "result_json": json.dumps({"dossier": DOSSIER_SUMMARY, "title": None}),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class PublishSession(RecordingSession):
    """A research_requests row that the publish writes change, as the database would."""

    def __init__(self, row, *, slug_taken=False, update_rowcount=1, tamper=False):
        super().__init__()
        self.row = row
        self.slug_taken = slug_taken
        self.update_rowcount = update_rowcount
        self.tamper = tamper
        self.written = None
        self.slug_after = row.slug

    def execute(self, stmt, params=None):
        super().execute(stmt, params)
        sql = stmt.text
        if "published_by, published_at, result_json" in sql:
            return FakeResult([self.row])
        if "SELECT 1 FROM research_requests WHERE slug" in sql:
            return FakeResult([object()] if self.slug_taken else [])
        if sql.lstrip().startswith("UPDATE research_requests"):
            self.written = params["result"]
            self.slug_after = params.get("slug", self.row.slug)
            return FakeResult([], rowcount=self.update_rowcount)
        if "INSERT INTO theo_paper_publications" in sql:
            return FakeResult([(42,)])
        if "SELECT status, is_public, slug, result_json" in sql:
            written = json.dumps({"tampered": True}) if self.tamper else self.written
            return FakeResult(
                [
                    SimpleNamespace(
                        status="completed",
                        is_public=True,
                        slug=self.slug_after,
                        result_json=written,
                    )
                ]
            )
        return FakeResult([])
```

- [ ] **Step 2: Write the failing anchor tests**

`tests/pipeline/test_theo_publishing_anchors.py`:

```python
"""Evidence anchors: one normalisation for the markdown here and the page's HTML (stream B)."""

from pipeline.lyra.theo_publishing import (
    MIN_ANCHOR_CHARS,
    normalize_anchor_text,
    report_paragraphs,
    resolve_evidence_anchors,
)
from tests.pipeline.theo_publish_fixtures import EVIDENCE, REPORT


def test_markdown_and_rendered_text_normalise_to_the_same_string():
    markdown = 'The **Stone** of the "Pregnant" Woman -- a [block](https://x.example) [1] weighs...'
    rendered = "The Stone of the “Pregnant” Woman – a block [1] weighs…"
    expected = 'the stone of the "pregnant" woman - a block weighs...'
    assert normalize_anchor_text(markdown) == expected
    assert normalize_anchor_text(rendered) == expected


def test_citation_and_draft_markers_disappear():
    assert (
        normalize_anchor_text("Dated to 9600 BC [S:1a2b3c4d5e6f] [2, 3] [4–6].")
        == "dated to 9600 bc ."
    )


def test_emphasis_underscores_go_but_snake_case_stays():
    assert (
        normalize_anchor_text("The _Kybalion_ cites the_all principle")
        == "the kybalion cites the_all principle"
    )


def test_report_paragraphs_are_prose_only():
    paragraphs = report_paragraphs(REPORT)
    assert len(paragraphs) == 5
    assert paragraphs[0].startswith("In 2014 a team")
    assert paragraphs[1].startswith("The Stone of the Pregnant Woman")
    assert all(not p.startswith(("#", "!", "*", "[1]")) for p in paragraphs)


def test_each_published_anchor_hits_exactly_one_paragraph():
    resolved, issues = resolve_evidence_anchors(REPORT, EVIDENCE)
    assert issues == []
    assert resolved == {"ev-01": 1, "ev-02": 4}


def test_ambiguous_missing_and_short_anchors_are_reported():
    report = (
        "# T\n\nRoman engineers moved blocks with capstans [1].\n\n"
        "Roman engineers moved blocks with ramps too [1].\n\n"
        "## References\n\n[1] A — https://a.example (accessed 2026-01-01)\n"
    )
    evidence = [
        {"id": "ev-01", "anchor_text": "Roman engineers moved blocks"},
        {"id": "ev-02", "anchor_text": "Greek engineers moved the blocks"},
        {"id": "ev-03", "anchor_text": "Roman"},
    ]
    resolved, issues = resolve_evidence_anchors(report, evidence)
    assert resolved == {}
    assert issues == [
        "ev-01: anchor_text matches 2 paragraphs (needs exactly 1)",
        "ev-02: anchor_text matches 0 paragraphs (needs exactly 1)",
        f"ev-03: anchor_text shorter than {MIN_ANCHOR_CHARS} characters after normalisation",
    ]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publishing_anchors.py -m "not integration and not live_llm" -q`
Expected: collection error `ModuleNotFoundError: No module named 'pipeline.lyra.theo_publishing'`.

- [ ] **Step 4: Create `pipeline/lyra/theo_publishing.py`**

```python
"""Shared publish sequence for Theo papers written in a Claude session (spec 2.6, 2.7).

Theo researches on the VPS and stops at a dossier (status 'researched'). A
Claude session writes, checks and publishes the paper through
`python -m pipeline.lyra.theo_publish` inside the API container; this module is
the sequence that CLI runs. It lives under pipeline/ so the CLI and
api/routes/theo.py (the manual founder route) share one slug rule and one
side-effect sequence: pipeline must not import api.

Nothing here repairs a paper. Every gate either passes or reports what is wrong;
the local check (pipeline/studio/paper) is the only place a paper gets fixed.

Module-level imports stay light (no pipeline.indexnow, no DB models): stream B's
paper renderer imports normalize_anchor_text from here.
"""

from __future__ import annotations

import re
import unicodedata

from pipeline.lyra.theo_citations import (
    _is_non_prose_block,
    _split_prose_into_paragraphs,
    split_artifact,
)

# ---------------------------------------------------------------------------
# Evidence anchors (contract C9, shared with the paper page)
# ---------------------------------------------------------------------------

#: An evidence id: "ev-" plus at least two digits ("ev-03", "ev-117").
EVIDENCE_ID_RE = re.compile(r"^ev-\d{2,}$")

#: Shortest normalised anchor text accepted. Shorter openings ("The site")
#: match many paragraphs and say nothing about which one is meant.
MIN_ANCHOR_CHARS = 20

_TYPOGRAPHY = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "–": "-",
        "—": "-",
        "−": "-",
    }
)
_MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_CITATION_MARKER_RE = re.compile(r"\[(?:\d+(?:\s*[,-]\s*\d+)*|S:[^\]\s]+)\]")
_DASH_RUN_RE = re.compile(r"-{2,}")
_EDGE_UNDERSCORE_RE = re.compile(r"(?<!\w)_+|_+(?!\w)")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_anchor_text(text: str) -> str:
    """Fold paragraph text so markdown source and rendered HTML text compare equal.

    The matching rule shared with the paper page: an evidence entry anchors to
    the paragraph whose normalised text STARTS WITH its normalised anchor_text.
    Apply this to the markdown paragraph here and to the paragraph's text
    content (tags stripped, entities unescaped) on the page.

    Steps, in order: Unicode NFKC (an ellipsis becomes "...", a no-break space a
    space); curly quotes to straight ones, en/em dash and minus to "-"; markdown
    links and images to their text; citation markers [N], [N, M], [N-M] and
    draft markers [S:<id>] removed; runs of "-" folded to one ("--" is what the
    renderer turns into an en dash); emphasis markers * and ` removed, _ removed
    at word edges; whitespace folded to single spaces; stripped; lower-cased.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHY)
    folded = _MD_LINK_RE.sub(r"\1", folded)
    folded = _CITATION_MARKER_RE.sub(" ", folded)
    folded = _DASH_RUN_RE.sub("-", folded)
    folded = folded.replace("*", "").replace("`", "")
    folded = _EDGE_UNDERSCORE_RE.sub("", folded)
    return _WHITESPACE_RE.sub(" ", folded).strip().lower()


def report_paragraphs(report: str) -> list[str]:
    """The prose paragraphs of a paper, in reading order.

    Blocks are split on a blank line, as the artifact gate splits them
    (theo_citations). Headings, image blocks, italic captions, [Source]( trailers
    and lone links are not paragraphs; nothing from the References heading on is.
    """
    prose, _heading, _refs = split_artifact(report.replace("\r\n", "\n"))
    return [
        block
        for _section, block in _split_prose_into_paragraphs(prose)
        if not _is_non_prose_block(block)
    ]


def resolve_evidence_anchors(
    report: str, evidence: list[dict]
) -> tuple[dict[str, int], list[str]]:
    """Map each evidence id to the index (in report_paragraphs) of the paragraph it anchors to.

    Returns (resolved, issues). An entry resolves only when exactly one
    paragraph's normalised text starts with its normalised anchor_text. Entries
    must already carry string `id` and `anchor_text` (check_evidence validates
    the shape first).
    """
    normalized = [normalize_anchor_text(p) for p in report_paragraphs(report)]
    resolved: dict[str, int] = {}
    issues: list[str] = []
    for entry in evidence:
        ev_id = entry["id"]
        anchor = normalize_anchor_text(entry["anchor_text"])
        if len(anchor) < MIN_ANCHOR_CHARS:
            issues.append(
                f"{ev_id}: anchor_text shorter than {MIN_ANCHOR_CHARS} characters after normalisation"
            )
            continue
        hits = [index for index, para in enumerate(normalized) if para.startswith(anchor)]
        if len(hits) != 1:
            issues.append(f"{ev_id}: anchor_text matches {len(hits)} paragraphs (needs exactly 1)")
            continue
        resolved[ev_id] = hits[0]
    return resolved, issues
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publishing_anchors.py -m "not integration and not live_llm" -q`
Expected: `6 passed`.

- [ ] **Step 6: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/theo_publishing.py tests/pipeline/theo_publish_fixtures.py tests/pipeline/test_theo_publishing_anchors.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/theo_publishing.py tests/pipeline/theo_publish_fixtures.py tests/pipeline/test_theo_publishing_anchors.py
git add pipeline/lyra/theo_publishing.py tests/pipeline/theo_publish_fixtures.py tests/pipeline/test_theo_publishing_anchors.py
git commit -m "Define the evidence-anchor normalisation that the publish gate and the paper page share" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 3: NUL-safe training-corpus writes

**Files:**
- Modify: `pipeline/lyra/training_corpus.py` (`archive_documents` 174-240, `save_artifact` 334-353, `record_run_links` 377-395)
- Test: `tests/pipeline/test_training_corpus_nul.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_training_corpus_nul.py`:

```python
"""NUL characters never reach PostgreSQL from the training corpus (2026-09-26).

PostgreSQL refuses U+0000 in TEXT and in JSONB. One NUL in one fetched page cost
runs aae36b9c and 23336ade their citation registry and every source link:
'A string literal cannot contain NUL (0x00) characters'.
"""

import hashlib
import json

from pipeline.lyra import training_corpus as tc


class _Result:
    def __init__(self) -> None:
        self.rowcount = 1

    def scalar_one(self) -> int:
        return 7


class _CaptureSession:
    """Keeps every (sql, params) pair, including executemany parameter lists."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.calls.append((stmt.text, params))
        return _Result()

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def _capture(monkeypatch) -> _CaptureSession:
    session = _CaptureSession()
    monkeypatch.setattr(tc, "_session_factory", lambda: session)
    return session


def test_strip_nul_walks_nested_payloads():
    payload = {"a\x00": ["x\x00y", {"z": "\x00"}], "n": 3, "t": ("p\x00",)}
    assert tc._strip_nul(payload) == {"a": ["xy", {"z": ""}], "n": 3, "t": ["p"]}


def test_archived_document_loses_its_nul_bytes(monkeypatch):
    session = _capture(monkeypatch)
    doc = tc.ArchiveDocument(
        source_id="a1b2c3d4e5f6",
        url="https://x.example/\x00p",
        title="Ti\x00tle",
        full_text="he\x00llo",
        authors=["Wool\x00ley"],
        venue="Anti\x00quity",
    )
    tc.archive_documents([doc])
    ((_sql, params),) = session.calls
    row = params[0]
    assert row["full_text"] == "hello"
    assert row["title"] == "Title"
    assert row["url"] == "https://x.example/p"
    assert row["venue"] == "Antiquity"
    assert json.loads(row["authors"]) == ["Woolley"]
    assert row["content_hash"] == hashlib.sha256(b"hello").hexdigest()


def test_artifact_payload_is_nul_free_json(monkeypatch):
    session = _capture(monkeypatch)
    tc.save_artifact("req-1", "moderated", {"final_claims": [{"claim": "Ba\x00albek"}]}, "r\x00ef")
    _sql, params = session.calls[-1]
    assert "\\u0000" not in params["payload"]
    assert json.loads(params["payload"]) == {"final_claims": [{"claim": "Baalbek"}]}
    assert params["ref"] == "ref"


def test_run_links_are_nul_free(monkeypatch):
    session = _capture(monkeypatch)
    tc.record_run_links(
        "req-1",
        [{"source_id": "a1b2c3d4e5f6", "angle_id": "a\x001", "search_query": "ur\x00 pottery", "cited": False}],
    )
    ((_sql, params),) = session.calls
    assert params[0]["search_query"] == "ur pottery"
    assert params[0]["angle_id"] == "a1"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_training_corpus_nul.py -m "not integration and not live_llm" -q`
Expected: `4 failed` (`AttributeError: module ... has no attribute '_strip_nul'` and NUL assertions).

- [ ] **Step 3: Implement**

In `pipeline/lyra/training_corpus.py`, add after `SNIPPET_CONTENT_TYPE = "adapter/snippet"`:

```python
def _strip_nul(value: Any) -> Any:
    """Remove NUL characters from every string in value, recursively through dicts and lists.

    PostgreSQL rejects U+0000 in TEXT and in JSONB (json.dumps writes it as
    \\u0000, which jsonb refuses). One NUL in one fetched page killed a whole
    content_fetch wave and the run close-out of 2 of 5 production runs
    (aae36b9c, 23336ade). Tuples come back as lists, which JSON treats the same.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {_strip_nul(key): _strip_nul(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strip_nul(item) for item in value]
    return value


def _json_default(value: Any) -> str:
    """json.dumps fallback for non-JSON values (datetimes, enums): their str(), NUL-free."""
    return _strip_nul(str(value))
```

In `archive_documents`, replace the loop body that builds `params` so it works on a NUL-free copy of each document:

```python
    params: list[dict[str, Any]] = []
    for original in documents:
        doc = ArchiveDocument(**_strip_nul(asdict(original)))
        body = doc.full_text[:MAX_TEXT_CHARS]
        # A reservation row records that we looked and were told not to keep
        # the text — the finding itself is the point, so it is stored without
        # a body.
        if doc.tdm_opt_out:
            body = ""
        html_gz = None
        if body and doc.raw_html:
            html_gz = gzip.compress(doc.raw_html[:MAX_HTML_CHARS].encode("utf-8", "replace"))
        params.append(
            {
                "source_id": doc.source_id,
                "content_hash": hashlib.sha256(body.encode()).hexdigest() if body else "",
                "url": doc.url,
                "domain": doc.domain,
                "title": doc.title[:2000],
                "full_text": body or None,
                "raw_html_gz": html_gz,
                "text_chars": len(body),
                "http_status": doc.http_status,
                "content_type": doc.content_type,
                "archive_only": doc.archive_only,
                "source_api": doc.source_api,
                "doi": doc.doi,
                "authors": json.dumps(doc.authors) if doc.authors else None,
                "venue": doc.venue[:500],
                "reliability_tier": doc.reliability_tier,
                "license": doc.license,
                "license_source": doc.license_source,
                "tdm_opt_out": doc.tdm_opt_out,
                "tdm_signal": doc.tdm_signal,
                "tdm_checked": bool(doc.tdm_signal) or doc.tdm_opt_out,
            }
        )
```

In `save_artifact`, change the parameter dict to:

```python
            {
                "request_id": request_id or None,
                "kind": kind,
                "ref": _strip_nul(ref)[:200],
                "payload": json.dumps(_strip_nul(payload), default=_json_default),
            },
```

In `record_run_links`, change the parameter list to:

```python
            [{"request_id": request_id, **_strip_nul(link)} for link in links],
```

- [ ] **Step 4: Run the new and the existing corpus tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_training_corpus_nul.py tests/pipeline/test_training_corpus.py tests/pipeline/test_content_fetch_archive.py -m "not integration and not live_llm" -q`
Expected: all pass (`4` new + the existing 18 + 6).

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/training_corpus.py tests/pipeline/test_training_corpus_nul.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/training_corpus.py tests/pipeline/test_training_corpus_nul.py
git add pipeline/lyra/training_corpus.py tests/pipeline/test_training_corpus_nul.py
git commit -m "Strip NUL characters from every training-corpus write so one page can no longer lose a run's archive" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 4: Dossier state, `DossierReady`, manifest helpers, `MODERATING` phase

**Files:**
- Modify: `pipeline/lyra/research_state.py` (enum lines 27-35, fields after line 144, new function at the end)
- Modify: `pipeline/lyra/research_events.py` (after `ModeratorComplete`, line 92)
- Modify: `pipeline/lyra/handlers/deadline.py` (lines 55-60)
- Modify: `pipeline/lyra/handlers/moderator.py` (docstring + start of `_on_debate_complete`)
- Create: `pipeline/lyra/dossier_manifest.py`
- Test: `tests/pipeline/test_research_state_dossier.py`, `tests/pipeline/test_dossier_manifest.py`

- [ ] **Step 1: Write the failing state/event tests**

`tests/pipeline/test_research_state_dossier.py`:

```python
"""Research-only state: the dossier fields, MODERATING, DossierReady, findings by specialist."""

import asyncio
from datetime import UTC, datetime, timedelta

from pipeline.lyra.handlers.deadline import DeadlineHandler
from pipeline.lyra.research_events import DebateComplete, DossierReady, EventBus
from pipeline.lyra.research_state import (
    ResearchAngle,
    ResearchPhase,
    ResearchState,
    findings_by_specialist,
)


def test_findings_grouped_by_specialist_keep_their_angle():
    angles = [
        ResearchAngle(
            id="a1",
            topic="Quarry",
            description="d",
            findings=[{"claim": "c1", "specialist_id": "geo"}, {"claim": "c2"}],
        ),
        ResearchAngle(
            id="a2", topic="Temple", description="d", findings=[{"claim": "c3", "specialist_id": "geo"}]
        ),
    ]
    assert findings_by_specialist(angles) == {
        "geo": [
            {"claim": "c1", "specialist_id": "geo", "angle_id": "a1"},
            {"claim": "c3", "specialist_id": "geo", "angle_id": "a2"},
        ],
        "unknown": [{"claim": "c2", "angle_id": "a1"}],
    }


def test_state_starts_without_a_dossier():
    state = ResearchState(question="q")
    assert state.dossier_ref is None
    assert state.dossier_summary == {}


def test_moderating_phase_exists():
    assert ResearchPhase.MODERATING.value == "moderating"


def test_dossier_ready_carries_the_request():
    assert DossierReady(request_id="r1").request_id == "r1"


async def test_imminent_deadline_forces_moderation_once():
    state = ResearchState(question="q")
    state.phase = ResearchPhase.DEBATING
    state.deadline = datetime.now(UTC) + timedelta(minutes=30)
    bus = EventBus(state=state)
    fired: list[ResearchPhase] = []

    async def on_debate_complete(event: DebateComplete):
        fired.append(state.phase)

    bus.on(DebateComplete, on_debate_complete)
    handler = DeadlineHandler(state, bus, asyncio.Semaphore(1))

    assert await handler.check_deadline() is True
    assert fired == [ResearchPhase.MODERATING]
    # MODERATING is outside (SYNTHESIZING, DEBATING): the next tick forces nothing.
    assert await handler.check_deadline() is False
    assert fired == [ResearchPhase.MODERATING]
```

- [ ] **Step 2: Write the failing manifest tests**

`tests/pipeline/test_dossier_manifest.py`:

```python
"""The dossier's shape: cited sources, the manifest, the result_json summary."""

from datetime import UTC, datetime, timedelta

from pipeline.lyra.dossier_manifest import (
    DOSSIER_KINDS,
    build_manifest,
    cited_source_ids,
    manifest_summary,
    moderated_source_ids,
)
from pipeline.lyra.research_state import ResearchAngle, ResearchState

MODERATED = {
    "final_claims": [{"claim": "f1", "source_ids": ["s1", "s2"]}],
    "revised_claims": [{"original": "o", "revised": "r", "source_ids": ["s2", "s3"]}],
    "speculative_claims": [{"claim": "sp", "source_ids": ["s4"]}],
    "dropped_claims": [{"claim": "d", "source_ids": ["s9"]}],
}

ARCHIVE = {
    "cited_sources": 4,
    "full_text": 3,
    "abstract_only": 1,
    "missing": 0,
    "tdm_reserved": 0,
    "failures": [],
    "duration_s": 1.0,
    "timed_out": False,
}


def test_moderated_sources_in_first_seen_order_without_dropped_claims():
    assert moderated_source_ids(MODERATED) == ["s1", "s2", "s3", "s4"]


def test_cited_sources_add_findings_that_share_a_source():
    angles = [
        {"id": "a1", "findings": [{"source_ids": ["s1", "s7"]}, {"source_ids": ["s8"]}]},
        {"id": "a2", "findings": [{"source_ids": ["s4", "s5"]}]},
    ]
    assert cited_source_ids(MODERATED, angles) == ["s1", "s2", "s3", "s4", "s7", "s5"]


def _state() -> ResearchState:
    state = ResearchState(question="Who cut the Baalbek monoliths?", request_id="req-1")
    state.started_at = datetime(2026, 9, 26, 0, 0, tzinfo=UTC)
    state.registry.register_source(url="https://a.example/1", title="A", snippet="x")
    state.registry.register_source(url="https://a.example/2", title="B", snippet="y")
    state.angles = [
        ResearchAngle(id="a1", topic="Quarry", description="d", findings=[{"claim": "c"}, {"claim": "d"}])
    ]
    state.moderated_result = MODERATED
    state.image_candidate_pool = {"a1": [{"url": "u1"}, {"url": "u2"}]}
    state.llm_call_count = 10
    state.total_tokens = 500
    return state


def test_manifest_counts_everything_the_writer_gets():
    created = datetime(2026, 9, 26, 1, 0, tzinfo=UTC)
    manifest = build_manifest(_state(), ARCHIVE, created_at=created)
    assert manifest == {
        "version": 1,
        "request_id": "req-1",
        "question": "Who cut the Baalbek monoliths?",
        "created_at": "2026-09-26T01:00:00+00:00",
        "angle_ids": ["a1"],
        "counts": {
            "angles": 1,
            "findings": 2,
            "sources": 2,
            "final_claims": 1,
            "revised_claims": 1,
            "speculative_claims": 1,
            "images": 2,
        },
        "kinds": list(DOSSIER_KINDS),
        "archive": ARCHIVE,
        "research": {"llm_calls": 10, "total_tokens": 500, "duration_s": 3600.0},
    }


def test_summary_is_what_result_json_carries():
    manifest = build_manifest(_state(), ARCHIVE, created_at=datetime.now(UTC) + timedelta(hours=1))
    summary = manifest_summary(manifest, 8812)
    assert summary["artifact_id"] == 8812
    assert summary["version"] == 1
    assert summary["counts"] == manifest["counts"]
    assert summary["archive"] == {
        "cited_sources": 4,
        "full_text": 3,
        "abstract_only": 1,
        "missing": 0,
        "tdm_reserved": 0,
    }
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_research_state_dossier.py tests/pipeline/test_dossier_manifest.py -m "not integration and not live_llm" -q`
Expected: collection errors (`ImportError: cannot import name 'findings_by_specialist'`, `DossierReady`, `No module named 'pipeline.lyra.dossier_manifest'`).

- [ ] **Step 4: Extend `research_state.py`**

Add `MODERATING` to the enum (the three writing phases are removed in Task 10):

```python
class ResearchPhase(enum.Enum):
    DECOMPOSING = "decomposing"
    EXPLORING = "exploring"
    SYNTHESIZING = "synthesizing"
    DEBATING = "debating"
    MODERATING = "moderating"
    WRITING = "writing"
    IMAGE_CURATION = "image_curation"
    JUDGING = "judging"
    DONE = "done"
```

After `moderated_result: dict = field(default_factory=dict)` add:

```python
    # Dossier (handlers/dossier.py). dossier_ref is the research_artifacts.id of
    # the manifest row, set only once the whole dossier is persisted; the
    # orchestrator's dossier guard fails a run that ends without it.
    # dossier_summary is what the worker stores as result_json["dossier"].
    dossier_ref: int | None = None
    dossier_summary: dict = field(default_factory=dict)
```

At the end of the module add:

```python
def findings_by_specialist(angles: list[ResearchAngle]) -> dict[str, list[dict]]:
    """Every finding of every angle, grouped by the specialist that produced it.

    Each finding is copied with its angle id added, so the grouping keeps the
    context the per-angle lists had. Findings without a specialist_id group
    under "unknown".
    """
    grouped: dict[str, list[dict]] = {}
    for angle in angles:
        for finding in angle.findings:
            grouped.setdefault(finding.get("specialist_id", "unknown"), []).append(
                {**finding, "angle_id": angle.id}
            )
    return grouped
```

- [ ] **Step 5: Add `DossierReady` to `research_events.py`**

Directly after the `ModeratorComplete` class:

```python
@dataclass
class DossierReady(ResearchEvent):
    """The dossier is persisted and the run is done (handlers/dossier.py).

    The orchestrator's done signal since the research-only split (2026-09-26);
    QualityPassed held that role while Theo still wrote papers.
    """

    request_id: str
```

- [ ] **Step 6: Make the forced deadline path moderate, not write**

In `pipeline/lyra/handlers/deadline.py` replace:

```python
            # Less than 1 hour --- skip to writing and emit DebateComplete to trigger paper
            self.state.log(
                "deadline",
                f"Deadline imminent ({hours_left:.1f}h left) --- forcing paper assembly",
            )
            self.state.phase = ResearchPhase.WRITING
            await self.bus.emit(DebateComplete())
```

with:

```python
            # Less than 1 hour --- skip to moderation: DebateComplete triggers the
            # moderator, whose ModeratorComplete makes the DossierHandler end the run.
            # MODERATING is outside (SYNTHESIZING, DEBATING), so the next tick does
            # not force it again.
            self.state.log(
                "deadline",
                f"Deadline imminent ({hours_left:.1f}h left) --- forcing moderation and the dossier",
            )
            self.state.phase = ResearchPhase.MODERATING
            await self.bus.emit(DebateComplete())
```

- [ ] **Step 7: Let the moderator mark its phase**

In `pipeline/lyra/handlers/moderator.py` replace the module docstring with:

```python
"""Moderator handler -- reviews claims from synthesis + debate, drops weak
claims, revises contested claims, and produces the filtered claim set the
dossier (handlers/dossier.py) hands to the Claude writer."""
```

add `from pipeline.lyra.research_state import ResearchPhase` to its imports, and make the first line of `_on_debate_complete`:

```python
        self.state.phase = ResearchPhase.MODERATING
```

- [ ] **Step 8: Create `pipeline/lyra/dossier_manifest.py`**

```python
"""The dossier's shape (spec 2.2): cited sources, the manifest, the result_json summary.

Pure functions over plain data (dicts and duck-typed state), so the
DossierHandler, the worker, the run close-out and the export CLI share one
definition. Imports nothing from pipeline.lyra, so training_corpus may import it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

DOSSIER_VERSION = 1

#: research_artifacts kinds the DossierHandler writes before the manifest.
DOSSIER_KINDS: tuple[str, ...] = (
    "moderated",
    "synthesis",
    "debate",
    "angle_findings",
    "specialist_analyses",
    "citation_registry",
    "image_candidate_pool",
)

#: The claim lists of state.moderated_result that the paper may cite.
#: dropped_claims are out: the moderator rejected them.
MODERATED_CLAIM_LISTS: tuple[str, ...] = ("final_claims", "revised_claims", "speculative_claims")

#: The archive counters result_json["dossier"] carries (the failures stay in the manifest).
ARCHIVE_COUNT_KEYS: tuple[str, ...] = (
    "cited_sources",
    "full_text",
    "abstract_only",
    "missing",
    "tdm_reserved",
)


def moderated_source_ids(moderated: dict) -> list[str]:
    """Every source id a final, revised or speculative claim cites; first-seen order, no duplicates."""
    seen: dict[str, None] = {}
    for key in MODERATED_CLAIM_LISTS:
        for claim in moderated.get(key) or []:
            for source_id in claim.get("source_ids") or []:
                seen.setdefault(source_id, None)
    return list(seen)


def cited_source_ids(moderated: dict, angles: list[dict]) -> list[str]:
    """Sources whose text the default export ships (`--texts cited`, spec 2.8).

    The moderated claims' sources, plus every source of an angle finding that
    shares at least one source with them: those findings are the evidence behind
    the moderated claims (the moderator carries no quotes of its own).
    """
    core = moderated_source_ids(moderated)
    core_set = set(core)
    seen: dict[str, None] = dict.fromkeys(core)
    for angle in angles:
        for finding in angle.get("findings") or []:
            source_ids = finding.get("source_ids") or []
            if core_set.intersection(source_ids):
                for source_id in source_ids:
                    seen.setdefault(source_id, None)
    return list(seen)


def build_manifest(state: Any, archive: dict, *, created_at: datetime) -> dict:
    """The 'dossier' artifact (contract C1). Written last: its presence means the dossier is complete."""
    moderated = state.moderated_result
    return {
        "version": DOSSIER_VERSION,
        "request_id": state.request_id,
        "question": state.question,
        "created_at": created_at.isoformat(),
        "angle_ids": [angle.id for angle in state.angles],
        "counts": {
            "angles": len(state.angles),
            "findings": sum(len(angle.findings) for angle in state.angles),
            "sources": len(state.registry.sources),
            "final_claims": len(moderated.get("final_claims") or []),
            "revised_claims": len(moderated.get("revised_claims") or []),
            "speculative_claims": len(moderated.get("speculative_claims") or []),
            "images": sum(len(pool) for pool in state.image_candidate_pool.values()),
        },
        "kinds": list(DOSSIER_KINDS),
        "archive": archive,
        "research": {
            "llm_calls": state.llm_call_count,
            "total_tokens": state.total_tokens,
            "duration_s": round((created_at - state.started_at).total_seconds(), 1),
        },
    }


def manifest_summary(manifest: dict, artifact_id: int) -> dict:
    """What research_requests.result_json["dossier"] carries (contract C2)."""
    return {
        "artifact_id": artifact_id,
        "version": manifest["version"],
        "created_at": manifest["created_at"],
        "counts": dict(manifest["counts"]),
        "archive": {key: manifest["archive"][key] for key in ARCHIVE_COUNT_KEYS},
    }
```

- [ ] **Step 9: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_research_state_dossier.py tests/pipeline/test_dossier_manifest.py tests/pipeline/test_research_events_quota.py -m "not integration and not live_llm" -q`
Expected: all pass (`5` + `4` + the existing 3).

- [ ] **Step 10: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/research_state.py pipeline/lyra/research_events.py pipeline/lyra/handlers/deadline.py pipeline/lyra/handlers/moderator.py pipeline/lyra/dossier_manifest.py tests/pipeline/test_research_state_dossier.py tests/pipeline/test_dossier_manifest.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/research_state.py pipeline/lyra/research_events.py pipeline/lyra/handlers/deadline.py pipeline/lyra/handlers/moderator.py pipeline/lyra/dossier_manifest.py tests/pipeline/test_research_state_dossier.py tests/pipeline/test_dossier_manifest.py
git add pipeline/lyra/research_state.py pipeline/lyra/research_events.py pipeline/lyra/handlers/deadline.py pipeline/lyra/handlers/moderator.py pipeline/lyra/dossier_manifest.py tests/pipeline/test_research_state_dossier.py tests/pipeline/test_dossier_manifest.py
git commit -m "Give a Theo run a dossier: state fields, the DossierReady event, a moderating phase and the manifest shape" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 5: Replace semantics, best archive rows and a close-out without the registry

**Files:**
- Modify: `pipeline/lyra/training_corpus.py`
- Modify: `tests/pipeline/test_training_corpus.py` (registry rename, close-out test)
- Test: `tests/pipeline/test_training_corpus_dossier.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_training_corpus_dossier.py`:

```python
"""Corpus writes the dossier relies on: replace semantics, ids, best archive rows."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from pipeline.lyra import training_corpus as tc
from tests.fake_sql import RecordingSession


class _Result:
    def __init__(self) -> None:
        self.rowcount = 1

    def scalar_one(self) -> int:
        return 7


class _CaptureSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.calls.append((stmt.text, params))
        return _Result()

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


@pytest.fixture
def session(monkeypatch) -> _CaptureSession:
    capture = _CaptureSession()
    monkeypatch.setattr(tc, "_session_factory", lambda: capture)
    return capture


def test_replace_deletes_the_current_row_first_in_one_transaction(session):
    artifact_id = tc.save_artifact("req-1", "dossier", {"version": 1}, "", replace=True)
    (delete_sql, delete_params), (insert_sql, _insert_params) = session.calls
    assert delete_sql.strip().startswith("DELETE FROM research_artifacts")
    assert delete_params == {"request_id": "req-1", "kind": "dossier", "ref": ""}
    assert "RETURNING id" in insert_sql
    assert session.commits == 1
    assert artifact_id == 7


def test_plain_save_appends_and_returns_the_id(session):
    assert tc.save_artifact(None, "curator_output", {"x": 1}, "2026-09-26") == 7
    ((insert_sql, _params),) = session.calls
    assert insert_sql.strip().startswith("INSERT INTO research_artifacts")


def test_replace_needs_a_run_identity():
    with pytest.raises(ValueError, match="needs a request_id"):
        tc.save_artifact(None, "moderated", {}, replace=True)


def test_run_links_never_downgrade_cited(session):
    tc.record_run_links("req-1", [{"source_id": "a1b2c3d4e5f6", "angle_id": "", "search_query": "", "cited": False}])
    sql, _params = session.calls[0]
    assert "cited = theo_source_archive_runs.cited OR EXCLUDED.cited" in sql


def _row(source_id, content_type, text_chars, tdm=False, full_text=None):
    return SimpleNamespace(
        source_id=source_id,
        url=f"https://x.example/{source_id}",
        content_type=content_type,
        text_chars=text_chars,
        fetched_at=datetime(2026, 9, 28, tzinfo=UTC),
        tdm_opt_out=tdm,
        full_text=full_text,
    )


def test_best_archive_rows_ask_for_one_row_per_source_full_text_first():
    session = RecordingSession(
        {"FROM theo_source_archive": [_row("s1", "text/html", 900, full_text="body")]}
    )
    rows = tc.best_archive_rows_in(session, ["s1", "s1", "s2"], with_text=True)
    sql, params = session.log[0]
    assert "DISTINCT ON (source_id)" in sql
    assert "WHEN tdm_opt_out THEN 1" in sql
    assert "full_text" in sql
    assert params["ids"] == ["s1", "s2"]
    assert rows == {
        "s1": {
            "source_id": "s1",
            "url": "https://x.example/s1",
            "content_type": "text/html",
            "text_chars": 900,
            "fetched_at": datetime(2026, 9, 28, tzinfo=UTC),
            "tdm_opt_out": False,
            "full_text": "body",
        }
    }


def test_best_archive_rows_without_text_do_not_load_bodies():
    session = RecordingSession({})
    assert tc.best_archive_rows_in(session, [], with_text=False) == {}
    assert session.log == []
    tc.best_archive_rows_in(session, ["s1"], with_text=False)
    assert "NULL::text AS full_text" in session.log[0][0]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (None, "missing"),
        ({"content_type": "text/html", "text_chars": 10, "tdm_opt_out": False}, "full_text"),
        ({"content_type": "adapter/snippet", "text_chars": 10, "tdm_opt_out": False}, "abstract_only"),
        ({"content_type": "text/html", "text_chars": 0, "tdm_opt_out": True}, "tdm_reserved"),
        ({"content_type": "text/html", "text_chars": 0, "tdm_opt_out": False}, "missing"),
    ],
)
def test_classify_archive_row(row, expected):
    assert tc.classify_archive_row(row) == expected
```

- [ ] **Step 2: Update `tests/pipeline/test_training_corpus.py`**

1. In `test_registry_payload_drops_snippet_bodies` change `payload = tc._registry_payload(registry)` to `payload = tc.registry_payload(registry)`.
2. Replace `_state_with` and `test_run_close_out_records_query_and_citation_state` with:

```python
def _state_with(registry, angle_sources, moderated=None):
    angle = SimpleNamespace(id="a1", source_ids=list(angle_sources))
    return SimpleNamespace(registry=registry, angles=[angle], moderated_result=moderated or {})


def test_run_close_out_marks_sources_of_moderated_claims_as_cited(recorder):
    registry = CitationRegistry()
    cited = registry.register_source(
        url="https://x.example/cited", title="C", snippet="abstract", search_query="ur ziggurat"
    )
    seen = registry.register_source(
        url="https://x.example/seen", title="S", snippet="abstract", search_query="ur pottery"
    )
    # Research-only runs assign no reference numbers: 'cited' means cited by a
    # moderated claim.
    moderated = {"final_claims": [{"claim": "The ziggurat is Ur-III.", "source_ids": [cited]}]}

    stats = tc.persist_run_corpus(_state_with(registry, [cited, seen], moderated), "req-1")

    assert stats == {"documents": 2, "links": 2}
    by_id = {link["source_id"]: link for link in recorder.links}
    assert by_id[cited]["cited"] is True
    assert by_id[cited]["search_query"] == "ur ziggurat"
    assert by_id[seen]["cited"] is False
    assert by_id[seen]["angle_id"] == "a1"
    # The registry is the DossierHandler's artifact now (handlers/dossier.py).
    assert recorder.artifacts == []
```

3. In the module docstring replace "and whether the run close-out records the citation state AFTER the presentation stage has pruned references." with "and whether the run close-out links every source and marks the ones a moderated claim cites."

- [ ] **Step 3: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_training_corpus_dossier.py tests/pipeline/test_training_corpus.py -m "not integration and not live_llm" -q`
Expected: failures (`TypeError: save_artifact() got an unexpected keyword argument 'replace'`, `AttributeError: ... 'registry_payload'`, `best_archive_rows_in`, `classify_archive_row`, and the close-out assertions).

- [ ] **Step 4: Implement in `pipeline/lyra/training_corpus.py`**

(a) Replace the module docstring's last paragraph "Nothing in the system reads these tables back for control flow." with:

```
The dossier export (pipeline/lyra/theo_dossier.py) reads them back to hand the
Claude writer its source texts; archive completion reads which sources already
have a full text. Nothing else reads them for control flow.
```

(b) Add to the imports: `from pipeline.lyra.dossier_manifest import moderated_source_ids`.

(c) Replace `save_artifact` with:

```python
_DELETE_ARTIFACT_SQL = text("""
    DELETE FROM research_artifacts
    WHERE request_id = :request_id AND kind = :kind AND ref = :ref
""")
_INSERT_ARTIFACT_SQL = text("""
    INSERT INTO research_artifacts (request_id, kind, ref, payload)
    VALUES (:request_id, :kind, :ref, CAST(:payload AS jsonb))
    RETURNING id
""")


def save_artifact(
    request_id: str | None, kind: str, payload: Any, ref: str = "", *, replace: bool = False
) -> int:
    """Store one intermediate reasoning artifact; returns its research_artifacts.id.

    ``request_id`` is None for passes that belong to no research run (curator,
    miner). ``ref`` scopes the kind — an angle id, or the pass date.
    ``replace=True`` keeps exactly one current row per (request_id, kind, ref):
    the old rows are deleted and the new one inserted in the same transaction.
    It needs a request_id; a standalone pass has no run identity to replace in.
    """
    if replace and not request_id:
        raise ValueError(f"save_artifact(replace=True) needs a request_id (kind={kind!r})")
    key = {"request_id": request_id or None, "kind": kind, "ref": _strip_nul(ref)[:200]}
    with _session_factory() as session:
        if replace:
            session.execute(_DELETE_ARTIFACT_SQL, key)
        artifact_id = session.execute(
            _INSERT_ARTIFACT_SQL,
            {**key, "payload": json.dumps(_strip_nul(payload), default=_json_default)},
        ).scalar_one()
        session.commit()
    return int(artifact_id)
```

(d) Rename `_registry_payload` to `registry_payload` (definition only; its one caller is removed in (g)). Update its docstring's first line to "Registry structure without the snippet bodies (the dossier's citation_registry kind)."

(e) Add after `registry_payload`:

```python
def classify_archive_row(row: dict | None) -> str:
    """full_text | tdm_reserved | abstract_only | missing, for one best_archive_rows entry."""
    if row is None:
        return "missing"
    if row["tdm_opt_out"]:
        return "tdm_reserved"
    if not row["text_chars"]:
        return "missing"
    return "abstract_only" if row["content_type"] == SNIPPET_CONTENT_TYPE else "full_text"


# The best archived row per source: a fetched full text beats a TDM reservation,
# which beats an adapter abstract; the newest row wins inside each class.
_BEST_ROWS_ORDER = """
    ORDER BY source_id,
             CASE WHEN NOT tdm_opt_out AND content_type <> :snippet AND text_chars > 0 THEN 0
                  WHEN tdm_opt_out THEN 1
                  ELSE 2 END,
             fetched_at DESC
"""
_BEST_ROWS_TEXT_SQL = text(
    """
    SELECT DISTINCT ON (source_id)
           source_id, url, content_type, text_chars, fetched_at, tdm_opt_out, full_text
    FROM theo_source_archive
    WHERE source_id = ANY(:ids)
    """
    + _BEST_ROWS_ORDER
)
_BEST_ROWS_META_SQL = text(
    """
    SELECT DISTINCT ON (source_id)
           source_id, url, content_type, text_chars, fetched_at, tdm_opt_out,
           NULL::text AS full_text
    FROM theo_source_archive
    WHERE source_id = ANY(:ids)
    """
    + _BEST_ROWS_ORDER
)


def best_archive_rows_in(session: Any, source_ids: list[str], *, with_text: bool) -> dict[str, dict]:
    """The best archived row for each source id, in the caller's session.

    Keys: source_id, url, content_type, text_chars, fetched_at, tdm_opt_out and
    full_text (None unless with_text). Sources with no row are absent.
    """
    ids = list(dict.fromkeys(source_ids))
    if not ids:
        return {}
    sql = _BEST_ROWS_TEXT_SQL if with_text else _BEST_ROWS_META_SQL
    rows = session.execute(sql, {"ids": ids, "snippet": SNIPPET_CONTENT_TYPE}).fetchall()
    return {
        row.source_id: {
            "source_id": row.source_id,
            "url": row.url,
            "content_type": row.content_type,
            "text_chars": row.text_chars,
            "fetched_at": row.fetched_at,
            "tdm_opt_out": row.tdm_opt_out,
            "full_text": row.full_text,
        }
        for row in rows
    }


def best_archive_rows(source_ids: list[str], *, with_text: bool) -> dict[str, dict]:
    """best_archive_rows_in with its own session (for asyncio.to_thread callers)."""
    with _session_factory() as session:
        return best_archive_rows_in(session, source_ids, with_text=with_text)
```

(f) In `record_run_links` change the conflict clause to:

```python
                ON CONFLICT (request_id, source_id) DO UPDATE
                    SET angle_id = EXCLUDED.angle_id,
                        search_query = EXCLUDED.search_query,
                        cited = theo_source_archive_runs.cited OR EXCLUDED.cited
```

and extend its docstring: "A link that is already cited stays cited: archive completion records the cited links before the run close-out writes every link."

(g) Replace `persist_run_corpus` with:

```python
def persist_run_corpus(state: Any, request_id: str) -> dict:
    """Close out a run: archive un-fetched source texts and link every source to the run.

    Runs at the very end of a run, successful or failed, when every source the
    run touched is known. 'cited' means cited by a moderated claim (research-only
    runs assign no reference numbers). The citation registry is written by the
    DossierHandler (handlers/dossier.py), not here.
    """
    registry = getattr(state, "registry", None)
    if registry is None or not registry.sources:
        return {"documents": 0, "links": 0}

    angle_of: dict[str, str] = {}
    query_of: dict[str, str] = {}
    for angle in getattr(state, "angles", None) or []:
        for sid in angle.source_ids:
            angle_of.setdefault(sid, angle.id)
    for sid, source in registry.sources.items():
        if source.search_query:
            query_of[sid] = source.search_query

    # Sources whose page was fetched are already archived with their full
    # text; everything else contributes the adapter abstract, so the archive
    # holds the text of every source exactly once.
    known = already_archived(list(registry.sources))
    documents = [
        document_from_source(
            source,
            full_text=source.snippet,
            content_type=SNIPPET_CONTENT_TYPE,
        )
        for sid, source in registry.sources.items()
        if sid not in known and source.snippet
    ]
    written = archive_documents(documents)

    # Standalone passes (request_id="") have no run identity worth keying on —
    # their documents are archived, but they contribute no run linkage.
    linked = 0
    if request_id:
        cited = set(moderated_source_ids(state.moderated_result))
        linked = record_run_links(
            request_id,
            [
                {
                    "source_id": sid,
                    "angle_id": angle_of.get(sid, ""),
                    "search_query": query_of.get(sid, "")[:2000],
                    "cited": sid in cited,
                }
                for sid in registry.sources
            ],
        )
    return {"documents": written, "links": linked}
```

- [ ] **Step 5: Run the corpus tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_training_corpus_dossier.py tests/pipeline/test_training_corpus.py tests/pipeline/test_training_corpus_nul.py tests/pipeline/test_content_fetch_archive.py -m "not integration and not live_llm" -q`
Expected: all pass (`11` new, the updated 18, `4`, `6`).

- [ ] **Step 6: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/training_corpus.py tests/pipeline/test_training_corpus.py tests/pipeline/test_training_corpus_dossier.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/training_corpus.py tests/pipeline/test_training_corpus.py tests/pipeline/test_training_corpus_dossier.py
git add pipeline/lyra/training_corpus.py tests/pipeline/test_training_corpus.py tests/pipeline/test_training_corpus_dossier.py
git commit -m "Keep one current research artifact per run, kind and ref, and read back the best archived text of each source" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 6: Archive completion

**Files:**
- Modify: `pipeline/lyra/handlers/content_fetch.py` (static methods `_domain_policy`/`_domain_of`, lines 280-309, become module functions)
- Create: `pipeline/lyra/archive_completion.py`
- Modify: `requirements-api.txt`
- Test: `tests/pipeline/test_archive_completion.py`

Prerequisite: `./.venv/Scripts/python.exe -m pip install pypdf==6.19.0`.

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_archive_completion.py`:

```python
"""Archive completion: the full text of every source a moderated claim cites (spec 2.3).

HTTP runs through httpx.MockTransport; the database seams (best_archive_rows,
archive_documents, record_run_links, load_transcript) are replaced by recorders.
"""

from __future__ import annotations

import asyncio
import io

import httpx
import pytest

from pipeline.lyra import archive_completion as ac
from pipeline.lyra.research_state import ResearchAngle
from pipeline.lyra.theo_citations import CitationRegistry
from pipeline.lyra.training_corpus import SNIPPET_CONTENT_TYPE, DomainPolicy

REQ = "11111111-2222-3333-4444-555555555555"
MISSING_SID = "deadbeef0000"


def minimal_pdf(text: str) -> bytes:
    """A one-page PDF whose text pypdf extracts (verified with pypdf 6.19.0)."""
    stream = f"BT /F1 12 Tf 72 712 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


# --- pure helpers -------------------------------------------------------------


def test_wikipedia_goes_through_the_rest_html_endpoint():
    assert ac.resolve_fetch_url("https://en.wikipedia.org/wiki/G%C3%B6bekli_Tepe") == (
        "wikipedia",
        "https://en.wikipedia.org/api/rest_v1/page/html/G%C3%B6bekli_Tepe",
    )


def test_doi_and_ordinary_pages_are_plain_web_fetches():
    assert ac.resolve_fetch_url("https://doi.org/10.1000/xyz") == ("web", "https://doi.org/10.1000/xyz")
    assert ac.resolve_fetch_url("https://en.wikipedia.org/w/index.php?title=X") == (
        "web",
        "https://en.wikipedia.org/w/index.php?title=X",
    )


@pytest.mark.parametrize(
    ("url", "video_id"),
    [
        ("https://youtu.be/dQw4w9WgXcQ?t=30", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/channel/UC123", None),
        ("https://example.com/watch?v=dQw4w9WgXcQ", None),
    ],
)
def test_youtube_video_id(url, video_id):
    assert ac.youtube_video_id(url) == video_id
    assert (ac.resolve_fetch_url(url)[0] == "youtube") is (video_id is not None)


def test_limits_come_from_the_environment(monkeypatch):
    monkeypatch.delenv("THEO_ARCHIVE_COMPLETION_MAX_S", raising=False)
    monkeypatch.delenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", raising=False)
    assert ac.archive_completion_limits() == (1800.0, 4)
    monkeypatch.setenv("THEO_ARCHIVE_COMPLETION_MAX_S", "600")
    monkeypatch.setenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", "2")
    assert ac.archive_completion_limits() == (600.0, 2)
    monkeypatch.setenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", "0")
    with pytest.raises(ValueError, match="at least 1"):
        ac.archive_completion_limits()


def test_pdf_text_is_extracted():
    pytest.importorskip("pypdf")
    assert "Baalbek trilithon weighs 800 tonnes" in ac.pdf_text(minimal_pdf("Baalbek trilithon weighs 800 tonnes"))


def test_unreadable_pdf_is_a_recorded_failure():
    pytest.importorskip("pypdf")
    with pytest.raises(ac.ArchiveFetchError, match="unreadable PDF"):
        ac.pdf_text(b"%PDF-1.4 this is not a pdf")


async def test_fetch_document_reads_pdf_and_rejects_other_binaries():
    pytest.importorskip("pypdf")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".pdf"):
            return httpx.Response(200, content=minimal_pdf("Roman capstans"), headers={"content-type": "application/pdf"})
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        page = await ac.fetch_document(client, "https://a.example/paper.pdf")
        assert "Roman capstans" in page.text
        assert page.html == ""
        with pytest.raises(ac.ArchiveFetchError, match="unsupported content type"):
            await ac.fetch_document(client, "https://a.example/figure.png")


# --- the whole step ---------------------------------------------------------


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url == "https://site.example/page":
        return httpx.Response(200, html="<html><body><p>Baalbek quarry blocks weigh 1,000 tonnes.</p></body></html>")
    if url == "https://en.wikipedia.org/api/rest_v1/page/html/Baalbek":
        return httpx.Response(200, html="<html><body><p>Baalbek is a city in Lebanon.</p></body></html>")
    if url == "https://doi.org/10.1000/xyz":
        return httpx.Response(302, headers={"location": "https://publisher.example/article"})
    if url == "https://publisher.example/article":
        return httpx.Response(403, html="blocked")
    if url == "https://reserved.example/paper":
        return httpx.Response(200, html="<html><body><p>Reserved text body.</p></body></html>")
    if url == "https://broken.example/x":
        return httpx.Response(500, text="oops")
    raise AssertionError(f"unexpected fetch {url}")


class _Recorder:
    def __init__(self) -> None:
        self.documents: list = []
        self.links: list = []


@pytest.fixture
def seams(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(
        ac, "archive_documents", lambda docs: rec.documents.extend(docs) or len(docs)
    )
    monkeypatch.setattr(
        ac, "record_run_links", lambda request_id, links: rec.links.extend(links) or len(links)
    )
    monkeypatch.setattr(
        ac, "load_transcript", lambda video_id: "Transcript of the talk." if video_id == "dQw4w9WgXcQ" else ""
    )

    async def policy(host: str) -> DomainPolicy:
        return DomainPolicy(reserved_paths=("/",)) if host == "reserved.example" else DomainPolicy()

    monkeypatch.setattr(ac, "fetch_domain_policy", policy)
    monkeypatch.setattr(
        ac,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(_handler), follow_redirects=True),
    )
    return rec


def _registry_and_ids():
    registry = CitationRegistry()
    ids = {
        "page": registry.register_source(url="https://site.example/page", title="Page", snippet=""),
        "wiki": registry.register_source(url="https://en.wikipedia.org/wiki/Baalbek", title="Baalbek", snippet=""),
        "doi": registry.register_source(url="https://doi.org/10.1000/xyz", title="Paper", snippet=""),
        "video": registry.register_source(url="https://youtu.be/dQw4w9WgXcQ?t=30", title="Talk", snippet=""),
        "known": registry.register_source(url="https://old.example/known", title="Known", snippet=""),
        "reserved": registry.register_source(url="https://reserved.example/paper", title="Reserved", snippet=""),
        "broken": registry.register_source(url="https://broken.example/x", title="Broken", snippet="An abstract."),
    }
    return registry, ids


async def test_every_cited_source_ends_classified_and_recorded(seams, monkeypatch):
    registry, ids = _registry_and_ids()
    monkeypatch.setattr(
        ac,
        "best_archive_rows",
        lambda source_ids, *, with_text: {
            ids["known"]: {
                "source_id": ids["known"],
                "url": "https://old.example/known",
                "content_type": "text/html",
                "text_chars": 5000,
                "fetched_at": None,
                "tdm_opt_out": False,
                "full_text": None,
            }
        },
    )
    moderated = {"final_claims": [{"claim": "c", "source_ids": [*ids.values(), MISSING_SID]}]}
    angles = [ResearchAngle(id="ang1", topic="t", description="d", source_ids=[ids["page"], ids["wiki"]])]

    stats = await ac.complete_archive(REQ, registry, moderated, angles, max_seconds=30, concurrency=3)

    assert (stats.cited_sources, stats.full_text, stats.tdm_reserved, stats.abstract_only, stats.missing) == (
        8,
        4,
        1,
        1,
        2,
    )
    assert stats.timed_out is False
    reasons = {failure["source_id"]: failure["reason"] for failure in stats.failures}
    assert reasons[MISSING_SID] == "source id is not in the citation registry"
    assert reasons[ids["doi"]].startswith("HTTP 403 from https://publisher.example/article")
    assert reasons[ids["broken"]].startswith("HTTP 500")
    assert set(reasons) == {MISSING_SID, ids["doi"], ids["broken"]}

    documents = {doc.source_id: doc for doc in seams.documents}
    assert set(documents) == {ids["page"], ids["wiki"], ids["video"], ids["reserved"], ids["broken"]}
    assert documents[ids["page"]].full_text == "Baalbek quarry blocks weigh 1,000 tonnes."
    assert documents[ids["wiki"]].full_text == "Baalbek is a city in Lebanon."
    assert documents[ids["video"]].content_type == ac.TRANSCRIPT_CONTENT_TYPE
    assert documents[ids["reserved"]].tdm_opt_out is True
    assert documents[ids["reserved"]].tdm_signal == "tdmrep"
    assert documents[ids["broken"]].content_type == SNIPPET_CONTENT_TYPE
    assert documents[ids["broken"]].full_text == "An abstract."

    links = {link["source_id"]: link for link in seams.links}
    assert set(links) == set(ids.values())
    assert all(link["cited"] is True for link in links.values())
    assert links[ids["page"]]["angle_id"] == "ang1"
    assert links[ids["doi"]]["angle_id"] == ""


async def test_time_budget_is_enforced_and_recorded(seams, monkeypatch):
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, html="<p>late</p>")

    monkeypatch.setattr(
        ac, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(slow), follow_redirects=True)
    )
    monkeypatch.setattr(ac, "best_archive_rows", lambda source_ids, *, with_text: {})
    registry = CitationRegistry()
    sid = registry.register_source(url="https://slow.example/p", title="Slow", snippet="")
    moderated = {"final_claims": [{"claim": "c", "source_ids": [sid]}]}

    stats = await ac.complete_archive(REQ, registry, moderated, [], max_seconds=0.1, concurrency=2)

    assert stats.timed_out is True
    assert stats.missing == 1
    assert stats.failures == [
        {"source_id": sid, "url": "https://slow.example/p", "reason": "archive completion time budget exhausted"}
    ]
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_archive_completion.py -m "not integration and not live_llm" -q`
Expected: collection error `No module named 'pipeline.lyra.archive_completion'`.

- [ ] **Step 3: Make the reservation helpers of `content_fetch.py` reusable**

In `pipeline/lyra/handlers/content_fetch.py`, move the bodies of the two static methods to module level (place them after `_resolve_max_content_chars`):

```python
async def fetch_domain_policy(domain: str) -> DomainPolicy:
    """Reservation signals published by one host (robots.txt and tdmrep.json).

    A host that answers neither document has reserved nothing, which is the
    normal case. A host we could not reach at all is recorded as `check_failed`
    on every document it produced: an unchecked row must never masquerade as a
    checked one. Shared with archive_completion.py.
    """
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (research bot)"},
        ) as client:
            robots_resp, tdm_resp = await asyncio.gather(
                client.get(f"https://{domain}/robots.txt"),
                client.get(f"https://{domain}/.well-known/tdmrep.json"),
            )
        return DomainPolicy(
            robots=parse_robots(robots_resp.text) if robots_resp.status_code == 200 else None,
            reserved_paths=parse_tdmrep(tdm_resp.text) if tdm_resp.status_code == 200 else (),
        )
    except Exception as exc:
        logger.debug("[archive] reservation check failed for %s: %s", domain, exc)
        return DomainPolicy(check_error=str(exc)[:200])


def domain_of(url: str) -> str:
    """Host of a URL without a leading www. (the key of the reservation policies)."""
    return (urllib.parse.urlparse(url).hostname or "").removeprefix("www.")
```

and replace the two `@staticmethod` definitions `_domain_policy` and `_domain_of` inside `ContentFetchHandler` with:

```python
    # Reached through the class so tests can swap them (test_content_fetch_archive.py).
    _domain_policy = staticmethod(fetch_domain_policy)
    _domain_of = staticmethod(domain_of)
```

(The `except Exception` that records `check_failed` already existed; it is moved, not added.)

- [ ] **Step 4: Create `pipeline/lyra/archive_completion.py`**

```python
"""Archive completion: the full text of every source a moderated claim cites (spec 2.3).

Runs inside the DossierHandler after the moderator, on the VPS. During the run
content_fetch fetched only sources whose adapter snippet was short, and never
Wikipedia, doi.org or YouTube, so about half of the sources behind moderated
claims had no more than an abstract archived. The Claude writer checks every
claim against archived text, so this step fetches what is missing:

* Wikipedia through its REST HTML endpoint (/api/rest_v1/page/html/<title>);
* doi.org by following the redirect to the publisher's landing page;
* PDFs through pypdf, HTML through pipeline.utils.text.extract_text_from_html;
* YouTube as the transcript news_videos holds (what the transcript adapter cites).

TDM reservations are honoured as content_fetch honours them: the row is stored
without its body and the source counts as tdm_reserved (the local fact check
reads it live). The step is bounded in time and concurrency
(THEO_ARCHIVE_COMPLETION_MAX_S, THEO_ARCHIVE_COMPLETION_CONCURRENCY), and every
per-source failure is recorded in the manifest, never dropped.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import time
import urllib.parse
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx
from sqlalchemy import text

from pipeline.lyra.dossier_manifest import moderated_source_ids
from pipeline.lyra.handlers.content_fetch import domain_of, fetch_domain_policy
from pipeline.lyra.training_corpus import (
    MAX_HTML_CHARS,
    SNIPPET_CONTENT_TYPE,
    DomainPolicy,
    archive_documents,
    best_archive_rows,
    classify_archive_row,
    document_from_source,
    html_reserves_tdm,
    record_run_links,
    reservation_for,
)
from pipeline.utils.http import DEFAULT_HEADERS, is_public_http_url
from pipeline.utils.text import extract_text_from_html

TRANSCRIPT_CONTENT_TYPE = "youtube/transcript"
_HTTP_TIMEOUT_S = 20.0
_MAX_PDF_BYTES = 30_000_000
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_TRANSCRIPT_SQL = text("SELECT transcript_text FROM news_videos WHERE id = :id")
_TIME_BUDGET_REASON = "archive completion time budget exhausted"


class ArchiveFetchError(Exception):
    """One source could not be archived; the reason goes into the manifest."""


@dataclass
class ArchiveStats:
    """The manifest's `archive` section (contract C1)."""

    cited_sources: int = 0
    full_text: int = 0
    abstract_only: int = 0
    missing: int = 0
    tdm_reserved: int = 0
    failures: list[dict] = field(default_factory=list)
    duration_s: float = 0.0
    timed_out: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FetchedDocument:
    """Text of one fetched document plus what the archive row needs."""

    text: str
    html: str
    status: int
    content_type: str
    final_url: str


@dataclass
class _Completed:
    document: Any  # training_corpus.ArchiveDocument
    status: str  # full_text | tdm_reserved


def archive_completion_limits() -> tuple[float, int]:
    """(THEO_ARCHIVE_COMPLETION_MAX_S, THEO_ARCHIVE_COMPLETION_CONCURRENCY), defaults 1800 s and 4."""
    max_seconds = float(os.getenv("THEO_ARCHIVE_COMPLETION_MAX_S", "1800"))
    concurrency = int(os.getenv("THEO_ARCHIVE_COMPLETION_CONCURRENCY", "4"))
    if concurrency < 1:
        raise ValueError(f"THEO_ARCHIVE_COMPLETION_CONCURRENCY must be at least 1, got {concurrency}")
    return max_seconds, concurrency


def youtube_video_id(url: str) -> str | None:
    """The 11-character video id of a youtu.be / youtube.com URL, else None."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = ""
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            candidate = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            candidate = parsed.path.split("/")[2]
    return candidate if _YOUTUBE_ID_RE.match(candidate) else None


def resolve_fetch_url(url: str) -> tuple[str, str]:
    """(kind, URL to fetch): kind is 'wikipedia', 'youtube' or 'web'.

    Wikipedia articles go through the REST HTML endpoint (article HTML without
    skin or navigation). doi.org stays 'web': the client follows the redirect
    to the publisher.
    """
    if youtube_video_id(url):
        return "youtube", url
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    is_wikipedia = host == "wikipedia.org" or host.endswith(".wikipedia.org")
    if is_wikipedia and parsed.path.startswith("/wiki/") and len(parsed.path) > len("/wiki/"):
        title = parsed.path[len("/wiki/") :]
        return "wikipedia", f"https://{host}/api/rest_v1/page/html/{title}"
    return "web", url


def pdf_text(data: bytes) -> str:
    """Text of a PDF (pypdf, imported here: API image only)."""
    from pypdf import PdfReader

    if len(data) > _MAX_PDF_BYTES:
        raise ArchiveFetchError(f"PDF larger than {_MAX_PDF_BYTES} bytes")
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 — pypdf parses untrusted bytes and raises many types; recorded per source
        raise ArchiveFetchError(f"unreadable PDF: {type(exc).__name__}: {exc}") from exc
    body = "\n".join(page.strip() for page in pages if page.strip())
    if not body:
        raise ArchiveFetchError("PDF carries no extractable text (scanned image?)")
    return body


async def fetch_document(client: httpx.AsyncClient, url: str) -> FetchedDocument:
    """Fetch one URL and extract its text (HTML or PDF). Raises ArchiveFetchError."""
    resp = await client.get(url)
    final_url = str(resp.url)
    if resp.status_code != 200:
        raise ArchiveFetchError(f"HTTP {resp.status_code} from {final_url}")
    content_type = resp.headers.get("content-type", "")
    lowered = content_type.lower()
    if "pdf" in lowered or urllib.parse.urlparse(final_url).path.lower().endswith(".pdf"):
        return FetchedDocument(
            text=pdf_text(resp.content),
            html="",
            status=resp.status_code,
            content_type=content_type or "application/pdf",
            final_url=final_url,
        )
    if "html" in lowered or not content_type:
        html = resp.text[:MAX_HTML_CHARS]
        body = extract_text_from_html(html)
        if not body:
            raise ArchiveFetchError(f"page yielded no text: {final_url}")
        return FetchedDocument(
            text=body, html=html, status=resp.status_code, content_type=content_type, final_url=final_url
        )
    raise ArchiveFetchError(f"unsupported content type {content_type!r} from {final_url}")


def load_transcript(video_id: str) -> str:
    """The transcript news_videos holds for a YouTube video, '' when it has none."""
    from pipeline.database import get_session

    with get_session() as session:
        row = session.execute(_TRANSCRIPT_SQL, {"id": video_id}).fetchone()
    if row is None or not row.transcript_text:
        return ""
    return row.transcript_text


def _client() -> httpx.AsyncClient:
    """One client for the whole step: follows redirects (doi.org), 20 s per request.

    The User-Agent names the project, as Wikimedia's API policy asks of API clients.
    """
    return httpx.AsyncClient(
        timeout=_HTTP_TIMEOUT_S,
        follow_redirects=True,
        headers={
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
        },
    )


async def _policy(cache: dict[str, asyncio.Task], host: str) -> DomainPolicy:
    """One reservation lookup per host, shared by concurrent fetches."""
    if host not in cache:
        cache[host] = asyncio.create_task(fetch_domain_policy(host))
    return await asyncio.shield(cache[host])


async def _complete_one(
    client: httpx.AsyncClient, source: Any, policy_cache: dict[str, asyncio.Task]
) -> _Completed:
    kind, fetch_url = resolve_fetch_url(source.url)
    if kind == "youtube":
        video_id = youtube_video_id(source.url)
        transcript = await asyncio.to_thread(load_transcript, video_id)
        if not transcript:
            raise ArchiveFetchError(f"no transcript for YouTube video {video_id} in news_videos")
        document = document_from_source(
            source, full_text=transcript, content_type=TRANSCRIPT_CONTENT_TYPE, archive_only=True
        )
        return _Completed(document, "full_text")
    if not is_public_http_url(fetch_url):
        raise ArchiveFetchError(f"not a public http(s) URL: {fetch_url}")
    page = await fetch_document(client, fetch_url)
    # Wikipedia is fetched through /api/, which robots.txt closes to crawlers; the
    # reservation question is about the article, so it is asked of the /wiki/ URL.
    policy_url = source.url if kind == "wikipedia" else page.final_url
    verdict = reservation_for(policy_url, await _policy(policy_cache, domain_of(policy_url)))
    if not verdict.opt_out and page.html and html_reserves_tdm(page.html):
        verdict.opt_out, verdict.signal = True, "meta_tag"
    document = document_from_source(
        source,
        full_text=page.text,
        raw_html=page.html,
        http_status=page.status,
        content_type=page.content_type,
        archive_only=True,
        tdm_opt_out=verdict.opt_out,
        tdm_signal=verdict.signal,
    )
    return _Completed(document, "tdm_reserved" if verdict.opt_out else "full_text")


async def _fetch_all(
    pending: list, *, max_seconds: float, concurrency: int
) -> tuple[dict[str, _Completed], dict[str, str], bool]:
    """Fetch every pending source: (completed by id, failure reason by id, timed out)."""
    if not pending:
        return {}, {}, False
    gate = asyncio.Semaphore(concurrency)
    policy_cache: dict[str, asyncio.Task] = {}
    async with _client() as client:

        async def run(source: Any) -> _Completed:
            async with gate:
                return await _complete_one(client, source, policy_cache)

        tasks = {source.id: asyncio.create_task(run(source)) for source in pending}
        _done, still_running = await asyncio.wait(tasks.values(), timeout=max(max_seconds, 0.0))
        for task in still_running:
            task.cancel()
        await asyncio.gather(*still_running, return_exceptions=True)
        for task in policy_cache.values():
            task.cancel()
        await asyncio.gather(*policy_cache.values(), return_exceptions=True)

    completed: dict[str, _Completed] = {}
    reasons: dict[str, str] = {}
    for source_id, task in tasks.items():
        if task in still_running:
            reasons[source_id] = _TIME_BUDGET_REASON
            continue
        exc = task.exception()
        if exc is None:
            completed[source_id] = task.result()
        elif isinstance(exc, ArchiveFetchError):
            reasons[source_id] = str(exc)
        elif isinstance(exc, httpx.HTTPError):
            reasons[source_id] = f"{type(exc).__name__}: {exc}"
        else:
            raise exc
    return completed, reasons, bool(still_running)


async def complete_archive(
    request_id: str,
    registry: Any,
    moderated: dict,
    angles: list,
    *,
    max_seconds: float,
    concurrency: int,
) -> ArchiveStats:
    """Archive the full text of every source the moderated claims cite; return the coverage.

    Every cited source ends in exactly one class: full_text, tdm_reserved,
    abstract_only (only an adapter abstract exists; archived here when it was
    not yet) or missing. Every cited source in the registry is linked to the run
    with cited=true (theo_source_archive_runs), meaning "cited by a moderated claim".
    """
    started = time.monotonic()
    targets = moderated_source_ids(moderated)
    stats = ArchiveStats(cited_sources=len(targets))
    known = await asyncio.to_thread(best_archive_rows, targets, with_text=False)

    status: dict[str, str] = {}
    failures: dict[str, dict] = {}
    pending: list = []
    for source_id in targets:
        source = registry.get_reference(source_id)
        if source is None:
            status[source_id] = "missing"
            failures[source_id] = {
                "source_id": source_id,
                "url": "",
                "reason": "source id is not in the citation registry",
            }
            continue
        current = classify_archive_row(known.get(source_id))
        if current in ("full_text", "tdm_reserved"):
            status[source_id] = current
        else:
            pending.append(source)

    completed, reasons, timed_out = await _fetch_all(
        pending, max_seconds=max_seconds - (time.monotonic() - started), concurrency=concurrency
    )

    documents = []
    for source in pending:
        if source.id in completed:
            documents.append(completed[source.id].document)
            status[source.id] = completed[source.id].status
            continue
        failures[source.id] = {"source_id": source.id, "url": source.url, "reason": reasons[source.id]}
        if classify_archive_row(known.get(source.id)) == "abstract_only":
            status[source.id] = "abstract_only"
        elif source.snippet:
            documents.append(
                document_from_source(source, full_text=source.snippet, content_type=SNIPPET_CONTENT_TYPE)
            )
            status[source.id] = "abstract_only"
        else:
            status[source.id] = "missing"
    await asyncio.to_thread(archive_documents, documents)

    angle_of: dict[str, str] = {}
    for angle in angles:
        for source_id in angle.source_ids:
            angle_of.setdefault(source_id, angle.id)
    links = []
    for source_id in targets:
        source = registry.get_reference(source_id)
        if source is None:
            continue
        links.append(
            {
                "source_id": source_id,
                "angle_id": angle_of.get(source_id, ""),
                "search_query": source.search_query[:2000],
                "cited": True,
            }
        )
    await asyncio.to_thread(record_run_links, request_id, links)

    tally = Counter(status.values())
    stats.full_text = tally["full_text"]
    stats.abstract_only = tally["abstract_only"]
    stats.missing = tally["missing"]
    stats.tdm_reserved = tally["tdm_reserved"]
    stats.failures = [failures[source_id] for source_id in targets if source_id in failures]
    stats.timed_out = timed_out
    stats.duration_s = round(time.monotonic() - started, 1)
    return stats
```

- [ ] **Step 5: Pin pypdf in the API image**

In `requirements-api.txt`, under `# --- Content rendering ---` after the `youtube-transcript-api` line, add:

```
pypdf==6.19.0  # archive completion: text of cited PDF sources (pipeline/lyra/archive_completion.py)
```

- [ ] **Step 6: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_archive_completion.py tests/pipeline/test_content_fetch_archive.py -m "not integration and not live_llm" -q`
Expected: `13 passed` in the new file (without pypdf installed, the three PDF tests show as skipped: install it, see Prerequisite) and the 6 content-fetch tests pass.

- [ ] **Step 7: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/handlers/content_fetch.py pipeline/lyra/archive_completion.py tests/pipeline/test_archive_completion.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/handlers/content_fetch.py pipeline/lyra/archive_completion.py tests/pipeline/test_archive_completion.py
git add pipeline/lyra/handlers/content_fetch.py pipeline/lyra/archive_completion.py requirements-api.txt tests/pipeline/test_archive_completion.py
git commit -m "Archive the full text of every source a moderated claim cites, including Wikipedia, doi landing pages, PDFs and transcripts" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 7: DossierHandler

**Files:**
- Create: `pipeline/lyra/handlers/dossier.py`
- Test: `tests/pipeline/test_dossier_handler.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_dossier_handler.py`:

```python
"""DossierHandler: the end of a research run (spec 2.1-2.3)."""

from __future__ import annotations

import asyncio

import pytest

from pipeline.lyra import convergence_orchestrator
from pipeline.lyra.archive_completion import ArchiveStats
from pipeline.lyra.handlers import dossier as dossier_module
from pipeline.lyra.handlers.dossier import DossierHandler
from pipeline.lyra.research_events import DossierReady, EventBus, ModeratorComplete
from pipeline.lyra.research_state import (
    ActiveSpecialist,
    ResearchAngle,
    ResearchPhase,
    ResearchState,
)

REQ = "11111111-2222-3333-4444-555555555555"
EXPECTED_KINDS = [
    "moderated",
    "synthesis",
    "debate",
    "angle_findings",
    "specialist_analyses",
    "citation_registry",
    "image_candidate_pool",
    "dossier",
]


@pytest.fixture
def saved(monkeypatch):
    rows: list[tuple] = []

    def fake_save(request_id, kind, payload, ref="", *, replace=False):
        rows.append((request_id, kind, ref, replace, payload))
        return len(rows)

    async def fake_complete(request_id, registry, moderated, angles, *, max_seconds, concurrency):
        assert (max_seconds, concurrency) == (1800.0, 4)
        return ArchiveStats(cited_sources=1, full_text=1, duration_s=2.5)

    monkeypatch.setattr(dossier_module, "save_artifact", fake_save)
    monkeypatch.setattr(dossier_module, "complete_archive", fake_complete)
    monkeypatch.setattr(dossier_module, "archive_completion_limits", lambda: (1800.0, 4))
    # EventBus.emit piggybacks a DB progress flush for runs with a request_id.
    monkeypatch.setattr(convergence_orchestrator, "_flush_progress_to_db", lambda state, rid: None)
    return rows


def _state() -> ResearchState:
    state = ResearchState(question="Who cut the Baalbek monoliths?", request_id=REQ)
    source = state.registry.register_source(url="https://a.example/survey", title="Survey", snippet="abstract")
    state.angles = [
        ResearchAngle(
            id="ang1",
            topic="Quarry",
            description="The quarry",
            source_ids=[source],
            findings=[{"claim": "c1", "source_ids": [source], "specialist_id": "geo"}],
        )
    ]
    state.panel = [ActiveSpecialist(specialist_id="geo", name="Geologist", domain="geology")]
    state.synthesis = {"consensus_claims": []}
    state.cross_angle_connections = [{"from_angle": "ang1", "to_angle": "ang1", "description": "x"}]
    state.debate_result = {"rounds": 1}
    state.moderated_result = {
        "final_claims": [{"claim": "c1", "source_ids": [source]}],
        "revised_claims": [],
        "speculative_claims": [],
        "dropped_claims": [],
    }
    state.image_candidate_pool = {"ang1": [{"url": "https://commons.example/File:A.jpg"}]}
    return state


def _wire(state: ResearchState) -> tuple[EventBus, list[str]]:
    bus = EventBus(state=state)
    DossierHandler(state, bus, asyncio.Semaphore(1)).register()
    ready: list[str] = []

    async def on_ready(event: DossierReady):
        ready.append(event.request_id)

    bus.on(DossierReady, on_ready)
    return bus, ready


async def test_dossier_is_persisted_manifest_last_and_the_run_ends(saved):
    state = _state()
    bus, ready = _wire(state)

    await bus.emit(ModeratorComplete())

    assert [kind for _rid, kind, _ref, _replace, _payload in saved] == EXPECTED_KINDS
    assert all(replace for _rid, _kind, _ref, replace, _payload in saved)
    assert {rid for rid, *_rest in saved} == {REQ}
    assert saved[3][2] == "ang1"  # angle_findings is scoped by the angle id
    analyses = saved[4][4]["analyses"]
    assert analyses["geo"][0]["angle_id"] == "ang1"
    manifest = saved[-1][4]
    assert manifest["counts"]["final_claims"] == 1
    assert manifest["archive"]["full_text"] == 1
    assert manifest["angle_ids"] == ["ang1"]
    assert state.dossier_ref == len(EXPECTED_KINDS)
    assert state.dossier_summary["artifact_id"] == len(EXPECTED_KINDS)
    assert state.phase is ResearchPhase.DONE
    assert ready == [REQ]
    assert state.error == ""


async def test_a_second_moderator_complete_is_ignored(saved):
    state = _state()
    bus, ready = _wire(state)

    await bus.emit(ModeratorComplete())
    await bus.emit(ModeratorComplete())

    assert len(saved) == len(EXPECTED_KINDS)
    assert ready == [REQ]


async def test_no_final_claims_fails_the_run_without_a_dossier(saved):
    state = _state()
    state.moderated_result["final_claims"] = []
    bus, ready = _wire(state)

    await bus.emit(ModeratorComplete())

    assert saved == []
    assert ready == []
    assert state.dossier_ref is None
    assert state.error.startswith("Moderator produced no final claims")


async def test_a_dossier_write_failure_fails_the_run_loudly(saved, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(dossier_module, "save_artifact", broken)
    state = _state()
    bus, ready = _wire(state)

    await bus.emit(ModeratorComplete())

    assert state.error == "Handler failed on ModeratorComplete: RuntimeError('disk full')"
    assert ready == []
    assert state.dossier_ref is None
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_dossier_handler.py -m "not integration and not live_llm" -q`
Expected: collection error `No module named 'pipeline.lyra.handlers.dossier'`.

- [ ] **Step 3: Create `pipeline/lyra/handlers/dossier.py`**

```python
"""Dossier handler: the end of a Theo research run (spec 2.1-2.3).

Registered as the only listener on ModeratorComplete. It persists everything a
Claude writer needs as research_artifacts rows (replace semantics: one current
row per (request_id, kind, ref)), completes the source archive for every
source a moderated claim cites, writes the manifest LAST (its presence means
the dossier is complete), then marks the run DONE and emits DossierReady, the
orchestrator's done signal.

Unlike StatePersist's passenger writes, nothing here is fail-soft: an exception
propagates to EventBus.emit, which records it in state.error, and the run ends
'failed'.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from pipeline.lyra.archive_completion import archive_completion_limits, complete_archive
from pipeline.lyra.dossier_manifest import build_manifest, manifest_summary
from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import DossierReady, ModeratorComplete
from pipeline.lyra.research_state import ResearchPhase, findings_by_specialist
from pipeline.lyra.training_corpus import registry_payload, save_artifact

logger = logging.getLogger(__name__)


class DossierHandler(BaseHandler):
    """Persists the research dossier and ends the run."""

    def __init__(self, state, bus, semaphore):
        super().__init__(state, bus, semaphore)
        # The forced-deadline path can emit DebateComplete while the debate is
        # still running, so ModeratorComplete may fire twice. The lock makes the
        # second call wait for the first and then find dossier_ref set.
        self._lock = asyncio.Lock()

    def register(self):
        self.bus.on(ModeratorComplete, self._on_moderator_complete)

    async def _on_moderator_complete(self, event: ModeratorComplete):
        async with self._lock:
            if self.state.dossier_ref is not None:
                self.state.log(
                    "dossier", "ModeratorComplete fired again: the dossier is already persisted, ignored"
                )
                return
            await self._persist_dossier()

    async def _persist_dossier(self) -> None:
        state = self.state
        if not state.request_id:
            state.error = "A dossier needs a research_requests row, but the run has no request_id"
            return
        final_claims = state.moderated_result.get("final_claims") or []
        if not final_claims:
            state.error = (
                "Moderator produced no final claims: there is nothing to write a paper from, "
                "so no dossier was persisted"
            )
            return

        self.emit_sse(
            {"type": "pipeline", "stage": "dossier", "status": "start", "meta": {"subtask_total": 3}}
        )
        self.emit_sse({"type": "status", "content": "Persisting the research dossier..."})
        await self._save("moderated", state.moderated_result)
        await self._save(
            "synthesis",
            {"synthesis": state.synthesis, "cross_angle_connections": state.cross_angle_connections},
        )
        await self._save("debate", state.debate_result)
        for angle in state.angles:
            await self._save("angle_findings", asdict(angle), ref=angle.id)
        await self._save(
            "specialist_analyses",
            {
                "analyses": findings_by_specialist(state.angles),
                "panel": [asdict(specialist) for specialist in state.panel],
            },
        )
        await self._save("citation_registry", registry_payload(state.registry))
        await self._save("image_candidate_pool", state.image_candidate_pool)

        self.emit_sse({"type": "status", "content": "Archiving the full texts of every cited source..."})
        max_seconds, concurrency = archive_completion_limits()
        archive = await complete_archive(
            state.request_id,
            state.registry,
            state.moderated_result,
            state.angles,
            max_seconds=max_seconds,
            concurrency=concurrency,
        )
        state.log(
            "dossier",
            f"Archive completion: {archive.full_text}/{archive.cited_sources} cited sources with full "
            f"text, {archive.abstract_only} abstract only, {archive.missing} missing, "
            f"{archive.tdm_reserved} TDM-reserved, {len(archive.failures)} failures "
            f"in {archive.duration_s}s",
        )

        manifest = build_manifest(state, archive.to_dict(), created_at=datetime.now(UTC))
        artifact_id = await self._save("dossier", manifest)
        state.dossier_ref = artifact_id
        state.dossier_summary = manifest_summary(manifest, artifact_id)
        state.phase = ResearchPhase.DONE
        logger.info("[THEO] %s dossier persisted (artifact %s)", state.request_id, artifact_id)
        self.emit_sse(
            {
                "type": "pipeline",
                "stage": "dossier",
                "status": "done",
                "meta": {
                    "final_claims": len(final_claims),
                    "cited_sources": archive.cited_sources,
                    "full_text": archive.full_text,
                    "abstract_only": archive.abstract_only,
                    "missing": archive.missing,
                    "tdm_reserved": archive.tdm_reserved,
                },
            }
        )
        await self.bus.emit(DossierReady(request_id=state.request_id))

    async def _save(self, kind: str, payload: Any, ref: str = "") -> int:
        return await asyncio.to_thread(
            save_artifact, self.state.request_id, kind, payload, ref, replace=True
        )
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_dossier_handler.py -m "not integration and not live_llm" -q`
Expected: `4 passed`.

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/handlers/dossier.py tests/pipeline/test_dossier_handler.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/handlers/dossier.py tests/pipeline/test_dossier_handler.py
git add pipeline/lyra/handlers/dossier.py tests/pipeline/test_dossier_handler.py
git commit -m "Add the DossierHandler that persists a run's dossier, completes its archive and ends the run" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 8: StatePersist writes real specialist analyses and leaves `moderated` to the dossier

**Files:**
- Modify (full rewrite, 90 lines): `pipeline/lyra/handlers/state_persist.py`
- Test: `tests/pipeline/test_state_persist.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_state_persist.py`:

```python
"""StatePersist passenger writes: specialist analyses carry findings; the dossier owns 'moderated'."""

from __future__ import annotations

import asyncio

import pytest

from pipeline.lyra import convergence_orchestrator
from pipeline.lyra.handlers import state_persist as sp
from pipeline.lyra.handlers.state_persist import StatePersistHandler
from pipeline.lyra.research_events import AllAnglesSaturated, EventBus, ModeratorComplete
from pipeline.lyra.research_state import ActiveSpecialist, ResearchAngle, ResearchState

REQ = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def saved(monkeypatch):
    rows: list[tuple] = []
    monkeypatch.setattr(
        sp,
        "save_artifact",
        lambda request_id, kind, payload, ref="", *, replace=False: rows.append(
            (request_id, kind, payload, ref, replace)
        ),
    )
    monkeypatch.setattr(convergence_orchestrator, "_flush_progress_to_db", lambda state, rid: None)
    return rows


def _handler(request_id: str) -> tuple[ResearchState, EventBus]:
    state = ResearchState(question="q", request_id=request_id)
    state.angles = [
        ResearchAngle(
            id="a1",
            topic="t",
            description="d",
            findings=[{"claim": "c1", "specialist_id": "geo"}, {"claim": "c2", "specialist_id": "arch"}],
        )
    ]
    state.panel = [ActiveSpecialist(specialist_id="geo", name="G", domain="geology")]
    bus = EventBus(state=state)
    StatePersistHandler(state, bus, asyncio.Semaphore(1)).register()
    return state, bus


async def test_specialist_analyses_carry_the_findings(saved):
    _state, bus = _handler(REQ)
    await bus.emit(AllAnglesSaturated())
    ((request_id, kind, payload, ref, replace),) = saved
    assert (request_id, kind, ref, replace) == (REQ, "specialist_analyses", "", True)
    assert payload["analyses"]["geo"] == [{"claim": "c1", "specialist_id": "geo", "angle_id": "a1"}]
    assert payload["panel"][0]["specialist_id"] == "geo"


async def test_moderated_is_left_to_the_dossier_handler(saved):
    _state, bus = _handler(REQ)
    await bus.emit(ModeratorComplete())
    assert saved == []


async def test_a_run_without_request_id_appends(saved):
    _state, bus = _handler("")
    await bus.emit(AllAnglesSaturated())
    ((request_id, _kind, _payload, _ref, replace),) = saved
    assert request_id is None
    assert replace is False
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_state_persist.py -m "not integration and not live_llm" -q`
Expected: 3 failed (empty `analyses`, `moderated` written, `replace` keyword missing).

- [ ] **Step 3: Rewrite `pipeline/lyra/handlers/state_persist.py`**

```python
"""Persists a run's intermediate reasoning to the training corpus as it happens.

Each angle's findings, the specialist analyses behind them, the synthesis and
the debate are written when the stage that produces them finishes, so a run
that dies later (quota, crash, cancellation) still leaves them behind. The
dossier itself (moderated claims, citation registry, image pool, manifest) is
written by handlers/dossier.py on ModeratorComplete, which also rewrites these
kinds with their final content.

Writes use replace semantics when the run has a request_id: one current row per
(request_id, kind, ref), so a re-emitted event or a deferred re-run does not
stack duplicate rows.

Nothing here can fail a research run: these are passenger writes, logged loudly
and recorded in the run's debug_log when they fail. The dossier writes are the
hard ones.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from pipeline.lyra.handlers import BaseHandler
from pipeline.lyra.research_events import (
    AllAnglesSaturated,
    AngleSaturated,
    DebateComplete,
    SynthesisReady,
)
from pipeline.lyra.research_state import findings_by_specialist
from pipeline.lyra.training_corpus import save_artifact

logger = logging.getLogger(__name__)


class StatePersistHandler(BaseHandler):
    """Writes intermediate research state to research_artifacts."""

    def register(self):
        self.bus.on(AngleSaturated, self._on_angle_saturated)
        self.bus.on(AllAnglesSaturated, self._on_all_angles_saturated)
        self.bus.on(SynthesisReady, self._on_synthesis_ready)
        self.bus.on(DebateComplete, self._on_debate_complete)

    async def _on_angle_saturated(self, event: AngleSaturated):
        angle = next((a for a in self.state.angles if a.id == event.angle_id), None)
        if angle is None:
            return
        await self._save("angle_findings", angle, ref=angle.id)

    async def _on_all_angles_saturated(self, event: AllAnglesSaturated):
        # Grouped from the angles' findings at this moment. state.specialist_analyses
        # is only assembled after the run, so reading it here stored an empty dict
        # in every production row until 2026-09-26.
        await self._save(
            "specialist_analyses",
            {
                "analyses": findings_by_specialist(self.state.angles),
                "panel": [asdict(s) for s in self.state.panel],
            },
        )

    async def _on_synthesis_ready(self, event: SynthesisReady):
        await self._save(
            "synthesis",
            {
                "synthesis": self.state.synthesis,
                "cross_angle_connections": self.state.cross_angle_connections,
            },
        )

    async def _on_debate_complete(self, event: DebateComplete):
        await self._save("debate", self.state.debate_result)

    async def _save(self, kind: str, payload: Any, ref: str = "") -> None:
        try:
            body = asdict(payload) if hasattr(payload, "__dataclass_fields__") else payload
            await asyncio.to_thread(
                save_artifact,
                self.state.request_id or None,
                kind,
                body,
                ref,
                replace=bool(self.state.request_id),
            )
        except Exception as exc:
            logger.error("[archive] artifact '%s' failed: %s", kind, exc)
            self.state.log("archive", f"ARTIFACT WRITE FAILED ({kind}): {exc}")
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_state_persist.py -m "not integration and not live_llm" -q`
Expected: `3 passed`.

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/handlers/state_persist.py tests/pipeline/test_state_persist.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/handlers/state_persist.py tests/pipeline/test_state_persist.py
git add pipeline/lyra/handlers/state_persist.py tests/pipeline/test_state_persist.py
git commit -m "Store the specialists' real findings in specialist_analyses and leave the moderated claims to the dossier" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 9: Run the event cascade as a task so deadline, flush and cancellation run

Today the whole run executes inside `await decomposition.decompose()` (convergence_orchestrator.py:317): the deadline loop, the 30 s flush and `_check_external_cancellation` never ran in production. This task fixes only that; the writing chain is cut in Task 10.

**Files:**
- Modify: `pipeline/lyra/convergence_orchestrator.py`
- Test: `tests/pipeline/test_orchestrator_cascade.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_orchestrator_cascade.py`:

```python
"""The watch loop runs beside the event cascade (the nesting defect, fixed 2026-09-26).

Before the fix the whole run executed inside `await decomposition.decompose()`,
so the deadline check, the 30 s DB flush and the external-cancellation check
never ran in any production run since 2026-08-20.
"""

from __future__ import annotations

import asyncio

import pytest

from pipeline.lyra import convergence_orchestrator as co
from pipeline.lyra.minimax_limiter import QuotaExhaustedError
from pipeline.lyra.research_state import ResearchState

REQ = "11111111-2222-3333-4444-555555555555"


class _Deadline:
    def __init__(self) -> None:
        self.calls = 0

    async def check_deadline(self) -> bool:
        self.calls += 1
        return False


@pytest.fixture
def flushes(monkeypatch) -> list[str]:
    recorded: list[str] = []
    monkeypatch.setattr(co, "_TICK_S", 0.01)
    monkeypatch.setattr(co, "_UNWIND_GRACE_S", 1.0)
    monkeypatch.setattr(co, "_flush_progress_to_db", lambda state, rid: recorded.append(rid))
    monkeypatch.setattr(co, "_check_external_cancellation", lambda rid: None)
    return recorded


def _state() -> ResearchState:
    return ResearchState(question="Who cut the Baalbek monoliths?", request_id=REQ)


async def _drive(state, cascade, done, *, deadline=None, emit=None):
    await co._drive_cascade(
        state,
        cascade,
        done,
        deadline or _Deadline(),
        request_id=REQ,
        emit=emit or (lambda event: None),
        t0=0.0,
    )


async def test_the_done_signal_ends_the_watch(flushes):
    state, done = _state(), asyncio.Event()

    async def cascade():
        done.set()

    await _drive(state, cascade(), done)
    assert state.error == ""


async def test_a_cascade_that_ends_without_the_done_signal_is_an_error(flushes):
    state, done = _state(), asyncio.Event()

    async def cascade():
        return None

    await _drive(state, cascade(), done)
    assert state.error == co._NO_DOSSIER_ERROR


async def test_the_watch_ticks_while_the_cascade_runs(flushes):
    state, done = _state(), asyncio.Event()
    events: list[dict] = []
    deadline = _Deadline()

    async def cascade():
        await asyncio.sleep(0.2)
        done.set()

    await _drive(state, cascade(), done, deadline=deadline, emit=events.append)
    assert flushes, "the 30 s DB flush never ran during the cascade"
    assert deadline.calls >= 2
    assert any(event["type"] == "progress" for event in events)


async def test_external_cancellation_now_stops_the_cascade(flushes, monkeypatch):
    state, done = _state(), asyncio.Event()
    cancelled: list[bool] = []

    def cancelled_in_db(rid):
        raise co._CancelledByUser(f"{rid} status changed to 'cancelled'")

    monkeypatch.setattr(co, "_check_external_cancellation", cancelled_in_db)

    async def cascade():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    with pytest.raises(co._CancelledByUser):
        await _drive(state, cascade(), done)
    assert cancelled == [True]


async def test_a_quota_error_in_the_cascade_propagates(flushes):
    state, done = _state(), asyncio.Event()

    async def cascade():
        raise QuotaExhaustedError("weekly wall")

    with pytest.raises(QuotaExhaustedError):
        await _drive(state, cascade(), done)


async def test_a_handler_error_stops_the_run_at_the_next_tick(flushes):
    state, done = _state(), asyncio.Event()
    cancelled: list[bool] = []

    async def cascade():
        state.error = "Handler failed on ContentFetched: RuntimeError('boom')"
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    await _drive(state, cascade(), done)
    assert cancelled == [True]
    assert state.error.startswith("Handler failed")


async def test_the_cascade_may_unwind_after_the_done_signal(flushes):
    state, done = _state(), asyncio.Event()
    unwound: list[bool] = []

    async def cascade():
        done.set()
        await asyncio.sleep(0.05)
        unwound.append(True)

    await _drive(state, cascade(), done)
    assert unwound == [True]
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_orchestrator_cascade.py -m "not integration and not live_llm" -q`
Expected: `7 failed` / errors: `AttributeError: module 'pipeline.lyra.convergence_orchestrator' has no attribute '_TICK_S'`.

- [ ] **Step 3: Add the watch-loop functions**

In `pipeline/lyra/convergence_orchestrator.py`:

(a) change the imports to

```python
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any
```

(b) directly after the `_empty_paper_error` function, add:

```python
# Wall time between two ticks of the watch loop (_drive_cascade): progress log,
# DB flush, external-cancellation check and the SSE progress snapshot.
_TICK_S = 30.0

# After the done signal the cascade only unwinds (StatePersist's last passenger
# writes run on the way back up). It gets this long before it is cancelled.
_UNWIND_GRACE_S = 120.0

_NO_DOSSIER_ERROR = (
    "Research ended without a dossier: the event cascade finished but DossierReady never fired"
)


async def _drive_cascade(
    state: ResearchState,
    cascade_coro: Coroutine[Any, Any, None],
    done_event: asyncio.Event,
    deadline_handler: Any,
    *,
    request_id: str,
    emit: Callable[[dict], None],
    t0: float,
) -> None:
    """Run the event cascade as a task and watch it until the run is done.

    The whole run executes inside the cascade (EventBus.emit awaits every
    handler inline), so the watch loop must run beside it, not after it: only
    then do the deadline check, the 30 s DB flush and the external-cancellation
    check actually run. Returns when the done signal fired, when state.error is
    set, or when the cascade finished (without the done signal that is an
    error). Raises _CancelledByUser and whatever the cascade raised (quota
    errors included). The cascade never outlives this call.
    """
    cascade = asyncio.create_task(cascade_coro)
    try:
        while not done_event.is_set():
            forced = await deadline_handler.check_deadline()
            if forced and state.phase == ResearchPhase.DONE:
                break
            done_wait = asyncio.create_task(done_event.wait())
            try:
                await asyncio.wait(
                    {cascade, done_wait}, timeout=_TICK_S, return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                done_wait.cancel()
            if cascade.done():
                cascade.result()
                if not done_event.is_set() and not state.error:
                    state.error = _NO_DOSSIER_ERROR
                break
            if done_event.is_set() or state.error:
                break
            _tick(state, request_id, emit, t0)
    finally:
        await _settle_cascade(state, cascade, done_event, request_id)


def _tick(state: ResearchState, request_id: str, emit: Callable[[dict], None], t0: float) -> None:
    """One watch-loop tick: progress log, DB flush, external cancellation, live snapshot."""
    saturated = sum(1 for a in state.angles if a.saturated)
    total = len(state.angles)
    elapsed = int(time.monotonic() - t0)
    progress_msg = (
        f"Progress: {saturated}/{total} angles saturated, "
        f"phase={state.phase.value}, elapsed={elapsed}s, "
        f"llm_calls={state.llm_call_count}, "
        f"sources={len(state.registry.sources)}"
    )
    state.log("orchestrator", progress_msg)
    # Promote to logger so docker logs are no longer blind; the rest of the
    # pipeline emits via SSE only.
    logger.info("[THEO] %s %s", request_id, progress_msg)
    # Counters + recent debug_log to the DB, so the run is diagnosable from psql.
    _flush_progress_to_db(state, request_id)
    # Ghost-task guard (2026-06-29): the DB row's status is the source of truth.
    # If the user cancelled via the API (or the watchdog deferred the run), this
    # raises _CancelledByUser and _drive_cascade cancels the cascade. Live since
    # the cascade runs as a task (2026-09-26); before, it never ran.
    _check_external_cancellation(request_id)
    spec_count = len({f.get("specialist_id", "unknown") for a in state.angles for f in a.findings})
    emit(
        {
            "type": "progress",
            "stage": "orchestrator",
            "meta": {
                "phase": state.phase.value,
                "elapsed_s": elapsed,
                "angles_saturated": saturated,
                "angles_total": total,
                "llm_calls": state.llm_call_count,
                "sources_found": len(state.registry.sources),
                "tools_used": spec_count,
                "total_tokens": state.total_tokens,
            },
        }
    )


async def _settle_cascade(
    state: ResearchState, cascade: asyncio.Task, done_event: asyncio.Event, request_id: str
) -> None:
    """Let a finished run's cascade unwind for a grace period, cancel everything else."""
    if not cascade.done() and done_event.is_set() and not state.error:
        await asyncio.wait({cascade}, timeout=_UNWIND_GRACE_S)
    if not cascade.done():
        cascade.cancel()
    (outcome,) = await asyncio.gather(cascade, return_exceptions=True)
    if (
        done_event.is_set()
        and isinstance(outcome, BaseException)
        and not isinstance(outcome, asyncio.CancelledError)
    ):
        # The dossier is complete; an error while unwinding does not undo it,
        # but it must be visible.
        state.log("orchestrator", f"Cascade raised after the run was done: {outcome!r}")
        logger.error("[THEO] %s cascade raised after the run was done: %r", request_id, outcome)
```

(c) In `run()`, replace everything from the line `        try:` that follows `        t0 = time.monotonic()` down to (not including) `        except _CancelledByUser as exc:` — i.e. the `decompose()` call, the early return and the whole `while not done_event.is_set():` loop — with:

```python
        try:
            await _drive_cascade(
                state,
                decomposition.decompose(),
                done_event,
                deadline_handler,
                request_id=request_id,
                emit=emit,
                t0=t0,
            )
```

The two `except` blocks that follow stay unchanged.

- [ ] **Step 4: Run the new and the neighbouring tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_orchestrator_cascade.py tests/pipeline/test_empty_paper_guard.py tests/pipeline/test_research_events_quota.py -m "not integration and not live_llm" -q`
Expected: all pass (`7` new; `test_empty_paper_guard.py` still exists until Task 10).

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/convergence_orchestrator.py tests/pipeline/test_orchestrator_cascade.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/convergence_orchestrator.py tests/pipeline/test_orchestrator_cascade.py
git add pipeline/lyra/convergence_orchestrator.py tests/pipeline/test_orchestrator_cascade.py
git commit -m "Run Theo's event cascade as a task beside the watch loop so the deadline, the DB flush and cancellation finally run" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 10: The research-only cut

Register the DossierHandler, make `DossierReady` the done signal, replace the empty-paper guard with the dossier guard, and delete the M3 writing chain with its events, phases and tests. One commit: the pieces only make sense together.

**Files:**
- Modify (full content below): `pipeline/lyra/convergence_orchestrator.py`
- Modify: `pipeline/lyra/research_events.py` (delete lines 95-141: `PaperReady` … `QualityFailed`)
- Modify: `pipeline/lyra/research_state.py` (enum; pool comment 164-168)
- Modify: `pipeline/lyra/handlers/probative_images.py` (docstring, imports, delete class `ProbativeImagesHandler` 554-592)
- Modify: `pipeline/lyra/handlers/angle_image_research.py` (docstring lines 1-10), `pipeline/lyra/image_diversity.py` (docstring lines 1-5)
- Delete: `pipeline/lyra/handlers/paper.py`, `fact_check.py`, `presentation.py`, `image_generation.py`, `judge.py`; `tests/pipeline/test_paper_claim_pack.py`, `test_paper_repair_pass.py`, `test_paper_title_validation.py`, `test_empty_paper_guard.py`, `test_shining_ones_regen.py`
- Modify: `tests/pipeline/test_hex_token_scrubber.py` (its `test_handler_uses_same_regex` reads `handlers/paper.py` from disk)
- Test: `tests/pipeline/test_orchestrator_research_only.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_orchestrator_research_only.py`:

```python
"""Theo researches only: the run ends at the dossier (spec 2.1)."""

from __future__ import annotations

import asyncio
import importlib.util

from pipeline.lyra import convergence_orchestrator as co
from pipeline.lyra import research_events
from pipeline.lyra.research_events import DossierReady, EventBus, ModeratorComplete
from pipeline.lyra.research_state import ResearchPhase, ResearchState

REMOVED_HANDLERS = {
    "PaperHandler",
    "ProbativeImagesHandler",
    "FactCheckHandler",
    "PresentationHandler",
    "ImageGenerationHandler",
    "JudgeHandler",
}


def test_the_run_ends_at_the_dossier_handler():
    state = ResearchState(question="q", request_id="r")
    bus = EventBus(state=state)
    wiring = co._build_handlers(state, bus, asyncio.Semaphore(1))
    names = [type(handler).__name__ for handler in wiring.handlers]
    assert names.index("DossierHandler") == names.index("ModeratorHandler") + 1
    assert not REMOVED_HANDLERS & set(names)
    listeners = bus._handlers[ModeratorComplete]
    assert [type(listener.__self__).__name__ for listener in listeners] == ["DossierHandler"]
    assert type(wiring.decomposition).__name__ == "DecompositionHandler"
    assert type(wiring.deadline).__name__ == "DeadlineHandler"


async def test_dossier_ready_is_the_done_signal():
    state = ResearchState(question="q")
    bus = EventBus(state=state)
    events: list[dict] = []
    done = co._wire_done_signal(bus, state, events.append)
    await bus.emit(DossierReady(request_id="r1"))
    assert done.is_set()
    assert events[-1]["type"] == "status"


def test_the_dossier_guard_fails_a_run_without_a_dossier():
    state = ResearchState(question="q")
    co._dossier_guard(state)
    assert state.error == co._DOSSIER_GUARD_ERROR


def test_the_dossier_guard_keeps_an_earlier_error_and_passes_a_dossier():
    failed = ResearchState(question="q", error="Decomposition produced no research angles")
    co._dossier_guard(failed)
    assert failed.error == "Decomposition produced no research angles"
    done = ResearchState(question="q", dossier_ref=8)
    co._dossier_guard(done)
    assert done.error == ""


def test_the_writing_chain_is_gone():
    for name in (
        "PaperReady",
        "ProbativeImagesReady",
        "FactCheckComplete",
        "PresentationChecked",
        "ImageGenComplete",
        "QualityPassed",
        "QualityFailed",
    ):
        assert not hasattr(research_events, name), name
    assert {phase.name for phase in ResearchPhase} == {
        "DECOMPOSING",
        "EXPLORING",
        "SYNTHESIZING",
        "DEBATING",
        "MODERATING",
        "DONE",
    }
    for module in ("paper", "fact_check", "presentation", "image_generation", "judge"):
        assert importlib.util.find_spec(f"pipeline.lyra.handlers.{module}") is None, module
    from pipeline.lyra.handlers import probative_images

    assert not hasattr(probative_images, "ProbativeImagesHandler")
    assert callable(probative_images.embed_probative_images)
    assert not hasattr(co, "_empty_paper_error")
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_orchestrator_research_only.py -m "not integration and not live_llm" -q`
Expected: `5 failed` (`_build_handlers`, `_wire_done_signal`, `_dossier_guard` missing; writing chain present).

- [ ] **Step 3: Replace `pipeline/lyra/convergence_orchestrator.py` with the research-only version**

Full file content:

```python
"""Convergence-based research orchestrator: one Theo research run, research only.

Event-driven state machine. The question is decomposed into angles that
converge independently via specialist consensus; synthesis, debate and
moderation follow, and the run ends when the DossierHandler has persisted the
dossier and emitted DossierReady (spec
docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md, 2.1). The
paper is written afterwards in a Claude session, not here.

Usage (from theo_worker.py):
    orchestrator = ConvergenceOrchestrator()
    state = await orchestrator.run(question, emit, ...)
    # state has: dossier_ref, dossier_summary, error, quota_exhausted,
    # total_tokens, llm_call_count, debug_log, registry, specialist_analyses
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from pipeline.lyra.config import _get_settings
from pipeline.lyra.research_events import (
    AngleCreated,
    CrossPollinationComplete,
    DossierReady,
    EventBus,
)
from pipeline.lyra.research_state import (
    ResearchConfig,
    ResearchPhase,
    ResearchState,
    findings_by_specialist,
)

logger = logging.getLogger(__name__)

# Wall time between two ticks of the watch loop (_drive_cascade): progress log,
# DB flush, external-cancellation check and the SSE progress snapshot.
_TICK_S = 30.0

# After DossierReady the cascade only unwinds (StatePersist's last passenger
# writes run on the way back up). It gets this long before it is cancelled.
_UNWIND_GRACE_S = 120.0

_NO_DOSSIER_ERROR = (
    "Research ended without a dossier: the event cascade finished but DossierReady never fired"
)

_DOSSIER_GUARD_ERROR = (
    "Research finished without a persisted dossier: no DossierReady with at least one "
    "moderated final claim was recorded"
)


class _Wiring(NamedTuple):
    """The handlers of one run in bus registration order, plus the two the loop drives."""

    handlers: list
    decomposition: Any
    deadline: Any


def _build_handlers(state: ResearchState, bus: EventBus, semaphore: asyncio.Semaphore) -> _Wiring:
    """Instantiate and register every handler of a research-only run.

    Event flow:
    AngleCreated -> search -> SourcesFound -> audit -> SourcesAudited
                \\-> angle_image_research -> (pool populated, no blocking event)
    -> content_fetch -> ContentFetched -> specialist -> FindingsProduced
    -> convergence check -> (loop or saturate)
    AllAnglesSaturated -> synthesis -> SynthesisReady -> debate
    -> DebateComplete -> moderator -> ModeratorComplete -> dossier -> DossierReady

    Registration order is dispatch order per event: the DossierHandler is the
    only listener on ModeratorComplete; StatePersist, registered last, writes
    its passenger artifacts after the stage handlers of the same event.
    """
    # Lazy imports to avoid circular dependencies
    from pipeline.lyra.handlers.angle_audit import AuditHandler
    from pipeline.lyra.handlers.angle_image_research import AngleImageResearchHandler
    from pipeline.lyra.handlers.angle_search import SearchHandler
    from pipeline.lyra.handlers.angle_specialist import SpecialistHandler
    from pipeline.lyra.handlers.content_fetch import ContentFetchHandler
    from pipeline.lyra.handlers.convergence_checker import ConvergenceChecker
    from pipeline.lyra.handlers.cross_pollination import CrossPollinationHandler
    from pipeline.lyra.handlers.deadline import DeadlineHandler
    from pipeline.lyra.handlers.debate import DebateHandler
    from pipeline.lyra.handlers.decomposition import DecompositionHandler
    from pipeline.lyra.handlers.dossier import DossierHandler
    from pipeline.lyra.handlers.moderator import ModeratorHandler
    from pipeline.lyra.handlers.state_persist import StatePersistHandler
    from pipeline.lyra.handlers.synthesis import SynthesisHandler

    decomposition = DecompositionHandler(state, bus, semaphore)
    deadline = DeadlineHandler(state, bus, semaphore)
    handlers = [
        decomposition,
        SearchHandler(state, bus, semaphore),
        AngleImageResearchHandler(state, bus, semaphore),
        AuditHandler(state, bus, semaphore),
        ContentFetchHandler(state, bus, semaphore),
        SpecialistHandler(state, bus, semaphore),
        ConvergenceChecker(state, bus, semaphore),
        CrossPollinationHandler(state, bus, semaphore),
        SynthesisHandler(state, bus, semaphore),
        DebateHandler(state, bus, semaphore),
        ModeratorHandler(state, bus, semaphore),
        DossierHandler(state, bus, semaphore),
        deadline,
        StatePersistHandler(state, bus, semaphore),
    ]
    for handler in handlers:
        handler.register()
        # angle_specialist looks the SearchHandler up by class (bus.get_handler).
        bus.register_instance(handler)
    return _Wiring(handlers=handlers, decomposition=decomposition, deadline=deadline)


def _wire_done_signal(
    bus: EventBus, state: ResearchState, emit: Callable[[dict], None]
) -> asyncio.Event:
    """DossierReady ends the run (it replaced QualityPassed with the research-only split)."""
    done_event = asyncio.Event()

    async def _on_dossier_ready(event: DossierReady):
        state.log("orchestrator", f"Dossier ready for {event.request_id}")
        emit(
            {
                "type": "status",
                "content": "Dossier ready: research complete, the paper is written next",
            }
        )
        done_event.set()

    bus.on(DossierReady, _on_dossier_ready)
    return done_event


def _dossier_guard(state: ResearchState) -> None:
    """Spec 2.1: a run succeeds only with a persisted dossier (replaces the empty-paper guard)."""
    if state.error or state.dossier_ref is not None:
        return
    state.error = _DOSSIER_GUARD_ERROR
    logger.error("[THEO] dossier guard tripped, failing the run: %s", _DOSSIER_GUARD_ERROR)


class ConvergenceOrchestrator:
    """Event-driven research pipeline with convergence-based quality gates."""

    def __init__(self, settings=None):
        self._settings = settings or _get_settings()

    async def run(
        self,
        question: str,
        emit: Callable[[dict], None],
        *,
        request_id: str = "",
        force_include: list[str] | None = None,
        force_exclude: list[str] | None = None,
        video_ids: list[str] | None = None,
        web_urls: list[str] | None = None,
        disabled_adapters: list[str] | None = None,
        low_priority: bool = True,
    ) -> ResearchState:
        """Run one research-only convergence pipeline.

        Returns the ResearchState the worker reads: dossier_ref and
        dossier_summary on success, error / quota_exhausted otherwise, plus
        total_tokens, llm_call_count, debug_log, registry and specialist_analyses.
        """
        config = ResearchConfig()
        state = ResearchState(
            question=question,
            request_id=request_id,
            seed_urls=list(web_urls or []),
            seed_video_ids=list(video_ids or []),
            force_include=list(force_include or []),
            force_exclude=list(force_exclude or []),
            disabled_adapters=list(disabled_adapters or []),
            config=config,
            emit=emit,
            started_at=datetime.now(UTC),
            deadline=datetime.now(UTC) + timedelta(hours=config.deadline_hours),
        )

        state.log("orchestrator", f"Starting convergence pipeline for: {question[:80]}...")

        # Quota preflight (2026-06-28, Layer 2 of the rate-limit-defense plan).
        # Probe the MiniMax Token Plan 5h-rolling remaining budget. If it's
        # below a sane floor for a full research run, raise InsufficientQuotaError
        # *before* making any LLM calls — the worker marks the request 'deferred'
        # and re-queues it after the 5h window resets.
        # The probe is fail-soft: if the endpoint doesn't exist (some plans) or
        # any error happens, we proceed. The limiter's quota-freeze still catches
        # mid-run exhaustion.
        from pipeline.lyra.minimax_limiter import InsufficientQuotaError
        from pipeline.lyra.minimax_shared import probe_minimax_quota

        quota = probe_minimax_quota()
        if quota.get("ok"):
            # The normalised fields are set by probe_minimax_quota() from the
            # MiniMax-native model_remains[0]. Floor at 5% — below this a
            # Decomposition call (~5k tokens) plus the cheapest search rounds
            # can't reliably finish, and the run will stall at 45min. The
            # worker marks the request 'deferred' so it's re-claimed after
            # the 5h window resets.
            remaining_5h_pct = quota.get("five_hour_remaining_percent")
            if remaining_5h_pct is not None and remaining_5h_pct < 5:
                state.log(
                    "orchestrator",
                    f"Preflight: 5h remaining={remaining_5h_pct}% < 5% floor — "
                    f"refusing to start, will be deferred by worker.",
                )
                raise InsufficientQuotaError(
                    f"MiniMax 5h-rolling remaining={remaining_5h_pct}% is below "
                    f"the 5% floor; deferring until window resets. Full probe: "
                    f"{json.dumps(quota, default=str)[:300]}"
                )
            # Probe says quota is healthy — if the limiter was frozen from a
            # previous quota hit, lift the freeze so calls can resume.
            from pipeline.lyra.minimax_limiter import limiter as global_limiter

            if global_limiter.is_frozen():
                state.log(
                    "orchestrator",
                    f"Preflight: quota healthy ({remaining_5h_pct}%); "
                    f"unfreezing global limiter (was frozen).",
                )
                global_limiter.unfreeze()
        # else: probe failed (endpoint missing / network error) — proceed and
        # rely on the limiter's quota-freeze for mid-run protection.

        # Run-priority lane (2026-07-26): batch runs bind the crawl lane —
        # their MiniMax calls pace at concurrency 1 with >= crawl-delay gaps
        # so background research never outpaces the shared 5h window.
        # Interactive (UI) runs stay on the full-speed adaptive lane and can
        # execute CONCURRENTLY with a crawling batch run (two worker slots).
        # The contextvar propagates through create_task/to_thread, so every
        # LLM call in this run's handler tree lands on the right lane.
        from pipeline.lyra.minimax_limiter import bind_low_priority

        run_low = bool(low_priority and self._settings.theo_low_priority)
        bind_low_priority(run_low)
        state.log(
            "orchestrator",
            "Crawl lane bound: low-priority run, concurrency 1, >=crawl-delay gaps."
            if run_low
            else "Full-speed lane bound: interactive run.",
        )

        # Bind state for token accounting. LLM helpers (minimax_shared.py,
        # config.call_api) read this contextvar to credit token usage back
        # to state.total_tokens without needing the state object threaded
        # through every signature.
        from pipeline.lyra import token_accounting

        token_accounting.bind(state)

        # NOTE (2026-06-28): The previous call `global_limiter.reset()` was
        # removed. The MiniMax Token Plan is a global 5h-rolling quota shared
        # across all pipelines; resetting to max_concurrency=100 at the start
        # of every Theo run wiped learned backoff state and was the direct
        # cause of the 82%-rate-limited 52-prompt batch. The limiter now
        # learns continuously; no per-task reset.

        # Event bus and handlers. The bus surfaces handler exceptions into
        # state.error, which the watch loop (_drive_cascade) reads.
        bus = EventBus(state=state)
        semaphore = asyncio.Semaphore(config.max_concurrent_llm_calls)
        wiring = _build_handlers(state, bus, semaphore)

        # Wire cross-pollination complete -> trigger round 2 via AngleCreated events.
        # This naturally flows: AngleCreated -> search -> audit -> content_fetch -> specialist.
        # The specialist handler skips its own search trigger for round 2
        # (only triggers for round 3+), preventing double-triggering.
        async def _on_cross_pollination_complete(event: CrossPollinationComplete):
            """After cross-pollination, kick off next round for all unsaturated angles."""
            state.log("orchestrator", "Cross-pollination complete, starting next round")
            emit(
                {
                    "type": "status",
                    "content": "Cross-pollination complete -- starting next round...",
                }
            )
            for angle in state.angles:
                if not angle.saturated:
                    await bus.emit(AngleCreated(angle_id=angle.id))

        bus.on(CrossPollinationComplete, _on_cross_pollination_complete)

        done_event = _wire_done_signal(bus, state, emit)

        # Register seed URLs as sources
        for url in state.seed_urls:
            state.registry.register_source(
                url=url,
                title=url.split("/")[-1].replace("-", " ").replace("_", " ")[:80] or url[:80],
                snippet="User-provided source -- content will be fetched",
            )

        # Specialist panel is no longer selected globally at startup.
        # Each angle selects its own specialists dynamically based on its domains
        # (see SpecialistHandler._on_content_fetched). The state.panel list is
        # populated lazily as angles assign specialists.
        state.log("orchestrator", "Specialist selection deferred to per-angle assignment")

        # --- Run the pipeline ---
        t0 = time.monotonic()

        try:
            await _drive_cascade(
                state,
                wiring.decomposition.decompose(),
                done_event,
                wiring.deadline,
                request_id=request_id,
                emit=emit,
                t0=t0,
            )
        except _CancelledByUser as exc:
            # User-cancellation (DB status changed to 'cancelled' or 'deferred').
            # Set a clean state.error so the worker's `"cancelled" in ctx.error`
            # branch fires and the task is marked 'cancelled' with credits
            # released. Don't re-raise — the worker should treat this as a
            # graceful stop, not a crash.
            state.error = f"Cancelled by user: {exc}"
            logger.info("[THEO] %s cancelled by user: %s", request_id, exc)
        except Exception as exc:
            # Quota errors must propagate so the worker can mark the request
            # 'deferred' rather than 'failed'. Without the re-raise, the
            # worker only sees state.error and treats it as a generic
            # failure — defeating the 2026-06-28 quota-aware design where
            # deferred rows are re-claimed after the 5h window resets.
            from pipeline.lyra.minimax_limiter import (
                InsufficientQuotaError,
                QuotaExhaustedError,
            )

            if isinstance(exc, (QuotaExhaustedError, InsufficientQuotaError)):
                # Flush progress before re-raising (audit P19): the deferred
                # run is re-claimed after the 5h window resets, and without
                # this flush the research_requests row loses everything since
                # the last 30s tick — debug_log/tokens/llm_calls read as
                # stale/NULL while the request sits in 'deferred'.
                # _flush_progress_to_db is best-effort and never raises.
                _flush_progress_to_db(state, request_id)
                raise
            state.error = f"Pipeline error: {exc}"
            logger.exception("Convergence pipeline failed")

        duration_ms = int((time.monotonic() - t0) * 1000)
        state.log(
            "orchestrator", f"Pipeline finished in {duration_ms}ms, phase={state.phase.value}"
        )

        # The worker reports len(specialist_analyses) as tools_used.
        state.specialist_analyses = findings_by_specialist(state.angles)

        _dossier_guard(state)

        # Persist the run's knowledge-graph contribution (angle tree + open
        # rabbit holes as frontier). The paper node is labelled with the
        # question (there is no paper title at research end). Best-effort inside.
        if request_id and not state.error:
            from pipeline.lyra.research_graph import persist_state_graph

            persist_state_graph(state, request_id)

        return state


async def _drive_cascade(
    state: ResearchState,
    cascade_coro: Coroutine[Any, Any, None],
    done_event: asyncio.Event,
    deadline_handler: Any,
    *,
    request_id: str,
    emit: Callable[[dict], None],
    t0: float,
) -> None:
    """Run the event cascade as a task and watch it until the run is done.

    The whole run executes inside the cascade (EventBus.emit awaits every
    handler inline), so the watch loop must run beside it, not after it: only
    then do the deadline check, the 30 s DB flush and the external-cancellation
    check actually run. Returns when DossierReady fired, when state.error is
    set, or when the cascade finished (without DossierReady that is an error).
    Raises _CancelledByUser and whatever the cascade raised (quota errors
    included). The cascade never outlives this call.
    """
    cascade = asyncio.create_task(cascade_coro)
    try:
        while not done_event.is_set():
            forced = await deadline_handler.check_deadline()
            if forced and state.phase == ResearchPhase.DONE:
                break
            done_wait = asyncio.create_task(done_event.wait())
            try:
                await asyncio.wait(
                    {cascade, done_wait}, timeout=_TICK_S, return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                done_wait.cancel()
            if cascade.done():
                cascade.result()
                if not done_event.is_set() and not state.error:
                    state.error = _NO_DOSSIER_ERROR
                break
            if done_event.is_set() or state.error:
                break
            _tick(state, request_id, emit, t0)
    finally:
        await _settle_cascade(state, cascade, done_event, request_id)


def _tick(state: ResearchState, request_id: str, emit: Callable[[dict], None], t0: float) -> None:
    """One watch-loop tick: progress log, DB flush, external cancellation, live snapshot."""
    saturated = sum(1 for a in state.angles if a.saturated)
    total = len(state.angles)
    elapsed = int(time.monotonic() - t0)
    progress_msg = (
        f"Progress: {saturated}/{total} angles saturated, "
        f"phase={state.phase.value}, elapsed={elapsed}s, "
        f"llm_calls={state.llm_call_count}, "
        f"sources={len(state.registry.sources)}"
    )
    state.log("orchestrator", progress_msg)
    # Promote to logger so docker logs are no longer blind; the rest of the
    # pipeline emits via SSE only.
    logger.info("[THEO] %s %s", request_id, progress_msg)
    # Counters + recent debug_log to the DB, so the run is diagnosable from psql.
    _flush_progress_to_db(state, request_id)
    # Ghost-task guard (2026-06-29): the DB row's status is the source of truth.
    # If the user cancelled via the API (or the watchdog deferred the run), this
    # raises _CancelledByUser and _drive_cascade cancels the cascade. Live since
    # the cascade runs as a task (2026-09-26); before, it never ran.
    _check_external_cancellation(request_id)
    spec_count = len({f.get("specialist_id", "unknown") for a in state.angles for f in a.findings})
    emit(
        {
            "type": "progress",
            "stage": "orchestrator",
            "meta": {
                "phase": state.phase.value,
                "elapsed_s": elapsed,
                "angles_saturated": saturated,
                "angles_total": total,
                "llm_calls": state.llm_call_count,
                "sources_found": len(state.registry.sources),
                "tools_used": spec_count,
                "total_tokens": state.total_tokens,
            },
        }
    )


async def _settle_cascade(
    state: ResearchState, cascade: asyncio.Task, done_event: asyncio.Event, request_id: str
) -> None:
    """Let a finished run's cascade unwind for a grace period, cancel everything else."""
    if not cascade.done() and done_event.is_set() and not state.error:
        await asyncio.wait({cascade}, timeout=_UNWIND_GRACE_S)
    if not cascade.done():
        cascade.cancel()
    (outcome,) = await asyncio.gather(cascade, return_exceptions=True)
    if (
        done_event.is_set()
        and isinstance(outcome, BaseException)
        and not isinstance(outcome, asyncio.CancelledError)
    ):
        # The dossier is complete; an error while unwinding does not undo it,
        # but it must be visible.
        state.log("orchestrator", f"Cascade raised after the run was done: {outcome!r}")
        logger.error("[THEO] %s cascade raised after the run was done: %r", request_id, outcome)


def _flush_progress_to_db(state, request_id: str) -> None:
    """Persist in-flight counters + recent debug_log to research_requests.

    Called on every watch-loop tick (every 30s) and piggybacked on
    EventBus.emit, so a stalled vs healthy run can be distinguished from psql
    alone. The final write in theo_worker.py overwrites everything anyway, so
    partial values here are safe to keep loose.
    """
    if not request_id:
        return
    try:
        from sqlalchemy import text

        from pipeline.database import get_session

        # Count unique specialists with at least one finding so far —
        # matches the completion-time tools_used semantics.
        spec_ids = {
            finding.get("specialist_id", "unknown")
            for angle in state.angles
            for finding in angle.findings
        }
        with get_session() as session:
            session.execute(
                text(
                    """
                    UPDATE research_requests
                    SET llm_calls    = :llm_calls,
                        total_tokens = :tokens,
                        sites_found  = :sites,
                        tools_used   = :tools,
                        debug_log    = :debug_log
                    WHERE id = :id
                    """
                ),
                {
                    "id": request_id,
                    "llm_calls": state.llm_call_count,
                    "tokens": state.total_tokens,
                    "sites": len(state.registry.sources),
                    "tools": len(spec_ids),
                    # Cap to keep the update cheap and avoid bloating the row
                    # mid-run (the completion write later replaces the full log).
                    "debug_log": json.dumps(state.debug_log[-200:]),
                },
            )
            session.commit()
    except Exception as exc:
        # Never let a diagnostic write break the pipeline.
        logger.warning("[THEO] DB progress flush failed: %s", exc)


class _CancelledByUser(Exception):
    """Raised when the orchestrator detects the DB status is no longer 'running'.

    The worker writes status='cancelled' to the DB when a user cancels via
    DELETE /research/{id}, but the in-flight asyncio task has no direct
    signal. The watch loop polls the DB every 30s; if status != 'running',
    this is raised so the worker can catch it cleanly and unwind credits.
    """


def _check_external_cancellation(request_id: str) -> None:
    """Read research_requests.status for `request_id`. If it's no longer
    'running' (e.g. user cancelled via API, watchdog marked deferred, etc.),
    raise ``_CancelledByUser`` so the watch loop unwinds.

    Called on every watch-loop tick. Best-effort: a transient DB error must NOT
    kill the pipeline — only a confirmed non-'running' status triggers the cancel.
    """
    if not request_id:
        return
    try:
        from sqlalchemy import text

        from pipeline.database import get_session

        with get_session() as session:
            row = session.execute(
                text("SELECT status FROM research_requests WHERE id = :id"),
                {"id": request_id},
            ).fetchone()
        if row is None:
            # Row vanished (manual cleanup). Treat as cancellation.
            raise _CancelledByUser(f"Research request {request_id} no longer exists")
        if row[0] != "running":
            raise _CancelledByUser(
                f"Research request {request_id} status changed to '{row[0]}' "
                f"while orchestrator was running"
            )
    except _CancelledByUser:
        raise
    except Exception as exc:
        # Best-effort: never let a DB read error kill the pipeline.
        logger.warning("[THEO] Cancellation check failed (continuing): %s", exc)
```

- [ ] **Step 4: Remove the writing events from `research_events.py`**

Delete the classes `PaperReady`, `ProbativeImagesReady`, `FactCheckComplete`, `PresentationChecked`, `ImageGenComplete`, `QualityPassed` and `QualityFailed` (the block between `DossierReady` and `NewAngleDiscovered`). Nothing else changes.

- [ ] **Step 5: Remove the writing phases from `research_state.py`**

```python
class ResearchPhase(enum.Enum):
    DECOMPOSING = "decomposing"
    EXPLORING = "exploring"
    SYNTHESIZING = "synthesizing"
    DEBATING = "debating"
    MODERATING = "moderating"
    DONE = "done"
```

and replace the comment above `image_candidate_pool` with:

```python
    # Image research pool — populated by AngleImageResearchHandler in parallel
    # with angle_search. Keyed by angle.id, values are serialized ImageCandidate
    # dicts (dataclass round-trip via asdict). Persisted in the dossier
    # (image_candidate_pool kind); the Claude image check picks from it.
```

- [ ] **Step 6: Delete the probative-image handler class, keep the helpers**

In `pipeline/lyra/handlers/probative_images.py`:
- replace the module docstring with:

```python
"""Probative-image embedding for research papers.

`embed_probative_images()` fetches, gates and embeds images into a paper. The
live pipeline no longer calls it (Theo researches only since 2026-09-26); the
backfill CLI (pipeline/lyra/backfill_probative_images.py) does, and the Claude
image check reuses the dedup helpers `_claim_image_content` and `_limit_tagged`.
"""
```

- delete the imports `from pipeline.lyra.handlers import BaseHandler`, `from pipeline.lyra.research_events import PaperReady, ProbativeImagesReady` and `from pipeline.lyra.research_state import ResearchPhase`;
- delete the whole `class ProbativeImagesHandler(BaseHandler):` block (it ends right before `async def _process_one_opportunity(`);
- in the `embed_probative_images` docstring replace "Reusable from both the live pipeline handler and the backfill CLI. Does all the work that used to live inside `ProbativeImagesHandler._on_paper_ready` except for event-bus emissions and state-machine transitions." with "Used by the backfill CLI."

- [ ] **Step 7: Fix the two docstrings that named the handler**

`pipeline/lyra/handlers/angle_image_research.py`, module docstring:

```python
"""Handler: populates state.image_candidate_pool per angle.

Runs in parallel with angle_search (both listen on AngleCreated). For each
angle, asks a specialist for 3-5 short image queries, fans those out across
the imagery connectors, dedupes, and stores serialized ImageCandidate dicts
in the state pool. The DossierHandler persists the pool; the Claude image
check picks from it.

If the feature flag is off, this handler no-ops so the pool stays empty.
"""
```

`pipeline/lyra/image_diversity.py`, first paragraph of the docstring:

```python
"""Diversity scoring for the probative-image selection.

Computed after embed_probative_images() finishes embedding images. Used to surface
"are we drawing from a wide spectrum of sources?" telemetry rather than silently
accepting a paper with 8 images all from Wikimedia.
```

(keep the rest of that docstring unchanged).

- [ ] **Step 8: Delete the writing chain and the tests that only covered it**

```bash
git rm pipeline/lyra/handlers/paper.py pipeline/lyra/handlers/fact_check.py pipeline/lyra/handlers/presentation.py pipeline/lyra/handlers/image_generation.py pipeline/lyra/handlers/judge.py tests/pipeline/test_paper_claim_pack.py tests/pipeline/test_paper_repair_pass.py tests/pipeline/test_paper_title_validation.py tests/pipeline/test_empty_paper_guard.py tests/pipeline/test_shining_ones_regen.py
```

In `tests/pipeline/test_hex_token_scrubber.py` delete the function `test_handler_uses_same_regex` (the last test; it pins a regex inside the deleted `paper.py`) and replace the comment above `_HEX_TOKEN_RE` with:

```python
# The scrub the M3 writer applied (handlers/paper.py Step 7.8, removed with the
# writing chain on 2026-09-26). The pattern stays as the audit's reference case
# for stray source-id tokens in prose.
```

- [ ] **Step 9: Nothing may still reference the removed names**

Run: `grep -rnE "PaperReady|ProbativeImagesReady|FactCheckComplete|PresentationChecked|ImageGenComplete|QualityPassed|QualityFailed|ResearchPhase\.(WRITING|IMAGE_CURATION|JUDGING)|handlers\.(paper|judge|presentation|fact_check|image_generation)|ProbativeImagesHandler|_empty_paper_error" --include=*.py pipeline api scripts tests`
Expected: only the assertions in `tests/pipeline/test_orchestrator_research_only.py` and one comment line in `api/services/theo_worker.py` (`_paper_artifact`'s docstring, deleted in Task 13).

- [ ] **Step 10: Run the orchestrator and pipeline tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_orchestrator_research_only.py tests/pipeline/test_orchestrator_cascade.py tests/pipeline/test_dossier_handler.py tests/pipeline/test_state_persist.py tests/pipeline/test_research_state_dossier.py tests/pipeline/test_image_content_dedup.py tests/pipeline/test_backfill_probative_replace.py tests/pipeline/test_research_graph.py tests/pipeline/test_hex_token_scrubber.py -m "not integration and not live_llm" -q`
Expected: all pass.

Run the Lyra-image import check (the Lyra image has no markdown, nh3 or api):
`./.venv/Scripts/python.exe -c "import sys; sys.modules['markdown']=None; sys.modules['nh3']=None; import pipeline.lyra.orchestrator"`
Expected: no output, exit code 0.

- [ ] **Step 11: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/convergence_orchestrator.py pipeline/lyra/research_events.py pipeline/lyra/research_state.py pipeline/lyra/handlers/probative_images.py pipeline/lyra/handlers/angle_image_research.py pipeline/lyra/image_diversity.py tests/pipeline/test_orchestrator_research_only.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/ tests/pipeline/test_orchestrator_research_only.py
./.venv/Scripts/python.exe -m vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80
git add pipeline/lyra/convergence_orchestrator.py pipeline/lyra/research_events.py pipeline/lyra/research_state.py pipeline/lyra/handlers/probative_images.py pipeline/lyra/handlers/angle_image_research.py pipeline/lyra/image_diversity.py tests/pipeline/test_orchestrator_research_only.py tests/pipeline/test_hex_token_scrubber.py
git commit -m "Make Theo research only: the run ends when the dossier is persisted and the M3 writing chain is gone" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(The `git rm` of Step 8 is already staged; this commit contains both.) vulture must print nothing.

---

## Task 11: `embed_probative_images` returns five parts when disabled

The disabled branch returns a 3-tuple (probative_images.py:418) while the backfill unpacks five (backfill_probative_images.py:166): `ValueError` whenever `probative_images_enabled` is off.

**Files:**
- Modify: `pipeline/lyra/handlers/probative_images.py` (signature annotation ~line 383, return at ~line 418)
- Test: `tests/pipeline/test_probative_disabled_return.py`

- [ ] **Step 1: Write the failing test**

```python
"""embed_probative_images returns the same five parts whether enabled or not."""

from types import SimpleNamespace

from pipeline.lyra.handlers.probative_images import embed_probative_images


async def test_disabled_embed_returns_five_parts_like_an_enabled_one():
    out = await embed_probative_images(
        "11111111-2222-3333-4444-555555555555",
        "paper text",
        "q",
        [],
        None,
        settings=SimpleNamespace(probative_images_enabled=False),
    )
    assert out == ("paper text", [], {}, {}, {})
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_probative_disabled_return.py -m "not integration and not live_llm" -q`
Expected: `1 failed` (`('paper text', [], {}) != ('paper text', [], {}, {}, {})`).

- [ ] **Step 3: Fix the return and the annotation**

In `embed_probative_images` change the return annotation to

```python
) -> tuple[str, list[dict], dict, dict[str, int], dict[str, int]]:
```

the docstring's Returns paragraph to "tuple of (new_paper_text, embedded_list, diversity_dict, strategy_counts, skip_reasons).", and the disabled branch to

```python
    if not getattr(settings, "probative_images_enabled", True):
        print("[probative] disabled by config, skipping", flush=True)
        return (paper_text, [], {}, {}, {})
```

- [ ] **Step 4: Run the test**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_probative_disabled_return.py tests/pipeline/test_backfill_probative_replace.py -m "not integration and not live_llm" -q`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/handlers/probative_images.py tests/pipeline/test_probative_disabled_return.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/handlers/probative_images.py tests/pipeline/test_probative_disabled_return.py
git add pipeline/lyra/handlers/probative_images.py tests/pipeline/test_probative_disabled_return.py
git commit -m "Return all five parts from embed_probative_images when images are disabled, as the backfill unpacks them" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 12: Delete the writing prompts and the LLM calls that read them

Task 1 ported the editorial spec. The deterministic parts of `coherence_pass` and `hallucination_gate` stay for stream C's local gates.

**Files:**
- Delete: `pipeline/lyra/prompts/v2_paper_outline.txt`, `v2_paper_hook.txt`, `v2_paper_section.txt`, `v2_paper_connecting.txt`, `v2_paper_otherside.txt`, `v2_paper_assessment.txt`, `coherence_pass.txt`, `hallucination_repair.txt`
- Modify: `pipeline/lyra/coherence_pass.py`, `pipeline/lyra/hallucination_gate.py`
- Modify: `tests/pipeline/test_coherence_pass.py`, `tests/pipeline/test_hallucination_gate.py`
- Test: `tests/pipeline/test_research_only_prompts.py`

- [ ] **Step 1: Write the failing test**

`tests/pipeline/test_research_only_prompts.py`:

```python
"""The M3 writing prompts and the LLM calls that read them are gone (research-only split)."""

from pathlib import Path

from pipeline.lyra import coherence_pass, hallucination_gate

PROMPTS = Path(__file__).resolve().parents[2] / "pipeline" / "lyra" / "prompts"
GONE = (
    "v2_paper_outline.txt",
    "v2_paper_hook.txt",
    "v2_paper_section.txt",
    "v2_paper_connecting.txt",
    "v2_paper_otherside.txt",
    "v2_paper_assessment.txt",
    "coherence_pass.txt",
    "hallucination_repair.txt",
)


def test_writing_prompts_are_deleted():
    assert [name for name in GONE if (PROMPTS / name).exists()] == []


def test_only_the_deterministic_checks_remain():
    assert not hasattr(coherence_pass, "run_coherence_pass")
    assert not hasattr(hallucination_gate, "repair_prose")
    for name in ("extract_title_terms", "check_title_terms_in_body", "extract_numeric_claims"):
        assert callable(getattr(coherence_pass, name))
    for name in ("extract_specifics", "verify_against_pack", "delete_sentences_with_specifics"):
        assert callable(getattr(hallucination_gate, name))
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_research_only_prompts.py -m "not integration and not live_llm" -q`
Expected: `2 failed`.

- [ ] **Step 3: Delete the prompts**

```bash
git rm pipeline/lyra/prompts/v2_paper_outline.txt pipeline/lyra/prompts/v2_paper_hook.txt pipeline/lyra/prompts/v2_paper_section.txt pipeline/lyra/prompts/v2_paper_connecting.txt pipeline/lyra/prompts/v2_paper_otherside.txt pipeline/lyra/prompts/v2_paper_assessment.txt pipeline/lyra/prompts/coherence_pass.txt pipeline/lyra/prompts/hallucination_repair.txt
```

- [ ] **Step 4: Strip the LLM call from `coherence_pass.py`**

- Module docstring becomes:

```python
"""Deterministic coherence checks for Theo research papers.

  - Title-term definitions: every multi-word phrase in the title must appear
    in the body (extract_title_terms / check_title_terms_in_body).
  - Numeric claims: every measurement with its section and sentence
    (extract_numeric_claims), the input for a numeric-conflict review.

The LLM coherence pass (run_coherence_pass) was removed with Theo's M3 writing
chain on 2026-09-26; the dataclasses stay as the result shapes of those reviews.
"""
```

- Delete the imports `import logging`, `from pathlib import Path`, `from pipeline.lyra.minimax_shared import parse_fenced_json`, and the lines `logger = logging.getLogger(__name__)` and `_PROMPTS = Path(__file__).resolve().parent / "prompts"`.
- Delete the functions `_format_numeric_claims_for_prompt` and `run_coherence_pass` (everything after `check_title_terms_in_body`).

- [ ] **Step 5: Strip the LLM repair from `hallucination_gate.py`**

- Module docstring becomes:

```python
"""Hallucination gate for Theo research paper prose.

Extracts specific claims from prose (person names, book titles, years,
measurements, quoted phrases) and verifies each appears in the evidence pack,
source texts or user question. delete_sentences_with_specifics removes the
sentences that still carry unsupported specifics. The LLM repair loop
(repair_prose) was removed with Theo's M3 writing chain on 2026-09-26.
"""
```

- Delete `import logging`, `from pathlib import Path`, `logger = logging.getLogger(__name__)`, `_PROMPTS = Path(__file__).resolve().parent / "prompts"`.
- Rename the section banner `# Repair loop — LLM retries + mechanical sentence deletion fallback` to `# Mechanical sentence deletion`.
- Delete the function `repair_prose` (the last function of the module).

- [ ] **Step 6: Drop the tests of the removed calls**

In `tests/pipeline/test_coherence_pass.py`: remove `run_coherence_pass`, `CoherenceResult`, `Contradiction` and `NumericConflict` from the import list; delete the section `# run_coherence_pass` (the four `@pytest.mark.asyncio` tests from `test_run_coherence_pass_parses_llm_output` to `test_run_coherence_pass_ignores_empty_entity_contradictions`) and the section `# run_coherence_pass — numeric_conflicts wiring` (the three tests from `test_run_coherence_pass_parses_numeric_conflicts` to the end of the file); remove `import pytest` if nothing else in the file uses it.

In `tests/pipeline/test_hallucination_gate.py`: remove `repair_prose` from the import list; delete the section `# repair_prose` (the four async tests at the end of the file); remove `import pytest` if nothing else uses it.

- [ ] **Step 7: Run the affected tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_research_only_prompts.py tests/pipeline/test_coherence_pass.py tests/pipeline/test_hallucination_gate.py -m "not integration and not live_llm" -q`
Expected: all pass (`2` new, 11 coherence, 20 hallucination).

Check nothing else reads the deleted prompts: `grep -rnE "v2_paper_|coherence_pass\.txt|hallucination_repair" --include=*.py pipeline api scripts tests`
Expected: only `tests/pipeline/test_research_only_prompts.py`.

- [ ] **Step 8: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/coherence_pass.py pipeline/lyra/hallucination_gate.py tests/pipeline/test_coherence_pass.py tests/pipeline/test_hallucination_gate.py tests/pipeline/test_research_only_prompts.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/coherence_pass.py pipeline/lyra/hallucination_gate.py tests/pipeline/test_coherence_pass.py tests/pipeline/test_hallucination_gate.py tests/pipeline/test_research_only_prompts.py
git add pipeline/lyra/coherence_pass.py pipeline/lyra/hallucination_gate.py tests/pipeline/test_coherence_pass.py tests/pipeline/test_hallucination_gate.py tests/pipeline/test_research_only_prompts.py
git commit -m "Delete Theo's M3 writing prompts and the LLM repair and coherence calls that read them, keeping the deterministic checks" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(The `git rm` of Step 3 is staged and goes into the same commit.)

---

## Task 13: The worker ends a successful run as `researched`

**Files:**
- Modify: `api/services/theo_worker.py` (header docstring, imports lines 26-28, `_paper_artifact` 255-274, `_persist_training_corpus` 300-322, success branch 494-586, `_auto_publish` 771-922)
- Modify: `api/services/theo_config.py` (lines 23-27)
- Test: `tests/api/test_theo_worker_researched.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_theo_worker_researched.py`:

```python
"""The worker's research-only branch (spec 2.4): researched, dossier summary, no auto-publish."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from api.services import theo_worker as tw
from tests.fake_sql import RecordingSession

REQ = "11111111-2222-3333-4444-555555555555"
SUMMARY = {
    "artifact_id": 8812,
    "version": 1,
    "created_at": "2026-09-28T09:14:03+00:00",
    "counts": {
        "angles": 7,
        "findings": 2937,
        "sources": 3697,
        "final_claims": 38,
        "revised_claims": 5,
        "speculative_claims": 9,
        "images": 150,
    },
    "archive": {"cited_sources": 171, "full_text": 150, "abstract_only": 12, "missing": 6, "tdm_reserved": 3},
}


def _run(monkeypatch, session: RecordingSession) -> dict[str, list]:
    calls: dict[str, list] = {"credits": [], "corpus": [], "explored": [], "thinking": [], "webhook": []}
    ctx = SimpleNamespace(
        error="",
        quota_exhausted=False,
        dossier_summary=SUMMARY,
        debug_log=[{"msg": "x"}],
        total_tokens=1234,
        llm_call_count=56,
        registry=SimpleNamespace(sources={"a1b2c3d4e5f6": object()}),
        specialist_analyses={"geo": []},
    )

    class FakeOrchestrator:
        async def run(self, question, emit, **kwargs):
            return ctx

    async def fake_corpus(ctx_, request_id, artifact):
        calls["corpus"].append((request_id, artifact))

    monkeypatch.setattr(tw, "get_session", lambda: session)
    monkeypatch.setattr(tw, "get_redis_client", lambda: None)
    monkeypatch.setattr(tw, "_plan_balance_snapshot", lambda: None)
    monkeypatch.setattr(tw, "_record_plan_cost", lambda request_id, start: None)
    monkeypatch.setattr(tw, "_deduct_credits", lambda request_id: calls["credits"].append(request_id))
    monkeypatch.setattr(tw, "_persist_training_corpus", fake_corpus)
    monkeypatch.setattr(tw, "_live_events", {})
    monkeypatch.setattr("pipeline.lyra.convergence_orchestrator.ConvergenceOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        "pipeline.lyra.research_graph.mark_node_explored", lambda request_id: calls["explored"].append(request_id)
    )
    monkeypatch.setattr(
        "pipeline.lyra.thinking_log.log_thinking",
        lambda kind, summary, details=None: calls["thinking"].append((kind, summary, details)),
    )
    monkeypatch.setattr(
        "api.services.notify.send_discord_webhook", lambda payload: calls["webhook"].append(payload) or False
    )
    return calls


async def test_success_ends_researched_with_the_dossier_and_no_publish(monkeypatch):
    session = RecordingSession({"SET status = 'running'": [object()], "SET status = 'researched'": [object()]})
    calls = _run(monkeypatch, session)

    await tw._process_request(REQ, "Who cut the Baalbek monoliths?", None, is_batch=True)

    update = session.statement_with("SET status = 'researched'")
    params = next(p for sql, p in session.log if sql == update)
    assert json.loads(params["result"]) == {"dossier": SUMMARY, "title": None}
    assert "status = 'running'" in update
    assert not [sql for sql in session.statements() if "is_public = TRUE" in sql]
    assert calls["credits"] == [REQ]
    assert calls["corpus"] == [(REQ, None)]
    assert calls["explored"] == [REQ]
    kind, _summary, details = calls["thinking"][0]
    assert kind == "run_event"
    assert details["event"] == "dossier_ready"
    assert len(calls["webhook"]) == 1
    assert tw._live_events[REQ][-1] == {"type": "done", "status": "researched"}


async def test_a_ui_run_is_researched_too_but_touches_no_graph_node(monkeypatch):
    session = RecordingSession({"SET status = 'running'": [object()], "SET status = 'researched'": [object()]})
    calls = _run(monkeypatch, session)

    await tw._process_request(REQ, "A website question", None, is_batch=False)

    assert session.statement_with("SET status = 'researched'")
    assert calls["explored"] == []
    assert calls["thinking"] == []
    assert len(calls["webhook"]) == 1


async def test_a_run_cancelled_mid_flight_is_not_announced(monkeypatch):
    # The researched UPDATE is guarded on status='running'; a DELETE flipped the row.
    session = RecordingSession({"SET status = 'running'": [object()]})
    calls = _run(monkeypatch, session)

    await tw._process_request(REQ, "q", None, is_batch=True)

    assert calls["explored"] == []
    assert calls["webhook"] == []


def test_the_auto_publish_path_is_gone():
    assert not hasattr(tw, "_auto_publish")
    assert not hasattr(tw, "_paper_artifact")
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_theo_worker_researched.py -m "not integration and not live_llm" -q`
Expected: `4 failed` (the success branch writes `completed`, `_auto_publish` exists).

- [ ] **Step 3: Rewrite the success branch**

In `api/services/theo_worker.py`:

(a) First docstring line block becomes:

```python
"""
Background worker for Theodore Furcade — processes research requests asynchronously.

Polls the research_requests table for queued requests (FIFO), runs the
research-only convergence pipeline and marks a finished run 'researched': its
dossier waits in research_artifacts for the Claude write (spec 2.4).
"""
```

(b) Delete the two imports `from pipeline.indexnow import page_url as indexnow_url` and `from pipeline.indexnow import submit as indexnow_submit` (only `_auto_publish` used them).

(c) Delete the function `_paper_artifact` entirely.

(d) Replace `_persist_training_corpus` with:

```python
async def _persist_training_corpus(ctx, request_id: str, artifact: tuple[str, dict] | None) -> None:
    """Close out the run's training-corpus record: snippet documents and run links.

    Called only after the result (or failure) row is committed. `artifact` is
    the failure snapshot on the error paths and None on success: the dossier
    (registry, image pool, manifest) was written, loudly, by the DossierHandler
    before the run returned. This close-out is a passenger: a write failure
    here is logged loudly and dropped rather than raised.
    """
    try:
        from pipeline.lyra.training_corpus import persist_run_corpus, save_artifact

        if artifact is not None:
            kind, payload = artifact
            await asyncio.to_thread(save_artifact, request_id, kind, payload, "")
        stats = await asyncio.to_thread(persist_run_corpus, ctx, request_id)
        logger.info(
            "[THEO] %s corpus: %d documents, %d source links",
            request_id,
            stats["documents"],
            stats["links"],
        )
    except Exception as exc:
        logger.error("[THEO] %s training-corpus write failed: %s", request_id, exc)
```

(e) Add after `_persist_training_corpus`:

```python
def _notify_dossier_ready(request_id: str, question: str, summary: dict) -> None:
    """Tell the owner a dossier waits for the Claude write.

    The Discord embed goes out only when DISCORD_WEBHOOK_URL is set
    (send_discord_webhook returns False otherwise); the thinking_log event the
    caller writes for batch runs is the record that always exists.
    """
    from api.services.notify import send_discord_webhook

    counts = summary["counts"]
    archive = summary["archive"]
    send_discord_webhook(
        {
            "embeds": [
                {
                    "title": "Theo dossier ready — awaiting the Claude write",
                    "description": (
                        f"`{request_id}`\n**{question[:200]}**\n"
                        f"{counts['final_claims']} final claims · {counts['sources']} sources · "
                        f"{archive['full_text']}/{archive['cited_sources']} cited sources with full text"
                    ),
                    "color": 0x2ECC71,
                }
            ]
        }
    )
```

(f) Replace the whole `else:` success branch of `_process_request` (from `        else:` / `            # Deduct credits and release reservation on success` down to and including `                await asyncio.to_thread(_auto_publish, request_id)`) with:

```python
        else:
            # Research-only (spec 2.4): the run ends with a dossier, not a paper.
            # Credits are still deducted at research end.
            _deduct_credits(request_id)
            summary = ctx.dossier_summary
            emit({"type": "done", "status": "researched"})
            with get_session() as session:
                # Guarded on status='running': a DELETE that cancelled the row
                # mid-run must not be overwritten back to a live status.
                written = session.execute(
                    text("""
                        UPDATE research_requests
                        SET status = 'researched',
                            result_json = :result,
                            pipeline_trace = :trace,
                            debug_log = :debug_log,
                            total_tokens = :tokens,
                            llm_calls = :llm_calls,
                            duration_ms = :duration,
                            sites_found = :sites,
                            tools_used = :tools,
                            completed_at = NOW()
                        WHERE id = :id AND status = 'running'
                    """),
                    {
                        "id": request_id,
                        "result": json.dumps({"dossier": summary, "title": None}),
                        "trace": json.dumps(pipeline_trace),
                        "debug_log": json.dumps(ctx.debug_log),
                        "tokens": ctx.total_tokens,
                        "llm_calls": ctx.llm_call_count,
                        "duration": duration_ms,
                        "sites": len(ctx.registry.sources),
                        "tools": len(ctx.specialist_analyses),
                    },
                )
                session.commit()
            # Snippet documents + run links (the dossier itself is already written).
            await _persist_training_corpus(ctx, request_id, None)
            if written.rowcount == 0:
                logger.warning(
                    "[THEO] Request %s was no longer 'running' at research end (cancelled "
                    "mid-run?): the dossier stays in research_artifacts, the status was not written.",
                    request_id,
                )
            else:
                logger.info(
                    "[THEO] Request %s researched in %dms (%d tokens), dossier artifact %s",
                    request_id,
                    duration_ms,
                    ctx.total_tokens,
                    summary["artifact_id"],
                )
                if is_batch:
                    # The frontier topic is researched; its paper follows in a
                    # Claude session.
                    from pipeline.lyra.research_graph import mark_node_explored

                    mark_node_explored(request_id)

                    from pipeline.lyra.thinking_log import log_thinking

                    log_thinking(
                        "run_event",
                        f"Dossier ready: {question[:200]}",
                        {
                            "request_id": request_id,
                            "event": "dossier_ready",
                            "final_claims": summary["counts"]["final_claims"],
                        },
                    )
                _notify_dossier_ready(request_id, question, summary)
```

(g) Delete the function `_auto_publish` entirely (from `def _auto_publish(request_id: str) -> None:` to the line before `async def _run_with_stall_guard(`).

- [ ] **Step 4: Drop the auto-publish author constant**

In `api/services/theo_config.py` replace

```python
# The permanent researcher (feeder) enqueues frontier topics under this
# account. The row owner stays the operator so owner-gated endpoints keep
# working; auto-published papers carry published_by='Theo' for attribution.
THEO_FEEDER_USER_ID = os.getenv("THEO_FEEDER_USER_ID", "442000112756064260")
THEO_AUTO_PUBLISH_AUTHOR = "Theo"
```

with

```python
# The permanent researcher (feeder) enqueues frontier topics under this
# account. The row owner stays the operator so owner-gated endpoints keep
# working; papers published by the Claude write carry published_by='Theo'
# (pipeline/lyra/theo_publishing.py PUBLISH_AUTHOR).
THEO_FEEDER_USER_ID = os.getenv("THEO_FEEDER_USER_ID", "442000112756064260")
```

- [ ] **Step 5: Run the worker tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_theo_worker_researched.py tests/api/test_theo_worker_quota.py tests/api/test_theo_worker_stall_guard.py tests/api/test_theo_worker_pacing.py tests/api/test_theo_live_event_bridge.py tests/api/test_worker_container_split.py -m "not integration and not live_llm" -q`
Expected: all pass.

- [ ] **Step 6: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format api/services/theo_worker.py api/services/theo_config.py tests/api/test_theo_worker_researched.py
./.venv/Scripts/python.exe -m ruff check --fix api/services/theo_worker.py api/services/theo_config.py tests/api/test_theo_worker_researched.py
./.venv/Scripts/python.exe -m vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80
git add api/services/theo_worker.py api/services/theo_config.py tests/api/test_theo_worker_researched.py
git commit -m "End a successful Theo run as researched with its dossier summary and drop the M3 auto-publish" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 14: Pace batch runs on research-only runs and cap unwritten dossiers

**Files:**
- Modify: `api/services/theo_config.py` (lines 64-100)
- Modify: `api/services/theo_worker.py` (imports, `_avg_batch_run_hours`, `_batch_claim_allowed`, `_feeder_loop`)
- Modify: `tests/api/test_theo_worker_quota.py` (section 3 and 4)
- Test: `tests/api/test_theo_worker_researched.py` (append)

- [ ] **Step 1: Append the failing tests**

Append to `tests/api/test_theo_worker_researched.py`:

```python
# --- pacing and feeder (spec 2.4) ---------------------------------------------


def test_run_pacing_constants():
    from api.services import theo_config

    assert theo_config.THEO_RUN_COST_PCT == 9.0
    assert theo_config.THEO_RUN_EST_HOURS == 11.0
    assert theo_config.THEO_MAX_UNWRITTEN_DOSSIERS == 6
    assert not hasattr(theo_config, "THEO_PAPER_COST_PCT")
    assert not hasattr(theo_config, "THEO_PAPER_EST_HOURS")


def test_average_run_hours_come_from_research_only_rows(monkeypatch):
    session = RecordingSession({"AVG(duration_ms)": [(36_000_000,)]})
    monkeypatch.setattr(tw, "get_session", lambda: session)
    monkeypatch.setattr(tw, "_avg_run_cache", None)
    assert tw._avg_batch_run_hours() == 10.0
    sql = session.statements()[0]
    assert "status IN ('completed', 'researched')" in sql
    assert "result_json::jsonb -> 'dossier' IS NOT NULL" in sql


def test_average_run_hours_fall_back_to_the_estimate_without_history(monkeypatch):
    monkeypatch.setattr(tw, "get_session", lambda: RecordingSession({}))
    monkeypatch.setattr(tw, "_avg_run_cache", None)
    assert tw._avg_batch_run_hours() == 11.0


def test_feeder_backlog_counts_pending_batch_rows_and_unwritten_dossiers(monkeypatch):
    session = RecordingSession({"FROM research_requests": [SimpleNamespace(pending=0, unwritten=6)]})
    monkeypatch.setattr(tw, "get_session", lambda: session)
    assert tw._read_feeder_backlog() == (0, 6)
    sql = session.statements()[0]
    assert "status = 'researched'" in sql
    assert "status IN ('queued', 'running', 'deferred')" in sql


@pytest.mark.parametrize(
    ("pending", "unwritten", "expected"),
    [(0, 0, True), (0, 5, True), (0, 6, False), (1, 0, False)],
)
def test_the_feeder_enqueues_only_into_an_empty_queue_below_the_cap(pending, unwritten, expected):
    assert tw._feeder_may_enqueue(pending, unwritten, 6) is expected
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_theo_worker_researched.py -m "not integration and not live_llm" -q`
Expected: the 8 new tests fail (`THEO_RUN_COST_PCT` missing, `_read_feeder_backlog` missing, SQL mismatch).

- [ ] **Step 3: Rename and re-measure the pacing constants**

In `api/services/theo_config.py`, in the end-of-week comment replace "paper (at the measured pace of the last 5 completed batch papers, fallback THEO_PAPER_EST_HOURS)" with "run (at the measured pace of the last 5 research-only batch runs, fallback THEO_RUN_EST_HOURS)", then replace the `THEO_PAPER_COST_PCT` block (comment + assignment) and the `THEO_PAPER_EST_HOURS` block with:

```python
# Weekly-budget share of one research-only batch run (spec 2.4, 2026-09-26).
# The last full-pipeline measurement (2026-08-08, migration 0013) put a whole
# paper at 9.1% of the weekly budget over 15.2h. The M3 writing chain was about
# 4h of a 14h run (production run 23336ade), so research alone costs less;
# 9 keeps headroom on top of that share. Re-measure with
# scripts/theo_plan_cost.py once research-only runs exist.
THEO_RUN_COST_PCT = float(os.getenv("THEO_RUN_COST_PCT", "9"))

# Weekly-% reserved PER REMAINING DAY for Lyra's hourly cycles and
# interactive research. The dynamic claim requirement is
# run cost + days-to-reset * this — Friday needs more headroom than a
# Saturday-night start.
THEO_LYRA_DAILY_RESERVE_PCT = float(os.getenv("THEO_LYRA_DAILY_RESERVE_PCT", "5"))

# Wall-clock fallback for one research-only batch run while no research-only
# history exists (the full runs took 14h13m, of which about 4h10m was M3
# writing). The live gate prefers the average of the last 5 research-only
# batch runs (duration_ms), which includes crawl-lane pacing and quota sleeps.
THEO_RUN_EST_HOURS = float(os.getenv("THEO_RUN_EST_HOURS", "11"))

# The feeder stops enqueueing frontier topics while this many dossiers wait for
# the Claude write (status 'researched'), so research cannot outrun writing.
THEO_MAX_UNWRITTEN_DOSSIERS = int(os.getenv("THEO_MAX_UNWRITTEN_DOSSIERS", "6"))
```

(the existing `THEO_LYRA_DAILY_RESERVE_PCT` block between the two is replaced by the copy above, whose comment says "run cost" instead of "paper cost").

- [ ] **Step 4: Use them in the worker**

In `api/services/theo_worker.py`:

(a) The config import becomes

```python
from api.services.theo_config import (
    THEO_MAX_UNWRITTEN_DOSSIERS,
    THEO_MIN_TASK_INTERVAL_S,
    THEO_PARALLEL_SLOTS,
    THEO_RESEARCH_COST,
)
```

(b) Replace `_avg_batch_run_hours` with:

```python
def _avg_batch_run_hours() -> float:
    """Measured wall-clock hours of one research-only batch run: the average of
    the last 5 batch rows that ended with a dossier (status 'researched', or
    'completed' after the Claude publish, which keeps result_json['dossier']).
    duration_ms includes crawl-lane pacing and quota sleeps. Full-pipeline runs
    (no 'dossier' key) are excluded: their 4h of M3 writing no longer happens.
    Falls back to THEO_RUN_EST_HOURS without history."""
    global _avg_run_cache
    from api.services.theo_config import THEO_RUN_EST_HOURS

    now = time.monotonic()
    if _avg_run_cache and now - _avg_run_cache[1] < 600:
        return _avg_run_cache[0]
    hours = THEO_RUN_EST_HOURS
    try:
        with get_session() as session:
            avg_ms = session.execute(
                text("""
                    SELECT AVG(duration_ms) FROM (
                        SELECT duration_ms FROM research_requests
                        WHERE is_batch = TRUE AND status IN ('completed', 'researched')
                          AND duration_ms IS NOT NULL
                          AND result_json::jsonb -> 'dossier' IS NOT NULL
                        ORDER BY completed_at DESC LIMIT 5
                    ) recent
                """)
            ).scalar()
        if avg_ms:
            hours = float(avg_ms) / 3_600_000
    except Exception as exc:
        logger.warning("[THEO] batch run duration read failed: %s", exc)
    _avg_run_cache = (hours, now)
    return hours
```

(c) In `_batch_claim_allowed` replace `THEO_PAPER_COST_PCT` by `THEO_RUN_COST_PCT` in the import and in `required = pre_reset_share * THEO_RUN_COST_PCT + days_left * THEO_LYRA_DAILY_RESERVE_PCT`; in its docstring replace "the share of one paper" by "the share of one research run" and "recent batch papers" by "recent research-only batch runs".

(d) Add before `async def _feeder_loop()`:

```python
_FEEDER_BACKLOG_SQL = text("""
    SELECT
        COUNT(*) FILTER (WHERE is_batch = TRUE
                           AND status IN ('queued', 'running', 'deferred')) AS pending,
        COUNT(*) FILTER (WHERE status = 'researched') AS unwritten
    FROM research_requests
""")


def _read_feeder_backlog() -> tuple[int, int]:
    """(batch rows queued/running/deferred, dossiers awaiting the Claude write)."""
    with get_session() as session:
        row = session.execute(_FEEDER_BACKLOG_SQL).fetchone()
    return int(row.pending), int(row.unwritten)


def _feeder_may_enqueue(pending: int, unwritten: int, cap: int) -> bool:
    """The feeder adds a frontier topic only to an empty batch queue, and only while
    fewer than `cap` researched dossiers wait for a write (spec 2.4)."""
    return pending == 0 and unwritten < cap
```

(e) In `_feeder_loop`, replace

```python
            with get_session() as session:
                pending = session.execute(
                    text("""
                        SELECT COUNT(*) FROM research_requests
                        WHERE is_batch = TRUE
                          AND status IN ('queued', 'running', 'deferred')
                    """)
                ).scalar()

            if not pending:
```

with

```python
            pending, unwritten = _read_feeder_backlog()
            if unwritten >= THEO_MAX_UNWRITTEN_DOSSIERS:
                logger.info(
                    "[THEO] Feeder paused: %d dossiers await the Claude write (cap %d)",
                    unwritten,
                    THEO_MAX_UNWRITTEN_DOSSIERS,
                )
            if _feeder_may_enqueue(pending, unwritten, THEO_MAX_UNWRITTEN_DOSSIERS):
```

and in the `_feeder_loop` docstring replace "Every 10 min: when no batch row is queued/running/deferred and the batch gate inputs allow a start" with "Every 10 min: when no batch row is queued/running/deferred, fewer than THEO_MAX_UNWRITTEN_DOSSIERS dossiers wait for the Claude write, and the batch gate inputs allow a start".

- [ ] **Step 5: Re-compute the batch-gate tests for 9 % and 11 h runs**

In `tests/api/test_theo_worker_quota.py` replace everything from the line `# --- 3. Batch claims require HEALTHY watchdog + weekly headroom --------------` up to (not including) `def test_hours_until_weekly_reset():` with:

```python
# --- 3. Batch claims require HEALTHY watchdog + weekly headroom --------------
# 2026-07-19: tier alone is not enough — a run must fit the remaining weekly
# budget or it parks in the weekly wall mid-run. None = probe carried no
# weekly value: batch runs never start blind.


# A Friday noon — 60h before the Monday 00:00 UTC reset, comfortably inside
# the default end-of-week window, so these cases test the gate/tier logic in
# isolation. avg_run_hours is injected so no DB read happens in tests. 11h is
# THEO_RUN_EST_HOURS, the research-only run (spec 2.4, 2026-09-26).
_FRIDAY = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
_RUN_H = 11.0


@pytest.mark.parametrize(
    "gate_open,tier,weekly,expected",
    [
        (True, "HEALTHY", 100, True),
        (True, "HEALTHY", 0, False),  # the 07-08..07-12 wall
        (True, "HEALTHY", None, False),  # probe blind: never start blind
        (True, "DEGRADED", 100, False),
        (True, "EXHAUSTED", 100, False),
        (True, "UNKNOWN", 100, False),
        (False, "HEALTHY", 100, False),
    ],
)
def test_batch_claim_allowed(gate_open, tier, weekly, expected):
    assert (
        tw._batch_claim_allowed(gate_open, tier, weekly, now_utc=_FRIDAY, avg_run_hours=_RUN_H)
        is expected
    )


# --- 4. End-of-week batch window: day x budget x measured speed --------------
# 2026-08-04: the weekly budget resets Monday 00:00 UTC. Batch starts are gated
# on two adaptive conditions: <=3 days to the reset, and the weekly budget
# covers the PRE-RESET SHARE of one research run (THEO_RUN_COST_PCT = 9 at the
# measured run pace, 2026-09-26) plus 5%/remaining-day Lyra reserve. The last
# run of the weekend may cross the reset onto Monday's fresh budget — the
# weekly must just never hit 0% mid-run (that aborts runs).


def _claim(now, weekly=100, run_h=_RUN_H):
    return tw._batch_claim_allowed(True, "HEALTHY", weekly, now_utc=now, avg_run_hours=run_h)


def test_window_closed_early_week():
    # Monday through Thursday: >3 days to the reset — the fresh budget
    # belongs to Lyra and interactive research, regardless of how full it is.
    assert _claim(datetime(2026, 8, 3, 0, 1, tzinfo=UTC)) is False  # Mon
    assert _claim(datetime(2026, 8, 4, 12, 0, tzinfo=UTC)) is False  # Tue
    assert _claim(datetime(2026, 8, 6, 23, 59, tzinfo=UTC)) is False  # Thu 23:59


def test_window_opens_friday():
    # Fri 00:00 = exactly 3.0 days to reset. An 11h run burns entirely
    # before the reset -> required = 9 (run) + 3.0 * 5 (Lyra) = 24.
    fri = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
    assert _claim(fri, weekly=100) is True
    assert _claim(fri, weekly=25) is True
    assert _claim(fri, weekly=23) is False  # surplus too small for Friday


def test_required_budget_shrinks_toward_reset():
    # The SAME 20% weekly is not enough on Friday (needs 24) but fine on
    # Saturday noon (36h left -> 9 + 1.5*5 = 16.5): closer to the reset,
    # less of the budget must stay reserved.
    fri = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)
    sat_noon = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    assert _claim(fri, weekly=20) is False
    assert _claim(sat_noon, weekly=20) is True


def test_last_run_may_cross_the_reset():
    # Sunday 20:00 = 4h left. An 11h run burns only 4/11 of its cost
    # before the reset -> required = 9*0.364 + 0.167*5 ~= 4.1. Even a
    # nearly-drained week can still launch the weekend's last run — it
    # finishes on Monday's fresh budget, and Monday itself allows no NEW
    # starts (window closed).
    sun_evening = datetime(2026, 8, 9, 20, 0, tzinfo=UTC)
    assert _claim(sun_evening, weekly=10) is True
    assert _claim(sun_evening, weekly=3) is False  # pre-reset share won't fit


def test_measured_pace_scales_pre_reset_share():
    # Sat 22:00 = 26h left. An 11h run fits entirely before the reset
    # (required 9 + 1.083*5 ~= 14.4); a slow 30h run defers 4/30 of its
    # burn past the reset (required 9*0.867 + 5.4 ~= 13.2). weekly=13.8
    # sits exactly between the two.
    sat_night = datetime(2026, 8, 8, 22, 0, tzinfo=UTC)
    assert _claim(sat_night, weekly=13.8, run_h=11.0) is False
    assert _claim(sat_night, weekly=13.8, run_h=30.0) is True


def test_never_starts_into_empty_weekly():
    # Sun 23:00 = 1h left: even the tiniest pre-reset share (1/11 of a
    # run ~= 0.8% + reserve ~= 1.0) must fit — the weekly hitting 0% mid-run
    # aborts the run and freezes the shared plan.
    sun_late = datetime(2026, 8, 9, 23, 0, tzinfo=UTC)
    assert _claim(sun_late, weekly=2) is True
    assert _claim(sun_late, weekly=0.5) is False


def test_window_env_override(monkeypatch):
    """MAX_DAYS_TO_RESET=7 restores always-on starts (budget still applies)."""
    monkeypatch.setattr("api.services.theo_config.THEO_BATCH_MAX_DAYS_TO_RESET", 7.0)
    monday = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    # 6.5 days to reset -> required 9 + 6.5*5 = 41.5
    assert _claim(monday, weekly=100) is True
    assert _claim(monday, weekly=40) is False


```

- [ ] **Step 6: Run the worker tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_theo_worker_researched.py tests/api/test_theo_worker_quota.py tests/api/test_theo_worker_pacing.py -m "not integration and not live_llm" -q`
Expected: all pass (`12` in the researched file).

Check nothing still uses the old names: `grep -rn "THEO_PAPER_COST_PCT\|THEO_PAPER_EST_HOURS\|THEO_AUTO_PUBLISH_AUTHOR" api pipeline tests`
Expected: no output.

- [ ] **Step 7: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format api/services/theo_worker.py api/services/theo_config.py tests/api/test_theo_worker_researched.py tests/api/test_theo_worker_quota.py
./.venv/Scripts/python.exe -m ruff check --fix api/services/theo_worker.py api/services/theo_config.py tests/api/test_theo_worker_researched.py tests/api/test_theo_worker_quota.py
git add api/services/theo_worker.py api/services/theo_config.py tests/api/test_theo_worker_researched.py tests/api/test_theo_worker_quota.py
git commit -m "Pace Theo's batch runs on research-only durations and stop the feeder while six dossiers wait for a write" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 15: Slug rule and publish gates (`theo_publishing.py`, part 2)

**Files:**
- Modify: `pipeline/lyra/theo_publishing.py`
- Test: `tests/pipeline/test_theo_publishing_gates.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_theo_publishing_gates.py`:

```python
"""Publish gates: slug, shape, snapshot, artifact, quality, evidence, images, status."""

from __future__ import annotations

import copy

import pytest

from pipeline.lyra import theo_publishing as tp
from pipeline.lyra.theo_citations import validate_paper_artifact
from tests.fake_sql import RecordingSession
from tests.pipeline.theo_publish_fixtures import (
    EVIDENCE,
    IMG,
    IMG_NAME,
    OTHER_REQ,
    QUALITY,
    REPORT,
    REQ,
    SOURCE_A,
    WRITER,
    make_result,
)

# --- slug -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("The Baalbek Trilithon", "the-baalbek-trilithon"),
        ("  Göbekli Tepe: Pillars & Pits  ", "gbekli-tepe-pillars-pits"),
        ("Sumer -- the -- Anunnaki", "sumer-the-anunnaki"),
    ],
)
def test_make_slug_keeps_the_route_rule(title, slug):
    assert tp.make_slug(title) == slug


def test_pick_slug_appends_the_id_on_collision():
    free = RecordingSession({})
    assert tp.pick_slug(free, "The Baalbek Trilithon", REQ) == "the-baalbek-trilithon"
    sql, params = free.log[0]
    assert "slug = :slug AND id != :id" in sql
    assert params == {"slug": "the-baalbek-trilithon", "id": REQ}
    taken = RecordingSession({"SELECT 1 FROM research_requests WHERE slug": [object()]})
    assert tp.pick_slug(taken, "The Baalbek Trilithon", REQ) == "the-baalbek-trilithon-11111111"


# --- shape and snapshot -------------------------------------------------------


def test_a_complete_bundle_passes_shape_and_snapshot():
    result = make_result()
    assert tp.check_publish_shape(result, WRITER) == {"passed": True, "issues": []}
    assert tp.check_snapshot(result) == {"passed": True, "issues": []}


def test_shape_names_every_problem():
    result = make_result(corrections=[{"date": "2026-10-01", "text": "x"}], extra="nope")
    del result["card_description"]
    gate = tp.check_publish_shape(result, {**WRITER, "human_review": "no"})
    assert gate["passed"] is False
    assert "writer.human_review must be true or false" in gate["issues"]
    assert "result.card_description must be a str" in gate["issues"]
    assert "result has unknown keys: ['extra']" in gate["issues"]


def test_shape_rejects_first_publish_corrections_and_a_foreign_writer():
    gate = tp.check_publish_shape(
        make_result(corrections=[{"date": "2026-10-01", "text": "x"}], writer={**WRITER, "model": "x"}),
        WRITER,
    )
    assert "result.corrections must be [] at first publish (use --correct afterwards)" in gate["issues"]
    assert "result.writer differs from the bundle's writer" in gate["issues"]


def test_shape_needs_evidence_and_the_audit_gate_summary():
    quality = copy.deepcopy(QUALITY)
    del quality["audit_gate_failures"]
    gate = tp.check_publish_shape(make_result(evidence=[], quality_score=quality), WRITER)
    assert "result.evidence is empty: every paper carries evidence entries" in gate["issues"]
    assert "result.quality_score.audit_gate_failures missing" in gate["issues"]


def test_snapshot_requires_one_text_and_one_hero():
    result = make_result(published_report=REPORT + "\nextra", published_hero_image=None)
    gate = tp.check_snapshot(result)
    assert gate["passed"] is False
    assert len(gate["issues"]) == 2


# --- artifact and quality ---------------------------------------------------------


def test_artifact_gate_returns_the_audit():
    gate, audit = tp.check_artifact(REPORT)
    assert gate == {"passed": True, "issues": []}
    assert audit["passed"] is True
    broken_gate, _ = tp.check_artifact(REPORT.replace("podium [2].", "podium [7]."))
    assert broken_gate["passed"] is False


def test_quality_needs_the_stored_verdict_and_the_recomputation():
    audit = validate_paper_artifact(REPORT)
    assert tp.check_quality(QUALITY, audit, require_stored_passed=True)["passed"] is True
    held = tp.check_quality({**QUALITY, "passed": False}, audit, require_stored_passed=True)
    assert held["passed"] is False
    assert held["issues"] == ["quality_score.passed is not true"]
    # Corrections recompute only: the stored flag predates the corrected text.
    assert tp.check_quality({**QUALITY, "passed": False}, audit, require_stored_passed=False)["passed"] is True
    no_summary = {k: v for k, v in QUALITY.items() if k != "audit_gate_failures"}
    assert tp.check_quality(no_summary, audit, require_stored_passed=False)["recomputed_passed"] is False


# --- evidence -----------------------------------------------------------------------


def test_published_evidence_resolves():
    gate = tp.check_evidence(REPORT, copy.deepcopy(EVIDENCE))
    assert gate == {"passed": True, "issues": [], "resolved": {"ev-01": 1, "ev-02": 4}}


def test_only_supported_well_formed_evidence_is_published():
    bad = copy.deepcopy(EVIDENCE)
    bad[0]["verdict"] = "partly"
    bad[1]["quote_source_id"] = SOURCE_A
    bad.append({**EVIDENCE[0], "id": "ev-1"})
    bad.append({**EVIDENCE[1]})
    gate = tp.check_evidence(REPORT, bad)
    assert gate["passed"] is False
    assert gate["resolved"] == {}
    assert "ev-01: verdict is 'partly'; only 'supported' may be published" in gate["issues"]
    assert "ev-02: quote_source_id is not one of source_ids" in gate["issues"]
    assert "ev-1: id must look like ev-NN" in gate["issues"]
    assert "ev-02: duplicate id" in gate["issues"]


def test_evidence_with_missing_keys_is_reported_not_crashed():
    gate = tp.check_evidence(REPORT, [{"id": "ev-01"}, "not an object"])
    assert gate["passed"] is False
    assert gate["issues"][0].startswith("ev-01: missing [")
    assert gate["issues"][1] == "evidence[1]: must be an object"


# --- images -------------------------------------------------------------------------


def test_images_must_exist_in_this_papers_folder(tmp_path):
    folder = tmp_path / REQ
    folder.mkdir()
    (folder / IMG_NAME).write_bytes(b"jpeg")
    result = make_result()
    gate = tp.check_images(REQ, REPORT, result["probative_images"], result["hero_image"], images_root=tmp_path)
    assert gate == {"passed": True, "issues": [], "checked": 1, "missing": [], "foreign": []}


def test_missing_foreign_and_unsafe_images_fail(tmp_path):
    foreign = f"/data/research-images/{OTHER_REQ}/p2.jpg"
    hero = {"src": f"/data/research-images/{REQ}/../etc.jpg"}
    gate = tp.check_images(REQ, REPORT, [{"web_path": foreign}, {"title": "no path"}], hero, images_root=tmp_path)
    assert gate["passed"] is False
    assert gate["missing"] == [IMG]
    assert gate["foreign"] == [foreign]
    assert "probative_images[1] has no web_path" in gate["issues"]
    assert f"not a research-images path: /data/research-images/{REQ}/../etc.jpg" in gate["issues"]


# --- status -------------------------------------------------------------------------


def test_status_gate_for_publish():
    assert tp.check_publish_status("researched", False, dry_run=False)["passed"] is True
    assert tp.check_publish_status("completed", False, dry_run=False)["passed"] is True
    assert tp.check_publish_status("running", False, dry_run=True)["passed"] is False
    public_dry = tp.check_publish_status("completed", True, dry_run=True)
    assert public_dry["passed"] is True
    assert public_dry["apply_allowed"] is False
    assert tp.check_publish_status("completed", True, dry_run=False)["passed"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publishing_gates.py -m "not integration and not live_llm" -q`
Expected: failures (`AttributeError: module 'pipeline.lyra.theo_publishing' has no attribute 'make_slug'`).

- [ ] **Step 3: Implement**

In `pipeline/lyra/theo_publishing.py` replace the import block with:

```python
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from sqlalchemy import text

from pipeline.lyra.quality_gate import recompute_quality_passed
from pipeline.lyra.theo_citations import (
    _is_non_prose_block,
    _split_prose_into_paragraphs,
    split_artifact,
    validate_paper_artifact,
)
```

and append at the end of the module:

```python
# ---------------------------------------------------------------------------
# Slug
# ---------------------------------------------------------------------------

#: published_by of every Theo paper. 'Theo' keeps the Organization author in the
#: page's JSON-LD and the "AI research agent" label (spec 3.7).
PUBLISH_AUTHOR = "Theo"


def make_slug(title: str) -> str:
    """URL slug of a paper title (moved unchanged from api/routes/theo.py::_make_slug)."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:250]


_SLUG_TAKEN_SQL = text("SELECT 1 FROM research_requests WHERE slug = :slug AND id != :id")


def pick_slug(session: Any, title: str, request_id: str) -> str:
    """make_slug(title), suffixed with -<id[:8]> when another paper already holds it."""
    slug = make_slug(title)
    taken = session.execute(_SLUG_TAKEN_SQL, {"slug": slug, "id": request_id}).fetchone()
    return f"{slug}-{request_id[:8]}" if taken else slug


# ---------------------------------------------------------------------------
# Gates. Each returns {"passed": bool, "issues": [str], ...}.
# ---------------------------------------------------------------------------

#: /app/public/data/research-images in the API container (bind mount of the VPS's
#: /var/www/ancientnerds/public/data); the repo root's public/data elsewhere.
RESEARCH_IMAGES_DIR = Path(__file__).resolve().parents[2] / "public" / "data" / "research-images"

SOURCE_ID_RE = re.compile(r"^[0-9a-f]{12}$")
WRITER_KEYS = ("model", "tool", "research_model", "published", "human_review")
MAX_TITLE_CHARS = 200
MAX_CARD_CHARS = 600

_IMAGE_REF_RE = re.compile(r"/data/research-images/[^\s)\"'<>]+")
_IMAGE_PATH_RE = re.compile(
    r"^/data/research-images/(?P<rid>[^/]+)/(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)$"
)
_EVIDENCE_KEYS = frozenset(
    {"id", "anchor_text", "claim", "source_ids", "quote", "quote_source_id", "verdict"}
)
_RESULT_REQUIRED: dict[str, type] = {
    "title": str,
    "card_description": str,
    "report": str,
    "published_report": str,
    "probative_images": list,
    "published_block_ids": list,
    "quality_score": dict,
    "evidence": list,
    "corrections": list,
}
_RESULT_NULLABLE_DICTS = ("hero_image", "published_hero_image")
_RESULT_OPTIONAL = frozenset({"audit", "writer"})


def _gate(issues: list[str], **extra: Any) -> dict:
    return {"passed": not issues, "issues": issues, **extra}


def check_writer(writer: Any) -> list[str]:
    """Issues with a writer object (contract C4 `writer`)."""
    if not isinstance(writer, dict):
        return ["writer must be an object"]
    issues = [f"writer.{key} missing" for key in WRITER_KEYS if key not in writer]
    for key in ("model", "tool", "research_model", "published"):
        if key in writer and not (isinstance(writer[key], str) and writer[key].strip()):
            issues.append(f"writer.{key} must be a non-empty string")
    if "human_review" in writer and not isinstance(writer["human_review"], bool):
        issues.append("writer.human_review must be true or false")
    unknown = sorted(set(writer) - set(WRITER_KEYS))
    if unknown:
        issues.append(f"writer has unknown keys: {unknown}")
    return issues


def check_publish_shape(result: dict, writer: Any) -> dict:
    """Every key the published paper needs, with the right type, and nothing else."""
    issues = check_writer(writer)
    for key, kind in _RESULT_REQUIRED.items():
        if not isinstance(result.get(key), kind):
            issues.append(f"result.{key} must be a {kind.__name__}")
    for key in _RESULT_NULLABLE_DICTS:
        if key not in result:
            issues.append(f"result.{key} missing (null when the paper has no hero image)")
        elif result[key] is not None and not isinstance(result[key], dict):
            issues.append(f"result.{key} must be an object or null")
    unknown = sorted(set(result) - set(_RESULT_REQUIRED) - set(_RESULT_NULLABLE_DICTS) - _RESULT_OPTIONAL)
    if unknown:
        issues.append(f"result has unknown keys: {unknown}")
    if issues:
        return _gate(issues)
    title = result["title"].strip()
    if not title or "\n" in title or len(title) > MAX_TITLE_CHARS:
        issues.append(f"result.title must be one line of 1-{MAX_TITLE_CHARS} characters")
    elif not make_slug(title):
        issues.append("result.title yields an empty slug")
    card = result["card_description"].strip()
    if not card or len(card) > MAX_CARD_CHARS:
        issues.append(f"result.card_description must be 1-{MAX_CARD_CHARS} characters")
    if result["published_block_ids"]:
        issues.append("result.published_block_ids must be [] (no block review on this path)")
    if result["corrections"]:
        issues.append("result.corrections must be [] at first publish (use --correct afterwards)")
    if not result["evidence"]:
        issues.append("result.evidence is empty: every paper carries evidence entries")
    if "writer" in result and result["writer"] != writer:
        issues.append("result.writer differs from the bundle's writer")
    if not isinstance(result["quality_score"].get("audit_gate_failures"), dict):
        issues.append("result.quality_score.audit_gate_failures missing")
    return _gate(issues)


def check_snapshot(result: dict) -> dict:
    """Spec 2.6.3: every reader (page, TTS, Qdrant, curator) sees the same text and hero."""
    issues = []
    if result["report"] != result["published_report"]:
        issues.append("report and published_report differ: every reader must see the same text")
    if result["hero_image"] != result["published_hero_image"]:
        issues.append("hero_image and published_hero_image differ")
    return _gate(issues)


def check_artifact(report: str) -> tuple[dict, dict]:
    """validate_paper_artifact on the exact text being published: (gate, audit). No repair."""
    audit = validate_paper_artifact(report)
    return _gate(list(audit["issues"])[:20]), audit


def check_quality(quality_score: dict, audit: dict, *, require_stored_passed: bool) -> dict:
    """recompute_quality_passed against the fresh audit; for a first publish also the stored verdict.

    A correction recomputes only: the stored `passed` predates the corrected text
    and cannot be refreshed (the 2026-08-31 lesson in quality_gate.py).
    """
    stored = quality_score.get("passed") is True
    recomputed = recompute_quality_passed(quality_score, audit)
    issues = []
    if require_stored_passed and not stored:
        issues.append("quality_score.passed is not true")
    if not recomputed:
        issues.append("recompute_quality_passed rejects the paper against the fresh audit")
    return _gate(issues, stored_passed=stored, recomputed_passed=recomputed)


def check_evidence(report: str, evidence: list) -> dict:
    """Every entry well-formed and 'supported', every anchor on exactly one paragraph (C9)."""
    issues: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(evidence):
        if not isinstance(entry, dict):
            issues.append(f"evidence[{index}]: must be an object")
            continue
        label = entry["id"] if isinstance(entry.get("id"), str) else f"evidence[{index}]"
        missing = sorted(_EVIDENCE_KEYS - set(entry))
        unknown = sorted(set(entry) - _EVIDENCE_KEYS)
        if missing:
            issues.append(f"{label}: missing {missing}")
        if unknown:
            issues.append(f"{label}: unknown keys {unknown}")
        if missing:
            continue
        if not isinstance(entry["id"], str) or not EVIDENCE_ID_RE.match(entry["id"]):
            issues.append(f"{label}: id must look like ev-NN")
        elif entry["id"] in seen:
            issues.append(f"{label}: duplicate id")
        else:
            seen.add(entry["id"])
        for key in ("anchor_text", "claim", "quote"):
            if not (isinstance(entry[key], str) and entry[key].strip()):
                issues.append(f"{label}: {key} must be a non-empty string")
        source_ids = entry["source_ids"]
        if not (
            isinstance(source_ids, list)
            and source_ids
            and all(isinstance(s, str) and SOURCE_ID_RE.match(s) for s in source_ids)
        ):
            issues.append(f"{label}: source_ids must be a non-empty list of 12-hex source ids")
        elif entry["quote_source_id"] not in source_ids:
            issues.append(f"{label}: quote_source_id is not one of source_ids")
        if entry["verdict"] != "supported":
            issues.append(f"{label}: verdict is {entry['verdict']!r}; only 'supported' may be published")
    if issues:
        return _gate(issues, resolved={})
    resolved, anchor_issues = resolve_evidence_anchors(report, evidence)
    return _gate(anchor_issues, resolved=resolved)


def referenced_images(
    report: str, probative_images: list, hero_image: dict | None
) -> tuple[list[str], list[str]]:
    """(web paths the paper references, issues about entries that carry none)."""
    paths = list(_IMAGE_REF_RE.findall(report))
    issues: list[str] = []
    for index, entry in enumerate(probative_images):
        web_path = entry.get("web_path") if isinstance(entry, dict) else None
        if not isinstance(web_path, str):
            issues.append(f"probative_images[{index}] has no web_path")
            continue
        paths.append(web_path)
    if hero_image is not None:
        if isinstance(hero_image.get("src"), str):
            paths.append(hero_image["src"])
        else:
            issues.append("hero_image has no src")
        if isinstance(hero_image.get("web_path"), str):
            paths.append(hero_image["web_path"])
    return list(dict.fromkeys(paths)), issues


def check_images(
    request_id: str,
    report: str,
    probative_images: list,
    hero_image: dict | None,
    *,
    images_root: Path,
) -> dict:
    """Every referenced image is a file in research-images/<request_id>/ (uploaded before --apply)."""
    paths, issues = referenced_images(report, probative_images, hero_image)
    missing: list[str] = []
    foreign: list[str] = []
    for path in paths:
        match = _IMAGE_PATH_RE.match(path)
        if match is None:
            issues.append(f"not a research-images path: {path}")
            continue
        if match["rid"] != request_id:
            foreign.append(path)
            continue
        if not (images_root / request_id / match["name"]).is_file():
            missing.append(path)
    if foreign:
        issues.append(f"{len(foreign)} image(s) belong to another paper's folder")
    if missing:
        issues.append(f"{len(missing)} image(s) missing under research-images/{request_id}/")
    return _gate(issues, checked=len(paths), missing=missing, foreign=foreign)


def check_publish_status(status: str, is_public: bool, *, dry_run: bool) -> dict:
    """Publish needs a 'researched' or 'completed' row; --apply also needs it not public.

    A dry run on a public row passes (it answers "would this content pass") but
    reports apply_allowed=false: a public paper changes only through --correct.
    """
    eligible = status in ("researched", "completed")
    apply_allowed = eligible and not is_public
    issues = []
    if not eligible:
        issues.append(f"status is {status!r}; publish needs 'researched' or 'completed'")
    if is_public and not dry_run:
        issues.append("the paper is already public: --apply is refused, use --correct")
    return {
        "passed": not issues,
        "issues": issues,
        "status": status,
        "is_public": bool(is_public),
        "apply_allowed": apply_allowed,
    }
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publishing_gates.py tests/pipeline/test_theo_publishing_anchors.py -m "not integration and not live_llm" -q`
Expected: all pass (`17` gates tests counting the three slug parameters, `6` anchor tests).

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_gates.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_gates.py
git add pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_gates.py
git commit -m "Add the shared slug rule and the publish gates a Claude-written Theo paper must pass" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 16: Migration 0025 — the publication journal

**Files:**
- Create: `migrations/0025_theo_paper_publications.sql`
- Test: `tests/pipeline/test_migration_0025.py`

- [ ] **Step 1: Write the failing test**

`tests/pipeline/test_migration_0025.py`:

```python
"""Migration 0025: the journal of every write the Claude publish path makes."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PATH = REPO / "migrations" / "0025_theo_paper_publications.sql"


def _flat() -> str:
    return " ".join(PATH.read_text(encoding="utf-8").split())


def test_it_is_forward_only_and_idempotent():
    sql = PATH.read_text(encoding="utf-8")
    assert sql.lstrip().startswith("-- 0025_theo_paper_publications.sql")
    assert "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")
    assert "CREATE TABLE IF NOT EXISTS theo_paper_publications" in sql


def test_journal_rows_outlive_their_paper():
    assert "request_id UUID REFERENCES research_requests (id) ON DELETE SET NULL" in _flat()


def test_action_vocabulary_hash_shape_and_required_columns():
    flat = _flat()
    assert "CHECK (action IN ('publish', 'correct', 'register_video'))" in flat
    assert "CHECK (bundle_sha256 ~ '^[0-9a-f]{64}$')" in flat
    assert "writer JSONB NOT NULL" in flat
    assert "gates JSONB NOT NULL" in flat
    assert "side_effects JSONB," in flat


def test_artifact_reads_get_their_index():
    flat = _flat()
    assert (
        "CREATE INDEX IF NOT EXISTS idx_research_artifacts_request_kind_created "
        "ON research_artifacts (request_id, kind, created_at DESC)"
    ) in flat


def test_no_other_migration_claims_the_number():
    assert [p.name for p in (REPO / "migrations").glob("0025_*.sql")] == [PATH.name]
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_migration_0025.py -m "not integration and not live_llm" -q`
Expected: `5 failed` (`FileNotFoundError`).

- [ ] **Step 3: Create `migrations/0025_theo_paper_publications.sql`**

```sql
-- 0025_theo_paper_publications.sql
--
-- The journal of every write the Claude publish path makes to a Theo paper
-- (spec docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md,
-- sections 2.6-2.9). pipeline/lyra/theo_publishing.py inserts one row per
-- publish, correction and video registration, in the same transaction as the
-- research_requests UPDATE; the IndexNow and Qdrant side effects that run after
-- the commit are recorded afterwards in side_effects.
--
-- WHY: research_requests is outside apply_remediation_change's allow-list
-- (migration 0022), so without this table a published or corrected paper leaves
-- no record of who wrote it, which input bundle it came from and which gates it
-- passed.
--
-- request_id is ON DELETE SET NULL: a journal row outlives its paper (DELETE
-- /api/theo/research/{id} archives and deletes the row).
--
-- The second statement indexes research_artifacts for the dossier reads
-- (latest row per request and kind).
--
-- LOCKING: a new, empty table; the FK takes a brief SHARE ROW EXCLUSIVE lock on
-- research_requests. The index build takes a SHARE lock on research_artifacts
-- (a few hundred rows). Forward-only and idempotent (IF NOT EXISTS everywhere).

BEGIN;

CREATE TABLE IF NOT EXISTS theo_paper_publications (
    id            BIGSERIAL PRIMARY KEY,
    request_id    UUID REFERENCES research_requests (id) ON DELETE SET NULL,
    action        TEXT        NOT NULL,
    slug          TEXT,
    writer        JSONB       NOT NULL,
    bundle_sha256 CHAR(64)    NOT NULL,
    gates         JSONB       NOT NULL,
    side_effects  JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT theo_paper_publications_action_vocab
        CHECK (action IN ('publish', 'correct', 'register_video')),
    CONSTRAINT theo_paper_publications_sha256_shape
        CHECK (bundle_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_theo_paper_publications_request
    ON theo_paper_publications (request_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_research_artifacts_request_kind_created
    ON research_artifacts (request_id, kind, created_at DESC);

COMMENT ON TABLE theo_paper_publications IS
    'One row per write of the Claude publish path (publish, correct, register_video): '
    'writer, input bundle hash, gate results and post-commit side effects '
    '(pipeline/lyra/theo_publishing.py).';

COMMIT;
```

- [ ] **Step 4: Run the test**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_migration_0025.py -m "not integration and not live_llm" -q`
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add migrations/0025_theo_paper_publications.sql tests/pipeline/test_migration_0025.py
git commit -m "Add migration 0025, the journal of every Claude publish, correction and video registration" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 17: `publish_paper` and the side-effect sequence (`theo_publishing.py`, part 3)

**Files:**
- Modify: `pipeline/lyra/theo_publishing.py`
- Test: `tests/pipeline/test_theo_publishing_publish.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_theo_publishing_publish.py`:

```python
"""publish_paper (spec 2.6): gates, one guarded transaction with its journal row, re-read, side effects."""

from __future__ import annotations

import json

import pytest

from pipeline.lyra import theo_publishing as tp
from tests.fake_sql import FakeResult
from tests.pipeline.theo_publish_fixtures import (
    DOSSIER_SUMMARY,
    IMG_NAME,
    REPORT,
    REQ,
    WRITER,
    PublishSession,
    make_result,
    research_row,
)

SHA = "a" * 64
EFFECTS = {"indexnow": {"ok": True}, "qdrant": {"ok": True, "sections": 6}}


@pytest.fixture
def images(tmp_path):
    (tmp_path / REQ).mkdir()
    (tmp_path / REQ / IMG_NAME).write_bytes(b"jpeg")
    return tmp_path


@pytest.fixture
def effects(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return EFFECTS

    monkeypatch.setattr(tp, "run_publish_side_effects", fake)
    return calls


def _publish(session, images, *, dry_run=False, result=None):
    return tp.publish_paper(
        session,
        REQ,
        result or make_result(),
        writer=WRITER,
        dry_run=dry_run,
        bundle_sha256=SHA,
        images_root=images,
    )


def test_publish_writes_journals_verifies_and_announces(images, effects):
    session = PublishSession(research_row())
    outcome = _publish(session, images)

    assert outcome.ok is True
    assert outcome.slug == "the-baalbek-trilithon"
    assert outcome.url == "https://ancientnerds.com/research/the-baalbek-trilithon"
    assert outcome.journal_id == 42
    assert outcome.side_effects == EFFECTS
    assert set(outcome.gates) == {"status", "shape", "snapshot", "artifact", "quality", "evidence", "images"}

    update = session.statement_with("UPDATE research_requests")
    assert "status IN ('researched', 'completed') AND is_public = FALSE" in update
    assert "published_by = :author" in update
    stored = json.loads(session.written)
    assert stored["dossier"] == DOSSIER_SUMMARY
    assert stored["writer"] == WRITER
    assert stored["audit"]["passed"] is True
    assert stored["published_report"] == REPORT

    journal_params = next(p for sql, p in session.log if "INSERT INTO theo_paper_publications" in sql)
    assert journal_params["action"] == "publish"
    assert journal_params["bundle_sha256"] == SHA
    assert json.loads(journal_params["writer"]) == WRITER
    assert session.statement_with("UPDATE theo_paper_publications SET side_effects")
    assert session.commits == 2

    (call,) = effects
    assert call["slug"] == "the-baalbek-trilithon"
    assert call["author_username"] == "Theo"
    assert call["reindex"] is False
    assert call["paper_text"] == REPORT


def test_a_dry_run_writes_nothing(images, effects):
    session = PublishSession(research_row())
    outcome = _publish(session, images, dry_run=True)
    assert outcome.ok is True
    assert outcome.journal_id is None
    assert outcome.side_effects == {}
    assert not [sql for sql in session.statements() if "UPDATE" in sql or "INSERT" in sql]
    assert effects == []


def test_a_failed_gate_blocks_the_write(images, effects):
    result = make_result()
    result["evidence"][0]["verdict"] = "partly"
    session = PublishSession(research_row())
    outcome = _publish(session, images, result=result)
    assert outcome.ok is False
    assert outcome.gates["evidence"]["passed"] is False
    assert not [sql for sql in session.statements() if "UPDATE" in sql]


def test_a_public_row_passes_a_dry_run_but_refuses_apply(images, effects):
    row = research_row(status="completed", is_public=True, slug="the-baalbek-trilithon")
    dry = _publish(PublishSession(row), images, dry_run=True)
    assert dry.ok is True
    assert dry.gates["status"]["apply_allowed"] is False
    session = PublishSession(row)
    applied = _publish(session, images)
    assert applied.ok is False
    assert not [sql for sql in session.statements() if "UPDATE" in sql]


def test_a_row_changed_underneath_raises_a_conflict(images, effects):
    session = PublishSession(research_row(), update_rowcount=0)
    with pytest.raises(tp.PublishConflictError):
        _publish(session, images)
    assert session.rollbacks == 1
    assert effects == []


def test_a_re_read_that_differs_raises_after_commit(images, effects):
    session = PublishSession(research_row(), tamper=True)
    with pytest.raises(tp.PublishVerificationError, match="result_json differs"):
        _publish(session, images)
    assert effects == []


def test_an_unknown_request_is_an_input_error(images, effects):
    class Empty(PublishSession):
        def execute(self, stmt, params=None):
            if "published_by, published_at, result_json" in stmt.text:
                return FakeResult([])
            return super().execute(stmt, params)

    with pytest.raises(tp.PublishInputError, match="does not exist"):
        _publish(Empty(research_row()), images)


# --- side effects ---------------------------------------------------------------


def test_side_effects_record_a_qdrant_failure_without_raising(monkeypatch):
    submitted: list[list[str]] = []
    monkeypatch.setattr("pipeline.indexnow.submit", lambda urls: submitted.append(list(urls)) or True)

    def down(**kwargs):
        raise RuntimeError("qdrant down")

    monkeypatch.setattr("pipeline.lyra.theo_research_index.index_paper", down)
    effects = tp.run_publish_side_effects(
        request_id=REQ,
        slug="s",
        title="T",
        paper_text=REPORT,
        author_username="Theo",
        author_discord_id="442000112756064260",
        published_at="2026-09-28T10:00:00+00:00",
        reindex=False,
    )
    assert effects == {"indexnow": {"ok": True}, "qdrant": {"ok": False, "error": "RuntimeError: qdrant down"}}
    assert submitted == [["https://ancientnerds.com/research/s", "https://ancientnerds.com/research/"]]


def test_a_reindex_deletes_the_old_sections_first(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr("pipeline.indexnow.submit", lambda urls: True)
    monkeypatch.setattr(
        "pipeline.lyra.theo_research_index.delete_paper", lambda paper_id: order.append("delete") or 1
    )
    monkeypatch.setattr(
        "pipeline.lyra.theo_research_index.index_paper", lambda **kwargs: order.append("index") or 6
    )
    effects = tp.run_publish_side_effects(
        request_id=REQ,
        slug="s",
        title="T",
        paper_text=REPORT,
        author_username="Theo",
        author_discord_id="442000112756064260",
        published_at="2026-09-28T10:00:00+00:00",
        reindex=True,
    )
    assert order == ["delete", "index"]
    assert effects["qdrant"] == {"ok": True, "sections": 6}
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publishing_publish.py -m "not integration and not live_llm" -q`
Expected: failures (`AttributeError: ... 'run_publish_side_effects'` / `'publish_paper'`).

- [ ] **Step 3: Implement**

In `pipeline/lyra/theo_publishing.py` add to the imports:

```python
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
```

and append:

```python
# ---------------------------------------------------------------------------
# Outcome, errors, row access, journal
# ---------------------------------------------------------------------------


class PublishInputError(ValueError):
    """The input or its target row cannot be processed at all (CLI exit 2)."""


class PublishConflictError(RuntimeError):
    """The row changed between read and write; nothing was committed (CLI exit 3)."""


class PublishVerificationError(RuntimeError):
    """Committed, but the re-read row differs from what was written (CLI exit 4)."""


@dataclass
class PublishOutcome:
    """What every theo_publish mode prints (contract C8)."""

    ok: bool
    action: str
    request_id: str
    dry_run: bool
    slug: str | None = None
    url: str | None = None
    gates: dict[str, dict] = field(default_factory=dict)
    side_effects: dict[str, dict] = field(default_factory=dict)
    journal_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_ROW_SQL = text("""
    SELECT id::text AS id, status, is_public, slug, question, user_id,
           published_by, published_at, result_json
    FROM research_requests
    WHERE id = :id
""")
_VERIFY_SQL = text("SELECT status, is_public, slug, result_json FROM research_requests WHERE id = :id")
_JOURNAL_SQL = text("""
    INSERT INTO theo_paper_publications
        (request_id, action, slug, writer, bundle_sha256, gates, side_effects)
    VALUES (CAST(:request_id AS uuid), :action, :slug, CAST(:writer AS jsonb),
            :bundle_sha256, CAST(:gates AS jsonb), NULL)
    RETURNING id
""")
_SIDE_EFFECTS_SQL = text(
    "UPDATE theo_paper_publications SET side_effects = CAST(:side_effects AS jsonb) WHERE id = :id"
)
_PUBLISH_SQL = text("""
    UPDATE research_requests
    SET status = 'completed',
        completed_at = NOW(),
        result_json = :result,
        is_public = TRUE,
        published_at = NOW(),
        published_by = :author,
        slug = :slug
    WHERE id = :id AND status IN ('researched', 'completed') AND is_public = FALSE
""")


def _read_row(session: Any, request_id: str) -> Any:
    row = session.execute(_ROW_SQL, {"id": request_id}).fetchone()
    if row is None:
        raise PublishInputError(f"research request {request_id} does not exist")
    return row


def _stored_result(row: Any) -> dict:
    return json.loads(row.result_json) if row.result_json else {}


def _journal(
    session: Any,
    *,
    request_id: str,
    action: str,
    slug: str | None,
    writer: dict,
    bundle_sha256: str,
    gates: dict,
) -> int:
    journal_id = session.execute(
        _JOURNAL_SQL,
        {
            "request_id": request_id,
            "action": action,
            "slug": slug,
            "writer": json.dumps(writer),
            "bundle_sha256": bundle_sha256,
            "gates": json.dumps(gates),
        },
    ).scalar_one()
    return int(journal_id)


def _verify(session: Any, request_id: str, *, result: dict, slug: str | None) -> None:
    """Re-read the committed row; raise when it is not what was written."""
    row = session.execute(_VERIFY_SQL, {"id": request_id}).fetchone()
    if row is None:
        raise PublishVerificationError(f"{request_id} vanished after the commit")
    problems = []
    if row.status != "completed":
        problems.append(f"status is {row.status!r}")
    if row.is_public is not True:
        problems.append("is_public is not true")
    if row.slug != slug:
        problems.append(f"slug is {row.slug!r}, expected {slug!r}")
    if json.loads(row.result_json or "null") != result:
        problems.append("result_json differs from what was written")
    if problems:
        raise PublishVerificationError(
            f"{request_id} was committed but the re-read row differs: " + "; ".join(problems)
        )


def _record_side_effects(session: Any, journal_id: int, effects: dict) -> None:
    session.execute(_SIDE_EFFECTS_SQL, {"id": journal_id, "side_effects": json.dumps(effects)})
    session.commit()


def run_publish_side_effects(
    *,
    request_id: str,
    slug: str,
    title: str,
    paper_text: str,
    author_username: str,
    author_discord_id: str,
    published_at: str,
    reindex: bool,
) -> dict[str, dict]:
    """IndexNow ping and Qdrant index after the commit (spec 2.6.5); also used by the founder route.

    Failures are returned, not raised: they are journalled and never undo a
    publish. The nightly 03:00 UTC reindex (vector_sync) is the backstop for
    Qdrant; Lyra's submit_recent re-announces papers published in the last 2 h.
    `reindex` deletes the paper's old sections first (a correction may have fewer).
    """
    from pipeline.indexnow import page_url
    from pipeline.indexnow import submit as indexnow_submit
    from pipeline.lyra.theo_research_index import delete_paper, index_paper

    effects: dict[str, dict] = {
        "indexnow": {"ok": indexnow_submit([page_url(f"/research/{slug}"), page_url("/research/")])}
    }
    try:
        if reindex:
            delete_paper(request_id)
        sections = index_paper(
            paper_id=request_id,
            paper_text=paper_text,
            paper_title=title,
            paper_slug=slug,
            author_username=author_username,
            author_discord_id=author_discord_id,
            published_at=published_at,
        )
    except Exception as exc:  # noqa: BLE001 — journalled in side_effects, never undoes the publish (spec 2.6.5)
        effects["qdrant"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        effects["qdrant"] = {"ok": sections > 0, "sections": sections}
    return effects


# ---------------------------------------------------------------------------
# Publish (spec 2.6)
# ---------------------------------------------------------------------------


def publish_paper(
    session: Any,
    request_id: str,
    result: dict,
    *,
    author: str = PUBLISH_AUTHOR,
    writer: dict,
    dry_run: bool,
    bundle_sha256: str,
    images_root: Path = RESEARCH_IMAGES_DIR,
) -> PublishOutcome:
    """Gate, then publish a Claude-written paper in one guarded transaction with its journal row.

    Order: every gate (no repair) -> slug with collision handling -> UPDATE
    guarded on status IN ('researched','completed') AND is_public = FALSE plus the
    journal INSERT, one commit -> re-read and verify -> IndexNow + Qdrant, whose
    outcome is recorded in the journal row. A dry run stops after the slug.
    result_json keeps the research row's `dossier` summary.
    """
    row = _read_row(session, request_id)
    gates: dict[str, dict] = {
        "status": check_publish_status(row.status, row.is_public, dry_run=dry_run),
        "shape": check_publish_shape(result, writer),
    }
    audit: dict = {}
    if gates["shape"]["passed"]:
        gates["snapshot"] = check_snapshot(result)
        gates["artifact"], audit = check_artifact(result["report"])
        gates["quality"] = check_quality(result["quality_score"], audit, require_stored_passed=True)
        gates["evidence"] = check_evidence(result["report"], result["evidence"])
        gates["images"] = check_images(
            request_id,
            result["report"],
            result["probative_images"],
            result["hero_image"],
            images_root=images_root,
        )
    outcome = PublishOutcome(
        ok=all(gate["passed"] for gate in gates.values()),
        action="publish",
        request_id=request_id,
        dry_run=dry_run,
        gates=gates,
    )
    if not gates["shape"]["passed"]:
        return outcome

    from pipeline.indexnow import page_url

    slug = pick_slug(session, result["title"], request_id)
    outcome.slug = slug
    outcome.url = page_url(f"/research/{slug}")
    if dry_run or not outcome.ok:
        return outcome

    stored = {**result, "audit": audit, "writer": writer}
    previous = _stored_result(row)
    if "dossier" in previous:
        stored["dossier"] = previous["dossier"]
    updated = session.execute(
        _PUBLISH_SQL,
        {"id": request_id, "result": json.dumps(stored), "author": author, "slug": slug},
    )
    if updated.rowcount != 1:
        session.rollback()
        raise PublishConflictError(
            f"{request_id} changed between read and write (status or is_public); nothing committed"
        )
    outcome.journal_id = _journal(
        session,
        request_id=request_id,
        action="publish",
        slug=slug,
        writer=writer,
        bundle_sha256=bundle_sha256,
        gates=gates,
    )
    session.commit()
    _verify(session, request_id, result=stored, slug=slug)
    outcome.side_effects = run_publish_side_effects(
        request_id=request_id,
        slug=slug,
        title=result["title"],
        paper_text=stored["published_report"],
        author_username=author,
        author_discord_id=row.user_id,
        published_at=datetime.now(UTC).isoformat(),
        reindex=False,
    )
    _record_side_effects(session, outcome.journal_id, outcome.side_effects)
    return outcome
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publishing_publish.py tests/pipeline/test_theo_publishing_gates.py tests/pipeline/test_theo_publishing_anchors.py -m "not integration and not live_llm" -q`
Expected: all pass (`9` publish tests).

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_publish.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_publish.py
git add pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_publish.py
git commit -m "Publish a Claude-written Theo paper in one gated, journalled, re-verified transaction, then announce and index it" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 18: Corrections and video registration (`theo_publishing.py`, part 4)

**Files:**
- Modify: `pipeline/lyra/theo_publishing.py`
- Test: `tests/pipeline/test_theo_publishing_corrections.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_theo_publishing_corrections.py`:

```python
"""correct_paper and register_video (spec 2.7): public papers change only through the journal."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest

from pipeline.lyra import theo_publishing as tp
from pipeline.lyra.theo_citations import validate_paper_artifact
from tests.pipeline.theo_publish_fixtures import (
    DOSSIER_SUMMARY,
    EVIDENCE,
    IMG_NAME,
    REPORT,
    REQ,
    WRITER,
    PublishSession,
    make_result,
    research_row,
)

SHA = "b" * 64
SLUG = "the-baalbek-trilithon"
NEW_REPORT = REPORT.replace(
    "The quarry dates to the Roman period, which the excavation layers confirm [2].",
    "The quarry dates to the Roman period, as the stratified excavation layers confirm [2].",
)


def _live_row(**result_overrides):
    stored = {
        **make_result(),
        "audit": validate_paper_artifact(REPORT),
        "writer": WRITER,
        "dossier": DOSSIER_SUMMARY,
    }
    stored.update(result_overrides)
    return research_row(
        status="completed",
        is_public=True,
        slug=SLUG,
        published_by="Theo",
        published_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
        result_json=json.dumps(stored),
    )


@pytest.fixture
def images(tmp_path):
    (tmp_path / REQ).mkdir()
    (tmp_path / REQ / IMG_NAME).write_bytes(b"jpeg")
    return tmp_path


@pytest.fixture
def effects(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return {"indexnow": {"ok": True}, "qdrant": {"ok": True, "sections": 6}}

    monkeypatch.setattr(tp, "run_publish_side_effects", fake)
    return calls


def _correction(**overrides) -> dict:
    correction = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "report": NEW_REPORT,
        "corrections_append": [
            {"date": "2026-10-02", "text": "Clarified how the dating was established.", "evidence_id": "ev-02"}
        ],
    }
    correction.update(overrides)
    return correction


def _correct(session, images, correction, *, dry_run=False):
    return tp.correct_paper(session, REQ, correction, bundle_sha256=SHA, dry_run=dry_run, images_root=images)


def test_a_correction_replaces_both_texts_and_logs_itself(images, effects):
    session = PublishSession(_live_row())
    outcome = _correct(session, images, _correction())

    assert outcome.ok is True
    assert outcome.action == "correct"
    assert outcome.slug == SLUG
    assert outcome.journal_id == 42
    stored = json.loads(session.written)
    assert stored["report"] == NEW_REPORT
    assert stored["published_report"] == NEW_REPORT
    assert stored["corrections"] == _correction()["corrections_append"]
    assert [entry["id"] for entry in stored["evidence"]] == ["ev-01", "ev-02"]
    update = session.statement_with("UPDATE research_requests")
    assert "result_json = :previous" in update
    journal_params = next(p for sql, p in session.log if "INSERT INTO theo_paper_publications" in sql)
    assert journal_params["action"] == "correct"
    (call,) = effects
    assert call["reindex"] is True
    assert call["paper_text"] == NEW_REPORT
    assert call["published_at"] == "2026-09-28T10:00:00+00:00"


def test_removing_an_evidence_id_needs_a_correction_that_names_it(images, effects):
    unnamed = _correction(
        evidence=[copy.deepcopy(EVIDENCE[0])],
        corrections_append=[{"date": "2026-10-02", "text": "Dropped a claim."}],
    )
    outcome = _correct(PublishSession(_live_row()), images, unnamed)
    assert outcome.ok is False
    assert outcome.gates["retention"]["issues"] == ["ev-02 removed without a correction entry naming it"]

    named = _correction(
        evidence=[copy.deepcopy(EVIDENCE[0])],
        corrections_append=[{"date": "2026-10-02", "text": "Retired the dating claim.", "evidence_id": "ev-02"}],
    )
    assert _correct(PublishSession(_live_row()), images, named).ok is True


def test_a_retired_evidence_id_is_never_reused(images, effects):
    row = _live_row(corrections=[{"date": "2026-10-01", "text": "Retired ev-03.", "evidence_id": "ev-03"}])
    reused = {
        **copy.deepcopy(EVIDENCE[1]),
        "id": "ev-03",
        "anchor_text": "Both blocks were cut from the same limestone bed",
    }
    correction = _correction(evidence=[*copy.deepcopy(EVIDENCE), reused])
    outcome = _correct(PublishSession(row), images, correction)
    assert outcome.ok is False
    assert "ev-03 was retired earlier and may not be reused" in outcome.gates["retention"]["issues"]


def test_only_a_public_paper_takes_corrections(images, effects):
    outcome = _correct(PublishSession(research_row()), images, _correction())
    assert outcome.ok is False
    assert outcome.gates["status"]["passed"] is False


def test_a_correction_dry_run_writes_nothing(images, effects):
    session = PublishSession(_live_row())
    outcome = _correct(session, images, _correction(), dry_run=True)
    assert outcome.ok is True
    assert not [sql for sql in session.statements() if "UPDATE" in sql or "INSERT" in sql]


def test_a_concurrent_change_is_a_conflict(images, effects):
    with pytest.raises(tp.PublishConflictError):
        _correct(PublishSession(_live_row(), update_rowcount=0), images, _correction())


# --- register_video -------------------------------------------------------------


def _video(**overrides) -> dict:
    video = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "youtube_id": "dQw4w9WgXcQ",
        "title": "Who Really Moved the Baalbek Stones?",
        "published_at": "2026-10-05T16:00:00+00:00",
        "evidence_timestamps": {"ev-01": 41, "ev-02": 312},
    }
    video.update(overrides)
    return video


@pytest.fixture
def pinged(monkeypatch) -> list[list[str]]:
    urls: list[list[str]] = []
    monkeypatch.setattr("pipeline.indexnow.submit", lambda batch: urls.append(list(batch)) or True)
    return urls


def test_a_video_is_appended_and_announced(pinged):
    session = PublishSession(_live_row())
    outcome = tp.register_video(session, REQ, _video(), bundle_sha256=SHA, dry_run=False)
    assert outcome.ok is True
    stored = json.loads(session.written)
    (video,) = stored["videos"]
    assert video["youtube_id"] == "dQw4w9WgXcQ"
    assert video["evidence_timestamps"] == {"ev-01": 41, "ev-02": 312}
    assert "registered_at" in video
    assert outcome.side_effects == {"indexnow": {"ok": True}}
    assert pinged == [[f"https://ancientnerds.com/research/{SLUG}"]]
    journal_params = next(p for sql, p in session.log if "INSERT INTO theo_paper_publications" in sql)
    assert journal_params["action"] == "register_video"


def test_a_video_must_point_at_known_evidence_and_be_new(pinged):
    unknown = tp.register_video(
        PublishSession(_live_row()), REQ, _video(evidence_timestamps={"ev-09": 5}), bundle_sha256=SHA, dry_run=False
    )
    assert unknown.ok is False
    assert unknown.gates["evidence_refs"]["issues"] == ["ev-09 is not an evidence id of this paper"]

    row = _live_row(videos=[{"youtube_id": "dQw4w9WgXcQ"}])
    duplicate = tp.register_video(PublishSession(row), REQ, _video(), bundle_sha256=SHA, dry_run=False)
    assert duplicate.ok is False
    assert duplicate.gates["duplicate"]["passed"] is False


def test_a_malformed_video_fails_the_shape_gate(pinged):
    outcome = tp.register_video(
        PublishSession(_live_row()),
        REQ,
        _video(youtube_id="short", published_at="yesterday", evidence_timestamps={"ev-01": -3}),
        bundle_sha256=SHA,
        dry_run=True,
    )
    assert outcome.ok is False
    issues = outcome.gates["shape"]["issues"]
    assert "youtube_id must be an 11-character YouTube id" in issues
    assert "published_at must be an ISO 8601 date-time with a UTC offset" in issues
    assert "evidence_timestamps['ev-01'] must be a whole number of seconds >= 0" in issues
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publishing_corrections.py -m "not integration and not live_llm" -q`
Expected: failures (`AttributeError: ... 'correct_paper'`).

- [ ] **Step 3: Implement**

Add to the imports of `pipeline/lyra/theo_publishing.py`: `from datetime import UTC, date, datetime` (replacing the Task 17 line), and append:

```python
# ---------------------------------------------------------------------------
# Corrections and videos (spec 2.7). Only a completed, public paper changes here.
# ---------------------------------------------------------------------------

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CORRECTION_ENTRY_KEYS = frozenset({"date", "text", "evidence_id"})
_UPDATE_RESULT_SQL = text("""
    UPDATE research_requests
    SET result_json = :result
    WHERE id = :id AND status = 'completed' AND is_public = TRUE AND result_json = :previous
""")


def check_live_status(status: str, is_public: bool) -> dict:
    """Corrections and videos apply to a completed, public paper only."""
    issues = []
    if not (status == "completed" and is_public is True):
        issues.append(f"the paper must be completed and public (status={status!r}, is_public={is_public})")
    return _gate(issues, status=status, is_public=bool(is_public))


def _correction_entry_issues(entries: Any) -> list[str]:
    if not isinstance(entries, list) or not entries:
        return ["corrections_append must be a non-empty list: every change is logged on the page"]
    issues = []
    for index, entry in enumerate(entries):
        label = f"corrections_append[{index}]"
        if not isinstance(entry, dict):
            issues.append(f"{label} must be an object")
            continue
        unknown = sorted(set(entry) - _CORRECTION_ENTRY_KEYS)
        if unknown:
            issues.append(f"{label} has unknown keys {unknown}")
        day = entry.get("date")
        try:
            valid_day = isinstance(day, str) and date.fromisoformat(day).isoformat() == day
        except ValueError:
            valid_day = False
        if not valid_day:
            issues.append(f"{label}.date must be YYYY-MM-DD")
        if not (isinstance(entry.get("text"), str) and entry["text"].strip()):
            issues.append(f"{label}.text must be a non-empty string")
        if "evidence_id" in entry and not (
            isinstance(entry["evidence_id"], str) and EVIDENCE_ID_RE.match(entry["evidence_id"])
        ):
            issues.append(f"{label}.evidence_id must look like ev-NN")
    return issues


def check_correction_shape(correction: dict) -> dict:
    """Value types of a correction input (the CLI checked the keys, contract C5)."""
    issues = check_writer(correction.get("writer"))
    if "report" in correction and not (
        isinstance(correction["report"], str) and correction["report"].strip()
    ):
        issues.append("report must be a non-empty string when given")
    if "evidence" in correction and not isinstance(correction["evidence"], list):
        issues.append("evidence must be a list when given")
    issues.extend(_correction_entry_issues(correction.get("corrections_append")))
    return _gate(issues)


def check_evidence_retention(
    old_evidence: list, new_evidence: list, old_corrections: list, appended: list
) -> dict:
    """Published evidence ids stay: an id is retired only by a correction naming it, and never reused."""
    old_ids = {entry["id"] for entry in old_evidence}
    new_ids = {entry["id"] for entry in new_evidence if isinstance(entry, dict) and "id" in entry}
    named = {entry["evidence_id"] for entry in appended if entry.get("evidence_id")}
    previously_retired = {
        entry["evidence_id"] for entry in old_corrections if entry.get("evidence_id")
    } - old_ids
    issues = [f"{ev} removed without a correction entry naming it" for ev in sorted(old_ids - new_ids - named)]
    issues += [f"{ev} was retired earlier and may not be reused" for ev in sorted(new_ids & previously_retired)]
    issues += [
        f"a correction names {ev}, which this paper never had"
        for ev in sorted(named - old_ids - new_ids)
    ]
    return _gate(issues)


def _update_result(session: Any, row: Any, stored: dict) -> None:
    updated = session.execute(
        _UPDATE_RESULT_SQL,
        {"id": row.id, "result": json.dumps(stored), "previous": row.result_json},
    )
    if updated.rowcount != 1:
        session.rollback()
        raise PublishConflictError(f"{row.id} changed between read and write; nothing committed")


def correct_paper(
    session: Any,
    request_id: str,
    correction: dict,
    *,
    bundle_sha256: str,
    dry_run: bool,
    images_root: Path = RESEARCH_IMAGES_DIR,
) -> PublishOutcome:
    """Re-gate and apply a correction to a public paper: report and published_report
    change together, the corrections log grows, evidence ids are kept (C5)."""
    from pipeline.indexnow import page_url

    row = _read_row(session, request_id)
    gates: dict[str, dict] = {
        "status": check_live_status(row.status, row.is_public),
        "shape": check_correction_shape(correction),
    }
    current = _stored_result(row)
    new_report = correction.get("report", current.get("report", ""))
    new_evidence = correction.get("evidence", current.get("evidence", []))
    audit: dict = {}
    if gates["status"]["passed"] and gates["shape"]["passed"]:
        gates["retention"] = check_evidence_retention(
            current.get("evidence", []),
            new_evidence,
            current.get("corrections", []),
            correction["corrections_append"],
        )
        gates["artifact"], audit = check_artifact(new_report)
        gates["quality"] = check_quality(
            current.get("quality_score") or {}, audit, require_stored_passed=False
        )
        gates["evidence"] = check_evidence(new_report, new_evidence)
        gates["images"] = check_images(
            request_id,
            new_report,
            current.get("probative_images") or [],
            current.get("hero_image"),
            images_root=images_root,
        )
    outcome = PublishOutcome(
        ok=all(gate["passed"] for gate in gates.values()),
        action="correct",
        request_id=request_id,
        dry_run=dry_run,
        slug=row.slug,
        url=page_url(f"/research/{row.slug}") if row.slug else None,
        gates=gates,
    )
    if dry_run or not outcome.ok:
        return outcome

    stored = {
        **current,
        "report": new_report,
        "published_report": new_report,
        "evidence": new_evidence,
        "corrections": [*current.get("corrections", []), *correction["corrections_append"]],
        "audit": audit,
    }
    _update_result(session, row, stored)
    outcome.journal_id = _journal(
        session,
        request_id=request_id,
        action="correct",
        slug=row.slug,
        writer=correction["writer"],
        bundle_sha256=bundle_sha256,
        gates=gates,
    )
    session.commit()
    _verify(session, request_id, result=stored, slug=row.slug)
    outcome.side_effects = run_publish_side_effects(
        request_id=request_id,
        slug=row.slug,
        title=current["title"],
        paper_text=new_report,
        author_username=row.published_by,
        author_discord_id=row.user_id,
        published_at=row.published_at.isoformat(),
        reindex=True,
    )
    _record_side_effects(session, outcome.journal_id, outcome.side_effects)
    return outcome


def check_video_shape(video: dict) -> dict:
    """Value types of a video registration (the CLI checked the keys, contract C6)."""
    issues = check_writer(video.get("writer"))
    if not (isinstance(video.get("youtube_id"), str) and YOUTUBE_ID_RE.match(video["youtube_id"])):
        issues.append("youtube_id must be an 11-character YouTube id")
    if not (isinstance(video.get("title"), str) and video["title"].strip()):
        issues.append("title must be a non-empty string")
    published_at = video.get("published_at")
    try:
        valid_time = (
            isinstance(published_at, str) and datetime.fromisoformat(published_at).tzinfo is not None
        )
    except ValueError:
        valid_time = False
    if not valid_time:
        issues.append("published_at must be an ISO 8601 date-time with a UTC offset")
    stamps = video.get("evidence_timestamps")
    if not isinstance(stamps, dict):
        issues.append("evidence_timestamps must be an object")
    else:
        for ev, seconds in stamps.items():
            if not (isinstance(seconds, int) and not isinstance(seconds, bool) and seconds >= 0):
                issues.append(f"evidence_timestamps[{ev!r}] must be a whole number of seconds >= 0")
    return _gate(issues)


def register_video(
    session: Any, request_id: str, video: dict, *, bundle_sha256: str, dry_run: bool
) -> PublishOutcome:
    """Append a YouTube video to result_json.videos of a public paper (C6) and ping IndexNow."""
    from pipeline.indexnow import page_url
    from pipeline.indexnow import submit as indexnow_submit

    row = _read_row(session, request_id)
    gates: dict[str, dict] = {
        "status": check_live_status(row.status, row.is_public),
        "shape": check_video_shape(video),
    }
    current = _stored_result(row)
    if gates["status"]["passed"] and gates["shape"]["passed"]:
        known = {entry["id"] for entry in current.get("evidence", [])}
        gates["evidence_refs"] = _gate(
            [f"{ev} is not an evidence id of this paper" for ev in sorted(set(video["evidence_timestamps"]) - known)]
        )
        already = any(v.get("youtube_id") == video["youtube_id"] for v in current.get("videos", []))
        gates["duplicate"] = _gate(
            [f"video {video['youtube_id']} is already registered"] if already else []
        )
    outcome = PublishOutcome(
        ok=all(gate["passed"] for gate in gates.values()),
        action="register_video",
        request_id=request_id,
        dry_run=dry_run,
        slug=row.slug,
        url=page_url(f"/research/{row.slug}") if row.slug else None,
        gates=gates,
    )
    if dry_run or not outcome.ok:
        return outcome

    entry = {
        "youtube_id": video["youtube_id"],
        "title": video["title"],
        "published_at": video["published_at"],
        "evidence_timestamps": video["evidence_timestamps"],
        "registered_at": datetime.now(UTC).isoformat(),
    }
    stored = {**current, "videos": [*current.get("videos", []), entry]}
    _update_result(session, row, stored)
    outcome.journal_id = _journal(
        session,
        request_id=request_id,
        action="register_video",
        slug=row.slug,
        writer=video["writer"],
        bundle_sha256=bundle_sha256,
        gates=gates,
    )
    session.commit()
    _verify(session, request_id, result=stored, slug=row.slug)
    outcome.side_effects = {"indexnow": {"ok": indexnow_submit([page_url(f"/research/{row.slug}")])}}
    _record_side_effects(session, outcome.journal_id, outcome.side_effects)
    return outcome
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publishing_corrections.py tests/pipeline/test_theo_publishing_publish.py tests/pipeline/test_theo_publishing_gates.py tests/pipeline/test_theo_publishing_anchors.py -m "not integration and not live_llm" -q`
Expected: all pass (`9` correction/video tests).

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_corrections.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_corrections.py
git add pipeline/lyra/theo_publishing.py tests/pipeline/test_theo_publishing_corrections.py
git commit -m "Let public Theo papers change only through gated, journalled corrections and video registrations that keep every evidence id" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 19: The publish CLI (`python -m pipeline.lyra.theo_publish`)

**Files:**
- Create: `pipeline/lyra/theo_publish.py`
- Test: `tests/pipeline/test_theo_publish_cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_theo_publish_cli.py`:

```python
"""The publish CLI: modes, envelope validation, bundle hash, exit codes (contract C8)."""

from __future__ import annotations

import hashlib
import io
import json

import pytest

from pipeline.lyra import theo_publish as cli
from pipeline.lyra.theo_publishing import PublishConflictError, PublishOutcome
from tests.fake_sql import RecordingSession
from tests.pipeline.theo_publish_fixtures import REQ, WRITER, make_result


def _raw(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _bundle(**overrides) -> dict:
    bundle = {"version": 1, "request_id": REQ, "writer": WRITER, "result": make_result()}
    bundle.update(overrides)
    return bundle


@pytest.fixture
def seen(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []
    monkeypatch.setattr(cli, "get_session", lambda: RecordingSession())

    def fake_publish(session, request_id, result, *, writer, dry_run, bundle_sha256):
        calls.append(("publish", request_id, dry_run, bundle_sha256))
        return PublishOutcome(ok=True, action="publish", request_id=request_id, dry_run=dry_run, slug="t")

    def fake_correct(session, request_id, correction, *, bundle_sha256, dry_run):
        calls.append(("correct", request_id, dry_run, bundle_sha256))
        return PublishOutcome(ok=True, action="correct", request_id=request_id, dry_run=dry_run)

    def fake_video(session, request_id, video, *, bundle_sha256, dry_run):
        calls.append(("register_video", request_id, dry_run, bundle_sha256))
        return PublishOutcome(ok=True, action="register_video", request_id=request_id, dry_run=dry_run)

    monkeypatch.setattr(cli, "publish_paper", fake_publish)
    monkeypatch.setattr(cli, "correct_paper", fake_correct)
    monkeypatch.setattr(cli, "register_video", fake_video)
    return calls


def _run(args: list[str], raw: bytes) -> tuple[int, dict]:
    out = io.StringIO()
    code = cli.main(args, stdin=io.BytesIO(raw), stdout=out)
    return code, json.loads(out.getvalue())


def test_a_dry_run_hashes_the_raw_bundle(seen):
    raw = _raw(_bundle())
    code, outcome = _run(["--dry-run"], raw)
    assert code == 0
    assert outcome["ok"] is True
    assert seen == [("publish", REQ, True, hashlib.sha256(raw).hexdigest())]


def test_apply_publishes(seen):
    code, _outcome = _run(["--apply"], _raw(_bundle()))
    assert code == 0
    assert seen[0][:3] == ("publish", REQ, False)


def test_correct_and_register_video_have_their_own_dry_runs(seen):
    correction = {"version": 1, "request_id": REQ, "writer": WRITER, "corrections_append": []}
    assert _run(["--correct"], _raw(correction))[0] == 0
    video = {
        "version": 1,
        "request_id": REQ,
        "writer": WRITER,
        "youtube_id": "dQw4w9WgXcQ",
        "title": "T",
        "published_at": "2026-10-05T16:00:00+00:00",
        "evidence_timestamps": {},
    }
    assert _run(["--register-video", "--dry-run"], _raw(video))[0] == 0
    assert [call[:3] for call in seen] == [("correct", REQ, False), ("register_video", REQ, True)]


def test_a_failed_gate_exits_1(seen, monkeypatch):
    monkeypatch.setattr(
        cli,
        "publish_paper",
        lambda session, request_id, result, **kw: PublishOutcome(
            ok=False, action="publish", request_id=request_id, dry_run=True
        ),
    )
    code, outcome = _run(["--dry-run"], _raw(_bundle()))
    assert code == 1
    assert outcome["ok"] is False


@pytest.mark.parametrize(
    "raw",
    [
        b"{not json",
        json.dumps(_bundle(version=2)).encode(),
        json.dumps(_bundle(request_id="not-a-uuid")).encode(),
        json.dumps(_bundle(author="Somebody")).encode(),
        json.dumps({"version": 1, "request_id": REQ, "writer": WRITER}).encode(),
        json.dumps(_bundle(result=[])).encode(),
    ],
)
def test_unusable_input_exits_2(seen, raw):
    code, outcome = _run(["--apply"], raw)
    assert code == 2
    assert outcome["ok"] is False
    assert outcome["error"]
    assert seen == []


def test_a_conflict_exits_3(seen, monkeypatch):
    def conflict(session, request_id, result, **kw):
        raise PublishConflictError("row changed")

    monkeypatch.setattr(cli, "publish_paper", conflict)
    code, outcome = _run(["--apply"], _raw(_bundle()))
    assert code == 3
    assert outcome == {"ok": False, "error": "row changed"}


@pytest.mark.parametrize("args", [[], ["--apply", "--dry-run"], ["--apply", "--correct"]])
def test_exactly_one_mode(args):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(args, stdin=io.BytesIO(b"{}"), stdout=io.StringIO())
    assert exit_info.value.code == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publish_cli.py -m "not integration and not live_llm" -q`
Expected: collection error `No module named 'pipeline.lyra.theo_publish'`.

- [ ] **Step 3: Create `pipeline/lyra/theo_publish.py`**

```python
"""Publish, correct and video-link Claude-written Theo papers (spec 2.6, 2.7). API image.

Run from a local Claude session over ssh, so production credentials never
leave the VPS:

    ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --dry-run < bundle.json
    ... --apply < bundle.json
    ... --correct [--dry-run] < correction.json
    ... --register-video [--dry-run] < video.json

Prints a PublishOutcome as JSON (contract C8). Exit codes: 0 ok, 1 a gate
failed, 2 unusable input, 3 the row changed between read and write (nothing
committed), 4 committed but the re-read row differs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from typing import BinaryIO, TextIO

from pipeline.database import get_session
from pipeline.lyra.theo_publishing import (
    PublishConflictError,
    PublishInputError,
    PublishVerificationError,
    correct_paper,
    publish_paper,
    register_video,
)

EXIT_OK = 0
EXIT_GATES = 1
EXIT_INPUT = 2
EXIT_CONFLICT = 3
EXIT_UNVERIFIED = 4

#: action -> (required top-level keys, optional top-level keys) (contracts C4-C6)
ENVELOPES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "publish": (frozenset({"version", "request_id", "writer", "result"}), frozenset()),
    "correct": (
        frozenset({"version", "request_id", "writer", "corrections_append"}),
        frozenset({"report", "evidence"}),
    ),
    "register_video": (
        frozenset(
            {"version", "request_id", "writer", "youtube_id", "title", "published_at", "evidence_timestamps"}
        ),
        frozenset(),
    ),
}


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.lyra.theo_publish",
        description="Publish, correct or video-link a Claude-written Theo paper (input on stdin).",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true", help="publish the bundle")
    modes.add_argument("--correct", action="store_true", help="apply a correction to a public paper")
    modes.add_argument("--register-video", action="store_true", help="append a YouTube video")
    parser.add_argument("--dry-run", action="store_true", help="run every gate, write nothing")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run exclude each other")
    if not (args.apply or args.correct or args.register_video or args.dry_run):
        parser.error("choose one of --dry-run, --apply, --correct, --register-video")
    if args.correct:
        args.action = "correct"
    elif args.register_video:
        args.action = "register_video"
    else:
        args.action = "publish"
    return args


def _check_envelope(payload: object, action: str) -> dict:
    """The top-level keys and ids of the input; value types are the gates' business."""
    if not isinstance(payload, dict):
        raise PublishInputError("the input must be a JSON object")
    required, optional = ENVELOPES[action]
    missing = sorted(required - set(payload))
    unknown = sorted(set(payload) - required - optional)
    if missing:
        raise PublishInputError(f"missing keys: {missing}")
    if unknown:
        raise PublishInputError(f"unknown keys: {unknown}")
    if payload["version"] != 1:
        raise PublishInputError(f"unsupported version {payload['version']!r} (expected 1)")
    try:
        uuid.UUID(str(payload["request_id"]))
    except ValueError:
        raise PublishInputError(f"request_id is not a UUID: {payload['request_id']!r}") from None
    if action == "publish" and not isinstance(payload["result"], dict):
        raise PublishInputError("result must be a JSON object")
    return payload


def _error(out: TextIO, message: str, code: int) -> int:
    out.write(json.dumps({"ok": False, "error": message}) + "\n")
    return code


def main(
    argv: list[str] | None = None, *, stdin: BinaryIO | None = None, stdout: TextIO | None = None
) -> int:
    args = _parse(argv)
    out = stdout or sys.stdout
    raw = (stdin or sys.stdin.buffer).read()
    try:
        payload = _check_envelope(json.loads(raw.decode("utf-8")), args.action)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _error(out, f"the input is not UTF-8 JSON: {exc}", EXIT_INPUT)
    except PublishInputError as exc:
        return _error(out, str(exc), EXIT_INPUT)
    bundle_sha256 = hashlib.sha256(raw).hexdigest()
    request_id = str(payload["request_id"])
    try:
        with get_session() as session:
            if args.action == "publish":
                outcome = publish_paper(
                    session,
                    request_id,
                    payload["result"],
                    writer=payload["writer"],
                    dry_run=args.dry_run,
                    bundle_sha256=bundle_sha256,
                )
            elif args.action == "correct":
                outcome = correct_paper(
                    session, request_id, payload, bundle_sha256=bundle_sha256, dry_run=args.dry_run
                )
            else:
                outcome = register_video(
                    session, request_id, payload, bundle_sha256=bundle_sha256, dry_run=args.dry_run
                )
    except PublishInputError as exc:
        return _error(out, str(exc), EXIT_INPUT)
    except PublishConflictError as exc:
        return _error(out, str(exc), EXIT_CONFLICT)
    except PublishVerificationError as exc:
        return _error(out, str(exc), EXIT_UNVERIFIED)
    out.write(json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2) + "\n")
    return EXIT_OK if outcome.ok else EXIT_GATES


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_publish_cli.py -m "not integration and not live_llm" -q`
Expected: `14 passed` (6 input variants and 3 mode variants counted).

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/theo_publish.py tests/pipeline/test_theo_publish_cli.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/theo_publish.py tests/pipeline/test_theo_publish_cli.py
git add pipeline/lyra/theo_publish.py tests/pipeline/test_theo_publish_cli.py
git commit -m "Add the theo_publish CLI that a local Claude session runs inside the API container to publish, correct and video-link papers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 20: The dossier CLI (`python -m pipeline.lyra.theo_dossier`)

**Files:**
- Create: `pipeline/lyra/theo_dossier.py`
- Test: `tests/pipeline/test_theo_dossier.py`

- [ ] **Step 1: Write the failing tests**

`tests/pipeline/test_theo_dossier.py`:

```python
"""Dossier export (contract C3): manifest dossiers, legacy runs, texts, list, CLI."""

from __future__ import annotations

import gzip
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from pipeline.lyra import theo_dossier as td
from tests.fake_sql import FakeResult, RecordingSession

REQ = "11111111-2222-3333-4444-555555555555"
S_CORE, S_FINDING, S_FAR, S_TDM, S_NONE = (
    "aaaaaaaaaaa1",
    "aaaaaaaaaaa2",
    "aaaaaaaaaaa3",
    "aaaaaaaaaaa4",
    "aaaaaaaaaaa5",
)

MODERATED = {
    "final_claims": [{"claim": "c", "source_ids": [S_CORE, S_TDM]}],
    "revised_claims": [],
    "speculative_claims": [],
    "dropped_claims": [],
}
ANGLE = {
    "id": "ang1",
    "topic": "Quarry",
    "description": "d",
    "findings": [
        {"claim": "f1", "source_ids": [S_CORE, S_FINDING]},
        {"claim": "f2", "source_ids": [S_FAR]},
    ],
    "search_queries": ["q"],
}
STALE_ANGLE = {**ANGLE, "id": "old1", "topic": "From a deferred first attempt"}


def _source(sid: str) -> dict:
    return {
        "id": sid,
        "url": f"https://x.example/{sid}",
        "title": sid,
        "domain": "x.example",
        "reliability_tier": 1,
        "doi": "",
        "authors": [],
        "venue": "",
        "date": "2014",
        "license": "",
        "source_api": "openalex",
        "snippet_chars": 10,
        "access_timestamp": "",
        "search_query": "",
        "citation_count": 0,
        "self_source": False,
    }


REGISTRY = {"sources": [_source(s) for s in (S_CORE, S_FINDING, S_FAR, S_TDM, S_NONE)], "claims": [], "reference_numbers": {}}
POOL = {"ang1": [{"url": "https://commons.example/File:A.jpg"}]}
MANIFEST = {"version": 1, "request_id": REQ, "angle_ids": ["ang1"], "counts": {"final_claims": 1}}


def _art(kind, payload, ref=""):
    return SimpleNamespace(kind=kind, ref=ref, payload=payload)


def _archive(sid, content_type="text/html", chars=100, tdm=False, text=None):
    return SimpleNamespace(
        source_id=sid,
        url=f"https://x.example/{sid}",
        content_type=content_type,
        text_chars=chars,
        fetched_at=datetime(2026, 9, 28, tzinfo=UTC),
        tdm_opt_out=tdm,
        full_text=text,
    )


REQUEST_ROW = SimpleNamespace(
    id=REQ,
    question="Who cut the Baalbek monoliths?",
    status="researched",
    is_batch=True,
    user_id="442000112756064260",
    created_at=datetime(2026, 9, 27, 20, 0),
    completed_at=datetime(2026, 9, 28, 9, 15),
    llm_calls=399,
    total_tokens=12345678,
    duration_ms=39_600_000,
)
ARCHIVE_ROWS = [
    _archive(S_CORE, text="core text"),
    _archive(S_FINDING, text="finding text"),
    _archive(S_FAR, text="far text"),
    _archive(S_TDM, chars=0, tdm=True),
]


class _ArchiveSession(RecordingSession):
    """Answers theo_source_archive reads for the requested ids only, as the database does."""

    def execute(self, stmt, params=None):
        result = super().execute(stmt, params)
        if "FROM theo_source_archive" in stmt.text:
            return FakeResult([row for row in ARCHIVE_ROWS if row.source_id in params["ids"]])
        return result


def _session(artifacts) -> RecordingSession:
    return _ArchiveSession({"FROM research_requests": [REQUEST_ROW], "FROM research_artifacts": artifacts})


DOSSIER_ARTIFACTS = [
    _art("dossier", MANIFEST),
    _art("moderated", MODERATED),
    _art("synthesis", {"synthesis": {}, "cross_angle_connections": []}),
    _art("debate", {"rounds": 4}),
    _art("angle_findings", ANGLE, "ang1"),
    _art("angle_findings", STALE_ANGLE, "old1"),
    _art("citation_registry", REGISTRY),
    _art("image_candidate_pool", POOL),
]


def test_export_of_a_dossier_ships_the_cited_texts_only():
    bundle = td.build_export(_session(DOSSIER_ARTIFACTS), REQ, texts="cited")
    assert bundle["version"] == 1
    assert bundle["texts_mode"] == "cited"
    assert bundle["manifest"] == MANIFEST
    assert bundle["request"]["status"] == "researched"
    assert bundle["request"]["completed_at"] == "2026-09-28T09:15:00"
    assert [angle["id"] for angle in bundle["angles"]] == ["ang1"]
    assert set(bundle["angles"][0]) == {"id", "topic", "description", "findings"}
    assert bundle["texts"] == {S_CORE: "core text", S_FINDING: "finding text"}
    sources = {source["id"]: source for source in bundle["sources"]}
    assert len(sources) == 5
    assert sources[S_TDM]["archive"]["tdm_opt_out"] is True
    assert sources[S_NONE]["archive"] is None
    assert "snippet_chars" not in sources[S_CORE]
    assert bundle["images"] == POOL


def test_all_texts_on_request():
    bundle = td.build_export(_session(DOSSIER_ARTIFACTS), REQ, texts="all")
    assert set(bundle["texts"]) == {S_CORE, S_FINDING, S_FAR}


def test_a_legacy_run_exports_with_a_computed_manifest():
    legacy = [
        _art("moderated", MODERATED),
        _art("synthesis", {"synthesis": {}, "cross_angle_connections": []}),
        _art("debate", {"rounds": 4}),
        _art("angle_findings", ANGLE, "ang1"),
        _art("citation_registry", REGISTRY),
        _art("paper_final", {"image_candidate_pool": POOL, "title": "Old paper"}),
    ]
    bundle = td.build_export(_session(legacy), REQ, texts="cited")
    manifest = bundle["manifest"]
    assert manifest["legacy"] is True
    assert manifest["angle_ids"] == ["ang1"]
    assert manifest["archive"]["cited_sources"] == 2
    assert manifest["archive"]["full_text"] == 1
    assert manifest["archive"]["tdm_reserved"] == 1
    assert manifest["research"] == {"llm_calls": 399, "total_tokens": 12345678, "duration_s": 39600.0}
    assert bundle["images"] == POOL


def test_an_incomplete_dossier_is_refused():
    broken = [artifact for artifact in DOSSIER_ARTIFACTS if artifact.kind != "citation_registry"]
    with pytest.raises(td.DossierExportError, match="citation_registry"):
        td.build_export(_session(broken), REQ, texts="cited")


def test_an_unknown_request_is_refused():
    session = RecordingSession({})
    with pytest.raises(td.DossierExportError, match="does not exist"):
        td.build_export(session, REQ, texts="cited")


def test_list_shows_researched_rows_with_their_summary():
    row = SimpleNamespace(
        id=REQ,
        question="q",
        status="researched",
        is_batch=True,
        created_at=datetime(2026, 9, 27, 20, 0),
        completed_at=datetime(2026, 9, 28, 9, 15),
        result_json=json.dumps({"dossier": {"artifact_id": 8}, "title": None}),
    )
    session = RecordingSession({"FROM research_requests": [row]})
    assert td.list_researched(session) == [
        {
            "id": REQ,
            "question": "q",
            "status": "researched",
            "is_batch": True,
            "created_at": "2026-09-27T20:00:00",
            "completed_at": "2026-09-28T09:15:00",
            "dossier": {"artifact_id": 8},
        }
    ]
    assert "WHERE status = 'researched'" in session.statements()[0]


def test_the_cli_writes_gzip_json(monkeypatch):
    monkeypatch.setattr(td, "get_session", lambda: _session(DOSSIER_ARTIFACTS))
    buffer = io.BytesIO()
    assert td.main(["export", REQ], stdout_bytes=buffer) == 0
    bundle = json.loads(gzip.decompress(buffer.getvalue()).decode("utf-8"))
    assert bundle["request"]["id"] == REQ


def test_the_cli_rejects_a_bad_id_and_reports_a_missing_dossier(monkeypatch):
    assert td.main(["export", "nope"], stdout_bytes=io.BytesIO()) == 2
    monkeypatch.setattr(td, "get_session", lambda: RecordingSession({}))
    assert td.main(["export", REQ], stdout_bytes=io.BytesIO()) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_dossier.py -m "not integration and not live_llm" -q`
Expected: collection error `No module named 'pipeline.lyra.theo_dossier'`.

- [ ] **Step 3: Create `pipeline/lyra/theo_dossier.py`**

```python
"""Dossier export for the Claude write (spec 2.8). Runs in the API container.

    ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier list
    ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier export <id> [--texts cited|all] > dossier.json.gz

`export` writes gzip'd JSON (contract C3) to stdout. Runs without a 'dossier'
manifest (the full-pipeline runs since the corpus started, e.g. 95fa3798)
export too, from their per-stage artifacts, with `"legacy": true`.
Exit codes: 0 ok, 1 no or incomplete dossier, 2 bad request id.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import uuid
from collections import Counter
from typing import Any, BinaryIO, TextIO

from sqlalchemy import text

from pipeline.database import get_session
from pipeline.lyra.dossier_manifest import (
    DOSSIER_VERSION,
    cited_source_ids,
    moderated_source_ids,
)
from pipeline.lyra.training_corpus import best_archive_rows_in, classify_archive_row

EXPORT_VERSION = 1

_LIST_SQL = text("""
    SELECT id::text AS id, question, status, is_batch, created_at, completed_at, result_json
    FROM research_requests
    WHERE status = 'researched'
    ORDER BY completed_at ASC
""")
_REQUEST_SQL = text("""
    SELECT id::text AS id, question, status, is_batch, user_id, created_at, completed_at,
           llm_calls, total_tokens, duration_ms
    FROM research_requests
    WHERE id = :id
""")
_ARTIFACTS_SQL = text("""
    SELECT DISTINCT ON (kind, ref) kind, ref, payload
    FROM research_artifacts
    WHERE request_id = :id AND kind = ANY(:kinds)
    ORDER BY kind, ref, created_at DESC, id DESC
""")
# The kinds the export ships (specialist_analyses is corpus material, not writer input).
_DOSSIER_REQUIRED = (
    "moderated",
    "synthesis",
    "debate",
    "angle_findings",
    "citation_registry",
    "image_candidate_pool",
)
_LEGACY_REQUIRED = ("moderated", "synthesis", "debate", "angle_findings", "citation_registry", "paper_final")
_EXPORT_KINDS = ["dossier", *_DOSSIER_REQUIRED, "paper_final"]
_SOURCE_KEYS = (
    "id",
    "url",
    "title",
    "domain",
    "reliability_tier",
    "doi",
    "authors",
    "venue",
    "date",
    "license",
    "source_api",
)


class DossierExportError(RuntimeError):
    """The request has no dossier, or its dossier is incomplete."""


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def list_researched(session: Any) -> list[dict]:
    """Researched rows with their dossier summary, oldest first (the writing queue)."""
    rows = session.execute(_LIST_SQL).fetchall()
    return [
        {
            "id": row.id,
            "question": row.question,
            "status": row.status,
            "is_batch": bool(row.is_batch),
            "created_at": _iso(row.created_at),
            "completed_at": _iso(row.completed_at),
            "dossier": json.loads(row.result_json)["dossier"],
        }
        for row in rows
    ]


def _export_source(source: dict, archive: dict | None) -> dict:
    entry = {key: source[key] for key in _SOURCE_KEYS}
    entry["archive"] = (
        None
        if archive is None
        else {
            "content_type": archive["content_type"],
            "text_chars": archive["text_chars"],
            "fetched_at": _iso(archive["fetched_at"]),
            "tdm_opt_out": archive["tdm_opt_out"],
        }
    )
    return entry


def _legacy_manifest(
    row: Any, parts: dict, angles: list[dict], images: dict, archive: dict[str, dict]
) -> dict:
    """What a manifest would say for a run that predates the DossierHandler."""
    moderated = parts["moderated"][""]
    cited = moderated_source_ids(moderated)
    classes = Counter(classify_archive_row(archive.get(source_id)) for source_id in cited)
    return {
        "version": DOSSIER_VERSION,
        "legacy": True,
        "request_id": row.id,
        "question": row.question,
        "created_at": None,
        "angle_ids": [angle["id"] for angle in angles],
        "counts": {
            "angles": len(angles),
            "findings": sum(len(angle["findings"]) for angle in angles),
            "sources": len(parts["citation_registry"][""]["sources"]),
            "final_claims": len(moderated.get("final_claims") or []),
            "revised_claims": len(moderated.get("revised_claims") or []),
            "speculative_claims": len(moderated.get("speculative_claims") or []),
            "images": sum(len(pool) for pool in images.values()),
        },
        "kinds": sorted(parts),
        "archive": {
            "cited_sources": len(cited),
            "full_text": classes["full_text"],
            "abstract_only": classes["abstract_only"],
            "missing": classes["missing"],
            "tdm_reserved": classes["tdm_reserved"],
            "failures": [],
            "duration_s": 0.0,
            "timed_out": False,
        },
        "research": {
            "llm_calls": row.llm_calls,
            "total_tokens": row.total_tokens,
            "duration_s": round(row.duration_ms / 1000, 1) if row.duration_ms is not None else None,
        },
    }


def build_export(session: Any, request_id: str, *, texts: str) -> dict:
    """The export bundle of one request (contract C3). texts: 'cited' or 'all'."""
    row = session.execute(_REQUEST_SQL, {"id": request_id}).fetchone()
    if row is None:
        raise DossierExportError(f"research request {request_id} does not exist")
    parts: dict[str, dict[str, Any]] = {}
    for artifact in session.execute(_ARTIFACTS_SQL, {"id": request_id, "kinds": _EXPORT_KINDS}).fetchall():
        parts.setdefault(artifact.kind, {})[artifact.ref] = artifact.payload

    legacy = "dossier" not in parts
    required = _LEGACY_REQUIRED if legacy else _DOSSIER_REQUIRED
    missing = [kind for kind in required if kind not in parts]
    if missing:
        label = "has no dossier and its per-stage artifacts are incomplete" if legacy else "has an incomplete dossier"
        raise DossierExportError(f"{request_id} {label}: missing {missing}")

    angle_rows = parts["angle_findings"]
    angle_ids = sorted(angle_rows) if legacy else parts["dossier"][""]["angle_ids"]
    absent = [angle_id for angle_id in angle_ids if angle_id not in angle_rows]
    if absent:
        raise DossierExportError(f"{request_id}: angle_findings rows missing for {absent}")
    angles = [
        {key: angle_rows[angle_id][key] for key in ("id", "topic", "description", "findings")}
        for angle_id in angle_ids
    ]
    if legacy:
        if "image_candidate_pool" not in parts["paper_final"][""]:
            raise DossierExportError(f"{request_id}: paper_final carries no image_candidate_pool")
        images = parts["paper_final"][""]["image_candidate_pool"]
    else:
        images = parts["image_candidate_pool"][""]

    moderated = parts["moderated"][""]
    registry = parts["citation_registry"][""]
    source_ids = [source["id"] for source in registry["sources"]]
    archive = best_archive_rows_in(session, source_ids, with_text=False)
    manifest = (
        _legacy_manifest(row, parts, angles, images, archive) if legacy else parts["dossier"][""]
    )
    text_ids = cited_source_ids(moderated, angles) if texts == "cited" else source_ids
    text_rows = best_archive_rows_in(session, text_ids, with_text=True)
    return {
        "version": EXPORT_VERSION,
        "texts_mode": texts,
        "request": {
            "id": row.id,
            "question": row.question,
            "status": row.status,
            "is_batch": bool(row.is_batch),
            "user_id": row.user_id,
            "created_at": _iso(row.created_at),
            "completed_at": _iso(row.completed_at),
        },
        "manifest": manifest,
        "moderated": moderated,
        "synthesis": parts["synthesis"][""],
        "debate": parts["debate"][""],
        "angles": angles,
        "sources": [_export_source(source, archive.get(source["id"])) for source in registry["sources"]],
        "texts": {
            source_id: entry["full_text"]
            for source_id, entry in text_rows.items()
            if entry["full_text"] and not entry["tdm_opt_out"]
        },
        "images": images,
    }


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stdout_bytes: BinaryIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.lyra.theo_dossier", description="Theo dossiers for the Claude write."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="researched rows with their dossier summary (JSON)")
    export = commands.add_parser("export", help="gzip'd JSON export bundle on stdout")
    export.add_argument("request_id")
    export.add_argument("--texts", choices=("cited", "all"), default="cited")
    args = parser.parse_args(argv)

    if args.command == "list":
        with get_session() as session:
            rows = list_researched(session)
        (stdout or sys.stdout).write(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
        return 0

    try:
        uuid.UUID(args.request_id)
    except ValueError:
        print(f"not a request id: {args.request_id!r}", file=sys.stderr)
        return 2
    try:
        with get_session() as session:
            bundle = build_export(session, args.request_id, texts=args.texts)
    except DossierExportError as exc:
        print(f"dossier export failed: {exc}", file=sys.stderr)
        return 1
    data = gzip.compress(json.dumps(bundle, ensure_ascii=False).encode("utf-8"), mtime=0)
    (stdout_bytes or sys.stdout.buffer).write(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_theo_dossier.py -m "not integration and not live_llm" -q`
Expected: `8 passed`.

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/theo_dossier.py tests/pipeline/test_theo_dossier.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/theo_dossier.py tests/pipeline/test_theo_dossier.py
git add pipeline/lyra/theo_dossier.py tests/pipeline/test_theo_dossier.py
git commit -m "Add the theo_dossier CLI that lists researched runs and exports a dossier with its source texts, legacy runs included" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 21: API routes know `researched` and share the publish sequence

**Files:**
- Modify: `api/routes/theo.py` (imports lines 20-52, `_make_slug` 117-122, stream 1070-1083, publish route 1414-1488)
- Test: `tests/api/test_theo_routes_researched.py`

- [ ] **Step 1: Write the failing tests**

`tests/api/test_theo_routes_researched.py`:

```python
"""Owner routes and the 'researched' status (spec 2.5)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import theo as theo_routes
from pipeline.lyra import theo_publishing
from tests.fake_sql import RecordingSession

REQ = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(theo_routes, "_get_user_id", lambda req: "owner-1")
    app = FastAPI()
    app.include_router(theo_routes.router)
    with TestClient(app) as test_client:
        yield test_client


def test_the_stream_of_a_researched_run_ends_at_once(client, monkeypatch):
    session = RecordingSession(
        {"SELECT user_id, status FROM research_requests": [SimpleNamespace(user_id="owner-1", status="researched")]}
    )
    monkeypatch.setattr(theo_routes, "get_session", lambda: session)
    response = client.get(f"/research/{REQ}/stream")
    assert response.status_code == 200
    assert "event: done" in response.text
    assert '"status": "researched"' in response.text


def test_deleting_a_researched_row_archives_it_first(client, monkeypatch):
    session = RecordingSession(
        {
            "SELECT user_id, status, is_public FROM research_requests": [
                SimpleNamespace(user_id="owner-1", status="researched", is_public=False)
            ]
        }
    )
    monkeypatch.setattr(theo_routes, "get_session", lambda: session)
    response = client.delete(f"/research/{REQ}")
    assert response.status_code == 200
    statements = session.statements()
    archive = next(i for i, sql in enumerate(statements) if "INSERT INTO research_requests_archive" in sql)
    delete = next(i for i, sql in enumerate(statements) if "DELETE FROM research_requests" in sql)
    assert archive < delete


def test_the_route_uses_the_shared_slug_rule_and_side_effects():
    assert not hasattr(theo_routes, "_make_slug")
    assert theo_routes.pick_slug is theo_publishing.pick_slug
    assert theo_routes.run_publish_side_effects is theo_publishing.run_publish_side_effects
    assert "researched" in theo_routes._STREAM_TERMINAL_STATUSES
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_theo_routes_researched.py -m "not integration and not live_llm" -q --timeout 20`
Expected: the stream test fails by timeout (with the current code a `researched` row falls into the 5-minute polling stream), the shared-rule test fails (`_make_slug` still exists); the delete test already passes (it pins existing behaviour).

- [ ] **Step 3: Implement**

In `api/routes/theo.py`:

(a) Remove `import re` (its only use was `_make_slug`), and add below the `from pipeline.indexnow import …` lines:

```python
from pipeline.lyra.theo_publishing import pick_slug, run_publish_side_effects
```

(b) Delete the function `_make_slug` (it lives on as `pipeline.lyra.theo_publishing.make_slug`).

(c) Add after the `_estimate_minutes` function:

```python
# Statuses after which a run emits no more live events. 'researched' is the
# research-only end of a run: the dossier waits for the Claude write (spec 2.5).
_STREAM_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "researched"})
```

and in `stream_research` replace

```python
    # If already completed, return a single done event
    if row.status in ("completed", "failed", "cancelled"):
```

with

```python
    # A finished run returns a single done event
    if row.status in _STREAM_TERMINAL_STATUSES:
```

(d) In `publish_research` replace

```python
        paper_title = result.get("title", row.question)
        slug = _make_slug(paper_title)
        existing = session.execute(
            text("SELECT id FROM research_requests WHERE slug = :slug AND id != :id"),
            {"slug": slug, "id": request_id},
        ).fetchone()
        if existing:
            slug = f"{slug}-{request_id[:8]}"
```

with

```python
        paper_title = result.get("title", row.question)
        slug = pick_slug(session, paper_title, request_id)
```

delete the three lines after `session.commit()` inside the session block:

```python
        # Bing (ChatGPT search, Copilot) learns about the paper now, not at
        # the next crawl. Fail-soft: a rejected ping is logged, never raised.
        indexnow_submit([indexnow_url(f"/research/{slug}"), indexnow_url("/research/")])
```

and replace the block after the `with get_session() as session:` block, from `    # Index the assembled publication (not the raw report) so search results` to the line before `    return {"status": "published", "slug": slug}`, with:

```python
    # IndexNow + Qdrant: the same sequence the Claude publish CLI runs
    # (pipeline/lyra/theo_publishing.py). Indexes the assembled publication, not
    # the raw report, so search results don't return rejected content. Failures
    # are returned, logged here, and never undo the publish.
    effects = run_publish_side_effects(
        request_id=request_id,
        slug=slug,
        title=paper_title,
        paper_text=assembled["published_report"],
        author_username=user.username,
        author_discord_id=user.discord_id,
        published_at=datetime.now(UTC).isoformat(),
        reindex=False,
    )
    if not all(effect["ok"] for effect in effects.values()):
        logger.error("Publish side effects incomplete for %s: %s", request_id, effects)
```

(`indexnow_submit`/`indexnow_url` stay imported: `unpublish_research` still uses them.)

- [ ] **Step 4: Run the route tests and mypy**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_theo_routes_researched.py -m "not integration and not live_llm" -q --timeout 20`
Expected: `3 passed`.

Run: `./.venv/Scripts/python.exe -m mypy api/ 2>&1 | grep -E "theo(_worker|_config)?\.py"`
Expected: no output. (CI runs `mypy api/`; the local venv reports the same pre-existing errors in other files as a clean checkout, 93 in 14 files on 2026-09-26, none in the Theo files.)

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format api/routes/theo.py tests/api/test_theo_routes_researched.py
./.venv/Scripts/python.exe -m ruff check --fix api/routes/theo.py tests/api/test_theo_routes_researched.py
git add api/routes/theo.py tests/api/test_theo_routes_researched.py
git commit -m "Treat researched as a finished run in the owner stream and share the slug rule and publish side effects with the Claude publish CLI" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 22: Paper audio narrates the published text

**Files:**
- Modify: `pipeline/lyra/tts_generator.py` (`generate_paper_audio`, lines 253-260)
- Test: `tests/pipeline/test_tts_published_report.py`

- [ ] **Step 1: Write the failing test**

```python
"""Paper audio narrates what the page shows: published_report (memory project-theo-published-report-trap)."""

from pipeline.lyra.tts_generator import report_for_audio


def test_a_published_paper_narrates_the_published_text():
    assert report_for_audio({"report": "draft", "published_report": "published"}) == "published"


def test_an_unpublished_paper_narrates_its_report():
    assert report_for_audio({"report": "draft"}) == "draft"


def test_an_empty_published_text_is_not_swapped_for_the_draft():
    assert report_for_audio({"report": "draft", "published_report": ""}) == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_tts_published_report.py -m "not integration and not live_llm" -q`
Expected: collection error `ImportError: cannot import name 'report_for_audio'`.

- [ ] **Step 3: Implement**

In `pipeline/lyra/tts_generator.py` add before `generate_paper_audio`:

```python
def report_for_audio(result: dict) -> str:
    """The text a reader sees: published_report, which /research/{slug} renders.

    report is used only while published_report does not exist yet (an owner
    queued audio for an unpublished paper). Reading report for a published paper
    narrated the pre-publish draft (memory project-theo-published-report-trap).
    """
    if "published_report" in result:
        return result["published_report"]
    return result.get("report", "")
```

and in `generate_paper_audio` replace

```python
        report = result.get("report", "")
        if not report:
            raise ValueError(f"Paper {tts_req.paper_id} has no report text")
```

with

```python
        report = report_for_audio(result)
        if not report:
            raise ValueError(f"Paper {tts_req.paper_id} has no report text")
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_tts_published_report.py tests/pipeline/test_tts_ai_marking.py -m "not integration and not live_llm" -q`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
./.venv/Scripts/python.exe -m ruff format pipeline/lyra/tts_generator.py tests/pipeline/test_tts_published_report.py
./.venv/Scripts/python.exe -m ruff check --fix pipeline/lyra/tts_generator.py tests/pipeline/test_tts_published_report.py
git add pipeline/lyra/tts_generator.py tests/pipeline/test_tts_published_report.py
git commit -m "Narrate a paper's published text, not its pre-publish report, in the paper audio" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 23: The live panel ends at "Dossier ready"

**Files:**
- Modify: `ancient-nerds-map/src/components/theo/TheoResearchLive.tsx`
- Test: `ancient-nerds-map/src/components/theo/__tests__/theoResearchLive.test.ts`

- [ ] **Step 1: Write the failing test**

`ancient-nerds-map/src/components/theo/__tests__/theoResearchLive.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { THEO_PHASES, doneSublabel, phaseForStage } from '../TheoResearchLive'

describe('Theo live panel (research only)', () => {
  it('has no write or judge phase and ends at the dossier', () => {
    expect(THEO_PHASES).not.toContain('writing')
    expect(THEO_PHASES).not.toContain('judging')
    expect(THEO_PHASES[THEO_PHASES.length - 1]).toBe('dossier')
  })

  it('moves debate -> moderating -> dossier -> done', () => {
    expect(phaseForStage('debate', 'done')).toBe('moderating')
    expect(phaseForStage('moderator', 'start')).toBe('moderating')
    expect(phaseForStage('moderator', 'done')).toBe('dossier')
    expect(phaseForStage('dossier', 'start')).toBe('dossier')
    expect(phaseForStage('dossier', 'done')).toBe('done')
  })

  it('keeps the research phases before it', () => {
    expect(phaseForStage('decomposition', 'start')).toBe('decomposing')
    expect(phaseForStage('search_ab12', 'done')).toBe('exploring')
    expect(phaseForStage('synthesis', 'start')).toBe('synthesizing')
  })

  it('ignores the removed writing stages', () => {
    expect(phaseForStage('paper', 'done')).toBeNull()
    expect(phaseForStage('quality_judge', 'done')).toBeNull()
  })

  it('says Dossier ready when the run ends researched', () => {
    expect(doneSublabel('researched')).toBe('DOSSIER READY')
    expect(doneSublabel('failed')).toBe('RESEARCH FAILED')
    expect(doneSublabel('cancelled')).toBe('RESEARCH CANCELLED')
    expect(doneSublabel(null)).toBe('RESEARCH FINISHED')
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ancient-nerds-map && npx vitest run src/components/theo/__tests__/theoResearchLive.test.ts`
Expected: FAIL (`THEO_PHASES` / `phaseForStage` / `doneSublabel` are not exported).

- [ ] **Step 3: Implement in `TheoResearchLive.tsx`**

(a) Replace the `THEO_STAGE_WEIGHTS` block (comment and object) with:

```ts
// 'source_audit' removed 2026-08-05: no live SSE event ever carries that
// stage id (see the matching removal in types/pipeline.ts).
// Research-only since 2026-09-26: the run ends at the dossier and the paper
// is written in a Claude session, so 'paper_assembly', 'quality_judge' and
// 'image_generation' are gone with the M3 writing chain.
const THEO_STAGE_WEIGHTS: Record<string, number> = {
  question_analysis: 5,
  web_search: 25,
  specialist_analysis: 35,
  synthesis: 15,
  debate: 15,
  moderator: 5,
}
```

(b) Directly after `const THEO_STAGE_ORDER = Object.keys(THEO_STAGE_WEIGHTS)` add:

```ts
// ---------------------------------------------------------------------------
// Research phases — the strip across the top of the live view
// ---------------------------------------------------------------------------

export const THEO_PHASES = ['decomposing', 'exploring', 'cross_pollinating', 'synthesizing', 'debating', 'moderating', 'dossier'] as const
type TheoPhase = (typeof THEO_PHASES)[number]

const THEO_PHASE_LABELS: Record<TheoPhase, string> = {
  decomposing: 'DECOMPOSE',
  exploring: 'EXPLORE',
  cross_pollinating: 'CROSS-POLL',
  synthesizing: 'SYNTHESIZE',
  debating: 'DEBATE',
  moderating: 'MODERATE',
  dossier: 'DOSSIER',
}

const PHASE_ORDER: readonly string[] = ['connecting', ...THEO_PHASES, 'done']

/** The research phase a pipeline event moves the live view to, or null when it moves none. */
export function phaseForStage(stage: string, status: string): string | null {
  if (stage === 'decomposition') return status === 'done' ? 'exploring' : 'decomposing'
  if (stage.startsWith('search_') || stage.startsWith('specialist_')) return 'exploring'
  if (stage === 'cross_pollination') return status === 'done' ? 'exploring' : 'cross_pollinating'
  if (stage === 'synthesis') return status === 'done' ? 'debating' : 'synthesizing'
  if (stage === 'debate') return status === 'done' ? 'moderating' : 'debating'
  if (stage === 'moderator') return status === 'done' ? 'dossier' : 'moderating'
  if (stage === 'dossier') return status === 'done' ? 'done' : 'dossier'
  return null
}

/** Sub-label of the finished progress bar, from the terminal 'done' event's status. */
export function doneSublabel(status: string | null): string {
  if (status === 'researched') return 'DOSSIER READY'
  if (status === 'failed') return 'RESEARCH FAILED'
  if (status === 'cancelled') return 'RESEARCH CANCELLED'
  if (status === 'deferred') return 'RESEARCH DEFERRED'
  return 'RESEARCH FINISHED'
}
```

(c) Replace the state line `const [qualityFlash, setQualityFlash] = useState<{ score: number; badge: string } | null>(null)` with:

```ts
  const [doneStatus, setDoneStatus] = useState<string | null>(null)
```

(d) In the `'pipeline'` case delete the block

```ts
          if (data.stage === 'quality_judge' && data.status === 'done' && typeof meta.score === 'number') {
            setQualityFlash({ score: meta.score as number, badge: (meta.badge as string) || '' })
            setTimeout(() => setQualityFlash(null), 8000)
          }
```

(e) Replace the seven `// Track research phase from pipeline stage names` lines (from `if (stage === 'decomposition') setResearchPhase(` to `else if (stage === 'quality_judge') setResearchPhase(...)`) with:

```ts
        // Track research phase from pipeline stage names
        const nextPhase = phaseForStage(stage, data.status as string)
        if (nextPhase) setResearchPhase(nextPhase)
```

(f) In the phase-detail block replace the `phaseKey` expression and the `detail` chain with:

```ts
          const phaseKey =
            stage === 'decomposition' ? 'decomposing'
            : stage === 'cross_pollination' ? 'cross_pollinating'
            : stage === 'synthesis' ? 'synthesizing'
            : stage === 'debate' ? 'debating'
            : stage === 'moderator' ? 'moderating'
            : stage === 'dossier' ? 'dossier'
            : stage.startsWith('search_') || stage.startsWith('specialist_') ? 'exploring'
            : null
          if (phaseKey) {
            let detail = ''
            if (stage === 'decomposition' && meta.angles) detail = `${meta.angles} angles created`
            else if (stage.startsWith('specialist_') && meta.angle) detail = `${meta.angle}: ${meta.new_claims || 0} new claims (round ${meta.round || '?'})`
            else if (stage === 'cross_pollination' && meta.enriched_angles) detail = `Enriched ${meta.enriched_angles} angles, ${meta.convergent_patterns || 0} convergent patterns`
            else if (stage === 'synthesis' && meta.consensus != null) detail = `${meta.consensus} consensus, ${meta.contested || 0} contested, ${meta.unique || 0} unique`
            else if (stage === 'debate' && meta.rounds) detail = `${meta.rounds} rounds, ${meta.challenges || 0} challenges, ${meta.defenses || 0} defenses`
            else if (stage === 'moderator' && meta.final_claims != null) detail = `${meta.final_claims} final, ${meta.revised_claims || 0} revised, ${meta.speculative_claims || 0} speculative claims`
            else if (stage === 'dossier' && meta.cited_sources != null) detail = `${meta.full_text || 0} of ${meta.cited_sources} cited sources archived in full`
            if (detail) {
              setPhaseDetails(prev => ({ ...prev, [phaseKey]: [...(prev[phaseKey] || []), detail] }))
            }
          }
```

(g) In the `'done'` case add `setDoneStatus(typeof data.status === 'string' ? data.status : null)` before `setDone(true)`.

(h) Replace the phase strip map

```tsx
            {(['decomposing', 'exploring', 'cross_pollinating', 'synthesizing', 'debating', 'writing', 'judging'] as const).map(phase => {
              const labels: Record<string, string> = { decomposing: 'DECOMPOSE', exploring: 'EXPLORE', cross_pollinating: 'CROSS-POLL', synthesizing: 'SYNTHESIZE', debating: 'DEBATE', writing: 'WRITE', judging: 'JUDGE' }
              const phaseOrder = ['connecting', 'decomposing', 'exploring', 'cross_pollinating', 'synthesizing', 'debating', 'writing', 'judging', 'done']
              const currentIdx = phaseOrder.indexOf(researchPhase)
              const thisIdx = phaseOrder.indexOf(phase)
```

with

```tsx
            {THEO_PHASES.map(phase => {
              const currentIdx = PHASE_ORDER.indexOf(researchPhase)
              const thisIdx = PHASE_ORDER.indexOf(phase)
```

and `{labels[phase]}` inside the button with `{THEO_PHASE_LABELS[phase]}`.

(i) In the finished progress bar replace `sublabel="RESEARCH FINISHED"` with `sublabel={doneSublabel(doneStatus)}`.

(j) Delete the block

```tsx
        {qualityFlash && (
          <div className="theo-quality-flash">
            Quality: {qualityFlash.score}/100 — {qualityFlash.badge}
          </div>
        )}
```

- [ ] **Step 4: Run the test and the type check**

Run: `cd ancient-nerds-map && npx vitest run src/components/theo/__tests__/theoResearchLive.test.ts && npm run type-check`
Expected: `5 passed`; type-check clean (noUnusedLocals catches a leftover `qualityFlash`).

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/src/components/theo/TheoResearchLive.tsx ancient-nerds-map/src/components/theo/__tests__/theoResearchLive.test.ts
git commit -m "End Theo's live panel at the moderated dossier instead of the removed write and judge phases" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 24: The owner list shows "Researched · awaiting write"

**Files:**
- Modify: `ancient-nerds-map/src/pages/TheoPage.tsx` (new helper after the imports; notifications ~338-346; badge ~1348-1352)
- Test: `ancient-nerds-map/src/pages/__tests__/theoStatusLabel.test.ts`

- [ ] **Step 1: Write the failing test**

`ancient-nerds-map/src/pages/__tests__/theoStatusLabel.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { researchStatusLabel } from '../TheoPage'

describe('researchStatusLabel', () => {
  it('names a finished research run that waits for the Claude write', () => {
    expect(researchStatusLabel('researched')).toBe('Researched · awaiting write')
  })

  it('keeps the existing labels', () => {
    expect(researchStatusLabel('completed')).toBe('Done')
    expect(researchStatusLabel('failed')).toBe('Failed')
    expect(researchStatusLabel('cancelled')).toBe('Cancelled')
  })

  it('shows any other status verbatim', () => {
    expect(researchStatusLabel('deferred')).toBe('deferred')
  })
})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ancient-nerds-map && npx vitest run src/pages/__tests__/theoStatusLabel.test.ts`
Expected: FAIL (`researchStatusLabel` is not exported).

- [ ] **Step 3: Implement in `TheoPage.tsx`**

(a) After the two `lazy(...)` lines add:

```ts
/** Owner-list badge text for a research row. 'researched' is a finished Theo run
 *  whose dossier waits for the Claude write (spec 2.5). */
export function researchStatusLabel(status: string): string {
  switch (status) {
    case 'completed': return 'Done'
    case 'failed': return 'Failed'
    case 'cancelled': return 'Cancelled'
    case 'researched': return 'Researched · awaiting write'
    default: return status
  }
}
```

(b) Replace the notification loop

```tsx
        for (const item of data) {
          const prev = prevStatusRef.current.get(item.id)
          if (prev && prev !== 'completed' && item.status === 'completed') {
            new Notification('Theo finished his research', {
              body: item.question.substring(0, 100),
            })
          }
        }
```

with

```tsx
        for (const item of data) {
          const prev = prevStatusRef.current.get(item.id)
          if (!prev || prev === item.status) continue
          if (item.status === 'researched') {
            new Notification('Theo finished his research', {
              body: `Dossier ready, the paper is written next: ${item.question.substring(0, 80)}`,
            })
          } else if (item.status === 'completed') {
            new Notification('Theo paper published', {
              body: item.question.substring(0, 100),
            })
          }
        }
```

(c) Replace the badge content

```tsx
                    <span className={`theo-badge theo-badge-status theo-badge-${item.status}`}>
                      {item.status === 'completed' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><polyline points="20 6 9 17 4 12"/></svg>Done</> :
                       item.status === 'failed' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>Failed</> :
                       item.status === 'cancelled' ? <><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><line x1="5" y1="12" x2="19" y2="12"/></svg>Cancelled</> : item.status}
                    </span>
```

with

```tsx
                    <span className={`theo-badge theo-badge-status theo-badge-${item.status}`}>
                      {item.status === 'completed' && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><polyline points="20 6 9 17 4 12"/></svg>}
                      {item.status === 'failed' && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>}
                      {item.status === 'cancelled' && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0}}><line x1="5" y1="12" x2="19" y2="12"/></svg>}
                      {researchStatusLabel(item.status)}
                    </span>
```

The Delete button keeps its `completed || failed || cancelled` condition: a researched row carries an unwritten dossier and is not offered for deletion in the UI (the API still archives-then-deletes it, spec 2.5).

- [ ] **Step 4: Run the test, the type check and the full frontend suite**

Run: `cd ancient-nerds-map && npx vitest run src/pages/__tests__/theoStatusLabel.test.ts && npm run type-check && npm run test`
Expected: `3 passed`; type-check clean; the whole vitest suite green.

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/src/pages/TheoPage.tsx ancient-nerds-map/src/pages/__tests__/theoStatusLabel.test.ts
git commit -m "Show researched Theo runs as awaiting the write and notify when a dossier is ready or a paper is published" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Task 25: Full verification

No new code. Every gate the pre-push hook and CI run over this stream's files.

- [ ] **Step 1: Backend suite**

Run: `./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"`
Expected: all pass; the only skips are the pre-existing ones (remediation caches absent in a worktree). Compare the pass count with the baseline noted before Task 2 (run the same command on a clean checkout first if no baseline was taken): the difference is the new tests minus the deleted paper tests (`test_paper_claim_pack.py` 5, `test_paper_repair_pass.py` 5, `test_paper_title_validation.py` 9, `test_empty_paper_guard.py` 5, removed LLM-call tests 11, `test_handler_uses_same_regex` 1). Locally `tests/api/lyra/test_backends.py` has 3 failures on a clean checkout too (missing Anthropic key; CI sets dummy keys): run with `LYRA_ANTHROPIC_API_KEY=ci-dummy ANTHROPIC_API_KEY=ci-dummy` to match CI.

- [ ] **Step 2: Static gates**

```bash
./.venv/Scripts/python.exe -m ruff check api/ pipeline/
./.venv/Scripts/python.exe -m ruff format --check api/ pipeline/
./.venv/Scripts/lint-imports.exe
./.venv/Scripts/python.exe -m vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80
./.venv/Scripts/python.exe -m mypy api/
./.venv/Scripts/semgrep.exe scan --config .semgrep api/ pipeline/ ancient-nerds-map/src/
./.venv/Scripts/pip-audit.exe -r requirements-api.txt --ignore-vuln CVE-2026-25990
```

Expected: ruff clean, format clean, `Contracts: 2 kept, 0 broken.`, vulture prints nothing, mypy reports no more errors than a clean checkout of `origin/main` (93 in 14 files locally on 2026-09-26, none in a Theo file), semgrep 0 findings, pip-audit "No known vulnerabilities found".

- [ ] **Step 3: The Lyra image still imports**

Run: `./.venv/Scripts/python.exe -c "import sys; sys.modules['markdown']=None; sys.modules['nh3']=None; import pipeline.lyra.orchestrator"`
Expected: exit 0, no output.

Also check the new modules import without the api package's heavy services at module level:
`./.venv/Scripts/python.exe -c "import sys; sys.modules['markdown']=None; sys.modules['nh3']=None; import pipeline.lyra.theo_publishing, pipeline.lyra.archive_completion, pipeline.lyra.handlers.dossier, pipeline.lyra.theo_dossier, pipeline.lyra.theo_publish"`
Expected: exit 0.

- [ ] **Step 4: Frontend gates**

```bash
cd ancient-nerds-map && npm run type-check && npm run test && npx knip --no-progress --include files,dependencies,devDependencies
```

Expected: all green.

- [ ] **Step 5: CLI smoke tests (no database needed)**

```bash
./.venv/Scripts/python.exe -m pipeline.lyra.theo_publish --help
./.venv/Scripts/python.exe -m pipeline.lyra.theo_dossier --help
echo '{"version": 2}' | ./.venv/Scripts/python.exe -m pipeline.lyra.theo_publish --dry-run; echo "exit=$?"
```

Expected: both help texts; the last prints `{"ok": false, "error": "missing keys: [...]"}` and `exit=2`.

- [ ] **Step 6: Record the result**

No commit (nothing changed). Report the pass counts and any gate that could not run on this machine instead of claiming it passed (CLAUDE.md "Local verification").

---

## Cross-stream requests (changes outside this stream's files)

1. **`requirements.txt`** (local dev list, owner of that file): add `pypdf==6.19.0` so a fresh venv runs the three PDF tests instead of skipping them.
2. **`ancient-nerds-map/src/types/pipeline.ts`** (optional, cosmetic): add `{ id: 'dossier', label: 'Dossier', sublabel: 'Archive completion + manifest' }` to `PIPELINE_STAGES` so the live trace shows a Dossier LED; `paper_assembly`, `quality_judge`, `image_generation`, `presentation`, `fact_check` are dead stage ids since this stream. The phase strip works without it (it reads raw stage names).
3. **Stream B (paper page):** import `normalize_anchor_text` from `pipeline.lyra.theo_publishing` and apply contract C9 to the text of each `<p>`; render `result_json.evidence` / `corrections` / `videos` per contract C7. Note that `GET /api/theo/public/{slug}` returns the full `result_json`, which now includes the `dossier` summary, `writer`, `evidence`, `corrections` and `videos` (no source texts).
4. **Stream C (paper studio):** copy `docs/superpowers/plans/assets/writer-brief-editorial.md` into `pipeline/studio/paper/brief_template.md`; build bundles per contracts C3–C6; read `PublishOutcome` per C8. `report_paragraphs` and `resolve_evidence_anchors` are importable for the local gate 3.4.6. The M3 hook carries no heading of its own in all 31 published papers (the asset says so); align the "six required h2 sections" gate with that.
5. **`scripts/`** (owner of scripts): `entitaet_research_host.py`, `smoke_theo_host.py`, `theo_ab_compare.py`, `theo_test_run.py` read `ctx.paper_text`, `ctx.paper_title`, `ctx.quality_score`; after the split these are always empty. Point them at `ctx.dossier_summary`, then the dead paper fields on `ResearchState` can be removed. `scripts/swap_theo_worker_when_idle.sh` explains its 300 s settle with `_auto_publish`, which no longer exists.
6. **Docs (CLAUDE.md / docs/procedures, stream D):** the Theo section: research-only, status `researched`, `theo_dossier` and `theo_publish` CLIs and their exit codes, `THEO_RUN_COST_PCT` / `THEO_RUN_EST_HOURS` / `THEO_MAX_UNWRITTEN_DOSSIERS` / `THEO_ARCHIVE_COMPLETION_*`. `docs/TRAINING_DATA_POLICY.md` states that nothing reads the corpus back for control flow; the dossier export and archive completion now do.
7. **Migration numbering:** this stream owns `0025_theo_paper_publications.sql`; `0026_studio_episodes.sql` belongs to the studio stream.

---

## Planning verification (2026-09-26)

Every code block of this plan was applied to a scratch copy of the worktree (`C:/tmp/scratchA`, script-driven, no hand edits) and run:
- all 226 tests in the files Tasks 2-22 create or touch passed on the first run, and the 8 frontend tests of Tasks 23-24 passed with `tsc --noEmit` clean;
- `tests/pipeline` + `tests/api`: 2288 passed; the only failures were environment ones (no git repository in the scratch copy, the pre-existing `test_backends.py` key failures) and `test_hex_token_scrubber.py::test_handler_uses_same_regex`, which Task 10 now removes;
- vulture clean, `lint-imports` 2 contracts kept, the Lyra import check passes, mypy shows no error in a Theo file;
- `ruff format` reformats a few long lines of the new modules and `ruff check --fix` settles two import-block blank lines: run both as each task says.

Task 9 alone (before Task 10) was checked separately: its 7 tests plus the still-present `test_empty_paper_guard.py` pass.
