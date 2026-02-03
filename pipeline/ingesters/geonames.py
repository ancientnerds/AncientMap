"""
GeoNames archaeological features ingester.

GeoNames is a geographical database with 11+ million place names.
We filter for archaeological feature codes (RUIN, ANS, etc.)

Data source: https://www.geonames.org/
License: CC-BY 4.0
API Key: Optional (for web services), not needed for bulk download
"""

import zipfile
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite
from pipeline.utils.http import download_file


class GeoNamesIngester(BaseIngester):
    """
    Ingester for GeoNames archaeological features.

    GeoNames uses feature codes to classify places. We filter for:
    - ANS: ancient site
    - RUIN: ruin(s)
    - CSTL: castle
    - MNMT: monument
    - TMPL: temple
    - PYR: pyramid
    - TOWR: tower (historic)
    - AMTH: amphitheater
    - And more...

    The full dump is large (~1.5GB), so we process it in streaming fashion.
    """

    source_id = "geonames"
    source_name = "GeoNames"

    # Download URL for full database
    DOWNLOAD_URL = "https://download.geonames.org/export/dump/allCountries.zip"

    # Alternative: specific country files are smaller
    # e.g., "https://download.geonames.org/export/dump/IT.zip" for Italy

    # Archaeological feature codes to include
    ARCHAEOLOGICAL_FEATURE_CODES: set[str] = {
        # Historic/Archaeological
        "ANS",    # ancient site
        "RUIN",   # ruin(s)
        "RUINS",  # ruins
        "CSTL",   # castle
        "MNMT",   # monument
        "TMPL",   # temple(s)
        "PYR",    # pyramid
        "PYRS",   # pyramids
        "AMTH",   # amphitheater
        "HSTS",   # historic site
        "PAL",    # palace
        "TOWR",   # tower
        "FRT",    # fort
        "FRST",   # fortress
        "WALL",   # wall
        "GRVE",   # grave
        "CMTY",   # cemetery
        "TMB",    # tomb(s)
        "BTYD",   # boatyard (ancient harbors)
        "MOLE",   # mole (ancient harbor structure)
        "PIER",   # pier
        "AQDC",   # aqueduct
        "BDG",    # bridge
        "RDGE",   # road/ridge (ancient roads)
        "CH",     # church (historic)
        "MSQE",   # mosque (historic)
        "SHRN",   # shrine
        "CVNT",   # convent
        "MSTY",   # monastery
        "ABB",    # abbey
        "CTHDRL", # cathedral
        "SQR",    # square (historic plaza)
        "THTR",   # theater
        "STDM",   # stadium
        "BTHS",   # baths
        "LIBR",   # library (ancient)
        "MUS",    # museum (site museums)
        "ZOO",    # zoo (ancient menageries)
        "CAVE",   # cave(s) - can be archaeological
        "CMPL",   # complex (archaeological complex)
        "OBPT",   # observation point (ancient)
    }

    # Feature code to site type mapping
    TYPE_MAPPING = {
        "ANS": "other",
        "RUIN": "other",
        "RUINS": "other",
        "CSTL": "fortress",
        "MNMT": "monument",
        "TMPL": "temple",
        "PYR": "pyramid",
        "PYRS": "pyramid",
        "AMTH": "amphitheater",
        "PAL": "palace",
        "TOWR": "monument",
        "FRT": "fortress",
        "FRST": "fortress",
        "WALL": "monument",
        "GRVE": "tomb",
        "CMT": "cemetery",
        "CMTY": "cemetery",
        "TMB": "tomb",
        "AQDC": "aqueduct",
        "BDG": "bridge",
        "CH": "church",
        "MSQE": "mosque",
        "SHRN": "sanctuary",
        "CVNT": "church",
        "MSTY": "church",
        "ABB": "church",
        "CTHDRL": "church",
        "THTR": "theater",
        "STDM": "stadium",
        "BTHS": "bath",
        "CAVE": "cave",
        "HSTS": "other",
    }

    def fetch(self) -> Path:
        """
        Download GeoNames data.

        Note: The full allCountries.zip is ~1.5GB compressed.
        Consider using country-specific files for faster testing.

        Returns:
            Path to the extracted TSV file
        """
        zip_path = self.raw_data_dir / "geonames.zip"
        tsv_path = self.raw_data_dir / "geonames.txt"

        # Check if we already have recent data
        if tsv_path.exists():
            logger.info(f"Using existing GeoNames data: {tsv_path}")
            return tsv_path

        logger.info(f"Downloading GeoNames data from {self.DOWNLOAD_URL}")
        logger.warning("This is a large file (~1.5GB). Consider using country files for testing.")
        self.report_progress(0, None, "downloading 1.5GB...")

        download_file(
            url=self.DOWNLOAD_URL,
            dest_path=zip_path,
            force=True,
            decompress_gzip=False,
        )

        # Extract the ZIP file
        logger.info(f"Extracting {zip_path}...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # The main file is allCountries.txt
            zf.extract("allCountries.txt", self.raw_data_dir)
            extracted_path = self.raw_data_dir / "allCountries.txt"
            extracted_path.rename(tsv_path)

        # Clean up ZIP
        zip_path.unlink()

        logger.info(f"Extracted GeoNames data to {tsv_path}")
        return tsv_path

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """
        Parse GeoNames TSV data, filtering for archaeological features.

        GeoNames TSV columns (tab-separated):
        0: geonameid
        1: name
        2: asciiname
        3: alternatenames (comma-separated)
        4: latitude
        5: longitude
        6: feature_class
        7: feature_code
        8: country_code
        9: cc2
        10: admin1_code
        11: admin2_code
        12: admin3_code
        13: admin4_code
        14: population
        15: elevation
        16: dem
        17: timezone
        18: modification_date

        Yields:
            ParsedSite objects for archaeological features
        """
        logger.info(f"Parsing GeoNames data from {raw_data_path}")
        logger.info(f"Filtering for {len(self.ARCHAEOLOGICAL_FEATURE_CODES)} feature codes")

        count = 0
        matched = 0

        with open(raw_data_path, encoding="utf-8") as f:
            for line in f:
                count += 1
                if count % 1000000 == 0:
                    logger.info(f"Processed {count:,} lines, found {matched:,} archaeological sites")

                # Parse TSV line
                parts = line.strip().split("\t")
                if len(parts) < 19:
                    continue

                # Check feature code
                feature_code = parts[7] if len(parts) > 7 else ""
                if feature_code not in self.ARCHAEOLOGICAL_FEATURE_CODES:
                    continue

                matched += 1
                site = self._parse_line(parts)
                if site:
                    yield site

        logger.info(f"Finished: {count:,} total lines, {matched:,} archaeological sites")

    def _parse_line(self, parts: list) -> ParsedSite | None:
        """
        Parse a single GeoNames TSV line.

        Args:
            parts: Tab-separated fields

        Returns:
            ParsedSite or None if invalid
        """
        try:
            geoname_id = parts[0]
            name = parts[1]
            ascii_name = parts[2]
            alt_names = parts[3].split(",") if parts[3] else []
            lat = float(parts[4])
            lon = float(parts[5])
            feature_class = parts[6]
            feature_code = parts[7]
            country_code = parts[8]

            # Skip invalid coordinates
            if lat == 0 and lon == 0:
                return None

            # Map feature code to site type
            site_type = self.TYPE_MAPPING.get(feature_code, "other")

            # Build alternative names list
            alternative_names = [n.strip() for n in alt_names if n.strip() and n.strip() != name][:10]

            # Source URL
            source_url = f"https://www.geonames.org/{geoname_id}"

            return ParsedSite(
                source_id=geoname_id,
                name=name,
                lat=lat,
                lon=lon,
                alternative_names=alternative_names,
                description=None,
                site_type=site_type,
                period_start=None,
                period_end=None,
                period_name=None,
                precision_meters=100,
                precision_reason="geonames",
                source_url=source_url,
                raw_data={
                    "geonameid": geoname_id,
                    "name": name,
                    "asciiname": ascii_name,
                    "feature_class": feature_class,
                    "feature_code": feature_code,
                    "country_code": country_code,
                    "alternatenames": parts[3][:500] if parts[3] else "",
                },
            )

        except (ValueError, IndexError) as e:
            logger.debug(f"Error parsing line: {e}")
            return None


def ingest_geonames(session=None, skip_fetch: bool = False) -> dict:
    """Run GeoNames ingestion."""
    with GeoNamesIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
