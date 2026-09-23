"""What a MiniMax search leaves on disk, and the rules that turn it into evidence.

The search lane (block A3 of `output/remediation/logs/remaining_map_2026-09-22.json`) reruns the
finder on the (site, field) pairs whose verdict was `UNVERIFIABLE`, with search results added to the
evidence the mass run already had. Three modules share one record, so its format lives here, in the
one module that both the writer of the record (`phase3/search_stage.py`) and its reader
(`phase3/model_stage.evidence_excerpts`, behind the finder, the reviewer and the citation check) can
import without importing each other:

* **What a site is asked, and which searches it buys - two keys, two meanings.** `rerun_fields`
  names the fields a run asks again: the discover pass asks only these, so only their answers reach
  the reviewer, and the writer refuses every other field of the site (`write_stage.RULE_NOT_RERUN`).
  `search_fields` names the fields a run buys a MiniMax search for, and must be a non-empty subset of
  `rerun_fields`. The search plan (`phase3/search_plan.py`) writes both; the gap plan
  (`output/remediation/tools/gap_plan.py`) writes `rerun_fields` only, because its levers are the
  narrowed Wikidata evidence and the enwiki sitelink route, not a search. Every search field maps to
  one search *key*; `description` and `card_description` share the key `text`, so one query serves
  both texts (brief W4). A record without `search_fields` buys no search at all - every record of
  `runs/mass`, whose prompts therefore do not change by one byte, and every record of the gap run.
* **The stored record.** One file per (site, key) in the batch's own evidence store, under the
  feature `minimax_search.<key>`: sorted-key JSON `{hits: [{date, rank, snippet, title, url}],
  linkless, query}` with no timestamp, so the bytes are a function of the answer alone. Only results
  that name a page are stored; `linkless` counts the ones that did not.
* **Which hits may become evidence.** A hit on this project's own site is circular - the search can
  find the very value under test, published by us - and a hit on a host in
  `pipeline/lyra/blocked_domains.txt` is a source the project already refuses elsewhere. Both are
  excluded when the evidence is built, so the stored record stays what the engine answered and the
  policy can be read next to it.
* **What the mass lane decided not to write.** A rerun field that was a planned write the mass lane
  held back (72 held by hand, `HUMAN_ONLY.md` B7; 8 stopped by `write_gate.py`'s boundary check, B8)
  carries that proposal under `rerun_unwritten`. The field is open again, but that exact proposal
  is not: `review_stage.plan_site` refuses to clear a rerun answer that repeats it
  (`unwritten_proposals`, `same_value`), so the lane can never write a held value back.
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
from pipeline.lyra.blocked_domains import BLOCKED_DOMAINS, listed_domain_of  # noqa: E402
from pipeline.lyra.minimax_shared import MINIMAX_SEARCH_PATH  # noqa: E402

#: The fields a run asks again (the gap plan and the search plan both name them): the discover pass
#: asks only these, and the writer refuses every other field of the site.
RERUN_FIELDS_KEY = "rerun_fields"

#: The fields a run buys a MiniMax search for: a non-empty subset of `rerun_fields`, named by the
#: search plan alone. A record without it buys no search, whatever it reruns.
SEARCH_FIELDS_KEY = "search_fields"

#: The keys a search plan adds to a mass record besides those two: why each field is rerun, the
#: proposals the mass lane did not write, the values a query may read (production's, at plan time),
#: and the mass batch the record was copied from.
RERUN_WHY_KEY = "rerun_why"
RERUN_UNWRITTEN_KEY = "rerun_unwritten"
QUERY_VALUES_KEY = "query_values"
SOURCE_BATCH_KEY = "source_batch"

#: The keys the search plan writes and no other planner does (`source_batch` is the gap plan's too). A
#: record that carries one of them without `search_fields` is a search-plan record built before that
#: key existed, or one that lost it: `rerun_why` is on every search plan written since 2026-09-22,
#: `rerun_unwritten` and `query_values` on the later ones.
SEARCH_PLAN_KEYS = (RERUN_WHY_KEY, RERUN_UNWRITTEN_KEY, QUERY_VALUES_KEY)

#: Why a planned write was not written: held by hand (B7) or stopped by the boundary check (B8).
UNWRITTEN_KINDS = ("held", "write_gate")

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


def _named_fields(site: Mapping[str, Any], key: str) -> tuple[str, ...]:
    """The fields a record names under `key`, in `DISCOVER_FIELDS` order.

    One reading for both keys: a non-empty list of known fields without repeats. `null`, `[]`, a
    string, a mapping or an unknown field raise, so a damaged plan can never quietly widen back to
    "all five" - nor narrow to "none".
    """
    site_id = str(site.get("site_id") or "")
    value = site[key]
    if not isinstance(value, list) or not value:
        raise InputError(
            f"{site_id}: {key}={value!r} is not a non-empty list of fields; a plan names the fields "
            "it means"
        )
    unknown = [name for name in value if name not in DISCOVER_FIELDS]
    if unknown:
        raise InputError(
            f"{site_id}: {key} names {unknown!r}, which the discover pass does not ask about "
            f"(known: {list(DISCOVER_FIELDS)})"
        )
    if len(set(value)) != len(value):
        raise InputError(f"{site_id}: {key}={value!r} names a field twice")
    return tuple(name for name in DISCOVER_FIELDS if name in value)


def rerun_fields(site: Mapping[str, Any]) -> tuple[str, ...] | None:
    """The fields a run asks again at this site, in `DISCOVER_FIELDS` order - or `None`.

    `None` means the record carries no `rerun_fields` key at all, which is the mass run's shape: every
    field is asked. The discover pass, the search stage's query rules and the writer
    (`write_stage.RULE_NOT_RERUN`) all read the fields through this one function; a present key is
    read by `_named_fields`' rules.
    """
    if RERUN_FIELDS_KEY not in site:
        return None
    return _named_fields(site, RERUN_FIELDS_KEY)


def search_fields(site: Mapping[str, Any]) -> tuple[str, ...] | None:
    """The fields this site buys a MiniMax search for, in `DISCOVER_FIELDS` order - or `None`.

    `None` means the record carries no `search_fields` key: it buys no search, whether it reruns
    fields (the gap run) or not (the mass run). A present key is read by `_named_fields`' rules, and
    every field it names must be one of the record's `rerun_fields`: a search is bought for a field
    the run asks again, and it never widens what the run asks.

    A record that carries one of `SEARCH_PLAN_KEYS` without `search_fields` raises: it is a
    search-plan record built before the key existed, or one that lost it. Read as a rerun record it
    would buy its finder calls on the evidence the mass run already had, and - with no
    `rerun_unwritten` read - a held proposal could come back as a clean rerun answer.
    """
    site_id = str(site.get("site_id") or "")
    if SEARCH_FIELDS_KEY not in site:
        carried = [key for key in SEARCH_PLAN_KEYS if key in site]
        if carried:
            raise InputError(
                f"{site_id}: carries {carried} but no {SEARCH_FIELDS_KEY}; only the search plan "
                "writes those keys, so this is a search-plan record without the fields it searches "
                "for - rebuild the plan instead of running it as a rerun without its searches"
            )
        return None
    fields = _named_fields(site, SEARCH_FIELDS_KEY)
    rerun = rerun_fields(site)
    outside = [name for name in fields if rerun is None or name not in rerun]
    if outside:
        raise InputError(
            f"{site_id}: {SEARCH_FIELDS_KEY} names {outside!r}, which {RERUN_FIELDS_KEY}="
            f"{None if rerun is None else list(rerun)!r} does not ask again; a search is bought only "
            "for a field the run asks again"
        )
    return fields


def search_feature(key: str) -> str:
    """`minimax_search.<key>` - the evidence feature one search is stored under."""
    return f"{SEARCH_FEATURE_PREFIX}{key}"


@dataclass(frozen=True)
class SearchSlot:
    """One search a site buys: its key, its evidence feature and the search fields it serves."""

    key: str
    feature: str
    fields: tuple[str, ...]


def search_slots(site: Mapping[str, Any]) -> tuple[SearchSlot, ...]:
    """The searches this site's search fields buy, one per key, in field order. `()` for no search.

    Read from `search_fields` alone: `rerun_fields` says what is asked, not what is searched for, and
    a record that reruns fields without naming a search field (the gap run's) buys none.
    """
    fields = search_fields(site)
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
class UnwrittenProposal:
    """A planned write of the mass lane that was not written: its key, its value, and why not."""

    change_key: str
    proposed: str
    kind: str


def unwritten_proposals(site: Mapping[str, Any]) -> dict[str, UnwrittenProposal]:
    """`field -> the proposal the mass lane did not write`, for this search-plan record.

    A record without `rerun_fields` (the mass run's shape) has none. A rerun record without
    `search_fields` (the gap run's) has none either: it re-asks fields the mass run holds no readable
    answer for, so no proposal of them can have been held back, and `search_fields` refuses such a
    record that carries `rerun_unwritten` (a search-plan key). A search-plan record (one with
    `search_fields`) must carry `rerun_unwritten` - `{}` when no rerun field was an unwritten row -
    because its planner is the one that selects unwritten rows (`search_plan.unwritten_rows`). Every
    entry must name a rerun field, a change key, a non-empty proposed value and one of
    `UNWRITTEN_KINDS`. Anything else raises: a damaged record must not quietly drop the one thing
    that keeps a held value out.
    """
    fields = rerun_fields(site)
    if fields is None:
        return {}
    if search_fields(site) is None:
        return {}
    site_id = str(site.get("site_id") or "")
    value = site.get(RERUN_UNWRITTEN_KEY)
    if not isinstance(value, dict):
        raise InputError(
            f"{site_id}: {RERUN_UNWRITTEN_KEY}={value!r} is not an object; a search plan names the "
            "proposals the mass lane did not write ({} for none)"
        )
    proposals: dict[str, UnwrittenProposal] = {}
    for name, row in value.items():
        if name not in fields:
            raise InputError(f"{site_id}: {RERUN_UNWRITTEN_KEY} names {name!r}, not a rerun field")
        if not isinstance(row, dict) or set(row) != {"change_key", "kind", "proposed"}:
            raise InputError(
                f"{site_id}/{name}: an unwritten proposal is not {{change_key, kind, proposed}}: "
                f"{row!r}"
            )
        texts = (row["change_key"], row["proposed"])
        if not all(isinstance(text, str) and text.strip() for text in texts):
            raise InputError(f"{site_id}/{name}: an unwritten proposal without its key or value")
        if row["kind"] not in UNWRITTEN_KINDS:
            raise InputError(
                f"{site_id}/{name}: kind {row['kind']!r} is not one of {UNWRITTEN_KINDS}"
            )
        proposals[name] = UnwrittenProposal(
            change_key=row["change_key"], proposed=row["proposed"], kind=row["kind"]
        )
    return proposals


def same_value(one: str, other: str) -> bool:
    """Whether two proposed values are the same value, for the unwritten-proposal refusal.

    Deliberately wide, because it guards a refusal: case and whitespace runs are folded, and two
    integers (a `period_start`) compare as numbers, so `-0500` repeats `-500`.
    """
    left, right = (" ".join(value.split()).casefold() for value in (one, other))
    try:
        return int(left) == int(right)
    except ValueError:
        return left == right


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
    its own list). The walk is `blocked_domains.listed_domain_of`, the one `theo_sources` and
    `web_research` use for their own lists.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return "the url does not parse"
    if parts.scheme not in ("http", "https") or not host:
        return "not an http(s) url with a host"
    if listed_domain_of(host, OWN_DOMAINS) is not None:
        return f"{host} is this project's own site: a quote from it would cite our own value"
    blocked = listed_domain_of(host, BLOCKED_DOMAINS)
    if blocked is not None:
        return f"{host} is on pipeline/lyra/blocked_domains.txt ({blocked})"
    return None
