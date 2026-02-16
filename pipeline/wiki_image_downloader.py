"""
Wiki Image Downloader for Ancient Nerds Map.

Downloads Wikipedia/Wikimedia Commons images for own curated sites,
stores them locally, and populates the wiki_images table with attribution.

Usage:
    python -m pipeline.wiki_image_downloader                             # all own sources
    python -m pipeline.wiki_image_downloader --source ancient_nerds      # specific source
    python -m pipeline.wiki_image_downloader --site-id <uuid>            # single site
    python -m pipeline.wiki_image_downloader --dry-run                   # preview only
    python -m pipeline.wiki_image_downloader --stats                     # show coverage
"""

import argparse
import hashlib
import re
import time
import urllib.parse
from pathlib import Path

import httpx
from loguru import logger
from sqlalchemy import text

from pipeline.database import WikiImage, get_session

# =============================================================================
# Configuration
# =============================================================================

OWN_SOURCES = ("ancient_nerds", "lyra", "ancient_nerds_community")

# Output directory for downloaded images
IMAGE_DIR = Path("public/data/images/wiki")

# Wikipedia/Wikimedia API endpoints
WIKIPEDIA_REST_API = "https://en.wikipedia.org/api/rest_v1"
WIKIPEDIA_ACTION_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

# Thumbnail width for downloads
THUMB_WIDTH = 800

# Rate limits (seconds between requests)
WIKIPEDIA_DELAY = 1.0
WIKIDATA_DELAY = 2.0

# Excluded image patterns (icons, logos, UI elements) — matches frontend
EXCLUDED_PATTERN = re.compile(
    r"icon|logo|symbol|diagram|chart|graph|flag|wikimedia|commons-logo|"
    r"edit-|question-mark|disambig|stub|padlock|pp-|protection|wikidata|"
    r"wiktionary|wikinews|wikiquote|wikisource|wikiversity|wikivoyage|"
    r"wikispecies|wikibooks|mediawiki|signature|coat.of.arms|escudo|"
    r"blason|coa_|seal_of|emblem",
    re.IGNORECASE,
)
EXCLUDED_EXT = re.compile(r"\.svg$", re.IGNORECASE)

# User-Agent per Wikimedia policy
HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}


# =============================================================================
# URL helpers
# =============================================================================

def extract_title_from_url(wikipedia_url: str) -> str | None:
    """Extract article title from a Wikipedia URL."""
    try:
        parsed = urllib.parse.urlparse(wikipedia_url)
        if not parsed.hostname or "wikipedia.org" not in parsed.hostname:
            return None

        # /wiki/Article_Title
        match = re.match(r"^/wiki/(.+)$", parsed.path)
        if match:
            return urllib.parse.unquote(match.group(1))

        # ?title=Article_Title
        params = urllib.parse.parse_qs(parsed.query)
        if "title" in params:
            return urllib.parse.unquote(params["title"][0])
    except Exception:
        pass
    return None


def thumb_to_original(thumb_url: str) -> str:
    """Convert a Wikimedia thumbnail URL to the original full-resolution URL."""
    url = thumb_url
    if url.startswith("//"):
        url = "https:" + url

    if "/thumb/" in url:
        url = url.replace("/thumb/", "/")
        last_slash = url.rfind("/")
        if last_slash > 0:
            url = url[:last_slash]

    return url


def site_image_dir(site_id: str) -> Path:
    """Get the directory for a site's images (first 8 chars of UUID)."""
    return IMAGE_DIR / site_id[:8]


def sanitize_filename(filename: str, max_len: int = 200) -> str:
    """Sanitize a filename for local storage."""
    # Remove unsafe characters
    safe = re.sub(r'[<>:"/\\|?*]', "_", filename)
    safe = safe.strip(". ")
    if len(safe) > max_len:
        # Keep extension
        name, ext = (safe[:safe.rfind(".")], safe[safe.rfind("."):]) if "." in safe else (safe, "")
        safe = name[:max_len - len(ext)] + ext
    return safe or "image.jpg"


