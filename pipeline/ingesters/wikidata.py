"""
Wikidata archaeological sites ingester.

Fetches archaeological sites from Wikidata using SPARQL queries.
Wikidata is a free knowledge base with millions of items including
archaeological sites, historic monuments, and ancient places.

Data source: https://www.wikidata.org/
License: CC0 (Public Domain)
API Key: Not required
"""

import json
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class WikidataIngester(BaseIngester):
    """
    Ingester for Wikidata archaeological sites.

    Uses SPARQL queries to fetch:
    - Archaeological sites (Q839954)
    - Ancient cities (Q15661340)
    - Historic monuments (Q4989906)
    - Ruins (Q109607)
    - UNESCO World Heritage Sites with archaeological significance

    Wikidata has excellent global coverage and links to Wikipedia.
    """

    source_id = "wikidata"
    source_name = "Wikidata"

    # Wikidata SPARQL endpoint
    SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

    # Rate limiting
    REQUEST_DELAY = 2.0  # Wikidata recommends delays between queries

    # Simpler SPARQL query - query one type at a time to avoid timeouts
    SPARQL_QUERY = """
    SELECT ?item ?itemLabel ?itemDescription ?coord ?countryLabel
    WHERE {{
      ?item wdt:P31 wd:{type_id} .
      ?item wdt:P625 ?coord .
      OPTIONAL {{ ?item wdt:P17 ?country . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }}
    LIMIT {limit}
    OFFSET {offset}
    """

    # Types to query (one at a time to avoid timeouts)
    WIKIDATA_TYPES = [
        ("Q839954", "archaeological site"),
        ("Q15661340", "ancient city"),
        ("Q109607", "ruins"),
        ("Q23413", "castle"),
        ("Q57821", "fortification"),
        ("Q44539", "temple"),
        ("Q16970", "church building"),
        ("Q32815", "mosque"),
        ("Q39614", "cemetery"),
        ("Q381885", "tumulus"),
        ("Q152095", "megalith"),
        ("Q35112", "amphitheater"),
        ("Q11315", "aqueduct"),
    ]

    # Batch size for SPARQL queries
    BATCH_SIZE = 5000
    MAX_RECORDS_PER_TYPE = 50000  # Limit per type

    # Wikidata class to site type mapping
    TYPE_MAPPING = {
        "archaeological site": "other",
        "ancient city": "settlement",
        "historic monument": "monument",
        "ruins": "other",
        "church": "church",
        "mosque": "mosque",
        "temple": "temple",
        "monastery": "church",
        "castle": "fortress",
        "fortification": "fortress",
        "cemetery": "cemetery",
        "tumulus": "tumulus",
        "megalith": "megalith",
        "amphitheater": "amphitheater",
        "amphitheatre": "amphitheater",
        "aqueduct": "aqueduct",
        "road": "road",
        "bridge": "bridge",
        "tower": "monument",
    }

    def fetch(self) -> Path:
        """
        Fetch data from Wikidata via SPARQL.

        Queries each type separately to avoid timeout issues.

        Returns:
            Path to JSON file with all results
        """
        dest_path = self.raw_data_dir / "wikidata.json"

        all_results = []

        logger.info("Fetching archaeological sites from Wikidata...")

        for type_id, type_name in self.WIKIDATA_TYPES:
            logger.info(f"Fetching {type_name} (wd:{type_id})...")
            offset = 0
            type_count = 0

            while offset < self.MAX_RECORDS_PER_TYPE:
                query = self.SPARQL_QUERY.format(
                    type_id=type_id,
                    limit=self.BATCH_SIZE,
                    offset=offset
                )

                try:
                    results = self._execute_sparql(query)
                except Exception as e:
                    logger.error(f"Error fetching {type_name} at offset {offset}: {e}")
                    break

                if not results:
                    break

                # Add type info to results
                for r in results:
                    r["_type_name"] = type_name

                all_results.extend(results)
                type_count += len(results)
                logger.debug(f"  {type_name}: {type_count:,} records")
                self.report_progress(len(all_results), None, f"{len(all_results):,} ({type_name})")

                if len(results) < self.BATCH_SIZE:
                    break

                offset += self.BATCH_SIZE
                time.sleep(self.REQUEST_DELAY)

            logger.info(f"  Total {type_name}: {type_count:,} records")
            time.sleep(self.REQUEST_DELAY)

        logger.info(f"Total Wikidata records: {len(all_results):,}")

        # Save to file
        output = {
            "results": all_results,
            "metadata": {
                "source": "Wikidata",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_fetched": len(all_results),
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_results):,} records to {dest_path}")
        return dest_path

    def _execute_sparql(self, query: str) -> list[dict]:
        """
        Execute a SPARQL query against Wikidata.

        Args:
            query: SPARQL query string

        Returns:
            List of result bindings
        """
        headers = {
            "Accept": "application/sparql-results+json",
            # Wikidata requires proper User-Agent with contact info per https://w.wiki/4wJS
            "User-Agent": "AncientNerds/1.0 (Research Platform; https://ancientnerds.com; contact@ancientnerds.com) Python/httpx",
        }

        params = {"query": query}

        response = fetch_with_retry(
            self.SPARQL_ENDPOINT,
            params=params,
            headers=headers,
            timeout=120,
        )

        data = response.json()
        return data.get("results", {}).get("bindings", [])

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Wikidata SPARQL results.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Wikidata data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8") as f:
            data = json.load(f)

        results = data.get("results", [])
        logger.info(f"Processing {len(results):,} results")

        # Deduplicate by item ID (same item may appear with different types)
        seen_items = set()

        for result in results:
            item_uri = result.get("item", {}).get("value", "")
            item_id = item_uri.split("/")[-1] if item_uri else ""

            if item_id in seen_items:
                continue
            seen_items.add(item_id)

            site = self._parse_result(result)
            if site:
                yield site

    def _parse_result(self, result: dict[str, Any]) -> ParsedSite | None:
        """
        Parse a single SPARQL result binding.

        Args:
            result: SPARQL result binding dict

        Returns:
            ParsedSite or None if invalid
        """
        # Extract item ID
        item_uri = result.get("item", {}).get("value", "")
        item_id = item_uri.split("/")[-1] if item_uri else ""

        if not item_id:
            return None

        # Extract label
        name = result.get("itemLabel", {}).get("value", "")
        if not name or name == item_id:  # Skip if no proper label
            return None

        # Parse coordinates (format: "Point(lon lat)")
        coord_str = result.get("coord", {}).get("value", "")
        if not coord_str:
            return None

        try:
            # Parse "Point(lon lat)" format
            coord_str = coord_str.replace("Point(", "").replace(")", "")
            lon, lat = map(float, coord_str.split())
        except (ValueError, IndexError):
            return None

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Extract other fields
        description = result.get("itemDescription", {}).get("value", "")
        country = result.get("countryLabel", {}).get("value", "")
        # Use _type_name from our query, or fall back to instanceLabel
        instance_type = result.get("_type_name", "") or result.get("instanceLabel", {}).get("value", "")

        # Map type
        site_type = self._map_type(instance_type)

        # Parse dates
        period_start = self._parse_wikidata_date(result.get("inception", {}).get("value"))
        period_end = self._parse_wikidata_date(result.get("dissolution", {}).get("value"))

        # Source URL
        source_url = f"https://www.wikidata.org/wiki/{item_id}"

        return ParsedSite(
            source_id=item_id,
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description[:500] if description else None,
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            period_name=None,
            precision_meters=100,
            precision_reason="wikidata",
            source_url=source_url,
            raw_data={
                "item": item_id,
                "name": name,
                "country": country,
                "instance_type": instance_type,
                "description": description[:200] if description else "",
            },
        )

    def _map_type(self, instance_type: str) -> str:
        """Map Wikidata instance type to our site type."""
        if not instance_type:
            return "other"

        type_lower = instance_type.lower()
        for key, value in self.TYPE_MAPPING.items():
            if key in type_lower:
                return value

        return "other"

    def _parse_wikidata_date(self, date_str: str | None) -> int | None:
        """
        Parse Wikidata date string to year.

        Wikidata dates can be:
        - ISO format: "2023-01-15T00:00:00Z"
        - Year only: "1500-01-01T00:00:00Z"
        - BCE dates: "-0500-01-01T00:00:00Z"

        Returns:
            Year as integer (negative for BCE) or None
        """
        if not date_str:
            return None

        try:
            # Handle BCE dates
            if date_str.startswith("-"):
                year_str = date_str[1:5]
                return -int(year_str)
            else:
                year_str = date_str[:4]
                return int(year_str)
        except (ValueError, IndexError):
            return None


def ingest_wikidata(session=None, skip_fetch: bool = False) -> dict:
    """Run Wikidata ingestion."""
    with WikidataIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
