# CLAUDE.md

This file provides guidance for the coding agents that work in this repository (MiniMax Code;
the tools are named as MiniMax Code spells them, `todowrite`, `read`, `edit`, `bash`, `grep`).

## Where the 2026-09 sites remediation stands

All 5,004 `ancient_nerds` sites have been examined. In production (2026-09-25, every write journalled,
0 deviations): Phase 3's 994 field writes, of which 499 stand (Opus re-judged the 934 DeepSeek decided:
481 kept, 453 reverted by `journal-reversal-3`); further lanes (wrong-both, coordinates, ids, images,
scope-e4: 78 sites retired); and Phase 4's **984 defect sites with a new Wikipedia-based description**.
Every model judgement runs through agents via `scripts/remediation/opus_handoff.py`: no DeepSeek,
Pi or opencode (owner, 2026-09-23). Since 2026-10-03 the owner replaces Claude Code with MiniMax Code
(`mcode`, model `MiniMax-M3.1-Flash-Preview`); MiniMax answers enter production only after the answer
stamp and the public AI disclosure name MiniMax truthfully (`ANSWER_MODELS`, `model4.AI_SYSTEM`) and a
calibration against already-answered batches has passed. Start with `output/remediation/HANDOVER.md` (state,
next steps in order, traps); evidence `AUDIT_LOG.md`, owner items `HUMAN_ONLY.md`. Open: lane L
(running), the `wip/p4-pilot` merge, Phase 6 incl. Push #2 and the final acceptance.

## Code Quality Standards

### NO FALLBACK CODE
**Do NOT add fallback logic, defensive coding, or "graceful degradation" when fixing bugs.**

When something doesn't work:
1. Find the ACTUAL root cause
2. Fix it properly or mark the connector as `available = False` with a clear reason
3. If an API is dead/changed/protected - say so directly, don't wrap it in try/catch that returns empty

Bad:
```python
# Try multiple endpoints and fallback
for endpoint in ["/api/v1", "/api/v2", "/old-api"]:
    try:
        response = await self.rest.get(endpoint)
        if response:
            return self._parse_response(response)
    except:
        continue
return []  # Silent failure
```

Good:
```python
# This endpoint works - verified on 2024-01-15
response = await self.rest.get("/api/v2/search")
return self._parse_response(response)
```

Or if it doesn't work:
```python
available = False
unavailable_reason = "API deprecated in 2021, no replacement available"
```

### Testing APIs
Before implementing a connector, actually test the API with curl to verify:
- The endpoint exists
- The response format matches what we expect
- There's no bot protection blocking requests

### Connector Status
If a connector cannot work due to:
- Bot protection (Cloudflare, Anubis)
- Deprecated/shutdown API
- Requires authentication we don't have

Mark it as `available = False` with `unavailable_reason` explaining why. Don't write fake code that silently returns empty results.

### Code Audits
When asked to audit code, read `docs/procedures/CODE_AUDIT.md` and follow its Execution Procedure step by step. The procedure includes finding issues, fixing them, and re-auditing until the quality gate passes. Do not stop after the initial report — fix everything fixable, then run a confirming audit.

### Database Audits
When asked to audit the database, read `docs/procedures/ENRICHMENT_AUDIT.md` and follow its Execution Procedure step by step. Use per-site judgment and web research — never batch-apply corrections without reviewing each site individually.

### Project lessons
`docs/procedures/PROJECT_LESSONS.md` collects the hard-won pitfalls of this project (deploy
verification, the two `pipeline/` images, database keys and protected tables, PWA/SSR traps, content
scope, working-tree rules). Read it before touching deploy, DB or frontend plumbing. Entries carry
their source and date; a "no longer valid" section names what the 2026-09-20 decisions superseded.

## Architecture

### Stack
- **Frontend**: React 18 + Three.js/Mapbox in `ancient-nerds-map/` (Vite + TypeScript). A
  multi-page app without a client router: every area is one `*.html` entry plus its own
  `src/*Main.tsx`, registered in `vite.config.ts` under `build.rollupOptions.input`.
- **API**: FastAPI in `api/` (`api/main.py` mounts every router), built from `Dockerfile` and run
  twice — `ancient_nerds_api` on 8000, `ancient_nerds_api2` on 8001 — so the deploy restarts one
  at a time behind nginx.