# =============================================================================
# Wikipedia API functions
# =============================================================================

def fetch_article_images(article_title: str) -> list[dict]:
    """
    Fetch all images from a Wikipedia article via REST API media-list.

    Returns list of dicts with: title, thumb_url, full_url, is_lead
    """
    encoded = urllib.parse.quote(article_title.replace(" ", "_"), safe="")
    url = f"{WIKIPEDIA_REST_API}/page/media-list/{encoded}"

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url, headers=HEADERS)

        if resp.status_code != 200:
            logger.debug(f"media-list {resp.status_code} for {article_title}")
            return []

        data = resp.json()
        items = data.get("items", [])
    except Exception as e:
        logger.debug(f"media-list error for {article_title}: {e}")
        return []

    images = []
    for item in items:
        if item.get("type") != "image":
            continue
        if item.get("showInGallery") is False:
            continue

        title = item.get("title", "")
        if not title:
            continue
        if EXCLUDED_PATTERN.search(title) or EXCLUDED_EXT.search(title):
            continue

        srcset = item.get("srcset", [])
        if not srcset:
            continue

        # Get largest thumbnail from srcset
        sorted_srcset = sorted(srcset, key=lambda s: float(s.get("scale", "1").rstrip("x") or "1"), reverse=True)
        thumb_src = sorted_srcset[0]["src"]
        thumb_url = ("https:" + thumb_src) if thumb_src.startswith("//") else thumb_src
        full_url = thumb_to_original(thumb_url)

        images.append({
            "title": title,
            "display_title": title.replace("File:", "").rsplit(".", 1)[0],
            "thumb_url": thumb_url,
            "full_url": full_url,
            "commons_page_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title, safe='')}",
            "is_lead": item.get("leadImage") is True,
        })

    return images


def fetch_image_metadata(file_title: str) -> dict:
    """
    Fetch image metadata (author, license) via MediaWiki imageinfo API.

    Returns dict with: author, author_url, license, license_url, width, height
    """
    normalized = file_title if file_title.startswith("File:") else f"File:{file_title}"

    params = {
        "action": "query",
        "titles": normalized,
        "prop": "imageinfo",
        "iiprop": "extmetadata|size|url",
        "iiextmetadatafilter": "Artist|Author|Credit|LicenseShortName|License|LicenseUrl",
        "format": "json",
    }

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(WIKIPEDIA_ACTION_API, params=params, headers=HEADERS)

        if resp.status_code != 200:
            return {}

        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        page: dict = next(iter(pages.values()), {})
        info = (page.get("imageinfo") or [{}])[0]
        ext = info.get("extmetadata", {})

        # Parse author (strip HTML)
        author = ext.get("Artist", ext.get("Author", ext.get("Credit", {}))).get("value", "")
        if author:
            author = re.sub(r"<[^>]*>", "", author).strip()
            if len(author) > 200:
                author = author[:200] + "..."

        # Parse author URL from the original HTML
        author_url = None
        raw_artist = ext.get("Artist", ext.get("Author", {})).get("value", "")
        href_match = re.search(r'href="([^"]+)"', raw_artist)
        if href_match:
            author_url = href_match.group(1)
            if author_url.startswith("//"):
                author_url = "https:" + author_url

        license_name = ext.get("LicenseShortName", ext.get("License", {})).get("value", "")
        license_url = ext.get("LicenseUrl", {}).get("value", "")

        return {
            "author": author or None,
            "author_url": author_url,
            "license": license_name or None,
            "license_url": license_url or None,
            "width": info.get("width"),
            "height": info.get("height"),
            "original_url": info.get("url"),
        }
    except Exception as e:
        logger.debug(f"imageinfo error for {file_title}: {e}")
        return {}


