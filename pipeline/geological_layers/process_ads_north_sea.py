"""
Download and convert Unpath'd Waters (ADS) North Sea geological shapefiles to GeoJSON.

Source: University of Bradford, CC BY 4.0
  https://doi.org/10.5284/1126107

Usage:
    python -m pipeline.geological_layers.process_ads_north_sea
    python -m pipeline.geological_layers.process_ads_north_sea --no-download
    python -m pipeline.geological_layers.process_ads_north_sea --layer palaeochannels
"""

import argparse
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path

try:
    import geopandas as gpd
except ImportError:
    print("Missing dependency: geopandas")
    print("  pip install geopandas")
    exit(1)

from loguru import logger

# =============================================================================
# Configuration
# =============================================================================

BASE_URL = "https://archaeologydataservice.ac.uk/catalogue/adsdata/arch-7678-1/dissemination"

RAW_DIR = Path("data/raw/geological")
OUTPUT_DIR = Path("public/data/geological")

# Simplification tolerance in degrees (~0.001 deg ≈ 111m at equator)
SIMPLIFY_TOLERANCE = 0.001

# Layer definitions: source zip → output file, group, color, description
# Colors follow geological mapping conventions, brightened for dark globe background
LAYERS = {
    "palaeochannels": {
        "zip": "Unpathd_Waters_Palaeolandscape_Features.zip",
        "output": "palaeochannels.geojson",
        "group": "Landscape",
        "color": "#5BC0EB",
        "label": "Palaeochannels & Lakes",
        "description": "Palaeochannels and lakes from the Late Pleistocene to Holocene",
    },
    "high_ground": {
        "zip": "Unpathd_Waters_Positive_Palaeolandscape_Features.zip",
        "output": "high_ground.geojson",
        "group": "Landscape",
        "color": "#FDE74C",
        "label": "High Ground Features",
        "description": "Positive palaeolandscape features (high ground, ridges)",
    },
    "palaeovalleys_lgm": {
        "zip": "D_Garcia_Moreno_Hypothesised_Palaeovalleys.zip",
        "output": "palaeovalleys_lgm.geojson",
        "group": "Landscape",
        "color": "#9BC53D",
        "label": "Palaeovalleys (LGM)",
        "description": "Hypothesised drainage routes from the Last Glacial Maximum (Garcia Moreno 2017)",
    },
    "drainage_80k_20k": {
        "zip": "Hijma_2011_Hypothesised_Features_80_to_20_ka_Lines.zip",
        "output": "drainage_80k_20k.geojson",
        "group": "Landscape",
        "color": "#56E39F",
        "label": "Drainage (80k-20k)",
        "description": "Hypothesised drainage routes, 80,000-20,000 years ago (Hijma & Cohen 2011)",
    },
    "drainage_11k": {
        "zip": "Ode_Smoothed.zip",
        "output": "drainage_11k.geojson",
        "group": "Landscape",
        "color": "#59C3C3",
        "label": "Drainage (~11ka)",
        "description": "Hypothesised drainage routes ~11,000 years ago (Ode et al. 2022)",
    },
    "peat_polygons": {
        "zip": "Unpathd_Waters_Peat_Polygons.zip",
        "output": "peat_polygons.geojson",
        "group": "Peat",
        "color": "#E8985E",
        "label": "Peat Deposits",
        "description": "Mapped peat deposits and peat-filled features",
    },
    "peat_points": {
        "zip": "Unpathd_Waters_Peat_Point_Shapefile.zip",
        "output": "peat_points.geojson",
        "group": "Peat",
        "color": "#C45BAA",
        "label": "Peat Core Points",
        "description": "Peat occurrence from core data (points)",
    },
    "archaeological_finds": {
        "zip": "Submerged_Landscapes_Archaeological_Finds_2019_to_2024.zip",
        "output": "archaeological_finds.geojson",
        "group": "Research",
        "color": "#F45B69",
        "label": "Archaeological Finds",
        "description": "Areas where archaeological material was recovered during seabed dredging (2019-2024)",
    },
    "boreholes": {
        "zip": "Submerged_Landscapes_Research_Centre_Boreholes_2016_to_2019.zip",
        "output": "boreholes.geojson",
        "group": "Research",
        "color": "#F7B32B",
        "label": "Boreholes",
        "description": "Borehole locations from the Europe's Lost Frontiers project (2016-2019)",
    },
}


def download_layer(layer_id: str, layer_cfg: dict) -> Path:
    """Download a single zip file from ADS. Returns path to zip."""
    zip_name = layer_cfg["zip"]
    dest = RAW_DIR / zip_name
    if dest.exists():
        logger.info(f"  Already downloaded: {zip_name}")
        return dest

    url = f"{BASE_URL}/{zip_name}"
    logger.info(f"  Downloading {url} ...")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "AncientMap/1.0 (archaeological research)"}
        )
        with urllib.request.urlopen(req) as response, open(dest, "wb") as out:
            out.write(response.read())
        logger.info(f"  Saved: {dest} ({dest.stat().st_size / 1024:.0f} KB)")
    except Exception as e:
        logger.error(f"  Failed to download {zip_name}: {e}")
        raise
    return dest


