"""
Process Cliopatria historical boundaries dataset.

Downloads Cliopatria GeoJSON from GitHub and extracts per-empire boundary files
with temporal snapshots for visualization on the globe.

Data source: https://github.com/Seshat-Global-History-Databank/cliopatria
- 1,800+ political entities with ~15,000 records (3400 BCE - 2024 CE)
- Ready-to-use GeoJSON format (EPSG:4326)
- Peer-reviewed scholarly data published in Nature Scientific Data
- CC BY license

Scope: Civilizations that "touch ancient" (startYear before cutoff)
- Old World (Europe, Asia, Africa, Oceania): startYear <= 500 AD
- Americas: startYear <= 1500 AD

Usage:
    python -m pipeline.historical_boundaries.process_cliopatria
    python -m pipeline.historical_boundaries.process_cliopatria --list-empires
    python -m pipeline.historical_boundaries.process_cliopatria --empire roman
"""

import argparse
import json
import re
import shutil
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

try:
    import geojson
    from shapely.geometry import MultiPolygon, Polygon, mapping, shape
    from shapely.ops import unary_union
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("\nInstall required packages:")
    print("  pip install shapely geojson")
    exit(1)

from loguru import logger

# =============================================================================
# Configuration
# =============================================================================

# Output directory
OUTPUT_DIR = Path('ancient-nerds-map/public/data/historical')

# Cliopatria data paths
CLIOPATRIA_ZIP_URL = 'https://github.com/Seshat-Global-History-Databank/cliopatria/raw/main/cliopatria.geojson.zip'
CLIOPATRIA_CACHE_DIR = Path('data/raw')
CLIOPATRIA_ZIP_PATH = CLIOPATRIA_CACHE_DIR / 'cliopatria.geojson.zip'
CLIOPATRIA_GEOJSON_PATH = CLIOPATRIA_CACHE_DIR / 'cliopatria.geojson'

# =============================================================================
# SeshatID-based Matching (Primary Method)
# =============================================================================
# Maps our empire IDs to Seshat polity IDs from Cliopatria GeoJSON.
# This is more reliable than name-based regex matching.
# SeshatID is the authoritative identifier from the Seshat database.

