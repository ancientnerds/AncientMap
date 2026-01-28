"""
Europeana Cultural Heritage ingester.

Downloads ancient and archaeological cultural heritage items from Europeana's
aggregated database of European museums, archives, and libraries.

Data source: https://www.europeana.eu/
API docs: https://pro.europeana.eu/page/search
License: Varies by item (CC0, CC BY, CC BY-SA, etc.)
API Key: Required (free registration)
"""

import json
import os
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

import httpx
from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.config import get_ai_thread_limit


class EuropeanaIngester(BaseIngester):
    """
    Ingester for Europeana cultural heritage collection.

    Fetches archaeological and ancient items from the aggregated
    European cultural heritage database.
    """

    source_id = "europeana"
    source_name = "Europeana"

    # API endpoints
    API_BASE = "https://api.europeana.eu/record/v2"
    SEARCH_ENDPOINT = f"{API_BASE}/search.json"

    # Search queries for ancient/archaeological content
    SEARCH_QUERIES = [
        "archaeological site",
        "ancient ruins",
        "roman archaeology",
        "greek archaeology",
        "egyptian archaeology",
        "prehistoric site",
        "bronze age",
        "iron age",
        "neolithic",
        "megalithic",
        "ancient temple",
        "ancient tomb",
        "ancient monument",
        "roman villa",
        "roman road",
        "ancient mosaic",
        "ancient sculpture",
        "ancient coin",
        "ancient inscription",
    ]

    # Europeana data providers with archaeological focus
    PROVIDERS = [
        "Rijksmuseum",
        "British Museum",
        "Louvre",
        "Archaeological Museum",
        "National Museum",
    ]

    MAX_RECORDS = 100000  # Limit per query
    RECORDS_PER_PAGE = 100
    MAX_PARALLEL = min(10, get_ai_thread_limit())  # Cap at 10 for API rate limits
    REQUEST_DELAY = 0.2  # Europeana rate limits

    # Type mapping
    TYPE_MAPPING = {
        "archaeological site": "archaeological_site",
        "ruins": "ruins",
        "temple": "temple",
        "tomb": "tomb",
        "monument": "monument",
        "villa": "settlement",
        "mosaic": "artwork",
        "sculpture": "sculpture",
        "coin": "coin",
        "inscription": "inscription",
        "pottery": "artifact",
        "ceramic": "artifact",
        "statue": "sculpture",
        "relief": "sculpture",
        "fresco": "artwork",
        "sarcophagus": "tomb",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get API key from config.json or environment
        from pipeline.api_config import get_europeana_api_key

        self.api_key = get_europeana_api_key() or ""
        if not self.api_key:
            logger.warning("Europeana API key not set - will use demo key with limited access")
            logger.warning("Get your key at: https://pro.europeana.eu/page/get-api")
            # Europeana provides a demo key for testing
            self.api_key = "api2demo"

    def fetch(self) -> Path:
        """Fetch archaeological items from Europeana API."""
        dest_path = self.raw_data_dir / "europeana.json"

        logger.info("=" * 60)
        logger.info("EUROPEANA - CULTURAL HERITAGE COLLECTION")
        logger.info("=" * 60)

        all_items = []
        seen_ids = set()

        total_queries = len(self.SEARCH_QUERIES)
        self.report_progress(0, total_queries, "searching...")

        for i, query in enumerate(self.SEARCH_QUERIES):
            if len(all_items) >= self.MAX_RECORDS:
                break

            logger.info(f"Searching: '{query}'...")
            items = self._search_query(query, seen_ids)
            all_items.extend(items)

            self.report_progress(i + 1, total_queries, f"{len(all_items):,} items")
            logger.info(f"  Found {len(items)} new items (total: {len(all_items):,})")

            time.sleep(self.REQUEST_DELAY)

        logger.info("=" * 60)
        logger.info(f"COMPLETED: {len(all_items):,} items with location data")
        logger.info("=" * 60)

        # Save results
        output = {
            "items": all_items,
            "metadata": {
                "source": "Europeana",
                "source_url": "https://www.europeana.eu/",
                "api_url": "https://pro.europeana.eu/page/search",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_items": len(all_items),
                "queries": self.SEARCH_QUERIES,
                "license": "Varies by item",
            }
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved to {dest_path}")

        return dest_path

    def _search_query(self, query: str, seen_ids: set) -> List[Dict]:
        """Search for items matching a query."""
        items = []
        cursor = "*"

        while len(items) < self.MAX_RECORDS // len(self.SEARCH_QUERIES):
            try:
                params = {
                    "wskey": self.api_key,
                    "query": query,
                    "qf": [
                        "pl_wgs84_pos_lat:*",  # Must have coordinates
                        "TYPE:IMAGE OR TYPE:3D",  # Focus on visual items
                    ],
                    "rows": self.RECORDS_PER_PAGE,
                    "cursor": cursor,
                    "profile": "rich",
                }

                with httpx.Client(timeout=60) as client:
                    response = client.get(self.SEARCH_ENDPOINT, params=params)

                    if response.status_code == 429:
                        # Rate limited - wait and retry
                        time.sleep(5)
                        continue

                    if response.status_code != 200:
                        logger.warning(f"Search failed: {response.status_code}")
                        break

                    data = response.json()

                if not data.get("success"):
                    break

                results = data.get("items", [])
                if not results:
                    break

                for item in results:
                    item_id = item.get("id")
                    if item_id and item_id not in seen_ids:
                        # Check for location data
                        if self._has_location(item):
                            seen_ids.add(item_id)
                            items.append(item)

                # Get next cursor
                cursor = data.get("nextCursor")
                if not cursor:
                    break

                time.sleep(self.REQUEST_DELAY)

            except Exception as e:
                logger.warning(f"Search error: {e}")
                break

        return items

    def _has_location(self, item: Dict) -> bool:
        """Check if item has usable location data."""
        # Check for WGS84 coordinates
        if item.get("edmPlaceLatitude") and item.get("edmPlaceLongitude"):
            return True

        # Check for enrichment coordinates
        enrichments = item.get("europeanaAggregation", {})
        if enrichments.get("edmPlaceLatitude") and enrichments.get("edmPlaceLongitude"):
            return True

        return False

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse Europeana items into sites."""
        logger.info(f"Parsing Europeana data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data.get("items", [])
        logger.info(f"Processing {len(items):,} items")

        for item in items:
            site = self._parse_item(item)
            if site:
                yield site

    def _parse_item(self, item: Dict) -> Optional[ParsedSite]:
        """Parse a single Europeana item."""
        item_id = item.get("id")
        if not item_id:
            return None

        # Get coordinates
        lat = self._get_first(item.get("edmPlaceLatitude"))
        lon = self._get_first(item.get("edmPlaceLongitude"))

        if lat is None or lon is None:
            return None

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return None

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        # Get title
        title = self._get_first(item.get("title")) or self._get_first(item.get("dcTitleLangAware", {}).get("en"))
        if not title:
            title = f"Europeana {item_id}"

        # Get description
        description = self._get_first(item.get("dcDescription"))

        # Get date
        date_str = self._get_first(item.get("year"))
        date_start, date_end = self._parse_date_range(date_str)

        # Get type
        dc_type = self._get_first(item.get("type"))
        item_type = self._map_type(title, description, dc_type)

        # Get place name
        place_name = self._get_first(item.get("edmPlaceLabel"))

        # Get provider
        provider = self._get_first(item.get("dataProvider"))

        # Build source URL
        source_url = f"https://www.europeana.eu/en/item{item_id}"

        # Get thumbnail
        thumbnail = self._get_first(item.get("edmPreview"))

        return ParsedSite(
            source_id=f"europeana_{item_id.replace('/', '_')}",
            name=title[:200] if title else f"Europeana Item {item_id}",
            lat=lat,
            lon=lon,
            alternative_names=[place_name] if place_name and place_name != title else [],
            description=description[:500] if description else None,
            site_type=item_type,
            period_start=date_start,
            period_end=date_end,
            precision_meters=5000,  # Museum metadata often approximate
            precision_reason="cultural_heritage_metadata",
            source_url=source_url,
            raw_data={
                "europeana_id": item_id,
                "provider": provider,
                "type": dc_type,
                "thumbnail": thumbnail,
                "place_label": place_name,
                "rights": self._get_first(item.get("rights")),
            },
        )

    def _get_first(self, value) -> Optional[str]:
        """Get first value from list or return value if string."""
        if isinstance(value, list):
            return value[0] if value else None
        return value

    def _parse_date_range(self, date_str) -> tuple:
        """Parse date string to year range."""
        if not date_str:
            return None, None

        try:
            # Handle single year
            year = int(date_str)
            return year, year
        except (ValueError, TypeError):
            pass

        # Handle ranges like "100-200" or "100 BC - 50 AD"
        if isinstance(date_str, str):
            date_str = date_str.lower()
            if "bc" in date_str or "bce" in date_str:
                # Ancient dates - try to extract
                import re
                numbers = re.findall(r'\d+', date_str)
                if numbers:
                    year = -int(numbers[0])
                    return year, year

        return None, None

    def _map_type(self, title: str, description: str, dc_type: str) -> str:
        """Map item to site type."""
        text = f"{title or ''} {description or ''} {dc_type or ''}".lower()

        for key, site_type in self.TYPE_MAPPING.items():
            if key in text:
                return site_type

        return "artifact"


def ingest_europeana(session=None, skip_fetch: bool = False) -> dict:
    """Run Europeana ingestion."""
    with EuropeanaIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
