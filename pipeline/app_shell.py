"""
Server-rendered SEO content injected into the real built app shell.

Every indexed URL (/news-archive/{slug}, /sites/{country}/{slug},
/research/{slug}, /articles/{slug}) serves the *same* HTML document the
SPA would serve — hashed asset tags and all — with three additions:

1. per-entity <title>/meta/OG/JSON-LD in <head>
2. crawlable content inside <div id="root">
3. window.__AN_ROUTE__, so the React entry knows which entity to load
   without parsing the URL or paying an extra round trip

React mounts, renders the interactive page and replaces the injected
markup. Crawlers and no-JS visitors keep the server-rendered version.

Why read the built file instead of hand-writing a shell: the asset
filenames are content-hashed and change on every build. Reading dist/
is the only way to stay in sync.

Why the mount is the *parent* directory (see docker-compose): the deploy
swaps the build in with `mv dist dist-old && mv dist-new dist`, replacing
the directory inode. A bind mount pointing straight at dist/ would keep
resolving to the deleted inode and serve stale shells forever — and the
api container is not even rebuilt when only frontend files change.
Mounting the parent means dist/ is resolved fresh on every read.
"""

import os
import threading
from pathlib import Path

FRONTEND_DIR = Path(os.getenv("FRONTEND_DIST_DIR", "/app/frontend/dist"))

_ROOT_DIV = '<div id="root"></div>'
_HEAD_CLOSE = "</head>"

# entry HTML -> (mtime_ns, size, content). Nanosecond precision: a rebuild
# can emit a same-size file inside one whole-second mtime tick.
_cache: dict[str, tuple[int, int, str]] = {}
_cache_lock = threading.Lock()


class ShellUnavailableError(RuntimeError):
    """The built frontend shell is missing — the deploy is broken, not the request."""


def _read_entry(entry: str) -> str:
    """Read a built entry HTML, re-reading whenever the file changes on disk."""
    path = FRONTEND_DIR / entry
    try:
        stat = path.stat()
    except OSError as exc:
        raise ShellUnavailableError(
            f"Built frontend shell {path} is missing. The API container needs "
            f"the frontend bind mount (./ancient-nerds-map:/app/frontend:ro) and "
            f"`npm run build` must have run. Set FRONTEND_DIST_DIR to override."
        ) from exc

    key = str(path)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2]

    html = path.read_text(encoding="utf-8")
    with _cache_lock:
        _cache[key] = (stat.st_mtime_ns, stat.st_size, html)
    return html


def _strip_default_head_tags(head: str) -> str:
    """
    Drop the shell's placeholder title and meta tags.

    The static entry files carry generic values ("Archaeological Site
    Detail | Ancient Nerds"). Leaving them in place would emit two
    <title> elements and two og:title tags per page, and crawlers pick
    whichever they like.
    """
    import re

    head = re.sub(r"<title>.*?</title>\s*", "", head, flags=re.DOTALL)
    head = re.sub(
        r'<meta\s+(?:name|property)="'
        r"(?:description|robots|og:type|og:title|og:description|og:image|og:url|og:site_name"
        r'|twitter:card|twitter:title|twitter:description|twitter:image)"'
        r"[^>]*/?>\s*",
        "",
        head,
        flags=re.IGNORECASE,
    )
    # The rule above only covered <meta>. articles.html and research.html ship
    # their own <link rel="canonical">, so every /articles/{slug} served two
    # canonicals — the shell's pointing at /articles.html, then the real one
    # (verified on prod 2026-08-09).
    head = re.sub(r'<link\s+rel="canonical"[^>]*/?>\s*', "", head, flags=re.IGNORECASE)
    return head


def _strip_noscript_fallback(body: str) -> str:
    """
    Drop the shell's <noscript> stand-in once real content is injected.

    Each entry ships a generic no-JS block — its own <h1>
    ("Archaeological Site Detail - Ancient Nerds") and a min-height:100vh
    wrapper — that sits *before* #root. Served as-is it gave every indexed
    page a boilerplate first <h1> ahead of the real one and pushed the
    server-rendered content a full viewport down for anything that does
    not run JavaScript (verified on prod for /sites/england, 2026-08-09).

    The injected fragment is a strictly better no-JS fallback, so the
    placeholder has nothing left to do.
    """
    import re

    return re.sub(r"<noscript>.*?</noscript>\s*", "", body, flags=re.DOTALL | re.IGNORECASE)


def render_app_shell(
    entry: str,
    *,
    head_html: str,
    root_html: str,
    route: str,
) -> str:
    """
    Build a full HTML document from a built entry shell.

    entry:     filename inside dist/, e.g. "story.html"
    head_html: per-entity <title>/meta/JSON-LD markup
    root_html: server-rendered content placed inside #root
    route:     JSON literal assigned to window.__AN_ROUTE__

    Raises ShellUnavailableError if the built entry is missing — that is a
    deployment fault and must be loud, not silently degraded.
    """
    html = _read_entry(entry)

    head_end = html.find(_HEAD_CLOSE)
    if head_end == -1:
        raise ShellUnavailableError(f"{entry} has no </head> — not a usable app shell")
    head, rest = html[:head_end], html[head_end:]
    head = _strip_default_head_tags(head)
    rest = _strip_noscript_fallback(rest)

    route_script = f"<script>window.__AN_ROUTE__={route};</script>"
    html = f"{head}{head_html}\n{route_script}\n{rest}"

    if _ROOT_DIV not in html:
        raise ShellUnavailableError(f"{entry} has no '{_ROOT_DIV}' — cannot inject content")
    return html.replace(_ROOT_DIV, f'<div id="root">{root_html}</div>', 1)
