"""
David Rumsey Historical Map Collection ingester.

The David Rumsey Collection contains 150,000+ historical maps,
with 60,000+ georeferenced. Now housed at Stanford University.

Data source: https://www.davidrumsey.com/
License: CC-BY-NC (non-commercial use)
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


class DavidRumseyIngester(BaseIngester):
    """
    Ingester for David Rumsey Historical Map Collection.

    Uses the LUNA API to fetch map metadata. The collection has
    excellent coverage of historical world maps and regional atlases.
    """

    source_id = "david_rumsey"
    source_name = "David Rumsey Map Collection"

    # LUNA API endpoint
    API_URL = "https://www.davidrumsey.com/luna/servlet/as/search"

    # Search queries for GEOREFERENCED ancient/historical maps
    # Adding "georeferenced" to each query ensures we get maps with bbox data
    SEARCHES = [
        # Ancient world maps - georeferenced only
        {"q": "ancient georeferenced", "sort": "date"},
        {"q": "roman empire georeferenced", "sort": "date"},
        {"q": "greece georeferenced", "sort": "date"},
        {"q": "egypt georeferenced", "sort": "date"},
        {"q": "mesopotamia georeferenced", "sort": "date"},
        {"q": "mediterranean georeferenced", "sort": "date"},
        {"q": "holy land georeferenced", "sort": "date"},
        {"q": "asia minor georeferenced", "sort": "date"},
        {"q": "ptolemy georeferenced", "sort": "date"},
        # Medieval
        {"q": "medieval georeferenced", "sort": "date"},
        # Archaeological
        {"q": "archaeological georeferenced", "sort": "date"},
        {"q": "ruins georeferenced", "sort": "date"},
        {"q": "pompeii georeferenced", "sort": "date"},
        # Regional historical - georeferenced
        {"q": "britain georeferenced", "sort": "date"},
        {"q": "france georeferenced", "sort": "date"},
        {"q": "italy georeferenced", "sort": "date"},
        {"q": "spain georeferenced", "sort": "date"},
        {"q": "persia georeferenced", "sort": "date"},
        {"q": "india georeferenced", "sort": "date"},
        {"q": "china georeferenced", "sort": "date"},
        {"q": "turkey georeferenced", "sort": "date"},
        {"q": "syria georeferenced", "sort": "date"},
        {"q": "iraq georeferenced", "sort": "date"},
        {"q": "israel georeferenced", "sort": "date"},
        {"q": "africa georeferenced", "sort": "date"},
        # Americas
        {"q": "mexico georeferenced", "sort": "date"},
        {"q": "peru georeferenced", "sort": "date"},
        {"q": "central america georeferenced", "sort": "date"},
        # General georeferenced searches
        {"q": "georeferenced historical", "sort": "date"},
    ]

    PAGE_SIZE = 100
    MAX_RESULTS_PER_SEARCH = 1000
    REQUEST_DELAY = 1.0

    def fetch(self) -> Path:
        """
        Fetch map metadata from David Rumsey Collection.

        Returns:
            Path to JSON file with map metadata
        """
        dest_path = self.raw_data_dir / "david_rumsey.json"

        logger.info("Fetching David Rumsey map metadata...")
        self.report_progress(0, len(self.SEARCHES), "starting...")

        all_maps = []
        seen_ids = set()

        headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform)",
        }

        for i, search in enumerate(self.SEARCHES):
            query = search.get("q", "")
            logger.info(f"Searching: {query}")
            self.report_progress(i, len(self.SEARCHES), f"'{query}'")

            offset = 0
            search_results = 0

            while search_results < self.MAX_RESULTS_PER_SEARCH:
                try:
                    params = {
                        "q": query,
                        "lc": "RUMSEY~8~1",  # Collection ID
                        "sort": search.get("sort", "date"),
                        "start": offset,
                        "rows": self.PAGE_SIZE,
                        "format": "json",
                    }

                    response = fetch_with_retry(
                        self.API_URL,
                        params=params,
                        headers=headers,
                        timeout=60,
                    )

                    data = response.json()
                    results = data.get("results", [])

                    if not results:
                        break

                    for item in results:
                        item_id = item.get("id", item.get("urlSize0", ""))
                        if item_id and item_id not in seen_ids:
                            seen_ids.add(item_id)

                            # Parse fieldValues into a flat dict
                            fields = {}
                            for fv in item.get("fieldValues", []):
                                for key, val in fv.items():
                                    fields[key] = val[0] if isinstance(val, list) and val else val

                            # Extract bbox from multiple possible field names
                            bbox = (
                                fields.get("Bounds", "") or
                                fields.get("bounds", "") or
                                fields.get("Bounding Box", "") or
                                item.get("bounds", "") or
                                item.get("bbox", "")
                            )

                            # Only save maps that have bbox data for geographic matching
                            if not bbox:
                                continue

                            # Extract key metadata
                            map_data = {
                                "id": item_id,
                                "title": item.get("displayName", fields.get("Short Title", "")),
                                "date": fields.get("Date", ""),
                                "author": fields.get("Author", ""),
                                "publisher": fields.get("Publisher", ""),
                                "description": item.get("description", ""),
                                "subject": fields.get("Subject", []),
                                "coverage": fields.get("Country", ""),
                                "type": fields.get("Type", ""),
                                "iiif_manifest": item.get("iiifManifest", ""),
                                "thumbnail": item.get("urlSize1", ""),
                                "full_image": item.get("urlSize4", ""),
                                "georeferenced": True,
                                "bbox": bbox,
                            }
                            all_maps.append(map_data)
                            search_results += 1

                    if len(results) < self.PAGE_SIZE:
                        break

                    offset += self.PAGE_SIZE
                    time.sleep(self.REQUEST_DELAY)

                except Exception as e:
                    logger.warning(f"Error searching '{query}' at offset {offset}: {e}")
                    break

            logger.info(f"  '{query}': {search_results:,} maps (total unique: {len(all_maps):,})")

        logger.info(f"Total maps fetched: {len(all_maps):,}")
        self.report_progress(len(self.SEARCHES), len(self.SEARCHES), f"{len(all_maps):,} maps")

        # Save to file
        output = {
            "maps": all_maps,
            "metadata": {
                "source": "David Rumsey Map Collection",
                "source_url": "https://www.davidrumsey.com/",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_maps": len(all_maps),
                "data_type": "historical_maps",
                "license": "CC-BY-NC",
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_maps):,} maps to {dest_path}")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse David Rumsey data - maps go to separate table."""
        logger.info(f"Parsing David Rumsey data from {raw_data_path}")
        return iter([])


def ingest_david_rumsey(session=None, skip_fetch: bool = False) -> dict:
    """Run David Rumsey ingestion."""
    with DavidRumseyIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
