# Lyra News Pipeline

Fully-automated AI-powered archaeological news discovery system. Runs on a 1-hour cycle inside the `ancient_nerds_api` Docker container. Transforms raw YouTube video content into curated Radar cards through 9 sequential stages.

---

## Pipeline Overview

```mermaid
flowchart LR
    subgraph "Every Hour"
        F[1. Fetch] --> S[2. Summarize]
        S --> M[3. Match]
        M --> P[4. Posts]
        P --> V[5. Verify]
        V --> D[6. Dedup]
        D --> SC[7. Screenshots]
        SC --> B[8. Backfill]
        B --> I[9. Identify]
    end
    I --> CB[Cache Bust]
    CB --> HB[Heartbeat]
```

| Stage | File | Entry Point | AI Model |
|-------|------|-------------|----------|
| 1. Fetch | `transcript_fetcher.py` | `fetch_new_videos()` | - |
| 2. Summarize | `summarizer.py` | `summarize_pending_videos()` | Haiku |
| 3. Match | `site_matcher.py` | `match_sites_for_pending_items()` | - |
| 4. Posts | `tweet_generator.py` | `generate_pending_posts()` | Sonnet |
| 5. Verify | `tweet_verifier.py` | `verify_pending_posts()` | Haiku |
| 6. Dedup | `tweet_deduplicator.py` | `deduplicate_posts()` | - |
| 7. Screenshots | `screenshot_extractor.py` | `extract_screenshots()` | - |
| 8. Backfill | `transcript_fetcher.py` | `backfill_video_descriptions()` | - |
| 9. Identify | `site_identifier.py` | `identify_and_enrich_sites()` | Haiku + Sonnet |

---

## Data Flow

```mermaid
flowchart TD
    YT["YouTube RSS\n(18 channels)"] -->|transcripts| NV[(news_videos)]
    NV -->|Haiku summarize| NI[(news_items)]
    NI -->|exact/spaceless match| US[(unified_sites\nunified_site_names)]
    NI -->|unmatched names| UC[(user_contributions\nsource='lyra')]

    UC -->|Haiku identify| DB{"DB fuzzy\nsearch\n(pg_trgm)"}
    DB -->|match found| BRANCH{"AN/promoted\nor external?"}
    DB -->|no match| WD["Wikidata API"]

    BRANCH -->|AN/promoted| HIDDEN["status='matched'\n(hidden)"]
    BRANCH -->|external| ENRICHED["status='enriched'\nmerge all sources\n(Radar card)"]

    WD -->|entity found| WP["Wikipedia API\n(summary + lead)"]
    WP -->|Haiku extract| SCORE["Score 0-100"]
    DB -->|no match, no Wikidata| SCORE

    SCORE -->|"score >= 55\n+ coords"| PROMOTE["Promote to\nunified_sites\n(source='lyra')"]
    SCORE -->|"score < 55"| KEEP["status='enriched'\n(Radar card)"]
```

---

## Stage Details

### 1. Fetch (`transcript_fetcher.py`)

Fetches recent videos from 18 seed YouTube archaeology channels via RSS. Downloads transcripts (youtube-transcript-api, optional Webshare proxy) and metadata (yt-dlp). Skips videos < 5 minutes.

- **Reads:** `news_channels` (enabled only)
- **Writes:** `news_videos` (status=`transcribed` or `failed`)
- **External:** YouTube RSS, youtube-transcript-api, yt-dlp

### 2. Summarize (`summarizer.py`)

Sends full transcript to Haiku. Extracts 2-8 key archaeological topics per video (scaled by duration + queue size). Queue soft cap 32 / hard cap 48.

- **Reads:** `news_videos` (status=`transcribed`)
- **Writes:** `news_items` (headline, facts[], site_name_extracted), `news_videos.summary_json`
- **Model:** Haiku (`prompts/summary.txt`)

### 3. Match (`site_matcher.py`)

