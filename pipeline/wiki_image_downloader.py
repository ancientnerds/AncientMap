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
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from pipeline.database import WikiImage, get_session
from pipeline.utils.mediawiki import dereference

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

LOCAL_MAX_WIDTH = 1600  # widest stored file: the 1600x900 hero pages want (rule: download_image)
FETCH_BUCKET = 1920  # the smallest Commons thumbnail bucket that is >= LOCAL_MAX_WIDTH
MAX_RAW_BYTES = 50_000_000  # 50 MB — skip downloads larger than this

# Rate limits per Wikimedia robot policy: 1s between requests, serial only
WIKIPEDIA_DELAY = 1.0
WIKIDATA_DELAY = 1.0
COMMONS_DELAY = 1.0

# Download settings — sequential per Wikimedia robot policy (1 req at a time)
# https://www.mediawiki.org/wiki/API:Etiquette
# https://wikitech.wikimedia.org/wiki/Robot_policy
DOWNLOAD_RETRY_ROUNDS = 3
DOWNLOAD_DELAY = 1.0  # 1 second between downloads per robot policy


class RateLimitedError(Exception):
    """Raised when Wikimedia returns 429 Too Many Requests."""

    def __init__(self, retry_after: float):
        self.retry_after = retry_after


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
# User-Agent per Wikimedia policy
HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}

# Shared HTTP client — reuses TCP connections to avoid Wikimedia connection resets.
# Each function was creating/destroying its own httpx.Client, which opened too many
# short-lived connections and triggered [WinError 10054] / 503 errors.
_http_client = httpx.Client(
    timeout=30,
    follow_redirects=True,
    headers=HEADERS,
    limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
)
# Longer timeout client for image downloads (large files)
_download_client = httpx.Client(
    timeout=60,
    follow_redirects=True,
    headers=HEADERS,
    limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
)


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
        resp = _http_client.get(url)

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


def fetch_image_metadata_batch(file_titles: list[str]) -> dict[str, dict]:
    """
    Fetch metadata for up to 50 images in one API call.

    The MediaWiki imageinfo API accepts pipe-separated titles (max 50) and answers each under the
    title it normalised it to (`File:A_b.jpg` -> `File:A b.jpg`, listed in `query.normalized`).
    Returns {requested File: title: {author, author_url, license, license_url, width, height,
    original_url}}, keyed by the title as it was asked: keyed by the answer's own title, 12 of 12
    underscore titles of a live media-list (en.wikipedia `Stonehenge`, 2026-09-23) missed their
    lookup, lost their width and failed to download. A Commons file redirect is answered under
    the requested title itself (measured the same day, with and without `redirects=1`). The
    original's URL and size are `parse_attribution`'s: the imageinfo url carries `?utm_...`
    analytics parameters that an upload original never needs.
    """
    if not file_titles:
        return {}

    requested = [t if t.startswith("File:") else f"File:{t}" for t in file_titles]
    titles_param = "|".join(requested)

    params = {
        "action": "query",
        "titles": titles_param,
        "prop": "imageinfo",
        "iiprop": "extmetadata|size|url",
        "iiextmetadatafilter": "Artist|Author|Credit|LicenseShortName|License|LicenseUrl",
        "format": "json",
    }

    try:
        resp = _http_client.get(WIKIPEDIA_ACTION_API, params=params)

        if resp.status_code != 200:
            return {}

        data = resp.json()
        query = data.get("query", {})
    except Exception as e:
        logger.debug(f"batch imageinfo error: {e}")
        return {}

    pages = {page.get("title", ""): page for page in query.get("pages", {}).values()}
    normalized = {entry["from"]: entry["to"] for entry in query.get("normalized", [])}
    results: dict[str, dict] = {}
    for title in requested:
        page = pages.get(dereference(title, normalized))
        if page is None:
            continue
        info = (page.get("imageinfo") or [{}])[0]
        ext = info.get("extmetadata", {})

        author = ext.get("Artist", ext.get("Author", ext.get("Credit", {}))).get("value", "")
        if author:
            author = re.sub(r"<[^>]*>", "", author).strip()
            if len(author) > 200:
                author = author[:200] + "..."

        author_url = None
        raw_artist = ext.get("Artist", ext.get("Author", {})).get("value", "")
        href_match = re.search(r'href="([^"]+)"', raw_artist)
        if href_match:
            author_url = href_match.group(1)
            if author_url.startswith("//"):
                author_url = "https:" + author_url

        license_name = ext.get("LicenseShortName", ext.get("License", {})).get("value", "")
        license_url = ext.get("LicenseUrl", {}).get("value", "")
        original = parse_attribution(info)

        results[title] = {
            "author": author or None,
            "author_url": author_url,
            "license": license_name or None,
            "license_url": license_url or None,
            "width": original["width"],
            "height": original["height"],
            "original_url": original["original_url"],
        }

    return results


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
        resp = _http_client.get(WIKIPEDIA_ACTION_API, params=params)

        if resp.status_code == 200:
            data = resp.json()
            titles = data[1] if len(data) > 1 else []
            return titles[0] if titles else None
    except Exception as e:
        logger.debug(f"opensearch error for '{site_name}': {e}")
    return None