def wikipedia_opensearch(site_name: str) -> str | None:
    """Resolve a site name to a Wikipedia article title using opensearch."""
    params = {
        "action": "opensearch",
        "search": site_name,
        "limit": "1",
        "namespace": "0",
        "format": "json",
    }

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(WIKIPEDIA_ACTION_API, params=params, headers=HEADERS)

        if resp.status_code == 200:
            data = resp.json()
            titles = data[1] if len(data) > 1 else []
            return titles[0] if titles else None
    except Exception as e:
        logger.debug(f"opensearch error for '{site_name}': {e}")
    return None


# =============================================================================
# Wikidata fallback for sites without Wikipedia URL
# =============================================================================

def wikidata_p18_for_name(site_name: str) -> str | None:
    """Query Wikidata for an image (P18) by site name. Returns Commons filename."""
    query = f"""
    SELECT ?image WHERE {{
      ?item rdfs:label "{site_name.replace('"', '')}"@en .
      ?item wdt:P18 ?image .
    }} LIMIT 1
    """

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(
                WIKIDATA_SPARQL_URL,
                params={"query": query, "format": "json"},
                headers={**HEADERS, "Accept": "application/sparql-results+json"},
            )

        if resp.status_code != 200:
            return None

        bindings = resp.json().get("results", {}).get("bindings", [])
        if bindings:
            image_url = bindings[0].get("image", {}).get("value", "")
            if image_url:
                return urllib.parse.unquote(image_url.split("/")[-1])
    except Exception as e:
        logger.debug(f"Wikidata P18 error for '{site_name}': {e}")
    return None


# =============================================================================
# Image download
# =============================================================================

def download_thumb(original_url: str, dest_path: Path, width: int = THUMB_WIDTH) -> tuple[int, int, int] | None:
    """
    Download a Wikimedia image thumbnail at the given width.

    Returns (file_size_bytes, width, height) or None on failure.
    """
    # Build thumbnail URL from original
    # Commons URL pattern: .../commons/a/ab/File.jpg
    # Thumb URL pattern:   .../commons/thumb/a/ab/File.jpg/800px-File.jpg
    if "upload.wikimedia.org" in original_url and "/thumb/" not in original_url:
        # Insert /thumb/ and append /{width}px-{filename}
        thumb_url = original_url.replace("/commons/", "/commons/thumb/")
        thumb_url = thumb_url.replace("/wikipedia/", "/wikipedia/thumb/")  # Some are under /wikipedia/
        filename = original_url.rsplit("/", 1)[-1]
        thumb_url = f"{thumb_url}/{width}px-{filename}"
    elif "/thumb/" in original_url:
        # Already a thumb URL, just change width
        thumb_url = re.sub(r"/\d+px-", f"/{width}px-", original_url)
    else:
        thumb_url = original_url

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(thumb_url, headers=HEADERS)

        if resp.status_code != 200:
            logger.debug(f"Download failed {resp.status_code}: {thumb_url}")
            return None

        content_type = resp.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            logger.debug(f"Not an image ({content_type}): {thumb_url}")
            return None

        content = resp.content
        if len(content) < 1000:
            logger.debug(f"Image too small ({len(content)} bytes), skipping: {thumb_url}")
            return None

        dest_path.write_bytes(content)

        # Try to get dimensions from response headers or PIL
        img_width, img_height = width, 0
        try:
            import io

            from PIL import Image
            with Image.open(io.BytesIO(content)) as img:
                img_width, img_height = img.size
        except Exception:
            pass

        return len(content), img_width, img_height

    except Exception as e:
        logger.debug(f"Download error: {e}")
        return None


# =============================================================================
# Main processing
# =============================================================================

