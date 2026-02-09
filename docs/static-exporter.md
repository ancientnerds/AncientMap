# Static Exporter

Exports PostgreSQL data to optimized static JSON files served directly by Nginx. Zero API involvement at runtime — the frontend loads these files and filters client-side.

**File:** `pipeline/static_exporter.py`

## Entry Points

| Caller | Function | What it exports |
|--------|----------|-----------------|
| `python -m pipeline.static_exporter` | `StaticExporter.export_all()` | Globe data (sources, sites, content, links) |

News feed is served live by the API (`/news/feed`), not exported to static JSON.

## Output Tree

```
public/data/
├── sources.json                  Source metadata (colors, counts, enabled_by_default)
├── links.json                    Site-to-content relationships
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
2. Writes compact JSON (`separators=(",",":")`, no whitespace)
3. Logs file size in KB
4. If `GZIP_OUTPUT` is true, writes `.json.gz` at compression level 9
5. Logs gzipped size

## When Things Run

```
Manual deploy / data refresh:
  python -m pipeline.static_exporter
  └─→ export_all() → sources + sites + content + links
```

News feed is served live by the FastAPI endpoint `GET /news/feed`.
