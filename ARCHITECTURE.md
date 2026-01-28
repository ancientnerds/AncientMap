# Architecture Overview

This document describes the high-level architecture of the Ancient Nerds Map platform.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    React + TypeScript + Vite                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │    │
│  │  │  Globe.tsx  │  │ FilterPanel │  │  SitePopup  │  │  AIChat    │  │    │
│  │  │  (Three.js) │  │             │  │             │  │  Modal     │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼ HTTP/SSE
┌─────────────────────────────────────────────────────────────────────────────┐
│                               BACKEND API                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI + Python 3.11+                            │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────────────┐ │    │
│  │  │  /sites   │  │  /sources │  │    /ai    │  │  /contributions   │ │    │
│  │  │  routes   │  │  routes   │  │  routes   │  │     routes        │ │    │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────────────┘ │    │
│  │                         │                                            │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                    Services Layer                            │    │    │
│  │  │  access_control.py │ rag_service.py │ cache.py              │    │    │
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
│  │                    unified_loader.py                                 │    │
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
│   │   └── ai_modes.py      # AI mode configurations
│   ├── routes/              # API endpoint handlers
│   │   ├── ai.py            # AI chat endpoints
│   │   ├── sites.py         # Site data endpoints
│   │   ├── sources.py       # Data source endpoints
│   │   ├── contributions.py # User contributions
│   │   ├── og.py            # Open Graph metadata
│   │   ├── sitemap.py       # XML sitemap generation
│   │   └── streetview.py    # Street View integration
│   └── services/            # Business logic
│       ├── access_control.py # PIN-based access management
│       └── rag_service.py   # RAG pipeline for AI chat
│
├── pipeline/                 # Data ingestion pipeline
│   ├── main.py              # Pipeline orchestrator
│   ├── unified_loader.py    # Central data loading
│   ├── database.py          # Database interface
│   ├── config.py            # Pipeline configuration
│   ├── ingesters/           # Data source ingesters (30+)
│   │   ├── pleiades.py
│   │   ├── dare.py
│   │   ├── unesco.py
│   │   └── ...
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
│   │   │   ├── SitePopup.tsx
│   │   │   └── AIAgentChatModal.tsx
│   │   ├── hooks/           # Custom React hooks
│   │   ├── services/        # API client services
│   │   ├── types/           # TypeScript definitions
│   │   └── utils/           # Utility functions
│   ├── public/              # Static assets
│   └── dist/                # Production build
│
├── scripts/                  # Utility scripts
│   ├── init_db.py           # Database initialization
│   ├── build_ai_index.py    # Build vector search index
│   ├── download_all.py      # Download all data sources
│   └── vps_backup.sh        # Backup scripts
│
├── data/                     # Data storage
│   ├── raw/                 # Raw downloaded data
│   ├── processed/           # Processed data
│   └── cache/               # Cache files
│
└── docker-compose.yml        # Container orchestration
```

## Key Components

### Frontend (React/TypeScript)

**Globe Visualization** (`Globe.tsx`)
- Three.js-based 3D globe rendering
- WebGL for high-performance rendering
- Supports 800K+ site markers
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
- `access_control.py`: PIN-based authentication for AI
- `rag_service.py`: Retrieval-Augmented Generation
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
- Primary data store for 800K+ sites
- Spatial indexing with PostGIS
- H3 hexagonal indexes for clustering

**Redis**
- API response caching (30 min TTL)
- Rate limiting counters
- Session storage fallback

**Qdrant**
- Vector embeddings for semantic search
- Powers AI site discovery
- Collection per data source

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

### AI Chat Query

```
1. User submits question
2. POST /api/ai/verify (Turnstile + PIN)
3. Session token returned
4. GET /api/ai/stream?message=...
5. API enters inference queue
6. RAG pipeline:
   a. Embed query with sentence-transformers
   b. Search Qdrant for relevant sites
   c. Build context from top results
   d. Stream response from Ollama LLM
7. SSE events sent to frontend
8. Frontend displays streaming response
```

### Data Ingestion

```
1. python -m pipeline.unified_loader --source pleiades
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
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │   Static    │ │   FastAPI   │ │   Ollama    │
    │   Files     │ │   (API)     │ │   (LLM)     │
    │   (Vite)    │ │             │ │             │
    └─────────────┘ └─────────────┘ └─────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ PostgreSQL  │ │    Redis    │ │   Qdrant    │
    │  + PostGIS  │ │             │ │             │
    └─────────────┘ └─────────────┘ └─────────────┘
```

### Docker Services

| Service    | Image                    | Port  | Purpose              |
|------------|--------------------------|-------|----------------------|
| db         | postgis/postgis:16-3.4   | 5432  | Primary database     |
| redis      | redis:7-alpine           | 6379  | Caching              |
| qdrant     | qdrant/qdrant            | 6333  | Vector search        |
| searxng    | searxng/searxng          | 8888  | Web search (AI)      |
| pgadmin    | dpage/pgadmin4           | 5050  | DB admin (dev only)  |

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

- PIN-based authentication for AI features
- Cloudflare Turnstile for bot protection
- Rate limiting per IP and tier
- Session timeout and cleanup
- Input validation on all endpoints

## Future Considerations

- **Horizontal scaling**: Stateless API supports multiple instances
- **CDN integration**: Static JSON can be served from CDN
- **Real-time updates**: WebSocket support for live data
- **Mobile apps**: API designed for cross-platform use
