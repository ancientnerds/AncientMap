# Static Exporter

Exports PostgreSQL data to optimized static JSON files served directly by Nginx. Zero API involvement at runtime — the frontend loads these files and filters client-side.

**File:** `pipeline/static_exporter.py`

## Entry Points

| Caller | Function | What it exports |
|--------|----------|-----------------|
| `python -m pipeline.static_exporter` | `StaticExporter.export_all()` | Globe data (sources, sites, content, links) |
| Lyra orchestrator (each hourly cycle) | `export_news_feed()` | News feed (`news/feed.json`) |

These are independent. `export_news_feed()` is a standalone function, not part of the `StaticExporter` class.

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
├── content/
│   ├── texts.json                Content items grouped by type
│   ├── maps.json
│   └── ...
└── news/
    └── feed.json                 Full news feed for client-side filtering
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

## News Feed: `export_news_feed()`

### news/feed.json

Single query joining 4 tables:

```sql
news_items  ──JOIN──  news_videos  ──JOIN──  news_channels
     │
     └──LEFT JOIN──  unified_sites
```

**Filter:** `WHERE post_text IS NOT NULL` (only items that have been through the full pipeline).

**Order:** `published_at DESC, created_at DESC`

Output matches the frontend `NewsItemData` TypeScript interface exactly:

```json
{
  "items": [
    {
      "id": 42,
      "headline": "...",
      "summary": "...",
      "post_text": "...",
      "facts": ["...", "..."],
      "timestamp_range": "2:15-4:30",
      "timestamp_seconds": 135,
      "screenshot_url": "/api/news/screenshots/...",
      "youtube_url": "https://www.youtube.com/watch?v=...",
      "youtube_deep_url": "https://www.youtube.com/watch?v=...&t=135s",
      "video": {
        "id": "dQw4w9WgXcQ",
        "title": "...",
        "channel_name": "...",
        "channel_id": "UC...",
        "published_at": "2025-01-15T10:00:00",
        "thumbnail_url": "https://i.ytimg.com/...",
        "duration_minutes": 12.5
      },
      "created_at": "2025-01-15T12:00:00",
      "site_id": "uuid-or-null",
      "site_name": "Pompeii",
      "site_lat": 40.7509,
      "site_lon": 14.4869,
      "site_type": "Settlement",
      "site_period_name": "500 BC - 1 AD",
      "site_period_start": -79,
      "site_country": "Italy",
      "site_name_extracted": null,
      "significance": 7,
      "news_category": "new_discovery"
    }
  ],
  "total_count": 1234,
  "exported_at": "2025-01-15T13:00:00"
}
```

`youtube_url` and `youtube_deep_url` are built in Python from `video_id` and `timestamp_seconds`. `site_name_extracted` is only included when `site_id` is null (unmatched items).

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

Lyra pipeline (every hour, or --once):
  orchestrator.py main()
  └─→ run_pipeline()
  └─→ _bust_radar_cache()
  └─→ export_news_feed()        ← news/feed.json
  └─→ write heartbeat
```

## Nginx Serving

```nginx
# Static news feed — served directly, no API
location /data/news/ {
    alias /var/www/ancientnerds/public/data/news/;
    add_header Cache-Control "public, max-age=300";
    gzip_static on;
}
```

The frontend fetches `/data/news/feed.json` once, then filters entirely client-side via `useMemo`. Live polling (5 items every 30s) still hits the API for freshest items only.
