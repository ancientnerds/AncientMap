"""Cached, polite HTTP access for the census.

Why a cache and not just requests: the census makes ~25,000 remote calls (4,618 Wikidata
entities, 981 Commons imageinfo batches, 15,230 URL heads). Without a cache every
re-run re-hammers Wikimedia, results stop being reproducible, and a network wobble
silently changes the flag list. With one, the tests become pure functions of
(snapshot, cache) and a re-run is free.

Wikimedia etiquette is enforced, not hoped for:
* a descriptive User-Agent with contact information (Wikimedia blocks generic agents),
* `maxlag=5` on API calls, so a lagging replica yields 503 instead of load,
* bounded concurrency, exponential backoff on 429/503, `Retry-After` honoured.

A transport failure is recorded as a failure, never as an empty result: a test must be
able to tell "not found" from "could not ask" (project rule: no silent fallbacks).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

log = logging.getLogger("census.fetch")


def _jitter(url: str, attempt: int) -> float:
    """Decorrelated, reproducible retry jitter in [0, 1).

    Derived from a hash of the request rather than a PRNG: two different URLs get
    different waits (so a retry storm does not synchronise), the same URL gets the
    same waits (so a re-run is reproducible), and no pseudo-random generator is
    involved in the retry path at all.
    """
    digest = hashlib.sha256(f"{url}|{attempt}".encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


def _retry_after_seconds(header: str | None) -> float | None:
    """Parse a Retry-After *delay-seconds* header, tolerating junk.

    `str.isdigit()` is not a safety check here: it is True for bytes that float()
    rejects (e.g. "\u00b2".isdigit() is True, float("\u00b2") raises). A malformed
    header must fall back to backoff, never crash the sweep.
    """
    if not header:
        return None
    try:
        value = float(header)
    except ValueError:
        return None
    return value if 0 <= value <= 300 else None


USER_AGENT = (
    "AncientNerdsSiteAudit/1.0 "
    "(https://ancientnerds.com; database audit; ancient.nerds@protonmail.com)"
)

DEFAULT_ROOT = Path("output/remediation/cache")


class FetchError(RuntimeError):
    """The request could not be completed. Never conflate this with 'absent'."""


class Fetcher:
    """Cache-backed HTTP client. Safe to share across threads."""

    def __init__(
        self,
        root: Path | str = DEFAULT_ROOT,
        workers: int = 8,
        timeout: float = 30.0,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.root = Path(root)
        self.workers = workers
        self.max_retries = max_retries
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            limits=httpx.Limits(max_connections=workers * 2, max_keepalive_connections=workers),
            transport=transport,
        )

    # ------------------------------------------------------------------ cache
    @staticmethod
    def _key(method: str, url: str, params: dict[str, Any] | None) -> str:
        blob = f"{method}\n{url}\n{urlencode(sorted((params or {}).items()))}"
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def _path(self, ns: str, key: str) -> Path:
        p = self.root / ns / key[:2] / f"{key}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load(self, ns: str, key: str) -> dict[str, Any] | None:
        p = self._path(ns, key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # A half-written cache entry must not poison the run: refetch it.
            log.warning("unreadable cache entry, refetching: %s", p)
            return None

    def _store(self, ns: str, key: str, payload: dict[str, Any]) -> None:
        p = self._path(ns, key)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)  # atomic: a killed run leaves no half entry

    # -------------------------------------------------------------- transport
    def _request(
        self, method: str, url: str, params: dict[str, Any] | None, ns: str, force: bool = False
    ) -> dict[str, Any]:
        key = self._key(method, url, params)
        if not force:
            cached = self._load(ns, key)
            if cached is not None:
                with self._lock:
                    self._hits += 1
                return cached

        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                r = self._client.request(method, url, params=params)
            except Exception as exc:  # httpx.TransportError and friends
                last = exc
                time.sleep(min(2**attempt, 12) + _jitter(url, attempt))
                continue

            if r.status_code in (429, 500, 502, 503, 504):
                delay = _retry_after_seconds(r.headers.get("retry-after"))
                if delay is None:
                    delay = min(2**attempt, 20)
                last = FetchError(f"HTTP {r.status_code} from {url}")
                if attempt < self.max_retries - 1:
                    time.sleep(delay + _jitter(url, attempt))
                    continue
            payload = {
                "method": method,
                "url": str(r.url),
                "status": r.status_code,
                "headers": {
                    k: v
                    for k, v in r.headers.items()
                    if k.lower() in ("content-type", "retry-after", "location")
                },
                "text": r.text if r.status_code < 400 else "",
                "error": None if r.status_code < 400 else f"HTTP {r.status_code}",
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            if r.status_code < 400:
                with self._lock:
                    self._misses += 1
                self._store(ns, key, payload)
            return payload

        raise FetchError(f"{method} {url} failed after {self.max_retries} attempts: {last}")

    # -------------------------------------------------------------- public API
    def get_json(
        self, url: str, params: dict[str, Any] | None = None, ns: str = "json", force: bool = False
    ) -> dict[str, Any]:
        """GET and parse JSON. Raises FetchError unless the answer is a real answer.

        Only a 404 is passed through as a value: "this does not exist" is something a
        test may legitimately conclude. Everything else that is not a 2xx/3xx - including
        401/403 - raises, because "we were refused" is not "it does not exist". Letting a
        403 through would invite exactly the silent empty-result fallback this project
        forbids (CLAUDE.md: mark a source unavailable with a reason, do not fake absence).
        """
        p = self._request("GET", url, params, ns, force)
        if p.get("error") and p["status"] != 404:
            raise FetchError(f"{p['url']}: {p['error']}")
        try:
            p = dict(p)
            p["json"] = json.loads(p.pop("text")) if p.get("text") else None
        except json.JSONDecodeError as exc:
            raise FetchError(f"{p.get('url')}: response was not JSON ({exc})") from exc
        return p

    def get_text(
        self, url: str, params: dict[str, Any] | None = None, ns: str = "text"
    ) -> dict[str, Any]:
        """Raw body as text. Same 404-is-a-value rule as `get_json`."""
        p = self._request("GET", url, params, ns)
        if p.get("error") and p["status"] != 404:
            raise FetchError(f"{p['url']}: {p['error']}")
        return p

    #: Statuses that make a HEAD answer unreliable rather than informative. 403 belongs
    #: here: bot-protection and CDNs routinely refuse HEAD while serving GET normally,
    #: and recording that as "dead link" would be a false accusation.
    _HEAD_REFUSED = (400, 401, 403, 405, 406, 501)

    def head(self, url: str, ns: str = "head") -> dict[str, Any]:
        """HEAD, falling back to GET when the server refuses HEAD.

        Never raises: the caller decides whether 403/5xx means "dead" or "unverified".
        """
        p = self._request("HEAD", url, None, ns)
        if p["status"] in self._HEAD_REFUSED:
            return self._request("GET", url, None, ns)
        return p

    def map(
        self,
        fn: Callable[[Any], Any],
        items: Sequence[Any],
        workers: int | None = None,
        desc: str = "",
    ) -> list[Any]:
        """Run `fn(item)` over `items` with bounded concurrency, order-preserving."""
        items = list(items)
        out: list[Any] = [None] * len(items)
        done = 0
        with ThreadPoolExecutor(max_workers=workers or self.workers) as pool:
            futs = {pool.submit(fn, it): i for i, it in enumerate(items)}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    out[i] = fut.result()
                except Exception as exc:  # recorded, never swallowed silently
                    out[i] = exc
                done += 1
                if desc and done % 200 == 0:
                    log.info("%s %d/%d", desc, done, len(items))
        if desc:
            log.info("%s %d/%d done", desc, done, len(items))
        return out

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"cache_hits": self._hits, "cache_misses": self._misses}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def chunked(seq: Iterable[Any], n: int) -> list[list[Any]]:
    seq = list(seq)
    return [seq[i : i + n] for i in range(0, len(seq), n)]
