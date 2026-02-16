"""
Wikidata Connector.

Discovers videos (P10) and papers (P373 -> Commons PDFs/DjVu) for archaeological sites
by resolving site names through Wikipedia -> Wikidata -> Commons.

API flow:
1. site_name -> Wikipedia opensearch -> article title
2. article title -> Wikipedia pageprops -> Wikidata QID
3. QID -> wbgetentities -> claims (P10 for video, P373 for Commons category)
4. P10 filename -> Commons imageinfo -> video URL + thumbnail
5. P373 category -> Commons categorymembers -> PDF/DjVu files
"""

import re
import urllib.parse

from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType

# User-Agent per Wikimedia policy
_HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}

_WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
_WIKIDATA_API = "https://www.wikidata.org/w/api.php"
_COMMONS_API = "https://commons.wikimedia.org/w/api.php"

_PAPER_EXT = re.compile(r"\.(pdf|djvu)$", re.IGNORECASE)


@ConnectorRegistry.register
class WikidataConnector(BaseConnector):
    """
    Wikidata connector for videos and papers.

    Resolves archaeological site names to Wikidata entities and extracts:
    - P10 (video) -> Commons-hosted .ogv/.webm clips
    - P373 (Commons category) -> PDF/DjVu academic papers
    """

    connector_id = "wikidata"
    connector_name = "Wikidata"
    description = "Videos and papers from Wikidata entities via Wikimedia Commons"

    content_types = [ContentType.VIDEO, ContentType.PAPER]

    base_url = "https://www.wikidata.org/w/api.php"
    website_url = "https://www.wikidata.org"
    protocol = ProtocolType.REST
    rate_limit = 2.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Various CC licenses"
    attribution = "Wikimedia Commons via Wikidata"

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search by site name — delegates to get_by_site."""
        if not query.strip():
            return []
        return await self.get_by_site(site_name=query, content_type=content_type, limit=limit)

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Not applicable — items are discovered via site resolution."""
        return None

    async def get_by_site(
        self,
        site_name: str,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        content_type: ContentType | None = None,
        limit: int = 20,
        **kwargs,
    ) -> list[ContentItem]:
        """
        Resolve site_name -> Wikipedia -> Wikidata -> videos + papers.
        """
        if not site_name.strip():
            return []

        items: list[ContentItem] = []

        # Step 1: Resolve site name to Wikipedia article title
        article_title = await self._resolve_article_title(site_name)
        if not article_title:
            return []

        # Step 2: Resolve article to Wikidata QID
        qid = await self._resolve_qid(article_title)
        if not qid:
            return []

        # Step 3: Fetch entity claims
        claims = await self._fetch_claims(qid)
        if not claims:
            return []

        # Step 4: Extract P10 video (if requested or no filter)
        if content_type is None or content_type == ContentType.VIDEO:
            video_items = await self._extract_videos(claims, qid)
            items.extend(video_items)

        # Step 5: Extract P373 Commons category -> papers (if requested or no filter)
        if content_type is None or content_type == ContentType.PAPER:
            commons_cat = self._get_string_value(claims, "P373")
            if commons_cat:
                paper_items = await self._fetch_category_papers(commons_cat, limit)
                items.extend(paper_items)

        logger.info(f"Wikidata: {len(items)} items for '{site_name}' (QID={qid})")
        return items[:limit]

    # =========================================================================
    # Resolution chain
    # =========================================================================

    async def _resolve_article_title(self, site_name: str) -> str | None:
        """Resolve site_name to a Wikipedia article title via opensearch."""
        await self._rate_limit()
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
            # opensearch returns [query, [titles], [descriptions], [urls]]
            titles = data[1] if len(data) > 1 else []
            return titles[0] if titles else None
        except Exception as e:
            logger.debug(f"Wikidata opensearch failed for '{site_name}': {e}")
            return None

    async def _resolve_qid(self, article_title: str) -> str | None:
        """Resolve Wikipedia article title to Wikidata QID via pageprops."""
        await self._rate_limit()
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
            logger.debug(f"Wikidata QID lookup failed for '{article_title}': {e}")
            return None

    async def _fetch_claims(self, qid: str) -> dict | None:
        """Fetch entity claims from Wikidata."""
        await self._rate_limit()
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
            logger.debug(f"Wikidata entity fetch failed for {qid}: {e}")
            return None

    # =========================================================================
    # Video extraction (P10)
    # =========================================================================

    async def _extract_videos(self, claims: dict, qid: str) -> list[ContentItem]:
        """Extract P10 (video) filenames and resolve to Commons URLs."""
        items: list[ContentItem] = []
        p10_claims = claims.get("P10", [])

        for claim in p10_claims:
            filename = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if not filename:
                continue

            video_item = await self._resolve_commons_video(filename, qid)
            if video_item:
                items.append(video_item)

        return items

    async def _resolve_commons_video(
        self, filename: str, qid: str
    ) -> ContentItem | None:
        """Resolve a Commons filename to a video ContentItem with thumbnail."""
        await self._rate_limit()
        encoded_name = filename.replace(" ", "_")
        params = {
            "action": "query",
            "titles": f"File:{encoded_name}",
            "prop": "imageinfo|videoinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": "400",  # Get a thumbnail even for video
            "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
            "viprop": "derivatives",
            "format": "json",
        }
        try:
            resp = await self.http_client.get(
                _COMMONS_API, params=params, headers=_HEADERS
            )
            if resp.status_code != 200:
                return None
            pages = resp.json().get("query", {}).get("pages", {})
            page: dict = next(iter(pages.values()), {})
            info_list = page.get("imageinfo", [])
            if not info_list:
                return None
            info = info_list[0]

            original_url = info.get("url")
            thumb_url = info.get("thumburl") or original_url
            if not original_url:
                return None

            # Prefer .webm transcode for browser compatibility (Ogg Theora is poorly supported)
            media_url = original_url
            videoinfo = page.get("videoinfo", [])
            if videoinfo:
                derivatives = videoinfo[0].get("derivatives", [])
                webm_url = self._pick_best_webm(derivatives)
                if webm_url:
                    media_url = webm_url

            ext = info.get("extmetadata", {})
            artist_raw = ext.get("Artist", {}).get("value", "")
            artist = re.sub(r"<[^>]*>", "", artist_raw).strip() if artist_raw else None
            license_name = ext.get("LicenseShortName", {}).get("value")
            license_url = ext.get("LicenseUrl", {}).get("value")

            display_title = filename.rsplit(".", 1)[0]
            page_url = f"https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(encoded_name, safe='')}"

            return ContentItem(
                id=f"wikidata-video-{qid}-{encoded_name}",
                source=self.connector_id,
                content_type=ContentType.VIDEO,
                title=display_title,
                url=page_url,
                thumbnail_url=thumb_url,
                media_url=media_url,
                creator=artist,
                license=license_name,
                license_url=license_url,
                attribution=f"{artist or 'Unknown'} via Wikimedia Commons",
            )
        except Exception as e:
            logger.debug(f"Commons video resolve failed for '{filename}': {e}")
            return None

    @staticmethod
    def _pick_best_webm(derivatives: list[dict]) -> str | None:
        """Pick the best .webm transcode from Commons derivatives."""
        best_url: str | None = None
        best_score = -1

        for d in derivatives:
            d_type = d.get("type", "")
            if "webm" not in d_type:
                continue
            src = d.get("src", "")
            if not src:
                continue

            score = 0
            if "vp9" in d_type:
                score += 10000
            m = re.search(r"(\d+)p\.", src)
            if m:
                score += min(int(m.group(1)), 720)

            if score > best_score:
                best_score = score
                best_url = src

        if best_url and best_url.startswith("//"):
            best_url = f"https:{best_url}"

        return best_url

    # =========================================================================
    # Paper extraction (P373 -> Commons category -> PDFs)
    # =========================================================================

    async def _fetch_category_papers(
        self, category_name: str, limit: int = 20
    ) -> list[ContentItem]:
        """Fetch PDF/DjVu files from a Commons category."""
        await self._rate_limit()
        items: list[ContentItem] = []
        gcmcontinue = None

        while len(items) < limit:
            params = {
                "action": "query",
                "generator": "categorymembers",
                "gcmtitle": f"Category:{category_name}",
                "gcmtype": "file",
                "gcmlimit": str(min(50, limit - len(items))),
                "prop": "imageinfo",
                "iiprop": "url|size|extmetadata",
                "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
                "format": "json",
            }
            if gcmcontinue:
                params["gcmcontinue"] = gcmcontinue

            try:
                resp = await self.http_client.get(
                    _COMMONS_API, params=params, headers=_HEADERS
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
            except Exception as e:
                logger.debug(f"Commons category error for {category_name}: {e}")
                break

            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                paper = self._parse_commons_paper(page)
                if paper:
                    items.append(paper)

            cont = data.get("continue", {})
            gcmcontinue = cont.get("gcmcontinue")
            if not gcmcontinue:
                break

            await self._rate_limit()

        return items[:limit]

    def _parse_commons_paper(self, page: dict) -> ContentItem | None:
        """Parse a Commons API page result for a PDF/DjVu into a ContentItem."""
        file_title = page.get("title", "")
        if not file_title or not _PAPER_EXT.search(file_title):
            return None

        info_list = page.get("imageinfo", [])
        media_url = info_list[0].get("url") if info_list else None
        if not media_url:
            return None

        # Clean title: "File:Pompei (IA pompeiscene00confiala).pdf" -> "Pompei"
        clean = file_title.replace("File:", "").rsplit(".", 1)[0]
        clean = re.sub(r"\s*\(IA\s+\w+\)\s*$", "", clean).strip()

        encoded_title = urllib.parse.quote(file_title, safe="")
        page_url = f"https://commons.wikimedia.org/wiki/{encoded_title}"

        return ContentItem(
            id=f"wikidata-paper-{encoded_title}",
            source=self.connector_id,
            content_type=ContentType.PAPER,
            title=clean or file_title,
            url=page_url,
            media_url=media_url,
            attribution="Wikimedia Commons",
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _get_string_value(claims: dict, prop_id: str) -> str | None:
        """Extract a string value from a Wikidata claim."""
        claim_list = claims.get(prop_id, [])
        if claim_list:
            snak = claim_list[0].get("mainsnak", {})
            return snak.get("datavalue", {}).get("value")
        return None
