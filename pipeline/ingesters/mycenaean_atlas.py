"""
Mycenaean Atlas Project ingester.

The Mycenaean Atlas Project (by Robert Consoli) is a comprehensive
georeferenced database of ~5,600 Bronze Age Aegean archaeological sites.

Data source: https://www.helladic.info/
License: CC BY-SA 4.0
API Key: Not required

The original domain mycenaean-atlas.org is dead (DNS failure).
The project moved to helladic.info which serves data via PHP-rendered
HTML tables. This ingester scrapes the gazetteer pages by region and
combines them into a local CSV.
"""

import csv
import io
import re
import time
from collections.abc import Iterator
from html import unescape
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_bytes
from pipeline.utils.http import fetch_with_retry

# Base URL for the Mycenaean Atlas on helladic.info
BASE_URL = "https://www.helladic.info"

# All top-level regions available on helladic.info (from the RegionCtrl dropdown).
# Each tuple is (region_name, zoom_level) matching the dropdown option values.
REGIONS = [
    "Achaea",
    "Achaea Phthiotis",
    "Aeolian Islands",
    "Aetolia",
    "Aetolia-Acharnania",
    "Ainis",
    "Anatolia",
    "Antikythera",
    "Arcadia",
    "Argolid",
    "Attica",
    "Boeotia",
    "Calabria",
    "Corinthia",
    "Crete",
    "Cyclades",
    "Cyprus",
    "Dodecanese",
    "Dolopia",
    "Doris",
    "Egypt",
    "Elis",
    "Epirus",
    "Euboea",
    "Eurytania",
    "Ionian Islands",
    "Italy",
    "Kythera",
    "Laconia",
    "Levant",
    "Locris",
    "Macedonia",
    "Magnesia",
    "Malis",
    "Malta",
    "Megaris",
    "Messenia",
    "NE Aegean",
    "Pamphylia",
    "Pelasgiotis",
    "Perraibia",
    "Phocis",
    "Phrygia",
    "Phthiotis",
    "Pieria",
    "Pisidia",
    "Pontis",
    "Psara",
    "Sardinia",
    "Saronic",
    "Seleucia",
    "Sicily",
    "Spain",
    "Sporades",
    "Sudan",
    "Syria",
    "Thesprotia",
    "Thessaly",
    "Thrace",
    "Triphylia",
    "Troezenia",
]

# Gazetteer endpoint: returns an HTML table with columns
# Place Key | Site Name | Region | Subregion | Latitude | Longitude | Accuracy (m) | Elevation (m)
GAZETTEER_URL = f"{BASE_URL}/MAPC/gazetteerList.php"

# CSV column names we produce
CSV_COLUMNS = [
    "place_key",
    "site_name",
    "region",
    "subregion",
    "latitude",
    "longitude",
    "accuracy_m",
    "elevation_m",
]

# Site type mapping from site name keywords (the gazetteer doesn't include
# a type column, so we infer from the site name)
TYPE_MAPPING = {
    "tomb": "tomb",
    "tholos": "tomb",
    "chamber tomb": "tomb",
    "cist": "tomb",
    "grave": "tomb",
    "burial": "tomb",
    "cemetery": "tomb",
    "necropolis": "tomb",
    "fortress": "fortress",
    "citadel": "fortress",
    "acropolis": "fortress",
    "fortification": "fortress",
    "fort": "fortress",
    "settlement": "settlement",
    "habitation": "settlement",
    "village": "settlement",
    "town": "settlement",
    "city": "settlement",
    "palace": "settlement",
    "sanctuary": "sanctuary",
    "shrine": "sanctuary",
    "temple": "sanctuary",
    "peak sanctuary": "sanctuary",
    "cave": "cave",
    "workshop": "workshop",
    "quarry": "quarry",
    "mine": "mine",
    "harbor": "port",
    "harbour": "port",
    "port": "port",
    " hab": "settlement",
    "pottery": "other",
    "sherds": "other",
    "wall": "fortress",
    "well": "other",
    "lithics": "other",
    "artifacts": "other",
    "building": "settlement",
    "house": "settlement",
    "cem": "tomb",
}

# Regex to extract <td> cell contents from an HTML table row
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
# Regex to strip HTML tags from cell content
_TAG_RE = re.compile(r"<[^>]+>")


def _map_site_type(name: str) -> str:
    """Infer site type from site name keywords."""
    if not name:
        return "other"
    name_lower = name.strip().lower()
    for key, value in TYPE_MAPPING.items():
        if key in name_lower:
            return value
    return "other"


def _parse_gazetteer_html(html: str) -> list[dict]:
    """
    Parse an HTML gazetteer page into a list of row dicts.

    The gazetteer page contains an HTML table with columns:
    Place Key | Site Name | Region | Subregion | Latitude | Longitude | Accuracy (m) | Elevation (m)

    Returns:
        List of dicts with keys matching CSV_COLUMNS.
    """
    rows = []

    # Split on <tr> to get table rows
    tr_parts = html.split("<tr>")
    for tr in tr_parts[1:]:  # skip before first <tr>
        cells = _TD_RE.findall(tr)
        if len(cells) < 8:
            continue

        # Strip HTML tags from each cell and decode entities
        clean = []
        for cell in cells[:8]:
            text = _TAG_RE.sub("", cell).strip()
            text = unescape(text)
            clean.append(text)

        place_key, site_name, region, subregion, lat, lon, accuracy, elevation = clean

        if not place_key or not lat or not lon:
            continue

        rows.append(
            {
                "place_key": place_key,
                "site_name": site_name.strip(),
                "region": region.strip(),
                "subregion": subregion.strip(),
                "latitude": lat,
                "longitude": lon,
                "accuracy_m": accuracy,
                "elevation_m": elevation,
            }
        )

    return rows


