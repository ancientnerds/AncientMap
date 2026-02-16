"""
Shared Wikimedia entity resolver.

Resolves archaeological site names to Wikidata entities (QIDs) and extracts
Commons categories, main images, and video filenames. Used by both
WikidataConnector and WikimediaConnector for precise content discovery.

Resolution strategies (tried in order):
1. Extract QID directly from source_url if it's a Wikidata URL (0 API calls)
2. Extract Wikipedia article title from source_url if Wikipedia URL (1 API call)
3. site_name -> Wikipedia opensearch -> article -> QID (2 API calls)

After getting QID: fetch wbgetentities claims -> extract P373, P18, P10.
"""

import re
from dataclasses import dataclass, field

import httpx
from loguru import logger

from pipeline.connectors.cache import MemoryCache

# User-Agent per Wikimedia policy
_HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}

_WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
_WIKIDATA_API = "https://www.wikidata.org/w/api.php"

_QID_RE = re.compile(r"wikidata\.org/(?:entity|wiki)/(Q\d+)")
_WIKI_ARTICLE_RE = re.compile(r"(?:\w+)\.wikipedia\.org/wiki/(.+?)(?:#.*)?$")


@dataclass
class ResolvedEntity:
    """Result of resolving a site name to a Wikidata entity."""

    qid: str
    commons_category: str | None = None  # P373
    main_image: str | None = None  # P18
    video_filenames: list[str] = field(default_factory=list)  # P10
    article_title: str | None = None


# Module-level cache shared between WikidataConnector and WikimediaConnector
_cache = MemoryCache(max_size=500)
_CACHE_TTL = 3600  # 1 hour


def extract_qid_from_url(url: str) -> str | None:
    """Extract QID from a Wikidata entity URL."""
    m = _QID_RE.search(url)
    return m.group(1) if m else None


def extract_article_from_wikipedia_url(url: str) -> str | None:
    """Extract article title from a Wikipedia URL."""
    m = _WIKI_ARTICLE_RE.search(url)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1)).replace("_", " ")
    return None


class WikimediaResolver:
    """
    Resolves site names / source URLs to Wikidata entities.

    Shared singleton instance (_resolver) is used by both Wiki* connectors.
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._http_client = http_client
        self._owns_client = http_client is None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
            self._owns_client = True
        return self._http_client

    async def resolve(
        self, site_name: str, source_url: str | None = None
    ) -> ResolvedEntity | None:
        """
        Resolve a site name (and optional source URL) to a Wikidata entity.

        Returns cached result if available.
        """
        cache_key = f"wm_resolve:{site_name}"
        cached = _cache.get(cache_key)
        if cached is not None:
            logger.debug(f"WikimediaResolver cache hit for '{site_name}'")
            return cached

        entity = await self._resolve_uncached(site_name, source_url)
        if entity:
            _cache.set(cache_key, entity, _CACHE_TTL)
        return entity

    async def _resolve_uncached(
        self, site_name: str, source_url: str | None
    ) -> ResolvedEntity | None:
        """Run the resolution chain without cache."""
        qid: str | None = None
        article_title: str | None = None

        # Strategy 1: Extract QID directly from Wikidata URL
        if source_url:
            qid = extract_qid_from_url(source_url)
            if qid:
                logger.debug(f"WikimediaResolver: QID {qid} extracted from URL")

        # Strategy 2: Extract article title from Wikipedia URL -> resolve to QID
        if not qid and source_url:
            article_title = extract_article_from_wikipedia_url(source_url)
            if article_title:
                qid = await self._resolve_qid(article_title)
                if qid:
                    logger.debug(
                        f"WikimediaResolver: QID {qid} via Wikipedia article '{article_title}'"
                    )

        # Strategy 3: opensearch -> article -> QID
        if not qid:
            article_title = await self._resolve_article_title(site_name)
            if article_title:
                qid = await self._resolve_qid(article_title)

        if not qid:
            return None

        # Fetch entity claims
        claims = await self._fetch_claims(qid)
        if claims is None:
            return None

        commons_category = _get_string_value(claims, "P373")
        main_image = _get_string_value(claims, "P18")

        video_filenames: list[str] = []
        for claim in claims.get("P10", []):
            filename = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if filename:
                video_filenames.append(filename)

        entity = ResolvedEntity(
            qid=qid,
            commons_category=commons_category,
            main_image=main_image,
            video_filenames=video_filenames,
            article_title=article_title,
        )
        logger.info(
            f"WikimediaResolver: '{site_name}' -> {qid}"
            f" (category={commons_category}, videos={len(video_filenames)})"
        )
        return entity

    # =========================================================================
    # API calls (extracted from WikidataConnector)
    # =========================================================================

    async def _resolve_article_title(self, site_name: str) -> str | None:
        """Resolve site_name to a Wikipedia article title via opensearch."""
        params = {
            "action": "opensearch",
            "search": site_name,
            "limit": "1",
            "namespace": "0",
            "format": "json",
        }
        try:
            resp = await self.http_client.get(
                _WIKIPEDIA_API, params=params, headers=_HEADERS
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            titles = data[1] if len(data) > 1 else []
            return titles[0] if titles else None
        except Exception as e:
            logger.debug(f"WikimediaResolver opensearch failed for '{site_name}': {e}")
            return None

    async def _resolve_qid(self, article_title: str) -> str | None:
        """Resolve Wikipedia article title to Wikidata QID via pageprops."""
        params = {
            "action": "query",
            "titles": article_title.replace(" ", "_"),
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "format": "json",
        }
        try:
            resp = await self.http_client.get(
                _WIKIPEDIA_API, params=params, headers=_HEADERS
            )
            if resp.status_code != 200:
                return None
            pages = resp.json().get("query", {}).get("pages", {})
            page: dict = next(iter(pages.values()), {})
            return page.get("pageprops", {}).get("wikibase_item")
        except Exception as e:
            logger.debug(f"WikimediaResolver QID lookup failed for '{article_title}': {e}")
            return None

    async def _fetch_claims(self, qid: str) -> dict | None:
        """Fetch entity claims from Wikidata."""
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "claims",
            "format": "json",
        }
        try:
            resp = await self.http_client.get(
                _WIKIDATA_API, params=params, headers=_HEADERS
            )
            if resp.status_code != 200:
                return None
            entity = resp.json().get("entities", {}).get(qid, {})
            return entity.get("claims", {})
        except Exception as e:
            logger.debug(f"WikimediaResolver entity fetch failed for {qid}: {e}")
            return None


# =========================================================================
# Helpers
# =========================================================================


def _get_string_value(claims: dict, prop_id: str) -> str | None:
    """Extract a string value from a Wikidata claim."""
    claim_list = claims.get(prop_id, [])
    if claim_list:
        snak = claim_list[0].get("mainsnak", {})
        return snak.get("datavalue", {}).get("value")
    return None


# Module-level singleton — both connectors share this instance
_resolver = WikimediaResolver()
