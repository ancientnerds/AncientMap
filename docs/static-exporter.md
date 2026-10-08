# Static Exporter

Exports PostgreSQL data to static JSON files under `public/data/`, served by nginx.

**The globe does not read the site files.** `DataStore` fetches `/api/sites/all` and
`/api/sources/`, and since 2026-09-22 both answer from the database only (their static-JSON
fallbacks are gone). What does read the output: the frontend build (`hubs.snapshot.json`,
baked into `index.html`), the audit page's version history and the source pins of
`/api/sites/all` (`snapshots/`), and the library page (`library/`).

**Scope (E4, migration 0020):** retired sites are left out of every site-keyed file — the
index, the details, the image index, the links, the hub list and the snapshot file
(`pipeline.utils.public_sites.not_retired()`).

**File:** `pipeline/static_exporter.py`

## Entry Points

| Caller | Function | What it exports |
|--------|----------|-----------------|
| `python -m pipeline.static_exporter` | `StaticExporter.export_all()` | Everything below |
| `python -m pipeline.static_exporter --hubs-only` | `export_hubs_snapshot()` | `hubs.snapshot.json` only |
| `POST /api/sites/rebuild-static` (founders) | the CLI above, in a child process | Background job: answers 202, `GET /api/sites/rebuild-static/status` reports it (the export takes ~4 min, nginx cuts `/api/` at 120 s) |
| `python -m api.services.rebuild_static` (in the API container, after a write wave) | the same job body, run to completion in the caller | Takes the same lock and status row as the POST; waits; exit 0 ok, 1 failed, 3 an export already runs |
| nightly, 04:30 UTC (`api/services/static_export_schedule.py`) | the same job as the POST | Started by both API instances; the lock lets one run, the other logs "already running" |
| `POST /api/library/refresh` (internal key) | `aggregate_library()` + `_export_library()` | Background job: answers 202, `GET /api/library/refresh/status` reports it |

Both jobs run once across `api` and `api2` (Postgres advisory lock) and keep their status in
`pipeline_heartbeats` as `job:<name>` (`api/services/background_jobs.py`).

News feed is served live by the API (`/news/feed`), not exported to static JSON.

## Output Tree

```
public/data/
├── sources.json                  Source metadata (colors, counts, enabled_by_default)
├── links.json                    Site-to-content relationships
├── hubs.snapshot.json            Homepage country hub list (baked in at frontend build)
├── images/index.json             Non-excluded wiki images per site
├── snapshots/                    Dated curated-site snapshots + manifest.json (newest 50)
├── library/                      Library sources by period
├── sites/
│   ├── index.json                Compact markers for Three.js globe
│   └── details/
│       ├── europe.json           Full site details, chunked by region
│       ├── mediterranean.json
│       ├── middle_east.json
│       ├── north_africa.json
│       ├── asia.json
│       ├── americas.json
│       ├── oceania.json
│       └── africa.json
└── content/
    ├── texts.json                Content items grouped by type
    ├── maps.json
    └── ...
```

Every `.json` file also gets a `.json.gz` companion (gzip level 9). Nginx serves these via `gzip_static on`.

## Globe Data: `StaticExporter.export_all()`

### sources.json

```
source_meta table → { sources: { [id]: { n, d, c, i, cat, cnt, lic, att, on } }, total }
```

Short keys minimize file size: `n`=name, `c`=color, `on`=enabled_by_default, etc.

### sites/index.json

```
unified_sites + unified_site_names → { sites: [{ i, n, la, lo, s, t, p, pn, c, d, im, u, an }], count }
```

Compact format for rendering markers. Key map:

| Key | Field | Notes |
|-----|-------|-------|
| `i` | id | UUID as string |
| `n` | name | Truncated to 100 chars |
| `la` | latitude | Rounded to 5 decimals |
| `lo` | longitude | Rounded to 5 decimals |
| `s` | source_id | |
| `t` | site_type | Optional |
| `p` | period | `[start, end]`, optional |
| `pn` | period_name | Optional |
| `c` | country | Optional |
| `d` | description | Truncated to 500 chars, optional |
| `im` | thumbnail_url | Optional |
| `u` | source_url | Optional |
| `an` | alt_names | Latin-script only, max 10, optional |

