"""What a MiniMax search leaves on disk, and the rules that turn it into evidence.

The search lane (block A3 of `output/remediation/logs/remaining_map_2026-09-22.json`) reruns the
finder on the (site, field) pairs whose verdict was `UNVERIFIABLE`, with search results added to the
evidence the mass run already had. Three modules share one record, so its format lives here, in the
one module that both the writer of the record (`phase3/search_stage.py`) and its reader
(`phase3/model_stage.evidence_excerpts`, behind the finder, the reviewer and the citation check) can
import without importing each other:

* **Which searches a site buys.** A site record of a search plan carries `rerun_fields`, a non-empty
  subset of `snapshot_plan.DISCOVER_FIELDS`. Every rerun field maps to one search *key*;
  `description` and `card_description` share the key `text`, so one query serves both texts
  (brief W4). A record without `rerun_fields` buys no search at all - that is every record of
  `runs/mass`, whose prompts therefore do not change by one byte.
* **The stored record.** One file per (site, key) in the batch's own evidence store, under the
  feature `minimax_search.<key>`: sorted-key JSON `{hits: [{date, rank, snippet, title, url}],
  linkless, query}` with no timestamp, so the bytes are a function of the answer alone. Only results
  that name a page are stored; `linkless` counts the ones that did not.
* **Which hits may become evidence.** A hit on this project's own site is circular - the search can
  find the very value under test, published by us - and a hit on a host in
  `pipeline/lyra/blocked_domains.txt` is a source the project already refuses elsewhere. Both are
  excluded when the evidence is built, so the stored record stays what the engine answered and the
  policy can be read next to it.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Dual use: `python -m phase3.search_evidence` and an import from `run.py`. Same shim as the other
# phase-3 modules for `phase3` itself, plus the repository root for `pipeline.lyra`: this module is
# imported by `model_stage`, and every tool that imports `model_stage` (the writer's gate, the
# acceptance scripts) must find the blocked-domain list without a PYTHONPATH of its own. Appended,
# not inserted, so nothing under the root can shadow a phase-3 module.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))

from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second
from phase3.snapshot_plan import DISCOVER_FIELDS  # noqa: E402
from pipeline.lyra.blocked_domains import BLOCKED_DOMAINS  # noqa: E402
from pipeline.lyra.minimax_shared import MINIMAX_SEARCH_PATH  # noqa: E402

#: The key a search plan's site record carries its rerun fields under.
RERUN_FIELDS_KEY = "rerun_fields"

#: The evidence feature of one search: `minimax_search.<key>`, the fetch stage's `<site>/<feature>`
#: naming, so `fetch_stage.EvidenceStore` stores it beside the pages it was bought to complement.
SEARCH_FEATURE_PREFIX = "minimax_search."

#: Which search serves which field. The two text fields share one: both are judged against what the
#: sources say the site *is*, and one query per site for both is the brief's own figure (W10: about
#: 2,140 searches for the 3,419 text fields instead of one per field).
SEARCH_KEY_FOR_FIELD: dict[str, str] = {
    "period_start": "period_start",
    "site_type": "site_type",
    "country": "country",
    "description": "text",
    "card_description": "text",
}

#: This project's own domains. A search can return our own published value for the very field under
#: test, and a quote from it would make the correction cite itself.
OWN_DOMAINS: tuple[str, ...] = ("ancientnerds.com",)

#: The `url` a failed or not-yet-run search carries in the prompt. A search is a POST whose query
#: travels in the body; the endpoint path is what identifies the call, the query is in the reason.
SEARCH_TARGET_URL = MINIMAX_SEARCH_PATH

#: The exact keys of a stored record and of one stored hit. A file with more or fewer is not a record
#: this module wrote, and reading it anyway would build evidence from bytes nobody can account for.
RECORD_KEYS = frozenset({"hits", "linkless", "query"})
HIT_KEYS = frozenset({"date", "rank", "snippet", "title", "url"})


def rerun_fields(site: Mapping[str, Any]) -> tuple[str, ...] | None:
    """The fields a search plan reruns for this site, in `DISCOVER_FIELDS` order - or `None`.

    `None` means the record carries no `rerun_fields` key at all, which is the mass run's shape: every
    field is asked. A key that is present must hold a non-empty list of known fields without repeats;
    `null`, `[]`, a string or an unknown field raise, so a damaged plan can never quietly widen back to
    "ask all five".
    """
    if RERUN_FIELDS_KEY not in site:
        return None
    site_id = str(site.get("site_id") or "")
    value = site[RERUN_FIELDS_KEY]
    if not isinstance(value, list) or not value:
        raise InputError(
            f"{site_id}: {RERUN_FIELDS_KEY}={value!r} is not a non-empty list of fields; a search "
            "plan names the fields it reruns"
        )
    unknown = [name for name in value if name not in DISCOVER_FIELDS]
    if unknown:
        raise InputError(
            f"{site_id}: {RERUN_FIELDS_KEY} names {unknown!r}, which the discover pass does not ask "
            f"about (known: {list(DISCOVER_FIELDS)})"
        )
    if len(set(value)) != len(value):
        raise InputError(f"{site_id}: {RERUN_FIELDS_KEY}={value!r} names a field twice")
    return tuple(name for name in DISCOVER_FIELDS if name in value)


def search_feature(key: str) -> str:
    """`minimax_search.<key>` - the evidence feature one search is stored under."""
    return f"{SEARCH_FEATURE_PREFIX}{key}"


@dataclass(frozen=True)
class SearchSlot:
    """One search a site buys: its key, its evidence feature and the rerun fields it serves."""

    key: str
    feature: str
    fields: tuple[str, ...]


def search_slots(site: Mapping[str, Any]) -> tuple[SearchSlot, ...]:
    """The searches this site's rerun fields buy, one per key, in field order. `()` for no search."""
    fields = rerun_fields(site)
    if fields is None:
        return ()
    served: dict[str, list[str]] = {}
    for name in fields:
        served.setdefault(SEARCH_KEY_FOR_FIELD[name], []).append(name)
    return tuple(
        SearchSlot(key=key, feature=search_feature(key), fields=tuple(names))
        for key, names in served.items()
    )


