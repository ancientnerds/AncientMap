"""
ROCEEH ROAD Radiocarbon Paleolithic Europe ingester.

The ROCEEH Out of Africa Database (ROAD) contains ~14,300 Paleolithic
localities across Europe with radiocarbon dating information.

Data source: https://www.roceeh.uni-tuebingen.de/roadweb/
License: Academic use
API Key: Not required
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class RadiocarbonPaleoIngester(BaseIngester):
    """
    Ingester for ROCEEH ROAD Radiocarbon Paleolithic Europe database.

    ROAD contains ~14,300 Paleolithic localities in Europe with
    radiocarbon dates, site types, and cultural attributions.
    """

    source_id = "radiocarbon_paleo"
    source_name = "Radiocarbon Paleolithic Europe"

    # Bulk JSON endpoint for all localities
    BULK_URL = "https://www.roceeh.uni-tuebingen.de/roadweb/tcpdf/data/road_localities.json"

    # Web interface base URL for linking to individual localities
    LOCALITY_URL = (
        "https://www.roceeh.uni-tuebingen.de/roadweb/"
        "smarty_road_simple_locality.php?locality={locality_id}"
    )

    def fetch(self) -> Path:
        """
        Fetch all localities from ROCEEH ROAD bulk JSON endpoint.

        Returns:
            Path to saved JSON file
        """
        dest_path = self.raw_data_dir / "radiocarbon_paleo.json"

        logger.info("Fetching ROCEEH ROAD bulk locality data...")
        self.report_progress(0, None, "fetching bulk JSON...")

        response = fetch_with_retry(self.BULK_URL, timeout=120)
        data = response.json()

        # Determine record count based on data structure
        if isinstance(data, list):
            record_count = len(data)
        elif isinstance(data, dict):
            # Could be wrapped in a key like "localities", "data", "features"
            for key in ("localities", "data", "features", "results"):
                if key in data and isinstance(data[key], list):
                    record_count = len(data[key])
                    break
            else:
                record_count = len(data)
        else:
            record_count = 0

        logger.info(f"Fetched {record_count:,} locality records from ROCEEH ROAD")
        self.report_progress(record_count, record_count, f"{record_count:,} records")

        output = {
            "data": data,
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

        data = wrapper.get("data", wrapper)

        # Extract the list of localities from the data
        if isinstance(data, list):
            localities = data
        elif isinstance(data, dict):
            for key in ("localities", "data", "features", "results"):
                if key in data and isinstance(data[key], list):
                    localities = data[key]
                    break
            else:
                # If dict has no recognized list key, treat values as records
                localities = list(data.values()) if data else []
        else:
            localities = []

        logger.info(f"Processing {len(localities):,} localities")

        for locality in localities:
            site = self._parse_locality(locality)
            if site:
                yield site

    def _parse_locality(self, record: dict[str, Any]) -> ParsedSite | None:
        """
        Parse a single ROAD locality record.

        Args:
            record: Raw locality dict from ROAD JSON

        Returns:
            ParsedSite or None if record lacks valid coordinates
        """
        # Extract coordinates - try common field name patterns
        lat = _to_float(record.get("lat") or record.get("latitude") or record.get("y"))
        lon = _to_float(
            record.get("lng") or record.get("lon") or record.get("longitude") or record.get("x")
        )

        if lat is None or lon is None:
            return None
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0.0 and lon == 0.0:
            return None

        # Extract ID
        locality_id = str(record.get("id") or record.get("locality_id") or record.get("ID") or "")
        if not locality_id:
            return None

        # Extract name
        name = (
            record.get("name")
            or record.get("site_name")
            or record.get("locality")
            or record.get("SITE")
            or f"ROAD-{locality_id}"
        )

        # Period information
        period_name = (
            record.get("period") or record.get("culture") or record.get("industry") or "Paleolithic"
        )

        # Radiocarbon age to calendar years (approximate)
        period_start = _c14_to_year(
            record.get("age_max") or record.get("date_max") or record.get("from")
        )
        period_end = _c14_to_year(
            record.get("age_min") or record.get("date_min") or record.get("to")
        )

        # Ensure correct ordering (start should be older = more negative)
        if period_start is not None and period_end is not None:
            if period_start > period_end:
                period_start, period_end = period_end, period_start

        # Description from available fields
        desc_parts = []
        if record.get("country"):
            desc_parts.append(f"Country: {record['country']}")
        if record.get("culture") or record.get("industry"):
            culture = record.get("culture") or record.get("industry")
            desc_parts.append(f"Culture: {culture}")
        if record.get("site_type") or record.get("type"):
            desc_parts.append(f"Type: {record.get('site_type') or record.get('type')}")

        description = "; ".join(desc_parts) if desc_parts else None

        source_url = self.LOCALITY_URL.format(locality_id=locality_id)

        return ParsedSite(
            source_id=locality_id,
            name=name,
            lat=lat,
            lon=lon,
            description=description[:500] if description else None,
            site_type="other",
            period_start=period_start,
            period_end=period_end,
            period_name=period_name,
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


def _c14_to_year(value: Any) -> int | None:
    """
    Convert a radiocarbon age value to a calendar year (negative = BCE).

    Radiocarbon ages are given as years Before Present (BP, where present = 1950).
    For Paleolithic timescales, uncalibrated C14 years are a rough approximation.

    A value of 30000 BP becomes -28050 (i.e., 28050 BCE).
    """
    num = _to_float(value)
    if num is None:
        return None
    # If the value is large and positive, treat as years BP
    if num > 1950:
        return int(1950 - num)
    # If already a calendar year (could be negative for BCE)
    return int(num)


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
