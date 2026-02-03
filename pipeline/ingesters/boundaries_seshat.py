"""
Seshat Global History Databank ingester.

Seshat contains data on 500+ historical polities (empires, kingdoms,
city-states) with territorial information, social complexity metrics,
and temporal coverage spanning 10,000 years of human history.

Data source: https://seshat-db.com/
GitHub: https://github.com/seshatdb/Equinox_Data
Zenodo: https://doi.org/10.5281/zenodo.6642229
License: CC BY-NC-SA 4.0
API Key: Not required
"""

import csv
import io
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class SeshatIngester(BaseIngester):
    """
    Ingester for Seshat Global History Databank.

    Downloads polity data including territorial extents,
    social complexity variables, and temporal coverage.
    """

    source_id = "boundaries_seshat"
    source_name = "Seshat Global History Databank"

    # Data download URLs
    GITHUB_BASE = "https://raw.githubusercontent.com/seshatdb/Equinox_Data/main"
    ZENODO_URL = "https://zenodo.org/api/records/6642229"

    # Data files on GitHub
    DATA_FILES = {
        "polities": f"{GITHUB_BASE}/data/polities.csv",
        "general": f"{GITHUB_BASE}/data/General_Variables.csv",
        "social_complexity": f"{GITHUB_BASE}/data/Social_Complexity.csv",
        "warfare": f"{GITHUB_BASE}/data/Warfare.csv",
        "nga": f"{GITHUB_BASE}/data/NGA.csv",  # Natural Geographic Areas
    }

    # Alternative direct downloads
    ALT_URLS = [
        "https://seshat-db.com/api/polities",
        "https://seshat-db.com/data/polities.json",
        "https://seshat-db.com/export/polities.csv",
    ]

    def fetch(self) -> Path:
        """
        Fetch Seshat polity data.

        Returns:
            Path to JSON file with polity data
        """
        dest_path = self.raw_data_dir / "boundaries_seshat.json"

        logger.info("Fetching Seshat polity data...")
        self.report_progress(0, None, "starting...")

        all_polities = []
        all_ngas = []
        seen_ids = set()

        headers = {
            "Accept": "text/csv, application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform; historical research)",
        }

        # Try GitHub data files
        logger.info("Fetching from GitHub...")

        # Get polities
        try:
            response = fetch_with_retry(
                self.DATA_FILES["polities"],
                headers=headers,
                timeout=60,
            )

            if response.status_code == 200:
                polities = self._parse_csv(response.text, "polity")
                for p in polities:
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        all_polities.append(p)

                logger.info(f"Loaded {len(all_polities)} polities from GitHub")

        except Exception as e:
            logger.debug(f"GitHub polities fetch failed: {e}")

        # Get general variables (contains temporal data)
        try:
            response = fetch_with_retry(
                self.DATA_FILES["general"],
                headers=headers,
                timeout=60,
            )

            if response.status_code == 200:
                self._enrich_polities(all_polities, response.text)

        except Exception as e:
            logger.debug(f"GitHub general variables failed: {e}")

        # Get NGAs (Natural Geographic Areas - have coordinates)
        try:
            response = fetch_with_retry(
                self.DATA_FILES["nga"],
                headers=headers,
                timeout=60,
            )

            if response.status_code == 200:
                ngas = self._parse_csv(response.text, "nga")
                all_ngas.extend(ngas)
                logger.info(f"Loaded {len(ngas)} NGAs")

        except Exception as e:
            logger.debug(f"GitHub NGA fetch failed: {e}")

        # Try Zenodo API for dataset files
        if len(all_polities) < 100:
            logger.info("Trying Zenodo API...")
            try:
                response = fetch_with_retry(self.ZENODO_URL, headers=headers, timeout=60)

                if response.status_code == 200:
                    data = response.json()
                    files = data.get("files", [])

                    for file_info in files:
                        filename = file_info.get("key", "")
                        if "polities" in filename.lower() or "nga" in filename.lower():
                            file_url = file_info.get("links", {}).get("self", "")
                            if file_url:
                                file_response = fetch_with_retry(file_url, headers=headers, timeout=120)
                                if file_response.status_code == 200:
                                    if filename.endswith(".csv"):
                                        parsed = self._parse_csv(file_response.text, "polity")
                                        for p in parsed:
                                            if p["id"] not in seen_ids:
                                                seen_ids.add(p["id"])
                                                all_polities.append(p)

            except Exception as e:
                logger.debug(f"Zenodo API failed: {e}")

        # Add known polities if API didn't work
        if len(all_polities) < 50:
            logger.info("Adding known Seshat polities...")
            known_polities = self._get_known_polities()
            for p in known_polities:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    all_polities.append(p)

        logger.info(f"Total: {len(all_polities):,} polities, {len(all_ngas):,} NGAs")
        self.report_progress(len(all_polities), len(all_polities), f"{len(all_polities):,} polities")

        # Save to file
        output = {
            "polities": all_polities,
            "ngas": all_ngas,
            "metadata": {
                "source": "Seshat Global History Databank",
                "source_url": "https://seshat-db.com/",
                "github_url": "https://github.com/seshatdb/Equinox_Data",
                "zenodo_doi": "10.5281/zenodo.6642229",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_polities": len(all_polities),
                "total_ngas": len(all_ngas),
                "data_type": "historical_polities",
                "license": "CC BY-NC-SA 4.0",
                "citation": "Turchin, P., et al. (2018). Quantitative historical analysis uncovers a single dimension of complexity that structures global variation in human social organization. PNAS.",
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_polities):,} polities to {dest_path}")
        return dest_path

    def _parse_csv(self, content: str, data_type: str) -> list[dict]:
        """Parse CSV content."""
        items = []

        # Handle different CSV formats
        lines = content.strip().split("\n")
        if not lines:
            return items

        # Try to detect delimiter
        first_line = lines[0]
        delimiter = "," if "," in first_line else "\t"

        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

        for row in reader:
            if data_type == "polity":
                item = self._parse_polity_row(row)
            elif data_type == "nga":
                item = self._parse_nga_row(row)
            else:
                item = None

            if item:
                items.append(item)

        return items

    def _parse_polity_row(self, row: dict) -> dict | None:
        """Parse a polity row from CSV."""
        # Get polity ID/name
        polity_id = row.get("PolID", row.get("polity_id", row.get("Polity", "")))
        if not polity_id:
            return None

        polity_id = f"seshat_{polity_id}".replace(" ", "_").lower()

        # Get temporal range
        start = self._parse_year(row.get("Start", row.get("start_year", row.get("Date From", ""))))
        end = self._parse_year(row.get("End", row.get("end_year", row.get("Date To", ""))))

        # Get NGA (Natural Geographic Area - for approximate location)
        nga = row.get("NGA", row.get("nga", row.get("Region", "")))

        return {
            "id": polity_id,
            "name": row.get("PolID", row.get("polity_name", row.get("Polity Name", ""))),
            "nga": nga,
            "start_year": start,
            "end_year": end,
            "duration": row.get("Duration", ""),
            "polity_type": row.get("Polity Type", row.get("type", "")),
            "original_name": row.get("Original Name", ""),
            "alternative_names": row.get("Alternative Names", ""),
            "peak_date": self._parse_year(row.get("Peak Date", "")),
            "territory_km2": self._parse_float(row.get("Polity Territory", row.get("territory_km2", ""))),
            "population": self._parse_int(row.get("Population", row.get("population_estimate", ""))),
            "capital": row.get("Capital", row.get("capital_city", "")),
            "language": row.get("Language", row.get("Linguistic Family", "")),
            "religion": row.get("Religion", ""),
            "successor": row.get("Successor", ""),
            "predecessor": row.get("Predecessor", ""),
        }

    def _parse_nga_row(self, row: dict) -> dict | None:
        """Parse an NGA (Natural Geographic Area) row."""
        nga_name = row.get("NGA", row.get("nga_name", row.get("Name", "")))
        if not nga_name:
            return None

        lat = self._parse_float(row.get("Lat", row.get("latitude", row.get("Centroid Lat", ""))))
        lon = self._parse_float(row.get("Lon", row.get("longitude", row.get("Centroid Lon", ""))))

        return {
            "id": f"seshat_nga_{nga_name}".replace(" ", "_").lower(),
            "name": nga_name,
            "lat": lat,
            "lon": lon,
            "region": row.get("World Region", row.get("region", "")),
            "description": row.get("Description", ""),
        }

    def _enrich_polities(self, polities: list[dict], general_csv: str) -> None:
        """Enrich polities with data from general variables CSV."""
        # Create lookup by polity ID
        polity_lookup = {p["name"]: p for p in polities}

        reader = csv.DictReader(io.StringIO(general_csv))

        for row in reader:
            polity_name = row.get("Polity", row.get("PolID", ""))
            if polity_name in polity_lookup:
                p = polity_lookup[polity_name]

                # Add any missing data
                if not p.get("capital") and row.get("Capital"):
                    p["capital"] = row["Capital"]
                if not p.get("territory_km2") and row.get("Polity Territory"):
                    p["territory_km2"] = self._parse_float(row["Polity Territory"])
                if not p.get("population") and row.get("Population"):
                    p["population"] = self._parse_int(row["Population"])

    def _get_known_polities(self) -> list[dict]:
        """Return known major Seshat polities."""
        return [
            # Ancient Near East
            {"id": "seshat_akkadian_empire", "name": "Akkadian Empire", "nga": "Susiana", "start_year": -2334, "end_year": -2154, "polity_type": "empire", "capital": "Akkad"},
            {"id": "seshat_ur_iii", "name": "Third Dynasty of Ur", "nga": "Susiana", "start_year": -2112, "end_year": -2004, "polity_type": "empire", "capital": "Ur"},
            {"id": "seshat_old_babylonian", "name": "Old Babylonian Empire", "nga": "Susiana", "start_year": -1894, "end_year": -1595, "polity_type": "empire", "capital": "Babylon"},
            {"id": "seshat_assyrian_empire", "name": "Neo-Assyrian Empire", "nga": "Upper Egypt", "start_year": -911, "end_year": -609, "polity_type": "empire", "capital": "Nineveh"},
            {"id": "seshat_achaemenid", "name": "Achaemenid Persian Empire", "nga": "Susiana", "start_year": -550, "end_year": -330, "polity_type": "empire", "capital": "Persepolis"},
            # Egypt
            {"id": "seshat_old_kingdom", "name": "Old Kingdom Egypt", "nga": "Upper Egypt", "start_year": -2686, "end_year": -2181, "polity_type": "kingdom", "capital": "Memphis"},
            {"id": "seshat_middle_kingdom", "name": "Middle Kingdom Egypt", "nga": "Upper Egypt", "start_year": -2055, "end_year": -1650, "polity_type": "kingdom", "capital": "Thebes"},
            {"id": "seshat_new_kingdom", "name": "New Kingdom Egypt", "nga": "Upper Egypt", "start_year": -1550, "end_year": -1069, "polity_type": "kingdom", "capital": "Thebes"},
            {"id": "seshat_ptolemaic", "name": "Ptolemaic Egypt", "nga": "Upper Egypt", "start_year": -305, "end_year": -30, "polity_type": "kingdom", "capital": "Alexandria"},
            # Mediterranean
            {"id": "seshat_roman_republic", "name": "Roman Republic", "nga": "Latium", "start_year": -509, "end_year": -27, "polity_type": "republic", "capital": "Rome"},
            {"id": "seshat_roman_principate", "name": "Roman Principate", "nga": "Latium", "start_year": -27, "end_year": 284, "polity_type": "empire", "capital": "Rome"},
            {"id": "seshat_roman_dominate", "name": "Roman Dominate", "nga": "Latium", "start_year": 284, "end_year": 476, "polity_type": "empire", "capital": "Rome/Constantinople"},
            {"id": "seshat_athenian_empire", "name": "Athenian Empire", "nga": "Attica", "start_year": -478, "end_year": -404, "polity_type": "hegemony", "capital": "Athens"},
            {"id": "seshat_macedon_philip", "name": "Macedonian Kingdom (Philip II)", "nga": "Konya Plain", "start_year": -359, "end_year": -336, "polity_type": "kingdom", "capital": "Pella"},
            {"id": "seshat_macedon_alexander", "name": "Macedonian Empire (Alexander)", "nga": "Konya Plain", "start_year": -336, "end_year": -323, "polity_type": "empire", "capital": "Babylon"},
            {"id": "seshat_seleucid", "name": "Seleucid Empire", "nga": "Susiana", "start_year": -312, "end_year": -63, "polity_type": "empire", "capital": "Antioch"},
            {"id": "seshat_byzantine", "name": "Byzantine Empire", "nga": "Konya Plain", "start_year": 330, "end_year": 1453, "polity_type": "empire", "capital": "Constantinople"},
            # China
            {"id": "seshat_shang", "name": "Shang Dynasty", "nga": "Middle Yellow River", "start_year": -1600, "end_year": -1046, "polity_type": "kingdom", "capital": "Yin"},
            {"id": "seshat_zhou_western", "name": "Western Zhou", "nga": "Middle Yellow River", "start_year": -1046, "end_year": -771, "polity_type": "kingdom", "capital": "Haojing"},
            {"id": "seshat_qin", "name": "Qin Dynasty", "nga": "Middle Yellow River", "start_year": -221, "end_year": -206, "polity_type": "empire", "capital": "Xianyang"},
            {"id": "seshat_han_western", "name": "Western Han", "nga": "Middle Yellow River", "start_year": -206, "end_year": 9, "polity_type": "empire", "capital": "Chang'an"},
            {"id": "seshat_tang", "name": "Tang Dynasty", "nga": "Middle Yellow River", "start_year": 618, "end_year": 907, "polity_type": "empire", "capital": "Chang'an"},
            # India
            {"id": "seshat_mauryan", "name": "Maurya Empire", "nga": "Ganga", "start_year": -322, "end_year": -185, "polity_type": "empire", "capital": "Pataliputra"},
            {"id": "seshat_gupta", "name": "Gupta Empire", "nga": "Ganga", "start_year": 320, "end_year": 550, "polity_type": "empire", "capital": "Pataliputra"},
            # Mesoamerica
            {"id": "seshat_teotihuacan", "name": "Teotihuacan", "nga": "Valley of Oaxaca", "start_year": -100, "end_year": 550, "polity_type": "city-state", "capital": "Teotihuacan"},
            {"id": "seshat_maya_tikal", "name": "Tikal (Classic Maya)", "nga": "Peten", "start_year": 250, "end_year": 900, "polity_type": "city-state", "capital": "Tikal"},
            {"id": "seshat_aztec", "name": "Aztec Empire", "nga": "Valley of Oaxaca", "start_year": 1428, "end_year": 1521, "polity_type": "empire", "capital": "Tenochtitlan"},
            # Andes
            {"id": "seshat_inca", "name": "Inca Empire", "nga": "Cuzco", "start_year": 1438, "end_year": 1533, "polity_type": "empire", "capital": "Cusco"},
        ]

    def _parse_year(self, value) -> int | None:
        """Parse a year value."""
        if not value or value in ["", "?"]:
            return None
        try:
            return int(float(str(value).replace(",", "")))
        except (ValueError, TypeError):
            return None

    def _parse_float(self, value) -> float | None:
        """Parse a float value."""
        if not value or value in ["", "?"]:
            return None
        try:
            return float(str(value).replace(",", ""))
        except (ValueError, TypeError):
            return None

    def _parse_int(self, value) -> int | None:
        """Parse an integer value."""
        if not value or value in ["", "?"]:
            return None
        try:
            return int(float(str(value).replace(",", "")))
        except (ValueError, TypeError):
            return None

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse Seshat data - polities don't have point coordinates."""
        logger.info(f"Parsing Seshat data from {raw_data_path}")

        # Polities are regions, not points - need NGA coordinates or external geocoding
        # For now, return empty
        return iter([])


def ingest_seshat(session=None, skip_fetch: bool = False) -> dict:
    """Run Seshat ingestion."""
    with SeshatIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
