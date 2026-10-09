"""The shared Wikipedia cache of the final repair, as the identity stages read it.

`output/remediation/final-2026-10-08/wiki_cache/` holds the article of every shown curated site,
fetched once and serially (`tools/wiki_cache.py`): `INDEX.jsonl` has one line per site and page
(`site_id`, `lang`, `title`, `file`), each file `{lang, title, resolved_title, pageid, revid,
timestamp, fetched_at, text}` (the article as plain text) or `{..., missing: true}`. Verifier agents
read the site's article from there first and fetch every other source live (Wikimedia throttles this
office's IP at four parallel readers, and a 403 or 429 is never a finding).

Two uses in the identity stages: the **question** names the cached file of each site, so the agent
opens a local file instead of the site; the **import** reads a cited Wikipedia URL from the same
file when the cache holds the page (the very text the agent read), and fetches every other URL live.
Nothing here writes to the cache.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

CACHE_SUBDIR = Path("output") / "remediation" / "final-2026-10-08" / "wiki_cache"
INDEX_FILE = "INDEX.jsonl"
_ARTICLE_URL = re.compile(r"^https://([a-z]{2,3}(?:-[a-z]+)?)\.wikipedia\.org/wiki/([^?#]+)\Z")


def article_url(lang: str, title: str) -> str:
    """The URL of an article as the site's own `source_url` values spell it."""
    return f"https://{lang}.wikipedia.org/wiki/" + quote(
        title.replace(" ", "_"), safe="()',-._~:!*;@$"
    )


def url_page(url: str) -> tuple[str, str] | None:
    """`(lang, title)` of a Wikipedia article URL, or `None` for any other URL."""
    match = _ARTICLE_URL.match(url)
    if match is None:
        return None
    return match.group(1), unquote(match.group(2)).replace("_", " ")


def load_cache(root: Path | None = None) -> WikiIndex:
    """The shared cache of the main checkout (or of `root`), or an `IdentityError` that says it is
    missing: the questions name its files and the import reads from it, and a run without it would
    send every verifier to Wikipedia - the throttle the cache exists to avoid."""
    from identity import common

    cache = (root or common.main_checkout()) / CACHE_SUBDIR
    if not (cache / INDEX_FILE).exists():
        raise common.IdentityError(
            f"{cache / INDEX_FILE} does not exist: run tools/wiki_cache.py first (the verifier "
            "agents read Wikipedia from it)"
        )
    return WikiIndex.load(cache)


@dataclass(frozen=True)
class CachedPage:
    lang: str
    title: str
    path: Path
    resolved_title: str | None
    missing: bool
    fetched_at: str | None

    def text(self) -> str:
        return str(json.loads(self.path.read_text(encoding="utf-8"))["text"])


class WikiIndex:
    """`INDEX.jsonl` of the cache: pages by site and by `(lang, title)`."""

    def __init__(self, root: Path, lines: Iterable[Mapping[str, Any]]) -> None:
        self.root = root
        self.by_site: dict[str, list[CachedPage]] = defaultdict(list)
        self.by_title: dict[tuple[str, str], CachedPage] = {}
        for line in lines:
            path = root / str(line["file"]).replace("\\", "/")
            if not path.exists():
                raise FileNotFoundError(f"{path}: the index names a page the cache does not hold")
            meta = json.loads(path.read_text(encoding="utf-8"))
            page = CachedPage(
                lang=str(line["lang"]),
                title=str(line["title"]),
                path=path,
                resolved_title=meta.get("resolved_title"),
                missing=bool(meta.get("missing")),
                fetched_at=meta.get("fetched_at"),
            )
            self.by_site[str(line["site_id"])].append(page)
            # an article URL spells a space as an underscore (`url_page` undoes it), a title never
            self.by_title.setdefault((page.lang, page.title.replace("_", " ")), page)
            if page.resolved_title:
                self.by_title.setdefault((page.lang, page.resolved_title.replace("_", " ")), page)

    @classmethod
    def load(cls, root: Path) -> WikiIndex:
        index = root / INDEX_FILE
        lines = [json.loads(x) for x in index.read_text(encoding="utf-8").splitlines() if x]
        return cls(root, lines)

    def site_pages(self, site_id: str) -> list[CachedPage]:
        """The cached, non-missing pages of a site, English first."""
        pages = [p for p in self.by_site.get(site_id, []) if not p.missing]
        return sorted(pages, key=lambda p: (p.lang != "en", p.lang, p.title))

    def for_url(self, url: str) -> CachedPage | None:
        """The cached page a Wikipedia URL names, if the cache holds it (and it is not missing)."""
        key = url_page(url)
        page = None if key is None else self.by_title.get(key)
        return None if page is None or page.missing else page
