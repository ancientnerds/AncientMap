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
    python -m pipeline.wiki_image_downloader --force                     # re-process existing
    python -m pipeline.wiki_image_downloader --max-per-category 50       # limit Commons images
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

from pipeline.database import SiteContentLink, WikiImage, get_session

# =============================================================================
# Configuration
# =============================================================================

OWN_SOURCES = ("ancient_nerds", "lyra", "ancient_nerds_community")

# Output directory for downloaded images
IMAGE_DIR = Path("public/data/images/wiki")

# Wikipedia/Wikimedia API endpoints
WIKIPEDIA_REST_API = "https://en.wikipedia.org/api/rest_v1"
WIKIPEDIA_ACTION_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_ACTION_API = "https://www.wikidata.org/w/api.php"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

# Thumbnail width for downloads
THUMB_WIDTH = 800

# Rate limits (seconds between requests)
WIKIPEDIA_DELAY = 1.0
WIKIDATA_DELAY = 2.0
COMMONS_DELAY = 0.5  # Commons is more lenient

# Wikidata image properties to extract
WIKIDATA_IMAGE_PROPS = {
    "P18": "wikidata_p18",  # Main image
    "P3451": "wikidata_p3451",  # Nighttime view
    "P4291": "wikidata_p4291",  # Panoramic view
    "P5775": "wikidata_p5775",  # Interior view
}

# Excluded image patterns (icons, logos, UI elements) — matches frontend
EXCLUDED_PATTERN = re.compile(
    r"icon|logo|symbol|diagram|chart|graph|flag|wikimedia|commons-logo|"
    r"edit-|question-mark|disambig|stub|padlock|pp-|protection|wikidata|"
    r"wiktionary|wikinews|wikiquote|wikisource|wikiversity|wikivoyage|"
    r"wikispecies|wikibooks|mediawiki|signature|coat.of.arms|escudo|"
    r"blason|coa_|seal_of|emblem",
    re.IGNORECASE,
)
EXCLUDED_EXT = re.compile(
    r"\.(svg|oga|ogg|ogv|mp3|mp4|wav|webm|flac|midi?|pdf|djvu|stl)$", re.IGNORECASE
)
PAPER_EXT = re.compile(r"\.(pdf|djvu)$", re.IGNORECASE)

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
        name, ext = (
            (safe[: safe.rfind(".")], safe[safe.rfind(".") :]) if "." in safe else (safe, "")
        )
        safe = name[: max_len - len(ext)] + ext
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
        sorted_srcset = sorted(
            srcset, key=lambda s: float(s.get("scale", "1").rstrip("x") or "1"), reverse=True
        )
        thumb_src = sorted_srcset[0]["src"]
        thumb_url = ("https:" + thumb_src) if thumb_src.startswith("//") else thumb_src
        full_url = thumb_to_original(thumb_url)

        images.append(
            {
                "title": title,
                "display_title": title.replace("File:", "").rsplit(".", 1)[0],
                "thumb_url": thumb_url,
                "full_url": full_url,
                "commons_page_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title, safe='')}",
                "is_lead": item.get("leadImage") is True,
            }
        )

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
      ?item rdfs:label "{site_name.replace('"', "")}"@en .
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


def resolve_wikidata_entity(article_title: str) -> dict | None:
    """
    Resolve a Wikipedia article title to a Wikidata entity.

    Returns dict with: qid, commons_category (P373), commons_gallery (P935),
    and image filenames for P18, P3451, P4291, P5775.
    Returns None if resolution fails.
    """
    # Step 1: Get Wikidata QID from Wikipedia article
    encoded_title = article_title.replace(" ", "_")
    params = {
        "action": "query",
        "titles": encoded_title,
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "format": "json",
    }

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(WIKIPEDIA_ACTION_API, params=params, headers=HEADERS)

        if resp.status_code != 200:
            return None

        pages = resp.json().get("query", {}).get("pages", {})
        page: dict = next(iter(pages.values()), {})
        qid = page.get("pageprops", {}).get("wikibase_item")
        if not qid:
            return None
    except Exception as e:
        logger.debug(f"Wikidata QID lookup failed for '{article_title}': {e}")
        return None

    time.sleep(WIKIDATA_DELAY)

    # Step 2: Fetch entity claims from Wikidata
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "claims",
        "format": "json",
    }

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(WIKIDATA_ACTION_API, params=params, headers=HEADERS)

        if resp.status_code != 200:
            return None

        entity = resp.json().get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})
    except Exception as e:
        logger.debug(f"Wikidata entity fetch failed for {qid}: {e}")
        return None

    def get_string_value(prop_id: str) -> str | None:
        claim_list = claims.get(prop_id, [])
        if claim_list:
            snak = claim_list[0].get("mainsnak", {})
            return snak.get("datavalue", {}).get("value")
        return None

    result = {"qid": qid}

    # P373 = Commons category name (the key to unlocking many more images)
    result["commons_category"] = get_string_value("P373")
    # P935 = Commons gallery page
    result["commons_gallery"] = get_string_value("P935")

    # Image properties: P18, P3451, P4291, P5775
    result["images"] = {}
    for prop_id, source_type in WIKIDATA_IMAGE_PROPS.items():
        filename = get_string_value(prop_id)
        if filename:
            result["images"][source_type] = filename

    return result


