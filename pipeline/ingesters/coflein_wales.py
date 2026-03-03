"""
Coflein (Royal Commission on Ancient Monuments of Wales) ingester.

Downloads ~113K archaeological sites from the RCAHMW National Monuments Record
via the DataMapWales WFS (Web Feature Service).

Data source: https://coflein.gov.uk/
WFS endpoint: https://datamap.gov.wales/geoserver/wfs
WFS layer: geonode:rcahmw_nmrw_terrestrialsites_rcahmw_bng
License: OGL (Open Government Licence)
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


class CofleinWalesIngester(BaseIngester):
    """
    Ingester for Coflein / RCAHMW National Monuments Record.

    Contains ~113K archaeological and historic sites across Wales.
    Uses DataMapWales WFS with GeoJSON output, paginated in batches.
    """

    source_id = "coflein_wales"
    source_name = "Coflein Wales"

    WFS_URL = "https://datamap.gov.wales/geoserver/wfs"
    TYPE_NAME = "geonode:rcahmw_nmrw_terrestrialsites_rcahmw_bng"
    PAGE_SIZE = 5000

    # Map site_type values (lowercased) to our site_type taxonomy
    TYPE_MAPPING = {
        "castle": "fortress",
        "fort": "fortress",
        "church": "church",
        "chapel": "church",
        "cairn": "tumulus",
        "barrow": "tumulus",
        "standing stone": "monument",
        "stone circle": "monument",
        "settlement": "settlement",
    }

    # Period name to approximate date range (year)
    PERIOD_DATES = {
        "PREHISTORIC": (-10000, -800),
        "NEOLITHIC": (-4000, -2200),
        "BRONZE AGE": (-2200, -800),
        "IRON AGE": (-800, 74),
        "ROMAN": (74, 410),
        "EARLY MEDIEVAL": (410, 1100),
        "MEDIEVAL": (1100, 1536),
    }

    def fetch(self) -> Path:
        """
        Fetch all records from DataMapWales WFS, paginated.

        Returns:
            Path to saved GeoJSON file.
        """
        dest_path = self.raw_data_dir / "coflein_wales.json"

        logger.info("Fetching Coflein Wales data from DataMapWales WFS...")
        self.report_progress(0, None, "fetching WFS...")

        all_features = []
        offset = 0

        while True:
            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": self.TYPE_NAME,
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                "count": self.PAGE_SIZE,
                "startIndex": offset,
            }

            response = fetch_with_retry(self.WFS_URL, params=params, timeout=120)
            data = response.json()

            features = data.get("features", [])
            all_features.extend(features)

            logger.info(
                f"Page at offset {offset}: {len(features)} features (total: {len(all_features):,})"
            )
            self.report_progress(len(all_features), None, f"{len(all_features):,} features")

            if len(features) < self.PAGE_SIZE:
                break

            offset += self.PAGE_SIZE

        logger.info(f"Fetched {len(all_features):,} features from Coflein Wales")

        output = {
            "type": "FeatureCollection",
            "features": all_features,
            "metadata": {
                "source": "Coflein / RCAHMW National Monuments Record",
                "source_url": "https://coflein.gov.uk/",
                "fetched_at": datetime.now(UTC).isoformat(),
                "total_features": len(all_features),
            },
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved {len(all_features):,} features to {dest_path}")

        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Coflein GeoJSON data into ParsedSite objects.

        Yields:
            ParsedSite objects for each valid feature.
        """
        logger.info(f"Parsing Coflein data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        logger.info(f"Processing {len(features):,} features")

        seen_nprns: set[str] = set()
        for feature in features:
            site = self._parse_feature(feature)
            if site:
                if site.source_id in seen_nprns:
                    continue
                seen_nprns.add(site.source_id)
                yield site

    def _parse_feature(self, feature: dict[str, Any]) -> ParsedSite | None:
        """
        Parse a single GeoJSON feature from the WFS response.

        Args:
            feature: GeoJSON feature dict

        Returns:
            ParsedSite or None if invalid
        """
        geometry = feature.get("geometry")
        properties = feature.get("properties", {})

        # Some features have null geometry (no coordinates)
        if not geometry:
            return None

        # Extract coordinates
        coords = geometry.get("coordinates", [])
        if not coords or len(coords) < 2:
            return None

        lon, lat = coords[0], coords[1]

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # NPRN is the unique identifier
        nprn = str(properties.get("nprn", ""))
        if not nprn:
            return None

        name = properties.get("name", "")
        if not name:
            return None

        # Map site type from site_type field
        site_type = self._map_type(properties)

        # Period
        period_raw = properties.get("period")
        period_name = period_raw if period_raw else None
        period_start, period_end = self._parse_period(period_raw)

        # Build description
        desc_parts = []
        if properties.get("site_type"):
            desc_parts.append(f"Type: {properties['site_type']}")
        if properties.get("evidence"):
            desc_parts.append(f"Evidence: {properties['evidence']}")
        if period_raw:
            desc_parts.append(f"Period: {period_raw}")
        if properties.get("community"):
            desc_parts.append(f"Community: {properties['community']}")

        description = "; ".join(desc_parts) if desc_parts else None

        source_url = f"https://coflein.gov.uk/en/site/{nprn}"

        return ParsedSite(
            source_id=nprn,
            name=name,
            lat=lat,
            lon=lon,
            description=description[:500] if description else None,
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            period_name=period_name,
            source_url=source_url,
            raw_data=properties,
        )

    def _map_type(self, properties: dict[str, Any]) -> str:
        """
        Map site_type field to our site_type taxonomy.

        Case-insensitive matching against semicolon-separated values.
        """
        value = properties.get("site_type", "")
        if not value:
            return "other"

        value_lower = value.lower()
        for key, mapped_type in self.TYPE_MAPPING.items():
            if key in value_lower:
                return mapped_type

        return "other"

    def _parse_period(self, period_raw: str | None) -> tuple[int | None, int | None]:
        """
        Parse period string to start/end years using PERIOD_DATES.

        Args:
            period_raw: Raw period string from the data (e.g. "MEDIEVAL")

        Returns:
            Tuple of (period_start, period_end) years, or (None, None)
        """
        if not period_raw:
            return None, None

        period_upper = period_raw.upper().strip()
        for period_key, (start, end) in self.PERIOD_DATES.items():
            if period_key in period_upper:
                return start, end

        return None, None


def ingest_coflein_wales(session=None, skip_fetch: bool = False) -> dict:
    """Run Coflein Wales ingestion."""
    with CofleinWalesIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
