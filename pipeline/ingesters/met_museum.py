"""
Metropolitan Museum of Art Collection ingester.

Downloads ancient art objects (Egyptian, Greek, Roman, Near Eastern)
with provenance locations from the Met's Open Access API.

Data source: https://metmuseum.github.io/
License: CC0 (Public Domain)
API Key: Not required
"""

import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

import httpx
from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json


class MetMuseumIngester(BaseIngester):
    """
    Ingester for Metropolitan Museum of Art ancient collections.

    Fetches objects from departments:
    - Egyptian Art
    - Greek and Roman Art
    - Ancient Near Eastern Art
    - Asian Art (ancient pieces)
    """

    source_id = "met_museum"
    source_name = "Metropolitan Museum of Art"

    # API endpoints
    API_BASE = "https://collectionapi.metmuseum.org/public/collection/v1"
    SEARCH_ENDPOINT = f"{API_BASE}/search"
    OBJECT_ENDPOINT = f"{API_BASE}/objects"

    # Department IDs for ancient art
    DEPARTMENTS = {
        10: "Egyptian Art",
        13: "Greek and Roman Art",
        3: "Ancient Near Eastern Art",
        6: "Asian Art",
    }

    # Search queries for ancient items
    SEARCH_QUERIES = [
        "ancient",
        "egyptian",
        "roman",
        "greek",
        "mesopotamian",
        "assyrian",
        "babylonian",
        "sumerian",
        "pharaoh",
        "mummy",
        "sarcophagus",
    ]

    MAX_PARALLEL = 20
    REQUEST_DELAY = 0.05  # Met API is generous with rate limits

    # Browser-like headers to avoid bot blocking
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Type mapping
    TYPE_MAPPING = {
        "sculpture": "sculpture",
        "statue": "sculpture",
        "relief": "sculpture",
        "stele": "monument",
        "sarcophagus": "tomb",
        "mummy": "tomb",
        "vessel": "artifact",
        "vase": "artifact",
        "amphora": "artifact",
        "jewelry": "artifact",
        "coin": "coin",
        "seal": "artifact",
        "tablet": "inscription",
        "papyrus": "text",
        "mosaic": "artwork",
        "fresco": "artwork",
        "painting": "artwork",
    }

    def fetch(self) -> Path:
        """Fetch ancient art objects from Met Museum API."""
        dest_path = self.raw_data_dir / "met_museum.json"

        logger.info("=" * 60)
        logger.info("MET MUSEUM - ANCIENT ART COLLECTION")
        logger.info("=" * 60)

        # Step 1: Get object IDs from relevant departments
        all_object_ids = set()

        logger.info("Fetching object IDs from ancient art departments...")
        self.report_progress(0, len(self.DEPARTMENTS), "fetching department IDs...")

        for i, (dept_id, dept_name) in enumerate(self.DEPARTMENTS.items()):
            try:
                url = f"{self.OBJECT_ENDPOINT}?departmentIds={dept_id}"
                with httpx.Client(timeout=60) as client:
                    response = client.get(url, headers=self.HEADERS)
                    if response.status_code == 200:
                        data = response.json()
                        ids = data.get("objectIDs", []) or []
                        all_object_ids.update(ids)
                        logger.info(f"  {dept_name}: {len(ids):,} objects")
            except Exception as e:
                logger.warning(f"  {dept_name}: failed - {e}")

            self.report_progress(i + 1, len(self.DEPARTMENTS), f"{len(all_object_ids):,} IDs")

        logger.info(f"Total unique object IDs: {len(all_object_ids):,}")

        # Limit for faster downloads - can increase later
        MAX_OBJECTS = 10000
        object_ids = list(all_object_ids)[:MAX_OBJECTS]
        logger.info(f"Fetching details for {len(object_ids):,} objects...")

        # Step 2: Fetch object details in parallel
        all_objects = []
        completed = 0
        failed = 0

        self.report_progress(0, len(object_ids), "fetching object details...")

        with ThreadPoolExecutor(max_workers=self.MAX_PARALLEL) as executor:
            future_to_id = {
                executor.submit(self._fetch_object, obj_id): obj_id
                for obj_id in object_ids
            }

            for future in as_completed(future_to_id):
                obj_id = future_to_id[future]
                completed += 1

                try:
                    obj = future.result()
                    if obj and self._has_location(obj):
                        all_objects.append(obj)
                except Exception:
                    failed += 1

                if completed % 1000 == 0:
                    self.report_progress(
                        completed, len(object_ids),
                        f"{len(all_objects):,} with locations"
                    )
                    logger.info(f"  Progress: {completed:,}/{len(object_ids):,} - {len(all_objects):,} with locations")

        logger.info("=" * 60)
        logger.info(f"COMPLETED: {len(all_objects):,} objects with location data")
        logger.info(f"Failed requests: {failed}")
        logger.info("=" * 60)

        # Save results
        output = {
            "objects": all_objects,
            "metadata": {
                "source": "Metropolitan Museum of Art",
                "source_url": "https://www.metmuseum.org/",
                "api_url": "https://metmuseum.github.io/",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_objects": len(all_objects),
                "departments": list(self.DEPARTMENTS.values()),
                "license": "CC0 (Public Domain)",
            }
        }

        atomic_write_json(dest_path, output)
        logger.info(f"Saved to {dest_path}")

        return dest_path

    def _fetch_object(self, object_id: int) -> Optional[Dict]:
        """Fetch a single object's details."""
        try:
            url = f"{self.OBJECT_ENDPOINT}/{object_id}"
            with httpx.Client(timeout=30) as client:
                response = client.get(url, headers=self.HEADERS)
                if response.status_code == 200:
                    return response.json()
        except Exception:
            pass
        return None

    def _has_location(self, obj: Dict) -> bool:
        """Check if object has usable location data."""
        # Check for geographic location fields
        location_fields = [
            "country", "region", "subregion", "locale", "locus",
            "excavation", "river", "city"
        ]
        for field in location_fields:
            if obj.get(field):
                return True
        return False

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse Met Museum objects into sites."""
        logger.info(f"Parsing Met Museum data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        objects = data.get("objects", [])
        logger.info(f"Processing {len(objects):,} objects")

        for obj in objects:
            site = self._parse_object(obj)
            if site:
                yield site

    def _parse_object(self, obj: Dict) -> Optional[ParsedSite]:
        """Parse a single Met object."""
        object_id = obj.get("objectID")
        if not object_id:
            return None

        # Build location string
        location_parts = []
        for field in ["locale", "locus", "excavation", "city", "subregion", "region", "country"]:
            if obj.get(field):
                location_parts.append(obj[field])

        location_name = ", ".join(location_parts) if location_parts else None
        if not location_name:
            return None

        # Try to get coordinates from known locations
        lat, lon = self._geocode_location(obj)

        # Get title
        title = obj.get("title", "")
        object_name = obj.get("objectName", "")
        name = title or object_name or f"Met Object {object_id}"

        # Get date range
        date_start = self._parse_year(obj.get("objectBeginDate"))
        date_end = self._parse_year(obj.get("objectEndDate"))

        # Get type
        classification = obj.get("classification", "")
        object_type = self._map_type(classification, object_name)

        # Build description
        desc_parts = []
        if obj.get("culture"):
            desc_parts.append(f"Culture: {obj['culture']}")
        if obj.get("period"):
            desc_parts.append(f"Period: {obj['period']}")
        if obj.get("dynasty"):
            desc_parts.append(f"Dynasty: {obj['dynasty']}")
        if obj.get("reign"):
            desc_parts.append(f"Reign: {obj['reign']}")
        if obj.get("medium"):
            desc_parts.append(f"Medium: {obj['medium']}")
        if obj.get("dimensions"):
            desc_parts.append(f"Dimensions: {obj['dimensions']}")

        description = "; ".join(desc_parts) if desc_parts else None

        return ParsedSite(
            source_id=f"met_{object_id}",
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[object_name] if object_name and object_name != name else [],
            description=description[:500] if description else None,
            site_type=object_type,
            period_start=date_start,
            period_end=date_end,
            period_name=obj.get("period"),
            precision_meters=10000,  # Museum provenance is often approximate
            precision_reason="museum_provenance",
            source_url=obj.get("objectURL", f"https://www.metmuseum.org/art/collection/search/{object_id}"),
            raw_data={
                "object_id": object_id,
                "department": obj.get("department"),
                "culture": obj.get("culture"),
                "location": location_name,
                "primary_image": obj.get("primaryImage"),
                "is_public_domain": obj.get("isPublicDomain"),
            },
        )

    def _geocode_location(self, obj: Dict) -> tuple:
        """Try to geocode object location based on known places."""
        country = obj.get("country", "").lower()
        region = obj.get("region", "").lower()
        city = obj.get("city", "").lower()

        # Known ancient site coordinates
        KNOWN_LOCATIONS = {
            # Egypt
            ("egypt", "thebes"): (25.7, 32.6),
            ("egypt", "luxor"): (25.7, 32.6),
            ("egypt", "karnak"): (25.72, 32.66),
            ("egypt", "giza"): (29.98, 31.13),
            ("egypt", "cairo"): (30.04, 31.24),
            ("egypt", "alexandria"): (31.2, 29.9),
            ("egypt", "memphis"): (29.85, 31.25),
            ("egypt", "abydos"): (26.18, 31.92),
            ("egypt", "amarna"): (27.65, 30.9),
            ("egypt", "aswan"): (24.09, 32.9),
            ("egypt", ""): (26.0, 30.0),  # Default Egypt
            # Greece
            ("greece", "athens"): (37.97, 23.73),
            ("greece", "corinth"): (37.91, 22.88),
            ("greece", "delphi"): (38.48, 22.5),
            ("greece", "olympia"): (37.64, 21.63),
            ("greece", ""): (39.0, 22.0),  # Default Greece
            # Italy
            ("italy", "rome"): (41.9, 12.5),
            ("italy", "pompeii"): (40.75, 14.49),
            ("italy", "naples"): (40.85, 14.27),
            ("italy", ""): (42.0, 12.5),  # Default Italy
            # Iraq (Mesopotamia)
            ("iraq", "babylon"): (32.54, 44.42),
            ("iraq", "ur"): (30.96, 46.1),
            ("iraq", "nineveh"): (36.36, 43.15),
            ("iraq", "nimrud"): (36.1, 43.33),
            ("iraq", ""): (33.0, 44.0),  # Default Iraq
            # Iran (Persia)
            ("iran", "persepolis"): (29.93, 52.89),
            ("iran", "susa"): (32.19, 48.26),
            ("iran", ""): (32.0, 53.0),  # Default Iran
            # Turkey
            ("turkey", "ephesus"): (37.94, 27.34),
            ("turkey", "troy"): (39.96, 26.24),
            ("turkey", ""): (39.0, 35.0),  # Default Turkey
            # Cyprus
            ("cyprus", ""): (35.0, 33.0),
            # Syria
            ("syria", ""): (35.0, 38.0),
            # Lebanon
            ("lebanon", ""): (33.9, 35.5),
            # Israel/Palestine
            ("israel", ""): (31.5, 35.0),
            ("palestine", ""): (31.5, 35.0),
            # Jordan
            ("jordan", ""): (31.0, 36.0),
            # Libya
            ("libya", ""): (27.0, 17.0),
            # Tunisia
            ("tunisia", "carthage"): (36.85, 10.32),
            ("tunisia", ""): (34.0, 9.0),
            # China
            ("china", ""): (35.0, 105.0),
            # India
            ("india", ""): (20.0, 78.0),
        }

        # Try to match location
        for (c, r), coords in KNOWN_LOCATIONS.items():
            if c in country:
                if r and r in f"{region} {city}".lower():
                    return coords
                elif not r:
                    return coords

        return None, None

    def _map_type(self, classification: str, object_name: str) -> str:
        """Map Met classification to site type."""
        text = f"{classification} {object_name}".lower()

        for key, site_type in self.TYPE_MAPPING.items():
            if key in text:
                return site_type

        return "artifact"

    def _parse_year(self, value) -> Optional[int]:
        """Parse year value."""
        if value is None:
            return None
        try:
            year = int(value)
            # Met uses negative for BCE
            return year
        except (ValueError, TypeError):
            return None


def ingest_met_museum(session=None, skip_fetch: bool = False) -> dict:
    """Run Met Museum ingestion."""
    with MetMuseumIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
