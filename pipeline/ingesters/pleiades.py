"""
Pleiades data ingester.

Pleiades is a community-built gazetteer and graph of ancient places,
focusing on the Mediterranean world and ancient Near East.

Data source: https://pleiades.stoa.org/
License: CC-BY 3.0
"""

import csv
import gzip
import json
from pathlib import Path
from typing import Iterator, Optional, List, Dict, Any
from datetime import datetime

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite
from pipeline.utils.http import download_file


class PleiadesIngester(BaseIngester):
    """
    Ingester for Pleiades ancient places data.

    Pleiades provides several download formats:
    - CSV: Simpler, good for basic data
    - JSON: More complete, includes connections and references

    We use the CSV format for initial ingestion as it's simpler to parse
    and contains all the core data we need.
    """

    source_id = "pleiades"
    source_name = "Pleiades"

    # Download URLs (atlantides.org hosts the actual downloads)
    CSV_URL = "https://atlantides.org/downloads/pleiades/dumps/pleiades-places-latest.csv.gz"
    JSON_URL = "https://atlantides.org/downloads/pleiades/json/pleiades-places-latest.json.gz"

    # Time period mapping (Pleiades uses descriptive periods)
    PERIOD_MAPPING = {
        # Prehistoric
        "neolithic": {"start": -7000, "end": -3000},
        "chalcolithic": {"start": -4500, "end": -3300},

        # Bronze Age
        "early-bronze-age-anatolia": {"start": -3000, "end": -2000},
        "middle-bronze-age-anatolia": {"start": -2000, "end": -1600},
        "late-bronze-age-anatolia": {"start": -1600, "end": -1200},
        "bronze-age-early-cycladic": {"start": -3200, "end": -2000},
        "bronze-age-early-helladic": {"start": -2800, "end": -2100},
        "bronze-age-early-minoan": {"start": -2700, "end": -2200},
        "bronze-age-middle-cycladic": {"start": -2000, "end": -1600},
        "bronze-age-middle-helladic": {"start": -2100, "end": -1600},
        "bronze-age-middle-minoan": {"start": -2200, "end": -1500},
        "bronze-age-late-cycladic": {"start": -1600, "end": -1100},
        "bronze-age-late-helladic": {"start": -1600, "end": -1100},
        "bronze-age-late-minoan": {"start": -1500, "end": -1100},
        "egyptian-middle-kingdom": {"start": -2055, "end": -1650},
        "egyptian-new-kingdom": {"start": -1550, "end": -1069},

        # Iron Age
        "archaic": {"start": -750, "end": -480},
        "classical": {"start": -480, "end": -323},
        "hellenistic-republican": {"start": -323, "end": -31},
        "hellenistic": {"start": -323, "end": -31},

        # Roman
        "roman-early-empire": {"start": -31, "end": 117},
        "roman-middle-empire": {"start": 117, "end": 284},
        "roman-late-empire": {"start": 284, "end": 476},
        "roman-provincial": {"start": -31, "end": 476},
        "roman": {"start": -31, "end": 476},
        "roman-republic": {"start": -509, "end": -27},

        # Late Antique / Byzantine
        "late-antique": {"start": 300, "end": 640},
        "transition-roman-early-empire-late-antique": {"start": 200, "end": 400},
        "byzantine": {"start": 330, "end": 1453},

        # Generic periods
        "modern": {"start": 1500, "end": 2000},
        "mediaeval-byzantine": {"start": 640, "end": 1453},
    }

    # Feature type to site type mapping
    TYPE_MAPPING = {
        "settlement": "settlement",
        "urban": "settlement",
        "fort": "fortress",
        "temple": "temple",
        "sanctuary": "sanctuary",
        "villa": "villa",
        "cemetery": "cemetery",
        "tomb": "tomb",
        "tumulus": "tumulus",
        "mine": "mine",
        "bridge": "bridge",
        "aqueduct": "aqueduct",
        "bath": "bath",
        "church": "church",
        "mosque": "mosque",
        "theater": "theater",
        "amphitheater": "amphitheater",
        "stadium": "stadium",
        "station": "settlement",
        "port": "port",
        "road": "road",
        "pass": "road",
        "mountain": "other",
        "river": "other",
        "island": "other",
        "cape": "other",
        "spring": "other",
        "lake": "other",
        "region": "other",
        "province": "other",
        "people": "other",
        "ethnic": "other",
    }

    def fetch(self) -> Path:
        """
        Download Pleiades CSV data.

        Returns:
            Path to the downloaded CSV file
        """
        dest_path = self.raw_data_dir / "pleiades-places.csv"

        # Download and decompress
        logger.info(f"Downloading Pleiades data from {self.CSV_URL}")
        self.report_progress(0, None, "downloading...")
        downloaded_path = download_file(
            url=self.CSV_URL,
            dest_path=dest_path.with_suffix(".csv.gz"),
            force=True,  # Always get fresh data
            decompress_gzip=True,
        )

        logger.info(f"Downloaded Pleiades data to {downloaded_path}")
        return downloaded_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Pleiades CSV data.

        The CSV has these columns:
        - id: Pleiades ID (e.g., "295374")
        - title: Primary name
        - description: Description text
        - reprLat, reprLong: Representative coordinates
        - placeTypes: Comma-separated feature types
        - timePeriods: Comma-separated time periods
        - names: Comma-separated alternative names
        - creators, contributors, etc.: Metadata

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Pleiades CSV from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                site = self._parse_row(row)
                if site:
                    yield site

    def _parse_row(self, row: Dict[str, Any]) -> Optional[ParsedSite]:
        """
        Parse a single CSV row into a ParsedSite.

        Args:
            row: CSV row as dictionary

        Returns:
            ParsedSite or None if invalid
        """
        # Extract basic fields
        pleiades_id = row.get("id", "").strip()
        title = row.get("title", "").strip()

        if not pleiades_id or not title:
            return None

        # Parse coordinates
        try:
            lat = float(row.get("reprLat", "").strip())
            lon = float(row.get("reprLong", "").strip())
        except (ValueError, TypeError):
            # No coordinates - skip this record
            logger.debug(f"Skipping {pleiades_id}: no valid coordinates")
            return None

        # Validate coordinates
        if lat == 0 and lon == 0:
            # Likely placeholder - skip
            return None

        # Parse alternative names
        names_str = row.get("names", "").strip()
        alt_names = [n.strip() for n in names_str.split(",") if n.strip() and n.strip() != title]

        # Parse time periods
        periods_str = row.get("timePeriods", "").strip()
        periods = [p.strip().lower() for p in periods_str.split(",") if p.strip()]

        period_start, period_end, period_name = self._parse_periods(periods)

        # Parse place types
        types_str = row.get("placeTypes", "").strip()
        types = [t.strip().lower() for t in types_str.split(",") if t.strip()]
        site_type = self._map_site_type(types)

        # Build source URL
        source_url = f"https://pleiades.stoa.org/places/{pleiades_id}"

        # Create ParsedSite
        return ParsedSite(
            source_id=pleiades_id,
            name=title,
            lat=lat,
            lon=lon,
            alternative_names=alt_names,
            description=row.get("description", "").strip() or None,
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            period_name=period_name,
            precision_meters=100,  # Pleiades coordinates are generally good
            precision_reason="representative_point",
            source_url=source_url,
            raw_data={
                "id": pleiades_id,
                "title": title,
                "description": row.get("description", ""),
                "placeTypes": types_str,
                "timePeriods": periods_str,
                "names": names_str,
                "creators": row.get("creators", ""),
                "contributors": row.get("contributors", ""),
                "created": row.get("created", ""),
                "modified": row.get("modified", ""),
            },
        )

    def _parse_periods(self, periods: List[str]) -> tuple:
        """
        Parse Pleiades time periods into start/end years.

        Args:
            periods: List of Pleiades period identifiers

        Returns:
            (period_start, period_end, period_name) tuple
        """
        if not periods:
            return None, None, None

        # Find min start and max end across all periods
        starts = []
        ends = []
        names = []

        for period in periods:
            period_lower = period.lower().replace(" ", "-")
            if period_lower in self.PERIOD_MAPPING:
                mapping = self.PERIOD_MAPPING[period_lower]
                starts.append(mapping["start"])
                ends.append(mapping["end"])
                names.append(period)

        if not starts:
            # Unknown periods - just use the names
            return None, None, ", ".join(periods)

        return min(starts), max(ends), ", ".join(names)

    def _map_site_type(self, types: List[str]) -> Optional[str]:
        """
        Map Pleiades place types to our standard site types.

        Args:
            types: List of Pleiades place types

        Returns:
            Standardized site type or None
        """
        if not types:
            return None

        # Try to find a match for each type
        for ptype in types:
            ptype_lower = ptype.lower().replace("-", "").replace(" ", "")
            for key, value in self.TYPE_MAPPING.items():
                if key in ptype_lower:
                    return value

        # Default to "other" if we have types but no match
        return "other"


# Convenience function
def ingest_pleiades(session=None, skip_fetch: bool = False) -> dict:
    """
    Run Pleiades ingestion.

    Args:
        session: SQLAlchemy session (optional)
        skip_fetch: Skip downloading and use existing raw data

    Returns:
        Result dictionary with statistics
    """
    with PleiadesIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "fetched": result.records_fetched,
            "parsed": result.records_parsed,
            "saved": result.records_saved,
            "failed": result.records_failed,
            "duration_seconds": result.duration_seconds,
            "errors": result.errors[:10],  # First 10 errors
        }
