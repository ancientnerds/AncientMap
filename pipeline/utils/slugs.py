# SPDX-License-Identifier: AGPL-3.0-only
"""URL slugs and the public base URL — pure string helpers with no
third-party imports.

They used to live in pipeline/article_html_renderer.py, which imports
markdown and nh3. The Lyra container has neither: when article_generator
started importing the renderer for slugify (IndexNow, 2026-09-17) the
orchestrator crash-looped 192 times on ModuleNotFoundError and its migration
lock retries pushed the API into lock timeouts. Everything that only needs a
slug imports from here.
"""

from __future__ import annotations

import re

BASE_URL = "https://ancientnerds.com"


def slugify(title: str) -> str:
    """Generate URL-safe slug from article title."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = re.sub(r"^-|-$", "", slug)
    return slug[:120]


def story_slug(headline: str, item_id: int) -> str:
    """Stable, unique slug for a news story: headline slug + numeric ID suffix."""
    return f"{slugify(headline)}-{item_id}"


def story_id_from_slug(slug: str) -> int | None:
    """Extract the numeric NewsItem ID from a story slug, or None if malformed."""
    tail = slug.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else None