- **SSR sidecar** (`ancient_nerds_ssr`, `Dockerfile.ssr`, port 8500): renders the indexed pages —
  `/sites/…`, `/articles/…` (journals), `/news-archive/…` (stories), `/research/…`, landing. Path:
  the `api/routes/*_html.py` routers → `api/seo_shell.py` → `api/ssr_client.py` POSTs a route
  payload → `ancient-nerds-map/ssr/server.mjs` → `src/entry-server.tsx` → `src/seo/registry.tsx`.
  No fallback renderer: a failing sidecar turns into a 502. The same components hydrate in the
  browser, so browser storage in a render path breaks every SSR page (guard:
  `src/seo/__tests__/render.test.tsx`).
- **Lyra** (`ancient_nerds_lyra`, `Dockerfile.lyra`, `python -m pipeline.lyra.orchestrator`): the
  hourly news/story cycle. **Theo** researches in `ancient_nerds_theo_worker` (API image,
  `scripts/run_theo_worker.py`); see "Theo" below. The LLM backend is `LYRA_LLM_BACKEND`
  (`anthropic` | `minimax`, `pipeline/lyra/config.py`); MiniMax is called through the Anthropic
  SDK against its Anthropic-compatible endpoint (`minimax_shared.py`, pacing in
  `minimax_limiter.py`).
- **Database**: PostgreSQL + PostGIS in `ancient_nerds_db`, with Redis (cache, rate limits) and
  Qdrant (vector search) beside it. SQLAlchemy models live in `pipeline/database.py`, shared by
  `api/` and `pipeline/`.
- **Static data**: Pre-exported JSON in `public/data/` (sites, sources, content, links)
- **Pipeline**: Data connectors and exporters in `pipeline/`
- **Studio** (the owner's workstation only): `pipeline/studio/` and the Remotion renderer
  `video/`; see "Studio" below.

### Cross-cutting rules that span several files
- **`pipeline/` ships in two images.** The API image has `api/` too; the Lyra image copies only
  `pipeline/` and lacks `markdown` and `nh3`. Before pushing a change to anything Lyra imports:
  `./.venv/Scripts/python.exe -c "import sys; sys.modules['markdown']=None; sys.modules['nh3']=None; import pipeline.lyra.orchestrator"`.
  Gate optional `api` imports with `importlib.util.find_spec("api")` (top-level package only).
- **Layer contracts** (`[tool.importlinter]` in `pyproject.toml`, gate `lint-imports`): `pipeline`
  must not import `api` beyond the frozen exceptions; `api` may import only the listed `pipeline`
  families. A new crossing fails CI. Code both images need belongs under `pipeline/`.
- **Schema changes have two paths.** Numbered `migrations/NNNN_*.sql` are applied once by the
  deploy and tracked by filename in the `applied_migrations` table — editing an applied file never
  runs again, add a new one. Lyra's boot migrations (`_run_migrations` in
  `pipeline/lyra/orchestrator.py`) run as one transaction: one failure rolls back all of them on
  every boot. `create_all_tables()` creates tables but never adds columns.
- **Generated frontend data**: `ancient-nerds-map/src/data/*.generated.json` come from Python
  constants (`pipeline/historical_boundaries/empire_metadata.py`, `api/cardgame/constants.py`).
  Edit the Python, then run `./.venv/Scripts/python.exe pipeline/generate_shared_data.py`; CI
  fails on stale output (`--verify`). One exception: `globeLayers.generated.json` and the
  coastline/border tiers in `public/data/layers/globe/` are built by
  `scripts/build_globe_layers.py` (never by hand) and checked by
  `tests/scripts/test_build_globe_layers.py`, not by `generate_shared_data.py --verify`.

### Key data flow
1. Connectors in `pipeline/connectors/` fetch from external APIs → write to `unified_sites` table
2. `pipeline/static_exporter.py` exports DB → static JSON files in `public/data/`
3. Frontend reads static JSON; API serves as fallback and for dynamic queries
4. The frontend reads the repo-root `public/data/` only: the Vite dev server proxies `/data` there (`ancient-nerds-map/vite.config.ts`), production nginx serves it as an alias. `ancient-nerds-map/public/data/` must **not** exist (`.gitignore`); the deploy removes it with `git clean`.

### Source visibility: `enabled` vs `enabled_by_default`
The `source_meta` table has two boolean columns:
- **`enabled`**: whether the source is active in the system (always true for working connectors)
- **`enabled_by_default`**: whether dots show on the globe on first load (only `ancient_nerds` is true)

The static exporter writes `"on"` in `sources.json` from `enabled_by_default`. The frontend uses this to decide which sources render immediately vs require user opt-in in the Filter panel.

## Theo: research on the VPS, the paper in a local session

