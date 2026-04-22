"""Federated search + download for probative images.

Fans out a single search query across the existing ConnectorRegistry imagery
and museums adapters, flattens the results into a uniform ImageCandidate type,
deduplicates by URL, caps per-source, and exposes a save-to-disk helper used
by the probative-images handler.

Verified against the actual codebase (2026-04-18):
- ConnectorRegistry.get_all() returns list[BaseConnector], not a dict.
  Individual lookup uses ConnectorRegistry.get(connector_id).
- connector.search() is an async method — no asyncio.to_thread needed.
- ContentItem uses `creator` (not `artist`) and `raw_data` (confirmed).
- Actual connector IDs: "wikimedia", "met_museum", "loc", "europeana",
  "getty_museum", "louvre", "pas".
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ImageCandidate:
    url: str
    source: str  # connector id: "wikimedia", "met_museum", "loc", ...
    title: str
    description: str = ""
    artist: str = ""
    license: str = ""
    license_url: str = ""
    thumbnail_url: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for storage in ResearchState.image_candidate_pool."""
        from dataclasses import asdict

        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ImageCandidate:
        """Reconstruct from serialized form. Unknown keys ignored."""
        fields = {
            "url",
            "source",
            "title",
            "description",
            "artist",
            "license",
            "license_url",
            "thumbnail_url",
            "metadata",
        }
        return cls(**{k: v for k, v in d.items() if k in fields})


def deduplicate_candidates(cands: list[ImageCandidate]) -> list[ImageCandidate]:
    """Keep first occurrence per URL."""
    seen: set[str] = set()
    out: list[ImageCandidate] = []
    for c in cands:
        if c.url in seen:
            continue
        seen.add(c.url)
        out.append(c)
    return out


def select_top_per_connector(
    cands: list[ImageCandidate],
    per_source: int = 3,
) -> list[ImageCandidate]:
    """Cap the number of candidates returned per source, preserving input order."""
    counts: dict[str, int] = {}
    out: list[ImageCandidate] = []
    for c in cands:
        n = counts.get(c.source, 0)
        if n >= per_source:
            continue
        counts[c.source] = n + 1
        out.append(c)
    return out


# Verified connector IDs from pipeline/connectors/imagery/ and museums/.
# Only IDs that exist in the registry are listed here.
_IMAGERY_CONNECTORS: tuple[str, ...] = (
    "wikimedia",
    "met_museum",
    "loc",
    "europeana",
    "getty_museum",
    "louvre",
    "pas",
)


def _item_to_candidate(item: object, connector_id: str) -> ImageCandidate:
    """Convert a ContentItem to an ImageCandidate.

    ContentItem fields (from pipeline/connectors/types.py):
      url, title, description, thumbnail_url, license, license_url,
      creator (not 'artist'), raw_data (dict | None).
    """
    raw = getattr(item, "raw_data", None) or {}
    return ImageCandidate(
        url=getattr(item, "url", "") or "",
        source=connector_id,
        title=getattr(item, "title", "") or "",
        description=getattr(item, "description", "") or "",
        # ContentItem uses 'creator', not 'artist'
        artist=getattr(item, "creator", "") or raw.get("artist", "") or "",
        license=getattr(item, "license", "") or "",
        license_url=getattr(item, "license_url", "") or "",
        thumbnail_url=getattr(item, "thumbnail_url", "") or getattr(item, "url", "") or "",
        metadata=raw,
    )


async def fetch_candidates(query: str, limit_per_source: int = 5) -> list[ImageCandidate]:
    """Fan out a query across all image-capable connectors in parallel.

    Returns deduplicated, source-capped candidates. Connectors that error out
    or return nothing are skipped silently so one misbehaving adapter can't
    block the whole pipeline.
    """
    from pipeline.connectors.registry import ConnectorRegistry

    async def _run_one(connector_id: str) -> list[ImageCandidate]:
        conn = ConnectorRegistry.get(connector_id)
        if conn is None:
            return []
        try:
            # search() is async — call it directly, no to_thread needed
            items = await conn.search(query=query, limit=limit_per_source)
        except Exception as exc:
            logger.info("connector %s failed for '%s': %s", connector_id, query, exc)
            return []
        return [_item_to_candidate(item, connector_id) for item in (items or [])]

    results = await asyncio.gather(*[_run_one(c) for c in _IMAGERY_CONNECTORS])
    flat: list[ImageCandidate] = []
    for batch in results:
        flat.extend(batch)
    deduped = deduplicate_candidates(flat)
    return select_top_per_connector(deduped, per_source=3)


async def download_candidate(cand: ImageCandidate, out_path: Path) -> bool:
    """Download the candidate's thumbnail (or full image) to disk.

    Returns True on success, False otherwise.
    """
    src = cand.thumbnail_url or cand.url
    if not src:
        return False

    def _dl() -> None:
        resp = httpx.get(
            src,
            timeout=60.0,
            follow_redirects=True,
            headers={"User-Agent": "AncientNerdsResearch/1.0 (https://ancientnerds.com)"},
        )
        resp.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)

    try:
        await asyncio.to_thread(_dl)
        return True
    except Exception as exc:
        logger.warning("download failed %s: %s", src, exc)
        return False
