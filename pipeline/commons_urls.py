"""Wikimedia Commons URL shapes the project writes, importable without a database.

`pipeline.wiki_image_downloader` opens a database engine on import (`pipeline.database`), so the
remediation lanes that only need its URL spelling could not import it and copied it instead. The
spelling lives here once: the downloader, the attribution backfill, the census URL test (T06) and
the gallery audit's L2 rule all import it.
"""

from urllib.parse import quote

COMMONS_PAGE_PREFIX = "https://commons.wikimedia.org/wiki/"


def commons_page_url_for(file_title: str) -> str:
    """Canonical Commons page URL for a File: title (spaces kept, then percent-quoted)."""
    return COMMONS_PAGE_PREFIX + quote(file_title, safe="")
