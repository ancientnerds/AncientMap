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
   git clone https://github.com/AncientNerds/AncientMap.git
   cd AncientMap
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   ```bash
   # Copy the example environment file
   cp .env.example .env

   # Edit .env with your settings (see Configuration section below)
   ```

   **Required settings in `.env`:**
   - `POSTGRES_PASSWORD` - Set a secure password for the database
   - `MAPBOX_ACCESS_TOKEN` - Get a free token from [Mapbox](https://account.mapbox.com/access-tokens/)

   > **Security Note**: Never commit your `.env` file to git. It's already in `.gitignore`.

3. **Start the services** (PostgreSQL, Redis, etc.):
   ```bash
   docker compose up -d
   ```

4. **Initialize the database**:
   ```bash
   python scripts/init_db.py
   ```

5. **Start the API server**:
   ```bash
   uvicorn api.main:app --reload --port 8000
   ```

6. **Start the frontend** (in a new terminal):
   ```bash
   cd ancient-nerds-map
   npm install
   npm run dev
   ```

7. **Open the app**: Visit http://localhost:5173

### Configuration

The `.env` file controls all configuration. Key sections:

| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_PASSWORD` | Database password | ✅ Yes |
| `DATABASE_URL` | Full PostgreSQL connection string | Auto-generated |
| `MAPBOX_ACCESS_TOKEN` | For map tiles ([get free token](https://mapbox.com)) | ✅ Yes |
| `AI_VALID_PINS` | JSON of PINs for AI agent access | Optional |
| `OLLAMA_MODEL` | LLM model for AI features | Optional |

See `.env.example` for all available options with descriptions.

### Running the Data Pipeline

After setup, you can ingest archaeological data:

```bash
# Run the first data ingestion (Pleiades)
python -m pipeline.main ingest pleiades

# Check pipeline status
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
├── .env.example           # Environment template (copy to .env)
└── .env                   # Your local config (not in git)
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
