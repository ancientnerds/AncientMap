"""
DARE (Digital Atlas of the Roman Empire) ingester.

DARE is a gazetteer of ancient places of the Roman Empire,
based on the Barrington Atlas among other sources.

Data source: https://imperium.ahlfeldt.se/
License: CC-BY-SA 3.0
API Key: Not required
"""

import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import time

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class DAREIngester(BaseIngester):
    """
    Ingester for Digital Atlas of the Roman Empire.

    DARE contains ~27,000 ancient places from the Roman world.
    Uses their GeoJSON API for data access.
    """

    source_id = "dare"
    source_name = "Digital Atlas of the Roman Empire"

    # API endpoint - returns all places in GeoJSON
    API_URL = "http://imperium.ahlfeldt.se/api/geojson.php"

    # Alternative: RDF dump
    # RDF_DUMP_URL = "https://dare.ht.lu.se/export_pelagios3.ttl.gz"

    # Site type mapping from DARE feature types
    TYPE_MAPPING = {
        "settlement": "settlement",
        "city": "settlement",
        "town": "settlement",
        "village": "settlement",
        "vicus": "settlement",
        "colonia": "settlement",
        "municipium": "settlement",
        "fort": "fortress",
        "fortress": "fortress",
        "castrum": "fortress",
        "castellum": "fortress",
        "military": "fortress",
        "legionary": "fortress",
        "temple": "temple",
        "sanctuary": "sanctuary",
        "shrine": "sanctuary",
        "bath": "bath",
        "thermae": "bath",
        "theater": "theater",
        "theatre": "theater",
        "amphitheater": "amphitheater",
        "amphitheatre": "amphitheater",
        "circus": "stadium",
        "stadium": "stadium",
        "aqueduct": "aqueduct",
        "bridge": "bridge",
        "road": "road",
        "port": "port",
        "harbor": "port",
        "harbour": "port",
        "villa": "villa",
        "palace": "palace",
        "cemetery": "cemetery",
        "necropolis": "cemetery",
        "tomb": "tomb",
        "mausoleum": "tomb",
        "mine": "mine",
        "quarry": "quarry",
        "monument": "monument",
        "arch": "monument",
        "column": "monument",
        "wall": "monument",
    }

    def fetch(self) -> Path:
        """
        Fetch all places from DARE GeoJSON API.

        Returns:
            Path to JSON file with all places
        """
        dest_path = self.raw_data_dir / "dare.json"

        logger.info("Fetching DARE data from GeoJSON API...")
        self.report_progress(0, None, "fetching API...")

        headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform)",
        }

        try:
            response = fetch_with_retry(
                self.API_URL,
                headers=headers,
                timeout=120,
            )
            data = response.json()
        except Exception as e:
            logger.error(f"Error fetching DARE data: {e}")
            raise

        features = data.get("features", [])
        logger.info(f"Fetched {len(features):,} places from DARE")
        self.report_progress(len(features), len(features), f"{len(features):,} places")

        # Save to file
        output = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "source": "Digital Atlas of the Roman Empire",
                "source_url": "https://imperium.ahlfeldt.se/",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_places": len(features),
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(features):,} places to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse DARE GeoJSON data.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing DARE data from {raw_data_path}")

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

        # Get coordinates
        if geometry.get("type") != "Point":
            return None

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Extract properties
        dare_id = properties.get("id", "")
        name = properties.get("name", "")
        ancient_name = properties.get("ancient_name", "")
        country = properties.get("country", "")
        feature_type = properties.get("featureType", properties.get("type", ""))

        if not dare_id:
            return None

        # Use ancient name if available, otherwise modern name
        display_name = ancient_name if ancient_name else name
        if not display_name:
            display_name = f"DARE {dare_id}"

        # Alternative names
        alt_names = []
        if ancient_name and name and ancient_name != name:
            alt_names.append(name)

        # Map type
        site_type = self._map_type(feature_type)

        # Build description
        desc_parts = []
        if ancient_name:
            desc_parts.append(f"Ancient: {ancient_name}")
        if name and name != ancient_name:
            desc_parts.append(f"Modern: {name}")
        if country:
            desc_parts.append(f"Country: {country}")
        if feature_type:
            desc_parts.append(f"Type: {feature_type}")

        description = "; ".join(desc_parts) if desc_parts else None

        # Source URL
        source_url = f"https://imperium.ahlfeldt.se/places/{dare_id}"

        return ParsedSite(
            source_id=str(dare_id),
            name=display_name,
            lat=lat,
            lon=lon,
            alternative_names=alt_names,
            description=description[:500] if description else None,
            site_type=site_type,
            period_start=-500,  # Roman period roughly
            period_end=500,
            period_name="Roman",
            precision_meters=100,
            precision_reason="dare",
            source_url=source_url,
            raw_data={
                "id": dare_id,
                "name": name,
                "ancient_name": ancient_name,
                "feature_type": feature_type,
                "country": country,
            },
        )

    def _map_type(self, feature_type: str) -> str:
        """Map DARE feature type to our site type."""
        if not feature_type:
            return "other"

        type_lower = feature_type.lower()
        for key, value in self.TYPE_MAPPING.items():
            if key in type_lower:
                return value

        return "other"


def ingest_dare(session=None, skip_fetch: bool = False) -> dict:
    """Run DARE ingestion."""
    with DAREIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