# =============================================================================
# Wikidata entity resolution
# =============================================================================


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
        resp = _http_client.get(WIKIPEDIA_ACTION_API, params=params)

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
        resp = _http_client.get(WIKIDATA_ACTION_API, params=params)

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


def parse_attribution(info: dict) -> dict:
    """Author, licence and URLs out of one imageinfo entry.

    Shared by the category fetcher and the attribution backfill
    (scripts/backfill_image_attribution.py) — the Artist field is HTML and
    parsing it twice would drift.
    """
    ext = info.get("extmetadata", {})

    author_raw = ext.get("Artist", {}).get("value", "")
    author = re.sub(r"<[^>]*>", "", author_raw).strip() if author_raw else None
    if author and len(author) > 200:
        author = author[:200] + "..."

    author_url = None
    href_match = re.search(r'href="([^"]+)"', author_raw)
    if href_match:
        author_url = href_match.group(1)
        if author_url.startswith("//"):
            author_url = "https:" + author_url

    # The imageinfo url started carrying ?uselang=…&utm_… analytics params in
    # 2026. Upload originals never need a query string, and keeping it broke
    # the thumb-URL construction (filename included the query → HTTP 400) and
    # tainted 45,180 stored original_urls.
    original_url = (info.get("url") or "").split("?")[0] or None

    return {
        "author": author or None,
        "author_url": author_url,
        "license": ext.get("LicenseShortName", {}).get("value", "") or None,
        "license_url": ext.get("LicenseUrl", {}).get("value", "") or None,
        "original_url": original_url,
        "width": info.get("width"),
        "height": info.get("height"),
    }


def commons_page_url_for(file_title: str) -> str:
    """Canonical Commons page URL for a File: title."""
    return f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(file_title, safe='')}"


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

    meta = parse_attribution(info)
    if not meta["original_url"]:
        return None

    return {
        "title": file_title,
        "display_title": file_title.replace("File:", "").rsplit(".", 1)[0],
        "commons_page_url": commons_page_url_for(file_title),
        "is_lead": False,
        "source_type": "commons_category",
        "_has_metadata": True,
        **meta,
    }


def _fetch_category_files(category_name: str, limit: int) -> list[dict]:
    """Fetch direct file members from a single Commons category."""
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
            resp = _http_client.get(COMMONS_API_URL, params=params)
            if resp.status_code != 200:
                break
            data = resp.json()
        except Exception as e:
            logger.debug(f"Commons category error for {category_name}: {e}")
            break

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            parsed = _parse_commons_file_page(page)
            if parsed:
                images.append(parsed)

        cont = data.get("continue", {})
        gcmcontinue = cont.get("gcmcontinue")
        if not gcmcontinue:
            break

        time.sleep(COMMONS_DELAY)

    return images[:limit]


def _fetch_subcategory_names(category_name: str) -> list[str]:
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
            resp = _http_client.get(COMMONS_API_URL, params=params)
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


