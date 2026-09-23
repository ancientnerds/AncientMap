# SPDX-License-Identifier: AGPL-3.0-only
"""Reading the MediaWiki action API's answers - pure helpers with no third-party imports.

The API answers a batch of titles under the names it normalised them to (`File:A_b.jpg` comes
back as `File:A b.jpg`) and, with `redirects=1`, under the targets of redirects. It reports both
rewrites in `query.normalized` and `query.redirects` as `{"from": ..., "to": ...}` entries. A
caller that looks an answer up by the title it asked for must follow those entries first, or it
misses every rewritten title. Until 2026-09-23 the census (T09, T10) and the attribution lane each
carried a copy of `dereference`; the downloader keyed its answers by the answer's own title and
missed 12 of 12 titles of a live `media-list` (measured that day on en.wikipedia `Stonehenge`).
"""


def dereference(title: str, mapping: dict[str, str]) -> str:
    """Apply the API's own `normalized`/`redirects` chains (bounded, in case of a loop)."""
    for _ in range(4):
        nxt = mapping.get(title)
        if nxt is None or nxt == title:
            break
        title = nxt
    return title
