"""
Convert Sturt et al. 2013 palaeo-coastline shapefiles to per-slice GeoJSON.

Source: Archaeology Data Service — 'Stepping Stones' project
  https://archaeologydataservice.ac.uk/archives/view/stepping_ahrc_2012/
  License: CC BY

22 time slices at 500-year intervals from 11,000 BP to 500 BP.
Automated download from ADS is blocked (403), so this script expects the
user to have manually downloaded the shapefile bundle(s) into
  data/raw/geological/sturt_2013/
and runs with --no-download (default).

The script handles both distribution layouts:
  A) One shapefile with an age/year column (filters per slice)
  B) One shapefile per slice (iterates files, matches year from filename)

Usage:
    python -m pipeline.geological_layers.process_sturt_2013
    python -m pipeline.geological_layers.process_sturt_2013 --inspect
    python -m pipeline.geological_layers.process_sturt_2013 --output public/data/geological
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from pathlib import Path

try:
    import geopandas as gpd
except ImportError:
    print("Missing dependency: geopandas")
    print("  pip install geopandas")
    raise SystemExit(1)

from loguru import logger

# =============================================================================
# Configuration
# =============================================================================

RAW_DIR = Path("data/raw/geological/sturt_2013")
OUTPUT_DIR = Path("public/data/geological")
METADATA_PATH = OUTPUT_DIR / "metadata.json"

SIMPLIFY_TOLERANCE = 0.001  # degrees; ~111 m at equator

TIME_STEPS_BP = [
    11000, 10500, 10000, 9500, 9000, 8500, 8000, 7500, 7000, 6500, 6000, 5500,
    5000, 4500, 4000, 3500, 3000, 2500, 2000, 1500, 1000, 500,
]

SOURCE_META = {
    "name": "Sturt et al. 2013 — 'Stepping Stones' sea-level reconstructions",
    "institution": "Archaeology Data Service",
    "license": "CC BY 4.0",
    "doi": "https://doi.org/10.5284/1021326",
    "citation": (
        "Sturt, F., Garrow, D., Bradley, S. (2013). "
        "New models of North West European Holocene palaeogeography and inundation. "
        "Journal of Archaeological Science."
    ),
    "url": "https://archaeologydataservice.ac.uk/archives/view/stepping_ahrc_2012/",
}

LAYER_META = {
    "sourceId": "sturt_2013",
    "label": "UK Sea Level (Sturt 2013)",
    "color": "#3B82F6",
    "group": "SeaLevel",
    "description": "500-year-resolution palaeo-coastline reconstructions for UK & Ireland (11ka–500 BP)",
}

# Attribute columns that plausibly carry the year/age. Checked in order.
AGE_COLUMN_CANDIDATES = ["YearBP", "yearbp", "year_bp", "age_BP", "age", "AGE", "Age", "BP", "bp"]

# =============================================================================
# Helpers
# =============================================================================


def find_zip_files(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    return sorted(raw_dir.glob("*.zip"))


def list_shapefiles_in_zip(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return [n for n in zf.namelist() if n.lower().endswith(".shp")]


def extract_zip(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)


def read_shapefile(shp_path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(shp_path)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        logger.info(f"  Reprojecting from {gdf.crs} to EPSG:4326")
        gdf = gdf.to_crs(epsg=4326)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
    return gdf


def simplify_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    geom_types = set(gdf.geom_type.unique())
    if not geom_types.issubset({"Point", "MultiPoint"}):
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
    return gdf


def gdf_to_stripped_geojson(gdf: gpd.GeoDataFrame) -> dict:
    data = json.loads(gdf.to_json())
    for feature in data.get("features", []):
        feature["properties"] = {}
    return data


def detect_age_column(gdf: gpd.GeoDataFrame) -> str | None:
    for col in AGE_COLUMN_CANDIDATES:
        if col in gdf.columns:
            return col
    # Last resort: any column whose normalised name contains 'bp' or 'age'
    for col in gdf.columns:
        lc = col.lower()
        if "bp" in lc or "age" in lc or "year" in lc:
            return col
    return None


def year_from_filename(name: str) -> int | None:
    """Extract the BP year from a filename like 'sealevel_8500bp.shp' or 'coast_8000.shp'."""
    # Prefer patterns like '8500bp', '8500BP'
    m = re.search(r"(\d{3,5})\s*(?:bp|BP)", name)
    if m:
        return int(m.group(1))
    # Fallback: any 3-5 digit number likely representing the year
    m = re.search(r"(\d{3,5})", name)
    if m:
        return int(m.group(1))
    return None


def write_geojson(path: Path, data: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))


# =============================================================================
# Inspection
# =============================================================================


def inspect(zip_paths: list[Path]) -> None:
    """Log shapefile names, attribute schema, and CRS of every shapefile bundled."""
    logger.info(f"Inspecting {len(zip_paths)} zip file(s) in {RAW_DIR}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for zip_path in zip_paths:
            logger.info(f"Zip: {zip_path.name}")
            shps = list_shapefiles_in_zip(zip_path)
            logger.info(f"  Shapefiles: {shps}")
            zip_tmp = tmp_root / zip_path.stem
            zip_tmp.mkdir(exist_ok=True)
            extract_zip(zip_path, zip_tmp)
            for shp_name in shps:
                shp_path = zip_tmp / shp_name
                try:
                    gdf = gpd.read_file(shp_path)
                except Exception as e:
                    logger.error(f"    Failed to read {shp_name}: {e}")
                    continue
                logger.info(
                    f"    {shp_name}: {len(gdf)} features, CRS={gdf.crs}, "
                    f"geom={gdf.geom_type.unique().tolist()}"
                )
                logger.info(f"      columns: {list(gdf.columns)}")
                if len(gdf) > 0:
                    sample = gdf.iloc[0].drop("geometry", errors="ignore").to_dict()
                    logger.info(f"      sample row: {sample}")


# =============================================================================
# Main processing
# =============================================================================


def process_single_shapefile_by_age(shp_path: Path, age_col: str) -> dict[int, dict]:
    """Layout A: one shapefile with an age column — split by year."""
    logger.info(f"  Single-shapefile layout; splitting by column '{age_col}'")
    gdf = read_shapefile(shp_path)
    gdf = simplify_gdf(gdf)

    outputs: dict[int, dict] = {}
    for year in TIME_STEPS_BP:
        subset = gdf[gdf[age_col].astype(int) == year]
        if len(subset) == 0:
            logger.warning(f"    year {year} BP: 0 features")
            continue
        outputs[year] = gdf_to_stripped_geojson(subset)
        logger.info(f"    year {year} BP: {len(subset)} features")
    return outputs


def process_per_slice_shapefiles(zip_paths: list[Path]) -> dict[int, dict]:
    """Layout B: one shapefile per slice — match year from filename."""
    logger.info("  Per-slice shapefile layout; matching year from filenames")
    outputs: dict[int, dict] = {}
    expected = set(TIME_STEPS_BP)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for zip_path in zip_paths:
            zip_tmp = tmp_root / zip_path.stem
            zip_tmp.mkdir(exist_ok=True)
            extract_zip(zip_path, zip_tmp)
            for shp_name in list_shapefiles_in_zip(zip_path):
                year = year_from_filename(Path(shp_name).name)
                if year is None or year not in expected:
                    logger.info(f"    skipping {shp_name} (no matching year)")
                    continue
                shp_path = zip_tmp / shp_name
                try:
                    gdf = read_shapefile(shp_path)
                except Exception as e:
                    logger.error(f"    failed {shp_name}: {e}")
                    continue
                gdf = simplify_gdf(gdf)
                outputs[year] = gdf_to_stripped_geojson(gdf)
                logger.info(f"    {year} BP ← {shp_name}: {len(gdf)} features")
    return outputs


def process(zip_paths: list[Path]) -> dict[int, dict]:
    """Auto-detect layout and produce per-year GeoJSONs."""
    if not zip_paths:
        logger.error(f"No zip files found in {RAW_DIR}")
        logger.error("Download the ADS bundle manually from:")
        logger.error(f"  {SOURCE_META['url']}")
        logger.error(f"and drop the zip file(s) into {RAW_DIR}")
        raise SystemExit(1)

    # Preference: if any zip contains a shapefile with an age column, use layout A
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for zip_path in zip_paths:
            shps = list_shapefiles_in_zip(zip_path)
            if len(shps) == 1:
                zip_tmp = tmp_root / zip_path.stem
                zip_tmp.mkdir(exist_ok=True)
                extract_zip(zip_path, zip_tmp)
                shp_path = zip_tmp / shps[0]
                gdf = gpd.read_file(shp_path)
                age_col = detect_age_column(gdf)
                if age_col is not None:
                    return process_single_shapefile_by_age(shp_path, age_col)

    # Fallback: per-slice layout
    return process_per_slice_shapefiles(zip_paths)


# =============================================================================
# Metadata merge
# =============================================================================


def update_metadata(feature_counts: dict[int, int]) -> None:
    """Merge Sturt 2013 entries into the existing metadata.json (preserves Unpath'd Waters)."""
    if METADATA_PATH.exists():
        with open(METADATA_PATH) as f:
            metadata = json.load(f)
    else:
        metadata = {}

    # Promote legacy flat `source` key to `sources` map (one-time migration).
    if "source" in metadata and "sources" not in metadata:
        legacy = metadata.pop("source")
        metadata["sources"] = {"unpathd_waters": legacy}

    metadata.setdefault("sources", {})
    metadata["sources"]["sturt_2013"] = SOURCE_META

    # Ensure coverage remains valid (don't overwrite) — extend only if clearly missing.
    metadata.setdefault("coverage", {"region": "North Sea & UK"})

    metadata.setdefault("layers", {})

    time_steps_entries = []
    total_features = 0
    for year in TIME_STEPS_BP:
        count = feature_counts.get(year, 0)
        total_features += count
        label = f"{year / 1000:g}ka" if year >= 1000 else f"{year} BP"
        time_steps_entries.append({
            "file": f"sturt_2013_{year}bp",
            "year": year,
            "label": label,
            "featureCount": count,
        })

    metadata["layers"]["sturt2013"] = {
        **LAYER_META,
        "file": f"sturt_2013_{TIME_STEPS_BP[0]}bp",
        "timeSteps": time_steps_entries,
        "featureCount": total_features,
    }

    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata written: {METADATA_PATH}")


# =============================================================================
# CLI
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Sturt 2013 palaeo-coastline shapefiles to per-slice GeoJSON"
    )
    parser.add_argument("--inspect", action="store_true",
                        help="Log schema of each shapefile in data/raw/geological/sturt_2013/ and exit")
    parser.add_argument("--output", type=str,
                        help="Override output directory (default: public/data/geological)")
    args = parser.parse_args()

    global OUTPUT_DIR, METADATA_PATH
    if args.output:
        OUTPUT_DIR = Path(args.output)
        METADATA_PATH = OUTPUT_DIR / "metadata.json"

    zip_paths = find_zip_files(RAW_DIR)

    if args.inspect:
        inspect(zip_paths)
        return

    if not zip_paths:
        logger.error(f"No zip files in {RAW_DIR}. Download from {SOURCE_META['url']} first.")
        raise SystemExit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    outputs = process(zip_paths)
    if not outputs:
        logger.error("No time slices produced. Run with --inspect to debug.")
        raise SystemExit(1)

    feature_counts: dict[int, int] = {}
    for year, geojson in outputs.items():
        out_path = OUTPUT_DIR / f"sturt_2013_{year}bp.geojson"
        write_geojson(out_path, geojson)
        count = len(geojson.get("features", []))
        feature_counts[year] = count
        size_kb = out_path.stat().st_size / 1024
        logger.info(f"  Written {out_path.name}: {count} features, {size_kb:.0f} KB")

    missing = [y for y in TIME_STEPS_BP if y not in outputs]
    if missing:
        logger.warning(f"Missing time slices: {missing}")

    update_metadata(feature_counts)
    logger.info(f"Done: {len(outputs)}/{len(TIME_STEPS_BP)} time slices written.")


if __name__ == "__main__":
    main()
