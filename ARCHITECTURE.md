# Architecture Overview

This document describes the high-level architecture of the Ancient Nerds Map platform.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    React + TypeScript + Vite                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐  ┌────────────┐  │    │
│  │  │  Globe.tsx  │  │ FilterPanel │  │SitePopupOverlay│  │ LyraChat   │  │    │
│  │  │  (Three.js) │  │             │  │                │  │  Modal     │  │    │
│  │  └─────────────┘  └─────────────┘  └──────────────────┘  └────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼ HTTP/SSE
┌─────────────────────────────────────────────────────────────────────────────┐
│                               BACKEND API                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI + Python 3.11+                            │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────────┐ │    │
│  │  │  /sites   │  │  /sources │  │  /lyra    │  │  /contributions   │ │    │
│  │  │  routes   │  │  routes   │  │  routes   │  │     routes        │ │    │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────────────┘ │    │
│  │                         │                                            │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                    Services Layer                            │    │    │
│  │  │  admin_auth.py │ lyra_agent.py │ lyra_embeddings.py │ turnstile.py │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
┌─────────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│     PostgreSQL      │  │      Redis      │  │       Qdrant        │
│     + PostGIS       │  │    (Cache)      │  │   (Vector DB)       │
│                     │  │                 │  │                     │
│  - unified_sites    │  │  - API cache    │  │  - Site embeddings  │
│  - contributions    │  │  - Rate limits  │  │  - Semantic search  │
└─────────────────────┘  └─────────────────┘  └─────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA PIPELINE                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    pipeline.main + ingesters                         │    │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │    │
│  │  │Pleiades │  │  DARE   │  │ UNESCO  │  │Wikidata │  │ 30+ more│   │    │
│  │  │ingester │  │ingester │  │ingester │  │ingester │  │ingesters│   │    │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
AncientMap/
├── api/                      # FastAPI backend
│   ├── main.py              # Application entry point
│   ├── cache.py             # Redis caching utilities
│   ├── config/              # Configuration modules
│   ├── routes/              # API endpoint handlers
│   │   ├── lyra.py          # Lyra AI chat (SSE streaming)
│   │   ├── radar.py         # Lyra Radar (discovered sites)
│   │   ├── news.py          # News feed endpoints
│   │   ├── sites.py         # Site data endpoints
│   │   ├── sources.py       # Data source endpoints
│   │   ├── contributions.py # User contributions
│   │   ├── og.py            # Open Graph metadata
│   │   ├── sitemap.py       # XML sitemap generation
│   │   └── streetview.py    # Street View integration
│   └── services/            # Business logic
│       ├── admin_auth.py    # PIN auth (timing-safe, XFF-aware)
│       ├── lyra_agent.py    # Mercury-powered RAG agent with tools
│       ├── lyra_embeddings.py # Voyage AI embeddings + Qdrant
│       └── turnstile.py     # Cloudflare Turnstile verification
│
├── pipeline/                 # Data ingestion + news pipeline
│   ├── main.py              # Pipeline orchestrator
│   ├── unified_loader.py    # Central data loading
│   ├── database.py          # Database models (SQLAlchemy)
│   ├── config.py            # Pipeline configuration
│   ├── ingesters/           # Data source ingesters (30+)
│   │   ├── pleiades.py
│   │   ├── dare.py
│   │   ├── unesco.py
│   │   └── ...
│   ├── lyra/                # AI news pipeline (hourly cycle)
│   │   ├── orchestrator.py  # 9-step pipeline runner
│   │   ├── config.py        # Lyra settings + shared client
│   │   ├── transcript_fetcher.py  # YouTube RSS + transcripts
│   │   ├── summarizer.py    # LLM topic extraction
│   │   ├── site_matcher.py  # DB fuzzy matching (pg_trgm)
│   │   ├── tweet_generator.py     # Social post generation
│   │   ├── tweet_verifier.py      # Fact verification
│   │   ├── tweet_deduplicator.py  # Semantic deduplication
│   │   ├── significance_scorer.py # Rescore + categorize
│   │   ├── screenshot_extractor.py # Video frame extraction
│   │   ├── site_identifier.py     # AI site identification
│   │   ├── article_generator.py   # Weekly article
│   │   └── prompts/         # 16 LLM prompt files (all guarded)
│   ├── normalizers/         # Data normalization
│   ├── deduplication/       # Duplicate detection
│   └── utils/               # Utility functions
│
├── ancient-nerds-map/        # React frontend
│   ├── src/
│   │   ├── App.tsx          # Main application
│   │   ├── components/      # React components
│   │   │   ├── Globe.tsx    # 3D globe (Three.js)
│   │   │   ├── FilterPanel.tsx
│   │   │   ├── SitePopupOverlay.tsx
│   │   │   ├── LyraChatModal.tsx
│   │   │   ├── NewsFeedPanel.tsx
│   │   │   └── ...          # 22 component files total
│   │   ├── pages/           # Route pages
│   │   │   ├── LyraPage.tsx
│   │   │   ├── LyraRadarPage.tsx
│   │   │   └── NewsFeedPage.tsx
│   │   ├── hooks/           # Custom React hooks
│   │   ├── services/        # API client services
│   │   ├── types/           # TypeScript definitions
│   │   └── utils/           # Utility functions
│   ├── public/              # Static assets
│   └── dist/                # Production build
│
├── scripts/                  # Utility scripts
│   ├── init_db.py           # Database initialization
│   ├── build_lyra_index.py   # Build vector search index
│   ├── download_all.py      # Download all data sources
│   └── vps_backup.sh        # Backup scripts
│
├── data/                     # Data storage
│   └── raw/                 # Raw downloaded data
│
└── docker-compose.yml        # Container orchestration
```

## Key Components

### Frontend (React/TypeScript)

**Globe Visualization** (`Globe.tsx`)
- Three.js-based 3D globe rendering
- WebGL for high-performance rendering
- Supports 750K+ site markers
- H3 hexagonal clustering for zoom levels
- Custom shaders for visual effects

**State Management**
- React Context for global state
- Custom hooks for data fetching
- Optimistic updates for user actions

### Backend (FastAPI/Python)

**API Layer**
- RESTful endpoints for site data
- Server-Sent Events (SSE) for AI streaming
- Request validation with Pydantic
- Rate limiting with Redis

**Services**
- `admin_auth.py`: Timing-safe PIN authentication with XFF-aware IP extraction
- `lyra_agent.py`: Mercury-powered RAG agent with 5 tools (site search, news lookup, map navigation, etc.)
- `lyra_embeddings.py`: Voyage AI embeddings + Qdrant vector search
- `turnstile.py`: Cloudflare Turnstile bot protection
- `cache.py`: Redis caching with TTL

### Data Pipeline

**Unified Loader**
- Orchestrates data ingestion from 30+ sources
- Normalizes data to common schema
- Handles deduplication across sources
- Exports to PostgreSQL and static JSON

**Ingesters**
- Source-specific data parsers
- Rate-limited API calls
- Error handling and retries

### Databases

**PostgreSQL + PostGIS**
- Primary data store for 750K+ sites
- Spatial indexing with PostGIS
- H3 hexagonal indexes for clustering

**Redis**
- API response caching (30 min TTL)
- Rate limiting counters
- Session storage fallback

**Qdrant** (self-hosted, telemetry disabled)
- Vector embeddings via Voyage AI (voyage-4)
- Powers Lyra agent's semantic site search tool
- Reranking via Voyage rerank-2.5-lite

## Data Flow

### Site Data Request

```
1. User pans/zooms globe
2. Frontend calculates viewport bounds
3. GET /api/sites/all?source=...&limit=...
4. API checks Redis cache
5. If miss: Query PostgreSQL with PostGIS
6. Cache response, return to client
7. Frontend renders markers on globe
```

### AI Chat Query (Lyra)

```
1. User submits question
2. POST /api/lyra/chat (Turnstile + rate limit)
3. Lyra agent initialized with Mercury 2
4. Agent loop (tool use):
   a. LLM decides which tools to call
   b. Tools: site_search, news_search, navigate_map, etc.
   c. Tool results fed back to LLM
   d. LLM generates streamed response
