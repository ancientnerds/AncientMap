"""
Megalithic Portal ingester.

The Megalithic Portal is the world's largest database of prehistoric
and ancient sites, with 25,000+ megalithic monuments worldwide.

Data source: https://www.megalithic.co.uk/
License: Free KMZ download (membership for CSV)
API Key: Not required for KMZ
"""

import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import re

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import download_file


class MegalithicPortalIngester(BaseIngester):
    """
    Ingester for Megalithic Portal data.

    Downloads the free KMZ file which contains 25,000+ prehistoric
    sites worldwide including stone circles, dolmens, standing stones,
    chambered tombs, hillforts, and more.
    """

    source_id = "megalithic_portal"
    source_name = "Megalithic Portal"

    # KMZ download URL (public, no auth required)
    KMZ_URL = "http://www.megalithic.co.uk/downloads/megalithic_earth.kmz"

    # Site type mapping from Megalithic Portal categories
    TYPE_MAPPING = {
        "stone circle": "megalith",
        "standing stone": "megalith",
        "menhir": "megalith",
        "dolmen": "megalith",
        "portal tomb": "megalith",
        "passage tomb": "tomb",
        "passage grave": "tomb",
        "chambered tomb": "tomb",
        "chambered cairn": "tomb",
        "wedge tomb": "tomb",
        "court tomb": "tomb",
        "gallery grave": "tomb",
        "long barrow": "tumulus",
        "round barrow": "tumulus",
        "barrow": "tumulus",
        "cairn": "tumulus",
        "tumulus": "tumulus",
        "henge": "megalith",
        "cursus": "monument",
        "hillfort": "fortress",
        "hill fort": "fortress",
        "promontory fort": "fortress",
        "ringfort": "fortress",
        "fort": "fortress",
        "broch": "fortress",
        "dun": "fortress",
        "crannog": "settlement",
        "settlement": "settlement",
        "rock art": "rock_art",
        "cup and ring": "rock_art",
        "petroglyph": "rock_art",
        "carved stone": "rock_art",
        "holy well": "sanctuary",
        "sacred well": "sanctuary",
        "spring": "sanctuary",
        "cross": "monument",
        "high cross": "monument",
        "round tower": "monument",
        "church": "church",
        "chapel": "church",
        "abbey": "church",
        "priory": "church",
        "monastery": "church",
        "hermitage": "church",
        "castle": "fortress",
        "tower house": "fortress",
        "souterrain": "other",
        "fogou": "other",
        "alignment": "megalith",
        "stone row": "megalith",
        "cist": "tomb",
        "kist": "tomb",
        "cromlech": "megalith",
        "quoit": "megalith",
    }

    def fetch(self) -> Path:
        """
        Download Megalithic Portal KMZ file.

        Returns:
            Path to extracted JSON file
        """
        kmz_path = self.raw_data_dir / "megalithic_portal.kmz"
        json_path = self.raw_data_dir / "megalithic_portal.json"

        logger.info(f"Downloading Megalithic Portal KMZ from {self.KMZ_URL}")
        self.report_progress(0, None, "downloading KMZ...")

        # Download KMZ file
        download_file(
            url=self.KMZ_URL,
            dest_path=kmz_path,
            force=True,
        )

        logger.info("Extracting and parsing KMZ...")
        self.report_progress(0, None, "parsing KMZ...")

        # Parse KMZ (which is a ZIP containing KML)
        sites = self._parse_kmz(kmz_path)

        logger.info(f"Extracted {len(sites):,} sites from KMZ")

        # Save as JSON for easier re-parsing
        output = {
            "sites": sites,
            "metadata": {
                "source": "Megalithic Portal",
                "source_url": "https://www.megalithic.co.uk/",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_sites": len(sites),
            }
        }

        atomic_write_json(json_path, output)
        self.report_progress(len(sites), len(sites), f"{len(sites):,} sites")

        # Clean up KMZ
        if kmz_path.exists():
            kmz_path.unlink()

        logger.info(f"Saved {len(sites):,} sites to {json_path}")
        return json_path

    def _parse_kmz(self, kmz_path: Path) -> List[Dict]:
        """
        Parse KMZ file and extract site data.

        Args:
            kmz_path: Path to KMZ file

        Returns:
            List of site dictionaries
        """
        sites = []

        with zipfile.ZipFile(kmz_path, 'r') as zf:
            # Find the KML file inside
            kml_files = [f for f in zf.namelist() if f.endswith('.kml')]
            if not kml_files:
                logger.error("No KML file found in KMZ")
                return sites

            for kml_file in kml_files:
                with zf.open(kml_file) as f:
                    kml_content = f.read()
                    sites.extend(self._parse_kml(kml_content))

        return sites

    def _parse_kml(self, kml_content: bytes) -> List[Dict]:
        """
        Parse KML content and extract placemarks.

        Args:
            kml_content: Raw KML bytes

        Returns:
            List of site dictionaries
        """
        sites = []

        # Parse XML
        root = ET.fromstring(kml_content)

        # KML namespace
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}

        # Also try without namespace for older KML files
        for placemark in root.iter():
            if placemark.tag.endswith('Placemark'):
                site = self._parse_placemark(placemark, ns)
                if site:
                    sites.append(site)

        return sites

    def _parse_placemark(self, placemark: ET.Element, ns: Dict) -> Optional[Dict]:
        """
        Parse a single KML Placemark element.

        Args:
            placemark: XML Element
            ns: Namespace dict

        Returns:
            Site dict or None
        """
        # Helper to get text from element
        def get_text(elem, tag):
            for child in elem.iter():
                if child.tag.endswith(tag):
                    return child.text
            return None

        name = get_text(placemark, 'name')
        description = get_text(placemark, 'description')
        coordinates = get_text(placemark, 'coordinates')

        if not name or not coordinates:
            return None

        # Parse coordinates (lon,lat,alt format)
        try:
            coord_parts = coordinates.strip().split(',')
            lon = float(coord_parts[0])
            lat = float(coord_parts[1])
        except (ValueError, IndexError):
            return None

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None
        if lat == 0 and lon == 0:
            return None

        # Extract site type from name or description
        site_type = "megalith"  # Default for this source
        name_lower = name.lower()

        # Try to extract ID from description (usually contains link)
        site_id = None
        if description:
            # Look for article.php?sid=XXXXXXX pattern
            match = re.search(r'sid=(\d+)', description)
            if match:
                site_id = match.group(1)

        if not site_id:
            # Generate ID from name and coordinates
            site_id = f"{name[:30]}_{lat:.4f}_{lon:.4f}".replace(" ", "_")

        return {
            "id": site_id,
            "name": name,
            "lat": lat,
            "lon": lon,
            "description": description,
            "raw_type": name_lower,
        }

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Megalithic Portal JSON data.

        Yields:
            ParsedSite objects
        """
        logger.info(f"Parsing Megalithic Portal data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        sites = data.get("sites", [])
        logger.info(f"Processing {len(sites):,} sites")

        for site in sites:
            parsed = self._parse_site(site)
            if parsed:
                yield parsed

    def _parse_site(self, site: Dict[str, Any]) -> Optional[ParsedSite]:
        """
        Parse a single site dictionary.

        Args:
            site: Site dict from JSON

        Returns:
            ParsedSite or None
        """
        site_id = site.get("id", "")
        name = site.get("name", "")
        lat = site.get("lat")
        lon = site.get("lon")

        if not site_id or not name or lat is None or lon is None:
            return None

        # Map type
        site_type = self._map_type(site.get("raw_type", ""))

        # Clean description (may contain HTML)
        description = site.get("description", "")
        if description:
            # Strip HTML tags
            description = re.sub(r'<[^>]+>', '', description)
            description = description[:500]

        # Build source URL
        if site_id.isdigit():
            source_url = f"https://www.megalithic.co.uk/article.php?sid={site_id}"
        else:
            source_url = "https://www.megalithic.co.uk/"

        return ParsedSite(
            source_id=str(site_id),
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[],
            description=description if description else None,
            site_type=site_type,
            period_start=None,
            period_end=None,
            period_name="Prehistoric",
            precision_meters=100,
            precision_reason="megalithic_portal",
            source_url=source_url,
            raw_data={
                "id": site_id,
                "name": name,
                "raw_type": site.get("raw_type", ""),
            },
        )

    def _map_type(self, raw_type: str) -> str:
        """Map Megalithic Portal type to our site type."""
        if not raw_type:
            return "megalith"

        raw_lower = raw_type.lower()
        for key, value in self.TYPE_MAPPING.items():
            if key in raw_lower:
                return value

        return "megalith"  # Default for this source


def ingest_megalithic_portal(session=None, skip_fetch: bool = False) -> dict:
    """Run Megalithic Portal ingestion."""
    with MegalithicPortalIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