Matches `news_items.site_name_extracted` against the curated sites database. Four strategies in order: exact name, spaceless name, exact alt-name, spaceless alt-name. Multiple candidates resolved by source priority.

```mermaid
flowchart TD
    NI["NewsItem\nsite_name_extracted"] --> NORM["normalize_name()"]
    NORM --> E1{"Exact match\nunified_sites?"}
    E1 -->|yes| PICK
    E1 -->|no| S1{"Spaceless match\nunified_sites?"}
    S1 -->|yes| PICK
    S1 -->|no| E2{"Exact match\nunified_site_names?"}
    E2 -->|yes| PICK
    E2 -->|no| S2{"Spaceless match\nunified_site_names?"}
    S2 -->|yes| PICK
    S2 -->|no| UNMATCHED["Upsert to\nuser_contributions\n(pending)"]

    PICK["Pick best\n(lowest priority)"] --> SRC{"Source?"}
    SRC -->|AN / promoted| LINK["Link news_items.site_id\n(no radar card)"]
    SRC -->|external| RADAR["Link + create radar card\nfill_contrib_from_site()"]
```

- **Reads:** `unified_sites`, `unified_site_names`, `news_videos.summary_json`
- **Writes:** `user_contributions` (upsert by lowercase name), `news_items.site_id`
- **Key function:** `fill_contrib_from_site()` -- canonical 10-field fill-if-missing

### 4. Posts (`tweet_generator.py`)

Generates short-form social posts (280 chars) from news items via Sonnet. One post per item. Includes timestamp attribution and recency note.

- **Reads:** `news_items`, `news_videos.summary_json`
- **Writes:** `news_items.post_text`
- **Model:** Sonnet (`prompts/tweet_template.txt`)

### 5. Verify (`tweet_verifier.py`)

Fact-checks posts against the transcript segment around the timestamp (+/-10s). Verdict: ACCEPT / MODIFY / REJECT.

- **Reads:** `news_items.post_text`, `news_videos.transcript_text`
- **Writes:** `news_items.post_text` (modifications), `news_items.timestamp_seconds` (refinements)
- **Deletes:** rejected items
- **Model:** Haiku (`prompts/verify_tweets.txt`)

### 6. Dedup (`tweet_deduplicator.py`)

Removes semantic duplicates. Feature extraction: numbers, words > 3 chars, URLs, timestamps. Weighted similarity: 40% numbers + 40% words + 20% metadata. Threshold: 0.25. Keeps newest.

- **Reads/Deletes:** `news_items` (with post_text)

### 7. Screenshots (`screenshot_extractor.py`)

Extracts one frame per news item at the post timestamp. Two-step: yt-dlp downloads 3s clip, ffmpeg extracts WebP frame (300px, q75). 4 parallel workers, 3 retries with proxy rotation.

- **Reads:** `news_items.timestamp_seconds`
- **Writes:** `news_items.screenshot_url` -> `public/data/news/screenshots/{video_id}_{ts}.webp`
- **External:** yt-dlp (with proxy), ffmpeg

### 8. Backfill (`transcript_fetcher.py`)

Fills in missing video metadata (description, tags) for older videos via yt-dlp.

- **Reads/Writes:** `news_videos.description`, `news_videos.tags`

### 9. Identify + Enrich (`site_identifier.py`)

The core AI discovery engine. Processes up to 20 candidates per cycle.

