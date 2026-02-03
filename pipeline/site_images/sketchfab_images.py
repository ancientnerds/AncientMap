"""
Sketchfab 3D model thumbnail matcher for archaeological sites.

Fetches cultural heritage 3D models from Sketchfab and matches them
to sites in the database by name/tags, updating thumbnail_url.

Usage:
    python -m pipeline.site_images.sketchfab_images --limit 10000
    python -m pipeline.site_images.sketchfab_images --stats
"""

import argparse
import re
import time

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.api_config import get_sketchfab_api_key
from pipeline.database import get_session
from pipeline.utils.http import fetch_with_retry

# =============================================================================
# Sketchfab API Configuration
# =============================================================================

API_URL = "https://api.sketchfab.com/v3"
SEARCH_URL = f"{API_URL}/search"

# Search queries for archaeological content
SEARCH_QUERIES = [
    "pompeii",
    "petra jordan",
    "colosseum rome",
    "parthenon",
    "stonehenge",
    "roman forum",
    "acropolis",
    "machu picchu",
    "teotihuacan",
    "angkor wat",
    "palmyra",
    "ephesus",
    "delphi",
    "mycenae",
    "knossos",
    "archaeological site",
    "ancient ruins",
    "roman temple",
    "greek temple",
    "egyptian temple",
    "ancient monument",
    "bronze age",
    "iron age",
    "neolithic site",
    "megalithic monument",
    "ancient artifact scan",
    "archaeology 3d scan",
    "photogrammetry ruins",
    "cultural heritage 3d",
    "museum artifact scan",
    "ancient sculpture scan",
    "roman villa",
    "hadrians wall",
    "leptis magna",
    "baalbek",
    "persepolis",
    "troy archaeology",
    "ancient greece",
    "ancient rome",
    "ancient egypt",
    "mayan ruins",
    "aztec temple",
    "inca ruins",
]

# Cultural heritage accounts with good content
HERITAGE_USERS = [
    "britishmuseum",
    "smikimamuseum",
    "cyark",
    "openheritage",
    "globaldigitalheritage",
    "threeDscans",
    "africanfossils",
]

PAGE_SIZE = 24
MAX_RESULTS_PER_QUERY = 200
REQUEST_DELAY = 0.5


# =============================================================================
# Name Matching Utilities
# =============================================================================

def normalize_name(name: str) -> str:
    """Normalize a name for matching."""
    if not name:
        return ""
    # Lowercase
    name = name.lower()
    # Remove common suffixes
    name = re.sub(r'\s*(3d\s*scan|photogrammetry|model|3d|scan)\s*$', '', name, flags=re.IGNORECASE)
    # Remove special characters
    name = re.sub(r'[^\w\s]', ' ', name)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name


def extract_location_names(text: str) -> set[str]:
    """Extract potential location names from text."""
    names = set()
    if not text:
        return names

    # Split by common separators
    parts = re.split(r'[,\-/|()]', text)
    for part in parts:
        part = part.strip()
        if part and len(part) > 3:
            names.add(normalize_name(part))

    # Also add the full normalized text
    full = normalize_name(text)
    if full:
        names.add(full)

    return names


def calculate_match_score(model: dict, site_name: str, site_alt_names: list[str] = None) -> float:
    """
    Calculate how well a model matches a site.

    Returns score 0-100, higher is better.
    """
    score = 0.0

    site_name_norm = normalize_name(site_name)
    if not site_name_norm:
        return 0.0

    # Check model name
    model_name = normalize_name(model.get("name", ""))

    # Exact match
    if site_name_norm == model_name:
        score += 100
    # Site name contained in model name
    elif site_name_norm in model_name:
        score += 80
    # Model name contained in site name
    elif model_name in site_name_norm:
        score += 70
    # Word overlap
    else:
        site_words = set(site_name_norm.split())
        model_words = set(model_name.split())
        overlap = site_words & model_words
        if overlap:
            score += len(overlap) * 20

    # Check tags
    tags = [normalize_name(t) for t in model.get("tags", [])]
    for tag in tags:
        if site_name_norm in tag or tag in site_name_norm:
            score += 30
            break

    # Check alternative names
    if site_alt_names:
        for alt_name in site_alt_names:
            alt_norm = normalize_name(alt_name)
            if alt_norm and alt_norm in model_name:
                score += 40
                break

    # Bonus for verified/staff-pick
    if model.get("is_staffpick"):
        score += 10

    # Bonus for likes
    likes = model.get("like_count", 0)
    if likes > 100:
        score += 5

    return score


# =============================================================================
# Sketchfab API Functions
# =============================================================================

