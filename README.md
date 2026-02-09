# ANCIENT NERDS - Research Platform

The one and only platform with all ancient archaeological sites in one place for everyone to study.

## Project Overview

This project aggregates data from 30+ open-source archaeological databases into a unified dataset of 800,000+ sites, displayed on an interactive 3D globe. It includes:

- **3D Globe**: Three.js + Mapbox GL interactive visualization with 800K+ site markers
- **Lyra AI Agent**: Claude-powered research assistant with tool use (site search, news lookup, map navigation)
- **News Pipeline**: Automated archaeological news discovery from 18+ YouTube channels (hourly cycle)
- **Radar**: AI-discovered archaeological sites not yet in the main database
- **Data Pipeline**: Python ingesters for 30+ external data sources
- **PostgreSQL + PostGIS Database**: Unified storage with spatial indexing
- **FastAPI Backend**: REST API with rate limiting and bot protection
- **React + TypeScript Frontend**: Full-featured SPA with filtering, empires, sea levels, and more

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
| `ADMIN_PIN` | 4-digit PIN for admin features | Optional |
| `LYRA_ADMIN_KEY` | Bearer token for Lyra admin chat | Optional |
| `LYRA_ANTHROPIC_API_KEY` | Anthropic API key for AI features | For AI |

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
AncientMap/
├── api/                    # FastAPI backend
│   ├── main.py            # API entry point
│   ├── routes/            # API endpoints (sites, lyra, radar, news, og)
│   └── services/          # Business logic (lyra_agent, admin_auth)
├── pipeline/               # Data ingestion + news pipeline
│   ├── database.py        # SQLAlchemy models
│   ├── ingesters/         # Source-specific ingesters (30+)
│   ├── lyra/              # AI news pipeline (9-step hourly cycle)
│   │   ├── orchestrator.py
│   │   ├── prompts/       # 11 LLM prompt files
│   │   └── ...
│   └── utils/             # Shared utilities
├── ancient-nerds-map/      # React + TypeScript frontend
│   └── src/
├── docs/                  # Technical documentation
├── scripts/               # Utility scripts
├── docker-compose.yml     # Docker services
└── .env.example           # Environment template (copy to .env)
```

## Data Sources

30+ integrated sources including:
- **Pleiades** (38,000+ ancient Mediterranean places)
- **UNESCO** World Heritage Sites
- **Wikidata** archaeological sites
- **Open Context**, **DINAA**, **Historic England**, **GeoNames**
- **OSM** historic features
- **Lyra Radar**: AI-discovered sites from YouTube archaeology channels
- And 20+ more regional databases

See [CHANGELOG.md](CHANGELOG.md) for the full list.

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

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and data flow
- [API.md](API.md) - API endpoint documentation
- [SECURITY.md](SECURITY.md) - Security policy and measures
- [CHANGELOG.md](CHANGELOG.md) - Release history and audit changes
- [docs/lyra-pipeline.md](docs/lyra-pipeline.md) - Lyra news pipeline (9-step cycle)
- [docs/lyra-rag-pipeline.html](docs/lyra-rag-pipeline.html) - Full AI architecture diagram

## License

This project aggregates open data from various sources. Each source has its own license:
- Pleiades: CC-BY 3.0
- UNESCO: Open with attribution
- And more (see source documentation)

Please respect the attribution requirements of each data source.

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Especially:
- New data source ingesters
- Frontend enhancements
- Security improvements
- Documentation

## Contact

- **Issues & Bugs**: [GitHub Issues](https://github.com/AncientNerds/AncientMap/issues)
- **Discussions**: [GitHub Discussions](https://github.com/AncientNerds/AncientMap/discussions)
