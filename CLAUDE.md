# Claude Code Instructions for AncientMap

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

## Architecture

### Stack
- **Frontend**: Three.js globe in `ancient-nerds-map/` (Vite + TypeScript), served as static files
- **API**: FastAPI in `api/`, runs in Docker container `ancient_nerds_api` on port 8000
- **Database**: PostgreSQL + PostGIS in Docker container `ancient_nerds_db`
- **Static data**: Pre-exported JSON in `public/data/` (sites, sources, content, links)
- **Pipeline**: Data connectors and exporters in `pipeline/`

### Key data flow
1. Connectors in `pipeline/connectors/` fetch from external APIs → write to `unified_sites` table
2. `pipeline/static_exporter.py` exports DB → static JSON files in `public/data/`
3. Frontend reads static JSON; API serves as fallback and for dynamic queries
4. `public/data/` is copied/symlinked to `ancient-nerds-map/public/data/` for the frontend build

### Source visibility: `enabled` vs `enabled_by_default`
The `source_meta` table has two boolean columns:
- **`enabled`**: whether the source is active in the system (always true for working connectors)
- **`enabled_by_default`**: whether dots show on the globe on first load (only `ancient_nerds` is true)

The static exporter writes `"on"` in `sources.json` from `enabled_by_default`. The frontend uses this to decide which sources render immediately vs require user opt-in in the Filter panel.

## Deployment

### Flow
Push to `main` → GitHub Actions CI (4 jobs: lint-frontend, lint-backend, security-scan, docker-build) → deploy job SSHes into VPS.

### Deploy script (`.github/workflows/ci.yml`)
On the VPS at `/var/www/ancientnerds`:
1. `git checkout -- .` — discard any manual VPS edits (prevents pull conflicts)
2. `git pull origin main` + `git lfs pull` — get latest code and LFS data files
3. `cd ancient-nerds-map && npm ci && npm run build` — rebuild frontend
4. `docker compose up -d --build api` — rebuild and restart API container
5. Health check on `http://localhost:8000/`

The DB container (`ancient_nerds_db`) is **not** rebuilt on deploy — it persists data in a Docker volume.

### VPS notes
- Manual edits on the VPS will be discarded by `git checkout -- .` on next deploy
- If you need to fix DB data on the VPS, SSH in and use `psql` directly
- LFS is used for large static JSON files (`public/data/sites/`)
