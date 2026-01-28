"""
Generate labels.json from Natural Earth data.

Downloads and processes:
- Populated places (cities, capitals) - with country linking
- Countries (admin_0) - ranked by area
- Geography (oceans, seas)
- Physical features (mountains, deserts) - ranked by scalerank

Natural Earth data: https://www.naturalearthdata.com/
"""

import json
import zipfile
import io
from pathlib import Path
import urllib.request

# Output path
OUTPUT_PATH = Path(__file__).parent.parent / "ancient-nerds-map" / "public" / "data" / "labels.json"

# Natural Earth data URLs (10m resolution for best coverage)
URLS = {
    "populated_places": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places.zip",
    "countries": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
    "oceans": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_geography_marine_polys.zip",
    "physical": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_geography_regions_polys.zip",
}

# Area thresholds for country ranking (in km²)
COUNTRY_AREA_THRESHOLDS = [
    (3_000_000, 1),   # Russia, Canada, USA, China, Brazil
    (1_000_000, 2),   # India, Argentina, Kazakhstan
    (300_000, 3),     # France, Spain, Germany
    (50_000, 4),      # Greece, Portugal, Netherlands
    (0, 5),           # Luxembourg, Monaco, Vatican
]

# Population thresholds for city ranking
CITY_POP_THRESHOLDS = [
    (10_000_000, 1),  # Tokyo, Delhi, Shanghai
    (5_000_000, 2),   # Singapore, Madrid, Toronto
    (1_000_000, 3),   # Prague, Dublin, Auckland
    (500_000, 4),     # Edinburgh, Nice, Zurich
    (0, 5),           # Smaller cities
]


def get_english_name(row) -> str:
    """Get English name, falling back to ASCII then native."""
    return (
        row.get("NAME_EN") or
        row.get("name_en") or
        row.get("NAMEASCII") or
        row.get("nameascii") or
        row.get("NAME") or
        row.get("name") or
        ""
    ).strip()


def download_and_extract_geojson(url: str, name: str):
    """Download a Natural Earth zip and extract the shapefile as GeoJSON."""
    print(f"Downloading {name}...")

    try:
        import geopandas as gpd
    except ImportError:
        print("Installing geopandas...")
        import subprocess
        subprocess.check_call(["pip", "install", "geopandas"])
        import geopandas as gpd

    # Download zip file
    with urllib.request.urlopen(url) as response:
        zip_data = io.BytesIO(response.read())

    # Extract to temp directory
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_data) as z:
            z.extractall(tmpdir)

        # Find the .shp file
        shp_files = list(Path(tmpdir).glob("*.shp"))
        if not shp_files:
            raise ValueError(f"No .shp file found in {name}")

        # Read with geopandas
        gdf = gpd.read_file(shp_files[0])
        return gdf


def get_rank_by_area(area_km2: float) -> int:
    """Get rank based on area in km²."""
    for threshold, rank in COUNTRY_AREA_THRESHOLDS:
        if area_km2 >= threshold:
            return rank
    return 5


def get_rank_by_population(pop: int) -> int:
    """Get rank based on population."""
    for threshold, rank in CITY_POP_THRESHOLDS:
        if pop >= threshold:
            return rank
    return 5