def fetch_commons_category_images(category_name: str, limit: int = 200) -> list[dict]:
    """
    Fetch image files from a Wikimedia Commons category and its subcategories.

    Crawls 1 level deep: direct files from the main category, then direct files
    from each subcategory, until the limit is reached.
    """
    # Direct files from the main category
    images = _fetch_category_files(category_name, limit)
    if len(images) >= limit:
        return images[:limit]

    # Subcategories — fetch files from each until we hit the limit
    subcats = _fetch_subcategory_names(category_name)
    for subcat in subcats:
        remaining = limit - len(images)
        if remaining <= 0:
            break
        sub_images = _fetch_category_files(subcat, remaining)
        images.extend(sub_images)

    return images[:limit]


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


#: The thumbnail widths Wikimedia serves. Measured 2026-09-23 with the census User-Agent:
#: `/800px-` and `/1600px-` answer HTTP 400, `/1280px-` and `/1920px-` answer 200 - any width
#: outside this list is a 400. The old `THUMB_WIDTH = 800` / `GALLERY_WIDTH = 1600` therefore
#: made every new download fail, and silently: the failure was logged at debug level and
#: returned as None. A bucket wider than the original is served *upscaled* (measured: a 327x800
#: original came back from the 1920 bucket as 1920x4697), so a bucket is only ever asked for an
#: original wider than it.
COMMONS_BUCKETS = (20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920, 3840)
#: Extensions whose thumbnail keeps the original's file name (`<width>px-<name>`). Every
#: `upload.wikimedia.org` original in the corpus is one of these (measured on the 2026-09-20
#: snapshot: jpg, jpeg, png, gif, webp); a TIFF or a PDF names its thumbnail differently.
THUMBNAIL_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
WEBP_QUALITY = 82
MIN_RAW_BYTES = 1000


