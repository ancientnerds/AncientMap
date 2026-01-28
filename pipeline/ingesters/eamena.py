"""
EAMENA (Endangered Archaeology in Middle East & North Africa) ingester.

EAMENA documents over 338,000 archaeological sites across the Middle East
and North Africa. It uses the Arches platform for data management.

Data source: https://database.eamena.org/
License: CC-BY-SA 4.0
API Key: Required for bulk access (apply through EAMENA)
"""

import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import time

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry, RateLimitError


class EAMENAIngester(BaseIngester):
    """
    Ingester for EAMENA archaeological data.

    EAMENA uses the Arches platform which provides a REST API.
    The API requires authentication for bulk data access.

    Note: You need to apply for API access at https://eamena.org/
    """

    source_id = "eamena"
    source_name = "EAMENA"

    # EAMENA v5 API endpoints (LDP-based)
    API_BASE = "https://database.eamena.org"
    RESOURCES_ENDPOINT = "/resources/"

    # Heritage Place resource model ID in EAMENA
    HERITAGE_PLACE_RESOURCE_MODEL = "34cfe98e-c2c0-11ea-9026-02e7594ce0a0"

    # Pagination - EAMENA lists 500 resources per page
    RESOURCES_PER_PAGE = 500
    MAX_RESOURCES = 50000  # Limit to avoid overwhelming the server
    REQUEST_DELAY = 0.5  # Delay between individual resource fetches

    # EAMENA site function to site type mapping
    TYPE_MAPPING = {
        "settlement": "settlement",
        "habitation": "settlement",
        "city": "settlement",
        "village": "settlement",
        "town": "settlement",
        "camp": "settlement",
        "fort": "fortress",
        "fortification": "fortress",
        "castle": "fortress",
        "citadel": "fortress",
        "military": "fortress",
        "religious": "temple",
        "temple": "temple",
        "church": "church",
        "mosque": "mosque",
        "synagogue": "temple",
        "shrine": "sanctuary",
        "monastery": "church",
        "tomb": "tomb",
        "burial": "tomb",
        "cemetery": "cemetery",
        "necropolis": "cemetery",
        "monument": "monument",
        "megalith": "megalith",
        "rock art": "rock_art",
        "petroglyph": "rock_art",
        "inscription": "monument",
        "quarry": "quarry",
        "mine": "mine",
        "water": "aqueduct",
        "dam": "aqueduct",
        "cistern": "aqueduct",
        "canal": "aqueduct",
        "road": "road",
        "bridge": "bridge",
        "bath": "bath",
        "theater": "theater",
        "amphitheater": "amphitheater",
        "stadium": "stadium",
        "palace": "palace",
        "villa": "villa",
        "tower": "monument",
        "wall": "monument",
        "tell": "settlement",
        "mound": "settlement",
        "cave": "cave",
    }

    def fetch(self) -> Path:
        """
        Fetch data from EAMENA v5 LDP API.

        First gets list of resource URIs, then fetches each resource individually.
        This is slower but works with the current EAMENA v5 API.

        Returns:
            Path to JSON file with all results
        """
        dest_path = self.raw_data_dir / "eamena.json"

        all_results = []

        logger.info("Fetching EAMENA heritage places via LDP API...")

        headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform)",
        }

        # First, get list of resource URIs
        try:
            response = fetch_with_retry(
                f"{self.API_BASE}{self.RESOURCES_ENDPOINT}",
                headers=headers,
                timeout=120,
            )
            data = response.json()
        except Exception as e:
            logger.error(f"Error fetching resources list: {e}")
            return dest_path

        resource_uris = data.get("ldp:contains", [])
        logger.info(f"Found {len(resource_uris):,} resource URIs")

        # Limit to MAX_RESOURCES
        resource_uris = resource_uris[:self.MAX_RESOURCES]
        logger.info(f"Fetching first {len(resource_uris):,} resources...")

        # Fetch each resource
        for i, uri in enumerate(resource_uris):
            try:
                response = fetch_with_retry(uri, headers=headers, timeout=30)
                resource_data = response.json()

                # Extract geometry from resource
                resource = resource_data.get("resource", {})
                geometry_list = resource.get("Geometry", [])

                if geometry_list:
                    # Resource has geometry, add to results
                    all_results.append({
                        "resourceinstanceid": resource_data.get("resourceinstanceid"),
                        "displayname": resource_data.get("displayname"),
                        "displaydescription": resource_data.get("displaydescription"),
                        "resource": resource,
                    })

                if (i + 1) % 100 == 0:
                    logger.info(f"Processed {i + 1:,} / {len(resource_uris):,} resources, {len(all_results):,} with geometry")

                self.report_progress(i + 1, len(resource_uris), f"{i + 1:,}/{len(resource_uris):,}")

            except Exception as e:
                logger.debug(f"Error fetching {uri}: {e}")
                continue

            time.sleep(self.REQUEST_DELAY)

        logger.info(f"Total EAMENA records with geometry: {len(all_results):,}")

        # Save to file
        output = {
            "results": all_results,
            "metadata": {
                "source": "EAMENA",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_fetched": len(all_results),
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_results):,} records to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse EAMENA JSON data.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing EAMENA data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        results = data.get("results", [])
        logger.info(f"Processing {len(results):,} results")

        for result in results:
            site = self._parse_result(result)
            if site:
                yield site

    def _parse_result(self, result: Dict[str, Any]) -> Optional[ParsedSite]:
        """
        Parse a single EAMENA v5 resource.

        Args:
            result: Resource dict from LDP API

        Returns:
            ParsedSite or None if invalid
        """
        resource_id = result.get("resourceinstanceid", "")
        if not resource_id:
            return None

        display_name = result.get("displayname", "")
        if not display_name:
            return None

        # Extract geometry from resource
        resource = result.get("resource", {})
        geometry_list = resource.get("Geometry", [])

        if not geometry_list:
            return None

        # Parse the geometry (stored as JSON string in @value)
        lat, lon = None, None
        for geom_entry in geometry_list:
            geom_expr = geom_entry.get("Geometric Place Expression", {})
            geom_str = geom_expr.get("@value", "")

            if not geom_str:
                continue

            try:
                import ast
                geom_data = ast.literal_eval(geom_str)

                if isinstance(geom_data, dict) and "features" in geom_data:
                    for feature in geom_data["features"]:
                        geom = feature.get("geometry", {})
                        geom_type = geom.get("type", "")
                        coords = geom.get("coordinates", [])

                        if geom_type == "Point" and len(coords) >= 2:
                            lon, lat = coords[0], coords[1]
                            break
                        elif geom_type == "Polygon" and coords:
                            ring = coords[0]
                            if ring:
                                lon = sum(c[0] for c in ring) / len(ring)
                                lat = sum(c[1] for c in ring) / len(ring)
                                break
                    if lat is not None:
                        break
            except Exception:
                continue

        if lat is None or lon is None:
            return None

        # Validate coordinates (MENA region roughly)
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Extract site function from resource
        site_function = self._extract_resource_value(resource, "Site Feature Form Type")
        site_type = self._map_type(site_function)

        # Extract other fields
        description = result.get("displaydescription", "")
        assessment = resource.get("Assessment Summary", {})
        condition = self._extract_resource_value(resource, "Overall Condition")

        # Build description
        desc_parts = []
        if description:
            desc_parts.append(description[:300])
        if condition:
            desc_parts.append(f"Condition: {condition}")
        if site_function:
            desc_parts.append(f"Type: {site_function}")

        full_description = "; ".join(desc_parts) if desc_parts else None

        # Source URL
        source_url = f"https://database.eamena.org/resources/{resource_id}"

        return ParsedSite(
            source_id=resource_id,
            name=display_name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=full_description[:1000] if full_description else None,
            site_type=site_type,
            period_start=None,
            period_end=None,
            period_name=None,
            precision_meters=100,
            precision_reason="eamena",
            source_url=source_url,
            raw_data={
                "resource_id": resource_id,
                "displayname": display_name,
                "site_function": site_function,
            },
        )

    def _extract_resource_value(self, resource: Dict, key: str) -> Optional[str]:
        """
        Extract a value from EAMENA v5 resource structure.

        Args:
            resource: Resource dict
            key: Key to search for

        Returns:
            Value string or None
        """
        def search_dict(obj, target_key):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if target_key.lower() in k.lower():
                        if isinstance(v, str):
                            return v
                        elif isinstance(v, list) and v:
                            first = v[0]
                            if isinstance(first, str):
                                return first
                            elif isinstance(first, dict):
                                return search_dict(first, target_key)
                    result = search_dict(v, target_key)
                    if result:
                        return result
            elif isinstance(obj, list):
                for item in obj:
                    result = search_dict(item, target_key)
                    if result:
                        return result
            return None

        return search_dict(resource, key)

    def _map_type(self, site_function: Optional[str]) -> str:
        """Map EAMENA site function to our site type."""
        if not site_function:
            return "other"

        func_lower = site_function.lower()
        for key, value in self.TYPE_MAPPING.items():
            if key in func_lower:
                return value

        return "other"


def ingest_eamena(session=None, skip_fetch: bool = False) -> dict:
    """Run EAMENA ingestion."""
    with EAMENAIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
