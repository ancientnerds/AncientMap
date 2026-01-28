"""
ToposText Ancient Texts ingester.

Downloads ancient text references to places from ToposText - an index linking
ancient Greek and Latin texts to geographic locations.

Data source: https://topostext.org/
API docs: https://topostext.org/api
License: CC BY-NC-SA 4.0
API Key: Not required
"""

import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import re

import httpx
from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json


class ToposTextIngester(BaseIngester):
    """
    Ingester for ToposText ancient text references.

    Fetches places mentioned in ancient Greek and Latin texts,
    linking literary references to geographic locations.
    """

    source_id = "topostext"
    source_name = "ToposText"

    # Download URLs - ToposText provides downloadable datasets
    GEOJSON_URL = "https://topostext.org/downloads/ToposText_places_2025-11-20.geojson"

    # Period mapping for ancient authors
    AUTHOR_PERIODS = {
        "homer": (-800, -700),
        "herodotus": (-484, -425),
        "thucydides": (-460, -400),
        "xenophon": (-430, -354),
        "plato": (-428, -348),
        "aristotle": (-384, -322),
        "strabo": (-64, 24),
        "pausanias": (110, 180),
        "pliny": (23, 79),
        "ptolemy": (100, 170),
        "livy": (-59, 17),
        "tacitus": (56, 120),
        "plutarch": (46, 120),
        "diodorus": (-90, -30),
        "polybius": (-200, -118),
    }

    def fetch(self) -> Path:
        """Fetch places with text references from ToposText GeoJSON download."""
        dest_path = self.raw_data_dir / "topostext.json"

        logger.info("=" * 60)
        logger.info("TOPOSTEXT - ANCIENT TEXT REFERENCES")
        logger.info("=" * 60)

        logger.info(f"Downloading ToposText GeoJSON from {self.GEOJSON_URL}...")
        self.report_progress(0, 1, "downloading GeoJSON...")

        # Download the GeoJSON file
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get(self.GEOJSON_URL)

            if response.status_code != 200:
                raise Exception(f"Failed to download: {response.status_code}")

            geojson = response.json()

        # Extract features
        features = geojson.get("features", [])
        logger.info(f"Downloaded {len(features):,} places")

        # Convert to our format
        all_places = []
        for feature in features:
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [])

            if geom.get("type") == "Point" and len(coords) >= 2:
                place = {
                    **props,
                    "lon": coords[0],
                    "lat": coords[1],
                    "geometry": geom,
                }
                all_places.append(place)

        self.report_progress(1, 1, f"{len(all_places):,} places")

        logger.info("=" * 60)
        logger.info(f"COMPLETED: {len(all_places):,} places with coordinates")
        logger.info("=" * 60)

        # Save results
        output = {
            "places": all_places,
            "metadata": {
                "source": "ToposText",
                "source_url": "https://topostext.org/",
                "download_url": self.GEOJSON_URL,
                "fetched_at": datetime.utcnow().isoformat(),
                "total_places": len(all_places),
                "license": "CC BY-NC-SA 4.0 (attribution required)",
                "description": "Index of ancient Greek and Latin texts with geographic references",
            }
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved to {dest_path}")

        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse ToposText places into sites."""
        logger.info(f"Parsing ToposText data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        places = data.get("places", [])
        logger.info(f"Processing {len(places):,} places")

        for place in places:
            site = self._parse_place(place)
            if site:
                yield site

    def _parse_place(self, place: Dict) -> Optional[ParsedSite]:
        """Parse a single ToposText place."""
        # Get ID
        place_id = place.get("id") or place.get("pleiades_id") or place.get("topostext_id")
        if not place_id:
            return None

        # Get coordinates
        lat = place.get("lat") or place.get("latitude")
        lon = place.get("lon") or place.get("longitude")

        # Try geometry object
        if lat is None or lon is None:
            geom = place.get("geometry", {})
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        if lat is None or lon is None:
            return None

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Get names
        name = place.get("name") or place.get("title") or place.get("label")
        if not name:
            name = f"ToposText {place_id}"

        alt_names = []
        for key in ["greek_name", "latin_name", "modern_name", "alternate_names"]:
            val = place.get(key)
            if val:
                if isinstance(val, list):
                    alt_names.extend(val)
                else:
                    alt_names.append(val)

        # Get text references
        text_refs = place.get("text_references", [])
        texts = place.get("texts", [])
        ref_count = place.get("reference_count", len(text_refs) + len(texts))

        # Build description
        desc_parts = []
        if ref_count:
            desc_parts.append(f"Referenced in {ref_count} ancient texts")
        if place.get("description"):
            desc_parts.append(place["description"])
        if place.get("type"):
            desc_parts.append(f"Type: {place['type']}")

        description = "; ".join(desc_parts) if desc_parts else None

        # Determine period from text references
        period_start, period_end = self._get_period_from_texts(text_refs + texts)

        # Map type
        place_type = place.get("type", "").lower()
        site_type = self._map_type(place_type, name)

        # Source URL
        source_url = place.get("url") or f"https://topostext.org/place/{place_id}"

        return ParsedSite(
            source_id=f"topostext_{place_id}",
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=list(set(alt_names))[:10],
            description=description[:500] if description else None,
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            precision_meters=1000,  # Literature references often imprecise
            precision_reason="literary_reference",
            source_url=source_url,
            raw_data={
                "topostext_id": place_id,
                "pleiades_id": place.get("pleiades_id"),
                "text_count": ref_count,
                "place_type": place.get("type"),
            },
        )

    def _get_period_from_texts(self, texts: List) -> tuple:
        """Estimate period based on text references."""
        earliest_start = None
        latest_end = None

        for text in texts:
            author = ""
            if isinstance(text, dict):
                author = text.get("author", "").lower()
            elif isinstance(text, str):
                author = text.lower()

            for author_name, (start, end) in self.AUTHOR_PERIODS.items():
                if author_name in author:
                    if earliest_start is None or start < earliest_start:
                        earliest_start = start
                    if latest_end is None or end > latest_end:
                        latest_end = end

        return earliest_start, latest_end

    def _map_type(self, place_type: str, name: str) -> str:
        """Map ToposText type to site type."""
        text = f"{place_type} {name}".lower()

        type_mapping = {
            "city": "settlement",
            "town": "settlement",
            "polis": "settlement",
            "colony": "settlement",
            "settlement": "settlement",
            "temple": "temple",
            "sanctuary": "temple",
            "oracle": "temple",
            "mountain": "natural_feature",
            "river": "natural_feature",
            "island": "natural_feature",
            "region": "region",
            "province": "region",
            "battle": "battlefield",
            "port": "port",
            "harbor": "port",
        }

        for key, site_type in type_mapping.items():
            if key in text:
                return site_type

        return "ancient_place"


def ingest_topostext(session=None, skip_fetch: bool = False) -> dict:
    """Run ToposText ingestion."""
    with ToposTextIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