class DownloadError(RuntimeError):
    """An image could not be stored. Carries the URL that was asked and the reason.

    Raised instead of the old debug-log-and-return-None: a download that fails must be named
    in the run's result, never counted as a skip.
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}: {url}")
        self.url = url
        self.reason = reason


@dataclass(frozen=True)
class DownloadResult:
    """What one stored file is, and how it was made."""

    file_size: int
    width: int
    height: int
    fetch_url: str
    #: The Commons bucket that was fetched, or None when the original itself was.
    fetched_bucket: int | None


def fetch_plan(original_url: str, original_width: int) -> tuple[str, int | None]:
    """(the URL to fetch, the bucket it names or None for the original).

    The original when it is at most FETCH_BUCKET px wide - then no bucket can be both valid
    and not an upscale - else the FETCH_BUCKET bucket. Either is then downscaled locally to
    LOCAL_MAX_WIDTH. Only a Commons/Wikipedia upload original is accepted: a thumbnail URL
    already names a width, and any other host has no bucket contract at all.
    """
    parsed = urllib.parse.urlparse(original_url)
    if parsed.scheme != "https" or parsed.netloc != "upload.wikimedia.org":
        raise DownloadError(original_url, "not an upload.wikimedia.org original")
    # The URL is stored as the row's original_url: a query (imageinfo's `?utm_...`) would taint
    # it, and urlparse keeps it out of the path the check below reads.
    if parsed.query or parsed.fragment:
        raise DownloadError(original_url, "an upload original carries no query or fragment")
    match = re.fullmatch(r"/wikipedia/([\w-]+)/([0-9a-f])/([0-9a-f]{2})/([^/]+)", parsed.path)
    if match is None:
        raise DownloadError(original_url, "not the path of an upload original")
    if isinstance(original_width, bool) or not isinstance(original_width, int):
        raise DownloadError(original_url, f"the original's width is {original_width!r}")
    if original_width <= 0:
        raise DownloadError(original_url, f"the original's width is {original_width}")
    if original_width <= FETCH_BUCKET:
        return original_url, None
    wiki, first, pair, name = match.groups()
    if not name.lower().endswith(THUMBNAIL_EXTENSIONS):
        raise DownloadError(original_url, "no thumbnail naming rule for this file type")
    return (
        f"https://upload.wikimedia.org/wikipedia/{wiki}/thumb/{first}/{pair}/{name}"
        f"/{FETCH_BUCKET}px-{name}",
        FETCH_BUCKET,
    )


def stored_size(width: int, height: int) -> tuple[int, int]:
    """The size of the stored derivative: at most LOCAL_MAX_WIDTH wide, never wider than given."""
    if width <= LOCAL_MAX_WIDTH:
        return width, height
    return LOCAL_MAX_WIDTH, max(1, round(height * LOCAL_MAX_WIDTH / width))


def download_image(original_url: str, dest_path: Path, original_width: int) -> DownloadResult:
    """Fetch a Wikimedia image by `fetch_plan`, downscale it, and store it as a new WebP file.

    `original_width` is the Commons original's width from `imageinfo`; it decides what is
    fetched and is the ceiling of what may arrive - a fetched image wider than the original is
    an upscale and is refused. The file is written with O_EXCL: an existing file is never
    replaced, so a stored image (and every row and page that points at it) cannot change
    underneath its readers. Raises `DownloadError` for every failure and `RateLimitedError` for
    a 429, which the caller retries.
    """
    import io

    from PIL import Image

    fetch_url, bucket = fetch_plan(original_url, original_width)
    try:
        resp = _download_client.get(fetch_url)
    except httpx.HTTPError as exc:
        raise DownloadError(fetch_url, f"no response ({type(exc).__name__}: {exc})") from exc

    if resp.status_code == 429:
        raise RateLimitedError(float(resp.headers.get("retry-after", 12)))
    if resp.status_code != 200:
        raise DownloadError(fetch_url, f"HTTP {resp.status_code}")
    content_type = resp.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise DownloadError(fetch_url, f"not an image ({content_type or 'no content-type'})")
    raw_bytes = resp.content
    if len(raw_bytes) < MIN_RAW_BYTES:
        raise DownloadError(fetch_url, f"only {len(raw_bytes)} bytes")
    if len(raw_bytes) > MAX_RAW_BYTES:
        raise DownloadError(fetch_url, f"{len(raw_bytes) / 1_000_000:.1f} MB is over the limit")

    Image.MAX_IMAGE_PIXELS = 200_000_000  # 200 MP - safe limit for panoramas
    try:
        with Image.open(io.BytesIO(raw_bytes)) as source:
            source.load()
            img = source
            if img.width > original_width:
                raise DownloadError(
                    fetch_url,
                    f"arrived {img.width} px wide, wider than the {original_width} px original "
                    "(an upscale, or the file changed since imageinfo was read)",
                )
            # WebP lossy has no palette mode: palette/alpha to RGBA, everything else to RGB
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            target = stored_size(img.width, img.height)
            if target != img.size:
                img = img.resize(target, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "WEBP", quality=WEBP_QUALITY, method=4)
    except DownloadError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise DownloadError(fetch_url, f"not a decodable image ({exc})") from exc

    data = buf.getvalue()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest_path.open("xb") as fh:
            fh.write(data)
    except FileExistsError as exc:
        raise DownloadError(fetch_url, f"{dest_path} exists and is never overwritten") from exc
    return DownloadResult(
        file_size=len(data),
        width=target[0],
        height=target[1],
        fetch_url=fetch_url,
        fetched_bucket=bucket,
    )


@dataclass(frozen=True)
class FailedDownload:
    """One image that could not be stored, named for the run's final report."""

    title: str
    url: str
    reason: str