Alt names come from `unified_site_names`, deduplicated by lowercase, filtered to Latin script only (for search, not display).

### sites/details/{region}.json

```
unified_sites WHERE lat/lon in bounds → { region, bounds, sites: { [id]: {...} }, count }
```

8 regions defined by lat/lon bounding boxes. Sites can appear in multiple regions if bounding boxes overlap (e.g. Mediterranean overlaps with Europe and North Africa).

### links.json

```
site_content_links WHERE score >= 0.2 → { links: { [site_id]: { [type]: [[src, id, score]] } }, count }
```

### content/{type}s.json

```
site_content_links (DISTINCT) → { type, items: { "src:id": { src, id, t, thumb, url, meta } }, count }
```

One file per content type (texts, maps, etc.).

## Shared Helper: `save_json()`

```python
save_json(path, data, compress=True)
```

1. Creates parent directories
2. Writes compact JSON (`separators=(",",":")`, no whitespace) to `<name>.tmp` beside the target
3. If `GZIP_OUTPUT` is true, writes `<name>.gz.tmp` at compression level 9
4. Moves each temp file over its target with `os.replace` (atomic on one file system) and logs the sizes

A reader (nginx, the frontend build) sees the old file or the complete new one, never the
short file a truncate-in-place left for the minutes the 362 MB `sites/index.json` takes. A
failed write removes its temp files and leaves the targets untouched. The temp file takes the
process umask (not `mkstemp`'s 0600): nginx reads these files as another user.

## Snapshot files: `write_file_snapshot()`

The one writer of `snapshots/` (the API's `export_file_snapshot()` calls it too). Keys are
`YYYY-MM-DD_HHMMSS`; a second write in the same second replaces its manifest entry instead of
adding a duplicate; the newest 50 are kept. A corrupt `manifest.json` raises — replacing it
with an empty one would drop the whole version history silently.

## When Things Run

```
After a write wave (the last deploy first: a deploy kills a running export), in the API container:
  docker exec ancient_nerds_api python -m api.services.rebuild_static   (locked, waits)
  scp + docker cp scripts/remediation/static_export_check.py, then python /tmp/x.py  (0 differing sites)
Every night 04:30 UTC: the same job, started by the API (api/services/static_export_schedule.py)
Manual deploy / data refresh:
  python -m pipeline.static_exporter            (or POST /api/sites/rebuild-static)
  (the plain CLI takes no lock: use it only when no other export can run)
  └─→ export_all() → sources + sites + images + hubs + content + links + library + snapshot
```

The files must be writable by the container user (uid 1000). Files created as root (as on
2026-08-18) make the export fail with a PermissionError, which the job status reports.

**Preflight (2026-09-25).** `export_all()` and `export_hubs_snapshot()` refuse to run as root
and, before the first database read or file write, check every target (`export_targets()`):
an existing file must be writable, a missing one must have a writable nearest ancestor. A
refusal names every failing path and the remedy - nothing is written, so an export is never
left half new. Root-owned targets are handed back without sudo on the host:

```
docker exec -u root ancient_nerds_api chown -R 1000:1000 /app/public/data/<path>
docker exec ancient_nerds_api python -m pipeline.static_exporter --no-library
```

The export files are gitignored (`.gitignore`, "PUBLIC DATA — generated on VPS"): they are
produced on the VPS and survive a deploy (`git clean -fd` without `-x` keeps ignored files).
Nothing of them is committed or pushed, and no LFS step belongs to them (`.gitattributes` still
lists `public/data/sites/index.json` as an LFS pattern; the file is ignored and never added).
`scripts/remediation/static_export_check.py` compares the served `d` and `cd` of every shown
site with the database (sha256 of `left(description, 500)` and of the card text); it runs in
the API container and exits 1 while any site differs.

News feed is served live by the FastAPI endpoint `GET /news/feed`.
