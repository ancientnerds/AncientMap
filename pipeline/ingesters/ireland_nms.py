"""
Ireland National Monuments Service (NMS) ingester.

The National Monuments Service maintains the Sites and Monuments Record (SMR)
and Record of Monuments and Places (RMP) for Ireland.

Data source: https://maps.archaeology.ie/
License: Open Government License Ireland
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


class IrelandNMSIngester(BaseIngester):
    """
    Ingester for Ireland's National Monuments Service data.

    Uses ArcGIS REST API to fetch archaeological monuments from Ireland.
    The SMR/RMP contains 140,000+ recorded monuments.
    """

    source_id = "ireland_nms"
    source_name = "Ireland National Monuments Service"

    # ArcGIS REST API endpoint (SMROpenData FeatureServer - correct as of 2025)
    # Layer 3 = SMR_Located (monuments with coordinates)
    # https://services-eu1.arcgis.com/HyjXgkV6KGMSF3jt/arcgis/rest/services/SMROpenData/FeatureServer
    ARCGIS_URL = (
        "https://services-eu1.arcgis.com/HyjXgkV6KGMSF3jt/arcgis/rest/services/"
        "SMROpenData/FeatureServer/3/query"
    )

    # Pagination
    PAGE_SIZE = 1000
    REQUEST_DELAY = 0.3

    # Monument class to site type mapping
    TYPE_MAPPING = {
        "castle": "fortress",
        "tower house": "fortress",
        "ringfort": "fortress",
        "fort": "fortress",
        "earthwork": "monument",
        "enclosure": "settlement",
        "church": "church",
        "ecclesiastical": "church",
        "monastery": "church",
        "abbey": "church",
        "priory": "church",
        "graveyard": "cemetery",
        "burial": "tomb",
        "grave": "tomb",
        "megalithic": "megalith",
        "standing stone": "megalith",
        "stone circle": "megalith",
        "portal tomb": "megalith",
        "passage tomb": "megalith",
        "wedge tomb": "megalith",
        "court tomb": "megalith",
        "cairn": "tumulus",
        "barrow": "tumulus",
        "mound": "tumulus",
        "tumulus": "tumulus",
        "souterrain": "other",
        "crannog": "settlement",
        "promontory fort": "fortress",
        "hillfort": "fortress",
        "holy well": "sanctuary",
        "cross": "monument",
        "high cross": "monument",
        "round tower": "monument",
        "bridge": "bridge",
        "mill": "other",
        "fulacht": "other",
        "cooking place": "other",
    }

    def fetch(self) -> Path:
        """
        Fetch data from Ireland NMS ArcGIS service.

        Returns:
            Path to JSON file with all features
        """
        dest_path = self.raw_data_dir / "ireland_nms.json"

        all_features = []
        offset = 0

        logger.info("Fetching Ireland NMS monuments...")

        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": self.PAGE_SIZE,
            }

            try:
                response = fetch_with_retry(self.ARCGIS_URL, params=params, timeout=60)
                data = response.json()
            except Exception as e:
                logger.error(f"Error at offset {offset}: {e}")
                break

            features = data.get("features", [])
            if not features:
                break

            all_features.extend(features)
            logger.info(f"Fetched {len(all_features):,} monuments")
            self.report_progress(len(all_features), None, f"{len(all_features):,} monuments")

            if len(features) < self.PAGE_SIZE:
                break

            offset += self.PAGE_SIZE
            time.sleep(self.REQUEST_DELAY)

        # Save to file
        output = {
            "type": "FeatureCollection",
            "features": all_features,
            "metadata": {
                "source": "Ireland National Monuments Service",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_fetched": len(all_features),
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_features):,} records to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Ireland NMS GeoJSON data.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Ireland NMS data from {raw_data_path}")

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

        # Validate Ireland bounds
        if not (51 <= lat <= 56 and -11 <= lon <= -5):
            return None

        # Extract properties
        smr_no = properties.get("SMR_NO", properties.get("smrs", ""))
        name = properties.get("NAME", properties.get("name", ""))
        classification = properties.get("CLASS1", properties.get("class1", ""))
        townland = properties.get("TOWNLAND", properties.get("townland", ""))
        county = properties.get("COUNTY", properties.get("county", ""))

        if not smr_no:
            return None

        # Use SMR number as name if no name
        if not name:
            name = f"Monument {smr_no}"

        # Map classification to site type
        site_type = self._map_type(classification)

        # Build description
        desc_parts = []
        if classification:
            desc_parts.append(f"Class: {classification}")
        if townland:
            desc_parts.append(f"Townland: {townland}")
        if county:
            desc_parts.append(f"County: {county}")

        description = "; ".join(desc_parts) if desc_parts else None

        # Source URL
        source_url = f"https://maps.archaeology.ie/HistoricEnvironment/?SMESSION={smr_no}"

        return ParsedSite(
            source_id=smr_no,
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description,
            site_type=site_type,
            period_start=None,
            period_end=None,
            period_name=None,
            precision_meters=50,
            precision_reason="ireland_nms",
            source_url=source_url,
            raw_data={
                "smr_no": smr_no,
                "name": name,
                "classification": classification,
                "townland": townland,
                "county": county,
            },
        )

    def _map_type(self, classification: str) -> str:
        """Map Ireland NMS classification to our site type."""
        if not classification:
            return "other"

        class_lower = classification.lower()
        for key, value in self.TYPE_MAPPING.items():
            if key in class_lower:
                return value

        return "other"


def ingest_ireland_nms(session=None, skip_fetch: bool = False) -> dict:
    """Run Ireland NMS ingestion."""
    with IrelandNMSIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