def download_images_sequential(
    download_tasks: list[tuple[int, dict, str, Path, int]],
) -> tuple[list[tuple[int, dict, str, DownloadResult]], list[FailedDownload]]:
    """
    Download images one at a time with delay. Retries 429s after cooldown.
    Logs every single image so you can see progress.

    Returns (the stored images, the failures). A failure is a `DownloadError` or a 429 that
    outlasted every retry round; anything else is a bug and propagates.
    """
    total = len(download_tasks)
    results: list[tuple[int, dict, str, DownloadResult]] = []
    failures: list[FailedDownload] = []
    remaining = list(download_tasks)

    for round_num in range(1, DOWNLOAD_RETRY_ROUNDS + 1):
        if not remaining:
            break

        if round_num > 1:
            logger.info(f"  Retry round {round_num}: {len(remaining)} images...")

        failed: list[tuple[int, dict, str, Path, int]] = []
        max_retry_after = 0.0

        for task in remaining:
            idx, img, orig_url, dest_path, original_width = task
            title = img.get("title", "?")[:60]
            done = len(results) + len(failures)
            try:
                result = download_image(orig_url, dest_path, original_width)
            except RateLimitedError as e:
                max_retry_after = max(max_retry_after, e.retry_after)
                failed.append(task)
                logger.info(f"  [{done}/{total}] 429 (retry-after {e.retry_after:.0f}s)  {title}")
                continue
            except DownloadError as e:
                failures.append(FailedDownload(img.get("title", "?"), e.url, e.reason))
                logger.warning(f"  [{done + 1}/{total}] FAIL  {title}: {e}")
                time.sleep(DOWNLOAD_DELAY)
                continue
            results.append((idx, img, orig_url, result))
            logger.info(f"  [{done + 1}/{total}] OK {result.file_size / 1024:.0f}KB  {title}")
            time.sleep(DOWNLOAD_DELAY)

        remaining = failed
        if remaining:
            cooldown = max(max_retry_after, 12.0)
            logger.info(
                f"  Waiting {cooldown:.0f}s before retrying {len(remaining)} rate-limited images..."
            )
            time.sleep(cooldown)

    for task in remaining:
        logger.warning(
            f"  GAVE UP on {task[1].get('title', '?')[:60]} after {DOWNLOAD_RETRY_ROUNDS} rounds"
        )
        failures.append(
            FailedDownload(
                task[1].get("title", "?"),
                task[2],
                f"HTTP 429 in all {DOWNLOAD_RETRY_ROUNDS} rounds",
            )
        )

    return results, failures


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


