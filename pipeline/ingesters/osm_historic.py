"""
OpenStreetMap Historic Sites ingester.

Downloads ~500K historic/archaeological sites from OSM by querying
Overpass API in PARALLEL for maximum speed.

Data source: https://www.openstreetmap.org/
License: ODbL (Open Database License)
"""

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json


class OSMHistoricIngester(BaseIngester):
    """
    Ingester for OpenStreetMap historic sites.

    Downloads ALL regions and tags in PARALLEL for speed.
    """

    source_id = "osm_historic"
    source_name = "OpenStreetMap Historic Sites"

    # Overpass API endpoints - we'll distribute load across all
    OVERPASS_ENDPOINTS = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]

    # Historic tags to fetch
    HISTORIC_TAGS = [
        "archaeological_site",  # 220K
        "ruins",                # 173K
        "tomb",                 # 72K
        "monument",             # 71K
        "castle",               # 53K
        "citywalls",            # 17K
        "fort",                 # 9K
        "roman_road",           # 4K
        "megalith",             # ~3K
        "city_gate",            # 9K
        "aqueduct",             # ~2K
        "temple",               # ~1K
    ]

    # World divided into regions (south, west, north, east)
    REGIONS = {
        # Europe
        "europe_iberia": (35, -10, 44, 5),
        "europe_france": (42, -5, 51, 8),
        "europe_britain": (49, -11, 61, 2),
        "europe_italy": (36, 6, 47, 19),
        "europe_balkans": (35, 13, 47, 30),
        "europe_greece": (34, 19, 42, 30),
        "europe_central": (45, 5, 55, 20),
        "europe_eastern": (44, 20, 56, 40),
        "europe_nordic": (54, 4, 72, 32),
        # Middle East & North Africa
        "mideast_turkey": (35, 25, 42, 45),
        "mideast_levant": (29, 34, 38, 43),
        "mideast_egypt": (22, 24, 32, 37),
        "mideast_iraq": (29, 38, 38, 49),
        "mideast_iran": (25, 44, 40, 64),
        "africa_north": (25, -10, 38, 25),
        "africa_libya": (19, 9, 34, 26),
        # Asia
        "asia_central": (35, 50, 55, 80),
        "asia_india": (6, 68, 36, 98),
        "asia_china_west": (25, 73, 45, 105),
        "asia_china_east": (20, 105, 45, 135),
        "asia_japan": (30, 128, 46, 146),
        "asia_southeast": (-10, 95, 25, 120),
        # Americas
        "americas_mexico": (14, -120, 33, -85),
        "americas_caribbean": (10, -90, 28, -60),
        "americas_central": (7, -92, 18, -77),
        "americas_peru": (-20, -82, 0, -68),
        "americas_andes": (-40, -76, -15, -62),
        "americas_usa_east": (24, -100, 50, -65),
        "americas_usa_west": (30, -130, 50, -100),
        # Other
        "oceania": (-50, 110, -10, 180),
        "africa_sub": (-35, -20, 20, 55),
    }

    # Parallel settings
    MAX_PARALLEL = 20  # Number of concurrent requests
    TIMEOUT = 300  # Timeout per request in seconds

    # Site type mapping
    TYPE_MAPPING = {
        "archaeological_site": "archaeological_site",
        "ruins": "ruins",
        "tomb": "tomb",
        "monument": "monument",
        "castle": "fortress",
        "fort": "fortress",
        "fortification": "fortress",
        "citywalls": "fortification",
        "city_gate": "fortification",
        "megalith": "megalith",
        "roman_road": "road",
        "aqueduct": "aqueduct",
        "temple": "temple",
    }

    def fetch(self) -> Path:
        """
        Fetch historic sites from OSM Overpass API - ALL IN PARALLEL.
        """
        dest_path = self.raw_data_dir / "osm_historic.json"

        logger.info("=" * 60)
        logger.info("OSM HISTORIC - PARALLEL DOWNLOAD")
        logger.info("=" * 60)

        # Build all query combinations
        all_queries = []
        for tag in self.HISTORIC_TAGS:
            for region_name, bbox in self.REGIONS.items():
                all_queries.append((tag, region_name, bbox))

        total_queries = len(all_queries)
        logger.info(f"Total queries to execute: {total_queries}")
        logger.info(f"Parallel workers: {self.MAX_PARALLEL}")
        logger.info(f"Endpoints: {len(self.OVERPASS_ENDPOINTS)}")

        # Run all queries in parallel
        all_elements = []
        seen_ids = set()
        completed = 0
        failed = 0

        self.report_progress(0, total_queries, "starting parallel download...")

        with ThreadPoolExecutor(max_workers=self.MAX_PARALLEL) as executor:
            # Submit all queries
            future_to_query = {
                executor.submit(self._query_overpass_sync, tag, bbox, i % len(self.OVERPASS_ENDPOINTS)): (tag, region_name, bbox)
                for i, (tag, region_name, bbox) in enumerate(all_queries)
            }

            # Process results as they complete
            for future in as_completed(future_to_query):
                tag, region_name, bbox = future_to_query[future]
                completed += 1

                try:
                    elements = future.result()

                    # Deduplicate
                    new_count = 0
                    for elem in elements:
                        elem_id = f"{elem.get('type', 'node')}_{elem.get('id', '')}"
                        if elem_id not in seen_ids:
                            seen_ids.add(elem_id)
                            all_elements.append(elem)
                            new_count += 1

                    if new_count > 0:
                        logger.info(f"[{completed}/{total_queries}] {tag}/{region_name}: +{new_count:,} (total: {len(all_elements):,})")

                except Exception as e:
                    failed += 1
                    logger.warning(f"[{completed}/{total_queries}] {tag}/{region_name}: FAILED - {e}")

                # Update progress
                self.report_progress(completed, total_queries, f"{len(all_elements):,} sites")

        # Final save
        logger.info("=" * 60)
        logger.info(f"COMPLETED: {len(all_elements):,} total sites")
        logger.info(f"Failed queries: {failed}")
        logger.info("=" * 60)

        output = {
            "elements": all_elements,
            "metadata": {
                "source": "OpenStreetMap",
                "source_url": "https://www.openstreetmap.org/",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_sites": len(all_elements),
                "license": "ODbL (Open Database License)",
                "tags_queried": self.HISTORIC_TAGS,
                "regions_queried": list(self.REGIONS.keys()),
                "failed_queries": failed,
            }
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved to {dest_path}")

        return dest_path

    def _query_overpass_sync(self, tag: str, bbox: tuple, endpoint_idx: int = 0) -> list[dict]:
        """Query Overpass API synchronously (for thread pool)."""
        south, west, north, east = bbox

        query = f"""[out:json][timeout:{self.TIMEOUT}];
(
  node["historic"="{tag}"]({south},{west},{north},{east});
  way["historic"="{tag}"]({south},{west},{north},{east});
);
out center;"""

        # Try assigned endpoint first, then others
        endpoints = self.OVERPASS_ENDPOINTS[endpoint_idx:] + self.OVERPASS_ENDPOINTS[:endpoint_idx]

        for endpoint in endpoints:
            try:
                with httpx.Client(timeout=self.TIMEOUT) as client:
                    response = client.post(
                        endpoint,
                        data={"data": query},
                        headers={"User-Agent": "AncientNerds/1.0 (Research Platform)"},
                    )

                if response.status_code == 200:
                    data = response.json()
                    if "elements" in data:
                        return data["elements"]
                    elif "remark" in data and "error" in data["remark"].lower():
                        continue  # Try next endpoint

            except Exception:
                continue  # Try next endpoint

        return []

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse OSM historic sites data."""
        logger.info(f"Parsing OSM historic data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        elements = data.get("elements", [])
        logger.info(f"Processing {len(elements):,} elements")

        for element in elements:
            site = self._parse_element(element)
            if site:
                yield site

    def _parse_element(self, element: dict[str, Any]) -> ParsedSite | None:
        """Parse a single OSM element."""
        elem_type = element.get("type", "")
        elem_id = element.get("id", "")
        tags = element.get("tags", {})

        # Get coordinates
        if elem_type == "node":
            lat = element.get("lat")
            lon = element.get("lon")
        elif elem_type in ("way", "relation"):
            center = element.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")
        else:
            return None

        if lat is None or lon is None:
            return None

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Extract tags
        name = tags.get("name", tags.get("name:en", ""))
        historic = tags.get("historic", "")
        site_type_tag = tags.get("site_type", tags.get("archaeological_site", ""))
        wikidata = tags.get("wikidata", "")
        description = tags.get("description", "")
        start_date = tags.get("start_date", "")

        if not name:
            name = f"OSM {historic} {elem_id}"

        # Map type
        site_type = self.TYPE_MAPPING.get(historic, "other")

        # Build description
        desc_parts = []
        if historic:
            desc_parts.append(f"Historic: {historic}")
        if site_type_tag:
            desc_parts.append(f"Site type: {site_type_tag}")
        if description:
            desc_parts.append(description[:200])

        full_desc = "; ".join(desc_parts) if desc_parts else None

        # Parse dates if available
        period_start = self._parse_date(start_date)

        # Source URL
        source_url = f"https://www.openstreetmap.org/{elem_type}/{elem_id}"

        return ParsedSite(
            source_id=f"{elem_type}_{elem_id}",
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=full_desc[:500] if full_desc else None,
            site_type=site_type,
            period_start=period_start,
            period_end=None,
            period_name=None,
            precision_meters=50,
            precision_reason="osm",
            source_url=source_url,
            raw_data={
                "osm_type": elem_type,
                "osm_id": elem_id,
                "historic": historic,
                "wikidata": wikidata,
            },
        )

    def _parse_date(self, date_str: str) -> int | None:
        """Parse OSM date string to year."""
        if not date_str:
            return None

        try:
            if date_str.startswith("-"):
                return int(date_str)
            if date_str.isdigit():
                return int(date_str)
            if "-" in date_str:
                return int(date_str.split("-")[0])
        except (ValueError, IndexError):
            pass

        return None


def ingest_osm_historic(session=None, skip_fetch: bool = False) -> dict:
    """Run OSM historic sites ingestion."""
    with OSMHistoricIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
