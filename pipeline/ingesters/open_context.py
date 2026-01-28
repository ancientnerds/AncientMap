"""
Open Context data ingester.

Open Context is a publisher of open research data in archaeology,
hosting 5+ million records from hundreds of projects worldwide.

Data source: https://opencontext.org/
License: CC-BY, CC0 (varies by project)
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


class OpenContextIngester(BaseIngester):
    """
    Ingester for Open Context archaeological data.

    Open Context provides a REST API that returns GeoJSON.
    We can query for all subjects with spatial coordinates.

    The API supports:
    - Pagination (start, rows parameters)
    - Filtering by project, category, etc.
    - GeoJSON output format

    Rate limiting: Be respectful, add delays between requests.
    """

    source_id = "open_context"
    source_name = "Open Context"

    # API base URL (new query endpoint as of 2025)
    API_BASE = "https://opencontext.org"
    SEARCH_ENDPOINT = "/query/.json"

    # Pagination settings
    PAGE_SIZE = 100  # Records per page (max 200)
    MAX_RECORDS = 100000  # Safety limit - adjust as needed
    REQUEST_DELAY = 0.5  # Seconds between requests

    # Category to site type mapping
    CATEGORY_MAPPING = {
        "site": "settlement",
        "trench": "other",
        "unit": "other",
        "locus": "other",
        "feature": "other",
        "object": "other",
        "sample": "other",
        "animal bone": "other",
        "pottery": "other",
        "architecture": "monument",
        "burial": "tomb",
        "coin": "other",
    }

    def fetch(self) -> Path:
        """
        Fetch data from Open Context API.

        Uses pagination to retrieve all records with coordinates.
        Uses the new /query/.json endpoint with response=geo-record.

        Returns:
            Path to JSON file with all records
        """
        dest_path = self.raw_data_dir / "open_context.json"

        all_features = []
        start = 0
        total_count = None

        logger.info("Fetching Open Context data via API...")

        headers = {
            "User-Agent": "oc-api-client",  # Required to avoid bot blocking
        }

        while True:
            # Build request URL with geo-record response to get actual items
            params = {
                "rows": self.PAGE_SIZE,
                "start": start,
                "type": "subjects",  # Only subjects (not media/projects)
                "response": "geo-record",  # Get actual records as GeoJSON
            }

            url = f"{self.API_BASE}{self.SEARCH_ENDPOINT}"

            try:
                response = fetch_with_retry(url, params=params, headers=headers)
                data = response.json()
            except RateLimitError:
                logger.warning("Rate limited. Waiting 60 seconds...")
                time.sleep(60)
                continue
            except Exception as e:
                logger.error(f"Error fetching page at start={start}: {e}")
                break

            # Get total count on first request
            if total_count is None:
                total_count = data.get("totalResults", 0)
                logger.info(f"Total records available: {total_count:,}")

            # Extract features from GeoJSON
            features = data.get("features", [])
            if not features:
                logger.info("No more features, stopping pagination")
                break

            all_features.extend(features)
            logger.info(f"Fetched {len(all_features):,} / {min(total_count, self.MAX_RECORDS):,} records")
            self.report_progress(len(all_features), min(total_count, self.MAX_RECORDS), f"{len(all_features):,} records")

            # Check if we've reached the limit
            if len(all_features) >= self.MAX_RECORDS:
                logger.warning(f"Reached MAX_RECORDS limit ({self.MAX_RECORDS})")
                break

            if start + self.PAGE_SIZE >= total_count:
                break

            start += self.PAGE_SIZE

            # Rate limiting
            time.sleep(self.REQUEST_DELAY)

        # Save to file
        output = {
            "type": "FeatureCollection",
            "features": all_features,
            "metadata": {
                "source": "Open Context",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_available": total_count,
                "total_fetched": len(all_features),
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_features):,} records to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Open Context GeoJSON data.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Open Context data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features):,} features")

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

        # Extract thumbnail/image URL if available
        # Open Context may include media references in various fields
        thumbnail = None
        for img_field in ["thumbnail", "depiction", "primaryImage", "image", "media"]:
            if feature.get(img_field):
                thumbnail = feature.get(img_field)
                break
            if properties.get(img_field):
                thumbnail = properties.get(img_field)
                break

        # Also check for icon field which Open Context sometimes uses
        if not thumbnail and properties.get("icon"):
            thumbnail = properties.get("icon")

        # Get coordinates - handle Point, Polygon, and MultiPolygon
        geom_type = geometry.get("type", "")
        coords = geometry.get("coordinates", [])

        if geom_type == "Point" and len(coords) >= 2:
            lon, lat = coords[0], coords[1]
        elif geom_type == "Polygon" and coords:
            # Use centroid of first ring
            ring = coords[0]
            if ring:
                lon = sum(c[0] for c in ring) / len(ring)
                lat = sum(c[1] for c in ring) / len(ring)
            else:
                return None
        elif geom_type == "MultiPolygon" and coords:
            # Use centroid of first polygon's first ring
            ring = coords[0][0] if coords[0] else []
            if ring:
                lon = sum(c[0] for c in ring) / len(ring)
                lat = sum(c[1] for c in ring) / len(ring)
            else:
                return None
        else:
            return None

        # Skip invalid coordinates
        if lat == 0 and lon == 0:
            return None
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Extract properties (new format from /query/.json endpoint)
        # Feature-level fields
        label = feature.get("label", "") or properties.get("label", "")
        uri = properties.get("uri", "") or feature.get("id", "")
        item_category = feature.get("category", "") or properties.get("feature-type", "")
        project = properties.get("project label", "")
        context = properties.get("context label", "")

        if not label:
            return None

        # Extract ID from URI
        source_id = uri.split("/")[-1] if uri else ""
        if not source_id:
            # Generate from label
            source_id = label.replace(" ", "_")[:50]

        # Map category to site type
        site_type = self._map_category(item_category)

        # Build description
        desc_parts = []
        if context:
            desc_parts.append(f"Context: {context}")
        if project:
            desc_parts.append(f"Project: {project}")
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
            precision_meters=100,
            precision_reason="open_context",
            source_url=uri if uri.startswith("http") else f"https://opencontext.org{uri}",
            raw_data={
                "uri": uri,
                "label": label,
                "item_category": item_category,
                "project": project,
                "context": context[:200] if context else "",
                "thumbnail": thumbnail,  # Image URL for unified_loader
            },
        )

    def _map_category(self, category: str) -> str:
        """Map Open Context category to our site type."""
        if not category:
            return "other"

        category_lower = category.lower()
        for key, value in self.CATEGORY_MAPPING.items():
            if key in category_lower:
                return value

        return "other"


def ingest_open_context(session=None, skip_fetch: bool = False) -> dict:
    """Run Open Context ingestion."""
    with OpenContextIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
