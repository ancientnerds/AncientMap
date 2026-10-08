"""What the identity questions' prompts share: the cached Wikipedia pages and a re-ask's note.

The final repair keeps one shared Wikipedia cache (`output/remediation/final-2026-10-08/wiki_cache/`,
`INDEX.jsonl` with `site_id, lang, title, file`, one JSON per page with `resolved_title`, `revid`,
`text`). A web-research prompt names the cached files of its site so the agent reads the Wikipedia
text from there first and fetches other sources live (a few requests at most; a 403 or 429 is never a
finding).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
for _root in (str(_HERE.parents[3]), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from collections.abc import Mapping
from typing import Any

from identity import common  # noqa: E402

WIKI_CACHE_SUBDIR = Path("output") / "remediation" / "final-2026-10-08" / "wiki_cache"

CACHE_NOTE = """
CACHED WIKIPEDIA (read the site's Wikipedia text here first; a JSON file with the field "text")
{lines}
"""


def wiki_cache_dir(root: Path | None = None) -> Path:
    return (root or common.main_checkout()) / WIKI_CACHE_SUBDIR


def cache_entries(cache: Path) -> dict[str, list[dict[str, str]]]:
    """The shared Wikipedia cache per site: `{lang, title, path}`, the path absolute and with `/`."""
    index = cache / "INDEX.jsonl"
    if not index.exists():
        raise common.IdentityError(
            f"{index} does not exist: the shared Wikipedia cache is not built"
        )
    by_site: dict[str, list[dict[str, str]]] = {}
    for row in common.read_jsonl(index):
        path = (cache / str(row["file"]).replace("\\", "/")).as_posix()
        by_site.setdefault(row["site_id"], []).append(
            {"lang": row["lang"], "title": row["title"], "path": path}
        )
    return by_site


def cache_section(ctx: Mapping[str, Any]) -> str:
    if not ctx["cache"]:
        return ""
    lines = "\n".join(
        f'  - {c["lang"]}.wikipedia "{c["title"]}": {c["path"]}' for c in ctx["cache"]
    )
    return CACHE_NOTE.format(lines=lines)


def earlier_section(earlier: str | None) -> str:
    return (
        ""
        if earlier is None
        else f"\nAN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED\n  {earlier}\n"
    )