@dataclass(frozen=True)
class StoredHit:
    """One result that names a page, as stored. Every field is text except the engine rank."""

    rank: int
    title: str
    url: str
    snippet: str
    date: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "rank": self.rank,
            "snippet": self.snippet,
            "title": self.title,
            "url": self.url,
        }


@dataclass(frozen=True)
class SearchRecord:
    """One answered search: the query sent, the hits that name a page, the results that named none."""

    query: str
    hits: tuple[StoredHit, ...]
    linkless: int

    def to_bytes(self) -> bytes:
        """Sorted keys, UTF-8, one trailing LF, no timestamp: the bytes are the answer's alone."""
        payload = {
            "hits": [hit.to_dict() for hit in self.hits],
            "linkless": self.linkless,
            "query": self.query,
        }
        return (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def read_record(path: Path) -> SearchRecord:
    """Read a stored search, refusing anything this module would not have written."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{path}: a stored search is not JSON: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) != RECORD_KEYS:
        raise InputError(f"{path}: a stored search carries keys other than {sorted(RECORD_KEYS)}")
    query, rows, linkless = payload["query"], payload["hits"], payload["linkless"]
    if not isinstance(query, str) or not query.strip():
        raise InputError(f"{path}: a stored search carries no query")
    if not isinstance(linkless, int) or isinstance(linkless, bool) or linkless < 0:
        raise InputError(f"{path}: linkless={linkless!r} is not a count")
    if not isinstance(rows, list):
        raise InputError(f"{path}: hits is not a list")
    hits: list[StoredHit] = []
    last_rank = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != HIT_KEYS:
            raise InputError(f"{path}: a stored hit carries keys other than {sorted(HIT_KEYS)}")
        rank = row["rank"]
        if not isinstance(rank, int) or isinstance(rank, bool) or rank <= last_rank:
            raise InputError(f"{path}: rank {rank!r} is not after rank {last_rank}")
        last_rank = rank
        texts = {name: row[name] for name in ("title", "url", "snippet", "date")}
        if not all(isinstance(value, str) for value in texts.values()) or not texts["url"]:
            raise InputError(f"{path}: a stored hit is not text with a url: {row!r}")
        hits.append(StoredHit(rank=rank, **texts))
    return SearchRecord(query=query, hits=tuple(hits), linkless=linkless)


def hit_text(hit: StoredHit) -> str:
    """The evidence text of one hit: `title`, newline, `snippet (date)` - plain text, not JSON.

    Plain on purpose: `discover_stage.normalise_quote` compares a quoted sentence against this text,
    and a JSON rendering would put escapes between the finder's quote and the words it copied.
    """
    body = f"{hit.snippet} ({hit.date})" if hit.date else hit.snippet
    return "\n".join(part for part in (hit.title, body.strip()) if part)


def excluded_because(url: str) -> str | None:
    """Why a hit may not become evidence, or `None` when it may.

    Matched by host and its parent domains (`old.reddit.com` is `reddit.com`), never by substring:
    a substring match on `x.com` would refuse `linux.com` (the defect `web_research.py` records for
    its own list). The two existing matchers in `pipeline/lyra/` are private to their modules and
    bound to their own lists, so neither can be reused for this one.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return "the url does not parse"
    if parts.scheme not in ("http", "https") or not host:
        return "not an http(s) url with a host"
    for domain in OWN_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return f"{host} is this project's own site: a quote from it would cite our own value"
    labels = host.split(".")
    for start in range(len(labels) - 1):
        candidate = ".".join(labels[start:])
        if candidate in BLOCKED_DOMAINS:
            return f"{host} is on pipeline/lyra/blocked_domains.txt ({candidate})"
    return None
