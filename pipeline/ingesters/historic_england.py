"""
Historic England data ingester.

Fetches scheduled monuments and listed buildings from Historic England's
ArcGIS REST services.

Data source: https://historicengland.org.uk/
License: Open Government Licence v3.0
API Key: Not required
"""

import json
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class HistoricEnglandIngester(BaseIngester):
    """
    Ingester for Historic England data.

    Historic England provides data via ArcGIS REST services:
    - Scheduled Monuments (~20,000 sites)
    - Listed Buildings (~400,000 buildings)

    We focus on Scheduled Monuments as they're more archaeologically relevant.
    """

    source_id = "historic_england"
    source_name = "Historic England"

    # ArcGIS REST API endpoints (NHLE = National Heritage List for England)
    # Layer 6 = Scheduled Monuments, Layer 0 = Listed Buildings
    NHLE_BASE_URL = (
        "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/ArcGIS/rest/services/"
        "National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer"
    )

    SCHEDULED_MONUMENTS_URL = f"{NHLE_BASE_URL}/6/query"
    LISTED_BUILDINGS_URL = f"{NHLE_BASE_URL}/0/query"

    # Pagination settings
    PAGE_SIZE = 1000  # Max records per request
    REQUEST_DELAY = 0.3  # Seconds between requests

    # Monument type to site type mapping
    TYPE_MAPPING = {
        "castle": "fortress",
        "fort": "fortress",
        "hillfort": "fortress",
        "roman fort": "fortress",
        "motte": "fortress",
        "church": "church",
        "chapel": "church",
        "abbey": "church",
        "priory": "church",
        "monastery": "church",
        "temple": "temple",
        "barrow": "tumulus",
        "tumulus": "tumulus",
        "burial": "tomb",
        "cemetery": "cemetery",
        "villa": "villa",
        "settlement": "settlement",
        "town": "settlement",
        "village": "settlement",
        "amphitheatre": "amphitheater",
        "theatre": "theater",
        "bath": "bath",
        "aqueduct": "aqueduct",
        "bridge": "bridge",
        "road": "road",
        "standing stone": "megalith",
        "stone circle": "megalith",
        "henge": "megalith",
        "cursus": "megalith",
        "dolmen": "megalith",
        "cromlech": "megalith",
        "mine": "mine",
        "quarry": "quarry",
        "cross": "monument",
        "monument": "monument",
        "camp": "fortress",
        "beacon": "monument",
        "tower": "monument",
        "wall": "monument",
    }

    def fetch(self) -> Path:
        """
        Fetch data from Historic England ArcGIS services.

        Returns:
            Path to JSON file with all features
        """
        dest_path = self.raw_data_dir / "historic_england.json"

        all_features = []

        # Fetch Scheduled Monuments
        logger.info("Fetching Scheduled Monuments...")
        monuments = self._fetch_arcgis_layer(self.SCHEDULED_MONUMENTS_URL, "monuments")
        all_features.extend(monuments)
        logger.info(f"Fetched {len(monuments):,} scheduled monuments")

        # Optionally fetch Listed Buildings (very large - 400K+)
        # Uncomment if you want all listed buildings
        # logger.info("Fetching Listed Buildings...")
        # buildings = self._fetch_arcgis_layer(self.LISTED_BUILDINGS_URL, "buildings")
        # all_features.extend(buildings)
        # logger.info(f"Fetched {len(buildings):,} listed buildings")

        # Save to file
        output = {
            "type": "FeatureCollection",
            "features": all_features,
            "metadata": {
                "source": "Historic England",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_fetched": len(all_features),
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_features):,} records to {dest_path}")
        return dest_path

    def _fetch_arcgis_layer(self, base_url: str, layer_name: str) -> list[dict]:
        """
        Fetch all features from an ArcGIS layer with pagination.

        Args:
            base_url: ArcGIS query endpoint
            layer_name: Name for logging

        Returns:
            List of GeoJSON features
        """
        all_features = []
        offset = 0

        while True:
            params = {
                "where": "1=1",  # All records
                "outFields": "*",  # All fields
                "outSR": "4326",  # WGS84
                "f": "geojson",  # GeoJSON format
                "resultOffset": offset,
                "resultRecordCount": self.PAGE_SIZE,
            }

            try:
                response = fetch_with_retry(base_url, params=params)
                data = response.json()
            except Exception as e:
                logger.error(f"Error fetching {layer_name} at offset {offset}: {e}")
                break

            features = data.get("features", [])
            if not features:
                break

            all_features.extend(features)
            logger.debug(f"Fetched {len(all_features):,} {layer_name} records")
            self.report_progress(len(all_features), None, f"{len(all_features):,} {layer_name}")

            # Check if there are more records
            if len(features) < self.PAGE_SIZE:
                break

            offset += self.PAGE_SIZE
            time.sleep(self.REQUEST_DELAY)

        return all_features

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Historic England GeoJSON data.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Historic England data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features):,} features")

        for feature in features:
            site = self._parse_feature(feature)
            if site:
                yield site

    def _parse_feature(self, feature: dict[str, Any]) -> ParsedSite | None:
        """
        Parse a single GeoJSON feature.

        Args:
            feature: GeoJSON feature dict

        Returns:
            ParsedSite or None if invalid
        """
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        # Get coordinates (centroid for polygons)
        geom_type = geometry.get("type", "")
        coords = geometry.get("coordinates", [])

        if geom_type == "Point" and len(coords) >= 2:
            lon, lat = coords[0], coords[1]
        elif geom_type == "Polygon" and coords:
            # Calculate centroid of first ring
            ring = coords[0]
            lon = sum(c[0] for c in ring) / len(ring)
            lat = sum(c[1] for c in ring) / len(ring)
        elif geom_type == "MultiPolygon" and coords:
            # Use first polygon's centroid
            ring = coords[0][0]
            lon = sum(c[0] for c in ring) / len(ring)
            lat = sum(c[1] for c in ring) / len(ring)
        else:
            return None

        # Validate coordinates (should be in UK)
        if not (49 <= lat <= 61 and -8 <= lon <= 2):
            return None

        # Extract properties
        # Field names vary between layers, try common ones
        list_entry = properties.get("ListEntry", properties.get("OBJECTID", ""))
        name = properties.get("Name", properties.get("NAME", ""))
        monument_type = properties.get("MonumentType", properties.get("Type", ""))
        description = properties.get("Description", "")

        if not name:
            name = f"Historic site {list_entry}"

        source_id = str(list_entry)

        # Map type
        site_type = self._map_type(monument_type)

        # Source URL
        source_url = f"https://historicengland.org.uk/listing/the-list/list-entry/{list_entry}"

        return ParsedSite(
            source_id=source_id,
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description[:1000] if description else None,
            site_type=site_type,
            period_start=None,
            period_end=None,
            period_name=None,
            precision_meters=50,
            precision_reason="historic_england",
            source_url=source_url,
            raw_data={
                "list_entry": list_entry,
                "name": name,
                "monument_type": monument_type,
            },
        )

    def _map_type(self, monument_type: str) -> str:
        """Map Historic England type to our site type."""
        if not monument_type:
            return "other"

        type_lower = monument_type.lower()
        for key, value in self.TYPE_MAPPING.items():
            if key in type_lower:
                return value

        return "other"


def ingest_historic_england(session=None, skip_fetch: bool = False) -> dict:
    """Run Historic England ingestion."""
    with HistoricEnglandIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
