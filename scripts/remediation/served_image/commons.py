"""The Commons API as the served-image lane asks it: read-only, paced, cached, one attempt each.

Three questions, each verified live on 2026-09-26 against `commons.wikimedia.org/w/api.php` with
the lanes' User-Agent (`research_web.USER_AGENT`):

* `prop=categories` for `File:` titles - the file's categories, the `normalized` and `redirects`
  chains the API applied (a renamed file answers under its new title), `missing: true` for a file
  that does not exist. `cllimit=max` caps a response at 500 categories across the batch, so the
  answer comes in pieces joined by `continue` (T10 measured the same, `_page_records`).
* `list=categorymembers` with `cmtype=file` - a category's files, in the API's own order.
* `prop=imageinfo` with `iiurlwidth` - the original's URL and a rendering of the requested width.
  Both URLs carry `utm_*` parameters since 2026; they are dropped (`plain_url`).

Answers are kept under the run directory (`commons/*.json`, the bytes under `commons/files/`), so a
repeated command asks nothing twice. A failed request raises: "Commons did not answer" is never
turned into "no category" or "no file".
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from pipeline.utils.http import is_public_http_url  # noqa: E402 - Lyra's own SSRF check
from pipeline.utils.mediawiki import dereference  # noqa: E402
from served_image.state import StateError, canonical_file  # noqa: E402

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
#: Titles per `prop=` query - the API's own limit for a client without the bot right.
TITLES_PER_QUERY = 50
#: A continuation chain longer than this is refused rather than recorded half.
MAX_CONTINUATIONS = 40
#: Seconds between two requests to one host (Wikimedia's robot policy asks for serial requests).
PACE_SECONDS = 1.0
#: The rendering width the vision stages look at (a Commons standard thumbnail step).
RENDER_WIDTH = 1280

OK = "ok"
MISSING = "missing"


class CommonsError(StateError):
    """Commons did not answer the question. Nothing is recorded for it."""


class Unfetchable(CommonsError):
    """The address itself says no: it refuses the connection, answers that the resource is gone or
    forbidden (`GONE_STATUSES`), or serves no bytes. A timeout, HTTP 429 or a 5xx is not this - it
    is a `CommonsError` that stops the command, to be run again."""


#: The HTTP answers that say the resource will not be served to us, whenever we ask.
GONE_STATUSES = frozenset({400, 401, 403, 404, 410, 451})
#: The transport failures that say the host refuses us, not that it is slow.
REFUSED = (httpx.ConnectError, httpx.RemoteProtocolError, httpx.UnsupportedProtocol)


def plain_url(url: str) -> str:
    """A Commons URL without its query and fragment (the `utm_*` tracking of 2026)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def canonical_category(name: str) -> str:
    """A category name in MediaWiki's title form, without the `Category:` prefix."""
    text = name.strip()
    if text[:9].lower() == "category:":
        text = text[9:]
    return canonical_file(text)


@dataclass(frozen=True)
class FileInfo:
    """What Commons says about one file: `ok` with its title and categories, or `missing`."""

    status: str
    title: str | None
    categories: tuple[str, ...]