5. SSE events sent to frontend:
   - token events (streaming text)
   - sites events (map markers)
   - news events (related articles)
   - done event (completion)
6. 5-minute timeout enforced on connection
```

### Data Ingestion

```
1. python -m pipeline.main ingest pleiades
2. Ingester fetches raw data
3. Parser extracts records
4. Normalizer standardizes fields
5. Deduplicator checks for duplicates
6. Records inserted to PostgreSQL
7. Embeddings computed and stored in Qdrant
8. Static JSON exported for CDN
```

## Deployment Architecture

### Production

```
                    ┌─────────────┐
                    │   Nginx     │
                    │  (reverse   │
                    │   proxy)    │
                    └──────┬──────┘
                           │
       ┌────────────────┼────────────────┐
       ▼                ▼                ▼
┌─────────────┐ ┌──────────────┐ ┌─────────────┐
│   Static    │ │   FastAPI    │ │  Mercury    │
│   Files     │ │   (API)      │ │    API      │
│   (Vite)    │ │              │ │  (external) │
└─────────────┘ └──────────────┘ └─────────────┘
                        │                ▲
                        │                │
                ┌───────┴──────┐  ┌──────┴──────┐
                │              │  │    Lyra     │
                │              │  │  Pipeline   │
                │              │  │  (hourly)   │
                │              │  └──────┬──────┘
                │              │         │
       ┌────────┼────────┐     └────┬────┘
       ▼        ▼        ▼         ▼
