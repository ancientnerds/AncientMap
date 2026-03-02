"""
Vici.org Roman archaeological sites ingester.

Vici.org is a community-driven database of ~20,000 Roman archaeological
sites across Europe, North Africa, and the Near East.

Data source: https://vici.org/data.geojson
License: CC BY-SA 3.0
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


class ViciOrgIngester(BaseIngester):
    """
    Ingester for Vici.org Roman archaeological sites.

    Vici.org provides a GeoJSON download of all sites. No pagination
    or API key required.
    """

    source_id = "vici_org"
    source_name = "Vici.org"

    GEOJSON_URL = "https://vici.org/data.geojson"

    # Map Vici.org 'kind' values to our site types (case-insensitive)
    KIND_MAPPING = {
        "fort": "fortress",
        "fortress": "fortress",
        "castrum": "fortress",
        "wall": "fortress",
        "limes": "fortress",
        "temple": "sanctuary",
        "shrine": "sanctuary",
        "road": "road",
        "milestone": "road",
        "settlement": "settlement",
        "town": "settlement",
        "city": "settlement",
        "village": "settlement",
        "vicus": "settlement",
        "amphitheatre": "theater",
        "amphitheater": "theater",
        "theatre": "theater",
        "theater": "theater",
        "bath": "bath",
        "thermae": "bath",
        "aqueduct": "aqueduct",
        "bridge": "bridge",
        "cemetery": "cemetery",
        "tomb": "cemetery",
        "mausoleum": "cemetery",
        "mine": "mine",
        "quarry": "mine",
        "port": "port",
        "harbour": "port",
        "harbor": "port",
        "villa": "villa",
    }

    def fetch(self) -> Path:
        """
        Fetch all sites from Vici.org GeoJSON endpoint.

        Returns:
            Path to saved JSON file
        """
        dest_path = self.raw_data_dir / "vici_org.json"

        logger.info("Fetching Vici.org data from GeoJSON endpoint...")
        self.report_progress(0, None, "fetching GeoJSON...")

        response = fetch_with_retry(self.GEOJSON_URL, timeout=120)
        data = response.json()

        features = data.get("features", [])
        logger.info(f"Fetched {len(features):,} sites from Vici.org")
        self.report_progress(len(features), len(features), f"{len(features):,} sites")

        output = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "source": "Vici.org",
                "source_url": "https://vici.org/",
                "download_url": self.GEOJSON_URL,
                "fetched_at": datetime.now(UTC).isoformat(),
                "total_sites": len(features),
            },
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved {len(features):,} sites to {dest_path}")

        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Vici.org GeoJSON data into ParsedSite objects.

        Args:
            raw_data_path: Path to the raw GeoJSON file

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Vici.org data from {raw_data_path}")

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
        Parse a single GeoJSON feature into a ParsedSite.

        Args:
            feature: GeoJSON feature dict

        Returns:
            ParsedSite or None if invalid
        """
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        # Only handle Point geometries
        if geometry.get("type") != "Point":
            return None

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        # Skip null island
        if lat == 0 and lon == 0:
            return None

        # Extract ID
        site_id = properties.get("id")
        if not site_id:
            return None
        site_id = str(site_id)

        # Extract name - skip if empty
        name = properties.get("name", "")
        if not name:
            return None

        # Source URL
        source_url = properties.get("uri") or f"https://vici.org/vici/{site_id}"

        # Description from summary or subtitle
        description = properties.get("summary") or properties.get("subtitle")

        # Map site type from 'kind'
        site_type = self._map_kind(properties.get("kind", ""))

        return ParsedSite(
            source_id=site_id,
            name=name,
            lat=lat,
            lon=lon,
            description=description[:500] if description else None,
            site_type=site_type,
            period_start=-500,
            period_end=500,
            period_name="Roman",
            source_url=source_url,
            raw_data=properties,
        )

    def _map_kind(self, kind: str) -> str:
        """Map Vici.org kind value to our site type."""
        if not kind:
            return "other"

        kind_lower = kind.lower()
        for key, value in self.KIND_MAPPING.items():
            if key in kind_lower:
                return value

        return "other"


def ingest_vici_org(session=None, skip_fetch: bool = False) -> dict:
    """Run Vici.org ingestion."""
    with ViciOrgIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
