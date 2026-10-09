"""The shared Wikipedia cache of the final repair, read for the image prompts.

`output/remediation/final-2026-10-08/wiki_cache/` (main checkout, gitignored) holds the Wikipedia text
of the sites: an `INDEX.jsonl` of `{site_id, lang, title, file}` lines and, per page, a JSON file
`{resolved_title, revid, text}` under `<lang>/`. The web-research and verifier briefs tell their
agents to read a site's text from it first and fetch anything else live (a few requests; a 403 or
429 is never a finding). The image prompts use it for the one sentence a vision judge is given about
the site: the lead of its English article.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

INDEX = "INDEX.jsonl"
#: How much of the article's lead goes to a picture judge: enough for what the site is and where.
LEAD_CHARS = 450
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


class WikiCacheError(RuntimeError):
    """The cache is not in its layout, or a page it indexes is missing. Never read as 'no page'."""


class WikiCache:
    """The cache by site: which pages a site has and their text."""

    def __init__(self, root: Path) -> None:
        index = root / INDEX
        if not index.is_file():
            raise WikiCacheError(
                f"{index} does not exist - the shared Wikipedia cache is the source"
            )
        self.root = root
        self.pages: dict[str, dict[str, str]] = {}
        for number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if set(row) != {"site_id", "lang", "title", "file"}:
                raise WikiCacheError(f"{index}:{number}: not an index line: {line[:100]}")
            self.pages.setdefault(row["site_id"], {})[row["lang"]] = row

    def page(self, site_id: str, lang: str = "en") -> dict[str, Any] | None:
        """The cached page of a site in a language (`{resolved_title, revid, text}`), or None when
        the site has no page in it. An indexed page whose file is gone is an error."""
        row = self.pages.get(site_id, {}).get(lang)
        if row is None:
            return None
        path = self.root / Path(row["file"].replace("\\", "/"))
        if not path.is_file():
            raise WikiCacheError(f"{path} is indexed but does not exist")
        return json.loads(path.read_text(encoding="utf-8"))

    def file_of(self, site_id: str, lang: str = "en") -> Path | None:
        """The absolute path of the site's cached page in a language, or None when it has none."""
        row = self.pages.get(site_id, {}).get(lang)
        return None if row is None else (self.root / Path(row["file"].replace("\\", "/"))).resolve()

    def lead(self, site_id: str, chars: int = LEAD_CHARS) -> str | None:
        """The opening of the site's English article, cut at a sentence end within `chars`, or None."""
        page = self.page(site_id, "en")
        return None if page is None else lead_of(str(page.get("text") or ""), chars)


def lead_of(text: str, chars: int = LEAD_CHARS) -> str | None:
    """The first sentences of `text` that fit in `chars` (the first sentence whole, however long),
    or None for an empty text."""
    body = " ".join(text.split())
    if not body:
        return None
    sentences = _SENTENCE_END.split(body)
    out = sentences[0]
    for sentence in sentences[1:]:
        if len(out) + 1 + len(sentence) > chars:
            break
        out += " " + sentence
    return out