EMPIRE_SESHAT_IDS = {
    # Ancient Near East (7 civilizations)
    'egyptian': [
        'eg_dynasty_1', 'eg_dynasty_2',  # Early Dynastic
        'eg_old_k_1', 'eg_old_k_2',  # Old Kingdom
        'eg_middle_k',  # Middle Kingdom
        'eg_new_k_1', 'eg_new_k_2',  # New Kingdom
        'eg_thebes_hyksos',  # Second Intermediate
        'eg_thebes_libyan',  # Third Intermediate
        'eg_ptolemaic_k_1', 'eg_ptolemaic_k_2',  # Ptolemaic
    ],
    'akkadian': ['iq_akkad_emp'],
    'elam': [
        'ir_elam_proto', 'ir_elam_old', 'ir_elam_middle',  # Early through Middle Elamite
        'ir_elam_neo',  # Neo-Elamite
    ],
    'babylonian': [
        'iq_babylonia_1', 'iq_babylonia_2',  # Old Babylonian
        'iq_bazi_dyn', 'iq_dynasty_e', 'iq_isin_dynasty2',  # Middle periods
        'iq_neo_babylonian_emp',  # Neo-Babylonian
    ],
    'assyrian': [
        'iq_middle_assyrian_emp',  # Middle Assyrian
        'iq_neo_assyrian_emp',  # Neo-Assyrian
    ],
    'hittite': ['tr_hatti_old_k', 'tr_hatti_new_k'],
    'mitanni': ['sy_mitanni_k'],

    # Mediterranean (9 civilizations)
    'minoan': ['gr_crete_new_palace', 'gr_crete_old_palace'],
    'mycenaean': [],  # Uses name fallback
    'phoenician': ['lb_phoenician_emp', 'lb_phoenicia'],
    'etruscan': [],  # Uses name fallback
    'greek': ['gr_macedonian_emp'],  # Limited SeshatIDs; uses name fallback
    'macedonian': ['gr_macedonian_emp', 'gr_antigonid_emp'],
    'carthaginian': ['tn_carthage_emp'],
    'roman': [
        'it_roman_rep_1', 'it_roman_rep_2', 'it_roman_rep_3',  # Republic
        'it_roman_principate',  # Principate
        'tr_roman_dominate',  # Dominate
        'it_western_roman_emp',  # Western Empire
    ],
    'byzantine': [
        'tr_byzantine_emp_1', 'tr_byzantine_emp_2', 'tr_byzantine_emp_3',
        'tr_east_roman_emp',
    ],

    # Persian/Central Asia (5 civilizations)
    'achaemenid': ['ir_achaemenid_emp'],
    'seleucid': ['ir_seleucid_emp'],
    'parthian': ['ir_parthian_emp_1'],
    'kushan': ['af_kushan_emp', 'pk_kushan'],
    'sassanid': ['ir_sassanid_emp_1', 'ir_sassanid_emp_2'],

    # East Asia (4 civilizations)
    'shang': ['cn_erligang', 'cn_late_shang_dyn'],
    'zhou': ['cn_western_zhou_dyn', 'cn_eastern_zhou_warring_states'],
    'qin': ['cn_qin_emp'],
    'han': ['cn_western_han_dyn', 'cn_eastern_han_dyn'],

    # South Asia (3 civilizations)
    'indus_valley': [
        'pk_kachi_ceramic_neolithic', 'pk_kachi_early_bronze',
        'pk_kachi_mature_harappan', 'pk_kachi_late_harappan',
        'pk_harappan',
    ],
    'maurya': ['in_mauryan_emp'],
    'gupta': ['in_gupta_emp'],

    # Africa (2 civilizations)
    'kush': ['sd_kush_k'],
    'axum': ['et_aksum_emp_1', 'et_aksum_emp_2', 'et_aksum_emp_3', 'et_ethiopian_k'],

    # Americas (6 civilizations)
    'olmec': [],  # Uses name fallback
    'zapotec': [
        'mx_monte_alban_1_early', 'mx_monte_alban_1_late',  # Early Zapotec
        'mx_monte_alban_2',  # Monte Alban II
        'mx_monte_alban_3_a', 'mx_monte_alban_3_b_4',  # Classic period
    ],
    'teotihuacan': ['mx_basin_of_mexico_7', 'mx_teotihuacan'],
    'maya': [
        'gt_tikal_early_classic',  # Classic Maya
        'gt_tikal_terminal_classic',  # Terminal Classic
        'gt_tikal_early_postclassic',  # Postclassic
        'mx_maya_classic',
    ],
    'aztec': ['mx_aztec_emp'],
    'inca': ['pe_inca_emp'],

    # Medieval Europe (1 civilization)
    'carolingian': ['fr_carolingian_emp_1', 'fr_carolingian_emp_2'],
}

# =============================================================================
# Name-based Matching (Fallback)
# =============================================================================
# Used when SeshatID is not present in the GeoJSON feature.
# Some Cliopatria features have empty SeshatID fields.

