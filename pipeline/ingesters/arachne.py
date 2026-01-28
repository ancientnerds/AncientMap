"""
Arachne (iDAI.objects) ingester.

Arachne is the central object database of the German Archaeological Institute
(DAI) and the Archaeological Institute of the University of Cologne.
It contains millions of objects, images, and archaeological site data.

Data source: https://arachne.dainst.org/
License: CC-BY
API Key: Not required
"""

import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import time

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry, RateLimitError


class ArachneIngester(BaseIngester):
    """
    Ingester for Arachne (iDAI.objects) database.

    Arachne provides a REST API that returns JSON data.
    We query for entities of type "Ort" (place) and "Bauwerk" (building)
    that have coordinates.
    """

    source_id = "arachne"
    source_name = "Arachne (iDAI)"

    # API endpoints
    API_BASE = "https://arachne.dainst.org"
    SEARCH_ENDPOINT = "/data/search"
    ENTITY_ENDPOINT = "/data/entity"

    # Search terms for archaeological sites (German and English)
    SEARCH_TERMS = [
        "tempel",       # temple
        "theater",      # theater
        "amphitheater", # amphitheater
        "forum",        # forum
        "basilika",     # basilica
        "therme",       # bath
        "villa",        # villa
        "grab",         # tomb
        "nekropole",    # necropolis
        "festung",      # fortress
        "kastell",      # fort
        "heiligtum",    # sanctuary
        "aquädukt",     # aqueduct
        "temple",       # temple (english)
        "ruins",        # ruins
        "sanctuary",    # sanctuary
    ]

    # Pagination
    PAGE_SIZE = 100
    MAX_PER_TERM = 10000  # Limit per search term
    REQUEST_DELAY = 0.5

    # Category to site type mapping
    TYPE_MAPPING = {
        "tempel": "temple",
        "temple": "temple",
        "theater": "theater",
        "amphitheater": "amphitheater",
        "forum": "monument",
        "basilika": "church",
        "basilica": "church",
        "kirche": "church",
        "church": "church",
        "therme": "bath",
        "bath": "bath",
        "villa": "villa",
        "palast": "palace",
        "palace": "palace",
        "grab": "tomb",
        "tomb": "tomb",
        "nekropole": "cemetery",
        "necropolis": "cemetery",
        "friedhof": "cemetery",
        "cemetery": "cemetery",
        "festung": "fortress",
        "fortress": "fortress",
        "fort": "fortress",
        "kastell": "fortress",
        "stadtmauer": "monument",
        "wall": "monument",
        "aquädukt": "aqueduct",
        "aqueduct": "aqueduct",
        "brücke": "bridge",
        "bridge": "bridge",
        "straße": "road",
        "road": "road",
        "hafen": "port",
        "harbor": "port",
        "port": "port",
        "heiligtum": "sanctuary",
        "sanctuary": "sanctuary",
        "altar": "sanctuary",
        "stadion": "stadium",
        "stadium": "stadium",
    }

    def fetch(self) -> Path:
        """
        Fetch data from Arachne API.

        Searches for archaeological terms to find records with locations.

        Returns:
            Path to JSON file with all results
        """
        dest_path = self.raw_data_dir / "arachne.json"

        all_results = []
        seen_ids = set()  # Deduplicate across terms

        logger.info("Fetching Arachne (iDAI) data...")

        headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform)",
        }

        for term in self.SEARCH_TERMS:
            logger.info(f"Searching for: {term}")
            offset = 0
            term_count = 0

            while term_count < self.MAX_PER_TERM:
                params = {
                    "q": term,
                    "limit": self.PAGE_SIZE,
                    "offset": offset,
                }

                try:
                    response = fetch_with_retry(
                        f"{self.API_BASE}{self.SEARCH_ENDPOINT}",
                        params=params,
                        headers=headers,
                        timeout=60,
                    )
                    data = response.json()
                except RateLimitError:
                    logger.warning("Rate limited. Waiting 60 seconds...")
                    time.sleep(60)
                    continue
                except Exception as e:
                    logger.error(f"Error fetching '{term}' at offset {offset}: {e}")
                    break

                entities = data.get("entities", [])
                if not entities:
                    break

                # Filter for entities with coordinates and deduplicate
                for entity in entities:
                    entity_id = entity.get("entityId")
                    if entity_id in seen_ids:
                        continue

                    places = entity.get("places", [])
                    # Check if any place has coordinates
                    has_coords = False
                    for place in places:
                        if isinstance(place, dict):
                            loc = place.get("location", {})
                            if loc.get("lat") and loc.get("lon"):
                                has_coords = True
                                break

                    if has_coords:
                        entity["search_term"] = term
                        all_results.append(entity)
                        seen_ids.add(entity_id)
                        term_count += 1

                logger.debug(f"  {term}: {term_count:,} records with locations")
                self.report_progress(len(all_results), None, f"{len(all_results):,} ({term})")

                total = data.get("size", 0)
                if offset + self.PAGE_SIZE >= total:
                    break

                offset += self.PAGE_SIZE
                time.sleep(self.REQUEST_DELAY)

            logger.info(f"  Total '{term}': {term_count:,} records")

        logger.info(f"Total Arachne records with locations: {len(all_results):,}")

        # Save to file
        output = {
            "results": all_results,
            "metadata": {
                "source": "Arachne (iDAI)",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_fetched": len(all_results),
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_results):,} records to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Arachne JSON data.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Arachne data from {raw_data_path}")

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
        Parse a single Arachne result.

        Args:
            result: Entity dict

        Returns:
            ParsedSite or None if invalid
        """
        entity_id = str(result.get("entity_id", ""))
        if not entity_id:
            return None

        title = result.get("title", "")
        if not title:
            return None

        # Get coordinates from places
        places = result.get("places", [])
        if not places:
            return None

        # Use first place with coordinates
        lat, lon = None, None
        place_name = None

        for place in places:
            if isinstance(place, dict):
                place_lat = place.get("lat")
                place_lon = place.get("lon")
                if place_lat and place_lon:
                    try:
                        lat = float(place_lat)
                        lon = float(place_lon)
                        place_name = place.get("name", "")
                        break
                    except (ValueError, TypeError):
                        continue
            elif isinstance(place, str):
                # Sometimes places is a string reference
                continue

        if lat is None or lon is None:
            return None

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Map type
        subtitle = result.get("subtitle", "")
        category = result.get("category", "")
        site_type = self._map_type(title, subtitle, category)

        # Build description
        desc_parts = []
        if subtitle:
            desc_parts.append(subtitle)
        if place_name:
            desc_parts.append(f"Location: {place_name}")
        if category:
            desc_parts.append(f"Category: {category}")

        description = "; ".join(desc_parts) if desc_parts else None

        # Source URL
        source_url = f"https://arachne.dainst.org/entity/{entity_id}"

        return ParsedSite(
            source_id=entity_id,
            name=title,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description[:500] if description else None,
            site_type=site_type,
            period_start=None,
            period_end=None,
            period_name=None,
            precision_meters=100,
            precision_reason="arachne",
            source_url=source_url,
            raw_data={
                "entity_id": entity_id,
                "title": title,
                "subtitle": subtitle,
                "category": category,
                "place_name": place_name,
            },
        )

    def _map_type(self, title: str, subtitle: str, category: str) -> str:
        """Map Arachne data to site type."""
        search_text = f"{title} {subtitle} {category}".lower()

        for key, value in self.TYPE_MAPPING.items():
            if key in search_text:
                return value

        # Default based on category
        if category == "bauwerk":
            return "monument"

        return "other"


def ingest_arachne(session=None, skip_fetch: bool = False) -> dict:
    """Run Arachne ingestion."""
    with ArachneIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