Theo researches only (design: `docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md`).
MiniMax M3 runs the convergence pipeline up to the moderator. The `DossierHandler`
(`pipeline/lyra/handlers/dossier.py`) then persists the dossier as `research_artifacts` rows, runs
archive completion (`pipeline/lyra/archive_completion.py`: the full text of every source a moderated
claim cites, Wikipedia, doi.org landing pages, PDFs and `news_videos` transcripts included; a
TDM-reserved source is recorded without its body) and writes the `dossier` manifest last, so its
presence means the dossier is complete. The worker ends the row as `status = 'researched'` with
`result_json = {"dossier": <summary>, "title": null}`. There is no M3 paper and no auto-publish;
every public reader filters `is_public AND status = 'completed'`, so a `researched` row stays
invisible. `THEO_WORKER_DISABLED=1` in the VPS `.env` idles the worker container (set on the owner's
behalf by another session on 2026-09-26, about 18:20 UTC; owner question Q1 keeps it off).

A local session writes, checks and publishes the paper ("Studio" below) through two CLIs in
the API image, run over ssh so production credentials stay on the VPS:

```bash
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier list
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_dossier export <id> [--texts all] > dossier.json.gz
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --dry-run < bundle.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --apply < bundle.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --correct [--dry-run] < correction.json
ssh ancientnerds docker exec -i ancient_nerds_api python -m pipeline.lyra.theo_publish --register-video [--dry-run] < video.json
```

- **`theo_dossier`** exits 0 ok, 1 no or incomplete dossier, 2 bad request id. `list` prints one
  JSON array, oldest first; `export` carries the texts of the sources the moderated claims cite
  (`--texts cited`, the default) or of every source (`--texts all`); a run without a `dossier`
  manifest exports from its per-stage artifacts with `"legacy": true`.
- **`theo_publish`** prints one `PublishOutcome` JSON (`{"ok": false, "error": …}` on errors) and
  exits 0 ok (side-effect failures are reported, not fatal), 1 a gate failed, 2 unusable input,
  3 the row changed between read and write (nothing committed), 4 committed but the re-read row
  differs (side effects not run). `request_id` is the canonical lowercase UUID. A publish dry run on
  a public paper answers `apply_allowed: false`: a public paper changes only through `--correct`.
- **Correction kinds** (`--correct`; each re-runs the gates and keeps every published evidence id
  that no `corrections_append` entry names): a log entry only (`corrections_append`); a text
  correction (`report`, optionally `evidence`); a full rewrite of a stored text by the session's
  model (`report` with `rewrite: true`, which excludes `evidence` and `result`: the writer is
  stored, the page shows the AI disclosure line, the owner is notified), where a small fix goes
  without `rewrite`; a full
  republish (`result`, the complete publish result, which excludes `report` and `evidence`), which
  keeps slug, `published_at` and `published_by`, optionally with `dossier_request_id`: the fresh
  `researched` run it was written from, closed as `cancelled` in the same transaction.
- **Journal** `theo_paper_publications` (migration 0025): one row per committed write, in the
  write's transaction, none for a dry run. `bundle_sha256` is the sha256 of the exact stdin bytes:
  after a timeout or exit 4, a row of the paper with the hash you sent means the write committed
  (never run it again; `side_effects` NULL: IndexNow, Qdrant and the notice did not run), no such
  row means nothing committed.
- **Journalled papers** (`result_json` carries `evidence`, `videos`, `corrections` or `writer`;
  `theo_publishing.JOURNALLED_PAPER_SQL`) change only through `theo_publish`. The `result_json`
  maintenance tools in `pipeline/lyra/` and `scripts/` skip them and refuse one named by slug or
  id, and `POST /api/theo/research/{id}/approve` answers 409 for a public row. A new writer of
  `result_json` must do the same.
- **Owner notices** are `thinking_log` `run_event`s: `dossier_ready` (batch runs) and
  `paper_published` (a publish, a full republish, a `rewrite` correction). Discord only while
  `DISCORD_WEBHOOK_URL` is set; the owner keeps it unset.
- **Config** (VPS env): `THEO_RUN_COST_PCT` (9, the weekly-budget share of one research-only batch
  run), `THEO_RUN_EST_HOURS` (11; the batch gate uses the average of the last five research-only
  batch runs once one exists), `THEO_MAX_UNWRITTEN_DOSSIERS` (6, the feeder enqueues nothing while
  that many `researched` rows wait), all in `api/services/theo_config.py`;
  `THEO_ARCHIVE_COMPLETION_MAX_S` (1800 s, at most 2400 to stay below the worker's 2700 s stall
  guard) and `THEO_ARCHIVE_COMPLETION_CONCURRENCY` (4) in `archive_completion.py`.