class Commons:
    """The Commons questions of the lane, answered from the cache or asked once."""

    def __init__(
        self,
        cache: Path,
        client: httpx.Client,
        *,
        pace: float = PACE_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cache = cache
        self.client = client
        self.pace = pace
        self.sleep = sleep
        self.clock = clock
        self._last: dict[str, float] = {}

    # ------------------------------------------------------------------------ transport
    def _wait(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        last = self._last.get(host)
        if last is not None and last + self.pace > self.clock():
            self.sleep(last + self.pace - self.clock())
        self._last[host] = self.clock()

    def get(self, url: str) -> httpx.Response:
        self._wait(url)
        try:
            response = self.client.get(url)
        except REFUSED as exc:
            raise Unfetchable(f"{url}: {type(exc).__name__}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise CommonsError(f"{url}: {type(exc).__name__}: {exc}") from exc
        if response.status_code in GONE_STATUSES:
            raise Unfetchable(f"{response.url}: HTTP {response.status_code}")
        if response.status_code != 200:
            raise CommonsError(f"{response.url}: HTTP {response.status_code}")
        return response

    def api(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """One API query, sent as a POST: 50 long titles in a GET line answer HTTP 414 (T09
        measured it), and the API reads a query from a form body just the same."""
        self._wait(COMMONS_API)
        data = {"format": "json", "formatversion": 2, **params}
        try:
            response = self.client.post(COMMONS_API, data=data)
        except httpx.HTTPError as exc:
            raise CommonsError(f"{COMMONS_API}: {type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise CommonsError(f"{COMMONS_API}: HTTP {response.status_code} for {dict(params)}")
        body = response.json()
        if "error" in body:
            raise CommonsError(f"Commons refused {dict(params)}: {body['error']}")
        return body

    # ------------------------------------------------------------------------ the cache
    def _load(self, name: str) -> dict[str, Any]:
        path = self.cache / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _save(self, name: str, data: Mapping[str, Any]) -> None:
        self.cache.mkdir(parents=True, exist_ok=True)
        path = self.cache / f"{name}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        tmp.replace(path)

    # ------------------------------------------------------------------------ categories
    def categories(self, files: Iterable[str]) -> dict[str, FileInfo]:
        """Each file's categories (title form, no prefix), asked in batches of 50 titles."""
        cached = self._load("categories")
        wanted = sorted({canonical_file(f) for f in files})
        todo = [f for f in wanted if f not in cached]
        for start in range(0, len(todo), TITLES_PER_QUERY):
            batch = todo[start : start + TITLES_PER_QUERY]
            cached.update(self._categories_batch(batch))
            self._save("categories", cached)
        out: dict[str, FileInfo] = {}
        for name in wanted:
            entry = cached[name]
            out[name] = FileInfo(entry["status"], entry["title"], tuple(entry["categories"]))
        return out

    def _categories_batch(self, files: list[str]) -> dict[str, dict[str, Any]]:
        params: dict[str, Any] = {
            "action": "query",
            "prop": "categories",
            "cllimit": "max",
            "redirects": 1,
            "titles": "|".join(f"File:{f}" for f in files),
        }
        pages: dict[str, dict[str, Any]] = {}
        mapping: dict[str, str] = {}
        for _ in range(MAX_CONTINUATIONS):
            body = self.api(params)
            query = body.get("query") or {}
            for page in query.get("pages") or []:
                rec = pages.setdefault(page["title"], {"missing": False, "categories": []})
                gone = bool(page.get("missing")) or bool(page.get("invalid"))
                rec["missing"] = rec["missing"] or gone
                rec["categories"] += [c["title"] for c in page.get("categories") or []]
            for entry in (query.get("normalized") or []) + (query.get("redirects") or []):
                mapping[entry["from"]] = entry["to"]
            if "continue" not in body:
                break
            params.update(body["continue"])
        else:
            raise CommonsError(f"categories of {files[0]!r}...: continuation past the limit")
        out: dict[str, dict[str, Any]] = {}
        for name in files:
            title = dereference(f"File:{name}", mapping)
            page = pages.get(title)
            if page is None:
                raise CommonsError(f"Commons answered nothing for File:{name}")
            if page["missing"]:
                out[name] = {"status": MISSING, "title": None, "categories": []}
                continue
            cats = sorted({canonical_category(c) for c in page["categories"]})
            out[name] = {"status": OK, "title": canonical_file(title), "categories": cats}
        return out

    # ------------------------------------------------------------------------ members
    def members(self, category: str, limit: int) -> list[str]:
        """The first `limit` files of a category, in the API's order (title form)."""
        key = canonical_category(category)
        cached = self._load("members")
        entry = cached.get(key)
        if entry is None or entry["limit"] < limit:
            body = self.api(
                {
                    "action": "query",
                    "list": "categorymembers",
                    "cmtitle": f"Category:{key}",
                    "cmtype": "file",
                    "cmlimit": limit,
                }
            )
            found = [canonical_file(m["title"]) for m in body["query"]["categorymembers"]]
            entry = {"limit": limit, "files": found}
            cached[key] = entry
            self._save("members", cached)
        return list(entry["files"])[:limit]

    # ------------------------------------------------------------------------ files
    def imageinfo(self, files: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Each file's original URL and its `RENDER_WIDTH` rendering (query stripped), or
        `{"status": "missing"}` for a file Commons does not hold."""
        cached = self._load("imageinfo")
        wanted = sorted({canonical_file(f) for f in files})
        todo = [f for f in wanted if f not in cached]
        for start in range(0, len(todo), TITLES_PER_QUERY):
            batch = todo[start : start + TITLES_PER_QUERY]
            body = self.api(
                {
                    "action": "query",
                    "prop": "imageinfo",
                    "iiprop": "url|mime|size|sha1",
                    "iiurlwidth": RENDER_WIDTH,
                    "redirects": 1,
                    "titles": "|".join(f"File:{f}" for f in batch),
                }
            )
            query = body.get("query") or {}
            mapping = {
                e["from"]: e["to"]
                for e in (query.get("normalized") or []) + (query.get("redirects") or [])
            }
            pages = {p["title"]: p for p in query.get("pages") or []}
            for name in batch:
                page = pages.get(dereference(f"File:{name}", mapping))
                if page is None:
                    raise CommonsError(f"Commons answered no imageinfo for File:{name}")
                if page.get("missing") or not page.get("imageinfo"):
                    cached[name] = {"status": MISSING}
                    continue
                info = page["imageinfo"][0]
                cached[name] = {
                    "status": OK,
                    "title": canonical_file(page["title"]),
                    "url": plain_url(info["url"]),
                    "render_url": plain_url(info.get("thumburl") or info["url"]),
                    "mime": info.get("mime"),
                    "sha1": info.get("sha1"),
                }
            self._save("imageinfo", cached)
        return {f: cached[f] for f in wanted}

    def download(self, url: str) -> Path:
        """The bytes behind a URL, kept once under `files/<sha256 of the URL>`."""
        if not is_public_http_url(url):
            raise CommonsError(f"{url} is not a public http(s) URL - never fetched")
        target = self.cache / "files" / hashlib.sha256(url.encode("utf-8")).hexdigest()
        if not target.exists():
            body = self.get(url).content
            if not body:
                raise Unfetchable(f"{url} answered an empty body")
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(target)
        return target
