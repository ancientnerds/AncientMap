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
- Additional data source integrations
- Improved deduplication algorithms
- Timeline animation feature
- User accounts and saved searches
- Mobile native apps
