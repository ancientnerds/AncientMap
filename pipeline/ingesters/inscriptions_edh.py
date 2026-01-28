"""
Epigraphic Database Heidelberg (EDH) ingester.

EDH is one of the largest databases of Latin inscriptions,
containing 82,000+ records with texts, translations,
locations, and dating information.

Data source: https://edh.ub.uni-heidelberg.de/
Open Data: https://edh.ub.uni-heidelberg.de/data/download
License: CC BY-SA 4.0
API Key: Not required
"""

import csv
import io
import json
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
from datetime import datetime
import time
import re

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class EDHInscriptionsIngester(BaseIngester):
    """
    Ingester for Epigraphic Database Heidelberg (EDH).

    Downloads CSV bulk exports from EDH data portal and merges
    geographic and inscription text data.
    """

    source_id = "inscriptions_edh"
    source_name = "Epigraphic Database Heidelberg"

    # EDH CSV download URLs
    BASE_URL = "https://edh.ub.uni-heidelberg.de"
    GEO_CSV_URL = f"{BASE_URL}/data/download/edh_data_geo.csv"
    TEXT_CSV_URL = f"{BASE_URL}/data/download/edh_data_text.csv"

    def fetch(self) -> Path:
        """
        Fetch inscription data from EDH via CSV bulk downloads.

        Returns:
            Path to JSON file with inscription data
        """
        dest_path = self.raw_data_dir / "inscriptions_edh.json"

        logger.info("Fetching EDH inscription data via CSV bulk downloads...")
        self.report_progress(0, 3, "downloading geo data...")

        headers = {
            "User-Agent": "AncientNerds/1.0 (Research Platform; academic research)",
        }

        all_inscriptions = []
        geo_data = {}  # id -> geo info
        text_data = {}  # hd_nr -> text info

        # Step 1: Download geographic data
        logger.info("Downloading EDH geographic data CSV...")
        try:
            response = fetch_with_retry(
                self.GEO_CSV_URL,
                headers=headers,
                timeout=300,
            )

            if response.status_code == 200:
                # Parse CSV
                reader = csv.DictReader(io.StringIO(response.text))
                for row in reader:
                    geo_id = row.get("id", "")
                    if geo_id:
                        # Parse coordinates (format: "lat,lon")
                        coords = row.get("koordinaten_1", "")
                        lat, lon = None, None
                        if coords and "," in coords:
                            parts = coords.split(",")
                            if len(parts) == 2:
                                try:
                                    lat = float(parts[0].strip())
                                    lon = float(parts[1].strip())
                                except ValueError:
                                    pass

                        geo_data[geo_id] = {
                            "geo_id": geo_id,
                            "lat": lat,
                            "lon": lon,
                            "ancient_place": row.get("fo_antik", ""),
                            "modern_place": row.get("fo_modern", ""),
                            "province": row.get("provinz", ""),
                            "country": row.get("land", ""),
                            "pleiades_id": row.get("pleiades_id_1", ""),
                            "geonames_id": row.get("geonames_id_1", ""),
                        }

                logger.info(f"Loaded {len(geo_data):,} geographic records")

        except Exception as e:
            logger.warning(f"Failed to download geo CSV: {e}")

        self.report_progress(1, 3, "downloading text data...")

        # Step 2: Download text/inscription data
        logger.info("Downloading EDH text data CSV...")
        try:
            response = fetch_with_retry(
                self.TEXT_CSV_URL,
                headers=headers,
                timeout=300,
            )

            if response.status_code == 200:
                # Parse CSV
                reader = csv.DictReader(io.StringIO(response.text))
                for row in reader:
                    hd_nr = row.get("hd_nr", "")
                    if hd_nr:
                        text_data[hd_nr] = row

                logger.info(f"Loaded {len(text_data):,} text records")

        except Exception as e:
            logger.warning(f"Failed to download text CSV: {e}")

        self.report_progress(2, 3, "merging data...")

        # Step 3: Merge and create inscription records
        logger.info("Merging geographic and text data...")

        seen_ids = set()

        for hd_nr, text_row in text_data.items():
            # Extract geo_id from text data if present
            geo_id = text_row.get("geo_id1", text_row.get("geo_id", ""))

            # Get geographic info
            geo = geo_data.get(geo_id, {})

            # Try to get coordinates from text row if not in geo
            lat = geo.get("lat")
            lon = geo.get("lon")

            if lat is None:
                coords = text_row.get("koordinaten1", "")
                if coords and "," in coords:
                    parts = coords.split(",")
                    if len(parts) == 2:
                        try:
                            lat = float(parts[0].strip())
                            lon = float(parts[1].strip())
                        except ValueError:
                            pass

            insc = {
                "id": f"edh_{hd_nr}",
                "edh_id": hd_nr,
                "lat": lat,
                "lon": lon,
                "find_spot": text_row.get("fundstelle", ""),
                "ancient_place": geo.get("ancient_place", text_row.get("fo_antik", "")),
                "modern_place": geo.get("modern_place", text_row.get("fo_modern", "")),
                "province": text_row.get("provinz", geo.get("province", "")),
                "country": text_row.get("land", geo.get("country", "")),
                "inscription_text": text_row.get("litext", ""),
                "transcription": text_row.get("li", ""),
                "inscription_type": text_row.get("i_gattung", ""),
                "object_type": text_row.get("denkmaltyp", ""),
                "material": text_row.get("material", ""),
                "date_start": self._parse_year(text_row.get("dat_von", text_row.get("dat_jahr_a", ""))),
                "date_end": self._parse_year(text_row.get("dat_bis", text_row.get("dat_jahr_e", ""))),
                "height_cm": self._parse_float(text_row.get("hoehe", "")),
                "width_cm": self._parse_float(text_row.get("breite", "")),
                "depth_cm": self._parse_float(text_row.get("tiefe", "")),
                "letters_height_cm": self._parse_float(text_row.get("bh", "")),
                "current_location": text_row.get("aufbewahrung", ""),
                "pleiades_id": geo.get("pleiades_id", ""),
                "source_url": f"https://edh.ub.uni-heidelberg.de/edh/inschrift/{hd_nr}",
            }

            if insc["id"] not in seen_ids:
                seen_ids.add(insc["id"])
                all_inscriptions.append(insc)

        logger.info(f"Total inscriptions merged: {len(all_inscriptions):,}")
        self.report_progress(3, 3, f"{len(all_inscriptions):,} inscriptions")

        # Save to file
        output = {
            "inscriptions": all_inscriptions,
            "metadata": {
                "source": "Epigraphic Database Heidelberg",
                "source_url": "https://edh.ub.uni-heidelberg.de/",
                "data_download_url": "https://edh.ub.uni-heidelberg.de/data/download",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_inscriptions": len(all_inscriptions),
                "data_type": "latin_inscriptions",
                "license": "CC BY-SA 4.0",
                "citation": "Epigraphic Database Heidelberg, https://edh.ub.uni-heidelberg.de/",
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_inscriptions):,} inscriptions to {dest_path}")
        return dest_path

    def _parse_geojson_feature(self, feature: Dict) -> Optional[Dict]:
        """Parse a GeoJSON feature from EDH."""
        if not feature or feature.get("type") != "Feature":
            return None

        props = feature.get("properties", {})
        geom = feature.get("geometry", {})

        # Get coordinates
        lat, lon = None, None
        if geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        # Get ID
        edh_id = props.get("id", props.get("edh_id", props.get("HD", "")))
        if not edh_id:
            return None

        if not str(edh_id).startswith("HD"):
            edh_id = f"HD{edh_id}"

        return {
            "id": f"edh_{edh_id}",
            "edh_id": edh_id,
            "lat": lat,
            "lon": lon,
            "find_spot": props.get("findspot", props.get("fo", "")),
            "ancient_place": props.get("ancient_findspot", props.get("fo_antik", "")),
            "modern_place": props.get("modern_findspot", props.get("fo_modern", "")),
            "province": props.get("province", props.get("provinz", "")),
            "country": props.get("country", props.get("land", "")),
            "inscription_text": props.get("text", props.get("inschrift", "")),
            "inscription_type": props.get("type", props.get("inschriftgattung", "")),
            "material": props.get("material", ""),
            "date_text": props.get("date", props.get("datierung", "")),
            "date_start": self._parse_year(props.get("not_before", props.get("dat_von", ""))),
            "date_end": self._parse_year(props.get("not_after", props.get("dat_bis", ""))),
            "height_cm": self._parse_float(props.get("height", "")),
            "width_cm": self._parse_float(props.get("width", "")),
            "depth_cm": self._parse_float(props.get("depth", "")),
            "current_location": props.get("repository", props.get("aufbewahrung", "")),
            "bibliography": props.get("bibliography", props.get("literatur", "")),
            "commentary": props.get("commentary", props.get("kommentar", "")),
            "image_url": props.get("images", props.get("bilder", "")),
            "source_url": f"https://edh.ub.uni-heidelberg.de/edh/inschrift/{edh_id}",
        }

    def _parse_inscription(self, item: Dict) -> Optional[Dict]:
        """Parse an inscription from the search API."""
        if not item:
            return None

        # Get ID
        edh_id = item.get("id", item.get("hd_nr", item.get("HD", "")))
        if not edh_id:
            return None

        if not str(edh_id).startswith("HD"):
            edh_id = f"HD{edh_id}"

        # Get coordinates
        lat = self._parse_float(item.get("lat", item.get("geo_lat", "")))
        lon = self._parse_float(item.get("lon", item.get("geo_long", "")))

        # Alternative coordinate fields
        if lat is None:
            geo = item.get("geo", item.get("coordinates", {}))
            if isinstance(geo, dict):
                lat = self._parse_float(geo.get("lat", geo.get("latitude", "")))
                lon = self._parse_float(geo.get("lon", geo.get("lng", geo.get("longitude", ""))))
            elif isinstance(geo, str) and "," in geo:
                parts = geo.split(",")
                if len(parts) == 2:
                    lat = self._parse_float(parts[0])
                    lon = self._parse_float(parts[1])

        return {
            "id": f"edh_{edh_id}",
            "edh_id": edh_id,
            "lat": lat,
            "lon": lon,
            "find_spot": item.get("findspot", item.get("fo", "")),
            "ancient_place": item.get("ancient_findspot", item.get("fo_antik", "")),
            "modern_place": item.get("modern_findspot", item.get("fo_modern", "")),
            "province": item.get("province", item.get("provinz", "")),
            "country": item.get("country", item.get("land", "")),
            "inscription_text": item.get("text", item.get("inschrift", "")),
            "transcription": item.get("diplomatic", item.get("lesbar", "")),
            "inscription_type": item.get("type", item.get("inschriftgattung", "")),
            "object_type": item.get("objecttype", item.get("objekt_typ", "")),
            "material": item.get("material", ""),
            "language": item.get("language", item.get("sprache", "Latin")),
            "date_text": item.get("date", item.get("datierung", "")),
            "date_start": self._parse_year(item.get("not_before", item.get("dat_von", ""))),
            "date_end": self._parse_year(item.get("not_after", item.get("dat_bis", ""))),
            "height_cm": self._parse_float(item.get("height", item.get("hoehe", ""))),
            "width_cm": self._parse_float(item.get("width", item.get("breite", ""))),
            "depth_cm": self._parse_float(item.get("depth", item.get("tiefe", ""))),
            "letters_height_cm": self._parse_float(item.get("letter_height", item.get("buchstabenhoehe", ""))),
            "current_location": item.get("repository", item.get("aufbewahrung", "")),
            "inventory_number": item.get("inventory", item.get("inv_nr", "")),
            "bibliography": item.get("bibliography", item.get("literatur", "")),
            "commentary": item.get("commentary", item.get("kommentar", "")),
            "source_url": f"https://edh.ub.uni-heidelberg.de/edh/inschrift/{edh_id}",
        }

    def _parse_year(self, value) -> Optional[int]:
        """Parse a year value, handling BCE dates."""
        if not value or value in ["", "?"]:
            return None

        try:
            # Handle negative dates for BCE
            v = str(value).strip()
            if v.startswith("-"):
                return int(v)
            return int(v)
        except (ValueError, TypeError):
            return None

    def _parse_float(self, value) -> Optional[float]:
        """Parse a float value."""
        if not value or value in ["", "?"]:
            return None
        try:
            # Remove units if present
            v = re.sub(r'[^\d.\-]', '', str(value))
            return float(v) if v else None
        except (ValueError, TypeError):
            return None

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse EDH inscription data into ParsedSite objects."""
        logger.info(f"Parsing EDH data from {raw_data_path}")

        with open(raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        inscriptions = data.get("inscriptions", [])
        logger.info(f"Processing {len(inscriptions)} inscriptions")

        for insc in inscriptions:
            site = self._inscription_to_site(insc)
            if site:
                yield site

    def _inscription_to_site(self, insc: Dict) -> Optional[ParsedSite]:
        """Convert an inscription to a ParsedSite."""
        lat = insc.get("lat")
        lon = insc.get("lon")

        if lat is None or lon is None:
            return None

        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        if lat == 0 and lon == 0:
            return None

        # Build name
        name_parts = []
        if insc.get("inscription_type"):
            name_parts.append(insc["inscription_type"])
        if insc.get("ancient_place"):
            name_parts.append(f"from {insc['ancient_place']}")
        elif insc.get("find_spot"):
            name_parts.append(f"from {insc['find_spot']}")

        name = " ".join(name_parts) if name_parts else f"Inscription {insc['edh_id']}"

        # Build description
        desc_parts = []
        if insc.get("inscription_text"):
            # Truncate long inscriptions
            text = insc["inscription_text"][:300]
            if len(insc["inscription_text"]) > 300:
                text += "..."
            desc_parts.append(f"Text: {text}")
        if insc.get("material"):
            desc_parts.append(f"Material: {insc['material']}")
        if insc.get("date_text"):
            desc_parts.append(f"Date: {insc['date_text']}")

        # Determine period from dates
        period_name = None
        date_start = insc.get("date_start")
        date_end = insc.get("date_end")

        if date_start is not None or date_end is not None:
            mid_date = date_start if date_start is not None else date_end
            if mid_date < -500:
                period_name = "Republican"
            elif mid_date < -27:
                period_name = "Late Republican"
            elif mid_date < 68:
                period_name = "Julio-Claudian"
            elif mid_date < 96:
                period_name = "Flavian"
            elif mid_date < 192:
                period_name = "Antonine"
            elif mid_date < 284:
                period_name = "Severan/Crisis"
            elif mid_date < 476:
                period_name = "Late Imperial"

        return ParsedSite(
            source_id=insc["id"],
            name=name,
            lat=lat,
            lon=lon,
            alternative_names=[insc.get("edh_id", "")],
            description="; ".join(desc_parts) if desc_parts else None,
            site_type="inscription",
            period_start=date_start,
            period_end=date_end,
            period_name=period_name,
            precision_meters=500,
            precision_reason="findspot",
            source_url=insc.get("source_url", "https://edh.ub.uni-heidelberg.de/"),
            raw_data={k: v for k, v in insc.items() if v is not None and k not in ["lat", "lon"]},
        )


def ingest_edh_inscriptions(session=None, skip_fetch: bool = False) -> dict:
    """Run EDH inscriptions ingestion."""
    with EDHInscriptionsIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
