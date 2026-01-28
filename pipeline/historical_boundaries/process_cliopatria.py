"""
Process Cliopatria historical boundaries dataset.

Downloads Cliopatria GeoJSON from GitHub and extracts per-empire boundary files
with temporal snapshots for visualization on the globe.

Data source: https://github.com/Seshat-Global-History-Databank/cliopatria
- 1,800+ political entities with ~15,000 records (3400 BCE - 2024 CE)
- Ready-to-use GeoJSON format (EPSG:4326)
- Peer-reviewed scholarly data published in Nature Scientific Data
- CC BY license

Usage:
    python -m pipeline.historical_boundaries.process_cliopatria
    python -m pipeline.historical_boundaries.process_cliopatria --list-empires
    python -m pipeline.historical_boundaries.process_cliopatria --empire roman
"""

import argparse
import json
import os
import zipfile
import urllib.request
import shutil
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
import time

try:
    from shapely.geometry import shape, mapping, Polygon, MultiPolygon
    from shapely.ops import unary_union
    import geojson
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

# Empire mapping: our ID -> list of Cliopatria name patterns (regex)
# Cliopatria uses various naming conventions, so we match by pattern
EMPIRE_MAPPINGS = {
    # Ancient Near East
    'egyptian': [
        r'Ancient Egypt.*',
        r'Ptolemaic.*',
        r'New Kingdom.*Egypt',
        r'Middle Kingdom.*Egypt',
        r'Old Kingdom.*Egypt',
        r'Egypt.*Dynasty',
        r'.*Egyptian.*Empire',
    ],
    'akkadian': [r'Akkad.*Empire', r'Akkadian.*'],
    'babylonian': [
        r'.*Babylon.*',
        r'Neo-Babylon.*',
        r'Old Babylon.*',
    ],
    'assyrian': [
        r'.*Assyria.*',
        r'Neo-Assyria.*',
        r'Middle Assyria.*',
    ],
    'hittite': [r'Hittite.*', r'.*Hatti.*'],

    # Mediterranean
    'roman': [
        r'Roman.*',
        r'.*Rome.*',
        r'Imperium Romanum',
        r'Western Roman.*',
        r'Roman Republic',
        r'Roman Principate',
        r'Roman Dominate',
    ],
    'greek': [
        r'.*Athens.*',
        r'.*Sparta.*',
        r'Classical Greece',
        r'Greek.*',
        r'Hellenic.*',
        r'Delian League',
    ],
    'macedonian': [
        r'Macedon.*',
        r'.*Alexander.*',
        r'Antigonid.*',
    ],
    'byzantine': [
        r'Byzantine.*',
        r'Eastern Roman.*',
        r'.*Constantinople.*',
    ],
    'carthaginian': [r'Carthag.*', r'Punic.*'],

    # Persian/Central Asia
    'achaemenid': [
        r'Achaemenid.*',
        r'Persian Empire.*Achaemenid',
        r'First Persian Empire',
    ],
    'parthian': [r'Parthia.*', r'Arsacid.*'],
    'sassanid': [r'Sassanid.*', r'Sasanian.*', r'Second Persian Empire'],
    'seleucid': [r'Seleucid.*'],
    'mongol': [
        r'Mongol.*Empire',
        r'.*Genghis.*',
        r'Yuan.*',
        r'Golden Horde',
        r'Ilkhanate',
        r'Chagatai.*',
    ],
    'timurid': [r'Timurid.*', r'.*Tamerlane.*'],

    # East Asia
    'shang': [r'Shang.*'],
    'zhou': [r'.*Zhou.*', r'Western Zhou', r'Eastern Zhou'],
    'qin': [r'Qin.*Dynasty', r'Qin Empire'],
    'han': [
        r'Han.*Dynasty',
        r'Western Han',
        r'Eastern Han',
        r'Han Empire',
    ],
    'tang': [r'Tang.*Dynasty', r'Tang Empire'],
    'song': [r'Song.*Dynasty', r'Northern Song', r'Southern Song'],
    'ming': [r'Ming.*Dynasty', r'Ming Empire'],
    'qing': [r'Qing.*Dynasty', r'Qing Empire', r'Manchu.*'],

    # South Asia
    'maurya': [r'Maurya.*', r'Mauryan.*'],
    'gupta': [r'Gupta.*'],
    'mughal': [r'Mughal.*', r'Moghul.*'],
    'chola': [r'Chola.*'],
    'delhi': [r'Delhi Sultanate.*'],

    # Southeast Asia
    'khmer': [r'Khmer.*', r'Angkor.*', r'Cambodia.*Empire'],
    'majapahit': [r'Majapahit.*'],
    'srivijaya': [r'Srivijaya.*'],

    # Africa
    'kush': [r'Kush.*', r'Nubia.*', r'Meroe.*'],
    'axum': [r'Axum.*', r'Aksumite.*'],
    'mali': [r'Mali.*Empire'],
    'songhai': [r'Songhai.*', r'Songhay.*'],
    'ghana': [r'Ghana.*Empire'],

    # Americas
    'maya': [r'Maya.*', r'Mayan.*'],
    'aztec': [r'Aztec.*', r'Mexica.*', r'Triple Alliance'],
    'inca': [r'Inca.*', r'Tawantinsuyu'],

    # Islamic
    'umayyad': [r'Umayyad.*'],
    'abbasid': [r'Abbasid.*'],
    'fatimid': [r'Fatimid.*'],
    'ottoman': [r'Ottoman.*'],
    'ayyubid': [r'Ayyubid.*'],

    # Medieval Europe
    'carolingian': [r'Carolingian.*', r'Frankish.*', r'.*Charlemagne.*'],
    'hre': [r'Holy Roman.*', r'HRE'],
}