- **Retired:** the M3 writing chain (handlers `paper`, `fact_check`, `presentation`,
  `image_generation`, `judge` and their prompts) and the four host scripts
  `scripts/entitaet_research_host.py`, `smoke_theo_host.py`, `theo_ab_compare.py` and
  `theo_test_run.py` (owner decision 22): they ran the orchestrator without a `research_requests`
  row, which the DossierHandler refuses.

## Studio: papers and YouTube episodes, on the workstation

`pipeline/studio/` and `video/` run only on the owner's workstation, inside a MiniMax Code session.
No studio code calls an LLM by itself: the model makes every judgement (writing, claim check,
image check, case file, script) and hands it over as files - in the session, or through one
`mcode exec` per task inside `python -m pipeline.studio mcode …` (`pipeline/studio/mcode.py`:
model `MiniMax-M3.1-Flash-Preview`, effort max, two runs at a time and more while no 429, a
10 % weekly-plan stop, and a `git status` guard that voids a batch whose runs wrote into the
checkout). The code validates, compiles and transports. The one paid call inside the code is
the narration: `episode voice` sends each beat's text to MiniMax's speech model after a
quota check. Nothing in `api/` or `pipeline/lyra` imports the package; only
`pipeline.studio.ledger_cli` runs in the API container.

```
./.venv/Scripts/python.exe -m pipeline.studio paper   {list,pull,number,check,claims-export,claims-import,images-export,images-import,bundle,publish,correct,register-video}
./.venv/Scripts/python.exe -m pipeline.studio episode {init,markers-export,markers-import,check,review,voice,capture,timeline,render,thumbnail,package,register-youtube}
./.venv/Scripts/python.exe -m pipeline.studio mcode   {claim-check,image-check,marker-check,casefile-verify,validate,probe}
./.venv/Scripts/python.exe -m pipeline.studio doctor [--fix-gpu]
```

A `StudioError` prints `error: <message>` and exits 2; `paper check`, `episode check`, `episode
voice` and `doctor` exit 1 when a gate or probe fails. A `mcode` check exits 0 when every pending
task was answered, 1 when at least one was not (each is named in `not_answered[]`) and 3 on the
weekly-plan stop.

- **Workspaces** live under `STUDIO_ASSETS`, default `<main checkout>/video-assets/studio`
  (gitignored; found through git's common dir, so a worktree writes into the main checkout's tree;
  the env var overrides it): `papers/<request_id>/` and `episodes/<slug>/`. The CLI loads the main
  checkout's `.env` (the MiniMax key for the voice, `VITE_MAPBOX_ACCESS_TOKEN` for the captures).
- **Skills** are tracked under `.claude/skills/` (the rest of `.claude/` stays local). The owner
  starts the weekly paper session by hand with `/theo-write`; episodes follow `studio-video` and
  `studio-casefile`. The four checks run through the Python driver
  `python -m pipeline.studio mcode {claim-check,image-check,marker-check,casefile-verify}`,
  one `mcode exec` per task on `MiniMax-M3.1-Flash-Preview` (see `pipeline/studio/mcode.py`).