def fetch_models_for_query(query: str, api_key: str = None, max_results: int = MAX_RESULTS_PER_QUERY) -> list[dict]:
    """Fetch 3D models matching a search query."""
    models = []

    headers = {
        "Accept": "application/json",
        "User-Agent": "AncientMap/1.0 (Archaeological Research Platform)",
    }

    if api_key:
        headers["Authorization"] = f"Token {api_key}"

    cursor = None

    while len(models) < max_results:
        try:
            params = {
                "type": "models",
                "q": query,
                "downloadable": "false",
                "sort_by": "-likeCount",
            }

            if cursor:
                params["cursor"] = cursor

            response = fetch_with_retry(
                SEARCH_URL,
                params=params,
                headers=headers,
                timeout=30,
            )

            if response.status_code != 200:
                break

            data = response.json()
            results = data.get("results", [])

            if not results:
                break

            for item in results:
                model = parse_model(item)
                if model:
                    models.append(model)

            cursor = data.get("cursors", {}).get("next")
            if not cursor:
                break

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            logger.debug(f"Error fetching '{query}': {e}")
            break

    return models


def fetch_user_models(username: str, api_key: str = None) -> list[dict]:
    """Fetch all models from a specific user."""
    models = []

    headers = {
        "Accept": "application/json",
        "User-Agent": "AncientMap/1.0 (Archaeological Research Platform)",
    }

    if api_key:
        headers["Authorization"] = f"Token {api_key}"

    cursor = None

    while True:
        try:
            params = {
                "type": "models",
                "user": username,
                "sort_by": "-likeCount",
            }

            if cursor:
                params["cursor"] = cursor

            response = fetch_with_retry(
                SEARCH_URL,
                params=params,
                headers=headers,
                timeout=30,
            )

            if response.status_code != 200:
                break

            data = response.json()
            results = data.get("results", [])

            if not results:
                break

            for item in results:
                model = parse_model(item)
                if model:
                    models.append(model)

            cursor = data.get("cursors", {}).get("next")
            if not cursor:
                break

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            logger.debug(f"Error fetching user '{username}': {e}")
            break

    return models


def parse_model(item: dict) -> dict | None:
    """Parse a Sketchfab API model response."""
    if not item:
        return None

    model_id = item.get("uid", "")
    if not model_id:
        return None

    # Get best thumbnail
    thumbnails = item.get("thumbnails", {}).get("images", [])
    thumbnail_url = ""
    if thumbnails:
        # Prefer medium-sized thumbnails (not too big, not too small)
        sorted_thumbs = sorted(thumbnails, key=lambda x: abs(x.get("width", 0) - 640))
        thumbnail_url = sorted_thumbs[0].get("url", "") if sorted_thumbs else ""

    user = item.get("user", {})

    return {
        "uid": model_id,
        "name": item.get("name", ""),
        "description": (item.get("description") or "")[:500],
        "creator": user.get("displayName", user.get("username", "")),
        "like_count": item.get("likeCount", 0),
        "view_count": item.get("viewCount", 0),
        "is_downloadable": item.get("isDownloadable", False),
        "is_staffpick": item.get("staffpickedAt") is not None,
        "tags": [t.get("name", "") for t in item.get("tags", [])],
        "thumbnail_url": thumbnail_url,
        "embed_url": f"https://sketchfab.com/models/{model_id}/embed",
        "viewer_url": f"https://sketchfab.com/3d-models/{model_id}",
    }


# =============================================================================
# Database Functions
# =============================================================================

def get_sites_without_images(session: Session, limit: int = None) -> list[dict]:
    """Get sites that don't have thumbnail images yet."""
    query = """
        SELECT id, name, source_id, site_type
        FROM unified_sites
        WHERE thumbnail_url IS NULL
        ORDER BY
            CASE
                WHEN site_type IN ('temple', 'monument', 'fortress', 'palace') THEN 0
                WHEN site_type IN ('settlement', 'city', 'town') THEN 1
                ELSE 2
            END,
            RANDOM()
    """

    if limit:
        query += f" LIMIT {limit}"

    result = session.execute(text(query))

    sites = []
    for row in result.fetchall():
        sites.append({
            "id": str(row[0]),
            "name": row[1],
            "source_id": row[2],
            "site_type": row[3],
        })

    return sites


def update_site_thumbnail(session: Session, site_id: str, thumbnail_url: str, sketchfab_uid: str) -> bool:
    """Update a site's thumbnail URL."""
    try:
        session.execute(text("""
            UPDATE unified_sites
            SET thumbnail_url = :url,
                raw_data = COALESCE(raw_data, '{}'::jsonb) || jsonb_build_object('sketchfab_model', :uid)
            WHERE id = :site_id
        """), {
            "url": thumbnail_url,
            "site_id": site_id,
            "uid": sketchfab_uid,
        })
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating site {site_id}: {e}")
        session.rollback()
        return False


