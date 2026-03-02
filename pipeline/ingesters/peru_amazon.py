"""
Pre-Columbian Amazon earthwork sites ingester.

Based on supplementary data from de Souza et al. (2018)
"Pre-Columbian earth-builders settled along the entire southern rim
of the Amazon" in Nature Communications.

Data source: https://doi.org/10.6084/m9.figshare.5898512
License: CC-BY-4.0
API Key: Not required
"""

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_bytes
from pipeline.utils.http import fetch_with_retry


class PeruAmazonIngester(BaseIngester):
    """
    Ingester for Pre-Columbian Amazon earthwork sites.

    Contains ~400 sites including geoglyphs, enclosures, and mounds
    along the southern rim of the Amazon basin.
    """

    source_id = "peru_amazon"
    source_name = "Pre-Columbian Amazon Sites"

    # Figshare dataset from de Souza et al. 2018
    DOWNLOAD_URL = "https://ndownloader.figshare.com/files/10725674"

    # Site type mapping from earthwork descriptions
    TYPE_MAPPING = {
        "geoglyph": "monument",
        "mound": "tumulus",
        "earthmound": "tumulus",
        "enclosure": "monument",
        "ditch": "monument",
        "ring ditch": "monument",
        "circular enclosure": "monument",
        "rectangular enclosure": "monument",
    }

    # Candidate column names for latitude
    LAT_CANDIDATES = [
        "Latitude",
        "Lat",
        "lat",
        "Y",
        "Decimal_Lat",
        "latitude",
        "LATITUDE",
        "LAT",
        "decimal_lat",
    ]

    # Candidate column names for longitude
    LON_CANDIDATES = [
        "Longitude",
        "Lon",
        "lon",
        "X",
        "Decimal_Long",
        "longitude",
        "LONGITUDE",
        "LON",
        "Long",
        "long",
        "decimal_long",
    ]

    # Candidate column names for site name
    NAME_CANDIDATES = [
        "Name",
        "name",
        "Site",
        "site",
        "Site_Name",
        "site_name",
        "SiteName",
        "NAME",
        "SITE",
    ]

    # Candidate column names for site type
    TYPE_CANDIDATES = [
        "Type",
        "type",
        "Site_Type",
        "site_type",
        "SiteType",
        "Feature",
        "feature",
        "TYPE",
        "Category",
        "category",
    ]

    # Candidate column names for site ID
    ID_CANDIDATES = [
        "ID",
        "id",
        "Site_ID",
        "site_id",
        "SiteID",
        "FID",
        "fid",
        "Number",
        "number",
    ]

    def _find_column(self, row: dict[str, Any], candidates: list[str]) -> str | None:
        """
        Find a column value by case-insensitive matching against candidates.

        Args:
            row: A dict row from the CSV reader
            candidates: List of candidate column names to try

        Returns:
            The value from the first matching column, or None
        """
        row_keys_lower = {k.strip().lower(): k for k in row.keys()}
        for candidate in candidates:
            key = row_keys_lower.get(candidate.strip().lower())
            if key is not None:
                value = row[key]
                if value is not None and str(value).strip():
                    return str(value).strip()
        return None

    def _map_type(self, raw_type: str) -> str:
        """Map earthwork type to standardized site type."""
        if not raw_type:
            return "other"

        type_lower = raw_type.lower().strip()
        for key, value in self.TYPE_MAPPING.items():
            if key in type_lower:
                return value

        return "other"

    def fetch(self) -> Path:
        """
        Fetch earthwork site data from Figshare.

        Returns:
            Path to downloaded CSV file
        """
        dest_path = self.raw_data_dir / "peru_amazon_raw.csv"

        logger.info("Fetching Pre-Columbian Amazon data from Figshare...")
        self.report_progress(0, None, "downloading from Figshare...")

        response = fetch_with_retry(self.DOWNLOAD_URL, timeout=120)

        atomic_write_bytes(dest_path, response.content)

        logger.info(f"Saved {len(response.content):,} bytes to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse CSV data into ParsedSite objects.

        Args:
            raw_data_path: Path to the downloaded CSV file

        Yields:
            ParsedSite objects for valid earthwork sites
        """
        logger.info(f"Parsing Pre-Columbian Amazon data from {raw_data_path}")

        raw_bytes = raw_data_path.read_bytes()

        # Detect encoding: try UTF-8 first, then latin-1
        for encoding in ["utf-8-sig", "utf-8", "latin-1"]:
            try:
                text = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        # Detect delimiter: try comma, then tab, then semicolon
        first_line = text.split("\n")[0]
        if "\t" in first_line:
            delimiter = "\t"
        elif ";" in first_line and "," not in first_line:
            delimiter = ";"
        else:
            delimiter = ","

        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

        parsed_count = 0
        skipped_count = 0

        for index, row in enumerate(reader):
            site = self._parse_row(row, index)
            if site:
                parsed_count += 1
                yield site
            else:
                skipped_count += 1

        logger.info(f"Parsed {parsed_count:,} sites, skipped {skipped_count:,} rows")

    def _parse_row(self, row: dict[str, Any], index: int) -> ParsedSite | None:
        """
        Parse a single CSV row into a ParsedSite.

        Args:
            row: Dict from csv.DictReader
            index: Row index for fallback ID/name

        Returns:
            ParsedSite or None if row is invalid
        """
        # Extract latitude
        lat_str = self._find_column(row, self.LAT_CANDIDATES)
        if not lat_str:
            return None

        # Extract longitude
        lon_str = self._find_column(row, self.LON_CANDIDATES)
        if not lon_str:
            return None

        # Parse coordinates
        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except ValueError:
            return None

        # Validate coordinates are roughly in South America
        # Lat: -20 to 5, Lon: -80 to -45
        if not (-20 <= lat <= 5) or not (-80 <= lon <= -45):
            logger.debug(
                f"Row {index}: coordinates ({lat}, {lon}) outside South America bounds, skipping"
            )
            return None

        # Extract site ID
        site_id = self._find_column(row, self.ID_CANDIDATES)
        if not site_id:
            site_id = str(index)

        # Extract site name
        name = self._find_column(row, self.NAME_CANDIDATES)
        if not name:
            name = f"Earthwork {index}"

        # Extract and map site type
        raw_type = self._find_column(row, self.TYPE_CANDIDATES)
        site_type = self._map_type(raw_type)

        # Build description
        desc_parts = []
        if raw_type:
            desc_parts.append(f"Type: {raw_type}")
        desc_parts.append("Region: Southern Amazon")
        description = "; ".join(desc_parts)

        # Build raw_data from the original row
        raw_data = {k: v for k, v in row.items() if v}

        return ParsedSite(
            source_id=site_id,
            name=name,
            lat=lat,
            lon=lon,
            description=description,
            site_type=site_type,
            period_start=-1000,
            period_end=1500,
            period_name="Pre-Columbian",
            precision_meters=500,
            precision_reason="figshare_supplement",
            source_url=("https://doi.org/10.1038/s41467-018-03510-7"),
            raw_data=raw_data,
        )


def ingest_peru_amazon(session=None, skip_fetch: bool = False) -> dict:
    """Run Pre-Columbian Amazon ingestion."""
    with PeruAmazonIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