EMPIRE_NAME_PATTERNS = {
    # Ancient Near East
    'egyptian': [
        r'.*Kingdom.*Egypt',
        r'.*Dynasty.*Egypt',
        r'Ptolemaic.*',
        r'Ancient Egypt.*',
    ],
    'akkadian': [r'Akkad.*Empire', r'Akkadian.*'],
    'elam': [r'Elam.*', r'Elamite.*'],
    'babylonian': [r'.*Babylon.*', r'Neo-Babylon.*'],
    'assyrian': [r'.*Assyria.*', r'Neo-Assyria.*'],
    'hittite': [r'Hittite.*', r'.*Hatti.*'],
    'mitanni': [r'Mitanni.*', r'Mittani.*'],

    # Mediterranean
    'minoan': [r'Minoan.*', r'.*Crete.*Palace'],
    'mycenaean': [r'Mycenae.*', r'Mycenaean.*'],
    'phoenician': [r'Phoenici.*', r'.*Phoenicia.*'],
    'etruscan': [r'Etrusc.*', r'Etruria.*'],
    'greek': [
        r'.*Athens.*', r'.*Sparta.*', r'Greek.*', r'Hellenic.*',
        r'Delian League', r'Greek City-States', r'Greek Dark Ages',
    ],
    'macedonian': [r'Macedon.*', r'Antigonid.*'],
    'carthaginian': [r'Carthag.*'],
    'roman': [r'Roman.*', r'Western Roman.*'],
    'byzantine': [r'Byzantine.*', r'Eastern Roman.*'],

    # Persian/Central Asia
    'achaemenid': [r'Achaemenid.*'],
    'seleucid': [r'Seleucid.*'],
    'parthian': [r'Parthia.*', r'Arsacid.*'],
    'kushan': [r'Kushan.*'],
    'sassanid': [r'Sassanid.*', r'Sasanian.*'],

    # East Asia
    'shang': [r'Shang.*'],
    'zhou': [r'.*Zhou.*'],
    'qin': [r'Qin Dynasty', r'Qin Empire'],  # Careful: not "Qing"
    'han': [r'Han Dynasty', r'.*Han.*Dynasty'],

    # South Asia
    'indus_valley': [r'Harappa.*', r'Indus Valley.*', r'Mohenjo.*'],
    'maurya': [r'Maurya.*'],
    'gupta': [r'Gupta.*'],

    # Africa
    'kush': [r'Kush.*', r'Nubia.*', r'Meroe.*'],
    'axum': [r'.*Axum.*', r'Aksumite.*', r'Ethiopian Empire'],

    # Americas
    'olmec': [r'Olmec.*', r'La Venta.*', r'San Lorenzo.*'],
    'zapotec': [r'Zapotec.*', r'Monte Alban.*'],
    'teotihuacan': [r'Teotihuac[aá]n.*'],
    'maya': [r'Maya.*', r'Mayan.*', r'.*Mayan City-States', r'Itza Maya.*'],
    'aztec': [r'Aztec.*', r'Mexica.*', r'Triple Alliance'],
    'inca': [r'Inca.*', r'Tawantinsuyu'],

    # Medieval Europe
    'carolingian': [r'.*Carolingian.*', r'Kingdom of the Franks', r'\(Kingdom of the Franks\)'],
}

# Legacy alias for backwards compatibility
EMPIRE_MAPPINGS = EMPIRE_NAME_PATTERNS