def get_sites_to_process(
    source_filter: str | None = None,
    site_id: str | None = None,
) -> list[dict]:
    """Get sites from own sources that need image downloading."""
    with get_session() as session:
        if site_id:
            result = session.execute(text("""
                SELECT id, name, source_url, source_id
                FROM unified_sites
                WHERE id = :site_id
            """), {"site_id": site_id})
        elif source_filter:
            result = session.execute(text("""
                SELECT id, name, source_url, source_id
                FROM unified_sites
                WHERE source_id = :source
                ORDER BY name
            """), {"source": source_filter})
        else:
            result = session.execute(text("""
                SELECT id, name, source_url, source_id
                FROM unified_sites
                WHERE source_id IN :sources
                ORDER BY source_id, name
            """), {"sources": OWN_SOURCES})

        return [
            {"id": str(row.id), "name": row.name, "source_url": row.source_url, "source_id": row.source_id}
            for row in result
        ]


def site_already_downloaded(site_id: str) -> bool:
    """Check if a site already has images in the wiki_images table."""
    with get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM wiki_images WHERE site_id = :sid"),
            {"sid": site_id},
        ).scalar()
        return count > 0


def process_site(site: dict, dry_run: bool = False) -> int:
    """
    Download images for a single site.

    Returns number of images downloaded.
    """
    site_id = site["id"]
    site_name = site["name"]
    source_url = site.get("source_url")

    # Resolve Wikipedia article title
    article_title = None
    if source_url and "wikipedia.org" in (source_url or ""):
        article_title = extract_title_from_url(source_url)

    if not article_title:
        # Try opensearch
        article_title = wikipedia_opensearch(site_name)
        time.sleep(WIKIPEDIA_DELAY)

    if not article_title:
        logger.debug(f"No Wikipedia article for: {site_name}")
        return 0

    # Fetch media list
    images = fetch_article_images(article_title)
    time.sleep(WIKIPEDIA_DELAY)

    if not images:
        logger.debug(f"No images for: {site_name} ({article_title})")
        return 0

    if dry_run:
        logger.info(f"  [DRY RUN] {site_name}: {len(images)} images found")
        return len(images)

    # Download each image
    downloaded = 0
    img_dir = site_image_dir(site_id)

    for idx, img in enumerate(images):
        file_title = img["title"]
        local_filename = sanitize_filename(file_title.replace("File:", ""))
        dest_path = img_dir / local_filename

        # Skip if already exists on disk
        if dest_path.exists():
            downloaded += 1
            continue

        # Fetch metadata (author, license)
        meta = fetch_image_metadata(file_title)
        time.sleep(WIKIPEDIA_DELAY)

        # Use the original URL from metadata if available, otherwise from media-list
        original_url = meta.get("original_url") or img["full_url"]

        # Download thumbnail
        result = download_thumb(original_url, dest_path, THUMB_WIDTH)
        time.sleep(WIKIPEDIA_DELAY)

        if not result:
            continue

        file_size, img_width, img_height = result

        # Insert into database
        try:
            with get_session() as session:
                wiki_img = WikiImage(
                    site_id=site_id,
                    filename=local_filename,
                    original_url=original_url,
                    commons_page_url=img.get("commons_page_url"),
                    thumb_width=THUMB_WIDTH,
                    author=meta.get("author"),
                    author_url=meta.get("author_url"),
                    license=meta.get("license"),
                    license_url=meta.get("license_url"),
                    title=img.get("display_title"),
                    is_hero=(idx == 0),
                    is_lead=img.get("is_lead", False),
                    sort_order=idx,
                    source_type="wikimedia",
                    file_size_bytes=file_size,
                    width=img_width,
                    height=img_height,
                )
                session.add(wiki_img)
                session.commit()
                downloaded += 1
        except Exception as e:
            # UniqueConstraint violation = already exists, skip
            if "uq_wiki_image_site_url" in str(e):
                downloaded += 1
            else:
                logger.warning(f"DB insert error for {file_title}: {e}")

    return downloaded


