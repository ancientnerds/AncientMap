"""Stage "search" of the search lane: one MiniMax search per (site, search key), stored as evidence.

Block A3 of `output/remediation/logs/remaining_map_2026-09-22.json`: 7,761 of the mass run's 24,255
finder answers are `UNVERIFIABLE`, and 61 % of them sit at sites whose Wikipedia lookup by name came
back missing - the evidence ran out, not the model. Decision 6 of `HANDOVER.md` settles the route:
**MiniMax supplies search only; the reasoning stays on opencode-go/deepseek-v4.1-flash.** This module
is that search and nothing else. It does not judge, and it writes no database.

What one batch does, in order (`search_batch`):

1. **The quota gate** (`quota_stop_reason`), before the first search. MiniMax's Token Plan is shared
   with Lyra and Theo, so this job yields first: it stops at the prospector's floors (weekly <= 25 %,
   5 h <= 20 %; `pipeline/lyra/prospector/__init__.py`), which sit above Theo's own freeze, and it
   refuses to run inside Theo's end-of-week batch window. Unlike the prospector it **fails closed**: a
   probe that failed, or that is missing any value the gate reads, stops the batch - a missing field
   never satisfies it.
2. **One query per search slot** (`build_query`): the stored name as a phrase plus the *other* stored
   fields that narrow it. A query never carries the stored value of a field it is asked for: the
   templates cannot name one (`QUERY_SLOTS`, checked when this module loads), and a slot value that
   happens to contain it raises rather than being sent.
3. **One ledger line per request**, `kind="fetch"`, label `<site>/minimax_search.<key>`, the url the
   endpoint plus `?q=<query>` - the key travels in a header and appears nowhere else. A transport
   failure, a 408/429/5xx and a 2xx whose body carries no usable answer are retried up to
   `fetch_stage.MAX_ATTEMPTS` times, every attempt its own line. An auth failure, the budget (2056),
   the plan's rate cap (2062) and a contract break stop the stage at once: each one would repeat on
   the next request.
4. **One evidence file per search**, `search_evidence.SearchRecord` in the batch's own evidence
   store. An existing file means "already searched" (a re-run costs nothing), and the store refuses
   different bytes over it.
5. **The report**, `search.json`, in `fetch.json`'s own shape (`sites[].outcomes[].failure`), so
   `model_stage.read_fetch_failures` reads a failed search exactly like a failed fetch - "the search
   failed" and "the search found nothing" stay two different facts in front of the judge - plus the
   quota readings before and after the batch: `weekly_remains_tokens` is the only honest cost signal
   the plan has (the API's own usage figure misses billed tokens by ~7x).

`run.py search` exits 0 when every slot has a stored search, `SEARCH_INCOMPLETE_EXIT` when some failed
(the mass driver then does not judge the batch, and a re-run retries only those), and `STOP_RUN_EXIT`
when the gate refused or a stop-class error arrived (the driver stops the whole run).

The pace is `fetch_stage.HostPacer` over the shared pacing directory at `SEARCH_MIN_INTERVAL_SECONDS`
between requests to the MiniMax host, across every process of a `--jobs N` run. One second is a
chosen bound, not a measurement: nothing in this repository states the search endpoint's rate limit,
and the gold-standard pilot (W9) is where the 2062 throttle gets measured.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote, urlencode

import httpx

# Dual use, same shim as the other phase-3 modules. `search_evidence` (imported below) puts the
# repository root on the path for `pipeline.lyra`.
if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase3 import discover_stage as DS  # noqa: E402  - a site record's stored values
from phase3 import fetch_stage as F  # noqa: E402  - the store, the pacer, the retry bounds
from phase3 import ledger as L  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402  - the record this stage writes
from phase3.model import Stage  # noqa: E402
from phase3.run import InputError  # noqa: E402  - one spelling per concept, not a second

# `pipeline` is importable once `search_evidence` has put the repository root on the path.
from pipeline.lyra.minimax_shared import (  # noqa: E402
    MINIMAX_SEARCH_PATH,
    CodingPlanAuthError,
    CodingPlanError,
    CodingPlanHTTPError,
    CodingPlanQuotaError,
    CodingPlanShapeError,
    CodingPlanThrottleError,
    CodingPlanTransportError,
    SearchResponse,
    create_minimax_client,
    hours_until_weekly_reset,
    minimax_search_strict,
)

#: The pace between two requests to the MiniMax host, across processes. A chosen bound until the
#: pilot measures the plan's rate cap (see the module docstring).
SEARCH_MIN_INTERVAL_SECONDS = 1.0

#: The prospector's floors (`pipeline/lyra/prospector/__init__.py`, `QUOTA_WEEKLY_FLOOR_PCT` and
#: `QUOTA_FIVE_HOUR_FLOOR_PCT`), stricter than Theo's freeze at 5 %, so a remediation job always yields
#: first. Copied rather than imported because that package opens the database layer on import; a test
#: holds the copies to the originals.
QUOTA_WEEKLY_FLOOR_PCT = 25
QUOTA_FIVE_HOUR_FLOOR_PCT = 20

#: Theo's end-of-week batch window (`api/services/theo_config.py`, `THEO_BATCH_MAX_DAYS_TO_RESET`):
#: batch papers start only this many days before the Monday 00:00 UTC reset and spend that week's
#: surplus. A search run inside it would eat exactly that surplus. Copied because importing `api`
#: builds the whole application; a test holds the copy to the original.
THEO_BATCH_MAX_DAYS_TO_RESET = 3.0

#: The probe fields the gate reads. Every one must be present and a number, or the gate stops.
QUOTA_FIELDS = (
    "five_hour_remaining_percent",
    "weekly_remaining_percent",
    "weekly_remains_tokens",
)

#: The query of each search key. `{name}` is the stored name as a phrase; the other slots are stored
#: values of **other** fields. Wording from the brief (W4), to be frozen after the pilot the way the
#: discover question was frozen.
QUERY_TEMPLATES: dict[str, str] = {
    "period_start": '"{name}" {country} archaeological site date century BC built',
    "site_type": '"{name}" {country} archaeological site',
    "country": '"{name}" {site_type} archaeological site location',
    "text": '"{name}" {country} {site_type}',
}

#: Which stored fields each template reads, besides the name.
QUERY_SLOTS: dict[str, tuple[str, ...]] = {
    "period_start": ("country",),
    "site_type": ("country",),
    "country": ("site_type",),
    "text": ("country", "site_type"),
}


def _check_templates() -> None:
    """A template may never read a field its own search is asked about. Checked when this loads."""
    for key, slots in QUERY_SLOTS.items():
        served = {name for name, served_by in SE.SEARCH_KEY_FOR_FIELD.items() if served_by == key}
        leaked = served & set(slots)
        if leaked:
            raise InputError(f"the {key!r} query reads {sorted(leaked)}, a field it is asked about")
        named = {part.split("}")[0] for part in QUERY_TEMPLATES[key].split("{")[1:]}
        if named != {"name", *slots}:
            raise InputError(f"the {key!r} template names {sorted(named)}, not name + {slots}")
    if set(QUERY_TEMPLATES) != set(SE.SEARCH_KEY_FOR_FIELD.values()):
        raise InputError("every search key needs exactly one query template")


_check_templates()


def _stored_text(site: Mapping[str, Any], field_name: str) -> str:
    """A stored value as query text: `""` when the field stores nothing."""
    value = DS.field_finding(site, field_name).get("current_value")
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def build_query(site: Mapping[str, Any], slot: SE.SearchSlot) -> str:
    """The one query of this slot: the name as a phrase, plus the other stored fields.

    A `"` inside the name is removed, because a phrase cannot contain its own delimiter (one of the
    5,004 snapshot names has one: `Arkheologicheskiy Muzey-Zapovednik "Tanais"`). A slot that
    stores nothing is left out rather than filled with a guess.
    """
    site_id = str(site.get("site_id") or "")
    name = str(site.get("name") or "").replace('"', "").strip()
    if not name:
        raise InputError(f"{site_id}: a search starts from the stored name, and there is none")
    values = {slot_field: _stored_text(site, slot_field) for slot_field in QUERY_SLOTS[slot.key]}
    for asked in slot.fields:
        stored = _stored_text(site, asked).casefold()
        for slot_field, value in values.items():
            if stored and stored in value.casefold():
                raise InputError(
                    f"{site_id}: the stored {slot_field} {value!r} contains the stored {asked} "
                    f"{stored!r}; a query that carried it would search for the value under test"
                )
    query = QUERY_TEMPLATES[slot.key].format(name=name, **values)
    return " ".join(query.split())


def search_ledger_url(endpoint: str, query: str) -> str:
    """The endpoint plus `?q=<query>`: the line's url. The request is a POST; no key is in it."""
    return f"{endpoint}?{urlencode({'q': query}, quote_via=quote)}"


