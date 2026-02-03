"""
IIIF Protocol Handler.

Provides access to IIIF (International Image Interoperability Framework) services:
- Image API: Request images at different sizes/regions
- Presentation API: Access manifests with metadata
- Used by many museums and digital libraries
"""

import asyncio
from typing import Any

import httpx
from loguru import logger


class IIIFProtocol:
    """
    IIIF protocol handler.

    Supports:
    - Image API v2/v3 for image retrieval
    - Presentation API v2/v3 for manifests
    - Content Search API for annotations
    """

    def __init__(
        self,
        timeout: float = 30.0,
        rate_limit: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize IIIF protocol handler.

        Args:
            timeout: Request timeout
            rate_limit: Max requests per second
            http_client: Optional shared HTTP client
        """
        self.timeout = timeout
        self.rate_limit = rate_limit

        self._http_client = http_client
        self._owns_client = http_client is None
        self._last_request_time: float | None = None
        self._request_lock = asyncio.Lock()

    async def __aenter__(self):
        if self._owns_client and self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owns_client and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
            self._owns_client = True
        return self._http_client

    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        if self.rate_limit <= 0:
            return

        async with self._request_lock:
            if self._last_request_time is not None:
                elapsed = asyncio.get_event_loop().time() - self._last_request_time
                min_interval = 1.0 / self.rate_limit
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)

            self._last_request_time = asyncio.get_event_loop().time()

    # =========================================================================
    # Image API
    # =========================================================================

    def build_image_url(
        self,
        base_url: str,
        region: str = "full",
        size: str = "max",
        rotation: int = 0,
        quality: str = "default",
        format: str = "jpg",
    ) -> str:
        """
        Build IIIF Image API URL.

        Args:
            base_url: Base image URL (e.g., "https://example.com/iiif/image1")
            region: Region selector (full, square, x,y,w,h, pct:x,y,w,h)
            size: Size selector (max, w,, ,h, pct:n, w,h, !w,h)
            rotation: Rotation in degrees (0-360)
            quality: Quality (default, color, gray, bitonal)
            format: Output format (jpg, png, gif, webp)

        Returns:
            Complete IIIF image URL
        """
        base = base_url.rstrip("/")
        return f"{base}/{region}/{size}/{rotation}/{quality}.{format}"

    def get_thumbnail_url(
        self,
        base_url: str,
        width: int = 400,
        height: int | None = None,
    ) -> str:
        """
        Get URL for a thumbnail image.

        Args:
            base_url: Base image URL
            width: Desired width
            height: Desired height (optional, maintains aspect ratio)

        Returns:
            Thumbnail URL
        """
        if height:
            size = f"!{width},{height}"
        else:
            size = f"{width},"

        return self.build_image_url(base_url, size=size)

    async def get_image_info(self, info_url: str) -> dict[str, Any]:
        """
        Get IIIF image info.json.

        Args:
            info_url: URL to info.json (or base image URL)

        Returns:
            Image info dictionary
        """
        await self._rate_limit()

        # Ensure URL ends with /info.json
        if not info_url.endswith("/info.json"):
            info_url = info_url.rstrip("/") + "/info.json"

        try:
            response = await self.client.get(
                info_url,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"IIIF info.json error: {e}")
            raise

    # =========================================================================
    # Presentation API
    # =========================================================================

    async def get_manifest(self, manifest_url: str) -> dict[str, Any]:
        """
        Get IIIF Presentation manifest.

        Args:
            manifest_url: URL to manifest.json

        Returns:
            Manifest dictionary
        """
        await self._rate_limit()

        try:
            response = await self.client.get(
                manifest_url,
                headers={
                    "Accept": "application/ld+json;profile=\"http://iiif.io/api/presentation/3/context.json\",application/json",
                },
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"IIIF manifest error: {e}")
            raise

    async def get_collection(self, collection_url: str) -> dict[str, Any]:
        """
        Get IIIF Collection.

        Args:
            collection_url: URL to collection.json

        Returns:
            Collection dictionary
        """
        await self._rate_limit()

        try:
            response = await self.client.get(
                collection_url,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"IIIF collection error: {e}")
            raise

    def extract_images_from_manifest(
        self,
        manifest: dict[str, Any],
        max_images: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Extract image info from a IIIF manifest.

        Handles both Presentation API v2 and v3.

        Args:
            manifest: Manifest dictionary
            max_images: Maximum images to extract

        Returns:
            List of image info dictionaries
        """
        images = []

        # Detect API version
        context = manifest.get("@context", "")
        if isinstance(context, list):
            context = " ".join(context)

        is_v3 = "presentation/3" in context

        if is_v3:
            images = self._extract_v3_images(manifest, max_images)
        else:
            images = self._extract_v2_images(manifest, max_images)

        return images

    def _extract_v2_images(
        self,
        manifest: dict[str, Any],
        max_images: int,
    ) -> list[dict[str, Any]]:
        """Extract images from Presentation API v2 manifest."""
        images = []

        sequences = manifest.get("sequences", [])
        for sequence in sequences:
            canvases = sequence.get("canvases", [])
            for canvas in canvases:
                if len(images) >= max_images:
                    break

                # Get canvas metadata
                label = self._get_label(canvas.get("label"))

                # Get image from canvas
                canvas_images = canvas.get("images", [])
                for img in canvas_images:
                    resource = img.get("resource", {})
                    service = resource.get("service", {})

                    # Get IIIF image service URL
                    if isinstance(service, list):
                        service = service[0] if service else {}

                    service_id = service.get("@id", "")
                    if not service_id:
                        # Fall back to direct image URL
                        service_id = resource.get("@id", "")

                    if service_id:
                        images.append({
                            "id": canvas.get("@id"),
                            "label": label,
                            "width": canvas.get("width"),
                            "height": canvas.get("height"),
                            "service_url": service_id,
                            "thumbnail_url": self.get_thumbnail_url(service_id, 400),
                            "full_url": self.build_image_url(service_id),
                        })
                        break

        return images

    def _extract_v3_images(
        self,
        manifest: dict[str, Any],
        max_images: int,
    ) -> list[dict[str, Any]]:
        """Extract images from Presentation API v3 manifest."""
        images = []

        items = manifest.get("items", [])
        for canvas in items:
            if len(images) >= max_images:
                break

            if canvas.get("type") != "Canvas":
                continue

            label = self._get_label(canvas.get("label"))

            # Navigate to annotation page
            annotation_pages = canvas.get("items", [])
            for page in annotation_pages:
                annotations = page.get("items", [])
                for annotation in annotations:
                    if annotation.get("motivation") != "painting":
                        continue

                    body = annotation.get("body", {})
                    if isinstance(body, list):
                        body = body[0] if body else {}

                    # Get service URL
                    service = body.get("service", [])
                    if isinstance(service, list):
                        service = service[0] if service else {}

                    service_id = service.get("id", service.get("@id", ""))
                    if not service_id:
                        service_id = body.get("id", "")

                    if service_id:
                        images.append({
                            "id": canvas.get("id"),
                            "label": label,
                            "width": canvas.get("width"),
                            "height": canvas.get("height"),
                            "service_url": service_id,
                            "thumbnail_url": self.get_thumbnail_url(service_id, 400),
                            "full_url": self.build_image_url(service_id),
                        })
                        break

        return images

    def _get_label(self, label: Any) -> str:
        """Extract label string from IIIF label (handles i18n)."""
        if label is None:
            return ""

        if isinstance(label, str):
            return label

        if isinstance(label, dict):
            # IIIF v3 language map
            for lang in ["en", "none", ""]:
                if lang in label:
                    values = label[lang]
                    return values[0] if isinstance(values, list) else values
            # Return first available
            for values in label.values():
                return values[0] if isinstance(values, list) else values

        if isinstance(label, list):
            # IIIF v2 array
            if label and isinstance(label[0], dict):
                return label[0].get("@value", "")
            return label[0] if label else ""

        return str(label)

    def extract_metadata_from_manifest(
        self,
        manifest: dict[str, Any],
    ) -> dict[str, str]:
        """
        Extract metadata from manifest.

        Args:
            manifest: Manifest dictionary

        Returns:
            Dictionary of metadata key-value pairs
        """
        metadata = {}

        # Get label
        metadata["label"] = self._get_label(manifest.get("label"))

        # Get description/summary
        description = manifest.get("description") or manifest.get("summary")
        if description:
            metadata["description"] = self._get_label(description)

        # Get attribution
        attribution = manifest.get("attribution") or manifest.get("requiredStatement")
        if attribution:
            if isinstance(attribution, dict):
                metadata["attribution"] = self._get_label(attribution.get("value"))
            else:
                metadata["attribution"] = self._get_label(attribution)

        # Get license
        license_url = manifest.get("license") or manifest.get("rights")
        if license_url:
            if isinstance(license_url, list):
                license_url = license_url[0]
            metadata["license_url"] = license_url

        # Get structured metadata
        manifest_metadata = manifest.get("metadata", [])
        for item in manifest_metadata:
            label = self._get_label(item.get("label"))
            value = self._get_label(item.get("value"))
            if label and value:
                metadata[label.lower().replace(" ", "_")] = value

        return metadata