# Empire metadata (for UI display)
EMPIRE_METADATA = {
    # Ancient Near East (7)
    'egyptian': {'name': 'Egyptian Empire', 'region': 'Ancient Near East', 'startYear': -3100, 'endYear': -30, 'color': 0xFFD700},
    'akkadian': {'name': 'Akkadian Empire', 'region': 'Ancient Near East', 'startYear': -2334, 'endYear': -2154, 'color': 0xFFA07A},
    'elam': {'name': 'Elam', 'region': 'Ancient Near East', 'startYear': -3200, 'endYear': -601, 'color': 0xE6A44C},
    'babylonian': {'name': 'Babylonian', 'region': 'Ancient Near East', 'startYear': -1894, 'endYear': -539, 'color': 0xFFB347},
    'assyrian': {'name': 'Assyrian Empire', 'region': 'Ancient Near East', 'startYear': -2500, 'endYear': -609, 'color': 0xFF6B6B},
    'hittite': {'name': 'Hittite Empire', 'region': 'Ancient Near East', 'startYear': -1600, 'endYear': -1178, 'color': 0xFFAA00},
    'mitanni': {'name': 'Mitanni', 'region': 'Ancient Near East', 'startYear': -1500, 'endYear': -1241, 'color': 0xD4A574},

    # Mediterranean (9)
    'minoan': {'name': 'Minoan Civilization', 'region': 'Mediterranean', 'startYear': -1600, 'endYear': -1401, 'color': 0x20B2AA},
    'mycenaean': {'name': 'Mycenaean Greece', 'region': 'Mediterranean', 'startYear': -1500, 'endYear': -1101, 'color': 0x48D1CC},
    'phoenician': {'name': 'Phoenicia', 'region': 'Mediterranean', 'startYear': -700, 'endYear': -616, 'color': 0x9370DB},
    'etruscan': {'name': 'Etruscan Civilization', 'region': 'Mediterranean', 'startYear': -750, 'endYear': -265, 'color': 0xDB7093},
    'greek': {'name': 'Greek City-States', 'region': 'Mediterranean', 'startYear': -800, 'endYear': -338, 'color': 0xFFA07A},
    'macedonian': {'name': 'Macedonian Empire', 'region': 'Mediterranean', 'startYear': -338, 'endYear': -168, 'color': 0xFF8866},
    'carthaginian': {'name': 'Carthaginian Empire', 'region': 'Mediterranean', 'startYear': -814, 'endYear': -146, 'color': 0xFFAA88},
    'roman': {'name': 'Roman Empire', 'region': 'Mediterranean', 'startYear': -509, 'endYear': 476, 'color': 0xFF7777},
    'byzantine': {'name': 'Byzantine Empire', 'region': 'Mediterranean', 'startYear': 330, 'endYear': 1453, 'color': 0xFF99AA},

    # Persian/Central Asia (5)
    'achaemenid': {'name': 'Achaemenid Persia', 'region': 'Persian/Central Asia', 'startYear': -550, 'endYear': -330, 'color': 0x00BFFF},
    'seleucid': {'name': 'Seleucid Empire', 'region': 'Persian/Central Asia', 'startYear': -312, 'endYear': -63, 'color': 0x00CED1},
    'parthian': {'name': 'Parthian Empire', 'region': 'Persian/Central Asia', 'startYear': -247, 'endYear': 224, 'color': 0x40E0D0},
    'kushan': {'name': 'Kushan Empire', 'region': 'Persian/Central Asia', 'startYear': 43, 'endYear': 237, 'color': 0x5F9EA0},
    'sassanid': {'name': 'Sassanid Empire', 'region': 'Persian/Central Asia', 'startYear': 224, 'endYear': 651, 'color': 0x7FFFD4},

    # East Asia (4)
    'shang': {'name': 'Shang Dynasty', 'region': 'East Asia', 'startYear': -1600, 'endYear': -1046, 'color': 0xFFD700},
    'zhou': {'name': 'Zhou Dynasty', 'region': 'East Asia', 'startYear': -1046, 'endYear': -256, 'color': 0xFFE135},
    'qin': {'name': 'Qin Dynasty', 'region': 'East Asia', 'startYear': -221, 'endYear': -206, 'color': 0xFF5733},
    'han': {'name': 'Han Dynasty', 'region': 'East Asia', 'startYear': -206, 'endYear': 220, 'color': 0xFF6347},

    # South Asia (3)
    'indus_valley': {'name': 'Indus Valley (Harappan)', 'region': 'South Asia', 'startYear': -3000, 'endYear': -1701, 'color': 0x66CDAA},
    'maurya': {'name': 'Maurya Empire', 'region': 'South Asia', 'startYear': -322, 'endYear': -185, 'color': 0x7FFF00},
    'gupta': {'name': 'Gupta Empire', 'region': 'South Asia', 'startYear': 320, 'endYear': 550, 'color': 0x00FF7F},

    # Africa (2)
    'kush': {'name': 'Kingdom of Kush', 'region': 'Africa', 'startYear': -1070, 'endYear': 350, 'color': 0xFF8C00},
    'axum': {'name': 'Aksumite Empire', 'region': 'Africa', 'startYear': 100, 'endYear': 940, 'color': 0xCD853F},

    # Americas (6)
    'olmec': {'name': 'Olmec Civilization', 'region': 'Americas', 'startYear': -650, 'endYear': -351, 'color': 0x228B22},
    'zapotec': {'name': 'Zapotec Civilization', 'region': 'Americas', 'startYear': -500, 'endYear': 900, 'color': 0x3CB371},
    'teotihuacan': {'name': 'Teotihuacan', 'region': 'Americas', 'startYear': -50, 'endYear': 704, 'color': 0x2E8B57},
    'maya': {'name': 'Maya Civilization', 'region': 'Americas', 'startYear': -2000, 'endYear': 1500, 'color': 0x00FF7F},
    'aztec': {'name': 'Aztec Empire', 'region': 'Americas', 'startYear': 1428, 'endYear': 1521, 'color': 0x7CFC00},
    'inca': {'name': 'Inca Empire', 'region': 'Americas', 'startYear': 1438, 'endYear': 1533, 'color': 0x7FFF00},

    # Medieval Europe (1)
    'carolingian': {'name': 'Carolingian Empire', 'region': 'Medieval Europe', 'startYear': 751, 'endYear': 888, 'color': 0x6495ED},
}


# =============================================================================
# Download
# =============================================================================