┌─────────────┐ ┌──────────────┐ ┌─────────────┐
│ PostgreSQL  │ │    Redis     │ │   Qdrant    │
│  + PostGIS  │ │              │ │             │
└─────────────┘ └──────────────┘ └─────────────┘
```

### Docker Services

| Service    | Image                    | Port  | Purpose                           |
|------------|--------------------------|-------|-----------------------------------|
| api        | custom (Dockerfile)      | 8000  | FastAPI backend                   |
| lyra       | custom (Dockerfile.lyra) | -     | Lyra news pipeline (hourly cycle) |
| db         | postgis/postgis:16-3.4   | 5432  | Primary database (PostGIS)        |
| redis      | redis:7.2.4-alpine       | 6379  | API response caching              |
| qdrant     | qdrant/qdrant            | 6333  | Vector search (self-hosted)       |
| pgadmin    | dpage/pgadmin4           | 5050  | DB admin (dev only)               |

## Performance Optimizations

### Frontend
- H3 clustering reduces marker count at low zoom
- WebWorkers for heavy computations
- Virtual scrolling for long lists
- Lazy loading of site details

### Backend
- Redis caching with 30-minute TTL
- GZip compression for responses >500 bytes
- Pre-computed H3 indexes in database
- Connection pooling for PostgreSQL

### Database
- PostGIS spatial indexes (`geom && envelope`)
- H3 indexes for clustering queries
- Partial indexes for common filters
- Query result caching

## Security Model

See [SECURITY.md](SECURITY.md) for details.

- **Authentication**: Timing-safe PIN comparison (`secrets.compare_digest`), Bearer token for admin
- **Bot protection**: Cloudflare Turnstile on chat and contribution endpoints
- **Rate limiting**: Per-IP in-memory rate limiter (20/hr on chat), XFF-aware behind proxy
- **Input validation**: Pydantic models with size constraints on all endpoints
- **XSS prevention**: UUID validation on dynamic URL parameters, HTML escaping
- **SSE protection**: 5-minute max stream duration, generic error messages
- **AI security**: Prompt injection guards on all 11 LLM prompts, sanitized tool errors
- **Connection pooling**: Shared API client across pipeline modules

## Future Considerations

- **Horizontal scaling**: Stateless API supports multiple instances
- **CDN integration**: Static JSON can be served from CDN
- **Real-time updates**: WebSocket support for live data
- **Mobile apps**: API designed for cross-platform use