# ── the gate ──────────────────────────────────────────────────────────────────────────────────────


def utc_now() -> datetime:
    """The clock the live command gives the gate; a module function so a test can stand in for it."""
    return datetime.now(UTC)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def quota_stop_reason(probe: Mapping[str, Any], *, now_utc: datetime) -> str | None:
    """Why this job may not search now, or `None` when it may. Fails closed.

    `probe` is `minimax_shared.probe_minimax_quota(force=True)`'s answer. A failed probe stops; so
    does a probe that lacks any of `QUOTA_FIELDS` or carries a non-number there - the gate is never
    satisfied by a value it could not read.
    """
    if probe.get("ok") is not True:
        return f"the quota probe did not answer (ok={probe.get('ok')!r}, {probe.get('error')!r})"
    for name in QUOTA_FIELDS:
        if not _number(probe.get(name)):
            return f"the quota probe carries no number for {name} ({probe.get(name)!r})"
    weekly = probe["weekly_remaining_percent"]
    five = probe["five_hour_remaining_percent"]
    if weekly <= QUOTA_WEEKLY_FLOOR_PCT:
        return f"weekly quota at {weekly}%, at or below the {QUOTA_WEEKLY_FLOOR_PCT}% floor"
    if five <= QUOTA_FIVE_HOUR_FLOOR_PCT:
        return f"5h quota at {five}%, at or below the {QUOTA_FIVE_HOUR_FLOOR_PCT}% floor"
    days_left = hours_until_weekly_reset(now_utc) / 24
    if days_left <= THEO_BATCH_MAX_DAYS_TO_RESET:
        return (
            f"{days_left:.2f} days before the weekly reset is inside Theo's batch window (the "
            f"last {THEO_BATCH_MAX_DAYS_TO_RESET:g} days); that surplus is Theo's"
        )
    return None