def download_cliopatria() -> Path:
    """Download Cliopatria dataset if not present."""
    if CLIOPATRIA_GEOJSON_PATH.exists():
        logger.info(f"Cliopatria data already exists at {CLIOPATRIA_GEOJSON_PATH}")
        return CLIOPATRIA_GEOJSON_PATH

    CLIOPATRIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading Cliopatria dataset...")
    logger.info(f"URL: {CLIOPATRIA_ZIP_URL}")

    def progress_hook(count, block_size, total_size):
        if total_size > 0:
            percent = count * block_size * 100 / total_size
            downloaded_mb = count * block_size / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            print(f"\r  Downloading: {percent:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end='', flush=True)

    try:
        urllib.request.urlretrieve(CLIOPATRIA_ZIP_URL, CLIOPATRIA_ZIP_PATH, progress_hook)
        print()  # New line
        logger.info(f"Downloaded to {CLIOPATRIA_ZIP_PATH}")

        logger.info("Extracting GeoJSON...")
        with zipfile.ZipFile(CLIOPATRIA_ZIP_PATH, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.geojson'):
                    logger.info(f"  Extracting {name}...")
                    zf.extract(name, CLIOPATRIA_CACHE_DIR)
                    extracted = CLIOPATRIA_CACHE_DIR / name
                    if extracted != CLIOPATRIA_GEOJSON_PATH:
                        shutil.move(str(extracted), str(CLIOPATRIA_GEOJSON_PATH))
                    break

        # Clean up zip
        CLIOPATRIA_ZIP_PATH.unlink()
        logger.info(f"Cliopatria data ready at {CLIOPATRIA_GEOJSON_PATH}")
        return CLIOPATRIA_GEOJSON_PATH

    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise


# =============================================================================
# Data Loading
# =============================================================================

def load_cliopatria(path: Path = CLIOPATRIA_GEOJSON_PATH) -> dict:
    """Load Cliopatria GeoJSON data."""
    if not path.exists():
        download_cliopatria()

    logger.info(f"Loading Cliopatria data from {path}...")
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    logger.info(f"Loaded {len(data.get('features', []))} features")
    return data


# =============================================================================
# Processing
# =============================================================================

def match_empire_by_seshat_id(seshat_id: str, empire_id: str) -> bool:
    """Check if a SeshatID matches an empire's configured IDs (primary matching method)."""
    if not seshat_id:
        return False
    empire_seshat_ids = EMPIRE_SESHAT_IDS.get(empire_id, [])
    # Check exact match or if the seshat_id starts with one of our configured IDs
    for configured_id in empire_seshat_ids:
        if seshat_id == configured_id or seshat_id.startswith(configured_id + ';'):
            return True
    return False


def match_empire_by_name(name: str, empire_id: str) -> bool:
    """Check if a polity name matches an empire's patterns (fallback method)."""
    patterns = EMPIRE_NAME_PATTERNS.get(empire_id, [])
    for pattern in patterns:
        if re.match(pattern, name, re.IGNORECASE):
            return True
    return False


def match_empire(feature: dict, empire_id: str) -> bool:
    """
    Check if a feature matches an empire using SeshatID (primary) or name (fallback).

    Priority:
    1. SeshatID-based matching (authoritative, reliable)
    2. Name-based pattern matching (fallback for features without SeshatID)
    """
    props = feature.get('properties', {})
    seshat_id = props.get('SeshatID', '')
    name = props.get('Name', '')

    # Primary: SeshatID matching
    if match_empire_by_seshat_id(seshat_id, empire_id):
        return True

    # Fallback: Name pattern matching (only if no SeshatID or not matched)
    if match_empire_by_name(name, empire_id):
        return True

    return False


def calculate_centroid(geometry: dict) -> tuple[float, float]:
    """Calculate centroid of a geometry. Returns (lat, lng)."""
    try:
        geom = shape(geometry)
        centroid = geom.centroid
        return (centroid.y, centroid.x)  # lat, lng
    except Exception:
        # Fallback: average of all coordinates
        coords = []
        def extract_coords(geom):
            if geom['type'] == 'Polygon':
                for ring in geom['coordinates']:
                    coords.extend(ring)
            elif geom['type'] == 'MultiPolygon':
                for poly in geom['coordinates']:
                    for ring in poly:
                        coords.extend(ring)

        extract_coords(geometry)
        if coords:
            avg_lng = sum(c[0] for c in coords) / len(coords)
            avg_lat = sum(c[1] for c in coords) / len(coords)
            return (avg_lat, avg_lng)
        return (0, 0)


def extract_empire_features(data: dict, empire_id: str) -> dict[int, list[dict]]:
    """
    Extract all features for an empire, grouped by year.

    Uses SeshatID matching as primary method, with name pattern fallback.

    Returns: {year: [features]}
    """
    features_by_year = defaultdict(list)
    matched_by_seshat = 0
    matched_by_name = 0

    for feature in data.get('features', []):
        props = feature.get('properties', {})
        seshat_id = props.get('SeshatID', '')

        # Use new matching that checks SeshatID first, then name patterns
        if not match_empire(feature, empire_id):
            continue

        # Track matching method for debugging
        if match_empire_by_seshat_id(seshat_id, empire_id):
            matched_by_seshat += 1
        else:
            matched_by_name += 1

        # Get temporal range
        from_year = props.get('FromYear')
        to_year = props.get('ToYear')

        if from_year is None:
            continue

        # Use the midpoint year or from_year as the key
        if to_year is not None:
            year = (from_year + to_year) // 2
        else:
            year = from_year

        features_by_year[year].append(feature)

    if features_by_year:
        logger.debug(f"  Matched {matched_by_seshat} by SeshatID, {matched_by_name} by name pattern")

    return dict(features_by_year)


def merge_features_to_geojson(features: list[dict], empire_id: str, year: int) -> dict:
    """
    Merge multiple features into a single GeoJSON FeatureCollection.
    """
    # Create feature collection
    merged_features = []

    for feature in features:
        geom = feature.get('geometry')
        props = feature.get('properties', {})

        if geom:
            merged_features.append({
                'type': 'Feature',
                'properties': {
                    'name': props.get('Name', ''),
                    'year': year,
                    'area_km2': props.get('Area', 0),
                    'seshat_id': props.get('SeshatID', ''),
                    'from_year': props.get('FromYear'),
                    'to_year': props.get('ToYear'),
                },
                'geometry': geom
            })

    # Calculate overall centroid
    all_centroids = [calculate_centroid(f['geometry']) for f in merged_features if f.get('geometry')]
    if all_centroids:
        avg_lat = sum(c[0] for c in all_centroids) / len(all_centroids)
        avg_lng = sum(c[1] for c in all_centroids) / len(all_centroids)
        centroid = [avg_lat, avg_lng]
    else:
        centroid = [0, 0]

    return {
        'type': 'FeatureCollection',
        'properties': {
            'empire_id': empire_id,
            'year': year,
            'centroid': centroid,
        },
        'features': merged_features
    }


def process_empire(data: dict, empire_id: str, output_dir: Path) -> dict | None:
    """
    Process a single empire, extracting all temporal snapshots.

    Returns metadata about the empire, or None if no data found.
    """
    logger.info(f"Processing {empire_id}...")

    features_by_year = extract_empire_features(data, empire_id)

    if not features_by_year:
        logger.warning(f"  No features found for {empire_id}")
        return None

    # Create empire directory
    empire_dir = output_dir / empire_id
    empire_dir.mkdir(parents=True, exist_ok=True)

    years = sorted(features_by_year.keys())
    centroids = {}
    areas_by_year = {}

    # Calculate total area for each year
    for year, features in features_by_year.items():
        total_area = 0
        for feature in features:
            area = feature.get('properties', {}).get('Area', 0)
            if area and isinstance(area, (int, float)):
                total_area += area
        areas_by_year[year] = total_area

    # Find year with maximum total area (peak territorial extent)
    if areas_by_year and any(a > 0 for a in areas_by_year.values()):
        peak_year = max(areas_by_year.keys(), key=lambda y: areas_by_year[y])
        logger.info(f"  Peak extent: {peak_year} ({areas_by_year[peak_year]:,.0f} km²)")
    else:
        # Fallback to year with most features if no area data
        peak_year = max(features_by_year.keys(), key=lambda y: len(features_by_year[y]))
        logger.info(f"  Peak extent (by feature count): {peak_year}")

    # Export each year's boundaries
    for year in years:
        features = features_by_year[year]
        geojson_data = merge_features_to_geojson(features, empire_id, year)

        # Store centroid
        centroids[str(year)] = geojson_data['properties']['centroid']

        # Write GeoJSON file
        output_path = empire_dir / f"{year}.geojson"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, separators=(',', ':'))

    # Get metadata from config or derive from data
    meta = EMPIRE_METADATA.get(empire_id, {})

    # Create metadata.json
    metadata = {
        'id': empire_id,
        'name': meta.get('name', empire_id.replace('_', ' ').title()),
        'region': meta.get('region', 'Unknown'),
        'years': years,
        'defaultYear': peak_year,
        'peakYear': peak_year,
        'peakArea': areas_by_year.get(peak_year, 0),
        'startYear': min(years),
        'endYear': max(years),
        'color': meta.get('color', 0x888888),
        'centroids': centroids,
        'featureCount': {str(y): len(features_by_year[y]) for y in years},
        'areaByYear': {str(y): areas_by_year.get(y, 0) for y in years},
    }

    metadata_path = empire_dir / 'metadata.json'
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"  Exported {len(years)} time periods: {min(years)} to {max(years)}")

    return metadata


