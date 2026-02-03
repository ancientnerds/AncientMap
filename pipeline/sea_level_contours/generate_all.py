"""
Pre-compute paleoshoreline contours for all sea levels.

Uses GEBCO bathymetry data to generate contour lines at every meter of sea level,
enabling visualization of ancient coastlines during ice ages.

Usage:
    python -m pipeline.sea_level_contours.generate_all
    python -m pipeline.sea_level_contours.generate_all --level -120
    python -m pipeline.sea_level_contours.generate_all --range -150 50

The script will automatically download GEBCO 2024 (~4GB compressed) if not found.
"""

import argparse
import json
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

try:
    import geojson
    import xarray as xr
    from shapely.geometry import LineString, MultiLineString
    from shapely.ops import linemerge
    from simplification.cutil import simplify_coords
    from skimage import measure
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("\nInstall required packages:")
    print("  pip install xarray netCDF4 shapely scikit-image simplification geojson")
    exit(1)

from loguru import logger

# =============================================================================
# Configuration
# =============================================================================

# Sea level range for archaeology (-150m covers LGM, +50m covers potential future)
DEFAULT_MIN_LEVEL = -150
DEFAULT_MAX_LEVEL = 50

# Detail levels matching the frontend LOD system
DETAIL_TOLERANCES = {
    '110m': 0.125,   # ~14km at equator (4x more detail)
    '50m': 0.017,    # ~1.9km (3x more detail)
    '10m': 0.0025,   # ~0.28km (2x more detail)
}

# Minimum line length in degrees to keep (0 = keep all)
MIN_LINE_LENGTH = {
    '110m': 0.0,
    '50m': 0.0,
    '10m': 0.0,
}

# Output directory
OUTPUT_DIR = Path('ancient-nerds-map/public/data/sea-levels')

# GEBCO data path and download URL
GEBCO_PATH = Path('data/raw/GEBCO_2024.nc')
GEBCO_DOWNLOAD_URL = 'https://www.bodc.ac.uk/data/open_download/gebco/gebco_2024/zip/'


# =============================================================================
# Download GEBCO Data
# =============================================================================