def run_downloader(
    source_filter: str | None = None,
    site_id: str | None = None,
    dry_run: bool = False,
    stats_only: bool = False,
) -> None:
    """Main entry point for the wiki image downloader."""
    if stats_only:
        print_stats()
        return

    sites = get_sites_to_process(source_filter, site_id)
    logger.info(f"Found {len(sites)} sites to process")

    total_downloaded = 0
    total_skipped = 0
    total_errors = 0

    for i, site in enumerate(sites):
        if (i + 1) % 100 == 0:
            logger.info(f"Progress: {i + 1}/{len(sites)} sites ({total_downloaded} images downloaded)")

        # Skip sites that already have images
        if not dry_run and site_already_downloaded(site["id"]):
            total_skipped += 1
            continue

        try:
            count = process_site(site, dry_run=dry_run)
            total_downloaded += count
            if count > 0:
                logger.info(f"  [{i + 1}/{len(sites)}] {site['name']}: {count} images")
        except Exception as e:
            logger.warning(f"  Error processing {site['name']}: {e}")
            total_errors += 1

    logger.info("=" * 60)
    logger.info("Download complete:")
    logger.info(f"  Sites processed: {len(sites)}")
    logger.info(f"  Sites skipped (already done): {total_skipped}")
    logger.info(f"  Images downloaded: {total_downloaded}")
    logger.info(f"  Errors: {total_errors}")


def print_stats() -> None:
    """Print image download coverage statistics."""
    with get_session() as session:
        # Total sites in own sources
        total = session.execute(text(
            "SELECT COUNT(*) FROM unified_sites WHERE source_id IN :sources"
        ), {"sources": OWN_SOURCES}).scalar()

        # Sites with wiki images
        with_images = session.execute(text("""
            SELECT COUNT(DISTINCT site_id) FROM wiki_images
        """)).scalar()

        # Total images
        total_images = session.execute(text("SELECT COUNT(*) FROM wiki_images")).scalar()

        # Total disk size
        total_bytes = session.execute(text(
            "SELECT COALESCE(SUM(file_size_bytes), 0) FROM wiki_images"
        )).scalar()

        # By source
        by_source = session.execute(text("""
            SELECT us.source_id,
                   COUNT(DISTINCT us.id) AS total_sites,
                   COUNT(DISTINCT wi.site_id) AS sites_with_images,
                   COUNT(wi.id) AS total_images
            FROM unified_sites us
            LEFT JOIN wiki_images wi ON wi.site_id = us.id
            WHERE us.source_id IN :sources
            GROUP BY us.source_id
            ORDER BY us.source_id
        """), {"sources": OWN_SOURCES}).fetchall()

    print("\n" + "=" * 60)
    print("WIKI IMAGE DOWNLOAD STATISTICS")
    print("=" * 60)
    print(f"Total own sites:      {total:,}")
    print(f"Sites with images:    {with_images:,}")
    print(f"Coverage:             {100 * with_images / total:.1f}%" if total else "N/A")
    print(f"Total images:         {total_images:,}")
    print(f"Total disk size:      {total_bytes / 1024 / 1024:.1f} MB")
    print()
    print(f"{'Source':<30} {'Sites':>8} {'With img':>10} {'Images':>8}")
    print("-" * 60)
    for row in by_source:
        print(f"{row.source_id:<30} {row.total_sites:>8,} {row.sites_with_images:>10,} {row.total_images:>8,}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Download Wikipedia images for own sites")
    parser.add_argument("--source", type=str, help="Filter to specific source (e.g. ancient_nerds)")
    parser.add_argument("--site-id", type=str, help="Process a single site by UUID")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't download")
    parser.add_argument("--stats", action="store_true", help="Print coverage statistics")
    args = parser.parse_args()

    run_downloader(
        source_filter=args.source,
        site_id=args.site_id,
        dry_run=args.dry_run,
        stats_only=args.stats,
    )


if __name__ == "__main__":
    main()