```mermaid
flowchart TD
    START["user_contributions\n(pending/enriched/rejected)"] --> HASH{"Facts hash\nchanged?"}
    HASH -->|no| SKIP["Skip\n(already processed)"]
    HASH -->|yes| AI["Haiku: identify site\n(name + confidence)"]

    AI --> SITE{"is_site?"}
    SITE -->|false| NAS["status=\n'not_a_site'"]
    SITE -->|true| CONF{"confidence?"}

    CONF -->|low/medium| SONNET["Escalate\nto Sonnet"]
    CONF -->|high| DB
    SONNET --> DB

    DB["DB fuzzy search\n(pg_trgm >= 0.35)"] --> DBMATCH{"Match\nfound?"}

    DBMATCH -->|yes| COUNTRY{"Country\nvalidation"}
    COUNTRY -->|mismatch| REJ["status='rejected'\n(country_mismatch)"]
    COUNTRY -->|ok| BRANCH{"AN/promoted\nor external?"}

    BRANCH -->|AN/promoted| MATCHED["status='matched'\n(hidden)"]
    BRANCH -->|external| EXT["status='enriched'\nfill_contrib_from_site()\nfrom all ext candidates"]

    DBMATCH -->|no| WD{"Wikidata\nsearch"}
    WD -->|entity w/ Wikipedia| ENRICH["Enrich:\ncoords, country, period,\ntype, description,\nthumbnail, wikipedia_url"]
    WD -->|no results| NEW["status='enriched'\n(name only)"]

    ENRICH --> SCORE["Score 0-100"]
    EXT --> SCORE
    NEW --> SCORE

    SCORE --> PROMOTE{"score >= 55\n+ has coords\n+ date cutoff?"}
    PROMOTE -->|yes| UNI["Insert unified_sites\n(source='lyra')\nstatus='promoted'"]
    PROMOTE -->|no| DONE["Keep as\nenriched"]
```

**Scoring breakdown:**

| Field | Points |
|-------|--------|
| Site name confirmed | 25 |
| Coordinates (lat/lon) | 20 |
| Country | 10 |
| Site type | 10 |
| Period / dating | 10 |
| Description (>= 50 chars) | 10 |
| Wikipedia URL | 5 |
| Thumbnail | 5 |
| Wikidata ID | 5 |
| **Max** | **100** |

Promotion threshold: **55** (requires coords + passes date cutoff).

---

## Database Tables

```mermaid
erDiagram
    news_channels ||--o{ news_videos : "channel_id"
    news_videos ||--o{ news_items : "video_id"
    news_items }o--o| unified_sites : "site_id"
    user_contributions }o--o| unified_sites : "promoted_site_id"
    unified_sites ||--o{ unified_site_names : "site_id"
    unified_sites }o--|| source_meta : "source_id"

    news_channels {
        string id PK "YouTube channel_id"
        string name
        boolean enabled
    }
    news_videos {
        string id PK "YouTube video_id"
        string channel_id FK
        string title
        text transcript_text
        json summary_json
        string status "transcribed|summarized|verified|..."
        float duration_minutes
        string[] tags
        text description
    }
    news_items {
        uuid id PK
        string video_id FK
        string headline
        string[] facts
        string site_name_extracted
        uuid site_id FK "nullable"
        string post_text
        string screenshot_url
        int timestamp_seconds
    }
    user_contributions {
        uuid id PK
        string name
        string source "lyra|user"
        int mention_count
        string enrichment_status "pending|enriched|matched|promoted|..."
        json enrichment_data
        uuid promoted_site_id FK "nullable"
        int score
        string wikidata_id
        float lat
        float lon
        string country
        string site_type
        string period_name
        int period_start
        string wikipedia_url
        string description
        string thumbnail_url
    }
    unified_sites {
        uuid id PK
        string source_id FK
        string name
        string name_normalized
        float lat
        float lon
        string country
        string site_type
        string period_name
        int period_start
        string description
        string thumbnail_url
        string source_url
    }
    unified_site_names {
        uuid site_id FK
        string name
        string name_normalized
        string name_type "label|alias"
    }
    source_meta {
        string id PK "lyra|ancient_nerds|..."
        string name
        int priority
        boolean enabled
        boolean enabled_by_default
        int record_count
    }
```

---

## Status Codes

### `news_videos.status`

