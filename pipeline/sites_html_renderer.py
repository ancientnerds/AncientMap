"""
Slugs, paths and display helpers for the crawlable site browser.

The page markup itself lives in pipeline/seo_pages.py — this module only
builds the URLs those pages use and formats coordinates and periods. It
used to render whole documents too; those renderers were never served
(nginx routes /sites/ to the app-shell splice) and were deleted 2026-08-09.
"""

import re
from html import escape
from urllib.parse import quote

from pipeline.article_html_renderer import slugify


def _coord_display(lat: float | None, lon: float | None) -> str:
    """Human-readable coordinate string, or empty when the site has no position."""
    if lat is None or lon is None:
        return ""
    lat_dir = "N" if lat >= 0 else "S"
    lon_dir = "E" if lon >= 0 else "W"
    return f"{abs(lat):.4f}&deg; {lat_dir}, {abs(lon):.4f}&deg; {lon_dir}"


def _year_display(year: int) -> str:
    """Format a signed year as an era-qualified label (-500 -> '500 BC')."""
    return f"{abs(year)} {'BC' if year < 0 else 'AD'}"


def _period_display(site: dict) -> str:
    """Prefer the curated period name, fall back to a start/end year range."""
    if site.get("period_name"):
        return str(site["period_name"])
    start, end = site.get("period_start"), site.get("period_end")
    if start is None:
        return ""
    if end is None:
        return _year_display(start)
    return f"{_year_display(start)} – {_year_display(end)}"


def country_slug(country: str) -> str:
    """URL slug for a country name."""
    return slugify(country)


def site_id_short(site_id: str) -> str:
    """First 8 hex chars of a site UUID — the on-disk image dir and slug suffix."""
    return str(site_id).replace("-", "")[:8]


def site_slug(name: str, site_id: str) -> str:
    """
    Stable, unique slug for a site: name slug + short ID suffix.

    The ID suffix is required, not decorative: 16 curated sites share a name
    with another site. It also makes the URL self-healing — a renamed site
    still resolves via the suffix and redirects to its new canonical slug.
    """
    stem = slugify(name)
    suffix = site_id_short(site_id)
    return f"{stem}-{suffix}" if stem else suffix


def site_id_prefix_from_slug(slug: str) -> str | None:
    """Extract the 8-hex-char site ID prefix from a site slug, or None if malformed."""
    tail = slug.rsplit("-", 1)[-1].lower()
    return tail if re.fullmatch(r"[0-9a-f]{8}", tail) else None


def site_path(country: str, name: str, site_id: str) -> str:
    """Canonical path for a site detail page, unencoded (see encode_path)."""
    return f"/sites/{country_slug(country)}/{site_slug(name, site_id)}"


def country_path(country: str) -> str:
    """Canonical path for a country listing page, unencoded (see encode_path)."""
    return f"/sites/{country_slug(country)}"


def encode_path(path: str) -> str:
    """
    Percent-encode a site-relative path for use in a sitemap <loc> or a
    rel=canonical URL.

    478 of the 5,012 curated site names carry non-ASCII characters
    (Ayşepınar, Aguada Fénix, …), one country does too (Türkiye), and so do
    ~100 news/article slugs. The sitemap protocol requires escaped URLs.

    Takes an UNENCODED path — passing an already-encoded one would
    double-escape every '%'. In-page href attributes do not need this;
    browsers encode them, and the readable form is nicer to look at.
    """
    return quote(path)
