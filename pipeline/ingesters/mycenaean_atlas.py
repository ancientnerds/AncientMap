"""
Mycenaean Atlas Project ingester.

The Mycenaean Atlas Project (by Robert Consoli) is a comprehensive
georeferenced database of ~5,600 Bronze Age Aegean archaeological sites.

Data source: http://www.mycenaean-atlas.org/
License: Academic / Research use
API Key: Not required
"""

import csv
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_bytes
from pipeline.utils.http import fetch_with_retry

# Site type mapping from Mycenaean Atlas type fields
TYPE_MAPPING = {
    "tomb": "tomb",
    "tholos": "tomb",
    "chamber tomb": "tomb",
    "cist": "tomb",
    "grave": "tomb",
    "burial": "tomb",
    "cemetery": "tomb",
    "necropolis": "tomb",
    "fortress": "fortress",
    "citadel": "fortress",
    "acropolis": "fortress",
    "fortification": "fortress",
    "fort": "fortress",
    "settlement": "settlement",
    "habitation": "settlement",
    "village": "settlement",
    "town": "settlement",
    "city": "settlement",
    "palace": "settlement",
    "sanctuary": "sanctuary",
    "shrine": "sanctuary",
    "temple": "sanctuary",
    "peak sanctuary": "sanctuary",
    "cave": "cave",
    "workshop": "workshop",
    "quarry": "quarry",
    "mine": "mine",
    "harbor": "port",
    "harbour": "port",
    "port": "port",
}


def _map_site_type(raw_type: str) -> str:
    """Map a Mycenaean Atlas type string to a normalized site type."""
    if not raw_type:
        return "other"
    type_lower = raw_type.strip().lower()
    for key, value in TYPE_MAPPING.items():
        if key in type_lower:
            return value
    return "other"


def _detect_columns(fieldnames: list[str]) -> dict[str, str]:
    """
    Detect which CSV columns correspond to lat, lon, name, type, etc.

    Returns a dict mapping logical names to actual column names.
    """
    mapping = {}
    lower_fields = {f.strip().lower(): f for f in fieldnames}

    # Latitude
    for candidate in ["latitude", "lat", "y"]:
        if candidate in lower_fields:
            mapping["lat"] = lower_fields[candidate]
            break

    # Longitude
    for candidate in ["longitude", "lon", "lng", "long", "x"]:
        if candidate in lower_fields:
            mapping["lon"] = lower_fields[candidate]
            break

    # Name
    for candidate in ["name", "site_name", "sitename", "site", "placename"]:
        if candidate in lower_fields:
            mapping["name"] = lower_fields[candidate]
            break

    # ID
    for candidate in ["id", "site_id", "siteid", "gid", "fid"]:
        if candidate in lower_fields:
            mapping["id"] = lower_fields[candidate]
            break

    # Type
    for candidate in ["type", "site_type", "sitetype", "category", "feature"]:
        if candidate in lower_fields:
            mapping["type"] = lower_fields[candidate]
            break

    # Period
    for candidate in ["period", "date", "dating", "chronology", "phase"]:
        if candidate in lower_fields:
            mapping["period"] = lower_fields[candidate]
            break

    # Description / notes
    for candidate in ["description", "notes", "remarks", "comment"]:
        if candidate in lower_fields:
            mapping["description"] = lower_fields[candidate]
            break

    return mapping


