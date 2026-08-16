"""
Slugs and paths for the crawlable site browser.

The page markup renders through React since the react-ssr cutover
(src/seo/, Task 16 deleted the Python renderer; the coordinate and period
display helpers moved to src/seo/display.ts). This module only builds the
URLs those pages use — routes and sitemap import it, so the slug contract
lives exactly once.
"""

import re
from urllib.parse import quote

from pipeline.article_html_renderer import slugify


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
