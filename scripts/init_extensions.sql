-- ANCIENT NERDS - Research Platform - PostgreSQL Extensions Initialization
-- This script runs automatically when the Docker container starts

-- Enable PostGIS for geospatial support
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable PostGIS topology (optional, for complex geometries)
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable fuzzy string matching (for deduplication)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable unaccent for diacritic-insensitive search
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Enable full-text search dictionaries
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

-- Verify extensions are installed
SELECT extname, extversion FROM pg_extension ORDER BY extname;