def process_site(
    site: dict, dry_run: bool = False, max_per_category: int = 20, force: bool = False
) -> tuple[int, list[FailedDownload]]:
    """
    Download images for a single site from all sources:
    1. Wikipedia article images (media-list REST API)
    2. Wikidata curated images (P18, P3451, P4291, P5775)
    3. Wikimedia Commons category images (via Wikidata P373)

    Returns (the number of images stored or already registered, every image that could not be
    stored or registered - a failed download, a failed insert, a file on disk no row names).
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
        return 0, []

    # --- Source 1: Wikipedia article images ---
    all_images: list[dict] = []
    wp_images = fetch_article_images(article_title)
    time.sleep(WIKIPEDIA_DELAY)

    for img in wp_images:
        img["source_type"] = "wikipedia"
        img["_has_metadata"] = False
    all_images.extend(wp_images)

    # --- Source 2 & 3: Wikidata entity + Commons category ---
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
            cat_images = fetch_commons_category_images(commons_cat, limit=max_per_category)
            all_images.extend(cat_images)
            logger.debug(
                f"  Commons category '{commons_cat}': {len(cat_images)} images for {site_name}"
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
        return 0, []

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

    # Cap total images per site — gallery lazy-loads more from external APIs
    MAX_IMAGES_PER_SITE = 20
    if len(deduped) > MAX_IMAGES_PER_SITE:
        deduped = deduped[:MAX_IMAGES_PER_SITE]

    if dry_run:
        wp_count = sum(1 for i in deduped if i.get("source_type") == "wikipedia")
        wd_count = sum(1 for i in deduped if (i.get("source_type") or "").startswith("wikidata"))
        cc_count = sum(1 for i in deduped if i.get("source_type") == "commons_category")
        logger.info(
            f"  [DRY RUN] {site_name}: {len(deduped)} images "
            f"(wikipedia={wp_count}, wikidata={wd_count}, commons={cc_count})"
        )
        return len(deduped), []

    # --- Prepare download list and batch-fetch metadata ---
    downloaded = 0
    img_dir = site_image_dir(site_id)
    failures: list[FailedDownload] = []

    # The site's rows, --force or not: a file on disk counts as done only when one of them
    # registers it; without --force a row alone marks its image as done.
    existing_urls: set[str] = set()
    existing_filenames: set[str] = set()
    with get_session() as session:
        rows = session.execute(
            text("SELECT original_url, filename FROM wiki_images WHERE site_id = :sid"),
            {"sid": site_id},
        ).fetchall()
        for row in rows:
            if row.original_url:
                existing_urls.add(row.original_url)
            if row.filename:
                existing_filenames.add(row.filename)

    # Build local filenames, skip images already in DB, identify metadata needs
    needs_metadata: list[str] = []
    img_filenames: list[str] = []
    skip_flags: list[bool] = []
    for idx, img in enumerate(deduped):
        file_title = img["title"]
        if idx == 0:
            # Hero image always named hero.webp for predictable URLs
            local_filename = "hero.webp"
        else:
            raw_name = sanitize_filename(file_title.replace("File:", ""))
            local_filename = re.sub(r"\.[^.]+$", ".webp", raw_name)
            if not local_filename.endswith(".webp"):
                local_filename += ".webp"
        img_filenames.append(local_filename)

        # A file on disk is never fetched again, --force or not: download_image refuses to
        # overwrite one. --force only stops the database rows from counting as done. A file no
        # row of this site names - an insert that failed, a run stopped between download and
        # insert - is named as a failure: it is never replaced, and never registered by guess
        # (the image behind hero.webp can differ between two runs).
        on_disk = (img_dir / local_filename).exists()
        registered = local_filename in existing_filenames
        if on_disk and not registered:
            failures.append(
                FailedDownload(
                    file_title,
                    str(img_dir / local_filename),
                    "on disk without a wiki_images row of this site - never overwritten, "
                    "never registered by guess",
                )
            )
            skip_flags.append(True)
            continue
        orig_url = img.get("original_url") or img.get("full_url", "")
        already_done = on_disk or (not force and (registered or orig_url in existing_urls))
        skip_flags.append(already_done)

        if already_done:
            downloaded += 1
        elif not img.get("_has_metadata"):
            needs_metadata.append(file_title)

    # Batch-fetch metadata in chunks of 50 (only for images we'll actually download)
    batch_metadata: dict[str, dict] = {}
    for chunk_start in range(0, len(needs_metadata), 50):
        chunk = needs_metadata[chunk_start : chunk_start + 50]
        batch_result = fetch_image_metadata_batch(chunk)
        batch_metadata.update(batch_result)
        time.sleep(WIKIPEDIA_DELAY)

    # Build download tasks (skip already-downloaded)
    download_tasks: list[tuple[int, dict, str, Path, int]] = []
    for idx, img in enumerate(deduped):
        if skip_flags[idx]:
            continue

        local_filename = img_filenames[idx]
        dest_path = img_dir / local_filename
        file_title = img["title"]
        normalized_title = file_title if file_title.startswith("File:") else f"File:{file_title}"

        if img.get("_has_metadata"):
            meta = {
                "original_url": img.get("original_url"),
                "width": img.get("width"),
            }
        else:
            meta = batch_metadata.get(normalized_title, {})

        original_url = (
            meta.get("original_url") or img.get("original_url") or img.get("full_url", "")
        )

        # The original's width decides what is fetched (download_image). A title the metadata
        # batch did not answer has none, and download_image refuses it by name.
        download_tasks.append((idx, img, original_url, dest_path, meta.get("width")))

    skipped = sum(skip_flags)
    if skipped:
        logger.debug(
            f"  {site_name}: skipped {skipped} already-downloaded, {len(download_tasks)} to download"
        )

    if not download_tasks:
        return downloaded, failures

    # Download images sequentially (avoids Wikimedia 429s)
    logger.info(f"  Downloading {len(download_tasks)} images for {site_name}...")
    dl_results, dl_failures = download_images_sequential(download_tasks)
    failures.extend(dl_failures)

    # Insert results into database
    for idx, img, original_url, result in dl_results:
        local_filename = img_filenames[idx]
        file_title = img["title"]
        normalized_title = file_title if file_title.startswith("File:") else f"File:{file_title}"
        is_hero = idx == 0
        source_type = img.get("source_type", "wikimedia")

        # Get metadata from batch results or inline
        if img.get("_has_metadata"):
            meta = img
        else:
            meta = batch_metadata.get(normalized_title, {})

        try:
            with get_session() as session:
                wiki_img = WikiImage(
                    site_id=site_id,
                    filename=local_filename,
                    original_url=original_url,
                    commons_page_url=img.get("commons_page_url"),
                    thumb_width=result.fetched_bucket,
                    author=meta.get("author") or img.get("author"),
                    author_url=meta.get("author_url") or img.get("author_url"),
                    license=meta.get("license") or img.get("license"),
                    license_url=meta.get("license_url") or img.get("license_url"),
                    title=img.get("display_title"),
                    is_hero=is_hero,
                    is_lead=img.get("is_lead", False),
                    sort_order=idx,
                    source_type=source_type,
                    file_size_bytes=result.file_size,
                    width=result.width,
                    height=result.height,
                )
                session.add(wiki_img)
                session.commit()
        except SQLAlchemyError as exc:
            # The one expected refusal: this site already has a row for this original.
            if not (isinstance(exc, IntegrityError) and "uq_wiki_image_site_url" in str(exc)):
                failures.append(
                    FailedDownload(
                        file_title,
                        original_url,
                        f"stored as {img_dir / local_filename}, but its wiki_images row was not "
                        f"written ({type(exc).__name__}: {str(exc).splitlines()[0]})",
                    )
                )
                continue
        downloaded += 1

        # Update unified_sites.thumbnail_url to local hero image path
        # Runs after an insert (new or duplicate) - never for a file whose row failed
        if is_hero:
            local_path = f"/data/images/wiki/{site_id[:8]}/{local_filename}"
            with get_session() as session:
                session.execute(
                    text("UPDATE unified_sites SET thumbnail_url = :url WHERE id = :sid"),
                    {"url": local_path, "sid": site_id},
                )
                session.commit()

    return downloaded, failures


def run_downloader(
    source_filter: str | None = None,
    site_id: str | None = None,
    dry_run: bool = False,
    stats_only: bool = False,
    force: bool = False,
    max_per_category: int = 20,
) -> list[FailedDownload]:
    """Main entry point for the wiki image downloader. Always sequential.

    Returns every image that could not be stored; `main` exits non-zero and names each one.
    """
    if stats_only:
        print_stats()
        return []

    sites = get_sites_to_process(source_filter, site_id)
    logger.info(f"Found {len(sites)} sites to process")
    if force:
        logger.info("--force enabled: re-processing sites even if they already have images")

    # Filter out already-downloaded sites upfront (unless --force)
    if not dry_run and not force:
        to_process = []
        total_skipped = 0
        for site in sites:
            if site_already_downloaded(site["id"]):
                total_skipped += 1
            else:
                to_process.append(site)
        logger.info(
            f"Skipped {total_skipped} sites already downloaded, {len(to_process)} remaining"
        )
    else:
        to_process = sites
        total_skipped = 0

    total_downloaded = 0
    all_failures: list[FailedDownload] = []

    # No site-level catch: an error that is not a named image failure is a bug, and it stops the
    # run with its traceback instead of a warning and an exit 0.
    for i, site in enumerate(to_process):
        count, failures = process_site(
            site, dry_run=dry_run, max_per_category=max_per_category, force=force
        )
        total_downloaded += count
        all_failures.extend(failures)
        if count > 0:
            logger.info(f"  [{i + 1}/{len(to_process)}] {site['name']}: {count} images")

    logger.info("=" * 60)
    logger.info("Download complete:")
    logger.info(f"  Sites processed: {len(to_process)}")
    logger.info(f"  Sites skipped (already done): {total_skipped}")
    logger.info(f"  Images downloaded: {total_downloaded}")
    logger.info(f"  Images that could not be stored: {len(all_failures)}")
    return all_failures


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
        default=20,
        help="Max images to fetch from Commons category per site (default: 20)",
    )
    args = parser.parse_args()

    failures = run_downloader(
        source_filter=args.source,
        site_id=args.site_id,
        dry_run=args.dry_run,
        stats_only=args.stats,
        force=args.force,
        max_per_category=args.max_per_category,
    )
    if failures:
        for failure in failures:
            logger.error(f"NOT STORED  {failure.title}: {failure.reason} ({failure.url})")
        raise SystemExit(f"{len(failures)} image(s) could not be stored - listed above")


if __name__ == "__main__":
    main()