class MycenaeanAtlasIngester(BaseIngester):
    """
    Ingester for the Mycenaean Atlas Project.

    Contains ~5,600 Bronze Age Aegean sites including settlements,
    tombs, sanctuaries, and fortifications from the Mycenaean,
    Minoan, and related cultures.
    """

    source_id = "mycenaean_atlas"
    source_name = "Mycenaean Atlas Project"

    # Data URL - Mycenaean Atlas Project dataset
    DOWNLOAD_URL = "http://www.mycenaean-atlas.org/downloads/map_sites.csv"

    def fetch(self) -> Path:
        """
        Fetch CSV data from the Mycenaean Atlas Project.

        Returns:
            Path to the downloaded CSV file.
        """
        dest_path = self.raw_data_dir / "mycenaean_atlas.csv"

        logger.info("Fetching Mycenaean Atlas data...")
        self.report_progress(0, None, "downloading CSV...")

        response = fetch_with_retry(
            self.DOWNLOAD_URL,
            headers={"Accept": "text/csv, */*"},
            timeout=60,
        )

        atomic_write_bytes(dest_path, response.content)

        size_kb = len(response.content) / 1024
        logger.info(f"Saved {size_kb:.1f} KB to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Mycenaean Atlas CSV data into ParsedSite objects.

        Args:
            raw_data_path: Path to the downloaded CSV file.

        Yields:
            ParsedSite objects for each valid site row.
        """
        logger.info(f"Parsing Mycenaean Atlas data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            if not fieldnames:
                logger.error("CSV file has no header row")
                return

            columns = _detect_columns(fieldnames)
            logger.info(f"CSV columns: {fieldnames}")
            logger.info(f"Column mapping: {columns}")

            if "lat" not in columns or "lon" not in columns:
                logger.error(f"Cannot find lat/lon columns in: {fieldnames}")
                return

            if "name" not in columns:
                logger.error(f"Cannot find name column in: {fieldnames}")
                return

            count = 0
            for i, row in enumerate(reader):
                site = self._parse_row(row, i, columns)
                if site:
                    count += 1
                    yield site

                if (i + 1) % 1000 == 0:
                    self.report_progress(i + 1, None, f"{count} valid sites")

            logger.info(f"Parsed {count} valid sites from {i + 1} rows")

    def _parse_row(self, row: dict, index: int, columns: dict[str, str]) -> ParsedSite | None:
        """
        Parse a single CSV row into a ParsedSite.

        Args:
            row: CSV row as a dict.
            index: Row index (0-based).
            columns: Column name mapping from _detect_columns.

        Returns:
            ParsedSite or None if the row is invalid.
        """
        # Extract and validate coordinates
        lat_str = row.get(columns["lat"], "").strip()
        lon_str = row.get(columns["lon"], "").strip()

        if not lat_str or not lon_str:
            return None

        lat = float(lat_str)
        lon = float(lon_str)

        # Basic geographic sanity for Aegean region
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Name
        name = row.get(columns["name"], "").strip()
        if not name:
            return None

        # Source ID
        if "id" in columns:
            site_id = row.get(columns["id"], "").strip()
        else:
            site_id = ""
        if not site_id:
            site_id = str(index)

        # Site type
        raw_type = ""
        if "type" in columns:
            raw_type = row.get(columns["type"], "").strip()
        site_type = _map_site_type(raw_type)

        # Period
        raw_period = ""
        if "period" in columns:
            raw_period = row.get(columns["period"], "").strip()
        period_name = raw_period if raw_period else "Mycenaean"
        period_start, period_end = self._parse_period(raw_period)

        # Description
        description = None
        if "description" in columns:
            description = row.get(columns["description"], "").strip()
            if description:
                description = description[:500]

        # Source URL
        source_url = f"http://www.mycenaean-atlas.org/atlas/site/{site_id}"

        return ParsedSite(
            source_id=str(site_id),
            name=name,
            lat=lat,
            lon=lon,
            description=description,
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            period_name=period_name,
            precision_meters=100,
            precision_reason="mycenaean_atlas",
            source_url=source_url,
            raw_data=dict(row),
        )

    def _parse_period(self, period_str: str) -> tuple[int, int]:
        """
        Parse a period string into start/end years.

        Known Aegean Bronze Age periods:
        - Early Bronze Age (EBA): ~3000-2000 BCE
        - Middle Bronze Age (MBA): ~2000-1600 BCE
        - Late Bronze Age (LBA): ~1600-1100 BCE
        - Early Helladic (EH): ~3000-2000 BCE
        - Middle Helladic (MH): ~2000-1600 BCE
        - Late Helladic (LH): ~1600-1050 BCE
        - Early Minoan (EM): ~3000-2000 BCE
        - Middle Minoan (MM): ~2000-1600 BCE
        - Late Minoan (LM): ~1600-1100 BCE

        Args:
            period_str: Raw period string from the CSV.

        Returns:
            Tuple of (period_start, period_end) as negative years for BCE.
        """
        if not period_str:
            return -1600, -1100

        p = period_str.strip().upper()

        # Early Bronze Age / Early Helladic / Early Minoan
        if any(
            tag in p
            for tag in ["EBA", "EH", "EM", "EARLY BRONZE", "EARLY HELLADIC", "EARLY MINOAN"]
        ):
            return -3000, -2000

        # Middle Bronze Age / Middle Helladic / Middle Minoan
        if any(
            tag in p
            for tag in ["MBA", "MH", "MM", "MIDDLE BRONZE", "MIDDLE HELLADIC", "MIDDLE MINOAN"]
        ):
            return -2000, -1600

        # Late Bronze Age / Late Helladic / Late Minoan (most Mycenaean)
        if any(
            tag in p
            for tag in [
                "LBA",
                "LH",
                "LM",
                "LATE BRONZE",
                "LATE HELLADIC",
                "LATE MINOAN",
                "MYCENAEAN",
            ]
        ):
            return -1600, -1100

        # Neolithic
        if "NEOLITHIC" in p:
            return -7000, -3000

        # Iron Age
        if "IRON" in p:
            return -1100, -600

        # Default: Late Bronze Age (core Mycenaean period)
        return -1600, -1100


def ingest_mycenaean_atlas(session=None, skip_fetch: bool = False) -> dict:
    """Run Mycenaean Atlas ingestion."""
    with MycenaeanAtlasIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
