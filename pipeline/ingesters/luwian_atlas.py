"""
Luwian Studies Site Atlas ingester.

483 Bronze Age archaeological sites in Anatolia (modern Turkey),
compiled by the Luwian Studies Foundation.

Data source: https://zenodo.org/records/17128262
License: CC-BY-4.0
API Key: Not required
"""

import csv
import io
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_bytes
from pipeline.utils.http import fetch_with_retry


class LuwianAtlasIngester(BaseIngester):
    """
    Ingester for the Luwian Studies Site Atlas.

    Contains 483 Bronze Age sites in Anatolia, published as a CSV
    on Zenodo by the Luwian Studies Foundation.
    """

    source_id = "luwian_atlas"
    source_name = "Luwian Studies Site Atlas"

    DOWNLOAD_URL = "https://zenodo.org/records/17128262/files/sites.csv?download=1"

    # Map site_type_id (from categories.csv) to normalized types
    # 1=Bronze Age inscription, 2=Regional center, 3=Settlement, 4=Excavation, 5=Cemetery
    TYPE_ID_MAPPING = {
        "1": "monument",
        "2": "settlement",
        "3": "settlement",
        "4": "other",
        "5": "tomb",
    }

    def fetch(self) -> Path:
        """
        Download the Luwian Studies CSV from Zenodo.

        Returns:
            Path to the downloaded CSV file.
        """
        dest_path = self.raw_data_dir / "luwian_atlas.csv"

        logger.info("Fetching Luwian Studies Site Atlas from Zenodo...")
        self.report_progress(0, None, "downloading CSV...")

        response = fetch_with_retry(self.DOWNLOAD_URL, timeout=60)

        atomic_write_bytes(dest_path, response.content)

        logger.info(f"Saved Luwian Atlas CSV to {dest_path} ({len(response.content):,} bytes)")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse the Luwian Studies CSV into ParsedSite objects.

        Yields:
            ParsedSite for each valid row.
        """
        logger.info(f"Parsing Luwian Atlas data from {raw_data_path}")

        text = raw_data_path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        parsed_count = 0
        skipped_count = 0

        for idx, row in enumerate(reader):
            site = self._parse_row(idx, row)
            if site:
                parsed_count += 1
                yield site
            else:
                skipped_count += 1

        logger.info(f"Parsed {parsed_count} sites, skipped {skipped_count}")

    def _parse_row(self, idx: int, row: dict) -> ParsedSite | None:
        """
        Parse a single CSV row into a ParsedSite.

        Args:
            idx: Row index (used as fallback source_id).
            row: CSV row as a dict.

        Returns:
            ParsedSite or None if the row is invalid.
        """
        # Extract coordinates
        lat_str = self._find_column(row, ["latitude", "Latitude", "Lat", "lat"])
        lon_str = self._find_column(row, ["longitude", "Longitude", "Lon", "lon"])

        if not lat_str or not lon_str:
            return None

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except (ValueError, TypeError):
            return None

        if lat == 0.0 and lon == 0.0:
            return None

        # Name
        name = self._find_column(row, ["name", "Name", "Site", "site_name"])
        if not name or not name.strip():
            return None
        name = name.strip()

        # Source ID: use id column if present, otherwise row index
        record_id = self._find_column(row, ["id", "ID", "Id"])
        source_id = record_id.strip() if record_id else str(idx)

        # Site type: numeric site_type_id mapped via TYPE_ID_MAPPING
        type_id = self._find_column(row, ["site_type_id", "SiteType", "Type"])
        site_type = self.TYPE_ID_MAPPING.get(type_id.strip(), "other") if type_id else "other"

        # Description from Province and District
        province = self._find_column(row, ["province", "Province", "Region"])
        district = self._find_column(row, ["district", "District"])

        desc_parts = []
        if province and province.strip():
            desc_parts.append(f"Province: {province.strip()}")
        if district and district.strip():
            desc_parts.append(f"District: {district.strip()}")
        description = "; ".join(desc_parts) if desc_parts else None

        # Source URL from full_url column
        source_url = self._find_column(row, ["full_url", "url"])
        if source_url:
            source_url = source_url.strip() or None

        return ParsedSite(
            source_id=source_id,
            name=name,
            lat=lat,
            lon=lon,
            site_type=site_type,
            period_name="Bronze Age",
            period_start=-3000,
            period_end=-1200,
            source_url=source_url,
            description=description,
            raw_data=dict(row),
        )

    def _find_column(self, row: dict, candidates: list[str]) -> str | None:
        """
        Find the first matching column name (case-insensitive).

        Args:
            row: CSV row dict.
            candidates: List of possible column names.

        Returns:
            The value for the first matching column, or None.
        """
        row_lower = {k.lower(): v for k, v in row.items()}
        for candidate in candidates:
            value = row_lower.get(candidate.lower())
            if value is not None:
                return value
        return None


def ingest_luwian_atlas(session=None, skip_fetch: bool = False) -> dict:
    """Run Luwian Studies Site Atlas ingestion."""
    with LuwianAtlasIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
