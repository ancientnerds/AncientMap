"""
Canmore (Historic Environment Scotland) ingester.

Canmore is Scotland's national record of the historic environment,
containing ~125K archaeological and historical sites.

Data source: https://canmore.org.uk/
WFS: https://maps.hes.scot/geoserver/hes/ows
License: Open Government Licence (OGL)
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

# Period name -> (start_year, end_year)
PERIOD_DATES = {
    "PREHISTORIC": (-10000, -800),
    "NEOLITHIC": (-4000, -2500),
    "BRONZE AGE": (-2500, -800),
    "IRON AGE": (-800, 400),
    "ROMAN": (43, 410),
    "EARLY MEDIEVAL": (400, 1100),
    "MEDIEVAL": (1100, 1500),
}

# Canmore SITE_TYPE -> our normalized site_type
TYPE_MAPPING = {
    "castle": "fortress",
    "church": "church",
    "cairn": "tumulus",
    "fort": "fortress",
    "broch": "fortress",
    "stone circle": "monument",
    "standing stone": "monument",
    "dun": "fortress",
    "chapel": "church",
    "tower": "fortress",
    "crannog": "settlement",
    "hut circle": "settlement",
    "souterrain": "settlement",
    "cist": "tomb",
    "chambered cairn": "tomb",
    "burial ground": "cemetery",
    "cemetery": "cemetery",
    "motte": "fortress",
    "hillfort": "fortress",
    "Roman fort": "fortress",
    "abbey": "church",
    "priory": "church",
    "monastery": "church",
    "cathedral": "church",
    "cup and ring marks": "monument",
    "rock art": "monument",
    "carved stone": "monument",
    "cross slab": "monument",
    "symbol stone": "monument",
    "roundhouse": "settlement",
    "wheelhouse": "settlement",
    "homestead": "settlement",
    "farmstead": "settlement",
    "township": "settlement",
    "settlement": "settlement",
}


class CanmoreScotlandIngester(BaseIngester):
    """
    Ingester for Canmore (Historic Environment Scotland).

    Downloads Scottish archaeological and historical site records
    via the HES Spatial Hub WFS endpoint (GeoJSON output).
    """

    source_id = "canmore_scotland"
    source_name = "Canmore Scotland"

    WFS_URL = "https://maps.hes.scot/geoserver/hes/ows"
    PAGE_SIZE = 5000

    def fetch(self) -> Path:
        """
        Fetch all Canmore sites via WFS pagination.

        Returns:
            Path to saved GeoJSON file.
        """
        dest_path = self.raw_data_dir / "canmore_scotland.json"

        all_features = []
        offset = 0

        logger.info("Fetching Canmore Scotland data via WFS...")

        while True:
            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": "hes:canmore_sites",
                "outputFormat": "application/json",
                "count": self.PAGE_SIZE,
                "startIndex": offset,
            }

            response = fetch_with_retry(self.WFS_URL, params=params, timeout=120)
            data = response.json()

            features = data.get("features", [])
            if not features:
                logger.info("No more features, stopping pagination")
                break

            all_features.extend(features)
            logger.info(
                f"Fetched {len(all_features):,} sites "
                f"(page at offset {offset}, got {len(features)})"
            )
            self.report_progress(len(all_features), None, f"{len(all_features):,} sites")

            if len(features) < self.PAGE_SIZE:
                break

            offset += self.PAGE_SIZE

        logger.info(f"Total features fetched: {len(all_features):,}")

        output = {
            "type": "FeatureCollection",
            "features": all_features,
            "metadata": {
                "source": "Canmore (Historic Environment Scotland)",
                "source_url": "https://canmore.org.uk/",
                "wfs_url": self.WFS_URL,
                "fetched_at": datetime.now(UTC).isoformat(),
                "total_features": len(all_features),
                "license": "Open Government Licence (OGL)",
            },
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved {len(all_features):,} features to {dest_path}")

        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Canmore GeoJSON data into ParsedSite objects.

        Yields:
            ParsedSite objects.
        """
        logger.info(f"Parsing Canmore data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features):,} features")

        for feature in features:
            site = self._parse_feature(feature)
            if site:
                yield site

    def _parse_feature(self, feature: dict[str, Any]) -> ParsedSite | None:
        """Parse a single GeoJSON feature from Canmore WFS."""
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        # Get coordinates (GeoJSON = [lon, lat])
        if not geometry or geometry.get("type") != "Point":
            return None

        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Extract fields
        site_id = str(properties.get("SITEID", ""))
        name = properties.get("SITE_NAME", "")

        if not site_id or not name:
            return None

        # Map site type
        raw_type = properties.get("SITE_TYPE", "")
        site_type = self._map_type(raw_type)

        # Map period
        raw_period = properties.get("PERIOD", "")
        period_name = raw_period if raw_period else None
        period_start, period_end = self._map_period(raw_period)

        # Source URL
        source_url = f"https://canmore.org.uk/site/{site_id}"

        return ParsedSite(
            source_id=site_id,
            name=name,
            lat=lat,
            lon=lon,
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            period_name=period_name,
            precision_meters=50,
            precision_reason="canmore_wfs",
            source_url=source_url,
            raw_data=properties,
        )

    def _map_type(self, raw_type: str) -> str:
        """Map Canmore SITE_TYPE to normalized site type."""
        if not raw_type:
            return "other"

        type_lower = raw_type.lower().strip()
        for key, value in TYPE_MAPPING.items():
            if key in type_lower:
                return value

        return "other"

    def _map_period(self, raw_period: str) -> tuple[int | None, int | None]:
        """Map Canmore PERIOD string to start/end years."""
        if not raw_period:
            return None, None

        period_upper = raw_period.upper().strip()
        for key, (start, end) in PERIOD_DATES.items():
            if key in period_upper:
                return start, end

        return None, None


def ingest_canmore_scotland(session=None, skip_fetch: bool = False) -> dict:
    """Run Canmore Scotland ingestion."""
    with CanmoreScotlandIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