# =============================================================================
# Commons category fetcher
# =============================================================================


def _parse_commons_file_page(page: dict) -> dict | None:
    """Parse a single Commons API page result into an image dict."""
    file_title = page.get("title", "")
    if not file_title:
        return None
    if EXCLUDED_PATTERN.search(file_title) or EXCLUDED_EXT.search(file_title):
        return None

    info_list = page.get("imageinfo", [])
    if not info_list:
        return None
    info = info_list[0]

    original_url = info.get("url")
    if not original_url:
        return None

    ext = info.get("extmetadata", {})

    # Parse author (strip HTML)
    author_raw = ext.get("Artist", {}).get("value", "")
    author = re.sub(r"<[^>]*>", "", author_raw).strip() if author_raw else None
    if author and len(author) > 200:
        author = author[:200] + "..."

    # Parse author URL from HTML
    author_url = None
    href_match = re.search(r'href="([^"]+)"', author_raw)
    if href_match:
        author_url = href_match.group(1)
        if author_url.startswith("//"):
            author_url = "https:" + author_url

    license_name = ext.get("LicenseShortName", {}).get("value", "")
    license_url = ext.get("LicenseUrl", {}).get("value", "")

    encoded_title = urllib.parse.quote(file_title, safe="")
    return {
        "title": file_title,
        "display_title": file_title.replace("File:", "").rsplit(".", 1)[0],
        "original_url": original_url,
        "commons_page_url": f"https://commons.wikimedia.org/wiki/{encoded_title}",
        "is_lead": False,
        "author": author or None,
        "author_url": author_url,
        "license": license_name or None,
        "license_url": license_url or None,
        "width": info.get("width"),
        "height": info.get("height"),
        "source_type": "commons_category",
        "_has_metadata": True,
    }


def _parse_commons_paper(page: dict) -> dict | None:
    """Parse a Commons API page result for a PDF/DjVu into a paper dict."""
    file_title = page.get("title", "")
    if not file_title or not PAPER_EXT.search(file_title):
        return None

    info_list = page.get("imageinfo", [])
    url = info_list[0].get("url") if info_list else None
    if not url:
        return None

    # Clean title: "File:Pompei (IA pompeiscene00confiala).pdf" → "Pompei"
    clean = file_title.replace("File:", "").rsplit(".", 1)[0]
    # Strip Internet Archive IDs in parentheses: "(IA ...)"
    clean = re.sub(r"\s*\(IA\s+\w+\)\s*$", "", clean).strip()

    encoded_title = urllib.parse.quote(file_title, safe="")
    return {
        "title": clean or file_title,
        "content_url": f"https://commons.wikimedia.org/wiki/{encoded_title}",
        "original_url": url,
        "filename": file_title.replace("File:", ""),
    }