def download_gebco(output_path: Path = GEBCO_PATH) -> Path:
    """Download GEBCO 2024 data if not present."""
    if output_path.exists():
        logger.info(f"GEBCO data already exists at {output_path}")
        return output_path

    zip_path = output_path.with_suffix('.zip')
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading GEBCO 2024 (~4GB compressed)...")
    logger.info(f"URL: {GEBCO_DOWNLOAD_URL}")
    logger.info("This may take 10-30 minutes depending on your connection...")

    def progress_hook(count, block_size, total_size):
        percent = count * block_size * 100 / total_size
        downloaded_mb = count * block_size / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        print(f"\r  Downloading: {percent:.1f}% ({downloaded_mb:.0f}/{total_mb:.0f} MB)", end='', flush=True)

    try:
        urllib.request.urlretrieve(GEBCO_DOWNLOAD_URL, zip_path, progress_hook)
        print()  # New line after progress
        logger.info(f"Downloaded to {zip_path}")

        logger.info("Extracting GEBCO NetCDF file...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.endswith('.nc'):
                    logger.info(f"  Extracting {name}...")
                    zf.extract(name, output_path.parent)
                    extracted = output_path.parent / name
                    if extracted != output_path:
                        shutil.move(str(extracted), str(output_path))
                    break

        # Clean up zip file
        zip_path.unlink()
        logger.info(f"GEBCO data ready at {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"Download failed: {e}")
        logger.info("Please download GEBCO 2024 manually from https://download.gebco.net/")
        raise


# =============================================================================
# Data Loading
# =============================================================================

def load_gebco(path: Path = GEBCO_PATH, auto_download: bool = True) -> xr.DataArray:
    """Load GEBCO NetCDF elevation/bathymetry data."""
    if not path.exists():
        if auto_download:
            logger.info(f"GEBCO data not found at {path}")
            download_gebco(path)
        else:
            raise FileNotFoundError(f"GEBCO data not found at {path}")

    logger.info(f"Loading GEBCO data from {path}...")
    ds = xr.open_dataset(path)

    if 'elevation' in ds:
        elevation = ds['elevation']
    elif 'z' in ds:
        elevation = ds['z']
    else:
        raise ValueError(f"Could not find elevation variable in {path}")

    logger.info(f"Loaded: {elevation.shape} grid, "
                f"lat range [{float(elevation.lat.min()):.1f}, {float(elevation.lat.max()):.1f}], "
                f"lon range [{float(elevation.lon.min()):.1f}, {float(elevation.lon.max()):.1f}]")

    return elevation


# =============================================================================
# Contour Extraction
# =============================================================================

def extract_contour(elevation: np.ndarray, level: float, lats: np.ndarray, lons: np.ndarray) -> MultiLineString:
    """Extract contour at given elevation using marching squares."""
    contours = measure.find_contours(elevation, level)

    lines = []
    for contour in contours:
        lat_coords = np.interp(contour[:, 0], range(len(lats)), lats)
        lon_coords = np.interp(contour[:, 1], range(len(lons)), lons)

        if len(lat_coords) >= 2:
            coords = list(zip(lon_coords, lat_coords, strict=False))
            lines.append(LineString(coords))

    if lines:
        merged = linemerge(lines)
        if isinstance(merged, LineString):
            return MultiLineString([merged])
        return merged

    return MultiLineString()


def line_length_degrees(line: LineString) -> float:
    """Calculate approximate line length in degrees."""
    coords = list(line.coords)
    total = 0.0
    for i in range(len(coords) - 1):
        dx = coords[i+1][0] - coords[i][0]
        dy = coords[i+1][1] - coords[i][1]
        total += (dx*dx + dy*dy) ** 0.5
    return total


def simplify_geometry(geom, tolerance: float, min_length: float = 0.0):
    """Simplify geometry using Douglas-Peucker algorithm."""
    if geom.is_empty:
        return geom

    if isinstance(geom, LineString):
        coords = list(geom.coords)
        if len(coords) > 2:
            simplified = simplify_coords(coords, tolerance)
            if len(simplified) >= 2:
                line = LineString(simplified)
                if line_length_degrees(line) >= min_length:
                    return line
        elif len(coords) >= 2:
            line = LineString(coords)
            if line_length_degrees(line) >= min_length:
                return line
        return LineString()

    elif isinstance(geom, MultiLineString):
        simplified_lines = []
        for line in geom.geoms:
            simplified = simplify_geometry(line, tolerance, min_length)
            if not simplified.is_empty:
                simplified_lines.append(simplified)

        if simplified_lines:
            return MultiLineString(simplified_lines)
        return MultiLineString()

    return geom


# =============================================================================
# Export
# =============================================================================

def export_geojson(geom, output_path: Path, sea_level: int):
    """Export geometry to GeoJSON file."""
    features = []

    if isinstance(geom, LineString):
        geoms = [geom]
    elif isinstance(geom, MultiLineString):
        geoms = list(geom.geoms)
    else:
        geoms = []

    for line in geoms:
        if not line.is_empty and len(list(line.coords)) >= 2:
            features.append(geojson.Feature(
                geometry=geojson.LineString(list(line.coords)),
                properties={'sea_level': sea_level}
            ))

    collection = geojson.FeatureCollection(features)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        geojson.dump(collection, f, separators=(',', ':'))


# =============================================================================
# Processing
# =============================================================================

def process_level(level: int, elevation_data: tuple[np.ndarray, np.ndarray, np.ndarray], output_dir: Path = OUTPUT_DIR) -> dict:
    """Process a single sea level."""
    elevation, lats, lons = elevation_data

    logger.info(f"Processing {level}m...")
    start_time = time.time()

    # Extract contour at this sea level
    contour = extract_contour(elevation, level, lats, lons)

    stats = {
        'level': level,
        'raw_features': len(list(contour.geoms)) if isinstance(contour, MultiLineString) else 1,
        'files': {}
    }

    # Generate simplified versions for each detail level
    for detail_name, tolerance in DETAIL_TOLERANCES.items():
        min_length = MIN_LINE_LENGTH.get(detail_name, 0.0)
        simplified = simplify_geometry(contour, tolerance, min_length)

        if isinstance(simplified, MultiLineString):
            num_features = len(list(simplified.geoms))
            total_coords = sum(len(list(line.coords)) for line in simplified.geoms)
        elif isinstance(simplified, LineString):
            num_features = 1
            total_coords = len(list(simplified.coords))
        else:
            num_features = 0
            total_coords = 0

        output_path = output_dir / f"{level}m" / f"contour_{detail_name}.json"
        export_geojson(simplified, output_path, level)

        file_size = output_path.stat().st_size if output_path.exists() else 0
        stats['files'][detail_name] = {
            'features': num_features,
            'coordinates': total_coords,
            'size_kb': round(file_size / 1024, 1)
        }

    elapsed = time.time() - start_time
    logger.debug(f"  {level}m done in {elapsed:.1f}s - {stats['raw_features']} raw features")

    return stats


def generate_metadata(levels: list[int], output_dir: Path = OUTPUT_DIR):
    """Generate metadata.json with level information."""
    metadata = {
        'range': {'min': min(levels), 'max': max(levels)},
        'levels': sorted(levels),
        'details': list(DETAIL_TOLERANCES.keys()),
        'key_levels': [
            {'level': -130, 'label': 'LGM Peak', 'description': 'Last Glacial Maximum peak (~26,000 years ago)'},
            {'level': -120, 'label': 'Late LGM', 'description': 'Late Last Glacial Maximum (~20,000 years ago)'},
            {'level': -80, 'label': 'Meltwater Pulse', 'description': 'Rapid sea level rise (~14,500 years ago)'},
            {'level': -60, 'label': 'Younger Dryas', 'description': 'Cold period (~12,000 years ago)'},
            {'level': -40, 'label': 'Early Holocene', 'description': 'Early Holocene warming (~10,000 years ago)'},
            {'level': 0, 'label': 'Present Day', 'description': 'Current sea level'},
        ],
        'sources': {
            'data': 'GEBCO 2024',
            'url': 'https://www.gebco.net/',
            'license': 'GEBCO is made available under a Creative Commons license'
        }
    }

    output_path = output_dir / 'metadata.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info("Generated metadata.json")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate sea level contour files from GEBCO bathymetry data'
    )
    parser.add_argument(
        '--level', '-l', type=int,
        help='Generate contour for a single sea level (meters)'
    )
    parser.add_argument(
        '--range', '-r', nargs=2, type=int, metavar=('MIN', 'MAX'),
        help=f'Sea level range to process (default: {DEFAULT_MIN_LEVEL} to {DEFAULT_MAX_LEVEL})'
    )
    parser.add_argument(
        '--gebco', '-g', type=Path, default=GEBCO_PATH,
        help=f'Path to GEBCO NetCDF file (default: {GEBCO_PATH})'
    )
    parser.add_argument(
        '--output', '-o', type=Path, default=OUTPUT_DIR,
        help=f'Output directory (default: {OUTPUT_DIR})'
    )
    parser.add_argument(
        '--no-download', action='store_true',
        help='Do not auto-download GEBCO data if missing'
    )

    args = parser.parse_args()

    # Determine levels to process
    if args.level is not None:
        levels = [args.level]
    elif args.range:
        levels = list(range(args.range[0], args.range[1] + 1))
    else:
        levels = list(range(DEFAULT_MIN_LEVEL, DEFAULT_MAX_LEVEL + 1))

    logger.info(f"Will generate contours for {len(levels)} sea levels: {min(levels)}m to {max(levels)}m")

    start_time = time.time()
    all_stats = []

    # Load GEBCO data once
    elevation = load_gebco(args.gebco, auto_download=not args.no_download)
    elevation_data = (
        elevation.values,
        elevation.lat.values,
        elevation.lon.values
    )

    # Process each level
    for i, level in enumerate(levels):
        logger.info(f"[{i+1}/{len(levels)}] Processing {level}m...")
        try:
            stats = process_level(level, elevation_data, args.output)
            all_stats.append(stats)
        except Exception as e:
            logger.error(f"Error processing {level}m: {e}")

    # Generate metadata
    generate_metadata(levels, args.output)

    # Summary
    elapsed = time.time() - start_time
    total_files = len(levels) * len(DETAIL_TOLERANCES)
    total_size_kb = sum(
        stats['files'][detail]['size_kb']
        for stats in all_stats
        for detail in stats['files']
    )

    logger.info(f"\n{'='*60}")
    logger.info("COMPLETE!")
    logger.info(f"  Levels processed: {len(levels)}")
    logger.info(f"  Files generated:  {total_files}")
    logger.info(f"  Total size:       {total_size_kb/1024:.1f} MB")
    logger.info(f"  Time elapsed:     {elapsed/60:.1f} minutes")
    logger.info(f"  Output directory: {args.output}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    main()
