"""
Portable Antiquities Scheme (PAS) data ingester.

The PAS records over 1.4 million archaeological finds made by the public
in England and Wales. It is run by the British Museum.

Data source: https://finds.org.uk/database/search/results/format/json
License: CC BY (attribution required)
API Key: Not required

Note: finds.org.uk uses Cloudflare which blocks Python HTTP libraries (httpx,
requests) via TLS fingerprinting. We use curl_cffi with Chrome impersonation
to bypass this. Standard User-Agent spoofing alone is not sufficient.
"""

import json
import math
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from curl_cffi import requests as cffi_requests
from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json

PAGE_SIZE = 100
REQUEST_DELAY = 0.5  # Be polite to the API

ANCIENT_PERIODS = [
    "IRON AGE",
    "ROMAN",
    "EARLY MEDIEVAL",
    "BRONZE AGE",
    "NEOLITHIC",
    "MESOLITHIC",
    "PALAEOLITHIC",
]

PERIOD_DATES = {
    "PALAEOLITHIC": (-500000, -10000),
    "MESOLITHIC": (-10000, -4000),
    "NEOLITHIC": (-4000, -2200),
    "BRONZE AGE": (-2200, -800),
    "IRON AGE": (-800, 43),
    "ROMAN": (43, 410),
    "EARLY MEDIEVAL": (410, 1066),
}


class PASFindsIngester(BaseIngester):
    """
    Ingester for the Portable Antiquities Scheme database.

    The PAS REST API returns JSON with pagination support.
    Each broadperiod is queried separately to keep result sets manageable.

    Rate limiting: 0.5s between requests. The API does not require auth.
    Uses curl_cffi with Chrome impersonation to bypass Cloudflare TLS fingerprinting.
    """

    source_id = "pas_finds"
    source_name = "Portable Antiquities Scheme"

    API_BASE = "https://finds.org.uk/database/search/results"

    def fetch(self) -> Path:
        """
        Fetch PAS finds for all ancient periods.

        Paginates through each broadperiod, collecting all results.
        This will take a long time (~14K pages per period at 100/page).

        Returns:
            Path to JSON file with all records
        """
        dest_path = self.raw_data_dir / "pas_finds.json"

        all_records = []
        grand_total = 0

        for period in ANCIENT_PERIODS:
            logger.info(f"Starting fetch for period: {period}")
            period_records = self._fetch_period(period)
            all_records.extend(period_records)
            grand_total += len(period_records)
            logger.info(
                f"Completed {period}: {len(period_records):,} records"
                f" (total so far: {grand_total:,})"
            )

        output = {
            "records": all_records,
            "metadata": {
                "source": "Portable Antiquities Scheme",
                "fetched_at": datetime.now(UTC).isoformat(),
                "total_fetched": len(all_records),
                "periods": ANCIENT_PERIODS,
            },
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved {len(all_records):,} total records to {dest_path}")
        return dest_path

    def _fetch_period(self, period: str) -> list[dict]:
        """
        Fetch all pages for a single broadperiod.

        Uses curl_cffi with Chrome impersonation because finds.org.uk
        uses Cloudflare which blocks Python HTTP clients via TLS fingerprinting.

        Args:
            period: PAS broadperiod name (e.g. "ROMAN")

        Returns:
            List of record dicts for this period
        """
        records = []
        page = 1
        total_results = None
        total_pages = None

        url = f"{self.API_BASE}/broadperiod/{period}/format/json"

        while True:
            params = {"page": page, "show": PAGE_SIZE}

            response = cffi_requests.get(
                url,
                params=params,
                impersonate="chrome",
                timeout=30,
            )

            if response.status_code == 429:
                logger.warning("Rate limited. Waiting 60 seconds...")
                time.sleep(60)
                continue

            if response.status_code >= 400:
                raise RuntimeError(f"HTTP {response.status_code} for {url}: {response.text[:200]}")

            data = response.json()

            # Get total on first page
            if total_results is None:
                meta = data.get("meta", {})
                total_results = int(meta.get("totalResults", 0))
                total_pages = math.ceil(total_results / PAGE_SIZE)
                logger.info(f"{period}: {total_results:,} results across {total_pages:,} pages")

            results = data.get("results", [])
            if not results:
                break

            records.extend(results)

            logger.info(f"Fetching {period} page {page}/{total_pages}")
            self.report_progress(len(records), total_results, f"Fetching {period}...")

            if page >= total_pages:
                break

            page += 1
            time.sleep(REQUEST_DELAY)

        return records

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse PAS finds JSON into ParsedSite objects.

        Yields:
            ParsedSite for each valid record with coordinates
        """
        logger.info(f"Parsing PAS data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        records = data.get("records", [])
        logger.info(f"Processing {len(records):,} records")

        for record in records:
            site = self._parse_record(record)
            if site:
                yield site

    def _parse_record(self, record: dict) -> ParsedSite | None:
        """
        Parse a single PAS record into a ParsedSite.

        Args:
            record: Raw PAS record dict

        Returns:
            ParsedSite or None if coordinates are missing/invalid
        """
        # Extract coordinates
        lat_raw = record.get("fourFigureLat") or record.get("latitude")
        lon_raw = record.get("fourFigureLon") or record.get("longitude")

        if lat_raw is None or lon_raw is None:
            return None

        try:
            lat = float(lat_raw)
            lon = float(lon_raw)
        except (ValueError, TypeError):
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Source ID
        record_id = record.get("id")
        if record_id is None:
            return None
        source_id = str(record_id)

        # Build name from object type and period
        object_type = record.get("objecttype", "Find")
        broad_period = record.get("broadperiod", "")
        name = f"{object_type} ({broad_period})" if broad_period else object_type

        # Period dates
        period_start = None
        period_end = None
        if broad_period and broad_period.upper() in PERIOD_DATES:
            period_start, period_end = PERIOD_DATES[broad_period.upper()]

        # Location description
        parts = []
        county = record.get("county")
        district = record.get("district")
        if district:
            parts.append(district)
        if county:
            parts.append(county)
        location_desc = ", ".join(parts) if parts else None

        # Description
        desc_parts = []
        if record.get("description"):
            desc_parts.append(record["description"])
        if record.get("objectMaterial"):
            desc_parts.append(f"Material: {record['objectMaterial']}")
        if location_desc:
            desc_parts.append(f"Found in: {location_desc}")
        description = "; ".join(desc_parts) if desc_parts else None

        return ParsedSite(
            source_id=source_id,
            name=name,
            lat=lat,
            lon=lon,
            description=description[:500] if description else None,
            site_type="other",
            period_name=broad_period if broad_period else None,
            period_start=period_start,
            period_end=period_end,
            precision_meters=1000,
            precision_reason="four_figure_grid_ref",
            source_url=(f"https://finds.org.uk/database/artefacts/record/id/{source_id}"),
            raw_data=record,
        )


def ingest_pas_finds(session=None, skip_fetch: bool = False) -> dict:
    """Run PAS Finds ingestion."""
    with PASFindsIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
