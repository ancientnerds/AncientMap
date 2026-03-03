"""
Vici.org Roman archaeological sites ingester.

Vici.org is a community-driven database of ~100,000 Roman archaeological
sites across Europe, North Africa, and the Near East.

Data source: https://vici.org/geojson.php (requires X-Vici-Token header)
License: CC BY-SA 3.0
Token: Public token from vici.org homepage JavaScript
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

    Vici.org serves GeoJSON via geojson.php, authenticated with a public
    token (embedded in the site's JavaScript widget). The ``flat=1`` param
    disables zoom-level filtering and ``bounds`` covers the full globe.
    """

    source_id = "vici_org"
    source_name = "Vici.org"

    GEOJSON_URL = "https://vici.org/geojson.php"
    VICI_TOKEN = "20E2ADF5AB"  # noqa: S105 - public token from vici.org JavaScript

    # Map Vici.org numeric 'kind' IDs to our site types.
    # IDs determined by sampling titles/summaries from the API.
    KIND_MAPPING: dict[int, str] = {
        1: "aqueduct",
        2: "bath",
        3: "settlement",  # city
        4: "fortress",  # fort / castle
        5: "cemetery",  # graves / burial field
        6: "mine",  # workshop / industry
        7: "settlement",  # mansio / tavern / relay
        8: "other",  # museum / memorial (contemporary)
        9: "settlement",  # general settlement
        10: "other",  # shipwreck
        11: "sanctuary",  # temple / sanctuary
        12: "theater",  # theatre / amphitheatre
        13: "villa",
        14: "settlement",  # rural settlement
        15: "fortress",  # watchtower
        16: "other",  # altar / relief / votiv stone
        17: "other",  # find / object
        18: "other",  # archaeological observation
        19: "other",  # inscription
        20: "road",  # milestone
        21: "other",  # building (other)
        22: "bridge",
        23: "road",
        24: "other",  # site of historic event
        25: "fortress",  # temporary camp
    }

    def fetch(self) -> Path:
        """
        Fetch all sites from Vici.org GeoJSON endpoint.

        Returns:
            Path to saved JSON file
        """
        dest_path = self.raw_data_dir / "vici_org.json"

        logger.info("Fetching Vici.org data from geojson.php...")
        self.report_progress(0, None, "fetching GeoJSON...")

        response = fetch_with_retry(
            self.GEOJSON_URL,
            headers={"X-Vici-Token": self.VICI_TOKEN},
            params={"bounds": "-90,-180,90,180", "zoom": "5", "flat": "1"},
            timeout=120,
        )
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

        seen_ids: set[str] = set()
        for feature in features:
            site = self._parse_feature(feature)
            if site:
                if site.source_id in seen_ids:
                    continue
                seen_ids.add(site.source_id)
                yield site

    def _parse_feature(self, feature: dict[str, Any]) -> ParsedSite | None:
        """
        Parse a single GeoJSON feature into a ParsedSite.

        The geojson.php response uses ``id`` at the feature level (not in
        properties), ``title`` instead of ``name``, numeric ``kind`` IDs,
        and ``url`` (relative path) instead of ``uri``.  Geometry may be
        a ``Point`` or a ``GeometryCollection`` containing a Point plus
        LineString(s) for roads/aqueducts.

        Args:
            feature: GeoJSON feature dict

        Returns:
            ParsedSite or None if invalid
        """
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})

        # Extract Point coordinates from geometry.
        # Geometry is either a Point directly or a GeometryCollection
        # whose first element is the Point.
        coords = self._extract_point_coords(geometry)
        if coords is None:
            return None

        lon, lat = coords[0], coords[1]

        # Skip null island
        if lat == 0 and lon == 0:
            return None

        # ID is at feature level, not in properties
        site_id = feature.get("id")
        if not site_id:
            return None
        site_id = str(site_id)

        # Name is "title" in the new API
        name = properties.get("title", "")
        if not name:
            return None

        # Source URL: API returns relative path like "/vici/123/"
        relative_url = properties.get("url", "")
        source_url = (
            f"https://vici.org{relative_url}"
            if relative_url
            else f"https://vici.org/vici/{site_id}/"
        )

        # Description from summary
        description = properties.get("summary")

        # Map site type from numeric 'kind'
        kind = properties.get("kind")
        site_type = self.KIND_MAPPING.get(kind, "other")

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

    @staticmethod
    def _extract_point_coords(geometry: dict[str, Any]) -> list[float] | None:
        """Extract [lon, lat] from a Point or GeometryCollection geometry."""
        geom_type = geometry.get("type")
        if geom_type == "Point":
            coords = geometry.get("coordinates", [])
            return coords if len(coords) >= 2 else None
        if geom_type == "GeometryCollection":
            for sub in geometry.get("geometries", []):
                if sub.get("type") == "Point":
                    coords = sub.get("coordinates", [])
                    return coords if len(coords) >= 2 else None
        return None


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