def list_unique_polities(data: dict) -> list[str]:
    """List all unique polity names in the dataset."""
    names = set()
    for feature in data.get('features', []):
        name = feature.get('properties', {}).get('Name', '')
        if name:
            names.add(name)
    return sorted(names)


def create_combined_metadata(all_metadata: list[dict], output_dir: Path):
    """Create a combined metadata.json file for all empires."""
    # Group by region
    by_region = defaultdict(list)
    for meta in all_metadata:
        by_region[meta['region']].append({
            'id': meta['id'],
            'name': meta['name'],
            'startYear': meta['startYear'],
            'endYear': meta['endYear'],
            'color': meta['color'],
            'defaultYear': meta['defaultYear'],
            'yearCount': len(meta['years']),
        })

    combined = {
        'empires': dict(sorted(by_region.items())),
        'totalEmpires': len(all_metadata),
        'regions': sorted(by_region.keys()),
    }

    output_path = output_dir / 'metadata.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(combined, f, indent=2)

    logger.info(f"Created combined metadata with {len(all_metadata)} empires")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Process Cliopatria historical boundaries'
    )
    parser.add_argument(
        '--list-empires', action='store_true',
        help='List all unique polity names in the dataset'
    )
    parser.add_argument(
        '--list-configured', action='store_true',
        help='List all configured empire IDs'
    )
    parser.add_argument(
        '--empire', '-e', type=str,
        help='Process only a specific empire (by ID)'
    )
    parser.add_argument(
        '--output', '-o', type=Path, default=OUTPUT_DIR,
        help=f'Output directory (default: {OUTPUT_DIR})'
    )
    parser.add_argument(
        '--no-download', action='store_true',
        help='Do not auto-download Cliopatria data if missing'
    )

    args = parser.parse_args()

    # Handle --list-configured
    if args.list_configured:
        print("\nConfigured empire IDs:")
        for empire_id, meta in sorted(EMPIRE_METADATA.items()):
            print(f"  {empire_id}: {meta['name']} ({meta['region']})")
        return

    # Load data
    if args.no_download and not CLIOPATRIA_GEOJSON_PATH.exists():
        logger.error(f"Cliopatria data not found at {CLIOPATRIA_GEOJSON_PATH}")
        return

    data = load_cliopatria()

    # Handle --list-empires
    if args.list_empires:
        names = list_unique_polities(data)
        print(f"\nUnique polity names in Cliopatria ({len(names)} total):\n")
        for name in names[:100]:  # Show first 100
            print(f"  {name}")
        if len(names) > 100:
            print(f"\n  ... and {len(names) - 100} more")
        return

    # Process empires
    args.output.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    all_metadata = []

    if args.empire:
        # Process single empire
        if args.empire not in EMPIRE_MAPPINGS:
            logger.error(f"Unknown empire ID: {args.empire}")
            logger.info(f"Available: {', '.join(sorted(EMPIRE_MAPPINGS.keys()))}")
            return

        meta = process_empire(data, args.empire, args.output)
        if meta:
            all_metadata.append(meta)
    else:
        # Process all configured empires
        for empire_id in sorted(EMPIRE_MAPPINGS.keys()):
            meta = process_empire(data, empire_id, args.output)
            if meta:
                all_metadata.append(meta)

    # Create combined metadata
    if all_metadata:
        create_combined_metadata(all_metadata, args.output)

    elapsed = time.time() - start_time
    logger.info(f"\n{'='*60}")
    logger.info("COMPLETE!")
    logger.info(f"  Empires processed: {len(all_metadata)}")
    logger.info(f"  Time elapsed:      {elapsed:.1f} seconds")
    logger.info(f"  Output directory:  {args.output}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    main()
