"""
Internet Archive Connector.

Source #22 from research paper.
Protocol: REST
Auth: None
License: Varies
Priority: P1

API: https://archive.org/developers/
"""


from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.connectors.registry import ConnectorRegistry
from pipeline.connectors.types import AuthType, ContentItem, ContentType, ProtocolType


@ConnectorRegistry.register
class InternetArchiveConnector(BaseConnector):
    """Internet Archive connector for books and documents."""

    connector_id = "internet_archive"
    connector_name = "Internet Archive"
    description = "Digital library of books, movies, music, and more"

    content_types = [ContentType.BOOK, ContentType.DOCUMENT, ContentType.PHOTO]

    base_url = "https://archive.org"
    protocol = ProtocolType.REST
    rate_limit = 5.0
    requires_auth = False
    auth_type = AuthType.NONE

    license = "Varies"
    attribution = "Internet Archive"

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self.rest = RestProtocol(base_url=self.base_url, rate_limit=self.rate_limit)

    async def search(
        self,
        query: str,
        content_type: ContentType | None = None,
        limit: int = 20,
        offset: int = 0,
        **kwargs,
    ) -> list[ContentItem]:
        """Search Internet Archive."""
        try:
            # Build mediatype filter
            mediatype = "texts"
            if content_type == ContentType.PHOTO:
                mediatype = "image"
            elif content_type == ContentType.BOOK:
                mediatype = "texts"

            params = {
                "q": f"{query} AND mediatype:{mediatype}",
                "output": "json",
                "rows": limit,
                "page": offset // limit + 1 if limit > 0 else 1,
            }

            response = await self.rest.get("/advancedsearch.php", params=params)

            if not response or "response" not in response:
                return []

            items = []
            for doc in response.get("response", {}).get("docs", []):
                try:
                    identifier = doc.get("identifier", "")

                    # Determine content type from mediatype
                    doc_mediatype = doc.get("mediatype", "texts")
                    ct = ContentType.BOOK
                    if doc_mediatype == "image":
                        ct = ContentType.PHOTO

                    item = ContentItem(
                        id=f"internet_archive:{identifier}",
                        source=self.connector_id,
                        content_type=ct,
                        title=doc.get("title", "Unknown"),
                        description=doc.get("description"),
                        url=f"https://archive.org/details/{identifier}",
                        thumbnail_url=f"https://archive.org/services/img/{identifier}",
                        creator=doc.get("creator", [""])[0] if isinstance(doc.get("creator"), list) else doc.get("creator"),
                        date=doc.get("date"),
                        license=doc.get("licenseurl", self.license),
                        attribution=self.attribution,
                        raw_data=doc,
                    )
                    items.append(item)
                except Exception as e:
                    logger.debug(f"Failed to parse Internet Archive item: {e}")

            return items

        except Exception as e:
            logger.error(f"Internet Archive search failed: {e}")
            return []

    async def get_item(self, item_id: str) -> ContentItem | None:
        """Get specific item by identifier."""
        try:
            if item_id.startswith("internet_archive:"):
                item_id = item_id[17:]

            response = await self.rest.get(f"/metadata/{item_id}")

            if not response or "metadata" not in response:
                return None

            metadata = response.get("metadata", {})

            return ContentItem(
                id=f"internet_archive:{item_id}",
                source=self.connector_id,
                content_type=ContentType.BOOK,
                title=metadata.get("title", "Unknown"),
                description=metadata.get("description"),
                url=f"https://archive.org/details/{item_id}",
                thumbnail_url=f"https://archive.org/services/img/{item_id}",
                creator=metadata.get("creator"),
                date=metadata.get("date"),
                license=metadata.get("licenseurl", self.license),
                attribution=self.attribution,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to get Internet Archive item {item_id}: {e}")
            return None
