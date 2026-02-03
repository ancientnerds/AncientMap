"""
Sketchfab Cultural Heritage 3D models ingester.

Sketchfab hosts 50,000+ cultural heritage 3D models from
museums, archaeologists, and heritage organizations worldwide.

Data source: https://sketchfab.com/
API Docs: https://docs.sketchfab.com/data-api/v3/
License: Varies per model (CC licenses common)
API Key: Required for full access
"""

import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from loguru import logger

from pipeline.ingesters.base import BaseIngester, ParsedSite, atomic_write_json
from pipeline.utils.http import fetch_with_retry


class SketchfabIngester(BaseIngester):
    """
    Ingester for Sketchfab cultural heritage 3D models.

    Uses the Sketchfab Data API to search for archaeological
    and cultural heritage models.
    """

    source_id = "models_sketchfab"
    source_name = "Sketchfab Cultural Heritage"

    # Sketchfab API endpoint
    API_URL = "https://api.sketchfab.com/v3"
    SEARCH_URL = f"{API_URL}/search"

    # Search queries for cultural heritage content
    SEARCH_QUERIES = [
        "archaeological site",
        "ancient artifact",
        "roman sculpture",
        "greek sculpture",
        "egyptian artifact",
        "archaeological find",
        "museum artifact",
        "ancient temple",
        "medieval castle",
        "prehistoric",
        "neolithic",
        "bronze age",
        "iron age",
        "viking",
        "maya ruins",
        "aztec",
        "inca",
        "petra",
        "pompeii",
        "archaeology 3d scan",
        "photogrammetry archaeology",
        "cultural heritage",
        "ancient pottery",
        "cuneiform tablet",
        "hieroglyphics",
        "sarcophagus",
        "amphora",
    ]

    # Known cultural heritage collections on Sketchfab
    COLLECTIONS = [
        "british-museum",  # British Museum
        "smikimamuseum",  # Smithsonian
        "mfranceart",  # Museums of France
        "afrh",  # African History
        "openheritage",  # Open Heritage
        "cyark",  # CyArk
        "sketchfab-archives",
    ]

    PAGE_SIZE = 24  # Sketchfab API default
    MAX_RESULTS_PER_QUERY = 500
    REQUEST_DELAY = 0.5

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from pipeline.api_config import get_sketchfab_api_key
        self.api_key = get_sketchfab_api_key()

    def fetch(self) -> Path:
        """
        Fetch 3D model metadata from Sketchfab.

        Returns:
            Path to JSON file with model metadata
        """
        dest_path = self.raw_data_dir / "models_sketchfab.json"

        logger.info("Fetching Sketchfab 3D model metadata...")
        self.report_progress(0, None, "starting...")

        all_models = []
        seen_ids = set()

        headers = {
            "Accept": "application/json",
            "User-Agent": "AncientNerds/1.0 (Research Platform)",
        }

        # Add API key if available
        if self.api_key:
            headers["Authorization"] = f"Token {self.api_key}"

        # Search by queries
        for i, query in enumerate(self.SEARCH_QUERIES):
            self.report_progress(i, len(self.SEARCH_QUERIES), f"'{query}'")

            cursor = None
            query_count = 0

            while query_count < self.MAX_RESULTS_PER_QUERY:
                try:
                    params = {
                        "type": "models",
                        "q": query,
                        "downloadable": "false",  # Include all models
                        "sort_by": "-likeCount",  # Most liked first
                    }

                    if cursor:
                        params["cursor"] = cursor

                    response = fetch_with_retry(
                        self.SEARCH_URL,
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
                        model = self._parse_model(item)
                        if model and model["id"] not in seen_ids:
                            seen_ids.add(model["id"])
                            all_models.append(model)
                            query_count += 1

                    # Get next page cursor
                    cursor = data.get("cursors", {}).get("next")
                    if not cursor:
                        break

                    time.sleep(self.REQUEST_DELAY)

                except Exception as e:
                    logger.debug(f"Search error for '{query}': {e}")
                    break

            if query_count > 0:
                logger.info(f"  '{query}': {query_count} models (total: {len(all_models)})")

        # Fetch from known cultural heritage collections
        logger.info("Fetching from cultural heritage collections...")
        for username in self.COLLECTIONS:
            try:
                params = {
                    "type": "models",
                    "user": username,
                    "sort_by": "-likeCount",
                }

                response = fetch_with_retry(
                    self.SEARCH_URL,
                    params=params,
                    headers=headers,
                    timeout=30,
                )

                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])

                    collection_count = 0
                    for item in results:
                        model = self._parse_model(item)
                        if model and model["id"] not in seen_ids:
                            seen_ids.add(model["id"])
                            all_models.append(model)
                            collection_count += 1

                    if collection_count > 0:
                        logger.info(f"  Collection '{username}': {collection_count} models")

                time.sleep(self.REQUEST_DELAY)

            except Exception as e:
                logger.debug(f"Collection fetch error for '{username}': {e}")

        logger.info(f"Total 3D models: {len(all_models):,}")
        self.report_progress(len(all_models), len(all_models), f"{len(all_models):,} models")

        # Save to file
        output = {
            "models": all_models,
            "metadata": {
                "source": "Sketchfab",
                "source_url": "https://sketchfab.com/",
                "api_docs": "https://docs.sketchfab.com/data-api/v3/",
                "fetched_at": datetime.utcnow().isoformat(),
                "total_models": len(all_models),
                "data_type": "3d_models",
                "license": "Varies per model",
                "note": "Models require Sketchfab embed or download for viewing",
            }
        }

        atomic_write_json(dest_path, output)

        logger.info(f"Saved {len(all_models):,} models to {dest_path}")
        return dest_path

    def _parse_model(self, item: dict) -> dict | None:
        """Parse a Sketchfab model."""
        if not item:
            return None

        model_id = item.get("uid", "")
        if not model_id:
            return None

        # Get thumbnails
        thumbnails = item.get("thumbnails", {}).get("images", [])
        thumbnail_url = ""
        if thumbnails:
            # Get largest thumbnail
            thumbnails_sorted = sorted(thumbnails, key=lambda x: x.get("width", 0), reverse=True)
            thumbnail_url = thumbnails_sorted[0].get("url", "") if thumbnails_sorted else ""

        # Get user info
        user = item.get("user", {})

        return {
            "id": f"sketchfab_{model_id}",
            "sketchfab_uid": model_id,
            "name": item.get("name", ""),
            "description": item.get("description", "")[:500] if item.get("description") else "",
            "creator": user.get("displayName", user.get("username", "")),
            "creator_url": user.get("profileUrl", ""),
            "created_at": item.get("createdAt", ""),
            "published_at": item.get("publishedAt", ""),
            "view_count": item.get("viewCount", 0),
            "like_count": item.get("likeCount", 0),
            "comment_count": item.get("commentCount", 0),
            "is_downloadable": item.get("isDownloadable", False),
            "license": item.get("license", {}).get("label", ""),
            "license_url": item.get("license", {}).get("url", ""),
            "vertex_count": item.get("vertexCount", 0),
            "face_count": item.get("faceCount", 0),
            "animation_count": item.get("animationCount", 0),
            "tags": [t.get("name", "") for t in item.get("tags", [])],
            "categories": [c.get("name", "") for c in item.get("categories", [])],
            "thumbnail_url": thumbnail_url,
            "embed_url": f"https://sketchfab.com/models/{model_id}/embed",
            "viewer_url": f"https://sketchfab.com/3d-models/{model_id}",
            "source_url": item.get("viewerUrl", f"https://sketchfab.com/3d-models/{model_id}"),
        }

    def parse(self, raw_data_path: Path) -> Iterator[ParsedSite]:
        """Parse Sketchfab data - 3D models don't have geographic coordinates."""
        logger.info(f"Parsing Sketchfab data from {raw_data_path}")

        # 3D models typically don't have coordinates
        # Return empty iterator - these link to sites by name/tag matching
        return iter([])


def ingest_sketchfab(session=None, skip_fetch: bool = False) -> dict:
    """Run Sketchfab ingestion."""
    with SketchfabIngester(session=session) as ingester:
        result = ingester.run(skip_fetch=skip_fetch)
        return {
            "source": result.source_id,
            "success": result.success,
            "saved": result.records_saved,
            "failed": result.records_failed,
        }
