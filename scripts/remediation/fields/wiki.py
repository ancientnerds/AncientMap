"""The shared Wikipedia cache of the final repair, read by the agents of lane wd5 (2026-10-08).

Wikimedia throttles this office IP from four parallel agents on (403 and 429 on a cache miss, a
false `UNVERIFIABLE` finding - AUDIT_LOG 2026-10-07). So one serial pass put the Wikipedia article
of every shown curated site on disk once (`output/remediation/final-2026-10-08/tools/wiki_cache.py`),
and the agents of the field re-check read the file instead of the site:

    <cache>/INDEX.jsonl                    one line per site and page: site_id, lang, title, file
    <cache>/<lang>/<sha1 of title>.json    {lang, title, resolved_title, pageid, revid, timestamp,
                                           fetched_at, text} - or {..., missing: true}

A page the machine's quote check reads is the live article, as fetched at import: the cached text is
the same article's extract as of its revision, so a quote copied from it is checked against the live
page and must match it character for character (footnote markers and tables are where the two can
differ). Anything that is not Wikipedia is still fetched live, a few requests at most.

    handoff.py wiki-text --label SITE_ID        the cached articles of a site, for the agent
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]

#: Where the cache lives in the checkout that holds the run tree (`output/` is untracked).
WIKI_CACHE = REPO / "output" / "remediation" / "final-2026-10-08" / "wiki_cache"
INDEX_FILE = "INDEX.jsonl"
INDEX_KEYS = frozenset({"site_id", "lang", "title", "file"})


class WikiCacheError(RuntimeError):
    """The cache is not there, or a file of it is not what its index says."""


class WikiCache:
    """The cache's index, read once: `pages(site_id)` is a site's cached articles."""

    def __init__(self, root: Path = WIKI_CACHE) -> None:
        self.root = root
        index = root / INDEX_FILE
        if not index.exists():
            raise WikiCacheError(f"{index} is missing: the Wikipedia cache is not built here")
        self._rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for number, raw in enumerate(index.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            row = json.loads(raw)
            if set(row) != INDEX_KEYS:
                raise WikiCacheError(f"{index}:{number}: a line carries {sorted(row)}")
            self._rows[str(row["site_id"])].append(row)

    def pages(self, site_id: str) -> list[dict[str, Any]]:
        """The cached pages of a site in index order - none for a site the cache never held."""
        out = []
        for row in self._rows.get(site_id, ()):
            path = self.root / str(row["file"]).replace("\\", "/")
            if not path.exists():
                raise WikiCacheError(f"{path} is in the index and not on disk")
            out.append(json.loads(path.read_text(encoding="utf-8")))
        return out


def article_url(page: Mapping[str, Any]) -> str:
    """The article's own URL as a browser's address bar copies it (the one the quote check reads)."""
    title = str(page.get("resolved_title") or page["title"]).replace(" ", "_")
    return f"https://{page['lang']}.wikipedia.org/wiki/{quote(title, safe='/:@!$&()*+,;=-._~')}"


def render(site_id: str, pages: list[dict[str, Any]]) -> str:
    """The cached articles of a site for an agent to read: URL, revision, then the text."""
    if not pages:
        return f"No cached Wikipedia page for {site_id}: the site names none (fetch live).\n"
    out = []
    for page in pages:
        out.append(
            f"# {page['lang']}.wikipedia.org: {page.get('resolved_title') or page['title']} "
            f"(revision {page.get('revid')})\nURL: {article_url(page)}\n"
        )
        out.append(
            "(the article does not exist)\n" if page.get("missing") else str(page["text"]) + "\n"
        )
    return "\n".join(out)