def find_shapefile_in_zip(zip_path: Path) -> str:
    """Find the .shp file inside a zip archive."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        shp_files = [n for n in zf.namelist() if n.lower().endswith(".shp")]
        if not shp_files:
            raise FileNotFoundError(f"No .shp file found in {zip_path}")
        if len(shp_files) > 1:
            logger.warning(f"  Multiple .shp files in {zip_path}, using first: {shp_files[0]}")
        return shp_files[0]


def convert_shapefile(zip_path: Path, layer_id: str) -> dict:
    """Read shapefile from zip, reproject to WGS84, simplify, return GeoJSON dict."""
    shp_name = find_shapefile_in_zip(zip_path)
    logger.info(f"  Reading shapefile: {shp_name}")

    # Extract to temp dir and read with geopandas
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
        shp_path = Path(tmp) / shp_name
        gdf = gpd.read_file(shp_path)

    logger.info(
        f"  CRS: {gdf.crs}, Features: {len(gdf)}, Geometry types: {gdf.geom_type.unique().tolist()}"
    )

    # Reproject to WGS84 if needed
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        logger.info(f"  Reprojecting from {gdf.crs} to EPSG:4326")
        gdf = gdf.to_crs(epsg=4326)

    # Drop empty geometries
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
    logger.info(f"  Valid features after filtering: {len(gdf)}")

    # Simplify (skip for points)
    geom_types = set(gdf.geom_type.unique())
    point_types = {"Point", "MultiPoint"}
    if not geom_types.issubset(point_types):
        logger.info(f"  Simplifying with tolerance {SIMPLIFY_TOLERANCE} degrees")
        gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)

    # Convert to GeoJSON dict
    geojson_str = gdf.to_json()
    geojson_dict = json.loads(geojson_str)

    # Strip properties to reduce file size — we only need geometry
    for feature in geojson_dict.get("features", []):
        feature["properties"] = {}

    return geojson_dict


def process_layer(layer_id: str, layer_cfg: dict, skip_download: bool = False) -> bool:
    """Process a single layer end-to-end. Returns True on success."""
    logger.info(f"Processing: {layer_id} ({layer_cfg['label']})")

    # Download
    zip_path = RAW_DIR / layer_cfg["zip"]
    if not skip_download:
        zip_path = download_layer(layer_id, layer_cfg)
    elif not zip_path.exists():
        logger.error(f"  Zip not found (use without --no-download): {zip_path}")
        return False

    # Convert
    geojson_dict = convert_shapefile(zip_path, layer_id)
    feature_count = len(geojson_dict.get("features", []))

    # Write output
    out_path = OUTPUT_DIR / layer_cfg["output"]
    with open(out_path, "w") as f:
        json.dump(geojson_dict, f, separators=(",", ":"))
    size_kb = out_path.stat().st_size / 1024
    logger.info(f"  Written: {out_path} ({feature_count} features, {size_kb:.0f} KB)")
    return True


def generate_metadata() -> None:
    """Generate metadata.json for the frontend."""
    layers_meta = {}
    for layer_id, cfg in LAYERS.items():
        out_path = OUTPUT_DIR / cfg["output"]
        feature_count = 0
        if out_path.exists():
            with open(out_path) as f:
                data = json.load(f)
                feature_count = len(data.get("features", []))

        layers_meta[layer_id] = {
            "file": cfg["output"].replace(".geojson", ""),
            "label": cfg["label"],
            "color": cfg["color"],
            "group": cfg["group"],
            "description": cfg["description"],
            "featureCount": feature_count,
        }

    metadata = {
        "source": {
            "name": "Unpath'd Waters Palaeolandscapes Data Package",
            "institution": "University of Bradford",
            "license": "CC BY 4.0",
            "doi": "https://doi.org/10.5284/1126107",
            "citation": "University of Bradford (2025) Digital Data from the Land Beneath the Sea Palaeolandscapes Project (Unpath'd Waters), 2016-2024",
        },
        "coverage": {
            "region": "North Sea",
            "bbox": [-1.14, 50.43, 10.55, 57.82],
            "periods": ["Palaeolithic", "Mesolithic"],
        },
        "layers": layers_meta,
    }

    meta_path = OUTPUT_DIR / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata written: {meta_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert ADS North Sea geological shapefiles to GeoJSON"
    )
    parser.add_argument("--no-download", action="store_true", help="Skip download, use cached zips")
    parser.add_argument("--layer", type=str, help="Process only this layer (e.g. palaeochannels)")
    parser.add_argument("--output", type=str, help="Override output directory")
    args = parser.parse_args()

    global OUTPUT_DIR
    if args.output:
        OUTPUT_DIR = Path(args.output)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.layer:
        if args.layer not in LAYERS:
            logger.error(f"Unknown layer: {args.layer}. Available: {', '.join(LAYERS.keys())}")
            return
        layers_to_process = {args.layer: LAYERS[args.layer]}
    else:
        layers_to_process = LAYERS

    success = 0
    failed = 0
    for layer_id, layer_cfg in layers_to_process.items():
        try:
            if process_layer(layer_id, layer_cfg, skip_download=args.no_download):
                success += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"  Failed: {layer_id}: {e}")
            failed += 1

    logger.info(f"\nDone: {success} succeeded, {failed} failed")
    generate_metadata()


if __name__ == "__main__":
    main()