- **Paper**: `paper pull` → this session writes `draft.md`, `paper_meta.json`, `evidence.json` →
  `number` → `claims-export`, `mcode claim-check`, `claims-import` → the same for images → `check`
  → `bundle` → `publish` (images uploaded by verified scp, dry run, apply once every gate passes;
  `publish --dry-run` uploads the images too).
  A public paper changes through `paper correct ID --text …|--entries FILE`: a log entry alone, or
  with `--with-report`, `--republish`, or `--report-file FILE [--rewrite]` (the full markdown of a
  legacy paper without a studio check, starting from the `content` of `GET /api/v1/research/{slug}`;
  `--rewrite` marks a full rewrite by this session's model). A legacy rewrite from a fresh Theo run
  is `paper pull ID --dossier-from RUN`, then `paper correct ID --republish`, never `paper publish`.
  Exit 3 committed nothing (re-run after `paper check`); exit 4, a timeout or no JSON answer is a
  `RemoteOutcomeUnknown`: follow the adoption procedure it prints and never re-run the write.
- **Episode**: `episode init` → case file (verified by `mcode casefile-verify`) → `markers-export`,
  `mcode marker-check`, `markers-import` → script → `check` → `review` → `voice` → `capture` →
  `timeline` → `render` (layout lint, Remotion, −14 LUFS, audit, ledger row) → `package` (MP4, SRT,
  description, three thumbnail candidates). The final package is the owner's only release gate. The
  upload is manual; then `episode register-youtube SLUG --youtube-id ID --title T --published-at TS
  --poster K` records it in the ledger and attaches the video to its paper, with thumbnail K as the
  page's poster (`paper register-video` is that paper step on its own, for a failed apply).
  `episode check` refuses a script whose `display` differs from its `spoken` text beyond number
  spelling (`spoken.py` accepts a digit with a magnitude word, duration compounds, decades, regnal
  and Roman numerals, ranges, dates, mm and degrees) and, once the voice and the takes exist, a clip
  scene (GlobeShot, MapboxFlyover) that plans one still picture for more than the render audit's 4 s
  (owner Q16; a GlobeShot pin lighting up does not count as a change of picture).
- **Renderer** `video/`: Remotion 4.0.529, every `@remotion/*` pinned to exactly that version (every
  dependency of `video/package.json` is pinned). Once per machine: `cd video && npm ci && npx remotion
  browser ensure`, then `./.venv/Scripts/python.exe -m playwright install chrome` (Playwright is in no
  requirements file: `pip install playwright` into the venv first when `doctor` names it missing),
  then `doctor --fix-gpu`. CI gates `video/` with `lint-video` (tsc, vitest) and, in `security-scan`,
  a blocking `npm audit --audit-level=critical`: vitest went from 4.0.18 to 4.1.11 on 2026-09-30 to
  clear GHSA-5xrq-8626-4rwp and GHSA-82fw-gwwq-j7x9, and a critical advisory in the lockfile fails
  the deploy (bump the package, never ignore the advisory).
  `npm run studio` previews the demo timeline (`--public-dir ../ancient-nerds-map/public`).
  `episode render` runs `video/scripts/{lint,render,still}.ts` as `node --import tsx
  scripts/<name>.ts`; they bundle into the episode's transient `render/bundle/`.
  `video/src/blocks/registry.json` is generated (`npm run registry`) and read by
  `pipeline/studio/blocks.py`; `tests/pipeline/studio/test_registry_contract.py` checks the
  studio's mirrors of the renderer.
- **GPU rule** (spec 4.11, binding): every GPU workload runs on the NVIDIA RTX 3080 (CUDA and NVENC
  index 0, Task Manager "GPU 1"), never on the integrated AMD or in software; a run that would land
  there fails. The proofs: every lint/render/still browser prints `gpu: <WebGL renderer>`, and
  `episode render` refuses one that does not name the NVIDIA and stores it in the ledger; every
  browser capture's manifest records it as a `gpu` event (a `mapbox_topdown` still is an API
  picture without a browser, so it has none); a page of the proved render browser that is closed
  from outside or crashes cancels the run at once (owner Q17); encodes use `h264_nvenc`/`hevc_nvenc`
  with `-gpu 0`; word timings run faster-whisper on CUDA 0 (float16). `doctor` probes nvidia-smi,
  NVENC, CUDA, the Remotion browser's per-app GPU preference and a capture Chrome's renderer;
  `doctor --fix-gpu` sets that preference (`HKCU\Software\Microsoft\DirectX\UserGpuPreferences`),
  once per machine.
- **Captures** are HEVC (`hevc_nvenc`), because `h264_nvenc` clips stall Remotion's decoder. The
  globe, Mapbox and platform takes drive a headed Chrome, which draws only on an awake, unlocked
  display: a take keeps the display on but cannot wake it (a sleeping display once hung a Mapbox
  fly-in for 15 minutes).
- **Glyph rule** (owner decision 32): every string the video draws must lie in the brand fonts'
  glyphs, `DRAWABLE` in `video/src/theme/glyphs.ts` (generated from the font files' cmaps;
  `pipeline/studio/glyphs.py` holds a copy the contract test compares). Only drawn strings are
  checked: the registry's `drawn` props, capture credits and `place`/`pin` labels, hook captions,
  chapter titles, thumbnail teasers. Each character is checked in upper case too (`ƒ` draws as `Ƒ`
  and is refused); `µ` is refused, write `micrometre`. A quote inside a captured page and a page's
  own title (never drawn: SourceViewer shows only the ASCII hostname) may hold any character.
