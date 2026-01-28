#!/usr/bin/env python3
"""
Initialize the ANCIENT NERDS - Research Platform database.

This script creates all tables and populates the source_databases table
with known data sources. Works with direct PostgreSQL installation (no Docker needed).

Usage:
    python scripts/init_db.py [--drop]

Options:
    --drop  Drop existing tables before creating (USE WITH CAUTION!)
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import text

from pipeline.database import engine, Base, SessionLocal

# Try to import these - they may not exist in older schema
try:
    from pipeline.database import SourceDatabase
    from pipeline.config import DATA_SOURCES, SOURCE_PRIORITY
    HAS_LEGACY_SOURCES = True
except ImportError:
    HAS_LEGACY_SOURCES = False

# Import new unified models
try:
    from pipeline.database import UnifiedSite, SiteContentLink, SourceMeta
    HAS_UNIFIED_MODELS = True
except ImportError:
    HAS_UNIFIED_MODELS = False


def init_source_databases(session) -> int:
    """
    Populate the source_databases table with known data sources.

    Returns:
        Number of sources added or updated.
    """
    if not HAS_LEGACY_SOURCES:
        return 0

    count = 0

    for source_id, source_info in DATA_SOURCES.items():
        # Check if source already exists
        existing = session.query(SourceDatabase).filter_by(id=source_id).first()

        if existing:
            logger.info(f"Updating source: {source_id}")
            existing.name = source_info["name"]
            existing.description = source_info.get("description")
            existing.url = source_info.get("url")
            existing.api_endpoint = source_info.get("api_url") or source_info.get("download_url")
            existing.license = source_info.get("license")
            existing.attribution_template = source_info.get("attribution")
            existing.priority = SOURCE_PRIORITY.get(source_id, 50)
        else:
            logger.info(f"Adding source: {source_id}")
            source_db = SourceDatabase(
                id=source_id,
                name=source_info["name"],
                description=source_info.get("description"),
                url=source_info.get("url"),
                api_endpoint=source_info.get("api_url") or source_info.get("download_url"),
                license=source_info.get("license"),
                attribution_template=source_info.get("attribution"),
                priority=SOURCE_PRIORITY.get(source_id, 50),
            )
            session.add(source_db)

        count += 1

    session.commit()
    return count


def verify_postgis(session) -> bool:
    """Verify PostGIS extension is available."""
    try:
        result = session.execute(text("SELECT PostGIS_version();")).fetchone()
        logger.info(f"PostGIS version: {result[0]}")
        return True
    except Exception as e:
        logger.error(f"PostGIS not available: {e}")
        return False


def verify_extensions(session) -> dict:
    """Check which PostgreSQL extensions are installed."""
    result = session.execute(
        text("SELECT extname, extversion FROM pg_extension ORDER BY extname;")
    ).fetchall()

    extensions = {row[0]: row[1] for row in result}
    logger.info(f"Installed extensions: {list(extensions.keys())}")
    return extensions


def main():
    parser = argparse.ArgumentParser(description="Initialize the ANCIENT NERDS database")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before creating (USE WITH CAUTION!)",
    )
    parser.add_argument(
        "--skip-sources",
        action="store_true",
        help="Skip populating source databases",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("ANCIENT NERDS - Database Initialization")
    logger.info("=" * 60)

    session = SessionLocal()

    try:
        # Verify PostGIS
        logger.info("Checking PostGIS extension...")
        if not verify_postgis(session):
            logger.error("PostGIS is required but not installed!")
            logger.error("Install it with: sudo apt install postgresql-16-postgis-3")
            logger.error("Then run: CREATE EXTENSION postgis;")
            sys.exit(1)

        # Check extensions
        logger.info("Checking PostgreSQL extensions...")
        verify_extensions(session)

        # Drop tables if requested
        if args.drop:
            logger.warning("Dropping all existing tables...")
            confirm = input("Are you sure you want to drop all tables? (yes/no): ")
            if confirm.lower() == "yes":
                Base.metadata.drop_all(engine)
                logger.info("Tables dropped.")
            else:
                logger.info("Drop cancelled.")
                sys.exit(0)

        # Create tables
        logger.info("Creating database tables...")
        Base.metadata.create_all(engine)
        logger.info("Tables created successfully!")

        # List created tables
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"Tables in database: {tables}")

        # Populate source databases (legacy)
        if not args.skip_sources and HAS_LEGACY_SOURCES:
            try:
                logger.info("Populating source databases...")
                count = init_source_databases(session)
                logger.info(f"Added/updated {count} source databases.")
            except Exception as e:
                logger.warning(f"Could not populate legacy sources: {e}")

        logger.info("=" * 60)
        logger.info("Database initialization complete!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error during initialization: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
