"""
DINAA (Digital Index of North American Archaeology) ingester.

DINAA aggregates data from State Historic Preservation Offices (SHPOs)
across the United States, containing 900,000+ site records.

Data is published through Open Context.

Data source: https://opencontext.org/projects/416A274C-CF88-4471-3E31-93DB825E9E4A
License: CC-BY (Attribution required)
API Key: Not required
"""

import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import time

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry, RateLimitError


class DINAAIngester(BaseIngester):
    """
    Ingester for DINAA (Digital Index of North American Archaeology).

    DINAA data is published through Open Context, so we use their API.
    The project ID filters for DINAA-specific records.

    This is one of the largest archaeological datasets with 900K+ sites.
    """

    source_id = "dinaa"
    source_name = "DINAA"

    # Open Context API
    API_BASE = "https://opencontext.org"
    SEARCH_ENDPOINT = "/subjects-search/.json"

    # DINAA project UUID in Open Context
    DINAA_PROJECT_ID = "416A274C-CF88-4471-3E31-93DB825E9E4A"

    # Pagination settings
    PAGE_SIZE = 200  # Open Context max
    MAX_RECORDS = 1000000  # DINAA has 900K+ records
    REQUEST_DELAY = 0.5  # Be respectful

    # DINAA site type mapping
    TYPE_MAPPING = {
        "habitation": "settlement",
        "village": "settlement",
        "camp": "settlement",
        "rockshelter": "cave",
        "cave": "cave",
        "burial": "tomb",
        "cemetery": "cemetery",
        "mound": "tumulus",
        "earthwork": "monument",
        "fortification": "fortress",
        "quarry": "quarry",
        "mine": "mine",
        "rock art": "rock_art",
        "petroglyph": "rock_art",
        "pictograph": "rock_art",
        "workshop": "other",
        "lithic": "other",
        "shell": "other",
    }

    def fetch(self) -> Path:
        """
        Fetch DINAA data from Open Context API.

        Returns:
            Path to JSON file with all features
        """
        dest_path = self.raw_data_dir / "dinaa.json"

        all_features = []
        start = 0
        total_count = None

        logger.info("Fetching DINAA data from Open Context...")

        while True:
            params = {
                "proj": self.DINAA_PROJECT_ID,
                "rows": self.PAGE_SIZE,
                "start": start,
                "response": "geo-facet",
            }

            url = f"{self.API_BASE}{self.SEARCH_ENDPOINT}"

            try:
                response = fetch_with_retry(url, params=params, timeout=120)
                data = response.json()
            except RateLimitError:
                logger.warning("Rate limited. Waiting 60 seconds...")
                time.sleep(60)
                continue
            except Exception as e:
                logger.error(f"Error at start={start}: {e}")
                break

            # Get total on first request
            if total_count is None:
                total_count = data.get("totalResults", 0)
                logger.info(f"Total DINAA records: {total_count:,}")

            features = data.get("features", [])
            if not features:
                logger.info("No more features")
                break

            all_features.extend(features)
            logger.info(f"Fetched {len(all_features):,} / {total_count:,} records")
            self.report_progress(len(all_features), total_count, f"{len(all_features):,} records")

            if len(all_features) >= self.MAX_RECORDS:
                logger.warning(f"Reached MAX_RECORDS limit ({self.MAX_RECORDS:,})")
                break

            if start + self.PAGE_SIZE >= total_count:
                break

            start += self.PAGE_SIZE
            time.sleep(self.REQUEST_DELAY)

        # Save to file
        output = {
            "type": "FeatureCollection",
            "features": all_features,
            "metadata": {
                "source": "DINAA via Open Context",
                "project_id": self.DINAA_PROJECT_ID,
                "fetched_at": datetime.utcnow().isoformat(),
                "total_available": total_count,
                "total_fetched": len(all_features),
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_features):,} DINAA records to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse DINAA GeoJSON data.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing DINAA data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features):,} DINAA features")

        for feature in features:
            site = self._parse_feature(feature)
            if site:
                yield site

    def _parse_feature(self, feature: Dict[str, Any]) -> Optional[ParsedSite]:
        """
        Parse a single GeoJSON feature.

        Args:
            feature: GeoJSON feature dict

        Returns:
            ParsedSite or None if invalid
        """
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        # Get coordinates
        if geometry.get("type") != "Point":
            return None

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        # Skip invalid coordinates
        if lat == 0 and lon == 0:
            return None

        # Validate US bounds (DINAA is North American)
        if not (24 <= lat <= 72) or not (-180 <= lon <= -50):
            return None

        # Extract properties
        uri = properties.get("uri", "")
        label = properties.get("label", "")
        item_category = properties.get("item-category", "")
        project = properties.get("project", "")
        context = properties.get("context", "")

        if not uri or not label:
            return None

        # Extract ID from URI
        source_id = uri.split("/")[-1] if uri else ""
        if not source_id:
            return None

        # Map category to site type
        site_type = self._map_category(item_category)

        # DINAA site locations are often generalized for privacy
        # Many are at county or township centroids
        precision = 5000  # 5km default precision for DINAA

        # Build description
        desc_parts = []
        if item_category:
            desc_parts.append(f"Category: {item_category}")
        if context:
            desc_parts.append(context[:300])

        description = "; ".join(desc_parts) if desc_parts else None

        return ParsedSite(
            source_id=source_id,
            name=label,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description[:500] if description else None,
            site_type=site_type,
            period_start=None,
            period_end=None,
            period_name=None,
            precision_meters=precision,
            precision_reason="dinaa_generalized",
            source_url=uri,
            raw_data={
                "uri": uri,
                "label": label,
                "item_category": item_category,
                "project": project,
            },
        )

    def _map_category(self, category: str) -> str:
        """Map DINAA category to our site type."""
        if not category:
            return "other"

        cat_lower = category.lower()
        for key, value in self.TYPE_MAPPING.items():
            if key in cat_lower:
                return value

        return "other"


def ingest_dinaa(session=None, skip_fetch: bool = False) -> dict:
    """Run DINAA ingestion."""
    with DINAAIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