def _fetch_category_files(
    client: httpx.Client, category_name: str, limit: int, papers: list[dict] | None = None
) -> list[dict]:
    """Fetch direct file members from a single Commons category.

    If papers list is provided, PDF/DjVu files are appended to it instead of being discarded.
    """
    images: list[dict] = []
    gcmcontinue = None

    while len(images) < limit:
        params = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{category_name}",
            "gcmtype": "file",
            "gcmlimit": str(min(50, limit - len(images))),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
            "format": "json",
        }
        if gcmcontinue:
            params["gcmcontinue"] = gcmcontinue

        try:
            resp = client.get(COMMONS_API_URL, params=params, headers=HEADERS)
            if resp.status_code != 200:
                break
            data = resp.json()
        except Exception as e:
            logger.debug(f"Commons category error for {category_name}: {e}")
            break

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            # Collect PDFs as papers before the image parser filters them out
            if papers is not None:
                paper = _parse_commons_paper(page)
                if paper:
                    papers.append(paper)
            parsed = _parse_commons_file_page(page)
            if parsed:
                images.append(parsed)

        cont = data.get("continue", {})
        gcmcontinue = cont.get("gcmcontinue")
        if not gcmcontinue:
            break

        time.sleep(COMMONS_DELAY)

    return images[:limit]


def _fetch_subcategory_names(client: httpx.Client, category_name: str) -> list[str]:
    """Fetch direct subcategory names from a Commons category."""
    subcats: list[str] = []
    cmcontinue = None

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category_name}",
            "cmtype": "subcat",
            "cmlimit": "50",
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        try:
            resp = client.get(COMMONS_API_URL, params=params, headers=HEADERS)
            if resp.status_code != 200:
                break
            data = resp.json()
        except Exception:
            break

        for member in data.get("query", {}).get("categorymembers", []):
            title = member.get("title", "")
            if title.startswith("Category:"):
                subcats.append(title.removeprefix("Category:"))

        cont = data.get("continue", {})
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue:
            break

        time.sleep(COMMONS_DELAY)

    return subcats


def fetch_commons_category_images(
    category_name: str, limit: int = 200
) -> tuple[list[dict], list[dict]]:
    """
    Fetch image files from a Wikimedia Commons category and its subcategories.

    Crawls 1 level deep: direct files from the main category, then direct files
    from each subcategory, until the limit is reached.

    Returns (images, papers) — papers are PDF/DjVu files found along the way.
    """
    papers: list[dict] = []

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        # Direct files from the main category
        images = _fetch_category_files(client, category_name, limit, papers)
        if len(images) >= limit:
            return images[:limit], papers

        # Subcategories — fetch files from each until we hit the limit
        subcats = _fetch_subcategory_names(client, category_name)
        for subcat in subcats:
            remaining = limit - len(images)
            if remaining <= 0:
                break
            sub_images = _fetch_category_files(client, subcat, remaining, papers)
            images.extend(sub_images)

    return images[:limit], papers


def build_wikidata_image_entries(wikidata_images: dict[str, str]) -> list[dict]:
    """
    Build image entries from Wikidata curated properties (P18, P3451, etc.).

    Takes a dict of {source_type: commons_filename} and returns list of image dicts.
    """
    entries = []
    for source_type, filename in wikidata_images.items():
        # Build the Commons file URL from filename
        # MD5 hash of filename determines the directory path
        encoded_name = filename.replace(" ", "_")
        md5 = hashlib.md5(encoded_name.encode()).hexdigest()
        original_url = f"https://upload.wikimedia.org/wikipedia/commons/{md5[0]}/{md5[:2]}/{urllib.parse.quote(encoded_name)}"
        encoded_title = urllib.parse.quote(f"File:{encoded_name}", safe="")

        entries.append(
            {
                "title": f"File:{filename}",
                "display_title": filename.rsplit(".", 1)[0],
                "original_url": original_url,
                "commons_page_url": f"https://commons.wikimedia.org/wiki/{encoded_title}",
                "is_lead": False,
                "source_type": source_type,
                "_has_metadata": False,  # Need to fetch metadata separately
            }
        )

    return entries


# =============================================================================
# Image download
# =============================================================================