- **Site export**: distribution dots (`site_ids` of curated `ancient_nerds` sites) and a Mapbox
  take's `country` resolve from the gitignored `public/data/sites/index.json` of the checkout the
  studio runs in, which may be stale. Before captures, refresh it read-only from that checkout's
  root: `curl -sfR --create-dirs -o public/data/sites/index.json https://ancientnerds.com/data/sites/index.json`;
  `doctor` reports its age.
- **Ledger** `studio_episodes` (migration 0026): `episode render` records every rendered video
  (case file, script and video hashes, the renderer string) through `ssh ancientnerds docker exec
  -i ancient_nerds_api python -m pipeline.studio.ledger_cli --record`; `episode register-youtube`
  marks it published (`--publish`).
- **Local only**: the NVENC and Playwright tests skip in CI, so CI never proves the capture and
  render path. On the workstation, `npm run test:gpu` in `video/` (the layout lint in a real Chrome
  on the NVIDIA, every block at its length limits, and a crashed and a closed render tab that must cancel the run at once), the smoke render and the real captures (Tasks 22 and 36 of
  `docs/superpowers/plans/2026-09-26-D-renderer-capture-video-mode.md`) prove it before a release.

Runbook (setup, both sessions, gates, recovery): `docs/procedures/STUDIO.md`.

## Local verification (measured 2026-10-03)

Use the repo venv explicitly. Bare `python`/`python3` is not reliable here: fresh shells and
pi-lens can put a foreign venv without pytest in front of PATH.

**A worktree has no `.env`**, and `pipeline/lyra/config.py` reads `env_file=".env"` relative
to the working directory. `tests/api/lyra/test_backends.py::TestGetBackend` then fails three
tests with "Anthropic API key is empty" — an environment gap, not a code defect. Load the
main checkout's `.env` for the run (it never prints the value):

```bash
./.venv/Scripts/python.exe -c "import sys,pytest; from dotenv import load_dotenv; load_dotenv(r'<main checkout>/.env'); sys.exit(pytest.main(['-q','-rs','--timeout','90','-m','not integration and not live_llm']))"
```

```bash
# Backend: the suite the pre-push hook runs (CI adds `and not slow`, which labels 0 tests)
./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"
#   2026-10-03: 10506 passed, 132 skipped, 57 deselected in 453.66s
#   (2026-09-20: 1648 passed, 3 skipped, 57 deselected in 47.71s; the skips are gitignored
#    inputs - the remediation snapshot, the Natural Earth cache, the brand fonts - and
#    00_prune_backups.sh, which cannot run on Windows)
#   -rs is mandatory: the skips are silent otherwise.

# Frontend
cd ancient-nerds-map && npm run type-check && npm run test
#   2026-10-03: type-check clean, 1215 tests in 126 files passed
#   (2026-09-20: 432 tests in 40 files)
```

In PowerShell 5.1 an argument with commas needs the `=` form: `npx knip
--no-progress "--include=files,dependencies,devDependencies"` — `npx.ps1` re-splits the
space-separated list and knip answers "Invalid issue type".

The studio renderer (`video/`, CI job `lint-video`) and the frontend's video recorder
(`ancient-nerds-map/video/`, which `npm run type-check` does not cover: its `tsconfig.json`
includes only `src`) are TypeScript projects of their own:

```bash
(cd video && npx tsc --noEmit && npx vitest run)
(cd video && npm audit --audit-level=critical)   # CI's security-scan runs it too (blocking)
(cd ancient-nerds-map && npx tsc -p video/tsconfig.json --noEmit)
```

Single tests. Always pass the gate's marker filter: `pyproject.toml` deselects only `live_llm`, so
a file marked `integration` (e.g. `tests/api/test_health.py`) otherwise errors on a missing
Postgres instead of being deselected.

```bash
M='not integration and not live_llm'
./.venv/Scripts/python.exe -m pytest tests/api/test_seo_shell.py -q -m "$M"
./.venv/Scripts/python.exe -m pytest "tests/api/test_seo_shell.py::test_splices_ssr_output" -q -m "$M"
./.venv/Scripts/python.exe -m pytest -k "radar and gates" -q -m "$M"
cd ancient-nerds-map && npx vitest run src/seo/__tests__/render.test.tsx   # or: npx vitest run -t "<name>"
```

`tests/conftest.py` sets `DATABASE_URL=sqlite:///:memory:` and zeroes the MiniMax limiter's pacing
for every test (opt out with the `real_limiter_pacing` marker). Only `tests/` is collected.