def process_countries(gdf) -> tuple[list, dict]:
    """
    Process countries into label format.
    Returns (labels, country_name_map) where country_name_map maps country names to their data.
    The map includes alternate names (ADMIN, ADM0_A3, etc.) as aliases to handle Natural Earth naming differences.
    """
    labels = []
    country_map = {}  # name -> {lat, lng, rank, primary_name} for capital linking

    for _, row in gdf.iterrows():
        name = get_english_name(row)
        if not name:
            continue

        geom = row.geometry
        if geom is None:
            continue

        # Use LABEL_X and LABEL_Y if available (Natural Earth provides these for optimal label placement)
        label_x = row.get("LABEL_X")
        label_y = row.get("LABEL_Y")

        if label_x is not None and label_y is not None:
            lng = float(label_x)
            lat = float(label_y)
        else:
            # Fallback to geometry centroid
            lng = geom.centroid.x
            lat = geom.centroid.y

        # Calculate area in km² from geometry
        # Natural Earth uses WGS84, so we need to project to equal-area for accurate area
        try:
            # Project to Equal Earth (EPSG:8857) for area calculation
            import pyproj
            from shapely.ops import transform

            project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:8857", always_xy=True).transform
            projected_geom = transform(project, geom)
            area_km2 = projected_geom.area / 1_000_000  # m² to km²
        except:
            # Fallback: use rough approximation based on bounds
            bounds = geom.bounds
            lat_span = bounds[3] - bounds[1]
            lng_span = bounds[2] - bounds[0]
            # Very rough approximation
            area_km2 = lat_span * lng_span * 111 * 111 * 0.5  # Rough km² estimate

        # Determine rank by area
        rank = get_rank_by_area(area_km2)

        label = {
            "name": name,
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "type": "country",
            "rank": rank,
        }
        labels.append(label)

        # Store in map for capital linking - include the primary display name
        country_data = {"lat": lat, "lng": lng, "rank": rank, "primary_name": name}

        # Store under multiple names to handle Natural Earth naming differences
        # Primary name (NAME_EN)
        country_map[name] = country_data

        # ADMIN field (used by populated places ADM0NAME) - e.g., "China" vs "People's Republic of China"
        admin = row.get("ADMIN") or row.get("admin")
        if admin:
            admin = str(admin).strip()
            if admin and admin != name:
                country_map[admin] = country_data

        # NAME field (sometimes different from NAME_EN)
        native_name = row.get("NAME") or row.get("name")
        if native_name:
            native_name = str(native_name).strip()
            if native_name and native_name != name:
                country_map[native_name] = country_data

        # SOVEREIGNT field (sovereign nation name)
        sov = row.get("SOVEREIGNT") or row.get("sovereignt")
        if sov:
            sov = str(sov).strip()
            if sov and sov != name:
                country_map[sov] = country_data

    return labels, country_map


def process_populated_places(gdf, country_map: dict) -> list:
    """
    Process populated places into label format.
    Links capitals to their parent country.
    """
    labels = []

    for _, row in gdf.iterrows():
        name = get_english_name(row)
        if not name:
            continue

        # Get coordinates from geometry centroid
        geom = row.geometry
        if geom is None:
            continue

        lng = geom.x if hasattr(geom, 'x') else geom.centroid.x
        lat = geom.y if hasattr(geom, 'y') else geom.centroid.y

        # Determine type based on FEATURECLA field
        feature_class = str(row.get("FEATURECLA", "")).lower()

        # Check if it's a capital
        is_capital = False
        adm0cap = row.get("ADM0CAP", 0)
        if adm0cap == 1 or "capital" in feature_class:
            is_capital = True

        # Get population for ranking
        pop = row.get("POP_MAX") or row.get("POP_MIN") or 0
        try:
            pop = int(pop) if pop else 0
        except:
            pop = 0

        # Get parent country name for capitals
        country_name = None
        country_display_name = None  # The name used in country labels for proper linking
        if is_capital:
            # For national capitals (ADM0CAP=1), prefer SOV0NAME as it's more reliable
            # Natural Earth's ADM0NAME sometimes has incorrect values (e.g., Canberra -> "Ashmore and Cartier Islands")
            sov0name = row.get("SOV0NAME") or row.get("sov0name")
            adm0name = row.get("ADM0NAME") or row.get("adm0name")

            if adm0cap == 1:
                # National capital - use sovereign country name
                country_name = sov0name or adm0name
            else:
                # State/province capital - use admin name
                country_name = adm0name or sov0name

            if country_name:
                country_name = str(country_name).strip()
                # Look up the primary display name from country_map
                if country_name in country_map:
                    country_display_name = country_map[country_name].get("primary_name", country_name)
                else:
                    country_display_name = country_name

        # Determine rank
        if is_capital:
            label_type = "capital"
            # ONLY national capitals (ADM0CAP=1) inherit country rank
            # Regional/state capitals should be ranked by population
            if adm0cap == 1 and country_name and country_name in country_map:
                # National capital - inherit country rank
                rank = country_map[country_name]["rank"]
            else:
                # State/regional capital or unknown - rank by population
                rank = get_rank_by_population(pop)
        else:
            label_type = "city"
            rank = get_rank_by_population(pop)

        label = {
            "name": name,
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "type": label_type,
            "rank": rank,
        }

        # Add country link for capitals - use the display name for proper linking
        if is_capital and country_display_name:
            label["country"] = country_display_name
            # Mark national capitals (for special handling in frontend)
            if adm0cap == 1:
                label["national"] = True

        # Store population for later filtering
        label["pop"] = pop

        labels.append(label)

    return labels


