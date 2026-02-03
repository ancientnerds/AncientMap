"""
Unified Data Loader for Ancient Nerds Map.

Loads all raw data files from data/raw/ into the unified_sites PostgreSQL table.
Each source has a custom schema mapping to normalize fields.

Usage:
    python -m pipeline.unified_loader
    python -m pipeline.unified_loader --source pleiades
    python -m pipeline.unified_loader --status
"""

import csv
import html
import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path


def strip_html(text: str) -> str:
    """Strip HTML tags and decode entities from text."""
    if not text:
        return text
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities like &#39; &amp; etc
    text = html.unescape(text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

from loguru import logger
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from pipeline.database import SourceMeta, UnifiedSite, get_session
from pipeline.utils import (
    get_centroid as _get_centroid,
)
from pipeline.utils import (
    normalize_name,
)
from pipeline.utils import (
    parse_wkt_point as _parse_wkt_point,
)
from pipeline.utils.country_lookup import lookup_country

# =============================================================================
# GLOBAL DATE CUTOFFS - Applied to ALL sources
# =============================================================================
# These define the project scope: Ancient History
# Americas: Pre-Columbian (up to 1500 AD)
# Rest of World: Classical/Ancient (up to 500 AD)

DATE_CUTOFF_AMERICAS = 1500
DATE_CUTOFF_REST_OF_WORLD = 500

# Americas bounding box (longitude-based)
AMERICAS_LON_MIN = -170  # Western Alaska/Aleutians
AMERICAS_LON_MAX = -30   # Eastern Brazil


def passes_date_cutoff(record: dict) -> bool:
    """
    Check if record passes the GLOBAL regional date cutoff.

    Applied to ALL sources during loading. This defines project scope.

    Rules:
    - Americas (lon -170 to -30): Must be <= 1500 AD
    - Rest of World: Must be <= 500 AD
    - Records WITHOUT dates: INCLUDED (can't filter unknown)

    Args:
        record: Site record dict with period_start, period_end, lat, lon fields

    Returns:
        True if record should be included, False if it should be filtered out
    """
    # Get the relevant date (prefer period_end, fallback to period_start)
    date = record.get("period_end") or record.get("period_start")
    if date is None:
        return True  # No date = include (conservative)

    # Determine region by longitude
    lon = record.get("lon")
    if lon is None:
        return True  # No location = include

    is_americas = AMERICAS_LON_MIN <= lon <= AMERICAS_LON_MAX
    cutoff = DATE_CUTOFF_AMERICAS if is_americas else DATE_CUTOFF_REST_OF_WORLD

    return date <= cutoff


# Source configurations with metadata and parsing info
SOURCE_CONFIG = {
    # Priority 0: PRIMARY SOURCE - Ancient Nerds Original (manually curated)
    "ancient_nerds": {
        "name": "Ancient Nerds (Original)",
        "description": "Manually researched and curated archaeological sites",
        "color": "#FFD700",  # Gold - primary source
        "icon": "star",
        "category": "Primary",
        "file_pattern": "ancient_nerds_original.geojson",
        "format": "geojson_ancient_nerds",
        "license": "CC BY-SA 4.0",
        "attribution": "Ancient Nerds Research Team",
        "is_primary": True,
        "enabled_by_default": True,
        "priority": 0,  # Highest priority
    },

    # Priority 1: Core ancient world databases
    "pleiades": {
        "name": "Pleiades",
        "description": "Gazetteer of ancient places",
        "color": "#e74c3c",  # Red
        "icon": "landmark",
        "category": "Ancient World",
        "file_pattern": "pleiades-places.csv",
        "format": "csv",
        "license": "CC BY 3.0",
        "attribution": "Pleiades Project",
    },
    "dare": {
        "name": "DARE",
        "description": "Digital Atlas of the Roman Empire",
        "color": "#6c5ce7",  # Violet-blue (Roman purple)
        "icon": "empire",
        "category": "Ancient World",
        "file_pattern": "dare.json",
        "format": "geojson",
        "license": "CC BY-SA 3.0",
        "attribution": "DARE Project, Lund University",
    },
    "topostext": {
        "name": "ToposText",
        "description": "Ancient texts linked to places",
        "color": "#00bcd4",  # Cyan (different from teal coastlines)
        "icon": "scroll",
        "category": "Ancient World",
        "file_pattern": "topostext.json",
        "format": "json_places",
        "license": "CC BY-NC-SA 4.0",
        "attribution": "ToposText Project",
    },

    # Priority 2: Global databases
    "unesco": {
        "name": "UNESCO World Heritage",
        "description": "World Heritage cultural sites",
        "color": "#ffd700",  # Gold/Yellow (UNESCO)
        "icon": "globe",
        "category": "Global",
        "file_pattern": "unesco-whs.json",
        "format": "geojson",
        "license": "Public Domain",
        "attribution": "UNESCO World Heritage Centre",
    },
    "wikidata": {
        "name": "Wikidata",
        "description": "Archaeological sites from Wikidata",
        "color": "#9966ff",  # Purple (no greens - coastlines are teal)
        "icon": "database",
        "category": "Global",
        "file_pattern": "wikidata.json",
        "format": "wikidata",
        "license": "CC0",
        "attribution": "Wikidata",
    },
    # GeoNames removed - 13.4M records with no period data, would add noise
    # Other sources (Pleiades, DARE, Wikidata) already cover ancient sites with proper dating

    # Priority 3: Regional databases
    "osm_historic": {
        "name": "OpenStreetMap Historic",
        "description": "Historic sites from OpenStreetMap",
        "color": "#ff9800",  # Orange (no greens - coastlines are teal)
        "icon": "map",
        "category": "Global",
        "file_pattern": "osm_historic.json",
        "format": "osm",
        "license": "ODbL",
        "attribution": "OpenStreetMap contributors",
    },
    "historic_england": {
        "name": "Historic England",
        "description": "Scheduled monuments of England",
        "color": "#c0392b",  # Dark red
        "icon": "castle",
        "category": "Europe",
        "file_pattern": "historic_england.json",
        "format": "geojson",
        "license": "Open Government Licence",
        "attribution": "Historic England",
    },
    "ireland_nms": {
        "name": "Ireland National Monuments",
        "description": "Archaeological sites of Ireland",
        "color": "#ff6699",  # Pink (no greens - coastlines are teal)
        "icon": "celtic",
        "category": "Europe",
        "file_pattern": "ireland_nms.json",
        "format": "geojson",
        "license": "Open Data",
        "attribution": "National Monuments Service, Ireland",
    },
    "arachne": {
        "name": "Arachne",
        "description": "Archaeological objects database",
        "color": "#8e44ad",  # Dark purple
        "icon": "amphora",
        "category": "Europe",
        "file_pattern": "arachne.json",
        "format": "arachne",
        "license": "CC BY-NC-SA 3.0",
        "attribution": "DAI & CoDArchLab",
    },

    # Priority 4: Specialized databases
    "megalithic_portal": {
        "name": "Megalithic Portal",
        "description": "Megalithic and ancient sites",
        "color": "#9966cc",  # Amethyst Purple (stone)
        "icon": "stone",
        "category": "Europe",
        "file_pattern": "megalithic_portal.json",
        "format": "json_sites",
        "license": "Various",
        "attribution": "Megalithic Portal",
    },
    "sacred_sites": {
        "name": "Sacred Sites",
        "description": "Sacred and spiritual sites worldwide",
        "color": "#ff69b4",  # Hot Pink (sacred)
        "icon": "star",
        "category": "Global",
        "file_pattern": "sacred_sites.json",
        "format": "json_sites",
        "license": "Various",
        "attribution": "Sacred Sites Project",
    },
    "rock_art": {
        "name": "Rock Art",
        "description": "Rock art and petroglyphs",
        "color": "#e67e22",  # Dark orange
        "icon": "paint",
        "category": "Global",
        "file_pattern": "rock_art.json",
        "format": "json_sites",
        "license": "Various",
        "attribution": "Rock Art Database",
    },

    # Inscriptions & Texts
    "inscriptions_edh": {
        "name": "EDH Inscriptions",
        "description": "Latin inscriptions database",
        "color": "#5dade2",  # Light blue (inscriptions)
        "icon": "inscription",
        "category": "Inscriptions",
        "file_pattern": "inscriptions_edh.json",
        "format": "edh",
        "license": "CC BY-SA 3.0",
        "attribution": "Epigraphic Database Heidelberg",
    },

    # Maritime & Shipwrecks
    "shipwrecks_oxrep": {
        "name": "OXREP Shipwrecks",
        "description": "Ancient Mediterranean shipwrecks",
        "color": "#0066ff",  # Ocean Blue (shipwrecks)
        "icon": "ship",
        "category": "Maritime",
        "file_pattern": "shipwrecks_oxrep.json",
        "format": "json_sites",
        "license": "CC BY 4.0",
        "attribution": "Oxford Roman Economy Project",
    },

    # Numismatics
    "coins_nomisma": {
        "name": "Nomisma Coins",
        "description": "Ancient coin mints and finds",
        "color": "#d4af37",  # Gold
        "icon": "coin",
        "category": "Numismatics",
        "file_pattern": "coins_nomisma.json",
        "format": "nomisma",
        "license": "CC BY 4.0",
        "attribution": "Nomisma.org",
    },

    # Environmental
    "volcanic_holvol": {
        "name": "HolVol Volcanic",
        "description": "Holocene volcanic eruptions",
        "color": "#ff0000",  # Bright Red (volcanic)
        "icon": "volcano",
        "category": "Environmental",
        "file_pattern": "volcanic_holvol.json",
        "format": "json_sites",
        "license": "CC BY 4.0",
        "attribution": "HolVol Database",
    },
    "earth_impacts": {
        "name": "Earth Impact Database",
        "description": "Confirmed meteorite impact craters",
        "color": "#FF6B35",  # Orange-red (impact/explosion)
        "icon": "crater",
        "category": "Geological",
        "file_pattern": "earth_impacts.geojson",
        "format": "geojson_impacts",
        "license": "Public Domain",
        "attribution": "Earth Impact Database / Planetary and Space Science Centre",
        "priority": 26,
    },

    # NCEI Natural Hazards
    "ncei_earthquakes": {
        "name": "NCEI Significant Earthquakes",
        "description": "Significant earthquakes with impact data",
        "color": "#FF6347",  # Tomato red
        "icon": "shake",
        "category": "Geological",
        "file_pattern": "ncei_earthquakes.json",
        "format": "json_sites",
        "license": "Public Domain",
        "attribution": "NOAA NCEI Natural Hazards",
    },
    "ncei_tsunamis": {
        "name": "NCEI Tsunami Events",
        "description": "Tsunami source events",
        "color": "#1E90FF",  # Dodger blue (water)
        "icon": "wave",
        "category": "Geological",
        "file_pattern": "ncei_tsunamis.json",
        "format": "json_sites",
        "license": "Public Domain",
        "attribution": "NOAA NCEI Natural Hazards",
    },
    "ncei_tsunami_obs": {
        "name": "NCEI Tsunami Observations",
        "description": "Tsunami observation points",
        "color": "#4169E1",  # Royal blue
        "icon": "wave",
        "category": "Geological",
        "file_pattern": "ncei_tsunami_observations.json",
        "format": "json_sites",
        "license": "Public Domain",
        "attribution": "NOAA NCEI Natural Hazards",
    },
    "ncei_volcanoes": {
        "name": "NCEI Significant Volcanic Eruptions",
        "description": "Volcanic eruptions with impact data",
        "color": "#FF4500",  # Orange red
        "icon": "volcano",
        "category": "Geological",
        "file_pattern": "ncei_volcanoes.json",
        "format": "json_sites",
        "license": "Public Domain",
        "attribution": "NOAA NCEI Natural Hazards",
    },

    # 3D Models
    "models_sketchfab": {
        "name": "Sketchfab 3D Models",
        "description": "3D scans of archaeological sites",
        "color": "#1da1f2",  # Sketchfab blue
        "icon": "cube",
        "category": "3D Models",
        "file_pattern": "models_sketchfab.json",
        "format": "json_sites",
        "license": "Various",
        "attribution": "Sketchfab",
    },

    # Boundaries
    "boundaries_seshat": {
        "name": "Seshat Boundaries",
        "description": "Historical polity boundaries",
        "color": "#a29bfe",  # Light purple (boundaries)
        "icon": "boundary",
        "category": "Boundaries",
        "file_pattern": "boundaries_seshat.json",
        "format": "json_sites",
        "license": "CC BY-NC-SA 4.0",
        "attribution": "Seshat Databank",
    },

    # Americas
    "dinaa": {
        "name": "DINAA",
        "description": "North American archaeology",
        "color": "#cd853f",  # Peru/brown
        "icon": "teepee",
        "category": "Americas",
        "file_pattern": "dinaa.json",
        "format": "json_sites",
        "license": "CC BY 4.0",
        "attribution": "Digital Index of North American Archaeology",
    },

    # Middle East & Africa
    "eamena": {
        "name": "EAMENA",
        "description": "Endangered archaeology MENA region",
        "color": "#d35400",  # Dark orange
        "icon": "pyramid",
        "category": "Middle East",
        "file_pattern": "eamena.json",
        "format": "eamena",  # Custom parser for nested geometry
        "license": "CC BY 4.0",
        "attribution": "EAMENA Database",
    },

    # Open Context
    "open_context": {
        "name": "Open Context",
        "description": "Open archaeological data",
        "color": "#2980b9",  # Strong blue
        "icon": "dig",
        "category": "Global",
        "file_pattern": "open_context.json",
        "format": "json_sites",
        "license": "CC BY 4.0",
        "attribution": "Open Context",
    },

    # Museum Collections (content sources - may have limited geo data)
    "europeana": {
        "name": "Europeana",
        "description": "European cultural heritage",
        "color": "#0a72cc",  # Europeana blue
        "icon": "museum",
        "category": "Museums",
        "file_pattern": "europeana.json",
        "format": "json_sites",
        "license": "CC BY-SA 4.0",
        "attribution": "Europeana",
    },

    # Historical Maps (content source - bbox, not points)
    "david_rumsey": {
        "name": "David Rumsey Maps",
        "description": "Historical map collection",
        "color": "#8b4513",  # Saddle brown
        "icon": "map-old",
        "category": "Maps",
        "file_pattern": "david_rumsey.json",
        "format": "maps",  # Special handling - content source
        "license": "CC BY-NC-SA 3.0",
        "attribution": "David Rumsey Map Collection",
    },
}

# Site types to EXCLUDE from Wikidata and OSM (mostly medieval/modern)
# These are "historic" but not ancient (pre-1500 AD)
EXCLUDED_MODERN_TYPES = {
    # Religious buildings (mostly medieval/modern)
    "church",
    "cathedral",
    "chapel",
    "monastery",
    "abbey",
    "priory",
    "mosque",
    "synagogue",
    # Modern memorials
    "memorial",
    "cenotaph",
    "war_memorial",
    # Cemeteries (mostly modern)
    "cemetery",
    "grave_yard",
    "graveyard",
    # Industrial heritage
    "mine",
    "mill",
    "factory",
    "industrial",
    # Transportation
    "railway",
    "railway_station",
    "station",
    "bridge",  # Many modern bridges tagged historic
    # Misc modern
    "cannon",
    "tank",
    "aircraft",
    "ship",  # Modern ships as monuments
    "milestone",
    "boundary_stone",
    "wayside_cross",
    "wayside_shrine",
}

# Site types that ARE ancient (whitelist for when we want to be strict)
ANCIENT_SITE_TYPES = {
    "archaeological_site",
    "ruin",
    "ruins",
    "tomb",
    "tumulus",
    "barrow",
    "dolmen",
    "menhir",
    "stone_circle",
    "megalith",
    "fort",
    "hillfort",
    "castle",  # Medieval but often on ancient sites
    "temple",
    "settlement",
    "city",
    "amphitheatre",
    "theatre",
    "aqueduct",
    "roman",
    "celtic",
    "prehistoric",
    "neolithic",
    "bronze_age",
    "iron_age",
    "ancient",
}


def parse_wkt_point(wkt: str) -> tuple[float | None, float | None]:
    """Parse WKT Point string like 'Point(lon lat)' -> (lat, lon).

    Uses shared utility but swaps order to return (lat, lon) for compatibility.
    """
    lon, lat = _parse_wkt_point(wkt)
    if lon is not None and lat is not None:
        return lat, lon
    return None, None


def extract_id_from_uri(uri: str) -> str:
    """Extract ID from URI like 'http://wikidata.org/entity/Q123' -> 'Q123'."""
    if not uri:
        return ""
    return uri.rstrip("/").split("/")[-1]


def parse_year(value) -> int | None:
    """Parse year value, handling various formats."""
    if value is None or value == "":
        return None
    try:
        year = int(float(value))
        # Sanity check: years should be reasonable
        if -10000 <= year <= 2100:
            return year
    except (ValueError, TypeError):
        pass
    return None


def get_centroid(geometry: dict) -> tuple[float | None, float | None]:
    """Get centroid from GeoJSON geometry -> (lat, lon).

    Uses shared utility but swaps order to return (lat, lon) for compatibility.
    """
    lon, lat = _get_centroid(geometry)
    if lon is not None and lat is not None:
        return lat, lon
    return None, None


def normalize_site_type(site_type: str | None) -> str:
    """Normalize site type to lowercase for consistent filtering.

    Args:
        site_type: Raw site type string

    Returns:
        Normalized lowercase site type, or 'unknown' if empty
    """
    if not site_type:
        return "unknown"
    return site_type.lower().strip()


def enrich_country(record: dict) -> dict:
    """Add country field if missing, using coordinates for reverse geocoding.

    Args:
        record: Site record dict with lat/lon fields

    Returns:
        Record with country field populated (if it was missing and could be determined)
    """
    # Ensure country is a valid string or None (fix SQLAlchemy binding issues)
    existing_country = record.get("country")
    if existing_country is not None:
        if isinstance(existing_country, str) and existing_country.strip():
            record["country"] = existing_country.strip()[:100]
            return record
        else:
            # Invalid country value (empty string, non-string) - try enrichment
            record["country"] = None

    lat = record.get("lat")
    lon = record.get("lon")

    if lat is not None and lon is not None:
        try:
            country = lookup_country(lat, lon)
            if country and isinstance(country, str):
                record["country"] = country[:100]  # Limit to field size
        except Exception:
            pass  # Silently ignore lookup failures

    return record


class UnifiedLoader:
    """Loads all raw data sources into the unified_sites table."""

    def __init__(self, skip_backup: bool = False):
        self.raw_dir = Path("data/raw")
        self.stats = {}
        self.skip_backup = skip_backup

    def load_all(self, source_filter: str | None = None, batch_size: int = 5000, skip_loaded: bool = False):
        """Load all sources or a specific source."""
        # Create backup before any destructive operations
        if not self.skip_backup:
            from pipeline.backup import create_backup
            logger.info("Creating backup before loading sources...")
            backup = create_backup(include_db=True, include_contributions=True)
            if not backup.success:
                raise RuntimeError(f"Backup failed - aborting: {backup.error}")
            logger.info(f"Backup created: {backup.backup_id}")

        sources_to_load = [source_filter] if source_filter else list(SOURCE_CONFIG.keys())

        with get_session() as session:
            # Initialize source metadata
            self._init_source_meta(session)

            # Get existing record counts if skip_loaded is enabled
            existing_counts = {}
            if skip_loaded:
                result = session.execute(text(
                    "SELECT source_id, COUNT(*) as count FROM unified_sites GROUP BY source_id"
                ))
                existing_counts = {row.source_id: row.count for row in result}

            for source_id in sources_to_load:
                if source_id not in SOURCE_CONFIG:
                    logger.warning(f"Unknown source: {source_id}")
                    continue

                # Skip if already loaded
                if skip_loaded and source_id in existing_counts and existing_counts[source_id] > 0:
                    logger.info(f"Skipping {source_id} - already has {existing_counts[source_id]:,} records")
                    self.stats[source_id] = {"success": True, "count": existing_counts[source_id], "skipped": True}
                    continue

                config = SOURCE_CONFIG[source_id]
                logger.info(f"\n{'='*60}")
                logger.info(f"Loading {config['name']} ({source_id})")
                logger.info(f"{'='*60}")

                try:
                    count = self._load_source(session, source_id, config, batch_size)
                    self.stats[source_id] = {"success": True, "count": count}

                    # Update source meta record count
                    session.execute(
                        text("UPDATE source_meta SET record_count = :count, last_loaded = NOW() WHERE id = :id"),
                        {"count": count, "id": source_id}
                    )
                    session.commit()

                    logger.info(f"Loaded {count:,} records from {source_id}")

                except Exception as e:
                    logger.error(f"Failed to load {source_id}: {e}")
                    self.stats[source_id] = {"success": False, "error": str(e)}
                    session.rollback()

        self._print_summary()

    def _init_source_meta(self, session):
        """Initialize source metadata table."""
        for source_id, config in SOURCE_CONFIG.items():
            # Determine if this is the primary source
            is_primary = config.get("is_primary", False)
            enabled_by_default = config.get("enabled_by_default", False)
            priority = config.get("priority", list(SOURCE_CONFIG.keys()).index(source_id) + 1)

            stmt = insert(SourceMeta).values(
                id=source_id,
                name=config["name"],
                description=config.get("description"),
                color=config.get("color"),
                icon=config.get("icon"),
                category=config.get("category"),
                license=config.get("license"),
                attribution=config.get("attribution"),
                enabled=True,
                is_primary=is_primary,
                enabled_by_default=enabled_by_default,
                priority=priority,
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": config["name"],
                    "description": config.get("description"),
                    "color": config.get("color"),
                    "icon": config.get("icon"),
                    "category": config.get("category"),
                    "is_primary": is_primary,
                    "enabled_by_default": enabled_by_default,
                    "priority": priority,
                }
            )
            session.execute(stmt)
        session.commit()

    def _load_source(self, session, source_id: str, config: dict, batch_size: int) -> int:
        """Load a single source into unified_sites."""
        source_dir = self.raw_dir / source_id
        if not source_dir.exists():
            logger.warning(f"No data directory for {source_id}")
            return 0

        # Find data file
        pattern = config.get("file_pattern", "*.json")
        files = list(source_dir.glob(pattern))
        if not files:
            logger.warning(f"No files matching {pattern} in {source_dir}")
            return 0

        data_file = files[0]
        logger.info(f"Reading {data_file}")

        # Parse based on format
        format_type = config.get("format", "json_sites")
        parser = getattr(self, f"_parse_{format_type}", None)
        if not parser:
            logger.warning(f"No parser for format: {format_type}")
            return 0

        # Delete existing records for this source
        session.execute(
            text("DELETE FROM unified_sites WHERE source_id = :sid"),
            {"sid": source_id}
        )

        # Load records in batches
        batch = []
        total = 0
        enriched_count = 0
        filtered_by_date = 0

        for record in parser(data_file, source_id, config):
            if record:
                # Normalize site_type to lowercase for consistent filtering
                if record.get("site_type"):
                    record["site_type"] = normalize_site_type(record["site_type"])

                # Enrich country field via reverse geocoding if missing
                if not record.get("country"):
                    original_country = record.get("country")
                    record = enrich_country(record)
                    if record.get("country") and record.get("country") != original_country:
                        enriched_count += 1

                # GLOBAL DATE CUTOFF - Applied to ALL sources
                # This defines project scope: Ancient History Map
                # Americas: <= 1500 AD, Rest of World: <= 500 AD
                if not passes_date_cutoff(record):
                    filtered_by_date += 1
                    continue  # Skip this record entirely

                batch.append(record)

            if len(batch) >= batch_size:
                self._insert_batch(session, batch)
                total += len(batch)
                logger.info(f"  Inserted {total:,} records...")
                batch = []

        # Insert remaining
        if batch:
            self._insert_batch(session, batch)
            total += len(batch)

        if enriched_count > 0:
            logger.info(f"  Enriched {enriched_count:,} records with country data")

        if filtered_by_date > 0:
            logger.info(f"  Filtered {filtered_by_date:,} records by date cutoff (>500 AD Old World, >1500 AD Americas)")

        session.commit()
        return total

    def _insert_batch(self, session, records: list[dict]):
        """Insert a batch of records using bulk insert."""
        if not records:
            return

        # Sanitize records to fix SQLAlchemy binding issues
        # All records must have the same keys for bulk insert
        # Explicitly set missing optional fields to None
        optional_string_fields = ["country", "description", "thumbnail_url", "source_url", "period_name"]
        sanitized = []
        for record in records:
            clean = dict(record)  # Copy the record
            for field in optional_string_fields:
                value = clean.get(field)
                # Convert empty/invalid strings to None, and ensure field exists
                if value is not None and isinstance(value, str) and value.strip():
                    clean[field] = value.strip()
                else:
                    clean[field] = None  # Explicitly set to None (including missing fields)
            sanitized.append(clean)

        stmt = insert(UnifiedSite).values(sanitized)
        stmt = stmt.on_conflict_do_nothing(index_elements=["source_id", "source_record_id"])
        session.execute(stmt)

    # ===== PARSERS FOR EACH FORMAT =====

    def _parse_csv(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse Pleiades CSV format."""
        # Period cutoff: include ancient + pre-Columbian (up to 1500 AD)
        PERIOD_CUTOFF = 1500

        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lat = parse_year(row.get("reprLat"))  # Actually float, not year
                lon = parse_year(row.get("reprLong"))

                if lat is None or lon is None:
                    continue

                try:
                    lat = float(row.get("reprLat", 0))
                    lon = float(row.get("reprLong", 0))
                except (ValueError, TypeError):
                    continue

                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue

                name = row.get("title", "").strip()
                if not name:
                    continue

                # Filter by period: only include sites ending <= 1500 AD
                max_date = parse_year(row.get("maxDate"))
                if max_date is not None and max_date > PERIOD_CUTOFF:
                    continue  # Skip medieval/modern sites

                yield {
                    "source_id": source_id,
                    "source_record_id": row.get("id", row.get("uid", "")),
                    "name": name[:500],
                    "name_normalized": normalize_name(name)[:500],
                    "lat": lat,
                    "lon": lon,
                    "site_type": self._normalize_type(row.get("featureTypes", "")),
                    "period_start": parse_year(row.get("minDate")),
                    "period_end": parse_year(row.get("maxDate")),
                    "period_name": row.get("timePeriods", "")[:100] if row.get("timePeriods") else None,
                    "description": row.get("description", "")[:2000] if row.get("description") else None,
                    "source_url": f"https://pleiades.stoa.org{row.get('path', '')}",
                    "raw_data": {
                        "tags": row.get("tags"),
                        "featureTypes": row.get("featureTypes"),
                        "creators": row.get("creators"),
                    },
                }

    def _parse_geojson(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse GeoJSON FeatureCollection."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])

        for feature in features:
            props = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}

            lat, lon = get_centroid(geometry)
            if lat is None or lon is None:
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            # Extract name based on source
            if source_id == "dare":
                name = props.get("name") or props.get("ancient", "")
                record_id = props.get("id", "")
                site_type = self._normalize_type(props.get("type", ""))
                source_url = f"https://dare.ht.lu.se/places/{record_id}"
            elif source_id == "unesco":
                name = props.get("name_en") or props.get("full_name", "")
                record_id = str(props.get("id_no", props.get("OBJECTID", "")))
                site_type = "heritage_site"
                source_url = props.get("hyperlink", "")
            elif source_id == "historic_england":
                name = props.get("Name", "")
                record_id = str(props.get("ListEntry", props.get("OBJECTID", "")))
                site_type = "scheduled_monument"
                source_url = props.get("hyperlink", f"https://historicengland.org.uk/listing/the-list/list-entry/{record_id}")
            elif source_id == "ireland_nms":
                name = props.get("MONUMENT_CLASS", props.get("TOWNLAND", ""))
                record_id = props.get("ENTITY_ID", props.get("SMRS", ""))
                site_type = self._normalize_type(props.get("MONUMENT_CLASS", ""))
                source_url = props.get("WEBSITE_LINK", "")
            else:
                name = props.get("name", props.get("title", "Unknown"))
                record_id = str(props.get("id", props.get("OBJECTID", "")))
                site_type = self._normalize_type(props.get("type", ""))
                source_url = props.get("hyperlink", props.get("url", ""))

            if not name:
                continue

            yield {
                "source_id": source_id,
                "source_record_id": str(record_id),
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": site_type,
                "country": props.get("country", props.get("COUNTY", ""))[:100] if props.get("country") or props.get("COUNTY") else None,
                "description": props.get("description", props.get("short_description_en", ""))[:2000] if props.get("description") or props.get("short_description_en") else None,
                "source_url": source_url[:500] if source_url else None,
                "raw_data": {k: v for k, v in props.items() if k not in ("name", "description")},
            }

    def _parse_geojson_impacts(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse Earth Impact Database GeoJSON format."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Parsing {len(features)} impact craters")

        for idx, feature in enumerate(features):
            props = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}

            lat, lon = get_centroid(geometry)
            if lat is None or lon is None:
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            name = props.get("crater_name", "").strip()
            if not name:
                continue

            # Build location string
            state = props.get("state", "")
            country = props.get("country", "")
            location = f"{state}, {country}" if state else country

            # Build description with crater details
            diameter = props.get("diameter_km")
            age = props.get("age_millions_years_ago", "")
            target_rock = props.get("target_rock", "")
            bolid_type = props.get("bolid_type", "")

            desc_parts = []
            if diameter:
                desc_parts.append(f"Diameter: {diameter} km")
            if age:
                desc_parts.append(f"Age: {age} million years ago")
            if target_rock:
                desc_parts.append(f"Target rock: {target_rock}")
            if bolid_type:
                desc_parts.append(f"Meteorite type: {bolid_type}")
            description = "; ".join(desc_parts) if desc_parts else None

            yield {
                "source_id": source_id,
                "source_record_id": f"impact_{idx:04d}",
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": "impact_crater",
                "country": location[:100] if location else None,
                "description": description[:2000] if description else None,
                "source_url": props.get("url", "")[:500] if props.get("url") else None,
                # No period_start/period_end - geological timescales don't fit archaeological filtering
                "raw_data": {
                    "diameter_km": diameter,
                    "age_millions_years_ago": age,
                    "target_rock": target_rock,
                    "bolid_type": bolid_type,
                    "exposed": props.get("exposed"),
                    "drilled": props.get("drilled"),
                },
            }

    def _parse_geojson_ancient_nerds(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse Ancient Nerds original GeoJSON format with rich descriptions."""
        # Period mapping from text to numeric years
        PERIOD_MAPPING = {
            "before 4500 BC": (-10000, -4500),
            "4500 - 3000 BC": (-4500, -3000),
            "3000 - 1500 BC": (-3000, -1500),
            "1500 - 500 BC": (-1500, -500),
            "500 BC - 1 AD": (-500, 1),
            "1 - 500 AD": (1, 500),
            "500 - 1000 AD": (500, 1000),
            "1000 - 1500 AD": (1000, 1500),
        }

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Parsing {len(features)} Ancient Nerds original sites")

        for idx, feature in enumerate(features):
            props = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}

            lat, lon = get_centroid(geometry)
            if lat is None or lon is None:
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            # Extract fields from the original schema
            name = props.get("Title", "").strip()
            if not name:
                continue

            # Generate stable ID
            record_id = f"an_{idx:05d}"

            # Get rich description (the key feature!)
            description = props.get("Description", "")

            # Get period and parse to years
            period_name = props.get("Period", "")
            period_start, period_end = PERIOD_MAPPING.get(period_name, (None, None))

            # Get category/site type - preserve original compound category names
            category = props.get("Category", "")
            site_type = self._clean_ancient_nerds_category(category)

            # Get location (country)
            country = props.get("Location", "")

            # Get source URL (Wikipedia)
            source_url = props.get("Source", "")

            # Get image URL - store in raw_data
            image_url = props.get("Images", "")

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": site_type,
                "period_start": period_start,
                "period_end": period_end,
                "period_name": period_name[:100] if period_name else None,
                "country": country[:100] if country else None,
                "description": description[:5000] if description else None,  # Allow longer descriptions
                "thumbnail_url": image_url[:500] if image_url else None,
                "source_url": source_url[:500] if source_url else None,
                "raw_data": {
                    "title": name,
                    "description": description,
                    "category": category,
                    "category_multi": props.get("Category (multi)", ""),
                    "location": country,
                    "year": props.get("Year", ""),
                    "period": period_name,
                    "source": source_url,
                    "image": image_url,
                },
            }

    def _parse_wikidata(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse Wikidata SPARQL results."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        results = data.get("results", [])
        seen_ids = set()  # Dedupe

        for item in results:
            item_uri = item.get("item", {}).get("value", "")
            record_id = extract_id_from_uri(item_uri)

            if not record_id or record_id in seen_ids:
                continue
            seen_ids.add(record_id)

            coord = item.get("coord", {}).get("value", "")
            lat, lon = parse_wkt_point(coord)

            if lat is None or lon is None:
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            name = item.get("itemLabel", {}).get("value", "")
            if not name:
                continue

            # Get site type and filter out modern types
            site_type = self._normalize_type(item.get("_type_name", ""))
            if site_type and site_type.lower() in EXCLUDED_MODERN_TYPES:
                continue  # Skip modern heritage sites

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": site_type,
                "country": item.get("countryLabel", {}).get("value", "")[:100] if item.get("countryLabel") else None,
                "description": item.get("itemDescription", {}).get("value", "")[:2000] if item.get("itemDescription") else None,
                "source_url": item_uri,
                "raw_data": {"wikidata_id": record_id},
            }

    def _parse_osm(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse OpenStreetMap historic elements."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        elements = data.get("elements", [])

        for elem in elements:
            lat = elem.get("lat")
            lon = elem.get("lon")

            # For ways/relations, try center
            if lat is None and "center" in elem:
                lat = elem["center"].get("lat")
                lon = elem["center"].get("lon")

            if lat is None or lon is None:
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            tags = elem.get("tags", {})
            name = tags.get("name", tags.get("name:en", ""))
            if not name:
                continue

            record_id = f"{elem.get('type', 'node')}_{elem.get('id', '')}"
            historic_type = tags.get("historic", tags.get("historic_type", ""))
            site_type = self._normalize_type(historic_type)

            # Filter out modern heritage types (churches, memorials, etc.)
            if site_type and site_type.lower() in EXCLUDED_MODERN_TYPES:
                continue  # Skip modern historic sites

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": site_type,
                "description": tags.get("description", "")[:2000] if tags.get("description") else None,
                "source_url": f"https://www.openstreetmap.org/{elem.get('type', 'node')}/{elem.get('id', '')}",
                "raw_data": {
                    "osm_type": elem.get("type"),
                    "osm_id": elem.get("id"),
                    "wikidata": tags.get("wikidata"),
                    "wikipedia": tags.get("wikipedia"),
                    "historic": historic_type,
                },
            }

    def _parse_json_places(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse ToposText places JSON."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        places = data.get("places", [])

        for place in places:
            lat = place.get("lat")
            lon = place.get("lon")

            if lat is None or lon is None:
                # Try geometry
                geom = place.get("geometry") or {}
                if geom:
                    lat, lon = get_centroid(geom)

            if lat is None or lon is None:
                continue

            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            name = place.get("name", "")
            if not name:
                continue

            # Extract ToposText ID from URL
            tt_url = place.get("ToposText", "")
            record_id = tt_url.split("/")[-1] if tt_url else place.get("id", str(uuid.uuid4())[:8])

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": self._normalize_type(place.get("type", "")),
                "country": place.get("country", place.get("region", ""))[:100] if place.get("country") or place.get("region") else None,
                "description": place.get("description", "")[:2000] if place.get("description") else None,
                "source_url": tt_url or f"https://topostext.org/place/{record_id}",
                "raw_data": {
                    "pleiades": place.get("Pleiades"),
                    "wikidata": place.get("Wikidata"),
                    "references": place.get("references"),
                    "greek": place.get("Greek"),
                },
            }

    def _parse_json_sites(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse generic JSON sites format."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Find the array of sites (could be under different keys)
        sites = []
        for key in ["sites", "records", "items", "features", "results", "objects", "inscriptions",
                    "models", "boundaries", "eruptions", "shipwrecks", "wrecks",
                    "earthquakes", "tsunamis", "volcanoes", "observations"]:
            if key in data:
                sites = data[key]
                break

        if not sites and isinstance(data, list):
            sites = data

        for site in sites:
            # Handle GeoJSON features: merge properties into site for easier access
            if "properties" in site and isinstance(site.get("properties"), dict):
                props = site["properties"]
                # Merge properties but keep geometry at top level
                site = {**props, "geometry": site.get("geometry")}

            lat = site.get("lat", site.get("latitude"))
            lon = site.get("lon", site.get("lng", site.get("longitude")))

            # Try geometry
            if lat is None or lon is None:
                geom = site.get("geometry") or {}
                if geom:
                    lat, lon = get_centroid(geom)

            # Try coordinates array
            if lat is None or lon is None:
                coords = site.get("coordinates", site.get("coords", []))
                if coords and len(coords) >= 2:
                    lat, lon = coords[1], coords[0]  # GeoJSON order

            if lat is None or lon is None:
                continue

            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            name = (site.get("name") or site.get("title") or site.get("label") or
                    site.get("volcano_name") or site.get("site_name") or
                    site.get("location_name") or "")
            if not name:
                continue

            # Period filtering for sources with date data (cutoff: 1500 AD for ancient + pre-Columbian)
            PERIOD_CUTOFF = 1500

            if source_id == "shipwrecks_oxrep":
                date_end = parse_year(site.get("date_sunk_end"))
                if date_end is not None and date_end > PERIOD_CUTOFF:
                    continue  # Skip post-ancient shipwrecks

            if source_id == "volcanic_holvol":
                year = parse_year(site.get("year"))
                if year is not None and year > PERIOD_CUTOFF:
                    continue  # Skip modern eruptions

            record_id = site.get("id") or site.get("_id") or site.get("uid") or str(uuid.uuid4())[:8]
            record_id = str(record_id)

            # Determine site_type - special handling for NCEI sources that don't have type in records
            raw_type = site.get("type", site.get("site_type", site.get("category", "")))
            if not raw_type:
                # Derive type from source_id for NCEI sources
                ncei_type_map = {
                    "ncei_earthquakes": "earthquake",
                    "ncei_tsunamis": "tsunami",
                    "ncei_tsunami_obs": "tsunami_observation",
                    "ncei_volcanoes": "volcanic_eruption",
                }
                raw_type = ncei_type_map.get(source_id, "")
            site_type = self._normalize_type(raw_type)

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": site_type,
                "period_start": self._derive_period_start(source_id, site),
                "period_end": parse_year(site.get("date_end", site.get("period_end", site.get("year_end")))),
                "country": site.get("country", site.get("region", ""))[:100] if site.get("country") or site.get("region") else None,
                "description": self._build_description(site),
                "source_url": site.get("url", site.get("source_url", site.get("link", "")))[:500] if site.get("url") or site.get("source_url") or site.get("link") else None,
                "thumbnail_url": self._extract_thumbnail(site),
                "raw_data": {k: v for k, v in site.items() if k not in ("name", "lat", "lon", "description")},
            }

    def _parse_arachne(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse Arachne results."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        results = data.get("results", [])

        for item in results:
            # Get location from places array
            places = item.get("places", [])
            if not places:
                continue

            loc = places[0].get("location", {})
            lat = loc.get("lat")
            lon = loc.get("lon")

            if lat is None or lon is None:
                continue

            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            name = item.get("title", "")
            if not name:
                continue

            record_id = str(item.get("entityId", ""))

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": self._normalize_type(item.get("type", "")),
                "country": places[0].get("country", "")[:100] if places[0].get("country") else None,
                "description": item.get("subtitle", "")[:2000] if item.get("subtitle") else None,
                "source_url": item.get("@id", f"https://arachne.dainst.org/entity/{record_id}"),
                "thumbnail_url": f"https://arachne.dainst.org/data/image/thumb/{item.get('thumbnailId')}" if item.get("thumbnailId") else None,
                "raw_data": {
                    "entity_id": record_id,
                    "type": item.get("type"),
                    "locality": places[0].get("locality"),
                },
            }

    def _parse_eamena(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse EAMENA (Endangered Archaeology of MENA) data with nested geometry."""
        import ast

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        results = data.get("results", [])

        for item in results:
            record_id = item.get("resourceinstanceid", "")
            if not record_id:
                continue

            name = item.get("displayname", "")
            if not name:
                continue

            # Extract geometry from nested resource structure
            resource = item.get("resource", {})
            geometry_list = resource.get("Geometry", [])

            lat, lon = None, None
            for geom_entry in geometry_list:
                geom_expr = geom_entry.get("Geometric Place Expression", {})
                geom_str = geom_expr.get("@value", "")

                if geom_str:
                    try:
                        # Parse the stringified GeoJSON
                        geom_data = ast.literal_eval(geom_str)
                        features = geom_data.get("features", [])
                        if features:
                            geometry = features[0].get("geometry", {})
                            lat, lon = get_centroid(geometry)
                            if lat is not None:
                                break
                    except (ValueError, SyntaxError):
                        continue

            if lat is None or lon is None:
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            # Extract additional info from resource
            description = item.get("displaydescription", "")

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": "archaeological_site",
                "description": description[:2000] if description else None,
                "source_url": f"https://database.eamena.org/report/{record_id}",
                "raw_data": {"eamena_id": name},
            }

    def _parse_nomisma(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse Nomisma coin data (mints and finds)."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Process mints (ancient coin minting locations)
        for mint in data.get("mints", []):
            lat = mint.get("lat")
            lon = mint.get("lon")

            if lat is None or lon is None:
                continue

            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            name = mint.get("name", "")
            if not name:
                continue

            yield {
                "source_id": source_id,
                "source_record_id": mint.get("id", ""),
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": "mint",
                "period_start": parse_year(mint.get("start_date")),
                "period_end": parse_year(mint.get("end_date")),
                "description": mint.get("definition", "")[:2000] if mint.get("definition") else None,
                "source_url": mint.get("uri", ""),
                "raw_data": {
                    "type": "mint",
                    "broader": mint.get("broader"),
                },
            }

        # Process finds (coin find locations)
        for find in data.get("finds", []):
            lat = find.get("lat")
            lon = find.get("lon")

            if lat is None or lon is None:
                continue

            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            # Finds don't have names, create from ID
            record_id = find.get("id", "")
            name = f"Coin find {record_id.split('_')[-1][:8]}" if record_id else "Coin find"

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": "coin_find",
                "period_start": parse_year(find.get("start_date")),
                "period_end": parse_year(find.get("end_date")),
                "source_url": find.get("uri", ""),
                "raw_data": {
                    "type": "find",
                    "denomination_uri": find.get("denomination_uri"),
                    "material_uri": find.get("material_uri"),
                    "mint_uri": find.get("mint_uri"),
                },
            }

    def _parse_edh(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse Epigraphic Database Heidelberg inscriptions."""
        # Period cutoff: include ancient + pre-Columbian (up to 1500 AD)
        PERIOD_CUTOFF = 1500

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        inscriptions = data.get("inscriptions", [])

        for insc in inscriptions:
            lat = insc.get("lat")
            lon = insc.get("lon")

            if lat is None or lon is None:
                continue

            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                continue

            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            # Filter by period: only include inscriptions dated <= 1500 AD
            date_end = parse_year(insc.get("date_end"))
            if date_end is not None and date_end > PERIOD_CUTOFF:
                continue  # Skip post-ancient inscriptions

            name = insc.get("ancient_place") or insc.get("modern_place") or f"Inscription {insc.get('edh_id', '')}"
            record_id = insc.get("edh_id", insc.get("id", ""))

            yield {
                "source_id": source_id,
                "source_record_id": record_id,
                "name": name[:500],
                "name_normalized": normalize_name(name)[:500],
                "lat": lat,
                "lon": lon,
                "site_type": "inscription",
                "period_start": parse_year(insc.get("date_start")),
                "period_end": parse_year(insc.get("date_end")),
                "country": insc.get("country", "")[:100] if insc.get("country") else None,
                "description": f"Type: {insc.get('inscription_type', '')}; Material: {insc.get('material', '')}; Find spot: {insc.get('find_spot', '')}"[:2000],
                "source_url": insc.get("source_url", f"https://edh.ub.uni-heidelberg.de/edh/inschrift/{record_id}"),
                "raw_data": {
                    "edh_id": record_id,
                    "inscription_type": insc.get("inscription_type"),
                    "material": insc.get("material"),
                    "object_type": insc.get("object_type"),
                    "province": insc.get("province"),
                    "pleiades_id": insc.get("pleiades_id"),
                },
            }

    def _parse_geonames_tsv(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse GeoNames TSV format."""
        # GeoNames columns: geonameid, name, asciiname, alternatenames, latitude, longitude,
        # feature class, feature code, country code, cc2, admin1, admin2, admin3, admin4,
        # population, elevation, dem, timezone, modification date

        with open(path, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) < 8:
                    continue

                try:
                    lat = float(parts[4])
                    lon = float(parts[5])
                except (ValueError, IndexError):
                    continue

                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue

                name = parts[1] or parts[2]  # name or asciiname
                if not name:
                    continue

                record_id = parts[0]
                feature_class = parts[6] if len(parts) > 6 else ""
                feature_code = parts[7] if len(parts) > 7 else ""
                country = parts[8] if len(parts) > 8 else ""

                # Map GeoNames feature codes to site types
                site_type = self._map_geonames_type(feature_class, feature_code)

                yield {
                    "source_id": source_id,
                    "source_record_id": record_id,
                    "name": name[:500],
                    "name_normalized": normalize_name(name)[:500],
                    "lat": lat,
                    "lon": lon,
                    "site_type": site_type,
                    "country": country[:100] if country else None,
                    "source_url": f"https://www.geonames.org/{record_id}",
                    "raw_data": {
                        "feature_class": feature_class,
                        "feature_code": feature_code,
                        "alternate_names": parts[3] if len(parts) > 3 else None,
                    },
                }

    def _parse_maps(self, path: Path, source_id: str, config: dict) -> Iterator[dict]:
        """Parse David Rumsey historical maps (content source - skip for sites)."""
        # Historical maps don't represent sites - they're content to link TO sites
        # Return empty iterator; maps will be used in content_linker.py
        logger.info("David Rumsey maps will be processed in content_linker.py, not as sites")
        return iter([])

    def _map_geonames_type(self, feature_class: str, feature_code: str) -> str:
        """Map GeoNames feature class/code to site type."""
        # S = spot, building, farm; H = stream, lake; T = mountain, hill; P = city, village
        # L = parks, area; A = country, state; R = road, railroad; U = undersea; V = forest, heath

        code_map = {
            "HSTS": "historic_site",
            "RUIN": "ruin",
            "CSTL": "castle",
            "FRT": "fort",
            "MNMT": "monument",
            "CH": "church",
            "MSTY": "monastery",
            "TMPL": "temple",
            "PYR": "pyramid",
            "TOWR": "tower",
            "BLDG": "building",
            "PAL": "palace",
            "ANS": "ancient_site",
            "CAVE": "cave",
            "CMTY": "cemetery",
        }

        if feature_code in code_map:
            return code_map[feature_code]

        class_map = {
            "S": "structure",
            "P": "settlement",
            "T": "natural_feature",
            "H": "water_feature",
            "L": "area",
        }

        return class_map.get(feature_class, "place")

    def _extract_thumbnail(self, site: dict) -> str | None:
        """
        Extract thumbnail URL from site dict, checking multiple locations.

        Ingesters store images in various places:
        - Top level: thumbnail, thumbnail_url, image
        - In raw_data: thumbnail, primary_image, image_url, etc.
        """
        # Check top-level fields first
        for field in ['thumbnail', 'thumbnail_url', 'image', 'primary_image']:
            if site.get(field):
                url = str(site[field])[:500]
                if url.startswith('http'):
                    return url

        # Check inside raw_data
        raw_data = site.get('raw_data', {})
        if raw_data and isinstance(raw_data, dict):
            for field in ['thumbnail', 'thumbnail_url', 'primary_image', 'image', 'image_url', 'depiction']:
                if raw_data.get(field):
                    url = str(raw_data[field])[:500]
                    if url.startswith('http'):
                        return url

        return None

    def _clean_ancient_nerds_category(self, category: str) -> str:
        """Clean Ancient Nerds category, preserving original compound names."""
        if not category:
            return "Unknown"

        # Strip whitespace and trailing commas
        category = category.strip().rstrip(",")

        # Fix known typos
        typo_fixes = {
            "City/town/settlemen": "City/town/settlement",
            "Rock Art": "Rock art",
            "Cave structures": "Cave Structures",
            "4th ml. BC": "Unknown",
        }

        if category in typo_fixes:
            category = typo_fixes[category]

        return category if category else "Unknown"

    def _normalize_type(self, raw_type: str) -> str:
        """Normalize site type to standard vocabulary."""
        if not raw_type:
            return "site"

        raw_type = raw_type.lower().strip()

        # Map to standard types
        type_map = {
            # Settlements
            "city": "settlement",
            "town": "settlement",
            "village": "settlement",
            "settlement": "settlement",
            "polis": "settlement",
            "urban": "settlement",
            "civitas": "settlement",
            "oppidum": "settlement",
            "vicus": "settlement",

            # Religious
            "temple": "temple",
            "sanctuary": "temple",
            "shrine": "temple",
            "oracle": "temple",
            "church": "church",
            "monastery": "monastery",
            "cathedral": "church",
            "chapel": "church",

            # Fortifications
            "fort": "fort",
            "fortress": "fort",
            "castle": "castle",
            "fortification": "fort",
            "hillfort": "fort",
            "castra": "fort",

            # Tombs & Burial
            "tomb": "tomb",
            "burial": "tomb",
            "cemetery": "cemetery",
            "necropolis": "cemetery",
            "mausoleum": "tomb",
            "tumulus": "tomb",
            "barrow": "tomb",
            "cairn": "tomb",

            # Monuments
            "monument": "monument",
            "memorial": "monument",
            "stele": "monument",
            "obelisk": "monument",
            "statue": "monument",
            "standing_stone": "monument",
            "megalith": "monument",
            "stone_circle": "monument",
            "dolmen": "monument",
            "menhir": "monument",

            # Infrastructure
            "road": "road",
            "bridge": "bridge",
            "aqueduct": "aqueduct",
            "wall": "wall",
            "gate": "gate",
            "harbor": "port",
            "port": "port",

            # Other built structures
            "theater": "theater",
            "theatre": "theater",
            "amphitheater": "amphitheater",
            "amphitheatre": "amphitheater",
            "stadium": "stadium",
            "circus": "stadium",
            "bath": "bath",
            "thermae": "bath",
            "forum": "forum",
            "agora": "forum",
            "palace": "palace",
            "villa": "villa",

            # Natural features
            "mountain": "natural_feature",
            "river": "natural_feature",
            "island": "natural_feature",
            "lake": "natural_feature",
            "spring": "natural_feature",
            "cave": "cave",

            # Archaeological categories
            "archaeological_site": "archaeological_site",
            "excavation": "archaeological_site",
            "ruin": "ruin",
            "ruins": "ruin",

            # Inscriptions & Art
            "inscription": "inscription",
            "rock_art": "rock_art",
            "petroglyph": "rock_art",

            # Maritime
            "shipwreck": "shipwreck",
            "wreck": "shipwreck",

            # Environmental / Geological
            "volcano": "volcano",
            "eruption": "volcano",
            "volcanic_eruption": "volcano",
            "earthquake": "earthquake",
            "tsunami": "tsunami",
            "tsunami_observation": "tsunami",
            "impact_crater": "impact_crater",
            "crater": "impact_crater",
            "impact": "impact_crater",
        }

        for key, value in type_map.items():
            if key in raw_type:
                return value

        return "site"

    def _build_description(self, site: dict) -> str | None:
        """Build description from various possible fields in the site data."""
        # Primary description fields
        desc = site.get("description") or site.get("comments")

        if desc:
            return strip_html(desc)[:2000]

        # For NCEI sources, combine available description fields
        parts = []

        # Deaths description
        if site.get("deaths_description"):
            parts.append(f"Deaths: {site['deaths_description']}")

        # Damage description
        if site.get("damage_description"):
            parts.append(f"Damage: {site['damage_description']}")

        # Cause (for tsunamis)
        if site.get("cause") and site.get("cause") != "Unknown":
            parts.append(f"Cause: {site['cause']}")

        if parts:
            return ". ".join(parts)[:2000]

        return None

    def _derive_period_start(self, source_id: str, site: dict) -> int | None:
        """Derive period_start from site data, with special handling for certain sources."""
        # First try standard date fields
        period = parse_year(site.get("date_start", site.get("period_start", site.get("year_start", site.get("year")))))
        if period is not None:
            return period

        # Special handling for ncei_volcanoes - derive from status field
        if source_id == "ncei_volcanoes":
            status = (site.get("status") or "").lower()
            if status == "historical":
                return -500  # Approximate historical period
            elif status == "holocene":
                return -10000  # Holocene epoch (last 11,700 years)
            elif status == "pleistocene":
                return -100000  # Pleistocene

        return None

    def _print_summary(self):
        """Print loading summary."""
        logger.info("\n" + "=" * 60)
        logger.info("LOADING SUMMARY")
        logger.info("=" * 60)

        success = sum(1 for s in self.stats.values() if s.get("success") and not s.get("skipped"))
        skipped = sum(1 for s in self.stats.values() if s.get("skipped"))
        failed = sum(1 for s in self.stats.values() if not s.get("success"))
        total_records = sum(s.get("count", 0) for s in self.stats.values())

        for source_id, stat in sorted(self.stats.items()):
            if stat.get("skipped"):
                logger.info(f"  - {source_id}: {stat['count']:,} records (skipped)")
            elif stat.get("success"):
                logger.info(f"  + {source_id}: {stat['count']:,} records")
            else:
                logger.error(f"  X {source_id}: {stat.get('error', 'Unknown error')}")

        logger.info("-" * 60)
        logger.info(f"Total: {total_records:,} records | Loaded: {success} | Skipped: {skipped} | Failed: {failed}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Load raw data into unified_sites table")
    parser.add_argument("--source", "-s", help="Load only specific source")
    parser.add_argument("--status", action="store_true", help="Show loading status")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for inserts")
    parser.add_argument("--skip-loaded", action="store_true", help="Skip sources that already have records")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup before loading (use with caution)")
    args = parser.parse_args()

    if args.status:
        # Show current database status
        with get_session() as session:
            result = session.execute(text("""
                SELECT source_id, COUNT(*) as count
                FROM unified_sites
                GROUP BY source_id
                ORDER BY count DESC
            """))

            print("\nCurrent unified_sites counts:")
            print("-" * 40)
            total = 0
            for row in result:
                print(f"  {row.source_id}: {row.count:,}")
                total += row.count
            print("-" * 40)
            print(f"  Total: {total:,}")
        return

    loader = UnifiedLoader(skip_backup=args.no_backup)
    loader.load_all(source_filter=args.source, batch_size=args.batch_size, skip_loaded=args.skip_loaded)


if __name__ == "__main__":
    main()
