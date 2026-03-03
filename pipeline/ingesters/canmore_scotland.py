"""
Canmore (Historic Environment Scotland) ingester.

Canmore is Scotland's national record of the historic environment,
containing ~320K archaeological and historical sites.

Data source: https://canmore.org.uk/
ArcGIS REST: https://inspire.hes.scot/arcgis/rest/services/CANMORE/Canmore_Points/MapServer
License: Open Government Licence (OGL)
API Key: Not required

Note: The old WFS at maps.hes.scot is dead (DNS failure).
HES migrated to ArcGIS at inspire.hes.scot.
"""

import json
import re
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

# Canmore SITETYPE -> our normalized site_type
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
    "burnt mound": "settlement",
    "occupation site": "settlement",
    "enclosure": "settlement",
}

# Regex to extract period from SITETYPE strings like "FORT (IRON AGE)"
_PERIOD_RE = re.compile(r"\(([^)]+)\)")


class CanmoreScotlandIngester(BaseIngester):
    """
    Ingester for Canmore (Historic Environment Scotland).

    Downloads Scottish archaeological and historical site records
    via the HES ArcGIS REST API (GeoJSON output).
    """

    source_id = "canmore_scotland"
    source_name = "Canmore Scotland"

    # ArcGIS REST query endpoint for the Terrestrial layer (layer 0)
    ARCGIS_QUERY_URL = (
        "https://inspire.hes.scot/arcgis/rest/services/CANMORE/Canmore_Points/MapServer/0/query"
    )
    # Server max is 1000 per request
    PAGE_SIZE = 1000

    # Fields to request from the API
    OUT_FIELDS = (
        "CANMOREID,SITENUMBER,NMRSNAME,ALTNAME,BROADCLASS,"
        "SITETYPE,COUNTY,COUNCIL,ARCHAEOLOG,FORM,ACCURACY,URL"
    )

    def fetch(self) -> Path:
        """
        Fetch all Canmore sites via ArcGIS REST API using FID-range pagination.

        The server does not support standard result pagination, so we query
        by FID ranges (FID >= X AND FID < X + PAGE_SIZE).

        Returns:
            Path to saved GeoJSON file.
        """
        dest_path = self.raw_data_dir / "canmore_scotland.json"

        # First, get the total count and ID range
        count_response = fetch_with_retry(
            self.ARCGIS_QUERY_URL,
            params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
            timeout=30,
        )
        total_count = count_response.json().get("count", 0)
        logger.info(f"Canmore reports {total_count:,} features in Terrestrial layer")

        # Get all object IDs to know the range
        ids_response = fetch_with_retry(
            self.ARCGIS_QUERY_URL,
            params={"where": "1=1", "returnIdsOnly": "true", "f": "json"},
            timeout=60,
        )
        all_ids = ids_response.json().get("objectIds", [])
        if not all_ids:
            logger.error("No object IDs returned from Canmore API")
            atomic_write_json(dest_path, {"type": "FeatureCollection", "features": []})
            return dest_path

        min_id = min(all_ids)
        max_id = max(all_ids)
        logger.info(f"FID range: {min_id} to {max_id}")

        all_features = []
        fid_start = min_id

        logger.info("Fetching Canmore Scotland data via ArcGIS REST API...")

        while fid_start <= max_id:
            fid_end = fid_start + self.PAGE_SIZE
            where = f"FID >= {fid_start} AND FID < {fid_end}"

            params = {
                "where": where,
                "outFields": self.OUT_FIELDS,
                "outSR": "4326",
                "f": "geojson",
            }

            response = fetch_with_retry(self.ARCGIS_QUERY_URL, params=params, timeout=120)
            data = response.json()

            features = data.get("features", [])
            all_features.extend(features)

            if len(all_features) % 10000 < self.PAGE_SIZE:
                logger.info(
                    f"Fetched {len(all_features):,} sites "
                    f"(FID {fid_start}-{fid_end - 1}, got {len(features)})"
                )
                self.report_progress(len(all_features), total_count, f"{len(all_features):,} sites")

            fid_start = fid_end

        logger.info(f"Total features fetched: {len(all_features):,}")

        output = {
            "type": "FeatureCollection",
            "features": all_features,
            "metadata": {
                "source": "Canmore (Historic Environment Scotland)",
                "source_url": "https://canmore.org.uk/",
                "api_url": self.ARCGIS_QUERY_URL,
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
        """Parse a single GeoJSON feature from the ArcGIS REST API."""
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        if not geometry:
            return None

        # Handle both Point and MultiPoint geometries
        geom_type = geometry.get("type", "")
        coords = geometry.get("coordinates", [])

        if geom_type == "MultiPoint":
            # Take the first point from MultiPoint
            if not coords or len(coords[0]) < 2:
                return None
            lon, lat = coords[0][0], coords[0][1]
        elif geom_type == "Point":
            if len(coords) < 2:
                return None
            lon, lat = coords[0], coords[1]
        else:
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Extract fields (new ArcGIS field names)
        site_id = str(properties.get("CANMOREID", ""))
        name = (properties.get("NMRSNAME") or "").strip()

        if not site_id or not name:
            return None

        # Map site type from SITETYPE (e.g. "FORT (IRON AGE)")
        raw_type = properties.get("SITETYPE", "") or ""
        site_type = self._map_type(raw_type)

        # Extract period from SITETYPE parentheses
        period_name = self._extract_period(raw_type)
        period_start, period_end = self._map_period(period_name or "")

        # Source URL — use the one from the API if available
        source_url = (properties.get("URL") or "").strip()
        if not source_url:
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
            precision_reason="canmore_arcgis",
            source_url=source_url,
            raw_data=properties,
        )

    def _extract_period(self, raw_type: str) -> str | None:
        """
        Extract period from SITETYPE strings.

        The ArcGIS API embeds period info in parentheses within SITETYPE,
        e.g. "FORT (IRON AGE)", "BURIAL GROUND (MEDIEVAL)", "BURNT MOUND (PREHISTORIC)".
        Multiple types may be comma-separated; we take the first recognized period.
        """
        if not raw_type:
            return None

        matches = _PERIOD_RE.findall(raw_type.upper())
        for match in matches:
            # Skip non-period parenthetical content
            cleaned = match.strip()
            if cleaned in ("POSSIBLE", "PROBABLE", "S", "PERIOD UNASSIGNED"):
                continue
            # Check if it matches a known period
            for period_key in PERIOD_DATES:
                if period_key in cleaned:
                    return cleaned
            # Also return century-based periods like "19TH CENTURY"
            if "CENTURY" in cleaned:
                return cleaned

        return None

    def _map_type(self, raw_type: str) -> str:
        """Map Canmore SITETYPE to normalized site type."""
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