def process_marine(gdf) -> list:
    """Process oceans and seas."""
    labels = []

    for _, row in gdf.iterrows():
        name = get_english_name(row)
        if not name:
            continue

        geom = row.geometry
        if geom is None:
            continue

        # Use centroid for polygon features
        centroid = geom.centroid
        lng = centroid.x
        lat = centroid.y

        # Determine if ocean or sea based on name/type
        feature_class = str(row.get("featurecla", "") or row.get("FEATURECLA", "")).lower()

        # Use scalerank if available for seas, oceans always rank 1
        scalerank = row.get("scalerank", 0) or row.get("SCALERANK", 0)
        try:
            scalerank = int(scalerank)
        except:
            scalerank = 0

        if "ocean" in name.lower() or "ocean" in feature_class:
            label_type = "ocean"
            rank = 1  # Oceans always highest priority
        elif "sea" in name.lower() or "gulf" in name.lower() or "bay" in name.lower():
            label_type = "sea"
            # Better scalerank mapping: 0-1 -> rank 1, 2-3 -> rank 2, etc.
            rank = min(5, max(1, (scalerank // 2) + 1))
        else:
            label_type = "sea"
            rank = min(5, max(2, (scalerank // 2) + 1))

        labels.append({
            "name": name,
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "type": label_type,
            "rank": rank
        })

    return labels


def process_physical_geography(gdf) -> list:
    """
    Process mountains, deserts, plateaus from physical geography polygons.
    Uses scalerank for importance ranking.
    """
    labels = []

    for _, row in gdf.iterrows():
        name = get_english_name(row)
        if not name:
            continue

        geom = row.geometry
        if geom is None:
            continue

        # Use centroid for polygon features
        centroid = geom.centroid
        lng = centroid.x
        lat = centroid.y

        feature_class = str(row.get("FEATURECLA", "") or row.get("featurecla", "")).lower()

        # Use scalerank for importance (0-10, lower = more important)
        scalerank = row.get("scalerank") or row.get("SCALERANK")
        try:
            scalerank = int(scalerank) if scalerank is not None else 5
        except:
            scalerank = 5  # Default to middle importance

        # Better scalerank to rank mapping:
        # scalerank 0-1 -> rank 1 (Himalayas, Andes, Sahara)
        # scalerank 2-3 -> rank 2 (Alps, Gobi)
        # scalerank 4-5 -> rank 3
        # scalerank 6-7 -> rank 4
        # scalerank 8+ -> rank 5
        if scalerank <= 1:
            rank = 1
        elif scalerank <= 3:
            rank = 2
        elif scalerank <= 5:
            rank = 3
        elif scalerank <= 7:
            rank = 4
        else:
            rank = 5

        # Filter for mountain-related and desert features
        # Natural Earth uses 'range/mtn' for mountain ranges
        if 'range' in feature_class or 'mtn' in feature_class:
            label_type = "mountain"
        elif 'plateau' in feature_class:
            label_type = "mountain"  # Group plateaus with mountains
        elif 'desert' in feature_class:
            label_type = "desert"
        else:
            continue  # Skip other physical features (islands, capes, etc.)

        labels.append({
            "name": name,
            "lat": round(lat, 4),
            "lng": round(lng, 4),
            "type": label_type,
            "rank": rank
        })

    return labels


def add_continents() -> list:
    """Add continent labels manually (Natural Earth doesn't have good continent label points)."""
    return [
        {"name": "Africa", "lat": 2, "lng": 20, "type": "continent", "rank": 1},
        {"name": "Antarctica", "lat": -82, "lng": 0, "type": "continent", "rank": 1},
        {"name": "Asia", "lat": 45, "lng": 90, "type": "continent", "rank": 1},
        {"name": "Australia", "lat": -25, "lng": 135, "type": "continent", "rank": 1},
        {"name": "Europe", "lat": 54, "lng": 15, "type": "continent", "rank": 1},
        {"name": "North America", "lat": 45, "lng": -100, "type": "continent", "rank": 1},
        {"name": "South America", "lat": -15, "lng": -60, "type": "continent", "rank": 1},
    ]


def main():
    all_labels = []
    country_map = {}

    # Add continents (manual)
    print("Adding continents...")
    all_labels.extend(add_continents())

    # Download and process each dataset
    try:
        # Countries - process first to build country map for capital linking
        countries_gdf = download_and_extract_geojson(URLS["countries"], "countries")
        country_labels, country_map = process_countries(countries_gdf)
        print(f"  Found {len(country_labels)} countries")

        # Print rank distribution
        rank_counts = {}
        for label in country_labels:
            r = label["rank"]
            rank_counts[r] = rank_counts.get(r, 0) + 1
        print(f"  Country ranks: {rank_counts}")

        all_labels.extend(country_labels)
    except Exception as e:
        print(f"  Error processing countries: {e}")
        import traceback
        traceback.print_exc()

    try:
        # Populated places (cities, capitals) - with country linking
        places_gdf = download_and_extract_geojson(URLS["populated_places"], "populated places")
        place_labels = process_populated_places(places_gdf, country_map)
        print(f"  Found {len(place_labels)} populated places")

        # Count capitals with country links
        linked_capitals = sum(1 for l in place_labels if l.get("country"))
        print(f"  Capitals linked to countries: {linked_capitals}")

        all_labels.extend(place_labels)
    except Exception as e:
        print(f"  Error processing populated places: {e}")
        import traceback
        traceback.print_exc()

    try:
        # Oceans and seas
        marine_gdf = download_and_extract_geojson(URLS["oceans"], "marine features")
        marine_labels = process_marine(marine_gdf)
        print(f"  Found {len(marine_labels)} marine features")
        all_labels.extend(marine_labels)
    except Exception as e:
        print(f"  Error processing marine features: {e}")

    try:
        # Physical geography (mountains, deserts, etc.)
        physical_gdf = download_and_extract_geojson(URLS["physical"], "physical geography")
        physical_labels = process_physical_geography(physical_gdf)
        print(f"  Found {len(physical_labels)} physical features (mountains, deserts)")

        # Print rank distribution
        rank_counts = {}
        for label in physical_labels:
            r = label["rank"]
            rank_counts[r] = rank_counts.get(r, 0) + 1
        print(f"  Physical feature ranks: {rank_counts}")

        all_labels.extend(physical_labels)
    except Exception as e:
        print(f"  Error processing physical geography: {e}")

    # Remove duplicates (same name + similar coordinates)
    seen = set()
    unique_labels = []
    for label in all_labels:
        key = (label["name"], round(label["lat"]), round(label["lng"]))
        if key not in seen:
            seen.add(key)
            unique_labels.append(label)

    # Sort by type priority, then rank, then name
    type_priority = {"continent": 0, "ocean": 1, "country": 2, "capital": 3, "mountain": 4, "sea": 5, "desert": 6, "city": 7}
    unique_labels.sort(key=lambda x: (type_priority.get(x["type"], 99), x["rank"], x["name"]))

    # Remove pop field (was only for internal use)
    for label in unique_labels:
        if "pop" in label:
            del label["pop"]

    print(f"\nTotal labels: {len(unique_labels)}")

    # Count by type
    by_type = {}
    for label in unique_labels:
        t = label["type"]
        by_type[t] = by_type.get(t, 0) + 1
    print("By type:", by_type)

    # Count by type and rank
    print("\nRank distribution:")
    for t in ["country", "capital", "mountain", "desert", "sea", "city"]:
        type_labels = [l for l in unique_labels if l["type"] == t]
        rank_dist = {}
        for l in type_labels:
            r = l["rank"]
            rank_dist[r] = rank_dist.get(r, 0) + 1
        if rank_dist:
            print(f"  {t}: {dict(sorted(rank_dist.items()))}")

    # NOTE: No collision detection - Globe.tsx handles visibility based on zoom level
    # This keeps all labels available for the frontend to filter dynamically

    # Write output with wrapper object
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {"labels": unique_labels}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nWritten to: {OUTPUT_PATH}")

    # Print some examples
    print("\nExample labels:")
    for t in ["country", "capital", "mountain", "desert"]:
        examples = [l for l in unique_labels if l["type"] == t][:3]
        print(f"  {t}:")
        for ex in examples:
            country_link = f" (country: {ex['country']})" if ex.get('country') else ""
            print(f"    - {ex['name']} (rank {ex['rank']}){country_link}")


if __name__ == "__main__":
    main()
