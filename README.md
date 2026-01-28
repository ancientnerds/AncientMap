# ANCIENT NERDS - Research Platform

The one and only platform with all ancient archaeological sites in one place for everyone to study.

## Project Overview

This project aggregates data from 100+ open-source archaeological databases worldwide into a unified, deduplicated dataset. It includes:

- **Data Pipeline**: Python scripts to ingest data from various sources (Pleiades, UNESCO, Open Context, DINAA, etc.)
- **PostgreSQL + PostGIS Database**: Unified storage with geospatial support
- **FastAPI Backend**: REST API with rate limiting and API keys for monetization
- **React + Mapbox Frontend**: Interactive map visualization (in `ancient-nerds-map/`)

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Node.js 18+ (for frontend)

### Setup

1. **Clone and install dependencies**:
   ```bash
   cd AncientNerds
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. **Start the database**:
   ```bash
   docker compose up -d db
   ```

3. **Initialize the database**:
   ```bash
   python scripts/init_db.py
   ```

4. **Run the first data ingestion (Pleiades)**:
   ```bash
   python -m pipeline.main ingest pleiades
   ```

5. **Check status**:
   ```bash
   python -m pipeline.main status
   ```

## Project Structure

```
AncientNerds/
├── pipeline/               # Data ingestion pipeline
│   ├── config.py          # Configuration management
│   ├── database.py        # SQLAlchemy models
│   ├── main.py            # CLI entry point
│   ├── ingesters/         # Source-specific ingesters
│   │   ├── base.py        # Base ingester class
│   │   ├── pleiades.py    # Pleiades ingester
│   │   └── ...
│   ├── normalizers/       # Data normalization
│   └── deduplication/     # Deduplication logic
├── api/                    # FastAPI backend
│   ├── main.py            # API entry point
│   ├── routers/           # API endpoints
│   └── middleware/        # Rate limiting, auth
├── scripts/               # Utility scripts
│   ├── init_db.py         # Database initialization
│   └── run_pipeline.py    # Pipeline runner
├── data/                  # Data storage
│   ├── raw/               # Downloaded raw data
│   └── processed/         # Processed exports
├── tests/                 # Test suite
├── docker-compose.yml     # Docker services
├── requirements.txt       # Python dependencies
└── .env                   # Environment configuration
```

## Data Sources

Currently implemented:
- **Pleiades** (38,000+ ancient Mediterranean places)

Planned:
- UNESCO World Heritage Sites
- GeoNames (archaeological features)
- Open Context
- DINAA (900,000+ North American sites)
- Historic England
- EAMENA
- And 100+ more regional databases

See `ANCIENT_NERDS_MAP_DATA_SOURCES.md` for the complete list.

## Pipeline Commands

```bash
# Ingest data from a specific source
python -m pipeline.main ingest pleiades

# Ingest from all sources
python -m pipeline.main ingest all

# Check pipeline status
python -m pipeline.main status

# List available sources
python -m pipeline.main list-sources

# Preview data without saving
python -m pipeline.main preview pleiades --limit 20
```

## Documentation

- `ANCIENT_NERDS_MAP_DATA_SOURCES.md` - Complete list of 100+ data sources
- `DATA_MERGING_DEDUPLICATION_STRATEGY.md` - Technical strategy for deduplication

## License

This project aggregates open data from various sources. Each source has its own license:
- Pleiades: CC-BY 3.0
- UNESCO: Open with attribution
- And more (see source documentation)

Please respect the attribution requirements of each data source.

## Contributing

Contributions welcome! Especially:
- New data source ingesters
- Deduplication improvements
- API features
- Frontend enhancements

## Contact

- **Issues & Bugs**: [GitHub Issues](https://github.com/AncientNerds/AncientMap/issues)
- **Discussions**: [GitHub Discussions](https://github.com/AncientNerds/AncientMap/discussions)