class MycenaeanAtlasIngester(BaseIngester):
    """
    Ingester for the Mycenaean Atlas Project (helladic.info).

    Contains ~5,600 Bronze Age Aegean sites including settlements,
    tombs, sanctuaries, and fortifications from the Mycenaean,
    Minoan, and related cultures.

    Data is scraped from the gazetteer pages at helladic.info since
    the original mycenaean-atlas.org CSV download endpoint is dead.
    """

    source_id = "mycenaean_atlas"
    source_name = "Mycenaean Atlas Project"

    def fetch(self) -> Path:
        """
        Fetch site data from helladic.info gazetteer pages.

        Iterates over all regions, scrapes the HTML table from each
        gazetteer page, and combines into a single CSV file.

        Returns:
            Path to the generated CSV file.
        """
        dest_path = self.raw_data_dir / "mycenaean_atlas.csv"

        logger.info("Fetching Mycenaean Atlas data from helladic.info...")
        self.report_progress(0, len(REGIONS), "starting region scrape...")

        all_rows = []
        seen_keys = set()

        for i, region in enumerate(REGIONS):
            logger.info(f"Fetching region {i + 1}/{len(REGIONS)}: {region}")
            self.report_progress(i, len(REGIONS), f"fetching {region}...")

            response = fetch_with_retry(
                GAZETTEER_URL,
                params={"Kase": "1", "Region": region, "Subregion": ""},
                headers={"Accept": "text/html, */*"},
                timeout=60,
            )

            rows = _parse_gazetteer_html(response.text)
            new_count = 0
            for row in rows:
                if row["place_key"] not in seen_keys:
                    seen_keys.add(row["place_key"])
                    all_rows.append(row)
                    new_count += 1

            logger.info(f"  {region}: {len(rows)} rows, {new_count} new (deduped)")

            # Be polite: small delay between requests
            if i < len(REGIONS) - 1:
                time.sleep(0.5)

        logger.info(f"Total unique sites: {len(all_rows)}")

        # Write combined CSV
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)
        csv_bytes = buf.getvalue().encode("utf-8")

        atomic_write_bytes(dest_path, csv_bytes)

        size_kb = len(csv_bytes) / 1024
        logger.info(f"Saved {size_kb:.1f} KB to {dest_path}")
        self.report_progress(len(REGIONS), len(REGIONS), f"{len(all_rows)} sites saved")
        return dest_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse Mycenaean Atlas CSV data into ParsedSite objects.

        Args:
            raw_data_path: Path to the downloaded CSV file.

        Yields:
            ParsedSite objects for each valid site row.
        """
        logger.info(f"Parsing Mycenaean Atlas data from {raw_data_path}")

        with open(raw_data_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            if not fieldnames:
                logger.error("CSV file has no header row")
                return

            logger.info(f"CSV columns: {fieldnames}")

            count = 0
            for i, row in enumerate(reader):
                site = self._parse_row(row, i)
                if site:
                    count += 1
                    yield site

                if (i + 1) % 1000 == 0:
                    self.report_progress(i + 1, None, f"{count} valid sites")

            logger.info(f"Parsed {count} valid sites from {i + 1} rows")

    def _parse_row(self, row: dict, index: int) -> ParsedSite | None:
        """
        Parse a single CSV row into a ParsedSite.

        Args:
            row: CSV row dict with CSV_COLUMNS keys.
            index: Row index (0-based).

        Returns:
            ParsedSite or None if the row is invalid.
        """
        lat_str = row.get("latitude", "").strip()
        lon_str = row.get("longitude", "").strip()

        if not lat_str or not lon_str:
            return None

        lat = float(lat_str)
        lon = float(lon_str)

        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return None

        name = row.get("site_name", "").strip()
        if not name:
            return None

        site_id = row.get("place_key", "").strip()
        if not site_id:
            site_id = str(index)

        # Infer site type from name
        site_type = _map_site_type(name)

        # All sites are Bronze Age Aegean; default to Mycenaean period
        period_name = "Mycenaean"
        period_start, period_end = -1600, -1100

        # Accuracy from the gazetteer (0 means precise, others in meters)
        accuracy_str = row.get("accuracy_m", "").strip()
        precision_meters = 100  # default
        if accuracy_str:
            try:
                acc = int(accuracy_str)
                precision_meters = max(acc, 1) if acc > 0 else 10
            except ValueError:
                pass

        # Build source URL pointing to the site's report page on helladic.info
        source_url = f"{BASE_URL}/MAPC/pkey_report_wparam.php?place={site_id}"

        return ParsedSite(
            source_id=str(site_id),
            name=name,
            lat=lat,
            lon=lon,
            description=None,
            site_type=site_type,
            period_start=period_start,
            period_end=period_end,
            period_name=period_name,
            precision_meters=precision_meters,
            precision_reason="mycenaean_atlas",
            source_url=source_url,
            raw_data=dict(row),
        )


def ingest_mycenaean_atlas(session=None, skip_fetch: bool = False) -> dict:
    """Run Mycenaean Atlas ingestion."""
    with MycenaeanAtlasIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