def get_stats(session: Session) -> dict:
    """Get Sketchfab image statistics."""
    result = session.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN thumbnail_url LIKE '%sketchfab%' THEN 1 END) as sketchfab_images,
            COUNT(thumbnail_url) as any_image
        FROM unified_sites
    """)).fetchone()

    return {
        "total_sites": result[0],
        "sketchfab_images": result[1],
        "any_image": result[2],
    }


# =============================================================================
# Main Matching Logic
# =============================================================================

def match_sketchfab_to_sites(limit: int = 10000, min_score: float = 50.0) -> dict:
    """
    Fetch Sketchfab models and match them to database sites.

    Returns statistics about the matching process.
    """
    api_key = get_sketchfab_api_key()
    if api_key:
        logger.info("Using Sketchfab API key")
    else:
        logger.warning("No Sketchfab API key - using unauthenticated access (rate limited)")

    logger.info("=" * 60)
    logger.info("SKETCHFAB 3D MODEL THUMBNAIL MATCHER")
    logger.info("=" * 60)

    # Fetch all cultural heritage models
    all_models = {}  # uid -> model dict

    # Search by queries
    logger.info(f"Searching {len(SEARCH_QUERIES)} queries...")
    for i, query in enumerate(SEARCH_QUERIES):
        logger.info(f"  [{i+1}/{len(SEARCH_QUERIES)}] '{query}'...")
        models = fetch_models_for_query(query, api_key)
        for m in models:
            all_models[m["uid"]] = m
        logger.info(f"    Found {len(models)} (total unique: {len(all_models)})")

    # Fetch from heritage accounts
    logger.info(f"Fetching from {len(HERITAGE_USERS)} heritage accounts...")
    for username in HERITAGE_USERS:
        logger.info(f"  Fetching @{username}...")
        models = fetch_user_models(username, api_key)
        for m in models:
            all_models[m["uid"]] = m
        logger.info(f"    Found {len(models)} (total unique: {len(all_models)})")

    logger.info(f"Total unique 3D models: {len(all_models):,}")

    # Build index for fast matching
    model_list = list(all_models.values())

    # Get sites to match
    with get_session() as session:
        sites = get_sites_without_images(session, limit)
        logger.info(f"Sites without images: {len(sites):,}")

        matched = 0
        processed = 0

        for site in sites:
            processed += 1

            if processed % 1000 == 0:
                logger.info(f"Progress: {processed:,}/{len(sites):,} | Matched: {matched:,}")

            # Find best matching model
            best_model = None
            best_score = 0

            for model in model_list:
                score = calculate_match_score(
                    model,
                    site["name"],
                    None  # No alternative names in DB schema
                )

                if score > best_score:
                    best_score = score
                    best_model = model

            # Only accept good matches
            if best_model and best_score >= min_score and best_model.get("thumbnail_url"):
                success = update_site_thumbnail(
                    session,
                    site["id"],
                    best_model["thumbnail_url"],
                    best_model["uid"]
                )

                if success:
                    matched += 1
                    if matched <= 10:
                        logger.info(f"  Matched: {site['name']} -> {best_model['name']} (score: {best_score:.0f})")

        stats = get_stats(session)

    logger.info("=" * 60)
    logger.info("MATCHING COMPLETE")
    logger.info(f"  Processed: {processed:,}")
    logger.info(f"  Matched: {matched:,}")
    logger.info(f"  Total Sketchfab images: {stats['sketchfab_images']:,}")
    logger.info("=" * 60)

    return {
        "models_fetched": len(all_models),
        "sites_processed": processed,
        "matched": matched,
        "sketchfab_images_total": stats["sketchfab_images"],
    }


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Match Sketchfab 3D models to archaeological sites"
    )
    parser.add_argument(
        "--limit", "-l", type=int, default=10000,
        help="Maximum sites to process (default: 10000)"
    )
    parser.add_argument(
        "--min-score", type=float, default=50.0,
        help="Minimum match score (default: 50)"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show statistics only"
    )

    args = parser.parse_args()

    # Setup logging
    from pipeline.utils.logging import setup_logging
    setup_logging()

    if args.stats:
        with get_session() as session:
            stats = get_stats(session)
            print("\n" + "=" * 50)
            print("SKETCHFAB IMAGE STATISTICS")
            print("=" * 50)
            print(f"  Total sites:        {stats['total_sites']:>10,}")
            print(f"  With any image:     {stats['any_image']:>10,}")
            print(f"  Sketchfab images:   {stats['sketchfab_images']:>10,}")
            print("=" * 50 + "\n")
        return

    match_sketchfab_to_sites(limit=args.limit, min_score=args.min_score)


if __name__ == "__main__":
    main()