def download_image(
    original_url: str, dest_path: Path, width: int | None = None
) -> tuple[int, int, int] | None:
    """
    Download a Wikimedia image, convert to WebP, and save.

    If width is set, fetches a thumbnail at that width.
    If width is None, fetches the original full-resolution image.
    dest_path must already have a .webp extension.
    Returns (file_size_bytes, width, height) or None on failure.
    """
    import io

    from PIL import Image

    if width is not None:
        # Build thumbnail URL from original
        # Commons URL pattern: .../commons/a/ab/File.jpg
        # Thumb URL pattern:   .../commons/thumb/a/ab/File.jpg/800px-File.jpg
        if "upload.wikimedia.org" in original_url and "/thumb/" not in original_url:
            # Insert /thumb/ into the path — URLs are either /wikipedia/commons/
            # or /wikipedia/en/ etc, so only one replacement should apply.
            if "/wikipedia/commons/" in original_url:
                fetch_url = original_url.replace("/commons/", "/commons/thumb/", 1)
            else:
                fetch_url = re.sub(
                    r"/wikipedia/(\w+)/", r"/wikipedia/\1/thumb/", original_url, count=1
                )
            filename = original_url.rsplit("/", 1)[-1]
            fetch_url = f"{fetch_url}/{width}px-{filename}"
        elif "/thumb/" in original_url:
            fetch_url = re.sub(r"/\d+px-", f"/{width}px-", original_url)
        else:
            fetch_url = original_url
    else:
        # Download original — strip any /thumb/ rewrite to get the real URL
        if "/thumb/" in original_url:
            fetch_url = thumb_to_original(original_url)
        else:
            fetch_url = original_url

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(fetch_url, headers=HEADERS)

        if resp.status_code != 200:
            logger.debug(f"Download failed {resp.status_code}: {fetch_url}")
            return None

        content_type = resp.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            logger.debug(f"Not an image ({content_type}): {fetch_url}")
            return None

        raw_bytes = resp.content
        if len(raw_bytes) < 1000:
            logger.debug(f"Image too small ({len(raw_bytes)} bytes), skipping: {fetch_url}")
            return None

        # Convert to WebP for smaller file size and faster loading
        try:
            Image.MAX_IMAGE_PIXELS = 500_000_000  # Allow large panoramic photos
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img_width, img_height = img.size
                # Convert RGBA/palette to RGB (WebP lossy doesn't support palette)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGBA")
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(dest_path, "WEBP", quality=82, method=4)
        except Exception as e:
            logger.debug(f"WebP conversion failed, saving original: {e}")
            dest_path.write_bytes(raw_bytes)
            img_width, img_height = width or 0, 0

        file_size = dest_path.stat().st_size
        return file_size, img_width, img_height

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
            result = session.execute(
                text("""
                SELECT id, name, source_url, source_id
                FROM unified_sites
                WHERE id = :site_id
            """),
                {"site_id": site_id},
            )
        elif source_filter:
            result = session.execute(
                text("""
                SELECT id, name, source_url, source_id
                FROM unified_sites
                WHERE source_id = :source
                ORDER BY name
            """),
                {"source": source_filter},
            )
        else:
            result = session.execute(
                text("""
                SELECT id, name, source_url, source_id
                FROM unified_sites
                WHERE source_id IN :sources
                ORDER BY source_id, name
            """),
                {"sources": OWN_SOURCES},
            )

        return [
            {
                "id": str(row.id),
                "name": row.name,
                "source_url": row.source_url,
                "source_id": row.source_id,
            }
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


def process_site(site: dict, dry_run: bool = False, max_per_category: int = 200) -> int:
    """
    Download images for a single site from all sources:
    1. Wikipedia article images (media-list REST API)
    2. Wikidata curated images (P18, P3451, P4291, P5775)
    3. Wikimedia Commons category images (via Wikidata P373)

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
        article_title = wikipedia_opensearch(site_name)
        time.sleep(WIKIPEDIA_DELAY)

    if not article_title:
        logger.debug(f"No Wikipedia article for: {site_name}")
        return 0

    # --- Source 1: Wikipedia article images ---
    all_images: list[dict] = []
    wp_images = fetch_article_images(article_title)
    time.sleep(WIKIPEDIA_DELAY)

    for img in wp_images:
        img["source_type"] = "wikipedia"
        img["_has_metadata"] = False
    all_images.extend(wp_images)

    # --- Source 2 & 3: Wikidata entity + Commons category ---
    all_papers: list[dict] = []
    wikidata = resolve_wikidata_entity(article_title)
    if wikidata:
        # Source 2: Wikidata curated images (P18, P3451, P4291, P5775)
        if wikidata.get("images"):
            wd_entries = build_wikidata_image_entries(wikidata["images"])
            all_images.extend(wd_entries)
            logger.debug(f"  Wikidata: {len(wd_entries)} curated images for {site_name}")

        # Source 3: Commons category images
        commons_cat = wikidata.get("commons_category")
        if commons_cat:
            cat_images, cat_papers = fetch_commons_category_images(
                commons_cat, limit=max_per_category
            )
            all_images.extend(cat_images)
            all_papers.extend(cat_papers)
            logger.debug(
                f"  Commons category '{commons_cat}': {len(cat_images)} images, "
                f"{len(cat_papers)} papers for {site_name}"
            )

    time.sleep(WIKIDATA_DELAY)

    # --- Deduplicate by file title + URL ---
    # The File: title is the canonical Wikimedia identifier — same image always
    # has the same title even when URLs differ due to encoding (thumb_to_original
    # vs imageinfo API vs MD5-constructed URL).
    seen: set[str] = set()
    deduped: list[dict] = []
    for img in all_images:
        title_key = img.get("title", "").replace(" ", "_").lower()
        url = img.get("original_url") or img.get("full_url", "")
        if title_key in seen or url in seen:
            continue
        if title_key:
            seen.add(title_key)
        if url:
            seen.add(url)
        deduped.append(img)

    if not deduped:
        logger.debug(f"No images for: {site_name} ({article_title})")
        return 0

    # --- Pick best hero image (most panoramic) and move to front ---
    best_hero_idx = 0  # default: first image (Wikipedia lead)

    # Priority 1: Wikidata P4291 (explicitly tagged as panoramic view)
    for i, img in enumerate(deduped):
        if img.get("source_type") == "wikidata_p4291":
            best_hero_idx = i
            break
    else:
        # Priority 2: widest aspect ratio among images with known dimensions
        best_ratio = 0.0
        for i, img in enumerate(deduped):
            w, h = img.get("width"), img.get("height")
            if w and h and h > 0:
                ratio = w / h
                if ratio > best_ratio and ratio >= 1.5:
                    best_ratio = ratio
                    best_hero_idx = i

    if best_hero_idx != 0:
        hero = deduped.pop(best_hero_idx)
        deduped.insert(0, hero)

    if dry_run:
        wp_count = sum(1 for i in deduped if i.get("source_type") == "wikipedia")
        wd_count = sum(1 for i in deduped if (i.get("source_type") or "").startswith("wikidata"))
        cc_count = sum(1 for i in deduped if i.get("source_type") == "commons_category")
        logger.info(
            f"  [DRY RUN] {site_name}: {len(deduped)} images "
            f"(wikipedia={wp_count}, wikidata={wd_count}, commons={cc_count})"
        )
        if all_papers:
            logger.info(f"  [DRY RUN] {site_name}: {len(all_papers)} papers from Commons")
        return len(deduped)

    # --- Download each image ---
    downloaded = 0
    img_dir = site_image_dir(site_id)

    for idx, img in enumerate(deduped):
        file_title = img["title"]
        raw_name = sanitize_filename(file_title.replace("File:", ""))
        local_filename = re.sub(r"\.[^.]+$", ".webp", raw_name)
        if not local_filename.endswith(".webp"):
            local_filename += ".webp"
        dest_path = img_dir / local_filename

        # Skip if already exists on disk
        if dest_path.exists():
            downloaded += 1
            continue

        # Fetch metadata if not already inline (Wikipedia and Wikidata images need it)
        if img.get("_has_metadata"):
            meta = {
                "author": img.get("author"),
                "author_url": img.get("author_url"),
                "license": img.get("license"),
                "license_url": img.get("license_url"),
                "width": img.get("width"),
                "height": img.get("height"),
            }
        else:
            meta = fetch_image_metadata(file_title)
            time.sleep(WIKIPEDIA_DELAY)

        # Use the original URL from metadata if available, otherwise from the image dict
        original_url = (
            meta.get("original_url") or img.get("original_url") or img.get("full_url", "")
        )

        # Download: hero image as 800px thumbnail, others at original size
        is_hero = idx == 0
        dl_width = THUMB_WIDTH if is_hero else None
        result = download_image(original_url, dest_path, width=dl_width)
        time.sleep(COMMONS_DELAY)

        if not result:
            continue

        file_size, img_width, img_height = result
        source_type = img.get("source_type", "wikimedia")

        # Insert into database
        try:
            with get_session() as session:
                wiki_img = WikiImage(
                    site_id=site_id,
                    filename=local_filename,
                    original_url=original_url,
                    commons_page_url=img.get("commons_page_url"),
                    thumb_width=dl_width,
                    author=meta.get("author") or img.get("author"),
                    author_url=meta.get("author_url") or img.get("author_url"),
                    license=meta.get("license") or img.get("license"),
                    license_url=meta.get("license_url") or img.get("license_url"),
                    title=img.get("display_title"),
                    is_hero=is_hero,
                    is_lead=img.get("is_lead", False),
                    sort_order=idx,
                    source_type=source_type,
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

    # --- Save papers (PDF/DjVu) as SiteContentLink rows ---
    if all_papers:
        saved_papers = 0
        with get_session() as session:
            for paper in all_papers:
                try:
                    link = SiteContentLink(
                        site_id=site_id,
                        content_type="paper",
                        content_source="wikimedia_commons",
                        content_id=paper["filename"],
                        title=paper["title"],
                        content_url=paper["content_url"],
                        link_metadata={"download_url": paper["original_url"]},
                    )
                    session.add(link)
                    session.commit()
                    saved_papers += 1
                except Exception as e:
                    session.rollback()
                    if "uq_content_link" in str(e):
                        pass  # Already linked
                    else:
                        logger.warning(f"Paper link error for {paper['filename']}: {e}")
        if saved_papers:
            logger.info(f"  {site_name}: linked {saved_papers} papers from Commons")

    return downloaded


def run_downloader(
    source_filter: str | None = None,
    site_id: str | None = None,
    dry_run: bool = False,
    stats_only: bool = False,
    force: bool = False,
    max_per_category: int = 200,
) -> None:
    """Main entry point for the wiki image downloader."""
    if stats_only:
        print_stats()
        return

    sites = get_sites_to_process(source_filter, site_id)
    logger.info(f"Found {len(sites)} sites to process")
    if force:
        logger.info("--force enabled: re-processing sites even if they already have images")

    total_downloaded = 0
    total_skipped = 0
    total_errors = 0

    for i, site in enumerate(sites):
        if (i + 1) % 100 == 0:
            logger.info(
                f"Progress: {i + 1}/{len(sites)} sites ({total_downloaded} images downloaded)"
            )

        # Skip sites that already have images (unless --force)
        if not dry_run and not force and site_already_downloaded(site["id"]):
            total_skipped += 1
            continue

        try:
            count = process_site(site, dry_run=dry_run, max_per_category=max_per_category)
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
        total = session.execute(
            text("SELECT COUNT(*) FROM unified_sites WHERE source_id IN :sources"),
            {"sources": OWN_SOURCES},
        ).scalar()

        # Sites with wiki images
        with_images = session.execute(
            text("""
            SELECT COUNT(DISTINCT site_id) FROM wiki_images
        """)
        ).scalar()

        # Total images
        total_images = session.execute(text("SELECT COUNT(*) FROM wiki_images")).scalar()

        # Total disk size
        total_bytes = session.execute(
            text("SELECT COALESCE(SUM(file_size_bytes), 0) FROM wiki_images")
        ).scalar()

        # By source
        by_source = session.execute(
            text("""
            SELECT us.source_id,
                   COUNT(DISTINCT us.id) AS total_sites,
                   COUNT(DISTINCT wi.site_id) AS sites_with_images,
                   COUNT(wi.id) AS total_images
            FROM unified_sites us
            LEFT JOIN wiki_images wi ON wi.site_id = us.id
            WHERE us.source_id IN :sources
            GROUP BY us.source_id
            ORDER BY us.source_id
        """),
            {"sources": OWN_SOURCES},
        ).fetchall()

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
        print(
            f"{row.source_id:<30} {row.total_sites:>8,} {row.sites_with_images:>10,} {row.total_images:>8,}"
        )
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Download Wikipedia images for own sites")
    parser.add_argument("--source", type=str, help="Filter to specific source (e.g. ancient_nerds)")
    parser.add_argument("--site-id", type=str, help="Process a single site by UUID")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't download")
    parser.add_argument("--stats", action="store_true", help="Print coverage statistics")
    parser.add_argument(
        "--force", action="store_true", help="Re-process sites that already have images"
    )
    parser.add_argument(
        "--max-per-category",
        type=int,
        default=200,
        help="Max images to fetch from Commons category per site (default: 200)",
    )
    args = parser.parse_args()

    run_downloader(
        source_filter=args.source,
        site_id=args.site_id,
        dry_run=args.dry_run,
        stats_only=args.stats,
        force=args.force,
        max_per_category=args.max_per_category,
    )


if __name__ == "__main__":
    main()