Dev server: `cd ancient-nerds-map && npm run dev` (http://localhost:5173). Vite serves `/data`
from the repo-root `public/data/` and proxies `/api` and `/goto` to `VITE_DEV_API_TARGET` (default
`http://localhost:8000`, which does not exist here; the video recorder points it at
`https://ancientnerds.com`). `npm run build:ssr` builds `dist-ssr/` for the SSR sidecar.

Local equivalents of the CI gates: `ruff check api/ pipeline/`, `lint-imports`,
`vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80`,
`semgrep scan --config .semgrep api/ pipeline/ ancient-nerds-map/src/`, `npx knip` (in
`ancient-nerds-map/`).

Installed on the dev machine (2026-09-20), so these CI gates are locally verifiable there:
`gitleaks git . --config .gitleaks.toml --gitleaks-ignore-path .gitleaksignore` (~1.5 min, full
history), `pip-audit -r requirements.txt` (likewise for `requirements-api.txt` and
`requirements.lyra.txt`) with `--ignore-vuln CVE-2026-25990`, and the container config scan — trivy
only sees copies of the Dockerfiles and the compose file, never the repo tree:

```bash
mkdir -p /tmp/dockerscan && cp Dockerfile* docker-compose.yml /tmp/dockerscan/
trivy config /tmp/dockerscan --severity HIGH,CRITICAL --exit-code 1
```

`trivy image` additionally needs a built image. On a machine without these tools, say so instead of
claiming the gate passed.

**There is no local database.** The database of record is the production one on the VPS (decision
2026-09-20, Martin). The gate suite, the lint/security gates and the pre-push hook all run DB-less —
no Docker needed for any of them.

Docker is a **tool here, not a data source**. It is worth having for exactly the gates of the CI job
`container-scan` (measured 2026-09-20: `docker build -t ancientmap-api-scan .` ≈24 s, then
`trivy image ancientmap-api-scan --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`
→ clean; `trivy config` only ever sees copies in `/tmp/dockerscan`, never the repo tree).
Do **not** bring up the compose stack locally: it requires production-only secrets
(`UMAMI_DB_PASSWORD`, `UMAMI_APP_SECRET`, `UMAMI_2FA_KEY`, …) that `.env` does not carry, and a local
Postgres would be exactly the second source of truth this project avoids.

The `integration` tests need Docker (`db`, `redis`, `qdrant`, a running API), so they cannot run
here — and they are not part of the CI gate either. **Never point them at production:** they INSERT
test rows into `unified_sites` (`source_id='test'`). Answer database questions on the VPS, read-only:

```bash
ssh <vps> "docker exec ancient_nerds_db psql -U ancient_map -d ancient_map -c '<sql>'"
```

Known state of those tests (measured 2026-09-20 against a local database, before Docker was turned
off): 34 passed, 8 failed — `tests/api/test_radar_review_endpoints.py` (7) and
`tests/api/test_replace_source.py` (1), pointing at an API validation gap (`NOT NULL` on
`unified_sites.lat/lon` instead of a 422). Unverified ever since, because CI deselects them. Schema
changes therefore reach production only through the deploy's forward-only migrations — there is no
local dress rehearsal.

## Deployment

### Flow
Push to `main` → GitHub Actions CI (lint-frontend, lint-video, lint-backend, security-scan, sast, container-scan, tests) → deploy job SSHes into VPS. All seven gates block the deploy; `tests` runs the DB-less pytest subset (`-m "not integration and not live_llm and not slow" --timeout 90`). `lint-video` runs `npm ci`, `npx tsc --noEmit` and `npx vitest run` in `video/` when the `video` path filter matches (`video/**`, `tests/pipeline/studio/golden_timeline.json`, the site's `tokens.css`, `colors.ts` and `public/fonts/**`); like the other path-filtered jobs, it blocks when red and not when skipped. The `backend` filter also matches `video/src/blocks/registry.json`, `video/src/theme/glyphs.ts` and `video/src/captions.ts`, which the studio's contract test reads.

**A push to `main` is a live deploy.** Never push from an agent session unless the change is
actually meant to go live — `.githooks/pre-push` then runs the hook gates below. `.githooks/pre-push` enforces exactly
that: for a push that targets `refs/heads/main` it first checks that the working tree matches the
pushed commit (the gates test the tree, the push deploys the commit — otherwise a green run proves
nothing) and then runs the local gates (`pytest -q -rs --timeout 90 -m "not integration and not
live_llm"`, `ruff`, `lint-imports`,
`vulture`, `npm run type-check`, `npm run test`, `npx knip --no-progress --include
files,dependencies,devDependencies`), plus `npx tsc --noEmit` and `npx vitest run` in `video/` when
the push changes a path of CI's `video` filter, measured from the remote `main` (it blocks with "run
npm ci in video/" while `video/node_modules/.bin/tsc` is missing, and when the remote `main` is not
fetched). It aborts the push when a gate is red, when the working tree
differs from the pushed commit, or when a gate cannot run at all (no venv, no npm): fail-closed.
Pushes to other branches skip the gates. The git-lfs forwarding runs afterwards, so LFS pushes keep
working. The hook is not a CI replacement: semgrep, gitleaks, pip-audit, trivy, mypy,
`ruff format --check`, `python pipeline/generate_shared_data.py --verify`, `npm run build`/`build:ssr`
and `npx size-limit` still run only in CI. Each clone has to
activate the hook once with `git config core.hooksPath .githooks`; `.gitattributes` pins
`.githooks/*` and `scripts/*.sh` to LF (`text eol=lf`) so shell scripts do not break on CRLF
checkouts.

Committing those hooks needs the executable bit **in the index**: `core.filemode` is `false` on this
Windows checkout, so a plain `git add` stores them `100644` and Linux/macOS would skip them
silently. Stage them with:

```bash
git add --chmod=+x .githooks/pre-commit .githooks/pre-push \
  .githooks/post-checkout .githooks/post-commit .githooks/post-merge
```

Known limits of the hook — by design, not bugs: `--no-verify` skips `pre-commit`/`pre-push` (not the
`post-*` hooks) and `-c core.hooksPath=` disables the whole hook directory, so no local hook can
survive a determined caller; a merge or a `workflow_dispatch` run on GitHub never executes a local
hook at all (`workflow_dispatch` deploys only from `main`). GitHub-side protection for `main` is
therefore the only backstop that cannot be bypassed locally. It exists: a branch rule blocks
force-pushes to `main` with error `GH013` (measured 2026-04-19, recorded in
`docs/procedures/PROJECT_LESSONS.md`); whether that rule also requires status checks or forbids
direct pushes is not verifiable from this repository. `git push --dry-run` also runs the gates for a `main` push: measured 2:17 min end to end
(pytest 1:27, type-check 0:31, the rest ~0:19). A push that mixes `main` with other refs is aborted
as a whole when a gate is red. The working-tree check covers tracked files only: untracked files are
not part of the pushed commit, but they can still change what the gates see. `git lfs install
--force` can overwrite `.githooks/pre-push` — restore it from git if that ever happens. `workflow_dispatch` triggers a run manually (also deploys) — useful when push-event processing is degraded. The sast job (semgrep + gitleaks + LLM-prompt-guard check) and container-scan job (trivy) block the deploy like the lint jobs. Local equivalents: `semgrep scan --config .semgrep`, `lint-imports`, `vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80`, `npx knip` (in ancient-nerds-map/).

### Deploy script (`.github/workflows/ci.yml`)
On the VPS at `/var/www/ancientnerds` (the `deploy` job; verified against `ci.yml` 2026-09-22):
1. `git checkout -- .` and `git clean` of both `public/data/` dirs — discard manual VPS edits
2. `git pull origin main` + `git lfs pull` — get latest code and LFS data files
3. Apply pending `migrations/*.sql` (see "Schema changes" above)
4. Frontend, only if `ancient-nerds-map/` changed: `npm ci && npm run build -- --outDir dist-new`,
   swapped in; the previous builds' `/assets` chunks are kept for 30 days because Googlebot renders
   from cache. Then `npm run build:ssr`.
5. Rebuild only what the diff touches: `api` (`api/`, `pipeline/`, `Dockerfile`, `requirements*`),
   `lyra` (`pipeline/`, `Dockerfile.lyra`, `requirements.lyra.txt`), `ssr` (any frontend change,
   and always together with `api`), `webcam-proxy`. `theo-worker` is rebuilt only when no
   `research_requests` row is `running` — a busy worker stays on the old image.
6. Images are built while the old containers serve; then a rolling restart ssr → api (:8000) →
   api2 (:8001), each gated by a health check.
7. Drift guard: if the `commit` reported by `http://localhost:8000/` differs from HEAD, api and
   lyra are rebuilt regardless of the diff. Check that same field after a deploy — a green run
   alone does not prove the new code is live.

The DB container (`ancient_nerds_db`) is **not** rebuilt on deploy — it persists data in a Docker volume.

### VPS notes
- Manual edits on the VPS will be discarded by `git checkout -- .` on next deploy
- If you need to fix DB data on the VPS, SSH in and use `psql` directly
- LFS is used for large static JSON files (`public/data/sites/`)
