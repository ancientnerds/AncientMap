# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Where the 2026-09 sites remediation stands

All 5,004 `ancient_nerds` sites have been examined; **994 corrections are in the production database**
(1,022 sites, 0 deviations, each with a journal entry and a rollback file). Start with
`output/remediation/HANDOVER.md` - task, state, commands, decisions, open work and the traps that
cost time here. The evidence behind every number is `output/remediation/AUDIT_LOG.md`; what only
Martin can decide is `output/remediation/HUMAN_ONLY.md`. Two things are open: five Northern-Ireland
spelling rows (route: the mechanical lane, never the frozen discover prompt) and the search route for
the 7,761 unverifiable fields (decided: MiniMax).

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
  hourly news/story cycle. **Theo** research runs in `ancient_nerds_theo_worker` (API image,
  `scripts/run_theo_worker.py`); one paper takes 7–15 h. The LLM backend is `LYRA_LLM_BACKEND`
  (`anthropic` | `minimax`, `pipeline/lyra/config.py`); MiniMax is called through the Anthropic
  SDK against its Anthropic-compatible endpoint (`minimax_shared.py`, pacing in
  `minimax_limiter.py`).
- **Database**: PostgreSQL + PostGIS in `ancient_nerds_db`, with Redis (cache, rate limits) and
  Qdrant (vector search) beside it. SQLAlchemy models live in `pipeline/database.py`, shared by
  `api/` and `pipeline/`.
- **Static data**: Pre-exported JSON in `public/data/` (sites, sources, content, links)
- **Pipeline**: Data connectors and exporters in `pipeline/`

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
  fails on stale output (`--verify`).

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

## Local verification (measured 2026-09-20)

Use the repo venv explicitly. Bare `python`/`python3` is not reliable here: fresh shells and
pi-lens can put a foreign venv without pytest in front of PATH.

```bash
# Backend: the suite the pre-push hook runs (CI adds `and not slow`, which labels 0 tests)
./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"
#   2026-09-20: 1648 passed, 3 skipped, 57 deselected in 47.71s
#   (+16 seit dem Lyra-Funnel: Allowlist-Tests fuer /lyra.html und Query-Strings)
#   -rs is mandatory: 3 skips are silent otherwise.

# Frontend
cd ancient-nerds-map && npm run type-check && npm run test
#   2026-09-20: type-check clean, 432 tests in 40 files passed
#   (394/36 war der Stand vom Vormittag; die Linsen-Tests kamen danach dazu)
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
Push to `main` → GitHub Actions CI (lint-frontend, lint-backend, security-scan, sast, container-scan, tests) → deploy job SSHes into VPS. All six gates block the deploy; `tests` runs the DB-less pytest subset (`-m "not integration and not live_llm and not slow" --timeout 90`).

**A push to `main` is a live deploy.** Never push from an agent session unless the change is
actually meant to go live — `.githooks/pre-push` then runs the hook gates below. `.githooks/pre-push` enforces exactly
that: for a push that targets `refs/heads/main` it first checks that the working tree matches the
pushed commit (the gates test the tree, the push deploys the commit — otherwise a green run proves
nothing) and then runs the local gates (`pytest -q -rs --timeout 90 -m "not integration and not
live_llm"`, `ruff`, `lint-imports`,
`vulture`, `npm run type-check`, `npm run test`, `npx knip --no-progress --include
files,dependencies,devDependencies`). It aborts the push when a gate is red, when the working tree
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
