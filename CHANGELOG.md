# Changelog

All notable changes to the ANCIENT NERDS Map project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-27

### Added
- Initial open source release
- Interactive 3D globe visualization with Three.js and Mapbox GL
- 800,000+ archaeological sites from 30+ data sources
- Real-time site filtering by source, category, country, and time period
- Site detail popups with Wikipedia images and related content
- Offline mode with IndexedDB caching
- AI assistant (Lyra) for archaeological research questions
- Historical empire boundaries visualization
- Sea level change overlays
- Paleoshoreline data for ancient coastlines
- Mobile-responsive design
- Dark/light theme support
- Site contribution system with admin review
- Measurement tools for distance calculation
- 3D model integration via Sketchfab

### Data Sources
- Pleiades (ancient Mediterranean)
- UNESCO World Heritage Sites
- Open Context
- DINAA (North American archaeology)
- Historic England
- GeoNames archaeological features
- Wikidata archaeological sites
- OSM historic features
- And 25+ additional regional databases

### Technical
- FastAPI backend with PostgreSQL/PostGIS
- React 18 frontend with TypeScript
- Redis caching for API responses
- Docker Compose deployment
- Cloudflare Turnstile bot protection
- Rate limiting for public API

## [Unreleased]

### Planned
- Timeline animation feature
- User accounts and saved searches
- Mobile native apps

## [2.0.0] - 2026-02-11

### Added
- Lyra News Pipeline: fully automated 9-step archaeological news discovery from 18+ YouTube channels
- AI-powered site identification via Claude Haiku with extended thinking for garbled caption names
- Radar page showing AI-discovered archaeological sites not yet in the main database
- News feed with curated social posts, screenshot thumbnails, and deep-link timestamps
- Lyra RAG chat agent (Claude-powered) with tool use: site search, news lookup, map navigation
- Weekly AI-generated article summarizing archaeological news
- Automatic site promotion from Radar to globe when enrichment score >= 55
- Creator opt-out system for YouTube channel exclusion

### Changed
- AI chat backend migrated from Ollama/Qdrant to Anthropic Claude API with Voyage AI embeddings
- All AI pipeline calls use structured JSON schema outputs (zero parse failures)
- Prompt caching on all pipeline LLM calls (90% cost reduction on repeated prompts)
- Shared Anthropic client pool across all pipeline modules (connection reuse)

### Security (Audit Rounds 1-3)
- Fixed reflected XSS in OG share page (UUID validation + HTML escaping)
- Fixed X-Forwarded-For header spoofing (only trust when TRUSTED_PROXY=1)
- Fixed admin PIN: removed insecure default, use timing-safe comparison
- Added prompt injection guards to all 11 LLM prompt files
- Added request payload size limits (images: 5, history: 50 messages)
- Added SSE stream timeout (5 minutes max connection duration)
- Capped sites endpoint at 50k rows (was 1M)
- Fixed radar cache-bust endpoint open when LYRA_ADMIN_KEY unconfigured
- Sanitized tool error messages in Lyra agent (no internal leak to users)
- Removed token waste: significance/category scoring from post generator (rescorer handles it)
- Removed unused schema fields from verifier (core_claim, site_name_correction)
- Replaced hard-delete with soft-delete in deduplicator
- Bounded deduplicator query to 500 items (prevents O(n^2) blowup)
- Fixed stale "tweeted" video status filter in article generator
- Fixed all datetime.utcnow() calls to datetime.now(UTC)
- Deleted dead code: _format_attribution, ESCALATION_SCHEMA, _parse_identification
