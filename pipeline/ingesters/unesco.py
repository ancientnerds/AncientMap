"""
UNESCO World Heritage Sites ingester.

Fetches cultural and mixed World Heritage Sites from UNESCO's data feeds.

Data source: https://data.unesco.org/
License: Open with attribution
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_bytes
from pipeline.utils.http import fetch_with_retry


class UNESCOIngester(BaseIngester):
    """
    Ingester for UNESCO World Heritage Sites.

    Uses the UNESCO DataHub API which provides GeoJSON format.
    We focus on Cultural and Mixed sites (not purely Natural).
    """

    source_id = "unesco"
    source_name = "UNESCO World Heritage Sites"

    # UNESCO DataHub API (more reliable than whc.unesco.org)
    GEOJSON_URL = "https://data.unesco.org/explore/dataset/whc001/download?format=geojson"
    JSON_URL = "https://data.unesco.org/explore/dataset/whc001/download?format=json"

    # Category mapping
    CATEGORY_MAPPING = {
        "Cultural": "monument",
        "Mixed": "monument",
        "Natural": None,  # Skip natural sites
    }

    def fetch(self) -> Path:
        """
        Download UNESCO World Heritage data.

        Returns:
            Path to the downloaded JSON file
        """
        dest_path = self.raw_data_dir / "unesco-whs.json"

        logger.info(f"Downloading UNESCO data from {self.GEOJSON_URL}")
        self.report_progress(0, None, "downloading...")

        headers = {
            "User-Agent": "AncientNerds/1.0 (Research Platform)",
            "Accept": "application/json",
        }

        response = fetch_with_retry(self.GEOJSON_URL, headers=headers)
        atomic_write_bytes(dest_path, response.content)

        logger.info(f"Downloaded UNESCO data to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse UNESCO GeoJSON data.

        Yields:
            ParsedSite objects for Cultural and Mixed sites
        """
        logger.info(f"Parsing UNESCO GeoJSON from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features)} UNESCO sites")

        for feature in features:
            site = self._parse_feature(feature)
            if site:
                yield site

    def _parse_feature(self, feature: dict[str, Any]) -> ParsedSite | None:
        """
        Parse a single GeoJSON feature into a ParsedSite.

        Args:
            feature: GeoJSON feature dict

        Returns:
            ParsedSite or None if not relevant
        """
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        # Get category first - skip Natural sites
        category = properties.get("category", "")
        if category == "Natural":
            return None

        # Extract basic fields
        unesco_id = str(properties.get("id_no", properties.get("id_number", "")))
        name = properties.get("name_en", properties.get("site", ""))

        if not unesco_id or not name:
            return None

        # Parse coordinates from geometry
        if geometry.get("type") != "Point":
            return None

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        # Skip if no valid coordinates
        if lat == 0 and lon == 0:
            return None

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Get other fields
        country = properties.get("states_name_en", properties.get("states", ""))
        description = properties.get("short_description_en", properties.get("short_description", ""))
        date_inscribed = str(properties.get("date_inscribed", ""))
        region = properties.get("region_en", properties.get("region", ""))
        criteria = properties.get("criteria_txt", "")

        # Determine site type based on criteria
        site_type = self._determine_site_type(criteria, category)

        # Build source URL
        source_url = f"https://whc.unesco.org/en/list/{unesco_id}"

        return ParsedSite(
            source_id=unesco_id,
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description[:1000] if description else None,
            site_type=site_type,
            period_start=None,  # UNESCO doesn't provide detailed periods
            period_end=None,
            period_name=None,
            precision_meters=1000,  # UNESCO coordinates are approximate centroids
            precision_reason="centroid",
            source_url=source_url,
            raw_data={
                "id": unesco_id,
                "name": name,
                "country": country,
                "region": region,
                "category": category,
                "criteria": criteria,
                "date_inscribed": date_inscribed,
            },
        )

    def _determine_site_type(self, criteria: str, category: str) -> str:
        """
        Determine site type from UNESCO criteria.

        UNESCO criteria:
        (i) - masterpiece of human creative genius
        (ii) - interchange of human values
        (iii) - testimony to cultural tradition
        (iv) - outstanding example of building/landscape
        (v) - traditional human settlement
        (vi) - association with events/traditions
        """
        if not criteria:
            return "monument"

        criteria_lower = criteria.lower()

        # Check for specific patterns
        if "(iv)" in criteria_lower:
            return "monument"
        if "(v)" in criteria_lower:
            return "settlement"
        if "(iii)" in criteria_lower:
            return "monument"

        return "monument"


def ingest_unesco(session=None, skip_fetch: bool = False) -> dict:
    """Run UNESCO ingestion."""
    with UNESCOIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