# Empire metadata (for UI display)
EMPIRE_METADATA = {
    # Ancient Near East
    'egyptian': {'name': 'Egyptian Empire', 'region': 'Ancient Near East', 'startYear': -3100, 'endYear': -30, 'color': 0xFFD700},
    'akkadian': {'name': 'Akkadian Empire', 'region': 'Ancient Near East', 'startYear': -2334, 'endYear': -2154, 'color': 0xCD853F},
    'babylonian': {'name': 'Babylonian', 'region': 'Ancient Near East', 'startYear': -1894, 'endYear': -539, 'color': 0x8B4513},
    'assyrian': {'name': 'Assyrian Empire', 'region': 'Ancient Near East', 'startYear': -2500, 'endYear': -609, 'color': 0x800000},
    'hittite': {'name': 'Hittite Empire', 'region': 'Ancient Near East', 'startYear': -1600, 'endYear': -1178, 'color': 0xA0522D},

    # Mediterranean
    'roman': {'name': 'Roman Empire', 'region': 'Mediterranean', 'startYear': -509, 'endYear': 476, 'color': 0xC02023},
    'greek': {'name': 'Greek City-States', 'region': 'Mediterranean', 'startYear': -800, 'endYear': -338, 'color': 0x4169E1},
    'macedonian': {'name': 'Macedonian Empire', 'region': 'Mediterranean', 'startYear': -338, 'endYear': -168, 'color': 0x9932CC},
    'byzantine': {'name': 'Byzantine Empire', 'region': 'Mediterranean', 'startYear': 330, 'endYear': 1453, 'color': 0x800080},
    'carthaginian': {'name': 'Carthaginian Empire', 'region': 'Mediterranean', 'startYear': -814, 'endYear': -146, 'color': 0xDC143C},

    # Persian/Central Asia
    'achaemenid': {'name': 'Achaemenid Persia', 'region': 'Persian/Central Asia', 'startYear': -550, 'endYear': -330, 'color': 0x1E90FF},
    'parthian': {'name': 'Parthian Empire', 'region': 'Persian/Central Asia', 'startYear': -247, 'endYear': 224, 'color': 0x00CED1},
    'sassanid': {'name': 'Sassanid Empire', 'region': 'Persian/Central Asia', 'startYear': 224, 'endYear': 651, 'color': 0x20B2AA},
    'seleucid': {'name': 'Seleucid Empire', 'region': 'Persian/Central Asia', 'startYear': -312, 'endYear': -63, 'color': 0x4682B4},
    'mongol': {'name': 'Mongol Empire', 'region': 'Persian/Central Asia', 'startYear': 1206, 'endYear': 1368, 'color': 0x2F4F4F},
    'timurid': {'name': 'Timurid Empire', 'region': 'Persian/Central Asia', 'startYear': 1370, 'endYear': 1507, 'color': 0x556B2F},

    # East Asia
    'shang': {'name': 'Shang Dynasty', 'region': 'East Asia', 'startYear': -1600, 'endYear': -1046, 'color': 0xB8860B},
    'zhou': {'name': 'Zhou Dynasty', 'region': 'East Asia', 'startYear': -1046, 'endYear': -256, 'color': 0xDAA520},
    'qin': {'name': 'Qin Dynasty', 'region': 'East Asia', 'startYear': -221, 'endYear': -206, 'color': 0x8B0000},
    'han': {'name': 'Han Dynasty', 'region': 'East Asia', 'startYear': -206, 'endYear': 220, 'color': 0xDC143C},
    'tang': {'name': 'Tang Dynasty', 'region': 'East Asia', 'startYear': 618, 'endYear': 907, 'color': 0xFF4500},
    'song': {'name': 'Song Dynasty', 'region': 'East Asia', 'startYear': 960, 'endYear': 1279, 'color': 0xFF6347},
    'ming': {'name': 'Ming Dynasty', 'region': 'East Asia', 'startYear': 1368, 'endYear': 1644, 'color': 0xFFD700},
    'qing': {'name': 'Qing Dynasty', 'region': 'East Asia', 'startYear': 1644, 'endYear': 1912, 'color': 0xFFA500},

    # South Asia
    'maurya': {'name': 'Maurya Empire', 'region': 'South Asia', 'startYear': -322, 'endYear': -185, 'color': 0x32CD32},
    'gupta': {'name': 'Gupta Empire', 'region': 'South Asia', 'startYear': 320, 'endYear': 550, 'color': 0x228B22},
    'mughal': {'name': 'Mughal Empire', 'region': 'South Asia', 'startYear': 1526, 'endYear': 1857, 'color': 0x006400},
    'chola': {'name': 'Chola Dynasty', 'region': 'South Asia', 'startYear': -300, 'endYear': 1279, 'color': 0x3CB371},
    'delhi': {'name': 'Delhi Sultanate', 'region': 'South Asia', 'startYear': 1206, 'endYear': 1526, 'color': 0x2E8B57},

    # Southeast Asia
    'khmer': {'name': 'Khmer Empire', 'region': 'Southeast Asia', 'startYear': 802, 'endYear': 1431, 'color': 0x8FBC8F},
    'majapahit': {'name': 'Majapahit Empire', 'region': 'Southeast Asia', 'startYear': 1293, 'endYear': 1527, 'color': 0x90EE90},
    'srivijaya': {'name': 'Srivijaya', 'region': 'Southeast Asia', 'startYear': 650, 'endYear': 1377, 'color': 0x98FB98},

    # Africa
    'kush': {'name': 'Kingdom of Kush', 'region': 'Africa', 'startYear': -1070, 'endYear': 350, 'color': 0xD2691E},
    'axum': {'name': 'Aksumite Empire', 'region': 'Africa', 'startYear': 100, 'endYear': 940, 'color': 0xCD853F},
    'mali': {'name': 'Mali Empire', 'region': 'Africa', 'startYear': 1235, 'endYear': 1600, 'color': 0xDEB887},
    'songhai': {'name': 'Songhai Empire', 'region': 'Africa', 'startYear': 1464, 'endYear': 1591, 'color': 0xF4A460},
    'ghana': {'name': 'Ghana Empire', 'region': 'Africa', 'startYear': 300, 'endYear': 1200, 'color': 0xD2B48C},

    # Americas
    'maya': {'name': 'Maya Civilization', 'region': 'Americas', 'startYear': -2000, 'endYear': 1500, 'color': 0x00FF7F},
    'aztec': {'name': 'Aztec Empire', 'region': 'Americas', 'startYear': 1428, 'endYear': 1521, 'color': 0x7CFC00},
    'inca': {'name': 'Inca Empire', 'region': 'Americas', 'startYear': 1438, 'endYear': 1533, 'color': 0x7FFF00},

    # Islamic
    'umayyad': {'name': 'Umayyad Caliphate', 'region': 'Islamic', 'startYear': 661, 'endYear': 750, 'color': 0x00FA9A},
    'abbasid': {'name': 'Abbasid Caliphate', 'region': 'Islamic', 'startYear': 750, 'endYear': 1258, 'color': 0x00FF00},
    'fatimid': {'name': 'Fatimid Caliphate', 'region': 'Islamic', 'startYear': 909, 'endYear': 1171, 'color': 0x32CD32},
    'ottoman': {'name': 'Ottoman Empire', 'region': 'Islamic', 'startYear': 1299, 'endYear': 1922, 'color': 0x228B22},
    'ayyubid': {'name': 'Ayyubid Dynasty', 'region': 'Islamic', 'startYear': 1171, 'endYear': 1341, 'color': 0x006400},

    # Medieval Europe
    'carolingian': {'name': 'Carolingian Empire', 'region': 'Medieval Europe', 'startYear': 751, 'endYear': 888, 'color': 0x4682B4},
    'hre': {'name': 'Holy Roman Empire', 'region': 'Medieval Europe', 'startYear': 800, 'endYear': 1806, 'color': 0x6495ED},
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

    logger.info(f"Downloading Cliopatria dataset...")
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

        logger.info(f"Extracting GeoJSON...")
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
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    logger.info(f"Loaded {len(data.get('features', []))} features")
    return data


# =============================================================================
# Processing
# =============================================================================

def match_empire(name: str, empire_id: str) -> bool:
    """Check if a polity name matches an empire's patterns."""
    patterns = EMPIRE_MAPPINGS.get(empire_id, [])
    for pattern in patterns:
        if re.match(pattern, name, re.IGNORECASE):
            return True
    return False


def calculate_centroid(geometry: dict) -> Tuple[float, float]:
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


def extract_empire_features(data: dict, empire_id: str) -> Dict[int, List[dict]]:
    """
    Extract all features for an empire, grouped by year.

    Returns: {year: [features]}
    """
    features_by_year = defaultdict(list)

    for feature in data.get('features', []):
        props = feature.get('properties', {})
        name = props.get('Name', '')

        if not match_empire(name, empire_id):
            continue

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

    return dict(features_by_year)


def merge_features_to_geojson(features: List[dict], empire_id: str, year: int) -> dict:
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


def process_empire(data: dict, empire_id: str, output_dir: Path) -> Optional[dict]:
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


def list_unique_polities(data: dict) -> List[str]:
    """List all unique polity names in the dataset."""
    names = set()
    for feature in data.get('features', []):
        name = feature.get('properties', {}).get('Name', '')
        if name:
            names.add(name)
    return sorted(names)


def create_combined_metadata(all_metadata: List[dict], output_dir: Path):
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
        'empires': {region: empires for region, empires in sorted(by_region.items())},
        'totalEmpires': len(all_metadata),
        'regions': list(sorted(by_region.keys())),
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
    logger.info(f"COMPLETE!")
    logger.info(f"  Empires processed: {len(all_metadata)}")
    logger.info(f"  Time elapsed:      {elapsed:.1f} seconds")
    logger.info(f"  Output directory:  {args.output}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    main()
