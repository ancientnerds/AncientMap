"""
ROCEEH ROAD Radiocarbon Paleolithic Europe ingester.

The ROCEEH Out of Africa Database (ROAD) contains ~2,200 Paleolithic
localities across Africa and Eurasia (3 Ma - 20 ka BP).

Data source: https://www.roceeh.uni-tuebingen.de/roadweb/
Data endpoint: askROAD getLocalities.php (POST, returns JSON)
License: CC BY-SA 4.0
API Key: Not required
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class RadiocarbonPaleoIngester(BaseIngester):
    """
    Ingester for ROCEEH ROAD Radiocarbon Paleolithic Europe database.

    ROAD contains ~2,200 Paleolithic localities across Africa and Eurasia
    with site types and geographic attributions.
    """

    source_id = "radiocarbon_paleo"
    source_name = "Radiocarbon Paleolithic Europe"

    # askROAD getLocalities endpoint - returns all localities as JSON via POST
    # Verified working 2026-03-03
    BULK_URL = "https://www.roceeh.uni-tuebingen.de/askROAD/getLocalities.php"

    # Summary Data Sheet URL for linking to individual localities
    LOCALITY_URL = (
        "https://www.roceeh.uni-tuebingen.de/roadweb/sdsPDF.php?localityName={locality_name}"
    )

    def fetch(self) -> Path:
        """
        Fetch all localities from ROCEEH ROAD askROAD endpoint.

        Uses the askROAD getLocalities.php POST endpoint with empty
        filter parameters to retrieve all localities.

        Returns:
            Path to saved JSON file
        """
        dest_path = self.raw_data_dir / "radiocarbon_paleo.json"

        logger.info("Fetching ROCEEH ROAD locality data via askROAD...")
        self.report_progress(0, None, "fetching localities via askROAD POST...")

        response = fetch_with_retry(
            self.BULK_URL,
            method="POST",
            data={
                "localityTypeRawValue": "",
                "countryRawValue": "",
                "continentRawValue": "",
                "subcontinentRawValue": "",
                "showParams": "{}",
            },
            timeout=120,
        )
        data = response.json()

        if not data.get("success"):
            raise RuntimeError(f"ROCEEH ROAD API returned success=false: {data}")

        localities = data.get("localities", [])
        record_count = len(localities)

        logger.info(f"Fetched {record_count:,} locality records from ROCEEH ROAD")
        self.report_progress(record_count, record_count, f"{record_count:,} records")

        output = {
            "data": localities,
            "metadata": {
                "source": "ROCEEH ROAD",
                "source_url": "https://www.roceeh.uni-tuebingen.de/roadweb/",
                "fetched_at": datetime.now(UTC).isoformat(),
                "total_records": record_count,
            },
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved {record_count:,} records to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse ROCEEH ROAD locality data into ParsedSite objects.

        Yields:
            ParsedSite objects for each valid locality
        """
        logger.info(f"Parsing ROCEEH ROAD data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            wrapper = json.load(f)

        localities = wrapper.get("data", [])
        if not isinstance(localities, list):
            localities = []

        logger.info(f"Processing {len(localities):,} localities")

        for locality in localities:
            site = self._parse_locality(locality)
            if site:
                yield site

    def _parse_locality(self, record: dict[str, Any]) -> ParsedSite | None:
        """
        Parse a single ROAD locality record from askROAD getLocalities.php.

        Record fields: localityName, country, continent, subcontinent,
        localityType, localityX (longitude), localityY (latitude).

        Args:
            record: Raw locality dict from askROAD JSON

        Returns:
            ParsedSite or None if record lacks valid coordinates
        """
        lat = _to_float(record.get("localityY"))
        lon = _to_float(record.get("localityX"))

        if lat is None or lon is None:
            return None
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0.0 and lon == 0.0:
            return None

        name = record.get("localityName")
        if not name:
            return None

        # Build description from available fields
        desc_parts = []
        if record.get("country"):
            desc_parts.append(f"Country: {record['country']}")
        if record.get("continent"):
            desc_parts.append(f"Continent: {record['continent']}")
        if record.get("subcontinent"):
            desc_parts.append(f"Region: {record['subcontinent']}")
        if record.get("localityType"):
            desc_parts.append(f"Type: {record['localityType']}")

        description = "; ".join(desc_parts) if desc_parts else None

        # URL-encode the locality name for the SDS PDF link
        source_url = self.LOCALITY_URL.format(locality_name=quote(name))

        return ParsedSite(
            source_id=name,
            name=name,
            lat=lat,
            lon=lon,
            description=description[:500] if description else None,
            site_type="other",
            period_start=None,
            period_end=None,
            period_name="Paleolithic",
            precision_meters=500,
            precision_reason="roceeh_road_locality",
            source_url=source_url,
            raw_data=record,
        )


def _to_float(value: Any) -> float | None:
    """Convert a value to float, returning None if not possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def ingest_radiocarbon_paleo(session=None, skip_fetch: bool = False) -> dict:
    """Run ROCEEH ROAD Radiocarbon Paleolithic Europe ingestion."""
    with RadiocarbonPaleoIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
