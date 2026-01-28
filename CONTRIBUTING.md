# Contributing to Ancient Nerds Map

Thank you for your interest in contributing to the Ancient Nerds Map project!
This document provides guidelines for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Data Contributions](#data-contributions)

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating,
you are expected to uphold this code. Please report unacceptable behavior to the
project maintainers.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+ with PostGIS
- Docker (recommended for local development)

### Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/AncientNerds/AncientMap.git
   cd AncientMap
   ```

2. Copy the environment template:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. Start the database:
   ```bash
   docker compose up -d db redis
   ```

4. Set up the Python environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. Set up the frontend:
   ```bash
   cd ancient-nerds-map
   npm install
   ```

6. Initialize the database:
   ```bash
   python scripts/init_db.py
   ```

7. Start development servers:
   ```bash
   # Terminal 1: API
   uvicorn api.main:app --reload

   # Terminal 2: Frontend
   cd ancient-nerds-map && npm run dev
   ```

## How to Contribute

### Reporting Bugs

- Check existing issues to avoid duplicates
- Use the bug report template
- Include steps to reproduce
- Include browser/OS information for frontend issues
- Include Python version and OS for backend issues

### Suggesting Features

- Check existing issues and discussions first
- Describe the problem you're trying to solve
- Explain your proposed solution
- Consider alternatives you've thought about

### Contributing Code

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Write or update tests
5. Ensure all tests pass
6. Commit your changes (see commit guidelines below)
7. Push to your fork
8. Open a Pull Request

### Contributing Data

We welcome contributions of new data sources! See [Data Contributions](#data-contributions)
section below.

## Development Setup

### Backend (Python/FastAPI)

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt  # if available

# Run tests
pytest

# Run linting
ruff check .
mypy .
```

### Frontend (React/TypeScript)

```bash
cd ancient-nerds-map

# Install dependencies
npm install

# Run development server
npm run dev

# Run tests
npm test

# Run linting
npm run lint

# Build for production
npm run build
```

### Database

```bash
# Start PostgreSQL with PostGIS
docker compose up -d db

# Or use docker compose for all services
docker compose up -d

# Initialize database schema
python scripts/init_db.py

# Load sample data
python -m pipeline.unified_loader --source ancient_nerds
```

## Pull Request Process

### Before Submitting

- [ ] Code follows the project's style guidelines
- [ ] Self-review of your code
- [ ] Comments added for complex logic
- [ ] Documentation updated if needed
- [ ] No new warnings introduced
- [ ] Tests added/updated
- [ ] All tests pass locally

### PR Guidelines

1. **Title**: Use a clear, descriptive title
   - Good: "Add support for EAMENA data source"
   - Bad: "Fixed stuff"

2. **Description**: Include:
   - What changes were made
   - Why the changes were necessary
   - How to test the changes
   - Screenshots for UI changes

3. **Size**: Keep PRs focused and reasonably sized
   - Split large changes into multiple PRs if possible

4. **Commits**: Use conventional commit messages:
   ```
   feat: add EAMENA data source integration
   fix: correct coordinate parsing for negative longitudes
   docs: update API documentation for /sites endpoint
   refactor: simplify database query in sites.py
   test: add unit tests for coordinate validation
   ```

### Review Process

1. Maintainers will review your PR
2. Address any requested changes
3. Once approved, a maintainer will merge your PR

## Coding Standards

### Python

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use `loguru` for logging (not print statements)
- Document functions with docstrings

```python
def process_site(site_id: str, options: dict | None = None) -> Site:
    """
    Process a site record and return normalized data.

    Args:
        site_id: Unique identifier for the site
        options: Optional processing options

    Returns:
        Normalized Site object

    Raises:
        ValueError: If site_id is invalid
    """
    ...
```

### TypeScript/React

- Use TypeScript for all new code
- Use functional components with hooks
- Follow React best practices
- Use meaningful component and variable names

```typescript
interface SiteProps {
  id: string;
  name: string;
  coordinates: [number, number];
}

export function SiteMarker({ id, name, coordinates }: SiteProps) {
  // Component implementation
}
```

### SQL

- Use parameterized queries (never string interpolation)
- Add indexes for frequently queried columns
- Document complex queries with comments

### Git

- Keep commits atomic and focused
- Write meaningful commit messages
- Rebase feature branches before merging (if requested)

## Data Contributions

### Adding New Data Sources

1. **Research the source**:
   - Verify data quality and coverage
   - Check the license allows redistribution
   - Document the attribution requirements

2. **Create an ingester**:
   - Add a new file in `pipeline/ingesters/`
   - Follow the existing ingester patterns
   - Include proper error handling

3. **Add source configuration**:
   - Update `pipeline/sources/configs.py`
   - Include all required metadata

4. **Test thoroughly**:
   - Test with sample data first
   - Verify coordinate accuracy
   - Check for duplicates with existing data

5. **Update documentation**:
   - Add to `ATTRIBUTION.md`
   - Update `data_sources_research.md` if applicable

### Data Quality Standards

- Coordinates must be WGS84 (EPSG:4326)
- Names should be properly encoded (UTF-8)
- Dates should follow ISO 8601 where possible
- Include source attribution in records

## Questions?

- Open a GitHub Discussion for general questions
- Open an Issue for bugs or feature requests
- Check existing documentation first

Thank you for contributing to Ancient Nerds Map!