| Status | Meaning | Next Stage |
|--------|---------|------------|
| `transcribed` | Has transcript | Summarize |
| `failed` | No transcript available | - |
| `skipped` | Too short (< 5 min) | - |
| `summarized` | summary_json populated | Posts |
| `posted` | Posts generated | Verify |
| `verified` | Posts fact-checked | Dedup/Screenshots |

### `user_contributions.enrichment_status`

| Status | Meaning | Visible on Radar? |
|--------|---------|:-:|
| `pending` | Awaiting identification | No |
| `enriching` | Currently processing (transient) | No |
| `enriched` | Identified + scored | Yes |
| `matched` | Matched to AN Original / promoted site | No |
| `rejected` | Country mismatch or other rejection | No |
| `promoted` | Promoted to `unified_sites` | Yes (as globe dot) |
| `failed` | Processing error | No |
| `not_a_site` | AI determined not an archaeological site | No |

---

## External APIs

| API | Used By | Purpose |
|-----|---------|---------|
| YouTube RSS | Fetch | Discover new videos from channels |
| youtube-transcript-api | Fetch | Download video captions |
| yt-dlp | Fetch, Screenshots, Backfill | Video metadata + frame extraction |
| ffmpeg | Screenshots | Extract WebP frame from clip |
| Anthropic (Haiku) | Summarize, Verify, Identify, Extract Metadata, Pick Entity | AI processing |
| Anthropic (Sonnet) | Posts, Identify (escalation) | Creative generation + review |
| Wikidata | Identify | Entity search + claims (coords, dates) |
| Wikipedia REST | Identify | Page summary + lead section |

---

## Shared Utilities

### `fill_contrib_from_site()` (`site_matcher.py`)

Canonical fill-if-missing function used by both matcher and identifier. Copies **10 fields** from a `UnifiedSite` into a `UserContribution`:

```
country, site_type, period_name, period_start,
lat, lon, description, thumbnail_url,
wikipedia_url (from site.source_url)
```

Called from 3 locations:
1. `site_matcher._upsert_lyra_suggestion()` -- external source match during matching
2. `site_identifier._handle_db_match()` -- pre-branch fill from best match
3. `site_identifier._handle_db_match()` -- external loop filling from all candidates

### `normalize_name()` (`pipeline/utils/text.py`)

Strips diacritics, lowercases, trims whitespace. Used for all name comparisons.

### `lookup_country()` (`pipeline/utils/country_lookup.py`)

PostGIS reverse geocoding: lat/lon -> country name. Fallback when Wikidata/AI don't provide country.

---

## Orchestrator Lifecycle

```mermaid
flowchart TD
    BOOT["Container Start"] --> MIG["Auto-migrations\n(ALTER TABLE for new columns)"]
    MIG --> SEED["Seed source_meta\n+ news_channels"]
    SEED --> RESET["Versioned resets\n(v4-v13)"]
    RESET --> LOOP["Main Loop"]

    LOOP --> CHECK{"Elapsed\n>= 3600s?"}
    CHECK -->|yes| RUN["run_pipeline()\n9 stages in order"]
    CHECK -->|no| ART{"Weekly article\ndue?"}

    RUN --> SUMMARY["Log cycle summary"]
    SUMMARY --> BUST["Cache bust\n(/api/radar/cache-bust)"]
    BUST --> HEART["Write heartbeat"]
    HEART --> ART

    ART -->|yes| GEN["generate_weekly_article()"]
    ART -->|no| SLEEP["sleep(60)"]
    GEN --> SLEEP
    SLEEP --> LOOP
```

The orchestrator runs `main()` which:
1. Applies auto-migrations (new columns, indexes, table renames)
2. Seeds `source_meta` ('lyra') and `news_channels` (18 YouTube channels)
3. Applies versioned resets (v4-v13) to re-queue items when prompts/logic change
4. Enters infinite loop: run pipeline every hour, generate article weekly, heartbeat after each cycle
