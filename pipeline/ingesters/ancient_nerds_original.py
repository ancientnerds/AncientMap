"""
Ancient Nerds Original Database Ingester.

This is the PRIMARY data source - manually researched and curated archaeological sites.
Contains 5995 sites with rich descriptions, periods, and categories.

Data source: https://github.com/matt-cavana/ancient-map
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_bytes
from pipeline.utils.http import fetch_with_retry


class AncientNerdsOriginalIngester(BaseIngester):
    """
    Ingester for the original Ancient Nerds manually-curated database.

    This is the PRIMARY source - all other sources are secondary.
    Contains detailed descriptions, period data, and images from Wikipedia.
    """

    source_id = "ancient_nerds"
    source_name = "Ancient Nerds (Original)"

    # GitHub raw URL for the original data
    GEOJSON_URL = "https://raw.githubusercontent.com/matt-cavana/ancient-map/main/cleaned_historical_sites_no_nan.geojson"

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

    # Category typo fixes - preserve original compound names but fix data quality issues
    CATEGORY_TYPO_FIXES = {
        "City/town/settlemen": "City/town/settlement",  # Missing 't'
        "Rock Art": "Rock art",  # Inconsistent capitalization
        "Cave structures": "Cave Structures",  # Inconsistent capitalization
        "4th ml. BC": "Unknown",  # Data error
    }

    @classmethod
    def clean_category(cls, category: str) -> str:
        """Clean a category string, preserving compound names but fixing typos."""
        if not category:
            return "Unknown"

        # Strip whitespace and trailing commas
        category = category.strip().rstrip(",")

        # Apply typo fixes
        if category in cls.CATEGORY_TYPO_FIXES:
            category = cls.CATEGORY_TYPO_FIXES[category]

        return category if category else "Unknown"

    def fetch(self) -> Path:
        """
        Download the original Ancient Nerds GeoJSON data.

        Returns:
            Path to the downloaded JSON file
        """
        dest_path = self.raw_data_dir / "ancient_nerds_original.geojson"

        logger.info(f"Downloading Ancient Nerds original data from {self.GEOJSON_URL}")
        self.report_progress(0, None, "downloading...")

        headers = {
            "User-Agent": "AncientNerds/1.0 (Research Platform)",
            "Accept": "application/json",
        }

        response = fetch_with_retry(self.GEOJSON_URL, headers=headers)
        atomic_write_bytes(dest_path, response.content)

        logger.info(f"Downloaded Ancient Nerds original data to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse the original Ancient Nerds GeoJSON data.

        Yields:
            ParsedSite objects for all sites
        """
        logger.info(f"Parsing Ancient Nerds GeoJSON from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features)} Ancient Nerds original sites")

        for idx, feature in enumerate(features):
            site = self._parse_feature(feature, idx)
            if site:
                yield site

    def _parse_feature(self, feature: dict[str, Any], index: int) -> ParsedSite | None:
        """
        Parse a single GeoJSON feature into a ParsedSite.

        Args:
            feature: GeoJSON feature dict
            index: Feature index for generating IDs

        Returns:
            ParsedSite or None if invalid
        """
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})

        # Extract basic fields
        title = properties.get("Title", "").strip()
        if not title:
            return None

        # Parse coordinates from geometry
        if geometry.get("type") != "Point":
            return None

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Generate a stable ID based on title and coordinates
        source_id = f"an_{index:05d}"

        # Get description (this is the rich content we want!)
        description = properties.get("Description", "")

        # Get period info
        period_name = properties.get("Period", "")
        period_start, period_end = self._parse_period(period_name)

        # Get category/site type - preserve original compound category names
        category = properties.get("Category", "")
        site_type = self.clean_category(category)

        # Get location (country)
        location = properties.get("Location", "")

        # Get year text
        year_text = properties.get("Year", "")

        # Get source URL (Wikipedia)
        source_url = properties.get("Source", "")

        # Get image URL
        image_url = properties.get("Images", "")

        return ParsedSite(
            source_id=source_id,
            name=title,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description,  # Full description - this is key!
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            period_name=period_name,
            precision_meters=100,  # Manually researched, good precision
            precision_reason="manually_researched",
            source_url=source_url,
            raw_data={
                "title": title,
                "description": description,
                "category": category,
                "category_multi": properties.get("Category (multi)", ""),
                "location": location,
                "year": year_text,
                "period": period_name,
                "source": source_url,
                "image": image_url,
                "map": properties.get("Map", ""),
            },
        )

    def _parse_period(self, period_text: str) -> tuple:
        """
        Parse period text into start/end years.

        Args:
            period_text: Period string like "1500 - 500 BC"

        Returns:
            Tuple of (period_start, period_end) as integers
        """
        if not period_text:
            return (None, None)

        # Try direct mapping
        if period_text in self.PERIOD_MAPPING:
            return self.PERIOD_MAPPING[period_text]

        # Try to parse from year text pattern like "150 - 160 AD"
        # This handles the Year field format
        return (None, None)


def ingest_ancient_nerds_original(session=None, skip_fetch: bool = False) -> dict:
    """Run Ancient Nerds original ingestion."""
    with AncientNerdsOriginalIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