def quota_reading(probe: Mapping[str, Any]) -> dict[str, Any]:
    """What the report records of one probe: the gate's fields, and the error when it failed."""
    reading: dict[str, Any] = {"ok": probe.get("ok") is True}
    if not reading["ok"]:
        reading["error"] = probe.get("error")
    for name in (*QUOTA_FIELDS, "five_hour_remains_tokens"):
        reading[name] = probe.get(name)
    return reading


# ── the seam ──────────────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class Searcher(Protocol):
    """The seam, like `fetch_stage.Fetcher`: tests pass a scripted one and open no socket."""

    #: The endpoint's url without the key; the ledger line is built from it.
    endpoint: str

    def search(self, query: str) -> SearchResponse:
        """Answer one query, or raise a `minimax_shared.CodingPlanError`."""
        ...


class MiniMaxSearcher:
    """The real searcher: `minimax_search_strict` over the Token Plan client."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self.endpoint = str(client.base_url).rstrip("/") + MINIMAX_SEARCH_PATH

    @classmethod
    def from_settings(cls) -> MiniMaxSearcher:
        """Build the client from `LyraSettings` - the pipeline reads the key, never this module."""
        from pipeline.lyra.config import _get_settings

        settings = _get_settings()
        if not settings.minimax_api_key or not settings.minimax_base_url:
            raise InputError(
                "LyraSettings carries no MiniMax key or base url (LYRA_MINIMAX_API_KEY / "
                "LYRA_MINIMAX_BASE_URL); the search stage cannot ask anything"
            )
        return cls(create_minimax_client(settings.minimax_base_url, settings.minimax_api_key))

    def search(self, query: str) -> SearchResponse:
        return minimax_search_strict(self._client, query)

    def close(self) -> None:
        self._client.close()


# ── one batch ─────────────────────────────────────────────────────────────────────────────────────

#: The errors that end the whole stage at once: each one would come back on the next request.
STOP_ERRORS: tuple[type[CodingPlanError], ...] = (
    CodingPlanAuthError,
    CodingPlanQuotaError,
    CodingPlanThrottleError,
    CodingPlanShapeError,
)


@dataclass(frozen=True)
class SearchAttempt:
    """One request: exactly the shape of its ledger line."""

    attempt: int
    outcome: L.FetchOutcome
    http_status: int | None
    bytes: int
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "bytes": self.bytes,
            "error": self.error,
            "http_status": self.http_status,
            "outcome": self.outcome.value,
        }


@dataclass
class SlotOutcome:
    """What one search slot of one site ended with."""

    feature: str
    fields: tuple[str, ...]
    query: str
    url: str
    attempts: list[SearchAttempt] = field(default_factory=list)
    existing: bool = False
    stored: bool = False
    hits: int = 0
    linkless: int = 0
    excluded: int = 0
    failure: str | None = None
    #: Set when this slot's last answer was a stop-class error: the stage ends after it.
    stops: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts": [a.to_dict() for a in self.attempts],
            "excluded": self.excluded,
            "existing": self.existing,
            "failure": self.failure,
            "feature": self.feature,
            "fields": list(self.fields),
            "hits": self.hits,
            "linkless": self.linkless,
            "query": self.query,
            "requests": len(self.attempts),
            "stops": self.stops,
            "stored": self.stored,
            "url": self.url,
        }


@dataclass
class SiteSearch:
    site_id: str
    outcomes: list[SlotOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"site_id": self.site_id, "outcomes": [o.to_dict() for o in self.outcomes]}


@dataclass
class SearchReport:
    """One batch's search stage. Deterministic but for the quota readings (the ledger has the clock)."""

    batch_id: str
    endpoint: str
    sites: list[SiteSearch] = field(default_factory=list)
    quota_before: dict[str, Any] | None = None
    quota_after: dict[str, Any] | None = None
    stopped: str | None = None

    @property
    def outcomes(self) -> list[SlotOutcome]:
        return [o for s in self.sites for o in s.outcomes]

    @property
    def failed(self) -> list[SlotOutcome]:
        return [o for o in self.outcomes if o.failure is not None]

    def to_json(self) -> str:
        outcomes = self.outcomes
        payload = {
            "batch_id": self.batch_id,
            "endpoint": self.endpoint,
            "quota": {"after": self.quota_after, "before": self.quota_before},
            "sites": [s.to_dict() for s in self.sites],
            "stopped": self.stopped,
            "totals": {
                "excluded": sum(o.excluded for o in outcomes),
                "existing": sum(o.existing for o in outcomes),
                "failed": len(self.failed),
                "hits": sum(o.hits for o in outcomes),
                "linkless": sum(o.linkless for o in outcomes),
                "requests": sum(len(o.attempts) for o in outcomes),
                "slots": len(outcomes),
                "stored": sum(o.stored for o in outcomes),
            },
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def write_report(path: Path, report: SearchReport) -> None:
    """`search.json`, written to a temp file and swapped in: a reader sees a whole report or none."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def stored_record(query: str, response: SearchResponse) -> SE.SearchRecord:
    """The record of one answer: the hits that name a page, as text, in engine order.

    `null` for a title, snippet or date is how an engine says it has none, and is stored as `""`;
    any other non-text value is a contract break and stops the stage (`CodingPlanShapeError`).
    """
    hits: list[SE.StoredHit] = []
    for hit in response.hits:
        texts: dict[str, str] = {}
        for name in ("title", "snippet", "date"):
            value = getattr(hit.result, name)
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise CodingPlanShapeError(
                    f"MiniMax search {query!r}: result {hit.rank} carries {name}={value!r}, not "
                    "text",
                    http_status=response.http_status,
                    body_bytes=response.body_bytes,
                )
            texts[name] = value
        hits.append(SE.StoredHit(rank=hit.rank, url=hit.result.url, **texts))
    return SE.SearchRecord(query=query, hits=tuple(hits), linkless=response.linkless)


def _attempt_line(exc: CodingPlanError | None, response: SearchResponse | None) -> SearchAttempt:
    """What one request looked like on the wire, for its ledger line."""
    if response is not None:
        return SearchAttempt(0, L.FetchOutcome.OK, response.http_status, response.body_bytes, None)
    assert exc is not None
    if isinstance(exc, CodingPlanTransportError) or exc.http_status is None:
        return SearchAttempt(0, L.FetchOutcome.TRANSPORT_FAILURE, None, 0, str(exc))
    kind = L.FetchOutcome.OK if 200 <= exc.http_status < 300 else L.FetchOutcome.HTTP_ERROR
    return SearchAttempt(0, kind, exc.http_status, exc.body_bytes, None)


def _retryable(exc: CodingPlanError) -> bool:
    """Weather is retried; an answer the next request would repeat is not."""
    if isinstance(exc, STOP_ERRORS):
        return False
    if isinstance(exc, CodingPlanHTTPError):
        return F.is_retryable_status(exc.http_status)
    return True  # a transport failure, or a 2xx that carried no usable answer


def search_slot(
    *,
    batch_id: str,
    site_id: str,
    slot: SE.SearchSlot,
    query: str,
    searcher: Searcher,
    store: F.EvidenceStore,
    ledger: L.Ledger,
    wait: Callable[[], None],
    sleep: Callable[[float], None],
    stage: Stage = Stage.FINDER,
) -> SlotOutcome:
    """Ask one query, up to `fetch_stage.MAX_ATTEMPTS` times. Every request is one ledger line.

    The line goes down before anything else happens with the answer (the fetch stage's rule: a request
    that left the machine is visible even if the next line of code does not run). A stop-class error
    ends the slot at once and sets `stops`, so the batch ends after it with every attempt on record.
    """
    url = search_ledger_url(searcher.endpoint, query)
    outcome = SlotOutcome(feature=slot.feature, fields=slot.fields, query=query, url=url)
    for number in range(1, F.MAX_ATTEMPTS + 1):
        wait()
        response: SearchResponse | None = None
        error: CodingPlanError | None = None
        try:
            response = searcher.search(query)
        except CodingPlanError as exc:
            error = exc
        line = _attempt_line(error, response)
        line = SearchAttempt(number, line.outcome, line.http_status, line.bytes, line.error)
        last = error is None or not _retryable(error) or number == F.MAX_ATTEMPTS
        ledger.append(
            L.Entry(
                kind=L.LedgerKind.FETCH,
                stage=stage,
                batch_id=batch_id,
                label=f"{site_id}/{slot.feature}",
                url=url,
                http_status=line.http_status,
                bytes=line.bytes,
                outcome=line.outcome,
                attempt=number,
                error=line.error,
                given_up=last and error is not None,
            )
        )
        outcome.attempts.append(line)
        if response is not None:
            try:
                record = stored_record(query, response)
            except CodingPlanShapeError as exc:
                outcome.failure = f"search failed: {exc} ({number} request(s) recorded)"
                outcome.stops = True
                return outcome
            store.write(site_id=site_id, feature=slot.feature, body=record.to_bytes())
            outcome.stored = True
            outcome.hits = len(record.hits)
            outcome.linkless = record.linkless
            outcome.excluded = sum(SE.excluded_because(h.url) is not None for h in record.hits)
            return outcome
        assert error is not None
        if last:
            outcome.failure = f"search failed: {error} ({number} request(s) recorded)"
            outcome.stops = isinstance(error, STOP_ERRORS)
            return outcome
        sleep(F.RETRY_BACKOFF_SECONDS[number - 1])
    raise AssertionError("unreachable: the loop returns on its last attempt")  # pragma: no cover


def search_batch(
    *,
    batch: Mapping[str, Any],
    searcher: Searcher,
    store: F.EvidenceStore,
    ledger: L.Ledger,
    probe: Callable[[], Mapping[str, Any]],
    now: Callable[[], datetime],
    wait: Callable[[], None],
    sleep: Callable[[float], None] = time.sleep,
) -> SearchReport:
    """Search every slot of every site of one search batch. Never raises for a failed search.

    The gate runs first (`probe` is `probe_minimax_quota(force=True)`); a refusal is the report's
    `stopped` and no request is made. A stop-class error during the batch ends it the same way. Slots
    the batch did not reach are recorded as failed with that reason, so no slot is missing from the
    report and a judge run cannot mistake an unasked search for an empty one. A batch whose searches
    are all on disk already makes no request, so it is neither probed nor gated (its quota readings
    stay `None`): a resumed batch must not be kept from its judge by a quota it will not touch.
    """
    batch_id = str(batch.get("batch_id") or "")
    sites = batch.get("sites")
    if not batch_id or not isinstance(sites, list) or not sites:
        raise InputError(f"{batch_id or 'a batch'}: a search batch needs a batch_id and sites")
    plan: list[tuple[str, SE.SearchSlot, str]] = []
    report = SearchReport(batch_id=batch_id, endpoint=searcher.endpoint)
    for site in sites:
        site_id = str(site.get("site_id") or "")
        slots = SE.search_slots(site)
        if not site_id or not slots:
            raise InputError(
                f"{batch_id}: site {site_id or '?'} carries no rerun_fields; a search batch reruns "
                "named fields only"
            )
        report.sites.append(SiteSearch(site_id=site_id))
        plan.extend((site_id, slot, build_query(site, slot)) for slot in slots)

    pending = [
        (site_id, slot) for site_id, slot, _ in plan if not store.exists(site_id, slot.feature)
    ]
    if pending:
        # The gate guards MiniMax requests. A resumed batch whose searches are all on disk makes
        # none, so it is neither probed nor stopped - its judge runs on the Pi route, not on MiniMax.
        reading = probe()
        report.quota_before = quota_reading(reading)
        report.stopped = quota_stop_reason(reading, now_utc=now())
    by_site = {s.site_id: s for s in report.sites}
    for site_id, slot, query in plan:
        if store.exists(site_id, slot.feature):
            by_site[site_id].outcomes.append(
                SlotOutcome(
                    feature=slot.feature,
                    fields=slot.fields,
                    query=query,
                    url=search_ledger_url(searcher.endpoint, query),
                    existing=True,
                )
            )
            continue
        if report.stopped is not None:
            by_site[site_id].outcomes.append(
                SlotOutcome(
                    feature=slot.feature,
                    fields=slot.fields,
                    query=query,
                    url=search_ledger_url(searcher.endpoint, query),
                    failure=f"not searched: the stage stopped ({report.stopped}); 0 requests",
                )
            )
            continue
        outcome = search_slot(
            batch_id=batch_id,
            site_id=site_id,
            slot=slot,
            query=query,
            searcher=searcher,
            store=store,
            ledger=ledger,
            wait=wait,
            sleep=sleep,
        )
        by_site[site_id].outcomes.append(outcome)
        if outcome.stops:
            report.stopped = f"{site_id}/{slot.feature}: {outcome.failure}"
    if pending:
        report.quota_after = quota_reading(probe())
    return report
